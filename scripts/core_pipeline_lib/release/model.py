"""Shared immutable values and validators for full-release records.

This module deliberately knows nothing about the command-line entrypoint or
repository-specific readers.  Callers pass facts only after validating their
source documents.  The release package then preserves those facts in strict,
portable documents with deterministic semantic identities.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import copy
import json
from pathlib import Path
import re
from typing import Any

from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..runtime import base_runner_evidence, runner_evidence_is_well_formed


FULL_RELEASE_PLAN_SCHEMA_REF = "../../manifests/full-release-plan.schema.json"
FULL_RELEASE_CORE_RESULT_SCHEMA_REF = (
    "../../manifests/full-release-core-result.schema.json"
)
FULL_RELEASE_CANDIDATE_SCHEMA_REF = (
    "../../manifests/full-release-candidate.schema.json"
)

# Short aliases keep the call sites readable while the long names remain the
# unambiguous public constants used by schemas and tests.
PLAN_SCHEMA_REF = FULL_RELEASE_PLAN_SCHEMA_REF
CORE_RESULT_SCHEMA_REF = FULL_RELEASE_CORE_RESULT_SCHEMA_REF
CANDIDATE_SCHEMA_REF = FULL_RELEASE_CANDIDATE_SCHEMA_REF

PLAN_SCHEMA_VERSION = 3
CORE_RESULT_SCHEMA_VERSION = 2
CANDIDATE_SCHEMA_VERSION = 2
VALIDATION_SCOPE = "static-build-only"
PUBLICATION = "disabled"
RELEASE_SCOPES = (
    "explicit",
    "canonical",
    "full-workflow-roster",
    "track-group",
)
RUNNER_SELECTORS = ("local", "github-actions", "github-actions-sim")

CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
EXECUTION_PROFILE_ID_RE = re.compile(r"^ra(?:32|64)-[a-z0-9-]+-v[0-9]+$")
REPOSITORY_PATH_RE = re.compile(
    r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$"
)
SOURCE_URL_RE = re.compile(
    r"^https://(?![^/\s]*@)(?![^\s]*[?#])[^\s/?#]+/[^\s?#]*\.git$"
)
SOURCE_REF_RE = re.compile(r"^refs/(?:heads|tags)/[^\s]+$")
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*_libretro\.zip$")
ARTIFACT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*_libretro\.so$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RUNNER_EVIDENCE_BY_SELECTOR: dict[str, dict[str, object]] = {
    "local": {
        "profile": "local",
        "mode": "native",
        "backend": "local-docker",
        "local_only": True,
        "publication": PUBLICATION,
    },
    "github-actions": {
        "profile": "github-actions",
        "mode": "native",
        "backend": "github-hosted-docker",
        "local_only": True,
        "publication": PUBLICATION,
    },
    "github-actions-sim": {
        "profile": "github-actions",
        "mode": "simulated",
        "backend": "local-docker",
        "local_only": True,
        "publication": PUBLICATION,
    },
}

PLAN_KEYS = frozenset(
    {
        "$schema",
        "schema_version",
        "candidate_id",
        "scope",
        "validation_scope",
        "local_only",
        "publication",
        "group",
        "repository",
        "cores",
        "summary",
        "content_sha256",
    }
)
REPOSITORY_KEYS = frozenset(
    {
        "head",
        "clean",
        "catalog",
        "toolchain_lock",
        "commit_blacklist",
        "pipeline_bundle",
        "workflow_audit",
        "orchestration",
    }
)
ORCHESTRATION_KEYS = frozenset({"coordinator", "worker"})
FILE_REFERENCE_KEYS = frozenset({"path", "file_sha256"})
CONTENT_REFERENCE_KEYS = frozenset({"path", "file_sha256", "content_sha256"})
PIPELINE_BUNDLE_REFERENCE_KEYS = frozenset({"file_sha256", "content_sha256"})
WORKFLOW_AUDIT_KEYS = frozenset(
    {
        "schema_version",
        "content_sha256",
        "core_workflow_count",
        "catalog_workflow_count",
        "shared_pipeline_workflows",
        "unmigrated_workflow_count",
    }
)
WORKFLOW_REFERENCE_KEYS = FILE_REFERENCE_KEYS
PIN_REFERENCE_KEYS = frozenset(
    {"path", "pin_id", "file_sha256", "content_sha256"}
)
SOURCE_SET_REFERENCE_KEYS = frozenset(
    {"path", "source_set_id", "file_sha256", "content_sha256"}
)
SOURCE_KEYS = frozenset(
    {"url", "requested_ref", "commit", "tree", "submodules"}
)
SUBMODULE_KEYS = frozenset({"path", "commit"})
PLAN_CORE_KEYS = frozenset(
    {
        "core_id",
        "core_spec_sha256",
        "workflow",
        "source",
        "pin",
        "source_set",
        "compatibility",
        "package",
        "targets",
        "core_group",
    }
)
PACKAGE_KEYS = frozenset({"name", "sha256", "size"})
PLAN_TARGET_KEYS = frozenset(
    {
        "architecture",
        "execution_profile",
        "artifact_name",
        "artifact_sha256",
        "artifact_size",
        "selected_build_record_sha256",
    }
)
PLAN_SUMMARY_KEYS = frozenset({"core_count", "target_count", "package_bytes"})

CORE_RESULT_KEYS = frozenset(
    {
        "$schema",
        "schema_version",
        "candidate_id",
        "core_id",
        "validation_scope",
        "local_only",
        "publication",
        "result",
        "core_group",
        "plan",
        "runner",
        "e2e",
        "package",
        "targets",
        "content_sha256",
    }
)
PLAN_IDENTITY_KEYS = frozenset({"file_sha256", "content_sha256"})
E2E_IDENTITY_KEYS = frozenset({"run_id", "file_sha256", "content_sha256"})
RESULT_TARGET_KEYS = frozenset(
    {
        "architecture",
        "artifact_sha256",
        "artifact_size",
        "build_record_sha256",
    }
)

CANDIDATE_KEYS = frozenset(
    {
        "$schema",
        "schema_version",
        "candidate_id",
        "validation_scope",
        "local_only",
        "publication",
        "result",
        "group",
        "plan",
        "runner",
        "assets",
        "summary",
        "asset_set_sha256",
        "content_sha256",
    }
)
CANDIDATE_PLAN_REFERENCE_KEYS = frozenset(
    {"path", "file_sha256", "content_sha256"}
)
CANDIDATE_ASSET_KEYS = frozenset(
    {"core_id", "path", "sha256", "size", "core_group", "result"}
)
CANDIDATE_RESULT_REFERENCE_KEYS = frozenset(
    {"path", "file_sha256", "content_sha256"}
)
CANDIDATE_SUMMARY_KEYS = frozenset(
    {"core_count", "asset_count", "asset_bytes"}
)


def compact_json_bytes(value: object) -> bytes:
    """Return the single canonical JSON encoding used for semantic hashes."""

    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def semantic_sha256(value: object) -> str:
    """Hash a semantic projection with compact, sorted JSON."""

    return sha256_bytes(compact_json_bytes(value))


def rendered_json_bytes(value: object) -> bytes:
    """Return the deterministic human-readable encoding used on disk."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def document_file_sha256(value: object) -> str:
    """Hash the deterministic rendered form of a JSON-compatible value."""

    return sha256_bytes(rendered_json_bytes(value))


def runner_contract_for_selector(selector: object) -> dict[str, object]:
    """Resolve one public runner selector to exact persisted runner evidence."""

    if not isinstance(selector, str) or selector not in RUNNER_EVIDENCE_BY_SELECTOR:
        raise PipelineError(
            "release runner selector must be local, github-actions, or "
            "github-actions-sim"
        )
    return copy.deepcopy(RUNNER_EVIDENCE_BY_SELECTOR[selector])


def runner_selector_for_contract(value: object) -> str:
    """Return the sole public selector represented by exact runner evidence."""

    if not runner_evidence_is_well_formed(value):
        raise PipelineError("release runner evidence is invalid")
    identity = base_runner_evidence(value)
    for selector, expected in RUNNER_EVIDENCE_BY_SELECTOR.items():
        if identity == expected:
            return selector
    raise PipelineError("release runner evidence has no public selector")


def exact_runner_for_selector(value: object, selector: object) -> bool:
    """Return whether runner evidence exactly represents ``selector``."""

    if not runner_evidence_is_well_formed(value):
        return False
    try:
        expected = runner_contract_for_selector(selector)
    except PipelineError:
        return False
    return base_runner_evidence(value) == expected


def is_sha1(value: object) -> bool:
    return isinstance(value, str) and SHA1_RE.fullmatch(value) is not None


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def is_positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def is_core_id(value: object) -> bool:
    return isinstance(value, str) and CORE_ID_RE.fullmatch(value) is not None


def is_identifier(value: object) -> bool:
    return isinstance(value, str) and IDENTIFIER_RE.fullmatch(value) is not None


def is_profile_id(value: object) -> bool:
    return isinstance(value, str) and PROFILE_ID_RE.fullmatch(value) is not None


def is_execution_profile_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and EXECUTION_PROFILE_ID_RE.fullmatch(value) is not None
    )


def is_exact_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return (
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts)
        and REPOSITORY_PATH_RE.fullmatch(value) is not None
    )


def exact_key_errors(value: object, keys: frozenset[str], label: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    if set(value) != keys:
        return [f"{label} fields are not exact"]
    return []


def _reference_errors(
    value: object,
    keys: frozenset[str],
    label: str,
) -> list[str]:
    errors = exact_key_errors(value, keys, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    if "path" in keys and not is_exact_relative_path(value.get("path")):
        errors.append(f"{label}.path is invalid")
    if not is_sha256(value.get("file_sha256")):
        errors.append(f"{label}.file_sha256 is invalid")
    if "content_sha256" in keys and not is_sha256(value.get("content_sha256")):
        errors.append(f"{label}.content_sha256 is invalid")
    return errors


def package_shape_errors(value: object, label: str = "package") -> list[str]:
    errors = exact_key_errors(value, PACKAGE_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    name = value.get("name")
    if not isinstance(name, str) or PACKAGE_NAME_RE.fullmatch(name) is None:
        errors.append(f"{label}.name is invalid")
    if not is_sha256(value.get("sha256")):
        errors.append(f"{label}.sha256 is invalid")
    if not is_positive_int(value.get("size")):
        errors.append(f"{label}.size is invalid")
    return errors


def result_target_shape_errors(value: object, label: str) -> list[str]:
    errors = exact_key_errors(value, RESULT_TARGET_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    if value.get("architecture") not in {"arm64", "armhf"}:
        errors.append(f"{label}.architecture is invalid")
    if not is_sha256(value.get("artifact_sha256")):
        errors.append(f"{label}.artifact_sha256 is invalid")
    if not is_positive_int(value.get("artifact_size")):
        errors.append(f"{label}.artifact_size is invalid")
    if not is_sha256(value.get("build_record_sha256")):
        errors.append(f"{label}.build_record_sha256 is invalid")
    return errors


def sorted_unique_mapping_rows(
    rows: object,
    *,
    key: str,
    label: str,
) -> bool:
    """Return whether rows are nonempty dictionaries sorted by a unique key."""

    if (
        not isinstance(rows, list)
        or not rows
        or any(not isinstance(row, dict) for row in rows)
    ):
        return False
    identities = [row.get(key) for row in rows]
    return (
        all(isinstance(identity, str) and identity for identity in identities)
        and len(identities) == len(set(identities))
        and identities == sorted(identities)
    )


def require_no_forbidden_keys(value: object, *, label: str) -> None:
    """Reject time and device claims recursively, including future aliases."""

    forbidden_exact = {
        "created_at",
        "updated_at",
        "timestamp",
        "timestamps",
        "device",
        "devices",
        "device_id",
        "device_ids",
        "device_profile",
        "device_profiles",
    }

    def visit(item: object, path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, str) and key in forbidden_exact:
                    raise PipelineError(f"{label} must not contain {path}{key}")
                visit(child, f"{path}{key}.")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}{index}.")

    visit(value, "")


def raise_shape_errors(errors: Iterable[str], label: str) -> None:
    errors = list(errors)
    if errors:
        raise PipelineError(f"invalid {label}: " + "; ".join(errors))


def deep_copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Make an ordinary independent dictionary from one normalized mapping."""

    return copy.deepcopy(dict(value))


def deep_copy_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [deep_copy_mapping(row) for row in rows]
