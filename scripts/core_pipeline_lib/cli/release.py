"""Full-release command registration for the local-only core pipeline."""

from __future__ import annotations

import argparse

from .model import AppendUniqueAction, ParserConfig, ParserHandlers
from .inventory import CORE_TRACK_GROUP_TAG_CHOICES


def register_release_parsers(
    subparsers: argparse._SubParsersAction,
    *,
    handlers: ParserHandlers,
    config: ParserConfig,
) -> None:
    """Register deterministic plan, matrix, worker-result, and seal commands."""

    source_graph = subparsers.add_parser(
        "prepare-release-source-graph",
        help="prepare exact full-history Git ancestry for one release group",
    )
    source_graph.add_argument(
        "--group-tag",
        choices=CORE_TRACK_GROUP_TAG_CHOICES,
        required=True,
        help="exact track group whose validated pins determine the graph",
    )
    source_graph.add_argument(
        "--core",
        help=(
            "optional exact plan-row core scope; workers use this to prepare "
            "only that core's complete ancestry graph"
        ),
    )
    source_graph.set_defaults(handler=handlers.prepare_release_source_graph)

    overlay = subparsers.add_parser(
        "convert-release-overlay",
        help="convert one run-bound sealed candidate after repository reconstruction",
    )
    overlay.add_argument("--candidate-dir", type=config.path_value, required=True)
    overlay.add_argument("--output-dir", type=config.path_value, required=True)
    overlay.add_argument("--expected-repository-head", required=True)
    overlay.add_argument("--coordinator-run-id", required=True)
    overlay.add_argument("--coordinator-run-attempt", type=int, required=True)
    overlay.set_defaults(handler=handlers.convert_release_overlay)

    plan = subparsers.add_parser(
        "plan-release",
        help="create one deterministic local-only full-release plan",
    )
    plan.add_argument("--candidate-id", required=True)
    selector = plan.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--core",
        action=AppendUniqueAction,
        help="explicit core selector; repeat only for unique cores",
    )
    selector.add_argument(
        "--scope",
        choices=config.release_scope_choices,
        help="deterministic catalog/workflow release scope",
    )
    selector.add_argument(
        "--group-tag",
        choices=CORE_TRACK_GROUP_TAG_CHOICES,
        help=(
            "exact full-roster <track>-<stable|test>:<chipset> selector; "
            "mutually exclusive with legacy --core/--scope"
        ),
    )
    plan.add_argument("--output", type=config.path_value, required=True)
    plan.set_defaults(handler=handlers.plan_release)

    matrix = subparsers.add_parser(
        "release-matrix",
        help="project one validated release plan into an Actions matrix",
    )
    matrix.add_argument("--plan", type=config.path_value, required=True)
    matrix.set_defaults(handler=handlers.release_matrix)

    result = subparsers.add_parser(
        "record-release-result",
        help="stage one deeply validated core result for a release plan",
    )
    result.add_argument("--plan", type=config.path_value, required=True)
    result.add_argument("--core", required=True)
    result.add_argument(
        "--group-tag",
        choices=CORE_TRACK_GROUP_TAG_CHOICES,
        help="exact track-group selector bound by the release plan",
    )
    result.add_argument("--e2e-record", type=config.path_value, required=True)
    result.add_argument("--output-dir", type=config.path_value, required=True)
    result.set_defaults(handler=handlers.record_release_result)

    seal = subparsers.add_parser(
        "seal-release",
        help="fail closed while sealing all planned core results",
    )
    seal.add_argument("--plan", type=config.path_value, required=True)
    seal.add_argument("--results-root", type=config.path_value, required=True)
    seal.add_argument(
        "--runner-profile",
        choices=config.runner_profile_choices,
        required=True,
    )
    seal.add_argument("--output-dir", type=config.path_value, required=True)
    seal.set_defaults(handler=handlers.seal_release)
