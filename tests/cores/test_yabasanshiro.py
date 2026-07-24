"""Focused YabaSanshiro (direct-make, generic GLES3, arm64-only) tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import yabasanshiro

from .support import ROOT, load_document


CORE_ID = "yabasanshiro"


class YabasanshiroManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_is_direct_make_with_the_generic_gles3_platform(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-make", build["driver"])
        # one generic build supersedes the three shipped device-tuned
        # variants (plain/_a133p link PowerVR internals, _smartpros links
        # the Mali blob); shipped and built arm64-only
        self.assertEqual(["arm64"], self.spec["targets"])
        self.assertEqual(
            "refs/heads/yabasanshiro", self.spec["source"]["requested_ref"]
        )
        self.assertEqual("yabause/src/libretro", build["make_subdir"])
        # the libretro-super driver cannot deliver this platform: its build
        # script hardcodes platform=unix on the make command line
        self.assertEqual(
            {"arm64": "arm64_cortex_a53_gles3"}, build["platforms"]
        )
        self.assertTrue(
            yabasanshiro.yabasanshiro_spec_is_well_formed(self.spec)
        )

    def test_registered_contract_pins_the_gles_link(self) -> None:
        contract = yabasanshiro.YABASANSHIRO_LOG_CONTRACT
        self.assertEqual({"arm64": 83}, dict(contract.expected_c_compile_count))
        self.assertEqual(
            {"arm64": 6}, dict(contract.expected_cxx_compile_count)
        )
        self.assertEqual(
            {"arm64": 1}, dict(contract.expected_asm_compile_count)
        )
        self.assertIn("-lGLESv2", contract.expected_link_options["arm64"])
        # the yabause tree names objects `<source>.o` (osdcore.c.o), the
        # opt-in the pairing sha256s make safe to admit
        self.assertTrue(contract.source_suffixed_object_names)

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core yabasanshiro", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class YabasanshiroCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/yabasanshiro.json"
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
        # the generic build links only the VERSIONED GLES soname, present on
        # every probed arm64 device family — the vendor stacks are not needed
        self.assertIn(
            "libGLESv2.so.2", compatibility["targets"]["arm64"]["needed"]
        )
        self.assertFalse(
            any(
                "mali" in name or "IMGegl" in name or "srv_um" in name
                for name in compatibility["targets"]["arm64"]["needed"]
            )
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/yabasanshiro.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
