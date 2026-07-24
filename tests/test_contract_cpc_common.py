from __future__ import annotations

import unittest

from scripts.core_pipeline_lib.contracts import cap32, crocods
from scripts.core_pipeline_lib.contracts.cpc_common import (
    cpc_compile_command_pair,
    cpc_link_command_objects_for,
)
from scripts.core_pipeline_lib.errors import PipelineError


class CpcCommonContractTests(unittest.TestCase):
    def test_individual_core_identities_are_complete_and_exact(self) -> None:
        for core_id, identity, contract in (
            (
                cap32.CAP32_CORE_ID,
                cap32.CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY,
                cap32.CAP32_LOG_CONTRACT,
            ),
            (
                crocods.CROCODS_CORE_ID,
                crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
                crocods.CROCODS_LOG_CONTRACT,
            ),
        ):
            with self.subTest(core_id=core_id):
                self.assertEqual(core_id, identity["source_key"])
                self.assertEqual(40, len(identity["source_commit"]))
                self.assertEqual(40, len(identity["source_tree"]))
                self.assertEqual(core_id, contract.core_id)
                self.assertEqual(identity["source_commit"], contract.source_commit)
                self.assertEqual(identity["source_tree"], contract.source_tree)

    def test_neutral_compile_and_link_parsers_bind_matching_objects(self) -> None:
        compilers = {"aarch64-linux-gnu-gcc"}
        pair = cpc_compile_command_pair(
            [
                "aarch64-linux-gnu-gcc",
                "-fPIC",
                "-c",
                "core.c",
                "-o",
                "core.o",
            ],
            compilers,
        )
        self.assertEqual(("core.o", "core.c"), pair)
        objects = cpc_link_command_objects_for(
            [
                "aarch64-linux-gnu-gcc",
                "-fPIC",
                "-shared",
                "-Wl,--no-undefined",
                "-lm",
                "core.o",
                "-o",
                crocods.CROCODS_BUILD_ARTIFACT_NAME,
            ],
            compilers,
            crocods.CROCODS_BUILD_ARTIFACT_NAME,
            crocods.CROCODS_EXPECTED_LINK_OPTIONS,
        )
        self.assertEqual({"core.o": 1}, objects)

    def test_individual_proofs_fail_closed_before_log_parsing(self) -> None:
        cases = (
            (
                cap32.CAP32_CORE_ID,
                cap32.CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY,
                cap32.cap32_log_proves_contract,
            ),
            (
                crocods.CROCODS_CORE_ID,
                crocods.CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
                crocods.crocods_log_proves_contract,
            ),
        )
        for core_id, identity, proof in cases:
            with self.subTest(core_id=core_id):
                self.assertFalse(
                    proof(
                        "",
                        "unknown",
                        "arm64",
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
                self.assertFalse(
                    proof(
                        "",
                        core_id,
                        "arm64",
                        "0" * 40,
                        identity["source_tree"],
                    )
                )
                with self.assertRaises(PipelineError):
                    proof(
                        "",
                        core_id,
                        "unknown",
                        identity["source_commit"],
                        identity["source_tree"],
                    )


if __name__ == "__main__":
    unittest.main()
