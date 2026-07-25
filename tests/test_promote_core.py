"""Tests for the promotion lifecycle composer (promote_core.py)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "promote_core", ROOT / "scripts" / "promote_core.py"
)
assert _spec is not None and _spec.loader is not None
promote_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(promote_core)

UZEM_ID = "uzem-d4fe82c38bf3-34eca38274ae"


class HelperTests(unittest.TestCase):
    def test_content_sha256_ignores_schema_and_self(self):
        a = {"$schema": "x", "a": 1, "content_sha256": "old"}
        b = {"$schema": "y", "a": 1}
        self.assertEqual(
            promote_core.content_sha256(a), promote_core.content_sha256(b)
        )

    def test_max_glibcxx_picks_highest(self):
        value, key = promote_core.max_glibcxx(
            ["GLIBCXX_3.4", "GLIBCXX_3.4.29", "GLIBC_2.4"]
        )
        self.assertEqual(value, "3.4.29")
        self.assertEqual(key, (3, 4, 29))


class SourceLockTests(unittest.TestCase):
    def test_compose_source_lock_matches_catalog_and_validates(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from profile_registry import canonical_content_sha256, validate_source_lock

        catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8")
        )
        source = catalog["cores"]["atari800"]["source"]
        lock = promote_core.compose_source_lock("atari800")
        self.assertEqual("atari800", lock["core_id"])
        self.assertEqual(f"atari800-{source['commit'][:12]}", lock["source_lock_id"])
        self.assertEqual(source["commit"], lock["source"]["commit"])
        self.assertEqual(source["tree"], lock["source"]["tree"])
        self.assertEqual([], lock["source"]["submodules"])
        self.assertEqual(
            canonical_content_sha256(lock), lock["content_sha256"]
        )
        validate_source_lock(lock, path=None)


class DeviceCaveatTests(unittest.TestCase):
    def test_over_mini_ceiling_is_a30_only(self):
        caveat = promote_core._device_caveat(
            {"armhf": {"version_requirements": ["GLIBCXX_3.4.29"]}}
        )
        self.assertIn("above the observed", caveat)
        self.assertIn("Mini profile is ineligible", caveat)

    def test_within_mini_ceiling_clears_both(self):
        caveat = promote_core._device_caveat(
            {"armhf": {"version_requirements": ["GLIBCXX_3.4.21"]}}
        )
        self.assertIn("within the observed Miyoo Mini", caveat)

    def test_c_only_clears_every_ceiling(self):
        caveat = promote_core._device_caveat(
            {"armhf": {"version_requirements": ["GLIBC_2.7"]}}
        )
        self.assertIn("no libstdc++ dependency", caveat)


class ComposeSourceSetTests(unittest.TestCase):
    def test_reproduces_committed_uzem_source_set(self):
        # The composed document must self-validate and bind its pin exactly.
        try:
            composed = promote_core.compose_source_set(UZEM_ID)
        except promote_core.PromoteCoreError:
            self.skipTest("uzem promotion evidence not present")
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from profile_registry import validate_source_set

        validate_source_set(composed)
        self.assertEqual(UZEM_ID, composed["source_set_id"])
        self.assertEqual(
            f"pins/core-sets/{UZEM_ID}.json", composed["evidence_pin"]["path"]
        )


class ComposeCompatibilityTests(unittest.TestCase):
    def test_composes_valid_uzem_manifest_with_derived_device_caveat(self):
        try:
            manifest = promote_core.compose_compatibility(
                "uzem", UZEM_ID,
                "actions-sim-build-core-uzem-w3", "build-core-uzem-local-w3",
            )
        except promote_core.PromoteCoreError:
            self.skipTest("uzem promotion evidence not present")
        self.assertEqual(manifest["core_id"], "uzem")
        self.assertEqual(manifest["publication"], "disabled")
        self.assertEqual(manifest["package_state"], "reproducible")
        self.assertEqual(set(manifest["targets"]), {"arm64", "armhf"})
        self.assertEqual(
            manifest["golden_source"], f"pins/core-sets/{UZEM_ID}.json"
        )
        # The device caveat is derived, not retyped: uzem is over the Mini ceiling.
        self.assertTrue(
            any("Mini profile is ineligible" in c for c in manifest["caveats"])
        )
        # content_sha256 is self-consistent.
        self.assertEqual(
            manifest["content_sha256"], promote_core.content_sha256(manifest)
        )

    def test_extra_caveats_are_appended(self):
        try:
            manifest = promote_core.compose_compatibility(
                "uzem", UZEM_ID,
                "actions-sim-build-core-uzem-w3", "build-core-uzem-local-w3",
                extra_caveats=["GPLv3 review pending."],
            )
        except promote_core.PromoteCoreError:
            self.skipTest("uzem promotion evidence not present")
        self.assertEqual(manifest["caveats"][-1], "GPLv3 review pending.")


class FinishPromotionTests(unittest.TestCase):
    def test_dangling_pointer_falls_back_to_expect_absent(self):
        calls = []

        def fake_pipeline(*args):
            calls.append(args)
            if "--expect-current" in args:
                raise promote_core.PromoteCoreError("current pointer invalid")
            return ""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            for channel in ("nightly", "pinned", "release"):
                (channels / f"{channel}.demo.json").write_text(
                    '{"target": {"id": "demo-aaaa-old1"}}', encoding="utf-8"
                )
            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(promote_core, "_pipeline", fake_pipeline):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")
            for channel in ("nightly", "pinned", "release"):
                self.assertFalse((channels / f"{channel}.demo.json").exists())
        swaps = [c for c in calls if c[0] == "update-channel"]
        self.assertEqual(6, len(swaps))  # one failed CAS + one create per channel
        self.assertEqual(3, sum("--expect-absent" in c for c in swaps))
        validates = [c for c in calls if c[0] == "validate-channel"]
        self.assertEqual(3, len(validates))

    def test_pointer_already_current_is_left_alone(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            channels = root / ".local-e2e" / "channels"
            channels.mkdir(parents=True)
            (root / ".local-e2e" / "releases" / "demo-aaaa-bbbb").mkdir(
                parents=True
            )
            for channel in ("nightly", "pinned", "release"):
                (channels / f"{channel}.demo.json").write_text(
                    '{"target": {"id": "demo-aaaa-bbbb"}}', encoding="utf-8"
                )
            with mock.patch.object(promote_core, "ROOT", root), \
                    mock.patch.object(
                        promote_core, "_pipeline",
                        lambda *a: calls.append(a) or ""):
                promote_core.finish_promotion("demo", "demo-aaaa-bbbb")
        self.assertEqual(0, sum(c[0] == "update-channel" for c in calls))
        self.assertEqual(3, sum(c[0] == "validate-channel" for c in calls))


class RunWaveTests(unittest.TestCase):
    def test_wave_refuses_a_dirty_tree(self):
        with mock.patch.object(
            promote_core, "_worktree_is_clean", lambda: False
        ):
            with self.assertRaises(promote_core.PromoteCoreError):
                promote_core.run_wave(
                    ["demo"], "wX", refresh=True,
                    carry_caveats=True, finish=True,
                )

    def test_wave_builds_every_core_before_any_promote(self):
        order = []

        def fake_pipeline(*args):
            order.append((args[0], args[args.index("--core") + 1]))
            return ""

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(promote_core, "ROOT", Path(tmp)), \
                mock.patch.object(promote_core, "_worktree_is_clean",
                                  lambda: True), \
                mock.patch.object(promote_core, "_pipeline", fake_pipeline), \
                mock.patch.object(promote_core, "run_promotion",
                                  lambda core, *a, **k: order.append(
                                      ("promote", core)) or f"{core}-x-y"), \
                mock.patch.object(promote_core, "finish_promotion",
                                  lambda *a: None), \
                mock.patch.object(promote_core, "_write_evidence_index",
                                  lambda core: None):
            promote_core.run_wave(
                ["one", "two"], "wX", refresh=True,
                carry_caveats=False, finish=True,
            )
        first_promote = order.index(("promote", "one"))
        builds_after = [
            entry for entry in order[first_promote:]
            if entry[0] == "build-core"
        ]
        self.assertEqual([], builds_after)
        self.assertEqual(4, sum(e[0] == "build-core" for e in order))


if __name__ == "__main__":
    unittest.main()
