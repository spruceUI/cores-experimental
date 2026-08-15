"""Fail-closed local execution and attested external receipt validation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import math
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
from typing import Protocol

from ..errors import PipelineError
from .artifacts import (
    argv_sha256,
    authenticate_captured_outputs,
    authenticate_external_outputs,
    sha256_bytes,
    subject_sha256,
)
from .model import (
    ArtifactRequest,
    AttestedReceiptBytes,
    CheckDefinition,
    CheckExecution,
    CheckInstrumentation,
    CheckReceipt,
    CheckResult,
    CheckStatus,
    CheckTier,
    FailureKind,
    ProcessCapture,
    ProcessDisposition,
    ResultOrigin,
    StructuredFormat,
    StructuredOutputRef,
)
from .registry import checks_for_tier, definition_for


FIXED_ENVIRONMENT = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONHASHSEED": "0",
    "PYTHONNOUSERSITE": "1",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
}
CONTROLLED_ENVIRONMENT_KEYS = tuple(sorted((*FIXED_ENVIRONMENT, "PATH")))
PYTEST_REPORTER_PLUGIN = "scripts.core_pipeline_lib.checks.pytest_reporter"
UNITTEST_SKIP_RE = re.compile(r"\bskipped\s*=\s*([0-9]+)\b")


class SubprocessService(Protocol):
    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
        shell: bool,
        artifact_requests: tuple[ArtifactRequest, ...] = (),
    ) -> ProcessCapture: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...


class RunIdSource(Protocol):
    def new_run_id(self) -> str: ...


class TrustedReceiptResolver(Protocol):
    """Trust boundary that authenticates receipt and artifact source bytes."""

    def resolve(
        self,
        *,
        locator: str,
        expected_subject: str,
        expected_tier: CheckTier,
    ) -> AttestedReceiptBytes: ...


class SecureRunIdSource:
    def new_run_id(self) -> str:
        return secrets.token_hex(16)


def controlled_environment(source: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(source, Mapping):
        raise PipelineError("runner environment must be a mapping")
    path = source.get("PATH")
    if type(path) is not str or not path or "\x00" in path:
        raise PipelineError("runner environment requires a valid PATH")
    result = dict(FIXED_ENVIRONMENT)
    result["PATH"] = path
    return dict(sorted(result.items()))


def _subject(value: object) -> str:
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise PipelineError("check subject must be a nonempty stripped string")
    return value


def _clock_value(clock: Clock) -> float:
    value = clock.monotonic()
    if type(value) not in {int, float} or not math.isfinite(value):
        raise PipelineError("check clock returned a non-finite value")
    return float(value)


def _timeout_buffer(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is str:
        return value
    if type(value) is bytes:
        return value.decode("utf-8", errors="replace")
    return None


def _unittest_reported_skips(stdout: str, stderr: str) -> tuple[str, ...]:
    counts = tuple(
        int(match.group(1))
        for match in UNITTEST_SKIP_RE.finditer(f"{stdout}\n{stderr}")
    )
    if not any(count > 0 for count in counts):
        return ()
    return (f"unittest-reported-skip-count-{sum(counts)}",)


def _pytest_invocation(
    *,
    definition: CheckDefinition,
    argv: tuple[str, ...],
    subject: str,
    run_id: str,
    output_root: Path,
) -> tuple[tuple[str, ...], tuple[ArtifactRequest, ...]]:
    report = output_root / "pytest-report.json"
    junit = output_root / "pytest-junit.xml"
    executed = argv + (
        "-p",
        PYTEST_REPORTER_PLUGIN,
        "--consolidated-check-report",
        str(report),
        "--consolidated-check-id",
        definition.check_id,
        "--consolidated-check-subject-sha256",
        subject_sha256(subject),
        "--consolidated-check-run-id",
        run_id,
        "--consolidated-check-argv-sha256",
        argv_sha256(argv),
        "--junitxml",
        str(junit),
        "-rs",
    )
    return executed, (
        ArtifactRequest(format=StructuredFormat.JSON, path=report),
        ArtifactRequest(format=StructuredFormat.JUNIT, path=junit),
    )


def _validate_executed_argv(definition: CheckDefinition, result: CheckResult) -> None:
    if not definition.accepts_argv(result.argv):
        raise PipelineError(f"result {result.check_id} argv is not registered")
    if definition.instrumentation is CheckInstrumentation.NONE:
        if result.executed_argv != result.argv:
            raise PipelineError(f"result {result.check_id} executed argv drifted")
        return
    prefix = result.argv
    actual = result.executed_argv
    if actual[: len(prefix)] != prefix or len(actual) != len(prefix) + 15:
        raise PipelineError("pytest executed argv does not have the exact reporter shape")
    suffix = actual[len(prefix) :]
    expected_fixed = {
        0: "-p",
        1: PYTEST_REPORTER_PLUGIN,
        2: "--consolidated-check-report",
        4: "--consolidated-check-id",
        5: result.check_id,
        6: "--consolidated-check-subject-sha256",
        7: subject_sha256(result.subject),
        8: "--consolidated-check-run-id",
        9: result.run_id,
        10: "--consolidated-check-argv-sha256",
        11: argv_sha256(result.argv),
        12: "--junitxml",
        14: "-rs",
    }
    if any(suffix[index] != value for index, value in expected_fixed.items()):
        raise PipelineError("pytest executed argv reporter provenance mismatch")
    report = Path(suffix[3])
    junit = Path(suffix[13])
    if (
        not report.is_absolute()
        or not junit.is_absolute()
        or report.parent != junit.parent
        or report.name != "pytest-report.json"
        or junit.name != "pytest-junit.xml"
    ):
        raise PipelineError("pytest executed argv output paths are not isolated/exact")


def validate_passed_check_result(
    definition: CheckDefinition,
    result: CheckResult,
    *,
    require_hydrated_outputs: bool = True,
) -> None:
    """Validate every registry-owned policy fact for one passed result.

    The runner and persistence adapters share this boundary so a serialized
    result cannot acquire authority merely by repeating a registered base
    argv.  Callers authenticating a serialized receipt may defer the hydrated
    byte requirement until they have resolved its exact artifact closure; all
    other pass-policy checks still run before hydration.
    """

    if type(definition) is not CheckDefinition or type(result) is not CheckResult:
        raise PipelineError("passed result validation requires exact check models")
    if type(require_hydrated_outputs) is not bool:
        raise PipelineError("hydrated output policy must be boolean")
    if result.check_id != definition.check_id or result.tier is not definition.tier:
        raise PipelineError("passed result does not match its registered definition")
    if result.status is not CheckStatus.PASSED:
        raise PipelineError(f"result {result.check_id} did not pass")
    if not definition.accepts_argv(result.argv):
        raise PipelineError(f"passed result {result.check_id} argv is not registered")
    _validate_executed_argv(definition, result)
    if (
        result.returncode != 0
        or result.signal is not None
        or result.timed_out
        or not result.logs_complete
        or result.failure_kind is not None
        or result.message is not None
    ):
        raise PipelineError(f"passed result {result.check_id} contains failing facts")
    expected_environment = (
        ()
        if definition.execution is CheckExecution.EXTERNAL_RECEIPT
        else CONTROLLED_ENVIRONMENT_KEYS
    )
    if result.environment_keys != expected_environment:
        raise PipelineError(f"passed result {result.check_id} environment drifted")
    ceiling = (
        definition.runtime_ceiling_milliseconds
        if definition.runtime_ceiling_milliseconds is not None
        else definition.timeout_milliseconds
    )
    if ceiling is not None and result.duration_milliseconds > ceiling:
        raise PipelineError(f"passed result {result.check_id} exceeds its ceiling")
    if result.skipped_tests != definition.allowed_skips:
        raise PipelineError(f"passed result {result.check_id} skip policy mismatch")
    if definition.check_id in {
        "tests.runner-contracts",
        "tests.pipeline-regression",
    } and _unittest_reported_skips(result.stdout, result.stderr):
        raise PipelineError(
            f"passed result {result.check_id} logs report skipped tests"
        )
    formats = tuple(item.format for item in result.structured_outputs)
    if formats != definition.required_structured_formats:
        raise PipelineError(f"passed result {result.check_id} output formats mismatch")
    if require_hydrated_outputs and any(
        item.content is None for item in result.structured_outputs
    ):
        raise PipelineError(f"passed result {result.check_id} has unresolved evidence")


class CheckRunner:
    def __init__(
        self,
        *,
        repository_root: Path,
        subprocess_service: SubprocessService,
        clock: Clock,
        environment: Mapping[str, object],
        run_id_source: RunIdSource | None = None,
        receipt_resolver: TrustedReceiptResolver | None = None,
        temporary_directory_factory: Callable[..., tempfile.TemporaryDirectory[str]] = (
            tempfile.TemporaryDirectory
        ),
    ) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            raise PipelineError("check repository root must be an absolute Path")
        self._repository_root = repository_root
        self._subprocess = subprocess_service
        self._clock = clock
        self._environment = controlled_environment(environment)
        self._run_ids = run_id_source or SecureRunIdSource()
        self._receipt_resolver = receipt_resolver
        self._temporary_directory = temporary_directory_factory
        self._issued_run_ids: set[str] = set()
        self._consumed_external_receipts: set[str] = set()
        self._consumed_external_run_ids: set[tuple[str, str]] = set()

    @property
    def environment(self) -> dict[str, str]:
        return dict(self._environment)

    def _new_run_id(self) -> str:
        try:
            run_id = self._run_ids.new_run_id()
        except Exception as exc:
            raise PipelineError("run ID source failed") from exc
        if (
            type(run_id) is not str
            or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,127}", run_id)
            or run_id in self._issued_run_ids
        ):
            raise PipelineError("run ID source returned an invalid or replayed ID")
        self._issued_run_ids.add(run_id)
        return run_id

    def run_check(
        self,
        check_id: str,
        *,
        subject: str,
        parameters: Mapping[str, object] | None = None,
    ) -> CheckResult:
        definition = definition_for(check_id)
        if definition.execution is not CheckExecution.LOCAL:
            raise PipelineError(
                f"check {definition.check_id} is external-receipt-only"
            )
        exact_subject = _subject(subject)
        argv = definition.render_argv(parameters)
        return self._run_definition(
            definition,
            argv=argv,
            subject=exact_subject,
            run_id=self._new_run_id(),
        )

    def run_tier(
        self,
        tier: CheckTier | str,
        *,
        subject: str,
        parameters_by_check: Mapping[str, Mapping[str, object]] | None = None,
        external_receipt_locator: str | None = None,
    ) -> CheckReceipt:
        exact_subject = _subject(subject)
        definitions = checks_for_tier(tier)
        selected_tier = definitions[-1].tier
        if selected_tier is CheckTier.REBUILD:
            if parameters_by_check:
                raise PipelineError("rebuild receipt validation accepts no local parameters")
            if external_receipt_locator is None:
                raise PipelineError("rebuild requires an external receipt locator")
            return self._resolve_external_receipt(
                locator=external_receipt_locator,
                subject=exact_subject,
            )
        if external_receipt_locator is not None:
            raise PipelineError("local tiers do not accept external receipt locators")
        supplied: Mapping[str, Mapping[str, object]] = (
            {} if parameters_by_check is None else parameters_by_check
        )
        if not isinstance(supplied, Mapping) or any(
            type(key) is not str for key in supplied
        ):
            raise PipelineError("tier parameters must map check IDs to mappings")
        selected_ids = frozenset(item.check_id for item in definitions)
        extra = frozenset(supplied) - selected_ids
        if extra:
            raise PipelineError(f"tier parameters contain unknown checks: {sorted(extra)}")
        invocations = tuple(
            (definition, definition.render_argv(supplied.get(definition.check_id)))
            for definition in definitions
        )
        run_ids = tuple(self._new_run_id() for _ in invocations)
        results = tuple(
            self._run_definition(
                definition,
                argv=argv,
                subject=exact_subject,
                run_id=run_id,
            )
            for (definition, argv), run_id in zip(invocations, run_ids, strict=True)
        )
        status = (
            CheckStatus.PASSED
            if all(item.status is CheckStatus.PASSED for item in results)
            else CheckStatus.FAILED
        )
        return CheckReceipt(
            tier=selected_tier,
            subject=exact_subject,
            status=status,
            origin=ResultOrigin.LOCAL,
            attestor_id=None,
            results=results,
        )

    def _run_definition(
        self,
        definition: CheckDefinition,
        *,
        argv: tuple[str, ...],
        subject: str,
        run_id: str,
    ) -> CheckResult:
        if definition.instrumentation is CheckInstrumentation.PYTEST:
            with self._temporary_directory(
                prefix="core-pipeline-check-"
            ) as temporary_root:
                output_root = Path(temporary_root).absolute()
                executed_argv, requests = _pytest_invocation(
                    definition=definition,
                    argv=argv,
                    subject=subject,
                    run_id=run_id,
                    output_root=output_root,
                )
                return self._execute(
                    definition,
                    argv=argv,
                    executed_argv=executed_argv,
                    artifact_requests=requests,
                    subject=subject,
                    run_id=run_id,
                )
        return self._execute(
            definition,
            argv=argv,
            executed_argv=argv,
            artifact_requests=(),
            subject=subject,
            run_id=run_id,
        )

    def _execute(
        self,
        definition: CheckDefinition,
        *,
        argv: tuple[str, ...],
        executed_argv: tuple[str, ...],
        artifact_requests: tuple[ArtifactRequest, ...],
        subject: str,
        run_id: str,
    ) -> CheckResult:
        started = _clock_value(self._clock)
        service_error: str | None = None
        try:
            capture = self._subprocess.run(
                argv=executed_argv,
                cwd=self._repository_root,
                env=dict(self._environment),
                timeout_seconds=definition.timeout_seconds,
                shell=False,
                artifact_requests=artifact_requests,
            )
        except subprocess.TimeoutExpired as exc:
            capture = ProcessCapture(
                disposition=ProcessDisposition.TIMED_OUT,
                returncode=None,
                stdout=_timeout_buffer(exc.stdout),
                stderr=_timeout_buffer(exc.stderr),
            )
        except Exception as exc:
            capture = None
            service_error = f"subprocess service raised {type(exc).__name__}"
        completed = _clock_value(self._clock)
        if completed < started:
            raise PipelineError("check clock moved backwards")
        duration = int(round((completed - started) * 1000))
        common = {
            "definition": definition,
            "argv": argv,
            "executed_argv": executed_argv,
            "subject": subject,
            "run_id": run_id,
            "duration": duration,
        }
        if service_error is not None or type(capture) is not ProcessCapture:
            return self._failed_result(
                **common,
                capture=None,
                kind=(
                    FailureKind.SERVICE_ERROR
                    if service_error is not None
                    else FailureKind.INVALID_PROCESS_RESULT
                ),
                message=service_error or "subprocess service returned a malformed capture",
            )
        if capture.disposition is ProcessDisposition.TIMED_OUT:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.TIMEOUT,
                message=f"check exceeded its {definition.timeout_seconds:g}-second timeout",
                timed_out=True,
            )
        if capture.disposition is ProcessDisposition.SKIPPED:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.SKIPPED,
                message="required check was skipped",
            )
        if capture.disposition is ProcessDisposition.ENVIRONMENT_GATED:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.ENVIRONMENT_GATED,
                message="required check was environment-gated",
            )
        if capture.stdout is None or capture.stderr is None:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.MISSING_LOGS,
                message="subprocess service omitted a complete stdout or stderr buffer",
            )
        if capture.returncode is None:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.INVALID_PROCESS_RESULT,
                message="completed subprocess omitted its returncode",
            )
        if capture.artifact_error is not None:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.INVALID_PROCESS_RESULT,
                message=f"structured capture failed: {capture.artifact_error}",
            )
        formats = tuple(item.format for item in capture.structured_outputs)
        expected_formats = definition.required_structured_formats
        if len(formats) != len(set(formats)) or set(formats) - set(expected_formats):
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.INVALID_PROCESS_RESULT,
                message="subprocess returned duplicate or unknown structured outputs",
            )
        if formats != expected_formats:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.MISSING_STRUCTURED_OUTPUT,
                message="subprocess omitted required structured outputs",
            )
        try:
            references, skipped = authenticate_captured_outputs(
                definition,
                check_id=definition.check_id,
                subject=subject,
                run_id=run_id,
                argv=argv,
                executed_argv=executed_argv,
                returncode=capture.returncode,
                outputs=capture.structured_outputs,
            )
        except Exception as exc:
            return self._failed_result(
                **common,
                capture=capture,
                kind=FailureKind.INVALID_PROCESS_RESULT,
                message=(
                    "structured output authentication failed: "
                    f"{type(exc).__name__}"
                ),
            )
        if definition.check_id in {
            "tests.runner-contracts",
            "tests.pipeline-regression",
        }:
            skipped = _unittest_reported_skips(capture.stdout, capture.stderr)
        if skipped != definition.allowed_skips:
            return self._failed_result(
                **common,
                capture=capture,
                references=references,
                skipped=skipped,
                kind=FailureKind.UNEXPECTED_SKIPS,
                message=(
                    f"observed skips differ from policy: "
                    f"expected={definition.allowed_skips!r}; observed={skipped!r}"
                ),
            )
        if capture.returncode < 0:
            signal_number = -capture.returncode
            return self._failed_result(
                **common,
                capture=capture,
                references=references,
                skipped=skipped,
                kind=FailureKind.SIGNAL,
                message=f"subprocess terminated by signal {signal_number}",
                signal_number=signal_number,
            )
        if capture.returncode != 0:
            return self._failed_result(
                **common,
                capture=capture,
                references=references,
                skipped=skipped,
                kind=FailureKind.NONZERO_EXIT,
                message=f"subprocess exited with status {capture.returncode}",
            )
        ceiling = (
            definition.runtime_ceiling_milliseconds
            if definition.runtime_ceiling_milliseconds is not None
            else definition.timeout_milliseconds
        )
        if ceiling is not None and duration > ceiling:
            return self._failed_result(
                **common,
                capture=capture,
                references=references,
                skipped=skipped,
                kind=FailureKind.DURATION_CEILING,
                message=f"check duration {duration}ms exceeds ceiling {ceiling}ms",
            )
        result = CheckResult(
            check_id=definition.check_id,
            tier=definition.tier,
            subject=subject,
            run_id=run_id,
            status=CheckStatus.PASSED,
            origin=ResultOrigin.LOCAL,
            argv=argv,
            executed_argv=executed_argv,
            environment_keys=CONTROLLED_ENVIRONMENT_KEYS,
            duration_milliseconds=duration,
            returncode=0,
            signal=None,
            timed_out=False,
            logs_complete=True,
            stdout=capture.stdout,
            stderr=capture.stderr,
            skipped_tests=skipped,
            structured_outputs=references,
            failure_kind=None,
            message=None,
        )
        validate_passed_check_result(definition, result)
        return result

    def _failed_result(
        self,
        *,
        definition: CheckDefinition,
        argv: tuple[str, ...],
        executed_argv: tuple[str, ...],
        subject: str,
        run_id: str,
        duration: int,
        capture: ProcessCapture | None,
        kind: FailureKind,
        message: str,
        references: tuple[StructuredOutputRef, ...] = (),
        skipped: tuple[str, ...] = (),
        timed_out: bool = False,
        signal_number: int | None = None,
    ) -> CheckResult:
        stdout = "" if capture is None or capture.stdout is None else capture.stdout
        stderr = "" if capture is None or capture.stderr is None else capture.stderr
        logs_complete = (
            capture is not None and capture.stdout is not None and capture.stderr is not None
        )
        returncode = None if capture is None or timed_out else capture.returncode
        return CheckResult(
            check_id=definition.check_id,
            tier=definition.tier,
            subject=subject,
            run_id=run_id,
            status=CheckStatus.FAILED,
            origin=ResultOrigin.LOCAL,
            argv=argv,
            executed_argv=executed_argv,
            environment_keys=CONTROLLED_ENVIRONMENT_KEYS,
            duration_milliseconds=duration,
            returncode=returncode,
            signal=signal_number,
            timed_out=timed_out,
            logs_complete=logs_complete,
            stdout=stdout,
            stderr=stderr,
            skipped_tests=skipped,
            structured_outputs=references,
            failure_kind=kind,
            message=message,
        )

    def _resolve_external_receipt(
        self,
        *,
        locator: str,
        subject: str,
    ) -> CheckReceipt:
        if type(locator) is not str or not locator or "\x00" in locator:
            raise PipelineError("external receipt locator is invalid")
        if self._receipt_resolver is None:
            raise PipelineError("rebuild requires an injected trusted receipt resolver")
        try:
            attested = self._receipt_resolver.resolve(
                locator=locator,
                expected_subject=subject,
                expected_tier=CheckTier.REBUILD,
            )
        except Exception as exc:
            raise PipelineError("trusted receipt resolver failed") from exc
        if type(attested) is not AttestedReceiptBytes:
            raise PipelineError("trusted resolver returned a malformed attestation")
        receipt_digest = sha256_bytes(attested.receipt_bytes)
        if receipt_digest in self._consumed_external_receipts:
            raise PipelineError("external receipt replay detected")
        receipt = CheckReceipt.from_bytes(attested.receipt_bytes)
        if receipt.attestor_id != attested.attestor_id:
            raise PipelineError("receipt attestor identity mismatch")
        if receipt.tier is not CheckTier.REBUILD or receipt.origin is not ResultOrigin.EXTERNAL:
            raise PipelineError("external receipt tier or origin is invalid")
        if receipt.subject != subject:
            raise PipelineError("external receipt subject mismatch")
        external_run_ids = tuple(
            (attested.attestor_id, result.run_id) for result in receipt.results
        )
        if any(
            identity in self._consumed_external_run_ids
            for identity in external_run_ids
        ):
            raise PipelineError("external run identity replay detected")
        definitions = checks_for_tier(CheckTier.REBUILD)
        expected_ids = tuple(item.check_id for item in definitions)
        actual_ids = tuple(item.check_id for item in receipt.results)
        if actual_ids != expected_ids:
            raise PipelineError("external receipt check IDs/order are not exact")
        artifact_bindings = tuple(item.binding_sha256 for item in attested.artifacts)
        if len(artifact_bindings) != len(set(artifact_bindings)):
            raise PipelineError("external attestation repeats an artifact binding")
        content_by_binding = {
            item.binding_sha256: item.content for item in attested.artifacts
        }
        expected_bindings = tuple(
            reference.binding_sha256
            for result in receipt.results
            for reference in result.structured_outputs
        )
        if len(expected_bindings) != len(set(expected_bindings)):
            raise PipelineError("external receipt repeats an artifact binding")
        if set(content_by_binding) != set(expected_bindings):
            raise PipelineError("external attestation artifact closure is not exact")

        hydrated_results: list[CheckResult] = []
        for definition, result in zip(definitions, receipt.results, strict=True):
            if result.tier is not definition.tier:
                raise PipelineError(f"external result {result.check_id} tier mismatch")
            _validate_executed_argv(definition, result)
            if result.status is CheckStatus.PASSED:
                validate_passed_check_result(
                    definition,
                    result,
                    require_hydrated_outputs=False,
                )
            try:
                hydrated = authenticate_external_outputs(
                    definition,
                    result,
                    content_by_binding,
                )
            except PipelineError:
                raise
            except Exception as exc:
                raise PipelineError(
                    "external artifact authentication failed for "
                    f"{result.check_id}: {type(exc).__name__}"
                ) from exc
            hydrated_result = replace(result, structured_outputs=hydrated)
            if hydrated_result.status is CheckStatus.PASSED:
                validate_passed_check_result(definition, hydrated_result)
            hydrated_results.append(hydrated_result)
        hydrated_receipt = replace(receipt, results=tuple(hydrated_results))
        if hydrated_receipt.to_bytes() != attested.receipt_bytes:
            raise PipelineError("hydrated receipt does not reproduce attested bytes")
        self._consumed_external_receipts.add(receipt_digest)
        self._consumed_external_run_ids.update(external_run_ids)
        return hydrated_receipt

__all__ = [
    "CONTROLLED_ENVIRONMENT_KEYS",
    "Clock",
    "CheckRunner",
    "FIXED_ENVIRONMENT",
    "PYTEST_REPORTER_PLUGIN",
    "RunIdSource",
    "SecureRunIdSource",
    "SubprocessService",
    "TrustedReceiptResolver",
    "controlled_environment",
    "validate_passed_check_result",
]
