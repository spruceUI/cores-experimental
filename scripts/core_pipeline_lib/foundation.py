"""Process, JSON, hashing, locking, and contained-path primitives."""

from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from .errors import PipelineError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PipelineError(
            f"command failed ({result.returncode}): {shlex.join(args)}\n{detail}"
        )
    return result


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def atomic_create_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.link(temporary, path)
    except FileExistsError as exc:
        raise PipelineError(f"refusing to replace existing pin manifest: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def durable_atomic_channel_write(path: Path, value: object, *, create: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(rendered)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        if create:
            os.link(temporary, path)
            temporary.unlink()
            temporary = None
        else:
            os.replace(temporary, path)
            temporary = None
        directory_fd = os.open(
            path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except FileExistsError as exc:
        raise PipelineError(f"channel pointer appeared during creation: {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def manifest_lock(path: Path, repository_root: Path = REPOSITORY_ROOT):
    lock_id = sha256_bytes(str(path.resolve()).encode())
    lock_path = repository_root / ".local-e2e" / "locks" / f"{lock_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def decode_json_object(raw: bytes, label: str | Path) -> dict:
    """Decode one strict UTF-8 JSON object from an existing byte snapshot."""

    try:
        text = raw.decode("utf-8")
        value = json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PipelineError(f"cannot load JSON from {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise PipelineError(f"expected a JSON object in {label}")
    return value


def load_json_with_sha256(path: Path) -> tuple[dict, str]:
    """Parse and hash one JSON object from the same immutable byte snapshot."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PipelineError(f"cannot load JSON from {path}: {exc}") from exc
    value = decode_json_object(raw, path)
    return value, sha256_bytes(raw)


def load_json(path: Path) -> dict:
    value, _file_sha256 = load_json_with_sha256(path)
    return value


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_child(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise PipelineError(f"{label} must be a relative path")
    root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PipelineError(f"{label} escapes its allowed root") from exc
    return resolved


def require_contained(path: Path, root: Path, label: str) -> Path:
    resolved = path.resolve()
    root = root.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PipelineError(f"{label} must be contained by {root}") from exc
    return resolved


def require_manifest_reference_path(
    reference: dict,
    allowed_root: Path,
    label: str,
    repository_root: Path = REPOSITORY_ROOT,
) -> Path:
    raw_path = reference.get("path", "")
    relative = Path(raw_path)
    if (
        not raw_path
        or relative.is_absolute()
        or relative.as_posix() != raw_path
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PipelineError(f"{label} path is not an exact relative path")
    unresolved = repository_root
    for part in relative.parts:
        unresolved /= part
        if unresolved.is_symlink():
            raise PipelineError(f"{label} path must not traverse a symlink")
    return require_contained(
        safe_child(repository_root, raw_path, label), allowed_root, label
    )
