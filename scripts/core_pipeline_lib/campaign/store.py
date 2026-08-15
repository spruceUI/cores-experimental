"""No-follow campaign storage and the sole mutable-pointer transaction.

The campaign store has two deliberately different mutation models:

* immutable objects are create-or-verify content-addressed files; and
* one caller-selected campaign pointer is replaced under one exclusive lock.

All filesystem traversal is anchored at an already-open repository directory.
No authority-bearing operation resolves paths through symlinks.  Failed
transactions retain valid immutable objects for deterministic resume, while a
pointer rollback touches the pointer only when its exact inode and bytes are
still owned by the transaction.

The lock is a cooperative-writer boundary.  Identity and content checks are
placed immediately beside publication and rollback, but portable POSIX calls
cannot eliminate the final check-to-link, check-to-replace, or check-to-unlink
window against a writer that ignores the lock.  Rollback therefore mutates
only the exact inode and bytes published by this transaction; it preserves a
foreign replacement rather than claiming stronger compare-exchange semantics.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
from typing import Literal, TypeAlias, TypeVar

from ..errors import PipelineError
from ..foundation import sha256_bytes
from .json_wire import validate_utf8_string
from .model import EvidenceRef, Receipt


FaultHook: TypeAlias = Callable[[str], None]
LockVerifier: TypeAlias = Callable[[], None]
Disposition: TypeAlias = Literal["created", "verified"]
StageCallback: TypeAlias = Callable[["TransactionView"], Receipt]
_VerificationResultT = TypeVar("_VerificationResultT")

FAULT_SEAMS = (
    "cas.after_temp_create",
    "cas.after_file_fsync",
    "cas.after_publish",
    "cas.after_directory_fsync",
    "pointer.after_lock",
    "pointer.after_cas",
    "pointer.after_required_verify",
    "pointer.after_pre_commit",
    "pointer.after_temp_create",
    "pointer.after_file_fsync",
    "pointer.before_replace",
    "pointer.after_replace",
    "pointer.after_directory_fsync",
    "pointer.after_post_commit",
    "rollback.before_restore",
    "rollback.after_restore",
    "rollback.after_directory_fsync",
    "rollback.before_owned_unlink",
    "rollback.after_owned_unlink",
    "rollback.after_unlink_directory_fsync",
)
_FAULT_SEAM_SET = frozenset(FAULT_SEAMS)

_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_FILE_MODE = 0o644
_LOCK_MODE = 0o600
_DIRECTORY_MODE = 0o755
_READ_SIZE = 1024 * 1024

_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


@dataclass(frozen=True, slots=True)
class StoreResult:
    """Result of publishing or independently verifying one immutable object."""

    reference: EvidenceRef
    disposition: Disposition

    def __post_init__(self) -> None:
        if type(self.reference) is not EvidenceRef:
            raise PipelineError("store result reference is invalid")
        if self.disposition not in {"created", "verified"}:
            raise PipelineError("store result disposition is invalid")


@dataclass(frozen=True, slots=True)
class PointerState:
    """One authenticated opaque-byte snapshot of a mutable pointer."""

    reference: EvidenceRef
    raw: bytes

    def __post_init__(self) -> None:
        if type(self.reference) is not EvidenceRef:
            raise PipelineError("pointer state reference is invalid")
        if type(self.raw) is not bytes:
            raise PipelineError("pointer state payload is invalid")
        if (
            len(self.raw) != self.reference.size
            or sha256_bytes(self.raw) != self.reference.file_sha256
        ):
            raise PipelineError("pointer state bytes do not match their reference")


@dataclass(frozen=True, slots=True)
class CommitResult:
    """Exact before/after states and stage receipts for one pointer commit."""

    before: PointerState | None
    after: PointerState
    pre_commit: Receipt
    post_commit: Receipt

    def __post_init__(self) -> None:
        if self.before is not None and type(self.before) is not PointerState:
            raise PipelineError("commit result predecessor is invalid")
        if type(self.after) is not PointerState:
            raise PipelineError("commit result successor is invalid")
        if (
            type(self.pre_commit) is not Receipt
            or self.pre_commit.stage != "pre-commit"
            or self.pre_commit.status != "passed"
        ):
            raise PipelineError("commit result pre-commit receipt is invalid")
        if (
            type(self.post_commit) is not Receipt
            or self.post_commit.stage != "post-commit"
            or self.post_commit.status != "passed"
        ):
            raise PipelineError("commit result post-commit receipt is invalid")


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    raw: bytes
    identity: tuple[int, int]


def _relative_parts(value: object, *, label: str) -> tuple[str, ...]:
    value = validate_utf8_string(value, label=label)
    if not value or "\x00" in value or "\\" in value or "//" in value:
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return path.parts


def _require_identifier(value: object, *, label: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def canonical_object_reference(
    *,
    state_relative: str,
    kind: str,
    raw: bytes,
    target_content_sha256: str | None,
) -> EvidenceRef:
    """Derive the one canonical immutable-object reference without I/O."""

    state_parts = _relative_parts(
        state_relative,
        label="campaign state path",
    )
    _require_identifier(kind, label="campaign object kind")
    if type(raw) is not bytes:
        raise PipelineError("campaign object raw payload must be exact bytes")
    file_sha256 = sha256_bytes(raw)
    return EvidenceRef(
        kind=kind,
        path=PurePosixPath(
            *state_parts,
            "objects",
            kind,
            "sha256",
            file_sha256[:2],
            file_sha256,
        ).as_posix(),
        file_sha256=file_sha256,
        target_content_sha256=target_content_sha256,
        size=len(raw),
    )


def _require_exact_file_stat(value: os.stat_result, *, mode: int, label: str) -> None:
    if not stat.S_ISREG(value.st_mode):
        raise PipelineError(f"{label} must be a regular file")
    if stat.S_IMODE(value.st_mode) != mode:
        raise PipelineError(f"{label} mode is invalid")
    if value.st_nlink != 1:
        raise PipelineError(f"{label} link count is invalid")


def _write_all(file_descriptor: int, raw: bytes) -> None:
    remaining = memoryview(raw)
    while remaining:
        written = os.write(file_descriptor, remaining)
        if written <= 0:
            raise OSError("campaign store write made no progress")
        remaining = remaining[written:]


class CampaignStore:
    """Descriptor-anchored immutable store and campaign pointer namespace."""

    def __init__(
        self,
        repository_root: Path,
        state_relative: str,
        *,
        fault_hook: FaultHook | None = None,
    ) -> None:
        if not isinstance(repository_root, Path):
            raise PipelineError("campaign repository_root must be a Path")
        if _O_DIRECTORY == 0 or _O_NOFOLLOW == 0:
            raise PipelineError("campaign store requires O_DIRECTORY and O_NOFOLLOW")
        repository_root = repository_root.absolute()
        try:
            root_stat = os.lstat(repository_root)
        except OSError as exc:
            raise PipelineError(
                f"campaign repository root is unavailable: {exc}"
            ) from exc
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
            raise PipelineError("campaign repository root must be a real directory")
        self._repository_root = repository_root
        self._root_identity = (root_stat.st_dev, root_stat.st_ino)
        self._state_parts = _relative_parts(
            state_relative,
            label="campaign state path",
        )
        self._state_relative = PurePosixPath(*self._state_parts).as_posix()
        if fault_hook is not None and not callable(fault_hook):
            raise PipelineError("campaign fault_hook must be callable")
        self._fault_hook = fault_hook

        # Prove the root can be opened without following its final component.
        root_fd = self._open_root()
        os.close(root_fd)

    @property
    def repository_root(self) -> Path:
        return self._repository_root

    @property
    def state_relative(self) -> str:
        return self._state_relative

    def _hit(self, seam: str) -> None:
        if seam not in _FAULT_SEAM_SET:
            raise AssertionError(f"unknown campaign fault seam: {seam}")
        if self._fault_hook is not None:
            self._fault_hook(seam)

    def _open_root(self) -> int:
        flags = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
        try:
            file_descriptor = os.open(self._repository_root, flags)
        except OSError as exc:
            raise PipelineError(f"cannot open campaign repository root: {exc}") from exc
        root_stat = os.fstat(file_descriptor)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or (root_stat.st_dev, root_stat.st_ino) != self._root_identity
        ):
            os.close(file_descriptor)
            raise PipelineError("campaign repository root identity changed")
        return file_descriptor

    def _open_directory(
        self,
        parts: tuple[str, ...],
        *,
        create: bool,
        missing_ok: bool = False,
        label: str,
    ) -> int | None:
        current_fd = self._open_root()
        try:
            for part in parts:
                created = False
                if create:
                    try:
                        os.mkdir(part, _DIRECTORY_MODE, dir_fd=current_fd)
                    except FileExistsError:
                        pass
                    except OSError as exc:
                        raise PipelineError(f"cannot create {label}: {exc}") from exc
                    else:
                        created = True
                flags = os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC
                try:
                    child_fd = os.open(part, flags, dir_fd=current_fd)
                except FileNotFoundError:
                    if missing_ok and not create:
                        os.close(current_fd)
                        return None
                    raise PipelineError(f"{label} is unavailable") from None
                except OSError as exc:
                    raise PipelineError(
                        f"{label} must not traverse a symlink or non-directory: {exc}"
                    ) from exc
                child_stat = os.fstat(child_fd)
                if not stat.S_ISDIR(child_stat.st_mode):
                    os.close(child_fd)
                    raise PipelineError(f"{label} component is not a directory")
                if created:
                    os.fchmod(child_fd, _DIRECTORY_MODE)
                    os.fsync(child_fd)
                    os.fsync(current_fd)
                os.close(current_fd)
                current_fd = child_fd
            return current_fd
        except BaseException:
            try:
                os.close(current_fd)
            except OSError:
                pass
            raise

    def _open_parent(
        self,
        relative: str,
        *,
        create: bool,
        missing_ok: bool = False,
        label: str,
    ) -> tuple[int | None, str]:
        parts = _relative_parts(relative, label=label)
        parent_fd = self._open_directory(
            parts[:-1],
            create=create,
            missing_ok=missing_ok,
            label=f"{label} parent",
        )
        return parent_fd, parts[-1]

    def _read_file_at(
        self,
        parent_fd: int,
        leaf: str,
        *,
        missing_ok: bool,
        mode: int,
        label: str,
    ) -> _FileSnapshot | None:
        flags = os.O_RDONLY | _O_NOFOLLOW | _O_CLOEXEC | _O_NONBLOCK
        try:
            file_descriptor = os.open(leaf, flags, dir_fd=parent_fd)
        except FileNotFoundError:
            if missing_ok:
                return None
            raise PipelineError(f"{label} is missing") from None
        except OSError as exc:
            raise PipelineError(
                f"cannot open {label} without following links: {exc}"
            ) from exc
        try:
            before = os.fstat(file_descriptor)
            _require_exact_file_stat(before, mode=mode, label=label)
            blocks: list[bytes] = []
            while True:
                block = os.read(file_descriptor, _READ_SIZE)
                if not block:
                    break
                blocks.append(block)
            raw = b"".join(blocks)
            after = os.fstat(file_descriptor)
            if (
                (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
                or before.st_ctime_ns != after.st_ctime_ns
                or len(raw) != after.st_size
            ):
                raise PipelineError(f"{label} changed while it was read")
            try:
                path_stat = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise PipelineError(
                    f"{label} changed after it was read: {exc}"
                ) from exc
            if (path_stat.st_dev, path_stat.st_ino) != (after.st_dev, after.st_ino):
                raise PipelineError(f"{label} changed after it was read")
            _require_exact_file_stat(path_stat, mode=mode, label=label)
            return _FileSnapshot(
                raw=raw,
                identity=(after.st_dev, after.st_ino),
            )
        finally:
            os.close(file_descriptor)

    def _authenticate_reference(self, reference: EvidenceRef, raw: bytes) -> None:
        if len(raw) != reference.size or sha256_bytes(raw) != reference.file_sha256:
            raise PipelineError("evidence bytes do not match their reference")

    def reference_for(
        self,
        *,
        kind: str,
        raw: bytes,
        target_content_sha256: str | None,
    ) -> EvidenceRef:
        reference = canonical_object_reference(
            state_relative=self._state_relative,
            kind=kind,
            raw=raw,
            target_content_sha256=target_content_sha256,
        )
        self._authenticate_reference(reference, raw)
        return reference

    def _temporary_file(self, parent_fd: int, *, mode: int) -> tuple[str, int]:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW | _O_CLOEXEC
        for _attempt in range(32):
            name = f".tmp-{os.getpid()}-{secrets.token_hex(12)}"
            try:
                file_descriptor = os.open(name, flags, mode, dir_fd=parent_fd)
            except FileExistsError:
                continue
            return name, file_descriptor
        raise PipelineError("cannot allocate a unique campaign temporary file")

    def create_or_verify(
        self,
        *,
        reference: EvidenceRef,
        raw: bytes,
    ) -> StoreResult:
        if type(reference) is not EvidenceRef or type(raw) is not bytes:
            raise PipelineError("campaign create-or-verify arguments are invalid")
        expected = self.reference_for(
            kind=reference.kind,
            raw=raw,
            target_content_sha256=reference.target_content_sha256,
        )
        if reference != expected:
            raise PipelineError("evidence reference path or identity is not canonical")
        return self._create_or_verify_authenticated(reference=reference, raw=raw)

    def create_or_verify_reference(
        self,
        *,
        reference: EvidenceRef,
        raw: bytes,
    ) -> StoreResult:
        """Create or verify one caller-authorized immutable evidence path.

        The caller owns path policy; this layer owns byte authentication and
        immutable publication.  Mutable pointer references are never accepted.
        """

        if type(reference) is not EvidenceRef or type(raw) is not bytes:
            raise PipelineError("campaign create-or-verify arguments are invalid")
        if reference.kind == "matrix-pointer":
            raise PipelineError(
                "caller-authorized immutable storage rejects matrix-pointer"
            )
        self._authenticate_reference(reference, raw)
        return self._create_or_verify_authenticated(reference=reference, raw=raw)

    def _create_or_verify_authenticated(
        self,
        *,
        reference: EvidenceRef,
        raw: bytes,
    ) -> StoreResult:
        parent_fd, leaf = self._open_parent(
            reference.path,
            create=True,
            label="content-addressed object",
        )
        assert parent_fd is not None
        temporary_name: str | None = None
        temporary_fd: int | None = None
        try:
            existing = self._read_file_at(
                parent_fd,
                leaf,
                missing_ok=True,
                mode=_FILE_MODE,
                label="content-addressed object",
            )
            if existing is not None:
                try:
                    self._authenticate_reference(reference, existing.raw)
                except PipelineError as exc:
                    raise PipelineError(
                        f"content-addressed store collision at {reference.path}"
                    ) from exc
                # Verification is durable too, but is not a create fault seam.
                os.fsync(parent_fd)
                return StoreResult(reference=reference, disposition="verified")

            temporary_name, temporary_fd = self._temporary_file(
                parent_fd,
                mode=_LOCK_MODE,
            )
            self._hit("cas.after_temp_create")
            _write_all(temporary_fd, raw)
            os.fchmod(temporary_fd, _FILE_MODE)
            os.fsync(temporary_fd)
            self._hit("cas.after_file_fsync")
            try:
                os.link(
                    temporary_name,
                    leaf,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileExistsError:
                os.close(temporary_fd)
                temporary_fd = None
                os.unlink(temporary_name, dir_fd=parent_fd)
                temporary_name = None
                concurrent = self._read_file_at(
                    parent_fd,
                    leaf,
                    missing_ok=False,
                    mode=_FILE_MODE,
                    label="content-addressed object",
                )
                assert concurrent is not None
                try:
                    self._authenticate_reference(reference, concurrent.raw)
                except PipelineError as exc:
                    raise PipelineError(
                        f"content-addressed store collision at {reference.path}"
                    ) from exc
                os.fsync(parent_fd)
                self._hit("cas.after_directory_fsync")
                return StoreResult(reference=reference, disposition="verified")

            self._hit("cas.after_publish")
            os.close(temporary_fd)
            temporary_fd = None
            os.unlink(temporary_name, dir_fd=parent_fd)
            temporary_name = None
            os.fsync(parent_fd)
            self._hit("cas.after_directory_fsync")
            published = self._read_file_at(
                parent_fd,
                leaf,
                missing_ok=False,
                mode=_FILE_MODE,
                label="content-addressed object",
            )
            assert published is not None
            self._authenticate_reference(reference, published.raw)
            return StoreResult(reference=reference, disposition="created")
        finally:
            if temporary_fd is not None:
                os.close(temporary_fd)
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
            os.close(parent_fd)

    def read_exact(self, reference: EvidenceRef) -> bytes:
        if type(reference) is not EvidenceRef:
            raise PipelineError("evidence reference is invalid")
        parent_fd, leaf = self._open_parent(
            reference.path,
            create=False,
            missing_ok=True,
            label="evidence object",
        )
        if parent_fd is None:
            raise PipelineError(f"evidence object is missing: {reference.path}")
        try:
            snapshot = self._read_file_at(
                parent_fd,
                leaf,
                missing_ok=False,
                mode=_FILE_MODE,
                label="evidence object",
            )
            assert snapshot is not None
            self._authenticate_reference(reference, snapshot.raw)
            return snapshot.raw
        finally:
            os.close(parent_fd)

    def read_snapshot(self, relative: str) -> bytes:
        """Read one stable raw snapshot without creating storage state.

        This is a bootstrap read for tracked inputs whose EvidenceRef does not
        exist yet.  Callers own strict decoding and must subsequently use an
        authenticated reference with :meth:`read_exact`.
        """

        parent_fd, leaf = self._open_parent(
            relative,
            create=False,
            missing_ok=True,
            label="campaign bootstrap snapshot",
        )
        if parent_fd is None:
            raise PipelineError(f"campaign bootstrap snapshot is missing: {relative}")
        try:
            snapshot = self._read_file_at(
                parent_fd,
                leaf,
                missing_ok=False,
                mode=_FILE_MODE,
                label="campaign bootstrap snapshot",
            )
            assert snapshot is not None
            return snapshot.raw
        finally:
            os.close(parent_fd)

    def _read_pointer_with_snapshot(
        self,
        reference: EvidenceRef,
    ) -> tuple[PointerState | None, _FileSnapshot | None]:
        if type(reference) is not EvidenceRef:
            raise PipelineError("pointer reference is invalid")
        parent_fd, leaf = self._open_parent(
            reference.path,
            create=False,
            missing_ok=True,
            label="campaign pointer",
        )
        if parent_fd is None:
            return None, None
        try:
            snapshot = self._read_file_at(
                parent_fd,
                leaf,
                missing_ok=True,
                mode=_FILE_MODE,
                label="campaign pointer",
            )
            if snapshot is None:
                return None, None
            self._authenticate_reference(reference, snapshot.raw)
            return PointerState(reference=reference, raw=snapshot.raw), snapshot
        finally:
            os.close(parent_fd)

    def read_pointer(self, reference: EvidenceRef) -> PointerState | None:
        """Read one pointer without creating state directories or lock files."""

        state, _snapshot = self._read_pointer_with_snapshot(reference)
        return state

    def _read_pointer_at(
        self,
        reference: EvidenceRef,
        parent_fd: int,
        leaf: str,
        *,
        missing_ok: bool,
    ) -> tuple[PointerState | None, _FileSnapshot | None]:
        snapshot = self._read_file_at(
            parent_fd,
            leaf,
            missing_ok=missing_ok,
            mode=_FILE_MODE,
            label="campaign pointer",
        )
        if snapshot is None:
            return None, None
        self._authenticate_reference(reference, snapshot.raw)
        return PointerState(reference=reference, raw=snapshot.raw), snapshot

    def _read_pointer_snapshot(self, relative: str) -> _FileSnapshot | None:
        parent_fd, leaf = self._open_parent(
            relative,
            create=False,
            missing_ok=True,
            label="campaign pointer",
        )
        if parent_fd is None:
            return None
        try:
            return self._read_file_at(
                parent_fd,
                leaf,
                missing_ok=True,
                mode=_FILE_MODE,
                label="campaign pointer",
            )
        finally:
            os.close(parent_fd)

    @contextmanager
    def _pointer_lock(
        self,
        campaign_id: str,
        *,
        create: bool = True,
        shared: bool = False,
        fire_acquire_fault: bool = True,
    ):
        relative = PurePosixPath(
            *self._state_parts,
            "locks",
            f"{campaign_id}.lock",
        ).as_posix()
        parent_fd, leaf = self._open_parent(
            relative,
            create=create,
            missing_ok=not create,
            label="campaign pointer lock",
        )
        if parent_fd is None:
            raise PipelineError("campaign pointer lock is missing")
        lock_fd: int | None = None
        created = False
        try:
            if create:
                create_flags = (
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | _O_NOFOLLOW
                    | _O_CLOEXEC
                    | _O_NONBLOCK
                )
                try:
                    lock_fd = os.open(
                        leaf,
                        create_flags,
                        _LOCK_MODE,
                        dir_fd=parent_fd,
                    )
                except FileExistsError:
                    try:
                        lock_fd = os.open(
                            leaf,
                            os.O_RDWR | _O_NOFOLLOW | _O_CLOEXEC | _O_NONBLOCK,
                            dir_fd=parent_fd,
                        )
                    except OSError as exc:
                        raise PipelineError(
                            f"cannot open campaign pointer lock safely: {exc}"
                        ) from exc
                else:
                    created = True
                    os.fchmod(lock_fd, _LOCK_MODE)
                    os.fsync(lock_fd)
                    os.fsync(parent_fd)
            else:
                try:
                    lock_fd = os.open(
                        leaf,
                        os.O_RDONLY | _O_NOFOLLOW | _O_CLOEXEC | _O_NONBLOCK,
                        dir_fd=parent_fd,
                    )
                except FileNotFoundError:
                    raise PipelineError("campaign pointer lock is missing") from None
                except OSError as exc:
                    raise PipelineError(
                        f"cannot open campaign pointer lock safely: {exc}"
                    ) from exc
            lock_stat = os.fstat(lock_fd)
            _require_exact_file_stat(
                lock_stat,
                mode=_LOCK_MODE,
                label="campaign pointer lock",
            )
            if not created:
                path_stat = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
                if (path_stat.st_dev, path_stat.st_ino) != (
                    lock_stat.st_dev,
                    lock_stat.st_ino,
                ):
                    raise PipelineError("campaign pointer lock changed while opened")

            def require_current_lock_path() -> None:
                current_parent_fd, current_leaf = self._open_parent(
                    relative,
                    create=False,
                    missing_ok=True,
                    label="campaign pointer lock",
                )
                if current_parent_fd is None:
                    raise PipelineError("campaign pointer lock path disappeared")
                try:
                    try:
                        current_stat = os.stat(
                            current_leaf,
                            dir_fd=current_parent_fd,
                            follow_symlinks=False,
                        )
                    except OSError as exc:
                        raise PipelineError(
                            f"campaign pointer lock changed while held: {exc}"
                        ) from exc
                    _require_exact_file_stat(
                        current_stat,
                        mode=_LOCK_MODE,
                        label="campaign pointer lock",
                    )
                    if (current_stat.st_dev, current_stat.st_ino) != (
                        lock_stat.st_dev,
                        lock_stat.st_ino,
                    ):
                        raise PipelineError(
                            "campaign pointer lock changed while held"
                        )
                finally:
                    os.close(current_parent_fd)

            lock_operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
            fcntl.flock(lock_fd, lock_operation)
            try:
                require_current_lock_path()
                if fire_acquire_fault:
                    self._hit("pointer.after_lock")
                    require_current_lock_path()
                yield require_current_lock_path
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(parent_fd)

    def verify_pointer(
        self,
        *,
        campaign_id: str,
        expected: EvidenceRef,
        validator: Callable[["VerificationView"], _VerificationResultT],
    ) -> _VerificationResultT:
        """Validate an exact pointer closure under the existing shared lock.

        This path is strictly read-only: it requires the lock namespace and
        file to exist already, fires no transaction fault seam, and rejects a
        pointer or lock-path replacement across the supplied callback.
        """

        campaign_id = _require_identifier(campaign_id, label="campaign_id")
        if (
            type(expected) is not EvidenceRef
            or expected.kind != "matrix-pointer"
            or expected.target_content_sha256 is None
        ):
            raise PipelineError("expected pointer must be an exact matrix-pointer ref")
        if not callable(validator):
            raise PipelineError("pointer verification validator must be callable")

        with self._pointer_lock(
            campaign_id,
            create=False,
            shared=True,
            fire_acquire_fault=False,
        ) as verify_lock:
            before, before_snapshot = self._read_pointer_with_snapshot(expected)
            if before is None or before_snapshot is None:
                raise PipelineError("expected campaign pointer is missing")
            verify_lock()
            view = VerificationView(
                _store=self,
                campaign_id=campaign_id,
                expected=expected,
            )
            result = validator(view)
            verify_lock()
            after, after_snapshot = self._read_pointer_with_snapshot(expected)
            if after is None or after_snapshot is None:
                raise PipelineError("campaign pointer changed during verification")
            if (
                after_snapshot.identity != before_snapshot.identity
                or after_snapshot.raw != before_snapshot.raw
            ):
                raise PipelineError("campaign pointer changed during verification")
            verify_lock()
            return result

    def pointer_transaction(
        self,
        *,
        campaign_id: str,
        expected: EvidenceRef | None,
        successor: EvidenceRef,
        successor_raw: bytes,
        required_objects: tuple[EvidenceRef, ...],
    ) -> "PointerTransaction":
        return PointerTransaction(
            store=self,
            campaign_id=campaign_id,
            expected=expected,
            successor=successor,
            successor_raw=successor_raw,
            required_objects=required_objects,
        )


@dataclass(frozen=True, slots=True)
class TransactionView:
    """Opaque read-only view supplied while the pointer lock is held."""

    _store: CampaignStore
    campaign_id: str
    expected: EvidenceRef | None
    successor: EvidenceRef

    def __post_init__(self) -> None:
        if type(self._store) is not CampaignStore:
            raise PipelineError("transaction view store is invalid")
        _require_identifier(self.campaign_id, label="campaign_id")
        if type(self.successor) is not EvidenceRef:
            raise PipelineError("transaction view successor is invalid")
        if self.expected is not None and (
            type(self.expected) is not EvidenceRef
            or self.expected.path != self.successor.path
            or self.expected.kind != self.successor.kind
        ):
            raise PipelineError("transaction view predecessor is invalid")

    def read_exact(self, reference: EvidenceRef) -> bytes:
        return self._store.read_exact(reference)

    def read_pointer(self, reference: EvidenceRef) -> PointerState | None:
        return self._store.read_pointer(reference)


@dataclass(frozen=True, slots=True)
class VerificationView:
    """Opaque read-only view supplied while the shared pointer lock is held."""

    _store: CampaignStore
    campaign_id: str
    expected: EvidenceRef

    def __post_init__(self) -> None:
        if type(self._store) is not CampaignStore:
            raise PipelineError("verification view store is invalid")
        _require_identifier(self.campaign_id, label="campaign_id")
        if (
            type(self.expected) is not EvidenceRef
            or self.expected.kind != "matrix-pointer"
            or self.expected.target_content_sha256 is None
        ):
            raise PipelineError("verification view pointer is invalid")

    def read_exact(self, reference: EvidenceRef) -> bytes:
        return self._store.read_exact(reference)

    def read_pointer(self, reference: EvidenceRef) -> PointerState | None:
        return self._store.read_pointer(reference)


class PointerTransaction:
    """Single-use compare-and-swap transaction for one campaign pointer.

    Stage callbacks are trusted semantic binders.  The store checks only exact
    Receipt type, stage, and passed status; H3 callers must perform transition
    validation and ``validate_plan_receipt`` before returning those receipts.
    """

    __slots__ = (
        "_store",
        "_campaign_id",
        "_expected",
        "_successor",
        "_successor_raw",
        "_required_objects",
        "_used",
    )

    def __init__(
        self,
        *,
        store: CampaignStore,
        campaign_id: str,
        expected: EvidenceRef | None,
        successor: EvidenceRef,
        successor_raw: bytes,
        required_objects: tuple[EvidenceRef, ...],
    ) -> None:
        if type(store) is not CampaignStore:
            raise PipelineError("pointer transaction store is invalid")
        campaign_id = _require_identifier(campaign_id, label="campaign_id")
        if type(successor) is not EvidenceRef or type(successor_raw) is not bytes:
            raise PipelineError("pointer successor reference/raw are invalid")
        store._authenticate_reference(successor, successor_raw)
        if expected is not None:
            if (
                type(expected) is not EvidenceRef
                or expected.path != successor.path
                or expected.kind != successor.kind
            ):
                raise PipelineError("expected pointer reference is invalid")
            if expected == successor:
                raise PipelineError(
                    "pointer successor must differ from its predecessor"
                )
        if type(required_objects) is not tuple or any(
            type(item) is not EvidenceRef for item in required_objects
        ):
            raise PipelineError("required_objects must be a tuple of EvidenceRef")
        keys = tuple((item.kind, item.path) for item in required_objects)
        if tuple(sorted(keys)) != keys or len(keys) != len(set(keys)):
            raise PipelineError(
                "required_objects must be sorted and unique by kind/path"
            )
        self._store = store
        self._campaign_id = campaign_id
        self._expected = expected
        self._successor = successor
        self._successor_raw = successor_raw
        self._required_objects = required_objects
        self._used = False

    @property
    def campaign_id(self) -> str:
        return self._campaign_id

    @property
    def successor_reference(self) -> EvidenceRef:
        return self._successor

    @property
    def expected_reference(self) -> EvidenceRef | None:
        return self._expected

    def _require_expected(
        self,
        snapshot: _FileSnapshot | None,
    ) -> PointerState | None:
        if self._expected is None:
            if snapshot is not None:
                raise PipelineError(
                    "campaign pointer compare-and-swap expected absence"
                )
            return None
        if snapshot is None:
            raise PipelineError(
                "campaign pointer compare-and-swap failed: "
                f"expected {self._expected.file_sha256}, found absent"
            )
        try:
            self._store._authenticate_reference(self._expected, snapshot.raw)
        except PipelineError as exc:
            raise PipelineError(
                "campaign pointer compare-and-swap failed: "
                f"expected {self._expected.file_sha256}, found "
                f"{sha256_bytes(snapshot.raw)}"
            ) from exc
        return PointerState(reference=self._expected, raw=snapshot.raw)

    @staticmethod
    def _same_snapshot(
        left: _FileSnapshot | None,
        right: _FileSnapshot | None,
    ) -> bool:
        if left is None or right is None:
            return left is right
        return left.identity == right.identity and left.raw == right.raw

    def _require_stage_receipt(self, value: object, *, stage: str) -> Receipt:
        if type(value) is not Receipt:
            raise PipelineError(f"{stage} validator did not return a Receipt")
        if value.stage != stage or value.status != "passed":
            raise PipelineError(f"{stage} receipt does not authorize the transaction")
        return value

    def _verify_required_objects(self) -> None:
        for reference in self._required_objects:
            self._store.read_exact(reference)

    def _hit_while_locked(self, seam: str, verify_lock: LockVerifier) -> None:
        self._store._hit(seam)
        verify_lock()

    def _owned_pointer_is_current(
        self,
        parent_fd: int,
        leaf: str,
        *,
        identity: tuple[int, int],
    ) -> bool:
        try:
            snapshot = self._store._read_file_at(
                parent_fd,
                leaf,
                missing_ok=True,
                mode=_FILE_MODE,
                label="campaign pointer",
            )
        except PipelineError:
            return False
        return (
            snapshot is not None
            and snapshot.identity == identity
            and snapshot.raw == self._successor_raw
        )

    def _rollback_pointer(
        self,
        *,
        parent_fd: int,
        leaf: str,
        before: PointerState | None,
        owned_identity: tuple[int, int],
    ) -> None:
        if not self._owned_pointer_is_current(
            parent_fd,
            leaf,
            identity=owned_identity,
        ):
            raise PipelineError("current pointer is no longer transaction-owned")

        if before is None:
            self._store._hit("rollback.before_owned_unlink")
            if not self._owned_pointer_is_current(
                parent_fd,
                leaf,
                identity=owned_identity,
            ):
                raise PipelineError("current pointer changed before owned unlink")
            os.unlink(leaf, dir_fd=parent_fd)
            self._store._hit("rollback.after_owned_unlink")
            os.fsync(parent_fd)
            self._store._hit("rollback.after_unlink_directory_fsync")
            remaining = self._store._read_file_at(
                parent_fd,
                leaf,
                missing_ok=True,
                mode=_FILE_MODE,
                label="campaign pointer",
            )
            if remaining is not None:
                raise PipelineError("owned pointer could not be removed")
            return

        self._store._hit("rollback.before_restore")
        if not self._owned_pointer_is_current(
            parent_fd,
            leaf,
            identity=owned_identity,
        ):
            raise PipelineError("current pointer changed before restore")
        temporary_name: str | None = None
        temporary_fd: int | None = None
        try:
            temporary_name, temporary_fd = self._store._temporary_file(
                parent_fd,
                mode=_LOCK_MODE,
            )
            _write_all(temporary_fd, before.raw)
            os.fchmod(temporary_fd, _FILE_MODE)
            os.fsync(temporary_fd)
            if not self._owned_pointer_is_current(
                parent_fd,
                leaf,
                identity=owned_identity,
            ):
                raise PipelineError("current pointer changed during restore")
            os.replace(
                temporary_name,
                leaf,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            temporary_name = None
            self._store._hit("rollback.after_restore")
            os.fsync(parent_fd)
            self._store._hit("rollback.after_directory_fsync")
            restored, _snapshot = self._store._read_pointer_at(
                before.reference,
                parent_fd,
                leaf,
                missing_ok=False,
            )
            if restored is None or restored.reference != before.reference:
                raise PipelineError("campaign pointer was not restored exactly")
        finally:
            if temporary_fd is not None:
                os.close(temporary_fd)
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass

    def commit(
        self,
        *,
        pre_commit: StageCallback,
        post_commit: StageCallback,
    ) -> CommitResult:
        if self._used:
            raise PipelineError("pointer transaction is single-use")
        if not callable(pre_commit) or not callable(post_commit):
            raise PipelineError("pointer transaction validators must be callable")
        self._used = True

        with self._store._pointer_lock(self._campaign_id) as verify_lock:
            before_snapshot = self._store._read_pointer_snapshot(
                self._successor.path
            )
            before = self._require_expected(before_snapshot)
            self._hit_while_locked("pointer.after_cas", verify_lock)

            self._verify_required_objects()
            self._hit_while_locked("pointer.after_required_verify", verify_lock)

            view = TransactionView(
                self._store,
                self._campaign_id,
                self._expected,
                self._successor,
            )
            pre_value = pre_commit(view)
            verify_lock()
            pre_receipt = self._require_stage_receipt(
                pre_value,
                stage="pre-commit",
            )
            after_pre_snapshot = self._store._read_pointer_snapshot(
                self._successor.path
            )
            if not self._same_snapshot(before_snapshot, after_pre_snapshot):
                raise PipelineError(
                    "campaign pointer changed during pre-commit validation"
                )
            self._verify_required_objects()
            self._hit_while_locked("pointer.after_pre_commit", verify_lock)

            parent_fd, leaf = self._store._open_parent(
                self._successor.path,
                create=True,
                label="campaign pointer",
            )
            assert parent_fd is not None
            temporary_name: str | None = None
            temporary_fd: int | None = None
            pointer_published = False
            owned_identity: tuple[int, int] | None = None
            try:
                final_before_snapshot = self._store._read_file_at(
                    parent_fd,
                    leaf,
                    missing_ok=True,
                    mode=_FILE_MODE,
                    label="campaign pointer",
                )
                self._require_expected(final_before_snapshot)
                if not self._same_snapshot(before_snapshot, final_before_snapshot):
                    raise PipelineError("campaign pointer changed before replacement")

                temporary_name, temporary_fd = self._store._temporary_file(
                    parent_fd,
                    mode=_LOCK_MODE,
                )
                self._hit_while_locked("pointer.after_temp_create", verify_lock)
                _write_all(temporary_fd, self._successor_raw)
                os.fchmod(temporary_fd, _FILE_MODE)
                os.fsync(temporary_fd)
                temporary_stat = os.fstat(temporary_fd)
                owned_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
                self._hit_while_locked("pointer.after_file_fsync", verify_lock)
                self._hit_while_locked("pointer.before_replace", verify_lock)
                self._verify_required_objects()

                immediate_before_snapshot = self._store._read_file_at(
                    parent_fd,
                    leaf,
                    missing_ok=True,
                    mode=_FILE_MODE,
                    label="campaign pointer",
                )
                self._require_expected(immediate_before_snapshot)
                if not self._same_snapshot(before_snapshot, immediate_before_snapshot):
                    raise PipelineError(
                        "campaign pointer changed at replacement boundary"
                    )

                # This is the final cooperative check adjacent to publication.
                self._verify_required_objects()
                verify_lock()

                if before is None:
                    try:
                        os.link(
                            temporary_name,
                            leaf,
                            src_dir_fd=parent_fd,
                            dst_dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                    except FileExistsError as exc:
                        raise PipelineError(
                            "campaign pointer compare-and-swap lost the create race"
                        ) from exc
                    pointer_published = True
                    os.close(temporary_fd)
                    temporary_fd = None
                    os.unlink(temporary_name, dir_fd=parent_fd)
                    temporary_name = None
                else:
                    os.replace(
                        temporary_name,
                        leaf,
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                    )
                    pointer_published = True
                    temporary_name = None
                    os.close(temporary_fd)
                    temporary_fd = None
                # From here onward, every failure is inside rollback scope.
                verify_lock()
                self._hit_while_locked("pointer.after_replace", verify_lock)
                os.fsync(parent_fd)
                self._hit_while_locked(
                    "pointer.after_directory_fsync",
                    verify_lock,
                )

                after_before_post, after_before_post_snapshot = (
                    self._store._read_pointer_at(
                        self._successor,
                        parent_fd,
                        leaf,
                        missing_ok=False,
                    )
                )
                if (
                    after_before_post is None
                    or after_before_post.raw != self._successor_raw
                    or after_before_post_snapshot is None
                    or after_before_post_snapshot.identity != owned_identity
                ):
                    raise PipelineError("campaign successor pointer is not exact")
                post_value = post_commit(view)
                verify_lock()
                post_receipt = self._require_stage_receipt(
                    post_value,
                    stage="post-commit",
                )
                self._verify_required_objects()
                self._hit_while_locked("pointer.after_post_commit", verify_lock)
                after, after_snapshot = self._store._read_pointer_at(
                    self._successor,
                    parent_fd,
                    leaf,
                    missing_ok=False,
                )
                if (
                    after is None
                    or after.raw != self._successor_raw
                    or after_snapshot is None
                    or after_snapshot.identity != owned_identity
                ):
                    raise PipelineError(
                        "campaign pointer changed after post-commit validation"
                    )
                verify_lock()
                return CommitResult(
                    before=before,
                    after=after,
                    pre_commit=pre_receipt,
                    post_commit=post_receipt,
                )
            except BaseException as exc:
                if pointer_published and owned_identity is not None:
                    try:
                        # Lock loss may be the triggering failure.  Rollback is
                        # therefore gated by pointer ownership, not by a lock
                        # path that is already known to be foreign.
                        self._rollback_pointer(
                            parent_fd=parent_fd,
                            leaf=leaf,
                            before=before,
                            owned_identity=owned_identity,
                        )
                    except BaseException as rollback_exc:
                        raise PipelineError(
                            "campaign pointer transaction rollback incomplete: "
                            f"{rollback_exc}"
                        ) from exc
                raise
            finally:
                if temporary_fd is not None:
                    os.close(temporary_fd)
                if temporary_name is not None:
                    try:
                        os.unlink(temporary_name, dir_fd=parent_fd)
                    except FileNotFoundError:
                        pass
                os.close(parent_fd)


__all__ = [
    "FAULT_SEAMS",
    "CampaignStore",
    "CommitResult",
    "FaultHook",
    "PointerState",
    "PointerTransaction",
    "StoreResult",
    "TransactionView",
    "VerificationView",
    "canonical_object_reference",
]
