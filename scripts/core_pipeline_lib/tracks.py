"""Manual version-channel core tracks with fail-closed build-pin admission."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import copy
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from .chipsets import (
    CHIPSETS,
    CHIPSET_ARCHITECTURES,
    PROFILE_ID_RE,
    REAL_CHIPSETS,
    UNIVERSAL_TUNING_PROFILE,
    resolved_tuning_profile,
    validate_chipset_tunings,
)
from .errors import PipelineError
from .foundation import load_json, load_json_with_sha256, safe_child, sha256_file


CORE_TRACKS = ("main", "nightly", "edge")
TRACK_PARENTS = {"main": None, "nightly": "main", "edge": "nightly"}
TRACK_ANCESTORS = {
    "main": frozenset({"main"}),
    "nightly": frozenset({"main", "nightly"}),
    "edge": frozenset({"main", "nightly", "edge"}),
}
TRACK_MARKERS = ("stable", "test")
CORE_TRACK_SCHEMA_REF = "./core-tracks.schema.json"
CORE_TRACK_SCHEMA_VERSION = 3
CORE_TRACK_SELECTION_MODEL = "manual-version-channel-build-pins-v3"
CORE_TRACK_APPLICABILITY_SCOPE = "architecture-only"
CORE_TRACK_VERSION_ASSIGNMENT_MODEL = "manual-reviewed-build-pin-v1"
CORE_TRACK_VERSION_SLICE_MODEL = "manual-track-version-slice-v1"
CORE_TRACK_SLICE_COMPARISON_BASIS_MODEL = (
    "spruce-track-comparison-basis-projection-v1"
)
CORE_TRACK_SLICE_BRANCH_BASIS_SNAPSHOT_MODEL = (
    "spruce-track-branch-basis-snapshot-v1"
)
CORE_TRACK_ASSIGNMENT_MODEL = "manual-track-cell-assignment-v1"
CORE_TRACK_SOURCE_ORDER_MODEL = (
    "assignment-time-git-ancestry-or-authorized-outlier-v1"
)
CORE_TRACK_VERSION_LEVELS = {
    "main": "spruce-main",
    "nightly": "spruce-development",
    "edge": "latest-reviewed-upstream",
}
CORE_TRACK_EDGE_LATEST_MODEL = "reviewed-remote-ref-snapshot-v1"
EDGE_HEAD_KEYS = frozenset(
    {
        "repository",
        "requested_ref",
        "commit",
        "tree",
        "latest_semantics",
        "status",
    }
)
EDGE_SNAPSHOT_KEYS = frozenset(
    {"snapshot_id", "captured_at", "file_sha256", "content_sha256"}
)
SOURCE_ORDER_PARENT_BINDING_MODEL = "assignment-time-parent-test-v1"
SOURCE_ORDER_PARENT_SELECTION_MODEL = "assignment-time-parent-selection-v1"
SOURCE_ORDER_PARENT_BINDING_KEYS = frozenset(
    {
        "model",
        "track",
        "core_id",
        "chipset",
        "captured_registry_content_sha256",
        "parent_track",
        "parent_origin_track",
        "parent_selected_chipset",
        "parent_cell",
        "parent_variant_id",
        "parent_build_pin_id",
        "parent_pin_content_sha256",
        "parent_source_repository",
        "parent_source_requested_ref",
        "parent_source_commit",
        "parent_source_tree",
        "parent_lineage",
        "parent_selection_content_sha256",
        "child_cell",
        "child_variant_id",
        "child_build_pin_id",
        "child_pin_content_sha256",
        "child_source_repository",
        "child_source_requested_ref",
        "child_source_commit",
        "child_source_tree",
        "content_sha256",
    }
)
SOURCE_ORDER_PARENT_LINEAGE_KEYS = frozenset({"binding", "outlier"})
SOURCE_ORDER_OUTLIER_KEYS = frozenset(
    {
        "marker",
        "track",
        "core_id",
        "chipset",
        "parent_track",
        "parent_binding_content_sha256",
        "child_cell",
        "child_variant_id",
        "child_build_pin_id",
        "child_pin_content_sha256",
        "child_source_repository",
        "child_source_requested_ref",
        "child_source_commit",
        "child_source_tree",
        "authorized_at",
        "authorized_by",
        "reason",
    }
)
CORE_TRACK_SPRUCE_BRANCH_BASES_PATH = (
    "manifests/spruce-core-branch-bases.json"
)
CORE_TRACK_SPRUCE_BRANCH_BASIS_IDS = {
    "main": "spruce-main",
    "nightly": "spruce-development",
    "edge": "spruce-development",
}
CORE_TRACK_MAIN_RELEASE_ROSTER_PATH = "manifests/spruce-release-roster.json"
CORE_TRACK_CATALOG_PATH = "manifests/core-builds.json"
CORE_TRACK_RELEASE_ROSTER_SCHEMA_REF = "./spruce-release-roster.schema.json"
CORE_TRACK_RELEASE_ROSTER_SCHEMA_VERSION = 1
CORE_TRACK_RELEASE_ROSTER_MODEL = "spruce-release-git-tree-v1"
CORE_TRACK_RELEASE_CORRELATION_MODEL = (
    "logical-core-name-correlation-only-v1"
)
CORE_TRACK_SOURCE_SNAPSHOT_SCHEMA_REF = (
    "../../manifests/core-track-source-snapshot.schema.json"
)
CORE_TRACK_SOURCE_SNAPSHOT_SCHEMA_VERSION = 1
CORE_TRACK_SOURCE_SNAPSHOT_ROOT = Path("pins/core-track-registry-snapshots")

CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SHIPPED_CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHIPSET_PATTERN = "|".join(re.escape(chipset) for chipset in CHIPSETS)
GROUP_TAG_RE = re.compile(
    rf"^(main|nightly|edge)-(stable|test):({CHIPSET_PATTERN})$"
)
APPROVED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
EXPECTED_STABLE_ABSENT = "absent"
EXPECTED_TEST_ABSENT = "absent"
EXPECTED_ASSIGNMENT_ABSENT = "absent"
MAX_STABLE_PROVENANCE_DEPTH = 64
DEFERRED_STATE = "deferred"
DEFERRED_NO_REVIEWED_VERSION_REASON = "no-reviewed-version-channel-build-pin"

TEST_CELL_KEYS = frozenset(
    {
        "build_pin_id",
        "tuning_profile",
        "applicable_chipsets",
        "version_slice",
    }
)
STABLE_CELL_KEYS = frozenset(
    {
        *TEST_CELL_KEYS,
        "approved_test_variant_id",
        "approved_test_origin_track",
        "approved_at",
        "approved_by",
        "reason",
        "previous_stable_variant_id",
        "source_registry_content_sha256",
    }
)
DEFERRED_CELL_KEYS = frozenset({"state", "reason"})
VERSION_SLICE_KEYS = frozenset(
    {"model", "track", "slice_time", "content_sha256"}
)
SLICE_COMPARISON_BASIS_KEYS = frozenset(
    {
        "model",
        "track",
        "slice_time",
        "spruce_branch_registry_content_sha256",
        "basis_id",
        "basis_content_sha256",
        "branch",
        "content_sha256",
    }
)
SLICE_COMPARISON_BRANCH_KEYS = frozenset(
    {"repository", "ref", "commit", "tree"}
)
SLICE_BRANCH_BASIS_SNAPSHOT_KEYS = frozenset(
    {
        "model",
        "branch_bases",
        "catalog",
        "release_roster",
        "catalog_file_sha256",
        "release_roster_file_sha256",
        "content_sha256",
    }
)


class _StableProvenanceValidation:
    """Memoized structural checks for immutable stable source snapshots."""

    def __init__(self) -> None:
        self.memo: dict[
            str,
            tuple[Mapping[str, Any] | None, tuple[str, ...]],
        ] = {}


def _canonical_utc_approval_timestamp(value: object) -> str | None:
    """Return an exact UTC second timestamp, rejecting impossible dates."""

    if not isinstance(value, str) or APPROVED_AT_RE.fullmatch(value) is None:
        return None
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=dt.timezone.utc
        )
    except ValueError:
        return None
    canonical = parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    return canonical if canonical == value else None


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def slice_comparison_basis_content_sha256(
    comparison_basis: Mapping[str, Any],
) -> str:
    """Return the identity of one self-contained Spruce comparison basis."""

    return _semantic_sha256(
        {
            key: comparison_basis.get(key)
            for key in sorted(
                SLICE_COMPARISON_BASIS_KEYS - {"content_sha256"}
            )
        }
    )


def version_slice_content_sha256(
    version_slice: Mapping[str, Any],
    *,
    comparison_basis: Mapping[str, Any],
) -> str:
    """Bind one manual tranche to its immutable comparison-basis projection."""

    return _semantic_sha256(
        {
            "model": version_slice.get("model"),
            "track": version_slice.get("track"),
            "slice_time": version_slice.get("slice_time"),
            "slice_comparison_basis_content_sha256": comparison_basis.get(
                "content_sha256"
            ),
        }
    )


def slice_branch_basis_snapshot_content_sha256(
    snapshot: Mapping[str, Any],
) -> str:
    """Return the identity of one detached, dependency-complete basis snapshot."""

    return _semantic_sha256(
        {
            key: snapshot.get(key)
            for key in sorted(
                SLICE_BRANCH_BASIS_SNAPSHOT_KEYS - {"content_sha256"}
            )
        }
    )


def _slice_branch_basis_snapshot(
    *,
    spruce_branch_bases: Mapping[str, Any],
    catalog: Mapping[str, Any],
    main_release_roster: Mapping[str, Any],
    catalog_file_sha256: str,
    release_roster_file_sha256: str,
) -> dict[str, Any]:
    snapshot = {
        "model": CORE_TRACK_SLICE_BRANCH_BASIS_SNAPSHOT_MODEL,
        "branch_bases": copy.deepcopy(dict(spruce_branch_bases)),
        "catalog": copy.deepcopy(dict(catalog)),
        "release_roster": copy.deepcopy(dict(main_release_roster)),
        "catalog_file_sha256": catalog_file_sha256,
        "release_roster_file_sha256": release_roster_file_sha256,
        "content_sha256": "",
    }
    snapshot["content_sha256"] = slice_branch_basis_snapshot_content_sha256(
        snapshot
    )
    return snapshot


def _slice_comparison_basis_projection(
    *,
    track: str,
    slice_time: str,
    spruce_branch_bases: Mapping[str, Any],
) -> dict[str, Any]:
    basis_id = CORE_TRACK_SPRUCE_BRANCH_BASIS_IDS[track]
    bases = spruce_branch_bases.get("bases")
    basis = bases.get(basis_id) if isinstance(bases, Mapping) else None
    branch = basis.get("branch") if isinstance(basis, Mapping) else None
    if (
        not isinstance(branch, Mapping)
        or set(branch) != SLICE_COMPARISON_BRANCH_KEYS
        or not isinstance(basis.get("content_sha256"), str)
        or SHA256_RE.fullmatch(basis["content_sha256"]) is None
        or not isinstance(spruce_branch_bases.get("content_sha256"), str)
        or SHA256_RE.fullmatch(spruce_branch_bases["content_sha256"]) is None
    ):
        raise PipelineError("Spruce comparison basis is unavailable for version slice")
    projection = {
        "model": CORE_TRACK_SLICE_COMPARISON_BASIS_MODEL,
        "track": track,
        "slice_time": slice_time,
        "spruce_branch_registry_content_sha256": spruce_branch_bases[
            "content_sha256"
        ],
        "basis_id": basis_id,
        "basis_content_sha256": basis["content_sha256"],
        "branch": {key: copy.deepcopy(branch[key]) for key in sorted(branch)},
        "content_sha256": "",
    }
    projection["content_sha256"] = slice_comparison_basis_content_sha256(
        projection
    )
    return projection


def core_track_version_slice(
    *,
    track: str,
    slice_time: str,
    spruce_branch_bases: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Construct one four-field slice plus its self-contained CAS evidence."""

    if track not in CORE_TRACKS:
        raise PipelineError("core track version slice track is invalid")
    canonical_time = _canonical_utc_approval_timestamp(slice_time)
    if canonical_time is None:
        raise PipelineError("core track version slice time is invalid")
    comparison_basis = _slice_comparison_basis_projection(
        track=track,
        slice_time=canonical_time,
        spruce_branch_bases=spruce_branch_bases,
    )
    version_slice = {
        "model": CORE_TRACK_VERSION_SLICE_MODEL,
        "track": track,
        "slice_time": canonical_time,
        "content_sha256": "",
    }
    version_slice["content_sha256"] = version_slice_content_sha256(
        version_slice,
        comparison_basis=comparison_basis,
    )
    return version_slice, comparison_basis


def core_track_assignment_content_sha256(
    *,
    track: str,
    core_id: str,
    chipset: str,
    cell: Mapping[str, Any],
    parent_registry_content_sha256: str | None,
) -> str:
    """Return the identity of one full track-cell assignment, not its build."""

    return _semantic_sha256(
        {
            "model": CORE_TRACK_ASSIGNMENT_MODEL,
            "track": track,
            "core_id": core_id,
            "chipset": chipset,
            "cell": _cell_projection(cell),
            "parent_registry_content_sha256": parent_registry_content_sha256,
        }
    )


def core_track_test_assignment_content_sha256(
    document: Mapping[str, Any],
    *,
    track: str,
    core_id: str,
    chipset: str,
) -> str | None:
    """Return the requested coordinate's direct TEST assignment CAS.

    Inherited TEST resolution deliberately does not count as a direct
    assignment on the requested track.  ``None`` therefore means callers must
    use the literal ``absent`` CAS when creating that exact coordinate.
    """

    canonical_group_tag(track, "test", chipset)
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        raise PipelineError("core track TEST assignment core id is invalid")
    tracks = document.get("tracks")
    if not isinstance(tracks, Mapping):
        raise PipelineError("core track TEST assignment registry is invalid")
    track_value = tracks.get(track)
    tests = track_value.get("test") if isinstance(track_value, Mapping) else None
    core_cells = tests.get(core_id) if isinstance(tests, Mapping) else None
    cell = core_cells.get(chipset) if isinstance(core_cells, Mapping) else None
    if cell is None:
        return None
    if not isinstance(cell, Mapping):
        raise PipelineError("core track direct TEST assignment cell is invalid")
    parent_registry_content_sha256 = None
    if track != "main":
        binding_index, binding_errors = _source_order_parent_binding_index(
            document.get("source_order_parent_bindings")
        )
        if binding_errors:
            raise PipelineError(
                "core track direct TEST assignment parent bindings are invalid"
            )
        binding = binding_index.get((track, core_id, chipset))
        if not isinstance(binding, Mapping):
            raise PipelineError(
                "core track direct TEST assignment has no frozen parent"
            )
        parent_registry_content_sha256 = binding.get(
            "captured_registry_content_sha256"
        )
        if (
            not isinstance(parent_registry_content_sha256, str)
            or SHA256_RE.fullmatch(parent_registry_content_sha256) is None
        ):
            raise PipelineError(
                "core track direct TEST assignment parent registry is invalid"
            )
    return core_track_assignment_content_sha256(
        track=track,
        core_id=core_id,
        chipset=chipset,
        cell=cell,
        parent_registry_content_sha256=parent_registry_content_sha256,
    )


def core_tracks_content_sha256(document: Mapping[str, Any]) -> str:
    # Version 1 snapshots remain immutable approval evidence.  They are not
    # admitted as current registries, but retaining their historical digest
    # projection lets the v2 loader verify and preserve those files.
    if document.get("schema_version") == 1:
        return _semantic_sha256(
            {
                "schema_version": document.get("schema_version"),
                "selection_model": document.get("selection_model"),
                "applicability_scope": document.get("applicability_scope"),
                "main_release": document.get("main_release"),
                "tracks": document.get("tracks"),
            }
        )
    if document.get("schema_version") == 2:
        return _semantic_sha256(
            {
                "schema_version": document.get("schema_version"),
                "selection_model": document.get("selection_model"),
                "applicability_scope": document.get("applicability_scope"),
                "spruce_branch_bases": document.get("spruce_branch_bases"),
                "historical_release_correlation": document.get(
                    "historical_release_correlation"
                ),
                "tracks": document.get("tracks"),
            }
        )
    return _semantic_sha256(
        {
            "schema_version": document.get("schema_version"),
            "selection_model": document.get("selection_model"),
            "applicability_scope": document.get("applicability_scope"),
            "version_policy": document.get("version_policy"),
            "source_order_parent_bindings": document.get(
                "source_order_parent_bindings"
            ),
            "source_order_outliers": document.get("source_order_outliers"),
            "spruce_branch_bases": document.get("spruce_branch_bases"),
            "historical_release_correlation": document.get(
                "historical_release_correlation"
            ),
            "tracks": document.get("tracks"),
        }
    )


def spruce_release_roster_content_sha256(document: Mapping[str, Any]) -> str:
    """Return the semantic identity of one tracked Spruce release roster."""

    return _semantic_sha256(
        {
            "schema_version": document.get("schema_version"),
            "roster_model": document.get("roster_model"),
            "correlation_model": document.get("correlation_model"),
            "release": document.get("release"),
            "cataloged_core_ids": document.get("cataloged_core_ids"),
            "alias_core_ids": document.get("alias_core_ids"),
            "uncataloged_core_ids": document.get("uncataloged_core_ids"),
        }
    )


def spruce_release_roster_errors(
    document: object, *, catalog: object
) -> list[str]:
    """Validate a reviewable release/core roster without consulting a network."""

    if not isinstance(document, Mapping):
        return ["Spruce release roster must be an object"]
    if set(document) != {
        "$schema",
        "schema_version",
        "roster_model",
        "correlation_model",
        "release",
        "cataloged_core_ids",
        "alias_core_ids",
        "uncataloged_core_ids",
        "content_sha256",
    }:
        return ["Spruce release roster fields are not exact"]
    errors: list[str] = []
    if document.get("$schema") != CORE_TRACK_RELEASE_ROSTER_SCHEMA_REF:
        errors.append("Spruce release roster schema reference is invalid")
    if document.get("schema_version") != CORE_TRACK_RELEASE_ROSTER_SCHEMA_VERSION:
        errors.append("Spruce release roster schema_version is invalid")
    if document.get("roster_model") != CORE_TRACK_RELEASE_ROSTER_MODEL:
        errors.append("Spruce release roster model is invalid")
    if document.get("correlation_model") != CORE_TRACK_RELEASE_CORRELATION_MODEL:
        errors.append("Spruce release roster correlation model is invalid")
    release = document.get("release")
    if not isinstance(release, Mapping) or set(release) != {
        "repository",
        "ref",
        "version",
        "commit",
        "tree",
    }:
        errors.append("Spruce release provenance fields are not exact")
    else:
        if release.get("repository") != "https://github.com/spruceUI/spruceOS.git":
            errors.append("Spruce release repository is invalid")
        version = release.get("version")
        if (
            not isinstance(version, str)
            or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None
            or release.get("ref") != f"refs/tags/v{version}"
        ):
            errors.append("Spruce release version/ref binding is invalid")
        for field in ("commit", "tree"):
            value = release.get(field)
            if not isinstance(value, str) or SHA1_RE.fullmatch(value) is None:
                errors.append(f"Spruce release {field} is invalid")

    cataloged = document.get("cataloged_core_ids")
    uncataloged = document.get("uncataloged_core_ids")
    aliases = document.get("alias_core_ids")
    if (
        not isinstance(cataloged, list)
        or not cataloged
        or any(
            not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None
            for core_id in cataloged
        )
        or cataloged != sorted(set(cataloged))
    ):
        errors.append("Spruce release cataloged core IDs are invalid")
        cataloged = []
    if (
        not isinstance(uncataloged, list)
        or any(
            not isinstance(core_id, str)
            or SHIPPED_CORE_ID_RE.fullmatch(core_id) is None
            for core_id in uncataloged
        )
        or uncataloged != sorted(set(uncataloged))
    ):
        errors.append("Spruce release uncataloged core IDs are invalid")
        uncataloged = []
    alias_ids: list[str] = []
    if not isinstance(aliases, Mapping) or list(aliases) != sorted(aliases):
        errors.append("Spruce release alias core map is invalid")
    else:
        for core_id, values in aliases.items():
            if core_id not in cataloged:
                errors.append(
                    f"Spruce release alias owner is not cataloged: {core_id}"
                )
            if (
                not isinstance(values, list)
                or not values
                or any(
                    not isinstance(value, str)
                    or SHIPPED_CORE_ID_RE.fullmatch(value) is None
                    for value in values
                )
                or values != sorted(set(values))
            ):
                errors.append(f"Spruce release aliases are invalid for {core_id}")
            else:
                alias_ids.extend(values)
    if len(alias_ids) != len(set(alias_ids)):
        errors.append("Spruce release aliases are duplicated")
    if set(cataloged) & (set(uncataloged) | set(alias_ids)):
        errors.append("Spruce release roster categories overlap")
    if set(uncataloged) & set(alias_ids):
        errors.append("Spruce release aliases overlap uncataloged cores")
    if not isinstance(catalog, Mapping) or not isinstance(
        catalog.get("cores"), Mapping
    ):
        errors.append("Spruce release roster requires a catalog cores object")
    elif set(cataloged) != set(catalog["cores"]):
        errors.append(
            "Spruce release cataloged roster differs from the core catalog"
        )
    digest = document.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        errors.append("Spruce release roster content_sha256 is invalid")
    elif digest != spruce_release_roster_content_sha256(document):
        errors.append("Spruce release roster content_sha256 is stale")
    return errors


def _pin_content_sha256(document: Mapping[str, Any]) -> str:
    return _semantic_sha256(
        {
            "schema_version": document.get("schema_version"),
            "pin_id": document.get("pin_id"),
            "local_only": document.get("local_only"),
            "publication": document.get("publication"),
            "scope": document.get("scope"),
            "parent": document.get("parent"),
            "sources": document.get("sources"),
            "selection_policy": document.get("selection_policy"),
            "cores": document.get("cores"),
            "summary": document.get("summary"),
        }
    )


def parse_group_tag(value: object) -> tuple[str, str, str]:
    """Parse the exact public ``track-marker:chipset`` spelling."""

    if not isinstance(value, str):
        raise PipelineError("core group tag must be a string")
    match = GROUP_TAG_RE.fullmatch(value)
    if match is None:
        raise PipelineError(
            "core group tag must match "
            "(main|nightly|edge)-(stable|test):"
            f"({'|'.join(CHIPSETS)})"
        )
    return match.group(1), match.group(2), match.group(3)


def canonical_group_tag(track: str, marker: str, chipset: str) -> str:
    tag = f"{track}-{marker}:{chipset}"
    parse_group_tag(tag)
    return tag


def local_git_source_ancestry_verifier(
    repository_cache: Path,
) -> Callable[[str, str, str, str], bool]:
    """Return a fail-closed, offline verifier for cached source Git graphs.

    Each core uses a bare mirror at ``<repository_cache>/<core_id>.git``.  The
    cache and mirror must already be real directories, the mirror's sole
    ``remote.origin.url`` must exactly match the pinned source URL, and both
    commit objects must exist locally.  Replacement objects, grafts, alternate
    object stores, environment-selected repositories, and lazy fetches are
    disabled or rejected.  This helper never fetches or otherwise mutates a
    repository.
    """

    cache = Path(repository_cache)

    def verify(
        core_id: str,
        repository: str,
        ancestor: str,
        descendant: str,
    ) -> bool:
        if (
            not isinstance(core_id, str)
            or CORE_ID_RE.fullmatch(core_id) is None
            or not isinstance(repository, str)
            or not repository
            or not isinstance(ancestor, str)
            or SHA1_RE.fullmatch(ancestor) is None
            or not isinstance(descendant, str)
            or SHA1_RE.fullmatch(descendant) is None
            or cache.is_symlink()
            or not cache.is_dir()
        ):
            return False
        try:
            lexical_source = cache / f"{core_id}.git"
            if lexical_source.is_symlink():
                return False
            source = safe_child(cache, f"{core_id}.git", "core source repository")
            if source.is_symlink() or not source.is_dir():
                return False
            objects = source / "objects"
            config = source / "config"
            shallow = source / "shallow"
            commondir = source / "commondir"
            forbidden_graph_inputs = (
                source / "info" / "grafts",
                objects / "info" / "alternates",
                objects / "info" / "http-alternates",
            )
            if (
                objects.is_symlink()
                or not objects.is_dir()
                or config.is_symlink()
                or not config.is_file()
                or shallow.exists()
                or shallow.is_symlink()
                or commondir.exists()
                or commondir.is_symlink()
                or any(path.is_symlink() for path in source.rglob("*"))
                or any(
                    path.exists() or path.is_symlink()
                    for path in forbidden_graph_inputs
                )
            ):
                return False
            git_environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("GIT_")
            }
            git_environment.update(
                {
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_NO_LAZY_FETCH": "1",
                    "GIT_NO_REPLACE_OBJECTS": "1",
                    "GIT_OPTIONAL_LOCKS": "0",
                }
            )

            def git(*arguments: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        "git",
                        "--no-replace-objects",
                        "-c",
                        "core.commitGraph=false",
                        f"--git-dir={source}",
                        *arguments,
                    ],
                    cwd=cache,
                    env=git_environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=60,
                )

            bare = git("rev-parse", "--is-bare-repository")
            if bare.returncode or bare.stdout.strip() != "true":
                return False
            common_report = git(
                "rev-parse", "--path-format=absolute", "--git-common-dir"
            )
            common_raw = common_report.stdout.strip()
            if (
                common_report.returncode
                or not common_raw
                or not Path(common_raw).is_absolute()
                or Path(common_raw).resolve(strict=True) != source.resolve(strict=True)
            ):
                return False
            shallow_report = git("rev-parse", "--is-shallow-repository")
            if shallow_report.returncode or shallow_report.stdout.strip() != "false":
                return False
            origin = git(
                "config",
                "--local",
                "--no-includes",
                "--get-all",
                "remote.origin.url",
            )
            if origin.returncode or origin.stdout.splitlines() != [repository]:
                return False
            for commit in (ancestor, descendant):
                if git("cat-file", "-e", f"{commit}^{{commit}}").returncode:
                    return False
            return (
                git("merge-base", "--is-ancestor", ancestor, descendant).returncode
                == 0
            )
        except (OSError, PipelineError, subprocess.TimeoutExpired):
            return False

    return verify


def load_core_pin_index(
    repository_root: Path,
    *,
    pin_validator: (
        Callable[[Mapping[str, Any], Path], Mapping[str, Any]] | None
    ) = None,
) -> dict[str, dict[str, Any]]:
    """Index only pins admitted by the pipeline's authoritative validator.

    The callback is mandatory so this selection layer cannot silently replace
    the full lifecycle validator with its smaller indexing projection.  It may
    validate embedded records without ignored artifact bytes, but it must
    reject any pin that is not an authentic canonical one-core pin.
    """

    if not callable(pin_validator):
        raise PipelineError("authoritative core pin validator is required")

    root = repository_root / "pins" / "core-sets"
    if not root.is_dir():
        raise PipelineError("core pin directory is unavailable")
    index: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise PipelineError(f"core pin must be a regular file: {path.name}")
        try:
            document, file_sha256 = load_json_with_sha256(path)
        except PipelineError as exc:
            if str(exc).startswith("expected a JSON object in "):
                raise PipelineError(
                    f"core pin must be an object: {path.name}"
                ) from exc
            raise
        try:
            report = pin_validator(document, path)
        except PipelineError as exc:
            raise PipelineError(
                f"authoritative core pin validation failed: {path.name}: {exc}"
            ) from exc
        report_errors = report.get("errors") if isinstance(report, Mapping) else None
        if (
            not isinstance(report, Mapping)
            or report.get("status") != "valid"
            or not isinstance(report_errors, list)
            or report_errors
        ):
            details = (
                "; ".join(str(error) for error in report_errors)
                if isinstance(report_errors, list) and report_errors
                else "validator did not return an exact valid report"
            )
            raise PipelineError(
                f"authoritative core pin validation failed: {path.name}: {details}"
            )
        pin_id = document.get("pin_id")
        cores = document.get("cores")
        if (
            not isinstance(pin_id, str)
            or IDENTIFIER_RE.fullmatch(pin_id) is None
            or not isinstance(cores, Mapping)
            or len(cores) != 1
        ):
            raise PipelineError(f"core pin identity is malformed: {path.name}")
        core_id = next(iter(cores))
        if (
            path.name != f"{pin_id}.json"
            or document.get("local_only") is not True
            or document.get("publication") != "disabled"
            or document.get("scope") != [core_id]
            or document.get("content_sha256") != _pin_content_sha256(document)
        ):
            raise PipelineError(f"core pin document identity is malformed: {path.name}")
        core = cores[core_id]
        selection = core.get("selection") if isinstance(core, Mapping) else None
        targets = selection.get("targets") if isinstance(selection, Mapping) else None
        if (
            not isinstance(core_id, str)
            or CORE_ID_RE.fullmatch(core_id) is None
            or not isinstance(targets, Mapping)
            or not targets
            or set(targets) - {"arm64", "armhf"}
        ):
            raise PipelineError(f"core pin target identity is malformed: {path.name}")
        source_commits: set[str] = set()
        source_repositories: set[str] = set()
        source_requested_refs: set[str] = set()
        source_trees: set[str] = set()
        tuning_identities: set[tuple[str, str]] = set()
        tuning_presence: set[bool] = set()
        artifact_sha256: dict[str, str] = {}
        for architecture, target in targets.items():
            golden = target.get("golden_record") if isinstance(target, Mapping) else None
            source = golden.get("source") if isinstance(golden, Mapping) else None
            commit = source.get("resolved_commit") if isinstance(source, Mapping) else None
            repository = source.get("resolved_url") if isinstance(source, Mapping) else None
            requested_ref = (
                source.get("requested_ref") if isinstance(source, Mapping) else None
            )
            tree = source.get("tree") if isinstance(source, Mapping) else None
            if not isinstance(commit, str) or SHA1_RE.fullmatch(commit) is None:
                raise PipelineError(
                    f"core pin source identity is malformed: {path.name}/{architecture}"
                )
            source_commits.add(commit)
            if not isinstance(repository, str) or not repository:
                raise PipelineError(
                    f"core pin source repository is malformed: "
                    f"{path.name}/{architecture}"
                )
            if not isinstance(tree, str) or SHA1_RE.fullmatch(tree) is None:
                raise PipelineError(
                    f"core pin source tree is malformed: {path.name}/{architecture}"
                )
            source_repositories.add(repository)
            if not isinstance(requested_ref, str) or not requested_ref.startswith(
                "refs/"
            ):
                raise PipelineError(
                    f"core pin source requested ref is malformed: "
                    f"{path.name}/{architecture}"
                )
            source_requested_refs.add(requested_ref)
            source_trees.add(tree)
            recipe = golden.get("recipe") if isinstance(golden, Mapping) else None
            tuning = recipe.get("chipset_tuning") if isinstance(recipe, Mapping) else None
            tuning_presence.add(tuning is not None)
            if isinstance(tuning, Mapping):
                if set(tuning) != {"profile_id", "content_sha256"}:
                    raise PipelineError(
                        f"core pin tuning identity fields are not exact: "
                        f"{path.name}/{architecture}"
                    )
                profile_id = tuning.get("profile_id")
                content_sha256 = tuning.get("content_sha256")
                if (
                    not isinstance(profile_id, str)
                    or PROFILE_ID_RE.fullmatch(profile_id) is None
                    or not isinstance(content_sha256, str)
                    or SHA256_RE.fullmatch(content_sha256) is None
                ):
                    raise PipelineError(
                        f"core pin tuning identity is malformed: "
                        f"{path.name}/{architecture}"
                    )
                tuning_identities.add((profile_id, content_sha256))
            elif tuning is not None:
                raise PipelineError(
                    f"core pin tuning identity is malformed: {path.name}/{architecture}"
                )
            artifact = target.get("artifact") if isinstance(target, Mapping) else None
            artifact_digest = (
                artifact.get("sha256") if isinstance(artifact, Mapping) else None
            )
            if (
                not isinstance(artifact_digest, str)
                or SHA256_RE.fullmatch(artifact_digest) is None
            ):
                raise PipelineError(
                    f"core pin artifact identity is malformed: "
                    f"{path.name}/{architecture}"
                )
            artifact_sha256[architecture] = artifact_digest
        if len(source_commits) != 1:
            raise PipelineError(f"core pin source commits differ by target: {path.name}")
        if len(source_repositories) != 1:
            raise PipelineError(
                f"core pin source repositories differ by target: {path.name}"
            )
        if len(source_requested_refs) != 1:
            raise PipelineError(
                f"core pin source requested refs differ by target: {path.name}"
            )
        if len(source_trees) != 1:
            raise PipelineError(f"core pin source trees differ by target: {path.name}")
        if len(tuning_identities) > 1:
            raise PipelineError(f"core pin tuning identities differ by target: {path.name}")
        if len(tuning_presence) > 1:
            raise PipelineError(f"core pin tuning presence differs by target: {path.name}")
        content_sha256 = document.get("content_sha256")
        if not isinstance(content_sha256, str) or SHA256_RE.fullmatch(content_sha256) is None:
            raise PipelineError(f"core pin content identity is malformed: {path.name}")
        host_reproduction = (
            selection.get("host_reproduction")
            if isinstance(selection, Mapping)
            else None
        )
        host_reproduction_content_sha256 = None
        if host_reproduction is not None:
            if not isinstance(host_reproduction, Mapping):
                raise PipelineError(
                    f"core pin host reproduction proof is malformed: {path.name}"
                )
            proof_digest = host_reproduction.get("content_sha256")
            if (
                not isinstance(proof_digest, str)
                or SHA256_RE.fullmatch(proof_digest) is None
            ):
                raise PipelineError(
                    f"core pin host reproduction proof is malformed: {path.name}"
                )
            # The mandatory authoritative validator above owns the complete
            # proof-shape and semantic checks.  This index projects only its
            # already-validated identity for the track admission gate.
            host_reproduction_content_sha256 = proof_digest
        if pin_id in index:
            raise PipelineError(f"duplicate core pin identity: {pin_id}")
        tuning_identity = next(iter(tuning_identities), None)
        index[pin_id] = {
            "path": str(path.relative_to(repository_root)),
            "pin_id": pin_id,
            "file_sha256": file_sha256,
            "content_sha256": content_sha256,
            "core_id": core_id,
            "architectures": sorted(targets),
            "artifact_sha256": dict(sorted(artifact_sha256.items())),
            "source_commit": next(iter(source_commits)),
            "source_repository": next(iter(source_repositories)),
            "source_requested_ref": next(iter(source_requested_refs)),
            "source_tree": next(iter(source_trees)),
            "tuning_identity": (
                {
                    "profile_id": tuning_identity[0],
                    "content_sha256": tuning_identity[1],
                }
                if tuning_identity is not None
                else None
            ),
            "host_reproduction_content_sha256": (
                host_reproduction_content_sha256
            ),
        }
    if not index:
        raise PipelineError("core pin index is empty")
    return index


def core_track_source_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    """Wrap one complete source registry as immutable approval evidence."""

    return {
        "$schema": CORE_TRACK_SOURCE_SNAPSHOT_SCHEMA_REF,
        "schema_version": CORE_TRACK_SOURCE_SNAPSHOT_SCHEMA_VERSION,
        "source_registry": copy.deepcopy(dict(document)),
    }


def core_track_source_snapshot_path(
    repository_root: Path, source_registry_content_sha256: str
) -> Path:
    """Return the only allowed snapshot location for one registry identity."""

    if SHA256_RE.fullmatch(source_registry_content_sha256) is None:
        raise PipelineError("core track source registry digest is invalid")
    return (
        repository_root
        / CORE_TRACK_SOURCE_SNAPSHOT_ROOT
        / f"{source_registry_content_sha256}.json"
    )


def _snapshot_file_sha256(snapshot: Mapping[str, Any]) -> str:
    rendered = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    return hashlib.sha256(rendered.encode()).hexdigest()


def _snapshot_index_entry(
    *,
    repository_root: Path,
    snapshot: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    if set(snapshot) != {"$schema", "schema_version", "source_registry"}:
        raise PipelineError("core track source snapshot fields are not exact")
    if snapshot.get("$schema") != CORE_TRACK_SOURCE_SNAPSHOT_SCHEMA_REF:
        raise PipelineError("core track source snapshot schema reference is invalid")
    if snapshot.get("schema_version") != CORE_TRACK_SOURCE_SNAPSHOT_SCHEMA_VERSION:
        raise PipelineError("core track source snapshot schema_version is invalid")
    source_registry = snapshot.get("source_registry")
    if not isinstance(source_registry, Mapping):
        raise PipelineError("core track source snapshot registry must be an object")
    digest = source_registry.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise PipelineError("core track source snapshot registry digest is invalid")
    if core_tracks_content_sha256(source_registry) != digest:
        raise PipelineError("core track source snapshot registry digest is stale")
    path = core_track_source_snapshot_path(repository_root, digest)
    return digest, {
        "path": str(path.relative_to(repository_root)),
        "file_sha256": _snapshot_file_sha256(snapshot),
        "source_registry": copy.deepcopy(dict(source_registry)),
    }


def load_core_track_source_registry_index(
    repository_root: Path,
) -> dict[str, dict[str, Any]]:
    """Load tracked prior registries used to prove stable approval lineage."""

    root = repository_root / CORE_TRACK_SOURCE_SNAPSHOT_ROOT
    if not root.exists():
        return {}
    if root.is_symlink() or not root.is_dir():
        raise PipelineError("core track source snapshot root must be a directory")
    index: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise PipelineError(
                f"core track source snapshot must be a regular file: {path.name}"
            )
        snapshot, file_sha256 = load_json_with_sha256(path)
        digest, entry = _snapshot_index_entry(
            repository_root=repository_root,
            snapshot=snapshot,
        )
        if path != core_track_source_snapshot_path(repository_root, digest):
            raise PipelineError(
                f"core track source snapshot filename is invalid: {path.name}"
            )
        if file_sha256 != entry["file_sha256"]:
            raise PipelineError(
                f"core track source snapshot bytes are non-canonical: {path.name}"
            )
        if digest in index:
            raise PipelineError(f"duplicate core track source snapshot: {digest}")
        index[digest] = entry
    return index


def _cell_projection(cell: Mapping[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(cell.get(key)) for key in sorted(TEST_CELL_KEYS)}


def _variant_material(
    *,
    core_id: str,
    cell_chipset: str,
    cell: Mapping[str, Any],
    pin: Mapping[str, Any],
    tuning: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "core_id": core_id,
        "cell_chipset": cell_chipset,
        "pin": {
            key: pin.get(key)
            for key in ("path", "pin_id", "file_sha256", "content_sha256")
        },
        "source_commit": pin.get("source_commit"),
        "architectures": pin.get("architectures"),
        "tuning": {
            "profile_id": tuning.get("profile_id"),
            "content_sha256": tuning.get("content_sha256"),
            "properties": tuning.get("properties"),
            "compiler_argument_mapping_version": tuning.get(
                "compiler_argument_mapping_version"
            ),
            "compiler_arguments": tuning.get("compiler_arguments"),
        },
        "applicable_chipsets": cell.get("applicable_chipsets"),
    }


def core_variant_id(
    *,
    core_id: str,
    cell_chipset: str,
    cell: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
) -> str:
    build_pin_id = cell.get("build_pin_id")
    profile_id = cell.get("tuning_profile")
    pin = (
        pin_index.get(build_pin_id)
        if isinstance(build_pin_id, str)
        else None
    )
    if not isinstance(pin, Mapping) or not isinstance(profile_id, str):
        raise PipelineError(f"cannot derive variant for {core_id}/{cell_chipset}")
    tuning = resolved_tuning_profile(tunings, profile_id)
    return _semantic_sha256(
        _variant_material(
            core_id=core_id,
            cell_chipset=cell_chipset,
            cell=cell,
            pin=pin,
            tuning=tuning,
        )
    )


def _version_slice_shape_errors(
    value: object, *, expected_track: object, label: str
) -> list[str]:
    if not isinstance(value, Mapping) or set(value) != VERSION_SLICE_KEYS:
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    if value.get("model") != CORE_TRACK_VERSION_SLICE_MODEL:
        errors.append(f"{label}.model is invalid")
    if value.get("track") != expected_track:
        errors.append(f"{label}.track is invalid")
    if _canonical_utc_approval_timestamp(value.get("slice_time")) is None:
        errors.append(f"{label}.slice_time is invalid")
    digest = value.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        errors.append(f"{label}.content_sha256 is invalid")
    return errors


def _cell_errors(
    *,
    core_id: str,
    cell_chipset: str,
    cell: object,
    stable: bool,
    approval_track: str,
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    label: str,
    version_slice_track: str | None = None,
) -> list[str]:
    keys = STABLE_CELL_KEYS if stable else TEST_CELL_KEYS
    if not isinstance(cell, Mapping) or set(cell) != keys:
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    expected_slice_track = (
        version_slice_track
        if version_slice_track is not None
        else cell.get("approved_test_origin_track")
        if stable
        else approval_track
    )
    errors.extend(
        _version_slice_shape_errors(
            cell.get("version_slice"),
            expected_track=expected_slice_track,
            label=f"{label}.version_slice",
        )
    )
    build_pin_id = cell.get("build_pin_id")
    pin = (
        pin_index.get(build_pin_id)
        if isinstance(build_pin_id, str)
        else None
    )
    if not isinstance(pin, Mapping):
        errors.append(f"{label}.build_pin_id is unknown")
    elif pin.get("core_id") != core_id:
        errors.append(f"{label}.build_pin_id belongs to another core")
    else:
        reproduction_digest = pin.get("host_reproduction_content_sha256")
        if (
            not isinstance(reproduction_digest, str)
            or SHA256_RE.fullmatch(reproduction_digest) is None
        ):
            errors.append(
                f"{label}.build_pin_id has no validated host reproduction proof"
            )
    profile_id = cell.get("tuning_profile")
    if not isinstance(profile_id, str) or PROFILE_ID_RE.fullmatch(profile_id) is None:
        errors.append(f"{label}.tuning_profile is invalid")
        tuning = None
    else:
        try:
            tuning = resolved_tuning_profile(tunings, profile_id)
        except PipelineError as exc:
            errors.append(f"{label}.tuning_profile is invalid: {exc}")
            tuning = None
    applicable = cell.get("applicable_chipsets")
    if (
        not isinstance(applicable, list)
        or any(not isinstance(chipset, str) for chipset in applicable)
        or applicable != sorted(set(applicable))
        or any(chipset not in REAL_CHIPSETS for chipset in applicable)
    ):
        errors.append(
            f"{label}.applicable_chipsets must be a unique sorted real-chipset list"
        )
        applicable = []
    if cell_chipset == "universal":
        if profile_id != UNIVERSAL_TUNING_PROFILE:
            errors.append(f"{label} universal cells require universal-v1 tuning")
        if isinstance(tuning, Mapping) and tuning.get("properties") != {}:
            errors.append(f"{label} universal tuning must resolve to no properties")
        if isinstance(pin, Mapping) and isinstance(tuning, Mapping):
            recorded_tuning = pin.get("tuning_identity")
            universal_identity = {
                "profile_id": tuning.get("profile_id"),
                "content_sha256": tuning.get("content_sha256"),
            }
            if recorded_tuning not in (None, universal_identity):
                errors.append(
                    f"{label} universal pin binds chipset-specific tuning"
                )
    else:
        if applicable != [cell_chipset]:
            errors.append(f"{label} exact chipset cells must apply only to themselves")
        if isinstance(tuning, Mapping) and tuning.get("chipset") != cell_chipset:
            errors.append(f"{label} tuning profile belongs to another chipset")
        # A typed tuning declaration is not build evidence.  The selected pin
        # must have recorded the same tuning identity before a tuned cell is
        # eligible for an inventory.
        if isinstance(pin, Mapping) and isinstance(tuning, Mapping):
            expected_identity = {
                "profile_id": tuning.get("profile_id"),
                "content_sha256": tuning.get("content_sha256"),
            }
            if pin.get("tuning_identity") != expected_identity:
                errors.append(f"{label} pin does not bind the selected tuning profile")
    if isinstance(pin, Mapping):
        architectures = set(pin.get("architectures", ()))
        for chipset in applicable:
            architecture = CHIPSET_ARCHITECTURES[chipset]
            if architecture not in architectures:
                errors.append(
                    f"{label} pin has no {architecture} target for chipset {chipset}"
                )
    if stable:
        variant_id = cell.get("approved_test_variant_id")
        if not isinstance(variant_id, str) or SHA256_RE.fullmatch(variant_id) is None:
            errors.append(f"{label}.approved_test_variant_id is invalid")
        elif isinstance(pin, Mapping) and isinstance(tuning, Mapping):
            expected_variant = core_variant_id(
                core_id=core_id,
                cell_chipset=cell_chipset,
                cell=cell,
                pin_index=pin_index,
                tunings=tunings,
            )
            if variant_id != expected_variant:
                errors.append(f"{label}.approved_test_variant_id is stale")
        if cell.get("approved_test_origin_track") not in TRACK_ANCESTORS[approval_track]:
            errors.append(f"{label}.approved_test_origin_track is invalid")
        if _canonical_utc_approval_timestamp(cell.get("approved_at")) is None:
            errors.append(f"{label}.approved_at is invalid")
        if (
            not isinstance(cell.get("approved_by"), str)
            or not cell["approved_by"].strip()
        ):
            errors.append(f"{label}.approved_by is invalid")
        if not isinstance(cell.get("reason"), str) or not cell["reason"].strip():
            errors.append(f"{label}.reason is invalid")
        previous_variant = cell.get("previous_stable_variant_id")
        if previous_variant is not None and (
            not isinstance(previous_variant, str)
            or SHA256_RE.fullmatch(previous_variant) is None
        ):
            errors.append(f"{label}.previous_stable_variant_id is invalid")
        source_digest = cell.get("source_registry_content_sha256")
        if not isinstance(source_digest, str) or SHA256_RE.fullmatch(source_digest) is None:
            errors.append(f"{label}.source_registry_content_sha256 is invalid")
    return errors


def _track_cells_errors(
    value: object,
    *,
    stable: bool,
    track: str,
    catalog_ids: set[str],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    label: str,
) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if list(value) != sorted(value):
        errors.append(f"{label} must be sorted by core ID")
    unknown = sorted(set(value) - catalog_ids)
    if unknown:
        errors.append(f"{label} contains uncataloged cores: " + ", ".join(unknown))
    for core_id, cells in value.items():
        core_label = f"{label}.{core_id}"
        if not isinstance(cells, Mapping) or not cells:
            errors.append(f"{core_label} must be a nonempty object")
            continue
        if list(cells) != sorted(cells):
            errors.append(f"{core_label} cells must be sorted by chipset")
        for chipset, cell in cells.items():
            if chipset not in CHIPSETS:
                errors.append(f"{core_label} contains unknown chipset {chipset}")
                continue
            errors.extend(
                _cell_errors(
                    core_id=core_id,
                    cell_chipset=chipset,
                    cell=cell,
                    stable=stable,
                    approval_track=track,
                    pin_index=pin_index,
                    tunings=tunings,
                    label=f"{core_label}.{chipset}",
                )
            )
    return errors


def _deferred_cells_errors(
    value: object,
    *,
    catalog_ids: set[str],
    label: str,
) -> list[str]:
    """Validate explicit cells without a reviewed version-channel build pin."""

    if not isinstance(value, Mapping):
        return [f"{label} must be an object"]
    errors: list[str] = []
    if list(value) != sorted(value):
        errors.append(f"{label} must be sorted by core ID")
    unknown = sorted(set(value) - catalog_ids)
    if unknown:
        errors.append(f"{label} contains uncataloged cores: " + ", ".join(unknown))
    for core_id, cells in value.items():
        core_label = f"{label}.{core_id}"
        if not isinstance(cells, Mapping) or not cells:
            errors.append(f"{core_label} must be a nonempty object")
            continue
        if list(cells) != sorted(cells):
            errors.append(f"{core_label} cells must be sorted by chipset")
        for chipset, cell in cells.items():
            cell_label = f"{core_label}.{chipset}"
            if chipset not in CHIPSETS:
                errors.append(f"{core_label} contains unknown chipset {chipset}")
                continue
            if not isinstance(cell, Mapping) or set(cell) != DEFERRED_CELL_KEYS:
                errors.append(f"{cell_label} fields are not exact")
                continue
            if cell.get("state") != DEFERRED_STATE:
                errors.append(f"{cell_label}.state is invalid")
            if cell.get("reason") != DEFERRED_NO_REVIEWED_VERSION_REASON:
                errors.append(f"{cell_label}.reason is invalid")
    return errors


def _effective_selection_cells_unchecked(
    tracks: Mapping[str, Any], track: str
) -> tuple[
    dict[tuple[str, str], tuple[dict[str, Any], str]],
    dict[tuple[str, str], tuple[dict[str, Any], str]],
]:
    """Resolve inherited pinned/deferred TEST states as an exclusive pair."""

    parent = TRACK_PARENTS[track]
    tests, deferred = (
        _effective_selection_cells_unchecked(tracks, parent)
        if parent is not None
        else ({}, {})
    )
    for core_id, cells in tracks[track]["deferred"].items():
        for chipset, cell in cells.items():
            key = (core_id, chipset)
            tests.pop(key, None)
            deferred[key] = (copy.deepcopy(cell), track)
    for core_id, cells in tracks[track]["test"].items():
        for chipset, cell in cells.items():
            key = (core_id, chipset)
            deferred.pop(key, None)
            tests[key] = (copy.deepcopy(cell), track)
    return tests, deferred


def _effective_test_cells_unchecked(
    tracks: Mapping[str, Any], track: str
) -> dict[tuple[str, str], tuple[dict[str, Any], str]]:
    return _effective_selection_cells_unchecked(tracks, track)[0]


def _effective_deferred_cells_unchecked(
    tracks: Mapping[str, Any], track: str
) -> dict[tuple[str, str], tuple[dict[str, Any], str]]:
    return _effective_selection_cells_unchecked(tracks, track)[1]


def _branch_comparison_binding_errors(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    main_release_roster: object,
    spruce_branch_bases: object,
    historical_snapshot_context: bool,
) -> list[str]:
    """Bind immutable comparison evidence without making it selection authority."""

    errors = spruce_release_roster_errors(main_release_roster, catalog=catalog)
    if historical_snapshot_context:
        if errors:
            return errors
        assert isinstance(main_release_roster, Mapping)
        registry_binding = document.get("spruce_branch_bases")
        if (
            not isinstance(registry_binding, Mapping)
            or set(registry_binding) != {"path", "content_sha256"}
            or registry_binding.get("path") != CORE_TRACK_SPRUCE_BRANCH_BASES_PATH
            or not isinstance(registry_binding.get("content_sha256"), str)
            or SHA256_RE.fullmatch(registry_binding["content_sha256"]) is None
        ):
            errors.append(
                "historical core track branch-basis registry binding is invalid"
            )
        historical = document.get("historical_release_correlation")
        if not isinstance(historical, Mapping) or set(historical) != {
            "roster_path",
            "roster_content_sha256",
        }:
            errors.append("historical release correlation fields are not exact")
        elif (
            historical.get("roster_path")
            != CORE_TRACK_MAIN_RELEASE_ROSTER_PATH
            or not isinstance(historical.get("roster_content_sha256"), str)
            or SHA256_RE.fullmatch(historical["roster_content_sha256"])
            is None
        ):
            # A source snapshot freezes the roster identity that existed when
            # it was captured.  Comparing it with today's roster would make a
            # valid historical slice expire after an ordinary roster/catalog
            # advance.  Its embedded, digest-bound slice authority validates
            # the frozen dependency bytes below.
            errors.append("historical release correlation binding is invalid")
        for track in CORE_TRACKS:
            binding = document["tracks"][track].get("spruce_branch_basis")
            if (
                not isinstance(binding, Mapping)
                or set(binding) != {"basis_id", "basis_content_sha256"}
                or binding.get("basis_id")
                != CORE_TRACK_SPRUCE_BRANCH_BASIS_IDS[track]
                or not isinstance(binding.get("basis_content_sha256"), str)
                or SHA256_RE.fullmatch(binding["basis_content_sha256"])
                is None
            ):
                errors.append(
                    f"tracks.{track}.spruce_branch_basis is invalid in "
                    "historical snapshot context"
                )
        return errors
    try:
        from .spruce_branch_bases import spruce_branch_bases_errors
    except ImportError:
        errors.append("Spruce branch-basis validator is unavailable")
        return errors
    try:
        repository_root = Path(__file__).resolve().parents[2]
        catalog_file_sha256 = sha256_file(
            repository_root / CORE_TRACK_CATALOG_PATH
        )
        roster_file_sha256 = sha256_file(
            repository_root / CORE_TRACK_MAIN_RELEASE_ROSTER_PATH
        )
    except OSError:
        errors.append("Spruce branch-basis dependency bytes are unavailable")
        return errors
    try:
        basis_errors = spruce_branch_bases_errors(
            spruce_branch_bases,
            catalog=catalog,
            catalog_file_sha256=catalog_file_sha256,
            roster=main_release_roster,
            roster_file_sha256=roster_file_sha256,
        )
    except Exception as exc:  # fail closed across the authority adapter
        errors.append(
            "Spruce branch-basis validation failed "
            f"({type(exc).__name__})"
        )
        return errors
    if not isinstance(basis_errors, list):
        errors.append("Spruce branch-basis validator returned an invalid report")
    else:
        errors.extend(str(error) for error in basis_errors)
    if errors:
        return errors
    assert isinstance(main_release_roster, Mapping)
    assert isinstance(spruce_branch_bases, Mapping)

    registry_binding = document.get("spruce_branch_bases")
    if not isinstance(registry_binding, Mapping) or set(registry_binding) != {
        "path",
        "content_sha256",
    }:
        errors.append("core track branch-basis registry binding fields are not exact")
    else:
        expected_registry_binding = {
            "path": CORE_TRACK_SPRUCE_BRANCH_BASES_PATH,
            "content_sha256": spruce_branch_bases.get("content_sha256"),
        }
        if dict(registry_binding) != expected_registry_binding:
            errors.append("core track branch-basis registry binding is stale")

    historical = document.get("historical_release_correlation")
    if not isinstance(historical, Mapping) or set(historical) != {
        "roster_path",
        "roster_content_sha256",
    }:
        errors.append("historical release correlation fields are not exact")
    elif dict(historical) != {
        "roster_path": CORE_TRACK_MAIN_RELEASE_ROSTER_PATH,
        "roster_content_sha256": main_release_roster["content_sha256"],
    }:
        errors.append("historical release correlation binding is stale")

    bases = spruce_branch_bases.get("bases")
    if not isinstance(bases, Mapping):
        errors.append("Spruce branch-basis index is unavailable")
        return errors
    for track in CORE_TRACKS:
        expected_basis_id = CORE_TRACK_SPRUCE_BRANCH_BASIS_IDS[track]
        basis = bases.get(expected_basis_id)
        binding = document["tracks"][track].get("spruce_branch_basis")
        if not isinstance(binding, Mapping) or set(binding) != {
            "basis_id",
            "basis_content_sha256",
        }:
            errors.append(
                f"tracks.{track}.spruce_branch_basis fields are not exact"
            )
            continue
        if not isinstance(basis, Mapping) or dict(binding) != {
            "basis_id": expected_basis_id,
            "basis_content_sha256": basis.get("content_sha256"),
        }:
            errors.append(f"tracks.{track}.spruce_branch_basis is stale")
    return errors


def _slice_comparison_basis_shape_errors(
    value: object, *, label: str
) -> list[str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != SLICE_COMPARISON_BASIS_KEYS
    ):
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    if value.get("model") != CORE_TRACK_SLICE_COMPARISON_BASIS_MODEL:
        errors.append(f"{label}.model is invalid")
    track = value.get("track")
    if track not in CORE_TRACKS:
        errors.append(f"{label}.track is invalid")
    if _canonical_utc_approval_timestamp(value.get("slice_time")) is None:
        errors.append(f"{label}.slice_time is invalid")
    for field in (
        "spruce_branch_registry_content_sha256",
        "basis_content_sha256",
        "content_sha256",
    ):
        digest = value.get(field)
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append(f"{label}.{field} is invalid")
    expected_basis_id = (
        CORE_TRACK_SPRUCE_BRANCH_BASIS_IDS.get(track)
        if isinstance(track, str)
        else None
    )
    if value.get("basis_id") != expected_basis_id:
        errors.append(f"{label}.basis_id is invalid")
    branch = value.get("branch")
    if (
        not isinstance(branch, Mapping)
        or set(branch) != SLICE_COMPARISON_BRANCH_KEYS
    ):
        errors.append(f"{label}.branch fields are not exact")
    else:
        if not isinstance(branch.get("repository"), str) or not branch[
            "repository"
        ]:
            errors.append(f"{label}.branch.repository is invalid")
        ref = branch.get("ref")
        if (
            not isinstance(ref, str)
            or re.fullmatch(r"refs/heads/[^\s]+", ref) is None
        ):
            errors.append(f"{label}.branch.ref is invalid")
        for field in ("commit", "tree"):
            item = branch.get(field)
            if not isinstance(item, str) or SHA1_RE.fullmatch(item) is None:
                errors.append(f"{label}.branch.{field} is invalid")
    if value.get("content_sha256") != slice_comparison_basis_content_sha256(
        value
    ):
        errors.append(f"{label}.content_sha256 is stale")
    return errors


def _slice_comparison_basis_index_errors(
    value: object,
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    if not isinstance(value, Mapping):
        return {}, ["version_policy.slice_comparison_bases must be an object"]
    errors: list[str] = []
    if list(value) != sorted(value):
        errors.append("version_policy.slice_comparison_bases must be sorted")
    index: dict[str, Mapping[str, Any]] = {}
    for digest, comparison_basis in value.items():
        label = f"version_policy.slice_comparison_bases.{digest}"
        if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
            errors.append(f"{label} key is invalid")
            continue
        errors.extend(
            _slice_comparison_basis_shape_errors(
                comparison_basis,
                label=label,
            )
        )
        if not isinstance(comparison_basis, Mapping):
            continue
        synthetic_slice = {
            "model": CORE_TRACK_VERSION_SLICE_MODEL,
            "track": comparison_basis.get("track"),
            "slice_time": comparison_basis.get("slice_time"),
            "content_sha256": digest,
        }
        if digest != version_slice_content_sha256(
            synthetic_slice,
            comparison_basis=comparison_basis,
        ):
            errors.append(f"{label} key is stale")
        index[digest] = comparison_basis
    return index, errors


def _slice_branch_basis_snapshot_errors(
    value: object, *, registry_digest: str, label: str
) -> list[str]:
    if (
        not isinstance(value, Mapping)
        or set(value) != SLICE_BRANCH_BASIS_SNAPSHOT_KEYS
    ):
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    if value.get("model") != CORE_TRACK_SLICE_BRANCH_BASIS_SNAPSHOT_MODEL:
        errors.append(f"{label}.model is invalid")
    for field in ("catalog_file_sha256", "release_roster_file_sha256"):
        item = value.get(field)
        if not isinstance(item, str) or SHA256_RE.fullmatch(item) is None:
            errors.append(f"{label}.{field} is invalid")
    branch_bases = value.get("branch_bases")
    catalog = value.get("catalog")
    roster = value.get("release_roster")
    if not isinstance(branch_bases, Mapping):
        errors.append(f"{label}.branch_bases is invalid")
    if not isinstance(catalog, Mapping):
        errors.append(f"{label}.catalog is invalid")
    if not isinstance(roster, Mapping):
        errors.append(f"{label}.release_roster is invalid")
    digest = value.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        errors.append(f"{label}.content_sha256 is invalid")
    elif digest != slice_branch_basis_snapshot_content_sha256(value):
        errors.append(f"{label}.content_sha256 is stale")
    if isinstance(branch_bases, Mapping):
        try:
            from .spruce_branch_bases import (
                spruce_branch_bases_content_sha256,
                spruce_branch_bases_detached_snapshot_errors,
            )
        except ImportError:
            errors.append(f"{label} validator is unavailable")
        else:
            if (
                branch_bases.get("content_sha256") != registry_digest
                or spruce_branch_bases_content_sha256(branch_bases)
                != registry_digest
            ):
                errors.append(f"{label}.branch_bases identity is stale")
            if isinstance(catalog, Mapping) and isinstance(roster, Mapping):
                try:
                    detached_errors = spruce_branch_bases_detached_snapshot_errors(
                        branch_bases,
                        catalog=catalog,
                        catalog_file_sha256=str(
                            value.get("catalog_file_sha256")
                        ),
                        roster=roster,
                        roster_file_sha256=str(
                            value.get("release_roster_file_sha256")
                        ),
                    )
                except Exception as exc:
                    errors.append(
                        f"{label} validator failed ({type(exc).__name__})"
                    )
                else:
                    if not isinstance(detached_errors, list):
                        errors.append(f"{label} validator report is invalid")
                    else:
                        errors.extend(
                            f"{label}: {error}" for error in detached_errors
                        )
    return errors


def _slice_branch_basis_snapshot_index_errors(
    value: object,
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    if not isinstance(value, Mapping):
        return {}, [
            "version_policy.slice_branch_basis_snapshots must be an object"
        ]
    errors: list[str] = []
    if list(value) != sorted(value):
        errors.append("version_policy.slice_branch_basis_snapshots must be sorted")
    index: dict[str, Mapping[str, Any]] = {}
    for registry_digest, snapshot in value.items():
        label = f"version_policy.slice_branch_basis_snapshots.{registry_digest}"
        if (
            not isinstance(registry_digest, str)
            or SHA256_RE.fullmatch(registry_digest) is None
        ):
            errors.append(f"{label} key is invalid")
            continue
        errors.extend(
            _slice_branch_basis_snapshot_errors(
                snapshot,
                registry_digest=registry_digest,
                label=label,
            )
        )
        if isinstance(snapshot, Mapping):
            index[registry_digest] = snapshot
    return index, errors


def _version_slice_registry_errors(
    document: Mapping[str, Any],
    *,
    spruce_branch_bases: object,
    canonical_basis_authenticated: bool,
) -> list[str]:
    """Bind every direct TEST/STABLE slice to append-only comparison evidence."""

    policy = document.get("version_policy")
    comparison_value = (
        policy.get("slice_comparison_bases")
        if isinstance(policy, Mapping)
        else None
    )
    comparison_index, errors = _slice_comparison_basis_index_errors(
        comparison_value
    )
    snapshot_value = (
        policy.get("slice_branch_basis_snapshots")
        if isinstance(policy, Mapping)
        else None
    )
    snapshot_index, snapshot_errors = _slice_branch_basis_snapshot_index_errors(
        snapshot_value
    )
    errors.extend(snapshot_errors)
    tracks = document.get("tracks")
    if not isinstance(tracks, Mapping):
        return errors
    for track in CORE_TRACKS:
        track_value = tracks.get(track)
        if not isinstance(track_value, Mapping):
            continue
        for marker in ("test", "stable"):
            cells_by_core = track_value.get(marker)
            if not isinstance(cells_by_core, Mapping):
                continue
            for core_id, cells in cells_by_core.items():
                if not isinstance(cells, Mapping):
                    continue
                for chipset, cell in cells.items():
                    if not isinstance(cell, Mapping):
                        continue
                    label = f"tracks.{track}.{marker}.{core_id}.{chipset}"
                    version_slice = cell.get("version_slice")
                    if not isinstance(version_slice, Mapping):
                        continue
                    digest = version_slice.get("content_sha256")
                    comparison_basis = comparison_index.get(digest)
                    if not isinstance(comparison_basis, Mapping):
                        errors.append(
                            f"{label}.version_slice has no comparison-basis record"
                        )
                        continue
                    if (
                        comparison_basis.get("track")
                        != version_slice.get("track")
                        or comparison_basis.get("slice_time")
                        != version_slice.get("slice_time")
                    ):
                        errors.append(
                            f"{label}.version_slice differs from its comparison basis"
                        )
                    if digest != version_slice_content_sha256(
                        version_slice,
                        comparison_basis=comparison_basis,
                    ):
                        errors.append(f"{label}.version_slice.content_sha256 is stale")
                    authenticated = False
                    if canonical_basis_authenticated and isinstance(
                        spruce_branch_bases, Mapping
                    ):
                        try:
                            canonical_projection = (
                                _slice_comparison_basis_projection(
                                    track=str(version_slice.get("track")),
                                    slice_time=str(version_slice.get("slice_time")),
                                    spruce_branch_bases=spruce_branch_bases,
                                )
                            )
                        except (KeyError, PipelineError):
                            canonical_projection = None
                        authenticated = comparison_basis == canonical_projection
                    if not authenticated:
                        registry_digest = comparison_basis.get(
                            "spruce_branch_registry_content_sha256"
                        )
                        snapshot = snapshot_index.get(registry_digest)
                        branch_snapshot = (
                            snapshot.get("branch_bases")
                            if isinstance(snapshot, Mapping)
                            else None
                        )
                        if isinstance(branch_snapshot, Mapping):
                            try:
                                historical_projection = (
                                    _slice_comparison_basis_projection(
                                        track=str(version_slice.get("track")),
                                        slice_time=str(
                                            version_slice.get("slice_time")
                                        ),
                                        spruce_branch_bases=branch_snapshot,
                                    )
                                )
                            except (KeyError, PipelineError):
                                historical_projection = None
                            authenticated = (
                                comparison_basis == historical_projection
                            )
                    if not authenticated:
                        errors.append(
                            f"{label}.version_slice comparison basis is unauthenticated"
                        )
    return errors


def _version_policy_errors(
    document: Mapping[str, Any], *, catalog: Mapping[str, Any]
) -> list[str]:
    """Validate the manual channel labels and self-contained Edge review heads."""

    policy = document.get("version_policy")
    if not isinstance(policy, Mapping) or set(policy) != {
        "assignment_model",
        "slice_model",
        "slice_comparison_bases",
        "slice_branch_basis_snapshots",
        "source_order_model",
        "levels",
        "edge_latest",
    }:
        return ["core track version_policy fields are not exact"]
    errors: list[str] = []
    if policy.get("assignment_model") != CORE_TRACK_VERSION_ASSIGNMENT_MODEL:
        errors.append("core track version assignment model is invalid")
    if policy.get("slice_model") != CORE_TRACK_VERSION_SLICE_MODEL:
        errors.append("core track version slice model is invalid")
    _slice_index, slice_errors = _slice_comparison_basis_index_errors(
        policy.get("slice_comparison_bases")
    )
    errors.extend(slice_errors)
    _snapshot_index, snapshot_errors = _slice_branch_basis_snapshot_index_errors(
        policy.get("slice_branch_basis_snapshots")
    )
    errors.extend(snapshot_errors)
    if policy.get("source_order_model") != CORE_TRACK_SOURCE_ORDER_MODEL:
        errors.append("core track source order model is invalid")
    if policy.get("levels") != CORE_TRACK_VERSION_LEVELS:
        errors.append("core track version levels are invalid")
    edge_latest = policy.get("edge_latest")
    if not isinstance(edge_latest, Mapping) or set(edge_latest) != {
        "model",
        "snapshot",
        "heads",
    }:
        errors.append("core track Edge latest policy fields are not exact")
        return errors
    if edge_latest.get("model") != CORE_TRACK_EDGE_LATEST_MODEL:
        errors.append("core track Edge latest model is invalid")
    snapshot = edge_latest.get("snapshot")
    if not isinstance(snapshot, Mapping) or set(snapshot) != EDGE_SNAPSHOT_KEYS:
        errors.append("core track Edge reviewed snapshot fields are not exact")
    else:
        snapshot_id = snapshot.get("snapshot_id")
        if (
            not isinstance(snapshot_id, str)
            or IDENTIFIER_RE.fullmatch(snapshot_id) is None
        ):
            errors.append("core track Edge reviewed snapshot ID is invalid")
        if _canonical_utc_approval_timestamp(snapshot.get("captured_at")) is None:
            errors.append("core track Edge reviewed snapshot timestamp is invalid")
        for field in ("file_sha256", "content_sha256"):
            value = snapshot.get(field)
            if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
                errors.append(
                    f"core track Edge reviewed snapshot {field} is invalid"
                )
    heads = edge_latest.get("heads")
    catalog_cores = catalog.get("cores")
    assert isinstance(catalog_cores, Mapping)
    if not isinstance(heads, Mapping):
        errors.append("core track Edge reviewed heads must be an object")
        return errors
    if list(heads) != sorted(heads):
        errors.append("core track Edge reviewed heads must be sorted by core ID")
    if set(heads) != set(catalog_cores):
        errors.append("core track Edge reviewed heads differ from the core catalog")
    for core_id, head in heads.items():
        label = f"version_policy.edge_latest.heads.{core_id}"
        if (
            not isinstance(core_id, str)
            or CORE_ID_RE.fullmatch(core_id) is None
            or not isinstance(head, Mapping)
            or set(head) != EDGE_HEAD_KEYS
        ):
            errors.append(f"{label} fields are not exact")
            continue
        repository = head.get("repository")
        requested_ref = head.get("requested_ref")
        if not isinstance(repository, str) or not repository:
            errors.append(f"{label}.repository is invalid")
        if (
            not isinstance(requested_ref, str)
            or re.fullmatch(r"refs/(?:heads|tags)/[^\s]+", requested_ref) is None
        ):
            errors.append(f"{label}.requested_ref is invalid")
        for field in ("commit", "tree"):
            value = head.get(field)
            if not isinstance(value, str) or SHA1_RE.fullmatch(value) is None:
                errors.append(f"{label}.{field} is invalid")
        latest_semantics = head.get("latest_semantics")
        if latest_semantics not in {
            "exact-branch-tip",
            "catalog-tag-only-not-latest",
        }:
            errors.append(f"{label}.latest_semantics is invalid")
        if head.get("status") not in {"unchanged", "fast-forward", "diverged"}:
            errors.append(f"{label}.status is invalid")
        if latest_semantics == "exact-branch-tip" and (
            not isinstance(requested_ref, str)
            or not requested_ref.startswith("refs/heads/")
        ):
            errors.append(f"{label} exact branch-tip semantics require a branch ref")
        if latest_semantics == "catalog-tag-only-not-latest" and (
            not isinstance(requested_ref, str)
            or not requested_ref.startswith("refs/tags/")
        ):
            errors.append(f"{label} tag-only semantics require a tag ref")
        catalog_core = catalog_cores.get(core_id)
        catalog_source = (
            catalog_core.get("source") if isinstance(catalog_core, Mapping) else None
        )
        if isinstance(catalog_source, Mapping) and (
            repository != catalog_source.get("url")
            or requested_ref != catalog_source.get("requested_ref")
        ):
            errors.append(f"{label} repository/ref differ from the core catalog")
    return errors


def _edge_reviewed_head(
    document: Mapping[str, Any], core_id: str
) -> Mapping[str, Any] | None:
    policy = document.get("version_policy")
    edge_latest = policy.get("edge_latest") if isinstance(policy, Mapping) else None
    heads = edge_latest.get("heads") if isinstance(edge_latest, Mapping) else None
    head = heads.get(core_id) if isinstance(heads, Mapping) else None
    return head if isinstance(head, Mapping) else None


def _pin_matches_edge_reviewed_head(
    document: Mapping[str, Any], *, core_id: str, pin: Mapping[str, Any]
) -> bool:
    head = _edge_reviewed_head(document, core_id)
    return bool(
        isinstance(head, Mapping)
        and head.get("latest_semantics") == "exact-branch-tip"
        # A reviewed divergent branch tip is still objectively latest.  Its
        # channel-order inversion remains gated by an exact source-order
        # outlier rather than being conflated with latest-head identity.
        and head.get("status") in {"unchanged", "fast-forward", "diverged"}
        and pin.get("source_repository") == head.get("repository")
        and pin.get("source_requested_ref") == head.get("requested_ref")
        and pin.get("source_commit") == head.get("commit")
        and pin.get("source_tree") == head.get("tree")
    )


def _edge_latest_errors(
    document: Mapping[str, Any], *, pin_index: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Require every executable Edge pin to equal its latest reviewed head."""

    errors: list[str] = []
    effective_test = _effective_test_cells_unchecked(document["tracks"], "edge")
    executable_cells = [
        ("test", core_id, chipset, cell)
        for (core_id, chipset), (cell, _origin) in effective_test.items()
    ]
    for marker, core_id, chipset, cell in executable_cells:
        pin = pin_index.get(cell.get("build_pin_id"))
        if not isinstance(pin, Mapping) or not _pin_matches_edge_reviewed_head(
            document, core_id=core_id, pin=pin
        ):
            errors.append(
                f"tracks.edge.{marker}.{core_id}.{chipset} pin does not match "
                "the latest reviewed upstream head"
            )
    return errors


def _parent_test_candidate(
    tracks: Mapping[str, Any],
    *,
    parent: str,
    core_id: str,
    chipset: str,
) -> tuple[dict[str, Any], str, str] | None:
    effective = _effective_test_cells_unchecked(tracks, parent)
    exact = effective.get((core_id, chipset))
    if exact is not None:
        cell, origin = exact
        return cell, origin, chipset
    if chipset == "universal":
        return None
    universal = effective.get((core_id, "universal"))
    if universal is None:
        return None
    cell, origin = universal
    if chipset not in cell.get("applicable_chipsets", ()):
        return None
    return cell, origin, "universal"


def source_order_parent_selection_content_sha256(
    binding: Mapping[str, Any],
) -> str:
    """Return the identity of only the frozen parent selection proof."""

    parent_cell = binding.get("parent_cell")
    return _semantic_sha256(
        {
            "model": SOURCE_ORDER_PARENT_SELECTION_MODEL,
            "track": binding.get("track"),
            "core_id": binding.get("core_id"),
            "requested_chipset": binding.get("chipset"),
            "parent_track": binding.get("parent_track"),
            "parent_origin_track": binding.get("parent_origin_track"),
            "parent_selected_chipset": binding.get("parent_selected_chipset"),
            "parent_cell": (
                _cell_projection(parent_cell)
                if isinstance(parent_cell, Mapping)
                else None
            ),
            "parent_variant_id": binding.get("parent_variant_id"),
            "parent_build_pin_id": binding.get("parent_build_pin_id"),
            "parent_pin_content_sha256": binding.get(
                "parent_pin_content_sha256"
            ),
            "parent_source_repository": binding.get(
                "parent_source_repository"
            ),
            "parent_source_requested_ref": binding.get(
                "parent_source_requested_ref"
            ),
            "parent_source_commit": binding.get("parent_source_commit"),
            "parent_source_tree": binding.get("parent_source_tree"),
            "parent_lineage": binding.get("parent_lineage"),
        }
    )


def source_order_parent_binding_content_sha256(
    binding: Mapping[str, Any],
) -> str:
    """Return the semantic identity of one frozen assignment-time parent."""

    return _semantic_sha256(
        {
            key: binding.get(key)
            for key in sorted(
                SOURCE_ORDER_PARENT_BINDING_KEYS - {"content_sha256"}
            )
        }
    )


def _source_order_record_coordinate(
    record: Mapping[str, Any],
) -> tuple[str, str, str] | None:
    track = record.get("track")
    core_id = record.get("core_id")
    chipset = record.get("chipset")
    if (
        track not in {"nightly", "edge"}
        or not isinstance(core_id, str)
        or CORE_ID_RE.fullmatch(core_id) is None
        or chipset not in CHIPSETS
    ):
        return None
    return track, core_id, chipset


def _source_order_outlier_shape_errors(
    record: object, *, label: str
) -> list[str]:
    if not isinstance(record, Mapping) or set(record) != SOURCE_ORDER_OUTLIER_KEYS:
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    coordinate = _source_order_record_coordinate(record)
    track = record.get("track")
    if coordinate is None:
        errors.append(f"{label} coordinate is invalid")
    if record.get("marker") != "test":
        errors.append(f"{label}.marker is invalid")
    if not isinstance(record.get("child_cell"), Mapping) or set(
        record.get("child_cell", {})
    ) != TEST_CELL_KEYS:
        errors.append(f"{label}.child_cell fields are not exact")
    expected_parent = TRACK_PARENTS.get(track) if isinstance(track, str) else None
    if record.get("parent_track") != expected_parent:
        errors.append(f"{label}.parent_track is invalid")
    for field in (
        "parent_binding_content_sha256",
        "child_variant_id",
        "child_pin_content_sha256",
    ):
        item = record.get(field)
        if not isinstance(item, str) or SHA256_RE.fullmatch(item) is None:
            errors.append(f"{label}.{field} is invalid")
    child_pin_id = record.get("child_build_pin_id")
    if not isinstance(child_pin_id, str) or IDENTIFIER_RE.fullmatch(child_pin_id) is None:
        errors.append(f"{label}.child_build_pin_id is invalid")
    for field in ("child_source_repository", "child_source_requested_ref"):
        item = record.get(field)
        if not isinstance(item, str) or not item:
            errors.append(f"{label}.{field} is invalid")
    for field in ("child_source_commit", "child_source_tree"):
        item = record.get(field)
        if not isinstance(item, str) or SHA1_RE.fullmatch(item) is None:
            errors.append(f"{label}.{field} is invalid")
    if _canonical_utc_approval_timestamp(record.get("authorized_at")) is None:
        errors.append(f"{label}.authorized_at is invalid")
    for field in ("authorized_by", "reason"):
        item = record.get(field)
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}.{field} is invalid")
    return errors


def _source_order_parent_binding_shape_errors(
    record: object, *, label: str, lineage_depth: int = 0
) -> list[str]:
    if (
        not isinstance(record, Mapping)
        or set(record) != SOURCE_ORDER_PARENT_BINDING_KEYS
    ):
        return [f"{label} fields are not exact"]
    errors: list[str] = []
    coordinate = _source_order_record_coordinate(record)
    track = record.get("track")
    if coordinate is None:
        errors.append(f"{label} coordinate is invalid")
    if record.get("model") != SOURCE_ORDER_PARENT_BINDING_MODEL:
        errors.append(f"{label}.model is invalid")
    expected_parent = TRACK_PARENTS.get(track) if isinstance(track, str) else None
    if record.get("parent_track") != expected_parent:
        errors.append(f"{label}.parent_track is invalid")
    parent_origin = record.get("parent_origin_track")
    if (
        not isinstance(expected_parent, str)
        or parent_origin not in TRACK_ANCESTORS[expected_parent]
    ):
        errors.append(f"{label}.parent_origin_track is invalid")
    if record.get("parent_selected_chipset") not in CHIPSETS:
        errors.append(f"{label}.parent_selected_chipset is invalid")
    if not isinstance(record.get("parent_cell"), Mapping) or set(
        record.get("parent_cell", {})
    ) != TEST_CELL_KEYS:
        errors.append(f"{label}.parent_cell fields are not exact")
    if not isinstance(record.get("child_cell"), Mapping) or set(
        record.get("child_cell", {})
    ) != TEST_CELL_KEYS:
        errors.append(f"{label}.child_cell fields are not exact")
    for field in (
        "captured_registry_content_sha256",
        "parent_variant_id",
        "parent_pin_content_sha256",
        "parent_selection_content_sha256",
        "child_variant_id",
        "child_pin_content_sha256",
        "content_sha256",
    ):
        item = record.get(field)
        if not isinstance(item, str) or SHA256_RE.fullmatch(item) is None:
            errors.append(f"{label}.{field} is invalid")
    for field in ("parent_build_pin_id", "child_build_pin_id"):
        item = record.get(field)
        if not isinstance(item, str) or IDENTIFIER_RE.fullmatch(item) is None:
            errors.append(f"{label}.{field} is invalid")
    for prefix in ("parent", "child"):
        for suffix in ("source_repository", "source_requested_ref"):
            field = f"{prefix}_{suffix}"
            item = record.get(field)
            if not isinstance(item, str) or not item:
                errors.append(f"{label}.{field} is invalid")
        for suffix in ("source_commit", "source_tree"):
            field = f"{prefix}_{suffix}"
            item = record.get(field)
            if not isinstance(item, str) or SHA1_RE.fullmatch(item) is None:
                errors.append(f"{label}.{field} is invalid")
    lineage = record.get("parent_lineage")
    if lineage is not None:
        if (
            not isinstance(lineage, Mapping)
            or set(lineage) != SOURCE_ORDER_PARENT_LINEAGE_KEYS
        ):
            errors.append(f"{label}.parent_lineage fields are not exact")
        elif lineage_depth >= 1:
            errors.append(f"{label}.parent_lineage exceeds channel depth")
        else:
            errors.extend(
                _source_order_parent_binding_shape_errors(
                    lineage.get("binding"),
                    label=f"{label}.parent_lineage.binding",
                    lineage_depth=lineage_depth + 1,
                )
            )
            nested_outlier = lineage.get("outlier")
            if nested_outlier is not None:
                errors.extend(
                    _source_order_outlier_shape_errors(
                        nested_outlier,
                        label=f"{label}.parent_lineage.outlier",
                    )
                )
    if record.get("content_sha256") != source_order_parent_binding_content_sha256(
        record
    ):
        errors.append(f"{label}.content_sha256 is stale")
    if record.get(
        "parent_selection_content_sha256"
    ) != source_order_parent_selection_content_sha256(record):
        errors.append(f"{label}.parent_selection_content_sha256 is stale")
    return errors


def _source_order_parent_binding_index(
    value: object,
) -> tuple[dict[tuple[str, str, str], Mapping[str, Any]], list[str]]:
    if not isinstance(value, list):
        return {}, ["source_order_parent_bindings must be a list"]
    errors: list[str] = []
    index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    coordinates: list[tuple[int, str, str]] = []
    for position, record in enumerate(value):
        label = f"source_order_parent_bindings[{position}]"
        errors.extend(
            _source_order_parent_binding_shape_errors(record, label=label)
        )
        if not isinstance(record, Mapping):
            continue
        coordinate = _source_order_record_coordinate(record)
        if coordinate is None:
            continue
        track, core_id, chipset = coordinate
        if coordinate in index:
            errors.append(
                "source_order_parent_bindings repeats coordinate "
                f"{track}/{core_id}/{chipset}"
            )
        else:
            index[coordinate] = record
        coordinates.append((CORE_TRACKS.index(track), core_id, chipset))
    if coordinates != sorted(coordinates):
        errors.append(
            "source_order_parent_bindings must be sorted by track/core/chipset"
        )
    return index, errors


def _source_order_outlier_index(
    value: object,
) -> tuple[dict[tuple[str, str, str], Mapping[str, Any]], list[str]]:
    """Validate and index exact, manually authorized TEST-order exceptions."""

    if not isinstance(value, list):
        return {}, ["source_order_outliers must be a list"]
    errors: list[str] = []
    index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    coordinates: list[tuple[int, str, str]] = []
    for position, record in enumerate(value):
        label = f"source_order_outliers[{position}]"
        errors.extend(_source_order_outlier_shape_errors(record, label=label))
        if not isinstance(record, Mapping):
            continue
        coordinate = _source_order_record_coordinate(record)
        if coordinate is None:
            continue
        track, core_id, chipset = coordinate
        if coordinate in index:
            errors.append(
                "source_order_outliers repeats coordinate "
                f"{track}/{core_id}/{chipset}"
            )
        else:
            index[coordinate] = record
        coordinates.append((CORE_TRACKS.index(track), core_id, chipset))
    if coordinates != sorted(coordinates):
        errors.append("source_order_outliers must be sorted by track/core/chipset")
    return index, errors


def _source_order_child_identity(
    *, child_cell: Mapping[str, Any], child_pin: Mapping[str, Any], child_variant: str
) -> dict[str, Any]:
    return {
        "child_cell": _cell_projection(child_cell),
        "child_variant_id": child_variant,
        "child_build_pin_id": child_cell["build_pin_id"],
        "child_pin_content_sha256": child_pin["content_sha256"],
        "child_source_repository": child_pin["source_repository"],
        "child_source_requested_ref": child_pin["source_requested_ref"],
        "child_source_commit": child_pin["source_commit"],
        "child_source_tree": child_pin["source_tree"],
    }


def _source_order_parent_binding(
    *,
    source_registry_content_sha256: str,
    track: str,
    core_id: str,
    chipset: str,
    parent_origin_track: str,
    parent_selected_chipset: str,
    parent_cell: Mapping[str, Any],
    parent_pin: Mapping[str, Any],
    parent_variant: str,
    parent_lineage: Mapping[str, Any] | None,
    child_cell: Mapping[str, Any],
    child_pin: Mapping[str, Any],
    child_variant: str,
) -> dict[str, Any]:
    parent = TRACK_PARENTS[track]
    assert parent is not None
    binding = {
        "model": SOURCE_ORDER_PARENT_BINDING_MODEL,
        "track": track,
        "core_id": core_id,
        "chipset": chipset,
        "captured_registry_content_sha256": source_registry_content_sha256,
        "parent_track": parent,
        "parent_origin_track": parent_origin_track,
        "parent_selected_chipset": parent_selected_chipset,
        "parent_cell": _cell_projection(parent_cell),
        "parent_variant_id": parent_variant,
        "parent_build_pin_id": parent_cell["build_pin_id"],
        "parent_pin_content_sha256": parent_pin["content_sha256"],
        "parent_source_repository": parent_pin["source_repository"],
        "parent_source_requested_ref": parent_pin["source_requested_ref"],
        "parent_source_commit": parent_pin["source_commit"],
        "parent_source_tree": parent_pin["source_tree"],
        "parent_lineage": copy.deepcopy(parent_lineage),
        "parent_selection_content_sha256": "",
        **_source_order_child_identity(
            child_cell=child_cell,
            child_pin=child_pin,
            child_variant=child_variant,
        ),
        "content_sha256": "",
    }
    binding["parent_selection_content_sha256"] = (
        source_order_parent_selection_content_sha256(binding)
    )
    binding["content_sha256"] = source_order_parent_binding_content_sha256(binding)
    return binding


def _source_order_outlier_binding(
    *, parent_binding: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "marker": "test",
        "track": parent_binding["track"],
        "core_id": parent_binding["core_id"],
        "chipset": parent_binding["chipset"],
        "parent_track": parent_binding["parent_track"],
        "parent_binding_content_sha256": parent_binding["content_sha256"],
        **{
            key: parent_binding[key]
            for key in (
                "child_cell",
                "child_variant_id",
                "child_build_pin_id",
                "child_pin_content_sha256",
                "child_source_repository",
                "child_source_requested_ref",
                "child_source_commit",
                "child_source_tree",
            )
        },
    }


def _outlier_matches_binding(
    record: Mapping[str, Any], binding: Mapping[str, Any]
) -> bool:
    return all(record.get(key) == value for key, value in binding.items())


def _captured_parent_selection_errors(
    binding: Mapping[str, Any],
    *,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    label: str,
) -> list[str]:
    """Reconstruct one frozen parent from its canonical captured registry."""

    digest = binding.get("captured_registry_content_sha256")
    entry = source_registry_index.get(digest) if isinstance(digest, str) else None
    source = entry.get("source_registry") if isinstance(entry, Mapping) else None
    if not isinstance(source, Mapping):
        return [f"{label} captured parent registry snapshot is missing"]
    if (
        source.get("$schema") != CORE_TRACK_SCHEMA_REF
        or source.get("schema_version") != CORE_TRACK_SCHEMA_VERSION
        or source.get("content_sha256") != digest
        or core_tracks_content_sha256(source) != digest
    ):
        return [f"{label} captured parent registry snapshot is invalid"]
    tracks = source.get("tracks")
    if not isinstance(tracks, Mapping):
        return [f"{label} captured parent registry has no tracks"]
    if _version_slice_registry_errors(
        source,
        spruce_branch_bases={},
        canonical_basis_authenticated=False,
    ):
        return [f"{label} captured parent version-slice evidence is invalid"]
    track = binding.get("track")
    core_id = binding.get("core_id")
    chipset = binding.get("chipset")
    parent_track = TRACK_PARENTS.get(track) if isinstance(track, str) else None
    if (
        not isinstance(parent_track, str)
        or not isinstance(core_id, str)
        or chipset not in CHIPSETS
    ):
        return [f"{label} captured parent coordinate is invalid"]
    try:
        predecessor = _parent_test_candidate(
            tracks,
            parent=parent_track,
            core_id=core_id,
            chipset=str(chipset),
        )
    except (KeyError, TypeError):
        predecessor = None
    if predecessor is None:
        return [f"{label} captured parent registry has no exact predecessor"]
    parent_cell, parent_origin, parent_chipset = predecessor
    parent_pin = pin_index.get(parent_cell.get("build_pin_id"))
    if not isinstance(parent_pin, Mapping):
        return [f"{label} captured parent pin is not authoritative"]
    try:
        parent_variant = core_variant_id(
            core_id=core_id,
            cell_chipset=parent_chipset,
            cell=parent_cell,
            pin_index=pin_index,
            tunings=tunings,
        )
    except PipelineError:
        return [f"{label} captured parent variant is invalid"]

    parent_lineage = None
    errors: list[str] = []
    if track == "edge" and parent_origin == "nightly":
        binding_index, binding_errors = _source_order_parent_binding_index(
            source.get("source_order_parent_bindings")
        )
        outlier_index, outlier_errors = _source_order_outlier_index(
            source.get("source_order_outliers")
        )
        if binding_errors or outlier_errors:
            errors.append(
                f"{label} captured direct Nightly lineage registry is invalid"
            )
        parent_coordinate = ("nightly", core_id, parent_chipset)
        frozen_parent = binding_index.get(parent_coordinate)
        if frozen_parent is None:
            errors.append(
                f"{label} captured direct Nightly lineage binding is missing"
            )
        else:
            parent_lineage = {
                "binding": copy.deepcopy(frozen_parent),
                "outlier": copy.deepcopy(outlier_index.get(parent_coordinate)),
            }
    expected_parent = {
        "parent_track": parent_track,
        "parent_origin_track": parent_origin,
        "parent_selected_chipset": parent_chipset,
        "parent_cell": _cell_projection(parent_cell),
        "parent_variant_id": parent_variant,
        "parent_build_pin_id": parent_cell["build_pin_id"],
        "parent_pin_content_sha256": parent_pin.get("content_sha256"),
        "parent_source_repository": parent_pin.get("source_repository"),
        "parent_source_requested_ref": parent_pin.get("source_requested_ref"),
        "parent_source_commit": parent_pin.get("source_commit"),
        "parent_source_tree": parent_pin.get("source_tree"),
        "parent_lineage": parent_lineage,
    }
    if any(binding.get(key) != value for key, value in expected_parent.items()):
        errors.append(f"{label} frozen parent differs from its captured registry")
    expected_selection = {
        **dict(binding),
        **expected_parent,
    }
    if binding.get(
        "parent_selection_content_sha256"
    ) != source_order_parent_selection_content_sha256(expected_selection):
        errors.append(
            f"{label} parent selection identity differs from its captured registry"
        )
    return errors


def _frozen_source_order_binding_errors(
    binding: Mapping[str, Any],
    *,
    outlier: Mapping[str, Any] | None,
    expected_child_cell: Mapping[str, Any],
    source_registry_index: Mapping[str, Mapping[str, Any]],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    source_ancestry_core_id: str | None,
    label: str,
) -> tuple[list[str], bool]:
    """Validate one frozen edge and its bounded historical lineage."""

    errors: list[str] = []
    track = str(binding["track"])
    core_id = str(binding["core_id"])
    chipset = str(binding["chipset"])
    parent_track = str(binding["parent_track"])
    parent_cell = binding["parent_cell"]
    parent_pin = pin_index.get(binding["parent_build_pin_id"])
    child_pin = pin_index.get(expected_child_cell.get("build_pin_id"))
    if not isinstance(parent_pin, Mapping):
        errors.append(f"{label} parent pin is not authoritative")
        return errors, False
    if not isinstance(child_pin, Mapping):
        errors.append(f"{label} child pin is not authoritative")
        return errors, False
    errors.extend(
        _captured_parent_selection_errors(
            binding,
            source_registry_index=source_registry_index,
            pin_index=pin_index,
            tunings=tunings,
            label=label,
        )
    )
    errors.extend(
        _cell_errors(
            core_id=core_id,
            cell_chipset=str(binding["parent_selected_chipset"]),
            cell=parent_cell,
            stable=False,
            approval_track=parent_track,
            pin_index=pin_index,
            tunings=tunings,
            label=f"{label}.parent_cell",
            version_slice_track=str(binding["parent_origin_track"]),
        )
    )
    if not _candidate_is_applicable(
        selected_chipset=str(binding["parent_selected_chipset"]),
        requested_chipset=chipset,
        cell=parent_cell,
    ):
        errors.append(f"{label} parent selection is not applicable")
    parent_variant = core_variant_id(
        core_id=core_id,
        cell_chipset=str(binding["parent_selected_chipset"]),
        cell=parent_cell,
        pin_index=pin_index,
        tunings=tunings,
    )
    parent_expected = {
        "parent_variant_id": parent_variant,
        "parent_build_pin_id": parent_cell["build_pin_id"],
        "parent_pin_content_sha256": parent_pin.get("content_sha256"),
        "parent_source_repository": parent_pin.get("source_repository"),
        "parent_source_requested_ref": parent_pin.get("source_requested_ref"),
        "parent_source_commit": parent_pin.get("source_commit"),
        "parent_source_tree": parent_pin.get("source_tree"),
    }
    if any(binding.get(key) != value for key, value in parent_expected.items()):
        errors.append(f"{label} frozen parent identity is stale")
    child_variant = core_variant_id(
        core_id=core_id,
        cell_chipset=chipset,
        cell=expected_child_cell,
        pin_index=pin_index,
        tunings=tunings,
    )
    child_expected = _source_order_child_identity(
        child_cell=expected_child_cell,
        child_pin=child_pin,
        child_variant=child_variant,
    )
    if any(binding.get(key) != value for key, value in child_expected.items()):
        errors.append(f"{label} frozen child identity is stale")

    lineage = binding.get("parent_lineage")
    parent_origin = binding.get("parent_origin_track")
    if track == "nightly":
        if parent_origin != "main" or lineage is not None:
            errors.append(f"{label} Nightly parent lineage is invalid")
    elif parent_origin == "nightly":
        if not isinstance(lineage, Mapping):
            errors.append(f"{label} direct Nightly parent lineage is missing")
        else:
            nested_binding = lineage.get("binding")
            nested_outlier = lineage.get("outlier")
            if isinstance(nested_binding, Mapping):
                expected_nested = (
                    "nightly",
                    core_id,
                    str(binding["parent_selected_chipset"]),
                )
                if _source_order_record_coordinate(nested_binding) != expected_nested:
                    errors.append(f"{label} parent lineage coordinate is stale")
                else:
                    nested_errors, nested_used = _frozen_source_order_binding_errors(
                        nested_binding,
                        outlier=(
                            nested_outlier
                            if isinstance(nested_outlier, Mapping)
                            else None
                        ),
                        expected_child_cell=parent_cell,
                        source_registry_index=source_registry_index,
                        pin_index=pin_index,
                        tunings=tunings,
                        source_ancestry_verifier=source_ancestry_verifier,
                        source_ancestry_core_id=source_ancestry_core_id,
                        label=f"{label}.parent_lineage.binding",
                    )
                    errors.extend(nested_errors)
                    if nested_outlier is not None and not nested_used:
                        errors.append(f"{label} parent lineage outlier is unused")
    elif lineage is not None:
        errors.append(f"{label} inherited Main parent lineage must be null")

    expected_outlier = _source_order_outlier_binding(parent_binding=binding)
    if outlier is not None and not _outlier_matches_binding(
        outlier, expected_outlier
    ):
        errors.append(f"{label} source-order outlier binding is stale")
        outlier = None
    parent_repository = binding.get("parent_source_repository")
    child_repository = binding.get("child_source_repository")
    parent_commit = binding.get("parent_source_commit")
    child_commit = binding.get("child_source_commit")
    if parent_commit == child_commit:
        if binding.get("parent_source_tree") != binding.get("child_source_tree"):
            errors.append(f"{label} has one source commit with differing trees")
            return errors, False
        if parent_repository == child_repository:
            return errors, False
        if outlier is not None:
            return errors, True
        errors.append(f"{label} changes source repository")
        return errors, False
    if outlier is not None:
        # Exact authorization owns the non-ordering edge. Do not feed it to an
        # ancestry recorder, which would turn the exception into a graph edge.
        return errors, True
    if parent_repository != child_repository:
        errors.append(f"{label} changes source repository")
        return errors, False
    if source_ancestry_core_id is not None and core_id != source_ancestry_core_id:
        return errors, False
    if source_ancestry_verifier is None:
        errors.append(
            f"{label} source ancestry is unverified; a Git ancestry verifier "
            "is required for differing commits"
        )
        return errors, False
    try:
        verified = source_ancestry_verifier(
            core_id,
            str(parent_repository),
            str(parent_commit),
            str(child_commit),
        )
    except Exception as exc:  # fail closed across verifier boundaries
        errors.append(
            f"{label} source ancestry verifier failed ({type(exc).__name__})"
        )
        return errors, False
    if verified is not True:
        errors.append(
            f"{label} source commit is not a verified descendant of {parent_track}"
        )
    return errors, False


def _source_order_errors(
    tracks: Mapping[str, Any],
    *,
    source_order_parent_bindings: object,
    source_order_outliers: object,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    source_ancestry_core_id: str | None,
) -> list[str]:
    """Prove every child TEST against its frozen assignment-time parent."""

    binding_index, errors = _source_order_parent_binding_index(
        source_order_parent_bindings
    )
    outlier_index, outlier_errors = _source_order_outlier_index(
        source_order_outliers
    )
    errors.extend(outlier_errors)
    expected_coordinates = {
        (track, core_id, chipset)
        for track in ("nightly", "edge")
        for core_id, cells in tracks[track]["test"].items()
        for chipset in cells
    }
    for track, core_id, chipset in sorted(expected_coordinates - set(binding_index)):
        errors.append(
            "source_order_parent_bindings has no frozen parent for "
            f"{track}/{core_id}/{chipset}"
        )
    for track, core_id, chipset in sorted(set(binding_index) - expected_coordinates):
        errors.append(
            "source_order_parent_bindings contains an unused or stale record for "
            f"{track}/{core_id}/{chipset}"
        )
    used_outliers: set[tuple[str, str, str]] = set()
    for coordinate in sorted(expected_coordinates & set(binding_index)):
        track, core_id, chipset = coordinate
        binding = binding_index[coordinate]
        child_cell = tracks[track]["test"][core_id][chipset]
        binding_errors, outlier_used = _frozen_source_order_binding_errors(
            binding,
            outlier=outlier_index.get(coordinate),
            expected_child_cell=child_cell,
            source_registry_index=source_registry_index,
            pin_index=pin_index,
            tunings=tunings,
            source_ancestry_verifier=source_ancestry_verifier,
            source_ancestry_core_id=source_ancestry_core_id,
            label=f"tracks.{track}.test.{core_id}.{chipset}",
        )
        errors.extend(binding_errors)
        if outlier_used:
            used_outliers.add(coordinate)
    for coordinate in sorted(set(outlier_index) - used_outliers):
        track, core_id, chipset = coordinate
        errors.append(
            "source_order_outliers contains an unused or stale record for "
            f"{track}/{core_id}/{chipset}"
        )
    return errors


def _validated_stable_source_registry(
    digest: str,
    *,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    source_registry_index: Mapping[str, Mapping[str, Any]],
    main_release_roster: object,
    spruce_branch_bases: object,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    source_ancestry_core_id: str | None,
    provenance_validation: _StableProvenanceValidation,
) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    """Load and structurally validate one immutable source registry."""

    memoized = provenance_validation.memo.get(digest)
    if memoized is not None:
        return memoized
    entry = source_registry_index.get(digest)
    source = entry.get("source_registry") if isinstance(entry, Mapping) else None
    if not isinstance(source, Mapping):
        result = (None, (f"stable provenance has no tracked snapshot: {digest}",))
        provenance_validation.memo[digest] = result
        return result
    if source.get("content_sha256") != digest:
        result = (None, (f"stable provenance snapshot identity differs: {digest}",))
        provenance_validation.memo[digest] = result
        return result
    source_errors = _core_track_errors(
        source,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tunings,
        source_registry_index=source_registry_index,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_ancestry_verifier=source_ancestry_verifier,
        source_ancestry_core_id=source_ancestry_core_id,
        verify_stable_provenance=False,
        historical_snapshot_context=True,
        provenance_validation=provenance_validation,
    )
    result = (
        (None, tuple(source_errors))
        if source_errors
        else (source, ())
    )
    provenance_validation.memo[digest] = result
    return result


def _stable_approval_link(
    stable_cell: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    approval_track: str,
    core_id: str,
    chipset: str,
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    label: str,
) -> tuple[Mapping[str, Any] | None, list[str]]:
    """Validate one approval against its source and return its exact prior cell."""

    errors: list[str] = []
    effective = _effective_test_cells_unchecked(source["tracks"], approval_track)
    candidate = effective.get((core_id, chipset))
    if candidate is None:
        return None, [
            f"{label} was not an effective test cell in its source registry"
        ]
    test_cell, origin = candidate
    if _cell_projection(stable_cell) != test_cell:
        return None, [
            f"{label} differs from the effective source-registry test cell"
        ]
    if stable_cell["approved_test_origin_track"] != origin:
        errors.append(
            f"{label}.approved_test_origin_track differs from the "
            "effective source-registry origin"
        )
    expected_variant = core_variant_id(
        core_id=core_id,
        cell_chipset=chipset,
        cell=test_cell,
        pin_index=pin_index,
        tunings=tunings,
    )
    if stable_cell["approved_test_variant_id"] != expected_variant:
        errors.append(
            f"{label}.approved_test_variant_id differs from the "
            "effective source-registry test variant"
        )
    prior_stable = (
        source["tracks"][approval_track]["stable"]
        .get(core_id, {})
        .get(chipset)
    )
    prior_variant = (
        prior_stable.get("approved_test_variant_id")
        if isinstance(prior_stable, Mapping)
        else None
    )
    if stable_cell["previous_stable_variant_id"] != prior_variant:
        errors.append(
            f"{label}.previous_stable_variant_id differs from the "
            "source-registry stable state"
        )
    return (prior_stable if isinstance(prior_stable, Mapping) else None), errors


def _stable_coordinate_lineage_errors(
    stable_cell: Mapping[str, Any],
    *,
    approval_track: str,
    core_id: str,
    chipset: str,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    source_registry_index: Mapping[str, Mapping[str, Any]],
    main_release_roster: object,
    spruce_branch_bases: object,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    source_ancestry_core_id: str | None,
    provenance_validation: _StableProvenanceValidation,
    label: str,
) -> list[str]:
    """Follow only one coordinate's immutable prior-STABLE lineage."""

    current = stable_cell
    seen_digests: set[str] = set()
    depth = 0
    while True:
        depth += 1
        if depth > MAX_STABLE_PROVENANCE_DEPTH:
            return [
                f"{label} stable provenance depth exceeds "
                f"{MAX_STABLE_PROVENANCE_DEPTH} for one coordinate"
            ]
        digest = current["source_registry_content_sha256"]
        if digest in seen_digests:
            return [
                f"{label} stable provenance snapshot cycle detected: {digest}"
            ]
        seen_digests.add(digest)
        source, source_errors = _validated_stable_source_registry(
            digest,
            catalog=catalog,
            pin_index=pin_index,
            tunings=tunings,
            source_registry_index=source_registry_index,
            main_release_roster=main_release_roster,
            spruce_branch_bases=spruce_branch_bases,
            source_ancestry_verifier=source_ancestry_verifier,
            source_ancestry_core_id=source_ancestry_core_id,
            provenance_validation=provenance_validation,
        )
        if source_errors:
            return [
                f"{label} source registry snapshot is invalid: "
                + "; ".join(source_errors)
            ]
        assert isinstance(source, Mapping)
        prior, link_errors = _stable_approval_link(
            current,
            source,
            approval_track=approval_track,
            core_id=core_id,
            chipset=chipset,
            pin_index=pin_index,
            tunings=tunings,
            label=label,
        )
        if link_errors:
            return link_errors
        if prior is None:
            return []
        current = prior


def _stable_provenance_errors(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    source_registry_index: Mapping[str, Mapping[str, Any]],
    main_release_roster: object,
    spruce_branch_bases: object,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    source_ancestry_core_id: str | None,
    provenance_validation: _StableProvenanceValidation,
) -> list[str]:
    errors: list[str] = []
    tracks = document["tracks"]
    for approval_track in CORE_TRACKS:
        for core_id, cells in tracks[approval_track]["stable"].items():
            for chipset, stable_cell in cells.items():
                label = f"tracks.{approval_track}.stable.{core_id}.{chipset}"
                errors.extend(
                    _stable_coordinate_lineage_errors(
                        stable_cell,
                        approval_track=approval_track,
                        core_id=core_id,
                        chipset=chipset,
                        catalog=catalog,
                        pin_index=pin_index,
                        tunings=tunings,
                        source_registry_index=source_registry_index,
                        main_release_roster=main_release_roster,
                        spruce_branch_bases=spruce_branch_bases,
                        source_ancestry_verifier=source_ancestry_verifier,
                        source_ancestry_core_id=source_ancestry_core_id,
                        provenance_validation=provenance_validation,
                        label=label,
                    )
                )
    return errors


def _core_track_errors(
    document: object,
    *,
    catalog: object,
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    main_release_roster: object,
    spruce_branch_bases: object,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    source_ancestry_core_id: str | None,
    verify_stable_provenance: bool,
    historical_snapshot_context: bool,
    provenance_validation: _StableProvenanceValidation,
) -> list[str]:
    """Return strict track-registry errors without mutating inputs."""

    try:
        validated_tunings = validate_chipset_tunings(tunings)
    except PipelineError as exc:
        return [str(exc)]
    if not isinstance(catalog, Mapping) or not isinstance(catalog.get("cores"), Mapping):
        return ["core tracks require a catalog cores object"]
    catalog_ids = set(catalog["cores"])
    if (
        source_ancestry_core_id is not None
        and source_ancestry_core_id not in catalog_ids
    ):
        return ["source ancestry core scope is not cataloged"]
    if not isinstance(document, Mapping):
        return ["core tracks must be an object"]
    if set(document) != {
        "$schema",
        "schema_version",
        "selection_model",
        "applicability_scope",
        "version_policy",
        "source_order_parent_bindings",
        "source_order_outliers",
        "spruce_branch_bases",
        "historical_release_correlation",
        "tracks",
        "content_sha256",
    }:
        return ["core track fields are not exact"]
    errors: list[str] = []
    if document.get("$schema") != CORE_TRACK_SCHEMA_REF:
        errors.append("core track schema reference is invalid")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != CORE_TRACK_SCHEMA_VERSION
    ):
        errors.append("core track schema_version is invalid")
    if document.get("selection_model") != CORE_TRACK_SELECTION_MODEL:
        errors.append("core track selection_model is invalid")
    if document.get("applicability_scope") != CORE_TRACK_APPLICABILITY_SCOPE:
        errors.append("core track applicability_scope is invalid")
    errors.extend(_version_policy_errors(document, catalog=catalog))
    _binding_index, binding_shape_errors = _source_order_parent_binding_index(
        document.get("source_order_parent_bindings")
    )
    errors.extend(binding_shape_errors)
    _outlier_index, outlier_shape_errors = _source_order_outlier_index(
        document.get("source_order_outliers")
    )
    errors.extend(outlier_shape_errors)
    tracks = document.get("tracks")
    if not isinstance(tracks, Mapping) or set(tracks) != set(CORE_TRACKS):
        errors.append("tracks must contain exactly: " + ", ".join(CORE_TRACKS))
        return errors
    for track in CORE_TRACKS:
        value = tracks.get(track)
        label = f"tracks.{track}"
        if not isinstance(value, Mapping) or set(value) != {
            "extends",
            "spruce_branch_basis",
            "test",
            "stable",
            "deferred",
        }:
            errors.append(
                f"{label} fields must be exactly extends, spruce_branch_basis, "
                "test, stable, and deferred"
            )
            continue
        if value.get("extends") != TRACK_PARENTS[track]:
            errors.append(f"{label}.extends is invalid")
        errors.extend(
            _track_cells_errors(
                value.get("test"),
                stable=False,
                track=track,
                catalog_ids=catalog_ids,
                pin_index=pin_index,
                tunings=validated_tunings,
                label=f"{label}.test",
            )
        )
        errors.extend(
            _deferred_cells_errors(
                value.get("deferred"),
                catalog_ids=catalog_ids,
                label=f"{label}.deferred",
            )
        )
        if isinstance(value.get("test"), Mapping) and isinstance(
            value.get("deferred"), Mapping
        ):
            direct_overlap = sorted(
                f"{core_id}/{chipset}"
                for core_id, cells in value["test"].items()
                if isinstance(cells, Mapping)
                for chipset in cells
                if chipset
                in (
                    value["deferred"].get(core_id, {})
                    if isinstance(value["deferred"].get(core_id), Mapping)
                    else {}
                )
            )
            if direct_overlap:
                errors.append(
                    f"{label} TEST/deferred cells overlap: "
                    + ", ".join(direct_overlap)
                )
        errors.extend(
            _track_cells_errors(
                value.get("stable"),
                stable=True,
                track=track,
                catalog_ids=catalog_ids,
                pin_index=pin_index,
                tunings=validated_tunings,
                label=f"{label}.stable",
            )
        )
    if errors:
        return errors

    assert isinstance(catalog, Mapping)
    binding_errors = _branch_comparison_binding_errors(
        document,
        catalog=catalog,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        historical_snapshot_context=historical_snapshot_context,
    )
    errors.extend(binding_errors)
    errors.extend(
        _version_slice_registry_errors(
            document,
            spruce_branch_bases=spruce_branch_bases,
            canonical_basis_authenticated=(
                not historical_snapshot_context and not binding_errors
            ),
        )
    )
    errors.extend(_edge_latest_errors(document, pin_index=pin_index))
    errors.extend(
        _source_order_errors(
            tracks,
            source_order_parent_bindings=document.get(
                "source_order_parent_bindings"
            ),
            source_order_outliers=document.get("source_order_outliers"),
            source_registry_index=source_registry_index,
            pin_index=pin_index,
            tunings=validated_tunings,
            source_ancestry_verifier=source_ancestry_verifier,
            source_ancestry_core_id=source_ancestry_core_id,
        )
    )

    for track in CORE_TRACKS:
        effective_test, effective_deferred = _effective_selection_cells_unchecked(
            tracks, track
        )
        missing_or_ambiguous = sorted(
            core_id
            for core_id in catalog_ids
            if (
                ((core_id, "universal") in effective_test)
                + ((core_id, "universal") in effective_deferred)
            )
            != 1
        )
        if missing_or_ambiguous:
            errors.append(
                f"{track} universal coverage must be build-pinned XOR deferred: "
                + ", ".join(missing_or_ambiguous)
            )
    for track in ("nightly", "edge"):
        parent = TRACK_PARENTS[track]
        assert parent is not None
        _inherited_test, inherited_deferred = _effective_selection_cells_unchecked(
            tracks, parent
        )
        for core_id, cells in tracks[track]["deferred"].items():
            for chipset, cell in cells.items():
                previous = inherited_deferred.get((core_id, chipset))
                if previous is not None and previous[0] == cell:
                    errors.append(
                        f"tracks.{track}.deferred.{core_id}.{chipset} "
                        "repeats its inherited deferred cell"
                    )
    digest = document.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        errors.append("core track content_sha256 is invalid")
    elif digest != core_tracks_content_sha256(document):
        errors.append("core track content_sha256 is stale")
    if not errors and verify_stable_provenance:
        errors.extend(
            _stable_provenance_errors(
                document,
                catalog=catalog,
                pin_index=pin_index,
                tunings=validated_tunings,
                source_registry_index=source_registry_index,
                main_release_roster=main_release_roster,
                spruce_branch_bases=spruce_branch_bases,
                source_ancestry_verifier=source_ancestry_verifier,
                source_ancestry_core_id=source_ancestry_core_id,
                provenance_validation=provenance_validation,
            )
        )
    return errors


def core_track_errors(
    document: object,
    *,
    catalog: object,
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    source_registry_index: Mapping[str, Mapping[str, Any]] | None = None,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None = None,
    source_ancestry_core_id: str | None = None,
) -> list[str]:
    """Return strict track-registry errors without mutating inputs."""

    return _core_track_errors(
        document,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tunings,
        source_registry_index=source_registry_index or {},
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_ancestry_verifier=source_ancestry_verifier,
        source_ancestry_core_id=source_ancestry_core_id,
        verify_stable_provenance=True,
        historical_snapshot_context=False,
        provenance_validation=_StableProvenanceValidation(),
    )


def validate_core_tracks(
    document: object,
    *,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    source_registry_index: Mapping[str, Mapping[str, Any]] | None = None,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None = None,
    source_ancestry_core_id: str | None = None,
) -> dict[str, Any]:
    """Validate tracks, optionally scoping only external Git ancestry proof.

    ``source_ancestry_core_id`` is for one-core workers. All registry, pin,
    tuning, roster, stable-provenance, repository, tree, and digest checks
    remain global; only differing-commit Git graph edges for other cores are
    deferred. Global inventory/coordinator/seal callers must leave it unset.
    """

    errors = core_track_errors(
        document,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
        source_ancestry_core_id=source_ancestry_core_id,
    )
    if errors:
        raise PipelineError("invalid core tracks:\n- " + "\n- ".join(errors))
    assert isinstance(document, Mapping)
    return copy.deepcopy(dict(document))


def _candidate_is_applicable(
    *,
    selected_chipset: str,
    requested_chipset: str,
    cell: Mapping[str, Any],
) -> bool:
    if requested_chipset == "universal":
        return selected_chipset == "universal"
    if selected_chipset == requested_chipset:
        return True
    return (
        selected_chipset == "universal"
        and requested_chipset in cell.get("applicable_chipsets", ())
    )


def _resolved_row(
    *,
    core_id: str,
    track: str,
    marker: str,
    requested_chipset: str,
    selected_chipset: str,
    cell: Mapping[str, Any],
    selected_state: str,
    resolution: str,
    test_origin_track: str,
    current_assignment_content_sha256: str | None,
    spruce_branch_basis: Mapping[str, Any],
    slice_comparison_bases: Mapping[str, Mapping[str, Any]],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
) -> dict[str, Any]:
    pin = pin_index[cell["build_pin_id"]]
    tuning = resolved_tuning_profile(tunings, cell["tuning_profile"])
    variant_id = core_variant_id(
        core_id=core_id,
        cell_chipset=selected_chipset,
        cell=cell,
        pin_index=pin_index,
        tunings=tunings,
    )
    selected_architectures = (
        copy.deepcopy(pin["architectures"])
        if requested_chipset == "universal"
        else [CHIPSET_ARCHITECTURES[requested_chipset]]
    )
    if any(
        architecture not in pin["architectures"]
        for architecture in selected_architectures
    ):
        raise PipelineError(
            f"selected pin has no target for {requested_chipset}: {core_id}"
        )
    row = {
        "core_id": core_id,
        "track": track,
        "requested_marker": marker,
        "requested_chipset": requested_chipset,
        "selected_chipset": selected_chipset,
        "selected_state": selected_state,
        "stability": "stable" if selected_state == "stable" else "unstable",
        "resolution": resolution,
        "test_origin_track": test_origin_track,
        "current_assignment_content_sha256": (
            current_assignment_content_sha256
        ),
        "spruce_branch_basis": copy.deepcopy(dict(spruce_branch_basis)),
        "version_slice": copy.deepcopy(cell["version_slice"]),
        "slice_comparison_basis": copy.deepcopy(
            slice_comparison_bases[
                cell["version_slice"]["content_sha256"]
            ]
        ),
        "variant_id": variant_id,
        "pin": {
            key: pin[key]
            for key in ("path", "pin_id", "file_sha256", "content_sha256")
        },
        "source_commit": pin["source_commit"],
        "architectures": copy.deepcopy(pin["architectures"]),
        "selected_architectures": selected_architectures,
        "tuning": {
            "profile_id": tuning["profile_id"],
            "content_sha256": tuning["content_sha256"],
            "properties": copy.deepcopy(tuning["properties"]),
            "compiler_argument_mapping_version": tuning[
                "compiler_argument_mapping_version"
            ],
            "compiler_arguments": copy.deepcopy(tuning["compiler_arguments"]),
        },
    }
    if selected_state == "stable":
        row["approval"] = {
            "approved_test_variant_id": cell["approved_test_variant_id"],
            "approved_test_origin_track": cell["approved_test_origin_track"],
            "approved_at": cell["approved_at"],
            "approved_by": cell["approved_by"],
            "reason": cell["reason"],
            "previous_stable_variant_id": cell[
                "previous_stable_variant_id"
            ],
            "source_registry_content_sha256": cell[
                "source_registry_content_sha256"
            ],
        }
    return row


def _resolve_core_track_cell_validated(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: Mapping[str, Any],
    track: str,
    marker: str,
    chipset: str,
    core_id: str,
) -> dict[str, Any] | None:
    """Resolve one core after both registries have been validated."""

    canonical_group_tag(track, marker, chipset)
    if core_id not in catalog["cores"]:
        raise PipelineError(f"core is not cataloged: {core_id}")
    tracks = document["tracks"]
    tests = _effective_test_cells_unchecked(tracks, track)
    stable_cells = tracks[track]["stable"].get(core_id, {})
    current_assignment_content_sha256 = (
        core_track_test_assignment_content_sha256(
            document,
            track=track,
            core_id=core_id,
            chipset=chipset,
        )
    )
    exact_order = [chipset] if chipset == "universal" else [chipset, "universal"]

    if marker == "stable":
        for selected_chipset in exact_order:
            cell = stable_cells.get(selected_chipset)
            if isinstance(cell, Mapping) and _candidate_is_applicable(
                selected_chipset=selected_chipset,
                requested_chipset=chipset,
                cell=cell,
            ):
                return _resolved_row(
                    core_id=core_id,
                    track=track,
                    marker=marker,
                    requested_chipset=chipset,
                    selected_chipset=selected_chipset,
                    cell=cell,
                    selected_state="stable",
                    resolution=(
                        "exact_stable"
                        if selected_chipset == chipset
                        else "universal_stable_fallback"
                    ),
                    test_origin_track=cell["approved_test_origin_track"],
                    current_assignment_content_sha256=(
                        current_assignment_content_sha256
                    ),
                    spruce_branch_basis=tracks[track]["spruce_branch_basis"],
                    slice_comparison_bases=document["version_policy"][
                        "slice_comparison_bases"
                    ],
                    pin_index=pin_index,
                    tunings=tunings,
                )

    for selected_chipset in exact_order:
        candidate = tests.get((core_id, selected_chipset))
        if candidate is None:
            continue
        cell, origin = candidate
        if not _candidate_is_applicable(
            selected_chipset=selected_chipset,
            requested_chipset=chipset,
            cell=cell,
        ):
            continue
        unstable = marker == "stable"
        return _resolved_row(
            core_id=core_id,
            track=track,
            marker=marker,
            requested_chipset=chipset,
            selected_chipset=selected_chipset,
            cell=cell,
            selected_state="unstable_fallback" if unstable else "test",
            resolution=(
                ("exact_test_unstable_fallback" if unstable else "exact_test")
                if selected_chipset == chipset
                else (
                    "universal_test_unstable_fallback"
                    if unstable
                    else "universal_test_fallback"
                )
            ),
            test_origin_track=origin,
            current_assignment_content_sha256=(
                current_assignment_content_sha256
            ),
            spruce_branch_basis=tracks[track]["spruce_branch_basis"],
            slice_comparison_bases=document["version_policy"][
                "slice_comparison_bases"
            ],
            pin_index=pin_index,
            tunings=tunings,
        )
    return None


def resolve_core_track_cell(
    document: object,
    *,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    track: str,
    marker: str,
    chipset: str,
    core_id: str,
    source_registry_index: Mapping[str, Mapping[str, Any]] | None = None,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None = None,
) -> dict[str, Any] | None:
    """Resolve one core using stable-first and universal-only fallback."""

    validated_tunings = validate_chipset_tunings(tunings)
    validated = validate_core_tracks(
        document,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
    )
    return _resolve_core_track_cell_validated(
        validated,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        track=track,
        marker=marker,
        chipset=chipset,
        core_id=core_id,
    )


def core_track_inventory_content_sha256(document: Mapping[str, Any]) -> str:
    return _semantic_sha256(
        {
            "schema_version": document.get("schema_version"),
            "validation_scope": document.get("validation_scope"),
            "local_only": document.get("local_only"),
            "publication": document.get("publication"),
            "group_tag": document.get("group_tag"),
            "applicability_scope": document.get("applicability_scope"),
            "catalog_content_sha256": document.get("catalog_content_sha256"),
            "track_registry_content_sha256": document.get(
                "track_registry_content_sha256"
            ),
            "tuning_registry_content_sha256": document.get(
                "tuning_registry_content_sha256"
            ),
            "cores": document.get("cores"),
            "deferred_cores": document.get("deferred_cores"),
            "unsupported_core_ids": document.get("unsupported_core_ids"),
            "inventory_state": document.get("inventory_state"),
            "complete": document.get("complete"),
            "summary": document.get("summary"),
        }
    )


def construct_core_track_inventory(
    document: object,
    *,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    group_tag: str,
    requested_cores: Sequence[str] | None = None,
    source_registry_index: Mapping[str, Mapping[str, Any]] | None = None,
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None = None,
    source_ancestry_core_id: str | None = None,
) -> dict[str, Any]:
    """Construct a deterministic marked inventory for one exact group tag.

    A non-null ancestry core scope is accepted only for that exact one-core
    inventory. It never changes the default full-graph validation contract.
    """

    track, marker, chipset = parse_group_tag(group_tag)
    if source_ancestry_core_id is not None and list(requested_cores or ()) != [
        source_ancestry_core_id
    ]:
        raise PipelineError(
            "source ancestry core scope requires the same exact one-core inventory"
        )
    validated_tunings = validate_chipset_tunings(tunings)
    validated = validate_core_tracks(
        document,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
        source_ancestry_core_id=source_ancestry_core_id,
    )
    catalog_ids = set(catalog["cores"])
    selected_ids = sorted(catalog_ids if requested_cores is None else requested_cores)
    if len(selected_ids) != len(set(selected_ids)):
        raise PipelineError("core track inventory core IDs must be unique")
    unknown = sorted(set(selected_ids) - catalog_ids)
    if unknown:
        raise PipelineError("core track inventory contains unknown cores: " + ", ".join(unknown))
    rows: list[dict[str, Any]] = []
    deferred_rows: list[dict[str, Any]] = []
    unsupported: list[str] = []
    effective_deferred = _effective_deferred_cells_unchecked(
        validated["tracks"], track
    )
    for core_id in selected_ids:
        row = _resolve_core_track_cell_validated(
            validated,
            catalog=catalog,
            pin_index=pin_index,
            tunings=validated_tunings,
            track=track,
            marker=marker,
            chipset=chipset,
            core_id=core_id,
        )
        if row is None:
            exact_order = (
                [chipset]
                if chipset == "universal"
                else [chipset, "universal"]
            )
            deferred_candidate = next(
                (
                    (selected_chipset, effective_deferred[(core_id, selected_chipset)])
                    for selected_chipset in exact_order
                    if (core_id, selected_chipset) in effective_deferred
                ),
                None,
            )
            if deferred_candidate is None:
                unsupported.append(core_id)
            else:
                selected_chipset, (deferred_cell, origin_track) = deferred_candidate
                deferred_rows.append(
                    {
                        "core_id": core_id,
                        "track": track,
                        "requested_marker": marker,
                        "requested_chipset": chipset,
                        "selected_chipset": selected_chipset,
                        "state": DEFERRED_STATE,
                        "reason": deferred_cell["reason"],
                        "origin_track": origin_track,
                        "current_assignment_content_sha256": (
                            core_track_test_assignment_content_sha256(
                                validated,
                                track=track,
                                core_id=core_id,
                                chipset=chipset,
                            )
                        ),
                        "resolution": (
                            "exact_deferred"
                            if selected_chipset == chipset
                            else "universal_deferred_fallback"
                        ),
                        "spruce_branch_basis": copy.deepcopy(
                            validated["tracks"][track]["spruce_branch_basis"]
                        ),
                    }
                )
        else:
            rows.append(row)
    stable_count = sum(row["stability"] == "stable" for row in rows)
    unstable_count = sum(row["stability"] == "unstable" for row in rows)
    inventory_state = (
        "deferred"
        if deferred_rows
        else "unstable"
        if unstable_count
        else "stable"
        if stable_count
        else "unavailable"
    )
    document_out: dict[str, Any] = {
        "schema_version": 2,
        "validation_scope": "static-build-selection-only",
        "local_only": True,
        "publication": "disabled",
        "group_tag": group_tag,
        "applicability_scope": validated["applicability_scope"],
        "catalog_content_sha256": _semantic_sha256(catalog),
        "track_registry_content_sha256": validated["content_sha256"],
        "tuning_registry_content_sha256": validated_tunings["content_sha256"],
        "cores": rows,
        "deferred_cores": deferred_rows,
        "unsupported_core_ids": unsupported,
        "inventory_state": inventory_state,
        "complete": not deferred_rows and not unsupported,
        "summary": {
            "selected_core_count": len(rows),
            "stable_core_count": stable_count,
            "unstable_core_count": unstable_count,
            "deferred_core_count": len(deferred_rows),
            "unsupported_core_count": len(unsupported),
            "universal_fallback_count": sum(
                row["selected_chipset"] == "universal" and chipset != "universal"
                for row in rows
            )
            + sum(
                row["resolution"] == "universal_deferred_fallback"
                for row in deferred_rows
            ),
        },
        "content_sha256": "",
    }
    document_out["content_sha256"] = core_track_inventory_content_sha256(document_out)
    return document_out


def promote_core_track_test(
    document: object,
    *,
    repository_root: Path,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None = None,
    track: str,
    core_id: str,
    chipset: str,
    approved_at: str,
    approved_by: str,
    reason: str,
    expected_test_variant: str,
    expected_current_stable: str,
) -> dict[str, Any]:
    """Promote one exact TEST cell using TEST and current-STABLE CAS gates."""

    canonical_group_tag(track, "test", chipset)
    canonical_approved_at = _canonical_utc_approval_timestamp(approved_at)
    if canonical_approved_at is None:
        raise PipelineError("core track approval timestamp is invalid")
    if not isinstance(approved_by, str) or not approved_by.strip():
        raise PipelineError("core track approver is invalid")
    if not isinstance(reason, str) or not reason.strip():
        raise PipelineError("core track approval reason is invalid")
    if (
        not isinstance(expected_test_variant, str)
        or SHA256_RE.fullmatch(expected_test_variant) is None
    ):
        raise PipelineError("expected core track TEST variant is invalid")
    if (
        not isinstance(expected_current_stable, str)
        or (
            expected_current_stable != EXPECTED_STABLE_ABSENT
            and SHA256_RE.fullmatch(expected_current_stable) is None
        )
    ):
        raise PipelineError(
            "expected current stable must be 'absent' or an exact variant identity"
        )
    validated_tunings = validate_chipset_tunings(tunings)
    source = validate_core_tracks(
        document,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
    )
    if core_id not in catalog["cores"]:
        raise PipelineError(f"core is not cataloged: {core_id}")
    effective = _effective_test_cells_unchecked(source["tracks"], track)
    candidate = effective.get((core_id, chipset))
    if candidate is None:
        raise PipelineError(
            f"no exact effective test cell to promote: {track}/{core_id}/{chipset}"
        )
    test_cell, origin = candidate
    current_test_variant = core_variant_id(
        core_id=core_id,
        cell_chipset=chipset,
        cell=test_cell,
        pin_index=pin_index,
        tunings=validated_tunings,
    )
    if current_test_variant != expected_test_variant:
        raise PipelineError(
            "effective core track TEST variant changed since approval review"
        )
    existing = source["tracks"][track]["stable"].get(core_id, {}).get(chipset)
    current_stable_variant = (
        existing.get("approved_test_variant_id")
        if isinstance(existing, Mapping)
        else None
    )
    if existing is None and expected_current_stable != EXPECTED_STABLE_ABSENT:
        raise PipelineError(
            "current stable core track cell changed since approval review: "
            f"expected {expected_current_stable}, found absent"
        )
    if existing is not None and expected_current_stable == EXPECTED_STABLE_ABSENT:
        raise PipelineError(
            "current stable core track cell changed since approval review: "
            f"expected absent, found {current_stable_variant}"
        )
    if (
        existing is not None
        and expected_current_stable != EXPECTED_STABLE_ABSENT
        and current_stable_variant != expected_current_stable
    ):
        raise PipelineError(
            "current stable core track cell changed since approval review: "
            f"expected {expected_current_stable}, found {current_stable_variant}"
        )

    source_digest = source["content_sha256"]
    snapshot = core_track_source_snapshot(source)
    snapshot_digest, snapshot_entry = _snapshot_index_entry(
        repository_root=repository_root,
        snapshot=snapshot,
    )
    if snapshot_digest != source_digest:
        raise AssertionError("source snapshot digest changed during promotion")
    prior_snapshot = source_registry_index.get(source_digest)
    if prior_snapshot is not None and prior_snapshot.get("source_registry") != source:
        raise PipelineError("existing source snapshot differs from the source registry")

    stable_cell = _cell_projection(test_cell)
    stable_cell.update(
        {
            "approved_test_variant_id": current_test_variant,
            "approved_test_origin_track": origin,
            "approved_at": canonical_approved_at,
            "approved_by": approved_by.strip(),
            "reason": reason.strip(),
            "previous_stable_variant_id": current_stable_variant,
            "source_registry_content_sha256": source_digest,
        }
    )
    promoted = copy.deepcopy(source)
    promoted["tracks"][track]["stable"].setdefault(core_id, {})[chipset] = stable_cell
    promoted["tracks"][track]["stable"] = dict(
        sorted(promoted["tracks"][track]["stable"].items())
    )
    promoted["tracks"][track]["stable"][core_id] = dict(
        sorted(promoted["tracks"][track]["stable"][core_id].items())
    )
    promoted["content_sha256"] = core_tracks_content_sha256(promoted)
    validation_index = dict(source_registry_index)
    validation_index[source_digest] = snapshot_entry
    validated = validate_core_tracks(
        promoted,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=validation_index,
        source_ancestry_verifier=source_ancestry_verifier,
    )
    return {
        "registry": validated,
        "snapshot": snapshot,
        "snapshot_path": snapshot_entry["path"],
        "snapshot_file_sha256": snapshot_entry["file_sha256"],
        "stable_cell": copy.deepcopy(stable_cell),
        "previous_stable_variant_id": current_stable_variant,
    }


@dataclass(frozen=True, slots=True)
class _CoreTrackTestExpectations:
    source_registry: str
    current_test: str
    current_assignment: str
    new_variant: str
    parent_variant: str | None
    parent_registry: str | None


def _evaluate_core_track_test(
    document: object,
    *,
    repository_root: Path,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    track: str,
    core_id: str,
    chipset: str,
    pin_id: str,
    tuning_profile: str,
    slice_time: str,
    expectations: _CoreTrackTestExpectations | None,
    applicable_chipsets: Sequence[str] | None = None,
    outlier_authorized_at: str | None = None,
    outlier_authorized_by: str | None = None,
    outlier_reason: str | None = None,
) -> dict[str, Any]:
    """Evaluate one complete TEST transition, optionally enforcing its CAS."""

    canonical_group_tag(track, "test", chipset)
    if not isinstance(repository_root, Path):
        raise PipelineError("core-track TEST repository root is invalid")
    canonical_slice_time = _canonical_utc_approval_timestamp(slice_time)
    if canonical_slice_time is None:
        raise PipelineError("core-track TEST slice time is invalid")
    planning = expectations is None
    expected_source_registry = (
        None if expectations is None else expectations.source_registry
    )
    expected_current_test = (
        None if expectations is None else expectations.current_test
    )
    expected_current_assignment = (
        None if expectations is None else expectations.current_assignment
    )
    expected_new_variant = (
        None if expectations is None else expectations.new_variant
    )
    expected_parent_variant = (
        None if expectations is None else expectations.parent_variant
    )
    expected_parent_registry = (
        None if expectations is None else expectations.parent_registry
    )
    if not planning:
        if (
            not isinstance(expected_source_registry, str)
            or SHA256_RE.fullmatch(expected_source_registry) is None
        ):
            raise PipelineError("expected source registry is invalid")
        if (
            not isinstance(expected_current_test, str)
            or (
                expected_current_test != EXPECTED_TEST_ABSENT
                and SHA256_RE.fullmatch(expected_current_test) is None
            )
        ):
            raise PipelineError(
                "expected current TEST must be 'absent' or an exact variant identity"
            )
        if (
            not isinstance(expected_current_assignment, str)
            or (
                expected_current_assignment != EXPECTED_ASSIGNMENT_ABSENT
                and SHA256_RE.fullmatch(expected_current_assignment) is None
            )
        ):
            raise PipelineError(
                "expected current TEST assignment must be 'absent' or an exact "
                "assignment identity"
            )
        if (
            not isinstance(expected_new_variant, str)
            or SHA256_RE.fullmatch(expected_new_variant) is None
        ):
            raise PipelineError("expected new TEST variant is invalid")
    outlier_values = (
        outlier_authorized_at,
        outlier_authorized_by,
        outlier_reason,
    )
    if any(value is not None for value in outlier_values) and not all(
        value is not None for value in outlier_values
    ):
        raise PipelineError("source-order outlier authorization fields are all-or-none")
    if track == "main":
        if expected_parent_variant is not None:
            raise PipelineError("main TEST admission has no parent variant")
        if expected_parent_registry is not None:
            raise PipelineError("main TEST admission has no parent registry")
        if any(value is not None for value in outlier_values):
            raise PipelineError("main TEST admission cannot authorize a source outlier")
    else:
        if not planning and (
            not isinstance(expected_parent_variant, str)
            or SHA256_RE.fullmatch(expected_parent_variant) is None
        ):
            raise PipelineError(
                "child-track TEST admission requires an exact expected parent variant"
            )
        if not planning and (
            not isinstance(expected_parent_registry, str)
            or SHA256_RE.fullmatch(expected_parent_registry) is None
        ):
            raise PipelineError(
                "child-track TEST admission requires an exact expected parent registry"
            )
    canonical_outlier_at = None
    if outlier_authorized_at is not None:
        canonical_outlier_at = _canonical_utc_approval_timestamp(
            outlier_authorized_at
        )
        if canonical_outlier_at is None:
            raise PipelineError("source-order outlier authorization timestamp is invalid")
        if not isinstance(outlier_authorized_by, str) or not outlier_authorized_by.strip():
            raise PipelineError("source-order outlier authorizer is invalid")
        if not isinstance(outlier_reason, str) or not outlier_reason.strip():
            raise PipelineError("source-order outlier reason is invalid")
    if applicable_chipsets is None:
        if chipset == "universal":
            raise PipelineError(
                "universal TEST admission requires explicit applicable chipsets"
            )
        selected_applicability = [chipset]
    else:
        if isinstance(applicable_chipsets, (str, bytes)):
            raise PipelineError("TEST applicability must be a chipset list")
        selected_applicability = list(applicable_chipsets)
        if (
            not selected_applicability
            or any(not isinstance(item, str) for item in selected_applicability)
            or selected_applicability != sorted(set(selected_applicability))
            or any(item not in REAL_CHIPSETS for item in selected_applicability)
        ):
            raise PipelineError(
                "TEST applicability must be a non-empty unique sorted "
                "real-chipset list"
            )
        if chipset != "universal" and selected_applicability != [chipset]:
            raise PipelineError(
                "exact-chipset TEST admission applies only to that chipset"
            )
    validated_tunings = validate_chipset_tunings(tunings)
    source = validate_core_tracks(
        document,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
    )
    if planning:
        expected_source_registry = source["content_sha256"]
    elif source["content_sha256"] != expected_source_registry:
        raise PipelineError(
            "source track registry changed since admission review"
        )
    if planning and track != "main":
        expected_parent_registry = source["content_sha256"]
    elif track != "main" and source["content_sha256"] != expected_parent_registry:
        raise PipelineError(
            "effective parent registry changed since admission review"
        )
    parent_snapshot = None
    parent_snapshot_entry = None
    validation_source_registry_index = dict(source_registry_index)
    if track != "main":
        parent_snapshot = core_track_source_snapshot(source)
        snapshot_digest, parent_snapshot_entry = _snapshot_index_entry(
            repository_root=repository_root,
            snapshot=parent_snapshot,
        )
        if snapshot_digest != source["content_sha256"]:
            raise AssertionError("parent registry snapshot digest changed")
        prior_snapshot = source_registry_index.get(snapshot_digest)
        if prior_snapshot is not None and prior_snapshot.get(
            "source_registry"
        ) != source:
            raise PipelineError(
                "existing parent registry snapshot differs from the source registry"
            )
        validation_source_registry_index[snapshot_digest] = parent_snapshot_entry
    if core_id not in catalog.get("cores", {}):
        raise PipelineError(f"core is not cataloged: {core_id}")
    pin = pin_index.get(pin_id)
    if not isinstance(pin, Mapping) or pin.get("core_id") != core_id:
        raise PipelineError("TEST admission pin is not authoritative for this core")
    reproduction_digest = pin.get("host_reproduction_content_sha256")
    if (
        not isinstance(reproduction_digest, str)
        or SHA256_RE.fullmatch(reproduction_digest) is None
    ):
        raise PipelineError(
            "TEST admission pin has no validated host reproduction proof"
        )
    parent_cell: Mapping[str, Any] | None = None
    parent_pin: Mapping[str, Any] | None = None
    parent_variant: str | None = None
    parent_origin: str | None = None
    parent_chipset: str | None = None
    if track != "main":
        parent_track = TRACK_PARENTS[track]
        assert parent_track is not None
        predecessor = _parent_test_candidate(
            source["tracks"],
            parent=parent_track,
            core_id=core_id,
            chipset=chipset,
        )
        if predecessor is None:
            raise PipelineError(
                f"child-track TEST admission has no {parent_track} predecessor"
            )
        parent_cell, parent_origin, parent_chipset = predecessor
        parent_pin = pin_index[parent_cell["build_pin_id"]]
        parent_variant = core_variant_id(
            core_id=core_id,
            cell_chipset=parent_chipset,
            cell=parent_cell,
            pin_index=pin_index,
            tunings=validated_tunings,
        )
        if planning:
            expected_parent_variant = parent_variant
        elif parent_variant != expected_parent_variant:
            raise PipelineError(
                "effective parent TEST variant changed since admission review"
            )
    if track == "edge" and not _pin_matches_edge_reviewed_head(
        source, core_id=core_id, pin=pin
    ):
        raise PipelineError(
            "Edge TEST admission pin does not match the latest reviewed upstream head"
        )
    tuning = resolved_tuning_profile(validated_tunings, tuning_profile)
    expected_tuning_identity = {
        "profile_id": tuning["profile_id"],
        "content_sha256": tuning["content_sha256"],
    }
    if chipset == "universal":
        if (
            tuning_profile != UNIVERSAL_TUNING_PROFILE
            or tuning.get("chipset") != "universal"
            or tuning.get("architecture") != "any"
            or tuning.get("properties") != {}
            or tuning.get("compiler_arguments") != []
            or pin.get("tuning_identity") not in (None, expected_tuning_identity)
            or any(
                CHIPSET_ARCHITECTURES[item] not in pin.get("architectures", ())
                for item in selected_applicability
            )
        ):
            raise PipelineError(
                "TEST admission pin does not bind the exact universal profile "
                "and applicability"
            )
    elif (
        tuning.get("chipset") != chipset
        or tuning.get("architecture") != CHIPSET_ARCHITECTURES[chipset]
        or pin.get("architectures") != [tuning["architecture"]]
        or pin.get("tuning_identity") != expected_tuning_identity
    ):
        raise PipelineError(
            "TEST admission pin does not bind the exact one-ABI tuning profile"
        )
    existing = source["tracks"][track]["test"].get(core_id, {}).get(chipset)
    current_variant = (
        core_variant_id(
            core_id=core_id,
            cell_chipset=chipset,
            cell=existing,
            pin_index=pin_index,
            tunings=validated_tunings,
        )
        if isinstance(existing, Mapping)
        else None
    )
    current_assignment_content_sha256 = (
        core_track_test_assignment_content_sha256(
            source,
            track=track,
            core_id=core_id,
            chipset=chipset,
        )
    )
    if planning:
        expected_current_test = (
            current_variant
            if current_variant is not None
            else EXPECTED_TEST_ABSENT
        )
        expected_current_assignment = (
            current_assignment_content_sha256
            if current_assignment_content_sha256 is not None
            else EXPECTED_ASSIGNMENT_ABSENT
        )
    elif existing is None and expected_current_test != EXPECTED_TEST_ABSENT:
        raise PipelineError(
            "track-local TEST cell changed since review: expected "
            f"{expected_current_test}, found absent"
        )
    if existing is not None and expected_current_test == EXPECTED_TEST_ABSENT:
        raise PipelineError(
            "track-local TEST cell changed since review: expected absent, found "
            f"{current_variant}"
        )
    if (
        existing is not None
        and expected_current_test != EXPECTED_TEST_ABSENT
        and current_variant != expected_current_test
    ):
        raise PipelineError(
            "track-local TEST cell changed since review: expected "
            f"{expected_current_test}, found {current_variant}"
        )
    if (
        current_assignment_content_sha256 is None
        and expected_current_assignment != EXPECTED_ASSIGNMENT_ABSENT
    ):
        raise PipelineError(
            "track-local TEST assignment changed since review: expected "
            f"{expected_current_assignment}, found absent"
        )
    if (
        current_assignment_content_sha256 is not None
        and expected_current_assignment == EXPECTED_ASSIGNMENT_ABSENT
    ):
        raise PipelineError(
            "track-local TEST assignment changed since review: expected absent, "
            f"found {current_assignment_content_sha256}"
        )
    if (
        current_assignment_content_sha256 is not None
        and expected_current_assignment != EXPECTED_ASSIGNMENT_ABSENT
        and current_assignment_content_sha256 != expected_current_assignment
    ):
        raise PipelineError(
            "track-local TEST assignment changed since review: expected "
            f"{expected_current_assignment}, found "
            f"{current_assignment_content_sha256}"
        )
    version_slice, slice_comparison_basis = core_track_version_slice(
        track=track,
        slice_time=canonical_slice_time,
        spruce_branch_bases=spruce_branch_bases,
    )
    if not isinstance(spruce_branch_bases, Mapping) or not isinstance(
        main_release_roster, Mapping
    ):
        raise AssertionError("validated slice dependencies became invalid")
    try:
        slice_basis_snapshot = _slice_branch_basis_snapshot(
            spruce_branch_bases=spruce_branch_bases,
            catalog=catalog,
            main_release_roster=main_release_roster,
            catalog_file_sha256=sha256_file(
                repository_root / CORE_TRACK_CATALOG_PATH
            ),
            release_roster_file_sha256=sha256_file(
                repository_root / CORE_TRACK_MAIN_RELEASE_ROSTER_PATH
            ),
        )
    except OSError as exc:
        raise PipelineError(
            "version-slice dependency bytes are unavailable"
        ) from exc
    new_cell = {
        "build_pin_id": pin_id,
        "tuning_profile": tuning_profile,
        "applicable_chipsets": selected_applicability,
        "version_slice": version_slice,
    }
    new_variant = core_variant_id(
        core_id=core_id,
        cell_chipset=chipset,
        cell=new_cell,
        pin_index=pin_index,
        tunings=validated_tunings,
    )
    if planning:
        expected_new_variant = new_variant
    elif new_variant != expected_new_variant:
        raise PipelineError("new core track TEST variant changed since review")
    deferred_before = _effective_deferred_cells_unchecked(
        source["tracks"], track
    ).get((core_id, chipset))
    updated = copy.deepcopy(source)
    slice_registry = updated["version_policy"]["slice_comparison_bases"]
    existing_slice_basis = slice_registry.get(version_slice["content_sha256"])
    if (
        existing_slice_basis is not None
        and existing_slice_basis != slice_comparison_basis
    ):
        raise PipelineError(
            "existing version-slice comparison basis differs from this assignment"
        )
    slice_registry[version_slice["content_sha256"]] = copy.deepcopy(
        slice_comparison_basis
    )
    updated["version_policy"]["slice_comparison_bases"] = dict(
        sorted(slice_registry.items())
    )
    branch_registry_digest = spruce_branch_bases["content_sha256"]
    branch_snapshot_registry = updated["version_policy"][
        "slice_branch_basis_snapshots"
    ]
    existing_branch_snapshot = branch_snapshot_registry.get(
        branch_registry_digest
    )
    if (
        existing_branch_snapshot is not None
        and existing_branch_snapshot != slice_basis_snapshot
    ):
        raise PipelineError(
            "existing version-slice branch-basis snapshot differs from "
            "the current authority"
        )
    branch_snapshot_registry[branch_registry_digest] = copy.deepcopy(
        slice_basis_snapshot
    )
    updated["version_policy"]["slice_branch_basis_snapshots"] = dict(
        sorted(branch_snapshot_registry.items())
    )
    coordinate = (track, core_id, chipset)
    retained_bindings = [
        copy.deepcopy(record)
        for record in updated["source_order_parent_bindings"]
        if (
            record.get("track"),
            record.get("core_id"),
            record.get("chipset"),
        )
        != coordinate
    ]
    source_order_parent_binding = None
    if track != "main":
        assert parent_cell is not None
        assert parent_pin is not None
        assert parent_variant is not None
        assert parent_origin is not None
        assert parent_chipset is not None
        parent_lineage = None
        if track == "edge" and parent_origin == "nightly":
            binding_index, binding_errors = _source_order_parent_binding_index(
                source["source_order_parent_bindings"]
            )
            outlier_index, outlier_errors = _source_order_outlier_index(
                source["source_order_outliers"]
            )
            if binding_errors or outlier_errors:
                raise AssertionError("validated source-order indexes became invalid")
            parent_coordinate = ("nightly", core_id, parent_chipset)
            frozen_parent = binding_index.get(parent_coordinate)
            if frozen_parent is None:
                raise AssertionError("direct Nightly parent has no frozen lineage")
            parent_lineage = {
                "binding": copy.deepcopy(frozen_parent),
                "outlier": copy.deepcopy(outlier_index.get(parent_coordinate)),
            }
        source_order_parent_binding = _source_order_parent_binding(
            source_registry_content_sha256=source["content_sha256"],
            track=track,
            core_id=core_id,
            chipset=chipset,
            parent_origin_track=parent_origin,
            parent_selected_chipset=parent_chipset,
            parent_cell=parent_cell,
            parent_pin=parent_pin,
            parent_variant=parent_variant,
            parent_lineage=parent_lineage,
            child_cell=new_cell,
            child_pin=pin,
            child_variant=new_variant,
        )
        retained_bindings.append(source_order_parent_binding)
    retained_bindings.sort(
        key=lambda record: (
            CORE_TRACKS.index(record["track"]),
            record["core_id"],
            record["chipset"],
        )
    )
    updated["source_order_parent_bindings"] = retained_bindings
    retained_outliers = [
        copy.deepcopy(record)
        for record in updated["source_order_outliers"]
        if (
            record.get("track"),
            record.get("core_id"),
            record.get("chipset"),
        )
        != coordinate
    ]
    source_order_outlier = None
    if canonical_outlier_at is not None:
        assert source_order_parent_binding is not None
        source_order_outlier = _source_order_outlier_binding(
            parent_binding=source_order_parent_binding,
        )
        source_order_outlier.update(
            {
                "authorized_at": canonical_outlier_at,
                "authorized_by": outlier_authorized_by.strip(),
                "reason": outlier_reason.strip(),
            }
        )
        retained_outliers.append(source_order_outlier)
    retained_outliers.sort(
        key=lambda record: (
            CORE_TRACKS.index(record["track"]),
            record["core_id"],
            record["chipset"],
        )
    )
    updated["source_order_outliers"] = retained_outliers
    stable_before = copy.deepcopy(updated["tracks"][track]["stable"])
    direct_deferred = updated["tracks"][track]["deferred"]
    if isinstance(direct_deferred.get(core_id), Mapping):
        direct_deferred[core_id].pop(chipset, None)
        if not direct_deferred[core_id]:
            del direct_deferred[core_id]
    updated["tracks"][track]["test"].setdefault(core_id, {})[chipset] = new_cell
    updated["tracks"][track]["test"] = dict(
        sorted(updated["tracks"][track]["test"].items())
    )
    updated["tracks"][track]["test"][core_id] = dict(
        sorted(updated["tracks"][track]["test"][core_id].items())
    )
    updated["tracks"][track]["deferred"] = dict(
        sorted(updated["tracks"][track]["deferred"].items())
    )
    edge_deferred_by_admission = None
    if track in {"main", "nightly"} and not isinstance(
        updated["tracks"]["edge"]["test"].get(core_id, {}).get(chipset),
        Mapping,
    ):
        probe_tracks = copy.deepcopy(updated["tracks"])
        probe_edge_deferred = probe_tracks["edge"]["deferred"]
        if isinstance(probe_edge_deferred.get(core_id), Mapping):
            probe_edge_deferred[core_id].pop(chipset, None)
            if not probe_edge_deferred[core_id]:
                del probe_edge_deferred[core_id]
        inherited_edge = _effective_test_cells_unchecked(
            probe_tracks, "edge"
        ).get((core_id, chipset))
        inherited_edge_pin = (
            pin_index.get(inherited_edge[0].get("build_pin_id"))
            if inherited_edge is not None
            else None
        )
        if isinstance(inherited_edge_pin, Mapping) and not _pin_matches_edge_reviewed_head(
            updated, core_id=core_id, pin=inherited_edge_pin
        ):
            edge_deferred_cell = {
                "state": DEFERRED_STATE,
                "reason": DEFERRED_NO_REVIEWED_VERSION_REASON,
            }
            updated["tracks"]["edge"]["deferred"].setdefault(core_id, {})[
                chipset
            ] = edge_deferred_cell
            updated["tracks"]["edge"]["deferred"] = dict(
                sorted(updated["tracks"]["edge"]["deferred"].items())
            )
            updated["tracks"]["edge"]["deferred"][core_id] = dict(
                sorted(updated["tracks"]["edge"]["deferred"][core_id].items())
            )
            edge_deferred_by_admission = {
                "track": "edge",
                "core_id": core_id,
                "chipset": chipset,
                **edge_deferred_cell,
            }
        elif isinstance(inherited_edge_pin, Mapping):
            direct_edge_deferred = updated["tracks"]["edge"]["deferred"]
            if isinstance(direct_edge_deferred.get(core_id), Mapping):
                direct_edge_deferred[core_id].pop(chipset, None)
                if not direct_edge_deferred[core_id]:
                    del direct_edge_deferred[core_id]
            updated["tracks"]["edge"]["deferred"] = dict(
                sorted(direct_edge_deferred.items())
            )
    if (core_id, chipset) in _effective_deferred_cells_unchecked(
        updated["tracks"], track
    ):
        raise AssertionError("TEST admission did not clear effective deferred state")
    if updated["tracks"][track]["stable"] != stable_before:
        raise AssertionError("TEST admission changed stable approval state")
    updated["content_sha256"] = core_tracks_content_sha256(updated)
    validated = validate_core_tracks(
        updated,
        catalog=catalog,
        pin_index=pin_index,
        tunings=validated_tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=validation_source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
    )
    assignment_content_sha256 = core_track_assignment_content_sha256(
        track=track,
        core_id=core_id,
        chipset=chipset,
        cell=new_cell,
        parent_registry_content_sha256=(
            source["content_sha256"] if track != "main" else None
        ),
    )
    assert isinstance(expected_source_registry, str)
    assert isinstance(expected_current_test, str)
    assert isinstance(expected_current_assignment, str)
    assert isinstance(expected_new_variant, str)
    return {
        "registry": validated,
        "cell": copy.deepcopy(new_cell),
        "previous_variant_id": current_variant,
        "previous_assignment_content_sha256": (
            current_assignment_content_sha256
        ),
        "previous_deferred": (
            copy.deepcopy(deferred_before[0])
            if deferred_before is not None
            else None
        ),
        "parent_variant_id": parent_variant,
        "parent_registry_content_sha256": (
            source["content_sha256"] if track != "main" else None
        ),
        "parent_selection_content_sha256": (
            source_order_parent_binding[
                "parent_selection_content_sha256"
            ]
            if source_order_parent_binding is not None
            else None
        ),
        "version_slice": copy.deepcopy(version_slice),
        "slice_comparison_basis": copy.deepcopy(slice_comparison_basis),
        "slice_branch_basis_registry_content_sha256": branch_registry_digest,
        "slice_branch_basis_snapshot": copy.deepcopy(slice_basis_snapshot),
        "assignment_content_sha256": assignment_content_sha256,
        "snapshot": copy.deepcopy(parent_snapshot),
        "snapshot_path": (
            parent_snapshot_entry["path"]
            if parent_snapshot_entry is not None
            else None
        ),
        "snapshot_file_sha256": (
            parent_snapshot_entry["file_sha256"]
            if parent_snapshot_entry is not None
            else None
        ),
        "source_order_parent_binding": copy.deepcopy(
            source_order_parent_binding
        ),
        "source_order_outlier": copy.deepcopy(source_order_outlier),
        "edge_deferred_by_admission": copy.deepcopy(
            edge_deferred_by_admission
        ),
        "variant_id": new_variant,
        "source_registry_content_sha256": source["content_sha256"],
        "expectations": {
            "expected_source_registry": expected_source_registry,
            "expected_current_test": expected_current_test,
            "expected_current_assignment": expected_current_assignment,
            "expected_new_variant": expected_new_variant,
            "expected_parent_variant": expected_parent_variant,
            "expected_parent_registry": expected_parent_registry,
        },
    }


def plan_core_track_test(
    document: object,
    *,
    repository_root: Path,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    track: str,
    core_id: str,
    chipset: str,
    pin_id: str,
    tuning_profile: str,
    slice_time: str,
    applicable_chipsets: Sequence[str] | None = None,
    outlier_authorized_at: str | None = None,
    outlier_authorized_by: str | None = None,
    outlier_reason: str | None = None,
) -> dict[str, Any]:
    """Plan and validate one TEST transition without enforcing or writing it."""

    return _evaluate_core_track_test(
        document,
        repository_root=repository_root,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
        track=track,
        core_id=core_id,
        chipset=chipset,
        pin_id=pin_id,
        tuning_profile=tuning_profile,
        slice_time=slice_time,
        expectations=None,
        applicable_chipsets=applicable_chipsets,
        outlier_authorized_at=outlier_authorized_at,
        outlier_authorized_by=outlier_authorized_by,
        outlier_reason=outlier_reason,
    )


def set_core_track_test(
    document: object,
    *,
    repository_root: Path,
    catalog: Mapping[str, Any],
    pin_index: Mapping[str, Mapping[str, Any]],
    tunings: object,
    main_release_roster: object,
    spruce_branch_bases: object,
    source_registry_index: Mapping[str, Mapping[str, Any]],
    source_ancestry_verifier: Callable[[str, str, str, str], bool] | None,
    track: str,
    core_id: str,
    chipset: str,
    pin_id: str,
    tuning_profile: str,
    slice_time: str,
    expected_source_registry: str,
    expected_current_test: str,
    expected_current_assignment: str,
    expected_new_variant: str,
    expected_parent_variant: str | None,
    expected_parent_registry: str | None,
    applicable_chipsets: Sequence[str] | None = None,
    outlier_authorized_at: str | None = None,
    outlier_authorized_by: str | None = None,
    outlier_reason: str | None = None,
) -> dict[str, Any]:
    """CAS one authoritative pin into one exact track-local TEST cell."""

    return _evaluate_core_track_test(
        document,
        repository_root=repository_root,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tunings,
        main_release_roster=main_release_roster,
        spruce_branch_bases=spruce_branch_bases,
        source_registry_index=source_registry_index,
        source_ancestry_verifier=source_ancestry_verifier,
        track=track,
        core_id=core_id,
        chipset=chipset,
        pin_id=pin_id,
        tuning_profile=tuning_profile,
        slice_time=slice_time,
        expectations=_CoreTrackTestExpectations(
            source_registry=expected_source_registry,
            current_test=expected_current_test,
            current_assignment=expected_current_assignment,
            new_variant=expected_new_variant,
            parent_variant=expected_parent_variant,
            parent_registry=expected_parent_registry,
        ),
        applicable_chipsets=applicable_chipsets,
        outlier_authorized_at=outlier_authorized_at,
        outlier_authorized_by=outlier_authorized_by,
        outlier_reason=outlier_reason,
    )
