"""Deterministic provenance identity for the pipeline's Python sources.

Repository source capture is deliberately descriptor anchored. A capture
keeps every opened file and directory alive until the final path-chain check,
so the returned raw bytes and metadata all belong to one stable repository
window. The generic primitive is also used by strict campaign collectors that
must bind non-Python repository authorities in the same window.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from .errors import PipelineError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_LAUNCHER = REPOSITORY_ROOT / "scripts" / "core_pipeline.py"
PIPELINE_PACKAGE_ROOT = REPOSITORY_ROOT / "scripts" / "core_pipeline_lib"
PIPELINE_LAUNCHER_RELATIVE = "scripts/core_pipeline.py"
PIPELINE_PACKAGE_PREFIX = "scripts/core_pipeline_lib/"
PIPELINE_PACKAGE_ROOT_RELATIVE = PIPELINE_PACKAGE_PREFIX.removesuffix("/")
PIPELINE_PACKAGE_INIT_RELATIVE = f"{PIPELINE_PACKAGE_PREFIX}__init__.py"
PIPELINE_LAUNCHER_MODE = 0o755
REPOSITORY_SOURCE_MODE = 0o644
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_READ_SIZE = 1024 * 1024
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _relative_parts(value: object, *, label: str) -> tuple[str, ...]:
    if type(value) is not str or not value or "\x00" in value or "\\" in value:
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return path.parts


def _stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _require_source_file_stat(
    value: os.stat_result,
    *,
    mode: int,
    label: str,
) -> None:
    if not stat.S_ISREG(value.st_mode):
        raise PipelineError(f"{label} must be a regular file")
    if stat.S_IMODE(value.st_mode) != mode:
        raise PipelineError(f"{label} mode must be {mode:04o}")
    if value.st_nlink != 1:
        raise PipelineError(f"{label} link count must be one")


@dataclass(frozen=True, slots=True, kw_only=True)
class RepositorySourceFileSet:
    """One descriptor-enumerated repository file set."""

    root: str
    suffixes: tuple[str, ...]
    recursive: bool
    mode: int = REPOSITORY_SOURCE_MODE
    label: str = "repository source file set"

    def __post_init__(self) -> None:
        _relative_parts(self.root, label=f"{self.label} root")
        if (
            type(self.suffixes) is not tuple
            or not self.suffixes
            or any(
                type(value) is not str
                or not value.startswith(".")
                or "/" in value
                for value in self.suffixes
            )
            or self.suffixes != tuple(sorted(self.suffixes))
            or len(self.suffixes) != len(set(self.suffixes))
        ):
            raise PipelineError(f"{self.label} suffixes are invalid")
        if type(self.recursive) is not bool:
            raise PipelineError(f"{self.label} recursion policy is invalid")
        if type(self.mode) is not int or not 0 <= self.mode <= 0o777:
            raise PipelineError(f"{self.label} mode is invalid")
        if type(self.label) is not str or not self.label:
            raise PipelineError("repository source file-set label is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class RepositorySourceMember:
    """Exact bytes and stable filesystem identity for one captured member."""

    path: str
    raw: bytes
    mode: int
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int

    def __post_init__(self) -> None:
        _relative_parts(self.path, label="repository source member path")
        if type(self.raw) is not bytes:
            raise PipelineError("repository source member bytes are invalid")
        for value, label in (
            (self.mode, "mode"),
            (self.device, "device"),
            (self.inode, "inode"),
            (self.size, "size"),
            (self.mtime_ns, "mtime"),
            (self.ctime_ns, "ctime"),
        ):
            if type(value) is not int or value < 0:
                raise PipelineError(f"repository source member {label} is invalid")
        if self.mode > 0o777 or self.size != len(self.raw):
            raise PipelineError("repository source member metadata is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class _RepositoryDirectoryState:
    path: str
    identity: tuple[int, ...]
    entries: tuple[str, ...] | None


@dataclass(frozen=True, slots=True, kw_only=True)
class RepositorySourceCapture:
    """One stable descriptor-anchored repository source window."""

    members: tuple[RepositorySourceMember, ...]
    directories: tuple[_RepositoryDirectoryState, ...]

    def __post_init__(self) -> None:
        if type(self.members) is not tuple or any(
            type(item) is not RepositorySourceMember for item in self.members
        ):
            raise PipelineError("repository source members are invalid")
        paths = tuple(item.path for item in self.members)
        if not paths or paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise PipelineError("repository source members must be sorted and unique")
        if type(self.directories) is not tuple or any(
            type(item) is not _RepositoryDirectoryState for item in self.directories
        ):
            raise PipelineError("repository source directories are invalid")
        directory_paths = tuple(item.path for item in self.directories)
        if (
            not directory_paths
            or directory_paths != tuple(sorted(directory_paths))
            or len(directory_paths) != len(set(directory_paths))
        ):
            raise PipelineError("repository source directories must be sorted and unique")


@dataclass(slots=True)
class _OpenDirectory:
    path: str
    descriptor: int
    before: os.stat_result
    parent_path: str | None
    leaf: str | None
    entries: tuple[str, ...] | None = None


@dataclass(slots=True)
class _OpenFile:
    member: RepositorySourceMember
    descriptor: int
    parent_path: str
    leaf: str
    identity: tuple[int, ...]
    label: str


class _RepositoryCaptureSession:
    """Hold every descriptor until one final live-path verification."""

    def __init__(self, repository_root: Path) -> None:
        if _O_DIRECTORY == 0 or _O_NOFOLLOW == 0:
            raise PipelineError(
                "repository source capture requires O_DIRECTORY and O_NOFOLLOW"
            )
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            raise PipelineError("repository source root must be an absolute Path")
        self._root = repository_root.absolute()
        try:
            root_lstat = os.stat(self._root, follow_symlinks=False)
        except OSError as exc:
            raise PipelineError(f"repository source root does not exist: {exc}") from exc
        if not stat.S_ISDIR(root_lstat.st_mode):
            raise PipelineError("repository source root must be a real directory")
        try:
            root_fd = os.open(
                self._root,
                os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC,
            )
        except OSError as exc:
            raise PipelineError(
                f"cannot open repository source root without following links: {exc}"
            ) from exc
        root_stat = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or _stat_identity(root_stat) != _stat_identity(root_lstat)
        ):
            os.close(root_fd)
            raise PipelineError("repository source root identity changed while opened")
        self._directories: dict[str, _OpenDirectory] = {
            ".": _OpenDirectory(
                path=".",
                descriptor=root_fd,
                before=root_stat,
                parent_path=None,
                leaf=None,
            )
        }
        self._files: list[_OpenFile] = []

    def close(self) -> None:
        for opened in self._files:
            try:
                os.close(opened.descriptor)
            except OSError:
                pass
        self._files.clear()
        for opened in reversed(tuple(self._directories.values())):
            try:
                os.close(opened.descriptor)
            except OSError:
                pass
        self._directories.clear()

    def _open_directory(self, relative: str, *, label: str) -> _OpenDirectory:
        parts = _relative_parts(relative, label=f"{label} path")
        parent_path = "."
        for index, part in enumerate(parts):
            current_path = PurePosixPath(*parts[: index + 1]).as_posix()
            existing = self._directories.get(current_path)
            if existing is not None:
                parent_path = current_path
                continue
            parent = self._directories[parent_path]
            try:
                descriptor = os.open(
                    part,
                    os.O_RDONLY | _O_DIRECTORY | _O_NOFOLLOW | _O_CLOEXEC,
                    dir_fd=parent.descriptor,
                )
            except FileNotFoundError:
                raise PipelineError(f"{label} does not exist") from None
            except OSError as exc:
                raise PipelineError(
                    f"{label} must not traverse a symlink or non-directory: {exc}"
                ) from exc
            opened_stat = os.fstat(descriptor)
            try:
                path_stat = os.stat(
                    part,
                    dir_fd=parent.descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                os.close(descriptor)
                raise PipelineError(f"{label} changed while it was opened: {exc}") from exc
            if (
                not stat.S_ISDIR(opened_stat.st_mode)
                or _stat_identity(opened_stat) != _stat_identity(path_stat)
            ):
                os.close(descriptor)
                raise PipelineError(f"{label} changed while it was opened")
            self._directories[current_path] = _OpenDirectory(
                path=current_path,
                descriptor=descriptor,
                before=opened_stat,
                parent_path=parent_path,
                leaf=part,
            )
            parent_path = current_path
        return self._directories[relative]

    def enumerate_file_set(
        self,
        source_set: RepositorySourceFileSet,
    ) -> dict[str, int]:
        discovered: dict[str, int] = {}

        def walk(relative: str) -> None:
            directory = self._open_directory(relative, label=source_set.label)
            try:
                names = tuple(sorted(os.listdir(directory.descriptor)))
            except OSError as exc:
                raise PipelineError(f"cannot enumerate {source_set.label}: {exc}") from exc
            if any(
                type(name) is not str
                or not name
                or name in {".", ".."}
                or "/" in name
                or "\x00" in name
                for name in names
            ):
                raise PipelineError(f"{source_set.label} contains an invalid entry")
            if directory.entries is not None and directory.entries != names:
                raise PipelineError(f"{source_set.label} changed during enumeration")
            directory.entries = names
            for name in names:
                path = f"{relative}/{name}"
                try:
                    entry_stat = os.stat(
                        name,
                        dir_fd=directory.descriptor,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise PipelineError(
                        f"cannot inspect {source_set.label}: {exc}"
                    ) from exc
                matches = name.endswith(source_set.suffixes)
                if stat.S_ISLNK(entry_stat.st_mode) and (
                    source_set.recursive or matches
                ):
                    raise PipelineError(
                        f"{source_set.label} must not traverse a symlink"
                    )
                if stat.S_ISDIR(entry_stat.st_mode):
                    if source_set.recursive:
                        walk(path)
                    continue
                if not matches:
                    continue
                if not stat.S_ISREG(entry_stat.st_mode):
                    raise PipelineError(
                        f"{source_set.label} must be a regular file: {path}"
                    )
                discovered[path] = source_set.mode

        walk(source_set.root)
        return discovered

    def read_file(self, relative: str, *, mode: int) -> RepositorySourceMember:
        parts = _relative_parts(relative, label="repository source member path")
        parent_path = (
            PurePosixPath(*parts[:-1]).as_posix() if len(parts) > 1 else "."
        )
        parent = (
            self._directories[parent_path]
            if parent_path in self._directories
            else self._open_directory(parent_path, label="repository source parent")
        )
        leaf = parts[-1]
        label = f"repository source member {relative}"
        try:
            descriptor = os.open(
                leaf,
                os.O_RDONLY | _O_NOFOLLOW | _O_CLOEXEC | _O_NONBLOCK,
                dir_fd=parent.descriptor,
            )
        except FileNotFoundError:
            raise PipelineError(f"{label} does not exist") from None
        except OSError as exc:
            raise PipelineError(
                f"cannot open {label} without following links: {exc}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            _require_source_file_stat(before, mode=mode, label=label)
            blocks: list[bytes] = []
            while True:
                block = os.read(descriptor, _READ_SIZE)
                if not block:
                    break
                blocks.append(block)
            raw = b"".join(blocks)
            after = os.fstat(descriptor)
            identity = _stat_identity(before)
            if identity != _stat_identity(after) or len(raw) != before.st_size:
                raise PipelineError(f"{label} changed while it was read")
            try:
                path_stat = os.stat(
                    leaf,
                    dir_fd=parent.descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise PipelineError(f"{label} changed after it was read: {exc}") from exc
            _require_source_file_stat(path_stat, mode=mode, label=label)
            if _stat_identity(path_stat) != identity:
                raise PipelineError(f"{label} changed after it was read")
            member = RepositorySourceMember(
                path=relative,
                raw=raw,
                mode=stat.S_IMODE(before.st_mode),
                device=before.st_dev,
                inode=before.st_ino,
                size=before.st_size,
                mtime_ns=before.st_mtime_ns,
                ctime_ns=before.st_ctime_ns,
            )
            self._files.append(
                _OpenFile(
                    member=member,
                    descriptor=descriptor,
                    parent_path=parent_path,
                    leaf=leaf,
                    identity=identity,
                    label=label,
                )
            )
            return member
        except BaseException:
            os.close(descriptor)
            raise

    def _verify_files(self) -> None:
        for opened in self._files:
            before = os.fstat(opened.descriptor)
            if _stat_identity(before) != opened.identity:
                raise PipelineError(f"{opened.label} changed during capture")
            try:
                os.lseek(opened.descriptor, 0, os.SEEK_SET)
                blocks: list[bytes] = []
                while True:
                    block = os.read(opened.descriptor, _READ_SIZE)
                    if not block:
                        break
                    blocks.append(block)
            except OSError as exc:
                raise PipelineError(
                    f"{opened.label} cannot be reverified: {exc}"
                ) from exc
            after = os.fstat(opened.descriptor)
            if (
                _stat_identity(after) != opened.identity
                or b"".join(blocks) != opened.member.raw
            ):
                raise PipelineError(f"{opened.label} changed during capture")
            parent = self._directories[opened.parent_path]
            try:
                path_stat = os.stat(
                    opened.leaf,
                    dir_fd=parent.descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise PipelineError(
                    f"{opened.label} changed during capture: {exc}"
                ) from exc
            _require_source_file_stat(
                path_stat,
                mode=opened.member.mode,
                label=opened.label,
            )
            if _stat_identity(path_stat) != opened.identity:
                raise PipelineError(f"{opened.label} changed during capture")

    def finish(self, members: tuple[RepositorySourceMember, ...]) -> RepositorySourceCapture:
        self._verify_files()
        directory_states: list[_RepositoryDirectoryState] = []
        verification_order = sorted(
            self._directories,
            key=lambda value: (-len(PurePosixPath(value).parts), value),
        )
        for path in verification_order:
            opened = self._directories[path]
            current = os.fstat(opened.descriptor)
            before_identity = _stat_identity(opened.before)
            if _stat_identity(current) != before_identity:
                raise PipelineError(
                    f"repository source directory changed during capture: {path}"
                )
            if opened.entries is not None:
                try:
                    current_entries = tuple(sorted(os.listdir(opened.descriptor)))
                except OSError as exc:
                    raise PipelineError(
                        f"cannot re-enumerate repository source directory {path}: {exc}"
                    ) from exc
                if current_entries != opened.entries:
                    raise PipelineError(
                        f"repository source directory changed during capture: {path}"
                    )
            if opened.parent_path is None:
                try:
                    path_stat = os.stat(self._root, follow_symlinks=False)
                except OSError as exc:
                    raise PipelineError(
                        f"repository source root changed during capture: {exc}"
                    ) from exc
            else:
                parent = self._directories[opened.parent_path]
                assert opened.leaf is not None
                try:
                    path_stat = os.stat(
                        opened.leaf,
                        dir_fd=parent.descriptor,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise PipelineError(
                        f"repository source directory path changed during capture: {path}"
                    ) from exc
            if (
                not stat.S_ISDIR(path_stat.st_mode)
                or _stat_identity(path_stat) != before_identity
            ):
                raise PipelineError(
                    f"repository source directory path changed during capture: {path}"
                )
            directory_states.append(
                _RepositoryDirectoryState(
                    path=path,
                    identity=before_identity,
                    entries=opened.entries,
                )
            )
        # Bracket the directory/path-chain pass. In-place source mutation does
        # not alter a parent directory, so every file descriptor, its bytes,
        # and its path must still match the identity recorded by the read.
        self._verify_files()
        return RepositorySourceCapture(
            members=members,
            directories=tuple(sorted(directory_states, key=lambda item: item.path)),
        )


def capture_repository_sources(
    *,
    repository_root: Path,
    exact_file_modes: Mapping[str, int],
    file_sets: tuple[RepositorySourceFileSet, ...] = (),
) -> RepositorySourceCapture:
    """Capture exact files and descriptor-enumerated sets in one stable window."""

    if not isinstance(exact_file_modes, Mapping):
        raise PipelineError("repository exact source paths are invalid")
    if type(file_sets) is not tuple or any(
        type(value) is not RepositorySourceFileSet for value in file_sets
    ):
        raise PipelineError("repository source file sets are invalid")
    expected: dict[str, int] = {}
    for path, mode in exact_file_modes.items():
        _relative_parts(path, label="repository exact source path")
        if type(mode) is not int or not 0 <= mode <= 0o777:
            raise PipelineError("repository exact source mode is invalid")
        expected[path] = mode

    session = _RepositoryCaptureSession(repository_root)
    try:
        for source_set in file_sets:
            for path, mode in session.enumerate_file_set(source_set).items():
                prior = expected.get(path)
                if prior is not None and prior != mode:
                    raise PipelineError(
                        f"repository source mode policy conflicts for {path}"
                    )
                expected[path] = mode
        if not expected:
            raise PipelineError("repository source capture is empty")
        members = tuple(
            session.read_file(path, mode=expected[path]) for path in sorted(expected)
        )
        return session.finish(members)
    finally:
        session.close()


def pipeline_bundle_content_sha256(files: Mapping[str, str]) -> str:
    material = {
        "schema_version": 1,
        "files": dict(files),
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

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"{label} does not exist") from exc
    try:
        resolved.relative_to(repository_root)
    except ValueError as exc:
        raise PipelineError(f"{label} is outside the pipeline repository") from exc
    return relative.as_posix()


def pipeline_source_capture() -> RepositorySourceCapture:
    """Capture the launcher and every package Python module securely."""

    repository_root = _resolved_repository_root()
    launcher_relative = _contained_relative_path(
        PIPELINE_LAUNCHER,
        repository_root,
        "pipeline launcher",
    )
    if launcher_relative != PIPELINE_LAUNCHER_RELATIVE:
        raise PipelineError("pipeline launcher is not at its canonical path")
    package_relative = _contained_relative_path(
        PIPELINE_PACKAGE_ROOT,
        repository_root,
        "pipeline package root",
    )
    if package_relative != PIPELINE_PACKAGE_ROOT_RELATIVE:
        raise PipelineError("pipeline package root is not at its canonical path")
    capture = capture_repository_sources(
        repository_root=repository_root,
        exact_file_modes={PIPELINE_LAUNCHER_RELATIVE: PIPELINE_LAUNCHER_MODE},
        file_sets=(
            RepositorySourceFileSet(
                root=PIPELINE_PACKAGE_ROOT_RELATIVE,
                suffixes=(".py",),
                recursive=True,
                mode=REPOSITORY_SOURCE_MODE,
                label="pipeline package entry",
            ),
        ),
    )
    paths = tuple(member.path for member in capture.members)
    if len(paths) < 2:
        raise PipelineError("pipeline package contains no Python sources")
    if PIPELINE_PACKAGE_INIT_RELATIVE not in paths:
        raise PipelineError("pipeline package is missing __init__.py")
    return capture


def pipeline_source_bundle_from_members(
    members: tuple[RepositorySourceMember, ...],
) -> dict[str, object]:
    """Derive the existing semantic bundle from already-captured raw bytes."""

    if type(members) is not tuple or any(
        type(member) is not RepositorySourceMember for member in members
    ):
        raise PipelineError("pipeline source members are invalid")
    selected = tuple(
        member
        for member in members
        if member.path == PIPELINE_LAUNCHER_RELATIVE
        or (
            member.path.startswith(PIPELINE_PACKAGE_PREFIX)
            and member.path.endswith(".py")
        )
    )
    paths = tuple(member.path for member in selected)
    if (
        not selected
        or paths != tuple(sorted(paths))
        or len(paths) != len(set(paths))
        or PIPELINE_LAUNCHER_RELATIVE not in paths
        or PIPELINE_PACKAGE_INIT_RELATIVE not in paths
    ):
        raise PipelineError("pipeline source member inventory is invalid")
    files = {member.path: _sha256_bytes(member.raw) for member in selected}
    bundle: dict[str, object] = {
        "schema_version": 1,
        "files": files,
    }
    bundle["content_sha256"] = pipeline_bundle_content_sha256(files)
    return bundle


def pipeline_source_bundle() -> dict[str, object]:
    return pipeline_source_bundle_from_members(pipeline_source_capture().members)


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


__all__ = [
    "PIPELINE_LAUNCHER_MODE",
    "PIPELINE_LAUNCHER_RELATIVE",
    "PIPELINE_PACKAGE_INIT_RELATIVE",
    "PIPELINE_PACKAGE_PREFIX",
    "PIPELINE_PACKAGE_ROOT_RELATIVE",
    "REPOSITORY_ROOT",
    "REPOSITORY_SOURCE_MODE",
    "RepositorySourceCapture",
    "RepositorySourceFileSet",
    "RepositorySourceMember",
    "capture_repository_sources",
    "pipeline_bundle_content_sha256",
    "pipeline_source_bundle",
    "pipeline_source_bundle_from_members",
    "pipeline_source_bundle_is_well_formed",
    "pipeline_source_capture",
]
