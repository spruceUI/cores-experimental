"""Pure normalization and legacy materialization for campaign matrix v1.

This module owns the in-memory closure between normalized cell, shard, and
root records.  It performs no filesystem, store, process, clock, transaction,
or publication work.  Historical matrix-v2 ``summary`` is accepted only when
it equals the view derived from authenticated cells; it is never retained in
the normalized root and is regenerated for every legacy materialization.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Final

from ..errors import PipelineError
from ..foundation import sha256_bytes
from .legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
    render_matrix_v2,
)
from .matrix_model import (
    EXCLUSION_PARTITION,
    EXPECTED_CORE_COUNT,
    EXPECTED_UNIVERSE_CELL_COUNT,
    LEGACY_MATRIX_FORMAT,
    PROJECTION_COUNT,
    PROJECTION_ORDER,
    SUPPORTED_PARTITION,
    TRACK_ORDER,
    UNIVERSE_CELLS_PER_CORE,
    LegacyMatrixV2Identity,
    MatrixCellV1,
    MatrixCoordinateV1,
    MatrixRootV1,
    MatrixShardV1,
    legacy_coordinate_order,
    render_matrix_v1,
)
from .model import EvidenceRef
from .store import canonical_object_reference


_ROOT_SOURCE_KEYS: Final = frozenset(
    {
        "$schema",
        "audit",
        "campaign_id",
        "captured_at",
        "content_sha256",
        "directory_fingerprint_model",
        "expansion",
        "format",
        "hash_model",
        "inputs",
        "local_only",
        "marker",
        "publication",
        "schema_version",
        "summary",
        "supersedes",
        "supported_cells",
        "tracks",
        "unsupported_exclusions",
        "validation_ledger",
        "validation_scope",
    }
)
_ROOT_OMITTED_KEYS: Final = frozenset(
    {
        "content_sha256",
        "summary",
        "supported_cells",
        "unsupported_exclusions",
    }
)
_EXPANSION_KEYS: Final = frozenset(
    {
        "algorithm",
        "architecture_order",
        "catalog_core_count",
        "chipset_order",
        "core_order",
        "core_order_content_sha256",
        "potential_coordinate_count",
        "projection_count",
        "projections",
        "supported_cell_count",
        "supported_coordinate_order_content_sha256",
        "track_count",
        "track_order",
        "unsupported_coordinate_order_content_sha256",
        "unsupported_exclusion_count",
    }
)
_EXPANSION_ALGORITHM: Final = (
    "cross ordered tracks, sorted catalog cores, and ordered typed "
    "chipset/ABI projections; partition by catalog target support"
)
_ARCHITECTURE_ORDER: Final = ("arm64", "armhf")
_CHIPSET_ORDER: Final = (
    "universal",
    "a133p",
    "a33",
    "a523",
    "h700",
    "rk3326",
    "rk3566",
    "ssd202d",
)
_SUMMARY_KEYS: Final = frozenset(
    {
        "admitted_cell_count",
        "admitted_core_count",
        "architecture_counts",
        "branch_artifact_correlation",
        "chipset_counts",
        "deferred_cell_count",
        "evidence_pin_count",
        "lifecycle_counts",
        "logical_reuse_cell_count",
        "not_run_cell_count",
        "potential_coordinate_count",
        "producer_cell_count",
        "reproduction_run_count",
        "resolution_counts",
        "selected_run_count",
        "source_order_outlier_count",
        "supported_cell_count",
        "track_counts",
        "unique_established_build_identity_count",
        "unsupported_exclusion_count",
    }
)
MATRIX_STATE_RELATIVE: Final = ".local-e2e/campaign-state"


def matrix_object_reference(value: object) -> EvidenceRef:
    """Return the canonical raw-addressed store reference for one matrix object."""

    kinds = {
        MatrixCellV1: "matrix-cell",
        MatrixShardV1: "matrix-shard",
        MatrixRootV1: "matrix-root",
    }
    value_type = type(value)
    if value_type not in kinds:
        raise PipelineError("matrix object reference requires an exact wire model")
    return canonical_object_reference(
        state_relative=MATRIX_STATE_RELATIVE,
        kind=kinds[value_type],
        raw=render_matrix_v1(value),
        target_content_sha256=value.content_sha256,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class NormalizedMatrixV1:
    """Hydrated immutable root/shard/cell closure, ordered for legacy output."""

    root: MatrixRootV1
    root_reference: EvidenceRef
    shards: tuple[MatrixShardV1, ...]
    cells: tuple[MatrixCellV1, ...]

    def __post_init__(self) -> None:
        if type(self.root) is not MatrixRootV1:
            raise PipelineError("normalized closure root must be exact")
        if (
            type(self.root_reference) is not EvidenceRef
            or self.root_reference.kind != "matrix-root"
            or self.root_reference.target_content_sha256 != self.root.content_sha256
        ):
            raise PipelineError("normalized closure root reference is invalid")
        if type(self.shards) is not tuple or any(
            type(item) is not MatrixShardV1 for item in self.shards
        ):
            raise PipelineError("normalized closure shards must be an exact tuple")
        if type(self.cells) is not tuple or any(
            type(item) is not MatrixCellV1 for item in self.cells
        ):
            raise PipelineError("normalized closure cells must be an exact tuple")


def _require_mapping(
    value: object,
    *,
    label: str,
    keys: frozenset[str] | None = None,
) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise PipelineError(f"{label} must be an exact string-keyed object")
    if keys is not None and frozenset(value) != keys:
        raise PipelineError(
            f"{label} fields are not exact: "
            f"missing={sorted(keys - frozenset(value))}; "
            f"extra={sorted(frozenset(value) - keys)}"
        )
    return value


def _require_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact array")
    return value


def _require_string(value: object, *, label: str) -> str:
    if type(value) is not str or not value:
        raise PipelineError(f"{label} must be a nonempty exact string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PipelineError(f"{label} must be valid UTF-8") from exc
    return value


def _require_sha256(value: object, *, label: str) -> str:
    value = _require_string(value, label=label)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _line_count(raw: bytes) -> int:
    return raw.count(b"\n") + int(bool(raw) and not raw.endswith(b"\n"))


def _canonical_equal(left: object, right: object) -> bool:
    return matrix_v2_canonical_bytes(left) == matrix_v2_canonical_bytes(right)


def _coordinate_key(coordinate: MatrixCoordinateV1) -> tuple[str, int]:
    return coordinate.core_id, coordinate.universe_ordinal


def _payload(cell: MatrixCellV1) -> dict[str, object]:
    payload = decode_matrix_v2(cell.legacy_payload_json.encode("utf-8"))
    if not _canonical_equal(payload.get("coordinate"), cell.coordinate.to_document()):
        raise PipelineError("normalized cell payload coordinate is inconsistent")
    if matrix_v2_semantic_sha256(payload) != payload.get("content_sha256"):
        raise PipelineError("normalized cell legacy semantic digest is invalid")
    return payload


def _counter(
    payloads: tuple[dict[str, object], ...],
    *,
    parent: str,
    field: str,
    label: str,
) -> dict[str, int]:
    result: Counter[str] = Counter()
    for index, payload in enumerate(payloads):
        owner = _require_mapping(
            payload.get(parent), label=f"{label} cell {index} {parent}"
        )
        value = _require_string(
            owner.get(field), label=f"{label} cell {index} {parent}.{field}"
        )
        result[value] += 1
    return dict(result)


def derive_legacy_summary(
    cells: object,
) -> dict[str, object]:
    """Derive the complete legacy matrix-v2 summary from normalized cells."""

    if type(cells) is not tuple or any(type(item) is not MatrixCellV1 for item in cells):
        raise PipelineError("summary cells must be an exact MatrixCellV1 tuple")
    if len(cells) != EXPECTED_UNIVERSE_CELL_COUNT:
        raise PipelineError("summary requires the complete 2646-cell universe")
    supported_cells = tuple(
        cell for cell in cells if cell.partition == SUPPORTED_PARTITION
    )
    exclusions = tuple(
        cell for cell in cells if cell.partition == EXCLUSION_PARTITION
    )
    if len(supported_cells) + len(exclusions) != len(cells):
        raise PipelineError("summary cell partition is incomplete")
    payloads = tuple(_payload(cell) for cell in supported_cells)

    admission = _counter(
        payloads,
        parent="lifecycle",
        field="admission_state",
        label="summary admission",
    )
    evidence_states = _counter(
        payloads,
        parent="lifecycle",
        field="evidence_state",
        label="summary evidence",
    )
    execution = _counter(
        payloads,
        parent="lifecycle",
        field="execution_state",
        label="summary execution",
    )
    gha = _counter(
        payloads,
        parent="lifecycle",
        field="gha_state",
        label="summary gha",
    )
    architectures = _counter(
        payloads,
        parent="coordinate",
        field="architecture",
        label="summary architecture",
    )
    chipsets = _counter(
        payloads,
        parent="coordinate",
        field="chipset",
        label="summary chipset",
    )
    tracks = _counter(
        payloads,
        parent="coordinate",
        field="track",
        label="summary track",
    )
    artifacts = _counter(
        payloads,
        parent="branch_artifact_observation",
        field="artifact_validity",
        label="summary branch artifact",
    )
    resolutions = _counter(
        payloads,
        parent="resolution",
        field="resolution",
        label="summary resolution",
    )

    admitted_cores: set[str] = set()
    pin_ids: set[str] = set()
    selected_run_ids: set[str] = set()
    reproduction_run_ids: set[str] = set()
    established_build_identities: set[str] = set()
    source_order_outlier_count = 0
    for index, (cell, payload) in enumerate(zip(supported_cells, payloads)):
        lifecycle = _require_mapping(
            payload.get("lifecycle"), label=f"summary cell {index} lifecycle"
        )
        if lifecycle.get("admission_state") == "admitted":
            admitted_cores.add(cell.coordinate.core_id)

        build_identity = _require_mapping(
            payload.get("build_identity"),
            label=f"summary cell {index} build_identity",
        )
        build_state = _require_string(
            build_identity.get("state"),
            label=f"summary cell {index} build_identity.state",
        )
        if build_state == "established":
            established_build_identities.add(
                _require_sha256(
                    build_identity.get("content_sha256"),
                    label=f"summary cell {index} build identity digest",
                )
            )
        pin = build_identity.get("pin")
        if pin is not None:
            pin_mapping = _require_mapping(
                pin, label=f"summary cell {index} build_identity.pin"
            )
            pin_ids.add(
                _require_string(
                    pin_mapping.get("pin_id"),
                    label=f"summary cell {index} pin_id",
                )
            )

        evidence = _require_mapping(
            payload.get("evidence"), label=f"summary cell {index} evidence"
        )
        for name, target in (
            ("selected", selected_run_ids),
            ("reproduction", reproduction_run_ids),
        ):
            run = evidence.get(name)
            if run is not None:
                run_mapping = _require_mapping(
                    run, label=f"summary cell {index} evidence.{name}"
                )
                target.add(
                    _require_string(
                        run_mapping.get("run_id"),
                        label=f"summary cell {index} evidence.{name}.run_id",
                    )
                )

        outlier = _require_mapping(
            payload.get("outlier"), label=f"summary cell {index} outlier"
        )
        if "authorization" not in outlier:
            raise PipelineError(f"summary cell {index} outlier authorization is missing")
        if outlier["authorization"] is not None:
            source_order_outlier_count += 1

    summary: dict[str, object] = {
        "admitted_cell_count": admission.get("admitted", 0),
        "admitted_core_count": len(admitted_cores),
        "architecture_counts": architectures,
        "branch_artifact_correlation": artifacts,
        "chipset_counts": chipsets,
        "deferred_cell_count": admission.get("deferred", 0),
        "evidence_pin_count": len(pin_ids),
        "lifecycle_counts": {
            "admission": admission,
            "evidence": evidence_states,
            "execution": execution,
            "gha": gha,
        },
        "logical_reuse_cell_count": execution.get("reused", 0),
        "not_run_cell_count": execution.get("not-run", 0),
        "potential_coordinate_count": len(cells),
        "producer_cell_count": execution.get("built", 0),
        "reproduction_run_count": len(reproduction_run_ids),
        "resolution_counts": resolutions,
        "selected_run_count": len(selected_run_ids),
        "source_order_outlier_count": source_order_outlier_count,
        "supported_cell_count": len(supported_cells),
        "track_counts": tracks,
        "unique_established_build_identity_count": len(
            established_build_identities
        ),
        "unsupported_exclusion_count": len(exclusions),
    }
    if frozenset(summary) != _SUMMARY_KEYS:
        raise PipelineError("derived legacy summary fields are not exact")
    return summary


def _validate_expansion(
    expansion_value: object,
    *,
    core_ids: tuple[str, ...],
    cells: tuple[MatrixCellV1, ...],
) -> None:
    expansion = _require_mapping(
        expansion_value, label="legacy matrix expansion", keys=_EXPANSION_KEYS
    )
    supported_coordinates = [
        cell.coordinate.to_document()
        for cell in cells
        if cell.partition == SUPPORTED_PARTITION
    ]
    exclusion_coordinates = [
        cell.coordinate.to_document()
        for cell in cells
        if cell.partition == EXCLUSION_PARTITION
    ]
    expected_projections = [
        {"architecture": architecture, "chipset": chipset}
        for chipset, architecture in PROJECTION_ORDER
    ]
    expected: dict[str, object] = {
        "algorithm": _EXPANSION_ALGORITHM,
        "architecture_order": list(_ARCHITECTURE_ORDER),
        "catalog_core_count": len(core_ids),
        "chipset_order": list(_CHIPSET_ORDER),
        "core_order": "ascending-core-id",
        "core_order_content_sha256": sha256_bytes(
            matrix_v2_canonical_bytes(list(core_ids))
        ),
        "potential_coordinate_count": len(cells),
        "projection_count": PROJECTION_COUNT,
        "projections": expected_projections,
        "supported_cell_count": len(supported_coordinates),
        "supported_coordinate_order_content_sha256": sha256_bytes(
            matrix_v2_canonical_bytes(supported_coordinates)
        ),
        "track_count": len(TRACK_ORDER),
        "track_order": list(TRACK_ORDER),
        "unsupported_coordinate_order_content_sha256": sha256_bytes(
            matrix_v2_canonical_bytes(exclusion_coordinates)
        ),
        "unsupported_exclusion_count": len(exclusion_coordinates),
    }
    if not _canonical_equal(expansion, expected):
        raise PipelineError("legacy matrix expansion is not the derived exact view")


def _validate_phase_freeze_binding(
    document: dict[str, object],
    phase_freeze: EvidenceRef,
) -> None:
    inputs = _require_mapping(document.get("inputs"), label="legacy matrix inputs")
    binding = _require_mapping(
        inputs.get("phase_freeze"), label="legacy matrix phase_freeze input"
    )
    expected = {
        "content_sha256": phase_freeze.target_content_sha256,
        "file_sha256": phase_freeze.file_sha256,
    }
    for key, expected_value in expected.items():
        if binding.get(key) != expected_value:
            raise PipelineError(f"legacy matrix phase_freeze {key} is inconsistent")


def _cell_from_payload(value: object, *, partition: str) -> MatrixCellV1:
    payload = _require_mapping(value, label=f"legacy {partition} cell")
    coordinate = MatrixCoordinateV1.from_document(payload.get("coordinate"))
    return MatrixCellV1(
        universe_ordinal=coordinate.universe_ordinal,
        coordinate=coordinate,
        partition=partition,
        legacy_payload_json=matrix_v2_canonical_bytes(payload).decode("utf-8"),
    )


def _validate_link_closure(
    closure: NormalizedMatrixV1,
) -> tuple[dict[str, object], ...]:
    if len(closure.shards) != EXPECTED_CORE_COUNT:
        raise PipelineError("normalized closure must contain exactly 98 shards")
    if len(closure.cells) != EXPECTED_UNIVERSE_CELL_COUNT:
        raise PipelineError("normalized closure must contain exactly 2646 cells")
    core_ids = tuple(shard.core_id for shard in closure.shards)
    root_core_ids = tuple(link.core_id for link in closure.root.shards)
    if core_ids != root_core_ids:
        raise PipelineError("normalized closure shard order differs from the root")
    expected_coordinates = legacy_coordinate_order(core_ids)
    actual_coordinates = tuple(cell.coordinate for cell in closure.cells)
    if actual_coordinates != expected_coordinates:
        raise PipelineError(
            "normalized closure cells are not in track/core/projection order"
        )

    by_key = {_coordinate_key(cell.coordinate): cell for cell in closure.cells}
    if len(by_key) != len(closure.cells):
        raise PipelineError("normalized closure contains duplicate cell coordinates")
    cell_references = {
        key: matrix_object_reference(cell) for key, cell in by_key.items()
    }
    expected_shards: list[MatrixShardV1] = []
    for core_id in core_ids:
        expected_shards.append(
            MatrixShardV1(
                core_id=core_id,
                cells=tuple(
                    by_key[(core_id, ordinal)].link(
                        cell_references[(core_id, ordinal)]
                    )
                    for ordinal in range(UNIVERSE_CELLS_PER_CORE)
                ),
            )
        )
    if closure.shards != tuple(expected_shards):
        raise PipelineError("normalized closure shard-to-cell links are invalid")
    expected_root_links = tuple(
        shard.link(matrix_object_reference(shard)) for shard in closure.shards
    )
    if closure.root.shards != expected_root_links:
        raise PipelineError("normalized closure root-to-shard links are invalid")
    if closure.root_reference != matrix_object_reference(closure.root):
        raise PipelineError("normalized closure root reference is invalid")

    payloads = tuple(_payload(cell) for cell in closure.cells)
    projection = decode_matrix_v2(closure.root.legacy_root_json.encode("utf-8"))
    _validate_phase_freeze_binding(projection, closure.root.phase_freeze)
    _validate_expansion(
        projection.get("expansion"), core_ids=core_ids, cells=closure.cells
    )
    return payloads


def _materialize_validated(closure: NormalizedMatrixV1) -> bytes:
    payloads = _validate_link_closure(closure)
    supported = [
        payload
        for cell, payload in zip(closure.cells, payloads)
        if cell.partition == SUPPORTED_PARTITION
    ]
    exclusions = [
        payload
        for cell, payload in zip(closure.cells, payloads)
        if cell.partition == EXCLUSION_PARTITION
    ]
    document = decode_matrix_v2(closure.root.legacy_root_json.encode("utf-8"))
    document["supported_cells"] = supported
    document["unsupported_exclusions"] = exclusions
    document["summary"] = derive_legacy_summary(closure.cells)
    document["content_sha256"] = matrix_v2_semantic_sha256(document)
    raw = render_matrix_v2(document)

    identity = closure.root.legacy_matrix
    observed = LegacyMatrixV2Identity(
        semantic_sha256=document["content_sha256"],  # type: ignore[arg-type]
        file_sha256=sha256_bytes(raw),
        size=len(raw),
        lines=_line_count(raw),
    )
    if observed != identity:
        raise PipelineError("materialized legacy matrix identity differs from root")
    return raw


def normalize_matrix_v2(
    raw: object,
    *,
    phase_freeze: EvidenceRef,
    core_spec_set: EvidenceRef,
) -> NormalizedMatrixV1:
    """Normalize one exact rendered legacy matrix-v2 byte snapshot."""

    if type(raw) is not bytes:
        raise PipelineError("legacy matrix input must be exact bytes")
    document = decode_matrix_v2(raw)
    _require_mapping(document, label="legacy matrix", keys=_ROOT_SOURCE_KEYS)
    if render_matrix_v2(document) != raw:
        raise PipelineError("legacy matrix input is not its exact deterministic rendering")
    if document.get("format") != LEGACY_MATRIX_FORMAT:
        raise PipelineError("legacy matrix format is invalid")
    embedded = _require_sha256(
        document.get("content_sha256"), label="legacy matrix content_sha256"
    )
    if embedded != matrix_v2_semantic_sha256(document):
        raise PipelineError("legacy matrix content_sha256 is invalid")
    if type(phase_freeze) is not EvidenceRef or type(core_spec_set) is not EvidenceRef:
        raise PipelineError("normalization authorities must be exact EvidenceRefs")
    _validate_phase_freeze_binding(document, phase_freeze)

    source_supported = _require_list(
        document.get("supported_cells"), label="legacy supported_cells"
    )
    source_exclusions = _require_list(
        document.get("unsupported_exclusions"),
        label="legacy unsupported_exclusions",
    )
    source_cells = tuple(
        _cell_from_payload(value, partition=SUPPORTED_PARTITION)
        for value in source_supported
    ) + tuple(
        _cell_from_payload(value, partition=EXCLUSION_PARTITION)
        for value in source_exclusions
    )
    by_key = {_coordinate_key(cell.coordinate): cell for cell in source_cells}
    if len(by_key) != len(source_cells):
        raise PipelineError("legacy matrix contains duplicate coordinates")
    core_ids = tuple(sorted({cell.coordinate.core_id for cell in source_cells}))
    if len(core_ids) != EXPECTED_CORE_COUNT:
        raise PipelineError("legacy matrix must contain exactly 98 core IDs")
    coordinates = legacy_coordinate_order(core_ids)
    try:
        ordered_cells = tuple(by_key[_coordinate_key(item)] for item in coordinates)
    except KeyError as exc:
        raise PipelineError("legacy matrix coordinate universe is incomplete") from exc
    if len(ordered_cells) != len(source_cells):
        raise PipelineError("legacy matrix coordinate universe is not exact")

    expected_supported = [
        _payload(cell)
        for cell in ordered_cells
        if cell.partition == SUPPORTED_PARTITION
    ]
    expected_exclusions = [
        _payload(cell)
        for cell in ordered_cells
        if cell.partition == EXCLUSION_PARTITION
    ]
    if not _canonical_equal(source_supported, expected_supported):
        raise PipelineError("legacy supported cell order is not exact")
    if not _canonical_equal(source_exclusions, expected_exclusions):
        raise PipelineError("legacy exclusion order is not exact")

    derived_summary = derive_legacy_summary(ordered_cells)
    if not _canonical_equal(document.get("summary"), derived_summary):
        raise PipelineError("legacy matrix summary is stale or unauthenticated")
    _validate_expansion(
        document.get("expansion"), core_ids=core_ids, cells=ordered_cells
    )

    cell_references = {
        _coordinate_key(cell.coordinate): matrix_object_reference(cell)
        for cell in ordered_cells
    }
    shards = tuple(
        MatrixShardV1(
            core_id=core_id,
            cells=tuple(
                by_key[(core_id, ordinal)].link(
                    cell_references[(core_id, ordinal)]
                )
                for ordinal in range(UNIVERSE_CELLS_PER_CORE)
            ),
        )
        for core_id in core_ids
    )
    shard_references = tuple(matrix_object_reference(shard) for shard in shards)
    root_projection = {
        key: value for key, value in document.items() if key not in _ROOT_OMITTED_KEYS
    }
    root = MatrixRootV1(
        campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
        captured_at=document.get("captured_at"),  # type: ignore[arg-type]
        phase_freeze=phase_freeze,
        core_spec_set=core_spec_set,
        legacy_matrix=LegacyMatrixV2Identity(
            semantic_sha256=embedded,
            file_sha256=sha256_bytes(raw),
            size=len(raw),
            lines=_line_count(raw),
        ),
        legacy_root_json=matrix_v2_canonical_bytes(root_projection).decode("utf-8"),
        shards=tuple(
            shard.link(reference)
            for shard, reference in zip(shards, shard_references)
        ),
    )
    closure = NormalizedMatrixV1(
        root=root,
        root_reference=matrix_object_reference(root),
        shards=shards,
        cells=ordered_cells,
    )
    materialized = _materialize_validated(closure)
    if materialized != raw:
        raise PipelineError("normalized closure does not reproduce source bytes")
    return closure


def validate_normalized_matrix(value: object) -> None:
    """Validate every cell/shard/root link and the expected legacy identity."""

    if type(value) is not NormalizedMatrixV1:
        raise PipelineError("normalized matrix closure must be exact")
    _materialize_validated(value)


def materialize_matrix_v2(value: object) -> bytes:
    """Regenerate exact legacy matrix-v2 bytes from one validated closure."""

    if type(value) is not NormalizedMatrixV1:
        raise PipelineError("normalized matrix closure must be exact")
    return _materialize_validated(value)


__all__ = [
    "MATRIX_STATE_RELATIVE",
    "NormalizedMatrixV1",
    "derive_legacy_summary",
    "matrix_object_reference",
    "materialize_matrix_v2",
    "normalize_matrix_v2",
    "validate_normalized_matrix",
]
