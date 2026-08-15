"""Catalog, source-candidate, artifact, and workflow validation.

The launcher remains the composition root. Global dependencies are captured in
a filtered call-time service record so legacy wrappers and monkeypatch seams
remain dynamic without introducing a reverse import.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .source_candidate import SourceCandidateContractProjection


@dataclass(frozen=True, slots=True)
class CatalogValidationServices:
    """Call-time namespace required by this pipeline domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "CatalogValidationServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"missing pipeline services: {names}")
        guard_names = {
            guard_name
            for guard_name, _validator, _message in namespace[
                "SPEC_GUARDS"
            ].values()
        }
        guard_overrides = guard_names.intersection(namespace)
        captured_names = _REQUIRED_BINDINGS | guard_overrides
        return cls(
            MappingProxyType(
                {name: namespace[name] for name in captured_names}
            )
        )


def required_binding_names() -> frozenset[str]:
    """Return the exact launcher bindings consumed by this leaf."""

    return _REQUIRED_BINDINGS


_REQUIRED_BINDINGS = frozenset(
    {
        'A5200_CORE_ID',
        'AGGREGATE_WORKFLOW_GLOBS',
        'ARCH_LAYOUT',
        'CORE_81_ID',
        'DEFAULT_CATALOG',
        'DEFAULT_NIGHTLIES',
        'DEFAULT_PIN_SET_DIR',
        'EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS',
        'GROUP_PIN_SOURCE_KEYS',
        'GROUP_PIN_SUBMODULE_KEYS',
        'Mapping',
        'NATIVE_GIT_VERSION_DERIVATION',
        'NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES',
        'NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES',
        'NATIVE_GIT_VERSION_SPEC_IDENTITIES',
        'NESTOPIA_CORE_ID',
        'O2EM_CORE_ID',
        'PICODRIVE_CORE_ID',
        'Path',
        'PipelineError',
        'QUICKNES_CORE_ID',
        'REQUIRED_LIBRETRO_SYMBOLS',
        'ROOT',
        'SHA1_RE',
        'SHA256_RE',
        'SNES9X_CORE_ID',
        'SPEC_GUARDS',
        'SourceCandidateContractProjection',
        'VECX_SOFTWARE_MAKE_PROFILE',
        'VECX_SOFTWARE_SPEC_IDENTITY',
        '_canonical_source_candidate_spec',
        '_group_submodule_path_is_safe',
        '_recorded_source_matches_source_candidate_projection',
        '_source_candidate_contract_spec',
        '_validate_catalog',
        '_validate_source_candidate_execution_catalog',
        'a5200_spec_is_well_formed',
        'audit_release_workflows',
        'container_build_script',
        'copy',
        'core_81_spec_is_well_formed',
        'core_spec_sha256',
        'core_workflows',
        'defined_libretro_symbols',
        'exact_native_git_describe_contract',
        'exact_native_git_version_contract',
        'json',
        'load_catalog_commit_blacklist',
        'load_catalog_toolchain_lock',
        'load_catalog_with_sha256',
        'load_json_with_sha256',
        'make_variable_profile',
        'native_git_describe_spec_is_well_formed',
        'native_git_version_short10_spec_is_well_formed',
        'native_git_version_short9_spec_is_well_formed',
        'native_git_version_spec_is_well_formed',
        'nestopia_spec_is_well_formed',
        'o2em_spec_is_well_formed',
        'picodrive_spec_is_well_formed',
        'pipeline_source_bundle_is_well_formed',
        'quicknes_spec_is_well_formed',
        're',
        'readelf_header',
        'render_source_candidate_build_contract',
        'require_canonical_store_entry',
        'require_catalog_cores_eligible',
        'require_lexical_repository_path',
        'run',
        'sha256_bytes',
        'sha256_file',
        'snes9x_spec_is_well_formed',
        'source_aware_candidate_contract_is_registered',
        'source_candidate_record_contract_projection',
        'tempfile',
        'validate_artifact',
        'validate_build_overlays',
        'validate_catalog',
        'validate_promoted_source_candidate_contract',
        'validate_source_candidate_catalog',
        'validated_compile_definitions',
        'validated_direct_cargo',
        'validated_direct_cmake',
        'validated_embedded_source_candidate_shape',
        'validated_forbidden_needed_prefixes',
        'validated_generated_source',
        'validated_git_version',
        'validated_make_variables',
        'validated_metadata_replacement',
        'validated_recipe_profile',
        'validated_source_candidate_contract_projection',
        'validated_source_date_epoch',
        'vecx_software_spec_is_well_formed',
        'verified_json_object',
    }
)


def _validate_catalog(
    catalog: dict,
    *,
    source_candidate_contract_context: tuple[
        str, dict, SourceCandidateContractProjection
    ]
    | None = None,
    services: CatalogValidationServices,
) -> None:
    errors: list[str] = []
    if type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 2:
        errors.append("schema_version must be the exact integer 2")
    if catalog.get("policy", {}).get("publication") != "disabled":
        errors.append("policy.publication must be disabled")
    if "exact_toolchain_archive_lock" not in catalog.get("policy", {}).get(
        "promotion_requires", []
    ):
        errors.append("policy.promotion_requires must include exact_toolchain_archive_lock")
    if "source_commit_not_actively_blacklisted" not in catalog.get(
        "policy", {}
    ).get("promotion_requires", []):
        errors.append(
            "policy.promotion_requires must include "
            "source_commit_not_actively_blacklisted"
        )
    try:
        services['load_catalog_commit_blacklist'](catalog)
    except services['PipelineError'] as exc:
        errors.append(str(exc))
    locked_toolchains: dict | None = None
    try:
        lock, _, _ = services['load_catalog_toolchain_lock'](catalog)
        locked_toolchains = lock["toolchains"]
    except services['PipelineError'] as exc:
        errors.append(str(exc))
    toolchains = catalog.get("toolchains", {})
    # The mirror must cover every locked entry: the two C cross images plus
    # the Rust image the direct-cargo driver builds inside.
    if locked_toolchains is not None and set(toolchains) != set(locked_toolchains):
        errors.append("toolchains mirror does not cover the archive lock entries")
    for arch in (*services['ARCH_LAYOUT'], "rust"):
        toolchain = toolchains.get(arch, {})
        image_id = toolchain.get("image_id", "")
        dockerfile_digest = toolchain.get("dockerfile_sha256", "")
        if not services['re'].fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            errors.append(f"toolchains.{arch}.image_id is not an exact SHA256 ID")
        if not services['SHA256_RE'].fullmatch(dockerfile_digest):
            errors.append(f"toolchains.{arch}.dockerfile_sha256 is invalid")
        if toolchain.get("dockerfile_linkage") != "unverified-local-cache":
            errors.append(
                f"toolchains.{arch}.dockerfile_linkage must preserve the unverified cache status"
            )
        dockerfile = services['ROOT'] / toolchain.get("dockerfile", "")
        if not dockerfile.is_file():
            errors.append(f"toolchains.{arch}.dockerfile does not exist")
        elif services['sha256_file'](dockerfile) != dockerfile_digest:
            errors.append(f"toolchains.{arch}.dockerfile_sha256 does not match")
        if locked_toolchains is not None:
            locked = locked_toolchains[arch]
            if toolchain.get("image") != locked["image"].get("tag"):
                errors.append(f"toolchains.{arch}.image does not match the archive lock")
            if image_id != locked["image"].get("id"):
                errors.append(f"toolchains.{arch}.image_id does not match the archive lock")
            if toolchain.get("dockerfile") != locked["dockerfile"].get("path"):
                errors.append(
                    f"toolchains.{arch}.dockerfile does not match the archive lock"
                )
            if dockerfile_digest != locked["dockerfile"].get("sha256"):
                errors.append(
                    f"toolchains.{arch}.dockerfile_sha256 does not match the archive lock"
                )
            if toolchain.get("dockerfile_linkage") != locked["dockerfile"].get(
                "linkage"
            ):
                errors.append(
                    f"toolchains.{arch}.dockerfile_linkage does not match the archive lock"
                )
    resolver = catalog.get("resolver", {})
    if not services['SHA1_RE'].fullmatch(resolver.get("libretro_super_commit", "")):
        errors.append("resolver.libretro_super_commit is not a full SHA")
    for prefix in ("core_rules", "fetch_script", "build_script"):
        raw_path = resolver.get(f"{prefix}_path", "")
        relative = services['Path'](raw_path)
        if not raw_path or relative.is_absolute() or ".." in relative.parts:
            errors.append(f"resolver.{prefix}_path is not a safe relative path")
        if not services['SHA256_RE'].fullmatch(resolver.get(f"{prefix}_sha256", "")):
            errors.append(f"resolver.{prefix}_sha256 is invalid")
    workflows = services['core_workflows']()
    cores = catalog.get("cores", {})
    if not isinstance(cores, dict) or not cores:
        errors.append("cores must be a non-empty object")
    else:
        contract_specs: dict[str, dict] = {}
        if source_candidate_contract_context is not None:
            candidate_core, canonical_spec, projection = (
                source_candidate_contract_context
            )
            try:
                if set(cores) != {candidate_core}:
                    raise services['PipelineError'](
                        "source-candidate contract context core set is invalid"
                    )
                embedded = services['validated_embedded_source_candidate_shape'](
                    catalog.get("source_candidate"),
                    core_id=candidate_core,
                )
                current_canonical_spec = services['_canonical_source_candidate_spec'](
                    embedded, candidate_core
                )
                if canonical_spec != current_canonical_spec:
                    raise services['PipelineError'](
                        "source-candidate canonical contract spec is not current"
                    )
                expected_projection = services['validated_source_candidate_contract_projection'](
                    embedded,
                    core_id=candidate_core,
                    canonical_spec=canonical_spec,
                    execution_spec=cores[candidate_core],
                    source_aware_log_contract=(
                        services['source_aware_candidate_contract_is_registered'](candidate_core)
                    ),
                )
                if projection != expected_projection:
                    raise services['PipelineError'](
                        "source-candidate authenticated contract projection differs"
                    )
                services['_source_candidate_contract_spec'](
                    candidate_core,
                    cores[candidate_core],
                    canonical_spec,
                    projection,
                )
                contract_specs[candidate_core] = canonical_spec
            except services['PipelineError'] as exc:
                errors.append(str(exc))
        for core_id, spec in cores.items():
            source = spec.get("source", {})
            commit = source.get("commit", "")
            if not isinstance(commit, str) or not services['SHA1_RE'].fullmatch(commit):
                errors.append(f"cores.{core_id}.source.commit is not a full SHA")
            source_tree = source.get("tree")
            if "tree" in source and (
                not isinstance(source_tree, str) or not services['SHA1_RE'].fullmatch(source_tree)
            ):
                errors.append(f"cores.{core_id}.source.tree is not a full SHA")
            workflow = spec.get("workflow", "")
            if core_id not in workflows:
                errors.append(f"cores.{core_id} has no core workflow")
            elif workflow != str(workflows[core_id].relative_to(services['ROOT'])):
                errors.append(f"cores.{core_id}.workflow does not match its workflow path")
            targets = spec.get("targets")
            if not targets or any(target not in services['ARCH_LAYOUT'] for target in targets):
                errors.append(f"cores.{core_id}.targets is invalid")
            driver = spec.get("build", {}).get("driver")
            if driver not in {"libretro-super", "direct-make", "direct-cmake", "direct-cargo"}:
                errors.append(f"cores.{core_id}.build.driver is unsupported")
            spec = contract_specs.get(core_id, spec)
            try:
                services['validated_compile_definitions'](spec)
                make_variables = services['validated_make_variables'](spec)
                git_version = services['validated_git_version'](spec)
                services['validated_generated_source'](spec)
                recipe_profile = services['validated_recipe_profile'](spec)
                services['validated_source_date_epoch'](spec)
                metadata_replacement = services['validated_metadata_replacement'](spec)
                services['validated_direct_cmake'](spec, core_id)
                services['validated_direct_cargo'](spec, core_id)
                services['validate_build_overlays'](
                    spec.get("build", {}).get("overlays", {}),
                    core_id,
                    spec.get("build", {}).get("source_dir", ""),
                    spec.get("targets", []),
                )
                services['validated_forbidden_needed_prefixes'](spec)
                if core_id == services['PICODRIVE_CORE_ID'] and (
                    not services['picodrive_spec_is_well_formed'](spec)
                    or recipe_profile is None
                ):
                    raise services['PipelineError'](
                        "the picodrive core must preserve its exact source-root "
                        "recipe, source, metadata, target, and dependency contract"
                    )
                spec_guard = services['SPEC_GUARDS'].get(core_id)
                if spec_guard is not None:
                    guard_name, guard_validator, guard_message = spec_guard
                    # Resolve through the launcher namespace first: focused
                    # boundary tests replace one validator at a time by
                    # patching the pipeline attribute, and that seam must
                    # keep working now that dispatch is registry-driven.
                    guard_validator = services.namespace.get(
                        guard_name, guard_validator
                    )
                    if not guard_validator(spec):
                        raise services['PipelineError'](guard_message)
                if core_id == services['QUICKNES_CORE_ID'] and not services['quicknes_spec_is_well_formed'](
                    spec
                ):
                    raise services['PipelineError'](
                        "the quicknes core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == services['NESTOPIA_CORE_ID'] and not services['nestopia_spec_is_well_formed'](
                    spec
                ):
                    raise services['PipelineError'](
                        "the nestopia core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == services['A5200_CORE_ID'] and not services['a5200_spec_is_well_formed'](spec):
                    raise services['PipelineError'](
                        "the a5200 core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == services['SNES9X_CORE_ID'] and not services['snes9x_spec_is_well_formed'](
                    spec
                ):
                    raise services['PipelineError'](
                        "the snes9x core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == services['O2EM_CORE_ID'] and not services['o2em_spec_is_well_formed'](
                    spec
                ):
                    raise services['PipelineError'](
                        "the o2em core must preserve its exact native version, "
                        "source, recipe, metadata, and target contract"
                    )
                if core_id == services['CORE_81_ID'] and not services['core_81_spec_is_well_formed'](
                    spec
                ):
                    raise services['PipelineError'](
                        "the 81 core must preserve its exact native generated "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == "vecx" and (
                    not services['vecx_software_spec_is_well_formed'](spec)
                    or services['make_variable_profile'](make_variables)
                    != services['VECX_SOFTWARE_MAKE_PROFILE']
                    or git_version
                    != {
                        "derivation": services['NATIVE_GIT_VERSION_DERIVATION'],
                        "value": f" {services['VECX_SOFTWARE_SPEC_IDENTITY']['source_commit'][:7]}",
                    }
                    or metadata_replacement is None
                ):
                    raise services['PipelineError'](
                        "the vecx core must preserve the exact VecX software "
                        "make, version, metadata, target, and dependency contract"
                    )
                if core_id in services['NATIVE_GIT_VERSION_SPEC_IDENTITIES']:
                    identity = services['NATIVE_GIT_VERSION_SPEC_IDENTITIES'][core_id]
                    expected_git_version = {
                        "derivation": services['NATIVE_GIT_VERSION_DERIVATION'],
                        "value": f" {identity['source_commit'][:7]}",
                    }
                    if identity.get("compiler_scope") is not None:
                        expected_git_version["compiler_scope"] = identity[
                            "compiler_scope"
                        ]
                    if (
                        not services['native_git_version_spec_is_well_formed'](spec, core_id)
                        or git_version != expected_git_version
                    ):
                        raise services['PipelineError'](
                            f"the {core_id} core must preserve its exact native "
                            "version, source, recipe, metadata, and target contract"
                        )
                if core_id in services['NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES']:
                    if (
                        not services['native_git_version_short9_spec_is_well_formed'](
                            spec, core_id
                        )
                        or git_version
                        != services['exact_native_git_version_contract'](core_id)
                    ):
                        raise services['PipelineError'](
                            f"the {core_id} core must preserve its exact native "
                            "short9 version, source, recipe, metadata, target, "
                            "compiler scope, and Git abbreviation contract"
                        )
                if core_id in services['NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES']:
                    if (
                        not services['native_git_version_short10_spec_is_well_formed'](
                            spec, core_id
                        )
                        or git_version
                        != services['exact_native_git_version_contract'](core_id)
                    ):
                        raise services['PipelineError'](
                            f"the {core_id} core must preserve its exact native "
                            "short10 version, source, epoch, recipe, metadata, "
                            "target, and Git abbreviation contract"
                        )
                if core_id in services['EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS']:
                    expected_git_version = services['exact_native_git_describe_contract'](core_id)
                    if (
                        not services['native_git_describe_spec_is_well_formed'](spec, core_id)
                        or git_version != expected_git_version
                    ):
                        raise services['PipelineError'](
                            f"the {core_id} core must preserve its exact native git "
                            "describe, source, recipe, metadata, target, and "
                            "compiler-macro contract"
                        )
            except services['PipelineError'] as exc:
                errors.append(f"cores.{core_id}.{exc}")
            metadata = spec.get("metadata", {})
            expected_info = f"{core_id}_libretro.info"
            if metadata.get("artifact_name") != expected_info:
                errors.append(f"cores.{core_id}.metadata.artifact_name must be {expected_info}")
            if "repo_path" in metadata:
                # Repo-pinned metadata: for cores whose .info does not exist in
                # the image's libretro-super checkout (the KMFDManic forks have
                # no upstream rule at all). The reviewed file lives under
                # metadata/ and is pinned by sha256, so the deployed metadata is
                # exactly the bytes SpruceOS ships.
                expected_repo = {
                    "repo_path": f"metadata/{expected_info}",
                    "sha256": metadata.get("sha256"),
                    "artifact_name": expected_info,
                }
                if metadata != expected_repo or not (
                    isinstance(metadata.get("sha256"), str)
                    and services['SHA256_RE'].fullmatch(metadata["sha256"])
                ):
                    errors.append(
                        f"cores.{core_id}.metadata repo-pinned form is malformed"
                    )
                else:
                    repo_file = services['ROOT'] / metadata["repo_path"]
                    if not repo_file.is_file():
                        errors.append(
                            f"cores.{core_id}.metadata.repo_path does not exist"
                        )
                    elif services['sha256_file'](repo_file) != metadata["sha256"]:
                        errors.append(
                            f"cores.{core_id}.metadata.sha256 does not match the file"
                        )
            elif metadata.get("source_path") != f"/libretro-super/dist/info/{expected_info}":
                errors.append(f"cores.{core_id}.metadata.source_path is invalid")
    if errors:
        raise services['PipelineError']("invalid build catalog:\n- " + "\n- ".join(errors))


def validate_catalog(catalog: dict, *, services: CatalogValidationServices) -> None:
    """Validate an ordinary catalog without any source-contract relaxation."""

    if "source_candidate" in catalog:
        raise services['PipelineError'](
            "ordinary catalog validation rejects source-candidate provenance"
        )
    services['_validate_catalog'](catalog)


def _validate_source_candidate_execution_catalog(
    catalog: dict,
    core_id: str,
    canonical_spec: dict,
    projection: SourceCandidateContractProjection | None,
    *,
    services: CatalogValidationServices,
) -> None:
    """Validate one proven execution spec against its canonical guard spec."""

    cores = catalog.get("cores")
    if not isinstance(cores, dict) or set(cores) != {core_id}:
        raise services['PipelineError']("source-candidate execution catalog core set is invalid")
    if projection is None:
        services['_validate_catalog'](catalog)
        return
    services['_source_candidate_contract_spec'](core_id, cores[core_id], canonical_spec, projection)
    services['_validate_catalog'](
        catalog,
        source_candidate_contract_context=(core_id, canonical_spec, projection),
    )


def render_source_candidate_build_contract(
    core_id: str,
    arch: str,
    execution_spec: dict,
    resolver: dict,
    canonical_spec: dict,
    projection: SourceCandidateContractProjection | None,
    *,
    services: CatalogValidationServices,
) -> str:
    if projection is None:
        return services['container_build_script'](core_id, arch, execution_spec, resolver)
    return services['container_build_script'](
        core_id,
        arch,
        execution_spec,
        resolver,
        source_candidate_contract_spec=canonical_spec,
        source_candidate_projection=projection,
    )


def load_catalog_with_sha256(path: Path, *, services: CatalogValidationServices) -> tuple[dict, str]:
    """Load one catalog and bind all validation to its exact byte snapshot."""

    catalog, file_sha256 = services['load_json_with_sha256'](path)
    if "source_candidate" not in catalog:
        services['validate_catalog'](catalog)
    else:
        report = services['validate_source_candidate_catalog'](
            repository_root=services['ROOT'],
            canonical_catalog_path=services['DEFAULT_CATALOG'],
            candidate_catalog_path=path,
            catalog_validator=services['validate_catalog'],
            candidate_catalog_validator=services['_validate_source_candidate_execution_catalog'],
            eligibility_validator=services['require_catalog_cores_eligible'],
            build_renderer=services['render_source_candidate_build_contract'],
            source_aware_contract_resolver=(
                services['source_aware_candidate_contract_is_registered']
            ),
        )
        if (
            report.get("status") != "valid"
            or report.get("catalog", {}).get("file_sha256") != file_sha256
        ):
            raise services['PipelineError'](
                "source-candidate catalog changed during authenticated load"
            )
        final_catalog, final_file_sha256 = services['load_json_with_sha256'](path)
        if final_catalog != catalog or final_file_sha256 != file_sha256:
            raise services['PipelineError'](
                "source-candidate catalog changed during authenticated load"
            )
    return catalog, file_sha256


def load_catalog(path: Path, *, services: CatalogValidationServices) -> dict:
    catalog, _file_sha256 = services['load_catalog_with_sha256'](path)
    return catalog


def _canonical_source_candidate_spec(
    provenance: Mapping[str, object],
    core_id: str,
    *,
    services: CatalogValidationServices,
) -> dict:
    canonical, _canonical_sha256 = services['load_json_with_sha256'](services['DEFAULT_CATALOG'])
    services['validate_catalog'](canonical)
    base_catalog = provenance.get("base_catalog")
    cores = canonical.get("cores")
    if (
        not isinstance(base_catalog, services['Mapping'])
        or not isinstance(cores, services['Mapping'])
        or core_id not in cores
        or services['core_spec_sha256'](cores[core_id])
        != base_catalog.get("core_spec_sha256")
    ):
        raise services['PipelineError'](
            "source-candidate contract is not bound to the current canonical recipe"
        )
    return services['copy'].deepcopy(cores[core_id])


def source_candidate_contract_context(
    catalog: Mapping[str, object],
    core_id: str,
    *,
    catalog_path: Path | None = None,
    services: CatalogValidationServices,
) -> tuple[dict, SourceCandidateContractProjection | None]:
    cores = catalog.get("cores")
    if not isinstance(cores, services['Mapping']) or core_id not in cores:
        raise services['PipelineError']("source-candidate contract core is not cataloged")
    execution_spec = services['copy'].deepcopy(cores[core_id])
    provenance = catalog.get("source_candidate")
    if provenance is None:
        return execution_spec, None
    if catalog_path is None:
        raise services['PipelineError'](
            "source-candidate contract requires its authenticated catalog path"
        )
    authenticated_catalog, _catalog_sha256 = services['load_catalog_with_sha256'](catalog_path)
    if authenticated_catalog != catalog:
        raise services['PipelineError'](
            "source-candidate contract catalog differs from authenticated bytes"
        )
    embedded = services['validated_embedded_source_candidate_shape'](
        provenance,
        core_id=core_id,
    )
    selection = embedded["selection"]
    source_aware = services['source_aware_candidate_contract_is_registered'](core_id)
    if (
        not source_aware
        or selection["status"] != "fast-forward"
        or selection["commit"] == selection["catalog_commit"]
    ):
        return execution_spec, None
    canonical_spec = services['_canonical_source_candidate_spec'](embedded, core_id)
    projection = services['validated_source_candidate_contract_projection'](
        embedded,
        core_id=core_id,
        canonical_spec=canonical_spec,
        execution_spec=execution_spec,
        source_aware_log_contract=source_aware,
    )
    return canonical_spec, projection


def _recorded_source_matches_source_candidate_projection(
    recorded_source: object,
    projection: SourceCandidateContractProjection,
    *,
    services: CatalogValidationServices,
) -> bool:
    """Bind persisted source bytes to one authenticated candidate projection."""

    if (
        not isinstance(recorded_source, services['Mapping'])
        or set(recorded_source) != services['GROUP_PIN_SOURCE_KEYS']
        or recorded_source.get("url") != projection.source_url
        or recorded_source.get("resolved_url") != projection.source_url
        or recorded_source.get("requested_ref") != projection.requested_ref
        or recorded_source.get("commit") != projection.candidate_commit
        or recorded_source.get("resolved_commit") != projection.candidate_commit
        or recorded_source.get("tree") != projection.candidate_tree
    ):
        return False
    recorded_submodules = recorded_source.get("submodules")
    if not isinstance(recorded_submodules, list):
        return False
    if any(
        not isinstance(item, services['Mapping'])
        or set(item) != services['GROUP_PIN_SUBMODULE_KEYS']
        or item.get("state") != " "
        or not services['_group_submodule_path_is_safe'](item.get("path"))
        or not isinstance(item.get("commit"), str)
        or services['SHA1_RE'].fullmatch(item["commit"]) is None
        for item in recorded_submodules
    ):
        return False
    recorded_pairs = [
        (item["path"], item["commit"])
        for item in recorded_submodules
    ]
    recorded_paths = [path for path, _commit in recorded_pairs]
    if (
        recorded_paths != sorted(recorded_paths)
        or len(recorded_paths) != len(set(recorded_paths))
    ):
        return False
    expected_top_level = dict(projection.candidate_submodules)
    recorded = dict(recorded_pairs)
    if any(recorded.get(path) != commit for path, commit in expected_top_level.items()):
        return False
    # v1 authenticates the root tree and exact top-level gitlinks.  Recursive
    # descendants are retained in the full source record and dual-E2E identity;
    # admit only clean unique descendants of an authenticated top-level path.
    return all(
        path in expected_top_level
        or any(path.startswith(f"{parent}/") for parent in expected_top_level)
        for path in recorded
    )


def _source_candidate_contract_source_for_guard(
    source: object,
    projection: SourceCandidateContractProjection | None,
    *,
    services: CatalogValidationServices,
) -> object:
    if projection is None or not isinstance(source, services['Mapping']):
        return source
    contract_source = services['copy'].deepcopy(dict(source))
    contract_source.update(
        {
            "commit": projection.canonical_commit,
            "tree": projection.canonical_tree,
            "resolved_commit": projection.canonical_commit,
        }
    )
    return contract_source


def _source_candidate_contract_build_for_guard(
    build: object,
    projection: SourceCandidateContractProjection | None,
    *,
    services: CatalogValidationServices,
) -> object:
    if projection is None or not isinstance(build, services['Mapping']):
        return build
    contract_build = services['copy'].deepcopy(dict(build))
    if projection.canonical_source_date_epoch is None:
        contract_build.pop("source_date_epoch", None)
    else:
        contract_build["source_date_epoch"] = (
            projection.canonical_source_date_epoch
        )
    return contract_build


def source_candidate_record_contract_projection(
    provenance: object,
    *,
    core_id: str,
    recorded_source: object,
    recorded_recipe: object,
    recipe_snapshot: object,
    services: CatalogValidationServices,
) -> SourceCandidateContractProjection | None:
    if provenance is None:
        return None
    embedded = services['validated_embedded_source_candidate_shape'](
        provenance,
        core_id=core_id,
    )
    selection = embedded["selection"]
    if not isinstance(recorded_recipe, services['Mapping']):
        raise services['PipelineError']("source-candidate contract record recipe is missing")
    if (
        not isinstance(recipe_snapshot, services['Mapping'])
        or recipe_snapshot.get("recipe") != recorded_recipe
        or not isinstance(recipe_snapshot.get("files"), services['Mapping'])
    ):
        raise services['PipelineError']("source-candidate frozen recipe snapshot is invalid")
    catalog_relative = recorded_recipe.get("catalog_path")
    catalog_sha256 = recorded_recipe.get("catalog_sha256")
    pipeline_bundle = recorded_recipe.get("pipeline_bundle")
    generator_path = embedded["generator"].get("path")
    if (
        not isinstance(catalog_relative, str)
        or not isinstance(catalog_sha256, str)
        or services['SHA256_RE'].fullmatch(catalog_sha256) is None
        or generator_path != "scripts/core_pipeline_lib/source_candidate.py"
        or not services['pipeline_source_bundle_is_well_formed'](pipeline_bundle)
        or pipeline_bundle["files"].get(generator_path)
        != embedded["generator"]["sha256"]
    ):
        raise services['PipelineError']("source-candidate contract recipe catalog is invalid")
    files = recipe_snapshot["files"]
    catalog_entry = files.get(catalog_relative)
    generator_entry = files.get(generator_path)
    if (
        not isinstance(catalog_entry, services['Mapping'])
        or set(catalog_entry) != {"sha256", "text"}
        or not isinstance(catalog_entry.get("text"), str)
        or services['sha256_bytes'](catalog_entry["text"].encode()) != catalog_sha256
        or catalog_entry.get("sha256") != catalog_sha256
        or not isinstance(generator_entry, services['Mapping'])
        or set(generator_entry) != {"sha256", "text"}
        or not isinstance(generator_entry.get("text"), str)
        or services['sha256_bytes'](generator_entry["text"].encode())
        != embedded["generator"]["sha256"]
        or generator_entry.get("sha256") != embedded["generator"]["sha256"]
    ):
        raise services['PipelineError'](
            "source-candidate frozen catalog/generator binding is invalid"
        )
    try:
        candidate_catalog = services['json'].loads(catalog_entry["text"])
    except (TypeError, services['json'].JSONDecodeError) as exc:
        raise services['PipelineError'](
            "source-candidate frozen catalog is not valid JSON"
        ) from exc
    if (
        not isinstance(candidate_catalog, dict)
        or catalog_entry["text"].encode()
        != (services['json'].dumps(candidate_catalog, indent=2, sort_keys=True) + "\n").encode()
        or candidate_catalog.get("source_candidate") != embedded
        or set(candidate_catalog.get("cores", {})) != {core_id}
    ):
        raise services['PipelineError'](
            "source-candidate contract recipe catalog binding is invalid"
        )
    projection = services['validate_promoted_source_candidate_contract'](
        repository_root=services['ROOT'],
        canonical_catalog_path=services['DEFAULT_CATALOG'],
        candidate_catalog=candidate_catalog,
        catalog_validator=services['validate_catalog'],
        source_aware_contract_resolver=(
            services['source_aware_candidate_contract_is_registered']
        ),
    )
    needs_contract_projection = bool(
        services['source_aware_candidate_contract_is_registered'](core_id)
        and selection["status"] == "fast-forward"
        and selection["commit"] != selection["catalog_commit"]
    )
    if needs_contract_projection and projection is None:
        raise services['PipelineError']("source-candidate frozen contract projection is missing")
    recorded_source_projection = projection or services['SourceCandidateContractProjection'](
        core_id=core_id,
        candidate_id=embedded["candidate_id"],
        canonical_commit=selection["catalog_commit"],
        canonical_tree=selection["catalog_tree"],
        candidate_commit=selection["commit"],
        candidate_tree=selection["tree"],
        canonical_spec_sha256=embedded["base_catalog"]["core_spec_sha256"],
        execution_spec_sha256=embedded["execution"]["core_spec_sha256"],
        source_url=selection["url"],
        requested_ref=selection["requested_ref"],
        candidate_submodules=tuple(
            (item["path"], item["commit"])
            for item in selection["top_level_gitlinks"]
        ),
    )
    if not services['_recorded_source_matches_source_candidate_projection'](
        recorded_source,
        recorded_source_projection,
    ):
        raise services['PipelineError'](
            "source-candidate contract record source is not the authenticated execution"
        )
    return projection


def _golden_source_candidate_contract_projection(
    golden: Mapping[str, object],
    *,
    core_id: str,
    arch: str,
    services: CatalogValidationServices,
) -> SourceCandidateContractProjection | None:
    provenance = golden.get("source_candidate")
    if provenance is None:
        return None
    embedded = services['validated_embedded_source_candidate_shape'](
        provenance,
        core_id=core_id,
    )
    local_store = golden.get("local_store")
    recipe_references = (
        local_store.get("recipe_snapshots")
        if isinstance(local_store, services['Mapping'])
        else None
    )
    recipe_reference = (
        recipe_references.get(arch)
        if isinstance(recipe_references, services['Mapping'])
        else None
    )
    if not isinstance(recipe_reference, dict):
        raise services['PipelineError'](
            f"{core_id}/{arch} source-candidate frozen recipe is missing"
        )
    recipe_path = services['require_canonical_store_entry'](
        recipe_reference,
        "recipes",
        f"{core_id}/{arch} source-candidate frozen recipe",
    )
    recipe_snapshot = services['verified_json_object'](
        recipe_path,
        recipe_reference.get("sha256"),
        f"{core_id}/{arch} source-candidate frozen recipe",
    )
    return services['source_candidate_record_contract_projection'](
        embedded,
        core_id=core_id,
        recorded_source=golden.get("source"),
        recorded_recipe=golden.get("recipe"),
        recipe_snapshot=recipe_snapshot,
    )


def require_ordinary_promotion_catalog(
    catalog: Mapping[str, object],
    operation: str,
    catalog_path: Path,
    *,
    services: CatalogValidationServices,
) -> None:
    """Keep generated source candidates on their dual-E2E admission path."""

    if "source_candidate" in catalog:
        raise services['PipelineError'](
            f"{operation} rejects source-candidate catalogs; "
            "use promote-source-candidate"
        )
    if catalog_path.resolve() != services['DEFAULT_CATALOG'].resolve():
        raise services['PipelineError'](
            f"{operation} requires the exact canonical catalog path"
        )


def immutable_promotion_output_paths(
    semantic_id: str,
    *,
    label: str,
    services: CatalogValidationServices,
) -> tuple[Path, Path]:
    """Resolve create-only golden/pin targets without traversing symlinks."""

    golden_path = services['require_lexical_repository_path'](
        services['DEFAULT_NIGHTLIES'] / semantic_id / "golden.json",
        services['DEFAULT_NIGHTLIES'],
        f"{label} promoted golden",
    )
    pin_path = services['require_lexical_repository_path'](
        services['DEFAULT_PIN_SET_DIR'] / f"{semantic_id}.json",
        services['DEFAULT_PIN_SET_DIR'],
        f"{label} promoted pin",
    )
    return golden_path, pin_path


def readelf_header(path: Path, *, services: CatalogValidationServices) -> dict[str, str]:
    result = services['run'](["readelf", "-h", str(path)])
    wanted = {"Class", "Data", "Type", "Machine", "Flags"}
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in wanted:
            fields[key.lower()] = value.strip()
    missing = {item.lower() for item in wanted} - fields.keys()
    if missing:
        raise services['PipelineError'](f"readelf omitted {sorted(missing)} for {path}")
    return fields


def defined_libretro_symbols(readelf_output: str, *, services: CatalogValidationServices) -> set[str]:
    symbols: set[str] = set()
    for line in readelf_output.splitlines():
        fields = line.split()
        if len(fields) < 8 or not fields[0].rstrip(":").isdigit():
            continue
        symbol_type = fields[3]
        binding = fields[4]
        visibility = fields[5]
        section_index = fields[6]
        name = fields[7].split("@", 1)[0]
        if (
            symbol_type == "FUNC"
            and binding in {"GLOBAL", "WEAK"}
            and visibility in {"DEFAULT", "PROTECTED"}
            and section_index != "UND"
            and name.startswith("retro_")
        ):
            symbols.add(name)
    return symbols


def validate_artifact(path: Path, arch: str, *, services: CatalogValidationServices) -> dict:
    if arch not in services['ARCH_LAYOUT']:
        raise services['PipelineError'](f"unknown architecture: {arch}")
    if not path.is_file() or path.stat().st_size == 0:
        return {
            "status": "invalid",
            "errors": ["artifact is missing or empty"],
        }
    try:
        header = services['readelf_header'](path)
    except services['PipelineError'] as exc:
        return {"status": "invalid", "errors": [str(exc)]}
    expected = services['ARCH_LAYOUT'][arch]
    errors: list[str] = []
    if header["class"] != expected["elf_class"]:
        errors.append(f"expected {expected['elf_class']}, got {header['class']}")
    if "little endian" not in header["data"].lower():
        errors.append(f"expected little-endian ELF data, got {header['data']}")
    if header["machine"] != expected["machine"]:
        errors.append(f"expected {expected['machine']}, got {header['machine']}")
    if not header["type"].startswith("DYN"):
        errors.append(f"expected a shared object, got ELF type {header['type']}")
    if arch == "armhf" and "hard-float ABI" not in header["flags"]:
        errors.append("expected ARM hard-float ABI flag")
    dynamic = services['run'](["readelf", "-d", str(path)], check=False)
    needed = services['re'].findall(r"\(NEEDED\).*?\[([^]]+)\]", dynamic.stdout)
    if dynamic.returncode:
        errors.append("could not inspect dynamic dependencies")
    symbols = services['run'](["readelf", "--dyn-syms", "--wide", str(path)], check=False)
    found_symbols = services['defined_libretro_symbols'](symbols.stdout)
    missing_symbols = sorted(services['REQUIRED_LIBRETRO_SYMBOLS'] - found_symbols)
    if symbols.returncode:
        errors.append("could not inspect dynamic symbols")
    elif missing_symbols:
        errors.append("missing libretro symbols: " + ", ".join(missing_symbols))
    versions = services['run'](["readelf", "--version-info", "--wide", str(path)], check=False)
    version_requirements = sorted(set(services['re'].findall(r"Name:\s+(\S+)", versions.stdout)))
    if versions.returncode:
        errors.append("could not inspect dynamic version requirements")
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "elf": header,
        "needed": sorted(set(needed)),
        "version_requirements": version_requirements,
        "libretro_symbols": sorted(found_symbols),
        "size": path.stat().st_size,
        "sha256": services['sha256_file'](path),
    }


def _validate_artifact_bytes(artifact_bytes: bytes, arch: str, *, services: CatalogValidationServices) -> dict:
    """Run static artifact checks against one private immutable byte snapshot."""

    if not isinstance(artifact_bytes, bytes):
        raise services['PipelineError']("artifact snapshot must be bytes")
    with services['tempfile'].NamedTemporaryFile(
        "wb", prefix="core-pipeline-artifact-", suffix=".so"
    ) as handle:
        handle.write(artifact_bytes)
        handle.flush()
        return services['validate_artifact'](services['Path'](handle.name), arch)


def audit_workflows(catalog: dict, *, services: CatalogValidationServices) -> dict:
    workflows = services['core_workflows']()
    workflow_dir = services['ROOT'] / ".github" / "workflows"
    aggregate_workflows = sorted(
        {
            str(path.relative_to(services['ROOT']))
            for pattern in services['AGGREGATE_WORKFLOW_GLOBS']
            for path in workflow_dir.glob(pattern)
            if path.is_file()
        }
    )
    records = {}
    for core_id, path in workflows.items():
        try:
            workflow_bytes = path.read_bytes()
            text = workflow_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise services['PipelineError'](
                f"cannot read core workflow as UTF-8: {path}: {exc}"
            ) from exc
        shared_pipeline_commands = services['re'].findall(
            r"(?<!\S)python3\s+scripts/core_pipeline\.py\s+e2e(?=\s|$)",
            text,
        )
        runner_profiles = services['re'].findall(
            r"--runner-profile\s+([A-Za-z0-9_-]+)(?=\s|$)", text
        )
        core_selectors = services['re'].findall(
            r"--core\s+([A-Za-z0-9_+-]+)(?=\s|$)", text
        )
        records[core_id] = {
            "workflow": str(path.relative_to(services['ROOT'])),
            "file_sha256": services['sha256_bytes'](workflow_bytes),
            "masked_build_failures": text.count('|| echo "::warning::'),
            "permits_info_only_package": (
                "_libretro.info" in text and 'if [ -n "$CONTENTS" ]' in text
            ),
            "uses_shared_pipeline": (
                len(shared_pipeline_commands) == 1
                and runner_profiles == ["github-actions"]
                and core_selectors == [core_id]
            ),
            "shared_pipeline_command_count": len(shared_pipeline_commands),
            "runner_profiles": runner_profiles,
            "core_selectors": core_selectors,
            "has_blank_source_default": bool(
                services['re'].search(r"core_ref:[\s\S]{0,180}?default:\s*''", text)
            ),
        }
    workflow_ids = set(workflows)
    catalog_ids = set(catalog["cores"])
    unmigrated_workflows = sorted(
        core_id
        for core_id, record in records.items()
        if not record["uses_shared_pipeline"]
    )
    invalid_catalog_workflows = sorted(
        core_id
        for core_id in catalog_ids & workflow_ids
        if not records[core_id]["uses_shared_pipeline"]
    )
    return {
        "schema_version": 2,
        "catalog_core_count": len(catalog_ids),
        "core_workflow_count": len(workflows),
        "catalog_workflow_count": len(catalog_ids & workflow_ids),
        "missing_catalog_workflows": sorted(catalog_ids - workflow_ids),
        "uncataloged_workflows": sorted(workflow_ids - catalog_ids),
        "active_aggregate_workflows": aggregate_workflows,
        "invalid_catalog_workflows": invalid_catalog_workflows,
        "masked_build_failure_paths": sum(
            record["masked_build_failures"] for record in records.values()
        ),
        "info_only_risk_workflows": sum(
            bool(record["permits_info_only_package"]) for record in records.values()
        ),
        "shared_pipeline_workflows": sum(
            bool(record["uses_shared_pipeline"]) for record in records.values()
        ),
        "unmigrated_workflow_count": len(unmigrated_workflows),
        "unmigrated_workflows": unmigrated_workflows,
        "catalog_cores": sorted(catalog["cores"]),
        "workflows": records,
        "release_orchestration": services['audit_release_workflows'](services['ROOT']),
    }
