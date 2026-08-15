"""Focused YabaSanshiro (portable AArch64/GLES3 direct-make) tests."""

from __future__ import annotations

import unittest

from .support import pipeline
from core_pipeline_lib.contracts import yabasanshiro

from .support import ROOT, load_document


CORE_ID = "yabasanshiro"
PORTABLE_PROBE_RUN = "campaign-20260810-yabasanshiro-portable-probe-01"
TUNED_RUNS = (
    "actions-sim-build-core-yabasanshiro-w3",
    "build-core-yabasanshiro-local-w3",
)


class YabasanshiroManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_is_direct_make_with_the_portable_gles3_recipe(self) -> None:
        build = self.spec["build"]
        self.assertEqual("direct-make", build["driver"])
        # one generic build supersedes the three shipped device-tuned
        # variants (plain/_a133p link PowerVR internals, _smartpros links
        # the Mali blob); shipped and built arm64-only
        self.assertEqual(["arm64"], self.spec["targets"])
        self.assertEqual(
            "refs/heads/yabasanshiro", self.spec["source"]["requested_ref"]
        )
        self.assertEqual("yabause/src/libretro", build["make_subdir"])
        # The generic arm64 platform retains the AArch64 dynarec without
        # selecting a CPU. FORCE_GLES keeps the GLES3 renderer while avoiding
        # arm64_cortex_a53_gles3's A53/CRC flags.
        self.assertEqual({"arm64": "arm64"}, build["platforms"])
        self.assertEqual(["FORCE_GLES=1"], build["make_args"])
        self.assertTrue(
            yabasanshiro.yabasanshiro_spec_is_well_formed(self.spec)
        )

    def test_spec_guard_rejects_the_tuned_platform_or_missing_gles(self) -> None:
        tuned = {
            **self.spec,
            "build": {
                **self.spec["build"],
                "platforms": {"arm64": "arm64_cortex_a53_gles3"},
            },
        }
        self.assertFalse(yabasanshiro.yabasanshiro_spec_is_well_formed(tuned))
        without_gles = {
            **self.spec,
            "build": {
                key: value
                for key, value in self.spec["build"].items()
                if key != "make_args"
            },
        }
        self.assertFalse(
            yabasanshiro.yabasanshiro_spec_is_well_formed(without_gles)
        )

    def test_driver_emits_the_portable_arm64_gles_make_arguments(self) -> None:
        script = pipeline.container_build_script(
            CORE_ID,
            "arm64",
            self.spec,
            self.catalog["resolver"],
        )
        make_line = next(
            line for line in script.splitlines() if line.startswith('make -j"')
        )
        self.assertIn("platform=arm64 FORCE_GLES=1", make_line)
        self.assertNotIn("cortex-a53", make_line)

    def test_registered_contract_pins_the_gles_link(self) -> None:
        contract = yabasanshiro.YABASANSHIRO_LOG_CONTRACT
        registered = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered)
        self.assertEqual("yabasanshiro-c-asm-v2", registered.contract_id)
        self.assertEqual(
            "yabasanshiro-c-asm-v2",
            yabasanshiro.YABASANSHIRO_LOG_CONTRACT_ID,
        )
        self.assertEqual({"arm64": 83}, dict(contract.expected_c_compile_count))
        self.assertEqual(
            {"arm64": 6}, dict(contract.expected_cxx_compile_count)
        )
        self.assertEqual(
            {"arm64": 1}, dict(contract.expected_asm_compile_count)
        )
        self.assertEqual(
            {
                "arm64": (
                    "7d4b35b01d396b9d9c96ee1ca20e3a389d57b79c4b20a19112be705b90693096"
                )
            },
            dict(contract.expected_compile_pair_sha256),
        )
        self.assertEqual(
            {
                "arm64": (
                    "9eeaa491a8aefb59e9d351c5cc7e59b649d361e8c9a6393cdbd548c79b40280d"
                )
            },
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            {
                "arm64": (
                    "7b0c18be87ad6e30918170d13c0b9b1d71f3507857cc0fe9ce6674079ff8caef"
                )
            },
            dict(contract.expected_link_object_sha256),
        )
        self.assertEqual(
            {
                "arm64": (
                    "d440ddc6c7c3026f16c6f2a1629ba40b57297ec1e8aacee3a69f03304cfde2dc"
                )
            },
            dict(contract.expected_raw_link_object_sha256 or {}),
        )
        self.assertEqual(
            (
                "-lpthread",
                "-lGLESv2",
                "-fPIC",
                "-shared",
                "-Wl,--no-undefined",
                "-Wl,--version-script=link.T",
            ),
            contract.expected_link_options["arm64"],
        )
        # the yabause tree names objects `<source>.o` (osdcore.c.o), the
        # opt-in the pairing sha256s make safe to admit
        self.assertTrue(contract.source_suffixed_object_names)

    def test_workflow_is_a_migrated_read_only_dispatcher(self) -> None:
        workflow = (ROOT / self.spec["workflow"]).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("--core yabasanshiro", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("|| echo", workflow)


class YabasanshiroPortableContractTests(unittest.TestCase):
    def _log(self, run_id: str) -> str | None:
        path = (
            ROOT
            / ".local-e2e"
            / "runs"
            / run_id
            / CORE_ID
            / "arm64"
            / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def _proves(self, log: str) -> bool:
        return yabasanshiro.yabasanshiro_log_proves_contract(
            log,
            CORE_ID,
            "arm64",
            yabasanshiro.YABASANSHIRO_SOURCE_COMMIT,
            yabasanshiro.YABASANSHIRO_SOURCE_TREE,
        )

    def test_portable_probe_proves_the_v2_contract(self) -> None:
        log = self._log(PORTABLE_PROBE_RUN)
        if log is None:
            self.skipTest("no workspace-local portable YabaSanshiro log present")
        self.assertNotIn("-mcpu=cortex-a53", log)
        self.assertNotIn("-mtune=cortex-a53", log)
        self.assertNotIn("-march=armv8-a+crc+fp+simd", log)
        self.assertTrue(self._proves(log))

    def test_v2_contract_rejects_the_old_tuned_logs(self) -> None:
        checked = 0
        for run_id in TUNED_RUNS:
            log = self._log(run_id)
            if log is None:
                continue
            self.assertIn("-mcpu=cortex-a53", log)
            self.assertFalse(self._proves(log), run_id)
            checked += 1
        if checked == 0:
            self.skipTest("no workspace-local tuned YabaSanshiro logs present")

    def test_v2_contract_rejects_portable_log_mutations(self) -> None:
        log = self._log(PORTABLE_PROBE_RUN)
        if log is None:
            self.skipTest("no workspace-local portable YabaSanshiro log present")
        first_compile = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-gcc -c ")
        )
        mutations = {
            "compile-argv": log.replace(" -D_OGLES3_ ", " -D_OGL3_ ", 1),
            "gles-link": log.replace(" -lGLESv2 ", " ", 1),
            "compile-count": log.replace(first_compile + "\n", "", 1),
        }
        for name, mutated in mutations.items():
            with self.subTest(name=name):
                self.assertNotEqual(log, mutated)
                self.assertFalse(self._proves(mutated))


class YabasanshiroCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/yabasanshiro.json"
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
        self.assertEqual(["arm64"], list(compatibility["targets"].keys()))
        # the generic build links only the VERSIONED GLES soname, present on
        # every probed arm64 device family — the vendor stacks are not needed
        self.assertIn(
            "libGLESv2.so.2", compatibility["targets"]["arm64"]["needed"]
        )
        self.assertFalse(
            any(
                "mali" in name or "IMGegl" in name or "srv_um" in name
                for name in compatibility["targets"]["arm64"]["needed"]
            )
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/yabasanshiro.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
