"""Read-only GitHub Actions matrix projection for full-release plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..errors import PipelineError
from .plan import validate_release_plan


MAX_ACTIONS_MATRIX_JOBS = 256


def actions_matrix_for_plan(plan: Mapping[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Return the exact deterministic one-core matrix for a validated plan.

    GitHub Actions permits at most 256 jobs generated from one matrix.  The
    release plan is validated before projection, so its existing canonical
    core order and uniqueness are authoritative.
    """

    validated = validate_release_plan(plan)
    group = validated["group"]
    rows = [
        {
            "core_id": row["core_id"],
            **(
                {"group_tag": group["group_tag"]}
                if isinstance(group, dict)
                else {}
            ),
        }
        for row in validated["cores"]
    ]
    if len(rows) > MAX_ACTIONS_MATRIX_JOBS:
        raise PipelineError(
            "release plan exceeds the GitHub Actions matrix ceiling of "
            f"{MAX_ACTIONS_MATRIX_JOBS} jobs"
        )
    return {"include": rows}


# This spelling reads naturally at coordinator call sites.
project_actions_matrix = actions_matrix_for_plan
