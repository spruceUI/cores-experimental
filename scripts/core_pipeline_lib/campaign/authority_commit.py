"""Pointer-last commit and historical verification for staged authority plans.

This module consumes one exact :class:`AuthorityStagePlanV1` staged receipt.  It
does not plan, run checks, expose a mutable selector, or publish externally.
Every immutable H5/H6 object and the complete H3 generation-1 ancestry is
verified before the legacy matrix pointer is replaced under the campaign lock.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Callable, Protocol, TypeVar

from ..errors import PipelineError
from .authority_staging import (
    StagedAuthorityStageV1,
    load_staged_authority_plan,
    verify_staged_authority_pointer,
)
from .json_wire import decode_identity_object, rendered_json_bytes
from .model import EvidenceRef, Receipt, StateRoot
from .phase_freeze import CAMPAIGN_STATE_RELATIVE
from .store import CampaignStore, CommitResult
from .workflow import load_historical_transition


Clock = Callable[[], str]
_RecordT = TypeVar("_RecordT", Receipt, StateRoot)


class _Reader(Protocol):
    def read_exact(self, reference: EvidenceRef) -> bytes: ...


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_store(value: object) -> CampaignStore:
    if type(value) is not CampaignStore:
        raise PipelineError("authority commit requires an exact CampaignStore")
    if value.state_relative != CAMPAIGN_STATE_RELATIVE:
        raise PipelineError("authority commit requires the consolidated campaign store")
    return value


def _require_staged_receipt_ref(value: object) -> EvidenceRef:
    if (
        type(value) is not EvidenceRef
        or value.kind != "validation-receipt"
        or value.target_content_sha256 is None
    ):
        raise PipelineError(
            "authority commit staged token must be a semantic validation-receipt"
        )
    return value


def _timestamp(clock: Clock) -> str:
    if not callable(clock):
        raise PipelineError("authority commit clock must be callable")
    value = clock()
    if type(value) is not str:
        raise PipelineError("authority commit clock must return an exact timestamp")
    return value


def _sorted_unique_refs(*references: EvidenceRef) -> tuple[EvidenceRef, ...]:
    if any(type(reference) is not EvidenceRef for reference in references):
        raise PipelineError("authority commit closure must contain exact EvidenceRefs")
    by_key: dict[tuple[str, str], EvidenceRef] = {}
    for reference in references:
        key = (reference.kind, reference.path)
        previous = by_key.get(key)
        if previous is not None and previous != reference:
            raise PipelineError("authority commit closure collides by kind/path")
        by_key[key] = reference
    return tuple(by_key[key] for key in sorted(by_key))


def _transaction_required_objects(
    staged: StagedAuthorityStageV1,
) -> tuple[EvidenceRef, ...]:
    if type(staged) is not StagedAuthorityStageV1:
        raise PipelineError("authority commit retention source is not staged")
    result = _sorted_unique_refs(
        *staged.staged_required_objects,
        *staged.historical_transition.required_objects,
    )
    if any(reference.kind == "matrix-pointer" for reference in result):
        raise PipelineError("authority commit retention closure contains a pointer")
    return result


def _historical_required_objects(
    staged: StagedAuthorityStageV1,
    *,
    state_root_ref: EvidenceRef,
    pre_commit_receipt_ref: EvidenceRef,
    post_commit_receipt_ref: EvidenceRef,
) -> tuple[EvidenceRef, ...]:
    result = _sorted_unique_refs(
        *_transaction_required_objects(staged),
        state_root_ref,
        pre_commit_receipt_ref,
        post_commit_receipt_ref,
    )
    if any(reference.kind == "matrix-pointer" for reference in result):
        raise PipelineError("historical authority closure contains a pointer")
    return result


def _record_reference(
    store: CampaignStore,
    *,
    kind: str,
    record: Receipt | StateRoot,
) -> tuple[EvidenceRef, bytes]:
    raw = rendered_json_bytes(record.to_document())
    return (
        store.reference_for(
            kind=kind,
            raw=raw,
            target_content_sha256=record.content_sha256,
        ),
        raw,
    )


def _read_record(
    store: CampaignStore,
    reader: _Reader,
    reference: EvidenceRef,
    record_type: type[_RecordT],
    *,
    kind: str,
    label: str,
) -> tuple[_RecordT, bytes]:
    if type(reference) is not EvidenceRef or reference.kind != kind:
        raise PipelineError(f"{label} reference kind is invalid")
    raw = reader.read_exact(reference)
    record = record_type.from_document(decode_identity_object(raw, label=label))
    if rendered_json_bytes(record.to_document()) != raw:
        raise PipelineError(f"{label} bytes are not canonical")
    expected = store.reference_for(
        kind=kind,
        raw=raw,
        target_content_sha256=record.content_sha256,
    )
    if reference != expected:
        raise PipelineError(f"{label} reference is not canonical")
    return record, raw


def _stage_record(
    store: CampaignStore,
    reference: EvidenceRef,
    raw: bytes,
) -> None:
    store.create_or_verify(reference=reference, raw=raw)


def _load_staged(
    store: CampaignStore,
    staged_receipt_ref: EvidenceRef,
    *,
    require_live_engine: bool,
    reader: _Reader | None = None,
) -> StagedAuthorityStageV1:
    _require_staged_receipt_ref(staged_receipt_ref)
    exact_reader = store if reader is None else reader
    if not callable(getattr(exact_reader, "read_exact", None)):
        raise PipelineError("authority commit reader is invalid")

    def load_h3(locked_reader: object, state_root_ref: EvidenceRef):
        return load_historical_transition(
            store,
            reader=locked_reader,  # type: ignore[arg-type]
            state_root_ref=state_root_ref,
        )

    return load_staged_authority_plan(
        store,
        staged_receipt_ref,
        require_live_engine=require_live_engine,
        reader=exact_reader,
        historical_root_loader=load_h3,
    )


def _passed_receipt(
    staged: StagedAuthorityStageV1,
    *,
    stage: str,
    outputs: tuple[EvidenceRef, ...],
    clock: Clock,
) -> Receipt:
    timestamp = _timestamp(clock)
    receipt = Receipt(
        transition_id=staged.planned.plan.transition_id,
        plan=staged.planned.plan_reference,
        stage=stage,
        status="passed",
        started_at=timestamp,
        completed_at=timestamp,
        checks=staged.receipt.checks,
        outputs=outputs,
    )
    _require_receipt(staged, receipt, stage=stage, outputs=outputs)
    return receipt


def _require_receipt(
    staged: StagedAuthorityStageV1,
    receipt: object,
    *,
    stage: str,
    outputs: tuple[EvidenceRef, ...],
) -> Receipt:
    if type(staged) is not StagedAuthorityStageV1 or type(receipt) is not Receipt:
        raise PipelineError(f"{stage} authority receipt is invalid")
    if (
        receipt.transition_id != staged.planned.plan.transition_id
        or receipt.plan != staged.planned.plan_reference
        or receipt.stage != stage
        or receipt.status != "passed"
        or receipt.started_at != receipt.completed_at
        or receipt.checks != staged.receipt.checks
        or receipt.outputs != outputs
    ):
        raise PipelineError(f"{stage} authority receipt closure is not exact")
    return receipt


def _require_state_root(
    staged: StagedAuthorityStageV1,
    state_root: object,
    *,
    post_commit_receipt_ref: EvidenceRef,
) -> StateRoot:
    if type(staged) is not StagedAuthorityStageV1 or type(state_root) is not StateRoot:
        raise PipelineError("committed authority StateRoot is invalid")
    prior_root = staged.historical_transition.state_root
    if (
        prior_root.generation != 1
        or state_root.generation != prior_root.generation + 1
        or state_root.generation != 2
        or state_root.campaign_id != staged.planned.plan.campaign_id
        or state_root.transition_id != staged.planned.plan.transition_id
        or state_root.plan != staged.planned.plan_reference
        or state_root.receipt != post_commit_receipt_ref
        or state_root.current != staged.canonical_successor_matrix
        or state_root.previous != staged.prior_state_root
    ):
        raise PipelineError("committed authority StateRoot topology is not exact")
    if state_root.current.kind != "matrix-snapshot":
        raise PipelineError(
            "committed authority current object is not canonical matrix data"
        )
    return state_root


def _only_kind(
    references: tuple[EvidenceRef, ...],
    kind: str,
    *,
    label: str,
) -> EvidenceRef:
    matches = tuple(reference for reference in references if reference.kind == kind)
    if len(matches) != 1:
        raise PipelineError(f"{label} must contain exactly one {kind} reference")
    return matches[0]


@dataclass(frozen=True, slots=True, kw_only=True)
class _LoadedHistoricalAuthorityCommitV1:
    """Exact pointer-free generation-2 authority ancestry."""

    state_root: StateRoot
    state_root_ref: EvidenceRef
    staged: StagedAuthorityStageV1
    pre_commit_receipt_ref: EvidenceRef
    post_commit_receipt_ref: EvidenceRef
    current_pointer_ref: EvidenceRef
    required_objects: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if type(self.state_root) is not StateRoot or type(
            self.staged
        ) is not StagedAuthorityStageV1:
            raise PipelineError("historical authority commit values are invalid")
        expected_kinds = (
            (self.state_root_ref, "state-root"),
            (self.pre_commit_receipt_ref, "validation-receipt"),
            (self.post_commit_receipt_ref, "validation-receipt"),
            (self.current_pointer_ref, "matrix-pointer"),
        )
        if any(
            type(reference) is not EvidenceRef
            or reference.kind != kind
            or reference.target_content_sha256 is None
            for reference, kind in expected_kinds
        ):
            raise PipelineError("historical authority reference topology is invalid")
        _require_state_root(
            self.staged,
            self.state_root,
            post_commit_receipt_ref=self.post_commit_receipt_ref,
        )
        if (
            self.state_root_ref.target_content_sha256
            != self.state_root.content_sha256
            or self.state_root.receipt != self.post_commit_receipt_ref
            or self.current_pointer_ref != self.staged.successor_pointer
        ):
            raise PipelineError("historical authority named closure is invalid")
        expected_required = _historical_required_objects(
            self.staged,
            state_root_ref=self.state_root_ref,
            pre_commit_receipt_ref=self.pre_commit_receipt_ref,
            post_commit_receipt_ref=self.post_commit_receipt_ref,
        )
        if self.required_objects != expected_required:
            raise PipelineError("historical authority retention closure is not exact")


def _load_historical_authority_commit(
    store: CampaignStore,
    *,
    state_root_ref: EvidenceRef,
    reader: _Reader | None = None,
) -> _LoadedHistoricalAuthorityCommitV1:
    """Deeply authenticate generation 2 without reading mutable selection."""

    store = _require_store(store)
    exact_reader = store if reader is None else reader
    if not callable(getattr(exact_reader, "read_exact", None)):
        raise PipelineError("historical authority reader is invalid")
    state_root, _root_raw = _read_record(
        store,
        exact_reader,
        state_root_ref,
        StateRoot,
        kind="state-root",
        label="authority StateRoot",
    )
    post_ref = state_root.receipt
    post_receipt, _post_raw = _read_record(
        store,
        exact_reader,
        post_ref,
        Receipt,
        kind="validation-receipt",
        label="authority post-commit receipt",
    )
    pointer_ref = _only_kind(
        post_receipt.outputs,
        "matrix-pointer",
        label="authority post-commit receipt",
    )
    pre_ref = _only_kind(
        post_receipt.outputs,
        "validation-receipt",
        label="authority post-commit receipt",
    )
    pre_receipt, _pre_raw = _read_record(
        store,
        exact_reader,
        pre_ref,
        Receipt,
        kind="validation-receipt",
        label="authority pre-commit receipt",
    )
    staged_ref = _only_kind(
        pre_receipt.outputs,
        "validation-receipt",
        label="authority pre-commit receipt",
    )
    staged = _load_staged(
        store,
        staged_ref,
        require_live_engine=False,
        reader=exact_reader,
    )
    _require_receipt(
        staged,
        pre_receipt,
        stage="pre-commit",
        outputs=(staged_ref,),
    )
    post_outputs = _sorted_unique_refs(pre_ref, staged.successor_pointer)
    _require_receipt(
        staged,
        post_receipt,
        stage="post-commit",
        outputs=post_outputs,
    )
    if pointer_ref != staged.successor_pointer:
        raise PipelineError("post-commit pointer differs from the staged successor")
    _require_state_root(
        staged,
        state_root,
        post_commit_receipt_ref=post_ref,
    )
    required_objects = _historical_required_objects(
        staged,
        state_root_ref=state_root_ref,
        pre_commit_receipt_ref=pre_ref,
        post_commit_receipt_ref=post_ref,
    )
    return _LoadedHistoricalAuthorityCommitV1(
        state_root=state_root,
        state_root_ref=state_root_ref,
        staged=staged,
        pre_commit_receipt_ref=pre_ref,
        post_commit_receipt_ref=post_ref,
        current_pointer_ref=pointer_ref,
        required_objects=required_objects,
    )


def commit_authority_plan(
    store: CampaignStore,
    *,
    staged_receipt_ref: EvidenceRef,
    clock: Clock = _utc_now,
) -> tuple[CommitResult, EvidenceRef]:
    """Commit one exact staged H5/H6 closure through a rollback-safe CAS."""

    store = _require_store(store)
    staged_receipt_ref = _require_staged_receipt_ref(staged_receipt_ref)
    initial = _load_staged(
        store,
        staged_receipt_ref,
        require_live_engine=True,
    )
    verify_staged_authority_pointer(
        initial,
        expected_pointer="predecessor",
        reader=store,
    )
    required_objects = _transaction_required_objects(initial)
    created: dict[str, EvidenceRef] = {}

    def load_locked(view: object) -> StagedAuthorityStageV1:
        locked = _load_staged(
            store,
            staged_receipt_ref,
            require_live_engine=True,
            reader=view,  # type: ignore[arg-type]
        )
        if locked != initial:
            raise PipelineError(
                "staged authority closure changed under the pointer lock"
            )
        if _transaction_required_objects(locked) != required_objects:
            raise PipelineError(
                "authority retention closure changed under the pointer lock"
            )
        return locked

    def pre_commit(view: object) -> Receipt:
        locked = load_locked(view)
        verify_staged_authority_pointer(
            locked,
            expected_pointer="predecessor",
            reader=view,  # type: ignore[arg-type]
        )
        pre_receipt = _passed_receipt(
            locked,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
            clock=clock,
        )
        pre_ref, pre_raw = _record_reference(
            store,
            kind="validation-receipt",
            record=pre_receipt,
        )
        _stage_record(store, pre_ref, pre_raw)
        persisted_pre, _persisted_raw = _read_record(
            store,
            view,  # type: ignore[arg-type]
            pre_ref,
            Receipt,
            kind="validation-receipt",
            label="authority pre-commit receipt",
        )
        _require_receipt(
            locked,
            persisted_pre,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
        )
        if persisted_pre != pre_receipt:
            raise PipelineError("persisted pre-commit receipt changed")
        created["pre"] = pre_ref
        return persisted_pre

    def post_commit(view: object) -> Receipt:
        locked = load_locked(view)
        verify_staged_authority_pointer(
            locked,
            expected_pointer="successor",
            reader=view,  # type: ignore[arg-type]
        )
        pre_ref = created.get("pre")
        if pre_ref is None:
            raise PipelineError("post-commit validation has no pre-commit receipt")
        pre_receipt, _pre_raw = _read_record(
            store,
            view,  # type: ignore[arg-type]
            pre_ref,
            Receipt,
            kind="validation-receipt",
            label="authority pre-commit receipt",
        )
        _require_receipt(
            locked,
            pre_receipt,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
        )

        post_outputs = _sorted_unique_refs(pre_ref, locked.successor_pointer)
        post_receipt = _passed_receipt(
            locked,
            stage="post-commit",
            outputs=post_outputs,
            clock=clock,
        )
        post_ref, post_raw = _record_reference(
            store,
            kind="validation-receipt",
            record=post_receipt,
        )
        state_root = StateRoot(
            campaign_id=locked.planned.plan.campaign_id,
            generation=locked.historical_transition.state_root.generation + 1,
            transition_id=locked.planned.plan.transition_id,
            plan=locked.planned.plan_reference,
            receipt=post_ref,
            current=locked.canonical_successor_matrix,
            previous=locked.prior_state_root,
        )
        _require_state_root(
            locked,
            state_root,
            post_commit_receipt_ref=post_ref,
        )
        root_ref, root_raw = _record_reference(
            store,
            kind="state-root",
            record=state_root,
        )

        # The successor pointer is already visible.  These immutable records are
        # persisted and reloaded before the transaction is allowed to return.
        _stage_record(store, post_ref, post_raw)
        _stage_record(store, root_ref, root_raw)
        persisted_post, _persisted_post_raw = _read_record(
            store,
            view,  # type: ignore[arg-type]
            post_ref,
            Receipt,
            kind="validation-receipt",
            label="authority post-commit receipt",
        )
        persisted_root, _persisted_root_raw = _read_record(
            store,
            view,  # type: ignore[arg-type]
            root_ref,
            StateRoot,
            kind="state-root",
            label="authority StateRoot",
        )
        _require_receipt(
            locked,
            persisted_post,
            stage="post-commit",
            outputs=post_outputs,
        )
        _require_state_root(
            locked,
            persisted_root,
            post_commit_receipt_ref=post_ref,
        )
        if persisted_post != post_receipt or persisted_root != state_root:
            raise PipelineError("persisted post-commit authority closure changed")
        verify_staged_authority_pointer(
            locked,
            expected_pointer="successor",
            reader=view,  # type: ignore[arg-type]
        )
        created["post"] = post_ref
        created["root"] = root_ref
        return persisted_post

    transaction = store.pointer_transaction(
        campaign_id=initial.planned.plan.campaign_id,
        expected=initial.predecessor_pointer,
        successor=initial.successor_pointer,
        successor_raw=initial.successor_raw,
        required_objects=required_objects,
    )
    result = transaction.commit(pre_commit=pre_commit, post_commit=post_commit)
    pre_ref = created.get("pre")
    post_ref = created.get("post")
    root_ref = created.get("root")
    if pre_ref is None or post_ref is None or root_ref is None:
        raise PipelineError("authority transaction did not create its StateRoot")
    result_pre_ref, _ = _record_reference(
        store,
        kind="validation-receipt",
        record=result.pre_commit,
    )
    result_post_ref, _ = _record_reference(
        store,
        kind="validation-receipt",
        record=result.post_commit,
    )
    if (
        result.before is None
        or result.before.reference != initial.predecessor_pointer
        or result.before.raw != initial.predecessor_raw
        or result.after.reference != initial.successor_pointer
        or result.after.raw != initial.successor_raw
        or result_pre_ref != pre_ref
        or result_post_ref != post_ref
    ):
        raise PipelineError("authority transaction result is not exact")
    return result, root_ref


def verify_committed_authority_plan(
    store: CampaignStore,
    *,
    state_root_ref: EvidenceRef,
) -> StateRoot:
    """Verify exact generation-2 ancestry and live successor selection."""

    store = _require_store(store)
    predicted = _load_historical_authority_commit(
        store,
        state_root_ref=state_root_ref,
    )

    def verify_locked(view: object) -> StateRoot:
        persisted = _load_historical_authority_commit(
            store,
            state_root_ref=state_root_ref,
            reader=view,  # type: ignore[arg-type]
        )
        if persisted != predicted:
            raise PipelineError(
                "committed authority closure changed during verification"
            )
        verify_staged_authority_pointer(
            persisted.staged,
            expected_pointer="successor",
            reader=view,  # type: ignore[arg-type]
        )
        verify_staged_authority_pointer(
            persisted.staged,
            expected_pointer="successor",
            reader=view,  # type: ignore[arg-type]
        )
        return persisted.state_root

    return store.verify_pointer(
        campaign_id=predicted.state_root.campaign_id,
        expected=predicted.current_pointer_ref,
        validator=verify_locked,
    )


__all__ = [
    "Clock",
    "commit_authority_plan",
    "verify_committed_authority_plan",
]
