"""EightyOne reviewed pins, lifecycle behaviors, and negative controls.

Promotion-derived bindings (digests, run ids, sizes, byte reproduction,
proof execution) are covered for every core by
``tests/test_evidence_bindings.py`` against the generated
``pins/evidence/81.json``; this file keeps only what a reviewer decided:
the caveat tokens, the generated-source contract, the resolver metadata
expectations, and the fail-closed negative controls — plus the
channel/registry lifecycle behaviors the parametric gate does not touch.
"""

from __future__ import annotations

import copy
import unittest

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import core_81

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "81"
OTHER_CORE_ID = "a5200"

_INDEX = load_document(ROOT / "pins" / "evidence" / f"{CORE_ID}.json")
_CATALOG_SPEC = load_document(ROOT / "manifests" / "core-builds.json")[
    "cores"
][CORE_ID]

SEMANTIC_ID = _INDEX["semantic_id"]
PIN_NAME = f"{SEMANTIC_ID}.json"
PIN_PATH = _INDEX["pin_path"]
SOURCE_SET_PATH = _INDEX["source_set_path"]
SOURCE_COMMIT = _CATALOG_SPEC["source"]["commit"]
SOURCE_TREE = _CATALOG_SPEC["source"]["tree"]
SOURCE_LOCK_ID = f"{CORE_ID}-{SOURCE_COMMIT[:12]}"
PACKAGE_SHA256 = _INDEX["package"]["sha256"]
SELECTED_RUN = _INDEX["runs"]["selected"]["run_id"]
REPRODUCTION_RUN = _INDEX["runs"]["reproduction"]["run_id"]
TARGETS = _INDEX["targets"]

# Reviewed pin: upstream Make generates src/version.c from the pinned
# commit; the pipeline verifies this exact digest and never injects
# GIT_VERSION or patches the source.
GENERATED_SOURCE_SHA256 = (
    "5a07d38a3bcd84ee5fa9abbdbe0bd706288d8ec4ee8095485447e35dc28a2862"
)

# Reviewed caveat tokens the promoted compatibility document must retain.
CAVEAT_TOKENS = (
    "semantic at the log layer",
    "actions-sim-build-core-81-v1",
    "src/version.c",
    "39 reviewed warnings and 6 notes",
    "38 reviewed warnings and 11 notes",
    "unescaped inner quotes",
    "compiled zx81 and dkchr ROM headers",
    "GLIBCXX_3.4.20",
    "CXXABI_1.3.9",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "every device view remains ineligible",
)

# Reviewed resolver metadata expectations for the copied .info text.
METADATA_TOKENS = (
    'display_version = "1.0a"',
    'supported_extensions = "p|tzx|t81"',
    'savestate = "true"',
    'libretro_saves = "false"',
    'supports_no_game = "false"',
    'in the "p" and "tzx" formats',
)


class Core81ReviewedPinTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)

    def test_records_bind_the_reviewed_generated_source(self) -> None:
        for run in _INDEX["runs"].values():
            for architecture in TARGETS:
                record = load_document(
                    ROOT
                    / ".local-e2e/runs"
                    / run["run_id"]
                    / CORE_ID
                    / architecture
                    / "build-record.json"
                )
                self.assertEqual(
                    {
                        "kind": "post-build-sha256-v1",
                        "path": "src/version.c",
                        "sha256": GENERATED_SOURCE_SHA256,
                    },
                    record["build"]["generated_source"],
                )

    def test_metadata_carries_the_reviewed_resolver_expectations(self) -> None:
        record = load_document(
            ROOT
            / ".local-e2e/runs"
            / SELECTED_RUN
            / CORE_ID
            / "arm64"
            / "build-record.json"
        )
        metadata_path = (
            ROOT
            / ".local-e2e/runs"
            / SELECTED_RUN
            / CORE_ID
            / "arm64"
            / record["metadata"]["path"]
        )
        metadata = metadata_path.read_text(encoding="utf-8")
        for token in METADATA_TOKENS:
            self.assertIn(token, metadata)


class Core81LifecycleTests(unittest.TestCase):
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
                self.assertEqual(
                    expected["artifact_sha256"], cell["artifact_sha256"]
                )
                self.assertEqual(
                    registry.PROFILE_BINDING[architecture],
                    cell["execution_profile_id"],
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
        self.assertEqual(
            [CORE_ID], [asset["core_id"] for asset in release["assets"]]
        )
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

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(
            core_81.core_81_spec_is_well_formed(catalog["cores"][CORE_ID])
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/81.json").exists()
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
