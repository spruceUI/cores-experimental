"""Deterministic fixtures shared by the pure full-release domain tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from scripts.core_pipeline_lib.release import (
    construct_release_plan,
    document_file_sha256,
    plan_core,
    runner_contract_for_selector,
    workflow_audit_content_sha256,
    write_core_result,
    write_release_plan,
)


def sha1(label: str) -> str:
    return hashlib.sha1(label.encode()).hexdigest()


def sha256(label: str | bytes) -> str:
    value = label if isinstance(label, bytes) else label.encode()
    return hashlib.sha256(value).hexdigest()


def package_bytes(core_id: str) -> bytes:
    return f"portable-package:{core_id}\n".encode()


def repository_facts() -> dict[str, Any]:
    workflow_audit: dict[str, Any] = {
        "schema_version": 2,
        "content_sha256": "",
        "core_workflow_count": 2,
        "catalog_workflow_count": 2,
        "shared_pipeline_workflows": 2,
        "unmigrated_workflow_count": 0,
    }
    workflow_audit["content_sha256"] = workflow_audit_content_sha256(
        workflow_audit
    )
    return {
        "head": sha1("repository-head"),
        "clean": True,
        "catalog": {
            "path": "manifests/core-builds.json",
            "file_sha256": sha256("catalog-file"),
        },
        "toolchain_lock": {
            "path": "manifests/toolchain-lock.json",
            "file_sha256": sha256("toolchain-file"),
            "content_sha256": sha256("toolchain-content"),
        },
        "commit_blacklist": {
            "path": "manifests/commit-blacklist.json",
            "file_sha256": sha256("blacklist-file"),
            "content_sha256": sha256("blacklist-content"),
        },
        "pipeline_bundle": {
            "file_sha256": sha256("pipeline-bundle-file"),
            "content_sha256": sha256("pipeline-bundle-content"),
        },
        "workflow_audit": workflow_audit,
        "orchestration": {
            "coordinator": {
                "path": ".github/workflows/release-candidate.yml",
                "file_sha256": sha256("release-coordinator-workflow"),
            },
            "worker": {
                "path": ".github/workflows/_build-one-core.yml",
                "file_sha256": sha256("release-worker-workflow"),
            },
        },
    }


def release_row(core_id: str) -> dict[str, Any]:
    pin_id = f"{core_id}-golden-v1"
    package = package_bytes(core_id)
    targets = []
    for architecture, profile in (
        ("arm64", "ra64-universal-v1"),
        ("armhf", "ra32-a30-v1"),
    ):
        targets.append(
            {
                "architecture": architecture,
                "execution_profile": profile,
                "artifact_name": f"{core_id}_libretro.so",
                "artifact_sha256": sha256(f"artifact:{core_id}:{architecture}"),
                "artifact_size": len(f"artifact:{core_id}:{architecture}"),
                "selected_build_record_sha256": sha256(
                    f"selected-build-record:{core_id}:{architecture}"
                ),
            }
        )
    return {
        "core_id": core_id,
        "core_spec_sha256": sha256(f"core-spec:{core_id}"),
        "workflow": {
            "path": f".github/workflows/build-{core_id}.yml",
            "file_sha256": sha256(f"workflow:{core_id}"),
        },
        "source": {
            "url": f"https://example.invalid/libretro-{core_id}.git",
            "requested_ref": "refs/heads/master",
            "commit": sha1(f"source-commit:{core_id}"),
            "tree": sha1(f"source-tree:{core_id}"),
            "submodules": [],
        },
        "pin": {
            "path": f"pins/core-sets/{pin_id}.json",
            "pin_id": pin_id,
            "file_sha256": sha256(f"pin-file:{core_id}"),
            "content_sha256": sha256(f"pin-content:{core_id}"),
        },
        "source_set": {
            "path": f"pins/source-sets/{pin_id}.json",
            "source_set_id": pin_id,
            "file_sha256": sha256(f"source-set-file:{core_id}"),
            "content_sha256": sha256(f"source-set-content:{core_id}"),
        },
        "compatibility": {
            "path": f"manifests/compatibility/{core_id}.json",
            "file_sha256": sha256(f"compatibility-file:{core_id}"),
            "content_sha256": sha256(f"compatibility-content:{core_id}"),
        },
        "package": {
            "name": f"{core_id}_libretro.zip",
            "sha256": sha256(package),
            "size": len(package),
        },
        "targets": targets,
        "core_group": None,
    }


def release_plan(
    core_ids: tuple[str, ...] = ("alpha", "beta"),
    *,
    candidate_id: str = "candidate-v1",
) -> dict[str, Any]:
    return construct_release_plan(
        candidate_id=candidate_id,
        scope="explicit",
        repository=repository_facts(),
        cores=[release_row(core_id) for core_id in core_ids],
    )


def normalized_e2e(
    plan: dict[str, Any],
    core_id: str,
    runner_selector: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    row = plan_core(plan, core_id)
    return {
        "run_id": run_id or f"{core_id}-{runner_selector}-run-v1",
        "file_sha256": sha256(f"e2e-file:{core_id}:{runner_selector}"),
        "content_sha256": sha256(f"e2e-content:{core_id}:{runner_selector}"),
        "runner": runner_contract_for_selector(runner_selector),
        "package": row["package"],
        "targets": [
            {
                "architecture": target["architecture"],
                "artifact_sha256": target["artifact_sha256"],
                "artifact_size": target["artifact_size"],
                "build_record_sha256": sha256(
                    f"fresh-build-record:{core_id}:{target['architecture']}"
                ),
            }
            for target in row["targets"]
        ],
    }


def write_plan_fixture(root: Path, plan: dict[str, Any]) -> Path:
    plan_path = root / "plan.json"
    write_release_plan(plan=plan, output_path=plan_path)
    assert document_file_sha256(plan) == sha256(plan_path.read_bytes())
    return plan_path


def write_result_bundle(
    root: Path,
    *,
    plan: dict[str, Any],
    plan_path: Path,
    core_id: str,
    runner_selector: str,
) -> dict[str, Any]:
    package_source = root / "package-inputs" / core_id / f"{core_id}_libretro.zip"
    package_source.parent.mkdir(parents=True, exist_ok=True)
    package_source.write_bytes(package_bytes(core_id))
    return write_core_result(
        plan=plan,
        plan_path=plan_path,
        core_id=core_id,
        runner_selector=runner_selector,
        e2e=normalized_e2e(plan, core_id, runner_selector),
        package_path=package_source,
        output_dir=root / "results" / core_id,
    )


def write_result_set(
    root: Path,
    *,
    plan: dict[str, Any],
    plan_path: Path,
    runner_selector: str,
    core_ids: tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    selected = core_ids or tuple(row["core_id"] for row in plan["cores"])
    return {
        core_id: write_result_bundle(
            root,
            plan=plan,
            plan_path=plan_path,
            core_id=core_id,
            runner_selector=runner_selector,
        )
        for core_id in selected
    }
