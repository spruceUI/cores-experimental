"""Focused km_duckswanstation catalog, rename, repo-metadata, and state tests."""

from __future__ import annotations

import copy
import hashlib
import unittest

from .support import pipeline

from .support import ROOT, load_document


CORE_ID = "km_duckswanstation_xtreme_amped"
SOURCE_URL = "https://github.com/KMFDManic/swanstation.git"
SOURCE_COMMIT = "be16ead371a6403c92cf196d80bee75356027670"
SOURCE_TREE = "a3be791dbe49f25f3f451fd3d877e87c91808667"


class KmDuckswanstationManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_the_exact_fork_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/main",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual("direct-cmake", self.spec["build"]["driver"])
        # Shipped armhf-only, matching the SpruceOS cores/ directory.
        self.assertEqual(["armhf"], self.spec["targets"])

    def test_rebrand_rename_is_restricted_to_the_cores_own_name(self) -> None:
        """The fork builds swanstation_libretro.so; we ship it renamed."""

        build = self.spec["build"]
        self.assertEqual("swanstation_libretro.so", build["output_path"])
        self.assertEqual(f"{CORE_ID}_libretro.so", build["artifact_name"])
        self.assertEqual("swanstation_libretro", build["cmake"]["target"])
        # Renaming to any name other than the core's own canonical one is
        # rejected -- an artifact must never impersonate another core.
        mutated = copy.deepcopy(self.spec)
        mutated["build"]["artifact_name"] = "swanstation2_libretro.so"
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validated_direct_cmake(mutated, CORE_ID)

    def test_metadata_is_repo_pinned_and_matches_the_file(self) -> None:
        """No .info exists in libretro-super for KM forks; the reviewed file
        in metadata/ is the deployed SpruceOS metadata, pinned by sha256."""

        metadata = self.spec["metadata"]
        self.assertEqual(
            {
                "repo_path": f"metadata/{CORE_ID}_libretro.info",
                "sha256": metadata["sha256"],
                "artifact_name": f"{CORE_ID}_libretro.info",
            },
            metadata,
        )
        payload = (ROOT / metadata["repo_path"]).read_bytes()
        self.assertEqual(
            metadata["sha256"], hashlib.sha256(payload).hexdigest()
        )
        self.assertIn(b"DuckSwanStation Xtreme Amped", payload)

    def test_repo_metadata_install_is_pinned_in_the_shell(self) -> None:
        shell = pipeline.metadata_install_shell(self.spec)
        self.assertIn("/metadata-repo/", shell)
        self.assertIn(self.spec["metadata"]["sha256"], shell)
        self.assertIn("CORE_PIPELINE_METADATA_REPO|", shell)
        mounts = pipeline.metadata_replacement_mount_args(self.spec)
        self.assertEqual("-v", mounts[0])
        self.assertTrue(mounts[1].endswith(":ro"))

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(f"--core {CORE_ID}", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("|| echo", workflow)
        self.assertNotIn("contents: write", workflow)


class KmDuckswanstationCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        path = ROOT / f"manifests/compatibility/{CORE_ID}.json"
        compatibility = load_document(path)
        report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=path,
            repository_root=ROOT,
            verify_pin=True,
        )
        self.assertEqual("valid", report["status"], report["errors"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual({"armhf"}, set(compatibility["targets"]))
        # Frontend-mediated GL only: no direct GL linkage. Its armhf build
        # needs GLIBCXX_3.4.32 (the armhf image's newer libstdc++), so like the
        # other modern-toolchain armhf C++ cores it sits in MINI_OVER_CEILING
        # even though the shipped fork (older toolchain) loaded there.
        needed = compatibility["targets"]["armhf"]["needed"]
        self.assertNotIn("libGLESv2.so.2", needed)
        self.assertIn("libstdc++.so.6", needed)


if __name__ == "__main__":
    unittest.main()
