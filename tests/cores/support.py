"""Shared loading helpers for per-core evidence tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load_document(path: Path) -> dict[str, Any]:
    """Load one tracked JSON document as an object."""

    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"expected a JSON object: {path}")
    return document


def write_document(path: Path, document: dict[str, Any]) -> None:
    """Write a deterministic temporary JSON fixture."""

    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    """Hash one temporary fixture file without pipeline policy coupling."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def refresh_copied_e2e(
    run_root: Path,
    evidence: dict[str, Any],
    content_hasher: Callable[[dict[str, Any]], str],
) -> None:
    """Rebind copied build-record bytes and the E2E semantic digest."""

    for build in evidence["builds"]:
        record_path = ROOT / build["record"]
        build["record_sha256"] = file_sha256(record_path)
    evidence["content_sha256"] = content_hasher(evidence)
    write_document(run_root / "e2e-record.json", evidence)


@contextmanager
def copied_e2e_run(
    source_run_id: str,
    *,
    prefix: str,
    content_hasher: Callable[[dict[str, Any]], str],
) -> Iterator[tuple[Path, dict[str, Any]]]:
    """Copy ignored run evidence and path-bind it to a temporary run ID."""

    runs_root = ROOT / ".local-e2e" / "runs"
    source_root = runs_root / source_run_id
    with tempfile.TemporaryDirectory(dir=runs_root, prefix=prefix) as temporary:
        run_root = Path(temporary)
        shutil.copytree(source_root, run_root, dirs_exist_ok=True)
        evidence = load_document(run_root / "e2e-record.json")
        evidence["run_id"] = run_root.name
        for build in evidence["builds"]:
            original = Path(build["record"])
            build["record"] = str(
                Path(".local-e2e")
                / "runs"
                / run_root.name
                / Path(*original.parts[3:])
            )
        refresh_copied_e2e(run_root, evidence, content_hasher)
        yield run_root, evidence


def load_core_documents(
    core_id: str,
    pin_name: str,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    """Load the individual pin and compatibility document for one core."""

    pin_path = ROOT / "pins" / "core-sets" / pin_name
    compatibility_path = (
        ROOT / "manifests" / "compatibility" / f"{core_id}.json"
    )
    return (
        pin_path,
        load_document(pin_path),
        compatibility_path,
        load_document(compatibility_path),
    )


def evidence_index(core_id: str) -> dict[str, Any]:
    """Load the generated per-core evidence index (pins/evidence)."""

    return load_document(ROOT / "pins" / "evidence" / f"{core_id}.json")


def evidence_handles(core_id: str) -> dict[str, Any]:
    """Legacy-shaped promotion-derived constants for one core.

    Derived entirely from the tracked evidence index and catalog so that
    per-core test files carry no transcribed literals; the parametric
    gate (tests/test_evidence_bindings.py) proves the index against the
    promoted disk state.
    """

    index = evidence_index(core_id)
    spec = load_document(ROOT / "manifests" / "core-builds.json")["cores"][
        core_id
    ]
    compatibility = load_document(
        ROOT / "manifests" / "compatibility" / f"{core_id}.json"
    )
    selected = index["runs"]["selected"]
    reproduction = index["runs"]["reproduction"]
    targets: dict[str, Any] = {}
    for arch, bound in index["targets"].items():
        runs = {
            selected["run_id"]: selected["builds"][arch],
            reproduction["run_id"]: reproduction["builds"][arch],
        }
        targets[arch] = {
            **{
                key: compatibility["targets"][arch][key]
                for key in ("elf", "needed", "version_requirements")
                if key in compatibility["targets"][arch]
            },
            "execution_profile_id": {
                "arm64": "ra64-universal-v1",
                "armhf": "ra32-a30-v1",
            }[arch],
            "artifact_sha256": bound["artifact_sha256"],
            "artifact_size": bound["artifact_size"],
            **_imported_artifact(core_id, index, arch),
            "image_id": bound["image_id"],
            "archive_sha256": bound["toolchain_archive_sha256"],
            "toolchain_archive_sha256": bound["toolchain_archive_sha256"],
            "toolchain_archive_size": bound["toolchain_archive_size"],
            "record_sha256": {
                run_id: build["record_sha256"]
                for run_id, build in runs.items()
            },
            "log_sha256": {
                run_id: build["log_sha256"] for run_id, build in runs.items()
            },
            "log_size": {
                run_id: build["log_size"] for run_id, build in runs.items()
            },
        }
    semantic_id = index["semantic_id"]
    source_commit = spec["source"]["commit"]
    return {
        "SEMANTIC_ID": semantic_id,
        "PIN_NAME": f"{semantic_id}.json",
        "PIN_PATH": index["pin_path"],
        "SOURCE_SET_PATH": index["source_set_path"],
        "SOURCE_COMMIT": source_commit,
        "SOURCE_TREE": spec["source"]["tree"],
        "SOURCE_LOCK_ID": f"{core_id}-{source_commit[:12]}",
        "SELECTION_SHA256": index["selection_sha256"],
        "PACKAGE_SHA256": index["package"]["sha256"],
        "PACKAGE_SIZE": index["package"]["size"],
        "SELECTED_RUN": selected["run_id"],
        "REPRODUCTION_RUN": reproduction["run_id"],
        "E2E_FILE_SHA256": {
            selected["run_id"]: selected["e2e_file_sha256"],
            reproduction["run_id"]: reproduction["e2e_file_sha256"],
        },
        "E2E_CONTENT_SHA256": {
            selected["run_id"]: selected["e2e_content_sha256"],
            reproduction["run_id"]: reproduction["e2e_content_sha256"],
        },
        "SELECTED_E2E_CONTENT_SHA256": selected["e2e_content_sha256"],
        "REPRODUCTION_E2E_CONTENT_SHA256": reproduction["e2e_content_sha256"],
        "COMPATIBILITY_FILE_SHA256": index["compatibility"]["file_sha256"],
        "COMPATIBILITY_CONTENT_SHA256": index["compatibility"][
            "content_sha256"
        ],
        "REPOSITORY_COMMIT": selected["builds"][
            next(iter(index["targets"]))
        ]["repository_head"],
        "TARGETS": targets,
        **_recipe_handles(core_id, index, selected),
    }


def _recipe_handles(
    core_id: str, index: dict[str, Any], selected: dict[str, Any]
) -> dict[str, Any]:
    """Recipe/toolchain identity facts from the selected run's record."""

    first_arch = next(iter(index["targets"]))
    record = load_document(
        ROOT
        / ".local-e2e/runs"
        / selected["run_id"]
        / core_id
        / first_arch
        / "build-record.json"
    )
    recipe = record["recipe"]
    toolchain = record["toolchain"]
    lock = toolchain["archive_provenance"]["lock"]
    pin_path = ROOT / index["pin_path"]
    handles: dict[str, Any] = {
        "PIN_FILE_SHA256": file_sha256(pin_path),
        "PIN_CONTENT_SHA256": load_document(pin_path)["content_sha256"],
        "CATALOG_SHA256": recipe["catalog_sha256"],
        "CORE_SPEC_SHA256": recipe["core_spec_sha256"],
        "PIPELINE_SHA256": recipe["pipeline_sha256"],
        "PIPELINE_BUNDLE_CONTENT_SHA256": recipe["pipeline_bundle"][
            "content_sha256"
        ],
        "WORKFLOW_SHA256": recipe["workflow_sha256"],
        "RECIPE_HEAD": recipe["repository_head"],
        "TOOLCHAIN_LOCK_FILE_SHA256": lock["file_sha256"],
        "TOOLCHAIN_LOCK_CONTENT_SHA256": lock["content_sha256"],
        "LIBRETRO_SUPER_COMMIT": toolchain.get("libretro_super_commit"),
    }
    git_version = record["build"].get("git_version")
    if isinstance(git_version, dict):
        handles["GIT_VERSION"] = git_version.get("value")
    handles["PIPELINE_BUNDLE_SHA256"] = handles[
        "PIPELINE_BUNDLE_CONTENT_SHA256"
    ]
    handles["REPOSITORY_HEAD"] = recipe["repository_head"]
    spec = load_document(ROOT / "manifests" / "core-builds.json")["cores"][
        core_id
    ]
    handles["SOURCE_URL"] = spec["source"]["url"]
    lock_path = (
        f"pins/sources/{core_id}/{spec['source']['commit']}.json"
    )
    handles["SOURCE_LOCK_PATH"] = lock_path
    handles["SOURCE_LOCK_FILE_SHA256"] = file_sha256(ROOT / lock_path)
    handles["SOURCE_LOCK_CONTENT_SHA256"] = load_document(
        ROOT / lock_path
    )["content_sha256"]
    source_set_path = ROOT / index["source_set_path"]
    handles["SOURCE_SET_FILE_SHA256"] = file_sha256(source_set_path)
    handles["SOURCE_SET_CONTENT_SHA256"] = load_document(source_set_path)[
        "content_sha256"
    ]
    metadata_path = (
        ROOT
        / ".local-e2e/runs"
        / selected["run_id"]
        / core_id
        / first_arch
        / record["metadata"]["path"]
    )
    if metadata_path.exists():
        handles["METADATA_SHA256"] = file_sha256(metadata_path)
    return handles


def _imported_artifact(
    core_id: str, index: dict[str, Any], arch: str
) -> dict[str, Any]:
    """Shipped-baseline artifact digest from the semantic nightly golden."""

    golden_path = (
        ROOT
        / ".local-e2e/nightlies"
        / index["semantic_id"]
        / "golden.json"
    )
    if not golden_path.exists():
        return {}
    artifacts = load_document(golden_path)["cores"][core_id].get(
        "artifacts", {}
    )
    if arch not in artifacts:
        return {}
    return {"imported_artifact_sha256": artifacts[arch]["sha256"]}
