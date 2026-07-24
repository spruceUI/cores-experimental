"""Focused FFmpeg (portable, make-variable) canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, load_document


CORE_ID = "ffmpeg"


class FfmpegCompatibilityTests(unittest.TestCase):
    def test_catalog_is_portable_make_variable_build(self) -> None:
        catalog = load_document(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][CORE_ID]
        # ARCH_* disabled => portable pure-C build (no architecture assembly).
        self.assertEqual(
            {
                "ARCH_AARCH64": 0,
                "ARCH_ARM": 0,
                "ARCH_X86": 0,
                "ARCH_X86_64": 0,
                "HAVE_SSA": 0,
                "LIBRETRO_EMBED_FFMPEG": 1,
                "OPENGL": 0,
            },
            spec["build"]["make_variables"],
        )

    def test_makeflags_force_deterministic_parallel_output(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][CORE_ID]
        # The reproduction log is only stable because parallel make output is
        # synchronized per recipe; the MAKEFLAGS carry --output-sync.
        self.assertTrue(
            pipeline.canonical_makeflags(spec).startswith(
                "--output-sync=recurse "
            )
        )

    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/ffmpeg.json"
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
            {"arm64", "armhf"}, set(compatibility["targets"].keys())
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/ffmpeg.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
