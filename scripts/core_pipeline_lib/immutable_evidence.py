"""Immutable evidence snapshots, identities, and local CAS primitives."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Protocol

from .errors import PipelineError
from .foundation import (
    decode_json_object,
    require_manifest_reference_path,
    safe_child,
    sha256_bytes,
    sha256_file,
)


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

HashBytes = Callable[[bytes], str]
HashFile = Callable[[Path], str]
ManifestReferencePath = Callable[[dict, Path, str, Path], Path]


class VerifiedBytesCache(Protocol):
    """Structural cache contract used by one validation walk."""

    verified_bytes: dict[tuple[str, str], bytes]


def verified_file_bytes(
    path: Path,
    expected_sha256: str,
    label: str,
    validation_context: VerifiedBytesCache | None = None,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> bytes:
    """Read and bind one file once for all semantic use in a validation walk."""

    if not isinstance(expected_sha256, str) or not SHA256_RE.fullmatch(
        expected_sha256
    ):
        raise PipelineError(f"{label} expected digest is invalid")
    cache_key = (str(path.resolve()), expected_sha256)
    if validation_context is not None and cache_key in validation_context.verified_bytes:
        cached = validation_context.verified_bytes[cache_key]
        if hash_bytes(cached) != expected_sha256:
            raise PipelineError(f"{label} cached digest drift")
        return cached
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PipelineError(f"{label} is not readable: {exc}") from exc
    if hash_bytes(raw) != expected_sha256:
        raise PipelineError(f"{label} digest drift")
    if validation_context is not None:
        validation_context.verified_bytes[cache_key] = raw
    return raw


def verified_json_object(
    path: Path,
    expected_sha256: str,
    label: str,
    validation_context: VerifiedBytesCache | None = None,
    *,
    read_verified: Callable[[Path, str, str, VerifiedBytesCache | None], bytes]
    | None = None,
) -> dict:
    """Decode a strict JSON object from an already digest-bound snapshot."""

    reader = read_verified or verified_file_bytes
    raw = reader(path, expected_sha256, label, validation_context)
    return decode_json_object(raw, label)


def snapshot_json_file(
    path: Path,
    label: str,
    validation_context: VerifiedBytesCache | None = None,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> tuple[dict, str]:
    """Capture one JSON object and its digest for a complete validation walk."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PipelineError(f"{label} is not readable: {exc}") from exc
    document = decode_json_object(raw, label)
    digest = hash_bytes(raw)
    if validation_context is not None:
        validation_context.verified_bytes[(str(path.resolve()), digest)] = raw
    return document, digest


def verified_utf8_text(
    path: Path,
    expected_sha256: str,
    label: str,
    validation_context: VerifiedBytesCache | None = None,
    *,
    read_verified: Callable[[Path, str, str, VerifiedBytesCache | None], bytes]
    | None = None,
) -> str:
    """Decode UTF-8 text from an already digest-bound snapshot."""

    reader = read_verified or verified_file_bytes
    raw = reader(path, expected_sha256, label, validation_context)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PipelineError(f"{label} is not readable UTF-8 text: {exc}") from exc


def lexical_repository_relative_path(
    path: Path,
    repository_root: Path,
    label: str,
) -> str:
    """Return an unresolved repository-relative path for later policy checks."""

    try:
        return path.absolute().relative_to(repository_root).as_posix()
    except ValueError as exc:
        raise PipelineError(f"{label} must be inside the repository") from exc


def toolchain_lock_content_sha256(
    document: dict,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "lock_id": document.get("lock_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "toolchains": document.get("toolchains"),
    }
    return _canonical_sha256(material, hash_bytes)


def golden_content_sha256(
    document: dict,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    schema_version = document.get("schema_version")
    if schema_version == 2:
        material = {
            "schema_version": schema_version,
            "core_id": document.get("core_id"),
            "pin_id": document.get("pin_id"),
            "local_only": document.get("local_only"),
            "publication": document.get("publication"),
            "baseline": document.get("baseline"),
            "cores": document.get("cores"),
            "build_goldens": document.get("build_goldens"),
        }
    else:
        # Preserve the exact schema-v1 digest projection for immutable history.
        material = {
            "schema_version": schema_version,
            "baseline": document.get("baseline"),
            "cores": document.get("cores"),
            "build_goldens": document.get("build_goldens"),
        }
    return _canonical_sha256(material, hash_bytes)


def e2e_content_sha256(
    document: dict,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "run_id": document.get("run_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "result": document.get("result"),
        "workflow_audit": document.get("workflow_audit"),
        "builds": document.get("builds"),
        "packages": document.get("packages"),
    }
    if document.get("schema_version") == 2:
        material["runner"] = document.get("runner")
    if "core_group" in document:
        material["core_group"] = document.get("core_group")
    if "tuning_candidate" in document:
        material["tuning_candidate"] = document.get("tuning_candidate")
    return _canonical_sha256(material, hash_bytes)


def selection_content_sha256(
    selection: dict,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    targets = {}
    for arch, target in sorted(selection.get("targets", {}).items()):
        targets[arch] = {
            "artifact": {
                "sha256": target.get("artifact", {}).get("sha256"),
                "size": target.get("artifact", {}).get("size"),
            },
            "build_record_sha256": target.get("build_record_sha256"),
            "provenance_identity_sha256": target.get(
                "provenance_identity_sha256"
            ),
        }
    material = {
        "tier": selection.get("tier"),
        "validation_scope": selection.get("validation_scope"),
        "e2e": selection.get("e2e"),
        "package": {
            "name": selection.get("package", {}).get("name"),
            "sha256": selection.get("package", {}).get("sha256"),
            "size": selection.get("package", {}).get("size"),
        },
        "metadata": {
            "sha256": selection.get("metadata", {}).get("sha256"),
            "size": selection.get("metadata", {}).get("size"),
        },
        "targets": targets,
    }
    if "chipset_tuning" in selection:
        material["chipset_tuning"] = selection.get("chipset_tuning")
    if "reproduction" in selection:
        material["reproduction"] = selection.get("reproduction")
    if "source_candidate" in selection:
        material["source_candidate"] = selection.get("source_candidate")
    if "output_reproduction" in selection:
        material["output_reproduction"] = selection.get("output_reproduction")
    if "host_reproduction" in selection:
        material["host_reproduction"] = selection.get("host_reproduction")
    return _canonical_sha256(material, hash_bytes)


def host_reproduction_content_sha256(
    proof: Mapping[str, object],
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    """Hash one immutable dual-host proof without its self digest."""

    material = {
        "schema_version": proof.get("schema_version"),
        "validation_scope": proof.get("validation_scope"),
        "selected": proof.get("selected"),
        "reproduction": proof.get("reproduction"),
        "equivalent_builds": proof.get("equivalent_builds"),
        "equivalent_outputs": proof.get("equivalent_outputs"),
    }
    return _canonical_sha256(material, hash_bytes)


def pin_set_content_sha256(
    document: dict,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "pin_id": document.get("pin_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "scope": document.get("scope"),
        "parent": document.get("parent"),
        "sources": document.get("sources"),
        "selection_policy": document.get("selection_policy"),
        "cores": document.get("cores"),
        "summary": document.get("summary"),
    }
    return _canonical_sha256(material, hash_bytes)


def release_content_sha256(
    document: dict,
    *,
    hash_bytes: HashBytes = sha256_bytes,
) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "release_id": document.get("release_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "pin": document.get("pin"),
        "assets": document.get("assets"),
    }
    return _canonical_sha256(material, hash_bytes)


def store_bytes(
    store_root: Path,
    namespace: str,
    content: bytes,
    *,
    hash_bytes: HashBytes = sha256_bytes,
    hash_file: HashFile = sha256_file,
    reference_path: ManifestReferencePath = require_manifest_reference_path,
) -> tuple[Path, str]:
    """Create or reuse one immutable local content-addressed store entry."""

    digest = hash_bytes(content)
    if not namespace or "/" in namespace or namespace in {".", ".."}:
        raise PipelineError("content-addressed namespace is invalid")
    store_root = store_root.absolute()
    if store_root.is_symlink():
        raise PipelineError("content-addressed store root must not be a symlink")
    relative = Path(namespace) / "sha256" / digest[:2] / digest
    destination = reference_path(
        {"path": relative.as_posix()},
        store_root,
        "content-addressed store destination",
        store_root,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = reference_path(
        {"path": relative.as_posix()},
        store_root,
        "content-addressed store destination",
        store_root,
    )
    if destination.exists():
        if not destination.is_file() or hash_file(destination) != digest:
            raise PipelineError(f"content-addressed store collision at {destination}")
        return destination, digest
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=destination.parent, delete=False
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fchmod(handle.fileno(), 0o644)
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        try:
            os.link(temporary, destination)
            directory_fd = os.open(
                destination.parent,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except FileExistsError:
            destination = reference_path(
                {"path": relative.as_posix()},
                store_root,
                "content-addressed store destination",
                store_root,
            )
            if not destination.is_file() or hash_file(destination) != digest:
                raise PipelineError(
                    f"content-addressed store collision at {destination}"
                )
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination, digest


def store_file(
    store_root: Path,
    namespace: str,
    source: Path,
    *,
    store: Callable[[Path, str, bytes], tuple[Path, str]] | None = None,
) -> tuple[Path, str]:
    """Store the exact bytes read from one source file."""

    writer = store or store_bytes
    return writer(store_root, namespace, source.read_bytes())


def canonical_store_path(store_root: Path, namespace: str, digest: str) -> Path:
    if not namespace or "/" in namespace or namespace in {".", ".."}:
        raise PipelineError("content-addressed namespace is invalid")
    if not SHA256_RE.fullmatch(digest):
        raise PipelineError("content-addressed digest is invalid")
    return store_root / namespace / "sha256" / digest[:2] / digest


def require_canonical_store_entry(
    entry: dict,
    namespace: str,
    label: str,
    *,
    repository_root: Path,
    store_root: Path,
    canonical_path: Callable[[str, str], Path],
) -> Path:
    digest = entry.get("sha256", "")
    expected = canonical_path(namespace, digest)
    expected_relative = str(expected.relative_to(repository_root))
    if entry.get("path") != expected_relative:
        raise PipelineError(f"{label} does not use its canonical local-store path")
    unresolved = repository_root
    for part in Path(entry["path"]).parts:
        unresolved /= part
        if unresolved.is_symlink():
            raise PipelineError(f"{label} must not traverse a symlink")
    path = safe_child(repository_root, entry["path"], label)
    try:
        path.relative_to(store_root.resolve())
    except ValueError as exc:
        raise PipelineError(f"{label} escapes the local store") from exc
    return path


def _canonical_sha256(material: object, hash_bytes: HashBytes) -> str:
    return hash_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


__all__ = [
    "VerifiedBytesCache",
    "canonical_store_path",
    "e2e_content_sha256",
    "golden_content_sha256",
    "host_reproduction_content_sha256",
    "lexical_repository_relative_path",
    "pin_set_content_sha256",
    "release_content_sha256",
    "require_canonical_store_entry",
    "selection_content_sha256",
    "snapshot_json_file",
    "store_bytes",
    "store_file",
    "toolchain_lock_content_sha256",
    "verified_file_bytes",
    "verified_json_object",
    "verified_utf8_text",
]
