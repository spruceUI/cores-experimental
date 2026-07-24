from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import prosystem
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]
SELECTED_RUN = "actions-sim-build-core-prosystem-w3"


class ProSystemLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_prosystem(self) -> None:
        contract = core_log_contract_for(prosystem.PROSYSTEM_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("prosystem-c-only-v1", contract.contract_id)
        self.assertEqual("prosystem_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({prosystem.PROSYSTEM_CORE_ID}), contract.core_ids)

    def test_exact_catalog_identity_is_core_owned(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][prosystem.PROSYSTEM_CORE_ID]
        identity = prosystem.PROSYSTEM_GIT_VERSION_SPEC_IDENTITY

        self.assertIs(identity, pipeline.PROSYSTEM_GIT_VERSION_SPEC_IDENTITY)
        self.assertTrue(prosystem.prosystem_spec_is_well_formed(spec))
        self.assertEqual(
            {
                "derivation": "hyphen-short7-v1",
                "value": "-363b6df",
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
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-363b6df",
                "CORE_PIPELINE_GIT_VERSION|-363b6df|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh prosystem",
            pipeline.libretro_build_shell(spec, prosystem.PROSYSTEM_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][prosystem.PROSYSTEM_CORE_ID]["build"]["git_version"][
            "compiler_scope"
        ] = "cxx"
        self.assertFalse(
            prosystem.prosystem_spec_is_well_formed(
                changed["cores"][prosystem.PROSYSTEM_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "prosystem core must preserve its exact injected version",
        ):
            pipeline.validate_catalog(changed)

    def test_synthetic_logs_dispatch_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline,
                    ROOT,
                    prosystem.PROSYSTEM_CORE_ID,
                    architecture,
                )
                contract = replace(
                    prosystem.PROSYSTEM_LOG_CONTRACT,
                    expected_compile_pair_sha256=fixture[
                        "compile_pair_sha256"
                    ],
                    expected_compile_invocation_sha256={
                        architecture: fixture["compile_invocation_sha256"]
                    },
                    expected_link_object_sha256=fixture["link_object_sha256"],
                    expected_raw_link_object_sha256=fixture[
                        "raw_link_object_sha256"
                    ],
                )
                arguments = (
                    fixture["log"],
                    prosystem.PROSYSTEM_CORE_ID,
                    architecture,
                    contract.source_commit,
                    contract.source_tree,
                )
                with mock.patch.object(
                    prosystem, "PROSYSTEM_LOG_CONTRACT", contract
                ):
                    self.assertTrue(prosystem.prosystem_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        prosystem.prosystem_log_proves_contract(
                            fixture["log"],
                            "a5200",
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )
                    self.assertFalse(
                        prosystem.prosystem_log_proves_contract(
                            fixture["log"],
                            prosystem.PROSYSTEM_CORE_ID,
                            architecture,
                            "0" * 40,
                            contract.source_tree,
                        )
                    )
                    for label, changed_log in (
                        (
                            "missing-warning",
                            fixture["log"].replace(
                                prosystem.PROSYSTEM_EXPECTED_WARNING_BLOCK + "\n",
                                "",
                            ),
                        ),
                        (
                            "different-warning",
                            fixture["log"].replace(
                                "value computed is not used",
                                "synthetic warning",
                            ),
                        ),
                        (
                            "extra-warning",
                            fixture["log"] + "warning: synthetic warning\n",
                        ),
                        (
                            "cxx-link",
                            fixture["log"].replace(
                                fixture["link_line"],
                                fixture["link_line"].replace(
                                    fixture["c_compiler"],
                                    fixture["cxx_compiler"],
                                    1,
                                ),
                            ),
                        ),
                        (
                            "raw-link-path",
                            fixture["log"].replace(" ./mixed/", " mixed/", 1),
                        ),
                        ("error", fixture["log"] + "error: synthetic failure\n"),
                        ("fatal", fixture["log"] + "fatal: synthetic failure\n"),
                    ):
                        with self.subTest(
                            architecture=architecture,
                            mutation=label,
                        ):
                            self.assertFalse(
                                prosystem.prosystem_log_proves_contract(
                                    changed_log,
                                    prosystem.PROSYSTEM_CORE_ID,
                                    architecture,
                                    contract.source_commit,
                                    contract.source_tree,
                                )
                            )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        identity = prosystem.PROSYSTEM_GIT_VERSION_SPEC_IDENTITY
        log_paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / prosystem.PROSYSTEM_CORE_ID
                / architecture
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        self.assertEqual(
            {"c": 32},
            dict(prosystem.PROSYSTEM_LOG_CONTRACT.expected_language_counts),
        )
        self.assertEqual(
            "c", prosystem.PROSYSTEM_LOG_CONTRACT.expected_link_language
        )
        self.assertEqual(
            prosystem.PROSYSTEM_SEMANTIC_PATH_ALIASES,
            prosystem.PROSYSTEM_LOG_CONTRACT.semantic_path_aliases,
        )
        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                log = log_path.read_text(encoding="utf-8")
                arguments = (
                    log,
                    prosystem.PROSYSTEM_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                self.assertTrue(prosystem.prosystem_log_proves_contract(*arguments))
                self.assertEqual(
                    [prosystem.PROSYSTEM_EXPECTED_WARNING_LINE],
                    [
                        line
                        for line in log.splitlines()
                        if "warning:" in line.casefold()
                    ],
                )


if __name__ == "__main__":
    unittest.main()
