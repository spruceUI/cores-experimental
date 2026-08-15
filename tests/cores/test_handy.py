"""Handy reviewed pins, lifecycle behaviors, and negative controls.

Promotion-derived bindings are covered for every core by
``tests/test_evidence_bindings.py`` against ``pins/evidence/handy.json``;
this file keeps the reviewed caveat tokens plus the lifecycle and
fail-closed behaviors the parametric gate does not exercise.
"""

from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

from .support import pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.records import compatibility as compatibility_records

from .support import (
    ROOT,
    copied_e2e_run,
    evidence_handles,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "handy"
OTHER_CORE_ID = "stella2014"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
TARGETS = _H["TARGETS"]

# Reviewed caveat tokens the promoted compatibility document must retain.
CAVEAT_TOKENS = (
    "13 C and 12 C++",
    "Handy 0.97",
    "version 0.95",
    "LGPL-2.1-or-later",
    "ra32-universal-v0 candidate",
)


class HandyCoreEvidenceTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)

    def test_individual_source_set_maps_build_profiles_without_device_claims(
        self,
    ) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(PIN_NAME.removesuffix(".json"), report["source_set_id"])
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

    def test_compatibility_validator_fails_closed_on_malformed_evidence(
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

        bool_schema = copy.deepcopy(compatibility)
        bool_schema["schema_version"] = True
        bool_schema["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(bool_schema)
        )
        schema_report = pipeline.validate_core_compatibility_document(
            bool_schema,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", schema_report["status"])
        self.assertIn(
            "core compatibility schema_version must be 1",
            schema_report["errors"],
        )

        non_string_artifact = copy.deepcopy(compatibility)
        non_string_artifact["targets"]["arm64"]["artifact_sha256"] = 7
        non_string_artifact["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(non_string_artifact)
        )
        artifact_report = pipeline.validate_core_compatibility_document(
            non_string_artifact,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", artifact_report["status"])
        self.assertIn(
            f"{CORE_ID}/arm64: artifact digest is invalid",
            artifact_report["errors"],
        )

        arbitrary_elf = copy.deepcopy(compatibility)
        arbitrary_elf["targets"]["arm64"]["elf"] = "ELF64/arbitrary"
        arbitrary_elf["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(arbitrary_elf)
        )
        elf_report = pipeline.validate_core_compatibility_document(
            arbitrary_elf,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", elf_report["status"])
        self.assertIn(
            f"{CORE_ID}/arm64: ELF label is invalid",
            elf_report["errors"],
        )

        non_object_target = copy.deepcopy(compatibility)
        non_object_target["targets"]["arm64"] = []
        non_object_target["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(non_object_target)
        )
        target_report = pipeline.validate_core_compatibility_document(
            non_object_target,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", target_report["status"])
        self.assertIn(
            f"{CORE_ID}/arm64: compatibility target is invalid",
            target_report["errors"],
        )

        missing_reproduction = copy.deepcopy(compatibility)
        missing_reproduction["reproduction_run"] = (
            ".local-e2e/runs/nonexistent-handy-reproduction/e2e-record.json"
        )
        missing_reproduction["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(missing_reproduction)
        )
        reproduction_report = pipeline.validate_core_compatibility_document(
            missing_reproduction,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", reproduction_report["status"])
        self.assertIn(
            "individual core reproduction E2E record is unavailable",
            reproduction_report["errors"],
        )

        swapped_runs = copy.deepcopy(compatibility)
        swapped_runs["e2e_run"], swapped_runs["reproduction_run"] = (
            swapped_runs["reproduction_run"],
            swapped_runs["e2e_run"],
        )
        swapped_runs["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(swapped_runs)
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
        self.assertIn(
            "individual core selected E2E content differs from pin",
            swapped_report["errors"],
        )

        malformed_pins = {
            "selection": copy.deepcopy(pin),
            "targets": copy.deepcopy(pin),
        }
        malformed_pins["selection"]["cores"][CORE_ID]["selection"] = []
        malformed_pins["targets"]["cores"][CORE_ID]["selection"][
            "targets"
        ] = []
        expected_errors = {
            "selection": "individual core pin selection is invalid",
            "targets": "individual core pin targets are invalid",
        }
        for label, malformed_pin in malformed_pins.items():
            with self.subTest(malformed_pin=label), mock.patch.object(
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
                self.assertIn(expected_errors[label], pin_report["errors"])

        pin_mutations = {
            "digest": copy.deepcopy(pin),
            "parent": copy.deepcopy(pin),
            "semantic_id": copy.deepcopy(pin),
            "source_reference": copy.deepcopy(pin),
        }
        pin_mutations["digest"]["content_sha256"] = "0" * 64
        pin_mutations["parent"]["parent"] = {
            "path": PIN_PATH,
            "file_sha256": pipeline.sha256_file(ROOT / PIN_PATH),
            "content_sha256": pin["content_sha256"],
            "pin_id": pin["pin_id"],
        }
        pin_mutations["parent"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["parent"])
        )
        pin_mutations["semantic_id"]["pin_id"] = "handy-nonsemantic-pin"
        pin_mutations["semantic_id"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["semantic_id"])
        )
        pin_mutations["source_reference"]["sources"][0]["file_sha256"] = (
            "0" * 64
        )
        pin_mutations["source_reference"]["content_sha256"] = (
            pipeline.pin_set_content_sha256(pin_mutations["source_reference"])
        )
        expected_pin_errors = {
            "digest": "individual core pin: pin-set content digest is invalid",
            "parent": "individual core pin parent must be null",
            "semantic_id": "individual core pin ID is not semantic",
            "source_reference": "individual core pin: source 0 no longer matches the pin",
        }
        for label, malformed_pin in pin_mutations.items():
            with self.subTest(pin_contract=label), mock.patch.object(
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

    def test_runner_roles_and_reproduction_digest_are_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        wrong_reproduction_digest = copy.deepcopy(compatibility)
        wrong_reproduction_digest["reproduction_e2e_content_sha256"] = "0" * 64
        wrong_reproduction_digest["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(
                wrong_reproduction_digest
            )
        )
        digest_report = pipeline.validate_core_compatibility_document(
            wrong_reproduction_digest,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertIn(
            "individual core reproduction E2E content differs from compatibility",
            digest_report["errors"],
        )

        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-recomputed-reproduction-handy-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            evidence["started_at"] = "tampered-but-internally-recomputed"
            refresh_copied_e2e(
                run_root,
                evidence,
                pipeline.e2e_content_sha256,
            )
            recomputed_reproduction = copy.deepcopy(compatibility)
            recomputed_reproduction["reproduction_run"] = str(
                (run_root / "e2e-record.json").relative_to(ROOT)
            )
            recomputed_reproduction["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(
                    recomputed_reproduction
                )
            )
            recomputed_report = pipeline.validate_core_compatibility_document(
                recomputed_reproduction,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertIn(
                "individual core reproduction E2E content differs from compatibility",
                recomputed_report["errors"],
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

        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-wrong-runner-handy-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            evidence["runner"] = {
                "profile": "github-actions",
                "mode": "native",
                "backend": "github-hosted-docker",
                "local_only": True,
                "publication": "disabled",
            }
            refresh_copied_e2e(
                run_root,
                evidence,
                pipeline.e2e_content_sha256,
            )
            wrong_runner = copy.deepcopy(compatibility)
            wrong_runner["reproduction_run"] = str(
                (run_root / "e2e-record.json").relative_to(ROOT)
            )
            wrong_runner["reproduction_e2e_content_sha256"] = evidence[
                "content_sha256"
            ]
            wrong_runner["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(wrong_runner)
            )
            runner_report = pipeline.validate_core_compatibility_document(
                wrong_runner,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertIn(
                "individual core reproduction E2E runner profile is invalid",
                runner_report["errors"],
            )

        with copied_e2e_run(
            SELECTED_RUN,
            prefix="compat-copied-selected-handy-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            copied_selected = copy.deepcopy(compatibility)
            copied_selected["reproduction_run"] = str(
                (run_root / "e2e-record.json").relative_to(ROOT)
            )
            copied_selected["reproduction_e2e_content_sha256"] = evidence[
                "content_sha256"
            ]
            copied_selected["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(copied_selected)
            )
            copied_report = pipeline.validate_core_compatibility_document(
                copied_selected,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertIn(
                "individual core reproduction E2E runner profile is invalid",
                copied_report["errors"],
            )

    def test_historical_reproduction_separates_log_identity_from_record_tampering(
        self,
    ) -> None:
        _, pin, _, _ = load_core_documents(CORE_ID, PIN_NAME)
        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        mutations = {
            "log": None,
            "build": "historical build differs",
            "recipe": "historical recipe differs",
            "source": "historical source differs",
            "toolchain": "historical toolchain differs",
            "record_fields": "build record fields are invalid",
        }
        for mutation, expected_error in mutations.items():
            with self.subTest(mutation=mutation), copied_e2e_run(
                REPRODUCTION_RUN,
                prefix=f"compat-tamper-handy-{mutation}-",
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
                if expected_error is None:
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )
                    continue
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    expected_error,
                ):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )

    def test_compatibility_consumes_digest_bound_snapshots_after_path_swap(
        self,
    ) -> None:
        _, pin, _, _ = load_core_documents(CORE_ID, PIN_NAME)
        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        for asset in ("build-record", "build-log", "package"):
            with self.subTest(asset=asset), copied_e2e_run(
                REPRODUCTION_RUN,
                prefix=f"compat-snapshot-handy-{asset}-",
                content_hasher=pipeline.e2e_content_sha256,
            ) as (run_root, evidence):
                record_path = run_root / CORE_ID / "arm64" / "build-record.json"
                record = load_document(record_path)
                targets = {
                    "build-record": (record_path, b"{}"),
                    "build-log": (
                        record_path.parent / record["build"]["log"],
                        b"tampered build log\n",
                    ),
                    "package": (
                        run_root / evidence["packages"][0]["path"],
                        b"not a zip archive",
                    ),
                }
                target_path, replacement_bytes = targets[asset]
                target_reads: list[Path] = []
                target_hashes: list[Path] = []
                original_read_bytes = Path.read_bytes
                original_sha256_file = compatibility_records.sha256_file

                def swap_after_read(path: Path) -> bytes:
                    snapshot = original_read_bytes(path)
                    if path == target_path:
                        target_reads.append(path)
                        target_path.write_bytes(replacement_bytes)
                    return snapshot

                def swap_after_hash(path: Path) -> str:
                    digest = original_sha256_file(path)
                    if path == target_path:
                        target_hashes.append(path)
                        target_path.write_bytes(replacement_bytes)
                    return digest

                with mock.patch.object(
                    Path,
                    "read_bytes",
                    autospec=True,
                    side_effect=swap_after_read,
                ), mock.patch.object(
                    compatibility_records,
                    "sha256_file",
                    side_effect=swap_after_hash,
                ):
                    pipeline._validate_compatibility_e2e_run(
                        run_root / "e2e-record.json",
                        CORE_ID,
                        expected_targets,
                    )

                self.assertEqual([target_path], target_reads)
                self.assertEqual([], target_hashes)


if __name__ == "__main__":
    unittest.main()
