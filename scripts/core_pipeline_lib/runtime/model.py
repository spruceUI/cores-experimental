"""Immutable inputs and resolved state for pipeline runner profiles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


RunnerSelector = Literal["local", "github-actions", "github-actions-sim"]
RunnerProfile = Literal["local", "github-actions"]
RunnerMode = Literal["native", "simulated"]
RunnerBackend = Literal["local-docker", "github-hosted-docker"]


@dataclass(frozen=True, slots=True)
class RunnerRequest:
    """Untrusted runner selection and repository state supplied by the entrypoint.

    ``repository_head`` and ``repository_clean`` are injected so this package
    does not run Git itself. Native GitHub Actions resolution requires both;
    local and simulated resolution preserve them when supplied.
    """

    profile: RunnerSelector | str
    repository_root: Path
    output_root: Path
    run_id: str | None = None
    repository_head: str | None = None
    repository_clean: bool | None = None


@dataclass(frozen=True, slots=True)
class RunnerContext:
    """Validated runner state consumed by the shared build implementation."""

    profile: RunnerProfile
    mode: RunnerMode
    backend: RunnerBackend
    repository_root: Path
    output_root: Path
    run_root: Path
    run_id: str
    repository_head: str | None
    repository_clean: bool | None
    local_only: bool = True
    publication: Literal["disabled"] = "disabled"
