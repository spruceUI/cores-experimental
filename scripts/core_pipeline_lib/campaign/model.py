"""Immutable wire models for consolidated campaign transitions.

These records contain normalized facts only.  They perform no filesystem,
process, repository, lock, or transaction work.  Every persisted shape is
closed, local-only, publication-disabled, and self-authenticated with the new
strict campaign JSON codec.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from pathlib import PurePosixPath
import re
from typing import ClassVar

from ..errors import PipelineError
from .json_wire import (
    canonical_json_sha256,
    validate_json_pointer,
    validate_utf8_string,
)


SCHEMA_VERSION = 1
PUBLICATION = "disabled"
TRANSITION_KIND = "matrix-authority-refresh-v1"

IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_SECONDS_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")

EVIDENCE_KINDS = frozenset(
    {
        "audit-checkpoint",
        "artifact",
        "check-log",
        "engine-bundle",
        "matrix-cas",
        "matrix-cell",
        "matrix-pointer",
        "matrix-root",
        "matrix-shard",
        "matrix-snapshot",
        "phase-freeze",
        "phase-freeze-cas",
        "pin-directory",
        "pipeline-bundle",
        "repository-snapshot",
        "state-root",
        "track-registry",
        "track-snapshot-directory",
        "transition-plan",
        "transition-spec",
        "validation-receipt",
    }
)

MATRIX_AUTHORITY_ALLOWED_CHANGES = (
    "/captured_at",
    "/content_sha256",
    "/inputs/generator",
    "/inputs/phase_freeze",
    "/inputs/pipeline_bundle",
    "/supersedes",
    "/validation_ledger",
)

MATRIX_AUTHORITY_REQUIRED_CHECKS = (
    "campaign.plan.identity",
    "matrix.authority.delta",
    "matrix.predecessor.immutable",
    "matrix.schema",
    "matrix.successor.identity",
    "publication.disabled",
)

VALIDATION_STAGES = frozenset(
    {"check", "staged", "pre-commit", "post-commit", "historical"}
)
CHECK_STATUSES = frozenset({"passed", "failed"})


def _require_identifier(value: object, label: str) -> str:
    if type(value) is not str or not IDENTIFIER_RE.fullmatch(value):
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _require_timestamp(value: object, label: str) -> str:
    if type(value) is not str or not UTC_SECONDS_RE.fullmatch(value):
        raise PipelineError(f"{label} must be an exact UTC-second timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise PipelineError(f"{label} must be a real UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise PipelineError(f"{label} is not canonical")
    return value


def _require_relative_path(value: object, label: str) -> str:
    value = validate_utf8_string(value, label=label)
    if not value or "\x00" in value or "\\" in value or "//" in value:
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return value


def _require_reason(value: object, label: str = "reason") -> str:
    value = validate_utf8_string(value, label=label)
    if not value or value != value.strip():
        raise PipelineError(f"{label} must be a nonempty stripped string")
    return value


def _require_exact_document(
    value: object,
    expected_keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict:
        raise PipelineError(f"{label} must be an exact JSON object")
    if any(type(key) is not str for key in value):
        raise PipelineError(f"{label} must contain exact string keys")
    actual = frozenset(value)
    if actual != expected_keys:
        missing = sorted(expected_keys - actual)
        extra = sorted(actual - expected_keys)
        raise PipelineError(
            f"{label} fields are not exact: missing={missing}; extra={extra}"
        )
    if value.get("schema_version") != SCHEMA_VERSION or type(
        value.get("schema_version")
    ) is not int:
        raise PipelineError(f"{label} schema_version is invalid")
    return value


def _require_fixed_envelope(document: dict[str, object], label: str) -> None:
    if document.get("local_only") is not True:
        raise PipelineError(f"{label} must be local-only")
    if (
        type(document.get("publication")) is not str
        or document.get("publication") != PUBLICATION
    ):
        raise PipelineError(f"{label} publication must be disabled")


def _with_content_sha256(material: dict[str, object]) -> dict[str, object]:
    document = dict(material)
    document["content_sha256"] = canonical_json_sha256(material)
    return document


def _require_content_sha256(
    document: dict[str, object],
    material: dict[str, object],
    label: str,
) -> None:
    expected = canonical_json_sha256(material)
    _require_sha256(document.get("content_sha256"), f"{label} content_sha256")
    if document.get("content_sha256") != expected:
        raise PipelineError(f"{label} content_sha256 is invalid")


def _require_sorted_unique_strings(
    values: object,
    *,
    label: str,
    pointers: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PipelineError(f"{label} must be a tuple")
    if any(type(item) is not str or not item for item in values):
        raise PipelineError(f"{label} must contain nonempty strings")
    if tuple(sorted(values)) != values or len(values) != len(set(values)):
        raise PipelineError(f"{label} must be sorted and unique")
    if pointers:
        for item in values:
            validate_json_pointer(item)
    else:
        for item in values:
            _require_identifier(item, f"{label} item")
    return values


def _documents_to_tuple(value: object, label: str) -> tuple[object, ...]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact JSON array")
    return tuple(value)


def _require_ref_order(values: tuple["EvidenceRef", ...], label: str) -> None:
    keys = tuple((item.kind, item.path) for item in values)
    if tuple(sorted(keys)) != keys or len(keys) != len(set(keys)):
        raise PipelineError(f"{label} must be sorted and unique by kind/path")


def _require_semantic_ref(
    value: object,
    *,
    kind: str,
    label: str,
) -> "EvidenceRef":
    if type(value) is not EvidenceRef or value.kind != kind:
        raise PipelineError(f"{label} kind is invalid")
    if value.target_content_sha256 is None:
        raise PipelineError(f"{label} must bind a semantic identity")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceRef:
    """Self-authenticating reference to one immutable evidence object."""

    kind: str
    path: str
    file_sha256: str
    target_content_sha256: str | None
    size: int

    schema_version: ClassVar[int] = SCHEMA_VERSION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "kind",
            "path",
            "file_sha256",
            "target_content_sha256",
            "size",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.kind, "evidence kind")
        if self.kind not in EVIDENCE_KINDS:
            raise PipelineError("evidence kind is not registered")
        _require_relative_path(self.path, "evidence path")
        _require_sha256(self.file_sha256, "evidence file_sha256")
        if self.target_content_sha256 is not None:
            _require_sha256(
                self.target_content_sha256,
                "evidence target_content_sha256",
            )
        if type(self.size) is not int or self.size < 0:
            raise PipelineError("evidence size must be a nonnegative integer")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": self.kind,
            "path": self.path,
            "file_sha256": self.file_sha256,
            "target_content_sha256": self.target_content_sha256,
            "size": self.size,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "EvidenceRef":
        document = _require_exact_document(value, cls._KEYS, "evidence reference")
        result = cls(
            kind=document.get("kind"),  # type: ignore[arg-type]
            path=document.get("path"),  # type: ignore[arg-type]
            file_sha256=document.get("file_sha256"),  # type: ignore[arg-type]
            target_content_sha256=document.get("target_content_sha256"),  # type: ignore[arg-type]
            size=document.get("size"),  # type: ignore[arg-type]
        )
        _require_content_sha256(document, result._material(), "evidence reference")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionSpec:
    """Small human-authorized intent for one code-owned transition policy."""

    transition_id: str
    campaign_id: str
    kind: str
    captured_at: str
    reason: str
    predecessor: EvidenceRef
    phase_freeze: EvidenceRef

    schema_version: ClassVar[int] = SCHEMA_VERSION
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "transition_id",
            "campaign_id",
            "kind",
            "captured_at",
            "reason",
            "predecessor",
            "phase_freeze",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.transition_id, "transition_id")
        _require_identifier(self.campaign_id, "campaign_id")
        if type(self.kind) is not str or self.kind != TRANSITION_KIND:
            raise PipelineError("transition kind is not supported")
        _require_timestamp(self.captured_at, "captured_at")
        _require_reason(self.reason)
        _require_semantic_ref(
            self.predecessor,
            kind="matrix-pointer",
            label="transition predecessor",
        )
        _require_semantic_ref(
            self.phase_freeze,
            kind="phase-freeze",
            label="transition phase_freeze",
        )

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "transition_id": self.transition_id,
            "campaign_id": self.campaign_id,
            "kind": self.kind,
            "captured_at": self.captured_at,
            "reason": self.reason,
            "predecessor": self.predecessor.to_document(),
            "phase_freeze": self.phase_freeze.to_document(),
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "TransitionSpec":
        document = _require_exact_document(value, cls._KEYS, "transition spec")
        _require_fixed_envelope(document, "transition spec")
        result = cls(
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            kind=document.get("kind"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            reason=document.get("reason"),  # type: ignore[arg-type]
            predecessor=EvidenceRef.from_document(document.get("predecessor")),
            phase_freeze=EvidenceRef.from_document(document.get("phase_freeze")),
        )
        _require_content_sha256(document, result._material(), "transition spec")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionPlan:
    """Resolved deterministic plan for the first authority-only policy."""

    transition_id: str
    campaign_id: str
    kind: str
    captured_at: str
    reason: str
    spec: EvidenceRef
    engine_bundle: EvidenceRef
    predecessor: EvidenceRef
    phase_freeze: EvidenceRef
    pipeline_bundle: EvidenceRef
    successor: EvidenceRef
    allowed_changes: tuple[str, ...]
    preserved_projection_sha256: str
    required_checks: tuple[str, ...]

    schema_version: ClassVar[int] = SCHEMA_VERSION
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "transition_id",
            "campaign_id",
            "kind",
            "captured_at",
            "reason",
            "spec",
            "engine_bundle",
            "predecessor",
            "phase_freeze",
            "pipeline_bundle",
            "successor",
            "allowed_changes",
            "preserved_projection_sha256",
            "required_checks",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.transition_id, "transition_id")
        _require_identifier(self.campaign_id, "campaign_id")
        if type(self.kind) is not str or self.kind != TRANSITION_KIND:
            raise PipelineError("transition plan kind is not supported")
        _require_timestamp(self.captured_at, "captured_at")
        _require_reason(self.reason)
        expected_kinds = {
            "spec": (self.spec, "transition-spec"),
            "engine_bundle": (self.engine_bundle, "engine-bundle"),
            "predecessor": (self.predecessor, "matrix-pointer"),
            "phase_freeze": (self.phase_freeze, "phase-freeze"),
            "pipeline_bundle": (self.pipeline_bundle, "pipeline-bundle"),
            "successor": (self.successor, "matrix-snapshot"),
        }
        for label, (reference, expected_kind) in expected_kinds.items():
            _require_semantic_ref(
                reference,
                kind=expected_kind,
                label=f"transition plan {label}",
            )
        _require_sorted_unique_strings(
            self.allowed_changes,
            label="transition plan allowed_changes",
            pointers=True,
        )
        if self.allowed_changes != MATRIX_AUTHORITY_ALLOWED_CHANGES:
            raise PipelineError("transition plan allowed_changes differ from policy")
        _require_sha256(
            self.preserved_projection_sha256,
            "transition plan preserved_projection_sha256",
        )
        _require_sorted_unique_strings(
            self.required_checks,
            label="transition plan required_checks",
        )
        if self.required_checks != MATRIX_AUTHORITY_REQUIRED_CHECKS:
            raise PipelineError("transition plan required_checks differ from policy")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "transition_id": self.transition_id,
            "campaign_id": self.campaign_id,
            "kind": self.kind,
            "captured_at": self.captured_at,
            "reason": self.reason,
            "spec": self.spec.to_document(),
            "engine_bundle": self.engine_bundle.to_document(),
            "predecessor": self.predecessor.to_document(),
            "phase_freeze": self.phase_freeze.to_document(),
            "pipeline_bundle": self.pipeline_bundle.to_document(),
            "successor": self.successor.to_document(),
            "allowed_changes": list(self.allowed_changes),
            "preserved_projection_sha256": self.preserved_projection_sha256,
            "required_checks": list(self.required_checks),
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "TransitionPlan":
        document = _require_exact_document(value, cls._KEYS, "transition plan")
        _require_fixed_envelope(document, "transition plan")
        result = cls(
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            kind=document.get("kind"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            reason=document.get("reason"),  # type: ignore[arg-type]
            spec=EvidenceRef.from_document(document.get("spec")),
            engine_bundle=EvidenceRef.from_document(document.get("engine_bundle")),
            predecessor=EvidenceRef.from_document(document.get("predecessor")),
            phase_freeze=EvidenceRef.from_document(document.get("phase_freeze")),
            pipeline_bundle=EvidenceRef.from_document(document.get("pipeline_bundle")),
            successor=EvidenceRef.from_document(document.get("successor")),
            allowed_changes=_documents_to_tuple(
                document.get("allowed_changes"), "transition plan allowed_changes"
            ),  # type: ignore[arg-type]
            preserved_projection_sha256=document.get(
                "preserved_projection_sha256"
            ),  # type: ignore[arg-type]
            required_checks=_documents_to_tuple(
                document.get("required_checks"), "transition plan required_checks"
            ),  # type: ignore[arg-type]
        )
        _require_content_sha256(document, result._material(), "transition plan")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckResult:
    """One stable, explicit validation result bound to immutable evidence."""

    check_id: str
    subject_sha256: str
    status: str
    evidence: tuple[EvidenceRef, ...] = ()
    message: str | None = None

    schema_version: ClassVar[int] = SCHEMA_VERSION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "check_id",
            "subject_sha256",
            "status",
            "evidence",
            "message",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.check_id, "check_id")
        _require_sha256(self.subject_sha256, "check subject_sha256")
        if type(self.status) is not str or self.status not in CHECK_STATUSES:
            raise PipelineError("check status must be passed or failed")
        if type(self.evidence) is not tuple or any(
            type(item) is not EvidenceRef for item in self.evidence
        ):
            raise PipelineError("check evidence must be a tuple of EvidenceRef")
        _require_ref_order(self.evidence, "check evidence")
        if self.message is not None:
            _require_reason(self.message, "check message")
        if self.status == "failed" and self.message is None:
            raise PipelineError("failed check must include a message")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "check_id": self.check_id,
            "subject_sha256": self.subject_sha256,
            "status": self.status,
            "evidence": [item.to_document() for item in self.evidence],
            "message": self.message,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "CheckResult":
        document = _require_exact_document(value, cls._KEYS, "check result")
        evidence_documents = _documents_to_tuple(
            document.get("evidence"), "check evidence"
        )
        result = cls(
            check_id=document.get("check_id"),  # type: ignore[arg-type]
            subject_sha256=document.get("subject_sha256"),  # type: ignore[arg-type]
            status=document.get("status"),  # type: ignore[arg-type]
            evidence=tuple(EvidenceRef.from_document(item) for item in evidence_documents),
            message=document.get("message"),  # type: ignore[arg-type]
        )
        _require_content_sha256(document, result._material(), "check result")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class Receipt:
    """Stage-aware validation or transaction receipt for one exact plan."""

    transition_id: str
    plan: EvidenceRef
    stage: str
    status: str
    started_at: str
    completed_at: str
    checks: tuple[CheckResult, ...]
    outputs: tuple[EvidenceRef, ...] = ()

    schema_version: ClassVar[int] = SCHEMA_VERSION
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "transition_id",
            "plan",
            "stage",
            "status",
            "started_at",
            "completed_at",
            "checks",
            "outputs",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.transition_id, "receipt transition_id")
        _require_semantic_ref(
            self.plan,
            kind="transition-plan",
            label="receipt plan",
        )
        if type(self.stage) is not str or self.stage not in VALIDATION_STAGES:
            raise PipelineError("receipt stage is invalid")
        if type(self.status) is not str or self.status not in CHECK_STATUSES:
            raise PipelineError("receipt status must be passed or failed")
        started = _require_timestamp(self.started_at, "receipt started_at")
        completed = _require_timestamp(self.completed_at, "receipt completed_at")
        if completed < started:
            raise PipelineError("receipt completed_at precedes started_at")
        if type(self.checks) is not tuple or not self.checks or any(
            type(item) is not CheckResult for item in self.checks
        ):
            raise PipelineError("receipt checks must be a nonempty tuple")
        check_ids = tuple(item.check_id for item in self.checks)
        if tuple(sorted(check_ids)) != check_ids or len(check_ids) != len(set(check_ids)):
            raise PipelineError("receipt checks must be sorted and unique")
        any_failed = any(item.status == "failed" for item in self.checks)
        if (self.status == "passed" and any_failed) or (
            self.status == "failed" and not any_failed
        ):
            raise PipelineError("receipt status is inconsistent with checks")
        if type(self.outputs) is not tuple or any(
            type(item) is not EvidenceRef for item in self.outputs
        ):
            raise PipelineError("receipt outputs must be a tuple of EvidenceRef")
        _require_ref_order(self.outputs, "receipt outputs")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "transition_id": self.transition_id,
            "plan": self.plan.to_document(),
            "stage": self.stage,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "checks": [item.to_document() for item in self.checks],
            "outputs": [item.to_document() for item in self.outputs],
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "Receipt":
        document = _require_exact_document(value, cls._KEYS, "receipt")
        _require_fixed_envelope(document, "receipt")
        check_documents = _documents_to_tuple(document.get("checks"), "receipt checks")
        output_documents = _documents_to_tuple(
            document.get("outputs"), "receipt outputs"
        )
        result = cls(
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            plan=EvidenceRef.from_document(document.get("plan")),
            stage=document.get("stage"),  # type: ignore[arg-type]
            status=document.get("status"),  # type: ignore[arg-type]
            started_at=document.get("started_at"),  # type: ignore[arg-type]
            completed_at=document.get("completed_at"),  # type: ignore[arg-type]
            checks=tuple(CheckResult.from_document(item) for item in check_documents),
            outputs=tuple(EvidenceRef.from_document(item) for item in output_documents),
        )
        _require_content_sha256(document, result._material(), "receipt")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class StateRoot:
    """Immutable campaign state root selected by a small external pointer."""

    campaign_id: str
    generation: int
    transition_id: str
    plan: EvidenceRef
    receipt: EvidenceRef
    current: EvidenceRef
    previous: EvidenceRef | None = None

    schema_version: ClassVar[int] = SCHEMA_VERSION
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "campaign_id",
            "generation",
            "transition_id",
            "plan",
            "receipt",
            "current",
            "previous",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.campaign_id, "state root campaign_id")
        _require_identifier(self.transition_id, "state root transition_id")
        if type(self.generation) is not int or self.generation < 1:
            raise PipelineError("state root generation must be a positive integer")
        expected_kinds = {
            "plan": (self.plan, "transition-plan"),
            "receipt": (self.receipt, "validation-receipt"),
        }
        for label, (reference, expected_kind) in expected_kinds.items():
            _require_semantic_ref(
                reference,
                kind=expected_kind,
                label=f"state root {label}",
            )
        _require_semantic_ref(
            self.current,
            kind="matrix-snapshot",
            label="state root current",
        )
        if self.generation == 1 and self.previous is not None:
            raise PipelineError("first state root must not have a predecessor")
        if self.generation > 1:
            _require_semantic_ref(
                self.previous,
                kind="state-root",
                label="later state root predecessor",
            )

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": self.campaign_id,
            "generation": self.generation,
            "transition_id": self.transition_id,
            "plan": self.plan.to_document(),
            "receipt": self.receipt.to_document(),
            "current": self.current.to_document(),
            "previous": self.previous.to_document() if self.previous is not None else None,
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "StateRoot":
        document = _require_exact_document(value, cls._KEYS, "state root")
        _require_fixed_envelope(document, "state root")
        previous_document = document.get("previous")
        result = cls(
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            generation=document.get("generation"),  # type: ignore[arg-type]
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            plan=EvidenceRef.from_document(document.get("plan")),
            receipt=EvidenceRef.from_document(document.get("receipt")),
            current=EvidenceRef.from_document(document.get("current")),
            previous=(
                EvidenceRef.from_document(previous_document)
                if previous_document is not None
                else None
            ),
        )
        _require_content_sha256(document, result._material(), "state root")
        return result


__all__ = [
    "CHECK_STATUSES",
    "EVIDENCE_KINDS",
    "MATRIX_AUTHORITY_ALLOWED_CHANGES",
    "MATRIX_AUTHORITY_REQUIRED_CHECKS",
    "PUBLICATION",
    "SCHEMA_VERSION",
    "TRANSITION_KIND",
    "VALIDATION_STAGES",
    "CheckResult",
    "EvidenceRef",
    "Receipt",
    "StateRoot",
    "TransitionPlan",
    "TransitionSpec",
]
