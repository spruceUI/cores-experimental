#!/usr/bin/env python3
"""Validate and locally lock the cached Cores-spruce toolchain archives.

This module intentionally does not load Docker images.  It validates the gzip,
tar, OCI, and Docker-save contracts in a single bounded stream and can stage the
original compressed bytes in the local content-addressed store.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
import tempfile
from typing import BinaryIO
import zlib


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "pins" / "toolchains" / "local-cache-v1.json"
DEFAULT_STORE = ROOT / ".local-e2e" / "store"
LOCK_SCHEMA_REF = "../../manifests/toolchain-lock.schema.json"
ARCHIVE_STORE_PREFIX = "toolchain-archives/sha256"
CHUNK_SIZE = 1024 * 1024
MAX_MEMBERS = 10_000
MAX_MEMBER_SIZE = 2 * 1024 * 1024 * 1024
MAX_TOTAL_MEMBER_SIZE = 2 * 1024 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 2 * 1024 * 1024 * 1024
MAX_JSON_SIZE = 4 * 1024 * 1024
MAX_CAPTURE_TOTAL = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
OCI_INDEX_MEDIA_TYPE = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"
OCI_CONFIG_MEDIA_TYPE = "application/vnd.oci.image.config.v1+json"
OCI_LAYER_MEDIA_TYPE = "application/vnd.oci.image.layer.v1.tar"
DOCKERFILE_LINKAGE = "unverified-local-cache"
DOCKERFILE_LINKAGE_REASON = (
    "The cached image predates this archive lock; matching its immutable image "
    "metadata does not prove that it was built from the current Dockerfile."
)

TOOLCHAIN_CONTRACTS = {
    "arm64": {
        "archive_filename": "cores-arm64.tar.gz",
        "archive_sha256": "8a3bdd7f36a10a092209cd8f308d2d2a85e316be7ede6d42562074243b25bc64",
        "archive_size": 502531978,
        "image_tag": "cores-arm64:latest",
        "image_id": "sha256:538411e2759cd5482068fd0c1f24d5a033138cd9f49db31f2c620929a8b046a9",
        "container_os": "linux",
        "container_architecture": "amd64",
        "target_host_cc": "aarch64-linux-gnu",
        "workdir": "/libretro-super",
        "dockerfile": "Dockerfile.arm64",
        "dockerfile_sha256": "1ddcbe99070a7ca3f72a61ea949186249ff5d9092f7946a7196d506bca7a1514",
    },
    "armhf": {
        "archive_filename": "cores-armhf.tar.gz",
        "archive_sha256": "f297cbf988aeb15c3de90c1bc900494aaf4214320aa5fcfa2cbbf10d2e32f16e",
        "archive_size": 835303648,
        "image_tag": "cores-armhf:latest",
        "image_id": "sha256:393a23661c4178edfc4e5ea0221e5de317a40f2f50a9fff1cb76e9e322189dd9",
        "container_os": "linux",
        "container_architecture": "amd64",
        "target_host_cc": "arm-a30-linux-gnueabihf",
        "workdir": "/libretro-super",
        "dockerfile": "Dockerfile.armhf",
        "dockerfile_sha256": "25ea28e7a00905fd94efe548fbec3abb762a2a949513762f7dfc86df254c44fb",
    },
    "rust": {
        "archive_filename": "cores-rust.tar.gz",
        "archive_sha256": "38ad84b2fe5dc0a54a94e9a14d5afd5b951a1b5a212692460c64cc6a849edade",
        "archive_size": 999801265,
        "image_tag": "cores-rust:latest",
        "image_id": "sha256:aa42a12ced6bd0d1c9dcb528f170c14fe80157f0650cab52f9a37e90ec2da5b6",
        "container_os": "linux",
        "container_architecture": "amd64",
        "target_host_cc": "cc",
        "workdir": "/build",
        "dockerfile": "Dockerfile.rust",
        "dockerfile_sha256": "1f07776357a22e92a08e1dfb05065a75ab6fb28d10f1969af8ac29fd5203c0bf",
    },
}


class ToolchainArchiveError(RuntimeError):
    """A malformed, unsafe, or inconsistent toolchain archive/lock."""


class _DuplicateJsonKey(ValueError):
    pass


class _HashingTeeReader:
    """Hash a sequential input and optionally copy the exact bytes to a sink."""

    def __init__(self, source: BinaryIO, sink: BinaryIO | None = None) -> None:
        self.source = source
        self.sink = sink
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        block = self.source.read(size)
        if block:
            self.digest.update(block)
            self.size += len(block)
            if self.sink is not None:
                self.sink.write(block)
        return block


class _CountingReader:
    def __init__(self, source: BinaryIO, limit: int) -> None:
        self.source = source
        self.limit = limit
        self.size = 0

    def read(self, size: int = -1) -> bytes:
        block = self.source.read(size)
        self.size += len(block)
        if self.size > self.limit:
            raise ToolchainArchiveError("gzip uncompressed size exceeds limit")
        return block


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate key: {key}")
        result[key] = value
    return result


def strict_json_bytes(value: bytes, label: str) -> object:
    if len(value) > MAX_JSON_SIZE:
        raise ToolchainArchiveError(f"{label} exceeds the JSON size limit")

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite number: {token}")

    try:
        return json.loads(
            value.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ToolchainArchiveError(f"invalid strict JSON in {label}: {exc}") from exc


def strict_json_file(path: Path) -> dict:
    _require_regular_input(path)
    try:
        with path.open("rb") as handle:
            value = strict_json_bytes(handle.read(MAX_JSON_SIZE + 1), str(path))
    except OSError as exc:
        raise ToolchainArchiveError(f"cannot read lock {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolchainArchiveError(f"lock must be a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(CHUNK_SIZE), b""):
                digest.update(block)
    except OSError as exc:
        raise ToolchainArchiveError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def lock_content_sha256(document: dict) -> str:
    value = {
        "schema_version": document.get("schema_version"),
        "lock_id": document.get("lock_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "toolchains": document.get("toolchains"),
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_regular_input(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ToolchainArchiveError(f"archive is unavailable: {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ToolchainArchiveError(f"archive must be a regular non-symlink file: {path}")


def _absolute_lexical_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _open_real_directory(path: Path, *, create: bool) -> int:
    """Open a directory path componentwise without following any symlink."""

    absolute = _absolute_lexical_path(path)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    parts = absolute.parts
    descriptor = os.open(parts[0], flags)
    try:
        for part in parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o755, dir_fd=descriptor)
                except FileExistsError:
                    # A concurrent creator is acceptable only if O_NOFOLLOW can
                    # open the resulting object as a real directory below.
                    pass
                os.fsync(descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError as exc:
        os.close(descriptor)
        raise ToolchainArchiveError(
            f"directory path must not traverse symlinks or non-directories: {path}: {exc}"
        ) from exc


def _ensure_real_directory(path: Path) -> None:
    descriptor = _open_real_directory(path, create=True)
    os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    directory_fd = _open_real_directory(path, create=False)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _discard_temporary(path: Path | None, directory: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
        if directory is not None:
            _fsync_directory(directory)
    except OSError as exc:
        raise ToolchainArchiveError(f"cannot durably discard staging file {path}: {exc}") from exc


def _canonical_member_name(member: tarfile.TarInfo) -> str:
    name = member.name
    if not name or "\\" in name or name.startswith("/") or "\x00" in name:
        raise ToolchainArchiveError(f"unsafe tar member name: {name!r}")
    path = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ToolchainArchiveError(f"non-canonical tar member name: {name!r}")
    canonical = path.as_posix()
    if canonical != name.rstrip("/"):
        raise ToolchainArchiveError(f"non-canonical tar member name: {name!r}")
    return canonical


def _descriptor(
    value: object,
    label: str,
    members: dict[str, dict],
    *,
    media_type: str,
) -> tuple[str, dict]:
    if not isinstance(value, dict):
        raise ToolchainArchiveError(f"{label} must be an object")
    if value.get("mediaType") != media_type:
        raise ToolchainArchiveError(f"{label} mediaType mismatch")
    raw_digest = value.get("digest", "")
    match = DIGEST_RE.fullmatch(raw_digest) if isinstance(raw_digest, str) else None
    if not match:
        raise ToolchainArchiveError(f"{label} digest is not exact sha256")
    digest = match.group(1)
    blob_path = f"blobs/sha256/{digest}"
    blob = members.get(blob_path)
    if blob is None:
        raise ToolchainArchiveError(f"{label} references a missing blob")
    size = value.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ToolchainArchiveError(f"{label} size is invalid")
    if size != blob["size"]:
        raise ToolchainArchiveError(f"{label} size does not match its blob")
    return digest, blob


def _required_object(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ToolchainArchiveError(f"{label} must be an object")
    return value


def _required_list(value: object, label: str) -> list:
    if not isinstance(value, list):
        raise ToolchainArchiveError(f"{label} must be an array")
    return value


def _exact_integer(value: object) -> bool:
    return type(value) is int


def _validate_tar_zero_padding(buffered: bytes, source: _CountingReader) -> None:
    """Consume and validate bytes after tarfile stops at its first zero block."""

    trailing_size = 0
    for block in (buffered,):
        trailing_size += len(block)
        if any(block):
            raise ToolchainArchiveError("non-zero payload follows the tar end marker")
    while True:
        block = source.read(CHUNK_SIZE)
        if not block:
            break
        trailing_size += len(block)
        if any(block):
            raise ToolchainArchiveError("non-zero payload follows the tar end marker")
    if trailing_size < tarfile.BLOCKSIZE:
        raise ToolchainArchiveError("tar archive is missing its second zero end block")
    if source.size % tarfile.BLOCKSIZE:
        raise ToolchainArchiveError("tar archive has non-canonical partial-block padding")


def _captured_json(members: dict[str, dict], path: str) -> object:
    member = members.get(path)
    if member is None or member.get("data") is None:
        raise ToolchainArchiveError(f"required JSON member is missing or too large: {path}")
    return strict_json_bytes(member["data"], path)


def _validate_graph(
    members: dict[str, dict],
    contract: dict,
    *,
    archive_filename: str,
    archive_sha256: str,
    archive_size: int,
    uncompressed_size: int,
    member_count: int,
) -> dict:
    expected_non_blob = {"index.json", "manifest.json", "oci-layout", "repositories"}
    regular_non_blob = {
        name
        for name, member in members.items()
        if member["kind"] == "file" and not name.startswith("blobs/sha256/")
    }
    if regular_non_blob != expected_non_blob:
        raise ToolchainArchiveError(
            "archive top-level files mismatch: "
            f"expected {sorted(expected_non_blob)}, got {sorted(regular_non_blob)}"
        )
    directory_names = {
        name for name, member in members.items() if member["kind"] == "directory"
    }
    if directory_names != {"blobs", "blobs/sha256"}:
        raise ToolchainArchiveError("archive directory layout is not canonical")

    layout = _required_object(_captured_json(members, "oci-layout"), "oci-layout")
    if layout != {"imageLayoutVersion": "1.0.0"}:
        raise ToolchainArchiveError("oci-layout is not the exact OCI 1.0 layout marker")

    index = _required_object(_captured_json(members, "index.json"), "index.json")
    if set(index) != {"schemaVersion", "mediaType", "manifests"}:
        raise ToolchainArchiveError("index.json has an unexpected shape")
    if (
        not _exact_integer(index.get("schemaVersion"))
        or index.get("schemaVersion") != 2
        or index.get("mediaType") != OCI_INDEX_MEDIA_TYPE
    ):
        raise ToolchainArchiveError("index.json is not an OCI image index v1")
    index_manifests = _required_list(index.get("manifests"), "index.json manifests")
    if len(index_manifests) != 1:
        raise ToolchainArchiveError("index.json must select exactly one image manifest")
    index_descriptor = _required_object(index_manifests[0], "index manifest descriptor")
    if set(index_descriptor) != {"mediaType", "digest", "size", "annotations"}:
        raise ToolchainArchiveError("index manifest descriptor has an unexpected shape")
    manifest_digest, _ = _descriptor(
        index_descriptor,
        "index manifest descriptor",
        members,
        media_type=OCI_MANIFEST_MEDIA_TYPE,
    )
    annotations = _required_object(
        index_descriptor.get("annotations"), "index manifest annotations"
    )
    expected_tag = contract["image_tag"]
    repository, tag = expected_tag.rsplit(":", 1)
    if annotations != {
        "io.containerd.image.name": f"docker.io/library/{expected_tag}",
        "org.opencontainers.image.ref.name": tag,
    }:
        raise ToolchainArchiveError("index annotations do not bind the expected image tag")

    oci_manifest = _required_object(
        _captured_json(members, f"blobs/sha256/{manifest_digest}"),
        "OCI image manifest",
    )
    if set(oci_manifest) != {"schemaVersion", "mediaType", "config", "layers"}:
        raise ToolchainArchiveError("OCI image manifest has an unexpected shape")
    if (
        not _exact_integer(oci_manifest.get("schemaVersion"))
        or oci_manifest.get("schemaVersion") != 2
        or oci_manifest.get("mediaType") != OCI_MANIFEST_MEDIA_TYPE
    ):
        raise ToolchainArchiveError("OCI image manifest version/mediaType mismatch")
    config_descriptor = _required_object(
        oci_manifest.get("config"), "OCI config descriptor"
    )
    if set(config_descriptor) != {"mediaType", "digest", "size"}:
        raise ToolchainArchiveError("OCI config descriptor has an unexpected shape")
    config_digest, _ = _descriptor(
        config_descriptor,
        "OCI config descriptor",
        members,
        media_type=OCI_CONFIG_MEDIA_TYPE,
    )
    expected_image_id = contract["image_id"]
    if f"sha256:{config_digest}" != expected_image_id:
        raise ToolchainArchiveError("OCI config digest does not match the exact image ID")

    layer_values = _required_list(oci_manifest.get("layers"), "OCI layers")
    if not layer_values:
        raise ToolchainArchiveError("OCI image must contain at least one layer")
    layer_descriptors = []
    layer_digests = []
    for index_value, layer_value in enumerate(layer_values):
        layer = _required_object(layer_value, f"OCI layer descriptor {index_value}")
        digest, _ = _descriptor(
            layer,
            f"OCI layer descriptor {index_value}",
            members,
            media_type=OCI_LAYER_MEDIA_TYPE,
        )
        if set(layer) != {"mediaType", "digest", "size"}:
            raise ToolchainArchiveError("OCI layer descriptor has an unexpected shape")
        layer_digests.append(digest)
        layer_descriptors.append(
            {"media_type": OCI_LAYER_MEDIA_TYPE, "sha256": digest, "size": layer["size"]}
        )
    if len(layer_digests) != len(set(layer_digests)):
        raise ToolchainArchiveError("OCI layer descriptors contain a duplicate digest")

    config = _required_object(
        _captured_json(members, f"blobs/sha256/{config_digest}"), "OCI config"
    )
    if config.get("os") != contract["container_os"]:
        raise ToolchainArchiveError("OCI config operating system mismatch")
    if config.get("architecture") != contract["container_architecture"]:
        raise ToolchainArchiveError("OCI config container architecture mismatch")
    config_runtime = _required_object(config.get("config"), "OCI runtime config")
    if config_runtime.get("WorkingDir") != contract["workdir"]:
        raise ToolchainArchiveError("OCI config working directory mismatch")
    env = _required_list(config_runtime.get("Env"), "OCI config environment")
    host_cc_values = [item for item in env if isinstance(item, str) and item.startswith("HOST_CC=")]
    if host_cc_values != [f"HOST_CC={contract['target_host_cc']}"]:
        raise ToolchainArchiveError("OCI config HOST_CC mismatch or ambiguity")
    rootfs = _required_object(config.get("rootfs"), "OCI rootfs")
    if rootfs.get("type") != "layers":
        raise ToolchainArchiveError("OCI rootfs type must be layers")
    expected_diff_ids = [f"sha256:{digest}" for digest in layer_digests]
    if rootfs.get("diff_ids") != expected_diff_ids:
        raise ToolchainArchiveError("OCI rootfs diff_ids do not match layer order")

    docker_manifest = _required_list(
        _captured_json(members, "manifest.json"), "Docker manifest.json"
    )
    if len(docker_manifest) != 1:
        raise ToolchainArchiveError("Docker manifest must select exactly one image")
    docker_image = _required_object(docker_manifest[0], "Docker manifest image")
    if set(docker_image) != {"Config", "RepoTags", "Layers", "LayerSources"}:
        raise ToolchainArchiveError("Docker manifest image has an unexpected shape")
    if docker_image.get("Config") != f"blobs/sha256/{config_digest}":
        raise ToolchainArchiveError("Docker manifest Config does not match OCI config")
    if docker_image.get("RepoTags") != [expected_tag]:
        raise ToolchainArchiveError("Docker manifest RepoTags mismatch")
    expected_layers = [f"blobs/sha256/{digest}" for digest in layer_digests]
    if docker_image.get("Layers") != expected_layers:
        raise ToolchainArchiveError("Docker manifest Layers do not match OCI layer order")
    layer_sources = _required_object(
        docker_image.get("LayerSources"), "Docker manifest LayerSources"
    )
    if set(layer_sources) != {f"sha256:{digest}" for digest in layer_digests}:
        raise ToolchainArchiveError("Docker LayerSources do not cover the OCI layers exactly")
    for descriptor, digest in zip(layer_descriptors, layer_digests):
        source = _required_object(
            layer_sources[f"sha256:{digest}"], "Docker LayerSources descriptor"
        )
        if set(source) != {"mediaType", "size", "digest"} or not _exact_integer(
            source.get("size")
        ):
            raise ToolchainArchiveError("Docker LayerSources descriptor shape mismatch")
        if source != {
            "mediaType": descriptor["media_type"],
            "size": descriptor["size"],
            "digest": f"sha256:{digest}",
        }:
            raise ToolchainArchiveError("Docker LayerSources descriptor mismatch")

    repositories = _required_object(
        _captured_json(members, "repositories"), "Docker repositories"
    )
    if repositories != {repository: {tag: layer_digests[-1]}}:
        raise ToolchainArchiveError("Docker repositories does not bind the expected top layer")

    referenced_blobs = {manifest_digest, config_digest, *layer_digests}
    all_blobs = {
        name.removeprefix("blobs/sha256/")
        for name, member in members.items()
        if member["kind"] == "file" and name.startswith("blobs/sha256/")
    }
    extras = []
    for digest in sorted(all_blobs - referenced_blobs):
        blob = members[f"blobs/sha256/{digest}"]
        data = blob.get("data")
        if data is None:
            raise ToolchainArchiveError("legacy extra blob exceeds the metadata size limit")
        value = strict_json_bytes(data, f"legacy extra blob {digest}")
        if not isinstance(value, dict):
            raise ToolchainArchiveError("legacy extra blob must be a strict JSON object")
        extras.append(
            {
                "sha256": digest,
                "size": blob["size"],
                "classification": "legacy-docker-save-metadata",
            }
        )

    archive_store_path = (
        f"{ARCHIVE_STORE_PREFIX}/{archive_sha256[:2]}/{archive_sha256}"
    )
    return {
        "architecture": contract["architecture"],
        "archive": {
            "filename": archive_filename,
            "format": "gzip-compressed-hybrid-oci-docker-save-tar",
            "sha256": archive_sha256,
            "size": archive_size,
            "uncompressed_size": uncompressed_size,
            "member_count": member_count,
            "store_path": archive_store_path,
        },
        "image": {
            "tag": expected_tag,
            "id": expected_image_id,
            "container_platform": {
                "os": contract["container_os"],
                "architecture": contract["container_architecture"],
            },
            "target_host_cc": contract["target_host_cc"],
            "workdir": contract["workdir"],
        },
        "oci": {
            "manifest": {
                "media_type": OCI_MANIFEST_MEDIA_TYPE,
                "sha256": manifest_digest,
                "size": members[f"blobs/sha256/{manifest_digest}"]["size"],
            },
            "config": {
                "media_type": OCI_CONFIG_MEDIA_TYPE,
                "sha256": config_digest,
                "size": members[f"blobs/sha256/{config_digest}"]["size"],
            },
            "layers": layer_descriptors,
            "rootfs_diff_ids": expected_diff_ids,
        },
        "docker_save": {
            "repo_tags": [expected_tag],
            "config": f"blobs/sha256/{config_digest}",
            "layers": expected_layers,
            "layer_sources_verified": True,
        },
        "legacy_extra_blobs": extras,
        "dockerfile": {
            "path": contract["dockerfile"],
            "sha256": contract["dockerfile_sha256"],
            "linkage": DOCKERFILE_LINKAGE,
            "reason": DOCKERFILE_LINKAGE_REASON,
        },
    }


def _verify_existing_store(path: Path, sha256: str, size: int) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ToolchainArchiveError(f"cannot inspect staged archive {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ToolchainArchiveError(f"staged archive collision is not a regular file: {path}")
    if stat.S_IMODE(info.st_mode) != 0o644:
        raise ToolchainArchiveError(f"staged archive collision has an unsafe mode: {path}")
    if info.st_size != size or sha256_file(path) != sha256:
        raise ToolchainArchiveError(f"staged archive collision does not match its digest: {path}")


def _finalize_stage(
    temporary: Path, store_root: Path, archive_sha256: str, archive_size: int
) -> Path:
    base = store_root / ARCHIVE_STORE_PREFIX
    destination_parent = base / archive_sha256[:2]
    _ensure_real_directory(destination_parent)
    destination = destination_parent / archive_sha256
    if destination.exists() or destination.is_symlink():
        _verify_existing_store(destination, archive_sha256, archive_size)
        _fsync_directory(destination_parent)
        temporary.unlink()
        _fsync_directory(base)
        return destination
    try:
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        _verify_existing_store(destination, archive_sha256, archive_size)
    except OSError as exc:
        raise ToolchainArchiveError(f"cannot atomically stage archive: {exc}") from exc
    _fsync_directory(destination_parent)
    temporary.unlink()
    _fsync_directory(base)
    return destination


def inspect_archive(
    archive_path: Path,
    contract: dict,
    *,
    repo_root: Path = ROOT,
    stage_store: Path | None = None,
    logical_filename: str | None = None,
) -> dict:
    """Fully stream and validate one archive, optionally staging compressed bytes."""

    archive_path = Path(archive_path)
    _require_regular_input(archive_path)
    filename = logical_filename or archive_path.name
    if filename != contract["archive_filename"]:
        raise ToolchainArchiveError(
            f"archive filename mismatch: expected {contract['archive_filename']}, got {filename}"
        )
    expected_size = contract.get("archive_size")
    input_size = archive_path.stat().st_size
    if expected_size is not None and input_size != expected_size:
        raise ToolchainArchiveError("archive compressed size does not match the pinned input")

    dockerfile = repo_root / contract["dockerfile"]
    _require_regular_input(dockerfile)
    dockerfile_sha256 = sha256_file(dockerfile)
    if dockerfile_sha256 != contract["dockerfile_sha256"]:
        raise ToolchainArchiveError(
            f"current {contract['dockerfile']} digest does not match its contract"
        )

    temporary_path: Path | None = None
    staging_base: Path | None = None
    staging_handle: BinaryIO | None = None
    if stage_store is not None:
        staging_base = Path(stage_store) / ARCHIVE_STORE_PREFIX
        _ensure_real_directory(staging_base)
        staging_handle = tempfile.NamedTemporaryFile(
            "w+b", dir=staging_base, prefix=".incoming-", delete=False
        )
        temporary_path = Path(staging_handle.name)

    members: dict[str, dict] = {}
    member_count = 0
    declared_total = 0
    captured_total = 0
    raw_reader: _HashingTeeReader | None = None
    uncompressed: _CountingReader | None = None
    try:
        with archive_path.open("rb") as raw_handle:
            raw_reader = _HashingTeeReader(raw_handle, staging_handle)
            with gzip.GzipFile(fileobj=raw_reader, mode="rb") as gzip_handle:
                uncompressed = _CountingReader(gzip_handle, MAX_UNCOMPRESSED_SIZE)
                post_eoa_buffer = b""
                with tarfile.open(fileobj=uncompressed, mode="r|") as archive:
                    for member in archive:
                        member_count += 1
                        if member_count > MAX_MEMBERS:
                            raise ToolchainArchiveError("archive member count exceeds limit")
                        name = _canonical_member_name(member)
                        if name in members:
                            raise ToolchainArchiveError(f"duplicate tar member: {name}")
                        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                            raise ToolchainArchiveError(f"unsafe special tar member: {name}")
                        if member.sparse is not None:
                            raise ToolchainArchiveError(f"sparse tar member is not allowed: {name}")
                        if member.isdir():
                            if member.size != 0:
                                raise ToolchainArchiveError(
                                    f"directory tar member has non-zero size: {name}"
                                )
                            members[name] = {"kind": "directory", "size": 0}
                            continue
                        if not member.isreg():
                            raise ToolchainArchiveError(f"unsupported tar member type: {name}")
                        if member.size < 0 or member.size > MAX_MEMBER_SIZE:
                            raise ToolchainArchiveError(f"tar member exceeds size limit: {name}")
                        declared_total += member.size
                        if declared_total > MAX_TOTAL_MEMBER_SIZE:
                            raise ToolchainArchiveError("archive declared content exceeds total limit")
                        extracted = archive.extractfile(member)
                        if extracted is None:
                            raise ToolchainArchiveError(f"cannot stream tar member: {name}")
                        digest = hashlib.sha256()
                        capture = None
                        if member.size <= MAX_JSON_SIZE:
                            if captured_total + member.size > MAX_CAPTURE_TOTAL:
                                raise ToolchainArchiveError(
                                    "archive metadata capture exceeds aggregate limit"
                                )
                            captured_total += member.size
                            capture = bytearray()
                        remaining = member.size
                        while remaining:
                            block = extracted.read(min(CHUNK_SIZE, remaining))
                            if not block:
                                raise ToolchainArchiveError(f"truncated tar member: {name}")
                            remaining -= len(block)
                            digest.update(block)
                            if capture is not None:
                                capture.extend(block)
                        actual_digest = digest.hexdigest()
                        if name.startswith("blobs/sha256/"):
                            blob_name = name.removeprefix("blobs/sha256/")
                            if not SHA256_RE.fullmatch(blob_name) or blob_name != actual_digest:
                                raise ToolchainArchiveError(
                                    f"blob filename digest mismatch: {name}"
                                )
                        members[name] = {
                            "kind": "file",
                            "size": member.size,
                            "sha256": actual_digest,
                            "data": bytes(capture) if capture is not None else None,
                        }
                    post_eoa_buffer = archive.fileobj.buf
                _validate_tar_zero_padding(post_eoa_buffer, uncompressed)
        if raw_reader is None or uncompressed is None:
            raise ToolchainArchiveError("archive stream was not initialized")
    except ToolchainArchiveError:
        _discard_temporary(temporary_path, staging_base)
        temporary_path = None
        raise
    except (OSError, EOFError, gzip.BadGzipFile, tarfile.TarError, zlib.error) as exc:
        _discard_temporary(temporary_path, staging_base)
        temporary_path = None
        raise ToolchainArchiveError(f"invalid gzip/tar stream in {archive_path}: {exc}") from exc
    finally:
        if staging_handle is not None:
            try:
                staging_handle.flush()
                os.fchmod(staging_handle.fileno(), 0o644)
                os.fsync(staging_handle.fileno())
            except OSError as exc:
                staging_handle.close()
                _discard_temporary(temporary_path, staging_base)
                temporary_path = None
                raise ToolchainArchiveError(
                    f"cannot durably write archive staging file: {exc}"
                ) from exc
            finally:
                if not staging_handle.closed:
                    staging_handle.close()

    try:
        archive_sha256 = raw_reader.digest.hexdigest()
        archive_size = raw_reader.size
        actual_stat_size = archive_path.stat().st_size
        if archive_size != actual_stat_size:
            raise ToolchainArchiveError("gzip validator did not consume the exact archive bytes")
        if expected_size is not None and archive_size != expected_size:
            raise ToolchainArchiveError("archive compressed size does not match the pinned input")
        expected_sha256 = contract.get("archive_sha256")
        if expected_sha256 is not None and archive_sha256 != expected_sha256:
            raise ToolchainArchiveError("archive SHA256 does not match the pinned input")

        result = _validate_graph(
            members,
            contract,
            archive_filename=filename,
            archive_sha256=archive_sha256,
            archive_size=archive_size,
            uncompressed_size=uncompressed.size,
            member_count=member_count,
        )
        if temporary_path is not None and stage_store is not None:
            staged = _finalize_stage(
                temporary_path, Path(stage_store), archive_sha256, archive_size
            )
            expected_staged = Path(stage_store) / result["archive"]["store_path"]
            if staged != expected_staged:
                raise ToolchainArchiveError("staged archive path mismatch")
            temporary_path = None
        return result
    except Exception:
        _discard_temporary(temporary_path, staging_base)
        temporary_path = None
        raise


def _contract_with_architecture(architecture: str, contract: dict) -> dict:
    return {**contract, "architecture": architecture}


def build_lock_document(lock_id: str, toolchains: dict[str, dict]) -> dict:
    document = {
        "$schema": LOCK_SCHEMA_REF,
        "schema_version": 1,
        "lock_id": lock_id,
        "local_only": True,
        "publication": "disabled",
        "toolchains": toolchains,
    }
    document["content_sha256"] = lock_content_sha256(document)
    return document


def _atomic_create_json(path: Path, document: dict) -> None:
    if path.exists() or path.is_symlink():
        raise ToolchainArchiveError(f"refusing to replace existing toolchain lock: {path}")
    _ensure_real_directory(path.parent)
    rendered = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w+b", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
        os.link(temporary, path, follow_symlinks=False)
    except FileExistsError as exc:
        raise ToolchainArchiveError(
            f"refusing to replace existing toolchain lock: {path}"
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _validate_lock_entry(entry: object, architecture: str, contract: dict, repo_root: Path) -> None:
    if not isinstance(entry, dict):
        raise ToolchainArchiveError(f"toolchains.{architecture} must be an object")
    expected_keys = {
        "architecture",
        "archive",
        "image",
        "oci",
        "docker_save",
        "legacy_extra_blobs",
        "dockerfile",
    }
    if set(entry) != expected_keys:
        raise ToolchainArchiveError(f"toolchains.{architecture} has an unexpected shape")
    if entry.get("architecture") != architecture:
        raise ToolchainArchiveError(f"toolchains.{architecture} architecture mismatch")
    archive = _required_object(entry.get("archive"), f"toolchains.{architecture}.archive")
    digest = archive.get("sha256", "")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise ToolchainArchiveError(f"toolchains.{architecture} archive digest is invalid")
    for field in ("size", "uncompressed_size", "member_count"):
        value = archive.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ToolchainArchiveError(
                f"toolchains.{architecture} archive {field} is invalid"
            )
    if archive["uncompressed_size"] > MAX_UNCOMPRESSED_SIZE:
        raise ToolchainArchiveError(
            f"toolchains.{architecture} archive uncompressed_size exceeds limit"
        )
    if archive["member_count"] > MAX_MEMBERS:
        raise ToolchainArchiveError(
            f"toolchains.{architecture} archive member_count exceeds limit"
        )
    expected_store_path = f"{ARCHIVE_STORE_PREFIX}/{digest[:2]}/{digest}"
    if archive != {
        "filename": contract["archive_filename"],
        "format": "gzip-compressed-hybrid-oci-docker-save-tar",
        "sha256": digest,
        "size": archive["size"],
        "uncompressed_size": archive["uncompressed_size"],
        "member_count": archive["member_count"],
        "store_path": expected_store_path,
    }:
        raise ToolchainArchiveError(f"toolchains.{architecture} archive metadata mismatch")
    if contract.get("archive_sha256") and digest != contract["archive_sha256"]:
        raise ToolchainArchiveError(f"toolchains.{architecture} archive digest is not pinned")
    if contract.get("archive_size") and archive["size"] != contract["archive_size"]:
        raise ToolchainArchiveError(f"toolchains.{architecture} archive size is not pinned")

    image = _required_object(entry.get("image"), f"toolchains.{architecture}.image")
    if image != {
        "tag": contract["image_tag"],
        "id": contract["image_id"],
        "container_platform": {
            "os": contract["container_os"],
            "architecture": contract["container_architecture"],
        },
        "target_host_cc": contract["target_host_cc"],
        "workdir": contract["workdir"],
    }:
        raise ToolchainArchiveError(f"toolchains.{architecture} image contract mismatch")
    dockerfile = _required_object(
        entry.get("dockerfile"), f"toolchains.{architecture}.dockerfile"
    )
    expected_dockerfile = {
        "path": contract["dockerfile"],
        "sha256": contract["dockerfile_sha256"],
        "linkage": DOCKERFILE_LINKAGE,
        "reason": DOCKERFILE_LINKAGE_REASON,
    }
    if dockerfile != expected_dockerfile:
        raise ToolchainArchiveError(f"toolchains.{architecture} Dockerfile contract mismatch")
    path = repo_root / dockerfile["path"]
    _require_regular_input(path)
    if sha256_file(path) != dockerfile["sha256"]:
        raise ToolchainArchiveError(f"toolchains.{architecture} current Dockerfile drifted")

    oci = _required_object(entry.get("oci"), f"toolchains.{architecture}.oci")
    if set(oci) != {"manifest", "config", "layers", "rootfs_diff_ids"}:
        raise ToolchainArchiveError(f"toolchains.{architecture} OCI metadata shape mismatch")
    manifest = _required_object(oci.get("manifest"), "lock OCI manifest")
    config = _required_object(oci.get("config"), "lock OCI config")
    for descriptor, media_type in (
        (manifest, OCI_MANIFEST_MEDIA_TYPE),
        (config, OCI_CONFIG_MEDIA_TYPE),
    ):
        if set(descriptor) != {"media_type", "sha256", "size"}:
            raise ToolchainArchiveError("lock OCI descriptor shape mismatch")
        descriptor_sha = descriptor.get("sha256", "")
        if (
            descriptor["media_type"] != media_type
            or not isinstance(descriptor_sha, str)
            or not SHA256_RE.fullmatch(descriptor_sha)
        ):
            raise ToolchainArchiveError("lock OCI descriptor identity mismatch")
        if not _exact_integer(descriptor.get("size")) or descriptor["size"] <= 0:
            raise ToolchainArchiveError("lock OCI descriptor size mismatch")
    if f"sha256:{config['sha256']}" != contract["image_id"]:
        raise ToolchainArchiveError("lock OCI config does not equal image ID")
    layers = _required_list(oci.get("layers"), "lock OCI layers")
    if not layers:
        raise ToolchainArchiveError("lock OCI layers are empty")
    layer_digests = []
    layer_size_total = 0
    for layer in layers:
        layer = _required_object(layer, "lock OCI layer")
        if set(layer) != {"media_type", "sha256", "size"}:
            raise ToolchainArchiveError("lock OCI layer descriptor shape mismatch")
        layer_sha = layer.get("sha256", "")
        if (
            layer.get("media_type") != OCI_LAYER_MEDIA_TYPE
            or not isinstance(layer_sha, str)
            or not SHA256_RE.fullmatch(layer_sha)
        ):
            raise ToolchainArchiveError("lock OCI layer descriptor mismatch")
        if not _exact_integer(layer.get("size")) or layer["size"] <= 0:
            raise ToolchainArchiveError("lock OCI layer size mismatch")
        layer_digests.append(layer["sha256"])
        layer_size_total += layer["size"]
    if layer_size_total > MAX_TOTAL_MEMBER_SIZE:
        raise ToolchainArchiveError("lock OCI layer sizes exceed the archive limit")
    if len(layer_digests) != len(set(layer_digests)):
        raise ToolchainArchiveError("lock OCI layer digests must be unique")
    if oci.get("rootfs_diff_ids") != [f"sha256:{item}" for item in layer_digests]:
        raise ToolchainArchiveError("lock rootfs diff_ids do not match layer order")
    docker = _required_object(
        entry.get("docker_save"), f"toolchains.{architecture}.docker_save"
    )
    if docker.get("layer_sources_verified") is not True:
        raise ToolchainArchiveError(
            f"toolchains.{architecture} Docker LayerSources verification flag is invalid"
        )
    if docker != {
        "repo_tags": [contract["image_tag"]],
        "config": f"blobs/sha256/{config['sha256']}",
        "layers": [f"blobs/sha256/{item}" for item in layer_digests],
        "layer_sources_verified": True,
    }:
        raise ToolchainArchiveError(f"toolchains.{architecture} Docker-save contract mismatch")
    extras = _required_list(
        entry.get("legacy_extra_blobs"),
        f"toolchains.{architecture}.legacy_extra_blobs",
    )
    extra_digests = []
    for extra in extras:
        extra = _required_object(extra, "legacy extra blob")
        if set(extra) != {"sha256", "size", "classification"}:
            raise ToolchainArchiveError("legacy extra blob shape mismatch")
        extra_sha = extra.get("sha256", "")
        if (
            not isinstance(extra_sha, str)
            or not SHA256_RE.fullmatch(extra_sha)
            or not _exact_integer(extra.get("size"))
            or extra["size"] <= 0
            or extra.get("classification") != "legacy-docker-save-metadata"
        ):
            raise ToolchainArchiveError("legacy extra blob metadata mismatch")
        extra_digests.append(extra["sha256"])
    if extra_digests != sorted(set(extra_digests)):
        raise ToolchainArchiveError("legacy extra blobs must be unique and sorted")
    graph_digests = {manifest["sha256"], config["sha256"], *layer_digests}
    if graph_digests.intersection(extra_digests):
        raise ToolchainArchiveError("legacy extra blobs overlap the OCI descriptor graph")


def validate_lock_document(
    document: dict,
    *,
    repo_root: Path = ROOT,
    contracts: dict[str, dict] = TOOLCHAIN_CONTRACTS,
) -> None:
    expected_keys = {
        "$schema",
        "schema_version",
        "lock_id",
        "local_only",
        "publication",
        "toolchains",
        "content_sha256",
    }
    if set(document) != expected_keys:
        raise ToolchainArchiveError("toolchain lock has an unexpected top-level shape")
    if (
        document.get("$schema") != LOCK_SCHEMA_REF
        or type(document.get("schema_version")) is not int
        or document.get("schema_version") != 1
    ):
        raise ToolchainArchiveError("toolchain lock schema/version mismatch")
    if document.get("lock_id") != "local-cache-v1":
        raise ToolchainArchiveError("toolchain lock ID must be local-cache-v1")
    if document.get("local_only") is not True or document.get("publication") != "disabled":
        raise ToolchainArchiveError("toolchain lock must remain local-only and unpublished")
    toolchains = _required_object(document.get("toolchains"), "toolchains")
    if set(toolchains) != set(contracts):
        raise ToolchainArchiveError("toolchain lock architecture set mismatch")
    for architecture, base_contract in contracts.items():
        contract = _contract_with_architecture(architecture, base_contract)
        _validate_lock_entry(toolchains[architecture], architecture, contract, repo_root)
    content_sha256 = document.get("content_sha256")
    if (
        not isinstance(content_sha256, str)
        or not SHA256_RE.fullmatch(content_sha256)
        or content_sha256 != lock_content_sha256(document)
    ):
        raise ToolchainArchiveError("toolchain lock content SHA256 mismatch")


def import_lock(
    archive_paths: dict[str, Path],
    *,
    output: Path = DEFAULT_LOCK,
    store_root: Path = DEFAULT_STORE,
    repo_root: Path = ROOT,
    contracts: dict[str, dict] = TOOLCHAIN_CONTRACTS,
) -> dict:
    if set(archive_paths) != set(contracts):
        raise ToolchainArchiveError("one archive is required for every locked architecture")
    if output.exists() or output.is_symlink():
        raise ToolchainArchiveError(f"refusing to replace existing toolchain lock: {output}")
    # Reject an unsafe output ancestry before staging any archive bytes.
    _ensure_real_directory(output.parent)
    toolchains = {}
    for architecture in sorted(contracts):
        contract = _contract_with_architecture(architecture, contracts[architecture])
        toolchains[architecture] = inspect_archive(
            archive_paths[architecture],
            contract,
            repo_root=repo_root,
            stage_store=store_root,
        )
    document = build_lock_document("local-cache-v1", toolchains)
    validate_lock_document(document, repo_root=repo_root, contracts=contracts)
    _atomic_create_json(output, document)
    return document


def validate_lock(
    lock_path: Path = DEFAULT_LOCK,
    *,
    verify_store: bool = False,
    store_root: Path = DEFAULT_STORE,
    repo_root: Path = ROOT,
    contracts: dict[str, dict] = TOOLCHAIN_CONTRACTS,
) -> dict:
    document = strict_json_file(lock_path)
    validate_lock_document(document, repo_root=repo_root, contracts=contracts)
    if verify_store:
        for architecture, entry in document["toolchains"].items():
            archive = entry["archive"]
            stored = Path(store_root) / archive["store_path"]
            contract = _contract_with_architecture(architecture, contracts[architecture])
            actual = inspect_archive(
                stored,
                contract,
                repo_root=repo_root,
                logical_filename=archive["filename"],
            )
            if actual != entry:
                raise ToolchainArchiveError(
                    f"staged {architecture} archive does not reproduce its lock metadata"
                )
    return {
        "status": "valid",
        "lock_id": document["lock_id"],
        "content_sha256": document["content_sha256"],
        "architectures": sorted(document["toolchains"]),
        "store": "verified" if verify_store else "not-requested",
    }


def _verify_download_identity(path: Path, expected: dict, architecture: str) -> dict:
    if path.name != expected["filename"]:
        raise ToolchainArchiveError(
            f"{architecture} archive filename mismatch: "
            f"expected {expected['filename']}, got {path.name}"
        )
    parent_fd = _open_real_directory(path.parent, create=False)
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        candidate = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(candidate.st_mode):
            raise ToolchainArchiveError(
                f"{architecture} archive must be a regular non-symlink file"
            )
        descriptor = os.open(path.name, flags, dir_fd=parent_fd)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_dev != candidate.st_dev
            or info.st_ino != candidate.st_ino
        ):
            raise ToolchainArchiveError(
                f"{architecture} archive changed during verification setup"
            )
        if info.st_size != expected["size"]:
            raise ToolchainArchiveError(
                f"{architecture} archive size mismatch: "
                f"expected {expected['size']}, got {info.st_size}"
            )
        digest = hashlib.sha256()
        streamed_size = 0
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            descriptor = None
            for block in iter(lambda: handle.read(CHUNK_SIZE), b""):
                streamed_size += len(block)
                digest.update(block)
        actual_sha256 = digest.hexdigest()
        if streamed_size != expected["size"] or actual_sha256 != expected["sha256"]:
            raise ToolchainArchiveError(f"{architecture} archive SHA256 mismatch")
        return {
            "filename": expected["filename"],
            "sha256": actual_sha256,
            "size": streamed_size,
        }
    except ToolchainArchiveError:
        raise
    except OSError as exc:
        raise ToolchainArchiveError(
            f"cannot verify {architecture} archive {path}: {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def verify_downloads(
    archive_paths: dict[str, Path],
    *,
    lock_path: Path = DEFAULT_LOCK,
    repo_root: Path = ROOT,
    contracts: dict[str, dict] = TOOLCHAIN_CONTRACTS,
) -> dict:
    """Verify exact downloaded archive bytes without staging or loading them."""

    document = strict_json_file(lock_path)
    validate_lock_document(document, repo_root=repo_root, contracts=contracts)
    # The two C cross archives are always required; the Rust archive is
    # verified when supplied. The 97 migrated C-core workflows predate the
    # rust lock entry and their bytes are part of every promoted recipe
    # identity, so they must stay valid while downloading only what their
    # core consumes.
    provided = {
        architecture: path
        for architecture, path in archive_paths.items()
        if path is not None
    }
    if not set(provided) <= set(document["toolchains"]) or not {
        "arm64",
        "armhf",
    } <= set(provided):
        raise ToolchainArchiveError(
            "downloaded archives must cover arm64 and armhf and only locked architectures"
        )
    archives = {}
    for architecture in sorted(provided):
        archives[architecture] = _verify_download_identity(
            Path(provided[architecture]),
            document["toolchains"][architecture]["archive"],
            architecture,
        )
    return {
        "status": "valid",
        "lock_id": document["lock_id"],
        "content_sha256": document["content_sha256"],
        "archives": archives,
    }


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _download_path(value: str) -> Path:
    return _absolute_lexical_path(Path(value).expanduser())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    importer = subparsers.add_parser(
        "import-lock", help="stream-validate, stage, and create the immutable lock"
    )
    importer.add_argument("--arm64", type=_path, required=True)
    importer.add_argument("--armhf", type=_path, required=True)
    importer.add_argument("--rust", type=_path, required=True)
    importer.add_argument("--output", type=_path, default=DEFAULT_LOCK)
    importer.add_argument("--store-root", type=_path, default=DEFAULT_STORE)
    validator = subparsers.add_parser(
        "validate-lock", help="validate lock metadata and optionally stream its CAS bytes"
    )
    validator.add_argument("--lock", type=_path, default=DEFAULT_LOCK)
    validator.add_argument("--store-root", type=_path, default=DEFAULT_STORE)
    validator.add_argument("--verify-store", action="store_true")
    downloads = subparsers.add_parser(
        "verify-downloads",
        help="stream-check downloaded archive size and SHA256 against the lock",
    )
    downloads.add_argument("--arm64", type=_download_path, required=True)
    downloads.add_argument("--armhf", type=_download_path, required=True)
    downloads.add_argument("--rust", type=_download_path)
    downloads.add_argument("--lock", type=_path, default=DEFAULT_LOCK)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "import-lock":
            document = import_lock(
                {"arm64": args.arm64, "armhf": args.armhf, "rust": args.rust},
                output=args.output,
                store_root=args.store_root,
            )
            report = {
                "status": "created",
                "lock_id": document["lock_id"],
                "content_sha256": document["content_sha256"],
                "architectures": sorted(document["toolchains"]),
            }
        elif args.command == "validate-lock":
            report = validate_lock(
                args.lock,
                verify_store=args.verify_store,
                store_root=args.store_root,
            )
        else:
            report = verify_downloads(
                {"arm64": args.arm64, "armhf": args.armhf, "rust": args.rust},
                lock_path=args.lock,
            )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except ToolchainArchiveError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
