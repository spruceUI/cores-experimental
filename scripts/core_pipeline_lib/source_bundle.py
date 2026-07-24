"""Deterministic provenance identity for the pipeline's Python sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .errors import PipelineError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_LAUNCHER = REPOSITORY_ROOT / "scripts" / "core_pipeline.py"
PIPELINE_PACKAGE_ROOT = REPOSITORY_ROOT / "scripts" / "core_pipeline_lib"
PIPELINE_LAUNCHER_RELATIVE = "scripts/core_pipeline.py"
PIPELINE_PACKAGE_PREFIX = "scripts/core_pipeline_lib/"
PIPELINE_PACKAGE_INIT_RELATIVE = f"{PIPELINE_PACKAGE_PREFIX}__init__.py"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pipeline_bundle_content_sha256(files: dict[str, str]) -> str:
    material = {
        "schema_version": 1,
        "files": files,
    }
    return _sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def _resolved_repository_root() -> Path:
    try:
        root = REPOSITORY_ROOT.resolve(strict=True)
    except OSError as exc:
        raise PipelineError("pipeline repository root does not exist") from exc
    if not root.is_dir():
        raise PipelineError("pipeline repository root is not a directory")
    return root


def _contained_relative_path(path: Path, repository_root: Path, label: str) -> str:
    try:
        relative = path.relative_to(REPOSITORY_ROOT)
    except ValueError as exc:
        raise PipelineError(f"{label} is outside the pipeline repository") from exc

    current = REPOSITORY_ROOT
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PipelineError(f"{label} must not traverse a symlink")

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"{label} does not exist") from exc
    try:
        resolved.relative_to(repository_root)
    except ValueError as exc:
        raise PipelineError(f"{label} is outside the pipeline repository") from exc
    return relative.as_posix()


def _pipeline_source_paths() -> list[Path]:
    repository_root = _resolved_repository_root()
    launcher_relative = _contained_relative_path(
        PIPELINE_LAUNCHER, repository_root, "pipeline launcher"
    )
    if launcher_relative != PIPELINE_LAUNCHER_RELATIVE:
        raise PipelineError("pipeline launcher is not at its canonical path")
    if not PIPELINE_LAUNCHER.is_file():
        raise PipelineError("pipeline launcher is not a regular file")

    package_relative = _contained_relative_path(
        PIPELINE_PACKAGE_ROOT, repository_root, "pipeline package root"
    )
    if package_relative != PIPELINE_PACKAGE_PREFIX.removesuffix("/"):
        raise PipelineError("pipeline package root is not at its canonical path")
    if not PIPELINE_PACKAGE_ROOT.is_dir():
        raise PipelineError("pipeline package root is not a directory")

    package_sources: list[Path] = []
    for path in sorted(PIPELINE_PACKAGE_ROOT.rglob("*")):
        relative = _contained_relative_path(
            path, repository_root, "pipeline package entry"
        )
        if path.suffix != ".py":
            continue
        if not path.is_file():
            raise PipelineError(
                f"pipeline Python source is not a regular file: {relative}"
            )
        package_sources.append(path)

    if not package_sources:
        raise PipelineError("pipeline package contains no Python sources")
    if not any(
        str(path.relative_to(REPOSITORY_ROOT)) == PIPELINE_PACKAGE_INIT_RELATIVE
        for path in package_sources
    ):
        raise PipelineError("pipeline package is missing __init__.py")
    return [PIPELINE_LAUNCHER, *package_sources]


def pipeline_source_bundle() -> dict:
    files = {
        str(path.relative_to(REPOSITORY_ROOT)): _sha256_file(path)
        for path in _pipeline_source_paths()
    }
    bundle = {
        "schema_version": 1,
        "files": files,
    }
    bundle["content_sha256"] = pipeline_bundle_content_sha256(files)
    return bundle


def pipeline_source_bundle_is_well_formed(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "content_sha256",
        "files",
    }:
        return False
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        return False
    files = value.get("files")
    if not isinstance(files, dict) or not files:
        return False
    if PIPELINE_LAUNCHER_RELATIVE not in files:
        return False
    if PIPELINE_PACKAGE_INIT_RELATIVE not in files:
        return False
    for relative, digest in files.items():
        path = Path(relative) if isinstance(relative, str) else Path()
        if (
            not isinstance(relative, str)
            or not relative
            or path.is_absolute()
            or path.as_posix() != relative
            or any(part in {"", ".", ".."} for part in path.parts)
            or (
                relative != PIPELINE_LAUNCHER_RELATIVE
                and not relative.startswith(PIPELINE_PACKAGE_PREFIX)
            )
            or not relative.endswith(".py")
            or not isinstance(digest, str)
            or not SHA256_RE.fullmatch(digest)
        ):
            return False
    return value.get("content_sha256") == pipeline_bundle_content_sha256(files)
