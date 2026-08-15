"""Persist authenticated H4 check facts as immutable campaign evidence.

The check package owns process execution and fact authentication.  This module
is the one-way composition boundary into campaign storage: structured output
bytes are published first as immutable artifacts, and the exact H4 receipt is
published last.  Stored validation is read-only and never invokes a runner.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib

from ..checks import (
    CapturedStructuredOutput,
    CheckExecution,
    CheckReceipt,
    CheckResult,
    CheckRunner,
    CheckStatus,
    CheckTier,
    ResultOrigin,
    StructuredOutputRef,
    check_ids_for_tier,
    definition_for,
    validate_passed_check_result,
)
from ..checks.artifacts import authenticate_captured_outputs
from ..errors import PipelineError
from .json_wire import rendered_json_bytes
from .model import EvidenceRef
from .store import CampaignStore


_ArtifactKey = tuple[str, int]


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredCheckReceipt:
    """Non-wire result naming one exact receipt and its artifact closure."""

    receipt_ref: EvidenceRef
    artifact_refs: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        if (
            type(self.receipt_ref) is not EvidenceRef
            or self.receipt_ref.kind != "check-log"
            or self.receipt_ref.target_content_sha256 is not None
        ):
            raise PipelineError("stored check receipt reference is invalid")
        if type(self.artifact_refs) is not tuple or any(
            type(item) is not EvidenceRef
            or item.kind != "artifact"
            or item.target_content_sha256 is not None
            for item in self.artifact_refs
        ):
            raise PipelineError("stored check artifact references are invalid")
        keys = tuple((item.kind, item.path) for item in self.artifact_refs)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise PipelineError(
                "stored check artifact references must be sorted and unique"
            )


def _require_store(value: object) -> CampaignStore:
    if not isinstance(value, CampaignStore):
        raise PipelineError("check evidence store must be a CampaignStore")
    return value


def _require_local_tier(value: object) -> CheckTier:
    if type(value) is not CheckTier:
        raise PipelineError("check evidence tier must be an exact CheckTier")
    if value is CheckTier.REBUILD:
        raise PipelineError("external/rebuild receipts are not campaign process facts")
    return value


def _require_subject(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise PipelineError("check evidence subject must be a nonempty stripped string")
    return value


def _require_expected_check_ids(
    value: object,
    *,
    tier: CheckTier,
) -> tuple[str, ...]:
    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise PipelineError("expected check IDs must be an exact tuple of strings")
    expected = check_ids_for_tier(tier)
    if value != expected:
        raise PipelineError("expected check IDs differ from the registered tier")
    return value


def _require_receipt(
    receipt: object,
    *,
    expected_subject: str,
    expected_tier: CheckTier,
    expected_check_ids: tuple[str, ...],
    require_hydrated_outputs: bool,
) -> CheckReceipt:
    if type(receipt) is not CheckReceipt:
        raise PipelineError("check runner did not return an exact CheckReceipt")
    raw = receipt.to_bytes()
    decoded = CheckReceipt.from_bytes(raw)
    if decoded != receipt or decoded.to_bytes() != raw:
        raise PipelineError("check receipt does not have one exact canonical encoding")
    if receipt.subject != expected_subject:
        raise PipelineError("check receipt subject mismatch")
    if receipt.tier is not expected_tier:
        raise PipelineError("check receipt tier mismatch")
    if receipt.status is not CheckStatus.PASSED:
        raise PipelineError("check receipt did not pass")
    if receipt.origin is not ResultOrigin.LOCAL or receipt.attestor_id is not None:
        raise PipelineError("check receipt is not exact local process evidence")
    actual_ids = tuple(result.check_id for result in receipt.results)
    if actual_ids != expected_check_ids:
        raise PipelineError("check receipt check IDs/order are not complete")

    for result in receipt.results:
        definition = definition_for(result.check_id)
        if definition.execution is not CheckExecution.LOCAL:
            raise PipelineError(
                f"check receipt includes external check {result.check_id}"
            )
        if result.tier is not definition.tier:
            raise PipelineError(f"check result {result.check_id} tier mismatch")
        if result.subject != expected_subject:
            raise PipelineError(f"check result {result.check_id} subject mismatch")
        if result.status is not CheckStatus.PASSED:
            raise PipelineError(f"check result {result.check_id} did not pass")
        if result.origin is not ResultOrigin.LOCAL:
            raise PipelineError(f"check result {result.check_id} is not local")
        validate_passed_check_result(
            definition,
            result,
            require_hydrated_outputs=require_hydrated_outputs,
        )
    return receipt


def _structured_references(
    receipt: CheckReceipt,
) -> tuple[tuple[CheckResult, StructuredOutputRef], ...]:
    pairs: list[tuple[CheckResult, StructuredOutputRef]] = []
    bindings: set[str] = set()
    artifact_keys: set[_ArtifactKey] = set()
    for result in receipt.results:
        for reference in result.structured_outputs:
            key = (reference.sha256, reference.size)
            if reference.binding_sha256 in bindings:
                raise PipelineError("check receipt repeats a structured output binding")
            if key in artifact_keys:
                raise PipelineError("check receipt repeats structured output content")
            bindings.add(reference.binding_sha256)
            artifact_keys.add(key)
            pairs.append((result, reference))
    return tuple(pairs)


def _authenticate_artifact_closure(
    receipt: CheckReceipt,
    content_by_key: Mapping[_ArtifactKey, bytes],
) -> None:
    pairs = _structured_references(receipt)
    expected_keys = frozenset(
        (reference.sha256, reference.size) for _result, reference in pairs
    )
    if frozenset(content_by_key) != expected_keys:
        raise PipelineError("check receipt artifact closure is not exact")
    for key, raw in content_by_key.items():
        if type(key) is not tuple or len(key) != 2 or type(raw) is not bytes:
            raise PipelineError("check receipt artifact closure is malformed")
        digest, size = key
        if (
            type(digest) is not str
            or type(size) is not int
            or len(raw) != size
            or hashlib.sha256(raw).hexdigest() != digest
        ):
            raise PipelineError("check receipt artifact bytes do not match their ref")

    for result in receipt.results:
        outputs = tuple(
            CapturedStructuredOutput(
                format=reference.format,
                content=content_by_key[(reference.sha256, reference.size)],
            )
            for reference in result.structured_outputs
        )
        authenticated, skipped = authenticate_captured_outputs(
            definition_for(result.check_id),
            check_id=result.check_id,
            subject=result.subject,
            run_id=result.run_id,
            argv=result.argv,
            executed_argv=result.executed_argv,
            returncode=result.returncode if result.returncode is not None else -1,
            outputs=outputs,
        )
        if tuple(item.to_document() for item in authenticated) != tuple(
            item.to_document() for item in result.structured_outputs
        ):
            raise PipelineError(
                f"structured output refs do not authenticate for {result.check_id}"
            )
        if skipped != result.skipped_tests:
            raise PipelineError(
                f"structured skip evidence differs for {result.check_id}"
            )
        validate_passed_check_result(
            definition_for(result.check_id),
            replace(result, structured_outputs=authenticated),
        )


def _hydrated_artifacts(
    store: CampaignStore,
    receipt: CheckReceipt,
) -> tuple[tuple[EvidenceRef, bytes], ...]:
    content_by_key: dict[_ArtifactKey, bytes] = {}
    for _result, reference in _structured_references(receipt):
        if type(reference.content) is not bytes:
            raise PipelineError("check receipt contains unresolved structured evidence")
        raw = reference.content
        key = (reference.sha256, reference.size)
        if (
            len(raw) != reference.size
            or hashlib.sha256(raw).hexdigest() != reference.sha256
        ):
            raise PipelineError("hydrated structured evidence is tampered")
        content_by_key[key] = raw
    _authenticate_artifact_closure(receipt, content_by_key)

    candidates = tuple(
        (
            store.reference_for(
                kind="artifact",
                raw=raw,
                target_content_sha256=None,
            ),
            raw,
        )
        for _key, raw in content_by_key.items()
    )
    return tuple(sorted(candidates, key=lambda item: (item[0].kind, item[0].path)))


def run_and_store_check_receipt(
    *,
    runner: CheckRunner,
    store: CampaignStore,
    tier: CheckTier,
    subject: str,
    parameters_by_check: Mapping[str, Mapping[str, object]] | None = None,
) -> StoredCheckReceipt:
    """Run one local cumulative tier and publish its immutable evidence closure."""

    exact_store = _require_store(store)
    exact_tier = _require_local_tier(tier)
    exact_subject = _require_subject(subject)
    expected_ids = check_ids_for_tier(exact_tier)
    run_tier = getattr(runner, "run_tier", None)
    if not callable(run_tier):
        raise PipelineError("check runner does not provide run_tier")
    receipt = run_tier(
        exact_tier,
        subject=exact_subject,
        parameters_by_check=parameters_by_check,
    )
    exact_receipt = _require_receipt(
        receipt,
        expected_subject=exact_subject,
        expected_tier=exact_tier,
        expected_check_ids=expected_ids,
        require_hydrated_outputs=True,
    )
    receipt_raw = exact_receipt.to_bytes()
    artifacts = _hydrated_artifacts(exact_store, exact_receipt)
    receipt_ref = exact_store.reference_for(
        kind="check-log",
        raw=receipt_raw,
        target_content_sha256=None,
    )
    result = StoredCheckReceipt(
        receipt_ref=receipt_ref,
        artifact_refs=tuple(reference for reference, _raw in artifacts),
    )

    # Artifacts are the receipt's closure and must become durable first.  A
    # later failure can leave harmless CAS orphans but never a new receipt that
    # names missing or unauthenticated evidence.
    for reference, raw in artifacts:
        exact_store.create_or_verify(reference=reference, raw=raw)
    for reference, _raw in artifacts:
        exact_store.read_exact(reference)
    exact_store.create_or_verify(reference=receipt_ref, raw=receipt_raw)
    return result


def store_reference_envelope(
    *,
    store: CampaignStore,
    reference: EvidenceRef,
) -> EvidenceRef:
    """Store one exact EvidenceRef document as a canonical artifact envelope.

    The referenced object must already be durable and authentic.  This keeps
    receipt/artifact publication ordered before the small resume envelope and
    gives the CLI a canonical repo-relative input path without shell-created
    files.
    """

    exact_store = _require_store(store)
    if type(reference) is not EvidenceRef:
        raise PipelineError("reference envelope target must be an EvidenceRef")
    exact_store.read_exact(reference)
    raw = rendered_json_bytes(reference.to_document())
    envelope = exact_store.reference_for(
        kind="artifact",
        raw=raw,
        target_content_sha256=reference.content_sha256,
    )
    exact_store.create_or_verify(reference=envelope, raw=raw)
    if exact_store.read_exact(envelope) != raw:
        raise PipelineError("stored reference envelope bytes are not exact")
    return envelope


def validate_stored_check_receipt(
    *,
    store: CampaignStore,
    receipt_ref: EvidenceRef,
    artifact_refs: tuple[EvidenceRef, ...],
    expected_subject: str,
    expected_tier: CheckTier,
    expected_check_ids: tuple[str, ...],
) -> CheckReceipt:
    """Read and authenticate one exact stored local receipt and artifact closure."""

    exact_store = _require_store(store)
    exact_tier = _require_local_tier(expected_tier)
    exact_subject = _require_subject(expected_subject)
    exact_ids = _require_expected_check_ids(expected_check_ids, tier=exact_tier)
    if (
        type(receipt_ref) is not EvidenceRef
        or receipt_ref.kind != "check-log"
        or receipt_ref.target_content_sha256 is not None
    ):
        raise PipelineError("stored process receipt must be a raw check-log ref")
    receipt_raw = exact_store.read_exact(receipt_ref)
    if receipt_ref != exact_store.reference_for(
        kind="check-log",
        raw=receipt_raw,
        target_content_sha256=None,
    ):
        raise PipelineError("stored process receipt reference is not canonical")
    receipt = _require_receipt(
        CheckReceipt.from_bytes(receipt_raw),
        expected_subject=exact_subject,
        expected_tier=exact_tier,
        expected_check_ids=exact_ids,
        require_hydrated_outputs=False,
    )

    if type(artifact_refs) is not tuple or any(
        type(item) is not EvidenceRef
        or item.kind != "artifact"
        or item.target_content_sha256 is not None
        for item in artifact_refs
    ):
        raise PipelineError("stored artifact closure must contain artifact refs")
    reference_keys = tuple((item.kind, item.path) for item in artifact_refs)
    if (
        reference_keys != tuple(sorted(reference_keys))
        or len(reference_keys) != len(set(reference_keys))
    ):
        raise PipelineError("stored artifact closure must be sorted and unique")

    content_by_key: dict[_ArtifactKey, bytes] = {}
    for reference in artifact_refs:
        raw = exact_store.read_exact(reference)
        canonical = exact_store.reference_for(
            kind="artifact",
            raw=raw,
            target_content_sha256=None,
        )
        if reference != canonical:
            raise PipelineError("stored artifact reference is not canonical")
        key = (canonical.file_sha256, canonical.size)
        if key in content_by_key:
            raise PipelineError("stored artifact closure repeats content")
        content_by_key[key] = raw
    _authenticate_artifact_closure(receipt, content_by_key)
    return receipt


__all__ = [
    "StoredCheckReceipt",
    "run_and_store_check_receipt",
    "store_reference_envelope",
    "validate_stored_check_receipt",
]
