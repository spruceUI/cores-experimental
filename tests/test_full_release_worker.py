from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.records import active_promotion_e2e_scope
from scripts.core_pipeline_lib.release import (
    ReleaseWorkerServices,
    plan_core,
    record_validated_release_result,
    runner_contract_for_selector,
)
from scripts.core_pipeline_lib.release import worker as release_worker
from scripts.core_pipeline_lib.release.repository import ReleaseRepositoryServices
from tests.test_full_release_support import (
    package_bytes,
    release_plan,
    sha256,
    write_plan_fixture,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def repository_services() -> ReleaseRepositoryServices:
    noop = lambda *args, **kwargs: None
    valid = lambda *args, **kwargs: {"status": "valid", "errors": []}
    return ReleaseRepositoryServices(
        load_catalog=lambda path: {"cores": {}},
        audit_workflows=lambda catalog: {},
        require_catalog_cores_eligible=noop,
        require_pin_sources_eligible=noop,
        validate_pin_set=valid,
        require_individual_pin_identity=lambda *args, **kwargs: ("alpha", "alpha-v1"),
        validate_compatibility=valid,
        profile_report=lambda source_set: {},
        core_spec_sha256=lambda spec: "0" * 64,
    )


class FullReleaseWorkerTests(unittest.TestCase):
    def worker_fixture(
        self,
        root: Path,
        *,
        repository_head: str | None = None,
        repository_dirty: bool = False,
    ) -> tuple[dict, Path, Path, Path, object]:
        plan = release_plan(("alpha",))
        plan_path = write_plan_fixture(root, plan)
        row = plan_core(plan, "alpha")
        run_root = root / "run"
        builds = []
        bound_records = {}
        for target in row["targets"]:
            architecture = target["architecture"]
            relative = f"run/alpha/{architecture}/build-record.json"
            record_path = root / relative
            write_json(record_path, {"architecture": architecture})
            record_sha256 = sha256(record_path.read_bytes())
            builds.append(
                {
                    "core_id": "alpha",
                    "architecture": architecture,
                    "record": relative,
                    "record_sha256": record_sha256,
                    "result": "passed",
                }
            )
            bound_records[architecture] = (
                {
                    "recipe": {
                        "repository_head": repository_head
                        if repository_head is not None
                        else plan["repository"]["head"],
                        "repository_dirty": repository_dirty,
                    },
                    "artifact": {
                        "sha256": target["artifact_sha256"],
                        "size": target["artifact_size"],
                    },
                },
                record_path,
                record_sha256,
            )
        package_path = run_root / "alpha_libretro.zip"
        package_path.write_bytes(package_bytes("alpha"))
        evidence = {
            "schema_version": 2,
            "run_id": "alpha-local-run-v1",
            "local_only": True,
            "publication": "disabled",
            "result": "passed",
            "runner": runner_contract_for_selector("local"),
            "builds": builds,
            "packages": [
                {
                    "core_id": "alpha",
                    "path": package_path.name,
                    "result": "packaged",
                    "sha256": row["package"]["sha256"],
                    "size": row["package"]["size"],
                }
            ],
            "content_sha256": sha256("fresh-e2e-content"),
        }
        e2e_path = run_root / "e2e-record.json"
        write_json(e2e_path, evidence)

        def validate_e2e(
            supplied_e2e: Path,
            selected_record: Path,
            catalog_path: Path,
            catalog: dict,
        ) -> tuple:
            self.assertEqual(supplied_e2e, e2e_path)
            self.assertEqual(
                selected_record,
                root / "run" / "alpha" / "arm64" / "build-record.json",
            )
            return (
                copy.deepcopy(evidence),
                sha256(e2e_path.read_bytes()),
                copy.deepcopy(bound_records),
                package_path,
                copy.deepcopy(evidence["packages"][0]),
            )

        return plan, plan_path, e2e_path, package_path, validate_e2e

    def test_deeply_validated_worker_stages_exact_portable_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, plan_path, e2e_path, _, validate_e2e = self.worker_fixture(root)
            output = root / "result"
            with mock.patch.object(
                release_worker,
                "validate_plan_against_repository",
                return_value=plan,
            ):
                result, selector = record_validated_release_result(
                    plan_path=plan_path,
                    core_id="alpha",
                    e2e_path=e2e_path,
                    output_dir=output,
                    repository_root=root,
                    catalog_path=root / "catalog.json",
                    repository_services=repository_services(),
                    worker_services=ReleaseWorkerServices(
                        active_e2e_scope=active_promotion_e2e_scope,
                        validate_e2e=validate_e2e,
                    ),
                )
            self.assertEqual(selector, "local")
            self.assertEqual(result["core_id"], "alpha")
            self.assertEqual(
                sorted(path.name for path in output.iterdir()),
                ["alpha_libretro.zip", "result.json"],
            )

    def test_changed_e2e_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, plan_path, e2e_path, _, validate_e2e = self.worker_fixture(root)

            def changed_validate(*args: object, **kwargs: object) -> tuple:
                result = list(validate_e2e(*args, **kwargs))
                result[0]["run_id"] = "changed-during-validation-v1"
                return tuple(result)

            output = root / "result"
            with mock.patch.object(
                release_worker,
                "validate_plan_against_repository",
                return_value=plan,
            ), self.assertRaisesRegex(PipelineError, "changed during validation"):
                record_validated_release_result(
                    plan_path=plan_path,
                    core_id="alpha",
                    e2e_path=e2e_path,
                    output_dir=output,
                    repository_root=root,
                    catalog_path=root / "catalog.json",
                    repository_services=repository_services(),
                    worker_services=ReleaseWorkerServices(
                        active_e2e_scope=active_promotion_e2e_scope,
                        validate_e2e=changed_validate,
                    ),
                )
            self.assertFalse(output.exists())

    def test_wrong_or_dirty_repository_identity_is_rejected_before_output(
        self,
    ) -> None:
        for case in ("wrong-head", "dirty"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                plan, plan_path, e2e_path, _, validate_e2e = self.worker_fixture(
                    root,
                    repository_head="f" * 40 if case == "wrong-head" else None,
                    repository_dirty=case == "dirty",
                )
                output = root / "result"
                expected = "head differs from plan" if case == "wrong-head" else "dirty"
                with mock.patch.object(
                    release_worker,
                    "validate_plan_against_repository",
                    return_value=plan,
                ), self.assertRaisesRegex(PipelineError, expected):
                    record_validated_release_result(
                        plan_path=plan_path,
                        core_id="alpha",
                        e2e_path=e2e_path,
                        output_dir=output,
                        repository_root=root,
                        catalog_path=root / "catalog.json",
                        repository_services=repository_services(),
                        worker_services=ReleaseWorkerServices(
                            active_e2e_scope=active_promotion_e2e_scope,
                            validate_e2e=validate_e2e,
                        ),
                    )
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
