"""Native and locally simulated GitHub Actions runner profiles."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Mapping

from .errors import RunnerProfileError
from .local import reject_native_actions_marker
from .model import RunnerContext, RunnerRequest
from .paths import (
    GIT_COMMIT_PATTERN,
    check_run_root,
    validate_new_run_id,
    validate_run_id,
)


POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]*")
SIMULATED_RUN_ID_PATTERN = re.compile(
    r"actions-sim-[A-Za-z0-9][A-Za-z0-9._-]{0,115}"
)


def required_environment(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not isinstance(value, str) or not value:
        raise RunnerProfileError(f"native GitHub Actions requires {name}")
    return value


def native_actions_run_id(
    requested: str | None,
    env: Mapping[str, str],
) -> str:
    github_run_id = required_environment(env, "GITHUB_RUN_ID")
    github_run_attempt = required_environment(env, "GITHUB_RUN_ATTEMPT")
    if POSITIVE_INTEGER_PATTERN.fullmatch(github_run_id) is None:
        raise RunnerProfileError("GITHUB_RUN_ID must be a positive decimal integer")
    if POSITIVE_INTEGER_PATTERN.fullmatch(github_run_attempt) is None:
        raise RunnerProfileError(
            "GITHUB_RUN_ATTEMPT must be a positive decimal integer"
        )
    expected = validate_run_id(f"actions-{github_run_id}-{github_run_attempt}")
    if requested is not None and requested != expected:
        raise RunnerProfileError(
            f"native GitHub Actions run ID must be exactly {expected}"
        )
    return expected


def resolve_simulated_actions_profile(
    request: RunnerRequest,
    *,
    env: Mapping[str, str],
    repository_root: Path,
    output_root: Path,
    repository_head: str | None,
    repository_clean: bool | None,
) -> RunnerContext:
    reject_native_actions_marker(env, request.profile)
    if request.run_id is None:
        raise RunnerProfileError(
            "github-actions-sim requires an explicit actions-sim-* run ID"
        )
    run_id = validate_new_run_id(request.run_id)
    if SIMULATED_RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise RunnerProfileError(
            "github-actions-sim run ID must start with actions-sim-"
        )
    return RunnerContext(
        profile="github-actions",
        mode="simulated",
        backend="local-docker",
        repository_root=repository_root,
        output_root=output_root,
        run_root=check_run_root(repository_root, output_root, run_id),
        run_id=run_id,
        repository_head=repository_head,
        repository_clean=repository_clean,
    )


def resolve_native_actions_profile(
    request: RunnerRequest,
    *,
    env: Mapping[str, str],
    repository_root: Path,
    output_root: Path,
    repository_head: str | None,
    repository_clean: bool | None,
) -> RunnerContext:
    if env.get("GITHUB_ACTIONS") != "true":
        raise RunnerProfileError("native GitHub Actions requires GITHUB_ACTIONS=true")
    if env.get("CI") != "true":
        raise RunnerProfileError("native GitHub Actions requires CI=true")
    workspace = required_environment(env, "GITHUB_WORKSPACE")
    if workspace != str(repository_root):
        raise RunnerProfileError(
            "GITHUB_WORKSPACE must exactly match the repository root"
        )
    github_sha = required_environment(env, "GITHUB_SHA")
    if GIT_COMMIT_PATTERN.fullmatch(github_sha) is None:
        raise RunnerProfileError("GITHUB_SHA must be an exact lowercase commit ID")
    if repository_head is None or repository_head != github_sha:
        raise RunnerProfileError("GITHUB_SHA must exactly match the checked-out HEAD")
    if repository_clean is not True:
        raise RunnerProfileError("native GitHub Actions requires a clean checkout")
    run_id = native_actions_run_id(request.run_id, env)
    return RunnerContext(
        profile="github-actions",
        mode="native",
        backend="github-hosted-docker",
        repository_root=repository_root,
        output_root=output_root,
        run_root=check_run_root(repository_root, output_root, run_id),
        run_id=run_id,
        repository_head=repository_head,
        repository_clean=repository_clean,
    )
