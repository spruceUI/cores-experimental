"""Tests for the runtime smoke-test contract and its feed into device fitness."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_smoke = _load("runtime_smoke")
fitness_record = _load("fitness_record")


def _all_pass_checks() -> dict[str, bool]:
    return {name: True for name in runtime_smoke.SMOKE_CHECKS}


class BuildResultTests(unittest.TestCase):
    def test_content_free_load_smoke_passes(self):
        # All load/init entry points succeed; frames stays 0 (no content run).
        result = runtime_smoke.build_smoke_result(
            core_id="gearboy",
            architecture="armhf",
            runner="qemu-user",
            provider_profile="device-miyoo-a30-v0",
            checks=_all_pass_checks(),
        )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["frames"], 0)
        self.assertEqual(runtime_smoke.validate_smoke_result(result), [])

    def test_a_failed_entry_point_fails(self):
        # dlopen resolving but retro_init failing (e.g. unmet provider symbol).
        checks = _all_pass_checks()
        checks["retro_init"] = False
        result = runtime_smoke.build_smoke_result(
            core_id="snes9x",
            architecture="armhf",
            runner="qemu-user",
            provider_profile="device-miyoo-mini-family-v0",
            checks=checks,
        )
        self.assertEqual(result["status"], "fail")

    def test_missing_or_unknown_checks_are_rejected(self):
        partial = {name: True for name in runtime_smoke.SMOKE_CHECKS[:-1]}
        with self.assertRaises(runtime_smoke.RuntimeSmokeError):
            runtime_smoke.build_smoke_result(
                core_id="x", architecture="arm64", runner="fake",
                provider_profile="p", checks=partial, frames=1,
            )
        extra = {**_all_pass_checks(), "bogus": True}
        with self.assertRaises(runtime_smoke.RuntimeSmokeError):
            runtime_smoke.build_smoke_result(
                core_id="x", architecture="arm64", runner="fake",
                provider_profile="p", checks=extra, frames=1,
            )

    def test_bad_architecture_or_runner_rejected(self):
        with self.assertRaises(runtime_smoke.RuntimeSmokeError):
            runtime_smoke.build_smoke_result(
                core_id="x", architecture="x86", runner="fake",
                provider_profile="p", checks=_all_pass_checks(), frames=1,
            )
        with self.assertRaises(runtime_smoke.RuntimeSmokeError):
            runtime_smoke.build_smoke_result(
                core_id="x", architecture="arm64", runner="cloud",
                provider_profile="p", checks=_all_pass_checks(), frames=1,
            )


class ValidateResultTests(unittest.TestCase):
    def test_status_must_match_checks(self):
        result = runtime_smoke.build_smoke_result(
            core_id="gearboy", architecture="arm64", runner="fake",
            provider_profile="p", checks=_all_pass_checks(), frames=2,
        )
        result["status"] = "fail"  # inconsistent with all-pass checks
        self.assertIn("status does not match its checks",
                      runtime_smoke.validate_smoke_result(result))

    def test_non_dict_is_rejected(self):
        self.assertTrue(runtime_smoke.validate_smoke_result("nope"))


class ApplyToFitnessTests(unittest.TestCase):
    def setUp(self):
        self.fitness = fitness_record.compose_fitness("gearboy")

    def test_matching_result_replaces_pending(self):
        result = runtime_smoke.build_smoke_result(
            core_id="gearboy", architecture="arm64", runner="native-arm64",
            provider_profile="device-trimui-a133p-family-v0",
            checks=_all_pass_checks(), frames=6,
        )
        merged = runtime_smoke.apply_to_fitness(self.fitness, [result])
        self.assertEqual(merged["targets"]["arm64"]["runtime_smoke"]["status"], "pass")
        # The un-tested ABI keeps its pending marker.
        self.assertEqual(merged["targets"]["armhf"]["runtime_smoke"], "pending")
        # The source record is not mutated.
        self.assertEqual(self.fitness["targets"]["arm64"]["runtime_smoke"], "pending")

    def test_mismatched_core_is_ignored(self):
        result = runtime_smoke.build_smoke_result(
            core_id="snes9x", architecture="arm64", runner="fake",
            provider_profile="p", checks=_all_pass_checks(), frames=1,
        )
        merged = runtime_smoke.apply_to_fitness(self.fitness, [result])
        self.assertEqual(merged["targets"]["arm64"]["runtime_smoke"], "pending")


class AnnotateDeviceSetTests(unittest.TestCase):
    def _mini_like_view(self):
        return {
            "architecture": "armhf",
            "counts": {},
            "eligible": [{"core": "handy"}, {"core": "2048"}],
            "eligible_ceiling_uncaptured": [],
            "over_ceiling": [{"core": "gearboy", "glibcxx": "3.4.32"}],
            "policy_excluded": [],
            "no_arch_target": [],
        }

    def test_runtime_pass_overrides_the_static_screen(self):
        # gearboy is over_ceiling on the Mini ABI screen; a captured runtime pass
        # on the device's provider promotes it to runtime_verified.
        annotated = runtime_smoke.annotate_device_set(
            self._mini_like_view(), {"gearboy": "pass"}
        )
        self.assertEqual(annotated["over_ceiling"], [])
        verified = {row["core"]: row["from"] for row in annotated["runtime_verified"]}
        self.assertEqual(verified.get("gearboy"), "over_ceiling")

    def test_runtime_fail_moves_core_to_failed(self):
        annotated = runtime_smoke.annotate_device_set(
            self._mini_like_view(), {"handy": "fail"}
        )
        failed = {row["core"] for row in annotated["runtime_failed"]}
        self.assertIn("handy", failed)
        self.assertNotIn("handy", {row["core"] for row in annotated["eligible"]})

    def test_untested_cores_keep_their_bucket_and_counts_recompute(self):
        annotated = runtime_smoke.annotate_device_set(self._mini_like_view(), {})
        self.assertEqual(annotated["counts"]["over_ceiling"], 1)
        self.assertEqual(annotated["counts"]["runtime_verified"], 0)
        self.assertEqual(len(annotated["eligible"]), 2)


if __name__ == "__main__":
    unittest.main()
