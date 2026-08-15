from __future__ import annotations

import ast
from collections import Counter
import copy
from dataclasses import FrozenInstanceError, replace
from functools import cache
from pathlib import Path
from types import MappingProxyType
import unittest
from unittest.mock import patch

from scripts.core_pipeline_lib.campaign.legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
    render_matrix_v2,
)
from scripts.core_pipeline_lib.campaign.matrix_materialize import (
    MATRIX_STATE_RELATIVE,
    NormalizedMatrixV1,
    derive_legacy_summary,
    materialize_matrix_v2,
    matrix_object_reference,
    normalize_matrix_v2,
    validate_normalized_matrix,
)
from scripts.core_pipeline_lib.campaign.matrix_model import (
    EXCLUSION_PARTITION,
    PROJECTION_COUNT,
    PROJECTION_ORDER,
    SUPPORTED_PARTITION,
    TRACK_ORDER,
    MatrixShardLinkV1,
    decode_matrix_v1,
    legacy_coordinate_order,
    render_matrix_v1,
)
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "matrix_materialize.py"
)
CORE_IDS = tuple(f"core_{index:03d}" for index in range(98))
BASE_EXCLUSIONS = frozenset(
    (core_id, ordinal)
    for core_id in CORE_IDS[:4]
    for ordinal in range(27)
)
SMALL_CORE_IDS = (CORE_IDS[0],)
SMALL_EXCLUSIONS = frozenset(
    (SMALL_CORE_IDS[0], ordinal) for ordinal in range(4)
)


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _reference(kind: str, name: str, number: int) -> EvidenceRef:
    raw = f"{kind}:{name}:{number}\n".encode()
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=sha256_bytes(raw),
        target_content_sha256=_sha256(number + 10_000),
        size=len(raw),
    )


PHASE_FREEZE = _reference("phase-freeze-cas", "phase-freeze", 1)
CORE_SPEC_SET = _reference("artifact", "core-spec-set", 2)


def _seal(document: dict[str, object]) -> bytes:
    sealed = copy.deepcopy(document)
    sealed.pop("content_sha256", None)
    sealed["content_sha256"] = matrix_v2_semantic_sha256(sealed)
    return render_matrix_v2(sealed)


def _supported_payload(
    coordinate: dict[str, object],
    *,
    identity: int,
) -> dict[str, object]:
    core_id = coordinate["core_id"]
    payload: dict[str, object] = {
        "branch_artifact_observation": {"artifact_validity": "valid"},
        "build_identity": {
            "content_sha256": _sha256(identity + 20_000),
            "pin": {"pin_id": f"pin-{core_id}"},
            "state": "established",
        },
        "coordinate": coordinate,
        "evidence": {
            "reproduction": {"run_id": f"reproduction-{core_id}"},
            "selected": {"run_id": f"selected-{core_id}"},
        },
        "lifecycle": {
            "admission_state": "admitted",
            "evidence_state": "host-validated",
            "execution_state": "built",
            "gha_state": "gha-not-requested",
        },
        "lineage": {},
        "outlier": {"authorization": None},
        "outputs": {},
        "performance": {"finite_legacy_measurement": 1.25},
        "resolution": {"resolution": "exact_test"},
        "reuse": {},
        "version_slice": {},
    }
    payload["content_sha256"] = matrix_v2_semantic_sha256(payload)
    return payload


def _exclusion_payload(coordinate: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "branch_artifact_observation": {"artifact_validity": "not_shipped"},
        "catalog_source": {},
        "coordinate": coordinate,
        "edge_candidate": {},
        "reason": "catalog-target-architecture-unsupported",
        "supported_architectures": ["arm64"],
    }
    payload["content_sha256"] = matrix_v2_semantic_sha256(payload)
    return payload


def _fixture_summary(
    supported: list[dict[str, object]],
    exclusions: list[dict[str, object]],
) -> dict[str, object]:
    coordinates = [item["coordinate"] for item in supported]

    def count(field: str) -> dict[str, int]:
        return dict(Counter(item[field] for item in coordinates))  # type: ignore[index]

    core_ids = {item["core_id"] for item in coordinates}  # type: ignore[index]
    supported_count = len(supported)
    return {
        "admitted_cell_count": supported_count,
        "admitted_core_count": len(core_ids),
        "architecture_counts": count("architecture"),
        "branch_artifact_correlation": {"valid": supported_count},
        "chipset_counts": count("chipset"),
        "deferred_cell_count": 0,
        "evidence_pin_count": len(core_ids),
        "lifecycle_counts": {
            "admission": {"admitted": supported_count},
            "evidence": {"host-validated": supported_count},
            "execution": {"built": supported_count},
            "gha": {"gha-not-requested": supported_count},
        },
        "logical_reuse_cell_count": 0,
        "not_run_cell_count": 0,
        "potential_coordinate_count": supported_count + len(exclusions),
        "producer_cell_count": supported_count,
        "reproduction_run_count": len(core_ids),
        "resolution_counts": {"exact_test": supported_count},
        "selected_run_count": len(core_ids),
        "source_order_outlier_count": 0,
        "supported_cell_count": supported_count,
        "track_counts": count("track"),
        "unique_established_build_identity_count": supported_count,
        "unsupported_exclusion_count": len(exclusions),
    }


def _fixture_document(
    *,
    exclusions: frozenset[tuple[str, int]] = BASE_EXCLUSIONS,
    captured_at: str = "2026-08-14T21:00:00Z",
    core_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    if core_ids is None:
        core_ids = CORE_IDS
    ordered = legacy_coordinate_order(core_ids)
    supported: list[dict[str, object]] = []
    unsupported: list[dict[str, object]] = []
    for identity, coordinate in enumerate(ordered, start=1):
        document = coordinate.to_document()
        if (coordinate.core_id, coordinate.universe_ordinal) in exclusions:
            unsupported.append(_exclusion_payload(document))
        else:
            supported.append(_supported_payload(document, identity=identity))

    supported_coordinates = [item["coordinate"] for item in supported]
    unsupported_coordinates = [item["coordinate"] for item in unsupported]
    expansion = {
        "algorithm": (
            "cross ordered tracks, sorted catalog cores, and ordered typed "
            "chipset/ABI projections; partition by catalog target support"
        ),
        "architecture_order": ["arm64", "armhf"],
        "catalog_core_count": len(core_ids),
        "chipset_order": [
            "universal",
            "a133p",
            "a33",
            "a523",
            "h700",
            "rk3326",
            "rk3566",
            "ssd202d",
        ],
        "core_order": "ascending-core-id",
        "core_order_content_sha256": sha256_bytes(
            matrix_v2_canonical_bytes(list(core_ids))
        ),
        "potential_coordinate_count": len(ordered),
        "projection_count": PROJECTION_COUNT,
        "projections": [
            {"architecture": architecture, "chipset": chipset}
            for chipset, architecture in PROJECTION_ORDER
        ],
        "supported_cell_count": len(supported),
        "supported_coordinate_order_content_sha256": sha256_bytes(
            matrix_v2_canonical_bytes(supported_coordinates)
        ),
        "track_count": len(TRACK_ORDER),
        "track_order": list(TRACK_ORDER),
        "unsupported_coordinate_order_content_sha256": sha256_bytes(
            matrix_v2_canonical_bytes(unsupported_coordinates)
        ),
        "unsupported_exclusion_count": len(unsupported),
    }
    return {
        "$schema": "campaign-matrix-v2.schema.json",
        "audit": {"label": "synthetic-local-only"},
        "campaign_id": "host-core-build-20260810",
        "captured_at": captured_at,
        "directory_fingerprint_model": {},
        "expansion": expansion,
        "format": "spruce-host-core-campaign-matrix-v2",
        "hash_model": {},
        "inputs": {
            "phase_freeze": {
                "content_sha256": PHASE_FREEZE.target_content_sha256,
                "file_sha256": PHASE_FREEZE.file_sha256,
                "path": PHASE_FREEZE.path,
            }
        },
        "local_only": True,
        "marker": "test",
        "publication": "disabled",
        "schema_version": 2,
        "summary": _fixture_summary(supported, unsupported),
        "supersedes": None,
        "supported_cells": supported,
        "tracks": [{"finite_legacy_measurement": 1.25}],
        "unsupported_exclusions": unsupported,
        "validation_ledger": [],
        "validation_scope": "host-build-version-channel-cell-ledger-v2",
    }


@cache
def _immutable_full_fixture() -> tuple[bytes, NormalizedMatrixV1]:
    raw = _seal(_fixture_document())
    closure = normalize_matrix_v2(
        raw,
        phase_freeze=PHASE_FREEZE,
        core_spec_set=CORE_SPEC_SET,
    )
    return raw, closure


@cache
def _immutable_small_fixture() -> tuple[bytes, NormalizedMatrixV1]:
    """Return immutable inputs for exact non-owner boundary coverage."""

    raw = _seal(
        _fixture_document(
            exclusions=SMALL_EXCLUSIONS,
            core_ids=SMALL_CORE_IDS,
        )
    )
    closure = normalize_matrix_v2(
        raw,
        phase_freeze=PHASE_FREEZE,
        core_spec_set=CORE_SPEC_SET,
    )
    return raw, closure


def _start_small_matrix_universe(test_case: unittest.TestCase) -> None:
    """Keep non-owner tests exact without repeating the full 98-core cost."""

    values = (
        (
            "scripts.core_pipeline_lib.campaign.matrix_model."
            "EXPECTED_CORE_COUNT",
            1,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_model."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_materialize."
            "EXPECTED_CORE_COUNT",
            1,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_materialize."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_store."
            "EXPECTED_CORE_COUNT",
            1,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_store."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
    )
    for target, value in values:
        patcher = patch(target, value)
        patcher.start()
        test_case.addCleanup(patcher.stop)


class CampaignMatrixMaterializeTests(unittest.TestCase):
    _FULL_MATRIX_OWNER = (
        "test_normalization_closes_all_links_and_round_trips_exact_bytes"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw, cls.closure = _immutable_full_fixture()
        cls.document = decode_matrix_v2(cls.raw)

    def setUp(self) -> None:
        # Staging guards this named owner as the always-running full closure.
        if self._testMethodName == self._FULL_MATRIX_OWNER:
            return
        _start_small_matrix_universe(self)
        self.raw, self.closure = _immutable_small_fixture()
        self.document = decode_matrix_v2(self.raw)

    def test_normalization_closes_all_links_and_round_trips_exact_bytes(self) -> None:
        closure = self.closure
        validate_normalized_matrix(closure)
        materialized = materialize_matrix_v2(closure)
        self.assertEqual(self.raw, materialized)
        self.assertEqual(98, len(closure.shards))
        self.assertEqual(2_646, len(closure.cells))
        self.assertEqual(2_538, closure.root.supported_cell_count)
        self.assertEqual(108, closure.root.unsupported_exclusion_count)
        self.assertEqual("matrix-root", closure.root_reference.kind)
        self.assertEqual(
            matrix_object_reference(closure.root), closure.root_reference
        )
        self.assertEqual(
            "14c4bf395bffaf11687c580f3d54740df45f6f3285a7f7c1cb5372be07f50eab",
            closure.root_reference.content_sha256,
        )
        self.assertTrue(
            closure.root_reference.path.startswith(
                f"{MATRIX_STATE_RELATIVE}/objects/matrix-root/sha256/"
            )
        )
        golden_objects = (
            (
                closure.cells[0],
                "bb833334f02ebcc329bc817bc6462f5f261f58797f80b0edadcf25bc1778daf9",
                "958f6009d3c9b157eb09fe09b920fe3583ec69135907c944eb837e25fcd8d8e3",
                888,
            ),
            (
                closure.shards[0],
                "4e1ad2482a4d24e04c3007fb64da322a83957d466dc9f3b1e1c61c1f8ae4b908",
                "6626d473462f1206e3c63d8094c7a2420a1b36303ac24842df310744f1ff70c4",
                17_133,
            ),
            (
                closure.root,
                "86e63e8f8260df59542d74b628c8198d579158c5638dcfaf17e15061b5889b66",
                "ecfc4e81e4f59a0fad6db4fef198f93d751a299b792da42bcc6a1fd7e4a6a5d5",
                67_955,
            ),
        )
        for value, semantic_sha256, file_sha256, size in golden_objects:
            with self.subTest(object_type=type(value).__name__):
                reference = matrix_object_reference(value)
                self.assertEqual(semantic_sha256, value.content_sha256)
                self.assertEqual(file_sha256, reference.file_sha256)
                self.assertEqual(size, reference.size)
        self.assertNotIn("summary", closure.root.to_document())
        self.assertNotIn("summary", decode_matrix_v2(
            closure.root.legacy_root_json.encode("utf-8")
        ))
        with self.assertRaises(FrozenInstanceError):
            closure.cells = ()  # type: ignore[misc]

        regenerated = decode_matrix_v2(materialized)
        self.assertEqual(
            self.document["summary"], derive_legacy_summary(closure.cells)
        )
        self.assertEqual(self.document["summary"], regenerated["summary"])

    def test_root_reference_recursively_resolves_exact_store_bytes(self) -> None:
        closure = self.closure
        objects = tuple(
            (matrix_object_reference(value), render_matrix_v1(value))
            for value in (*closure.cells, *closure.shards, closure.root)
        )
        self.assertEqual(
            len(closure.cells) + len(closure.shards) + 1,
            len(objects),
        )
        self.assertEqual(len(objects), len({reference for reference, _raw in objects}))
        object_bytes = MappingProxyType(dict(objects))
        visited: set[EvidenceRef] = set()

        def read_exact(reference: EvidenceRef) -> bytes:
            raw = object_bytes[reference]
            self.assertEqual(reference.size, len(raw))
            self.assertEqual(reference.file_sha256, sha256_bytes(raw))
            self.assertEqual(reference, matrix_object_reference(decode_matrix_v1(raw)))
            visited.add(reference)
            return raw

        loaded_root = decode_matrix_v1(read_exact(closure.root_reference))
        self.assertEqual(closure.root, loaded_root)
        loaded_cell_count = 0
        for expected_shard, shard_link in zip(
            closure.shards, loaded_root.shards
        ):
            loaded_shard = decode_matrix_v1(read_exact(shard_link.reference))
            self.assertEqual(expected_shard, loaded_shard)
            for cell_link in loaded_shard.cells:
                loaded_cell = decode_matrix_v1(read_exact(cell_link.reference))
                self.assertEqual(
                    cell_link.content_sha256,
                    loaded_cell.content_sha256,
                )
                loaded_cell_count += 1
        self.assertEqual(len(closure.cells), loaded_cell_count)
        self.assertEqual(set(object_bytes), visited)

    def test_normalization_rejects_stale_summary_even_after_outer_reseal(self) -> None:
        document = decode_matrix_v2(self.raw)
        document["summary"]["producer_cell_count"] -= 1  # type: ignore[index,operator]
        with self.assertRaisesRegex(PipelineError, "summary"):
            normalize_matrix_v2(
                _seal(document),
                phase_freeze=PHASE_FREEZE,
                core_spec_set=CORE_SPEC_SET,
            )

    def test_expansion_counts_and_all_order_hashes_are_derived(self) -> None:
        mutations = {
            "supported_cell_count": 1,
            "core_order_content_sha256": _sha256(90),
            "supported_coordinate_order_content_sha256": _sha256(91),
            "unsupported_coordinate_order_content_sha256": _sha256(92),
        }
        for key, value in mutations.items():
            document = decode_matrix_v2(self.raw)
            document["expansion"][key] = value  # type: ignore[index]
            with self.subTest(key=key):
                with self.assertRaisesRegex(PipelineError, "expansion"):
                    normalize_matrix_v2(
                        _seal(document),
                        phase_freeze=PHASE_FREEZE,
                        core_spec_set=CORE_SPEC_SET,
                    )

    def test_source_cell_semantic_digest_and_global_order_fail_closed(self) -> None:
        document = decode_matrix_v2(self.raw)
        document["supported_cells"][0]["performance"][  # type: ignore[index]
            "finite_legacy_measurement"
        ] = 2.5
        with self.assertRaisesRegex(PipelineError, "content_sha256"):
            normalize_matrix_v2(
                _seal(document),
                phase_freeze=PHASE_FREEZE,
                core_spec_set=CORE_SPEC_SET,
            )

        document = decode_matrix_v2(self.raw)
        supported = document["supported_cells"]
        supported[0], supported[1] = supported[1], supported[0]  # type: ignore[index]
        with self.assertRaisesRegex(PipelineError, "order"):
            normalize_matrix_v2(
                _seal(document),
                phase_freeze=PHASE_FREEZE,
                core_spec_set=CORE_SPEC_SET,
            )

    def test_full_closure_validation_rejects_cell_shard_root_and_identity_drift(self) -> None:
        closure = self.closure
        swapped = replace(
            closure,
            cells=(closure.cells[1], closure.cells[0], *closure.cells[2:]),
        )
        with self.assertRaises(PipelineError):
            validate_normalized_matrix(swapped)

        first_shard = closure.shards[0]
        drifted_link = replace(
            first_shard.cells[0],
            reference=replace(
                first_shard.cells[0].reference,
                file_sha256=_sha256(999),
            ),
        )
        drifted_shard = replace(
            first_shard,
            cells=(drifted_link, *first_shard.cells[1:]),
        )
        shard_drift = replace(
            closure,
            shards=(drifted_shard, *closure.shards[1:]),
        )
        with self.assertRaises(PipelineError):
            validate_normalized_matrix(shard_drift)

        first_root_link = closure.root.shards[0]
        root_link = MatrixShardLinkV1(
            core_id=first_root_link.core_id,
            supported_cell_count=first_root_link.supported_cell_count,
            unsupported_exclusion_count=first_root_link.unsupported_exclusion_count,
            reference=replace(
                first_root_link.reference,
                file_sha256=_sha256(998),
            ),
        )
        drifted_root = replace(
            closure.root,
            shards=(root_link, *closure.root.shards[1:]),
        )
        root_drift = replace(
            closure,
            root=drifted_root,
            root_reference=matrix_object_reference(drifted_root),
        )
        with self.assertRaises(PipelineError):
            validate_normalized_matrix(root_drift)

        wrong_identity = replace(
            closure.root.legacy_matrix,
            file_sha256=_sha256(997),
        )
        identity_root = replace(closure.root, legacy_matrix=wrong_identity)
        identity_drift = replace(
            closure,
            root=identity_root,
            root_reference=matrix_object_reference(identity_root),
        )
        with self.assertRaisesRegex(PipelineError, "identity"):
            materialize_matrix_v2(identity_drift)

        wrong_phase = replace(
            closure.root.phase_freeze,
            target_content_sha256=_sha256(995),
        )
        authority_root = replace(closure.root, phase_freeze=wrong_phase)
        authority_drift = replace(
            closure,
            root=authority_root,
            root_reference=matrix_object_reference(authority_root),
        )
        with self.assertRaisesRegex(PipelineError, "phase_freeze"):
            validate_normalized_matrix(authority_drift)

        for field, value in (
            ("path", "wrong/matrix-root.json"),
            ("file_sha256", _sha256(994)),
            ("size", closure.root_reference.size + 1),
        ):
            with self.subTest(root_reference_field=field):
                wrong_root_reference = replace(
                    closure.root_reference,
                    **{field: value},
                )
                with self.assertRaisesRegex(PipelineError, "root reference"):
                    validate_normalized_matrix(
                        replace(closure, root_reference=wrong_root_reference)
                    )

    def test_authority_only_metadata_change_reuses_every_cell_and_shard(self) -> None:
        document = _fixture_document(
            exclusions=SMALL_EXCLUSIONS,
            captured_at="2026-08-14T22:00:00Z",
            core_ids=SMALL_CORE_IDS,
        )
        raw = _seal(document)
        after = normalize_matrix_v2(
            raw,
            phase_freeze=PHASE_FREEZE,
            core_spec_set=CORE_SPEC_SET,
        )
        self.assertEqual(self.closure.cells, after.cells)
        self.assertEqual(self.closure.shards, after.shards)
        self.assertNotEqual(self.closure.root, after.root)
        self.assertNotEqual(self.closure.root_reference, after.root_reference)
        self.assertEqual(raw, materialize_matrix_v2(after))

    def test_one_support_flip_changes_one_cell_one_shard_and_one_root(self) -> None:
        exclusions = frozenset(
            item
            for item in SMALL_EXCLUSIONS
            if item != (SMALL_CORE_IDS[0], 0)
        )
        raw = _seal(
            _fixture_document(
                exclusions=exclusions,
                core_ids=SMALL_CORE_IDS,
            )
        )
        after = normalize_matrix_v2(
            raw,
            phase_freeze=PHASE_FREEZE,
            core_spec_set=CORE_SPEC_SET,
        )
        changed_cells = [
            (left, right)
            for left, right in zip(self.closure.cells, after.cells)
            if left != right
        ]
        changed_shards = [
            (left, right)
            for left, right in zip(self.closure.shards, after.shards)
            if left != right
        ]
        self.assertEqual(1, len(changed_cells))
        self.assertEqual(1, len(changed_shards))
        before_cell, after_cell = changed_cells[0]
        self.assertEqual(before_cell.universe_ordinal, after_cell.universe_ordinal)
        self.assertEqual(before_cell.coordinate, after_cell.coordinate)
        self.assertEqual(EXCLUSION_PARTITION, before_cell.partition)
        self.assertEqual(SUPPORTED_PARTITION, after_cell.partition)
        self.assertEqual(
            self.closure.root.supported_cell_count + 1,
            after.root.supported_cell_count,
        )
        self.assertEqual(
            self.closure.root.unsupported_exclusion_count - 1,
            after.root.unsupported_exclusion_count,
        )
        self.assertNotEqual(self.closure.root, after.root)
        self.assertNotEqual(self.closure.root_reference, after.root_reference)
        self.assertEqual(raw, materialize_matrix_v2(after))

    def test_authority_binding_types_and_module_purity_fail_closed(self) -> None:
        wrong_phase = replace(
            PHASE_FREEZE,
            target_content_sha256=_sha256(996),
        )
        with self.assertRaises(PipelineError):
            normalize_matrix_v2(
                self.raw,
                phase_freeze=wrong_phase,
                core_spec_set=CORE_SPEC_SET,
            )
        for value in (None, {}, object()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(PipelineError):
                    validate_normalized_matrix(value)
                with self.assertRaises(PipelineError):
                    materialize_matrix_v2(value)

        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_roots.add(node.module.split(".", 1)[0])
        self.assertTrue(
            {"os", "pathlib", "subprocess", "importlib", "time"}.isdisjoint(
                imported_roots
            )
        )
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(
            {"open", "exec", "eval", "compile", "__import__"}.isdisjoint(calls)
        )


if __name__ == "__main__":
    unittest.main()
