"""Create-only catalogs for building an unpinned, frozen source candidate.

The canonical catalog and every tracked pin remain untouched.  A candidate
catalog is an ignored, one-core catalog derived from three immutable inputs:

* the current canonical recipe;
* one canonical remote-ref snapshot; and
* the exact object retained by the core's local bare mirror.

The normal E2E and promotion commands can consume the resulting catalog via
their existing global ``--catalog`` option.  Their recipe snapshots therefore
freeze this candidate manifest, including the source-snapshot and mirror
proofs below, without widening canonical or group-selected execution.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

from .errors import PipelineError
from .foundation import (
    atomic_create_json,
    decode_json_object,
    sha256_bytes,
)


SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SNAPSHOT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
FROZEN_REF_RE = re.compile(r"^refs/spruce-edge-refs/[0-9a-f]{64}$")
FROZEN_REF_PREFIX = "refs/spruce-edge-refs/"
# The first promoted non-source-aware candidates predate commit-specific retained
# refs.  Their frozen recipe snapshots authenticate this exact generator digest;
# no other generator may opt back into the reusable branch-ref projection.
LEGACY_REUSABLE_REF_GENERATOR_SHA256 = frozenset(
    {"e829d19f504284fd3db8b25de70731267596d323f64ef1f898fbbf2d2f0893b2"}
)
UTC_Z_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
MAX_SOURCE_DATE_EPOCH = 253402300799

SNAPSHOT_KEYS = frozenset(
    {
        "captured_at",
        "catalog",
        "content_sha256",
        "local_only",
        "publication",
        "resolution_window",
        "schema_version",
        "snapshot_id",
        "sources",
        "summary",
        "validation_scope",
    }
)
SOURCE_KEYS = frozenset(
    {
        "catalog_commit",
        "catalog_is_ancestor",
        "catalog_tree",
        "commit",
        "commit_epoch",
        "frozen_local_ref",
        "latest_semantics",
        "recipe_risk",
        "ref_kind",
        "ref_object",
        "ref_object_type",
        "requested_ref",
        "status",
        "top_level_gitlinks",
        "tree",
        "url",
    }
)
RECIPE_RISK_KEYS = frozenset(
    {
        "catalog_declared_submodules",
        "driver",
        "git_version",
        "overlays",
        "recursive_submodules",
        "source_aware_log_contract",
        "source_date_epoch",
        "submodule_fetch",
    }
)
SUMMARY_KEYS = frozenset(
    {
        "branch_core_count",
        "core_count",
        "diverged_core_count",
        "fast-forward_core_count",
        "latest_policy_gap_core_count",
        "latest_semantics_defined_core_count",
        "source_aware_log_contract_core_count",
        "tag_core_count",
        "top_level_gitlink_core_count",
        "top_level_gitlink_count",
        "unchanged_core_count",
        "unique_url_ref_count",
    }
)
CANDIDATE_VALIDATION_SCOPE = "immutable-edge-source-candidate-catalog-v1"
CATALOG_REBASE_VALIDATION_SCOPE = "core-source-snapshot-catalog-rebase-v1"
CATALOG_REBASE_KEYS = frozenset(
    {
        "schema_version",
        "validation_scope",
        "local_only",
        "publication",
        "core_id",
        "original_snapshot",
        "current_catalog",
        "source_tuple",
        "selection",
        "content_sha256",
    }
)

CatalogValidator = Callable[[dict], None]
EligibilityValidator = Callable[[dict, list[str]], None]
SourceAwareContractResolver = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class SourceCandidateContractProjection:
    """Authenticated canonical/execution identities for one source candidate."""

    core_id: str
    candidate_id: str
    canonical_commit: str
    canonical_tree: str
    candidate_commit: str
    candidate_tree: str
    canonical_spec_sha256: str
    execution_spec_sha256: str
    source_url: str = ""
    requested_ref: str = ""
    candidate_submodules: tuple[tuple[str, str], ...] = ()
    canonical_source_date_epoch: int | None = None


CandidateCatalogValidator = Callable[
    [dict, str, dict, SourceCandidateContractProjection | None], None
]
BuildRenderer = Callable[
    [str, str, dict, dict, dict, SourceCandidateContractProjection | None], str
]


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _content_sha256(document: Mapping[str, object]) -> str:
    material = {
        key: value for key, value in document.items() if key != "content_sha256"
    }
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def _relative_regular_file(path: Path, root: Path, label: str) -> tuple[Path, str]:
    """Resolve a regular file without accepting a symlinked spelling."""

    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"{label} allowed root does not exist") from exc
    if not root.is_dir():
        raise PipelineError(f"{label} allowed root is not a directory")
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise PipelineError(f"{label} must be contained by {root}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PipelineError(f"{label} must not traverse a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"{label} does not exist: {path}") from exc
    try:
        resolved_relative = resolved.relative_to(root)
    except ValueError as exc:
        raise PipelineError(f"{label} must be contained by {root}") from exc
    if path.absolute() != resolved:
        raise PipelineError(f"{label} path spelling is non-canonical")
    if not resolved.is_file():
        raise PipelineError(f"{label} must be a regular file")
    return resolved, resolved_relative.as_posix()


def _relative_directory(path: Path, root: Path, label: str) -> tuple[Path, str]:
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"{label} allowed root does not exist") from exc
    if not root.is_dir():
        raise PipelineError(f"{label} allowed root is not a directory")
    try:
        relative = path.absolute().relative_to(root)
    except ValueError as exc:
        raise PipelineError(f"{label} must be contained by {root}") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PipelineError(f"{label} must not traverse a symlink")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(f"{label} does not exist: {path}") from exc
    if not resolved.is_dir():
        raise PipelineError(f"{label} must be a directory")
    return resolved, resolved.relative_to(root).as_posix()


def _ensure_contained_create_directory(
    repository_root: Path,
    relative: Path,
    label: str,
) -> Path:
    """Create one contained directory chain without following parent symlinks."""

    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PipelineError(f"{label} path is unsafe")
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PipelineError(f"{label} must not traverse a parent symlink")
        try:
            current.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise PipelineError(f"cannot create {label}: {current}") from exc
        if current.is_symlink() or not current.is_dir():
            raise PipelineError(f"{label} parent must be a real directory")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(repository_root)
    except (OSError, ValueError) as exc:
        raise PipelineError(f"{label} escapes the repository") from exc
    if resolved != current:
        raise PipelineError(f"{label} must not traverse a parent symlink")
    return current


def _safe_gitlink_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return bool(
        not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def _validated_gitlinks(value: object, *, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PipelineError(f"{label} must be a list")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if (
            not isinstance(item, Mapping)
            or set(item) != {"commit", "path"}
            or not isinstance(item.get("commit"), str)
            or SHA1_RE.fullmatch(item["commit"]) is None
            or not _safe_gitlink_path(item.get("path"))
        ):
            raise PipelineError(f"{label} entry {index} is malformed")
        result.append({"commit": item["commit"], "path": item["path"]})
    if result != sorted(result, key=lambda item: item["path"]):
        raise PipelineError(f"{label} must be sorted by path")
    paths = [item["path"] for item in result]
    if len(paths) != len(set(paths)):
        raise PipelineError(f"{label} repeats a path")
    return result


def _read_snapshot(
    snapshot_path: Path, repository_root: Path
) -> tuple[dict, bytes, str]:
    allowed_root, _relative = _relative_directory(
        repository_root / ".local-e2e" / "source-probes",
        repository_root,
        "source-candidate snapshot root",
    )
    path, relative = _relative_regular_file(
        snapshot_path, allowed_root, "source-candidate snapshot"
    )
    raw = path.read_bytes()
    document = decode_json_object(raw, path)
    if raw != _canonical_json_bytes(document):
        raise PipelineError("source-candidate snapshot bytes are non-canonical")
    if set(document) != SNAPSHOT_KEYS:
        raise PipelineError("source-candidate snapshot fields are not exact")
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
        or document.get("local_only") is not True
        or document.get("publication") != "disabled"
        or document.get("validation_scope") != "remote-ref-resolution-only"
        or not isinstance(document.get("snapshot_id"), str)
        or SNAPSHOT_ID_RE.fullmatch(document["snapshot_id"]) is None
        or not isinstance(document.get("captured_at"), str)
        or UTC_Z_RE.fullmatch(document["captured_at"]) is None
        or not isinstance(document.get("content_sha256"), str)
        or SHA256_RE.fullmatch(document["content_sha256"]) is None
        or _content_sha256(document) != document["content_sha256"]
    ):
        raise PipelineError("source-candidate snapshot identity is invalid")
    catalog = document.get("catalog")
    window = document.get("resolution_window")
    summary = document.get("summary")
    sources = document.get("sources")
    if (
        not isinstance(catalog, Mapping)
        or set(catalog) != {"file_sha256", "path"}
        or catalog.get("path") != "manifests/core-builds.json"
        or not isinstance(catalog.get("file_sha256"), str)
        or SHA256_RE.fullmatch(catalog["file_sha256"]) is None
        or not isinstance(window, Mapping)
        or set(window) != {"first_fetch_mtime", "last_fetch_mtime"}
        or any(
            not isinstance(window.get(key), str)
            or UTC_Z_RE.fullmatch(window[key]) is None
            for key in window
        )
        or not isinstance(summary, Mapping)
        or set(summary) != SUMMARY_KEYS
        or any(type(value) is not int or value < 0 for value in summary.values())
        or not isinstance(sources, Mapping)
        or not sources
        or summary.get("core_count") != len(sources)
    ):
        raise PipelineError("source-candidate snapshot structure is invalid")
    return document, raw, relative


def _validated_source_entry(
    value: object,
    *,
    core_id: str,
    catalog_spec: Mapping[str, object],
    source_aware_log_contract: bool,
    candidate_retained_ref: bool = False,
) -> dict:
    if not isinstance(value, Mapping) or set(value) != SOURCE_KEYS:
        raise PipelineError(f"source-candidate snapshot entry is malformed: {core_id}")
    source = catalog_spec.get("source")
    build = catalog_spec.get("build")
    risk = value.get("recipe_risk")
    if not isinstance(source, Mapping) or not isinstance(build, Mapping):
        raise PipelineError(f"canonical recipe is malformed: {core_id}")
    if (
        value.get("url") != source.get("url")
        or value.get("requested_ref") != source.get("requested_ref")
        or value.get("catalog_commit") != source.get("commit")
        or value.get("catalog_tree") != source.get("tree")
    ):
        raise PipelineError(
            f"source-candidate snapshot baseline differs from the current recipe: {core_id}"
        )
    commit = value.get("commit")
    tree = value.get("tree")
    epoch = value.get("commit_epoch")
    frozen_ref = value.get("frozen_local_ref")
    requested_ref = value.get("requested_ref")
    if value.get("ref_kind") == "tag" or (
        isinstance(requested_ref, str) and requested_ref.startswith("refs/tags/")
    ):
        raise PipelineError(
            f"source-candidate tag policy is unsupported/deferred: {core_id}"
        )
    if value.get("status") == "diverged" or value.get("catalog_is_ancestor") is False:
        raise PipelineError(
            f"source-candidate divergence policy is unsupported/deferred: {core_id}"
        )
    canonical_frozen_ref = None
    if isinstance(requested_ref, str):
        frozen_material = requested_ref.encode()
        if candidate_retained_ref and isinstance(commit, str):
            frozen_material += b"\0" + commit.encode()
        canonical_frozen_ref = (
            FROZEN_REF_PREFIX + hashlib.sha256(frozen_material).hexdigest()
        )
    if (
        not isinstance(commit, str)
        or SHA1_RE.fullmatch(commit) is None
        or not isinstance(tree, str)
        or SHA1_RE.fullmatch(tree) is None
        or type(epoch) is not int
        or not 1 <= epoch <= MAX_SOURCE_DATE_EPOCH
        or not isinstance(frozen_ref, str)
        or FROZEN_REF_RE.fullmatch(frozen_ref) is None
        or value.get("ref_kind") != "branch"
        or value.get("ref_object_type") != "commit"
        or value.get("ref_object") != commit
        or value.get("latest_semantics") != "exact-branch-tip"
        or not isinstance(requested_ref, str)
        or not requested_ref.startswith("refs/heads/")
        or value.get("catalog_is_ancestor") is not True
        or value.get("status") not in {"unchanged", "fast-forward"}
        or (commit == source.get("commit")) != (value.get("status") == "unchanged")
    ):
        raise PipelineError(
            f"source-candidate snapshot does not identify an exact forward branch tip: {core_id}"
        )
    if frozen_ref != canonical_frozen_ref:
        raise PipelineError(
            f"source-candidate frozen ref is non-canonical: {core_id}"
        )
    gitlinks = _validated_gitlinks(
        value.get("top_level_gitlinks"),
        label=f"source-candidate {core_id} gitlinks",
    )
    overlays = build.get("overlays", {})
    overlay_count = (
        len(overlays)
        if isinstance(overlays, Mapping)
        and all(
            isinstance(target, str)
            and target
            and isinstance(items, list)
            and items
            and all(isinstance(item, Mapping) for item in items)
            for target, items in overlays.items()
        )
        else -1
    )
    declared_submodules = source.get("submodules", [])
    if (
        not isinstance(risk, Mapping)
        or set(risk) != RECIPE_RISK_KEYS
        or not isinstance(risk.get("driver"), str)
        or type(risk.get("catalog_declared_submodules")) is not int
        or risk.get("catalog_declared_submodules", -1) < 0
        or type(risk.get("overlays")) is not int
        or risk.get("overlays", -1) < 0
        or any(
            type(risk.get(key)) is not bool
            for key in (
                "git_version",
                "recursive_submodules",
                "source_aware_log_contract",
                "source_date_epoch",
                "submodule_fetch",
            )
        )
        or type(risk.get("source_aware_log_contract")) is not bool
    ):
        raise PipelineError(
            f"source-candidate recipe-risk projection is malformed: {core_id}"
        )
    if (
        risk.get("driver") != build.get("driver")
        or risk.get("catalog_declared_submodules")
        != (len(declared_submodules) if isinstance(declared_submodules, list) else -1)
        or risk.get("overlays") != overlay_count
        or risk.get("git_version") is not ("git_version" in build)
        or risk.get("source_date_epoch") is not ("source_date_epoch" in build)
        or risk.get("recursive_submodules")
        is not (build.get("recursive_submodules") is not False)
        or risk.get("submodule_fetch") is not (build.get("submodules") is not False)
        or risk.get("source_aware_log_contract") is not source_aware_log_contract
    ):
        raise PipelineError(
            f"source-candidate recipe-risk projection is stale: {core_id}"
        )
    result = copy.deepcopy(dict(value))
    result["top_level_gitlinks"] = gitlinks
    return result


def _candidate_uses_retained_ref(
    entry: Mapping[str, object],
    *,
    source_aware_log_contract: bool,
) -> bool:
    del source_aware_log_contract
    return bool(
        entry.get("status") in {"unchanged", "fast-forward"}
        and entry.get("catalog_is_ancestor") is True
        and entry.get("commit") is not None
    )


def _retained_candidate_entry(
    entry: Mapping[str, object],
    *,
    source_aware_log_contract: bool,
) -> dict:
    retained = copy.deepcopy(dict(entry))
    if _candidate_uses_retained_ref(
        retained,
        source_aware_log_contract=source_aware_log_contract,
    ):
        requested_ref = retained["requested_ref"]
        commit = retained["commit"]
        assert isinstance(requested_ref, str) and isinstance(commit, str)
        retained["frozen_local_ref"] = FROZEN_REF_PREFIX + hashlib.sha256(
            requested_ref.encode() + b"\0" + commit.encode()
        ).hexdigest()
    return retained


def _git(
    mirror: Path,
    args: list[str],
    *,
    binary: bool = False,
) -> str | bytes:
    command = [
        "git",
        "--no-replace-objects",
        "-c",
        "core.commitGraph=false",
        f"--git-dir={mirror}",
        *args,
    ]
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        process = subprocess.run(
            command,
            cwd=mirror.parent,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError(f"source-candidate mirror command failed: {exc}") from exc
    if process.returncode:
        stderr = process.stderr
        detail = (
            stderr.decode("utf-8", "replace").strip()
            if isinstance(stderr, bytes)
            else stderr.strip()
        )
        raise PipelineError(
            f"source-candidate mirror command failed: {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return process.stdout


def _mirror_gitlinks(mirror: Path, commit: str) -> list[dict[str, str]]:
    raw = _git(mirror, ["ls-tree", "-r", "-z", commit], binary=True)
    assert isinstance(raw, bytes)
    result: list[dict[str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, raw_path = record.split(b"\t", 1)
            _mode, object_type, raw_commit = header.split(b" ", 2)
            path = raw_path.decode("utf-8")
            object_commit = raw_commit.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise PipelineError("source-candidate mirror ls-tree output is malformed") from exc
        if object_type != b"commit":
            continue
        result.append({"commit": object_commit, "path": path})
    return _validated_gitlinks(result, label="source-candidate mirror gitlinks")


def _retain_candidate_ref(mirror: Path, entry: Mapping[str, object]) -> None:
    """Create one immutable commit-specific ref without replacing prior proof."""

    frozen_ref = entry.get("frozen_local_ref")
    commit = entry.get("commit")
    if (
        not isinstance(frozen_ref, str)
        or FROZEN_REF_RE.fullmatch(frozen_ref) is None
        or not isinstance(commit, str)
        or SHA1_RE.fullmatch(commit) is None
    ):
        raise PipelineError("source-candidate retained ref identity is malformed")
    current = _git(
        mirror,
        ["for-each-ref", "--format=%(objectname)", frozen_ref],
    )
    assert isinstance(current, str)
    current = current.strip()
    if current and current != commit:
        raise PipelineError("source-candidate retained ref is not immutable")
    if not current:
        _git(mirror, ["update-ref", frozen_ref, commit, "0" * 40])


def _verify_mirror(
    *,
    repository_root: Path,
    core_id: str,
    entry: Mapping[str, object],
) -> tuple[Path, str]:
    mirror_root = repository_root / ".local-e2e" / "source-repositories"
    mirror_root, _cache_relative = _relative_directory(
        mirror_root,
        repository_root,
        "source-candidate mirror cache",
    )
    mirror, relative = _relative_directory(
        mirror_root / f"{core_id}.git",
        mirror_root,
        "source-candidate mirror",
    )
    objects = mirror / "objects"
    config = mirror / "config"
    forbidden_graph_inputs = (
        mirror / "commondir",
        mirror / "gitdir",
        mirror / "shallow",
        mirror / "info" / "grafts",
        objects / "info" / "alternates",
        objects / "info" / "http-alternates",
    )
    if (
        objects.is_symlink()
        or not objects.is_dir()
        or config.is_symlink()
        or not config.is_file()
        or any(path.exists() or path.is_symlink() for path in forbidden_graph_inputs)
        or any(path.is_symlink() for path in mirror.rglob("*"))
    ):
        raise PipelineError(
            f"source-candidate mirror has forbidden graph inputs: {core_id}"
        )
    bare = _git(mirror, ["rev-parse", "--is-bare-repository"])
    common = _git(
        mirror,
        ["rev-parse", "--path-format=absolute", "--git-common-dir"],
    )
    shallow = _git(mirror, ["rev-parse", "--is-shallow-repository"])
    config_keys = _git(
        mirror,
        ["config", "--local", "--no-includes", "--name-only", "--list"],
    )
    remotes = _git(mirror, ["remote"])
    origin = _git(
        mirror,
        ["config", "--local", "--no-includes", "--get-all", "remote.origin.url"],
    )
    replacements = _git(mirror, ["for-each-ref", "--format=%(refname)", "refs/replace"])
    frozen = _git(mirror, ["show-ref", "--verify", "--hash", entry["frozen_local_ref"]])
    _git(mirror, ["cat-file", "-e", f"{entry['catalog_commit']}^{{commit}}"])
    _git(mirror, ["cat-file", "-e", f"{entry['commit']}^{{commit}}"])
    catalog_tree = _git(mirror, ["rev-parse", f"{entry['catalog_commit']}^{{tree}}"])
    tree = _git(mirror, ["rev-parse", f"{entry['commit']}^{{tree}}"])
    epoch = _git(mirror, ["show", "-s", "--format=%ct", entry["commit"]])
    _git(
        mirror,
        [
            "merge-base",
            "--is-ancestor",
            entry["catalog_commit"],
            entry["commit"],
        ],
    )
    assert all(
        isinstance(item, str)
        for item in (
            bare,
            common,
            shallow,
            config_keys,
            remotes,
            origin,
            replacements,
            frozen,
            catalog_tree,
            tree,
            epoch,
        )
    )
    try:
        common_path = Path(common.strip()).resolve(strict=True)
        exact_mirror = mirror.resolve(strict=True)
    except OSError as exc:
        raise PipelineError(
            f"source-candidate mirror common directory is invalid: {core_id}"
        ) from exc
    allowed_config_keys = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "remote.origin.url",
    }
    local_config_keys = config_keys.splitlines()
    if (
        bare.strip() != "true"
        or common_path != exact_mirror
        or shallow.strip() != "false"
        or set(local_config_keys) != allowed_config_keys
        or len(local_config_keys) != len(set(local_config_keys))
        or remotes.splitlines() != ["origin"]
        or origin.splitlines() != [entry["url"]]
        or replacements.strip()
        or frozen.strip() != entry["commit"]
        or catalog_tree.strip() != entry["catalog_tree"]
        or tree.strip() != entry["tree"]
        or epoch.strip() != str(entry["commit_epoch"])
        or _mirror_gitlinks(mirror, entry["commit"])
        != entry["top_level_gitlinks"]
    ):
        raise PipelineError(
            f"source-candidate mirror does not match the frozen snapshot: {core_id}"
        )
    return mirror, relative


def _git_blob(mirror: Path, commit: str, path: str, label: str) -> bytes:
    if not _safe_gitlink_path(path):
        raise PipelineError(f"{label} path is unsafe")
    try:
        raw = _git(mirror, ["show", f"{commit}:{path}"], binary=True)
    except PipelineError as exc:
        raise PipelineError(f"{label} is absent from the candidate tree") from exc
    assert isinstance(raw, bytes)
    return raw


def _verify_source_bound_files(
    *,
    spec: Mapping[str, object],
    mirror: Path,
    entry: Mapping[str, object],
) -> None:
    build = spec.get("build")
    if not isinstance(build, Mapping):
        raise PipelineError("source-candidate build recipe is malformed")
    overlays = build.get("overlays", {})
    seen: set[tuple[str, str]] = set()
    if isinstance(overlays, Mapping):
        for arch, items in sorted(overlays.items()):
            if not isinstance(items, list):
                raise PipelineError("source-candidate overlays are malformed")
            for index, overlay in enumerate(items):
                if not isinstance(overlay, Mapping):
                    raise PipelineError("source-candidate overlay is malformed")
                source_path = overlay.get("source_path")
                preimage = overlay.get("preimage_sha256")
                key = (str(source_path), str(preimage))
                if key in seen:
                    continue
                seen.add(key)
                if overlay.get("submodule_path"):
                    raise PipelineError(
                        "source-candidate overlay preimages inside submodules "
                        "require an explicit reviewed source contract"
                    )
                if (
                    not isinstance(source_path, str)
                    or not isinstance(preimage, str)
                    or SHA256_RE.fullmatch(preimage) is None
                    or sha256_bytes(
                        _git_blob(
                            mirror,
                            entry["commit"],
                            source_path,
                            f"source-candidate overlay {arch}/{index}",
                        )
                    )
                    != preimage
                ):
                    raise PipelineError(
                        f"source-candidate overlay preimage changed: {arch}/{index}"
                    )
    cargo = build.get("cargo")
    if isinstance(cargo, Mapping):
        subdir = cargo.get("subdir")
        lock_sha256 = cargo.get("lock_sha256")
        lock_path = "Cargo.lock" if subdir in (None, "") else f"{subdir}/Cargo.lock"
        if (
            not isinstance(lock_sha256, str)
            or SHA256_RE.fullmatch(lock_sha256) is None
            or sha256_bytes(
                _git_blob(
                    mirror,
                    entry["commit"],
                    lock_path,
                    "source-candidate Cargo.lock",
                )
            )
            != lock_sha256
        ):
            raise PipelineError("source-candidate Cargo.lock digest changed")


def core_spec_sha256(spec: Mapping[str, object]) -> str:
    return sha256_bytes(
        json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    )


def _load_canonical_catalog(
    *,
    repository_root: Path,
    catalog_path: Path,
    catalog_validator: CatalogValidator,
) -> tuple[Path, dict, bytes]:
    expected = repository_root / "manifests" / "core-builds.json"
    if catalog_path.absolute() != expected:
        raise PipelineError("source-candidate operation requires the canonical catalog")
    resolved, relative = _relative_regular_file(
        expected,
        repository_root,
        "source-candidate canonical catalog",
    )
    if relative != "manifests/core-builds.json":
        raise PipelineError("source-candidate canonical catalog path is invalid")
    raw = resolved.read_bytes()
    catalog = decode_json_object(raw, resolved)
    catalog_validator(catalog)
    if "source_candidate" in catalog:
        raise PipelineError("canonical catalog must not already be a source candidate")
    return resolved, catalog, raw


def _source_tuple(spec: Mapping[str, object]) -> dict[str, str]:
    source = spec.get("source")
    if not isinstance(source, Mapping):
        raise PipelineError("source-candidate canonical source is malformed")
    result = {
        key: source.get(key) for key in ("url", "requested_ref", "commit", "tree")
    }
    if (
        not isinstance(result["url"], str)
        or not isinstance(result["requested_ref"], str)
        or not isinstance(result["commit"], str)
        or SHA1_RE.fullmatch(result["commit"]) is None
        or not isinstance(result["tree"], str)
        or SHA1_RE.fullmatch(result["tree"]) is None
    ):
        raise PipelineError("source-candidate canonical source tuple is malformed")
    return result  # type: ignore[return-value]


def prepare_source_snapshot_catalog_rebase(
    *,
    repository_root: Path,
    catalog_path: Path,
    snapshot_path: Path,
    core_id: str,
    catalog_validator: CatalogValidator,
    source_aware_contract_resolver: SourceAwareContractResolver,
) -> dict[str, Any]:
    """Create a deterministic proof rebasing one stale snapshot to one recipe.

    The proof does not claim that the old full-catalog bytes are current.  It
    records both identities and proves only that this core's URL/ref/commit/tree
    baseline tuple is unchanged.  Candidate preparation still consumes the
    current recipe and independently verifies the frozen mirror object.
    """

    try:
        repository_root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError("source-candidate repository root is missing") from exc
    if not repository_root.is_dir():
        raise PipelineError("source-candidate repository root is not a directory")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        raise PipelineError("source-candidate core ID is malformed")
    if not callable(catalog_validator) or not callable(
        source_aware_contract_resolver
    ):
        raise TypeError("source-candidate catalog validators must be callable")

    _resolved_catalog, catalog, catalog_raw = _load_canonical_catalog(
        repository_root=repository_root,
        catalog_path=catalog_path,
        catalog_validator=catalog_validator,
    )
    if core_id not in catalog.get("cores", {}):
        raise PipelineError(f"source-candidate core is not cataloged: {core_id}")
    spec = catalog["cores"][core_id]
    snapshot, snapshot_raw, snapshot_relative_to_probe_root = _read_snapshot(
        snapshot_path, repository_root
    )
    current_catalog_sha256 = sha256_bytes(catalog_raw)
    if snapshot["catalog"]["file_sha256"] == current_catalog_sha256:
        raise PipelineError("source-candidate snapshot already binds the current catalog")
    entry = _validated_source_entry(
        snapshot["sources"].get(core_id),
        core_id=core_id,
        catalog_spec=spec,
        source_aware_log_contract=source_aware_contract_resolver(core_id),
    )
    _verify_mirror(
        repository_root=repository_root,
        core_id=core_id,
        entry=entry,
    )
    current_tuple = _source_tuple(spec)
    snapshot_tuple = {
        "url": entry["url"],
        "requested_ref": entry["requested_ref"],
        "commit": entry["catalog_commit"],
        "tree": entry["catalog_tree"],
    }
    if current_tuple != snapshot_tuple:
        raise PipelineError(
            f"source-candidate catalog rebase source tuple changed: {core_id}"
        )
    snapshot_relative = (
        Path(".local-e2e/source-probes") / snapshot_relative_to_probe_root
    ).as_posix()
    document: dict[str, Any] = {
        "schema_version": 1,
        "validation_scope": CATALOG_REBASE_VALIDATION_SCOPE,
        "local_only": True,
        "publication": "disabled",
        "core_id": core_id,
        "original_snapshot": {
            "path": snapshot_relative,
            "file_sha256": sha256_bytes(snapshot_raw),
            "content_sha256": snapshot["content_sha256"],
            "snapshot_id": snapshot["snapshot_id"],
            "catalog_file_sha256": snapshot["catalog"]["file_sha256"],
        },
        "current_catalog": {
            "path": "manifests/core-builds.json",
            "file_sha256": current_catalog_sha256,
            "core_spec_sha256": core_spec_sha256(spec),
        },
        "source_tuple": current_tuple,
        "selection": copy.deepcopy(entry),
    }
    document["content_sha256"] = _content_sha256(document)
    output_parent_relative = (
        Path(".local-e2e/source-probes/catalog-rebases")
        / snapshot["content_sha256"]
        / current_catalog_sha256
    )
    output_parent = _ensure_contained_create_directory(
        repository_root,
        output_parent_relative,
        "source-candidate catalog-rebase output",
    )
    output_path = output_parent / f"{core_id}.json"
    if output_path.exists() or output_path.is_symlink():
        raise PipelineError(
            f"refusing to reuse source-candidate catalog rebase: {output_path}"
        )
    atomic_create_json(output_path, document)
    raw = output_path.read_bytes()
    if raw != _canonical_json_bytes(document):
        raise AssertionError("created source-candidate rebase bytes changed")
    validated_rebase = _validate_catalog_rebase(
        path=output_path,
        repository_root=repository_root,
        snapshot=snapshot,
        snapshot_raw=snapshot_raw,
        snapshot_relative=snapshot_relative,
        catalog_raw=catalog_raw,
        core_id=core_id,
        spec=spec,
        entry=entry,
    )
    return {
        "status": "prepared",
        "local_only": True,
        "publication": "disabled",
        "validation_scope": CATALOG_REBASE_VALIDATION_SCOPE,
        "core_id": core_id,
        "catalog_rebase": validated_rebase,
        "source_tuple": current_tuple,
    }


def _validate_catalog_rebase(
    *,
    path: Path,
    repository_root: Path,
    snapshot: Mapping[str, object],
    snapshot_raw: bytes,
    snapshot_relative: str,
    catalog_raw: bytes,
    core_id: str,
    spec: Mapping[str, object],
    entry: Mapping[str, object],
) -> dict[str, str]:
    allowed_root, _relative = _relative_directory(
        repository_root / ".local-e2e" / "source-probes" / "catalog-rebases",
        repository_root,
        "source-candidate catalog-rebase root",
    )
    resolved, relative_to_rebase_root = _relative_regular_file(
        path, allowed_root, "source-candidate catalog rebase"
    )
    raw = resolved.read_bytes()
    document = decode_json_object(raw, resolved)
    if raw != _canonical_json_bytes(document):
        raise PipelineError("source-candidate catalog rebase bytes are non-canonical")
    if (
        set(document) != CATALOG_REBASE_KEYS
        or document.get("schema_version") != 1
        or document.get("validation_scope") != CATALOG_REBASE_VALIDATION_SCOPE
        or document.get("local_only") is not True
        or document.get("publication") != "disabled"
        or document.get("core_id") != core_id
        or document.get("content_sha256") != _content_sha256(document)
    ):
        raise PipelineError("source-candidate catalog rebase identity is invalid")
    expected_original = {
        "path": snapshot_relative,
        "file_sha256": sha256_bytes(snapshot_raw),
        "content_sha256": snapshot["content_sha256"],
        "snapshot_id": snapshot["snapshot_id"],
        "catalog_file_sha256": snapshot["catalog"]["file_sha256"],
    }
    expected_current = {
        "path": "manifests/core-builds.json",
        "file_sha256": sha256_bytes(catalog_raw),
        "core_spec_sha256": core_spec_sha256(spec),
    }
    expected_tuple = _source_tuple(spec)
    if (
        document.get("original_snapshot") != expected_original
        or document.get("current_catalog") != expected_current
        or document.get("source_tuple") != expected_tuple
        or document.get("selection") != entry
    ):
        raise PipelineError("source-candidate catalog rebase is stale")
    expected_path = (
        Path(snapshot["content_sha256"])
        / sha256_bytes(catalog_raw)
        / f"{core_id}.json"
    ).as_posix()
    if relative_to_rebase_root != expected_path:
        raise PipelineError("source-candidate catalog rebase path is non-canonical")
    return {
        "path": (
            Path(".local-e2e/source-probes/catalog-rebases")
            / relative_to_rebase_root
        ).as_posix(),
        "file_sha256": sha256_bytes(raw),
        "content_sha256": document["content_sha256"],
    }


def _candidate_execution_spec(
    base_spec: Mapping[str, object],
    entry: Mapping[str, object],
) -> tuple[dict, str]:
    execution_spec = copy.deepcopy(dict(base_spec))
    execution_source = execution_spec.get("source")
    execution_build = execution_spec.get("build")
    if not isinstance(execution_source, dict) or not isinstance(execution_build, dict):
        raise PipelineError("source-candidate canonical recipe is malformed")
    execution_source["commit"] = entry["commit"]
    execution_source["tree"] = entry["tree"]
    if "submodules" in execution_source:
        execution_source["submodules"] = copy.deepcopy(entry["top_level_gitlinks"])
    epoch_derivation = "absent"
    if "source_date_epoch" in execution_build:
        execution_build["source_date_epoch"] = entry["commit_epoch"]
        epoch_derivation = "candidate-commit-epoch"
    return execution_spec, epoch_derivation


def source_candidate_execution_spec(
    base_spec: Mapping[str, object],
    selection: Mapping[str, object],
) -> dict:
    """Reconstruct the only execution spec admitted by candidate provenance."""

    execution_spec, _epoch_derivation = _candidate_execution_spec(
        base_spec, selection
    )
    return execution_spec


def validated_source_candidate_contract_projection(
    provenance: object,
    *,
    core_id: str,
    canonical_spec: Mapping[str, object],
    execution_spec: Mapping[str, object],
    source_aware_log_contract: bool,
) -> SourceCandidateContractProjection:
    """Bind a source-aware relaxation to exact authenticated v1 provenance."""

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
    if not isinstance(provenance, Mapping) or frozenset(provenance) not in {
        frozenset(required),
        frozenset(required | {"catalog_rebase"}),
    }:
        raise PipelineError("source-candidate contract provenance fields are not exact")
    candidate_id = provenance.get("candidate_id")
    material = copy.deepcopy(dict(provenance))
    material.pop("candidate_id", None)
    if (
        provenance.get("schema_version") != 1
        or provenance.get("validation_scope") != CANDIDATE_VALIDATION_SCOPE
        or provenance.get("local_only") is not True
        or provenance.get("publication") != "disabled"
        or provenance.get("core_id") != core_id
        or not isinstance(candidate_id, str)
        or SHA256_RE.fullmatch(candidate_id) is None
        or candidate_id != _content_sha256(material)
    ):
        raise PipelineError("source-candidate contract provenance identity is invalid")
    base_catalog = provenance.get("base_catalog")
    execution = provenance.get("execution")
    if (
        not isinstance(base_catalog, Mapping)
        or set(base_catalog) != {"path", "file_sha256", "core_spec_sha256"}
        or base_catalog.get("path") != "manifests/core-builds.json"
        or not isinstance(execution, Mapping)
        or set(execution)
        != {"core_spec_sha256", "source_date_epoch_derivation"}
    ):
        raise PipelineError("source-candidate contract spec binding is invalid")
    selection = _validated_source_entry(
        provenance.get("selection"),
        core_id=core_id,
        catalog_spec=canonical_spec,
        source_aware_log_contract=source_aware_log_contract,
        candidate_retained_ref=True,
    )
    risk = selection["recipe_risk"]
    if (
        source_aware_log_contract is not True
        or selection.get("status") != "fast-forward"
        or selection.get("commit") == selection.get("catalog_commit")
        or risk.get("source_aware_log_contract") is not True
    ):
        raise PipelineError(
            "source-candidate contract projection requires a registered "
            "source-aware fast-forward"
        )
    if risk.get("git_version") is not False:
        raise PipelineError(
            "source-candidate explicit git-version projection is unsupported/deferred"
        )
    expected_execution, epoch_derivation = _candidate_execution_spec(
        canonical_spec, selection
    )
    if dict(execution_spec) != expected_execution:
        raise PipelineError("source-candidate execution spec projection is invalid")
    canonical_digest = core_spec_sha256(canonical_spec)
    execution_digest = core_spec_sha256(execution_spec)
    if (
        base_catalog.get("core_spec_sha256") != canonical_digest
        or execution.get("core_spec_sha256") != execution_digest
        or execution.get("source_date_epoch_derivation") != epoch_derivation
    ):
        raise PipelineError("source-candidate contract spec digest is invalid")
    return SourceCandidateContractProjection(
        core_id=core_id,
        candidate_id=candidate_id,
        canonical_commit=selection["catalog_commit"],
        canonical_tree=selection["catalog_tree"],
        candidate_commit=selection["commit"],
        candidate_tree=selection["tree"],
        canonical_spec_sha256=canonical_digest,
        execution_spec_sha256=execution_digest,
        source_url=selection["url"],
        requested_ref=selection["requested_ref"],
        candidate_submodules=tuple(
            (item["path"], item["commit"])
            for item in selection["top_level_gitlinks"]
        ),
        canonical_source_date_epoch=canonical_spec.get("build", {}).get(
            "source_date_epoch"
        ),
    )


def _generator_reference(repository_root: Path) -> dict[str, str]:
    try:
        generator_path = Path(__file__).resolve(strict=True)
        generator_relative = generator_path.relative_to(repository_root).as_posix()
    except (OSError, ValueError) as exc:
        raise PipelineError("source-candidate generator is outside the repository") from exc
    if generator_relative != "scripts/core_pipeline_lib/source_candidate.py":
        raise PipelineError("source-candidate generator path is non-canonical")
    return {
        "path": generator_relative,
        "sha256": sha256_bytes(generator_path.read_bytes()),
    }


def _candidate_provenance(
    *,
    repository_root: Path,
    core_id: str,
    snapshot: Mapping[str, object],
    snapshot_raw: bytes,
    snapshot_relative: str,
    catalog_raw: bytes,
    base_spec: Mapping[str, object],
    entry: Mapping[str, object],
    execution_spec: Mapping[str, object],
    epoch_derivation: str,
    mirror_relative_to_cache: str,
    catalog_rebase: Mapping[str, str] | None,
) -> dict[str, Any]:
    provenance: dict[str, Any] = {
        "schema_version": 1,
        "validation_scope": CANDIDATE_VALIDATION_SCOPE,
        "local_only": True,
        "publication": "disabled",
        "core_id": core_id,
        "generator": _generator_reference(repository_root),
        "snapshot": {
            "path": snapshot_relative,
            "file_sha256": sha256_bytes(snapshot_raw),
            "content_sha256": snapshot["content_sha256"],
            "snapshot_id": snapshot["snapshot_id"],
            "captured_at": snapshot["captured_at"],
            "catalog": copy.deepcopy(snapshot["catalog"]),
        },
        "base_catalog": {
            "path": "manifests/core-builds.json",
            "file_sha256": sha256_bytes(catalog_raw),
            "core_spec_sha256": core_spec_sha256(base_spec),
        },
        "mirror": {
            "path": (
                Path(".local-e2e/source-repositories") / mirror_relative_to_cache
            ).as_posix(),
            "origin_url": entry["url"],
            "frozen_local_ref": entry["frozen_local_ref"],
        },
        "selection": copy.deepcopy(dict(entry)),
        "execution": {
            "core_spec_sha256": core_spec_sha256(execution_spec),
            "source_date_epoch_derivation": epoch_derivation,
        },
    }
    if catalog_rebase is not None:
        provenance["catalog_rebase"] = copy.deepcopy(dict(catalog_rebase))
    provenance["candidate_id"] = _content_sha256(provenance)
    return provenance


def _validate_candidate_callbacks(
    *,
    catalog_validator: CatalogValidator,
    candidate_catalog_validator: CandidateCatalogValidator,
    eligibility_validator: EligibilityValidator,
    build_renderer: BuildRenderer,
    source_aware_contract_resolver: SourceAwareContractResolver,
) -> None:
    if not all(
        callable(callback)
        for callback in (
            catalog_validator,
            candidate_catalog_validator,
            eligibility_validator,
            build_renderer,
            source_aware_contract_resolver,
        )
    ):
        raise TypeError("source-candidate validators and renderer must be callable")


def _candidate_report(
    *,
    status: str,
    repository_root: Path,
    catalog_path: Path,
    catalog_raw: bytes,
    provenance: Mapping[str, object],
    entry: Mapping[str, object],
    execution_spec: Mapping[str, object],
    epoch_derivation: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "local_only": True,
        "publication": "disabled",
        "validation_scope": CANDIDATE_VALIDATION_SCOPE,
        "core_id": provenance["core_id"],
        "candidate_id": provenance["candidate_id"],
        "catalog": {
            "path": catalog_path.relative_to(repository_root).as_posix(),
            "file_sha256": sha256_bytes(catalog_raw),
        },
        "source": {
            "url": entry["url"],
            "requested_ref": entry["requested_ref"],
            "commit": entry["commit"],
            "tree": entry["tree"],
            "submodules": copy.deepcopy(entry["top_level_gitlinks"]),
        },
        "targets": copy.deepcopy(execution_spec["targets"]),
        "source_date_epoch_derivation": epoch_derivation,
    }


def _repository_reference_path(
    *,
    repository_root: Path,
    value: object,
    prefix: str,
    label: str,
) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise PipelineError(f"{label} path is malformed")
    relative = Path(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
        or not value.startswith(prefix)
    ):
        raise PipelineError(f"{label} path is non-canonical")
    return repository_root / relative


def validate_source_candidate_catalog(
    *,
    repository_root: Path,
    canonical_catalog_path: Path,
    candidate_catalog_path: Path,
    catalog_validator: CatalogValidator,
    candidate_catalog_validator: CandidateCatalogValidator,
    eligibility_validator: EligibilityValidator,
    build_renderer: BuildRenderer,
    source_aware_contract_resolver: SourceAwareContractResolver,
) -> dict[str, Any]:
    """Deeply revalidate one ignored source-candidate catalog.

    No provenance field is trusted as an independent input.  The candidate's
    canonical snapshot/rebase paths are reopened, the current canonical recipe
    is rebound, and the retained mirror graph and source-bound files are proved
    again before an exact candidate document and path are reconstructed.
    """

    try:
        repository_root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError("source-candidate repository root is missing") from exc
    if not repository_root.is_dir():
        raise PipelineError("source-candidate repository root is not a directory")
    _validate_candidate_callbacks(
        catalog_validator=catalog_validator,
        candidate_catalog_validator=candidate_catalog_validator,
        eligibility_validator=eligibility_validator,
        build_renderer=build_renderer,
        source_aware_contract_resolver=source_aware_contract_resolver,
    )
    _canonical_path, canonical, canonical_raw = _load_canonical_catalog(
        repository_root=repository_root,
        catalog_path=canonical_catalog_path,
        catalog_validator=catalog_validator,
    )

    candidate_root, _relative = _relative_directory(
        repository_root / ".local-e2e" / "source-candidates",
        repository_root,
        "source-candidate catalog root",
    )
    candidate_path, _candidate_relative = _relative_regular_file(
        candidate_catalog_path,
        candidate_root,
        "source-candidate catalog",
    )
    candidate_raw = candidate_path.read_bytes()
    candidate = decode_json_object(candidate_raw, candidate_path)
    if candidate_raw != _canonical_json_bytes(candidate):
        raise PipelineError("source-candidate catalog bytes are non-canonical")
    provenance = candidate.get("source_candidate")
    if not isinstance(provenance, Mapping):
        raise PipelineError("source-candidate catalog provenance is missing")
    core_id = provenance.get("core_id")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        raise PipelineError("source-candidate catalog core ID is malformed")
    candidate_cores = candidate.get("cores")
    canonical_cores = canonical.get("cores")
    if not isinstance(candidate_cores, Mapping) or set(candidate_cores) != {core_id}:
        raise PipelineError("source-candidate catalog must contain exactly its core")
    if not isinstance(canonical_cores, Mapping) or core_id not in canonical_cores:
        raise PipelineError(f"source-candidate core is not cataloged: {core_id}")
    base_spec = copy.deepcopy(canonical_cores[core_id])

    snapshot_reference = provenance.get("snapshot")
    if not isinstance(snapshot_reference, Mapping):
        raise PipelineError("source-candidate snapshot provenance is malformed")
    snapshot_path = _repository_reference_path(
        repository_root=repository_root,
        value=snapshot_reference.get("path"),
        prefix=".local-e2e/source-probes/",
        label="source-candidate snapshot provenance",
    )
    snapshot, snapshot_raw, snapshot_relative_to_probe_root = _read_snapshot(
        snapshot_path,
        repository_root,
    )
    snapshot_relative = (
        Path(".local-e2e/source-probes") / snapshot_relative_to_probe_root
    ).as_posix()
    stale_snapshot = (
        snapshot["catalog"]["file_sha256"] != sha256_bytes(canonical_raw)
    )
    source_aware_log_contract = source_aware_contract_resolver(core_id)
    snapshot_entry = _validated_source_entry(
        snapshot["sources"].get(core_id),
        core_id=core_id,
        catalog_spec=base_spec,
        source_aware_log_contract=source_aware_log_contract,
    )

    raw_rebase = provenance.get("catalog_rebase")
    if stale_snapshot:
        if not isinstance(raw_rebase, Mapping):
            raise PipelineError(
                "source-candidate catalog lacks its required stale-snapshot rebase"
            )
        rebase_path = _repository_reference_path(
            repository_root=repository_root,
            value=raw_rebase.get("path"),
            prefix=".local-e2e/source-probes/catalog-rebases/",
            label="source-candidate catalog rebase provenance",
        )
        catalog_rebase = _validate_catalog_rebase(
            path=rebase_path,
            repository_root=repository_root,
            snapshot=snapshot,
            snapshot_raw=snapshot_raw,
            snapshot_relative=snapshot_relative,
            catalog_raw=canonical_raw,
            core_id=core_id,
            spec=base_spec,
            entry=snapshot_entry,
        )
    else:
        if raw_rebase is not None:
            raise PipelineError(
                "source-candidate catalog has a rebase for a current snapshot"
            )
        catalog_rebase = None

    entry = _retained_candidate_entry(
        snapshot_entry,
        source_aware_log_contract=source_aware_log_contract,
    )
    if provenance.get("selection") != entry:
        raise PipelineError(
            "source-candidate selection differs from its retained snapshot"
        )
    mirror, mirror_relative_to_cache = _verify_mirror(
        repository_root=repository_root,
        core_id=core_id,
        entry=entry,
    )
    _verify_source_bound_files(spec=base_spec, mirror=mirror, entry=entry)
    execution_spec, epoch_derivation = _candidate_execution_spec(base_spec, entry)
    expected_provenance = _candidate_provenance(
        repository_root=repository_root,
        core_id=core_id,
        snapshot=snapshot,
        snapshot_raw=snapshot_raw,
        snapshot_relative=snapshot_relative,
        catalog_raw=canonical_raw,
        base_spec=base_spec,
        entry=entry,
        execution_spec=execution_spec,
        epoch_derivation=epoch_derivation,
        mirror_relative_to_cache=mirror_relative_to_cache,
        catalog_rebase=catalog_rebase,
    )
    expected_candidate = {
        key: copy.deepcopy(value)
        for key, value in canonical.items()
        if key != "cores"
    }
    expected_candidate["cores"] = {core_id: execution_spec}
    expected_candidate["source_candidate"] = expected_provenance
    if candidate != expected_candidate:
        raise PipelineError(
            "source-candidate catalog differs from its current exact provenance"
        )
    expected_path = (
        repository_root
        / ".local-e2e"
        / "source-candidates"
        / snapshot["content_sha256"]
        / core_id
        / expected_provenance["candidate_id"]
        / "core-builds.json"
    )
    if candidate_path != expected_path:
        raise PipelineError("source-candidate catalog path is non-canonical")

    projection = (
        validated_source_candidate_contract_projection(
            expected_provenance,
            core_id=core_id,
            canonical_spec=base_spec,
            execution_spec=execution_spec,
            source_aware_log_contract=source_aware_log_contract,
        )
        if source_aware_log_contract
        and entry["status"] == "fast-forward"
        and entry["commit"] != entry["catalog_commit"]
        else None
    )
    candidate_catalog_validator(candidate, core_id, base_spec, projection)

    eligibility_validator(candidate, [core_id])
    targets = execution_spec.get("targets")
    if not isinstance(targets, list) or not targets:
        raise PipelineError("source-candidate execution targets are malformed")
    for arch in targets:
        rendered = build_renderer(
            core_id,
            arch,
            execution_spec,
            candidate["resolver"],
            base_spec,
            projection,
        )
        if not isinstance(rendered, str) or not rendered.strip():
            raise PipelineError(
                f"source-candidate build contract cannot render: {core_id}/{arch}"
            )
    return _candidate_report(
        status="valid",
        repository_root=repository_root,
        catalog_path=candidate_path,
        catalog_raw=candidate_raw,
        provenance=expected_provenance,
        entry=entry,
        execution_spec=execution_spec,
        epoch_derivation=epoch_derivation,
    )


def validate_promoted_source_candidate_contract(
    *,
    repository_root: Path,
    canonical_catalog_path: Path,
    candidate_catalog: Mapping[str, object],
    catalog_validator: CatalogValidator,
    source_aware_contract_resolver: SourceAwareContractResolver,
) -> SourceCandidateContractProjection | None:
    """Revalidate promoted candidate bytes without trusting the live generator.

    The immutable recipe snapshot supplies the historical candidate catalog and
    generator digest.  This validator reopens the referenced source snapshot,
    optional rebase, and retained mirror, then reconstructs every other v1
    provenance byte against the still-current canonical recipe.
    """

    try:
        repository_root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError("promoted source-candidate repository is missing") from exc
    _canonical_path, canonical, _canonical_raw = _load_canonical_catalog(
        repository_root=repository_root,
        catalog_path=canonical_catalog_path,
        catalog_validator=catalog_validator,
    )
    provenance = candidate_catalog.get("source_candidate")
    if not isinstance(provenance, Mapping):
        raise PipelineError("promoted source-candidate provenance is missing")
    core_id = provenance.get("core_id")
    canonical_cores = canonical.get("cores")
    candidate_cores = candidate_catalog.get("cores")
    if (
        not isinstance(core_id, str)
        or CORE_ID_RE.fullmatch(core_id) is None
        or not isinstance(canonical_cores, Mapping)
        or core_id not in canonical_cores
        or not isinstance(candidate_cores, Mapping)
        or set(candidate_cores) != {core_id}
    ):
        raise PipelineError("promoted source-candidate core set is invalid")
    # v1 provenance authenticates the selected core recipe and source graph,
    # but it does not carry the historical base catalog's remaining bytes.
    # Fail closed by requiring every non-core execution input/policy byte to
    # equal the currently authenticated canonical catalog.  Other canonical
    # core entries may evolve independently because the candidate is an exact
    # one-core projection.
    canonical_non_core = {
        key: value for key, value in canonical.items() if key != "cores"
    }
    candidate_non_core = {
        key: value
        for key, value in candidate_catalog.items()
        if key not in {"cores", "source_candidate"}
    }
    if candidate_non_core != canonical_non_core:
        raise PipelineError(
            "promoted source-candidate non-core catalog bytes differ from "
            "the canonical catalog"
        )
    base_spec = copy.deepcopy(canonical_cores[core_id])
    snapshot_reference = provenance.get("snapshot")
    if not isinstance(snapshot_reference, Mapping):
        raise PipelineError("promoted source-candidate snapshot is malformed")
    snapshot_path = _repository_reference_path(
        repository_root=repository_root,
        value=snapshot_reference.get("path"),
        prefix=".local-e2e/source-probes/",
        label="promoted source-candidate snapshot",
    )
    snapshot, snapshot_raw, snapshot_relative_to_probe_root = _read_snapshot(
        snapshot_path,
        repository_root,
    )
    snapshot_relative = (
        Path(".local-e2e/source-probes") / snapshot_relative_to_probe_root
    ).as_posix()
    source_aware = source_aware_contract_resolver(core_id)
    snapshot_entry = _validated_source_entry(
        snapshot["sources"].get(core_id),
        core_id=core_id,
        catalog_spec=base_spec,
        source_aware_log_contract=source_aware,
    )
    retained_entry = _retained_candidate_entry(
        snapshot_entry,
        source_aware_log_contract=source_aware,
    )
    selection = provenance.get("selection")
    generator = provenance.get("generator")
    legacy_reusable_ref = bool(
        isinstance(generator, Mapping)
        and generator.get("sha256") in LEGACY_REUSABLE_REF_GENERATOR_SHA256
        and selection == snapshot_entry
    )
    if selection == retained_entry:
        entry = retained_entry
    elif legacy_reusable_ref:
        entry = snapshot_entry
    else:
        raise PipelineError(
            "promoted source-candidate selection differs from its frozen snapshot"
        )
    base_catalog = provenance.get("base_catalog")
    if (
        not isinstance(base_catalog, Mapping)
        or set(base_catalog) != {"path", "file_sha256", "core_spec_sha256"}
        or base_catalog.get("path") != "manifests/core-builds.json"
        or not isinstance(base_catalog.get("file_sha256"), str)
        or SHA256_RE.fullmatch(base_catalog["file_sha256"]) is None
        or base_catalog.get("core_spec_sha256") != core_spec_sha256(base_spec)
    ):
        raise PipelineError("promoted source-candidate base recipe is invalid")
    expected_snapshot_reference = {
        "path": snapshot_relative,
        "file_sha256": sha256_bytes(snapshot_raw),
        "content_sha256": snapshot["content_sha256"],
        "snapshot_id": snapshot["snapshot_id"],
        "captured_at": snapshot["captured_at"],
        "catalog": copy.deepcopy(snapshot["catalog"]),
    }
    if snapshot_reference != expected_snapshot_reference:
        raise PipelineError("promoted source-candidate snapshot binding is stale")
    stale_snapshot = (
        snapshot["catalog"]["file_sha256"] != base_catalog["file_sha256"]
    )
    raw_rebase = provenance.get("catalog_rebase")
    if stale_snapshot:
        if not isinstance(raw_rebase, Mapping):
            raise PipelineError(
                "promoted source-candidate lacks its required catalog rebase"
            )
        rebase_path = _repository_reference_path(
            repository_root=repository_root,
            value=raw_rebase.get("path"),
            prefix=".local-e2e/source-probes/catalog-rebases/",
            label="promoted source-candidate catalog rebase",
        )
        rebase_root, _ = _relative_directory(
            repository_root / ".local-e2e" / "source-probes" / "catalog-rebases",
            repository_root,
            "promoted source-candidate catalog rebase root",
        )
        resolved_rebase, relative_rebase = _relative_regular_file(
            rebase_path,
            rebase_root,
            "promoted source-candidate catalog rebase",
        )
        rebase_raw = resolved_rebase.read_bytes()
        rebase_document = decode_json_object(rebase_raw, resolved_rebase)
        expected_rebase_path = (
            Path(snapshot["content_sha256"])
            / base_catalog["file_sha256"]
            / f"{core_id}.json"
        ).as_posix()
        if (
            rebase_raw != _canonical_json_bytes(rebase_document)
            or set(rebase_document) != CATALOG_REBASE_KEYS
            or rebase_document.get("schema_version") != 1
            or rebase_document.get("validation_scope")
            != CATALOG_REBASE_VALIDATION_SCOPE
            or rebase_document.get("local_only") is not True
            or rebase_document.get("publication") != "disabled"
            or rebase_document.get("core_id") != core_id
            or rebase_document.get("content_sha256")
            != _content_sha256(rebase_document)
            or relative_rebase != expected_rebase_path
            or rebase_document.get("original_snapshot")
            != {
                "path": snapshot_relative,
                "file_sha256": sha256_bytes(snapshot_raw),
                "content_sha256": snapshot["content_sha256"],
                "snapshot_id": snapshot["snapshot_id"],
                "catalog_file_sha256": snapshot["catalog"]["file_sha256"],
            }
            or rebase_document.get("current_catalog")
            != {
                "path": "manifests/core-builds.json",
                "file_sha256": base_catalog["file_sha256"],
                "core_spec_sha256": core_spec_sha256(base_spec),
            }
            or rebase_document.get("source_tuple") != _source_tuple(base_spec)
            or rebase_document.get("selection") != snapshot_entry
        ):
            raise PipelineError(
                "promoted source-candidate catalog rebase binding is invalid"
            )
        catalog_rebase = {
            "path": (
                Path(".local-e2e/source-probes/catalog-rebases")
                / relative_rebase
            ).as_posix(),
            "file_sha256": sha256_bytes(rebase_raw),
            "content_sha256": rebase_document["content_sha256"],
        }
        if raw_rebase != catalog_rebase:
            raise PipelineError(
                "promoted source-candidate catalog rebase reference is stale"
            )
    else:
        if raw_rebase is not None:
            raise PipelineError(
                "promoted source-candidate has a rebase for a current snapshot"
            )
        catalog_rebase = None
    mirror, mirror_relative_to_cache = _verify_mirror(
        repository_root=repository_root,
        core_id=core_id,
        entry=entry,
    )
    _verify_source_bound_files(spec=base_spec, mirror=mirror, entry=entry)
    execution_spec, epoch_derivation = _candidate_execution_spec(base_spec, entry)
    mirror_reference = provenance.get("mirror")
    if mirror_reference != {
        "path": (
            Path(".local-e2e/source-repositories") / mirror_relative_to_cache
        ).as_posix(),
        "origin_url": entry["url"],
        "frozen_local_ref": entry["frozen_local_ref"],
    }:
        raise PipelineError("promoted source-candidate mirror binding is stale")
    generator = provenance.get("generator")
    if (
        not isinstance(generator, Mapping)
        or set(generator) != {"path", "sha256"}
        or generator.get("path")
        != "scripts/core_pipeline_lib/source_candidate.py"
        or not isinstance(generator.get("sha256"), str)
        or SHA256_RE.fullmatch(generator["sha256"]) is None
    ):
        raise PipelineError("promoted source-candidate generator is invalid")
    if candidate_cores[core_id] != execution_spec:
        raise PipelineError(
            "promoted source-candidate execution spec is invalid"
        )
    required_provenance = {
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
    candidate_id = provenance.get("candidate_id")
    identity_material = copy.deepcopy(dict(provenance))
    identity_material.pop("candidate_id", None)
    if (
        frozenset(provenance)
        not in {
            frozenset(required_provenance),
            frozenset(required_provenance | {"catalog_rebase"}),
        }
        or provenance.get("schema_version") != 1
        or provenance.get("validation_scope") != CANDIDATE_VALIDATION_SCOPE
        or provenance.get("local_only") is not True
        or provenance.get("publication") != "disabled"
        or provenance.get("core_id") != core_id
        or provenance.get("execution")
        != {
            "core_spec_sha256": core_spec_sha256(execution_spec),
            "source_date_epoch_derivation": epoch_derivation,
        }
        or not isinstance(candidate_id, str)
        or SHA256_RE.fullmatch(candidate_id) is None
        or candidate_id != _content_sha256(identity_material)
    ):
        raise PipelineError("promoted source-candidate provenance identity is invalid")
    if (
        not source_aware
        or entry["status"] != "fast-forward"
        or entry["commit"] == entry["catalog_commit"]
    ):
        return None
    return validated_source_candidate_contract_projection(
        provenance,
        core_id=core_id,
        canonical_spec=base_spec,
        execution_spec=execution_spec,
        source_aware_log_contract=source_aware,
    )


def prepare_source_candidate_catalog(
    *,
    repository_root: Path,
    catalog_path: Path,
    snapshot_path: Path,
    core_id: str,
    catalog_rebase_path: Path | None,
    catalog_validator: CatalogValidator,
    candidate_catalog_validator: CandidateCatalogValidator,
    eligibility_validator: EligibilityValidator,
    build_renderer: BuildRenderer,
    source_aware_contract_resolver: SourceAwareContractResolver,
) -> dict[str, Any]:
    """Create and return the identity of one immutable candidate catalog."""

    try:
        repository_root = repository_root.resolve(strict=True)
    except OSError as exc:
        raise PipelineError("source-candidate repository root is missing") from exc
    if not repository_root.is_dir():
        raise PipelineError("source-candidate repository root is not a directory")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        raise PipelineError("source-candidate core ID is malformed")
    _validate_candidate_callbacks(
        catalog_validator=catalog_validator,
        candidate_catalog_validator=candidate_catalog_validator,
        eligibility_validator=eligibility_validator,
        build_renderer=build_renderer,
        source_aware_contract_resolver=source_aware_contract_resolver,
    )
    _resolved_catalog, catalog, catalog_raw = _load_canonical_catalog(
        repository_root=repository_root,
        catalog_path=catalog_path,
        catalog_validator=catalog_validator,
    )
    if core_id not in catalog.get("cores", {}):
        raise PipelineError(f"source-candidate core is not cataloged: {core_id}")
    base_spec = copy.deepcopy(catalog["cores"][core_id])

    snapshot, snapshot_raw, snapshot_relative_to_probe_root = _read_snapshot(
        snapshot_path, repository_root
    )
    source_value = snapshot["sources"].get(core_id)
    current_catalog_sha256 = sha256_bytes(catalog_raw)
    stale_snapshot = snapshot["catalog"]["file_sha256"] != current_catalog_sha256
    if stale_snapshot and catalog_rebase_path is None:
        raise PipelineError(
            "source-candidate snapshot catalog binding is stale; create and pass "
            "an explicit core-source-snapshot catalog rebase"
        )
    if not stale_snapshot and catalog_rebase_path is not None:
        raise PipelineError(
            "source-candidate catalog rebase is forbidden for a current snapshot"
        )
    source_aware_log_contract = source_aware_contract_resolver(core_id)
    snapshot_entry = _validated_source_entry(
        source_value,
        core_id=core_id,
        catalog_spec=base_spec,
        source_aware_log_contract=source_aware_log_contract,
    )
    snapshot_relative = (
        Path(".local-e2e/source-probes") / snapshot_relative_to_probe_root
    ).as_posix()
    catalog_rebase = (
        _validate_catalog_rebase(
            path=catalog_rebase_path,
            repository_root=repository_root,
            snapshot=snapshot,
            snapshot_raw=snapshot_raw,
            snapshot_relative=snapshot_relative,
            catalog_raw=catalog_raw,
            core_id=core_id,
            spec=base_spec,
            entry=snapshot_entry,
        )
        if catalog_rebase_path is not None
        else None
    )
    mirror, mirror_relative_to_cache = _verify_mirror(
        repository_root=repository_root,
        core_id=core_id,
        entry=snapshot_entry,
    )
    entry = _retained_candidate_entry(
        snapshot_entry,
        source_aware_log_contract=source_aware_log_contract,
    )
    if entry != snapshot_entry:
        _retain_candidate_ref(mirror, entry)
    _verify_source_bound_files(spec=base_spec, mirror=mirror, entry=entry)
    execution_spec, epoch_derivation = _candidate_execution_spec(base_spec, entry)
    provenance = _candidate_provenance(
        repository_root=repository_root,
        core_id=core_id,
        snapshot=snapshot,
        snapshot_raw=snapshot_raw,
        snapshot_relative=snapshot_relative,
        catalog_raw=catalog_raw,
        base_spec=base_spec,
        entry=entry,
        execution_spec=execution_spec,
        epoch_derivation=epoch_derivation,
        mirror_relative_to_cache=mirror_relative_to_cache,
        catalog_rebase=catalog_rebase,
    )

    candidate = {
        key: copy.deepcopy(value)
        for key, value in catalog.items()
        if key != "cores"
    }
    candidate["cores"] = {core_id: execution_spec}
    candidate["source_candidate"] = provenance
    projection = (
        validated_source_candidate_contract_projection(
            provenance,
            core_id=core_id,
            canonical_spec=base_spec,
            execution_spec=execution_spec,
            source_aware_log_contract=source_aware_log_contract,
        )
        if source_aware_log_contract
        and entry["status"] == "fast-forward"
        and entry["commit"] != entry["catalog_commit"]
        else None
    )
    candidate_catalog_validator(candidate, core_id, base_spec, projection)
    eligibility_validator(candidate, [core_id])
    for arch in execution_spec["targets"]:
        rendered = build_renderer(
            core_id,
            arch,
            execution_spec,
            candidate["resolver"],
            base_spec,
            projection,
        )
        if not isinstance(rendered, str) or not rendered.strip():
            raise PipelineError(
                f"source-candidate build contract cannot render: {core_id}/{arch}"
            )

    output_parent_relative = (
        Path(".local-e2e/source-candidates")
        / snapshot["content_sha256"]
        / core_id
        / provenance["candidate_id"]
    )
    output_parent = _ensure_contained_create_directory(
        repository_root,
        output_parent_relative,
        "source-candidate catalog output",
    )
    output_path = output_parent / "core-builds.json"
    if output_path.exists() or output_path.is_symlink():
        raise PipelineError(
            f"refusing to reuse source-candidate catalog: {output_path}"
        )
    atomic_create_json(output_path, candidate)
    report = validate_source_candidate_catalog(
        repository_root=repository_root,
        canonical_catalog_path=catalog_path,
        candidate_catalog_path=output_path,
        catalog_validator=catalog_validator,
        candidate_catalog_validator=candidate_catalog_validator,
        eligibility_validator=eligibility_validator,
        build_renderer=build_renderer,
        source_aware_contract_resolver=source_aware_contract_resolver,
    )
    report["status"] = "prepared"
    return report


__all__ = [
    "CATALOG_REBASE_VALIDATION_SCOPE",
    "CANDIDATE_VALIDATION_SCOPE",
    "LEGACY_REUSABLE_REF_GENERATOR_SHA256",
    "SourceCandidateContractProjection",
    "core_spec_sha256",
    "prepare_source_candidate_catalog",
    "prepare_source_snapshot_catalog_rebase",
    "source_candidate_execution_spec",
    "validated_source_candidate_contract_projection",
    "validate_promoted_source_candidate_contract",
    "validate_source_candidate_catalog",
]
