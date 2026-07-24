"""Focused KM parallel-n64 fork (direct-make, armhf GLES2, overlays) tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import km_parallel_n64_xtreme_amped_turbo as km

from .support import ROOT, load_document


CORE_ID = "km_parallel_n64_xtreme_amped_turbo"


class KmParallelN64ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_is_direct_make_with_the_reviewed_recipe(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-make", build["driver"])
        self.assertEqual(["armhf"], self.spec["targets"])
        self.assertEqual(
            "https://github.com/KMFDManic/parallel-n64.git",
            self.spec["source"]["url"],
        )
        self.assertEqual({"armhf": "unix"}, build["platforms"])
        self.assertEqual(
            ["WITH_DYNAREC=arm", "FORCE_GLES=1", "NOSSE=1"],
            build["make_args"],
        )
        # upstream's product name is staged under the core's canonical
        # artifact name — the km_duckswanstation rebrand rule
        self.assertEqual("parallel_n64_libretro.so", build["output_path"])
        self.assertEqual(
            "km_parallel_n64_xtreme_amped_turbo_libretro.so",
            build["artifact_name"],
        )
        # metadata is repo-pinned: no km_* entries exist in libretro-super
        self.assertIn("repo_path", self.spec["metadata"])

    def test_the_five_buildability_overlays_are_pinned(self) -> None:
        overlays = self.spec["build"]["overlays"]
        self.assertEqual(["armhf"], sorted(overlays))
        sources = [item["source_path"] for item in overlays["armhf"]]
        self.assertEqual(
            [
                "Makefile",
                "glide2gl/src/Glide64/glide64_rdp.c",
                "glide2gl/src/Glide64/rdp.h",
                "libretro-common/include/glsm/glsm.h",
                "mupen64plus-video-angrylion-thr/parallel_al.cpp",
            ],
            sources,
        )
        for item in overlays["armhf"]:
            self.assertEqual("git-apply-v1", item["kind"])
            self.assertTrue((ROOT / item["patch_path"]).is_file())

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core km_parallel_n64_xtreme_amped_turbo", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class KmParallelN64CompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = (
            ROOT / "manifests/compatibility/km_parallel_n64_xtreme_amped_turbo.json"
        )
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
        self.assertIn(
            "libGLESv2.so", compatibility["targets"]["armhf"]["needed"]
        )
        self.assertFalse(
            (
                ROOT
                / "manifests/compatibility/pending/km_parallel_n64_xtreme_amped_turbo.json"
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
