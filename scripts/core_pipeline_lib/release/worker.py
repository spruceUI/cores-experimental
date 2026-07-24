"""Deep E2E adapter for one portable full-release worker result.

The pure result domain accepts normalized facts only.  This module owns the
repository-facing boundary: it revalidates the tracked plan, asks the existing
pipeline validator to prove every fresh build/package byte, derives the exact
runner selector from persisted evidence, and only then stages a worker bundle.
"""

from __future__ import annotations

from collections.abc import Callable
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import PipelineError
from ..foundation import load_json, safe_child
from .model import runner_selector_for_contract
from .repository import (
    ReleaseRepositoryServices,
    validate_plan_against_repository,
)
from .result import write_core_result


DeepE2EResult = tuple[
    dict[str, Any],
    str,
    dict[str, tuple[dict[str, Any], Path, str]],
    Path,
    dict[str, Any],
]


@dataclass(frozen=True, slots=True)
class ReleaseWorkerServices:
    """Entrypoint-owned E2E readers required by the worker adapter."""

    active_e2e_scope: Callable[
        [object, object], tuple[list[dict[str, Any]], list[dict[str, Any]]]
    ]
    validate_e2e: Callable[
        [Path, Path, Path, dict[str, Any]], DeepE2EResult
    ]

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if not callable(getattr(self, name)):
                raise TypeError(f"release worker service {name} must be callable")


def _selected_record_path(
    *,
    evidence: dict[str, Any],
    core_id: str,
    repository_root: Path,
    services: ReleaseWorkerServices,
) -> Path:
    builds, _ = services.active_e2e_scope(evidence, core_id)
    if not builds:
        raise PipelineError("release worker E2E record contains no builds")
    ordered = sorted(builds, key=lambda item: str(item.get("architecture")))
    record = ordered[0].get("record")
    if not isinstance(record, str) or not record:
        raise PipelineError("release worker E2E build record path is invalid")
    return safe_child(repository_root, record, "release worker build record")


def normalize_deep_e2e_facts(
    *,
    evidence: dict[str, Any],
    evidence_file_sha256: str,
    bound_records: dict[str, tuple[dict[str, Any], Path, str]],
    package_path: Path,
    package_record: dict[str, Any],
) -> dict[str, Any]:
    """Project a successful deep validation into portable result facts."""

    targets: list[dict[str, Any]] = []
    for architecture in sorted(bound_records):
        record, _, record_file_sha256 = bound_records[architecture]
        artifact = record.get("artifact")
        if not isinstance(artifact, dict):
            raise PipelineError(
                f"release worker {architecture} artifact record is malformed"
            )
        targets.append(
            {
                "architecture": architecture,
                "artifact_sha256": artifact.get("sha256"),
                "artifact_size": artifact.get("size"),
                "build_record_sha256": record_file_sha256,
            }
        )
    return {
        "run_id": evidence.get("run_id"),
        "file_sha256": evidence_file_sha256,
        "content_sha256": evidence.get("content_sha256"),
        "runner": copy.deepcopy(evidence.get("runner")),
        "package": {
            "name": package_path.name,
            "sha256": package_record.get("sha256"),
            "size": package_record.get("size"),
        },
        "targets": targets,
    }


def require_fresh_repository_identity(
    *,
    plan: dict[str, Any],
    bound_records: dict[str, tuple[dict[str, Any], Path, str]],
) -> None:
    """Require every fresh target to originate at the clean planned commit."""

    expected_head = plan["repository"]["head"]
    for architecture, (record, _, _) in sorted(bound_records.items()):
        recipe = record.get("recipe")
        if not isinstance(recipe, dict):
            raise PipelineError(
                f"release worker {architecture} recipe identity is malformed"
            )
        if recipe.get("repository_head") != expected_head:
            raise PipelineError(
                f"release worker {architecture} repository head differs from plan"
            )
        if recipe.get("repository_dirty") is not False:
            raise PipelineError(
                f"release worker {architecture} was built from a dirty repository"
            )


def record_validated_release_result(
    *,
    plan_path: Path,
    core_id: str,
    e2e_path: Path,
    output_dir: Path,
    repository_root: Path,
    catalog_path: Path,
    repository_services: ReleaseRepositoryServices,
    worker_services: ReleaseWorkerServices,
) -> tuple[dict[str, Any], str]:
    """Validate current tracked state and one fresh E2E run, then stage it."""

    if not isinstance(plan_path, Path) or plan_path.is_symlink() or not plan_path.is_file():
        raise PipelineError("release worker plan must be a regular non-symlink file")
    if not isinstance(e2e_path, Path) or e2e_path.is_symlink() or not e2e_path.is_file():
        raise PipelineError("release worker E2E record must be a regular non-symlink file")
    plan = validate_plan_against_repository(
        load_json(plan_path),
        repository_root=repository_root,
        catalog_path=catalog_path,
        services=repository_services,
    )
    catalog = repository_services.load_catalog(catalog_path)
    initial_evidence = load_json(e2e_path)
    selected_record = _selected_record_path(
        evidence=initial_evidence,
        core_id=core_id,
        repository_root=repository_root,
        services=worker_services,
    )
    (
        evidence,
        evidence_file_sha256,
        bound_records,
        package_path,
        package_record,
    ) = worker_services.validate_e2e(
        e2e_path,
        selected_record,
        catalog_path,
        catalog,
    )
    if evidence != initial_evidence:
        raise PipelineError("release worker E2E record changed during validation")
    require_fresh_repository_identity(
        plan=plan,
        bound_records=bound_records,
    )
    facts = normalize_deep_e2e_facts(
        evidence=evidence,
        evidence_file_sha256=evidence_file_sha256,
        bound_records=bound_records,
        package_path=package_path,
        package_record=package_record,
    )
    runner_selector = runner_selector_for_contract(facts["runner"])
    result = write_core_result(
        plan=plan,
        plan_path=plan_path,
        core_id=core_id,
        runner_selector=runner_selector,
        e2e=facts,
        package_path=package_path,
        output_dir=output_dir,
    )
    return result, runner_selector
