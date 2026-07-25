"""2048 shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import core_2048
from core_pipeline_lib.contracts.registry import core_log_contract_for
from core_pipeline_lib.foundation import sha256_file
from tests.core_contract_helpers import build_c_only_log_fixture


ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOCK_FILE_SHA256 = (
    "1a91c8cc3f0349ec6b191fa5a14c1e3bd48f84086950cad2836fe11085ff6ce6"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "c89f2f646f2c3c1414a2a8969488e29d6ff2d6002be3e73c41c789851ee2f55a"
)


class Core2048ContractTests(unittest.TestCase):
    def test_source_lock_is_exact_and_catalog_bound(self) -> None:
        identity = core_2048.CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
        source_lock = registry.composed_source_lock("2048")

        registry.validate_source_lock(
            source_lock,
        )
        self.assertEqual("2048-c90437d3c391", source_lock["source_lock_id"])
        self.assertEqual(core_2048.CORE_2048_ID, source_lock["core_id"])
        self.assertEqual(
            {
                "url": identity["source_url"],
                "requested_ref": identity["source_requested_ref"],
                "commit": identity["source_commit"],
                "tree": identity["source_tree"],
                "submodules": [],
            },
            source_lock["source"],
        )
        self.assertEqual(
            SOURCE_LOCK_CONTENT_SHA256,
            registry.canonical_content_sha256(source_lock),
        )

    def test_registry_identity_is_owned_by_2048(self) -> None:
        contract = core_log_contract_for(core_2048.CORE_2048_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("core-2048-c-only-v1", contract.contract_id)
        self.assertEqual("core_2048_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertEqual(
            frozenset({core_2048.CORE_2048_ID}), contract.core_ids
        )

    def test_exact_catalog_and_promoted_record_contracts(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = core_2048.CORE_2048_ID
        spec = catalog["cores"][core_id]
        identity = core_2048.CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
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
                "derivation": (
                    core_2048.CORE_2048_NATIVE_GIT_VERSION_DERIVATION
                ),
                "value": core_2048.CORE_2048_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
            "log": "build.log",
            "log_sha256": "a" * 64,
        }

        self.assertIs(
            identity, pipeline.CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertTrue(core_2048.core_2048_spec_is_well_formed(spec))
        self.assertTrue(
            core_2048.core_2048_golden_source_is_well_formed(core_id, source)
        )
        self.assertTrue(
            core_2048.core_2048_golden_build_contract_is_well_formed(
                build, identity["source_commit"], core_id, source
            )
        )
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" c90437d"|file'],
            pipeline.git_version_log_markers(spec),
        )
        self.assertEqual(
            "./libretro-build.sh 2048",
            pipeline.libretro_build_shell(spec, core_id),
        )

        wrong_spec = copy.deepcopy(spec)
        wrong_spec["build"]["git_version"]["compiler_scope"] = "cxx"
        self.assertFalse(core_2048.core_2048_spec_is_well_formed(wrong_spec))
        changed_catalog = copy.deepcopy(catalog)
        changed_catalog["cores"][core_id] = wrong_spec
        with self.assertRaisesRegex(pipeline.PipelineError, r"cores\.2048"):
            pipeline.validate_catalog(changed_catalog)
        wrong_source = copy.deepcopy(source)
        wrong_source["submodules"] = [
            {"path": "injected", "commit": "0" * 40}
        ]
        self.assertFalse(
            core_2048.core_2048_golden_source_is_well_formed(
                core_id, wrong_source
            )
        )
        wrong_build = copy.deepcopy(build)
        wrong_build["git_version"]["compiler_scope"] = "cxx"
        self.assertFalse(
            core_2048.core_2048_golden_build_contract_is_well_formed(
                wrong_build, identity["source_commit"], core_id, source
            )
        )

    def test_exact_2048_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_c_only_log_fixture(
                    pipeline, ROOT, core_2048.CORE_2048_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    core_2048.CORE_2048_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    core_2048,
                    "CORE_2048_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    core_2048.CORE_2048_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    core_2048,
                    "CORE_2048_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    core_2048,
                    "CORE_2048_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        core_2048.core_2048_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        core_2048.core_2048_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        core_2048.core_2048_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            core_2048.CORE_2048_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
