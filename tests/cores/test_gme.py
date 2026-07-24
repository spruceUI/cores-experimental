"""Focused gme catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import gme

from .support import ROOT, load_document


CORE_ID = "gme"
SOURCE_URL = "https://github.com/libretro/libretro-gme.git"
SOURCE_COMMIT = "818629a9fbb9f99bd9c585395318834ae5c6434e"
SOURCE_TREE = "dd10fdad6ccd383a7fa163ac76ad3d952e9842a5"
SELECTED_RUN = "actions-sim-build-core-gme-v1"
REPRODUCTION_RUN = "build-core-gme-local-v1"


class GmeManifestTests(unittest.TestCase):
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
        self.assertEqual("libretro-gme", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(gme.gme_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(gme.gme_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core gme", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class GmeCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/gme.json"
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
            (ROOT / "manifests/compatibility/pending/gme.json").exists()
        )


class GmeContractTests(unittest.TestCase):
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
                    gme.gme_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the gme contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local gme build logs present")

    def test_contract_rejects_a_wrong_language_count(self) -> None:
        import dataclasses

        from core_pipeline_lib.contracts.mixed_language import (
            mixed_language_log_proves_contract,
        )

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local gme build log present")
        tampered = dataclasses.replace(
            gme.GME_LOG_CONTRACT,
            expected_language_counts={"cxx": 47, "c": 31},
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
