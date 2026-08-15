from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release import (
    construct_release_plan,
    document_file_sha256,
    release_plan_content_sha256,
    validate_release_plan,
    write_release_plan,
)
from tests.test_full_release_support import (
    release_plan,
    release_row,
    repository_facts,
    sha256,
)


class FullReleasePlanTests(unittest.TestCase):
    def test_construction_is_deterministic_sorted_and_independent(self) -> None:
        rows = [release_row("beta"), release_row("alpha")]
        first = construct_release_plan(
            candidate_id="candidate-v1",
            scope="explicit",
            repository=repository_facts(),
            cores=rows,
        )
        second = construct_release_plan(
            candidate_id="candidate-v1",
            scope="explicit",
            repository=repository_facts(),
            cores=list(reversed(rows)),
        )

        self.assertEqual(first, second)
        self.assertEqual([row["core_id"] for row in first["cores"]], ["alpha", "beta"])
        self.assertEqual(first["content_sha256"], release_plan_content_sha256(first))
        self.assertEqual(first["schema_version"], 3)
        self.assertTrue(first["local_only"])
        self.assertEqual(first["publication"], "disabled")

        rows[0]["source"]["commit"] = "f" * 40
        validated = validate_release_plan(first)
        validated["cores"][0]["source"]["commit"] = "e" * 40
        self.assertNotEqual(first["cores"][0]["source"]["commit"], "e" * 40)
        self.assertNotEqual(first["cores"][1]["source"]["commit"], "f" * 40)

    def test_validation_rejects_tampered_summary_digest_and_forbidden_claims(
        self,
    ) -> None:
        plan = release_plan(("alpha",))

        stale_digest = copy.deepcopy(plan)
        stale_digest["cores"][0]["package"]["size"] += 1
        with self.assertRaisesRegex(PipelineError, "content_sha256"):
            validate_release_plan(stale_digest)

        inconsistent_summary = copy.deepcopy(plan)
        inconsistent_summary["summary"]["package_bytes"] += 1
        inconsistent_summary["content_sha256"] = release_plan_content_sha256(
            inconsistent_summary
        )
        with self.assertRaisesRegex(PipelineError, "package_bytes is inconsistent"):
            validate_release_plan(inconsistent_summary)

        forbidden = copy.deepcopy(plan)
        forbidden["device_profiles"] = ["test-device"]
        with self.assertRaises(PipelineError) as context:
            validate_release_plan(forbidden)
        self.assertIn("fields are not exact", str(context.exception))

        legacy_shape = copy.deepcopy(plan)
        legacy_shape["schema_version"] = 1
        legacy_shape["content_sha256"] = release_plan_content_sha256(legacy_shape)
        with self.assertRaisesRegex(PipelineError, "schema_version"):
            validate_release_plan(legacy_shape)

    def test_repository_orchestration_is_required_and_path_bound(self) -> None:
        missing = repository_facts()
        del missing["orchestration"]
        with self.assertRaisesRegex(PipelineError, "fields are not exact"):
            construct_release_plan(
                candidate_id="candidate-v2",
                scope="explicit",
                repository=missing,
                cores=[release_row("alpha")],
            )

        wrong_path = repository_facts()
        wrong_path["orchestration"]["worker"]["path"] = (
            ".github/workflows/build-alpha.yml"
        )
        with self.assertRaisesRegex(PipelineError, "worker.path is not canonical"):
            construct_release_plan(
                candidate_id="candidate-v2",
                scope="explicit",
                repository=wrong_path,
                cores=[release_row("alpha")],
            )

        malformed_hash = repository_facts()
        malformed_hash["orchestration"]["coordinator"]["file_sha256"] = "bad"
        with self.assertRaisesRegex(PipelineError, "file_sha256 is invalid"):
            construct_release_plan(
                candidate_id="candidate-v2",
                scope="explicit",
                repository=malformed_hash,
                cores=[release_row("alpha")],
            )

        extra_role = repository_facts()
        extra_role["orchestration"]["publisher"] = extra_role["orchestration"][
            "worker"
        ]
        with self.assertRaisesRegex(PipelineError, "fields are not exact"):
            construct_release_plan(
                candidate_id="candidate-v2",
                scope="explicit",
                repository=extra_role,
                cores=[release_row("alpha")],
            )

    def test_construction_rejects_path_escape_duplicate_and_noncanonical_rows(
        self,
    ) -> None:
        escaped = release_row("alpha")
        escaped["compatibility"]["path"] = "../alpha.json"
        with self.assertRaisesRegex(PipelineError, "path is invalid"):
            construct_release_plan(
                candidate_id="candidate-v1",
                scope="explicit",
                repository=repository_facts(),
                cores=[escaped],
            )

        duplicate = release_row("alpha")
        with self.assertRaisesRegex(PipelineError, "must be unique"):
            construct_release_plan(
                candidate_id="candidate-v1",
                scope="explicit",
                repository=repository_facts(),
                cores=[duplicate, copy.deepcopy(duplicate)],
            )

        wrong_workflow = release_row("alpha")
        wrong_workflow["workflow"]["path"] = ".github/workflows/build-beta.yml"
        with self.assertRaisesRegex(PipelineError, "workflow path is not core-owned"):
            construct_release_plan(
                candidate_id="candidate-v1",
                scope="explicit",
                repository=repository_facts(),
                cores=[wrong_workflow],
            )

    def test_write_is_byte_deterministic_and_refuses_replacement(self) -> None:
        plan = release_plan(("alpha",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.json"
            second = root / "second.json"
            write_release_plan(plan=plan, output_path=first)
            write_release_plan(plan=plan, output_path=second)

            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(sha256(first.read_bytes()), document_file_sha256(plan))
            original = first.read_bytes()
            with self.assertRaisesRegex(PipelineError, "refusing to replace"):
                write_release_plan(plan=plan, output_path=first)
            self.assertEqual(first.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
