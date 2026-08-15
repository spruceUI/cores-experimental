from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import inspect
import unittest

from scripts.core_pipeline_lib.campaign.json_wire import canonical_json_sha256
from scripts.core_pipeline_lib.campaign.model import (
    CHECK_STATUSES as REGISTERED_CHECK_STATUSES,
    EVIDENCE_KINDS as REGISTERED_EVIDENCE_KINDS,
    VALIDATION_STAGES as REGISTERED_VALIDATION_STAGES,
    CheckResult,
    EvidenceRef,
    Receipt,
    StateRoot,
    TransitionPlan,
    TransitionSpec,
)
from scripts.core_pipeline_lib.errors import PipelineError


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

EVIDENCE_KINDS = (
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
)


class _StringSubclass(str):
    pass

DOCUMENT_KEYS = {
    EvidenceRef: {
        "schema_version",
        "kind",
        "path",
        "file_sha256",
        "target_content_sha256",
        "size",
        "content_sha256",
    },
    TransitionSpec: {
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
    },
    TransitionPlan: {
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
    },
    CheckResult: {
        "schema_version",
        "check_id",
        "subject_sha256",
        "status",
        "evidence",
        "message",
        "content_sha256",
    },
    Receipt: {
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
    },
    StateRoot: {
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
    },
}


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _evidence(
    kind: str,
    name: str,
    number: int,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=_sha256(number),
        target_content_sha256=_sha256(number + 1000),
        size=100 + number,
    )


def _spec() -> TransitionSpec:
    return TransitionSpec(
        transition_id="post-gambatte-authority-v1",
        campaign_id="core-build-campaign-v1",
        kind="matrix-authority-refresh-v1",
        captured_at="2026-08-14T12:34:56Z",
        reason="Refresh the matrix authority from the sealed Gambatte freeze — local only.",
        predecessor=_evidence("matrix-pointer", "predecessor-pointer", 1),
        phase_freeze=_evidence("phase-freeze", "phase-freeze", 2),
    )


def _plan() -> TransitionPlan:
    return TransitionPlan(
        transition_id="post-gambatte-authority-v1",
        campaign_id="core-build-campaign-v1",
        kind="matrix-authority-refresh-v1",
        captured_at="2026-08-14T12:34:56Z",
        reason="Refresh the matrix authority from the sealed Gambatte freeze — local only.",
        spec=_evidence("transition-spec", "transition-spec", 3),
        engine_bundle=_evidence("engine-bundle", "engine-bundle", 4),
        predecessor=_evidence("matrix-pointer", "predecessor-pointer", 1),
        phase_freeze=_evidence("phase-freeze", "phase-freeze", 2),
        pipeline_bundle=_evidence("pipeline-bundle", "pipeline-bundle", 5),
        successor=_evidence("matrix-snapshot", "successor-snapshot", 6),
        allowed_changes=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        preserved_projection_sha256=_sha256(7),
        required_checks=MATRIX_AUTHORITY_REQUIRED_CHECKS,
    )


def _checks(*, failed_id: str | None = None) -> tuple[CheckResult, ...]:
    rows: list[CheckResult] = []
    for offset, check_id in enumerate(MATRIX_AUTHORITY_REQUIRED_CHECKS, start=20):
        failed = check_id == failed_id
        rows.append(
            CheckResult(
                check_id=check_id,
                subject_sha256=_sha256(offset),
                status="failed" if failed else "passed",
                evidence=(),
                message="independent validation failed" if failed else None,
            )
        )
    return tuple(rows)


def _receipt() -> Receipt:
    return Receipt(
        transition_id="post-gambatte-authority-v1",
        plan=_evidence("transition-plan", "transition-plan", 8),
        stage="check",
        status="passed",
        started_at="2026-08-14T12:35:00Z",
        completed_at="2026-08-14T12:35:01Z",
        checks=_checks(),
        outputs=(
            _evidence("matrix-cas", "successor-cas", 9),
            _evidence("matrix-snapshot", "successor-snapshot", 6),
        ),
    )


def _state_root(*, generation: int = 2) -> StateRoot:
    return StateRoot(
        campaign_id="core-build-campaign-v1",
        generation=generation,
        transition_id="post-gambatte-authority-v1",
        plan=_evidence("transition-plan", "transition-plan", 8),
        receipt=_evidence("validation-receipt", "validation-receipt", 10),
        current=_evidence("matrix-snapshot", "successor-snapshot", 6),
        previous=(
            None
            if generation == 1
            else _evidence("state-root", "predecessor-state-root", 11)
        ),
    )


def _all_records() -> tuple[object, ...]:
    return (
        _evidence("artifact", "artifact", 12),
        _spec(),
        _plan(),
        CheckResult(
            check_id="matrix.schema",
            subject_sha256=_sha256(13),
            status="passed",
        ),
        _receipt(),
        _state_root(),
    )


def _resign(document: dict[str, object]) -> dict[str, object]:
    resigned = copy.deepcopy(document)
    resigned.pop("content_sha256", None)
    resigned["content_sha256"] = canonical_json_sha256(resigned)
    return resigned


class CampaignModelTests(unittest.TestCase):
    def test_all_records_are_frozen_slotted_values(self) -> None:
        fields_to_change = (
            "path",
            "reason",
            "reason",
            "status",
            "status",
            "generation",
        )

        for record, field_name in zip(_all_records(), fields_to_change, strict=True):
            with self.subTest(record_type=type(record).__name__):
                self.assertFalse(hasattr(record, "__dict__"))
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, field_name, "tampered")

    def test_all_documents_have_exact_keys_derived_digests_and_roundtrip(
        self,
    ) -> None:
        for record in _all_records():
            with self.subTest(record_type=type(record).__name__):
                document = record.to_document()
                identity = copy.deepcopy(document)
                content_sha256 = identity.pop("content_sha256")

                self.assertEqual(set(document), DOCUMENT_KEYS[type(record)])
                self.assertEqual(document["schema_version"], 1)
                self.assertEqual(content_sha256, canonical_json_sha256(identity))
                self.assertEqual(record.content_sha256, content_sha256)
                self.assertNotIn(
                    "content_sha256",
                    inspect.signature(type(record)).parameters,
                )
                self.assertEqual(type(record).from_document(document), record)

    def test_from_document_is_closed_and_authenticates_outer_digest(self) -> None:
        for record in _all_records():
            record_type = type(record)
            document = record.to_document()
            removable_key = next(
                key
                for key in document
                if key not in {"schema_version", "content_sha256"}
            )

            extra = copy.deepcopy(document)
            extra["unexpected"] = None
            extra = _resign(extra)

            missing = copy.deepcopy(document)
            del missing[removable_key]
            missing = _resign(missing)

            stale = copy.deepcopy(document)
            stale["schema_version"] = 2

            wrong_digest = copy.deepcopy(document)
            wrong_digest["content_sha256"] = (
                "0" * 64
                if document["content_sha256"] != "0" * 64
                else "1" * 64
            )

            for label, malformed in (
                ("extra", extra),
                ("missing", missing),
                ("stale", stale),
                ("wrong-digest", wrong_digest),
                ("not-a-document", []),
            ):
                with self.subTest(record_type=record_type.__name__, case=label):
                    with self.assertRaises(PipelineError):
                        record_type.from_document(malformed)

    def test_document_conversion_is_independent_at_every_nested_level(self) -> None:
        plan = _plan()
        source = plan.to_document()
        parsed = TransitionPlan.from_document(source)
        untouched = plan.to_document()

        source["predecessor"]["path"] = "campaign/evidence/attacker.json"
        source["allowed_changes"].append("/attacker")
        source["required_checks"].append("attacker.check")

        self.assertEqual(parsed, plan)
        self.assertEqual(parsed.to_document(), untouched)

        returned = parsed.to_document()
        returned["phase_freeze"]["path"] = "campaign/evidence/mutated.json"
        returned["allowed_changes"].clear()
        self.assertEqual(parsed.to_document(), untouched)

    def test_nested_documents_remain_closed_and_independently_authenticated(
        self,
    ) -> None:
        plan_document = _plan().to_document()
        predecessor = copy.deepcopy(plan_document["predecessor"])
        predecessor["unexpected"] = "forbidden"
        plan_document["predecessor"] = _resign(predecessor)
        plan_document = _resign(plan_document)

        with self.assertRaises(PipelineError):
            TransitionPlan.from_document(plan_document)

        stale_nested = _plan().to_document()
        stale_nested["predecessor"]["path"] = (
            "campaign/evidence/different-but-canonical.json"
        )
        stale_nested = _resign(stale_nested)
        with self.assertRaises(PipelineError):
            TransitionPlan.from_document(stale_nested)

    def test_evidence_reference_has_closed_kinds_and_exact_identity_types(
        self,
    ) -> None:
        for index, kind in enumerate(EVIDENCE_KINDS, start=100):
            with self.subTest(kind=kind):
                reference = _evidence(kind, kind, index)
                self.assertEqual(
                    EvidenceRef.from_document(reference.to_document()),
                    reference,
                )

        base = _evidence("artifact", "artifact", 200)
        invalid_replacements = (
            {"kind": "unknown-evidence-kind"},
            {"path": "../escape.json"},
            {"path": "/absolute/path.json"},
            {"path": "campaign/./artifact.json"},
            {"file_sha256": "A" * 64},
            {"file_sha256": "not-a-digest"},
            {"target_content_sha256": "A" * 64},
            {"target_content_sha256": 1},
            {"size": -1},
            {"size": True},
        )

        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(base, **changes)

    def test_registered_policy_vocabularies_are_exactly_closed(self) -> None:
        self.assertEqual(REGISTERED_EVIDENCE_KINDS, frozenset(EVIDENCE_KINDS))
        self.assertEqual(
            REGISTERED_VALIDATION_STAGES,
            frozenset({"check", "staged", "pre-commit", "post-commit", "historical"}),
        )
        self.assertEqual(REGISTERED_CHECK_STATUSES, frozenset({"passed", "failed"}))

    def test_matrix_object_kinds_do_not_widen_existing_role_gates(self) -> None:
        for index, kind in enumerate(
            ("matrix-cell", "matrix-shard", "matrix-root"), start=220
        ):
            reference = _evidence(kind, kind, index)
            adversaries = (
                (_spec(), {"predecessor": reference}),
                (_spec(), {"phase_freeze": reference}),
                (_plan(), {"spec": reference}),
                (_plan(), {"engine_bundle": reference}),
                (_plan(), {"predecessor": reference}),
                (_plan(), {"phase_freeze": reference}),
                (_plan(), {"pipeline_bundle": reference}),
                (_plan(), {"successor": reference}),
                (_receipt(), {"plan": reference}),
                (_state_root(), {"plan": reference}),
                (_state_root(), {"receipt": reference}),
                (_state_root(), {"current": reference}),
            )
            for record, changes in adversaries:
                with self.subTest(
                    kind=kind,
                    record=type(record).__name__,
                    field=next(iter(changes)),
                ):
                    with self.assertRaises(PipelineError):
                        replace(record, **changes)

    def test_model_strings_are_utf8_and_paths_reject_nul(self) -> None:
        reference = _evidence("artifact", "artifact", 206)
        for changes in (
            {"path": "campaign/evidence/\ud800.json"},
            {"path": "campaign/evidence/nul\x00.json"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(reference, **changes)
        with self.assertRaises(PipelineError):
            replace(_spec(), reason="reason \udfff")
        with self.assertRaises(PipelineError):
            CheckResult(
                check_id="matrix.schema",
                subject_sha256=_sha256(207),
                status="failed",
                message="failure \ud800",
            )

    def test_models_reject_string_subclass_equality_aliases(self) -> None:
        reference = _evidence("artifact", "artifact", 203)
        with self.assertRaises(PipelineError):
            replace(reference, kind=_StringSubclass("artifact"))
        with self.assertRaises(PipelineError):
            replace(_spec(), kind=_StringSubclass("matrix-authority-refresh-v1"))
        with self.assertRaises(PipelineError):
            replace(
                CheckResult(
                    check_id="matrix.schema",
                    subject_sha256=_sha256(204),
                    status="passed",
                ),
                status=_StringSubclass("passed"),
            )
        with self.assertRaises(PipelineError):
            replace(_receipt(), stage=_StringSubclass("check"))

        document = reference.to_document()
        kind = document.pop("kind")
        document[_StringSubclass("kind")] = kind
        with self.assertRaises(PipelineError):
            EvidenceRef.from_document(document)

        spec_document = _spec().to_document()
        spec_document["publication"] = _StringSubclass("disabled")
        with self.assertRaises(PipelineError):
            TransitionSpec.from_document(spec_document)

    def test_raw_evidence_uses_explicit_null_semantic_target(self) -> None:
        raw = EvidenceRef(
            kind="artifact",
            path="campaign/evidence/raw-build-log.txt",
            file_sha256=_sha256(201),
            target_content_sha256=None,
            size=0,
        )

        self.assertIsNone(raw.to_document()["target_content_sha256"])
        self.assertEqual(EvidenceRef.from_document(raw.to_document()), raw)

        check = CheckResult(
            check_id="matrix.schema",
            subject_sha256=_sha256(201),
            status="passed",
            evidence=(raw,),
        )
        receipt = replace(_receipt(), outputs=(raw,))
        self.assertEqual(CheckResult.from_document(check.to_document()), check)
        self.assertEqual(Receipt.from_document(receipt.to_document()), receipt)

    def test_transition_spec_fixes_policy_timestamp_and_local_only_domain(
        self,
    ) -> None:
        spec = _spec()
        self.assertTrue(spec.to_document()["local_only"])
        self.assertEqual(spec.to_document()["publication"], "disabled")

        invalid_replacements = (
            {"kind": "different-transition-v1"},
            {"captured_at": "2026-08-14T12:34:56+00:00"},
            {"captured_at": "2026-08-14T12:34:56.000Z"},
            {"captured_at": "2026-02-30T12:34:56Z"},
            {"reason": ""},
            {"reason": " padded reason "},
        )
        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(spec, **changes)

        for key, forbidden in (("local_only", False), ("publication", "enabled")):
            document = spec.to_document()
            document[key] = forbidden
            document = _resign(document)
            with self.subTest(key=key):
                with self.assertRaises(PipelineError):
                    TransitionSpec.from_document(document)

    def test_authoritative_nested_references_require_semantic_identity(
        self,
    ) -> None:
        raw_only = EvidenceRef(
            kind="matrix-pointer",
            path="campaign/evidence/unbound-pointer.json",
            file_sha256=_sha256(202),
            target_content_sha256=None,
            size=10,
        )

        with self.assertRaises(PipelineError):
            replace(_spec(), predecessor=raw_only)

    def test_transition_plan_requires_the_exact_code_owned_policy(self) -> None:
        plan = _plan()
        self.assertEqual(plan.allowed_changes, MATRIX_AUTHORITY_ALLOWED_CHANGES)
        self.assertEqual(plan.required_checks, MATRIX_AUTHORITY_REQUIRED_CHECKS)

        invalid_replacements = (
            {"allowed_changes": tuple(reversed(MATRIX_AUTHORITY_ALLOWED_CHANGES))},
            {"allowed_changes": MATRIX_AUTHORITY_ALLOWED_CHANGES[:-1]},
            {
                "allowed_changes": (
                    *MATRIX_AUTHORITY_ALLOWED_CHANGES,
                    MATRIX_AUTHORITY_ALLOWED_CHANGES[-1],
                )
            },
            {
                "allowed_changes": (
                    *MATRIX_AUTHORITY_ALLOWED_CHANGES[:-1],
                    "/invalid~pointer",
                )
            },
            {"required_checks": tuple(reversed(MATRIX_AUTHORITY_REQUIRED_CHECKS))},
            {"required_checks": MATRIX_AUTHORITY_REQUIRED_CHECKS[:-1]},
            {
                "required_checks": (
                    *MATRIX_AUTHORITY_REQUIRED_CHECKS,
                    MATRIX_AUTHORITY_REQUIRED_CHECKS[-1],
                )
            },
            {"preserved_projection_sha256": "A" * 64},
        )

        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(plan, **changes)

    def test_transition_plan_rejects_bool_aliases_in_sequence_documents(self) -> None:
        document = _plan().to_document()
        document["required_checks"] = [False]
        document = _resign(document)

        with self.assertRaises(PipelineError):
            TransitionPlan.from_document(document)

    def test_check_result_has_closed_status_and_sorted_unique_evidence(self) -> None:
        evidence = (
            _evidence("artifact", "artifact", 210),
            _evidence("engine-bundle", "engine", 211),
        )
        passed = CheckResult(
            check_id="matrix.schema",
            subject_sha256=_sha256(212),
            status="passed",
            evidence=evidence,
        )
        failed = replace(
            passed,
            status="failed",
            message="schema validation failed",
        )
        self.assertEqual(CheckResult.from_document(passed.to_document()), passed)
        self.assertEqual(CheckResult.from_document(failed.to_document()), failed)

        invalid_replacements = (
            {"status": "skipped"},
            {"check_id": ""},
            {"subject_sha256": "A" * 64},
            {"evidence": tuple(reversed(evidence))},
            {"evidence": (evidence[0], evidence[0])},
        )
        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(passed, **changes)

    def test_receipt_requires_sorted_unique_checks_and_consistent_status(
        self,
    ) -> None:
        receipt = _receipt()
        failed_checks = _checks(failed_id="matrix.schema")
        failed = replace(receipt, status="failed", checks=failed_checks)

        self.assertEqual(Receipt.from_document(receipt.to_document()), receipt)
        self.assertEqual(Receipt.from_document(failed.to_document()), failed)

        invalid_replacements = (
            {"stage": "apply"},
            {"status": "skipped"},
            {"started_at": "2026-08-14T12:35:00.000Z"},
            {"completed_at": "2026-08-14T12:34:59Z"},
            {"checks": tuple(reversed(receipt.checks))},
            {"checks": (*receipt.checks, receipt.checks[-1])},
            {"status": "passed", "checks": failed_checks},
            {"status": "failed", "checks": receipt.checks},
        )
        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(receipt, **changes)

    def test_receipt_supports_only_the_closed_stage_vocabulary(self) -> None:
        receipt = _receipt()
        for stage in ("check", "staged", "pre-commit", "post-commit", "historical"):
            with self.subTest(stage=stage):
                staged = replace(receipt, stage=stage)
                self.assertEqual(Receipt.from_document(staged.to_document()), staged)

    def test_state_root_generation_controls_previous_identity(self) -> None:
        first = _state_root(generation=1)
        second = _state_root(generation=2)
        self.assertIsNone(first.previous)
        self.assertIsNotNone(second.previous)
        self.assertEqual(StateRoot.from_document(first.to_document()), first)
        self.assertEqual(StateRoot.from_document(second.to_document()), second)

        invalid_replacements = (
            {"generation": 0},
            {"generation": True},
            {"generation": 1, "previous": second.previous},
            {"generation": 2, "previous": None},
        )
        for changes in invalid_replacements:
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(second, **changes)

        with self.assertRaises(PipelineError):
            replace(
                second,
                current=_evidence("artifact", "not-a-matrix-state", 205),
            )

    def test_every_semantic_envelope_is_local_only_and_non_publishable(self) -> None:
        records = (_spec(), _plan(), _receipt(), _state_root())
        for record in records:
            record_type = type(record)
            document = record.to_document()
            self.assertIs(document["local_only"], True)
            self.assertEqual(document["publication"], "disabled")

            for key, forbidden in (
                ("local_only", 1),
                ("local_only", False),
                ("publication", "enabled"),
            ):
                malformed = copy.deepcopy(document)
                malformed[key] = forbidden
                malformed = _resign(malformed)
                with self.subTest(record_type=record_type.__name__, key=key):
                    with self.assertRaises(PipelineError):
                        record_type.from_document(malformed)


if __name__ == "__main__":
    unittest.main()
