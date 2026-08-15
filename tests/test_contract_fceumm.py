from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import fceumm
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.test_contract_c_only import build_c_only_fixture


ROOT = Path(__file__).resolve().parents[1]


class FceummLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_fceumm(self) -> None:
        contract = core_log_contract_for(fceumm.FCEUMM_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("fceumm-c-only-v1", contract.contract_id)
        self.assertEqual("fceumm_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({fceumm.FCEUMM_CORE_ID}), contract.core_ids)

    def test_catalog_and_command_scope_use_fceumm_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][fceumm.FCEUMM_CORE_ID]
        identity = fceumm.FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[fceumm.FCEUMM_CORE_ID],
        )
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(identity["artifact_name"], spec["build"]["artifact_name"])
        self.assertEqual("c", spec["build"]["git_version"]["compiler_scope"])
        self.assertEqual(
            '" 718c5a2"', pipeline.command_scoped_native_git_version(spec)
        )

    def test_exact_fceumm_log_dispatches_through_individual_proof(self) -> None:
        fixture_contract, log = build_c_only_fixture()
        contract = replace(
            fixture_contract,
            core_id=fceumm.FCEUMM_CORE_ID,
            source_commit=(
                fceumm.FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"]
            ),
            source_tree=(
                fceumm.FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_tree"]
            ),
        )
        arguments = (
            log,
            fceumm.FCEUMM_CORE_ID,
            "arm64",
            contract.source_commit,
            contract.source_tree,
        )
        with mock.patch.object(fceumm, "FCEUMM_LOG_CONTRACT", contract):
            self.assertTrue(fceumm.fceumm_log_proves_contract(*arguments))
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(*arguments)
            )
            self.assertFalse(
                fceumm.fceumm_log_proves_contract(
                    log,
                    "other",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                fceumm.fceumm_log_proves_contract(
                    log + "dubious ownership\n",
                    fceumm.FCEUMM_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                )
            )


if __name__ == "__main__":
    unittest.main()
