"""Pinned Gambatte build-evidence tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "gambatte"
OTHER_CORE_ID = "handy"
PIN_NAME = "gambatte-dfc165599f3f-9a6aa3658c05.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "dfc165599f3f1068c40a0b7ad6fe5f161283d483"
SOURCE_TREE = "5ca06b386819d5a99f83531d38d88d1d04db426c"
SOURCE_LOCK_ID = "gambatte-dfc165599f3f"
SELECTION_SHA256 = (
    "9a6aa3658c0534a28a0e791f3ac6b391de09b3cd9208d386dc356bdbb5941137"
)
SELECTED_RUN = "actions-sim-build-core-gambatte-v1"
REPRODUCTION_RUN = "build-core-gambatte-local-v1"
PACKAGE_SHA256 = (
    "1e38889d973ff3285fdb64aff5cb6628202ea6a28431bb24320d90eef4fa29fc"
)
METADATA_SHA256 = (
    "084975942c06a658972890c12a8251fe8d0f6c7ffd2b268850458628bbbe68f4"
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
            "0f36a693e262f89b3e417956718660ed22927444ed8370850fb26e12bc56f47c"
        ),
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libm.so.6",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBC_2.17",
            "GLIBC_2.27",
        ],
    },
    "armhf": {
        "artifact_sha256": (
            "c26f3e41a8c3fa556d5d9401f4ecdea9d25699ff0537a6488a1f3e16e678b0d9"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libgcc_s.so.1", "libm.so.6", "libstdc++.so.6"],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.29",
            "GLIBC_2.4",
            "GLIBC_2.7",
        ],
    },
}
CAVEAT_TOKENS = (
    "31 C++ and 16 C compiles",
    "GLIBCXX_3.4.29",
    "GPLv2",
    "gb_bios.bin",
    "ra32-mini-v0",
    "ra32-universal-v0",
)
FAILURE_MARKERS = ("warning:", "error:", "fatal:", "dubious")


class GambatteCoreEvidenceTests(unittest.TestCase):
    def test_individual_pin_and_compatibility_bind_promoted_evidence(self) -> None:
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
        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])
        self.assertNotIn("tranche", compatibility["golden_source"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["e2e"]["package_sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            selection["e2e"]["content_sha256"],
            compatibility["selected_e2e_content_sha256"],
        )
        reproduction = load_document(
            ROOT / ".local-e2e" / "runs" / REPRODUCTION_RUN / "e2e-record.json"
        )
        self.assertEqual(
            reproduction["content_sha256"],
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

        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden_record = selected_target["golden_record"]
                artifact = golden_record["artifact"]

                self.assertEqual(CORE_ID, golden_record["core_id"])
                self.assertEqual(SOURCE_COMMIT, golden_record["source"]["commit"])
                self.assertEqual(SOURCE_TREE, golden_record["source"]["tree"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], selected_target["artifact"]["sha256"]
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
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

    def test_individual_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
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
                    "ra64-universal-v1"
                    if architecture == "arm64"
                    else "ra32-a30-v1",
                    cell["execution_profile_id"],
                )
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_individual_channels_target_semantic_artifacts(self) -> None:
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
                self.assertEqual(channel, pointer["channel"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", pointer["target"]["path"])

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

    def test_selected_and_reproduction_runs_prove_exact_mixed_builds(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence = load_document(run_root / "e2e-record.json")
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    [CORE_ID],
                    [item["core_id"] for item in evidence["packages"]],
                )
                package = evidence["packages"][0]
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())

                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        record_path = (
                            run_root / CORE_ID / architecture / "build-record.json"
                        )
                        record = load_document(record_path)
                        log_path = record_path.parent / record["build"]["log"]
                        log_text = log_path.read_text(encoding="utf-8")
                        self.assertEqual(SOURCE_COMMIT, record["source"]["commit"])
                        self.assertEqual(SOURCE_TREE, record["source"]["tree"])
                        self.assertEqual(
                            {
                                "compiler_scope": "cxx",
                                "derivation": "native-space-short7-v1",
                                "value": " dfc1655",
                            },
                            record["build"]["git_version"],
                        )
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                log_text,
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
                            )
                        )
                        lowered_log = log_text.lower()
                        for marker in FAILURE_MARKERS:
                            self.assertNotIn(marker, lowered_log)
                        compile_line = next(
                            line
                            for line in log_text.splitlines()
                            if "g++" in line and " -c " in line
                        )
                        self.assertFalse(
                            pipeline.registered_core_log_contract_proves(
                                log_text + "\n" + compile_line + "\n",
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
                            )
                        )

                        metadata_path = (
                            record_path.parent / record["metadata"]["path"]
                        )
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata_payloads.append(metadata_path.read_bytes())

                        artifact_path = (
                            record_path.parent / record["artifact"]["path"]
                        )
                        self.assertEqual(
                            expected["artifact_sha256"],
                            file_sha256(artifact_path),
                        )
                        artifacts[architecture].append(artifact_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture, payloads in artifacts.items():
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(payloads[0], payloads[1])


if __name__ == "__main__":
    unittest.main()
