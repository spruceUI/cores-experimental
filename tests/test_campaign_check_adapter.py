from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from scripts.core_pipeline_lib.campaign import (
    StoredCheckReceipt,
    run_and_store_check_receipt,
    validate_stored_check_receipt,
)
from scripts.core_pipeline_lib.campaign import workflow
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.campaign.store import CampaignStore
from scripts.core_pipeline_lib.checks import (
    CONTROLLED_ENVIRONMENT_KEYS,
    FULL_STATIC_ALLOWED_SKIPS,
    PYTEST_REPORTER_PLUGIN,
    CapturedStructuredOutput,
    CheckReceipt,
    CheckResult,
    CheckStatus,
    CheckTier,
    FailureKind,
    ResultOrigin,
    StructuredFormat,
    StructuredOutputRef,
    canonical_json_bytes,
    check_ids_for_tier,
    checks_for_tier,
)
from scripts.core_pipeline_lib.checks.artifacts import (
    argv_sha256,
    authenticate_captured_outputs,
    binding_sha256,
    subject_sha256,
)
from scripts.core_pipeline_lib.errors import PipelineError


SUBJECT = "a" * 64


def _junit_bytes(skipped: tuple[str, ...]) -> bytes:
    suites = ET.Element("testsuites")
    suite = ET.SubElement(
        suites,
        "testsuite",
        tests=str(len(skipped)),
        skipped=str(len(skipped)),
    )
    for node_id in skipped:
        parts = node_id.split("::")
        testcase = ET.SubElement(
            suite,
            "testcase",
            classname=".".join((parts[0][:-3].replace("/", "."), *parts[1:-1])),
            name=parts[-1],
        )
        ET.SubElement(testcase, "skipped", message="environment gate")
    return ET.tostring(suites, encoding="utf-8")


def _pytest_executed_argv(
    argv: tuple[str, ...],
    *,
    check_id: str,
    subject: str,
    run_id: str,
) -> tuple[str, ...]:
    root = Path("/authenticated/check-adapter-test")
    return argv + (
        "-p",
        PYTEST_REPORTER_PLUGIN,
        "--consolidated-check-report",
        str(root / "pytest-report.json"),
        "--consolidated-check-id",
        check_id,
        "--consolidated-check-subject-sha256",
        subject_sha256(subject),
        "--consolidated-check-run-id",
        run_id,
        "--consolidated-check-argv-sha256",
        argv_sha256(argv),
        "--junitxml",
        str(root / "pytest-junit.xml"),
        "-rs",
    )


def _receipt(
    tier: CheckTier,
    *,
    subject: str = SUBJECT,
) -> CheckReceipt:
    results: list[CheckResult] = []
    for index, definition in enumerate(checks_for_tier(tier)):
        run_id = f"adapter-run-{index:03d}"
        argv = definition.render_argv()
        executed_argv = argv
        structured_outputs = ()
        skipped = ()
        if definition.check_id == "tests.full-static":
            executed_argv = _pytest_executed_argv(
                argv,
                check_id=definition.check_id,
                subject=subject,
                run_id=run_id,
            )
            report = canonical_json_bytes(
                {
                    "schema_version": 1,
                    "check_id": definition.check_id,
                    "subject_sha256": subject_sha256(subject),
                    "run_id": run_id,
                    "argv_sha256": argv_sha256(argv),
                    "exitstatus": 0,
                    "tests": [
                        {"node_id": node_id, "outcome": "skipped"}
                        for node_id in FULL_STATIC_ALLOWED_SKIPS
                    ],
                }
            )
            structured_outputs, skipped = authenticate_captured_outputs(
                definition,
                check_id=definition.check_id,
                subject=subject,
                run_id=run_id,
                argv=argv,
                executed_argv=executed_argv,
                returncode=0,
                outputs=(
                    CapturedStructuredOutput(
                        format=StructuredFormat.JSON,
                        content=report,
                    ),
                    CapturedStructuredOutput(
                        format=StructuredFormat.JUNIT,
                        content=_junit_bytes(FULL_STATIC_ALLOWED_SKIPS),
                    ),
                ),
            )
        results.append(
            CheckResult(
                check_id=definition.check_id,
                tier=definition.tier,
                subject=subject,
                run_id=run_id,
                status=CheckStatus.PASSED,
                origin=ResultOrigin.LOCAL,
                argv=argv,
                executed_argv=executed_argv,
                environment_keys=CONTROLLED_ENVIRONMENT_KEYS,
                duration_milliseconds=1,
                returncode=0,
                signal=None,
                timed_out=False,
                logs_complete=True,
                stdout="complete stdout\n",
                stderr="complete stderr\n",
                skipped_tests=skipped,
                structured_outputs=structured_outputs,
                failure_kind=None,
                message=None,
            )
        )
    return CheckReceipt(
        tier=tier,
        subject=subject,
        status=CheckStatus.PASSED,
        origin=ResultOrigin.LOCAL,
        attestor_id=None,
        results=tuple(results),
    )


class SpyRunner:
    def __init__(self, receipt: CheckReceipt) -> None:
        self.receipt = receipt
        self.calls: list[dict[str, object]] = []

    def run_tier(
        self,
        tier: CheckTier,
        *,
        subject: str,
        parameters_by_check=None,
    ) -> CheckReceipt:
        self.calls.append(
            {
                "tier": tier,
                "subject": subject,
                "parameters_by_check": parameters_by_check,
            }
        )
        return self.receipt


class RecordingStore(CampaignStore):
    def __init__(self, repository_root: Path) -> None:
        super().__init__(repository_root, "campaign-state")
        self.publications: list[str] = []

    def create_or_verify(self, *, reference: EvidenceRef, raw: bytes):
        self.publications.append(reference.kind)
        return super().create_or_verify(reference=reference, raw=raw)


class CampaignCheckAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.root = Path(self._temporary.name)
        self.store = RecordingStore(self.root)

    def _persist_receipt(self, receipt: CheckReceipt) -> EvidenceRef:
        raw = receipt.to_bytes()
        reference = self.store.reference_for(
            kind="check-log",
            raw=raw,
            target_content_sha256=None,
        )
        self.store.create_or_verify(reference=reference, raw=raw)
        return reference

    def _validate(
        self,
        reference: EvidenceRef,
        *,
        artifact_refs: tuple[EvidenceRef, ...] = (),
        tier: CheckTier = CheckTier.QUICK,
        subject: str = SUBJECT,
        check_ids: tuple[str, ...] | None = None,
    ) -> CheckReceipt:
        return validate_stored_check_receipt(
            store=self.store,
            receipt_ref=reference,
            artifact_refs=artifact_refs,
            expected_subject=subject,
            expected_tier=tier,
            expected_check_ids=(
                check_ids_for_tier(tier) if check_ids is None else check_ids
            ),
        )

    def test_static_receipt_publishes_artifacts_first_and_retries_idempotently(
        self,
    ) -> None:
        receipt = _receipt(CheckTier.STATIC)
        runner = SpyRunner(receipt)
        parameters: dict[str, dict[str, object]] = {}

        first = run_and_store_check_receipt(
            runner=runner,  # type: ignore[arg-type]
            store=self.store,
            tier=CheckTier.STATIC,
            subject=SUBJECT,
            parameters_by_check=parameters,
        )
        second = run_and_store_check_receipt(
            runner=runner,  # type: ignore[arg-type]
            store=self.store,
            tier=CheckTier.STATIC,
            subject=SUBJECT,
            parameters_by_check=parameters,
        )

        self.assertIsInstance(first, StoredCheckReceipt)
        self.assertEqual(first, second)
        self.assertEqual(2, len(first.artifact_refs))
        self.assertEqual(
            tuple(sorted(first.artifact_refs, key=lambda item: (item.kind, item.path))),
            first.artifact_refs,
        )
        self.assertEqual(
            [
                "artifact",
                "artifact",
                "check-log",
                "artifact",
                "artifact",
                "check-log",
            ],
            self.store.publications,
        )
        self.assertEqual(2, len(runner.calls))
        self.assertIs(parameters, runner.calls[0]["parameters_by_check"])
        self.assertEqual(CheckTier.STATIC, runner.calls[0]["tier"])
        self.assertEqual(SUBJECT, runner.calls[0]["subject"])

        calls_before_validation = len(runner.calls)
        loaded = self._validate(
            first.receipt_ref,
            artifact_refs=first.artifact_refs,
            tier=CheckTier.STATIC,
        )
        self.assertEqual(receipt.to_bytes(), loaded.to_bytes())
        self.assertTrue(
            all(
                reference.content is None
                for result in loaded.results
                for reference in result.structured_outputs
            )
        )
        self.assertEqual(calls_before_validation, len(runner.calls))

    def test_quick_receipt_has_no_artifacts_and_is_accepted_by_h3(self) -> None:
        receipt = _receipt(CheckTier.QUICK)
        runner = SpyRunner(receipt)
        stored = run_and_store_check_receipt(
            runner=runner,  # type: ignore[arg-type]
            store=self.store,
            tier=CheckTier.QUICK,
            subject=SUBJECT,
        )

        self.assertEqual((), stored.artifact_refs)
        self.assertEqual(["check-log"], self.store.publications)
        self.assertEqual(
            receipt.to_bytes(),
            workflow._require_process_receipt(
                self.store,
                self.store,
                stored.receipt_ref,
            ),
        )
        calls_before_validation = len(runner.calls)
        self._validate(stored.receipt_ref)
        self.assertEqual(calls_before_validation, len(runner.calls))

    def test_stored_validation_rejects_receipt_authority_drift(self) -> None:
        original = _receipt(CheckTier.QUICK)
        failed_first = replace(
            original.results[0],
            status=CheckStatus.FAILED,
            returncode=1,
            failure_kind=FailureKind.NONZERO_EXIT,
            message="injected failure",
        )
        variants = {
            "subject": replace(
                original,
                subject="b" * 64,
                results=tuple(
                    replace(result, subject="b" * 64)
                    for result in original.results
                ),
            ),
            "tier": replace(original, tier=CheckTier.STATIC),
            "status": replace(
                original,
                status=CheckStatus.FAILED,
                results=(failed_first, *original.results[1:]),
            ),
            "origin": replace(
                original,
                origin=ResultOrigin.EXTERNAL,
                attestor_id="test-attestor",
                results=tuple(
                    replace(result, origin=ResultOrigin.EXTERNAL)
                    for result in original.results
                ),
            ),
            "check-completeness": replace(
                original,
                results=original.results[:-1],
            ),
            "check-id": replace(
                original,
                results=(
                    *original.results[:-1],
                    replace(
                        original.results[-1],
                        check_id="repository.drift-check",
                    ),
                ),
            ),
        }
        for label, receipt in variants.items():
            with self.subTest(label=label):
                reference = self._persist_receipt(receipt)
                with self.assertRaises(PipelineError):
                    self._validate(reference)

        reference = self._persist_receipt(original)
        with self.assertRaises(PipelineError):
            self._validate(
                reference,
                check_ids=check_ids_for_tier(CheckTier.QUICK)[:-1],
            )

    def test_pass_policy_drift_cannot_be_persisted_or_revalidated(self) -> None:
        quick = _receipt(CheckTier.QUICK)
        first = quick.results[0]
        quick_definition = next(
            definition
            for definition in checks_for_tier(CheckTier.QUICK)
            if definition.check_id == first.check_id
        )
        assert quick_definition.timeout_milliseconds is not None
        arbitrary_execution = replace(
            quick,
            results=(
                replace(first, executed_argv=(*first.executed_argv, "--forged")),
                *quick.results[1:],
            ),
        )
        late = replace(
            quick,
            results=(
                replace(
                    first,
                    duration_milliseconds=quick_definition.timeout_milliseconds + 1,
                ),
                *quick.results[1:],
            ),
        )

        static = _receipt(CheckTier.STATIC)
        full_index, full = next(
            (index, result)
            for index, result in enumerate(static.results)
            if result.check_id == "tests.full-static"
        )
        suffix_index = len(full.argv) + 3
        noncanonical_executed = list(full.executed_argv)
        noncanonical_executed[suffix_index] = (
            "/authenticated/check-adapter-test/forged-report.json"
        )
        noncanonical_tuple = tuple(noncanonical_executed)
        rebound_outputs = tuple(
            replace(
                reference,
                binding_sha256=binding_sha256(
                    format=reference.format,
                    artifact_sha256=reference.sha256,
                    artifact_size=reference.size,
                    check_id=full.check_id,
                    subject=full.subject,
                    run_id=full.run_id,
                    argv=full.argv,
                    executed_argv=noncanonical_tuple,
                ),
            )
            for reference in full.structured_outputs
        )
        forged_full = replace(
            full,
            executed_argv=noncanonical_tuple,
            structured_outputs=rebound_outputs,
        )
        forged_results = list(static.results)
        forged_results[full_index] = forged_full
        rebound_pytest = replace(static, results=tuple(forged_results))

        cases = (
            (
                "uninstrumented",
                arbitrary_execution,
                CheckTier.QUICK,
                "executed argv",
            ),
            ("duration", late, CheckTier.QUICK, "exceeds its ceiling"),
            (
                "pytest-suffix",
                rebound_pytest,
                CheckTier.STATIC,
                "output paths",
            ),
        )
        for label, receipt, tier, error in cases:
            with self.subTest(label=label):
                predicted = self.store.reference_for(
                    kind="check-log",
                    raw=receipt.to_bytes(),
                    target_content_sha256=None,
                )
                with self.assertRaisesRegex(PipelineError, error):
                    run_and_store_check_receipt(
                        runner=SpyRunner(receipt),  # type: ignore[arg-type]
                        store=self.store,
                        tier=tier,
                        subject=SUBJECT,
                    )
                with self.assertRaises(PipelineError):
                    self.store.read_exact(predicted)

                stored = self._persist_receipt(receipt)
                with self.assertRaisesRegex(PipelineError, error):
                    self._validate(stored, tier=tier)

    def test_run_rejects_missing_tampered_and_duplicate_hydrated_content(self) -> None:
        def with_outputs(
            receipt: CheckReceipt,
            outputs: tuple[StructuredOutputRef, ...],
        ) -> CheckReceipt:
            results = tuple(
                replace(result, structured_outputs=outputs)
                if result.check_id == "tests.full-static"
                else result
                for result in receipt.results
            )
            return replace(receipt, results=results)

        missing = _receipt(CheckTier.STATIC)
        full = next(
            result
            for result in missing.results
            if result.check_id == "tests.full-static"
        )
        missing = with_outputs(
            missing,
            (
                replace(full.structured_outputs[0], content=None),
                full.structured_outputs[1],
            ),
        )

        tampered = _receipt(CheckTier.STATIC)
        tampered_full = next(
            result
            for result in tampered.results
            if result.check_id == "tests.full-static"
        )
        object.__setattr__(
            tampered_full.structured_outputs[0],
            "content",
            b"x" * tampered_full.structured_outputs[0].size,
        )

        duplicate = _receipt(CheckTier.STATIC)
        duplicate_full = next(
            result
            for result in duplicate.results
            if result.check_id == "tests.full-static"
        )
        first = duplicate_full.structured_outputs[0]
        duplicate_second = StructuredOutputRef(
            format=StructuredFormat.JUNIT,
            sha256=first.sha256,
            size=first.size,
            binding_sha256=binding_sha256(
                format=StructuredFormat.JUNIT,
                artifact_sha256=first.sha256,
                artifact_size=first.size,
                check_id=duplicate_full.check_id,
                subject=duplicate_full.subject,
                run_id=duplicate_full.run_id,
                argv=duplicate_full.argv,
                executed_argv=duplicate_full.executed_argv,
            ),
            content=first.content,
        )
        duplicate = with_outputs(duplicate, (first, duplicate_second))

        for label, receipt in {
            "missing": missing,
            "tampered": tampered,
            "duplicate": duplicate,
        }.items():
            with self.subTest(label=label):
                predicted = self.store.reference_for(
                    kind="check-log",
                    raw=receipt.to_bytes(),
                    target_content_sha256=None,
                )
                with self.assertRaises(PipelineError):
                    run_and_store_check_receipt(
                        runner=SpyRunner(receipt),  # type: ignore[arg-type]
                        store=self.store,
                        tier=CheckTier.STATIC,
                        subject=SUBJECT,
                    )
                with self.assertRaises(PipelineError):
                    self.store.read_exact(predicted)

    def test_artifact_collision_and_symlink_fail_before_receipt_publication(
        self,
    ) -> None:
        for label in ("collision", "symlink"):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    store = RecordingStore(root)
                    receipt = _receipt(CheckTier.STATIC)
                    full = next(
                        result
                        for result in receipt.results
                        if result.check_id == "tests.full-static"
                    )
                    content = full.structured_outputs[0].content
                    assert content is not None
                    artifact_ref = store.reference_for(
                        kind="artifact",
                        raw=content,
                        target_content_sha256=None,
                    )
                    artifact_path = root / artifact_ref.path
                    artifact_path.parent.mkdir(parents=True)
                    if label == "collision":
                        artifact_path.write_bytes(b"foreign collision bytes")
                        artifact_path.chmod(0o644)
                    else:
                        target = root / "foreign-artifact"
                        target.write_bytes(content)
                        target.chmod(0o644)
                        artifact_path.symlink_to(target)
                    receipt_ref = store.reference_for(
                        kind="check-log",
                        raw=receipt.to_bytes(),
                        target_content_sha256=None,
                    )

                    with self.assertRaises(PipelineError):
                        run_and_store_check_receipt(
                            runner=SpyRunner(receipt),  # type: ignore[arg-type]
                            store=store,
                            tier=CheckTier.STATIC,
                            subject=SUBJECT,
                        )
                    with self.assertRaises(PipelineError):
                        store.read_exact(receipt_ref)

    def test_stored_validation_requires_exact_untampered_artifact_closure(self) -> None:
        receipt = _receipt(CheckTier.STATIC)
        runner = SpyRunner(receipt)
        stored = run_and_store_check_receipt(
            runner=runner,  # type: ignore[arg-type]
            store=self.store,
            tier=CheckTier.STATIC,
            subject=SUBJECT,
        )

        with self.assertRaises(PipelineError):
            self._validate(
                stored.receipt_ref,
                artifact_refs=stored.artifact_refs[:-1],
                tier=CheckTier.STATIC,
            )
        with self.assertRaises(PipelineError):
            self._validate(
                stored.receipt_ref,
                artifact_refs=(stored.artifact_refs[0], stored.artifact_refs[0]),
                tier=CheckTier.STATIC,
            )

        extra_raw = b"unreferenced adapter artifact\n"
        extra_ref = self.store.reference_for(
            kind="artifact",
            raw=extra_raw,
            target_content_sha256=None,
        )
        self.store.create_or_verify(reference=extra_ref, raw=extra_raw)
        with self.assertRaises(PipelineError):
            self._validate(
                stored.receipt_ref,
                artifact_refs=tuple(
                    sorted(
                        (*stored.artifact_refs, extra_ref),
                        key=lambda item: (item.kind, item.path),
                    )
                ),
                tier=CheckTier.STATIC,
            )

        artifact_path = self.root / stored.artifact_refs[0].path
        artifact_path.write_bytes(b"tampered stored artifact")
        artifact_path.chmod(0o644)
        with self.assertRaises(PipelineError):
            self._validate(
                stored.receipt_ref,
                artifact_refs=stored.artifact_refs,
                tier=CheckTier.STATIC,
            )
        self.assertEqual(1, len(runner.calls))

    def test_stored_validation_routes_every_read_through_injected_reader(self) -> None:
        receipt = _receipt(CheckTier.STATIC)
        stored = run_and_store_check_receipt(
            runner=SpyRunner(receipt),  # type: ignore[arg-type]
            store=self.store,
            tier=CheckTier.STATIC,
            subject=SUBJECT,
        )
        references = (stored.receipt_ref, *stored.artifact_refs)
        content = {reference: self.store.read_exact(reference) for reference in references}
        reads: list[EvidenceRef] = []

        class Reader:
            def read_exact(self, reference: EvidenceRef) -> bytes:
                reads.append(reference)
                return content[reference]

        with mock.patch.object(
            self.store,
            "read_exact",
            side_effect=AssertionError("validator bypassed injected reader"),
        ):
            validated = validate_stored_check_receipt(
                store=self.store,
                reader=Reader(),
                receipt_ref=stored.receipt_ref,
                artifact_refs=stored.artifact_refs,
                expected_subject=SUBJECT,
                expected_tier=CheckTier.STATIC,
                expected_check_ids=check_ids_for_tier(CheckTier.STATIC),
            )

        self.assertEqual(receipt, validated)
        self.assertEqual(list(references), reads)

    def test_external_and_rebuild_boundaries_are_rejected_without_process(self) -> None:
        receipt = _receipt(CheckTier.QUICK)
        runner = SpyRunner(receipt)
        with self.assertRaises(PipelineError):
            run_and_store_check_receipt(
                runner=runner,  # type: ignore[arg-type]
                store=self.store,
                tier=CheckTier.REBUILD,
                subject=SUBJECT,
            )
        self.assertEqual([], runner.calls)

        external = replace(
            receipt,
            origin=ResultOrigin.EXTERNAL,
            attestor_id="test-attestor",
            results=tuple(
                replace(result, origin=ResultOrigin.EXTERNAL)
                for result in receipt.results
            ),
        )
        external_ref = self._persist_receipt(external)
        with self.assertRaises(PipelineError):
            self._validate(external_ref)
        with self.assertRaises(PipelineError):
            validate_stored_check_receipt(
                store=self.store,
                receipt_ref=external_ref,
                artifact_refs=(),
                expected_subject=SUBJECT,
                expected_tier=CheckTier.REBUILD,
                expected_check_ids=check_ids_for_tier(CheckTier.REBUILD),
            )
        self.assertEqual([], runner.calls)


if __name__ == "__main__":
    unittest.main()
