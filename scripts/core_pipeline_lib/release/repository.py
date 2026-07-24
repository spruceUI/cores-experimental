"""Tracked repository adapter for deterministic full-release planning.

The release domain stays independent from the historical pipeline launcher.
This adapter accepts the remaining launcher-owned validators explicitly, reads
only tracked repository records, and normalizes them for :mod:`release.plan`.
Ignored build evidence is intentionally outside the planning boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import PipelineError
from ..foundation import (
    load_json,
    require_manifest_reference_path,
    run,
    sha256_file,
)
from ..source_bundle import pipeline_source_bundle
from .model import document_file_sha256
from .plan import (
    construct_release_plan,
    validate_release_plan,
    workflow_audit_content_sha256,
)
from .workflow_audit import (
    COORDINATOR_PATH,
    WORKER_PATH,
    audit_release_workflows,
)


ValidationReport = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ReleaseRepositoryServices:
    """Entrypoint-owned validators required by the tracked adapter."""

    load_catalog: Callable[[Path], dict[str, Any]]
    audit_workflows: Callable[[dict[str, Any]], dict[str, Any]]
    require_catalog_cores_eligible: Callable[[dict[str, Any], Iterable[str]], None]
    require_pin_sources_eligible: Callable[[dict[str, Any], dict[str, Any]], None]
    validate_pin_set: Callable[..., ValidationReport]
    require_individual_pin_identity: Callable[..., tuple[str, str]]
    validate_compatibility: Callable[..., ValidationReport]
    profile_report: Callable[[str], dict[str, Any]]
    core_spec_sha256: Callable[[dict[str, Any]], str]

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if not callable(getattr(self, name)):
                raise TypeError(f"release repository service {name} must be callable")


def _relative(path: Path, repository_root: Path, label: str) -> str:
    try:
        relative = path.relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise PipelineError(f"{label} must be inside the repository") from exc
    return relative


def _tracked_file(
    repository_root: Path,
    allowed_root: Path,
    relative: str,
    label: str,
) -> Path:
    path = require_manifest_reference_path(
        {"path": relative},
        allowed_root,
        label,
        repository_root=repository_root,
    )
    if path.is_symlink() or not path.is_file():
        raise PipelineError(f"{label} must be a tracked regular file")
    tracked = run(
        ["git", "ls-files", "--error-unmatch", relative],
        cwd=repository_root,
        check=False,
    )
    if tracked.returncode:
        raise PipelineError(f"{label} is not tracked by Git")
    return path


def _require_tracked_paths(
    repository_root: Path,
    relatives: Iterable[str],
    *,
    allowed_root: Path,
    label: str,
) -> None:
    """Require an exact nonempty set of regular repository-tracked files."""

    paths = list(relatives)
    if not paths or any(not isinstance(path, str) for path in paths):
        raise PipelineError(f"{label} paths are malformed")
    if len(paths) != len(set(paths)):
        raise PipelineError(f"{label} paths are not unique")
    ordered = sorted(paths)
    for relative in ordered:
        path = require_manifest_reference_path(
            {"path": relative},
            allowed_root,
            label,
            repository_root=repository_root,
        )
        if path.is_symlink() or not path.is_file():
            raise PipelineError(f"{label} must contain only regular files")
    tracked = run(
        ["git", "ls-files", "--error-unmatch", "--", *ordered],
        cwd=repository_root,
        check=False,
    )
    returned = sorted(line for line in tracked.stdout.splitlines() if line)
    if tracked.returncode or returned != ordered:
        raise PipelineError(f"{label} must contain only Git-tracked files")


def _compatibility_ids(directory: Path) -> set[str]:
    if not directory.is_dir() or directory.is_symlink():
        raise PipelineError(f"compatibility directory is unavailable: {directory}")
    result: set[str] = set()
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise PipelineError(f"compatibility entry must be a regular file: {path}")
        result.add(path.stem)
    return result


def _scope_core_ids(
    *,
    scope: str,
    requested_cores: list[str] | None,
    catalog: dict[str, Any],
    workflow_audit: dict[str, Any],
    canonical_ids: set[str],
    pending_ids: set[str],
) -> list[str]:
    catalog_ids = set(catalog["cores"])
    workflows = workflow_audit.get("workflows")
    if not isinstance(workflows, dict):
        raise PipelineError("workflow audit omitted the per-core workflow roster")
    workflow_ids = set(workflows)

    if scope == "explicit":
        if not requested_cores:
            raise PipelineError("explicit release scope requires at least one core")
        if len(requested_cores) != len(set(requested_cores)):
            raise PipelineError("explicit release core selectors must be unique")
        selected = set(requested_cores)
        unavailable = sorted(selected - canonical_ids)
        if unavailable:
            raise PipelineError(
                "explicit release cores are not canonical: " + ", ".join(unavailable)
            )
        return sorted(selected)

    if requested_cores:
        raise PipelineError("named release scope cannot also select explicit cores")
    if scope == "canonical":
        if not canonical_ids:
            raise PipelineError("canonical release scope is empty")
        return sorted(canonical_ids)
    if scope != "full-workflow-roster":
        raise PipelineError(f"unknown release scope: {scope}")

    pending = workflow_ids & pending_ids
    uncataloged = workflow_ids - catalog_ids
    legacy_bridge = (workflow_ids & catalog_ids) - canonical_ids - pending
    canonical = workflow_ids & canonical_ids
    nonshared = {
        core_id
        for core_id, record in workflows.items()
        if not isinstance(record, dict) or record.get("uses_shared_pipeline") is not True
    }
    missing_canonical_workflows = canonical_ids - workflow_ids
    if pending or uncataloged or legacy_bridge or nonshared or missing_canonical_workflows:
        raise PipelineError(
            "full workflow roster is not release-ready: "
            f"canonical={len(canonical)}, "
            f"legacy_bridge={len(legacy_bridge)}, "
            f"pending={len(pending)}, "
            f"uncataloged={len(uncataloged)}, "
            f"nonshared={len(nonshared)}, "
            f"missing_canonical_workflows={len(missing_canonical_workflows)}"
        )
    return sorted(workflow_ids)


def _require_valid_report(report: object, label: str) -> None:
    if not isinstance(report, dict):
        raise PipelineError(f"{label} validator returned no structured report")
    errors = report.get("errors")
    if report.get("status") != "valid" or not isinstance(errors, list) or errors:
        detail = errors if isinstance(errors, list) else ["malformed validation report"]
        raise PipelineError(f"{label} is invalid:\n- " + "\n- ".join(map(str, detail)))


def _tracked_release_orchestration(repository_root: Path) -> dict[str, Any]:
    """Audit, track, and bind the exact coordinator and worker bytes."""

    report = audit_release_workflows(repository_root)
    _require_valid_report(report, "release orchestration")
    references: dict[str, Any] = {}
    for role, relative_path in (
        ("coordinator", COORDINATOR_PATH),
        ("worker", WORKER_PATH),
    ):
        relative = relative_path.as_posix()
        path = _tracked_file(
            repository_root,
            repository_root / ".github" / "workflows",
            relative,
            f"release orchestration {role}",
        )
        record = report.get(role)
        file_sha256 = sha256_file(path)
        if (
            not isinstance(record, dict)
            or record.get("status") != "valid"
            or record.get("errors") != []
            or record.get("path") != relative
            or record.get("file_sha256") != file_sha256
        ):
            raise PipelineError(
                f"release orchestration {role} audit identity is inconsistent"
            )
        references[role] = {
            "path": relative,
            "file_sha256": file_sha256,
        }
    return references


def _release_core_row(
    *,
    core_id: str,
    repository_root: Path,
    catalog: dict[str, Any],
    workflow_audit: dict[str, Any],
    services: ReleaseRepositoryServices,
) -> dict[str, Any]:
    spec = catalog["cores"].get(core_id)
    if not isinstance(spec, dict):
        raise PipelineError(f"release core is not cataloged: {core_id}")
    workflow_record = workflow_audit["workflows"].get(core_id)
    if (
        not isinstance(workflow_record, dict)
        or workflow_record.get("uses_shared_pipeline") is not True
    ):
        raise PipelineError(f"release core workflow is not migrated: {core_id}")

    compatibility_relative = f"manifests/compatibility/{core_id}.json"
    compatibility_path = _tracked_file(
        repository_root,
        repository_root / "manifests" / "compatibility",
        compatibility_relative,
        f"{core_id} compatibility",
    )
    compatibility = load_json(compatibility_path)
    _require_valid_report(
        services.validate_compatibility(
            compatibility,
            document_path=compatibility_path,
            repository_root=repository_root,
            verify_pin=False,
        ),
        f"{core_id} compatibility",
    )

    pin_relative = compatibility.get("golden_source")
    if not isinstance(pin_relative, str):
        raise PipelineError(f"{core_id} compatibility omitted its pin")
    pin_path = _tracked_file(
        repository_root,
        repository_root / "pins" / "core-sets",
        pin_relative,
        f"{core_id} pin",
    )
    pin = load_json(pin_path)
    _require_valid_report(
        services.validate_pin_set(
            pin,
            verify_store=False,
            verify_sources=False,
            document_path=pin_path,
        ),
        f"{core_id} pin",
    )
    pin_core, semantic_id = services.require_individual_pin_identity(
        pin,
        pin_path=pin_path,
    )
    if pin_core != core_id:
        raise PipelineError(f"{core_id} pin owns a different core")
    services.require_pin_sources_eligible(catalog, pin)

    selection = pin["cores"][core_id]["selection"]
    package = selection.get("package")
    targets = selection.get("targets")
    selected_e2e = selection.get("e2e")
    if (
        not isinstance(package, dict)
        or not isinstance(targets, dict)
        or not isinstance(selected_e2e, dict)
    ):
        raise PipelineError(f"{core_id} pin selection is malformed")
    if (
        selection.get("tier") != "build_golden"
        or selection.get("validation_scope") != "static-build-only"
    ):
        raise PipelineError(f"{core_id} pin is not a static build golden")
    if compatibility.get("source_commit") != spec["source"].get("commit"):
        raise PipelineError(f"{core_id} compatibility source differs from catalog")
    if compatibility.get("package_sha256") != package.get("sha256"):
        raise PipelineError(f"{core_id} compatibility package differs from pin")
    selected_run_id = selected_e2e.get("run_id")
    if compatibility.get("e2e_run") != (
        f".local-e2e/runs/{selected_run_id}/e2e-record.json"
    ):
        raise PipelineError(f"{core_id} compatibility E2E run differs from pin")
    if compatibility.get("selected_e2e_content_sha256") != selected_e2e.get(
        "content_sha256"
    ):
        raise PipelineError(f"{core_id} compatibility E2E identity differs from pin")
    if selected_e2e.get("package_sha256") != package.get("sha256"):
        raise PipelineError(f"{core_id} pin E2E package identity is inconsistent")
    compatibility_targets = compatibility.get("targets")
    if not isinstance(compatibility_targets, dict) or set(compatibility_targets) != set(
        targets
    ):
        raise PipelineError(f"{core_id} compatibility target scope differs from pin")

    source_set_relative = f"pins/source-sets/{semantic_id}.json"
    source_set_path = _tracked_file(
        repository_root,
        repository_root / "pins" / "source-sets",
        source_set_relative,
        f"{core_id} source set",
    )
    source_set = load_json(source_set_path)
    if (
        source_set.get("source_set_id") != semantic_id
        or set(source_set.get("sources", {})) != {core_id}
    ):
        raise PipelineError(f"{core_id} source set is not one-core semantic state")
    profile_report = services.profile_report(source_set_relative)
    cells = profile_report.get("build_evidence_cells")
    if not isinstance(cells, list):
        raise PipelineError(f"{core_id} profile report omitted build evidence cells")
    cell_by_architecture = {
        cell.get("architecture"): cell for cell in cells if isinstance(cell, dict)
    }
    if set(cell_by_architecture) != set(targets):
        raise PipelineError(f"{core_id} profile cells differ from pin targets")
    device_views = profile_report.get("device_views")
    if not isinstance(device_views, list) or any(
        not isinstance(view, dict) or view.get("eligible_build_evidence_cells")
        for view in device_views
    ):
        raise PipelineError(f"{core_id} release plan must not inherit device claims")

    source_reference = source_set["sources"][core_id]
    source_lock_relative = source_reference.get("path")
    if not isinstance(source_lock_relative, str):
        raise PipelineError(f"{core_id} source set omitted its source lock")
    source_lock_path = _tracked_file(
        repository_root,
        repository_root / "pins" / "sources" / core_id,
        source_lock_relative,
        f"{core_id} source lock",
    )
    source_lock = load_json(source_lock_path)
    source = source_lock.get("source")
    if not isinstance(source, dict):
        raise PipelineError(f"{core_id} source lock is malformed")
    if source.get("commit") != spec["source"].get("commit"):
        raise PipelineError(f"{core_id} source lock differs from catalog")

    normalized_targets: list[dict[str, Any]] = []
    selected_build_records = selected_e2e.get("build_records")
    if not isinstance(selected_build_records, dict) or set(
        selected_build_records
    ) != set(targets):
        raise PipelineError(f"{core_id} pin E2E target identity is inconsistent")
    for architecture in sorted(targets):
        target = targets[architecture]
        artifact = target.get("artifact") if isinstance(target, dict) else None
        cell = cell_by_architecture[architecture]
        if not isinstance(artifact, dict):
            raise PipelineError(f"{core_id}/{architecture} pin artifact is malformed")
        if (
            compatibility_targets[architecture].get("artifact_sha256")
            != artifact.get("sha256")
            or cell.get("artifact_sha256") != artifact.get("sha256")
            or cell.get("core_id") != core_id
            or selected_build_records.get(architecture)
            != target.get("build_record_sha256")
        ):
            raise PipelineError(
                f"{core_id}/{architecture} compatibility/profile/E2E target differs"
            )
        normalized_targets.append(
            {
                "architecture": architecture,
                "execution_profile": cell.get("execution_profile_id"),
                "artifact_name": spec["build"]["artifact_name"],
                "artifact_sha256": artifact.get("sha256"),
                "artifact_size": artifact.get("size"),
                "selected_build_record_sha256": target.get(
                    "build_record_sha256"
                ),
            }
        )

    workflow_relative = spec.get("workflow")
    if workflow_record.get("workflow") != workflow_relative:
        raise PipelineError(f"{core_id} workflow audit differs from catalog")
    workflow_path = _tracked_file(
        repository_root,
        repository_root / ".github" / "workflows",
        workflow_relative,
        f"{core_id} workflow",
    )
    return {
        "core_id": core_id,
        "core_spec_sha256": services.core_spec_sha256(spec),
        "workflow": {
            "path": workflow_relative,
            "file_sha256": sha256_file(workflow_path),
        },
        "source": copy.deepcopy(source),
        "pin": {
            "path": pin_relative,
            "pin_id": pin["pin_id"],
            "file_sha256": sha256_file(pin_path),
            "content_sha256": pin["content_sha256"],
        },
        "source_set": {
            "path": source_set_relative,
            "source_set_id": source_set["source_set_id"],
            "file_sha256": sha256_file(source_set_path),
            "content_sha256": source_set["content_sha256"],
        },
        "compatibility": {
            "path": compatibility_relative,
            "file_sha256": sha256_file(compatibility_path),
            "content_sha256": compatibility["content_sha256"],
        },
        "package": {
            "name": package.get("name"),
            "sha256": package.get("sha256"),
            "size": package.get("size"),
        },
        "targets": normalized_targets,
    }


def construct_tracked_release_plan(
    *,
    candidate_id: str,
    scope: str,
    requested_cores: list[str] | None,
    repository_root: Path,
    catalog_path: Path,
    services: ReleaseRepositoryServices,
) -> dict[str, Any]:
    """Construct a release plan without reading ignored local evidence."""

    if not isinstance(repository_root, Path) or not repository_root.is_dir():
        raise PipelineError("release repository root is unavailable")
    canonical_catalog = repository_root / "manifests" / "core-builds.json"
    if catalog_path != canonical_catalog:
        raise PipelineError("full-release planning requires manifests/core-builds.json")
    if run(["git", "status", "--short"], cwd=repository_root).stdout:
        raise PipelineError("full-release planning requires a clean repository")
    head = run(["git", "rev-parse", "HEAD"], cwd=repository_root).stdout.strip()
    orchestration = _tracked_release_orchestration(repository_root)

    catalog = services.load_catalog(catalog_path)
    workflow_audit = services.audit_workflows(catalog)
    if (
        workflow_audit.get("active_aggregate_workflows")
        or workflow_audit.get("missing_catalog_workflows")
        or workflow_audit.get("invalid_catalog_workflows")
    ):
        raise PipelineError("workflow audit is not safe for release planning")
    workflow_records = workflow_audit.get("workflows")
    if not isinstance(workflow_records, dict):
        raise PipelineError("workflow audit omitted the per-core workflow roster")
    if any(not isinstance(record, dict) for record in workflow_records.values()):
        raise PipelineError("workflow audit contains a malformed workflow record")
    _require_tracked_paths(
        repository_root,
        (
            record.get("workflow")
            for record in workflow_records.values()
        ),
        allowed_root=repository_root / ".github" / "workflows",
        label="release workflow roster",
    )
    compatibility_root = repository_root / "manifests" / "compatibility"
    canonical_ids = _compatibility_ids(compatibility_root)
    pending_ids = _compatibility_ids(compatibility_root / "pending")
    core_ids = _scope_core_ids(
        scope=scope,
        requested_cores=requested_cores,
        catalog=catalog,
        workflow_audit=workflow_audit,
        canonical_ids=canonical_ids,
        pending_ids=pending_ids,
    )
    services.require_catalog_cores_eligible(catalog, core_ids)

    rows = [
        _release_core_row(
            core_id=core_id,
            repository_root=repository_root,
            catalog=catalog,
            workflow_audit=workflow_audit,
            services=services,
        )
        for core_id in core_ids
    ]
    topology = {
        "schema_version": workflow_audit.get("schema_version"),
        "content_sha256": "",
        "core_workflow_count": workflow_audit.get("core_workflow_count"),
        "catalog_workflow_count": workflow_audit.get("catalog_workflow_count"),
        "shared_pipeline_workflows": workflow_audit.get(
            "shared_pipeline_workflows"
        ),
        "unmigrated_workflow_count": workflow_audit.get(
            "unmigrated_workflow_count"
        ),
    }
    topology["content_sha256"] = workflow_audit_content_sha256(topology)
    bundle = pipeline_source_bundle()
    bundle_files = bundle.get("files")
    if not isinstance(bundle_files, dict):
        raise PipelineError("release pipeline source bundle is malformed")
    _require_tracked_paths(
        repository_root,
        bundle_files,
        allowed_root=repository_root / "scripts",
        label="release pipeline source bundle",
    )
    repository = {
        "head": head,
        "clean": True,
        "catalog": {
            "path": _relative(catalog_path, repository_root, "release catalog"),
            "file_sha256": sha256_file(catalog_path),
        },
        "toolchain_lock": {
            key: catalog["toolchain_lock"][key]
            for key in ("path", "file_sha256", "content_sha256")
        },
        "commit_blacklist": {
            key: catalog["commit_blacklist"][key]
            for key in ("path", "file_sha256", "content_sha256")
        },
        "pipeline_bundle": {
            "file_sha256": document_file_sha256(bundle),
            "content_sha256": bundle["content_sha256"],
        },
        "workflow_audit": topology,
        "orchestration": orchestration,
    }
    return construct_release_plan(
        candidate_id=candidate_id,
        scope=scope,
        repository=repository,
        cores=rows,
    )


def validate_plan_against_repository(
    plan: dict[str, Any],
    *,
    repository_root: Path,
    catalog_path: Path,
    services: ReleaseRepositoryServices,
) -> dict[str, Any]:
    """Reconstruct and require the exact current tracked plan identity."""

    validated = validate_release_plan(plan)
    scope = validated["scope"]
    requested = (
        [row["core_id"] for row in validated["cores"]]
        if scope == "explicit"
        else None
    )
    current = construct_tracked_release_plan(
        candidate_id=validated["candidate_id"],
        scope=scope,
        requested_cores=requested,
        repository_root=repository_root,
        catalog_path=catalog_path,
        services=services,
    )
    if current != validated:
        raise PipelineError("release plan differs from the current tracked repository")
    return validated
