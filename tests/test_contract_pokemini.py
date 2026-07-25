from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
import shlex
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mixed_language, pokemini
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT / "tests/fixtures/per-core-oracles/pokemini.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / pokemini.POKEMINI_CORE_ID
        / architecture
        / "build.log"
    )


def build_pokemini_log_fixture(
    architecture: str,
) -> tuple[
    mixed_language.MixedLanguageLogContract,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
]:
    """Build the complete proof shape without ignored build evidence."""

    compiler = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }[architecture]
    compile_lines = tuple(
        f"{compiler} -c -osynthetic/unit_{index:03d}.o "
        f"synthetic/unit_{index:03d}.c "
        f"{pokemini.POKEMINI_NATIVE_GIT_VERSION_LOG_TOKEN} "
        "-O2 -DNDEBUG -D__LIBRETRO__ -fPIC"
        for index in range(pokemini.POKEMINI_EXPECTED_COMPILE_COUNT)
    )
    parsed_invocations = tuple(
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            {compiler},
            set(),
        )
        for line in compile_lines
    )
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct PokéMini compile fixture")
    invocations = tuple(
        invocation
        for invocation in parsed_invocations
        if invocation is not None
    )
    pairs = tuple(
        (output, source)
        for output, source, _language, *_raw in invocations
    )
    objects = tuple(output for output, _source in pairs)
    link_argv = (
        compiler,
        "-fPIC",
        "-shared",
        "-Wl,--version-script=libretro/link.T",
        "-o",
        pokemini.POKEMINI_BUILD_ARTIFACT_NAME,
        *(f"./{path}" for path in objects),
        "-lm",
    )
    contract = replace(
        pokemini.POKEMINI_LOG_CONTRACT,
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
            mixed_language.mixed_language_raw_link_object_sha256(
                f"./{path}" for path in objects
            )
        ),
    )
    diagnostic_blocks = pokemini.POKEMINI_EXPECTED_DIAGNOSTIC_BLOCKS[
        architecture
    ]
    log = (
        "\n".join(
            (
                pokemini.POKEMINI_SOURCE_HEAD_MARKER,
                pokemini.POKEMINI_NATIVE_VERSION_MARKER,
                *compile_lines,
                *diagnostic_blocks,
                " ".join(link_argv),
            )
        )
        + "\n"
    )
    return contract, compile_lines, link_argv, diagnostic_blocks, log


@contextmanager
def synthetic_contract(
    architecture: str,
    contract: mixed_language.MixedLanguageLogContract,
    link_argv: tuple[str, ...],
):
    ordered_digest = pokemini.pokemini_ordered_link_argv_sha256(
        list(link_argv)
    )
    with mock.patch.object(
        pokemini,
        "POKEMINI_EXPECTED_ORDERED_LINK_ARGV_SHA256",
        {architecture: ordered_digest},
    ), mock.patch.object(
        pokemini,
        "POKEMINI_LOG_CONTRACT",
        contract,
    ):
        yield


class PokeminiModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = pokemini.POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            build_log_text,
            pokemini.POKEMINI_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_exact_catalog_and_promoted_contracts_are_core_owned(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][pokemini.POKEMINI_CORE_ID]
        identity = pokemini.POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
        expected_version = {
            "derivation": pokemini.POKEMINI_NATIVE_GIT_VERSION_DERIVATION,
            "value": pokemini.POKEMINI_NATIVE_GIT_VERSION,
        }

        self.assertTrue(pokemini.pokemini_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(
                spec, pokemini.POKEMINI_CORE_ID
            )
        )
        self.assertEqual(expected_version, spec["build"]["git_version"])
        self.assertEqual(expected_version, pipeline.validated_git_version(spec))
        self.assertEqual({}, pipeline.validated_make_variables(spec))
        self.assertNotIn("compiler_scope", spec["build"]["git_version"])
        self.assertNotIn("make_variables", spec["build"])
        self.assertEqual("Makefile.libretro", identity["native_makefile"])

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
            pokemini.pokemini_golden_source_is_well_formed(
                pokemini.POKEMINI_CORE_ID, source
            )
        )
        self.assertTrue(
            pipeline.native_git_version_golden_source_is_well_formed(
                pokemini.POKEMINI_CORE_ID, source
            )
        )
        self.assertTrue(
            pokemini.pokemini_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                pokemini.POKEMINI_CORE_ID,
                source,
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                pokemini.POKEMINI_CORE_ID,
                source,
            )
        )

        for label, changed_source in {
            "tree": {**source, "tree": "0" * 40},
            "resolved-commit": {**source, "resolved_commit": "0" * 40},
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/PokeMini.git",
            },
            "submodule": {
                **source,
                "submodules": [{"path": "foreign", "commit": "0" * 40}],
            },
            "extra": {**source, "unexpected": True},
        }.items():
            with self.subTest(source=label):
                self.assertFalse(
                    pokemini.pokemini_golden_source_is_well_formed(
                        pokemini.POKEMINI_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    pipeline.native_git_version_golden_source_is_well_formed(
                        pokemini.POKEMINI_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    pokemini.pokemini_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        pokemini.POKEMINI_CORE_ID,
                        changed_source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        pokemini.POKEMINI_CORE_ID,
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
                "git_version": {
                    **expected_version,
                    "compiler_scope": "cxx",
                },
            },
            "make": {**build, "make_variables": {"IS_X86": 0}},
            "epoch": {**build, "source_date_epoch": 1},
            "log": {**build, "log": "other.log"},
            "digest": {**build, "log_sha256": "invalid"},
            "extra": {**build, "unexpected": True},
        }.items():
            with self.subTest(build=label):
                self.assertFalse(
                    pokemini.pokemini_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        pokemini.POKEMINI_CORE_ID,
                        source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        pokemini.POKEMINI_CORE_ID,
                        source,
                    )
                )

    def test_catalog_predicate_rejects_every_owned_boundary(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][pokemini.POKEMINI_CORE_ID]

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(spec)
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "workflow",
                lambda changed: changed.update({"workflow": "build.yml"}),
            ),
            mutation(
                "source-url-case",
                lambda changed: changed["source"].update(
                    {"url": "https://github.com/libretro/pokemini.git"}
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
                lambda changed: changed["source"].update({"commit": "0" * 40}),
            ),
            mutation(
                "source-tree",
                lambda changed: changed["source"].update({"tree": "0" * 40}),
            ),
            mutation(
                "version",
                lambda changed: changed["build"]["git_version"].update(
                    {"value": " 0000000"}
                ),
            ),
            mutation(
                "scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "cxx"}
                ),
            ),
            mutation(
                "make",
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
                self.assertFalse(pokemini.pokemini_spec_is_well_formed(changed))

    def test_schema_boundaries_are_individual_and_exact(self) -> None:
        schema = json.loads(
            (ROOT / "manifests/core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_reviewed_build_fingerprints_are_individual_and_exact(self) -> None:
        self.assertEqual(43, pokemini.POKEMINI_EXPECTED_COMPILE_COUNT)
        self.assertEqual(
            {"c": 43}, pokemini.POKEMINI_EXPECTED_LANGUAGE_COUNTS
        )
        self.assertEqual(
            "17f65c12b7ef794447812008357fb682cb19db4a6a3e82486670da39d0145750",
            pokemini.POKEMINI_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "533510854d6e233ce8042544af7dbbd43eb387404ef1e011c534af9a4575b8d8"
                ),
                "armhf": (
                    "214985b96125d51986696ccca44d08d63e43ce6579e37cc13a4f15c33c141826"
                ),
            },
            pokemini.POKEMINI_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            "3527e8711e8a30937f33c5be35b0e5d6c98721f4b141bcf6ed6acfb1fc1765c4",
            pokemini.POKEMINI_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            "c", pokemini.POKEMINI_LOG_CONTRACT.expected_link_language
        )
        self.assertEqual(
            {"arm64": 5, "armhf": 5},
            {
                arch: len(lines)
                for arch, lines in pokemini.POKEMINI_EXPECTED_WARNING_LINES.items()
            },
        )
        self.assertEqual(
            {"arm64": 3, "armhf": 3},
            {
                arch: len(blocks)
                for arch, blocks in pokemini.POKEMINI_EXPECTED_DIAGNOSTIC_BLOCKS.items()
            },
        )

    def test_synthetic_logs_prove_both_architecture_contracts(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compiles, link_argv, _diagnostics, log = (
                build_pokemini_log_fixture(architecture)
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    pokemini.pokemini_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_diagnostic_streams_allow_parallel_interleaving(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compiles, link_argv, blocks, log = (
                build_pokemini_log_fixture(architecture)
            )
            sequential = "\n".join(blocks)
            streams = [block.splitlines() for block in blocks]
            interleaved = "\n".join(
                line
                for index in range(max(map(len, streams)))
                for stream in streams
                if index < len(stream)
                for line in (stream[index],)
            )
            self.assertNotEqual(sequential, interleaved)
            changed = log.replace(sequential, interleaved, 1)
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    pokemini.pokemini_log_proves_contract(
                        *self.contract_arguments(changed, architecture)
                    )
                )

    def test_synthetic_log_rejects_marker_and_identity_mutations(self) -> None:
        contract, _compiles, link_argv, _diagnostics, log = (
            build_pokemini_log_fixture("arm64")
        )
        arguments = self.contract_arguments(log)[1:]
        head = pokemini.POKEMINI_SOURCE_HEAD_MARKER
        marker = pokemini.POKEMINI_NATIVE_VERSION_MARKER
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "missing-marker": log.replace(marker + "\n", "", 1),
            "late-marker": log.replace(marker + "\n", "", 1) + marker + "\n",
            "wrong-origin": log.replace("|file", "|command line", 1),
            "wrong-value": log.replace(" bb009b1", " 0000000", 1),
            "injected-version": (
                log + "CORE_PIPELINE_GIT_VERSION|-bb009b1|command line\n"
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        pokemini.pokemini_log_proves_contract(
                            changed, *arguments
                        )
                    )
            for label, changed_arguments in {
                "core": (
                    "potator",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                ),
                "commit": (
                    pokemini.POKEMINI_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                ),
                "tree": (
                    pokemini.POKEMINI_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                ),
                "architecture": (
                    pokemini.POKEMINI_CORE_ID,
                    "unknown",
                    contract.source_commit,
                    contract.source_tree,
                ),
            }.items():
                with self.subTest(identity=label):
                    self.assertFalse(
                        pokemini.pokemini_log_proves_contract(
                            log, *changed_arguments
                        )
                    )

    def test_synthetic_log_rejects_compile_and_link_mutations(self) -> None:
        contract, compile_lines, link_argv, _diagnostics, log = (
            build_pokemini_log_fixture("arm64")
        )
        arguments = self.contract_arguments(log)[1:]
        compile_line = compile_lines[0]
        link_line = " ".join(link_argv)
        first_objects = (
            "./synthetic/unit_000.o ./synthetic/unit_001.o"
        )
        mutations = {
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "duplicate-compile": log.replace(
                compile_line, compile_line + "\n" + compile_line, 1
            ),
            "compile-option": log.replace(
                compile_line, compile_line.replace("-O2", "-O3", 1), 1
            ),
            "missing-version": log.replace(
                compile_line,
                compile_line.replace(
                    f" {pokemini.POKEMINI_NATIVE_GIT_VERSION_LOG_TOKEN}",
                    "",
                    1,
                ),
                1,
            ),
            "cxx-compiler": log.replace(
                compile_line,
                compile_line.replace(
                    "aarch64-linux-gnu-gcc",
                    "aarch64-linux-gnu-g++",
                    1,
                ),
                1,
            ),
            "response-file": log.replace(
                compile_line,
                compile_line.replace(" -O2", " @args.rsp -O2", 1),
                1,
            ),
            "missing-link-object": log.replace(
                link_line,
                link_line.replace(" ./synthetic/unit_000.o", "", 1),
                1,
            ),
            "link-object-order": log.replace(
                link_line,
                link_line.replace(
                    first_objects,
                    "./synthetic/unit_001.o ./synthetic/unit_000.o",
                    1,
                ),
                1,
            ),
            "link-option-order": log.replace(
                link_line,
                link_line.replace("-fPIC -shared", "-shared -fPIC", 1),
                1,
            ),
            "cxx-link": log.replace(
                link_line,
                link_line.replace(
                    "aarch64-linux-gnu-gcc",
                    "aarch64-linux-gnu-g++",
                    1,
                ),
                1,
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        pokemini.pokemini_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_synthetic_log_rejects_diagnostic_mutations(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compiles, link_argv, blocks, log = (
                build_pokemini_log_fixture(architecture)
            )
            arguments = self.contract_arguments(log, architecture)[1:]
            warning = pokemini.POKEMINI_EXPECTED_WARNING_LINES[architecture][0]
            context_line = blocks[0].splitlines()[0]
            diagnostic_text = "\n".join(blocks) + "\n"
            link_line = " ".join(link_argv) + "\n"
            mutations = {
                "missing-warning": log.replace(warning + "\n", "", 1),
                "changed-warning": log.replace(
                    "warning: this statement",
                    "warning: synthetic statement",
                    1,
                ),
                "missing-context": log.replace(context_line + "\n", "", 1),
                "extra-warning": log + "warning: synthetic warning\n",
                "extra-note": log + "note: synthetic note\n",
                "error": log + "error: synthetic error\n",
                "make": log + "make: *** [all] Error 2\n",
                "linker": log + "undefined reference to synthetic_symbol\n",
                "late-diagnostics": log.replace(diagnostic_text, "", 1)
                + diagnostic_text,
                "context-after-link": log.replace(
                    context_line + "\n", "", 1
                ).replace(link_line, link_line + context_line + "\n", 1),
            }
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                for label, changed in mutations.items():
                    with self.subTest(mutation=label):
                        self.assertFalse(
                            pokemini.pokemini_log_proves_contract(
                                changed, *arguments
                            )
                        )

    def test_shared_native_version_validator_is_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][pokemini.POKEMINI_CORE_ID]
        contract = spec["build"]["git_version"]
        source_commit = spec["source"]["commit"]
        for architecture in ("arm64", "armhf"):
            _exact, compile_lines, _link, _diagnostics, log = (
                build_pokemini_log_fixture(architecture)
            )
            compile_line = compile_lines[0]
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log, contract, source_commit, architecture
                    )
                )
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        log.replace(
                            compile_line,
                            compile_line.replace(
                                f" {pokemini.POKEMINI_NATIVE_GIT_VERSION_LOG_TOKEN}",
                                "",
                                1,
                            ),
                            1,
                        ),
                        contract,
                        source_commit,
                        architecture,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        log.replace(
                            compile_line,
                            compile_line.replace(
                                " -O2", " @compiler-options.rsp -O2", 1
                            ),
                            1,
                        ),
                        contract,
                        source_commit,
                        architecture,
                    )
                )

class PokeminiCompositionIntegrationTests(unittest.TestCase):
    def test_shared_generation_surfaces_preserve_native_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = pokemini.POKEMINI_CORE_ID
        spec = catalog["cores"][core_id]
        expected_version = {
            "derivation": pokemini.POKEMINI_NATIVE_GIT_VERSION_DERIVATION,
            "value": pokemini.POKEMINI_NATIVE_GIT_VERSION,
        }
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
        version_probe = (
            "make --no-print-directory -s "
            "-C /libretro-super/libretro-pokemini "
            "-f Makefile.libretro -f "
            "/tmp/core-pipeline-native-git-version-origin.mk "
            "core_pipeline_native_git_version_origin"
        )

        self.assertEqual(
            [pokemini.POKEMINI_NATIVE_VERSION_MARKER],
            pipeline.git_version_log_markers(spec),
        )
        version_shell = pipeline.git_version_shell(spec)
        self.assertIn(version_probe, version_shell)
        self.assertNotIn("-f Makefile -f /tmp/core-pipeline", version_shell)
        self.assertNotIn("GIT_CONFIG_PARAMETERS", version_shell)
        self.assertNotIn("core.abbrev", version_shell)
        self.assertEqual("", pipeline.make_variable_shell(spec))
        self.assertEqual([], pipeline.make_variable_log_markers(spec))

        build_shell = pipeline.libretro_build_shell(spec, core_id)
        self.assertEqual("./libretro-build.sh pokemini", build_shell)
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
                self.assertEqual(1, container_shell.count(generated_marker))
                self.assertLess(
                    container_shell.index(version_probe),
                    container_shell.index(build_shell),
                )
                self.assertLess(
                    container_shell.index(generated_marker),
                    container_shell.index(build_shell),
                )

    def test_composition_root_and_registry_bind_individual_contract(self) -> None:
        identity = pokemini.POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity, pipeline.POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        self.assertEqual(
            {
                "derivation": pokemini.POKEMINI_NATIVE_GIT_VERSION_DERIVATION,
                "value": pokemini.POKEMINI_NATIVE_GIT_VERSION,
            },
            pipeline.exact_native_git_version_contract(
                pokemini.POKEMINI_CORE_ID
            ),
        )
        contract = core_log_contract_for(pokemini.POKEMINI_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("pokemini-c-only-v1", contract.contract_id)
        self.assertEqual("pokemini_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({pokemini.POKEMINI_CORE_ID}), contract.core_ids
        )

    def test_catalog_guard_and_dispatch_use_individual_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        changed = copy.deepcopy(catalog)
        changed["cores"][pokemini.POKEMINI_CORE_ID]["build"]["git_version"][
            "compiler_scope"
        ] = "cxx"
        self.assertFalse(
            pokemini.pokemini_spec_is_well_formed(
                changed["cores"][pokemini.POKEMINI_CORE_ID]
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)

        contract, _compiles, link_argv, _diagnostics, log = (
            build_pokemini_log_fixture("arm64")
        )
        identity = pokemini.POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY
        with synthetic_contract("arm64", contract, link_argv):
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    log,
                    pokemini.POKEMINI_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                )
            )


if __name__ == "__main__":
    unittest.main()
