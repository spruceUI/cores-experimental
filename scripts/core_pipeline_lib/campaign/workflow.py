"""Imperative shell for the first consolidated campaign transition.

The pure matrix policy remains in :mod:`campaign.transition`.  This module
owns authenticated reads, immutable staging, receipt topology, and the one
pointer transaction.  It deliberately does not execute checks, shells,
builds, publication, Git, audit, or external-service work.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
from typing import Protocol, TypeVar

from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..source_bundle import (
    pipeline_source_bundle,
    pipeline_source_bundle_is_well_formed,
)
from .json_wire import (
    canonical_json_bytes,
    decode_identity_object,
    rendered_json_bytes,
)
from .model import (
    CheckResult,
    EvidenceRef,
    Receipt,
    StateRoot,
    TransitionPlan,
    TransitionSpec,
)
from .store import CampaignStore, CommitResult
from .transition import (
    EXPECTED_ENGINE_BUNDLE_PATH,
    EXPECTED_SCHEMA_CANONICAL_SHA256,
    EXPECTED_SCHEMA_PATH,
    EXPECTED_SPEC_PATH,
    PlannedMatrixAuthorityRefresh,
    legacy_matrix_compatibility_references,
    legacy_matrix_pointer_reference,
    plan_matrix_authority_refresh,
    validate_matrix_authority_refresh,
)
from .validate import (
    validate_plan_receipt,
    validate_transition_chain,
)


DEFAULT_STATE_RELATIVE = ".local-e2e/campaign-state"

Clock = Callable[[], str]
_RecordT = TypeVar("_RecordT", TransitionSpec, TransitionPlan, Receipt, StateRoot)


class _Reader(Protocol):
    def read_exact(self, reference: EvidenceRef) -> bytes: ...

    def read_pointer(self, reference: EvidenceRef): ...


@dataclass(frozen=True, slots=True)
class _PredictedClosure:
    """Private authenticated inputs and pure result for a write-free prediction."""

    spec: TransitionSpec
    spec_ref: EvidenceRef
    engine_document: dict[str, object]
    engine_ref: EvidenceRef
    schema_raw: bytes
    predecessor_raw: bytes
    phase_freeze_raw: bytes
    result: PlannedMatrixAuthorityRefresh


@dataclass(frozen=True, slots=True)
class _PlannedClosure:
    """Private, non-wire material needed to validate one exact plan."""

    spec: TransitionSpec
    spec_ref: EvidenceRef
    spec_object_ref: EvidenceRef
    engine_document: dict[str, object]
    engine_ref: EvidenceRef
    engine_object_ref: EvidenceRef
    schema_raw: bytes
    schema_ref: EvidenceRef
    predecessor_raw: bytes
    predecessor_ref: EvidenceRef
    phase_freeze_raw: bytes
    phase_freeze_ref: EvidenceRef
    process_receipt_ref: EvidenceRef
    result: PlannedMatrixAuthorityRefresh
    plan_ref: EvidenceRef
    legacy_snapshot_ref: EvidenceRef
    legacy_cas_ref: EvidenceRef
    base_outputs: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadedHistoricalTransition:
    """Fully authenticated immutable H3 ancestry, without pointer selection."""

    state_root: StateRoot
    state_root_ref: EvidenceRef
    staged_receipt_ref: EvidenceRef
    check_receipt_ref: EvidenceRef
    pre_commit_receipt_ref: EvidenceRef
    post_commit_receipt_ref: EvidenceRef
    process_receipt_ref: EvidenceRef
    current_pointer_ref: EvidenceRef
    required_objects: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if type(self.state_root) is not StateRoot:
            raise PipelineError("historical transition StateRoot is invalid")
        expected_kinds = (
            (self.state_root_ref, "state-root"),
            (self.staged_receipt_ref, "validation-receipt"),
            (self.check_receipt_ref, "validation-receipt"),
            (self.pre_commit_receipt_ref, "validation-receipt"),
            (self.post_commit_receipt_ref, "validation-receipt"),
            (self.process_receipt_ref, "check-log"),
            (self.current_pointer_ref, "matrix-pointer"),
        )
        if any(
            type(reference) is not EvidenceRef or reference.kind != kind
            for reference, kind in expected_kinds
        ):
            raise PipelineError("historical transition reference topology is invalid")
        if self.state_root_ref.target_content_sha256 != self.state_root.content_sha256:
            raise PipelineError("historical transition StateRoot identity is invalid")
        if (
            type(self.required_objects) is not tuple
            or not self.required_objects
            or any(type(item) is not EvidenceRef for item in self.required_objects)
        ):
            raise PipelineError("historical transition retention closure is invalid")
        keys = tuple((item.kind, item.path) for item in self.required_objects)
        if (
            keys != tuple(sorted(keys))
            or len(keys) != len(set(keys))
            or any(item.kind == "matrix-pointer" for item in self.required_objects)
        ):
            raise PipelineError("historical transition retention closure is invalid")
        named_immutable = {
            self.state_root_ref,
            self.staged_receipt_ref,
            self.check_receipt_ref,
            self.pre_commit_receipt_ref,
            self.post_commit_receipt_ref,
            self.process_receipt_ref,
            self.state_root.plan,
            self.state_root.current,
        }
        if not named_immutable.issubset(set(self.required_objects)) or (
            self.state_root.receipt != self.post_commit_receipt_ref
            or self.current_pointer_ref.file_sha256
            != self.state_root.current.file_sha256
            or self.current_pointer_ref.target_content_sha256
            != self.state_root.current.target_content_sha256
            or self.current_pointer_ref.size != self.state_root.current.size
        ):
            raise PipelineError("historical transition named closure is invalid")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _require_store(store: object) -> CampaignStore:
    if type(store) is not CampaignStore:
        raise PipelineError("workflow store must be an exact CampaignStore")
    if store.state_relative != DEFAULT_STATE_RELATIVE:
        raise PipelineError("campaign store state path is not the consolidated path")
    return store


def _timestamp(clock: Clock) -> str:
    if not callable(clock):
        raise PipelineError("workflow clock must be callable")
    value = clock()
    if type(value) is not str:
        raise PipelineError("workflow clock must return an exact timestamp string")
    return value


def _sorted_refs(*references: EvidenceRef) -> tuple[EvidenceRef, ...]:
    if any(type(reference) is not EvidenceRef for reference in references):
        raise PipelineError("workflow evidence must contain exact EvidenceRef values")
    result = tuple(sorted(references, key=lambda item: (item.kind, item.path)))
    keys = tuple((item.kind, item.path) for item in result)
    if len(keys) != len(set(keys)):
        raise PipelineError("workflow evidence contains duplicate kind/path values")
    return result


def _same_document(left: object, right: object, *, label: str) -> None:
    if canonical_json_bytes(left) != canonical_json_bytes(right):
        raise PipelineError(f"{label} does not match")


def _record_reference(
    store: CampaignStore,
    *,
    kind: str,
    record: TransitionPlan | Receipt | StateRoot,
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
    document = decode_identity_object(raw, label=label)
    record = record_type.from_document(document)
    exact_raw = rendered_json_bytes(record.to_document())
    if raw != exact_raw:
        raise PipelineError(f"{label} bytes are not the exact campaign rendering")
    if reference.target_content_sha256 != record.content_sha256:
        raise PipelineError(f"{label} semantic reference is invalid")
    return record, raw


def _read_engine(
    reader: _Reader,
    reference: EvidenceRef,
) -> tuple[dict[str, object], bytes]:
    if type(reference) is not EvidenceRef or reference.kind != "engine-bundle":
        raise PipelineError("engine bundle reference kind is invalid")
    raw = reader.read_exact(reference)
    document = decode_identity_object(raw, label="engine bundle")
    if rendered_json_bytes(document) != raw:
        raise PipelineError("engine bundle bytes are not the exact campaign rendering")
    if not pipeline_source_bundle_is_well_formed(document):
        raise PipelineError("engine bundle is not a well-formed source bundle")
    content_sha256 = document.get("content_sha256")
    if reference.target_content_sha256 != content_sha256:
        raise PipelineError("engine bundle semantic reference is invalid")
    return document, raw


def _require_live_engine(engine_document: dict[str, object]) -> None:
    live = pipeline_source_bundle()
    if not pipeline_source_bundle_is_well_formed(live):
        raise PipelineError("live pipeline source bundle is not well-formed")
    if canonical_json_bytes(live) != canonical_json_bytes(engine_document):
        raise PipelineError("live pipeline sources differ from the engine bundle")


def _canonical_object_reference(
    store: CampaignStore,
    reference: EvidenceRef,
    raw: bytes,
) -> None:
    expected = store.reference_for(
        kind=reference.kind,
        raw=raw,
        target_content_sha256=reference.target_content_sha256,
    )
    if reference != expected:
        raise PipelineError(
            f"{reference.kind} reference is not canonical store evidence"
        )


def _require_reference_identity(
    authority: EvidenceRef,
    immutable_copy: EvidenceRef,
    *,
    label: str,
) -> None:
    if (
        authority.kind != immutable_copy.kind
        or authority.file_sha256 != immutable_copy.file_sha256
        or authority.target_content_sha256
        != immutable_copy.target_content_sha256
        or authority.size != immutable_copy.size
    ):
        raise PipelineError(f"{label} CAS copy differs from its plan authority")


def _require_process_receipt(
    store: CampaignStore,
    reader: _Reader,
    reference: EvidenceRef,
) -> bytes:
    if type(reference) is not EvidenceRef or reference.kind != "check-log":
        raise PipelineError("process receipt must be an exact check-log EvidenceRef")
    raw = reader.read_exact(reference)
    _canonical_object_reference(store, reference, raw)
    return raw


def _bootstrap_record(
    store: CampaignStore,
    *,
    path: str,
    kind: str,
    record_type: type[_RecordT],
    label: str,
) -> tuple[_RecordT, EvidenceRef, bytes]:
    raw = store.read_snapshot(path)
    document = decode_identity_object(raw, label=label)
    record = record_type.from_document(document)
    if rendered_json_bytes(record.to_document()) != raw:
        raise PipelineError(f"{label} bytes are not the exact campaign rendering")
    reference = EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=record.content_sha256,
        size=len(raw),
    )
    authenticated, authenticated_raw = _read_record(
        store,
        reference,
        record_type,
        kind=kind,
        label=label,
    )
    _same_document(
        authenticated.to_document(),
        record.to_document(),
        label=f"bootstrapped {label}",
    )
    if authenticated_raw != raw:
        raise PipelineError(f"{label} changed after bootstrap")
    return authenticated, reference, raw


def _bootstrap_engine(
    store: CampaignStore,
) -> tuple[dict[str, object], EvidenceRef, bytes]:
    raw = store.read_snapshot(EXPECTED_ENGINE_BUNDLE_PATH)
    document = decode_identity_object(raw, label="engine bundle")
    if rendered_json_bytes(document) != raw:
        raise PipelineError("engine bundle bytes are not the exact campaign rendering")
    if not pipeline_source_bundle_is_well_formed(document):
        raise PipelineError("engine bundle is not a well-formed source bundle")
    content_sha256 = document.get("content_sha256")
    if type(content_sha256) is not str:
        raise PipelineError("engine bundle content identity is invalid")
    reference = EvidenceRef(
        kind="engine-bundle",
        path=EXPECTED_ENGINE_BUNDLE_PATH,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=content_sha256,
        size=len(raw),
    )
    authenticated, authenticated_raw = _read_engine(store, reference)
    _same_document(authenticated, document, label="bootstrapped engine bundle")
    if authenticated_raw != raw:
        raise PipelineError("engine bundle changed after bootstrap")
    return authenticated, reference, raw


def _bootstrap_schema(store: CampaignStore) -> tuple[bytes, EvidenceRef]:
    raw = store.read_snapshot(EXPECTED_SCHEMA_PATH)
    source_reference = EvidenceRef(
        kind="artifact",
        path=EXPECTED_SCHEMA_PATH,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=EXPECTED_SCHEMA_CANONICAL_SHA256,
        size=len(raw),
    )
    if store.read_exact(source_reference) != raw:
        raise PipelineError("matrix schema changed after bootstrap")
    return raw, source_reference


def _plan_reference(
    store: CampaignStore,
    result: PlannedMatrixAuthorityRefresh,
) -> EvidenceRef:
    reference, _raw = _record_reference(
        store,
        kind="transition-plan",
        record=result.plan,
    )
    return reference


def _make_closure(
    store: CampaignStore,
    *,
    spec: TransitionSpec,
    spec_ref: EvidenceRef,
    engine_document: dict[str, object],
    engine_ref: EvidenceRef,
    schema_raw: bytes,
    predecessor_raw: bytes,
    phase_freeze_raw: bytes,
    process_receipt_ref: EvidenceRef,
    result: PlannedMatrixAuthorityRefresh,
) -> _PlannedClosure:
    plan_ref = _plan_reference(store, result)
    spec_raw = rendered_json_bytes(spec.to_document())
    spec_object_ref = store.reference_for(
        kind="transition-spec",
        raw=spec_raw,
        target_content_sha256=spec.content_sha256,
    )
    engine_raw = rendered_json_bytes(engine_document)
    engine_object_ref = store.reference_for(
        kind="engine-bundle",
        raw=engine_raw,
        target_content_sha256=engine_ref.target_content_sha256,
    )
    schema_ref = store.reference_for(
        kind="artifact",
        raw=schema_raw,
        target_content_sha256=EXPECTED_SCHEMA_CANONICAL_SHA256,
    )
    predecessor_ref = store.reference_for(
        kind="matrix-snapshot",
        raw=predecessor_raw,
        target_content_sha256=spec.predecessor.target_content_sha256,
    )
    phase_freeze_ref = store.reference_for(
        kind="phase-freeze-cas",
        raw=phase_freeze_raw,
        target_content_sha256=spec.phase_freeze.target_content_sha256,
    )
    successor_ref = store.reference_for(
        kind="matrix-snapshot",
        raw=result.candidate_raw,
        target_content_sha256=result.plan.successor.target_content_sha256,
    )
    if successor_ref != result.plan.successor:
        raise PipelineError("planned successor is not canonical consolidated evidence")
    legacy_snapshot_ref, legacy_cas_ref = legacy_matrix_compatibility_references(
        result
    )
    base_outputs = _sorted_refs(
        process_receipt_ref,
        schema_ref,
        predecessor_ref,
        phase_freeze_ref,
        spec_object_ref,
        engine_object_ref,
        result.plan.successor,
        legacy_snapshot_ref,
        legacy_cas_ref,
        plan_ref,
    )
    return _PlannedClosure(
        spec=spec,
        spec_ref=spec_ref,
        spec_object_ref=spec_object_ref,
        engine_document=engine_document,
        engine_ref=engine_ref,
        engine_object_ref=engine_object_ref,
        schema_raw=schema_raw,
        schema_ref=schema_ref,
        predecessor_raw=predecessor_raw,
        predecessor_ref=predecessor_ref,
        phase_freeze_raw=phase_freeze_raw,
        phase_freeze_ref=phase_freeze_ref,
        process_receipt_ref=process_receipt_ref,
        result=result,
        plan_ref=plan_ref,
        legacy_snapshot_ref=legacy_snapshot_ref,
        legacy_cas_ref=legacy_cas_ref,
        base_outputs=base_outputs,
    )


def _bootstrap_prediction(store: CampaignStore) -> _PredictedClosure:
    spec_value, spec_ref, _spec_raw = _bootstrap_record(
        store,
        path=EXPECTED_SPEC_PATH,
        kind="transition-spec",
        record_type=TransitionSpec,
        label="transition spec",
    )
    if type(spec_value) is not TransitionSpec:
        raise AssertionError("closed bootstrap returned a non-spec")
    engine_document, engine_ref, _engine_raw = _bootstrap_engine(store)
    schema_raw, _schema_source_ref = _bootstrap_schema(store)

    predecessor = store.read_pointer(spec_value.predecessor)
    if predecessor is None:
        raise PipelineError("authorized predecessor pointer is missing")
    phase_freeze_raw = store.read_exact(spec_value.phase_freeze)
    result = plan_matrix_authority_refresh(
        spec=spec_value,
        spec_ref=spec_ref,
        predecessor_raw=predecessor.raw,
        phase_freeze_raw=phase_freeze_raw,
        engine_bundle_ref=engine_ref,
        engine_bundle_document=engine_document,
    )
    validate_matrix_authority_refresh(
        result,
        spec=spec_value,
        spec_ref=spec_ref,
        predecessor_raw=predecessor.raw,
        phase_freeze_raw=phase_freeze_raw,
        engine_bundle_ref=engine_ref,
        engine_bundle_document=engine_document,
        schema_raw=schema_raw,
    )
    # Bind the executing tracked sources after reconstruction, immediately
    # before accepting the predicted plan.
    _require_live_engine(engine_document)
    return _PredictedClosure(
        spec=spec_value,
        spec_ref=spec_ref,
        engine_document=engine_document,
        engine_ref=engine_ref,
        schema_raw=schema_raw,
        predecessor_raw=predecessor.raw,
        phase_freeze_raw=phase_freeze_raw,
        result=result,
    )


def _bootstrap_closure(
    store: CampaignStore,
    process_receipt_ref: EvidenceRef,
) -> _PlannedClosure:
    _require_process_receipt(store, store, process_receipt_ref)
    predicted = _bootstrap_prediction(store)
    return _make_closure(
        store,
        spec=predicted.spec,
        spec_ref=predicted.spec_ref,
        engine_document=predicted.engine_document,
        engine_ref=predicted.engine_ref,
        schema_raw=predicted.schema_raw,
        predecessor_raw=predicted.predecessor_raw,
        phase_freeze_raw=predicted.phase_freeze_raw,
        process_receipt_ref=process_receipt_ref,
        result=predicted.result,
    )


def _semantic_checks(
    plan: TransitionPlan,
    process_receipt_ref: EvidenceRef,
) -> tuple[CheckResult, ...]:
    return tuple(
        CheckResult(
            check_id=check_id,
            subject_sha256=plan.content_sha256,
            status="passed",
            evidence=(process_receipt_ref,),
        )
        for check_id in plan.required_checks
    )


def _passed_receipt(
    closure: _PlannedClosure,
    *,
    stage: str,
    outputs: tuple[EvidenceRef, ...],
    clock: Clock,
) -> Receipt:
    timestamp = _timestamp(clock)
    receipt = Receipt(
        transition_id=closure.spec.transition_id,
        plan=closure.plan_ref,
        stage=stage,
        status="passed",
        started_at=timestamp,
        completed_at=timestamp,
        checks=_semantic_checks(
            closure.result.plan,
            closure.process_receipt_ref,
        ),
        outputs=outputs,
    )
    validate_plan_receipt(closure.result.plan, receipt)
    _require_receipt_evidence(receipt, closure.process_receipt_ref)
    return receipt


def _require_receipt_evidence(
    receipt: Receipt,
    process_receipt_ref: EvidenceRef,
) -> None:
    expected = (process_receipt_ref,)
    if any(check.evidence != expected for check in receipt.checks):
        raise PipelineError(
            "every campaign semantic check must name the same process receipt"
        )
    if any(check.message is not None for check in receipt.checks):
        raise PipelineError("passed campaign semantic checks must not carry messages")


def _require_receipt(
    plan: TransitionPlan,
    receipt: Receipt,
    *,
    stage: str,
    outputs: tuple[EvidenceRef, ...],
    process_receipt_ref: EvidenceRef,
) -> None:
    validate_plan_receipt(plan, receipt)
    if receipt.stage != stage or receipt.status != "passed":
        raise PipelineError(f"{stage} receipt does not authorize this lifecycle stage")
    if receipt.outputs != outputs:
        raise PipelineError(f"{stage} receipt output closure is not exact")
    _require_receipt_evidence(receipt, process_receipt_ref)


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


def _predecessor_copy(
    store: CampaignStore,
    reader: _Reader,
    plan: TransitionPlan,
    outputs: tuple[EvidenceRef, ...],
) -> EvidenceRef:
    matches = tuple(
        reference
        for reference in outputs
        if reference.kind == "matrix-snapshot"
        and reference.file_sha256 == plan.predecessor.file_sha256
        and reference.target_content_sha256
        == plan.predecessor.target_content_sha256
        and reference.size == plan.predecessor.size
    )
    if len(matches) != 1:
        raise PipelineError("staged closure has no exact immutable predecessor")
    raw = reader.read_exact(matches[0])
    _canonical_object_reference(store, matches[0], raw)
    return matches[0]


def _load_staged_closure(
    store: CampaignStore,
    reader: _Reader,
    staged_ref: EvidenceRef,
    *,
    require_live_engine: bool,
) -> tuple[_PlannedClosure, Receipt, EvidenceRef, Receipt]:
    staged_value, staged_raw = _read_record(
        reader,
        staged_ref,
        Receipt,
        kind="validation-receipt",
        label="staged receipt",
    )
    if type(staged_value) is not Receipt:
        raise AssertionError("closed receipt decoder returned a non-receipt")
    _canonical_object_reference(store, staged_ref, staged_raw)
    if staged_value.stage != "staged" or staged_value.status != "passed":
        raise PipelineError("staged receipt is not a passed staged receipt")

    plan_value, plan_raw = _read_record(
        reader,
        staged_value.plan,
        TransitionPlan,
        kind="transition-plan",
        label="transition plan",
    )
    if type(plan_value) is not TransitionPlan:
        raise AssertionError("closed plan decoder returned a non-plan")
    _canonical_object_reference(store, staged_value.plan, plan_raw)

    spec_object_ref = _only_kind(
        staged_value.outputs,
        "transition-spec",
        label="staged closure",
    )
    spec_value, spec_raw = _read_record(
        reader,
        spec_object_ref,
        TransitionSpec,
        kind="transition-spec",
        label="transition spec CAS",
    )
    if type(spec_value) is not TransitionSpec:
        raise AssertionError("closed spec decoder returned a non-spec")
    _canonical_object_reference(store, spec_object_ref, spec_raw)
    _require_reference_identity(
        plan_value.spec,
        spec_object_ref,
        label="transition spec",
    )
    engine_object_ref = _only_kind(
        staged_value.outputs,
        "engine-bundle",
        label="staged closure",
    )
    engine_document, engine_raw = _read_engine(reader, engine_object_ref)
    _canonical_object_reference(store, engine_object_ref, engine_raw)
    _require_reference_identity(
        plan_value.engine_bundle,
        engine_object_ref,
        label="engine bundle",
    )

    process_ref = _only_kind(
        staged_value.outputs,
        "check-log",
        label="staged closure",
    )
    _require_process_receipt(store, reader, process_ref)
    schema_ref = _only_kind(
        staged_value.outputs,
        "artifact",
        label="staged closure",
    )
    schema_raw = reader.read_exact(schema_ref)
    _canonical_object_reference(store, schema_ref, schema_raw)
    predecessor_ref = _predecessor_copy(
        store,
        reader,
        plan_value,
        staged_value.outputs,
    )
    predecessor_raw = reader.read_exact(predecessor_ref)
    freeze_ref = _only_kind(
        staged_value.outputs,
        "phase-freeze-cas",
        label="staged closure",
    )
    phase_freeze_raw = reader.read_exact(freeze_ref)
    _canonical_object_reference(store, freeze_ref, phase_freeze_raw)
    if (
        freeze_ref.file_sha256 != plan_value.phase_freeze.file_sha256
        or freeze_ref.target_content_sha256
        != plan_value.phase_freeze.target_content_sha256
        or freeze_ref.size != plan_value.phase_freeze.size
    ):
        raise PipelineError("phase-freeze CAS differs from the reviewed freeze")
    if (
        plan_value.pipeline_bundle.file_sha256 != freeze_ref.file_sha256
        or plan_value.pipeline_bundle.size != freeze_ref.size
    ):
        raise PipelineError("pipeline bundle raw identity differs from the freeze CAS")

    successor_raw = reader.read_exact(plan_value.successor)
    _canonical_object_reference(store, plan_value.successor, successor_raw)
    result = plan_matrix_authority_refresh(
        spec=spec_value,
        spec_ref=plan_value.spec,
        predecessor_raw=predecessor_raw,
        phase_freeze_raw=phase_freeze_raw,
        engine_bundle_ref=plan_value.engine_bundle,
        engine_bundle_document=engine_document,
    )
    _same_document(
        result.plan.to_document(),
        plan_value.to_document(),
        label="reconstructed transition plan",
    )
    if result.candidate_raw != successor_raw:
        raise PipelineError("staged successor differs from pure reconstruction")
    validate_matrix_authority_refresh(
        result,
        spec=spec_value,
        spec_ref=plan_value.spec,
        predecessor_raw=predecessor_raw,
        phase_freeze_raw=phase_freeze_raw,
        engine_bundle_ref=plan_value.engine_bundle,
        engine_bundle_document=engine_document,
        schema_raw=schema_raw,
    )
    closure = _make_closure(
        store,
        spec=spec_value,
        spec_ref=plan_value.spec,
        engine_document=engine_document,
        engine_ref=plan_value.engine_bundle,
        schema_raw=schema_raw,
        predecessor_raw=predecessor_raw,
        phase_freeze_raw=phase_freeze_raw,
        process_receipt_ref=process_ref,
        result=result,
    )
    if closure.plan_ref != staged_value.plan:
        raise PipelineError("staged receipt names a noncanonical transition plan")
    if (
        closure.predecessor_ref != predecessor_ref
        or closure.phase_freeze_ref != freeze_ref
        or closure.spec_object_ref != spec_object_ref
        or closure.engine_object_ref != engine_object_ref
    ):
        raise PipelineError("staged immutable input references are not exact")

    for reference in (
        closure.legacy_snapshot_ref,
        closure.legacy_cas_ref,
    ):
        if reader.read_exact(reference) != result.candidate_raw:
            raise PipelineError("legacy successor alias bytes are not exact")

    check_ref = _only_kind(
        staged_value.outputs,
        "validation-receipt",
        label="staged closure",
    )
    check_value, check_raw = _read_record(
        reader,
        check_ref,
        Receipt,
        kind="validation-receipt",
        label="check receipt",
    )
    if type(check_value) is not Receipt:
        raise AssertionError("closed receipt decoder returned a non-receipt")
    _canonical_object_reference(store, check_ref, check_raw)
    _require_receipt(
        result.plan,
        check_value,
        stage="check",
        outputs=closure.base_outputs,
        process_receipt_ref=process_ref,
    )
    _require_receipt(
        result.plan,
        staged_value,
        stage="staged",
        outputs=_sorted_refs(*closure.base_outputs, check_ref),
        process_receipt_ref=process_ref,
    )
    if require_live_engine:
        # In stage/commit this executes after every immutable input and receipt
        # has been reconstructed.  Historical verification intentionally uses
        # the sealed engine CAS so future tracked-source additions do not
        # invalidate an already committed root.
        _require_live_engine(engine_document)
    return closure, check_value, check_ref, staged_value


def _stage_reference(
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
        raise PipelineError(f"staged {reference.kind} bytes are not exact")


def predict_transition(store: CampaignStore) -> TransitionPlan:
    """Return the fully validated plan without creating evidence or a lock."""

    store = _require_store(store)
    return _bootstrap_prediction(store).result.plan


def check_transition(
    store: CampaignStore,
    *,
    process_receipt_ref: EvidenceRef,
    clock: Clock = _utc_now,
) -> Receipt:
    """Pure-plan and deeply check the frozen transition without writing state."""

    store = _require_store(store)
    closure = _bootstrap_closure(store, process_receipt_ref)
    return _passed_receipt(
        closure,
        stage="check",
        outputs=closure.base_outputs,
        clock=clock,
    )


def stage_transition(
    store: CampaignStore,
    *,
    process_receipt_ref: EvidenceRef,
    clock: Clock = _utc_now,
) -> EvidenceRef:
    """Create or verify the exact immutable closure, stopping before commit."""

    store = _require_store(store)
    closure = _bootstrap_closure(store, process_receipt_ref)

    spec_raw = rendered_json_bytes(closure.spec.to_document())
    engine_raw = rendered_json_bytes(closure.engine_document)
    _stage_reference(store, closure.spec_object_ref, spec_raw)
    _stage_reference(store, closure.engine_object_ref, engine_raw)
    _stage_reference(store, closure.schema_ref, closure.schema_raw)
    _stage_reference(store, closure.predecessor_ref, closure.predecessor_raw)
    _stage_reference(store, closure.phase_freeze_ref, closure.phase_freeze_raw)
    _stage_reference(
        store,
        closure.result.plan.successor,
        closure.result.candidate_raw,
    )
    # These are the exact two legacy successor aliases.  Path policy belongs
    # to transition.py; the workflow only asks the store to create or verify.
    _stage_reference(
        store,
        closure.legacy_snapshot_ref,
        closure.result.candidate_raw,
        caller_path=True,
    )
    _stage_reference(
        store,
        closure.legacy_cas_ref,
        closure.result.candidate_raw,
        caller_path=True,
    )

    plan_raw = rendered_json_bytes(closure.result.plan.to_document())
    _stage_reference(store, closure.plan_ref, plan_raw)
    check_receipt = _passed_receipt(
        closure,
        stage="check",
        outputs=closure.base_outputs,
        clock=clock,
    )
    check_ref, check_raw = _record_reference(
        store,
        kind="validation-receipt",
        record=check_receipt,
    )
    _stage_reference(store, check_ref, check_raw)

    staged_receipt = _passed_receipt(
        closure,
        stage="staged",
        outputs=_sorted_refs(*closure.base_outputs, check_ref),
        clock=clock,
    )
    staged_ref, staged_raw = _record_reference(
        store,
        kind="validation-receipt",
        record=staged_receipt,
    )
    _stage_reference(store, staged_ref, staged_raw)
    # Re-open the whole staged closure before returning a resume identity.
    _load_staged_closure(
        store,
        store,
        staged_ref,
        require_live_engine=True,
    )
    return staged_ref


def commit_transition(
    store: CampaignStore,
    *,
    staged_receipt_ref: EvidenceRef,
    clock: Clock = _utc_now,
) -> tuple[CommitResult, EvidenceRef]:
    """Commit one staged closure and return store result plus immutable root."""

    store = _require_store(store)
    closure, _check, _check_ref, staged_receipt = _load_staged_closure(
        store,
        store,
        staged_receipt_ref,
        require_live_engine=True,
    )
    pointer_ref = legacy_matrix_pointer_reference(closure.spec, closure.result)
    required_objects = _sorted_refs(*staged_receipt.outputs, staged_receipt_ref)
    if any(reference.kind == "matrix-pointer" for reference in required_objects):
        raise PipelineError("staged immutable closure must not contain a pointer")

    created: dict[str, EvidenceRef] = {}

    def pre_commit(view) -> Receipt:
        locked, _locked_check, _locked_check_ref, locked_staged = (
            _load_staged_closure(
                store,
                view,
                staged_receipt_ref,
                require_live_engine=True,
            )
        )
        before = view.read_pointer(locked.spec.predecessor)
        if before is None or before.raw != locked.predecessor_raw:
            raise PipelineError("locked pre-commit predecessor pointer is not exact")
        pre_receipt = _passed_receipt(
            locked,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
            clock=clock,
        )
        _require_receipt(
            locked.result.plan,
            pre_receipt,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
            process_receipt_ref=locked.process_receipt_ref,
        )
        pre_ref, pre_raw = _record_reference(
            store,
            kind="validation-receipt",
            record=pre_receipt,
        )
        _stage_reference(store, pre_ref, pre_raw)
        persisted, _raw = _read_record(
            view,
            pre_ref,
            Receipt,
            kind="validation-receipt",
            label="pre-commit receipt",
        )
        if type(persisted) is not Receipt:
            raise AssertionError("closed receipt decoder returned a non-receipt")
        _require_receipt(
            locked.result.plan,
            persisted,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
            process_receipt_ref=locked.process_receipt_ref,
        )
        _same_document(
            locked_staged.to_document(),
            staged_receipt.to_document(),
            label="locked staged receipt",
        )
        created["pre"] = pre_ref
        return persisted

    def post_commit(view) -> Receipt:
        visible = view.read_pointer(pointer_ref)
        if visible is None or visible.raw != closure.result.candidate_raw:
            raise PipelineError("post-commit successor pointer is not exact")
        locked, _locked_check, _locked_check_ref, _locked_staged = (
            _load_staged_closure(
                store,
                view,
                staged_receipt_ref,
                require_live_engine=True,
            )
        )
        locked_pointer = legacy_matrix_pointer_reference(locked.spec, locked.result)
        if locked_pointer != pointer_ref:
            raise PipelineError("locked successor pointer identity drifted")
        visible = view.read_pointer(locked_pointer)
        if visible is None or visible.raw != locked.result.candidate_raw:
            raise PipelineError("successor pointer changed during post validation")
        pre_ref = created.get("pre")
        if pre_ref is None:
            raise PipelineError("post-commit validation has no pre-commit receipt")
        pre_value, _pre_raw = _read_record(
            view,
            pre_ref,
            Receipt,
            kind="validation-receipt",
            label="pre-commit receipt",
        )
        if type(pre_value) is not Receipt:
            raise AssertionError("closed receipt decoder returned a non-receipt")
        _require_receipt(
            locked.result.plan,
            pre_value,
            stage="pre-commit",
            outputs=(staged_receipt_ref,),
            process_receipt_ref=locked.process_receipt_ref,
        )

        post_outputs = _sorted_refs(pre_ref, locked_pointer)
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
            campaign_id=locked.spec.campaign_id,
            generation=1,
            transition_id=locked.spec.transition_id,
            plan=locked.plan_ref,
            receipt=post_ref,
            current=locked.result.plan.successor,
            previous=None,
        )
        validate_transition_chain(
            locked.spec,
            locked.result.plan,
            post_receipt,
            state_root,
        )
        _require_receipt(
            locked.result.plan,
            post_receipt,
            stage="post-commit",
            outputs=post_outputs,
            process_receipt_ref=locked.process_receipt_ref,
        )
        root_ref, root_raw = _record_reference(
            store,
            kind="state-root",
            record=state_root,
        )

        # Neither object exists until the new pointer is visibly installed and
        # the complete in-memory closure above has passed.
        _stage_reference(store, post_ref, post_raw)
        _stage_reference(store, root_ref, root_raw)
        persisted_post, _ = _read_record(
            view,
            post_ref,
            Receipt,
            kind="validation-receipt",
            label="post-commit receipt",
        )
        persisted_root, _ = _read_record(
            view,
            root_ref,
            StateRoot,
            kind="state-root",
            label="state root",
        )
        if type(persisted_post) is not Receipt or type(persisted_root) is not StateRoot:
            raise AssertionError("closed post-commit decoder returned a wrong record")
        validate_transition_chain(
            locked.spec,
            locked.result.plan,
            persisted_post,
            persisted_root,
        )
        _require_receipt(
            locked.result.plan,
            persisted_post,
            stage="post-commit",
            outputs=post_outputs,
            process_receipt_ref=locked.process_receipt_ref,
        )
        visible = view.read_pointer(locked_pointer)
        if visible is None or visible.raw != locked.result.candidate_raw:
            raise PipelineError("successor pointer changed after durable evidence")
        created["root"] = root_ref
        return persisted_post

    transaction = store.pointer_transaction(
        campaign_id=closure.spec.campaign_id,
        expected=closure.spec.predecessor,
        successor=pointer_ref,
        successor_raw=closure.result.candidate_raw,
        required_objects=required_objects,
    )
    result = transaction.commit(pre_commit=pre_commit, post_commit=post_commit)
    root_ref = created.get("root")
    if root_ref is None:
        raise PipelineError("committed transaction did not create a StateRoot")
    return result, root_ref


def load_historical_transition(
    store: CampaignStore,
    *,
    reader: _Reader | None = None,
    state_root_ref: EvidenceRef,
) -> LoadedHistoricalTransition:
    """Authenticate the complete immutable H3 chain without reading a pointer.

    ``reader`` may be an already-locked transaction view.  Every evidence byte
    is obtained through that reader; ``store`` is used only to derive and
    compare canonical content-addressed references.
    """

    store = _require_store(store)
    exact_reader = store if reader is None else reader
    if not callable(getattr(exact_reader, "read_exact", None)):
        raise PipelineError("historical transition reader is invalid")
    root_value, root_raw = _read_record(
        exact_reader,
        state_root_ref,
        StateRoot,
        kind="state-root",
        label="state root",
    )
    if type(root_value) is not StateRoot:
        raise AssertionError("closed root decoder returned a non-root")
    _canonical_object_reference(store, state_root_ref, root_raw)
    post_value, post_raw = _read_record(
        exact_reader,
        root_value.receipt,
        Receipt,
        kind="validation-receipt",
        label="post-commit receipt",
    )
    if type(post_value) is not Receipt:
        raise AssertionError("closed receipt decoder returned a non-receipt")
    _canonical_object_reference(store, root_value.receipt, post_raw)
    pointer_ref = _only_kind(
        post_value.outputs,
        "matrix-pointer",
        label="post-commit receipt",
    )
    pre_ref = _only_kind(
        post_value.outputs,
        "validation-receipt",
        label="post-commit receipt",
    )
    pre_value, pre_raw = _read_record(
        exact_reader,
        pre_ref,
        Receipt,
        kind="validation-receipt",
        label="pre-commit receipt",
    )
    if type(pre_value) is not Receipt:
        raise AssertionError("closed receipt decoder returned a non-receipt")
    _canonical_object_reference(store, pre_ref, pre_raw)
    staged_ref = _only_kind(
        pre_value.outputs,
        "validation-receipt",
        label="pre-commit receipt",
    )
    closure, _check, check_ref, staged_value = _load_staged_closure(
        store,
        exact_reader,
        staged_ref,
        require_live_engine=False,
    )
    expected_pointer = legacy_matrix_pointer_reference(closure.spec, closure.result)
    if expected_pointer != pointer_ref:
        raise PipelineError("StateRoot chain names a different live pointer")
    _require_receipt(
        closure.result.plan,
        pre_value,
        stage="pre-commit",
        outputs=(staged_ref,),
        process_receipt_ref=closure.process_receipt_ref,
    )
    post_outputs = _sorted_refs(pre_ref, expected_pointer)
    _require_receipt(
        closure.result.plan,
        post_value,
        stage="post-commit",
        outputs=post_outputs,
        process_receipt_ref=closure.process_receipt_ref,
    )
    validate_transition_chain(
        closure.spec,
        closure.result.plan,
        post_value,
        root_value,
    )
    if root_value.generation != 1 or root_value.previous is not None:
        raise PipelineError("pilot StateRoot generation topology is invalid")
    required_objects = _sorted_refs(
        state_root_ref,
        root_value.receipt,
        pre_ref,
        staged_ref,
        *staged_value.outputs,
    )
    if any(reference.kind == "matrix-pointer" for reference in required_objects):
        raise PipelineError("historical retention closure contains a pointer")
    return LoadedHistoricalTransition(
        state_root=root_value,
        state_root_ref=state_root_ref,
        staged_receipt_ref=staged_ref,
        check_receipt_ref=check_ref,
        pre_commit_receipt_ref=pre_ref,
        post_commit_receipt_ref=root_value.receipt,
        process_receipt_ref=closure.process_receipt_ref,
        current_pointer_ref=expected_pointer,
        required_objects=required_objects,
    )


def verify_transition(
    store: CampaignStore,
    *,
    state_root_ref: EvidenceRef,
) -> StateRoot:
    """Verify an immutable chain and its exact live pointer under shared lock."""

    store = _require_store(store)
    predicted = load_historical_transition(
        store,
        reader=store,
        state_root_ref=state_root_ref,
    )

    def validate_locked(view) -> StateRoot:
        persisted = load_historical_transition(
            store,
            reader=view,
            state_root_ref=state_root_ref,
        )
        if persisted != predicted:
            raise PipelineError("historical transition changed before locked verification")
        successor_raw = view.read_exact(persisted.state_root.current)
        live = view.read_pointer(persisted.current_pointer_ref)
        if live is None or live.raw != successor_raw:
            raise PipelineError("StateRoot chain is not selected by the live pointer")
        live = view.read_pointer(persisted.current_pointer_ref)
        if live is None or live.raw != successor_raw:
            raise PipelineError("live pointer changed during chain verification")
        return persisted.state_root

    return store.verify_pointer(
        campaign_id=predicted.state_root.campaign_id,
        expected=predicted.current_pointer_ref,
        validator=validate_locked,
    )


__all__ = [
    "Clock",
    "DEFAULT_STATE_RELATIVE",
    "LoadedHistoricalTransition",
    "check_transition",
    "commit_transition",
    "load_historical_transition",
    "predict_transition",
    "stage_transition",
    "verify_transition",
]
