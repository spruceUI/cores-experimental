"""Focused SwanStation arm64-only canonical-state tests."""

from __future__ import annotations

import unittest

from .support import pipeline

from .support import ROOT, load_document


CORE_ID = "swanstation"


class SwanstationCompatibilityTests(unittest.TestCase):
    def test_catalog_is_arm64_only(self) -> None:
        catalog = load_document(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][CORE_ID]
        # The spruceOS-shipped armhf baseline is invalid (ELF64) and armhf is
        # not consumed on device views, so swanstation is an arm64-only core.
        self.assertEqual(["arm64"], spec["targets"])
        self.assertEqual({"arm64"}, set(spec["build"]["cmake"]["systems"]))

    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/swanstation.json"
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
        self.assertEqual(["arm64"], list(compatibility["targets"].keys()))
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/swanstation.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
