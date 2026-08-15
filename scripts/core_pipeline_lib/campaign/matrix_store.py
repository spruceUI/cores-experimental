"""Persistent normalized-matrix closure over :mod:`campaign.store`.

The normalized matrix wire carries complete raw-addressed references from a
root to 98 shards and from each shard to its 27 cells.  This module is the
small imperative adapter that stages that immutable closure and hydrates it
again.  It owns no path formula, filesystem primitive, mutable pointer, or
legacy-matrix construction policy; those remain in ``CampaignStore`` and the
pure matrix model/materializer.

Staging validates the complete closure before its first write, then publishes
cells, shards, and the root in dependency order.  A failure may leave valid
immutable children behind, which is the campaign store's intentional retry
model.  The root is the sole closure locator and is always published last.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import PipelineError
from .matrix_materialize import (
    NormalizedMatrixV1,
    matrix_object_reference,
    validate_normalized_matrix,
)
from .matrix_model import (
    EXPECTED_CORE_COUNT,
    EXPECTED_UNIVERSE_CELL_COUNT,
    MatrixCellV1,
    MatrixRootV1,
    MatrixShardV1,
    decode_matrix_v1,
    legacy_coordinate_order,
    render_matrix_v1,
)
from .model import EvidenceRef
from .store import CampaignStore, StoreResult


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredNormalizedMatrixV1:
    """Results for one dependency-ordered immutable closure publication."""

    cells: tuple[StoreResult, ...]
    shards: tuple[StoreResult, ...]
    root: StoreResult

    def __post_init__(self) -> None:
        if (
            type(self.cells) is not tuple
            or len(self.cells) != EXPECTED_UNIVERSE_CELL_COUNT
            or any(
                type(item) is not StoreResult
                or item.reference.kind != "matrix-cell"
                for item in self.cells
            )
        ):
            raise PipelineError("stored matrix cells are invalid")
        if (
            type(self.shards) is not tuple
            or len(self.shards) != EXPECTED_CORE_COUNT
            or any(
                type(item) is not StoreResult
                or item.reference.kind != "matrix-shard"
                for item in self.shards
            )
        ):
            raise PipelineError("stored matrix shards are invalid")
        if type(self.root) is not StoreResult or self.root.reference.kind != "matrix-root":
            raise PipelineError("stored matrix root is invalid")
        _require_unique_references(
            tuple(item.reference for item in self.cells),
            label="stored matrix cells",
        )
        _require_unique_references(
            tuple(item.reference for item in self.shards),
            label="stored matrix shards",
        )

    @property
    def root_reference(self) -> EvidenceRef:
        """Return the one resolvable locator for the stored closure."""

        return self.root.reference


def _require_store(value: object) -> CampaignStore:
    if not isinstance(value, CampaignStore):
        raise PipelineError("normalized matrix storage requires CampaignStore")
    return value


def _require_unique_references(
    references: tuple[EvidenceRef, ...],
    *,
    label: str,
) -> None:
    if len(set(references)) != len(references):
        raise PipelineError(f"{label} contain duplicate references")
    paths = tuple(reference.path for reference in references)
    if len(set(paths)) != len(paths):
        raise PipelineError(f"{label} contain duplicate paths")


def _read_matrix_object(
    store: CampaignStore,
    reference: EvidenceRef,
    *,
    expected_type: type[MatrixCellV1] | type[MatrixShardV1] | type[MatrixRootV1],
    label: str,
) -> MatrixCellV1 | MatrixShardV1 | MatrixRootV1:
    raw = store.read_exact(reference)
    value = decode_matrix_v1(raw)
    if type(value) is not expected_type:
        raise PipelineError(f"{label} has the wrong normalized matrix type")
    if matrix_object_reference(value) != reference:
        raise PipelineError(f"{label} reference is not canonical for its bytes")
    return value


def stage_normalized_matrix(
    store: CampaignStore,
    closure: NormalizedMatrixV1,
) -> StoredNormalizedMatrixV1:
    """Create or verify one complete closure, publishing its root last."""

    store = _require_store(store)
    if type(closure) is not NormalizedMatrixV1:
        raise PipelineError("normalized matrix closure must be exact")

    # This traverses every link and reproduces the legacy matrix before the
    # first create-or-verify call.  Once it passes, the frozen closure cannot
    # drift between child publications.
    validate_normalized_matrix(closure)

    cell_results = tuple(
        store.create_or_verify(
            reference=matrix_object_reference(cell),
            raw=render_matrix_v1(cell),
        )
        for cell in closure.cells
    )
    shard_results = tuple(
        store.create_or_verify(
            reference=matrix_object_reference(shard),
            raw=render_matrix_v1(shard),
        )
        for shard in closure.shards
    )
    root_result = store.create_or_verify(
        reference=closure.root_reference,
        raw=render_matrix_v1(closure.root),
    )
    result = StoredNormalizedMatrixV1(
        cells=cell_results,
        shards=shard_results,
        root=root_result,
    )
    expected_cell_references = tuple(
        matrix_object_reference(cell) for cell in closure.cells
    )
    expected_shard_references = tuple(
        matrix_object_reference(shard) for shard in closure.shards
    )
    if tuple(item.reference for item in result.cells) != expected_cell_references:
        raise PipelineError("stored matrix cell results differ from the closure")
    if tuple(item.reference for item in result.shards) != expected_shard_references:
        raise PipelineError("stored matrix shard results differ from the closure")
    if result.root_reference != closure.root_reference:
        raise PipelineError("stored matrix root result differs from the closure")
    return result


def load_normalized_matrix(
    store: CampaignStore,
    root_reference: EvidenceRef,
) -> NormalizedMatrixV1:
    """Hydrate and authenticate a complete closure from its root reference."""

    store = _require_store(store)
    if type(root_reference) is not EvidenceRef or root_reference.kind != "matrix-root":
        raise PipelineError("normalized matrix root reference is invalid")

    root_value = _read_matrix_object(
        store,
        root_reference,
        expected_type=MatrixRootV1,
        label="normalized matrix root",
    )
    assert type(root_value) is MatrixRootV1
    root = root_value

    shard_references = tuple(link.reference for link in root.shards)
    _require_unique_references(shard_references, label="normalized matrix shards")
    shards: list[MatrixShardV1] = []
    for root_link in root.shards:
        shard_value = _read_matrix_object(
            store,
            root_link.reference,
            expected_type=MatrixShardV1,
            label=f"normalized matrix shard {root_link.core_id}",
        )
        assert type(shard_value) is MatrixShardV1
        shard = shard_value
        if shard.link(root_link.reference) != root_link:
            raise PipelineError("normalized matrix root-to-shard link is invalid")
        shards.append(shard)

    cell_references = tuple(
        link.reference for shard in shards for link in shard.cells
    )
    _require_unique_references(cell_references, label="normalized matrix cells")
    cells_by_coordinate: dict[tuple[str, int], MatrixCellV1] = {}
    for shard in shards:
        for shard_link in shard.cells:
            cell_value = _read_matrix_object(
                store,
                shard_link.reference,
                expected_type=MatrixCellV1,
                label=(
                    "normalized matrix cell "
                    f"{shard.core_id}/{shard_link.universe_ordinal}"
                ),
            )
            assert type(cell_value) is MatrixCellV1
            cell = cell_value
            if cell.link(shard_link.reference) != shard_link:
                raise PipelineError("normalized matrix shard-to-cell link is invalid")
            if cell.coordinate.core_id != shard.core_id:
                raise PipelineError("normalized matrix cell belongs to another shard")
            key = (cell.coordinate.core_id, cell.universe_ordinal)
            if key in cells_by_coordinate:
                raise PipelineError("normalized matrix contains duplicate cells")
            cells_by_coordinate[key] = cell

    core_ids = tuple(shard.core_id for shard in shards)
    coordinates = legacy_coordinate_order(core_ids)
    try:
        cells = tuple(
            cells_by_coordinate[(coordinate.core_id, coordinate.universe_ordinal)]
            for coordinate in coordinates
        )
    except KeyError as exc:
        raise PipelineError("normalized matrix cell closure is incomplete") from exc
    if len(cells_by_coordinate) != len(cells):
        raise PipelineError("normalized matrix cell closure is not exact")

    closure = NormalizedMatrixV1(
        root=root,
        root_reference=root_reference,
        shards=tuple(shards),
        cells=cells,
    )
    validate_normalized_matrix(closure)
    return closure


__all__ = [
    "StoredNormalizedMatrixV1",
    "load_normalized_matrix",
    "stage_normalized_matrix",
]
