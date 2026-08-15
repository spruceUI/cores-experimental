from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import mixed_language, nestopia
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]
SELECTED_RUN = "actions-sim-build-core-nestopia-w3"


class NestopiaLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_nestopia(self) -> None:
        contract = core_log_contract_for(nestopia.NESTOPIA_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("nestopia-cxx-link-v1", contract.contract_id)
        self.assertEqual("nestopia_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({nestopia.NESTOPIA_CORE_ID}), contract.core_ids
        )

    def test_exact_catalog_identity_is_core_owned(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][nestopia.NESTOPIA_CORE_ID]
        identity = nestopia.NESTOPIA_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(identity, pipeline.NESTOPIA_GIT_VERSION_SPEC_IDENTITY)
        self.assertTrue(nestopia.nestopia_spec_is_well_formed(spec))
        self.assertEqual(
            {
                "compiler_scope": "cxx",
                "derivation": "hyphen-short7-v1",
                "value": "-b0fd87d",
            },
            spec["build"]["git_version"],
        )
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            [
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-b0fd87d",
                "CORE_PIPELINE_GIT_VERSION|-b0fd87d|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh nestopia",
            pipeline.libretro_build_shell(spec, nestopia.NESTOPIA_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][nestopia.NESTOPIA_CORE_ID]["build"][
            "git_version"
        ].pop("compiler_scope")
        self.assertFalse(
            nestopia.nestopia_spec_is_well_formed(
                changed["cores"][nestopia.NESTOPIA_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "nestopia core must preserve its exact injected version",
        ):
            pipeline.validate_catalog(changed)

    def test_reviewed_semantic_path_aliases_are_core_owned(self) -> None:
        aliases = nestopia.nestopia_cxx_contract().semantic_path_aliases
        self.assertEqual(
            "source/core/NstCpu.o",
            mixed_language.mixed_language_semantic_log_path(
                "../source/core/NstCpu.o", ".o", aliases
            ),
        )
        self.assertEqual(
            "libretro/libretro.cpp",
            mixed_language.mixed_language_semantic_log_path(
                "../libretro/libretro.cpp", ".cpp", aliases
            ),
        )
        self.assertIsNone(
            mixed_language.mixed_language_semantic_log_path(
                "../unreviewed/unit.o", ".o", aliases
            )
        )

    def test_synthetic_logs_dispatch_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_mixed_language_log_fixture(
                    pipeline, ROOT, nestopia.NESTOPIA_CORE_ID, architecture
                )
                self.assertEqual(
                    {"cxx": 296},
                    nestopia.nestopia_cxx_contract().expected_language_counts,
                )
                self.assertEqual(
                    {"cxx"},
                    {
                        language
                        for _output, _source, language, _compiler in fixture[
                            "entries"
                        ]
                    },
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    nestopia.NESTOPIA_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    nestopia,
                    "NESTOPIA_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    nestopia.NESTOPIA_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    nestopia,
                    "NESTOPIA_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    nestopia,
                    "NESTOPIA_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        nestopia.nestopia_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        nestopia.nestopia_log_proves_contract(
                            fixture["log"],
                            "quicknes",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        nestopia.nestopia_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            nestopia.NESTOPIA_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        identity = nestopia.NESTOPIA_GIT_VERSION_SPEC_IDENTITY
        log_paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / nestopia.NESTOPIA_CORE_ID
                / architecture
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        contract = nestopia.nestopia_cxx_contract()
        self.assertEqual(296, contract.expected_compile_count)
        self.assertEqual({"cxx": 296}, contract.expected_language_counts)
        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                log = log_path.read_text(encoding="utf-8")
                arguments = (
                    log,
                    nestopia.NESTOPIA_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                self.assertTrue(nestopia.nestopia_log_proves_contract(*arguments))
                self.assertFalse(
                    nestopia.nestopia_log_proves_contract(
                        log,
                        "quicknes",
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
                self.assertFalse(
                    nestopia.nestopia_log_proves_contract(
                        log + "fatal: synthetic failure\n",
                        nestopia.NESTOPIA_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
