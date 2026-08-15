"""Focused gpSP catalog, contract, and canonical-state tests."""

from __future__ import annotations

import unittest

from .support import pipeline
from core_pipeline_lib.contracts import gpsp

from .support import ROOT, load_document
from .support import evidence_handles


CORE_ID = "gpsp"

_H = evidence_handles(CORE_ID)
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]

SOURCE_URL = _H["SOURCE_URL"]

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
