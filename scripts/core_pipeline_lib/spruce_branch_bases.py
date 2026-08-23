"""Exact, artifact-only identities for Spruce branch core trees.

This module deliberately does not infer source commits, recipes, toolchains, or
reproducible-build provenance from shipped ELF files.  A branch basis is only a
byte-exact statement about Git objects already present in a Spruce branch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .errors import PipelineError


SPRUCE_BRANCH_BASES_MANIFEST_PATH = "manifests/spruce-core-branch-bases.json"
SPRUCE_BRANCH_BASES_SCHEMA_REF = "./spruce-core-branch-bases.schema.json"
SPRUCE_BRANCH_BASES_SCHEMA_VERSION = 1
SPRUCE_BRANCH_BASES_MODEL = "spruce-git-branch-artifact-basis-v1"
SPRUCE_BRANCH_BASES_PROVENANCE_MODEL = (
    "artifact-only-no-source-recipe-toolchain-provenance-v1"
)
SPRUCE_REPOSITORY = "https://github.com/spruceUI/spruceOS.git"
SPRUCE_CATALOG_PATH = "manifests/core-builds.json"
SPRUCE_RELEASE_ROSTER_PATH = "manifests/spruce-release-roster.json"

SPRUCE_BRANCH_SPECS: dict[str, dict[str, str]] = {
    "spruce-development": {
        "track": "nightly",
        "ref": "refs/heads/Development",
        "local_ref": "refs/remotes/origin/Development",
        "commit": "c0bf28c047bfaeac317323f1c581faf51a786c4b",
        "tree": "4c58ba1ded35cb08bc75eb8c9dec3199dca47600",
    },
    "spruce-main": {
        "track": "main",
        "ref": "refs/heads/main",
        "local_ref": "refs/remotes/origin/main",
        "commit": "de480d2b2c2d5e3b692eb7dc6c3bae6692395fb1",
        "tree": "f57693ecbded5cf6a550a6a2af4b651685b381c0",
    },
}

SPRUCE_CORE_TREES: dict[str, dict[str, str]] = {
    "arm64": {
        "path": "RetroArch/.retroarch/cores64",
        "tree": "db1ab83ccd170a124a172a3b0192838d5d4ae905",
    },
    "armhf": {
        "path": "RetroArch/.retroarch/cores",
        "tree": "fe73cd4bca2ce0130bd95b35805b01ebf5d5c336",
    },
}

# These names, tracks, and branch refs are part of the durable artifact-basis
# model.  Unlike ``SPRUCE_BRANCH_SPECS``, this projection deliberately omits
# the reviewed commit/tree values so an immutable old registry can still be
# validated after the live reviewed heads advance.
SPRUCE_DETACHED_BRANCH_SPECS: dict[str, dict[str, str]] = {
    "spruce-development": {
        "track": "nightly",
        "ref": "refs/heads/Development",
    },
    "spruce-main": {
        "track": "main",
        "ref": "refs/heads/main",
    },
}

# Manual review authority for immutable historical branch-basis registries.
# New reviewed registries are appended; existing entries must never be removed
# merely because the live branch heads advance.  The detached validator below
# combines this external anchor with a full internal validation of the frozen
# registry and all of its catalog/roster dependencies.
SPRUCE_REVIEWED_BRANCH_BASIS_SNAPSHOT_CONTENT_SHA256 = frozenset(
    {
        "c9a4abe291688e8e615b90f028e20dd5f2831e95cd560d63ea18e667c234fe7d",
        "d98259a71405079c9eb0c0a1d625ac234445dc65800073908d0ed2500b9601f6",
    }
)

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SHIPPED_CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
ARCHITECTURES = ("arm64", "armhf")
CATALOG_CELL_STATUSES = frozenset({"valid", "not_shipped", "invalid"})
ARTIFACT_CORRELATION_STATUSES = frozenset(
    {"catalog_exact", "catalog_alias", "uncataloged"}
)


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def catalog_semantic_sha256(catalog: Mapping[str, Any]) -> str:
    """Return the deterministic semantic identity of the complete catalog."""

    return _semantic_sha256(catalog)


def release_roster_semantic_sha256(roster: Mapping[str, Any]) -> str:
    """Return the roster identity using its declared semantic projection."""

    return _semantic_sha256(
        {
            "schema_version": roster.get("schema_version"),
            "roster_model": roster.get("roster_model"),
            "correlation_model": roster.get("correlation_model"),
            "release": roster.get("release"),
            "cataloged_core_ids": roster.get("cataloged_core_ids"),
            "alias_core_ids": roster.get("alias_core_ids"),
            "uncataloged_core_ids": roster.get("uncataloged_core_ids"),
        }
    )


def spruce_branch_artifact_identity_set_sha256(
    artifacts: Sequence[Mapping[str, Any]],
) -> str:
    """Return the semantic identity of an ordered physical artifact set."""

    return _semantic_sha256(list(artifacts))


def spruce_branch_basis_content_sha256(basis: Mapping[str, Any]) -> str:
    """Return the semantic identity of one branch basis."""

    return _semantic_sha256(
        {key: value for key, value in basis.items() if key != "content_sha256"}
    )


def spruce_branch_bases_content_sha256(document: Mapping[str, Any]) -> str:
    """Return the semantic identity of the branch-basis registry."""

    return _semantic_sha256(
        {
            key: value
            for key, value in document.items()
            if key not in {"$schema", "content_sha256"}
        }
    )


def spruce_branch_basis_catalog_cell_index(
    basis: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    """Index the exact catalog cells in a validated basis.

    Duplicate or malformed cell keys fail closed instead of being overwritten.
    """

    cells = basis.get("catalog_cells")
    if not isinstance(cells, list):
        raise PipelineError("Spruce branch basis catalog_cells must be a list")
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    for offset, cell in enumerate(cells):
        if not isinstance(cell, Mapping):
            raise PipelineError(f"Spruce branch catalog cell {offset} is not an object")
        core_id = cell.get("core_id")
        architecture = cell.get("architecture")
        if not isinstance(core_id, str) or not isinstance(architecture, str):
            raise PipelineError(f"Spruce branch catalog cell {offset} has no exact key")
        key = (core_id, architecture)
        if key in index:
            raise PipelineError(
                f"duplicate Spruce branch catalog cell {core_id}:{architecture}"
            )
        index[key] = cell
    return index


def load_spruce_branch_basis_index(
    document: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    """Return the basis-id index from a validated registry shape."""

    bases = document.get("bases")
    if not isinstance(bases, Mapping):
        raise PipelineError("Spruce branch bases registry has no bases object")
    result: dict[str, Mapping[str, Any]] = {}
    for basis_id, basis in bases.items():
        if not isinstance(basis_id, str) or not isinstance(basis, Mapping):
            raise PipelineError("Spruce branch bases registry contains a malformed basis")
        if basis.get("basis_id") != basis_id:
            raise PipelineError(f"Spruce branch basis key mismatch: {basis_id}")
        result[basis_id] = basis
    return result


def _is_sha1(value: object) -> bool:
    return isinstance(value, str) and SHA1_RE.fullmatch(value) is not None


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _artifact_architecture_is_valid(artifact: Mapping[str, Any]) -> bool:
    architecture = artifact.get("architecture")
    elf = artifact.get("elf")
    if not isinstance(elf, Mapping) or elf.get("data") != "little-endian":
        return False
    if elf.get("type") != "DYN":
        return False
    if architecture == "arm64":
        return elf.get("class") == "ELF64" and elf.get("machine") == "AArch64"
    if architecture == "armhf":
        return (
            elf.get("class") == "ELF32"
            and elf.get("machine") == "ARM"
            and elf.get("float_abi") == "hard"
        )
    return False


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> list[str]:
    actual = set(value)
    if actual == expected:
        return []
    return [
        f"{label} keys differ: missing={sorted(expected - actual)!r} "
        f"unexpected={sorted(actual - expected)!r}"
    ]


def spruce_branch_bases_errors(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    catalog_file_sha256: str,
    roster_file_sha256: str,
    roster: Mapping[str, Any] | None = None,
    release_roster: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return every fail-closed branch-basis registry validation error.

    ``release_roster`` is accepted as a spelling-compatible alias for callers
    that make the manifest's full name explicit.  Supplying both is rejected.
    """

    errors: list[str] = []
    if roster is not None and release_roster is not None:
        return ["provide roster or release_roster, not both"]
    roster = roster if roster is not None else release_roster
    if not isinstance(document, Mapping):
        return ["Spruce branch bases document must be an object"]
    if not isinstance(catalog, Mapping):
        return ["Spruce core catalog must be an object"]
    if not isinstance(roster, Mapping):
        return ["Spruce release roster must be an object"]

    errors.extend(
        _exact_keys(
            document,
            {
                "$schema",
                "schema_version",
                "basis_model",
                "provenance_model",
                "catalog",
                "release_roster",
                "bases",
                "cross_branch_core_identity",
                "content_sha256",
            },
            "Spruce branch bases document",
        )
    )
    constants = {
        "$schema": SPRUCE_BRANCH_BASES_SCHEMA_REF,
        "schema_version": SPRUCE_BRANCH_BASES_SCHEMA_VERSION,
        "basis_model": SPRUCE_BRANCH_BASES_MODEL,
        "provenance_model": SPRUCE_BRANCH_BASES_PROVENANCE_MODEL,
    }
    for key, expected in constants.items():
        if document.get(key) != expected:
            errors.append(f"Spruce branch bases {key} must equal {expected!r}")

    catalog_ref = document.get("catalog")
    if not isinstance(catalog_ref, Mapping):
        errors.append("Spruce branch bases catalog reference must be an object")
    else:
        errors.extend(
            _exact_keys(
                catalog_ref,
                {"path", "file_sha256", "semantic_sha256"},
                "Spruce branch bases catalog reference",
            )
        )
        if catalog_ref.get("path") != SPRUCE_CATALOG_PATH:
            errors.append("Spruce branch bases catalog path is not canonical")
        if not _is_sha256(catalog_ref.get("file_sha256")):
            errors.append("Spruce branch bases catalog file_sha256 is malformed")
        elif not _is_sha256(catalog_file_sha256):
            errors.append("Supplied Spruce catalog file_sha256 is malformed")
        elif catalog_ref.get("file_sha256") != catalog_file_sha256:
            errors.append("Spruce branch bases catalog file identity is stale")
        if catalog_ref.get("semantic_sha256") != catalog_semantic_sha256(catalog):
            errors.append("Spruce branch bases catalog semantic identity is stale")

    roster_ref = document.get("release_roster")
    if not isinstance(roster_ref, Mapping):
        errors.append("Spruce branch bases release_roster reference must be an object")
    else:
        errors.extend(
            _exact_keys(
                roster_ref,
                {"path", "file_sha256", "content_sha256"},
                "Spruce branch bases release_roster reference",
            )
        )
        if roster_ref.get("path") != SPRUCE_RELEASE_ROSTER_PATH:
            errors.append("Spruce branch bases release roster path is not canonical")
        if not _is_sha256(roster_ref.get("file_sha256")):
            errors.append("Spruce branch bases release roster file_sha256 is malformed")
        elif not _is_sha256(roster_file_sha256):
            errors.append("Supplied Spruce release roster file_sha256 is malformed")
        elif roster_ref.get("file_sha256") != roster_file_sha256:
            errors.append("Spruce branch bases release roster file identity is stale")
        expected_roster_identity = release_roster_semantic_sha256(roster)
        if roster_ref.get("content_sha256") != expected_roster_identity:
            errors.append("Spruce branch bases release roster identity is stale")
        if roster.get("content_sha256") != expected_roster_identity:
            errors.append("Supplied Spruce release roster content_sha256 is invalid")

    catalog_cores = catalog.get("cores")
    if not isinstance(catalog_cores, Mapping):
        errors.append("Spruce core catalog has no cores object")
        catalog_core_ids: set[str] = set()
    else:
        catalog_core_ids = {
            core_id for core_id in catalog_cores if isinstance(core_id, str)
        }
        if len(catalog_core_ids) != len(catalog_cores):
            errors.append("Spruce core catalog contains a non-string core id")

    roster_cataloged = roster.get("cataloged_core_ids")
    if not isinstance(roster_cataloged, list) or set(roster_cataloged) != catalog_core_ids:
        errors.append("Spruce release roster cataloged ids do not match the catalog")
    raw_aliases = roster.get("alias_core_ids")
    aliases: dict[str, str] = {}
    if isinstance(raw_aliases, Mapping):
        for catalog_core_id, shipped_ids in raw_aliases.items():
            if not isinstance(shipped_ids, list):
                errors.append(f"Spruce release alias list for {catalog_core_id!r} is malformed")
                continue
            for shipped_id in shipped_ids:
                if not isinstance(shipped_id, str) or shipped_id in aliases:
                    errors.append(f"Spruce release alias {shipped_id!r} is malformed or duplicated")
                    continue
                aliases[shipped_id] = str(catalog_core_id)
    else:
        errors.append("Spruce release roster alias_core_ids must be an object")
    raw_uncataloged = roster.get("uncataloged_core_ids")
    uncataloged = set(raw_uncataloged) if isinstance(raw_uncataloged, list) else set()
    if not isinstance(raw_uncataloged, list):
        errors.append("Spruce release roster uncataloged_core_ids must be a list")

    bases = document.get("bases")
    if not isinstance(bases, Mapping):
        errors.append("Spruce branch bases bases must be an object")
        bases = {}
    if set(bases) != set(SPRUCE_BRANCH_SPECS):
        errors.append(
            "Spruce branch basis ids differ: "
            f"expected={sorted(SPRUCE_BRANCH_SPECS)!r} actual={sorted(bases)!r}"
        )

    basis_artifact_hashes: dict[str, str] = {}
    for basis_id in sorted(SPRUCE_BRANCH_SPECS):
        basis = bases.get(basis_id)
        if not isinstance(basis, Mapping):
            errors.append(f"Spruce branch basis {basis_id} must be an object")
            continue
        errors.extend(
            _basis_errors(
                basis_id,
                basis,
                catalog_core_ids=catalog_core_ids,
                aliases=aliases,
                uncataloged=uncataloged,
                spec=SPRUCE_BRANCH_SPECS[basis_id],
                core_trees=SPRUCE_CORE_TREES,
                require_reviewed_counts=True,
            )
        )
        summary = basis.get("summary")
        if isinstance(summary, Mapping) and isinstance(
            summary.get("artifact_identity_set_sha256"), str
        ):
            basis_artifact_hashes[basis_id] = summary["artifact_identity_set_sha256"]

    cross = document.get("cross_branch_core_identity")
    if not isinstance(cross, Mapping):
        errors.append("cross_branch_core_identity must be an object")
    else:
        errors.extend(
            _exact_keys(
                cross,
                {
                    "basis_ids",
                    "core_trees_identical",
                    "artifact_bytes_identical",
                    "core_trees",
                    "artifact_identity_set_sha256",
                },
                "cross_branch_core_identity",
            )
        )
        if cross.get("basis_ids") != sorted(SPRUCE_BRANCH_SPECS):
            errors.append("cross-branch basis_ids are not exact")
        if cross.get("core_trees_identical") is not True:
            errors.append("cross-branch core_trees_identical must be true")
        if cross.get("artifact_bytes_identical") is not True:
            errors.append("cross-branch artifact_bytes_identical must be true")
        if cross.get("core_trees") != SPRUCE_CORE_TREES:
            errors.append("cross-branch core tree identities are stale")
        unique_artifact_hashes = set(basis_artifact_hashes.values())
        if len(unique_artifact_hashes) != 1:
            errors.append("branch artifact identity sets are not identical")
        elif cross.get("artifact_identity_set_sha256") not in unique_artifact_hashes:
            errors.append("cross-branch artifact identity hash is stale")

    content_sha256 = document.get("content_sha256")
    if not _is_sha256(content_sha256):
        errors.append("Spruce branch bases content_sha256 is malformed")
    elif content_sha256 != spruce_branch_bases_content_sha256(document):
        errors.append("Spruce branch bases content_sha256 is stale")
    return errors


def spruce_branch_bases_detached_snapshot_errors(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    catalog_file_sha256: str,
    roster_file_sha256: str,
    roster: Mapping[str, Any] | None = None,
    release_roster: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate one immutable, dependency-complete historical registry.

    The live validator above intentionally compares branch commits, trees, and
    core-tree objects with today's reviewed constants.  That is correct for
    new admissions but would make a previously authenticated version slice
    expire whenever those constants advance.  This detached validator instead
    proves the frozen registry is internally exact: it validates the complete
    frozen catalog and roster bindings, both canonical branch identities,
    every artifact/cell correlation, shared core-tree identities, and all
    semantic digests.  It does not consult today's commit/tree constants.

    Callers must keep the returned object behind an append-only content-addressed
    authority.  This function validates immutable evidence; it does not make an
    arbitrary inline projection authoritative by itself.
    """

    errors: list[str] = []
    if roster is not None and release_roster is not None:
        return ["provide roster or release_roster, not both"]
    roster = roster if roster is not None else release_roster
    if not isinstance(document, Mapping):
        return ["Spruce branch bases document must be an object"]
    if not isinstance(catalog, Mapping):
        return ["Spruce core catalog must be an object"]
    if not isinstance(roster, Mapping):
        return ["Spruce release roster must be an object"]
    if document.get("content_sha256") not in (
        SPRUCE_REVIEWED_BRANCH_BASIS_SNAPSHOT_CONTENT_SHA256
    ):
        errors.append(
            "Spruce branch bases detached snapshot is not in the append-only "
            "reviewed registry"
        )
    try:
        # Kept lazy so the canonical live branch-basis module remains usable
        # independently.  Historical slice validation is invoked only after
        # the track model has loaded, and must apply the same exact roster
        # schema/shape/semantic checks as the live authority path.
        from .tracks import spruce_release_roster_errors
    except ImportError:
        errors.append("Spruce release roster validator is unavailable")
    else:
        try:
            frozen_roster_errors = spruce_release_roster_errors(
                roster,
                catalog=catalog,
            )
        except Exception as exc:
            errors.append(
                "Spruce release roster validation failed "
                f"({type(exc).__name__})"
            )
        else:
            if not isinstance(frozen_roster_errors, list):
                errors.append("Spruce release roster validator report is invalid")
            else:
                errors.extend(
                    f"frozen {error}" for error in frozen_roster_errors
                )

    errors.extend(
        _exact_keys(
            document,
            {
                "$schema",
                "schema_version",
                "basis_model",
                "provenance_model",
                "catalog",
                "release_roster",
                "bases",
                "cross_branch_core_identity",
                "content_sha256",
            },
            "Spruce branch bases document",
        )
    )
    constants = {
        "$schema": SPRUCE_BRANCH_BASES_SCHEMA_REF,
        "schema_version": SPRUCE_BRANCH_BASES_SCHEMA_VERSION,
        "basis_model": SPRUCE_BRANCH_BASES_MODEL,
        "provenance_model": SPRUCE_BRANCH_BASES_PROVENANCE_MODEL,
    }
    for key, expected in constants.items():
        if document.get(key) != expected:
            errors.append(f"Spruce branch bases {key} must equal {expected!r}")

    catalog_ref = document.get("catalog")
    if not isinstance(catalog_ref, Mapping):
        errors.append("Spruce branch bases catalog reference must be an object")
    else:
        errors.extend(
            _exact_keys(
                catalog_ref,
                {"path", "file_sha256", "semantic_sha256"},
                "Spruce branch bases catalog reference",
            )
        )
        if catalog_ref.get("path") != SPRUCE_CATALOG_PATH:
            errors.append("Spruce branch bases catalog path is not canonical")
        if not _is_sha256(catalog_ref.get("file_sha256")):
            errors.append("Spruce branch bases catalog file_sha256 is malformed")
        elif not _is_sha256(catalog_file_sha256):
            errors.append("Supplied Spruce catalog file_sha256 is malformed")
        elif catalog_ref.get("file_sha256") != catalog_file_sha256:
            errors.append("Spruce branch bases catalog file identity is stale")
        if catalog_ref.get("semantic_sha256") != catalog_semantic_sha256(catalog):
            errors.append("Spruce branch bases catalog semantic identity is stale")

    roster_ref = document.get("release_roster")
    if not isinstance(roster_ref, Mapping):
        errors.append("Spruce branch bases release_roster reference must be an object")
    else:
        errors.extend(
            _exact_keys(
                roster_ref,
                {"path", "file_sha256", "content_sha256"},
                "Spruce branch bases release_roster reference",
            )
        )
        if roster_ref.get("path") != SPRUCE_RELEASE_ROSTER_PATH:
            errors.append("Spruce branch bases release roster path is not canonical")
        if not _is_sha256(roster_ref.get("file_sha256")):
            errors.append("Spruce branch bases release roster file_sha256 is malformed")
        elif not _is_sha256(roster_file_sha256):
            errors.append("Supplied Spruce release roster file_sha256 is malformed")
        elif roster_ref.get("file_sha256") != roster_file_sha256:
            errors.append("Spruce branch bases release roster file identity is stale")
        expected_roster_identity = release_roster_semantic_sha256(roster)
        if roster_ref.get("content_sha256") != expected_roster_identity:
            errors.append("Spruce branch bases release roster identity is stale")
        if roster.get("content_sha256") != expected_roster_identity:
            errors.append("Supplied Spruce release roster content_sha256 is invalid")

    catalog_cores = catalog.get("cores")
    if not isinstance(catalog_cores, Mapping):
        errors.append("Spruce core catalog has no cores object")
        catalog_core_ids: set[str] = set()
    else:
        catalog_core_ids = {
            core_id for core_id in catalog_cores if isinstance(core_id, str)
        }
        if len(catalog_core_ids) != len(catalog_cores):
            errors.append("Spruce core catalog contains a non-string core id")

    roster_cataloged = roster.get("cataloged_core_ids")
    if not isinstance(roster_cataloged, list) or set(roster_cataloged) != catalog_core_ids:
        errors.append("Spruce release roster cataloged ids do not match the catalog")
    raw_aliases = roster.get("alias_core_ids")
    aliases: dict[str, str] = {}
    if isinstance(raw_aliases, Mapping):
        for catalog_core_id, shipped_ids in raw_aliases.items():
            if not isinstance(shipped_ids, list):
                errors.append(f"Spruce release alias list for {catalog_core_id!r} is malformed")
                continue
            for shipped_id in shipped_ids:
                if not isinstance(shipped_id, str) or shipped_id in aliases:
                    errors.append(
                        f"Spruce release alias {shipped_id!r} is malformed or duplicated"
                    )
                    continue
                aliases[shipped_id] = str(catalog_core_id)
    else:
        errors.append("Spruce release roster alias_core_ids must be an object")
    raw_uncataloged = roster.get("uncataloged_core_ids")
    uncataloged = set(raw_uncataloged) if isinstance(raw_uncataloged, list) else set()
    if not isinstance(raw_uncataloged, list):
        errors.append("Spruce release roster uncataloged_core_ids must be a list")

    cross = document.get("cross_branch_core_identity")
    frozen_core_trees: Mapping[str, Any] = {}
    if not isinstance(cross, Mapping):
        errors.append("cross_branch_core_identity must be an object")
    else:
        errors.extend(
            _exact_keys(
                cross,
                {
                    "basis_ids",
                    "core_trees_identical",
                    "artifact_bytes_identical",
                    "core_trees",
                    "artifact_identity_set_sha256",
                },
                "cross_branch_core_identity",
            )
        )
        raw_core_trees = cross.get("core_trees")
        if not isinstance(raw_core_trees, Mapping) or set(raw_core_trees) != set(
            ARCHITECTURES
        ):
            errors.append("cross-branch core tree identities are malformed")
        else:
            frozen_core_trees = raw_core_trees
            for architecture in ARCHITECTURES:
                tree = raw_core_trees.get(architecture)
                if (
                    not isinstance(tree, Mapping)
                    or set(tree) != {"path", "tree"}
                    or tree.get("path")
                    != (
                        "RetroArch/.retroarch/cores64"
                        if architecture == "arm64"
                        else "RetroArch/.retroarch/cores"
                    )
                    or not _is_sha1(tree.get("tree"))
                ):
                    errors.append(
                        f"cross-branch {architecture} core tree identity is malformed"
                    )

    bases = document.get("bases")
    if not isinstance(bases, Mapping):
        errors.append("Spruce branch bases bases must be an object")
        bases = {}
    if set(bases) != set(SPRUCE_DETACHED_BRANCH_SPECS):
        errors.append(
            "Spruce branch basis ids differ: "
            f"expected={sorted(SPRUCE_DETACHED_BRANCH_SPECS)!r} "
            f"actual={sorted(bases)!r}"
        )

    basis_artifact_hashes: dict[str, str] = {}
    for basis_id in sorted(SPRUCE_DETACHED_BRANCH_SPECS):
        basis = bases.get(basis_id)
        if not isinstance(basis, Mapping):
            errors.append(f"Spruce branch basis {basis_id} must be an object")
            continue
        durable_spec = SPRUCE_DETACHED_BRANCH_SPECS[basis_id]
        branch = basis.get("branch")
        if not isinstance(branch, Mapping) or set(branch) != {
            "repository",
            "ref",
            "commit",
            "tree",
        }:
            errors.append(f"Spruce branch basis {basis_id} branch identity is malformed")
            spec = {
                "track": durable_spec["track"],
                "ref": durable_spec["ref"],
                "commit": "",
                "tree": "",
            }
        else:
            if branch.get("repository") != SPRUCE_REPOSITORY:
                errors.append(
                    f"Spruce branch basis {basis_id} repository is not canonical"
                )
            if branch.get("ref") != durable_spec["ref"]:
                errors.append(f"Spruce branch basis {basis_id} ref is not canonical")
            if not _is_sha1(branch.get("commit")):
                errors.append(f"Spruce branch basis {basis_id} commit is malformed")
            if not _is_sha1(branch.get("tree")):
                errors.append(f"Spruce branch basis {basis_id} tree is malformed")
            spec = {
                "track": durable_spec["track"],
                "ref": durable_spec["ref"],
                "commit": str(branch.get("commit")),
                "tree": str(branch.get("tree")),
            }
        errors.extend(
            _basis_errors(
                basis_id,
                basis,
                catalog_core_ids=catalog_core_ids,
                aliases=aliases,
                uncataloged=uncataloged,
                spec=spec,
                core_trees=frozen_core_trees,
                require_reviewed_counts=False,
            )
        )
        summary = basis.get("summary")
        if isinstance(summary, Mapping) and isinstance(
            summary.get("artifact_identity_set_sha256"), str
        ):
            basis_artifact_hashes[basis_id] = summary[
                "artifact_identity_set_sha256"
            ]

    if isinstance(cross, Mapping):
        if cross.get("basis_ids") != sorted(SPRUCE_DETACHED_BRANCH_SPECS):
            errors.append("cross-branch basis_ids are not exact")
        if cross.get("core_trees_identical") is not True:
            errors.append("cross-branch core_trees_identical must be true")
        if cross.get("artifact_bytes_identical") is not True:
            errors.append("cross-branch artifact_bytes_identical must be true")
        unique_artifact_hashes = set(basis_artifact_hashes.values())
        if len(unique_artifact_hashes) != 1:
            errors.append("branch artifact identity sets are not identical")
        elif cross.get("artifact_identity_set_sha256") not in unique_artifact_hashes:
            errors.append("cross-branch artifact identity hash is stale")

    content_sha256 = document.get("content_sha256")
    if not _is_sha256(content_sha256):
        errors.append("Spruce branch bases content_sha256 is malformed")
    elif content_sha256 != spruce_branch_bases_content_sha256(document):
        errors.append("Spruce branch bases content_sha256 is stale")
    return errors


def _basis_errors(
    basis_id: str,
    basis: Mapping[str, Any],
    *,
    catalog_core_ids: set[str],
    aliases: Mapping[str, str],
    uncataloged: set[Any],
    spec: Mapping[str, str],
    core_trees: Mapping[str, Any],
    require_reviewed_counts: bool,
) -> list[str]:
    errors: list[str] = []
    label = f"Spruce branch basis {basis_id}"
    errors.extend(
        _exact_keys(
            basis,
            {
                "basis_id",
                "track",
                "branch",
                "core_trees",
                "provenance",
                "artifacts",
                "catalog_cells",
                "summary",
                "content_sha256",
            },
            label,
        )
    )
    if basis.get("basis_id") != basis_id:
        errors.append(f"{label} basis_id differs from its key")
    if basis.get("track") != spec["track"]:
        errors.append(f"{label} track is stale")
    branch = basis.get("branch")
    expected_branch = {
        "repository": SPRUCE_REPOSITORY,
        "ref": spec["ref"],
        "commit": spec["commit"],
        "tree": spec["tree"],
    }
    if branch != expected_branch:
        errors.append(f"{label} branch identity is not the reviewed exact identity")
    if basis.get("core_trees") != core_trees:
        errors.append(f"{label} core tree identities are stale")
    expected_provenance = {
        "kind": "artifact-only",
        "source_commits": "not-established",
        "submodule_commits": "not-established",
        "build_recipes": "not-established",
        "toolchains": "not-established",
        "reproducible_builds": "not-established",
    }
    if basis.get("provenance") != expected_provenance:
        errors.append(f"{label} must retain exact artifact-only provenance")

    artifacts = basis.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append(f"{label} artifacts must be a list")
        artifacts = []
    if artifacts != sorted(artifacts, key=lambda value: str(value.get("path", ""))):
        errors.append(f"{label} artifacts are not sorted by path")
    path_index: dict[str, Mapping[str, Any]] = {}
    canonical_index: dict[tuple[str, str], Mapping[str, Any]] = {}
    alias_count = 0
    uncataloged_count = 0
    shipped_names: set[str] = set()
    for offset, artifact in enumerate(artifacts):
        artifact_label = f"{label} artifact {offset}"
        if not isinstance(artifact, Mapping):
            errors.append(f"{artifact_label} must be an object")
            continue
        errors.extend(
            _artifact_errors(
                artifact,
                artifact_label,
                core_trees=core_trees,
            )
        )
        path = artifact.get("path")
        architecture = artifact.get("architecture")
        shipped_core_id = artifact.get("shipped_core_id")
        if isinstance(path, str):
            if path in path_index:
                errors.append(f"{label} repeats artifact path {path}")
            path_index[path] = artifact
        if isinstance(shipped_core_id, str):
            shipped_names.add(shipped_core_id)
        correlation = artifact.get("catalog_correlation")
        if not isinstance(correlation, Mapping):
            continue
        status = correlation.get("status")
        catalog_core_id = correlation.get("catalog_core_id")
        if shipped_core_id in catalog_core_ids:
            if status != "catalog_exact" or catalog_core_id != shipped_core_id:
                errors.append(f"{artifact_label} has stale exact catalog correlation")
            elif isinstance(architecture, str):
                key = (shipped_core_id, architecture)
                if key in canonical_index:
                    errors.append(f"{label} repeats canonical artifact {key}")
                canonical_index[key] = artifact
        elif isinstance(shipped_core_id, str) and shipped_core_id in aliases:
            alias_count += 1
            if status != "catalog_alias" or catalog_core_id != aliases[shipped_core_id]:
                errors.append(f"{artifact_label} has stale alias catalog correlation")
        elif shipped_core_id in uncataloged:
            uncataloged_count += 1
            if status != "uncataloged" or catalog_core_id is not None:
                errors.append(f"{artifact_label} has stale uncataloged correlation")
        else:
            errors.append(f"{artifact_label} is absent from the exact release roster")

    cells = basis.get("catalog_cells")
    if not isinstance(cells, list):
        errors.append(f"{label} catalog_cells must be a list")
        cells = []
    expected_cell_keys = [
        (core_id, architecture)
        for core_id in sorted(catalog_core_ids)
        for architecture in ARCHITECTURES
    ]
    actual_cell_keys: list[tuple[object, object]] = []
    status_counts = {status: 0 for status in CATALOG_CELL_STATUSES}
    for offset, cell in enumerate(cells):
        cell_label = f"{label} catalog cell {offset}"
        if not isinstance(cell, Mapping):
            errors.append(f"{cell_label} must be an object")
            continue
        core_id = cell.get("core_id")
        architecture = cell.get("architecture")
        actual_cell_keys.append((core_id, architecture))
        artifact = canonical_index.get((str(core_id), str(architecture)))
        if artifact is None:
            expected_status = "not_shipped"
            expected_cell = {
                "core_id": core_id,
                "architecture": architecture,
                "status": expected_status,
            }
        else:
            expected_status = (
                "valid" if _artifact_architecture_is_valid(artifact) else "invalid"
            )
            expected_cell = {
                "core_id": core_id,
                "architecture": architecture,
                "status": expected_status,
                "artifact_path": artifact.get("path"),
                "artifact_sha256": artifact.get("sha256"),
            }
        if dict(cell) != expected_cell:
            errors.append(f"{cell_label} does not match its exact physical artifact")
        status = cell.get("status")
        if status in status_counts:
            status_counts[str(status)] += 1
        else:
            errors.append(f"{cell_label} has an unknown status")
    if actual_cell_keys != expected_cell_keys:
        errors.append(f"{label} catalog cell key order or coverage is not exact")

    summary = basis.get("summary")
    if not isinstance(summary, Mapping):
        errors.append(f"{label} summary must be an object")
    else:
        expected_summary = {
            "artifact_count": len(artifacts),
            "shipped_core_name_count": len(shipped_names),
            "catalog_core_count": len(catalog_core_ids),
            "catalog_cell_count": len(cells),
            "valid_catalog_cell_count": status_counts["valid"],
            "not_shipped_catalog_cell_count": status_counts["not_shipped"],
            "invalid_catalog_cell_count": status_counts["invalid"],
            "alias_artifact_count": alias_count,
            "uncataloged_artifact_count": uncataloged_count,
            "artifact_identity_set_sha256": spruce_branch_artifact_identity_set_sha256(
                artifacts
            ),
        }
        if dict(summary) != expected_summary:
            errors.append(f"{label} summary is stale")
    if require_reviewed_counts and len(artifacts) != 184:
        errors.append(f"{label} must contain all 184 shipped .so artifacts")
    if require_reviewed_counts and len(catalog_core_ids) == 98 and status_counts != {
        "valid": 174,
        "not_shipped": 21,
        "invalid": 1,
    }:
        errors.append(f"{label} catalog status counts differ from reviewed branch bytes")
    content_sha256 = basis.get("content_sha256")
    if not _is_sha256(content_sha256):
        errors.append(f"{label} content_sha256 is malformed")
    elif content_sha256 != spruce_branch_basis_content_sha256(basis):
        errors.append(f"{label} content_sha256 is stale")
    return errors


def _artifact_errors(
    artifact: Mapping[str, Any],
    label: str,
    *,
    core_trees: Mapping[str, Any],
) -> list[str]:
    errors = _exact_keys(
        artifact,
        {
            "path",
            "architecture",
            "shipped_core_id",
            "catalog_correlation",
            "git",
            "sha256",
            "elf",
            "architecture_validation",
        },
        label,
    )
    path = artifact.get("path")
    architecture = artifact.get("architecture")
    shipped_core_id = artifact.get("shipped_core_id")
    if architecture not in ARCHITECTURES:
        errors.append(f"{label} architecture is unknown")
    if not isinstance(shipped_core_id, str) or SHIPPED_CORE_ID_RE.fullmatch(shipped_core_id) is None:
        errors.append(f"{label} shipped_core_id is malformed")
    expected_tree = core_trees.get(str(architecture), {})
    expected_path = (
        f"{expected_tree.get('path')}/{shipped_core_id}_libretro.so"
        if expected_tree and isinstance(shipped_core_id, str)
        else None
    )
    if path != expected_path:
        errors.append(f"{label} path does not match its architecture and shipped id")
    if not _is_sha256(artifact.get("sha256")):
        errors.append(f"{label} sha256 is malformed")
    correlation = artifact.get("catalog_correlation")
    if not isinstance(correlation, Mapping):
        errors.append(f"{label} catalog_correlation must be an object")
    else:
        if set(correlation) != {"status", "catalog_core_id"}:
            errors.append(f"{label} catalog_correlation keys are not exact")
        if correlation.get("status") not in ARTIFACT_CORRELATION_STATUSES:
            errors.append(f"{label} catalog correlation status is unknown")
        correlated = correlation.get("catalog_core_id")
        if correlated is not None and (
            not isinstance(correlated, str) or CORE_ID_RE.fullmatch(correlated) is None
        ):
            errors.append(f"{label} catalog_core_id is malformed")
    git = artifact.get("git")
    if not isinstance(git, Mapping):
        errors.append(f"{label} git identity must be an object")
    else:
        if set(git) != {"mode", "object_type", "blob", "size"}:
            errors.append(f"{label} git identity keys are not exact")
        if git.get("mode") not in {"100644", "100755"}:
            errors.append(f"{label} Git mode is unsupported")
        if git.get("object_type") != "blob":
            errors.append(f"{label} Git object must be a blob")
        if not _is_sha1(git.get("blob")):
            errors.append(f"{label} Git blob id is malformed")
        if not isinstance(git.get("size"), int) or int(git.get("size", 0)) <= 0:
            errors.append(f"{label} Git blob size is invalid")
    elf = artifact.get("elf")
    if not isinstance(elf, Mapping):
        errors.append(f"{label} ELF identity must be an object")
    else:
        required = {
            "class",
            "data",
            "version",
            "osabi",
            "abi_version",
            "type",
            "machine",
            "flags",
            "float_abi",
        }
        if set(elf) != required:
            errors.append(f"{label} ELF identity keys are not exact")
        if elf.get("class") not in {"ELF32", "ELF64"}:
            errors.append(f"{label} ELF class is unsupported")
        if elf.get("data") not in {"little-endian", "big-endian"}:
            errors.append(f"{label} ELF data encoding is unsupported")
        if elf.get("version") != 1:
            errors.append(f"{label} ELF version is not current")
        if not isinstance(elf.get("osabi"), int) or not isinstance(
            elf.get("abi_version"), int
        ):
            errors.append(f"{label} ELF ABI identity is malformed")
        if elf.get("type") != "DYN":
            errors.append(f"{label} is not an ELF shared object")
        if not isinstance(elf.get("machine"), str) or not elf.get("machine"):
            errors.append(f"{label} ELF machine is malformed")
        if not isinstance(elf.get("flags"), str) or re.fullmatch(
            r"^0x[0-9a-f]{8}$", str(elf.get("flags"))
        ) is None:
            errors.append(f"{label} ELF flags are malformed")
        if elf.get("float_abi") not in {"hard", "soft", "not-applicable"}:
            errors.append(f"{label} ELF float ABI is malformed")
    expected_validation = (
        "valid" if _artifact_architecture_is_valid(artifact) else "invalid"
    )
    if artifact.get("architecture_validation") != expected_validation:
        errors.append(f"{label} architecture_validation is stale")
    return errors


def validate_spruce_branch_bases(
    document: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any],
    catalog_file_sha256: str,
    roster_file_sha256: str,
    roster: Mapping[str, Any] | None = None,
    release_roster: Mapping[str, Any] | None = None,
) -> None:
    """Raise when a Spruce branch artifact basis is incomplete or stale."""

    errors = spruce_branch_bases_errors(
        document,
        catalog=catalog,
        catalog_file_sha256=catalog_file_sha256,
        roster_file_sha256=roster_file_sha256,
        roster=roster,
        release_roster=release_roster,
    )
    if errors:
        raise PipelineError("invalid Spruce branch bases:\n- " + "\n- ".join(errors))
