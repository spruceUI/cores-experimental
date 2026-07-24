from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shlex
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mixed_language, vice_x64
from core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT / "tests/fixtures/per-core-oracles/vice_x64.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / vice_x64.VICE_X64_CORE_ID
        / architecture
        / "build.log"
    )


def build_vice_x64_log_fixture(
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
    version_token = vice_x64.VICE_X64_NATIVE_GIT_VERSION_LOG_TOKEN
    core_token = vice_x64.VICE_X64_CORE_NAME_LOG_TOKEN
    machine_token = vice_x64.VICE_X64_MACHINE_COMPILE_TOKEN
    compile_lines = (
        (
            f"{c_compiler} {core_token} {machine_token} {version_token} "
            "-O3 -fPIC -c -o build/./c/unit.o c/unit.c"
        ),
        (
            f"{cxx_compiler} {core_token} {machine_token} {version_token} "
            "-O3 -fPIC -std=c++98 -c -o build/./cxx/unit.o cxx/unit.cc"
        ),
    )
    expected_compilers = {c_compiler, cxx_compiler}
    expected_cxx_compilers = {cxx_compiler}
    parsed_invocations = [
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            expected_compilers,
            expected_cxx_compilers,
            vice_x64.VICE_X64_SEMANTIC_PATH_ALIASES,
        )
        for line in compile_lines
    ]
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct VICE x64 compile fixture")
    invocations = [
        invocation
        for invocation in parsed_invocations
        if invocation is not None
    ]
    pairs = [
        (output, source)
        for output, source, _language, *_raw in invocations
    ]
    raw_objects = tuple(
        raw_output
        for *_prefix, raw_output, _source, _argv in invocations
    )
    link_argv = (
        cxx_compiler,
        "-o",
        vice_x64.VICE_X64_BUILD_ARTIFACT_NAME,
        *raw_objects,
        *vice_x64.VICE_X64_EXPECTED_LINK_OPTIONS,
    )
    ordered_link_sha256 = ordered_command_argv_sha256(link_argv)
    if ordered_link_sha256 is None:
        raise AssertionError("failed to construct VICE x64 link fixture")
    contract = replace(
        vice_x64.VICE_X64_LOG_CONTRACT,
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
            mixed_language.mixed_language_link_object_sha256(
                output for output, _source in pairs
            )
        ),
        expected_raw_link_object_sha256=(
            mixed_language.mixed_language_raw_link_object_sha256(raw_objects)
        ),
        expected_ordered_link_argv_sha256={
            architecture: ordered_link_sha256
        },
    )
    log = (
        "\n".join(
            (
                vice_x64.VICE_X64_SOURCE_HEAD_MARKER,
                vice_x64.VICE_X64_GIT_ABBREV_MARKER,
                vice_x64.VICE_X64_NATIVE_VERSION_MARKER,
                vice_x64.VICE_X64_CFLAGS_MARKER,
                *compile_lines,
                " ".join(link_argv),
            )
        )
        + "\n"
    )
    return contract, link_argv, log


@contextmanager
def synthetic_contract(
    contract: mixed_language.MixedLanguageLogContract,
):
    with mock.patch.object(
        vice_x64,
        "VICE_X64_EXPECTED_COMPILE_COUNT",
        contract.expected_compile_count,
    ), mock.patch.object(
        vice_x64,
        "VICE_X64_LOG_CONTRACT",
        contract,
    ):
        yield


class ViceX64ModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = vice_x64.VICE_X64_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            build_log_text,
            vice_x64.VICE_X64_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_workflow_is_exact_publication_disabled_template(self) -> None:
        template = (
            ROOT / ".github" / "workflows" / "build-gearcoleco.yml"
        ).read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github" / "workflows" / "build-vice_x64.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(template.replace("gearcoleco", "vice_x64"), workflow)
        self.assertEqual(1, workflow.count("--core vice_x64"))
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)

    def test_native_short10_epoch_recipe_is_exact_and_sanitized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][vice_x64.VICE_X64_CORE_ID]
        source = {
            "url": "https://github.com/libretro/vice-libretro.git",
            "requested_ref": "refs/heads/master",
            "commit": "7946cfa0d3775e958616d4d107de867a4616ae6c",
            "tree": "db2760ffc97b9c20ef8777fcb7689082be66bc45",
        }
        version = {
            "derivation": "native-space-short10-v1",
            "value": " 7946cfa0d3",
        }
        expected = {
            "workflow": ".github/workflows/build-vice_x64.yml",
            "source": source,
            "build": {
                "driver": "libretro-super",
                "source_key": "vice_x64",
                "source_dir": "libretro-vice",
                "output_path": "dist/unix/vice_x64_libretro.so",
                "artifact_name": "vice_x64_libretro.so",
                "source_date_epoch": 1780486798,
                "git_version": version,
            },
            "metadata": {
                "source_path": (
                    "/libretro-super/dist/info/vice_x64_libretro.info"
                ),
                "artifact_name": "vice_x64_libretro.info",
            },
            "targets": ["arm64", "armhf"],
        }
        self.assertEqual(expected, spec)
        self.assertTrue(vice_x64.vice_x64_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_version_short10_spec_is_well_formed(
                spec, vice_x64.VICE_X64_CORE_ID
            )
        )
        self.assertEqual(
            version,
            pipeline.exact_native_git_version_contract(
                vice_x64.VICE_X64_CORE_ID
            ),
        )
        self.assertEqual(version, pipeline.validated_git_version(spec))
        self.assertEqual(
            1780486798, pipeline.validated_source_date_epoch(spec)
        )
        self.assertEqual({}, pipeline.validated_make_variables(spec))
        self.assertNotIn("EMUTYPE", spec["build"])
        markers = [
            vice_x64.VICE_X64_GIT_ABBREV_MARKER,
            vice_x64.VICE_X64_NATIVE_VERSION_MARKER,
        ]
        self.assertEqual(markers, pipeline.git_version_log_markers(spec))
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                self.assertEqual(
                    {
                        "driver": "libretro-super",
                        "environment": "sanitized-v1",
                        "compile_definitions": [],
                        "git_version": version,
                        "source_date_epoch": 1780486798,
                    },
                    pipeline.normalized_build_contract(spec, architecture),
                )

        shell = pipeline.git_version_shell(spec)
        config_lines = (
            "export GIT_CONFIG_SYSTEM=/dev/null",
            "export GIT_CONFIG_GLOBAL=/dev/null",
            "export GIT_CONFIG_PARAMETERS=\"'core.abbrev=10'\"",
        )
        for line in config_lines:
            self.assertEqual(1, shell.count(line))
        for incompatible_export in (
            "export GIT_CONFIG_COUNT=",
            "export GIT_CONFIG_KEY_",
            "export GIT_CONFIG_VALUE_",
        ):
            self.assertNotIn(incompatible_export, shell)
        self.assertIn("git config --show-origin --get core.abbrev", shell)
        self.assertIn("$(printf 'command line:\\t10')", shell)
        self.assertIn(vice_x64.VICE_X64_GIT_ABBREV_MARKER, shell)
        self.assertIn(
            "-C /libretro-super/libretro-vice -f Makefile -f ", shell
        )
        self.assertNotIn("Makefile.libretro", shell)

        build_script = pipeline.container_build_script(
            vice_x64.VICE_X64_CORE_ID, "arm64", spec, catalog["resolver"]
        )
        config_position = build_script.index(config_lines[0])
        marker_position = build_script.index(
            vice_x64.VICE_X64_GIT_ABBREV_MARKER
        )
        probe_position = build_script.index(
            "core_pipeline_native_git_version_origin", marker_position
        )
        build_position = build_script.index("./libretro-build.sh vice_x64")
        self.assertLess(config_position, marker_position)
        self.assertLess(marker_position, probe_position)
        self.assertLess(probe_position, build_position)
        self.assertNotIn("EMUTYPE=", build_script)
        for incompatible_export in (
            "export GIT_CONFIG_COUNT=",
            "export GIT_CONFIG_KEY_",
            "export GIT_CONFIG_VALUE_",
        ):
            self.assertNotIn(incompatible_export, build_script)

        prelude = pipeline.sanitized_shell_prelude()
        fixed_controls = {
            "GIT_CONFIG_COUNT",
            "GIT_CONFIG_PARAMETERS",
            "GIT_CONFIG_SYSTEM",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_CONFIG",
        }
        unset_line = next(
            line for line in prelude.splitlines() if line.startswith("unset ")
        )
        self.assertTrue(fixed_controls.issubset(set(unset_line.split()[1:])))
        self.assertIn("GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*", prelude)
        self.assertIn('unset "$core_pipeline_environment_name"', prelude)

    def test_catalog_identity_epoch_and_copy_mutations_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(catalog)
            mutate(changed)
            return label, changed

        core_id = vice_x64.VICE_X64_CORE_ID
        mutations = (
            mutation(
                "source-commit",
                lambda changed: changed["cores"][core_id]["source"].update(
                    {"commit": "a" * 40}
                ),
            ),
            mutation(
                "source-tree",
                lambda changed: changed["cores"][core_id]["source"].update(
                    {"tree": "b" * 40}
                ),
            ),
            mutation(
                "wrong-ref",
                lambda changed: changed["cores"][core_id]["source"].update(
                    {"requested_ref": "refs/heads/main"}
                ),
            ),
            mutation(
                "missing-epoch",
                lambda changed: changed["cores"][core_id]["build"].pop(
                    "source_date_epoch"
                ),
            ),
            mutation(
                "epoch-drift",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"source_date_epoch": 1780486799}
                ),
            ),
            mutation(
                "boolean-epoch",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"source_date_epoch": True}
                ),
            ),
            mutation(
                "short7",
                lambda changed: changed["cores"][core_id]["build"][
                    "git_version"
                ].update(
                    {
                        "derivation": "native-space-short7-v1",
                        "value": " 7946cfa",
                    }
                ),
            ),
            mutation(
                "wrong-short10",
                lambda changed: changed["cores"][core_id]["build"][
                    "git_version"
                ].update({"value": " 0000000000"}),
            ),
            mutation(
                "compiler-scope",
                lambda changed: changed["cores"][core_id]["build"][
                    "git_version"
                ].update({"compiler_scope": "cxx"}),
            ),
            mutation(
                "catalog-git-config",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"git_config": {"core.abbrev": 10}}
                ),
            ),
            mutation(
                "make-variable-emutype",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"make_variables": {"EMUTYPE": 1}}
                ),
            ),
            mutation(
                "x64-uses-xvic-resolver-key",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"source_key": "vice_xvic"}
                ),
            ),
            mutation(
                "x64-uses-xvic-artifact",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {
                        "output_path": "dist/unix/vice_xvic_libretro.so",
                        "artifact_name": "vice_xvic_libretro.so",
                    }
                ),
            ),
            mutation(
                "whole-xvic-spec-copied-to-x64",
                lambda changed: changed["cores"].update(
                    {
                        core_id: copy.deepcopy(
                            changed["cores"]["vice_xvic"]
                        )
                    }
                ),
            ),
        )
        for label, changed in mutations:
            with self.subTest(mutation=label):
                self.assertFalse(
                    vice_x64.vice_x64_spec_is_well_formed(
                        changed["cores"][core_id]
                    )
                )
                with self.assertRaises(pipeline.PipelineError):
                    pipeline.validate_catalog(changed)

    def test_generic_short10_log_proof_binds_abbrev_and_each_compile(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][vice_x64.VICE_X64_CORE_ID]
        contract = spec["build"]["git_version"]
        config_marker, version_marker = pipeline.git_version_log_markers(spec)
        version_token = vice_x64.VICE_X64_NATIVE_GIT_VERSION_LOG_TOKEN
        compilers = {
            "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
            "armhf": (
                "arm-a30-linux-gnueabihf-gcc",
                "arm-a30-linux-gnueabihf-g++",
            ),
        }

        def valid_log(architecture: str) -> str:
            c_compiler, cxx_compiler = compilers[architecture]
            return (
                "\n".join(
                    (
                        config_marker,
                        version_marker,
                        f"{c_compiler} {version_token} -c source.c -o source.o",
                        (
                            f"{cxx_compiler} {version_token} -c source.cpp "
                            "-o source-cxx.o"
                        ),
                    )
                )
                + "\n"
            )

        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        valid_log(architecture),
                        contract,
                        spec["source"]["commit"],
                        architecture,
                    )
                )

        baseline = valid_log("arm64")
        lines = baseline.splitlines()
        mutations = {
            "missing-config-marker": baseline.replace(
                config_marker + "\n", "", 1
            ),
            "duplicate-config-marker": config_marker + "\n" + baseline,
            "wrong-config-origin": baseline.replace(
                "command line:", "file:", 1
            ),
            "wrong-config-value": baseline.replace("line:|10", "line:|7", 1),
            "late-config-marker": (
                "\n".join(
                    (version_marker, lines[2], config_marker, *lines[3:])
                )
                + "\n"
            ),
            "wrong-make-origin": baseline.replace(
                "|file", "|environment", 1
            ),
            "wrong-version-value": baseline.replace(
                " 7946cfa0d3", " 0000000000", 1
            ),
            "short7-token": baseline.replace(
                version_token, r'-DGIT_VERSION=\"" 7946cfa"\"', 1
            ),
            "missing-c-token": baseline.replace(
                " " + version_token, "", 1
            ),
            "missing-cxx-token": baseline.replace(
                "aarch64-linux-gnu-g++ " + version_token,
                "aarch64-linux-gnu-g++",
                1,
            ),
            "duplicate-token": baseline.replace(
                version_token, version_token + " " + version_token, 1
            ),
            "alternate-definition": baseline.replace(
                version_token,
                version_token + r' -DGIT_VERSION=\"" 0000000000"\"',
                1,
            ),
            "split-definition": baseline.replace(
                version_token,
                version_token + r' -D GIT_VERSION=\"" 0000000000"\"',
                1,
            ),
            "undefine": baseline.replace(
                version_token, version_token + " -UGIT_VERSION", 1
            ),
            "split-undefine": baseline.replace(
                version_token, version_token + " -U GIT_VERSION", 1
            ),
            "preprocessor-undefine": baseline.replace(
                version_token,
                version_token + " -Xpreprocessor -UGIT_VERSION",
                1,
            ),
            "wp-undefine": baseline.replace(
                version_token, version_token + " -Wp,-UGIT_VERSION", 1
            ),
            "equals-preprocessor": baseline.replace(
                version_token,
                version_token + " -Xpreprocessor=-UGIT_VERSION",
                1,
            ),
            "response-file": baseline.replace(
                " -c source.c", " @compiler-options.rsp -c source.c", 1
            ),
        }
        for label, changed_log in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        changed_log,
                        contract,
                        spec["source"]["commit"],
                        "arm64",
                    )
                )

    def test_golden_source_build_and_epoch_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][vice_x64.VICE_X64_CORE_ID]
        source = {
            **spec["source"],
            "resolved_commit": spec["source"]["commit"],
            "resolved_url": spec["source"]["url"],
            "submodules": [],
        }
        build = {
            **pipeline.normalized_build_contract(spec, "arm64"),
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            vice_x64.vice_x64_golden_source_is_well_formed(
                vice_x64.VICE_X64_CORE_ID, source
            )
        )
        self.assertTrue(
            vice_x64.vice_x64_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                vice_x64.VICE_X64_CORE_ID,
                source,
            )
        )
        self.assertTrue(
            pipeline.native_git_version_golden_source_is_well_formed(
                vice_x64.VICE_X64_CORE_ID, source
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                vice_x64.VICE_X64_CORE_ID,
                source,
            )
        )

        source_mutations = {
            "tree": {**source, "tree": "b" * 40},
            "resolved-commit": {**source, "resolved_commit": "c" * 40},
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/vice-libretro.git",
            },
            "submodule": {
                **source,
                "submodules": [
                    {"path": "deps/foreign", "commit": "d" * 40}
                ],
            },
            "extra": {**source, "unexpected": True},
        }
        for label, changed_source in source_mutations.items():
            with self.subTest(source_mutation=label):
                self.assertFalse(
                    vice_x64.vice_x64_golden_source_is_well_formed(
                        vice_x64.VICE_X64_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    pipeline.native_git_version_golden_source_is_well_formed(
                        vice_x64.VICE_X64_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    vice_x64.vice_x64_golden_build_contract_is_well_formed(
                        build,
                        spec["source"]["commit"],
                        vice_x64.VICE_X64_CORE_ID,
                        changed_source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        build,
                        spec["source"]["commit"],
                        vice_x64.VICE_X64_CORE_ID,
                        changed_source,
                    )
                )

        build_mutations = {
            "missing-epoch": {
                key: value
                for key, value in build.items()
                if key != "source_date_epoch"
            },
            "epoch-drift": {**build, "source_date_epoch": 1780486799},
            "boolean-epoch": {**build, "source_date_epoch": True},
            "short7": {
                **build,
                "git_version": {
                    "derivation": "native-space-short7-v1",
                    "value": " 7946cfa",
                },
            },
            "wrong-short10": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "value": " 0000000000",
                },
            },
            "compiler-scope": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "compiler_scope": "cxx",
                },
            },
            "extra": {**build, "unexpected": True},
        }
        for label, changed_build in build_mutations.items():
            with self.subTest(build_mutation=label):
                self.assertFalse(
                    vice_x64.vice_x64_golden_build_contract_is_well_formed(
                        changed_build,
                        spec["source"]["commit"],
                        vice_x64.VICE_X64_CORE_ID,
                        source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        changed_build,
                        spec["source"]["commit"],
                        vice_x64.VICE_X64_CORE_ID,
                        source,
                    )
                )

    def test_short10_schema_contract_is_exact_and_disjoint(self) -> None:
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
        expected = {
            "type": "object",
            "required": ["derivation", "value"],
            "properties": {
                "derivation": {"const": "native-space-short10-v1"},
                "value": {"const": " 7946cfa0d3"},
            },
            "additionalProperties": False,
        }
        for schema in (catalog_schema, golden_schema):
            with self.subTest(schema=schema["$id"]):
                self.assertEqual(
                    expected, schema["$defs"]["viceNativeGitVersion"]
                )
                derivations = {
                    schema["$defs"][name]["properties"]["derivation"][
                        "const"
                    ]
                    for name in (
                        "gitVersion",
                        "nativeGitVersion",
                        "nativeGitDescribeVersion",
                        "viceNativeGitVersion",
                    )
                }
                self.assertEqual(4, len(derivations))

        definition = "viceX64Core"
        self.assertEqual(
            {"$ref": f"#/$defs/{definition}"},
            catalog_schema["properties"]["cores"]["properties"][
                vice_x64.VICE_X64_CORE_ID
            ],
        )
        exact = catalog_schema["$defs"][definition]["allOf"][1]
        build = exact["properties"]["build"]
        self.assertEqual(
            {
                "artifact_name",
                "driver",
                "git_version",
                "output_path",
                "source_date_epoch",
                "source_dir",
                "source_key",
            },
            set(build["required"]),
        )
        self.assertEqual(
            {"$ref": "#/$defs/viceNativeGitVersion"},
            build["properties"]["git_version"],
        )
        self.assertEqual(
            {"const": 1780486798},
            build["properties"]["source_date_epoch"],
        )

        exact_build = golden_schema["$defs"]["buildGolden"][
            "dependentSchemas"
        ]["build"]
        branches = {
            branch["properties"]["core_id"]["const"]: branch
            for branch in exact_build["then"]["oneOf"]
        }
        golden_build = branches[vice_x64.VICE_X64_CORE_ID]["properties"][
            "build"
        ]
        self.assertIn("source_date_epoch", golden_build["required"])
        self.assertEqual(
            {"const": 1780486798},
            golden_build["properties"]["source_date_epoch"],
        )
        self.assertEqual(
            {"$ref": "#/$defs/viceNativeGitVersion"},
            golden_build["properties"]["git_version"],
        )

    def test_production_contract_constants_match_reviewed_oracle(self) -> None:
        contract = ORACLE_FIXTURE["production_log_contract"]
        self.assertEqual(
            contract["compile_count"],
            vice_x64.VICE_X64_EXPECTED_COMPILE_COUNT,
        )
        self.assertEqual(
            contract["language_counts"],
            vice_x64.VICE_X64_EXPECTED_LANGUAGE_COUNTS,
        )
        self.assertEqual(
            contract["source_suffix_counts"],
            vice_x64.VICE_X64_EXPECTED_SOURCE_SUFFIX_COUNTS,
        )
        self.assertEqual(
            contract["compile_pair_sha256"],
            vice_x64.VICE_X64_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            contract["compile_invocation_sha256"],
            vice_x64.VICE_X64_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            contract["link_object_sha256"],
            vice_x64.VICE_X64_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            contract["raw_link_object_sha256"],
            vice_x64.VICE_X64_EXPECTED_RAW_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            contract["ordered_link_argv_sha256"],
            vice_x64.VICE_X64_EXPECTED_ORDERED_LINK_ARGV_SHA256,
        )
        self.assertEqual(
            contract["diagnostic_lines_sha256"],
            vice_x64.VICE_X64_EXPECTED_DIAGNOSTIC_LINES_SHA256,
        )

    def test_synthetic_logs_prove_both_architecture_contracts(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _link_argv, log = build_vice_x64_log_fixture(
                architecture
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                self.assertTrue(
                    vice_x64.vice_x64_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_registry_identity_is_owned_by_vice_x64(self) -> None:
        contract = core_log_contract_for(vice_x64.VICE_X64_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("vice-x64-mixed-language-v1", contract.contract_id)
        self.assertEqual("vice_x64_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({vice_x64.VICE_X64_CORE_ID}), contract.core_ids
        )

    def test_synthetic_log_rejects_contract_mutations(self) -> None:
        contract, link_argv, log = build_vice_x64_log_fixture("arm64")
        arguments = self.contract_arguments(log)[1:]
        head = vice_x64.VICE_X64_SOURCE_HEAD_MARKER
        config = vice_x64.VICE_X64_GIT_ABBREV_MARKER
        marker = vice_x64.VICE_X64_NATIVE_VERSION_MARKER
        version_token = vice_x64.VICE_X64_NATIVE_GIT_VERSION_LOG_TOKEN
        core_token = vice_x64.VICE_X64_CORE_NAME_LOG_TOKEN
        machine_token = vice_x64.VICE_X64_MACHINE_COMPILE_TOKEN
        compile_line = next(
            line
            for line in log.splitlines()
            if line.startswith("aarch64-linux-gnu-gcc ")
        )
        link_line = " ".join(link_argv)
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "missing-config": log.replace(config + "\n", "", 1),
            "duplicate-config": config + "\n" + log,
            "wrong-config-origin": log.replace("command line:", "file:", 1),
            "wrong-config-value": log.replace("line:|10", "line:|7", 1),
            "missing-version-marker": log.replace(marker + "\n", "", 1),
            "wrong-version-origin": log.replace("|file", "|environment", 1),
            "late-version-marker": (
                log.replace(marker + "\n", "", 1) + marker + "\n"
            ),
            "wrong-version": log.replace(
                version_token, r'-DGIT_VERSION=\"" 0000000000"\"', 1
            ),
            "wrong-core": log.replace(
                core_token, r'-DCORE_NAME=\"xvic\"', 1
            ),
            "wrong-machine": log.replace(machine_token, "-D__XVIC__", 1),
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "compile-option": log.replace(
                compile_line, compile_line.replace("-O3", "-O2", 1), 1
            ),
            "response-file": log.replace(
                compile_line,
                compile_line.replace(" -O3", " @args.rsp -O3", 1),
                1,
            ),
            "link-option": log.replace(
                link_line,
                link_line.replace("-Wl,--gc-sections", "-Wl,--as-needed"),
                1,
            ),
            "link-order": log.replace(
                link_line,
                link_line.replace(
                    "build/./c/unit.o build/./cxx/unit.o",
                    "build/./cxx/unit.o build/./c/unit.o",
                ),
                1,
            ),
            "warning": log + "warning: synthetic warning\n",
            "note": log + "note: synthetic note\n",
            "error": log + "error: synthetic error\n",
            "make-failure": log + "make: *** [all] Error 2\n",
        }
        with synthetic_contract(contract):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        vice_x64.vice_x64_log_proves_contract(
                            changed, *arguments
                        )
                    )
            self.assertFalse(
                vice_x64.vice_x64_log_proves_contract(
                    log,
                    "vice_xvic",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                vice_x64.vice_x64_log_proves_contract(
                    log,
                    vice_x64.VICE_X64_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                vice_x64.vice_x64_log_proves_contract(
                    log,
                    vice_x64.VICE_X64_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                )
            )

if __name__ == "__main__":
    unittest.main()
