"""Shared fail-closed path and repository-state validation for runners."""

from __future__ import annotations

import os
from pathlib import Path
import re

from .errors import RunnerProfileError
from .model import RunnerRequest


GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def absolute_exact_path(value: object, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise RunnerProfileError(f"{label} must be a path")
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw:
        raise RunnerProfileError(f"{label} must be a non-empty path")
    path = Path(raw)
    if not path.is_absolute():
        raise RunnerProfileError(f"{label} must be absolute")
    normalized = Path(os.path.normpath(raw))
    if path != normalized:
        raise RunnerProfileError(f"{label} must be an exact normalized path")
    return path


def require_real_directory(path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RunnerProfileError(f"{label} must be an existing directory") from exc
    if resolved != path:
        raise RunnerProfileError(f"{label} must not traverse a symlink")
    if not path.is_dir():
        raise RunnerProfileError(f"{label} must be an existing directory")
    return resolved


def require_contained_output(
    repository_root: Path,
    output_root_value: object,
) -> Path:
    output_root = absolute_exact_path(output_root_value, "output root")
    try:
        relative = output_root.relative_to(repository_root)
    except ValueError as exc:
        raise RunnerProfileError(
            "output root must be contained by the repository"
        ) from exc
    if not relative.parts:
        raise RunnerProfileError("output root must be below the repository root")

    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise RunnerProfileError("output root must not traverse a symlink")
        if current.exists() and current != output_root and not current.is_dir():
            raise RunnerProfileError("output root parent must be a directory")
    if output_root.exists() and not output_root.is_dir():
        raise RunnerProfileError("output root must be a directory when it exists")
    return output_root


def validate_repository_state(
    request: RunnerRequest,
) -> tuple[str | None, bool | None]:
    head = request.repository_head
    if head is not None and (
        not isinstance(head, str) or GIT_COMMIT_PATTERN.fullmatch(head) is None
    ):
        raise RunnerProfileError(
            "repository head must be an exact lowercase 40-character commit ID"
        )
    clean = request.repository_clean
    if clean is not None and type(clean) is not bool:
        raise RunnerProfileError(
            "repository clean state must be a boolean when supplied"
        )
    return head, clean


def validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RunnerProfileError(
            "run ID must contain only letters, digits, dot, underscore, or dash"
        )
    return run_id


def validate_new_run_id(run_id: object) -> str:
    """Validate a user-supplied identity for newly created local evidence.

    Historical readers deliberately continue to use ``validate_run_id`` (or
    their frozen record contract) so tranche-named evidence remains auditable.
    """

    checked = validate_run_id(run_id)
    if "tranche" in checked.casefold():
        raise RunnerProfileError(
            "new local or simulated-Actions run ID must not contain tranche"
        )
    return checked


def check_run_root(
    repository_root: Path, output_root: Path, run_id: str
) -> Path:
    run_root = output_root / run_id
    try:
        run_root.relative_to(repository_root)
    except ValueError as exc:  # Run IDs cannot currently introduce separators.
        raise RunnerProfileError("run output escapes the repository") from exc
    if run_root.is_symlink():
        raise RunnerProfileError("run output must not be a symlink")
    if run_root.exists() and not run_root.is_dir():
        raise RunnerProfileError("run output must be a directory when it exists")
    return run_root
