"""Durable, pointer-free staging for one combined H5/H6 authority change.

The pure H5 planner and normalized H6 matrix model remain the owners of their
respective semantics.  This module binds their already-validated results into
one closed staging plan, copies every hydrated source to canonical campaign
CAS, persists both normalized matrix closures, and creates a passed ``staged``
receipt last.  It never executes checks and never opens a pointer transaction.

The H4 process receipt is deliberately not part of the plan identity.  A
caller first predicts the combined plan, runs the cumulative local evidence
tier for that exact plan digest, and passes the resulting ``StoredCheckReceipt``
to :func:`stage_authority_plan`.  That breaks the plan/receipt dependency
cycle while retaining a facts-only check boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import datetime as dt
from pathlib import Path, PurePosixPath
import re
from typing import ClassVar, Final, Protocol

from ..checks import (
    FULL_STATIC_ALLOWED_SKIPS,
    CheckReceipt,
    CheckTier,
    StructuredFormat,
    check_ids_for_tier,
    decode_canonical_json_bytes,
)
from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..source_bundle import (
    PIPELINE_LAUNCHER_MODE,
    PIPELINE_LAUNCHER_RELATIVE,
    REPOSITORY_SOURCE_MODE,
    pipeline_source_bundle_is_well_formed,
)
from .check_adapter import StoredCheckReceipt, validate_stored_check_receipt
from .json_wire import (
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
)
from .legacy_matrix_v2 import decode_matrix_v2
from .matrix_materialize import (
    NormalizedMatrixV1,
    matrix_object_reference,
    materialize_matrix_v2,
    validate_normalized_matrix,
)
from .matrix_model import (
    MatrixCellV1,
    MatrixCoordinateV1,
    MatrixRootV1,
    MatrixShardV1,
    decode_matrix_v1,
    legacy_coordinate_order,
)
from .matrix_refresh import (
    DirectoryFingerprintV1,
    HydratedArtifactV1,
    PipelineBundleIdentityV1,
    TrackCellEvidenceV1,
    project_matrix_root_refresh_v1,
    project_track_inventory_cell_v1,
    splice_matrix_core_refresh_v1,
)
from .matrix_store import stage_normalized_matrix
from .model import CheckResult, EvidenceRef, Receipt, StateRoot
from .phase_freeze import (
    CAMPAIGN_STATE_RELATIVE,
    PlannedPhaseFreeze,
    decode_phase_freeze,
    plan_phase_freeze,
    validate_phase_freeze,
)
from .phase_freeze_bootstrap import capture_repository_phase_freeze_sources
from .store import CampaignStore, canonical_object_reference
from .transition_model import (
    AuthenticatedInput,
    ResolvedTransitionPlanV1,
    TransitionIntentV1,
    TransitionRequest,
)
from .transition_registry import INPUT_ROLE_NAMES
from .workflow import (
    LoadedHistoricalTransition,
    load_historical_transition,
    verify_transition,
)


SCHEMA_VERSION: Final = 1
FORMAT: Final = "spruce-campaign-authority-stage-v1"
PUBLICATION: Final = "disabled"
PROCESS_TIER: Final = "evidence"
SCHEMA_PATH: Final = "manifests/campaign-authority-stage-v1.schema.json"
LEGACY_MATRIX_ROOT: Final = ".local-e2e/campaigns"
LEGACY_MATRIX_CAS_ROOT: Final = ".local-e2e/store/campaign-matrices/sha256"

REQUIRED_CHECKS: Final = (
    "authority-stage.copies",
    "authority-stage.matrix-delta",
    "authority-stage.phase-freeze",
    "authority-stage.pointer-preserved",
    "authority-stage.schema",
    "publication.disabled",
)

_IDENTIFIER_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_CORE_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_UTC_SECONDS_RE: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_PYTEST_SUMMARY_RE: Final = re.compile(
    r"(?m)^(?:=+\s*)?(?P<passed>[0-9]+) passed,\s+"
    r"(?P<skipped>[0-9]+) skipped"
    r"(?:\s+in\s+[^=\r\n]+)?(?:\s*=+)?$"
)
_PHASE_SOURCE_COPY_RE: Final = re.compile(r"^phase\.source\.[0-9a-f]{24}$")

_PHASE_FIXED_COPY_NAMES: Final = frozenset(
    {
        "phase.engine-bundle",
        "phase.intent",
        "phase.predecessor",
        *(f"phase.authority.{name}" for name in INPUT_ROLE_NAMES),
    }
)

Clock = Callable[[], str]


class AuthorityStageReader(Protocol):
    """Minimum immutable/pointer read surface accepted under an outer lock."""

    def read_exact(self, reference: EvidenceRef) -> bytes: ...

    def read_pointer(self, reference: EvidenceRef) -> object: ...


HistoricalRootLoader = Callable[
    [AuthorityStageReader, EvidenceRef], LoadedHistoricalTransition
]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_identifier(value: object, *, label: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_core_id(value: object, *, label: str) -> str:
    if type(value) is not str or _CORE_ID_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be an exact core ID")
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


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _require_relative_path(value: object, *, label: str) -> str:
    if type(value) is not str or not value or "\\" in value or "//" in value:
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return value


def _phase_source_copy_name(path: str) -> str:
    """Derive the sole copy name authorized for one captured source path."""

    return f"phase.source.{sha256_bytes(path.encode('utf-8'))[:24]}"


def _require_exact_mapping(
    value: object,
    *,
    label: str,
    keys: frozenset[str] | None = None,
) -> dict[str, object]:
    document = decode_identity_object(value, label=label)
    if keys is not None and frozenset(document) != keys:
        raise PipelineError(
            f"{label} fields are not exact: "
            f"missing={sorted(keys - frozenset(document))}; "
            f"extra={sorted(frozenset(document) - keys)}"
        )
    return document


def _require_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact array")
    return value


def _with_content_sha256(material: dict[str, object]) -> dict[str, object]:
    return {**material, "content_sha256": canonical_json_sha256(material)}


def _require_content_sha256(
    document: Mapping[str, object],
    material: Mapping[str, object],
    *,
    label: str,
) -> None:
    if document.get("content_sha256") != canonical_json_sha256(dict(material)):
        raise PipelineError(f"{label} content_sha256 is invalid")


def _canonical_path(reference: EvidenceRef) -> str:
    digest = reference.file_sha256
    return PurePosixPath(
        CAMPAIGN_STATE_RELATIVE,
        "objects",
        reference.kind,
        "sha256",
        digest[:2],
        digest,
    ).as_posix()


def _require_semantic_ref(
    value: object,
    *,
    label: str,
    kinds: frozenset[str],
) -> EvidenceRef:
    if (
        type(value) is not EvidenceRef
        or value.kind not in kinds
        or value.target_content_sha256 is None
    ):
        raise PipelineError(f"{label} is not an authorized semantic reference")
    return value


def _same_raw_identity(left: EvidenceRef, right: EvidenceRef) -> bool:
    return (
        left.file_sha256 == right.file_sha256
        and left.target_content_sha256 == right.target_content_sha256
        and left.size == right.size
    )


def _sorted_unique_refs(*references: EvidenceRef) -> tuple[EvidenceRef, ...]:
    if any(type(item) is not EvidenceRef for item in references):
        raise PipelineError("authority-stage outputs must be EvidenceRefs")
    by_key: dict[tuple[str, str], EvidenceRef] = {}
    for reference in references:
        key = (reference.kind, reference.path)
        previous = by_key.get(key)
        if previous is not None and previous != reference:
            raise PipelineError("authority-stage outputs collide by kind/path")
        by_key[key] = reference
    return tuple(by_key[key] for key in sorted(by_key))


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorityCopyV1:
    """One unchanged source reference mapped to its canonical campaign CAS."""

    name: str
    source: EvidenceRef
    stored: EvidenceRef
    source_mode: int | None = None

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"name", "source", "stored", "source_mode", "content_sha256"}
    )

    def __post_init__(self) -> None:
        _require_identifier(self.name, label="authority copy name")
        if type(self.source) is not EvidenceRef or type(self.stored) is not EvidenceRef:
            raise PipelineError("authority copy references must be exact")
        if self.source.kind == "matrix-pointer" or self.stored.kind == "matrix-pointer":
            raise PipelineError("authority copies cannot contain a mutable pointer")
        if self.name.startswith("phase.source."):
            if self.name != _phase_source_copy_name(self.source.path):
                raise PipelineError(
                    "captured repository authority copy name is not canonical"
                )
            allowed_kind = (
                self.source.kind == "artifact"
                and self.stored.kind == "repository-snapshot"
            )
        else:
            allowed_kind = self.source.kind == self.stored.kind or (
                self.source.kind == "phase-freeze"
                and self.stored.kind == "phase-freeze-cas"
            )
        if not allowed_kind or not _same_raw_identity(self.source, self.stored):
            raise PipelineError("authority copy changes source identity")
        if self.stored.path != _canonical_path(self.stored):
            raise PipelineError("authority copy destination is not canonical CAS")
        if self.name.startswith("phase.source."):
            if (
                type(self.source_mode) is not int
                or not 0 <= self.source_mode <= 0o777
            ):
                raise PipelineError(
                    "captured repository authority copy must bind its source mode"
                )
        elif self.source_mode is not None:
            raise PipelineError(
                "only captured repository authority copies may bind a source mode"
            )

    def _material(self) -> dict[str, object]:
        return {
            "name": self.name,
            "source": self.source.to_document(),
            "stored": self.stored.to_document(),
            "source_mode": self.source_mode,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "AuthorityCopyV1":
        document = _require_exact_mapping(
            value, label="authority copy", keys=cls._KEYS
        )
        result = cls(
            name=document.get("name"),  # type: ignore[arg-type]
            source=EvidenceRef.from_document(document.get("source")),
            stored=EvidenceRef.from_document(document.get("stored")),
            source_mode=document.get("source_mode"),  # type: ignore[arg-type]
        )
        _require_content_sha256(document, result._material(), label="authority copy")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixCoreDeltaV1:
    """One exact 27-cell shard replacement; multiple entries form a batch."""

    core_id: str
    predecessor_cells: tuple[EvidenceRef, ...]
    successor_cells: tuple[EvidenceRef, ...]
    predecessor_shard: EvidenceRef
    successor_shard: EvidenceRef

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "core_id",
            "predecessor_cells",
            "successor_cells",
            "predecessor_shard",
            "successor_shard",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_core_id(self.core_id, label="matrix delta core_id")
        for label, values in (
            ("predecessor", self.predecessor_cells),
            ("successor", self.successor_cells),
        ):
            if (
                type(values) is not tuple
                or len(values) != 27
                or any(
                    type(item) is not EvidenceRef or item.kind != "matrix-cell"
                    for item in values
                )
                or len(set(values)) != 27
            ):
                raise PipelineError(f"matrix delta {label} cells are not exact")
        for label, reference in (
            ("predecessor", self.predecessor_shard),
            ("successor", self.successor_shard),
        ):
            if type(reference) is not EvidenceRef or reference.kind != "matrix-shard":
                raise PipelineError(f"matrix delta {label} shard is invalid")
        if self.predecessor_cells == self.successor_cells:
            raise PipelineError("matrix delta must change its cells")
        if self.predecessor_shard == self.successor_shard:
            raise PipelineError("matrix delta must change its shard")

    def _material(self) -> dict[str, object]:
        return {
            "core_id": self.core_id,
            "predecessor_cells": [item.to_document() for item in self.predecessor_cells],
            "successor_cells": [item.to_document() for item in self.successor_cells],
            "predecessor_shard": self.predecessor_shard.to_document(),
            "successor_shard": self.successor_shard.to_document(),
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "MatrixCoreDeltaV1":
        document = _require_exact_mapping(
            value, label="matrix core delta", keys=cls._KEYS
        )
        before = _require_list(
            document.get("predecessor_cells"), label="predecessor cells"
        )
        after = _require_list(
            document.get("successor_cells"), label="successor cells"
        )
        result = cls(
            core_id=document.get("core_id"),  # type: ignore[arg-type]
            predecessor_cells=tuple(EvidenceRef.from_document(item) for item in before),
            successor_cells=tuple(EvidenceRef.from_document(item) for item in after),
            predecessor_shard=EvidenceRef.from_document(
                document.get("predecessor_shard")
            ),
            successor_shard=EvidenceRef.from_document(
                document.get("successor_shard")
            ),
        )
        _require_content_sha256(
            document, result._material(), label="matrix core delta"
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class LegacyMatrixStageV1:
    """Pointer expectation plus immutable successor and compatibility aliases."""

    predecessor_pointer: EvidenceRef
    successor_pointer: EvidenceRef
    canonical_object: EvidenceRef
    semantic_alias: EvidenceRef
    raw_alias: EvidenceRef

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "predecessor_pointer",
            "successor_pointer",
            "canonical_object",
            "semantic_alias",
            "raw_alias",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        for label, reference in (
            ("predecessor pointer", self.predecessor_pointer),
            ("successor pointer", self.successor_pointer),
        ):
            _require_semantic_ref(
                reference,
                label=f"legacy {label}",
                kinds=frozenset({"matrix-pointer"}),
            )
        if (
            self.predecessor_pointer.path != self.successor_pointer.path
            or self.predecessor_pointer == self.successor_pointer
        ):
            raise PipelineError("legacy pointer prediction is invalid")
        for label, reference, kind in (
            ("canonical object", self.canonical_object, "matrix-snapshot"),
            ("semantic alias", self.semantic_alias, "matrix-snapshot"),
            ("raw alias", self.raw_alias, "matrix-cas"),
        ):
            _require_semantic_ref(
                reference, label=f"legacy {label}", kinds=frozenset({kind})
            )
            if not _same_raw_identity(reference, self.successor_pointer):
                raise PipelineError(f"legacy {label} differs from successor bytes")
        if self.canonical_object.path != _canonical_path(self.canonical_object):
            raise PipelineError("legacy canonical object path is invalid")
        digest = self.raw_alias.file_sha256
        expected_raw = f"{LEGACY_MATRIX_CAS_ROOT}/{digest[:2]}/{digest}"
        if self.raw_alias.path != expected_raw:
            raise PipelineError("legacy raw alias path is invalid")

    def _material(self) -> dict[str, object]:
        return {
            "predecessor_pointer": self.predecessor_pointer.to_document(),
            "successor_pointer": self.successor_pointer.to_document(),
            "canonical_object": self.canonical_object.to_document(),
            "semantic_alias": self.semantic_alias.to_document(),
            "raw_alias": self.raw_alias.to_document(),
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "LegacyMatrixStageV1":
        document = _require_exact_mapping(
            value, label="legacy matrix stage", keys=cls._KEYS
        )
        result = cls(
            predecessor_pointer=EvidenceRef.from_document(
                document.get("predecessor_pointer")
            ),
            successor_pointer=EvidenceRef.from_document(
                document.get("successor_pointer")
            ),
            canonical_object=EvidenceRef.from_document(
                document.get("canonical_object")
            ),
            semantic_alias=EvidenceRef.from_document(
                document.get("semantic_alias")
            ),
            raw_alias=EvidenceRef.from_document(document.get("raw_alias")),
        )
        _require_content_sha256(
            document, result._material(), label="legacy matrix stage"
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceReplayV1:
    """Copy names for the exact nine-member admitted-cell proof bundle."""

    pin: str
    golden: str
    selected_e2e: str
    reproduction_e2e: str
    selected_telemetry: str
    reproduction_telemetry: str
    selected_build_record: str
    reproduction_build_record: str
    telemetry_schema: str

    _FIELDS: ClassVar[tuple[str, ...]] = (
        "golden",
        "pin",
        "reproduction_build_record",
        "reproduction_e2e",
        "reproduction_telemetry",
        "selected_build_record",
        "selected_e2e",
        "selected_telemetry",
        "telemetry_schema",
    )
    _KEYS: ClassVar[frozenset[str]] = frozenset((*_FIELDS, "content_sha256"))

    def __post_init__(self) -> None:
        for field in self._FIELDS:
            _require_identifier(
                getattr(self, field), label=f"evidence replay {field} copy"
            )

    def _material(self) -> dict[str, object]:
        return {field: getattr(self, field) for field in self._FIELDS}

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "EvidenceReplayV1":
        document = _require_exact_mapping(
            value, label="evidence replay", keys=cls._KEYS
        )
        result = cls(  # type: ignore[arg-type]
            **{field: document.get(field) for field in cls._FIELDS}
        )
        _require_content_sha256(
            document, result._material(), label="evidence replay"
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceSnapshotReplayV1:
    """One source-registry semantic identity and its hydrated copy name."""

    content_sha256: str
    copy: str

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"content_sha256", "copy", "binding_sha256"}
    )

    def __post_init__(self) -> None:
        _require_sha256(
            self.content_sha256, label="source snapshot content_sha256"
        )
        _require_identifier(self.copy, label="source snapshot copy")

    def _material(self) -> dict[str, object]:
        return {"content_sha256": self.content_sha256, "copy": self.copy}

    @property
    def binding_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return {**self._material(), "binding_sha256": self.binding_sha256}

    @classmethod
    def from_document(cls, value: object) -> "SourceSnapshotReplayV1":
        document = _require_exact_mapping(
            value, label="source snapshot replay", keys=cls._KEYS
        )
        result = cls(
            content_sha256=document.get("content_sha256"),  # type: ignore[arg-type]
            copy=document.get("copy"),  # type: ignore[arg-type]
        )
        if document.get("binding_sha256") != result.binding_sha256:
            raise PipelineError("source snapshot binding_sha256 is invalid")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixCellReplayV1:
    """Hydrated-input recipe for one pure matrix cell projection."""

    coordinate: MatrixCoordinateV1
    inventory_copy: str
    evidence: EvidenceReplayV1 | None
    producer_coordinate: MatrixCoordinateV1 | None
    pipeline_bundle_content_sha256: str | None
    source_registry_snapshots: tuple[SourceSnapshotReplayV1, ...] = ()

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "coordinate",
            "inventory_copy",
            "evidence",
            "producer_coordinate",
            "pipeline_bundle_content_sha256",
            "source_registry_snapshots",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        if type(self.coordinate) is not MatrixCoordinateV1:
            raise PipelineError("cell replay coordinate is invalid")
        _require_identifier(self.inventory_copy, label="cell replay inventory copy")
        if self.evidence is None:
            if self.producer_coordinate is not None:
                raise PipelineError("deferred cell replay cannot name a producer")
            _require_sha256(
                self.pipeline_bundle_content_sha256,
                label="deferred replay pipeline bundle",
            )
        else:
            if type(self.evidence) is not EvidenceReplayV1 or type(
                self.producer_coordinate
            ) is not MatrixCoordinateV1:
                raise PipelineError("admitted cell replay evidence is incomplete")
            if self.pipeline_bundle_content_sha256 is not None:
                raise PipelineError("admitted cell replay cannot use deferred bundle")
        if type(self.source_registry_snapshots) is not tuple or any(
            type(item) is not SourceSnapshotReplayV1
            for item in self.source_registry_snapshots
        ):
            raise PipelineError("cell replay source snapshots are invalid")
        keys = tuple(item.content_sha256 for item in self.source_registry_snapshots)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise PipelineError("cell replay source snapshots are not sorted/unique")

    def _material(self) -> dict[str, object]:
        return {
            "coordinate": self.coordinate.to_document(),
            "inventory_copy": self.inventory_copy,
            "evidence": self.evidence.to_document() if self.evidence else None,
            "producer_coordinate": (
                self.producer_coordinate.to_document()
                if self.producer_coordinate is not None
                else None
            ),
            "pipeline_bundle_content_sha256": self.pipeline_bundle_content_sha256,
            "source_registry_snapshots": [
                item.to_document() for item in self.source_registry_snapshots
            ],
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "MatrixCellReplayV1":
        document = _require_exact_mapping(
            value, label="matrix cell replay", keys=cls._KEYS
        )
        evidence = document.get("evidence")
        producer = document.get("producer_coordinate")
        snapshots = _require_list(
            document.get("source_registry_snapshots"),
            label="cell replay source snapshots",
        )
        result = cls(
            coordinate=MatrixCoordinateV1.from_document(document.get("coordinate")),
            inventory_copy=document.get("inventory_copy"),  # type: ignore[arg-type]
            evidence=(
                EvidenceReplayV1.from_document(evidence)
                if evidence is not None
                else None
            ),
            producer_coordinate=(
                MatrixCoordinateV1.from_document(producer)
                if producer is not None
                else None
            ),
            pipeline_bundle_content_sha256=document.get(
                "pipeline_bundle_content_sha256"
            ),  # type: ignore[arg-type]
            source_registry_snapshots=tuple(
                SourceSnapshotReplayV1.from_document(item) for item in snapshots
            ),
        )
        _require_content_sha256(
            document, result._material(), label="matrix cell replay"
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class DirectoryReplayV1:
    """One legacy fingerprint directory reconstructed from member copies."""

    path: str
    members: tuple[str, ...]

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"path", "members", "content_sha256"}
    )

    def __post_init__(self) -> None:
        _require_relative_path(self.path, label="directory replay path")
        if type(self.members) is not tuple or not self.members or any(
            type(item) is not str for item in self.members
        ):
            raise PipelineError("directory replay members must be nonempty")
        if self.members != tuple(sorted(self.members)) or len(self.members) != len(
            set(self.members)
        ):
            raise PipelineError("directory replay members must be sorted/unique")
        for item in self.members:
            _require_identifier(item, label="directory replay member copy")

    def _material(self) -> dict[str, object]:
        return {"path": self.path, "members": list(self.members)}

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "DirectoryReplayV1":
        document = _require_exact_mapping(
            value, label="directory replay", keys=cls._KEYS
        )
        members = _require_list(
            document.get("members"), label="directory replay members"
        )
        result = cls(
            path=document.get("path"),  # type: ignore[arg-type]
            members=tuple(members),  # type: ignore[arg-type]
        )
        _require_content_sha256(
            document, result._material(), label="directory replay"
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class MatrixRefreshReplayV1:
    """Strict request that replays cell, root, and shard projection semantics."""

    transition_id: str
    core_id: str
    cells: tuple[MatrixCellReplayV1, ...]
    audit_label: str
    leaf_audit_id: str
    reason: str
    predecessor_pointer_path: str
    generator_copy: str
    track_registry_copy: str
    pipeline_bundle_copy: str
    authoritative_suite_summary: str
    edge_source_count: int
    pin_directory: DirectoryReplayV1 | None
    track_registry_snapshot_directory: DirectoryReplayV1 | None

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = "spruce-matrix-refresh-replay-v1"
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "transition_id",
            "core_id",
            "cells",
            "audit_label",
            "leaf_audit_id",
            "reason",
            "predecessor_pointer_path",
            "generator_copy",
            "track_registry_copy",
            "pipeline_bundle_copy",
            "authoritative_suite_summary",
            "edge_source_count",
            "pin_directory",
            "track_registry_snapshot_directory",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.transition_id, label="matrix replay transition_id")
        _require_core_id(self.core_id, label="matrix replay core_id")
        if type(self.cells) is not tuple or len(self.cells) != 27 or any(
            type(item) is not MatrixCellReplayV1 for item in self.cells
        ):
            raise PipelineError("matrix replay must contain exactly 27 cell rows")
        if tuple(item.coordinate.universe_ordinal for item in self.cells) != tuple(
            range(27)
        ) or any(item.coordinate.core_id != self.core_id for item in self.cells):
            raise PipelineError("matrix replay cells do not cover one exact shard")
        _require_identifier(self.audit_label, label="matrix replay audit_label")
        _require_identifier(self.leaf_audit_id, label="matrix replay leaf_audit_id")
        if type(self.reason) is not str or not self.reason or self.reason != self.reason.strip():
            raise PipelineError("matrix replay reason must be a stripped string")
        _require_relative_path(
            self.predecessor_pointer_path,
            label="matrix replay predecessor pointer path",
        )
        for label, name in (
            ("generator", self.generator_copy),
            ("track registry", self.track_registry_copy),
            ("pipeline bundle", self.pipeline_bundle_copy),
        ):
            _require_identifier(name, label=f"matrix replay {label} copy")
        if (
            type(self.authoritative_suite_summary) is not str
            or not self.authoritative_suite_summary
            or self.authoritative_suite_summary
            != self.authoritative_suite_summary.strip()
        ):
            raise PipelineError("matrix replay suite summary is invalid")
        if type(self.edge_source_count) is not int or self.edge_source_count < 1:
            raise PipelineError("matrix replay edge source count is invalid")
        for label, value in (
            ("pin directory", self.pin_directory),
            ("track snapshot directory", self.track_registry_snapshot_directory),
        ):
            if value is not None and type(value) is not DirectoryReplayV1:
                raise PipelineError(f"matrix replay {label} is invalid")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": self.format,
            "transition_id": self.transition_id,
            "core_id": self.core_id,
            "cells": [item.to_document() for item in self.cells],
            "audit_label": self.audit_label,
            "leaf_audit_id": self.leaf_audit_id,
            "reason": self.reason,
            "predecessor_pointer_path": self.predecessor_pointer_path,
            "generator_copy": self.generator_copy,
            "track_registry_copy": self.track_registry_copy,
            "pipeline_bundle_copy": self.pipeline_bundle_copy,
            "authoritative_suite_summary": self.authoritative_suite_summary,
            "edge_source_count": self.edge_source_count,
            "pin_directory": (
                self.pin_directory.to_document() if self.pin_directory else None
            ),
            "track_registry_snapshot_directory": (
                self.track_registry_snapshot_directory.to_document()
                if self.track_registry_snapshot_directory
                else None
            ),
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "MatrixRefreshReplayV1":
        document = _require_exact_mapping(
            value, label="matrix refresh replay", keys=cls._KEYS
        )
        if document.get("schema_version") != SCHEMA_VERSION or document.get(
            "format"
        ) != cls.format:
            raise PipelineError("matrix refresh replay envelope is invalid")
        if document.get("local_only") is not True or document.get(
            "publication"
        ) != PUBLICATION:
            raise PipelineError("matrix refresh replay publication is invalid")
        cells = _require_list(document.get("cells"), label="matrix replay cells")
        pin_directory = document.get("pin_directory")
        track_directory = document.get("track_registry_snapshot_directory")
        result = cls(
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            core_id=document.get("core_id"),  # type: ignore[arg-type]
            cells=tuple(MatrixCellReplayV1.from_document(item) for item in cells),
            audit_label=document.get("audit_label"),  # type: ignore[arg-type]
            leaf_audit_id=document.get("leaf_audit_id"),  # type: ignore[arg-type]
            reason=document.get("reason"),  # type: ignore[arg-type]
            predecessor_pointer_path=document.get(
                "predecessor_pointer_path"
            ),  # type: ignore[arg-type]
            generator_copy=document.get("generator_copy"),  # type: ignore[arg-type]
            track_registry_copy=document.get(
                "track_registry_copy"
            ),  # type: ignore[arg-type]
            pipeline_bundle_copy=document.get(
                "pipeline_bundle_copy"
            ),  # type: ignore[arg-type]
            authoritative_suite_summary=document.get(
                "authoritative_suite_summary"
            ),  # type: ignore[arg-type]
            edge_source_count=document.get("edge_source_count"),  # type: ignore[arg-type]
            pin_directory=(
                DirectoryReplayV1.from_document(pin_directory)
                if pin_directory is not None
                else None
            ),
            track_registry_snapshot_directory=(
                DirectoryReplayV1.from_document(track_directory)
                if track_directory is not None
                else None
            ),
        )
        _require_content_sha256(
            document, result._material(), label="matrix refresh replay"
        )
        return result


def render_matrix_refresh_replay(value: MatrixRefreshReplayV1) -> bytes:
    if type(value) is not MatrixRefreshReplayV1:
        raise PipelineError("matrix refresh replay must be exact")
    return rendered_json_bytes(value.to_document())


def decode_matrix_refresh_replay(raw: bytes) -> MatrixRefreshReplayV1:
    if type(raw) is not bytes:
        raise PipelineError("matrix refresh replay bytes must be exact")
    result = MatrixRefreshReplayV1.from_document(raw)
    if render_matrix_refresh_replay(result) != raw:
        raise PipelineError("matrix refresh replay bytes are not canonical")
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorityStagePlanV1:
    """Closed combined plan used as the H4 subject and staged resume authority."""

    campaign_id: str
    transition_id: str
    captured_at: str
    schema: AuthorityCopyV1
    matrix_replay: AuthorityCopyV1
    copies: tuple[AuthorityCopyV1, ...]
    current_state_root: EvidenceRef
    phase_plan: EvidenceRef
    phase_successor: EvidenceRef
    predecessor_matrix_root: EvidenceRef
    successor_matrix_root: EvidenceRef
    matrix_changes: tuple[MatrixCoreDeltaV1, ...]
    legacy_matrix: LegacyMatrixStageV1
    required_checks: tuple[str, ...] = REQUIRED_CHECKS
    process_tier: str = PROCESS_TIER

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "campaign_id",
            "transition_id",
            "captured_at",
            "schema",
            "matrix_replay",
            "copies",
            "current_state_root",
            "phase_plan",
            "phase_successor",
            "predecessor_matrix_root",
            "successor_matrix_root",
            "matrix_changes",
            "legacy_matrix",
            "required_checks",
            "process_tier",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.campaign_id, label="authority-stage campaign_id")
        _require_identifier(self.transition_id, label="authority-stage transition_id")
        _require_timestamp(self.captured_at, label="authority-stage captured_at")
        if (
            type(self.schema) is not AuthorityCopyV1
            or self.schema.name != "stage.schema"
            or self.schema.source.kind != "artifact"
        ):
            raise PipelineError("authority-stage schema copy is invalid")
        if self.schema.source.path != SCHEMA_PATH:
            raise PipelineError("authority-stage schema source path is invalid")
        if (
            type(self.matrix_replay) is not AuthorityCopyV1
            or self.matrix_replay.name != "matrix.replay"
            or self.matrix_replay.source.kind != "artifact"
        ):
            raise PipelineError("authority-stage matrix replay copy is invalid")
        expected_replay_path = (
            "campaign/evidence/"
            f"{self.transition_id}-matrix-refresh-replay-v1.json"
        )
        if self.matrix_replay.source.path != expected_replay_path:
            raise PipelineError("authority-stage matrix replay source path is invalid")
        if type(self.copies) is not tuple or not self.copies or any(
            type(item) is not AuthorityCopyV1 for item in self.copies
        ):
            raise PipelineError("authority-stage copies must be nonempty")
        names = tuple(item.name for item in self.copies)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise PipelineError("authority-stage copies must be sorted and unique")
        phase_source_paths: list[str] = []
        for item in self.copies:
            name = item.name
            if name in _PHASE_FIXED_COPY_NAMES:
                continue
            if _PHASE_SOURCE_COPY_RE.fullmatch(name) is not None:
                if name != _phase_source_copy_name(item.source.path):
                    raise PipelineError(
                        "authority-stage phase source copy name is not canonical"
                    )
                phase_source_paths.append(item.source.path)
                continue
            if name.startswith("matrix.member."):
                _require_identifier(
                    name.removeprefix("matrix.member."),
                    label="matrix member copy name",
                )
                continue
            raise PipelineError(f"authority-stage copy name is unknown: {name}")
        if len(phase_source_paths) != len(set(phase_source_paths)):
            raise PipelineError(
                "authority-stage phase source paths must be unique"
            )
        if {self.schema.name, self.matrix_replay.name} & set(names):
            raise PipelineError("authority-stage special copies must not be duplicated")
        _require_semantic_ref(
            self.current_state_root,
            label="authority-stage current StateRoot",
            kinds=frozenset({"state-root"}),
        )
        _require_semantic_ref(
            self.phase_plan,
            label="authority-stage phase plan",
            kinds=frozenset({"transition-plan"}),
        )
        _require_semantic_ref(
            self.phase_successor,
            label="authority-stage phase successor",
            kinds=frozenset({"phase-freeze-cas"}),
        )
        for label, reference in (
            ("predecessor", self.predecessor_matrix_root),
            ("successor", self.successor_matrix_root),
        ):
            _require_semantic_ref(
                reference,
                label=f"authority-stage {label} matrix root",
                kinds=frozenset({"matrix-root"}),
            )
        if self.predecessor_matrix_root == self.successor_matrix_root:
            raise PipelineError("authority-stage matrix root must advance")
        if type(self.matrix_changes) is not tuple or not self.matrix_changes or any(
            type(item) is not MatrixCoreDeltaV1 for item in self.matrix_changes
        ):
            raise PipelineError("authority-stage matrix changes must be nonempty")
        core_ids = tuple(item.core_id for item in self.matrix_changes)
        if core_ids != tuple(sorted(core_ids)) or len(core_ids) != len(set(core_ids)):
            raise PipelineError("authority-stage matrix changes must be sorted and unique")
        if type(self.legacy_matrix) is not LegacyMatrixStageV1:
            raise PipelineError("authority-stage legacy matrix binding is invalid")
        if self.required_checks != REQUIRED_CHECKS:
            raise PipelineError("authority-stage required checks are not exact")
        if self.process_tier != PROCESS_TIER:
            raise PipelineError("authority-stage process tier must remain evidence")
        expected_semantic_path = (
            f"{LEGACY_MATRIX_ROOT}/{self.campaign_id}/matrices/"
            f"{self.legacy_matrix.semantic_alias.target_content_sha256}.json"
        )
        if self.legacy_matrix.semantic_alias.path != expected_semantic_path:
            raise PipelineError("legacy semantic alias path is invalid")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": FORMAT,
            "campaign_id": self.campaign_id,
            "transition_id": self.transition_id,
            "captured_at": self.captured_at,
            "schema": self.schema.to_document(),
            "matrix_replay": self.matrix_replay.to_document(),
            "copies": [item.to_document() for item in self.copies],
            "current_state_root": self.current_state_root.to_document(),
            "phase_plan": self.phase_plan.to_document(),
            "phase_successor": self.phase_successor.to_document(),
            "predecessor_matrix_root": self.predecessor_matrix_root.to_document(),
            "successor_matrix_root": self.successor_matrix_root.to_document(),
            "matrix_changes": [item.to_document() for item in self.matrix_changes],
            "legacy_matrix": self.legacy_matrix.to_document(),
            "required_checks": list(self.required_checks),
            "process_tier": self.process_tier,
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "AuthorityStagePlanV1":
        document = _require_exact_mapping(
            value, label="authority-stage plan", keys=cls._KEYS
        )
        if document.get("schema_version") != SCHEMA_VERSION:
            raise PipelineError("authority-stage schema_version is invalid")
        if document.get("format") != FORMAT:
            raise PipelineError("authority-stage format is invalid")
        if document.get("local_only") is not True or document.get(
            "publication"
        ) != PUBLICATION:
            raise PipelineError("authority-stage publication envelope is invalid")
        copies = _require_list(document.get("copies"), label="authority-stage copies")
        changes = _require_list(
            document.get("matrix_changes"), label="authority-stage matrix changes"
        )
        checks = _require_list(
            document.get("required_checks"), label="authority-stage checks"
        )
        result = cls(
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            schema=AuthorityCopyV1.from_document(document.get("schema")),
            matrix_replay=AuthorityCopyV1.from_document(
                document.get("matrix_replay")
            ),
            copies=tuple(AuthorityCopyV1.from_document(item) for item in copies),
            current_state_root=EvidenceRef.from_document(
                document.get("current_state_root")
            ),
            phase_plan=EvidenceRef.from_document(document.get("phase_plan")),
            phase_successor=EvidenceRef.from_document(
                document.get("phase_successor")
            ),
            predecessor_matrix_root=EvidenceRef.from_document(
                document.get("predecessor_matrix_root")
            ),
            successor_matrix_root=EvidenceRef.from_document(
                document.get("successor_matrix_root")
            ),
            matrix_changes=tuple(
                MatrixCoreDeltaV1.from_document(item) for item in changes
            ),
            legacy_matrix=LegacyMatrixStageV1.from_document(
                document.get("legacy_matrix")
            ),
            required_checks=tuple(checks),  # type: ignore[arg-type]
            process_tier=document.get("process_tier"),  # type: ignore[arg-type]
        )
        _require_content_sha256(
            document, result._material(), label="authority-stage plan"
        )
        return result


def render_authority_stage_plan(value: AuthorityStagePlanV1) -> bytes:
    if type(value) is not AuthorityStagePlanV1:
        raise PipelineError("authority-stage plan must be exact")
    return rendered_json_bytes(value.to_document())


def decode_authority_stage_plan(raw: bytes) -> AuthorityStagePlanV1:
    if type(raw) is not bytes:
        raise PipelineError("authority-stage plan bytes must be exact")
    result = AuthorityStagePlanV1.from_document(raw)
    if render_authority_stage_plan(result) != raw:
        raise PipelineError("authority-stage plan bytes are not canonical")
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthorityCopyPayloadV1:
    """Runtime-only exact bytes for one persisted source-to-CAS mapping."""

    copy: AuthorityCopyV1
    raw: bytes

    def __post_init__(self) -> None:
        if type(self.copy) is not AuthorityCopyV1 or type(self.raw) is not bytes:
            raise PipelineError("authority copy payload is invalid")
        if (
            len(self.raw) != self.copy.source.size
            or sha256_bytes(self.raw) != self.copy.source.file_sha256
        ):
            raise PipelineError("authority copy bytes differ from the source reference")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedAuthorityStageV1:
    """Complete in-memory closure validated before the first durable write."""

    plan: AuthorityStagePlanV1
    plan_reference: EvidenceRef
    phase_request: TransitionRequest
    phase_result: PlannedPhaseFreeze
    phase_plan_raw: bytes
    phase_successor_raw: bytes
    schema_raw: bytes
    matrix_replay: MatrixRefreshReplayV1
    matrix_replay_raw: bytes
    copies: tuple[AuthorityCopyPayloadV1, ...]
    current_state_root: StateRoot
    predecessor_matrix: NormalizedMatrixV1
    successor_matrix: NormalizedMatrixV1
    legacy_raw: bytes

    def __post_init__(self) -> None:
        validate_planned_authority_stage(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class StagedAuthorityStageV1:
    """Deeply reloaded combined plan and its sole resumable receipt token."""

    planned: PlannedAuthorityStageV1
    receipt: Receipt
    receipt_reference: EvidenceRef
    process_receipt: StoredCheckReceipt
    historical_transition: LoadedHistoricalTransition

    def __post_init__(self) -> None:
        if type(self.planned) is not PlannedAuthorityStageV1:
            raise PipelineError("staged authority plan is invalid")
        if (
            type(self.receipt) is not Receipt
            or self.receipt.stage != "staged"
            or self.receipt.status != "passed"
        ):
            raise PipelineError("staged authority receipt is invalid")
        if type(self.process_receipt) is not StoredCheckReceipt:
            raise PipelineError("staged process receipt is invalid")
        if type(self.historical_transition) is not LoadedHistoricalTransition:
            raise PipelineError("staged historical H3 transition is invalid")
        if (
            self.historical_transition.state_root != self.planned.current_state_root
            or self.historical_transition.state_root_ref
            != self.planned.plan.current_state_root
            or self.historical_transition.current_pointer_ref
            != self.planned.plan.legacy_matrix.predecessor_pointer
        ):
            raise PipelineError("staged historical H3 transition differs from the plan")
        if type(self.receipt_reference) is not EvidenceRef:
            raise PipelineError("staged receipt reference is invalid")

    @property
    def predecessor_pointer(self) -> EvidenceRef:
        return self.planned.plan.legacy_matrix.predecessor_pointer

    @property
    def successor_pointer(self) -> EvidenceRef:
        return self.planned.plan.legacy_matrix.successor_pointer

    @property
    def predecessor_raw(self) -> bytes:
        return materialize_matrix_v2(self.planned.predecessor_matrix)

    @property
    def successor_raw(self) -> bytes:
        return self.planned.legacy_raw

    @property
    def canonical_successor_matrix(self) -> EvidenceRef:
        return self.planned.plan.legacy_matrix.canonical_object

    @property
    def prior_state_root(self) -> EvidenceRef:
        return self.planned.plan.current_state_root

    @property
    def staged_required_objects(self) -> tuple[EvidenceRef, ...]:
        """Sorted staged H5/H6 closure, excluding separately verified H3 ancestry."""

        normalized_members = tuple(
            matrix_object_reference(item)
            for closure in (
                self.planned.predecessor_matrix,
                self.planned.successor_matrix,
            )
            for item in (*closure.cells, *closure.shards)
        )
        result = _sorted_unique_refs(
            *self.receipt.outputs,
            self.receipt_reference,
            *normalized_members,
        )
        if any(item.kind == "matrix-pointer" for item in result):
            raise PipelineError("staged required object closure contains a pointer")
        return result


def _schema_document(raw: bytes) -> dict[str, object]:
    schema = decode_identity_object(raw, label="authority-stage schema")
    if rendered_json_bytes(schema) != raw:
        raise PipelineError("authority-stage schema bytes are not canonical")
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        raise PipelineError("jsonschema is required for authority staging") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise PipelineError(f"authority-stage schema is invalid: {exc.message}") from exc
    return schema


def _validate_schema(raw: bytes, plan: AuthorityStagePlanV1) -> str:
    schema = _schema_document(raw)
    schema_content_sha256 = canonical_json_sha256(schema)
    if (
        plan.schema.source.target_content_sha256 != schema_content_sha256
        or plan.schema.stored.target_content_sha256 != schema_content_sha256
    ):
        raise PipelineError(
            "authority-stage schema references differ from the canonical schema"
        )
    try:
        from jsonschema import Draft202012Validator

        error = next(iter(Draft202012Validator(schema).iter_errors(plan.to_document())), None)
    except Exception as exc:
        raise PipelineError(f"authority-stage schema validation failed: {exc}") from exc
    if error is not None:
        path = "/".join(str(part) for part in error.absolute_path)
        raise PipelineError(
            f"authority-stage plan fails schema at /{path}: {error.message}"
        )
    return schema_content_sha256


def _copy_payload(
    store: CampaignStore,
    *,
    name: str,
    source: EvidenceRef,
    raw: bytes,
    stored_kind: str | None = None,
    source_mode: int | None = None,
) -> AuthorityCopyPayloadV1:
    if type(raw) is not bytes or len(raw) != source.size or sha256_bytes(raw) != source.file_sha256:
        raise PipelineError(f"authority source {name} bytes are not authentic")
    stored = store.reference_for(
        kind=stored_kind or source.kind,
        raw=raw,
        target_content_sha256=source.target_content_sha256,
    )
    return AuthorityCopyPayloadV1(
        copy=AuthorityCopyV1(
            name=name,
            source=source,
            stored=stored,
            source_mode=source_mode,
        ),
        raw=raw,
    )


def _phase_copy_payloads(
    store: CampaignStore,
    phase_request: TransitionRequest,
    source_members: object,
) -> tuple[AuthorityCopyPayloadV1, ...]:
    intent = TransitionIntentV1.from_document(phase_request.spec_raw)
    payloads = [
        _copy_payload(
            store,
            name="phase.engine-bundle",
            source=phase_request.engine_bundle_ref,
            raw=phase_request.engine_bundle_raw,
        ),
        _copy_payload(
            store,
            name="phase.intent",
            source=phase_request.spec_ref,
            raw=phase_request.spec_raw,
        ),
        _copy_payload(
            store,
            name="phase.predecessor",
            source=intent.predecessor,
            raw=phase_request.predecessor_raw,
            stored_kind="phase-freeze-cas",
        ),
    ]
    payloads.extend(
        _copy_payload(
            store,
            name=f"phase.authority.{item.name}",
            source=item.reference,
            raw=item.raw,
        )
        for item in phase_request.inputs
    )
    if type(source_members) is not tuple or not source_members:
        raise PipelineError("phase bootstrap does not expose captured source members")
    members: list[tuple[str, bytes, int]] = []
    for item in source_members:
        path = getattr(item, "path", None)
        raw = getattr(item, "raw", None)
        mode = getattr(item, "mode", None)
        if (
            type(path) is not str
            or type(raw) is not bytes
            or type(mode) is not int
            or not 0 <= mode <= 0o777
        ):
            raise PipelineError("captured repository source member is invalid")
        members.append((path, raw, mode))
    paths = tuple(path for path, _raw, _mode in members)
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
        raise PipelineError("captured repository source members are not sorted/unique")
    for path, raw, mode in members:
        source = EvidenceRef(
            kind="artifact",
            path=path,
            file_sha256=sha256_bytes(raw),
            target_content_sha256=None,
            size=len(raw),
        )
        name = _phase_source_copy_name(path)
        payloads.append(
            _copy_payload(
                store,
                name=name,
                source=source,
                raw=raw,
                stored_kind="repository-snapshot",
                source_mode=mode,
            )
        )
    return tuple(sorted(payloads, key=lambda item: item.copy.name))


def _validate_phase_source_coverage(
    request: TransitionRequest,
    copies: tuple[AuthorityCopyPayloadV1, ...],
) -> None:
    source_payloads = tuple(
        item for item in copies if item.copy.name.startswith("phase.source.")
    )
    source_paths = tuple(item.copy.source.path for item in source_payloads)
    if len(source_paths) != len(set(source_paths)):
        raise PipelineError("phase captured source paths are not unique")
    if any(
        item.copy.name != _phase_source_copy_name(item.copy.source.path)
        for item in source_payloads
    ):
        raise PipelineError("phase captured source copy name is not canonical")
    source_by_path = {
        item.copy.source.path: (item.raw, item.copy.source_mode)
        for item in source_payloads
    }
    engine = decode_identity_object(
        request.engine_bundle_raw, label="authority-stage engine bundle"
    )
    if not pipeline_source_bundle_is_well_formed(engine):
        raise PipelineError("authority-stage engine bundle is invalid")
    expected: dict[str, tuple[str, int]] = {
        path: (
            digest,
            len(source_by_path[path][0]) if path in source_by_path else -1,
        )
        for path, digest in engine["files"].items()  # type: ignore[union-attr]
    }
    for item in request.inputs:
        try:
            document = decode_identity_object(item.raw, label=f"phase input {item.name}")
        except PipelineError:
            document = {}
        if document.get("format") == "spruce-repository-file-set-v1":
            files = document.get("files")
            if type(files) is not dict:
                raise PipelineError("phase file-set member map is invalid")
            for path, identity in files.items():
                if type(path) is not str or type(identity) is not dict:
                    raise PipelineError("phase file-set member identity is invalid")
                expected[path] = (
                    identity.get("file_sha256"),  # type: ignore[arg-type]
                    identity.get("size"),  # type: ignore[arg-type]
                )
        else:
            expected[item.reference.path] = (
                item.reference.file_sha256,
                item.reference.size,
            )
    host_inputs = tuple(item for item in request.inputs if item.name == "host-execution")
    if len(host_inputs) != 1:
        raise PipelineError("phase host-execution authority is not exact")
    host_document = decode_identity_object(
        host_inputs[0].raw,
        label="phase host-execution authority",
    )
    schema_leaf = host_document.get("$schema")
    if (
        type(schema_leaf) is not str
        or not schema_leaf
        or PurePosixPath(schema_leaf).name != schema_leaf
    ):
        raise PipelineError("phase host-execution schema path is invalid")
    host_schema_path = PurePosixPath(
        PurePosixPath(host_inputs[0].reference.path).parent,
        schema_leaf,
    ).as_posix()
    host_schema = source_by_path.get(host_schema_path)
    if host_schema is None or host_document.get("schema_file_sha256") != sha256_bytes(
        host_schema[0]
    ):
        raise PipelineError("phase host-execution schema binding is stale")
    expected[host_schema_path] = (sha256_bytes(host_schema[0]), len(host_schema[0]))
    if frozenset(source_by_path) != frozenset(expected):
        raise PipelineError("phase captured source-member coverage is not exact")
    for path, (digest, size) in expected.items():
        raw, mode = source_by_path[path]
        expected_name = _phase_source_copy_name(path)
        matching = tuple(
            item
            for item in copies
            if item.copy.name == expected_name and item.copy.source.path == path
        )
        if (
            len(matching) != 1
            or type(mode) is not int
            or mode
            != (
                PIPELINE_LAUNCHER_MODE
                if path == PIPELINE_LAUNCHER_RELATIVE
                else REPOSITORY_SOURCE_MODE
            )
            or sha256_bytes(raw) != digest
            or len(raw) != size
        ):
            raise PipelineError(f"captured source member moved: {path}")


def _phase_request_from_copies(
    plan: AuthorityStagePlanV1,
    copies: tuple[AuthorityCopyPayloadV1, ...],
) -> TransitionRequest:
    by_name = {item.copy.name: item for item in copies}
    try:
        intent = by_name["phase.intent"]
        engine = by_name["phase.engine-bundle"]
        predecessor = by_name["phase.predecessor"]
        inputs = tuple(
            AuthenticatedInput(
                name=name,
                reference=by_name[f"phase.authority.{name}"].copy.source,
                raw=by_name[f"phase.authority.{name}"].raw,
            )
            for name in INPUT_ROLE_NAMES
        )
    except KeyError as exc:
        raise PipelineError("authority-stage phase copy closure is incomplete") from exc
    request = TransitionRequest(
        spec_ref=intent.copy.source,
        spec_raw=intent.raw,
        engine_bundle_ref=engine.copy.source,
        engine_bundle_raw=engine.raw,
        predecessor_raw=predecessor.raw,
        inputs=inputs,
    )
    request_intent = TransitionIntentV1.from_document(request.spec_raw)
    if request_intent.transition_id != plan.transition_id:
        raise PipelineError("authority-stage transition differs from phase intent")
    return request


def _matrix_changes(
    predecessor: NormalizedMatrixV1,
    successor: NormalizedMatrixV1,
) -> tuple[MatrixCoreDeltaV1, ...]:
    prior_shards = {item.core_id: item for item in predecessor.shards}
    next_shards = {item.core_id: item for item in successor.shards}
    if frozenset(prior_shards) != frozenset(next_shards):
        raise PipelineError("matrix refresh changes the core universe")
    prior_cells = {
        (item.coordinate.core_id, item.universe_ordinal): item
        for item in predecessor.cells
    }
    next_cells = {
        (item.coordinate.core_id, item.universe_ordinal): item
        for item in successor.cells
    }
    changes: list[MatrixCoreDeltaV1] = []
    for core_id in sorted(prior_shards):
        before = prior_shards[core_id]
        after = next_shards[core_id]
        changed_ordinals = tuple(
            ordinal
            for ordinal in range(27)
            if prior_cells[(core_id, ordinal)] != next_cells[(core_id, ordinal)]
        )
        if before == after and not changed_ordinals:
            continue
        if changed_ordinals != tuple(range(27)) or before == after:
            raise PipelineError(
                "authority-stage matrix change must replace exact 27-cell shards"
            )
        for ordinal in range(27):
            left = prior_cells[(core_id, ordinal)]
            right = next_cells[(core_id, ordinal)]
            if left.coordinate != right.coordinate or left.partition != right.partition:
                raise PipelineError("matrix refresh changes coordinate support policy")
        changes.append(
            MatrixCoreDeltaV1(
                core_id=core_id,
                predecessor_cells=tuple(link.reference for link in before.cells),
                successor_cells=tuple(link.reference for link in after.cells),
                predecessor_shard=predecessor.root.shards[
                    tuple(item.core_id for item in predecessor.root.shards).index(core_id)
                ].reference,
                successor_shard=successor.root.shards[
                    tuple(item.core_id for item in successor.root.shards).index(core_id)
                ].reference,
            )
        )
    if not changes:
        raise PipelineError("authority-stage matrix refresh has no changed core")
    return tuple(changes)


def _matrix_member_payloads(
    copies: tuple[AuthorityCopyPayloadV1, ...],
) -> dict[str, AuthorityCopyPayloadV1]:
    result: dict[str, AuthorityCopyPayloadV1] = {}
    for item in copies:
        prefix = "matrix.member."
        if not item.copy.name.startswith(prefix):
            continue
        name = item.copy.name.removeprefix(prefix)
        if name in result:
            raise PipelineError("matrix replay member copy is duplicated")
        result[name] = item
    return result


def _matrix_replay_member_names(
    replay: MatrixRefreshReplayV1,
) -> tuple[str, ...]:
    """Return the exact semantic-use closure of one H6 replay request."""

    if type(replay) is not MatrixRefreshReplayV1:
        raise PipelineError("matrix replay must be exact")
    names = {
        replay.generator_copy,
        replay.track_registry_copy,
        replay.pipeline_bundle_copy,
    }
    for row in replay.cells:
        names.add(row.inventory_copy)
        names.update(item.copy for item in row.source_registry_snapshots)
        if row.evidence is not None:
            names.update(
                getattr(row.evidence, field) for field in EvidenceReplayV1._FIELDS
            )
    for directory in (
        replay.pin_directory,
        replay.track_registry_snapshot_directory,
    ):
        if directory is not None:
            names.update(directory.members)
    return tuple(sorted(names))


def _validate_copy_graph(
    replay: MatrixRefreshReplayV1,
    copies: tuple[AuthorityCopyPayloadV1, ...],
) -> None:
    """Require every general copy to be consumed by exactly one owned surface."""

    if type(copies) is not tuple or any(
        type(item) is not AuthorityCopyPayloadV1 for item in copies
    ):
        raise PipelineError("authority-stage copy graph payloads are invalid")
    actual = tuple(item.copy.name for item in copies)
    source_names = {
        name for name in actual if _PHASE_SOURCE_COPY_RE.fullmatch(name) is not None
    }
    matrix_names = {
        f"matrix.member.{name}" for name in _matrix_replay_member_names(replay)
    }
    expected = tuple(sorted((*_PHASE_FIXED_COPY_NAMES, *source_names, *matrix_names)))
    if actual != expected:
        missing = tuple(sorted(set(expected) - set(actual)))
        unused = tuple(sorted(set(actual) - set(expected)))
        raise PipelineError(
            "authority-stage copy graph is not exact: "
            f"missing={missing}, unused={unused}"
        )


def _hydrated_member(
    members: Mapping[str, AuthorityCopyPayloadV1],
    name: str,
    *,
    label: str,
) -> HydratedArtifactV1:
    try:
        item = members[name]
    except KeyError as exc:
        raise PipelineError(f"matrix replay lacks {label} member: {name}") from exc
    return HydratedArtifactV1(path=item.copy.source.path, raw=item.raw)


def _evidence_from_replay(
    value: EvidenceReplayV1,
    members: Mapping[str, AuthorityCopyPayloadV1],
) -> TrackCellEvidenceV1:
    return TrackCellEvidenceV1(
        pin=_hydrated_member(members, value.pin, label="pin"),
        golden=_hydrated_member(members, value.golden, label="golden"),
        selected_e2e=_hydrated_member(
            members, value.selected_e2e, label="selected e2e"
        ),
        reproduction_e2e=_hydrated_member(
            members, value.reproduction_e2e, label="reproduction e2e"
        ),
        selected_telemetry=_hydrated_member(
            members, value.selected_telemetry, label="selected telemetry"
        ),
        reproduction_telemetry=_hydrated_member(
            members,
            value.reproduction_telemetry,
            label="reproduction telemetry",
        ),
        selected_build_record=_hydrated_member(
            members, value.selected_build_record, label="selected build record"
        ),
        reproduction_build_record=_hydrated_member(
            members,
            value.reproduction_build_record,
            label="reproduction build record",
        ),
        telemetry_schema=_hydrated_member(
            members, value.telemetry_schema, label="telemetry schema"
        ),
    )


def _directory_from_replay(
    value: DirectoryReplayV1 | None,
    members: Mapping[str, AuthorityCopyPayloadV1],
) -> DirectoryFingerprintV1 | None:
    if value is None:
        return None
    files = tuple(
        sorted(
            (
                _hydrated_member(members, name, label="directory")
                for name in value.members
            ),
            key=lambda item: item.path,
        )
    )
    return DirectoryFingerprintV1(path=value.path, files=files)


def replay_matrix_refresh(
    predecessor: NormalizedMatrixV1,
    *,
    replay: MatrixRefreshReplayV1,
    copies: tuple[AuthorityCopyPayloadV1, ...],
    phase_freeze: EvidenceRef,
    captured_at: str,
) -> NormalizedMatrixV1:
    """Rerun every pure H6 projection from the persisted typed/raw request."""

    if type(predecessor) is not NormalizedMatrixV1 or type(
        replay
    ) is not MatrixRefreshReplayV1:
        raise PipelineError("matrix replay arguments are invalid")
    validate_normalized_matrix(predecessor)
    members = _matrix_member_payloads(copies)
    registry_artifact = _hydrated_member(
        members, replay.track_registry_copy, label="track registry"
    )
    registry = registry_artifact.document(label="matrix replay track registry")
    bundle_member = members.get(replay.pipeline_bundle_copy)
    if bundle_member is None:
        raise PipelineError("matrix replay lacks its pipeline bundle member")
    bundle_artifact = _hydrated_member(
        members, replay.pipeline_bundle_copy, label="pipeline bundle"
    )
    bundle = decode_identity_object(
        bundle_artifact.raw, label="matrix replay pipeline bundle"
    )
    if not pipeline_source_bundle_is_well_formed(bundle):
        raise PipelineError("matrix replay pipeline bundle is invalid")
    bundle_content = bundle.get("content_sha256")
    if (
        type(bundle_content) is not str
        or (
            bundle_member.copy.source.target_content_sha256 is not None
            and bundle_member.copy.source.target_content_sha256 != bundle_content
        )
    ):
        raise PipelineError("matrix replay pipeline bundle identity is invalid")
    pipeline_identity = PipelineBundleIdentityV1(
        schema_version=bundle.get("schema_version"),  # type: ignore[arg-type]
        file_count=len(bundle.get("files", {})),  # type: ignore[arg-type]
        content_sha256=bundle_content,
    )
    prior_by_coordinate = {
        item.coordinate: item
        for item in predecessor.cells
        if item.coordinate.core_id == replay.core_id
    }
    if len(prior_by_coordinate) != 27:
        raise PipelineError("matrix replay predecessor shard is incomplete")
    evidence_by_record: dict[EvidenceReplayV1, TrackCellEvidenceV1] = {}
    replacement: list[MatrixCellV1] = []
    for row in replay.cells:
        inventory_artifact = _hydrated_member(
            members, row.inventory_copy, label="track inventory"
        )
        inventory = decode_matrix_v2(inventory_artifact.raw)
        evidence = None
        if row.evidence is not None:
            evidence = evidence_by_record.setdefault(
                row.evidence, _evidence_from_replay(row.evidence, members)
            )
        snapshots = {
            item.content_sha256: _hydrated_member(
                members, item.copy, label="source registry snapshot"
            )
            for item in row.source_registry_snapshots
        }
        replacement.append(
            project_track_inventory_cell_v1(
                inventory,
                coordinate=row.coordinate,
                track_registry=registry,
                predecessor_cell=prior_by_coordinate[row.coordinate],
                evidence=evidence,
                producer_coordinate=row.producer_coordinate,
                pipeline_bundle_content_sha256=(
                    row.pipeline_bundle_content_sha256
                ),
                source_registry_snapshots=snapshots,
            )
        )
    replacements = tuple(replacement)
    replacement_by_coordinate = {item.coordinate: item for item in replacements}
    successor_cells = tuple(
        replacement_by_coordinate.get(item.coordinate, item)
        for item in predecessor.cells
    )
    evidence_records = tuple(
        sorted(evidence_by_record.values(), key=lambda item: item.pin.path)
    )
    root_projection = project_matrix_root_refresh_v1(
        predecessor,
        cells=successor_cells,
        captured_at=captured_at,
        audit_label=replay.audit_label,
        leaf_audit_id=replay.leaf_audit_id,
        reason=replay.reason,
        predecessor_pointer_path=replay.predecessor_pointer_path,
        generator=_hydrated_member(
            members, replay.generator_copy, label="matrix generator"
        ),
        phase_freeze=phase_freeze,
        track_registry_artifact=registry_artifact,
        pipeline_bundle=pipeline_identity,
        authoritative_suite_summary=replay.authoritative_suite_summary,
        edge_source_count=replay.edge_source_count,
        evidence_records=evidence_records,
        pin_directory=_directory_from_replay(replay.pin_directory, members),
        track_registry_snapshot_directory=_directory_from_replay(
            replay.track_registry_snapshot_directory, members
        ),
    )
    return splice_matrix_core_refresh_v1(
        predecessor,
        replacement_cells=replacements,
        legacy_root_projection=root_projection,
        phase_freeze=phase_freeze,
    )


def _legacy_stage(
    store: CampaignStore,
    *,
    campaign_id: str,
    predecessor_pointer: EvidenceRef,
    successor_raw: bytes,
    successor_content_sha256: str,
) -> LegacyMatrixStageV1:
    canonical = store.reference_for(
        kind="matrix-snapshot",
        raw=successor_raw,
        target_content_sha256=successor_content_sha256,
    )
    common = {
        "file_sha256": canonical.file_sha256,
        "target_content_sha256": canonical.target_content_sha256,
        "size": canonical.size,
    }
    return LegacyMatrixStageV1(
        predecessor_pointer=predecessor_pointer,
        successor_pointer=EvidenceRef(
            kind="matrix-pointer", path=predecessor_pointer.path, **common
        ),
        canonical_object=canonical,
        semantic_alias=EvidenceRef(
            kind="matrix-snapshot",
            path=(
                f"{LEGACY_MATRIX_ROOT}/{campaign_id}/matrices/"
                f"{successor_content_sha256}.json"
            ),
            **common,
        ),
        raw_alias=EvidenceRef(
            kind="matrix-cas",
            path=(
                f"{LEGACY_MATRIX_CAS_ROOT}/{canonical.file_sha256[:2]}/"
                f"{canonical.file_sha256}"
            ),
            **common,
        ),
    )


def _state_root_value(
    store: CampaignStore,
    reader: AuthorityStageReader,
    reference: EvidenceRef,
) -> StateRoot:
    raw = reader.read_exact(reference)
    expected = store.reference_for(
        kind="state-root",
        raw=raw,
        target_content_sha256=reference.target_content_sha256,
    )
    if expected != reference:
        raise PipelineError("current StateRoot reference is not canonical")
    value = StateRoot.from_document(decode_identity_object(raw, label="current StateRoot"))
    if rendered_json_bytes(value.to_document()) != raw:
        raise PipelineError("current StateRoot bytes are not canonical")
    if reference.target_content_sha256 != value.content_sha256:
        raise PipelineError("current StateRoot semantic reference is invalid")
    return value


def _assert_pointer(
    reader: AuthorityStageReader,
    expected: EvidenceRef,
    raw: bytes,
) -> None:
    state = reader.read_pointer(expected)
    if state is None or getattr(state, "raw", None) != raw:
        raise PipelineError("legacy matrix pointer differs from the planned predecessor")


def _phase_authority_references(
    phase_result: PlannedPhaseFreeze,
) -> dict[str, EvidenceRef]:
    result = {
        item.name: item.reference
        for item in phase_result.phase_freeze.authorities
    }
    if tuple(sorted(result)) != INPUT_ROLE_NAMES:
        raise PipelineError("strict phase-freeze authority roles are not exact")
    return result


def _same_source_projection(left: EvidenceRef, right: EvidenceRef) -> bool:
    return (
        left.path == right.path
        and left.file_sha256 == right.file_sha256
        and left.size == right.size
        and (
            left.target_content_sha256 is None
            or right.target_content_sha256 is None
            or left.target_content_sha256 == right.target_content_sha256
        )
    )


def validate_h5_h6_authority_bindings(
    *,
    phase_result: PlannedPhaseFreeze,
    predecessor_matrix: NormalizedMatrixV1,
    successor_matrix: NormalizedMatrixV1,
    matrix_replay: MatrixRefreshReplayV1,
    copies: tuple[AuthorityCopyPayloadV1, ...],
) -> None:
    """Cross-bind the replayed H6 closure to the exact strict H5 authorities."""

    if type(phase_result) is not PlannedPhaseFreeze or type(
        predecessor_matrix
    ) is not NormalizedMatrixV1 or type(successor_matrix) is not NormalizedMatrixV1:
        raise PipelineError("H5/H6 authority binding inputs are invalid")
    if type(matrix_replay) is not MatrixRefreshReplayV1 or type(copies) is not tuple:
        raise PipelineError("H5/H6 replay binding inputs are invalid")
    validate_normalized_matrix(predecessor_matrix)
    validate_normalized_matrix(successor_matrix)
    authorities = _phase_authority_references(phase_result)
    if predecessor_matrix.root.core_spec_set != authorities["core-spec-set"] or (
        successor_matrix.root.core_spec_set != authorities["core-spec-set"]
    ):
        raise PipelineError(
            "matrix CoreSpec authority differs from the strict phase freeze"
        )

    phase_sources = {
        item.copy.source.path: item
        for item in copies
        if _PHASE_SOURCE_COPY_RE.fullmatch(item.copy.name) is not None
    }
    members = _matrix_member_payloads(copies)
    telemetry_schema_names = tuple(
        sorted(
            {
                row.evidence.telemetry_schema
                for row in matrix_replay.cells
                if row.evidence is not None
            }
        )
    )
    required_overlap_names = {
        matrix_replay.generator_copy,
        matrix_replay.track_registry_copy,
        *telemetry_schema_names,
    }
    for name, member in members.items():
        phase_source = phase_sources.get(member.copy.source.path)
        if phase_source is None:
            if name in required_overlap_names:
                raise PipelineError(
                    f"matrix member lacks captured H5 source overlap: {name}"
                )
            continue
        if member.raw != phase_source.raw or not _same_source_projection(
            member.copy.source, phase_source.copy.source
        ):
            raise PipelineError(
                f"matrix member differs from captured H5 source: {name}"
            )
    for name in telemetry_schema_names:
        try:
            telemetry_schema = members[name]
        except KeyError as exc:
            raise PipelineError(
                f"matrix replay lacks telemetry schema member: {name}"
            ) from exc
        if telemetry_schema.copy.source != authorities["telemetry-schema"]:
            raise PipelineError(
                f"matrix telemetry schema differs from H5 authority: {name}"
            )

    inventory_expected = {
        "catalog_content_sha256": authorities["catalog"].target_content_sha256,
        "track_registry_content_sha256": authorities["tracks"].target_content_sha256,
        "tuning_registry_content_sha256": authorities["tunings"].target_content_sha256,
    }
    if any(item is None for item in inventory_expected.values()):
        raise PipelineError("H5 matrix authority lacks semantic identity")
    for name in sorted({row.inventory_copy for row in matrix_replay.cells}):
        inventory = decode_matrix_v2(
            _hydrated_member(members, name, label="track inventory").raw
        )
        if any(
            inventory.get(field) != expected
            for field, expected in inventory_expected.items()
        ):
            raise PipelineError(
                f"matrix inventory authorities differ from H5: {name}"
            )

    legacy_projection = decode_matrix_v2(
        successor_matrix.root.legacy_root_json.encode("utf-8")
    )
    legacy_inputs = legacy_projection.get("inputs")
    if type(legacy_inputs) is not dict:
        raise PipelineError("successor legacy matrix inputs are invalid")
    root_roles = {
        "catalog": "catalog",
        "commit_blacklist": "commit-blacklist",
        "branch_bases": "spruce-branch-bases",
        "release_roster": "spruce-release-roster",
        "host_execution_profiles": "host-execution",
        "host_telemetry_schema": "telemetry-schema",
        "toolchain_lock": "toolchain-lock",
        "tracks": "tracks",
        "tunings": "tunings",
    }
    for root_name, role in root_roles.items():
        projection = legacy_inputs.get(root_name)
        if type(projection) is not dict or frozenset(projection) not in {
            frozenset({"path", "file_sha256"}),
            frozenset({"path", "file_sha256", "content_sha256"}),
        }:
            raise PipelineError(f"successor legacy input is not exact: {root_name}")
        reference = authorities[role]
        if (
            projection.get("path") != reference.path
            or projection.get("file_sha256") != reference.file_sha256
            or (
                "content_sha256" in projection
                and projection.get("content_sha256")
                != reference.target_content_sha256
            )
        ):
            raise PipelineError(
                f"successor legacy input differs from H5: {root_name}"
            )


def validate_planned_authority_stage(value: object) -> None:
    """Reconstruct every pure object in one in-memory staging closure."""

    if type(value) is not PlannedAuthorityStageV1:
        raise PipelineError("planned authority stage must be exact")
    plan = value.plan
    if type(plan) is not AuthorityStagePlanV1:
        raise PipelineError("planned authority-stage plan is invalid")
    if type(value.phase_request) is not TransitionRequest:
        raise PipelineError("planned authority-stage phase request is invalid")
    if type(value.phase_result) is not PlannedPhaseFreeze:
        raise PipelineError("planned authority-stage phase result is invalid")
    validate_phase_freeze(value.phase_result, request=value.phase_request)
    if rendered_json_bytes(value.phase_result.plan.to_document()) != value.phase_plan_raw:
        raise PipelineError("phase plan bytes differ from the pure H5 result")
    if value.phase_result.candidate_raw != value.phase_successor_raw:
        raise PipelineError("phase successor bytes differ from the pure H5 result")
    if value.phase_result.plan.campaign_id != plan.campaign_id or (
        value.phase_result.plan.transition_id != plan.transition_id
        or value.phase_result.plan.captured_at != plan.captured_at
    ):
        raise PipelineError("authority-stage identity differs from the phase plan")
    expected_phase_plan = canonical_object_reference(
        state_relative=CAMPAIGN_STATE_RELATIVE,
        kind="transition-plan",
        raw=value.phase_plan_raw,
        target_content_sha256=value.phase_result.plan.content_sha256,
    )
    if plan.phase_plan != expected_phase_plan:
        raise PipelineError("authority-stage phase plan reference is invalid")
    if plan.phase_successor != value.phase_result.plan.successor:
        raise PipelineError("authority-stage phase successor reference is invalid")

    if type(value.copies) is not tuple or not value.copies:
        raise PipelineError("planned authority-stage copy payloads are empty")
    copy_records = tuple(item.copy for item in value.copies)
    if copy_records != tuple(sorted(copy_records, key=lambda item: item.name)):
        raise PipelineError("planned authority-stage copy payloads are not sorted")
    if copy_records != plan.copies:
        raise PipelineError("planned authority-stage copies differ from the plan")
    _plan_receipt_outputs(value)
    if type(value.matrix_replay) is not MatrixRefreshReplayV1 or (
        value.matrix_replay.transition_id != plan.transition_id
    ):
        raise PipelineError("planned matrix replay is invalid")
    if (
        value.matrix_replay.predecessor_pointer_path
        != plan.legacy_matrix.predecessor_pointer.path
    ):
        raise PipelineError(
            "matrix replay predecessor pointer path differs from the plan"
        )
    if value.matrix_replay.reason != value.phase_result.plan.reason:
        raise PipelineError("matrix replay reason differs from the H5 phase plan")
    _validate_copy_graph(value.matrix_replay, value.copies)
    reconstructed = _phase_request_from_copies(plan, value.copies)
    if reconstructed != value.phase_request:
        raise PipelineError("authority-stage phase request differs from copy closure")
    _validate_phase_source_coverage(value.phase_request, value.copies)
    if render_matrix_refresh_replay(value.matrix_replay) != value.matrix_replay_raw:
        raise PipelineError("matrix replay bytes differ from the parsed request")
    expected_replay_ref = canonical_object_reference(
        state_relative=CAMPAIGN_STATE_RELATIVE,
        kind="artifact",
        raw=value.matrix_replay_raw,
        target_content_sha256=value.matrix_replay.content_sha256,
    )
    if plan.matrix_replay.stored != expected_replay_ref or (
        plan.matrix_replay.source.file_sha256 != expected_replay_ref.file_sha256
        or plan.matrix_replay.source.target_content_sha256
        != expected_replay_ref.target_content_sha256
        or plan.matrix_replay.source.size != expected_replay_ref.size
    ):
        raise PipelineError("matrix replay copy does not bind the replay request")
    replay_members = _matrix_member_payloads(value.copies)
    try:
        replay_bundle_raw = replay_members[
            value.matrix_replay.pipeline_bundle_copy
        ].raw
    except KeyError as exc:
        raise PipelineError("matrix replay pipeline bundle copy is missing") from exc
    replay_bundle = decode_identity_object(
        replay_bundle_raw, label="matrix replay source bundle"
    )
    phase_bundle = decode_identity_object(
        value.phase_request.engine_bundle_raw, label="phase engine bundle"
    )
    if replay_bundle != phase_bundle:
        raise PipelineError("matrix replay source bundle differs from H5 engine")

    if type(value.current_state_root) is not StateRoot:
        raise PipelineError("planned current StateRoot is invalid")
    if (
        value.current_state_root.campaign_id != plan.campaign_id
        or value.current_state_root.generation != 1
        or value.current_state_root.previous is not None
    ):
        raise PipelineError("current StateRoot belongs to another campaign")
    if not _same_raw_identity(
        value.current_state_root.current, plan.legacy_matrix.predecessor_pointer
    ):
        raise PipelineError("current StateRoot differs from the predecessor pointer")

    validate_normalized_matrix(value.predecessor_matrix)
    validate_normalized_matrix(value.successor_matrix)
    if value.predecessor_matrix.root_reference != plan.predecessor_matrix_root or (
        value.successor_matrix.root_reference != plan.successor_matrix_root
    ):
        raise PipelineError("normalized matrix roots differ from the plan")
    if value.predecessor_matrix.root.campaign_id != plan.campaign_id or (
        value.successor_matrix.root.campaign_id != plan.campaign_id
    ):
        raise PipelineError("normalized matrix campaign is inconsistent")
    if value.successor_matrix.root.phase_freeze != plan.phase_successor:
        raise PipelineError("successor matrix does not bind the H5 phase freeze")
    if (
        value.successor_matrix.root.core_spec_set
        != value.predecessor_matrix.root.core_spec_set
    ):
        raise PipelineError("matrix refresh changes CoreSpec authority")
    if value.successor_matrix.root.captured_at != plan.captured_at:
        raise PipelineError("matrix captured_at differs from the combined plan")
    replayed = replay_matrix_refresh(
        value.predecessor_matrix,
        replay=value.matrix_replay,
        copies=value.copies,
        phase_freeze=plan.phase_successor,
        captured_at=plan.captured_at,
    )
    if replayed != value.successor_matrix or (
        materialize_matrix_v2(replayed) != value.legacy_raw
    ):
        raise PipelineError("successor matrix differs from pure replay")
    validate_h5_h6_authority_bindings(
        phase_result=value.phase_result,
        predecessor_matrix=value.predecessor_matrix,
        successor_matrix=value.successor_matrix,
        matrix_replay=value.matrix_replay,
        copies=value.copies,
    )
    if _matrix_changes(value.predecessor_matrix, value.successor_matrix) != plan.matrix_changes:
        raise PipelineError("matrix delta differs from the exact closure")
    # The first repository bootstrap is deliberately a one-core Gambatte step;
    # the persisted wire remains batch-capable for later transitions.
    if tuple(item.core_id for item in plan.matrix_changes) != ("gambatte",):
        raise PipelineError("first authority-stage runtime must change only Gambatte")

    predecessor_raw = materialize_matrix_v2(value.predecessor_matrix)
    if materialize_matrix_v2(value.predecessor_matrix) != predecessor_raw:
        raise PipelineError("predecessor matrix double materialization moved")
    if not _same_raw_identity(
        plan.legacy_matrix.predecessor_pointer,
        EvidenceRef(
            kind="matrix-pointer",
            path=plan.legacy_matrix.predecessor_pointer.path,
            file_sha256=sha256_bytes(predecessor_raw),
            target_content_sha256=value.predecessor_matrix.root.legacy_matrix.semantic_sha256,
            size=len(predecessor_raw),
        ),
    ):
        raise PipelineError("predecessor pointer identity differs from normalized bytes")
    successor_raw = materialize_matrix_v2(value.successor_matrix)
    if materialize_matrix_v2(value.successor_matrix) != successor_raw:
        raise PipelineError("successor matrix double materialization moved")
    if successor_raw != value.legacy_raw:
        raise PipelineError("legacy successor bytes differ from normalized matrix")
    if not _same_raw_identity(
        plan.legacy_matrix.canonical_object,
        plan.legacy_matrix.successor_pointer,
    ):
        raise PipelineError("legacy successor identities differ")
    if sha256_bytes(successor_raw) != plan.legacy_matrix.canonical_object.file_sha256:
        raise PipelineError("legacy successor raw identity is invalid")

    if type(value.schema_raw) is not bytes:
        raise PipelineError("authority-stage schema bytes are invalid")
    schema_payloads = tuple(item for item in value.copies if item.copy.name == "stage.schema")
    if len(schema_payloads) != 0:
        raise PipelineError("stage schema must remain outside general copies")
    if len(value.schema_raw) != plan.schema.source.size or (
        sha256_bytes(value.schema_raw) != plan.schema.source.file_sha256
    ):
        raise PipelineError("authority-stage schema source identity is invalid")
    _validate_schema(value.schema_raw, plan)
    expected_plan_ref = canonical_object_reference(
        state_relative=CAMPAIGN_STATE_RELATIVE,
        kind="transition-plan",
        raw=render_authority_stage_plan(plan),
        target_content_sha256=plan.content_sha256,
    )
    if value.plan_reference != expected_plan_ref:
        raise PipelineError("combined authority-stage plan reference is invalid")


def plan_repository_authority_stage(
    store: CampaignStore,
    *,
    phase_bootstrap: object,
    current_state_root_ref: EvidenceRef,
    expected_pointer: EvidenceRef,
    predecessor_matrix: NormalizedMatrixV1,
    successor_matrix: NormalizedMatrixV1,
    matrix_replay: MatrixRefreshReplayV1,
    matrix_members: tuple[AuthenticatedInput, ...],
) -> PlannedAuthorityStageV1:
    """Authenticate current authority and predict one write-free combined plan."""

    if not isinstance(store, CampaignStore) or store.state_relative != CAMPAIGN_STATE_RELATIVE:
        raise PipelineError("authority staging requires the consolidated CampaignStore")
    request = getattr(phase_bootstrap, "request", None)
    result = getattr(phase_bootstrap, "result", None)
    source_members = getattr(phase_bootstrap, "source_members", None)
    if type(request) is not TransitionRequest or type(result) is not PlannedPhaseFreeze:
        raise PipelineError("phase bootstrap result is not the owning H5 runtime result")
    validate_phase_freeze(result, request=request)
    if type(expected_pointer) is not EvidenceRef or expected_pointer.kind != "matrix-pointer":
        raise PipelineError("expected legacy pointer reference is invalid")

    verified_root = verify_transition(store, state_root_ref=current_state_root_ref)
    historical = load_historical_transition(
        store,
        reader=store,
        state_root_ref=current_state_root_ref,
    )
    if historical.state_root != verified_root or (
        historical.current_pointer_ref != expected_pointer
    ):
        raise PipelineError(
            "historical H3 pointer differs from the planned predecessor"
        )
    persisted_root = _state_root_value(store, store, current_state_root_ref)
    if verified_root != persisted_root:
        raise PipelineError("H3 StateRoot verification returned a different root")
    predecessor_raw = materialize_matrix_v2(predecessor_matrix)
    _assert_pointer(store, expected_pointer, predecessor_raw)

    schema_raw_first = store.read_snapshot(SCHEMA_PATH)
    schema_raw_second = store.read_snapshot(SCHEMA_PATH)
    if schema_raw_first != schema_raw_second:
        raise PipelineError("authority-stage schema moved during capture")
    schema_document = _schema_document(schema_raw_first)
    schema_source = EvidenceRef(
        kind="artifact",
        path=SCHEMA_PATH,
        file_sha256=sha256_bytes(schema_raw_first),
        target_content_sha256=canonical_json_sha256(schema_document),
        size=len(schema_raw_first),
    )
    schema_payload = _copy_payload(
        store,
        name="stage.schema",
        source=schema_source,
        raw=schema_raw_first,
    )

    phase_copies = _phase_copy_payloads(store, request, source_members)
    if type(matrix_members) is not tuple or any(
        type(item) is not AuthenticatedInput for item in matrix_members
    ):
        raise PipelineError("matrix members must be exact AuthenticatedInput values")
    member_names = tuple(item.name for item in matrix_members)
    if member_names != tuple(sorted(member_names)) or len(member_names) != len(set(member_names)):
        raise PipelineError("matrix members must be sorted and unique")
    matrix_copies = tuple(
        _copy_payload(
            store,
            name=f"matrix.member.{item.name}",
            source=item.reference,
            raw=item.raw,
        )
        for item in matrix_members
    )
    copies = tuple(
        sorted((*phase_copies, *matrix_copies), key=lambda item: item.copy.name)
    )

    phase_plan_raw = rendered_json_bytes(result.plan.to_document())
    phase_plan_ref = store.reference_for(
        kind="transition-plan",
        raw=phase_plan_raw,
        target_content_sha256=result.plan.content_sha256,
    )
    if type(matrix_replay) is not MatrixRefreshReplayV1 or (
        matrix_replay.transition_id != result.plan.transition_id
    ):
        raise PipelineError("matrix replay does not belong to the H5 transition")
    matrix_replay_raw = render_matrix_refresh_replay(matrix_replay)
    matrix_replay_source = EvidenceRef(
        kind="artifact",
        path=(
            "campaign/evidence/"
            f"{result.plan.transition_id}-matrix-refresh-replay-v1.json"
        ),
        file_sha256=sha256_bytes(matrix_replay_raw),
        target_content_sha256=matrix_replay.content_sha256,
        size=len(matrix_replay_raw),
    )
    matrix_replay_payload = _copy_payload(
        store,
        name="matrix.replay",
        source=matrix_replay_source,
        raw=matrix_replay_raw,
    )
    successor_raw = materialize_matrix_v2(successor_matrix)
    legacy = _legacy_stage(
        store,
        campaign_id=result.plan.campaign_id,
        predecessor_pointer=expected_pointer,
        successor_raw=successor_raw,
        successor_content_sha256=successor_matrix.root.legacy_matrix.semantic_sha256,
    )
    plan = AuthorityStagePlanV1(
        campaign_id=result.plan.campaign_id,
        transition_id=result.plan.transition_id,
        captured_at=result.plan.captured_at,
        schema=schema_payload.copy,
        matrix_replay=matrix_replay_payload.copy,
        copies=tuple(item.copy for item in copies),
        current_state_root=current_state_root_ref,
        phase_plan=phase_plan_ref,
        phase_successor=result.plan.successor,
        predecessor_matrix_root=predecessor_matrix.root_reference,
        successor_matrix_root=successor_matrix.root_reference,
        matrix_changes=_matrix_changes(predecessor_matrix, successor_matrix),
        legacy_matrix=legacy,
    )
    plan_raw = render_authority_stage_plan(plan)
    planned = PlannedAuthorityStageV1(
        plan=plan,
        plan_reference=store.reference_for(
            kind="transition-plan",
            raw=plan_raw,
            target_content_sha256=plan.content_sha256,
        ),
        phase_request=request,
        phase_result=result,
        phase_plan_raw=phase_plan_raw,
        phase_successor_raw=result.candidate_raw,
        schema_raw=schema_raw_first,
        matrix_replay=matrix_replay,
        matrix_replay_raw=matrix_replay_raw,
        copies=copies,
        current_state_root=persisted_root,
        predecessor_matrix=predecessor_matrix,
        successor_matrix=successor_matrix,
        legacy_raw=successor_raw,
    )
    _assert_pointer(store, expected_pointer, predecessor_raw)
    return planned


def _stage_exact(
    store: CampaignStore,
    reference: EvidenceRef,
    raw: bytes,
    *,
    caller_path: bool = False,
) -> None:
    if caller_path:
        store.create_or_verify_reference(reference=reference, raw=raw)
    else:
        store.create_or_verify(reference=reference, raw=raw)
    if store.read_exact(reference) != raw:
        raise PipelineError(f"staged {reference.kind} bytes differ after publication")


def _receipt_outputs(
    planned: PlannedAuthorityStageV1,
    process_receipt: StoredCheckReceipt,
) -> tuple[EvidenceRef, ...]:
    return _sorted_unique_refs(
        *_plan_receipt_outputs(planned),
        process_receipt.receipt_ref,
        *process_receipt.artifact_refs,
    )


def _plan_receipt_outputs(
    planned: PlannedAuthorityStageV1,
) -> tuple[EvidenceRef, ...]:
    return _sorted_unique_refs(
        planned.plan_reference,
        planned.plan.current_state_root,
        planned.plan.phase_plan,
        planned.plan.phase_successor,
        planned.plan.predecessor_matrix_root,
        planned.plan.successor_matrix_root,
        planned.plan.legacy_matrix.canonical_object,
        planned.plan.legacy_matrix.semantic_alias,
        planned.plan.legacy_matrix.raw_alias,
        planned.plan.schema.stored,
        planned.plan.matrix_replay.stored,
        *(item.copy.stored for item in planned.copies),
    )


def authoritative_suite_summary(
    *,
    passed_count: int,
    skipped_ids: tuple[str, ...] = FULL_STATIC_ALLOWED_SKIPS,
) -> str:
    """Render the sole legacy-root summary accepted from H4 pytest facts."""

    if type(passed_count) is not int or passed_count < 1:
        raise PipelineError("authoritative suite passed count must be positive")
    if type(skipped_ids) is not tuple or skipped_ids != FULL_STATIC_ALLOWED_SKIPS:
        raise PipelineError("authoritative suite skip IDs are not exact")
    return (
        f"pytest: {passed_count} passed, {len(skipped_ids)} skipped; "
        f"skip_ids={','.join(skipped_ids)}"
    )


def _suite_summary_from_process_receipt(
    reader: AuthorityStageReader,
    receipt: object,
    artifact_refs: tuple[EvidenceRef, ...],
) -> str:
    results = getattr(receipt, "results", None)
    if type(results) is not tuple:
        raise PipelineError("stored H4 receipt has no exact result tuple")
    matches = tuple(item for item in results if item.check_id == "tests.full-static")
    if len(matches) != 1:
        raise PipelineError("stored H4 receipt lacks one full-static result")
    result = matches[0]
    json_outputs = tuple(
        item
        for item in result.structured_outputs
        if item.format is StructuredFormat.JSON
    )
    if len(json_outputs) != 1:
        raise PipelineError("full-static result lacks one JSON report")
    output = json_outputs[0]
    artifacts = {
        (item.file_sha256, item.size): reader.read_exact(item)
        for item in artifact_refs
    }
    try:
        raw = artifacts[(output.sha256, output.size)]
    except KeyError as exc:
        raise PipelineError("full-static JSON report is absent from H4 closure") from exc
    report = decode_canonical_json_bytes(raw, label="full-static JSON report")
    tests = report.get("tests")
    if type(tests) is not list:
        raise PipelineError("full-static JSON report tests are invalid")
    passed = 0
    skipped: list[str] = []
    for item in tests:
        if type(item) is not dict:
            raise PipelineError("full-static JSON test row is invalid")
        outcome = item.get("outcome")
        if outcome == "passed":
            passed += 1
        elif outcome == "skipped":
            node_id = item.get("node_id")
            if type(node_id) is not str:
                raise PipelineError("full-static skipped node ID is invalid")
            skipped.append(node_id)
        else:
            raise PipelineError("full-static report contains a nonpassing result")
    if tuple(skipped) != FULL_STATIC_ALLOWED_SKIPS:
        raise PipelineError("full-static skip IDs/order are not exact")
    if result.skipped_tests != tuple(skipped):
        raise PipelineError("full-static receipt facts differ from its reporter")
    summaries = tuple(_PYTEST_SUMMARY_RE.finditer(result.stdout))
    if len(summaries) != 1:
        raise PipelineError("full-static stdout lacks one exact pytest summary")
    stdout_passed = int(summaries[0].group("passed"))
    stdout_skipped = int(summaries[0].group("skipped"))
    if stdout_passed != passed or stdout_skipped != len(skipped):
        raise PipelineError("full-static stdout differs from its reporter")
    return authoritative_suite_summary(
        passed_count=passed,
        skipped_ids=tuple(skipped),
    )


def _require_process_receipt(
    store: CampaignStore,
    reader: AuthorityStageReader,
    planned: PlannedAuthorityStageV1,
    process_receipt: StoredCheckReceipt,
) -> None:
    if type(process_receipt) is not StoredCheckReceipt:
        raise PipelineError("authority staging requires a StoredCheckReceipt")
    receipt = validate_stored_check_receipt(
        store=store,
        reader=reader,
        receipt_ref=process_receipt.receipt_ref,
        artifact_refs=process_receipt.artifact_refs,
        expected_subject=planned.plan.content_sha256,
        expected_tier=CheckTier.EVIDENCE,
        expected_check_ids=check_ids_for_tier(CheckTier.EVIDENCE),
    )
    summary = _suite_summary_from_process_receipt(
        reader, receipt, process_receipt.artifact_refs
    )
    if summary != planned.matrix_replay.authoritative_suite_summary:
        raise PipelineError(
            "matrix authoritative suite summary differs from authenticated H4 facts"
        )


def _staged_receipt(
    planned: PlannedAuthorityStageV1,
    process_receipt: StoredCheckReceipt,
    *,
    clock: Clock,
) -> Receipt:
    if not callable(clock):
        raise PipelineError("authority-stage clock must be callable")
    timestamp = clock()
    checks = tuple(
        CheckResult(
            check_id=check_id,
            subject_sha256=planned.plan.content_sha256,
            status="passed",
            evidence=(process_receipt.receipt_ref,),
        )
        for check_id in planned.plan.required_checks
    )
    return Receipt(
        transition_id=planned.plan.transition_id,
        plan=planned.plan_reference,
        stage="staged",
        status="passed",
        started_at=timestamp,
        completed_at=timestamp,
        checks=checks,
        outputs=_receipt_outputs(planned, process_receipt),
    )


def stage_authority_plan(
    store: CampaignStore,
    planned: PlannedAuthorityStageV1,
    *,
    process_receipt: StoredCheckReceipt,
    clock: Clock = _utc_now,
) -> EvidenceRef:
    """Publish a validated closure and its sole resume receipt, receipt last."""

    if not isinstance(store, CampaignStore):
        raise PipelineError("authority staging requires CampaignStore")
    if type(planned) is not PlannedAuthorityStageV1:
        raise PipelineError("authority staging requires an exact planned closure")
    # Cheap mutable-source gates precede the expensive pure matrix replay, but
    # every gate still completes before the first create-or-verify below.
    _live_sources_match(
        store.repository_root,
        planned.phase_request,
        planned.copies,
    )
    _live_schema_matches(store, planned.schema_raw)
    historical_store = (
        store
        if type(store) is CampaignStore
        else CampaignStore(store.repository_root, store.state_relative)
    )
    historical = load_historical_transition(
        historical_store,
        reader=store,
        state_root_ref=planned.plan.current_state_root,
    )
    if (
        historical.state_root != planned.current_state_root
        or historical.state_root_ref != planned.plan.current_state_root
        or historical.current_pointer_ref
        != planned.plan.legacy_matrix.predecessor_pointer
    ):
        raise PipelineError("planned historical H3 closure moved before staging")
    validate_planned_authority_stage(planned)
    _require_process_receipt(store, store, planned, process_receipt)
    _assert_pointer(
        store,
        planned.plan.legacy_matrix.predecessor_pointer,
        materialize_matrix_v2(planned.predecessor_matrix),
    )

    receipt = _staged_receipt(planned, process_receipt, clock=clock)
    receipt_raw = rendered_json_bytes(receipt.to_document())
    receipt_ref = store.reference_for(
        kind="validation-receipt",
        raw=receipt_raw,
        target_content_sha256=receipt.content_sha256,
    )

    # Complete in-memory validation above precedes the first create-or-verify.
    _stage_exact(store, planned.plan.schema.stored, planned.schema_raw)
    for item in planned.copies:
        if item.copy.name.startswith("phase."):
            _stage_exact(store, item.copy.stored, item.raw)
    _stage_exact(store, planned.plan.phase_successor, planned.phase_successor_raw)
    _stage_exact(store, planned.plan.phase_plan, planned.phase_plan_raw)
    for item in planned.copies:
        if item.copy.name.startswith("matrix.member."):
            _stage_exact(store, item.copy.stored, item.raw)
    _stage_exact(
        store,
        planned.plan.matrix_replay.stored,
        planned.matrix_replay_raw,
    )

    stage_normalized_matrix(store, planned.predecessor_matrix)
    stage_normalized_matrix(store, planned.successor_matrix)
    legacy = planned.plan.legacy_matrix
    _stage_exact(store, legacy.canonical_object, planned.legacy_raw)
    _stage_exact(store, legacy.semantic_alias, planned.legacy_raw, caller_path=True)
    _stage_exact(store, legacy.raw_alias, planned.legacy_raw, caller_path=True)
    _stage_exact(
        store,
        planned.plan_reference,
        render_authority_stage_plan(planned.plan),
    )

    _stage_exact(store, receipt_ref, receipt_raw)
    load_staged_authority_plan(
        store,
        receipt_ref,
        require_live_engine=True,
    )
    return receipt_ref


def _read_canonical(
    store: CampaignStore,
    reader: AuthorityStageReader,
    reference: EvidenceRef,
    *,
    label: str,
) -> bytes:
    raw = reader.read_exact(reference)
    expected = store.reference_for(
        kind=reference.kind,
        raw=raw,
        target_content_sha256=reference.target_content_sha256,
    )
    if expected != reference:
        raise PipelineError(f"{label} reference is not canonical")
    return raw


def _load_normalized_matrix_from_reader(
    reader: AuthorityStageReader,
    root_reference: EvidenceRef,
) -> NormalizedMatrixV1:
    """Hydrate an H6 closure through a caller's already-locked read view."""

    if type(root_reference) is not EvidenceRef or root_reference.kind != "matrix-root":
        raise PipelineError("normalized matrix root reference is invalid")

    def read_object(
        reference: EvidenceRef,
        expected_type: type[MatrixCellV1]
        | type[MatrixShardV1]
        | type[MatrixRootV1],
        *,
        label: str,
    ) -> MatrixCellV1 | MatrixShardV1 | MatrixRootV1:
        value = decode_matrix_v1(reader.read_exact(reference))
        if type(value) is not expected_type or matrix_object_reference(value) != reference:
            raise PipelineError(f"{label} is not canonical for its bytes")
        return value

    root_value = read_object(
        root_reference,
        MatrixRootV1,
        label="normalized matrix root",
    )
    assert type(root_value) is MatrixRootV1
    shard_refs = tuple(item.reference for item in root_value.shards)
    if len(shard_refs) != len(set(shard_refs)):
        raise PipelineError("normalized matrix root repeats a shard")
    shards: list[MatrixShardV1] = []
    cells: dict[tuple[str, int], MatrixCellV1] = {}
    for root_link in root_value.shards:
        shard_value = read_object(
            root_link.reference,
            MatrixShardV1,
            label=f"normalized matrix shard {root_link.core_id}",
        )
        assert type(shard_value) is MatrixShardV1
        if shard_value.link(root_link.reference) != root_link:
            raise PipelineError("normalized matrix root-to-shard link is invalid")
        shards.append(shard_value)
        for cell_link in shard_value.cells:
            cell_value = read_object(
                cell_link.reference,
                MatrixCellV1,
                label=(
                    "normalized matrix cell "
                    f"{shard_value.core_id}/{cell_link.universe_ordinal}"
                ),
            )
            assert type(cell_value) is MatrixCellV1
            if cell_value.link(cell_link.reference) != cell_link:
                raise PipelineError("normalized matrix shard-to-cell link is invalid")
            key = (cell_value.coordinate.core_id, cell_value.universe_ordinal)
            if key in cells or cell_value.coordinate.core_id != shard_value.core_id:
                raise PipelineError("normalized matrix cell closure is not unique")
            cells[key] = cell_value
    coordinates = legacy_coordinate_order(tuple(item.core_id for item in shards))
    try:
        ordered_cells = tuple(
            cells[(item.core_id, item.universe_ordinal)] for item in coordinates
        )
    except KeyError as exc:
        raise PipelineError("normalized matrix cell closure is incomplete") from exc
    if len(cells) != len(ordered_cells):
        raise PipelineError("normalized matrix cell closure is not exact")
    result = NormalizedMatrixV1(
        root=root_value,
        root_reference=root_reference,
        shards=tuple(shards),
        cells=ordered_cells,
    )
    validate_normalized_matrix(result)
    return result


def _live_sources_match(
    repository_root: Path,
    request: TransitionRequest,
    copies: tuple[AuthorityCopyPayloadV1, ...],
) -> None:
    if not isinstance(repository_root, Path):
        raise PipelineError("staged repository root is invalid")
    if type(request) is not TransitionRequest:
        raise PipelineError("staged phase request is invalid")
    expected = tuple(
        sorted(
            (
                item.copy.source.path,
                item.raw,
                item.copy.source_mode,
            )
            for item in copies
            if item.copy.name.startswith("phase.source.")
        )
    )
    if not expected or any(type(mode) is not int for _path, _raw, mode in expected):
        raise PipelineError("staged repository source closure is incomplete")

    # Reapply the owning bootstrap's complete descriptor-enumerated policy. A
    # new workflow or package module is therefore source drift too.
    arguments = {"repository_root": repository_root}
    first = capture_repository_phase_freeze_sources(**arguments)
    second = capture_repository_phase_freeze_sources(**arguments)
    if first != second:
        raise PipelineError("live repository source moved during recapture")
    live_projection = tuple(
        (item.path, item.raw, item.mode) for item in first.members
    )
    if live_projection != expected:
        raise PipelineError("live repository source differs from staged provenance")


def _live_schema_matches(store: CampaignStore, expected_raw: bytes) -> None:
    first = store.read_snapshot(SCHEMA_PATH)
    second = store.read_snapshot(SCHEMA_PATH)
    if first != second or first != expected_raw:
        raise PipelineError("live authority-stage schema differs from staged provenance")


def _process_receipt_from_outputs(
    reader: AuthorityStageReader,
    outputs: tuple[EvidenceRef, ...],
) -> StoredCheckReceipt:
    receipt_refs = tuple(item for item in outputs if item.kind == "check-log")
    if len(receipt_refs) != 1:
        raise PipelineError("staged outputs must contain one H4 check-log")
    raw = reader.read_exact(receipt_refs[0])
    receipt = CheckReceipt.from_bytes(raw)
    expected_keys = {
        (structured.sha256, structured.size)
        for result in receipt.results
        for structured in result.structured_outputs
    }
    artifacts_by_key = {
        (item.file_sha256, item.size): item
        for item in outputs
        if item.kind == "artifact" and item.target_content_sha256 is None
    }
    try:
        artifact_refs = tuple(
            sorted(
                (artifacts_by_key[key] for key in expected_keys),
                key=lambda item: (item.kind, item.path),
            )
        )
    except KeyError as exc:
        raise PipelineError("staged outputs omit an H4 structured artifact") from exc
    return StoredCheckReceipt(
        receipt_ref=receipt_refs[0],
        artifact_refs=artifact_refs,
    )


def load_staged_authority_plan(
    store: CampaignStore,
    staged_receipt_ref: EvidenceRef,
    *,
    require_live_engine: bool,
    reader: AuthorityStageReader | None = None,
    historical_root_loader: HistoricalRootLoader | None = None,
) -> StagedAuthorityStageV1:
    """Deeply reload one receipt-selected staging closure without mutation.

    The default H3 loader authenticates immutable ancestry only: it neither
    reads a mutable pointer nor acquires another lock.  An outer transaction
    may inject its read-only view and an equivalent exact loader.
    """

    if not isinstance(store, CampaignStore) or type(require_live_engine) is not bool:
        raise PipelineError("staged authority load arguments are invalid")
    exact_reader = store if reader is None else reader
    if not callable(getattr(exact_reader, "read_exact", None)):
        raise PipelineError("staged authority reader is invalid")
    if historical_root_loader is not None and not callable(historical_root_loader):
        raise PipelineError("historical root loader must be callable")
    receipt_raw = _read_canonical(
        store,
        exact_reader,
        staged_receipt_ref,
        label="staged authority receipt",
    )
    receipt = Receipt.from_document(
        decode_identity_object(receipt_raw, label="staged authority receipt")
    )
    if receipt.stage != "staged" or receipt.status != "passed":
        raise PipelineError("authority-stage receipt is not passed/staged")
    plan_raw = _read_canonical(
        store,
        exact_reader,
        receipt.plan,
        label="authority-stage plan",
    )
    plan = decode_authority_stage_plan(plan_raw)
    if receipt.transition_id != plan.transition_id:
        raise PipelineError("staged receipt transition differs from its plan")

    schema_raw = _read_canonical(
        store,
        exact_reader,
        plan.schema.stored,
        label="authority-stage schema",
    )
    if schema_raw != exact_reader.read_exact(plan.schema.stored):
        raise PipelineError("authority-stage schema moved during reload")
    payloads = tuple(
        AuthorityCopyPayloadV1(
            copy=item,
            raw=_read_canonical(
                store,
                exact_reader,
                item.stored,
                label=item.name,
            ),
        )
        for item in plan.copies
    )
    matrix_replay_raw = _read_canonical(
        store,
        exact_reader,
        plan.matrix_replay.stored,
        label="matrix refresh replay",
    )
    matrix_replay = decode_matrix_refresh_replay(matrix_replay_raw)
    request = _phase_request_from_copies(plan, payloads)
    phase_result = plan_phase_freeze(request)
    validate_phase_freeze(phase_result, request=request)
    phase_plan_raw = _read_canonical(
        store,
        exact_reader,
        plan.phase_plan,
        label="phase plan",
    )
    stored_phase_plan = ResolvedTransitionPlanV1.from_document(
        phase_plan_raw
    )
    if stored_phase_plan != phase_result.plan or (
        rendered_json_bytes(stored_phase_plan.to_document()) != phase_plan_raw
    ):
        raise PipelineError("staged H5 plan differs from reconstruction")
    phase_successor_raw = _read_canonical(
        store,
        exact_reader,
        plan.phase_successor,
        label="phase successor",
    )
    if decode_phase_freeze(phase_successor_raw) != phase_result.phase_freeze or (
        phase_successor_raw != phase_result.candidate_raw
    ):
        raise PipelineError("staged H5 successor differs from reconstruction")
    if require_live_engine:
        _live_sources_match(store.repository_root, request, payloads)
        _live_schema_matches(store, schema_raw)

    persisted_root = _state_root_value(
        store,
        exact_reader,
        plan.current_state_root,
    )
    if historical_root_loader is None:
        historical_store = (
            store
            if type(store) is CampaignStore
            else CampaignStore(store.repository_root, store.state_relative)
        )
        historical = load_historical_transition(
            historical_store,
            reader=exact_reader,
            state_root_ref=plan.current_state_root,
        )
    else:
        historical = historical_root_loader(exact_reader, plan.current_state_root)
    if type(historical) is not LoadedHistoricalTransition or (
        historical.state_root != persisted_root
        or historical.state_root_ref != plan.current_state_root
        or historical.current_pointer_ref
        != plan.legacy_matrix.predecessor_pointer
    ):
        raise PipelineError(
            "historical H3 loader returned a different StateRoot or pointer"
        )
    current_root = historical.state_root
    predecessor = _load_normalized_matrix_from_reader(
        exact_reader,
        plan.predecessor_matrix_root,
    )
    successor = _load_normalized_matrix_from_reader(
        exact_reader,
        plan.successor_matrix_root,
    )
    legacy_raw = _read_canonical(
        store,
        exact_reader,
        plan.legacy_matrix.canonical_object,
        label="legacy canonical matrix",
    )
    for label, reference in (
        ("semantic", plan.legacy_matrix.semantic_alias),
        ("raw", plan.legacy_matrix.raw_alias),
    ):
        if exact_reader.read_exact(reference) != legacy_raw:
            raise PipelineError(f"legacy {label} alias bytes differ")

    planned = PlannedAuthorityStageV1(
        plan=plan,
        plan_reference=receipt.plan,
        phase_request=request,
        phase_result=phase_result,
        phase_plan_raw=phase_plan_raw,
        phase_successor_raw=phase_successor_raw,
        schema_raw=schema_raw,
        matrix_replay=matrix_replay,
        matrix_replay_raw=matrix_replay_raw,
        copies=payloads,
        current_state_root=current_root,
        predecessor_matrix=predecessor,
        successor_matrix=successor,
        legacy_raw=legacy_raw,
    )
    process_receipt = _process_receipt_from_outputs(exact_reader, receipt.outputs)
    _require_process_receipt(store, exact_reader, planned, process_receipt)
    expected_receipt = _staged_receipt(
        planned,
        process_receipt,
        clock=lambda: receipt.started_at,
    )
    if expected_receipt != receipt or rendered_json_bytes(receipt.to_document()) != receipt_raw:
        raise PipelineError("staged authority receipt closure is not exact")
    return StagedAuthorityStageV1(
        planned=planned,
        receipt=receipt,
        receipt_reference=staged_receipt_ref,
        process_receipt=process_receipt,
        historical_transition=historical,
    )


def verify_staged_authority_pointer(
    staged: StagedAuthorityStageV1,
    *,
    expected_pointer: str | None = "predecessor",
    reader: AuthorityStageReader,
) -> StagedAuthorityStageV1:
    """Verify one pointer mode for an already-authenticated staged closure."""

    if type(staged) is not StagedAuthorityStageV1:
        raise PipelineError("authority-stage pointer selection is not staged")
    if expected_pointer not in {None, "predecessor", "successor"}:
        raise PipelineError("authority-stage expected pointer mode is invalid")
    if expected_pointer is None:
        return staged
    if not callable(getattr(reader, "read_pointer", None)):
        raise PipelineError("authority-stage pointer reader is invalid")
    pointer = (
        staged.predecessor_pointer
        if expected_pointer == "predecessor"
        else staged.successor_pointer
    )
    raw = (
        staged.predecessor_raw
        if expected_pointer == "predecessor"
        else staged.successor_raw
    )
    _assert_pointer(reader, pointer, raw)
    return staged


def verify_staged_authority_plan(
    store: CampaignStore,
    staged_receipt_ref: EvidenceRef,
    *,
    require_live_engine: bool = True,
    expected_pointer: str | None = "predecessor",
    reader: AuthorityStageReader | None = None,
    historical_root_loader: HistoricalRootLoader | None = None,
) -> StagedAuthorityStageV1:
    """Verify a staged envelope and, when requested, its selected pointer."""

    result = load_staged_authority_plan(
        store,
        staged_receipt_ref,
        require_live_engine=require_live_engine,
        reader=reader,
        historical_root_loader=historical_root_loader,
    )
    return verify_staged_authority_pointer(
        result,
        expected_pointer=expected_pointer,
        reader=store if reader is None else reader,
    )


__all__ = [
    "FORMAT",
    "PROCESS_TIER",
    "PUBLICATION",
    "REQUIRED_CHECKS",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "AuthorityStageReader",
    "AuthorityCopyPayloadV1",
    "AuthorityCopyV1",
    "AuthorityStagePlanV1",
    "DirectoryReplayV1",
    "EvidenceReplayV1",
    "HistoricalRootLoader",
    "LegacyMatrixStageV1",
    "LoadedHistoricalTransition",
    "MatrixCellReplayV1",
    "MatrixCoreDeltaV1",
    "MatrixRefreshReplayV1",
    "PlannedAuthorityStageV1",
    "SourceSnapshotReplayV1",
    "StagedAuthorityStageV1",
    "authoritative_suite_summary",
    "decode_authority_stage_plan",
    "decode_matrix_refresh_replay",
    "load_staged_authority_plan",
    "plan_repository_authority_stage",
    "replay_matrix_refresh",
    "render_authority_stage_plan",
    "render_matrix_refresh_replay",
    "stage_authority_plan",
    "validate_planned_authority_stage",
    "verify_staged_authority_pointer",
    "verify_staged_authority_plan",
    "validate_h5_h6_authority_bindings",
]
