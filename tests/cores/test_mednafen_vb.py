"""Pinned Mednafen Virtual Boy individual lifecycle tests."""

from __future__ import annotations

import copy
from collections import Counter
import unittest
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import mednafen_vb
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


CORE_ID = "mednafen_vb"
OTHER_CORE_ID = "mednafen_pcfx"

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

SOURCE_URL = _H["SOURCE_URL"]

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
    "13 compiles (10 C and 3 C++)",
    "v1.31.0 38e7a0e",
    "ARM64 contains no warnings",
    "two reviewed GCC 7.1 psABI notes",
    "GPLv2",
    "vb|vboy|bin",
    "no external firmware",
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

class MednafenVbCoreEvidenceTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)


    def test_singleton_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, report["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock = load_document(ROOT / source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(SOURCE_LOCK_IDENTITY, source_lock["source"])
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
            ".local-e2e/runs/nonexistent-mednafen-vb/e2e-record.json"
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
        pin_mutations["semantic_id"]["pin_id"] = "mednafen_vb-nonsemantic-pin"
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
                prefix=f"compat-tamper-vb-{mutation}-",
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

    def test_reproduction_tolerates_reorder_but_rejects_content_drift(self) -> None:
        # Parallel make interleaves complete diagnostic lines differently per
        # -j level and host, so a multiset-preserving reorder must PROVE; a
        # content change to any diagnostic line must still fail closed.
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-reorder-vb-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "armhf" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_text = log_path.read_text(encoding="utf-8")
            diagnostic_block = (
                "\n".join(mednafen_vb.MEDNAFEN_VB_ARMHF_DIAGNOSTIC_CONTEXT)
                + "\n"
            )
            diagnostic_lines = diagnostic_block.splitlines(keepends=True)
            reordered_block = "".join(
                (diagnostic_lines[1], diagnostic_lines[0], *diagnostic_lines[2:])
            )
            reordered_log = log_text.replace(diagnostic_block, reordered_block, 1)
            self.assertNotEqual(log_text, reordered_log)
            self.assertEqual(
                Counter(log_text.splitlines(keepends=True)),
                Counter(reordered_log.splitlines(keepends=True)),
            )
            self.assertTrue(
                mednafen_vb.mednafen_vb_log_proves_contract(
                    reordered_log,
                    CORE_ID,
                    "armhf",
                    SOURCE_COMMIT,
                    SOURCE_TREE,
                )
            )
            drifted_line = diagnostic_lines[0].replace(
                "vector:72", "vector:73", 1
            )
            self.assertNotEqual(drifted_line, diagnostic_lines[0])
            drifted_log = log_text.replace(
                diagnostic_lines[0], drifted_line, 1
            )
            self.assertFalse(
                mednafen_vb.mednafen_vb_log_proves_contract(
                    drifted_log,
                    CORE_ID,
                    "armhf",
                    SOURCE_COMMIT,
                    SOURCE_TREE,
                )
            )
            log_path.write_text(drifted_log, encoding="utf-8")
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)

            mutated = copy.deepcopy(compatibility)
            mutated["reproduction_run"] = (
                f".local-e2e/runs/{run_root.name}/e2e-record.json"
            )
            mutated["reproduction_e2e_content_sha256"] = evidence["content_sha256"]
            mutated["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(mutated)
            )
            report = pipeline.validate_core_compatibility_document(
                mutated,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertEqual("invalid", report["status"])
            registered_contract = pipeline.core_log_contract_for(CORE_ID)
            self.assertIsNotNone(registered_contract)
            assert registered_contract is not None
            # Content drift changes the log multiset, so validation may fail
            # at the reproduction-comparison gate before the contract proof
            # reruns; either rejection is the fail-closed outcome.
            self.assertTrue(
                any(
                    registered_contract.failure_message in error
                    or "historical build differs" in error
                    for error in report["errors"]
                ),
                report["errors"],
            )


if __name__ == "__main__":
    unittest.main()
