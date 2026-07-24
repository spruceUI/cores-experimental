from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import shlex
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mednafen_vb, mixed_language
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_RUNS = (
    "tranche10b-mednafen-vb-golden-v1",
    "tranche10b-mednafen-vb-repro-v1",
)
SOURCE_PAIRS = (
    ("mednafen/hw_cpu/v810/v810_cpu.o", "mednafen/hw_cpu/v810/v810_cpu.cpp"),
    ("mednafen/mempatcher.o", "mednafen/mempatcher.cpp"),
    ("libretro.o", "libretro.cpp"),
    ("mednafen/vb/vsu.o", "mednafen/vb/vsu.c"),
    ("mednafen/vb/input.o", "mednafen/vb/input.c"),
    ("mednafen/vb/timer.o", "mednafen/vb/timer.c"),
    ("mednafen/vb/vip.o", "mednafen/vb/vip.c"),
    (
        "mednafen/hw_cpu/v810/fpu-new/softfloat.o",
        "mednafen/hw_cpu/v810/fpu-new/softfloat.c",
    ),
    ("mednafen/sound/Blip_Buffer.o", "mednafen/sound/Blip_Buffer.c"),
    ("mednafen/state.o", "mednafen/state.c"),
    ("mednafen/settings.o", "mednafen/settings.c"),
    (
        "libretro-common/compat/compat_strl.o",
        "libretro-common/compat/compat_strl.c",
    ),
    (
        "libretro-common/compat/compat_snprintf.o",
        "libretro-common/compat/compat_snprintf.c",
    ),
)


def historical_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / mednafen_vb.MEDNAFEN_VB_CORE_ID
        / architecture
        / "build.log"
    )


def build_synthetic_log(
    architecture: str,
) -> tuple[mixed_language.MixedLanguageLogContract, str]:
    c_compiler, cxx_compiler = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }[architecture]
    token = mednafen_vb.MEDNAFEN_VB_NATIVE_GIT_VERSION_LOG_TOKEN
    compile_lines = tuple(
        f"{c_compiler if source.endswith('.c') else cxx_compiler} "
        f"-c -o {output} {source} {token} -O2 -fPIC"
        for output, source in SOURCE_PAIRS
    )
    invocations = tuple(
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            {c_compiler, cxx_compiler},
            {cxx_compiler},
        )
        for line in compile_lines
    )
    if any(invocation is None for invocation in invocations):
        raise AssertionError("failed to construct Virtual Boy compile fixture")
    typed_invocations = tuple(
        invocation for invocation in invocations if invocation is not None
    )
    contract = replace(
        mednafen_vb.MEDNAFEN_VB_LOG_CONTRACT,
        expected_compile_invocation_sha256={
            architecture: (
                mixed_language.mixed_language_compile_invocation_sha256(
                    typed_invocations
                )
            )
        },
    )
    link_line = " ".join(
        (
            cxx_compiler,
            "-o",
            mednafen_vb.MEDNAFEN_VB_BUILD_ARTIFACT_NAME,
            *(output for output, _source in SOURCE_PAIRS),
            *mednafen_vb.MEDNAFEN_VB_EXPECTED_LINK_OPTIONS,
        )
    )
    diagnostic_lines = (
        mednafen_vb.MEDNAFEN_VB_EXPECTED_DIAGNOSTIC_CONTEXT[architecture]
    )
    lines = (
        *mednafen_vb.MEDNAFEN_VB_SUCCESS_MARKER,
        mednafen_vb.MEDNAFEN_VB_SOURCE_HEAD_MARKER,
        *compile_lines,
        *diagnostic_lines,
        link_line,
        *mednafen_vb.MEDNAFEN_VB_SUCCESS_TRAILER,
    )
    return contract, "\n".join(lines) + "\n"


@contextmanager
def synthetic_contract(contract: mixed_language.MixedLanguageLogContract):
    with mock.patch.object(
        mednafen_vb, "MEDNAFEN_VB_LOG_CONTRACT", contract
    ):
        yield


class MednafenVbContractTests(unittest.TestCase):
    def contract_arguments(
        self, build_log_text: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = mednafen_vb.MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            build_log_text,
            mednafen_vb.MEDNAFEN_VB_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_registry_identity_is_owned_by_mednafen_vb(self) -> None:
        contract = core_log_contract_for(mednafen_vb.MEDNAFEN_VB_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("mednafen-vb-mixed-language-v1", contract.contract_id)
        self.assertEqual(
            "mednafen_vb_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({mednafen_vb.MEDNAFEN_VB_CORE_ID}), contract.core_ids
        )

    def test_exact_catalog_identity_and_native_version_are_core_owned(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][mednafen_vb.MEDNAFEN_VB_CORE_ID]
        identity = mednafen_vb.MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY

        self.assertIs(
            identity, pipeline.MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertTrue(mednafen_vb.mednafen_vb_spec_is_well_formed(spec))
        self.assertEqual(" 38e7a0e", mednafen_vb.MEDNAFEN_VB_NATIVE_GIT_VERSION)
        self.assertEqual(
            frozenset({"c", "cxx"}),
            mednafen_vb.MEDNAFEN_VB_NATIVE_GIT_VERSION_COMPILER_SCOPE,
        )
        self.assertNotIn("git_version", spec["build"])
        self.assertEqual([], pipeline.git_version_log_markers(spec))
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual("Makefile", identity["native_makefile"])

        changed_catalog = copy.deepcopy(catalog)
        changed_catalog["cores"][mednafen_vb.MEDNAFEN_VB_CORE_ID]["build"][
            "output_path"
        ] = "dist/unix/other.so"
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "mednafen_vb core must preserve its exact native version",
        ):
            pipeline.validate_catalog(changed_catalog)

    def test_exact_spec_rejects_every_owned_boundary(self) -> None:
        spec = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")[
            "cores"
        ][mednafen_vb.MEDNAFEN_VB_CORE_ID]

        def changed(path: tuple[str, ...], value: object) -> dict:
            result = copy.deepcopy(spec)
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return result

        mutations = {
            "workflow": changed(("workflow",), ".github/workflows/other.yml"),
            "source-url": changed(
                ("source", "url"), "https://example.com/other.git"
            ),
            "source-ref": changed(
                ("source", "requested_ref"), "refs/heads/main"
            ),
            "source-commit": changed(("source", "commit"), "0" * 40),
            "source-tree": changed(("source", "tree"), "0" * 40),
            "driver": changed(("build", "driver"), "direct-make"),
            "source-key": changed(("build", "source_key"), "other"),
            "source-dir": changed(("build", "source_dir"), "other"),
            "output": changed(("build", "output_path"), "other.so"),
            "artifact": changed(("build", "artifact_name"), "other.so"),
            "metadata": changed(
                ("metadata", "artifact_name"), "other.info"
            ),
            "targets": changed(("targets",), ["arm64"]),
        }
        extra = copy.deepcopy(spec)
        extra["unexpected"] = True
        mutations["extra"] = extra
        injected = copy.deepcopy(spec)
        injected["build"]["git_version"] = {
            "derivation": "native-space-short7-v1",
            "value": " 38e7a0e",
        }
        mutations["injected-version"] = injected

        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    mednafen_vb.mednafen_vb_spec_is_well_formed(mutation)
                )

    def test_synthetic_logs_prove_both_architectures_and_dispatch(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            arguments = self.contract_arguments(log, architecture)
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                self.assertTrue(
                    mednafen_vb.mednafen_vb_log_proves_contract(*arguments)
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )
                self.assertFalse(
                    mednafen_vb.mednafen_vb_log_proves_contract(
                        log,
                        "mednafen_ngp",
                        architecture,
                        contract.source_commit,
                        contract.source_tree,
                    )
                )
                self.assertFalse(
                    mednafen_vb.mednafen_vb_log_proves_contract(
                        log,
                        mednafen_vb.MEDNAFEN_VB_CORE_ID,
                        architecture,
                        "0" * 40,
                        contract.source_tree,
                    )
                )
                self.assertFalse(
                    mednafen_vb.mednafen_vb_log_proves_contract(
                        log,
                        mednafen_vb.MEDNAFEN_VB_CORE_ID,
                        architecture,
                        contract.source_commit,
                        "0" * 40,
                    )
                )

    def test_synthetic_log_rejects_source_version_and_success_mutations(
        self,
    ) -> None:
        contract, log = build_synthetic_log("arm64")
        arguments = self.contract_arguments(log, "arm64")[1:]
        head = mednafen_vb.MEDNAFEN_VB_SOURCE_HEAD_MARKER
        success = "\n".join(mednafen_vb.MEDNAFEN_VB_SUCCESS_MARKER) + "\n"
        token = mednafen_vb.MEDNAFEN_VB_NATIVE_GIT_VERSION_LOG_TOKEN
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "foreign-head": log + "HEAD is now at 0000000 synthetic\n",
            "missing-fetch-success": log.replace(success, "", 1),
            "duplicate-success": success + log,
            "changed-success-core": log.replace("\tmednafen_vb", "\tother", 1),
            "nonterminal-success": log + "post-success noise\n",
            "wrong-version": log.replace(
                token, r'-DGIT_VERSION=\"" 0000000"\"', 1
            ),
            "pipeline-version": log.replace(
                head + "\n",
                head
                + '\nCORE_PIPELINE_NATIVE_GIT_VERSION|" 38e7a0e"|file\n',
                1,
            ),
            "prefixed-pipeline-version": log.replace(
                head + "\n",
                head
                + '\nprefix CORE_PIPELINE_NATIVE_GIT_VERSION|" 38e7a0e"|file\n',
                1,
            ),
            "injected-version": log.replace(
                head + "\n",
                head
                + "\nCORE_PIPELINE_GIT_VERSION|-38e7a0e|command line\n",
                1,
            ),
            "indented-injected-version": log.replace(
                head + "\n",
                head
                + "\n CORE_PIPELINE_GIT_VERSION|-38e7a0e|command line\n",
                1,
            ),
        }
        with synthetic_contract(contract):
            for label, mutation in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_vb.mednafen_vb_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_synthetic_log_rejects_compile_and_link_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        arguments = self.contract_arguments(log, "arm64")[1:]
        compile_line = next(line for line in log.splitlines() if " -c " in line)
        cxx_line = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-g++ -c ")
        )
        link_line = next(
            line for line in log.splitlines() if " -shared " in line
        )
        mutations = {
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "duplicate-compile": log.replace(
                link_line, compile_line + "\n" + link_line, 1
            ),
            "compile-argv": log.replace(
                compile_line, compile_line.replace("-O2", "-O3", 1), 1
            ),
            "wrong-language": log.replace(
                cxx_line,
                cxx_line.replace(
                    "aarch64-linux-gnu-g++", "aarch64-linux-gnu-gcc", 1
                ),
                1,
            ),
            "link-option": log.replace(
                link_line,
                link_line.replace("-Wl,--no-undefined", "-Wl,--as-needed", 1),
                1,
            ),
            "link-order": log.replace(
                link_line,
                link_line.replace(
                    "mednafen/mempatcher.o libretro.o",
                    "libretro.o mednafen/mempatcher.o",
                    1,
                ),
                1,
            ),
            "raw-link-path": log.replace(
                link_line,
                link_line.replace(
                    "mednafen/mempatcher.o", "./mednafen/mempatcher.o", 1
                ),
                1,
            ),
            "link-compiler": log.replace(
                link_line,
                link_line.replace(
                    "aarch64-linux-gnu-g++", "aarch64-linux-gnu-gcc", 1
                ),
                1,
            ),
        }
        with synthetic_contract(contract):
            for label, mutation in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_vb.mednafen_vb_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_synthetic_log_rejects_diagnostic_mutations(self) -> None:
        forbidden = {
            "warning": "warning: synthetic warning\n",
            "error": "error: synthetic error\n",
            "fatal": "fatal: synthetic fatal\n",
            "undefined": "undefined reference to synthetic_symbol\n",
            "make": "make: *** [all] Error 2\n",
            "killed": "Killed\n",
        }
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            arguments = self.contract_arguments(log, architecture)[1:]
            link_line = next(
                line for line in log.splitlines() if " -shared " in line
            )
            mutations = {
                label: log.replace(link_line, text + link_line, 1)
                for label, text in forbidden.items()
            }
            mutations["unexpected-note"] = log.replace(
                link_line, "synthetic.c:1: note: unexpected\n" + link_line, 1
            )
            if architecture == "armhf":
                context = mednafen_vb.MEDNAFEN_VB_ARMHF_DIAGNOSTIC_CONTEXT
                context_block = "\n".join(context) + "\n"
                mutations["missing-context"] = log.replace(
                    context[0] + "\n", "", 1
                )
                mutations["changed-note"] = log.replace(
                    "changed in GCC 7.1", "changed in GCC 8.1", 1
                )
                mutations["reordered-context"] = log.replace(
                    context[0] + "\n" + context[1],
                    context[1] + "\n" + context[0],
                    1,
                )
                mutations["early-context"] = log.replace(
                    context_block, "", 1
                ).replace(
                    mednafen_vb.MEDNAFEN_VB_SOURCE_HEAD_MARKER,
                    context_block + mednafen_vb.MEDNAFEN_VB_SOURCE_HEAD_MARKER,
                    1,
                )
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                for label, mutation in mutations.items():
                    with self.subTest(mutation=label):
                        self.assertFalse(
                            mednafen_vb.mednafen_vb_log_proves_contract(
                                mutation, *arguments
                            )
                        )

if __name__ == "__main__":
    unittest.main()
