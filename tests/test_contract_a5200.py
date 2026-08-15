from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import a5200
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.test_contract_c_only import build_c_only_fixture


ROOT = Path(__file__).resolve().parents[1]
SELECTED_RUN = "actions-sim-build-core-a5200-w3"


class A5200LogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_a5200(self) -> None:
        contract = core_log_contract_for(a5200.A5200_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("a5200-c-only-v1", contract.contract_id)
        self.assertEqual("a5200_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({a5200.A5200_CORE_ID}), contract.core_ids)

    def test_exact_catalog_identity_is_core_owned(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][a5200.A5200_CORE_ID]
        identity = a5200.A5200_GIT_VERSION_SPEC_IDENTITY

        self.assertIs(identity, pipeline.A5200_GIT_VERSION_SPEC_IDENTITY)
        self.assertTrue(a5200.a5200_spec_is_well_formed(spec))
        self.assertEqual(
            {
                "derivation": "hyphen-short7-v1",
                "value": "-23c1ea4",
            },
            spec["build"]["git_version"],
        )
        self.assertNotIn("compiler_scope", spec["build"]["git_version"])
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            [
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-23c1ea4",
                "CORE_PIPELINE_GIT_VERSION|-23c1ea4|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh a5200",
            pipeline.libretro_build_shell(spec, a5200.A5200_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][a5200.A5200_CORE_ID]["build"]["git_version"][
            "compiler_scope"
        ] = "cxx"
        self.assertFalse(
            a5200.a5200_spec_is_well_formed(
                changed["cores"][a5200.A5200_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "a5200 core must preserve its exact injected version",
        ):
            pipeline.validate_catalog(changed)

    def test_synthetic_logs_dispatch_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture_contract, log = build_c_only_fixture(architecture)
                contract = replace(
                    fixture_contract,
                    core_id=a5200.A5200_CORE_ID,
                    source_commit=(
                        a5200.A5200_GIT_VERSION_SPEC_IDENTITY["source_commit"]
                    ),
                    source_tree=(
                        a5200.A5200_GIT_VERSION_SPEC_IDENTITY["source_tree"]
                    ),
                )
                arguments = (
                    log,
                    a5200.A5200_CORE_ID,
                    architecture,
                    contract.source_commit,
                    contract.source_tree,
                )
                with mock.patch.object(a5200, "A5200_LOG_CONTRACT", contract):
                    self.assertTrue(a5200.a5200_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        a5200.a5200_log_proves_contract(
                            log,
                            "prosystem",
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )
                    self.assertFalse(
                        a5200.a5200_log_proves_contract(
                            log,
                            a5200.A5200_CORE_ID,
                            architecture,
                            "0" * 40,
                            contract.source_tree,
                        )
                    )
                    self.assertFalse(
                        a5200.a5200_log_proves_contract(
                            log.replace(
                                " src/beta.o src/alpha.o",
                                " ./src/beta.o src/alpha.o",
                            ),
                            a5200.A5200_CORE_ID,
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )
                    self.assertFalse(
                        a5200.a5200_log_proves_contract(
                            log + "fatal: synthetic failure\n",
                            a5200.A5200_CORE_ID,
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        identity = a5200.A5200_GIT_VERSION_SPEC_IDENTITY
        log_paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / a5200.A5200_CORE_ID
                / architecture
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        self.assertEqual(
            36, a5200.A5200_LOG_CONTRACT.expected_compile_count
        )
        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                log = log_path.read_text(encoding="utf-8")
                arguments = (
                    log,
                    a5200.A5200_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                self.assertTrue(a5200.a5200_log_proves_contract(*arguments))
                self.assertFalse(
                    a5200.a5200_log_proves_contract(
                        log + "fatal: synthetic failure\n",
                        a5200.A5200_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
