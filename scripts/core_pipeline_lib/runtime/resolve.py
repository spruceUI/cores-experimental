"""Fail-closed routing between explicit runner-profile delegates."""

from __future__ import annotations

import datetime as dt
from typing import Mapping

from .errors import RunnerProfileError
from .github_actions import (
    resolve_native_actions_profile,
    resolve_simulated_actions_profile,
)
from .local import resolve_local_profile
from .model import RunnerContext, RunnerRequest
from .paths import (
    absolute_exact_path,
    require_contained_output,
    require_real_directory,
    validate_repository_state,
)


RUNNER_SELECTORS = frozenset({"local", "github-actions", "github-actions-sim"})


def resolve_runner_context(
    request: RunnerRequest,
    *,
    env: Mapping[str, str],
    now: dt.datetime | None = None,
) -> RunnerContext:
    """Resolve one selector without reading process globals.

    The shared router validates repository and output boundaries once, then
    delegates environment-specific identity checks to the selected profile.
    Every returned context remains local-only with publication disabled.
    """

    if not isinstance(request, RunnerRequest):
        raise RunnerProfileError("runner request has an unexpected type")
    if not isinstance(env, Mapping):
        raise RunnerProfileError("runner environment must be a mapping")
    selector = request.profile
    if not isinstance(selector, str) or selector not in RUNNER_SELECTORS:
        raise RunnerProfileError(
            "runner profile must be exactly local, github-actions, or "
            "github-actions-sim"
        )

    repository_root = require_real_directory(
        absolute_exact_path(request.repository_root, "repository root"),
        "repository root",
    )
    output_root = require_contained_output(repository_root, request.output_root)
    repository_head, repository_clean = validate_repository_state(request)
    common = {
        "request": request,
        "env": env,
        "repository_root": repository_root,
        "output_root": output_root,
        "repository_head": repository_head,
        "repository_clean": repository_clean,
    }

    if selector == "local":
        return resolve_local_profile(now=now, **common)
    if selector == "github-actions-sim":
        return resolve_simulated_actions_profile(**common)
    return resolve_native_actions_profile(**common)
