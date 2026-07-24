from __future__ import annotations

import copy
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import shlex
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mednafen_pce_fast, mixed_language
from core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)
from core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_RUNS = (
    "tranche16a-mednafen-pce-fast-control-v2",
    "tranche16a-mednafen-pce-fast-repro-v1",
)
SOURCE_PAIRS = tuple(
    (output, output.removesuffix(".o") + ".c")
    for output in mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECTS
)
EXPECTED_INVOCATION_HASHES = (
    mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_INVOCATION_SHA256
)
EXPECTED_LINK_OBJECT_HASH = (
    mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECT_SHA256
)
EXPECTED_RAW_LINK_OBJECT_HASH = (
    mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_RAW_LINK_OBJECT_SHA256
)
EXPECTED_ORDERED_LINK_HASHES = (
    mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV_SHA256
)


def historical_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID
        / architecture
        / "build.log"
    )


def load_catalog_spec() -> dict:
    catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
    return catalog["cores"][mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID]


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
                raise AssertionError("failed to parse PCE Fast compile fixture")
            invocations.append(invocation)
        elif mednafen_pce_fast.MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME in tokens:
            links.append(tuple(tokens))
    return invocations, links


def build_synthetic_log(
    architecture: str,
) -> tuple[mixed_language.MixedLanguageLogContract, str]:
    c_compiler = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }[architecture]
    compile_lines = tuple(
        f"{c_compiler} -c -o {output} {source} -O2 -fPIC"
        for output, source in SOURCE_PAIRS
    )
    invocations, links = parsed_commands(
        "\n".join(compile_lines), architecture
    )
    if links or len(invocations) != len(SOURCE_PAIRS):
        raise AssertionError("failed to construct PCE Fast compile fixture")
    contract = replace(
        mednafen_pce_fast.MEDNAFEN_PCE_FAST_LOG_CONTRACT,
        expected_compile_invocation_sha256={
            architecture: (
                mixed_language.mixed_language_compile_invocation_sha256(
                    invocations
                )
            )
        },
    )
    link_line = " ".join(
        mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV[
            architecture
        ]
    )
    lines = (
        *mednafen_pce_fast.MEDNAFEN_PCE_FAST_SUCCESS_MARKER,
        mednafen_pce_fast.MEDNAFEN_PCE_FAST_SOURCE_HEAD_MARKER,
        *compile_lines,
        link_line,
        *mednafen_pce_fast.MEDNAFEN_PCE_FAST_SUCCESS_TRAILER,
    )
    return contract, "\n".join(lines) + "\n"


@contextmanager
def synthetic_contract(contract: mixed_language.MixedLanguageLogContract):
    with mock.patch.object(
        mednafen_pce_fast,
        "MEDNAFEN_PCE_FAST_LOG_CONTRACT",
        contract,
    ):
        yield


class MednafenPceFastContractTests(unittest.TestCase):
    def contract_arguments(
        self, build_log_text: str, architecture: str
    ) -> tuple[str, str, str, str, str]:
        identity = mednafen_pce_fast.MEDNAFEN_PCE_FAST_SPEC_IDENTITY
        return (
            build_log_text,
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_exact_catalog_identity_is_core_owned_and_plain(self) -> None:
        spec = load_catalog_spec()
        identity = mednafen_pce_fast.MEDNAFEN_PCE_FAST_SPEC_IDENTITY

        self.assertTrue(
            mednafen_pce_fast.mednafen_pce_fast_spec_is_well_formed(spec)
        )
        self.assertEqual(identity["source_commit"], spec["source"]["commit"])
        self.assertEqual(identity["source_tree"], spec["source"]["tree"])
        for forbidden in (
            "compile_definitions",
            "git_version",
            "make_variables",
            "source_date_epoch",
        ):
            self.assertNotIn(forbidden, spec["build"])

    def test_exact_spec_rejects_every_owned_boundary(self) -> None:
        spec = load_catalog_spec()

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
        for field, value in {
            "compile_definitions": ["SYNTHETIC=1"],
            "git_version": {
                "derivation": "hyphen-short7-v1",
                "value": "-0bc6c86",
            },
            "make_variables": {"SYNTHETIC": 1},
            "source_date_epoch": 1,
        }.items():
            injected = copy.deepcopy(spec)
            injected["build"][field] = value
            mutations[f"injected-{field}"] = injected

        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    mednafen_pce_fast.mednafen_pce_fast_spec_is_well_formed(
                        mutation
                    )
                )
        self.assertFalse(
            mednafen_pce_fast.mednafen_pce_fast_spec_is_well_formed(None)
        )

    def test_frozen_source_pairs_and_ordered_links_are_self_consistent(
        self,
    ) -> None:
        self.assertEqual(92, len(SOURCE_PAIRS))
        self.assertEqual(92, len(set(SOURCE_PAIRS)))
        self.assertTrue(all(source.endswith(".c") for _, source in SOURCE_PAIRS))
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_COMPILE_PAIR_SHA256,
            mixed_language.mixed_language_compile_pair_sha256(SOURCE_PAIRS),
        )
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECT_SHA256,
            mixed_language.mixed_language_link_object_sha256(
                output for output, _source in SOURCE_PAIRS
            ),
        )
        self.assertEqual(
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_RAW_LINK_OBJECT_SHA256,
            mixed_language.mixed_language_raw_link_object_sha256(
                output for output, _source in SOURCE_PAIRS
            ),
        )
        for architecture, link_argv in (
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_ORDERED_LINK_ARGV.items()
        ):
            with self.subTest(architecture=architecture):
                self.assertEqual(
                    EXPECTED_ORDERED_LINK_HASHES[architecture],
                    ordered_command_argv_sha256(link_argv),
                )

    def test_synthetic_logs_prove_both_architectures(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                self.assertTrue(
                    mednafen_pce_fast.mednafen_pce_fast_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_log_rejects_core_architecture_and_source_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        identity = mednafen_pce_fast.MEDNAFEN_PCE_FAST_SPEC_IDENTITY
        with synthetic_contract(contract):
            for arguments in (
                (
                    log,
                    "mednafen_supergrafx",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                ),
                (
                    log,
                    mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID,
                    "unknown",
                    contract.source_commit,
                    contract.source_tree,
                ),
                (
                    log,
                    mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                ),
                (
                    log,
                    mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                ),
                (
                    None,
                    mednafen_pce_fast.MEDNAFEN_PCE_FAST_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                ),
            ):
                with self.subTest(arguments=arguments[1:]):
                    self.assertFalse(
                        mednafen_pce_fast.mednafen_pce_fast_log_proves_contract(
                            *arguments
                        )
                    )

    def test_log_rejects_source_version_and_success_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        arguments = self.contract_arguments(log, "arm64")[1:]
        head = mednafen_pce_fast.MEDNAFEN_PCE_FAST_SOURCE_HEAD_MARKER
        success = (
            "\n".join(
                mednafen_pce_fast.MEDNAFEN_PCE_FAST_SUCCESS_MARKER
            )
            + "\n"
        )
        copy_line = mednafen_pce_fast.MEDNAFEN_PCE_FAST_SUCCESS_TRAILER[0]
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "foreign-head": log + "HEAD is now at 0000000 synthetic\n",
            "missing-fetch-success": log.replace(success, "", 1),
            "duplicate-success": success + log,
            "changed-success-core": log.replace(
                "\tmednafen_pce_fast", "\tother", 1
            ),
            "orphan-success-headline": log.replace(
                head,
                mednafen_pce_fast.MEDNAFEN_PCE_FAST_SUCCESS_MARKER[0]
                + "\n"
                + head,
                1,
            ),
            "changed-copy": log.replace(
                copy_line, copy_line.replace("/dist/unix/", "/dist/other/"), 1
            ),
            "nonterminal-success": log + "post-success noise\n",
            "pipeline-marker": log.replace(
                head + "\n",
                head + "\nCORE_PIPELINE_SYNTHETIC|1\n",
                1,
            ),
            "pipeline-version": log.replace(
                head + "\n",
                head + "\nCORE_PIPELINE_NATIVE_GIT_VERSION|0bc6c86|file\n",
                1,
            ),
            "injected-version": log.replace(
                head + "\n", head + "\nGIT_VERSION=-0bc6c86\n", 1
            ),
        }
        with synthetic_contract(contract):
            for label, mutation in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_pce_fast.mednafen_pce_fast_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_log_rejects_compile_and_link_mutations(self) -> None:
        contract, log = build_synthetic_log("arm64")
        arguments = self.contract_arguments(log, "arm64")[1:]
        compile_line = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-gcc -c ")
        )
        link_line = next(
            line for line in log.splitlines() if " -shared " in line
        )
        first_object, second_object = (
            mednafen_pce_fast.MEDNAFEN_PCE_FAST_EXPECTED_LINK_OBJECTS[:2]
        )
        mutations = {
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "duplicate-compile": log.replace(
                link_line, compile_line + "\n" + link_line, 1
            ),
            "compile-argv": log.replace(
                compile_line, compile_line.replace("-O2", "-O3", 1), 1
            ),
            "cxx-compile": log.replace(
                compile_line,
                compile_line.replace(
                    "aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++", 1
                ),
                1,
            ),
            "wrong-source-language": log.replace(
                compile_line,
                compile_line.replace("cdrom.c", "cdrom.cpp", 1),
                1,
            ),
            "raw-compile-path": log.replace(
                compile_line,
                compile_line.replace(first_object, "./" + first_object, 1),
                1,
            ),
            "compile-version": log.replace(
                compile_line,
                compile_line + " -DGIT_VERSION=-0bc6c86",
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
                    f"{first_object} {second_object}",
                    f"{second_object} {first_object}",
                    1,
                ),
                1,
            ),
            "raw-link-path": log.replace(
                link_line,
                link_line.replace(first_object, "./" + first_object, 1),
                1,
            ),
            "link-compiler": log.replace(
                link_line,
                link_line.replace(
                    "aarch64-linux-gnu-g++", "aarch64-linux-gnu-gcc", 1
                ),
                1,
            ),
            "link-output": log.replace(
                link_line,
                link_line.replace(
                    mednafen_pce_fast.MEDNAFEN_PCE_FAST_BUILD_ARTIFACT_NAME,
                    "other.so",
                    1,
                ),
                1,
            ),
            "duplicate-link": log.replace(
                link_line, link_line + "\n" + link_line, 1
            ),
            "unexpected-compiler-command": log.replace(
                link_line,
                "aarch64-linux-gnu-gcc -E synthetic.c\n" + link_line,
                1,
            ),
        }
        with synthetic_contract(contract):
            for label, mutation in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_pce_fast.mednafen_pce_fast_log_proves_contract(
                            mutation, *arguments
                        )
                    )

    def test_log_rejects_every_diagnostic_and_failure_frame(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, log = build_synthetic_log(architecture)
            arguments = self.contract_arguments(log, architecture)[1:]
            link_line = next(
                line for line in log.splitlines() if " -shared " in line
            )
            frames = {
                "warning": "synthetic.c:1: warning: unexpected",
                "note": "synthetic.c:1: note: unexpected",
                "error": "synthetic.c:1: error: failure",
                "fatal": "fatal: synthetic failure",
                "include-context": "In file included from synthetic.c:1:",
                "function-context": "synthetic.c: In function 'broken':",
                "source-context": "    1 | broken",
                "make-failure": "make: *** [all] Error 2",
                "process-failure": "Killed",
            }
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                for label, frame in frames.items():
                    mutation = log.replace(
                        link_line, frame + "\n" + link_line, 1
                    )
                    with self.subTest(frame=label):
                        self.assertFalse(
                            mednafen_pce_fast.mednafen_pce_fast_log_proves_contract(
                                mutation, *arguments
                            )
                        )

if __name__ == "__main__":
    unittest.main()
