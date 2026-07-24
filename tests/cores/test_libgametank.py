"""Focused libgametank (direct-cargo, Rust image, Cargo.lock pin) tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, load_document


CORE_ID = "libgametank"


class LibgametankManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_pins_gametank_sdk_and_cargo_recipe(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-cargo", build["driver"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertEqual(
            "https://github.com/dwbrite/gametank-sdk.git",
            self.spec["source"]["url"],
        )
        self.assertEqual("refs/heads/master", self.spec["source"]["requested_ref"])
        self.assertEqual(1784593754, build["source_date_epoch"])
        cargo = build["cargo"]
        self.assertEqual("tools/gte/libretro", cargo["subdir"])
        self.assertEqual("release", cargo["profile"])
        # Upstream's committed Cargo.lock is the dependency pin: per-crate
        # sha256 checksums make every crates.io fetch content-addressed, and
        # the driver builds with --locked.
        self.assertEqual(
            "b8c66e6924352eb35603df6a921ef43ecd91fa6b79ab8b44def74098069ce360",
            cargo["lock_sha256"],
        )
        # The glibc floor suffix matches the A30 sysroot generation; the
        # measured artifact requirement is GLIBC <= 2.18 on both targets.
        self.assertEqual(
            {
                "arm64": "aarch64-unknown-linux-gnu.2.23",
                "armhf": "armv7-unknown-linux-gnueabihf.2.23",
            },
            cargo["targets"],
        )

    def test_cargo_builds_run_inside_the_locked_rust_image(self) -> None:
        for arch in ("arm64", "armhf"):
            self.assertEqual(
                "rust", pipeline.build_toolchain_key(self.spec, arch)
            )
            contract = pipeline.direct_cargo_contract_for_target(self.spec, arch)
            assert contract is not None
            self.assertEqual(
                self.spec["build"]["cargo"]["targets"][arch],
                contract["cargo"]["target"],
            )
        rust = self.catalog["toolchains"]["rust"]
        self.assertEqual("cores-rust:latest", rust["image"])
        self.assertEqual("Dockerfile.rust", rust["dockerfile"])
        lock = load_document(ROOT / "pins/toolchains/local-cache-v1.json")
        self.assertEqual(
            rust["image_id"], lock["toolchains"]["rust"]["image"]["id"]
        )
        self.assertEqual(
            "cores-rust.tar.gz",
            lock["toolchains"]["rust"]["archive"]["filename"],
        )

    def test_metadata_is_repo_pinned(self) -> None:
        metadata = self.spec["metadata"]
        self.assertEqual(
            "metadata/libgametank_libretro.info", metadata["repo_path"]
        )
        info_path = ROOT / metadata["repo_path"]
        self.assertTrue(info_path.is_file())
        self.assertEqual(
            metadata["sha256"], pipeline.sha256_file(info_path)
        )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core libgametank", workflow)
        self.assertIn("cores-rust.tar.gz", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class LibgametankCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/libgametank.json"
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
        self.assertEqual(["arm64", "armhf"], sorted(compatibility["targets"]))
        # Rust static linkage: nothing beyond the loader base set (libdl is
        # in every device capture), so the core is loader-eligible wherever
        # its ABI is.
        for arch in ("arm64", "armhf"):
            needed = compatibility["targets"][arch]["needed"]
            for name in needed:
                self.assertTrue(
                    name.startswith(
                        ("ld-linux", "libc.so", "libdl.so", "libm.so",
                         "libpthread.so", "libgcc_s.so")
                    ),
                    f"{arch} links an unexpected library: {name}",
                )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/libgametank.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
