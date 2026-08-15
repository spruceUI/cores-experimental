"""Verified pipeline inputs, policy admission, toolchains, and recipe snapshots.

The launcher remains the composition root. Global dependencies are captured in
a filtered call-time service record so legacy wrappers and monkeypatch seams
remain dynamic without introducing a reverse import.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import Any, Protocol

from .policy import CommitBlacklist, CommitPolicyReport
from .runtime import HostExecutionProfile


class _PinValidationContext(Protocol):
    """Read-once evidence caches supplied by the launcher composition root."""

    log_proofs: dict[tuple[str, str, str, str], tuple[bool, ...]]
    pinned_packages: set[tuple[str, str, str, str, int]]
    verified_bytes: dict[tuple[str, str], bytes]


@dataclass(frozen=True, slots=True)
class PipelineInputServices:
    """Call-time namespace required by this pipeline domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "PipelineInputServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"missing pipeline services: {names}")
        return cls(
            MappingProxyType(
                {name: namespace[name] for name in _REQUIRED_BINDINGS}
            )
        )


def required_binding_names() -> frozenset[str]:
    """Return the exact launcher bindings consumed by this leaf."""

    return _REQUIRED_BINDINGS


_REQUIRED_BINDINGS = frozenset(
    {
        'AGGREGATE_WORKFLOW_GLOBS',
        'DEFAULT_STORE',
        'EXACT_SOURCE_NATIVE_CORE_IDS',
        'HOST_EXECUTION_PROFILE_PATH',
        'HOST_EXECUTION_PROFILE_SCHEMA_PATH',
        'ModuleType',
        'NON_CORE_WORKFLOWS',
        'Path',
        'PipelineError',
        'ROOT',
        'RunnerProfileError',
        'SHA256_RE',
        'TELEMETRY_SCHEMA_PATH',
        'TOOLCHAIN_LOCK_SCHEMA_REF',
        'TOOL_WRAPPER_SOURCE',
        'UNIT_RUNNER_COMPILE_ARGUMENTS',
        'UNIT_RUNNER_SOURCE',
        '__file__',
        '_foundation_manifest_lock',
        '_foundation_manifest_reference_path',
        '_host_store_reference',
        '_immutable_canonical_store_path',
        '_immutable_e2e_content_sha256',
        '_immutable_golden_content_sha256',
        '_immutable_host_reproduction_content_sha256',
        '_immutable_lexical_path',
        '_immutable_pin_set_content_sha256',
        '_immutable_release_content_sha256',
        '_immutable_require_canonical_store_entry',
        '_immutable_selection_content_sha256',
        '_immutable_snapshot_json_file',
        '_immutable_store_bytes',
        '_immutable_store_file',
        '_immutable_toolchain_lock_content_sha256',
        '_immutable_verified_file_bytes',
        '_immutable_verified_json_object',
        '_immutable_verified_utf8_text',
        '_load_catalog_commit_blacklist',
        '_require_catalog_cores_eligible',
        '_require_golden_sources_eligible',
        '_require_pin_sources_eligible',
        '_require_source_commits_eligible',
        'build_host_execution_contract',
        'canonical_store_path',
        'commit_blacklist_reference_is_well_formed',
        'copy',
        'json',
        'load_catalog_toolchain_lock',
        'load_toolchain_archive_validator',
        'metadata_replacement_contract_is_well_formed',
        'pipeline_source_bundle_is_well_formed',
        'recorded_build_contract',
        'require_manifest_reference_path',
        'resolve_host_execution_profile',
        'run',
        'safe_child',
        'sha256_bytes',
        'sha256_file',
        'store_bytes',
        'store_file',
        'toolchain_lock_content_sha256',
        'tuning_candidate_recipe_identity',
        'validate_host_execution_contract',
        'validated_tuning_candidate_shape',
        'verified_file_bytes',
    }
)


def verified_file_bytes(
    path: Path,
    expected_sha256: str,
    label: str,
    validation_context: _PinValidationContext | None = None,
    *,
    services: PipelineInputServices,
) -> bytes:
    return services['_immutable_verified_file_bytes'](
        path,
        expected_sha256,
        label,
        validation_context,
        hash_bytes=services['sha256_bytes'],
    )


def verified_json_object(
    path: Path,
    expected_sha256: str,
    label: str,
    validation_context: _PinValidationContext | None = None,
    *,
    services: PipelineInputServices,
) -> dict:
    return services['_immutable_verified_json_object'](
        path,
        expected_sha256,
        label,
        validation_context,
        read_verified=services['verified_file_bytes'],
    )


def snapshot_json_file(
    path: Path,
    label: str,
    validation_context: _PinValidationContext | None = None,
    *,
    services: PipelineInputServices,
) -> tuple[dict, str]:
    return services['_immutable_snapshot_json_file'](
        path,
        label,
        validation_context,
        hash_bytes=services['sha256_bytes'],
    )


def verified_utf8_text(
    path: Path,
    expected_sha256: str,
    label: str,
    validation_context: _PinValidationContext | None = None,
    *,
    services: PipelineInputServices,
) -> str:
    return services['_immutable_verified_utf8_text'](
        path,
        expected_sha256,
        label,
        validation_context,
        read_verified=services['verified_file_bytes'],
    )


@contextmanager
def manifest_lock(path: Path, *, services: PipelineInputServices):
    with services['_foundation_manifest_lock'](path, services['ROOT']):
        yield


def require_manifest_reference_path(
    reference: dict,
    allowed_root: Path,
    label: str,
    *,
    services: PipelineInputServices,
) -> Path:
    return services['_foundation_manifest_reference_path'](
        reference,
        allowed_root,
        label,
        services['ROOT'],
    )


def require_lexical_repository_path(
    path: Path,
    allowed_root: Path,
    label: str,
    *,
    services: PipelineInputServices,
) -> Path:
    """Validate an operator path before resolving any symlink component."""

    relative = services['_immutable_lexical_path'](path, services['ROOT'], label)
    return services['require_manifest_reference_path'](
        {"path": relative},
        allowed_root,
        label,
    )


def load_catalog_commit_blacklist(
    catalog: dict,
    *,
    services: PipelineInputServices,
) -> tuple[CommitBlacklist, Path]:
    return services['_load_catalog_commit_blacklist'](catalog, services['ROOT'])


def require_source_commits_eligible(
    catalog: dict,
    sources: Iterable[tuple[object, object]],
    *,
    services: PipelineInputServices,
) -> list[CommitPolicyReport]:
    return services['_require_source_commits_eligible'](catalog, sources, services['ROOT'])


def require_catalog_cores_eligible(catalog: dict, core_ids: Iterable[str], *, services: PipelineInputServices) -> None:
    services['_require_catalog_cores_eligible'](catalog, core_ids, services['ROOT'])


def require_pin_sources_eligible(catalog: dict, pin: dict, *, services: PipelineInputServices) -> None:
    services['_require_pin_sources_eligible'](catalog, pin, services['ROOT'])


def require_golden_sources_eligible(catalog: dict, golden: dict, *, services: PipelineInputServices) -> None:
    services['_require_golden_sources_eligible'](catalog, golden, services['ROOT'])


def toolchain_lock_content_sha256(document: dict, *, services: PipelineInputServices) -> str:
    return services['_immutable_toolchain_lock_content_sha256'](
        document,
        hash_bytes=services['sha256_bytes'],
    )


def load_toolchain_archive_validator(path: Path, source: bytes, *, services: PipelineInputServices) -> ModuleType:
    """Execute the exact validator bytes already approved by the catalog."""

    module = services['ModuleType']("cores_toolchain_archive")
    module.__file__ = str(path)
    module.__package__ = ""
    try:
        code = compile(source, str(path), "exec", dont_inherit=True)
        exec(code, module.__dict__)
    except Exception as exc:
        raise services['PipelineError'](f"cannot load toolchain archive validator: {exc}") from exc
    return module


def load_catalog_toolchain_lock(catalog: dict, *, services: PipelineInputServices) -> tuple[dict, Path, Path]:
    reference = catalog.get("toolchain_lock")
    if not isinstance(reference, dict) or set(reference) != {
        "path",
        "schema_version",
        "lock_id",
        "file_sha256",
        "content_sha256",
    }:
        raise services['PipelineError']("toolchain_lock reference has an unexpected shape")
    if reference.get("path") != "pins/toolchains/local-cache-v1.json":
        raise services['PipelineError']("toolchain_lock path must be the exact local-cache-v1 lock")
    if type(reference.get("schema_version")) is not int or reference["schema_version"] != 1:
        raise services['PipelineError']("toolchain_lock schema_version must be the exact integer 1")
    if reference.get("lock_id") != "local-cache-v1":
        raise services['PipelineError']("toolchain_lock lock_id must be local-cache-v1")
    for field in ("file_sha256", "content_sha256"):
        value = reference.get(field)
        if not isinstance(value, str) or not services['SHA256_RE'].fullmatch(value):
            raise services['PipelineError'](f"toolchain_lock {field} is invalid")
    validator_reference = catalog.get("toolchain_lock_validator")
    if (
        not isinstance(validator_reference, dict)
        or set(validator_reference) != {"path", "sha256"}
        or validator_reference.get("path") != "scripts/toolchain_archive.py"
        or not isinstance(validator_reference.get("sha256"), str)
        or not services['SHA256_RE'].fullmatch(validator_reference["sha256"])
    ):
        raise services['PipelineError']("toolchain_lock_validator reference is invalid")
    path = services['require_manifest_reference_path'](
        reference, services['ROOT'] / "pins" / "toolchains", "toolchain lock"
    )
    validator_path = services['require_manifest_reference_path'](
        validator_reference, services['ROOT'] / "scripts", "toolchain lock validator"
    )
    try:
        lock_source = path.read_bytes()
    except OSError as exc:
        raise services['PipelineError']("toolchain_lock file SHA256 does not match") from exc
    if not path.is_file() or services['sha256_bytes'](lock_source) != reference["file_sha256"]:
        raise services['PipelineError']("toolchain_lock file SHA256 does not match")
    try:
        validator_source = validator_path.read_bytes()
    except OSError as exc:
        raise services['PipelineError']("toolchain_lock_validator SHA256 does not match") from exc
    if (
        not validator_path.is_file()
        or services['sha256_bytes'](validator_source) != validator_reference["sha256"]
    ):
        raise services['PipelineError']("toolchain_lock_validator SHA256 does not match")
    validator = services['load_toolchain_archive_validator'](validator_path, validator_source)
    try:
        document = validator.strict_json_bytes(lock_source, str(path))
        if not isinstance(document, dict):
            raise validator.ToolchainArchiveError(
                f"lock must be a JSON object: {path}"
            )
        validator.validate_lock_document(document, repo_root=services['ROOT'])
    except validator.ToolchainArchiveError as exc:
        raise services['PipelineError'](f"toolchain lock is invalid: {exc}") from exc
    if set(document) != {
        "$schema",
        "schema_version",
        "lock_id",
        "local_only",
        "publication",
        "toolchains",
        "content_sha256",
    }:
        raise services['PipelineError']("toolchain lock has an unexpected top-level shape")
    if (
        document.get("$schema") != services['TOOLCHAIN_LOCK_SCHEMA_REF']
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != reference["schema_version"]
        or document.get("lock_id") != reference["lock_id"]
        or document.get("local_only") is not True
        or document.get("publication") != "disabled"
    ):
        raise services['PipelineError']("toolchain lock metadata does not match its catalog reference")
    if (
        document.get("content_sha256") != reference["content_sha256"]
        or document["content_sha256"] != services['toolchain_lock_content_sha256'](document)
    ):
        raise services['PipelineError']("toolchain lock content SHA256 does not match")
    return document, path, validator_path


def build_toolchain_key(spec: dict, arch: str, *, services: PipelineInputServices) -> str:
    """The toolchain-lock entry a build for this spec runs inside.

    direct-cargo cores build every device target inside the pinned Rust
    image (cargo-zigbuild carries the cross linkage); every other driver
    uses the target architecture's C cross image.
    """

    if spec.get("build", {}).get("driver") == "direct-cargo":
        return "rust"
    return arch


def expected_archive_provenance(catalog: dict, architecture: str, *, services: PipelineInputServices) -> dict:
    document, _, _ = services['load_catalog_toolchain_lock'](catalog)
    entry = document["toolchains"][architecture]
    archive = entry["archive"]
    return {
        "lock": services['copy'].deepcopy(catalog["toolchain_lock"]),
        "validator": services['copy'].deepcopy(catalog["toolchain_lock_validator"]),
        "architecture": architecture,
        "archive": {
            "filename": archive["filename"],
            "sha256": archive["sha256"],
            "size": archive["size"],
        },
    }


def golden_content_sha256(document: dict, *, services: PipelineInputServices) -> str:
    return services['_immutable_golden_content_sha256'](document, hash_bytes=services['sha256_bytes'])


def e2e_content_sha256(document: dict, *, services: PipelineInputServices) -> str:
    return services['_immutable_e2e_content_sha256'](document, hash_bytes=services['sha256_bytes'])


def provenance_identity_sha256(record: dict, *, services: PipelineInputServices) -> str:
    source = record.get("source", {})
    recipe = record.get("recipe", {})
    toolchain = record.get("toolchain", {})
    material = {
        "core_id": record.get("core_id"),
        "architecture": record.get("architecture"),
        "source": {
            "resolved_commit": source.get("resolved_commit"),
            "tree": source.get("tree"),
            "submodules": source.get("submodules", []),
        },
        "recipe": {
            "core_spec_sha256": recipe.get("core_spec_sha256"),
            "pipeline_sha256": recipe.get("pipeline_sha256"),
            "workflow_sha256": recipe.get("workflow_sha256"),
        },
        "toolchain": {
            "resolved_image_id": toolchain.get("resolved_image_id"),
            "dockerfile_sha256": toolchain.get("dockerfile_sha256"),
            "resolver_digests": toolchain.get("resolver_digests"),
        },
        "artifact_sha256": record.get("artifact", {}).get("sha256"),
        "metadata_sha256": record.get("metadata", {}).get("sha256"),
    }
    archive_provenance = toolchain.get("archive_provenance")
    pipeline_bundle = recipe.get("pipeline_bundle")
    if services['pipeline_source_bundle_is_well_formed'](pipeline_bundle):
        material["recipe"]["pipeline_bundle"] = pipeline_bundle
    host_execution = recipe.get("host_execution")
    if isinstance(host_execution, dict):
        material["recipe"]["host_execution"] = host_execution
    commit_blacklist = recipe.get("commit_blacklist")
    if services['commit_blacklist_reference_is_well_formed'](commit_blacklist):
        material["recipe"]["commit_blacklist"] = commit_blacklist
    if archive_provenance is not None:
        material["provenance_version"] = 2
        material["toolchain"]["archive_provenance"] = archive_provenance
    if "core_group" in record:
        material["core_group"] = record.get("core_group")
    if "tuning_candidate" in record:
        material["tuning_candidate"] = record.get("tuning_candidate")
    if "source_candidate" in record:
        material["source_candidate"] = record.get("source_candidate")
    if "chipset_tuning" in recipe:
        material["recipe"]["chipset_tuning"] = recipe.get("chipset_tuning")
    build = record.get("build", {})
    if isinstance(build, dict) and (
        build.get("driver") == "direct-cmake"
        or "make_variables" in build
        or "git_version" in build
        or "generated_source" in build
        or "recipe_profile" in build
        or (
            record.get("core_id") in services['EXACT_SOURCE_NATIVE_CORE_IDS']
            and services['pipeline_source_bundle_is_well_formed'](
                recipe.get("pipeline_bundle")
            )
        )
    ):
        material["build"] = services['recorded_build_contract'](build)
    elif isinstance(build, dict) and "source_date_epoch" in build:
        material["build"] = {"source_date_epoch": build["source_date_epoch"]}
    return services['sha256_bytes'](
        services['json'].dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def selection_content_sha256(selection: dict, *, services: PipelineInputServices) -> str:
    return services['_immutable_selection_content_sha256'](
        selection,
        hash_bytes=services['sha256_bytes'],
    )


def host_reproduction_content_sha256(proof: Mapping[str, object], *, services: PipelineInputServices) -> str:
    return services['_immutable_host_reproduction_content_sha256'](
        proof,
        hash_bytes=services['sha256_bytes'],
    )


def pin_set_content_sha256(document: dict, *, services: PipelineInputServices) -> str:
    return services['_immutable_pin_set_content_sha256'](document, hash_bytes=services['sha256_bytes'])


def release_content_sha256(document: dict, *, services: PipelineInputServices) -> str:
    return services['_immutable_release_content_sha256'](document, hash_bytes=services['sha256_bytes'])


def store_bytes(store_root: Path, namespace: str, content: bytes, *, services: PipelineInputServices) -> tuple[Path, str]:
    return services['_immutable_store_bytes'](
        store_root,
        namespace,
        content,
        hash_bytes=services['sha256_bytes'],
        hash_file=services['sha256_file'],
        reference_path=services['_foundation_manifest_reference_path'],
    )


def store_file(store_root: Path, namespace: str, source: Path, *, services: PipelineInputServices) -> tuple[Path, str]:
    return services['_immutable_store_file'](
        store_root,
        namespace,
        source,
        store=services['store_bytes'],
    )


def _host_store_reference(path: Path, digest: str, *, services: PipelineInputServices) -> dict:
    return {
        "path": path.relative_to(services['ROOT']).as_posix(),
        "file_sha256": digest,
    }


def prepare_host_execution_context(
    selector: str,
    *,
    services: PipelineInputServices,
) -> tuple[HostExecutionProfile, dict, dict]:
    """Freeze every deterministic local-host execution input in the CAS."""

    try:
        canonical = services['resolve_host_execution_profile'](selector, repository_root=services['ROOT'])
    except services['RunnerProfileError'] as exc:
        raise services['PipelineError'](str(exc)) from exc
    registry_path, registry_sha256 = services['store_file'](
        services['DEFAULT_STORE'],
        "host-execution-profiles",
        services['ROOT'] / services['HOST_EXECUTION_PROFILE_PATH'],
    )
    profile_schema_path, profile_schema_sha256 = services['store_file'](
        services['DEFAULT_STORE'],
        "schemas",
        services['ROOT'] / services['HOST_EXECUTION_PROFILE_SCHEMA_PATH'],
    )
    telemetry_schema_path, telemetry_schema_sha256 = services['store_file'](
        services['DEFAULT_STORE'],
        "schemas",
        services['ROOT'] / services['TELEMETRY_SCHEMA_PATH'],
    )
    unit_runner_path, unit_runner_sha256 = services['store_file'](
        services['DEFAULT_STORE'],
        "host-build-tools",
        services['ROOT'] / services['UNIT_RUNNER_SOURCE'],
    )
    wrapper_path, wrapper_sha256 = services['store_file'](
        services['DEFAULT_STORE'],
        "host-build-tools",
        services['ROOT'] / services['TOOL_WRAPPER_SOURCE'],
    )
    try:
        profile = services['resolve_host_execution_profile'](
            selector,
            repository_root=services['ROOT'],
            registry_path=registry_path,
            registry_schema_path=profile_schema_path,
        )
    except services['RunnerProfileError'] as exc:
        raise services['PipelineError'](str(exc)) from exc
    if (
        profile.profile_content_sha256 != canonical.profile_content_sha256
        or profile.resource_class_content_sha256
        != canonical.resource_class_content_sha256
        or profile.resources() != canonical.resources()
        or profile.runner_identity() != canonical.runner_identity()
    ):
        raise services['PipelineError']("immutable host execution snapshot changed during capture")
    instrumentation = {
        "schema_version": 1,
        "tool_wrapper": services['_host_store_reference'](wrapper_path, wrapper_sha256),
        "unit_runner_source": services['_host_store_reference'](
            unit_runner_path, unit_runner_sha256
        ),
        "unit_runner_compile": {
            "compiler_command": "cc",
            "arguments": list(services['UNIT_RUNNER_COMPILE_ARGUMENTS']),
        },
    }
    telemetry_schema = services['_host_store_reference'](
        telemetry_schema_path, telemetry_schema_sha256
    )
    contract = services['build_host_execution_contract'](
        profile=profile,
        instrumentation=instrumentation,
        telemetry_schema=telemetry_schema,
        repository_root=services['ROOT'],
    )
    if profile.registry_file_sha256 != registry_sha256 or (
        profile.registry_schema_file_sha256 != profile_schema_sha256
    ):
        raise services['PipelineError']("immutable host execution profile reference is inconsistent")
    return profile, contract, telemetry_schema


def canonical_store_path(namespace: str, digest: str, *, services: PipelineInputServices) -> Path:
    return services['_immutable_canonical_store_path'](services['DEFAULT_STORE'], namespace, digest)


def require_canonical_store_entry(entry: dict, namespace: str, label: str, *, services: PipelineInputServices) -> Path:
    return services['_immutable_require_canonical_store_entry'](
        entry,
        namespace,
        label,
        repository_root=services['ROOT'],
        store_root=services['DEFAULT_STORE'],
        canonical_path=services['canonical_store_path'],
    )


def recipe_snapshot(record: dict, *, services: PipelineInputServices) -> bytes:
    recipe = record["recipe"]
    toolchain = record["toolchain"]
    build = record.get("build", {})
    is_direct_cmake = (
        isinstance(build, dict) and build.get("driver") == "direct-cmake"
    )
    tuning_candidate = record.get("tuning_candidate")
    if tuning_candidate is not None:
        tuning_candidate = services['validated_tuning_candidate_shape'](tuning_candidate)
        if recipe.get("chipset_tuning") != services['tuning_candidate_recipe_identity'](
            tuning_candidate
        ):
            raise services['PipelineError']("recipe snapshot tuning identity is inconsistent")
    paths = {
        recipe["catalog_path"],
        recipe["workflow"],
        str(services['Path'](services['__file__']).relative_to(services['ROOT'])),
        toolchain["dockerfile"],
    }
    if tuning_candidate is not None:
        paths.add(tuning_candidate["registry"]["path"])
    pipeline_bundle = recipe.get("pipeline_bundle")
    if pipeline_bundle is not None:
        if not services['pipeline_source_bundle_is_well_formed'](pipeline_bundle):
            raise services['PipelineError']("recipe snapshot pipeline bundle is invalid")
        if (
            pipeline_bundle["files"].get(str(services['Path'](services['__file__']).relative_to(services['ROOT'])))
            != recipe.get("pipeline_sha256")
        ):
            raise services['PipelineError']("recipe snapshot launcher digest is inconsistent")
        paths.update(pipeline_bundle["files"])
    commit_blacklist = recipe.get("commit_blacklist")
    if pipeline_bundle is not None and commit_blacklist is None:
        raise services['PipelineError'](
            "schema-v9 recipe snapshot requires commit blacklist provenance"
        )
    if commit_blacklist is not None:
        if not services['commit_blacklist_reference_is_well_formed'](commit_blacklist):
            raise services['PipelineError']("recipe snapshot commit blacklist is invalid")
        paths.add(commit_blacklist["path"])
    host_execution = recipe.get("host_execution")
    if host_execution is not None:
        host_execution = services['validate_host_execution_contract'](
            host_execution, repository_root=services['ROOT']
        )
        paths.update(
            {
                host_execution["instrumentation"]["tool_wrapper"]["path"],
                host_execution["instrumentation"]["unit_runner_source"]["path"],
                host_execution["telemetry_schema"]["path"],
            }
        )
    archive_provenance = toolchain.get("archive_provenance")
    if archive_provenance is not None:
        paths.add(archive_provenance["lock"]["path"])
        paths.add(archive_provenance["validator"]["path"])
    if is_direct_cmake:
        overlays = build.get("overlays")
        if not isinstance(overlays, list):
            raise services['PipelineError']("direct-CMake recipe snapshot overlays are invalid")
        for overlay in overlays:
            if not isinstance(overlay, dict) or not isinstance(
                overlay.get("patch_path"), str
            ):
                raise services['PipelineError']("direct-CMake recipe snapshot overlay is invalid")
            paths.add(overlay["patch_path"])
    metadata_replacement = build.get("metadata_replacement")
    if metadata_replacement is not None:
        if not services['metadata_replacement_contract_is_well_formed'](
            metadata_replacement
        ):
            raise services['PipelineError'](
                "recipe snapshot metadata replacement contract is invalid"
            )
        paths.add(metadata_replacement["path"])
    files = {}
    for relative in sorted(paths):
        path = services['safe_child'](services['ROOT'], relative, "recipe snapshot path")
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise services['PipelineError'](
                f"recipe snapshot file is not readable UTF-8: {relative}: {exc}"
            ) from exc
        files[relative] = {
            "sha256": services['sha256_bytes'](raw),
            "text": text,
        }
    snapshot_toolchain = {
        "image_id": toolchain["resolved_image_id"],
        "dockerfile": toolchain["dockerfile"],
        "dockerfile_sha256": toolchain["dockerfile_sha256"],
        "resolver_digests": toolchain["resolver_digests"],
    }
    if archive_provenance is not None:
        snapshot_toolchain["archive_provenance"] = archive_provenance
    has_compile_definition_contract = (
        isinstance(build, dict) and "compile_definitions" in build
    )
    has_make_variable_contract = (
        isinstance(build, dict) and "make_variables" in build
    )
    has_git_version_contract = (
        isinstance(build, dict) and "git_version" in build
    )
    has_generated_source_contract = (
        isinstance(build, dict) and "generated_source" in build
    )
    has_recipe_profile_contract = (
        isinstance(build, dict) and "recipe_profile" in build
    )
    has_source_date_epoch_contract = (
        isinstance(build, dict) and "source_date_epoch" in build
    )
    snapshot = {
        "schema_version": (
            12
            if host_execution is not None
            else 11
            if tuning_candidate is not None
            else 10
            if has_generated_source_contract
            else 9
            if pipeline_bundle is not None
            else 8
            if has_git_version_contract and has_make_variable_contract
            else 7
            if has_git_version_contract
            else 6
            if has_make_variable_contract
            else 5
            if is_direct_cmake
            else 4
            if has_source_date_epoch_contract
            else 3
            if has_compile_definition_contract
            else (2 if archive_provenance is not None else 1)
        ),
        "core_id": record["core_id"],
        "architecture": record["architecture"],
        "source": record["source"],
        "recipe": recipe,
        "toolchain": snapshot_toolchain,
        "files": files,
    }
    if tuning_candidate is not None:
        snapshot["tuning_candidate"] = services['copy'].deepcopy(tuning_candidate)
    if host_execution is not None:
        snapshot["host_execution"] = services['copy'].deepcopy(host_execution)
    if (
        is_direct_cmake
        or has_compile_definition_contract
        or has_make_variable_contract
        or has_git_version_contract
        or has_generated_source_contract
        or has_recipe_profile_contract
        or has_source_date_epoch_contract
        or tuning_candidate is not None
    ):
        snapshot["build"] = services['recorded_build_contract'](build)
    return (services['json'].dumps(snapshot, indent=2, sort_keys=True) + "\n").encode()


def git_head(path: Path, *, services: PipelineInputServices) -> str:
    return services['run'](["git", "rev-parse", "HEAD"], cwd=path).stdout.strip()


def core_workflows(*, services: PipelineInputServices) -> dict[str, Path]:
    workflow_dir = services['ROOT'] / ".github" / "workflows"
    result: dict[str, Path] = {}
    for path in sorted(workflow_dir.glob("build-*.yml")):
        if path.name in services['NON_CORE_WORKFLOWS'] or any(
            path.match(pattern)
            for pattern in services['AGGREGATE_WORKFLOW_GLOBS']
        ):
            continue
        core_id = path.stem.removeprefix("build-")
        if core_id in result:
            raise services['PipelineError'](f"duplicate workflow core ID: {core_id}")
        result[core_id] = path
    if not result:
        raise services['PipelineError']("no core workflows found")
    return result
