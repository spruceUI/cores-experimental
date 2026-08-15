"""Strict pure wire models for normalized campaign matrix storage.

The normalized format separates global authority, per-core membership, and
individual coordinate payloads into root, shard, and cell identities.  A
cell's stable universe ordinal is independent of whether that coordinate is
supported, so a support/exclusion transition changes one cell, its shard, and
the root without renumbering any peer.

Shard and root links carry complete role-specific ``EvidenceRef`` values.
Their semantic target identifies the child model while their raw digest, size,
and path make the child directly resolvable in the existing campaign CAS.

Historical matrix-v2 payloads contain finite floats.  They are retained as
canonical legacy JSON *strings* inside the strict no-float campaign identity
wire.  The legacy root projection deliberately omits both cell arrays, the
legacy root digest, and ``summary``; the latter is a derived materializer view,
never normalized authority.  This module performs no filesystem, CAS,
process, clock, import discovery, or transaction work.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import re
from typing import ClassVar, Final, TypeAlias

from ..errors import PipelineError
from .json_wire import (
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
    validate_utf8_string,
)
from .legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
)
from .model import EvidenceRef


SCHEMA_VERSION: Final = 1
CELL_FORMAT: Final = "spruce-campaign-matrix-cell-v1"
SHARD_FORMAT: Final = "spruce-campaign-matrix-shard-v1"
ROOT_FORMAT: Final = "spruce-campaign-matrix-root-v1"
LEGACY_MATRIX_FORMAT: Final = "spruce-host-core-campaign-matrix-v2"
PUBLICATION: Final = "disabled"

EXPECTED_CORE_COUNT: Final = 98
TRACK_ORDER: Final = ("main", "nightly", "edge")
PROJECTION_ORDER: Final = (
    ("universal", "arm64"),
    ("universal", "armhf"),
    ("a133p", "arm64"),
    ("a33", "armhf"),
    ("a523", "arm64"),
    ("h700", "arm64"),
    ("rk3326", "arm64"),
    ("rk3566", "arm64"),
    ("ssd202d", "armhf"),
)
PROJECTION_COUNT: Final = len(PROJECTION_ORDER)
UNIVERSE_CELLS_PER_CORE: Final = len(TRACK_ORDER) * PROJECTION_COUNT
EXPECTED_UNIVERSE_CELL_COUNT: Final = (
    EXPECTED_CORE_COUNT * UNIVERSE_CELLS_PER_CORE
)
EXPECTED_SUPPORTED_CELL_COUNT: Final = 2_538
EXPECTED_UNSUPPORTED_EXCLUSION_COUNT: Final = 108

SUPPORTED_PARTITION: Final = "supported"
EXCLUSION_PARTITION: Final = "unsupported-exclusion"
PARTITIONS: Final = frozenset({SUPPORTED_PARTITION, EXCLUSION_PARTITION})

_CORE_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_IDENTIFIER_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECONDS_RE: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

_COORDINATE_KEYS: Final = frozenset(
    {"architecture", "chipset", "core_id", "marker", "track"}
)
_SUPPORTED_LEGACY_CELL_KEYS: Final = frozenset(
    {
        "branch_artifact_observation",
        "build_identity",
        "content_sha256",
        "coordinate",
        "evidence",
        "lifecycle",
        "lineage",
        "outlier",
        "outputs",
        "performance",
        "resolution",
        "reuse",
        "version_slice",
    }
)
_EXCLUSION_LEGACY_CELL_KEYS: Final = frozenset(
    {
        "branch_artifact_observation",
        "catalog_source",
        "content_sha256",
        "coordinate",
        "edge_candidate",
        "reason",
        "supported_architectures",
    }
)
_LEGACY_ROOT_PROJECTION_KEYS: Final = frozenset(
    {
        "$schema",
        "audit",
        "campaign_id",
        "captured_at",
        "directory_fingerprint_model",
        "expansion",
        "format",
        "hash_model",
        "inputs",
        "local_only",
        "marker",
        "publication",
        "schema_version",
        "supersedes",
        "tracks",
        "validation_ledger",
        "validation_scope",
    }
)


def _require_exact_string(value: object, *, label: str) -> str:
    value = validate_utf8_string(value, label=label)
    if "\x00" in value:
        raise PipelineError(f"{label} must not contain NUL")
    return value


def _require_identifier(value: object, *, label: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_core_id(value: object, *, label: str = "core_id") -> str:
    value = _require_exact_string(value, label=label)
    if _CORE_ID_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} is not a canonical core identifier")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _require_timestamp(value: object, *, label: str) -> str:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be an exact UTC-second timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise PipelineError(f"{label} must be a real UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise PipelineError(f"{label} is not canonical")
    return value


def _require_nonnegative_int(value: object, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PipelineError(f"{label} must be a nonnegative exact integer")
    return value


def _require_positive_int(value: object, *, label: str) -> int:
    if type(value) is not int or value < 1:
        raise PipelineError(f"{label} must be a positive exact integer")
    return value


def _require_exact_document(
    value: object,
    *,
    keys: frozenset[str],
    label: str,
    format_value: str | None = None,
) -> dict[str, object]:
    document = decode_identity_object(value, label=label)
    actual = frozenset(document)
    if actual != keys:
        raise PipelineError(
            f"{label} fields are not exact: "
            f"missing={sorted(keys - actual)}; extra={sorted(actual - keys)}"
        )
    if format_value is not None:
        if type(document.get("schema_version")) is not int or document.get(
            "schema_version"
        ) != SCHEMA_VERSION:
            raise PipelineError(f"{label} schema_version is invalid")
        if type(document.get("format")) is not str or document.get(
            "format"
        ) != format_value:
            raise PipelineError(f"{label} format is invalid")
        if document.get("local_only") is not True:
            raise PipelineError(f"{label} must be local-only")
        if type(document.get("publication")) is not str or document.get(
            "publication"
        ) != PUBLICATION:
            raise PipelineError(f"{label} publication must be disabled")
    return document


def _with_content_sha256(material: dict[str, object]) -> dict[str, object]:
    document = dict(material)
    document["content_sha256"] = canonical_json_sha256(material)
    return document


def _require_content_sha256(
    document: dict[str, object],
    material: dict[str, object],
    *,
    label: str,
) -> None:
    actual = _require_sha256(
        document.get("content_sha256"),
        label=f"{label} content_sha256",
    )
    if actual != canonical_json_sha256(material):
        raise PipelineError(f"{label} content_sha256 is invalid")


def _require_evidence_ref(
    value: object,
    *,
    label: str,
    kinds: frozenset[str],
) -> EvidenceRef:
    if type(value) is not EvidenceRef:
        raise PipelineError(f"{label} must be an exact EvidenceRef")
    if value.kind not in kinds or value.target_content_sha256 is None:
        raise PipelineError(f"{label} must be a semantic {sorted(kinds)} reference")
    return value


def _decode_canonical_legacy_object(value: object, *, label: str) -> dict[str, object]:
    text = _require_exact_string(value, label=label)
    raw = text.encode("utf-8")
    decoded = decode_matrix_v2(raw)
    if matrix_v2_canonical_bytes(decoded) != raw:
        raise PipelineError(f"{label} must be canonical compact legacy matrix JSON")
    return decoded


def _require_legacy_cell(
    value: object,
    *,
    partition: str,
    coordinate: "MatrixCoordinateV1",
) -> str:
    text = _require_exact_string(value, label="legacy cell JSON")
    payload = _decode_canonical_legacy_object(text, label="legacy cell JSON")
    expected_keys = (
        _SUPPORTED_LEGACY_CELL_KEYS
        if partition == SUPPORTED_PARTITION
        else _EXCLUSION_LEGACY_CELL_KEYS
    )
    if frozenset(payload) != expected_keys:
        raise PipelineError(
            "legacy cell fields do not match its normalized partition: "
            f"missing={sorted(expected_keys - frozenset(payload))}; "
            f"extra={sorted(frozenset(payload) - expected_keys)}"
        )
    legacy_coordinate = payload.get("coordinate")
    if type(legacy_coordinate) is not dict or frozenset(
        legacy_coordinate
    ) != _COORDINATE_KEYS:
        raise PipelineError("legacy cell coordinate fields are not exact")
    if legacy_coordinate != coordinate.to_document():
        raise PipelineError("legacy cell coordinate differs from normalized coordinate")
    actual_digest = _require_sha256(
        payload.get("content_sha256"), label="legacy cell content_sha256"
    )
    if actual_digest != matrix_v2_semantic_sha256(payload):
        raise PipelineError("legacy cell content_sha256 is invalid")
    return text


def _require_legacy_root_projection(
    value: object,
    *,
    campaign_id: str,
    captured_at: str,
    supported_cell_count: int,
    unsupported_exclusion_count: int,
) -> str:
    text = _require_exact_string(value, label="legacy root projection JSON")
    projection = _decode_canonical_legacy_object(
        text, label="legacy root projection JSON"
    )
    actual_keys = frozenset(projection)
    if actual_keys != _LEGACY_ROOT_PROJECTION_KEYS:
        raise PipelineError(
            "legacy root projection fields are not exact: "
            f"missing={sorted(_LEGACY_ROOT_PROJECTION_KEYS - actual_keys)}; "
            f"extra={sorted(actual_keys - _LEGACY_ROOT_PROJECTION_KEYS)}"
        )
    fixed_values = {
        "schema_version": 2,
        "format": LEGACY_MATRIX_FORMAT,
        "campaign_id": campaign_id,
        "captured_at": captured_at,
        "marker": "test",
        "local_only": True,
        "publication": PUBLICATION,
    }
    for key, expected in fixed_values.items():
        actual = projection.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise PipelineError(f"legacy root projection {key} is invalid")
    expansion = projection.get("expansion")
    if type(expansion) is not dict:
        raise PipelineError("legacy root expansion must be an exact object")
    expansion_values = {
        "catalog_core_count": EXPECTED_CORE_COUNT,
        "track_count": len(TRACK_ORDER),
        "projection_count": PROJECTION_COUNT,
        "potential_coordinate_count": EXPECTED_UNIVERSE_CELL_COUNT,
        "supported_cell_count": supported_cell_count,
        "unsupported_exclusion_count": unsupported_exclusion_count,
    }
    for key, expected in expansion_values.items():
        actual = expansion.get(key)
        if type(actual) is not int or actual != expected:
            raise PipelineError(f"legacy root expansion {key} is invalid")
    expected_projections = [
        {"architecture": architecture, "chipset": chipset}
        for chipset, architecture in PROJECTION_ORDER
    ]
    if expansion.get("track_order") != list(TRACK_ORDER):
        raise PipelineError("legacy root track_order is invalid")
    if expansion.get("projections") != expected_projections:
        raise PipelineError("legacy root projection order is invalid")
    return text


def _require_partition(value: object, *, label: str = "matrix partition") -> str:
    if type(value) is not str or value not in PARTITIONS:
        raise PipelineError(f"{label} is invalid")
    return value


def _require_ordinal(value: object, *, label: str = "universe ordinal") -> int:
    if (
        type(value) is not int
        or value < 0
        or value >= UNIVERSE_CELLS_PER_CORE
    ):
        raise PipelineError(
            f"{label} must be an exact integer in [0, "
            f"{UNIVERSE_CELLS_PER_CORE - 1}]"
        )
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixCoordinateV1:
    """One coordinate in the fixed 27-position universe for a core."""

    core_id: str
    track: str
    chipset: str
    architecture: str
    marker: str = "test"

    _KEYS: ClassVar[frozenset[str]] = _COORDINATE_KEYS

    def __post_init__(self) -> None:
        _require_core_id(self.core_id)
        _require_exact_string(self.track, label="matrix coordinate track")
        _require_exact_string(self.chipset, label="matrix coordinate chipset")
        _require_exact_string(
            self.architecture, label="matrix coordinate architecture"
        )
        if self.track not in TRACK_ORDER:
            raise PipelineError("matrix coordinate track is not in the fixed order")
        if (self.chipset, self.architecture) not in PROJECTION_ORDER:
            raise PipelineError("matrix coordinate projection is not in the fixed order")
        if type(self.marker) is not str or self.marker != "test":
            raise PipelineError("matrix coordinate marker must be test")

    @property
    def universe_ordinal(self) -> int:
        return (
            TRACK_ORDER.index(self.track) * PROJECTION_COUNT
            + PROJECTION_ORDER.index((self.chipset, self.architecture))
        )

    def to_document(self) -> dict[str, object]:
        return {
            "core_id": self.core_id,
            "track": self.track,
            "chipset": self.chipset,
            "architecture": self.architecture,
            "marker": self.marker,
        }

    @classmethod
    def from_document(cls, value: object) -> "MatrixCoordinateV1":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="matrix coordinate",
        )
        return cls(
            core_id=document.get("core_id"),  # type: ignore[arg-type]
            track=document.get("track"),  # type: ignore[arg-type]
            chipset=document.get("chipset"),  # type: ignore[arg-type]
            architecture=document.get("architecture"),  # type: ignore[arg-type]
            marker=document.get("marker"),  # type: ignore[arg-type]
        )


def coordinate_for_ordinal(core_id: object, ordinal: object) -> MatrixCoordinateV1:
    """Return the immutable coordinate assigned to one per-core ordinal."""

    core_id = _require_core_id(core_id)
    ordinal = _require_ordinal(ordinal)
    track_index, projection_index = divmod(ordinal, PROJECTION_COUNT)
    chipset, architecture = PROJECTION_ORDER[projection_index]
    return MatrixCoordinateV1(
        core_id=core_id,
        track=TRACK_ORDER[track_index],
        chipset=chipset,
        architecture=architecture,
    )


def legacy_coordinate_order(
    core_ids: object,
) -> tuple[MatrixCoordinateV1, ...]:
    """Return legacy track/core/projection order for exactly 98 sorted cores."""

    if type(core_ids) is not tuple:
        raise PipelineError("legacy coordinate core_ids must be an exact tuple")
    normalized = tuple(
        _require_core_id(item, label="legacy coordinate core_id")
        for item in core_ids
    )
    if len(normalized) != EXPECTED_CORE_COUNT:
        raise PipelineError("legacy coordinate order requires exactly 98 cores")
    if normalized != tuple(sorted(normalized)) or len(normalized) != len(
        set(normalized)
    ):
        raise PipelineError("legacy coordinate core_ids must be sorted and unique")
    return tuple(
        coordinate_for_ordinal(
            core_id,
            track_index * PROJECTION_COUNT + projection_index,
        )
        for track_index in range(len(TRACK_ORDER))
        for core_id in normalized
        for projection_index in range(PROJECTION_COUNT)
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class LegacyMatrixV2Identity:
    """Expected exact identity of a reproducible legacy matrix-v2 document."""

    semantic_sha256: str
    file_sha256: str
    size: int
    lines: int

    format: ClassVar[str] = LEGACY_MATRIX_FORMAT
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"format", "semantic_sha256", "file_sha256", "size", "lines"}
    )

    def __post_init__(self) -> None:
        _require_sha256(
            self.semantic_sha256, label="legacy matrix semantic_sha256"
        )
        _require_sha256(self.file_sha256, label="legacy matrix file_sha256")
        _require_positive_int(self.size, label="legacy matrix size")
        _require_positive_int(self.lines, label="legacy matrix lines")

    def to_document(self) -> dict[str, object]:
        return {
            "format": LEGACY_MATRIX_FORMAT,
            "semantic_sha256": self.semantic_sha256,
            "file_sha256": self.file_sha256,
            "size": self.size,
            "lines": self.lines,
        }

    @classmethod
    def from_document(cls, value: object) -> "LegacyMatrixV2Identity":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="legacy matrix identity",
        )
        if type(document.get("format")) is not str or document.get(
            "format"
        ) != LEGACY_MATRIX_FORMAT:
            raise PipelineError("legacy matrix identity format is invalid")
        return cls(
            semantic_sha256=document.get("semantic_sha256"),  # type: ignore[arg-type]
            file_sha256=document.get("file_sha256"),  # type: ignore[arg-type]
            size=document.get("size"),  # type: ignore[arg-type]
            lines=document.get("lines"),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixCellLinkV1:
    """Shard-local resolvable reference to one normalized cell object."""

    universe_ordinal: int
    partition: str
    reference: EvidenceRef

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"universe_ordinal", "partition", "reference"}
    )

    def __post_init__(self) -> None:
        _require_ordinal(self.universe_ordinal)
        _require_partition(self.partition)
        _require_evidence_ref(
            self.reference,
            label="matrix cell link reference",
            kinds=frozenset({"matrix-cell"}),
        )

    @property
    def content_sha256(self) -> str:
        """Return the referenced cell's authenticated semantic identity."""

        target = self.reference.target_content_sha256
        assert target is not None
        return target

    def to_document(self) -> dict[str, object]:
        return {
            "universe_ordinal": self.universe_ordinal,
            "partition": self.partition,
            "reference": self.reference.to_document(),
        }

    @classmethod
    def from_document(cls, value: object) -> "MatrixCellLinkV1":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="matrix cell link",
        )
        return cls(
            universe_ordinal=document.get("universe_ordinal"),  # type: ignore[arg-type]
            partition=document.get("partition"),  # type: ignore[arg-type]
            reference=EvidenceRef.from_document(document.get("reference")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixShardLinkV1:
    """Root-local resolvable reference and partition index for one shard."""

    core_id: str
    supported_cell_count: int
    unsupported_exclusion_count: int
    reference: EvidenceRef

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "core_id",
            "supported_cell_count",
            "unsupported_exclusion_count",
            "reference",
        }
    )

    def __post_init__(self) -> None:
        _require_core_id(self.core_id)
        supported = _require_nonnegative_int(
            self.supported_cell_count, label="shard link supported_cell_count"
        )
        excluded = _require_nonnegative_int(
            self.unsupported_exclusion_count,
            label="shard link unsupported_exclusion_count",
        )
        if supported + excluded != UNIVERSE_CELLS_PER_CORE:
            raise PipelineError("shard link partition does not cover 27 ordinals")
        _require_evidence_ref(
            self.reference,
            label="matrix shard link reference",
            kinds=frozenset({"matrix-shard"}),
        )

    @property
    def content_sha256(self) -> str:
        """Return the referenced shard's authenticated semantic identity."""

        target = self.reference.target_content_sha256
        assert target is not None
        return target

    def to_document(self) -> dict[str, object]:
        return {
            "core_id": self.core_id,
            "supported_cell_count": self.supported_cell_count,
            "unsupported_exclusion_count": self.unsupported_exclusion_count,
            "reference": self.reference.to_document(),
        }

    @classmethod
    def from_document(cls, value: object) -> "MatrixShardLinkV1":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="matrix shard link",
        )
        return cls(
            core_id=document.get("core_id"),  # type: ignore[arg-type]
            supported_cell_count=document.get(  # type: ignore[arg-type]
                "supported_cell_count"
            ),
            unsupported_exclusion_count=document.get(  # type: ignore[arg-type]
                "unsupported_exclusion_count"
            ),
            reference=EvidenceRef.from_document(document.get("reference")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixCellV1:
    """One immutable coordinate payload in the normalized matrix universe."""

    universe_ordinal: int
    coordinate: MatrixCoordinateV1
    partition: str
    legacy_payload_json: str

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = CELL_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "universe_ordinal",
            "coordinate",
            "partition",
            "legacy_payload_json",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_ordinal(self.universe_ordinal)
        if type(self.coordinate) is not MatrixCoordinateV1:
            raise PipelineError("matrix cell coordinate must be exact")
        if self.coordinate.universe_ordinal != self.universe_ordinal:
            raise PipelineError("matrix cell coordinate differs from its stable ordinal")
        partition = _require_partition(self.partition)
        _require_legacy_cell(
            self.legacy_payload_json,
            partition=partition,
            coordinate=self.coordinate,
        )

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": CELL_FORMAT,
            "universe_ordinal": self.universe_ordinal,
            "coordinate": self.coordinate.to_document(),
            "partition": self.partition,
            "legacy_payload_json": self.legacy_payload_json,
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    def link(self, reference: object) -> MatrixCellLinkV1:
        """Bind this cell to one exact persisted-object reference."""

        reference = _require_evidence_ref(
            reference,
            label="matrix cell persisted reference",
            kinds=frozenset({"matrix-cell"}),
        )
        if reference.target_content_sha256 != self.content_sha256:
            raise PipelineError("matrix cell reference semantic identity is invalid")
        return MatrixCellLinkV1(
            universe_ordinal=self.universe_ordinal,
            partition=self.partition,
            reference=reference,
        )

    @classmethod
    def from_document(cls, value: object) -> "MatrixCellV1":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="normalized matrix cell",
            format_value=CELL_FORMAT,
        )
        result = cls(
            universe_ordinal=document.get("universe_ordinal"),  # type: ignore[arg-type]
            coordinate=MatrixCoordinateV1.from_document(document.get("coordinate")),
            partition=document.get("partition"),  # type: ignore[arg-type]
            legacy_payload_json=document.get("legacy_payload_json"),  # type: ignore[arg-type]
        )
        _require_content_sha256(
            document,
            result._material(),
            label="normalized matrix cell",
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixShardV1:
    """One immutable 27-cell membership map for a single core."""

    core_id: str
    cells: tuple[MatrixCellLinkV1, ...]

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = SHARD_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "core_id",
            "universe_cell_count",
            "supported_cell_count",
            "unsupported_exclusion_count",
            "cells",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_core_id(self.core_id)
        if type(self.cells) is not tuple or any(
            type(item) is not MatrixCellLinkV1 for item in self.cells
        ):
            raise PipelineError("matrix shard cells must be exact cell links")
        ordinals = tuple(item.universe_ordinal for item in self.cells)
        if ordinals != tuple(range(UNIVERSE_CELLS_PER_CORE)):
            raise PipelineError("matrix shard must contain ordinals 0 through 26 exactly")

    @property
    def supported_cell_count(self) -> int:
        return sum(item.partition == SUPPORTED_PARTITION for item in self.cells)

    @property
    def unsupported_exclusion_count(self) -> int:
        return sum(item.partition == EXCLUSION_PARTITION for item in self.cells)

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": SHARD_FORMAT,
            "core_id": self.core_id,
            "universe_cell_count": UNIVERSE_CELLS_PER_CORE,
            "supported_cell_count": self.supported_cell_count,
            "unsupported_exclusion_count": self.unsupported_exclusion_count,
            "cells": [item.to_document() for item in self.cells],
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    def link(self, reference: object) -> MatrixShardLinkV1:
        """Bind this shard to one exact persisted-object reference."""

        reference = _require_evidence_ref(
            reference,
            label="matrix shard persisted reference",
            kinds=frozenset({"matrix-shard"}),
        )
        if reference.target_content_sha256 != self.content_sha256:
            raise PipelineError("matrix shard reference semantic identity is invalid")
        return MatrixShardLinkV1(
            core_id=self.core_id,
            supported_cell_count=self.supported_cell_count,
            unsupported_exclusion_count=self.unsupported_exclusion_count,
            reference=reference,
        )

    @classmethod
    def from_document(cls, value: object) -> "MatrixShardV1":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="normalized matrix shard",
            format_value=SHARD_FORMAT,
        )
        cells_value = document.get("cells")
        if type(cells_value) is not list:
            raise PipelineError("normalized matrix shard cells must be an exact array")
        result = cls(
            core_id=document.get("core_id"),  # type: ignore[arg-type]
            cells=tuple(MatrixCellLinkV1.from_document(item) for item in cells_value),
        )
        expected_counts = {
            "universe_cell_count": UNIVERSE_CELLS_PER_CORE,
            "supported_cell_count": result.supported_cell_count,
            "unsupported_exclusion_count": result.unsupported_exclusion_count,
        }
        for key, expected in expected_counts.items():
            actual = document.get(key)
            if type(actual) is not int or actual != expected:
                raise PipelineError(f"normalized matrix shard {key} is invalid")
        _require_content_sha256(
            document,
            result._material(),
            label="normalized matrix shard",
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixRootV1:
    """Global authority and 98-shard index for one normalized matrix."""

    campaign_id: str
    captured_at: str
    phase_freeze: EvidenceRef
    core_spec_set: EvidenceRef
    legacy_matrix: LegacyMatrixV2Identity
    legacy_root_json: str
    shards: tuple[MatrixShardLinkV1, ...]

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = ROOT_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "campaign_id",
            "captured_at",
            "phase_freeze",
            "core_spec_set",
            "legacy_matrix",
            "legacy_root_json",
            "core_count",
            "universe_cell_count",
            "supported_cell_count",
            "unsupported_exclusion_count",
            "shards",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.campaign_id, label="matrix root campaign_id")
        _require_timestamp(self.captured_at, label="matrix root captured_at")
        _require_evidence_ref(
            self.phase_freeze,
            label="matrix root phase_freeze",
            kinds=frozenset({"phase-freeze", "phase-freeze-cas"}),
        )
        _require_evidence_ref(
            self.core_spec_set,
            label="matrix root core_spec_set",
            kinds=frozenset({"artifact"}),
        )
        if type(self.legacy_matrix) is not LegacyMatrixV2Identity:
            raise PipelineError("matrix root legacy_matrix identity must be exact")
        if type(self.shards) is not tuple or any(
            type(item) is not MatrixShardLinkV1 for item in self.shards
        ):
            raise PipelineError("matrix root shards must be exact shard links")
        core_ids = tuple(item.core_id for item in self.shards)
        if len(core_ids) != EXPECTED_CORE_COUNT:
            raise PipelineError("matrix root must contain exactly 98 core shards")
        if core_ids != tuple(sorted(core_ids)) or len(core_ids) != len(set(core_ids)):
            raise PipelineError("matrix root shards must be sorted and unique by core_id")
        if (
            self.supported_cell_count + self.unsupported_exclusion_count
            != EXPECTED_UNIVERSE_CELL_COUNT
        ):
            raise PipelineError("matrix root partition must cover all 2646 ordinals")
        _require_legacy_root_projection(
            self.legacy_root_json,
            campaign_id=self.campaign_id,
            captured_at=self.captured_at,
            supported_cell_count=self.supported_cell_count,
            unsupported_exclusion_count=self.unsupported_exclusion_count,
        )

    @property
    def supported_cell_count(self) -> int:
        return sum(item.supported_cell_count for item in self.shards)

    @property
    def unsupported_exclusion_count(self) -> int:
        return sum(item.unsupported_exclusion_count for item in self.shards)

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": ROOT_FORMAT,
            "campaign_id": self.campaign_id,
            "captured_at": self.captured_at,
            "phase_freeze": self.phase_freeze.to_document(),
            "core_spec_set": self.core_spec_set.to_document(),
            "legacy_matrix": self.legacy_matrix.to_document(),
            "legacy_root_json": self.legacy_root_json,
            "core_count": EXPECTED_CORE_COUNT,
            "universe_cell_count": EXPECTED_UNIVERSE_CELL_COUNT,
            "supported_cell_count": self.supported_cell_count,
            "unsupported_exclusion_count": self.unsupported_exclusion_count,
            "shards": [item.to_document() for item in self.shards],
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "MatrixRootV1":
        document = _require_exact_document(
            value,
            keys=cls._KEYS,
            label="normalized matrix root",
            format_value=ROOT_FORMAT,
        )
        shards_value = document.get("shards")
        if type(shards_value) is not list:
            raise PipelineError("normalized matrix root shards must be an exact array")
        result = cls(
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            phase_freeze=EvidenceRef.from_document(document.get("phase_freeze")),
            core_spec_set=EvidenceRef.from_document(document.get("core_spec_set")),
            legacy_matrix=LegacyMatrixV2Identity.from_document(
                document.get("legacy_matrix")
            ),
            legacy_root_json=document.get("legacy_root_json"),  # type: ignore[arg-type]
            shards=tuple(MatrixShardLinkV1.from_document(item) for item in shards_value),
        )
        expected_counts = {
            "core_count": EXPECTED_CORE_COUNT,
            "universe_cell_count": EXPECTED_UNIVERSE_CELL_COUNT,
            "supported_cell_count": result.supported_cell_count,
            "unsupported_exclusion_count": result.unsupported_exclusion_count,
        }
        for key, expected in expected_counts.items():
            actual = document.get(key)
            if type(actual) is not int or actual != expected:
                raise PipelineError(f"normalized matrix root {key} is invalid")
        _require_content_sha256(
            document,
            result._material(),
            label="normalized matrix root",
        )
        return result


MatrixObjectV1: TypeAlias = MatrixCellV1 | MatrixShardV1 | MatrixRootV1


def decode_matrix_v1(value: object) -> MatrixObjectV1:
    """Strictly decode one normalized matrix cell, shard, or root document."""

    document = decode_identity_object(value, label="normalized matrix object")
    format_value = document.get("format")
    decoders = {
        CELL_FORMAT: MatrixCellV1.from_document,
        SHARD_FORMAT: MatrixShardV1.from_document,
        ROOT_FORMAT: MatrixRootV1.from_document,
    }
    if type(format_value) is not str or format_value not in decoders:
        raise PipelineError("normalized matrix object format is invalid")
    return decoders[format_value](document)


def render_matrix_v1(value: object) -> bytes:
    """Render one exact normalized matrix object with a single terminal LF."""

    if type(value) not in {MatrixCellV1, MatrixShardV1, MatrixRootV1}:
        raise PipelineError("normalized matrix object must be an exact wire model")
    return rendered_json_bytes(value.to_document())


__all__ = [
    "CELL_FORMAT",
    "EXCLUSION_PARTITION",
    "EXPECTED_CORE_COUNT",
    "EXPECTED_SUPPORTED_CELL_COUNT",
    "EXPECTED_UNIVERSE_CELL_COUNT",
    "EXPECTED_UNSUPPORTED_EXCLUSION_COUNT",
    "LegacyMatrixV2Identity",
    "MatrixCellLinkV1",
    "MatrixCellV1",
    "MatrixCoordinateV1",
    "MatrixObjectV1",
    "MatrixRootV1",
    "MatrixShardLinkV1",
    "MatrixShardV1",
    "PROJECTION_COUNT",
    "PROJECTION_ORDER",
    "ROOT_FORMAT",
    "SHARD_FORMAT",
    "SUPPORTED_PARTITION",
    "TRACK_ORDER",
    "UNIVERSE_CELLS_PER_CORE",
    "coordinate_for_ordinal",
    "decode_matrix_v1",
    "legacy_coordinate_order",
    "render_matrix_v1",
]
