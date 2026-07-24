"""RACE shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import race
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_c_only_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class RaceLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_race(self) -> None:
        contract = core_log_contract_for(race.RACE_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("race-c-only-v1", contract.contract_id)
        self.assertEqual("race_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({race.RACE_CORE_ID}), contract.core_ids)

    def test_catalog_uses_race_owned_native_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][race.RACE_CORE_ID]
        identity = race.RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertTrue(race.race_spec_is_well_formed(spec))
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            race.RACE_NATIVE_GIT_VERSION_DERIVATION,
            spec["build"]["git_version"]["derivation"],
        )
        self.assertEqual(
            race.RACE_NATIVE_GIT_VERSION,
            spec["build"]["git_version"]["value"],
        )
        self.assertEqual("c", spec["build"]["git_version"]["compiler_scope"])

    def test_exact_race_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_c_only_log_fixture(
                    pipeline, ROOT, race.RACE_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    race.RACE_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    race,
                    "RACE_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    race.RACE_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    race,
                    "RACE_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    race,
                    "RACE_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(race.race_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        race.race_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        race.race_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            race.RACE_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
