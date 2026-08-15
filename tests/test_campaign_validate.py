from __future__ import annotations

import copy
from dataclasses import fields, replace
import unittest

from scripts.core_pipeline_lib.campaign.json_wire import (
    canonical_json_sha256,
    rendered_json_bytes,
)
from scripts.core_pipeline_lib.campaign.model import (
    MATRIX_AUTHORITY_ALLOWED_CHANGES,
    MATRIX_AUTHORITY_REQUIRED_CHECKS,
    CheckResult,
    EvidenceRef,
    Receipt,
    StateRoot,
    TransitionPlan,
    TransitionSpec,
)
from scripts.core_pipeline_lib.campaign.validate import (
    validate_plan_receipt,
    validate_receipt_state_root,
    validate_spec_plan,
    validate_transition_chain,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _evidence(kind: str, name: str, number: int) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=_sha256(number),
        target_content_sha256=_sha256(number + 1000),
        size=100 + number,
    )


def _record_reference(
    kind: str,
    name: str,
    record: TransitionSpec | TransitionPlan | Receipt,
) -> EvidenceRef:
    raw = rendered_json_bytes(record.to_document())
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=sha256_bytes(raw),
        target_content_sha256=record.content_sha256,
        size=len(raw),
    )


def _spec() -> TransitionSpec:
    return TransitionSpec(
        transition_id="post-gambatte-authority-v1",
        campaign_id="core-build-campaign-v1",
        kind="matrix-authority-refresh-v1",
        captured_at="2026-08-14T12:34:56Z",
        reason="Refresh matrix authority from the sealed Gambatte freeze.",
        predecessor=_evidence("matrix-pointer", "predecessor", 1),
        phase_freeze=_evidence("phase-freeze", "phase-freeze", 2),
    )


def _plan(spec: TransitionSpec) -> TransitionPlan:
    return TransitionPlan(
        transition_id=spec.transition_id,
        campaign_id=spec.campaign_id,
        kind=spec.kind,
        captured_at=spec.captured_at,
        reason=spec.reason,
        spec=_record_reference("transition-spec", "transition-spec", spec),
        engine_bundle=_evidence("engine-bundle", "engine-bundle", 3),
        predecessor=spec.predecessor,
        phase_freeze=spec.phase_freeze,
        pipeline_bundle=_evidence("pipeline-bundle", "pipeline-bundle", 4),
        successor=_evidence("matrix-snapshot", "successor", 5),
        allowed_changes=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        preserved_projection_sha256=_sha256(6),
        required_checks=MATRIX_AUTHORITY_REQUIRED_CHECKS,
    )


def _checks(
    plan: TransitionPlan,
    *,
    failed_id: str | None = None,
) -> tuple[CheckResult, ...]:
    return tuple(
        CheckResult(
            check_id=check_id,
            subject_sha256=plan.content_sha256,
            status="failed" if check_id == failed_id else "passed",
            message=(
                "required validation failed" if check_id == failed_id else None
            ),
        )
        for check_id in plan.required_checks
    )


def _receipt(
    plan: TransitionPlan,
    *,
    stage: str = "post-commit",
    status: str = "passed",
) -> Receipt:
    failed_id = plan.required_checks[0] if status == "failed" else None
    return Receipt(
        transition_id=plan.transition_id,
        plan=_record_reference("transition-plan", "transition-plan", plan),
        stage=stage,
        status=status,
        started_at="2026-08-14T12:35:00Z",
        completed_at="2026-08-14T12:35:01Z",
        checks=_checks(plan, failed_id=failed_id),
        outputs=(plan.successor,),
    )


def _state_root(plan: TransitionPlan, receipt: Receipt) -> StateRoot:
    return StateRoot(
        campaign_id=plan.campaign_id,
        generation=1,
        transition_id=plan.transition_id,
        plan=receipt.plan,
        receipt=_record_reference(
            "validation-receipt",
            "validation-receipt",
            receipt,
        ),
        current=plan.successor,
        previous=None,
    )


def _chain() -> tuple[TransitionSpec, TransitionPlan, Receipt, StateRoot]:
    spec = _spec()
    plan = _plan(spec)
    receipt = _receipt(plan)
    return spec, plan, receipt, _state_root(plan, receipt)


def _resign(document: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(document)
    result.pop("content_sha256", None)
    result["content_sha256"] = canonical_json_sha256(result)
    return result


class _SpecSubclass(TransitionSpec):
    pass


class _PlanSubclass(TransitionPlan):
    pass


class _ReceiptSubclass(Receipt):
    pass


class _StateRootSubclass(StateRoot):
    pass


def _subclass_copy(record: object, subclass: type[object]) -> object:
    return subclass(
        **{field.name: getattr(record, field.name) for field in fields(record)}
    )


class CampaignValidateTests(unittest.TestCase):
    def test_complete_transition_chain_is_valid(self) -> None:
        spec, plan, receipt, state_root = _chain()

        self.assertIsNone(validate_spec_plan(spec, plan))
        self.assertIsNone(validate_plan_receipt(plan, receipt))
        self.assertIsNone(
            validate_receipt_state_root(plan, receipt, state_root)
        )
        self.assertIsNone(
            validate_transition_chain(spec, plan, receipt, state_root)
        )

    def test_spec_plan_requires_every_repeated_scalar(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        mismatches = (
            {"transition_id": "different-transition-v1"},
            {"campaign_id": "different-campaign-v1"},
            {"captured_at": "2026-08-14T12:34:57Z"},
            {"reason": "A different but otherwise valid reason."},
        )

        for changes in mismatches:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    validate_spec_plan(spec, replace(plan, **changes))

    def test_spec_plan_requires_canonical_predecessor_and_freeze_refs(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        predecessor = spec.predecessor
        mismatches = (
            replace(predecessor, path="campaign/evidence/other-pointer.json"),
            replace(predecessor, file_sha256=_sha256(40)),
            replace(predecessor, target_content_sha256=_sha256(41)),
            replace(predecessor, size=predecessor.size + 1),
        )

        for reference in mismatches:
            with self.subTest(field="predecessor", reference=reference):
                with self.assertRaises(PipelineError):
                    validate_spec_plan(
                        spec,
                        replace(plan, predecessor=reference),
                    )

        other_freeze = replace(
            spec.phase_freeze,
            path="campaign/evidence/other-freeze.json",
        )
        with self.assertRaises(PipelineError):
            validate_spec_plan(spec, replace(plan, phase_freeze=other_freeze))

    def test_plan_spec_reference_binds_semantic_and_rendered_identities(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        reference = plan.spec
        mismatches = (
            replace(reference, target_content_sha256=_sha256(50)),
            replace(reference, file_sha256=_sha256(51)),
            replace(reference, size=reference.size + 1),
        )

        for bad_reference in mismatches:
            with self.subTest(reference=bad_reference):
                with self.assertRaises(PipelineError):
                    validate_spec_plan(
                        spec,
                        replace(plan, spec=bad_reference),
                    )

    def test_plan_receipt_binds_transition_and_exact_plan_bytes(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        receipt = _receipt(plan)

        with self.assertRaises(PipelineError):
            validate_plan_receipt(
                plan,
                replace(receipt, transition_id="different-transition-v1"),
            )

        reference = receipt.plan
        mismatches = (
            replace(reference, target_content_sha256=_sha256(60)),
            replace(reference, file_sha256=_sha256(61)),
            replace(reference, size=reference.size + 1),
        )
        for bad_reference in mismatches:
            with self.subTest(reference=bad_reference):
                with self.assertRaises(PipelineError):
                    validate_plan_receipt(
                        plan,
                        replace(receipt, plan=bad_reference),
                    )

    def test_receipt_check_ids_are_exactly_the_plan_requirement(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        receipt = _receipt(plan)

        missing = replace(receipt, checks=receipt.checks[:-1])
        extra_check = CheckResult(
            check_id="zz.extra-check",
            subject_sha256=plan.content_sha256,
            status="passed",
        )
        extra = replace(receipt, checks=(*receipt.checks, extra_check))
        for label, malformed in (("missing", missing), ("extra", extra)):
            with self.subTest(case=label):
                with self.assertRaises(PipelineError):
                    validate_plan_receipt(plan, malformed)

        duplicate_document = receipt.to_document()
        duplicate_document["checks"].append(
            copy.deepcopy(duplicate_document["checks"][-1])
        )
        duplicate_document = _resign(duplicate_document)
        with self.assertRaises(PipelineError):
            Receipt.from_document(duplicate_document)

    def test_receipt_every_check_subject_is_the_plan_content_identity(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        receipt = _receipt(plan)
        wrong = replace(receipt.checks[0], subject_sha256=_sha256(70))
        malformed = replace(receipt, checks=(wrong, *receipt.checks[1:]))

        with self.assertRaises(PipelineError):
            validate_plan_receipt(plan, malformed)

    def test_non_authorizing_stages_validate_receipt_but_not_state_root(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        for stage in ("check", "staged", "pre-commit", "historical"):
            receipt = _receipt(plan, stage=stage)
            state_root = _state_root(plan, receipt)
            with self.subTest(stage=stage):
                self.assertIsNone(validate_plan_receipt(plan, receipt))
                with self.assertRaises(PipelineError):
                    validate_receipt_state_root(plan, receipt, state_root)
                with self.assertRaises(PipelineError):
                    validate_transition_chain(spec, plan, receipt, state_root)

    def test_failed_post_commit_receipt_cannot_authorize_state_root(self) -> None:
        spec = _spec()
        plan = _plan(spec)
        receipt = _receipt(plan, status="failed")
        state_root = _state_root(plan, receipt)

        self.assertIsNone(validate_plan_receipt(plan, receipt))
        with self.assertRaises(PipelineError):
            validate_receipt_state_root(plan, receipt, state_root)

    def test_state_root_repeats_plan_and_transition_identity(self) -> None:
        _spec_value, plan, receipt, state_root = _chain()
        mismatches = (
            {"campaign_id": "different-campaign-v1"},
            {"transition_id": "different-transition-v1"},
        )
        for changes in mismatches:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    validate_receipt_state_root(
                        plan,
                        receipt,
                        replace(state_root, **changes),
                    )

    def test_state_root_plan_and_receipt_bind_raw_and_semantic_bytes(self) -> None:
        _spec_value, plan, receipt, state_root = _chain()
        alternate_path = replace(
            state_root.plan,
            path="campaign/evidence/alternate-plan-location.json",
        )
        wrong_plan_raw = replace(state_root.plan, file_sha256=_sha256(80))
        wrong_receipt_semantic = replace(
            state_root.receipt,
            target_content_sha256=_sha256(81),
        )
        wrong_receipt_size = replace(
            state_root.receipt,
            size=state_root.receipt.size + 1,
        )

        for changes in (
            {"plan": alternate_path},
            {"plan": wrong_plan_raw},
            {"receipt": wrong_receipt_semantic},
            {"receipt": wrong_receipt_size},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    validate_receipt_state_root(
                        plan,
                        receipt,
                        replace(state_root, **changes),
                    )

    def test_state_root_current_is_the_exact_planned_successor_reference(self) -> None:
        _spec_value, plan, receipt, state_root = _chain()
        mismatches = (
            replace(plan.successor, path="campaign/evidence/other-successor.json"),
            replace(plan.successor, file_sha256=_sha256(90)),
            replace(plan.successor, target_content_sha256=_sha256(91)),
            replace(plan.successor, size=plan.successor.size + 1),
        )

        for current in mismatches:
            with self.subTest(current=current):
                with self.assertRaises(PipelineError):
                    validate_receipt_state_root(
                        plan,
                        receipt,
                        replace(state_root, current=current),
                    )

    def test_public_validators_reject_model_subclasses(self) -> None:
        spec, plan, receipt, state_root = _chain()
        spec_subclass = _subclass_copy(spec, _SpecSubclass)
        plan_subclass = _subclass_copy(plan, _PlanSubclass)
        receipt_subclass = _subclass_copy(receipt, _ReceiptSubclass)
        root_subclass = _subclass_copy(state_root, _StateRootSubclass)

        with self.assertRaises(PipelineError):
            validate_spec_plan(spec_subclass, plan)  # type: ignore[arg-type]
        with self.assertRaises(PipelineError):
            validate_spec_plan(spec, plan_subclass)  # type: ignore[arg-type]
        with self.assertRaises(PipelineError):
            validate_plan_receipt(plan, receipt_subclass)  # type: ignore[arg-type]
        with self.assertRaises(PipelineError):
            validate_receipt_state_root(
                plan,
                receipt,
                root_subclass,  # type: ignore[arg-type]
            )

    def test_parsed_documents_reject_python_equality_aliases_before_validation(
        self,
    ) -> None:
        spec, plan, receipt, state_root = _chain()

        spec_document = spec.to_document()
        predecessor_size = spec_document["predecessor"]["size"]
        spec_document["predecessor"]["size"] = float(predecessor_size)
        with self.assertRaises(PipelineError):
            TransitionSpec.from_document(spec_document)

        root_document = state_root.to_document()
        root_document["generation"] = True
        with self.assertRaises(PipelineError):
            StateRoot.from_document(root_document)

        self.assertEqual(3, 3.0)
        self.assertEqual(1, True)
        self.assertIsNone(validate_plan_receipt(plan, receipt))


if __name__ == "__main__":
    unittest.main()
