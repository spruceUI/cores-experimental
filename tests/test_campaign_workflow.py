from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.core_pipeline_lib.campaign import (
    cli,
    run_and_store_check_receipt,
    store_reference_envelope,
    workflow,
)
from scripts.core_pipeline_lib.campaign.json_wire import (
    decode_identity_object,
    rendered_json_bytes,
)
from scripts.core_pipeline_lib.campaign.model import (
    MATRIX_AUTHORITY_ALLOWED_CHANGES,
    MATRIX_AUTHORITY_REQUIRED_CHECKS,
    TRANSITION_KIND,
    EvidenceRef,
    Receipt,
    StateRoot,
    TransitionPlan,
    TransitionSpec,
)
from scripts.core_pipeline_lib.campaign.store import CampaignStore
from scripts.core_pipeline_lib.campaign.transition import (
    PlannedMatrixAuthorityRefresh,
)
from scripts.core_pipeline_lib.checks import (
    CONTROLLED_ENVIRONMENT_KEYS,
    CheckReceipt as ProcessReceipt,
    CheckResult as ProcessResult,
    CheckStatus as ProcessStatus,
    CheckTier,
    ResultOrigin,
    checks_for_tier,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.source_bundle import pipeline_bundle_content_sha256


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bundle(files: dict[str, str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "files": files,
        "content_sha256": pipeline_bundle_content_sha256(files),
    }


def _write(root: Path, relative: str, raw: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o644)


def _tree(root: Path) -> tuple[tuple[str, bytes | None], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.read_bytes() if path.is_file() else None,
        )
        for path in sorted(root.rglob("*"))
    )


def _quick_process_receipt(subject: str) -> ProcessReceipt:
    results = tuple(
        ProcessResult(
            check_id=definition.check_id,
            tier=definition.tier,
            subject=subject,
            run_id=f"workflow-cycle-{index:03d}",
            status=ProcessStatus.PASSED,
            origin=ResultOrigin.LOCAL,
            argv=definition.render_argv(),
            executed_argv=definition.render_argv(),
            environment_keys=CONTROLLED_ENVIRONMENT_KEYS,
            duration_milliseconds=1,
            returncode=0,
            signal=None,
            timed_out=False,
            logs_complete=True,
            stdout="complete stdout\n",
            stderr="complete stderr\n",
            skipped_tests=definition.allowed_skips,
            structured_outputs=(),
            failure_kind=None,
            message=None,
        )
        for index, definition in enumerate(checks_for_tier(CheckTier.QUICK))
    )
    return ProcessReceipt(
        tier=CheckTier.QUICK,
        subject=subject,
        status=ProcessStatus.PASSED,
        origin=ResultOrigin.LOCAL,
        attestor_id=None,
        results=results,
    )


class _ProcessRunner:
    def __init__(self, receipt: ProcessReceipt) -> None:
        self.receipt = receipt
        self.subjects: list[str] = []

    def run_tier(self, tier, *, subject, parameters_by_check=None):
        self.subjects.append(subject)
        if tier is not CheckTier.QUICK or parameters_by_check is not None:
            raise AssertionError("workflow cycle runner arguments drifted")
        return self.receipt


class WorkflowFixture:
    spec_path = "manifests/transitions/pilot.json"
    engine_path = "manifests/engines/pilot.json"
    schema_path = "fixtures/matrix.schema.json"
    pointer_path = "campaigns/pilot/matrix.json"
    freeze_path = "campaigns/pilot/freeze.json"

    predecessor_raw = b"legacy predecessor bytes\n"
    candidate_raw = b"legacy successor bytes\n"
    freeze_raw = b"legacy freeze bytes\n"
    schema_raw = b'{"type":"object"}\n'
    process_raw = b'{"h4_process_receipt":"opaque"}\n'

    def __init__(self, root: Path, *, store_process_receipt: bool = True) -> None:
        self.root = root
        self.store = CampaignStore(root, workflow.DEFAULT_STATE_RELATIVE)
        self.engine_document = _bundle(
            {
                "scripts/core_pipeline.py": "1" * 64,
                "scripts/core_pipeline_lib/__init__.py": "2" * 64,
                "scripts/core_pipeline_lib/campaign/transition.py": "3" * 64,
                "scripts/core_pipeline_lib/campaign/workflow.py": "4" * 64,
            }
        )
        self.predecessor_ref = EvidenceRef(
            kind="matrix-pointer",
            path=self.pointer_path,
            file_sha256=_sha(self.predecessor_raw),
            target_content_sha256=_sha(b"predecessor semantic"),
            size=len(self.predecessor_raw),
        )
        self.freeze_ref = EvidenceRef(
            kind="phase-freeze",
            path=self.freeze_path,
            file_sha256=_sha(self.freeze_raw),
            target_content_sha256=_sha(b"freeze semantic"),
            size=len(self.freeze_raw),
        )
        self.spec = TransitionSpec(
            transition_id="pilot-transition",
            campaign_id="pilot-campaign",
            kind=TRANSITION_KIND,
            captured_at="2026-08-14T12:00:00Z",
            reason="Exercise the consolidated campaign workflow.",
            predecessor=self.predecessor_ref,
            phase_freeze=self.freeze_ref,
        )
        _write(root, self.spec_path, rendered_json_bytes(self.spec.to_document()))
        _write(root, self.engine_path, rendered_json_bytes(self.engine_document))
        _write(root, self.schema_path, self.schema_raw)
        _write(root, self.pointer_path, self.predecessor_raw)
        _write(root, self.freeze_path, self.freeze_raw)

        self.process_ref = self.store.reference_for(
            kind="check-log",
            raw=self.process_raw,
            target_content_sha256=None,
        )
        self.process_reference_path: str | None = None
        if store_process_receipt:
            self.store.create_or_verify(
                reference=self.process_ref,
                raw=self.process_raw,
            )
            process_envelope = store_reference_envelope(
                store=self.store,
                reference=self.process_ref,
            )
            self.process_reference_path = process_envelope.path

        self.patches = (
            mock.patch.object(workflow, "EXPECTED_SPEC_PATH", self.spec_path),
            mock.patch.object(
                workflow,
                "EXPECTED_ENGINE_BUNDLE_PATH",
                self.engine_path,
            ),
            mock.patch.object(workflow, "EXPECTED_SCHEMA_PATH", self.schema_path),
            mock.patch.object(
                workflow,
                "EXPECTED_SCHEMA_CANONICAL_SHA256",
                _sha(b"schema semantic"),
            ),
            mock.patch.object(
                workflow,
                "pipeline_source_bundle",
                side_effect=lambda: copy.deepcopy(self.engine_document),
            ),
            mock.patch.object(
                workflow,
                "plan_matrix_authority_refresh",
                side_effect=self.plan,
            ),
            mock.patch.object(
                workflow,
                "validate_matrix_authority_refresh",
                side_effect=self.validate,
            ),
            mock.patch.object(
                workflow,
                "legacy_matrix_compatibility_references",
                side_effect=self.aliases,
            ),
            mock.patch.object(
                workflow,
                "legacy_matrix_pointer_reference",
                side_effect=self.pointer,
            ),
        )
        for patch in self.patches:
            patch.start()

    def close(self) -> None:
        for patch in reversed(self.patches):
            patch.stop()

    def plan(
        self,
        *,
        spec: TransitionSpec,
        spec_ref: EvidenceRef,
        predecessor_raw: bytes,
        phase_freeze_raw: bytes,
        engine_bundle_ref: EvidenceRef,
        engine_bundle_document: object,
    ) -> PlannedMatrixAuthorityRefresh:
        if spec != self.spec:
            raise PipelineError("test planner spec drift")
        if predecessor_raw != self.predecessor_raw:
            raise PipelineError("test planner predecessor drift")
        if phase_freeze_raw != self.freeze_raw:
            raise PipelineError("test planner freeze drift")
        if engine_bundle_document != self.engine_document:
            raise PipelineError("test planner engine drift")
        successor = self.store.reference_for(
            kind="matrix-snapshot",
            raw=self.candidate_raw,
            target_content_sha256=_sha(b"successor semantic"),
        )
        pipeline_bundle = EvidenceRef(
            kind="pipeline-bundle",
            path=spec.phase_freeze.path,
            file_sha256=spec.phase_freeze.file_sha256,
            target_content_sha256=_sha(b"frozen pipeline semantic"),
            size=spec.phase_freeze.size,
        )
        plan = TransitionPlan(
            transition_id=spec.transition_id,
            campaign_id=spec.campaign_id,
            kind=spec.kind,
            captured_at=spec.captured_at,
            reason=spec.reason,
            spec=spec_ref,
            engine_bundle=engine_bundle_ref,
            predecessor=spec.predecessor,
            phase_freeze=spec.phase_freeze,
            pipeline_bundle=pipeline_bundle,
            successor=successor,
            allowed_changes=MATRIX_AUTHORITY_ALLOWED_CHANGES,
            preserved_projection_sha256=_sha(b"preserved projection"),
            required_checks=MATRIX_AUTHORITY_REQUIRED_CHECKS,
        )
        return PlannedMatrixAuthorityRefresh(
            plan=plan,
            candidate_raw=self.candidate_raw,
            changed_pointers=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        )

    def validate(self, result: PlannedMatrixAuthorityRefresh, **arguments) -> None:
        expected = self.plan(
            spec=arguments["spec"],
            spec_ref=arguments["spec_ref"],
            predecessor_raw=arguments["predecessor_raw"],
            phase_freeze_raw=arguments["phase_freeze_raw"],
            engine_bundle_ref=arguments["engine_bundle_ref"],
            engine_bundle_document=arguments["engine_bundle_document"],
        )
        if result != expected or arguments["schema_raw"] != self.schema_raw:
            raise PipelineError("test deep validation drift")

    def aliases(
        self,
        result: PlannedMatrixAuthorityRefresh,
    ) -> tuple[EvidenceRef, EvidenceRef]:
        common = {
            "file_sha256": _sha(result.candidate_raw),
            "target_content_sha256": result.plan.successor.target_content_sha256,
            "size": len(result.candidate_raw),
        }
        return (
            EvidenceRef(
                kind="matrix-snapshot",
                path="legacy/matrices/successor.json",
                **common,
            ),
            EvidenceRef(
                kind="matrix-cas",
                path=f"legacy/matrix-cas/{_sha(result.candidate_raw)}",
                **common,
            ),
        )

    def pointer(
        self,
        spec: TransitionSpec,
        result: PlannedMatrixAuthorityRefresh,
    ) -> EvidenceRef:
        return EvidenceRef(
            kind="matrix-pointer",
            path=spec.predecessor.path,
            file_sha256=_sha(result.candidate_raw),
            target_content_sha256=result.plan.successor.target_content_sha256,
            size=len(result.candidate_raw),
        )


class CampaignWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = WorkflowFixture(Path(self.temporary.name))
        self.addCleanup(self.fixture.close)
        self.clock = lambda: "2026-08-14T12:00:01Z"

    def stage(self) -> EvidenceRef:
        return workflow.stage_transition(
            self.fixture.store,
            process_receipt_ref=self.fixture.process_ref,
            clock=self.clock,
        )

    def test_predict_precedes_process_receipt_and_writes_no_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = WorkflowFixture(root, store_process_receipt=False)
            try:
                before = _tree(root)
                with self.assertRaisesRegex(PipelineError, "evidence object is missing"):
                    fixture.store.read_exact(fixture.process_ref)

                first = workflow.predict_transition(fixture.store)
                second = workflow.predict_transition(fixture.store)

                self.assertIsInstance(first, TransitionPlan)
                self.assertEqual(first.to_document(), second.to_document())
                self.assertEqual(fixture.spec.transition_id, first.transition_id)
                self.assertEqual(before, _tree(root))
                self.assertFalse((
                    root / workflow.DEFAULT_STATE_RELATIVE
                ).exists())
            finally:
                fixture.close()

    def test_h4_runner_subject_is_exact_predicted_plan_sha(self) -> None:
        plan = workflow.predict_transition(self.fixture.store)
        process_receipt = _quick_process_receipt(plan.content_sha256)
        runner = _ProcessRunner(process_receipt)
        stored = run_and_store_check_receipt(
            runner=runner,  # type: ignore[arg-type]
            store=self.fixture.store,
            tier=CheckTier.QUICK,
            subject=plan.content_sha256,
        )
        campaign_receipt = workflow.check_transition(
            self.fixture.store,
            process_receipt_ref=stored.receipt_ref,
            clock=self.clock,
        )

        self.assertEqual([plan.content_sha256], runner.subjects)
        self.assertEqual(plan.content_sha256, process_receipt.subject)
        self.assertEqual(plan.content_sha256, campaign_receipt.plan.target_content_sha256)
        self.assertTrue(all(
            check.evidence == (stored.receipt_ref,)
            for check in campaign_receipt.checks
        ))

    def test_check_is_read_only_and_binds_uniform_process_evidence(self) -> None:
        before = _tree(self.fixture.root)
        receipt = workflow.check_transition(
            self.fixture.store,
            process_receipt_ref=self.fixture.process_ref,
            clock=self.clock,
        )

        self.assertEqual("check", receipt.stage)
        self.assertEqual(MATRIX_AUTHORITY_REQUIRED_CHECKS, tuple(
            check.check_id for check in receipt.checks
        ))
        self.assertTrue(all(
            check.evidence == (self.fixture.process_ref,)
            for check in receipt.checks
        ))
        with self.assertRaisesRegex(PipelineError, "evidence object is missing"):
            self.fixture.store.read_exact(receipt.plan)
        self.assertEqual(before, _tree(self.fixture.root))

    def test_uniform_process_evidence_rejects_omission_and_substitution(self) -> None:
        receipt = workflow.check_transition(
            self.fixture.store,
            process_receipt_ref=self.fixture.process_ref,
            clock=self.clock,
        )
        substitute_raw = b"different process receipt\n"
        substitute = self.fixture.store.reference_for(
            kind="check-log",
            raw=substitute_raw,
            target_content_sha256=None,
        )
        cases = ((), (substitute,))
        for evidence in cases:
            checks = list(receipt.checks)
            checks[0] = replace(checks[0], evidence=evidence)
            forged = replace(receipt, checks=tuple(checks))
            with self.subTest(evidence=evidence), self.assertRaisesRegex(
                PipelineError,
                "same process receipt",
            ):
                workflow._require_receipt_evidence(  # type: ignore[attr-defined]
                    forged,
                    self.fixture.process_ref,
                )

    def test_stage_stops_before_pre_post_and_root_then_commit_verifies(self) -> None:
        staged_ref = self.stage()
        staged = Receipt.from_document(
            decode_identity_object(self.fixture.store.read_exact(staged_ref))
        )
        legacy_aliases = tuple(
            (reference.kind, reference.path)
            for reference in staged.outputs
            if reference.path.startswith("legacy/")
        )
        self.assertEqual(
            (
                (
                    "matrix-cas",
                    f"legacy/matrix-cas/{_sha(self.fixture.candidate_raw)}",
                ),
                ("matrix-snapshot", "legacy/matrices/successor.json"),
            ),
            legacy_aliases,
        )
        self.assertTrue({
            self.fixture.spec_path,
            self.fixture.engine_path,
            self.fixture.freeze_path,
        }.isdisjoint(reference.path for reference in staged.outputs))
        receipt_directory = (
            self.fixture.root
            / workflow.DEFAULT_STATE_RELATIVE
            / "objects"
            / "validation-receipt"
            / "sha256"
        )
        self.assertEqual(2, len(tuple(receipt_directory.glob("*/*"))))
        self.assertFalse((
            self.fixture.root
            / workflow.DEFAULT_STATE_RELATIVE
            / "objects"
            / "state-root"
        ).exists())
        self.assertEqual(self.fixture.predecessor_raw, (
            self.fixture.root / self.fixture.pointer_path
        ).read_bytes())

        commit_result, root_ref = workflow.commit_transition(
            self.fixture.store,
            staged_receipt_ref=staged_ref,
            clock=self.clock,
        )
        self.assertEqual(self.fixture.candidate_raw, commit_result.after.raw)
        self.assertEqual(self.fixture.candidate_raw, (
            self.fixture.root / self.fixture.pointer_path
        ).read_bytes())
        verified = workflow.verify_transition(
            self.fixture.store,
            state_root_ref=root_ref,
        )
        self.assertIsInstance(verified, StateRoot)
        self.assertEqual(root_ref.target_content_sha256, verified.content_sha256)

        common = {
            "file_sha256": _sha(self.fixture.candidate_raw),
            "target_content_sha256": verified.current.target_content_sha256,
            "size": len(self.fixture.candidate_raw),
        }
        alias_snapshot = EvidenceRef(
            kind="matrix-snapshot",
            path="legacy/matrices/successor.json",
            **common,
        )
        alias_cas = EvidenceRef(
            kind="matrix-cas",
            path=f"legacy/matrix-cas/{_sha(self.fixture.candidate_raw)}",
            **common,
        )
        for alias in (alias_snapshot, alias_cas):
            self.assertEqual(
                self.fixture.candidate_raw,
                self.fixture.store.read_exact(alias),
            )

    def test_post_evidence_failure_rolls_pointer_back(self) -> None:
        staged_ref = self.stage()
        original = workflow._stage_reference  # type: ignore[attr-defined]

        def fail_state_root(store, reference, raw, *, caller_path=False):
            if reference.kind == "state-root":
                raise PipelineError("injected StateRoot persistence failure")
            return original(
                store,
                reference,
                raw,
                caller_path=caller_path,
            )

        with mock.patch.object(
            workflow,
            "_stage_reference",
            side_effect=fail_state_root,
        ):
            with self.assertRaisesRegex(PipelineError, "injected StateRoot"):
                workflow.commit_transition(
                    self.fixture.store,
                    staged_receipt_ref=staged_ref,
                    clock=self.clock,
                )
        self.assertEqual(self.fixture.predecessor_raw, (
            self.fixture.root / self.fixture.pointer_path
        ).read_bytes())
        self.assertFalse((
            self.fixture.root
            / workflow.DEFAULT_STATE_RELATIVE
            / "objects"
            / "state-root"
        ).exists())

    def test_state_root_never_authorizes_without_live_successor(self) -> None:
        staged_ref = self.stage()
        _result, root_ref = workflow.commit_transition(
            self.fixture.store,
            staged_receipt_ref=staged_ref,
            clock=self.clock,
        )
        _write(
            self.fixture.root,
            self.fixture.pointer_path,
            self.fixture.predecessor_raw,
        )
        with self.assertRaises(PipelineError):
            workflow.verify_transition(
                self.fixture.store,
                state_root_ref=root_ref,
            )

    def test_historical_verify_uses_input_cas_and_rejects_cas_tamper(self) -> None:
        staged_ref = self.stage()
        _result, root_ref = workflow.commit_transition(
            self.fixture.store,
            staged_receipt_ref=staged_ref,
            clock=self.clock,
        )

        _write(self.fixture.root, self.fixture.spec_path, b"drifted spec\n")
        (self.fixture.root / self.fixture.engine_path).unlink()
        _write(self.fixture.root, self.fixture.freeze_path, b"drifted freeze\n")
        with mock.patch.object(
            workflow,
            "pipeline_source_bundle",
            side_effect=AssertionError("historical verify consulted live sources"),
        ):
            verified = workflow.verify_transition(
                self.fixture.store,
                state_root_ref=root_ref,
            )
        self.assertEqual(root_ref.target_content_sha256, verified.content_sha256)

        staged = Receipt.from_document(
            decode_identity_object(self.fixture.store.read_exact(staged_ref))
        )
        engine_cas = next(
            reference
            for reference in staged.outputs
            if reference.kind == "engine-bundle"
        )
        _write(self.fixture.root, engine_cas.path, b"tampered engine CAS\n")
        with self.assertRaises(PipelineError):
            workflow.verify_transition(
                self.fixture.store,
                state_root_ref=root_ref,
            )

    def test_locked_precommit_rejects_live_engine_drift(self) -> None:
        staged_ref = self.stage()
        files = dict(self.fixture.engine_document["files"])  # type: ignore[arg-type]
        files["scripts/core_pipeline_lib/campaign/workflow.py"] = "f" * 64
        mismatched = _bundle(files)
        with mock.patch.object(
            workflow,
            "pipeline_source_bundle",
            side_effect=[copy.deepcopy(self.fixture.engine_document), mismatched],
        ) as source_bundle:
            with self.assertRaisesRegex(PipelineError, "live pipeline sources"):
                workflow.commit_transition(
                    self.fixture.store,
                    staged_receipt_ref=staged_ref,
                    clock=self.clock,
                )
        self.assertEqual(2, source_bundle.call_count)
        self.assertEqual(self.fixture.predecessor_raw, (
            self.fixture.root / self.fixture.pointer_path
        ).read_bytes())

    def test_live_engine_mismatch_fails_closed_without_writes(self) -> None:
        before = _tree(self.fixture.root)
        mismatched = copy.deepcopy(self.fixture.engine_document)
        files = dict(mismatched["files"])  # type: ignore[arg-type]
        files["scripts/core_pipeline_lib/campaign/workflow.py"] = "f" * 64
        mismatched = _bundle(files)
        with mock.patch.object(
            workflow,
            "pipeline_source_bundle",
            return_value=mismatched,
        ):
            with self.assertRaisesRegex(PipelineError, "live pipeline sources"):
                workflow.check_transition(
                    self.fixture.store,
                    process_receipt_ref=self.fixture.process_ref,
                    clock=self.clock,
                )
        self.assertEqual(before, _tree(self.fixture.root))


class CampaignCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = WorkflowFixture(Path(self.temporary.name))
        self.addCleanup(self.fixture.close)

    def test_parser_exposes_only_exact_lifecycle_verbs(self) -> None:
        parser = cli.build_parser()
        choices = parser._subparsers._group_actions[0].choices
        self.assertEqual({"check", "stage", "commit", "verify"}, set(choices))

    def test_reference_envelopes_round_trip_check_staged_and_root_refs(self) -> None:
        process_path = self.fixture.process_reference_path
        self.assertIsInstance(process_path, str)
        process = cli._load_reference_document(  # type: ignore[attr-defined]
            self.fixture.store,
            process_path,  # type: ignore[arg-type]
            kind="check-log",
            label="process receipt",
        )
        self.assertEqual(self.fixture.process_ref, process)

        staged_ref = workflow.stage_transition(
            self.fixture.store,
            process_receipt_ref=process,
            clock=lambda: "2026-08-14T12:00:01Z",
        )
        staged_envelope = store_reference_envelope(
            store=self.fixture.store,
            reference=staged_ref,
        )
        self.assertEqual(
            staged_ref,
            cli._load_reference_document(  # type: ignore[attr-defined]
                self.fixture.store,
                staged_envelope.path,
                kind="validation-receipt",
                label="staged receipt",
            ),
        )

        _commit, root_ref = workflow.commit_transition(
            self.fixture.store,
            staged_receipt_ref=staged_ref,
            clock=lambda: "2026-08-14T12:00:02Z",
        )
        root_envelope = store_reference_envelope(
            store=self.fixture.store,
            reference=root_ref,
        )
        self.assertEqual(
            root_ref,
            cli._load_reference_document(  # type: ignore[attr-defined]
                self.fixture.store,
                root_envelope.path,
                kind="state-root",
                label="StateRoot",
            ),
        )

    def test_reference_envelope_rejects_tamper_collision_and_symlink(self) -> None:
        absent_raw = b"not yet durable\n"
        absent_target = self.fixture.store.reference_for(
            kind="check-log",
            raw=absent_raw,
            target_content_sha256=None,
        )
        absent_envelope_raw = rendered_json_bytes(absent_target.to_document())
        absent_envelope = self.fixture.store.reference_for(
            kind="artifact",
            raw=absent_envelope_raw,
            target_content_sha256=absent_target.content_sha256,
        )
        before_absent = _tree(self.fixture.root)
        with self.assertRaisesRegex(PipelineError, "evidence object is missing"):
            store_reference_envelope(
                store=self.fixture.store,
                reference=absent_target,
            )
        self.assertEqual(before_absent, _tree(self.fixture.root))
        with self.assertRaisesRegex(PipelineError, "evidence object is missing"):
            self.fixture.store.read_exact(absent_envelope)

        process_path = self.fixture.process_reference_path
        self.assertIsInstance(process_path, str)
        substitute_raw = b"substitute check receipt\n"
        substitute_ref = self.fixture.store.reference_for(
            kind="check-log",
            raw=substitute_raw,
            target_content_sha256=None,
        )
        self.fixture.store.create_or_verify(
            reference=substitute_ref,
            raw=substitute_raw,
        )
        _write(
            self.fixture.root,
            process_path,  # type: ignore[arg-type]
            rendered_json_bytes(substitute_ref.to_document()),
        )
        with self.assertRaisesRegex(PipelineError, "path is not canonical"):
            cli._load_reference_document(  # type: ignore[attr-defined]
                self.fixture.store,
                process_path,  # type: ignore[arg-type]
                kind="check-log",
                label="process receipt",
            )

        collision_raw = b"collision target\n"
        collision_target = self.fixture.store.reference_for(
            kind="check-log",
            raw=collision_raw,
            target_content_sha256=None,
        )
        self.fixture.store.create_or_verify(
            reference=collision_target,
            raw=collision_raw,
        )
        envelope_raw = rendered_json_bytes(collision_target.to_document())
        collision_envelope = self.fixture.store.reference_for(
            kind="artifact",
            raw=envelope_raw,
            target_content_sha256=collision_target.content_sha256,
        )
        _write(self.fixture.root, collision_envelope.path, b"foreign collision\n")
        with self.assertRaises(PipelineError):
            store_reference_envelope(
                store=self.fixture.store,
                reference=collision_target,
            )

        symlink_raw = b"symlink target\n"
        symlink_target = self.fixture.store.reference_for(
            kind="check-log",
            raw=symlink_raw,
            target_content_sha256=None,
        )
        self.fixture.store.create_or_verify(
            reference=symlink_target,
            raw=symlink_raw,
        )
        symlink_envelope_raw = rendered_json_bytes(symlink_target.to_document())
        symlink_envelope = self.fixture.store.reference_for(
            kind="artifact",
            raw=symlink_envelope_raw,
            target_content_sha256=symlink_target.content_sha256,
        )
        envelope_path = self.fixture.root / symlink_envelope.path
        envelope_path.parent.mkdir(parents=True, exist_ok=True)
        symlink_source = self.fixture.root / "symlink-envelope-source.json"
        symlink_source.write_bytes(symlink_envelope_raw)
        symlink_source.chmod(0o644)
        envelope_path.symlink_to(symlink_source)
        with self.assertRaises(PipelineError):
            store_reference_envelope(
                store=self.fixture.store,
                reference=symlink_target,
            )

    def test_check_consumes_reference_document_and_emits_plan_reference(self) -> None:
        plan_ref = EvidenceRef(
            kind="transition-plan",
            path="predicted/plan.json",
            file_sha256="1" * 64,
            target_content_sha256="2" * 64,
            size=1,
        )
        receipt = mock.Mock(plan=plan_ref)
        process_path = self.fixture.process_reference_path
        self.assertIsInstance(process_path, str)
        with (
            mock.patch.object(cli, "check_transition", return_value=receipt) as checked,
            mock.patch.object(cli, "_emit") as emitted,
        ):
            status = cli.main(
                [
                    "check",
                    "--process-receipt-ref",
                    process_path,
                ],
                store=self.fixture.store,
            )
        self.assertEqual(0, status)
        checked.assert_called_once_with(
            self.fixture.store,
            process_receipt_ref=self.fixture.process_ref,
        )
        emitted.assert_called_once_with(
            plan_ref,
            status="check passed; predicted plan reference (not staged)",
        )

    def test_reference_document_must_be_exact_and_name_expected_kind(self) -> None:
        wrong = replace(self.fixture.process_ref, kind="artifact")
        path = "resume/wrong-ref.json"
        _write(
            self.fixture.root,
            path,
            rendered_json_bytes(wrong.to_document()),
        )
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            status = cli.main(
                ["check", "--process-receipt-ref", path],
                store=self.fixture.store,
            )
        self.assertEqual(2, status)
        self.assertIn("kind must be check-log", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
