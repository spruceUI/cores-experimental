"""Focused easyrpg (direct-cmake, static dep prefix, liblcf pin) tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline

from .support import ROOT, load_document


CORE_ID = "easyrpg"

# Sonames the fleet captures prove present on every probed device; the
# static-prefix design exists so the artifact needs nothing beyond these.
DEVICE_PROVEN_EXTRAS = {"libpng16.so.16", "libz.so.1"}
DESKTOP_ZOO_MARKERS = (
    "liblcf",
    "libexpat",
    "libfmt",
    "libpixman",
    "libicu",
    "libvorbis",
    "libogg",
    "libmpg123",
    "libsndfile",
    "libfreetype",
    "libharfbuzz",
    "libfluidsynth",
)


class EasyrpgManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_pins_player_master_and_reviewed_flags(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-cmake", build["driver"])
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])
        self.assertEqual(
            "https://github.com/EasyRPG/Player.git", self.spec["source"]["url"]
        )
        self.assertEqual("refs/heads/master", self.spec["source"]["requested_ref"])
        self.assertEqual(1784044064, build["source_date_epoch"])
        defines = build["cmake"]["defines"]
        # the reviewed feature set: libretro frontend, in-tree pinned liblcf,
        # ICU encoding + XML on (static), built-in font, decoders limited to
        # what the shipped working core carried (vorbis/mpg123/sndfile/FmMidi)
        self.assertEqual("libretro", defines["PLAYER_TARGET_PLATFORM"])
        self.assertEqual("ON", defines["PLAYER_BUILD_LIBLCF"])
        self.assertEqual("ON", defines["LIBLCF_WITH_ICU"])
        self.assertEqual("ON", defines["PLAYER_WITH_OGGVORBIS"])
        self.assertEqual("ON", defines["PLAYER_WITH_MPG123"])
        self.assertEqual("ON", defines["PLAYER_WITH_LIBSNDFILE"])
        self.assertEqual("OFF", defines["PLAYER_WITH_FREETYPE"])
        self.assertEqual("OFF", defines["PLAYER_WITH_FLUIDSYNTH"])
        self.assertEqual("OFF", defines["PLAYER_WITH_WILDMIDI"])

    def test_static_dep_prefix_is_per_architecture(self) -> None:
        systems = self.spec["build"]["cmake"]["systems"]
        self.assertEqual(
            {"CMAKE_PREFIX_PATH": "/usr/local/easyrpg-deps-arm64"},
            systems["arm64"]["defines"],
        )
        self.assertEqual(
            {"CMAKE_PREFIX_PATH": "/usr/local/easyrpg-deps-armhf"},
            systems["armhf"]["defines"],
        )
        for arch in ("arm64", "armhf"):
            contract = pipeline.direct_cmake_contract_for_target(self.spec, arch)
            assert contract is not None
            self.assertEqual(
                f"/usr/local/easyrpg-deps-{arch}",
                contract["cmake"]["defines"]["CMAKE_PREFIX_PATH"],
            )
            # the per-arch define merges over the common set
            self.assertEqual(
                "libretro", contract["cmake"]["defines"]["PLAYER_TARGET_PLATFORM"]
            )
            self.assertEqual(
                {"name", "processor"}, set(contract["cmake"]["system"])
            )

    def test_liblcf_pin_overlay_applies_to_both_targets(self) -> None:
        overlays = self.spec["build"]["overlays"]
        self.assertEqual(["arm64", "armhf"], sorted(overlays))
        for arch in ("arm64", "armhf"):
            (overlay,) = overlays[arch]
            self.assertEqual("git-apply-v1", overlay["kind"])
            self.assertEqual("CMakeLists.txt", overlay["source_path"])
            self.assertNotIn("submodule_path", overlay)
            patch_path = ROOT / overlay["patch_path"]
            self.assertTrue(patch_path.is_file())
            patch_text = patch_path.read_text(encoding="utf-8")
            # the reviewed pin: exact liblcf commit and tree assert baked
            # into the configure-time clone
            self.assertIn("666e6c023696d4a45a67dd9ba879dbff7b0f69f3", patch_text)
            self.assertIn(
                "4aaae9a4dadefc46011715ebcff2313cf33c0816", patch_text
            )

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core easyrpg", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class EasyrpgCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/easyrpg.json"
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
        # The shipped arm64 core dynamically linked the desktop dependency
        # zoo and never loaded on a device; the rebuilt core must need
        # nothing beyond the loader base set plus the capture-proven pair.
        for arch in ("arm64", "armhf"):
            needed = compatibility["targets"][arch]["needed"]
            for name in needed:
                self.assertFalse(
                    any(name.startswith(marker) for marker in DESKTOP_ZOO_MARKERS),
                    f"{arch} links a device-absent library: {name}",
                )
            self.assertIn("libpng16.so.16", needed)
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/easyrpg.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
