"""Catalog, build, and end-to-end command handlers.

The launcher remains the composition root. Every invocation captures a fresh,
filtered namespace so legacy monkeypatch seams and nested handler calls retain
their original behavior without a reverse import.
"""

from __future__ import annotations

import argparse
import builtins
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..runtime import HostExecutionProfile


@dataclass(frozen=True, slots=True)
class CatalogBuildServices:
    """Call-time launcher namespace consumed by this command domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "CatalogBuildServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"missing pipeline services: {names}")
        captured = {name: namespace[name] for name in _REQUIRED_BINDINGS}
        captured.update(
            {
                name: namespace.get(name, getattr(builtins, name))
                for name in _BUILTIN_BINDINGS
            }
        )
        return cls(MappingProxyType(captured))


def required_binding_names() -> frozenset[str]:
    """Return the exact launcher bindings consumed by this leaf."""

    return _REQUIRED_BINDINGS


def builtin_binding_names() -> frozenset[str]:
    """Return builtins captured dynamically to preserve launcher overrides."""

    return _BUILTIN_BINDINGS


_REQUIRED_BINDINGS = frozenset(
    {
        'CHIPSETS',
        'CORE_TRACKS',
        'Counter',
        'DEFAULT_CATALOG',
        'DEFAULT_CHIPSET_TUNINGS',
        'DEFAULT_CORE_TRACKS',
        'DEFAULT_NIGHTLIES',
        'DEFAULT_SPRUCE_BRANCH_BASES',
        'DEFAULT_SPRUCE_RELEASE_ROSTER',
        'DEFAULT_STORE',
        'PipelineError',
        'ROOT',
        'RunnerProfileError',
        'RunnerRequest',
        'TRACK_MARKERS',
        '_validate_source_candidate_execution_catalog',
        'argparse',
        'atomic_create_json',
        'atomic_write_json',
        'audit_workflows',
        'build_sidecar_document',
        'candidate_golden_id_is_well_formed',
        'cmd_e2e',
        'container_build_script',
        'copy',
        'core_track_source_ancestry_verifier',
        'e2e_content_sha256',
        'git_head',
        'group_execution_spec',
        'imported_core_baseline',
        'json',
        'load_authoritative_core_pin_index',
        'load_catalog',
        'load_catalog_compatibility_coverage',
        'load_core_track_source_registry_index',
        'load_json',
        'os',
        'package_e2e_core',
        'perform_build',
        'prepare_host_execution_context',
        'prepare_source_candidate_catalog',
        'prepare_source_snapshot_catalog_rebase',
        'render_source_candidate_build_contract',
        'require_catalog_cores_eligible',
        'require_contained',
        'require_lexical_repository_path',
        'resolve_core_group_build_selection',
        'resolve_runner_context',
        'resolve_tuning_candidate_selection',
        'run',
        'runner_evidence',
        'safe_child',
        'sha256_file',
        'source_aware_candidate_contract_is_registered',
        'store_file',
        'time',
        'validate_catalog',
        'validate_chipset_tunings',
        'validate_core_tracks',
        'validate_golden_document',
        'verify_local_store',
        'write_sidecar',
    }
)


_BUILTIN_BINDINGS = frozenset(
    {
        'all',
        'any',
        'bool',
        'getattr',
        'isinstance',
        'len',
        'print',
        'set',
        'sorted',
        'str',
        'sum',
    }
)


def cmd_catalog_check(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    CHIPSETS = services['CHIPSETS']
    CORE_TRACKS = services['CORE_TRACKS']
    DEFAULT_CATALOG = services['DEFAULT_CATALOG']
    DEFAULT_CHIPSET_TUNINGS = services['DEFAULT_CHIPSET_TUNINGS']
    DEFAULT_CORE_TRACKS = services['DEFAULT_CORE_TRACKS']
    DEFAULT_SPRUCE_BRANCH_BASES = services['DEFAULT_SPRUCE_BRANCH_BASES']
    DEFAULT_SPRUCE_RELEASE_ROSTER = services['DEFAULT_SPRUCE_RELEASE_ROSTER']
    ROOT = services['ROOT']
    TRACK_MARKERS = services['TRACK_MARKERS']
    core_track_source_ancestry_verifier = services['core_track_source_ancestry_verifier']
    json = services['json']
    len = services['len']
    load_authoritative_core_pin_index = services['load_authoritative_core_pin_index']
    load_catalog = services['load_catalog']
    load_catalog_compatibility_coverage = services['load_catalog_compatibility_coverage']
    load_core_track_source_registry_index = services['load_core_track_source_registry_index']
    load_json = services['load_json']
    print = services['print']
    sorted = services['sorted']
    validate_chipset_tunings = services['validate_chipset_tunings']
    validate_core_tracks = services['validate_core_tracks']

    catalog = load_catalog(args.catalog)
    report = {
        "status": "valid",
        "catalog_cores": sorted(catalog["cores"]),
        "publication": catalog["policy"]["publication"],
    }
    if args.catalog.resolve() == DEFAULT_CATALOG.resolve():
        tunings = validate_chipset_tunings(load_json(DEFAULT_CHIPSET_TUNINGS))
        main_release_roster = load_json(DEFAULT_SPRUCE_RELEASE_ROSTER)
        spruce_branch_bases = load_json(DEFAULT_SPRUCE_BRANCH_BASES)
        tracks = validate_core_tracks(
            load_json(DEFAULT_CORE_TRACKS),
            catalog=catalog,
            pin_index=load_authoritative_core_pin_index(),
            tunings=tunings,
            main_release_roster=main_release_roster,
            spruce_branch_bases=spruce_branch_bases,
            source_registry_index=load_core_track_source_registry_index(ROOT),
            source_ancestry_verifier=core_track_source_ancestry_verifier(),
        )
        report.update(
            {
                "core_track_selection_model": tracks["selection_model"],
                "core_track_content_sha256": tracks["content_sha256"],
                "chipset_tuning_content_sha256": tunings["content_sha256"],
                "core_track_group_tag_count": (
                    len(CORE_TRACKS) * len(TRACK_MARKERS) * len(CHIPSETS)
                ),
                "chipset_tuning_profiles": sorted(tunings["profiles"]),
                "main_spruce_release_version": main_release_roster["release"][
                    "version"
                ],
                "main_spruce_release_commit": main_release_roster["release"][
                    "commit"
                ],
                "main_spruce_release_roster_content_sha256": (
                    main_release_roster["content_sha256"]
                ),
                "main_spruce_release_correlation_model": (
                    main_release_roster["correlation_model"]
                ),
                "spruce_branch_bases_content_sha256": (
                    spruce_branch_bases["content_sha256"]
                ),
                "spruce_main_branch_commit": spruce_branch_bases["bases"]
                ["spruce-main"]["branch"]["commit"],
                "spruce_development_branch_commit": spruce_branch_bases[
                    "bases"
                ]["spruce-development"]["branch"]["commit"],
            }
        )
        report.update(
            load_catalog_compatibility_coverage(
                catalog=catalog,
                repository_root=ROOT,
            )
        )
    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def cmd_core_source_candidate_rebase(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    """Bind one stale remote-ref snapshot to the current core recipe."""
    ROOT = services['ROOT']
    json = services['json']
    prepare_source_snapshot_catalog_rebase = services['prepare_source_snapshot_catalog_rebase']
    print = services['print']
    source_aware_candidate_contract_is_registered = services['source_aware_candidate_contract_is_registered']
    validate_catalog = services['validate_catalog']


    result = prepare_source_snapshot_catalog_rebase(
        repository_root=ROOT,
        catalog_path=args.catalog,
        snapshot_path=args.snapshot,
        core_id=args.core,
        catalog_validator=validate_catalog,
        source_aware_contract_resolver=(
            source_aware_candidate_contract_is_registered
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_core_source_candidate_prepare(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    """Create one ignored catalog for an exact, not-yet-pinned source."""
    ROOT = services['ROOT']
    _validate_source_candidate_execution_catalog = services['_validate_source_candidate_execution_catalog']
    json = services['json']
    prepare_source_candidate_catalog = services['prepare_source_candidate_catalog']
    print = services['print']
    render_source_candidate_build_contract = services['render_source_candidate_build_contract']
    require_catalog_cores_eligible = services['require_catalog_cores_eligible']
    source_aware_candidate_contract_is_registered = services['source_aware_candidate_contract_is_registered']
    validate_catalog = services['validate_catalog']


    result = prepare_source_candidate_catalog(
        repository_root=ROOT,
        catalog_path=args.catalog,
        snapshot_path=args.snapshot,
        core_id=args.core,
        catalog_rebase_path=args.catalog_rebase,
        catalog_validator=validate_catalog,
        candidate_catalog_validator=_validate_source_candidate_execution_catalog,
        eligibility_validator=require_catalog_cores_eligible,
        build_renderer=render_source_candidate_build_contract,
        source_aware_contract_resolver=(
            source_aware_candidate_contract_is_registered
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

def cmd_audit(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    atomic_write_json = services['atomic_write_json']
    audit_workflows = services['audit_workflows']
    json = services['json']
    load_catalog = services['load_catalog']
    print = services['print']

    catalog = load_catalog(args.catalog)
    report = audit_workflows(catalog)
    if args.output:
        atomic_write_json(args.output, report)
    summary = {key: value for key, value in report.items() if key != "workflows"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return (
        1
        if report["missing_catalog_workflows"]
        or report["active_aggregate_workflows"]
        or report["invalid_catalog_workflows"]
        or report["release_orchestration"].get("status") != "valid"
        else 0
    )

def cmd_import_golden(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    DEFAULT_NIGHTLIES = services['DEFAULT_NIGHTLIES']
    PipelineError = services['PipelineError']
    atomic_create_json = services['atomic_create_json']
    candidate_golden_id_is_well_formed = services['candidate_golden_id_is_well_formed']
    imported_core_baseline = services['imported_core_baseline']
    json = services['json']
    len = services['len']
    print = services['print']
    require_lexical_repository_path = services['require_lexical_repository_path']
    validate_golden_document = services['validate_golden_document']

    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_NIGHTLIES,
        "individual imported golden output",
    )
    output_relative = output_path.relative_to(DEFAULT_NIGHTLIES.resolve())
    candidate_name = output_relative.parts[0] if output_relative.parts else ""
    if (
        len(output_relative.parts) != 2
        or output_relative.parts[1] != "golden.json"
        or not candidate_golden_id_is_well_formed(args.core, candidate_name)
    ):
        raise PipelineError(
            "individual imported golden output must be "
            "<core>-candidate-<label>/golden.json"
        )
    document = imported_core_baseline(
        args.spruceos,
        args.core,
        output_relative.parts[0],
    )
    report = validate_golden_document(document)
    missing_baseline_error = f"{args.core}: no valid imported artifact"
    validation_errors = report["errors"]
    tolerated_missing_baseline = (
        args.allow_missing
        and validation_errors == [missing_baseline_error]
        and document["summary"]["cores_without_valid_artifacts"] == [args.core]
    )
    if report["status"] != "valid" and not tolerated_missing_baseline:
        raise PipelineError(
            "individual imported golden is invalid:\n- "
            + "\n- ".join(validation_errors)
        )
    atomic_create_json(output_path, document)
    print(json.dumps(document["summary"], indent=2, sort_keys=True))
    return 0

def cmd_validate_golden(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    json = services['json']
    load_json = services['load_json']
    print = services['print']
    validate_golden_document = services['validate_golden_document']
    verify_local_store = services['verify_local_store']

    document = load_json(args.golden)
    report = validate_golden_document(document, args.spruceos if args.verify_files else None)
    if args.verify_store:
        store_errors = verify_local_store(document)
        report["errors"].extend(store_errors)
        report["local_store"] = "valid" if not store_errors else "invalid"
        if store_errors:
            report["status"] = "invalid"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1

def cmd_build(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    load_catalog = services['load_catalog']
    perform_build = services['perform_build']

    catalog = load_catalog(args.catalog)
    record = perform_build(
        catalog_path=args.catalog,
        catalog=catalog,
        core_id=args.core,
        arch=args.arch,
        output_dir=args.output,
    )
    return 0 if record["result"] == "passed" else 1

def cmd_build_core(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    """Build every catalog target and package exactly one selected core."""
    argparse = services['argparse']
    cmd_e2e = services['cmd_e2e']
    getattr = services['getattr']


    return cmd_e2e(
        argparse.Namespace(
            catalog=args.catalog,
            runner_profile=args.runner_profile,
            core=args.core,
            group_tag=getattr(args, "group_tag", None),
            arch=None,
            run_id=args.run_id,
            output_root=args.output_root,
            fail_fast=True,
        )
    )

def cmd_e2e(args: argparse.Namespace, *, services: CatalogBuildServices) -> int:
    Counter = services['Counter']
    DEFAULT_STORE = services['DEFAULT_STORE']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    RunnerProfileError = services['RunnerProfileError']
    RunnerRequest = services['RunnerRequest']
    all = services['all']
    any = services['any']
    atomic_write_json = services['atomic_write_json']
    audit_workflows = services['audit_workflows']
    bool = services['bool']
    build_sidecar_document = services['build_sidecar_document']
    container_build_script = services['container_build_script']
    copy = services['copy']
    e2e_content_sha256 = services['e2e_content_sha256']
    getattr = services['getattr']
    git_head = services['git_head']
    group_execution_spec = services['group_execution_spec']
    isinstance = services['isinstance']
    json = services['json']
    len = services['len']
    load_catalog = services['load_catalog']
    os = services['os']
    package_e2e_core = services['package_e2e_core']
    perform_build = services['perform_build']
    prepare_host_execution_context = services['prepare_host_execution_context']
    print = services['print']
    require_catalog_cores_eligible = services['require_catalog_cores_eligible']
    require_contained = services['require_contained']
    resolve_core_group_build_selection = services['resolve_core_group_build_selection']
    resolve_runner_context = services['resolve_runner_context']
    resolve_tuning_candidate_selection = services['resolve_tuning_candidate_selection']
    run = services['run']
    runner_evidence = services['runner_evidence']
    safe_child = services['safe_child']
    set = services['set']
    sha256_file = services['sha256_file']
    sorted = services['sorted']
    store_file = services['store_file']
    str = services['str']
    sum = services['sum']
    time = services['time']
    write_sidecar = services['write_sidecar']

    catalog = load_catalog(args.catalog)
    if not isinstance(args.core, str) or not args.core:
        raise PipelineError("E2E requires exactly one --core")
    core_ids = [args.core]
    unknown = sorted(set(core_ids) - set(catalog["cores"]))
    if unknown:
        raise PipelineError(f"unknown core: {', '.join(unknown)}")
    requested_arches = args.arch
    group_tag = getattr(args, "group_tag", None)
    tuning_profile = getattr(args, "tuning_profile", None)
    if sum(value is not None for value in (group_tag, tuning_profile)) + bool(
        requested_arches
    ) > 1:
        raise PipelineError(
            "E2E --group-tag, --tuning-profile, and --arch are mutually exclusive"
        )
    if requested_arches:
        duplicate_arches = sorted(
            arch for arch, count in Counter(requested_arches).items() if count > 1
        )
        if duplicate_arches:
            raise PipelineError(
                "duplicate E2E architectures: " + ", ".join(duplicate_arches)
            )
    if group_tag is None:
        require_catalog_cores_eligible(catalog, core_ids)
    group_selection = (
        resolve_core_group_build_selection(
            group_tag=group_tag,
            catalog_path=args.catalog,
            catalog=catalog,
            core_id=args.core,
        )
        if group_tag is not None
        else None
    )
    tuning_selection = (
        resolve_tuning_candidate_selection(tuning_profile)
        if tuning_profile is not None
        else None
    )
    group_spec = (
        group_execution_spec(
            core_id=args.core,
            catalog_spec=catalog["cores"][args.core],
            group_selection=group_selection,
        )
        if group_selection is not None
        else None
    )
    if tuning_selection is not None:
        candidate_arch = tuning_selection["profile"]["architecture"]
        if candidate_arch not in catalog["cores"][args.core]["targets"]:
            raise PipelineError(
                "tuning candidate architecture is not enabled for this core"
            )
        # Fail closed before runner resolution or run-directory creation for
        # build drivers that cannot honestly prove typed compiler injection.
        container_build_script(
            args.core,
            candidate_arch,
            catalog["cores"][args.core],
            catalog["resolver"],
            tuning_selection["profile"]["profile_id"],
        )
    output_root = require_contained(args.output_root, ROOT / ".local-e2e", "E2E output root")
    repository_head = git_head(ROOT)
    repository_clean = not bool(
        run(
            ["git", "status", "--short", "--untracked-files=no"],
            cwd=ROOT,
        ).stdout
    )
    try:
        runner_context = resolve_runner_context(
            RunnerRequest(
                profile=args.runner_profile,
                repository_root=ROOT,
                output_root=output_root,
                run_id=args.run_id,
                repository_head=repository_head,
                repository_clean=repository_clean,
            ),
            env=os.environ,
        )
    except RunnerProfileError as exc:
        raise PipelineError(str(exc)) from exc
    execution_profile: HostExecutionProfile | None = None
    host_execution: dict | None = None
    telemetry_schema: dict | None = None
    if args.runner_profile in {"local", "github-actions-sim"}:
        execution_profile, host_execution, telemetry_schema = (
            prepare_host_execution_context(args.runner_profile)
        )
        if execution_profile.runner_identity() != {
            "profile": runner_context.profile,
            "mode": runner_context.mode,
            "backend": runner_context.backend,
        }:
            raise PipelineError(
                "resolved host execution profile differs from runner identity"
            )
    execution_spec = group_spec or catalog["cores"][args.core]
    if execution_profile is not None and (
        execution_spec["build"]["driver"]
        not in execution_profile.admissible_build_drivers
    ):
        raise PipelineError(
            "host-build telemetry does not yet admit build driver "
            + execution_spec["build"]["driver"]
        )
    run_id = runner_context.run_id
    run_root = runner_context.run_root
    if run_root.exists():
        raise PipelineError(f"refusing to reuse E2E run directory: {run_root}")
    run_root.mkdir(parents=True)
    audit = audit_workflows(catalog)
    records: list[dict] = []
    packages: list[dict] = []
    telemetry_builds: list[dict] = []
    package_duration_ns = 0
    for core_id in core_ids:
        core_records = []
        targets = (
            group_selection["selected_architectures"]
            if group_selection is not None
            else [tuning_selection["profile"]["architecture"]]
            if tuning_selection is not None
            else requested_arches or catalog["cores"][core_id]["targets"]
        )
        for arch in targets:
            record = perform_build(
                catalog_path=args.catalog,
                catalog=catalog,
                core_id=core_id,
                arch=arch,
                output_dir=run_root / core_id / arch,
                group_selection=group_selection,
                tuning_selection=tuning_selection,
                execution_profile=execution_profile,
                host_execution=host_execution,
                telemetry_sink=(
                    telemetry_builds if execution_profile is not None else None
                ),
            )
            records.append(record)
            core_records.append(record)
            if args.fail_fast and record["result"] != "passed":
                break
        package_started_ns = time.monotonic_ns()
        packages.append(
            package_e2e_core(
                run_root,
                core_id,
                core_records,
                group_spec or catalog["cores"][core_id],
                group_selection=group_selection,
                tuning_selection=tuning_selection,
            )
        )
        package_duration_ns += time.monotonic_ns() - package_started_ns
        if args.fail_fast and any(item["result"] != "passed" for item in core_records):
            break
    result = (
        "passed"
        if records
        and all(item["result"] == "passed" for item in records)
        and all(item["result"] == "packaged" for item in packages)
        else "failed"
    )
    telemetry_reference: dict | None = None
    if execution_profile is not None:
        assert telemetry_schema is not None
        if len(telemetry_builds) != len(records):
            raise PipelineError("host-build telemetry does not cover every build record")
        for telemetry_build in telemetry_builds:
            build_reference = telemetry_build["bindings"]["build_record"]
            run_record_path = safe_child(
                ROOT,
                build_reference["path"],
                "host-build telemetry run build record",
            )
            stored_record, stored_record_sha256 = store_file(
                DEFAULT_STORE, "build-records", run_record_path
            )
            if stored_record_sha256 != build_reference["file_sha256"]:
                raise PipelineError("host-build record changed during CAS capture")
            build_reference["path"] = stored_record.relative_to(ROOT).as_posix()
            log_reference = telemetry_build["bindings"]["outputs"]["build_log"]
            run_log_path = run_record_path.parent / "build.log"
            stored_log, stored_log_sha256 = store_file(
                DEFAULT_STORE, "logs", run_log_path
            )
            if stored_log_sha256 != log_reference["sha256"]:
                raise PipelineError("host-build log changed during CAS capture")
            log_reference["path"] = stored_log.relative_to(ROOT).as_posix()
        telemetry_document = build_sidecar_document(
            run_id=run_id,
            profile=execution_profile,
            builds=telemetry_builds,
            packages=copy.deepcopy(packages),
            package_duration_ns=package_duration_ns,
            result=result,
            telemetry_schema=telemetry_schema,
            repository_root=ROOT,
        )
        run_telemetry_reference = write_sidecar(
            run_root, telemetry_document, repository_root=ROOT
        )
        stored_telemetry, stored_telemetry_sha256 = store_file(
            DEFAULT_STORE,
            "host-build-telemetry",
            run_root / "telemetry.json",
        )
        if stored_telemetry_sha256 != run_telemetry_reference["file_sha256"]:
            raise PipelineError("host-build telemetry changed during CAS capture")
        telemetry_reference = {
            "path": stored_telemetry.relative_to(ROOT).as_posix(),
            "file_sha256": stored_telemetry_sha256,
            "content_sha256": telemetry_document["content_sha256"],
        }
    summary = {
        "schema_version": 2,
        "run_id": run_id,
        "local_only": True,
        "publication": "disabled",
        "runner": runner_evidence(
            runner_context, execution_profile, telemetry_reference
        ),
        "result": result,
        "workflow_audit": {
            "core_workflow_count": audit["core_workflow_count"],
            "masked_build_failure_paths": audit["masked_build_failure_paths"],
            "info_only_risk_workflows": audit["info_only_risk_workflows"],
            "shared_pipeline_workflows": audit["shared_pipeline_workflows"],
        },
        "builds": [
            {
                "core_id": record["core_id"],
                "architecture": record["architecture"],
                "result": record["result"],
                "record": str(
                    (run_root / record["core_id"] / record["architecture"] / "build-record.json").relative_to(ROOT)
                ),
                "record_sha256": sha256_file(
                    run_root / record["core_id"] / record["architecture"] / "build-record.json"
                ),
            }
            for record in records
        ],
        "packages": packages,
    }
    if group_selection is not None:
        summary["core_group"] = copy.deepcopy(group_selection)
    if tuning_selection is not None:
        summary["tuning_candidate"] = copy.deepcopy(tuning_selection)
    summary["content_sha256"] = e2e_content_sha256(summary)
    atomic_write_json(run_root / "e2e-record.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result == "passed" else 1
