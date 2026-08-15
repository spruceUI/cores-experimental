from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import quicknes
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.core_contract_helpers import build_mixed_language_log_fixture


ROOT = Path(__file__).resolve().parents[1]


class QuicknesLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_quicknes(self) -> None:
        contract = core_log_contract_for(quicknes.QUICKNES_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("quicknes-cxx-link-v1", contract.contract_id)
        self.assertEqual("quicknes_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({quicknes.QUICKNES_CORE_ID}), contract.core_ids
        )

    def test_catalog_uses_quicknes_owned_identity(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][quicknes.QUICKNES_CORE_ID]
        identity = quicknes.QUICKNES_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(identity, pipeline.QUICKNES_GIT_VERSION_SPEC_IDENTITY)
        self.assertTrue(quicknes.quicknes_spec_is_well_formed(spec))
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(identity["source_key"], spec["build"]["source_key"])
        self.assertEqual(identity["source_dir"], spec["build"]["source_dir"])
        self.assertEqual(identity["output_path"], spec["build"]["output_path"])
        self.assertEqual(identity["artifact_name"], spec["build"]["artifact_name"])
        self.assertEqual(identity["git_version"], spec["build"]["git_version"])
        self.assertEqual(
            identity["metadata_source_path"], spec["metadata"]["source_path"]
        )
        self.assertEqual(
            identity["metadata_artifact_name"],
            spec["metadata"]["artifact_name"],
        )
        self.assertEqual(identity["targets"], spec["targets"])
        self.assertEqual(
            [
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-26bb785",
                "CORE_PIPELINE_GIT_VERSION|-26bb785|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh quicknes",
            pipeline.libretro_build_shell(spec, quicknes.QUICKNES_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][quicknes.QUICKNES_CORE_ID]["build"][
            "git_version"
        ].pop("compiler_scope")
        self.assertFalse(
            quicknes.quicknes_spec_is_well_formed(
                changed["cores"][quicknes.QUICKNES_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "quicknes core must preserve its exact injected version",
        ):
            pipeline.validate_catalog(changed)

    def test_exact_cxx_log_dispatches_through_individual_proof(self) -> None:
        fixture = build_mixed_language_log_fixture(
            pipeline, ROOT, quicknes.QUICKNES_CORE_ID, "arm64"
        )
        self.assertEqual(
            {"cxx": 30},
            quicknes.quicknes_cxx_contract().expected_language_counts,
        )
        self.assertEqual(
            {"cxx"},
            {
                language
                for _output, _source, language, _compiler in fixture["entries"]
            },
        )
        spec = fixture["spec"]
        arguments = (
            fixture["log"],
            quicknes.QUICKNES_CORE_ID,
            "arm64",
            spec["source"]["commit"],
            spec["source"]["tree"],
        )
        with mock.patch.object(
            quicknes,
            "QUICKNES_EXPECTED_COMPILE_PAIR_SHA256",
            fixture["compile_pair_sha256"],
        ), mock.patch.dict(
            quicknes.QUICKNES_EXPECTED_COMPILE_INVOCATION_SHA256,
            {"arm64": fixture["compile_invocation_sha256"]},
        ), mock.patch.object(
            quicknes,
            "QUICKNES_EXPECTED_LINK_OBJECT_SHA256",
            fixture["link_object_sha256"],
        ), mock.patch.object(
            quicknes,
            "QUICKNES_EXPECTED_RAW_LINK_OBJECT_SHA256",
            fixture["raw_link_object_sha256"],
        ):
            self.assertTrue(quicknes.quicknes_log_proves_contract(*arguments))
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(*arguments)
            )
            self.assertFalse(
                quicknes.quicknes_log_proves_contract(
                    fixture["log"],
                    "nestopia",
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )
            self.assertFalse(
                quicknes.quicknes_log_proves_contract(
                    fixture["log"],
                    quicknes.QUICKNES_CORE_ID,
                    "arm64",
                    "0" * 40,
                    spec["source"]["tree"],
                )
            )
            duplicate = fixture["log"] + fixture["compile_lines"][0] + "\n"
            self.assertFalse(
                quicknes.quicknes_log_proves_contract(
                    duplicate,
                    quicknes.QUICKNES_CORE_ID,
                    "arm64",
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
            )


if __name__ == "__main__":
    unittest.main()
