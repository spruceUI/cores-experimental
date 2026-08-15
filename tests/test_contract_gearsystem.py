"""Gearsystem shared compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import gearsystem
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class GearsystemLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_gearsystem(self) -> None:
        contract = core_log_contract_for(gearsystem.GEARSYSTEM_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("gearsystem-mixed-language-v1", contract.contract_id)
        self.assertEqual("gearsystem_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({gearsystem.GEARSYSTEM_CORE_ID}), contract.core_ids
        )

    def test_catalog_uses_gearsystem_owned_native_describe_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][gearsystem.GEARSYSTEM_CORE_ID]
        identity = gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
        self.assertTrue(gearsystem.gearsystem_spec_is_well_formed(spec))
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_DERIVATION,
            spec["build"]["git_version"]["derivation"],
        )
        self.assertEqual(
            gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_VALUE,
            spec["build"]["git_version"]["value"],
        )

    def test_golden_source_and_build_records_are_bound_exactly(self) -> None:
        identity = gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
        source = {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": {
                "derivation": gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_DERIVATION,
                "value": gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_VALUE,
            },
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            gearsystem.gearsystem_golden_source_is_well_formed(
                gearsystem.GEARSYSTEM_CORE_ID, source
            )
        )
        self.assertTrue(
            gearsystem.gearsystem_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                gearsystem.GEARSYSTEM_CORE_ID,
                source,
            )
        )
        drifted = {**source, "tree": "b" * 40}
        self.assertFalse(
            gearsystem.gearsystem_golden_source_is_well_formed(
                gearsystem.GEARSYSTEM_CORE_ID, drifted
            )
        )

    def test_exact_gearsystem_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, gearsystem.GEARSYSTEM_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    gearsystem.GEARSYSTEM_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    gearsystem,
                    "GEARSYSTEM_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    gearsystem.GEARSYSTEM_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    gearsystem,
                    "GEARSYSTEM_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    gearsystem,
                    "GEARSYSTEM_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        gearsystem.gearsystem_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        gearsystem.gearsystem_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        gearsystem.gearsystem_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            gearsystem.GEARSYSTEM_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
