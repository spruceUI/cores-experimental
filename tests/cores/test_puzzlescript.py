"""Focused puzzlescript catalog, workflow, contract, and submodule tests."""

from __future__ import annotations

import dataclasses
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import puzzlescript
from core_pipeline_lib.contracts.mixed_language import (
    mixed_language_log_proves_contract,
)

from .support import ROOT, load_document


CORE_ID = "puzzlescript"
SOURCE_URL = "https://github.com/nwhitehead/pzretro.git"
SOURCE_COMMIT = "6d859b47092f585a7ec05804c1d51a1676a06531"
SOURCE_TREE = "5e215b3f00ceba47f14b81c0b67d6a3d879a08af"
SELECTED_RUN = "actions-sim-build-core-puzzlescript-v1"
REPRODUCTION_RUN = "build-core-puzzlescript-local-v1"


class PuzzlescriptManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_recipe_with_top_level_submodules(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/main",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual(
            "libretro-puzzlescript", self.spec["build"]["source_dir"]
        )
        # the load-bearing flag: recursive fetch descends into quickjs-ng's
        # unresolvable test262 submodule, so this core fetches top-level only
        self.assertFalse(self.spec["build"]["recursive_submodules"])
        self.assertFalse(pipeline.spec_submodules_recursive(self.spec))
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(
            puzzlescript.puzzlescript_spec_is_well_formed(self.spec)
        )
        # dropping the submodule flag must not validate
        mutated = {
            **self.spec,
            "build": {
                k: v
                for k, v in self.spec["build"].items()
                if k != "recursive_submodules"
            },
        }
        self.assertFalse(
            puzzlescript.puzzlescript_spec_is_well_formed(mutated)
        )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core puzzlescript", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class PuzzlescriptCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/puzzlescript.json"
        compatibility = load_document(compatibility_path)
        report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual("valid", report["status"], report["errors"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/puzzlescript.json").exists()
        )


class PuzzlescriptContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    puzzlescript.puzzlescript_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local puzzlescript build logs present")

    def test_contract_rejects_a_wrong_language_count(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local puzzlescript build log present")
        tampered = dataclasses.replace(
            puzzlescript.PUZZLESCRIPT_LOG_CONTRACT,
            expected_language_counts={"c": 5, "cxx": 12},
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
