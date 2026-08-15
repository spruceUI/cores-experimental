from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import shlex
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import c_only, freechaf
from core_pipeline_lib.contracts.registry import core_log_contract_for
from tests.test_contract_c_only import build_c_only_fixture


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT
    / "tests/fixtures/per-core-oracles/freechaf.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])
SELECTED_RUN = "actions-sim-build-core-freechaf-w3"


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / freechaf.FREECHAF_CORE_ID
        / architecture
        / "build.log"
    )


def build_freechaf_native_log_fixture(
    architecture: str,
) -> tuple[c_only.COnlyLogContract, str]:
    """Adapt the neutral C fixture to FreeChaF's native build markers."""

    fixture_contract, log = build_c_only_fixture(architecture)
    compiler = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }[architecture]
    lines = [
        (
            line.replace(
                " -O2",
                f" {freechaf.FREECHAF_NATIVE_GIT_VERSION_LOG_TOKEN} -O2",
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
        raise AssertionError("failed to construct FreeChaF compile fixture")
    typed_invocations = [
        invocation for invocation in invocations if invocation is not None
    ]
    contract = replace(
        fixture_contract,
        core_id=freechaf.FREECHAF_CORE_ID,
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
            freechaf.FREECHAF_NATIVE_VERSION_SPEC_IDENTITY["source_commit"]
        ),
        source_tree=(
            freechaf.FREECHAF_NATIVE_VERSION_SPEC_IDENTITY["source_tree"]
        ),
    )
    lines.extend(
        (
            freechaf.FREECHAF_EXPECTED_WARNING_BLOCK,
            freechaf.FREECHAF_SUBMODULE_CHECKOUT_MARKER,
        )
    )
    return contract, "\n".join(lines) + "\n"


class FreechafLogContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_freechaf(self) -> None:
        contract = core_log_contract_for(freechaf.FREECHAF_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("freechaf-c-only-v1", contract.contract_id)
        self.assertEqual("freechaf_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({freechaf.FREECHAF_CORE_ID}), contract.core_ids)

    def test_exact_catalog_identity_preserves_native_version_derivation(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][freechaf.FREECHAF_CORE_ID]
        identity = freechaf.FREECHAF_NATIVE_VERSION_SPEC_IDENTITY

        self.assertIs(identity, pipeline.FREECHAF_NATIVE_VERSION_SPEC_IDENTITY)
        self.assertTrue(freechaf.freechaf_spec_is_well_formed(spec))
        self.assertNotIn("git_version", spec["build"])
        self.assertEqual([], pipeline.git_version_log_markers(spec))
        self.assertEqual(" 76c7a84", freechaf.FREECHAF_NATIVE_GIT_VERSION)
        self.assertEqual(identity["workflow"], spec["workflow"])
        self.assertEqual(identity["source_url"], spec["source"]["url"])
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual(
            [
                {
                    "path": "src/deps/libretro-common",
                    "commit": "01c6122931a10a7012973054e7067859d2116420",
                }
            ],
            spec["source"]["submodules"],
        )
        self.assertEqual(
            "./libretro-build.sh freechaf",
            pipeline.libretro_build_shell(spec, freechaf.FREECHAF_CORE_ID),
        )

        changed = copy.deepcopy(catalog)
        changed["cores"][freechaf.FREECHAF_CORE_ID]["build"]["git_version"] = {
            "derivation": "hyphen-short7-v1",
            "value": "-76c7a84",
        }
        self.assertFalse(
            freechaf.freechaf_spec_is_well_formed(
                changed["cores"][freechaf.FREECHAF_CORE_ID]
            )
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "freechaf core must preserve its exact native version",
        ):
            pipeline.validate_catalog(changed)

    def test_synthetic_log_dispatch_and_boundaries(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                contract, log = build_freechaf_native_log_fixture(architecture)
                arguments = (
                    log,
                    freechaf.FREECHAF_CORE_ID,
                    architecture,
                    contract.source_commit,
                    contract.source_tree,
                )
                with mock.patch.object(
                    freechaf,
                    "FREECHAF_EXPECTED_COMPILE_COUNT",
                    contract.expected_compile_count,
                ), mock.patch.object(
                    freechaf, "FREECHAF_LOG_CONTRACT", contract
                ):
                    self.assertTrue(
                        freechaf.freechaf_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        freechaf.freechaf_log_proves_contract(
                            log,
                            "o2em",
                            architecture,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )
                    self.assertFalse(
                        freechaf.freechaf_log_proves_contract(
                            log,
                            freechaf.FREECHAF_CORE_ID,
                            architecture,
                            "0" * 40,
                            contract.source_tree,
                        )
                    )
                    other_arch = "armhf" if architecture == "arm64" else "arm64"
                    self.assertFalse(
                        freechaf.freechaf_log_proves_contract(
                            log,
                            freechaf.FREECHAF_CORE_ID,
                            other_arch,
                            contract.source_commit,
                            contract.source_tree,
                        )
                    )

    def test_synthetic_log_rejects_diagnostic_and_source_marker_mutations(
        self,
    ) -> None:
        contract, log = build_freechaf_native_log_fixture("arm64")
        arguments = (
            freechaf.FREECHAF_CORE_ID,
            "arm64",
            contract.source_commit,
            contract.source_tree,
        )
        mutations = {
            "missing-warning": log.replace(
                freechaf.FREECHAF_EXPECTED_WARNING_BLOCK, "", 1
            ),
            "changed-warning": log.replace("unused variable", "unused value", 1),
            "extra-warning": log + "warning: synthetic warning\n",
            "missing-submodule": log.replace(
                freechaf.FREECHAF_SUBMODULE_CHECKOUT_MARKER, "", 1
            ),
            "wrong-submodule": log.replace(
                freechaf.FREECHAF_SUBMODULE_COMMIT, "0" * 40, 1
            ),
            "extra-submodule": (
                log
                + "Submodule path 'src/deps/extra': checked out '"
                + "0" * 40
                + "'\n"
            ),
            "injected-version": (
                log + "CORE_PIPELINE_GIT_VERSION|-76c7a84|command line\n"
            ),
            "changed-version": log.replace(
                freechaf.FREECHAF_NATIVE_GIT_VERSION_LOG_TOKEN,
                r'-DGIT_VERSION=\"-76c7a84\"',
                1,
            ),
            "note": log + "note: synthetic note\n",
            "error": log + "error: synthetic error\n",
            "undefined": log + "undefined reference to synthetic_symbol\n",
            "linker": log + "aarch64-linux-gnu-ld: cannot find -lsynthetic\n",
            "linker-object": (
                log
                + "aarch64-linux-gnu-ld: cannot find missing.o: "
                + "No such file or directory\n"
            ),
            "make": log + "make: *** [all] Error 2\n",
            "killed": log + "Killed\n",
            "segfault": log + "Segmentation fault\n",
            "terminated": log + "Terminated\n",
            "bus-error": log + "Bus error\n",
            "illegal-instruction": log + "Illegal instruction\n",
            "compilation-terminated": log + "compilation terminated.\n",
        }
        with mock.patch.object(
            freechaf,
            "FREECHAF_EXPECTED_COMPILE_COUNT",
            contract.expected_compile_count,
        ), mock.patch.object(freechaf, "FREECHAF_LOG_CONTRACT", contract):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        freechaf.freechaf_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_synthetic_log_rejects_compile_and_link_mutations(self) -> None:
        contract, log = build_freechaf_native_log_fixture("arm64")
        arguments = (
            freechaf.FREECHAF_CORE_ID,
            "arm64",
            contract.source_commit,
            contract.source_tree,
        )
        compile_line = next(line for line in log.splitlines() if " -c " in line)
        link_line = next(
            line for line in log.splitlines() if " -shared " in line
        )
        changed_link_operand = link_line.replace(
            "src/beta.o", "src/alpha.o", 1
        )
        raw_path_drift = link_line.replace(
            "src/beta.o", "./src/beta.o", 1
        )
        cxx_compile = compile_line.replace(
            "aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++", 1
        )
        mutations = {
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "duplicate-compile": log + compile_line + "\n",
            "compile-argv": log.replace(
                compile_line, compile_line.replace("-O2", "-O3", 1), 1
            ),
            "cxx-substitution": log.replace(compile_line, cxx_compile, 1),
            "link-option": log.replace(
                link_line,
                link_line.replace("-Wl,--no-undefined", "-Wl,--as-needed", 1),
                1,
            ),
            "link-operand": log.replace(link_line, changed_link_operand, 1),
            "raw-path": log.replace(link_line, raw_path_drift, 1),
        }
        with mock.patch.object(
            freechaf,
            "FREECHAF_EXPECTED_COMPILE_COUNT",
            contract.expected_compile_count,
        ), mock.patch.object(freechaf, "FREECHAF_LOG_CONTRACT", contract):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        freechaf.freechaf_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_individual_selected_logs_prove_exact_contract(self) -> None:
        identity = freechaf.FREECHAF_NATIVE_VERSION_SPEC_IDENTITY
        log_paths = {
            architecture: oracle_log_path(SELECTED_RUN, architecture)
            for architecture in identity["targets"]
        }
        missing = [str(path) for path in log_paths.values() if not path.is_file()]
        if missing:
            self.skipTest("workspace-local selected logs are unavailable")

        for architecture, log_path in log_paths.items():
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    freechaf.freechaf_log_proves_contract(
                        log_path.read_text(encoding="utf-8"),
                        freechaf.FREECHAF_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
