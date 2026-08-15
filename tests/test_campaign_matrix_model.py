from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, fields, replace
import inspect
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from scripts.core_pipeline_lib.campaign.legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
)
from scripts.core_pipeline_lib.campaign.matrix_model import (
    CELL_FORMAT,
    EXCLUSION_PARTITION,
    EXPECTED_CORE_COUNT,
    EXPECTED_SUPPORTED_CELL_COUNT,
    EXPECTED_UNIVERSE_CELL_COUNT,
    EXPECTED_UNSUPPORTED_EXCLUSION_COUNT,
    LegacyMatrixV2Identity,
    MatrixCellLinkV1,
    MatrixCellV1,
    MatrixCoordinateV1,
    MatrixRootV1,
    MatrixShardLinkV1,
    MatrixShardV1,
    PROJECTION_COUNT,
    PROJECTION_ORDER,
    ROOT_FORMAT,
    SHARD_FORMAT,
    SUPPORTED_PARTITION,
    TRACK_ORDER,
    UNIVERSE_CELLS_PER_CORE,
    coordinate_for_ordinal,
    decode_matrix_v1,
    legacy_coordinate_order,
    render_matrix_v1,
)
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.campaign.store import canonical_object_reference
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "manifests" / "campaign-matrix-v1.schema.json"
MODEL_PATH = (
    ROOT / "scripts" / "core_pipeline_lib" / "campaign" / "matrix_model.py"
)


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _ref(kind: str, name: str, number: int) -> EvidenceRef:
    raw = f"{kind}:{name}:{number}\n".encode()
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=sha256_bytes(raw),
        target_content_sha256=_sha256(number + 10_000),
        size=len(raw),
    )


def _matrix_ref(kind: str, name: str, target_content_sha256: str) -> EvidenceRef:
    raw = f"{kind}:{name}:{target_content_sha256}\n".encode()
    return canonical_object_reference(
        state_relative=".local-e2e/campaign-state",
        kind=kind,
        raw=raw,
        target_content_sha256=target_content_sha256,
    )


def _legacy_cell_json(
    coordinate: MatrixCoordinateV1,
    partition: str,
    *,
    measurement: float = 1.25,
) -> str:
    if partition == SUPPORTED_PARTITION:
        payload: dict[str, object] = {
            "branch_artifact_observation": {},
            "build_identity": {},
            "coordinate": coordinate.to_document(),
            "evidence": {},
            "lifecycle": {},
            "lineage": {},
            "outlier": {},
            "outputs": {},
            "performance": {
                "finite_legacy_measurement": measurement,
                "unicode_text": "café 雪",
            },
            "resolution": {},
            "reuse": {},
            "version_slice": {},
        }
    else:
        payload = {
            "branch_artifact_observation": {},
            "catalog_source": {},
            "coordinate": coordinate.to_document(),
            "edge_candidate": {},
            "reason": "catalog-target-architecture-unsupported",
            "supported_architectures": ["arm64"],
        }
    payload["content_sha256"] = matrix_v2_semantic_sha256(payload)
    return matrix_v2_canonical_bytes(payload).decode("utf-8")


def _cell(
    core_id: str = "core_000",
    ordinal: int = 0,
    partition: str = SUPPORTED_PARTITION,
) -> MatrixCellV1:
    coordinate = coordinate_for_ordinal(core_id, ordinal)
    return MatrixCellV1(
        universe_ordinal=ordinal,
        coordinate=coordinate,
        partition=partition,
        legacy_payload_json=_legacy_cell_json(coordinate, partition),
    )


def _shard(
    core_id: str = "core_000",
    *,
    excluded: frozenset[int] = frozenset(),
) -> MatrixShardV1:
    return MatrixShardV1(
        core_id=core_id,
        cells=tuple(
            MatrixCellLinkV1(
                universe_ordinal=ordinal,
                partition=(
                    EXCLUSION_PARTITION
                    if ordinal in excluded
                    else SUPPORTED_PARTITION
                ),
                reference=_matrix_ref(
                    "matrix-cell",
                    f"{core_id}-{ordinal}",
                    _sha256(ordinal + 1),
                ),
            )
            for ordinal in range(UNIVERSE_CELLS_PER_CORE)
        ),
    )


def _core_ids() -> tuple[str, ...]:
    return tuple(f"core_{index:03d}" for index in range(EXPECTED_CORE_COUNT))


def _root_projection_json(
    *,
    captured_at: str = "2026-08-14T21:00:00Z",
    supported: int = EXPECTED_SUPPORTED_CELL_COUNT,
    excluded: int = EXPECTED_UNSUPPORTED_EXCLUSION_COUNT,
) -> str:
    projection = {
        "$schema": "campaign-matrix-v2.schema.json",
        "audit": {"label": "local-audit"},
        "campaign_id": "host-core-build-20260810",
        "captured_at": captured_at,
        "directory_fingerprint_model": {},
        "expansion": {
            "catalog_core_count": EXPECTED_CORE_COUNT,
            "potential_coordinate_count": EXPECTED_UNIVERSE_CELL_COUNT,
            "projection_count": PROJECTION_COUNT,
            "projections": [
                {"architecture": architecture, "chipset": chipset}
                for chipset, architecture in PROJECTION_ORDER
            ],
            "supported_cell_count": supported,
            "track_count": len(TRACK_ORDER),
            "track_order": list(TRACK_ORDER),
            "unsupported_exclusion_count": excluded,
        },
        "format": "spruce-host-core-campaign-matrix-v2",
        "hash_model": {},
        "inputs": {},
        "local_only": True,
        "marker": "test",
        "publication": "disabled",
        "schema_version": 2,
        "supersedes": None,
        "tracks": [{"finite_legacy_measurement": 1.25}],
        "validation_ledger": [],
        "validation_scope": "host-build-version-channel-cell-ledger-v2",
    }
    return matrix_v2_canonical_bytes(projection).decode("utf-8")


def _root(
    *,
    captured_at: str = "2026-08-14T21:00:00Z",
    phase_number: int = 1,
    matrix_number: int | None = None,
    first_shard: MatrixShardV1 | None = None,
) -> MatrixRootV1:
    matrix_number = phase_number if matrix_number is None else matrix_number
    core_ids = _core_ids()
    first = first_shard or _shard(core_ids[0], excluded=frozenset(range(27)))
    shard_links: list[MatrixShardLinkV1] = [
        first.link(_matrix_ref("matrix-shard", first.core_id, first.content_sha256))
    ]
    for index, core_id in enumerate(core_ids[1:], start=1):
        excluded = frozenset(range(27)) if index < 4 else frozenset()
        shard = _shard(core_id, excluded=excluded)
        shard_links.append(
            shard.link(_matrix_ref("matrix-shard", core_id, shard.content_sha256))
        )
    supported = sum(item.supported_cell_count for item in shard_links)
    excluded = sum(item.unsupported_exclusion_count for item in shard_links)
    return MatrixRootV1(
        campaign_id="host-core-build-20260810",
        captured_at=captured_at,
        phase_freeze=_ref("phase-freeze-cas", "phase-freeze", phase_number),
        core_spec_set=_ref("artifact", "core-spec-set", 100),
        legacy_matrix=LegacyMatrixV2Identity(
            semantic_sha256=_sha256(200 + matrix_number),
            file_sha256=_sha256(300 + matrix_number),
            size=40_000_000 + matrix_number,
            lines=900_000 + matrix_number,
        ),
        legacy_root_json=_root_projection_json(
            captured_at=captured_at,
            supported=supported,
            excluded=excluded,
        ),
        shards=tuple(shard_links),
    )


def _contains_float(value: object) -> bool:
    if type(value) is float:
        return True
    if type(value) is list:
        return any(_contains_float(item) for item in value)
    if type(value) is dict:
        return any(_contains_float(item) for item in value.values())
    return False


class CampaignMatrixModelTests(unittest.TestCase):
    def test_fixed_universe_ordinals_and_legacy_global_order_are_exact(self) -> None:
        self.assertEqual(3, len(TRACK_ORDER))
        self.assertEqual(9, PROJECTION_COUNT)
        self.assertEqual(27, UNIVERSE_CELLS_PER_CORE)
        coordinates = tuple(
            coordinate_for_ordinal("core_000", ordinal)
            for ordinal in range(UNIVERSE_CELLS_PER_CORE)
        )
        self.assertEqual(tuple(range(27)), tuple(c.universe_ordinal for c in coordinates))
        self.assertEqual(
            tuple(track for track in TRACK_ORDER for _ in PROJECTION_ORDER),
            tuple(coordinate.track for coordinate in coordinates),
        )
        self.assertEqual(
            PROJECTION_ORDER * len(TRACK_ORDER),
            tuple(
                (coordinate.chipset, coordinate.architecture)
                for coordinate in coordinates
            ),
        )

        ordered = legacy_coordinate_order(_core_ids())
        self.assertEqual(EXPECTED_UNIVERSE_CELL_COUNT, len(ordered))
        self.assertEqual(("core_000", 0), (ordered[0].core_id, ordered[0].universe_ordinal))
        self.assertEqual(("core_001", 0), (ordered[9].core_id, ordered[9].universe_ordinal))
        self.assertEqual(
            ("core_000", 9),
            (ordered[EXPECTED_CORE_COUNT * PROJECTION_COUNT].core_id,
             ordered[EXPECTED_CORE_COUNT * PROJECTION_COUNT].universe_ordinal),
        )
        self.assertEqual(("core_097", 26), (ordered[-1].core_id, ordered[-1].universe_ordinal))

    def test_cell_round_trip_authenticates_legacy_float_payload_as_a_string(self) -> None:
        cell = _cell(ordinal=12)
        document = cell.to_document()

        self.assertEqual(CELL_FORMAT, document["format"])
        self.assertEqual(cell.content_sha256, document["content_sha256"])
        self.assertIn("1.25", cell.legacy_payload_json)
        self.assertIn("café 雪", cell.legacy_payload_json)
        self.assertFalse(_contains_float(document))
        decoded_legacy = decode_matrix_v2(cell.legacy_payload_json.encode("utf-8"))
        self.assertIs(type(decoded_legacy["performance"]["finite_legacy_measurement"]), float)  # type: ignore[index]
        self.assertEqual(
            "café 雪",
            decoded_legacy["performance"]["unicode_text"],  # type: ignore[index]
        )

        rendered = render_matrix_v1(cell)
        self.assertEqual(
            "11b5293d7ca4757874c2df889f7f4699fb4cf78358500e1ad9bb320fc9e6889a",
            cell.content_sha256,
        )
        self.assertEqual(
            "f2a6e81141493617dd7f4584698e3658b0750dc008ca812fe03412104f6a3d5d",
            sha256_bytes(rendered),
        )
        decoded = decode_matrix_v1(rendered)
        self.assertEqual(cell, decoded)
        self.assertEqual(document, decoded.to_document())
        self.assertIn("café 雪", rendered.decode("utf-8"))
        self.assertTrue(rendered.endswith(b"}\n"))

    def test_cell_rejects_ordinal_partition_payload_and_digest_drift(self) -> None:
        supported = _cell(ordinal=5)
        excluded = _cell(ordinal=5, partition=EXCLUSION_PARTITION)
        self.assertEqual(supported.universe_ordinal, excluded.universe_ordinal)
        self.assertEqual(supported.coordinate, excluded.coordinate)
        self.assertNotEqual(supported.content_sha256, excluded.content_sha256)

        with self.assertRaises(PipelineError):
            replace(supported, universe_ordinal=6)
        with self.assertRaises(PipelineError):
            replace(supported, partition=EXCLUSION_PARTITION)
        with self.assertRaises(PipelineError):
            replace(supported, legacy_payload_json=" " + supported.legacy_payload_json)
        with self.assertRaises(PipelineError):
            replace(supported, legacy_payload_json="\ud800")

        for token in ("NaN", "Infinity", "+Infinity", "-Infinity"):
            with self.subTest(nonfinite=token):
                nonfinite = supported.legacy_payload_json.replace(
                    "1.25", token, 1
                )
                with self.assertRaises(PipelineError):
                    replace(supported, legacy_payload_json=nonfinite)

        payload = decode_matrix_v2(supported.legacy_payload_json.encode("utf-8"))
        payload["content_sha256"] = _sha256(999)
        with self.assertRaises(PipelineError):
            replace(
                supported,
                legacy_payload_json=matrix_v2_canonical_bytes(payload).decode("utf-8"),
            )

        payload = decode_matrix_v2(supported.legacy_payload_json.encode("utf-8"))
        payload["coordinate"]["track"] = "edge"  # type: ignore[index]
        payload["content_sha256"] = matrix_v2_semantic_sha256(payload)
        with self.assertRaises(PipelineError):
            replace(
                supported,
                legacy_payload_json=matrix_v2_canonical_bytes(payload).decode("utf-8"),
            )

    def test_shard_is_exactly_one_link_per_stable_ordinal(self) -> None:
        shard = _shard(excluded=frozenset({1, 4, 26}))
        self.assertEqual(24, shard.supported_cell_count)
        self.assertEqual(3, shard.unsupported_exclusion_count)
        self.assertEqual(tuple(range(27)), tuple(item.universe_ordinal for item in shard.cells))
        self.assertEqual(
            {"matrix-cell"}, {item.reference.kind for item in shard.cells}
        )
        rendered = render_matrix_v1(shard)
        self.assertEqual(
            "b0d1de3511cdb98fefa5669127e6c7873bd75ddea2ededb96d745df351b6256a",
            shard.content_sha256,
        )
        self.assertEqual(
            "3828dd689999ab5a3814a5eaa71a953e4d3f290296a3f623a7320722ae9c6853",
            sha256_bytes(rendered),
        )
        self.assertEqual(shard, decode_matrix_v1(rendered))

        with self.assertRaises(PipelineError):
            replace(shard, cells=shard.cells[:-1])
        with self.assertRaises(PipelineError):
            replace(shard, cells=(shard.cells[1], shard.cells[0], *shard.cells[2:]))
        with self.assertRaises(PipelineError):
            replace(shard, cells=list(shard.cells))  # type: ignore[arg-type]

    def test_links_require_full_role_specific_semantic_references(self) -> None:
        cell = _cell(ordinal=8)
        cell_reference = _matrix_ref(
            "matrix-cell", "linked-cell", cell.content_sha256
        )
        cell_link = cell.link(cell_reference)
        self.assertEqual(cell_reference, cell_link.reference)
        self.assertEqual(cell.content_sha256, cell_link.content_sha256)
        self.assertEqual(
            cell_link,
            MatrixCellLinkV1.from_document(cell_link.to_document()),
        )
        for reference in (
            replace(cell_reference, kind="matrix-shard"),
            replace(cell_reference, target_content_sha256=_sha256(998)),
            replace(cell_reference, target_content_sha256=None),
        ):
            with self.subTest(reference=reference):
                with self.assertRaises(PipelineError):
                    cell.link(reference)

        shard = _shard()
        shard_reference = _matrix_ref(
            "matrix-shard", "linked-shard", shard.content_sha256
        )
        shard_link = shard.link(shard_reference)
        self.assertEqual(shard_reference, shard_link.reference)
        self.assertEqual(shard.content_sha256, shard_link.content_sha256)
        self.assertEqual(
            shard_link,
            MatrixShardLinkV1.from_document(shard_link.to_document()),
        )
        for reference in (
            replace(shard_reference, kind="matrix-cell"),
            replace(shard_reference, target_content_sha256=_sha256(997)),
            replace(shard_reference, target_content_sha256=None),
        ):
            with self.subTest(reference=reference):
                with self.assertRaises(PipelineError):
                    shard.link(reference)

    def test_status_flip_changes_one_cell_one_shard_and_one_root_without_renumbering(self) -> None:
        before_cell = _cell(ordinal=7, partition=EXCLUSION_PARTITION)
        after_cell = _cell(ordinal=7, partition=SUPPORTED_PARTITION)
        before_shard = _shard(excluded=frozenset(range(27)))
        after_links = list(before_shard.cells)
        after_links[7] = after_cell.link(
            _matrix_ref("matrix-cell", "after-cell-7", after_cell.content_sha256)
        )
        before_links = list(before_shard.cells)
        before_links[7] = before_cell.link(
            _matrix_ref("matrix-cell", "before-cell-7", before_cell.content_sha256)
        )
        before_shard = replace(before_shard, cells=tuple(before_links))
        after_shard = replace(before_shard, cells=tuple(after_links))

        self.assertEqual(
            tuple(range(27)),
            tuple(item.universe_ordinal for item in after_shard.cells),
        )
        changed_links = [
            index
            for index, (left, right) in enumerate(zip(before_shard.cells, after_shard.cells))
            if left != right
        ]
        self.assertEqual([7], changed_links)
        self.assertNotEqual(before_shard.content_sha256, after_shard.content_sha256)

        before_root = _root(first_shard=before_shard)
        after_root = _root(first_shard=after_shard, matrix_number=2)
        changed_shards = [
            index
            for index, (left, right) in enumerate(zip(before_root.shards, after_root.shards))
            if left != right
        ]
        self.assertEqual([0], changed_shards)
        self.assertEqual(before_root.phase_freeze, after_root.phase_freeze)
        self.assertEqual(before_root.core_spec_set, after_root.core_spec_set)
        self.assertEqual(
            EXPECTED_UNIVERSE_CELL_COUNT,
            after_root.supported_cell_count + after_root.unsupported_exclusion_count,
        )
        self.assertEqual(
            before_root.supported_cell_count + 1,
            after_root.supported_cell_count,
        )
        self.assertNotEqual(before_root.content_sha256, after_root.content_sha256)

    def test_root_requires_98_sorted_shards_and_derives_current_exact_partition(self) -> None:
        root = _root()
        self.assertEqual(EXPECTED_CORE_COUNT, len(root.shards))
        self.assertEqual(EXPECTED_SUPPORTED_CELL_COUNT, root.supported_cell_count)
        self.assertEqual(
            EXPECTED_UNSUPPORTED_EXCLUSION_COUNT,
            root.unsupported_exclusion_count,
        )
        self.assertEqual(ROOT_FORMAT, root.to_document()["format"])
        rendered = render_matrix_v1(root)
        self.assertEqual(
            "bda77789edd10345a88c5a84ed87cc4064b0ecd5250c289e3cfc51b43064165f",
            root.content_sha256,
        )
        self.assertEqual(
            "9aeb95d86f7c177258c7b870c23b21f8a059cae88eec4d3be7ec63b9b6138c76",
            sha256_bytes(rendered),
        )
        self.assertEqual(root, decode_matrix_v1(rendered))

        with self.assertRaises(PipelineError):
            replace(root, shards=root.shards[:-1])
        with self.assertRaises(PipelineError):
            replace(root, shards=(root.shards[1], root.shards[0], *root.shards[2:]))
        with self.assertRaises(PipelineError):
            replace(root, shards=(root.shards[0], root.shards[0], *root.shards[2:]))

    def test_authority_only_refresh_changes_root_without_changing_shards(self) -> None:
        before = _root()
        after = _root(captured_at="2026-08-14T22:00:00Z", phase_number=2)

        self.assertEqual(before.shards, after.shards)
        self.assertNotEqual(before.phase_freeze, after.phase_freeze)
        self.assertNotEqual(before.legacy_matrix, after.legacy_matrix)
        self.assertNotEqual(before.content_sha256, after.content_sha256)

    def test_summary_is_rejected_from_root_authority_and_counts_are_derived(self) -> None:
        root = _root()
        self.assertNotIn("summary", root.to_document())
        projection = decode_matrix_v2(root.legacy_root_json.encode("utf-8"))
        self.assertNotIn("summary", projection)
        projection["summary"] = {
            "supported_cell_count": root.supported_cell_count,
            "unsupported_exclusion_count": root.unsupported_exclusion_count,
        }
        with self.assertRaises(PipelineError):
            replace(
                root,
                legacy_root_json=matrix_v2_canonical_bytes(projection).decode("utf-8"),
            )

        document = root.to_document()
        document["supported_cell_count"] = root.supported_cell_count - 1
        document["content_sha256"] = _sha256(999)
        with self.assertRaises(PipelineError):
            MatrixRootV1.from_document(document)

    def test_wire_records_are_frozen_slotted_exact_and_self_authenticating(self) -> None:
        records = (_cell(), _shard(), _root())
        for record in records:
            with self.subTest(record=type(record).__name__):
                self.assertFalse(hasattr(record, "__dict__"))
                self.assertNotIn("content_sha256", inspect.signature(type(record)).parameters)
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, fields(record)[0].name, "replacement")

                document = record.to_document()
                document["content_sha256"] = _sha256(999)
                with self.assertRaises(PipelineError):
                    decode_matrix_v1(document)

                document = record.to_document()
                document["unexpected"] = True
                with self.assertRaises(PipelineError):
                    decode_matrix_v1(document)

        for bad_key, bad_value in (
            ("schema_version", True),
            ("format", "spruce-campaign-matrix-cell-v2"),
            ("local_only", 1),
            ("publication", "enabled"),
        ):
            document = _cell().to_document()
            document[bad_key] = bad_value
            with self.subTest(key=bad_key):
                with self.assertRaises(PipelineError):
                    MatrixCellV1.from_document(document)

    def test_strict_outer_wire_rejects_duplicate_keys_floats_and_scalar_aliases(self) -> None:
        raw = render_matrix_v1(_cell())
        duplicate = raw.replace(
            b'  "format":',
            b'  "format": "duplicate",\n  "format":',
            1,
        )
        with self.assertRaises(PipelineError):
            decode_matrix_v1(duplicate)

        document = _cell().to_document()
        document["universe_ordinal"] = 0.0
        with self.assertRaises(PipelineError):
            decode_matrix_v1(document)

        cyclic: list[object] = []
        cyclic.append(cyclic)
        document = _cell().to_document()
        document["coordinate"] = cyclic
        with self.assertRaises(PipelineError):
            decode_matrix_v1(document)
        with self.assertRaises(PipelineError):
            MatrixCellLinkV1(
                universe_ordinal=True,  # type: ignore[arg-type]
                partition=SUPPORTED_PARTITION,
                reference=_matrix_ref("matrix-cell", "boolean-ordinal", _sha256(1)),
            )

    def test_schema_is_local_closed_and_accepts_all_three_wire_objects(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        records = (_cell(), _shard(), _root())
        for record in records:
            with self.subTest(record=type(record).__name__):
                validator.validate(record.to_document())

        refs: list[str] = []

        def collect(value: object) -> None:
            if type(value) is dict:
                for key, item in value.items():
                    if key == "$ref":
                        refs.append(item)  # type: ignore[arg-type]
                    collect(item)
            elif type(value) is list:
                for item in value:
                    collect(item)

        collect(schema)
        self.assertTrue(refs)
        self.assertTrue(all(type(ref) is str and ref.startswith("#/") for ref in refs))
        self.assertEqual(
            "https://spruceui.local/schemas/campaign-matrix-v1.schema.json",
            schema["$id"],
        )

        invalid = _root().to_document()
        invalid["summary"] = {}
        self.assertTrue(tuple(validator.iter_errors(invalid)))

    def test_model_boundary_has_no_filesystem_process_or_dynamic_import_owner(self) -> None:
        tree = ast.parse(MODEL_PATH.read_text(encoding="utf-8"))
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

    def test_documents_and_decoded_models_do_not_alias_mutable_inputs(self) -> None:
        original = _root().to_document()
        working = copy.deepcopy(original)
        decoded = MatrixRootV1.from_document(working)
        working["shards"][0]["core_id"] = "changed"  # type: ignore[index]
        working["phase_freeze"]["path"] = "changed"  # type: ignore[index]
        self.assertEqual(original, decoded.to_document())
        self.assertEqual(original, json.loads(json.dumps(original)))

    def test_wrong_model_types_and_bad_coordinate_orders_fail_closed(self) -> None:
        with self.assertRaises(PipelineError):
            render_matrix_v1(MatrixCoordinateV1(
                core_id="core_000",
                track="main",
                chipset="universal",
                architecture="arm64",
            ))
        for core_ids in (
            _core_ids()[:-1],
            tuple(reversed(_core_ids())),
            (_core_ids()[0], _core_ids()[0], *_core_ids()[2:]),
            list(_core_ids()),
        ):
            with self.subTest(length=len(core_ids)):
                with self.assertRaises(PipelineError):
                    legacy_coordinate_order(core_ids)

        self.assertEqual(SHARD_FORMAT, _shard().to_document()["format"])
        self.assertEqual(ROOT_FORMAT, _root().to_document()["format"])


if __name__ == "__main__":
    unittest.main()
