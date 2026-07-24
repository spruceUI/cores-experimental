from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release import (
    construct_core_result,
    core_result_content_sha256,
    document_file_sha256,
    validate_core_result,
    write_core_result,
)
from tests.test_full_release_support import (
    normalized_e2e,
    package_bytes,
    release_plan,
    sha256,
    write_plan_fixture,
)


class FullReleaseResultTests(unittest.TestCase):
    def test_construction_is_deterministic_sorted_and_plan_bound(self) -> None:
        plan = release_plan(("alpha",))
        plan_file_sha256 = document_file_sha256(plan)
        e2e = normalized_e2e(plan, "alpha", "local")
        e2e["targets"].reverse()

        first = construct_core_result(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            core_id="alpha",
            runner_selector="local",
            e2e=e2e,
        )
        second = construct_core_result(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            core_id="alpha",
            runner_selector="local",
            e2e=e2e,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            [target["architecture"] for target in first["targets"]],
            ["arm64", "armhf"],
        )
        self.assertEqual(first["content_sha256"], core_result_content_sha256(first))
        self.assertEqual(first["plan"]["file_sha256"], plan_file_sha256)
        self.assertEqual(first["result"], "passed")
        self.assertTrue(first["local_only"])
        self.assertEqual(first["publication"], "disabled")

        validated = validate_core_result(
            first,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector="local",
        )
        validated["targets"][0]["artifact_size"] += 1
        self.assertNotEqual(validated, first)

    def test_package_artifact_and_runner_mismatches_are_rejected(self) -> None:
        plan = release_plan(("alpha",))
        plan_file_sha256 = document_file_sha256(plan)

        wrong_package = normalized_e2e(plan, "alpha", "local")
        wrong_package["package"]["sha256"] = sha256("different package")
        with self.assertRaisesRegex(PipelineError, "package does not match"):
            construct_core_result(
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                core_id="alpha",
                runner_selector="local",
                e2e=wrong_package,
            )

        wrong_artifact = normalized_e2e(plan, "alpha", "local")
        wrong_artifact["targets"][0]["artifact_sha256"] = sha256(
            "different artifact"
        )
        with self.assertRaisesRegex(PipelineError, "targets do not match"):
            construct_core_result(
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                core_id="alpha",
                runner_selector="local",
                e2e=wrong_artifact,
            )

        simulated = normalized_e2e(plan, "alpha", "github-actions-sim")
        with self.assertRaisesRegex(PipelineError, "runner does not match"):
            construct_core_result(
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                core_id="alpha",
                runner_selector="local",
                e2e=simulated,
            )

    def test_write_rehashes_package_and_creates_no_output_on_failure(self) -> None:
        plan = release_plan(("alpha",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = write_plan_fixture(root, plan)
            package_path = root / "alpha_libretro.zip"
            package_path.write_bytes(b"tampered-package\n")
            output_dir = root / "result"

            with self.assertRaisesRegex(PipelineError, "package bytes do not match"):
                write_core_result(
                    plan=plan,
                    plan_path=plan_path,
                    core_id="alpha",
                    runner_selector="local",
                    e2e=normalized_e2e(plan, "alpha", "local"),
                    package_path=package_path,
                    output_dir=output_dir,
                )
            self.assertFalse(output_dir.exists())

    def test_write_rejects_symlink_inputs_and_symlink_output_parent(self) -> None:
        plan = release_plan(("alpha",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = write_plan_fixture(root, plan)
            real_package = root / "real" / "alpha_libretro.zip"
            real_package.parent.mkdir()
            real_package.write_bytes(package_bytes("alpha"))
            package_link = root / "alpha_libretro.zip"
            package_link.symlink_to(real_package)

            package_output = root / "package-link-result"
            with self.assertRaisesRegex(PipelineError, "non-symlink"):
                write_core_result(
                    plan=plan,
                    plan_path=plan_path,
                    core_id="alpha",
                    runner_selector="local",
                    e2e=normalized_e2e(plan, "alpha", "local"),
                    package_path=package_link,
                    output_dir=package_output,
                )
            self.assertFalse(package_output.exists())

            plan_link = root / "plan-link.json"
            plan_link.symlink_to(plan_path)
            plan_output = root / "plan-link-result"
            with self.assertRaisesRegex(PipelineError, "non-symlink"):
                write_core_result(
                    plan=plan,
                    plan_path=plan_link,
                    core_id="alpha",
                    runner_selector="local",
                    e2e=normalized_e2e(plan, "alpha", "local"),
                    package_path=real_package,
                    output_dir=plan_output,
                )
            self.assertFalse(plan_output.exists())

            actual_parent = root / "actual-parent"
            actual_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(actual_parent, target_is_directory=True)
            escaped_output = linked_parent / "result"
            with self.assertRaisesRegex(PipelineError, "parent must not be a symlink"):
                write_core_result(
                    plan=plan,
                    plan_path=plan_path,
                    core_id="alpha",
                    runner_selector="local",
                    e2e=normalized_e2e(plan, "alpha", "local"),
                    package_path=real_package,
                    output_dir=escaped_output,
                )
            self.assertFalse((actual_parent / "result").exists())

    def test_validation_rejects_manifest_tamper_even_with_valid_hash_shapes(
        self,
    ) -> None:
        plan = release_plan(("alpha",))
        plan_file_sha256 = document_file_sha256(plan)
        result = construct_core_result(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            core_id="alpha",
            runner_selector="local",
            e2e=normalized_e2e(plan, "alpha", "local"),
        )
        tampered = copy.deepcopy(result)
        tampered["e2e"]["content_sha256"] = sha256("tampered e2e")
        with self.assertRaisesRegex(PipelineError, "content_sha256 is invalid"):
            validate_core_result(
                tampered,
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                runner_selector="local",
            )


if __name__ == "__main__":
    unittest.main()
