#!/usr/bin/env python3

"""Mutation and malformed-input boundaries for the per-core lifecycle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry


ROOT = Path(__file__).resolve().parents[1]


class PerCoreLifecycleTests(unittest.TestCase):
    def assert_tranche_free(self, value: object, label: str) -> None:
        self.assertIsInstance(value, str, f"{label} must be a string")
        assert isinstance(value, str)
        self.assertNotIn(
            "tranche",
            value.casefold(),
            f"{label} must not use tranche naming: {value}",
        )

    def test_canonical_compatibility_files_have_matching_core_owned_files(self) -> None:
        compatibility_directory = ROOT / "manifests" / "compatibility"
        for compatibility_path in sorted(compatibility_directory.glob("*.json")):
            with self.subTest(core=compatibility_path.stem):
                document = pipeline.load_json(compatibility_path)
                core_id = document["core_id"]
                self.assertEqual(core_id, compatibility_path.stem)
                pin_path = ROOT / document["golden_source"]
                self.assertTrue(pin_path.is_file())
                registry.composed_source_set(pin_path.stem)
                self.assertTrue(
                    (ROOT / "tests" / "cores" / f"test_{core_id}.py").is_file()
                )

    def test_canonical_lifecycle_files_are_one_core_semantic_and_tranche_free(
        self,
    ) -> None:
        compatibility_directory = ROOT / "manifests" / "compatibility"
        compatibility_paths = sorted(compatibility_directory.glob("*.json"))
        self.assertTrue(compatibility_paths)

        for compatibility_path in compatibility_paths:
            with self.subTest(core=compatibility_path.stem):
                compatibility = pipeline.load_json(compatibility_path)
                core_id = compatibility["core_id"]
                compatibility_relative = compatibility_path.relative_to(ROOT)
                self.assertEqual(core_id, compatibility_path.stem)
                self.assert_tranche_free(core_id, "canonical core ID")
                self.assert_tranche_free(
                    compatibility_relative.as_posix(),
                    "canonical compatibility path",
                )

                pin_relative = compatibility["golden_source"]
                self.assertIsInstance(pin_relative, str)
                assert isinstance(pin_relative, str)
                pin_reference = Path(pin_relative)
                self.assertFalse(pin_reference.is_absolute())
                self.assertEqual(
                    Path("pins/core-sets"),
                    pin_reference.parent,
                )
                self.assertEqual(".json", pin_reference.suffix)
                self.assert_tranche_free(pin_relative, "canonical pin path")
                pin_path = ROOT / pin_relative
                pin = pipeline.load_json(pin_path)
                pin_core_id, semantic_id = pipeline.require_individual_pin_identity(
                    pin,
                    pin_path=pin_path,
                )
                self.assertEqual(core_id, pin_core_id)
                self.assertRegex(
                    semantic_id,
                    rf"^{core_id}-[0-9a-f]{{12}}-[0-9a-f]{{12}}$",
                )
                self.assertRegex(
                    compatibility["source_commit"],
                    r"^[0-9a-f]{40}$",
                )
                self.assertTrue(
                    semantic_id.startswith(
                        f"{core_id}-{compatibility['source_commit'][:12]}-"
                    )
                )
                self.assertEqual(
                    f"pins/core-sets/{semantic_id}.json",
                    pin_relative,
                )
                self.assertEqual([core_id], pin["scope"])
                self.assertEqual({core_id}, set(pin["cores"]))
                self.assert_tranche_free(semantic_id, "canonical semantic ID")

                nightly_relative = pin["sources"][0]["path"]
                self.assertEqual(
                    f".local-e2e/nightlies/{semantic_id}/golden.json",
                    nightly_relative,
                )
                self.assert_tranche_free(
                    nightly_relative,
                    "canonical nightly path",
                )

                source_set_relative = (
                    f"pins/source-sets/{semantic_id}.json"
                )
                source_set = registry.composed_source_set(semantic_id)
                self.assertEqual(semantic_id, source_set["source_set_id"])
                self.assertEqual({core_id}, set(source_set["sources"]))
                self.assertEqual(
                    {
                        "path": pin_relative,
                        "pin_id": semantic_id,
                    },
                    {
                        key: source_set["evidence_pin"][key]
                        for key in ("path", "pin_id")
                    },
                )
                self.assert_tranche_free(
                    source_set_relative,
                    "canonical source-set path",
                )
                self.assert_tranche_free(
                    source_set["source_set_id"],
                    "canonical source-set ID",
                )
                self.assert_tranche_free(
                    source_set["evidence_pin"]["path"],
                    "canonical source-set pin path",
                )
                self.assert_tranche_free(
                    source_set["evidence_pin"]["pin_id"],
                    "canonical source-set pin ID",
                )

                source_lock = source_set["sources"][core_id]
                self.assert_tranche_free(
                    source_lock["path"],
                    "canonical source-lock path",
                )
                self.assert_tranche_free(
                    source_lock["source_lock_id"],
                    "canonical source-lock ID",
                )

                # Selected and reproduction runs are immutable evidence. Their
                # historical IDs are deliberately outside this naming guard.
                for run_field in ("e2e_run", "reproduction_run"):
                    self.assertIsInstance(compatibility[run_field], str)

    def test_golden_validator_fails_closed_on_malformed_per_core_maps(self) -> None:
        for build_goldens in (
            {"handy": []},
            {"handy": {"arm64": []}},
        ):
            with self.subTest(build_goldens=build_goldens):
                report = pipeline.validate_golden_document(
                    {"build_goldens": build_goldens}
                )
                self.assertEqual("invalid", report["status"])
                self.assertTrue(
                    any("must be an object" in error for error in report["errors"]),
                    report["errors"],
                )

    def test_complete_core_bundle_fails_closed_on_malformed_nested_maps(self) -> None:
        malformed_records = (
            {"arm64": []},
            {"arm64": {"e2e": []}},
            {"arm64": {"e2e": {"build_records": []}}},
        )
        for records in malformed_records:
            with self.subTest(records=records), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.complete_core_bundle(
                    {"build_goldens": {"handy": records}},
                    "handy",
                )

    def test_release_validator_fails_closed_on_malformed_assets(self) -> None:
        pipeline.DEFAULT_RELEASES.mkdir(parents=True, exist_ok=True)
        pin = {
            "pin_id": "fixture",
            "content_sha256": "a" * 64,
            "scope": [],
            "cores": {},
        }
        for assets in (None, [None]):
            with self.subTest(assets=assets), tempfile.TemporaryDirectory(
                dir=pipeline.DEFAULT_RELEASES
            ) as directory:
                release_root = Path(directory)
                manifest = {
                    "schema_version": 1,
                    "release_id": release_root.name,
                    "local_only": True,
                    "publication": "disabled",
                    "pin": {
                        "pin_id": pin["pin_id"],
                        "content_sha256": pin["content_sha256"],
                        "file_sha256": "b" * 64,
                    },
                    "assets": assets,
                }
                manifest["content_sha256"] = pipeline.release_content_sha256(
                    manifest
                )
                (release_root / "release-manifest.json").write_text(
                    json.dumps(manifest),
                    encoding="utf-8",
                )
                report = pipeline._validate_local_release(
                    release_root,
                    pin,
                    "b" * 64,
                    manifest_document=manifest,
                )
                self.assertEqual("invalid", report["status"])
                self.assertTrue(
                    any("asset" in error for error in report["errors"]),
                    report["errors"],
                )

    def test_compose_core_golden_rejects_lexical_symlink_paths(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            nightlies.mkdir()
            actual_source = root / "source.json"
            actual_source.write_text("{}\n", encoding="utf-8")
            linked_source = root / "linked-source.json"
            linked_source.symlink_to(actual_source)
            output = nightlies / "fixture" / "golden.json"
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), self.assertRaisesRegex(pipeline.PipelineError, "symlink"):
                pipeline.compose_core_golden(
                    core_id="handy",
                    source_path=linked_source,
                    output_path=output,
                )

            actual_output = root / "actual-output.json"
            actual_output.write_text("{}\n", encoding="utf-8")
            output.parent.mkdir()
            output.symlink_to(actual_output)
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), self.assertRaisesRegex(pipeline.PipelineError, "symlink"):
                pipeline.compose_core_golden(
                    core_id="handy",
                    source_path=actual_source,
                    output_path=output,
                )

            linked_parent = nightlies / "linked-parent"
            actual_parent = root / "actual-parent"
            actual_parent.mkdir()
            linked_parent.symlink_to(actual_parent, target_is_directory=True)
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), self.assertRaisesRegex(pipeline.PipelineError, "symlink"):
                pipeline.compose_core_golden(
                    core_id="handy",
                    source_path=actual_source,
                    output_path=linked_parent / "golden.json",
                )

    def test_channel_target_rejects_lexical_symlink_paths(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            actual_parent = nightlies / "actual"
            actual_parent.mkdir(parents=True)
            actual_target = actual_parent / "golden.json"
            actual_target.write_text("{}\n", encoding="utf-8")

            linked_parent = nightlies / "linked-parent"
            linked_parent.symlink_to(actual_parent, target_is_directory=True)
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), self.assertRaisesRegex(pipeline.PipelineError, "symlink"):
                pipeline.derive_channel_target(
                    "nightly",
                    linked_parent / "golden.json",
                    core_id="handy",
                )

            linked_file_parent = nightlies / "linked-file"
            linked_file_parent.mkdir()
            linked_target = linked_file_parent / "golden.json"
            linked_target.symlink_to(actual_target)
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), self.assertRaisesRegex(pipeline.PipelineError, "symlink"):
                pipeline.derive_channel_target(
                    "nightly",
                    linked_target,
                    core_id="handy",
                )

    def test_individual_pin_inherits_immutable_source_timestamp(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            pins = root / "pins"
            semantic_id = "handy-aaaaaaaaaaaa-bbbbbbbbbbbb"
            source_path = nightlies / semantic_id / "golden.json"
            source_path.parent.mkdir(parents=True)
            output_path = pins / f"{semantic_id}.json"
            source = {
                "schema_version": 2,
                "core_id": "handy",
                "updated_at": "2026-01-02T03:04:05+00:00",
                "cores": {"handy": {}},
                "build_goldens": {"handy": {}},
            }
            source_path.write_text(
                json.dumps(source, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            selection = {
                "selection_sha256": "b" * 64,
                "targets": {
                    "arm64": {
                        "golden_record": {"source": {"commit": "a" * 40}}
                    }
                },
            }
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline, "load_json", return_value={"cores": {}}
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "verify_local_store", return_value=[]
            ), mock.patch.object(
                pipeline,
                "golden_source_reference",
                return_value={
                    "path": str(source_path.relative_to(ROOT)),
                },
            ), mock.patch.object(
                pipeline, "complete_core_bundle", return_value=selection
            ), mock.patch.object(
                pipeline,
                "_require_catalog_bound_source_candidate_selection",
                return_value=None,
            ), mock.patch.object(
                pipeline, "require_pin_sources_eligible"
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ):
                document = pipeline.compose_pin_set(
                    pin_id=semantic_id,
                    core_ids=["handy"],
                    source_paths=[source_path],
                    output_path=output_path,
                )

            self.assertEqual(source["updated_at"], document["created_at"])
            self.assertEqual(
                source["updated_at"],
                pipeline.load_json(output_path)["created_at"],
            )

    def test_active_handlers_reject_noncanonical_mutation_before_write(self) -> None:
        with mock.patch.object(
            pipeline,
            "update_channel",
            side_effect=AssertionError("aggregate update reached mutator"),
        ), self.assertRaisesRegex(pipeline.PipelineError, "requires --core"):
            pipeline.cmd_update_channel(
                argparse.Namespace(
                    channel="nightly",
                    target=Path("golden.json"),
                    expect_absent=True,
                    expect_current=None,
                    catalog=Path("catalog.json"),
                )
            )

        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            pins = root / "pins"
            releases = root / "releases"
            source = nightlies / "candidate" / "golden.json"
            source.parent.mkdir(parents=True)
            source.write_text("{}\n", encoding="utf-8")
            output = pins / "fixture.json"
            selection = {
                "selection_sha256": "b" * 64,
                "targets": {
                    "arm64": {
                        "golden_record": {"source": {"commit": "a" * 40}}
                    }
                },
            }
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline,
                "load_json",
                return_value={
                    "schema_version": 2,
                    "core_id": "handy",
                    "cores": {"handy": {}},
                    "build_goldens": {"handy": {}},
                },
            ), mock.patch.object(
                pipeline, "complete_core_bundle", return_value=selection
            ), mock.patch.object(
                pipeline,
                "compose_pin_set",
                side_effect=AssertionError("nonsemantic pin reached mutator"),
            ), self.assertRaisesRegex(pipeline.PipelineError, "semantic ID"):
                pipeline.cmd_compose_pin_set(
                    argparse.Namespace(
                        core="handy",
                        pin_id="fixture",
                        source_golden=source,
                        output=output,
                        catalog=Path("catalog.json"),
                    )
                )

            pin_path = pins / "aggregate.json"
            pin_path.parent.mkdir(parents=True, exist_ok=True)
            pin_path.write_text(
                json.dumps(
                    {
                        "pin_id": "aggregate",
                        "scope": ["handy", "stella2014"],
                        "cores": {"handy": {}, "stella2014": {}},
                        "parent": None,
                        "sources": [{}],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ), mock.patch.object(
                pipeline,
                "promote_local_release",
                side_effect=AssertionError("aggregate pin reached release mutator"),
            ), self.assertRaisesRegex(pipeline.PipelineError, "one parentless core"):
                pipeline.cmd_promote_release(
                    argparse.Namespace(
                        pin_set=pin_path,
                        output=releases / "aggregate",
                        catalog=Path("catalog.json"),
                    )
                )


if __name__ == "__main__":
    unittest.main()
