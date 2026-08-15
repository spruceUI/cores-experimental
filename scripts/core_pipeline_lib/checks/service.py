"""Concrete no-shell subprocess service with secure one-read artifact capture."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
import stat
import subprocess

from ..errors import PipelineError
from .artifacts import MAX_STRUCTURED_OUTPUT_BYTES
from .model import (
    ArtifactRequest,
    CapturedStructuredOutput,
    ProcessCapture,
    ProcessDisposition,
)


READ_CHUNK_SIZE = 1024 * 1024


def _timeout_buffer(value: object) -> str | None:
    """Preserve absent timeout buffers instead of inventing complete logs."""

    if value is None:
        return None
    if type(value) is str:
        return value
    if type(value) is bytes:
        return value.decode("utf-8", errors="replace")
    return None


def _read_once_no_follow(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise PipelineError("structured output must be one regular non-linked file")
        if before.st_size < 0 or before.st_size > MAX_STRUCTURED_OUTPUT_BYTES:
            raise PipelineError("structured output exceeds the size limit")
        blocks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, READ_CHUNK_SIZE)
            if not block:
                break
            total += len(block)
            if total > MAX_STRUCTURED_OUTPUT_BYTES:
                raise PipelineError("structured output exceeds the size limit")
            blocks.append(block)
        after = os.fstat(descriptor)
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if not stable or total != before.st_size:
            raise PipelineError("structured output changed while it was captured")
        return b"".join(blocks)
    finally:
        os.close(descriptor)


class LocalSubprocessService:
    """Execute an exact argv and capture runner-owned outputs without a shell."""

    def run(
        self,
        *,
        argv: tuple[str, ...],
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
        shell: bool,
        artifact_requests: tuple[ArtifactRequest, ...] = (),
    ) -> ProcessCapture:
        if shell is not False:
            raise PipelineError("local check subprocesses must not use a shell")
        if type(argv) is not tuple or not argv or any(
            type(item) is not str or not item or "\x00" in item for item in argv
        ):
            raise PipelineError("local subprocess argv is invalid")
        if not isinstance(cwd, Path) or not cwd.is_absolute():
            raise PipelineError("local subprocess cwd must be absolute")
        if not isinstance(env, Mapping) or any(
            type(key) is not str or type(value) is not str
            for key, value in env.items()
        ):
            raise PipelineError("local subprocess environment is invalid")
        if type(timeout_seconds) not in {int, float} or timeout_seconds <= 0:
            raise PipelineError("local subprocess timeout is invalid")
        if type(artifact_requests) is not tuple or any(
            type(item) is not ArtifactRequest for item in artifact_requests
        ):
            raise PipelineError("local subprocess artifact requests are invalid")
        formats = tuple(item.format for item in artifact_requests)
        paths = tuple(item.path for item in artifact_requests)
        if len(formats) != len(set(formats)) or len(paths) != len(set(paths)):
            raise PipelineError("local subprocess artifact requests must be unique")
        for request in artifact_requests:
            if request.path.exists() or request.path.is_symlink():
                raise PipelineError("runner-owned artifact path already exists")
            try:
                parent = request.path.parent.lstat()
            except OSError as exc:
                raise PipelineError("runner-owned artifact directory is unavailable") from exc
            if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
                raise PipelineError("runner-owned artifact directory is not a real directory")

        try:
            try:
                completed = subprocess.run(
                    list(argv),
                    cwd=cwd,
                    env=dict(env),
                    timeout=float(timeout_seconds),
                    shell=False,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            except subprocess.TimeoutExpired as exc:
                return ProcessCapture(
                    disposition=ProcessDisposition.TIMED_OUT,
                    returncode=None,
                    stdout=_timeout_buffer(exc.stdout),
                    stderr=_timeout_buffer(exc.stderr),
                )
            if type(completed.returncode) is not int:
                return ProcessCapture(
                    disposition=ProcessDisposition.COMPLETED,
                    returncode=None,
                    stdout=(completed.stdout if type(completed.stdout) is str else None),
                    stderr=(completed.stderr if type(completed.stderr) is str else None),
                    artifact_error="subprocess returned a malformed completion record",
                )
            outputs: list[CapturedStructuredOutput] = []
            artifact_error: str | None = None
            for request in artifact_requests:
                try:
                    content = _read_once_no_follow(request.path)
                except (OSError, PipelineError) as exc:
                    artifact_error = (
                        f"cannot securely capture {request.format.value} output: "
                        f"{type(exc).__name__}"
                    )
                    break
                outputs.append(
                    CapturedStructuredOutput(
                        format=request.format,
                        content=content,
                    )
                )
            return ProcessCapture(
                disposition=ProcessDisposition.COMPLETED,
                returncode=completed.returncode,
                stdout=(completed.stdout if type(completed.stdout) is str else None),
                stderr=(completed.stderr if type(completed.stderr) is str else None),
                structured_outputs=tuple(outputs),
                artifact_error=artifact_error,
            )
        finally:
            for request in artifact_requests:
                try:
                    request.path.unlink(missing_ok=True)
                except OSError:
                    # The TemporaryDirectory owner performs a second exact-scope
                    # cleanup.  Capture validation still fails if a file could
                    # not be read or authenticated above.
                    pass


__all__ = ["LocalSubprocessService"]
