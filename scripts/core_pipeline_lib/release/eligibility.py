"""Strict normalized eligibility rows for full-release planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from typing import Any

from ..errors import PipelineError
from ..chipsets import CHIPSETS
from ..tracks import CORE_TRACKS, parse_group_tag
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
    is_profile_id,
    is_sha1,
    is_sha256,
    package_shape_errors,
    raise_shape_errors,
    SOURCE_REF_RE,
    SOURCE_URL_RE,
)


CORE_GROUP_KEYS = frozenset(
    {
        "schema_version",
        "validation_scope",
        "group_tag",
        "inventory_content_sha256",
        "track_registry_content_sha256",
        "tuning_registry_content_sha256",
        "spruce_branch_basis",
        "core_id",
        "variant_id",
        "requested_marker",
        "requested_chipset",
        "selected_chipset",
        "selected_state",
        "stability",
        "resolution",
        "test_origin_track",
        "pin",
        "source_commit",
        "execution_source",
        "recipe_compatibility",
        "selected_architectures",
        "tuning",
        "expected_outputs",
    }
)
CORE_GROUP_APPROVAL_KEYS = frozenset(
    {
        "approved_test_variant_id",
        "approved_test_origin_track",
        "approved_at",
        "approved_by",
        "reason",
        "previous_stable_variant_id",
        "source_registry_content_sha256",
    }
)
CORE_GROUP_TUNING_KEYS = frozenset(
    {
        "profile_id",
        "content_sha256",
        "properties",
        "compiler_argument_mapping_version",
        "compiler_arguments",
    }
)
CORE_GROUP_BRANCH_BASIS_KEYS = frozenset(
    {"basis_id", "basis_content_sha256"}
)
CORE_GROUP_OUTPUT_KEYS = frozenset({"targets", "metadata", "package"})
CORE_GROUP_RECIPE_COMPATIBILITY_KEYS = frozenset(
    {
        "model",
        "selected_pin_core_spec_sha256",
        "execution_core_spec_sha256",
        "core_spec_identity_match",
    }
)
CORE_GROUP_EXPECTED_TARGET_KEYS = frozenset({"artifact"})
CORE_GROUP_EXPECTED_ARTIFACT_KEYS = frozenset({"sha256", "size"})
CORE_GROUP_EXPECTED_PACKAGE_KEYS = frozenset(
    {"comparison", "name", "sha256", "size"}
)
CORE_GROUP_MARKER_KEYS = (
    "group_tag",
    "variant_id",
    "requested_marker",
    "requested_chipset",
    "selected_chipset",
    "selected_state",
    "stability",
    "resolution",
    "test_origin_track",
    "spruce_branch_basis",
    "pin_id",
    "source_commit",
    "selected_architectures",
)


def _artifact_identity_errors(value: object, label: str) -> list[str]:
    errors = exact_key_errors(value, CORE_GROUP_EXPECTED_ARTIFACT_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    if not is_sha256(value.get("sha256")):
        errors.append(f"{label}.sha256 is invalid")
    if not is_positive_int(value.get("size")):
        errors.append(f"{label}.size is invalid")
    return errors


def core_group_selection_shape_errors(
    value: object,
    label: str = "core group selection",
) -> list[str]:
    """Validate one exact build/E2E group selection admitted to a release."""

    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    allowed = CORE_GROUP_KEYS | ({"approval"} if "approval" in value else set())
    errors = exact_key_errors(value, frozenset(allowed), label)
    if errors:
        return errors
    if value.get("schema_version") != 1:
        errors.append(f"{label}.schema_version is invalid")
    if value.get("validation_scope") != "pinned-output-reproduction-v1":
        errors.append(f"{label}.validation_scope is invalid")
    try:
        track, marker, chipset = parse_group_tag(value.get("group_tag"))
    except PipelineError:
        errors.append(f"{label}.group_tag is invalid")
        track = marker = chipset = None
    for field in (
        "inventory_content_sha256",
        "track_registry_content_sha256",
        "tuning_registry_content_sha256",
        "variant_id",
    ):
        if not is_sha256(value.get(field)):
            errors.append(f"{label}.{field} is invalid")
    branch_basis = value.get("spruce_branch_basis")
    basis_errors = exact_key_errors(
        branch_basis,
        CORE_GROUP_BRANCH_BASIS_KEYS,
        f"{label}.spruce_branch_basis",
    )
    errors.extend(basis_errors)
    if not basis_errors:
        assert isinstance(branch_basis, dict)
        expected_basis_id = (
            "spruce-main" if track == "main" else "spruce-development"
        )
        if branch_basis.get("basis_id") != expected_basis_id:
            errors.append(f"{label}.spruce_branch_basis.basis_id is invalid")
        if not is_sha256(branch_basis.get("basis_content_sha256")):
            errors.append(
                f"{label}.spruce_branch_basis.basis_content_sha256 is invalid"
            )
    core_id = value.get("core_id")
    if not is_core_id(core_id):
        errors.append(f"{label}.core_id is invalid")
    if value.get("requested_marker") != marker:
        errors.append(f"{label}.requested_marker differs from group_tag")
    if value.get("requested_chipset") != chipset:
        errors.append(f"{label}.requested_chipset differs from group_tag")
    if value.get("selected_chipset") not in CHIPSETS:
        errors.append(f"{label}.selected_chipset is invalid")
    if value.get("test_origin_track") not in CORE_TRACKS:
        errors.append(f"{label}.test_origin_track is invalid")
    selected_state = value.get("selected_state")
    stability = value.get("stability")
    if marker == "stable":
        if selected_state not in {"stable", "unstable_fallback"}:
            errors.append(f"{label}.selected_state is invalid for a stable view")
    elif marker == "test" and selected_state != "test":
        errors.append(f"{label}.selected_state is invalid for a test view")
    expected_stability = "stable" if selected_state == "stable" else "unstable"
    if stability != expected_stability:
        errors.append(f"{label}.stability is inconsistent")
    if value.get("resolution") not in {
        "exact_stable",
        "universal_stable_fallback",
        "exact_test_unstable_fallback",
        "universal_test_unstable_fallback",
        "exact_test",
        "universal_test_fallback",
    }:
        errors.append(f"{label}.resolution is invalid")
    resolution = value.get("resolution")
    resolutions_by_state = {
        "stable": {"exact_stable", "universal_stable_fallback"},
        "unstable_fallback": {
            "exact_test_unstable_fallback",
            "universal_test_unstable_fallback",
        },
        "test": {"exact_test", "universal_test_fallback"},
    }
    if selected_state in resolutions_by_state and resolution not in resolutions_by_state[
        selected_state
    ]:
        errors.append(f"{label}.resolution is inconsistent with selected_state")
    exact_resolutions = {
        "exact_stable",
        "exact_test_unstable_fallback",
        "exact_test",
    }
    universal_resolutions = {
        "universal_stable_fallback",
        "universal_test_unstable_fallback",
        "universal_test_fallback",
    }
    if resolution in exact_resolutions and value.get("selected_chipset") != chipset:
        errors.append(f"{label}.selected_chipset differs from exact request")
    if resolution in universal_resolutions and (
        chipset == "universal" or value.get("selected_chipset") != "universal"
    ):
        errors.append(f"{label}.universal fallback chipset is inconsistent")

    pin = value.get("pin")
    errors.extend(_reference_errors(pin, PIN_REFERENCE_KEYS, f"{label}.pin"))
    if isinstance(pin, dict) and isinstance(core_id, str):
        pin_id = pin.get("pin_id")
        if not is_identifier(pin_id) or not str(pin_id).startswith(f"{core_id}-"):
            errors.append(f"{label}.pin.pin_id is invalid")
        if pin.get("path") != f"pins/core-sets/{pin_id}.json":
            errors.append(f"{label}.pin.path is not canonical")
    if not is_sha1(value.get("source_commit")):
        errors.append(f"{label}.source_commit is invalid")
    errors.extend(_source_errors(value.get("execution_source"), f"{label}.execution_source"))
    execution_source = value.get("execution_source")
    if isinstance(execution_source, dict) and execution_source.get("commit") != value.get(
        "source_commit"
    ):
        errors.append(f"{label}.execution_source.commit differs from source_commit")

    compatibility = value.get("recipe_compatibility")
    compatibility_errors = exact_key_errors(
        compatibility,
        CORE_GROUP_RECIPE_COMPATIBILITY_KEYS,
        f"{label}.recipe_compatibility",
    )
    errors.extend(compatibility_errors)
    if not compatibility_errors:
        assert isinstance(compatibility, dict)
        if compatibility.get("model") != "source-normalized-build-contract-v1":
            errors.append(f"{label}.recipe_compatibility.model is invalid")
        for field in (
            "selected_pin_core_spec_sha256",
            "execution_core_spec_sha256",
        ):
            if not is_sha256(compatibility.get(field)):
                errors.append(f"{label}.recipe_compatibility.{field} is invalid")
        if type(compatibility.get("core_spec_identity_match")) is not bool:
            errors.append(
                f"{label}.recipe_compatibility.core_spec_identity_match is invalid"
            )

    architectures = value.get("selected_architectures")
    if (
        not isinstance(architectures, list)
        or not architectures
        or architectures != sorted(architectures)
        or len(architectures) != len(set(architectures))
        or any(item not in {"arm64", "armhf"} for item in architectures)
    ):
        errors.append(f"{label}.selected_architectures is invalid")

    tuning = value.get("tuning")
    tuning_errors = exact_key_errors(tuning, CORE_GROUP_TUNING_KEYS, f"{label}.tuning")
    errors.extend(tuning_errors)
    if not tuning_errors:
        assert isinstance(tuning, dict)
        if not is_profile_id(tuning.get("profile_id")):
            errors.append(f"{label}.tuning.profile_id is invalid")
        if not is_sha256(tuning.get("content_sha256")):
            errors.append(f"{label}.tuning.content_sha256 is invalid")
        if not isinstance(tuning.get("properties"), dict):
            errors.append(f"{label}.tuning.properties must be an object")
        if not isinstance(tuning.get("compiler_argument_mapping_version"), str) or not tuning.get(
            "compiler_argument_mapping_version"
        ):
            errors.append(
                f"{label}.tuning.compiler_argument_mapping_version is invalid"
            )
        arguments = tuning.get("compiler_arguments")
        if not isinstance(arguments, list) or any(
            not isinstance(argument, str) or not argument for argument in arguments
        ):
            errors.append(f"{label}.tuning.compiler_arguments is invalid")

    outputs = value.get("expected_outputs")
    output_errors = exact_key_errors(outputs, CORE_GROUP_OUTPUT_KEYS, f"{label}.expected_outputs")
    errors.extend(output_errors)
    if not output_errors:
        assert isinstance(outputs, dict)
        targets = outputs.get("targets")
        if not isinstance(targets, dict) or set(targets) != set(architectures or ()):
            errors.append(f"{label}.expected_outputs.targets differ from selected architectures")
        else:
            for architecture, target in targets.items():
                target_label = f"{label}.expected_outputs.targets.{architecture}"
                target_errors = exact_key_errors(
                    target, CORE_GROUP_EXPECTED_TARGET_KEYS, target_label
                )
                errors.extend(target_errors)
                if not target_errors:
                    errors.extend(
                        _artifact_identity_errors(
                            target["artifact"], f"{target_label}.artifact"
                        )
                    )
        errors.extend(
            _artifact_identity_errors(
                outputs.get("metadata"), f"{label}.expected_outputs.metadata"
            )
        )
        package = outputs.get("package")
        package_errors = exact_key_errors(
            package,
            CORE_GROUP_EXPECTED_PACKAGE_KEYS,
            f"{label}.expected_outputs.package",
        )
        errors.extend(package_errors)
        if not package_errors:
            assert isinstance(package, dict)
            if package.get("comparison") != "exact":
                errors.append(
                    f"{label}.expected_outputs.package.comparison must be exact"
                )
            errors.extend(
                package_shape_errors(
                    {key: package.get(key) for key in ("name", "sha256", "size")},
                    f"{label}.expected_outputs.package",
                )
            )
            if isinstance(core_id, str) and package.get("name") != f"{core_id}_libretro.zip":
                errors.append(f"{label}.expected_outputs.package is not core-owned")

    approval = value.get("approval")
    if selected_state == "stable":
        approval_errors = exact_key_errors(
            approval, CORE_GROUP_APPROVAL_KEYS, f"{label}.approval"
        )
        errors.extend(approval_errors)
        if not approval_errors:
            assert isinstance(approval, dict)
            for field in (
                "approved_test_variant_id",
                "source_registry_content_sha256",
            ):
                if not is_sha256(approval.get(field)):
                    errors.append(f"{label}.approval.{field} is invalid")
            if approval.get("approved_test_origin_track") not in CORE_TRACKS:
                errors.append(f"{label}.approval.approved_test_origin_track is invalid")
            previous = approval.get("previous_stable_variant_id")
            if previous is not None and not is_sha256(previous):
                errors.append(f"{label}.approval.previous_stable_variant_id is invalid")
            for field in ("approved_at", "approved_by", "reason"):
                if not isinstance(approval.get(field), str) or not approval[field].strip():
                    errors.append(f"{label}.approval.{field} is invalid")
    elif approval is not None:
        errors.append(f"{label}.approval is only valid for a stable selection")
    return errors


def core_group_marker(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project the release-visible per-core group inventory marker."""

    errors = core_group_selection_shape_errors(dict(value))
    raise_shape_errors(errors, "core group selection")
    pin = value["pin"]
    return {
        "group_tag": value["group_tag"],
        "variant_id": value["variant_id"],
        "requested_marker": value["requested_marker"],
        "requested_chipset": value["requested_chipset"],
        "selected_chipset": value["selected_chipset"],
        "selected_state": value["selected_state"],
        "stability": value["stability"],
        "resolution": value["resolution"],
        "test_origin_track": value["test_origin_track"],
        "spruce_branch_basis": copy.deepcopy(value["spruce_branch_basis"]),
        "pin_id": pin["pin_id"],
        "source_commit": value["source_commit"],
        "selected_architectures": copy.deepcopy(value["selected_architectures"]),
    }


def core_group_marker_shape_errors(
    value: object, label: str = "core group marker"
) -> list[str]:
    """Validate the compact marker copied into candidate/overlay inventory."""

    errors = exact_key_errors(value, frozenset(CORE_GROUP_MARKER_KEYS), label)
    if errors:
        return errors
    assert isinstance(value, dict)
    try:
        _track, marker, chipset = parse_group_tag(value.get("group_tag"))
    except PipelineError:
        errors.append(f"{label}.group_tag is invalid")
        _track = marker = chipset = None
    branch_basis = value.get("spruce_branch_basis")
    basis_errors = exact_key_errors(
        branch_basis,
        CORE_GROUP_BRANCH_BASIS_KEYS,
        f"{label}.spruce_branch_basis",
    )
    errors.extend(basis_errors)
    if not basis_errors:
        assert isinstance(branch_basis, dict)
        expected_basis_id = (
            "spruce-main" if _track == "main" else "spruce-development"
        )
        if branch_basis.get("basis_id") != expected_basis_id:
            errors.append(f"{label}.spruce_branch_basis.basis_id is invalid")
        if not is_sha256(branch_basis.get("basis_content_sha256")):
            errors.append(
                f"{label}.spruce_branch_basis.basis_content_sha256 is invalid"
            )
    if not is_sha256(value.get("variant_id")):
        errors.append(f"{label}.variant_id is invalid")
    if value.get("requested_marker") != marker:
        errors.append(f"{label}.requested_marker differs from group_tag")
    if value.get("requested_chipset") != chipset:
        errors.append(f"{label}.requested_chipset differs from group_tag")
    if value.get("selected_chipset") not in CHIPSETS:
        errors.append(f"{label}.selected_chipset is invalid")
    selected_state = value.get("selected_state")
    if selected_state not in {"stable", "unstable_fallback", "test"}:
        errors.append(f"{label}.selected_state is invalid")
    expected_marker = "test" if selected_state == "test" else "stable"
    if marker != expected_marker:
        errors.append(f"{label}.selected_state is inconsistent with group_tag")
    if value.get("stability") != (
        "stable" if selected_state == "stable" else "unstable"
    ):
        errors.append(f"{label}.stability is inconsistent")
    if value.get("resolution") not in {
        "exact_stable",
        "universal_stable_fallback",
        "exact_test_unstable_fallback",
        "universal_test_unstable_fallback",
        "exact_test",
        "universal_test_fallback",
    }:
        errors.append(f"{label}.resolution is invalid")
    resolution = value.get("resolution")
    resolutions_by_state = {
        "stable": {"exact_stable", "universal_stable_fallback"},
        "unstable_fallback": {
            "exact_test_unstable_fallback",
            "universal_test_unstable_fallback",
        },
        "test": {"exact_test", "universal_test_fallback"},
    }
    if selected_state in resolutions_by_state and resolution not in resolutions_by_state[
        selected_state
    ]:
        errors.append(f"{label}.resolution is inconsistent with selected_state")
    exact_resolutions = {
        "exact_stable",
        "exact_test_unstable_fallback",
        "exact_test",
    }
    universal_resolutions = {
        "universal_stable_fallback",
        "universal_test_unstable_fallback",
        "universal_test_fallback",
    }
    if resolution in exact_resolutions and value.get("selected_chipset") != chipset:
        errors.append(f"{label}.selected_chipset differs from exact request")
    if resolution in universal_resolutions and (
        chipset == "universal" or value.get("selected_chipset") != "universal"
    ):
        errors.append(f"{label}.universal fallback chipset is inconsistent")
    if value.get("test_origin_track") not in CORE_TRACKS:
        errors.append(f"{label}.test_origin_track is invalid")
    if not is_identifier(value.get("pin_id")):
        errors.append(f"{label}.pin_id is invalid")
    if not is_sha1(value.get("source_commit")):
        errors.append(f"{label}.source_commit is invalid")
    architectures = value.get("selected_architectures")
    if (
        not isinstance(architectures, list)
        or not architectures
        or architectures != sorted(architectures)
        or len(architectures) != len(set(architectures))
        or any(item not in {"arm64", "armhf"} for item in architectures)
    ):
        errors.append(f"{label}.selected_architectures is invalid")
    return errors


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

    core_group = row.get("core_group")
    if core_group is not None:
        errors.extend(
            core_group_selection_shape_errors(core_group, f"{label}.core_group")
        )

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
        if isinstance(core_group, dict):
            if core_group.get("core_id") != core_id:
                errors.append(f"{label}.core_group owns a different core")
            recipe_compatibility = core_group.get("recipe_compatibility")
            if isinstance(recipe_compatibility, dict) and row.get(
                "core_spec_sha256"
            ) != recipe_compatibility.get("execution_core_spec_sha256"):
                errors.append(
                    f"{label}.core_spec_sha256 differs from group execution recipe"
                )
            if core_group.get("pin") != pin:
                errors.append(f"{label}.core_group pin differs from release pin")
            if core_group.get("source_commit") != row.get("source", {}).get(
                "commit"
            ):
                errors.append(f"{label}.core_group source differs from release source")
            if core_group.get("execution_source") != row.get("source"):
                errors.append(
                    f"{label}.core_group execution source differs from release source"
                )
            expected_package = core_group.get("expected_outputs", {}).get("package")
            if isinstance(expected_package, dict) and isinstance(package, dict) and {
                key: expected_package.get(key) for key in ("name", "sha256", "size")
            } != package:
                errors.append(f"{label}.core_group package differs from release package")

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
        if isinstance(core_group, dict):
            if core_group.get("selected_architectures") != architectures:
                errors.append(f"{label}.core_group architectures differ from targets")
            expected_targets = core_group.get("expected_outputs", {}).get("targets")
            actual_artifacts = {
                target.get("architecture"): {
                    "artifact": {
                        "sha256": target.get("artifact_sha256"),
                        "size": target.get("artifact_size"),
                    }
                }
                for target in targets
                if isinstance(target, dict)
            }
            if expected_targets != actual_artifacts:
                errors.append(f"{label}.core_group artifacts differ from targets")
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
