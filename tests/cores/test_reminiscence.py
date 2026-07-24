"""Focused reminiscence catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import reminiscence

from .support import ROOT, load_document


CORE_ID = "reminiscence"
SOURCE_URL = "https://github.com/libretro/REminiscence.git"
SOURCE_COMMIT = "b0eb4ff6479d3a0f9e327ba595533604713cdb27"
SOURCE_TREE = "f5fef5de7e6213d6512b8a6036e21f93f237e985"
SELECTED_RUN = "actions-sim-build-core-reminiscence-v1"
REPRODUCTION_RUN = "build-core-reminiscence-local-v1"


class ReminiscenceManifestTests(unittest.TestCase):
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
        self.assertEqual("libretro-reminiscence", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(reminiscence.reminiscence_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(reminiscence.reminiscence_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core reminiscence", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class ReminiscenceCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/reminiscence.json"
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
            (ROOT / "manifests/compatibility/pending/reminiscence.json").exists()
        )


class ReminiscenceContractTests(unittest.TestCase):
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
                    reminiscence.reminiscence_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the reminiscence contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local reminiscence build logs present")

    def test_contract_rejects_a_wrong_language_count(self) -> None:
        import dataclasses

        from core_pipeline_lib.contracts.mixed_language import (
            mixed_language_log_proves_contract,
        )

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local reminiscence build log present")
        tampered = dataclasses.replace(
            reminiscence.REMINISCENCE_LOG_CONTRACT,
            expected_language_counts={"cxx": 31, "c": 10},
        )
        self.assertFalse(
            mixed_language_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
