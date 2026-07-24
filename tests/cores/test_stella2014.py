"""Pinned Stella 2014 build-evidence tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "stella2014"
OTHER_CORE_ID = "handy"
PIN_NAME = "stella2014-4a7da82595d2-1fb14ddbab91.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "4a7da82595d27b8df7af1ecb467a64b642a41bc9"
SOURCE_TREE = "25eb55b1241824f7003eb3006847870672bbe4b2"
SOURCE_LOCK_ID = "stella2014-4a7da82595d2"
SELECTION_SHA256 = (
    "1fb14ddbab91484db499c109b6fb90aad2a29d65ab6ca7f86ec1b13cf4c0e8e2"
)
SELECTED_RUN = "actions-sim-build-core-stella2014-v1"
REPRODUCTION_RUN = "build-core-stella2014-local-v1"
PACKAGE_SHA256 = (
    "883c091e516ede7491e0533e86217fbcaf4543a864424e3423578daf50c92c9e"
)
TARGETS = {
    "arm64": {
        "artifact_sha256": (
            "7684f873cb6c1c87c36b9dfc05af2287e89735c52d892b8200601a4ace6df743"
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
            "GLIBCXX_3.4.9",
            "GLIBC_2.17",
        ],
    },
    "armhf": {
        "artifact_sha256": (
            "598ac496335c64a2ad426a4b0b8349cf10013dccf7e954ebf72e221b675f256f"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": [
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "CXXABI_1.3.8",
            "CXXABI_1.3.9",
            "CXXABI_ARM_1.3.3",
            "GCC_3.5",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.32",
            "GLIBCXX_3.4.9",
            "GLIBC_2.4",
            "GLIBC_2.7",
        ],
    },
}
CAVEAT_TOKENS = (
    "14 C and 84 C++",
    "a26|bin",
    "mvc",
    "GPLv2",
    "GLIBCXX_3.4.32",
)


class Stella2014CoreEvidenceTests(unittest.TestCase):
    def test_individual_pin_and_compatibility_bind_promoted_evidence(self) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        report = pipeline.validate_pin_set_document(pin, document_path=pin_path)
        self.assertEqual("valid", report["status"], report["errors"])
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
        self.assertEqual(
            load_document(
                ROOT
                / ".local-e2e"
                / "runs"
                / REPRODUCTION_RUN
                / "e2e-record.json"
            )["content_sha256"],
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
        ):
            self.assertNotIn("tranche", active_reference.lower())

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
                self.assertEqual(
                    "needs-target-runtime", target["runtime_validation"]
                )
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

    def test_fresh_selected_and_reproduction_runs_are_byte_identical(
        self,
    ) -> None:
        selected_root = ROOT / ".local-e2e" / "runs" / SELECTED_RUN
        reproduction_root = ROOT / ".local-e2e" / "runs" / REPRODUCTION_RUN
        compared_paths = ["stella2014_libretro.zip"]
        for architecture in TARGETS:
            compared_paths.extend(
                f"{CORE_ID}/{architecture}/{name}"
                for name in (
                    "build.log",
                    "stella2014_libretro.info",
                    "stella2014_libretro.so",
                )
            )

        for relative_path in compared_paths:
            with self.subTest(path=relative_path):
                selected_path = selected_root / relative_path
                reproduction_path = reproduction_root / relative_path
                self.assertTrue(selected_path.is_file())
                self.assertTrue(reproduction_path.is_file())
                self.assertEqual(
                    file_sha256(selected_path),
                    file_sha256(reproduction_path),
                )

    def test_individual_source_set_maps_build_profiles_without_device_claims(
        self,
    ) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertNotIn("tranche", source_set["evidence_pin"]["path"].lower())
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock = load_document(ROOT / source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual([], source_lock["source"]["submodules"])
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
                self.assertEqual(
                    expected["artifact_sha256"], cell["artifact_sha256"]
                )
                self.assertEqual(
                    (
                        "ra64-universal-v1"
                        if architecture == "arm64"
                        else "ra32-a30-v1"
                    ),
                    cell["execution_profile_id"],
                )
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_individual_channel_lifecycle_targets_semantic_artifacts(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": (
                f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json"
            ),
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer_path = (
                    ROOT
                    / ".local-e2e"
                    / "channels"
                    / f"{channel}.{CORE_ID}.json"
                )
                pointer = load_document(pointer_path)
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

                mutated_pointer = {**pointer, "core_id": OTHER_CORE_ID}
                mutated_report = pipeline.validate_channel_pointer_document(
                    mutated_pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", mutated_report["status"])
                self.assertIn(
                    "channel pointer document does not match its core alias filename",
                    mutated_report["errors"],
                )

                other_core_report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", other_core_report["status"])
                self.assertIn(
                    "channel pointer document does not match its core alias filename",
                    other_core_report["errors"],
                )

    def test_reproduction_rejects_recomputed_record_tampering(
        self,
    ) -> None:
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
                prefix=f"compat-tamper-stella-{mutation}-",
                content_hasher=pipeline.e2e_content_sha256,
            ) as (run_root, evidence):
                record_path = (
                    run_root / CORE_ID / "arm64" / "build-record.json"
                )
                record = load_document(record_path)
                if mutation == "log":
                    log_path = record_path.parent / record["build"]["log"]
                    log_path.write_text(
                        log_path.read_text(encoding="utf-8") + "tampered\n",
                        encoding="utf-8",
                    )
                    record["build"]["log_sha256"] = file_sha256(log_path)
                elif mutation == "build":
                    record["build"]["environment"] = "tampered-v1"
                elif mutation == "recipe":
                    record["recipe"]["repository_dirty"] = not record[
                        "recipe"
                    ]["repository_dirty"]
                elif mutation == "source":
                    record["source"]["resolved_url"] = (
                        "https://example.invalid/tampered.git"
                    )
                elif mutation == "toolchain":
                    record["toolchain"]["compiler"] += " tampered"
                else:
                    record["unexpected"] = True
                write_document(record_path, record)
                refresh_copied_e2e(
                    run_root,
                    evidence,
                    pipeline.e2e_content_sha256,
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    expected_error,
                ):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )


if __name__ == "__main__":
    unittest.main()
