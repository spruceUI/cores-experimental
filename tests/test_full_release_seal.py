from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.core_pipeline_lib.errors import PipelineError
import scripts.core_pipeline_lib.release.seal as release_seal_module
from scripts.core_pipeline_lib.release import (
    asset_set_sha256,
    construct_core_result,
    construct_release_candidate,
    core_result_content_sha256,
    document_file_sha256,
    release_candidate_content_sha256,
    runner_contract_for_selector,
    seal_release_candidate,
    validate_release_candidate,
    validate_sealed_candidate_directory,
)
from tests.test_full_release_support import (
    normalized_e2e,
    release_plan,
    sha256,
    write_plan_fixture,
    write_result_bundle,
    write_result_set,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


class FullReleaseSealTests(unittest.TestCase):
    def test_deep_validation_never_rehashes_a_parsed_json_path(self) -> None:
        plan = release_plan(("alpha",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = write_plan_fixture(root, plan)
            write_result_set(
                root,
                plan=plan,
                plan_path=plan_path,
                runner_selector="local",
                core_ids=("alpha",),
            )
            output = root / "candidate"
            candidate = seal_release_candidate(
                plan=plan,
                plan_path=plan_path,
                results_root=root / "results",
                output_dir=output,
                runner_selector="local",
            )
            real_sha256_file = release_seal_module.sha256_file

            def reject_json_rehash(path: Path) -> str:
                if path.suffix == ".json":
                    raise AssertionError(f"JSON path was rehashed after parsing: {path}")
                return real_sha256_file(path)

            with mock.patch.object(
                release_seal_module,
                "sha256_file",
                side_effect=reject_json_rehash,
            ):
                self.assertEqual(
                    candidate,
                    validate_sealed_candidate_directory(
                        candidate=candidate,
                        output_dir=output,
                        plan=plan,
                        runner_selector="local",
                    ),
                )

    def test_complete_fan_in_seals_deterministically_and_deeply_validates(self) -> None:
        plan = release_plan()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = write_plan_fixture(root, plan)

            first_root = root / "first"
            write_result_set(
                first_root,
                plan=plan,
                plan_path=plan_path,
                runner_selector="local",
            )
            first_output = root / "candidate-first"
            first = seal_release_candidate(
                plan=plan,
                plan_path=plan_path,
                results_root=first_root / "results",
                output_dir=first_output,
                runner_selector="local",
            )

            second_root = root / "second"
            write_result_set(
                second_root,
                plan=plan,
                plan_path=plan_path,
                runner_selector="local",
            )
            second_output = root / "candidate-second"
            second = seal_release_candidate(
                plan=plan,
                plan_path=plan_path,
                results_root=second_root / "results",
                output_dir=second_output,
                runner_selector="local",
            )

            self.assertEqual(first, second)
            self.assertEqual(
                validate_sealed_candidate_directory(
                    candidate=first,
                    output_dir=first_output,
                    plan=plan,
                    runner_selector="local",
                ),
                first,
            )
            self.assertEqual(
                sorted(
                    path.relative_to(first_output).as_posix()
                    for path in first_output.rglob("*")
                ),
                [
                    "assets",
                    "assets/alpha_libretro.zip",
                    "assets/beta_libretro.zip",
                    "candidate.json",
                    "plan.json",
                    "results",
                    "results/alpha",
                    "results/alpha/result.json",
                    "results/beta",
                    "results/beta/result.json",
                ],
            )

    def test_missing_and_unexpected_result_sets_fail_without_output(self) -> None:
        for case in ("missing", "unexpected"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = release_plan()
                plan_path = write_plan_fixture(root, plan)
                if case == "missing":
                    write_result_set(
                        root,
                        plan=plan,
                        plan_path=plan_path,
                        runner_selector="local",
                        core_ids=("alpha",),
                    )
                else:
                    write_result_set(
                        root,
                        plan=plan,
                        plan_path=plan_path,
                        runner_selector="local",
                    )
                    (root / "results" / "rogue").mkdir()
                output = root / "candidate"

                with self.assertRaisesRegex(PipelineError, "result set is not exact"):
                    seal_release_candidate(
                        plan=plan,
                        plan_path=plan_path,
                        results_root=root / "results",
                        output_dir=output,
                        runner_selector="local",
                    )
                self.assertFalse(output.exists())

    def test_duplicate_results_are_rejected_by_pure_candidate_construction(
        self,
    ) -> None:
        plan = release_plan(("alpha",))
        plan_hash = document_file_sha256(plan)
        result = construct_core_result(
            plan=plan,
            plan_file_sha256=plan_hash,
            core_id="alpha",
            runner_selector="local",
            e2e=normalized_e2e(plan, "alpha", "local"),
        )
        with self.assertRaisesRegex(PipelineError, "exact plan result set"):
            construct_release_candidate(
                plan=plan,
                plan_file_sha256=plan_hash,
                runner_selector="local",
                results=[result, copy.deepcopy(result)],
                result_file_sha256_by_core={"alpha": sha256("result-file")},
            )

    def test_standalone_candidate_validation_binds_assets_to_plan(self) -> None:
        plan = release_plan(("alpha",))
        plan_hash = document_file_sha256(plan)
        result = construct_core_result(
            plan=plan,
            plan_file_sha256=plan_hash,
            core_id="alpha",
            runner_selector="local",
            e2e=normalized_e2e(plan, "alpha", "local"),
        )
        candidate = construct_release_candidate(
            plan=plan,
            plan_file_sha256=plan_hash,
            runner_selector="local",
            results=[result],
            result_file_sha256_by_core={"alpha": sha256("result-file")},
        )
        changed = copy.deepcopy(candidate)
        changed["assets"][0]["sha256"] = sha256("different package")
        changed["asset_set_sha256"] = asset_set_sha256(changed["assets"])
        changed["content_sha256"] = release_candidate_content_sha256(changed)

        with self.assertRaisesRegex(PipelineError, "asset alpha differs from plan"):
            validate_release_candidate(
                changed,
                plan=plan,
                plan_file_sha256=plan_hash,
                runner_selector="local",
            )

    def test_mixed_runner_and_mixed_plan_results_fail_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = release_plan()
            plan_path = write_plan_fixture(root, plan)
            write_result_bundle(
                root,
                plan=plan,
                plan_path=plan_path,
                core_id="alpha",
                runner_selector="local",
            )
            write_result_bundle(
                root,
                plan=plan,
                plan_path=plan_path,
                core_id="beta",
                runner_selector="github-actions-sim",
            )
            output = root / "mixed-runner-candidate"
            with self.assertRaisesRegex(PipelineError, "runner does not match"):
                seal_release_candidate(
                    plan=plan,
                    plan_path=plan_path,
                    results_root=root / "results",
                    output_dir=output,
                    runner_selector="local",
                )
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_root = root / "original"
            original_plan = release_plan(candidate_id="candidate-original")
            original_plan_path = write_plan_fixture(original_root, original_plan)
            write_result_set(
                original_root,
                plan=original_plan,
                plan_path=original_plan_path,
                runner_selector="local",
            )

            other_root = root / "other"
            other_plan = release_plan(candidate_id="candidate-other")
            other_plan_path = write_plan_fixture(other_root, other_plan)
            output = root / "mixed-plan-candidate"
            with self.assertRaises(PipelineError) as context:
                seal_release_candidate(
                    plan=other_plan,
                    plan_path=other_plan_path,
                    results_root=original_root / "results",
                    output_dir=output,
                    runner_selector="local",
                )
            self.assertIn("plan", str(context.exception))
            self.assertFalse(output.exists())

    def test_result_manifest_and_package_tamper_fail_without_output(self) -> None:
        for case in ("manifest", "package"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = release_plan()
                plan_path = write_plan_fixture(root, plan)
                write_result_set(
                    root,
                    plan=plan,
                    plan_path=plan_path,
                    runner_selector="local",
                )
                if case == "manifest":
                    result_path = root / "results" / "alpha" / "result.json"
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                    result["e2e"]["run_id"] = "tampered-run-v2"
                    write_json(result_path, result)
                else:
                    package_path = (
                        root / "results" / "alpha" / "alpha_libretro.zip"
                    )
                    package_path.write_bytes(b"tampered package bytes\n")
                output = root / "candidate"

                with self.assertRaises(PipelineError):
                    seal_release_candidate(
                        plan=plan,
                        plan_path=plan_path,
                        results_root=root / "results",
                        output_dir=output,
                        runner_selector="local",
                    )
                self.assertFalse(output.exists())

    def test_deep_validation_detects_sealed_manifest_and_asset_tamper(self) -> None:
        for case in ("manifest", "asset"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan = release_plan()
                plan_path = write_plan_fixture(root, plan)
                write_result_set(
                    root,
                    plan=plan,
                    plan_path=plan_path,
                    runner_selector="local",
                )
                output = root / "candidate"
                candidate = seal_release_candidate(
                    plan=plan,
                    plan_path=plan_path,
                    results_root=root / "results",
                    output_dir=output,
                    runner_selector="local",
                )
                if case == "manifest":
                    changed = copy.deepcopy(candidate)
                    changed["summary"]["asset_bytes"] += 1
                    write_json(output / "candidate.json", changed)
                    supplied = changed
                else:
                    (output / "assets" / "alpha_libretro.zip").write_bytes(
                        b"sealed asset tamper\n"
                    )
                    supplied = candidate

                with self.assertRaises(PipelineError):
                    validate_sealed_candidate_directory(
                        candidate=supplied,
                        output_dir=output,
                        plan=plan,
                        runner_selector="local",
                    )

    def test_deep_validation_derives_runner_and_rejects_mixed_results(self) -> None:
        plan = release_plan()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = write_plan_fixture(root, plan)
            write_result_set(
                root,
                plan=plan,
                plan_path=plan_path,
                runner_selector="local",
            )
            output = root / "candidate"
            candidate = seal_release_candidate(
                plan=plan,
                plan_path=plan_path,
                results_root=root / "results",
                output_dir=output,
                runner_selector="local",
            )

            result_path = output / "results" / "beta" / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["runner"] = runner_contract_for_selector("github-actions-sim")
            result["content_sha256"] = core_result_content_sha256(result)
            write_json(result_path, result)
            changed = copy.deepcopy(candidate)
            beta_asset = next(
                asset for asset in changed["assets"] if asset["core_id"] == "beta"
            )
            beta_asset["result"]["file_sha256"] = sha256(result_path.read_bytes())
            beta_asset["result"]["content_sha256"] = result["content_sha256"]
            changed["content_sha256"] = release_candidate_content_sha256(changed)
            write_json(output / "candidate.json", changed)

            with self.assertRaisesRegex(PipelineError, "runner does not match"):
                validate_sealed_candidate_directory(
                    candidate=changed,
                    output_dir=output,
                    plan=plan,
                )

    def test_symlink_and_output_path_escape_fail_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = release_plan()
            plan_path = write_plan_fixture(root, plan)
            write_result_set(
                root,
                plan=plan,
                plan_path=plan_path,
                runner_selector="local",
            )
            (root / "results" / "linked-result").symlink_to(
                root / "results" / "alpha", target_is_directory=True
            )
            output = root / "candidate"
            with self.assertRaisesRegex(PipelineError, "contains symlink"):
                seal_release_candidate(
                    plan=plan,
                    plan_path=plan_path,
                    results_root=root / "results",
                    output_dir=output,
                    runner_selector="local",
                )
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = release_plan()
            plan_path = write_plan_fixture(root, plan)
            write_result_set(
                root,
                plan=plan,
                plan_path=plan_path,
                runner_selector="local",
            )
            escaped_output = root / "results" / "candidate"
            with self.assertRaisesRegex(PipelineError, "must not be inside"):
                seal_release_candidate(
                    plan=plan,
                    plan_path=plan_path,
                    results_root=root / "results",
                    output_dir=escaped_output,
                    runner_selector="local",
                )
            self.assertFalse(escaped_output.exists())

    def test_asset_set_identity_matches_local_and_actions_simulation(self) -> None:
        plan = release_plan()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = write_plan_fixture(root, plan)
            candidates = {}
            for selector in ("local", "github-actions-sim"):
                run_root = root / selector
                write_result_set(
                    run_root,
                    plan=plan,
                    plan_path=plan_path,
                    runner_selector=selector,
                )
                candidates[selector] = seal_release_candidate(
                    plan=plan,
                    plan_path=plan_path,
                    results_root=run_root / "results",
                    output_dir=root / f"candidate-{selector}",
                    runner_selector=selector,
                )

            self.assertEqual(
                candidates["local"]["asset_set_sha256"],
                candidates["github-actions-sim"]["asset_set_sha256"],
            )
            self.assertNotEqual(
                candidates["local"]["content_sha256"],
                candidates["github-actions-sim"]["content_sha256"],
            )
            self.assertEqual(
                [
                    (asset["core_id"], asset["sha256"], asset["size"])
                    for asset in candidates["local"]["assets"]
                ],
                [
                    (asset["core_id"], asset["sha256"], asset["size"])
                    for asset in candidates["github-actions-sim"]["assets"]
                ],
            )


if __name__ == "__main__":
    unittest.main()
