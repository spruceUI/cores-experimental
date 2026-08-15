"""Stable persisted evidence for resolved runner contexts."""

from __future__ import annotations

import re

from .execution import HostExecutionProfile
from .model import RunnerContext


LEGACY_RUNNER_EVIDENCE_KEYS = frozenset(
    {"profile", "mode", "backend", "local_only", "publication"}
)
HARDENED_RUNNER_EVIDENCE_KEYS = frozenset(
    {
        "schema_version",
        "profile",
        "mode",
        "backend",
        "local_only",
        "publication",
        "execution_profile",
        "telemetry",
    }
)
EXECUTION_PROFILE_REFERENCE_KEYS = frozenset(
    {
        "path",
        "file_sha256",
        "content_sha256",
        "schema",
        "profile_id",
        "profile_content_sha256",
        "resource_class_id",
        "resource_class_content_sha256",
        "execution_label",
    }
)
TELEMETRY_REFERENCE_KEYS = frozenset({"path", "file_sha256", "content_sha256"})
SCHEMA_REFERENCE_KEYS = frozenset({"path", "file_sha256"})
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def _identity(context: RunnerContext) -> dict:
    return {
        "profile": context.profile,
        "mode": context.mode,
        "backend": context.backend,
        "local_only": context.local_only,
        "publication": context.publication,
    }


def runner_evidence(
    context: RunnerContext,
    execution_profile: HostExecutionProfile | None = None,
    telemetry_reference: dict | None = None,
) -> dict:
    """Persist legacy identity or one fully bound schema-v2 host runner."""

    identity = _identity(context)
    if execution_profile is None and telemetry_reference is None:
        return identity
    if execution_profile is None or telemetry_reference is None:
        raise ValueError(
            "hardened runner evidence requires both execution profile and telemetry"
        )
    if execution_profile.runner_identity() != {
        key: identity[key] for key in ("profile", "mode", "backend")
    }:
        raise ValueError("host execution profile does not match runner identity")
    value = {
        "schema_version": 2,
        **identity,
        "execution_profile": {
            **execution_profile.reference(),
            "execution_label": execution_profile.execution_label,
        },
        "telemetry": dict(telemetry_reference),
    }
    if not runner_evidence_is_well_formed(value):
        raise ValueError("hardened runner evidence is malformed")
    return value


def _base_identity_is_well_formed(value: dict) -> bool:
    if value.get("local_only") is not True or value.get("publication") != "disabled":
        return False
    identity = (value.get("profile"), value.get("mode"), value.get("backend"))
    return identity in {
        ("local", "native", "local-docker"),
        ("github-actions", "native", "github-hosted-docker"),
        ("github-actions", "simulated", "local-docker"),
    }


def runner_evidence_is_hardened(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != HARDENED_RUNNER_EVIDENCE_KEYS:
        return False
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 2:
        return False
    if not _base_identity_is_well_formed(value):
        return False
    execution = value.get("execution_profile")
    telemetry = value.get("telemetry")
    if (
        not isinstance(execution, dict)
        or set(execution) != EXECUTION_PROFILE_REFERENCE_KEYS
        or not isinstance(telemetry, dict)
        or set(telemetry) != TELEMETRY_REFERENCE_KEYS
    ):
        return False
    schema = execution.get("schema")
    if not isinstance(schema, dict) or set(schema) != SCHEMA_REFERENCE_KEYS:
        return False
    for mapping, names in (
        (
            execution,
            (
                "file_sha256",
                "content_sha256",
                "profile_content_sha256",
                "resource_class_content_sha256",
            ),
        ),
        (telemetry, ("file_sha256", "content_sha256")),
        (schema, ("file_sha256",)),
    ):
        if any(
            not isinstance(mapping.get(name), str)
            or SHA256_PATTERN.fullmatch(mapping[name]) is None
            for name in names
        ):
            return False
    if not all(
        isinstance(execution.get(name), str) and execution[name]
        for name in ("profile_id", "resource_class_id", "execution_label")
    ):
        return False
    registry_digest = execution["file_sha256"]
    schema_digest = schema["file_sha256"]
    telemetry_digest = telemetry["file_sha256"]
    expected_registry_path = (
        ".local-e2e/store/host-execution-profiles/sha256/"
        + registry_digest[:2]
        + "/"
        + registry_digest
    )
    expected_schema_path = (
        ".local-e2e/store/schemas/sha256/"
        + schema_digest[:2]
        + "/"
        + schema_digest
    )
    expected_telemetry_path = (
        ".local-e2e/store/host-build-telemetry/sha256/"
        + telemetry_digest[:2]
        + "/"
        + telemetry_digest
    )
    if (
        execution.get("path") != expected_registry_path
        or schema.get("path") != expected_schema_path
        or telemetry.get("path") != expected_telemetry_path
    ):
        return False
    if value.get("mode") == "native" and value.get("profile") == "github-actions":
        return False
    return True


def runner_evidence_is_well_formed(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) == LEGACY_RUNNER_EVIDENCE_KEYS:
        return _base_identity_is_well_formed(value)
    return runner_evidence_is_hardened(value)


def base_runner_evidence(value: object) -> dict | None:
    if not runner_evidence_is_well_formed(value):
        return None
    assert isinstance(value, dict)
    return {key: value[key] for key in LEGACY_RUNNER_EVIDENCE_KEYS}
