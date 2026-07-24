"""Pinned Mednafen PCE Fast individual lifecycle tests."""

from __future__ import annotations

import copy
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import mednafen_pce_fast
from core_pipeline_lib.records import compatibility as compatibility_records

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "mednafen_pce_fast"
OTHER_CORE_ID = "mednafen_ngp"
PIN_NAME = "mednafen_pce_fast-0bc6c8692834-8e747136926e.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"
SOURCE_COMMIT = "0bc6c86928343ca4202c5b6ef33fa4387c47fc12"
SOURCE_TREE = "80bd8d86bb10d9ab374d6de4ca3e129498c3c3e0"
SOURCE_URL = "https://github.com/libretro/beetle-pce-fast-libretro.git"
SOURCE_LOCK_ID = "mednafen_pce_fast-0bc6c8692834"
SOURCE_LOCK_PATH = (
    "pins/sources/mednafen_pce_fast/"
    "0bc6c86928343ca4202c5b6ef33fa4387c47fc12.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "b75d20c75e76934494225130beabb3e6d28b3d7ce6a847a9aef2367b439fa530"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "f2d755989ad999ac2db8f3e1a026b80e0536a51adae35ef1bb4f1136e84d7192"
)
PIN_FILE_SHA256 = (
    "33167e0c925c810b89db8eb7fd9a77f754acf8a47bbe26d78d21c134e7bcafc1"
)
PIN_CONTENT_SHA256 = (
    "a679bbf99ff521d5ed0d7d99fb7f66bd067e5a5bcbf3607eecff8b3b0a9606e9"
)
GOLDEN_FILE_SHA256 = (
    "66881dde741192d97d973fd0a7521465c9f1e9a411ad5d07acd7bc5ced51f673"
)
GOLDEN_CONTENT_SHA256 = (
    "394eb252e7db5f17c1076bc3e69ab9d4ac72e3d6535fe671d1d05eea5e24f767"
)
SELECTION_SHA256 = (
    "8e747136926ea0bc652a2dc2441633d8fa5888e5da59ba914a7637df326c9cba"
)
SELECTED_RUN = "actions-sim-build-core-mednafen_pce_fast-v1"
REPRODUCTION_RUN = "build-core-mednafen_pce_fast-local-v1"
SELECTED_E2E_CONTENT_SHA256 = (
    "5a2a9fcb30ec723b28cbe43bd50cf18d5e3a74a0bdfb986b994ec756a01549f1"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "dbd31f75404ce3c93c0fab919bb2eb7abe43d04d04dfaa7f7063a566a0a77c8b"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "bad6979e876b98696982fe1f7a50b719101d7ef5b2564782da5feb41c5ef9c85"
    ),
    REPRODUCTION_RUN: (
        "f414b2c1242e293cbcecb3cd5dea71da164b992c9321901e51cc321ea6247867"
    ),
}
PACKAGE_SHA256 = (
    "497dec13368d324ab271d55f5de7bc0e8eac73619ab6ed875def269c22174a96"
)
PACKAGE_SIZE = 1131197
METADATA_SHA256 = (
    "b75e4f64518d4161bef48068f6d4be24c4ea0f478431b749b490251430d8ec35"
)
METADATA_SIZE = 1772
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
            "bdbdd42e3cd165ee0ef0ec791d18f44fc958888469391c617b19894562ccd404"
        ),
        "artifact_size": 4536184,
        "record_sha256": {
            SELECTED_RUN: (
                "877e663940c1985db2169a5b2bc83cab8aa9a0bc61e8f54d4917ee54d77b1c15"
            ),
            REPRODUCTION_RUN: (
                "5cc29006b32f57754dbc71678b6ee7f39805d319e3d2cb739ecb9af8b429353c"
            ),
        },
        "log_sha256": (
            "553b1a3d769b93accb1ce50f6c63be93b59aa97533fbdc76334d14e369f611de"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.17", "GLIBC_2.27"],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "449aff51c01627565a423c060e4898c60fb3a6562d584f59c4b10bb8ed760795"
        ),
        "artifact_size": 2557204,
        "record_sha256": {
            SELECTED_RUN: (
                "ece65e26dd18ec2632be99272af624663e93e996a72ebd5fbdd9a30e3ba7f7d1"
            ),
            REPRODUCTION_RUN: (
                "32a43261425e232e1454bd85cd4df9a407c6e973f0fec68fb6a6622944bdd8a2"
            ),
        },
        "log_sha256": (
            "d293de800b216b7db3597de57ed86fec98c15b8dcf379663308880318e8a49e4"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": [
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "librt.so.1",
            "libstdc++.so.6",
        ],
        "version_requirements": ["GCC_3.5", "GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
    },
}
SOURCE_LOCK_IDENTITY = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "submodules": [],
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
    "92-command C compile",
    "exact 92-object link uses C++",
    "v1.31.0.0",
    "no warnings, notes, errors, or fatal diagnostics",
    "GPLv2",
    "pce|cue|ccd|chd|toc|m3u",
    "No firmware or BIOS is packaged",
    "syscard3.pce",
    "38179df8f4ac870017db21ebcbf53114",
    "some games do not work",
    "does not support SuperGrafx games",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device eligibility claims remain gated",
)
FAILURE_MARKERS = (
    "error:",
    "fatal:",
    "undefined reference",
    "dubious ownership",
    "make: ***",
)


class MednafenPceFastCoreEvidenceTests(unittest.TestCase):
    def test_singleton_pin_and_compatibility_bind_promoted_evidence(self) -> None:
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
            "valid",
            compatibility_report["status"],
            compatibility_report["errors"],
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
        self.assertEqual(PIN_PATH, compatibility["golden_source"])

        self.assertEqual(1, len(pin["sources"]))
        golden_reference = pin["sources"][0]
        self.assertEqual(GOLDEN_PATH, golden_reference["path"])
        self.assertEqual(SEMANTIC_ID, golden_reference["pin_id"])
        self.assertEqual(GOLDEN_FILE_SHA256, golden_reference["file_sha256"])
        self.assertEqual(
            GOLDEN_CONTENT_SHA256, golden_reference["content_sha256"]
        )
        golden_path = ROOT / GOLDEN_PATH
        golden = load_document(golden_path)
        self.assertEqual(GOLDEN_FILE_SHA256, file_sha256(golden_path))
        self.assertEqual(GOLDEN_CONTENT_SHA256, golden["content_sha256"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["e2e"]["package_sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
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
        for active_reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            compatibility["golden_source"],
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
            caveats,
        ):
            self.assertNotIn("tranche", active_reference.casefold())

        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden_record = selected_target["golden_record"]
                artifact = golden_record["artifact"]

                self.assertEqual(CORE_ID, golden_record["core_id"])
                self.assertEqual(architecture, golden_record["architecture"])
                self.assertEqual(SOURCE_RECORD_IDENTITY, golden_record["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], selected_target["artifact"]["sha256"]
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual([], golden_record["build"]["compile_definitions"])
                self.assertNotIn("git_version", golden_record["build"])
                self.assertEqual(METADATA_SHA256, golden_record["metadata"]["sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["version_requirements"], artifact["version_requirements"]
                )

                snapshot_reference = golden_record["local_store"][
                    "recipe_snapshots"
                ][architecture]
                snapshot_path = ROOT / snapshot_reference["path"]
                snapshot = load_document(snapshot_path)
                self.assertEqual(9, snapshot["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        golden_record,
                        f"{CORE_ID}/{architecture}",
                    ),
                )

    def test_singleton_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set_path = ROOT / SOURCE_SET_PATH
        source_set = load_document(source_set_path)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
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
        source_lock = load_document(ROOT / source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(SOURCE_LOCK_IDENTITY, source_lock["source"])
        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
        self.assertEqual(5, report["counts"]["execution_profiles"])
        self.assertEqual(8, report["counts"]["runtime_contracts"])
        self.assertEqual(
            {
                "catalog_cores": catalog_core_count,
                "catalog_unlocked_cores": catalog_core_count - 1,
                "evidence_cells": 2,
                "locked_cores": 1,
            },
            report["mirror"],
        )

        cells = {
            cell["architecture"]: cell for cell in report["build_evidence_cells"]
        }
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                cell = cells[architecture]
                self.assertEqual(CORE_ID, cell["core_id"])
                self.assertEqual(SOURCE_LOCK_ID, cell["source_lock_id"])
                self.assertEqual(expected["artifact_sha256"], cell["artifact_sha256"])
                self.assertEqual(
                    expected["execution_profile_id"], cell["execution_profile_id"]
                )
        self.assertTrue(report["device_views"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_channel_lifecycle_is_semantic_and_core_isolated(self) -> None:
        target_paths = {
            "nightly": GOLDEN_PATH,
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
                self.assertEqual(channel, pointer["channel"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", pointer["target"]["path"].casefold())

                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])
                self.assertIn(
                    "channel pointer document does not match its core alias filename",
                    wrong_core["errors"],
                )

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

    def test_selected_and_reproduction_runs_prove_exact_builds(self) -> None:
        contract = mednafen_pce_fast.MEDNAFEN_PCE_FAST_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual(
            "mednafen-pce-fast-c-only-v1", registered_contract.contract_id
        )
        self.assertEqual(
            "mednafen_pce_fast_log_proves_contract",
            registered_contract.proof_name,
        )
        self.assertEqual(92, contract.expected_compile_count)
        self.assertEqual({"c": 92}, dict(contract.expected_language_counts))
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_PAIR_SHA256,
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_INVOCATION_SHA256,
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECT_SHA256,
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_RAW_LINK_OBJECT_SHA256,
            contract.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV_SHA256,
            dict(contract.expected_ordered_link_argv_sha256),
        )

        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                self.assertNotIn("tranche", run_id.casefold())
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                e2e_path = run_root / "e2e-record.json"
                evidence = load_document(e2e_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(e2e_path))
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    SELECTED_E2E_CONTENT_SHA256
                    if run_id == SELECTED_RUN
                    else REPRODUCTION_E2E_CONTENT_SHA256,
                    evidence["content_sha256"],
                )
                self.assertEqual(
                    [CORE_ID], [item["core_id"] for item in evidence["packages"]]
                )
                package = evidence["packages"][0]
                self.assertEqual("packaged", package["result"])
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                self.assertEqual(PACKAGE_SIZE, package["size"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    names = set(archive.namelist())
                    self.assertEqual(
                        {
                            "cores64/mednafen_pce_fast_libretro.so",
                            "cores/mednafen_pce_fast_libretro.so",
                            "mednafen_pce_fast_libretro.info",
                            "manifest.json",
                        },
                        names,
                    )
                    self.assertFalse(
                        any("syscard" in name.casefold() for name in names)
                    )

                builds = {
                    build["architecture"]: build for build in evidence["builds"]
                }
                self.assertEqual(set(TARGETS), set(builds))
                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        build = builds[architecture]
                        self.assertEqual(CORE_ID, build["core_id"])
                        self.assertEqual("passed", build["result"])
                        self.assertEqual(
                            expected["record_sha256"][run_id], build["record_sha256"]
                        )
                        record_path = ROOT / build["record"]
                        self.assertEqual(
                            build["record_sha256"], file_sha256(record_path)
                        )
                        record = load_document(record_path)
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual("libretro-super", record["build"]["driver"])
                        self.assertEqual("sanitized-v1", record["build"]["environment"])
                        self.assertEqual([], record["build"]["compile_definitions"])
                        self.assertNotIn("git_version", record["build"])

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(expected["log_sha256"], file_sha256(log_path))
                        logs[architecture].append(log_bytes)
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
                            92,
                            sum(" -c " in line for line in log_text.splitlines()),
                        )
                        self.assertNotIn("GIT_VERSION", log_text)
                        self.assertNotIn("CORE_PIPELINE_", log_text)
                        self.assertEqual(0, log_text.casefold().count("warning:"))
                        self.assertEqual(0, log_text.casefold().count("note:"))
                        lowered_log = log_text.casefold()
                        for marker in FAILURE_MARKERS:
                            self.assertNotIn(marker, lowered_log)

                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "v0.9.38.7"', metadata)
                        self.assertIn(b'license = "GPLv2"', metadata)
                        self.assertIn(
                            b'supported_extensions = "pce|cue|ccd|chd|toc|m3u"',
                            metadata,
                        )
                        self.assertIn(b'supports_no_game = "false"', metadata)
                        self.assertIn(b'savestate_features = "deterministic"', metadata)
                        self.assertIn(b'firmware_count = 4', metadata)
                        self.assertIn(b'firmware0_path = "syscard3.pce"', metadata)
                        self.assertIn(
                            b'38179df8f4ac870017db21ebcbf53114', metadata
                        )
                        self.assertIn(b'does not support SuperGrafx games', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"v1.31.0.0", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])
                self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_compatibility_and_pin_mutations_fail_closed(self) -> None:
        _, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        wrong_digest = copy.deepcopy(compatibility)
        wrong_digest["content_sha256"] = "0" * 64
        digest_report = pipeline.validate_core_compatibility_document(
            wrong_digest,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", digest_report["status"])
        self.assertIn(
            "core compatibility content digest is invalid", digest_report["errors"]
        )

        malformed_documents = {
            "artifact": copy.deepcopy(compatibility),
            "elf": copy.deepcopy(compatibility),
            "target": copy.deepcopy(compatibility),
        }
        malformed_documents["artifact"]["targets"]["arm64"]["artifact_sha256"] = 7
        malformed_documents["elf"]["targets"]["arm64"]["elf"] = "ELF64/arbitrary"
        malformed_documents["target"]["targets"]["arm64"] = []
        expected_errors = {
            "artifact": f"{CORE_ID}/arm64: artifact digest is invalid",
            "elf": f"{CORE_ID}/arm64: ELF label is invalid",
            "target": f"{CORE_ID}/arm64: compatibility target is invalid",
        }
        for label, malformed in malformed_documents.items():
            with self.subTest(compatibility_mutation=label):
                malformed["content_sha256"] = (
                    pipeline.core_compatibility_content_sha256(malformed)
                )
                report = pipeline.validate_core_compatibility_document(
                    malformed,
                    document_path=compatibility_path,
                    repository_root=ROOT,
                    verify_pin=False,
                )
                self.assertEqual("invalid", report["status"])
                self.assertIn(expected_errors[label], report["errors"])

        missing_reproduction = copy.deepcopy(compatibility)
        missing_reproduction["reproduction_run"] = (
            ".local-e2e/runs/nonexistent-mednafen-pce-fast/e2e-record.json"
        )
        missing_reproduction["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(missing_reproduction)
        )
        missing_report = pipeline.validate_core_compatibility_document(
            missing_reproduction,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", missing_report["status"])
        self.assertIn(
            "individual core reproduction E2E record is unavailable",
            missing_report["errors"],
        )

        wrong_reproduction_digest = copy.deepcopy(compatibility)
        wrong_reproduction_digest["reproduction_e2e_content_sha256"] = "0" * 64
        wrong_reproduction_digest["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(wrong_reproduction_digest)
        )
        reproduction_digest_report = pipeline.validate_core_compatibility_document(
            wrong_reproduction_digest,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertIn(
            "individual core reproduction E2E content differs from compatibility",
            reproduction_digest_report["errors"],
        )

        same_run = copy.deepcopy(compatibility)
        same_run["reproduction_run"] = same_run["e2e_run"]
        same_run["reproduction_e2e_content_sha256"] = same_run[
            "selected_e2e_content_sha256"
        ]
        same_run["content_sha256"] = pipeline.core_compatibility_content_sha256(
            same_run
        )
        same_run_report = pipeline.validate_core_compatibility_document(
            same_run,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        swapped_runs = copy.deepcopy(compatibility)
        swapped_runs["e2e_run"], swapped_runs["reproduction_run"] = (
            swapped_runs["reproduction_run"],
            swapped_runs["e2e_run"],
        )
        swapped_runs["content_sha256"] = pipeline.core_compatibility_content_sha256(
            swapped_runs
        )
        swapped_report = pipeline.validate_core_compatibility_document(
            swapped_runs,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", swapped_report["status"])
        self.assertIn(
            "individual core selected E2E run differs from compatibility",
            swapped_report["errors"],
        )

        pin_mutations = {
            "digest": copy.deepcopy(pin),
            "semantic_id": copy.deepcopy(pin),
            "source_reference": copy.deepcopy(pin),
        }
        pin_mutations["digest"]["content_sha256"] = "0" * 64
        pin_mutations["semantic_id"]["pin_id"] = (
            "mednafen_pce_fast-nonsemantic-pin"
        )
        pin_mutations["semantic_id"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["semantic_id"])
        )
        pin_mutations["source_reference"]["sources"][0]["file_sha256"] = "0" * 64
        pin_mutations["source_reference"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["source_reference"])
        )
        expected_pin_errors = {
            "digest": "individual core pin: pin-set content digest is invalid",
            "semantic_id": "individual core pin ID is not semantic",
            "source_reference": (
                "individual core pin: source 0 no longer matches the pin"
            ),
        }
        for label, malformed_pin in pin_mutations.items():
            with self.subTest(pin_mutation=label), mock.patch.object(
                compatibility_records,
                "load_json",
                return_value=malformed_pin,
            ):
                pin_report = pipeline.validate_core_compatibility_document(
                    compatibility,
                    document_path=compatibility_path,
                    repository_root=ROOT,
                )
                self.assertEqual("invalid", pin_report["status"])
                self.assertIn(expected_pin_errors[label], pin_report["errors"])

    def test_reproduction_rejects_recomputed_record_tampering(self) -> None:
        _, pin, _, _ = load_core_documents(CORE_ID, PIN_NAME)
        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        mutations = {
            "log": "historical build differs",
            "build": "historical build differs",
            "recipe": "historical recipe differs",
            "source": "historical source differs",
            "toolchain": "historical toolchain differs",
            "record_fields": "build record fields are invalid",
        }
        for mutation, expected_error in mutations.items():
            with self.subTest(mutation=mutation), copied_e2e_run(
                REPRODUCTION_RUN,
                prefix=f"compat-tamper-pce-fast-{mutation}-",
                content_hasher=pipeline.e2e_content_sha256,
            ) as (run_root, evidence):
                record_path = run_root / CORE_ID / "arm64" / "build-record.json"
                record = load_document(record_path)
                if mutation == "log":
                    log_path = record_path.parent / record["build"]["log"]
                    log_path.write_text(
                        log_path.read_text(encoding="utf-8") + "warning: extra\n",
                        encoding="utf-8",
                    )
                    record["build"]["log_sha256"] = file_sha256(log_path)
                elif mutation == "build":
                    record["build"]["environment"] = "tampered-v1"
                elif mutation == "recipe":
                    record["recipe"]["repository_dirty"] = not record["recipe"][
                        "repository_dirty"
                    ]
                elif mutation == "source":
                    record["source"]["resolved_url"] = (
                        "https://example.invalid/tampered.git"
                    )
                elif mutation == "toolchain":
                    record["toolchain"]["compiler"] += " tampered"
                else:
                    record["unexpected"] = True
                write_document(record_path, record)
                refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)
                with self.assertRaisesRegex(pipeline.PipelineError, expected_error):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )


if __name__ == "__main__":
    unittest.main()
