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
