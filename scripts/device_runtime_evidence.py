#!/usr/bin/env python3
"""Migrate and project artifact-bound physical-device runtime evidence.

The checked-in v1 capture is an immutable source transcript.  ``migrate``
joins its physical-device verdicts to the exact evidence indexes, device
contracts, and execution profiles at the sealed candidate commit.  The v2
result is therefore explicit for every historical physical device and every
canonical core, with load status kept independent from selection policy.

``project`` joins those observations to today's canonical artifact SHA-256s.
It never treats family-level static eligibility as a runtime pass.  Family
summaries are conservative: any disagreement between physical members yields
``UNKNOWN`` while retaining every member result.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
_PROFILE_REGISTRY_SPEC = importlib.util.spec_from_file_location(
    "device_runtime_profile_registry", ROOT / "scripts" / "profile_registry.py"
)
if _PROFILE_REGISTRY_SPEC is None or _PROFILE_REGISTRY_SPEC.loader is None:
    raise RuntimeError("cannot load maintained profile registry validators")
profile_registry = importlib.util.module_from_spec(_PROFILE_REGISTRY_SPEC)
_PROFILE_REGISTRY_SPEC.loader.exec_module(profile_registry)

SCHEMA_PATH = ROOT / "manifests" / "device-runtime-captures.schema.json"
V1_CAPTURE_PATH = (
    ROOT
    / "manifests"
    / "device-runtime-captures"
    / "load-smoke-20260724-v1.json"
)
V2_CAPTURE_PATH = (
    ROOT
    / "manifests"
    / "device-runtime-captures"
    / "load-smoke-20260724-v2.json"
)
CURRENT_CONTRACTS_PATH = ROOT / "manifests" / "device-runtime-contracts.json"
CURRENT_PROFILES_PATH = ROOT / "manifests" / "execution-profiles.json"
CURRENT_CATALOG_PATH = ROOT / "manifests" / "core-builds.json"
HISTORICAL_COMMIT = "aaaee534cb75d8ca0e65c2afe2e4390f1c184478"
V1_CAPTURE_SHA256 = "a36c192848efcbd9f2d56280da2b601b080e845f062430860adbb5beedb6dee2"
HISTORICAL_CONTRACTS_PATH = "manifests/device-runtime-contracts.json"
HISTORICAL_PROFILES_PATH = "manifests/execution-profiles.json"
HISTORICAL_CATALOG_PATH = "manifests/core-builds.json"
HISTORICAL_EVIDENCE_PREFIX = "pins/evidence"

EXPECTED_DEVICE_COUNT = 16
# The evidence corpus: cores with promoted build evidence under pins/evidence.
# The live catalog may be larger - cores pinned as compile candidates carry a
# pending compatibility record instead of evidence and project as NO_BUILD.
EXPECTED_CORE_COUNT = 98
PENDING_COMPATIBILITY_DIR = "manifests/compatibility/pending"
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
LOAD_RESULTS = {"PASS", "FAIL", "UNKNOWN", "NO_BUILD"}
DECLARED_CONTEXT_BASIS = "candidate-contract-and-profile-snapshots"
DECLARED_CONTEXT_STATUS = "DECLARED_NOT_DEVICE_OBSERVED"
CURRENT_DECLARED_CONTEXT_BASIS = "current-validated-contract-and-profile-registries"
RUNTIME_CONTEXT_CAVEAT = (
    "legacy v1 observed only the RetroArch binary name; execution-profile ID "
    "and frontend path/SHA are repository declarations, not on-device observations"
)


class DeviceRuntimeEvidenceError(Exception):
    """Raised when runtime evidence is incomplete, ambiguous, or stale."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeviceRuntimeEvidenceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_duplicate_rejecting_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeviceRuntimeEvidenceError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise DeviceRuntimeEvidenceError(f"{label} must be a JSON object")
    return value


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DeviceRuntimeEvidenceError(f"{label} is not readable: {exc}") from exc
    return _decode_json_object(raw, label), raw


def _safe_repo_path(
    repo_root: Path, relative: str, label: str, *, directory: bool
) -> Path:
    raw = Path(relative)
    if (
        raw.is_absolute()
        or raw.as_posix() != relative
        or not raw.parts
        or any(part in {"", ".", ".."} for part in raw.parts)
    ):
        raise DeviceRuntimeEvidenceError(
            f"{label} must be an exact repository-relative path"
        )
    root = repo_root.resolve()
    candidate = root
    for part in raw.parts:
        candidate /= part
        try:
            info = candidate.lstat()
        except OSError as exc:
            raise DeviceRuntimeEvidenceError(
                f"{label} is unavailable: {relative}: {exc}"
            ) from exc
        if stat.S_ISLNK(info.st_mode):
            raise DeviceRuntimeEvidenceError(
                f"{label} must not traverse a symlink: {relative}"
            )
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DeviceRuntimeEvidenceError(f"{label} escapes repository root") from exc
    expected_kind = resolved.is_dir() if directory else resolved.is_file()
    if not expected_kind:
        kind = "directory" if directory else "regular file"
        raise DeviceRuntimeEvidenceError(f"{label} is not a {kind}: {relative}")
    return resolved


def _safe_repo_file(repo_root: Path, relative: str, label: str) -> Path:
    return _safe_repo_path(repo_root, relative, label, directory=False)


def _safe_repo_directory(repo_root: Path, relative: str, label: str) -> Path:
    return _safe_repo_path(repo_root, relative, label, directory=True)


def _read_repo_json(
    repo_root: Path, relative: str, label: str
) -> tuple[dict[str, Any], bytes, Path]:
    path = _safe_repo_file(repo_root, relative, label)
    document, raw = _read_json(path, label)
    return document, raw, path


def _git_blob(repo_root: Path, commit: str, path: str) -> bytes:
    if not SHA1_RE.fullmatch(commit):
        raise DeviceRuntimeEvidenceError("historical repository commit is invalid")
    try:
        completed = subprocess.run(
            ["git", "--no-replace-objects", "show", f"{commit}:{path}"],
            cwd=repo_root,
            check=True,
            env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise DeviceRuntimeEvidenceError(
            f"cannot read {path} at {commit}{suffix}"
        ) from exc
    return completed.stdout


def _git_tree_files(repo_root: Path, commit: str, path_prefix: str) -> set[str]:
    if not SHA1_RE.fullmatch(commit):
        raise DeviceRuntimeEvidenceError("historical repository commit is invalid")
    try:
        completed = subprocess.run(
            [
                "git",
                "--no-replace-objects",
                "ls-tree",
                "-r",
                "--name-only",
                commit,
                "--",
                path_prefix,
            ],
            cwd=repo_root,
            check=True,
            env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise DeviceRuntimeEvidenceError(
            f"cannot list {path_prefix} at {commit}{suffix}"
        ) from exc
    try:
        paths = completed.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise DeviceRuntimeEvidenceError(
            f"tree listing for {path_prefix} at {commit} is not UTF-8"
        ) from exc
    if len(paths) != len(set(paths)):
        raise DeviceRuntimeEvidenceError(
            f"tree listing for {path_prefix} at {commit} has duplicates"
        )
    return set(paths)


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _document_content_sha256(document: Mapping[str, Any]) -> str:
    return _canonical_sha256(
        {key: value for key, value in document.items() if key != "content_sha256"}
    )


def _render_json(document: Mapping[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeviceRuntimeEvidenceError(f"{label} must be an object")
    return value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise DeviceRuntimeEvidenceError(f"{label} must be an array")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise DeviceRuntimeEvidenceError(f"{label} must be a non-empty string")
    return value


def _schema_validator() -> Draft202012Validator:
    schema, _raw, _path = _read_repo_json(
        ROOT,
        SCHEMA_PATH.relative_to(ROOT).as_posix(),
        "device runtime capture schema",
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_schema(document: Mapping[str, Any], label: str) -> None:
    errors = sorted(
        _schema_validator().iter_errors(document),
        key=lambda item: (list(item.absolute_path), item.message),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path)
        prefix = f" at {location}" if location else ""
        raise DeviceRuntimeEvidenceError(
            f"{label} fails schema{prefix}: {error.message}"
        )


def _snapshot(path: str, raw: bytes) -> dict[str, str]:
    return {"path": path, "file_sha256": _sha256_bytes(raw)}


def _load_historical_inputs(repo_root: Path) -> dict[str, Any]:
    paths = {
        "device_runtime_contracts": HISTORICAL_CONTRACTS_PATH,
        "execution_profiles": HISTORICAL_PROFILES_PATH,
        "core_builds": HISTORICAL_CATALOG_PATH,
    }
    result: dict[str, Any] = {"raw": {}, "documents": {}, "snapshots": {}}
    for name, path in paths.items():
        raw = _git_blob(repo_root, HISTORICAL_COMMIT, path)
        result["raw"][name] = raw
        result["documents"][name] = _decode_json_object(
            raw, f"{path} at {HISTORICAL_COMMIT}"
        )
        result["snapshots"][name] = _snapshot(path, raw)
    return result


def _pending_core_ids(repo_root: Path) -> set[str]:
    directory = repo_root / PENDING_COMPATIBILITY_DIR
    if not directory.is_dir():
        return set()
    return {
        path.stem
        for path in directory.iterdir()
        if path.suffix == ".json" and CORE_ID_RE.fullmatch(path.stem)
    }


def _catalog_core_ids(
    catalog: Mapping[str, Any],
    label: str,
    *,
    evidence_core_ids: set[str] | None = None,
) -> list[str]:
    cores = _require_mapping(catalog.get("cores"), f"{label}.cores")
    core_ids = sorted(cores)
    if any(CORE_ID_RE.fullmatch(core_id) is None for core_id in core_ids):
        raise DeviceRuntimeEvidenceError(f"{label} has an invalid core id")
    evidence_backed = (
        core_ids
        if evidence_core_ids is None
        else [core_id for core_id in core_ids if core_id in evidence_core_ids]
    )
    if len(evidence_backed) != EXPECTED_CORE_COUNT:
        raise DeviceRuntimeEvidenceError(
            f"{label} must contain exactly {EXPECTED_CORE_COUNT} "
            "evidence-backed cores"
        )
    return core_ids


def _artifact_from_evidence(
    *,
    core_id: str,
    architecture: str,
    evidence: Mapping[str, Any],
    evidence_path: str,
    evidence_file_sha256: str,
) -> dict[str, Any] | None:
    if evidence.get("core_id") != core_id:
        raise DeviceRuntimeEvidenceError(
            f"{evidence_path} core_id does not match {core_id}"
        )
    semantic_id = _require_string(
        evidence.get("semantic_id"), f"{evidence_path}.semantic_id"
    )
    selection_sha256 = _require_string(
        evidence.get("selection_sha256"), f"{evidence_path}.selection_sha256"
    )
    if SHA256_RE.fullmatch(selection_sha256) is None:
        raise DeviceRuntimeEvidenceError(
            f"{evidence_path}.selection_sha256 is invalid"
        )
    pin_path = _require_string(evidence.get("pin_path"), f"{evidence_path}.pin_path")
    targets = _require_mapping(evidence.get("targets"), f"{evidence_path}.targets")
    if not targets or not set(targets) <= {"arm64", "armhf"}:
        raise DeviceRuntimeEvidenceError(f"{evidence_path}.targets is invalid")
    target = targets.get(architecture)
    if target is None:
        return None
    target = _require_mapping(target, f"{evidence_path}.targets.{architecture}")
    sha256 = _require_string(
        target.get("artifact_sha256"),
        f"{evidence_path}.targets.{architecture}.artifact_sha256",
    )
    size = target.get("artifact_size")
    if SHA256_RE.fullmatch(sha256) is None:
        raise DeviceRuntimeEvidenceError(
            f"{evidence_path}.targets.{architecture}.artifact_sha256 is invalid"
        )
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise DeviceRuntimeEvidenceError(
            f"{evidence_path}.targets.{architecture}.artifact_size is invalid"
        )
    return {
        "sha256": sha256,
        "size": size,
        "authority": {
            "evidence_index_path": evidence_path,
            "evidence_index_file_sha256": evidence_file_sha256,
            "semantic_id": semantic_id,
            "selection_sha256": selection_sha256,
            "pin_path": pin_path,
        },
    }


def _historical_artifacts(
    repo_root: Path, core_ids: Iterable[str]
) -> tuple[dict[str, dict[str, dict[str, Any] | None]], dict[str, str]]:
    core_ids = list(core_ids)
    expected_paths = {
        f"{HISTORICAL_EVIDENCE_PREFIX}/{core_id}.json" for core_id in core_ids
    }
    actual_paths = _git_tree_files(
        repo_root, HISTORICAL_COMMIT, HISTORICAL_EVIDENCE_PREFIX
    )
    if actual_paths != expected_paths:
        raise DeviceRuntimeEvidenceError(
            "historical evidence indexes do not exactly match the core snapshot"
        )
    artifacts: dict[str, dict[str, dict[str, Any] | None]] = {}
    evidence_hashes: dict[str, str] = {}
    for core_id in core_ids:
        path = f"{HISTORICAL_EVIDENCE_PREFIX}/{core_id}.json"
        raw = _git_blob(repo_root, HISTORICAL_COMMIT, path)
        digest = _sha256_bytes(raw)
        evidence_hashes[path] = digest
        evidence = _decode_json_object(raw, f"{path} at {HISTORICAL_COMMIT}")
        artifacts[core_id] = {
            architecture: _artifact_from_evidence(
                core_id=core_id,
                architecture=architecture,
                evidence=evidence,
                evidence_path=path,
                evidence_file_sha256=digest,
            )
            for architecture in ("arm64", "armhf")
        }
    return artifacts, evidence_hashes


def _current_artifacts(
    repo_root: Path, core_ids: Iterable[str]
) -> tuple[dict[str, dict[str, dict[str, Any] | None]], dict[str, str]]:
    artifacts: dict[str, dict[str, dict[str, Any] | None]] = {}
    evidence_hashes: dict[str, str] = {}
    core_ids = list(core_ids)
    expected_paths = {f"pins/evidence/{core_id}.json" for core_id in core_ids}
    evidence_dir = _safe_repo_directory(
        repo_root, "pins/evidence", "current evidence directory"
    )
    actual_paths = {
        f"pins/evidence/{path.name}" for path in evidence_dir.iterdir()
    }
    if actual_paths != expected_paths:
        raise DeviceRuntimeEvidenceError(
            "current evidence indexes do not exactly match the canonical roster"
        )
    for core_id in core_ids:
        path = f"pins/evidence/{core_id}.json"
        evidence, raw, _resolved = _read_repo_json(repo_root, path, path)
        digest = _sha256_bytes(raw)
        evidence_hashes[path] = digest
        artifacts[core_id] = {
            architecture: _artifact_from_evidence(
                core_id=core_id,
                architecture=architecture,
                evidence=evidence,
                evidence_path=path,
                evidence_file_sha256=digest,
            )
            for architecture in ("arm64", "armhf")
        }
    return artifacts, evidence_hashes


def _evidence_set_snapshot(evidence_hashes: Mapping[str, str]) -> dict[str, Any]:
    items = [
        {"path": path, "file_sha256": evidence_hashes[path]}
        for path in sorted(evidence_hashes)
    ]
    if len(items) != EXPECTED_CORE_COUNT:
        raise DeviceRuntimeEvidenceError(
            f"evidence index set must contain {EXPECTED_CORE_COUNT} files"
        )
    return {
        "path_prefix": HISTORICAL_EVIDENCE_PREFIX,
        "file_count": len(items),
        "file_set_sha256": _canonical_sha256(items),
    }


def _device_contexts(
    contracts_document: Mapping[str, Any], profiles_document: Mapping[str, Any]
) -> list[dict[str, Any]]:
    contracts = _require_mapping(contracts_document.get("contracts"), "contracts")
    profiles = _require_mapping(profiles_document.get("profiles"), "profiles")
    contexts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for contract_id in sorted(contracts):
        contract = _require_mapping(contracts[contract_id], f"contract {contract_id}")
        family_id = _require_string(
            contract.get("runtime_family_id"),
            f"contract {contract_id}.runtime_family_id",
        )
        profile_id = _require_string(
            contract.get("default_execution_profile"),
            f"contract {contract_id}.default_execution_profile",
        )
        profile = _require_mapping(profiles.get(profile_id), f"profile {profile_id}")
        architecture = profile.get("architecture")
        if architecture not in {"arm64", "armhf"}:
            raise DeviceRuntimeEvidenceError(
                f"profile {profile_id} has an invalid architecture"
            )
        frontend = _require_mapping(
            profile.get("frontend"), f"profile {profile_id}.frontend"
        )
        frontend_availability = frontend.get("availability")
        if frontend_availability not in {"present", "missing"}:
            raise DeviceRuntimeEvidenceError(
                f"profile {profile_id} frontend availability is invalid"
            )
        frontend_path = _require_string(
            frontend.get("spruce_path"),
            f"profile {profile_id}.frontend.spruce_path",
        )
        frontend_sha256 = frontend.get("sha256")
        if frontend_availability == "present":
            if (
                not isinstance(frontend_sha256, str)
                or SHA256_RE.fullmatch(frontend_sha256) is None
            ):
                raise DeviceRuntimeEvidenceError(
                    f"profile {profile_id} frontend sha256 is invalid"
                )
        elif frontend_sha256 is not None:
            raise DeviceRuntimeEvidenceError(
                f"missing profile {profile_id} frontend must not have a sha256"
            )
        devices = _require_list(
            contract.get("devices"), f"contract {contract_id}.devices"
        )
        for raw_device in devices:
            device = _require_mapping(raw_device, f"contract {contract_id} device")
            device_id = _require_string(device.get("device_id"), "device_id")
            if device_id in seen:
                raise DeviceRuntimeEvidenceError(
                    f"physical device appears more than once: {device_id}"
                )
            seen.add(device_id)
            support_status = device.get("support_status")
            release_default = device.get("release_default")
            if support_status not in {"official", "staged", "provisional"}:
                raise DeviceRuntimeEvidenceError(
                    f"device {device_id} support_status is invalid"
                )
            if type(release_default) is not bool:
                raise DeviceRuntimeEvidenceError(
                    f"device {device_id} release_default is invalid"
                )
            contexts.append(
                {
                    "device_id": device_id,
                    "runtime_contract_id": contract_id,
                    "runtime_family_id": family_id,
                    "support_status": support_status,
                    "release_default": release_default,
                    "execution_profile_id": profile_id,
                    "architecture": architecture,
                    "frontend_availability": frontend_availability,
                    "frontend_path": frontend_path,
                    "frontend_sha256": frontend_sha256,
                }
            )
    contexts.sort(key=lambda item: item["device_id"])
    if len(contexts) != EXPECTED_DEVICE_COUNT:
        raise DeviceRuntimeEvidenceError(
            f"device snapshot must contain exactly {EXPECTED_DEVICE_COUNT} devices"
        )
    return contexts


def _flat_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Declared device context, flat on the row, as both test specs read it."""

    return {
        "runtime_contract_id": context["runtime_contract_id"],
        "runtime_family_id": context["runtime_family_id"],
        "execution_profile_id": context["execution_profile_id"],
        "architecture": context["architecture"],
        "support_status": context["support_status"],
        "release_default": context["release_default"],
        "frontend_availability": context["frontend_availability"],
        "frontend_path": context["frontend_path"],
        "frontend_sha256": context["frontend_sha256"],
    }


def _policy_for(
    policies: Mapping[str, Any], core_id: str, architecture: str, contract_id: str
) -> dict[str, Any]:
    if core_id not in policies:
        return {"status": "INCLUDED", "reason": None}
    raw_policy = policies[core_id]
    if not isinstance(raw_policy, dict):
        raise DeviceRuntimeEvidenceError(f"core policy for {core_id} is invalid")
    if raw_policy.get("default_selection") == "excluded":
        if "armhf_device_views" in raw_policy:
            raise DeviceRuntimeEvidenceError(
                f"core policy for {core_id} mixes exclusion models"
            )
        return {"status": "EXCLUDED", "reason": "default-excluded"}
    runtime_contract_ids = raw_policy.get("runtime_contract_ids", [])
    if raw_policy.get("armhf_device_views") == "not-consumed":
        if (
            not isinstance(runtime_contract_ids, list)
            or not runtime_contract_ids
            or any(not isinstance(item, str) or not item for item in runtime_contract_ids)
            or len(runtime_contract_ids) != len(set(runtime_contract_ids))
        ):
            raise DeviceRuntimeEvidenceError(
                f"core policy contract scope for {core_id} is invalid"
            )
        if architecture == "armhf" and contract_id in runtime_contract_ids:
            return {"status": "EXCLUDED", "reason": "armhf-not-consumed"}
        return {"status": "INCLUDED", "reason": None}
    raise DeviceRuntimeEvidenceError(f"core policy for {core_id} is unsupported")


def _load_legacy_capture(
    repo_root: Path,
    *,
    contexts: Iterable[Mapping[str, Any]],
    core_ids: Iterable[str],
    artifacts: Mapping[str, Mapping[str, dict[str, Any] | None]],
) -> tuple[dict[str, Any], bytes, dict[str, dict[str, Any]]]:
    document, raw, _path = _read_repo_json(
        repo_root,
        V1_CAPTURE_PATH.relative_to(ROOT).as_posix(),
        "legacy device runtime capture",
    )
    if _sha256_bytes(raw) != V1_CAPTURE_SHA256:
        raise DeviceRuntimeEvidenceError("legacy v1 capture bytes differ")
    _validate_schema(document, "legacy device runtime capture")
    candidate = _require_mapping(document.get("candidate"), "legacy candidate")
    short_commit = _require_string(
        candidate.get("repository_commit"), "legacy candidate.repository_commit"
    )
    if not HISTORICAL_COMMIT.startswith(short_commit):
        raise DeviceRuntimeEvidenceError(
            "legacy capture does not name the historical candidate commit"
        )
    if candidate.get("candidate_id") != "wave4b-complete-30124953754-1":
        raise DeviceRuntimeEvidenceError("legacy candidate id differs")
    if candidate.get("sealed_run") != "30124953754":
        raise DeviceRuntimeEvidenceError("legacy sealed run differs")

    context_by_device = {item["device_id"]: item for item in contexts}
    core_set = set(core_ids)
    captured: dict[str, dict[str, Any]] = {}
    contracts = _require_mapping(document.get("contracts"), "legacy contracts")
    for contract_id, raw_block in contracts.items():
        block = _require_mapping(raw_block, f"legacy contract {contract_id}")
        for raw_device in _require_list(
            block.get("devices"), f"legacy contract {contract_id}.devices"
        ):
            device = _require_mapping(raw_device, "legacy captured device")
            device_id = _require_string(device.get("device_id"), "legacy device_id")
            if device_id in captured:
                raise DeviceRuntimeEvidenceError(
                    f"legacy capture repeats physical device {device_id}"
                )
            context = context_by_device.get(device_id)
            if context is None or context["runtime_contract_id"] != contract_id:
                raise DeviceRuntimeEvidenceError(
                    f"legacy device {device_id} is bound to the wrong contract"
                )
            passed = _require_list(device.get("passed"), f"{device_id}.passed")
            if any(not isinstance(item, str) for item in passed):
                raise DeviceRuntimeEvidenceError(f"{device_id}.passed is invalid")
            if len(passed) != len(set(passed)):
                raise DeviceRuntimeEvidenceError(f"{device_id}.passed has duplicates")
            failed = _require_mapping(device.get("failed"), f"{device_id}.failed")
            if set(passed) & set(failed):
                raise DeviceRuntimeEvidenceError(
                    f"{device_id} has overlapping pass and fail verdicts"
                )
            seen = set(passed) | set(failed)
            architecture = context["architecture"]
            expected = {
                core_id
                for core_id in core_set
                if artifacts[core_id][architecture] is not None
            }
            if seen != expected:
                raise DeviceRuntimeEvidenceError(
                    f"{device_id} verdicts do not exactly cover its artifact set"
                )
            if device.get("passed_count") != len(passed):
                raise DeviceRuntimeEvidenceError(f"{device_id} passed_count differs")
            if device.get("artifacts_byte_verified") != len(seen):
                raise DeviceRuntimeEvidenceError(
                    f"{device_id} byte-verification count differs"
                )
            captured[device_id] = {
                "retroarch_binary": _require_string(
                    device.get("retroarch_binary"), f"{device_id}.retroarch_binary"
                ),
                "passed": set(passed),
                "failed": copy.deepcopy(failed),
            }
    return document, raw, captured


def build_migration(repo_root: Path = ROOT) -> dict[str, Any]:
    """Derive the exact v2 capture without consulting current mutable inputs."""

    historical = _load_historical_inputs(repo_root)
    contracts = historical["documents"]["device_runtime_contracts"]
    profiles = historical["documents"]["execution_profiles"]
    catalog = historical["documents"]["core_builds"]
    evidence_dir = repo_root / HISTORICAL_EVIDENCE_PREFIX
    evidence_ids = {
        path.stem for path in evidence_dir.iterdir() if path.suffix == ".json"
    }
    all_ids = _catalog_core_ids(
        catalog, "historical core catalog", evidence_core_ids=evidence_ids
    )
    core_ids = [core_id for core_id in all_ids if core_id in evidence_ids]
    contexts = _device_contexts(contracts, profiles)
    artifacts, evidence_hashes = _historical_artifacts(repo_root, core_ids)
    legacy, legacy_raw, captured = _load_legacy_capture(
        repo_root,
        contexts=contexts,
        core_ids=core_ids,
        artifacts=artifacts,
    )
    policies = _require_mapping(contracts.get("core_policies"), "core policies")

    artifact_subjects: list[dict[str, Any]] = []
    for core_id in core_ids:
        core_artifacts = artifacts[core_id]
        authorities = {
            _canonical_sha256(target["authority"])
            for target in core_artifacts.values()
            if target is not None
        }
        if len(authorities) != 1:
            raise DeviceRuntimeEvidenceError(
                f"historical artifact authority is ambiguous for {core_id}"
            )
        authority = next(
            target["authority"]
            for target in core_artifacts.values()
            if target is not None
        )
        artifact_subjects.append(
            {
                "core_id": core_id,
                "authority": copy.deepcopy(authority),
                "targets": {
                    architecture: (
                        {
                            "sha256": core_artifacts[architecture]["sha256"],
                            "size": core_artifacts[architecture]["size"],
                        }
                        if core_artifacts[architecture] is not None
                        else None
                    )
                    for architecture in ("arm64", "armhf")
                },
            }
        )

    devices: list[dict[str, Any]] = []
    for context in contexts:
        device_id = context["device_id"]
        architecture = context["architecture"]
        observed = captured.get(device_id)
        results: list[dict[str, Any]] = []
        for core_id in core_ids:
            artifact = artifacts[core_id][architecture]
            policy = _policy_for(
                policies,
                core_id,
                architecture,
                context["runtime_contract_id"],
            )
            if artifact is None:
                result = {
                    "core_id": core_id,
                    "architecture": architecture,
                    "artifact_sha256": None,
                    "artifact_byte_verified": False,
                    "load_result": "NO_BUILD",
                    "reason": "no-artifact-for-architecture",
                    "policy": policy,
                }
            elif observed is None:
                result = {
                    "core_id": core_id,
                    "architecture": architecture,
                    "artifact_sha256": artifact["sha256"],
                    "artifact_byte_verified": False,
                    "load_result": "UNKNOWN",
                    "reason": "device-not-captured",
                    "policy": policy,
                }
            elif core_id in observed["passed"]:
                result = {
                    "core_id": core_id,
                    "architecture": architecture,
                    "artifact_sha256": artifact["sha256"],
                    "artifact_byte_verified": True,
                    "load_result": "PASS",
                    "reason": "load-smoke-pass",
                    "policy": policy,
                }
            else:
                failure = observed["failed"].get(core_id)
                if not isinstance(failure, str) or not failure:
                    raise DeviceRuntimeEvidenceError(
                        f"captured result is missing for {device_id}/{core_id}"
                    )
                result = {
                    "core_id": core_id,
                    "architecture": architecture,
                    "artifact_sha256": artifact["sha256"],
                    "artifact_byte_verified": True,
                    "load_result": "FAIL",
                    "reason": failure,
                    "policy": policy,
                }
            results.append(result)
        devices.append(
            {
                "device_id": device_id,
                **_flat_context(context),
                "capture_status": (
                    "CAPTURED" if observed is not None else "NOT_CAPTURED"
                ),
                "retroarch_binary": (
                    observed["retroarch_binary"] if observed is not None else None
                ),
                "results": results,
            }
        )

    snapshots = historical["snapshots"]
    document: dict[str, Any] = {
        "$schema": "../device-runtime-captures.schema.json",
        "schema_version": 2,
        "capture_id": "load-smoke-20260724-v2",
        "kind": "artifact-bound-physical-device-load-smoke-v2",
        "captured_at": legacy["captured_at"],
        "local_only": True,
        "publication": "disabled",
        "source_capture": {
            "path": V1_CAPTURE_PATH.relative_to(ROOT).as_posix(),
            "file_sha256": _sha256_bytes(legacy_raw),
            "capture_id": legacy["capture_id"],
        },
        "candidate": {
            "candidate_id": legacy["candidate"]["candidate_id"],
            "sealed_run_id": legacy["candidate"]["sealed_run"],
            "repository_commit": HISTORICAL_COMMIT,
        },
        "derivation": {
            "model": (
                "legacy-v1-device-artifact-observations-plus-"
                "candidate-declarations-v1"
            ),
            "repository_commit": HISTORICAL_COMMIT,
            "device_runtime_contracts": snapshots["device_runtime_contracts"],
            "execution_profiles": snapshots["execution_profiles"],
            "core_builds": snapshots["core_builds"],
            "evidence_indexes": _evidence_set_snapshot(evidence_hashes),
        },
        "scope": {
            "level": "dlopen-libretro-init",
            "watchdog_seconds": 10,
            "content_boot": False,
            "input": False,
            "av_pacing": False,
            "saves": False,
            "sustained_performance": False,
        },
        "artifacts": artifact_subjects,
        "devices": devices,
    }
    document["content_sha256"] = _document_content_sha256(document)
    _validate_schema(document, "derived v2 device runtime capture")
    return document


def validate_capture(
    document: Mapping[str, Any], *, repo_root: Path = ROOT
) -> dict[str, Any]:
    """Strictly validate v2 shape, digest, sources, and deterministic migration."""

    _validate_schema(document, "v2 device runtime capture")
    if document.get("schema_version") != 2:
        raise DeviceRuntimeEvidenceError("capture is not schema v2")
    expected_digest = _document_content_sha256(document)
    if document.get("content_sha256") != expected_digest:
        raise DeviceRuntimeEvidenceError("v2 capture content_sha256 differs")
    expected = build_migration(repo_root)
    if document != expected:
        raise DeviceRuntimeEvidenceError(
            "v2 capture differs from the deterministic historical migration"
        )
    statuses: dict[str, int] = {status: 0 for status in sorted(LOAD_RESULTS)}
    for device in document["devices"]:
        for result in device["results"]:
            statuses[result["load_result"]] += 1
    return {
        "capture_id": document["capture_id"],
        "device_count": len(document["devices"]),
        "core_count": len(document["devices"][0]["results"]),
        "status_counts": statuses,
        "content_sha256": document["content_sha256"],
    }


def _load_capture_snapshot(
    path: Path = V2_CAPTURE_PATH, *, repo_root: Path = ROOT
) -> tuple[dict[str, Any], bytes, Path, str]:
    repo_root = repo_root.resolve()
    if path.is_absolute():
        try:
            relative = path.relative_to(repo_root).as_posix()
        except ValueError as exc:
            raise DeviceRuntimeEvidenceError(
                "v2 capture path must be inside the repository"
            ) from exc
    else:
        relative = path.as_posix()
    resolved = _safe_repo_file(repo_root, relative, "v2 device runtime capture")
    document, raw = _read_json(resolved, "v2 device runtime capture")
    validate_capture(document, repo_root=repo_root)
    return document, raw, resolved, relative


def load_capture(
    path: Path = V2_CAPTURE_PATH, *, repo_root: Path = ROOT
) -> dict[str, Any]:
    document, _raw, _resolved, _relative = _load_capture_snapshot(
        path, repo_root=repo_root
    )
    return document


def _capture_index(
    capture: Mapping[str, Any]
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[tuple[str, str], Mapping[str, Any]],
    dict[tuple[str, str], Mapping[str, Any] | None],
]:
    devices: dict[str, Mapping[str, Any]] = {}
    results: dict[tuple[str, str], Mapping[str, Any]] = {}
    artifacts: dict[tuple[str, str], Mapping[str, Any] | None] = {}
    for raw_subject in capture["artifacts"]:
        subject = _require_mapping(raw_subject, "capture artifact subject")
        core_id = _require_string(subject.get("core_id"), "artifact core_id")
        targets = _require_mapping(subject.get("targets"), f"{core_id}.targets")
        for architecture in ("arm64", "armhf"):
            key = (core_id, architecture)
            if key in artifacts:
                raise DeviceRuntimeEvidenceError(
                    f"capture repeats artifact subject {core_id}/{architecture}"
                )
            target = targets.get(architecture)
            if target is not None:
                target = _require_mapping(
                    target, f"capture artifact {core_id}/{architecture}"
                )
            artifacts[key] = target
    for raw_device in capture["devices"]:
        device = _require_mapping(raw_device, "capture device")
        device_id = device["device_id"]
        if device_id in devices:
            raise DeviceRuntimeEvidenceError(f"capture repeats device {device_id}")
        devices[device_id] = device
        for raw_result in device["results"]:
            result = _require_mapping(raw_result, f"capture result for {device_id}")
            key = (device_id, result["core_id"])
            if key in results:
                raise DeviceRuntimeEvidenceError(
                    f"capture repeats result {device_id}/{result['core_id']}"
                )
            target = artifacts.get(
                (result["core_id"], result["architecture"])
            )
            expected_sha256 = target.get("sha256") if target is not None else None
            if result.get("artifact_sha256") != expected_sha256:
                raise DeviceRuntimeEvidenceError(
                    "capture result artifact differs for "
                    f"{device_id}/{result['core_id']}"
                )
            results[key] = result
    return devices, results, artifacts


def _project_one_result(
    *,
    core_id: str,
    architecture: str,
    artifact: dict[str, Any] | None,
    policy: Mapping[str, Any],
    capture_device: Mapping[str, Any] | None,
    capture_result: Mapping[str, Any] | None,
    capture_artifact: Mapping[str, Any] | None,
    capture_id: str,
) -> dict[str, Any]:
    if artifact is None:
        return {
            "core_id": core_id,
            "architecture": architecture,
            "artifact": None,
            "load_result": "NO_BUILD",
            "reason": "no-artifact-for-architecture",
            "evidence_capture_id": None,
            "policy": copy.deepcopy(dict(policy)),
        }
    if capture_device is None or capture_result is None:
        return {
            "core_id": core_id,
            "architecture": architecture,
            "artifact": copy.deepcopy(artifact),
            "load_result": "UNKNOWN",
            "reason": "device-not-in-capture",
            "evidence_capture_id": None,
            "policy": copy.deepcopy(dict(policy)),
        }
    captured_sha256 = capture_result.get("artifact_sha256")
    exact = captured_sha256 == artifact["sha256"]
    if exact and (
        capture_artifact is None or capture_artifact.get("size") != artifact["size"]
    ):
        raise DeviceRuntimeEvidenceError(
            f"artifact size conflicts for {capture_device['device_id']}/{core_id}"
        )
    if not exact:
        return {
            "core_id": core_id,
            "architecture": architecture,
            "artifact": copy.deepcopy(artifact),
            "load_result": "UNKNOWN",
            "reason": (
                "device-not-captured"
                if capture_device.get("capture_status") == "NOT_CAPTURED"
                else "artifact-not-observed"
            ),
            "evidence_capture_id": None,
            "policy": copy.deepcopy(dict(policy)),
        }
    status = capture_result.get("load_result")
    if status not in LOAD_RESULTS - {"NO_BUILD"}:
        raise DeviceRuntimeEvidenceError(
            f"capture result for {capture_device['device_id']}/{core_id} is invalid"
        )
    return {
        "core_id": core_id,
        "architecture": architecture,
        "artifact": copy.deepcopy(artifact),
        "load_result": status,
        "reason": capture_result["reason"],
        "evidence_capture_id": (
            capture_id if status in {"PASS", "FAIL"} else None
        ),
        "policy": copy.deepcopy(dict(policy)),
    }


def aggregate_families(devices: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return conservative artifact-load summaries over physical family members."""

    by_family: dict[str, list[Mapping[str, Any]]] = {}
    architectures_by_device: dict[str, str] = {}
    seen_devices: set[str] = set()
    for device in devices:
        device_id = _require_string(device.get("device_id"), "projection device_id")
        if device_id in seen_devices:
            raise DeviceRuntimeEvidenceError(
                f"projection repeats physical device {device_id}"
            )
        seen_devices.add(device_id)
        family_id = _require_string(
            device.get("runtime_family_id"), f"{device_id}.runtime_family_id"
        )
        architecture = device.get("architecture")
        if architecture not in {"arm64", "armhf"}:
            raise DeviceRuntimeEvidenceError(
                f"{device_id} has an invalid declared architecture"
            )
        architectures_by_device[device_id] = architecture
        by_family.setdefault(family_id, []).append(device)

    families: list[dict[str, Any]] = []
    for family_id in sorted(by_family):
        members = sorted(by_family[family_id], key=lambda item: item["device_id"])
        architectures = {
            architectures_by_device[member["device_id"]] for member in members
        }
        if len(architectures) != 1:
            raise DeviceRuntimeEvidenceError(
                f"runtime family {family_id} mixes architectures"
            )
        result_maps: list[dict[str, Mapping[str, Any]]] = []
        for member in members:
            rows = _require_list(
                member.get("results"), f"{member['device_id']}.results"
            )
            mapping: dict[str, Mapping[str, Any]] = {}
            for row in rows:
                row = _require_mapping(row, "projection result")
                if set(row) != {
                    "core_id",
                    "architecture",
                    "artifact",
                    "load_result",
                    "reason",
                    "evidence_capture_id",
                    "policy",
                }:
                    raise DeviceRuntimeEvidenceError(
                        f"{member['device_id']} has a malformed projection result"
                    )
                core_id = _require_string(row.get("core_id"), "projection core_id")
                if core_id in mapping:
                    raise DeviceRuntimeEvidenceError(
                        f"{member['device_id']} repeats core {core_id}"
                    )
                architecture = architectures_by_device[member["device_id"]]
                if row.get("architecture") != architecture:
                    raise DeviceRuntimeEvidenceError(
                        f"{member['device_id']}/{core_id} mixes architectures"
                    )
                status = row.get("load_result")
                if status not in LOAD_RESULTS:
                    raise DeviceRuntimeEvidenceError(
                        f"{member['device_id']}/{core_id} has an invalid load result"
                    )
                _require_string(
                    row.get("reason"), f"{member['device_id']}/{core_id}.reason"
                )
                artifact = row.get("artifact")
                if status == "NO_BUILD":
                    if artifact is not None or row.get("evidence_capture_id") is not None:
                        raise DeviceRuntimeEvidenceError(
                            f"{member['device_id']}/{core_id} NO_BUILD is malformed"
                        )
                else:
                    artifact = _require_mapping(
                        artifact, f"{member['device_id']}/{core_id}.artifact"
                    )
                    sha256 = artifact.get("sha256")
                    size = artifact.get("size")
                    if (
                        not isinstance(sha256, str)
                        or SHA256_RE.fullmatch(sha256) is None
                        or not isinstance(size, int)
                        or isinstance(size, bool)
                        or size < 1
                    ):
                        raise DeviceRuntimeEvidenceError(
                            f"{member['device_id']}/{core_id} artifact is invalid"
                        )
                    evidence_capture_id = row.get("evidence_capture_id")
                    if status in {"PASS", "FAIL"}:
                        _require_string(
                            evidence_capture_id,
                            f"{member['device_id']}/{core_id}.evidence_capture_id",
                        )
                    elif evidence_capture_id is not None:
                        raise DeviceRuntimeEvidenceError(
                            f"{member['device_id']}/{core_id} UNKNOWN is malformed"
                        )
                policy = _require_mapping(
                    row.get("policy"), f"{member['device_id']}/{core_id}.policy"
                )
                if set(policy) != {"status", "reason"} or policy.get(
                    "status"
                ) not in {"INCLUDED", "EXCLUDED"}:
                    raise DeviceRuntimeEvidenceError(
                        f"{member['device_id']}/{core_id} policy is malformed"
                    )
                if (
                    policy["status"] == "INCLUDED"
                    and policy.get("reason") is not None
                ) or (
                    policy["status"] == "EXCLUDED"
                    and not isinstance(policy.get("reason"), str)
                ):
                    raise DeviceRuntimeEvidenceError(
                        f"{member['device_id']}/{core_id} policy is inconsistent"
                    )
                mapping[core_id] = row
            result_maps.append(mapping)
        core_sets = {frozenset(mapping) for mapping in result_maps}
        if len(core_sets) != 1:
            raise DeviceRuntimeEvidenceError(
                f"runtime family {family_id} has missing core evidence"
            )
        core_ids = sorted(next(iter(core_sets)))
        family_results: list[dict[str, Any]] = []
        for core_id in core_ids:
            member_results = [
                {
                    "device_id": member["device_id"],
                    "load_result": mapping[core_id]["load_result"],
                    "reason": mapping[core_id]["reason"],
                    "artifact_sha256": (
                        mapping[core_id]["artifact"]["sha256"]
                        if isinstance(mapping[core_id].get("artifact"), dict)
                        else None
                    ),
                }
                for member, mapping in zip(members, result_maps)
            ]
            statuses = {item["load_result"] for item in member_results}
            reasons = {item["reason"] for item in member_results}
            hashes = {item["artifact_sha256"] for item in member_results}
            if statuses == {"PASS"} and len(hashes) == 1:
                status = "PASS"
                reason = "all-physical-devices-pass"
            elif statuses == {"FAIL"} and len(reasons) == 1 and len(hashes) == 1:
                status = "FAIL"
                reason = next(iter(reasons))
            elif statuses == {"NO_BUILD"}:
                status = "NO_BUILD"
                reason = "no-family-device-build"
            elif statuses == {"UNKNOWN"} and len(hashes) == 1:
                status = "UNKNOWN"
                reason = "all-physical-device-results-unknown"
            else:
                status = "UNKNOWN"
                reason = "mixed-physical-device-results"
            family_results.append(
                {
                    "core_id": core_id,
                    "architecture": next(iter(architectures)),
                    "load_result": status,
                    "reason": reason,
                    "member_results": member_results,
                }
            )
        families.append(
            {
                "runtime_family_id": family_id,
                "architecture": next(iter(architectures)),
                "device_ids": [member["device_id"] for member in members],
                "results": family_results,
            }
        )
    return families


def _validate_current_registries(
    contracts: dict[str, Any], profiles: dict[str, Any], *, repo_root: Path
) -> None:
    try:
        # This maintained validator transitively validates execution profiles,
        # their content/Spruce/toolchain bindings, then the runtime contracts'
        # content, device, policy, and cross-registry bindings.
        profile_registry.validate_runtime_contracts(
            contracts,
            execution_profiles=profiles,
            repo_root=repo_root,
        )
    except profile_registry.RegistryError as exc:
        raise DeviceRuntimeEvidenceError(
            f"current device/profile registries are invalid: {exc}"
        ) from exc


def project_current_physical_devices(
    *, repo_root: Path = ROOT, capture_path: Path = V2_CAPTURE_PATH
) -> dict[str, Any]:
    """Return the exact current 98-core by 16-physical-device runtime matrix.

    This is the small public consumer API for renderers such as
    ``device_matrix.py``.  ``core_order`` and ``device_order`` are stable,
    every device contains one result for every core, and ``status_counts`` is
    over that complete Cartesian product. Runtime status is joined only by
    physical device and artifact SHA-256. Profile/frontend fields are declared
    repository context, never represented as observations. The independent
    ``policy`` field must not be rendered as a load verdict.
    """

    repo_root = repo_root.resolve()
    capture, capture_raw, _capture_resolved, capture_relative_path = (
        _load_capture_snapshot(capture_path, repo_root=repo_root)
    )
    capture_devices, capture_results, capture_artifacts = _capture_index(capture)
    contracts, contracts_raw, _contracts_path = _read_repo_json(
        repo_root,
        CURRENT_CONTRACTS_PATH.relative_to(ROOT).as_posix(),
        "current device runtime contracts",
    )
    profiles, profiles_raw, _profiles_path = _read_repo_json(
        repo_root,
        CURRENT_PROFILES_PATH.relative_to(ROOT).as_posix(),
        "current execution profiles",
    )
    catalog, catalog_raw, _catalog_path = _read_repo_json(
        repo_root,
        CURRENT_CATALOG_PATH.relative_to(ROOT).as_posix(),
        "current core catalog",
    )
    _validate_current_registries(contracts, profiles, repo_root=repo_root)
    # Pending compatibility cores (awaiting-local-e2e) have no promoted
    # evidence; the projection covers exactly the evidence-backed corpus and
    # the matrix layer surfaces pending cores separately.
    pending_ids = _pending_core_ids(repo_root)
    all_ids = _catalog_core_ids(
        catalog,
        "current core catalog",
        evidence_core_ids=set(catalog.get("cores", {})) - pending_ids,
    )
    core_ids = [core_id for core_id in all_ids if core_id not in pending_ids]
    contexts = _device_contexts(contracts, profiles)
    artifacts, evidence_hashes = _current_artifacts(repo_root, core_ids)
    policies = _require_mapping(contracts.get("core_policies"), "current core policies")

    devices: list[dict[str, Any]] = []
    for context in contexts:
        device_id = context["device_id"]
        architecture = context["architecture"]
        capture_device = capture_devices.get(device_id)
        flat_context = _flat_context(context)
        declared_profile_matches_capture_snapshot = bool(
            capture_device is not None
            and all(
                capture_device.get(key) == value
                for key, value in flat_context.items()
            )
        )
        results: list[dict[str, Any]] = []
        for core_id in core_ids:
            artifact = artifacts[core_id][architecture]
            policy = _policy_for(
                policies,
                core_id,
                architecture,
                context["runtime_contract_id"],
            )
            results.append(
                _project_one_result(
                    core_id=core_id,
                    architecture=architecture,
                    artifact=artifact,
                    policy=policy,
                    capture_device=capture_device,
                    capture_result=capture_results.get((device_id, core_id)),
                    capture_artifact=capture_artifacts.get((core_id, architecture)),
                    capture_id=capture["capture_id"],
                )
            )
        devices.append(
            {
                "device_id": device_id,
                **flat_context,
                "capture_status": (
                    capture_device["capture_status"]
                    if capture_device is not None
                    else "NOT_IN_CAPTURE"
                ),
                "recorded_retroarch_binary": (
                    capture_device.get("retroarch_binary")
                    if capture_device is not None
                    else None
                ),
                "execution_context_matches": (
                    declared_profile_matches_capture_snapshot
                ),
                "results": results,
            }
        )

    device_order = [device["device_id"] for device in devices]
    if device_order != sorted(device_order) or len(set(device_order)) != len(
        device_order
    ):
        raise DeviceRuntimeEvidenceError("current physical device order is ambiguous")
    if len(device_order) != EXPECTED_DEVICE_COUNT:
        raise DeviceRuntimeEvidenceError("current physical device roster is incomplete")
    status_counts = {status: 0 for status in sorted(LOAD_RESULTS)}
    for device in devices:
        row_core_ids = [result["core_id"] for result in device["results"]]
        if row_core_ids != core_ids:
            raise DeviceRuntimeEvidenceError(
                f"current projection is incomplete for {device['device_id']}"
            )
        for result in device["results"]:
            status_counts[result["load_result"]] += 1

    projection: dict[str, Any] = {
        "schema_version": 1,
        "projection_id": "current-canonical-artifact-runtime-v1",
        "validation_scope": "physical-device-artifact-load-only",
        "local_only": True,
        "publication": "disabled",
        "core_order": core_ids,
        "device_order": device_order,
        "status_counts": status_counts,
        "runtime_context_provenance": {
            "legacy_observed_fields": ["observed_retroarch_binary_label"],
            "legacy_observation_scope": "RETROARCH_BINARY_NAME_ONLY",
            "declared_context_status": DECLARED_CONTEXT_STATUS,
            "binary_name_to_declared_frontend_binding": "NOT_ESTABLISHED",
            "load_result_applicability": "EXACT_PHYSICAL_DEVICE_AND_ARTIFACT_SHA256",
            "caveat": RUNTIME_CONTEXT_CAVEAT,
        },
        "capture": {
            "path": capture_relative_path,
            "file_sha256": _sha256_bytes(capture_raw),
            "capture_id": capture["capture_id"],
            "content_sha256": capture["content_sha256"],
        },
        "current_sources": {
            "device_runtime_contracts": _snapshot(
                CURRENT_CONTRACTS_PATH.relative_to(ROOT).as_posix(), contracts_raw
            ),
            "execution_profiles": _snapshot(
                CURRENT_PROFILES_PATH.relative_to(ROOT).as_posix(), profiles_raw
            ),
            "core_builds": _snapshot(
                CURRENT_CATALOG_PATH.relative_to(ROOT).as_posix(), catalog_raw
            ),
            "evidence_indexes": _evidence_set_snapshot(evidence_hashes),
        },
        "devices": devices,
        "families": aggregate_families(devices),
    }
    projection["content_sha256"] = _document_content_sha256(projection)
    return projection


def project_current(
    *, repo_root: Path = ROOT, capture_path: Path = V2_CAPTURE_PATH
) -> dict[str, Any]:
    """Backward-compatible name for the public physical-device projector."""

    return project_current_physical_devices(
        repo_root=repo_root, capture_path=capture_path
    )


def _write_generated(path: Path, document: Mapping[str, Any]) -> None:
    path.write_text(_render_json(document), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate = subparsers.add_parser(
        "migrate", help="render the deterministic v1-to-v2 migration"
    )
    mode = migrate.add_mutually_exclusive_group()
    mode.add_argument(
        "--write", action="store_true", help="write the canonical v2 file"
    )
    mode.add_argument(
        "--check", action="store_true", help="verify the checked-in v2 bytes"
    )
    validate = subparsers.add_parser(
        "validate", help="strictly validate one v2 capture"
    )
    validate.add_argument("--path", type=Path, default=V2_CAPTURE_PATH)
    project = subparsers.add_parser(
        "project", help="project current canonical artifacts onto physical devices"
    )
    project.add_argument("--capture", type=Path, default=V2_CAPTURE_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "migrate":
            document = build_migration(ROOT)
            rendered = _render_json(document)
            if args.write:
                _write_generated(V2_CAPTURE_PATH, document)
                print(
                    json.dumps(
                        {
                            "path": V2_CAPTURE_PATH.relative_to(ROOT).as_posix(),
                            "file_sha256": _sha256_bytes(rendered.encode("utf-8")),
                            "content_sha256": document["content_sha256"],
                        },
                        sort_keys=True,
                    )
                )
                return 0
            if args.check:
                try:
                    actual = V2_CAPTURE_PATH.read_text(encoding="utf-8")
                except OSError as exc:
                    raise DeviceRuntimeEvidenceError(
                        f"checked-in v2 capture is not readable: {exc}"
                    ) from exc
                if actual != rendered:
                    raise DeviceRuntimeEvidenceError(
                        "checked-in v2 capture differs from migration output"
                    )
                print("device runtime v2 migration is current")
                return 0
            sys.stdout.write(rendered)
            return 0
        if args.command == "validate":
            summary = validate_capture(
                _read_json(args.path, "v2 device runtime capture")[0],
                repo_root=ROOT,
            )
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        if args.command == "project":
            sys.stdout.write(
                _render_json(project_current(repo_root=ROOT, capture_path=args.capture))
            )
            return 0
    except DeviceRuntimeEvidenceError as exc:
        print(f"device runtime evidence error: {exc}", file=sys.stderr)
        return 1
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
