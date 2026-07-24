"""Focused retro8 catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import retro8

from .support import ROOT, load_document


CORE_ID = "retro8"
SOURCE_URL = "https://github.com/libretro/retro8.git"
SOURCE_COMMIT = "ddc06a142398ee9755894b3f0bb17c8dc428151d"
SOURCE_TREE = "b2d7603bffe84e98130bc62365d65d347d22521e"
SELECTED_RUN = "actions-sim-build-core-retro8-v1"
REPRODUCTION_RUN = "build-core-retro8-local-v1"


class Retro8ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual("libretro-retro8", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(retro8.retro8_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(retro8.retro8_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core retro8", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class Retro8CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/retro8.json"
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
            (ROOT / "manifests/compatibility/pending/retro8.json").exists()
        )


class Retro8ContractTests(unittest.TestCase):
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
                    retro8.retro8_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the retro8 contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local retro8 build logs present")

    def test_contract_rejects_a_wrong_language_count(self) -> None:
        import dataclasses

        from core_pipeline_lib.contracts.mixed_language import (
            mixed_language_log_proves_contract,
        )

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local retro8 build log present")
        tampered = dataclasses.replace(
            retro8.RETRO8_LOG_CONTRACT,
            expected_language_counts={"cxx": 11, "c": 33},
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
