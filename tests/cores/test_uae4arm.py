"""Focused UAE4ARM (armhf-only) canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import uae4arm

from .support import evidence_handles, ROOT, load_document


CORE_ID = "uae4arm"
_H = evidence_handles(CORE_ID)
SOURCE_COMMIT = "dafd48fad7510ebc2f90ebdee8331bbdcf65fd49"
SOURCE_TREE = "7d99605e9faecc7c154c30861ebee2a36b9fde18"
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]


class Uae4armManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_document(ROOT / "manifests/core-builds.json")[
            "cores"
        ][CORE_ID]

    def test_catalog_is_armhf_only(self) -> None:
        # The arm64 build fails to assemble the core's armv7 inline assembly,
        # so uae4arm is an armhf-only core.
        self.assertEqual(["armhf"], self.spec["targets"])
        self.assertTrue(uae4arm.uae4arm_spec_is_well_formed(self.spec))
        self.assertFalse(
            uae4arm.uae4arm_spec_is_well_formed(
                {**self.spec, "targets": ["arm64", "armhf"]}
            )
        )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core uae4arm", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)


class Uae4armCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_armhf_only(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/uae4arm.json"
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
        self.assertEqual(["armhf"], list(compatibility["targets"].keys()))


class Uae4armContractTests(unittest.TestCase):
    def _log(self, run_id: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / "armhf"
            / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_real_armhf_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            log = self._log(run_id)
            if log is None:
                continue
            self.assertTrue(
                uae4arm.uae4arm_log_proves_contract(
                    log, CORE_ID, "armhf", SOURCE_COMMIT, SOURCE_TREE
                ),
                f"{run_id}/armhf did not prove the UAE4ARM contract",
            )
            proven += 1
        if proven == 0:
            self.skipTest("no workspace-local UAE4ARM build logs present")


if __name__ == "__main__":
    unittest.main()
