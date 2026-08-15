"""Closed immutable process and tier models for the check front door."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import ClassVar

from ..errors import PipelineError


SCHEMA_VERSION = 2
MAX_RECEIPT_BYTES = 64 * 1024 * 1024

CHECK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
PARAMETER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
FLAG_RE = re.compile(r"^--[a-z0-9][a-z0-9-]*$")
RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CheckTier(str, Enum):
    QUICK = "quick"
    STATIC = "static"
    EVIDENCE = "evidence"
    REBUILD = "rebuild"


class CheckExecution(str, Enum):
    LOCAL = "local"
    EXTERNAL_RECEIPT = "external-receipt"


class CheckInstrumentation(str, Enum):
    NONE = "none"
    PYTEST = "pytest"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


class ResultOrigin(str, Enum):
    LOCAL = "local"
    EXTERNAL = "external"


class ProcessDisposition(str, Enum):
    COMPLETED = "completed"
    TIMED_OUT = "timed-out"
    SKIPPED = "skipped"
    ENVIRONMENT_GATED = "environment-gated"


class FailureKind(str, Enum):
    NONZERO_EXIT = "nonzero-exit"
    SIGNAL = "signal"
    TIMEOUT = "timeout"
    DURATION_CEILING = "duration-ceiling"
    MISSING_LOGS = "missing-logs"
    SKIPPED = "skipped"
    ENVIRONMENT_GATED = "environment-gated"
    MISSING_SKIP_REPORT = "missing-skip-report"
    UNEXPECTED_SKIPS = "unexpected-skips"
    MISSING_STRUCTURED_OUTPUT = "missing-structured-output"
    INVALID_PROCESS_RESULT = "invalid-process-result"
    SERVICE_ERROR = "service-error"


class StructuredFormat(str, Enum):
    JSON = "json"
    JUNIT = "junit"


class ParameterKind(str, Enum):
    PATH = "path"


class _DuplicateKey(ValueError):
    pass


def canonical_json_bytes(value: object) -> bytes:
    """Render the exact JSON identity used by check reports and receipts."""

    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise PipelineError(f"value is not canonical check JSON: {exc}") from exc


def decode_canonical_json_bytes(
    value: object,
    *,
    label: str,
    maximum_bytes: int = MAX_RECEIPT_BYTES,
) -> dict[str, object]:
    """Decode duplicate-free canonical UTF-8 JSON with one exact object root."""

    if type(value) is not bytes or not value or len(value) > maximum_bytes:
        raise PipelineError(f"{label} bytes are missing or exceed the size limit")

    def exact_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise _DuplicateKey(key)
            result[key] = item
        return result

    def reject_constant(token: str) -> None:
        raise ValueError(f"non-finite number: {token}")

    try:
        decoded = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=exact_object,
            parse_constant=reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise PipelineError(f"{label} is not strict JSON: {exc}") from exc
    if type(decoded) is not dict:
        raise PipelineError(f"{label} must have one exact object root")
    if canonical_json_bytes(decoded) != value:
        raise PipelineError(f"{label} is not canonically encoded")
    return decoded


def _require_identifier(value: object, label: str) -> str:
    if type(value) is not str or not CHECK_ID_RE.fullmatch(value):
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_text(value: object, label: str) -> str:
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise PipelineError(f"{label} must be a nonempty stripped string")
    return value


def _require_sha256(value: object, label: str) -> str:
    if type(value) is not str or not SHA256_RE.fullmatch(value):
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _require_exact_mapping(
    value: object,
    keys: frozenset[str],
    label: str,
) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise PipelineError(f"{label} must be an exact object")
    actual = frozenset(value)
    if actual != keys:
        raise PipelineError(
            f"{label} fields are not exact: "
            f"missing={sorted(keys - actual)}; extra={sorted(actual - keys)}"
        )
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != SCHEMA_VERSION
    ):
        raise PipelineError(f"{label} schema_version is invalid")
    return value


def _require_exact_list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact array")
    return value


def _enum_value(enum_type: type[Enum], value: object, label: str) -> Enum:
    if type(value) is not str:
        raise PipelineError(f"{label} is invalid")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise PipelineError(f"{label} is invalid") from exc


@dataclass(frozen=True, slots=True, kw_only=True)
class CapturedStructuredOutput:
    """Untrusted raw bytes returned by a subprocess service."""

    format: StructuredFormat
    content: bytes

    def __post_init__(self) -> None:
        if type(self.format) is not StructuredFormat or type(self.content) is not bytes:
            raise PipelineError("captured structured output is malformed")


@dataclass(frozen=True, slots=True, kw_only=True)
class ArtifactRequest:
    """One runner-owned output path the service must capture exactly once."""

    format: StructuredFormat
    path: Path

    def __post_init__(self) -> None:
        if type(self.format) is not StructuredFormat:
            raise PipelineError("artifact request format is invalid")
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise PipelineError("artifact request path must be absolute")


@dataclass(frozen=True, slots=True, kw_only=True)
class StructuredOutputRef:
    """Content and invocation-bound structured evidence reference."""

    format: StructuredFormat
    sha256: str
    size: int
    binding_sha256: str
    content: bytes | None = field(default=None, repr=False, compare=False)

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"schema_version", "format", "sha256", "size", "binding_sha256"}
    )

    def __post_init__(self) -> None:
        if type(self.format) is not StructuredFormat:
            raise PipelineError("structured output format is invalid")
        _require_sha256(self.sha256, "structured output sha256")
        _require_sha256(self.binding_sha256, "structured output binding_sha256")
        if type(self.size) is not int or self.size < 0:
            raise PipelineError("structured output size must be nonnegative")
        if self.content is not None:
            if type(self.content) is not bytes:
                raise PipelineError("structured output content must be bytes")
            if len(self.content) != self.size:
                raise PipelineError("structured output content size mismatch")
            if hashlib.sha256(self.content).hexdigest() != self.sha256:
                raise PipelineError("structured output content hash mismatch")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": self.format.value,
            "sha256": self.sha256,
            "size": self.size,
            "binding_sha256": self.binding_sha256,
        }

    @classmethod
    def from_document(cls, value: object) -> "StructuredOutputRef":
        document = _require_exact_mapping(value, cls._KEYS, "structured output")
        return cls(
            format=_enum_value(
                StructuredFormat, document["format"], "structured output format"
            ),  # type: ignore[arg-type]
            sha256=document["sha256"],  # type: ignore[arg-type]
            size=document["size"],  # type: ignore[arg-type]
            binding_sha256=document["binding_sha256"],  # type: ignore[arg-type]
        )

    def with_content(self, content: bytes) -> "StructuredOutputRef":
        return StructuredOutputRef(
            format=self.format,
            sha256=self.sha256,
            size=self.size,
            binding_sha256=self.binding_sha256,
            content=content,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AttestedArtifactBytes:
    binding_sha256: str
    content: bytes

    def __post_init__(self) -> None:
        _require_sha256(self.binding_sha256, "attested artifact binding")
        if type(self.content) is not bytes:
            raise PipelineError("attested artifact content must be bytes")


@dataclass(frozen=True, slots=True, kw_only=True)
class AttestedReceiptBytes:
    """Exact bytes returned only by an injected trusted resolver/attestor."""

    attestor_id: str
    receipt_bytes: bytes
    artifacts: tuple[AttestedArtifactBytes, ...]

    def __post_init__(self) -> None:
        _require_text(self.attestor_id, "receipt attestor_id")
        if type(self.receipt_bytes) is not bytes or not self.receipt_bytes:
            raise PipelineError("attested receipt bytes are missing")
        if type(self.artifacts) is not tuple or any(
            type(item) is not AttestedArtifactBytes for item in self.artifacts
        ):
            raise PipelineError("attested receipt artifacts are invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ArgvParameter:
    name: str
    flag: str
    kind: ParameterKind
    required: bool = True

    def __post_init__(self) -> None:
        if type(self.name) is not str or not PARAMETER_NAME_RE.fullmatch(self.name):
            raise PipelineError("argv parameter name is invalid")
        if type(self.flag) is not str or not FLAG_RE.fullmatch(self.flag):
            raise PipelineError("argv parameter flag is invalid")
        if type(self.kind) is not ParameterKind:
            raise PipelineError("argv parameter kind is invalid")
        if type(self.required) is not bool:
            raise PipelineError("argv parameter required must be boolean")

    def validate(self, value: object) -> str:
        if self.kind is not ParameterKind.PATH:
            raise PipelineError(f"unsupported argv parameter kind for {self.name}")
        if type(value) is not str:
            raise PipelineError(f"argv parameter {self.name} must be a string path")
        if not value or "\x00" in value:
            raise PipelineError(f"argv parameter {self.name} is not a valid lexical path")
        if value.startswith("-"):
            raise PipelineError(f"argv parameter {self.name} must not inject an option")
        return value


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckDefinition:
    check_id: str
    tier: CheckTier
    execution: CheckExecution
    argv_prefix: tuple[str, ...]
    parameters: tuple[ArgvParameter, ...] = ()
    timeout_milliseconds: int | None = None
    instrumentation: CheckInstrumentation = CheckInstrumentation.NONE
    allowed_skips: tuple[str, ...] = ()
    required_structured_formats: tuple[StructuredFormat, ...] = ()
    audited_baseline_milliseconds: int | None = None
    runtime_ceiling_milliseconds: int | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.check_id, "check_id")
        if type(self.tier) is not CheckTier or type(self.execution) is not CheckExecution:
            raise PipelineError("check tier or execution mode is invalid")
        if type(self.instrumentation) is not CheckInstrumentation:
            raise PipelineError("check instrumentation is invalid")
        if type(self.argv_prefix) is not tuple or any(
            type(item) is not str or not item or "\x00" in item
            for item in self.argv_prefix
        ):
            raise PipelineError("check argv prefix must contain exact tokens")
        if type(self.parameters) is not tuple or any(
            type(item) is not ArgvParameter for item in self.parameters
        ):
            raise PipelineError("check parameters are invalid")
        names = tuple(item.name for item in self.parameters)
        flags = tuple(item.flag for item in self.parameters)
        if len(names) != len(set(names)) or len(flags) != len(set(flags)):
            raise PipelineError("check parameters must be unique")
        optional_seen = False
        for parameter in self.parameters:
            optional_seen = optional_seen or not parameter.required
            if optional_seen and parameter.required:
                raise PipelineError("required parameters must precede optional ones")
        if self.timeout_milliseconds is not None and (
            type(self.timeout_milliseconds) is not int
            or self.timeout_milliseconds <= 0
        ):
            raise PipelineError("check timeout must be positive milliseconds")
        if type(self.allowed_skips) is not tuple or any(
            type(item) is not str or not item for item in self.allowed_skips
        ):
            raise PipelineError("allowed skips are invalid")
        if len(self.allowed_skips) != len(set(self.allowed_skips)):
            raise PipelineError("allowed skips must be unique")
        if type(self.required_structured_formats) is not tuple or any(
            type(item) is not StructuredFormat
            for item in self.required_structured_formats
        ):
            raise PipelineError("required structured formats are invalid")
        if len(self.required_structured_formats) != len(
            set(self.required_structured_formats)
        ):
            raise PipelineError("required structured formats must be unique")
        for label, value in (
            ("baseline", self.audited_baseline_milliseconds),
            ("ceiling", self.runtime_ceiling_milliseconds),
        ):
            if value is not None and (type(value) is not int or value <= 0):
                raise PipelineError(f"check runtime {label} is invalid")
        if (self.audited_baseline_milliseconds is None) != (
            self.runtime_ceiling_milliseconds is None
        ):
            raise PipelineError("runtime baseline and ceiling must be paired")
        if (
            self.audited_baseline_milliseconds is not None
            and self.runtime_ceiling_milliseconds is not None
            and self.runtime_ceiling_milliseconds < self.audited_baseline_milliseconds
        ):
            raise PipelineError("runtime ceiling precedes baseline")
        if self.execution is CheckExecution.LOCAL:
            if not self.argv_prefix or self.timeout_milliseconds is None:
                raise PipelineError("local check requires argv and timeout")
        elif (
            self.argv_prefix
            or self.parameters
            or self.timeout_milliseconds is not None
            or self.instrumentation is not CheckInstrumentation.NONE
        ):
            raise PipelineError("external check must not define local execution")
        if self.instrumentation is CheckInstrumentation.PYTEST and set(
            self.required_structured_formats
        ) != {StructuredFormat.JSON, StructuredFormat.JUNIT}:
            raise PipelineError("pytest instrumentation requires JSON and JUnit")

    @property
    def timeout_seconds(self) -> float:
        if self.timeout_milliseconds is None:
            raise PipelineError(f"check {self.check_id} is external-receipt-only")
        return self.timeout_milliseconds / 1000.0

    def render_argv(
        self,
        values: Mapping[str, object] | None = None,
    ) -> tuple[str, ...]:
        if self.execution is not CheckExecution.LOCAL:
            raise PipelineError(f"check {self.check_id} is external-receipt-only")
        supplied: Mapping[str, object] = {} if values is None else values
        if not isinstance(supplied, Mapping) or any(
            type(key) is not str for key in supplied
        ):
            raise PipelineError(f"check {self.check_id} parameters must be a mapping")
        known = frozenset(item.name for item in self.parameters)
        actual = frozenset(supplied)
        missing = frozenset(
            item.name
            for item in self.parameters
            if item.required and item.name not in supplied
        )
        extra = actual - known
        if missing or extra:
            raise PipelineError(
                f"check {self.check_id} parameters are not exact: "
                f"missing={sorted(missing)}; extra={sorted(extra)}"
            )
        result = list(self.argv_prefix)
        for parameter in self.parameters:
            if parameter.name in supplied:
                result.extend(
                    (parameter.flag, parameter.validate(supplied[parameter.name]))
                )
        return tuple(result)

    def accepts_argv(self, argv: object) -> bool:
        if type(argv) is not tuple or any(type(item) is not str for item in argv):
            return False
        if self.execution is CheckExecution.EXTERNAL_RECEIPT:
            return argv == ()
        if argv[: len(self.argv_prefix)] != self.argv_prefix:
            return False
        index = len(self.argv_prefix)
        values: dict[str, object] = {}
        for parameter in self.parameters:
            if index >= len(argv):
                if parameter.required:
                    return False
                continue
            if argv[index] != parameter.flag:
                if parameter.required:
                    return False
                continue
            if index + 1 >= len(argv):
                return False
            values[parameter.name] = argv[index + 1]
            index += 2
        if index != len(argv):
            return False
        try:
            return self.render_argv(values) == argv
        except PipelineError:
            return False


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessCapture:
    disposition: ProcessDisposition
    returncode: int | None
    stdout: str | None
    stderr: str | None
    structured_outputs: tuple[CapturedStructuredOutput, ...] = ()
    artifact_error: str | None = None

    def __post_init__(self) -> None:
        if type(self.disposition) is not ProcessDisposition:
            raise PipelineError("process disposition is invalid")
        if self.returncode is not None and type(self.returncode) is not int:
            raise PipelineError("process returncode is invalid")
        if self.stdout is not None and type(self.stdout) is not str:
            raise PipelineError("process stdout is invalid")
        if self.stderr is not None and type(self.stderr) is not str:
            raise PipelineError("process stderr is invalid")
        if type(self.structured_outputs) is not tuple or any(
            type(item) is not CapturedStructuredOutput
            for item in self.structured_outputs
        ):
            raise PipelineError("process structured outputs are invalid")
        if self.artifact_error is not None:
            _require_text(self.artifact_error, "process artifact error")


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckResult:
    check_id: str
    tier: CheckTier
    subject: str
    run_id: str
    status: CheckStatus
    origin: ResultOrigin
    argv: tuple[str, ...]
    executed_argv: tuple[str, ...]
    environment_keys: tuple[str, ...]
    duration_milliseconds: int
    returncode: int | None
    signal: int | None
    timed_out: bool
    logs_complete: bool
    stdout: str
    stderr: str
    skipped_tests: tuple[str, ...]
    structured_outputs: tuple[StructuredOutputRef, ...]
    failure_kind: FailureKind | None
    message: str | None

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "check_id",
            "tier",
            "subject",
            "run_id",
            "status",
            "origin",
            "argv",
            "executed_argv",
            "environment_keys",
            "duration_milliseconds",
            "returncode",
            "signal",
            "timed_out",
            "logs_complete",
            "stdout",
            "stderr",
            "skipped_tests",
            "structured_outputs",
            "failure_kind",
            "message",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.check_id, "check result check_id")
        if type(self.tier) is not CheckTier:
            raise PipelineError("check result tier is invalid")
        _require_text(self.subject, "check result subject")
        if type(self.run_id) is not str or not RUN_ID_RE.fullmatch(self.run_id):
            raise PipelineError("check result run_id is invalid")
        if type(self.status) is not CheckStatus or type(self.origin) is not ResultOrigin:
            raise PipelineError("check result status or origin is invalid")
        for label, argv in (("argv", self.argv), ("executed_argv", self.executed_argv)):
            if type(argv) is not tuple or any(
                type(item) is not str or not item or "\x00" in item for item in argv
            ):
                raise PipelineError(f"check result {label} is invalid")
        if type(self.environment_keys) is not tuple or any(
            type(item) is not str or not item for item in self.environment_keys
        ):
            raise PipelineError("check result environment keys are invalid")
        if self.environment_keys != tuple(sorted(set(self.environment_keys))):
            raise PipelineError("check result environment keys are invalid")
        if type(self.duration_milliseconds) is not int or self.duration_milliseconds < 0:
            raise PipelineError("check result duration is invalid")
        if self.returncode is not None and type(self.returncode) is not int:
            raise PipelineError("check result returncode is invalid")
        if self.signal is not None and (
            type(self.signal) is not int or self.signal <= 0 or self.returncode != -self.signal
        ):
            raise PipelineError("check result signal is invalid")
        if type(self.timed_out) is not bool or type(self.logs_complete) is not bool:
            raise PipelineError("check result flags are invalid")
        if type(self.stdout) is not str or type(self.stderr) is not str:
            raise PipelineError("check result logs are invalid")
        if type(self.skipped_tests) is not tuple or any(
            type(item) is not str or not item for item in self.skipped_tests
        ):
            raise PipelineError("check result skipped tests are invalid")
        if len(self.skipped_tests) != len(set(self.skipped_tests)):
            raise PipelineError("check result skipped tests must be unique")
        if type(self.structured_outputs) is not tuple or any(
            type(item) is not StructuredOutputRef for item in self.structured_outputs
        ):
            raise PipelineError("check result structured outputs are invalid")
        bindings = tuple(item.binding_sha256 for item in self.structured_outputs)
        if len(bindings) != len(set(bindings)):
            raise PipelineError("check result structured outputs must be unique")
        if self.failure_kind is not None and type(self.failure_kind) is not FailureKind:
            raise PipelineError("check result failure kind is invalid")
        if self.message is not None:
            _require_text(self.message, "check result message")
        if self.timed_out and (self.returncode is not None or self.signal is not None):
            raise PipelineError("timed-out result must not claim exit or signal")
        if self.status is CheckStatus.PASSED:
            if (
                self.failure_kind is not None
                or self.message is not None
                or self.returncode != 0
                or self.signal is not None
                or self.timed_out
                or not self.logs_complete
            ):
                raise PipelineError("passed check result contains failing facts")
        elif self.failure_kind is None or self.message is None:
            raise PipelineError("failed check result requires failure details")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "check_id": self.check_id,
            "tier": self.tier.value,
            "subject": self.subject,
            "run_id": self.run_id,
            "status": self.status.value,
            "origin": self.origin.value,
            "argv": list(self.argv),
            "executed_argv": list(self.executed_argv),
            "environment_keys": list(self.environment_keys),
            "duration_milliseconds": self.duration_milliseconds,
            "returncode": self.returncode,
            "signal": self.signal,
            "timed_out": self.timed_out,
            "logs_complete": self.logs_complete,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "skipped_tests": list(self.skipped_tests),
            "structured_outputs": [item.to_document() for item in self.structured_outputs],
            "failure_kind": (
                None if self.failure_kind is None else self.failure_kind.value
            ),
            "message": self.message,
        }

    @classmethod
    def from_document(cls, value: object) -> "CheckResult":
        document = _require_exact_mapping(value, cls._KEYS, "check result")
        argv = _require_exact_list(document["argv"], "check result argv")
        executed = _require_exact_list(
            document["executed_argv"], "check result executed_argv"
        )
        environment_keys = _require_exact_list(
            document["environment_keys"], "check result environment_keys"
        )
        skipped = _require_exact_list(
            document["skipped_tests"], "check result skipped_tests"
        )
        outputs = _require_exact_list(
            document["structured_outputs"], "check result structured_outputs"
        )
        failure_raw = document["failure_kind"]
        failure = (
            None
            if failure_raw is None
            else _enum_value(FailureKind, failure_raw, "check result failure_kind")
        )
        return cls(
            check_id=document["check_id"],  # type: ignore[arg-type]
            tier=_enum_value(
                CheckTier,
                document["tier"],
                "check result tier",
            ),  # type: ignore[arg-type]
            subject=document["subject"],  # type: ignore[arg-type]
            run_id=document["run_id"],  # type: ignore[arg-type]
            status=_enum_value(
                CheckStatus,
                document["status"],
                "check result status",
            ),  # type: ignore[arg-type]
            origin=_enum_value(
                ResultOrigin,
                document["origin"],
                "check result origin",
            ),  # type: ignore[arg-type]
            argv=tuple(argv),  # type: ignore[arg-type]
            executed_argv=tuple(executed),  # type: ignore[arg-type]
            environment_keys=tuple(environment_keys),  # type: ignore[arg-type]
            duration_milliseconds=document["duration_milliseconds"],  # type: ignore[arg-type]
            returncode=document["returncode"],  # type: ignore[arg-type]
            signal=document["signal"],  # type: ignore[arg-type]
            timed_out=document["timed_out"],  # type: ignore[arg-type]
            logs_complete=document["logs_complete"],  # type: ignore[arg-type]
            stdout=document["stdout"],  # type: ignore[arg-type]
            stderr=document["stderr"],  # type: ignore[arg-type]
            skipped_tests=tuple(skipped),  # type: ignore[arg-type]
            structured_outputs=tuple(
                StructuredOutputRef.from_document(item) for item in outputs
            ),
            failure_kind=failure,  # type: ignore[arg-type]
            message=document["message"],  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckReceipt:
    tier: CheckTier
    subject: str
    status: CheckStatus
    origin: ResultOrigin
    attestor_id: str | None
    results: tuple[CheckResult, ...]

    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "tier",
            "subject",
            "status",
            "origin",
            "attestor_id",
            "results",
        }
    )

    def __post_init__(self) -> None:
        if type(self.tier) is not CheckTier:
            raise PipelineError("check receipt tier is invalid")
        _require_text(self.subject, "check receipt subject")
        if type(self.status) is not CheckStatus or type(self.origin) is not ResultOrigin:
            raise PipelineError("check receipt status or origin is invalid")
        if self.origin is ResultOrigin.LOCAL:
            if self.attestor_id is not None:
                raise PipelineError("local check receipt must not claim an attestor")
        elif self.attestor_id is None:
            raise PipelineError("external check receipt requires an attestor_id")
        else:
            _require_text(self.attestor_id, "check receipt attestor_id")
        if type(self.results) is not tuple or not self.results or any(
            type(item) is not CheckResult for item in self.results
        ):
            raise PipelineError("check receipt results are invalid")
        ids = tuple(item.check_id for item in self.results)
        run_ids = tuple(item.run_id for item in self.results)
        if len(ids) != len(set(ids)) or len(run_ids) != len(set(run_ids)):
            raise PipelineError("check receipt check and run IDs must be unique")
        if any(item.subject != self.subject for item in self.results):
            raise PipelineError("check receipt result subject mismatch")
        if any(item.origin is not self.origin for item in self.results):
            raise PipelineError("check receipt result origin mismatch")
        any_failed = any(item.status is CheckStatus.FAILED for item in self.results)
        if (self.status is CheckStatus.PASSED) == any_failed:
            raise PipelineError("check receipt status is inconsistent")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "tier": self.tier.value,
            "subject": self.subject,
            "status": self.status.value,
            "origin": self.origin.value,
            "attestor_id": self.attestor_id,
            "results": [item.to_document() for item in self.results],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_document())

    @classmethod
    def from_document(cls, value: object) -> "CheckReceipt":
        document = _require_exact_mapping(value, cls._KEYS, "check receipt")
        results = _require_exact_list(document["results"], "check receipt results")
        return cls(
            tier=_enum_value(
                CheckTier,
                document["tier"],
                "check receipt tier",
            ),  # type: ignore[arg-type]
            subject=document["subject"],  # type: ignore[arg-type]
            status=_enum_value(
                CheckStatus,
                document["status"],
                "check receipt status",
            ),  # type: ignore[arg-type]
            origin=_enum_value(
                ResultOrigin,
                document["origin"],
                "check receipt origin",
            ),  # type: ignore[arg-type]
            attestor_id=document["attestor_id"],  # type: ignore[arg-type]
            results=tuple(CheckResult.from_document(item) for item in results),
        )

    @classmethod
    def from_bytes(cls, value: bytes) -> "CheckReceipt":
        return cls.from_document(
            decode_canonical_json_bytes(value, label="check receipt")
        )


__all__ = [
    "ArgvParameter",
    "ArtifactRequest",
    "AttestedArtifactBytes",
    "AttestedReceiptBytes",
    "CapturedStructuredOutput",
    "CheckDefinition",
    "CheckExecution",
    "CheckInstrumentation",
    "CheckReceipt",
    "CheckResult",
    "CheckStatus",
    "CheckTier",
    "FailureKind",
    "ParameterKind",
    "ProcessCapture",
    "ProcessDisposition",
    "ResultOrigin",
    "SCHEMA_VERSION",
    "StructuredFormat",
    "StructuredOutputRef",
    "canonical_json_bytes",
    "decode_canonical_json_bytes",
]
