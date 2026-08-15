"""Versioned, fail-closed local host build execution profiles."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .errors import RunnerProfileError


HOST_EXECUTION_PROFILE_PATH = Path("manifests/host-build-execution-profiles.json")
HOST_EXECUTION_PROFILE_SCHEMA_PATH = Path(
    "manifests/host-build-execution-profiles.schema.json"
)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
LOCAL_SELECTORS = frozenset({"local", "github-actions-sim"})
EXPECTED_RUNNERS = {
    "local": {
        "profile": "local",
        "mode": "native",
        "backend": "local-docker",
    },
    "github-actions-sim": {
        "profile": "github-actions",
        "mode": "simulated",
        "backend": "local-docker",
    },
}


def _canonical_content_sha256(value: dict) -> str:
    material = copy.deepcopy(value)
    material.pop("content_sha256", None)
    canonical = json.dumps(
        material, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise RunnerProfileError(f"{label} has an invalid exact key set")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise RunnerProfileError(f"{label} must be an exact lowercase SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class HostExecutionProfile:
    """Resolved immutable resource and evidence identity for one local runner."""

    selector: str
    profile_id: str
    execution_label: str
    runner_profile: str
    runner_mode: str
    runner_backend: str
    resource_class_id: str
    jobs: int
    cpu_quota: int
    memory_bytes: int
    memory_swap_bytes: int
    pids_limit: int
    matrix_parallelism: int
    pair_execution: str
    telemetry_contract: str
    admissible_build_drivers: tuple[str, ...]
    cache_classification: str
    cache_scope: str
    cache_identity: str
    cache_container_filesystem: str
    cache_source: str
    cache_compiler: str
    cache_image_layers: str
    cache_host_page_cache: str
    registry_path: str
    registry_file_sha256: str
    registry_content_sha256: str
    registry_schema_path: str
    registry_schema_file_sha256: str
    profile_content_sha256: str
    resource_class_content_sha256: str

    def reference(self) -> dict:
        return {
            "path": self.registry_path,
            "file_sha256": self.registry_file_sha256,
            "content_sha256": self.registry_content_sha256,
            "schema": {
                "path": self.registry_schema_path,
                "file_sha256": self.registry_schema_file_sha256,
            },
            "profile_id": self.profile_id,
            "profile_content_sha256": self.profile_content_sha256,
            "resource_class_id": self.resource_class_id,
            "resource_class_content_sha256": self.resource_class_content_sha256,
        }

    def resources(self) -> dict:
        return {
            "jobs": self.jobs,
            "cpu_quota": self.cpu_quota,
            "memory_bytes": self.memory_bytes,
            "memory_swap_bytes": self.memory_swap_bytes,
            "pids_limit": self.pids_limit,
            "matrix_parallelism": self.matrix_parallelism,
            "pair_execution": self.pair_execution,
        }

    def cache(self) -> dict:
        return {
            "classification": self.cache_classification,
            "scope": self.cache_scope,
            "identity": self.cache_identity,
            "container_filesystem": self.cache_container_filesystem,
            "source": self.cache_source,
            "compiler": self.cache_compiler,
            "image_layers": self.cache_image_layers,
            "host_page_cache": self.cache_host_page_cache,
        }

    def runner_identity(self) -> dict:
        return {
            "profile": self.runner_profile,
            "mode": self.runner_mode,
            "backend": self.runner_backend,
        }


def _validate_resource_class(value: object) -> dict:
    resource = _exact_keys(
        value,
        {
            "jobs",
            "cpu_quota",
            "memory_bytes",
            "memory_swap_bytes",
            "pids_limit",
            "matrix_parallelism",
            "pair_execution",
            "telemetry_contract",
            "admissible_build_drivers",
            "cache",
            "content_sha256",
        },
        "host execution resource class",
    )
    expected_scalars = {
        "jobs": 8,
        "cpu_quota": 8,
        "memory_bytes": 4 * 1024**3,
        "memory_swap_bytes": 4 * 1024**3,
        "pids_limit": 1024,
        "matrix_parallelism": 1,
        "pair_execution": "selected-then-reproduction-sequential",
        "telemetry_contract": "host-build-telemetry-v1",
    }
    for key, expected in expected_scalars.items():
        if resource.get(key) != expected or (
            isinstance(expected, int) and type(resource.get(key)) is not int
        ):
            raise RunnerProfileError(
                f"host execution resource class {key} must be exactly {expected}"
            )
    if resource.get("admissible_build_drivers") != ["libretro-super"]:
        raise RunnerProfileError(
            "host execution resource class must initially admit only libretro-super"
        )
    cache = _exact_keys(
        resource.get("cache"),
        {
            "classification",
            "scope",
            "identity",
            "container_filesystem",
            "source",
            "compiler",
            "image_layers",
            "host_page_cache",
        },
        "host execution cache policy",
    )
    expected_cache = {
        "classification": "cold",
        "scope": "pipeline-source-build-and-compiler-state",
        "identity": "fresh-container-network-clone-no-restored-compiler-cache-v1",
        "container_filesystem": "fresh",
        "source": "fresh-network-clone",
        "compiler": "disabled",
        "image_layers": "preloaded-content-addressed-image",
        "host_page_cache": "uncontrolled",
    }
    if cache != expected_cache:
        raise RunnerProfileError("host execution cache policy is invalid")
    declared = _sha256(resource.get("content_sha256"), "resource class digest")
    if declared != _canonical_content_sha256(resource):
        raise RunnerProfileError("host execution resource class digest mismatch")
    return resource


def _validate_profile(value: object, selector: str) -> dict:
    profile = _exact_keys(
        value,
        {
            "runner_selector",
            "runner",
            "execution_label",
            "resource_class",
            "content_sha256",
        },
        f"{selector} host execution profile",
    )
    if profile.get("runner_selector") != selector:
        raise RunnerProfileError("host execution runner selector mismatch")
    runner = _exact_keys(
        profile.get("runner"), {"profile", "mode", "backend"}, "runner identity"
    )
    if runner != EXPECTED_RUNNERS[selector]:
        raise RunnerProfileError("host execution runner identity mismatch")
    expected_label = "host-local" if selector == "local" else "local-gha-sim"
    if profile.get("execution_label") != expected_label:
        raise RunnerProfileError("host execution label mismatch")
    if profile.get("resource_class") != "host-8c-4g-noswap-v1":
        raise RunnerProfileError("host execution resource class reference mismatch")
    declared = _sha256(profile.get("content_sha256"), "profile digest")
    if declared != _canonical_content_sha256(profile):
        raise RunnerProfileError("host execution profile digest mismatch")
    return profile


def resolve_host_execution_profile(
    selector: str,
    *,
    repository_root: Path,
    registry_path: Path | None = None,
    registry_schema_path: Path | None = None,
) -> HostExecutionProfile:
    """Resolve one exact local-host profile from one immutable byte snapshot."""

    if selector not in LOCAL_SELECTORS:
        raise RunnerProfileError(
            "native github-actions execution is outside the local host profile tranche"
        )
    if not isinstance(repository_root, Path) or not repository_root.is_absolute():
        raise RunnerProfileError("host execution repository root must be absolute")
    path = registry_path or repository_root / HOST_EXECUTION_PROFILE_PATH
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise RunnerProfileError("host execution profile registry must be a regular file")
    resolved_root = repository_root.resolve()
    resolved_path = path.resolve()
    try:
        relative = resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise RunnerProfileError(
            "host execution profile registry must be contained by the repository"
        ) from exc
    raw = path.read_bytes()
    registry_file_sha256 = hashlib.sha256(raw).hexdigest()
    if relative != HOST_EXECUTION_PROFILE_PATH:
        expected_snapshot = (
            Path(".local-e2e")
            / "store"
            / "host-execution-profiles"
            / "sha256"
            / registry_file_sha256[:2]
            / registry_file_sha256
        )
        if relative != expected_snapshot:
            raise RunnerProfileError(
                "host execution profile snapshot path is not canonical"
            )
    try:
        registry = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerProfileError(
            f"cannot load host execution profile registry: {exc}"
        ) from exc
    registry = _exact_keys(
        registry,
        {
            "$schema",
            "schema_file_sha256",
            "schema_version",
            "registry_id",
            "local_only",
            "publication",
            "selector_profiles",
            "resource_classes",
            "profiles",
            "content_sha256",
        },
        "host execution profile registry",
    )
    if (
        registry.get("$schema") != "host-build-execution-profiles.schema.json"
        or type(registry.get("schema_version")) is not int
        or registry.get("schema_version") != 1
        or registry.get("registry_id") != "host-build-execution-profiles-v1"
        or registry.get("local_only") is not True
        or registry.get("publication") != "disabled"
    ):
        raise RunnerProfileError("host execution profile registry header is invalid")
    declared_schema_digest = _sha256(
        registry.get("schema_file_sha256"), "host execution profile schema digest"
    )
    schema_path = (
        registry_schema_path
        or repository_root / HOST_EXECUTION_PROFILE_SCHEMA_PATH
    )
    if schema_path.is_symlink() or not schema_path.is_file():
        raise RunnerProfileError("host execution profile schema must be a regular file")
    try:
        schema_relative = schema_path.resolve().relative_to(resolved_root)
    except ValueError as exc:
        raise RunnerProfileError(
            "host execution profile schema must be contained by the repository"
        ) from exc
    schema_raw = schema_path.read_bytes()
    schema_file_sha256 = hashlib.sha256(schema_raw).hexdigest()
    if schema_file_sha256 != declared_schema_digest:
        raise RunnerProfileError("host execution profile schema digest mismatch")
    if schema_relative != HOST_EXECUTION_PROFILE_SCHEMA_PATH:
        expected_schema_snapshot = (
            Path(".local-e2e")
            / "store"
            / "schemas"
            / "sha256"
            / schema_file_sha256[:2]
            / schema_file_sha256
        )
        if schema_relative != expected_schema_snapshot:
            raise RunnerProfileError(
                "host execution profile schema snapshot path is not canonical"
            )
    try:
        schema_document = json.loads(schema_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RunnerProfileError(
            f"cannot load host execution profile schema: {exc}"
        ) from exc
    if not isinstance(schema_document, dict):
        raise RunnerProfileError("host execution profile schema is not an object")
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError

        Draft202012Validator.check_schema(schema_document)
        schema_errors = list(Draft202012Validator(schema_document).iter_errors(registry))
    except (ImportError, SchemaError) as exc:
        raise RunnerProfileError(
            "host execution profile schema validator is unavailable"
        ) from exc
    if schema_errors:
        raise RunnerProfileError(
            "host execution profile registry fails its bound JSON Schema"
        )
    selector_profiles = _exact_keys(
        registry.get("selector_profiles"),
        {"local", "github-actions-sim"},
        "host execution selector map",
    )
    expected_profile_ids = {
        "local": "local-host-8c-4g-v1",
        "github-actions-sim": "github-actions-sim-host-8c-4g-v1",
    }
    if selector_profiles != expected_profile_ids:
        raise RunnerProfileError("host execution selector map is invalid")
    resource_classes = _exact_keys(
        registry.get("resource_classes"),
        {"host-8c-4g-noswap-v1"},
        "host execution resource classes",
    )
    resource = _validate_resource_class(resource_classes["host-8c-4g-noswap-v1"])
    profiles = _exact_keys(
        registry.get("profiles"),
        set(expected_profile_ids.values()),
        "host execution profiles",
    )
    for profile_selector, profile_id in expected_profile_ids.items():
        _validate_profile(profiles[profile_id], profile_selector)
    declared_registry_digest = _sha256(
        registry.get("content_sha256"), "host execution registry digest"
    )
    if declared_registry_digest != _canonical_content_sha256(registry):
        raise RunnerProfileError("host execution profile registry digest mismatch")
    profile_id = selector_profiles[selector]
    profile = profiles[profile_id]
    cache = resource["cache"]
    runner = profile["runner"]
    return HostExecutionProfile(
        selector=selector,
        profile_id=profile_id,
        execution_label=profile["execution_label"],
        runner_profile=runner["profile"],
        runner_mode=runner["mode"],
        runner_backend=runner["backend"],
        resource_class_id=profile["resource_class"],
        jobs=resource["jobs"],
        cpu_quota=resource["cpu_quota"],
        memory_bytes=resource["memory_bytes"],
        memory_swap_bytes=resource["memory_swap_bytes"],
        pids_limit=resource["pids_limit"],
        matrix_parallelism=resource["matrix_parallelism"],
        pair_execution=resource["pair_execution"],
        telemetry_contract=resource["telemetry_contract"],
        admissible_build_drivers=tuple(resource["admissible_build_drivers"]),
        cache_classification=cache["classification"],
        cache_scope=cache["scope"],
        cache_identity=cache["identity"],
        cache_container_filesystem=cache["container_filesystem"],
        cache_source=cache["source"],
        cache_compiler=cache["compiler"],
        cache_image_layers=cache["image_layers"],
        cache_host_page_cache=cache["host_page_cache"],
        registry_path=relative.as_posix(),
        registry_file_sha256=registry_file_sha256,
        registry_content_sha256=declared_registry_digest,
        registry_schema_path=schema_relative.as_posix(),
        registry_schema_file_sha256=schema_file_sha256,
        profile_content_sha256=profile["content_sha256"],
        resource_class_content_sha256=resource["content_sha256"],
    )


__all__ = [
    "HOST_EXECUTION_PROFILE_PATH",
    "HOST_EXECUTION_PROFILE_SCHEMA_PATH",
    "HostExecutionProfile",
    "resolve_host_execution_profile",
]
