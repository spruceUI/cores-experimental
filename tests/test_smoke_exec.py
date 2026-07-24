"""Tests for the smoke executor's deterministic parse/resolve logic.

The container run itself needs an ARM executor and is exercised out of band; here
we cover the pure pieces: parsing loader output and resolving store artifacts.
"""

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


smoke_exec = _load("smoke_exec")
# Use the exact runtime_smoke instance smoke_exec imported, so exception classes
# and SMOKE_CHECKS identity match (avoids a second, distinct module object).
runtime_smoke = smoke_exec.runtime_smoke


class ParseLoaderOutputTests(unittest.TestCase):
    def _all_pass_text(self) -> str:
        return "\n".join(
            f"CHECK {name} pass" for name in runtime_smoke.SMOKE_CHECKS
        )

    def test_all_pass_lines_map_to_true(self):
        checks = smoke_exec.parse_loader_output(self._all_pass_text())
        self.assertEqual(set(checks), set(runtime_smoke.SMOKE_CHECKS))
        self.assertTrue(all(checks.values()))
        # Build a result to confirm the parse feeds a valid pass.
        result = runtime_smoke.build_smoke_result(
            core_id="gearboy", architecture="arm64", runner="qemu-user",
            provider_profile="generic-arm64", checks=checks,
        )
        self.assertEqual(result["status"], "pass")

    def test_missing_lines_default_to_false(self):
        # A loader that crashes in retro_init never prints init/info/deinit.
        text = "CHECK dlopen pass\nCHECK retro_api_version pass\nCHECK retro_set_environment pass"
        checks = smoke_exec.parse_loader_output(text)
        self.assertTrue(checks["dlopen"])
        self.assertFalse(checks["retro_init"])
        self.assertFalse(checks["retro_deinit"])

    def test_dlopen_failure_is_recorded(self):
        text = "CHECK dlopen fail"
        checks = smoke_exec.parse_loader_output(text)
        self.assertFalse(checks["dlopen"])

    def test_unknown_and_malformed_lines_are_ignored(self):
        text = "CHECK bogus pass\nnoise\nCHECK dlopen pass extra\nCHECK dlopen pass"
        checks = smoke_exec.parse_loader_output(text)
        self.assertTrue(checks["dlopen"])
        self.assertNotIn("bogus", checks)


class ResolveArtifactTests(unittest.TestCase):
    def test_gearboy_arm64_resolves_to_store_cas_path(self):
        # gearboy's arm64 artifact is staged in the local content-addressed store.
        try:
            path = smoke_exec.resolve_artifact("gearboy", "arm64")
        except runtime_smoke.RuntimeSmokeError:
            self.skipTest("local evidence store not present")
        self.assertTrue(path.name.startswith("7f0cab958e27"))
        self.assertIn("store/artifacts/sha256", path.as_posix())

    def test_unknown_target_raises(self):
        with self.assertRaises(runtime_smoke.RuntimeSmokeError):
            smoke_exec.resolve_artifact("gearboy", "sparc")


if __name__ == "__main__":
    unittest.main()
