#!/usr/bin/env python3

from __future__ import annotations

import copy
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "toolchain_archive.py"
SPEC = importlib.util.spec_from_file_location("toolchain_archive", MODULE_PATH)
assert SPEC and SPEC.loader
archive_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive_tool)


def json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def add_directory(archive: tarfile.TarFile, name: str) -> None:
    member = tarfile.TarInfo(name)
    member.type = tarfile.DIRTYPE
    member.mode = 0o755
    archive.addfile(member)


def add_file(
    archive: tarfile.TarFile,
    name: str,
    value: bytes,
    *,
    member_type: bytes | None = None,
) -> None:
    member = tarfile.TarInfo(name)
    member.mode = 0o644
    member.size = len(value)
    if member_type is not None:
        member.type = member_type
        if member_type in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
            member.linkname = "target"
            member.size = 0
            archive.addfile(member)
            return
    archive.addfile(member, io.BytesIO(value))


def make_archive(
    directory: Path,
    architecture: str,
    *,
    config_mutator=None,
    manifest_mutator=None,
    index_mutator=None,
    docker_mutator=None,
    repositories_mutator=None,
    duplicate_index: bool = False,
    duplicate_extra: bool = False,
    wrong_blob_name: bool = False,
    extra_tar_member: tuple[str, bytes, bytes | None] | None = None,
    duplicate_tar_member: bool = False,
    image_id_override: str | None = None,
    capture_bomb: tuple[int, int] | None = None,
) -> tuple[Path, dict]:
    image_tag = f"cores-{architecture}:latest"
    host_cc = "aarch64-linux-gnu" if architecture == "arm64" else "arm-a30-linux-gnueabihf"
    dockerfile_name = f"Dockerfile.{architecture}"
    dockerfile = directory / dockerfile_name
    dockerfile.write_text(f"FROM synthetic-{architecture}\n", encoding="utf-8")
    dockerfile_sha256 = digest(dockerfile.read_bytes())

    layer_values = [b"synthetic layer one\n", b"synthetic layer two\n"]
    layer_digests = [digest(value) for value in layer_values]
    config = {
        "architecture": "amd64",
        "os": "linux",
        "config": {
            "Env": ["PATH=/usr/bin", f"HOST_CC={host_cc}"],
            "WorkingDir": "/libretro-super",
        },
        "rootfs": {
            "type": "layers",
            "diff_ids": [f"sha256:{value}" for value in layer_digests],
        },
    }
    if config_mutator:
        config_mutator(config)
    config_value = json_bytes(config)
    config_digest = digest(config_value)
    manifest = {
        "schemaVersion": 2,
        "mediaType": archive_tool.OCI_MANIFEST_MEDIA_TYPE,
        "config": {
            "mediaType": archive_tool.OCI_CONFIG_MEDIA_TYPE,
            "digest": f"sha256:{config_digest}",
            "size": len(config_value),
        },
        "layers": [
            {
                "mediaType": archive_tool.OCI_LAYER_MEDIA_TYPE,
                "digest": f"sha256:{layer_digest}",
                "size": len(layer_value),
            }
            for layer_digest, layer_value in zip(layer_digests, layer_values)
        ],
    }
    if manifest_mutator:
        manifest_mutator(manifest)
    manifest_value = json_bytes(manifest)
    manifest_digest = digest(manifest_value)
    index = {
        "schemaVersion": 2,
        "mediaType": archive_tool.OCI_INDEX_MEDIA_TYPE,
        "manifests": [
            {
                "mediaType": archive_tool.OCI_MANIFEST_MEDIA_TYPE,
                "digest": f"sha256:{manifest_digest}",
                "size": len(manifest_value),
                "annotations": {
                    "io.containerd.image.name": f"docker.io/library/{image_tag}",
                    "org.opencontainers.image.ref.name": "latest",
                },
            }
        ],
    }
    if index_mutator:
        index_mutator(index)
    docker_manifest = [
        {
            "Config": f"blobs/sha256/{config_digest}",
            "RepoTags": [image_tag],
            "Layers": [f"blobs/sha256/{value}" for value in layer_digests],
            "LayerSources": {
                f"sha256:{layer_digest}": {
                    "mediaType": archive_tool.OCI_LAYER_MEDIA_TYPE,
                    "size": len(layer_value),
                    "digest": f"sha256:{layer_digest}",
                }
                for layer_digest, layer_value in zip(layer_digests, layer_values)
            },
        }
    ]
    if docker_mutator:
        docker_mutator(docker_manifest)
    repositories = {f"cores-{architecture}": {"latest": layer_digests[-1]}}
    if repositories_mutator:
        repositories_mutator(repositories)
    extra_value = (
        b'{"id":"legacy","id":"duplicate"}'
        if duplicate_extra
        else b'{"id":"legacy","os":"linux"}'
    )
    extra_digest = digest(extra_value)
    index_value = json_bytes(index)
    if duplicate_index:
        rendered_descriptor = json.dumps(index["manifests"], separators=(",", ":"))
        index_value = (
            '{"schemaVersion":2,"schemaVersion":2,"mediaType":'
            + json.dumps(archive_tool.OCI_INDEX_MEDIA_TYPE)
            + ',"manifests":'
            + rendered_descriptor
            + "}"
        ).encode()

    members = [
        (f"blobs/sha256/{config_digest}", config_value),
        (f"blobs/sha256/{manifest_digest}", manifest_value),
        (f"blobs/sha256/{extra_digest}", extra_value),
    ]
    for layer_digest, layer_value in zip(layer_digests, layer_values):
        name_digest = "0" * 64 if wrong_blob_name and layer_digest == layer_digests[0] else layer_digest
        members.append((f"blobs/sha256/{name_digest}", layer_value))
    members.extend(
        [
            ("index.json", index_value),
            ("manifest.json", json_bytes(docker_manifest)),
            ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}'),
            ("repositories", json_bytes(repositories)),
        ]
    )
    if capture_bomb:
        count, size = capture_bomb
        members.extend(
            (f"capture-bomb-{index}", b"x" * size) for index in range(count)
        )
    path = directory / f"cores-{architecture}.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        add_directory(archive, "blobs/")
        add_directory(archive, "blobs/sha256/")
        for name, value in members:
            add_file(archive, name, value)
        if duplicate_tar_member:
            add_file(archive, "index.json", index_value)
        if extra_tar_member:
            name, value, member_type = extra_tar_member
            add_file(archive, name, value, member_type=member_type)
    contract = {
        "archive_filename": path.name,
        "archive_sha256": None,
        "archive_size": None,
        "image_tag": image_tag,
        "image_id": image_id_override or f"sha256:{config_digest}",
        "container_os": "linux",
        "container_architecture": "amd64",
        "target_host_cc": host_cc,
        "workdir": "/libretro-super",
        "dockerfile": dockerfile_name,
        "dockerfile_sha256": dockerfile_sha256,
    }
    return path, contract


def make_download_fixture(root: Path) -> tuple[dict[str, Path], Path, dict]:
    paths = {}
    contracts = {}
    toolchains = {}
    for architecture in ("arm64", "armhf"):
        arch_root = root / architecture
        arch_root.mkdir()
        path, contract = make_archive(arch_root, architecture)
        dockerfile = root / contract["dockerfile"]
        dockerfile.write_bytes((arch_root / contract["dockerfile"]).read_bytes())
        contract["dockerfile_sha256"] = digest(dockerfile.read_bytes())
        paths[architecture] = path
        contracts[architecture] = contract
        toolchains[architecture] = archive_tool.inspect_archive(
            path,
            {**contract, "architecture": architecture},
            repo_root=root,
        )
    document = archive_tool.build_lock_document("local-cache-v1", toolchains)
    lock_path = root / "pins" / "toolchains" / "local-cache-v1.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return paths, lock_path, contracts


class ToolchainArchiveTests(unittest.TestCase):
    def test_valid_archive_is_fully_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            result = archive_tool.inspect_archive(
                path,
                {**contract, "architecture": "arm64"},
                repo_root=root,
            )
            self.assertEqual(digest(path.read_bytes()), result["archive"]["sha256"])
            self.assertEqual(path.stat().st_size, result["archive"]["size"])
            self.assertGreater(result["archive"]["uncompressed_size"], 0)
            self.assertEqual(contract["image_id"], result["image"]["id"])
            self.assertEqual(
                [item["sha256"] for item in result["oci"]["layers"]],
                [value.removeprefix("sha256:") for value in result["oci"]["rootfs_diff_ids"]],
            )
            self.assertEqual(1, len(result["legacy_extra_blobs"]))

    def test_archive_reads_are_chunked_not_read_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            original_read_bytes = Path.read_bytes

            def guarded_read_bytes(candidate: Path) -> bytes:
                if candidate == path:
                    raise AssertionError("archive read_bytes is forbidden")
                return original_read_bytes(candidate)

            with mock.patch.object(Path, "read_bytes", guarded_read_bytes):
                archive_tool.inspect_archive(
                    path,
                    {**contract, "architecture": "arm64"},
                    repo_root=root,
                )

    def test_pinned_size_is_checked_before_gzip_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            contract["archive_size"] = path.stat().st_size + 1
            with mock.patch.object(
                archive_tool.gzip, "GzipFile", side_effect=AssertionError("gzip opened")
            ):
                with self.assertRaisesRegex(
                    archive_tool.ToolchainArchiveError, "compressed size"
                ):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_truncation_and_crc_corruption_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            value = path.read_bytes()
            variants = {
                "truncated": value[:-7],
                "crc": value[:-8] + bytes([value[-8] ^ 0xFF]) + value[-7:],
            }
            for label, damaged in variants.items():
                with self.subTest(label=label):
                    candidate = root / f"{label}.tar.gz"
                    candidate.write_bytes(damaged)
                    with self.assertRaises(archive_tool.ToolchainArchiveError):
                        archive_tool.inspect_archive(
                            candidate,
                            {**contract, "architecture": "arm64"},
                            repo_root=root,
                            logical_filename=contract["archive_filename"],
                        )

    def test_uncompressed_limit_stops_gzip_bombs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            with mock.patch.object(archive_tool, "MAX_UNCOMPRESSED_SIZE", 128):
                with self.assertRaisesRegex(
                    archive_tool.ToolchainArchiveError, "uncompressed size"
                ):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_aggregate_capture_limit_stops_many_small_members(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(
                root, "arm64", capture_bomb=(12, 512)
            )
            with mock.patch.object(archive_tool, "MAX_CAPTURE_TOTAL", 4096):
                with self.assertRaisesRegex(
                    archive_tool.ToolchainArchiveError, "aggregate limit"
                ):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_tar_tail_requires_two_zero_blocks_and_rejects_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            with gzip.open(path, "rb") as handle:
                payload = handle.read()
            blocks = [
                payload[index : index + tarfile.BLOCKSIZE]
                for index in range(0, len(payload), tarfile.BLOCKSIZE)
            ]
            last_nonzero = max(
                index for index, block in enumerate(blocks) if any(block)
            )
            variants = {}
            one_marker = b"".join(blocks[: last_nonzero + 2])
            one_marker_path = root / "one-marker.tar.gz"
            with gzip.open(one_marker_path, "wb") as handle:
                handle.write(one_marker)
            variants["one-marker"] = one_marker_path

            nonzero_path = root / "nonzero-tail.tar.gz"
            with gzip.open(nonzero_path, "wb") as handle:
                handle.write(payload + b"nonzero-tail")
            variants["nonzero-tail"] = nonzero_path

            concatenated_path = root / "concatenated.tar.gz"
            concatenated_path.write_bytes(path.read_bytes() + gzip.compress(b"payload"))
            variants["concatenated"] = concatenated_path

            for label, candidate in variants.items():
                with self.subTest(label=label):
                    with self.assertRaises(archive_tool.ToolchainArchiveError):
                        archive_tool.inspect_archive(
                            candidate,
                            {**contract, "architecture": "arm64"},
                            repo_root=root,
                            logical_filename=contract["archive_filename"],
                        )

    def test_unsafe_tar_members_are_rejected(self) -> None:
        cases = {
            "traversal": {"extra_tar_member": ("../escape", b"x", None)},
            "backslash": {"extra_tar_member": ("bad\\name", b"x", None)},
            "duplicate": {"duplicate_tar_member": True},
            "symlink": {
                "extra_tar_member": ("unsafe-link", b"", tarfile.SYMTYPE)
            },
            "device": {
                "extra_tar_member": ("unsafe-device", b"", tarfile.CHRTYPE)
            },
        }
        for label, options in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path, contract = make_archive(root, "arm64", **options)
                with self.assertRaises(archive_tool.ToolchainArchiveError):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_duplicate_key_json_is_rejected_in_graph_and_legacy_metadata(self) -> None:
        for option in ("duplicate_index", "duplicate_extra"):
            with self.subTest(option=option), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path, contract = make_archive(root, "arm64", **{option: True})
                with self.assertRaisesRegex(
                    archive_tool.ToolchainArchiveError, "duplicate key"
                ):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_blob_filename_and_descriptor_mismatches_are_rejected(self) -> None:
        cases = {
            "blob": {"wrong_blob_name": True},
            "index-size": {
                "index_mutator": lambda value: value["manifests"][0].__setitem__(
                    "size", value["manifests"][0]["size"] + 1
                )
            },
            "config-size": {
                "manifest_mutator": lambda value: value["config"].__setitem__(
                    "size", value["config"]["size"] + 1
                )
            },
            "layer-digest": {
                "manifest_mutator": lambda value: value["layers"][0].__setitem__(
                    "digest", f"sha256:{'f' * 64}"
                )
            },
        }
        for label, options in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path, contract = make_archive(root, "arm64", **options)
                with self.assertRaises(archive_tool.ToolchainArchiveError):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_oci_schema_versions_require_exact_integers(self) -> None:
        cases = {
            "index": {
                "index_mutator": lambda value: value.__setitem__(
                    "schemaVersion", 2.0
                )
            },
            "manifest": {
                "manifest_mutator": lambda value: value.__setitem__(
                    "schemaVersion", 2.0
                )
            },
        }
        for label, options in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path, contract = make_archive(root, "arm64", **options)
                with self.assertRaises(archive_tool.ToolchainArchiveError):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_config_identity_platform_workdir_env_and_layer_order_are_rejected(self) -> None:
        cases = {
            "image-id": {"image_id_override": f"sha256:{'f' * 64}"},
            "platform": {
                "config_mutator": lambda value: value.__setitem__("architecture", "arm64")
            },
            "os": {"config_mutator": lambda value: value.__setitem__("os", "windows")},
            "workdir": {
                "config_mutator": lambda value: value["config"].__setitem__(
                    "WorkingDir", "/wrong"
                )
            },
            "env": {
                "config_mutator": lambda value: value["config"].__setitem__(
                    "Env", ["HOST_CC=wrong"]
                )
            },
            "duplicate-env": {
                "config_mutator": lambda value: value["config"]["Env"].append(
                    "HOST_CC=aarch64-linux-gnu"
                )
            },
            "diff-order": {
                "config_mutator": lambda value: value["rootfs"]["diff_ids"].reverse()
            },
        }
        for label, options in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path, contract = make_archive(root, "arm64", **options)
                with self.assertRaises(archive_tool.ToolchainArchiveError):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_docker_save_cross_checks_are_rejected(self) -> None:
        cases = {
            "config": lambda value: value[0].__setitem__(
                "Config", f"blobs/sha256/{'f' * 64}"
            ),
            "tags": lambda value: value[0].__setitem__("RepoTags", ["wrong:latest"]),
            "layers": lambda value: value[0]["Layers"].reverse(),
            "sources": lambda value: next(iter(value[0]["LayerSources"].values())).__setitem__(
                "size", 999
            ),
        }
        for label, mutator in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path, contract = make_archive(root, "arm64", docker_mutator=mutator)
                with self.assertRaises(archive_tool.ToolchainArchiveError):
                    archive_tool.inspect_archive(
                        path,
                        {**contract, "architecture": "arm64"},
                        repo_root=root,
                    )

    def test_verify_downloads_checks_both_archives_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths, lock_path, contracts = make_download_fixture(root)
            self.assertFalse((root / "store").exists())
            before = {
                str(path.relative_to(root)): path.stat().st_mtime_ns
                for path in root.rglob("*")
                if path.is_file()
            }
            report = archive_tool.verify_downloads(
                paths,
                lock_path=lock_path,
                repo_root=root,
                contracts=contracts,
            )
            after = {
                str(path.relative_to(root)): path.stat().st_mtime_ns
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)
            self.assertFalse((root / "store").exists())
            self.assertEqual("valid", report["status"])
            self.assertEqual({"arm64", "armhf"}, set(report["archives"]))
            for architecture, path in paths.items():
                self.assertEqual(
                    digest(path.read_bytes()),
                    report["archives"][architecture]["sha256"],
                )

    def test_verify_downloads_rejects_missing_tampered_and_unsafe_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths, lock_path, contracts = make_download_fixture(root)

            with self.assertRaisesRegex(
                archive_tool.ToolchainArchiveError, "must cover arm64 and armhf"
            ):
                archive_tool.verify_downloads(
                    {"arm64": paths["arm64"]},
                    lock_path=lock_path,
                    repo_root=root,
                    contracts=contracts,
                )

            cases = {}
            renamed = root / "renamed.tar.gz"
            renamed.write_bytes(paths["arm64"].read_bytes())
            cases["filename"] = renamed

            wrong_size_dir = root / "wrong-size"
            wrong_size_dir.mkdir()
            wrong_size = wrong_size_dir / paths["arm64"].name
            wrong_size.write_bytes(paths["arm64"].read_bytes() + b"x")
            cases["size"] = wrong_size

            wrong_sha_dir = root / "wrong-sha"
            wrong_sha_dir.mkdir()
            wrong_sha = wrong_sha_dir / paths["arm64"].name
            changed = bytearray(paths["arm64"].read_bytes())
            changed[len(changed) // 2] ^= 0x01
            wrong_sha.write_bytes(changed)
            cases["SHA256"] = wrong_sha

            symlink_dir = root / "symlink"
            symlink_dir.mkdir()
            symlink = symlink_dir / paths["arm64"].name
            symlink.symlink_to(paths["arm64"])
            cases["regular non-symlink"] = symlink

            directory_dir = root / "directory"
            directory_dir.mkdir()
            directory = directory_dir / paths["arm64"].name
            directory.mkdir()
            cases["regular non-symlink-dir"] = directory

            for expected, candidate in cases.items():
                with self.subTest(expected=expected):
                    with self.assertRaises(archive_tool.ToolchainArchiveError) as raised:
                        archive_tool.verify_downloads(
                            {"arm64": candidate, "armhf": paths["armhf"]},
                            lock_path=lock_path,
                            repo_root=root,
                            contracts=contracts,
                        )
                    self.assertIn(expected.split("-")[0], str(raised.exception))

    def test_verify_downloads_cli_emits_json(self) -> None:
        expected = {
            "status": "valid",
            "lock_id": "local-cache-v1",
            "content_sha256": "a" * 64,
            "archives": {},
        }
        output = io.StringIO()
        with mock.patch.object(
            archive_tool, "verify_downloads", return_value=expected
        ) as verifier, contextlib.redirect_stdout(output):
            result = archive_tool.main(
                [
                    "verify-downloads",
                    "--arm64",
                    "/tmp/cores-arm64.tar.gz",
                    "--armhf",
                    "/tmp/cores-armhf.tar.gz",
                    "--lock",
                    "/tmp/local-cache-v1.json",
                ]
            )
        self.assertEqual(0, result)
        self.assertEqual(expected, json.loads(output.getvalue()))
        verifier.assert_called_once()

    def test_verify_downloads_cli_preserves_symlinks_for_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.tar.gz"
            target.write_bytes(b"archive")
            arm64 = root / "cores-arm64.tar.gz"
            arm64.symlink_to(target)
            armhf = root / "cores-armhf.tar.gz"
            armhf.write_bytes(b"archive")
            with mock.patch.object(
                archive_tool,
                "verify_downloads",
                side_effect=archive_tool.ToolchainArchiveError("symlink rejected"),
            ) as verifier, contextlib.redirect_stderr(io.StringIO()):
                result = archive_tool.main(
                    [
                        "verify-downloads",
                        "--arm64",
                        str(arm64),
                        "--armhf",
                        str(armhf),
                    ]
                )
            self.assertEqual(2, result)
            supplied = verifier.call_args.args[0]
            self.assertEqual(arm64, supplied["arm64"])
            self.assertTrue(supplied["arm64"].is_symlink())

    def test_stage_is_atomic_idempotent_create_only_and_mode_0644(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = {}
            contracts = {}
            for architecture in ("arm64", "armhf"):
                arch_root = root / architecture
                arch_root.mkdir()
                path, contract = make_archive(arch_root, architecture)
                # Lock validation resolves both Dockerfiles from one repository root.
                (root / contract["dockerfile"]).write_bytes(
                    (arch_root / contract["dockerfile"]).read_bytes()
                )
                contract["dockerfile_sha256"] = digest(
                    (root / contract["dockerfile"]).read_bytes()
                )
                paths[architecture] = path
                contracts[architecture] = contract
            output = root / "pins" / "toolchains" / "local-cache-v1.json"
            store = root / "store"
            document = archive_tool.import_lock(
                paths,
                output=output,
                store_root=store,
                repo_root=root,
                contracts=contracts,
            )
            archive_tool.validate_lock_document(
                document, repo_root=root, contracts=contracts
            )
            for architecture, entry in document["toolchains"].items():
                staged = store / entry["archive"]["store_path"]
                self.assertTrue(staged.is_file())
                self.assertEqual(0o644, stat.S_IMODE(staged.stat().st_mode))
                self.assertEqual(entry["archive"]["sha256"], archive_tool.sha256_file(staged))
                contract = {**contracts[architecture], "architecture": architecture}
                repeated = archive_tool.inspect_archive(
                    paths[architecture],
                    contract,
                    repo_root=root,
                    stage_store=store,
                )
                self.assertEqual(entry, repeated)
            self.assertEqual([], list(store.rglob(".incoming-*")))
            with self.assertRaisesRegex(
                archive_tool.ToolchainArchiveError, "refusing to replace"
            ):
                archive_tool.import_lock(
                    paths,
                    output=output,
                    store_root=store,
                    repo_root=root,
                    contracts=contracts,
                )
            report = archive_tool.validate_lock(
                output,
                verify_store=True,
                store_root=store,
                repo_root=root,
                contracts=contracts,
            )
            self.assertEqual("verified", report["store"])

    def test_staging_cleanup_and_symlink_collision_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bad_path, bad_contract = make_archive(
                root,
                "arm64",
                config_mutator=lambda value: value.__setitem__("os", "windows"),
            )
            store = root / "store"
            with self.assertRaises(archive_tool.ToolchainArchiveError):
                archive_tool.inspect_archive(
                    bad_path,
                    {**bad_contract, "architecture": "arm64"},
                    repo_root=root,
                    stage_store=store,
                )
            self.assertEqual([], list(store.rglob(".incoming-*")))

            good_path, good_contract = make_archive(root, "armhf")
            contract = {**good_contract, "architecture": "armhf"}
            result = archive_tool.inspect_archive(good_path, contract, repo_root=root)
            destination = store / result["archive"]["store_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            target = root / "collision-target"
            target.write_bytes(b"wrong")
            destination.symlink_to(target)
            with self.assertRaisesRegex(
                archive_tool.ToolchainArchiveError, "collision"
            ):
                archive_tool.inspect_archive(
                    good_path,
                    contract,
                    repo_root=root,
                    stage_store=store,
                )
            self.assertEqual([], list(store.rglob(".incoming-*")))

    def test_symlinked_store_and_lock_ancestors_fail_before_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, contract = make_archive(root, "arm64")
            outside_store = root / "outside-store"
            outside_store.mkdir()
            store_link = root / "store-link"
            store_link.symlink_to(outside_store, target_is_directory=True)
            with self.assertRaisesRegex(
                archive_tool.ToolchainArchiveError, "must not traverse"
            ):
                archive_tool.inspect_archive(
                    path,
                    {**contract, "architecture": "arm64"},
                    repo_root=root,
                    stage_store=store_link / "nested",
                )
            self.assertEqual([], list(outside_store.iterdir()))

            outside_lock = root / "outside-lock"
            outside_lock.mkdir()
            lock_link = root / "lock-link"
            lock_link.symlink_to(outside_lock, target_is_directory=True)
            with self.assertRaisesRegex(
                archive_tool.ToolchainArchiveError, "must not traverse"
            ):
                archive_tool._atomic_create_json(
                    lock_link / "nested" / "local-cache-v1.json", {"test": True}
                )
            self.assertEqual([], list(outside_lock.iterdir()))

    def test_untrusted_lock_types_raise_contract_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            toolchains = {}
            contracts = {}
            for architecture in ("arm64", "armhf"):
                arch_root = root / architecture
                arch_root.mkdir()
                path, contract = make_archive(arch_root, architecture)
                (root / contract["dockerfile"]).write_bytes(
                    (arch_root / contract["dockerfile"]).read_bytes()
                )
                contract["dockerfile_sha256"] = digest(
                    (root / contract["dockerfile"]).read_bytes()
                )
                contracts[architecture] = contract
                toolchains[architecture] = archive_tool.inspect_archive(
                    path,
                    {**contract, "architecture": architecture},
                    repo_root=root,
                )
            document = archive_tool.build_lock_document("local-cache-v1", toolchains)
            mutations = [
                lambda value: value.__setitem__("schema_version", True),
                lambda value: value["toolchains"]["arm64"]["archive"].__setitem__(
                    "sha256", None
                ),
                lambda value: value["toolchains"]["arm64"]["archive"].__setitem__(
                    "size", True
                ),
                lambda value: value["toolchains"]["arm64"]["oci"]["config"].__setitem__(
                    "sha256", 3
                ),
                lambda value: value["toolchains"]["arm64"]["oci"]["config"].__setitem__(
                    "size", True
                ),
                lambda value: value["toolchains"]["arm64"]["oci"]["manifest"].__setitem__(
                    "size", True
                ),
                lambda value: value["toolchains"]["arm64"]["oci"]["layers"][0].__setitem__(
                    "sha256", []
                ),
                lambda value: value["toolchains"]["arm64"]["oci"]["layers"][0].__setitem__(
                    "size", True
                ),
                lambda value: value["toolchains"]["arm64"]["legacy_extra_blobs"][0].__setitem__(
                    "sha256", {}
                ),
                lambda value: value["toolchains"]["arm64"]["legacy_extra_blobs"][0].__setitem__(
                    "size", True
                ),
                lambda value: value["toolchains"]["arm64"]["docker_save"].__setitem__(
                    "layer_sources_verified", 1
                ),
            ]
            for mutate in mutations:
                candidate = copy.deepcopy(document)
                mutate(candidate)
                candidate["content_sha256"] = archive_tool.lock_content_sha256(
                    candidate
                )
                with self.assertRaises(archive_tool.ToolchainArchiveError):
                    archive_tool.validate_lock_document(
                        candidate, repo_root=root, contracts=contracts
                    )
            invalid_content = copy.deepcopy(document)
            invalid_content["content_sha256"] = 7
            with self.assertRaises(archive_tool.ToolchainArchiveError):
                archive_tool.validate_lock_document(
                    invalid_content, repo_root=root, contracts=contracts
                )


@unittest.skipUnless(
    os.environ.get("CORE_TOOLCHAIN_ARCHIVE_REAL_TESTS") == "1",
    "set CORE_TOOLCHAIN_ARCHIVE_REAL_TESTS=1 for the large real-archive gate",
)
class RealToolchainArchiveTests(unittest.TestCase):
    def test_current_archives_reproduce_the_complete_tracked_lock(self) -> None:
        document = archive_tool.strict_json_file(archive_tool.DEFAULT_LOCK)
        archive_tool.validate_lock_document(document)
        for architecture, base_contract in archive_tool.TOOLCHAIN_CONTRACTS.items():
            with self.subTest(architecture=architecture):
                path = Path("/tmp") / base_contract["archive_filename"]
                result = archive_tool.inspect_archive(
                    path,
                    {**base_contract, "architecture": architecture},
                )
                self.assertEqual(document["toolchains"][architecture], result)

    def test_real_downloads_match_the_tracked_lock(self) -> None:
        paths = {
            architecture: Path("/tmp") / contract["archive_filename"]
            for architecture, contract in archive_tool.TOOLCHAIN_CONTRACTS.items()
        }
        report = archive_tool.verify_downloads(paths)
        self.assertEqual("valid", report["status"])
        for architecture, contract in archive_tool.TOOLCHAIN_CONTRACTS.items():
            self.assertEqual(
                contract["archive_sha256"],
                report["archives"][architecture]["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
