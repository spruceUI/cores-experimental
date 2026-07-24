"""Focused uw8 catalog, workflow, contract, and canonical-state tests."""

from __future__ import annotations

import dataclasses
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import uw8
from core_pipeline_lib.contracts.c_only import c_only_log_proves_contract

from .support import ROOT, load_document


CORE_ID = "uw8"
SOURCE_URL = "https://github.com/libretro/uw8-libretro.git"
SOURCE_COMMIT = "92e0f7a7678de9955002ecce8501eb1be5e46d35"
SOURCE_TREE = "b0abb1ab7a2905e1f67df521a800014f7ca89fac"
SELECTED_RUN = "actions-sim-build-core-uw8-w3"
REPRODUCTION_RUN = "build-core-uw8-local-w3"


class Uw8ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_libretro_super_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/main",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual("libretro-uw8", self.spec["build"]["source_dir"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(uw8.uw8_spec_is_well_formed(self.spec))
        mutated = {**self.spec, "targets": ["arm64"]}
        self.assertFalse(uw8.uw8_spec_is_well_formed(mutated))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core uw8", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class Uw8CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/uw8.json"
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
        for arch in ("arm64", "armhf"):
            self.assertNotIn(
                "libstdc++.so.6", compatibility["targets"][arch]["needed"]
            )


class Uw8ContractTests(unittest.TestCase):
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
                    uw8.uw8_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the uw8 contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local uw8 build logs present")

    def test_contract_rejects_a_wrong_compile_count(self) -> None:
        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local uw8 build log present")
        tampered = dataclasses.replace(
            uw8.UW8_LOG_CONTRACT, expected_compile_count=99
        )
        self.assertFalse(
            c_only_log_proves_contract(
                log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE, tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
