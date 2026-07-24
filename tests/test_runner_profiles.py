#!/usr/bin/env python3

from __future__ import annotations

import datetime as dt
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from scripts.core_pipeline_lib.runtime import (
    RunnerProfileError,
    RunnerRequest,
    resolve_runner_context,
)
from scripts.core_pipeline_lib.runtime.paths import validate_run_id


HEAD = "1234567890abcdef1234567890abcdef12345678"


class RunnerProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.repository_root = Path(self.temporary_directory.name) / "repository"
        self.repository_root.mkdir()
        self.output_root = self.repository_root / ".local-e2e" / "runs"

    def request(self, profile: str, **overrides: object) -> RunnerRequest:
        values: dict[str, object] = {
            "profile": profile,
            "repository_root": self.repository_root,
            "output_root": self.output_root,
        }
        values.update(overrides)
        return RunnerRequest(**values)  # type: ignore[arg-type]

    def actions_environment(self, **overrides: str) -> dict[str, str]:
        values = {
            "CI": "true",
            "GITHUB_ACTIONS": "true",
            "GITHUB_WORKSPACE": str(self.repository_root),
            "GITHUB_SHA": HEAD,
            "GITHUB_RUN_ID": "987654321",
            "GITHUB_RUN_ATTEMPT": "2",
        }
        values.update(overrides)
        return values

    def test_local_defaults_to_a_utc_timestamp_and_is_immutable(self) -> None:
        request = self.request("local")
        context = resolve_runner_context(
            request,
            env={},
            now=dt.datetime(2026, 7, 17, 12, 34, 56, tzinfo=dt.timezone.utc),
        )

        self.assertEqual("local", context.profile)
        self.assertEqual("native", context.mode)
        self.assertEqual("local-docker", context.backend)
        self.assertEqual("20260717T123456Z", context.run_id)
        self.assertEqual(self.output_root / context.run_id, context.run_root)
        self.assertTrue(context.local_only)
        self.assertEqual("disabled", context.publication)
        with self.assertRaises(FrozenInstanceError):
            request.profile = "github-actions"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            context.run_id = "changed"  # type: ignore[misc]

    def test_local_accepts_an_explicit_safe_run_id(self) -> None:
        context = resolve_runner_context(
            self.request(
                "local",
                run_id="core-32.local",
                repository_head=HEAD,
                repository_clean=False,
            ),
            env={"GITHUB_ACTIONS": "false"},
        )

        self.assertEqual("core-32.local", context.run_id)
        self.assertEqual(HEAD, context.repository_head)
        self.assertFalse(context.repository_clean)

    def test_new_local_run_ids_reject_tranche_case_insensitively(self) -> None:
        for run_id in (
            "tranche-32.local",
            "local-TrAnChE-32",
            "local-pretranchepost",
        ):
            with self.subTest(run_id=run_id), self.assertRaisesRegex(
                RunnerProfileError, "must not contain tranche"
            ):
                resolve_runner_context(
                    self.request("local", run_id=run_id),
                    env={},
                )

    def test_historical_run_id_syntax_remains_read_compatible(self) -> None:
        oracle_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "per-core-oracles"
            / "freechaf.json"
        )
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
        historical = oracle["positive_runs"][0]["run_id"]
        self.assertEqual(historical, validate_run_id(historical))

    def test_runner_selection_is_exact_and_fail_closed(self) -> None:
        for profile in ("", "LOCAL", "github", "github-actions-simulation", " local"):
            with self.subTest(profile=profile), self.assertRaisesRegex(
                RunnerProfileError, "must be exactly"
            ):
                resolve_runner_context(self.request(profile), env={})

        with self.assertRaisesRegex(RunnerProfileError, "cannot execute"):
            resolve_runner_context(
                self.request("local", run_id="local-fixture"),
                env={"GITHUB_ACTIONS": "true"},
            )

    def test_native_actions_binds_workspace_head_clean_state_and_run_identity(self) -> None:
        context = resolve_runner_context(
            self.request(
                "github-actions",
                repository_head=HEAD,
                repository_clean=True,
            ),
            env=self.actions_environment(),
        )

        self.assertEqual("github-actions", context.profile)
        self.assertEqual("native", context.mode)
        self.assertEqual("github-hosted-docker", context.backend)
        self.assertEqual("actions-987654321-2", context.run_id)
        self.assertTrue(context.local_only)
        self.assertEqual("disabled", context.publication)

        explicit = resolve_runner_context(
            self.request(
                "github-actions",
                run_id="actions-987654321-2",
                repository_head=HEAD,
                repository_clean=True,
            ),
            env=self.actions_environment(),
        )
        self.assertEqual(context.run_id, explicit.run_id)

    def test_native_actions_rejects_ambiguous_or_mismatched_state(self) -> None:
        cases = {
            "actions marker": (
                self.request("github-actions", repository_head=HEAD, repository_clean=True),
                self.actions_environment(GITHUB_ACTIONS="false"),
            ),
            "ci marker": (
                self.request("github-actions", repository_head=HEAD, repository_clean=True),
                self.actions_environment(CI="false"),
            ),
            "workspace": (
                self.request("github-actions", repository_head=HEAD, repository_clean=True),
                self.actions_environment(GITHUB_WORKSPACE=str(self.repository_root / "other")),
            ),
            "head": (
                self.request("github-actions", repository_head="a" * 40, repository_clean=True),
                self.actions_environment(),
            ),
            "dirty": (
                self.request("github-actions", repository_head=HEAD, repository_clean=False),
                self.actions_environment(),
            ),
            "run ID": (
                self.request(
                    "github-actions",
                    run_id="actions-wrong-1",
                    repository_head=HEAD,
                    repository_clean=True,
                ),
                self.actions_environment(),
            ),
            "attempt": (
                self.request("github-actions", repository_head=HEAD, repository_clean=True),
                self.actions_environment(GITHUB_RUN_ATTEMPT="0"),
            ),
        }
        for label, (request, environment) in cases.items():
            with self.subTest(label=label), self.assertRaises(RunnerProfileError):
                resolve_runner_context(request, env=environment)

    def test_actions_simulation_requires_an_explicit_namespaced_run_id(self) -> None:
        context = resolve_runner_context(
            self.request(
                "github-actions-sim",
                run_id="actions-sim-handy-control-v1",
                repository_head=HEAD,
                repository_clean=False,
            ),
            env={},
        )

        self.assertEqual("github-actions", context.profile)
        self.assertEqual("simulated", context.mode)
        self.assertEqual("local-docker", context.backend)
        self.assertEqual("actions-sim-handy-control-v1", context.run_id)
        self.assertTrue(context.local_only)
        self.assertEqual("disabled", context.publication)

        for run_id in (None, "sim-handy", "actions-sim-", "actions-sim-.hidden"):
            with self.subTest(run_id=run_id), self.assertRaises(RunnerProfileError):
                resolve_runner_context(
                    self.request("github-actions-sim", run_id=run_id),
                    env={},
                )
        with self.assertRaisesRegex(RunnerProfileError, "cannot execute"):
            resolve_runner_context(
                self.request(
                    "github-actions-sim",
                    run_id="actions-sim-native-marker",
                ),
                env={"GITHUB_ACTIONS": "true"},
            )

    def test_new_simulated_actions_run_ids_reject_tranche_case_insensitively(
        self,
    ) -> None:
        for run_id in (
            "actions-sim-tranche-32",
            "actions-sim-TrAnChE-core",
            "actions-sim-pretranchepost",
        ):
            with self.subTest(run_id=run_id), self.assertRaisesRegex(
                RunnerProfileError, "must not contain tranche"
            ):
                resolve_runner_context(
                    self.request("github-actions-sim", run_id=run_id),
                    env={},
                )

    def test_output_must_be_contained_and_must_not_traverse_symlinks(self) -> None:
        outside = Path(self.temporary_directory.name) / "outside"
        with self.assertRaisesRegex(RunnerProfileError, "contained"):
            resolve_runner_context(
                self.request("local", output_root=outside, run_id="outside"),
                env={},
            )

        real_output = self.repository_root / "real-output"
        real_output.mkdir()
        symlink_output = self.repository_root / "linked-output"
        symlink_output.symlink_to(real_output, target_is_directory=True)
        with self.assertRaisesRegex(RunnerProfileError, "symlink"):
            resolve_runner_context(
                self.request("local", output_root=symlink_output, run_id="linked"),
                env={},
            )

        self.output_root.mkdir(parents=True)
        linked_run = self.output_root / "linked-run"
        linked_run.symlink_to(real_output, target_is_directory=True)
        with self.assertRaisesRegex(RunnerProfileError, "symlink"):
            resolve_runner_context(
                self.request("local", run_id="linked-run"),
                env={},
            )

    def test_invalid_run_ids_repository_state_and_paths_fail_closed(self) -> None:
        for run_id in ("bad/run", " space", "x" * 129):
            with self.subTest(run_id=run_id), self.assertRaises(RunnerProfileError):
                resolve_runner_context(
                    self.request("local", run_id=run_id),
                    env={},
                )
        with self.assertRaisesRegex(RunnerProfileError, "repository head"):
            resolve_runner_context(
                self.request("local", run_id="bad-head", repository_head="ABC"),
                env={},
            )
        with self.assertRaisesRegex(RunnerProfileError, "clean state"):
            resolve_runner_context(
                self.request("local", run_id="bad-clean", repository_clean=1),
                env={},
            )
        with self.assertRaisesRegex(RunnerProfileError, "must be absolute"):
            resolve_runner_context(
                self.request("local", output_root=Path("relative"), run_id="relative"),
                env={},
            )


if __name__ == "__main__":
    unittest.main()
