"""Argument-parser construction for the local-only core pipeline."""

from __future__ import annotations

import argparse

from ..chipsets import CHIPSETS, REAL_CHIPSETS
from ..tracks import CORE_TRACKS
from .inventory import CORE_TRACK_GROUP_TAG_CHOICES, register_inventory_parser
from .model import AppendUniqueAction, ParserConfig, ParserHandlers
from .release import register_release_parsers
from .track_promotion import register_track_promotion_parser


RUN_ID_HELP = "new individual-core run identity"


class _StoreOnceAction(argparse.Action):
    """Store one required selector and reject repeated option spelling."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str,
        option_string: str | None = None,
    ) -> None:
        if getattr(namespace, self.dest, None) is not None:
            parser.error(f"{option_string} may be specified only once")
        setattr(namespace, self.dest, values)


def build_parser(
    *, handlers: ParserHandlers, config: ParserConfig
) -> argparse.ArgumentParser:
    """Build the complete CLI from explicit entrypoint-owned dependencies."""

    if not isinstance(handlers, ParserHandlers):
        raise TypeError("handlers must be a ParserHandlers instance")
    if not isinstance(config, ParserConfig):
        raise TypeError("config must be a ParserConfig instance")

    parser = argparse.ArgumentParser(description=config.description)
    parser.add_argument(
        "--catalog", type=config.path_value, default=config.default_catalog
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser(
        "catalog-check", help="validate the individual-core build catalog"
    )
    catalog.set_defaults(handler=handlers.catalog_check)

    source_rebase = subparsers.add_parser(
        "core-source-candidate-rebase",
        help=(
            "create a core-scoped proof rebasing a stale frozen source "
            "snapshot to the current canonical recipe"
        ),
    )
    source_rebase.add_argument("--core", action=_StoreOnceAction, required=True)
    source_rebase.add_argument(
        "--snapshot", type=config.path_value, required=True
    )
    source_rebase.set_defaults(handler=handlers.core_source_candidate_rebase)

    source_prepare = subparsers.add_parser(
        "core-source-candidate-prepare",
        help=(
            "create an ignored one-core catalog for an exact frozen, "
            "not-yet-pinned source"
        ),
    )
    source_prepare.add_argument("--core", action=_StoreOnceAction, required=True)
    source_prepare.add_argument(
        "--snapshot", type=config.path_value, required=True
    )
    source_prepare.add_argument(
        "--catalog-rebase",
        type=config.path_value,
        help="required exact catalog-rebase proof when the snapshot catalog is stale",
    )
    source_prepare.set_defaults(handler=handlers.core_source_candidate_prepare)

    register_inventory_parser(
        subparsers,
        handlers=handlers,
    )
    register_track_promotion_parser(
        subparsers,
        handlers=handlers,
    )

    set_test = subparsers.add_parser(
        "core-track-set-test",
        help="atomically admit one authoritative pin into one exact TEST cell",
    )
    set_test.add_argument("--track", choices=CORE_TRACKS, required=True)
    set_test.add_argument("--core", required=True)
    set_test.add_argument("--chipset", choices=CHIPSETS, required=True)
    set_test.add_argument("--pin-id", required=True)
    set_test.add_argument("--tuning-profile", required=True)
    set_test.add_argument(
        "--slice-time",
        required=True,
        metavar="YYYY-MM-DDTHH:MM:SSZ",
        help="immutable UTC version-slice time for this exact track assignment",
    )
    set_test.add_argument(
        "--applicable-chipset",
        action=AppendUniqueAction,
        choices=REAL_CHIPSETS,
        help=(
            "explicit fallback applicability; repeat in sorted order for a "
            "universal cell, omit for an exact tuned cell"
        ),
    )
    set_test.add_argument(
        "--expected-current-test",
        required=True,
        metavar="absent|SHA256",
        help="two-sided CAS expectation for the exact track-local TEST cell",
    )
    set_test.add_argument(
        "--expected-current-assignment",
        required=True,
        metavar="absent|SHA256",
        help=(
            "CAS expectation for the complete direct assignment, including "
            "its immutable version slice"
        ),
    )
    set_test.add_argument(
        "--expected-new-variant",
        required=True,
        help="reviewed 64-hex variant identity for the admitted pin/profile",
    )
    set_test.add_argument(
        "--expected-parent-variant",
        metavar="SHA256",
        help=(
            "reviewed parent-track variant CAS; required for nightly/edge "
            "and forbidden for main"
        ),
    )
    set_test.add_argument(
        "--expected-parent-registry",
        metavar="SHA256",
        help=(
            "reviewed parent registry CAS; required for nightly/edge and "
            "forbidden for main"
        ),
    )
    set_test.add_argument(
        "--outlier-authorized-at",
        metavar="YYYY-MM-DDTHH:MM:SSZ",
        help="exact source-order outlier authorization timestamp",
    )
    set_test.add_argument(
        "--outlier-authorized-by",
        help="source-order outlier authorizer; requires the complete outlier tuple",
    )
    set_test.add_argument(
        "--outlier-reason",
        help="source-order outlier reason; requires the complete outlier tuple",
    )
    set_test.set_defaults(handler=handlers.core_track_set_test)

    audit = subparsers.add_parser(
        "audit-workflows", help="audit core and release Actions workflows"
    )
    audit.add_argument("--output", type=config.path_value)
    audit.set_defaults(handler=handlers.audit_workflows)

    imported = subparsers.add_parser(
        "import-golden",
        help="create one core-owned candidate from SpruceOS bytes",
    )
    imported.add_argument("--core", required=True)
    imported.add_argument(
        "--spruceos", type=config.path_value, default=config.default_spruceos
    )
    imported.add_argument(
        "--output", type=config.path_value, required=True
    )
    imported.add_argument("--allow-missing", action="store_true")
    imported.set_defaults(handler=handlers.import_golden)

    validate = subparsers.add_parser(
        "validate-golden", help="validate explicit golden evidence"
    )
    validate.add_argument(
        "--golden",
        type=config.path_value,
        required=True,
        help="required individual schema-v2 golden path",
    )
    validate.add_argument(
        "--spruceos", type=config.path_value, default=config.default_spruceos
    )
    validate.add_argument("--verify-files", action="store_true")
    validate.add_argument("--verify-store", action="store_true")
    validate.set_defaults(handler=handlers.validate_golden)

    build = subparsers.add_parser(
        "build", help="run one pinned local Docker build"
    )
    build.add_argument("--core", required=True)
    build.add_argument(
        "--arch", choices=list(config.arch_choices), required=True
    )
    build.add_argument("--output", type=config.path_value, required=True)
    build.set_defaults(handler=handlers.build)

    build_core = subparsers.add_parser(
        "build-core",
        help="build and package exactly one catalog core",
    )
    build_core.add_argument(
        "--runner-profile",
        choices=config.runner_profile_choices,
        default=config.default_runner_profile,
    )
    build_core.add_argument(
        "--core",
        action=_StoreOnceAction,
        required=True,
        help="one catalog core; builds its complete declared target set",
    )
    build_core.add_argument(
        "--group-tag",
        choices=CORE_TRACK_GROUP_TAG_CHOICES,
        help=(
            "optional pinned <track>-<stable|test>:<chipset> selection; "
            "builds only its resolved architecture set"
        ),
    )
    build_core.add_argument("--run-id", help=RUN_ID_HELP)
    build_core.add_argument(
        "--output-root", type=config.path_value, default=config.default_runs
    )
    build_core.set_defaults(handler=handlers.build_core)

    e2e = subparsers.add_parser(
        "e2e", help="run one core's local build/package flow"
    )
    e2e.add_argument(
        "--runner-profile",
        choices=config.runner_profile_choices,
        default=config.default_runner_profile,
    )
    e2e.add_argument(
        "--core",
        action=_StoreOnceAction,
        required=True,
        help="exactly one catalog core; this option may not be repeated",
    )
    e2e_scope = e2e.add_mutually_exclusive_group()
    e2e_scope.add_argument(
        "--group-tag",
        choices=CORE_TRACK_GROUP_TAG_CHOICES,
        help=(
            "optional pinned <track>-<stable|test>:<chipset> selection; "
            "cannot be combined with --arch"
        ),
    )
    e2e_scope.add_argument(
        "--arch",
        action="append",
        choices=list(config.arch_choices),
        help="diagnostic target for this core; repeat only for unique targets",
    )
    e2e_scope.add_argument(
        "--tuning-profile",
        action=_StoreOnceAction,
        help=(
            "build exactly one ABI using a current non-universal typed tuning "
            "profile; candidate evidence is promotable only by promote-tuned-variant"
        ),
    )
    e2e.add_argument("--run-id", help=RUN_ID_HELP)
    e2e.add_argument(
        "--output-root", type=config.path_value, default=config.default_runs
    )
    e2e.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop this core's run after its first failed target",
    )
    e2e.set_defaults(handler=handlers.e2e)

    promote = subparsers.add_parser(
        "promote", help="promote one passing core-owned schema-v2 record"
    )
    promote.add_argument(
        "--golden", type=config.path_value, required=True
    )
    promote.add_argument("--record", type=config.path_value, required=True)
    promote.add_argument("--e2e-record", type=config.path_value, required=True)
    promote.set_defaults(handler=handlers.promote)

    promote_host_reproduction = subparsers.add_parser(
        "promote-host-reproduction",
        help=(
            "create an immutable golden and pin from hardened simulated-Actions "
            "and native-local E2Es"
        ),
    )
    promote_host_reproduction.add_argument(
        "--core", action=_StoreOnceAction, required=True
    )
    promote_host_reproduction.add_argument(
        "--source-golden", type=config.path_value, required=True
    )
    promote_host_reproduction.add_argument(
        "--selected-e2e", type=config.path_value, required=True
    )
    promote_host_reproduction.add_argument(
        "--reproduction-e2e", type=config.path_value, required=True
    )
    promote_host_reproduction.set_defaults(
        handler=handlers.promote_host_reproduction
    )

    promote_source_candidate = subparsers.add_parser(
        "promote-source-candidate",
        help=(
            "create an immutable golden and pin from two independent untuned "
            "E2Es built with one authenticated source-candidate catalog"
        ),
    )
    promote_source_candidate.add_argument(
        "--core", action=_StoreOnceAction, required=True
    )
    promote_source_candidate.add_argument(
        "--source-golden", type=config.path_value, required=True
    )
    promote_source_candidate.add_argument(
        "--selected-e2e", type=config.path_value, required=True
    )
    promote_source_candidate.add_argument(
        "--reproduction-e2e", type=config.path_value, required=True
    )
    promote_source_candidate.set_defaults(
        handler=handlers.promote_source_candidate
    )

    promote_tuned = subparsers.add_parser(
        "promote-tuned-variant",
        help="promote two independent one-ABI tuned E2Es into a golden and pin",
    )
    promote_tuned.add_argument("--core", required=True)
    promote_tuned.add_argument("--tuning-profile", required=True)
    promote_tuned.add_argument(
        "--source-golden", type=config.path_value, required=True
    )
    promote_tuned.add_argument(
        "--selected-e2e", type=config.path_value, required=True
    )
    promote_tuned.add_argument(
        "--reproduction-e2e", type=config.path_value, required=True
    )
    promote_tuned.set_defaults(handler=handlers.promote_tuned_variant)

    derive_id = subparsers.add_parser(
        "derive-core-id",
        help="derive one core's semantic lifecycle ID without writing files",
    )
    derive_id.add_argument("--core", required=True)
    derive_id.add_argument(
        "--source-golden", type=config.path_value, required=True
    )
    derive_id.set_defaults(handler=handlers.derive_core_id)

    compose_golden = subparsers.add_parser(
        "compose-core-golden",
        help="create an exact-scope individual core nightly",
    )
    compose_golden.add_argument("--core", required=True)
    compose_golden.add_argument(
        "--source-golden", type=config.path_value, required=True
    )
    compose_golden.add_argument(
        "--output", type=config.path_value, required=True
    )
    compose_golden.set_defaults(handler=handlers.compose_core_golden)

    compose = subparsers.add_parser(
        "compose-pin-set", help="create one semantic individual-core package lock"
    )
    compose.add_argument("--pin-id", required=True)
    compose.add_argument("--core", required=True)
    compose.add_argument(
        "--source-golden",
        type=config.path_value,
        required=True,
    )
    compose.add_argument("--output", type=config.path_value, required=True)
    compose.set_defaults(handler=handlers.compose_pin_set)

    validate_pin = subparsers.add_parser(
        "validate-pin-set", help="validate an immutable core-set lock"
    )
    validate_pin.add_argument("--pin-set", type=config.path_value, required=True)
    validate_pin.add_argument("--verify-store", action="store_true")
    validate_pin.add_argument("--verify-sources", action="store_true")
    validate_pin.set_defaults(handler=handlers.validate_pin_set)

    release = subparsers.add_parser(
        "promote-release", help="copy pinned package bytes into a local release"
    )
    release.add_argument("--pin-set", type=config.path_value, required=True)
    release.add_argument("--output", type=config.path_value, required=True)
    release.set_defaults(handler=handlers.promote_release)

    validate_release = subparsers.add_parser(
        "validate-release", help="verify a local release against its pin"
    )
    validate_release.add_argument(
        "--pin-set", type=config.path_value, required=True
    )
    validate_release.add_argument(
        "--release", type=config.path_value, required=True
    )
    validate_release.add_argument("--verify-store", action="store_true")
    validate_release.set_defaults(handler=handlers.validate_release)

    update_channel = subparsers.add_parser(
        "update-channel",
        help="atomically compare-and-swap a local channel pointer",
    )
    update_channel.add_argument(
        "--channel", choices=list(config.channel_choices), required=True
    )
    update_channel.add_argument(
        "--target", type=config.path_value, required=True
    )
    update_channel.add_argument(
        "--core",
        required=True,
        help="update the individual-core channel namespace",
    )
    channel_expectation = update_channel.add_mutually_exclusive_group(required=True)
    channel_expectation.add_argument("--expect-absent", action="store_true")
    channel_expectation.add_argument("--expect-current")
    update_channel.set_defaults(handler=handlers.update_channel)

    validate_channel = subparsers.add_parser(
        "validate-channel",
        help="deeply validate a local channel pointer and target",
    )
    validate_channel.add_argument(
        "--channel", choices=list(config.channel_choices), required=True
    )
    validate_channel.add_argument(
        "--core",
        required=True,
        help="validate the individual-core channel alias",
    )
    validate_channel.set_defaults(handler=handlers.validate_channel)

    register_release_parsers(
        subparsers,
        handlers=handlers,
        config=config,
    )
    return parser
