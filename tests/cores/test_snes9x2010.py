"""Focused Snes9x 2010 catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import snes9x2010

from .support import ROOT, load_document


CORE_ID = "snes9x2010"
SOURCE_URL = "https://github.com/libretro/snes9x2010.git"
SOURCE_COMMIT = "33077919157b990578011d2cce462e58c9e5c985"
SOURCE_TREE = "b1ce4512418a0629442c9dad0f1341600c6a6b43"
SELECTED_RUN = "actions-sim-build-core-snes9x2010-w3"
REPRODUCTION_RUN = "build-core-snes9x2010-local-w3"


class Snes9x2010ManifestTests(unittest.TestCase):
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
        self.assertEqual(
            {
                "driver": "libretro-super",
                "source_key": CORE_ID,
                "source_dir": "libretro-snes9x2010",
                "output_path": "dist/unix/snes9x2010_libretro.so",
                "artifact_name": "snes9x2010_libretro.so",
            },
            self.spec["build"],
        )
        self.assertNotIn("make_variables", self.spec["build"])
        self.assertNotIn("recipe_profile", self.spec["build"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(snes9x2010.snes9x2010_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(snes9x2010.snes9x2010_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertIn("--runner-profile github-actions", workflow)
        self.assertIn("--core snes9x2010", workflow)
        # The fail-open patterns must be gone.
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class Snes9x2010CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/snes9x2010.json"
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
            (
                ROOT / "manifests/compatibility/pending/snes9x2010.json"
            ).exists()
        )
        # C-only core: no libstdc++ dependency, clears every device ceiling.
        for arch in ("arm64", "armhf"):
            self.assertNotIn(
                "libstdc++.so.6", compatibility["targets"][arch]["needed"]
            )


class Snes9x2010ContractTests(unittest.TestCase):
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
                    snes9x2010.snes9x2010_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the Snes9x 2010 contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local Snes9x 2010 build logs present")

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        import dataclasses

        from core_pipeline_lib.contracts.c_only import (
            c_only_log_proves_contract,
        )

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local Snes9x 2010 build log present")
        # The dataclass is frozen; a modified copy must be rejected.
        tampered = dataclasses.replace(
            snes9x2010.SNES9X2010_LOG_CONTRACT, expected_compile_count=999
        )
        self.assertFalse(
            c_only_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
