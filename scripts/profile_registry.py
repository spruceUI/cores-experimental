#!/usr/bin/env python3
"""Validate and report local-only source/profile registries.

This module is deliberately read-only.  It binds immutable build-golden evidence
to execution profiles without copying artifacts or claiming device runtime
eligibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
EXECUTION_PROFILES_PATH = ROOT / "manifests" / "execution-profiles.json"
RUNTIME_CONTRACTS_PATH = ROOT / "manifests" / "device-runtime-contracts.json"
CATALOG_PATH = ROOT / "manifests" / "core-builds.json"

SOURCE_LOCK_SCHEMA_REF = "../../../manifests/core-source-lock.schema.json"
SOURCE_SET_SCHEMA_REF = "../../manifests/core-source-set.schema.json"
EXECUTION_SCHEMA_REF = "execution-profiles.schema.json"
RUNTIME_SCHEMA_REF = "device-runtime-contracts.schema.json"

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
PROFILE_ID_RE = re.compile(r"^ra(?:32|64)-[a-z0-9-]+-v[0-9]+$")
CONTRACT_ID_RE = re.compile(r"^device-[a-z0-9-]+-v[0-9]+$")
LOCAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DEVICE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]+$")
CORE_SET_PATH_RE = re.compile(r"^pins/core-sets/[A-Za-z0-9._-]+\.json$")
SOURCE_SET_PATH_RE = re.compile(r"^pins/source-sets/[A-Za-z0-9._-]+\.json$")
FAMILY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]+-v[0-9]+$")
SUBMODULE_PATH_RE = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$"
)
VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)+$")
MAX_JSON_SIZE = 16 * 1024 * 1024

SPRUCE_SNAPSHOT = {
    "repository": "https://github.com/spruceUI/spruceOS.git",
    "commit": "0507598f7c322f0880eee6f147bd57709749a3b1",
    "tree": "569de730a1b317857a227da8b1282b0815af513a",
}

EXPECTED_PROFILE_IDS = {
    "ra32-a30-v1",
    "ra32-mini-v0",
    "ra32-universal-v0",
    "ra64-pixel2-v0",
    "ra64-universal-v1",
}
EXPECTED_CONTRACT_IDS = {
    "device-anbernic-h700-family-v0",
    "device-gkd-pixel2-v0",
    "device-magicx-zero28-v0",
    "device-miyoo-a30-v0",
    "device-miyoo-flip-v0",
    "device-miyoo-mini-family-v0",
    "device-trimui-a133p-family-v0",
    "device-trimui-smart-pro-s-v0",
}
PROFILE_BINDING = {"arm64": "ra64-universal-v1", "armhf": "ra32-a30-v1"}
PROFILE_MISSING_EVIDENCE = {
    "effective-runtime-provider-capture",
    "frontend-binary",
    "target-sysroot-capture",
    "target-toolchain-lock",
}
RUNTIME_MISSING_EVIDENCE = {
    "effective-runtime-provider-capture",
    "frontend-binary",
    "target-loader-capture",
    "target-playback-validation",
    "target-rootfs-load-validation",
}
EXPECTED_PROFILE_MISSING_EVIDENCE = {
    "ra32-a30-v1": [],
    "ra32-mini-v0": [
        "effective-runtime-provider-capture",
        "target-sysroot-capture",
        "target-toolchain-lock",
    ],
    "ra32-universal-v0": [
        "effective-runtime-provider-capture",
        "target-sysroot-capture",
        "target-toolchain-lock",
    ],
    "ra64-pixel2-v0": [
        "effective-runtime-provider-capture",
        "frontend-binary",
        "target-sysroot-capture",
        "target-toolchain-lock",
    ],
    "ra64-universal-v1": [],
}
EXPECTED_RUNTIME_CONTRACT_FACTS = {
    "device-miyoo-a30-v0": {
        "runtime_family_id": "miyoo-a30-v0",
        "devices": [
            {
                "device_id": "MIYOO_A30",
                "support_status": "official",
                "release_default": True,
            }
        ],
        "default_execution_profile": "ra32-a30-v1",
        "optional_execution_profiles": [],
        "candidate_build_flavors": [],
        "provider_observations": [
            {
                "role": "bundled-first-search-path-provider",
                "path": "/mnt/SDCARD/spruce/a30/lib/libstdc++.so.6",
                "sha256": "8014989515dc003f669e87abe4cbd89dcc4d68a458248ceee2528d73ed457a72",
                "max_versioned_symbols": {
                    "GLIBCXX": "3.4.32",
                    "CXXABI": "1.3.14",
                },
                "enforcing": False,
            }
        ],
        "missing_evidence": ["target-playback-validation", "target-rootfs-load-validation"],
    },
    "device-miyoo-flip-v0": {
        "runtime_family_id": "miyoo-flip-v0",
        "devices": [
            {
                "device_id": "MIYOO_FLIP",
                "support_status": "official",
                "release_default": True,
            }
        ],
        "default_execution_profile": "ra64-universal-v1",
        "optional_execution_profiles": ["ra32-universal-v0"],
        "candidate_build_flavors": [],
        "provider_observations": [
            {
                "role": "packaged-fallback-provider",
                "path": "/usr/lib/libstdc++.so.6.0.29",
                "sha256": "eb47b110eab5a94b4bd868f71b9ca6e13806156bac4ceb71ee381c07e281dbef",
                "max_versioned_symbols": {
                    "GLIBCXX": "3.4.32",
                    "CXXABI": "1.3.14",
                },
                "enforcing": False,
            }
        ],
        "missing_evidence": ["target-playback-validation", "target-rootfs-load-validation"],
    },
    "device-miyoo-mini-family-v0": {
        "runtime_family_id": "miyoo-mini-v0",
        "devices": [
            {
                "device_id": "MIYOO_MINI",
                "support_status": "official",
                "release_default": True,
            },
            {
                "device_id": "MIYOO_MINI_V4",
                "support_status": "official",
                "release_default": True,
            },
            {
                "device_id": "MIYOO_MINI_PLUS",
                "support_status": "official",
                "release_default": True,
            },
            {
                "device_id": "MIYOO_MINI_FLIP",
                "support_status": "official",
                "release_default": True,
            },
        ],
        "default_execution_profile": "ra32-mini-v0",
        "optional_execution_profiles": [],
        "candidate_build_flavors": [],
        "provider_observations": [
            {
                "role": "bundled-first-search-path-provider",
                "path": "/mnt/SDCARD/miyoo/lib/libstdc++.so.6",
                "sha256": "8014989515dc003f669e87abe4cbd89dcc4d68a458248ceee2528d73ed457a72",
                "max_versioned_symbols": {
                    "GLIBCXX": "3.4.32",
                    "CXXABI": "1.3.14",
                },
                "enforcing": False,
            }
        ],
        "missing_evidence": ["target-playback-validation", "target-rootfs-load-validation"],
    },
    "device-trimui-a133p-family-v0": {
        "runtime_family_id": "a133p-v0",
        "devices": [
            {
                "device_id": "TRIMUI_SMART_PRO",
                "support_status": "official",
                "release_default": True,
            },
            {
                "device_id": "TRIMUI_BRICK",
                "support_status": "official",
                "release_default": True,
            },
            {
                "device_id": "TRIMUI_BRICK_PRO",
                "support_status": "staged",
                "release_default": False,
            },
        ],
        "default_execution_profile": "ra64-universal-v1",
        "optional_execution_profiles": [],
        "candidate_build_flavors": [],
        "provider_observations": [
            {
                "role": "packaged-fallback-provider",
                "path": "/usr/lib/libstdc++.so.6.0.28",
                "sha256": "29d043b7bcd049f0d254cb190b92cfe68105a08b38e8b5f487bfaf1ffb1ce7d1",
                "max_versioned_symbols": {
                    "GLIBCXX": "3.4.28",
                    "CXXABI": "1.3.12",
                },
                "enforcing": False,
            }
        ],
        "missing_evidence": [
            "target-playback-validation",
            "target-rootfs-load-validation",
        ],
    },
    "device-trimui-smart-pro-s-v0": {
        "runtime_family_id": "trimui-smart-pro-s-v0",
        "devices": [
            {
                "device_id": "TRIMUI_SMART_PRO_S",
                "support_status": "official",
                "release_default": True,
            }
        ],
        "default_execution_profile": "ra64-universal-v1",
        "optional_execution_profiles": [],
        "candidate_build_flavors": [],
        "provider_observations": [
            {
                "role": "packaged-fallback-provider",
                "path": "/usr/lib/libstdc++.so.6.0.28",
                "sha256": "21aa3b6bbbdb88933da4d11f744920f7c71a3511492fe7c4098adfd26d5e408b",
                "max_versioned_symbols": {
                    "GLIBCXX": "3.4.28",
                    "CXXABI": "1.3.12",
                },
                "enforcing": False,
            }
        ],
        "missing_evidence": ["target-playback-validation", "target-rootfs-load-validation"],
    },
    "device-gkd-pixel2-v0": {
        "runtime_family_id": "gkd-pixel2-v0",
        "devices": [
            {
                "device_id": "GKD_PIXEL2",
                "support_status": "provisional",
                "release_default": False,
            }
        ],
        "default_execution_profile": "ra64-pixel2-v0",
        "optional_execution_profiles": [],
        "candidate_build_flavors": [],
        "provider_observations": [
            {
                "role": "packaged-fallback-provider",
                "path": "/usr/lib/libstdc++.so.6.0.33",
                "sha256": "22347a81e63224af1eb2222df273b65fdcfeaab7db90c4c7172c2fe4188fc6d7",
                "max_versioned_symbols": {
                    "GLIBCXX": "3.4.33",
                    "CXXABI": "1.3.15",
                },
                "enforcing": False,
            }
        ],
        "missing_evidence": ["target-playback-validation", "target-rootfs-load-validation"],
    },
    "device-anbernic-h700-family-v0": {
        "runtime_family_id": "allwinner-h700-v0",
        "devices": [
            {
                "device_id": "ANBERNIC_RG28XX",
                "support_status": "provisional",
                "release_default": False,
            },
            {
                "device_id": "ANBERNIC_RG34XXSP",
                "support_status": "provisional",
                "release_default": False,
            },
            {
                "device_id": "ANBERNIC_RGCUBEXX",
                "support_status": "provisional",
                "release_default": False,
            },
            {
                "device_id": "ANBERNIC_RGXX640480",
                "support_status": "provisional",
                "release_default": False,
            },
        ],
        "default_execution_profile": "ra64-universal-v1",
        "optional_execution_profiles": ["ra32-universal-v0"],
        "candidate_build_flavors": [],
        "provider_observations": [],
        "missing_evidence": [
            "effective-runtime-provider-capture",
            "target-loader-capture",
            "target-rootfs-load-validation",
        ],
    },
    "device-magicx-zero28-v0": {
        "runtime_family_id": "a133p-v0",
        "devices": [
            {
                "device_id": "MAGICX_ZERO28",
                "support_status": "provisional",
                "release_default": False,
            }
        ],
        "default_execution_profile": "ra64-universal-v1",
        "optional_execution_profiles": [],
        "candidate_build_flavors": [],
        "provider_observations": [],
        "missing_evidence": [
            "effective-runtime-provider-capture",
            "target-loader-capture",
            "target-playback-validation",
            "target-rootfs-load-validation",
        ],
    },
}


class RegistryError(RuntimeError):
    """Raised when immutable registry data fails closed validation."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RegistryError(f"cannot read JSON file {path}: {exc}") from exc
    if len(raw) > MAX_JSON_SIZE:
        raise RegistryError(f"JSON file exceeds {MAX_JSON_SIZE} bytes: {path}")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RegistryError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RegistryError(f"JSON document must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise RegistryError(f"cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def canonical_content_sha256(document: dict[str, Any]) -> str:
    """Hash all semantic fields, excluding schema routing and the digest itself."""

    if not isinstance(document, dict):
        raise RegistryError("content digest input must be an object")
    material = {
        key: value
        for key, value in document.items()
        if key not in {"$schema", "content_sha256"}
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _pin_set_content_sha256(document: dict[str, Any]) -> str:
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
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _toolchain_lock_content_sha256(document: dict[str, Any]) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "lock_id": document.get("lock_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "toolchains": document.get("toolchains"),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RegistryError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise RegistryError(f"{label} must be an array")
    return value


def _string(value: Any, label: str, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryError(f"{label} must be a non-empty string")
    if pattern is not None and not pattern.fullmatch(value):
        raise RegistryError(f"{label} has an invalid value")
    return value


def _exact_keys(
    value: dict[str, Any] | set[str], expected: set[str], label: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RegistryError(f"{label} keys differ; missing={missing}, extra={extra}")


def _unique_strings(
    value: Any,
    label: str,
    pattern: re.Pattern[str] | None = None,
) -> list[str]:
    items = _array(value, label)
    result = [_string(item, f"{label}[{index}]", pattern) for index, item in enumerate(items)]
    if len(result) != len(set(result)):
        raise RegistryError(f"{label} contains duplicates")
    return result


def _validate_content_digest(document: dict[str, Any], label: str) -> None:
    digest = _string(document.get("content_sha256"), f"{label}.content_sha256", SHA256_RE)
    expected = canonical_content_sha256(document)
    if digest != expected:
        raise RegistryError(f"{label}.content_sha256 does not cover current content")


def _validate_local_header(
    document: dict[str, Any],
    *,
    schema_ref: str,
    label: str,
) -> None:
    if document.get("$schema") != schema_ref:
        raise RegistryError(f"{label} has the wrong $schema reference")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise RegistryError(f"{label}.schema_version must be integer 1")
    if document.get("local_only") is not True:
        raise RegistryError(f"{label}.local_only must be true")
    if document.get("publication") != "disabled":
        raise RegistryError(f"{label}.publication must be disabled")


def _safe_repo_file(repo_root: Path, relative: str, label: str) -> Path:
    raw = Path(relative)
    if (
        raw.is_absolute()
        or raw.as_posix() != relative
        or not raw.parts
        or any(part in {"", ".", ".."} for part in raw.parts)
    ):
        raise RegistryError(f"{label} must be an exact repository-relative path")
    root = repo_root.resolve()
    candidate = root
    for part in raw.parts:
        candidate /= part
        try:
            info = candidate.lstat()
        except OSError as exc:
            raise RegistryError(f"{label} is unavailable: {relative}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode):
            raise RegistryError(f"{label} must not traverse a symlink: {relative}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RegistryError(f"{label} escapes repository root") from exc
    if not resolved.is_file():
        raise RegistryError(f"{label} is not a regular file: {relative}")
    return resolved


def _validate_spruce_snapshot(snapshot: Any, label: str) -> dict[str, Any]:
    result = _object(snapshot, label)
    _exact_keys(result, {"repository", "commit", "tree"}, label)
    if result["repository"] != SPRUCE_SNAPSHOT["repository"]:
        raise RegistryError(f"{label}.repository is not the approved SpruceOS source")
    _string(result["commit"], f"{label}.commit", SHA1_RE)
    _string(result["tree"], f"{label}.tree", SHA1_RE)
    if result != SPRUCE_SNAPSHOT:
        raise RegistryError(f"{label} is not the approved SpruceOS consumer snapshot")
    return result


def validate_source_lock(
    document: dict[str, Any],
    *,
    path: Path | None = None,
    repo_root: Path = ROOT,
) -> None:
    label = "source lock"
    _exact_keys(
        document,
        {
            "$schema",
            "schema_version",
            "source_lock_id",
            "core_id",
            "source",
            "local_only",
            "publication",
            "content_sha256",
        },
        label,
    )
    _validate_local_header(document, schema_ref=SOURCE_LOCK_SCHEMA_REF, label=label)
    core_id = _string(document["core_id"], "source lock.core_id", CORE_ID_RE)
    source = _object(document["source"], "source lock.source")
    _exact_keys(source, {"url", "requested_ref", "commit", "tree", "submodules"}, "source lock.source")
    url = _string(source["url"], "source lock.source.url")
    try:
        parsed_url = urlsplit(url)
    except ValueError as exc:
        raise RegistryError("source lock.source.url is malformed") from exc
    if (
        parsed_url.scheme != "https"
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or "?" in url
        or "#" in url
        or bool(parsed_url.query)
        or bool(parsed_url.fragment)
        or not parsed_url.path.endswith(".git")
        or any(char.isspace() for char in url)
    ):
        raise RegistryError("source lock.source.url must be an exact HTTPS Git URL")
    requested_ref = _string(source["requested_ref"], "source lock.source.requested_ref")
    ref_prefix = next(
        (
            prefix
            for prefix in ("refs/heads/", "refs/tags/")
            if requested_ref.startswith(prefix)
        ),
        None,
    )
    if (
        ref_prefix is None
        or requested_ref == ref_prefix
        or any(char.isspace() for char in requested_ref)
    ):
        raise RegistryError("source lock.source.requested_ref must be a full branch or tag ref")
    commit = _string(source["commit"], "source lock.source.commit", SHA1_RE)
    _string(source["tree"], "source lock.source.tree", SHA1_RE)
    submodules = _array(source["submodules"], "source lock.source.submodules")
    paths: list[str] = []
    for index, item in enumerate(submodules):
        submodule = _object(item, f"source lock.source.submodules[{index}]")
        _exact_keys(submodule, {"path", "commit"}, f"source lock.source.submodules[{index}]")
        submodule_path = _string(submodule["path"], f"source lock.source.submodules[{index}].path")
        if (
            not SUBMODULE_PATH_RE.fullmatch(submodule_path)
            or any(part in {"", ".", ".."} for part in Path(submodule_path).parts)
        ):
            raise RegistryError("source lock submodule path is not exact and relative")
        _string(submodule["commit"], f"source lock.source.submodules[{index}].commit", SHA1_RE)
        paths.append(submodule_path)
    if paths != sorted(set(paths)):
        raise RegistryError("source lock submodules must be unique and path-sorted")
    expected_id = f"{core_id}-{commit[:12]}"
    if document["source_lock_id"] != expected_id:
        raise RegistryError("source lock id does not bind core and commit")
    _validate_content_digest(document, label)
    if path is not None:
        try:
            relative = path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError as exc:
            raise RegistryError("source lock path is outside repository root") from exc
        expected_path = f"pins/sources/{core_id}/{commit}.json"
        if relative != expected_path:
            raise RegistryError("source lock path does not bind core and commit")


def _validate_reference_digest(value: Any, label: str) -> dict[str, Any]:
    reference = _object(value, label)
    _exact_keys(
        reference,
        {"path", "source_lock_id", "commit", "file_sha256", "content_sha256"},
        label,
    )
    _string(reference["path"], f"{label}.path")
    _string(reference["source_lock_id"], f"{label}.source_lock_id")
    _string(reference["commit"], f"{label}.commit", SHA1_RE)
    _string(reference["file_sha256"], f"{label}.file_sha256", SHA256_RE)
    _string(reference["content_sha256"], f"{label}.content_sha256", SHA256_RE)
    return reference


def validate_source_set(
    document: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    verify_files: bool = True,
) -> None:
    label = "source set"
    _exact_keys(
        document,
        {
            "$schema",
            "schema_version",
            "source_set_id",
            "local_only",
            "publication",
            "evidence_pin",
            "sources",
            "content_sha256",
        },
        label,
    )
    _validate_local_header(document, schema_ref=SOURCE_SET_SCHEMA_REF, label=label)
    _string(document["source_set_id"], "source set.source_set_id", LOCAL_ID_RE)
    evidence = _object(document["evidence_pin"], "source set.evidence_pin")
    _exact_keys(evidence, {"path", "pin_id", "file_sha256", "content_sha256"}, "source set.evidence_pin")
    _string(evidence["path"], "source set.evidence_pin.path", CORE_SET_PATH_RE)
    _string(evidence["pin_id"], "source set.evidence_pin.pin_id", LOCAL_ID_RE)
    _string(evidence["file_sha256"], "source set.evidence_pin.file_sha256", SHA256_RE)
    _string(evidence["content_sha256"], "source set.evidence_pin.content_sha256", SHA256_RE)
    sources = _object(document["sources"], "source set.sources")
    if not sources:
        raise RegistryError("source set.sources must not be empty")
    for core_id, raw_reference in sources.items():
        _string(core_id, "source set core id", CORE_ID_RE)
        reference = _validate_reference_digest(raw_reference, f"source set.sources.{core_id}")
        expected_path = f"pins/sources/{core_id}/{reference['commit']}.json"
        if reference["path"] != expected_path:
            raise RegistryError(f"source set reference path does not bind {core_id}")
        if reference["source_lock_id"] != f"{core_id}-{reference['commit'][:12]}":
            raise RegistryError(f"source set reference id does not bind {core_id}")
        if verify_files:
            lock_path = _safe_repo_file(repo_root, reference["path"], f"source lock {core_id}")
            if sha256_file(lock_path) != reference["file_sha256"]:
                raise RegistryError(f"source lock file digest differs for {core_id}")
            lock = strict_json_file(lock_path)
            validate_source_lock(lock, path=lock_path, repo_root=repo_root)
            if (
                lock["core_id"] != core_id
                or lock["source_lock_id"] != reference["source_lock_id"]
                or lock["source"]["commit"] != reference["commit"]
                or lock["content_sha256"] != reference["content_sha256"]
            ):
                raise RegistryError(f"source lock reference content differs for {core_id}")
    _validate_content_digest(document, label)
    if verify_files:
        pin_path = _safe_repo_file(repo_root, evidence["path"], "source evidence pin")
        if sha256_file(pin_path) != evidence["file_sha256"]:
            raise RegistryError("source evidence pin file digest differs")
        pin = strict_json_file(pin_path)
        if (
            pin.get("pin_id") != evidence["pin_id"]
            or pin.get("content_sha256") != evidence["content_sha256"]
            or pin.get("content_sha256") != _pin_set_content_sha256(pin)
            or pin.get("local_only") is not True
            or pin.get("publication") != "disabled"
        ):
            raise RegistryError("source evidence pin identity differs")


def _validate_build_identity(identity: Any, profile_id: str, architecture: str, repo_root: Path) -> None:
    value = _object(identity, f"execution profile {profile_id}.build_identity")
    expected_keys = {
        "toolchain_lock_path",
        "toolchain_lock_id",
        "toolchain_lock_file_sha256",
        "toolchain_lock_content_sha256",
        "toolchain_architecture",
        "image_id",
        "dockerfile_sha256",
        "dockerfile_linkage",
        "compiler",
        "sysroot",
    }
    _exact_keys(value, expected_keys, f"execution profile {profile_id}.build_identity")
    if value["toolchain_lock_path"] != "pins/toolchains/local-cache-v1.json":
        raise RegistryError(f"execution profile {profile_id} has an unknown toolchain lock")
    if value["toolchain_lock_id"] != "local-cache-v1":
        raise RegistryError(f"execution profile {profile_id} has an unknown toolchain lock id")
    if value["toolchain_architecture"] != architecture:
        raise RegistryError(f"execution profile {profile_id} toolchain architecture differs")
    _string(value["toolchain_lock_file_sha256"], "toolchain lock file digest", SHA256_RE)
    _string(value["toolchain_lock_content_sha256"], "toolchain lock content digest", SHA256_RE)
    image_id = _string(value["image_id"], "toolchain image id")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RegistryError(f"execution profile {profile_id} image id is invalid")
    _string(value["dockerfile_sha256"], "toolchain dockerfile digest", SHA256_RE)
    if value["dockerfile_linkage"] != "unverified-local-cache":
        raise RegistryError(
            f"execution profile {profile_id} must preserve unverified Dockerfile linkage"
        )
    _string(value["compiler"], "toolchain compiler")
    if not _string(value["sysroot"], "toolchain sysroot").startswith("/"):
        raise RegistryError(f"execution profile {profile_id} sysroot must be absolute")
    expected_compiler_sysroot = {
        "ra32-a30-v1": (
            "arm-a30-linux-gnueabihf-gcc-13.2.0.br_real (Buildroot 2024.02.1) 13.2.0",
            "/opt/a30/arm-a30-linux-gnueabihf/sysroot",
        ),
        "ra64-universal-v1": (
            "aarch64-linux-gnu-gcc (Ubuntu 9.4.0-1ubuntu1~20.04.2) 9.4.0",
            "/",
        ),
    }
    if (value["compiler"], value["sysroot"]) != expected_compiler_sysroot.get(profile_id):
        raise RegistryError(f"execution profile {profile_id} compiler/sysroot identity differs")
    lock_path = _safe_repo_file(repo_root, value["toolchain_lock_path"], "toolchain lock")
    if sha256_file(lock_path) != value["toolchain_lock_file_sha256"]:
        raise RegistryError(f"execution profile {profile_id} toolchain lock file differs")
    lock = strict_json_file(lock_path)
    if lock.get("content_sha256") != _toolchain_lock_content_sha256(lock):
        raise RegistryError(f"execution profile {profile_id} toolchain lock content differs")
    entry = _object(_object(lock.get("toolchains"), "toolchain lock.toolchains").get(architecture), f"toolchain {architecture}")
    if (
        lock.get("lock_id") != value["toolchain_lock_id"]
        or lock.get("content_sha256") != value["toolchain_lock_content_sha256"]
        or _object(entry.get("image"), f"toolchain {architecture}.image").get("id") != value["image_id"]
        or _object(entry.get("dockerfile"), f"toolchain {architecture}.dockerfile").get("sha256")
        != value["dockerfile_sha256"]
        or _object(entry.get("dockerfile"), f"toolchain {architecture}.dockerfile").get("linkage")
        != value["dockerfile_linkage"]
    ):
        raise RegistryError(f"execution profile {profile_id} toolchain identity differs")


def validate_execution_profiles(
    document: dict[str, Any],
    *,
    repo_root: Path = ROOT,
) -> None:
    label = "execution profiles"
    _exact_keys(
        document,
        {
            "$schema",
            "schema_version",
            "registry_id",
            "local_only",
            "publication",
            "spruce_snapshot",
            "profiles",
            "content_sha256",
        },
        label,
    )
    _validate_local_header(document, schema_ref=EXECUTION_SCHEMA_REF, label=label)
    if document["registry_id"] != "execution-profiles-v1":
        raise RegistryError("execution profile registry id is invalid")
    _validate_spruce_snapshot(document["spruce_snapshot"], "execution profiles.spruce_snapshot")
    profiles = _object(document["profiles"], "execution profiles.profiles")
    if set(profiles) != EXPECTED_PROFILE_IDS:
        raise RegistryError(
            "execution profile registry does not contain the exact supported profiles"
        )
    expected = {
        "ra32-a30-v1": ("armhf", "RetroArch/ra32.a30", "91c1e475371d1035bfec94c1f39f5df8132203e9feec38764f5a34ccd29eae37", "ELF32", "ARM", "/lib/ld-linux-armhf.so.3", "locked-build-identity"),
        "ra32-mini-v0": ("armhf", "RetroArch/ra32.mini", "f7350c5755277b4aca957ce08055c71685bd59cf5967cfbb72899e932d8fae4d", "ELF32", "ARM", "/lib/ld-linux-armhf.so.3", "provisional"),
        "ra32-universal-v0": ("armhf", "RetroArch/ra32.universal", "1fdf00d848e61a0703fa51ccc968d207e712017b9af28be7c2a07cb8577c7586", "ELF32", "ARM", "/lib/ld-linux-armhf.so.3", "provisional"),
        "ra64-pixel2-v0": ("arm64", "RetroArch/ra64.pixel2", None, "ELF64", "AArch64", "/lib/ld-linux-aarch64.so.1", "provisional-missing-frontend"),
        "ra64-universal-v1": ("arm64", "RetroArch/ra64.universal", "b94fd5ea8bdc5a969d2639e7365088b246fa8241d00428c86be00a6d807c4c11", "ELF64", "AArch64", "/lib/ld-linux-aarch64.so.1", "locked-build-identity"),
    }
    for profile_id, profile_value in profiles.items():
        _string(profile_id, "execution profile id", PROFILE_ID_RE)
        profile = _object(profile_value, f"execution profile {profile_id}")
        _exact_keys(
            profile,
            {"architecture", "status", "frontend", "core_layout", "build_identity", "missing_evidence", "runtime_validation"},
            f"execution profile {profile_id}",
        )
        architecture, path, frontend_sha256, elf_class, machine, interpreter, status = expected[profile_id]
        if profile["architecture"] != architecture or profile["status"] != status:
            raise RegistryError(f"execution profile {profile_id} architecture/status differs")
        if profile["runtime_validation"] != "needs-target-runtime":
            raise RegistryError(f"execution profile {profile_id} overclaims runtime validation")
        frontend = _object(profile["frontend"], f"execution profile {profile_id}.frontend")
        _exact_keys(frontend, {"availability", "spruce_path", "sha256", "elf_class", "machine", "interpreter"}, f"execution profile {profile_id}.frontend")
        if (
            frontend["spruce_path"] != path
            or frontend["sha256"] != frontend_sha256
            or frontend["elf_class"] != elf_class
            or frontend["machine"] != machine
            or frontend["interpreter"] != interpreter
        ):
            raise RegistryError(f"execution profile {profile_id} frontend identity differs")
        availability = frontend["availability"]
        if availability == "present":
            _string(frontend["sha256"], f"execution profile {profile_id}.frontend.sha256", SHA256_RE)
        elif availability == "missing" and frontend["sha256"] is None:
            pass
        else:
            raise RegistryError(f"execution profile {profile_id} frontend availability differs")
        layout = _object(profile["core_layout"], f"execution profile {profile_id}.core_layout")
        _exact_keys(layout, {"directory", "package_directory"}, f"execution profile {profile_id}.core_layout")
        expected_layout = (
            ("RetroArch/.retroarch/cores64", "cores64")
            if architecture == "arm64"
            else ("RetroArch/.retroarch/cores", "cores")
        )
        if (layout["directory"], layout["package_directory"]) != expected_layout:
            raise RegistryError(f"execution profile {profile_id} core layout differs")
        missing = _unique_strings(profile["missing_evidence"], f"execution profile {profile_id}.missing_evidence")
        if set(missing) - PROFILE_MISSING_EVIDENCE:
            raise RegistryError(f"execution profile {profile_id} has unknown missing evidence")
        if missing != EXPECTED_PROFILE_MISSING_EVIDENCE[profile_id]:
            raise RegistryError(
                f"execution profile {profile_id} missing-evidence contract differs"
            )
        if status == "locked-build-identity":
            if missing:
                raise RegistryError(f"locked execution profile {profile_id} has missing build evidence")
            _validate_build_identity(profile["build_identity"], profile_id, architecture, repo_root)
        else:
            if profile["build_identity"] is not None or not missing:
                raise RegistryError(f"provisional execution profile {profile_id} must fail closed")
            if status == "provisional-missing-frontend" and "frontend-binary" not in missing:
                raise RegistryError(f"missing frontend evidence is not explicit for {profile_id}")
    _validate_content_digest(document, label)


def validate_runtime_contracts(
    document: dict[str, Any],
    *,
    execution_profiles: dict[str, Any] | None = None,
    repo_root: Path = ROOT,
) -> None:
    label = "runtime contracts"
    _exact_keys(
        document,
        {
            "$schema",
            "schema_version",
            "registry_id",
            "local_only",
            "publication",
            "spruce_snapshot",
            "policy",
            "contracts",
            "compatibility_constraints",
            "core_policies",
            "content_sha256",
        },
        label,
    )
    _validate_local_header(document, schema_ref=RUNTIME_SCHEMA_REF, label=label)
    if document["registry_id"] != "device-runtime-contracts-v1":
        raise RegistryError("runtime contract registry id is invalid")
    snapshot = _validate_spruce_snapshot(document["spruce_snapshot"], "runtime contracts.spruce_snapshot")
    profile_ids = EXPECTED_PROFILE_IDS
    if execution_profiles is not None:
        validate_execution_profiles(execution_profiles, repo_root=repo_root)
        if snapshot != execution_profiles["spruce_snapshot"]:
            raise RegistryError("execution and runtime registries bind different Spruce snapshots")
        profile_ids = set(execution_profiles["profiles"])
    policy = _object(document["policy"], "runtime contracts.policy")
    _exact_keys(policy, {"artifact_reuse", "build_strategy", "default_tier", "runtime_claims"}, "runtime contracts.policy")
    expected_policy = {
        "artifact_reuse": "allow-after-runtime-contract-pass",
        "build_strategy": "portable-shared-default-sparse-family-override-on-evidence",
        "default_tier": "device_golden",
        "runtime_claims": "provisional-until-target-capture",
    }
    if policy != expected_policy:
        raise RegistryError("runtime contract policy differs")
    contracts = _object(document["contracts"], "runtime contracts.contracts")
    if set(contracts) != EXPECTED_CONTRACT_IDS:
        raise RegistryError(
            "runtime contract registry does not contain the exact supported device groups"
        )
    seen_devices: set[str] = set()
    family_by_contract: dict[str, str] = {}
    for contract_id, raw_contract in contracts.items():
        _string(contract_id, "runtime contract id", CONTRACT_ID_RE)
        contract = _object(raw_contract, f"runtime contract {contract_id}")
        # `library_observations` is optional: it appears once a device_probe
        # run has resolved the installed cores' libraries on that device.
        # `load_smoke` is optional: it appears once an on-device load-smoke
        # capture has been recorded for the contract's devices.
        _exact_keys(
            set(contract) - {"library_observations", "load_smoke"},
            {
                "status",
                "runtime_family_id",
                "devices",
                "default_execution_profile",
                "optional_execution_profiles",
                "candidate_build_flavors",
                "runtime_capture",
                "effective_abi_ceiling",
                "provider_observations",
                "missing_evidence",
            },
            f"runtime contract {contract_id}",
        )
        # A library-resolution capture is evidence about *loading*, not about
        # playback, so it may name the probe that ran but must not promote the
        # contract's status or claim an ABI ceiling. Those still require a
        # target-runtime smoke test.
        # A load-smoke capture is likewise loading evidence only: the
        # contract stays provisional and playback claims remain gated.
        if contract["status"] != "provisional" or contract["runtime_capture"] not in {
            "needs-target-runtime",
            "device-probe-v3",
            "load-smoke-v1",
        }:
            raise RegistryError(f"runtime contract {contract_id} overclaims validation")
        observations = contract.get("library_observations")
        if observations is not None:
            observations = _object(
                observations, f"runtime contract {contract_id}.library_observations"
            )
            if observations.get("enforcing") is not False:
                raise RegistryError(
                    f"runtime contract {contract_id} library observations overclaim enforcement"
                )
            if contract["runtime_capture"] != observations.get(
                "probe_schema"
            ) and not (
                contract["runtime_capture"] == "load-smoke-v1"
                and "load_smoke" in contract
            ):
                raise RegistryError(
                    f"runtime contract {contract_id} runtime_capture does not name its probe"
                )
        if contract["effective_abi_ceiling"] != "unknown":
            raise RegistryError(f"runtime contract {contract_id} overclaims an ABI ceiling")
        family = _string(
            contract["runtime_family_id"],
            f"runtime contract {contract_id}.runtime_family_id",
            FAMILY_ID_RE,
        )
        family_by_contract[contract_id] = family
        default_profile = _string(contract["default_execution_profile"], f"runtime contract {contract_id}.default_execution_profile", PROFILE_ID_RE)
        optional = _unique_strings(contract["optional_execution_profiles"], f"runtime contract {contract_id}.optional_execution_profiles", PROFILE_ID_RE)
        if default_profile not in profile_ids or any(item not in profile_ids for item in optional):
            raise RegistryError(f"runtime contract {contract_id} references an unknown profile")
        if default_profile in optional:
            raise RegistryError(f"runtime contract {contract_id} repeats its default profile")
        candidates = _unique_strings(contract["candidate_build_flavors"], f"runtime contract {contract_id}.candidate_build_flavors")
        if candidates:
            raise RegistryError(
                f"runtime contract {contract_id} must not bind unvalidated build flavors"
            )
        devices = _array(contract["devices"], f"runtime contract {contract_id}.devices")
        if not devices:
            raise RegistryError(f"runtime contract {contract_id} has no devices")
        for index, raw_device in enumerate(devices):
            device = _object(raw_device, f"runtime contract {contract_id}.devices[{index}]")
            _exact_keys(device, {"device_id", "support_status", "release_default"}, f"runtime contract {contract_id}.devices[{index}]")
            device_id = _string(device["device_id"], f"runtime contract {contract_id}.devices[{index}].device_id", DEVICE_ID_RE)
            if device_id in seen_devices:
                raise RegistryError(f"device {device_id} belongs to more than one runtime contract")
            seen_devices.add(device_id)
            if device["support_status"] not in {"official", "staged", "provisional"}:
                raise RegistryError(f"device {device_id} support status is invalid")
            if type(device["release_default"]) is not bool:
                raise RegistryError(f"device {device_id} release_default must be boolean")
            if device["support_status"] != "official" and device["release_default"]:
                raise RegistryError(f"non-official device {device_id} cannot be a release default")
        observations = _array(contract["provider_observations"], f"runtime contract {contract_id}.provider_observations")
        for index, raw_observation in enumerate(observations):
            observation = _object(raw_observation, f"runtime contract {contract_id}.provider_observations[{index}]")
            _exact_keys(observation, {"role", "path", "sha256", "max_versioned_symbols", "enforcing"}, f"runtime contract {contract_id}.provider_observations[{index}]")
            if observation["role"] not in {"bundled-first-search-path-provider", "packaged-fallback-provider"}:
                raise RegistryError(f"runtime contract {contract_id} provider role is invalid")
            _string(observation["path"], "provider observation path")
            _string(observation["sha256"], "provider observation digest", SHA256_RE)
            symbols = _object(observation["max_versioned_symbols"], "provider observation symbols")
            _exact_keys(symbols, {"GLIBCXX", "CXXABI"}, "provider observation symbols")
            _string(symbols["GLIBCXX"], "provider GLIBCXX version", VERSION_RE)
            _string(symbols["CXXABI"], "provider CXXABI version", VERSION_RE)
            if observation["enforcing"] is not False:
                raise RegistryError("provider observations must remain non-enforcing")
        missing = _unique_strings(contract["missing_evidence"], f"runtime contract {contract_id}.missing_evidence")
        if not missing:
            raise RegistryError(f"runtime contract {contract_id} must identify missing target evidence")
        if set(missing) - RUNTIME_MISSING_EVIDENCE:
            raise RegistryError(f"runtime contract {contract_id} has unknown missing evidence")
        expected_facts = EXPECTED_RUNTIME_CONTRACT_FACTS[contract_id]
        actual_facts = {
            key: contract[key]
            for key in expected_facts
        }
        if actual_facts != expected_facts:
            raise RegistryError(
                f"runtime contract {contract_id} canonical device/profile facts differ"
            )
    if family_by_contract["device-trimui-a133p-family-v0"] != family_by_contract["device-magicx-zero28-v0"]:
        raise RegistryError("TrimUI and MagicX A133P views must share a runtime family")
    constraints = _array(document["compatibility_constraints"], "runtime contracts.compatibility_constraints")
    if len(constraints) != 1:
        raise RegistryError("runtime contracts must contain the one known Mini C++ uncertainty")
    constraint = _object(constraints[0], "runtime compatibility constraint")
    _exact_keys(constraint, {"constraint_id", "core_ids", "execution_profile_id", "kind", "required_symbols", "disposition", "evidence_scope"}, "runtime compatibility constraint")
    if (
        constraint["constraint_id"] != "mini-cxx-provider-unverified-v0"
        or constraint["core_ids"] != ["gearboy", "gearsystem"]
        or constraint["execution_profile_id"] != "ra32-mini-v0"
        or constraint["kind"] != "provider-ceiling-unverified"
        or constraint["required_symbols"] != ["GLIBCXX_3.4.32"]
        or constraint["disposition"] != "unverified-for-profile"
        or constraint["evidence_scope"] != "packaged-fallback-observation"
    ):
        raise RegistryError("Mini compatibility constraint overclaims or differs")
    core_policies = _object(document["core_policies"], "runtime contracts.core_policies")
    _exact_keys(core_policies, {"ffmpeg", "swanstation"}, "runtime contracts.core_policies")
    ffmpeg = _object(core_policies["ffmpeg"], "runtime contracts.core_policies.ffmpeg")
    _exact_keys(ffmpeg, {"portable_role", "default_selection", "accelerated_candidates", "accelerated_denied_runtime_contracts", "runtime_validation"}, "runtime contracts.core_policies.ffmpeg")
    if (
        ffmpeg["portable_role"] != "software-diagnostic-only"
        or ffmpeg["default_selection"] != "excluded"
        or ffmpeg["runtime_validation"] != "needs-target-playback"
    ):
        raise RegistryError("FFmpeg must remain nondefault and runtime-unverified")
    accelerated = _array(ffmpeg["accelerated_candidates"], "FFmpeg accelerated candidates")
    if len(accelerated) != 1:
        raise RegistryError("FFmpeg must have only the sparse A133P candidate")
    candidate = _object(accelerated[0], "FFmpeg accelerated candidate")
    _exact_keys(candidate, {"build_flavor_id", "runtime_contract_ids", "runtime_family_ids", "status"}, "FFmpeg accelerated candidate")
    candidate_contracts = _unique_strings(candidate["runtime_contract_ids"], "FFmpeg candidate runtime contracts", CONTRACT_ID_RE)
    candidate_families = _unique_strings(candidate["runtime_family_ids"], "FFmpeg candidate runtime families")
    if (
        candidate["build_flavor_id"] != "trimui-a133p-pvr-v0"
        or set(candidate_contracts) != {"device-trimui-a133p-family-v0", "device-magicx-zero28-v0"}
        or candidate_families != ["a133p-v0"]
        or candidate["status"] != "provisional"
        or any(family_by_contract[item] != "a133p-v0" for item in candidate_contracts)
    ):
        raise RegistryError("FFmpeg accelerated candidate is not strictly A133P-scoped")
    denied = set(_unique_strings(ffmpeg["accelerated_denied_runtime_contracts"], "FFmpeg denied runtime contracts", CONTRACT_ID_RE))
    if denied != {"device-miyoo-flip-v0", "device-trimui-smart-pro-s-v0"}:
        raise RegistryError("FFmpeg accelerated denial set differs")
    swan = _object(core_policies["swanstation"], "runtime contracts.core_policies.swanstation")
    _exact_keys(swan, {"armhf_device_views", "runtime_contract_ids", "catalog_menu_eligibility"}, "runtime contracts.core_policies.swanstation")
    if (
        swan["armhf_device_views"] != "not-consumed"
        or set(swan["runtime_contract_ids"]) != {"device-miyoo-a30-v0", "device-miyoo-mini-family-v0"}
        or swan["catalog_menu_eligibility"] != "unsupported"
    ):
        raise RegistryError("SwanStation ARMHF consumer policy differs")
    _validate_content_digest(document, label)


def _normalized_submodules(value: Any, label: str) -> list[dict[str, str]]:
    items = _array(value, label)
    normalized: list[dict[str, str]] = []
    for index, raw_item in enumerate(items):
        item = _object(raw_item, f"{label}[{index}]")
        if set(item) not in ({"path", "commit"}, {"path", "commit", "state"}):
            raise RegistryError(f"{label}[{index}] has an unexpected shape")
        normalized.append(
            {
                "path": _string(item["path"], f"{label}[{index}].path"),
                "commit": _string(item["commit"], f"{label}[{index}].commit", SHA1_RE),
            }
        )
    return normalized


def verify_catalog_source_mirror(
    *,
    source_set: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, int]:
    validate_source_set(source_set, repo_root=repo_root)
    catalog = strict_json_file(repo_root / CATALOG_PATH.relative_to(ROOT))
    cores = _object(catalog.get("cores"), "build catalog.cores")
    source_references = _object(source_set["sources"], "source set.sources")
    missing_catalog_cores = set(source_references) - set(cores)
    if missing_catalog_cores:
        raise RegistryError(
            "source set cores are missing from the build catalog: "
            f"{sorted(missing_catalog_cores)}"
        )
    evidence = source_set["evidence_pin"]
    pin = strict_json_file(_safe_repo_file(repo_root, evidence["path"], "source evidence pin"))
    pin_cores = _object(pin.get("cores"), "source evidence pin.cores")
    if set(pin_cores) != set(source_references):
        raise RegistryError("source set coverage differs from its evidence pin")
    evidence_cells = 0
    for core_id, reference in source_references.items():
        lock = strict_json_file(_safe_repo_file(repo_root, reference["path"], f"source lock {core_id}"))
        source = lock["source"]
        catalog_source = _object(_object(cores[core_id], f"catalog core {core_id}").get("source"), f"catalog core {core_id}.source")
        for field in ("url", "requested_ref", "commit"):
            if catalog_source.get(field) != source[field]:
                raise RegistryError(f"catalog source {field} differs for {core_id}")
        if "tree" in catalog_source and catalog_source["tree"] != source["tree"]:
            raise RegistryError(f"catalog source tree differs for {core_id}")
        selection = _object(_object(pin_cores[core_id], f"pin core {core_id}").get("selection"), f"pin core {core_id}.selection")
        if selection.get("tier") != "build_golden" or selection.get("validation_scope") != "static-build-only":
            raise RegistryError(f"source evidence tier differs for {core_id}")
        targets = _object(selection.get("targets"), f"pin core {core_id}.selection.targets")
        # Single-ABI cores (uae4arm/squirreljme armhf-only; swanstation,
        # yabasanshiro, the N64 tier arm64-only) pin exactly their catalog
        # target set, not a hardcoded pair.
        if set(targets) != set(
            _object(cores[core_id], f"catalog core {core_id}").get("targets", [])
        ):
            raise RegistryError(f"source evidence targets differ for {core_id}")
        for architecture, raw_target in targets.items():
            target = _object(raw_target, f"pin core {core_id}.{architecture}")
            golden = _object(target.get("golden_record"), f"pin core {core_id}.{architecture}.golden_record")
            golden_source = _object(golden.get("source"), f"pin core {core_id}.{architecture}.source")
            if (
                golden_source.get("url") != source["url"]
                or golden_source.get("resolved_url") != source["url"]
                or golden_source.get("requested_ref") != source["requested_ref"]
                or golden_source.get("commit") != source["commit"]
                or golden_source.get("resolved_commit") != source["commit"]
                or golden_source.get("tree") != source["tree"]
                # An empty lock submodule list is the reviewed convention
                # for "gitlinks are pinned by the superproject tree": the
                # golden's captured submodules are build-time evidence the
                # pipeline already validated against that tree, not a
                # divergence from the lock. Compare only when the lock
                # actually enumerates gitlinks.
                or (
                    source["submodules"] != []
                    and _normalized_submodules(golden_source.get("submodules"), f"pin core {core_id}.{architecture}.submodules")
                    != source["submodules"]
                )
            ):
                raise RegistryError(
                    f"source evidence differs for {core_id}/{architecture}"
                )
            artifact = _object(target.get("artifact"), f"pin core {core_id}.{architecture}.artifact")
            _string(artifact.get("sha256"), f"pin core {core_id}.{architecture}.artifact.sha256", SHA256_RE)
            evidence_cells += 1
    return {
        "locked_cores": len(source_references),
        "catalog_cores": len(cores),
        "catalog_unlocked_cores": len(set(cores) - set(source_references)),
        "evidence_cells": evidence_cells,
    }


def _build_evidence_cells(
    source_set: dict[str, Any],
    pin: dict[str, Any],
    execution_profiles: dict[str, Any],
) -> list[dict[str, str]]:
    cells: list[dict[str, str]] = []
    for core_id in sorted(source_set["sources"]):
        source_lock_id = source_set["sources"][core_id]["source_lock_id"]
        selection = pin["cores"][core_id]["selection"]
        # Single-ABI cores carry exactly their pinned target set; the cells
        # cover what the pin proves, nothing more.
        for architecture in sorted(selection["targets"]):
            target = selection["targets"][architecture]
            cells.append(
                {
                    "core_id": core_id,
                    "architecture": architecture,
                    "execution_profile_id": PROFILE_BINDING[architecture],
                    "source_lock_id": source_lock_id,
                    "artifact_sha256": target["artifact"]["sha256"],
                    "tier": selection["tier"],
                    "validation_scope": selection["validation_scope"],
                    "device_eligibility": "provisional-unverified",
                    "dockerfile_linkage": execution_profiles["profiles"][
                        PROFILE_BINDING[architecture]
                    ]["build_identity"]["dockerfile_linkage"],
                }
            )
    return cells


def copy_device_metadata(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "device_id": device["device_id"],
            "support_status": device["support_status"],
            "release_default": device["release_default"],
        }
        for device in devices
    ]


def _source_set_report_data(
    *,
    source_set: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    execution_profiles = strict_json_file(repo_root / EXECUTION_PROFILES_PATH.relative_to(ROOT))
    runtime_contracts = strict_json_file(repo_root / RUNTIME_CONTRACTS_PATH.relative_to(ROOT))
    validate_source_set(source_set, repo_root=repo_root)
    validate_execution_profiles(execution_profiles, repo_root=repo_root)
    validate_runtime_contracts(
        runtime_contracts,
        execution_profiles=execution_profiles,
        repo_root=repo_root,
    )
    mirror = verify_catalog_source_mirror(repo_root=repo_root, source_set=source_set)
    pin = strict_json_file(_safe_repo_file(repo_root, source_set["evidence_pin"]["path"], "source evidence pin"))
    cells = _build_evidence_cells(source_set, pin, execution_profiles)
    # One evidence cell per PINNED target: dual-ABI cores map two, the
    # single-ABI cores exactly one.
    expected_cells = sum(
        len(pin["cores"][core_id]["selection"]["targets"])
        for core_id in source_set["sources"]
    )
    if len(cells) != expected_cells:
        raise RegistryError(
            "source/profile bridge must map one evidence cell per pinned target"
        )
    if any(
        cell["execution_profile_id"] != "ra32-a30-v1"
        for cell in cells
        if cell["architecture"] == "armhf"
    ):
        raise RegistryError("ARMHF build evidence must not be aliased to Mini or universal32")
    device_views = []
    for contract_id, contract in sorted(runtime_contracts["contracts"].items()):
        device_views.append(
            {
                "runtime_contract_id": contract_id,
                "runtime_family_id": contract["runtime_family_id"],
                "device_ids": [device["device_id"] for device in contract["devices"]],
                "devices": copy_device_metadata(contract["devices"]),
                "default_execution_profile": contract["default_execution_profile"],
                "optional_execution_profiles": contract["optional_execution_profiles"],
                "status": contract["status"],
                "eligible_build_evidence_cells": [],
                "eligibility": "provisional-unverified",
            }
        )
    return {
        "schema_version": 1,
        "local_only": True,
        "publication": "disabled",
        "source_set_id": source_set["source_set_id"],
        "spruce_snapshot": execution_profiles["spruce_snapshot"],
        "build_strategy": runtime_contracts["policy"]["build_strategy"],
        "artifact_reuse": runtime_contracts["policy"]["artifact_reuse"],
        "counts": {
            "source_locks": len(source_set["sources"]),
            "execution_profiles": len(execution_profiles["profiles"]),
            "runtime_contracts": len(runtime_contracts["contracts"]),
            "devices": sum(len(contract["devices"]) for contract in runtime_contracts["contracts"].values()),
            "build_evidence_cells": len(cells),
        },
        "mirror": mirror,
        "build_evidence_cells": cells,
        "device_views": device_views,
        "compatibility_constraints": runtime_contracts[
            "compatibility_constraints"
        ],
        "core_policies": runtime_contracts["core_policies"],
    }


def report_data(
    *,
    source_set_path: str,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Return the active exact-one-core source/profile report."""

    _string(source_set_path, "source set path", SOURCE_SET_PATH_RE)
    source_set = strict_json_file(
        _safe_repo_file(repo_root, source_set_path, "source set")
    )
    validate_source_set(source_set, repo_root=repo_root)
    if len(source_set["sources"]) != 1:
        raise RegistryError("individual source set must contain exactly one core")
    return _source_set_report_data(
        source_set=source_set,
        repo_root=repo_root,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    commands = (
        (
            "report",
            "validate and report one core's source/profile bindings",
            "required repo-relative individual source-set manifest",
        ),
    )
    for command, command_help, source_help in commands:
        report = subparsers.add_parser(command, help=command_help)
        report.add_argument("--source-set", required=True, help=source_help)
        report.add_argument(
            "--json", action="store_true", help="emit machine-readable JSON"
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "report":
            report = report_data(source_set_path=args.source_set)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                counts = report["counts"]
                print(
                    f"source_set={report['source_set_id']} "
                    f"cores={counts['source_locks']} "
                    f"profiles={counts['execution_profiles']} "
                    f"runtime_contracts={counts['runtime_contracts']} "
                    f"build_evidence_cells={counts['build_evidence_cells']}"
                )
            return 0
    except RegistryError as exc:
        print(f"profile registry error: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
