"""Local Docker runner profile."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Mapping

from .errors import RunnerProfileError
from .model import RunnerContext, RunnerRequest
from .paths import check_run_root, validate_new_run_id


def reject_native_actions_marker(
    env: Mapping[str, str], selector: str
) -> None:
    marker = env.get("GITHUB_ACTIONS")
    if marker == "true":
        raise RunnerProfileError(
            f"{selector} runner profile cannot execute in native GitHub Actions"
        )
    if marker not in (None, "", "false"):
        raise RunnerProfileError("GITHUB_ACTIONS must use an exact recognized value")


def local_run_id(requested: str | None, now: dt.datetime | None) -> str:
    if requested is not None:
        return validate_new_run_id(requested)
    instant = now if now is not None else dt.datetime.now(dt.timezone.utc)
    if not isinstance(instant, dt.datetime) or instant.tzinfo is None:
        raise RunnerProfileError(
            "local timestamp source must be a timezone-aware datetime"
        )
    return instant.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve_local_profile(
    request: RunnerRequest,
    *,
    env: Mapping[str, str],
    now: dt.datetime | None,
    repository_root: Path,
    output_root: Path,
    repository_head: str | None,
    repository_clean: bool | None,
) -> RunnerContext:
    reject_native_actions_marker(env, request.profile)
    run_id = local_run_id(request.run_id, now)
    return RunnerContext(
        profile="local",
        mode="native",
        backend="local-docker",
        repository_root=repository_root,
        output_root=output_root,
        run_root=check_run_root(repository_root, output_root, run_id),
        run_id=run_id,
        repository_head=repository_head,
        repository_clean=repository_clean,
    )
