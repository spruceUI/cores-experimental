"""Strict generic records for registered campaign transitions.

These records are deliberately separate from the H3 matrix-transition model.
They describe generic transition intent and resolved plans without changing the
legacy ``TransitionSpec``, ``TransitionPlan``, or ``StateRoot`` contracts.
They perform no filesystem, process, import-discovery, clock, or transaction
work.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import re
from typing import ClassVar

from ..errors import PipelineError
from ..foundation import sha256_bytes
from .json_wire import (
    canonical_json_sha256,
    decode_identity_object,
    validate_json_pointer,
    validate_utf8_string,
)
from .model import EvidenceRef


SCHEMA_VERSION = 1
INTENT_FORMAT = "spruce-campaign-transition-intent-v1"
PLAN_FORMAT = "spruce-campaign-transition-plan-v1"
PUBLICATION = "disabled"

IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UTC_SECONDS_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
PROCESS_TIERS = frozenset({"quick", "static", "evidence", "rebuild"})


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


def _require_reason(value: object) -> str:
    value = validate_utf8_string(value, label="transition reason")
    if not value or value != value.strip() or "\x00" in value:
        raise PipelineError("transition reason must be a nonempty stripped string")
    return value


def _require_evidence_ref(value: object, label: str) -> EvidenceRef:
    if type(value) is not EvidenceRef:
        raise PipelineError(f"{label} must be an exact EvidenceRef")
    return value


def _require_semantic_ref(
    value: object,
    *,
    label: str,
    kind: str | None = None,
) -> EvidenceRef:
    reference = _require_evidence_ref(value, label)
    if kind is not None and reference.kind != kind:
        raise PipelineError(f"{label} kind is invalid")
    if reference.target_content_sha256 is None:
        raise PipelineError(f"{label} must bind a semantic identity")
    return reference


def _require_exact_document(
    value: object,
    expected_keys: frozenset[str],
    label: str,
    *,
    schema_version: bool,
) -> dict[str, object]:
    document = decode_identity_object(value, label=label)
    actual = frozenset(document)
    if actual != expected_keys:
        raise PipelineError(
            f"{label} fields are not exact: "
            f"missing={sorted(expected_keys - actual)}; "
            f"extra={sorted(actual - expected_keys)}"
        )
    if schema_version and (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        raise PipelineError(f"{label} schema_version is invalid")
    return document


def _require_fixed_envelope(
    document: dict[str, object],
    *,
    label: str,
    expected_format: str,
) -> None:
    if type(document.get("format")) is not str or document.get(
        "format"
    ) != expected_format:
        raise PipelineError(f"{label} format is invalid")
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
    _require_sha256(document.get("content_sha256"), f"{label} content_sha256")
    if document.get("content_sha256") != canonical_json_sha256(material):
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
        raise PipelineError(f"{label} must contain nonempty exact strings")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise PipelineError(f"{label} must be sorted and unique")
    for item in values:
        if pointers:
            validate_json_pointer(item)
        else:
            _require_identifier(item, f"{label} item")
    return values


def _require_unique_identifiers(
    values: object,
    *,
    label: str,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PipelineError(f"{label} must be a tuple")
    if not values or any(type(item) is not str or not item for item in values):
        raise PipelineError(f"{label} must contain nonempty exact strings")
    if len(values) != len(set(values)):
        raise PipelineError(f"{label} must be nonempty and unique")
    for item in values:
        _require_identifier(item, f"{label} item")
    return values


def _documents_to_tuple(value: object, label: str) -> tuple[object, ...]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact JSON array")
    return tuple(value)


def _require_named_inputs(
    values: object,
    *,
    item_type: type,
    label: str,
) -> tuple[object, ...]:
    if type(values) is not tuple or any(
        type(item) is not item_type for item in values
    ):
        raise PipelineError(
            f"{label} must be a tuple of exact {item_type.__name__} values"
        )
    if not values:
        raise PipelineError(f"{label} must be nonempty")
    names = tuple(item.name for item in values)
    if names != tuple(sorted(names)) or len(names) != len(set(names)):
        raise PipelineError(f"{label} must be sorted and unique by name")
    return values


def _require_raw_matches_reference(
    raw: object,
    reference: EvidenceRef,
    *,
    label: str,
) -> bytes:
    if type(raw) is not bytes:
        raise PipelineError(f"{label} must be exact bytes")
    if len(raw) != reference.size:
        raise PipelineError(f"{label} size differs from its reference")
    if sha256_bytes(raw) != reference.file_sha256:
        raise PipelineError(f"{label} SHA-256 differs from its reference")
    return raw


@dataclass(frozen=True, slots=True, kw_only=True)
class NamedEvidenceRef:
    """One immutable evidence reference bound to a stable transition role."""

    name: str
    reference: EvidenceRef

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"name", "reference", "content_sha256"}
    )

    def __post_init__(self) -> None:
        _require_identifier(self.name, "named evidence name")
        _require_evidence_ref(self.reference, "named evidence reference")

    def _material(self) -> dict[str, object]:
        return {"name": self.name, "reference": self.reference.to_document()}

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "NamedEvidenceRef":
        document = _require_exact_document(
            value,
            cls._KEYS,
            "named evidence reference",
            schema_version=False,
        )
        result = cls(
            name=document.get("name"),  # type: ignore[arg-type]
            reference=EvidenceRef.from_document(document.get("reference")),
        )
        _require_content_sha256(
            document,
            result._material(),
            "named evidence reference",
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionIntentV1:
    """Human-authorized generic intent resolved by one registered policy."""

    transition_id: str
    campaign_id: str
    kind: str
    captured_at: str
    reason: str
    predecessor: EvidenceRef
    inputs: tuple[NamedEvidenceRef, ...]
    changed_authorities: tuple[str, ...]

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = INTENT_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "transition_id",
            "campaign_id",
            "kind",
            "captured_at",
            "reason",
            "predecessor",
            "inputs",
            "changed_authorities",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.transition_id, "transition intent transition_id")
        _require_identifier(self.campaign_id, "transition intent campaign_id")
        _require_identifier(self.kind, "transition intent kind")
        _require_timestamp(self.captured_at, "transition intent captured_at")
        _require_reason(self.reason)
        _require_semantic_ref(
            self.predecessor,
            label="transition intent predecessor",
        )
        _require_named_inputs(
            self.inputs,
            item_type=NamedEvidenceRef,
            label="transition intent inputs",
        )
        _require_sorted_unique_strings(
            self.changed_authorities,
            label="transition intent changed_authorities",
        )
        input_names = frozenset(item.name for item in self.inputs)
        unexpected = sorted(set(self.changed_authorities) - input_names)
        if unexpected:
            raise PipelineError(
                "transition intent changed_authorities are not inputs: "
                f"{unexpected}"
            )

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": INTENT_FORMAT,
            "transition_id": self.transition_id,
            "campaign_id": self.campaign_id,
            "kind": self.kind,
            "captured_at": self.captured_at,
            "reason": self.reason,
            "predecessor": self.predecessor.to_document(),
            "inputs": [item.to_document() for item in self.inputs],
            "changed_authorities": list(self.changed_authorities),
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "TransitionIntentV1":
        document = _require_exact_document(
            value,
            cls._KEYS,
            "transition intent",
            schema_version=True,
        )
        _require_fixed_envelope(
            document,
            label="transition intent",
            expected_format=INTENT_FORMAT,
        )
        inputs = _documents_to_tuple(document.get("inputs"), "transition intent inputs")
        changed = _documents_to_tuple(
            document.get("changed_authorities"),
            "transition intent changed_authorities",
        )
        result = cls(
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            kind=document.get("kind"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            reason=document.get("reason"),  # type: ignore[arg-type]
            predecessor=EvidenceRef.from_document(document.get("predecessor")),
            inputs=tuple(NamedEvidenceRef.from_document(item) for item in inputs),
            changed_authorities=changed,  # type: ignore[arg-type]
        )
        _require_content_sha256(document, result._material(), "transition intent")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionDeltaV1:
    """Exact pointer delta and preserved projection for one resolved plan."""

    allowed_changes: tuple[str, ...]
    required_changes: tuple[str, ...]
    changed_pointers: tuple[str, ...]
    preserved_projection_sha256: str

    schema_version: ClassVar[int] = SCHEMA_VERSION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "allowed_changes",
            "required_changes",
            "changed_pointers",
            "preserved_projection_sha256",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_sorted_unique_strings(
            self.allowed_changes,
            label="transition delta allowed_changes",
            pointers=True,
        )
        _require_sorted_unique_strings(
            self.required_changes,
            label="transition delta required_changes",
            pointers=True,
        )
        _require_sorted_unique_strings(
            self.changed_pointers,
            label="transition delta changed_pointers",
            pointers=True,
        )
        allowed = frozenset(self.allowed_changes)
        required = frozenset(self.required_changes)
        changed = frozenset(self.changed_pointers)
        if not required <= allowed:
            raise PipelineError(
                "transition delta required_changes must be allowed"
            )
        if not required <= changed or not changed <= allowed:
            raise PipelineError(
                "transition delta changed_pointers violate the exact policy"
            )
        _require_sha256(
            self.preserved_projection_sha256,
            "transition delta preserved_projection_sha256",
        )

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "allowed_changes": list(self.allowed_changes),
            "required_changes": list(self.required_changes),
            "changed_pointers": list(self.changed_pointers),
            "preserved_projection_sha256": self.preserved_projection_sha256,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "TransitionDeltaV1":
        document = _require_exact_document(
            value,
            cls._KEYS,
            "transition delta",
            schema_version=True,
        )
        result = cls(
            allowed_changes=_documents_to_tuple(
                document.get("allowed_changes"),
                "transition delta allowed_changes",
            ),  # type: ignore[arg-type]
            required_changes=_documents_to_tuple(
                document.get("required_changes"),
                "transition delta required_changes",
            ),  # type: ignore[arg-type]
            changed_pointers=_documents_to_tuple(
                document.get("changed_pointers"),
                "transition delta changed_pointers",
            ),  # type: ignore[arg-type]
            preserved_projection_sha256=document.get(
                "preserved_projection_sha256"
            ),  # type: ignore[arg-type]
        )
        _require_content_sha256(document, result._material(), "transition delta")
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class ResolvedTransitionPlanV1:
    """Fully resolved, deterministic plan for one registered transition."""

    transition_id: str
    campaign_id: str
    kind: str
    handler_id: str
    captured_at: str
    reason: str
    intent: EvidenceRef
    engine_bundle: EvidenceRef
    predecessor: EvidenceRef
    inputs: tuple[NamedEvidenceRef, ...]
    successor: EvidenceRef
    delta: TransitionDeltaV1
    required_checks: tuple[str, ...]
    process_tier: str

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = PLAN_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "transition_id",
            "campaign_id",
            "kind",
            "handler_id",
            "captured_at",
            "reason",
            "intent",
            "engine_bundle",
            "predecessor",
            "inputs",
            "successor",
            "delta",
            "required_checks",
            "process_tier",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.transition_id, "resolved plan transition_id")
        _require_identifier(self.campaign_id, "resolved plan campaign_id")
        _require_identifier(self.kind, "resolved plan kind")
        _require_identifier(self.handler_id, "resolved plan handler_id")
        _require_timestamp(self.captured_at, "resolved plan captured_at")
        _require_reason(self.reason)
        _require_semantic_ref(
            self.intent,
            kind="transition-spec",
            label="resolved plan intent",
        )
        _require_semantic_ref(
            self.engine_bundle,
            kind="engine-bundle",
            label="resolved plan engine_bundle",
        )
        _require_semantic_ref(
            self.predecessor,
            label="resolved plan predecessor",
        )
        _require_named_inputs(
            self.inputs,
            item_type=NamedEvidenceRef,
            label="resolved plan inputs",
        )
        _require_semantic_ref(self.successor, label="resolved plan successor")
        if type(self.delta) is not TransitionDeltaV1:
            raise PipelineError(
                "resolved plan delta must be an exact TransitionDeltaV1"
            )
        _require_unique_identifiers(
            self.required_checks,
            label="resolved plan required_checks",
        )
        if type(self.process_tier) is not str or self.process_tier not in PROCESS_TIERS:
            raise PipelineError("resolved plan process_tier is invalid")

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": PLAN_FORMAT,
            "transition_id": self.transition_id,
            "campaign_id": self.campaign_id,
            "kind": self.kind,
            "handler_id": self.handler_id,
            "captured_at": self.captured_at,
            "reason": self.reason,
            "intent": self.intent.to_document(),
            "engine_bundle": self.engine_bundle.to_document(),
            "predecessor": self.predecessor.to_document(),
            "inputs": [item.to_document() for item in self.inputs],
            "successor": self.successor.to_document(),
            "delta": self.delta.to_document(),
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
    def from_document(cls, value: object) -> "ResolvedTransitionPlanV1":
        document = _require_exact_document(
            value,
            cls._KEYS,
            "resolved transition plan",
            schema_version=True,
        )
        _require_fixed_envelope(
            document,
            label="resolved transition plan",
            expected_format=PLAN_FORMAT,
        )
        inputs = _documents_to_tuple(document.get("inputs"), "resolved plan inputs")
        checks = _documents_to_tuple(
            document.get("required_checks"),
            "resolved plan required_checks",
        )
        result = cls(
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            kind=document.get("kind"),  # type: ignore[arg-type]
            handler_id=document.get("handler_id"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            reason=document.get("reason"),  # type: ignore[arg-type]
            intent=EvidenceRef.from_document(document.get("intent")),
            engine_bundle=EvidenceRef.from_document(document.get("engine_bundle")),
            predecessor=EvidenceRef.from_document(document.get("predecessor")),
            inputs=tuple(NamedEvidenceRef.from_document(item) for item in inputs),
            successor=EvidenceRef.from_document(document.get("successor")),
            delta=TransitionDeltaV1.from_document(document.get("delta")),
            required_checks=checks,  # type: ignore[arg-type]
            process_tier=document.get("process_tier"),  # type: ignore[arg-type]
        )
        _require_content_sha256(
            document,
            result._material(),
            "resolved transition plan",
        )
        return result


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthenticatedInput:
    """Runtime-only bytes authenticated by one named immutable reference."""

    name: str
    reference: EvidenceRef
    raw: bytes

    def __post_init__(self) -> None:
        _require_identifier(self.name, "authenticated input name")
        reference = _require_evidence_ref(
            self.reference,
            "authenticated input reference",
        )
        _require_raw_matches_reference(
            self.raw,
            reference,
            label=f"authenticated input {self.name}",
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionRequest:
    """Runtime-only authenticated inputs supplied to a code-owned handler."""

    spec_ref: EvidenceRef
    spec_raw: bytes
    engine_bundle_ref: EvidenceRef
    engine_bundle_raw: bytes
    predecessor_raw: bytes
    inputs: tuple[AuthenticatedInput, ...]

    def __post_init__(self) -> None:
        spec_ref = _require_semantic_ref(
            self.spec_ref,
            kind="transition-spec",
            label="transition request spec_ref",
        )
        engine_ref = _require_semantic_ref(
            self.engine_bundle_ref,
            kind="engine-bundle",
            label="transition request engine_bundle_ref",
        )
        _require_raw_matches_reference(
            self.spec_raw,
            spec_ref,
            label="transition request spec_raw",
        )
        _require_raw_matches_reference(
            self.engine_bundle_raw,
            engine_ref,
            label="transition request engine_bundle_raw",
        )
        intent = TransitionIntentV1.from_document(self.spec_raw)
        if spec_ref.target_content_sha256 != intent.content_sha256:
            raise PipelineError("transition request spec semantic identity is invalid")
        _require_raw_matches_reference(
            self.predecessor_raw,
            intent.predecessor,
            label="transition request predecessor_raw",
        )
        inputs = _require_named_inputs(
            self.inputs,
            item_type=AuthenticatedInput,
            label="transition request inputs",
        )
        actual = tuple((item.name, item.reference) for item in inputs)
        expected = tuple((item.name, item.reference) for item in intent.inputs)
        if actual != expected:
            raise PipelineError("transition request inputs differ from the intent")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedTransition:
    """One generic resolved plan paired with its exact candidate bytes."""

    plan: ResolvedTransitionPlanV1
    candidate_raw: bytes

    def __post_init__(self) -> None:
        if type(self.plan) is not ResolvedTransitionPlanV1:
            raise PipelineError("planned transition plan is invalid")
        _require_raw_matches_reference(
            self.candidate_raw,
            self.plan.successor,
            label="planned transition candidate_raw",
        )


__all__ = [
    "INTENT_FORMAT",
    "PLAN_FORMAT",
    "PROCESS_TIERS",
    "PUBLICATION",
    "SCHEMA_VERSION",
    "AuthenticatedInput",
    "NamedEvidenceRef",
    "PlannedTransition",
    "ResolvedTransitionPlanV1",
    "TransitionDeltaV1",
    "TransitionIntentV1",
    "TransitionRequest",
]
