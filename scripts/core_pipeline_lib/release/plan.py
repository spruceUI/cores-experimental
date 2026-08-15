"""Pure construction and strict validation of full-release plans."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from pathlib import Path
from typing import Any

from ..errors import PipelineError
from ..foundation import atomic_create_json
from ..tracks import parse_group_tag
from .eligibility import normalize_release_rows, release_core_row_shape_errors
from .model import (
    CONTENT_REFERENCE_KEYS,
    FILE_REFERENCE_KEYS,
    FULL_RELEASE_PLAN_SCHEMA_REF,
    ORCHESTRATION_KEYS,
    PIPELINE_BUNDLE_REFERENCE_KEYS,
    PLAN_KEYS,
    PLAN_SCHEMA_VERSION,
    PLAN_SUMMARY_KEYS,
    PUBLICATION,
    RELEASE_SCOPES,
    REPOSITORY_KEYS,
    VALIDATION_SCOPE,
    WORKFLOW_AUDIT_KEYS,
    exact_key_errors,
    is_exact_relative_path,
    is_identifier,
    is_nonnegative_int,
    is_sha1,
    is_sha256,
    raise_shape_errors,
    require_no_forbidden_keys,
    semantic_sha256,
)


PLAN_GROUP_KEYS = frozenset(
    {
        "group_tag",
        "inventory_state",
        "track_registry",
        "tuning_registry",
        "release_roster",
        "spruce_branch_bases",
        "stable_core_count",
        "unstable_fallback_core_count",
        "test_core_count",
    }
)


def plan_group_shape_errors(value: object) -> list[str]:
    """Validate the exact manifest identities and state counts for one group."""

    errors = exact_key_errors(value, PLAN_GROUP_KEYS, "release plan group")
    if errors:
        return errors
    assert isinstance(value, dict)
    try:
        parse_group_tag(value.get("group_tag"))
    except PipelineError:
        errors.append("release plan group.group_tag is invalid")
    if value.get("inventory_state") not in {"stable", "unstable"}:
        errors.append("release plan group.inventory_state is invalid")
    expected_paths = {
        "track_registry": "manifests/core-tracks.json",
        "tuning_registry": "manifests/chipset-tunings.json",
        "release_roster": "manifests/spruce-release-roster.json",
        "spruce_branch_bases": "manifests/spruce-core-branch-bases.json",
    }
    for field, expected_path in expected_paths.items():
        errors.extend(
            _reference_errors(
                value.get(field),
                CONTENT_REFERENCE_KEYS,
                f"release plan group.{field}",
            )
        )
        reference = value.get(field)
        if isinstance(reference, dict) and reference.get("path") != expected_path:
            errors.append(f"release plan group.{field}.path is not canonical")
    for field in (
        "stable_core_count",
        "unstable_fallback_core_count",
        "test_core_count",
    ):
        if not is_nonnegative_int(value.get(field)):
            errors.append(f"release plan group.{field} is invalid")
    return errors


def release_plan_content_sha256(document: Mapping[str, Any]) -> str:
    """Hash every semantic plan field while excluding schema routing/digest."""

    material = {
        "schema_version": document.get("schema_version"),
        "candidate_id": document.get("candidate_id"),
        "scope": document.get("scope"),
        "validation_scope": document.get("validation_scope"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "group": document.get("group"),
        "repository": document.get("repository"),
        "cores": document.get("cores"),
        "summary": document.get("summary"),
    }
    return semantic_sha256(material)


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


def workflow_audit_content_sha256(value: Mapping[str, Any]) -> str:
    """Hash the compact workflow-topology projection bound by a plan."""

    material = {
        "schema_version": value.get("schema_version"),
        "core_workflow_count": value.get("core_workflow_count"),
        "catalog_workflow_count": value.get("catalog_workflow_count"),
        "shared_pipeline_workflows": value.get("shared_pipeline_workflows"),
        "unmigrated_workflow_count": value.get("unmigrated_workflow_count"),
    }
    return semantic_sha256(material)


def workflow_audit_shape_errors(value: object) -> list[str]:
    errors = exact_key_errors(
        value, WORKFLOW_AUDIT_KEYS, "plan.repository.workflow_audit"
    )
    if errors:
        return errors
    assert isinstance(value, dict)
    if type(value.get("schema_version")) is not int or value.get("schema_version") != 2:
        errors.append("plan.repository.workflow_audit.schema_version is invalid")
    for field in (
        "core_workflow_count",
        "catalog_workflow_count",
        "shared_pipeline_workflows",
        "unmigrated_workflow_count",
    ):
        if not is_nonnegative_int(value.get(field)):
            errors.append(f"plan.repository.workflow_audit.{field} is invalid")
    core_count = value.get("core_workflow_count")
    catalog_count = value.get("catalog_workflow_count")
    shared_count = value.get("shared_pipeline_workflows")
    unmigrated_count = value.get("unmigrated_workflow_count")
    if all(
        is_nonnegative_int(item)
        for item in (core_count, catalog_count, shared_count, unmigrated_count)
    ):
        if catalog_count > core_count:
            errors.append("plan.repository.workflow_audit catalog count exceeds roster")
        if shared_count > core_count:
            errors.append("plan.repository.workflow_audit shared count exceeds roster")
        if unmigrated_count != core_count - shared_count:
            errors.append(
                "plan.repository.workflow_audit unmigrated count is inconsistent"
            )
    if value.get("content_sha256") != workflow_audit_content_sha256(value):
        errors.append("plan.repository.workflow_audit.content_sha256 is invalid")
    return errors


def orchestration_shape_errors(value: object) -> list[str]:
    """Validate the exact coordinator and reusable-worker file identities."""

    label = "plan.repository.orchestration"
    errors = exact_key_errors(value, ORCHESTRATION_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    expected_paths = {
        "coordinator": ".github/workflows/release-candidate.yml",
        "worker": ".github/workflows/_build-one-core.yml",
    }
    for role, expected_path in expected_paths.items():
        reference_label = f"{label}.{role}"
        reference = value.get(role)
        errors.extend(
            _reference_errors(reference, FILE_REFERENCE_KEYS, reference_label)
        )
        if isinstance(reference, dict) and reference.get("path") != expected_path:
            errors.append(f"{reference_label}.path is not canonical")
    return errors


def repository_facts_shape_errors(value: object) -> list[str]:
    """Validate exact already-normalized tracked repository facts."""

    errors = exact_key_errors(value, REPOSITORY_KEYS, "plan.repository")
    if errors:
        return errors
    assert isinstance(value, dict)
    if not is_sha1(value.get("head")):
        errors.append("plan.repository.head is invalid")
    if value.get("clean") is not True:
        errors.append("plan.repository.clean must be true")
    errors.extend(
        _reference_errors(
            value.get("catalog"), FILE_REFERENCE_KEYS, "plan.repository.catalog"
        )
    )
    errors.extend(
        _reference_errors(
            value.get("toolchain_lock"),
            CONTENT_REFERENCE_KEYS,
            "plan.repository.toolchain_lock",
        )
    )
    errors.extend(workflow_audit_shape_errors(value.get("workflow_audit")))
    errors.extend(orchestration_shape_errors(value.get("orchestration")))
    errors.extend(
        _reference_errors(
            value.get("commit_blacklist"),
            CONTENT_REFERENCE_KEYS,
            "plan.repository.commit_blacklist",
        )
    )
    errors.extend(
        _reference_errors(
            value.get("pipeline_bundle"),
            PIPELINE_BUNDLE_REFERENCE_KEYS,
            "plan.repository.pipeline_bundle",
        )
    )
    catalog = value.get("catalog")
    if (
        isinstance(catalog, dict)
        and catalog.get("path") != "manifests/core-builds.json"
    ):
        errors.append("plan.repository.catalog path is not canonical")
    return errors


def release_plan_shape_errors(document: object) -> list[str]:
    """Return all strict structure and semantic-consistency errors."""

    errors = exact_key_errors(document, PLAN_KEYS, "release plan")
    if errors:
        return errors
    assert isinstance(document, dict)
    if document.get("$schema") != FULL_RELEASE_PLAN_SCHEMA_REF:
        errors.append("release plan schema reference is invalid")
    if type(document.get("schema_version")) is not int or document.get(
        "schema_version"
    ) != PLAN_SCHEMA_VERSION:
        errors.append("release plan schema_version is invalid")
    if not is_identifier(document.get("candidate_id")):
        errors.append("release plan candidate_id is invalid")
    if document.get("scope") not in RELEASE_SCOPES:
        errors.append("release plan scope is invalid")
    if document.get("validation_scope") != VALIDATION_SCOPE:
        errors.append("release plan validation_scope is invalid")
    if document.get("local_only") is not True:
        errors.append("release plan must be local-only")
    if document.get("publication") != PUBLICATION:
        errors.append("release plan publication must be disabled")
    group = document.get("group")
    if document.get("scope") == "track-group":
        errors.extend(plan_group_shape_errors(group))
    elif group is not None:
        errors.append("release plan group is only valid for track-group scope")
    errors.extend(repository_facts_shape_errors(document.get("repository")))

    cores = document.get("cores")
    core_ids: list[str] = []
    target_count = 0
    package_bytes = 0
    selected_states: list[str] = []
    if not isinstance(cores, list) or not cores:
        errors.append("release plan cores must be a nonempty list")
    else:
        for index, row in enumerate(cores):
            errors.extend(
                release_core_row_shape_errors(row, f"release plan cores[{index}]")
            )
            if isinstance(row, dict):
                core_id = row.get("core_id")
                if isinstance(core_id, str):
                    core_ids.append(core_id)
                targets = row.get("targets")
                if isinstance(targets, list):
                    target_count += len(targets)
                package = row.get("package")
                if isinstance(package, dict) and type(package.get("size")) is int:
                    package_bytes += package["size"]
                core_group = row.get("core_group")
                if isinstance(core_group, dict) and isinstance(
                    core_group.get("selected_state"), str
                ):
                    selected_states.append(core_group["selected_state"])
        if core_ids != sorted(core_ids) or len(core_ids) != len(set(core_ids)):
            errors.append("release plan cores must have unique sorted core_id values")
    if document.get("scope") == "track-group":
        if len(selected_states) != len(core_ids):
            errors.append("track-group plan cores must all preserve group selections")
        if isinstance(group, dict):
            group_tag = group.get("group_tag")
            if any(
                isinstance(row, dict)
                and isinstance(row.get("core_group"), dict)
                and row["core_group"].get("group_tag") != group_tag
                for row in cores or ()
            ):
                errors.append("track-group plan core selectors differ from plan group")
            expected_counts = {
                "stable_core_count": selected_states.count("stable"),
                "unstable_fallback_core_count": selected_states.count(
                    "unstable_fallback"
                ),
                "test_core_count": selected_states.count("test"),
            }
            for field, expected in expected_counts.items():
                if group.get(field) != expected:
                    errors.append(f"release plan group.{field} is inconsistent")
            expected_state = (
                "stable"
                if expected_counts["stable_core_count"] == len(core_ids)
                else "unstable"
            )
            if group.get("inventory_state") != expected_state:
                errors.append("release plan group.inventory_state is inconsistent")
    elif selected_states:
        errors.append("legacy release plan cores must not contain group selections")

    summary = document.get("summary")
    summary_errors = exact_key_errors(
        summary, PLAN_SUMMARY_KEYS, "release plan summary"
    )
    errors.extend(summary_errors)
    if not summary_errors:
        assert isinstance(summary, dict)
        for key in PLAN_SUMMARY_KEYS:
            if not is_nonnegative_int(summary.get(key)):
                errors.append(f"release plan summary.{key} is invalid")
        if summary.get("core_count") != len(core_ids):
            errors.append("release plan summary.core_count is inconsistent")
        if summary.get("target_count") != target_count:
            errors.append("release plan summary.target_count is inconsistent")
        if summary.get("package_bytes") != package_bytes:
            errors.append("release plan summary.package_bytes is inconsistent")
    if document.get("content_sha256") != release_plan_content_sha256(document):
        errors.append("release plan content_sha256 is invalid")
    try:
        require_no_forbidden_keys(document, label="release plan")
    except PipelineError as exc:
        errors.append(str(exc))
    return errors


def validate_release_plan(document: object) -> dict[str, Any]:
    """Require and return an independent exact release-plan document."""

    errors = release_plan_shape_errors(document)
    raise_shape_errors(errors, "release plan")
    assert isinstance(document, dict)
    return copy.deepcopy(document)


def construct_release_plan(
    *,
    candidate_id: str,
    scope: str,
    repository: Mapping[str, Any],
    cores: Sequence[Mapping[str, Any]],
    group: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a deterministic plan from validated, normalized facts.

    This function does not read repository files.  The entrypoint owns those
    reads and passes their already-validated identities here.
    """

    if not is_identifier(candidate_id):
        raise PipelineError("release candidate_id is invalid")
    if scope not in RELEASE_SCOPES:
        raise PipelineError("release scope is invalid")
    if (scope == "track-group") != (group is not None):
        raise PipelineError(
            "track-group scope requires one exact group; legacy scopes forbid it"
        )
    repository_copy = copy.deepcopy(dict(repository))
    repository_errors = repository_facts_shape_errors(repository_copy)
    raise_shape_errors(repository_errors, "release repository facts")
    rows = normalize_release_rows(cores)
    document: dict[str, Any] = {
        "$schema": FULL_RELEASE_PLAN_SCHEMA_REF,
        "schema_version": PLAN_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "scope": scope,
        "validation_scope": VALIDATION_SCOPE,
        "local_only": True,
        "publication": PUBLICATION,
        "group": copy.deepcopy(dict(group)) if group is not None else None,
        "repository": repository_copy,
        "cores": rows,
        "summary": {
            "core_count": len(rows),
            "target_count": sum(len(row["targets"]) for row in rows),
            "package_bytes": sum(row["package"]["size"] for row in rows),
        },
        "content_sha256": "",
    }
    document["content_sha256"] = release_plan_content_sha256(document)
    return validate_release_plan(document)


def plan_core(document: Mapping[str, Any], core_id: str) -> dict[str, Any]:
    """Return one independently copied row from a validated plan."""

    plan = validate_release_plan(document)
    for row in plan["cores"]:
        if row["core_id"] == core_id:
            return copy.deepcopy(row)
    raise PipelineError(f"release plan does not contain core {core_id}")


def write_release_plan(*, plan: Mapping[str, Any], output_path: Path) -> dict[str, Any]:
    """Create one immutable plan without replacing an existing path."""

    document = validate_release_plan(plan)
    if not isinstance(output_path, Path):
        raise PipelineError("release plan output path must be a Path")
    atomic_create_json(output_path, document)
    return document
