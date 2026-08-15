from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import shlex
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import mednafen_ngp, mixed_language
from core_pipeline_lib.contracts.command_line import ordered_command_argv_sha256
from core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_RUNS = (
    "tranche10b-mednafen-ngp-golden-v1",
    "tranche10b-mednafen-ngp-repro-v1",
)
CXX_OBJECTS = {
    "mednafen/ngp/sound.o",
    "mednafen/ngp/T6W28_Apu.o",
    "mednafen/sound/Blip_Buffer.o",
    "mednafen/mempatcher.o",
    "mednafen/sound/Stereo_Buffer.o",
}
SOURCE_PAIRS = tuple(
    (
        output,
        output.removesuffix(".o")
        + (".cpp" if output in CXX_OBJECTS else ".c"),
    )
    for output in mednafen_ngp.MEDNAFEN_NGP_EXPECTED_LINK_OBJECTS
)


def historical_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / mednafen_ngp.MEDNAFEN_NGP_CORE_ID
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
                raise AssertionError("failed to parse NGP compile fixture")
            invocations.append(invocation)
        elif mednafen_ngp.MEDNAFEN_NGP_BUILD_ARTIFACT_NAME in tokens:
            links.append(tuple(tokens))
    return invocations, links


def build_synthetic_log(
    architecture: str,
    *,
    warning_after: int = 12,
) -> tuple[mixed_language.MixedLanguageLogContract, str]:
    c_compiler, cxx_compiler = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }[architecture]
    token = mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_LOG_TOKEN
    compile_lines = tuple(
        " ".join(
            (
                cxx_compiler if source.endswith(".cpp") else c_compiler,
                "-c",
                "-o",
                output,
                source,
                token,
                *(() if source.endswith(".cpp") else (token,)),
                "-O2",
                "-fPIC",
            )
        )
        for output, source in SOURCE_PAIRS
    )
    unpatched_contract = mednafen_ngp.MEDNAFEN_NGP_LOG_CONTRACT
    invocations, _links = parsed_commands(
        "\n".join(compile_lines), architecture
    )
    contract = replace(
        unpatched_contract,
        expected_compile_invocation_sha256={
            architecture: (
                mixed_language.mixed_language_compile_invocation_sha256(
                    invocations
                )
            )
        },
    )
    link_line = " ".join(
        mednafen_ngp.MEDNAFEN_NGP_EXPECTED_ORDERED_LINK_ARGV[architecture]
    )
    lines = (
        *mednafen_ngp.MEDNAFEN_NGP_SUCCESS_MARKER,
        mednafen_ngp.MEDNAFEN_NGP_SOURCE_HEAD_MARKER,
        *compile_lines[:warning_after],
        *mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT,
        *compile_lines[warning_after:],
        *(
            mednafen_ngp.MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT
            if architecture == "armhf"
            else ()
        ),
        link_line,
        *mednafen_ngp.MEDNAFEN_NGP_SUCCESS_TRAILER,
    )
    return contract, "\n".join(lines) + "\n"


@contextmanager
def synthetic_contract(contract: mixed_language.MixedLanguageLogContract):
    with mock.patch.object(
        mednafen_ngp, "MEDNAFEN_NGP_LOG_CONTRACT", contract
    ):
        yield


class MednafenNgpContractTests(unittest.TestCase):
    def contract_arguments(
        self, build_log_text: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            build_log_text,
            mednafen_ngp.MEDNAFEN_NGP_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_registry_identity_is_owned_by_mednafen_ngp(self) -> None:
        contract = core_log_contract_for(mednafen_ngp.MEDNAFEN_NGP_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("mednafen-ngp-mixed-language-v1", contract.contract_id)
        self.assertEqual(
            "mednafen_ngp_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({mednafen_ngp.MEDNAFEN_NGP_CORE_ID}), contract.core_ids
        )

    def test_exact_catalog_identity_and_native_version_are_core_owned(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][mednafen_ngp.MEDNAFEN_NGP_CORE_ID]
        identity = mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY

        self.assertIs(
            identity, pipeline.MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertTrue(mednafen_ngp.mednafen_ngp_spec_is_well_formed(spec))
        self.assertEqual(
            " a50d5ac", mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION
        )
        self.assertEqual(
            frozenset({"c", "cxx"}),
            mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_COMPILER_SCOPE,
        )
        self.assertEqual(
            {"c": 2, "cxx": 1},
            mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_OCCURRENCES_BY_LANGUAGE,
        )
        self.assertNotIn("git_version", spec["build"])
        self.assertEqual([], pipeline.git_version_log_markers(spec))
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        self.assertEqual("Makefile", identity["native_makefile"])

        changed_catalog = copy.deepcopy(catalog)
        changed_catalog["cores"][mednafen_ngp.MEDNAFEN_NGP_CORE_ID]["build"][
            "output_path"
        ] = "dist/unix/other.so"
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "mednafen_ngp core must preserve its exact native version",
        ):
            pipeline.validate_catalog(changed_catalog)

    def test_exact_spec_rejects_every_owned_boundary(self) -> None:
        spec = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")[
            "cores"
        ][mednafen_ngp.MEDNAFEN_NGP_CORE_ID]

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
            "value": " a50d5ac",
        }
        mutations["injected-version"] = injected

        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    mednafen_ngp.mednafen_ngp_spec_is_well_formed(mutation)
                )

    def test_synthetic_logs_accept_parallel_warning_interleavings(self) -> None:
        for architecture in ("arm64", "armhf"):
            for warning_after in (26, 30, len(SOURCE_PAIRS)):
                contract, log = build_synthetic_log(
                    architecture, warning_after=warning_after
                )
                arguments = self.contract_arguments(log, architecture)
                with self.subTest(
                    architecture=architecture,
                    warning_after=warning_after,
                ), synthetic_contract(contract):
                    self.assertTrue(
                        mednafen_ngp.mednafen_ngp_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )

    def test_armhf_note_context_accepts_prelink_compile_interleaving(self) -> None:
        contract, log = build_synthetic_log("armhf", warning_after=26)
        note_block = (
            "\n".join(mednafen_ngp.MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT) + "\n"
        )
        final_compile = next(
            line
            for line in log.splitlines()
            if " -c -o mednafen/settings.o " in line
        )
        interleaved = log.replace(note_block, "", 1).replace(
            final_compile,
            note_block + final_compile,
            1,
        )
        with synthetic_contract(contract):
            self.assertTrue(
                mednafen_ngp.mednafen_ngp_log_proves_contract(
                    *self.contract_arguments(interleaved, "armhf")
                )
            )

    def test_armhf_diagnostic_blocks_accept_either_completion_order(self) -> None:
        contract, log = build_synthetic_log("armhf", warning_after=26)
        warning_block = (
            "\n".join(mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT) + "\n"
        )
        note_block = (
            "\n".join(mednafen_ngp.MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT) + "\n"
        )
        notes_first = log.replace(note_block, "", 1).replace(
            warning_block,
            note_block + warning_block,
            1,
        )
        with synthetic_contract(contract):
            self.assertTrue(
                mednafen_ngp.mednafen_ngp_log_proves_contract(
                    *self.contract_arguments(notes_first, "armhf")
                )
            )

    def test_log_rejects_core_architecture_and_source_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        identity = mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY
        with synthetic_contract(contract):
            for arguments in (
                (
                    log,
                    "mednafen_vb",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                ),
                (
                    log,
                    mednafen_ngp.MEDNAFEN_NGP_CORE_ID,
                    "unknown",
                    contract.source_commit,
                    contract.source_tree,
                ),
                (
                    log,
                    mednafen_ngp.MEDNAFEN_NGP_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                ),
                (
                    log,
                    mednafen_ngp.MEDNAFEN_NGP_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                ),
                (
                    None,
                    mednafen_ngp.MEDNAFEN_NGP_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ):
                with self.subTest(arguments=arguments[1:]):
                    self.assertFalse(
                        mednafen_ngp.mednafen_ngp_log_proves_contract(*arguments)
                    )

    def test_log_rejects_source_version_and_success_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        arguments = self.contract_arguments(log, "arm64")[1:]
        head = mednafen_ngp.MEDNAFEN_NGP_SOURCE_HEAD_MARKER
        success = "\n".join(mednafen_ngp.MEDNAFEN_NGP_SUCCESS_MARKER) + "\n"
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "foreign-head": log + "HEAD is now at 0000000 synthetic\n",
            "missing-fetch-success": log.replace(success, "", 1),
            "duplicate-success": success + log,
            "orphan-success-headline": log.replace(
                head,
                mednafen_ngp.MEDNAFEN_NGP_SUCCESS_MARKER[0] + "\n" + head,
                1,
            ),
            "changed-success-core": log.replace("\tmednafen_ngp", "\tother", 1),
            "nonterminal-success": log + "post-success noise\n",
            "pipeline-version": log.replace(
                head + "\n",
                head
                + '\nCORE_PIPELINE_NATIVE_GIT_VERSION|" a50d5ac"|file\n',
                1,
            ),
            "injected-version": log.replace(
                head + "\n",
                head + "\nCORE_PIPELINE_GIT_VERSION|-a50d5ac|command line\n",
                1,
            ),
        }
        with synthetic_contract(contract):
            for label, mutation in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_ngp.mednafen_ngp_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_log_rejects_compile_and_link_mutations(self) -> None:
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
        token = mednafen_ngp.MEDNAFEN_NGP_NATIVE_GIT_VERSION_LOG_TOKEN
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
            "missing-c-version-copy": log.replace(
                c_line, c_line.replace(token + " ", "", 1), 1
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
                    "mednafen/ngp/sound.o mednafen/ngp/T6W28_Apu.o",
                    "mednafen/ngp/T6W28_Apu.o mednafen/ngp/sound.o",
                    1,
                ),
                1,
            ),
            "raw-link-path": log.replace(
                link_line,
                link_line.replace(
                    "mednafen/ngp/sound.o", "./mednafen/ngp/sound.o", 1
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
                        mednafen_ngp.mednafen_ngp_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_log_rejects_diagnostic_mutations_and_invalid_interleaving(
        self,
    ) -> None:
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            arguments = self.contract_arguments(log, architecture)[1:]
            warning = "\n".join(mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT) + "\n"
            link_line = next(
                line for line in log.splitlines() if " -shared " in line
            )
            first_compile = next(
                line for line in log.splitlines() if " -c " in line
            )
            mutations = {
                "missing-warning-context": log.replace(
                    mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT[0] + "\n", "", 1
                ),
                "changed-warning": log.replace(
                    "missing braces around initializer",
                    "synthetic warning",
                    1,
                ),
                "unexpected-warning": log.replace(
                    link_line, "synthetic.c:1: warning: unexpected\n" + link_line, 1
                ),
                "unexpected-note": log.replace(
                    link_line, "synthetic.c:1: note: unexpected\n" + link_line, 1
                ),
                "error": log.replace(
                    link_line, "synthetic.c:1: error: failure\n" + link_line, 1
                ),
                "fatal": log.replace(
                    link_line, "fatal: synthetic failure\n" + link_line, 1
                ),
                "make-failure": log.replace(
                    link_line, "make: *** [all] Error 2\n" + link_line, 1
                ),
                "warning-before-compiles": log.replace(warning, "", 1).replace(
                    first_compile, warning + first_compile, 1
                ),
                "warning-after-link": log.replace(warning, "", 1).replace(
                    link_line + "\n", link_line + "\n" + warning, 1
                ),
            }
            warning_lines = mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT
            mutations["split-warning-context"] = log.replace(
                warning_lines[2] + "\n",
                warning_lines[2] + "\nnoise between warning lines\n",
                1,
            )
            if architecture == "armhf":
                note_context = mednafen_ngp.MEDNAFEN_NGP_ARMHF_NOTE_CONTEXT
                note_block = "\n".join(note_context) + "\n"
                mutations["missing-note-context"] = log.replace(
                    note_context[0] + "\n", "", 1
                )
                mutations["changed-note"] = log.replace(
                    "changed in GCC 7.1", "changed in GCC 8.1", 1
                )
                mutations["early-note-context"] = log.replace(
                    note_block, "", 1
                ).replace(first_compile, note_block + first_compile, 1)
                mutations["post-link-note-context"] = log.replace(
                    note_block, "", 1
                ).replace(link_line + "\n", link_line + "\n" + note_block, 1)
                mutations["split-note-context"] = log.replace(
                    note_context[3] + "\n",
                    note_context[3] + "\nnoise between note lines\n",
                    1,
                )
                mutations["interleaved-diagnostic-blocks"] = log.replace(
                    note_block, "", 1
                ).replace(
                    mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT[2] + "\n",
                    mednafen_ngp.MEDNAFEN_NGP_WARNING_CONTEXT[2]
                    + "\n"
                    + note_block,
                    1,
                )
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                for label, mutation in mutations.items():
                    with self.subTest(mutation=label):
                        self.assertFalse(
                            mednafen_ngp.mednafen_ngp_log_proves_contract(
                                mutation, *arguments
                            )
                        )

if __name__ == "__main__":
    unittest.main()
