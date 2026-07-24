from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import unittest

from tests import expected_counts
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release import release_plan_content_sha256
from scripts.core_pipeline_lib.release import repository as release_repository


class FullReleaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = pipeline.release_repository_services()
        self.real_run = release_repository.run

    def clean_run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if (
            len(args) == 4
            and args[:3] == ["git", "ls-files", "--error-unmatch"]
            and args[3] != "--"
        ):
            return subprocess.CompletedProcess(args, 0, args[3] + "\n", "")
        if args[:4] == ["git", "ls-files", "--error-unmatch", "--"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "\n".join(args[4:]) + "\n",
                "",
            )
        return self.real_run(args, cwd=cwd, check=check)

    def construct(self, *, core_ids: list[str]) -> dict:
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ):
            return release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-2048-gambatte-v2",
                scope="explicit",
                requested_cores=core_ids,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_actual_two_core_plan_is_tracked_only_and_profile_bound(self) -> None:
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def guarded_read_bytes(path: Path) -> bytes:
            if ".local-e2e" in path.parts:
                raise AssertionError(f"planner read ignored evidence: {path}")
            return original_read_bytes(path)

        def guarded_read_text(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> str:
            if ".local-e2e" in path.parts:
                raise AssertionError(f"planner read ignored evidence: {path}")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_bytes", guarded_read_bytes), mock.patch.object(
            Path,
            "read_text",
            guarded_read_text,
        ):
            plan = self.construct(core_ids=["gambatte", "2048"])

        self.assertEqual(
            [row["core_id"] for row in plan["cores"]],
            ["2048", "gambatte"],
        )
        self.assertEqual(plan["summary"]["core_count"], 2)
        self.assertEqual(plan["summary"]["target_count"], 4)
        for row in plan["cores"]:
            self.assertEqual(
                [target["execution_profile"] for target in row["targets"]],
                ["ra64-universal-v1", "ra32-a30-v1"],
            )
        for role, relative in (
            ("coordinator", ".github/workflows/release-candidate.yml"),
            ("worker", ".github/workflows/_build-one-core.yml"),
        ):
            self.assertEqual(
                {
                    "path": relative,
                    "file_sha256": pipeline.sha256_file(pipeline.ROOT / relative),
                },
                plan["repository"]["orchestration"][role],
            )

    def test_full_workflow_roster_constructs_a_release_ready_plan(self) -> None:
        # The 2026-07-24 milestone: with every shipped-core workflow
        # canonical (98/98, zero uncataloged, zero pending), the FULL roster
        # constructs a valid release plan for the first time -- the
        # "not release-ready" blocker report this test used to pin is no
        # longer reachable from real repository state.
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ):
            plan = release_repository.construct_tracked_release_plan(
                candidate_id="full-roster-v1",
                scope="full-workflow-roster",
                requested_cores=None,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        self.assertEqual(
            plan["summary"]["core_count"], expected_counts.CATALOG_CORE_COUNT
        )
        self.assertEqual(
            plan["summary"]["target_count"],
            sum(len(spec["targets"]) for spec in catalog["cores"].values()),
        )
        self.assertEqual(
            [row["core_id"] for row in plan["cores"]],
            sorted(catalog["cores"]),
        )

    def test_planner_rejects_compatibility_e2e_drift_from_pin(self) -> None:
        real_load_json = release_repository.load_json

        def drifted_load(path: Path) -> dict:
            document = real_load_json(path)
            if path == pipeline.ROOT / "manifests" / "compatibility" / "2048.json":
                document = copy.deepcopy(document)
                document["selected_e2e_content_sha256"] = "0" * 64
                document["content_sha256"] = (
                    pipeline.core_compatibility_content_sha256(document)
                )
            return document

        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "load_json",
            side_effect=drifted_load,
        ), self.assertRaisesRegex(PipelineError, "E2E identity differs from pin"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v1",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_planner_requires_a_clean_repository(self) -> None:
        def dirty_run(
            args: list[str],
            *,
            cwd: Path | None = None,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, " M tracked-file\n", "")
            return self.real_run(args, cwd=cwd, check=check)

        with mock.patch.object(
            release_repository,
            "run",
            side_effect=dirty_run,
        ), self.assertRaisesRegex(PipelineError, "requires a clean repository"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v1",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_planner_rejects_untracked_workflow_or_pipeline_roster(self) -> None:
        for case in ("workflow", "pipeline"):
            with self.subTest(case=case):
                def untracked_run(
                    args: list[str],
                    *,
                    cwd: Path | None = None,
                    check: bool = True,
                ) -> subprocess.CompletedProcess[str]:
                    result = self.clean_run(args, cwd=cwd, check=check)
                    if args[:4] != ["git", "ls-files", "--error-unmatch", "--"]:
                        return result
                    paths = args[4:]
                    is_workflow_roster = all(
                        path.startswith(".github/workflows/") for path in paths
                    )
                    if (case == "workflow") == is_workflow_roster:
                        return subprocess.CompletedProcess(
                            args,
                            1,
                            "",
                            "simulated untracked path",
                        )
                    return result

                expected = (
                    "release workflow roster"
                    if case == "workflow"
                    else "release pipeline source bundle"
                )
                with mock.patch.object(
                    release_repository,
                    "run",
                    side_effect=untracked_run,
                ), self.assertRaisesRegex(PipelineError, expected):
                    release_repository.construct_tracked_release_plan(
                        candidate_id="release-canary-v1",
                        scope="explicit",
                        requested_cores=["2048"],
                        repository_root=pipeline.ROOT,
                        catalog_path=pipeline.DEFAULT_CATALOG,
                        services=self.services,
                    )

    def test_planner_rejects_invalid_or_inconsistent_release_orchestration(
        self,
    ) -> None:
        invalid = {
            "status": "invalid",
            "errors": ["coordinator: simulated unsafe workflow"],
        }
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "audit_release_workflows",
            return_value=invalid,
        ), self.assertRaisesRegex(PipelineError, "release orchestration is invalid"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v2",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

        inconsistent = copy.deepcopy(
            release_repository.audit_release_workflows(pipeline.ROOT)
        )
        inconsistent["coordinator"]["file_sha256"] = "0" * 64
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "audit_release_workflows",
            return_value=inconsistent,
        ), self.assertRaisesRegex(PipelineError, "audit identity is inconsistent"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v2",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_planner_rejects_untracked_release_orchestration_files(self) -> None:
        for relative in (
            ".github/workflows/release-candidate.yml",
            ".github/workflows/_build-one-core.yml",
        ):
            with self.subTest(relative=relative):
                def untracked_run(
                    args: list[str],
                    *,
                    cwd: Path | None = None,
                    check: bool = True,
                ) -> subprocess.CompletedProcess[str]:
                    if args == ["git", "ls-files", "--error-unmatch", relative]:
                        return subprocess.CompletedProcess(
                            args,
                            1,
                            "",
                            "simulated untracked orchestration",
                        )
                    return self.clean_run(args, cwd=cwd, check=check)

                with mock.patch.object(
                    release_repository,
                    "run",
                    side_effect=untracked_run,
                ), self.assertRaisesRegex(PipelineError, "not tracked by Git"):
                    release_repository.construct_tracked_release_plan(
                        candidate_id="release-canary-v2",
                        scope="explicit",
                        requested_cores=["2048"],
                        repository_root=pipeline.ROOT,
                        catalog_path=pipeline.DEFAULT_CATALOG,
                        services=self.services,
                    )

    def test_repository_revalidation_rejects_forged_orchestration_identity(
        self,
    ) -> None:
        forged = self.construct(core_ids=["2048"])
        forged["repository"]["orchestration"]["worker"]["file_sha256"] = "0" * 64
        forged["content_sha256"] = release_plan_content_sha256(forged)

        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), self.assertRaisesRegex(
            PipelineError,
            "differs from the current tracked repository",
        ):
            release_repository.validate_plan_against_repository(
                forged,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )


if __name__ == "__main__":
    unittest.main()
