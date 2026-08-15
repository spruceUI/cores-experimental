"""Live build-record and E2E evidence validation.

The launcher remains the composition root. Global dependencies are captured in
a filtered call-time service record so legacy wrappers and monkeypatch seams
remain dynamic without introducing a reverse import.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .source_candidate import SourceCandidateContractProjection


class _PinValidationContext(Protocol):
    """Read-once evidence caches supplied by the launcher composition root."""

    log_proofs: dict[tuple[str, str, str, str], tuple[bool, ...]]
    pinned_packages: set[tuple[str, str, str, str, int]]
    verified_bytes: dict[tuple[str, str], bytes]


@dataclass(frozen=True, slots=True)
class EvidenceValidationServices:
    """Call-time namespace required by this evidence domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "EvidenceValidationServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(
                f"missing evidence validation services: {names}"
            )
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
        'ARCH_LAYOUT',
        'COMBINED_NATIVE_MAKE_CORE_IDS',
        'DEFAULT_CATALOG',
        'DEFAULT_RUNS',
        'EXACT_SOURCE_NATIVE_CORE_IDS',
        'FBNEO_CORE_ID',
        'FREEINTV_CORE_ID',
        'HOST_REPRODUCTION_SCOPE',
        'MAME2003_PLUS_CORE_ID',
        'Mapping',
        'NATIVE_GIT_VERSION_DERIVATION',
        'PICODRIVE_CORE_ID',
        'Path',
        'PipelineError',
        'ROOT',
        'RunnerProfileError',
        'SHA1_RE',
        'SOURCE_CANDIDATE_BUILD_RECORD_KEYS',
        'SOURCE_CANDIDATE_E2E_KEYS',
        'TUNED_BUILD_RECORD_KEYS',
        'TUNED_E2E_KEYS',
        'VEMULATOR_CORE_ID',
        '_PinValidationContext',
        '__file__',
        '_group_execution_tuning',
        '_recorded_source_matches_source_candidate_projection',
        '_registered_core_log_contract_proves',
        '_require_public_ordinary_catalog',
        '_source_candidate_contract_build_for_guard',
        '_source_candidate_contract_source_for_guard',
        '_source_candidate_contract_spec',
        '_stored_reference_is_well_formed',
        '_validate_artifact_bytes',
        '_validate_build_record_identity',
        '_validate_e2e_evidence',
        'active_promotion_e2e_scope',
        'apply_artifact_dependency_policy',
        'apply_group_output_expectations',
        'base_runner_evidence',
        'build_source_date_epoch_matches',
        'build_toolchain_key',
        'chipset_tuning_log_proves_contract',
        'combined_git_version_make_golden_build_contract_is_well_formed',
        'compile_definitions_for_target',
        'compile_log_proves_definitions',
        'copy',
        'core_81_golden_build_contract_is_well_formed',
        'core_log_contract_for',
        'core_spec_sha256',
        'decode_json_object',
        'direct_cmake_log_proves_contract',
        'e2e_content_sha256',
        'expected_archive_provenance',
        'fbneo_golden_source_is_well_formed',
        'freeintv_golden_build_contract_is_well_formed',
        'freeintv_golden_source_is_well_formed',
        'git_version_golden_build_contract_is_well_formed',
        'git_version_log_proves_contract',
        'group_execution_spec',
        'group_source_candidate_contract_projection',
        'host_reproduction_build_identity',
        'host_reproduction_content_sha256',
        'host_reproduction_output_identity',
        'io',
        'json',
        'load_catalog_with_sha256',
        'load_json_with_sha256',
        'make_variable_contract_name',
        'make_variable_golden_build_contract_is_well_formed',
        'make_variable_log_proves_contract',
        'mame2003_plus_golden_source_is_well_formed',
        'metadata_matches_replacement',
        'metadata_replacement_log_proves_contract',
        'normalized_build_contract',
        'picodrive_golden_build_contract_is_well_formed',
        'picodrive_golden_source_is_well_formed',
        'pinned_group_execution_source',
        'pipeline_source_bundle',
        'recipe_snapshot',
        'recorded_build_contract',
        'require_canonical_store_entry',
        'require_contained',
        'require_host_execution_runner_coupling',
        'require_host_reproduction_equivalence',
        'require_lexical_repository_path',
        'require_selected_reproduction_runner_pair',
        'resolve_core_group_build_selection',
        'resolve_host_execution_profile',
        'runner_evidence_is_hardened',
        'runner_evidence_is_well_formed',
        'safe_child',
        'sha256_bytes',
        'sha256_file',
        'source_candidate_build_identity',
        'source_candidate_contract_context',
        'source_candidate_output_identity',
        'tuned_candidate_build_identity',
        'tuned_candidate_output_identity',
        'tuning_candidate_recipe_identity',
        'validate_bound_host_telemetry',
        'validate_catalog',
        'validate_host_execution_contract',
        'validate_job_count_log',
        'validate_sidecar_reference',
        'validated_embedded_source_candidate_shape',
        'validated_forbidden_needed_prefixes',
        'validated_generated_source',
        'validated_git_version',
        'validated_make_variables',
        'validated_metadata_replacement',
        'validated_recipe_profile',
        'validated_source_date_epoch',
        'validated_tuning_candidate_selection',
        'vemulator_golden_build_contract_is_well_formed',
        'vemulator_golden_source_is_well_formed',
        'verified_file_bytes',
        'verified_utf8_text',
        'zipfile',
    }
)


def _validate_build_record_identity(
    record: dict,
    record_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    execution_tuning: Mapping[str, object] | None = None,
    validation_context: _PinValidationContext | None = None,
    expected_catalog_file_sha256: str | None = None,
    authenticated_recipe_catalog_snapshot: Mapping[str, object] | None = None,
    authenticated_source_candidate_contract: tuple[
        dict, SourceCandidateContractProjection
    ]
    | None = None,
    services: EvidenceValidationServices,
) -> tuple[Path, Path, Path]:
    record_path = services['require_contained'](record_path, services['ROOT'] / ".local-e2e", "build record")
    if record.get("result") != "passed" or record.get("build_exit_code") != 0:
        raise services['PipelineError']("only a successful build record can be promoted")
    if not record.get("local_only") or record.get("publication") != "disabled":
        raise services['PipelineError']("build record is not marked local-only/publication-disabled")
    if type(record.get("schema_version")) is not int or record["schema_version"] != 2:
        raise services['PipelineError']("build record schema_version must be the exact integer 2")
    if "core_group" in record:
        raise services['PipelineError'](
            "core group build evidence is not supported by golden, pin, or release promotion"
        )
    if "tuning_candidate" in record or "chipset_tuning" in record.get("recipe", {}):
        raise services['PipelineError'](
            "tuned build evidence requires the separate promote-tuned-variant flow"
        )
    core_id = record.get("core_id")
    arch = record.get("architecture")
    if core_id not in catalog["cores"]:
        raise services['PipelineError']("build record core is not in the current catalog")
    spec = catalog["cores"][core_id]
    if arch not in spec["targets"]:
        raise services['PipelineError']("build record architecture is not enabled for its core")
    if authenticated_source_candidate_contract is None:
        source_candidate_contract_spec, source_candidate_projection = (
            services['source_candidate_contract_context'](
                catalog,
                core_id,
                catalog_path=catalog_path,
            )
        )
    else:
        source_candidate_contract_spec, source_candidate_projection = (
            authenticated_source_candidate_contract
        )
        services['_source_candidate_contract_spec'](
            core_id,
            spec,
            source_candidate_contract_spec,
            source_candidate_projection,
        )
    expected_compile_definitions = services['compile_definitions_for_target'](spec, arch)
    expected_make_variables = services['validated_make_variables'](
        source_candidate_contract_spec
    )
    expected_git_version = services['validated_git_version'](source_candidate_contract_spec)
    expected_generated_source = services['validated_generated_source'](
        source_candidate_contract_spec
    )
    expected_recipe_profile = services['validated_recipe_profile'](
        source_candidate_contract_spec
    )
    expected_metadata_replacement = services['validated_metadata_replacement'](
        source_candidate_contract_spec
    )
    expected_source_date_epoch = services['validated_source_date_epoch'](spec)
    expected_build_contract = services['normalized_build_contract'](
        spec,
        arch,
        core_id=core_id,
        source_candidate_contract_spec=(
            source_candidate_contract_spec
            if source_candidate_projection is not None
            else None
        ),
        source_candidate_projection=source_candidate_projection,
    )

    recipe = record.get("recipe", {})
    catalog_path = services['require_contained'](catalog_path, services['ROOT'], "catalog")
    catalog_snapshot, catalog_file_sha256 = services['load_json_with_sha256'](catalog_path)
    recipe_catalog_snapshot = (
        catalog
        if authenticated_recipe_catalog_snapshot is None
        else authenticated_recipe_catalog_snapshot
    )
    if catalog_snapshot != recipe_catalog_snapshot or (
        expected_catalog_file_sha256 is not None
        and catalog_file_sha256 != expected_catalog_file_sha256
    ):
        raise services['PipelineError']("catalog changed after it was loaded for build validation")
    expected_recipe = {
        "catalog_path": str(catalog_path.relative_to(services['ROOT'])),
        "catalog_sha256": catalog_file_sha256,
        "core_id": core_id,
        "core_spec_sha256": services['core_spec_sha256'](spec),
        "pipeline_sha256": services['sha256_file'](services['Path'](services['__file__'])),
        "pipeline_bundle": services['pipeline_source_bundle'](),
        "commit_blacklist": services['copy'].deepcopy(catalog["commit_blacklist"]),
        "workflow": spec["workflow"],
        "workflow_sha256": services['sha256_file'](services['ROOT'] / spec["workflow"]),
    }
    for key, expected in expected_recipe.items():
        if recipe.get(key) != expected:
            raise services['PipelineError'](f"build record recipe identity mismatch: {key}")
    if "host_execution" in recipe:
        services['validate_host_execution_contract'](
            recipe.get("host_execution"), repository_root=services['ROOT']
        )
    if not services['SHA1_RE'].fullmatch(recipe.get("repository_head", "")):
        raise services['PipelineError']("build record repository head is not a full SHA")
    if not isinstance(recipe.get("repository_dirty"), bool):
        raise services['PipelineError']("build record repository dirty state is missing")

    source = record.get("source", {})
    for key, expected in spec["source"].items():
        # Submodule pins are {path, commit} while records capture the live
        # `git submodule status` shape; they are bound exactly below instead.
        if key == "submodules":
            continue
        if source.get(key) != expected:
            raise services['PipelineError'](f"build record source identity mismatch: {key}")
    if source.get("resolved_commit") != spec["source"]["commit"]:
        raise services['PipelineError']("resolved source does not match the requested commit")
    if source.get("resolved_url") != spec["source"]["url"]:
        raise services['PipelineError']("resolved source URL does not match the source pin")
    if not services['SHA1_RE'].fullmatch(source.get("tree", "")):
        raise services['PipelineError']("resolved source tree is not a full SHA")
    contract_source = services['_source_candidate_contract_source_for_guard'](
        source,
        source_candidate_projection,
    )
    contract_source_commit = spec["source"]["commit"]
    if source_candidate_projection is not None:
        contract_source_commit = source_candidate_projection.canonical_commit
    if (
        core_id == services['VEMULATOR_CORE_ID']
        and not services['vemulator_golden_source_is_well_formed'](core_id, contract_source)
    ):
        raise services['PipelineError'](
            "build record source does not match the exact VEmulator contract"
        )
    if (
        core_id == services['FREEINTV_CORE_ID']
        and not services['freeintv_golden_source_is_well_formed'](core_id, contract_source)
    ):
        raise services['PipelineError'](
            "build record source does not match the exact FreeIntv contract"
        )
    if (
        core_id == services['PICODRIVE_CORE_ID']
        and not services['picodrive_golden_source_is_well_formed'](core_id, contract_source)
    ):
        raise services['PipelineError'](
            "build record source does not match the exact Picodrive contract"
        )
    if (
        core_id == services['MAME2003_PLUS_CORE_ID']
        and not services['mame2003_plus_golden_source_is_well_formed'](
            core_id, contract_source
        )
    ):
        raise services['PipelineError'](
            "build record source does not match the exact MAME2003+ contract"
        )
    if (
        core_id == services['FBNEO_CORE_ID']
        and not services['fbneo_golden_source_is_well_formed'](core_id, contract_source)
    ):
        raise services['PipelineError'](
            "build record source does not match the exact FBNeo contract"
        )
    recorded_submodules = source.get("submodules", [])
    for submodule in recorded_submodules:
        if (
            submodule.get("state") != " "
            or not services['SHA1_RE'].fullmatch(submodule.get("commit", ""))
            or not submodule.get("path")
        ):
            raise services['PipelineError']("submodule state is not coherent with the pinned source")
    pinned_submodules = spec["source"].get("submodules")
    if pinned_submodules is not None and [
        {"path": submodule["path"], "commit": submodule["commit"]}
        for submodule in recorded_submodules
    ] != pinned_submodules:
        raise services['PipelineError']("recorded submodules do not match the pinned source submodules")
    if source_candidate_projection is not None and not (
        services['_recorded_source_matches_source_candidate_projection'](
            source,
            source_candidate_projection,
        )
    ):
        raise services['PipelineError'](
            "recorded source does not match authenticated source-candidate provenance"
        )

    toolchain = record.get("toolchain", {})
    expected_toolchain = catalog["toolchains"][services['build_toolchain_key'](spec, arch)]
    for key, expected in expected_toolchain.items():
        if toolchain.get(key) != expected:
            raise services['PipelineError'](f"build record toolchain identity mismatch: {key}")
    if toolchain.get("resolved_image_id") != expected_toolchain["image_id"]:
        raise services['PipelineError']("resolved toolchain image does not match the pin")
    if toolchain.get("archive_provenance") != services['expected_archive_provenance'](
        catalog, services['build_toolchain_key'](spec, arch)
    ):
        raise services['PipelineError']("build record archive provenance does not match the lock")
    if services['build_toolchain_key'](spec, arch) == "rust":
        # The Rust image carries no libretro-super checkout; a cargo record
        # must have captured NO resolver identity at all -- a value here
        # would mean the build ran in the wrong image.
        expected_absent_resolver = {"libretro_super_commit": None}
        for prefix in ("core_rules", "fetch_script", "build_script"):
            expected_absent_resolver[f"{prefix}_path"] = catalog["resolver"][
                f"{prefix}_path"
            ]
            expected_absent_resolver[f"{prefix}_sha256"] = None
        if (
            toolchain.get("libretro_super_commit") is not None
            or toolchain.get("resolver_digests") != expected_absent_resolver
        ):
            raise services['PipelineError'](
                "cargo build record captured resolver identity from the wrong image"
            )
    else:
        if toolchain.get("libretro_super_commit") != catalog["resolver"][
            "libretro_super_commit"
        ]:
            raise services['PipelineError']("build record resolver commit does not match the catalog")
        if toolchain.get("resolver_digests") != catalog["resolver"]:
            raise services['PipelineError']("build record resolver digests do not match the catalog")
    if not toolchain.get("compiler") or toolchain.get("sysroot") is None:
        raise services['PipelineError']("build record toolchain fingerprint is incomplete")

    artifact = record.get("artifact", {})
    if artifact.get("path") != spec["build"]["artifact_name"]:
        raise services['PipelineError']("build artifact name does not match the catalog")
    artifact_path = services['safe_child'](record_path.parent, artifact["path"], "build artifact path")
    artifact_bytes = services['verified_file_bytes'](
        artifact_path,
        artifact.get("sha256", ""),
        "build artifact",
        validation_context,
    )
    current_artifact = services['apply_artifact_dependency_policy'](
        services['_validate_artifact_bytes'](artifact_bytes, arch), spec
    )
    dependency_policy = services['validated_forbidden_needed_prefixes'](spec)
    if (
        current_artifact.get("status") != "valid"
        or current_artifact.get("sha256") != artifact.get("sha256")
        or current_artifact.get("size") != artifact.get("size")
        or (
            dependency_policy
            and (
                not isinstance(current_artifact.get("needed"), list)
                or not isinstance(artifact.get("needed"), list)
                or current_artifact.get("needed") != artifact.get("needed")
            )
        )
    ):
        raise services['PipelineError']("build artifact is missing, invalid, or no longer matches its record")

    metadata = record.get("metadata", {})
    if metadata.get("path") != spec["metadata"]["artifact_name"]:
        raise services['PipelineError']("build metadata name does not match the catalog")
    metadata_path = services['safe_child'](record_path.parent, metadata["path"], "build metadata path")
    if (
        metadata.get("status") != "valid"
        or not metadata_path.is_file()
        or metadata_path.stat().st_size != metadata.get("size")
        or services['sha256_file'](metadata_path) != metadata.get("sha256")
    ):
        raise services['PipelineError']("build metadata is missing or no longer matches its record")
    if not services['metadata_matches_replacement'](metadata, expected_metadata_replacement):
        raise services['PipelineError'](
            "build metadata does not match the exact catalog replacement"
        )

    build = record.get("build", {})
    contract_build = services['_source_candidate_contract_build_for_guard'](
        build,
        source_candidate_projection,
    )
    record_has_recipe_profile = (
        isinstance(build, dict) and "recipe_profile" in build
    )
    is_direct_cmake = spec["build"]["driver"] == "direct-cmake"
    is_strict_build_contract = (
        is_direct_cmake
        or bool(expected_make_variables)
        or expected_git_version is not None
        or expected_generated_source is not None
        or expected_recipe_profile is not None
        or record_has_recipe_profile
        or core_id in services['EXACT_SOURCE_NATIVE_CORE_IDS']
    )
    is_combined_git_make_contract = bool(expected_make_variables) and (
        expected_git_version is not None
        and expected_git_version.get("derivation")
        == services['NATIVE_GIT_VERSION_DERIVATION']
        and core_id in services['COMBINED_NATIVE_MAKE_CORE_IDS']
    )
    strict_record_mismatch = is_strict_build_contract and (
        not isinstance(build, dict)
        or set(build) != set(expected_build_contract).union({"log", "log_sha256"})
        or services['recorded_build_contract'](build) != expected_build_contract
        or (
            expected_generated_source is not None
            and not services['core_81_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        )
        or (
            is_combined_git_make_contract
            and not services['combined_git_version_make_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        )
        or (
            not is_combined_git_make_contract
            and bool(expected_make_variables)
            and not services['make_variable_golden_build_contract_is_well_formed'](build)
        )
        or (
            not is_combined_git_make_contract
            and
            expected_git_version is not None
            and not services['git_version_golden_build_contract_is_well_formed'](
                contract_build,
                contract_source_commit,
                core_id,
                contract_source,
                arch,
            )
        )
        or (
            core_id == services['VEMULATOR_CORE_ID']
            and not services['vemulator_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        )
        or (
            core_id == services['FREEINTV_CORE_ID']
            and not services['freeintv_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        )
        or (
            expected_recipe_profile is not None
            and not services['picodrive_golden_build_contract_is_well_formed'](
                contract_build,
                contract_source_commit,
                core_id,
                contract_source,
                arch,
            )
        )
    )
    legacy_record_mismatch = not is_strict_build_contract and (
        not isinstance(build, dict)
        or build.get("driver") != spec["build"]["driver"]
        or build.get("environment") != "sanitized-v1"
        or (
            expected_source_date_epoch is not None
            and "compile_definitions" not in build
        )
        or build.get("compile_definitions", []) != expected_compile_definitions
        or not services['build_source_date_epoch_matches'](build, expected_source_date_epoch)
    )
    if strict_record_mismatch or legacy_record_mismatch:
        raise services['PipelineError']("build record compile environment does not match the catalog")
    build_log = services['safe_child'](record_path.parent, build.get("log", ""), "build log path")
    build_log_text = services['verified_utf8_text'](
        build_log,
        build.get("log_sha256"),
        "build log",
        validation_context,
    )
    if not services['compile_log_proves_definitions'](
        build_log_text, expected_compile_definitions, arch
    ):
        raise services['PipelineError'](
            "build log does not prove the catalog compile definitions on a "
            "compiler -c command: "
            + ", ".join(expected_compile_definitions)
        )
    if expected_make_variables and not services['make_variable_log_proves_contract'](
        build_log_text, expected_make_variables, arch
    ):
        raise services['PipelineError'](
            "build log does not prove the exact "
            + services['make_variable_contract_name'](expected_make_variables)
            + " make-variable origin and compile contract"
        )
    if expected_git_version is not None and not services['git_version_log_proves_contract'](
        build_log_text,
        expected_git_version,
        spec["source"]["commit"],
        arch,
    ):
        raise services['PipelineError'](
            "build log does not prove the exact commit-derived GIT_VERSION "
            "GNU Make origin and target compile token"
        )
    log_contract = services['core_log_contract_for'](core_id)
    if log_contract is not None and not services['_registered_core_log_contract_proves'](
        build_log_text,
        core_id,
        arch,
        spec["source"]["commit"],
        spec["source"]["tree"],
        tuning=execution_tuning,
        source_candidate_projection=source_candidate_projection,
    ):
        raise services['PipelineError'](log_contract.failure_message)
    if expected_metadata_replacement is not None and not (
        services['metadata_replacement_log_proves_contract'](
            build_log_text, expected_metadata_replacement
        )
    ):
        raise services['PipelineError'](
            "build log does not prove the exact metadata replacement contract"
        )
    if is_direct_cmake and not services['direct_cmake_log_proves_contract'](
        build_log_text, spec, arch
    ):
        raise services['PipelineError'](
            "build log does not prove the exact direct-CMake and overlay contract"
        )
    return artifact_path, metadata_path, build_log


def validate_build_record_identity(
    record: dict,
    record_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    expected_catalog_file_sha256: str | None = None,
    services: EvidenceValidationServices,
) -> tuple[Path, Path, Path]:
    """Validate an ordinary record without a caller-supplied relaxation."""

    services['_require_public_ordinary_catalog'](
        catalog_path,
        catalog,
        expected_catalog_file_sha256=expected_catalog_file_sha256,
    )
    return services['_validate_build_record_identity'](
        record,
        record_path,
        catalog_path,
        catalog,
        expected_catalog_file_sha256=expected_catalog_file_sha256,
    )


def _require_public_ordinary_catalog(
    catalog_path: Path,
    catalog: Mapping[str, object],
    *,
    expected_catalog_file_sha256: str | None = None,
    services: EvidenceValidationServices,
) -> str:
    resolved = services['require_contained'](catalog_path, services['ROOT'], "ordinary catalog")
    if resolved.resolve() != services['DEFAULT_CATALOG'].resolve():
        raise services['PipelineError'](
            "ordinary evidence validation requires the exact canonical catalog path"
        )
    on_disk, file_sha256 = services['load_json_with_sha256'](resolved)
    if on_disk != catalog:
        raise services['PipelineError'](
            "ordinary evidence validation catalog differs from canonical disk bytes"
        )
    if (
        expected_catalog_file_sha256 is not None
        and expected_catalog_file_sha256 != file_sha256
    ):
        raise services['PipelineError'](
            "ordinary evidence validation catalog digest differs"
        )
    services['validate_catalog'](dict(on_disk))
    return file_sha256


def validate_bound_host_telemetry(evidence: dict, e2e_path: Path, *, services: EvidenceValidationServices) -> dict | None:
    """Deeply bind a schema-v2 runner sidecar; preserve legacy read support."""

    runner = evidence.get("runner")
    if not services['runner_evidence_is_hardened'](runner):
        return None
    assert isinstance(runner, dict)
    document = services['validate_sidecar_reference'](runner["telemetry"], services['ROOT'])
    selector = document.get("runner", {}).get("selector")
    profile_reference = runner.get("execution_profile")
    if not isinstance(profile_reference, dict) or not isinstance(
        profile_reference.get("schema"), dict
    ):
        raise services['PipelineError']("host-build execution profile reference is malformed")
    try:
        profile = services['resolve_host_execution_profile'](
            selector,
            repository_root=services['ROOT'],
            registry_path=services['safe_child'](
                services['ROOT'],
                profile_reference.get("path", ""),
                "host execution profile snapshot",
            ),
            registry_schema_path=services['safe_child'](
                services['ROOT'],
                profile_reference["schema"].get("path", ""),
                "host execution profile schema snapshot",
            ),
        )
    except services['RunnerProfileError'] as exc:
        raise services['PipelineError'](str(exc)) from exc
    expected_runner = {
        "selector": selector,
        **profile.runner_identity(),
        "execution_label": profile.execution_label,
    }
    expected_runner_reference = {
        **profile.reference(),
        "execution_label": profile.execution_label,
    }
    if (
        document.get("$schema")
        != "../../../manifests/host-build-telemetry.schema.json"
        or document.get("schema_version") != 1
        or document.get("telemetry_contract") != profile.telemetry_contract
        or document.get("run_id") != evidence.get("run_id")
        or document.get("result") != evidence.get("result")
        or document.get("local_only") is not True
        or document.get("publication") != "disabled"
        or document.get("runner") != expected_runner
        or runner.get("execution_profile") != expected_runner_reference
        or document.get("execution_profile")
        != {**profile.reference(), "resources": profile.resources()}
        or document.get("cache") != profile.cache()
    ):
        raise services['PipelineError']("host-build telemetry execution identity is invalid")
    builds = evidence.get("builds")
    telemetry_builds = document.get("builds")
    packages = evidence.get("packages")
    if (
        not isinstance(builds, list)
        or not isinstance(telemetry_builds, list)
        or not isinstance(packages, list)
        or document.get("packages") != packages
    ):
        raise services['PipelineError']("host-build telemetry build/package scope is invalid")
    expected_entries = {
        (item.get("core_id"), item.get("architecture")): item
        for item in builds
        if isinstance(item, dict)
    }
    observed_entries = {
        (item.get("core_id"), item.get("architecture")): item
        for item in telemetry_builds
        if isinstance(item, dict)
    }
    if (
        len(expected_entries) != len(builds)
        or len(observed_entries) != len(telemetry_builds)
        or set(observed_entries) != set(expected_entries)
    ):
        raise services['PipelineError']("host-build telemetry target scope is invalid")
    for target, telemetry_build in observed_entries.items():
        e2e_entry = expected_entries[target]
        bindings = telemetry_build["bindings"]
        build_reference = bindings["build_record"]
        record_digest = build_reference.get("file_sha256")
        try:
            expected_record_path = services['require_canonical_store_entry'](
                {
                    "path": build_reference.get("path"),
                    "sha256": record_digest,
                },
                "build-records",
                "host-build telemetry build record",
            )
        except services['PipelineError'] as exc:
            raise services['PipelineError'](
                "host-build telemetry build-record reference is invalid"
            ) from exc
        if (
            e2e_entry.get("record_sha256") != record_digest
        ):
            raise services['PipelineError']("host-build telemetry build-record binding is invalid")
        record, record_file_sha256 = services['load_json_with_sha256'](expected_record_path)
        if record_file_sha256 != record_digest:
            raise services['PipelineError']("host-build telemetry build-record bytes are invalid")
        expected_abi = {
            "architecture": record.get("architecture"),
            "elf_class": record.get("artifact", {}).get("elf_class"),
            "machine": record.get("artifact", {}).get("machine"),
            "interpreter": record.get("artifact", {}).get("interpreter"),
        }
        expected_outputs = {
            "artifact": {
                "path": record.get("artifact", {}).get("path"),
                "sha256": record.get("artifact", {}).get("sha256"),
                "size": record.get("artifact", {}).get("size"),
            },
            "metadata": {
                "path": record.get("metadata", {}).get("path"),
                "sha256": record.get("metadata", {}).get("sha256"),
                "size": record.get("metadata", {}).get("size"),
            },
            "build_log": bindings["outputs"]["build_log"],
        }
        log_reference = bindings["outputs"]["build_log"]
        log_digest = log_reference.get("sha256")
        try:
            expected_log_path = services['require_canonical_store_entry'](
                log_reference,
                "logs",
                "host-build telemetry build log",
            )
        except services['PipelineError'] as exc:
            raise services['PipelineError']("host-build telemetry log reference is invalid") from exc
        if (
            not expected_log_path.is_file()
            or services['sha256_file'](expected_log_path) != log_digest
            or record.get("build", {}).get("log_sha256") != log_digest
        ):
            raise services['PipelineError']("host-build telemetry build-log binding is invalid")
        log_text = services['verified_utf8_text'](
            expected_log_path, log_digest, "host-build telemetry build log"
        )
        services['validate_job_count_log'](
            log_text,
            profile.jobs,
            require_parallel_invocation=(
                telemetry_build.get("units", {}).get("status") != "unavailable"
            ),
        )
        if (
            telemetry_build.get("result") != record.get("result")
            or telemetry_build.get("container", {}).get("state", {}).get("exit_code")
            != record.get("build_exit_code")
            or telemetry_build.get("driver") != record.get("build", {}).get("driver")
            or bindings.get("source") != record.get("source")
            or bindings.get("recipe") != record.get("recipe")
            or bindings.get("toolchain") != record.get("toolchain")
            or bindings.get("abi") != expected_abi
            or bindings.get("tuning")
            != record.get("recipe", {}).get("chipset_tuning")
            or bindings.get("outputs") != expected_outputs
            or telemetry_build["instrumentation"]["contract"]
            != record.get("recipe", {}).get("host_execution", {}).get(
                "instrumentation"
            )
            or record.get("recipe", {}).get("host_execution", {}).get("resources")
            != profile.resources()
            or record.get("recipe", {}).get("host_execution", {}).get("cache")
            != profile.cache()
        ):
            raise services['PipelineError']("host-build telemetry nested build binding is invalid")
    return document


def require_host_execution_runner_coupling(
    evidence: Mapping[str, object], record: Mapping[str, object], label: str,
    *,
    services: EvidenceValidationServices,
) -> None:
    """Reject either direction of runner/recipe telemetry downgrade."""

    recipe = record.get("recipe")
    has_host_execution = isinstance(recipe, services['Mapping']) and "host_execution" in recipe
    hardened = services['runner_evidence_is_hardened'](evidence.get("runner"))
    if has_host_execution != hardened:
        raise services['PipelineError'](
            f"{label}: host-execution recipe and hardened runner evidence differ"
        )


def _validate_e2e_evidence(
    e2e_path: Path,
    selected_record_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    expected_catalog_file_sha256: str | None = None,
    services: EvidenceValidationServices,
) -> tuple[dict, str, dict[str, tuple[dict, Path, str]], Path, dict]:
    e2e_path = services['require_contained'](e2e_path, services['ROOT'] / ".local-e2e", "E2E record")
    selected_record_path = services['require_contained'](
        selected_record_path, services['ROOT'] / ".local-e2e", "build record"
    )
    if e2e_path.name != "e2e-record.json":
        raise services['PipelineError']("E2E evidence must be an e2e-record.json file")
    run_root = e2e_path.parent
    services['require_contained'](selected_record_path, run_root, "selected build record")
    try:
        evidence_bytes = e2e_path.read_bytes()
        evidence = services['decode_json_object'](evidence_bytes, e2e_path)
    except (OSError, services['PipelineError']) as exc:
        raise services['PipelineError'](f"cannot load E2E JSON from {e2e_path}: {exc}") from exc
    evidence_file_sha256 = services['sha256_bytes'](evidence_bytes)
    selected, selected_file_sha256 = services['load_json_with_sha256'](selected_record_path)
    core_id = selected.get("core_id")
    arch = selected.get("architecture")
    if core_id not in catalog["cores"]:
        raise services['PipelineError']("selected record core is not in the current catalog")
    matching_builds, matching_packages = services['active_promotion_e2e_scope'](
        evidence, core_id
    )
    if not services['runner_evidence_is_well_formed'](evidence.get("runner")):
        raise services['PipelineError']("E2E runner evidence is missing or invalid")
    services['validate_bound_host_telemetry'](evidence, e2e_path)
    if (
        evidence.get("result") != "passed"
        or not evidence.get("local_only")
        or evidence.get("publication") != "disabled"
    ):
        raise services['PipelineError']("E2E record is not a passed local-only run")
    if evidence.get("content_sha256") != services['e2e_content_sha256'](evidence):
        raise services['PipelineError']("E2E record content digest is invalid")

    spec = catalog["cores"][core_id]
    if (
        len(matching_builds) != len(spec["targets"])
        or {item.get("architecture") for item in matching_builds} != set(spec["targets"])
        or any(item.get("result") != "passed" for item in matching_builds)
    ):
        raise services['PipelineError']("E2E record does not contain a complete passing target set")

    bound_records: dict[str, tuple[dict, services['Path'], str]] = {}
    for item in matching_builds:
        record_path = services['safe_child'](services['ROOT'], item.get("record", ""), "E2E build record path")
        services['require_contained'](record_path, run_root, "E2E build record")
        if record_path.resolve() == selected_record_path.resolve():
            record = selected
            record_file_sha256 = selected_file_sha256
        else:
            record, record_file_sha256 = services['load_json_with_sha256'](record_path)
        if not record_path.is_file() or record_file_sha256 != item.get("record_sha256"):
            raise services['PipelineError']("E2E build record digest is missing or invalid")
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != item.get("architecture")
        ):
            raise services['PipelineError']("E2E build entry does not match its build record")
        services['require_host_execution_runner_coupling'](
            evidence, record, f"{core_id}/{item.get('architecture')} E2E build"
        )
        services['_validate_build_record_identity'](
            record,
            record_path,
            catalog_path,
            catalog,
            expected_catalog_file_sha256=expected_catalog_file_sha256,
        )
        bound_records[record["architecture"]] = (
            record,
            record_path,
            item["record_sha256"],
        )
    if len({item[0]["metadata"]["sha256"] for item in bound_records.values()}) != 1:
        raise services['PipelineError']("E2E target metadata digests are inconsistent")
    if bound_records.get(arch, ({}, services['Path']()))[1].resolve() != selected_record_path:
        raise services['PipelineError']("selected build record is not bound to this E2E run")

    if len(matching_packages) != 1 or matching_packages[0].get("result") != "packaged":
        raise services['PipelineError']("E2E record lacks one passing package for the selected core")
    package_record = matching_packages[0]
    package_path = services['safe_child'](run_root, package_record.get("path", ""), "E2E package path")
    try:
        package_bytes = services['verified_file_bytes'](
            package_path,
            package_record.get("sha256"),
            "E2E package",
        )
    except services['PipelineError'] as exc:
        raise services['PipelineError']("E2E package is missing or does not match its record") from exc
    if (
        package_path.name != f"{core_id}_libretro.zip"
        or len(package_bytes) != package_record.get("size")
    ):
        raise services['PipelineError']("E2E package is missing or does not match its record")

    try:
        with services['zipfile'].ZipFile(services['io'].BytesIO(package_bytes)) as archive:
            expected_members = {
                f"{services['ARCH_LAYOUT'][target]['package_directory']}/{spec['build']['artifact_name']}"
                for target in spec["targets"]
            }
            expected_members.update({spec["metadata"]["artifact_name"], "manifest.json"})
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise services['PipelineError']("E2E package contains duplicate members")
            if set(archive.namelist()) != expected_members:
                raise services['PipelineError']("E2E package members do not match the catalog")
            manifest = services['decode_json_object'](
                archive.read("manifest.json"), "E2E package manifest"
            )
            if (
                manifest.get("core_id") != core_id
                or not manifest.get("local_only")
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != set(spec["targets"])
            ):
                raise services['PipelineError']("E2E package manifest identity is invalid")
            for target, (record, _, _) in bound_records.items():
                member = (
                    f"{services['ARCH_LAYOUT'][target]['package_directory']}/"
                    f"{spec['build']['artifact_name']}"
                )
                package_artifact = manifest["artifacts"][target]
                if (
                    package_artifact.get("path") != member
                    or package_artifact.get("sha256") != record["artifact"]["sha256"]
                    or package_artifact.get("source_commit")
                    != record["source"]["resolved_commit"]
                    or package_artifact.get("toolchain_image_id")
                    != record["toolchain"]["resolved_image_id"]
                    or services['sha256_bytes'](archive.read(member)) != record["artifact"]["sha256"]
                ):
                    raise services['PipelineError']("E2E packaged artifact identity is invalid")
            metadata_manifest = manifest.get("metadata", {})
            metadata_name = spec["metadata"]["artifact_name"]
            expected_metadata_sha = bound_records[spec["targets"][0]][0]["metadata"][
                "sha256"
            ]
            if (
                metadata_manifest.get("path") != metadata_name
                or metadata_manifest.get("sha256") != expected_metadata_sha
                or services['sha256_bytes'](archive.read(metadata_name)) != expected_metadata_sha
            ):
                raise services['PipelineError']("E2E packaged metadata identity is invalid")
    except (KeyError, services['PipelineError'], services['zipfile'].BadZipFile) as exc:
        raise services['PipelineError'](f"cannot validate E2E package: {exc}") from exc
    return evidence, evidence_file_sha256, bound_records, package_path, package_record


def validate_e2e_evidence(
    e2e_path: Path,
    selected_record_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    expected_catalog_file_sha256: str | None = None,
    services: EvidenceValidationServices,
) -> tuple[dict, str, dict[str, tuple[dict, Path, str]], Path, dict]:
    """Validate ordinary E2E bytes against the exact canonical catalog."""

    catalog_file_sha256 = services['_require_public_ordinary_catalog'](
        catalog_path,
        catalog,
        expected_catalog_file_sha256=expected_catalog_file_sha256,
    )
    return services['_validate_e2e_evidence'](
        e2e_path,
        selected_record_path,
        catalog_path,
        catalog,
        expected_catalog_file_sha256=catalog_file_sha256,
    )


def validate_group_e2e_evidence(
    e2e_path: Path,
    selected_record_path: Path,
    catalog_path: Path,
    catalog: dict,
    expected_group: Mapping[str, object],
    *,
    services: EvidenceValidationServices,
) -> tuple[dict, str, dict[str, tuple[dict, Path, str]], Path, dict]:
    """Deeply validate one full-package grouped E2E reproduction.

    This is intentionally separate from legacy golden promotion.  It accepts
    group records only when the caller supplies the exact plan-bound group and
    the selected architecture set covers the pin's complete package identity.
    """

    validation_context = services['_PinValidationContext']()
    if not isinstance(expected_group, services['Mapping']):
        raise services['PipelineError']("expected core group evidence must be an object")
    expected_outputs = expected_group.get("expected_outputs")
    expected_package = (
        expected_outputs.get("package")
        if isinstance(expected_outputs, services['Mapping'])
        else None
    )
    if not isinstance(expected_package, services['Mapping']) or expected_package.get(
        "comparison"
    ) != "exact":
        raise services['PipelineError'](
            "grouped release evidence requires exact full-package comparison"
        )
    expected_tuning = expected_group.get("tuning")
    if not isinstance(expected_tuning, services['Mapping']):
        raise services['PipelineError']("expected core group tuning must be an object")
    core_id = expected_group.get("core_id")
    if core_id not in catalog["cores"]:
        raise services['PipelineError']("group E2E core is not in the current catalog")
    group_tag = expected_group.get("group_tag")
    if not isinstance(group_tag, str) or services['resolve_core_group_build_selection'](
        group_tag=group_tag,
        catalog_path=catalog_path,
        catalog=catalog,
        core_id=core_id,
    ) != expected_group:
        raise services['PipelineError']("expected core group is not the canonical current selection")
    execution_spec = services['group_execution_spec'](
        core_id=core_id,
        catalog_spec=catalog["cores"][core_id],
        group_selection=expected_group,
    )
    execution_catalog = services['copy'].deepcopy(catalog)
    execution_catalog["cores"][core_id] = execution_spec
    group_source_candidate_projection = (
        services['group_source_candidate_contract_projection'](
            core_id=core_id,
            catalog_spec=catalog["cores"][core_id],
            execution_spec=execution_spec,
            group_selection=expected_group,
        )
    )
    authenticated_source_candidate_contract = (
        (catalog["cores"][core_id], group_source_candidate_projection)
        if group_source_candidate_projection is not None
        else None
    )
    e2e_path = services['require_contained'](e2e_path, services['ROOT'] / ".local-e2e", "group E2E record")
    selected_record_path = services['require_contained'](
        selected_record_path,
        services['ROOT'] / ".local-e2e",
        "group build record",
    )
    if e2e_path.name != "e2e-record.json":
        raise services['PipelineError']("group E2E evidence must be an e2e-record.json file")
    run_root = e2e_path.parent
    services['require_contained'](selected_record_path, run_root, "selected group build record")
    selected, selected_file_sha256 = services['load_json_with_sha256'](selected_record_path)
    try:
        evidence_bytes = e2e_path.read_bytes()
        evidence = services['decode_json_object'](evidence_bytes, e2e_path)
    except (OSError, services['PipelineError']) as exc:
        raise services['PipelineError'](f"cannot load group E2E JSON from {e2e_path}: {exc}") from exc
    if evidence.get("core_group") != expected_group:
        raise services['PipelineError']("group E2E selection does not match the release plan")
    if (
        evidence.get("schema_version") != 2
        or evidence.get("result") != "passed"
        or evidence.get("local_only") is not True
        or evidence.get("publication") != "disabled"
        or not services['runner_evidence_is_well_formed'](evidence.get("runner"))
        or evidence.get("content_sha256") != services['e2e_content_sha256'](evidence)
    ):
        raise services['PipelineError']("group E2E record contract is invalid")
    services['validate_bound_host_telemetry'](evidence, e2e_path)
    selected_architectures = expected_group.get("selected_architectures")
    if (
        not isinstance(selected_architectures, list)
        or not selected_architectures
        or len(selected_architectures) != len(set(selected_architectures))
        or any(arch not in catalog["cores"][core_id]["targets"] for arch in selected_architectures)
    ):
        raise services['PipelineError']("group E2E selected architecture scope is invalid")
    matching_builds, matching_packages = services['active_promotion_e2e_scope'](
        evidence,
        core_id,
    )
    if (
        len(matching_builds) != len(selected_architectures)
        or {item.get("architecture") for item in matching_builds}
        != set(selected_architectures)
        or any(item.get("result") != "passed" for item in matching_builds)
    ):
        raise services['PipelineError']("group E2E record does not contain its exact passing ABI set")

    bound_records: dict[str, tuple[dict, services['Path'], str]] = {}
    spec = execution_spec
    for item in matching_builds:
        record_path = services['safe_child'](services['ROOT'], item.get("record", ""), "group E2E build record")
        services['require_contained'](record_path, run_root, "group E2E build record")
        if record_path.resolve() == selected_record_path.resolve():
            record = selected
            record_file_sha256 = selected_file_sha256
        else:
            record, record_file_sha256 = services['load_json_with_sha256'](record_path)
        if not record_path.is_file() or record_file_sha256 != item.get("record_sha256"):
            raise services['PipelineError']("group E2E build record digest is missing or invalid")
        arch = item.get("architecture")
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != arch
            or record.get("core_group") != expected_group
        ):
            raise services['PipelineError']("group E2E build entry does not match its build record")
        services['require_host_execution_runner_coupling'](
            evidence, record, f"{core_id}/{arch} group E2E build"
        )
        expected_tuning_identity = {
            "profile_id": expected_tuning.get("profile_id"),
            "content_sha256": expected_tuning.get("content_sha256"),
        }
        if record.get("recipe", {}).get("chipset_tuning") != expected_tuning_identity:
            raise services['PipelineError']("group build recipe tuning identity is invalid")
        if services['pinned_group_execution_source'](
            record.get("source"),
            label=f"{core_id}/{arch} group build",
        ) != expected_group.get("execution_source"):
            raise services['PipelineError']("group build source identity is invalid")
        legacy_projection = services['copy'].deepcopy(record)
        legacy_projection.pop("core_group", None)
        legacy_projection.get("recipe", {}).pop("chipset_tuning", None)
        tuning = services['_group_execution_tuning'](expected_group, core_id=core_id, arch=arch)
        assert tuning is not None
        _artifact_path, _metadata_path, build_log_path = services['_validate_build_record_identity'](
            legacy_projection,
            record_path,
            catalog_path,
            execution_catalog,
            execution_tuning=tuning,
            validation_context=validation_context,
            authenticated_recipe_catalog_snapshot=catalog,
            authenticated_source_candidate_contract=(
                authenticated_source_candidate_contract
            ),
        )
        if not services['chipset_tuning_log_proves_contract'](
            services['verified_utf8_text'](
                build_log_path,
                record.get("build", {}).get("log_sha256"),
                "group build log",
                validation_context,
            ),
            tuning,
            arch,
            allow_no_target_compile=(
                record.get("build", {}).get("driver") == "direct-cargo"
            ),
        ):
            raise services['PipelineError']("group build log does not prove its tuning contract")
        artifact_validation = services['copy'].deepcopy(record.get("artifact", {}))
        metadata_validation = services['copy'].deepcopy(record.get("metadata", {}))
        services['apply_group_output_expectations'](
            artifact_validation=artifact_validation,
            metadata_validation=metadata_validation,
            group_selection=expected_group,
            arch=arch,
        )
        if (
            artifact_validation.get("status") != "valid"
            or metadata_validation.get("status") != "valid"
        ):
            raise services['PipelineError']("group build outputs do not match the selected pin")
        bound_records[arch] = (record, record_path, item["record_sha256"])
    if bound_records.get(selected.get("architecture"), ({}, services['Path']()))[
        1
    ].resolve() != selected_record_path:
        raise services['PipelineError']("selected group build record is not bound to this E2E run")

    if len(matching_packages) != 1 or matching_packages[0].get("result") != "packaged":
        raise services['PipelineError']("group E2E record lacks one passing package")
    package_record = matching_packages[0]
    expected_package_binding = {
        "variant_id": expected_group.get("variant_id"),
        "comparison": "exact",
    }
    package_path = services['safe_child'](
        run_root,
        package_record.get("path", ""),
        "group E2E package path",
    )
    try:
        package_bytes = services['verified_file_bytes'](
            package_path,
            expected_package.get("sha256"),
            "group E2E package",
        )
    except services['PipelineError'] as exc:
        raise services['PipelineError']("group E2E package does not match the selected pin") from exc
    if (
        package_record.get("core_group") != expected_package_binding
        or package_record.get("path") != expected_package.get("name")
        or package_record.get("sha256") != expected_package.get("sha256")
        or package_record.get("size") != expected_package.get("size")
        or len(package_bytes) != expected_package.get("size")
    ):
        raise services['PipelineError']("group E2E package does not match the selected pin")
    try:
        with services['zipfile'].ZipFile(services['io'].BytesIO(package_bytes)) as archive:
            expected_members = {
                f"{services['ARCH_LAYOUT'][arch]['package_directory']}/{spec['build']['artifact_name']}"
                for arch in selected_architectures
            }
            expected_members.update({spec["metadata"]["artifact_name"], "manifest.json"})
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist()) != expected_members
            ):
                raise services['PipelineError']("group E2E package members do not match its ABI set")
            manifest = services['decode_json_object'](
                archive.read("manifest.json"), "group E2E package manifest"
            )
            if (
                manifest.get("core_id") != core_id
                or manifest.get("local_only") is not True
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != set(selected_architectures)
            ):
                raise services['PipelineError']("group E2E package manifest identity is invalid")
            for arch, (record, _, _) in bound_records.items():
                member = (
                    f"{services['ARCH_LAYOUT'][arch]['package_directory']}/"
                    f"{spec['build']['artifact_name']}"
                )
                package_artifact = manifest["artifacts"][arch]
                if (
                    package_artifact.get("path") != member
                    or package_artifact.get("sha256") != record["artifact"]["sha256"]
                    or package_artifact.get("source_commit")
                    != record["source"]["resolved_commit"]
                    or package_artifact.get("toolchain_image_id")
                    != record["toolchain"]["resolved_image_id"]
                    or services['sha256_bytes'](archive.read(member)) != record["artifact"]["sha256"]
                ):
                    raise services['PipelineError']("group E2E packaged artifact identity is invalid")
            metadata_name = spec["metadata"]["artifact_name"]
            expected_metadata = expected_outputs.get("metadata")
            if not isinstance(expected_metadata, services['Mapping']):
                raise services['PipelineError']("group E2E expected metadata identity is invalid")
            metadata_manifest = manifest.get("metadata", {})
            if (
                metadata_manifest.get("path") != metadata_name
                or metadata_manifest.get("sha256") != expected_metadata.get("sha256")
                or services['sha256_bytes'](archive.read(metadata_name))
                != expected_metadata.get("sha256")
            ):
                raise services['PipelineError']("group E2E packaged metadata identity is invalid")
    except (KeyError, services['json'].JSONDecodeError, UnicodeDecodeError, services['zipfile'].BadZipFile) as exc:
        raise services['PipelineError'](f"cannot validate group E2E package: {exc}") from exc
    return (
        evidence,
        services['sha256_bytes'](evidence_bytes),
        bound_records,
        package_path,
        package_record,
    )


TUNED_BUILD_RECORD_KEYS = frozenset(
    {
        "schema_version", "local_only", "publication", "started_at",
        "finished_at", "core_id", "architecture", "result",
        "build_exit_code", "source", "recipe", "toolchain", "build",
        "artifact", "metadata", "tuning_candidate",
    }
)
TUNED_E2E_KEYS = frozenset(
    {
        "schema_version", "run_id", "local_only", "publication", "runner",
        "result", "workflow_audit", "builds", "packages",
        "tuning_candidate", "content_sha256",
    }
)


def validate_tuned_e2e_evidence(
    e2e_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    expected_core: str | None = None,
    expected_selection: Mapping[str, object] | None = None,
    services: EvidenceValidationServices,
) -> dict:
    validation_context = services['_PinValidationContext']()
    """Deeply validate one registry-owned, one-ABI tuning candidate."""

    e2e_path = services['require_contained'](
        e2e_path, services['ROOT'] / ".local-e2e", "tuning candidate E2E record"
    )
    if e2e_path.name != "e2e-record.json":
        raise services['PipelineError']("tuning candidate evidence must be an e2e-record.json file")
    try:
        evidence_bytes = e2e_path.read_bytes()
        evidence = services['decode_json_object'](evidence_bytes, e2e_path)
    except (OSError, services['PipelineError']) as exc:
        raise services['PipelineError'](f"cannot load tuning candidate E2E: {exc}") from exc
    if set(evidence) != services['TUNED_E2E_KEYS']:
        raise services['PipelineError']("tuning candidate E2E fields are not exact")
    selection = services['validated_tuning_candidate_selection'](evidence.get("tuning_candidate"))
    if expected_selection is not None and selection != dict(expected_selection):
        raise services['PipelineError']("tuning candidate E2E uses a different tuning identity")
    if (
        evidence.get("schema_version") != 2
        or evidence.get("result") != "passed"
        or evidence.get("local_only") is not True
        or evidence.get("publication") != "disabled"
        or not services['runner_evidence_is_well_formed'](evidence.get("runner"))
        or evidence.get("content_sha256") != services['e2e_content_sha256'](evidence)
    ):
        raise services['PipelineError']("tuning candidate E2E identity is invalid")
    services['validate_bound_host_telemetry'](evidence, e2e_path)
    builds = evidence.get("builds")
    packages = evidence.get("packages")
    if (
        not isinstance(builds, list) or len(builds) != 1
        or not isinstance(packages, list) or len(packages) != 1
    ):
        raise services['PipelineError']("tuning candidate E2E must contain one build and package")
    build_entry = builds[0]
    package_record = packages[0]
    if (
        not isinstance(build_entry, dict)
        or set(build_entry)
        != {"core_id", "architecture", "result", "record", "record_sha256"}
        or build_entry.get("result") != "passed"
        or not isinstance(package_record, dict)
        or set(package_record)
        != {"core_id", "result", "path", "sha256", "size", "tuning_candidate"}
        or package_record.get("result") != "packaged"
        or package_record.get("tuning_candidate") != selection
    ):
        raise services['PipelineError']("tuning candidate E2E entries are invalid")
    core_id = build_entry.get("core_id")
    arch = selection["profile"]["architecture"]
    if (
        core_id not in catalog.get("cores", {})
        or (expected_core is not None and core_id != expected_core)
        or build_entry.get("architecture") != arch
        or package_record.get("core_id") != core_id
        or arch not in catalog["cores"][core_id]["targets"]
    ):
        raise services['PipelineError']("tuning candidate core or architecture is invalid")
    run_root = e2e_path.parent
    record_path = services['safe_child'](
        services['ROOT'], build_entry.get("record", ""), "tuning candidate build record"
    )
    services['require_contained'](record_path, run_root, "tuning candidate build record")
    record, record_file_sha256 = services['load_json_with_sha256'](record_path)
    if not record_path.is_file() or record_file_sha256 != build_entry.get("record_sha256"):
        raise services['PipelineError']("tuning candidate build record digest is invalid")
    if (
        set(record) != services['TUNED_BUILD_RECORD_KEYS']
        or record.get("core_id") != core_id
        or record.get("architecture") != arch
        or record.get("tuning_candidate") != selection
        or record.get("recipe", {}).get("chipset_tuning")
        != services['tuning_candidate_recipe_identity'](selection)
    ):
        raise services['PipelineError']("tuning candidate build identity is invalid")
    services['require_host_execution_runner_coupling'](
        evidence, record, f"{core_id}/{arch} tuning candidate build"
    )
    legacy_projection = services['copy'].deepcopy(record)
    legacy_projection.pop("tuning_candidate")
    legacy_projection["recipe"].pop("chipset_tuning")
    artifact_path, metadata_path, log_path = services['_validate_build_record_identity'](
        legacy_projection,
        record_path,
        catalog_path,
        catalog,
        execution_tuning=selection["profile"],
        validation_context=validation_context,
    )
    if not services['chipset_tuning_log_proves_contract'](
        services['verified_utf8_text'](
            log_path,
            record.get("build", {}).get("log_sha256"),
            "tuning candidate build log",
            validation_context,
        ),
        selection["profile"], arch,
    ):
        raise services['PipelineError']("tuning candidate build log does not prove its contract")
    package_path = services['safe_child'](
        run_root, package_record.get("path", ""), "tuning candidate package"
    )
    try:
        package_bytes = services['verified_file_bytes'](
            package_path,
            package_record.get("sha256"),
            "tuning candidate package",
        )
    except services['PipelineError'] as exc:
        raise services['PipelineError']("tuning candidate package identity is invalid") from exc
    if (
        package_path.name != f"{core_id}_libretro.zip"
        or len(package_bytes) != package_record.get("size")
    ):
        raise services['PipelineError']("tuning candidate package identity is invalid")
    spec = catalog["cores"][core_id]
    artifact_member = (
        f"{services['ARCH_LAYOUT'][arch]['package_directory']}/{spec['build']['artifact_name']}"
    )
    metadata_member = spec["metadata"]["artifact_name"]
    try:
        with services['zipfile'].ZipFile(services['io'].BytesIO(package_bytes)) as archive:
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist())
                != {artifact_member, metadata_member, "manifest.json"}
            ):
                raise services['PipelineError']("tuning candidate package members are invalid")
            manifest = services['decode_json_object'](
                archive.read("manifest.json"), "tuning candidate package manifest"
            )
            if (
                not isinstance(manifest, dict)
                or set(manifest)
                != {"schema_version", "local_only", "publication", "core_id",
                    "artifacts", "metadata", "tuning_candidate"}
                or manifest.get("schema_version") != 1
                or manifest.get("local_only") is not True
                or manifest.get("publication") != "disabled"
                or manifest.get("core_id") != core_id
                or manifest.get("tuning_candidate") != selection
                or set(manifest.get("artifacts", {})) != {arch}
            ):
                raise services['PipelineError']("tuning candidate package manifest is invalid")
            artifact_manifest = manifest["artifacts"][arch]
            if (
                set(artifact_manifest)
                != {"path", "sha256", "source_commit", "toolchain_image_id"}
                or artifact_manifest.get("path") != artifact_member
                or artifact_manifest.get("sha256") != record["artifact"]["sha256"]
                or artifact_manifest.get("source_commit")
                != record["source"]["resolved_commit"]
                or artifact_manifest.get("toolchain_image_id")
                != record["toolchain"]["resolved_image_id"]
                or services['sha256_bytes'](archive.read(artifact_member))
                != record["artifact"]["sha256"]
            ):
                raise services['PipelineError']("tuning candidate packaged artifact is invalid")
            metadata_manifest = manifest.get("metadata")
            if (
                not isinstance(metadata_manifest, dict)
                or set(metadata_manifest) != {"path", "sha256"}
                or metadata_manifest.get("path") != metadata_member
                or metadata_manifest.get("sha256") != record["metadata"]["sha256"]
                or services['sha256_bytes'](archive.read(metadata_member))
                != record["metadata"]["sha256"]
            ):
                raise services['PipelineError']("tuning candidate packaged metadata is invalid")
    except (KeyError, services['json'].JSONDecodeError, UnicodeDecodeError, services['zipfile'].BadZipFile) as exc:
        raise services['PipelineError'](f"cannot validate tuning candidate package: {exc}") from exc
    return {
        "e2e": evidence,
        "e2e_path": e2e_path,
        "e2e_file_sha256": services['sha256_bytes'](evidence_bytes),
        "selection": selection,
        "core_id": core_id,
        "architecture": arch,
        "record": record,
        "record_path": record_path,
        "record_sha256": build_entry["record_sha256"],
        "artifact_path": artifact_path,
        "metadata_path": metadata_path,
        "log_path": log_path,
        "package_path": package_path,
        "package_record": services['copy'].deepcopy(package_record),
    }


def tuned_candidate_output_identity(bundle: Mapping[str, object], *, services: EvidenceValidationServices) -> dict:
    record = bundle.get("record")
    package = bundle.get("package_record")
    if not isinstance(record, services['Mapping']) or not isinstance(package, services['Mapping']):
        raise services['PipelineError']("tuning candidate bundle is incomplete")
    return {
        "artifact": {
            "sha256": record.get("artifact", {}).get("sha256"),
            "size": record.get("artifact", {}).get("size"),
        },
        "metadata": {
            "sha256": record.get("metadata", {}).get("sha256"),
            "size": record.get("metadata", {}).get("size"),
        },
        "package": {
            "name": package.get("path"),
            "sha256": package.get("sha256"),
            "size": package.get("size"),
        },
    }


def tuned_candidate_build_identity(bundle: Mapping[str, object], *, services: EvidenceValidationServices) -> dict:
    """Project build semantics while deliberately excluding log bytes/times."""

    record = bundle.get("record")
    if not isinstance(record, services['Mapping']):
        raise services['PipelineError']("tuning candidate record is missing")
    build = services['copy'].deepcopy(record.get("build"))
    if not isinstance(build, dict):
        raise services['PipelineError']("tuning candidate build contract is missing")
    build.pop("log_sha256", None)
    return {
        "schema_version": record.get("schema_version"),
        "local_only": record.get("local_only"),
        "publication": record.get("publication"),
        "core_id": record.get("core_id"),
        "architecture": record.get("architecture"),
        "result": record.get("result"),
        "build_exit_code": record.get("build_exit_code"),
        "source": record.get("source"),
        "recipe": record.get("recipe"),
        "toolchain": record.get("toolchain"),
        "build": build,
        "artifact": record.get("artifact"),
        "metadata": record.get("metadata"),
        "tuning_candidate": record.get("tuning_candidate"),
    }


def require_selected_reproduction_runner_pair(
    selected_e2e: Mapping[str, object], reproduction_e2e: Mapping[str, object],
    *,
    services: EvidenceValidationServices,
) -> None:
    selected_identity = services['base_runner_evidence'](selected_e2e.get("runner"))
    reproduction_identity = services['base_runner_evidence'](reproduction_e2e.get("runner"))
    if selected_identity != {
        "profile": "github-actions",
        "mode": "simulated",
        "backend": "local-docker",
        "local_only": True,
        "publication": "disabled",
    } or reproduction_identity != {
        "profile": "local",
        "mode": "native",
        "backend": "local-docker",
        "local_only": True,
        "publication": "disabled",
    }:
        raise services['PipelineError'](
            "selected/reproduction evidence must use github-actions-sim then local"
        )


def require_tuned_candidate_equivalence(
    selected: Mapping[str, object], reproduction: Mapping[str, object],
    *,
    services: EvidenceValidationServices,
) -> dict:
    """Require independent executions with byte-identical promoted outputs."""

    selected_e2e = selected.get("e2e")
    reproduction_e2e = reproduction.get("e2e")
    if not isinstance(selected_e2e, services['Mapping']) or not isinstance(
        reproduction_e2e, services['Mapping']
    ):
        raise services['PipelineError']("tuning candidate E2E records are missing")
    services['require_selected_reproduction_runner_pair'](selected_e2e, reproduction_e2e)
    if (
        selected.get("e2e_path") == reproduction.get("e2e_path")
        or selected_e2e.get("run_id") == reproduction_e2e.get("run_id")
        or selected.get("record_path") == reproduction.get("record_path")
        or selected.get("log_path") == reproduction.get("log_path")
    ):
        raise services['PipelineError']("tuned promotion requires two independent E2E runs")
    if selected.get("selection") != reproduction.get("selection"):
        raise services['PipelineError']("tuning profile or registry differs between E2E runs")
    if services['tuned_candidate_build_identity'](selected) != services['tuned_candidate_build_identity'](
        reproduction
    ):
        raise services['PipelineError']("tuning candidate build semantics differ between runs")
    selected_outputs = services['tuned_candidate_output_identity'](selected)
    if selected_outputs != services['tuned_candidate_output_identity'](reproduction):
        raise services['PipelineError'](
            "tuning candidate artifact, metadata, or package bytes differ"
        )
    return services['copy'].deepcopy(selected_outputs)


SOURCE_CANDIDATE_E2E_KEYS = frozenset(
    {
        "schema_version",
        "run_id",
        "local_only",
        "publication",
        "runner",
        "result",
        "workflow_audit",
        "builds",
        "packages",
        "content_sha256",
    }
)
SOURCE_CANDIDATE_BUILD_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "local_only",
        "publication",
        "started_at",
        "finished_at",
        "core_id",
        "architecture",
        "result",
        "build_exit_code",
        "source",
        "recipe",
        "toolchain",
        "build",
        "artifact",
        "metadata",
    }
)


def validate_source_candidate_e2e_evidence(
    e2e_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    expected_core: str,
    catalog_file_sha256: str,
    services: EvidenceValidationServices,
) -> dict:
    """Deeply validate one complete, untuned source-candidate E2E."""

    # A caller-provided mapping and matching file digest are not candidate
    # provenance.  Re-enter through the authenticated candidate loader so the
    # snapshot, retained mirror, generator, canonical recipe, and non-core
    # catalog bytes are all proved before any E2E evidence can be admitted.
    current_catalog, current_catalog_sha256 = services['load_catalog_with_sha256'](
        catalog_path
    )
    if (
        current_catalog != catalog
        or current_catalog_sha256 != catalog_file_sha256
    ):
        raise services['PipelineError'](
            "source-candidate catalog changed after authenticated load"
        )
    embedded_candidate = services['validated_embedded_source_candidate_shape'](
        current_catalog.get("source_candidate"),
        core_id=expected_core,
    )
    if set(current_catalog.get("cores", {})) != {expected_core}:
        raise services['PipelineError']("source-candidate catalog must contain exactly its core")
    e2e_path = services['require_lexical_repository_path'](
        e2e_path,
        services['DEFAULT_RUNS'],
        "source-candidate E2E record",
    )
    try:
        evidence, _evidence_file_sha256 = services['load_json_with_sha256'](e2e_path)
    except services['PipelineError'] as exc:
        raise services['PipelineError'](f"cannot load source-candidate E2E: {exc}") from exc
    if set(evidence) != services['SOURCE_CANDIDATE_E2E_KEYS']:
        raise services['PipelineError']("source-candidate E2E fields are not exact")
    builds, packages = services['active_promotion_e2e_scope'](evidence, expected_core)
    if not builds:
        raise services['PipelineError']("source-candidate E2E has no build records")
    first_entry = sorted(builds, key=lambda item: str(item.get("architecture")))[0]
    selected_record_path = services['safe_child'](
        services['ROOT'],
        first_entry.get("record", ""),
        "source-candidate selected build record",
    )
    (
        validated_e2e,
        e2e_file_sha256,
        bound_records,
        package_path,
        package_record,
    ) = services['_validate_e2e_evidence'](
        e2e_path,
        selected_record_path,
        catalog_path,
        catalog,
        expected_catalog_file_sha256=catalog_file_sha256,
    )
    expected_build_entry_keys = {
        "core_id",
        "architecture",
        "result",
        "record",
        "record_sha256",
    }
    if any(set(entry) != expected_build_entry_keys for entry in builds):
        raise services['PipelineError']("source-candidate E2E build entries are not exact")
    if (
        len(packages) != 1
        or set(packages[0])
        != {"core_id", "result", "path", "sha256", "size"}
    ):
        raise services['PipelineError']("source-candidate E2E package entry is not exact")

    targets: dict[str, dict] = {}
    for arch, (record, record_path, record_sha256) in sorted(
        bound_records.items()
    ):
        if set(record) != services['SOURCE_CANDIDATE_BUILD_RECORD_KEYS']:
            raise services['PipelineError'](
                f"source-candidate build record fields are not exact: {arch}"
            )
        if (
            "core_group" in record
            or "tuning_candidate" in record
            or "chipset_tuning" in record.get("recipe", {})
        ):
            raise services['PipelineError'](
                "source-candidate promotion rejects group and tuned evidence"
            )
        recipe = record.get("recipe")
        if (
            not isinstance(recipe, services['Mapping'])
            or recipe.get("catalog_path")
            != str(catalog_path.resolve().relative_to(services['ROOT']))
            or recipe.get("catalog_sha256")
            != catalog_file_sha256
        ):
            raise services['PipelineError']("source-candidate build recipe catalog binding is invalid")
        artifact_path = services['safe_child'](
            record_path.parent,
            record.get("artifact", {}).get("path", ""),
            f"source-candidate {arch} artifact",
        )
        metadata_path = services['safe_child'](
            record_path.parent,
            record.get("metadata", {}).get("path", ""),
            f"source-candidate {arch} metadata",
        )
        log_path = services['safe_child'](
            record_path.parent,
            record.get("build", {}).get("log", ""),
            f"source-candidate {arch} build log",
        )
        targets[arch] = {
            "record": record,
            "record_path": record_path,
            "record_sha256": record_sha256,
            "artifact_path": artifact_path,
            "metadata_path": metadata_path,
            "log_path": log_path,
        }
    final_catalog, final_catalog_sha256 = services['load_json_with_sha256'](catalog_path)
    if final_catalog != catalog or final_catalog_sha256 != catalog_file_sha256:
        raise services['PipelineError'](
            "source-candidate catalog changed during E2E validation"
        )
    return {
        "e2e": validated_e2e,
        "e2e_path": e2e_path,
        "e2e_file_sha256": e2e_file_sha256,
        "core_id": expected_core,
        "source_candidate": embedded_candidate,
        "targets": targets,
        "package_path": package_path,
        "package_record": package_record,
    }


def source_candidate_build_identity(bundle: Mapping[str, object], *, services: EvidenceValidationServices) -> dict:
    """Project exact build semantics while excluding times and log bytes."""

    targets = bundle.get("targets")
    if not isinstance(targets, services['Mapping']) or not targets:
        raise services['PipelineError']("source-candidate build targets are missing")
    identity: dict[str, dict] = {}
    for arch, target in sorted(targets.items()):
        record = target.get("record") if isinstance(target, services['Mapping']) else None
        if not isinstance(record, services['Mapping']):
            raise services['PipelineError']("source-candidate build record is missing")
        build = services['copy'].deepcopy(record.get("build"))
        if not isinstance(build, dict):
            raise services['PipelineError']("source-candidate build contract is missing")
        build.pop("log_sha256", None)
        identity[arch] = {
            "schema_version": record.get("schema_version"),
            "local_only": record.get("local_only"),
            "publication": record.get("publication"),
            "core_id": record.get("core_id"),
            "architecture": record.get("architecture"),
            "result": record.get("result"),
            "build_exit_code": record.get("build_exit_code"),
            "source": record.get("source"),
            "recipe": record.get("recipe"),
            "toolchain": record.get("toolchain"),
            "build": build,
            "artifact": record.get("artifact"),
            "metadata": record.get("metadata"),
            "recipe_snapshot_sha256": services['sha256_bytes'](services['recipe_snapshot'](dict(record))),
        }
    return identity


def source_candidate_output_identity(bundle: Mapping[str, object], *, services: EvidenceValidationServices) -> dict:
    targets = bundle.get("targets")
    package = bundle.get("package_record")
    if (
        not isinstance(targets, services['Mapping'])
        or not targets
        or not isinstance(package, services['Mapping'])
    ):
        raise services['PipelineError']("source-candidate output bundle is incomplete")
    records = {
        arch: target.get("record") if isinstance(target, services['Mapping']) else None
        for arch, target in targets.items()
    }
    if any(not isinstance(record, services['Mapping']) for record in records.values()):
        raise services['PipelineError']("source-candidate output record is missing")
    first = records[sorted(records)[0]]
    assert isinstance(first, services['Mapping'])
    return {
        "artifacts": {
            arch: {
                "sha256": record.get("artifact", {}).get("sha256"),
                "size": record.get("artifact", {}).get("size"),
            }
            for arch, record in sorted(records.items())
            if isinstance(record, services['Mapping'])
        },
        "metadata": {
            "sha256": first.get("metadata", {}).get("sha256"),
            "size": first.get("metadata", {}).get("size"),
        },
        "package": {
            "name": package.get("path"),
            "sha256": package.get("sha256"),
            "size": package.get("size"),
        },
    }


def require_source_candidate_equivalence(
    selected: Mapping[str, object],
    reproduction: Mapping[str, object],
    *,
    services: EvidenceValidationServices,
) -> dict:
    """Require independent valid logs and exact untuned build/output identity."""

    selected_e2e = selected.get("e2e")
    reproduction_e2e = reproduction.get("e2e")
    selected_targets = selected.get("targets")
    reproduction_targets = reproduction.get("targets")
    if (
        not isinstance(selected_e2e, services['Mapping'])
        or not isinstance(reproduction_e2e, services['Mapping'])
        or not isinstance(selected_targets, services['Mapping'])
        or not isinstance(reproduction_targets, services['Mapping'])
    ):
        raise services['PipelineError']("source-candidate E2E records are missing")
    services['require_selected_reproduction_runner_pair'](selected_e2e, reproduction_e2e)
    if (
        selected.get("e2e_path") == reproduction.get("e2e_path")
        or selected_e2e.get("run_id") == reproduction_e2e.get("run_id")
        or set(selected_targets) != set(reproduction_targets)
        or {
            target.get("record_path")
            for target in selected_targets.values()
            if isinstance(target, services['Mapping'])
        }
        & {
            target.get("record_path")
            for target in reproduction_targets.values()
            if isinstance(target, services['Mapping'])
        }
        or {
            target.get("log_path")
            for target in selected_targets.values()
            if isinstance(target, services['Mapping'])
        }
        & {
            target.get("log_path")
            for target in reproduction_targets.values()
            if isinstance(target, services['Mapping'])
        }
    ):
        raise services['PipelineError'](
            "source-candidate promotion requires two independent E2E runs"
        )
    if selected.get("source_candidate") != reproduction.get("source_candidate"):
        raise services['PipelineError']("source-candidate provenance differs between E2E runs")
    if services['source_candidate_build_identity'](selected) != services['source_candidate_build_identity'](
        reproduction
    ):
        raise services['PipelineError'](
            "source-candidate source, recipe, toolchain, or build outputs differ"
        )
    outputs = services['source_candidate_output_identity'](selected)
    if outputs != services['source_candidate_output_identity'](reproduction):
        raise services['PipelineError'](
            "source-candidate artifact, metadata, or package bytes differ"
        )
    return services['copy'].deepcopy(outputs)


def validate_host_reproduction_e2e_evidence(
    e2e_path: Path,
    catalog_path: Path,
    catalog: dict,
    *,
    expected_core: str,
    catalog_file_sha256: str,
    services: EvidenceValidationServices,
) -> dict:
    """Deeply validate one ordinary hardened-host E2E and its output bytes."""

    current_catalog, current_catalog_sha256 = services['load_catalog_with_sha256'](
        catalog_path
    )
    if (
        current_catalog != catalog
        or current_catalog_sha256 != catalog_file_sha256
        or catalog_path.resolve() != services['DEFAULT_CATALOG'].resolve()
    ):
        raise services['PipelineError'](
            "host reproduction requires the unchanged canonical catalog"
        )
    if expected_core not in catalog.get("cores", {}):
        raise services['PipelineError']("host reproduction core is not cataloged")
    e2e_path = services['require_lexical_repository_path'](
        e2e_path,
        services['DEFAULT_RUNS'],
        "host reproduction E2E record",
    )
    evidence, _ = services['load_json_with_sha256'](e2e_path)
    if (
        not services['runner_evidence_is_hardened'](evidence.get("runner"))
        or "core_group" in evidence
        or "tuning_candidate" in evidence
    ):
        raise services['PipelineError'](
            "host reproduction requires ordinary hardened runner evidence"
        )
    builds, _packages = services['active_promotion_e2e_scope'](evidence, expected_core)
    if not builds:
        raise services['PipelineError']("host reproduction E2E has no build records")
    first = sorted(builds, key=lambda item: str(item.get("architecture")))[0]
    selected_record_path = services['safe_child'](
        services['ROOT'],
        first.get("record", ""),
        "host reproduction selected build record",
    )
    (
        validated_e2e,
        e2e_file_sha256,
        bound_records,
        package_path,
        package_record,
    ) = services['_validate_e2e_evidence'](
        e2e_path,
        selected_record_path,
        catalog_path,
        catalog,
        expected_catalog_file_sha256=catalog_file_sha256,
    )
    targets: dict[str, dict] = {}
    for arch, (record, record_path, record_sha256) in sorted(
        bound_records.items()
    ):
        recipe = record.get("recipe")
        if (
            "core_group" in record
            or "tuning_candidate" in record
            or "source_candidate" in record
            or not isinstance(recipe, services['Mapping'])
            or "chipset_tuning" in recipe
            or not isinstance(recipe.get("host_execution"), services['Mapping'])
        ):
            raise services['PipelineError'](
                "host reproduction rejects grouped, tuned, or candidate evidence"
            )
        artifact_path = services['safe_child'](
            record_path.parent,
            record.get("artifact", {}).get("path", ""),
            f"host reproduction {arch} artifact",
        )
        metadata_path = services['safe_child'](
            record_path.parent,
            record.get("metadata", {}).get("path", ""),
            f"host reproduction {arch} metadata",
        )
        log_path = services['safe_child'](
            record_path.parent,
            record.get("build", {}).get("log", ""),
            f"host reproduction {arch} build log",
        )
        targets[arch] = {
            "record": record,
            "record_path": record_path,
            "record_sha256": record_sha256,
            "artifact_path": artifact_path,
            "metadata_path": metadata_path,
            "log_path": log_path,
        }
    final_catalog, final_catalog_sha256 = services['load_json_with_sha256'](catalog_path)
    if final_catalog != catalog or final_catalog_sha256 != catalog_file_sha256:
        raise services['PipelineError']("canonical catalog changed during host reproduction")
    return {
        "e2e": validated_e2e,
        "e2e_path": e2e_path,
        "e2e_file_sha256": e2e_file_sha256,
        "core_id": expected_core,
        "targets": targets,
        "package_path": package_path,
        "package_record": package_record,
    }


def require_host_reproduction_equivalence(
    selected: Mapping[str, object],
    reproduction: Mapping[str, object],
    *,
    services: EvidenceValidationServices,
) -> tuple[dict[str, str], dict]:
    """Require independent hardened hosts with exact deterministic outputs."""

    selected_e2e = selected.get("e2e")
    reproduction_e2e = reproduction.get("e2e")
    selected_targets = selected.get("targets")
    reproduction_targets = reproduction.get("targets")
    if (
        not isinstance(selected_e2e, services['Mapping'])
        or not isinstance(reproduction_e2e, services['Mapping'])
        or not services['runner_evidence_is_hardened'](selected_e2e.get("runner"))
        or not services['runner_evidence_is_hardened'](reproduction_e2e.get("runner"))
        or not isinstance(selected_targets, services['Mapping'])
        or not isinstance(reproduction_targets, services['Mapping'])
        or not selected_targets
        or set(selected_targets) != set(reproduction_targets)
    ):
        raise services['PipelineError'](
            "host reproduction requires two complete hardened E2E runs"
        )
    services['require_selected_reproduction_runner_pair'](selected_e2e, reproduction_e2e)
    selected_record_paths = {
        target.get("record_path")
        for target in selected_targets.values()
        if isinstance(target, services['Mapping'])
    }
    reproduction_record_paths = {
        target.get("record_path")
        for target in reproduction_targets.values()
        if isinstance(target, services['Mapping'])
    }
    selected_log_paths = {
        target.get("log_path")
        for target in selected_targets.values()
        if isinstance(target, services['Mapping'])
    }
    reproduction_log_paths = {
        target.get("log_path")
        for target in reproduction_targets.values()
        if isinstance(target, services['Mapping'])
    }
    if (
        selected.get("e2e_path") == reproduction.get("e2e_path")
        or selected_e2e.get("run_id") == reproduction_e2e.get("run_id")
        or selected_record_paths & reproduction_record_paths
        or selected_log_paths & reproduction_log_paths
    ):
        raise services['PipelineError'](
            "host reproduction requires two independent E2E executions"
        )
    selected_records = {
        arch: target.get("record")
        for arch, target in selected_targets.items()
        if isinstance(target, services['Mapping'])
    }
    reproduction_records = {
        arch: target.get("record")
        for arch, target in reproduction_targets.items()
        if isinstance(target, services['Mapping'])
    }
    if (
        set(selected_records) != set(selected_targets)
        or set(reproduction_records) != set(reproduction_targets)
        or any(
            not isinstance(record, services['Mapping'])
            for record in (*selected_records.values(), *reproduction_records.values())
        )
    ):
        raise services['PipelineError']("host reproduction build records are incomplete")
    selected_identities = {
        arch: services['host_reproduction_build_identity'](record)
        for arch, record in sorted(selected_records.items())
        if isinstance(record, services['Mapping'])
    }
    reproduction_identities = {
        arch: services['host_reproduction_build_identity'](record)
        for arch, record in sorted(reproduction_records.items())
        if isinstance(record, services['Mapping'])
    }
    if selected_identities != reproduction_identities:
        raise services['PipelineError'](
            "host reproduction source, recipe, toolchain, or build differs"
        )
    selected_package = selected.get("package_record")
    reproduction_package = reproduction.get("package_record")
    if not isinstance(selected_package, services['Mapping']) or not isinstance(
        reproduction_package, services['Mapping']
    ):
        raise services['PipelineError']("host reproduction package records are missing")
    outputs = services['host_reproduction_output_identity'](
        selected_records, selected_package
    )
    if outputs != services['host_reproduction_output_identity'](
        reproduction_records, reproduction_package
    ):
        raise services['PipelineError'](
            "host reproduction artifact, metadata, or package bytes differ"
        )
    build_digests = {
        arch: services['sha256_bytes'](
            services['json'].dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        )
        for arch, identity in sorted(selected_identities.items())
    }
    return build_digests, services['copy'].deepcopy(outputs)


def create_host_reproduction_proof(
    selected: Mapping[str, object],
    reproduction: Mapping[str, object],
    *,
    selected_e2e_record: Mapping[str, object],
    reproduction_e2e_record: Mapping[str, object],
    services: EvidenceValidationServices,
) -> dict:
    """Create one self-hashed proof from an already validated hardened pair."""

    if not services['_stored_reference_is_well_formed'](selected_e2e_record) or not (
        services['_stored_reference_is_well_formed'](reproduction_e2e_record)
    ):
        raise services['PipelineError']("host reproduction E2E store identity is invalid")
    equivalent_builds, equivalent_outputs = (
        services['require_host_reproduction_equivalence'](selected, reproduction)
    )
    selected_e2e = selected.get("e2e")
    reproduction_e2e = reproduction.get("e2e")
    assert isinstance(selected_e2e, services['Mapping'])
    assert isinstance(reproduction_e2e, services['Mapping'])
    proof = {
        "schema_version": 1,
        "validation_scope": services['HOST_REPRODUCTION_SCOPE'],
        "selected": {
            "run_id": selected_e2e["run_id"],
            "content_sha256": selected_e2e["content_sha256"],
            "e2e_record": services['copy'].deepcopy(dict(selected_e2e_record)),
        },
        "reproduction": {
            "run_id": reproduction_e2e["run_id"],
            "content_sha256": reproduction_e2e["content_sha256"],
            "e2e_record": services['copy'].deepcopy(dict(reproduction_e2e_record)),
        },
        "equivalent_builds": equivalent_builds,
        "equivalent_outputs": equivalent_outputs,
    }
    proof["content_sha256"] = services['host_reproduction_content_sha256'](proof)
    return proof
