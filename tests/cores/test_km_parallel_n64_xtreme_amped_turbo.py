"""Focused KM parallel-n64 fork (direct-make, armhf GLES2, overlays) tests."""

from __future__ import annotations

import copy
import unittest

from .support import pipeline
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
        self.assertEqual(
            km.KM_PARALLEL_N64_SOURCE_DATE_EPOCH,
            build["source_date_epoch"],
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

    def test_spec_guard_pins_the_timestamped_source_and_recipe(self) -> None:
        self.assertTrue(
            km.km_parallel_n64_spec_is_well_formed(self.spec)
        )
        without_epoch = copy.deepcopy(self.spec)
        del without_epoch["build"]["source_date_epoch"]
        self.assertFalse(
            km.km_parallel_n64_spec_is_well_formed(without_epoch)
        )
        drifted_epoch = copy.deepcopy(self.spec)
        drifted_epoch["build"]["source_date_epoch"] += 1
        self.assertFalse(
            km.km_parallel_n64_spec_is_well_formed(drifted_epoch)
        )
        drifted_source = copy.deepcopy(self.spec)
        drifted_source["source"]["tree"] = "0" * 40
        self.assertFalse(
            km.km_parallel_n64_spec_is_well_formed(drifted_source)
        )

    def test_catalog_guard_fails_closed_without_the_epoch(self) -> None:
        mutated_catalog = copy.deepcopy(self.catalog)
        del mutated_catalog["cores"][CORE_ID]["build"]["source_date_epoch"]
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "must preserve its exact timestamped direct-make",
        ):
            pipeline.validate_catalog(mutated_catalog)

    def test_driver_exports_and_proves_the_pinned_source_epoch(self) -> None:
        script = pipeline.container_build_script(
            CORE_ID,
            "armhf",
            self.spec,
            self.catalog["resolver"],
        )
        epoch = km.KM_PARALLEL_N64_SOURCE_DATE_EPOCH
        self.assertIn(f"export SOURCE_DATE_EPOCH={epoch}", script)
        self.assertIn("git -C /tmp/core-source show -s --format=%ct HEAD", script)
        self.assertIn(f'test "$actual_source_date_epoch" = {epoch}', script)

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
