from __future__ import annotations

import ast
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from scripts.core_pipeline_lib.campaign import authority_commit
from scripts.core_pipeline_lib.campaign.authority_staging import (
    StagedAuthorityStageV1,
)
from scripts.core_pipeline_lib.campaign.json_wire import (
    decode_identity_object,
    rendered_json_bytes,
)
from scripts.core_pipeline_lib.campaign.model import (
    CheckResult,
    EvidenceRef,
    Receipt,
    StateRoot,
)
from scripts.core_pipeline_lib.campaign.phase_freeze import (
    CAMPAIGN_STATE_RELATIVE,
)
from scripts.core_pipeline_lib.campaign.store import (
    CampaignStore,
    TransactionView,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "authority_commit.py"
)
CAMPAIGN_ID = "authority-commit-campaign"
TRANSITION_ID = "authority-commit-transition-v1"
POINTER_PATH = (
    ".local-e2e/campaigns/authority-commit-campaign/campaign-matrix.json"
)


def _sorted_refs(*references: EvidenceRef) -> tuple[EvidenceRef, ...]:
    return tuple(sorted(references, key=lambda item: (item.kind, item.path)))


def _publish(
    store: CampaignStore,
    *,
    kind: str,
    raw: bytes,
    target: str | None = None,
) -> EvidenceRef:
    reference = store.reference_for(
        kind=kind,
        raw=raw,
        target_content_sha256=target,
    )
    store.create_or_verify(reference=reference, raw=raw)
    return reference


def _pointer(raw: bytes, *, target: str) -> EvidenceRef:
    return EvidenceRef(
        kind="matrix-pointer",
        path=POINTER_PATH,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=target,
        size=len(raw),
    )


def _write_pointer(root: Path, raw: bytes) -> None:
    path = root / POINTER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(0o644)


def _record(
    store: CampaignStore,
    reference: EvidenceRef,
    record_type: type[Receipt] | type[StateRoot],
    *,
    label: str,
) -> Receipt | StateRoot:
    return record_type.from_document(
        decode_identity_object(store.read_exact(reference), label=label)
    )


def _forge_staged(
    *,
    planned: object,
    receipt: Receipt,
    receipt_reference: EvidenceRef,
    historical_transition: object,
) -> StagedAuthorityStageV1:
    result = object.__new__(StagedAuthorityStageV1)
    object.__setattr__(result, "planned", planned)
    object.__setattr__(result, "receipt", receipt)
    object.__setattr__(result, "receipt_reference", receipt_reference)
    object.__setattr__(result, "process_receipt", None)
    object.__setattr__(result, "historical_transition", historical_transition)
    return result


class _DeepLoadController:
    def __init__(
        self,
        *,
        staged: StagedAuthorityStageV1,
        staged_receipt_ref: EvidenceRef,
        prior_state_root_ref: EvidenceRef,
        historical_transition: object,
        retained: tuple[EvidenceRef, ...],
    ) -> None:
        self.staged = staged
        self.staged_receipt_ref = staged_receipt_ref
        self.prior_state_root_ref = prior_state_root_ref
        self.historical_transition = historical_transition
        self.retained = retained
        self.calls: list[tuple[bool, object, object]] = []
        self.live_call_count = 0
        self.fail_live_call: int | None = None

    def reset(self, *, fail_live_call: int | None = None) -> None:
        self.calls.clear()
        self.live_call_count = 0
        self.fail_live_call = fail_live_call

    def __call__(
        self,
        store: CampaignStore,
        staged_receipt_ref: EvidenceRef,
        *,
        require_live_engine: bool,
        reader=None,
        historical_root_loader=None,
    ) -> StagedAuthorityStageV1:
        exact_reader = store if reader is None else reader
        self.calls.append(
            (require_live_engine, exact_reader, historical_root_loader)
        )
        if staged_receipt_ref != self.staged_receipt_ref:
            raise PipelineError("deep loader received a different staged token")
        if not callable(historical_root_loader):
            raise PipelineError("deep loader omitted the no-lock H3 loader")
        for reference in self.retained:
            exact_reader.read_exact(reference)
        historical = historical_root_loader(
            exact_reader,
            self.prior_state_root_ref,
        )
        if historical is not self.historical_transition:
            raise PipelineError("deep loader returned different H3 ancestry")
        if require_live_engine:
            self.live_call_count += 1
            if self.live_call_count == self.fail_live_call:
                raise PipelineError("live authority source differs")
        return self.staged


@contextmanager
def _tiny_authority_cycle():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        store = CampaignStore(root, CAMPAIGN_STATE_RELATIVE)
        predecessor_raw = b'{"matrix":"predecessor"}\n'
        successor_raw = b'{"matrix":"successor"}\n'
        predecessor_target = sha256_bytes(b"predecessor semantic")
        successor_target = sha256_bytes(b"successor semantic")
        predecessor_pointer = _pointer(
            predecessor_raw,
            target=predecessor_target,
        )
        successor_pointer = _pointer(
            successor_raw,
            target=successor_target,
        )
        _write_pointer(root, predecessor_raw)

        predecessor_matrix_ref = _publish(
            store,
            kind="matrix-snapshot",
            raw=predecessor_raw,
            target=predecessor_target,
        )
        successor_matrix_ref = _publish(
            store,
            kind="matrix-snapshot",
            raw=successor_raw,
            target=successor_target,
        )
        prior_plan_ref = _publish(
            store,
            kind="transition-plan",
            raw=b"prior plan\n",
            target=sha256_bytes(b"prior plan semantic"),
        )
        prior_post_ref = _publish(
            store,
            kind="validation-receipt",
            raw=b"prior post receipt\n",
            target=sha256_bytes(b"prior post semantic"),
        )
        prior_state_root = StateRoot(
            campaign_id=CAMPAIGN_ID,
            generation=1,
            transition_id="authority-prior-transition-v1",
            plan=prior_plan_ref,
            receipt=prior_post_ref,
            current=predecessor_matrix_ref,
            previous=None,
        )
        prior_root_raw = rendered_json_bytes(prior_state_root.to_document())
        prior_state_root_ref = _publish(
            store,
            kind="state-root",
            raw=prior_root_raw,
            target=prior_state_root.content_sha256,
        )

        plan_ref = _publish(
            store,
            kind="transition-plan",
            raw=b"combined authority plan\n",
            target=sha256_bytes(b"combined authority semantic"),
        )
        h4_ref = _publish(
            store,
            kind="check-log",
            raw=b"combined H4 receipt\n",
        )
        staged_member_ref = _publish(
            store,
            kind="artifact",
            raw=b"staged-only retained member\n",
        )
        h3_member_ref = _publish(
            store,
            kind="artifact",
            raw=b"H3-only retained member\n",
        )
        plan_target = plan_ref.target_content_sha256
        assert plan_target is not None
        check = CheckResult(
            check_id="campaign.plan.identity",
            subject_sha256=plan_target,
            status="passed",
            evidence=(h4_ref,),
        )
        staged_receipt = Receipt(
            transition_id=TRANSITION_ID,
            plan=plan_ref,
            stage="staged",
            status="passed",
            started_at="2026-08-15T04:05:00Z",
            completed_at="2026-08-15T04:05:00Z",
            checks=(check,),
            outputs=_sorted_refs(
                h4_ref,
                plan_ref,
                prior_state_root_ref,
                staged_member_ref,
                successor_matrix_ref,
            ),
        )
        staged_raw = rendered_json_bytes(staged_receipt.to_document())
        staged_receipt_ref = _publish(
            store,
            kind="validation-receipt",
            raw=staged_raw,
            target=staged_receipt.content_sha256,
        )
        staged_required = _sorted_refs(
            staged_receipt_ref,
            *staged_receipt.outputs,
        )
        historical_required = _sorted_refs(
            h3_member_ref,
            prior_plan_ref,
            prior_post_ref,
            prior_state_root_ref,
            predecessor_matrix_ref,
        )
        historical_transition = SimpleNamespace(
            state_root=prior_state_root,
            state_root_ref=prior_state_root_ref,
            current_pointer_ref=predecessor_pointer,
            required_objects=historical_required,
        )
        legacy_matrix = SimpleNamespace(
            predecessor_pointer=predecessor_pointer,
            successor_pointer=successor_pointer,
            canonical_object=successor_matrix_ref,
        )
        plan = SimpleNamespace(
            campaign_id=CAMPAIGN_ID,
            transition_id=TRANSITION_ID,
            current_state_root=prior_state_root_ref,
            legacy_matrix=legacy_matrix,
        )
        planned = SimpleNamespace(
            plan=plan,
            plan_reference=plan_ref,
            predecessor_matrix=None,
            legacy_raw=successor_raw,
        )
        staged = _forge_staged(
            planned=planned,
            receipt=staged_receipt,
            receipt_reference=staged_receipt_ref,
            historical_transition=historical_transition,
        )
        retained = authority_commit._sorted_unique_refs(
            *staged_required,
            *historical_required,
        )
        controller = _DeepLoadController(
            staged=staged,
            staged_receipt_ref=staged_receipt_ref,
            prior_state_root_ref=prior_state_root_ref,
            historical_transition=historical_transition,
            retained=retained,
        )

        def load_h3(
            exact_store: CampaignStore,
            *,
            reader,
            state_root_ref: EvidenceRef,
        ):
            if exact_store is not store or state_root_ref != prior_state_root_ref:
                raise PipelineError("synthetic H3 loader identity drifted")
            for reference in historical_required:
                reader.read_exact(reference)
            return historical_transition

        with ExitStack() as patches:
            patches.enter_context(
                mock.patch.object(
                    StagedAuthorityStageV1,
                    "predecessor_raw",
                    new_callable=mock.PropertyMock,
                    return_value=predecessor_raw,
                )
            )
            patches.enter_context(
                mock.patch.object(
                    StagedAuthorityStageV1,
                    "staged_required_objects",
                    new_callable=mock.PropertyMock,
                    return_value=staged_required,
                )
            )
            deep_mock = patches.enter_context(
                mock.patch.object(
                    authority_commit,
                    "load_staged_authority_plan",
                    side_effect=controller,
                )
            )
            h3_mock = patches.enter_context(
                mock.patch.object(
                    authority_commit,
                    "load_historical_transition",
                    side_effect=load_h3,
                )
            )
            yield SimpleNamespace(
                root=root,
                store=store,
                staged=staged,
                staged_raw=staged_raw,
                staged_receipt_ref=staged_receipt_ref,
                staged_required=staged_required,
                historical_required=historical_required,
                staged_member_ref=staged_member_ref,
                h3_member_ref=h3_member_ref,
                predecessor_pointer=predecessor_pointer,
                predecessor_raw=predecessor_raw,
                successor_pointer=successor_pointer,
                successor_raw=successor_raw,
                successor_matrix_ref=successor_matrix_ref,
                prior_state_root_ref=prior_state_root_ref,
                controller=controller,
                deep_mock=deep_mock,
                h3_mock=h3_mock,
            )


class CampaignAuthorityCommitTests(unittest.TestCase):
    def assert_pointer(self, cycle, reference: EvidenceRef, raw: bytes) -> None:
        selected = cycle.store.read_pointer(reference)
        self.assertIsNotNone(selected)
        self.assertEqual(reference, selected.reference)
        self.assertEqual(raw, selected.raw)

    def test_pointer_last_commit_rollback_and_historical_verification(self) -> None:
        with _tiny_authority_cycle() as cycle:
            wrong_kind = _publish(
                cycle.store,
                kind="artifact",
                raw=cycle.staged_raw,
                target=cycle.staged.receipt.content_sha256,
            )
            cycle.controller.reset()
            with self.assertRaisesRegex(PipelineError, "validation-receipt"):
                authority_commit.commit_authority_plan(
                    cycle.store,
                    staged_receipt_ref=wrong_kind,
                )
            self.assertEqual([], cycle.controller.calls)
            self.assert_pointer(
                cycle,
                cycle.predecessor_pointer,
                cycle.predecessor_raw,
            )
            collision = replace(
                cycle.staged_member_ref,
                file_sha256="f" * 64,
            )
            with self.assertRaisesRegex(PipelineError, "collides"):
                authority_commit._sorted_unique_refs(
                    cycle.staged_member_ref,
                    collision,
                )
            with mock.patch.object(
                StagedAuthorityStageV1,
                "staged_required_objects",
                new_callable=mock.PropertyMock,
                return_value=_sorted_refs(
                    *cycle.staged_required,
                    cycle.successor_pointer,
                ),
            ):
                with self.assertRaisesRegex(PipelineError, "contains a pointer"):
                    authority_commit._transaction_required_objects(cycle.staged)

            for missing_ref in (
                cycle.staged_member_ref,
                cycle.h3_member_ref,
            ):
                missing_raw = cycle.store.read_exact(missing_ref)
                missing_path = cycle.root / missing_ref.path
                original_pointer_transaction = cycle.store.pointer_transaction

                def remove_required_then_build(**kwargs):
                    missing_path.unlink()
                    return original_pointer_transaction(**kwargs)

                cycle.controller.reset()
                try:
                    with (
                        self.subTest(missing_kind=missing_ref.kind),
                        mock.patch.object(
                            cycle.store,
                            "pointer_transaction",
                            side_effect=remove_required_then_build,
                        ),
                        self.assertRaisesRegex(PipelineError, "missing"),
                    ):
                        authority_commit.commit_authority_plan(
                            cycle.store,
                            staged_receipt_ref=cycle.staged_receipt_ref,
                            clock=lambda: "2026-08-15T04:05:30Z",
                        )
                finally:
                    cycle.store.create_or_verify(
                        reference=missing_ref,
                        raw=missing_raw,
                    )
                self.assertEqual(1, len(cycle.controller.calls))
                self.assert_pointer(
                    cycle,
                    cycle.predecessor_pointer,
                    cycle.predecessor_raw,
                )

            cycle.controller.reset(fail_live_call=2)
            with self.assertRaisesRegex(PipelineError, "source differs"):
                authority_commit.commit_authority_plan(
                    cycle.store,
                    staged_receipt_ref=cycle.staged_receipt_ref,
                    clock=lambda: "2026-08-15T04:06:00Z",
                )
            self.assertEqual(2, len(cycle.controller.calls))
            self.assert_pointer(
                cycle,
                cycle.predecessor_pointer,
                cycle.predecessor_raw,
            )

            cycle.controller.reset(fail_live_call=3)
            with self.assertRaisesRegex(PipelineError, "source differs"):
                authority_commit.commit_authority_plan(
                    cycle.store,
                    staged_receipt_ref=cycle.staged_receipt_ref,
                    clock=lambda: "2026-08-15T04:07:00Z",
                )
            self.assertEqual(3, len(cycle.controller.calls))
            self.assert_pointer(
                cycle,
                cycle.predecessor_pointer,
                cycle.predecessor_raw,
            )

            original_stage_record = authority_commit._stage_record

            def fail_root_persistence(store, reference, raw):
                if reference.kind == "state-root":
                    raise PipelineError("injected StateRoot persistence failure")
                return original_stage_record(store, reference, raw)

            cycle.controller.reset()
            with (
                mock.patch.object(
                    authority_commit,
                    "_stage_record",
                    side_effect=fail_root_persistence,
                ),
                self.assertRaisesRegex(PipelineError, "persistence failure"),
            ):
                authority_commit.commit_authority_plan(
                    cycle.store,
                    staged_receipt_ref=cycle.staged_receipt_ref,
                    clock=lambda: "2026-08-15T04:08:00Z",
                )
            self.assert_pointer(
                cycle,
                cycle.predecessor_pointer,
                cycle.predecessor_raw,
            )

            cycle.controller.reset()
            cycle.deep_mock.reset_mock()
            cycle.h3_mock.reset_mock()
            original_pointer_transaction = cycle.store.pointer_transaction
            publication_pointer_bytes: list[tuple[str, bytes]] = []
            persisted_readers: list[object] = []
            original_read_record = authority_commit._read_record

            def record_stage(store, reference, raw):
                publication_pointer_bytes.append(
                    (
                        reference.kind,
                        (cycle.root / POINTER_PATH).read_bytes(),
                    )
                )
                return original_stage_record(store, reference, raw)

            def record_persisted_read(*args, **kwargs):
                persisted_readers.append(args[1])
                return original_read_record(*args, **kwargs)

            timestamps = iter(
                ("2026-08-15T04:09:00Z", "2026-08-15T04:10:00Z")
            )
            with (
                mock.patch.object(
                    cycle.store,
                    "pointer_transaction",
                    wraps=original_pointer_transaction,
                ) as pointer_transaction,
                mock.patch.object(
                    authority_commit,
                    "_stage_record",
                    side_effect=record_stage,
                ),
                mock.patch.object(
                    authority_commit,
                    "_read_record",
                    side_effect=record_persisted_read,
                ),
            ):
                result, state_root_ref = authority_commit.commit_authority_plan(
                    cycle.store,
                    staged_receipt_ref=cycle.staged_receipt_ref,
                    clock=lambda: next(timestamps),
                )

            self.assertEqual(3, len(cycle.controller.calls))
            self.assertTrue(
                all(call[0] is True for call in cycle.controller.calls)
            )
            self.assertIs(cycle.store, cycle.controller.calls[0][1])
            self.assertTrue(
                all(
                    type(call[1]) is TransactionView
                    for call in cycle.controller.calls[1:]
                )
            )
            self.assertTrue(
                all(callable(call[2]) for call in cycle.controller.calls)
            )
            self.assertEqual(3, cycle.h3_mock.call_count)
            self.assertTrue(persisted_readers)
            self.assertTrue(
                all(type(reader) is TransactionView for reader in persisted_readers)
            )
            self.assertEqual(
                [
                    ("validation-receipt", cycle.predecessor_raw),
                    ("validation-receipt", cycle.successor_raw),
                    ("state-root", cycle.successor_raw),
                ],
                publication_pointer_bytes,
            )
            expected_retention = authority_commit._sorted_unique_refs(
                *cycle.staged_required,
                *cycle.historical_required,
            )
            transaction_arguments = pointer_transaction.call_args.kwargs
            self.assertEqual(
                expected_retention,
                transaction_arguments["required_objects"],
            )
            self.assertFalse(
                any(item.kind == "matrix-pointer" for item in expected_retention)
            )
            self.assertLess(
                len(expected_retention),
                len(cycle.staged_required) + len(cycle.historical_required),
            )
            self.assertEqual(cycle.predecessor_pointer, result.before.reference)
            self.assertEqual(cycle.predecessor_raw, result.before.raw)
            self.assertEqual(cycle.successor_pointer, result.after.reference)
            self.assertEqual(cycle.successor_raw, result.after.raw)

            state_root = _record(
                cycle.store,
                state_root_ref,
                StateRoot,
                label="authority StateRoot",
            )
            self.assertIsInstance(state_root, StateRoot)
            post_receipt = _record(
                cycle.store,
                state_root.receipt,
                Receipt,
                label="authority post receipt",
            )
            self.assertIsInstance(post_receipt, Receipt)
            pre_ref = next(
                item
                for item in post_receipt.outputs
                if item.kind == "validation-receipt"
            )
            pre_receipt = _record(
                cycle.store,
                pre_ref,
                Receipt,
                label="authority pre receipt",
            )
            self.assertIsInstance(pre_receipt, Receipt)
            self.assertEqual((cycle.staged_receipt_ref,), pre_receipt.outputs)
            self.assertEqual(
                authority_commit._sorted_unique_refs(
                    pre_ref,
                    cycle.successor_pointer,
                ),
                post_receipt.outputs,
            )
            self.assertEqual(cycle.staged.receipt.checks, pre_receipt.checks)
            self.assertEqual(cycle.staged.receipt.checks, post_receipt.checks)
            self.assertEqual(pre_receipt, result.pre_commit)
            self.assertEqual(post_receipt, result.post_commit)
            self.assertEqual(pre_receipt.started_at, pre_receipt.completed_at)
            self.assertEqual(post_receipt.started_at, post_receipt.completed_at)
            self.assertEqual(2, state_root.generation)
            self.assertEqual(cycle.prior_state_root_ref, state_root.previous)
            self.assertEqual(cycle.staged.planned.plan_reference, state_root.plan)
            self.assertEqual(cycle.successor_matrix_ref, state_root.current)
            self.assert_pointer(
                cycle,
                cycle.successor_pointer,
                cycle.successor_raw,
            )

            cycle.controller.reset()
            historical = authority_commit._load_historical_authority_commit(
                cycle.store,
                state_root_ref=state_root_ref,
            )
            self.assertEqual(state_root, historical.state_root)
            self.assertEqual(pre_ref, historical.pre_commit_receipt_ref)
            self.assertEqual(
                cycle.successor_pointer,
                historical.current_pointer_ref,
            )
            self.assertEqual(
                authority_commit._historical_required_objects(
                    cycle.staged,
                    state_root_ref=state_root_ref,
                    pre_commit_receipt_ref=pre_ref,
                    post_commit_receipt_ref=state_root.receipt,
                ),
                historical.required_objects,
            )
            alternate_check = replace(
                pre_receipt.checks[0],
                subject_sha256="f" * 64,
            )
            receipt_tampers = (
                ("transition", replace(pre_receipt, transition_id="other-v1")),
                (
                    "plan",
                    replace(
                        pre_receipt,
                        plan=cycle.staged.historical_transition.state_root.plan,
                    ),
                ),
                ("stage", replace(pre_receipt, stage="historical")),
                (
                    "timestamp",
                    replace(
                        pre_receipt,
                        completed_at="2026-08-15T04:09:01Z",
                    ),
                ),
                ("checks", replace(pre_receipt, checks=(alternate_check,))),
                ("outputs-missing", replace(pre_receipt, outputs=())),
                (
                    "outputs-extra",
                    replace(
                        pre_receipt,
                        outputs=_sorted_refs(
                            cycle.staged_receipt_ref,
                            wrong_kind,
                        ),
                    ),
                ),
            )
            for label, tampered_receipt in receipt_tampers:
                with (
                    self.subTest(receipt_tamper=label),
                    self.assertRaisesRegex(
                        PipelineError,
                        "closure is not exact",
                    ),
                ):
                    authority_commit._require_receipt(
                        cycle.staged,
                        tampered_receipt,
                        stage="pre-commit",
                        outputs=(cycle.staged_receipt_ref,),
                    )

            alias_pointer = replace(
                cycle.successor_pointer,
                path=(
                    ".local-e2e/campaigns/authority-commit-campaign/"
                    "campaign-matrix-alias.json"
                ),
            )
            tampered_post = replace(
                post_receipt,
                outputs=_sorted_refs(pre_ref, alias_pointer),
            )
            with self.assertRaisesRegex(PipelineError, "closure is not exact"):
                authority_commit._require_receipt(
                    cycle.staged,
                    tampered_post,
                    stage="post-commit",
                    outputs=authority_commit._sorted_unique_refs(
                        pre_ref,
                        cycle.successor_pointer,
                    ),
                )

            root_tampers = (
                ("generation", replace(state_root, generation=3)),
                (
                    "campaign",
                    replace(state_root, campaign_id="other-campaign"),
                ),
                (
                    "transition",
                    replace(state_root, transition_id="other-transition-v1"),
                ),
                (
                    "plan",
                    replace(
                        state_root,
                        plan=cycle.staged.historical_transition.state_root.plan,
                    ),
                ),
                ("receipt", replace(state_root, receipt=pre_ref)),
                (
                    "current",
                    replace(
                        state_root,
                        current=(
                            cycle.staged.historical_transition.state_root.current
                        ),
                    ),
                ),
                ("previous", replace(state_root, previous=state_root_ref)),
            )
            for label, tampered_root in root_tampers:
                with (
                    self.subTest(root_tamper=label),
                    self.assertRaisesRegex(PipelineError, "topology is not exact"),
                ):
                    authority_commit._require_state_root(
                        cycle.staged,
                        tampered_root,
                        post_commit_receipt_ref=state_root.receipt,
                    )

            loaded_type = type(historical)
            retention_tampers = (
                historical.required_objects[:-1],
                authority_commit._sorted_unique_refs(
                    *historical.required_objects,
                    wrong_kind,
                ),
                authority_commit._sorted_unique_refs(
                    *historical.required_objects,
                    cycle.successor_pointer,
                ),
            )
            for tampered_retention in retention_tampers:
                with self.assertRaisesRegex(PipelineError, "closure is not exact"):
                    loaded_type(
                        state_root=historical.state_root,
                        state_root_ref=historical.state_root_ref,
                        staged=historical.staged,
                        pre_commit_receipt_ref=(
                            historical.pre_commit_receipt_ref
                        ),
                        post_commit_receipt_ref=(
                            historical.post_commit_receipt_ref
                        ),
                        current_pointer_ref=historical.current_pointer_ref,
                        required_objects=tampered_retention,
                    )
            content = {
                reference: cycle.store.read_exact(reference)
                for reference in historical.required_objects
            }
            reads: list[EvidenceRef] = []

            class PointerFreeReader:
                def read_exact(self, reference: EvidenceRef) -> bytes:
                    reads.append(reference)
                    return content[reference]

                def read_pointer(self, _reference: EvidenceRef):
                    raise AssertionError("historical load read a pointer")

            cycle.controller.reset()
            with mock.patch.object(
                cycle.store,
                "read_exact",
                side_effect=AssertionError(
                    "historical load bypassed the injected reader"
                ),
            ):
                routed = authority_commit._load_historical_authority_commit(
                    cycle.store,
                    state_root_ref=state_root_ref,
                    reader=PointerFreeReader(),
                )
            self.assertEqual(historical, routed)
            self.assertEqual(set(historical.required_objects), set(reads))
            self.assertTrue(
                all(call[0] is False for call in cycle.controller.calls)
            )

            cycle.controller.reset()
            self.assertEqual(
                state_root,
                authority_commit.verify_committed_authority_plan(
                    cycle.store,
                    state_root_ref=state_root_ref,
                ),
            )
            self.assertEqual(
                [False, False],
                [call[0] for call in cycle.controller.calls],
            )

            cycle.controller.reset()
            with self.assertRaises(PipelineError):
                authority_commit.commit_authority_plan(
                    cycle.store,
                    staged_receipt_ref=cycle.staged_receipt_ref,
                    clock=lambda: "2026-08-15T04:11:00Z",
                )
            self.assertEqual(1, len(cycle.controller.calls))
            self.assert_pointer(
                cycle,
                cycle.successor_pointer,
                cycle.successor_raw,
            )

            _write_pointer(cycle.root, cycle.predecessor_raw)
            with self.assertRaises(PipelineError):
                authority_commit.verify_committed_authority_plan(
                    cycle.store,
                    state_root_ref=state_root_ref,
                )

    def test_surface_is_library_only_and_bounded(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            {"subprocess", "requests", "urllib", "argparse"}.isdisjoint(imports)
        )
        attribute_calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue(
            {"glob", "rglob", "iterdir", "walk"}.isdisjoint(attribute_calls)
        )
        self.assertNotIn("__main__", MODULE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            {
                "Clock",
                "commit_authority_plan",
                "verify_committed_authority_plan",
            },
            set(authority_commit.__all__),
        )


if __name__ == "__main__":
    unittest.main()
