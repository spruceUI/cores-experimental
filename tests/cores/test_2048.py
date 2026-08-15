"""2048 individual lifecycle and reproducibility tests."""

from __future__ import annotations

import copy
import unittest
import zipfile

from .support import pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import core_2048

from .support import ROOT, file_sha256, load_core_documents, load_document
from .support import evidence_handles


CORE_ID = "2048"
OTHER_CORE_ID = "a5200"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
PACKAGE_SHA256 = _H["PACKAGE_SHA256"]
TARGETS = _H["TARGETS"]

CAVEAT_TOKENS = (
    "16-source C-only compile",
    "eight commits newer",
    "Unlicense/Public Domain",
    "libretro_saves=false",
    "RETRO_MEMORY_SAVE_RAM",
    "expected silence/no-audio initialization behavior",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)
TUNED_CONTRACT_FIXTURE = ROOT / "tests/fixtures/2048-a523-tuned-contract.log"
TUNED_CONTRACT_FIXTURE_SHA256 = (
    "560c2413778cc0d074a56161cee1efbba90ebe2327541c3d761e6e42bc42b27c"
)


class Core2048LifecycleTests(unittest.TestCase):
    def test_typed_tuning_composes_with_exact_compile_link_contract(self) -> None:
        self.assertEqual(
            TUNED_CONTRACT_FIXTURE_SHA256,
            file_sha256(TUNED_CONTRACT_FIXTURE),
        )
        log = TUNED_CONTRACT_FIXTURE.read_text(encoding="utf-8")
        tuning = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )["profile"]
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(log, tuning, "arm64")
        )
        self.assertFalse(
            pipeline._registered_core_log_contract_proves(
                log,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )
        self.assertTrue(
            pipeline._registered_core_log_contract_proves(
                log,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
                tuning=tuning,
            )
        )

        first_compile = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-gcc -mcpu=") and " -c " in line
        )
        mutations = {
            "compile-count": log.replace(first_compile + "\n", "", 1),
            "version": log.replace("c90437d", "0000000"),
            "link": log.replace("-Wl,--no-undefined", "-Wl,--version-script=x", 1),
            "diagnostic": log + "fatal: synthetic failure\n",
            "conflicting-machine": log.replace(
                "-mcpu=cortex-a55", "-mcpu=cortex-a53", 1
            ),
            "duplicate-machine": log.replace(
                "-mcpu=cortex-a55", "-mcpu=cortex-a55 -mcpu=cortex-a55", 1
            ),
        }
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    pipeline._registered_core_log_contract_proves(
                        changed,
                        CORE_ID,
                        "arm64",
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                        tuning=tuning,
                    )
                )

    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)


    def test_source_set_maps_shared_profiles_without_device_claims(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests/core-builds.json")["cores"]
        )

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
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
                self.assertEqual("static-build-only", cell["validation_scope"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

    def test_channels_and_release_target_one_semantic_core(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT / ".local-e2e/channels" / f"{channel}.{CORE_ID}.json"
                )
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
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
        release_root = ROOT / ".local-e2e/releases" / SEMANTIC_ID
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
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])


    def test_compatibility_and_registered_proof_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
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
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        changed_artifact = copy.deepcopy(compatibility)
        changed_artifact["targets"]["arm64"]["artifact_sha256"] = "0" * 64
        changed_artifact["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(changed_artifact)
        )
        changed_report = pipeline.validate_core_compatibility_document(
            changed_artifact,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", changed_report["status"])

        log_path = (
            ROOT / ".local-e2e/runs" / REPRODUCTION_RUN / CORE_ID / "arm64/build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        self.assertFalse(
            pipeline.registered_core_log_contract_proves(
                log_text.replace("-Wl,--no-undefined", "-Wl,--version-script=link.T", 1),
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(
            core_2048.core_2048_spec_is_well_formed(catalog["cores"][CORE_ID])
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/2048.json").exists()
        )
        coverage = pipeline.load_catalog_compatibility_coverage(
            catalog=catalog,
            repository_root=ROOT,
        )
        self.assertNotIn(CORE_ID, coverage["pending_compatibility_cores"])
        self.assertEqual(
            len(catalog["cores"]),
            coverage["compatibility_coverage_core_count"]
            + coverage["pending_compatibility_core_count"],
        )


if __name__ == "__main__":
    unittest.main()
