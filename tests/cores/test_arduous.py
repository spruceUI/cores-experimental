"""Focused Arduous (direct-cmake, both-arch) canonical-state tests."""

from __future__ import annotations

import unittest

from .support import pipeline

from .support import ROOT, load_document


CORE_ID = "arduous"


class ArduousManifestTests(unittest.TestCase):
    def test_catalog_is_direct_cmake_both_arch_with_submodule_source(self) -> None:
        catalog = load_document(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][CORE_ID]
        self.assertEqual("direct-cmake", spec["build"]["driver"])
        self.assertEqual(["arm64", "armhf"], spec["targets"])
        self.assertEqual(
            {"arm64", "armhf"}, set(spec["build"]["cmake"]["systems"])
        )
        self.assertEqual(
            "https://github.com/libretro/arduous.git", spec["source"]["url"]
        )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        catalog = load_document(ROOT / "manifests/core-builds.json")
        workflow = (
            ROOT / catalog["cores"][CORE_ID]["workflow"]
        ).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core arduous", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)

    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/arduous.json"
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
        self.assertEqual(
            ["arm64", "armhf"], list(compatibility["targets"].keys())
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/arduous.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
