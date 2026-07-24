#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

from scripts.core_pipeline_lib.runtime import runner_evidence_is_well_formed


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "core_pipeline.py"
SPEC = importlib.util.spec_from_file_location("core_pipeline_runner_evidence", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class RunnerEvidenceTests(unittest.TestCase):
    def test_e2e_cli_defaults_local_and_accepts_explicit_profiles(self) -> None:
        parser = pipeline.build_parser()
        local = parser.parse_args(["e2e", "--core", "handy"])
        native = parser.parse_args(
            ["e2e", "--runner-profile", "github-actions", "--core", "handy"]
        )
        simulated = parser.parse_args(
            [
                "e2e",
                "--runner-profile",
                "github-actions-sim",
                "--core",
                "handy",
            ]
        )
        self.assertEqual("local", local.runner_profile)
        self.assertEqual("github-actions", native.runner_profile)
        self.assertEqual("github-actions-sim", simulated.runner_profile)

    def test_e2e_v1_digest_projection_ignores_runner_extension(self) -> None:
        document = {
            "schema_version": 1,
            "run_id": "gambatte-schema-v1-digest-projection",
            "local_only": True,
            "publication": "disabled",
            "result": "passed",
            "workflow_audit": {},
            "builds": [],
            "packages": [],
        }
        digest = pipeline.e2e_content_sha256(document)
        changed = json.loads(json.dumps(document))
        changed["runner"] = {
            "profile": "local",
            "mode": "native",
            "backend": "local-docker",
            "local_only": True,
            "publication": "disabled",
        }
        self.assertEqual(digest, pipeline.e2e_content_sha256(changed))
        self.assertEqual(
            "gambatte-schema-v1-digest-projection",
            document["run_id"],
        )

    def test_e2e_v2_digest_binds_strict_runner_evidence(self) -> None:
        runner = {
            "profile": "github-actions",
            "mode": "simulated",
            "backend": "local-docker",
            "local_only": True,
            "publication": "disabled",
        }
        self.assertTrue(runner_evidence_is_well_formed(runner))
        document = {
            "schema_version": 2,
            "run_id": "actions-sim-handy-v1",
            "local_only": True,
            "publication": "disabled",
            "runner": runner,
            "result": "passed",
            "workflow_audit": {},
            "builds": [],
            "packages": [],
        }
        digest = pipeline.e2e_content_sha256(document)
        changed = json.loads(json.dumps(document))
        changed["runner"]["mode"] = "native"
        self.assertNotEqual(digest, pipeline.e2e_content_sha256(changed))
        self.assertFalse(runner_evidence_is_well_formed(changed["runner"]))


if __name__ == "__main__":
    unittest.main()
