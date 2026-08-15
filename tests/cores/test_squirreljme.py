"""Focused SquirrelJME (direct-cmake nanocoat, armhf-only) canonical tests."""

from __future__ import annotations

import unittest

from .support import pipeline

from .support import ROOT, load_document


CORE_ID = "squirreljme"


class SquirreljmeManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_is_direct_cmake_from_the_nanocoat_subdir(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-cmake", build["driver"])
        # shipped armhf-only; matches the SpruceOS baseline
        self.assertEqual(["armhf"], self.spec["targets"])
        self.assertEqual(
            "https://github.com/SquirrelJME/SquirrelJME.git",
            self.spec["source"]["url"],
        )
        cmake = build["cmake"]
        self.assertEqual("nanocoat", cmake["source_subdir"])
        self.assertEqual("squirreljme_libretro", cmake["target"])
        # the load-bearing define: the libretro frontend defaults OFF under
        # cross configuration, so without it no libretro target exists
        self.assertEqual(
            "ON", cmake["defines"]["SQUIRRELJME_ENABLE_FRONTEND_LIBRETRO"]
        )
        self.assertEqual(["armhf"], sorted(cmake["systems"]))
        self.assertEqual(1784151532, build["source_date_epoch"])

    def test_overlays_pin_the_host_tools_and_arm32_fix(self) -> None:
        overlays = self.spec["build"]["overlays"]
        self.assertEqual(["armhf"], sorted(overlays))
        by_source = {item["source_path"]: item for item in overlays["armhf"]}
        self.assertEqual(
            {
                # one-token upstream fix: the ARM32 elseif omits a trailing OR
                "nanocoat/cmake/system-map.cmake",
                # configure-time utilities must be HOST tools: CMake forwards
                # the cross compiler into their make, and the cross-built
                # binary cannot execute during configure
                "nanocoat/cmake/utils/decode/Makefile",
                "nanocoat/cmake/utils/sourceize/Makefile",
            },
            set(by_source),
        )
        for item in by_source.values():
            self.assertEqual("git-apply-v1", item["kind"])
            self.assertTrue((ROOT / item["patch_path"]).is_file())

    def test_direct_cmake_contract_projects_the_define(self) -> None:
        contract = pipeline.direct_cmake_contract_for_target(self.spec, "armhf")
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "ON",
            contract["cmake"]["defines"]["SQUIRRELJME_ENABLE_FRONTEND_LIBRETRO"],
        )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core squirreljme", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class SquirreljmeCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/squirreljme.json"
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
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/squirreljme.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
