"""Tests for the per-device candidate core-set assembly (device_sets.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "device_sets.py"

_spec = importlib.util.spec_from_file_location("device_sets", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
device_sets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(device_sets)


# The C++ cores whose armhf build references GLIBCXX above the Miyoo Mini
# packaged-fallback ceiling of 3.4.24. Kept as an explicit expectation so a
# future migration that changes this set fails loudly here (uzem joined on its
# promotion to canonical: its armhf build needs GLIBCXX_3.4.29).
MINI_OVER_CEILING: set[str] = set()
# Emptied 2026-07-23: the Mini family's bundled SD provider was upgraded to the
# A30 buildroot libstdc++ (GLIBCXX 3.4.32, observed on-device by probe), so no
# canonical armhf core exceeds the captured ceiling any more.


class VersionTupleTests(unittest.TestCase):
    def test_dotted_versions_compare_numerically(self):
        self.assertEqual(device_sets.version_tuple("3.4.32"), (3, 4, 32))
        self.assertLess(
            device_sets.version_tuple("3.4.24"),
            device_sets.version_tuple("3.4.32"),
        )

    def test_bare_version_sorts_below_patch_versions(self):
        # GLIBCXX_3.4 is the base symbol and must sort below any 3.4.N.
        self.assertLess(
            device_sets.version_tuple("3.4"),
            device_sets.version_tuple("3.4.15"),
        )

    def test_non_numeric_yields_empty_tuple(self):
        self.assertEqual(device_sets.version_tuple("3.x"), ())


class MaxSymbolTests(unittest.TestCase):
    def test_picks_highest_prefixed_symbol(self):
        symbols = ["GLIBCXX_3.4", "GLIBCXX_3.4.21", "GLIBCXX_3.4.15", "CXXABI_1.3"]
        self.assertEqual(
            device_sets.max_symbol_version(symbols, "GLIBCXX_"),
            "GLIBCXX_3.4.21",
        )

    def test_absent_prefix_returns_none(self):
        self.assertIsNone(
            device_sets.max_symbol_version(["GLIBC_2.17"], "GLIBCXX_")
        )


# A device whose probe observed every library these fixtures reference. Passing
# it keeps each ceiling test about the ceiling; the library screen has its own
# tests below.
ALL_PRESENT = ({"libc.so.6", "libm.so.6", "libstdc++.so.6", "libGLESv2.so.2"}, set())


class ClassifyCoreTests(unittest.TestCase):
    def test_c_only_core_clears_any_ceiling(self):
        target = {"needed": ["libc.so.6", "libm.so.6"], "version_requirements": []}
        bucket, _ = device_sets.classify_core(target, "3.4.24", "arm64", ALL_PRESENT)
        self.assertEqual(bucket, "eligible")

    def test_cpp_core_within_ceiling_is_eligible(self):
        target = {
            "needed": ["libc.so.6", "libstdc++.so.6"],
            "version_requirements": ["GLIBCXX_3.4.21"],
        }
        bucket, detail = device_sets.classify_core(
            target, "3.4.24", "arm64", ALL_PRESENT
        )
        self.assertEqual(bucket, "eligible")
        self.assertEqual(detail["glibcxx"], "3.4.21")

    def test_cpp_core_over_ceiling(self):
        target = {
            "needed": ["libc.so.6", "libstdc++.so.6"],
            "version_requirements": ["GLIBCXX_3.4.32"],
        }
        bucket, detail = device_sets.classify_core(
            target, "3.4.24", "arm64", ALL_PRESENT
        )
        self.assertEqual(bucket, "over_ceiling")
        self.assertEqual(detail["glibcxx"], "3.4.32")

    def test_uncaptured_ceiling_defers_cpp_core(self):
        target = {
            "needed": ["libstdc++.so.6"],
            "version_requirements": ["GLIBCXX_3.4.21"],
        }
        bucket, _ = device_sets.classify_core(target, None, "arm64", ALL_PRESENT)
        self.assertEqual(bucket, "eligible_ceiling_uncaptured")

    def test_missing_target_reports_no_arch(self):
        bucket, _ = device_sets.classify_core(None, "3.4.24")
        self.assertEqual(bucket, "no_arch_target")

    def test_absent_provider_disqualifies_regardless_of_ceiling(self):
        """The case a ceiling-only screen missed: a library that is not there."""

        target = {
            "needed": ["libc.so.6", "libGLESv2.so.2"],
            "version_requirements": [],
        }
        bucket, detail = device_sets.classify_core(
            target, "3.4.24", "arm64", ({"libc.so.6"}, {"libGLESv2.so.2"})
        )
        self.assertEqual(bucket, "missing_provider")
        self.assertEqual(detail["missing_providers"], ["libGLESv2.so.2"])

    def test_unprobed_device_fails_closed(self):
        target = {"needed": ["libc.so.6"], "version_requirements": []}
        bucket, detail = device_sets.classify_core(target, "3.4.24", "arm64", None)
        self.assertEqual(bucket, "provider_uncaptured")
        self.assertEqual(detail["unverified_providers"], ["libc.so.6"])

    def test_elf_interpreter_is_not_a_separate_provider(self):
        """It is implied by the ABI the device runs, not a library to find."""

        target = {
            "needed": ["libc.so.6", "ld-linux-aarch64.so.1"],
            "version_requirements": [],
        }
        bucket, _ = device_sets.classify_core(
            target, "3.4.24", "arm64", ({"libc.so.6"}, set())
        )
        self.assertEqual(bucket, "eligible")

    def test_a_known_ceiling_failure_outranks_an_unprobed_provider(self):
        """An unprobed device still reports what IS known about it."""

        target = {
            "needed": ["libc.so.6", "libstdc++.so.6"],
            "version_requirements": ["GLIBCXX_3.4.32"],
        }
        bucket, _ = device_sets.classify_core(target, "3.4.24", "armhf", None)
        self.assertEqual(bucket, "over_ceiling")


class ReportInvariantTests(unittest.TestCase):
    def setUp(self):
        self.report = device_sets.build_report()

    def test_report_is_local_and_publication_disabled(self):
        self.assertTrue(self.report["local_only"])
        self.assertEqual(self.report["publication"], "disabled")
        self.assertEqual(self.report["screen"], "static-abi-only")

    def test_report_is_deterministic(self):
        self.assertEqual(self.report, device_sets.build_report())

    def test_every_core_lands_in_exactly_one_bucket(self):
        buckets = (
            "eligible",
            "memory_ineligible",
            "eligible_ceiling_uncaptured",
            "over_ceiling",
            "missing_provider",
            "provider_uncaptured",
            "policy_excluded",
            "no_arch_target",
        )
        for device_id, view in self.report["devices"].items():
            total = sum(len(view[name]) for name in buckets)
            self.assertEqual(
                total,
                self.report["core_count"],
                f"{device_id} does not partition every core exactly once",
            )


class LiveDeviceScreenTests(unittest.TestCase):
    def setUp(self):
        self.devices = device_sets.build_report()["devices"]

    def test_miyoo_mini_excludes_the_over_ceiling_cores(self):
        mini = self.devices["device-miyoo-mini-family-v0"]
        self.assertEqual(mini["architecture"], "armhf")
        self.assertEqual(mini["provider_glibcxx_ceiling"], "3.4.32")
        over = {row["core"] for row in mini["over_ceiling"]}
        self.assertEqual(over, MINI_OVER_CEILING)
        eligible = {row["core"] for row in mini["eligible"]}
        self.assertTrue(MINI_OVER_CEILING.isdisjoint(eligible))
        # A C-only core is always Mini-portable.
        self.assertIn("2048", eligible)
        # The Mini was probed on 2026-07-22. flycast's armhf build links the
        # UNVERSIONED libGLESv2.so; the capture proved only the versioned
        # libGLESv2.so.2 absent, so the unversioned name fails closed as
        # uncaptured (the Mini family has no GLES2 provider either way).
        self.assertEqual("loader", mini["library_capture"])
        # km_parallel_n64 no longer reaches ABI classification on the Mini
        # family: the measured memory screen excludes it first.
        self.assertEqual(
            [
                {
                    "core": "flycast",
                    "glibcxx": "3.4.32",
                    "unverified_providers": ["libGLESv2.so"],
                },
            ],
            mini["provider_uncaptured"],
        )

    def test_miyoo_a30_clears_every_armhf_core(self):
        a30 = self.devices["device-miyoo-a30-v0"]
        self.assertEqual(a30["provider_glibcxx_ceiling"], "3.4.32")
        self.assertEqual(a30["over_ceiling"], [])

    def test_arm64_device_defers_cpp_cores_with_uncaptured_ceiling(self):
        # MagicX Zero28 is an A133P-family device we have not probed yet, so it
        # still has no provider observation and defers every C++ core.
        magicx = self.devices["device-magicx-zero28-v0"]
        self.assertEqual(magicx["architecture"], "arm64")
        self.assertIsNone(magicx["provider_glibcxx_ceiling"])
        self.assertEqual(magicx["over_ceiling"], [])
        self.assertIsNone(magicx["library_capture"])
        self.assertTrue(magicx["provider_uncaptured"])

    def test_probed_devices_have_a_loader_truth_library_capture(self):
        """The five-device fleet capture (2026-07-22, device-probe-v3)."""

        for device_id in (
            "device-trimui-a133p-family-v0",
            "device-trimui-smart-pro-s-v0",
            "device-miyoo-flip-v0",
            "device-gkd-pixel2-v0",
        ):
            view = self.devices[device_id]
            self.assertEqual("loader", view["library_capture"], device_id)
            self.assertEqual([], view["provider_uncaptured"], device_id)
            self.assertEqual([], view["missing_provider"], device_id)

    def test_parallel_n64_needs_a_gles2_provider_and_has_one(self):
        """The core that motivated the provider screen.

        parallel_n64 is the only catalog core linking a graphics library
        directly, and every probed device resolved it. If a device without a
        GLES2 provider is ever added, this core must land in missing_provider
        rather than being waved through on a libstdc++ comparison.
        """

        targets = device_sets.load_core_targets()["parallel_n64"]
        self.assertIn("libGLESv2.so.2", targets["arm64"]["needed"])
        for device_id in (
            "device-trimui-a133p-family-v0",
            "device-gkd-pixel2-v0",
        ):
            eligible = {
                row["core"] for row in self.devices[device_id]["eligible"]
            }
            self.assertIn("parallel_n64", eligible, device_id)

    def test_mini_plus_has_no_gles2_provider_and_the_screen_knows(self):
        """The case that justifies the provider screen.

        The 2026-07-22 Mini Plus probe found no libGLESv2.so.2 at all, and the
        shipped armhf flycast fails to load there with exactly that missing
        soname. No catalog core is affected yet -- parallel_n64, the only one
        linking GLES directly, is arm64-only and the Mini is armhf -- but a
        GL-linking armhf core must land in missing_provider rather than being
        waved through on a libstdc++ comparison the way it would have been
        before this screen existed.
        """

        contracts = device_sets._load_json(device_sets.DEVICE_CONTRACTS_PATH)
        mini = contracts["contracts"]["device-miyoo-mini-family-v0"]
        libraries = device_sets.device_library_availability(mini)
        self.assertIsNotNone(libraries)
        available, absent = libraries
        self.assertIn("libGLESv2.so.2", absent)
        self.assertNotIn("libGLESv2.so.2", available)

        gl_core = {
            "needed": ["libc.so.6", "libGLESv2.so.2"],
            "version_requirements": [],
        }
        bucket, detail = device_sets.classify_core(
            gl_core, "3.4.24", "armhf", libraries
        )
        self.assertEqual("missing_provider", bucket)
        self.assertEqual(["libGLESv2.so.2"], detail["missing_providers"])

    def test_captured_arm64_devices_clear_the_whole_catalog(self):
        # On-device probes (device_probe.sh) captured the effective libstdc++
        # ceiling for these four arm64 devices; every arm64 C++ core needs at
        # most GLIBCXX_3.4.26 (neocd), so nothing is over-ceiling and nothing
        # is deferred.
        expected = {
            "device-trimui-a133p-family-v0": "3.4.28",
            "device-trimui-smart-pro-s-v0": "3.4.28",
            "device-miyoo-flip-v0": "3.4.32",
            "device-gkd-pixel2-v0": "3.4.33",
        }
        for device_id, ceiling in expected.items():
            view = self.devices[device_id]
            self.assertEqual(view["architecture"], "arm64", device_id)
            self.assertEqual(
                view["provider_glibcxx_ceiling"], ceiling, device_id
            )
            self.assertEqual(view["over_ceiling"], [], device_id)
            self.assertEqual(view["eligible_ceiling_uncaptured"], [], device_id)

    def test_pixel2_frontend_is_flagged_missing(self):
        pixel2 = self.devices["device-gkd-pixel2-v0"]
        self.assertFalse(pixel2["frontend_available"])

    def test_mini_family_memory_screen_excludes_the_measured_pair(self):
        mini = self.devices["device-miyoo-mini-family-v0"]
        self.assertEqual(
            [
                {
                    "core": "km_parallel_n64_xtreme_amped_turbo",
                    "reason": "memory-zero-fill-map",
                    "capture": "load-smoke-20260724-v1",
                    "constraint": "mini-family-memory-capacity-v0",
                },
                {
                    "core": "puae2021",
                    "reason": "memory-zero-fill-map",
                    "capture": "load-smoke-20260724-v1",
                    "constraint": "mini-family-memory-capacity-v0",
                },
            ],
            mini["memory_ineligible"],
        )
        # The screen is contract-bound: no other device view consumes it.
        for contract_id, view in self.devices.items():
            if contract_id == "device-miyoo-mini-family-v0":
                continue
            self.assertEqual([], view["memory_ineligible"], contract_id)

    def test_mini_over_ceiling_carries_the_formal_constraint(self):
        mini = self.devices["device-miyoo-mini-family-v0"]
        # The provider upgrade moved these to eligible, but the constraint
        # still rides along: the profile's runtime behavior remains unverified
        # (playback validation is a separate, still-missing gate).
        constrained = {
            row["core"]: row.get("constraint")
            for bucket in ("eligible", "over_ceiling")
            for row in mini[bucket]
        }
        self.assertEqual(
            constrained.get("gearboy"), "mini-cxx-provider-unverified-v0"
        )
        self.assertEqual(
            constrained.get("gearsystem"), "mini-cxx-provider-unverified-v0"
        )


if __name__ == "__main__":
    unittest.main()
