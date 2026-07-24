"""Focused TIC-80 (direct-cmake, source_subdir + defines) canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, load_document


CORE_ID = "tic80"


class Tic80ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_is_direct_cmake_with_source_subdir_and_defines(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-cmake", build["driver"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertEqual(
            "https://github.com/libretro/TIC-80.git", self.spec["source"]["url"]
        )
        self.assertEqual("bin/tic80_libretro.so", build["output_path"])
        cmake = build["cmake"]
        # the load-bearing extensions: CMake source is the `core` submodule and
        # the reviewed defines select the libretro-only build (no SDL/player)
        self.assertEqual("core", cmake["source_subdir"])
        self.assertEqual("OFF", cmake["defines"]["BUILD_SDL"])
        self.assertEqual("ON", cmake["defines"]["BUILD_LIBRETRO"])

    def test_direct_cmake_contract_projects_the_extensions(self) -> None:
        contract = pipeline.direct_cmake_contract_for_target(self.spec, "arm64")
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("core", contract["cmake"]["source_subdir"])
        self.assertIn("BUILD_LIBRETRO", contract["cmake"]["defines"])

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core tic80", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)


class Tic80CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/tic80.json"
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
        # a fantasy console: CPU-rendered, links no graphics libs
        for arch in ("arm64", "armhf"):
            needed = compatibility["targets"][arch]["needed"]
            self.assertFalse(
                any("libGL" in n or "libEGL" in n or "libvulkan" in n for n in needed)
            )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/tic80.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
