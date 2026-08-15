"""Tuning, source-candidate, output, and host-reproduction models.

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


@dataclass(frozen=True, slots=True)
class CandidateModelServices:
    """Call-time namespace required by this pipeline domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "CandidateModelServices":
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
        'ARCH_LAYOUT',
        'CHIPSET_ARCHITECTURES',
        'COMPILER_ARGUMENT_MAPPING_VERSION',
        'DEFAULT_CHIPSET_TUNINGS',
        'HOST_REPRODUCTION_SCOPE',
        'LEGACY_REUSABLE_REF_GENERATOR_SHA256',
        'Mapping',
        'Path',
        'PipelineError',
        'REAL_CHIPSETS',
        'RECIPE_RISK_KEYS',
        'ROOT',
        'SHA1_RE',
        'SHA256_RE',
        'SOURCE_CANDIDATE_REPRODUCTION_SCOPE',
        'SOURCE_KEYS',
        'TUNED_REPRODUCTION_SCOPE',
        'TUNING_CANDIDATE_KEYS',
        'TUNING_CANDIDATE_REGISTRY_KEYS',
        'TUNING_CANDIDATE_SCOPE',
        'TUNING_PROFILE_KEYS',
        '_stored_reference_is_well_formed',
        'candidate_golden_id_is_well_formed',
        'copy',
        'core_workflows',
        'git_head',
        'golden_content_sha256',
        'host_reproduction_build_content_sha256',
        'host_reproduction_build_identity',
        'host_reproduction_content_sha256',
        'host_reproduction_output_identity',
        'json',
        'load_json',
        'load_json_with_sha256',
        'one_core_golden_document',
        'resolve_tuning_candidate_selection',
        'resolved_tuning_profile',
        'run',
        'sha256_bytes',
        'source_aware_candidate_contract_is_registered',
        'utc_now',
        'validate_artifact',
        'validate_chipset_tunings',
        'validated_tuning_candidate_shape',
    }
)


def imported_core_baseline(
    spruceos: Path,
    core_id: str,
    pin_id: str,
    *,
    services: CandidateModelServices,
) -> dict:
    """Import only one shipped core into a schema-v2 promotion candidate."""

    workflows = services['core_workflows']()
    if core_id not in workflows:
        raise services['PipelineError'](f"individual imported core is unknown: {core_id}")
    if not services['candidate_golden_id_is_well_formed'](core_id, pin_id):
        raise services['PipelineError'](
            "individual imported golden ID must be <core>-candidate-<label>"
        )
    if not (spruceos / ".git").exists():
        raise services['PipelineError'](f"not a git checkout: {spruceos}")
    source_commit = services['git_head'](spruceos)
    artifacts = {}
    for arch, layout in services['ARCH_LAYOUT'].items():
        relative = services['Path'](layout["directory"]) / f"{core_id}_libretro.so"
        artifact_path = spruceos / relative
        if artifact_path.is_file():
            artifacts[arch] = {
                "path": relative.as_posix(),
                **services['validate_artifact'](artifact_path, arch),
            }
        else:
            artifacts[arch] = {"status": "not_shipped"}
    core_record = {
        "workflow": str(workflows[core_id].relative_to(services['ROOT'])),
        "tier": "imported_baseline",
        "promotion_eligible": False,
        "artifacts": artifacts,
    }
    document = services['one_core_golden_document'](
        core_id=core_id,
        pin_id=pin_id,
        created_at=services['utc_now'](),
        baseline={
            "kind": "spruceos-shipped-artifacts",
            "repository_commit": source_commit,
            "provenance": "artifact-only",
            "warning": (
                "Imported binaries pin starting bytes but are not reproducible "
                "build goldens until source, submodules, recipe, and toolchain "
                "are recorded."
            ),
        },
        core_record=core_record,
        build_goldens={},
    )
    document["content_sha256"] = services['golden_content_sha256'](document)
    return document


def verify_image(toolchain: dict, *, services: CandidateModelServices) -> str:
    image = toolchain["image"]
    expected = toolchain["image_id"]
    result = services['run'](["docker", "image", "inspect", "--format", "{{.Id}}", image])
    actual = result.stdout.strip()
    if actual != expected:
        raise services['PipelineError'](
            f"toolchain image mismatch for {image}: expected {expected}, got {actual}"
        )
    return actual


def sanitized_shell_prelude(*, cargo: bool = False, services: CandidateModelServices) -> str:
    """The environment-sanitizing script head every build runs under.

    The C image variant exports and verifies the cross toolchain from
    HOST_CC; the cargo variant (the Rust image carries no C cross
    toolchain) verifies the pinned cargo/zig tools instead, with the same
    hostile-environment scrub.
    """

    if cargo:
        return r"""
set -Eeuo pipefail
export LC_ALL=C
export LANG=C
umask 022
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS ASMFLAGS ASFLAGS MAKE MAKEFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MFLAGS GIT_VERSION EMULATOR_BUILD HAS_GPU IS_X86 USE_BLARGG_APU ARCH ARCH_AARCH64 ARCH_ARM ARCH_X86 ARCH_X86_64 HAVE_SSA LIBRETRO_EMBED_FFMPEG OPENGL CMAKE_TOOLCHAIN_FILE SOURCE_DATE_EPOCH CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET CMAKE_BUILD_PARALLEL_LEVEL GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_CONFIG RUSTFLAGS RUSTC RUSTC_WRAPPER CARGO_BUILD_RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
while IFS='=' read -r core_pipeline_environment_name _; do
  case "$core_pipeline_environment_name" in
    GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*|CARGO_TARGET_*_RUSTFLAGS) unset "$core_pipeline_environment_name" ;;
  esac
done < <(env)
for tool in cargo rustc zig cargo-zigbuild git; do
  command -v "$tool" >/dev/null
done
""".strip()
    return r"""
set -Eeuo pipefail
export LC_ALL=C
export LANG=C
umask 022
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS ASMFLAGS ASFLAGS MAKE MAKEFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MFLAGS GIT_VERSION EMULATOR_BUILD HAS_GPU IS_X86 USE_BLARGG_APU ARCH ARCH_AARCH64 ARCH_ARM ARCH_X86 ARCH_X86_64 HAVE_SSA LIBRETRO_EMBED_FFMPEG OPENGL CMAKE_TOOLCHAIN_FILE SOURCE_DATE_EPOCH CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET CMAKE_BUILD_PARALLEL_LEVEL GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_CONFIG
while IFS='=' read -r core_pipeline_environment_name _; do
  case "$core_pipeline_environment_name" in
    GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*) unset "$core_pipeline_environment_name" ;;
  esac
done < <(env)
export CC="${HOST_CC}-gcc"
export CXX="${HOST_CC}-g++"
export AR="${HOST_CC}-ar"
export RANLIB="${HOST_CC}-ranlib"
export STRIP="${HOST_CC}-strip"
export CROSS_COMPILE="${HOST_CC}-"
export CHOST="${HOST_CC}"
for tool in "$CC" "$CXX" "$AR" "$RANLIB" "$STRIP"; do
  command -v "$tool" >/dev/null
done
""".strip()


def execution_tuning_profile(
    profile_id: str | None,
    arch: str,
    tuning_registry: Mapping[str, object] | None = None,
    *,
    services: CandidateModelServices,
) -> dict | None:
    """Resolve only a registry-owned tuning profile for one target ABI.

    Callers never provide compiler flags.  The profile ID is resolved through
    the validated registry and the versioned mapping in ``chipsets.py``.
    """

    if profile_id is None:
        return None
    tuning = services['resolved_tuning_profile'](
        services['load_json'](services['DEFAULT_CHIPSET_TUNINGS'])
        if tuning_registry is None
        else tuning_registry,
        profile_id,
    )
    if tuning["architecture"] not in {"any", arch}:
        raise services['PipelineError'](
            f"chipset tuning profile {profile_id} is incompatible with {arch}"
        )
    return tuning


TUNING_CANDIDATE_SCOPE = "registry-owned-one-abi-tuning-v1"
TUNED_REPRODUCTION_SCOPE = "dual-independent-e2e-byte-equivalence-v1"
SOURCE_CANDIDATE_REPRODUCTION_SCOPE = (
    "dual-independent-untuned-e2e-byte-equivalence-v1"
)
HOST_REPRODUCTION_SCOPE = "dual-hardened-host-e2e-equivalence-v1"
TUNING_CANDIDATE_KEYS = frozenset(
    {"schema_version", "validation_scope", "registry", "profile"}
)
TUNING_CANDIDATE_REGISTRY_KEYS = frozenset(
    {"path", "file_sha256", "content_sha256"}
)
TUNING_PROFILE_KEYS = frozenset(
    {
        "profile_id",
        "chipset",
        "architecture",
        "properties",
        "compiler_argument_mapping_version",
        "compiler_arguments",
        "content_sha256",
    }
)


def resolve_tuning_candidate_selection(profile_id: str, *, services: CandidateModelServices) -> dict:
    """Resolve one non-universal registry profile into immutable E2E input."""

    if not isinstance(profile_id, str) or not profile_id:
        raise services['PipelineError']("tuning candidate profile ID is required")
    registry_document, registry_file_sha256 = services['load_json_with_sha256'](
        services['DEFAULT_CHIPSET_TUNINGS']
    )
    registry = services['validate_chipset_tunings'](registry_document)
    profile = services['resolved_tuning_profile'](registry, profile_id)
    if (
        profile.get("chipset") == "universal"
        or profile.get("architecture") not in services['ARCH_LAYOUT']
        or not profile.get("compiler_arguments")
    ):
        raise services['PipelineError'](
            "tuning candidates require one non-universal, non-empty registry profile"
        )
    return {
        "schema_version": 1,
        "validation_scope": services['TUNING_CANDIDATE_SCOPE'],
        "registry": {
            "path": str(services['DEFAULT_CHIPSET_TUNINGS'].relative_to(services['ROOT'])),
            "file_sha256": registry_file_sha256,
            "content_sha256": registry["content_sha256"],
        },
        "profile": profile,
    }


def validated_tuning_candidate_selection(value: object, *, services: CandidateModelServices) -> dict:
    """Require an exact projection of the current, tracked tuning registry."""

    shaped = services['validated_tuning_candidate_shape'](value)
    profile = shaped["profile"]
    expected = services['resolve_tuning_candidate_selection'](profile["profile_id"])
    if shaped != expected:
        raise services['PipelineError']("tuning candidate differs from the current registry")
    return services['copy'].deepcopy(expected)


def validated_tuning_candidate_shape(value: object, *, services: CandidateModelServices) -> dict:
    """Validate the immutable embedded shape without consulting live registry."""

    if not isinstance(value, services['Mapping']) or set(value) != services['TUNING_CANDIDATE_KEYS']:
        raise services['PipelineError']("tuning candidate fields are not exact")
    registry = value.get("registry")
    profile = value.get("profile")
    properties = profile.get("properties") if isinstance(profile, services['Mapping']) else None
    compiler_arguments = (
        profile.get("compiler_arguments") if isinstance(profile, services['Mapping']) else None
    )
    argument_mapping = (
        ("cpu_target", "-mcpu="),
        ("tune_target", "-mtune="),
        ("fpu", "-mfpu="),
        ("float_abi", "-mfloat-abi="),
    )
    expected_arguments = (
        [prefix + properties[key] for key, prefix in argument_mapping if key in properties]
        if isinstance(properties, services['Mapping'])
        and all(isinstance(key, str) and isinstance(item, str) for key, item in properties.items())
        else None
    )
    allowed_property_values = {
        "cpu_target": {"cortex-a7", "cortex-a35", "cortex-a53", "cortex-a55"},
        "tune_target": {"cortex-a7", "cortex-a35", "cortex-a53", "cortex-a55"},
        "fpu": {"neon-vfpv4"},
        "float_abi": {"hard"},
    }
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("validation_scope") != services['TUNING_CANDIDATE_SCOPE']
        or not isinstance(registry, services['Mapping'])
        or set(registry) != services['TUNING_CANDIDATE_REGISTRY_KEYS']
        or not isinstance(profile, services['Mapping'])
        or set(profile) != services['TUNING_PROFILE_KEYS']
        or not isinstance(profile.get("profile_id"), str)
        or registry.get("path") != str(services['DEFAULT_CHIPSET_TUNINGS'].relative_to(services['ROOT']))
        or not isinstance(registry.get("file_sha256"), str)
        or services['SHA256_RE'].fullmatch(registry["file_sha256"]) is None
        or not isinstance(registry.get("content_sha256"), str)
        or services['SHA256_RE'].fullmatch(registry["content_sha256"]) is None
        or profile.get("chipset") not in services['REAL_CHIPSETS']
        or profile.get("architecture") not in services['ARCH_LAYOUT']
        or services['CHIPSET_ARCHITECTURES'].get(profile.get("chipset"))
        != profile.get("architecture")
        or profile.get("compiler_argument_mapping_version")
        != services['COMPILER_ARGUMENT_MAPPING_VERSION']
        or not isinstance(properties, services['Mapping'])
        or set(properties) - {key for key, _prefix in argument_mapping}
        or any(
            item not in allowed_property_values.get(key, set())
            for key, item in properties.items()
        )
        or not isinstance(compiler_arguments, list)
        or not compiler_arguments
        or compiler_arguments != expected_arguments
    ):
        raise services['PipelineError']("tuning candidate identity is invalid")
    profile_material = {
        key: services['copy'].deepcopy(profile[key])
        for key in services['TUNING_PROFILE_KEYS'] - {"content_sha256"}
    }
    if profile.get("content_sha256") != services['sha256_bytes'](
        services['json'].dumps(profile_material, sort_keys=True, separators=(",", ":")).encode()
    ):
        raise services['PipelineError']("tuning candidate profile content identity is invalid")
    return services['copy'].deepcopy(dict(value))


def tuning_candidate_recipe_identity(selection: Mapping[str, object], *, services: CandidateModelServices) -> dict:
    profile = selection.get("profile")
    if not isinstance(profile, services['Mapping']):
        raise services['PipelineError']("tuning candidate profile is missing")
    return {
        "profile_id": profile.get("profile_id"),
        "content_sha256": profile.get("content_sha256"),
    }


def validated_tuned_reproduction_shape(
    value: object,
    *,
    core_id: str,
    arch: str,
    golden_record: Mapping[str, object],
    services: CandidateModelServices,
) -> dict:
    """Validate tamper-evident dual-run references without reading store bytes."""

    if not isinstance(value, services['Mapping']) or set(value) != {
        "schema_version",
        "validation_scope",
        "selected",
        "reproduction",
        "equivalent_outputs",
    }:
        raise services['PipelineError']("tuned reproduction fields are not exact")
    side_keys = {
        "run_id",
        "content_sha256",
        "e2e_record",
        "build_record",
        "build_log",
        "recipe_snapshot",
    }
    selected = value.get("selected")
    reproduction = value.get("reproduction")
    if (
        value.get("schema_version") != 1
        or value.get("validation_scope") != services['TUNED_REPRODUCTION_SCOPE']
        or not isinstance(selected, services['Mapping'])
        or set(selected) != side_keys
        or not isinstance(reproduction, services['Mapping'])
        or set(reproduction) != side_keys
    ):
        raise services['PipelineError']("tuned reproduction identity is invalid")
    for side in (selected, reproduction):
        if (
            not isinstance(side.get("run_id"), str)
            or not side["run_id"]
            or not isinstance(side.get("content_sha256"), str)
            or services['SHA256_RE'].fullmatch(side["content_sha256"]) is None
        ):
            raise services['PipelineError']("tuned reproduction run identity is invalid")
        for name in ("e2e_record", "build_record", "build_log", "recipe_snapshot"):
            reference = side.get(name)
            if (
                not isinstance(reference, services['Mapping'])
                or set(reference) != {"path", "sha256"}
                or not isinstance(reference.get("path"), str)
                or not reference["path"].startswith(".local-e2e/store/")
                or not isinstance(reference.get("sha256"), str)
                or services['SHA256_RE'].fullmatch(reference["sha256"]) is None
            ):
                raise services['PipelineError']("tuned reproduction store reference is invalid")
    if (
        selected["run_id"] == reproduction["run_id"]
        or selected["e2e_record"] == reproduction["e2e_record"]
        or selected["build_record"] == reproduction["build_record"]
    ):
        raise services['PipelineError']("tuned reproduction runs are not independent")
    local_store = golden_record.get("local_store")
    e2e = golden_record.get("e2e")
    if not isinstance(local_store, services['Mapping']) or not isinstance(e2e, services['Mapping']):
        raise services['PipelineError']("tuned reproduction golden store identity is invalid")
    if (
        selected["run_id"] != e2e.get("run_id")
        or selected["content_sha256"] != e2e.get("content_sha256")
        or selected["e2e_record"] != local_store.get("e2e_record")
        or selected["build_record"]
        != local_store.get("build_records", {}).get(arch)
        or selected["build_log"] != local_store.get("build_logs", {}).get(arch)
        or selected["recipe_snapshot"]
        != local_store.get("recipe_snapshots", {}).get(arch)
    ):
        raise services['PipelineError']("tuned reproduction selected side differs from golden")
    outputs = value.get("equivalent_outputs")
    artifact = golden_record.get("artifact")
    metadata = golden_record.get("metadata")
    if (
        not isinstance(outputs, services['Mapping'])
        or set(outputs) != {"artifact", "metadata", "package"}
        or outputs.get("artifact")
        != {
            "sha256": artifact.get("sha256") if isinstance(artifact, services['Mapping']) else None,
            "size": artifact.get("size") if isinstance(artifact, services['Mapping']) else None,
        }
        or outputs.get("metadata")
        != {
            "sha256": metadata.get("sha256") if isinstance(metadata, services['Mapping']) else None,
            "size": metadata.get("size") if isinstance(metadata, services['Mapping']) else None,
        }
        or not isinstance(outputs.get("package"), services['Mapping'])
        or set(outputs["package"]) != {"name", "sha256", "size"}
        or outputs["package"].get("name") != f"{core_id}_libretro.zip"
        or outputs["package"].get("sha256") != e2e.get("package_sha256")
        or type(outputs["package"].get("size")) is not int
        or outputs["package"]["size"] <= 0
    ):
        raise services['PipelineError']("tuned reproduction equivalent outputs are invalid")
    return services['copy'].deepcopy(dict(value))


def _stored_reference_is_well_formed(value: object, *, services: CandidateModelServices) -> bool:
    return bool(
        isinstance(value, services['Mapping'])
        and set(value) == {"path", "sha256"}
        and isinstance(value.get("path"), str)
        and value["path"].startswith(".local-e2e/store/")
        and isinstance(value.get("sha256"), str)
        and services['SHA256_RE'].fullmatch(value["sha256"]) is not None
    )


def validated_embedded_source_candidate_shape(
    value: object,
    *,
    core_id: str,
    services: CandidateModelServices,
) -> dict:
    """Validate the immutable candidate projection embedded in a golden/pin.

    Live candidate catalogs receive the stronger filesystem, mirror, snapshot,
    generator, and recipe validation in ``validate_source_candidate_catalog``.
    This shape remains self-authenticating after promotion: its candidate ID
    covers every nested provenance byte, so immutable goldens and pins cannot
    silently rewrite any part of the accepted source selection.
    """

    required = {
        "schema_version",
        "validation_scope",
        "local_only",
        "publication",
        "core_id",
        "generator",
        "snapshot",
        "base_catalog",
        "mirror",
        "selection",
        "execution",
        "candidate_id",
    }
    if not isinstance(value, services['Mapping']) or frozenset(value) not in {
        frozenset(required),
        frozenset(required | {"catalog_rebase"}),
    }:
        raise services['PipelineError']("embedded source candidate fields are not exact")
    candidate_id = value.get("candidate_id")
    material = services['copy'].deepcopy(dict(value))
    material.pop("candidate_id", None)
    expected_candidate_id = services['sha256_bytes'](
        services['json'].dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )
    if (
        value.get("schema_version") != 1
        or value.get("validation_scope")
        != "immutable-edge-source-candidate-catalog-v1"
        or value.get("local_only") is not True
        or value.get("publication") != "disabled"
        or value.get("core_id") != core_id
        or not isinstance(candidate_id, str)
        or services['SHA256_RE'].fullmatch(candidate_id) is None
        or candidate_id != expected_candidate_id
    ):
        raise services['PipelineError']("embedded source candidate identity is invalid")
    nested_fields = {
        "generator": {"path", "sha256"},
        "snapshot": {
            "path",
            "file_sha256",
            "content_sha256",
            "snapshot_id",
            "captured_at",
            "catalog",
        },
        "base_catalog": {"path", "file_sha256", "core_spec_sha256"},
        "mirror": {"path", "origin_url", "frozen_local_ref"},
        "execution": {"core_spec_sha256", "source_date_epoch_derivation"},
    }
    for name, fields in nested_fields.items():
        nested = value.get(name)
        if not isinstance(nested, services['Mapping']) or set(nested) != fields:
            raise services['PipelineError'](f"embedded source candidate {name} is invalid")
    if value["generator"].get("path") != (
        "scripts/core_pipeline_lib/source_candidate.py"
    ):
        raise services['PipelineError']("embedded source candidate generator is invalid")
    selection = value.get("selection")
    if not isinstance(selection, services['Mapping']) or set(selection) != services['SOURCE_KEYS']:
        raise services['PipelineError']("embedded source candidate selection is invalid")
    requested_ref = selection.get("requested_ref")
    commit = selection.get("commit")
    catalog_commit = selection.get("catalog_commit")
    risk = selection.get("recipe_risk")
    expected_frozen_refs: set[str] = set()
    if isinstance(requested_ref, str) and isinstance(commit, str):
        expected_frozen_refs.add(
            "refs/spruce-edge-refs/"
            + services['sha256_bytes'](requested_ref.encode() + b"\0" + commit.encode())
        )
        if (
            value["generator"].get("sha256")
            in services['LEGACY_REUSABLE_REF_GENERATOR_SHA256']
        ):
            expected_frozen_refs.add(
                "refs/spruce-edge-refs/" + services['sha256_bytes'](requested_ref.encode())
            )
    if (
        not isinstance(selection.get("url"), str)
        or not selection["url"]
        or not isinstance(requested_ref, str)
        or not requested_ref.startswith("refs/heads/")
        or not isinstance(catalog_commit, str)
        or services['SHA1_RE'].fullmatch(catalog_commit) is None
        or not isinstance(selection.get("catalog_tree"), str)
        or services['SHA1_RE'].fullmatch(selection["catalog_tree"]) is None
        or not isinstance(commit, str)
        or services['SHA1_RE'].fullmatch(commit) is None
        or not isinstance(selection.get("tree"), str)
        or services['SHA1_RE'].fullmatch(selection["tree"]) is None
        or type(selection.get("commit_epoch")) is not int
        or selection["commit_epoch"] <= 0
        or selection.get("frozen_local_ref") not in expected_frozen_refs
        or selection.get("ref_kind") != "branch"
        or selection.get("ref_object") != commit
        or selection.get("ref_object_type") != "commit"
        or selection.get("latest_semantics") != "exact-branch-tip"
        or selection.get("catalog_is_ancestor") is not True
        or selection.get("status") not in {"unchanged", "fast-forward"}
        or (commit == catalog_commit)
        is not (selection.get("status") == "unchanged")
        or not isinstance(selection.get("top_level_gitlinks"), list)
        or not isinstance(risk, services['Mapping'])
        or set(risk) != services['RECIPE_RISK_KEYS']
        or not isinstance(risk.get("driver"), str)
        or type(risk.get("catalog_declared_submodules")) is not int
        or risk["catalog_declared_submodules"] < 0
        or type(risk.get("overlays")) is not int
        or risk["overlays"] < 0
        or any(
            type(risk.get(name)) is not bool
            for name in (
                "git_version",
                "recursive_submodules",
                "source_aware_log_contract",
                "source_date_epoch",
                "submodule_fetch",
            )
        )
        or risk.get("source_aware_log_contract")
        is not services['source_aware_candidate_contract_is_registered'](core_id)
        or value["mirror"].get("origin_url") != selection.get("url")
        or value["mirror"].get("frozen_local_ref")
        != selection.get("frozen_local_ref")
    ):
        raise services['PipelineError']("embedded source candidate selection identity is invalid")
    for digest in (
        value["generator"].get("sha256"),
        value["snapshot"].get("file_sha256"),
        value["snapshot"].get("content_sha256"),
        value["base_catalog"].get("file_sha256"),
        value["base_catalog"].get("core_spec_sha256"),
        value["execution"].get("core_spec_sha256"),
    ):
        if not isinstance(digest, str) or services['SHA256_RE'].fullmatch(digest) is None:
            raise services['PipelineError']("embedded source candidate digest is invalid")
    if "catalog_rebase" in value:
        rebase = value["catalog_rebase"]
        if (
            not isinstance(rebase, services['Mapping'])
            or set(rebase) != {"path", "file_sha256", "content_sha256"}
            or any(
                not isinstance(rebase.get(name), str)
                or services['SHA256_RE'].fullmatch(rebase[name]) is None
                for name in ("file_sha256", "content_sha256")
            )
        ):
            raise services['PipelineError']("embedded source candidate catalog rebase is invalid")
    return services['copy'].deepcopy(dict(value))


def validated_output_reproduction_shape(
    value: object,
    *,
    core_id: str,
    golden_records: Mapping[str, object],
    services: CandidateModelServices,
) -> dict:
    """Validate generic untuned dual-E2E evidence without reading store bytes."""

    if not isinstance(value, services['Mapping']) or set(value) != {
        "schema_version",
        "validation_scope",
        "selected",
        "reproduction",
        "equivalent_outputs",
    }:
        raise services['PipelineError']("output reproduction fields are not exact")
    if (
        value.get("schema_version") != 1
        or value.get("validation_scope")
        != services['SOURCE_CANDIDATE_REPRODUCTION_SCOPE']
        or not isinstance(golden_records, services['Mapping'])
        or not golden_records
        or any(arch not in services['ARCH_LAYOUT'] for arch in golden_records)
    ):
        raise services['PipelineError']("output reproduction identity is invalid")
    expected_targets = set(golden_records)
    side_keys = {
        "run_id",
        "content_sha256",
        "e2e_record",
        "build_records",
        "build_logs",
        "recipe_snapshots",
    }
    selected = value.get("selected")
    reproduction = value.get("reproduction")
    for side in (selected, reproduction):
        if (
            not isinstance(side, services['Mapping'])
            or set(side) != side_keys
            or not isinstance(side.get("run_id"), str)
            or not side["run_id"]
            or not isinstance(side.get("content_sha256"), str)
            or services['SHA256_RE'].fullmatch(side["content_sha256"]) is None
            or not services['_stored_reference_is_well_formed'](side.get("e2e_record"))
        ):
            raise services['PipelineError']("output reproduction run identity is invalid")
        for group_name in ("build_records", "build_logs", "recipe_snapshots"):
            group = side.get(group_name)
            if (
                not isinstance(group, services['Mapping'])
                or set(group) != expected_targets
                or any(
                    not services['_stored_reference_is_well_formed'](reference)
                    for reference in group.values()
                )
            ):
                raise services['PipelineError'](
                    f"output reproduction {group_name} identity is invalid"
                )
    assert isinstance(selected, services['Mapping']) and isinstance(reproduction, services['Mapping'])
    if (
        selected["run_id"] == reproduction["run_id"]
        or selected["e2e_record"] == reproduction["e2e_record"]
        or selected["build_records"] == reproduction["build_records"]
    ):
        raise services['PipelineError']("output reproduction runs are not independent")

    first_record = golden_records[sorted(expected_targets)[0]]
    if not isinstance(first_record, services['Mapping']):
        raise services['PipelineError']("output reproduction golden record is invalid")
    local_store = first_record.get("local_store")
    e2e = first_record.get("e2e")
    if not isinstance(local_store, services['Mapping']) or not isinstance(e2e, services['Mapping']):
        raise services['PipelineError']("output reproduction golden store identity is invalid")
    if (
        selected["run_id"] != e2e.get("run_id")
        or selected["content_sha256"] != e2e.get("content_sha256")
        or selected["e2e_record"] != local_store.get("e2e_record")
        or selected["build_records"] != local_store.get("build_records")
        or selected["build_logs"] != local_store.get("build_logs")
        or selected["recipe_snapshots"] != local_store.get("recipe_snapshots")
    ):
        raise services['PipelineError']("output reproduction selected side differs from golden")

    outputs = value.get("equivalent_outputs")
    package_output = (
        outputs.get("package") if isinstance(outputs, services['Mapping']) else None
    )
    expected_outputs = {
        "artifacts": {
            arch: {
                "sha256": record.get("artifact", {}).get("sha256")
                if isinstance(record, services['Mapping'])
                else None,
                "size": record.get("artifact", {}).get("size")
                if isinstance(record, services['Mapping'])
                else None,
            }
            for arch, record in sorted(golden_records.items())
        },
        "metadata": {
            "sha256": first_record.get("metadata", {}).get("sha256"),
            "size": first_record.get("metadata", {}).get("size"),
        },
        "package": {
            "name": f"{core_id}_libretro.zip",
            "sha256": e2e.get("package_sha256"),
            "size": package_output.get("size")
            if isinstance(package_output, services['Mapping'])
            else None,
        },
    }
    if (
        outputs != expected_outputs
        or type(expected_outputs["package"]["size"]) is not int
        or expected_outputs["package"]["size"] <= 0
    ):
        raise services['PipelineError']("output reproduction equivalent outputs are invalid")
    return services['copy'].deepcopy(dict(value))


def host_reproduction_build_identity(record: Mapping[str, object], *, services: CandidateModelServices) -> dict:
    """Project deterministic build identity while excluding run-local log bytes."""

    build = record.get("build")
    if not isinstance(build, dict):
        raise services['PipelineError']("host reproduction build contract is missing")
    identity = {
        "core_id": record.get("core_id"),
        "architecture": record.get("architecture"),
        "source": record.get("source"),
        "recipe": record.get("recipe"),
        "toolchain": record.get("toolchain"),
        "build": {
            key: services['copy'].deepcopy(item)
            for key, item in build.items()
            if key != "log_sha256"
        },
        "artifact": record.get("artifact"),
        "metadata": record.get("metadata"),
    }
    recipe = identity["recipe"]
    if not isinstance(recipe, services['Mapping']) or not isinstance(
        recipe.get("host_execution"), services['Mapping']
    ):
        raise services['PipelineError'](
            "host reproduction record lacks deterministic host execution"
        )
    if "tuning_candidate" in record:
        identity["tuning_candidate"] = services['copy'].deepcopy(record["tuning_candidate"])
    # Source-candidate records deliberately keep the ordinary exact build-record
    # key set.  Their authenticated candidate identity is carried by the shared
    # source/recipe tuple plus the separate source_candidate/output_reproduction
    # proof in the promoted selection, so it is not projected from golden-only
    # metadata here.
    return identity


def host_reproduction_build_content_sha256(
    record: Mapping[str, object],
    *,
    services: CandidateModelServices,
) -> str:
    return services['sha256_bytes'](
        services['json'].dumps(
            services['host_reproduction_build_identity'](record),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )


def host_reproduction_output_identity(
    records: Mapping[str, object], package: Mapping[str, object],
    *,
    services: CandidateModelServices,
) -> dict:
    if not records or any(
        arch not in services['ARCH_LAYOUT'] or not isinstance(record, services['Mapping'])
        for arch, record in records.items()
    ):
        raise services['PipelineError']("host reproduction output records are invalid")
    first = records[sorted(records)[0]]
    assert isinstance(first, services['Mapping'])
    output = {
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
    if (
        output["package"]["name"]
        != f"{first.get('core_id')}_libretro.zip"
        or type(output["package"]["size"]) is not int
        or output["package"]["size"] <= 0
    ):
        raise services['PipelineError']("host reproduction package identity is invalid")
    return output


def validated_host_reproduction_shape(
    value: object,
    *,
    core_id: str,
    golden_records: Mapping[str, object],
    services: CandidateModelServices,
) -> dict:
    """Validate a dual hardened-host proof without consulting mutable runs."""

    proof_keys = {
        "schema_version",
        "validation_scope",
        "selected",
        "reproduction",
        "equivalent_builds",
        "equivalent_outputs",
        "content_sha256",
    }
    side_keys = {"run_id", "content_sha256", "e2e_record"}
    if (
        not isinstance(value, services['Mapping'])
        or set(value) != proof_keys
        or value.get("schema_version") != 1
        or value.get("validation_scope") != services['HOST_REPRODUCTION_SCOPE']
        or not isinstance(golden_records, services['Mapping'])
        or not golden_records
        or any(arch not in services['ARCH_LAYOUT'] for arch in golden_records)
    ):
        raise services['PipelineError']("host reproduction identity is invalid")
    selected = value.get("selected")
    reproduction = value.get("reproduction")
    for side in (selected, reproduction):
        if (
            not isinstance(side, services['Mapping'])
            or set(side) != side_keys
            or not isinstance(side.get("run_id"), str)
            or not side["run_id"]
            or not isinstance(side.get("content_sha256"), str)
            or services['SHA256_RE'].fullmatch(side["content_sha256"]) is None
            or not services['_stored_reference_is_well_formed'](side.get("e2e_record"))
        ):
            raise services['PipelineError']("host reproduction run identity is invalid")
    assert isinstance(selected, services['Mapping']) and isinstance(reproduction, services['Mapping'])
    if (
        selected["run_id"] == reproduction["run_id"]
        or selected["e2e_record"] == reproduction["e2e_record"]
    ):
        raise services['PipelineError']("host reproduction runs are not independent")

    expected_targets = set(golden_records)
    equivalent_builds = value.get("equivalent_builds")
    expected_builds = {
        arch: services['host_reproduction_build_content_sha256'](record)
        for arch, record in sorted(golden_records.items())
        if isinstance(record, services['Mapping'])
    }
    if (
        not isinstance(equivalent_builds, services['Mapping'])
        or set(equivalent_builds) != expected_targets
        or equivalent_builds != expected_builds
    ):
        raise services['PipelineError']("host reproduction build identity is invalid")

    first = golden_records[sorted(expected_targets)[0]]
    if not isinstance(first, services['Mapping']):
        raise services['PipelineError']("host reproduction golden record is invalid")
    local_store = first.get("local_store")
    e2e = first.get("e2e")
    if not isinstance(local_store, services['Mapping']) or not isinstance(e2e, services['Mapping']):
        raise services['PipelineError']("host reproduction golden store identity is invalid")
    if (
        selected["run_id"] != e2e.get("run_id")
        or selected["content_sha256"] != e2e.get("content_sha256")
        or selected["e2e_record"] != local_store.get("e2e_record")
    ):
        raise services['PipelineError']("host reproduction selected side differs from golden")
    package = value.get("equivalent_outputs", {}).get("package")
    if not isinstance(package, services['Mapping']):
        raise services['PipelineError']("host reproduction output identity is invalid")
    expected_outputs = services['host_reproduction_output_identity'](
        golden_records,
        {
            "path": f"{core_id}_libretro.zip",
            "sha256": e2e.get("package_sha256"),
            "size": package.get("size"),
        },
    )
    if value.get("equivalent_outputs") != expected_outputs:
        raise services['PipelineError']("host reproduction output identity is invalid")
    if (
        not isinstance(value.get("content_sha256"), str)
        or services['SHA256_RE'].fullmatch(value["content_sha256"]) is None
        or value["content_sha256"]
        != services['host_reproduction_content_sha256'](value)
    ):
        raise services['PipelineError']("host reproduction content identity is invalid")
    return services['copy'].deepcopy(dict(value))

