"""Strict normalized eligibility rows for full-release planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from typing import Any

from ..errors import PipelineError
from .model import (
    ARTIFACT_NAME_RE,
    CONTENT_REFERENCE_KEYS,
    PIN_REFERENCE_KEYS,
    PLAN_CORE_KEYS,
    PLAN_TARGET_KEYS,
    SOURCE_KEYS,
    SOURCE_SET_REFERENCE_KEYS,
    SUBMODULE_KEYS,
    WORKFLOW_REFERENCE_KEYS,
    exact_key_errors,
    is_core_id,
    is_execution_profile_id,
    is_exact_relative_path,
    is_identifier,
    is_positive_int,
    is_sha1,
    is_sha256,
    package_shape_errors,
    raise_shape_errors,
    SOURCE_REF_RE,
    SOURCE_URL_RE,
)


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


def _source_errors(value: object, label: str) -> list[str]:
    errors = exact_key_errors(value, SOURCE_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    if (
        not isinstance(value.get("url"), str)
        or SOURCE_URL_RE.fullmatch(value["url"]) is None
    ):
        errors.append(f"{label}.url is invalid")
    if (
        not isinstance(value.get("requested_ref"), str)
        or SOURCE_REF_RE.fullmatch(value["requested_ref"]) is None
    ):
        errors.append(f"{label}.requested_ref is invalid")
    if not is_sha1(value.get("commit")):
        errors.append(f"{label}.commit is invalid")
    if not is_sha1(value.get("tree")):
        errors.append(f"{label}.tree is invalid")
    submodules = value.get("submodules")
    if not isinstance(submodules, list):
        errors.append(f"{label}.submodules must be a list")
        return errors
    paths: list[str] = []
    for index, submodule in enumerate(submodules):
        sublabel = f"{label}.submodules[{index}]"
        suberrors = exact_key_errors(submodule, SUBMODULE_KEYS, sublabel)
        errors.extend(suberrors)
        if suberrors:
            continue
        assert isinstance(submodule, dict)
        path = submodule.get("path")
        if not is_exact_relative_path(path):
            errors.append(f"{sublabel}.path is invalid")
        else:
            paths.append(path)
        if not is_sha1(submodule.get("commit")):
            errors.append(f"{sublabel}.commit is invalid")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        errors.append(f"{label}.submodules must have unique sorted paths")
    return errors


def _target_errors(value: object, label: str) -> list[str]:
    errors = exact_key_errors(value, PLAN_TARGET_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    if value.get("architecture") not in {"arm64", "armhf"}:
        errors.append(f"{label}.architecture is invalid")
    if not is_execution_profile_id(value.get("execution_profile")):
        errors.append(f"{label}.execution_profile is invalid")
    artifact_name = value.get("artifact_name")
    if not isinstance(artifact_name, str) or ARTIFACT_NAME_RE.fullmatch(
        artifact_name
    ) is None:
        errors.append(f"{label}.artifact_name is invalid")
    if not is_sha256(value.get("artifact_sha256")):
        errors.append(f"{label}.artifact_sha256 is invalid")
    if not is_positive_int(value.get("artifact_size")):
        errors.append(f"{label}.artifact_size is invalid")
    if not is_sha256(value.get("selected_build_record_sha256")):
        errors.append(f"{label}.selected_build_record_sha256 is invalid")
    return errors


def release_core_row_shape_errors(
    row: object, label: str = "release core"
) -> list[str]:
    """Return strict shape and normalized-identity errors for one plan row."""

    errors = exact_key_errors(row, PLAN_CORE_KEYS, label)
    if errors:
        return errors
    assert isinstance(row, dict)
    core_id = row.get("core_id")
    if not is_core_id(core_id):
        errors.append(f"{label}.core_id is invalid")
    if not is_sha256(row.get("core_spec_sha256")):
        errors.append(f"{label}.core_spec_sha256 is invalid")
    errors.extend(
        _reference_errors(
            row.get("workflow"), WORKFLOW_REFERENCE_KEYS, f"{label}.workflow"
        )
    )
    errors.extend(_source_errors(row.get("source"), f"{label}.source"))
    errors.extend(_reference_errors(row.get("pin"), PIN_REFERENCE_KEYS, f"{label}.pin"))
    errors.extend(
        _reference_errors(
            row.get("source_set"),
            SOURCE_SET_REFERENCE_KEYS,
            f"{label}.source_set",
        )
    )
    errors.extend(
        _reference_errors(
            row.get("compatibility"),
            CONTENT_REFERENCE_KEYS,
            f"{label}.compatibility",
        )
    )
    errors.extend(package_shape_errors(row.get("package"), f"{label}.package"))

    if isinstance(core_id, str):
        workflow = row.get("workflow")
        pin = row.get("pin")
        source_set = row.get("source_set")
        compatibility = row.get("compatibility")
        package = row.get("package")
        if isinstance(workflow, dict) and workflow.get("path") != (
            f".github/workflows/build-{core_id}.yml"
        ):
            errors.append(f"{label}.workflow path is not core-owned")
        if isinstance(pin, dict):
            pin_id = pin.get("pin_id")
            if not is_identifier(pin_id) or not str(pin_id).startswith(f"{core_id}-"):
                errors.append(f"{label}.pin.pin_id is invalid")
            if pin.get("path") != f"pins/core-sets/{pin_id}.json":
                errors.append(f"{label}.pin path is not canonical")
        if isinstance(source_set, dict):
            source_set_id = source_set.get("source_set_id")
            if (
                not is_identifier(source_set_id)
                or not str(source_set_id).startswith(f"{core_id}-")
            ):
                errors.append(f"{label}.source_set.source_set_id is invalid")
            if source_set_id != (pin.get("pin_id") if isinstance(pin, dict) else None):
                errors.append(f"{label}.source_set does not match pin identity")
            if source_set.get("path") != f"pins/source-sets/{source_set_id}.json":
                errors.append(f"{label}.source_set path is not canonical")
        if isinstance(compatibility, dict) and compatibility.get("path") != (
            f"manifests/compatibility/{core_id}.json"
        ):
            errors.append(f"{label}.compatibility path is not canonical")
        if isinstance(package, dict) and package.get("name") != (
            f"{core_id}_libretro.zip"
        ):
            errors.append(f"{label}.package name is not core-owned")

    targets = row.get("targets")
    if not isinstance(targets, list) or not targets:
        errors.append(f"{label}.targets must be a nonempty list")
    else:
        architectures: list[str] = []
        for index, target in enumerate(targets):
            errors.extend(_target_errors(target, f"{label}.targets[{index}]"))
            if isinstance(target, dict) and isinstance(target.get("architecture"), str):
                architectures.append(target["architecture"])
        if architectures != sorted(architectures) or len(architectures) != len(
            set(architectures)
        ):
            errors.append(f"{label}.targets must have unique sorted architectures")
    return errors


def validate_release_core_row(
    row: object, label: str = "release core"
) -> dict[str, Any]:
    """Require one exact normalized and canonically eligible core row."""

    errors = release_core_row_shape_errors(row, label)
    raise_shape_errors(errors, label)
    assert isinstance(row, dict)
    return copy.deepcopy(row)


def normalize_release_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate, copy, sort, and reject duplicates in normalized core facts."""

    if isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence) or not rows:
        raise PipelineError("release plan requires at least one normalized core row")
    normalized = [
        validate_release_core_row(row, f"release cores[{index}]")
        for index, row in enumerate(rows)
    ]
    core_ids = [row["core_id"] for row in normalized]
    if len(core_ids) != len(set(core_ids)):
        raise PipelineError("release plan core rows must be unique")
    return sorted(normalized, key=lambda row: row["core_id"])


# A name that reads naturally to callers constructing plans.
canonical_release_rows = normalize_release_rows
