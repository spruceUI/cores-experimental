"""Pure cross-document validation for campaign transition records.

The H1 wire models close and authenticate each document independently.  This
module closes the references between those documents without reading a
filesystem or consulting mutable repository state.  Store and transaction
validation remain separate layers.
"""

from __future__ import annotations

from typing import TypeVar

from ..errors import PipelineError
from ..foundation import sha256_bytes
from .json_wire import canonical_json_bytes, rendered_json_bytes
from .model import (
    CheckResult,
    EvidenceRef,
    Receipt,
    StateRoot,
    TransitionPlan,
    TransitionSpec,
)


_RecordT = TypeVar(
    "_RecordT",
    TransitionSpec,
    TransitionPlan,
    Receipt,
)


def _require_concrete(value: object, expected: type[_RecordT], label: str) -> _RecordT:
    if type(value) is not expected:
        raise PipelineError(f"{label} must be an exact {expected.__name__}")
    return value


def _require_canonical_match(actual: object, expected: object, label: str) -> None:
    """Require exact campaign-JSON identity without Python equality aliases."""

    if canonical_json_bytes(actual) != canonical_json_bytes(expected):
        raise PipelineError(f"{label} does not match")


def _require_reference_match(
    actual: EvidenceRef,
    expected: EvidenceRef,
    label: str,
) -> None:
    if type(actual) is not EvidenceRef or type(expected) is not EvidenceRef:
        raise PipelineError(f"{label} must contain exact EvidenceRef values")
    _require_canonical_match(
        actual.to_document(),
        expected.to_document(),
        label,
    )


def _require_record_binding(
    reference: EvidenceRef,
    record: _RecordT,
    *,
    kind: str,
    label: str,
) -> None:
    """Bind one reference to the semantic identity and rendered record bytes."""

    if type(reference) is not EvidenceRef:
        raise PipelineError(f"{label} must be an exact EvidenceRef")
    _require_canonical_match(reference.kind, kind, f"{label} kind")

    document = record.to_document()
    raw = rendered_json_bytes(document)
    _require_canonical_match(
        reference.target_content_sha256,
        record.content_sha256,
        f"{label} target_content_sha256",
    )
    _require_canonical_match(
        reference.file_sha256,
        sha256_bytes(raw),
        f"{label} file_sha256",
    )
    _require_canonical_match(reference.size, len(raw), f"{label} size")


def validate_spec_plan(spec: TransitionSpec, plan: TransitionPlan) -> None:
    """Validate one resolved plan against its exact declarative spec."""

    spec = _require_concrete(spec, TransitionSpec, "spec")
    plan = _require_concrete(plan, TransitionPlan, "plan")

    repeated_fields = (
        ("transition_id", spec.transition_id, plan.transition_id),
        ("campaign_id", spec.campaign_id, plan.campaign_id),
        ("kind", spec.kind, plan.kind),
        ("captured_at", spec.captured_at, plan.captured_at),
        ("reason", spec.reason, plan.reason),
    )
    for field, spec_value, plan_value in repeated_fields:
        _require_canonical_match(
            plan_value,
            spec_value,
            f"spec/plan {field}",
        )

    _require_reference_match(
        plan.predecessor,
        spec.predecessor,
        "spec/plan predecessor",
    )
    _require_reference_match(
        plan.phase_freeze,
        spec.phase_freeze,
        "spec/plan phase_freeze",
    )
    _require_record_binding(
        plan.spec,
        spec,
        kind="transition-spec",
        label="plan spec reference",
    )


def validate_plan_receipt(plan: TransitionPlan, receipt: Receipt) -> None:
    """Validate one receipt against its exact plan at any lifecycle stage."""

    plan = _require_concrete(plan, TransitionPlan, "plan")
    receipt = _require_concrete(receipt, Receipt, "receipt")

    _require_canonical_match(
        receipt.transition_id,
        plan.transition_id,
        "plan/receipt transition_id",
    )
    _require_record_binding(
        receipt.plan,
        plan,
        kind="transition-plan",
        label="receipt plan reference",
    )

    for check in receipt.checks:
        if type(check) is not CheckResult:
            raise PipelineError("receipt checks must be exact CheckResult values")
    _require_canonical_match(
        [check.check_id for check in receipt.checks],
        list(plan.required_checks),
        "receipt required check IDs",
    )
    for check in receipt.checks:
        _require_canonical_match(
            check.subject_sha256,
            plan.content_sha256,
            f"receipt check {check.check_id} subject_sha256",
        )


def validate_receipt_state_root(
    plan: TransitionPlan,
    receipt: Receipt,
    state_root: StateRoot,
) -> None:
    """Validate a passed post-commit receipt and the StateRoot it authorizes."""

    plan = _require_concrete(plan, TransitionPlan, "plan")
    receipt = _require_concrete(receipt, Receipt, "receipt")
    if type(state_root) is not StateRoot:
        raise PipelineError("state_root must be an exact StateRoot")

    validate_plan_receipt(plan, receipt)
    _require_canonical_match(
        receipt.stage,
        "post-commit",
        "state-root authorizing receipt stage",
    )
    _require_canonical_match(
        receipt.status,
        "passed",
        "state-root authorizing receipt status",
    )
    _require_canonical_match(
        state_root.campaign_id,
        plan.campaign_id,
        "plan/state-root campaign_id",
    )
    _require_canonical_match(
        state_root.transition_id,
        plan.transition_id,
        "plan/state-root transition_id",
    )
    _require_record_binding(
        state_root.plan,
        plan,
        kind="transition-plan",
        label="state-root plan reference",
    )
    _require_reference_match(
        state_root.plan,
        receipt.plan,
        "receipt/state-root plan reference",
    )
    _require_record_binding(
        state_root.receipt,
        receipt,
        kind="validation-receipt",
        label="state-root receipt reference",
    )
    _require_reference_match(
        state_root.current,
        plan.successor,
        "plan/state-root current reference",
    )


def validate_transition_chain(
    spec: TransitionSpec,
    plan: TransitionPlan,
    receipt: Receipt,
    state_root: StateRoot,
) -> None:
    """Validate the complete pure spec-to-StateRoot transition closure."""

    validate_spec_plan(spec, plan)
    validate_receipt_state_root(plan, receipt, state_root)


__all__ = [
    "validate_plan_receipt",
    "validate_receipt_state_root",
    "validate_spec_plan",
    "validate_transition_chain",
]
