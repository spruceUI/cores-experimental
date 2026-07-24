"""Focused Flycast (direct-cmake, GLES-per-ABI, submodule overlay) tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, load_document


CORE_ID = "flycast"


class FlycastManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_pins_the_v26_tag_and_reviewed_flags(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-cmake", build["driver"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertEqual("refs/tags/v2.6", self.spec["source"]["requested_ref"])
        self.assertEqual(1767792512, build["source_date_epoch"])
        defines = build["cmake"]["defines"]
        # the reviewed dependency-minimizing set: no Vulkan on any target
        # device, libgomp unproven on devices, bundled libzip
        self.assertEqual("ON", defines["LIBRETRO"])
        self.assertEqual("OFF", defines["USE_VULKAN"])
        self.assertEqual("OFF", defines["USE_OPENMP"])
        self.assertEqual("OFF", defines["USE_HOST_LIBZIP"])

    def test_gles_selection_is_per_architecture(self) -> None:
        systems = self.spec["build"]["cmake"]["systems"]
        self.assertEqual({"USE_GLES": "ON"}, systems["arm64"]["defines"])
        self.assertEqual({"USE_GLES2": "ON"}, systems["armhf"]["defines"])
        for arch, gles in (("arm64", "USE_GLES"), ("armhf", "USE_GLES2")):
            contract = pipeline.direct_cmake_contract_for_target(self.spec, arch)
            assert contract is not None
            self.assertEqual("ON", contract["cmake"]["defines"][gles])
            # the per-arch define merges over the common set
            self.assertEqual("ON", contract["cmake"]["defines"]["LIBRETRO"])
            # the projected system keeps the exact target identity only
            self.assertEqual(
                {"name", "processor"}, set(contract["cmake"]["system"])
            )

    def test_armhf_overlay_is_submodule_owned(self) -> None:
        overlays = self.spec["build"]["overlays"]
        self.assertEqual(["armhf"], sorted(overlays))
        (overlay,) = overlays["armhf"]
        self.assertEqual("git-apply-v1", overlay["kind"])
        self.assertEqual("core/deps/libchdr", overlay["submodule_path"])
        self.assertTrue(
            overlay["source_path"].startswith(overlay["submodule_path"] + "/")
        )
        self.assertTrue((ROOT / overlay["patch_path"]).is_file())

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core flycast", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class FlycastCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/flycast.json"
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
            ["arm64", "armhf"], sorted(compatibility["targets"])
        )
        # the armhf build links GLES2 directly (unversioned soname); arm64
        # resolves GL at runtime and links no GL library
        armhf_needed = compatibility["targets"]["armhf"]["needed"]
        self.assertIn("libGLESv2.so", armhf_needed)
        arm64_needed = compatibility["targets"]["arm64"]["needed"]
        self.assertFalse(any("GL" in name for name in arm64_needed))
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/flycast.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
