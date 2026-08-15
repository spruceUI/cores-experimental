"""Golden-document and immutable-store evidence verification.

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
class StoredEvidenceServices:
    """Call-time namespace required by this evidence domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "StoredEvidenceServices":
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
        'CORE_81_ID',
        'CORE_ID_RE',
        'CommitBlacklistError',
        'DEFAULT_STORE',
        'EXACT_GIT_VERSION_CORE_IDS',
        'EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS',
        'EXACT_NATIVE_GIT_VERSION_CORE_IDS',
        'EXACT_SOURCE_NATIVE_CORE_IDS',
        'FBNEO_CORE_ID',
        'FREEINTV_CORE_ID',
        'MAME2003_PLUS_CORE_ID',
        'MGBA_CORE_ID',
        'Mapping',
        'NATIVE_GIT_VERSION_DERIVATION',
        'PICODRIVE_CORE_ID',
        'Path',
        'PipelineError',
        'ROOT',
        'SHA1_RE',
        'SHA256_RE',
        'SOURCE_CANDIDATE_BUILD_RECORD_KEYS',
        'SOURCE_CANDIDATE_E2E_KEYS',
        'STORE_SINGLE_EVIDENCE_NAMES',
        'STORE_TARGET_EVIDENCE_NAMES',
        'TUNED_REPRODUCTION_SCOPE',
        'VEMULATOR_CORE_ID',
        '_PinValidationContext',
        '__file__',
        '_build_equivalence_identity',
        '_canonical_source_candidate_spec',
        '_chipset_tuning_log_proves_resolved',
        '_golden_source_candidate_contract_projection',
        '_make_variable_profile_facts',
        '_registered_core_log_contract_proves',
        '_source_candidate_contract_build_for_guard',
        '_source_candidate_contract_source_for_guard',
        '_source_candidate_contract_spec',
        '_validate_artifact_bytes',
        '_validate_golden_document_impl',
        '_verify_historical_recipe_snapshot',
        '_verify_host_reproduction_bundle',
        '_verify_local_store',
        '_verify_output_reproduction_bundle',
        '_verify_recipe_snapshot',
        '_verify_stored_e2e_bundle',
        '_verify_tuned_reproduction_bundle',
        'build_source_date_epoch_matches',
        'combined_git_version_make_golden_build_contract_is_well_formed',
        'commit_blacklist_reference_is_well_formed',
        'compile_definition_list_is_well_formed',
        'compile_definitions_for_target',
        'compile_log_proves_definitions',
        'copy',
        'core_81_golden_build_contract_is_well_formed',
        'core_golden_v2_shape_errors',
        'core_log_contract_for',
        'core_spec_sha256',
        'core_workflows',
        'decode_json_object',
        'direct_cargo_golden_build_contract_is_well_formed',
        'direct_cmake_golden_build_contract_is_well_formed',
        'e2e_content_sha256',
        'exact_native_golden_build_contract_is_well_formed',
        'fbneo_golden_source_is_well_formed',
        'fbneo_spec_is_well_formed',
        'forbidden_needed_dependencies',
        'freeintv_golden_build_contract_is_well_formed',
        'freeintv_golden_source_is_well_formed',
        'freeintv_spec_is_well_formed',
        'generated_source_contract_is_well_formed',
        'git_version_golden_build_contract_is_well_formed',
        'git_version_log_proves_contract',
        'golden_content_sha256',
        'host_reproduction_build_content_sha256',
        'host_reproduction_build_identity',
        'host_reproduction_output_identity',
        'io',
        'json',
        'load_json',
        'make_variable_golden_build_contract_is_well_formed',
        'make_variable_log_proves_contract',
        'make_variable_profile',
        'mame2003_plus_golden_source_is_well_formed',
        'mame2003_plus_spec_is_well_formed',
        'metadata_matches_replacement',
        'metadata_replacement_contract_is_well_formed',
        'metadata_replacement_log_proves_contract',
        'mgba_spec_is_well_formed',
        'normalized_build_contract',
        'parse_commit_blacklist',
        'picodrive_golden_build_contract_is_well_formed',
        'picodrive_golden_source_is_well_formed',
        'picodrive_spec_is_well_formed',
        'pipeline_source_bundle_is_well_formed',
        'provenance_identity_sha256',
        'recorded_build_contract',
        'require_canonical_store_entry',
        'require_contained',
        'require_host_execution_runner_coupling',
        'require_selected_reproduction_runner_pair',
        'resolved_tuning_profile',
        'runner_evidence_is_hardened',
        'runner_evidence_is_well_formed',
        'safe_child',
        'selection_content_sha256',
        'sha256_bytes',
        'sha256_file',
        'source_candidate_record_contract_projection',
        'source_date_epoch_is_well_formed',
        'toolchain_lock_content_sha256',
        'tuned_candidate_build_identity',
        'tuned_candidate_output_identity',
        'tuning_candidate_recipe_identity',
        'validate_artifact',
        'validate_bound_host_telemetry',
        'validate_chipset_tunings',
        'validate_host_execution_contract',
        'validated_embedded_source_candidate_shape',
        'validated_generated_source',
        'validated_git_version',
        'validated_host_reproduction_shape',
        'validated_make_variables',
        'validated_output_reproduction_shape',
        'validated_recipe_profile',
        'validated_source_date_epoch',
        'validated_tuned_reproduction_shape',
        'validated_tuning_candidate_shape',
        'vecx_combined_golden_build_contract_is_well_formed',
        'vemulator_golden_build_contract_is_well_formed',
        'vemulator_golden_source_is_well_formed',
        'vemulator_spec_is_well_formed',
        'verified_file_bytes',
        'verified_json_object',
        'verified_utf8_text',
        'zipfile',
    }
)


def _validate_golden_document_impl(
    document: dict, spruceos: Path | None = None,
    *,
    services: StoredEvidenceServices,
) -> dict:
    if not isinstance(document, dict):
        return {
            "status": "invalid",
            "errors": ["golden document must be an object"],
            "core_count": 0,
            "valid_imported_artifacts": 0,
            "invalid_imported_artifacts": [],
            "build_golden_count": 0,
        }

    errors: list[str] = []
    workflows = services['core_workflows']()
    baseline = document.get("baseline")
    cores = document.get("cores")
    summary = document.get("summary")
    structural_errors = []
    if not isinstance(baseline, dict):
        structural_errors.append("baseline must be an object")
    if not isinstance(cores, dict):
        structural_errors.append("cores must be an object")
    elif any(
        not isinstance(core_id, str)
        or not isinstance(record, dict)
        or not isinstance(record.get("artifacts"), dict)
        or any(
            not isinstance(artifact, dict)
            for artifact in record.get("artifacts", {}).values()
        )
        for core_id, record in cores.items()
    ):
        structural_errors.append("core records and artifacts must be objects")
    if not isinstance(summary, dict):
        structural_errors.append("summary must be an object")
    if structural_errors:
        return {
            "status": "invalid",
            "errors": structural_errors,
            "core_count": len(cores) if isinstance(cores, dict) else 0,
            "valid_imported_artifacts": 0,
            "invalid_imported_artifacts": [],
            "build_golden_count": 0,
        }

    schema_version = document.get("schema_version")
    scoped_workflows = workflows
    if type(schema_version) is not int or schema_version not in {1, 2}:
        errors.append("schema_version must be the exact integer 1 or 2")
    elif schema_version == 1:
        if set(cores) != set(workflows):
            errors.append("golden core roster does not exactly match core workflows")
    else:
        errors.extend(services['core_golden_v2_shape_errors'](document))
        core_id = document.get("core_id")
        if (
            not isinstance(core_id, str)
            or services['CORE_ID_RE'].fullmatch(core_id) is None
            or core_id not in workflows
        ):
            errors.append("schema-v2 core golden core_id is invalid")
            scoped_workflows = {}
        else:
            scoped_workflows = {core_id: workflows[core_id]}
    if document.get("publication") != "disabled":
        errors.append("publication must be disabled")
    baseline_commit = baseline.get("repository_commit")
    if not isinstance(baseline_commit, str) or not services['SHA1_RE'].fullmatch(baseline_commit):
        errors.append("baseline.repository_commit is not a full SHA")
    if document.get("content_sha256") != services['golden_content_sha256'](document):
        errors.append("content_sha256 does not cover the current baseline and build goldens")
    valid_artifacts = 0
    invalid_artifacts: list[str] = []
    for core_id, path in scoped_workflows.items():
        record = cores.get(core_id, {})
        if record.get("workflow") != str(path.relative_to(services['ROOT'])):
            errors.append(f"{core_id}: workflow path mismatch")
        artifacts = record.get("artifacts", {})
        core_valid = False
        for arch in services['ARCH_LAYOUT']:
            artifact = artifacts.get(arch, {})
            status = artifact.get("status")
            if status == "valid":
                core_valid = True
                valid_artifacts += 1
                if not services['SHA256_RE'].fullmatch(artifact.get("sha256", "")):
                    errors.append(f"{core_id}/{arch}: invalid SHA256")
                if spruceos is not None:
                    try:
                        source_path = services['safe_child'](
                            spruceos, artifact.get("path", ""), f"{core_id}/{arch} source path"
                        )
                        current = services['validate_artifact'](source_path, arch)
                        if current.get("status") != "valid":
                            errors.append(f"{core_id}/{arch}: source artifact is no longer valid")
                        elif current.get("sha256") != artifact.get("sha256"):
                            errors.append(f"{core_id}/{arch}: source artifact digest drift")
                    except services['PipelineError'] as exc:
                        errors.append(str(exc))
            elif status != "not_shipped":
                if status == "invalid":
                    invalid_artifacts.append(f"{core_id}/{arch}")
                    if not artifact.get("errors"):
                        errors.append(f"{core_id}/{arch}: invalid artifact lacks evidence")
                    if not services['SHA256_RE'].fullmatch(artifact.get("sha256", "")):
                        errors.append(f"{core_id}/{arch}: invalid artifact SHA256 is invalid")
                    if spruceos is not None:
                        try:
                            source_path = services['safe_child'](
                                spruceos,
                                artifact.get("path", ""),
                                f"{core_id}/{arch} rejected source path",
                            )
                            current = services['validate_artifact'](source_path, arch)
                            if current.get("status") != "invalid":
                                errors.append(
                                    f"{core_id}/{arch}: rejected source artifact status drift"
                                )
                            elif current.get("sha256") != artifact.get("sha256"):
                                errors.append(
                                    f"{core_id}/{arch}: rejected source artifact digest drift"
                                )
                        except services['PipelineError'] as exc:
                            errors.append(str(exc))
                else:
                    errors.append(f"{core_id}/{arch}: unexpected status {status!r}")
        if not core_valid:
            errors.append(f"{core_id}: no valid imported artifact")
    build_goldens = document.get("build_goldens", {})
    if not isinstance(build_goldens, dict):
        errors.append("build_goldens must be an object")
        build_goldens = {}
    for core_id, targets in build_goldens.items():
        if core_id not in workflows:
            errors.append(f"build golden references unknown core {core_id}")
            continue
        if not isinstance(targets, dict):
            errors.append(f"{core_id}: build-golden targets must be an object")
            continue
        for arch, golden in targets.items():
            if not isinstance(golden, dict):
                errors.append(f"{core_id}/{arch}: build golden must be an object")
                continue
            if arch not in services['ARCH_LAYOUT']:
                errors.append(f"{core_id}: build golden has unknown target {arch}")
            if golden.get("promotion_state") != "build_golden":
                errors.append(f"{core_id}/{arch}: invalid promotion state")
            if golden.get("core_id") != core_id or golden.get("architecture") != arch:
                errors.append(f"{core_id}/{arch}: promoted identity mismatch")
            if golden.get("validation_scope") != "static-build-only":
                errors.append(f"{core_id}/{arch}: invalid validation scope")
            source_candidate_projection: (
                SourceCandidateContractProjection | None
            ) = None
            tuning_candidate = golden.get("tuning_candidate")
            recipe_tuning = golden.get("recipe", {}).get("chipset_tuning")
            source_candidate = golden.get("source_candidate")
            output_reproduction = golden.get("output_reproduction")
            host_reproduction = golden.get("host_reproduction")
            if tuning_candidate is not None:
                try:
                    if source_candidate is not None or output_reproduction is not None:
                        raise services['PipelineError'](
                            "tuned and source-candidate evidence are mutually exclusive"
                        )
                    validated_candidate = services['validated_tuning_candidate_shape'](
                        tuning_candidate
                    )
                    if (
                        validated_candidate["profile"]["architecture"] != arch
                        or recipe_tuning
                        != services['tuning_candidate_recipe_identity'](validated_candidate)
                    ):
                        errors.append(
                            f"{core_id}/{arch}: tuned golden identity is incoherent"
                        )
                    services['validated_tuned_reproduction_shape'](
                        golden.get("reproduction"),
                        core_id=core_id,
                        arch=arch,
                        golden_record=golden,
                    )
                except services['PipelineError'] as exc:
                    errors.append(f"{core_id}/{arch}: {exc}")
            elif source_candidate is not None or output_reproduction is not None:
                try:
                    if recipe_tuning is not None or "reproduction" in golden:
                        raise services['PipelineError'](
                            "source-candidate evidence must be untuned"
                        )
                    candidate = services['validated_embedded_source_candidate_shape'](
                        source_candidate,
                        core_id=core_id,
                    )
                    services['validated_output_reproduction_shape'](
                        output_reproduction,
                        core_id=core_id,
                        golden_records=targets,
                    )
                    source_candidate_projection = (
                        services['_golden_source_candidate_contract_projection'](
                            golden,
                            core_id=core_id,
                            arch=arch,
                        )
                    )
                    source = golden.get("source")
                    selection = candidate["selection"]
                    if not isinstance(source, services['Mapping']) or any(
                        source.get(record_key) != selection.get(selection_key)
                        for record_key, selection_key in (
                            ("url", "url"),
                            ("requested_ref", "requested_ref"),
                            ("commit", "commit"),
                            ("resolved_commit", "commit"),
                            ("tree", "tree"),
                        )
                    ):
                        raise services['PipelineError'](
                            "source-candidate selection differs from promoted source"
                        )
                except services['PipelineError'] as exc:
                    errors.append(f"{core_id}/{arch}: {exc}")
            elif recipe_tuning is not None or "reproduction" in golden:
                errors.append(
                    f"{core_id}/{arch}: tuning evidence is incomplete"
                )
            if host_reproduction is not None:
                try:
                    if any(
                        not isinstance(target_record, services['Mapping'])
                        or target_record.get("host_reproduction")
                        != host_reproduction
                        for target_record in targets.values()
                    ):
                        raise services['PipelineError'](
                            "host reproduction differs across package targets"
                        )
                    services['validated_host_reproduction_shape'](
                        host_reproduction,
                        core_id=core_id,
                        golden_records=targets,
                    )
                except services['PipelineError'] as exc:
                    errors.append(f"{core_id}/{arch}: {exc}")
            artifact = golden.get("artifact")
            if not isinstance(artifact, dict):
                errors.append(f"{core_id}/{arch}: promoted artifact must be an object")
                artifact = {}
            if artifact.get("status") != "valid":
                errors.append(f"{core_id}/{arch}: promoted artifact is not valid")
            if not isinstance(artifact.get("sha256"), str) or not services['SHA256_RE'].fullmatch(
                artifact["sha256"]
            ):
                errors.append(f"{core_id}/{arch}: promoted artifact SHA256 is invalid")
            source = golden.get("source")
            if not isinstance(source, dict):
                errors.append(f"{core_id}/{arch}: promoted source must be an object")
                source = {}
            if not isinstance(source.get("resolved_commit"), str) or not services['SHA1_RE'].fullmatch(
                source["resolved_commit"]
            ):
                errors.append(f"{core_id}/{arch}: promoted source commit is invalid")
            contract_source = services['_source_candidate_contract_source_for_guard'](
                source,
                source_candidate_projection,
            )
            if (
                core_id == services['VEMULATOR_CORE_ID']
                and not services['vemulator_golden_source_is_well_formed'](
                    core_id, contract_source
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == services['FREEINTV_CORE_ID']
                and not services['freeintv_golden_source_is_well_formed'](
                    core_id, contract_source
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == services['PICODRIVE_CORE_ID']
                and not services['picodrive_golden_source_is_well_formed'](
                    core_id, contract_source
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == services['MAME2003_PLUS_CORE_ID']
                and not services['mame2003_plus_golden_source_is_well_formed'](
                    core_id, contract_source
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == services['FBNEO_CORE_ID']
                and not services['fbneo_golden_source_is_well_formed'](
                    core_id, contract_source
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            golden_toolchain = golden.get("toolchain", {})
            if not isinstance(golden_toolchain, dict):
                errors.append(f"{core_id}/{arch}: promoted toolchain is not an object")
                archive_provenance = None
            else:
                archive_provenance = golden_toolchain.get("archive_provenance")
            if archive_provenance is not None:
                # The provenance names the LOCK ENTRY the build ran inside:
                # the target architecture for the C drivers, "rust" for a
                # direct-cargo golden.
                golden_build = golden.get("build")
                expected_lock_entry = (
                    "rust"
                    if isinstance(golden_build, dict)
                    and golden_build.get("driver") == "direct-cargo"
                    else arch
                )
                if not isinstance(archive_provenance, dict):
                    errors.append(f"{core_id}/{arch}: archive provenance is invalid")
                    lock_reference = {}
                    validator_reference = {}
                    archive = {}
                else:
                    lock_reference = archive_provenance.get("lock", {})
                    validator_reference = archive_provenance.get("validator", {})
                    archive = archive_provenance.get("archive", {})
                if not all(
                    isinstance(value, dict)
                    for value in (lock_reference, validator_reference, archive)
                ) or (
                    golden.get("provenance_version") != 2
                    or set(archive_provenance)
                    != {"lock", "validator", "architecture", "archive"}
                    or archive_provenance.get("architecture") != expected_lock_entry
                    or set(lock_reference)
                    != {
                        "path",
                        "schema_version",
                        "lock_id",
                        "file_sha256",
                        "content_sha256",
                    }
                    or lock_reference.get("path")
                    != "pins/toolchains/local-cache-v1.json"
                    or type(lock_reference.get("schema_version")) is not int
                    or lock_reference.get("schema_version") != 1
                    or lock_reference.get("lock_id") != "local-cache-v1"
                    or not isinstance(lock_reference.get("file_sha256"), str)
                    or not services['SHA256_RE'].fullmatch(lock_reference["file_sha256"])
                    or not isinstance(lock_reference.get("content_sha256"), str)
                    or not services['SHA256_RE'].fullmatch(lock_reference["content_sha256"])
                    or set(validator_reference) != {"path", "sha256"}
                    or validator_reference.get("path")
                    != "scripts/toolchain_archive.py"
                    or not isinstance(validator_reference.get("sha256"), str)
                    or not services['SHA256_RE'].fullmatch(validator_reference["sha256"])
                    or set(archive) != {"filename", "sha256", "size"}
                    or archive.get("filename") != f"cores-{expected_lock_entry}.tar.gz"
                    or not isinstance(archive.get("sha256"), str)
                    or not services['SHA256_RE'].fullmatch(archive["sha256"])
                    or type(archive.get("size")) is not int
                    or archive.get("size", 0) <= 0
                ):
                    errors.append(f"{core_id}/{arch}: archive provenance is invalid")
            elif golden.get("provenance_version") is not None:
                errors.append(f"{core_id}/{arch}: legacy provenance marker is invalid")
            metadata = golden.get("metadata")
            if not isinstance(metadata, dict):
                errors.append(f"{core_id}/{arch}: promoted metadata must be an object")
                metadata = {}
            if (
                metadata.get("status") != "valid"
                or not isinstance(metadata.get("sha256"), str)
                or not services['SHA256_RE'].fullmatch(metadata["sha256"])
            ):
                errors.append(f"{core_id}/{arch}: promoted metadata is invalid")
            promoted_build = golden.get("build")
            contract_promoted_build = services['_source_candidate_contract_build_for_guard'](
                promoted_build,
                source_candidate_projection,
            )
            contract_source_commit = (
                contract_source.get("resolved_commit")
                if isinstance(contract_source, services['Mapping'])
                else None
            )
            build_is_required = core_id in (
                services['EXACT_GIT_VERSION_CORE_IDS']
                | services['EXACT_SOURCE_NATIVE_CORE_IDS']
                | {"vecx", services['CORE_81_ID'], services['PICODRIVE_CORE_ID']}
            )
            if (
                isinstance(promoted_build, dict)
                and "metadata_replacement" in promoted_build
                and not services['metadata_matches_replacement'](
                    metadata, promoted_build["metadata_replacement"]
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted metadata does not match its replacement"
                )
            if build_is_required and not isinstance(promoted_build, dict):
                errors.append(f"{core_id}/{arch}: promoted build contract is missing")
            elif "build" in golden:
                is_git_version_build = isinstance(promoted_build, dict) and (
                    "git_version" in promoted_build
                )
                is_make_variable_build = isinstance(promoted_build, dict) and (
                    "make_variables" in promoted_build
                )
                is_generated_source_build = isinstance(
                    promoted_build, dict
                ) and ("generated_source" in promoted_build)
                is_recipe_profile_build = isinstance(
                    promoted_build, dict
                ) and ("recipe_profile" in promoted_build)
                is_direct_cmake_build = isinstance(promoted_build, dict) and (
                    promoted_build.get("driver") == "direct-cmake"
                    or "cmake" in promoted_build
                    or "overlays" in promoted_build
                )
                is_direct_cargo_build = isinstance(promoted_build, dict) and (
                    promoted_build.get("driver") == "direct-cargo"
                    or "cargo" in promoted_build
                )
                if core_id == services['CORE_81_ID']:
                    if not services['core_81_golden_build_contract_is_well_formed'](
                        contract_promoted_build,
                        contract_source_commit,
                        core_id,
                        contract_source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id == services['PICODRIVE_CORE_ID']:
                    if not services['picodrive_golden_build_contract_is_well_formed'](
                        contract_promoted_build,
                        contract_source_commit,
                        core_id,
                        contract_source,
                        arch,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif is_recipe_profile_build:
                    errors.append(
                        f"{core_id}/{arch}: recipe-profile build contract "
                        "belongs only to picodrive"
                    )
                elif is_generated_source_build:
                    errors.append(
                        f"{core_id}/{arch}: generated-source build contract "
                        "belongs only to 81"
                    )
                elif core_id == "vecx":
                    if not services['vecx_combined_golden_build_contract_is_well_formed'](
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id == services['VEMULATOR_CORE_ID']:
                    if not services['vemulator_golden_build_contract_is_well_formed'](
                        contract_promoted_build,
                        contract_source_commit,
                        core_id,
                        contract_source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id == services['FREEINTV_CORE_ID']:
                    if not services['freeintv_golden_build_contract_is_well_formed'](
                        contract_promoted_build,
                        contract_source_commit,
                        core_id,
                        contract_source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id in services['EXACT_NATIVE_GIT_VERSION_CORE_IDS']:
                    if not services['exact_native_golden_build_contract_is_well_formed'](
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                        arch,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id in services['EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS']:
                    if not services['git_version_golden_build_contract_is_well_formed'](
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                        arch,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif is_git_version_build and not services['git_version_golden_build_contract_is_well_formed'](
                    promoted_build,
                    source.get("resolved_commit"),
                    core_id,
                    source,
                    arch,
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_make_variable_build and not services['make_variable_golden_build_contract_is_well_formed'](
                    promoted_build
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_direct_cmake_build and not services['direct_cmake_golden_build_contract_is_well_formed'](
                    promoted_build, core_id, arch
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_direct_cmake_build and artifact.get("path") != (
                    f"{promoted_build.get('cmake', {}).get('target')}.so"
                ) and artifact.get("path") != f"{core_id}_libretro.so":
                    errors.append(f"{core_id}/{arch}: promoted build artifact path is invalid")
                elif is_direct_cargo_build and not services['direct_cargo_golden_build_contract_is_well_formed'](
                    promoted_build, core_id, arch
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_direct_cargo_build and artifact.get("path") != f"{core_id}_libretro.so":
                    errors.append(f"{core_id}/{arch}: promoted build artifact path is invalid")
                elif (
                    not is_git_version_build
                    and not is_make_variable_build
                    and not is_direct_cmake_build
                    and not is_direct_cargo_build
                    and (
                        not isinstance(promoted_build, dict)
                        or promoted_build.get("environment") != "sanitized-v1"
                        or not services['compile_definition_list_is_well_formed'](
                            promoted_build.get("compile_definitions")
                        )
                        or (
                            "source_date_epoch" in promoted_build
                            and not services['source_date_epoch_is_well_formed'](
                                promoted_build["source_date_epoch"]
                            )
                        )
                    )
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
            e2e = golden.get("e2e")
            if not isinstance(e2e, dict):
                errors.append(f"{core_id}/{arch}: E2E record must be an object")
                e2e = {}
            for digest_name in ("record_sha256", "content_sha256", "package_sha256"):
                if not isinstance(e2e.get(digest_name), str) or not services['SHA256_RE'].fullmatch(
                    e2e[digest_name]
                ):
                    errors.append(f"{core_id}/{arch}: E2E {digest_name} is invalid")
            for path_name in ("record", "package"):
                try:
                    evidence_path = services['safe_child'](
                        services['ROOT'],
                        e2e.get(path_name, ""),
                        f"{core_id}/{arch} E2E {path_name} path",
                    )
                    evidence_path.relative_to((services['ROOT'] / ".local-e2e").resolve())
                except (services['PipelineError'], ValueError):
                    errors.append(
                        f"{core_id}/{arch}: E2E {path_name} path is outside local output"
                    )
            local_store = golden.get("local_store")
            if not isinstance(local_store, dict):
                errors.append(f"{core_id}/{arch}: local store record must be an object")
                local_store = {}
            if local_store.get("availability") != "local-only":
                errors.append(f"{core_id}/{arch}: build golden lacks local store metadata")
            for stored_name in services['STORE_SINGLE_EVIDENCE_NAMES']:
                stored = local_store.get(stored_name)
                if not isinstance(stored, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} record must be an object"
                    )
                    stored = {}
                if not isinstance(stored.get("sha256"), str) or not services['SHA256_RE'].fullmatch(
                    stored["sha256"]
                ):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} SHA256 is invalid"
                    )
                try:
                    stored_path = services['safe_child'](
                        services['ROOT'],
                        stored.get("path", ""),
                        f"{core_id}/{arch} local {stored_name} path",
                    )
                    stored_path.relative_to(services['DEFAULT_STORE'].resolve())
                except (services['PipelineError'], ValueError):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} path is outside the local store"
                    )
            build_record_digests = e2e.get("build_records")
            if not isinstance(build_record_digests, dict):
                errors.append(f"{core_id}/{arch}: E2E build records must be an object")
                build_record_digests = {}
            if (
                not build_record_digests
                or arch not in build_record_digests
                or any(target not in services['ARCH_LAYOUT'] for target in build_record_digests)
            ):
                errors.append(f"{core_id}/{arch}: E2E build-record target set is invalid")
            for group_name in services['STORE_TARGET_EVIDENCE_NAMES']:
                group = local_store.get(group_name)
                if not isinstance(group, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {group_name} must be an object"
                    )
                    group = {}
                if set(group) != set(build_record_digests):
                    errors.append(
                        f"{core_id}/{arch}: local {group_name} target set is incomplete"
                    )
                for target, stored in group.items():
                    if not isinstance(stored, dict):
                        errors.append(
                            f"{core_id}/{arch}: local {group_name}/{target} must be an object"
                        )
                        continue
                    if (
                        target not in services['ARCH_LAYOUT']
                        or not isinstance(stored.get("sha256"), str)
                        or not services['SHA256_RE'].fullmatch(stored["sha256"])
                    ):
                        errors.append(
                            f"{core_id}/{arch}: local {group_name}/{target} identity is invalid"
                        )
                    try:
                        stored_path = services['safe_child'](
                            services['ROOT'],
                            stored.get("path", ""),
                            f"{core_id}/{arch} local {group_name}/{target} path",
                        )
                        stored_path.relative_to(services['DEFAULT_STORE'].resolve())
                    except (services['PipelineError'], ValueError):
                        errors.append(
                            f"{core_id}/{arch}: local {group_name}/{target} path is outside the local store"
                        )
            for target, expected_digest in build_record_digests.items():
                if (
                    local_store.get("build_records", {}).get(target, {}).get("sha256")
                    != expected_digest
                ):
                    errors.append(
                        f"{core_id}/{arch}: stored {target} build record is not bound to E2E"
                    )
            linked_digests = {
                "artifact": artifact.get("sha256"),
                "metadata": metadata.get("sha256"),
                "e2e_record": e2e.get("record_sha256"),
                "package": e2e.get("package_sha256"),
            }
            for stored_name, expected_digest in linked_digests.items():
                if local_store.get(stored_name, {}).get("sha256") != expected_digest:
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} digest is not bound to its record"
                    )
    cores_without_valid = sorted(
        core_id
        for core_id, record in cores.items()
        if not any(
            artifact.get("status") == "valid"
            for artifact in record.get("artifacts", {}).values()
        )
    )
    expected_summary = {
        "core_count": len(cores),
        "valid_artifact_count": valid_artifacts,
        "invalid_artifacts": sorted(invalid_artifacts),
        "cores_without_valid_artifacts": cores_without_valid,
    }
    for key, expected in expected_summary.items():
        actual = summary.get(key)
        matches = (
            sorted(actual) == expected
            if isinstance(expected, list) and isinstance(actual, list)
            else actual == expected
        )
        if not matches:
            errors.append(f"summary.{key} does not match manifest contents")
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "core_count": len(cores),
        "valid_imported_artifacts": valid_artifacts,
        "invalid_imported_artifacts": invalid_artifacts,
        "build_golden_count": sum(len(targets) for targets in build_goldens.values()),
    }


def validate_golden_document(document: dict, spruceos: Path | None = None, *, services: StoredEvidenceServices) -> dict:
    """Validate untrusted golden JSON without exposing shape exceptions."""

    try:
        return services['_validate_golden_document_impl'](document, spruceos)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {
            "status": "invalid",
            "errors": [
                "golden document contains malformed nested data "
                f"({type(exc).__name__})"
            ],
            "core_count": 0,
            "valid_imported_artifacts": 0,
            "invalid_imported_artifacts": [],
            "build_golden_count": 0,
        }


def _verify_recipe_snapshot(
    path: Path,
    record: dict,
    label: str,
    *,
    snapshot: dict | None = None,
    services: StoredEvidenceServices,
) -> list[str]:
    errors: list[str] = []
    if snapshot is None:
        try:
            snapshot = services['load_json'](path)
        except services['PipelineError'] as exc:
            return [str(exc)]
    recipe = record.get("recipe", {})
    pipeline_bundle = recipe.get("pipeline_bundle") if isinstance(recipe, dict) else None
    has_pipeline_bundle = services['pipeline_source_bundle_is_well_formed'](pipeline_bundle)
    commit_blacklist = (
        recipe.get("commit_blacklist") if isinstance(recipe, dict) else None
    )
    has_commit_blacklist = services['commit_blacklist_reference_is_well_formed'](
        commit_blacklist
    )
    host_execution = recipe.get("host_execution") if isinstance(recipe, dict) else None
    has_host_execution = host_execution is not None
    if has_host_execution:
        try:
            host_execution = services['validate_host_execution_contract'](
                host_execution, repository_root=services['ROOT']
            )
        except services['PipelineError'] as exc:
            errors.append(f"{label}: {exc}")
            host_execution = None
    tuning_candidate = record.get("tuning_candidate")
    if tuning_candidate is not None:
        try:
            tuning_candidate = services['validated_tuning_candidate_shape'](tuning_candidate)
        except services['PipelineError'] as exc:
            errors.append(f"{label}: {exc}")
            tuning_candidate = None
    if isinstance(recipe, dict) and "pipeline_bundle" in recipe:
        if not has_pipeline_bundle:
            errors.append(f"{label}: recipe pipeline bundle is invalid")
        elif (
            pipeline_bundle["files"].get(str(services['Path'](services['__file__']).relative_to(services['ROOT'])))
            != recipe.get("pipeline_sha256")
        ):
            errors.append(f"{label}: recipe launcher digest is inconsistent")
    if isinstance(recipe, dict) and "commit_blacklist" in recipe:
        if not has_commit_blacklist:
            errors.append(f"{label}: recipe commit blacklist reference is invalid")
    if (
        snapshot.get("core_id") != record.get("core_id")
        or snapshot.get("architecture") != record.get("architecture")
        or snapshot.get("source") != record.get("source")
        or snapshot.get("recipe") != record.get("recipe")
        or snapshot.get("tuning_candidate") != tuning_candidate
        or snapshot.get("host_execution") != host_execution
    ):
        errors.append(f"{label}: recipe snapshot identity mismatch")
    source_candidate_projection: SourceCandidateContractProjection | None = None
    try:
        source_candidate_projection = services['source_candidate_record_contract_projection'](
            record.get("source_candidate"),
            core_id=record.get("core_id"),
            recorded_source=record.get("source"),
            recorded_recipe=record.get("recipe"),
            recipe_snapshot=snapshot,
        )
    except services['PipelineError'] as exc:
        errors.append(f"{label}: {exc}")
    contract_record_source = services['_source_candidate_contract_source_for_guard'](
        record.get("source"),
        source_candidate_projection,
    )
    contract_record_build = services['_source_candidate_contract_build_for_guard'](
        record.get("build"),
        source_candidate_projection,
    )
    contract_record_source_commit = (
        contract_record_source.get("resolved_commit")
        if isinstance(contract_record_source, services['Mapping'])
        else None
    )
    snapshot_toolchain = snapshot.get("toolchain", {})
    record_toolchain = record.get("toolchain", {})
    if not isinstance(record_toolchain, dict):
        return [f"{label}: build record toolchain is not an object"]
    archive_provenance = record_toolchain.get("archive_provenance")
    if archive_provenance is not None and not isinstance(archive_provenance, dict):
        return [f"{label}: build record archive provenance is not an object"]
    if archive_provenance is not None and (
        not isinstance(archive_provenance.get("lock"), dict)
        or not isinstance(archive_provenance.get("validator"), dict)
        or not isinstance(archive_provenance.get("archive"), dict)
    ):
        return [f"{label}: build record archive provenance shape is invalid"]
    record_build = record.get("build", {})
    has_compile_definition_contract = (
        isinstance(record_build, dict) and "compile_definitions" in record_build
    )
    has_make_variable_contract = (
        isinstance(record_build, dict) and "make_variables" in record_build
    )
    has_git_version_contract = (
        isinstance(record_build, dict) and "git_version" in record_build
    )
    has_generated_source_contract = (
        isinstance(record_build, dict) and "generated_source" in record_build
    )
    has_recipe_profile_contract = (
        isinstance(record_build, dict) and "recipe_profile" in record_build
    )
    has_source_date_epoch_contract = (
        isinstance(record_build, dict) and "source_date_epoch" in record_build
    )
    has_direct_cmake_contract = (
        isinstance(record_build, dict)
        and (
            record_build.get("driver") == "direct-cmake"
            or "cmake" in record_build
            or "overlays" in record_build
        )
    )
    snapshot_version = snapshot.get("schema_version")
    requires_v9_provenance = (
        snapshot_version in {9, 10, 11, 12} or has_pipeline_bundle
    )
    if requires_v9_provenance and not has_pipeline_bundle:
        errors.append(f"{label}: schema-v9 recipe requires a valid pipeline bundle")
    if requires_v9_provenance and not has_commit_blacklist:
        errors.append(
            f"{label}: schema-v9 recipe requires a valid commit blacklist binding"
        )
    is_combined_git_make_contract = bool(
        record.get("core_id") in services['COMBINED_NATIVE_MAKE_CORE_IDS']
        and has_git_version_contract
        and has_make_variable_contract
    )
    if (
        record.get("core_id") == services['VEMULATOR_CORE_ID']
        and not services['vemulator_golden_build_contract_is_well_formed'](
            contract_record_build,
            contract_record_source_commit,
            record.get("core_id"),
            contract_record_source,
        )
    ):
        errors.append(
            f"{label}: source-native recipe snapshot lacks its normalized contract"
        )
    if (
        record.get("core_id") == services['FREEINTV_CORE_ID']
        and not services['freeintv_golden_build_contract_is_well_formed'](
            contract_record_build,
            contract_record_source_commit,
            record.get("core_id"),
            contract_record_source,
        )
    ):
        errors.append(
            f"{label}: source-native recipe snapshot lacks its normalized contract"
        )
    if has_recipe_profile_contract and (
        record.get("core_id") != services['PICODRIVE_CORE_ID']
        or has_git_version_contract
        or has_make_variable_contract
        or has_generated_source_contract
        or has_direct_cmake_contract
        or not services['picodrive_golden_source_is_well_formed'](
            record.get("core_id"), contract_record_source
        )
        or not services['picodrive_golden_build_contract_is_well_formed'](
            contract_record_build,
            contract_record_source_commit,
            record.get("core_id"),
            contract_record_source,
            record.get("architecture"),
        )
    ):
        errors.append(
            f"{label}: recipe-profile snapshot lacks its normalized contract"
        )
    if has_generated_source_contract:
        expected_snapshot_versions = {10}
        if (
            record.get("core_id") != services['CORE_81_ID']
            or not has_compile_definition_contract
            or has_git_version_contract
            or has_make_variable_contract
            or has_source_date_epoch_contract
            or not services['core_81_golden_build_contract_is_well_formed'](
                contract_record_build,
                contract_record_source_commit,
                record.get("core_id"),
                contract_record_source,
            )
        ):
            errors.append(
                f"{label}: generated-source recipe snapshot lacks its "
                "normalized contract"
            )
    elif has_git_version_contract and has_make_variable_contract:
        expected_snapshot_versions = {8}
        if (
            not is_combined_git_make_contract
            or not has_compile_definition_contract
            or has_source_date_epoch_contract
            or not services['combined_git_version_make_golden_build_contract_is_well_formed'](
                record_build,
                record.get("source", {}).get("resolved_commit"),
                record.get("core_id"),
                record.get("source"),
            )
        ):
            errors.append(
                f"{label}: combined native recipe snapshot lacks its normalized contract"
            )
    elif has_git_version_contract:
        expected_snapshot_versions = {7}
        if (
            not has_compile_definition_contract
            or not services['git_version_golden_build_contract_is_well_formed'](
                record_build,
                record.get("source", {}).get("resolved_commit"),
                record.get("core_id"),
                record.get("source"),
                record.get("architecture"),
            )
        ):
            errors.append(
                f"{label}: git-version recipe snapshot lacks its normalized contract"
            )
    elif has_make_variable_contract:
        expected_snapshot_versions = {6}
        make_profile = services['make_variable_profile'](record_build.get("make_variables"))
        snapshot_facts = services['_make_variable_profile_facts']().get(make_profile or "")
        # golden_epoch again: profiles whose record forbids a source_date_epoch
        # carry the same snapshot minus that one contract; profiles validated
        # by the combined native+make validators never reach this branch.
        if snapshot_facts is None or snapshot_facts.golden_epoch is None:
            normalized = False
        elif snapshot_facts.golden_epoch:
            normalized = (
                has_compile_definition_contract
                and has_source_date_epoch_contract
            )
        else:
            normalized = (
                has_compile_definition_contract
                and not has_source_date_epoch_contract
            )
        if not normalized:
            errors.append(
                f"{label}: make-variable recipe snapshot lacks its normalized contract"
            )
    elif has_direct_cmake_contract:
        expected_snapshot_versions = {5}
        if not has_compile_definition_contract or not has_source_date_epoch_contract:
            errors.append(
                f"{label}: direct-CMake recipe snapshot lacks its normalized contract"
            )
    elif has_source_date_epoch_contract:
        expected_snapshot_versions = {4}
        if not has_compile_definition_contract:
            errors.append(
                f"{label}: timestamped recipe snapshot lacks compile definitions"
            )
    elif has_compile_definition_contract:
        expected_snapshot_versions = {2, 3} if archive_provenance is not None else {3}
    else:
        expected_snapshot_versions = {2 if archive_provenance is not None else 1}
    if has_pipeline_bundle and not has_generated_source_contract:
        expected_snapshot_versions = {9}
    if tuning_candidate is not None:
        expected_snapshot_versions = {11}
    if has_host_execution:
        expected_snapshot_versions = {12}
    if (
        type(snapshot_version) is not int
        or snapshot_version not in expected_snapshot_versions
    ):
        errors.append(f"{label}: recipe snapshot schema version mismatch")
    expected_toolchain = {
        "image_id": record_toolchain.get("resolved_image_id"),
        "dockerfile": record_toolchain.get("dockerfile"),
        "dockerfile_sha256": record_toolchain.get("dockerfile_sha256"),
        "resolver_digests": record_toolchain.get("resolver_digests"),
    }
    if archive_provenance is not None:
        expected_toolchain["archive_provenance"] = archive_provenance
    if snapshot_toolchain != expected_toolchain:
        errors.append(f"{label}: recipe snapshot toolchain mismatch")
    if (
        has_direct_cmake_contract
        or has_compile_definition_contract
        or has_make_variable_contract
        or has_git_version_contract
        or has_generated_source_contract
        or has_recipe_profile_contract
        or has_source_date_epoch_contract
        or tuning_candidate is not None
        or has_host_execution
    ) and snapshot_version in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:
        expected_build = services['recorded_build_contract'](record_build)
        if snapshot.get("build") != expected_build:
            errors.append(f"{label}: recipe snapshot build contract mismatch")
    elif "build" in snapshot:
        errors.append(f"{label}: legacy recipe snapshot has a build contract")
    expected_files = {
        recipe.get("catalog_path"),
        recipe.get("workflow"),
        str(services['Path'](services['__file__']).relative_to(services['ROOT'])),
        record_toolchain.get("dockerfile"),
    }
    if has_pipeline_bundle:
        expected_files.update(pipeline_bundle["files"])
    if has_commit_blacklist:
        expected_files.add(commit_blacklist["path"])
    if tuning_candidate is not None:
        expected_files.add(tuning_candidate["registry"]["path"])
    if host_execution is not None:
        expected_files.update(
            {
                host_execution["instrumentation"]["tool_wrapper"]["path"],
                host_execution["instrumentation"]["unit_runner_source"]["path"],
                host_execution["telemetry_schema"]["path"],
            }
        )
    if archive_provenance is not None:
        expected_files.add(archive_provenance.get("lock", {}).get("path"))
        expected_files.add(archive_provenance.get("validator", {}).get("path"))
    if has_direct_cmake_contract and isinstance(record_build.get("overlays"), list):
        expected_files.update(
            overlay.get("patch_path")
            for overlay in record_build["overlays"]
            if isinstance(overlay, dict)
        )
    metadata_replacement = record_build.get("metadata_replacement")
    if metadata_replacement is not None:
        if services['metadata_replacement_contract_is_well_formed'](metadata_replacement):
            expected_files.add(metadata_replacement["path"])
            if not services['metadata_matches_replacement'](
                record.get("metadata"), metadata_replacement
            ):
                errors.append(
                    f"{label}: metadata does not match the recipe replacement"
                )
        else:
            errors.append(f"{label}: metadata replacement contract is invalid")
    files = snapshot.get("files", {})
    if set(files) != expected_files:
        errors.append(f"{label}: recipe snapshot file set mismatch")
        return errors
    for relative, stored in files.items():
        text = stored.get("text")
        if not isinstance(text, str) or services['sha256_bytes'](text.encode()) != stored.get("sha256"):
            errors.append(f"{label}: recipe snapshot digest mismatch for {relative}")
    expected_hashes = {
        recipe.get("catalog_path"): recipe.get("catalog_sha256"),
        recipe.get("workflow"): recipe.get("workflow_sha256"),
        str(services['Path'](services['__file__']).relative_to(services['ROOT'])): recipe.get("pipeline_sha256"),
        record_toolchain.get("dockerfile"): record_toolchain.get("dockerfile_sha256"),
    }
    if has_pipeline_bundle:
        expected_hashes.update(pipeline_bundle["files"])
    if has_commit_blacklist:
        expected_hashes[commit_blacklist["path"]] = commit_blacklist[
            "file_sha256"
        ]
    if tuning_candidate is not None:
        expected_hashes[tuning_candidate["registry"]["path"]] = tuning_candidate[
            "registry"
        ]["file_sha256"]
    if host_execution is not None:
        for reference in (
            host_execution["instrumentation"]["tool_wrapper"],
            host_execution["instrumentation"]["unit_runner_source"],
            host_execution["telemetry_schema"],
        ):
            expected_hashes[reference["path"]] = reference["file_sha256"]
    if archive_provenance is not None:
        expected_hashes[archive_provenance.get("lock", {}).get("path")] = (
            archive_provenance.get("lock", {}).get("file_sha256")
        )
        expected_hashes[archive_provenance.get("validator", {}).get("path")] = (
            archive_provenance.get("validator", {}).get("sha256")
        )
    if has_direct_cmake_contract and isinstance(record_build.get("overlays"), list):
        for overlay in record_build["overlays"]:
            if isinstance(overlay, dict):
                expected_hashes[overlay.get("patch_path")] = overlay.get(
                    "patch_sha256"
                )
    if services['metadata_replacement_contract_is_well_formed'](metadata_replacement):
        expected_hashes[metadata_replacement["path"]] = metadata_replacement[
            "replacement_sha256"
        ]
    for relative, expected in expected_hashes.items():
        if files.get(relative, {}).get("sha256") != expected:
            errors.append(f"{label}: recipe record digest mismatch for {relative}")
    if tuning_candidate is not None:
        try:
            tuning_registry_text = files[tuning_candidate["registry"]["path"]]["text"]
            tuning_registry = services['validate_chipset_tunings'](
                services['json'].loads(tuning_registry_text)
            )
            if (
                tuning_registry.get("content_sha256")
                != tuning_candidate["registry"]["content_sha256"]
                or services['resolved_tuning_profile'](
                    tuning_registry,
                    tuning_candidate["profile"]["profile_id"],
                )
                != tuning_candidate["profile"]
                or record.get("recipe", {}).get("chipset_tuning")
                != services['tuning_candidate_recipe_identity'](tuning_candidate)
            ):
                errors.append(f"{label}: tuning registry snapshot identity mismatch")
        except (KeyError, TypeError, services['json'].JSONDecodeError, services['PipelineError']) as exc:
            errors.append(f"{label}: cannot validate tuning registry snapshot: {exc}")
    try:
        catalog_snapshot = services['json'].loads(files[recipe["catalog_path"]]["text"])
        if catalog_snapshot.get("source_candidate") != record.get(
            "source_candidate"
        ):
            errors.append(
                f"{label}: recipe snapshot source-candidate binding differs"
            )
        snapshot_spec = catalog_snapshot["cores"][record["core_id"]]
        contract_snapshot_spec = snapshot_spec
        if source_candidate_projection is not None:
            contract_snapshot_spec = services['_canonical_source_candidate_spec'](
                record.get("source_candidate"),
                record["core_id"],
            )
            services['_source_candidate_contract_spec'](
                record["core_id"],
                snapshot_spec,
                contract_snapshot_spec,
                source_candidate_projection,
            )
        if (
            record.get("core_id") == services['VEMULATOR_CORE_ID']
            and not services['vemulator_spec_is_well_formed'](contract_snapshot_spec)
        ):
            errors.append(
                f"{label}: VEmulator catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == services['FREEINTV_CORE_ID']
            and has_pipeline_bundle
            and not services['freeintv_spec_is_well_formed'](contract_snapshot_spec)
        ):
            errors.append(
                f"{label}: FreeIntv catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == services['MGBA_CORE_ID']
            and has_pipeline_bundle
            and not services['mgba_spec_is_well_formed'](contract_snapshot_spec)
        ):
            errors.append(f"{label}: mGBA catalog snapshot contract is invalid")
        if (
            record.get("core_id") == services['PICODRIVE_CORE_ID']
            and not services['picodrive_spec_is_well_formed'](contract_snapshot_spec)
        ):
            errors.append(
                f"{label}: Picodrive catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == services['MAME2003_PLUS_CORE_ID']
            and not services['mame2003_plus_spec_is_well_formed'](contract_snapshot_spec)
        ):
            errors.append(
                f"{label}: MAME2003+ catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == services['FBNEO_CORE_ID']
            and not services['fbneo_spec_is_well_formed'](contract_snapshot_spec)
        ):
            errors.append(
                f"{label}: FBNeo catalog snapshot contract is invalid"
            )
        if has_commit_blacklist and catalog_snapshot.get(
            "commit_blacklist"
        ) != commit_blacklist:
            errors.append(f"{label}: commit blacklist catalog reference mismatch")
        if services['core_spec_sha256'](snapshot_spec) != recipe.get("core_spec_sha256"):
            errors.append(f"{label}: core specification digest mismatch")
        snapshot_resolver = catalog_snapshot.get("resolver")
        recorded_resolver = record_toolchain.get("resolver_digests")
        snapshot_build = (
            snapshot_spec.get("build") if isinstance(snapshot_spec, dict) else None
        )
        if (
            isinstance(snapshot_build, dict)
            and snapshot_build.get("driver") == "direct-cargo"
        ):
            # A cargo record runs in the Rust image, which carries no
            # libretro-super checkout: the captured resolver identity must be
            # the absent shape (paths mirrored from the snapshot, digests
            # None). A real digest here would mean the wrong image built it.
            expected_absent = {"libretro_super_commit": None}
            if isinstance(snapshot_resolver, dict):
                for prefix in ("core_rules", "fetch_script", "build_script"):
                    expected_absent[f"{prefix}_path"] = snapshot_resolver.get(
                        f"{prefix}_path"
                    )
                    expected_absent[f"{prefix}_sha256"] = None
            if recorded_resolver != expected_absent:
                errors.append(f"{label}: resolver snapshot mismatch")
        elif snapshot_resolver != recorded_resolver:
            errors.append(f"{label}: resolver snapshot mismatch")
        record_source = record.get("source", {})
        snapshot_source = snapshot_spec.get("source", {})
        contract_record_source = services['_source_candidate_contract_source_for_guard'](
            record_source,
            source_candidate_projection,
        )
        contract_record_build = services['_source_candidate_contract_build_for_guard'](
            record_build,
            source_candidate_projection,
        )
        contract_source_commit = contract_snapshot_spec.get("source", {}).get(
            "commit"
        )
        if not isinstance(record_source, dict) or not isinstance(snapshot_source, dict):
            errors.append(f"{label}: source specification shape mismatch")
        elif any(
            record_source.get(key) != value
            for key, value in snapshot_source.items()
            # Submodule pins are {path, commit}; records capture the live
            # `git submodule status` shape, so bind the projection instead.
            if key != "submodules"
        ):
            errors.append(f"{label}: source does not match the catalog snapshot")
        elif "submodules" in snapshot_source and [
            {"path": submodule.get("path"), "commit": submodule.get("commit")}
            for submodule in record_source.get("submodules", [])
        ] != snapshot_source["submodules"]:
            errors.append(f"{label}: source does not match the catalog snapshot")
        expected_definitions = services['compile_definitions_for_target'](
            snapshot_spec, record["architecture"]
        )
        expected_source_date_epoch = services['validated_source_date_epoch'](snapshot_spec)
        snapshot_build_spec = snapshot_spec.get("build", {})
        forbidden_needed = services['forbidden_needed_dependencies'](
            snapshot_spec, record.get("artifact", {}).get("needed")
        )
        if forbidden_needed:
            errors.append(
                f"{label}: artifact violates the catalog dependency policy: "
                + ", ".join(forbidden_needed)
            )
        expected_make_variables = services['validated_make_variables'](contract_snapshot_spec)
        expected_git_version = services['validated_git_version'](contract_snapshot_spec)
        expected_generated_source = services['validated_generated_source'](
            contract_snapshot_spec
        )
        expected_recipe_profile = services['validated_recipe_profile'](
            contract_snapshot_spec
        )
        is_combined_git_make_contract = bool(expected_make_variables) and (
            expected_git_version is not None
            and expected_git_version.get("derivation")
            == services['NATIVE_GIT_VERSION_DERIVATION']
            and record.get("core_id") in services['COMBINED_NATIVE_MAKE_CORE_IDS']
        )
        if (
            snapshot_build_spec.get("driver") == "direct-cmake"
            or expected_make_variables
            or expected_git_version is not None
            or expected_generated_source is not None
            or expected_recipe_profile is not None
            or record.get("core_id") in services['EXACT_SOURCE_NATIVE_CORE_IDS']
        ):
            expected_build_contract = services['normalized_build_contract'](
                snapshot_spec,
                record["architecture"],
                core_id=record["core_id"],
                source_candidate_contract_spec=(
                    contract_snapshot_spec
                    if source_candidate_projection is not None
                    else None
                ),
                source_candidate_projection=source_candidate_projection,
            )
            if (
                not isinstance(record_build, dict)
                or set(record_build)
                != set(expected_build_contract).union({"log", "log_sha256"})
                or services['recorded_build_contract'](record_build) != expected_build_contract
                or (
                    expected_generated_source is not None
                    and not services['core_81_golden_build_contract_is_well_formed'](
                        contract_record_build,
                        contract_source_commit,
                        record.get("core_id"),
                        contract_record_source,
                    )
                )
                or (
                    is_combined_git_make_contract
                    and not services['combined_git_version_make_golden_build_contract_is_well_formed'](
                        contract_record_build,
                        contract_source_commit,
                        record.get("core_id"),
                        contract_record_source,
                    )
                )
                or (
                    not is_combined_git_make_contract
                    and bool(expected_make_variables)
                    and not services['make_variable_golden_build_contract_is_well_formed'](
                        record_build
                    )
                )
                or (
                    not is_combined_git_make_contract
                    and
                    expected_git_version is not None
                    and not services['git_version_golden_build_contract_is_well_formed'](
                        contract_record_build,
                        contract_source_commit,
                        record.get("core_id"),
                        contract_record_source,
                        record.get("architecture"),
                    )
                )
                or (
                    record.get("core_id") == services['VEMULATOR_CORE_ID']
                    and not services['vemulator_golden_build_contract_is_well_formed'](
                        contract_record_build,
                        contract_source_commit,
                        record.get("core_id"),
                        contract_record_source,
                    )
                )
                or (
                    record.get("core_id") == services['FREEINTV_CORE_ID']
                    and not services['freeintv_golden_build_contract_is_well_formed'](
                        contract_record_build,
                        contract_source_commit,
                        record.get("core_id"),
                        contract_record_source,
                    )
                )
                or (
                    expected_recipe_profile is not None
                    and not services['picodrive_golden_build_contract_is_well_formed'](
                        contract_record_build,
                        contract_source_commit,
                        record.get("core_id"),
                        contract_record_source,
                        record.get("architecture"),
                    )
                )
                or record_build.get("log") != "build.log"
                or not isinstance(record_build.get("log_sha256"), str)
                or not services['SHA256_RE'].fullmatch(record_build["log_sha256"])
            ):
                errors.append(f"{label}: build does not match the catalog snapshot")
        elif (
            not isinstance(record_build, dict)
            or record_build.get("driver") != snapshot_build_spec.get("driver")
            or record_build.get("environment") != "sanitized-v1"
            or record_build.get("compile_definitions", []) != expected_definitions
            or not services['build_source_date_epoch_matches'](
                record_build, expected_source_date_epoch
            )
        ):
            errors.append(f"{label}: build does not match the catalog snapshot")
    except (KeyError, TypeError, services['json'].JSONDecodeError, services['PipelineError']) as exc:
        errors.append(f"{label}: cannot parse catalog recipe snapshot: {exc}")
    if has_commit_blacklist:
        try:
            blacklist_snapshot = services['json'].loads(
                files[commit_blacklist["path"]]["text"]
            )
            parsed_blacklist = services['parse_commit_blacklist'](blacklist_snapshot)
            if (
                parsed_blacklist.policy_id != commit_blacklist["policy_id"]
                or parsed_blacklist.content_sha256
                != commit_blacklist["content_sha256"]
            ):
                errors.append(f"{label}: recipe commit blacklist identity mismatch")
        except (
            KeyError,
            TypeError,
            services['json'].JSONDecodeError,
            services['CommitBlacklistError'],
        ) as exc:
            errors.append(f"{label}: cannot parse recipe commit blacklist: {exc}")
    if archive_provenance is not None:
        try:
            lock_reference = archive_provenance["lock"]
            validator_reference = archive_provenance["validator"]
            lock_snapshot = services['json'].loads(files[lock_reference["path"]]["text"])
            architecture = archive_provenance["architecture"]
            locked = lock_snapshot["toolchains"][architecture]
            expected_archive = {
                key: locked["archive"][key] for key in ("filename", "sha256", "size")
            }
            # The provenance names the LOCK ENTRY the build ran inside. For
            # every C driver that is the record's target architecture; a
            # direct-cargo record builds both device targets inside the
            # pinned Rust image, so its entry is "rust".
            record_driver = (record.get("build") or {}).get("driver")
            expected_lock_entry = (
                "rust" if record_driver == "direct-cargo"
                else record.get("architecture")
            )
            if (
                architecture != expected_lock_entry
                or validator_reference.get("path") != "scripts/toolchain_archive.py"
                or not isinstance(validator_reference.get("sha256"), str)
                or not services['SHA256_RE'].fullmatch(validator_reference["sha256"])
                or lock_snapshot.get("schema_version")
                != lock_reference.get("schema_version")
                or lock_snapshot.get("lock_id") != lock_reference.get("lock_id")
                or lock_snapshot.get("content_sha256")
                != lock_reference.get("content_sha256")
                or lock_snapshot.get("content_sha256")
                != services['toolchain_lock_content_sha256'](lock_snapshot)
                or archive_provenance.get("archive") != expected_archive
                or locked.get("image", {}).get("tag")
                != record_toolchain.get("image")
                or locked.get("image", {}).get("id")
                != record_toolchain.get("resolved_image_id")
                or locked.get("dockerfile", {}).get("path")
                != record_toolchain.get("dockerfile")
                or locked.get("dockerfile", {}).get("sha256")
                != record_toolchain.get("dockerfile_sha256")
                or locked.get("dockerfile", {}).get("linkage")
                != record_toolchain.get("dockerfile_linkage")
            ):
                errors.append(f"{label}: recipe snapshot archive provenance mismatch")
        except (AttributeError, KeyError, TypeError, services['json'].JSONDecodeError) as exc:
            errors.append(f"{label}: cannot parse toolchain lock recipe snapshot: {exc}")
    return errors


def verify_recipe_snapshot(
    path: Path,
    record: dict,
    label: str,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    """Verify the recipe snapshot read from its named path."""

    return services['_verify_recipe_snapshot'](path, record, label)


def _verify_historical_recipe_snapshot(
    path: Path,
    record: dict,
    label: str,
    *,
    snapshot: dict | None = None,
    services: StoredEvidenceServices,
) -> list[str]:
    """Validate immutable recipe bytes without today's core policy constants."""

    errors: list[str] = []
    if snapshot is None:
        try:
            snapshot = services['load_json'](path)
        except services['PipelineError'] as exc:
            return [str(exc)]
    recipe = record.get("recipe")
    source = record.get("source")
    toolchain = record.get("toolchain")
    build = record.get("build")
    if not all(
        isinstance(value, dict)
        for value in (recipe, source, toolchain, build)
    ):
        return [f"{label}: historical recipe record fields are invalid"]
    pipeline_bundle = recipe.get("pipeline_bundle")
    if not services['pipeline_source_bundle_is_well_formed'](pipeline_bundle):
        return [f"{label}: historical recipe pipeline bundle is invalid"]
    tuning_candidate = record.get("tuning_candidate")
    if tuning_candidate is not None:
        try:
            tuning_candidate = services['validated_tuning_candidate_shape'](tuning_candidate)
        except services['PipelineError'] as exc:
            return [f"{label}: {exc}"]
    historical_generated_source = build.get("generated_source")
    has_historical_generated_source = (
        services['generated_source_contract_is_well_formed'](historical_generated_source)
    )
    if (
        "generated_source" in build
        and not has_historical_generated_source
    ):
        errors.append(
            f"{label}: historical generated-source contract is invalid"
        )
    host_execution = recipe.get("host_execution")
    if host_execution is not None:
        try:
            host_execution = services['validate_host_execution_contract'](
                host_execution, repository_root=services['ROOT']
            )
        except services['PipelineError'] as exc:
            errors.append(f"{label}: historical host execution is invalid: {exc}")
            host_execution = None
    expected_snapshot_version = (
        12
        if "host_execution" in recipe
        else 11
        if tuning_candidate is not None
        else 10
        if has_historical_generated_source
        else 9
    )
    if (
        snapshot.get("schema_version") != expected_snapshot_version
        or snapshot.get("core_id") != record.get("core_id")
        or snapshot.get("architecture") != record.get("architecture")
        or snapshot.get("source") != source
        or snapshot.get("recipe") != recipe
        or snapshot.get("tuning_candidate") != tuning_candidate
        or snapshot.get("host_execution") != host_execution
    ):
        errors.append(f"{label}: historical recipe snapshot identity mismatch")

    archive_provenance = toolchain.get("archive_provenance")
    expected_toolchain = {
        "image_id": toolchain.get("resolved_image_id"),
        "dockerfile": toolchain.get("dockerfile"),
        "dockerfile_sha256": toolchain.get("dockerfile_sha256"),
        "resolver_digests": toolchain.get("resolver_digests"),
    }
    if archive_provenance is not None:
        if not isinstance(archive_provenance, dict):
            errors.append(f"{label}: historical archive provenance is invalid")
        else:
            expected_toolchain["archive_provenance"] = archive_provenance
    if snapshot.get("toolchain") != expected_toolchain:
        errors.append(f"{label}: historical recipe toolchain differs")
    expected_build = {
        key: value
        for key, value in build.items()
        if key not in {"log", "log_sha256"}
    }
    if snapshot.get("build") != expected_build:
        errors.append(f"{label}: historical recipe build contract differs")

    files = snapshot.get("files")
    if not isinstance(files, dict):
        return [*errors, f"{label}: historical recipe files are invalid"]
    expected_hashes = dict(pipeline_bundle["files"])
    direct_hashes = {
        recipe.get("catalog_path"): recipe.get("catalog_sha256"),
        recipe.get("workflow"): recipe.get("workflow_sha256"),
        str(services['Path'](services['__file__']).relative_to(services['ROOT'])): recipe.get("pipeline_sha256"),
        toolchain.get("dockerfile"): toolchain.get("dockerfile_sha256"),
    }
    commit_blacklist = recipe.get("commit_blacklist")
    if isinstance(commit_blacklist, dict):
        direct_hashes[commit_blacklist.get("path")] = commit_blacklist.get(
            "file_sha256"
        )
    if tuning_candidate is not None:
        direct_hashes[tuning_candidate["registry"]["path"]] = tuning_candidate[
            "registry"
        ]["file_sha256"]
    if host_execution is not None:
        for reference in (
            host_execution["instrumentation"]["tool_wrapper"],
            host_execution["instrumentation"]["unit_runner_source"],
            host_execution["telemetry_schema"],
        ):
            direct_hashes[reference["path"]] = reference["file_sha256"]
    if isinstance(archive_provenance, dict):
        lock_reference = archive_provenance.get("lock")
        validator_reference = archive_provenance.get("validator")
        if isinstance(lock_reference, dict):
            direct_hashes[lock_reference.get("path")] = lock_reference.get(
                "file_sha256"
            )
        if isinstance(validator_reference, dict):
            direct_hashes[validator_reference.get("path")] = validator_reference.get(
                "sha256"
            )
    overlays = build.get("overlays")
    if isinstance(overlays, list):
        for overlay in overlays:
            if isinstance(overlay, dict):
                direct_hashes[overlay.get("patch_path")] = overlay.get(
                    "patch_sha256"
                )
    metadata_replacement = build.get("metadata_replacement")
    if isinstance(metadata_replacement, dict):
        direct_hashes[metadata_replacement.get("path")] = (
            metadata_replacement.get("replacement_sha256")
        )
    expected_hashes.update(
        {
            relative: digest
            for relative, digest in direct_hashes.items()
            if isinstance(relative, str) and relative
        }
    )
    if set(files) != set(expected_hashes):
        errors.append(f"{label}: historical recipe file set differs")
        return errors
    for relative, expected_sha256 in expected_hashes.items():
        stored = files.get(relative)
        if not isinstance(stored, dict):
            errors.append(f"{label}: historical recipe file is invalid: {relative}")
            continue
        text = stored.get("text")
        if (
            not isinstance(expected_sha256, str)
            or not services['SHA256_RE'].fullmatch(expected_sha256)
            or not isinstance(text, str)
            or stored.get("sha256") != expected_sha256
            or services['sha256_bytes'](text.encode()) != expected_sha256
        ):
            errors.append(f"{label}: historical recipe digest differs: {relative}")

    if tuning_candidate is not None:
        try:
            tuning_registry = services['validate_chipset_tunings'](
                services['json'].loads(files[tuning_candidate["registry"]["path"]]["text"])
            )
            if (
                tuning_registry.get("content_sha256")
                != tuning_candidate["registry"]["content_sha256"]
                or services['resolved_tuning_profile'](
                    tuning_registry,
                    tuning_candidate["profile"]["profile_id"],
                )
                != tuning_candidate["profile"]
                or recipe.get("chipset_tuning")
                != services['tuning_candidate_recipe_identity'](tuning_candidate)
            ):
                errors.append(f"{label}: historical tuning registry differs")
        except (KeyError, TypeError, services['json'].JSONDecodeError, services['PipelineError']) as exc:
            errors.append(f"{label}: cannot parse historical tuning registry: {exc}")

    catalog_path = recipe.get("catalog_path")
    try:
        historical_catalog = services['json'].loads(files[catalog_path]["text"])
        if historical_catalog.get("source_candidate") != record.get(
            "source_candidate"
        ):
            errors.append(
                f"{label}: historical recipe source-candidate binding differs"
            )
        historical_spec = historical_catalog["cores"][record["core_id"]]
        if services['core_spec_sha256'](historical_spec) != recipe.get("core_spec_sha256"):
            errors.append(f"{label}: historical core specification differs")
        if historical_spec.get("workflow") != recipe.get("workflow"):
            errors.append(f"{label}: historical workflow binding differs")
        if record.get("architecture") not in historical_spec.get("targets", []):
            errors.append(f"{label}: historical target binding differs")
        historical_source = historical_spec.get("source")
        if not isinstance(historical_source, dict) or any(
            historical_source.get(spec_key) != source.get(record_key)
            for spec_key, record_key in (
                ("url", "url"),
                ("requested_ref", "requested_ref"),
                ("commit", "commit"),
                ("tree", "tree"),
            )
            if spec_key in historical_source
        ):
            errors.append(f"{label}: historical source binding differs")
        historical_build = (
            historical_spec.get("build")
            if isinstance(historical_spec, dict)
            else None
        )
        if (
            isinstance(historical_build, dict)
            and historical_build.get("driver") == "direct-cargo"
        ):
            historical_resolver = historical_catalog.get("resolver")
            expected_absent = {"libretro_super_commit": None}
            if isinstance(historical_resolver, dict):
                for prefix in ("core_rules", "fetch_script", "build_script"):
                    expected_absent[f"{prefix}_path"] = historical_resolver.get(
                        f"{prefix}_path"
                    )
                    expected_absent[f"{prefix}_sha256"] = None
            if toolchain.get("resolver_digests") != expected_absent:
                errors.append(f"{label}: historical resolver binding differs")
        elif historical_catalog.get("resolver") != toolchain.get(
            "resolver_digests"
        ):
            errors.append(f"{label}: historical resolver binding differs")
        if isinstance(commit_blacklist, dict) and historical_catalog.get(
            "commit_blacklist"
        ) != commit_blacklist:
            errors.append(f"{label}: historical blacklist binding differs")
    except (KeyError, TypeError, services['json'].JSONDecodeError) as exc:
        errors.append(f"{label}: cannot parse historical catalog snapshot: {exc}")
    return errors


def verify_historical_recipe_snapshot(
    path: Path,
    record: dict,
    label: str,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    """Verify historical recipe bytes read from their named path."""

    return services['_verify_historical_recipe_snapshot'](path, record, label)


def _verify_stored_e2e_bundle(
    golden: dict,
    core_id: str,
    selected_arch: str,
    _validation_context: _PinValidationContext | None = None,
    *,
    historical_recipe_proofs: bool = False,
    verify_reproduction: bool = True,
    services: StoredEvidenceServices,
) -> list[str]:
    if _validation_context is None:
        _validation_context = services['_PinValidationContext']()
    errors: list[str] = []
    label = f"{core_id}/{selected_arch}"
    tuning_candidate = golden.get("tuning_candidate")
    if tuning_candidate is not None:
        try:
            tuning_candidate = services['validated_tuning_candidate_shape'](tuning_candidate)
        except services['PipelineError'] as exc:
            errors.append(f"{label}: {exc}")
            tuning_candidate = None
    elif golden.get("recipe", {}).get("chipset_tuning") is not None:
        errors.append(f"{label}: tuned golden lacks tuning candidate evidence")
    log_contract = (
        None if historical_recipe_proofs else services['core_log_contract_for'](core_id)
    )
    local_store = golden.get("local_store", {})
    try:
        e2e_entry = local_store["e2e_record"]
        e2e_path = services['safe_child'](
            services['ROOT'], e2e_entry["path"], f"{label} stored E2E record"
        )
        package_entry = local_store["package"]
        package_path = services['safe_child'](
            services['ROOT'], package_entry["path"], f"{label} stored package"
        )
        evidence = services['verified_json_object'](
            e2e_path,
            e2e_entry["sha256"],
            f"{label} stored E2E record",
            _validation_context,
        )
    except (KeyError, services['PipelineError']) as exc:
        return [f"{label}: cannot load stored E2E evidence: {exc}"]
    if (
        evidence.get("result") != "passed"
        or not evidence.get("local_only")
        or evidence.get("publication") != "disabled"
        or evidence.get("content_sha256") != services['e2e_content_sha256'](evidence)
    ):
        errors.append(f"{label}: stored E2E record contract is invalid")
    if not services['runner_evidence_is_well_formed'](evidence.get("runner")):
        errors.append(f"{label}: stored E2E runner evidence is invalid")
    else:
        try:
            services['validate_bound_host_telemetry'](evidence, e2e_path)
        except services['PipelineError'] as exc:
            errors.append(f"{label}: stored host telemetry is invalid: {exc}")
    if evidence.get("content_sha256") != golden.get("e2e", {}).get("content_sha256"):
        errors.append(f"{label}: stored E2E content is not bound to the golden")
    if evidence.get("run_id") != golden.get("e2e", {}).get("run_id"):
        errors.append(f"{label}: stored E2E run ID is not bound to the golden")
    if tuning_candidate is not None and evidence.get("tuning_candidate") != tuning_candidate:
        errors.append(f"{label}: stored E2E tuning candidate differs from golden")
    build_entries = [
        item for item in evidence.get("builds", []) if item.get("core_id") == core_id
    ]
    expected_targets = set(golden.get("e2e", {}).get("build_records", {}))
    if not expected_targets:
        return [f"{label}: stored E2E target set is empty"]
    if (
        {item.get("architecture") for item in build_entries} != expected_targets
        or len(build_entries) != len(expected_targets)
        or any(item.get("result") != "passed" for item in build_entries)
    ):
        errors.append(f"{label}: stored E2E target set is invalid")
        return errors
    records: dict[str, dict] = {}
    for entry in build_entries:
        target = entry["architecture"]
        try:
            record_entry = local_store["build_records"][target]
            record_path = services['safe_child'](
                services['ROOT'], record_entry["path"], f"{label} stored {target} build record"
            )
            record = services['verified_json_object'](
                record_path,
                record_entry["sha256"],
                f"{label} stored {target} build record",
                _validation_context,
            )
            log_entry = local_store["build_logs"][target]
            recipe_entry = local_store["recipe_snapshots"][target]
            log_path = services['safe_child'](services['ROOT'], log_entry["path"], f"{label} stored {target} log")
            recipe_path = services['safe_child'](
                services['ROOT'], recipe_entry["path"], f"{label} stored {target} recipe"
            )
            recipe_snapshot = services['verified_json_object'](
                recipe_path,
                recipe_entry.get("sha256"),
                f"{label} stored {target} recipe",
                _validation_context,
            )
            source_candidate_projection = (
                services['source_candidate_record_contract_projection'](
                    golden.get("source_candidate"),
                    core_id=core_id,
                    recorded_source=record.get("source"),
                    recorded_recipe=record.get("recipe"),
                    recipe_snapshot=recipe_snapshot,
                )
                if not historical_recipe_proofs
                else None
            )
        except (KeyError, services['PipelineError']) as exc:
            errors.append(f"{label}: cannot load stored {target} evidence: {exc}")
            continue
        if (
            record_entry.get("sha256") != entry.get("record_sha256")
            or record_entry.get("sha256")
            != golden.get("e2e", {}).get("build_records", {}).get(target)
        ):
            errors.append(f"{label}: stored {target} record digest is not E2E-bound")
        try:
            services['require_host_execution_runner_coupling'](
                evidence, record, f"{label}/{target} stored build"
            )
        except services['PipelineError'] as exc:
            errors.append(str(exc))
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != target
            or record.get("result") != "passed"
            or record.get("build_exit_code") != 0
            or not record.get("local_only")
            or record.get("publication") != "disabled"
        ):
            errors.append(f"{label}: stored {target} build record contract is invalid")
        if tuning_candidate is not None and (
            record.get("tuning_candidate") != tuning_candidate
            or record.get("recipe", {}).get("chipset_tuning")
            != services['tuning_candidate_recipe_identity'](tuning_candidate)
            or target != tuning_candidate["profile"]["architecture"]
        ):
            errors.append(f"{label}: stored {target} tuning identity is invalid")
        source = record.get("source", {})
        toolchain = record.get("toolchain", {})
        record_build = record.get("build", {})
        contract_source = services['_source_candidate_contract_source_for_guard'](
            source,
            source_candidate_projection,
        )
        contract_build = services['_source_candidate_contract_build_for_guard'](
            record_build,
            source_candidate_projection,
        )
        contract_source_commit = (
            contract_source.get("resolved_commit")
            if isinstance(contract_source, services['Mapping'])
            else None
        )
        record_metadata_replacement = (
            record_build.get("metadata_replacement")
            if isinstance(record_build, dict)
            else None
        )
        if record_metadata_replacement is not None and not (
            services['metadata_matches_replacement'](
                record.get("metadata"), record_metadata_replacement
            )
        ):
            errors.append(
                f"{label}: stored {target} metadata does not match its replacement"
            )
        if not isinstance(toolchain, dict):
            errors.append(f"{label}: stored {target} toolchain is not an object")
            toolchain = {}
        archive_provenance = toolchain.get("archive_provenance")
        if (
            source.get("resolved_commit") != source.get("commit")
            or source.get("resolved_url") != source.get("url")
            or not services['SHA1_RE'].fullmatch(source.get("tree", ""))
            or toolchain.get("resolved_image_id") != toolchain.get("image_id")
            or toolchain.get("resolver_digests", {}).get("libretro_super_commit")
            != toolchain.get("libretro_super_commit")
        ):
            errors.append(f"{label}: stored {target} provenance is internally inconsistent")
        if archive_provenance is not None:
            if not isinstance(archive_provenance, dict) or (
                type(record.get("schema_version")) is not int
                or record["schema_version"] != 2
                or golden.get("provenance_version") != 2
                or archive_provenance.get("architecture")
                != (
                    "rust"
                    if isinstance(record_build, dict)
                    and record_build.get("driver") == "direct-cargo"
                    else target
                )
            ):
                errors.append(f"{label}: stored {target} archive provenance is invalid")
        elif golden.get("provenance_version") is not None:
            errors.append(f"{label}: stored {target} legacy provenance marker is invalid")
        has_make_variables = isinstance(record_build, dict) and (
            "make_variables" in record_build
        )
        has_git_version = isinstance(record_build, dict) and (
            "git_version" in record_build
        )
        has_generated_source = isinstance(record_build, dict) and (
            "generated_source" in record_build
        )
        has_recipe_profile = isinstance(record_build, dict) and (
            "recipe_profile" in record_build
        )
        is_combined_git_make_build = (
            core_id in services['COMBINED_NATIVE_MAKE_CORE_IDS']
            and has_make_variables
            and has_git_version
        )
        if not isinstance(record_build, dict) or (
            "source_date_epoch" in record_build
            and not services['source_date_epoch_is_well_formed'](
                record_build["source_date_epoch"]
            )
        ) or (
            has_generated_source
            and core_id != services['CORE_81_ID']
        ) or (
            core_id == services['CORE_81_ID']
            and (
                not has_generated_source
                or not services['core_81_golden_build_contract_is_well_formed'](
                    contract_build,
                    contract_source_commit,
                    core_id,
                    contract_source,
                )
            )
        ) or (
            is_combined_git_make_build
            and not services['combined_git_version_make_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        ) or (
            has_make_variables
            and not is_combined_git_make_build
            and not services['make_variable_golden_build_contract_is_well_formed'](
                record_build
            )
        ) or (
            has_git_version
            and not is_combined_git_make_build
            and not services['git_version_golden_build_contract_is_well_formed'](
                contract_build,
                contract_source_commit,
                core_id,
                contract_source,
                target,
            )
        ) or (
            core_id == services['VEMULATOR_CORE_ID']
            and not services['vemulator_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        ) or (
            core_id == services['FREEINTV_CORE_ID']
            and not services['freeintv_golden_build_contract_is_well_formed'](
                contract_build, contract_source_commit, core_id, contract_source
            )
        ) or (
            has_recipe_profile
            and (
                core_id != services['PICODRIVE_CORE_ID']
                or not services['picodrive_golden_build_contract_is_well_formed'](
                    contract_build,
                    contract_source_commit,
                    core_id,
                    contract_source,
                    target,
                )
            )
        ) or (
            core_id == services['PICODRIVE_CORE_ID'] and not has_recipe_profile
        ):
            errors.append(f"{label}: stored {target} build contract is invalid")
        if (
            not log_path.is_file()
            or log_entry.get("sha256") != record.get("build", {}).get("log_sha256")
        ):
            errors.append(f"{label}: stored {target} log is not build-record-bound")
        else:
            try:
                definitions = record.get("build", {}).get("compile_definitions", [])
                log_text = services['verified_utf8_text'](
                    log_path,
                    log_entry["sha256"],
                    f"{label} stored {target} log",
                    _validation_context,
                )
                proof_key = (
                    target,
                    log_entry.get("sha256", ""),
                    services['sha256_bytes'](
                        services['json'].dumps(
                            record, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ),
                    (
                        source_candidate_projection.candidate_id
                        if source_candidate_projection is not None
                        else ""
                    ),
                )
                proofs = (
                    _validation_context.log_proofs.get(proof_key)
                    if _validation_context is not None
                    and not historical_recipe_proofs
                    else None
                )
                make_variables = record_build.get("make_variables")
                git_version = record_build.get("git_version")
                metadata_replacement = record_build.get("metadata_replacement")
                if proofs is None:
                    proofs = (
                        isinstance(definitions, list)
                        and services['compile_log_proves_definitions'](
                            log_text, definitions, target
                        ),
                        make_variables is None
                        or services['make_variable_log_proves_contract'](
                            log_text, make_variables, target
                        ),
                        git_version is None
                        or services['git_version_log_proves_contract'](
                            log_text,
                            git_version,
                            source.get("resolved_commit"),
                            target,
                        ),
                        metadata_replacement is None
                        or services['metadata_replacement_log_proves_contract'](
                            log_text, metadata_replacement
                        ),
                        historical_recipe_proofs
                        or services['_registered_core_log_contract_proves'](
                            log_text,
                            core_id,
                            target,
                            source.get("resolved_commit"),
                            source.get("tree"),
                            tuning=(
                                tuning_candidate["profile"]
                                if tuning_candidate is not None
                                else None
                            ),
                            source_candidate_projection=(
                                source_candidate_projection
                            ),
                        ),
                        tuning_candidate is None
                        or services['_chipset_tuning_log_proves_resolved'](
                            log_text,
                            tuning_candidate["profile"],
                            target,
                        ),
                    )
                    if (
                        _validation_context is not None
                        and not historical_recipe_proofs
                        and all(proofs)
                    ):
                        _validation_context.log_proofs[proof_key] = proofs
                (
                    definitions_proven,
                    make_proven,
                    version_proven,
                    metadata_proven,
                    registered_contract_proven,
                    tuning_proven,
                ) = proofs
                if not definitions_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its compile definitions"
                    )
                if not make_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its make-variable contract"
                    )
                if not version_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its "
                        "commit-derived GIT_VERSION contract"
                    )
                if not metadata_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its "
                        "metadata replacement contract"
                    )
                if log_contract is not None and not registered_contract_proven:
                    errors.append(
                        f"{label}: stored {target} {log_contract.failure_message}"
                    )
                if not tuning_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its tuning contract"
                    )
            except services['PipelineError'] as exc:
                errors.append(str(exc))
        snapshot_validator = (
            services['_verify_historical_recipe_snapshot']
            if historical_recipe_proofs
            else services['_verify_recipe_snapshot']
        )
        try:
            stored_recipe_snapshot = services['verified_json_object'](
                recipe_path,
                recipe_entry["sha256"],
                f"{label} stored {target} recipe",
                _validation_context,
            )
        except services['PipelineError'] as exc:
            errors.append(str(exc))
            continue
        snapshot_record = record
        if golden.get("source_candidate") is not None:
            snapshot_record = services['copy'].deepcopy(record)
            snapshot_record["source_candidate"] = services['copy'].deepcopy(
                golden["source_candidate"]
            )
        errors.extend(
            snapshot_validator(
                recipe_path,
                snapshot_record,
                f"{label}/{target}",
                snapshot=stored_recipe_snapshot,
            )
        )
        records[target] = record
    if set(records) != expected_targets or selected_arch not in records:
        return errors
    package_entries = [
        item for item in evidence.get("packages", []) if item.get("core_id") == core_id
    ]
    if (
        len(package_entries) != 1
        or package_entries[0].get("result") != "packaged"
        or package_entries[0].get("sha256")
        != golden.get("e2e", {}).get("package_sha256")
    ):
        errors.append(f"{label}: stored E2E package entry is not golden-bound")
    selected = records[selected_arch]
    selected_fields = ["source", "recipe", "toolchain", "artifact", "metadata"]
    if (
        core_id
        in (
            services['EXACT_GIT_VERSION_CORE_IDS']
            | services['EXACT_SOURCE_NATIVE_CORE_IDS']
            | {"vecx"}
        )
        or "build" in golden
    ):
        selected_fields.append("build")
    for field in selected_fields:
        if selected.get(field) != golden.get(field):
            errors.append(f"{label}: stored selected record {field} differs from golden")
    try:
        artifact_entry = local_store["artifact"]
        stored_artifact = services['safe_child'](
            services['ROOT'], artifact_entry["path"], f"{label} stored artifact"
        )
        artifact_bytes = services['verified_file_bytes'](
            stored_artifact,
            artifact_entry["sha256"],
            f"{label} stored artifact",
            _validation_context,
        )
        current_artifact = services['_validate_artifact_bytes'](
            artifact_bytes, selected_arch
        )
        if (
            current_artifact.get("status") != "valid"
            or current_artifact.get("sha256") != selected["artifact"].get("sha256")
            or current_artifact.get("sha256") != artifact_entry.get("sha256")
        ):
            errors.append(f"{label}: stored artifact no longer passes static validation")
    except (KeyError, services['PipelineError']) as exc:
        errors.append(f"{label}: cannot revalidate stored artifact: {exc}")
    try:
        package_bytes = services['verified_file_bytes'](
            package_path,
            package_entry["sha256"],
            f"{label} stored package",
            _validation_context,
        )
        with services['zipfile'].ZipFile(services['io'].BytesIO(package_bytes)) as archive:
            manifest = services['decode_json_object'](
                archive.read("manifest.json"), f"{label} stored package manifest"
            )
            expected_members = {"manifest.json"}
            for target, record in records.items():
                member = (
                    f"{services['ARCH_LAYOUT'][target]['package_directory']}/"
                    f"{record['artifact']['path']}"
                )
                expected_members.add(member)
                packaged = manifest.get("artifacts", {}).get(target, {})
                if (
                    packaged.get("path") != member
                    or packaged.get("sha256") != record["artifact"].get("sha256")
                    or packaged.get("source_commit")
                    != record["source"].get("resolved_commit")
                    or packaged.get("toolchain_image_id")
                    != record["toolchain"].get("resolved_image_id")
                    or services['sha256_bytes'](archive.read(member)) != record["artifact"].get("sha256")
                ):
                    errors.append(f"{label}: stored package {target} artifact mismatch")
            metadata_hashes = {record["metadata"].get("sha256") for record in records.values()}
            metadata_names = {record["metadata"].get("path") for record in records.values()}
            if len(metadata_hashes) != 1 or len(metadata_names) != 1:
                errors.append(f"{label}: stored target metadata is inconsistent")
            else:
                metadata_name = next(iter(metadata_names))
                metadata_sha = next(iter(metadata_hashes))
                expected_members.add(metadata_name)
                if (
                    manifest.get("metadata", {}).get("path") != metadata_name
                    or manifest.get("metadata", {}).get("sha256") != metadata_sha
                    or services['sha256_bytes'](archive.read(metadata_name)) != metadata_sha
                ):
                    errors.append(f"{label}: stored package metadata mismatch")
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist()) != expected_members
                or manifest.get("core_id") != core_id
                or not manifest.get("local_only")
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != expected_targets
                or (
                    tuning_candidate is not None
                    and manifest.get("tuning_candidate") != tuning_candidate
                )
                or (
                    tuning_candidate is None
                    and "tuning_candidate" in manifest
                )
            ):
                errors.append(f"{label}: stored package contract is invalid")
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        services['json'].JSONDecodeError,
        services['zipfile'].BadZipFile,
        services['PipelineError'],
    ) as exc:
        errors.append(f"{label}: cannot validate stored package: {exc}")
    if tuning_candidate is not None and verify_reproduction:
        errors.extend(
            services['_verify_tuned_reproduction_bundle'](
                golden,
                core_id,
                selected_arch,
                tuning_candidate,
                _validation_context,
                historical_recipe_proofs=historical_recipe_proofs,
            )
        )
    return errors


def verify_stored_e2e_bundle(
    golden: dict,
    core_id: str,
    selected_arch: str,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    """Verify stored evidence with a fresh, operation-local proof cache."""

    return services['_verify_stored_e2e_bundle'](
        golden,
        core_id,
        selected_arch,
        services['_PinValidationContext'](),
    )


def _verify_tuned_reproduction_bundle(
    golden: dict,
    core_id: str,
    arch: str,
    tuning_candidate: dict,
    validation_context: _PinValidationContext | None,
    *,
    historical_recipe_proofs: bool,
    services: StoredEvidenceServices,
) -> list[str]:
    """Validate the second independently stored E2E via the normal deep walk."""

    label = f"{core_id}/{arch} tuned reproduction"
    proof = golden.get("reproduction")
    if not isinstance(proof, dict) or set(proof) != {
        "schema_version",
        "validation_scope",
        "selected",
        "reproduction",
        "equivalent_outputs",
    }:
        return [f"{label}: reproduction proof fields are not exact"]
    if (
        proof.get("schema_version") != 1
        or proof.get("validation_scope") != services['TUNED_REPRODUCTION_SCOPE']
    ):
        return [f"{label}: reproduction proof identity is invalid"]
    side_keys = {
        "run_id",
        "content_sha256",
        "e2e_record",
        "build_record",
        "build_log",
        "recipe_snapshot",
    }
    selected_side = proof.get("selected")
    reproduction_side = proof.get("reproduction")
    if (
        not isinstance(selected_side, dict)
        or set(selected_side) != side_keys
        or not isinstance(reproduction_side, dict)
        or set(reproduction_side) != side_keys
    ):
        return [f"{label}: reproduction side fields are not exact"]
    local_store = golden.get("local_store", {})
    if (
        selected_side.get("e2e_record") != local_store.get("e2e_record")
        or selected_side.get("build_record")
        != local_store.get("build_records", {}).get(arch)
        or selected_side.get("build_log")
        != local_store.get("build_logs", {}).get(arch)
        or selected_side.get("recipe_snapshot")
        != local_store.get("recipe_snapshots", {}).get(arch)
        or selected_side.get("run_id") != golden.get("e2e", {}).get("run_id")
        or selected_side.get("content_sha256")
        != golden.get("e2e", {}).get("content_sha256")
    ):
        return [f"{label}: selected proof differs from the golden store"]
    namespace_by_key = {
        "e2e_record": "e2e",
        "build_record": "build-records",
        "build_log": "logs",
        "recipe_snapshot": "recipes",
    }
    if validation_context is None:
        validation_context = services['_PinValidationContext']()
    loaded_paths: dict[str, Path] = {}
    loaded_bytes: dict[str, bytes] = {}
    errors: list[str] = []
    for key, namespace in namespace_by_key.items():
        entry = reproduction_side.get(key)
        if not isinstance(entry, dict):
            errors.append(f"{label}: {key} store reference is invalid")
            continue
        try:
            path = services['require_canonical_store_entry'](entry, namespace, f"{label} {key}")
            loaded_bytes[key] = services['verified_file_bytes'](
                path,
                entry.get("sha256"),
                f"{label} {key} store bytes",
                validation_context,
            )
            loaded_paths[key] = path
        except services['PipelineError'] as exc:
            errors.append(str(exc))
    if errors or set(loaded_paths) != set(namespace_by_key):
        return errors
    try:
        reproduction_e2e = services['decode_json_object'](
            loaded_bytes["e2e_record"], f"{label} E2E record"
        )
        reproduction_record = services['decode_json_object'](
            loaded_bytes["build_record"], f"{label} build record"
        )
    except services['PipelineError'] as exc:
        return [f"{label}: cannot load reproduction records: {exc}"]
    builds = reproduction_e2e.get("builds")
    packages = reproduction_e2e.get("packages")
    if (
        reproduction_e2e.get("result") != "passed"
        or reproduction_e2e.get("local_only") is not True
        or reproduction_e2e.get("publication") != "disabled"
        or reproduction_e2e.get("tuning_candidate") != tuning_candidate
        or reproduction_e2e.get("content_sha256")
        != reproduction_side.get("content_sha256")
        or reproduction_e2e.get("content_sha256")
        != services['e2e_content_sha256'](reproduction_e2e)
        or reproduction_e2e.get("run_id") != reproduction_side.get("run_id")
        or not isinstance(builds, list)
        or len(builds) != 1
        or not isinstance(packages, list)
        or len(packages) != 1
        or builds[0].get("record_sha256")
        != reproduction_side["build_record"].get("sha256")
        or packages[0].get("sha256")
        != local_store.get("package", {}).get("sha256")
    ):
        return [f"{label}: stored reproduction E2E binding is invalid"]
    if (
        selected_side.get("run_id") == reproduction_side.get("run_id")
        or selected_side.get("e2e_record") == reproduction_side.get("e2e_record")
        or selected_side.get("build_record") == reproduction_side.get("build_record")
    ):
        return [f"{label}: E2E runs are not independent"]
    pseudo = services['copy'].deepcopy(golden)
    pseudo.pop("reproduction", None)
    for field in ("source", "recipe", "toolchain", "build", "artifact", "metadata"):
        pseudo[field] = services['copy'].deepcopy(reproduction_record.get(field))
    pseudo["tuning_candidate"] = services['copy'].deepcopy(tuning_candidate)
    pseudo["e2e"] = {
        "run_id": reproduction_e2e["run_id"],
        "record": reproduction_side["e2e_record"]["path"],
        "record_sha256": reproduction_side["e2e_record"]["sha256"],
        "content_sha256": reproduction_e2e["content_sha256"],
        "package": local_store["package"]["path"],
        "package_sha256": local_store["package"]["sha256"],
        "build_records": {arch: reproduction_side["build_record"]["sha256"]},
    }
    pseudo["local_store"] = {
        "availability": "local-only",
        "artifact": services['copy'].deepcopy(local_store["artifact"]),
        "metadata": services['copy'].deepcopy(local_store["metadata"]),
        "e2e_record": services['copy'].deepcopy(reproduction_side["e2e_record"]),
        "package": services['copy'].deepcopy(local_store["package"]),
        "build_records": {arch: services['copy'].deepcopy(reproduction_side["build_record"])},
        "build_logs": {arch: services['copy'].deepcopy(reproduction_side["build_log"])},
        "recipe_snapshots": {
            arch: services['copy'].deepcopy(reproduction_side["recipe_snapshot"])
        },
    }
    errors.extend(
        services['_verify_stored_e2e_bundle'](
            pseudo,
            core_id,
            arch,
            validation_context,
            historical_recipe_proofs=historical_recipe_proofs,
            verify_reproduction=False,
        )
    )
    selected_bundle = {
        "record": {
            key: services['copy'].deepcopy(golden.get(key))
            for key in (
                "source", "recipe", "toolchain", "build", "artifact", "metadata"
            )
        }
    }
    selected_bundle["record"].update(
        {
            "schema_version": reproduction_record.get("schema_version"),
            "local_only": True,
            "publication": "disabled",
            "core_id": core_id,
            "architecture": arch,
            "result": "passed",
            "build_exit_code": 0,
            "tuning_candidate": services['copy'].deepcopy(tuning_candidate),
        }
    )
    selected_bundle["package_record"] = packages[0]
    reproduction_bundle = {
        "record": reproduction_record,
        "package_record": packages[0],
    }
    if services['tuned_candidate_build_identity'](selected_bundle) != services['tuned_candidate_build_identity'](
        reproduction_bundle
    ):
        errors.append(f"{label}: build semantics differ from selected run")
    expected_outputs = proof.get("equivalent_outputs")
    if (
        not isinstance(expected_outputs, dict)
        or services['tuned_candidate_output_identity'](reproduction_bundle) != expected_outputs
        or expected_outputs
        != {
            "artifact": {
                "sha256": golden.get("artifact", {}).get("sha256"),
                "size": golden.get("artifact", {}).get("size"),
            },
            "metadata": {
                "sha256": golden.get("metadata", {}).get("sha256"),
                "size": golden.get("metadata", {}).get("size"),
            },
            "package": {
                "name": packages[0].get("path"),
                "sha256": local_store.get("package", {}).get("sha256"),
                "size": packages[0].get("size"),
            },
        }
    ):
        errors.append(f"{label}: equivalent output identity is invalid")
    return errors


def verify_tuned_reproduction_bundle(
    golden: dict,
    core_id: str,
    arch: str,
    tuning_candidate: dict,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    """Verify tuned reproduction with a fresh, ordinary proof context."""

    return services['_verify_tuned_reproduction_bundle'](
        golden,
        core_id,
        arch,
        tuning_candidate,
        services['_PinValidationContext'](),
        historical_recipe_proofs=False,
    )


def _verify_output_reproduction_bundle(
    golden_records: Mapping[str, object],
    core_id: str,
    arch: str,
    validation_context: _PinValidationContext | None,
    *,
    historical_recipe_proofs: bool,
    services: StoredEvidenceServices,
) -> list[str]:
    """Deeply revalidate the independently stored generic E2E."""

    label = f"{core_id}/{arch} source-candidate reproduction"
    golden = golden_records.get(arch)
    if not isinstance(golden, dict):
        return [f"{label}: golden record is invalid"]
    try:
        proof = services['validated_output_reproduction_shape'](
            golden.get("output_reproduction"),
            core_id=core_id,
            golden_records=golden_records,
        )
    except services['PipelineError'] as exc:
        return [f"{label}: {exc}"]
    reproduction_side = proof["reproduction"]
    if validation_context is None:
        validation_context = services['_PinValidationContext']()
    errors: list[str] = []
    try:
        e2e_path = services['require_canonical_store_entry'](
            reproduction_side["e2e_record"],
            "e2e",
            f"{label} E2E record",
        )
        reproduction_e2e = services['verified_json_object'](
            e2e_path,
            reproduction_side["e2e_record"]["sha256"],
            f"{label} E2E record",
            validation_context,
        )
    except services['PipelineError'] as exc:
        return [str(exc)]
    builds = reproduction_e2e.get("builds")
    packages = reproduction_e2e.get("packages")
    expected_targets = set(golden_records)
    if (
        set(reproduction_e2e) != services['SOURCE_CANDIDATE_E2E_KEYS']
        or reproduction_e2e.get("result") != "passed"
        or reproduction_e2e.get("local_only") is not True
        or reproduction_e2e.get("publication") != "disabled"
        or reproduction_e2e.get("run_id") != reproduction_side["run_id"]
        or reproduction_e2e.get("content_sha256")
        != reproduction_side["content_sha256"]
        or reproduction_e2e.get("content_sha256")
        != services['e2e_content_sha256'](reproduction_e2e)
        or not isinstance(builds, list)
        or {item.get("architecture") for item in builds if isinstance(item, dict)}
        != expected_targets
        or len(builds) != len(expected_targets)
        or not isinstance(packages, list)
        or len(packages) != 1
        or packages[0].get("sha256")
        != golden.get("local_store", {}).get("package", {}).get("sha256")
    ):
        return [f"{label}: stored reproduction E2E binding is invalid"]

    reproduction_records: dict[str, dict] = {}
    for target in sorted(expected_targets):
        try:
            record_reference = reproduction_side["build_records"][target]
            record_path = services['require_canonical_store_entry'](
                record_reference,
                "build-records",
                f"{label} {target} build record",
            )
            record = services['verified_json_object'](
                record_path,
                record_reference["sha256"],
                f"{label} {target} build record",
                validation_context,
            )
        except services['PipelineError'] as exc:
            errors.append(str(exc))
            continue
        matching_entries = [
            item
            for item in builds
            if isinstance(item, dict) and item.get("architecture") == target
        ]
        if (
            len(matching_entries) != 1
            or matching_entries[0].get("record_sha256")
            != record_reference["sha256"]
            or set(record) != services['SOURCE_CANDIDATE_BUILD_RECORD_KEYS']
            or record.get("core_id") != core_id
            or record.get("architecture") != target
        ):
            errors.append(f"{label}: {target} reproduction record is invalid")
            continue
        selected_record = golden_records[target]
        assert isinstance(selected_record, services['Mapping'])
        for field in ("source", "recipe", "toolchain", "artifact", "metadata"):
            if record.get(field) != selected_record.get(field):
                errors.append(
                    f"{label}: {target} reproduction {field} differs"
                )
        if services['_build_equivalence_identity'](record.get("build")) != (
            services['_build_equivalence_identity'](selected_record.get("build"))
        ):
            errors.append(f"{label}: {target} reproduction build differs")
        reproduction_records[target] = record
    if errors or set(reproduction_records) != expected_targets:
        return errors

    local_store = golden.get("local_store", {})
    reproduction_record = reproduction_records[arch]
    pseudo = services['copy'].deepcopy(golden)
    pseudo.pop("output_reproduction", None)
    for field in ("source", "recipe", "toolchain", "build", "artifact", "metadata"):
        pseudo[field] = services['copy'].deepcopy(reproduction_record.get(field))
    pseudo["e2e"] = {
        "run_id": reproduction_e2e["run_id"],
        "record": reproduction_side["e2e_record"]["path"],
        "record_sha256": reproduction_side["e2e_record"]["sha256"],
        "content_sha256": reproduction_e2e["content_sha256"],
        "package": local_store["package"]["path"],
        "package_sha256": local_store["package"]["sha256"],
        "build_records": {
            target: reproduction_side["build_records"][target]["sha256"]
            for target in sorted(expected_targets)
        },
    }
    pseudo["local_store"] = {
        "availability": "local-only",
        "artifact": services['copy'].deepcopy(local_store["artifact"]),
        "metadata": services['copy'].deepcopy(local_store["metadata"]),
        "e2e_record": services['copy'].deepcopy(reproduction_side["e2e_record"]),
        "package": services['copy'].deepcopy(local_store["package"]),
        "build_records": services['copy'].deepcopy(reproduction_side["build_records"]),
        "build_logs": services['copy'].deepcopy(reproduction_side["build_logs"]),
        "recipe_snapshots": services['copy'].deepcopy(
            reproduction_side["recipe_snapshots"]
        ),
    }
    errors.extend(
        services['_verify_stored_e2e_bundle'](
            pseudo,
            core_id,
            arch,
            validation_context,
            historical_recipe_proofs=historical_recipe_proofs,
            verify_reproduction=False,
        )
    )
    output_identity = {
        "artifacts": {
            target: {
                "sha256": record["artifact"]["sha256"],
                "size": record["artifact"]["size"],
            }
            for target, record in sorted(reproduction_records.items())
        },
        "metadata": {
            "sha256": reproduction_record["metadata"]["sha256"],
            "size": reproduction_record["metadata"]["size"],
        },
        "package": {
            "name": packages[0].get("path"),
            "sha256": packages[0].get("sha256"),
            "size": packages[0].get("size"),
        },
    }
    if output_identity != proof["equivalent_outputs"]:
        errors.append(f"{label}: equivalent output identity is invalid")
    return errors


def verify_output_reproduction_bundle(
    golden_records: Mapping[str, object],
    core_id: str,
    arch: str,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    """Verify output reproduction with a fresh, ordinary proof context."""

    return services['_verify_output_reproduction_bundle'](
        golden_records,
        core_id,
        arch,
        services['_PinValidationContext'](),
        historical_recipe_proofs=False,
    )


def _verify_host_reproduction_bundle(
    golden_records: Mapping[str, object],
    core_id: str,
    validation_context: _PinValidationContext | None,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    """Revalidate both hardened E2Es entirely through immutable CAS refs."""

    label = f"{core_id} host reproduction"
    if not golden_records:
        return [f"{label}: build-golden records are missing"]
    first = golden_records[sorted(golden_records)[0]]
    if not isinstance(first, services['Mapping']):
        return [f"{label}: first golden record is invalid"]
    try:
        proof = services['validated_host_reproduction_shape'](
            first.get("host_reproduction"),
            core_id=core_id,
            golden_records=golden_records,
        )
    except services['PipelineError'] as exc:
        return [f"{label}: {exc}"]
    if validation_context is None:
        validation_context = services['_PinValidationContext']()

    loaded: dict[str, dict] = {}
    telemetry_by_side: dict[str, dict] = {}
    errors: list[str] = []
    for side_name in ("selected", "reproduction"):
        side = proof[side_name]
        try:
            e2e_path = services['require_canonical_store_entry'](
                side["e2e_record"],
                "e2e",
                f"{label} {side_name} E2E",
            )
            evidence = services['verified_json_object'](
                e2e_path,
                side["e2e_record"]["sha256"],
                f"{label} {side_name} E2E",
                validation_context,
            )
            if (
                evidence.get("schema_version") != 2
                or evidence.get("run_id") != side["run_id"]
                or evidence.get("content_sha256") != side["content_sha256"]
                or evidence.get("content_sha256")
                != services['e2e_content_sha256'](evidence)
                or evidence.get("result") != "passed"
                or evidence.get("local_only") is not True
                or evidence.get("publication") != "disabled"
                or not services['runner_evidence_is_hardened'](evidence.get("runner"))
                or "core_group" in evidence
            ):
                raise services['PipelineError'](
                    f"{label} {side_name} E2E identity is invalid"
                )
            telemetry = services['validate_bound_host_telemetry'](evidence, e2e_path)
            if not isinstance(telemetry, dict):
                raise services['PipelineError'](
                    f"{label} {side_name} telemetry is not hardened"
                )
        except services['PipelineError'] as exc:
            errors.append(str(exc))
            continue
        loaded[side_name] = evidence
        telemetry_by_side[side_name] = telemetry
    if errors or set(loaded) != {"selected", "reproduction"}:
        return errors
    try:
        services['require_selected_reproduction_runner_pair'](
            loaded["selected"], loaded["reproduction"]
        )
    except services['PipelineError'] as exc:
        return [f"{label}: {exc}"]
    if loaded["selected"]["run_id"] == loaded["reproduction"]["run_id"]:
        return [f"{label}: E2E runs are not independent"]

    expected_targets = set(golden_records)
    records_by_side: dict[str, dict[str, dict]] = {}
    record_refs_by_side: dict[str, dict[str, dict]] = {}
    packages_by_side: dict[str, dict] = {}
    for side_name in ("selected", "reproduction"):
        evidence = loaded[side_name]
        telemetry = telemetry_by_side[side_name]
        builds = evidence.get("builds")
        packages = evidence.get("packages")
        telemetry_builds = telemetry.get("builds")
        if (
            not isinstance(builds, list)
            or len(builds) != len(expected_targets)
            or {
                item.get("architecture")
                for item in builds
                if isinstance(item, services['Mapping'])
                and item.get("core_id") == core_id
                and item.get("result") == "passed"
            }
            != expected_targets
            or not isinstance(packages, list)
            or len(packages) != 1
            or not isinstance(packages[0], dict)
            or packages[0].get("core_id") != core_id
            or packages[0].get("result") != "packaged"
            or not isinstance(telemetry_builds, list)
        ):
            errors.append(f"{label}: {side_name} E2E scope is invalid")
            continue
        packages_by_side[side_name] = packages[0]
        telemetry_index = {
            item.get("architecture"): item
            for item in telemetry_builds
            if isinstance(item, services['Mapping']) and item.get("core_id") == core_id
        }
        build_index = {
            item.get("architecture"): item
            for item in builds
            if isinstance(item, services['Mapping']) and item.get("core_id") == core_id
        }
        if set(telemetry_index) != expected_targets or set(build_index) != expected_targets:
            errors.append(f"{label}: {side_name} target scope is invalid")
            continue
        side_records: dict[str, dict] = {}
        side_refs: dict[str, dict] = {}
        for arch in sorted(expected_targets):
            telemetry_build = telemetry_index[arch]
            reference = telemetry_build.get("bindings", {}).get("build_record")
            stored_reference = {
                "path": reference.get("path")
                if isinstance(reference, services['Mapping'])
                else None,
                "sha256": reference.get("file_sha256")
                if isinstance(reference, services['Mapping'])
                else None,
            }
            try:
                record_path = services['require_canonical_store_entry'](
                    stored_reference,
                    "build-records",
                    f"{label} {side_name} {arch} build record",
                )
                record = services['verified_json_object'](
                    record_path,
                    stored_reference["sha256"],
                    f"{label} {side_name} {arch} build record",
                    validation_context,
                )
            except services['PipelineError'] as exc:
                errors.append(str(exc))
                continue
            if (
                build_index[arch].get("record_sha256")
                != stored_reference["sha256"]
                or record.get("core_id") != core_id
                or record.get("architecture") != arch
                or record.get("result") != "passed"
                or record.get("build_exit_code") != 0
            ):
                errors.append(
                    f"{label}: {side_name} {arch} build record is invalid"
                )
                continue
            side_records[arch] = record
            side_refs[arch] = stored_reference
        records_by_side[side_name] = side_records
        record_refs_by_side[side_name] = side_refs
    if errors or any(
        set(records_by_side.get(side, {})) != expected_targets
        for side in ("selected", "reproduction")
    ):
        return errors

    selected_records = records_by_side["selected"]
    reproduction_records = records_by_side["reproduction"]
    for arch in sorted(expected_targets):
        golden = golden_records[arch]
        assert isinstance(golden, services['Mapping'])
        local_store = golden.get("local_store")
        if (
            not isinstance(local_store, services['Mapping'])
            or local_store.get("build_records", {}).get(arch)
            != record_refs_by_side["selected"][arch]
            or services['host_reproduction_build_identity'](selected_records[arch])
            != services['host_reproduction_build_identity'](golden)
            or services['host_reproduction_build_identity'](selected_records[arch])
            != services['host_reproduction_build_identity'](reproduction_records[arch])
        ):
            errors.append(
                f"{label}: {arch} selected/reproduction/golden build differs"
            )
    if errors:
        return errors
    selected_outputs = services['host_reproduction_output_identity'](
        selected_records, packages_by_side["selected"]
    )
    reproduction_outputs = services['host_reproduction_output_identity'](
        reproduction_records, packages_by_side["reproduction"]
    )
    if (
        selected_outputs != reproduction_outputs
        or selected_outputs != proof["equivalent_outputs"]
        or proof["equivalent_builds"]
        != {
            arch: services['host_reproduction_build_content_sha256'](record)
            for arch, record in sorted(selected_records.items())
        }
    ):
        errors.append(f"{label}: equivalent build/output identity is invalid")
    return errors


def verify_host_reproduction_bundle(
    golden_records: Mapping[str, object], core_id: str,
    *,
    services: StoredEvidenceServices,
) -> list[str]:
    return services['_verify_host_reproduction_bundle'](
        golden_records, core_id, services['_PinValidationContext']()
    )


def _verify_local_store(
    document: dict,
    _validation_context: _PinValidationContext | None = None,
    *,
    historical_recipe_proofs: bool = False,
    services: StoredEvidenceServices,
) -> list[str]:
    if _validation_context is None:
        _validation_context = services['_PinValidationContext']()
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["golden document must be an object"]
    build_goldens = document.get("build_goldens")
    if not isinstance(build_goldens, dict):
        return ["build_goldens must be an object"]
    for core_id, targets in build_goldens.items():
        if not isinstance(targets, dict):
            errors.append(f"{core_id}: build-golden targets must be an object")
            continue
        for arch, golden in targets.items():
            if not isinstance(golden, dict):
                errors.append(f"{core_id}/{arch}: build golden must be an object")
                continue
            local_store = golden.get("local_store")
            if not isinstance(local_store, dict):
                errors.append(f"{core_id}/{arch}: local store record must be an object")
                continue
            entries: list[tuple[str, dict]] = [
                (name, local_store.get(name, {}))
                for name in services['STORE_SINGLE_EVIDENCE_NAMES']
            ]
            for group_name in services['STORE_TARGET_EVIDENCE_NAMES']:
                group = local_store.get(group_name)
                if not isinstance(group, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {group_name} must be an object"
                    )
                    continue
                entries.extend(
                    (f"{group_name}/{target}", stored)
                    for target, stored in group.items()
                )
            all_files_valid = True
            for stored_name, stored in entries:
                if not isinstance(stored, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} record must be an object"
                    )
                    all_files_valid = False
                    continue
                raw_path = stored.get("path")
                expected = stored.get("sha256")
                if (
                    not isinstance(raw_path, str)
                    or not raw_path
                    or not isinstance(expected, str)
                    or services['SHA256_RE'].fullmatch(expected) is None
                ):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} identity is invalid"
                    )
                    all_files_valid = False
                    continue
                try:
                    path = services['safe_child'](
                        services['ROOT'],
                        raw_path,
                        f"{core_id}/{arch} local {stored_name} path",
                    )
                except services['PipelineError'] as exc:
                    errors.append(str(exc))
                    all_files_valid = False
                    continue
                try:
                    services['verified_file_bytes'](
                        path,
                        expected,
                        f"{core_id}/{arch}: local {stored_name}",
                        _validation_context,
                    )
                except services['PipelineError'] as exc:
                    errors.append(str(exc))
                    all_files_valid = False
            if all_files_valid:
                errors.extend(
                    services['_verify_stored_e2e_bundle'](
                        golden,
                        core_id,
                        arch,
                        _validation_context,
                        historical_recipe_proofs=historical_recipe_proofs,
                    )
                )
                if "output_reproduction" in golden:
                    errors.extend(
                        services['_verify_output_reproduction_bundle'](
                            targets,
                            core_id,
                            arch,
                            _validation_context,
                            historical_recipe_proofs=historical_recipe_proofs,
                        )
                    )
                if "host_reproduction" in golden and arch == sorted(targets)[0]:
                    errors.extend(
                        services['_verify_host_reproduction_bundle'](
                            targets,
                            core_id,
                            _validation_context,
                        )
                    )
    return errors


def verify_local_store(document: dict, *, services: StoredEvidenceServices) -> list[str]:
    """Verify one local store with a fresh, ordinary proof context."""

    return services['_verify_local_store'](document, services['_PinValidationContext']())


def golden_source_reference(
    path: Path,
    document: dict,
    *,
    file_sha256: str | None = None,
    services: StoredEvidenceServices,
) -> dict:
    path = services['require_contained'](path, services['ROOT'], "golden source")
    return {
        "path": str(path.relative_to(services['ROOT'])),
        "file_sha256": file_sha256 or services['sha256_file'](path),
        "content_sha256": document["content_sha256"],
        "pin_id": document["pin_id"],
    }


def complete_core_bundle(golden: dict, core_id: str, *, services: StoredEvidenceServices) -> dict | None:
    build_goldens = golden.get("build_goldens")
    if not isinstance(build_goldens, dict):
        raise services['PipelineError']("golden build_goldens must be an object")
    records = build_goldens.get(core_id, {})
    if not isinstance(records, dict):
        raise services['PipelineError'](f"{core_id}: build-golden targets must be an object")
    if not records:
        return None
    e2e_by_arch: dict[str, dict] = {}
    target_sets: set[frozenset[str]] = set()
    for arch, record in records.items():
        if arch not in services['ARCH_LAYOUT'] or not isinstance(record, dict):
            raise services['PipelineError'](
                f"{core_id}/{arch}: build golden must be an object for a known target"
            )
        e2e = record.get("e2e")
        if not isinstance(e2e, dict):
            raise services['PipelineError'](f"{core_id}/{arch}: build-golden E2E must be an object")
        build_records = e2e.get("build_records")
        if (
            not isinstance(build_records, dict)
            or not build_records
            or any(target not in services['ARCH_LAYOUT'] for target in build_records)
        ):
            raise services['PipelineError'](
                f"{core_id}/{arch}: build-golden E2E target set is invalid"
            )
        e2e_by_arch[arch] = e2e
        target_sets.add(frozenset(build_records))
    if len(target_sets) != 1:
        raise services['PipelineError'](f"{core_id}: build goldens disagree on their E2E target set")
    expected_targets = set(next(iter(target_sets)))
    if set(records) != expected_targets:
        return None

    ordered = [records[target] for target in sorted(expected_targets)]
    first = ordered[0]
    first_e2e = e2e_by_arch[sorted(expected_targets)[0]]
    first_metadata = first.get("metadata")
    shared_source = first.get("source")
    shared_recipe = first.get("recipe")
    first_local_store = first.get("local_store")
    shared_tuning_candidate = first.get("tuning_candidate")
    shared_reproduction = first.get("reproduction")
    shared_source_candidate = first.get("source_candidate")
    shared_output_reproduction = first.get("output_reproduction")
    shared_host_reproduction = first.get("host_reproduction")
    if (
        not isinstance(first_metadata, dict)
        or not isinstance(shared_source, dict)
        or not isinstance(shared_recipe, dict)
        or not isinstance(first_local_store, dict)
        or not isinstance(first_local_store.get("package"), dict)
    ):
        raise services['PipelineError'](f"{core_id}: build-golden bundle fields are invalid")
    shared_e2e = {
        "run_id": first_e2e.get("run_id"),
        "content_sha256": first_e2e.get("content_sha256"),
        "package_sha256": first_e2e.get("package_sha256"),
        "build_records": first_e2e.get("build_records"),
    }
    shared_metadata_sha = first_metadata.get("sha256")
    shared_package_store = first_local_store["package"]
    for arch, record in zip(sorted(expected_targets), ordered, strict=True):
        metadata = record.get("metadata")
        source = record.get("source")
        recipe = record.get("recipe")
        local_store = record.get("local_store")
        if (
            not isinstance(metadata, dict)
            or not isinstance(source, dict)
            or not isinstance(recipe, dict)
            or not isinstance(local_store, dict)
            or not isinstance(local_store.get("package"), dict)
        ):
            raise services['PipelineError'](f"{core_id}/{arch}: build-golden fields are invalid")
        e2e = e2e_by_arch[arch]
        current_e2e = {
            "run_id": e2e.get("run_id"),
            "content_sha256": e2e.get("content_sha256"),
            "package_sha256": e2e.get("package_sha256"),
            "build_records": e2e.get("build_records"),
        }
        if (
            record.get("core_id") != core_id
            or record.get("promotion_state") != "build_golden"
            or record.get("validation_scope") != "static-build-only"
            or current_e2e != shared_e2e
            or metadata.get("sha256") != shared_metadata_sha
            or source != shared_source
            or recipe != shared_recipe
            or local_store.get("package") != shared_package_store
            or record.get("tuning_candidate") != shared_tuning_candidate
            or record.get("reproduction") != shared_reproduction
            or record.get("source_candidate") != shared_source_candidate
            or record.get("output_reproduction")
            != shared_output_reproduction
            or record.get("host_reproduction")
            != shared_host_reproduction
        ):
            raise services['PipelineError'](f"{core_id}: build goldens are not one coherent package")
        record_build = record.get("build", {})
        record_metadata_replacement = (
            record_build.get("metadata_replacement")
            if isinstance(record_build, dict)
            else None
        )
        if record_metadata_replacement is not None and not (
            services['metadata_matches_replacement'](
                record.get("metadata"), record_metadata_replacement
            )
        ):
            raise services['PipelineError'](
                f"{core_id}: metadata does not match its replacement"
            )

    tuned_recipe = shared_recipe.get("chipset_tuning")
    if shared_tuning_candidate is not None or shared_reproduction is not None:
        if (
            shared_source_candidate is not None
            or shared_output_reproduction is not None
        ):
            raise services['PipelineError'](
                f"{core_id}: tuned and source-candidate bundles are mutually exclusive"
            )
        tuning_candidate = services['validated_tuning_candidate_shape'](shared_tuning_candidate)
        if (
            len(expected_targets) != 1
            or next(iter(expected_targets))
            != tuning_candidate["profile"]["architecture"]
            or tuned_recipe != services['tuning_candidate_recipe_identity'](tuning_candidate)
            or not isinstance(shared_reproduction, services['Mapping'])
        ):
            raise services['PipelineError'](f"{core_id}: tuned build-golden bundle is incoherent")
        services['validated_tuned_reproduction_shape'](
            shared_reproduction,
            core_id=core_id,
            arch=next(iter(expected_targets)),
            golden_record=first,
        )
    elif shared_source_candidate is not None or shared_output_reproduction is not None:
        if tuned_recipe is not None:
            raise services['PipelineError'](f"{core_id}: source-candidate bundle is tuned")
        source_candidate = services['validated_embedded_source_candidate_shape'](
            shared_source_candidate,
            core_id=core_id,
        )
        services['validated_output_reproduction_shape'](
            shared_output_reproduction,
            core_id=core_id,
            golden_records=records,
        )
        candidate_selection = source_candidate["selection"]
        if any(
            shared_source.get(record_key) != candidate_selection.get(selection_key)
            for record_key, selection_key in (
                ("url", "url"),
                ("requested_ref", "requested_ref"),
                ("commit", "commit"),
                ("resolved_commit", "commit"),
                ("tree", "tree"),
            )
        ):
            raise services['PipelineError'](
                f"{core_id}: source-candidate bundle source is incoherent"
            )
    elif tuned_recipe is not None:
        raise services['PipelineError'](f"{core_id}: build-golden tuning lacks candidate evidence")
    if shared_host_reproduction is not None:
        services['validated_host_reproduction_shape'](
            shared_host_reproduction,
            core_id=core_id,
            golden_records=records,
        )

    package_path = services['require_canonical_store_entry'](
        shared_package_store, "packages", f"{core_id} package"
    )
    if (
        not package_path.is_file()
        or services['sha256_file'](package_path) != shared_e2e.get("package_sha256")
    ):
        raise services['PipelineError'](f"{core_id}: package is missing from the local store")
    metadata_store = first_local_store.get("metadata")
    if not isinstance(metadata_store, dict):
        raise services['PipelineError'](f"{core_id}: metadata store record is invalid")
    metadata_path = services['require_canonical_store_entry'](
        metadata_store, "metadata", f"{core_id} metadata"
    )
    if (
        not metadata_path.is_file()
        or metadata_path.stat().st_size != first_metadata.get("size")
        or services['sha256_file'](metadata_path) != shared_metadata_sha
    ):
        raise services['PipelineError'](f"{core_id}: metadata is missing from the local store")

    targets = {}
    for arch in sorted(expected_targets):
        record = records[arch]
        artifact = record.get("artifact")
        local_store = record.get("local_store")
        artifact_store = (
            local_store.get("artifact") if isinstance(local_store, dict) else None
        )
        if not isinstance(artifact, dict) or not isinstance(artifact_store, dict):
            raise services['PipelineError'](f"{core_id}/{arch}: artifact records are invalid")
        artifact_path = services['require_canonical_store_entry'](
            artifact_store, "artifacts", f"{core_id}/{arch} artifact"
        )
        if (
            artifact.get("status") != "valid"
            or artifact_store.get("sha256") != artifact.get("sha256")
            or not artifact_path.is_file()
            or artifact_path.stat().st_size != artifact.get("size")
            or services['sha256_file'](artifact_path) != artifact.get("sha256")
        ):
            raise services['PipelineError'](f"{core_id}/{arch}: artifact store identity is invalid")
        targets[arch] = {
            "artifact": {
                "path": artifact_store["path"],
                "sha256": artifact["sha256"],
                "size": artifact["size"],
            },
            "build_record_sha256": shared_e2e["build_records"][arch],
            "provenance_identity_sha256": services['provenance_identity_sha256'](record),
            "golden_record": services['copy'].deepcopy(record),
        }

    selection = {
        "tier": "build_golden",
        "validation_scope": "static-build-only",
        "e2e": shared_e2e,
        "package": {
            "name": f"{core_id}_libretro.zip",
            "path": shared_package_store["path"],
            "sha256": shared_e2e["package_sha256"],
            "size": package_path.stat().st_size,
        },
        "metadata": {
            "path": metadata_store["path"],
            "sha256": shared_metadata_sha,
            "size": metadata_path.stat().st_size,
        },
        "targets": targets,
    }
    if shared_tuning_candidate is not None:
        selection["chipset_tuning"] = services['copy'].deepcopy(shared_tuning_candidate)
        selection["reproduction"] = services['copy'].deepcopy(shared_reproduction)
    if shared_source_candidate is not None:
        selection["source_candidate"] = services['copy'].deepcopy(shared_source_candidate)
        selection["output_reproduction"] = services['copy'].deepcopy(
            shared_output_reproduction
        )
    if shared_host_reproduction is not None:
        selection["host_reproduction"] = services['copy'].deepcopy(
            shared_host_reproduction
        )
    selection["selection_sha256"] = services['selection_content_sha256'](selection)
    return selection
