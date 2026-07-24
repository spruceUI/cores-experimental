from __future__ import annotations

import argparse
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release import (
    MAX_ACTIONS_MATRIX_JOBS,
    actions_matrix_for_plan,
    construct_release_plan,
    release_plan_content_sha256,
)
from tests.test_full_release_support import (
    release_plan,
    release_row,
    repository_facts,
)


class FullReleaseMatrixTests(unittest.TestCase):
    def test_projection_is_compact_deterministic_and_sorted(self) -> None:
        plan = construct_release_plan(
            candidate_id="candidate-v1",
            scope="explicit",
            repository=repository_facts(),
            cores=[release_row("gamma"), release_row("alpha"), release_row("beta")],
        )

        first = actions_matrix_for_plan(plan)
        second = actions_matrix_for_plan(copy.deepcopy(plan))

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            {
                "include": [
                    {"core_id": "alpha"},
                    {"core_id": "beta"},
                    {"core_id": "gamma"},
                ]
            },
        )

    def test_projection_rejects_malformed_and_tampered_plans(self) -> None:
        with self.assertRaisesRegex(PipelineError, "invalid release plan"):
            actions_matrix_for_plan({"cores": []})

        tampered = release_plan(("alpha",))
        tampered["cores"][0]["core_id"] = "beta"
        with self.assertRaisesRegex(PipelineError, "content_sha256"):
            actions_matrix_for_plan(tampered)

    def test_projection_rejects_duplicate_core_rows_via_plan_validation(self) -> None:
        plan = release_plan(("alpha",))
        duplicate = copy.deepcopy(plan)
        duplicate["cores"].append(copy.deepcopy(duplicate["cores"][0]))
        duplicate["summary"]["core_count"] = 2
        duplicate["summary"]["target_count"] *= 2
        duplicate["summary"]["package_bytes"] *= 2
        duplicate["content_sha256"] = release_plan_content_sha256(duplicate)

        with self.assertRaisesRegex(PipelineError, "unique sorted core_id"):
            actions_matrix_for_plan(duplicate)

    def test_projection_accepts_256_rows_and_rejects_257(self) -> None:
        at_limit = construct_release_plan(
            candidate_id="candidate-256",
            scope="explicit",
            repository=repository_facts(),
            cores=[
                release_row(f"core{index:03d}")
                for index in range(MAX_ACTIONS_MATRIX_JOBS)
            ],
        )
        matrix = actions_matrix_for_plan(at_limit)
        self.assertEqual(len(matrix["include"]), MAX_ACTIONS_MATRIX_JOBS)
        self.assertEqual(matrix["include"][0], {"core_id": "core000"})
        self.assertEqual(matrix["include"][-1], {"core_id": "core255"})

        above_limit = construct_release_plan(
            candidate_id="candidate-257",
            scope="explicit",
            repository=repository_facts(),
            cores=[
                release_row(f"core{index:03d}")
                for index in range(MAX_ACTIONS_MATRIX_JOBS + 1)
            ],
        )
        with self.assertRaisesRegex(PipelineError, "matrix ceiling of 256"):
            actions_matrix_for_plan(above_limit)

    def test_cli_revalidates_repository_and_prints_one_compact_json_line(self) -> None:
        plan = release_plan(("beta", "alpha"))
        services = object()
        stdout = io.StringIO()

        with mock.patch.object(
            pipeline,
            "_canonical_full_release_plan",
            return_value=(Path("plan.json"), plan),
        ), mock.patch.object(
            pipeline,
            "release_repository_services",
            return_value=services,
        ), mock.patch.object(
            pipeline,
            "validate_plan_against_repository",
            return_value=plan,
        ) as validate, redirect_stdout(stdout):
            status = pipeline.cmd_release_matrix(
                argparse.Namespace(
                    plan=Path("plan.json"),
                    catalog=Path("catalog.json"),
                )
            )

        self.assertEqual(status, 0)
        self.assertEqual(
            stdout.getvalue(),
            '{"include":[{"core_id":"alpha"},{"core_id":"beta"}]}\n',
        )
        validate.assert_called_once_with(
            plan,
            repository_root=pipeline.ROOT,
            catalog_path=Path("catalog.json"),
            services=services,
        )


if __name__ == "__main__":
    unittest.main()
