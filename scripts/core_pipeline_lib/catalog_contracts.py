"""Catalog build-contract normalization and proof compatibility.

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
class CatalogContractServices:
    """Call-time namespace required by this pipeline domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "CatalogContractServices":
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
        'ATARI800_CORE_ID',
        'ATARI800_METADATA_PREIMAGE_SHA256',
        'ATARI800_METADATA_REPLACEMENT_KIND',
        'ATARI800_METADATA_REPLACEMENT_PATH',
        'ATARI800_METADATA_REPLACEMENT_SHA256',
        'BLUEMSX_CORE_ID',
        'CORE_2048_ID',
        'FBNEO_CORE_ID',
        'FBNEO_GIT_VERSION',
        'FMSX_CORE_ID',
        'GEARBOY_CORE_ID',
        'GEARCOLECO_CORE_ID',
        'GEARSYSTEM_CORE_ID',
        'GENERATED_SOURCE_PATH_RE',
        'GIT_VERSION_DERIVATION',
        'LOWRESNX_CORE_ID',
        'MAME2003_PLUS_CORE_ID',
        'MAME2003_PLUS_GIT_VERSION',
        'MEDNAFEN_PCFX_CORE_ID',
        'MEDNAFEN_SUPERGRAFX_CORE_ID',
        'MEDNAFEN_WSWAN_CORE_ID',
        'MGBA_CORE_ID',
        'MGBA_NATIVE_GIT_VERSION',
        'NATIVE_GIT_DESCRIBE_DERIVATION',
        'NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES',
        'NATIVE_GIT_MAKE_BUILD_KEYS',
        'NATIVE_GIT_VERSION_DERIVATION',
        'NATIVE_GIT_VERSION_SHORT10_BUILD_KEYS',
        'NATIVE_GIT_VERSION_SHORT10_DERIVATION',
        'NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES',
        'NATIVE_GIT_VERSION_SHORT9_DERIVATION',
        'NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES',
        'NATIVE_GIT_VERSION_SPEC_IDENTITIES',
        'PICODRIVE_METADATA_PREIMAGE_SHA256',
        'PICODRIVE_METADATA_REPLACEMENT_KIND',
        'PICODRIVE_METADATA_REPLACEMENT_PATH',
        'PICODRIVE_METADATA_REPLACEMENT_SHA256',
        'POKEMINI_CORE_ID',
        'POTATOR_CORE_ID',
        'PipelineError',
        'RACE_CORE_ID',
        'ROOT',
        'SHA256_RE',
        'SNES9X2005_PLUS_MAKE_PROFILE',
        'UZEM_CORE_ID',
        'UZEM_NATIVE_GIT_VERSION_BUILD_KEYS',
        'VECX_METADATA_PREIMAGE_SHA256',
        'VECX_METADATA_REPLACEMENT_KIND',
        'VECX_METADATA_REPLACEMENT_PATH',
        'VECX_METADATA_REPLACEMENT_SHA256',
        'VECX_SOFTWARE_MAKE_PROFILE',
        'VICE_X64_CORE_ID',
        'VICE_XVIC_CORE_ID',
        '_build_contract_io',
        '_build_contract_resolvers',
        '_build_contracts',
        '_chipset_tuning_log_proves_resolved',
        '_source_candidate_contract_spec',
        'atari800_golden_build_contract_is_well_formed',
        'atari800_golden_source_is_well_formed',
        'atari800_identity_is_well_formed',
        'atari800_metadata_replacement_contract_is_well_formed',
        'atari800_spec_is_well_formed',
        'bluemsx_golden_build_contract_is_well_formed',
        'bluemsx_golden_source_is_well_formed',
        'bluemsx_spec_is_well_formed',
        'combined_git_version_make_golden_build_contract_is_well_formed',
        'compile_definitions_for_target',
        'copy',
        'core_2048_golden_build_contract_is_well_formed',
        'core_2048_golden_source_is_well_formed',
        'core_2048_spec_is_well_formed',
        'core_81_generated_source_contract_is_well_formed',
        'core_81_spec_is_well_formed',
        'core_spec_sha256',
        'direct_cargo_contract_for_target',
        'direct_cmake_contract_for_target',
        'exact_native_git_describe_contract',
        'exact_native_git_version_contract',
        'execution_tuning_profile',
        'fbneo_golden_build_contract_is_well_formed',
        'fbneo_golden_source_is_well_formed',
        'fbneo_spec_is_well_formed',
        'fmsx_golden_build_contract_is_well_formed',
        'fmsx_golden_source_is_well_formed',
        'fmsx_spec_is_well_formed',
        'gearboy_golden_build_contract_is_well_formed',
        'gearboy_golden_source_is_well_formed',
        'gearboy_spec_is_well_formed',
        'gearcoleco_golden_build_contract_is_well_formed',
        'gearcoleco_golden_source_is_well_formed',
        'gearcoleco_spec_is_well_formed',
        'gearsystem_golden_build_contract_is_well_formed',
        'gearsystem_golden_source_is_well_formed',
        'gearsystem_spec_is_well_formed',
        'generated_source_contract_is_well_formed',
        'git_version_contract_is_well_formed',
        'git_version_golden_build_contract_is_well_formed',
        'lowresnx_golden_build_contract_is_well_formed',
        'lowresnx_golden_source_is_well_formed',
        'lowresnx_spec_is_well_formed',
        'make_variable_profile',
        'mame2003_plus_golden_build_contract_is_well_formed',
        'mame2003_plus_golden_source_is_well_formed',
        'mame2003_plus_spec_is_well_formed',
        'mednafen_pcfx_combined_golden_build_contract_is_well_formed',
        'mednafen_pcfx_golden_source_is_well_formed',
        'mednafen_pcfx_spec_is_well_formed',
        'mednafen_supergrafx_spec_is_well_formed',
        'mednafen_wswan_golden_build_contract_is_well_formed',
        'mednafen_wswan_golden_source_is_well_formed',
        'mednafen_wswan_spec_is_well_formed',
        'metadata_replacement_contract_is_well_formed',
        'mgba_golden_build_contract_is_well_formed',
        'mgba_golden_source_is_well_formed',
        'mgba_spec_is_well_formed',
        'native_git_describe_golden_source_is_well_formed',
        'native_git_version_golden_source_is_well_formed',
        'picodrive_identity_is_well_formed',
        'picodrive_metadata_replacement_contract_is_well_formed',
        'pokemini_golden_build_contract_is_well_formed',
        'pokemini_golden_source_is_well_formed',
        'pokemini_spec_is_well_formed',
        'potator_spec_is_well_formed',
        'race_spec_is_well_formed',
        'safe_child',
        'snes9x2005_plus_combined_golden_build_contract_is_well_formed',
        'source_aware_candidate_contract_is_registered',
        'source_date_epoch_is_well_formed',
        'uzem_golden_build_contract_is_well_formed',
        'uzem_golden_source_is_well_formed',
        'uzem_spec_is_well_formed',
        'validated_generated_source',
        'validated_git_version',
        'validated_make_variables',
        'validated_metadata_replacement',
        'validated_recipe_profile',
        'validated_source_date_epoch',
        'vecx_combined_golden_build_contract_is_well_formed',
        'vecx_metadata_replacement_contract_is_well_formed',
        'vecx_software_identity_is_well_formed',
        'verified_file_bytes',
        'vice_x64_golden_build_contract_is_well_formed',
        'vice_x64_golden_source_is_well_formed',
        'vice_x64_spec_is_well_formed',
        'vice_xvic_golden_build_contract_is_well_formed',
        'vice_xvic_golden_source_is_well_formed',
        'vice_xvic_spec_is_well_formed',
    }
)


def native_git_version_spec_is_well_formed(
    spec: object, core_id: object,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == services['FBNEO_CORE_ID']:
        return services['fbneo_spec_is_well_formed'](spec)
    if core_id == services['MAME2003_PLUS_CORE_ID']:
        return services['mame2003_plus_spec_is_well_formed'](spec)
    if core_id == services['ATARI800_CORE_ID']:
        return services['atari800_spec_is_well_formed'](spec)
    if core_id == services['UZEM_CORE_ID']:
        return services['uzem_spec_is_well_formed'](spec)
    if core_id == services['MEDNAFEN_WSWAN_CORE_ID']:
        return services['mednafen_wswan_spec_is_well_formed'](spec)
    if core_id == services['MEDNAFEN_PCFX_CORE_ID']:
        return services['mednafen_pcfx_spec_is_well_formed'](spec)
    if core_id == services['MEDNAFEN_SUPERGRAFX_CORE_ID']:
        return services['mednafen_supergrafx_spec_is_well_formed'](spec)
    if core_id == services['POKEMINI_CORE_ID']:
        return services['pokemini_spec_is_well_formed'](spec)
    if core_id == services['FMSX_CORE_ID']:
        return services['fmsx_spec_is_well_formed'](spec)
    if core_id == services['BLUEMSX_CORE_ID']:
        return services['bluemsx_spec_is_well_formed'](spec)
    if core_id == services['CORE_2048_ID']:
        return services['core_2048_spec_is_well_formed'](spec)
    if core_id == services['LOWRESNX_CORE_ID']:
        return services['lowresnx_spec_is_well_formed'](spec)
    if core_id == services['POTATOR_CORE_ID']:
        return services['potator_spec_is_well_formed'](spec)
    if core_id == services['RACE_CORE_ID']:
        return services['race_spec_is_well_formed'](spec)
    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
    }:
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    identity = services['NATIVE_GIT_VERSION_SPEC_IDENTITIES'].get(core_id)
    if identity is None:
        return False
    expected_build_keys = (
        services['NATIVE_GIT_MAKE_BUILD_KEYS']
        if identity.get("make_variables") is not None
        else services['UZEM_NATIVE_GIT_VERSION_BUILD_KEYS']
    )
    if identity.get("overlays") is not None:
        # An identity may declare exact reviewed overlays; the build must
        # then carry exactly that mapping and nothing else changes shape.
        expected_build_keys = frozenset(expected_build_keys) | {"overlays"}
    expected_git_version = {
        "derivation": services['NATIVE_GIT_VERSION_DERIVATION'],
        "value": f" {identity['source_commit'][:7]}",
    }
    compiler_scope = identity.get("compiler_scope")
    if compiler_scope is not None:
        expected_git_version["compiler_scope"] = compiler_scope
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == expected_build_keys
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version") == expected_git_version
        and (
            identity.get("make_variables") is None
            or build.get("make_variables") == identity["make_variables"]
        )
        and (
            identity.get("overlays") is None
            or build.get("overlays") == identity["overlays"]
        )
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


def exact_native_git_version_contract(core_id: object, *, services: CatalogContractServices) -> dict | None:
    if core_id == services['FBNEO_CORE_ID']:
        return services['copy'].deepcopy(services['FBNEO_GIT_VERSION'])
    if core_id == services['MAME2003_PLUS_CORE_ID']:
        return services['copy'].deepcopy(services['MAME2003_PLUS_GIT_VERSION'])
    identity = services['NATIVE_GIT_VERSION_SPEC_IDENTITIES'].get(core_id)
    if identity is not None:
        contract = {
            "derivation": services['NATIVE_GIT_VERSION_DERIVATION'],
            "value": f" {identity['source_commit'][:7]}",
        }
        if identity.get("compiler_scope") is not None:
            contract["compiler_scope"] = identity["compiler_scope"]
        return contract
    identity = services['NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES'].get(core_id)
    if identity is not None:
        return {
            "derivation": services['NATIVE_GIT_VERSION_SHORT9_DERIVATION'],
            "value": services['MGBA_NATIVE_GIT_VERSION'],
            "compiler_scope": identity["compiler_scope"],
        }
    identity = services['NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES'].get(core_id)
    if identity is not None:
        return {
            "derivation": services['NATIVE_GIT_VERSION_SHORT10_DERIVATION'],
            "value": identity["git_version_value"],
        }
    return None


def native_git_version_short9_spec_is_well_formed(
    spec: object, core_id: object,
    *,
    services: CatalogContractServices,
) -> bool:
    return core_id == services['MGBA_CORE_ID'] and services['mgba_spec_is_well_formed'](spec)


def native_git_version_short10_spec_is_well_formed(
    spec: object, core_id: object,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == services['VICE_X64_CORE_ID']:
        return services['vice_x64_spec_is_well_formed'](spec)
    if core_id == services['VICE_XVIC_CORE_ID']:
        return services['vice_xvic_spec_is_well_formed'](spec)
    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
    }:
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    identity = services['NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES'].get(core_id)
    if identity is None:
        return False
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == services['NATIVE_GIT_VERSION_SHORT10_BUILD_KEYS']
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version")
        == {
            "derivation": services['NATIVE_GIT_VERSION_SHORT10_DERIVATION'],
            "value": identity["git_version_value"],
        }
        and build.get("source_date_epoch") == identity["source_date_epoch"]
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


def native_git_describe_spec_is_well_formed(
    spec: object, core_id: object,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == services['GEARBOY_CORE_ID']:
        return services['gearboy_spec_is_well_formed'](spec)
    if core_id == services['GEARSYSTEM_CORE_ID']:
        return services['gearsystem_spec_is_well_formed'](spec)
    if core_id == services['GEARCOLECO_CORE_ID']:
        return services['gearcoleco_spec_is_well_formed'](spec)
    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
    }:
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    identity = services['NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES'].get(core_id)
    if identity is None:
        return False
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == services['UZEM_NATIVE_GIT_VERSION_BUILD_KEYS']
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version")
        == {
            "derivation": services['NATIVE_GIT_DESCRIBE_DERIVATION'],
            "value": identity["git_version_value"],
        }
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


def exact_native_git_describe_contract(core_id: object, *, services: CatalogContractServices) -> dict | None:
    identity = services['NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES'].get(core_id)
    if identity is None:
        return None
    return {
        "derivation": services['NATIVE_GIT_DESCRIBE_DERIVATION'],
        "value": identity["git_version_value"],
    }


def uzem_native_git_version_spec_is_well_formed(spec: object, *, services: CatalogContractServices) -> bool:
    return services['uzem_spec_is_well_formed'](spec)


def validated_make_variables(spec: dict, *, services: CatalogContractServices) -> dict[str, int]:
    return services['_build_contracts'].validated_make_variables(
        spec,
        resolvers=services['_build_contract_resolvers'](),
    )


def git_version_contract_is_well_formed(
    value: object, source_commit: object,
    *,
    services: CatalogContractServices,
) -> bool:
    return services['_build_contracts'].git_version_contract_is_well_formed(
        value,
        source_commit,
        resolvers=services['_build_contract_resolvers'](),
    )


def validated_git_version(spec: dict, *, services: CatalogContractServices) -> dict | None:
    return services['_build_contracts'].validated_git_version(
        spec,
        resolvers=services['_build_contract_resolvers'](),
    )




def canonical_makeflags(spec: dict, *, services: CatalogContractServices) -> str:
    return services['_build_contracts'].canonical_makeflags(
        spec,
        resolvers=services['_build_contract_resolvers'](),
    )




def validated_recipe_profile(spec: dict, *, services: CatalogContractServices) -> dict | None:
    return services['_build_contracts'].validated_recipe_profile(
        spec,
        resolvers=services['_build_contract_resolvers'](),
    )




def metadata_matches_replacement(
    metadata: object, replacement: object | None,
    *,
    services: CatalogContractServices,
) -> bool:
    if replacement is None:
        return True
    return bool(
        isinstance(metadata, dict)
        and services['metadata_replacement_contract_is_well_formed'](replacement)
        and metadata.get("status") == "valid"
        and metadata.get("sha256") == replacement["replacement_sha256"]
    )


def validated_metadata_replacement(spec: dict, *, services: CatalogContractServices) -> dict | None:
    metadata = spec.get("metadata", {})
    if not isinstance(metadata, dict):
        raise services['PipelineError']("metadata must be an object")
    raw = metadata.get("replacement")
    is_vecx_identity = (
        services['make_variable_profile'](spec.get("build", {}).get("make_variables"))
        == services['VECX_SOFTWARE_MAKE_PROFILE']
        and services['vecx_software_identity_is_well_formed'](spec)
    )
    is_atari800_identity = services['atari800_identity_is_well_formed'](spec)
    is_picodrive_identity = services['picodrive_identity_is_well_formed'](spec)
    if raw is None:
        if is_vecx_identity:
            raise services['PipelineError'](
                "metadata.replacement is required by the VecX software contract"
            )
        if is_atari800_identity:
            raise services['PipelineError'](
                "metadata.replacement is required by the Atari800 source contract"
            )
        if is_picodrive_identity:
            raise services['PipelineError'](
                "metadata.replacement is required by the Picodrive source contract"
            )
        return None
    if is_vecx_identity:
        expected_kind = services['VECX_METADATA_REPLACEMENT_KIND']
        expected_path = services['VECX_METADATA_REPLACEMENT_PATH']
        expected_preimage = services['VECX_METADATA_PREIMAGE_SHA256']
        expected_replacement = services['VECX_METADATA_REPLACEMENT_SHA256']
        replacement_label = "VecX software"
        replacement_proof = services['vecx_metadata_replacement_contract_is_well_formed']
    elif is_atari800_identity:
        expected_kind = services['ATARI800_METADATA_REPLACEMENT_KIND']
        expected_path = services['ATARI800_METADATA_REPLACEMENT_PATH']
        expected_preimage = services['ATARI800_METADATA_PREIMAGE_SHA256']
        expected_replacement = services['ATARI800_METADATA_REPLACEMENT_SHA256']
        replacement_label = "Atari800 source"
        replacement_proof = services['atari800_metadata_replacement_contract_is_well_formed']
    elif is_picodrive_identity:
        expected_kind = services['PICODRIVE_METADATA_REPLACEMENT_KIND']
        expected_path = services['PICODRIVE_METADATA_REPLACEMENT_PATH']
        expected_preimage = services['PICODRIVE_METADATA_PREIMAGE_SHA256']
        expected_replacement = services['PICODRIVE_METADATA_REPLACEMENT_SHA256']
        replacement_label = "Picodrive source"
        replacement_proof = (
            services['picodrive_metadata_replacement_contract_is_well_formed']
        )
    else:
        raise services['PipelineError'](
            "metadata.replacement is restricted to an exact reviewed core contract"
        )
    if not isinstance(raw, dict):
        raise services['PipelineError']("metadata.replacement must be an object")
    expected_keys = {
        "kind",
        "path",
        "preimage_sha256",
        "replacement_sha256",
    }
    if set(raw) != expected_keys:
        raise services['PipelineError'](
            "metadata.replacement must contain the exact metadata replacement fields"
        )
    if raw.get("kind") != expected_kind:
        raise services['PipelineError']("metadata.replacement.kind must be whole-file-v1")
    if raw.get("path") != expected_path:
        raise services['PipelineError'](
            "metadata.replacement.path does not match the reviewed core contract"
        )
    if raw.get("preimage_sha256") != expected_preimage:
        raise services['PipelineError'](
            "metadata.replacement.preimage_sha256 does not match the reviewed source"
        )
    if (
        not isinstance(raw.get("replacement_sha256"), str)
        or not services['SHA256_RE'].fullmatch(raw["replacement_sha256"])
        or raw["replacement_sha256"] == raw["preimage_sha256"]
    ):
        raise services['PipelineError'](
            "metadata.replacement.replacement_sha256 is invalid"
        )
    if raw["replacement_sha256"] != expected_replacement:
        raise services['PipelineError'](
            "metadata.replacement.replacement_sha256 does not match the "
            f"reviewed {replacement_label} metadata"
        )
    if not replacement_proof(raw):
        raise services['PipelineError'](
            "metadata.replacement must be the exact reviewed whole-file-v1 "
            f"{replacement_label} contract"
        )
    assert isinstance(raw, dict)
    replacement_path = services['safe_child'](
        services['ROOT'], raw["path"], "metadata replacement path"
    )
    try:
        replacement_bytes = services['verified_file_bytes'](
            replacement_path,
            raw["replacement_sha256"],
            "metadata replacement file",
        )
    except services['PipelineError'] as exc:
        raise services['PipelineError'](
            "metadata.replacement.replacement_sha256 does not match its file"
        ) from exc
    if is_vecx_identity:
        try:
            replacement_text = replacement_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise services['PipelineError'](
                f"metadata replacement is not readable UTF-8 text: {exc}"
            ) from exc
        if (
            'hw_render = "false"' not in replacement_text
            or "required_hw_api" in replacement_text
            or "hardware-rendered" in replacement_text.lower()
        ):
            raise services['PipelineError'](
                "metadata replacement does not describe a software-only renderer"
            )
    return {key: raw[key] for key in sorted(raw)}


def generated_source_contract_is_well_formed(value: object, *, services: CatalogContractServices) -> bool:
    """Recognize the versioned, path-safe generated-source record shape."""

    return bool(
        isinstance(value, dict)
        and set(value) == {"kind", "path", "sha256"}
        and value.get("kind") == "post-build-sha256-v1"
        and isinstance(value.get("path"), str)
        and services['GENERATED_SOURCE_PATH_RE'].fullmatch(value["path"]) is not None
        and isinstance(value.get("sha256"), str)
        and services['SHA256_RE'].fullmatch(value["sha256"]) is not None
    )


def validated_generated_source(spec: dict, *, services: CatalogContractServices) -> dict | None:
    """Return the one reviewed post-build generated-source contract."""

    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise services['PipelineError']("build must be an object")
    raw = build.get("generated_source")
    if raw is None:
        return None
    if (
        not services['generated_source_contract_is_well_formed'](raw)
        or not services['core_81_spec_is_well_formed'](spec)
        or not services['core_81_generated_source_contract_is_well_formed'](raw)
    ):
        raise services['PipelineError'](
            "build.generated_source is restricted to the exact EightyOne "
            "post-build source digest contract"
        )
    return services['copy'].deepcopy(raw)


def validate_build_overlays(
    overlays: object,
    core_id: str | None,
    source_dir: str,
    targets: object,
    *,
    services: CatalogContractServices,
) -> dict:
    return services['_build_contracts'].validate_build_overlays(
        overlays,
        core_id,
        source_dir,
        targets,
        io=services['_build_contract_io'](),
    )


def validated_direct_cmake(
    spec: dict, core_id: str | None = None,
    *,
    services: CatalogContractServices,
) -> dict | None:
    return services['_build_contracts'].validated_direct_cmake(
        spec,
        core_id,
        io=services['_build_contract_io'](),
    )


def direct_cmake_contract_for_target(spec: dict, arch: str, *, services: CatalogContractServices) -> dict | None:
    return services['_build_contracts'].direct_cmake_contract_for_target(
        spec,
        arch,
        io=services['_build_contract_io'](),
    )




def _source_candidate_contract_spec(
    core_id: str,
    execution_spec: dict,
    contract_spec: dict | None,
    projection: SourceCandidateContractProjection | None,
    *,
    services: CatalogContractServices,
) -> dict:
    if contract_spec is None and projection is None:
        return execution_spec
    if contract_spec is None or projection is None:
        raise services['PipelineError']("source-candidate contract context is incomplete")
    execution_source = execution_spec.get("source", {})
    canonical_source = contract_spec.get("source", {})
    if (
        projection.core_id != core_id
        or services['core_spec_sha256'](contract_spec) != projection.canonical_spec_sha256
        or services['core_spec_sha256'](execution_spec) != projection.execution_spec_sha256
        or canonical_source.get("commit") != projection.canonical_commit
        or canonical_source.get("tree") != projection.canonical_tree
        or execution_source.get("commit") != projection.candidate_commit
        or execution_source.get("tree") != projection.candidate_tree
        or execution_source.get("url") != projection.source_url
        or execution_source.get("requested_ref") != projection.requested_ref
        or services['validated_source_date_epoch'](contract_spec)
        != projection.canonical_source_date_epoch
        or services['validated_git_version'](contract_spec) is not None
        or not services['source_aware_candidate_contract_is_registered'](core_id)
    ):
        raise services['PipelineError']("source-candidate contract context is invalid")
    return contract_spec


def normalized_build_contract(
    spec: dict,
    arch: str,
    *,
    core_id: str | None = None,
    source_candidate_contract_spec: dict | None = None,
    source_candidate_projection: SourceCandidateContractProjection | None = None,
    services: CatalogContractServices,
) -> dict:
    contract_spec = services['_source_candidate_contract_spec'](
        core_id or spec.get("build", {}).get("source_key", ""),
        spec,
        source_candidate_contract_spec,
        source_candidate_projection,
    )
    git_version = services['validated_git_version'](contract_spec)
    contract = {
        "driver": spec.get("build", {}).get("driver"),
        "environment": "sanitized-v1",
        "compile_definitions": services['compile_definitions_for_target'](spec, arch),
    }
    if git_version is not None:
        contract["git_version"] = git_version
    generated_source = services['validated_generated_source'](contract_spec)
    if generated_source is not None:
        contract["generated_source"] = generated_source
    recipe_profile = services['validated_recipe_profile'](contract_spec)
    if recipe_profile is not None:
        contract["recipe_profile"] = recipe_profile
    make_variables = services['validated_make_variables'](contract_spec)
    if make_variables:
        contract["make_variables"] = make_variables
    source_date_epoch = services['validated_source_date_epoch'](spec)
    if source_date_epoch is not None:
        contract["source_date_epoch"] = source_date_epoch
    metadata_replacement = services['validated_metadata_replacement'](contract_spec)
    if metadata_replacement is not None:
        contract["metadata_replacement"] = metadata_replacement
    direct_cmake = services['direct_cmake_contract_for_target'](spec, arch)
    if direct_cmake is not None:
        contract.update(direct_cmake)
    direct_cargo = services['direct_cargo_contract_for_target'](spec, arch)
    if direct_cargo is not None:
        contract.update(direct_cargo)
    return contract




def native_git_version_golden_source_is_well_formed(
    core_id: object, source: object,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == services['FBNEO_CORE_ID']:
        return services['fbneo_golden_source_is_well_formed'](core_id, source)
    if core_id == services['MAME2003_PLUS_CORE_ID']:
        return services['mame2003_plus_golden_source_is_well_formed'](core_id, source)
    if core_id == services['ATARI800_CORE_ID']:
        return services['atari800_golden_source_is_well_formed'](core_id, source)
    if core_id == services['MGBA_CORE_ID']:
        return services['mgba_golden_source_is_well_formed'](core_id, source)
    if core_id == services['UZEM_CORE_ID']:
        return services['uzem_golden_source_is_well_formed'](core_id, source)
    if core_id == services['MEDNAFEN_WSWAN_CORE_ID']:
        return services['mednafen_wswan_golden_source_is_well_formed'](core_id, source)
    if core_id == services['MEDNAFEN_PCFX_CORE_ID']:
        return services['mednafen_pcfx_golden_source_is_well_formed'](core_id, source)
    if core_id == services['POKEMINI_CORE_ID']:
        return services['pokemini_golden_source_is_well_formed'](core_id, source)
    if core_id == services['FMSX_CORE_ID']:
        return services['fmsx_golden_source_is_well_formed'](core_id, source)
    if core_id == services['BLUEMSX_CORE_ID']:
        return services['bluemsx_golden_source_is_well_formed'](core_id, source)
    if core_id == services['CORE_2048_ID']:
        return services['core_2048_golden_source_is_well_formed'](core_id, source)
    if core_id == services['LOWRESNX_CORE_ID']:
        return services['lowresnx_golden_source_is_well_formed'](core_id, source)
    if core_id == services['VICE_X64_CORE_ID']:
        return services['vice_x64_golden_source_is_well_formed'](core_id, source)
    if core_id == services['VICE_XVIC_CORE_ID']:
        return services['vice_xvic_golden_source_is_well_formed'](core_id, source)
    identity = services['NATIVE_GIT_VERSION_SPEC_IDENTITIES'].get(core_id)
    if identity is None:
        identity = services['NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES'].get(core_id)
    if identity is None:
        identity = services['NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES'].get(core_id)
    return bool(
        identity is not None
        and isinstance(source, dict)
        and set(source)
        == {
            "url",
            "requested_ref",
            "commit",
            "tree",
            "resolved_commit",
            "resolved_url",
            "submodules",
        }
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and source.get("resolved_commit") == identity["source_commit"]
        and source.get("resolved_url") == identity["source_url"]
        and source.get("submodules") == []
    )


def native_git_describe_golden_source_is_well_formed(
    core_id: object, source: object,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == services['GEARBOY_CORE_ID']:
        return services['gearboy_golden_source_is_well_formed'](core_id, source)
    if core_id == services['GEARSYSTEM_CORE_ID']:
        return services['gearsystem_golden_source_is_well_formed'](core_id, source)
    if core_id == services['GEARCOLECO_CORE_ID']:
        return services['gearcoleco_golden_source_is_well_formed'](core_id, source)
    identity = services['NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES'].get(core_id)
    return bool(
        identity is not None
        and isinstance(source, dict)
        and set(source)
        == {
            "url",
            "requested_ref",
            "commit",
            "tree",
            "resolved_commit",
            "resolved_url",
            "submodules",
        }
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and source.get("resolved_commit") == identity["source_commit"]
        and source.get("resolved_url") == identity["source_url"]
        and source.get("submodules") == []
    )


def uzem_native_golden_source_is_well_formed(
    core_id: object, source: object,
    *,
    services: CatalogContractServices,
) -> bool:
    return services['uzem_golden_source_is_well_formed'](core_id, source)


def git_version_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object = None,
    source: object = None,
    arch: object = None,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == services['FBNEO_CORE_ID']:
        return services['fbneo_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source, arch
        )
    if core_id == services['MAME2003_PLUS_CORE_ID']:
        return services['mame2003_plus_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source, arch
        )
    if core_id == services['ATARI800_CORE_ID']:
        return services['atari800_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['MGBA_CORE_ID']:
        return services['mgba_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['MEDNAFEN_WSWAN_CORE_ID']:
        return services['mednafen_wswan_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['POKEMINI_CORE_ID']:
        return services['pokemini_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['UZEM_CORE_ID']:
        return services['uzem_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['GEARBOY_CORE_ID']:
        return services['gearboy_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['GEARSYSTEM_CORE_ID']:
        return services['gearsystem_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['GEARCOLECO_CORE_ID']:
        return services['gearcoleco_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['FMSX_CORE_ID']:
        return services['fmsx_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['BLUEMSX_CORE_ID']:
        return services['bluemsx_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['CORE_2048_ID']:
        return services['core_2048_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['LOWRESNX_CORE_ID']:
        return services['lowresnx_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['VICE_X64_CORE_ID']:
        return services['vice_x64_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['VICE_XVIC_CORE_ID']:
        return services['vice_xvic_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if not isinstance(build, dict):
        return False
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "git_version",
        "log",
        "log_sha256",
    }
    common_contract_is_well_formed = bool(
        required_keys.issubset(build)
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and services['git_version_contract_is_well_formed'](
            build.get("git_version"), source_commit
        )
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and services['SHA256_RE'].fullmatch(build["log_sha256"])
    )
    if not common_contract_is_well_formed:
        return False
    derivation = build.get("git_version", {}).get("derivation")
    if derivation == services['GIT_VERSION_DERIVATION']:
        return bool(
            set(build).issubset(required_keys.union({"source_date_epoch"}))
            and (
                "source_date_epoch" not in build
                or services['source_date_epoch_is_well_formed'](build["source_date_epoch"])
            )
        )
    if derivation == services['NATIVE_GIT_VERSION_DERIVATION']:
        return bool(
            set(build) == required_keys
            and services['native_git_version_golden_source_is_well_formed'](core_id, source)
            and build.get("git_version")
            == services['exact_native_git_version_contract'](core_id)
        )
    if derivation == services['NATIVE_GIT_VERSION_SHORT9_DERIVATION']:
        return bool(
            set(build) == required_keys
            and services['native_git_version_golden_source_is_well_formed'](core_id, source)
            and build.get("git_version")
            == services['exact_native_git_version_contract'](core_id)
        )
    if derivation == services['NATIVE_GIT_VERSION_SHORT10_DERIVATION']:
        identity = services['NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES'].get(core_id)
        return bool(
            identity is not None
            and set(build) == required_keys.union({"source_date_epoch"})
            and services['native_git_version_golden_source_is_well_formed'](core_id, source)
            and build.get("git_version")
            == services['exact_native_git_version_contract'](core_id)
            and build.get("source_date_epoch")
            == identity["source_date_epoch"]
        )
    if derivation == services['NATIVE_GIT_DESCRIBE_DERIVATION']:
        return bool(
            set(build) == required_keys
            and services['native_git_describe_golden_source_is_well_formed'](core_id, source)
            and build.get("git_version")
            == services['exact_native_git_describe_contract'](core_id)
        )
    return False


def snes9x2005_plus_combined_golden_build_contract_is_well_formed(
    build: object, source_commit: object, core_id: object, source: object,
    *,
    services: CatalogContractServices,
) -> bool:
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "make_variables",
        "git_version",
        "log",
        "log_sha256",
    }
    return bool(
        isinstance(build, dict)
        and core_id == "snes9x2005_plus"
        and services['native_git_version_golden_source_is_well_formed'](core_id, source)
        and set(build) == required_keys
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and services['make_variable_profile'](build.get("make_variables"))
        == services['SNES9X2005_PLUS_MAKE_PROFILE']
        and services['git_version_contract_is_well_formed'](
            build.get("git_version"), source_commit
        )
        and build.get("git_version")
        == services['exact_native_git_version_contract'](core_id)
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and services['SHA256_RE'].fullmatch(build["log_sha256"])
    )


def combined_git_version_make_golden_build_contract_is_well_formed(
    build: object, source_commit: object, core_id: object, source: object,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id == "vecx":
        return services['vecx_combined_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == services['MEDNAFEN_PCFX_CORE_ID']:
        return services['mednafen_pcfx_combined_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    if core_id == "snes9x2005_plus":
        return services['snes9x2005_plus_combined_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    return False


def exact_native_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
    arch: object = None,
    *,
    services: CatalogContractServices,
) -> bool:
    if core_id in {services['MEDNAFEN_PCFX_CORE_ID'], "snes9x2005_plus"}:
        return services['combined_git_version_make_golden_build_contract_is_well_formed'](
            build, source_commit, core_id, source
        )
    return services['git_version_golden_build_contract_is_well_formed'](
        build, source_commit, core_id, source, arch
    )




def chipset_tuning_log_proves_contract(
    build_log_text: str,
    tuning: object,
    arch: str,
    *,
    allow_no_target_compile: bool = False,
    services: CatalogContractServices,
) -> bool:
    """Prove the resolved profile marker and every target compile invocation.

    The proof rejects response files and conflicting machine-selection flags;
    a non-empty tuning must be visible on every C or C++ ``-c`` command for
    the selected target compiler.
    """

    if not isinstance(tuning, dict) or not isinstance(tuning.get("profile_id"), str):
        return False
    try:
        expected_tuning = services['execution_tuning_profile'](tuning["profile_id"], arch)
    except services['PipelineError']:
        return False
    if expected_tuning != tuning:
        return False
    return services['_chipset_tuning_log_proves_resolved'](
        build_log_text,
        tuning,
        arch,
        allow_no_target_compile=allow_no_target_compile,
    )




def git_version_markers(
    git_version: object, source_commit: object,
    *,
    services: CatalogContractServices,
) -> list[str]:
    return services['_build_contracts'].git_version_markers(
        git_version,
        source_commit,
        resolvers=services['_build_contract_resolvers'](),
    )


def git_version_log_proves_contract(
    build_log_text: str,
    git_version: object,
    source_commit: object,
    arch: str,
    *,
    services: CatalogContractServices,
) -> bool:
    return services['_build_contracts'].git_version_log_proves_contract(
        build_log_text,
        git_version,
        source_commit,
        arch,
        resolvers=services['_build_contract_resolvers'](),
    )


def read_build_log(path: Path, label: str, *, services: CatalogContractServices) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise services['PipelineError'](f"{label} is not readable UTF-8 text: {exc}") from exc

