"""Full-release planning, worker, conversion, and sealing commands.

The launcher remains the composition root. Every invocation captures a fresh,
filtered namespace so legacy monkeypatch seams and nested handler calls retain
their original behavior without a reverse import.
"""

from __future__ import annotations

import argparse
import builtins
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class FullReleaseCommandServices:
    """Call-time launcher namespace consumed by this command domain."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "FullReleaseCommandServices":
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
        'DEFAULT_CATALOG',
        'DEFAULT_FULL_RELEASE_CANDIDATES',
        'DEFAULT_FULL_RELEASE_PLANS',
        'DEFAULT_FULL_RELEASE_RESULTS',
        'DEFAULT_RELEASE_OVERLAYS',
        'DEFAULT_RELEASE_OVERLAY_INPUT',
        'DEFAULT_RUNS',
        'PipelineError',
        'ROOT',
        '_canonical_full_release_plan',
        'actions_matrix_for_plan',
        'construct_tracked_release_plan',
        'json',
        'load_json',
        'manifest_lock',
        'prepare_release_group_source_graph',
        'record_validated_release_result',
        'release_repository_services',
        'release_worker_services',
        'require_lexical_repository_path',
        'seal_release_candidate',
        'validate_plan_against_repository',
        'validate_release_plan',
        'write_release_plan',
    }
)


_BUILTIN_BINDINGS = frozenset(
    {
        'dict',
        'getattr',
        'print',
        'str',
    }
)


def _canonical_full_release_plan(path: Path, *, services: FullReleaseCommandServices) -> tuple[Path, dict]:
    DEFAULT_FULL_RELEASE_PLANS = services['DEFAULT_FULL_RELEASE_PLANS']
    PipelineError = services['PipelineError']
    load_json = services['load_json']
    require_lexical_repository_path = services['require_lexical_repository_path']
    validate_release_plan = services['validate_release_plan']

    plan_path = require_lexical_repository_path(
        path,
        DEFAULT_FULL_RELEASE_PLANS,
        "full-release plan",
    )
    plan = validate_release_plan(load_json(plan_path))
    expected = (DEFAULT_FULL_RELEASE_PLANS / f"{plan['candidate_id']}.json").resolve()
    if plan_path != expected:
        raise PipelineError(
            "full-release plan must be "
            f".local-e2e/release-plans/{plan['candidate_id']}.json"
        )
    return plan_path, plan

def cmd_prepare_release_source_graph(args: argparse.Namespace, *, services: FullReleaseCommandServices) -> int:
    """Prepare exact full-history ancestry evidence before release work."""
    DEFAULT_CATALOG = services['DEFAULT_CATALOG']
    PipelineError = services['PipelineError']
    getattr = services['getattr']
    json = services['json']
    prepare_release_group_source_graph = services['prepare_release_group_source_graph']
    print = services['print']


    if args.catalog.resolve() != DEFAULT_CATALOG.resolve():
        raise PipelineError(
            "release source-graph preparation requires the canonical catalog"
        )
    report = prepare_release_group_source_graph(
        args.group_tag,
        core_id=getattr(args, "core", None),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0

def cmd_convert_release_overlay(args: argparse.Namespace, *, services: FullReleaseCommandServices) -> int:
    """Convert one run-bound seal only after trusted repository reconstruction."""
    DEFAULT_CATALOG = services['DEFAULT_CATALOG']
    DEFAULT_RELEASE_OVERLAYS = services['DEFAULT_RELEASE_OVERLAYS']
    DEFAULT_RELEASE_OVERLAY_INPUT = services['DEFAULT_RELEASE_OVERLAY_INPUT']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    dict = services['dict']
    json = services['json']
    print = services['print']
    release_repository_services = services['release_repository_services']
    require_lexical_repository_path = services['require_lexical_repository_path']
    str = services['str']
    validate_plan_against_repository = services['validate_plan_against_repository']


    if args.catalog.resolve() != DEFAULT_CATALOG.resolve():
        raise PipelineError("release overlay conversion requires the canonical catalog")
    expected_candidate_dir = (
        DEFAULT_RELEASE_OVERLAY_INPUT
        / f"release-candidate-{args.coordinator_run_id}-{args.coordinator_run_attempt}"
    ).resolve()
    candidate_dir = require_lexical_repository_path(
        args.candidate_dir,
        DEFAULT_RELEASE_OVERLAY_INPUT,
        "release overlay candidate input",
    )
    if candidate_dir != expected_candidate_dir:
        raise PipelineError(
            "release overlay candidate input must be "
            ".local-e2e/overlay-input/release-candidate-"
            f"{args.coordinator_run_id}-{args.coordinator_run_attempt}"
        )
    expected_output_dir = (
        DEFAULT_RELEASE_OVERLAYS
        / f"release-overlay-{args.coordinator_run_id}-{args.coordinator_run_attempt}"
    ).resolve()
    output_dir = require_lexical_repository_path(
        args.output_dir,
        DEFAULT_RELEASE_OVERLAYS,
        "release overlay output",
    )
    if output_dir != expected_output_dir:
        raise PipelineError(
            "release overlay output must be "
            ".local-e2e/overlays/release-overlay-"
            f"{args.coordinator_run_id}-{args.coordinator_run_attempt}"
        )

    def trusted_plan_validator(plan: Mapping[str, object]) -> Mapping[str, object]:
        return validate_plan_against_repository(
            dict(plan),
            repository_root=ROOT,
            catalog_path=args.catalog,
            services=release_repository_services(),
        )

    from release_overlay import OverlayError, build_overlay

    try:
        manifest = build_overlay(
            candidate_dir,
            output_dir,
            trusted_plan_validator=trusted_plan_validator,
            expected_repository_head=args.expected_repository_head,
            expected_coordinator_run_id=args.coordinator_run_id,
            expected_coordinator_run_attempt=args.coordinator_run_attempt,
        )
    except OverlayError as exc:
        raise PipelineError(str(exc)) from exc
    print(
        json.dumps(
            {
                "status": "converted",
                "candidate_id": manifest["source"]["candidate_id"],
                "overlay": str(
                    (output_dir / manifest["overlay"]["path"]).relative_to(ROOT)
                ),
                "sha256": manifest["overlay"]["sha256"],
                "member_count": manifest["overlay"]["member_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def cmd_plan_release(args: argparse.Namespace, *, services: FullReleaseCommandServices) -> int:
    DEFAULT_FULL_RELEASE_PLANS = services['DEFAULT_FULL_RELEASE_PLANS']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    construct_tracked_release_plan = services['construct_tracked_release_plan']
    getattr = services['getattr']
    json = services['json']
    manifest_lock = services['manifest_lock']
    print = services['print']
    release_repository_services = services['release_repository_services']
    require_lexical_repository_path = services['require_lexical_repository_path']
    str = services['str']
    write_release_plan = services['write_release_plan']

    group_tag = getattr(args, "group_tag", None)
    scope = (
        "track-group"
        if group_tag is not None
        else args.scope if args.scope is not None else "explicit"
    )
    services = release_repository_services()
    plan = construct_tracked_release_plan(
        candidate_id=args.candidate_id,
        scope=scope,
        requested_cores=args.core,
        repository_root=ROOT,
        catalog_path=args.catalog,
        services=services,
        group_tag=group_tag,
    )
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_FULL_RELEASE_PLANS,
        "full-release plan output",
    )
    expected = (
        DEFAULT_FULL_RELEASE_PLANS / f"{plan['candidate_id']}.json"
    ).resolve()
    if output_path != expected:
        raise PipelineError(
            "full-release plan output must be "
            f".local-e2e/release-plans/{plan['candidate_id']}.json"
        )
    with manifest_lock(output_path):
        write_release_plan(plan=plan, output_path=output_path)
    print(
        json.dumps(
            {
                "status": "planned",
                "candidate_id": plan["candidate_id"],
                "scope": plan["scope"],
                "group_tag": group_tag,
                "core_count": plan["summary"]["core_count"],
                "target_count": plan["summary"]["target_count"],
                "content_sha256": plan["content_sha256"],
                "path": str(output_path.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def cmd_release_matrix(args: argparse.Namespace, *, services: FullReleaseCommandServices) -> int:
    """Print the exact one-core Actions matrix for a current release plan."""
    ROOT = services['ROOT']
    _canonical_full_release_plan = services['_canonical_full_release_plan']
    actions_matrix_for_plan = services['actions_matrix_for_plan']
    json = services['json']
    print = services['print']
    release_repository_services = services['release_repository_services']
    validate_plan_against_repository = services['validate_plan_against_repository']


    _, loaded_plan = _canonical_full_release_plan(args.plan)
    plan = validate_plan_against_repository(
        loaded_plan,
        repository_root=ROOT,
        catalog_path=args.catalog,
        services=release_repository_services(),
    )
    print(
        json.dumps(
            actions_matrix_for_plan(plan),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0

def cmd_record_release_result(args: argparse.Namespace, *, services: FullReleaseCommandServices) -> int:
    DEFAULT_FULL_RELEASE_RESULTS = services['DEFAULT_FULL_RELEASE_RESULTS']
    DEFAULT_RUNS = services['DEFAULT_RUNS']
    ROOT = services['ROOT']
    _canonical_full_release_plan = services['_canonical_full_release_plan']
    getattr = services['getattr']
    json = services['json']
    manifest_lock = services['manifest_lock']
    print = services['print']
    record_validated_release_result = services['record_validated_release_result']
    release_repository_services = services['release_repository_services']
    release_worker_services = services['release_worker_services']
    require_lexical_repository_path = services['require_lexical_repository_path']
    str = services['str']

    plan_path, _preflight_plan = _canonical_full_release_plan(args.plan)
    e2e_path = require_lexical_repository_path(
        args.e2e_record,
        DEFAULT_RUNS,
        "full-release worker E2E record",
    )
    output_dir = require_lexical_repository_path(
        args.output_dir,
        DEFAULT_FULL_RELEASE_RESULTS,
        "full-release worker output",
    )
    with manifest_lock(output_dir):
        result, validated_runner = record_validated_release_result(
            plan_path=plan_path,
            core_id=args.core,
            e2e_path=e2e_path,
            results_root=DEFAULT_FULL_RELEASE_RESULTS,
            output_dir=output_dir,
            repository_root=ROOT,
            catalog_path=args.catalog,
            repository_services=release_repository_services(),
            worker_services=release_worker_services(),
            expected_group_tag=getattr(args, "group_tag", None),
        )
    print(
        json.dumps(
            {
                "status": "recorded",
                "candidate_id": result["candidate_id"],
                "core_id": result["core_id"],
                "runner_profile": validated_runner,
                "content_sha256": result["content_sha256"],
                "path": str(output_dir.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0

def cmd_seal_release(args: argparse.Namespace, *, services: FullReleaseCommandServices) -> int:
    DEFAULT_FULL_RELEASE_CANDIDATES = services['DEFAULT_FULL_RELEASE_CANDIDATES']
    DEFAULT_FULL_RELEASE_RESULTS = services['DEFAULT_FULL_RELEASE_RESULTS']
    PipelineError = services['PipelineError']
    ROOT = services['ROOT']
    _canonical_full_release_plan = services['_canonical_full_release_plan']
    json = services['json']
    manifest_lock = services['manifest_lock']
    print = services['print']
    release_repository_services = services['release_repository_services']
    require_lexical_repository_path = services['require_lexical_repository_path']
    seal_release_candidate = services['seal_release_candidate']
    str = services['str']
    validate_plan_against_repository = services['validate_plan_against_repository']

    plan_path, loaded_plan = _canonical_full_release_plan(args.plan)
    plan = validate_plan_against_repository(
        loaded_plan,
        repository_root=ROOT,
        catalog_path=args.catalog,
        services=release_repository_services(),
    )
    results_root = require_lexical_repository_path(
        args.results_root,
        DEFAULT_FULL_RELEASE_RESULTS,
        "full-release result set",
    )
    expected_results = (
        DEFAULT_FULL_RELEASE_RESULTS
        / plan["candidate_id"]
        / args.runner_profile
    ).resolve()
    if results_root != expected_results:
        raise PipelineError(
            "full-release results root must be "
            ".local-e2e/release-results/"
            f"{plan['candidate_id']}/{args.runner_profile}"
        )
    output_dir = require_lexical_repository_path(
        args.output_dir,
        DEFAULT_FULL_RELEASE_CANDIDATES,
        "sealed full-release output",
    )
    expected_output = (
        DEFAULT_FULL_RELEASE_CANDIDATES
        / plan["candidate_id"]
        / args.runner_profile
    ).resolve()
    if output_dir != expected_output:
        raise PipelineError(
            "sealed full-release output must be "
            ".local-e2e/release-candidates/"
            f"{plan['candidate_id']}/{args.runner_profile}"
        )
    with manifest_lock(output_dir):
        candidate = seal_release_candidate(
            plan=plan,
            plan_path=plan_path,
            results_root=results_root,
            output_dir=output_dir,
            runner_selector=args.runner_profile,
        )
    print(
        json.dumps(
            {
                "status": "sealed",
                "candidate_id": candidate["candidate_id"],
                "runner_profile": args.runner_profile,
                "asset_count": candidate["summary"]["asset_count"],
                "asset_set_sha256": candidate["asset_set_sha256"],
                "content_sha256": candidate["content_sha256"],
                "path": str(output_dir.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0
