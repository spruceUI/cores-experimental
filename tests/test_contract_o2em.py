from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import shlex
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import c_only, o2em
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.test_contract_c_only import build_c_only_fixture


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT
    / "tests/fixtures/per-core-oracles/o2em.json"
)
POSITIVE_ORACLE_RUNS = tuple(
    run["run_id"] for run in ORACLE_FIXTURE["positive_runs"]
)
INJECTED_VERSION_CONTROL_RUN = ORACLE_FIXTURE["rejected_comparison"]["run_id"]
SELECTED_RUN = "actions-sim-build-core-o2em-w3"


def build_o2em_native_log_fixture(
    architecture: str,
) -> tuple[c_only.COnlyLogContract, str]:
    """Adapt the neutral C fixture to O2EM's upstream-native version token."""

    fixture_contract, log = build_c_only_fixture(architecture)
    compiler = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }[architecture]
    lines = [
        (
            line.replace(
                " -O2",
                f" {o2em.O2EM_NATIVE_GIT_VERSION_LOG_TOKEN} -O2",
                1,
            )
            if " -c " in line
            else line
        )
        for line in log.splitlines()
    ]
    invocations = [
        c_only.c_only_compile_invocation(shlex.split(line), {compiler})
        for line in lines
        if " -c " in line
    ]
    if any(invocation is None for invocation in invocations):
        raise AssertionError("failed to construct O2EM compile fixture")
    typed_invocations = [
        invocation for invocation in invocations if invocation is not None
    ]
    contract = replace(
        fixture_contract,
        core_id=o2em.O2EM_CORE_ID,
        expected_compile_invocation_sha256={
            architecture: c_only.c_only_compile_invocation_sha256(
                typed_invocations
            )
        },
        expected_raw_compile_invocation_sha256={
            architecture: c_only.c_only_raw_compile_invocation_sha256(
                tuple(shlex.split(line))
                for line in lines
                if " -c " in line
            )
        },
        source_commit=(
            o2em.O2EM_NATIVE_VERSION_SPEC_IDENTITY["source_commit"]
        ),
        source_tree=o2em.O2EM_NATIVE_VERSION_SPEC_IDENTITY["source_tree"],
    )
    return contract, "\n".join(lines) + "\n"


class O2emLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_o2em(self) -> None:
        contract = core_log_contract_for(o2em.O2EM_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("o2em-c-only-v1", contract.contract_id)
        self.assertEqual("o2em_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({o2em.O2EM_CORE_ID}), contract.core_ids)

    def test_exact_catalog_identity_preserves_native_version_derivation(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][o2em.O2EM_CORE_ID]
        identity = o2em.O2EM_NATIVE_VERSION_SPEC_IDENTITY

        self.assertIs(identity, pipeline.O2EM_NATIVE_VERSION_SPEC_IDENTITY)
        self.assertTrue(o2em.o2em_spec_is_well_formed(spec))
        self.assertNotIn("git_version", spec["build"])
        self.assertEqual([], pipeline.git_version_log_markers(spec))
        self.assertEqual(" e03d3be", o2em.O2EM_NATIVE_GIT_VERSION)
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertNotIn("submodules", spec["source"])
        self.assertEqual(
            "./libretro-build.sh o2em",
            pipeline.libretro_build_shell(spec, o2em.O2EM_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][o2em.O2EM_CORE_ID]["build"]["git_version"] = {
            "derivation": "hyphen-short7-v1",
            "value": "-e03d3be",
        }
        self.assertFalse(
            o2em.o2em_spec_is_well_formed(
                changed["cores"][o2em.O2EM_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "o2em core must preserve its exact native version",
        ):
            pipeline.validate_catalog(changed)

    def test_synthetic_logs_dispatch_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                contract, log = build_o2em_native_log_fixture(architecture)
                arguments = (
                    log,
                    o2em.O2EM_CORE_ID,
                    architecture,
                    contract.source_commit,
                    contract.source_tree,
                )
                with mock.patch.object(
                    o2em,
                    "O2EM_EXPECTED_COMPILE_COUNT",
                    contract.expected_compile_count,
                ), mock.patch.object(o2em, "O2EM_LOG_CONTRACT", contract):
                    self.assertTrue(o2em.o2em_log_proves_contract(*arguments))
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        o2em.o2em_log_proves_contract(
                            log,
                            "freechaf",
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )
                    self.assertFalse(
                        o2em.o2em_log_proves_contract(
                            log + "warning: synthetic diagnostic\n",
                            o2em.O2EM_CORE_ID,
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        identity = o2em.O2EM_NATIVE_VERSION_SPEC_IDENTITY
        log_paths = {
            architecture: (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / o2em.O2EM_CORE_ID
                / architecture
                / "build.log"
            )
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    o2em.o2em_log_proves_contract(
                        log_path.read_text(encoding="utf-8"),
                        o2em.O2EM_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
