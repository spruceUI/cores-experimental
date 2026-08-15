from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import hashlib
from pathlib import Path
import shlex
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import mednafen_lynx, mixed_language
from core_pipeline_lib.contracts.command_line import ordered_command_argv_sha256
from core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_RUNS = (
    "tranche13b-mednafen-lynx-golden-v1",
    "tranche13b-mednafen-lynx-repro-v1",
)
HISTORICAL_LOG_SHA256 = {
    "arm64": "43e8b082c99744994b5189bac9393590ba2bf2bf7ebe46bbf25f45c72dcd2ccf",
    "armhf": "70a98dd3eea6a059d7b181791bfeaf81feba36565b0b55185aeb4d3912939d55",
}
CXX_OBJECTS = frozenset(
    {
        "mednafen/lynx/cart.o",
        "mednafen/lynx/c65c02.o",
        "mednafen/lynx/memmap.o",
        "mednafen/lynx/mikie.o",
        "mednafen/lynx/ram.o",
        "mednafen/lynx/rom.o",
        "mednafen/lynx/susie.o",
        "mednafen/lynx/system.o",
        "mednafen/sound/Blip_Buffer.o",
        "mednafen/settings.o",
        "mednafen/state.o",
        "mednafen/mempatcher.o",
        "mednafen/md5.o",
        "mednafen/sound/Stereo_Buffer.o",
        "mednafen/endian.o",
        "libretro.o",
    }
)
SOURCE_PAIRS = tuple(
    (
        output,
        output.removesuffix(".o")
        + (".cpp" if output in CXX_OBJECTS else ".c"),
    )
    for output in mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_LINK_OBJECTS
)


def historical_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / mednafen_lynx.MEDNAFEN_LYNX_CORE_ID
        / architecture
        / "build.log"
    )


def parsed_commands(
    log: str, architecture: str
) -> tuple[list[tuple], list[tuple[str, ...]]]:
    compilers = TARGET_COMPILERS[architecture]
    cxx_compilers = TARGET_CXX_COMPILERS[architecture]
    invocations = []
    links = []
    for line in log.splitlines():
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens or tokens[0] not in compilers:
            continue
        if "-c" in tokens:
            invocation = mixed_language.mixed_language_compile_invocation(
                tokens, compilers, cxx_compilers
            )
            if invocation is None:
                raise AssertionError("failed to parse Mednafen Lynx compile fixture")
            invocations.append(invocation)
        elif mednafen_lynx.MEDNAFEN_LYNX_BUILD_ARTIFACT_NAME in tokens:
            links.append(tuple(tokens))
    return invocations, links


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
    version_token = mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_LOG_TOKEN
    compile_lines = tuple(
        " ".join(
            (
                cxx_compiler if source.endswith(".cpp") else c_compiler,
                "-c",
                "-o",
                output,
                source,
                *((version_token,) if source.endswith(".cpp") else ()),
                "-DMEDNAFEN_VERSION_NUMERIC=1240",
                "-O2",
                "-fPIC",
            )
        )
        for output, source in SOURCE_PAIRS
    )
    invocations, _links = parsed_commands(
        "\n".join(compile_lines), architecture
    )
    contract = replace(
        mednafen_lynx.MEDNAFEN_LYNX_LOG_CONTRACT,
        expected_compile_invocation_sha256={
            architecture: (
                mixed_language.mixed_language_compile_invocation_sha256(
                    invocations
                )
            )
        },
    )
    link_line = " ".join(
        mednafen_lynx.MEDNAFEN_LYNX_EXPECTED_ORDERED_LINK_ARGV[architecture]
    )
    lines = (
        *mednafen_lynx.MEDNAFEN_LYNX_SUCCESS_MARKER,
        mednafen_lynx.MEDNAFEN_LYNX_SOURCE_HEAD_MARKER,
        *compile_lines,
        *mednafen_lynx.MEDNAFEN_LYNX_TRUNCATION_CONTEXT[architecture],
        *(
            mednafen_lynx.MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT
            if architecture == "armhf"
            else ()
        ),
        link_line,
        *mednafen_lynx.MEDNAFEN_LYNX_SUCCESS_TRAILER,
    )
    return contract, "\n".join(lines) + "\n"


@contextmanager
def synthetic_contract(contract: mixed_language.MixedLanguageLogContract):
    with mock.patch.object(
        mednafen_lynx, "MEDNAFEN_LYNX_LOG_CONTRACT", contract
    ):
        yield


class MednafenLynxContractTests(unittest.TestCase):
    def contract_arguments(
        self, build_log_text: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = (
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        return (
            build_log_text,
            mednafen_lynx.MEDNAFEN_LYNX_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_registry_and_catalog_identity_are_core_owned(self) -> None:
        contract = core_log_contract_for(
            mednafen_lynx.MEDNAFEN_LYNX_CORE_ID
        )
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "mednafen-lynx-mixed-language-v1", contract.contract_id
        )
        self.assertEqual(
            "mednafen_lynx_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({mednafen_lynx.MEDNAFEN_LYNX_CORE_ID}),
            contract.core_ids,
        )

        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][mednafen_lynx.MEDNAFEN_LYNX_CORE_ID]
        identity = (
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertIs(
            identity,
            pipeline.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
        )
        self.assertTrue(
            mednafen_lynx.mednafen_lynx_spec_is_well_formed(spec)
        )
        self.assertEqual(
            " fcdefcf", mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION
        )
        self.assertEqual(
            frozenset({"cxx"}),
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_COMPILER_SCOPE,
        )
        self.assertEqual(
            {"c": 0, "cxx": 1},
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE,
        )
        self.assertNotIn("git_version", spec["build"])
        self.assertEqual([], pipeline.git_version_log_markers(spec))
        self.assertEqual("Makefile", identity["native_makefile"])

        changed_catalog = copy.deepcopy(catalog)
        changed_catalog["cores"][mednafen_lynx.MEDNAFEN_LYNX_CORE_ID][
            "build"
        ]["output_path"] = "dist/unix/other.so"
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "mednafen_lynx core must preserve its exact native version",
        ):
            pipeline.validate_catalog(changed_catalog)

    def test_exact_spec_rejects_every_owned_boundary(self) -> None:
        spec = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")[
            "cores"
        ][mednafen_lynx.MEDNAFEN_LYNX_CORE_ID]

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
            "metadata-source": changed(
                ("metadata", "source_path"), "/tmp/other.info"
            ),
            "metadata-artifact": changed(
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
            "value": " fcdefcf",
        }
        mutations["injected-version"] = injected

        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    mednafen_lynx.mednafen_lynx_spec_is_well_formed(mutation)
                )

    def test_synthetic_logs_and_parallel_diagnostic_orders_pass(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            warning_block = "\n".join(
                mednafen_lynx.MEDNAFEN_LYNX_TRUNCATION_CONTEXT[architecture]
            ) + "\n"
            libretro_compile = next(
                line
                for line in log.splitlines()
                if " -c -o libretro.o libretro.cpp " in line
            )
            warning_during_parallel_compiles = log.replace(
                warning_block, "", 1
            ).replace(
                libretro_compile + "\n",
                libretro_compile + "\n" + warning_block,
                1,
            )
            passing_logs = [log, warning_during_parallel_compiles]
            if architecture == "armhf":
                psabi_block = "\n".join(
                    mednafen_lynx.MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT
                ) + "\n"
                mempatcher_compile = next(
                    line
                    for line in log.splitlines()
                    if " -c -o mednafen/mempatcher.o " in line
                )
                notes_during_parallel_compiles = log.replace(
                    psabi_block, "", 1
                ).replace(
                    mempatcher_compile + "\n",
                    mempatcher_compile + "\n" + psabi_block,
                    1,
                )
                notes_first = log.replace(psabi_block, "", 1).replace(
                    warning_block,
                    psabi_block + warning_block,
                    1,
                )
                passing_logs.extend(
                    (notes_during_parallel_compiles, notes_first)
                )

            with synthetic_contract(contract):
                for label, candidate in enumerate(passing_logs):
                    arguments = self.contract_arguments(
                        candidate, architecture
                    )
                    with self.subTest(
                        architecture=architecture, scheduling=label
                    ):
                        self.assertTrue(
                            mednafen_lynx.mednafen_lynx_log_proves_contract(
                                *arguments
                            )
                        )
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                *arguments
                            )
                        )

    def test_log_rejects_identity_source_and_success_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        identity = (
            mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        valid = self.contract_arguments(log, "arm64")
        invalid_arguments = (
            (log, "mednafen_ngp", "arm64", valid[3], valid[4]),
            (log, valid[1], "unknown", valid[3], valid[4]),
            (log, valid[1], "arm64", "0" * 40, valid[4]),
            (log, valid[1], "arm64", valid[3], "0" * 40),
            (None, valid[1], "arm64", valid[3], valid[4]),
        )
        head = mednafen_lynx.MEDNAFEN_LYNX_SOURCE_HEAD_MARKER
        success = "\n".join(
            mednafen_lynx.MEDNAFEN_LYNX_SUCCESS_MARKER
        ) + "\n"
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "foreign-head": log + "HEAD is now at 0000000 synthetic\n",
            "missing-fetch-success": log.replace(success, "", 1),
            "separated-fetch-success": log.replace(
                success + head, success + "unexpected framing\n" + head, 1
            ),
            "duplicate-success": success + log,
            "changed-success-core": log.replace("\tmednafen_lynx", "\tother", 1),
            "changed-copy": log.replace(
                'cp "mednafen_lynx_libretro.so"',
                'cp "other.so"',
                1,
            ),
            "nonterminal-success": log + "post-success noise\n",
            "pipeline-version": log.replace(
                head + "\n",
                head
                + '\nCORE_PIPELINE_NATIVE_GIT_VERSION|" fcdefcf"|file\n',
                1,
            ),
        }
        with synthetic_contract(contract):
            for arguments in invalid_arguments:
                with self.subTest(arguments=arguments[1:]):
                    self.assertFalse(
                        mednafen_lynx.mednafen_lynx_log_proves_contract(
                            *arguments
                        )
                    )
            for label, mutation in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_lynx.mednafen_lynx_log_proves_contract(
                            mutation,
                            mednafen_lynx.MEDNAFEN_LYNX_CORE_ID,
                            "arm64",
                            identity["source_commit"],
                            identity["source_tree"],
                        )
                    )

    def test_log_rejects_compile_version_and_link_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        arguments = self.contract_arguments(log, "arm64")[1:]
        c_line = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-gcc -c ")
        )
        cxx_line = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-g++ -c ")
        )
        link_line = next(
            line for line in log.splitlines() if " -shared " in line
        )
        token = mednafen_lynx.MEDNAFEN_LYNX_NATIVE_GIT_VERSION_LOG_TOKEN
        mutations = {
            "missing-compile": log.replace(c_line + "\n", "", 1),
            "duplicate-compile": log.replace(
                link_line, c_line + "\n" + link_line, 1
            ),
            "compile-argv": log.replace(
                c_line, c_line.replace("-O2", "-O3", 1), 1
            ),
            "wrong-language": log.replace(
                cxx_line,
                cxx_line.replace(
                    "aarch64-linux-gnu-g++", "aarch64-linux-gnu-gcc", 1
                ),
                1,
            ),
            "missing-cxx-version": log.replace(
                cxx_line, cxx_line.replace(token + " ", "", 1), 1
            ),
            "version-on-c": log.replace(
                c_line, c_line.replace(" -O2", " " + token + " -O2", 1), 1
            ),
            "duplicate-cxx-version": log.replace(
                cxx_line, cxx_line.replace(token, token + " " + token, 1), 1
            ),
            "wrong-version": log.replace(
                token, r'-DGIT_VERSION=\"" 0000000"\"', 1
            ),
            "link-option": log.replace(
                link_line,
                link_line.replace("-Wl,--no-undefined", "-Wl,--as-needed", 1),
                1,
            ),
            "link-order": log.replace(
                link_line,
                link_line.replace(
                    "mednafen/lynx/cart.o mednafen/lynx/c65c02.o",
                    "mednafen/lynx/c65c02.o mednafen/lynx/cart.o",
                    1,
                ),
                1,
            ),
            "raw-link-path": log.replace(
                link_line,
                link_line.replace(
                    "mednafen/lynx/cart.o", "./mednafen/lynx/cart.o", 1
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
                        mednafen_lynx.mednafen_lynx_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_log_rejects_diagnostic_mutations_and_invalid_interleaving(
        self,
    ) -> None:
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            arguments = self.contract_arguments(log, architecture)[1:]
            truncation_context = (
                mednafen_lynx.MEDNAFEN_LYNX_TRUNCATION_CONTEXT[architecture]
            )
            warning_block = "\n".join(truncation_context) + "\n"
            link_line = next(
                line for line in log.splitlines() if " -shared " in line
            )
            first_compile = next(
                line for line in log.splitlines() if " -c " in line
            )
            mutations = {
                "missing-warning-context": log.replace(
                    truncation_context[0] + "\n", "", 1
                ),
                "changed-warning": log.replace(
                    "may be truncated", "synthetic warning", 1
                ),
                "unexpected-warning": log.replace(
                    link_line,
                    "synthetic.cpp:1: warning: unexpected\n" + link_line,
                    1,
                ),
                "unexpected-note": log.replace(
                    link_line,
                    "synthetic.cpp:1: note: unexpected\n" + link_line,
                    1,
                ),
                "error": log.replace(
                    link_line, "synthetic.cpp:1: error: failure\n" + link_line, 1
                ),
                "fatal": log.replace(
                    link_line, "fatal: synthetic failure\n" + link_line, 1
                ),
                "make-failure": log.replace(
                    link_line, "make: *** [all] Error 2\n" + link_line, 1
                ),
                "warning-before-source-compile": log.replace(
                    warning_block, "", 1
                ).replace(first_compile, warning_block + first_compile, 1),
                "warning-after-link": log.replace(
                    warning_block, "", 1
                ).replace(
                    link_line + "\n", link_line + "\n" + warning_block, 1
                ),
                "split-warning-context": log.replace(
                    truncation_context[2] + "\n",
                    truncation_context[2] + "\nnoise between warning lines\n",
                    1,
                ),
            }
            if architecture == "armhf":
                psabi_context = (
                    mednafen_lynx.MEDNAFEN_LYNX_ARMHF_PSABI_CONTEXT
                )
                psabi_block = "\n".join(psabi_context) + "\n"
                mutations["missing-psabi-context"] = log.replace(
                    psabi_context[0] + "\n", "", 1
                )
                mutations["changed-psabi-note"] = log.replace(
                    "changed in GCC 7.1", "changed in GCC 8.1", 1
                )
                mutations["psabi-before-source-compile"] = log.replace(
                    psabi_block, "", 1
                ).replace(first_compile, psabi_block + first_compile, 1)
                # Parallel make interleaves diagnostic blocks in real logs
                # (observed live on 2026-07-23: the armhf psabi block split
                # and reordered between two content-identical builds), so
                # block reordering and interleaving are ACCEPTED now -- every
                # diagnostic line stays exactly pinned by the multiset and
                # framing checks. These two shapes moved from rejected to
                # accepted deliberately.
                accepted_reorders = {
                    "split-psabi-context": log.replace(
                        psabi_context[3] + "\n",
                        psabi_context[3] + "\nnoise between psABI lines\n",
                        1,
                    ),
                }
                # Injecting the psabi block INSIDE the truncation block still
                # rejects: the truncation context keeps its contiguity check
                # (both live logs held it contiguous), and splitting it is a
                # framing violation, not a scheduling reorder.
                mutations["interleaved-diagnostic-blocks"] = log.replace(
                    psabi_block, "", 1
                ).replace(
                    truncation_context[2] + "\n",
                    truncation_context[2] + "\n" + psabi_block,
                    1,
                )
                with synthetic_contract(contract):
                    for label, mutation in accepted_reorders.items():
                        with self.subTest(
                            architecture=architecture, mutation=label
                        ):
                            self.assertTrue(
                                mednafen_lynx.mednafen_lynx_log_proves_contract(
                                    mutation, *arguments
                                )
                            )
            with synthetic_contract(contract):
                for label, mutation in mutations.items():
                    with self.subTest(
                        architecture=architecture, mutation=label
                    ):
                        self.assertFalse(
                            mednafen_lynx.mednafen_lynx_log_proves_contract(
                                mutation, *arguments
                            )
                        )

if __name__ == "__main__":
    unittest.main()
