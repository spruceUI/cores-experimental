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
from core_pipeline_lib.contracts import c_only, fmsx
from core_pipeline_lib.contracts.command_line import ordered_command_argv_sha256
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT / "tests/fixtures/per-core-oracles/fmsx.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / fmsx.FMSX_CORE_ID
        / architecture
        / "build.log"
    )


def build_fmsx_log_fixture(
    architecture: str,
) -> tuple[
    c_only.COnlyLogContract,
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
        f"{compiler} -c -o synthetic/unit_{index:03d}.o "
        f"synthetic/unit_{index:03d}.c "
        f"{fmsx.FMSX_NATIVE_GIT_VERSION_LOG_TOKEN} "
        "-O2 -DNDEBUG -fPIC -D__LIBRETRO__"
        for index in range(fmsx.FMSX_EXPECTED_COMPILE_COUNT)
    )
    parsed_invocations = tuple(
        c_only.c_only_compile_invocation(shlex.split(line), {compiler})
        for line in compile_lines
    )
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct fMSX compile fixture")
    invocations = tuple(
        invocation
        for invocation in parsed_invocations
        if invocation is not None
    )
    pairs = tuple((output, source) for output, source, _tokens in invocations)
    objects = tuple(output for output, _source in pairs)
    link_argv = (
        compiler,
        "-o",
        fmsx.FMSX_BUILD_ARTIFACT_NAME,
        *fmsx.FMSX_EXPECTED_LINK_OPTIONS,
        *(f"./{path}" for path in objects),
    )
    contract = replace(
        fmsx.FMSX_LOG_CONTRACT,
        expected_compile_pair_sha256=(
            c_only.c_only_compile_pair_sha256(pairs)
        ),
        expected_compile_invocation_sha256={
            architecture: c_only.c_only_compile_invocation_sha256(invocations)
        },
        expected_link_object_sha256=(
            c_only.c_only_link_object_sha256(objects)
        ),
        expected_raw_link_object_sha256=(
            c_only.c_only_raw_link_object_sha256(
                f"./{path}" for path in objects
            )
        ),
    )
    log = (
        "\n".join(
            (
                fmsx.FMSX_SOURCE_HEAD_MARKER,
                fmsx.FMSX_NATIVE_VERSION_MARKER,
                *compile_lines,
                " ".join(link_argv),
            )
        )
        + "\n"
    )
    return contract, compile_lines, link_argv, log


@contextmanager
def synthetic_contract(
    architecture: str,
    contract: c_only.COnlyLogContract,
    link_argv: tuple[str, ...],
):
    ordered_digest = ordered_command_argv_sha256(list(link_argv))
    with mock.patch.object(
        fmsx,
        "FMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256",
        {architecture: ordered_digest},
    ), mock.patch.object(fmsx, "FMSX_LOG_CONTRACT", contract):
        yield


class FmsxModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = fmsx.FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            build_log_text,
            fmsx.FMSX_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_exact_catalog_and_promoted_contracts_are_core_owned(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][fmsx.FMSX_CORE_ID]
        identity = fmsx.FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        expected_version = {
            "derivation": fmsx.FMSX_NATIVE_GIT_VERSION_DERIVATION,
            "value": fmsx.FMSX_NATIVE_GIT_VERSION,
        }

        self.assertTrue(fmsx.fmsx_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(
                spec, fmsx.FMSX_CORE_ID
            )
        )
        self.assertEqual(expected_version, spec["build"]["git_version"])
        self.assertEqual(expected_version, pipeline.validated_git_version(spec))
        self.assertEqual({}, pipeline.validated_make_variables(spec))
        self.assertNotIn("compiler_scope", spec["build"]["git_version"])
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
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
            fmsx.fmsx_golden_source_is_well_formed(
                fmsx.FMSX_CORE_ID, source
            )
        )
        self.assertTrue(
            pipeline.native_git_version_golden_source_is_well_formed(
                fmsx.FMSX_CORE_ID, source
            )
        )
        self.assertTrue(
            fmsx.fmsx_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                fmsx.FMSX_CORE_ID,
                source,
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                fmsx.FMSX_CORE_ID,
                source,
            )
        )

        for label, changed_source in {
            "tree": {**source, "tree": "0" * 40},
            "resolved-commit": {**source, "resolved_commit": "0" * 40},
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/fmsx.git",
            },
            "submodule": {
                **source,
                "submodules": [{"path": "foreign", "commit": "0" * 40}],
            },
            "extra": {**source, "unexpected": True},
        }.items():
            with self.subTest(source=label):
                self.assertFalse(
                    fmsx.fmsx_golden_source_is_well_formed(
                        fmsx.FMSX_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    pipeline.native_git_version_golden_source_is_well_formed(
                        fmsx.FMSX_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    fmsx.fmsx_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        fmsx.FMSX_CORE_ID,
                        changed_source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        fmsx.FMSX_CORE_ID,
                        changed_source,
                    )
                )

        for label, changed_build in {
            "version": {
                **build,
                "git_version": {**expected_version, "value": " 0000000"},
            },
            "c-scope": {
                **build,
                "git_version": {
                    **expected_version,
                    "compiler_scope": "c",
                },
            },
            "cxx-scope": {
                **build,
                "git_version": {
                    **expected_version,
                    "compiler_scope": "cxx",
                },
            },
            "epoch": {**build, "source_date_epoch": 1},
            "make": {**build, "make_variables": {"IS_X86": 0}},
            "log": {**build, "log": "other.log"},
            "digest": {**build, "log_sha256": "invalid"},
            "extra": {**build, "unexpected": True},
        }.items():
            with self.subTest(build=label):
                self.assertFalse(
                    fmsx.fmsx_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        fmsx.FMSX_CORE_ID,
                        source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        fmsx.FMSX_CORE_ID,
                        source,
                    )
                )

    def test_catalog_predicate_rejects_every_owned_boundary(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][fmsx.FMSX_CORE_ID]

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
                "source-url",
                lambda changed: changed["source"].update(
                    {"url": "https://example.com/fmsx.git"}
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
                "missing-version",
                lambda changed: changed["build"].pop("git_version"),
            ),
            mutation(
                "scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "c"}
                ),
            ),
            mutation(
                "cxx-scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "cxx"}
                ),
            ),
            mutation(
                "epoch",
                lambda changed: changed["build"].update(
                    {"source_date_epoch": 1780599766}
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
                self.assertFalse(fmsx.fmsx_spec_is_well_formed(changed))

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
        self.assertEqual(
            {"$ref": "#/$defs/fmsxCore"},
            catalog_schema["properties"]["cores"]["properties"][
                fmsx.FMSX_CORE_ID
            ],
        )
        exact = catalog_schema["$defs"]["fmsxCore"]["allOf"][1]
        self.assertEqual(
            {"workflow", "source", "build", "metadata", "targets"},
            set(exact["required"]),
        )
        catalog_version = exact["properties"]["build"]["properties"][
            "git_version"
        ]["allOf"][1]
        self.assertEqual(
            ["derivation", "value"],
            catalog_version["propertyNames"]["enum"],
        )
        self.assertNotIn("compiler_scope", catalog_version["properties"])
        self.assertEqual(
            {"const": fmsx.FMSX_NATIVE_GIT_VERSION},
            catalog_version["properties"]["value"],
        )

        self.assertEqual(
            {
                "allOf": [
                    {"$ref": "#/$defs/nativeGitVersion"},
                    {
                        "propertyNames": {
                            "enum": ["derivation", "value"]
                        },
                        "properties": {
                            "value": {
                                "const": fmsx.FMSX_NATIVE_GIT_VERSION
                            }
                        },
                    },
                ]
            },
            golden_schema["$defs"]["fmsxNativeGitVersion"],
        )
        exact_build = golden_schema["$defs"]["buildGolden"][
            "dependentSchemas"
        ]["build"]
        branches = {
            branch["properties"]["core_id"]["const"]: branch
            for branch in exact_build["then"]["oneOf"]
        }
        branch = branches[fmsx.FMSX_CORE_ID]["properties"]
        source = branch["source"]
        expected_source_keys = {
            "url",
            "requested_ref",
            "commit",
            "tree",
            "resolved_commit",
            "resolved_url",
            "submodules",
        }
        self.assertEqual(expected_source_keys, set(source["required"]))
        self.assertEqual(
            expected_source_keys, set(source["propertyNames"]["enum"])
        )
        build = branch["build"]
        self.assertEqual(
            {"$ref": "#/$defs/fmsxNativeGitVersion"},
            build["properties"]["git_version"],
        )
        expected_build_keys = {
            "driver",
            "environment",
            "compile_definitions",
            "git_version",
            "log",
            "log_sha256",
        }
        self.assertEqual(expected_build_keys, set(build["required"]))
        self.assertEqual(
            expected_build_keys, set(build["propertyNames"]["enum"])
        )

    def test_reviewed_build_fingerprints_are_individual_and_exact(self) -> None:
        self.assertEqual(31, fmsx.FMSX_EXPECTED_COMPILE_COUNT)
        self.assertEqual(
            "a1439ee1038cef8d0ba4e80989a4e8d149ccb6dc6257256b3e45f001a7416286",
            fmsx.FMSX_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "f5e30ab376935c5cd6e952e4390451198c6c53674f24f6899d96982d58b63d59"
                ),
                "armhf": (
                    "48022dc7f8ddc706c0ee6a6b4f0adbff770348575aebb46e50d37f8ecdeac050"
                ),
            },
            fmsx.FMSX_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            "6acaf4be9c83c81a78e315870e85fb622db139328777395611eb44fef07c4b6a",
            fmsx.FMSX_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            "af4895bbc360f6d34d4fd7abd11ab879736d3bacccddd402fa6a120fac2601ea",
            fmsx.FMSX_EXPECTED_RAW_LINK_OBJECT_SHA256,
        )

    def test_synthetic_logs_prove_both_architecture_contracts(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _compiles, link_argv, log = build_fmsx_log_fixture(
                architecture
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    fmsx.fmsx_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_synthetic_log_rejects_marker_and_identity_mutations(self) -> None:
        contract, _compiles, link_argv, log = build_fmsx_log_fixture("arm64")
        arguments = self.contract_arguments(log)[1:]
        head = fmsx.FMSX_SOURCE_HEAD_MARKER
        marker = fmsx.FMSX_NATIVE_VERSION_MARKER
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "missing-marker": log.replace(marker + "\n", "", 1),
            "late-marker": log.replace(marker + "\n", "", 1) + marker + "\n",
            "wrong-origin": log.replace("|file", "|command line", 1),
            "wrong-version": log.replace(" f013e21", " 0000000", 1),
            "injected-version": (
                log + "CORE_PIPELINE_GIT_VERSION|-f013e21|command line\n"
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        fmsx.fmsx_log_proves_contract(changed, *arguments)
                    )
            for label, changed_arguments in {
                "core": (
                    "bluemsx",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                ),
                "commit": (
                    fmsx.FMSX_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                ),
                "tree": (
                    fmsx.FMSX_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                ),
                "architecture": (
                    fmsx.FMSX_CORE_ID,
                    "unknown",
                    contract.source_commit,
                    contract.source_tree,
                ),
            }.items():
                with self.subTest(identity=label):
                    self.assertFalse(
                        fmsx.fmsx_log_proves_contract(
                            log, *changed_arguments
                        )
                    )

    def test_synthetic_log_rejects_compile_link_and_diagnostic_mutations(
        self,
    ) -> None:
        contract, compile_lines, link_argv, log = build_fmsx_log_fixture(
            "arm64"
        )
        arguments = self.contract_arguments(log)[1:]
        compile_line = compile_lines[0]
        link_line = " ".join(link_argv)
        first_objects = "./synthetic/unit_000.o ./synthetic/unit_001.o"
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
                    f" {fmsx.FMSX_NATIVE_GIT_VERSION_LOG_TOKEN}", "", 1
                ),
                1,
            ),
            "warning-suppression": log.replace(
                compile_line,
                compile_line.replace(" -O2", " -w -O2", 1),
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
                link_line.replace(
                    "-shared -Wl,-version-script=link.T",
                    "-Wl,-version-script=link.T -shared",
                    1,
                ),
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
            "warning": log + "warning: synthetic warning\n",
            "note": log + "note: synthetic note\n",
            "error": log + "error: synthetic error\n",
            "make": log + "make: *** [all] Error 2\n",
            "linker": log + "undefined reference to synthetic_symbol\n",
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        fmsx.fmsx_log_proves_contract(changed, *arguments)
                    )

    def test_shared_native_version_validator_binds_every_c_compile(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][fmsx.FMSX_CORE_ID]
        contract = spec["build"]["git_version"]
        source_commit = spec["source"]["commit"]
        for architecture in ("arm64", "armhf"):
            _exact, compile_lines, _link, log = build_fmsx_log_fixture(
                architecture
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
                                f" {fmsx.FMSX_NATIVE_GIT_VERSION_LOG_TOKEN}",
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

class FmsxCompositionIntegrationTests(unittest.TestCase):
    def test_shared_generation_surfaces_preserve_native_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = fmsx.FMSX_CORE_ID
        spec = catalog["cores"][core_id]
        expected_version = {
            "derivation": fmsx.FMSX_NATIVE_GIT_VERSION_DERIVATION,
            "value": fmsx.FMSX_NATIVE_GIT_VERSION,
        }
        expected_normalized = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": expected_version,
        }
        version_probe = (
            "make --no-print-directory -s "
            "-C /libretro-super/libretro-fmsx "
            "-f Makefile -f "
            "/tmp/core-pipeline-native-git-version-origin.mk "
            "core_pipeline_native_git_version_origin"
        )
        generated_marker = (
            "CORE_PIPELINE_NATIVE_GIT_VERSION|$(GIT_VERSION)|"
            "$(origin GIT_VERSION)"
        )

        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(spec, core_id)
        )
        self.assertEqual(
            expected_version,
            pipeline.exact_native_git_version_contract(core_id),
        )
        self.assertEqual(
            [fmsx.FMSX_NATIVE_VERSION_MARKER],
            pipeline.git_version_log_markers(spec),
        )
        version_shell = pipeline.git_version_shell(spec)
        self.assertIn(version_probe, version_shell)
        self.assertNotIn("Makefile.libretro", version_shell)
        self.assertEqual("", pipeline.make_variable_shell(spec))
        self.assertEqual([], pipeline.make_variable_log_markers(spec))

        build_shell = pipeline.libretro_build_shell(spec, core_id)
        self.assertEqual("./libretro-build.sh fmsx", build_shell)
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

        workflow_template = (
            ROOT / ".github/workflows/build-vice_x64.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            workflow_template.replace("vice_x64", core_id),
            (ROOT / spec["workflow"]).read_text(encoding="utf-8"),
        )

    def test_composition_root_and_registry_bind_individual_contract(self) -> None:
        identity = fmsx.FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(identity, pipeline.FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY)
        contract = core_log_contract_for(fmsx.FMSX_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("fmsx-c-only-v1", contract.contract_id)
        self.assertEqual("fmsx_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({fmsx.FMSX_CORE_ID}), contract.core_ids)

    def test_catalog_guard_and_dispatch_use_individual_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        changed = copy.deepcopy(catalog)
        changed["cores"][fmsx.FMSX_CORE_ID]["build"]["git_version"][
            "compiler_scope"
        ] = "c"
        self.assertFalse(
            fmsx.fmsx_spec_is_well_formed(
                changed["cores"][fmsx.FMSX_CORE_ID]
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)

        contract, _compiles, link_argv, log = build_fmsx_log_fixture("arm64")
        identity = fmsx.FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        with synthetic_contract("arm64", contract, link_argv):
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    log,
                    fmsx.FMSX_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                )
            )


if __name__ == "__main__":
    unittest.main()
