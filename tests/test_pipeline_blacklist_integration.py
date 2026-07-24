#!/usr/bin/env python3

from __future__ import annotations

import argparse
from contextlib import nullcontext
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "core_pipeline.py"
SPEC = importlib.util.spec_from_file_location("core_pipeline_blacklist", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)

from core_pipeline_lib.policy import admission  # noqa: E402
from core_pipeline_lib.policy.blacklist import (  # noqa: E402
    commit_blacklist_content_sha256,
    parse_commit_blacklist,
)


CATALOG_PATH = ROOT / "manifests" / "core-builds.json"


def active_blacklist(core_id: str, source: dict) -> object:
    document = {
        "$schema": "../manifests/core-commit-blacklist.schema.json",
        "schema_version": 1,
        "policy_id": "core-commit-blacklist-v1",
        "local_only": True,
        "publication": "disabled",
        "entries": [
            {
                "core_id": core_id,
                "source_url": source["url"],
                "commit": source["commit"],
                "disposition": "active",
                "reason": "Focused integration-test block.",
                "evidence": ["tests/test_pipeline_blacklist_integration.py"],
            }
        ],
        "content_sha256": "0" * 64,
    }
    document["content_sha256"] = commit_blacklist_content_sha256(document)
    return parse_commit_blacklist(document)


class PipelineBlacklistIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(CATALOG_PATH)
        self.core_id = "gambatte"
        self.source = self.catalog["cores"][self.core_id]["source"]
        self.blacklist = active_blacklist(self.core_id, self.source)

    def policy_patch(self):
        return mock.patch.object(
            admission,
            "load_catalog_commit_blacklist",
            return_value=(self.blacklist, ROOT / "policies/core-commit-blacklist.json"),
        )

    def test_catalog_binds_exact_policy_file_and_content_identity(self) -> None:
        blacklist, path = pipeline.load_catalog_commit_blacklist(self.catalog)
        reference = self.catalog["commit_blacklist"]

        self.assertEqual(ROOT / reference["path"], path)
        self.assertEqual(reference["file_sha256"], pipeline.sha256_file(path))
        self.assertEqual(reference["content_sha256"], blacklist.content_sha256)
        self.assertIn(
            "source_commit_not_actively_blacklisted",
            self.catalog["policy"]["promotion_requires"],
        )

        for field in ("file_sha256", "content_sha256"):
            changed = copy.deepcopy(self.catalog)
            changed["commit_blacklist"][field] = "0" * 64
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "commit_blacklist"
                ):
                    pipeline.validate_catalog(changed)

    def test_exact_active_identity_blocks_while_each_near_miss_is_eligible(self) -> None:
        with self.policy_patch():
            with self.assertRaisesRegex(
                pipeline.PipelineError, "actively blacklisted"
            ):
                pipeline.require_catalog_cores_eligible(
                    self.catalog, [self.core_id]
                )

            near_misses = (
                (
                    "gambatte_alt",
                    self.source,
                ),
                (
                    self.core_id,
                    {
                        **self.source,
                        "url": "https://github.com/libretro/gambatte-fork.git",
                    },
                ),
                (
                    self.core_id,
                    {**self.source, "commit": "1" + self.source["commit"][1:]},
                ),
            )
            reports = pipeline.require_source_commits_eligible(
                self.catalog, near_misses
            )
        self.assertEqual(3, len(reports))
        self.assertTrue(all(report.eligible for report in reports))

    def test_build_and_all_runner_profiles_block_before_output_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_output = root / "build"
            with mock.patch.object(
                pipeline,
                "require_catalog_cores_eligible",
                side_effect=pipeline.PipelineError("actively blacklisted"),
            ), mock.patch.object(
                pipeline, "verify_image", side_effect=AssertionError("image checked")
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "actively blacklisted"
                ):
                    pipeline.perform_build(
                        catalog_path=CATALOG_PATH,
                        catalog=self.catalog,
                        core_id=self.core_id,
                        arch="arm64",
                        output_dir=build_output,
                    )
            self.assertFalse(build_output.exists())

            for profile in ("local", "github-actions-sim", "github-actions"):
                output_root = root / profile
                args = argparse.Namespace(
                    catalog=CATALOG_PATH,
                    core=self.core_id,
                    arch=None,
                    output_root=output_root,
                    run_id=f"blocked-{profile}",
                    runner_profile=profile,
                    fail_fast=False,
                )
                with self.subTest(profile=profile), mock.patch.object(
                    pipeline,
                    "require_catalog_cores_eligible",
                    side_effect=pipeline.PipelineError("actively blacklisted"),
                ):
                    with self.assertRaisesRegex(
                        pipeline.PipelineError, "actively blacklisted"
                    ):
                        pipeline.cmd_e2e(args)
                self.assertFalse(output_root.exists())

    def test_promotion_and_pin_composition_gate_before_state_creation(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as record_directory:
            root = Path(record_directory)
            runs = root / "runs"
            nightlies = root / "nightlies"
            record_path = runs / "blocked" / "build-record.json"
            record_path.parent.mkdir(parents=True)
            record_path.write_text(
                json.dumps(
                    {
                        "core_id": self.core_id,
                        "source": {
                            **self.source,
                            "resolved_url": self.source["url"],
                            "resolved_commit": self.source["commit"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            golden_path = nightlies / "gambatte-candidate" / "golden.json"
            with mock.patch.object(
                pipeline, "DEFAULT_RUNS", runs
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline,
                "require_source_commits_eligible",
                side_effect=pipeline.PipelineError("actively blacklisted"),
            ), mock.patch.object(
                pipeline, "manifest_lock", side_effect=AssertionError("lock created")
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "actively blacklisted"
                ):
                    pipeline.promote_build_record(
                        golden_path,
                        record_path,
                        record_path.parent / "e2e-record.json",
                    )

        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            pins = root / "pins"
            selection = {
                "selection_sha256": "b" * 64,
                "targets": {
                    "arm64": {
                        "golden_record": {
                            "source": {
                                **self.source,
                                "resolved_url": self.source["url"],
                                "resolved_commit": self.source["commit"],
                            }
                        }
                    }
                },
            }
            semantic_id = pipeline.individual_core_semantic_id(
                self.core_id, selection
            )
            source_path = nightlies / semantic_id / "golden.json"
            source_path.parent.mkdir(parents=True)
            source_document = {
                "schema_version": 2,
                "core_id": self.core_id,
                "pin_id": "candidate-golden",
                "content_sha256": "c" * 64,
                "cores": {self.core_id: {}},
                "build_goldens": {self.core_id: {}},
            }
            source_path.write_text(json.dumps(source_document), encoding="utf-8")
            output_path = pins / f"{semantic_id}.json"
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "verify_local_store", return_value=[]
            ), mock.patch.object(
                pipeline, "complete_core_bundle", return_value=selection
            ), mock.patch.object(
                pipeline,
                "require_pin_sources_eligible",
                side_effect=pipeline.PipelineError("actively blacklisted"),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "actively blacklisted"
                ):
                    pipeline.compose_pin_set(
                        pin_id=semantic_id,
                        core_ids=[self.core_id],
                        source_paths=[source_path],
                        output_path=output_path,
                    )
            self.assertFalse(output_path.exists())

    def test_release_and_all_channel_kinds_gate_before_pointer_or_release(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            pins = root / "pins"
            releases = root / "releases"
            selection = {
                "selection_sha256": "b" * 64,
                "targets": {
                    "arm64": {
                        "golden_record": {
                            "source": {"commit": self.source["commit"]}
                        }
                    }
                },
            }
            semantic_id = pipeline.individual_core_semantic_id(
                self.core_id, selection
            )
            pin_path = pins / f"{semantic_id}.json"
            pin_path.parent.mkdir(parents=True)
            pin_path.write_text(
                json.dumps(
                    {
                        "pin_id": semantic_id,
                        "scope": [self.core_id],
                        "parent": None,
                        "sources": [
                            {
                                "path": (
                                    f".local-e2e/nightlies/{semantic_id}/golden.json"
                                )
                            }
                        ],
                        "cores": {
                            self.core_id: {
                                "decision": "select_source",
                                "source_index": 0,
                                "selection": selection,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_path = releases / semantic_id
            with mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ), mock.patch.object(
                pipeline,
                "validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "require_pin_sources_eligible",
                side_effect=pipeline.PipelineError("actively blacklisted"),
            ), mock.patch.object(
                pipeline, "manifest_lock", side_effect=AssertionError("lock created")
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "actively blacklisted"
                ):
                    pipeline.promote_local_release(pin_path, release_path)
            self.assertFalse(release_path.exists())

        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            roots = {
                "nightly": root / "nightlies",
                "pinned": root / "pins",
                "release": root / "releases",
            }
            for channel, target_root in roots.items():
                target = target_root / "target.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target_document = {}
                if channel == "nightly":
                    target_document = {
                        "schema_version": 2,
                        "core_id": self.core_id,
                        "cores": {self.core_id: {}},
                        "build_goldens": {self.core_id: {}},
                    }
                target.write_text(
                    json.dumps(target_document) + "\n",
                    encoding="utf-8",
                )
                derived = {
                    "kind": pipeline.CHANNEL_KINDS[channel],
                    "path": str(target.relative_to(ROOT)),
                    "id": "blocked-target",
                    "file_sha256": "a" * 64,
                    "content_sha256": "b" * 64,
                }
                with self.subTest(channel=channel), mock.patch.object(
                    pipeline, "DEFAULT_CHANNELS", channels
                ), mock.patch.object(
                    pipeline, "DEFAULT_NIGHTLIES", roots["nightly"]
                ), mock.patch.object(
                    pipeline, "DEFAULT_PIN_SET_DIR", roots["pinned"]
                ), mock.patch.object(
                    pipeline, "DEFAULT_RELEASES", roots["release"]
                ), mock.patch.object(
                    pipeline, "manifest_lock", return_value=nullcontext()
                ), mock.patch.object(
                    pipeline, "derive_channel_target", return_value=derived
                ), mock.patch.object(
                    pipeline,
                    "require_channel_target_sources_eligible",
                    side_effect=pipeline.PipelineError("actively blacklisted"),
                ):
                    with self.assertRaisesRegex(
                        pipeline.PipelineError, "actively blacklisted"
                    ):
                        pipeline.update_channel(
                            channel,
                            target,
                            core_id=self.core_id,
                            expect_absent=True,
                        )
                self.assertFalse(
                    (channels / f"{channel}.{self.core_id}.json").exists()
                )

    def test_new_recipe_snapshot_binds_policy_while_legacy_recipe_remains_valid(self) -> None:
        spec = self.catalog["cores"]["handy"]
        recipe = pipeline.recipe_record(CATALOG_PATH, "handy", spec)
        source = {
            **spec["source"],
            "resolved_commit": spec["source"]["commit"],
            "resolved_url": spec["source"]["url"],
            "submodules": [],
        }
        record = {
            "core_id": "handy",
            "architecture": "arm64",
            "source": source,
            "recipe": recipe,
            "toolchain": {
                **self.catalog["toolchains"]["arm64"],
                "resolved_image_id": self.catalog["toolchains"]["arm64"]["image_id"],
                "resolver_digests": self.catalog["resolver"],
            },
            "build": {
                **pipeline.normalized_build_contract(spec, "arm64"),
                "log": "build.log",
                "log_sha256": "0" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "recipe.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            snapshot = pipeline.load_json(snapshot_path)
            reference = recipe["commit_blacklist"]

            self.assertEqual(9, snapshot["schema_version"])
            self.assertIn(reference["path"], snapshot["files"])
            self.assertEqual(
                reference["file_sha256"],
                snapshot["files"][reference["path"]]["sha256"],
            )
            self.assertEqual(
                [], pipeline.verify_recipe_snapshot(snapshot_path, record, "new")
            )

            for mutation in ("missing", "malformed"):
                with self.subTest(mutation=mutation):
                    crafted_record = copy.deepcopy(record)
                    if mutation == "missing":
                        crafted_record["recipe"].pop("commit_blacklist")
                    else:
                        crafted_record["recipe"]["commit_blacklist"].pop(
                            "content_sha256"
                        )
                    with self.assertRaises(pipeline.PipelineError):
                        pipeline.recipe_snapshot(crafted_record)

                    crafted_snapshot = copy.deepcopy(snapshot)
                    crafted_snapshot["recipe"] = copy.deepcopy(
                        crafted_record["recipe"]
                    )
                    crafted_snapshot["files"].pop(reference["path"])
                    crafted_path = Path(directory) / f"crafted-{mutation}.json"
                    crafted_path.write_text(
                        json.dumps(crafted_snapshot, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    self.assertTrue(
                        any(
                            "schema-v9 recipe requires a valid commit blacklist binding"
                            in error
                            for error in pipeline.verify_recipe_snapshot(
                                crafted_path,
                                crafted_record,
                                f"crafted-{mutation}",
                            )
                        )
                    )

            legacy = copy.deepcopy(record)
            legacy["recipe"].pop("pipeline_bundle")
            legacy["recipe"].pop("commit_blacklist")
            self.assertNotEqual(
                pipeline.provenance_identity_sha256(record),
                pipeline.provenance_identity_sha256(legacy),
            )
            legacy_snapshot_path = Path(directory) / "legacy.json"
            legacy_snapshot_path.write_bytes(pipeline.recipe_snapshot(legacy))
            self.assertNotEqual(
                9, pipeline.load_json(legacy_snapshot_path)["schema_version"]
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    legacy_snapshot_path, legacy, "legacy"
                ),
            )

            tampered = copy.deepcopy(snapshot)
            tampered["files"][reference["path"]]["text"] += "\n"
            snapshot_path.write_text(
                json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(
                any(
                    "commit-blacklist.json" in error
                    or "commit blacklist" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, record, "tampered"
                    )
                )
            )

if __name__ == "__main__":
    unittest.main()
