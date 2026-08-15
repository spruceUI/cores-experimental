"""Pin identity, source authority, compatibility, and composition lifecycle.

The launcher remains the composition root. Global dependencies are captured in
a filtered call-time service record so legacy wrappers and monkeypatch seams
remain dynamic without introducing a reverse import.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol


class _PinValidationContext(Protocol):
    """Read-once evidence caches supplied by the launcher composition root."""

    log_proofs: dict[tuple[str, str, str, str], tuple[bool, ...]]
    pinned_packages: set[tuple[str, str, str, str, int]]
    verified_bytes: dict[tuple[str, str], bytes]


_MODULE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = _MODULE_ROOT / "manifests" / "core-builds.json"
DEFAULT_STORE = _MODULE_ROOT / ".local-e2e" / "store"


@dataclass(frozen=True, slots=True)
class PinLifecycleServices:
    """Call-time namespace required by this lifecycle domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "PinLifecycleServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(
                f"missing lifecycle services: {names}"
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
        'CORE_ID_RE',
        'DEFAULT_CATALOG',
        'DEFAULT_CHIPSET_TUNINGS',
        'DEFAULT_CORE_TRACKS',
        'DEFAULT_CORE_TRACK_SOURCE_REPOSITORIES',
        'DEFAULT_NIGHTLIES',
        'DEFAULT_PIN_SET_DIR',
        'DEFAULT_RELEASES',
        'DEFAULT_RUNS',
        'DEFAULT_SPRUCE_BRANCH_BASES',
        'DEFAULT_SPRUCE_RELEASE_ROSTER',
        'FBNEO_CORE_ID',
        'LOCAL_ID_RE',
        'MAME2003_PLUS_CORE_ID',
        'MAX_PIN_PARENT_DEPTH',
        'Mapping',
        'PICODRIVE_CORE_ID',
        'PIN_SELECTION_POLICY',
        'Path',
        'PipelineError',
        'ROOT',
        'SHA1_RE',
        'SHA256_RE',
        'SourceCandidateContractProjection',
        '_PinValidationContext',
        '__file__',
        '_authoritative_core_track_pin_report',
        '_build_equivalence_identity',
        '_recorded_source_matches_source_candidate_projection',
        '_registered_core_log_contract_proves',
        '_require_catalog_bound_source_candidate_selection',
        '_require_current_selection_source_authority',
        '_require_pin_current_selection_authority',
        '_source_candidate_contract_build_for_guard',
        '_source_candidate_contract_source_for_guard',
        '_validate_artifact_bytes',
        '_validate_canonical_compatibility_build_record',
        '_validate_compatibility_e2e_run',
        '_validate_core_compatibility_document',
        '_validate_historical_pin_set_document',
        '_validate_pin_set_document',
        '_validate_pin_set_document_impl',
        '_verify_historical_recipe_snapshot',
        '_verify_local_store',
        '_verify_pinned_package',
        'atomic_create_json',
        'compile_log_proves_definitions',
        'complete_core_bundle',
        'construct_core_track_inventory',
        'copy',
        'core_log_contract_for',
        'core_spec_sha256',
        'core_track_source_ancestry_verifier',
        'decode_json_object',
        'direct_cmake_log_proves_contract',
        'e2e_content_sha256',
        'fbneo_golden_build_contract_is_well_formed',
        'fbneo_golden_source_is_well_formed',
        'git_version_log_proves_contract',
        'golden_content_sha256',
        'golden_source_reference',
        'individual_core_semantic_id',
        'inspect_individual_core_golden',
        'io',
        'json',
        'load_authoritative_core_pin_index',
        'load_catalog',
        'load_catalog_with_sha256',
        'load_core_pin_index',
        'load_core_track_source_registry_index',
        'load_json',
        'load_json_with_sha256',
        'local_git_source_ancestry_verifier',
        'make_variable_log_proves_contract',
        'mame2003_plus_golden_build_contract_is_well_formed',
        'mame2003_plus_golden_source_is_well_formed',
        'metadata_matches_replacement',
        'metadata_replacement_log_proves_contract',
        'one_core_golden_document',
        'parse_group_tag',
        'picodrive_golden_build_contract_is_well_formed',
        'pin_set_content_sha256',
        'pinned_group_execution_source',
        'pipeline_source_bundle_is_well_formed',
        'prepare_release_source_graph',
        'provenance_identity_sha256',
        'release_source_graph_requirements',
        'require_active_candidate_golden_path',
        'require_active_core_golden',
        'require_canonical_store_entry',
        'require_contained',
        'require_host_execution_runner_coupling',
        'require_individual_pin_identity',
        'require_lexical_repository_path',
        'require_manifest_reference_path',
        'require_pin_sources_eligible',
        'runner_evidence_is_well_formed',
        'safe_child',
        'selection_content_sha256',
        'sha256_bytes',
        'sha256_file',
        'snapshot_json_file',
        'source_candidate_record_contract_projection',
        'store_bytes',
        'tuning_candidate_recipe_identity',
        'validate_bound_host_telemetry',
        'validate_core_e2e_run',
        'validate_core_tracks',
        'validate_golden_document',
        'validated_embedded_source_candidate_shape',
        'validated_host_reproduction_shape',
        'validated_output_reproduction_shape',
        'validated_tuned_reproduction_shape',
        'validated_tuning_candidate_shape',
        'verified_file_bytes',
        'verified_json_object',
        'verify_local_store',
        'zipfile',
    }
)


def individual_core_semantic_id(core_id: str, selection: dict, *, services: PinLifecycleServices) -> str:
    """Derive the canonical ID shared by one core's nightly, pin, and release."""

    if not isinstance(core_id, str) or services['CORE_ID_RE'].fullmatch(core_id) is None:
        raise services['PipelineError']("individual core semantic identity has an invalid core ID")
    targets = selection.get("targets") if isinstance(selection, dict) else None
    if not isinstance(targets, dict) or not targets:
        raise services['PipelineError']("individual core semantic identity has no targets")
    source_commits: set[str] = set()
    for target in targets.values():
        if not isinstance(target, dict):
            raise services['PipelineError'](
                "individual core semantic identity has an invalid target"
            )
        golden_record = target.get("golden_record")
        source = (
            golden_record.get("source")
            if isinstance(golden_record, dict)
            else None
        )
        if not isinstance(source, dict):
            raise services['PipelineError'](
                "individual core semantic identity has an invalid source"
            )
        source_commit = source.get("commit")
        if not isinstance(source_commit, str) or services['SHA1_RE'].fullmatch(source_commit) is None:
            raise services['PipelineError']("individual core semantic identity is invalid")
        source_commits.add(source_commit)
    source_commit = next(iter(source_commits), None)
    selection_sha256 = selection.get("selection_sha256")
    if (
        len(source_commits) != 1
        or not isinstance(selection_sha256, str)
        or services['SHA256_RE'].fullmatch(selection_sha256) is None
    ):
        raise services['PipelineError']("individual core semantic identity is invalid")
    return f"{core_id}-{source_commit[:12]}-{selection_sha256[:12]}"


def require_individual_pin_identity(
    pin: dict,
    *,
    pin_path: Path | None = None,
    services: PinLifecycleServices,
) -> tuple[str, str]:
    """Require the canonical parentless one-core pin used by active mutators."""

    scope = pin.get("scope")
    cores = pin.get("cores")
    sources = pin.get("sources")
    if (
        not isinstance(scope, list)
        or len(scope) != 1
        or not isinstance(scope[0], str)
        or not isinstance(cores, dict)
        or set(cores) != {scope[0]}
        or pin.get("parent") is not None
        or not isinstance(sources, list)
        or len(sources) != 1
    ):
        raise services['PipelineError'](
            "active pin mutation requires one parentless core and one source"
        )
    core_id = scope[0]
    core_record = cores.get(core_id)
    if (
        not isinstance(core_record, dict)
        or core_record.get("decision") != "select_source"
        or core_record.get("source_index") != 0
        or not isinstance(core_record.get("selection"), dict)
    ):
        raise services['PipelineError']("active pin mutation requires one direct core selection")
    semantic_id = services['individual_core_semantic_id'](
        core_id,
        core_record["selection"],
    )
    if pin.get("pin_id") != semantic_id:
        raise services['PipelineError'](
            f"individual pin ID must be semantic ID {semantic_id}"
        )
    source_reference = sources[0]
    expected_source_path = f".local-e2e/nightlies/{semantic_id}/golden.json"
    if (
        not isinstance(source_reference, dict)
        or source_reference.get("path") != expected_source_path
    ):
        raise services['PipelineError'](
            "individual pin source must be its exact semantic nightly golden"
        )
    if pin_path is not None:
        canonical_pin_path = services['require_lexical_repository_path'](
            pin_path,
            services['DEFAULT_PIN_SET_DIR'],
            "individual pin",
        )
        expected_pin_path = (services['DEFAULT_PIN_SET_DIR'] / f"{semantic_id}.json").resolve()
        if canonical_pin_path != expected_pin_path:
            raise services['PipelineError'](
                f"individual pin path must be pins/core-sets/{semantic_id}.json"
            )
    return core_id, semantic_id


def _require_current_selection_source_authority(
    catalog: Mapping[str, object],
    selection: Mapping[str, object],
    *,
    core_id: str,
    operation: str,
    services: PinLifecycleServices,
) -> None:
    """Bind a deeply validated persisted selection to today's core source."""

    cores = catalog.get("cores")
    canonical_spec = cores.get(core_id) if isinstance(cores, services['Mapping']) else None
    canonical_source = (
        canonical_spec.get("source")
        if isinstance(canonical_spec, services['Mapping'])
        else None
    )
    targets = selection.get("targets")
    if (
        not isinstance(canonical_spec, services['Mapping'])
        or not isinstance(canonical_source, services['Mapping'])
        or not isinstance(targets, services['Mapping'])
        or not targets
    ):
        raise services['PipelineError'](
            f"{operation} selection lacks canonical source authority"
        )

    has_candidate = "source_candidate" in selection
    has_reproduction = "output_reproduction" in selection
    if has_candidate != has_reproduction:
        raise services['PipelineError'](
            f"{operation} source-candidate selection is incomplete"
        )
    candidate_projection: services['SourceCandidateContractProjection'] | None = None
    if has_candidate:
        embedded = services['validated_embedded_source_candidate_shape'](
            selection["source_candidate"],
            core_id=core_id,
        )
        candidate = embedded["selection"]
        if (
            embedded["base_catalog"].get("core_spec_sha256")
            != services['core_spec_sha256'](canonical_spec)
            or candidate.get("url") != canonical_source.get("url")
            or candidate.get("requested_ref")
            != canonical_source.get("requested_ref")
            or candidate.get("catalog_commit") != canonical_source.get("commit")
            or candidate.get("catalog_tree") != canonical_source.get("tree")
        ):
            raise services['PipelineError'](
                f"{operation} source-candidate baseline differs from the "
                "canonical core"
            )
        candidate_projection = services['SourceCandidateContractProjection'](
            core_id=core_id,
            candidate_id=embedded["candidate_id"],
            canonical_commit=candidate["catalog_commit"],
            canonical_tree=candidate["catalog_tree"],
            candidate_commit=candidate["commit"],
            candidate_tree=candidate["tree"],
            canonical_spec_sha256=embedded["base_catalog"][
                "core_spec_sha256"
            ],
            execution_spec_sha256=embedded["execution"]["core_spec_sha256"],
            source_url=candidate["url"],
            requested_ref=candidate["requested_ref"],
            candidate_submodules=tuple(
                (item["path"], item["commit"])
                for item in candidate["top_level_gitlinks"]
            ),
        )

    for arch, target in sorted(targets.items()):
        golden = target.get("golden_record") if isinstance(target, services['Mapping']) else None
        source = golden.get("source") if isinstance(golden, services['Mapping']) else None
        if candidate_projection is not None:
            if not services['_recorded_source_matches_source_candidate_projection'](
                source,
                candidate_projection,
            ):
                raise services['PipelineError'](
                    f"{operation} {core_id}/{arch} source differs from the "
                    "authenticated candidate"
                )
            continue
        try:
            source_projection = services['pinned_group_execution_source'](
                source,
                label=f"{core_id}/{arch} ordinary selection",
            )
        except services['PipelineError'] as exc:
            raise services['PipelineError'](f"{operation}: {exc}") from exc
        if any(
            source_projection.get(key) != canonical_source.get(key)
            for key in ("url", "requested_ref", "commit", "tree")
        ) or (
            "submodules" in canonical_source
            and source_projection.get("submodules")
            != canonical_source.get("submodules")
        ):
            raise services['PipelineError'](
                f"{operation} ordinary selection source differs from the "
                "canonical core"
            )


def _require_catalog_bound_source_candidate_selection(
    catalog: Mapping[str, object],
    selection: Mapping[str, object],
    *,
    core_id: str,
    operation: str,
    catalog_path: Path,
    services: PinLifecycleServices,
) -> None:
    """Require candidate provenance in both the catalog and projected bundle."""

    catalog_has_candidate = "source_candidate" in catalog
    selection_has_candidate = (
        "source_candidate" in selection or "output_reproduction" in selection
    )
    if catalog_has_candidate != selection_has_candidate:
        raise services['PipelineError'](
            f"{operation} requires source-candidate provenance in both the "
            "authenticated catalog and dual-E2E bundle"
        )
    if not catalog_has_candidate:
        if catalog_path.resolve() != services['DEFAULT_CATALOG'].resolve():
            raise services['PipelineError'](
                f"{operation} ordinary selection requires the exact canonical "
                "catalog path"
            )
        canonical_catalog = services['load_catalog'](services['DEFAULT_CATALOG'])
        if catalog != canonical_catalog:
            raise services['PipelineError'](
                f"{operation} ordinary selection catalog differs from the "
                "canonical bytes"
            )
        services['_require_current_selection_source_authority'](
            canonical_catalog,
            selection,
            core_id=core_id,
            operation=operation,
        )
        return
    expected_source_candidate = services['validated_embedded_source_candidate_shape'](
        catalog["source_candidate"],
        core_id=core_id,
    )
    if (
        selection.get("source_candidate") != expected_source_candidate
        or "output_reproduction" not in selection
    ):
        raise services['PipelineError'](
            f"{operation} requires the exact source-candidate dual-E2E bundle"
        )


def inspect_individual_core_golden(
    core_id: str,
    source_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    *,
    services: PinLifecycleServices,
) -> tuple[dict, dict, str, Path]:
    """Read and identify a complete working golden owned by one core."""

    catalog = services['load_catalog'](catalog_path)
    if core_id not in catalog["cores"]:
        raise services['PipelineError'](f"individual golden core is not cataloged: {core_id}")
    source_path = services['require_lexical_repository_path'](
        source_path,
        services['ROOT'],
        "core golden source",
    )
    if not source_path.is_file() or source_path.is_symlink():
        raise services['PipelineError']("core golden source must be a regular file")
    source, _source_file_sha256 = services['snapshot_json_file'](
        source_path,
        "core golden source",
    )
    source_report = services['validate_golden_document'](source)
    if source_report["status"] != "valid":
        raise services['PipelineError'](
            "cannot project an invalid golden source:\n- "
            + "\n- ".join(source_report["errors"])
        )
    services['require_active_core_golden'](source, core_id)
    services['require_active_candidate_golden_path'](source_path, source)
    store_errors = services['verify_local_store'](source)
    if store_errors:
        raise services['PipelineError'](
            "individual core golden source store is invalid:\n- "
            + "\n- ".join(store_errors)
        )
    build_goldens = source.get("build_goldens")
    if not isinstance(build_goldens, dict) or set(build_goldens) != {core_id}:
        raise services['PipelineError'](
            "individual core golden source must contain build evidence for exactly its core"
        )
    selection = services['complete_core_bundle'](source, core_id)
    if selection is None:
        raise services['PipelineError'](f"core golden source has no complete {core_id} bundle")
    services['_require_catalog_bound_source_candidate_selection'](
        catalog,
        selection,
        core_id=core_id,
        operation="individual golden projection",
        catalog_path=catalog_path,
    )
    semantic_id = services['individual_core_semantic_id'](core_id, selection)
    return source, selection, semantic_id, source_path


def derive_core_id(
    *,
    core_id: str,
    source_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    services: PinLifecycleServices,
) -> dict:
    """Return canonical individual lifecycle paths without mutating the tree."""

    _source, _selection, semantic_id, source_path = services['inspect_individual_core_golden'](
        core_id,
        source_path,
        catalog_path,
    )
    return {
        "status": "valid",
        "core_id": core_id,
        "semantic_id": semantic_id,
        "source_golden": str(source_path.relative_to(services['ROOT'])),
        "nightly_golden": str(
            (services['DEFAULT_NIGHTLIES'] / semantic_id / "golden.json").relative_to(services['ROOT'])
        ),
        "pin_set": str((services['DEFAULT_PIN_SET_DIR'] / f"{semantic_id}.json").relative_to(services['ROOT'])),
        "release": str((services['DEFAULT_RELEASES'] / semantic_id).relative_to(services['ROOT'])),
    }


def compose_core_golden(
    *,
    core_id: str,
    source_path: Path,
    output_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    services: PinLifecycleServices,
) -> dict:
    """Create one exact-scope nightly view from immutable promoted evidence."""

    output_path = services['require_lexical_repository_path'](
        output_path,
        services['DEFAULT_NIGHTLIES'],
        "individual core golden output",
    )
    output_relative = output_path.relative_to(services['DEFAULT_NIGHTLIES'].resolve())
    if (
        len(output_relative.parts) != 2
        or output_relative.parts[1] != "golden.json"
        or not services['LOCAL_ID_RE'].fullmatch(output_relative.parts[0])
    ):
        raise services['PipelineError'](
            "individual core golden output must be <semantic-id>/golden.json"
        )
    if output_path.exists() or output_path.is_symlink():
        raise services['PipelineError'](f"refusing to replace individual core golden: {output_path}")
    source, _selection, semantic_id, _source_path = services['inspect_individual_core_golden'](
        core_id,
        source_path,
        catalog_path,
    )
    if output_relative.parts[0] != semantic_id:
        raise services['PipelineError'](
            f"individual core golden directory must be semantic ID {semantic_id}"
        )

    projected = services['one_core_golden_document'](
        core_id=core_id,
        pin_id=semantic_id,
        created_at=source["created_at"],
        updated_at=source.get("updated_at"),
        baseline=source["baseline"],
        core_record=source["cores"][core_id],
        build_goldens=source["build_goldens"][core_id],
    )
    projected["content_sha256"] = services['golden_content_sha256'](projected)
    projected_report = services['validate_golden_document'](projected)
    projected_errors = [
        *projected_report["errors"],
        *services['verify_local_store'](projected),
    ]
    if projected_errors:
        raise services['PipelineError'](
            "individual core golden projection is invalid:\n- "
            + "\n- ".join(projected_errors)
        )
    services['atomic_create_json'](output_path, projected)
    result = {
        "status": "created",
        "core_id": core_id,
        "semantic_id": semantic_id,
        "path": str(output_path.relative_to(services['ROOT'])),
        "file_sha256": services['sha256_file'](output_path),
        "content_sha256": projected["content_sha256"],
    }
    return result


def freeze_failed_e2e(e2e_path: Path, store_root: Path = DEFAULT_STORE, *, services: PinLifecycleServices) -> dict[str, dict]:
    e2e_path = services['require_contained'](e2e_path, services['ROOT'] / ".local-e2e", "failed E2E record")
    store_root = services['require_contained'](store_root, services['ROOT'] / ".local-e2e", "local store")
    if e2e_path.name != "e2e-record.json":
        raise services['PipelineError']("failed E2E evidence must be an e2e-record.json file")
    evidence_bytes = e2e_path.read_bytes()
    evidence = services['decode_json_object'](evidence_bytes, "failed E2E evidence")
    if (
        not isinstance(evidence, dict)
        or evidence.get("result") != "failed"
        or not evidence.get("local_only")
        or evidence.get("publication") != "disabled"
        or evidence.get("content_sha256") != services['e2e_content_sha256'](evidence)
    ):
        raise services['PipelineError']("failed E2E evidence contract is invalid")
    if not services['runner_evidence_is_well_formed'](evidence.get("runner")):
        raise services['PipelineError']("failed E2E runner evidence is invalid")
    services['validate_bound_host_telemetry'](evidence, e2e_path)

    stored_e2e, stored_e2e_sha = services['store_bytes'](store_root, "e2e", evidence_bytes)
    build_records: dict[str, dict[str, dict]] = {}
    for entry in evidence.get("builds", []):
        core_id = entry.get("core_id")
        arch = entry.get("architecture")
        if not core_id or arch not in services['ARCH_LAYOUT']:
            raise services['PipelineError']("failed E2E build identity is invalid")
        record_path = services['safe_child'](services['ROOT'], entry.get("record", ""), "failed build record")
        services['require_contained'](record_path, e2e_path.parent, "failed build record")
        record_bytes = services['verified_file_bytes'](
            record_path,
            entry.get("record_sha256"),
            "failed E2E build record",
        )
        record = services['decode_json_object'](record_bytes, "failed E2E build record")
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != arch
            or record.get("result") != entry.get("result")
            or not record.get("local_only")
            or record.get("publication") != "disabled"
        ):
            raise services['PipelineError']("failed E2E build record identity is invalid")
        services['require_host_execution_runner_coupling'](
            evidence, record, f"{core_id}/{arch} failed E2E build"
        )
        stored_record, stored_record_sha = services['store_bytes'](
            store_root, "build-records", record_bytes
        )
        frozen = {
            "result": entry.get("result"),
            "record": {
                "path": str(stored_record.relative_to(services['ROOT'])),
                "sha256": stored_record_sha,
            },
        }
        log_name = record.get("build", {}).get("log")
        if log_name:
            log_path = services['safe_child'](record_path.parent, log_name, "failed build log")
            expected_log_sha = record.get("build", {}).get("log_sha256")
            log_bytes = services['verified_file_bytes'](
                log_path, expected_log_sha, "failed E2E build log"
            )
            stored_log, stored_log_sha = services['store_bytes'](
                store_root, "logs", log_bytes
            )
            frozen["log"] = {
                "path": str(stored_log.relative_to(services['ROOT'])),
                "sha256": stored_log_sha,
            }
        core_records = build_records.setdefault(core_id, {})
        if arch in core_records:
            raise services['PipelineError'](f"duplicate failed E2E build identity for {core_id}/{arch}")
        core_records[arch] = frozen

    failures = {}
    for package in evidence.get("packages", []):
        if package.get("result") != "not_packaged":
            continue
        core_id = package.get("core_id")
        if not core_id or core_id in failures:
            raise services['PipelineError']("failed E2E package identity is invalid")
        failures[core_id] = {
            "run_id": evidence.get("run_id"),
            "content_sha256": evidence.get("content_sha256"),
            "record": {
                "path": str(stored_e2e.relative_to(services['ROOT'])),
                "sha256": stored_e2e_sha,
            },
            "reason": package.get("reason", "core package was not produced"),
            "build_records": build_records.get(core_id, {}),
        }
    if not failures:
        raise services['PipelineError']("failed E2E evidence contains no rejected core package")
    return failures


def _verify_pinned_package(
    selection: dict,
    core_id: str,
    validation_context: _PinValidationContext | None = None,
    *,
    services: PinLifecycleServices,
) -> list[str]:
    errors: list[str] = []
    package = selection.get("package", {})
    try:
        package_path = services['require_canonical_store_entry'](
            package, "packages", f"{core_id} pinned package"
        )
        package_bytes = services['verified_file_bytes'](
            package_path,
            package.get("sha256"),
            f"{core_id} pinned package",
            validation_context,
        )
        with services['zipfile'].ZipFile(services['io'].BytesIO(package_bytes)) as archive:
            targets = selection.get("targets", {})
            expected_members = {"manifest.json"}
            manifest = services['decode_json_object'](
                archive.read("manifest.json"), f"{core_id} pinned package manifest"
            )
            for arch, target in targets.items():
                record = target.get("golden_record", {})
                artifact_name = record.get("artifact", {}).get("path")
                member = f"{services['ARCH_LAYOUT'][arch]['package_directory']}/{artifact_name}"
                expected_members.add(member)
                packaged = manifest.get("artifacts", {}).get(arch, {})
                if (
                    packaged.get("path") != member
                    or packaged.get("sha256") != target.get("artifact", {}).get("sha256")
                    or packaged.get("source_commit")
                    != record.get("source", {}).get("resolved_commit")
                    or packaged.get("toolchain_image_id")
                    != record.get("toolchain", {}).get("resolved_image_id")
                    or services['sha256_bytes'](archive.read(member))
                    != target.get("artifact", {}).get("sha256")
                ):
                    errors.append(f"{core_id}/{arch}: pinned package artifact mismatch")
            first_record = next(iter(targets.values())).get("golden_record", {})
            metadata_name = first_record.get("metadata", {}).get("path")
            expected_members.add(metadata_name)
            metadata = selection.get("metadata", {})
            if (
                manifest.get("metadata", {}).get("path") != metadata_name
                or manifest.get("metadata", {}).get("sha256") != metadata.get("sha256")
                or services['sha256_bytes'](archive.read(metadata_name)) != metadata.get("sha256")
            ):
                errors.append(f"{core_id}: pinned package metadata mismatch")
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist()) != expected_members
                or manifest.get("core_id") != core_id
                or not manifest.get("local_only")
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != set(targets)
                or (
                    "chipset_tuning" in selection
                    and manifest.get("tuning_candidate")
                    != selection.get("chipset_tuning")
                )
                or (
                    "chipset_tuning" not in selection
                    and "tuning_candidate" in manifest
                )
            ):
                errors.append(f"{core_id}: pinned package contract is invalid")
    except (
        KeyError,
        StopIteration,
        TypeError,
        UnicodeDecodeError,
        services['json'].JSONDecodeError,
        services['zipfile'].BadZipFile,
        OSError,
        services['PipelineError'],
    ) as exc:
        errors.append(f"{core_id}: cannot verify pinned package: {exc}")
    return errors


def verify_pinned_package(
    selection: dict,
    core_id: str,
    *,
    services: PinLifecycleServices,
) -> list[str]:
    """Verify one pinned package with a fresh, operation-local cache."""

    return services['_verify_pinned_package'](
        selection,
        core_id,
        services['_PinValidationContext'](),
    )


def _validate_pin_set_document_impl(
    document: dict,
    *,
    verify_store: bool = False,
    verify_sources: bool = False,
    document_path: Path | None = None,
    _lineage_paths: tuple[Path, ...] = (),
    _lineage_identities: frozenset[tuple[str, str]] = frozenset(),
    _lineage_depth: int = 0,
    _validation_context: _PinValidationContext | None = None,
    historical_recipe_proofs: bool = False,
    services: PinLifecycleServices,
) -> dict:
    if not isinstance(document, dict):
        return {"status": "invalid", "errors": ["pin set must be an object"]}
    if _validation_context is None:
        _validation_context = services['_PinValidationContext']()
    if _lineage_depth > services['MAX_PIN_PARENT_DEPTH']:
        return {
            "status": "invalid",
            "errors": [
                f"pin parent lineage exceeds maximum depth {services['MAX_PIN_PARENT_DEPTH']}"
            ],
        }

    errors: list[str] = []
    pin_id = document.get("pin_id")
    content_sha256 = document.get("content_sha256")
    scope = document.get("scope")
    cores = document.get("cores")
    sources = document.get("sources")
    parent = document.get("parent")
    summary = document.get("summary")
    if not isinstance(pin_id, str) or services['LOCAL_ID_RE'].fullmatch(pin_id) is None:
        errors.append("pin_id is invalid")
    if not isinstance(content_sha256, str) or services['SHA256_RE'].fullmatch(
        content_sha256
    ) is None:
        errors.append("pin-set content digest is invalid")
    if not isinstance(scope, list) or any(
        not isinstance(core_id, str) for core_id in scope
    ):
        errors.append("pin-set scope must be an array of core IDs")
    if not isinstance(cores, dict) or any(
        not isinstance(core_id, str) or not isinstance(core, dict)
        for core_id, core in (cores.items() if isinstance(cores, dict) else ())
    ):
        errors.append("pin-set cores must be an object of core records")
    if not isinstance(sources, list) or any(
        not isinstance(source, dict) for source in sources
    ):
        errors.append("pin-set sources must be an array of source records")
    if parent is not None and not isinstance(parent, dict):
        errors.append("parent pin identity is invalid")
    if not isinstance(summary, dict):
        errors.append("pin-set summary must be an object")
    if errors:
        return {"status": "invalid", "errors": errors}

    lineage_paths = _lineage_paths
    if document_path is not None:
        try:
            current_path = services['require_contained'](
                document_path, services['DEFAULT_PIN_SET_DIR'], "pin-set document"
            )
            if current_path in lineage_paths:
                return {
                    "status": "invalid",
                    "errors": ["pin parent lineage contains a path cycle"],
                }
            lineage_paths = (*lineage_paths, current_path)
        except services['PipelineError'] as exc:
            errors.append(str(exc))

    lineage_identities = _lineage_identities
    current_identity = (
        pin_id,
        content_sha256,
    )
    if services['LOCAL_ID_RE'].fullmatch(current_identity[0]) and services['SHA256_RE'].fullmatch(
        current_identity[1]
    ):
        if current_identity in lineage_identities:
            return {
                "status": "invalid",
                "errors": ["pin parent lineage repeats an immutable pin identity"],
            }
        lineage_identities = lineage_identities | {current_identity}

    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not document.get("local_only") or document.get("publication") != "disabled":
        errors.append("pin set must be local-only and publication-disabled")
    if document.get("content_sha256") != services['pin_set_content_sha256'](document):
        errors.append("pin-set content digest is invalid")
    if document.get("selection_policy") != services['PIN_SELECTION_POLICY']:
        errors.append("pin-set selection policy is invalid")
    scope_is_well_formed = (
        all(core_id for core_id in scope)
        and scope == sorted(set(scope))
        and set(scope) == set(cores)
    )
    if not scope_is_well_formed:
        errors.append("pin-set scope does not exactly match its core selections")

    source_count = len(sources)
    source_documents: list[dict | None] = []
    for index, source in enumerate(sources):
        source_document = None
        if (
            not services['SHA256_RE'].fullmatch(source.get("file_sha256", ""))
            or not services['SHA256_RE'].fullmatch(source.get("content_sha256", ""))
        ):
            errors.append(f"source {index} digest is invalid")
            source_documents.append(None)
            continue
        try:
            source_path = services['require_manifest_reference_path'](
                source, services['ROOT'], f"source {index}"
            )
            if verify_sources:
                try:
                    source_document, source_file_sha256 = services['load_json_with_sha256'](
                        source_path
                    )
                except services['PipelineError']:
                    errors.append(f"source {index} no longer matches the pin")
                    source_document = None
                if source_document is not None:
                    if (
                        source_file_sha256 != source["file_sha256"]
                        or
                        source_document.get("content_sha256")
                        != source["content_sha256"]
                        or source_document.get("pin_id") != source.get("pin_id")
                    ):
                        errors.append(f"source {index} no longer matches the pin")
                        source_document = None
                    else:
                        source_report = services['validate_golden_document'](source_document)
                        source_errors = list(source_report["errors"])
                        if verify_store:
                            source_errors.extend(
                                services['_verify_local_store'](
                                    source_document,
                                    _validation_context,
                                    historical_recipe_proofs=(
                                        historical_recipe_proofs
                                    ),
                                )
                            )
                        if source_errors:
                            errors.extend(
                                f"source {index}: {error}" for error in source_errors
                            )
                            source_document = None
        except services['PipelineError'] as exc:
            errors.append(str(exc))
        source_documents.append(source_document)

    parent_document = None
    if parent is not None and (
        not isinstance(parent.get("file_sha256"), str)
        or services['SHA256_RE'].fullmatch(parent["file_sha256"]) is None
        or not isinstance(parent.get("content_sha256"), str)
        or services['SHA256_RE'].fullmatch(parent["content_sha256"]) is None
        or not isinstance(parent.get("pin_id"), str)
        or services['LOCAL_ID_RE'].fullmatch(parent["pin_id"]) is None
    ):
        errors.append("parent pin identity is invalid")
    elif parent is not None:
        try:
            parent_path = services['require_manifest_reference_path'](
                parent, services['DEFAULT_PIN_SET_DIR'], "parent pin"
            )
            parent_identity = (parent["pin_id"], parent["content_sha256"])
            if verify_sources and parent_path in lineage_paths:
                errors.append("pin parent lineage contains a path cycle")
            elif verify_sources and parent_identity in lineage_identities:
                errors.append("pin parent lineage repeats an immutable pin identity")
            elif verify_sources and _lineage_depth >= services['MAX_PIN_PARENT_DEPTH']:
                errors.append(
                    f"pin parent lineage exceeds maximum depth {services['MAX_PIN_PARENT_DEPTH']}"
                )
            elif verify_sources:
                try:
                    parent_document, parent_file_sha256 = services['load_json_with_sha256'](
                        parent_path
                    )
                except services['PipelineError']:
                    errors.append("parent pin no longer matches its reference")
                    parent_document = None
                if parent_document is not None and (
                    parent_file_sha256 != parent["file_sha256"]
                    or parent_document.get("content_sha256")
                    != parent["content_sha256"]
                    or parent_document.get("pin_id") != parent["pin_id"]
                ):
                    errors.append("parent pin no longer matches its reference")
                    parent_document = None
                if parent_document is not None:
                    parent_scope = parent_document.get("scope", [])
                    if (
                        scope_is_well_formed
                        and isinstance(parent_scope, list)
                        and all(isinstance(core_id, str) for core_id in parent_scope)
                    ):
                        dropped = sorted(set(parent_scope) - set(scope))
                        if dropped:
                            errors.append(
                                "pin-set scope drops parent cores: "
                                + ", ".join(dropped)
                            )
                    ancestor_report = services['_validate_pin_set_document'](
                        parent_document,
                        verify_store=verify_store,
                        verify_sources=True,
                        document_path=parent_path,
                        _lineage_paths=lineage_paths,
                        _lineage_identities=lineage_identities,
                        _lineage_depth=_lineage_depth + 1,
                        _validation_context=_validation_context,
                        historical_recipe_proofs=historical_recipe_proofs,
                    )
                    errors.extend(
                        f"parent {parent['pin_id']}: {error}"
                        for error in ancestor_report["errors"]
                    )
        except services['PipelineError'] as exc:
            errors.append(str(exc))

    retained = 0
    for core_id, core in cores.items():
        decision = core.get("decision")
        if decision not in {"select_source", "retain_parent"}:
            errors.append(f"{core_id}: selection decision is invalid")
        if decision == "select_source":
            source_index = core.get("source_index")
            if (
                isinstance(source_index, bool)
                or not isinstance(source_index, int)
                or not 0 <= source_index < source_count
            ):
                errors.append(f"{core_id}: source index is invalid")
        else:
            retained += 1
            if parent is None:
                errors.append(f"{core_id}: parent retention lacks a parent pin")
        selection = core.get("selection")
        if not isinstance(selection, dict):
            errors.append(f"{core_id}: selection must be an object")
            continue
        reconstructed_sources: list[dict | None] = []
        if verify_sources:
            for source_index, source_document in enumerate(source_documents):
                if source_document is None:
                    reconstructed_sources.append(None)
                    continue
                try:
                    reconstructed_sources.append(
                        services['complete_core_bundle'](source_document, core_id)
                    )
                except services['PipelineError'] as exc:
                    errors.append(
                        f"{core_id}: cannot reconstruct source {source_index} bundle: {exc}"
                    )
                    reconstructed_sources.append(None)
        if verify_sources and decision == "select_source":
            source_index = core.get("source_index")
            if (
                isinstance(source_index, int)
                and not isinstance(source_index, bool)
                and 0 <= source_index < len(reconstructed_sources)
            ):
                expected_selection = reconstructed_sources[source_index]
                if expected_selection is None or selection != expected_selection:
                    errors.append(
                        f"{core_id}: selection does not match its frozen source bundle"
                    )
                if any(
                    candidate is not None
                    for candidate in reconstructed_sources[:source_index]
                ):
                    errors.append(
                        f"{core_id}: selection violates first-complete source order"
                    )
        elif verify_sources and decision == "retain_parent":
            if any(candidate is not None for candidate in reconstructed_sources):
                errors.append(f"{core_id}: parent retained despite a complete source bundle")
            if parent_document is not None:
                parent_selection = (
                    parent_document.get("cores", {}).get(core_id, {}).get("selection")
                )
                if selection != parent_selection:
                    errors.append(f"{core_id}: retained selection differs from its parent")
        computed_selection_sha256 = services['selection_content_sha256'](selection)
        full_selection_sha256 = services['sha256_bytes'](
            services['json'].dumps(selection, sort_keys=True, separators=(",", ":")).encode()
        )
        if selection.get("selection_sha256") != computed_selection_sha256:
            errors.append(f"{core_id}: selection digest is invalid")
        if (
            selection.get("tier") != "build_golden"
            or selection.get("validation_scope") != "static-build-only"
        ):
            errors.append(f"{core_id}: only static build-golden bundles are selectable")
        selection_tuning = selection.get("chipset_tuning")
        selection_reproduction = selection.get("reproduction")
        selection_source_candidate = selection.get("source_candidate")
        selection_output_reproduction = selection.get("output_reproduction")
        selection_host_reproduction = selection.get("host_reproduction")
        if selection_tuning is not None:
            try:
                if (
                    selection_source_candidate is not None
                    or selection_output_reproduction is not None
                ):
                    raise services['PipelineError'](
                        "tuned and source-candidate selections are mutually exclusive"
                    )
                selection_tuning = services['validated_tuning_candidate_shape'](
                    selection_tuning
                )
                if not isinstance(selection_reproduction, services['Mapping']):
                    errors.append(f"{core_id}: tuned selection lacks reproduction proof")
            except services['PipelineError'] as exc:
                errors.append(f"{core_id}: {exc}")
                selection_tuning = None
        elif selection_reproduction is not None:
            errors.append(f"{core_id}: untuned selection has reproduction evidence")
        elif (
            selection_source_candidate is not None
            or selection_output_reproduction is not None
        ):
            try:
                selection_source_candidate = (
                    services['validated_embedded_source_candidate_shape'](
                        selection_source_candidate,
                        core_id=core_id,
                    )
                )
                if not isinstance(selection_output_reproduction, services['Mapping']):
                    raise services['PipelineError'](
                        "source-candidate selection lacks output reproduction proof"
                    )
            except services['PipelineError'] as exc:
                errors.append(f"{core_id}: {exc}")
                selection_source_candidate = None
        package = selection.get("package")
        if not isinstance(package, dict):
            errors.append(f"{core_id}: package must be an object")
            package = {}
        if package.get("name") != f"{core_id}_libretro.zip":
            errors.append(f"{core_id}: package name is invalid")
        package_store_valid = False
        try:
            package_path = services['require_canonical_store_entry'](
                package, "packages", f"{core_id} pinned package"
            )
            if verify_store:
                try:
                    package_bytes = services['verified_file_bytes'](
                        package_path,
                        package.get("sha256"),
                        f"{core_id} pinned package",
                        _validation_context,
                    )
                    package_store_valid = len(package_bytes) == package.get("size")
                except services['PipelineError']:
                    package_store_valid = False
                if not package_store_valid:
                    errors.append(
                        f"{core_id}: pinned package store identity is invalid"
                    )
        except services['PipelineError'] as exc:
            errors.append(str(exc))

        metadata = selection.get("metadata")
        if not isinstance(metadata, dict):
            errors.append(f"{core_id}: metadata must be an object")
            metadata = {}
        try:
            metadata_path = services['require_canonical_store_entry'](
                metadata, "metadata", f"{core_id} pinned metadata"
            )
            if verify_store:
                try:
                    metadata_bytes = services['verified_file_bytes'](
                        metadata_path,
                        metadata.get("sha256"),
                        f"{core_id} pinned metadata",
                        _validation_context,
                    )
                    if len(metadata_bytes) != metadata.get("size"):
                        raise services['PipelineError']("metadata size drift")
                except services['PipelineError']:
                    errors.append(
                        f"{core_id}: pinned metadata store identity is invalid"
                    )
        except services['PipelineError'] as exc:
            errors.append(str(exc))

        targets = selection.get("targets")
        if not isinstance(targets, dict):
            errors.append(f"{core_id}: targets must be an object")
            targets = {}
        selected_e2e = selection.get("e2e")
        if not isinstance(selected_e2e, dict):
            errors.append(f"{core_id}: E2E identity must be an object")
            selected_e2e = {}
        selected_build_records = selected_e2e.get("build_records")
        if not isinstance(selected_build_records, dict):
            errors.append(f"{core_id}: E2E build records must be an object")
            selected_build_records = {}
        expected_targets = set(selected_build_records)
        if (
            not selected_e2e.get("run_id")
            or not services['SHA256_RE'].fullmatch(selected_e2e.get("content_sha256", ""))
            or selected_e2e.get("package_sha256") != package.get("sha256")
        ):
            errors.append(f"{core_id}: pinned E2E identity is invalid")
        if not targets or set(targets) != expected_targets:
            errors.append(f"{core_id}: pinned target set is incomplete")
        if selection_tuning is not None and (
            len(targets) != 1
            or set(targets) != {selection_tuning["profile"]["architecture"]}
        ):
            errors.append(f"{core_id}: tuned pin must contain exactly its profile ABI")
        reference_source = None
        reference_recipe = None
        for arch, target in targets.items():
            if not isinstance(target, dict):
                errors.append(f"{core_id}/{arch}: target must be an object")
                continue
            record = target.get("golden_record")
            artifact = target.get("artifact")
            if not isinstance(record, dict) or not isinstance(artifact, dict):
                errors.append(
                    f"{core_id}/{arch}: golden record and artifact must be objects"
                )
                continue
            if arch not in services['ARCH_LAYOUT']:
                errors.append(f"{core_id}: unknown pinned target {arch}")
                continue
            if (
                record.get("core_id") != core_id
                or record.get("architecture") != arch
                or record.get("promotion_state") != "build_golden"
                or record.get("artifact", {}).get("sha256") != artifact.get("sha256")
                or record.get("artifact", {}).get("size") != artifact.get("size")
                or record.get("metadata", {}).get("sha256") != metadata.get("sha256")
                or record.get("local_store", {}).get("artifact", {}).get("path")
                != artifact.get("path")
                or record.get("local_store", {}).get("artifact", {}).get("sha256")
                != artifact.get("sha256")
                or record.get("local_store", {}).get("metadata", {}).get("path")
                != metadata.get("path")
                or record.get("local_store", {}).get("metadata", {}).get("sha256")
                != metadata.get("sha256")
                or record.get("local_store", {}).get("package", {}).get("path")
                != package.get("path")
                or record.get("local_store", {}).get("package", {}).get("sha256")
                != package.get("sha256")
                or record.get("e2e", {}).get("package_sha256")
                != package.get("sha256")
                or record.get("e2e", {}).get("content_sha256")
                != selection.get("e2e", {}).get("content_sha256")
                or record.get("e2e", {}).get("build_records")
                != selection.get("e2e", {}).get("build_records")
                or target.get("build_record_sha256")
                != selected_build_records.get(arch)
                or target.get("provenance_identity_sha256")
                != services['provenance_identity_sha256'](record)
                or record.get("host_reproduction")
                != selection_host_reproduction
                or (
                    selection_tuning is not None
                    and (
                        record.get("tuning_candidate") != selection_tuning
                        or record.get("reproduction") != selection_reproduction
                        or record.get("recipe", {}).get("chipset_tuning")
                        != services['tuning_candidate_recipe_identity'](selection_tuning)
                    )
                )
                or (
                    selection_tuning is None
                    and selection_source_candidate is None
                    and (
                        "tuning_candidate" in record
                        or "reproduction" in record
                        or "source_candidate" in record
                        or "output_reproduction" in record
                        or "chipset_tuning" in record.get("recipe", {})
                    )
                )
                or (
                    selection_source_candidate is not None
                    and (
                        record.get("source_candidate")
                        != selection_source_candidate
                        or record.get("output_reproduction")
                        != selection_output_reproduction
                        or "tuning_candidate" in record
                        or "reproduction" in record
                        or "chipset_tuning" in record.get("recipe", {})
                    )
                )
            ):
                errors.append(f"{core_id}/{arch}: embedded golden record is inconsistent")
            if selection_tuning is not None:
                try:
                    services['validated_tuned_reproduction_shape'](
                        selection_reproduction,
                        core_id=core_id,
                        arch=arch,
                        golden_record=record,
                    )
                except services['PipelineError'] as exc:
                    errors.append(f"{core_id}/{arch}: {exc}")
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
                errors.append(
                    f"{core_id}/{arch}: embedded metadata does not match its replacement"
                )
            if reference_source is None:
                reference_source = record.get("source")
                reference_recipe = record.get("recipe")
            elif record.get("source") != reference_source or record.get("recipe") != reference_recipe:
                errors.append(f"{core_id}: target provenance is not package-coherent")
            try:
                artifact_path = services['require_canonical_store_entry'](
                    artifact, "artifacts", f"{core_id}/{arch} pinned artifact"
                )
                if verify_store:
                    try:
                        artifact_bytes = services['verified_file_bytes'](
                            artifact_path,
                            artifact.get("sha256"),
                            f"{core_id}/{arch} pinned artifact",
                            _validation_context,
                        )
                        if len(artifact_bytes) != artifact.get("size"):
                            raise services['PipelineError']("artifact size drift")
                    except services['PipelineError']:
                        errors.append(
                            f"{core_id}/{arch}: pinned artifact store identity is invalid"
                        )
            except services['PipelineError'] as exc:
                errors.append(str(exc))

        candidate_records = {
            target_arch: target.get("golden_record")
            for target_arch, target in targets.items()
            if isinstance(target, services['Mapping'])
        }
        if selection_source_candidate is not None:
            candidate_selection = selection_source_candidate["selection"]
            if not isinstance(reference_source, services['Mapping']) or any(
                reference_source.get(record_key)
                != candidate_selection.get(selection_key)
                for record_key, selection_key in (
                    ("url", "url"),
                    ("requested_ref", "requested_ref"),
                    ("commit", "commit"),
                    ("resolved_commit", "commit"),
                    ("tree", "tree"),
                )
            ):
                errors.append(
                    f"{core_id}: source-candidate selection differs from pin source"
                )
            try:
                services['validated_output_reproduction_shape'](
                    selection_output_reproduction,
                    core_id=core_id,
                    golden_records=candidate_records,
                )
            except services['PipelineError'] as exc:
                errors.append(f"{core_id}: {exc}")
        if selection_host_reproduction is not None:
            try:
                services['validated_host_reproduction_shape'](
                    selection_host_reproduction,
                    core_id=core_id,
                    golden_records=candidate_records,
                )
            except services['PipelineError'] as exc:
                errors.append(f"{core_id}: {exc}")

        if verify_store:
            package_cache_key = None
            if (
                package_store_valid
                and isinstance(package.get("path"), str)
                and isinstance(package.get("sha256"), str)
                and type(package.get("size")) is int
            ):
                package_cache_key = (
                    core_id,
                    full_selection_sha256,
                    package["path"],
                    package["sha256"],
                    package["size"],
                )
            if (
                package_cache_key is None
                or package_cache_key not in _validation_context.pinned_packages
            ):
                package_errors = services['_verify_pinned_package'](
                    selection, core_id, _validation_context
                )
                errors.extend(package_errors)
                if package_cache_key is not None and not package_errors:
                    _validation_context.pinned_packages.add(package_cache_key)

        failure = core.get("failed_candidate")
        if failure is not None:
            if not isinstance(failure, dict):
                errors.append(f"{core_id}: failed candidate must be an object")
                continue
            if decision != "retain_parent":
                errors.append(f"{core_id}: failed candidate did not retain its parent")
            try:
                evidence_path = services['require_canonical_store_entry'](
                    failure.get("record", {}), "e2e", f"{core_id} failed candidate"
                )
                if verify_store:
                    try:
                        evidence = services['verified_json_object'](
                            evidence_path,
                            failure.get("record", {}).get("sha256"),
                            f"{core_id} failed-candidate evidence",
                            _validation_context,
                        )
                    except services['PipelineError']:
                        errors.append(f"{core_id}: failed-candidate evidence drift")
                        continue
                    if (
                        evidence.get("result") != "failed"
                        or not evidence.get("local_only")
                        or evidence.get("publication") != "disabled"
                        or evidence.get("run_id") != failure.get("run_id")
                        or evidence.get("content_sha256")
                        != failure.get("content_sha256")
                        or evidence.get("content_sha256")
                        != services['e2e_content_sha256'](evidence)
                    ):
                        errors.append(f"{core_id}: failed-candidate contract is invalid")
                    if not services['runner_evidence_is_well_formed'](evidence.get("runner")):
                        errors.append(
                            f"{core_id}: failed-candidate runner evidence is invalid"
                        )
                    else:
                        try:
                            services['validate_bound_host_telemetry'](evidence, evidence_path)
                        except services['PipelineError'] as exc:
                            errors.append(
                                f"{core_id}: failed-candidate host telemetry is invalid: {exc}"
                            )
                    matching_packages = [
                        item
                        for item in evidence.get("packages", [])
                        if item.get("core_id") == core_id
                    ]
                    if (
                        len(matching_packages) != 1
                        or matching_packages[0].get("result") != "not_packaged"
                        or matching_packages[0].get("reason") != failure.get("reason")
                    ):
                        errors.append(
                            f"{core_id}: failed-candidate package evidence is not bound"
                        )
                    matching_builds = {}
                    for item in evidence.get("builds", []):
                        if item.get("core_id") != core_id:
                            continue
                        arch = item.get("architecture")
                        if arch in matching_builds:
                            errors.append(
                                f"{core_id}/{arch}: duplicate failed E2E build evidence"
                            )
                        else:
                            matching_builds[arch] = item
                    frozen_builds = failure.get("build_records", {})
                    if set(matching_builds) != set(frozen_builds):
                        errors.append(
                            f"{core_id}: failed-candidate build target set is not bound"
                        )
                    for arch, frozen in frozen_builds.items():
                        entry = matching_builds.get(arch, {})
                        record_entry = frozen.get("record", {})
                        if (
                            entry.get("result") != frozen.get("result")
                            or entry.get("record_sha256") != record_entry.get("sha256")
                        ):
                            errors.append(
                                f"{core_id}/{arch}: failed build record is not E2E-bound"
                            )
                        try:
                            record_path = services['require_canonical_store_entry'](
                                record_entry,
                                "build-records",
                                f"{core_id}/{arch} failed build record",
                            )
                            record = services['verified_json_object'](
                                record_path,
                                record_entry.get("sha256"),
                                f"{core_id}/{arch} failed build record",
                                _validation_context,
                            )
                            if (
                                record.get("core_id") != core_id
                                or record.get("architecture") != arch
                                or record.get("result") != frozen.get("result")
                                or not record.get("local_only")
                                or record.get("publication") != "disabled"
                            ):
                                errors.append(
                                    f"{core_id}/{arch}: failed build record identity is invalid"
                                )
                            try:
                                services['require_host_execution_runner_coupling'](
                                    evidence,
                                    record,
                                    f"{core_id}/{arch} failed stored build",
                                )
                            except services['PipelineError'] as exc:
                                errors.append(str(exc))
                            expected_log_sha = record.get("build", {}).get("log_sha256")
                            log_entry = frozen.get("log")
                            if expected_log_sha and log_entry is None:
                                errors.append(
                                    f"{core_id}/{arch}: failed build log evidence is missing"
                                )
                            elif not expected_log_sha and log_entry is not None:
                                errors.append(
                                    f"{core_id}/{arch}: failed build log is not record-bound"
                                )
                            elif log_entry is not None:
                                log_path = services['require_canonical_store_entry'](
                                    log_entry,
                                    "logs",
                                    f"{core_id}/{arch} failed build log",
                                )
                                if log_entry.get("sha256") != expected_log_sha:
                                    errors.append(
                                        f"{core_id}/{arch}: failed build log drift"
                                    )
                                else:
                                    services['verified_file_bytes'](
                                        log_path,
                                        log_entry.get("sha256"),
                                        f"{core_id}/{arch} failed build log",
                                        _validation_context,
                                    )
                        except services['PipelineError'] as exc:
                            errors.append(str(exc))
            except services['PipelineError'] as exc:
                errors.append(str(exc))

    if summary.get("core_count") != len(cores):
        errors.append("summary.core_count does not match")
    if summary.get("retained_parent_count") != retained:
        errors.append("summary.retained_parent_count does not match")
    if summary.get("selected_source_count") != len(cores) - retained:
        errors.append("summary.selected_source_count does not match")
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def _validate_pin_set_document(
    document: dict,
    *,
    verify_store: bool = False,
    verify_sources: bool = False,
    document_path: Path | None = None,
    _lineage_paths: tuple[Path, ...] = (),
    _lineage_identities: frozenset[tuple[str, str]] = frozenset(),
    _lineage_depth: int = 0,
    _validation_context: _PinValidationContext | None = None,
    historical_recipe_proofs: bool = False,
    services: PinLifecycleServices,
) -> dict:
    """Validate untrusted pin JSON without exposing shape exceptions."""

    try:
        return services['_validate_pin_set_document_impl'](
            document,
            verify_store=verify_store,
            verify_sources=verify_sources,
            document_path=document_path,
            _lineage_paths=_lineage_paths,
            _lineage_identities=_lineage_identities,
            _lineage_depth=_lineage_depth,
            _validation_context=_validation_context,
            historical_recipe_proofs=historical_recipe_proofs,
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {
            "status": "invalid",
            "errors": [
                "pin set contains malformed nested data "
                f"({type(exc).__name__})"
            ],
        }


def validate_pin_set_document(
    document: dict,
    *,
    verify_store: bool = False,
    verify_sources: bool = False,
    document_path: Path | None = None,
    services: PinLifecycleServices,
) -> dict:
    """Validate a pin with a fresh cache and no historical-proof bypass."""

    return services['_validate_pin_set_document'](
        document,
        verify_store=verify_store,
        verify_sources=verify_sources,
        document_path=document_path,
        _validation_context=services['_PinValidationContext'](),
    )


def _require_pin_current_selection_authority(
    pin: Mapping[str, object],
    *,
    operation: str,
    catalog: Mapping[str, object] | None = None,
    services: PinLifecycleServices,
) -> None:
    if catalog is None:
        catalog = services['load_catalog'](services['DEFAULT_CATALOG'])
    scope = pin.get("scope")
    cores = pin.get("cores")
    if not isinstance(scope, list) or not isinstance(cores, services['Mapping']):
        raise services['PipelineError'](f"{operation} pin scope is malformed")
    for core_id in scope:
        core_record = cores.get(core_id) if isinstance(core_id, str) else None
        selection = (
            core_record.get("selection")
            if isinstance(core_record, services['Mapping'])
            else None
        )
        if not isinstance(core_id, str) or not isinstance(selection, services['Mapping']):
            raise services['PipelineError'](f"{operation} pin selection is malformed")
        services['_require_current_selection_source_authority'](
            catalog,
            selection,
            core_id=core_id,
            operation=operation,
        )


def _authoritative_core_track_pin_report(
    document: dict,
    path: Path,
    *,
    catalog: Mapping[str, object],
    services: PinLifecycleServices,
) -> dict:
    """Apply pin admission against one authenticated catalog snapshot."""

    try:
        persisted, persisted_file_sha256 = services['load_json_with_sha256'](path)
    except services['PipelineError'] as exc:
        return {"status": "invalid", "errors": [str(exc)]}
    if persisted != document:
        return {
            "status": "invalid",
            "errors": [
                "authoritative core pin document differs from exact path bytes"
            ],
        }
    report = services['_validate_pin_set_document'](
        persisted,
        verify_store=True,
        verify_sources=True,
        document_path=path,
        historical_recipe_proofs=True,
    )
    if report.get("status") != "valid":
        return report
    try:
        core_id, _semantic_id = services['require_individual_pin_identity'](
            persisted, pin_path=path
        )
        services['_require_pin_current_selection_authority'](
            persisted,
            operation="authoritative core-track pin",
            catalog=catalog,
        )
    except services['PipelineError'] as exc:
        return {"status": "invalid", "errors": [str(exc)]}
    try:
        final_document, final_file_sha256 = services['load_json_with_sha256'](path)
    except services['PipelineError'] as exc:
        return {"status": "invalid", "errors": [str(exc)]}
    if (
        final_file_sha256 != persisted_file_sha256
        or final_document != persisted
    ):
        return {
            "status": "invalid",
            "errors": ["authoritative core pin changed during admission"],
        }
    return report


def authoritative_core_track_pin_report(document: dict, path: Path, *, services: PinLifecycleServices) -> dict:
    """Apply the full immutable-pin and fresh canonical admission gates."""

    return services['_authoritative_core_track_pin_report'](
        document,
        path,
        catalog=services['load_catalog'](services['DEFAULT_CATALOG']),
    )


def load_authoritative_core_pin_index(*, services: PinLifecycleServices) -> dict[str, dict[str, object]]:
    """Load track pins only after the canonical lifecycle validator admits them."""

    catalog, catalog_file_sha256 = services['load_catalog_with_sha256'](services['DEFAULT_CATALOG'])
    index = services['load_core_pin_index'](
        services['ROOT'],
        pin_validator=lambda document, path: services['_authoritative_core_track_pin_report'](
            document,
            path,
            catalog=catalog,
        ),
    )
    final_catalog, final_catalog_file_sha256 = services['load_json_with_sha256'](
        services['DEFAULT_CATALOG']
    )
    if (
        final_catalog_file_sha256 != catalog_file_sha256
        or final_catalog != catalog
    ):
        raise services['PipelineError'](
            "canonical catalog changed during authoritative core pin indexing"
        )
    return index


def core_track_source_ancestry_verifier(*, services: PinLifecycleServices) -> Callable[[str, str, str, str], bool]:
    """Use only already-present local source graphs; never fetch for validation."""

    return services['local_git_source_ancestry_verifier'](
        services['DEFAULT_CORE_TRACK_SOURCE_REPOSITORIES']
    )


def release_source_graph_requirements(
    *,
    catalog: Mapping[str, object],
    pin_index: Mapping[str, Mapping[str, object]],
    services: PinLifecycleServices,
) -> list[dict[str, object]]:
    """Discover differing track edges, then bind their exact pin sources.

    The first registry pass defers only the ancestry decision to a recording
    callback. Every other registry, roster, tuning, stable-provenance, and pin
    identity gate runs normally. The prepared graph is subsequently checked
    by the real offline verifier before any caller may continue.
    """

    registry = services['load_json'](services['DEFAULT_CORE_TRACKS'])
    tunings = services['load_json'](services['DEFAULT_CHIPSET_TUNINGS'])
    roster = services['load_json'](services['DEFAULT_SPRUCE_RELEASE_ROSTER'])
    spruce_branch_bases = services['load_json'](services['DEFAULT_SPRUCE_BRANCH_BASES'])
    source_registry_index = services['load_core_track_source_registry_index'](services['ROOT'])
    recorded_edges: list[tuple[str, str, str, str]] = []

    def record_edge(
        core_id: str,
        repository: str,
        ancestor: str,
        descendant: str,
    ) -> bool:
        recorded_edges.append((core_id, repository, ancestor, descendant))
        return True

    services['validate_core_tracks'](
        registry,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tunings,
        main_release_roster=roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=record_edge,
    )
    edges = sorted(set(recorded_edges))
    if not edges:
        return []

    requirements: list[dict[str, object]] = []
    for core_id in sorted({edge[0] for edge in edges}):
        core_edges = [edge for edge in edges if edge[0] == core_id]
        repositories = {edge[1] for edge in core_edges}
        if len(repositories) != 1:
            raise services['PipelineError'](
                f"release source graph has multiple repositories for {core_id}"
            )
        repository = next(iter(repositories))
        required_commits = {
            commit for _core, _repository, ancestor, descendant in core_edges
            for commit in (ancestor, descendant)
        }
        matching_entries = [
            entry
            for _pin_id, entry in sorted(pin_index.items())
            if entry.get("core_id") == core_id
            and entry.get("source_repository") == repository
            and entry.get("source_commit") in required_commits
        ]
        matched_commits = {entry.get("source_commit") for entry in matching_entries}
        if matched_commits != required_commits:
            missing = sorted(required_commits - matched_commits)
            raise services['PipelineError'](
                f"release source graph cannot bind validated pins for {core_id}: "
                + ", ".join(missing)
            )
        sources: dict[tuple[str, str, str], dict[str, str]] = {}
        for entry in matching_entries:
            pin_path = services['safe_child'](
                services['ROOT'],
                str(entry["path"]),
                f"{core_id} release source graph pin",
            )
            pin, pin_file_sha256 = services['load_json_with_sha256'](pin_path)
            if pin_file_sha256 != entry.get("file_sha256"):
                raise services['PipelineError'](
                    f"release source graph pin changed after indexing: {core_id}"
                )
            if pin.get("content_sha256") != entry.get("content_sha256"):
                raise services['PipelineError'](
                    f"release source graph pin content changed after indexing: {core_id}"
                )
            selection = pin.get("cores", {}).get(core_id, {}).get("selection", {})
            targets = selection.get("targets") if isinstance(selection, services['Mapping']) else None
            if not isinstance(targets, services['Mapping']) or not targets:
                raise services['PipelineError'](
                    f"release source graph pin targets are unavailable: {core_id}"
                )
            pin_sources = [
                services['pinned_group_execution_source'](
                    target.get("golden_record", {}).get("source")
                    if isinstance(target, services['Mapping'])
                    else None,
                    label=f"{core_id}/{architecture} release source graph pin",
                )
                for architecture, target in sorted(targets.items())
            ]
            source = pin_sources[0]
            if any(item != source for item in pin_sources):
                raise services['PipelineError'](
                    f"release source graph pin sources differ by target: {core_id}"
                )
            if (
                source["url"] != repository
                or source["commit"] != entry.get("source_commit")
                or source["tree"] != entry.get("source_tree")
            ):
                raise services['PipelineError'](
                    f"release source graph pin projection is inconsistent: {core_id}"
                )
            material = {
                "requested_ref": source["requested_ref"],
                "commit": source["commit"],
                "tree": source["tree"],
            }
            sources[
                (material["requested_ref"], material["commit"], material["tree"])
            ] = material
        requirements.append(
            {
                "core_id": core_id,
                "repository": repository,
                "sources": [sources[key] for key in sorted(sources)],
                "ancestry": [
                    {"ancestor": ancestor, "descendant": descendant}
                    for _core, _repository, ancestor, descendant in core_edges
                ],
            }
        )
    return requirements


def prepare_release_group_source_graph(
    group_tag: str,
    *,
    core_id: str | None = None,
    services: PinLifecycleServices,
) -> dict[str, object]:
    """Prepare and revalidate a full group or one exact plan-row core graph."""

    services['parse_group_tag'](group_tag)
    catalog = services['load_catalog'](services['DEFAULT_CATALOG'])
    if core_id is not None and (
        not isinstance(core_id, str) or core_id not in catalog.get("cores", {})
    ):
        raise services['PipelineError'](f"release source graph core is not cataloged: {core_id}")
    pin_index = services['load_authoritative_core_pin_index']()

    # The first pass is authority/coverage-only.  It must reject deferred
    # groups before source hydration, but a clean cache cannot yet prove
    # cross-track ancestry.  The requirements builder records those exact
    # edges, preparation hydrates them, and the second pass below proves them
    # with the real cache-backed verifier before returning any usable report.
    def preflight_ancestry_recorder(
        _core_id: str,
        _repository: str,
        _ancestor: str,
        _descendant: str,
    ) -> bool:
        return True

    inventory = services['construct_core_track_inventory'](
        services['load_json'](services['DEFAULT_CORE_TRACKS']),
        catalog=catalog,
        pin_index=pin_index,
        tunings=services['load_json'](services['DEFAULT_CHIPSET_TUNINGS']),
        main_release_roster=services['load_json'](services['DEFAULT_SPRUCE_RELEASE_ROSTER']),
        spruce_branch_bases=services['load_json'](services['DEFAULT_SPRUCE_BRANCH_BASES']),
        group_tag=group_tag,
        requested_cores=None if core_id is None else [core_id],
        source_registry_index=services['load_core_track_source_registry_index'](services['ROOT']),
        source_ancestry_verifier=preflight_ancestry_recorder,
        source_ancestry_core_id=core_id,
    )
    if not inventory["complete"]:
        deferred_ids = [
            row["core_id"]
            for row in inventory.get("deferred_cores", [])
            if isinstance(row, services['Mapping']) and isinstance(row.get("core_id"), str)
        ]
        raise services['PipelineError'](
            "release source graph group inventory is incomplete: "
            + ", ".join(
                sorted(set(inventory["unsupported_core_ids"]) | set(deferred_ids))
            )
        )
    all_requirements = services['release_source_graph_requirements'](
        catalog=catalog,
        pin_index=pin_index,
    )
    requirements = (
        all_requirements
        if core_id is None
        else [
            requirement
            for requirement in all_requirements
            if requirement["core_id"] == core_id
        ]
    )
    verifier = services['core_track_source_ancestry_verifier']()
    report = services['prepare_release_source_graph'](
        requirements=requirements,
        repository_root=services['ROOT'],
        repository_cache=services['DEFAULT_CORE_TRACK_SOURCE_REPOSITORIES'],
        ancestry_verifier=verifier,
    )
    inventory = services['construct_core_track_inventory'](
        services['load_json'](services['DEFAULT_CORE_TRACKS']),
        catalog=catalog,
        pin_index=pin_index,
        tunings=services['load_json'](services['DEFAULT_CHIPSET_TUNINGS']),
        main_release_roster=services['load_json'](services['DEFAULT_SPRUCE_RELEASE_ROSTER']),
        spruce_branch_bases=services['load_json'](services['DEFAULT_SPRUCE_BRANCH_BASES']),
        group_tag=group_tag,
        requested_cores=None if core_id is None else [core_id],
        source_registry_index=services['load_core_track_source_registry_index'](services['ROOT']),
        source_ancestry_verifier=verifier,
        source_ancestry_core_id=core_id,
    )
    if not inventory["complete"]:
        deferred_ids = [
            row["core_id"]
            for row in inventory.get("deferred_cores", [])
            if isinstance(row, services['Mapping']) and isinstance(row.get("core_id"), str)
        ]
        raise services['PipelineError'](
            "release source graph group inventory became incomplete after preparation: "
            + ", ".join(
                sorted(set(inventory["unsupported_core_ids"]) | set(deferred_ids))
            )
        )
    return {
        **report,
        "group_tag": group_tag,
        "core_scope": core_id if core_id is not None else "all",
        "track_registry_content_sha256": inventory[
            "track_registry_content_sha256"
        ],
        "inventory_content_sha256": inventory["content_sha256"],
    }


def _build_equivalence_identity(build: object, *, services: PinLifecycleServices) -> object:
    """Project the recipe-bound build contract without run-local log bytes.

    Each build log remains independently content-addressed and validated.  Its
    byte identity is evidence about one execution, not part of the equivalence
    identity for two builds that produce the exact approved artifact bytes.
    """

    if not isinstance(build, dict):
        return None
    return {key: value for key, value in build.items() if key != "log_sha256"}


def _validate_canonical_compatibility_build_record(
    record: dict,
    record_path: Path,
    expected_target: dict,
    build_log_text: str,
    *,
    services: PinLifecycleServices,
) -> None:
    """Prove a canonical compatibility build against frozen and current gates.

    This deliberately does not compare the record with the current catalog,
    workflows, pipeline bytes, or toolchain files.  The selected pin binds a
    content-addressed recipe snapshot containing those historical bytes; both
    the selected and reproduction records must match that same snapshot.
    Canonical compatibility is also a current admission record, so it
    reapplies any registered core-owned log proof. A changed proof can require
    a new per-core compatibility successor without changing the immutable pin
    or legacy fixture.
    """

    expected_record = expected_target.get("golden_record")
    if not isinstance(expected_record, dict):
        raise services['PipelineError']("compatibility expected build record is invalid")
    core_id = record.get("core_id")
    architecture = record.get("architecture")
    label = f"{core_id}/{architecture} compatibility build"
    required_keys = {
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
    if set(record) != required_keys:
        raise services['PipelineError'](f"{label}: build record fields are invalid")
    if (
        expected_record.get("core_id") != core_id
        or expected_record.get("architecture") != architecture
    ):
        raise services['PipelineError'](f"{label}: promoted build identity differs")
    for field in (
        "source",
        "recipe",
        "toolchain",
        "artifact",
        "metadata",
    ):
        if record.get(field) != expected_record.get(field):
            raise services['PipelineError'](f"{label}: historical {field} differs")

    build = record.get("build")
    expected_build = expected_record.get("build")
    if not isinstance(build, dict) or not isinstance(expected_build, dict):
        raise services['PipelineError'](f"{label}: historical build differs")
    if services['_build_equivalence_identity'](build) != services['_build_equivalence_identity'](
        expected_build
    ):
        raise services['PipelineError'](f"{label}: historical build differs")

    recipe = record.get("recipe")
    if not isinstance(recipe, dict) or not services['pipeline_source_bundle_is_well_formed'](
        recipe.get("pipeline_bundle")
    ):
        raise services['PipelineError'](f"{label}: historical recipe bundle is invalid")
    pipeline_bundle = recipe["pipeline_bundle"]
    launcher_path = str(services['Path'](services['__file__']).relative_to(services['ROOT']))
    if pipeline_bundle["files"].get(launcher_path) != recipe.get(
        "pipeline_sha256"
    ):
        raise services['PipelineError'](f"{label}: historical recipe launcher is inconsistent")

    local_store = expected_record.get("local_store")
    snapshot_references = (
        local_store.get("recipe_snapshots")
        if isinstance(local_store, dict)
        else None
    )
    snapshot_reference = (
        snapshot_references.get(architecture)
        if isinstance(snapshot_references, dict)
        else None
    )
    if not isinstance(snapshot_reference, dict):
        raise services['PipelineError'](f"{label}: promoted recipe snapshot is missing")
    snapshot_path = services['require_canonical_store_entry'](
        snapshot_reference,
        "recipes",
        f"{label} recipe snapshot",
    )
    if snapshot_path.is_symlink():
        raise services['PipelineError'](f"{label}: promoted recipe snapshot bytes are invalid")
    try:
        snapshot = services['verified_json_object'](
            snapshot_path,
            snapshot_reference.get("sha256"),
            f"{label} promoted recipe snapshot",
        )
    except services['PipelineError'] as exc:
        raise services['PipelineError'](
            f"{label}: promoted recipe snapshot bytes are invalid"
        ) from exc
    snapshot_record = record
    if expected_record.get("source_candidate") is not None:
        snapshot_record = services['copy'].deepcopy(record)
        snapshot_record["source_candidate"] = services['copy'].deepcopy(
            expected_record["source_candidate"]
        )
    snapshot_errors = services['_verify_historical_recipe_snapshot'](
        snapshot_path,
        snapshot_record,
        label,
        snapshot=snapshot,
    )
    if snapshot_errors:
        raise services['PipelineError']("\n- ".join(snapshot_errors))

    source = record.get("source")
    if not isinstance(build, dict) or not isinstance(source, dict):
        raise services['PipelineError'](f"{label}: historical build/source contract is invalid")
    source_candidate_projection = services['source_candidate_record_contract_projection'](
        expected_record.get("source_candidate"),
        core_id=core_id,
        recorded_source=source,
        recorded_recipe=record.get("recipe"),
        recipe_snapshot=snapshot,
    )
    contract_source = services['_source_candidate_contract_source_for_guard'](
        source,
        source_candidate_projection,
    )
    contract_build = services['_source_candidate_contract_build_for_guard'](
        build,
        source_candidate_projection,
    )
    contract_source_commit = contract_source.get("resolved_commit")
    if core_id == services['MAME2003_PLUS_CORE_ID'] and (
        not services['mame2003_plus_golden_source_is_well_formed'](core_id, contract_source)
        or not services['mame2003_plus_golden_build_contract_is_well_formed'](
            contract_build,
            contract_source_commit,
            core_id,
            contract_source,
            architecture,
        )
    ):
        raise services['PipelineError'](f"{label}: MAME2003+ build/source contract is invalid")
    if core_id == services['FBNEO_CORE_ID'] and (
        not services['fbneo_golden_source_is_well_formed'](core_id, contract_source)
        or not services['fbneo_golden_build_contract_is_well_formed'](
            contract_build,
            contract_source_commit,
            core_id,
            contract_source,
            architecture,
        )
    ):
        raise services['PipelineError'](f"{label}: FBNeo build/source contract is invalid")
    if not services['compile_log_proves_definitions'](
        build_log_text,
        build.get("compile_definitions"),
        architecture,
    ):
        raise services['PipelineError'](f"{label}: compile-definition log proof failed")
    has_recipe_profile = "recipe_profile" in build
    if has_recipe_profile and (
        core_id != services['PICODRIVE_CORE_ID']
        or not services['picodrive_golden_build_contract_is_well_formed'](
            contract_build,
            contract_source_commit,
            core_id,
            contract_source,
            architecture,
        )
    ):
        raise services['PipelineError'](f"{label}: recipe-profile contract is invalid")
    if core_id == services['PICODRIVE_CORE_ID'] and not has_recipe_profile:
        raise services['PipelineError'](f"{label}: recipe-profile contract is missing")
    if "make_variables" in build and not services['make_variable_log_proves_contract'](
        build_log_text,
        build["make_variables"],
        architecture,
    ):
        raise services['PipelineError'](f"{label}: make-variable log proof failed")
    if "git_version" in build and not services['git_version_log_proves_contract'](
        build_log_text,
        build["git_version"],
        source.get("resolved_commit"),
        architecture,
    ):
        raise services['PipelineError'](f"{label}: Git-version log proof failed")
    log_contract = services['core_log_contract_for'](core_id)
    if log_contract is not None and not services['_registered_core_log_contract_proves'](
        build_log_text,
        core_id,
        architecture,
        source.get("resolved_commit"),
        source.get("tree"),
        source_candidate_projection=source_candidate_projection,
    ):
        raise services['PipelineError'](f"{label}: {log_contract.failure_message}")
    if build.get("driver") == "direct-cmake":
        files = snapshot.get("files")
        catalog_path = recipe.get("catalog_path")
        try:
            historical_catalog = services['json'].loads(files[catalog_path]["text"])
            historical_spec = historical_catalog["cores"][core_id]
        except (KeyError, TypeError, services['json'].JSONDecodeError) as exc:
            raise services['PipelineError'](
                f"{label}: historical direct-CMake recipe is invalid"
            ) from exc
        if not services['direct_cmake_log_proves_contract'](
            build_log_text,
            historical_spec,
            architecture,
        ):
            raise services['PipelineError'](f"{label}: direct-CMake log proof failed")
    metadata_replacement = build.get("metadata_replacement")
    if metadata_replacement is not None and not (
        services['metadata_replacement_log_proves_contract'](
            build_log_text,
            metadata_replacement,
        )
    ):
        raise services['PipelineError'](f"{label}: metadata-replacement log proof failed")


def _validate_compatibility_e2e_run(
    e2e_path: Path,
    core_id: str,
    expected_build_records: dict[str, dict],
    *,
    services: PinLifecycleServices,
) -> dict:
    """Validate canonical evidence against frozen recipes and current log gates."""

    try:
        compatibility_evidence_bytes = e2e_path.read_bytes()
    except OSError as exc:
        raise services['PipelineError'](f"cannot load compatibility E2E record: {exc}") from exc
    compatibility_evidence = services['decode_json_object'](
        compatibility_evidence_bytes, e2e_path
    )
    if not services['runner_evidence_is_well_formed'](compatibility_evidence.get("runner")):
        raise services['PipelineError']("compatibility E2E runner evidence is invalid")
    services['validate_bound_host_telemetry'](compatibility_evidence, e2e_path)

    expected_targets = set(expected_build_records)
    package_directories = {
        architecture: services['ARCH_LAYOUT'][architecture]["package_directory"]
        for architecture in expected_targets
        if architecture in services['ARCH_LAYOUT']
    }

    return services['validate_core_e2e_run'](
        e2e_path,
        core_id,
        repository_root=services['ROOT'],
        runs_root=services['DEFAULT_RUNS'],
        expected_targets=expected_targets,
        package_directories=package_directories,
        expected_build_records=expected_build_records,
        artifact_validator=services['_validate_artifact_bytes'],
        build_record_validator=services['_validate_canonical_compatibility_build_record'],
        content_hasher=services['e2e_content_sha256'],
        runner_validator=services['runner_evidence_is_well_formed'],
        evidence_document=compatibility_evidence,
    )


def _validate_historical_pin_set_document(
    document: dict,
    *, services: PinLifecycleServices, **kwargs,
) -> dict:
    """Deeply validate a pin using its frozen recipe rather than current policy."""

    return services['_validate_pin_set_document'](
        document,
        historical_recipe_proofs=True,
        **kwargs,
    )


def validate_core_compatibility_document(
    document: dict,
    *,
    document_path: Path | None = None,
    repository_root: Path,
    verify_pin: bool = True,
    services: PinLifecycleServices,
) -> dict:
    """Inject the pipeline's deep pin and E2E validators."""

    return services['_validate_core_compatibility_document'](
        document,
        document_path=document_path,
        repository_root=repository_root,
        verify_pin=verify_pin,
        pin_validator=services['_validate_historical_pin_set_document'],
        e2e_validator=services['_validate_compatibility_e2e_run'],
    )


def compose_pin_set(
    *,
    pin_id: str,
    core_ids: list[str],
    source_paths: list[Path],
    output_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    services: PinLifecycleServices,
) -> dict:
    """Create one canonical parentless pin for one individual core."""

    validation_context = services['_PinValidationContext']()
    catalog = services['load_catalog'](catalog_path)
    if (
        not isinstance(core_ids, list)
        or len(core_ids) != 1
        or not isinstance(core_ids[0], str)
        or services['CORE_ID_RE'].fullmatch(core_ids[0]) is None
        or not isinstance(source_paths, list)
        or len(source_paths) != 1
        or not isinstance(source_paths[0], services['Path'])
        or not isinstance(output_path, services['Path'])
        or not isinstance(pin_id, str)
    ):
        raise services['PipelineError'](
            "active pin composition requires exactly one core and one source"
        )
    core_id = core_ids[0]
    source_path = services['require_lexical_repository_path'](
        source_paths[0], services['DEFAULT_NIGHTLIES'], "individual pin source golden"
    )
    output_path = services['require_lexical_repository_path'](
        output_path, services['DEFAULT_PIN_SET_DIR'], "individual pin output"
    )
    source, source_file_sha256 = services['snapshot_json_file'](
        source_path,
        "individual pin source golden",
        validation_context,
    )
    report = services['validate_golden_document'](source)
    if report["status"] == "valid":
        report["errors"].extend(services['_verify_local_store'](source, validation_context))
    if report["errors"]:
        raise services['PipelineError'](
            f"golden source is invalid ({source_path}):\n- "
            + "\n- ".join(report["errors"])
        )
    services['require_active_core_golden'](source, core_id)
    build_goldens = source.get("build_goldens")
    if not isinstance(build_goldens, dict) or set(build_goldens) != {core_id}:
        raise services['PipelineError'](
            "active pin composition requires an exact one-core nightly golden"
        )
    selection = services['complete_core_bundle'](source, core_id)
    if selection is None:
        raise services['PipelineError'](f"no complete build-golden bundle is available for {core_id}")
    services['_require_catalog_bound_source_candidate_selection'](
        catalog,
        selection,
        core_id=core_id,
        operation="pin composition",
        catalog_path=catalog_path,
    )
    semantic_id = services['individual_core_semantic_id'](core_id, selection)
    if pin_id != semantic_id:
        raise services['PipelineError'](f"individual pin ID must be semantic ID {semantic_id}")
    expected_source = (services['DEFAULT_NIGHTLIES'] / semantic_id / "golden.json").resolve()
    expected_output = (services['DEFAULT_PIN_SET_DIR'] / f"{semantic_id}.json").resolve()
    if source_path != expected_source:
        raise services['PipelineError'](
            "individual pin source must be its exact semantic nightly golden"
        )
    if output_path != expected_output:
        raise services['PipelineError'](
            f"individual pin output must be pins/core-sets/{semantic_id}.json"
        )
    cores = {
        core_id: {
            "decision": "select_source",
            "source_index": 0,
            "selection": selection,
        }
    }
    candidate_pin = {"scope": [core_id], "cores": cores}
    services['require_pin_sources_eligible'](catalog, candidate_pin)
    document = {
        "$schema": "../../manifests/core-set.schema.json",
        "schema_version": 1,
        "pin_id": pin_id,
        # The immutable pin derives its timestamp from its first immutable
        # source so recreating lost bytes cannot change a semantic ID's file.
        "created_at": source.get("updated_at"),
        "local_only": True,
        "publication": "disabled",
        "scope": [core_id],
        "parent": None,
        "sources": [
            services['golden_source_reference'](
                source_path,
                source,
                file_sha256=source_file_sha256,
            )
        ],
        "selection_policy": services['copy'].deepcopy(services['PIN_SELECTION_POLICY']),
        "cores": cores,
        "summary": {
            "core_count": 1,
            "retained_parent_count": 0,
            "selected_source_count": 1,
        },
    }
    document["content_sha256"] = services['pin_set_content_sha256'](document)
    report = services['_validate_pin_set_document'](
        document,
        verify_store=True,
        verify_sources=True,
        document_path=output_path,
        _validation_context=validation_context,
    )
    if report["status"] != "valid":
        raise services['PipelineError']("composed pin set is invalid:\n- " + "\n- ".join(report["errors"]))
    services['atomic_create_json'](output_path, document)
    return document

