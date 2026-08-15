"""Prepare exact, full-history Git graphs for pinned release-track ancestry.

The track registry remains the authority for which parent/child relationships
must be proved.  This module only materializes the already validated source
requirements into contained bare repositories.  Floating refs are discovery
inputs: the pinned commit and tree remain the acceptance identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urlsplit

from ..errors import PipelineError


CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SOURCE_GRAPH_REQUIREMENT_KEYS = frozenset(
    {"core_id", "repository", "sources", "ancestry"}
)
SOURCE_KEYS = frozenset({"requested_ref", "commit", "tree"})
ANCESTRY_KEYS = frozenset({"ancestor", "descendant"})
ALLOWED_LOCAL_CONFIG_KEYS = frozenset(
    {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "remote.origin.url",
    }
)

GitRunner = Callable[..., subprocess.CompletedProcess[str]]
AncestryVerifier = Callable[[str, str, str, str], bool]


def _source_repository_is_safe(value: object) -> bool:
    if not isinstance(value, str) or not value or any(
        character.isspace() for character in value
    ):
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.path.startswith("/")
        and parsed.path.endswith(".git")
        and "//" not in parsed.path
        and all(part not in {"", ".", ".."} for part in parsed.path.split("/")[1:])
    )


def _source_ref_is_safe(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(
        ("refs/heads/", "refs/tags/")
    ):
        return False
    name = value.split("/", 2)[2]
    return (
        bool(name)
        and not name.startswith(".")
        and not name.endswith((".", "/"))
        and ".." not in name
        and "//" not in name
        and "@{" not in name
        and "\\" not in name
        and not any(character in name for character in " ~^:?*[")
        and all(not part.endswith(".lock") for part in name.split("/"))
    )


def validated_source_graph_requirements(value: object) -> list[dict[str, Any]]:
    """Validate and normalize a deterministic release source-graph request."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PipelineError("release source graph requirements must be a list")
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        label = f"release source graph requirement {index}"
        if not isinstance(raw, Mapping) or set(raw) != SOURCE_GRAPH_REQUIREMENT_KEYS:
            raise PipelineError(f"{label} fields are not exact")
        core_id = raw.get("core_id")
        repository = raw.get("repository")
        sources = raw.get("sources")
        ancestry = raw.get("ancestry")
        if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
            raise PipelineError(f"{label} core ID is invalid")
        if not _source_repository_is_safe(repository):
            raise PipelineError(f"{label} repository is invalid")
        if (
            not isinstance(sources, list)
            or not sources
            or not isinstance(ancestry, list)
        ):
            raise PipelineError(f"{label} source/ancestry lists are invalid")

        normalized_sources: list[dict[str, str]] = []
        for source_index, source in enumerate(sources):
            if not isinstance(source, Mapping) or set(source) != SOURCE_KEYS:
                raise PipelineError(
                    f"{label} source {source_index} fields are not exact"
                )
            requested_ref = source.get("requested_ref")
            commit = source.get("commit")
            tree = source.get("tree")
            if (
                not _source_ref_is_safe(requested_ref)
                or not isinstance(commit, str)
                or SHA1_RE.fullmatch(commit) is None
                or not isinstance(tree, str)
                or SHA1_RE.fullmatch(tree) is None
            ):
                raise PipelineError(f"{label} source {source_index} is invalid")
            normalized_sources.append(
                {
                    "requested_ref": requested_ref,
                    "commit": commit,
                    "tree": tree,
                }
            )
        expected_sources = sorted(
            normalized_sources,
            key=lambda item: (item["requested_ref"], item["commit"], item["tree"]),
        )
        if normalized_sources != expected_sources or len(
            {
                (item["requested_ref"], item["commit"], item["tree"])
                for item in normalized_sources
            }
        ) != len(normalized_sources):
            raise PipelineError(f"{label} sources must be unique and sorted")

        commits = {item["commit"] for item in normalized_sources}
        normalized_ancestry: list[dict[str, str]] = []
        for edge_index, edge in enumerate(ancestry):
            if not isinstance(edge, Mapping) or set(edge) != ANCESTRY_KEYS:
                raise PipelineError(
                    f"{label} ancestry {edge_index} fields are not exact"
                )
            ancestor = edge.get("ancestor")
            descendant = edge.get("descendant")
            if (
                not isinstance(ancestor, str)
                or SHA1_RE.fullmatch(ancestor) is None
                or not isinstance(descendant, str)
                or SHA1_RE.fullmatch(descendant) is None
                or ancestor == descendant
                or ancestor not in commits
                or descendant not in commits
            ):
                raise PipelineError(f"{label} ancestry {edge_index} is invalid")
            normalized_ancestry.append(
                {"ancestor": ancestor, "descendant": descendant}
            )
        expected_ancestry = sorted(
            normalized_ancestry,
            key=lambda item: (item["ancestor"], item["descendant"]),
        )
        if normalized_ancestry != expected_ancestry or len(
            {(item["ancestor"], item["descendant"]) for item in normalized_ancestry}
        ) != len(normalized_ancestry):
            raise PipelineError(f"{label} ancestry must be unique and sorted")
        normalized.append(
            {
                "core_id": core_id,
                "repository": repository,
                "sources": normalized_sources,
                "ancestry": normalized_ancestry,
            }
        )
    if [item["core_id"] for item in normalized] != sorted(
        item["core_id"] for item in normalized
    ) or len({item["core_id"] for item in normalized}) != len(normalized):
        raise PipelineError("release source graph core requirements must be unique and sorted")
    return normalized


def _git_environment() -> dict[str, str]:
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
    return environment


def _run(
    runner: GitRunner,
    argv: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    label: str,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            argv,
            cwd=cwd,
            env=dict(environment),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PipelineError(f"{label} failed: {exc}") from exc
    if result.returncode:
        detail = result.stderr.strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise PipelineError(f"{label} failed{suffix}")
    return result


def _git_prefix(mirror: Path) -> list[str]:
    return [
        "git",
        "--no-replace-objects",
        "-c",
        "core.commitGraph=false",
        f"--git-dir={mirror}",
    ]


def source_ref_fetch_argv(
    mirror: Path,
    repository: str,
    requested_ref: str,
) -> list[str]:
    """Return the exact full-history argv for one validated source ref."""

    namespace = hashlib.sha256(requested_ref.encode()).hexdigest()
    return [
        *_git_prefix(mirror),
        "fetch",
        "--force",
        "--no-tags",
        "--no-recurse-submodules",
        repository,
        f"+{requested_ref}:refs/spruce-source-refs/{namespace}",
    ]


def source_commit_fetch_argv(
    mirror: Path,
    repository: str,
    commit: str,
) -> list[str]:
    """Return the exact fallback argv for one unreachable pinned commit."""

    return [
        *_git_prefix(mirror),
        "fetch",
        "--force",
        "--no-tags",
        "--no-recurse-submodules",
        repository,
        f"+{commit}:refs/spruce-source-commits/{commit}",
    ]


def _ensure_contained_directory(repository_root: Path, cache: Path) -> None:
    if not repository_root.is_absolute() or not cache.is_absolute():
        raise PipelineError("release source graph paths must be absolute")
    try:
        relative = cache.relative_to(repository_root)
    except ValueError as exc:
        raise PipelineError("release source graph cache escapes the repository") from exc
    if not relative.parts:
        raise PipelineError("release source graph cache must not be the repository root")
    current = repository_root
    if current.is_symlink() or not current.is_dir():
        raise PipelineError("release source graph repository root is invalid")
    for part in relative.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink() or not current.is_dir():
                raise PipelineError(
                    "release source graph cache path must contain only real directories"
                )
        else:
            current.mkdir()


def _git(
    runner: GitRunner,
    mirror: Path,
    cache: Path,
    environment: Mapping[str, str],
    *arguments: str,
    label: str,
) -> subprocess.CompletedProcess[str]:
    return _run(
        runner,
        [*_git_prefix(mirror), *arguments],
        cwd=cache,
        environment=environment,
        label=label,
    )


def _validate_bare_mirror(
    *,
    runner: GitRunner,
    cache: Path,
    mirror: Path,
    repository: str,
    environment: Mapping[str, str],
) -> None:
    if mirror.is_symlink() or not mirror.is_dir():
        raise PipelineError(f"release source mirror is not a real directory: {mirror}")
    forbidden = (
        mirror / "commondir",
        mirror / "gitdir",
        mirror / "shallow",
        mirror / "info" / "grafts",
        mirror / "objects" / "info" / "alternates",
        mirror / "objects" / "info" / "http-alternates",
    )
    if any(path.exists() or path.is_symlink() for path in forbidden) or any(
        path.is_symlink() for path in mirror.rglob("*")
    ):
        raise PipelineError(f"release source mirror has forbidden graph inputs: {mirror}")
    bare = _git(
        runner,
        mirror,
        cache,
        environment,
        "rev-parse",
        "--is-bare-repository",
        label="inspect release source mirror",
    )
    if bare.stdout.strip() != "true":
        raise PipelineError("release source mirror must be bare")
    common = _git(
        runner,
        mirror,
        cache,
        environment,
        "rev-parse",
        "--git-common-dir",
        label="inspect release source mirror common directory",
    )
    common_path = Path(common.stdout.strip())
    if not common_path.is_absolute():
        common_path = cache / common_path
    try:
        exact_common = common_path.resolve(strict=True)
        exact_mirror = mirror.resolve(strict=True)
    except OSError as exc:
        raise PipelineError("release source mirror common directory is invalid") from exc
    if exact_common != exact_mirror:
        raise PipelineError("release source mirror uses a separate common directory")
    shallow = _git(
        runner,
        mirror,
        cache,
        environment,
        "rev-parse",
        "--is-shallow-repository",
        label="inspect release source mirror history",
    )
    if shallow.stdout.strip() != "false":
        raise PipelineError("release source mirror must contain full history")
    keys = _git(
        runner,
        mirror,
        cache,
        environment,
        "config",
        "--local",
        "--no-includes",
        "--name-only",
        "--list",
        label="inspect release source mirror configuration",
    ).stdout.splitlines()
    if set(keys) != set(ALLOWED_LOCAL_CONFIG_KEYS) or len(keys) != len(set(keys)):
        raise PipelineError("release source mirror local configuration is not exact")
    remotes = _git(
        runner,
        mirror,
        cache,
        environment,
        "remote",
        label="inspect release source mirror remotes",
    ).stdout.splitlines()
    origin = _git(
        runner,
        mirror,
        cache,
        environment,
        "config",
        "--local",
        "--no-includes",
        "--get-all",
        "remote.origin.url",
        label="inspect release source mirror origin",
    ).stdout.splitlines()
    if remotes != ["origin"] or origin != [repository]:
        raise PipelineError("release source mirror origin is not exact")


def prepare_release_source_graph(
    *,
    requirements: object,
    repository_root: Path,
    repository_cache: Path,
    ancestry_verifier: AncestryVerifier,
    git_runner: GitRunner = subprocess.run,
) -> dict[str, Any]:
    """Populate contained mirrors, then prove every registry ancestry edge."""

    normalized = validated_source_graph_requirements(requirements)
    if not callable(ancestry_verifier):
        raise PipelineError("release source graph ancestry verifier is required")
    selected = [item for item in normalized if item["ancestry"]]
    if not selected:
        return {
            "status": "verified",
            "repository_count": 0,
            "source_count": 0,
            "ancestry_count": 0,
            "network_fetch_required": False,
        }
    _ensure_contained_directory(repository_root, repository_cache)
    environment = _git_environment()
    source_count = 0
    ancestry_count = 0
    for requirement in selected:
        core_id = requirement["core_id"]
        repository = requirement["repository"]
        mirror = repository_cache / f"{core_id}.git"
        if not mirror.exists() and not mirror.is_symlink():
            _run(
                git_runner,
                ["git", "init", "--bare", str(mirror)],
                cwd=repository_cache,
                environment=environment,
                label=f"initialize release source mirror for {core_id}",
            )
            _git(
                git_runner,
                mirror,
                repository_cache,
                environment,
                "config",
                "--local",
                "remote.origin.url",
                repository,
                label=f"configure release source mirror for {core_id}",
            )
        _validate_bare_mirror(
            runner=git_runner,
            cache=repository_cache,
            mirror=mirror,
            repository=repository,
            environment=environment,
        )

        requested_refs = sorted(
            {source["requested_ref"] for source in requirement["sources"]}
        )
        for requested_ref in requested_refs:
            _run(
                git_runner,
                source_ref_fetch_argv(mirror, repository, requested_ref),
                cwd=repository_cache,
                environment=environment,
                label=f"fetch exact release source ref for {core_id}",
            )
        for source in requirement["sources"]:
            commit = source["commit"]
            present = subprocess.CompletedProcess([], 1, "", "")
            try:
                present = _git(
                    git_runner,
                    mirror,
                    repository_cache,
                    environment,
                    "cat-file",
                    "-e",
                    f"{commit}^{{commit}}",
                    label=f"inspect pinned release source commit for {core_id}",
                )
            except PipelineError:
                _run(
                    git_runner,
                    source_commit_fetch_argv(mirror, repository, commit),
                    cwd=repository_cache,
                    environment=environment,
                    label=f"fetch exact pinned release source commit for {core_id}",
                )
                present = _git(
                    git_runner,
                    mirror,
                    repository_cache,
                    environment,
                    "cat-file",
                    "-e",
                    f"{commit}^{{commit}}",
                    label=f"verify pinned release source commit for {core_id}",
                )
            if present.returncode:
                raise PipelineError(f"pinned release source commit is unavailable: {core_id}")
            tree = _git(
                git_runner,
                mirror,
                repository_cache,
                environment,
                "rev-parse",
                f"{commit}^{{tree}}",
                label=f"resolve pinned release source tree for {core_id}",
            ).stdout.strip()
            if tree != source["tree"]:
                raise PipelineError(f"pinned release source tree differs: {core_id}")
            source_count += 1
        _git(
            git_runner,
            mirror,
            repository_cache,
            environment,
            "fsck",
            "--full",
            "--connectivity-only",
            label=f"verify full release source graph for {core_id}",
        )
        _validate_bare_mirror(
            runner=git_runner,
            cache=repository_cache,
            mirror=mirror,
            repository=repository,
            environment=environment,
        )
        for edge in requirement["ancestry"]:
            if ancestry_verifier(
                core_id,
                repository,
                edge["ancestor"],
                edge["descendant"],
            ) is not True:
                raise PipelineError(
                    f"release source ancestry is not verified: {core_id}/"
                    f"{edge['ancestor']}..{edge['descendant']}"
                )
            ancestry_count += 1
    return {
        "status": "verified",
        "repository_count": len(selected),
        "source_count": source_count,
        "ancestry_count": ancestry_count,
        "network_fetch_required": True,
    }


__all__ = [
    "prepare_release_source_graph",
    "source_commit_fetch_argv",
    "source_ref_fetch_argv",
    "validated_source_graph_requirements",
]
