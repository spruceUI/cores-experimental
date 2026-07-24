"""Pinned Mednafen Lynx individual lifecycle tests."""

from __future__ import annotations

import copy
from collections import Counter
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import mednafen_lynx

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "mednafen_lynx"
OTHER_CORE_ID = "mednafen_ngp"
PIN_NAME = "mednafen_lynx-fcdefcfb3c11-c2247f1f6de1.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "fcdefcfb3c11d6d2e71be076a5d3df2e88ab73ed"
SOURCE_TREE = "3e815d4d338aa1a201e009b36cf34e5a53ad4c9e"
SOURCE_URL = "https://github.com/libretro/beetle-lynx-libretro.git"
SOURCE_LOCK_ID = "mednafen_lynx-fcdefcfb3c11"
SOURCE_LOCK_PATH = (
    "pins/sources/mednafen_lynx/"
    "fcdefcfb3c11d6d2e71be076a5d3df2e88ab73ed.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "28fd0706125612fb5a26aaac3cc319b2d2a4c73d87a6265ef5c8917ecab283d3"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "038652c31fa459cf95247274ade47692dab5dd4a49471d909421cab86d308e6e"
)
SOURCE_SET_CONTENT_SHA256 = (
    "2924936a5fb35d9f8ef8db2d2d5f1dd2b4ddb7d0d91997ac73037d512519f378"
)
PIN_FILE_SHA256 = (
    "79d0b6588cc62d67ae63bd356b6b631247da0e96fb0a903831703468bb176236"
)
PIN_CONTENT_SHA256 = (
    "2564abdc524f71d264584071942a2ac87967adeab1ed5b870e498a22dc39d16b"
)
SELECTION_SHA256 = (
    "c2247f1f6de1d5b86fcc304e199273d7ad5505f0253ddd7dcd9e5b200f41f82f"
)
GOLDEN_FILE_SHA256 = (
    "163b3694567078ee5915e9485ff2f52568f6f2f1f7b4831643aa101baab6f241"
)
GOLDEN_CONTENT_SHA256 = (
    "e29fa5dc7a07e5256b13b5b091f7d95bab10a512538bff920cf6e7b288d79285"
)
SELECTED_RUN = "actions-sim-build-core-mednafen_lynx-v1"
REPRODUCTION_RUN = "build-core-mednafen_lynx-local-v1"
SELECTED_E2E_CONTENT_SHA256 = (
    "bcb0347802262a2801b058f225482cd1d7959a2960881cfe2e23d79824bb264a"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "4ec2d8bac52f3fd4707d99bc0763985510c06ea35ade629b3f2c15458b077505"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "ef63a4fd2e5345762ce297141f50f025b42b0916c7bbd089f6dbb1eeb5c533f1"
    ),
    REPRODUCTION_RUN: (
        "3980f31210afd0ca30091078bbeccc988145ab48704d732ad8b32f15a67c952f"
    ),
}
PACKAGE_SHA256 = (
    "0b9e88a0c3e246b2dcba45b60459e21bf1e93b6603a29f5a68449308d7c400b0"
)
PACKAGE_SIZE = 189414
METADATA_SHA256 = (
    "b81537311f91546383465273faf6c31c835a87b60a7466c8e1953e8c1d51e89e"
)
METADATA_SIZE = 838
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
            "7681c558428d0490dd91af225ea83a82112a06cf5b19fe6f6d69a362b3bffaf6"
        ),
        "artifact_size": 217608,
        "record_sha256": {
            SELECTED_RUN: (
                "878f1329df1ddee628b09554f1128852ae7b99051c0c1478feba0f3226c8b4a4"
            ),
            REPRODUCTION_RUN: (
                "a3ba130b9c34083290c05f0a8fb9ef648a440d7d5ea1c7de0d7b5c5893ed7d2d"
            ),
        },
        "log_sha256": (
            "43e8b082c99744994b5189bac9393590ba2bf2bf7ebe46bbf25f45c72dcd2ccf"
        ),
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libgcc_s.so.1",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.9",
            "GCC_3.0",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.21",
            "GLIBC_2.17",
        ],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "1d3a3dcb98e52186bce0eeaed9ab1a64262be599773f27b18df692674dc12d1a"
        ),
        "artifact_size": 189756,
        "record_sha256": {
            SELECTED_RUN: (
                "06089ac03849cf68616f44f5d5f22c84a0c93cbe912b627267554a2fec788a27"
            ),
            REPRODUCTION_RUN: (
                "4393efec38e89627e35bcef3eb00ac0b79b889413211395e6518b8bfb1462196"
            ),
        },
        "log_sha256": (
            "70a98dd3eea6a059d7b181791bfeaf81feba36565b0b55185aeb4d3912939d55"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": [
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "librt.so.1",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.9",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.21",
            "GLIBC_2.4",
            "GLIBC_2.7",
        ],
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
    "build logs",
    "exactly once on each of 16 C++ compiles",
    "29 compiles (13 C and 16 C++)",
    "v1.24.0 fcdefcf",
    "-Wformat-truncation",
    "two reviewed GCC 7.1 psABI notes",
    "Zlib|GPLv2",
    "lnx|lyx|bll|o",
    "External firmware lynxboot.img is required",
    "fcd403db69f54290b51035d82f835e7b",
    "No firmware is packaged",
    "regular Handy core",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)
FAILURE_MARKERS = (
    "error:",
    "fatal:",
    "undefined reference",
    "dubious ownership",
    "make: ***",
)
NATIVE_VERSION_OCCURRENCE_COUNT = (
    mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCE_COUNT
)


class MednafenLynxCoreEvidenceTests(unittest.TestCase):
    def test_singleton_pin_and_compatibility_bind_promoted_evidence(self) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        pin_report = pipeline.validate_pin_set_document(
            pin, document_path=pin_path
        )
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

        golden_reference = pin["sources"][0]
        golden_path = ROOT / golden_reference["path"]
        golden = load_document(golden_path)
        self.assertEqual(GOLDEN_FILE_SHA256, file_sha256(golden_path))
        self.assertEqual(GOLDEN_FILE_SHA256, golden_reference["file_sha256"])
        self.assertEqual(GOLDEN_CONTENT_SHA256, golden["content_sha256"])
        self.assertEqual(
            GOLDEN_CONTENT_SHA256, golden_reference["content_sha256"]
        )
        self.assertEqual(SEMANTIC_ID, golden["pin_id"])
        self.assertEqual({CORE_ID}, set(golden["cores"]))
        self.assertEqual({CORE_ID}, set(golden["build_goldens"]))

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
                self.assertEqual(
                    "needs-target-runtime", target["runtime_validation"]
                )
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(
                    expected["artifact_sha256"], target["artifact_sha256"]
                )
                self.assertEqual(
                    expected["artifact_sha256"],
                    selected_target["artifact"]["sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual([], golden_record["build"]["compile_definitions"])
                self.assertNotIn("git_version", golden_record["build"])
                self.assertEqual(
                    METADATA_SHA256, golden_record["metadata"]["sha256"]
                )
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"],
                    target["version_requirements"],
                )
                self.assertEqual(
                    expected["version_requirements"],
                    artifact["version_requirements"],
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

        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertEqual(
            PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"]
        )
        self.assertEqual(
            PIN_CONTENT_SHA256, source_set["evidence_pin"]["content_sha256"]
        )
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_PATH, source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, source["file_sha256"])
        self.assertEqual(
            SOURCE_LOCK_CONTENT_SHA256, source["content_sha256"]
        )
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
            cell["architecture"]: cell
            for cell in report["build_evidence_cells"]
        }
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                cell = cells[architecture]
                self.assertEqual(CORE_ID, cell["core_id"])
                self.assertEqual(SOURCE_LOCK_ID, cell["source_lock_id"])
                self.assertEqual(
                    expected["artifact_sha256"], cell["artifact_sha256"]
                )
                self.assertEqual(
                    expected["execution_profile_id"],
                    cell["execution_profile_id"],
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
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": (
                f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json"
            ),
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT
                    / ".local-e2e"
                    / "channels"
                    / f"{channel}.{CORE_ID}.json"
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
                self.assertNotIn(
                    "tranche", pointer["target"]["path"].casefold()
                )

                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])
                self.assertIn(
                    "channel pointer document does not match its core alias "
                    "filename",
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
        self.assertEqual(
            "valid", release_report["status"], release_report["errors"]
        )
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual(
            [CORE_ID], [asset["core_id"] for asset in release["assets"]]
        )
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

    def test_selected_and_reproduction_runs_prove_exact_builds(self) -> None:
        contract = mednafen_lynx.MEDNAFEN_LYNX_LOG_CONTRACT
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual(
            "mednafen-lynx-mixed-language-v1",
            registered_contract.contract_id,
        )
        self.assertEqual(
            "mednafen_lynx_log_proves_contract",
            registered_contract.proof_name,
        )
        self.assertEqual(29, contract.expected_compile_count)
        self.assertEqual(
            {"c": 13, "cxx": 16}, dict(contract.expected_language_counts)
        )
        self.assertEqual(
            mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_COMPILE_PAIR_SHA256,
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_COMPILE_INVOCATION_SHA256,
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_LINK_OBJECT_SHA256,
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_RAW_LINK_OBJECT_SHA256,
            contract.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_ORDERED_LINK_ARGV_SHA256,
            dict(contract.expected_ordered_link_argv_sha256),
        )
        self.assertEqual(
            "native-space-short7-v1",
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_DERIVATION,
        )
        self.assertEqual(
            " fcdefcf", mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION
        )
        self.assertEqual(
            frozenset({"cxx"}),
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_COMPILER_SCOPE,
        )
        self.assertEqual(
            {"c": 0, "cxx": 1},
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE,
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
                    [CORE_ID],
                    [item["core_id"] for item in evidence["packages"]],
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
                            "cores64/mednafen_lynx_libretro.so",
                            "cores/mednafen_lynx_libretro.so",
                            "mednafen_lynx_libretro.info",
                            "manifest.json",
                        },
                        names,
                    )
                    self.assertFalse(
                        any("lynxboot.img" in name.casefold() for name in names)
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
                            expected["record_sha256"][run_id],
                            build["record_sha256"],
                        )
                        record_path = ROOT / build["record"]
                        self.assertEqual(
                            build["record_sha256"], file_sha256(record_path)
                        )
                        record = load_document(record_path)
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual(
                            "libretro-super", record["build"]["driver"]
                        )
                        self.assertEqual(
                            "sanitized-v1", record["build"]["environment"]
                        )
                        self.assertEqual(
                            [], record["build"]["compile_definitions"]
                        )
                        self.assertNotIn("git_version", record["build"])

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(
                            expected["log_sha256"], file_sha256(log_path)
                        )
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
                            NATIVE_VERSION_OCCURRENCE_COUNT,
                            log_text.count(
                                mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_LOG_TOKEN
                            ),
                        )
                        warning_lines = tuple(
                            line
                            for line in log_text.splitlines()
                            if "warning:" in line.casefold()
                        )
                        note_lines = tuple(
                            line
                            for line in log_text.splitlines()
                            if "note:" in line.casefold()
                        )
                        self.assertEqual(
                            Counter(
                                mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_WARNING_LINES[
                                    architecture
                                ]
                            ),
                            Counter(warning_lines),
                        )
                        self.assertEqual(
                            Counter(
                                mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_NOTE_LINES[
                                    architecture
                                ]
                            ),
                            Counter(note_lines),
                        )
                        lowered_log = log_text.casefold()
                        for marker in FAILURE_MARKERS:
                            self.assertNotIn(marker, lowered_log)

                        metadata_path = (
                            record_path.parent / record["metadata"]["path"]
                        )
                        self.assertEqual(
                            METADATA_SHA256, file_sha256(metadata_path)
                        )
                        self.assertEqual(
                            METADATA_SIZE, record["metadata"]["size"]
                        )
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'display_version = "v1.24.0"', metadata)
                        self.assertIn(b'license = "Zlib|GPLv2"', metadata)
                        self.assertIn(
                            b'supported_extensions = "lnx|lyx|bll|o"',
                            metadata,
                        )
                        self.assertIn(b'firmware0_path = "lynxboot.img"', metadata)
                        self.assertIn(b'firmware0_opt = "false"', metadata)
                        self.assertIn(
                            b"fcd403db69f54290b51035d82f835e7b", metadata
                        )
                        self.assertIn(b"regular Handy core", metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = (
                            record_path.parent / record["artifact"]["path"]
                        )
                        self.assertEqual(
                            expected["artifact_sha256"],
                            file_sha256(artifact_path),
                        )
                        artifact = artifact_path.read_bytes()
                        self.assertIn(b"v1.24.0 fcdefcf", artifact)
                        artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(
                payload == metadata_payloads[0]
                for payload in metadata_payloads[1:]
            )
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])
                self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_compatibility_mutations_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
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
            "core compatibility content digest is invalid",
            digest_report["errors"],
        )

        malformed = copy.deepcopy(compatibility)
        malformed["targets"]["arm64"]["artifact_sha256"] = 7
        malformed["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(malformed)
        )
        malformed_report = pipeline.validate_core_compatibility_document(
            malformed,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", malformed_report["status"])
        self.assertIn(
            f"{CORE_ID}/arm64: artifact digest is invalid",
            malformed_report["errors"],
        )

        missing_reproduction = copy.deepcopy(compatibility)
        missing_reproduction["reproduction_run"] = (
            ".local-e2e/runs/nonexistent-mednafen-lynx/e2e-record.json"
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

        same_run = copy.deepcopy(compatibility)
        same_run["reproduction_run"] = same_run["e2e_run"]
        same_run["reproduction_e2e_content_sha256"] = same_run[
            "selected_e2e_content_sha256"
        ]
        same_run["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(same_run)
        )
        same_run_report = pipeline.validate_core_compatibility_document(
            same_run,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

    def test_reproduction_rejects_recomputed_log_tampering(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-lynx-log-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_path.write_text(
                log_path.read_text(encoding="utf-8") + "warning: extra\n",
                encoding="utf-8",
            )
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(
                run_root, evidence, pipeline.e2e_content_sha256
            )

            mutated = copy.deepcopy(compatibility)
            mutated["reproduction_run"] = (
                f".local-e2e/runs/{run_root.name}/e2e-record.json"
            )
            mutated["reproduction_e2e_content_sha256"] = evidence[
                "content_sha256"
            ]
            mutated["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(mutated)
            )
            report = pipeline.validate_core_compatibility_document(
                mutated,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertEqual("invalid", report["status"])
            self.assertIn(
                "individual core reproduction E2E validation failed: "
                f"{CORE_ID}/arm64 compatibility build: historical build "
                "differs",
                report["errors"],
            )


if __name__ == "__main__":
    unittest.main()
