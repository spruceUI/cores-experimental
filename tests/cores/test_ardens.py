"""Focused Ardens (direct-cmake, libretro-only defines) canonical-state tests."""

from __future__ import annotations

import unittest

from .support import pipeline

from .support import ROOT, load_document


CORE_ID = "ardens"


class ArdensManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_is_direct_cmake_with_libretro_only_defines(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-cmake", build["driver"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertEqual(
            "https://github.com/tiberiusbrown/Ardens.git",
            self.spec["source"]["url"],
        )
        # the load-bearing defines: without them CMake pulls the SDL/GL desktop
        # build (player/debugger) and configure fails on missing X/GL headers
        defines = build["cmake"]["defines"]
        self.assertEqual("1", defines["ARDENS_LIBRETRO"])
        self.assertEqual("0", defines["ARDENS_PLAYER"])
        self.assertEqual("0", defines["ARDENS_DEBUGGER"])
        self.assertEqual("0", defines["ARDENS_LLVM"])
        self.assertEqual("ardens_libretro", build["cmake"]["target"])

    def test_direct_cmake_contract_projects_the_defines(self) -> None:
        for arch in ("arm64", "armhf"):
            contract = pipeline.direct_cmake_contract_for_target(self.spec, arch)
            self.assertIsNotNone(contract)
            assert contract is not None
            self.assertEqual("1", contract["cmake"]["defines"]["ARDENS_LIBRETRO"])

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core ardens", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class ArdensCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/ardens.json"
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
        # libretro-only build: the SDL/GL desktop frontend is compiled out
        for arch in ("arm64", "armhf"):
            needed = compatibility["targets"][arch]["needed"]
            self.assertFalse(
                any("libGL" in n or "libEGL" in n or "libSDL" in n for n in needed)
            )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/ardens.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
