from __future__ import annotations

from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import handy
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class HandyLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_handy(self) -> None:
        contract = core_log_contract_for(handy.HANDY_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("handy-mixed-language-v1", contract.contract_id)
        self.assertEqual("handy_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({handy.HANDY_CORE_ID}), contract.core_ids)

    def test_catalog_and_command_scope_use_handy_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][handy.HANDY_CORE_ID]
        identity = handy.HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[handy.HANDY_CORE_ID],
        )
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(identity["artifact_name"], spec["build"]["artifact_name"])
        self.assertEqual("cxx", spec["build"]["git_version"]["compiler_scope"])
        self.assertEqual(
            '" bc55d46"', pipeline.command_scoped_native_git_version(spec)
        )

    def test_exact_handy_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, handy.HANDY_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    handy.HANDY_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    handy,
                    "HANDY_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    handy.HANDY_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    handy,
                    "HANDY_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    handy,
                    "HANDY_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(handy.handy_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        handy.handy_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        handy.handy_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            handy.HANDY_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
