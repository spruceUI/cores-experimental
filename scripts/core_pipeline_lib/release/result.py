"""Portable one-core release-worker result construction and persistence."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from ..errors import PipelineError
from ..foundation import atomic_create_json, load_json, sha256_file
from ..runtime import runner_evidence_is_well_formed
from .model import (
    CORE_RESULT_KEYS,
    CORE_RESULT_SCHEMA_VERSION,
    E2E_IDENTITY_KEYS,
    FULL_RELEASE_CORE_RESULT_SCHEMA_REF,
    PLAN_IDENTITY_KEYS,
    PUBLICATION,
    VALIDATION_SCOPE,
    exact_key_errors,
    exact_runner_for_selector,
    is_core_id,
    is_identifier,
    is_sha256,
    package_shape_errors,
    raise_shape_errors,
    require_no_forbidden_keys,
    result_target_shape_errors,
    semantic_sha256,
)
from .plan import plan_core, validate_release_plan


E2E_FACT_KEYS = frozenset(
    {"run_id", "file_sha256", "content_sha256", "runner", "package", "targets"}
)


def core_result_content_sha256(document: Mapping[str, Any]) -> str:
    """Hash every semantic worker-result field except schema routing/digest."""

    material = {
        "schema_version": document.get("schema_version"),
        "candidate_id": document.get("candidate_id"),
        "core_id": document.get("core_id"),
        "validation_scope": document.get("validation_scope"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "result": document.get("result"),
        "plan": document.get("plan"),
        "runner": document.get("runner"),
        "e2e": document.get("e2e"),
        "package": document.get("package"),
        "targets": document.get("targets"),
    }
    return semantic_sha256(material)


def _identity_errors(value: object, keys: frozenset[str], label: str) -> list[str]:
    errors = exact_key_errors(value, keys, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    for field in keys:
        if field == "run_id":
            if not is_identifier(value.get(field)):
                errors.append(f"{label}.run_id is invalid")
        elif not is_sha256(value.get(field)):
            errors.append(f"{label}.{field} is invalid")
    return errors


def normalized_e2e_fact_errors(value: object) -> list[str]:
    """Validate facts supplied only after the entrypoint's deep E2E check."""

    errors = exact_key_errors(value, E2E_FACT_KEYS, "normalized E2E facts")
    if errors:
        return errors
    assert isinstance(value, dict)
    errors.extend(
        _identity_errors(
            {
                "run_id": value.get("run_id"),
                "file_sha256": value.get("file_sha256"),
                "content_sha256": value.get("content_sha256"),
            },
            E2E_IDENTITY_KEYS,
            "normalized E2E identity",
        )
    )
    if not runner_evidence_is_well_formed(value.get("runner")):
        errors.append("normalized E2E runner is invalid")
    errors.extend(package_shape_errors(value.get("package"), "normalized E2E package"))
    targets = value.get("targets")
    architectures: list[str] = []
    if not isinstance(targets, list) or not targets:
        errors.append("normalized E2E targets must be a nonempty list")
    else:
        for index, target in enumerate(targets):
            errors.extend(
                result_target_shape_errors(target, f"normalized E2E targets[{index}]")
            )
            if isinstance(target, dict) and isinstance(target.get("architecture"), str):
                architectures.append(target["architecture"])
        if architectures != sorted(architectures) or len(architectures) != len(
            set(architectures)
        ):
            errors.append(
                "normalized E2E targets must have unique sorted architectures"
            )
    return errors


def _result_shape_errors(document: object) -> list[str]:
    errors = exact_key_errors(document, CORE_RESULT_KEYS, "release core result")
    if errors:
        return errors
    assert isinstance(document, dict)
    if document.get("$schema") != FULL_RELEASE_CORE_RESULT_SCHEMA_REF:
        errors.append("release core result schema reference is invalid")
    if type(document.get("schema_version")) is not int or document.get(
        "schema_version"
    ) != CORE_RESULT_SCHEMA_VERSION:
        errors.append("release core result schema_version is invalid")
    if not is_identifier(document.get("candidate_id")):
        errors.append("release core result candidate_id is invalid")
    if not is_core_id(document.get("core_id")):
        errors.append("release core result core_id is invalid")
    if document.get("validation_scope") != VALIDATION_SCOPE:
        errors.append("release core result validation_scope is invalid")
    if document.get("local_only") is not True:
        errors.append("release core result must be local-only")
    if document.get("publication") != PUBLICATION:
        errors.append("release core result publication must be disabled")
    if document.get("result") != "passed":
        errors.append("release core result must be passed")
    errors.extend(
        _identity_errors(document.get("plan"), PLAN_IDENTITY_KEYS, "result plan")
    )
    if not runner_evidence_is_well_formed(document.get("runner")):
        errors.append("release core result runner is invalid")
    errors.extend(
        _identity_errors(document.get("e2e"), E2E_IDENTITY_KEYS, "result E2E")
    )
    errors.extend(package_shape_errors(document.get("package"), "result package"))

    core_id = document.get("core_id")
    package = document.get("package")
    if (
        isinstance(core_id, str)
        and isinstance(package, dict)
        and package.get("name") != f"{core_id}_libretro.zip"
    ):
        errors.append("release core result package is not core-owned")

    targets = document.get("targets")
    architectures: list[str] = []
    if not isinstance(targets, list) or not targets:
        errors.append("release core result targets must be a nonempty list")
    else:
        for index, target in enumerate(targets):
            errors.extend(
                result_target_shape_errors(target, f"result targets[{index}]")
            )
            if isinstance(target, dict) and isinstance(target.get("architecture"), str):
                architectures.append(target["architecture"])
        if architectures != sorted(architectures) or len(architectures) != len(
            set(architectures)
        ):
            errors.append(
                "release core result targets must have unique sorted architectures"
            )
    if document.get("content_sha256") != core_result_content_sha256(document):
        errors.append("release core result content_sha256 is invalid")
    try:
        require_no_forbidden_keys(document, label="release core result")
    except PipelineError as exc:
        errors.append(str(exc))
    return errors


def _planned_target_projection(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "architecture": target["architecture"],
            "artifact_sha256": target["artifact_sha256"],
            "artifact_size": target["artifact_size"],
        }
        for target in row["targets"]
    ]


def _result_target_projection(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    targets = document.get("targets")
    if not isinstance(targets, list):
        return []
    return [
        {
            "architecture": target.get("architecture"),
            "artifact_sha256": target.get("artifact_sha256"),
            "artifact_size": target.get("artifact_size"),
        }
        for target in targets
        if isinstance(target, dict)
    ]


def core_result_shape_errors(
    document: object,
    *,
    plan: Mapping[str, Any] | None = None,
    plan_file_sha256: str | None = None,
    runner_selector: str | None = None,
) -> list[str]:
    """Validate shape and, when supplied, exact plan/runner bindings."""

    errors = _result_shape_errors(document)
    if errors or not isinstance(document, dict):
        return errors
    if runner_selector is not None and not exact_runner_for_selector(
        document.get("runner"), runner_selector
    ):
        errors.append("release core result runner does not match requested selector")
    if plan is None:
        return errors
    try:
        validated_plan = validate_release_plan(plan)
        row = plan_core(validated_plan, document["core_id"])
    except PipelineError as exc:
        errors.append(str(exc))
        return errors
    if document.get("candidate_id") != validated_plan["candidate_id"]:
        errors.append("release core result candidate_id does not match plan")
    plan_identity = document.get("plan")
    if isinstance(plan_identity, dict):
        if plan_identity.get("content_sha256") != validated_plan["content_sha256"]:
            errors.append("release core result plan content identity is invalid")
        if plan_file_sha256 is not None and plan_identity.get(
            "file_sha256"
        ) != plan_file_sha256:
            errors.append("release core result plan file identity is invalid")
    if document.get("package") != row["package"]:
        errors.append("release core result package does not match plan")
    if _result_target_projection(document) != _planned_target_projection(row):
        errors.append("release core result targets do not match plan")
    return errors


def validate_core_result(
    document: object,
    *,
    plan: Mapping[str, Any] | None = None,
    plan_file_sha256: str | None = None,
    runner_selector: str | None = None,
) -> dict[str, Any]:
    """Require and return an independent portable worker-result document."""

    errors = core_result_shape_errors(
        document,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        runner_selector=runner_selector,
    )
    raise_shape_errors(errors, "release core result")
    assert isinstance(document, dict)
    return copy.deepcopy(document)


def construct_core_result(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    core_id: str,
    runner_selector: str,
    e2e: Mapping[str, Any],
) -> dict[str, Any]:
    """Construct a portable result from one deeply validated fresh E2E run."""

    validated_plan = validate_release_plan(plan)
    if not is_sha256(plan_file_sha256):
        raise PipelineError("release plan file SHA256 is invalid")
    row = plan_core(validated_plan, core_id)
    facts = copy.deepcopy(dict(e2e))
    if isinstance(facts.get("targets"), list) and all(
        isinstance(target, dict) for target in facts["targets"]
    ):
        facts["targets"] = sorted(
            facts["targets"], key=lambda target: str(target.get("architecture"))
        )
    raise_shape_errors(normalized_e2e_fact_errors(facts), "normalized E2E facts")
    if not exact_runner_for_selector(facts["runner"], runner_selector):
        raise PipelineError("normalized E2E runner does not match requested selector")
    if facts["package"] != row["package"]:
        raise PipelineError("fresh E2E package does not match planned package")
    if _result_target_projection(facts) != _planned_target_projection(row):
        raise PipelineError("fresh E2E targets do not match planned targets")

    document: dict[str, Any] = {
        "$schema": FULL_RELEASE_CORE_RESULT_SCHEMA_REF,
        "schema_version": CORE_RESULT_SCHEMA_VERSION,
        "candidate_id": validated_plan["candidate_id"],
        "core_id": core_id,
        "validation_scope": VALIDATION_SCOPE,
        "local_only": True,
        "publication": PUBLICATION,
        "result": "passed",
        "plan": {
            "file_sha256": plan_file_sha256,
            "content_sha256": validated_plan["content_sha256"],
        },
        "runner": copy.deepcopy(facts["runner"]),
        "e2e": {
            "run_id": facts["run_id"],
            "file_sha256": facts["file_sha256"],
            "content_sha256": facts["content_sha256"],
        },
        "package": copy.deepcopy(facts["package"]),
        "targets": copy.deepcopy(facts["targets"]),
        "content_sha256": "",
    }
    document["content_sha256"] = core_result_content_sha256(document)
    return validate_core_result(
        document,
        plan=validated_plan,
        plan_file_sha256=plan_file_sha256,
        runner_selector=runner_selector,
    )


def _require_regular_nonsymlink(path: Path, label: str) -> None:
    try:
        if path.is_symlink() or not path.is_file():
            raise PipelineError(f"{label} must be a regular non-symlink file")
    except OSError as exc:
        raise PipelineError(f"cannot inspect {label}: {exc}") from exc


def _load_exact_plan_file(
    plan: Mapping[str, Any], plan_path: Path
) -> tuple[dict[str, Any], str]:
    if not isinstance(plan_path, Path):
        raise PipelineError("release plan path must be a Path")
    _require_regular_nonsymlink(plan_path, "release plan")
    validated_plan = validate_release_plan(plan)
    if load_json(plan_path) != validated_plan:
        raise PipelineError("release plan file does not match supplied plan document")
    return validated_plan, sha256_file(plan_path)


def write_core_result(
    *,
    plan: Mapping[str, Any],
    plan_path: Path,
    core_id: str,
    runner_selector: str,
    e2e: Mapping[str, Any],
    package_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Validate fully, then atomically create one portable worker bundle.

    ``e2e`` must contain already deep-validated facts.  The package itself is
    independently rehashed here before any output directory is staged.
    """

    validated_plan, plan_file_sha256 = _load_exact_plan_file(plan, plan_path)
    document = construct_core_result(
        plan=validated_plan,
        plan_file_sha256=plan_file_sha256,
        core_id=core_id,
        runner_selector=runner_selector,
        e2e=e2e,
    )
    if not isinstance(package_path, Path):
        raise PipelineError("release result package path must be a Path")
    _require_regular_nonsymlink(package_path, "release result package")
    package = document["package"]
    if (
        package_path.name != package["name"]
        or package_path.stat().st_size != package["size"]
        or sha256_file(package_path) != package["sha256"]
    ):
        raise PipelineError("release result package bytes do not match E2E and plan")
    if not isinstance(output_dir, Path):
        raise PipelineError("release result output directory must be a Path")
    if os.path.lexists(output_dir):
        raise PipelineError(f"refusing to replace release result output: {output_dir}")

    # All validation is complete.  Only now may staging become visible.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.parent.is_symlink():
        raise PipelineError("release result output parent must not be a symlink")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.stage-", dir=output_dir.parent)
    )
    try:
        shutil.copyfile(package_path, temporary / package["name"])
        os.chmod(temporary / package["name"], 0o644)
        atomic_create_json(temporary / "result.json", document)
        staged_package = temporary / package["name"]
        if (
            staged_package.stat().st_size != package["size"]
            or sha256_file(staged_package) != package["sha256"]
            or load_json(temporary / "result.json") != document
        ):
            raise PipelineError("staged release result bytes failed verification")
        if os.path.lexists(output_dir):
            raise PipelineError(
                f"release result output appeared during staging: {output_dir}"
            )
        os.rename(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return document
