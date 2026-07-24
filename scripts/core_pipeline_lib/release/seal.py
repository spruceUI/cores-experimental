"""Fail-closed validation and sealing of complete full-release candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
    CANDIDATE_ASSET_KEYS,
    CANDIDATE_KEYS,
    CANDIDATE_PLAN_REFERENCE_KEYS,
    CANDIDATE_RESULT_REFERENCE_KEYS,
    CANDIDATE_SCHEMA_VERSION,
    CANDIDATE_SUMMARY_KEYS,
    FULL_RELEASE_CANDIDATE_SCHEMA_REF,
    PUBLICATION,
    VALIDATION_SCOPE,
    exact_key_errors,
    exact_runner_for_selector,
    is_core_id,
    is_exact_relative_path,
    is_identifier,
    is_nonnegative_int,
    is_positive_int,
    is_sha256,
    raise_shape_errors,
    require_no_forbidden_keys,
    runner_selector_for_contract,
    semantic_sha256,
)
from .plan import validate_release_plan
from .result import validate_core_result


def asset_set_content_sha256(assets: object) -> str:
    """Hash only sorted output-byte identities, independent of runner facts."""

    projection: list[dict[str, object]] = []
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, dict):
                raw_path = asset.get("path")
                name = Path(raw_path).name if isinstance(raw_path, str) else None
                projection.append(
                    {
                        "core_id": asset.get("core_id"),
                        "name": name,
                        "sha256": asset.get("sha256"),
                        "size": asset.get("size"),
                    }
                )
    return semantic_sha256(projection)


# The shorter public spelling is convenient in reports and tests.
asset_set_sha256 = asset_set_content_sha256


def release_candidate_content_sha256(document: Mapping[str, Any]) -> str:
    """Hash all semantic seal fields except schema routing/digest."""

    material = {
        "schema_version": document.get("schema_version"),
        "candidate_id": document.get("candidate_id"),
        "validation_scope": document.get("validation_scope"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "result": document.get("result"),
        "plan": document.get("plan"),
        "runner": document.get("runner"),
        "assets": document.get("assets"),
        "summary": document.get("summary"),
        "asset_set_sha256": document.get("asset_set_sha256"),
    }
    return semantic_sha256(material)


def _digest_reference_errors(
    value: object,
    keys: frozenset[str],
    label: str,
) -> list[str]:
    errors = exact_key_errors(value, keys, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    if not is_exact_relative_path(value.get("path")):
        errors.append(f"{label}.path is invalid")
    if not is_sha256(value.get("file_sha256")):
        errors.append(f"{label}.file_sha256 is invalid")
    if not is_sha256(value.get("content_sha256")):
        errors.append(f"{label}.content_sha256 is invalid")
    return errors


def _asset_errors(value: object, label: str) -> list[str]:
    errors = exact_key_errors(value, CANDIDATE_ASSET_KEYS, label)
    if errors:
        return errors
    assert isinstance(value, dict)
    core_id = value.get("core_id")
    if not is_core_id(core_id):
        errors.append(f"{label}.core_id is invalid")
    expected_path = f"assets/{core_id}_libretro.zip"
    if value.get("path") != expected_path:
        errors.append(f"{label}.path is not canonical")
    if not is_sha256(value.get("sha256")):
        errors.append(f"{label}.sha256 is invalid")
    if not is_positive_int(value.get("size")):
        errors.append(f"{label}.size is invalid")
    errors.extend(
        _digest_reference_errors(
            value.get("result"),
            CANDIDATE_RESULT_REFERENCE_KEYS,
            f"{label}.result",
        )
    )
    result = value.get("result")
    if isinstance(result, dict) and isinstance(core_id, str) and result.get(
        "path"
    ) != f"results/{core_id}/result.json":
        errors.append(f"{label}.result.path is not core-owned")
    return errors


def release_candidate_shape_errors(
    document: object,
    *,
    plan: Mapping[str, Any] | None = None,
    plan_file_sha256: str | None = None,
    runner_selector: str | None = None,
) -> list[str]:
    """Validate a pure candidate document and optional external bindings."""

    errors = exact_key_errors(document, CANDIDATE_KEYS, "release candidate")
    if errors:
        return errors
    assert isinstance(document, dict)
    if document.get("$schema") != FULL_RELEASE_CANDIDATE_SCHEMA_REF:
        errors.append("release candidate schema reference is invalid")
    if type(document.get("schema_version")) is not int or document.get(
        "schema_version"
    ) != CANDIDATE_SCHEMA_VERSION:
        errors.append("release candidate schema_version is invalid")
    if not is_identifier(document.get("candidate_id")):
        errors.append("release candidate candidate_id is invalid")
    if document.get("validation_scope") != VALIDATION_SCOPE:
        errors.append("release candidate validation_scope is invalid")
    if document.get("local_only") is not True:
        errors.append("release candidate must be local-only")
    if document.get("publication") != PUBLICATION:
        errors.append("release candidate publication must be disabled")
    if document.get("result") != "sealed":
        errors.append("release candidate result must be sealed")
    errors.extend(
        _digest_reference_errors(
            document.get("plan"),
            CANDIDATE_PLAN_REFERENCE_KEYS,
            "release candidate plan",
        )
    )
    plan_reference = document.get("plan")
    if isinstance(plan_reference, dict) and plan_reference.get("path") != "plan.json":
        errors.append("release candidate plan path is not canonical")
    if not runner_evidence_is_well_formed(document.get("runner")):
        errors.append("release candidate runner is invalid")
    if runner_selector is not None and not exact_runner_for_selector(
        document.get("runner"), runner_selector
    ):
        errors.append("release candidate runner does not match requested selector")

    assets = document.get("assets")
    core_ids: list[str] = []
    asset_bytes = 0
    if not isinstance(assets, list) or not assets:
        errors.append("release candidate assets must be a nonempty list")
    else:
        for index, asset in enumerate(assets):
            errors.extend(_asset_errors(asset, f"release candidate assets[{index}]"))
            if isinstance(asset, dict):
                if isinstance(asset.get("core_id"), str):
                    core_ids.append(asset["core_id"])
                if type(asset.get("size")) is int:
                    asset_bytes += asset["size"]
        if core_ids != sorted(core_ids) or len(core_ids) != len(set(core_ids)):
            errors.append(
                "release candidate assets must have unique sorted core_id values"
            )
    if document.get("asset_set_sha256") != asset_set_content_sha256(assets):
        errors.append("release candidate asset_set_sha256 is invalid")

    summary = document.get("summary")
    summary_errors = exact_key_errors(
        summary, CANDIDATE_SUMMARY_KEYS, "release candidate summary"
    )
    errors.extend(summary_errors)
    if not summary_errors:
        assert isinstance(summary, dict)
        for field in CANDIDATE_SUMMARY_KEYS:
            if not is_nonnegative_int(summary.get(field)):
                errors.append(f"release candidate summary.{field} is invalid")
        if summary.get("core_count") != len(core_ids):
            errors.append("release candidate summary.core_count is inconsistent")
        if summary.get("asset_count") != len(core_ids):
            errors.append("release candidate summary.asset_count is inconsistent")
        if summary.get("asset_bytes") != asset_bytes:
            errors.append("release candidate summary.asset_bytes is inconsistent")

    if plan is not None:
        try:
            validated_plan = validate_release_plan(plan)
        except PipelineError as exc:
            errors.append(str(exc))
        else:
            expected_core_ids = [row["core_id"] for row in validated_plan["cores"]]
            expected_packages = {
                row["core_id"]: row["package"] for row in validated_plan["cores"]
            }
            if document.get("candidate_id") != validated_plan["candidate_id"]:
                errors.append("release candidate candidate_id does not match plan")
            if core_ids != expected_core_ids:
                errors.append("release candidate asset set does not exactly match plan")
            if isinstance(assets, list):
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    core_id = asset.get("core_id")
                    package = expected_packages.get(core_id)
                    if package is None:
                        continue
                    if (
                        asset.get("path") != f"assets/{package['name']}"
                        or asset.get("sha256") != package["sha256"]
                        or asset.get("size") != package["size"]
                    ):
                        errors.append(
                            f"release candidate asset {core_id} differs from plan"
                        )
            if isinstance(plan_reference, dict):
                if plan_reference.get("content_sha256") != validated_plan[
                    "content_sha256"
                ]:
                    errors.append("release candidate plan content identity is invalid")
                if plan_file_sha256 is not None and plan_reference.get(
                    "file_sha256"
                ) != plan_file_sha256:
                    errors.append("release candidate plan file identity is invalid")

    if document.get("content_sha256") != release_candidate_content_sha256(document):
        errors.append("release candidate content_sha256 is invalid")
    try:
        require_no_forbidden_keys(document, label="release candidate")
    except PipelineError as exc:
        errors.append(str(exc))
    return errors


def validate_release_candidate(
    document: object,
    *,
    plan: Mapping[str, Any] | None = None,
    plan_file_sha256: str | None = None,
    runner_selector: str | None = None,
) -> dict[str, Any]:
    """Require and return an independent exact sealed-candidate document."""

    errors = release_candidate_shape_errors(
        document,
        plan=plan,
        plan_file_sha256=plan_file_sha256,
        runner_selector=runner_selector,
    )
    raise_shape_errors(errors, "release candidate")
    assert isinstance(document, dict)
    return copy.deepcopy(document)


def construct_release_candidate(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    runner_selector: str,
    results: Sequence[Mapping[str, Any]],
    result_file_sha256_by_core: Mapping[str, str],
) -> dict[str, Any]:
    """Purely construct a candidate from an exact complete result set."""

    validated_plan = validate_release_plan(plan)
    if not is_sha256(plan_file_sha256):
        raise PipelineError("release candidate plan file SHA256 is invalid")
    if isinstance(results, (str, bytes)) or not isinstance(results, Sequence):
        raise PipelineError("release candidate results must be a sequence")
    expected_core_ids = [row["core_id"] for row in validated_plan["cores"]]
    if any(not isinstance(result, Mapping) for result in results):
        raise PipelineError("release candidate results must contain only objects")
    supplied_results = [copy.deepcopy(dict(result)) for result in results]
    supplied_core_ids = [result.get("core_id") for result in supplied_results]
    if (
        any(not isinstance(core_id, str) for core_id in supplied_core_ids)
        or len(supplied_core_ids) != len(set(supplied_core_ids))
        or sorted(supplied_core_ids) != expected_core_ids
    ):
        raise PipelineError("release candidate requires the exact plan result set")
    supplied_results.sort(key=lambda result: result["core_id"])
    if set(result_file_sha256_by_core) != set(expected_core_ids) or any(
        not is_sha256(value) for value in result_file_sha256_by_core.values()
    ):
        raise PipelineError("release candidate result file identities are not exact")

    assets: list[dict[str, Any]] = []
    for result in supplied_results:
        core_id = result["core_id"]
        validate_core_result(
            result,
            plan=validated_plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector=runner_selector,
        )
        package = result["package"]
        assets.append(
            {
                "core_id": core_id,
                "path": f"assets/{package['name']}",
                "sha256": package["sha256"],
                "size": package["size"],
                "result": {
                    "path": f"results/{core_id}/result.json",
                    "file_sha256": result_file_sha256_by_core[core_id],
                    "content_sha256": result["content_sha256"],
                },
            }
        )
    document: dict[str, Any] = {
        "$schema": FULL_RELEASE_CANDIDATE_SCHEMA_REF,
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "candidate_id": validated_plan["candidate_id"],
        "validation_scope": VALIDATION_SCOPE,
        "local_only": True,
        "publication": PUBLICATION,
        "result": "sealed",
        "plan": {
            "path": "plan.json",
            "file_sha256": plan_file_sha256,
            "content_sha256": validated_plan["content_sha256"],
        },
        "runner": copy.deepcopy(supplied_results[0]["runner"]),
        "assets": assets,
        "summary": {
            "core_count": len(assets),
            "asset_count": len(assets),
            "asset_bytes": sum(asset["size"] for asset in assets),
        },
        "asset_set_sha256": asset_set_content_sha256(assets),
        "content_sha256": "",
    }
    document["content_sha256"] = release_candidate_content_sha256(document)
    return validate_release_candidate(
        document,
        plan=validated_plan,
        plan_file_sha256=plan_file_sha256,
        runner_selector=runner_selector,
    )


def _directory_entries(path: Path, label: str) -> dict[str, Path]:
    try:
        if path.is_symlink() or not path.is_dir():
            raise PipelineError(f"{label} must be a regular non-symlink directory")
        entries: dict[str, Path] = {}
        with os.scandir(path) as iterator:
            for entry in iterator:
                child = path / entry.name
                if entry.is_symlink():
                    raise PipelineError(f"{label} contains symlink {entry.name}")
                entries[entry.name] = child
        return entries
    except OSError as exc:
        raise PipelineError(f"cannot inspect {label}: {exc}") from exc


def _require_regular_file(path: Path, label: str) -> None:
    try:
        if path.is_symlink() or not path.is_file():
            raise PipelineError(f"{label} must be a regular non-symlink file")
    except OSError as exc:
        raise PipelineError(f"cannot inspect {label}: {exc}") from exc


def _load_bound_plan(
    plan: Mapping[str, Any], plan_path: Path
) -> tuple[dict[str, Any], str]:
    if not isinstance(plan_path, Path):
        raise PipelineError("release plan path must be a Path")
    _require_regular_file(plan_path, "release plan")
    validated_plan = validate_release_plan(plan)
    if load_json(plan_path) != validated_plan:
        raise PipelineError("release plan file does not match supplied plan document")
    return validated_plan, sha256_file(plan_path)


def _validated_result_tree(
    *,
    plan: Mapping[str, Any],
    plan_file_sha256: str,
    results_root: Path,
    runner_selector: str,
) -> tuple[list[dict[str, Any]], dict[str, Path], dict[str, Path], dict[str, str]]:
    """Validate the entire fan-in tree without creating any output."""

    expected_rows = {row["core_id"]: row for row in plan["cores"]}
    root_entries = _directory_entries(results_root, "release results root")
    if set(root_entries) != set(expected_rows):
        missing = sorted(set(expected_rows) - set(root_entries))
        unexpected = sorted(set(root_entries) - set(expected_rows))
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if unexpected:
            detail.append("unexpected=" + ",".join(unexpected))
        raise PipelineError("release result set is not exact: " + " ".join(detail))

    results: list[dict[str, Any]] = []
    result_paths: dict[str, Path] = {}
    package_paths: dict[str, Path] = {}
    result_file_hashes: dict[str, str] = {}
    for core_id in sorted(expected_rows):
        core_root = root_entries[core_id]
        entries = _directory_entries(core_root, f"release result {core_id}")
        package_name = expected_rows[core_id]["package"]["name"]
        if set(entries) != {"result.json", package_name}:
            raise PipelineError(
                f"{core_id}: release result bundle entries are not exact"
            )
        result_path = entries["result.json"]
        package_path = entries[package_name]
        _require_regular_file(result_path, f"{core_id} release result record")
        _require_regular_file(package_path, f"{core_id} release result package")
        result = load_json(result_path)
        if result.get("core_id") != core_id:
            raise PipelineError(
                f"{core_id}: release result directory identity is invalid"
            )
        result = validate_core_result(
            result,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector=runner_selector,
        )
        package = result["package"]
        planned_package = expected_rows[core_id]["package"]
        if package != planned_package:
            raise PipelineError(
                f"{core_id}: release package identity differs from plan"
            )
        if (
            package_path.stat().st_size != package["size"]
            or sha256_file(package_path) != package["sha256"]
        ):
            raise PipelineError(
                f"{core_id}: release package bytes differ from result and plan"
            )
        results.append(result)
        result_paths[core_id] = result_path
        package_paths[core_id] = package_path
        result_file_hashes[core_id] = sha256_file(result_path)
    return results, result_paths, package_paths, result_file_hashes


def validate_sealed_candidate_directory(
    *,
    candidate: Mapping[str, Any],
    output_dir: Path,
    plan: Mapping[str, Any] | None = None,
    runner_selector: str | None = None,
) -> dict[str, Any]:
    """Deeply validate an exact sealed output tree and every referenced byte."""

    if not isinstance(output_dir, Path):
        raise PipelineError("sealed candidate output directory must be a Path")
    if runner_selector is None:
        runner_selector = runner_selector_for_contract(candidate.get("runner"))
    root_entries = _directory_entries(output_dir, "sealed candidate directory")
    if set(root_entries) != {"assets", "candidate.json", "plan.json", "results"}:
        raise PipelineError("sealed candidate top-level entries are not exact")
    candidate_path = root_entries["candidate.json"]
    plan_path = root_entries["plan.json"]
    _require_regular_file(candidate_path, "sealed candidate record")
    _require_regular_file(plan_path, "sealed candidate plan")
    if load_json(candidate_path) != dict(candidate):
        raise PipelineError("sealed candidate record differs from supplied document")
    stored_plan = load_json(plan_path)
    validated_plan = validate_release_plan(plan if plan is not None else stored_plan)
    if stored_plan != validated_plan:
        raise PipelineError("sealed candidate plan bytes contain a different plan")
    plan_file_sha256 = sha256_file(plan_path)
    validated_candidate = validate_release_candidate(
        candidate,
        plan=validated_plan,
        plan_file_sha256=plan_file_sha256,
        runner_selector=runner_selector,
    )

    asset_entries = _directory_entries(
        root_entries["assets"], "sealed candidate assets"
    )
    result_entries = _directory_entries(
        root_entries["results"], "sealed candidate results"
    )
    expected_assets = {
        Path(asset["path"]).name: asset
        for asset in validated_candidate["assets"]
    }
    expected_cores = {
        asset["core_id"]: asset for asset in validated_candidate["assets"]
    }
    if set(asset_entries) != set(expected_assets):
        raise PipelineError("sealed candidate asset entries are not exact")
    if set(result_entries) != set(expected_cores):
        raise PipelineError("sealed candidate result entries are not exact")

    for core_id, asset in expected_cores.items():
        package_path = asset_entries[Path(asset["path"]).name]
        _require_regular_file(package_path, f"{core_id} sealed asset")
        if (
            package_path.stat().st_size != asset["size"]
            or sha256_file(package_path) != asset["sha256"]
        ):
            raise PipelineError(f"{core_id}: sealed asset bytes are invalid")
        one_result_entries = _directory_entries(
            result_entries[core_id], f"{core_id} sealed result directory"
        )
        if set(one_result_entries) != {"result.json"}:
            raise PipelineError(f"{core_id}: sealed result entries are not exact")
        result_path = one_result_entries["result.json"]
        _require_regular_file(result_path, f"{core_id} sealed result")
        result_reference = asset["result"]
        if sha256_file(result_path) != result_reference["file_sha256"]:
            raise PipelineError(f"{core_id}: sealed result file identity is invalid")
        result = load_json(result_path)
        if result.get("content_sha256") != result_reference["content_sha256"]:
            raise PipelineError(f"{core_id}: sealed result content identity is invalid")
        validate_core_result(
            result,
            plan=validated_plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector=runner_selector,
        )
        if result["package"] != {
            "name": Path(asset["path"]).name,
            "sha256": asset["sha256"],
            "size": asset["size"],
        }:
            raise PipelineError(f"{core_id}: sealed result and asset differ")
    return validated_candidate


def seal_release_candidate(
    *,
    plan: Mapping[str, Any],
    plan_path: Path,
    results_root: Path,
    output_dir: Path,
    runner_selector: str,
) -> dict[str, Any]:
    """Validate the exact fan-in completely, then atomically expose a seal."""

    if not isinstance(results_root, Path):
        raise PipelineError("release results root must be a Path")
    if not isinstance(output_dir, Path):
        raise PipelineError("release candidate output directory must be a Path")
    if os.path.lexists(output_dir):
        raise PipelineError(f"refusing to replace sealed candidate: {output_dir}")
    try:
        resolved_results = results_root.resolve(strict=True)
        resolved_output = output_dir.resolve(strict=False)
        resolved_output.relative_to(resolved_results)
    except ValueError:
        pass
    except OSError as exc:
        raise PipelineError(f"cannot resolve release paths: {exc}") from exc
    else:
        raise PipelineError("sealed candidate output must not be inside results root")

    validated_plan, plan_file_sha256 = _load_bound_plan(plan, plan_path)
    (
        results,
        result_paths,
        package_paths,
        result_file_hashes,
    ) = _validated_result_tree(
        plan=validated_plan,
        plan_file_sha256=plan_file_sha256,
        results_root=results_root,
        runner_selector=runner_selector,
    )
    candidate = construct_release_candidate(
        plan=validated_plan,
        plan_file_sha256=plan_file_sha256,
        runner_selector=runner_selector,
        results=results,
        result_file_sha256_by_core=result_file_hashes,
    )

    # The source fan-in, plan, identities, runners, and bytes are all valid.
    # Nothing under output_dir is created before this point.
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.parent.is_symlink():
        raise PipelineError("sealed candidate output parent must not be a symlink")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.stage-", dir=output_dir.parent)
    )
    try:
        (temporary / "assets").mkdir()
        (temporary / "results").mkdir()
        shutil.copyfile(plan_path, temporary / "plan.json")
        os.chmod(temporary / "plan.json", 0o644)
        for core_id in sorted(result_paths):
            asset = next(
                item
                for item in candidate["assets"]
                if item["core_id"] == core_id
            )
            asset_path = temporary / asset["path"]
            shutil.copyfile(package_paths[core_id], asset_path)
            os.chmod(asset_path, 0o644)
            result_destination = temporary / asset["result"]["path"]
            result_destination.parent.mkdir()
            shutil.copyfile(result_paths[core_id], result_destination)
            os.chmod(result_destination, 0o644)
        atomic_create_json(temporary / "candidate.json", candidate)
        validate_sealed_candidate_directory(
            candidate=candidate,
            output_dir=temporary,
            plan=validated_plan,
            runner_selector=runner_selector,
        )
        if os.path.lexists(output_dir):
            raise PipelineError(
                f"sealed candidate output appeared during staging: {output_dir}"
            )
        os.rename(temporary, output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return candidate
