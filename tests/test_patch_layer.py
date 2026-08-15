"""Tests for the driver-agnostic build-time patch (overlay) layer."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

from .core_contract_helpers import pipeline


ROOT = Path(__file__).resolve().parents[1]

# The committed picodrive patch, used as a real overlay fixture.
PICODRIVE_OVERLAY = {
    "kind": "git-apply-v1",
    "patch_path": "patches/picodrive/tools-makefile-single-line-offsets.patch",
    "patch_sha256": (
        "2c442768b54d5ffd52ab06530e67dc582c4f9b0dac8f2d1d9ccea9739444053c"
    ),
    "source_path": "tools/Makefile",
    "preimage_sha256": (
        "9c738f02c4afb1b13d95421f74092d9af77b8c8f0f8ae55dfa0e9b7b4f6df44d"
    ),
    "postimage_sha256": (
        "2d36ea4092510e7547274ac4361897c9992ccb7db2362c622c6d9e1d76426843"
    ),
}
CORE_ID = "picodrive"
SOURCE_DIR = "libretro-picodrive"
TARGETS = ["arm64", "armhf"]


def overlays(arch_map):
    return copy.deepcopy(arch_map)


class ValidateBuildOverlaysTests(unittest.TestCase):
    def test_absent_overlays_are_ok(self) -> None:
        self.assertEqual(
            {}, pipeline.validate_build_overlays({}, CORE_ID, SOURCE_DIR, TARGETS)
        )

    def test_exact_overlay_validates_and_round_trips(self) -> None:
        result = pipeline.validate_build_overlays(
            overlays({"armhf": [PICODRIVE_OVERLAY]}), CORE_ID, SOURCE_DIR, TARGETS
        )
        self.assertEqual({"armhf": [PICODRIVE_OVERLAY]}, result)

    def test_non_target_arch_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            pipeline.PipelineError, "non-target architecture"
        ):
            pipeline.validate_build_overlays(
                {"x86_64": [PICODRIVE_OVERLAY]}, CORE_ID, SOURCE_DIR, TARGETS
            )

    def test_wrong_core_scope_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            pipeline.PipelineError, "core-scoped tracked patch"
        ):
            pipeline.validate_build_overlays(
                {"armhf": [PICODRIVE_OVERLAY]}, "swanstation", "other", TARGETS
            )

    def test_patch_digest_and_field_mutations_fail_closed(self) -> None:
        # patch_sha256 is verified against the committed patch file at catalog
        # time; preimage/postimage are verified at build time by
        # overlay_apply_shell against the real checked-out source.
        with self.subTest(field="patch_sha256"):
            with self.assertRaisesRegex(
                pipeline.PipelineError, "patch_sha256 does not match"
            ):
                pipeline.validate_build_overlays(
                    {"armhf": [{**PICODRIVE_OVERLAY, "patch_sha256": "0" * 64}]},
                    CORE_ID,
                    SOURCE_DIR,
                    TARGETS,
                )
        with self.subTest(field="missing-key"):
            dropped = {k: v for k, v in PICODRIVE_OVERLAY.items() if k != "kind"}
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_build_overlays(
                    {"armhf": [dropped]}, CORE_ID, SOURCE_DIR, TARGETS
                )
        with self.subTest(field="unknown-patch"):
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_build_overlays(
                    {
                        "armhf": [
                            {
                                **PICODRIVE_OVERLAY,
                                "patch_path": "patches/picodrive/nope.patch",
                            }
                        ]
                    },
                    CORE_ID,
                    SOURCE_DIR,
                    TARGETS,
                )

    def test_equal_pre_and_post_image_is_rejected(self) -> None:
        same = {
            **PICODRIVE_OVERLAY,
            "postimage_sha256": PICODRIVE_OVERLAY["preimage_sha256"],
        }
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_build_overlays(
                {"armhf": [same]}, CORE_ID, SOURCE_DIR, TARGETS
            )


class OverlayShellAndMountTests(unittest.TestCase):
    def _spec(self, arch_map):
        return {"build": {"overlays": copy.deepcopy(arch_map)}}

    def test_build_overlays_for_target(self) -> None:
        spec = self._spec({"armhf": [PICODRIVE_OVERLAY]})
        self.assertEqual(
            [PICODRIVE_OVERLAY], pipeline.build_overlays_for_target(spec, "armhf")
        )
        self.assertEqual([], pipeline.build_overlays_for_target(spec, "arm64"))
        self.assertEqual([], pipeline.build_overlays_for_target({"build": {}}, "armhf"))

    def test_apply_shell_emits_verified_git_apply(self) -> None:
        spec = self._spec({"armhf": [PICODRIVE_OVERLAY]})
        shell = pipeline.overlay_apply_shell(spec, "armhf", SOURCE_DIR)
        self.assertEqual("", pipeline.overlay_apply_shell(spec, "arm64", SOURCE_DIR))
        self.assertIn(
            "git -C libretro-picodrive apply --check --whitespace=error-all "
            "/recipe-overlays/0.patch",
            shell,
        )
        self.assertIn(
            "git -C libretro-picodrive apply --whitespace=error-all "
            "/recipe-overlays/0.patch",
            shell,
        )
        self.assertIn(PICODRIVE_OVERLAY["patch_sha256"], shell)
        self.assertIn(PICODRIVE_OVERLAY["preimage_sha256"], shell)
        self.assertIn(PICODRIVE_OVERLAY["postimage_sha256"], shell)
        self.assertIn("libretro-picodrive/tools/Makefile", shell)

    def test_mount_args_pin_the_patch(self) -> None:
        spec = self._spec({"armhf": [PICODRIVE_OVERLAY]})
        args = pipeline.overlay_mount_args(spec, "armhf")
        self.assertEqual([], pipeline.overlay_mount_args(spec, "arm64"))
        self.assertEqual("-v", args[0])
        self.assertTrue(args[1].endswith("/recipe-overlays/0.patch:ro"))
        self.assertIn(
            "patches/picodrive/tools-makefile-single-line-offsets.patch", args[1]
        )

    def test_mount_args_reject_a_drifted_patch(self) -> None:
        drifted = {**PICODRIVE_OVERLAY, "patch_sha256": "0" * 64}
        with self.assertRaises(pipeline.PipelineError):
            pipeline.overlay_mount_args(self._spec({"armhf": [drifted]}), "armhf")


if __name__ == "__main__":
    unittest.main()
