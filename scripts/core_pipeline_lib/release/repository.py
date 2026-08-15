"""Tracked repository adapter for deterministic full-release planning.

The release domain stays independent from the historical pipeline launcher.
This adapter accepts the remaining launcher-owned validators explicitly, reads
only tracked repository records, and normalizes them for :mod:`release.plan`.
Ignored build evidence is intentionally outside the planning boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import PipelineError
from ..foundation import (
    load_json_with_sha256,
    require_manifest_reference_path,
    run,
    sha256_file,
)
from ..source_bundle import pipeline_source_bundle
from .model import document_file_sha256
from .eligibility import core_group_selection_shape_errors
from ..records.source import (
    compose_source_lock,
    compose_source_set,
    record_file_sha256,
    source_set_coordinate,
)
from .plan import (
    construct_release_plan,
    plan_core,
    validate_release_plan,
    workflow_audit_content_sha256,
)
from .workflow_audit import (
    COORDINATOR_PATH,
    OVERLAY_PATH,
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
    group_execution_spec: Callable[..., dict[str, Any]]
    load_core_pin_index: Callable[[], Mapping[str, Mapping[str, object]]]
    resolve_core_group_build_selection: Callable[..., dict[str, Any]]

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

    if scope == "track-group":
        if requested_cores:
            raise PipelineError("track-group release scope forbids explicit cores")
        scope = "full-workflow-roster"

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


def _tracked_group_inputs(
    repository_root: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Capture every tracked group registry once for planning and binding."""

    manifest_specs = {
        "track_registry": "manifests/core-tracks.json",
        "tuning_registry": "manifests/chipset-tunings.json",
        "release_roster": "manifests/spruce-release-roster.json",
        "spruce_branch_bases": "manifests/spruce-core-branch-bases.json",
    }
    documents: dict[str, dict[str, Any]] = {}
    references: dict[str, dict[str, Any]] = {}
    for field, relative in manifest_specs.items():
        path = _tracked_file(
            repository_root,
            repository_root / "manifests",
            relative,
            f"release group {field}",
        )
        document, file_sha256 = load_json_with_sha256(path)
        if not isinstance(document, dict):
            raise PipelineError(f"release group {field} must be an object")
        content_sha256 = document.get("content_sha256")
        if not isinstance(content_sha256, str):
            raise PipelineError(f"release group {field} has no content identity")
        documents[field] = document
        references[field] = {
            "path": relative,
            "file_sha256": file_sha256,
            "content_sha256": content_sha256,
        }
    return documents, references


def _tracked_group_facts(
    *,
    group_tag: str,
    selections: dict[str, dict[str, Any]],
    repository_root: Path,
    documents: dict[str, dict[str, Any]] | None = None,
    references: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bind the exact tracked registries and aggregate selection state."""

    if not selections:
        raise PipelineError("track-group release selection is empty")
    if documents is None or references is None:
        documents, references = _tracked_group_inputs(repository_root)

    track_content = documents["track_registry"]["content_sha256"]
    tuning_content = documents["tuning_registry"]["content_sha256"]
    selected_track = group_tag.split("-", 1)[0]
    expected_branch_basis = (
        documents["track_registry"].get("tracks", {}).get(selected_track, {}).get(
            "spruce_branch_basis"
        )
    )
    if not isinstance(expected_branch_basis, dict):
        raise PipelineError("release group has no exact Spruce branch basis")
    historical = documents["track_registry"].get(
        "historical_release_correlation"
    )
    if not isinstance(historical, dict) or (
        historical.get("roster_path")
        != references["release_roster"]["path"]
        or historical.get("roster_content_sha256")
        != references["release_roster"]["content_sha256"]
    ):
        raise PipelineError("release group roster identity differs from core tracks")
    branch_bases = documents["track_registry"].get("spruce_branch_bases")
    if not isinstance(branch_bases, dict) or (
        branch_bases.get("path")
        != references["spruce_branch_bases"]["path"]
        or branch_bases.get("content_sha256")
        != references["spruce_branch_bases"]["content_sha256"]
    ):
        raise PipelineError(
            "release group Spruce branch basis differs from core tracks"
        )
    for core_id, selection in sorted(selections.items()):
        if selection.get("group_tag") != group_tag:
            raise PipelineError(f"{core_id}: release group selector changed")
        if selection.get("track_registry_content_sha256") != track_content:
            raise PipelineError(f"{core_id}: release track registry identity changed")
        if selection.get("tuning_registry_content_sha256") != tuning_content:
            raise PipelineError(f"{core_id}: release tuning registry identity changed")
        if selection.get("spruce_branch_basis") != expected_branch_basis:
            raise PipelineError(f"{core_id}: release Spruce branch basis changed")

    states = [selection["selected_state"] for selection in selections.values()]
    stable_count = states.count("stable")
    return {
        "group_tag": group_tag,
        "inventory_state": (
            "stable" if stable_count == len(selections) else "unstable"
        ),
        **references,
        "stable_core_count": stable_count,
        "unstable_fallback_core_count": states.count("unstable_fallback"),
        "test_core_count": states.count("test"),
    }


def _resolve_release_group_selection(
    *,
    group_tag: str,
    core_id: str,
    catalog_path: Path,
    catalog: dict[str, Any],
    pin_index: Mapping[str, Mapping[str, object]],
    services: ReleaseRepositoryServices,
    group_documents: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve one exact-package selection before any release row is built."""

    resolver_arguments: dict[str, Any] = {
        "group_tag": group_tag,
        "catalog_path": catalog_path,
        "catalog": catalog,
        "core_id": core_id,
        "pin_index": pin_index,
    }
    if group_documents is not None:
        resolver_arguments.update(
            {
                "track_registry": copy.deepcopy(group_documents["track_registry"]),
                "tuning_registry": copy.deepcopy(group_documents["tuning_registry"]),
                "release_roster": copy.deepcopy(group_documents["release_roster"]),
                "spruce_branch_bases": copy.deepcopy(
                    group_documents["spruce_branch_bases"]
                ),
            }
        )
    selection = services.resolve_core_group_build_selection(**resolver_arguments)
    package = selection.get("expected_outputs", {}).get("package")
    comparison = package.get("comparison") if isinstance(package, dict) else None
    if comparison != "exact":
        raise PipelineError(
            f"{core_id}: track-group release requires an exact pinned "
            "package; projected architecture packages are unsupported"
        )
    selection_errors = core_group_selection_shape_errors(
        selection, f"{core_id} release group selection"
    )
    if selection_errors:
        raise PipelineError(
            f"{core_id} release group selection is invalid:\n- "
            + "\n- ".join(selection_errors)
        )
    return selection


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
        ("overlay", OVERLAY_PATH),
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
        if role != "overlay":
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
    group_selection: dict[str, Any] | None = None,
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
    compatibility, compatibility_file_sha256 = load_json_with_sha256(
        compatibility_path
    )
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
    pin, pin_file_sha256 = load_json_with_sha256(pin_path)
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

    # Validate the tracked execution-profile registry through the canonical
    # promoted pin before a track may substitute a different immutable source.
    # The profile identity is ABI-owned; the selected artifact/source cells are
    # rebuilt below from the group pin rather than sent back through the
    # catalog-source mirror gate.
    canonical_semantic_id = semantic_id
    canonical_source_set_relative = source_set_coordinate(canonical_semantic_id)
    canonical_source_set = compose_source_set(
        canonical_semantic_id,
        repository_root=repository_root,
        catalog=catalog,
    )
    canonical_pin_reference = {
        "path": pin_relative,
        "pin_id": pin["pin_id"],
        "file_sha256": pin_file_sha256,
        "content_sha256": pin["content_sha256"],
    }
    if (
        canonical_source_set.get("source_set_id") != canonical_semantic_id
        or set(canonical_source_set.get("sources", {})) != {core_id}
        or canonical_source_set.get("evidence_pin") != canonical_pin_reference
    ):
        raise PipelineError(
            f"{core_id} source set differs from its parsed pin snapshot"
        )
    profile_report = services.profile_report(canonical_source_set_relative)
    canonical_cells = profile_report.get("build_evidence_cells")
    if not isinstance(canonical_cells, list):
        raise PipelineError(f"{core_id} profile report omitted build evidence cells")
    canonical_cell_by_architecture = {
        cell.get("architecture"): cell
        for cell in canonical_cells
        if isinstance(cell, dict)
    }
    if set(canonical_cell_by_architecture) != set(targets):
        raise PipelineError(f"{core_id} profile cells differ from canonical pin targets")
    for architecture, target in targets.items():
        cell = canonical_cell_by_architecture[architecture]
        artifact = target.get("artifact") if isinstance(target, dict) else None
        if (
            not isinstance(artifact, dict)
            or cell.get("core_id") != core_id
            or cell.get("artifact_sha256") != artifact.get("sha256")
            or not isinstance(cell.get("execution_profile_id"), str)
        ):
            raise PipelineError(
                f"{core_id}/{architecture} canonical profile cell differs from pin"
            )
    device_views = profile_report.get("device_views")
    if not isinstance(device_views, list) or any(
        not isinstance(view, dict) or view.get("eligible_build_evidence_cells")
        for view in device_views
    ):
        raise PipelineError(f"{core_id} release plan must not inherit device claims")

    # Compatibility remains independently bound to the canonical promoted pin
    # above.  A track group may select another immutable pin; from this point
    # onward the release row is derived exclusively from that selected pin.
    if group_selection is not None:
        group_errors = core_group_selection_shape_errors(
            group_selection, f"{core_id} release group selection"
        )
        if group_errors:
            raise PipelineError(
                f"{core_id} release group selection is invalid:\n- "
                + "\n- ".join(group_errors)
            )
        selected_pin = group_selection["pin"]
        pin_relative = selected_pin["path"]
        pin_path = _tracked_file(
            repository_root,
            repository_root / "pins" / "core-sets",
            pin_relative,
            f"{core_id} selected group pin",
        )
        pin, pin_file_sha256 = load_json_with_sha256(pin_path)
        _require_valid_report(
            services.validate_pin_set(
                pin,
                verify_store=False,
                verify_sources=False,
                document_path=pin_path,
            ),
            f"{core_id} selected group pin",
        )
        pin_core, semantic_id = services.require_individual_pin_identity(
            pin,
            pin_path=pin_path,
        )
        if pin_core != core_id:
            raise PipelineError(f"{core_id} selected group pin owns another core")
        actual_pin_reference = {
            "path": pin_relative,
            "pin_id": pin["pin_id"],
            "file_sha256": pin_file_sha256,
            "content_sha256": pin["content_sha256"],
        }
        if actual_pin_reference != selected_pin:
            raise PipelineError(f"{core_id} selected group pin identity changed")
        services.require_pin_sources_eligible(catalog, pin)
        selection = pin["cores"][core_id]["selection"]
        package = selection.get("package")
        targets = selection.get("targets")
        selected_e2e = selection.get("e2e")
        if (
            not isinstance(package, dict)
            or not isinstance(targets, dict)
            or not isinstance(selected_e2e, dict)
            or selection.get("tier") != "build_golden"
            or selection.get("validation_scope") != "static-build-only"
        ):
            raise PipelineError(f"{core_id} selected group pin is not executable")
        expected_outputs = group_selection["expected_outputs"]
        if (
            group_selection["selected_architectures"] != sorted(targets)
            or {
                key: expected_outputs["package"][key]
                for key in ("name", "sha256", "size")
            }
            != {key: package.get(key) for key in ("name", "sha256", "size")}
            or {
                architecture: {
                    "artifact": {
                        "sha256": targets[architecture]["artifact"].get("sha256"),
                        "size": targets[architecture]["artifact"].get("size"),
                    }
                }
                for architecture in sorted(targets)
            }
            != expected_outputs["targets"]
        ):
            raise PipelineError(f"{core_id} selected group pin outputs changed")
        if selected_e2e.get("package_sha256") != package.get("sha256"):
            raise PipelineError(
                f"{core_id} selected group pin E2E package identity is inconsistent"
            )

    source_set_relative = source_set_coordinate(semantic_id)
    if group_selection is None:
        source_lock = compose_source_lock(
            core_id,
            repository_root=repository_root,
            catalog=catalog,
        )
        source = source_lock.get("source")
        if not isinstance(source, dict):
            raise PipelineError(f"{core_id} source lock is malformed")
        catalog_source = spec.get("source")
        if not isinstance(catalog_source, dict) or source != {
            "url": catalog_source.get("url"),
            "requested_ref": catalog_source.get("requested_ref"),
            "commit": catalog_source.get("commit"),
            "tree": catalog_source.get("tree"),
            "submodules": copy.deepcopy(catalog_source.get("submodules", [])),
        }:
            raise PipelineError(f"{core_id} source lock differs from catalog")
        source = copy.deepcopy(source)
        source_set = canonical_source_set
        cell_by_architecture = canonical_cell_by_architecture
        row_core_spec_sha256 = services.core_spec_sha256(spec)
    else:
        # The group resolver has already proved that this immutable source is
        # executable with the current normalized recipe.  Re-check that every
        # selected-pin target captured that exact source identity, then compose
        # the source lock/set from a private catalog projection.  Calling the
        # legacy profile report here would incorrectly require the historical
        # pin source to equal the current catalog source.
        source = copy.deepcopy(group_selection["execution_source"])
        for architecture, target in sorted(targets.items()):
            golden = target.get("golden_record") if isinstance(target, dict) else None
            captured = golden.get("source") if isinstance(golden, dict) else None
            if not isinstance(captured, dict):
                raise PipelineError(
                    f"{core_id}/{architecture} selected group pin source is malformed"
                )
            submodules = captured.get("submodules")
            if not isinstance(submodules, list) or any(
                not isinstance(item, dict) for item in submodules
            ):
                raise PipelineError(
                    f"{core_id}/{architecture} selected group pin submodules are malformed"
                )
            captured_source = {
                "url": captured.get("url"),
                "requested_ref": captured.get("requested_ref"),
                "commit": captured.get("commit"),
                "tree": captured.get("tree"),
                "submodules": [
                    {"path": item.get("path"), "commit": item.get("commit")}
                    for item in submodules
                ],
            }
            if (
                captured.get("resolved_url") != captured.get("url")
                or captured.get("resolved_commit") != captured.get("commit")
                or captured_source != source
            ):
                raise PipelineError(
                    f"{core_id}/{architecture} selected group pin source changed"
                )

        execution_catalog = copy.deepcopy(catalog)
        execution_catalog["cores"][core_id]["source"] = copy.deepcopy(source)
        source_lock = compose_source_lock(
            core_id,
            repository_root=repository_root,
            catalog=execution_catalog,
        )
        if source_lock.get("source") != source:
            raise PipelineError(f"{core_id} group source lock changed")
        source_set = compose_source_set(
            semantic_id,
            repository_root=repository_root,
            catalog=execution_catalog,
        )
        source_reference = source_set.get("sources", {}).get(core_id)
        if (
            source_set.get("source_set_id") != semantic_id
            or set(source_set.get("sources", {})) != {core_id}
            or not isinstance(source_reference, dict)
            or source_reference.get("commit") != source["commit"]
            or source_reference.get("source_lock_id")
            != source_lock.get("source_lock_id")
        ):
            raise PipelineError(f"{core_id} group source set changed")

        # Execution profiles are ABI registry identities, not source or
        # artifact identities.  Project the already-validated canonical ABI
        # mapping onto the selected pin while retaining the selected artifact
        # and source-lock bindings.
        missing_profiles = set(targets) - set(canonical_cell_by_architecture)
        if missing_profiles:
            raise PipelineError(
                f"{core_id} selected group pin has no canonical execution profile: "
                + ", ".join(sorted(missing_profiles))
            )
        cell_by_architecture = {}
        for architecture, target in sorted(targets.items()):
            artifact = target.get("artifact") if isinstance(target, dict) else None
            if not isinstance(artifact, dict):
                raise PipelineError(
                    f"{core_id}/{architecture} selected group pin artifact is malformed"
                )
            canonical_cell = canonical_cell_by_architecture[architecture]
            cell_by_architecture[architecture] = {
                **copy.deepcopy(canonical_cell),
                "source_lock_id": source_lock["source_lock_id"],
                "artifact_sha256": artifact.get("sha256"),
            }

        execution_spec = services.group_execution_spec(
            core_id=core_id,
            catalog_spec=spec,
            group_selection=group_selection,
            validated_pin_selection=selection,
        )
        row_core_spec_sha256 = services.core_spec_sha256(execution_spec)
        if row_core_spec_sha256 != group_selection["recipe_compatibility"].get(
            "execution_core_spec_sha256"
        ):
            raise PipelineError(f"{core_id} group execution recipe identity changed")

    if (
        source_set.get("source_set_id") != semantic_id
        or set(source_set.get("sources", {})) != {core_id}
        or source_set.get("evidence_pin")
        != {
            "path": pin_relative,
            "pin_id": pin["pin_id"],
            "file_sha256": pin_file_sha256,
            "content_sha256": pin["content_sha256"],
        }
    ):
        raise PipelineError(
            f"{core_id} source set differs from its parsed pin snapshot"
        )

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
            (
                group_selection is None
                and compatibility_targets[architecture].get("artifact_sha256")
                != artifact.get("sha256")
            )
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
    workflow_file_sha256 = workflow_record.get("file_sha256")
    if (
        workflow_record.get("workflow") != workflow_relative
        or not isinstance(workflow_file_sha256, str)
        or len(workflow_file_sha256) != 64
        or any(character not in "0123456789abcdef" for character in workflow_file_sha256)
    ):
        raise PipelineError(f"{core_id} workflow audit differs from catalog")
    workflow_path = _tracked_file(
        repository_root,
        repository_root / ".github" / "workflows",
        workflow_relative,
        f"{core_id} workflow",
    )
    return {
        "core_id": core_id,
        "core_spec_sha256": row_core_spec_sha256,
        "workflow": {
            "path": workflow_relative,
            "file_sha256": workflow_file_sha256,
        },
        "source": copy.deepcopy(source),
        "pin": {
            "path": pin_relative,
            "pin_id": pin["pin_id"],
            "file_sha256": pin_file_sha256,
            "content_sha256": pin["content_sha256"],
        },
        "source_set": {
            "path": source_set_relative,
            "source_set_id": source_set["source_set_id"],
            "file_sha256": record_file_sha256(source_set),
            "content_sha256": source_set["content_sha256"],
        },
        "compatibility": {
            "path": compatibility_relative,
            "file_sha256": compatibility_file_sha256,
            "content_sha256": compatibility["content_sha256"],
        },
        "package": {
            "name": package.get("name"),
            "sha256": package.get("sha256"),
            "size": package.get("size"),
        },
        "targets": normalized_targets,
        "core_group": copy.deepcopy(group_selection),
    }


def construct_tracked_release_plan(
    *,
    candidate_id: str,
    scope: str,
    requested_cores: list[str] | None,
    repository_root: Path,
    catalog_path: Path,
    services: ReleaseRepositoryServices,
    group_tag: str | None = None,
) -> dict[str, Any]:
    """Construct a release plan without reading ignored local evidence."""

    if not isinstance(repository_root, Path) or not repository_root.is_dir():
        raise PipelineError("release repository root is unavailable")
    if (scope == "track-group") != (group_tag is not None):
        raise PipelineError(
            "track-group release scope requires exactly one group tag"
        )
    canonical_catalog = repository_root / "manifests" / "core-builds.json"
    if catalog_path != canonical_catalog:
        raise PipelineError("full-release planning requires manifests/core-builds.json")
    if run(["git", "status", "--short"], cwd=repository_root).stdout:
        raise PipelineError("full-release planning requires a clean repository")
    head = run(["git", "rev-parse", "HEAD"], cwd=repository_root).stdout.strip()
    orchestration = _tracked_release_orchestration(repository_root)

    catalog, catalog_file_sha256 = load_json_with_sha256(catalog_path)
    validated_catalog = services.load_catalog(catalog_path)
    if validated_catalog != catalog:
        raise PipelineError("release catalog changed while it was being validated")
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

    group_selections: dict[str, dict[str, Any]] = {}
    group_facts: dict[str, Any] | None = None
    if group_tag is not None:
        group_documents, group_references = _tracked_group_inputs(repository_root)
        group_pin_index = services.load_core_pin_index()
        if not isinstance(group_pin_index, Mapping):
            raise PipelineError(
                "track-group release pin index loader returned no mapping"
            )
        # Resolve the complete selector first.  In particular, reject a
        # projected multi-ABI package or historical recipe before any release
        # row is composed and before a matrix can dispatch work.
        for core_id in core_ids:
            group_selections[core_id] = _resolve_release_group_selection(
                group_tag=group_tag,
                core_id=core_id,
                catalog_path=catalog_path,
                catalog=catalog,
                pin_index=group_pin_index,
                services=services,
                group_documents=group_documents,
            )
        group_facts = _tracked_group_facts(
            group_tag=group_tag,
            selections=group_selections,
            repository_root=repository_root,
            documents=group_documents,
            references=group_references,
        )

    rows = [
        _release_core_row(
            core_id=core_id,
            repository_root=repository_root,
            catalog=catalog,
            workflow_audit=workflow_audit,
            services=services,
            group_selection=group_selections.get(core_id),
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
            "file_sha256": catalog_file_sha256,
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
        group=group_facts,
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
        group_tag=(
            validated["group"]["group_tag"]
            if validated["group"] is not None
            else None
        ),
    )
    if current != validated:
        raise PipelineError("release plan differs from the current tracked repository")
    return validated


def validate_plan_core_against_repository(
    plan: dict[str, Any],
    *,
    core_id: str,
    repository_root: Path,
    catalog_path: Path,
    services: ReleaseRepositoryServices,
) -> dict[str, Any]:
    """Revalidate one worker row without requiring unrelated source graphs.

    The complete plan remains subject to its strict semantic hash, shape,
    summary, and group-count validation.  Repository/orchestration facts are
    reconstructed from tracked state, while the plan-bound group row is
    independently resolved with the selected-core ancestry scope.  Full-plan
    callers (matrix, seal, and overlay reconstruction) continue to use
    :func:`validate_plan_against_repository` and therefore require every graph.
    """

    validated = validate_release_plan(plan)
    planned_row = plan_core(validated, core_id)
    if validated["group"] is None:
        return validate_plan_against_repository(
            validated,
            repository_root=repository_root,
            catalog_path=catalog_path,
            services=services,
        )

    # Reconstruct all repository-wide identities through the canonical legacy
    # row path.  This proves the clean head, catalog, policy/toolchain records,
    # pipeline bundle, workflow topology, and orchestration bytes without
    # consulting any track ancestry graph.
    repository_projection = construct_tracked_release_plan(
        candidate_id=validated["candidate_id"],
        scope="explicit",
        requested_cores=[core_id],
        repository_root=repository_root,
        catalog_path=catalog_path,
        services=services,
    )
    if repository_projection["repository"] != validated["repository"]:
        raise PipelineError(
            "release plan repository differs from the current tracked repository"
        )

    catalog = services.load_catalog(catalog_path)
    workflow_audit = services.audit_workflows(catalog)
    services.require_catalog_cores_eligible(catalog, [core_id])
    group_tag = validated["group"]["group_tag"]
    pin_index = services.load_core_pin_index()
    if not isinstance(pin_index, Mapping):
        raise PipelineError(
            "track-group release pin index loader returned no mapping"
        )
    selection = _resolve_release_group_selection(
        group_tag=group_tag,
        core_id=core_id,
        catalog_path=catalog_path,
        catalog=catalog,
        pin_index=pin_index,
        services=services,
    )
    current_row = _release_core_row(
        core_id=core_id,
        repository_root=repository_root,
        catalog=catalog,
        workflow_audit=workflow_audit,
        services=services,
        group_selection=selection,
    )
    if current_row != planned_row:
        raise PipelineError(
            f"release plan core {core_id} differs from the current tracked repository"
        )

    current_group = _tracked_group_facts(
        group_tag=group_tag,
        selections={core_id: selection},
        repository_root=repository_root,
    )
    for field in (
        "group_tag",
        "track_registry",
        "tuning_registry",
        "release_roster",
        "spruce_branch_bases",
    ):
        if current_group[field] != validated["group"][field]:
            raise PipelineError(
                "release plan group registries differ from the current "
                "tracked repository"
            )
    return validated
