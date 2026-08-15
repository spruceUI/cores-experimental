"""Pinned Genesis Plus GX Wide build-evidence and lifecycle tests."""

from __future__ import annotations

import copy
import json
import unittest
from collections import Counter
from unittest import mock
import zipfile

from .support import pipeline
from scripts import profile_registry as registry
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
from .support import evidence_handles


CORE_ID = "genesis_plus_gx_wide"
OTHER_CORE_ID = "genesis_plus_gx"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
PIN_FILE_SHA256 = _H["PIN_FILE_SHA256"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
PACKAGE_SHA256 = _H["PACKAGE_SHA256"]
TARGETS = _H["TARGETS"]

SOURCE_LOCK_PATH = _H["SOURCE_LOCK_PATH"]

SOURCE_URL = _H["SOURCE_URL"]

SOURCE_LOCK_FILE_SHA256 = _H["SOURCE_LOCK_FILE_SHA256"]

SOURCE_LOCK_CONTENT_SHA256 = _H["SOURCE_LOCK_CONTENT_SHA256"]

SOURCE_SET_FILE_SHA256 = _H["SOURCE_SET_FILE_SHA256"]

SOURCE_SET_CONTENT_SHA256 = _H["SOURCE_SET_CONTENT_SHA256"]

PIPELINE_BUNDLE_SHA256 = _H["PIPELINE_BUNDLE_SHA256"]

REPOSITORY_HEAD = _H["REPOSITORY_HEAD"]

NATIVE_GIT_VERSION = " 29d9d10"

BASE_SOURCE_COMMIT = "fa4dca561e08d5be9077419f7b255e1da213ed21"

BASE_SOURCE_TREE = "7f4b0916e938e15e046e1c35acd0173aab1aaac3"

BASE_SELECTED_RUN = "actions-sim-build-core-genesis_plus_gx-w3"

SOURCE_RECORD_IDENTITY = {
    "commit": SOURCE_COMMIT,
    "requested_ref": "refs/heads/main",
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
    "tree": SOURCE_TREE,
    "url": SOURCE_URL,
}

CAVEAT_TOKENS = (
    "both build logs byte for byte",
    "106 C compile commands",
    "two reviewed warnings and one note",
    "genesis_plus_gx_wide_*",
    "GENPLUS-GX 1.7.6",
    "GENPLUS-GX 1.7.7",
    "Base-to-Wide",
    "Non-commercial",
    "corresponding source",
    "human legal and policy gate",
    "no offline source bundle",
    "dockerfile_linkage=unverified-local-cache",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "TRIMUI_SMART_PRO",
    "all device views remain ineligible",
)

class GenesisPlusGxWideCoreEvidenceTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)


    def test_source_set_release_and_channels_are_core_owned(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))

        source = source_set["sources"][CORE_ID]
        source_lock = registry.composed_source_lock(CORE_ID)
        self.assertEqual(SOURCE_LOCK_PATH, source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, source["file_sha256"])
        self.assertEqual(SOURCE_LOCK_CONTENT_SHA256, source["content_sha256"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/main",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
                "submodules": [],
            },
            source_lock["source"],
        )

        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
        cells = {cell["architecture"]: cell for cell in report["build_evidence_cells"]}
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            self.assertEqual(
                expected["artifact_sha256"], cells[architecture]["artifact_sha256"]
            )
            self.assertEqual(
                expected["execution_profile_id"],
                cells[architecture]["execution_profile_id"],
            )
        self.assertEqual(8, len(report["device_views"]))
        self.assertTrue(
            all(
                view["status"] == "provisional"
                and view["eligibility"] == "provisional-unverified"
                and not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            pointer = load_document(
                ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
            )
            pointer_report = pipeline.validate_channel_pointer_document(
                pointer, expected_channel=channel, expected_core=CORE_ID
            )
            self.assertEqual(
                "valid", pointer_report["status"], pointer_report["errors"]
            )
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
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

        nightly = load_document(
            ROOT / ".local-e2e" / "nightlies" / SEMANTIC_ID / "golden.json"
        )
        imported = nightly["cores"][CORE_ID]["artifacts"]
        self.assertEqual(
            "96eb5e2771e03ae3c867b31db8d8413e951c2dff4e3fb4b7ac8b1749b3f44742",
            imported["arm64"]["sha256"],
        )
        self.assertEqual(11534200, imported["arm64"]["size"])
        self.assertEqual({"status": "not_shipped"}, imported["armhf"])


    def test_fresh_base_and_wide_logs_are_reciprocally_rejected(self) -> None:
        for architecture in TARGETS:
            wide_log = (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / CORE_ID
                / architecture
                / "build.log"
            ).read_text(encoding="utf-8")
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    wide_log, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
                )
            )
            self.assertFalse(
                pipeline.registered_core_log_contract_proves(
                    wide_log,
                    OTHER_CORE_ID,
                    architecture,
                    BASE_SOURCE_COMMIT,
                    BASE_SOURCE_TREE,
                )
            )

            base_log = (
                ROOT
                / ".local-e2e"
                / "runs"
                / BASE_SELECTED_RUN
                / OTHER_CORE_ID
                / architecture
                / "build.log"
            ).read_text(encoding="utf-8")
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    base_log,
                    OTHER_CORE_ID,
                    architecture,
                    BASE_SOURCE_COMMIT,
                    BASE_SOURCE_TREE,
                )
            )
            self.assertFalse(
                pipeline.registered_core_log_contract_proves(
                    base_log, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
                )
            )

    def test_manifest_pin_source_set_and_reproduction_tampering_fail_closed(
        self,
    ) -> None:
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
            "core compatibility content digest is invalid",
            digest_report["errors"],
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
            same_run, document_path=compatibility_path, repository_root=ROOT
        )
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        malformed_pin = copy.deepcopy(pin)
        malformed_pin["sources"][0]["file_sha256"] = "0" * 64
        malformed_pin["content_sha256"] = pipeline.pin_set_content_sha256(malformed_pin)
        with mock.patch.object(
            compatibility_records, "load_json", return_value=malformed_pin
        ):
            pin_report = pipeline.validate_core_compatibility_document(
                compatibility,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
        self.assertEqual("invalid", pin_report["status"])
        self.assertIn(
            "individual core pin: source 0 no longer matches the pin",
            pin_report["errors"],
        )

        malformed_source_set = registry.composed_source_set(SEMANTIC_ID)
        malformed_source_set["sources"][CORE_ID]["commit"] = "0" * 40
        with self.assertRaisesRegex(
            registry.RegistryError,
            "source set reference path does not bind genesis_plus_gx_wide",
        ):
            registry.validate_source_set(malformed_source_set)

        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-genesis-plus-gx-wide-log-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_path.write_text(
                log_path.read_text(encoding="utf-8") + "warning: synthetic\n",
                encoding="utf-8",
            )
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)
            with self.assertRaisesRegex(
                pipeline.PipelineError, "build log does not prove"
            ):
                pipeline._validate_compatibility_e2e_run(
                    run_root / "e2e-record.json", CORE_ID, expected_targets
                )


if __name__ == "__main__":
    unittest.main()
