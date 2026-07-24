"""Stable persisted evidence for resolved runner contexts."""

from __future__ import annotations

from .model import RunnerContext


RUNNER_EVIDENCE_KEYS = frozenset(
    {"profile", "mode", "backend", "local_only", "publication"}
)


def runner_evidence(context: RunnerContext) -> dict:
    return {
        "profile": context.profile,
        "mode": context.mode,
        "backend": context.backend,
        "local_only": context.local_only,
        "publication": context.publication,
    }


def runner_evidence_is_well_formed(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != RUNNER_EVIDENCE_KEYS:
        return False
    if value.get("local_only") is not True or value.get("publication") != "disabled":
        return False
    identity = (value.get("profile"), value.get("mode"), value.get("backend"))
    return identity in {
        ("local", "native", "local-docker"),
        ("github-actions", "native", "github-hosted-docker"),
        ("github-actions", "simulated", "local-docker"),
    }
