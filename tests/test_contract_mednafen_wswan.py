from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import shlex
import unittest
from unittest import mock

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import mednafen_wswan, mixed_language
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT
    / "tests/fixtures/per-core-oracles/mednafen_wswan.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID
        / architecture
        / "build.log"
    )


def build_mednafen_wswan_log_fixture(
    architecture: str,
) -> tuple[
    mixed_language.MixedLanguageLogContract,
    tuple[str, ...],
    str,
]:
    """Build a small exact log without depending on ignored build evidence."""

    c_compiler, cxx_compiler = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }[architecture]
    token = mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_LOG_TOKEN
    compile_lines = (
        f"{c_compiler} -c -o c/unit.o c/unit.c {token} -O2 -fPIC",
        f"{cxx_compiler} -c -o cxx/unit.o cxx/unit.cpp {token} -O2 -fPIC",
    )
    expected_compilers = {c_compiler, cxx_compiler}
    expected_cxx_compilers = {cxx_compiler}
    parsed_invocations = [
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            expected_compilers,
            expected_cxx_compilers,
        )
        for line in compile_lines
    ]
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct WonderSwan compile fixture")
    invocations = [
        invocation
        for invocation in parsed_invocations
        if invocation is not None
    ]
    pairs = [
        (output, source)
        for output, source, _language, *_raw in invocations
    ]
    objects = tuple(output for output, _source in pairs)
    link_argv = (
        cxx_compiler,
        "-o",
        mednafen_wswan.MEDNAFEN_WSWAN_BUILD_ARTIFACT_NAME,
        *objects,
        *mednafen_wswan.MEDNAFEN_WSWAN_EXPECTED_LINK_OPTIONS,
    )
    contract = replace(
        mednafen_wswan.MEDNAFEN_WSWAN_LOG_CONTRACT,
        expected_compile_count=2,
        expected_language_counts={"c": 1, "cxx": 1},
        expected_compile_pair_sha256=(
            mixed_language.mixed_language_compile_pair_sha256(pairs)
        ),
        expected_compile_invocation_sha256={
            architecture: (
                mixed_language.mixed_language_compile_invocation_sha256(
                    invocations
                )
            )
        },
        expected_link_object_sha256=(
            mixed_language.mixed_language_link_object_sha256(objects)
        ),
        expected_raw_link_object_sha256=(
            mixed_language.mixed_language_raw_link_object_sha256(objects)
        ),
    )
    diagnostic_lines = tuple(
        line
        for block in mednafen_wswan.MEDNAFEN_WSWAN_EXPECTED_DIAGNOSTIC_BLOCKS[
            architecture
        ]
        for line in block.splitlines()
    )
    log = (
        "\n".join(
            (
                mednafen_wswan.MEDNAFEN_WSWAN_SOURCE_HEAD_MARKER,
                mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_VERSION_MARKER,
                *compile_lines,
                *diagnostic_lines,
                " ".join(link_argv),
            )
        )
        + "\n"
    )
    return contract, link_argv, log


@contextmanager
def synthetic_contract(
    architecture: str,
    contract: mixed_language.MixedLanguageLogContract,
    link_argv: tuple[str, ...],
):
    with mock.patch.object(
        mednafen_wswan,
        "MEDNAFEN_WSWAN_EXPECTED_COMPILE_COUNT",
        contract.expected_compile_count,
    ), mock.patch.object(
        mednafen_wswan,
        "MEDNAFEN_WSWAN_EXPECTED_ORDERED_LINK_ARGV",
        {architecture: link_argv},
    ), mock.patch.object(
        mednafen_wswan,
        "MEDNAFEN_WSWAN_LOG_CONTRACT",
        contract,
    ):
        yield


class MednafenWswanModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = (
            mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        return (
            build_log_text,
            mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_exact_catalog_and_promoted_contracts_are_core_owned(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID]
        identity = (
            mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        expected_version = {
            "derivation": (
                mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_DERIVATION
            ),
            "value": mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION,
        }

        self.assertTrue(
            mednafen_wswan.mednafen_wswan_spec_is_well_formed(spec)
        )
        self.assertEqual(expected_version, spec["build"]["git_version"])
        self.assertNotIn("compiler_scope", spec["build"]["git_version"])
        self.assertNotIn("make_variables", spec["build"])
        self.assertEqual("Makefile", identity["native_makefile"])

        source = {
            **spec["source"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": expected_version,
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            mednafen_wswan.mednafen_wswan_golden_source_is_well_formed(
                mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID, source
            )
        )
        self.assertTrue(
            mednafen_wswan.mednafen_wswan_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
                source,
            )
        )

        for label, changed_source in {
            "tree": {**source, "tree": "0" * 40},
            "resolved-commit": {**source, "resolved_commit": "0" * 40},
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/other.git",
            },
            "submodule": {
                **source,
                "submodules": [{"path": "foreign", "commit": "0" * 40}],
            },
            "extra": {**source, "unexpected": True},
        }.items():
            with self.subTest(source=label):
                self.assertFalse(
                    mednafen_wswan.mednafen_wswan_golden_source_is_well_formed(
                        mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
                        changed_source,
                    )
                )
                self.assertFalse(
                    mednafen_wswan.mednafen_wswan_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
                        changed_source,
                    )
                )

        for label, changed_build in {
            "version": {
                **build,
                "git_version": {**expected_version, "value": " 0000000"},
            },
            "scope": {
                **build,
                "git_version": {**expected_version, "compiler_scope": "cxx"},
            },
            "make": {**build, "make_variables": {"IS_X86": 0}},
            "epoch": {**build, "source_date_epoch": 1},
            "log": {**build, "log": "other.log"},
            "digest": {**build, "log_sha256": "invalid"},
            "extra": {**build, "unexpected": True},
        }.items():
            with self.subTest(build=label):
                self.assertFalse(
                    mednafen_wswan.mednafen_wswan_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
                        source,
                    )
                )

    def test_exact_catalog_predicate_rejects_every_owned_boundary(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        core_id = mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(catalog["cores"][core_id])
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "workflow",
                lambda changed: changed.update({"workflow": "build.yml"}),
            ),
            mutation(
                "source-url",
                lambda changed: changed["source"].update(
                    {"url": "https://example.com/other.git"}
                ),
            ),
            mutation(
                "source-ref",
                lambda changed: changed["source"].update(
                    {"requested_ref": "refs/heads/main"}
                ),
            ),
            mutation(
                "source-commit",
                lambda changed: changed["source"].update(
                    {"commit": "0" * 40}
                ),
            ),
            mutation(
                "source-tree",
                lambda changed: changed["source"].update({"tree": "0" * 40}),
            ),
            mutation(
                "version-derivation",
                lambda changed: changed["build"]["git_version"].update(
                    {"derivation": "hyphen-short7-v1"}
                ),
            ),
            mutation(
                "version-value",
                lambda changed: changed["build"]["git_version"].update(
                    {"value": " 0000000"}
                ),
            ),
            mutation(
                "compiler-scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "cxx"}
                ),
            ),
            mutation(
                "pcfx-variable",
                lambda changed: changed["build"].update(
                    {"make_variables": {"IS_X86": 0}}
                ),
            ),
            mutation(
                "output",
                lambda changed: changed["build"].update(
                    {"output_path": "dist/unix/other.so"}
                ),
            ),
            mutation(
                "metadata",
                lambda changed: changed["metadata"].update(
                    {"artifact_name": "other.info"}
                ),
            ),
            mutation(
                "targets",
                lambda changed: changed.update({"targets": ["arm64"]}),
            ),
            mutation(
                "extra",
                lambda changed: changed.update({"unexpected": True}),
            ),
        )
        for label, changed in mutations:
            with self.subTest(mutation=label):
                self.assertFalse(
                    mednafen_wswan.mednafen_wswan_spec_is_well_formed(changed)
                )

    def test_schema_boundaries_are_individual_and_exact(self) -> None:
        catalog_schema = json.loads(
            (ROOT / "manifests/core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )
        golden_schema = json.loads(
            (ROOT / "manifests/golden-start.schema.json").read_text(
                encoding="utf-8"
            )
        )
        core_id = mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID
        self.assertNotIn(
            "mednafen_wswan",
            catalog_schema["properties"]["cores"].get(
                "properties", {}
            ),
        )

    def test_synthetic_logs_prove_both_architecture_contracts(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, link_argv, log = build_mednafen_wswan_log_fixture(
                architecture
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    mednafen_wswan.mednafen_wswan_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )
                spec = pipeline.load_json(ROOT / "manifests/core-builds.json")[
                    "cores"
                ][mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID]
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log,
                        spec["build"]["git_version"],
                        spec["source"]["commit"],
                        architecture,
                    )
                )

    def test_synthetic_log_rejects_marker_and_identity_mutations(self) -> None:
        contract, link_argv, log = build_mednafen_wswan_log_fixture("arm64")
        arguments = self.contract_arguments(log)[1:]
        marker = mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_VERSION_MARKER
        head = mednafen_wswan.MEDNAFEN_WSWAN_SOURCE_HEAD_MARKER
        token = mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_LOG_TOKEN
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "foreign-head": log + "HEAD is now at 0000000 synthetic\n",
            "missing-marker": log.replace(marker + "\n", "", 1),
            "wrong-origin": log.replace("|file", "|command line", 1),
            "late-marker": log.replace(marker + "\n", "", 1) + marker + "\n",
            "foreign-native-marker": (
                log + 'CORE_PIPELINE_NATIVE_GIT_VERSION|" 0000000"|file\n'
            ),
            "wrong-version": log.replace(token, r'-DGIT_VERSION=\"" 0000000"\"', 1),
            "injected-marker": (
                log + "CORE_PIPELINE_GIT_VERSION|-da6d0d9|command line\n"
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_wswan.mednafen_wswan_log_proves_contract(
                            changed, *arguments
                        )
                    )
            self.assertFalse(
                mednafen_wswan.mednafen_wswan_log_proves_contract(
                    log,
                    "mednafen_pcfx",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                mednafen_wswan.mednafen_wswan_log_proves_contract(
                    log,
                    mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                mednafen_wswan.mednafen_wswan_log_proves_contract(
                    log,
                    mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                )
            )

    def test_synthetic_log_rejects_compile_and_ordered_link_mutations(
        self,
    ) -> None:
        contract, link_argv, log = build_mednafen_wswan_log_fixture("arm64")
        arguments = self.contract_arguments(log)[1:]
        compile_line = next(line for line in log.splitlines() if " -c " in line)
        cxx_line = next(
            line
            for line in log.splitlines()
            if "aarch64-linux-gnu-g++ -c" in line
        )
        link_line = " ".join(link_argv)
        mutations = {
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "duplicate-compile": log + compile_line + "\n",
            "compile-option": log.replace(
                compile_line, compile_line.replace("-O2", "-O3", 1), 1
            ),
            "response-file": log.replace(
                compile_line, compile_line.replace(" -O2", " @args.rsp -O2", 1), 1
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
                    "c/unit.o cxx/unit.o", "cxx/unit.o c/unit.o", 1
                ),
                1,
            ),
            "link-raw-path": log.replace(
                link_line,
                link_line.replace("cxx/unit.o", "./cxx/unit.o", 1),
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
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        mednafen_wswan.mednafen_wswan_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_synthetic_log_rejects_diagnostic_mutations(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, link_argv, log = build_mednafen_wswan_log_fixture(
                architecture
            )
            arguments = self.contract_arguments(log, architecture)[1:]
            expected_blocks = (
                mednafen_wswan.MEDNAFEN_WSWAN_EXPECTED_DIAGNOSTIC_BLOCKS[
                    architecture
                ]
            )
            final_context_line = expected_blocks[-1].splitlines()[-1] + "\n"
            before_context, matched_context, after_context = log.rpartition(
                final_context_line
            )
            self.assertEqual(final_context_line, matched_context)
            late_context_suffix = (
                before_context + after_context + matched_context
            )
            final_context_block = expected_blocks[-1] + "\n"
            self.assertIn(final_context_block, log)
            late_context_block = (
                log.replace(final_context_block, "", 1)
                + final_context_block
            )
            mutations = {
                "missing-warning": log.replace(
                    mednafen_wswan.MEDNAFEN_WSWAN_EXPECTED_WARNING_LINES[0]
                    + "\n",
                    "",
                    1,
                ),
                "changed-warning": log.replace(
                    "warning: variable 'mult' set but not used",
                    "warning: value 'mult' set but not used",
                    1,
                ),
                "extra-warning": log + "warning: synthetic warning\n",
                "missing-context": log.replace(
                    "mednafen/wswan/v30mz.c: In function 'DoOP':\n", "", 1
                ),
                "extra-note": log + "note: synthetic note\n",
                "error": log + "error: synthetic error\n",
                "make": log + "make: *** [all] Error 2\n",
                "linker": log + "undefined reference to synthetic_symbol\n",
                "crash": log + "Segmentation fault\n",
                "late-context-suffix": late_context_suffix,
                "late-context-block": late_context_block,
            }
            if architecture == "armhf":
                mutations["missing-note"] = log.replace(
                    mednafen_wswan.MEDNAFEN_WSWAN_ARMHF_EXPECTED_NOTE_LINES[0]
                    + "\n",
                    "",
                    1,
                )
                mutations["changed-note"] = log.replace(
                    "changed in GCC 7.1", "changed in GCC 8.1", 1
                )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                for label, changed in mutations.items():
                    with self.subTest(mutation=label):
                        self.assertFalse(
                            mednafen_wswan.mednafen_wswan_log_proves_contract(
                                changed, *arguments
                            )
                        )

    def test_synthetic_log_accepts_parallel_diagnostic_interleaving(
        self,
    ) -> None:
        architecture = "armhf"
        contract, link_argv, log = build_mednafen_wswan_log_fixture(
            architecture
        )
        streams = tuple(
            tuple(block.splitlines())
            for block in (
                mednafen_wswan.MEDNAFEN_WSWAN_EXPECTED_DIAGNOSTIC_BLOCKS[
                    architecture
                ]
            )
        )
        sequential = "\n".join(
            line for stream in streams for line in stream
        )
        interleaved_lines = []
        for position in range(max(len(stream) for stream in streams)):
            interleaved_lines.extend(
                stream[position]
                for stream in streams
                if position < len(stream)
            )
        interleaved = "\n".join(interleaved_lines)
        self.assertNotEqual(sequential, interleaved)
        changed = log.replace(sequential, interleaved, 1)
        with synthetic_contract(architecture, contract, link_argv):
            self.assertTrue(
                mednafen_wswan.mednafen_wswan_log_proves_contract(
                    *self.contract_arguments(changed, architecture)
                )
            )

class MednafenWswanCompositionIntegrationTests(unittest.TestCase):
    def test_shared_generation_surfaces_preserve_native_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID
        spec = catalog["cores"][core_id]
        expected_version = {
            "derivation": (
                mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_DERIVATION
            ),
            "value": mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION,
        }
        expected_markers = [
            mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_VERSION_MARKER
        ]
        expected_normalized = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": expected_version,
        }
        generated_marker = (
            "CORE_PIPELINE_NATIVE_GIT_VERSION|$(GIT_VERSION)|"
            "$(origin GIT_VERSION)"
        )
        version_probe_command = (
            "make --no-print-directory -s "
            "-C /libretro-super/libretro-mednafen_wswan "
            "-f Makefile -f "
            "/tmp/core-pipeline-native-git-version-origin.mk "
            "core_pipeline_native_git_version_origin"
        )

        self.assertEqual(
            expected_markers, pipeline.git_version_log_markers(spec)
        )
        version_shell = pipeline.git_version_shell(spec)
        self.assertIn(
            "-f Makefile -f "
            "/tmp/core-pipeline-native-git-version-origin.mk",
            version_shell,
        )
        self.assertNotIn("Makefile.libretro", version_shell)
        self.assertEqual("", pipeline.make_variable_shell(spec))
        self.assertEqual([], pipeline.make_variable_log_markers(spec))

        build_shell = pipeline.libretro_build_shell(spec, core_id)
        self.assertEqual("./libretro-build.sh mednafen_wswan", build_shell)
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                self.assertEqual(
                    expected_normalized,
                    pipeline.normalized_build_contract(spec, architecture),
                )
                container_shell = pipeline.container_build_script(
                    core_id,
                    architecture,
                    spec,
                    catalog["resolver"],
                )
                self.assertIn(version_shell, container_shell)
                self.assertEqual(1, container_shell.count(generated_marker))
                self.assertLess(
                    container_shell.index(generated_marker),
                    container_shell.index(build_shell),
                )
                self.assertLess(
                    container_shell.index(version_probe_command),
                    container_shell.index(build_shell),
                )

    def test_composition_root_and_registry_bind_the_individual_contract(
        self,
    ) -> None:
        identity = (
            mednafen_wswan.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertIs(
            identity, pipeline.MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        contract = core_log_contract_for(
            mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID
        )
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "mednafen-wswan-mixed-language-v1", contract.contract_id
        )
        self.assertEqual(
            "mednafen_wswan_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID}),
            contract.core_ids,
        )

    def test_catalog_guard_and_registered_dispatch_use_individual_proof(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        changed = copy.deepcopy(catalog)
        changed["cores"][mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID]["build"][
            "git_version"
        ]["compiler_scope"] = "cxx"
        self.assertFalse(
            mednafen_wswan.mednafen_wswan_spec_is_well_formed(
                changed["cores"][mednafen_wswan.MEDNAFEN_WSWAN_CORE_ID]
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)

        contract, link_argv, log = build_mednafen_wswan_log_fixture("arm64")
        with synthetic_contract("arm64", contract, link_argv):
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    *MednafenWswanModuleTests().contract_arguments(log)
                )
            )


if __name__ == "__main__":
    unittest.main()
