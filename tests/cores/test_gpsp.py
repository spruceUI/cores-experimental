"""Focused gpSP catalog, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import gpsp

from .support import ROOT, load_document


CORE_ID = "gpsp"
SOURCE_URL = "https://github.com/libretro/gpsp.git"
SOURCE_COMMIT = "69e86ebe89f14c3f5f75b809c12c0a953b3d6ce4"
SOURCE_TREE = "de26635ae1419714d0efe3c85b75faf494be950c"
SELECTED_RUN = "actions-sim-build-core-gpsp-w3"
REPRODUCTION_RUN = "build-core-gpsp-local-w3"


class GpspManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_document(ROOT / "manifests/core-builds.json")
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_direct_make_recipe(self) -> None:
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual(
            {
                "driver": "direct-make",
                "source_dir": "gpsp",
                "output_path": "gpsp_libretro.so",
                "artifact_name": "gpsp_libretro.so",
                "platforms": {"arm64": "arm64", "armhf": "armv7hardfloat"},
            },
            self.spec["build"],
        )
        self.assertEqual(["arm64", "armhf"], self.spec["targets"])

    def test_spec_is_well_formed_pins_the_catalog_identity(self) -> None:
        self.assertTrue(gpsp.gpsp_spec_is_well_formed(self.spec))
        mutated = {
            **self.spec,
            "build": {
                **self.spec["build"],
                "platforms": {"arm64": "arm64", "armhf": "armhf"},
            },
        }
        self.assertFalse(gpsp.gpsp_spec_is_well_formed(mutated))


class GpspCompatibilityTests(unittest.TestCase):
    def test_promoted_compatibility_is_valid_and_canonical(self) -> None:
        compatibility_path = ROOT / "manifests/compatibility/gpsp.json"
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
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/gpsp.json").exists()
        )
        # Its two C++ units do not pull in libstdc++, so gpSP clears every
        # device provider ceiling (including the Miyoo Mini).
        for arch in ("arm64", "armhf"):
            needed = compatibility["targets"][arch]["needed"]
            self.assertNotIn("libstdc++.so.6", needed)


class GpspContractTests(unittest.TestCase):
    def _log(self, run_id: str, arch: str) -> str | None:
        path = (
            ROOT / ".local-e2e" / "runs" / run_id / CORE_ID / arch / "build.log"
        )
        return path.read_text(encoding="utf-8") if path.is_file() else None

    def test_real_logs_prove_the_exact_contract(self) -> None:
        proven = 0
        for run_id in (SELECTED_RUN, REPRODUCTION_RUN):
            for arch in ("arm64", "armhf"):
                log = self._log(run_id, arch)
                if log is None:
                    continue
                self.assertTrue(
                    gpsp.gpsp_log_proves_contract(
                        log, CORE_ID, arch, SOURCE_COMMIT, SOURCE_TREE
                    ),
                    f"{run_id}/{arch} did not prove the gpSP contract",
                )
                proven += 1
        if proven == 0:
            self.skipTest("no workspace-local gpSP build logs present")

    def test_contract_rejects_a_wrong_cxx_count(self) -> None:
        from unittest import mock

        log = self._log(SELECTED_RUN, "arm64") or self._log(
            REPRODUCTION_RUN, "arm64"
        )
        if log is None:
            self.skipTest("no workspace-local gpSP build log present")
        with mock.patch.object(
            gpsp, "GPSP_EXPECTED_CXX_COMPILE_COUNT", {"arm64": 3, "armhf": 2}
        ):
            self.assertFalse(
                gpsp.gpsp_log_proves_contract(
                    log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )


if __name__ == "__main__":
    unittest.main()
