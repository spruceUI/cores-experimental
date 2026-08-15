from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import FrozenInstanceError, replace
import json
import unittest
from unittest import mock

from scripts.core_pipeline_lib.campaign import transition
from scripts.core_pipeline_lib.campaign.json_wire import rendered_json_bytes
from scripts.core_pipeline_lib.campaign.legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
    render_matrix_v2,
)
from scripts.core_pipeline_lib.campaign.model import (
    MATRIX_AUTHORITY_ALLOWED_CHANGES,
    MATRIX_AUTHORITY_REQUIRED_CHECKS,
    TRANSITION_KIND,
    EvidenceRef,
    TransitionSpec,
)
from scripts.core_pipeline_lib.campaign.projection import projection_sha256
from scripts.core_pipeline_lib.campaign.transition import (
    EXPECTED_2048_CELL_COUNT,
    EXPECTED_ADMITTED_CELL_COUNT,
    EXPECTED_CAMPAIGN_ID,
    EXPECTED_DEFERRED_CELL_COUNT,
    EXPECTED_DOUBLE_RENDER_COMPARISON,
    EXPECTED_ENGINE_BUNDLE_PATH,
    EXPECTED_EVIDENCE_PIN_COUNT,
    EXPECTED_HOST_VALIDATED_CELL_COUNT,
    EXPECTED_LOGICAL_REUSE_CELL_COUNT,
    EXPECTED_PARENT_BINDING_COUNT,
    EXPECTED_PER_CELL_HASH_ALGORITHM,
    EXPECTED_PER_CELL_HASH_SERIALIZATION,
    EXPECTED_PHASE_FREEZE_PATH,
    EXPECTED_PREDECESSOR_PATH,
    EXPECTED_PRODUCER_CELL_COUNT,
    EXPECTED_SCHEMA_DRAFT,
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_PATH,
    EXPECTED_SUPPORTED_COORDINATE_SET_SHA256,
    EXPECTED_SUPERSEDES_REASON,
    EXPECTED_TRANSITION_ID,
    EXPECTED_UNSUPPORTED_COORDINATE_SET_SHA256,
    EXPECTED_VEMULATOR_MAIN_CELL_COUNT,
    EXPECTED_VERSION_ALIGNMENT_MODEL,
    LEGACY_CHECK_IDS,
    LEGACY_DETAIL_KEYS,
    MATRIX_FORMAT,
    TRANSITION_MEMBER_PATH,
    PlannedMatrixAuthorityRefresh,
    legacy_matrix_compatibility_references,
    legacy_matrix_pointer_reference,
    legacy_matrix_predecessor_references,
    plan_matrix_authority_refresh,
    validate_matrix_authority_refresh,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes
from scripts.core_pipeline_lib.source_bundle import pipeline_bundle_content_sha256


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _source_bundle(files: dict[str, str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "files": files,
        "content_sha256": pipeline_bundle_content_sha256(files),
    }


def _seal_legacy(document: dict[str, object]) -> bytes:
    document["content_sha256"] = matrix_v2_semantic_sha256(document)
    return render_matrix_v2(document)


def _reference(
    *,
    kind: str,
    path: str,
    raw: bytes,
    target_content_sha256: str,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=target_content_sha256,
        size=len(raw),
    )


def _schema_identity_policy(raw: bytes) -> dict[str, object]:
    schema = decode_matrix_v2(raw)
    return {
        "EXPECTED_SCHEMA_FILE_SHA256": sha256_bytes(raw),
        "EXPECTED_SCHEMA_CANONICAL_SHA256": sha256_bytes(
            matrix_v2_canonical_bytes(schema)
        ),
        "EXPECTED_SCHEMA_BYTES": len(raw),
        "EXPECTED_SCHEMA_LINES": len(raw.splitlines()),
    }


class MatrixAuthorityTransitionFixture:
    def __init__(self) -> None:
        self.pipeline_source = _source_bundle(
            {
                "scripts/core_pipeline.py": _sha256(1),
                "scripts/core_pipeline_lib/__init__.py": _sha256(2),
                "scripts/core_pipeline_lib/campaign/legacy.py": _sha256(3),
            }
        )
        self.engine_bundle = _source_bundle(
            {
                "scripts/core_pipeline.py": _sha256(11),
                "scripts/core_pipeline_lib/__init__.py": _sha256(12),
                TRANSITION_MEMBER_PATH: _sha256(13),
            }
        )
        engine_raw = rendered_json_bytes(self.engine_bundle)
        self.engine_ref = _reference(
            kind="engine-bundle",
            path=EXPECTED_ENGINE_BUNDLE_PATH,
            raw=engine_raw,
            target_content_sha256=self.engine_bundle["content_sha256"],  # type: ignore[arg-type]
        )

        self.catalog = {
            "content_sha256": _sha256(101),
            "core_count": 2,
            "file_sha256": _sha256(102),
            "path": "manifests/core-catalog.json",
            "resolver": {"content_sha256": _sha256(103)},
            "toolchains": {"content_sha256": _sha256(104)},
        }
        self.core_specs = {
            "2048": {"core_id": "2048"},
            "VEmulator": {"core_id": "VEmulator"},
        }
        self.track_registry_sha256 = _sha256(105)
        self.tuning_registry_sha256 = _sha256(106)
        self.suite_summary = "2 passed, 0 skipped in 0.02s"
        self.canonical_inputs: dict[str, object] = {
            "catalog": self.catalog,
            "commit_blacklist": {"content_sha256": _sha256(110)},
            "core_specs": self.core_specs,
            "host_execution": {"content_sha256": _sha256(111)},
            "instrumentation": {"content_sha256": _sha256(112)},
            "recipe_auxiliaries": {"content_sha256": _sha256(113)},
            "schemas": {"content_sha256": _sha256(114)},
            "spruce_branch_bases": {"content_sha256": _sha256(115)},
            "spruce_release_roster": {"content_sha256": _sha256(116)},
            "telemetry_schema": {"content_sha256": _sha256(117)},
            "toolchain_lock": {"content_sha256": _sha256(118)},
            "tracks": {"content_sha256": self.track_registry_sha256},
            "tunings": {"content_sha256": self.tuning_registry_sha256},
            "workflows": {"content_sha256": _sha256(119)},
        }
        self.freeze_document: dict[str, object] = {
            "captured_at": "2026-08-14T12:00:00Z",
            "validation_scope": {"finite_legacy_value": 1.25},
            "local_only": True,
            "publication": "disabled",
            "repository": {"name": "fixture"},
            "bundles": {
                "pipeline_source": self.pipeline_source,
                "production": {"content_sha256": _sha256(121)},
                "tests": {"content_sha256": _sha256(122)},
            },
            "canonical_inputs": self.canonical_inputs,
            "validation": {
                "authoritative_post_gambatte_full_suite": {
                    "summary": self.suite_summary,
                },
                "status": "passed",
            },
        }
        self.freeze_raw = _seal_legacy(self.freeze_document)
        self.freeze_ref = _reference(
            kind="phase-freeze",
            path=EXPECTED_PHASE_FREEZE_PATH,
            raw=self.freeze_raw,
            target_content_sha256=self.freeze_document["content_sha256"],  # type: ignore[arg-type]
        )

        self.supported_cells: list[object] = []
        for core_id, count in (("VEmulator", 27), ("2048", 27), ("other", 1)):
            for index in range(count):
                self.supported_cells.append(
                    {
                        "coordinate": {
                            "architecture": "arm64",
                            "chipset": "a33",
                            "core_id": core_id,
                            "marker": "main" if index < 9 else f"aux-{index}",
                            "track": "main",
                        },
                        "weight": float(index) if index == 0 else index,
                    }
                )
        self.exclusions: list[object] = [
            {"core": "excluded", "coordinate": "main/arm64"},
            {"core": "deferred", "coordinate": "next/arm64"},
        ]
        self.summary: dict[str, object] = {
            "admitted_cell_count": EXPECTED_ADMITTED_CELL_COUNT,
            "deferred_cell_count": EXPECTED_DEFERRED_CELL_COUNT,
            "evidence_pin_count": EXPECTED_EVIDENCE_PIN_COUNT,
            "logical_reuse_cell_count": EXPECTED_LOGICAL_REUSE_CELL_COUNT,
            "producer_cell_count": EXPECTED_PRODUCER_CELL_COUNT,
            "supported_cell_count": len(self.supported_cells),
            "unsupported_exclusion_count": len(self.exclusions),
        }
        self.tracks: list[object] = ["main", "next", "reuse"]
        self.predecessor_current_authority: dict[str, object] = {
            "audit": {"selected": "closed-predecessor-fact"},
            "classification": "predecessor-authority",
            "full_suite": {"summary": "older suite"},
            "generator_path": ".local-e2e/held-generator.py",
            "phase_freeze": {"content_sha256": _sha256(210)},
            "phase_freeze_generator": {"file_sha256": _sha256(211)},
            "pin_directory": ".local-e2e/pins",
            "pipeline_bundle": {"content_sha256": _sha256(212)},
            "production_bundle": {"content_sha256": _sha256(213)},
            "targeted_suite": {"summary": "older targeted suite"},
            "tests_bundle": {"content_sha256": _sha256(214)},
            "track_snapshot_directory": ".local-e2e/tracks",
            "tracks": {"content_sha256": _sha256(215)},
        }
        self.predecessor_historical_chain: dict[str, object] = {
            "adapter": {"file_sha256": _sha256(216)},
            "classification": "historical-predecessor",
            "inherited_provenance": {
                "adapter_source": {"file_sha256": _sha256(217)},
                "freeze_generator": {"file_sha256": _sha256(218)},
                "held_v1_provenance": {"file_sha256": _sha256(219)},
                "held_v2_provenance": {"file_sha256": _sha256(220)},
                "phase_freeze": {"content_sha256": _sha256(221)},
            },
            "matrix": {"content_sha256": _sha256(222)},
            "phase_freeze": {"content_sha256": _sha256(223)},
        }
        self.predecessor_document: dict[str, object] = {
            "format": MATRIX_FORMAT,
            "captured_at": "2026-08-13T12:00:00Z",
            "inputs": {
                "generator": {
                    "path": ".local-e2e/held-generator.py",
                    "file_sha256": _sha256(30),
                },
                "phase_freeze": {
                    "path": ".local-e2e/old-freeze.json",
                    "content_sha256": _sha256(31),
                    "file_sha256": _sha256(32),
                },
                "pipeline_bundle": {
                    "schema_version": 1,
                    "file_count": 1,
                    "content_sha256": _sha256(33),
                    "source_phase_freeze_content_sha256": _sha256(34),
                },
                "unrelated": {"must": "remain"},
            },
            "supersedes": {
                "path": ".local-e2e/older-pointer.json",
                "format": MATRIX_FORMAT,
                "content_sha256": _sha256(40),
                "file_sha256": _sha256(41),
                "bytes": 100,
                "lines": 10,
                "snapshot_path": ".local-e2e/older-snapshot.json",
                "cas_path": ".local-e2e/older-cas.json",
                "reason": "older authority",
            },
            "validation_ledger": self._ledger(),
            "supported_cells": self.supported_cells,
            "unsupported_exclusions": self.exclusions,
            "summary": self.summary,
            "tracks": self.tracks,
            "local_only": True,
            "publication": "disabled",
            "stable_root": {"must": ["remain", False, 0, 1.0]},
        }
        self.predecessor_raw = _seal_legacy(self.predecessor_document)
        self.predecessor_ref = _reference(
            kind="matrix-pointer",
            path=EXPECTED_PREDECESSOR_PATH,
            raw=self.predecessor_raw,
            target_content_sha256=self.predecessor_document["content_sha256"],  # type: ignore[arg-type]
        )
        self.spec = TransitionSpec(
            transition_id=EXPECTED_TRANSITION_ID,
            campaign_id=EXPECTED_CAMPAIGN_ID,
            kind=TRANSITION_KIND,
            captured_at="2026-08-14T13:00:00Z",
            reason=EXPECTED_SUPERSEDES_REASON,
            predecessor=self.predecessor_ref,
            phase_freeze=self.freeze_ref,
        )
        self.spec_ref = self._spec_reference(self.spec)
        self.schema: dict[str, object] = {
            "$schema": EXPECTED_SCHEMA_DRAFT,
            "type": "object",
            "required": [
                "format",
                "captured_at",
                "inputs",
                "supersedes",
                "validation_ledger",
                "supported_cells",
                "unsupported_exclusions",
                "summary",
                "tracks",
                "local_only",
                "publication",
                "content_sha256",
            ],
            "properties": {
                "format": {"const": MATRIX_FORMAT},
                "local_only": {"const": True},
                "publication": {"const": "disabled"},
                "supported_cells": {"type": "array"},
                "unsupported_exclusions": {"type": "array"},
                "validation_ledger": {
                    "type": "object",
                    "properties": {"check_count": {"const": 11}},
                    "required": ["check_count", "checks", "status"],
                },
            },
        }
        self.schema_raw = (
            json.dumps(
                self.schema,
                ensure_ascii=False,
                allow_nan=False,
                indent=4,
                sort_keys=False,
            )
            + "\n"
        ).encode("utf-8")
        self.policy_values = self._policy_values()

    def _ledger(self) -> dict[str, object]:
        details_by_id: dict[str, dict[str, object]] = {
            "canonical-inputs-validated-once": {
                "authoritative_suite_summary": "older suite",
                "catalog_core_count": 2,
                "current_authority": self.predecessor_current_authority,
                "historical_predecessor_chain": (
                    self.predecessor_historical_chain
                ),
                "phase_freeze_content_sha256": _sha256(201),
                "pipeline_source_content_sha256": _sha256(202),
                "track_registry_content_sha256": _sha256(203),
                "tuning_registry_content_sha256": _sha256(204),
            },
            "frozen-edge-snapshot-bound": {
                "content_sha256": _sha256(205),
                "file_sha256": _sha256(206),
                "source_count": 1,
            },
            "coordinate-partition-exact": {
                "potential_coordinate_count": len(self.supported_cells)
                + len(self.exclusions),
                "supported_cell_count": len(self.supported_cells),
                "unsupported_exclusion_count": len(self.exclusions),
            },
            "cell-order-and-uniqueness": {
                "supported_coordinate_set_content_sha256": (
                    EXPECTED_SUPPORTED_COORDINATE_SET_SHA256
                ),
                "unsupported_coordinate_set_content_sha256": (
                    EXPECTED_UNSUPPORTED_COORDINATE_SET_SHA256
                ),
            },
            "independent-lifecycle-axes-cross-validated": {
                "admitted_cell_count": EXPECTED_ADMITTED_CELL_COUNT,
                "allowed_target_changes": [],
                "deferred_cell_count": EXPECTED_DEFERRED_CELL_COUNT,
                "lifecycle_change_scope": [],
                "logical_reuse_cell_count": EXPECTED_LOGICAL_REUSE_CELL_COUNT,
                "non_target_supported_exact_count": len(self.supported_cells),
                "preserved_2048_cell_count": EXPECTED_2048_CELL_COUNT,
                "preserved_vemulator_main_cell_count": (
                    EXPECTED_VEMULATOR_MAIN_CELL_COUNT
                ),
                "producer_cell_count": EXPECTED_PRODUCER_CELL_COUNT,
                "target_cell_count": 0,
                "unchanged_exclusion_count": len(self.exclusions),
            },
            "host-reproduction-proof-required-for-test": {
                "evidence_pin_count": EXPECTED_EVIDENCE_PIN_COUNT,
                "host_validated_cell_count": EXPECTED_HOST_VALIDATED_CELL_COUNT,
            },
            "source-order-lineage-and-outliers-validated": {
                "authorized_outlier_count": 0,
                "parent_binding_count": EXPECTED_PARENT_BINDING_COUNT,
            },
            "branch-artifacts-observational-only": {
                "byte_match_required": False,
                "version_alignment_model": EXPECTED_VERSION_ALIGNMENT_MODEL,
            },
            "per-cell-and-root-semantic-hash-projections": {
                "algorithm": EXPECTED_PER_CELL_HASH_ALGORITHM,
                "serialization": EXPECTED_PER_CELL_HASH_SERIALIZATION,
            },
            "json-schema-draft-2020-12": {"schema_path": EXPECTED_SCHEMA_PATH},
            "deterministic-double-render": {
                "comparison": EXPECTED_DOUBLE_RENDER_COMPARISON
            },
        }
        if tuple(details_by_id) != LEGACY_CHECK_IDS:
            raise AssertionError("fixture ledger order differs from legacy policy")
        for check_id, details in details_by_id.items():
            if frozenset(details) != LEGACY_DETAIL_KEYS[check_id]:
                raise AssertionError(f"fixture detail keys differ for {check_id}")
        return {
            "check_count": len(LEGACY_CHECK_IDS),
            "checks": [
                {
                    "check_id": check_id,
                    "details": details_by_id[check_id],
                    "status": "passed",
                }
                for check_id in LEGACY_CHECK_IDS
            ],
            "status": "passed",
        }

    @staticmethod
    def _spec_reference(spec: TransitionSpec) -> EvidenceRef:
        raw = rendered_json_bytes(spec.to_document())
        return _reference(
            kind="transition-spec",
            path=EXPECTED_SPEC_PATH,
            raw=raw,
            target_content_sha256=spec.content_sha256,
        )

    def _policy_values(self) -> dict[str, object]:
        vemulator = [
            cell
            for cell in self.supported_cells
            if cell["coordinate"]["core_id"].casefold() == "vemulator"  # type: ignore[index,union-attr]
        ]
        core_2048 = [
            cell
            for cell in self.supported_cells
            if cell["coordinate"]["core_id"] == "2048"  # type: ignore[index]
        ]
        return {
            "EXPECTED_PREDECESSOR_CONTENT_SHA256": self.predecessor_document[
                "content_sha256"
            ],
            "EXPECTED_PREDECESSOR_FILE_SHA256": sha256_bytes(self.predecessor_raw),
            "EXPECTED_PREDECESSOR_BYTES": len(self.predecessor_raw),
            "EXPECTED_PREDECESSOR_LINES": len(self.predecessor_raw.splitlines()),
            "EXPECTED_PHASE_FREEZE_CONTENT_SHA256": self.freeze_document[
                "content_sha256"
            ],
            "EXPECTED_PHASE_FREEZE_FILE_SHA256": sha256_bytes(self.freeze_raw),
            "EXPECTED_PHASE_FREEZE_BYTES": len(self.freeze_raw),
            "EXPECTED_PHASE_FREEZE_LINES": len(self.freeze_raw.splitlines()),
            "EXPECTED_CANONICAL_INPUT_COUNT": len(self.core_specs),
            "EXPECTED_CATALOG_CONTENT_SHA256": self.catalog["content_sha256"],
            "EXPECTED_CATALOG_FILE_SHA256": self.catalog["file_sha256"],
            "EXPECTED_PREDECESSOR_CURRENT_AUTHORITY_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(self.predecessor_current_authority)
            ),
            "EXPECTED_PREDECESSOR_HISTORICAL_CHAIN_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(self.predecessor_historical_chain)
            ),
            "EXPECTED_SUPPORTED_CELL_COUNT": len(self.supported_cells),
            "EXPECTED_EXCLUSION_COUNT": len(self.exclusions),
            "EXPECTED_PRESERVED_PROJECTION_SHA256": projection_sha256(
                self.predecessor_document,
                MATRIX_AUTHORITY_ALLOWED_CHANGES,
                canonical_bytes=matrix_v2_canonical_bytes,
            ),
            "EXPECTED_SUPPORTED_CELLS_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(self.supported_cells)
            ),
            "EXPECTED_EXCLUSIONS_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(self.exclusions)
            ),
            "EXPECTED_SUMMARY_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(self.summary)
            ),
            "EXPECTED_TRACKS_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(self.tracks)
            ),
            "EXPECTED_VEMULATOR_PROJECTION_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(vemulator)
            ),
            "EXPECTED_2048_PROJECTION_SHA256": sha256_bytes(
                matrix_v2_canonical_bytes(core_2048)
            ),
            **_schema_identity_policy(self.schema_raw),
        }

    @contextmanager
    def policy(self):
        with mock.patch.multiple(transition, **self.policy_values):
            yield

    @contextmanager
    def schema_policy(self, raw: bytes):
        with mock.patch.multiple(transition, **_schema_identity_policy(raw)):
            yield

    def planner_arguments(self) -> dict[str, object]:
        return {
            "spec": self.spec,
            "spec_ref": self.spec_ref,
            "predecessor_raw": self.predecessor_raw,
            "phase_freeze_raw": self.freeze_raw,
            "engine_bundle_ref": self.engine_ref,
            "engine_bundle_document": self.engine_bundle,
        }

    def plan(self) -> PlannedMatrixAuthorityRefresh:
        return plan_matrix_authority_refresh(**self.planner_arguments())  # type: ignore[arg-type]

    def validate(
        self,
        result: PlannedMatrixAuthorityRefresh,
        *,
        schema_raw: bytes | None = None,
        arguments: dict[str, object] | None = None,
    ) -> None:
        values = self.planner_arguments() if arguments is None else arguments
        validate_matrix_authority_refresh(
            result,
            **values,  # type: ignore[arg-type]
            schema_raw=self.schema_raw if schema_raw is None else schema_raw,
        )

    def rebind_predecessor(
        self,
        document: dict[str, object],
    ) -> tuple[bytes, TransitionSpec, EvidenceRef, dict[str, object]]:
        raw = _seal_legacy(document)
        predecessor_ref = _reference(
            kind="matrix-pointer",
            path=self.predecessor_ref.path,
            raw=raw,
            target_content_sha256=document["content_sha256"],  # type: ignore[arg-type]
        )
        spec = replace(self.spec, predecessor=predecessor_ref)
        spec_ref = self._spec_reference(spec)
        policy = dict(self.policy_values)
        policy.update(
            {
                "EXPECTED_PREDECESSOR_CONTENT_SHA256": document["content_sha256"],
                "EXPECTED_PREDECESSOR_FILE_SHA256": sha256_bytes(raw),
                "EXPECTED_PREDECESSOR_BYTES": len(raw),
                "EXPECTED_PREDECESSOR_LINES": len(raw.splitlines()),
                "EXPECTED_SUMMARY_SHA256": sha256_bytes(
                    matrix_v2_canonical_bytes(document["summary"])
                ),
            }
        )
        return raw, spec, spec_ref, policy

    def rebind_freeze(
        self,
        document: dict[str, object],
    ) -> tuple[bytes, TransitionSpec, EvidenceRef, dict[str, object]]:
        raw = _seal_legacy(document)
        freeze_ref = _reference(
            kind="phase-freeze",
            path=self.freeze_ref.path,
            raw=raw,
            target_content_sha256=document["content_sha256"],  # type: ignore[arg-type]
        )
        spec = replace(self.spec, phase_freeze=freeze_ref)
        spec_ref = self._spec_reference(spec)
        policy = dict(self.policy_values)
        policy.update(
            {
                "EXPECTED_PHASE_FREEZE_CONTENT_SHA256": document["content_sha256"],
                "EXPECTED_PHASE_FREEZE_FILE_SHA256": sha256_bytes(raw),
                "EXPECTED_PHASE_FREEZE_BYTES": len(raw),
                "EXPECTED_PHASE_FREEZE_LINES": len(raw.splitlines()),
            }
        )
        return raw, spec, spec_ref, policy


class CampaignTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = MatrixAuthorityTransitionFixture()

    @staticmethod
    def _checks_by_id(candidate: dict[str, object]) -> dict[str, dict[str, object]]:
        ledger = candidate["validation_ledger"]
        return {
            check["check_id"]: check["details"]
            for check in ledger["checks"]  # type: ignore[index]
        }

    def test_plan_is_deterministic_exact_and_deeply_valid(self) -> None:
        fixture = self.fixture
        predecessor_snapshot = copy.deepcopy(fixture.predecessor_document)
        freeze_snapshot = copy.deepcopy(fixture.freeze_document)
        with fixture.policy():
            first = fixture.plan()
            second = fixture.plan()
            fixture.validate(first)

        self.assertEqual(first, second)
        self.assertEqual(first.changed_pointers, MATRIX_AUTHORITY_ALLOWED_CHANGES)
        self.assertEqual(first.plan.required_checks, MATRIX_AUTHORITY_REQUIRED_CHECKS)
        self.assertEqual(first.plan.predecessor, fixture.predecessor_ref)
        self.assertEqual(first.plan.phase_freeze, fixture.freeze_ref)
        self.assertEqual(first.plan.engine_bundle, fixture.engine_ref)
        self.assertEqual(first.plan.pipeline_bundle.path, fixture.freeze_ref.path)
        self.assertEqual(
            first.plan.pipeline_bundle.target_content_sha256,
            fixture.pipeline_source["content_sha256"],
        )

        candidate = decode_matrix_v2(first.candidate_raw)
        self.assertEqual(candidate["captured_at"], fixture.spec.captured_at)
        self.assertEqual(candidate["inputs"]["unrelated"], {"must": "remain"})  # type: ignore[index]
        self.assertEqual(
            candidate["inputs"]["generator"],  # type: ignore[index]
            {
                "path": TRANSITION_MEMBER_PATH,
                "file_sha256": fixture.engine_bundle["files"][  # type: ignore[index]
                    TRANSITION_MEMBER_PATH
                ],
            },
        )
        self.assertEqual(
            candidate["inputs"]["phase_freeze"],  # type: ignore[index]
            {
                "path": EXPECTED_PHASE_FREEZE_PATH,
                "content_sha256": fixture.freeze_ref.target_content_sha256,
                "file_sha256": fixture.freeze_ref.file_sha256,
            },
        )
        self.assertEqual(
            candidate["inputs"]["pipeline_bundle"],  # type: ignore[index]
            {
                "schema_version": 1,
                "file_count": len(fixture.pipeline_source["files"]),  # type: ignore[arg-type]
                "content_sha256": fixture.pipeline_source["content_sha256"],
                "source_phase_freeze_content_sha256": (
                    fixture.freeze_ref.target_content_sha256
                ),
            },
        )
        self.assertEqual(candidate["supersedes"]["path"], EXPECTED_PREDECESSOR_PATH)  # type: ignore[index]
        self.assertEqual(candidate["supersedes"]["reason"], EXPECTED_SUPERSEDES_REASON)  # type: ignore[index]

        ledger = candidate["validation_ledger"]
        self.assertIs(type(ledger["check_count"]), int)  # type: ignore[index]
        self.assertEqual(ledger["check_count"], 11)  # type: ignore[index]
        checks = ledger["checks"]  # type: ignore[index]
        self.assertEqual([check["check_id"] for check in checks], list(LEGACY_CHECK_IDS))  # type: ignore[index]
        for check in checks:  # type: ignore[assignment]
            self.assertEqual(
                frozenset(check["details"]),  # type: ignore[index]
                LEGACY_DETAIL_KEYS[check["check_id"]],  # type: ignore[index]
            )
        details = self._checks_by_id(candidate)
        canonical = details["canonical-inputs-validated-once"]
        self.assertEqual(canonical["authoritative_suite_summary"], fixture.suite_summary)
        self.assertEqual(canonical["catalog_core_count"], len(fixture.core_specs))
        self.assertEqual(
            canonical["track_registry_content_sha256"],
            fixture.track_registry_sha256,
        )
        self.assertEqual(
            canonical["tuning_registry_content_sha256"],
            fixture.tuning_registry_sha256,
        )
        self.assertEqual(
            frozenset(canonical["historical_predecessor_chain"]),  # type: ignore[arg-type]
            frozenset(
                {
                    "adapter",
                    "classification",
                    "inherited_predecessor_chain",
                    "matrix",
                    "predecessor_current_authority",
                }
            ),
        )
        self.assertEqual(
            details["frozen-edge-snapshot-bound"],
            {
                "content_sha256": fixture.catalog["content_sha256"],
                "file_sha256": fixture.catalog["file_sha256"],
                "source_count": len(fixture.core_specs),
            },
        )
        self.assertNotEqual(
            details["frozen-edge-snapshot-bound"],
            fixture.predecessor_document["validation_ledger"]["checks"][1][  # type: ignore[index]
                "details"
            ],
        )
        self.assertEqual(
            details["cell-order-and-uniqueness"],
            {
                "supported_coordinate_set_content_sha256": (
                    EXPECTED_SUPPORTED_COORDINATE_SET_SHA256
                ),
                "unsupported_coordinate_set_content_sha256": (
                    EXPECTED_UNSUPPORTED_COORDINATE_SET_SHA256
                ),
            },
        )
        lifecycle = details["independent-lifecycle-axes-cross-validated"]
        self.assertEqual(lifecycle["admitted_cell_count"], 297)
        self.assertEqual(lifecycle["deferred_cell_count"], 2241)
        self.assertEqual(lifecycle["logical_reuse_cell_count"], 275)
        self.assertEqual(lifecycle["producer_cell_count"], 22)
        self.assertEqual(lifecycle["target_cell_count"], 0)
        self.assertEqual(lifecycle["non_target_supported_exact_count"], 55)
        self.assertEqual(lifecycle["preserved_vemulator_main_cell_count"], 9)
        self.assertEqual(lifecycle["preserved_2048_cell_count"], 27)
        self.assertEqual(lifecycle["unchanged_exclusion_count"], 2)
        self.assertEqual(lifecycle["allowed_target_changes"], [])
        self.assertEqual(lifecycle["lifecycle_change_scope"], [])
        self.assertEqual(
            details["host-reproduction-proof-required-for-test"],
            {"evidence_pin_count": 11, "host_validated_cell_count": 297},
        )
        self.assertEqual(
            details["source-order-lineage-and-outliers-validated"],
            {"authorized_outlier_count": 0, "parent_binding_count": 22},
        )
        self.assertEqual(
            details["branch-artifacts-observational-only"],
            {
                "byte_match_required": False,
                "version_alignment_model": "manual-version-level-only",
            },
        )
        self.assertEqual(
            details["per-cell-and-root-semantic-hash-projections"],
            {
                "algorithm": "sha256",
                "serialization": "canonical-json-utf8-sort-keys-compact-v1",
            },
        )
        self.assertEqual(
            details["json-schema-draft-2020-12"],
            {"schema_path": EXPECTED_SCHEMA_PATH},
        )
        self.assertEqual(
            details["deterministic-double-render"],
            {"comparison": "exact-pretty-json-bytes"},
        )
        self.assertEqual(fixture.predecessor_document, predecessor_snapshot)
        self.assertEqual(fixture.freeze_document, freeze_snapshot)
        self.assertNotIn(first.plan.content_sha256.encode(), first.candidate_raw)
        self.assertNotIn(first.plan.successor.file_sha256.encode(), first.candidate_raw)

    def test_successor_predecessor_and_pointer_compatibility_paths_are_exact(self) -> None:
        fixture = self.fixture
        with fixture.policy():
            result = fixture.plan()
            self.assertNotEqual(render_matrix_v2(fixture.schema), fixture.schema_raw)
            fixture.validate(result)
            snapshot, raw_cas = legacy_matrix_compatibility_references(result)
            predecessor_snapshot, predecessor_raw_cas = (
                legacy_matrix_predecessor_references(fixture.spec)
            )
            pointer = legacy_matrix_pointer_reference(fixture.spec, result)
        raw_sha256 = sha256_bytes(result.candidate_raw)
        semantic = decode_matrix_v2(result.candidate_raw)["content_sha256"]
        self.assertEqual(
            result.plan.successor.path,
            (
                ".local-e2e/campaign-state/objects/matrix-snapshot/sha256/"
                f"{raw_sha256[:2]}/{raw_sha256}"
            ),
        )
        self.assertEqual(
            snapshot.path,
            (
                ".local-e2e/campaigns/host-core-build-20260810/matrices/"
                f"{semantic}.json"
            ),
        )
        self.assertEqual(
            raw_cas.path,
            (
                ".local-e2e/store/campaign-matrices/sha256/"
                f"{raw_sha256[:2]}/{raw_sha256}"
            ),
        )
        self.assertEqual(pointer.path, EXPECTED_PREDECESSOR_PATH)
        for reference in (snapshot, raw_cas, pointer):
            self.assertEqual(reference.file_sha256, raw_sha256)
            self.assertEqual(reference.target_content_sha256, semantic)
            self.assertEqual(reference.size, len(result.candidate_raw))

        predecessor_semantic = fixture.predecessor_ref.target_content_sha256
        predecessor_raw = fixture.predecessor_ref.file_sha256
        self.assertEqual(
            predecessor_snapshot.path,
            (
                ".local-e2e/campaigns/host-core-build-20260810/matrices/"
                f"{predecessor_semantic}.json"
            ),
        )
        self.assertEqual(
            predecessor_raw_cas.path,
            (
                ".local-e2e/store/campaign-matrices/sha256/"
                f"{predecessor_raw[:2]}/{predecessor_raw}"
            ),
        )
        for reference in (predecessor_snapshot, predecessor_raw_cas):
            self.assertEqual(reference.file_sha256, predecessor_raw)
            self.assertEqual(reference.target_content_sha256, predecessor_semantic)
            self.assertEqual(reference.size, len(fixture.predecessor_raw))

        candidate = decode_matrix_v2(result.candidate_raw)
        candidate["captured_at"] = "2026-08-14T13:00:01Z"
        candidate["content_sha256"] = matrix_v2_semantic_sha256(candidate)
        mismatched = PlannedMatrixAuthorityRefresh(
            plan=result.plan,
            candidate_raw=render_matrix_v2(candidate),
            changed_pointers=result.changed_pointers,
        )
        with self.assertRaises(PipelineError):
            legacy_matrix_compatibility_references(mismatched)
        with fixture.policy(), self.assertRaises(PipelineError):
            legacy_matrix_predecessor_references(
                replace(
                    fixture.spec,
                    predecessor=replace(fixture.predecessor_ref, file_sha256=_sha256(1)),
                )
            )
        with fixture.policy(), self.assertRaises(PipelineError):
            legacy_matrix_predecessor_references(
                replace(
                    fixture.spec,
                    predecessor=replace(
                        fixture.predecessor_ref,
                        path=".local-e2e/campaigns/other/campaign-matrix.json",
                    ),
                )
            )

    def test_campaign_transition_and_authority_paths_are_closed(self) -> None:
        fixture = self.fixture
        cases: list[tuple[str, dict[str, object]]] = []
        for field, value in (
            ("transition_id", "other-transition"),
            ("campaign_id", "other-campaign"),
        ):
            spec = replace(fixture.spec, **{field: value})
            cases.append(
                (
                    field,
                    {"spec": spec, "spec_ref": fixture._spec_reference(spec)},
                )
            )
        predecessor = replace(
            fixture.predecessor_ref,
            path=".local-e2e/campaigns/other/campaign-matrix.json",
        )
        spec = replace(fixture.spec, predecessor=predecessor)
        cases.append(
            (
                "predecessor-path",
                {"spec": spec, "spec_ref": fixture._spec_reference(spec)},
            )
        )
        freeze = replace(
            fixture.freeze_ref,
            path=".local-e2e/campaigns/other/freeze.json",
        )
        spec = replace(fixture.spec, phase_freeze=freeze)
        cases.append(
            (
                "freeze-path",
                {"spec": spec, "spec_ref": fixture._spec_reference(spec)},
            )
        )
        cases.extend(
            (
                (
                    "spec-ref-path",
                    {
                        "spec_ref": replace(
                            fixture.spec_ref,
                            path="manifests/campaign-transitions/other.json",
                        )
                    },
                ),
                (
                    "engine-ref-path",
                    {
                        "engine_bundle_ref": replace(
                            fixture.engine_ref,
                            path="manifests/campaign-engine-bundles/other.json",
                        )
                    },
                ),
            )
        )
        with fixture.policy():
            for name, replacements in cases:
                with self.subTest(name=name):
                    arguments = fixture.planner_arguments()
                    arguments.update(replacements)
                    with self.assertRaises(PipelineError):
                        plan_matrix_authority_refresh(**arguments)  # type: ignore[arg-type]

    def test_every_explicit_input_is_reauthenticated(self) -> None:
        fixture = self.fixture
        original = fixture.planner_arguments()
        changed_engine = copy.deepcopy(fixture.engine_bundle)
        changed_engine["files"][TRANSITION_MEMBER_PATH] = _sha256(999)  # type: ignore[index]
        cases = {
            "spec": replace(fixture.spec, captured_at="2026-08-14T13:00:01Z"),
            "spec_ref": replace(fixture.spec_ref, size=fixture.spec_ref.size + 1),
            "predecessor_raw": fixture.predecessor_raw + b" ",
            "phase_freeze_raw": fixture.freeze_raw + b" ",
            "engine_bundle_ref": replace(
                fixture.engine_ref,
                file_sha256=_sha256(998),
            ),
            "engine_bundle_document": changed_engine,
        }
        with fixture.policy():
            for name, value in cases.items():
                with self.subTest(name=name):
                    arguments = dict(original)
                    arguments[name] = value
                    with self.assertRaises(PipelineError):
                        plan_matrix_authority_refresh(**arguments)  # type: ignore[arg-type]

    def test_engine_transition_member_is_required_and_bound(self) -> None:
        fixture = self.fixture
        for operation in ("missing", "tampered"):
            bundle = copy.deepcopy(fixture.engine_bundle)
            files = bundle["files"]
            if operation == "missing":
                files.pop(TRANSITION_MEMBER_PATH)  # type: ignore[union-attr]
            else:
                files[TRANSITION_MEMBER_PATH] = _sha256(997)  # type: ignore[index]
            bundle["content_sha256"] = pipeline_bundle_content_sha256(files)  # type: ignore[arg-type]
            raw = rendered_json_bytes(bundle)
            reference = _reference(
                kind="engine-bundle",
                path=EXPECTED_ENGINE_BUNDLE_PATH,
                raw=raw,
                target_content_sha256=bundle["content_sha256"],  # type: ignore[arg-type]
            )
            arguments = fixture.planner_arguments()
            arguments.update(
                {"engine_bundle_document": bundle, "engine_bundle_ref": reference}
            )
            with self.subTest(operation=operation), fixture.policy():
                if operation == "missing":
                    with self.assertRaises(PipelineError):
                        plan_matrix_authority_refresh(**arguments)  # type: ignore[arg-type]
                else:
                    result = plan_matrix_authority_refresh(**arguments)  # type: ignore[arg-type]
                    candidate = decode_matrix_v2(result.candidate_raw)
                    self.assertEqual(
                        candidate["inputs"]["generator"]["file_sha256"],  # type: ignore[index]
                        _sha256(997),
                    )

    def test_every_authorized_leaf_and_preserved_cell_tamper_is_rejected(self) -> None:
        fixture = self.fixture
        with fixture.policy():
            result = fixture.plan()
        mutators = {
            "captured_at": lambda value: value.__setitem__(
                "captured_at", "2026-08-14T13:00:01Z"
            ),
            "content_sha256": lambda value: value.__setitem__(
                "content_sha256", _sha256(900)
            ),
            "inputs.generator": lambda value: value["inputs"][
                "generator"
            ].__setitem__("file_sha256", _sha256(901)),
            "inputs.phase_freeze": lambda value: value["inputs"][
                "phase_freeze"
            ].__setitem__("file_sha256", _sha256(902)),
            "inputs.pipeline_bundle": lambda value: value["inputs"][
                "pipeline_bundle"
            ].__setitem__("content_sha256", _sha256(903)),
            "supersedes": lambda value: value["supersedes"].__setitem__(
                "reason", "tampered reason"
            ),
            "validation_ledger": lambda value: value["validation_ledger"][
                "checks"
            ][0]["details"].__setitem__("catalog_core_count", 999),
            "supported-cell": lambda value: value["supported_cells"][0][
                "coordinate"
            ].__setitem__("core_id", "tampered"),
        }
        for name, mutate in mutators.items():
            with self.subTest(name=name):
                candidate = decode_matrix_v2(result.candidate_raw)
                mutate(candidate)
                if name != "content_sha256":
                    candidate["content_sha256"] = matrix_v2_semantic_sha256(candidate)
                tampered = PlannedMatrixAuthorityRefresh(
                    plan=result.plan,
                    candidate_raw=render_matrix_v2(candidate),
                    changed_pointers=result.changed_pointers,
                )
                with fixture.policy(), self.assertRaises(PipelineError):
                    fixture.validate(tampered)

    def test_predecessor_ledger_values_and_exact_integer_types_are_closed(self) -> None:
        fixture = self.fixture
        variants: list[tuple[str, dict[str, object]]] = []

        def mutate(name: str, operation) -> None:
            document = copy.deepcopy(fixture.predecessor_document)
            operation(document)
            variants.append((name, document))

        mutate(
            "check-count-float",
            lambda value: value["validation_ledger"].__setitem__("check_count", 11.0),
        )
        mutate(
            "check-count-bool",
            lambda value: value["validation_ledger"].__setitem__("check_count", True),
        )
        mutate(
            "catalog-source-count-float",
            lambda value: value["validation_ledger"]["checks"][1][
                "details"
            ].__setitem__("source_count", 1.0),
        )
        mutate(
            "predecessor-current-authority-keys",
            lambda value: value["validation_ledger"]["checks"][0][
                "details"
            ]["current_authority"].pop("audit"),
        )
        mutate(
            "predecessor-history-digest",
            lambda value: value["validation_ledger"]["checks"][0][
                "details"
            ]["historical_predecessor_chain"].__setitem__(
                "classification", "tampered"
            ),
        )
        mutate(
            "coordinate-set",
            lambda value: value["validation_ledger"]["checks"][3][
                "details"
            ].__setitem__("supported_coordinate_set_content_sha256", _sha256(801)),
        )
        mutate(
            "parent-binding-float",
            lambda value: value["validation_ledger"]["checks"][6][
                "details"
            ].__setitem__("parent_binding_count", 22.0),
        )
        mutate(
            "byte-match",
            lambda value: value["validation_ledger"]["checks"][7][
                "details"
            ].__setitem__("byte_match_required", True),
        )
        mutate(
            "serialization",
            lambda value: value["validation_ledger"]["checks"][8][
                "details"
            ].__setitem__("serialization", "other"),
        )
        mutate(
            "schema-path",
            lambda value: value["validation_ledger"]["checks"][9][
                "details"
            ].__setitem__("schema_path", ".local-e2e/other.schema.json"),
        )
        mutate(
            "double-render",
            lambda value: value["validation_ledger"]["checks"][10][
                "details"
            ].__setitem__("comparison", "semantic-only"),
        )
        mutate(
            "admitted-count",
            lambda value: value["summary"].__setitem__("admitted_cell_count", 296),
        )
        mutate(
            "evidence-pin-bool",
            lambda value: value["summary"].__setitem__("evidence_pin_count", True),
        )
        for name, document in variants:
            raw, spec, spec_ref, policy = fixture.rebind_predecessor(document)
            arguments = fixture.planner_arguments()
            arguments.update(
                {"spec": spec, "spec_ref": spec_ref, "predecessor_raw": raw}
            )
            with self.subTest(name=name), mock.patch.multiple(transition, **policy):
                with self.assertRaises(PipelineError):
                    plan_matrix_authority_refresh(**arguments)  # type: ignore[arg-type]

    def test_nested_production_freeze_shape_and_numeric_aliases_are_closed(self) -> None:
        fixture = self.fixture
        self.assertEqual(len(fixture.canonical_inputs), 14)
        self.assertEqual(len(fixture.core_specs), 2)
        variants: list[tuple[str, dict[str, object]]] = []

        def mutate(name: str, operation) -> None:
            freeze = copy.deepcopy(fixture.freeze_document)
            operation(freeze)
            variants.append((name, freeze))

        mutate("root-list", lambda value: value.__setitem__("canonical_inputs", [1, 2]))
        mutate(
            "missing-root-key",
            lambda value: value["canonical_inputs"].pop("workflows"),
        )
        mutate(
            "extra-root-key",
            lambda value: value["canonical_inputs"].__setitem__("extra", {}),
        )
        mutate(
            "core-specs-list",
            lambda value: value["canonical_inputs"].__setitem__("core_specs", []),
        )
        mutate(
            "core-spec-count",
            lambda value: value["canonical_inputs"]["core_specs"].pop("2048"),
        )
        mutate(
            "catalog-count-float",
            lambda value: value["canonical_inputs"]["catalog"].__setitem__(
                "core_count", 2.0
            ),
        )
        mutate(
            "catalog-count-bool",
            lambda value: value["canonical_inputs"]["catalog"].__setitem__(
                "core_count", True
            ),
        )
        mutate(
            "catalog-keys",
            lambda value: value["canonical_inputs"]["catalog"].pop("resolver"),
        )
        mutate(
            "catalog-identity",
            lambda value: value["canonical_inputs"]["catalog"].__setitem__(
                "content_sha256", _sha256(700)
            ),
        )
        mutate(
            "track-registry",
            lambda value: value["canonical_inputs"]["tracks"].pop(
                "content_sha256"
            ),
        )
        mutate(
            "suite-summary",
            lambda value: value["validation"][
                "authoritative_post_gambatte_full_suite"
            ].pop("summary"),
        )
        mutate(
            "nested-pipeline",
            lambda value: value["bundles"]["pipeline_source"]["files"].pop(
                "scripts/core_pipeline.py"
            ),
        )
        for name, freeze in variants:
            if name == "nested-pipeline":
                files = freeze["bundles"]["pipeline_source"]["files"]
                freeze["bundles"]["pipeline_source"]["content_sha256"] = (
                    pipeline_bundle_content_sha256(files)
                )
            raw, spec, spec_ref, policy = fixture.rebind_freeze(freeze)
            arguments = fixture.planner_arguments()
            arguments.update(
                {"spec": spec, "spec_ref": spec_ref, "phase_freeze_raw": raw}
            )
            with self.subTest(name=name), mock.patch.multiple(transition, **policy):
                with self.assertRaises(PipelineError):
                    plan_matrix_authority_refresh(**arguments)  # type: ignore[arg-type]

    def test_schema_raw_identity_draft_references_and_validation_fail_closed(self) -> None:
        fixture = self.fixture
        with fixture.policy():
            result = fixture.plan()
            fixture.validate(result)
            with self.assertRaises(PipelineError):
                fixture.validate(result, schema_raw=fixture.schema_raw + b" ")
            permissive = render_matrix_v2(
                {"$schema": EXPECTED_SCHEMA_DRAFT, "type": "object"}
            )
            with self.assertRaises(PipelineError):
                fixture.validate(result, schema_raw=permissive)
            identity_cases = {
                "size": {"EXPECTED_SCHEMA_BYTES": len(fixture.schema_raw) + 1},
                "lines": {
                    "EXPECTED_SCHEMA_LINES": len(fixture.schema_raw.splitlines()) + 1
                },
                "canonical": {"EXPECTED_SCHEMA_CANONICAL_SHA256": _sha256(600)},
            }
            for name, policy in identity_cases.items():
                with self.subTest(name=name), mock.patch.multiple(
                    transition,
                    **policy,
                ):
                    with self.assertRaises(PipelineError):
                        fixture.validate(result)

            isolated = (
                ("missing-draft", {"type": "object"}),
                (
                    "wrong-draft",
                    {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                    },
                ),
                (
                    "remote-ref",
                    {
                        "$schema": EXPECTED_SCHEMA_DRAFT,
                        "$ref": "https://example.invalid/schema.json",
                    },
                ),
                (
                    "invalid-schema",
                    {"$schema": EXPECTED_SCHEMA_DRAFT, "type": 123},
                ),
                (
                    "candidate-failure",
                    {
                        "$schema": EXPECTED_SCHEMA_DRAFT,
                        "type": "object",
                        "properties": {"format": {"const": "wrong"}},
                    },
                ),
            )
            for name, schema in isolated:
                raw = render_matrix_v2(schema)
                with self.subTest(name=name), fixture.schema_policy(raw):
                    with self.assertRaises(PipelineError):
                        fixture.validate(result, schema_raw=raw)

            compact = matrix_v2_canonical_bytes(fixture.schema)
            with self.subTest(name="alternate-pinned-layout"), fixture.schema_policy(
                compact
            ):
                fixture.validate(result, schema_raw=compact)

    def test_result_is_frozen_and_planning_does_not_mutate_inputs(self) -> None:
        fixture = self.fixture
        engine_snapshot = copy.deepcopy(fixture.engine_bundle)
        predecessor_snapshot = bytes(fixture.predecessor_raw)
        freeze_snapshot = bytes(fixture.freeze_raw)
        with fixture.policy():
            result = fixture.plan()
            fixture.validate(result)
            again = fixture.plan()
        self.assertEqual(result, again)
        self.assertEqual(fixture.engine_bundle, engine_snapshot)
        self.assertEqual(fixture.predecessor_raw, predecessor_snapshot)
        self.assertEqual(fixture.freeze_raw, freeze_snapshot)
        with self.assertRaises(FrozenInstanceError):
            result.candidate_raw = b"changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
