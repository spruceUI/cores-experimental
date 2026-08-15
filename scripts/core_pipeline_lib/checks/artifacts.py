"""Authenticate structured check artifacts and bind them to one invocation."""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET

from ..errors import PipelineError
from .model import (
    CapturedStructuredOutput,
    CheckDefinition,
    CheckInstrumentation,
    CheckResult,
    StructuredFormat,
    StructuredOutputRef,
    canonical_json_bytes,
    decode_canonical_json_bytes,
)


MAX_STRUCTURED_OUTPUT_BYTES = 32 * 1024 * 1024
PYTEST_REPORT_SCHEMA_VERSION = 1
PYTEST_REPORT_KEYS = frozenset(
    {
        "schema_version",
        "check_id",
        "subject_sha256",
        "run_id",
        "argv_sha256",
        "exitstatus",
        "tests",
    }
)
PYTEST_TEST_KEYS = frozenset({"node_id", "outcome"})
PYTEST_OUTCOMES = frozenset({"passed", "failed", "skipped"})
XML_DECLARATION_RE = re.compile(r"\A<\?xml(?:\s.*?)?\?>", re.DOTALL)
XML_ENCODING_RE = re.compile(
    r"\bencoding\s*=\s*(?P<quote>['\"])(?P<encoding>[^'\"]+)(?P=quote)",
    re.IGNORECASE,
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def argv_sha256(argv: tuple[str, ...]) -> str:
    return sha256_bytes(canonical_json_bytes(list(argv)))


def subject_sha256(subject: str) -> str:
    return sha256_bytes(subject.encode("utf-8"))


def binding_sha256(
    *,
    format: StructuredFormat,
    artifact_sha256: str,
    artifact_size: int,
    check_id: str,
    subject: str,
    run_id: str,
    argv: tuple[str, ...],
    executed_argv: tuple[str, ...],
) -> str:
    """Bind exact artifact bytes to one canonical and executed invocation."""

    return sha256_bytes(
        canonical_json_bytes(
            {
                "schema_version": 1,
                "format": format.value,
                "artifact_sha256": artifact_sha256,
                "artifact_size": artifact_size,
                "check_id": check_id,
                "subject": subject,
                "run_id": run_id,
                "argv": list(argv),
                "executed_argv": list(executed_argv),
            }
        )
    )


def _strict_pytest_report(
    content: bytes,
    *,
    check_id: str,
    subject: str,
    run_id: str,
    argv: tuple[str, ...],
    returncode: int,
) -> tuple[str, ...]:
    document = decode_canonical_json_bytes(
        content,
        label="pytest structured report",
        maximum_bytes=MAX_STRUCTURED_OUTPUT_BYTES,
    )
    if frozenset(document) != PYTEST_REPORT_KEYS:
        raise PipelineError("pytest structured report fields are not exact")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != PYTEST_REPORT_SCHEMA_VERSION
    ):
        raise PipelineError("pytest structured report schema_version is invalid")
    expected = {
        "check_id": check_id,
        "subject_sha256": subject_sha256(subject),
        "run_id": run_id,
        "argv_sha256": argv_sha256(argv),
    }
    for key, value in expected.items():
        if type(document[key]) is not str or document[key] != value:
            raise PipelineError(f"pytest structured report {key} mismatch")
    if type(document["exitstatus"]) is not int or document["exitstatus"] != returncode:
        raise PipelineError("pytest structured report exitstatus mismatch")
    tests = document["tests"]
    if type(tests) is not list:
        raise PipelineError("pytest structured report tests must be an array")
    node_ids: list[str] = []
    skipped: list[str] = []
    failed = False
    for item in tests:
        if type(item) is not dict or frozenset(item) != PYTEST_TEST_KEYS:
            raise PipelineError("pytest structured test result fields are not exact")
        node_id = item["node_id"]
        outcome = item["outcome"]
        if type(node_id) is not str or not node_id or "\x00" in node_id:
            raise PipelineError("pytest structured report node_id is invalid")
        if type(outcome) is not str or outcome not in PYTEST_OUTCOMES:
            raise PipelineError("pytest structured report outcome is invalid")
        node_ids.append(node_id)
        if outcome == "skipped":
            skipped.append(node_id)
        elif outcome == "failed":
            failed = True
    if len(node_ids) != len(set(node_ids)):
        raise PipelineError("pytest structured report repeats a test node")
    if returncode == 0 and failed:
        raise PipelineError("passing pytest exit contains a failed structured test")
    return tuple(skipped)


def _safe_junit_root(content: bytes) -> ET.Element:
    if not content or len(content) > MAX_STRUCTURED_OUTPUT_BYTES:
        raise PipelineError("JUnit bytes are missing or exceed the size limit")
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PipelineError("JUnit must use an unambiguous UTF-8 encoding") from exc
    if decoded.startswith("\ufeff"):
        decoded = decoded[1:]
    if "\x00" in decoded:
        raise PipelineError("JUnit must use an unambiguous UTF-8 encoding")
    declaration = XML_DECLARATION_RE.match(decoded)
    if declaration is not None:
        encodings = tuple(XML_ENCODING_RE.finditer(declaration.group(0)))
        if len(encodings) > 1:
            raise PipelineError("JUnit XML declaration repeats its encoding")
        if encodings and encodings[0].group("encoding").lower() not in {
            "utf-8",
            "utf8",
        }:
            raise PipelineError("JUnit XML declaration uses an unsupported encoding")
    upper = decoded.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise PipelineError("JUnit must not contain a DTD or entity declaration")
    try:
        root = ET.fromstring(content)
    except (ET.ParseError, LookupError, UnicodeError, ValueError) as exc:
        raise PipelineError(f"JUnit is not well-formed XML: {exc}") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise PipelineError("JUnit root must be testsuite or testsuites")
    return root


def _junit_identity(node_id: str) -> tuple[str, str]:
    parts = node_id.split("::")
    if len(parts) < 2 or not parts[0].endswith(".py"):
        raise PipelineError(f"pytest node ID cannot bind JUnit: {node_id}")
    module = parts[0][:-3].replace("/", ".")
    classname = ".".join((module, *parts[1:-1]))
    return classname, parts[-1]


def _validate_pytest_junit(content: bytes, skipped: tuple[str, ...]) -> None:
    root = _safe_junit_root(content)
    observed: list[tuple[str, str]] = []
    for testcase in root.iter("testcase"):
        if testcase.find("skipped") is None:
            continue
        classname = testcase.get("classname")
        name = testcase.get("name")
        if not classname or not name:
            raise PipelineError("skipped JUnit testcase lacks classname or name")
        observed.append((classname, name))
    expected = [_junit_identity(node_id) for node_id in skipped]
    if observed != expected:
        raise PipelineError(
            f"JUnit skipped tests differ from reporter: expected={expected!r}; "
            f"observed={observed!r}"
        )


def authenticate_captured_outputs(
    definition: CheckDefinition,
    *,
    check_id: str,
    subject: str,
    run_id: str,
    argv: tuple[str, ...],
    executed_argv: tuple[str, ...],
    returncode: int,
    outputs: tuple[CapturedStructuredOutput, ...],
) -> tuple[tuple[StructuredOutputRef, ...], tuple[str, ...]]:
    """Parse raw bytes, reject duplicates, and mint invocation-bound refs."""

    formats = tuple(item.format for item in outputs)
    if len(formats) != len(set(formats)):
        raise PipelineError("subprocess capture repeats a structured output format")
    if set(formats) != set(definition.required_structured_formats):
        raise PipelineError(
            f"structured output formats are not exact for {definition.check_id}"
        )
    by_format = {item.format: item.content for item in outputs}
    skipped: tuple[str, ...] = ()
    if StructuredFormat.JSON in by_format:
        if definition.instrumentation is CheckInstrumentation.PYTEST:
            skipped = _strict_pytest_report(
                by_format[StructuredFormat.JSON],
                check_id=check_id,
                subject=subject,
                run_id=run_id,
                argv=argv,
                returncode=returncode,
            )
        else:
            decode_canonical_json_bytes(
                by_format[StructuredFormat.JSON],
                label=f"{definition.check_id} JSON artifact",
                maximum_bytes=MAX_STRUCTURED_OUTPUT_BYTES,
            )
    if StructuredFormat.JUNIT in by_format:
        if definition.instrumentation is CheckInstrumentation.PYTEST:
            _validate_pytest_junit(by_format[StructuredFormat.JUNIT], skipped)
        else:
            _safe_junit_root(by_format[StructuredFormat.JUNIT])

    references = []
    for output in outputs:
        digest = sha256_bytes(output.content)
        references.append(
            StructuredOutputRef(
                format=output.format,
                sha256=digest,
                size=len(output.content),
                binding_sha256=binding_sha256(
                    format=output.format,
                    artifact_sha256=digest,
                    artifact_size=len(output.content),
                    check_id=check_id,
                    subject=subject,
                    run_id=run_id,
                    argv=argv,
                    executed_argv=executed_argv,
                ),
                content=output.content,
            )
        )
    return tuple(references), skipped


def authenticate_external_outputs(
    definition: CheckDefinition,
    result: CheckResult,
    content_by_binding: dict[str, bytes],
) -> tuple[StructuredOutputRef, ...]:
    """Hydrate and authenticate every ref supplied by a trusted resolver."""

    outputs = tuple(
        CapturedStructuredOutput(
            format=reference.format,
            content=content_by_binding[reference.binding_sha256],
        )
        for reference in result.structured_outputs
    )
    authenticated, skipped = authenticate_captured_outputs(
        definition,
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
        raise PipelineError(f"external artifacts do not match {result.check_id} refs")
    if skipped != result.skipped_tests:
        raise PipelineError(f"external skip evidence mismatch for {result.check_id}")
    return authenticated


__all__ = [
    "MAX_STRUCTURED_OUTPUT_BYTES",
    "PYTEST_REPORT_SCHEMA_VERSION",
    "argv_sha256",
    "authenticate_captured_outputs",
    "authenticate_external_outputs",
    "binding_sha256",
    "sha256_bytes",
    "subject_sha256",
]
