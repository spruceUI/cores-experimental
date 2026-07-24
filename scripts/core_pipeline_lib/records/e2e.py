"""Active E2E record boundaries kept separate from historical readers."""

from __future__ import annotations

from ..errors import PipelineError


def active_promotion_e2e_scope(
    evidence: object,
    core_id: object,
) -> tuple[list[dict], list[dict]]:
    """Return exact-one-core schema-v2 build/package entries."""

    if not isinstance(evidence, dict) or not isinstance(core_id, str):
        raise PipelineError("active promotion E2E identity is malformed")
    schema_version = evidence.get("schema_version")
    if type(schema_version) is not int or schema_version != 2:
        raise PipelineError(
            "active promotion requires an exact one-core schema-v2 E2E record"
        )
    builds = evidence.get("builds")
    packages = evidence.get("packages")
    if (
        not isinstance(builds, list)
        or not isinstance(packages, list)
        or any(not isinstance(item, dict) for item in builds)
        or any(not isinstance(item, dict) for item in packages)
    ):
        raise PipelineError("active promotion E2E build/package lists are malformed")
    if (
        {item.get("core_id") for item in builds} != {core_id}
        or {item.get("core_id") for item in packages} != {core_id}
    ):
        raise PipelineError(
            "active promotion E2E evidence must contain exactly one core"
        )
    return builds, packages
