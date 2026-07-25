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
from core_pipeline_lib.contracts import gearcoleco, mixed_language
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT / "tests/fixtures/per-core-oracles/gearcoleco.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / gearcoleco.GEARCOLECO_CORE_ID
        / architecture
        / "build.log"
    )


def build_gearcoleco_log_fixture(
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
    token = gearcoleco.GEARCOLECO_NATIVE_GIT_DESCRIBE_LOG_TOKEN
    compile_lines = (
        f"{c_compiler} {token} -O3 -fPIC -c -o c/unit.o c/unit.c",
        (
            f"{cxx_compiler} {token} -O3 -fPIC -std=c++11 "
            "-c -o ../../src/Processor.o ../../src/Processor.cpp"
        ),
        (
            f"{cxx_compiler} {token} -O3 -fPIC -std=c++11 "
            "-c -o cxx/unit.o cxx/unit.cpp"
        ),
    )
    expected_compilers = {c_compiler, cxx_compiler}
    expected_cxx_compilers = {cxx_compiler}
    parsed_invocations = [
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            expected_compilers,
            expected_cxx_compilers,
            gearcoleco.GEARCOLECO_SEMANTIC_PATH_ALIASES,
        )
        for line in compile_lines
    ]
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct GearColeco compile fixture")
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
        "-fPIC",
        "-shared",
        "-Wl,-version-script=./link.T",
        "-o",
        gearcoleco.GEARCOLECO_BUILD_ARTIFACT_NAME,
        *objects,
        "-lm",
    )
    contract = replace(
        gearcoleco.GEARCOLECO_LOG_CONTRACT,
        expected_compile_count=len(compile_lines),
        expected_language_counts={"c": 1, "cxx": 2},
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
    diagnostic_block = gearcoleco.GEARCOLECO_EXPECTED_DIAGNOSTIC_BLOCKS[
        architecture
    ]
    log = (
        "\n".join(
            (
                gearcoleco.GEARCOLECO_SOURCE_HEAD_MARKER,
                gearcoleco.GEARCOLECO_NATIVE_VERSION_MARKER,
                *compile_lines[:2],
                diagnostic_block,
                *compile_lines[2:],
                " ".join(link_argv),
                gearcoleco.GEARCOLECO_BUILD_COMPLETE_MARKER,
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
        gearcoleco,
        "GEARCOLECO_EXPECTED_COMPILE_COUNT",
        contract.expected_compile_count,
    ), mock.patch.object(
        gearcoleco,
        "GEARCOLECO_EXPECTED_ORDERED_LINK_ARGV",
        {architecture: link_argv},
    ), mock.patch.object(
        gearcoleco,
        "GEARCOLECO_LOG_CONTRACT",
        contract,
    ):
        yield


class GearcolecoModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = gearcoleco.GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
        return (
            build_log_text,
            gearcoleco.GEARCOLECO_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_native_git_describe_recipe_is_exact_and_normalized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["gearcoleco"]
        expected_git_version = {
            "derivation": "native-git-describe-v1",
            "value": "1.6.6-11-g1123457",
        }
        self.assertEqual(
            {
                "workflow": ".github/workflows/build-gearcoleco.yml",
                "source": {
                    "url": "https://github.com/drhelius/Gearcoleco.git",
                    "requested_ref": "refs/heads/main",
                    "commit": "112345747c04eb7752d1939258881aa10319e32e",
                    "tree": "0afbed445cf4689daa878816f961ea4bcb4832a3",
                },
                "build": {
                    "driver": "libretro-super",
                    "source_key": "gearcoleco",
                    "source_dir": "libretro-gearcoleco",
                    "output_path": "dist/unix/gearcoleco_libretro.so",
                    "artifact_name": "gearcoleco_libretro.so",
                    "git_version": expected_git_version,
                },
                "metadata": {
                    "source_path": (
                        "/libretro-super/dist/info/gearcoleco_libretro.info"
                    ),
                    "artifact_name": "gearcoleco_libretro.info",
                },
                "targets": ["arm64", "armhf"],
            },
            spec,
        )
        self.assertTrue(gearcoleco.gearcoleco_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_describe_spec_is_well_formed(
                spec, "gearcoleco"
            )
        )
        self.assertEqual(
            expected_git_version,
            pipeline.exact_native_git_describe_contract("gearcoleco"),
        )
        self.assertEqual(expected_git_version, pipeline.validated_git_version(spec))
        self.assertEqual({}, pipeline.validated_make_variables(spec))
        self.assertNotIn("compiler_scope", expected_git_version)
        self.assertEqual(
            [
                "CORE_PIPELINE_NATIVE_GIT_VERSION|"
                "1.6.6-11-g1123457|file"
            ],
            pipeline.git_version_log_markers(spec),
        )
        shell = pipeline.git_version_shell(spec)
        self.assertIn(
            "-C /libretro-super/libretro-gearcoleco/platforms/libretro "
            "-f Makefile -f /tmp/core-pipeline-native-git-version-origin.mk",
            shell,
        )
        self.assertIn("core_pipeline_native_git_version_origin", shell)
        self.assertNotIn("Makefile.libretro", shell)
        prelude = pipeline.sanitized_shell_prelude()
        self.assertIn("GIT_VERSION", prelude)
        self.assertIn("EMULATOR_BUILD", prelude)
        self.assertEqual(
            "platforms/libretro/Makefile",
            gearcoleco.GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY[
                "native_makefile"
            ],
        )
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                self.assertEqual(
                    {
                        "driver": "libretro-super",
                        "environment": "sanitized-v1",
                        "compile_definitions": [],
                        "git_version": expected_git_version,
                    },
                    pipeline.normalized_build_contract(spec, arch),
                )

    def test_catalog_mutations_and_contract_copy_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(catalog)
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "source-url",
                lambda changed: changed["cores"]["gearcoleco"]["source"].update(
                    {"url": "https://github.com/libretro/Gearcoleco.git"}
                ),
            ),
            mutation(
                "source-ref",
                lambda changed: changed["cores"]["gearcoleco"]["source"].update(
                    {"requested_ref": "refs/heads/master"}
                ),
            ),
            mutation(
                "source-commit",
                lambda changed: changed["cores"]["gearcoleco"]["source"].update(
                    {"commit": "a" * 40}
                ),
            ),
            mutation(
                "source-tree",
                lambda changed: changed["cores"]["gearcoleco"]["source"].update(
                    {"tree": "b" * 40}
                ),
            ),
            mutation(
                "workflow",
                lambda changed: changed["cores"]["gearcoleco"].update(
                    {"workflow": ".github/workflows/build-gearsystem.yml"}
                ),
            ),
            mutation(
                "source-directory",
                lambda changed: changed["cores"]["gearcoleco"]["build"].update(
                    {"source_dir": "libretro-gearcoleco-wrong"}
                ),
            ),
            mutation(
                "output-path",
                lambda changed: changed["cores"]["gearcoleco"]["build"].update(
                    {"output_path": "gearcoleco_libretro.so"}
                ),
            ),
            mutation(
                "missing-version",
                lambda changed: changed["cores"]["gearcoleco"]["build"].pop(
                    "git_version"
                ),
            ),
            mutation(
                "short-version-derivation",
                lambda changed: changed["cores"]["gearcoleco"]["build"][
                    "git_version"
                ].update(
                    {
                        "derivation": "native-space-short7-v1",
                        "value": " 1123457",
                    }
                ),
            ),
            mutation(
                "wrong-describe-value",
                lambda changed: changed["cores"]["gearcoleco"]["build"][
                    "git_version"
                ].update({"value": "1.6.6-10-g1123457"}),
            ),
            mutation(
                "forbidden-compiler-scope",
                lambda changed: changed["cores"]["gearcoleco"]["build"][
                    "git_version"
                ].update({"compiler_scope": "cxx"}),
            ),
            mutation(
                "forbidden-make-variables",
                lambda changed: changed["cores"]["gearcoleco"]["build"].update(
                    {"make_variables": {"IS_X86": 0}}
                ),
            ),
            mutation(
                "target-shape",
                lambda changed: changed["cores"]["gearcoleco"].update(
                    {"targets": ["arm64"]}
                ),
            ),
            mutation(
                "contract-copied-to-gearboy",
                lambda changed: changed["cores"]["gearboy"]["build"].update(
                    {
                        "git_version": copy.deepcopy(
                            changed["cores"]["gearcoleco"]["build"][
                                "git_version"
                            ]
                        )
                    }
                ),
            ),
            mutation(
                "whole-spec-copied-to-gearboy",
                lambda changed: changed["cores"].update(
                    {
                        "gearboy": copy.deepcopy(
                            changed["cores"]["gearcoleco"]
                        )
                    }
                ),
            ),
        )
        for label, changed in mutations:
            with self.subTest(label=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validate_catalog(changed)

    def test_native_git_describe_log_proof_binds_every_compile(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["gearcoleco"]
        contract = spec["build"]["git_version"]
        marker = pipeline.git_version_log_markers(spec)[0]
        version_token = r'-DEMULATOR_BUILD=\"1.6.6-11-g1123457\"'
        compilers = {
            "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
            "armhf": (
                "arm-a30-linux-gnueabihf-gcc",
                "arm-a30-linux-gnueabihf-g++",
            ),
        }

        def valid_log(arch: str) -> str:
            c_compiler, cxx_compiler = compilers[arch]
            compile_lines = [
                f"{c_compiler} {version_token} -c miniz.c -o miniz.o",
                *(
                    f"{cxx_compiler} {version_token} -c source-{index}.cpp "
                    f"-o source-{index}.o"
                    for index in range(19)
                ),
            ]
            self.assertEqual(20, len(compile_lines))
            return "\n".join([marker, *compile_lines]) + "\n"

        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        valid_log(arch),
                        contract,
                        spec["source"]["commit"],
                        arch,
                    )
                )

        baseline = valid_log("arm64")
        lines = baseline.splitlines()
        alternate_token = r'-DEMULATOR_BUILD=\"1.6.6-10-g1123457\"'
        legacy_macro = r'-DGIT_VERSION=\"1.6.6-11-g1123457\"'
        mutations = {
            "missing-marker": baseline.replace(marker + "\n", "", 1),
            "duplicate-marker": marker + "\n" + baseline,
            "late-marker": "\n".join([lines[1], marker, *lines[2:]]) + "\n",
            "wrong-origin": baseline.replace("|file", "|command line", 1),
            "alternate-version": baseline.replace(
                version_token, alternate_token, 1
            ),
            "unquoted-version": baseline.replace(
                version_token,
                "-DEMULATOR_BUILD=1.6.6-11-g1123457",
                1,
            ),
            "duplicate-token": baseline.replace(
                version_token, version_token + " " + version_token, 1
            ),
            "alternate-version-macro": baseline.replace(
                version_token, version_token + " " + legacy_macro, 1
            ),
            "undefined-version-macro": baseline.replace(
                version_token, version_token + " -UEMULATOR_BUILD", 1
            ),
            "missing-c-token": baseline.replace(" " + version_token, "", 1),
            "missing-cxx-token": baseline.replace(
                "aarch64-linux-gnu-g++ " + version_token,
                "aarch64-linux-gnu-g++",
                1,
            ),
            "response-file": baseline.replace(
                " -c miniz.c", " @compiler-options.rsp -c miniz.c", 1
            ),
        }
        for label, changed_log in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        changed_log,
                        contract,
                        spec["source"]["commit"],
                        "arm64",
                    )
                )

    def test_golden_source_and_build_contract_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["gearcoleco"]
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
            gearcoleco.gearcoleco_golden_source_is_well_formed(
                "gearcoleco", source
            )
        )
        self.assertTrue(
            gearcoleco.gearcoleco_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                "gearcoleco",
                source,
            )
        )
        self.assertTrue(
            pipeline.native_git_describe_golden_source_is_well_formed(
                "gearcoleco", source
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                "gearcoleco",
                source,
            )
        )

        source_mutations = {
            "wrong-url": {**source, "url": "https://example.com/Gearcoleco.git"},
            "wrong-ref": {**source, "requested_ref": "refs/heads/master"},
            "wrong-commit": {**source, "commit": "a" * 40},
            "wrong-tree": {**source, "tree": "b" * 40},
            "wrong-resolved-commit": {**source, "resolved_commit": "c" * 40},
            "wrong-resolved-url": {
                **source,
                "resolved_url": "https://example.com/Gearcoleco.git",
            },
            "submodule": {
                **source,
                "submodules": [{"path": "deps/foreign", "commit": "d" * 40}],
            },
            "extra-key": {**source, "unexpected": True},
        }
        for label, changed_source in source_mutations.items():
            with self.subTest(source=label):
                self.assertFalse(
                    gearcoleco.gearcoleco_golden_source_is_well_formed(
                        "gearcoleco", changed_source
                    )
                )
                self.assertFalse(
                    gearcoleco.gearcoleco_golden_build_contract_is_well_formed(
                        build,
                        spec["source"]["commit"],
                        "gearcoleco",
                        changed_source,
                    )
                )
                self.assertFalse(
                    pipeline.native_git_describe_golden_source_is_well_formed(
                        "gearcoleco", changed_source
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        build,
                        spec["source"]["commit"],
                        "gearcoleco",
                        changed_source,
                    )
                )

        build_mutations = {
            "wrong-derivation": {
                **build,
                "git_version": {
                    "derivation": "native-space-short7-v1",
                    "value": " 1123457",
                },
            },
            "wrong-value": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "value": "1.6.6-10-g1123457",
                },
            },
            "compiler-scope": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "compiler_scope": "cxx",
                },
            },
            "make-variables": {**build, "make_variables": {"IS_X86": 0}},
            "extra-key": {**build, "unexpected": True},
        }
        for label, changed_build in build_mutations.items():
            with self.subTest(build=label):
                self.assertFalse(
                    gearcoleco.gearcoleco_golden_build_contract_is_well_formed(
                        changed_build,
                        spec["source"]["commit"],
                        "gearcoleco",
                        source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        changed_build,
                        spec["source"]["commit"],
                        "gearcoleco",
                        source,
                    )
                )
        self.assertFalse(
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                "gearboy",
                source,
            )
        )

    def test_workflow_is_exact_publication_disabled_template(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "build-gearcoleco.yml"
        ).read_text(encoding="utf-8")
        template = (
            ROOT / ".github" / "workflows" / "build-pokemini.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            template.replace("pokemini", "gearcoleco"),
            workflow,
        )
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn(
            "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5",
            workflow,
        )
        self.assertEqual(1, workflow.count("--core gearcoleco"))
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("gh release create", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn('|| echo "::warning::', workflow)
        download64 = workflow.index(
            'gh release download toolchains --pattern "cores-arm64.tar.gz"'
        )
        downloadhf = workflow.index(
            'gh release download toolchains --pattern "cores-armhf.tar.gz"'
        )
        verify = workflow.index("scripts/toolchain_archive.py verify-downloads")
        load64 = workflow.index("gunzip -c cores-arm64.tar.gz | docker load")
        loadhf = workflow.index("gunzip -c cores-armhf.tar.gz | docker load")
        e2e = workflow.index("scripts/core_pipeline.py e2e")
        self.assertLess(download64, downloadhf)
        self.assertLess(downloadhf, verify)
        self.assertLess(verify, load64)
        self.assertLess(load64, loadhf)
        self.assertLess(loadhf, e2e)

    def test_schema_branches_are_exact_and_disjoint(self) -> None:
        catalog_schema = json.loads(
            (ROOT / "manifests" / "core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )
        golden_schema = json.loads(
            (ROOT / "manifests" / "golden-start.schema.json").read_text(
                encoding="utf-8"
            )
        )
        expected_version = {
            "type": "object",
            "required": ["derivation", "value"],
            "properties": {
                "derivation": {"const": "native-git-describe-v1"},
                "value": {"const": "1.6.6-11-g1123457"},
            },
            "additionalProperties": False,
        }
        version_defs = (
            "gitVersion",
            "nativeGitVersion",
            "fbneoNativeVersion",
            "mame2003PlusNativeGitVersion",
            "mgbaNativeGitVersion",
            "nativeGitDescribeVersion",
            "gearboyNativeGitDescribeVersion",
            "gearsystemNativeGitDescribeVersion",
            "viceNativeGitVersion",
        )
        catalog_ref_defs = (
            "gitVersion",
            "nativeGitVersion",
            "fbneoNativeVersion",
            "mame2003PlusNativeGitVersion",
            "mgbaNativeGitVersion",
            "nativeGitDescribeVersion",
            "viceNativeGitVersion",
        )
        catalog_expected_refs = [
            f"#/$defs/{name}" for name in catalog_ref_defs
        ]
        golden_expected_refs = [f"#/$defs/{name}" for name in version_defs]
        for schema, def_names in (
            (catalog_schema, catalog_ref_defs),
            (golden_schema, version_defs),
        ):
            with self.subTest(schema=schema["$id"]):
                self.assertEqual(
                    expected_version,
                    schema["$defs"]["nativeGitDescribeVersion"],
                )
                identities = [
                    (
                        schema["$defs"][name]["properties"]["derivation"][
                            "const"
                        ],
                        json.dumps(
                            schema["$defs"][name]["properties"].get("value"),
                            sort_keys=True,
                        ),
                    )
                    for name in def_names
                ]
                self.assertEqual(len(identities), len(set(identities)))

        self.assertNotIn(
            "gearcoleco",
            catalog_schema["properties"]["cores"].get("properties", {}),
        )
        catalog_git_refs = [
            branch["$ref"]
            for branch in catalog_schema["$defs"]["core"]["properties"]["build"][
                "properties"
            ]["git_version"]["oneOf"]
        ]
        self.assertEqual(catalog_expected_refs, catalog_git_refs)

        exact_build = golden_schema["$defs"]["buildGolden"]["dependentSchemas"][
            "build"
        ]
        exact_core_ids = [
            branch["properties"]["core_id"]["const"]
            for branch in exact_build["then"]["oneOf"]
        ]
        self.assertEqual(len(exact_core_ids), len(set(exact_core_ids)))
        self.assertEqual(1, exact_core_ids.count("gearcoleco"))
        gearcoleco_branch = next(
            branch
            for branch in exact_build["then"]["oneOf"]
            if branch["properties"]["core_id"]["const"] == "gearcoleco"
        )
        self.assertEqual(
            {"$ref": "#/$defs/nativeGitDescribeVersion"},
            gearcoleco_branch["properties"]["build"]["properties"][
                "git_version"
            ],
        )
        self.assertEqual(
            {
                "url",
                "requested_ref",
                "commit",
                "tree",
                "resolved_commit",
                "resolved_url",
                "submodules",
            },
            set(
                gearcoleco_branch["properties"]["source"]["propertyNames"][
                    "enum"
                ]
            ),
        )
        golden_git_refs = [
            branch["$ref"]
            for branch in golden_schema["$defs"]["buildContract"]["properties"][
                "git_version"
            ]["oneOf"]
        ]
        self.assertEqual(golden_expected_refs, golden_git_refs)

    def test_production_contract_constants_match_reviewed_oracle(self) -> None:
        contract = ORACLE_FIXTURE["production_log_contract"]
        self.assertEqual(
            contract["compile_count"],
            gearcoleco.GEARCOLECO_EXPECTED_COMPILE_COUNT,
        )
        self.assertEqual(
            contract["language_counts"],
            gearcoleco.GEARCOLECO_EXPECTED_LANGUAGE_COUNTS,
        )
        self.assertEqual(
            contract["compile_pair_sha256"],
            gearcoleco.GEARCOLECO_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            contract["compile_invocation_sha256"],
            gearcoleco.GEARCOLECO_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            contract["link_object_sha256"],
            gearcoleco.GEARCOLECO_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            contract["raw_link_object_sha256"],
            gearcoleco.GEARCOLECO_EXPECTED_RAW_LINK_OBJECT_SHA256,
        )
        for architecture, block in (
            gearcoleco.GEARCOLECO_EXPECTED_DIAGNOSTIC_BLOCKS.items()
        ):
            self.assertEqual(
                contract["diagnostic_block_sha256"][architecture],
                hashlib.sha256((block + "\n").encode("utf-8")).hexdigest(),
            )

    def test_synthetic_interleaved_logs_prove_both_architecture_contracts(
        self,
    ) -> None:
        for architecture in ("arm64", "armhf"):
            contract, link_argv, log = build_gearcoleco_log_fixture(
                architecture
            )
            lines = log.splitlines()
            diagnostic_lines = (
                gearcoleco.GEARCOLECO_EXPECTED_DIAGNOSTIC_BLOCKS[
                    architecture
                ].splitlines()
            )
            diagnostic_position = lines.index(diagnostic_lines[0])
            diagnostic_end = diagnostic_position + len(diagnostic_lines)
            processor_position = next(
                index
                for index, line in enumerate(lines)
                if gearcoleco.GEARCOLECO_PROCESSOR_SOURCE in line
            )
            compile_positions = [
                index
                for index, line in enumerate(lines)
                if " -c " in line
            ]
            self.assertEqual(
                diagnostic_lines,
                lines[diagnostic_position:diagnostic_end],
            )
            self.assertLess(processor_position, diagnostic_position)
            self.assertTrue(
                any(position >= diagnostic_end for position in compile_positions)
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                architecture, contract, link_argv
            ):
                self.assertTrue(
                    gearcoleco.gearcoleco_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_registry_identity_is_owned_by_gearcoleco(self) -> None:
        contract = core_log_contract_for(gearcoleco.GEARCOLECO_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(
            "gearcoleco-mixed-language-v1", contract.contract_id
        )
        self.assertEqual(
            "gearcoleco_log_proves_contract", contract.proof_name
        )
        self.assertEqual(
            frozenset({gearcoleco.GEARCOLECO_CORE_ID}), contract.core_ids
        )

    def test_synthetic_log_rejects_contract_mutations(self) -> None:
        contract, link_argv, log = build_gearcoleco_log_fixture("arm64")
        arguments = self.contract_arguments(log)[1:]
        head = gearcoleco.GEARCOLECO_SOURCE_HEAD_MARKER
        marker = gearcoleco.GEARCOLECO_NATIVE_VERSION_MARKER
        token = gearcoleco.GEARCOLECO_NATIVE_GIT_DESCRIBE_LOG_TOKEN
        diagnostic = gearcoleco.GEARCOLECO_ARM64_DIAGNOSTIC_BLOCK + "\n"
        compile_line = next(line for line in log.splitlines() if " -c " in line)
        processor_compile_line = next(
            line
            for line in log.splitlines()
            if gearcoleco.GEARCOLECO_PROCESSOR_SOURCE in line
        )
        later_compile_line = next(
            line
            for line in reversed(log.splitlines())
            if " -c " in line
            and gearcoleco.GEARCOLECO_PROCESSOR_SOURCE not in line
        )
        link_line = " ".join(link_argv)
        diagnostic_before_processor = log.replace(diagnostic, "", 1).replace(
            processor_compile_line + "\n",
            diagnostic + processor_compile_line + "\n",
            1,
        )
        diagnostic_after_link = log.replace(diagnostic, "", 1).replace(
            link_line + "\n",
            link_line + "\n" + diagnostic,
            1,
        )
        compile_after_link = log.replace(
            later_compile_line + "\n", "", 1
        ).replace(
            link_line + "\n",
            link_line + "\n" + later_compile_line + "\n",
            1,
        )
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "missing-marker": log.replace(marker + "\n", "", 1),
            "wrong-origin": log.replace("|file", "|command line", 1),
            "late-marker": log.replace(marker + "\n", "", 1) + marker + "\n",
            "wrong-version": log.replace(
                token, r'-DEMULATOR_BUILD=\"1.6.6-10-g1123457\"', 1
            ),
            "legacy-macro": log.replace(
                token, token + r' -DGIT_VERSION=\"1.6.6-11-g1123457\"', 1
            ),
            "missing-compile": log.replace(compile_line + "\n", "", 1),
            "missing-processor-compile": log.replace(
                processor_compile_line + "\n", "", 1
            ),
            "duplicate-processor-compile": log.replace(
                processor_compile_line + "\n",
                processor_compile_line + "\n" + processor_compile_line + "\n",
                1,
            ),
            "compile-option": log.replace(
                compile_line, compile_line.replace("-O3", "-O2", 1), 1
            ),
            "response-file": log.replace(
                compile_line, compile_line.replace(" -O3", " @args.rsp -O3", 1), 1
            ),
            "link-option": log.replace(
                link_line,
                link_line.replace("-Wl,-version-script=./link.T", "-Wl,--as-needed"),
                1,
            ),
            "link-order": log.replace(
                link_line,
                link_line.replace(
                    f"{link_argv[6]} {link_argv[7]}",
                    f"{link_argv[7]} {link_argv[6]}",
                ),
                1,
            ),
            "missing-diagnostic": log.replace(diagnostic, "", 1),
            "changed-context": log.replace(
                "from ../../src/Processor.cpp:27:",
                "from ../../src/Processor.cpp:28:",
                1,
            ),
            "extra-warning": log + "warning: synthetic warning\n",
            "extra-note": log + "note: synthetic note\n",
            "error": log + "error: synthetic error\n",
            "make-failure": log + "make: *** [all] Error 2\n",
            "diagnostic-before-processor": diagnostic_before_processor,
            "diagnostic-after-link": diagnostic_after_link,
            "compile-after-link": compile_after_link,
            "diagnostic-after-build-complete": (
                log.replace(diagnostic, "", 1) + diagnostic
            ),
            "missing-build-complete": log.replace(
                gearcoleco.GEARCOLECO_BUILD_COMPLETE_MARKER + "\n", "", 1
            ),
        }
        with synthetic_contract("arm64", contract, link_argv):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        gearcoleco.gearcoleco_log_proves_contract(
                            changed, *arguments
                        )
                    )
            self.assertFalse(
                gearcoleco.gearcoleco_log_proves_contract(
                    log,
                    "gearboy",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                gearcoleco.gearcoleco_log_proves_contract(
                    log,
                    gearcoleco.GEARCOLECO_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                )
            )
            self.assertFalse(
                gearcoleco.gearcoleco_log_proves_contract(
                    log,
                    gearcoleco.GEARCOLECO_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                )
            )

if __name__ == "__main__":
    unittest.main()
