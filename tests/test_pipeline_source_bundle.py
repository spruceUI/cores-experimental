#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
import core_pipeline_lib.source_bundle as source_bundle

ROOT = Path(__file__).resolve().parents[1]


class PipelineSourceBundleTests(unittest.TestCase):
    def _bundle_paths(self, root: Path) -> dict[str, Path]:
        return {
            "REPOSITORY_ROOT": root,
            "PIPELINE_LAUNCHER": root / "scripts" / "core_pipeline.py",
            "PIPELINE_PACKAGE_ROOT": root / "scripts" / "core_pipeline_lib",
        }

    def _write_minimal_pipeline(self, root: Path) -> None:
        paths = self._bundle_paths(root)
        paths["PIPELINE_PACKAGE_ROOT"].mkdir(parents=True)
        paths["PIPELINE_LAUNCHER"].write_text("# launcher\n", encoding="utf-8")
        (paths["PIPELINE_PACKAGE_ROOT"] / "__init__.py").write_text(
            '"""Package."""\n', encoding="utf-8"
        )

    def test_bundle_covers_launcher_and_every_package_module(self) -> None:
        bundle = pipeline.pipeline_source_bundle()
        expected = {"scripts/core_pipeline.py"}
        expected.update(
            str(path.relative_to(ROOT))
            for path in (ROOT / "scripts" / "core_pipeline_lib").rglob("*.py")
            if path.is_file() and not path.is_symlink()
        )
        self.assertEqual(expected, set(bundle["files"]))
        self.assertTrue(pipeline.pipeline_source_bundle_is_well_formed(bundle))
        for relative, digest in bundle["files"].items():
            self.assertEqual(pipeline.sha256_file(ROOT / relative), digest)

    def test_bundle_fails_closed_when_package_root_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._bundle_paths(root)
            paths["PIPELINE_LAUNCHER"].parent.mkdir(parents=True)
            paths["PIPELINE_LAUNCHER"].write_text("# launcher\n", encoding="utf-8")

            with mock.patch.multiple(source_bundle, **paths):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "pipeline package root does not exist"
                ):
                    pipeline.pipeline_source_bundle()

    def test_bundle_rejects_symlinked_python_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_pipeline(root)
            package_root = self._bundle_paths(root)["PIPELINE_PACKAGE_ROOT"]
            (package_root / "implementation.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            (package_root / "alias.py").symlink_to("implementation.py")

            with mock.patch.multiple(source_bundle, **self._bundle_paths(root)):
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "pipeline package entry must not traverse a symlink",
                ):
                    pipeline.pipeline_source_bundle()

    def test_bundle_rejects_uncontained_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "repository"
            outside = base / "outside" / "core_pipeline_lib"
            self._write_minimal_pipeline(root)
            outside.mkdir(parents=True)
            (outside / "__init__.py").write_text("# outside\n", encoding="utf-8")
            paths = self._bundle_paths(root)
            paths["PIPELINE_PACKAGE_ROOT"] = outside

            with mock.patch.multiple(source_bundle, **paths):
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "pipeline package root is outside the pipeline repository",
                ):
                    pipeline.pipeline_source_bundle()

    def test_fixture_bundle_inventory_and_hashes_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_pipeline(root)
            package_root = self._bundle_paths(root)["PIPELINE_PACKAGE_ROOT"]
            nested = package_root / "domain"
            nested.mkdir()
            (nested / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
            (nested / "README.txt").write_text("ignored\n", encoding="utf-8")

            with mock.patch.multiple(source_bundle, **self._bundle_paths(root)):
                bundle = pipeline.pipeline_source_bundle()

            self.assertEqual(
                {
                    "scripts/core_pipeline.py",
                    "scripts/core_pipeline_lib/__init__.py",
                    "scripts/core_pipeline_lib/domain/model.py",
                },
                set(bundle["files"]),
            )
            self.assertTrue(pipeline.pipeline_source_bundle_is_well_formed(bundle))
            for relative, digest in bundle["files"].items():
                self.assertEqual(pipeline.sha256_file(root / relative), digest)

    def test_bundle_rejects_digest_and_path_tampering(self) -> None:
        bundle = pipeline.pipeline_source_bundle()
        changed_digest = json.loads(json.dumps(bundle))
        changed_digest["files"]["scripts/core_pipeline.py"] = "0" * 64
        self.assertFalse(
            pipeline.pipeline_source_bundle_is_well_formed(changed_digest)
        )

        changed_path = json.loads(json.dumps(bundle))
        digest = changed_path["files"].pop("scripts/core_pipeline_lib/__init__.py")
        changed_path["files"]["scripts/elsewhere.py"] = digest
        changed_path["content_sha256"] = pipeline.pipeline_bundle_content_sha256(
            changed_path["files"]
        )
        self.assertFalse(pipeline.pipeline_source_bundle_is_well_formed(changed_path))

    def test_bundle_rejects_launcher_only_inventory(self) -> None:
        files = {"scripts/core_pipeline.py": "0" * 64}
        bundle = {
            "schema_version": 1,
            "files": files,
            "content_sha256": pipeline.pipeline_bundle_content_sha256(files),
        }
        self.assertFalse(pipeline.pipeline_source_bundle_is_well_formed(bundle))

    def test_new_recipe_snapshot_binds_the_complete_bundle(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        recipe = pipeline.recipe_record(catalog_path, "handy", catalog["cores"]["handy"])
        self.assertEqual(pipeline.pipeline_source_bundle(), recipe["pipeline_bundle"])
        spec = catalog["cores"]["handy"]
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
                "resolved_image_id": catalog["toolchains"]["arm64"]["image_id"],
                "dockerfile": catalog["toolchains"]["arm64"]["dockerfile"],
                "dockerfile_sha256": catalog["toolchains"]["arm64"][
                    "dockerfile_sha256"
                ],
                "resolver_digests": catalog["resolver"],
            },
            "build": {
                **pipeline.normalized_build_contract(spec, "arm64"),
                "log": "build.log",
                "log_sha256": "0" * 64,
            },
        }
        snapshot = json.loads(pipeline.recipe_snapshot(record))
        self.assertEqual(9, snapshot["schema_version"])
        self.assertTrue(set(recipe["pipeline_bundle"]["files"]) <= set(snapshot["files"]))

        missing_policy = json.loads(json.dumps(record))
        missing_policy["recipe"].pop("commit_blacklist")
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "schema-v9 recipe snapshot requires commit blacklist provenance",
        ):
            pipeline.recipe_snapshot(missing_policy)

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "recipe-snapshot.json"
            snapshot_path.write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(
                [], pipeline.verify_recipe_snapshot(snapshot_path, record, "fixture")
            )

            changed = json.loads(json.dumps(snapshot))
            changed["files"]["scripts/core_pipeline_lib/__init__.py"]["text"] += "# changed\n"
            snapshot_path.write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.assertIn(
                "recipe snapshot digest mismatch",
                "\n".join(
                    pipeline.verify_recipe_snapshot(snapshot_path, record, "fixture")
                ),
            )


if __name__ == "__main__":
    unittest.main()
