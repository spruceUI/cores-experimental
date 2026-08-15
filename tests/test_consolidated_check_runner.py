from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.checks import (
    CONTROLLED_ENVIRONMENT_KEYS,
    FULL_STATIC_ALLOWED_SKIPS,
    ArtifactRequest,
    AttestedArtifactBytes,
    AttestedReceiptBytes,
    CapturedStructuredOutput,
    CheckExecution,
    CheckReceipt,
    CheckResult,
    CheckRunner,
    CheckStatus,
    CheckTier,
    FailureKind,
    LocalSubprocessService,
    ProcessCapture,
    ProcessDisposition,
    PYTEST_REPORTER_PLUGIN,
    ResultOrigin,
    StructuredFormat,
    canonical_json_bytes,
    check_ids_for_tier,
    checks_for_tier,
    controlled_environment,
    definition_for,
    validate_passed_check_result,
)
from scripts.core_pipeline_lib.checks.artifacts import (
    argv_sha256,
    authenticate_captured_outputs,
    binding_sha256,
    sha256_bytes,
    subject_sha256,
)
from scripts.core_pipeline_lib.checks import pytest_reporter


class TickClock:
    def __init__(self, step: float = 0.001) -> None:
        self.value = 0.0
        self.step = step

    def monotonic(self) -> float:
        value = self.value
        self.value += self.step
        return value


class SequentialRunIds:
    def __init__(self, prefix: str = "local-run") -> None:
        self.prefix = prefix
        self.index = 0

    def new_run_id(self) -> str:
        result = f"{self.prefix}-{self.index:03d}"
        self.index += 1
        return result


class FakeSubprocessService:
    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs: object) -> ProcessCapture:
        self.calls.append(dict(kwargs))
        if not self.outcomes:
            raise AssertionError("unexpected subprocess call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            outcome = outcome(kwargs)
        return outcome  # type: ignore[return-value]


class FakeReceiptResolver:
    def __init__(self, value: object) -> None:
        self.value = value
        self.calls: list[dict[str, object]] = []

    def resolve(self, **kwargs: object) -> AttestedReceiptBytes:
        self.calls.append(dict(kwargs))
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value  # type: ignore[return-value]


def completed_capture(
    *,
    returncode: int = 0,
    stdout: str | None = "complete stdout\n",
    stderr: str | None = "complete stderr\n",
    disposition: ProcessDisposition = ProcessDisposition.COMPLETED,
    structured_outputs: tuple[CapturedStructuredOutput, ...] = (),
    artifact_error: str | None = None,
) -> ProcessCapture:
    return ProcessCapture(
        disposition=disposition,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        structured_outputs=structured_outputs,
        artifact_error=artifact_error,
    )


def option_value(argv: tuple[str, ...], option: str) -> str:
    index = argv.index(option)
    return argv[index + 1]


def junit_bytes(skipped: tuple[str, ...]) -> bytes:
    suites = ET.Element("testsuites")
    suite = ET.SubElement(
        suites,
        "testsuite",
        tests=str(len(skipped)),
        skipped=str(len(skipped)),
    )
    for node_id in skipped:
        parts = node_id.split("::")
        classname = ".".join((parts[0][:-3].replace("/", "."), *parts[1:-1]))
        testcase = ET.SubElement(
            suite,
            "testcase",
            classname=classname,
            name=parts[-1],
        )
        ET.SubElement(testcase, "skipped", message="environment gate")
    return ET.tostring(suites, encoding="utf-8")


def pytest_capture_for_call(
    call: dict[str, object],
    *,
    skipped: tuple[str, ...] = FULL_STATIC_ALLOWED_SKIPS,
    returncode: int = 0,
    json_override: bytes | None = None,
    junit_override: bytes | None = None,
) -> ProcessCapture:
    executed = call["argv"]
    assert type(executed) is tuple
    definition = definition_for("tests.full-static")
    canonical = definition.render_argv()
    tests = [
        {"node_id": node_id, "outcome": "skipped"} for node_id in skipped
    ]
    report = {
        "schema_version": 1,
        "check_id": option_value(executed, "--consolidated-check-id"),
        "subject_sha256": option_value(
            executed, "--consolidated-check-subject-sha256"
        ),
        "run_id": option_value(executed, "--consolidated-check-run-id"),
        "argv_sha256": argv_sha256(canonical),
        "exitstatus": returncode,
        "tests": tests,
    }
    return completed_capture(
        returncode=returncode,
        structured_outputs=(
            CapturedStructuredOutput(
                format=StructuredFormat.JSON,
                content=(json_override or canonical_json_bytes(report)),
            ),
            CapturedStructuredOutput(
                format=StructuredFormat.JUNIT,
                content=(junit_override or junit_bytes(skipped)),
            ),
        ),
    )


def make_runner(
    service: FakeSubprocessService,
    *,
    clock: TickClock | None = None,
    resolver: FakeReceiptResolver | None = None,
) -> CheckRunner:
    return CheckRunner(
        repository_root=Path("/checked/repository"),
        subprocess_service=service,
        clock=clock or TickClock(),
        environment={
            "PATH": "/controlled/bin",
            "HOME": "/must/not/pass-through",
            "CORE_TOOLCHAIN_ARCHIVE_REAL_TESTS": "1",
            "PYTEST_ADDOPTS": "--unsafe-user-option",
        },
        run_id_source=SequentialRunIds(),
        receipt_resolver=resolver,
    )


def external_executed_argv(
    definition_id: str,
    *,
    argv: tuple[str, ...],
    subject: str,
    run_id: str,
) -> tuple[str, ...]:
    if definition_id != "tests.full-static":
        return argv
    root = Path("/attested/check-run")
    return argv + (
        "-p",
        PYTEST_REPORTER_PLUGIN,
        "--consolidated-check-report",
        str(root / "pytest-report.json"),
        "--consolidated-check-id",
        definition_id,
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


def external_bundle(
    *,
    subject: str = "candidate-1",
    attestor_id: str = "trusted-ci-attestor-v1",
) -> AttestedReceiptBytes:
    results: list[CheckResult] = []
    artifact_bytes: list[AttestedArtifactBytes] = []
    for index, check_id in enumerate(check_ids_for_tier(CheckTier.REBUILD)):
        definition = definition_for(check_id)
        run_id = f"external-run-{index:03d}"
        if definition.execution is CheckExecution.EXTERNAL_RECEIPT:
            argv = ()
            environment_keys = ()
        elif check_id == "evidence.toolchain-downloads":
            argv = definition.render_argv(
                {
                    "arm64_archive": "artifacts/cores-arm64.tar.gz",
                    "armhf_archive": "artifacts/cores-armhf.tar.gz",
                    "rust_archive": "artifacts/cores-rust.tar.gz",
                }
            )
            environment_keys = CONTROLLED_ENVIRONMENT_KEYS
        else:
            argv = definition.render_argv()
            environment_keys = CONTROLLED_ENVIRONMENT_KEYS
        executed = external_executed_argv(
            check_id,
            argv=argv,
            subject=subject,
            run_id=run_id,
        )
        if check_id == "tests.full-static":
            report = {
                "schema_version": 1,
                "check_id": check_id,
                "subject_sha256": subject_sha256(subject),
                "run_id": run_id,
                "argv_sha256": argv_sha256(argv),
                "exitstatus": 0,
                "tests": [
                    {"node_id": node_id, "outcome": "skipped"}
                    for node_id in FULL_STATIC_ALLOWED_SKIPS
                ],
            }
            raw_outputs = (
                CapturedStructuredOutput(
                    format=StructuredFormat.JSON,
                    content=canonical_json_bytes(report),
                ),
                CapturedStructuredOutput(
                    format=StructuredFormat.JUNIT,
                    content=junit_bytes(FULL_STATIC_ALLOWED_SKIPS),
                ),
            )
        elif check_id == "release-candidate-roster":
            raw_outputs = (
                CapturedStructuredOutput(
                    format=StructuredFormat.JSON,
                    content=canonical_json_bytes(
                        {"check_id": check_id, "run_id": run_id}
                    ),
                ),
                CapturedStructuredOutput(
                    format=StructuredFormat.JUNIT,
                    content=b'<testsuite tests="0"/>',
                ),
            )
        else:
            raw_outputs = ()
        references, skipped = authenticate_captured_outputs(
            definition,
            check_id=check_id,
            subject=subject,
            run_id=run_id,
            argv=argv,
            executed_argv=executed,
            returncode=0,
            outputs=raw_outputs,
        )
        results.append(
            CheckResult(
                check_id=check_id,
                tier=definition.tier,
                subject=subject,
                run_id=run_id,
                status=CheckStatus.PASSED,
                origin=ResultOrigin.EXTERNAL,
                argv=argv,
                executed_argv=executed,
                environment_keys=environment_keys,
                duration_milliseconds=1,
                returncode=0,
                signal=None,
                timed_out=False,
                logs_complete=True,
                stdout=f"{check_id} stdout\n",
                stderr=f"{check_id} stderr\n",
                skipped_tests=skipped,
                structured_outputs=references,
                failure_kind=None,
                message=None,
            )
        )
        artifact_bytes.extend(
            AttestedArtifactBytes(
                binding_sha256=reference.binding_sha256,
                content=reference.content or b"",
            )
            for reference in references
        )
    receipt = CheckReceipt(
        tier=CheckTier.REBUILD,
        subject=subject,
        status=CheckStatus.PASSED,
        origin=ResultOrigin.EXTERNAL,
        attestor_id=attestor_id,
        results=tuple(results),
    )
    return AttestedReceiptBytes(
        attestor_id=attestor_id,
        receipt_bytes=receipt.to_bytes(),
        artifacts=tuple(artifact_bytes),
    )


def replace_external_artifact(
    bundle: AttestedReceiptBytes,
    *,
    check_id: str,
    format: StructuredFormat,
    content: bytes,
) -> AttestedReceiptBytes:
    document = json.loads(bundle.receipt_bytes)
    result = next(
        item for item in document["results"] if item["check_id"] == check_id
    )
    reference = next(
        item
        for item in result["structured_outputs"]
        if item["format"] == format.value
    )
    old_binding = reference["binding_sha256"]
    digest = sha256_bytes(content)
    new_binding = binding_sha256(
        format=format,
        artifact_sha256=digest,
        artifact_size=len(content),
        check_id=check_id,
        subject=result["subject"],
        run_id=result["run_id"],
        argv=tuple(result["argv"]),
        executed_argv=tuple(result["executed_argv"]),
    )
    reference.update(
        {
            "sha256": digest,
            "size": len(content),
            "binding_sha256": new_binding,
        }
    )
    artifacts = tuple(
        (
            AttestedArtifactBytes(
                binding_sha256=new_binding,
                content=content,
            )
            if item.binding_sha256 == old_binding
            else item
        )
        for item in bundle.artifacts
    )
    return AttestedReceiptBytes(
        attestor_id=bundle.attestor_id,
        receipt_bytes=canonical_json_bytes(document),
        artifacts=artifacts,
    )


class ConsolidatedCheckRunnerTests(unittest.TestCase):
    def test_plain_runner_uses_exact_environment_timeout_and_no_shell(self) -> None:
        service = FakeSubprocessService(completed_capture())
        result = make_runner(service).run_check(
            "toolchain.lock-metadata", subject="tree-abc"
        )
        self.assertIs(result.status, CheckStatus.PASSED)
        self.assertEqual("complete stdout\n", result.stdout)
        self.assertEqual("complete stderr\n", result.stderr)
        self.assertEqual(result.argv, result.executed_argv)
        call = service.calls[0]
        self.assertEqual(
            ("python3", "scripts/toolchain_archive.py", "validate-lock"),
            call["argv"],
        )
        self.assertEqual(120.0, call["timeout_seconds"])
        self.assertIs(call["shell"], False)
        self.assertEqual((), call["artifact_requests"])
        self.assertEqual(
            controlled_environment({"PATH": "/controlled/bin"}), call["env"]
        )
        self.assertNotIn("HOME", call["env"])
        self.assertNotIn("CORE_TOOLCHAIN_ARCHIVE_REAL_TESTS", call["env"])

    def test_full_static_actual_argv_is_explicitly_instrumented_and_retained(self) -> None:
        service = FakeSubprocessService(pytest_capture_for_call)
        result = make_runner(service).run_check(
            "tests.full-static", subject="tree-static"
        )
        self.assertIs(result.status, CheckStatus.PASSED)
        call = service.calls[0]
        executed = call["argv"]
        self.assertEqual(result.executed_argv, executed)
        self.assertEqual(result.argv, executed[: len(result.argv)])
        self.assertIn(PYTEST_REPORTER_PLUGIN, executed)
        self.assertIn("--junitxml", executed)
        self.assertIn("-rs", executed)
        self.assertIs(call["shell"], False)
        requests = call["artifact_requests"]
        self.assertEqual(
            (StructuredFormat.JSON, StructuredFormat.JUNIT),
            tuple(item.format for item in requests),
        )
        self.assertEqual(
            result.argv
            + (
                "-p",
                PYTEST_REPORTER_PLUGIN,
                "--consolidated-check-report",
                str(requests[0].path),
                "--consolidated-check-id",
                "tests.full-static",
                "--consolidated-check-subject-sha256",
                subject_sha256("tree-static"),
                "--consolidated-check-run-id",
                "local-run-000",
                "--consolidated-check-argv-sha256",
                argv_sha256(result.argv),
                "--junitxml",
                str(requests[1].path),
                "-rs",
            ),
            executed,
        )
        output_root = requests[0].path.parent
        self.assertFalse(output_root.exists())
        self.assertEqual(FULL_STATIC_ALLOWED_SKIPS, result.skipped_tests)
        for reference in result.structured_outputs:
            self.assertIsNotNone(reference.content)
            self.assertEqual(len(reference.content or b""), reference.size)

    def test_artifact_binding_changes_across_subjects_with_same_bytes(self) -> None:
        first = make_runner(FakeSubprocessService(pytest_capture_for_call)).run_check(
            "tests.full-static", subject="tree-one"
        )
        second = make_runner(FakeSubprocessService(pytest_capture_for_call)).run_check(
            "tests.full-static", subject="tree-two"
        )
        self.assertNotEqual(
            first.structured_outputs[0].sha256,
            second.structured_outputs[0].sha256,
        )
        self.assertEqual(
            first.structured_outputs[1].sha256,
            second.structured_outputs[1].sha256,
        )
        self.assertNotEqual(
            tuple(item.binding_sha256 for item in first.structured_outputs),
            tuple(item.binding_sha256 for item in second.structured_outputs),
        )

    def test_public_pass_policy_rejects_execution_runtime_and_hydration_drift(
        self,
    ) -> None:
        plain = make_runner(FakeSubprocessService(completed_capture())).run_check(
            "toolchain.lock-metadata", subject="tree-policy"
        )
        static = make_runner(
            FakeSubprocessService(pytest_capture_for_call)
        ).run_check("tests.full-static", subject="tree-policy")
        plain_definition = definition_for(plain.check_id)
        static_definition = definition_for(static.check_id)
        validate_passed_check_result(plain_definition, plain)
        validate_passed_check_result(static_definition, static)

        assert plain_definition.timeout_milliseconds is not None
        late = replace(
            plain,
            duration_milliseconds=plain_definition.timeout_milliseconds + 1,
        )
        unresolved = replace(
            static,
            structured_outputs=tuple(
                replace(reference, content=None)
                for reference in static.structured_outputs
            ),
        )
        adversaries = (
            (
                plain_definition,
                replace(
                    plain,
                    executed_argv=(*plain.executed_argv, "--unregistered"),
                ),
            ),
            (plain_definition, late),
            (static_definition, unresolved),
        )
        for definition, result in adversaries:
            with self.subTest(check_id=result.check_id):
                with self.assertRaises(PipelineError):
                    validate_passed_check_result(definition, result)

        validate_passed_check_result(
            static_definition,
            unresolved,
            require_hydrated_outputs=False,
        )

    def test_quick_tier_runs_once_in_registry_order(self) -> None:
        definitions = checks_for_tier(CheckTier.QUICK)
        service = FakeSubprocessService(
            *(completed_capture() for _ in definitions)
        )
        receipt = make_runner(service).run_tier(CheckTier.QUICK, subject="tree")
        self.assertIs(receipt.status, CheckStatus.PASSED)
        self.assertEqual(
            check_ids_for_tier(CheckTier.QUICK),
            tuple(item.check_id for item in receipt.results),
        )
        self.assertEqual(len(definitions), len(service.calls))

    def test_evidence_parameters_preflight_before_any_subprocess(self) -> None:
        service = FakeSubprocessService()
        runner = make_runner(service)
        with self.assertRaises(PipelineError):
            runner.run_tier(CheckTier.EVIDENCE, subject="tree")
        with self.assertRaises(PipelineError):
            runner.run_tier(
                CheckTier.EVIDENCE,
                subject="tree",
                parameters_by_check={"unknown.check": {}},
            )
        self.assertEqual([], service.calls)

    def test_nonzero_timeout_and_signal_are_distinct(self) -> None:
        cases = (
            (completed_capture(returncode=7), FailureKind.NONZERO_EXIT, 7, None),
            (
                subprocess.TimeoutExpired(cmd=("python3",), timeout=1),
                FailureKind.TIMEOUT,
                None,
                None,
            ),
            (completed_capture(returncode=-15), FailureKind.SIGNAL, -15, 15),
        )
        for outcome, kind, returncode, signal_number in cases:
            with self.subTest(kind=kind.value):
                result = make_runner(FakeSubprocessService(outcome)).run_check(
                    "toolchain.lock-metadata", subject="tree"
                )
                self.assertIs(result.status, CheckStatus.FAILED)
                self.assertIs(result.failure_kind, kind)
                self.assertEqual(returncode, result.returncode)
                self.assertEqual(signal_number, result.signal)

    def test_timeout_none_buffers_remain_incomplete(self) -> None:
        timeout = subprocess.TimeoutExpired(
            cmd=("python3",), timeout=1, output=None, stderr=None
        )
        result = make_runner(FakeSubprocessService(timeout)).run_check(
            "toolchain.lock-metadata", subject="tree"
        )
        self.assertIs(result.failure_kind, FailureKind.TIMEOUT)
        self.assertFalse(result.logs_complete)
        self.assertEqual("", result.stdout)
        self.assertEqual("", result.stderr)

    def test_missing_logs_and_late_success_fail_closed(self) -> None:
        missing = make_runner(
            FakeSubprocessService(completed_capture(stdout=None))
        ).run_check("toolchain.lock-metadata", subject="tree")
        self.assertIs(missing.failure_kind, FailureKind.MISSING_LOGS)
        late = make_runner(
            FakeSubprocessService(completed_capture()),
            clock=TickClock(step=121),
        ).run_check("toolchain.lock-metadata", subject="tree")
        self.assertIs(late.failure_kind, FailureKind.DURATION_CEILING)

    def test_skipped_and_environment_gated_checks_fail(self) -> None:
        for disposition, expected in (
            (ProcessDisposition.SKIPPED, FailureKind.SKIPPED),
            (ProcessDisposition.ENVIRONMENT_GATED, FailureKind.ENVIRONMENT_GATED),
        ):
            with self.subTest(disposition=disposition.value):
                result = make_runner(
                    FakeSubprocessService(
                        completed_capture(disposition=disposition)
                    )
                ).run_check("toolchain.lock-metadata", subject="tree")
                self.assertIs(result.failure_kind, expected)

    def test_unittest_reported_skip_fails_quick_check(self) -> None:
        capture = completed_capture(stderr="OK (skipped=1)\n")
        result = make_runner(FakeSubprocessService(capture)).run_check(
            "tests.runner-contracts", subject="tree"
        )
        self.assertIs(result.failure_kind, FailureKind.UNEXPECTED_SKIPS)

        repeated = completed_capture(
            stdout="OK (skipped=1)\n",
            stderr="OK (skipped=1)\n",
        )
        repeated_result = make_runner(
            FakeSubprocessService(repeated)
        ).run_check("tests.runner-contracts", subject="tree")
        self.assertIs(
            repeated_result.failure_kind,
            FailureKind.UNEXPECTED_SKIPS,
        )
        self.assertEqual(
            ("unittest-reported-skip-count-2",),
            repeated_result.skipped_tests,
        )

    def test_full_static_requires_exact_skip_id_set(self) -> None:
        invalid_skip_sets = (
            FULL_STATIC_ALLOWED_SKIPS[:1],
            FULL_STATIC_ALLOWED_SKIPS + ("tests/test_other.py::test_x",),
        )
        for skipped in invalid_skip_sets:
            with self.subTest(skipped=skipped):
                result = make_runner(
                    FakeSubprocessService(
                        lambda call: pytest_capture_for_call(
                            call,
                            skipped=skipped,
                        )
                    )
                ).run_check("tests.full-static", subject="tree")
                self.assertIs(
                    result.failure_kind,
                    FailureKind.UNEXPECTED_SKIPS,
                )

    def test_duplicate_or_malformed_service_capture_is_invalid_not_exception(self) -> None:
        dummy = make_runner(FakeSubprocessService(object())).run_check(
            "toolchain.lock-metadata", subject="tree"
        )
        self.assertIs(dummy.failure_kind, FailureKind.INVALID_PROCESS_RESULT)

        def duplicate(call: dict[str, object]) -> ProcessCapture:
            valid = pytest_capture_for_call(call)
            return completed_capture(
                structured_outputs=(
                    valid.structured_outputs[0],
                    valid.structured_outputs[0],
                    valid.structured_outputs[1],
                )
            )

        repeated = make_runner(FakeSubprocessService(duplicate)).run_check(
            "tests.full-static", subject="tree"
        )
        self.assertIs(repeated.failure_kind, FailureKind.INVALID_PROCESS_RESULT)

        with mock.patch(
            "scripts.core_pipeline_lib.checks.runner.authenticate_captured_outputs",
            side_effect=RuntimeError("untrusted parser surprise"),
        ):
            parser_failure = make_runner(
                FakeSubprocessService(pytest_capture_for_call)
            ).run_check("tests.full-static", subject="tree")
        self.assertIs(
            parser_failure.failure_kind,
            FailureKind.INVALID_PROCESS_RESULT,
        )

    def test_missing_or_bad_structured_outputs_fail_closed(self) -> None:
        missing = make_runner(
            FakeSubprocessService(
                completed_capture(
                    structured_outputs=(
                        CapturedStructuredOutput(
                            format=StructuredFormat.JSON,
                            content=b"{}",
                        ),
                    )
                )
            )
        ).run_check("tests.full-static", subject="tree")
        self.assertIs(missing.failure_kind, FailureKind.MISSING_STRUCTURED_OUTPUT)

        def duplicate_key(call: dict[str, object]) -> ProcessCapture:
            return pytest_capture_for_call(
                call,
                json_override=b'{"schema_version":1,"schema_version":1}',
            )

        malformed = make_runner(
            FakeSubprocessService(duplicate_key)
        ).run_check("tests.full-static", subject="tree")
        self.assertIs(malformed.failure_kind, FailureKind.INVALID_PROCESS_RESULT)

        def entity_junit(call: dict[str, object]) -> ProcessCapture:
            return pytest_capture_for_call(
                call,
                junit_override=(
                    b'<!DOCTYPE x [<!ENTITY y "z">]><testsuite>&y;</testsuite>'
                ),
            )

        unsafe_xml = make_runner(
            FakeSubprocessService(entity_junit)
        ).run_check("tests.full-static", subject="tree")
        self.assertIs(unsafe_xml.failure_kind, FailureKind.INVALID_PROCESS_RESULT)

        hostile_junit = (
            (
                '<?xml version="1.0" encoding="UTF-16"?>'
                '<!DOCTYPE testsuite [<!ENTITY x "expanded">]>'
                "<testsuite>&x;</testsuite>"
            ).encode("utf-16"),
            b'<?xml version="1.0" encoding="does-not-exist"?><testsuite/>',
        )
        for content in hostile_junit:
            with self.subTest(junit_prefix=content[:24]):
                result = make_runner(
                    FakeSubprocessService(
                        lambda call, raw=content: pytest_capture_for_call(
                            call,
                            junit_override=raw,
                        )
                    )
                ).run_check("tests.full-static", subject="tree")
                self.assertIs(
                    result.failure_kind,
                    FailureKind.INVALID_PROCESS_RESULT,
                )

    def test_concrete_service_runs_no_shell_reads_once_and_cleans_outputs(self) -> None:
        service = LocalSubprocessService()
        with tempfile.TemporaryDirectory(prefix="check-service-test-") as root_text:
            root = Path(root_text)
            with self.assertRaises(PipelineError):
                service.run(
                    argv=("python3", "-V"),
                    cwd=root,
                    env={"PATH": "/bin"},
                    timeout_seconds=10,
                    shell=True,
                )
            requests = (
                ArtifactRequest(
                    format=StructuredFormat.JSON,
                    path=root / "report.json",
                ),
                ArtifactRequest(
                    format=StructuredFormat.JUNIT,
                    path=root / "junit.xml",
                ),
            )

            def complete(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                requests[0].path.write_bytes(b'{"canonical":true}')
                requests[1].path.write_bytes(b'<testsuite tests="0"/>')
                return subprocess.CompletedProcess(args[0], 0, "stdout", "stderr")

            with mock.patch(
                "scripts.core_pipeline_lib.checks.service.subprocess.run",
                side_effect=complete,
            ) as run:
                capture = service.run(
                    argv=("python3", "-V"),
                    cwd=root,
                    env={"PATH": "/bin"},
                    timeout_seconds=10,
                    shell=False,
                    artifact_requests=requests,
                )
            self.assertEqual("stdout", capture.stdout)
            self.assertEqual("stderr", capture.stderr)
            self.assertEqual(
                (b'{"canonical":true}', b'<testsuite tests="0"/>'),
                tuple(item.content for item in capture.structured_outputs),
            )
            self.assertFalse(requests[0].path.exists())
            self.assertFalse(requests[1].path.exists())
            self.assertIs(run.call_args.kwargs["shell"], False)
            self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_concrete_service_rejects_symlink_artifact_and_preserves_none_timeout(self) -> None:
        service = LocalSubprocessService()
        with tempfile.TemporaryDirectory(prefix="check-service-test-") as root_text:
            root = Path(root_text)
            request = ArtifactRequest(
                format=StructuredFormat.JSON,
                path=root / "report.json",
            )
            target = root / "foreign.json"
            target.write_bytes(b"{}")

            def symlink(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                request.path.symlink_to(target)
                return subprocess.CompletedProcess(args[0], 0, "stdout", "stderr")

            with mock.patch(
                "scripts.core_pipeline_lib.checks.service.subprocess.run",
                side_effect=symlink,
            ):
                capture = service.run(
                    argv=("python3", "-V"),
                    cwd=root,
                    env={"PATH": "/bin"},
                    timeout_seconds=10,
                    shell=False,
                    artifact_requests=(request,),
                )
            self.assertIsNotNone(capture.artifact_error)
            self.assertFalse(request.path.exists())
            self.assertEqual(b"{}", target.read_bytes())

            hardlink_request = ArtifactRequest(
                format=StructuredFormat.JSON,
                path=root / "hardlink-report.json",
            )

            def hardlink(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                hardlink_request.path.hardlink_to(target)
                return subprocess.CompletedProcess(args[0], 0, "stdout", "stderr")

            with mock.patch(
                "scripts.core_pipeline_lib.checks.service.subprocess.run",
                side_effect=hardlink,
            ):
                hardlink_capture = service.run(
                    argv=("python3", "-V"),
                    cwd=root,
                    env={"PATH": "/bin"},
                    timeout_seconds=10,
                    shell=False,
                    artifact_requests=(hardlink_request,),
                )
            self.assertIsNotNone(hardlink_capture.artifact_error)
            self.assertFalse(hardlink_request.path.exists())
            self.assertEqual(b"{}", target.read_bytes())

            with mock.patch(
                "scripts.core_pipeline_lib.checks.service.subprocess.run",
                side_effect=subprocess.TimeoutExpired(
                    cmd=("python3",), timeout=1, output=None, stderr=None
                ),
            ):
                timeout_capture = service.run(
                    argv=("python3", "-V"),
                    cwd=root,
                    env={"PATH": "/bin"},
                    timeout_seconds=1,
                    shell=False,
                )
            self.assertIsNone(timeout_capture.stdout)
            self.assertIsNone(timeout_capture.stderr)

    def test_pytest_reporter_exclusive_writer_rejects_no_progress(self) -> None:
        self.assertEqual(
            "core-pipeline-consolidated-check-reporter",
            pytest_reporter.PLUGIN_NAME,
        )
        with tempfile.TemporaryDirectory(prefix="check-reporter-test-") as root_text:
            output = Path(root_text) / "report.json"
            with mock.patch.object(pytest_reporter.os, "write", return_value=0):
                with self.assertRaises(OSError):
                    pytest_reporter._exclusive_write(output, b"{}")

    def test_pytest_reporter_emits_canonical_exact_node_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="check-reporter-test-") as root_text:
            output = Path(root_text) / "report.json"
            options = {
                "--consolidated-check-report": str(output),
                "--consolidated-check-id": "tests.full-static",
                "--consolidated-check-subject-sha256": "a" * 64,
                "--consolidated-check-run-id": "run-001",
                "--consolidated-check-argv-sha256": "b" * 64,
            }
            config = mock.Mock()
            config.getoption.side_effect = options.__getitem__
            reporter = pytest_reporter._Reporter(config)
            first = mock.Mock(nodeid="tests/test_a.py::Case::test_pass")
            second = mock.Mock(nodeid="tests/test_a.py::Case::test_skip")
            session = mock.Mock(items=[first, second])
            reporter.pytest_collection_finish(session)
            reporter.pytest_runtest_logreport(
                mock.Mock(
                    nodeid=first.nodeid,
                    skipped=False,
                    failed=False,
                    when="call",
                )
            )
            reporter.pytest_runtest_logreport(
                mock.Mock(
                    nodeid=second.nodeid,
                    skipped=True,
                    failed=False,
                    when="setup",
                )
            )
            reporter.pytest_sessionfinish(session, 0)
            content = output.read_bytes()
            document = json.loads(content)
            self.assertEqual(content, canonical_json_bytes(document))
            self.assertEqual(
                [
                    {"node_id": first.nodeid, "outcome": "passed"},
                    {"node_id": second.nodeid, "outcome": "skipped"},
                ],
                document["tests"],
            )
            self.assertEqual("run-001", document["run_id"])

    def test_rebuild_requires_trusted_resolver_and_never_launches(self) -> None:
        service = FakeSubprocessService()
        runner = make_runner(service)
        with self.assertRaises(PipelineError):
            runner.run_tier(CheckTier.REBUILD, subject="candidate-1")
        with self.assertRaises(PipelineError):
            runner.run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/1",
            )
        with self.assertRaises(PipelineError):
            runner.run_check("release-candidate-roster", subject="candidate-1")
        self.assertEqual([], service.calls)

    def test_attested_rebuild_receipt_and_artifact_closure_validate(self) -> None:
        bundle = external_bundle()
        resolver = FakeReceiptResolver(bundle)
        service = FakeSubprocessService()
        receipt = make_runner(service, resolver=resolver).run_tier(
            CheckTier.REBUILD,
            subject="candidate-1",
            external_receipt_locator="ci/run/1",
        )
        self.assertIs(receipt.status, CheckStatus.PASSED)
        self.assertEqual("trusted-ci-attestor-v1", receipt.attestor_id)
        self.assertTrue(
            all(
                reference.content is not None
                for result in receipt.results
                for reference in result.structured_outputs
            )
        )
        self.assertEqual([], service.calls)
        self.assertEqual("candidate-1", resolver.calls[0]["expected_subject"])

    def test_external_receipt_replay_and_cross_subject_fail(self) -> None:
        bundle = external_bundle()
        resolver = FakeReceiptResolver(bundle)
        runner = make_runner(FakeSubprocessService(), resolver=resolver)
        runner.run_tier(
            CheckTier.REBUILD,
            subject="candidate-1",
            external_receipt_locator="ci/run/1",
        )
        with self.assertRaisesRegex(PipelineError, "replay"):
            runner.run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/1",
            )
        with self.assertRaisesRegex(PipelineError, "subject"):
            make_runner(
                FakeSubprocessService(), resolver=FakeReceiptResolver(bundle)
            ).run_tier(
                CheckTier.REBUILD,
                subject="candidate-2",
                external_receipt_locator="ci/run/1",
            )

        changed_document = json.loads(bundle.receipt_bytes)
        changed_document["results"][0]["stdout"] = "rewritten stdout\n"
        changed = AttestedReceiptBytes(
            attestor_id=bundle.attestor_id,
            receipt_bytes=canonical_json_bytes(changed_document),
            artifacts=bundle.artifacts,
        )
        resolver.value = changed
        with self.assertRaisesRegex(PipelineError, "run identity replay"):
            runner.run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/2",
            )

    def test_external_wrong_hash_size_and_artifact_closure_fail(self) -> None:
        base = external_bundle()
        document = json.loads(base.receipt_bytes)
        full = next(
            item for item in document["results"] if item["check_id"] == "tests.full-static"
        )
        for field, value in (("sha256", "0" * 64), ("size", 1)):
            with self.subTest(field=field):
                changed = copy.deepcopy(document)
                changed_full = next(
                    item
                    for item in changed["results"]
                    if item["check_id"] == "tests.full-static"
                )
                changed_full["structured_outputs"][0][field] = value
                tampered = AttestedReceiptBytes(
                    attestor_id=base.attestor_id,
                    receipt_bytes=canonical_json_bytes(changed),
                    artifacts=base.artifacts,
                )
                with self.assertRaises(PipelineError):
                    make_runner(
                        FakeSubprocessService(),
                        resolver=FakeReceiptResolver(tampered),
                    ).run_tier(
                        CheckTier.REBUILD,
                        subject="candidate-1",
                        external_receipt_locator="ci/run/1",
                    )
        extra = AttestedArtifactBytes(
            binding_sha256="f" * 64,
            content=b"unreferenced artifact",
        )
        first = base.artifacts[0]
        tampered_content = AttestedArtifactBytes(
            binding_sha256=first.binding_sha256,
            content=first.content + b"tampered",
        )
        malformed_artifact_sets = (
            base.artifacts[:-1],
            base.artifacts + (base.artifacts[0],),
            base.artifacts + (extra,),
            (tampered_content, *base.artifacts[1:]),
        )
        for artifacts in malformed_artifact_sets:
            with self.subTest(artifact_count=len(artifacts)):
                malformed = AttestedReceiptBytes(
                    attestor_id=base.attestor_id,
                    receipt_bytes=base.receipt_bytes,
                    artifacts=artifacts,
                )
                with self.assertRaises(PipelineError):
                    make_runner(
                        FakeSubprocessService(),
                        resolver=FakeReceiptResolver(malformed),
                    ).run_tier(
                        CheckTier.REBUILD,
                        subject="candidate-1",
                        external_receipt_locator="ci/run/1",
                    )

    def test_external_duplicate_key_noncanonical_dummy_and_attestor_mismatch_fail(self) -> None:
        base = external_bundle()
        malformed_values = (
            AttestedReceiptBytes(
                attestor_id=base.attestor_id,
                receipt_bytes=b'{"schema_version":2,"schema_version":2}',
                artifacts=(),
            ),
            AttestedReceiptBytes(
                attestor_id=base.attestor_id,
                receipt_bytes=json.dumps(json.loads(base.receipt_bytes)).encode(),
                artifacts=base.artifacts,
            ),
            AttestedReceiptBytes(
                attestor_id="different-attestor",
                receipt_bytes=base.receipt_bytes,
                artifacts=base.artifacts,
            ),
            object(),
        )
        for value in malformed_values:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(PipelineError):
                    make_runner(
                        FakeSubprocessService(),
                        resolver=FakeReceiptResolver(value),
                    ).run_tier(
                        CheckTier.REBUILD,
                        subject="candidate-1",
                        external_receipt_locator="ci/run/1",
                    )

    def test_external_junit_encoding_and_parser_failures_are_normalized(self) -> None:
        base = external_bundle()
        hostile_junit = (
            (
                '<?xml version="1.0" encoding="UTF-16"?>'
                '<!DOCTYPE testsuite [<!ENTITY x "expanded">]>'
                "<testsuite>&x;</testsuite>"
            ).encode("utf-16"),
            b'<?xml version="1.0" encoding="does-not-exist"?><testsuite/>',
        )
        for content in hostile_junit:
            with self.subTest(junit_prefix=content[:24]):
                attested = replace_external_artifact(
                    base,
                    check_id="release-candidate-roster",
                    format=StructuredFormat.JUNIT,
                    content=content,
                )
                with self.assertRaisesRegex(PipelineError, "JUnit"):
                    make_runner(
                        FakeSubprocessService(),
                        resolver=FakeReceiptResolver(attested),
                    ).run_tier(
                        CheckTier.REBUILD,
                        subject="candidate-1",
                        external_receipt_locator="ci/run/1",
                    )

        with mock.patch(
            "scripts.core_pipeline_lib.checks.runner.authenticate_external_outputs",
            side_effect=LookupError("unknown encoding"),
        ):
            with self.assertRaisesRegex(
                PipelineError,
                "external artifact authentication failed",
            ):
                make_runner(
                    FakeSubprocessService(),
                    resolver=FakeReceiptResolver(base),
                ).run_tier(
                    CheckTier.REBUILD,
                    subject="candidate-1",
                    external_receipt_locator="ci/run/1",
                )

    def test_external_wrong_argv_and_report_provenance_fail(self) -> None:
        base = external_bundle()
        document = json.loads(base.receipt_bytes)
        first = document["results"][0]
        first["argv"] = ["python3", "unknown.py"]
        first["executed_argv"] = ["python3", "unknown.py"]
        tampered = AttestedReceiptBytes(
            attestor_id=base.attestor_id,
            receipt_bytes=canonical_json_bytes(document),
            artifacts=base.artifacts,
        )
        with self.assertRaises(PipelineError):
            make_runner(
                FakeSubprocessService(), resolver=FakeReceiptResolver(tampered)
            ).run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/1",
            )

        run_document = json.loads(base.receipt_bytes)
        full_static = next(
            item
            for item in run_document["results"]
            if item["check_id"] == "tests.full-static"
        )
        full_static["run_id"] = "wrong-run-identity"
        wrong_run = AttestedReceiptBytes(
            attestor_id=base.attestor_id,
            receipt_bytes=canonical_json_bytes(run_document),
            artifacts=base.artifacts,
        )
        with self.assertRaises(PipelineError):
            make_runner(
                FakeSubprocessService(), resolver=FakeReceiptResolver(wrong_run)
            ).run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/1",
            )

        binding_document = json.loads(base.receipt_bytes)
        binding_full = next(
            item
            for item in binding_document["results"]
            if item["check_id"] == "tests.full-static"
        )
        old_binding = binding_full["structured_outputs"][0]["binding_sha256"]
        new_binding = "e" * 64
        binding_full["structured_outputs"][0]["binding_sha256"] = new_binding
        rebound_artifacts = tuple(
            AttestedArtifactBytes(
                binding_sha256=(
                    new_binding
                    if item.binding_sha256 == old_binding
                    else item.binding_sha256
                ),
                content=item.content,
            )
            for item in base.artifacts
        )
        wrong_binding = AttestedReceiptBytes(
            attestor_id=base.attestor_id,
            receipt_bytes=canonical_json_bytes(binding_document),
            artifacts=rebound_artifacts,
        )
        with self.assertRaises(PipelineError):
            make_runner(
                FakeSubprocessService(),
                resolver=FakeReceiptResolver(wrong_binding),
            ).run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/1",
            )

        skip_document = json.loads(base.receipt_bytes)
        unittest_result = next(
            item
            for item in skip_document["results"]
            if item["check_id"] == "tests.runner-contracts"
        )
        unittest_result["stderr"] = "OK (skipped=1)\n"
        hidden_skip = AttestedReceiptBytes(
            attestor_id=base.attestor_id,
            receipt_bytes=canonical_json_bytes(skip_document),
            artifacts=base.artifacts,
        )
        with self.assertRaisesRegex(PipelineError, "logs report skipped tests"):
            make_runner(
                FakeSubprocessService(),
                resolver=FakeReceiptResolver(hidden_skip),
            ).run_tier(
                CheckTier.REBUILD,
                subject="candidate-1",
                external_receipt_locator="ci/run/1",
            )

    def test_receipt_bytes_are_canonical_exact_schema(self) -> None:
        bundle = external_bundle()
        receipt = CheckReceipt.from_bytes(bundle.receipt_bytes)
        self.assertEqual(bundle.receipt_bytes, receipt.to_bytes())
        document = receipt.to_document()
        document["unknown"] = True
        with self.assertRaises(PipelineError):
            CheckReceipt.from_document(document)


if __name__ == "__main__":
    unittest.main()
