from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release import (
    actions_matrix_for_plan,
    construct_core_result,
    construct_release_candidate,
    construct_release_plan,
    core_group_marker,
    document_file_sha256,
    record_validated_release_result,
    ReleaseWorkerServices,
    runner_contract_for_selector,
    validate_core_result,
    validate_release_candidate,
)
from scripts.core_pipeline_lib.release import worker as release_worker
from tests.test_full_release_support import (
    normalized_e2e,
    package_bytes,
    release_row,
    repository_facts,
    sha256,
)


GROUP_TAG = "main-stable:universal"


def group_selection(row: dict, selected_state: str) -> dict:
    core_id = row["core_id"]
    selection = {
        "schema_version": 1,
        "validation_scope": "pinned-output-reproduction-v1",
        "group_tag": GROUP_TAG,
        "inventory_content_sha256": sha256(f"inventory:{core_id}"),
        "track_registry_content_sha256": sha256("track-registry"),
        "tuning_registry_content_sha256": sha256("tuning-registry"),
        "spruce_branch_basis": {
            "basis_id": "spruce-main",
            "basis_content_sha256": sha256("spruce-main-basis"),
        },
        "core_id": core_id,
        "variant_id": sha256(f"variant:{core_id}"),
        "requested_marker": "stable",
        "requested_chipset": "universal",
        "selected_chipset": "universal",
        "selected_state": selected_state,
        "stability": "stable" if selected_state == "stable" else "unstable",
        "resolution": (
            "exact_stable"
            if selected_state == "stable"
            else "exact_test_unstable_fallback"
        ),
        "test_origin_track": "main",
        "pin": copy.deepcopy(row["pin"]),
        "source_commit": row["source"]["commit"],
        "execution_source": copy.deepcopy(row["source"]),
        "recipe_compatibility": {
            "model": "source-normalized-build-contract-v1",
            "selected_pin_core_spec_sha256": row["core_spec_sha256"],
            "execution_core_spec_sha256": row["core_spec_sha256"],
            "core_spec_identity_match": True,
        },
        "selected_architectures": [
            target["architecture"] for target in row["targets"]
        ],
        "tuning": {
            "profile_id": "universal-v1",
            "content_sha256": sha256("universal-tuning"),
            "properties": {},
            "compiler_argument_mapping_version": "gcc-machine-flags-v1",
            "compiler_arguments": [],
        },
        "expected_outputs": {
            "targets": {
                target["architecture"]: {
                    "artifact": {
                        "sha256": target["artifact_sha256"],
                        "size": target["artifact_size"],
                    }
                }
                for target in row["targets"]
            },
            "metadata": {"sha256": sha256(f"metadata:{core_id}"), "size": 64},
            "package": {"comparison": "exact", **copy.deepcopy(row["package"])},
        },
    }
    if selected_state == "stable":
        selection["approval"] = {
            "approved_test_variant_id": selection["variant_id"],
            "approved_test_origin_track": "main",
            "approved_at": "2026-08-09T00:00:00Z",
            "approved_by": "release-test",
            "reason": "approved synthetic fixture",
            "previous_stable_variant_id": None,
            "source_registry_content_sha256": sha256("source-registry"),
        }
    return selection


def group_facts() -> dict:
    return {
        "group_tag": GROUP_TAG,
        "inventory_state": "unstable",
        "track_registry": {
            "path": "manifests/core-tracks.json",
            "file_sha256": sha256("track-registry-file"),
            "content_sha256": sha256("track-registry"),
        },
        "tuning_registry": {
            "path": "manifests/chipset-tunings.json",
            "file_sha256": sha256("tuning-registry-file"),
            "content_sha256": sha256("tuning-registry"),
        },
        "release_roster": {
            "path": "manifests/spruce-release-roster.json",
            "file_sha256": sha256("release-roster-file"),
            "content_sha256": sha256("release-roster"),
        },
        "spruce_branch_bases": {
            "path": "manifests/spruce-core-branch-bases.json",
            "file_sha256": sha256("spruce-branch-bases-file"),
            "content_sha256": sha256("spruce-branch-bases"),
        },
        "stable_core_count": 1,
        "unstable_fallback_core_count": 1,
        "test_core_count": 0,
    }


def track_plan() -> dict:
    alpha = release_row("alpha")
    beta = release_row("beta")
    alpha["core_group"] = group_selection(alpha, "stable")
    beta["core_group"] = group_selection(beta, "unstable_fallback")
    return construct_release_plan(
        candidate_id="track-group-v1",
        scope="track-group",
        repository=repository_facts(),
        cores=[beta, alpha],
        group=group_facts(),
    )


class FullReleaseTrackGroupTests(unittest.TestCase):
    def test_worker_requires_tag_and_uses_grouped_deep_validator(self) -> None:
        plan = track_plan()
        plan["cores"] = [plan["cores"][0]]
        plan["group"]["stable_core_count"] = 1
        plan["group"]["unstable_fallback_core_count"] = 0
        plan["group"]["inventory_state"] = "stable"
        plan["summary"] = {
            "core_count": 1,
            "target_count": len(plan["cores"][0]["targets"]),
            "package_bytes": plan["cores"][0]["package"]["size"],
        }
        from scripts.core_pipeline_lib.release import release_plan_content_sha256

        plan["content_sha256"] = release_plan_content_sha256(plan)
        row = plan["cores"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            plan_path.write_text(
                json.dumps(plan, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            record_path = root / "run" / "alpha" / "arm64" / "build-record.json"
            record_path.parent.mkdir(parents=True)
            record_path.write_text("{}\n", encoding="utf-8")
            e2e = {
                "run_id": "group-worker-v1",
                "content_sha256": sha256("group-worker-content"),
                "runner": runner_contract_for_selector("local"),
                "builds": [{"record": str(record_path.relative_to(root))}],
            }
            e2e_path = root / "run" / "e2e-record.json"
            e2e_path.write_text(
                json.dumps(e2e, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            package_path = root / "run" / "alpha_libretro.zip"
            package_path.write_bytes(package_bytes("alpha"))
            bound_records = {
                target["architecture"]: (
                    {
                        "recipe": {
                            "repository_head": plan["repository"]["head"],
                            "repository_dirty": False,
                        },
                        "artifact": {
                            "sha256": target["artifact_sha256"],
                            "size": target["artifact_size"],
                        },
                    },
                    record_path,
                    sha256(f"fresh-record:{target['architecture']}"),
                )
                for target in row["targets"]
            }
            grouped_validator = mock.Mock(
                return_value=(
                    e2e,
                    sha256(e2e_path.read_bytes()),
                    bound_records,
                    package_path,
                    {
                        "sha256": row["package"]["sha256"],
                        "size": row["package"]["size"],
                    },
                )
            )
            legacy_validator = mock.Mock()
            worker_services = ReleaseWorkerServices(
                active_e2e_scope=lambda evidence, core_id: (
                    [{"record": str(record_path.relative_to(root))}],
                    [],
                ),
                validate_e2e=legacy_validator,
                validate_group_e2e=grouped_validator,
            )
            repository_services = type(
                "RepositoryServices",
                (),
                {"load_catalog": staticmethod(lambda path: {"cores": {}})},
            )()
            results_root = root / "results"
            output = results_root / plan["candidate_id"] / "local" / "alpha"
            with mock.patch.object(
                release_worker,
                "validate_plan_core_against_repository",
                return_value=plan,
            ):
                with self.assertRaisesRegex(PipelineError, "group tag"):
                    record_validated_release_result(
                        plan_path=plan_path,
                        core_id="alpha",
                        e2e_path=e2e_path,
                        results_root=results_root,
                        output_dir=root / "wrong-tag-result",
                        repository_root=root,
                        catalog_path=root / "catalog.json",
                        repository_services=repository_services,
                        worker_services=worker_services,
                        expected_group_tag="edge-test:universal",
                    )
                result, selector = record_validated_release_result(
                    plan_path=plan_path,
                    core_id="alpha",
                    e2e_path=e2e_path,
                    results_root=results_root,
                    output_dir=output,
                    repository_root=root,
                    catalog_path=root / "catalog.json",
                    repository_services=repository_services,
                    worker_services=worker_services,
                    expected_group_tag=GROUP_TAG,
                )
            self.assertEqual(selector, "local")
            self.assertEqual(result["core_group"], row["core_group"])
            legacy_validator.assert_not_called()
            self.assertEqual(grouped_validator.call_args.args[-1], row["core_group"])

    def test_track_documents_validate_against_release_schemas(self) -> None:
        plan = track_plan()
        plan_file_sha256 = document_file_sha256(plan)
        results = [
            construct_core_result(
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                core_id=row["core_id"],
                runner_selector="local",
                e2e=normalized_e2e(plan, row["core_id"], "local"),
            )
            for row in plan["cores"]
        ]
        candidate = construct_release_candidate(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector="local",
            results=results,
            result_file_sha256_by_core={
                result["core_id"]: sha256(f"result-file:{result['core_id']}")
                for result in results
            },
        )
        manifest_root = Path(__file__).resolve().parents[1] / "manifests"
        schema_names = (
            "full-release-plan.schema.json",
            "full-release-core-result.schema.json",
            "full-release-candidate.schema.json",
        )
        schemas = [
            json.loads((manifest_root / name).read_text(encoding="utf-8"))
            for name in schema_names
        ]
        for schema in schemas:
            self.assertIn("Structural interoperability schema only", schema["$comment"])
        registry = Registry()
        for schema in schemas:
            Draft202012Validator.check_schema(schema)
            registry = registry.with_resource(
                schema["$id"], Resource.from_contents(schema)
            )
        documents = (plan, results[0], candidate)
        for schema, document in zip(schemas, documents, strict=True):
            Draft202012Validator(schema, registry=registry).validate(document)

    def test_plan_matrix_result_and_candidate_preserve_mixed_markers(self) -> None:
        plan = track_plan()
        self.assertEqual(
            actions_matrix_for_plan(plan),
            {
                "include": [
                    {"core_id": "alpha", "group_tag": GROUP_TAG},
                    {"core_id": "beta", "group_tag": GROUP_TAG},
                ]
            },
        )
        plan_file_sha256 = document_file_sha256(plan)
        results = []
        result_hashes = {}
        for row in plan["cores"]:
            core_id = row["core_id"]
            result = construct_core_result(
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                core_id=core_id,
                runner_selector="local",
                e2e=normalized_e2e(plan, core_id, "local"),
            )
            self.assertEqual(result["core_group"], row["core_group"])
            validate_core_result(
                result,
                plan=plan,
                plan_file_sha256=plan_file_sha256,
                runner_selector="local",
            )
            results.append(result)
            result_hashes[core_id] = sha256(f"result-file:{core_id}")

        candidate = construct_release_candidate(
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector="local",
            results=results,
            result_file_sha256_by_core=result_hashes,
        )
        self.assertEqual(candidate["group"], plan["group"])
        self.assertEqual(
            [asset["core_group"]["selected_state"] for asset in candidate["assets"]],
            ["stable", "unstable_fallback"],
        )
        for asset, row in zip(candidate["assets"], plan["cores"], strict=True):
            self.assertEqual(asset["core_group"], core_group_marker(row["core_group"]))
        validate_release_candidate(
            candidate,
            plan=plan,
            plan_file_sha256=plan_file_sha256,
            runner_selector="local",
        )

    def test_group_identity_and_exact_package_are_semantic(self) -> None:
        plan = track_plan()
        changed_group = copy.deepcopy(plan)
        changed_group["group"]["track_registry"]["content_sha256"] = sha256(
            "drifted-track-registry"
        )
        from scripts.core_pipeline_lib.release import release_plan_content_sha256

        changed_group["content_sha256"] = release_plan_content_sha256(changed_group)
        self.assertNotEqual(changed_group["content_sha256"], plan["content_sha256"])

        projected = copy.deepcopy(plan)
        projected["cores"][0]["core_group"]["expected_outputs"]["package"][
            "comparison"
        ] = "not_applicable_projected_architectures"
        projected["content_sha256"] = release_plan_content_sha256(projected)
        with self.assertRaisesRegex(PipelineError, "comparison must be exact"):
            construct_release_plan(
                candidate_id="projected-v1",
                scope="track-group",
                repository=repository_facts(),
                cores=projected["cores"],
                group=group_facts(),
            )

        source_drift = copy.deepcopy(plan)
        source_drift["cores"][0]["source"]["tree"] = "f" * 40
        source_drift["content_sha256"] = release_plan_content_sha256(source_drift)
        with self.assertRaisesRegex(PipelineError, "execution source differs"):
            construct_release_plan(
                candidate_id="source-drift-v1",
                scope="track-group",
                repository=repository_facts(),
                cores=source_drift["cores"],
                group=group_facts(),
            )


if __name__ == "__main__":
    unittest.main()
