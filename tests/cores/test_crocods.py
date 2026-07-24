"""Pinned CrocoDS build-evidence and individual-lifecycle tests."""

from __future__ import annotations

from collections import Counter
import json
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import crocods

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "crocods"
OTHER_CORE_ID = "cap32"
PIN_NAME = "crocods-87bbb3d9007a-5a44afda913e.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/crocods/87bbb3d9007ac537864278c6c3149ae3291873f8.json"
)
SOURCE_COMMIT = "87bbb3d9007ac537864278c6c3149ae3291873f8"
SOURCE_TREE = "5a76585f521954c8e8ebef9b489a4d6c7a8b73db"
SOURCE_URL = "https://github.com/libretro/libretro-crocods.git"
SOURCE_LOCK_ID = "crocods-87bbb3d9007a"
SOURCE_LOCK_FILE_SHA256 = (
    "8d9b5b70fde49c6240d7d2420cf7b166eeb23bd791e7b60a2b0afa6fb4f5fc53"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "153fa581737cacd3879922bacdfbbd2114651af6d8b900daef8c571e267e5268"
)
PIN_FILE_SHA256 = (
    "f8a6a3f72fa41f84c0b657b52a7d63afdb183fce24d6f5325a2ebfe3fa5ce0e1"
)
PIN_CONTENT_SHA256 = (
    "b24f1a3c769b7afe1b6803fe92186f81f4d0bbf2b2aa62e51c968a6069a3c56c"
)
SOURCE_SET_FILE_SHA256 = (
    "454ca209ed2f8e946d603e510697ef56b67d9fa7ac42db76fbb72fcd2738e5d2"
)
SOURCE_SET_CONTENT_SHA256 = (
    "3a9b57821d089d52879b73030483a28a6dd9f0acf1213674602b149ec081c8ae"
)
COMPATIBILITY_FILE_SHA256 = (
    "be2436f16c79e41a7aac0ed5ebaf575daecca4ec311907d1b1fb67e08f0cab3f"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "ac5dd6a26107d59250059b2075454d4a4e56c383befe652a5ae105f945d91b5d"
)
SELECTION_SHA256 = (
    "5a44afda913e54a39aa8674ae0eed6558a2f1b1900c7baf5254dc4eb0c383351"
)
SELECTED_RUN = "actions-sim-build-core-crocods-w3"
REPRODUCTION_RUN = "build-core-crocods-local-w3"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "c61fde30675b6a7b41751c3505eccb8d83a3bd23334b099aa9498accf1846016"
    ),
    REPRODUCTION_RUN: (
        "ca9da6d1214d2e5a000a013270d278b7524e10ed9cd2e8ccb0dbc2ed59dab602"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "1d1e04c961f182d33a1585fab2d70fa19023f1a1aafaea014a28c52875717a7d"
    ),
    REPRODUCTION_RUN: (
        "94219a0e3c4c83b320be830b1bb5f91eb861f9a0358e5e85a74df6be2d65fbbd"
    ),
}
PACKAGE_SHA256 = (
    "9504d858daaee44be2f789dde40f53ab532ba7c2e3515a0468d19740e1423d35"
)
PACKAGE_SIZE = 519486
METADATA_SHA256 = (
    "4bf12dc021fcb628de8d14542a9e5b0ee8aa69828a99adda85346fe54c879cf8"
)
METADATA_SIZE = 944
PIPELINE_BUNDLE_SHA256 = (
    "d4f5928d2c412e75ee02378aa03b944d58625e35eae8bc047d50cf03eeed0c0d"
)
REPOSITORY_HEAD = "9d95cda3d6dce32c8d33d85a58f37adad19d38d7"
WORKFLOW_SHA256 = (
    "219b513f5a38220c1338dfa9b855c50da7ef8506bd8a0ab583bedf4849efe88d"
)
RUNNERS = {
    SELECTED_RUN: {
        "backend": "local-docker",
        "local_only": True,
        "mode": "simulated",
        "profile": "github-actions",
        "publication": "disabled",
    },
    REPRODUCTION_RUN: {
        "backend": "local-docker",
        "local_only": True,
        "mode": "native",
        "profile": "local",
        "publication": "disabled",
    },
}
TARGETS = {
    "arm64": {
        "artifact_sha256": (
            "4bb772d20f1e352efd8d0f9f43788531ec9cf13df295aac04d0a14fe1bcc39e1"
        ),
        "artifact_size": 632216,
        "record_sha256": {
            SELECTED_RUN: (
                "35364a216b9988be4ed3182e7c39c7c6e8b24ec834079cd5b7d1c5f325198930"
            ),
            REPRODUCTION_RUN: (
                "c7f73aa5bb1429cb7dd35d9a7de1952c440b0270ae9e4ba7420bceefda0cefba"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "6b22fd62c2e2ed687090c5f43c0dc5b63b9b7ab022438a9e689616aa5faf87a6"
            ),
            REPRODUCTION_RUN: (
                "764cba640ae6daab3075d8cd1335c72c97bdee5bfaba440dfebd1d836017693c"
            ),
        },
        "log_size": 16595,
        "warning_count": 9,
        "note_count": 7,
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
        "image_id": (
            "sha256:538411e2759cd5482068fd0c1f24d5a033138cd9f49db31f2c620929a8b046a9"
        ),
        "archive_sha256": (
            "bb1c69cf19fcf3cbccaee06cc8b8a01bf7020fb1ac306d3d876530b6e9636012"
        ),
        "recipe_snapshot_sha256": (
            "0b223eeed461cea8c173a97fcdbbe021332c4f0c06a59b0f4c9ee77585ad5b03"
        ),
        "recipe_snapshot_size": 1980846,
    },
    "armhf": {
        "artifact_sha256": (
            "a53a16452ce5d1e4efea3d6057ef8a86be7400d0703bd82d559deab35a9573e1"
        ),
        "artifact_size": 560764,
        "record_sha256": {
            SELECTED_RUN: (
                "77f3c243f054f4d9c143af06299557117711cd1742d01d5d84c4b7e71ee24b3b"
            ),
            REPRODUCTION_RUN: (
                "b138c1b2e1e5c63322d6dbd833b3f94ae55609b1686a9291b7bfe16a6749f8f4"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "05c5c87eedb63795e408c68da023507c71edf1d94811643bcac33133272708d3"
            ),
            REPRODUCTION_RUN: (
                "05c5c87eedb63795e408c68da023507c71edf1d94811643bcac33133272708d3"
            ),
        },
        "log_size": 9900,
        "warning_count": 0,
        "note_count": 0,
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:393a23661c4178edfc4e5ea0221e5de317a40f2f50a9fff1cb76e9e322189dd9"
        ),
        "archive_sha256": (
            "e2b103c7bf1fdc9bb3ce3cf7bcde9cf2f3fd473fb0d916e8b4d0b4d278fd1afe"
        ),
        "recipe_snapshot_sha256": (
            "d0b6bc89578a757c79d76c70323072ce01f27e674a88575bd85611cd920d576b"
        ),
        "recipe_snapshot_size": 1980555,
    },
}
SOURCE_RECORD_IDENTITY = {
    "commit": SOURCE_COMMIT,
    "requested_ref": "refs/heads/master",
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
    "tree": SOURCE_TREE,
    "url": SOURCE_URL,
}
CAVEAT_TOKENS = (
    "50 C compile commands",
    "nine reviewed warnings and seven notes",
    "binary identity git 87bbb3d",
    "display_version v1",
    "needs_kbd_mouse_focus=true",
    "GPLv2-or-later",
    "zlib 1.1.3",
    "cpc6128.bin.c",
    "human legal and policy gate",
    "no offline source bundle",
    "dockerfile_linkage=unverified-local-cache",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)


class CrocodsCoreEvidenceTests(unittest.TestCase):
    def test_semantic_pin_and_compatibility_bind_promoted_evidence(self) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        pin_report = pipeline.validate_pin_set_document(pin, document_path=pin_path)
        self.assertEqual("valid", pin_report["status"], pin_report["errors"])
        compatibility_report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual(
            "valid", compatibility_report["status"], compatibility_report["errors"]
        )

        self.assertEqual(PIN_FILE_SHA256, file_sha256(pin_path))
        self.assertEqual(PIN_CONTENT_SHA256, pin["content_sha256"])
        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertIsNone(pin["parent"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(
            COMPATIBILITY_FILE_SHA256, file_sha256(compatibility_path)
        )
        self.assertEqual(
            COMPATIBILITY_CONTENT_SHA256, compatibility["content_sha256"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SIZE, selection["package"]["size"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN], selection["e2e"]["content_sha256"]
        )
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN],
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            E2E_CONTENT_SHA256[REPRODUCTION_RUN],
            compatibility["reproduction_e2e_content_sha256"],
        )
        self.assertEqual(
            f".local-e2e/runs/{SELECTED_RUN}/e2e-record.json",
            compatibility["e2e_run"],
        )
        self.assertEqual(
            f".local-e2e/runs/{REPRODUCTION_RUN}/e2e-record.json",
            compatibility["reproduction_run"],
        )

        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)
        for reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            SOURCE_LOCK_PATH,
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
        ):
            self.assertNotIn("tranche", reference.casefold())

        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden = selected_target["golden_record"]
                artifact = golden["artifact"]

                self.assertEqual(CORE_ID, golden["core_id"])
                self.assertEqual(architecture, golden["architecture"])
                self.assertEqual(SOURCE_RECORD_IDENTITY, golden["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual(
                    "needs-target-runtime", target["runtime_validation"]
                )
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["version_requirements"], artifact["version_requirements"]
                )
                self.assertEqual([], golden["build"]["compile_definitions"])
                self.assertEqual(
                    {
                        "compiler_scope": "c",
                        "derivation": "native-space-short7-v1",
                        "value": crocods.CROCODS_NATIVE_GIT_VERSION,
                    },
                    golden["build"]["git_version"],
                )
                self.assertEqual(METADATA_SHA256, golden["metadata"]["sha256"])
                self.assertEqual(METADATA_SIZE, golden["metadata"]["size"])

                recipe = golden["recipe"]
                self.assertFalse(recipe["repository_dirty"])
                self.assertEqual(REPOSITORY_HEAD, recipe["repository_head"])
                self.assertEqual(
                    PIPELINE_BUNDLE_SHA256,
                    recipe["pipeline_bundle"]["content_sha256"],
                )
                self.assertEqual(
                    ".github/workflows/build-crocods.yml", recipe["workflow"]
                )
                self.assertEqual(WORKFLOW_SHA256, recipe["workflow_sha256"])
                self.assertEqual(
                    "policies/core-commit-blacklist.json",
                    recipe["commit_blacklist"]["path"],
                )

                toolchain = golden["toolchain"]
                self.assertEqual(expected["image_id"], toolchain["image_id"])
                self.assertEqual(expected["image_id"], toolchain["resolved_image_id"])
                self.assertEqual(
                    "unverified-local-cache", toolchain["dockerfile_linkage"]
                )
                self.assertEqual(
                    expected["archive_sha256"],
                    toolchain["archive_provenance"]["archive"]["sha256"],
                )

                snapshot_reference = golden["local_store"]["recipe_snapshots"][
                    architecture
                ]
                self.assertEqual(
                    expected["recipe_snapshot_sha256"],
                    snapshot_reference["sha256"],
                )
                snapshot_path = ROOT / snapshot_reference["path"]
                self.assertEqual(
                    expected["recipe_snapshot_size"], snapshot_path.stat().st_size
                )
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path, golden, f"{CORE_ID}/{architecture}"
                    ),
                )

    def test_source_set_release_and_channels_are_core_owned(self) -> None:
        source_set_path = ROOT / SOURCE_SET_PATH
        source_set = load_document(source_set_path)
        registry.validate_source_set(source_set)
        profile_report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SOURCE_SET_FILE_SHA256, file_sha256(source_set_path))
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertEqual(PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"])
        self.assertEqual(
            PIN_CONTENT_SHA256, source_set["evidence_pin"]["content_sha256"]
        )
        self.assertEqual({CORE_ID}, set(source_set["sources"]))

        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_PATH, source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, source["file_sha256"])
        self.assertEqual(SOURCE_LOCK_CONTENT_SHA256, source["content_sha256"])
        source_lock = load_document(ROOT / SOURCE_LOCK_PATH)
        self.assertEqual(
            SOURCE_LOCK_FILE_SHA256, file_sha256(ROOT / SOURCE_LOCK_PATH)
        )
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
                "submodules": [],
            },
            source_lock["source"],
        )

        self.assertEqual(1, profile_report["counts"]["source_locks"])
        self.assertEqual(2, profile_report["counts"]["build_evidence_cells"])
        cells = {
            cell["architecture"]: cell
            for cell in profile_report["build_evidence_cells"]
        }
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(profile=architecture):
                self.assertEqual(CORE_ID, cells[architecture]["core_id"])
                self.assertEqual(
                    SOURCE_LOCK_ID, cells[architecture]["source_lock_id"]
                )
                self.assertEqual(
                    expected["artifact_sha256"],
                    cells[architecture]["artifact_sha256"],
                )
                self.assertEqual(
                    expected["execution_profile_id"],
                    cells[architecture]["execution_profile_id"],
                )
        self.assertTrue(profile_report["device_views"])
        self.assertEqual(8, len(profile_report["device_views"]))
        self.assertEqual(
            16,
            sum(len(view["devices"]) for view in profile_report["device_views"]),
        )
        self.assertTrue(
            all(
                view["status"] == "provisional"
                and view["eligibility"] == "provisional-unverified"
                and not view["eligible_build_evidence_cells"]
                for view in profile_report["device_views"]
            )
        )

        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
                )
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])

        pin_path = ROOT / PIN_PATH
        pin = load_document(pin_path)
        release_root = ROOT / ".local-e2e" / "releases" / SEMANTIC_ID
        release_report = pipeline.validate_local_release(
            release_root,
            pin,
            file_sha256(pin_path),
            expected_release_id=SEMANTIC_ID,
        )
        self.assertEqual("valid", release_report["status"], release_report["errors"])
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])
        self.assertEqual(PACKAGE_SIZE, release["assets"][0]["size"])

    def test_selected_and_reproduction_runs_are_byte_reproducible(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        log_lines: dict[str, list[Counter[str]]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }

        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence_path = run_root / "e2e-record.json"
                evidence = load_document(evidence_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
                self.assertEqual(E2E_CONTENT_SHA256[run_id], evidence["content_sha256"])
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    [CORE_ID], [package["core_id"] for package in evidence["packages"]]
                )

                package = evidence["packages"][0]
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                self.assertEqual(PACKAGE_SIZE, package_path.stat().st_size)
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/crocods_libretro.so",
                            "cores/crocods_libretro.so",
                            "crocods_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )
                    self.assertTrue(
                        all(
                            info.date_time == (1980, 1, 1, 0, 0, 0)
                            for info in archive.infolist()
                        )
                    )
                    package_manifest = json.loads(archive.read("manifest.json"))
                    self.assertEqual(CORE_ID, package_manifest["core_id"])
                    self.assertTrue(package_manifest["local_only"])
                    self.assertEqual("disabled", package_manifest["publication"])
                    self.assertEqual(
                        METADATA_SHA256, package_manifest["metadata"]["sha256"]
                    )
                    for architecture, expected in TARGETS.items():
                        packaged_artifact = package_manifest["artifacts"][architecture]
                        self.assertEqual(
                            expected["artifact_sha256"], packaged_artifact["sha256"]
                        )
                        self.assertEqual(
                            expected["image_id"],
                            packaged_artifact["toolchain_image_id"],
                        )
                        self.assertEqual(
                            SOURCE_COMMIT, packaged_artifact["source_commit"]
                        )

                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        record_path = (
                            run_root / CORE_ID / architecture / "build-record.json"
                        )
                        record = load_document(record_path)
                        self.assertEqual(
                            expected["record_sha256"][run_id], file_sha256(record_path)
                        )
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertEqual(
                            crocods.CROCODS_NATIVE_GIT_VERSION,
                            record["build"]["git_version"]["value"],
                        )

                        log_path = record_path.parent / record["build"]["log"]
                        log_text = log_path.read_text(encoding="utf-8")
                        self.assertEqual(
                            expected["log_sha256"][run_id], file_sha256(log_path)
                        )
                        self.assertEqual(expected["log_size"], log_path.stat().st_size)
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                log_text,
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
                            )
                        )
                        self.assertEqual(
                            expected["warning_count"],
                            sum("warning:" in line for line in log_text.splitlines()),
                        )
                        self.assertEqual(
                            expected["note_count"],
                            sum("note:" in line for line in log_text.splitlines()),
                        )
                        log_lines[architecture].append(Counter(log_text.splitlines()))
                        logs[architecture].append(log_path.read_bytes())

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact_bytes = artifact_path.read_bytes()
                        self.assertIn(b"git 87bbb3d", artifact_bytes)
                        artifacts[architecture].append(artifact_bytes)
                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata_payloads.append(metadata_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads)
        )
        metadata_text = metadata_payloads[0].decode("utf-8")
        self.assertIn('display_version = "v1"', metadata_text)
        self.assertIn('license = "MIT"', metadata_text)
        self.assertIn('supported_extensions = "dsk|sna|kcr"', metadata_text)
        self.assertIn('supports_no_game = "false"', metadata_text)
        self.assertIn('needs_fullpath = "false"', metadata_text)
        self.assertIn('disk_control = "false"', metadata_text)
        self.assertIn('libretro_saves = "false"', metadata_text)
        self.assertIn('needs_kbd_mouse_focus = "true"', metadata_text)
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                self.assertEqual(log_lines[architecture][0], log_lines[architecture][1])
        self.assertNotEqual(logs["arm64"][0], logs["arm64"][1])
        self.assertEqual(logs["armhf"][0], logs["armhf"][1])


if __name__ == "__main__":
    unittest.main()
