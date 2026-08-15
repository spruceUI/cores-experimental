"""Code-owned stable check registry and cumulative tier expansion."""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType

from ..errors import PipelineError
from .model import (
    ArgvParameter,
    CheckDefinition,
    CheckExecution,
    CheckInstrumentation,
    CheckTier,
    ParameterKind,
    StructuredFormat,
)


TIER_ORDER = (
    CheckTier.QUICK,
    CheckTier.STATIC,
    CheckTier.EVIDENCE,
    CheckTier.REBUILD,
)

FULL_STATIC_ARGV = (
    "python3",
    "-B",
    "-m",
    "pytest",
    "--import-mode=importlib",
    "-p",
    "no:cacheprovider",
    "tests/",
    "-q",
)
FULL_STATIC_BASELINE_MILLISECONDS = 917_350
FULL_STATIC_CEILING_MILLISECONDS = 1_009_085
FULL_STATIC_ALLOWED_SKIPS = (
    "tests/test_toolchain_archive.py::RealToolchainArchiveTests::"
    "test_current_archives_reproduce_the_complete_tracked_lock",
    "tests/test_toolchain_archive.py::RealToolchainArchiveTests::"
    "test_real_downloads_match_the_tracked_lock",
)

TOOLCHAIN_DOWNLOAD_ARGV_PREFIX = (
    "python3",
    "-B",
    "scripts/toolchain_archive.py",
    "verify-downloads",
    "--lock",
    "pins/toolchains/local-cache-v1.json",
)
TOOLCHAIN_DOWNLOAD_PARAMETERS = (
    ArgvParameter(
        name="arm64_archive",
        flag="--arm64",
        kind=ParameterKind.PATH,
    ),
    ArgvParameter(
        name="armhf_archive",
        flag="--armhf",
        kind=ParameterKind.PATH,
    ),
    ArgvParameter(
        name="rust_archive",
        flag="--rust",
        kind=ParameterKind.PATH,
        required=False,
    ),
)


CHECK_DEFINITIONS = (
    CheckDefinition(
        check_id="toolchain.lock-metadata",
        tier=CheckTier.QUICK,
        execution=CheckExecution.LOCAL,
        argv_prefix=("python3", "scripts/toolchain_archive.py", "validate-lock"),
        timeout_milliseconds=120_000,
    ),
    CheckDefinition(
        check_id="pipeline.workflow-audit",
        tier=CheckTier.QUICK,
        execution=CheckExecution.LOCAL,
        argv_prefix=("python3", "scripts/core_pipeline.py", "audit-workflows"),
        timeout_milliseconds=180_000,
    ),
    CheckDefinition(
        check_id="tests.runner-contracts",
        tier=CheckTier.QUICK,
        execution=CheckExecution.LOCAL,
        argv_prefix=(
            "python3",
            "-m",
            "unittest",
            "tests.test_runner_profiles",
            "tests.test_runner_evidence",
            "tests.test_pipeline_source_bundle",
            "tests.test_commit_blacklist",
        ),
        timeout_milliseconds=300_000,
    ),
    CheckDefinition(
        check_id="tests.pipeline-regression",
        tier=CheckTier.QUICK,
        execution=CheckExecution.LOCAL,
        argv_prefix=("python3", "-m", "unittest", "tests.test_core_pipeline"),
        timeout_milliseconds=900_000,
    ),
    CheckDefinition(
        check_id="repository.diff-check",
        tier=CheckTier.QUICK,
        execution=CheckExecution.LOCAL,
        argv_prefix=("git", "diff", "--check"),
        timeout_milliseconds=60_000,
    ),
    CheckDefinition(
        check_id="pipeline.catalog",
        tier=CheckTier.STATIC,
        execution=CheckExecution.LOCAL,
        argv_prefix=("python3", "scripts/core_pipeline.py", "catalog-check"),
        timeout_milliseconds=300_000,
    ),
    CheckDefinition(
        check_id="tests.full-static",
        tier=CheckTier.STATIC,
        execution=CheckExecution.LOCAL,
        argv_prefix=FULL_STATIC_ARGV,
        timeout_milliseconds=FULL_STATIC_CEILING_MILLISECONDS,
        instrumentation=CheckInstrumentation.PYTEST,
        allowed_skips=FULL_STATIC_ALLOWED_SKIPS,
        required_structured_formats=(StructuredFormat.JSON, StructuredFormat.JUNIT),
        audited_baseline_milliseconds=FULL_STATIC_BASELINE_MILLISECONDS,
        runtime_ceiling_milliseconds=FULL_STATIC_CEILING_MILLISECONDS,
    ),
    CheckDefinition(
        check_id="evidence.promoted-core-sweep",
        tier=CheckTier.EVIDENCE,
        execution=CheckExecution.LOCAL,
        argv_prefix=("python3", "scripts/verify_core.py", "--all"),
        timeout_milliseconds=1_800_000,
    ),
    CheckDefinition(
        check_id="evidence.toolchain-store",
        tier=CheckTier.EVIDENCE,
        execution=CheckExecution.LOCAL,
        argv_prefix=(
            "python3",
            "scripts/toolchain_archive.py",
            "validate-lock",
            "--verify-store",
        ),
        timeout_milliseconds=1_800_000,
    ),
    CheckDefinition(
        check_id="evidence.toolchain-downloads",
        tier=CheckTier.EVIDENCE,
        execution=CheckExecution.LOCAL,
        argv_prefix=TOOLCHAIN_DOWNLOAD_ARGV_PREFIX,
        parameters=TOOLCHAIN_DOWNLOAD_PARAMETERS,
        timeout_milliseconds=1_800_000,
    ),
    CheckDefinition(
        check_id="release-candidate-roster",
        tier=CheckTier.REBUILD,
        execution=CheckExecution.EXTERNAL_RECEIPT,
        argv_prefix=(),
        required_structured_formats=(StructuredFormat.JSON, StructuredFormat.JUNIT),
    ),
)

TIER_ADDITIONS = MappingProxyType(
    {
        CheckTier.QUICK: (
            "toolchain.lock-metadata",
            "pipeline.workflow-audit",
            "tests.runner-contracts",
            "tests.pipeline-regression",
            "repository.diff-check",
        ),
        CheckTier.STATIC: (
            "pipeline.catalog",
            "tests.full-static",
        ),
        CheckTier.EVIDENCE: (
            "evidence.promoted-core-sweep",
            "evidence.toolchain-store",
            "evidence.toolchain-downloads",
        ),
        CheckTier.REBUILD: ("release-candidate-roster",),
    }
)

CHECK_BY_ID = MappingProxyType(
    {definition.check_id: definition for definition in CHECK_DEFINITIONS}
)


def _coerce_tier(value: CheckTier | str) -> CheckTier:
    if type(value) is CheckTier:
        return value
    if type(value) is str:
        try:
            return CheckTier(value)
        except ValueError as exc:
            raise PipelineError(f"unknown check tier: {value}") from exc
    raise PipelineError("check tier must be a stable tier string")


def definition_for(check_id: str) -> CheckDefinition:
    """Return one exact registered definition, rejecting unknown IDs."""

    if type(check_id) is not str:
        raise PipelineError("check ID must be a string")
    try:
        return CHECK_BY_ID[check_id]
    except KeyError as exc:
        raise PipelineError(f"unknown check ID: {check_id}") from exc


def checks_for_tiers(
    tiers: Iterable[CheckTier | str],
) -> tuple[CheckDefinition, ...]:
    """Expand cumulative tiers in registry order and deduplicate definitions."""

    if isinstance(tiers, (str, bytes)):
        raise PipelineError("check tiers must be an iterable of complete tier names")
    requested = tuple(_coerce_tier(item) for item in tiers)
    if not requested:
        raise PipelineError("at least one check tier is required")
    included_tiers: set[CheckTier] = set()
    for requested_tier in requested:
        limit = TIER_ORDER.index(requested_tier)
        included_tiers.update(TIER_ORDER[: limit + 1])
    check_ids = tuple(
        check_id
        for tier in TIER_ORDER
        if tier in included_tiers
        for check_id in TIER_ADDITIONS[tier]
    )
    return tuple(definition_for(check_id) for check_id in check_ids)


def checks_for_tier(tier: CheckTier | str) -> tuple[CheckDefinition, ...]:
    """Expand one cumulative tier in stable registry order."""

    return checks_for_tiers((_coerce_tier(tier),))


def check_ids_for_tier(tier: CheckTier | str) -> tuple[str, ...]:
    """Return the stable ordered IDs required to claim one tier."""

    return tuple(item.check_id for item in checks_for_tier(tier))


def _validate_registry() -> None:
    ids = tuple(item.check_id for item in CHECK_DEFINITIONS)
    if len(ids) != len(set(ids)):
        raise RuntimeError("consolidated check registry contains duplicate IDs")
    additions = tuple(
        check_id for tier in TIER_ORDER for check_id in TIER_ADDITIONS[tier]
    )
    if additions != ids:
        raise RuntimeError("consolidated check registry order differs from tier policy")
    for tier in TIER_ORDER:
        for check_id in TIER_ADDITIONS[tier]:
            if CHECK_BY_ID[check_id].tier is not tier:
                raise RuntimeError(
                    f"consolidated check {check_id} is assigned to the wrong tier"
                )


_validate_registry()


__all__ = [
    "CHECK_BY_ID",
    "CHECK_DEFINITIONS",
    "FULL_STATIC_ALLOWED_SKIPS",
    "FULL_STATIC_ARGV",
    "FULL_STATIC_BASELINE_MILLISECONDS",
    "FULL_STATIC_CEILING_MILLISECONDS",
    "TIER_ADDITIONS",
    "TIER_ORDER",
    "TOOLCHAIN_DOWNLOAD_ARGV_PREFIX",
    "TOOLCHAIN_DOWNLOAD_PARAMETERS",
    "check_ids_for_tier",
    "checks_for_tier",
    "checks_for_tiers",
    "definition_for",
]
