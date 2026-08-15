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
from core_pipeline_lib.contracts import bluemsx, mixed_language
from core_pipeline_lib.contracts.command_line import (
    ordered_command_argv_sha256,
)
from core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT / "tests/fixtures/per-core-oracles/bluemsx.json"
)
POSITIVE_ORACLES = tuple(ORACLE_FIXTURE["positive_runs"])


def oracle_log_path(run_id: str, architecture: str) -> Path:
    return (
        ROOT
        / ".local-e2e"
        / "runs"
        / run_id
        / bluemsx.BLUEMSX_CORE_ID
        / architecture
        / "build.log"
    )


def build_bluemsx_log_fixture(
    architecture: str,
) -> tuple[
    mixed_language.MixedLanguageLogContract,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
]:
    """Build every C/C++ compile and the complete ordered link proof."""

    c_compiler, cxx_compiler = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }[architecture]
    c_compile_lines = tuple(
        f"{c_compiler} -c -osynthetic/c/unit_{index:03d}.o "
        f"synthetic/c/unit_{index:03d}.c "
        f"{bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN} "
        "-std=gnu89 -O2 -fPIC -w"
        for index in range(
            bluemsx.BLUEMSX_EXPECTED_LANGUAGE_COUNTS["c"]
        )
    )
    cxx_compile_lines = tuple(
        f"{cxx_compiler} -c -osynthetic/cxx/unit_{index:03d}.o "
        f"synthetic/cxx/unit_{index:03d}.cpp "
        "-std=gnu++98 -O2 -fPIC -w"
        for index in range(
            bluemsx.BLUEMSX_EXPECTED_LANGUAGE_COUNTS["cxx"]
        )
    )
    compile_lines = c_compile_lines + cxx_compile_lines
    parsed_invocations = tuple(
        mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            {c_compiler, cxx_compiler},
            {cxx_compiler},
        )
        for line in compile_lines
    )
    if any(invocation is None for invocation in parsed_invocations):
        raise AssertionError("failed to construct blueMSX compile fixture")
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
        cxx_compiler,
        "-o",
        bluemsx.BLUEMSX_BUILD_ARTIFACT_NAME,
        *bluemsx.BLUEMSX_EXPECTED_LINK_OPTIONS,
        *(f"./{path}" for path in objects),
    )
    ordered_link_digest = ordered_command_argv_sha256(link_argv)
    if ordered_link_digest is None:
        raise AssertionError("failed to hash blueMSX link fixture")
    contract = replace(
        bluemsx.BLUEMSX_LOG_CONTRACT,
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
        expected_ordered_link_argv_sha256={
            architecture: ordered_link_digest
        },
    )
    log = (
        "\n".join(
            (
                bluemsx.BLUEMSX_SOURCE_HEAD_MARKER,
                bluemsx.BLUEMSX_NATIVE_VERSION_MARKER,
                *compile_lines,
                " ".join(link_argv),
            )
        )
        + "\n"
    )
    return contract, c_compile_lines, cxx_compile_lines, link_argv, log


@contextmanager
def synthetic_contract(
    contract: mixed_language.MixedLanguageLogContract,
):
    with mock.patch.object(bluemsx, "BLUEMSX_LOG_CONTRACT", contract):
        yield


class BluemsxModuleTests(unittest.TestCase):
    def contract_arguments(
        self,
        build_log_text: str,
        architecture: str = "arm64",
    ) -> tuple[str, str, str, str, str]:
        identity = bluemsx.BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        return (
            build_log_text,
            bluemsx.BLUEMSX_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_exact_catalog_and_promoted_contracts_are_core_owned(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][bluemsx.BLUEMSX_CORE_ID]
        identity = bluemsx.BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        expected_version = {
            "derivation": bluemsx.BLUEMSX_NATIVE_GIT_VERSION_DERIVATION,
            "value": bluemsx.BLUEMSX_NATIVE_GIT_VERSION,
            "compiler_scope": "c",
        }

        self.assertTrue(bluemsx.bluemsx_spec_is_well_formed(spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(
                spec, bluemsx.BLUEMSX_CORE_ID
            )
        )
        self.assertEqual(expected_version, spec["build"]["git_version"])
        self.assertEqual(expected_version, pipeline.validated_git_version(spec))
        self.assertEqual({}, pipeline.validated_make_variables(spec))
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
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
            bluemsx.bluemsx_golden_source_is_well_formed(
                bluemsx.BLUEMSX_CORE_ID, source
            )
        )
        self.assertTrue(
            pipeline.native_git_version_golden_source_is_well_formed(
                bluemsx.BLUEMSX_CORE_ID, source
            )
        )
        self.assertTrue(
            bluemsx.bluemsx_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                bluemsx.BLUEMSX_CORE_ID,
                source,
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                bluemsx.BLUEMSX_CORE_ID,
                source,
            )
        )

        for label, changed_source in {
            "tree": {**source, "tree": "0" * 40},
            "resolved-commit": {
                **source,
                "resolved_commit": "0" * 40,
            },
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/bluemsx.git",
            },
            "submodule": {
                **source,
                "submodules": [
                    {"path": "foreign", "commit": "0" * 40}
                ],
            },
            "extra": {**source, "unexpected": True},
        }.items():
            with self.subTest(source=label):
                self.assertFalse(
                    bluemsx.bluemsx_golden_source_is_well_formed(
                        bluemsx.BLUEMSX_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    pipeline.native_git_version_golden_source_is_well_formed(
                        bluemsx.BLUEMSX_CORE_ID, changed_source
                    )
                )
                self.assertFalse(
                    bluemsx.bluemsx_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        bluemsx.BLUEMSX_CORE_ID,
                        changed_source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        build,
                        identity["source_commit"],
                        bluemsx.BLUEMSX_CORE_ID,
                        changed_source,
                    )
                )

        for label, changed_build in {
            "version": {
                **build,
                "git_version": {**expected_version, "value": " 0000000"},
            },
            "missing-scope": {
                **build,
                "git_version": {
                    "derivation": expected_version["derivation"],
                    "value": expected_version["value"],
                },
            },
            "cxx-scope": {
                **build,
                "git_version": {
                    **expected_version,
                    "compiler_scope": "cxx",
                },
            },
            "all-scope": {
                **build,
                "git_version": {
                    **expected_version,
                    "compiler_scope": "all",
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
                    bluemsx.bluemsx_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        bluemsx.BLUEMSX_CORE_ID,
                        source,
                    )
                )
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        bluemsx.BLUEMSX_CORE_ID,
                        source,
                    )
                )

    def test_catalog_predicate_rejects_every_owned_boundary(self) -> None:
        catalog = pipeline.load_json(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][bluemsx.BLUEMSX_CORE_ID]

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
                    {"url": "https://example.com/bluemsx.git"}
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
                lambda changed: changed["source"].update(
                    {"tree": "0" * 40}
                ),
            ),
            mutation(
                "version",
                lambda changed: changed["build"]["git_version"].update(
                    {"value": " 0000000"}
                ),
            ),
            mutation(
                "missing-scope",
                lambda changed: changed["build"]["git_version"].pop(
                    "compiler_scope"
                ),
            ),
            mutation(
                "cxx-scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "cxx"}
                ),
            ),
            mutation(
                "all-scope",
                lambda changed: changed["build"]["git_version"].update(
                    {"compiler_scope": "all"}
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
                self.assertFalse(
                    bluemsx.bluemsx_spec_is_well_formed(changed)
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
        self.assertNotIn(
            "bluemsx",
            catalog_schema["properties"]["cores"].get(
                "properties", {}
            ),
        )
        self.assertEqual(
            {
                "allOf": [
                    {"$ref": "#/$defs/nativeGitVersion"},
                    {
                        "required": ["compiler_scope"],
                        "propertyNames": {
                            "enum": [
                                "derivation",
                                "value",
                                "compiler_scope",
                            ]
                        },
                        "properties": {
                            "value": {
                                "const": bluemsx.BLUEMSX_NATIVE_GIT_VERSION
                            },
                            "compiler_scope": {"const": "c"},
                        },
                    },
                ]
            },
            golden_schema["$defs"]["bluemsxNativeGitVersion"],
        )
        exact_build = golden_schema["$defs"]["buildGolden"][
            "dependentSchemas"
        ]["build"]
        branches = {
            branch["properties"]["core_id"]["const"]: branch
            for branch in exact_build["then"]["oneOf"]
        }
        branch = branches[bluemsx.BLUEMSX_CORE_ID]["properties"]
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
            {"$ref": "#/$defs/bluemsxNativeGitVersion"},
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
        self.assertEqual(269, bluemsx.BLUEMSX_EXPECTED_COMPILE_COUNT)
        self.assertEqual(
            {"c": 255, "cxx": 14},
            bluemsx.BLUEMSX_EXPECTED_LANGUAGE_COUNTS,
        )
        self.assertEqual(
            "cd7ff9673f83630e220fda7186b2887fe5cfb208019388223a503d4da0f385ec",
            bluemsx.BLUEMSX_EXPECTED_COMPILE_PAIR_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "b164112377465c8b7d41d82f5a2385c19ce1f0021b3f8d1b48dc64ed025f96a1"
                ),
                "armhf": (
                    "82e9389a71aba5a01ef6229a80771ac70891b16dd8e1ec1fa59390049f840dca"
                ),
            },
            bluemsx.BLUEMSX_EXPECTED_COMPILE_INVOCATION_SHA256,
        )
        self.assertEqual(
            "4f7e5b8f24429107aa86d06e304bce477137c2cbe1468bae5b613c4067f550b4",
            bluemsx.BLUEMSX_EXPECTED_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            "7f65220d6c91961e84d4801548bd0da14349843fe176d69d7149752cc64a3d86",
            bluemsx.BLUEMSX_EXPECTED_RAW_LINK_OBJECT_SHA256,
        )
        self.assertEqual(
            {
                "arm64": (
                    "8b495607ac268e960f0dc4822d07388636f8137e379dd15371ccada08776b17d"
                ),
                "armhf": (
                    "9b638c84c69d48f61577f6cdcccb22acf618e1ab353ec203f4330c19d3df6483"
                ),
            },
            bluemsx.BLUEMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256,
        )
        self.assertEqual(
            "cxx", bluemsx.BLUEMSX_LOG_CONTRACT.expected_link_language
        )
        self.assertEqual(
            bluemsx.BLUEMSX_EXPECTED_ORDERED_LINK_ARGV_SHA256,
            bluemsx.BLUEMSX_LOG_CONTRACT.expected_ordered_link_argv_sha256,
        )

    def test_synthetic_logs_prove_both_architecture_contracts(self) -> None:
        for architecture in ("arm64", "armhf"):
            contract, _c, _cxx, _link, log = build_bluemsx_log_fixture(
                architecture
            )
            with self.subTest(architecture=architecture), synthetic_contract(
                contract
            ):
                self.assertTrue(
                    bluemsx.bluemsx_log_proves_contract(
                        *self.contract_arguments(log, architecture)
                    )
                )

    def test_synthetic_log_rejects_marker_and_identity_mutations(self) -> None:
        contract, _c, _cxx, _link, log = build_bluemsx_log_fixture(
            "arm64"
        )
        arguments = self.contract_arguments(log)[1:]
        head = bluemsx.BLUEMSX_SOURCE_HEAD_MARKER
        marker = bluemsx.BLUEMSX_NATIVE_VERSION_MARKER
        mutations = {
            "missing-head": log.replace(head + "\n", "", 1),
            "duplicate-head": head + "\n" + log,
            "missing-marker": log.replace(marker + "\n", "", 1),
            "late-marker": log.replace(marker + "\n", "", 1)
            + marker
            + "\n",
            "wrong-origin": log.replace("|file", "|command line", 1),
            "wrong-value": log.replace(
                marker, marker.replace(" 5f595c7", " 0000000"), 1
            ),
            "injected-version": (
                log
                + "CORE_PIPELINE_GIT_VERSION|-5f595c7|command line\n"
            ),
        }
        with synthetic_contract(contract):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        bluemsx.bluemsx_log_proves_contract(
                            changed, *arguments
                        )
                    )
            for label, changed_arguments in {
                "core": (
                    "fmsx",
                    "arm64",
                    contract.source_commit,
                    contract.source_tree,
                ),
                "commit": (
                    bluemsx.BLUEMSX_CORE_ID,
                    "arm64",
                    "0" * 40,
                    contract.source_tree,
                ),
                "tree": (
                    bluemsx.BLUEMSX_CORE_ID,
                    "arm64",
                    contract.source_commit,
                    "0" * 40,
                ),
                "architecture": (
                    bluemsx.BLUEMSX_CORE_ID,
                    "unknown",
                    contract.source_commit,
                    contract.source_tree,
                ),
            }.items():
                with self.subTest(identity=label):
                    self.assertFalse(
                        bluemsx.bluemsx_log_proves_contract(
                            log, *changed_arguments
                        )
                    )

    def test_synthetic_log_rejects_compile_link_and_suppression_mutations(
        self,
    ) -> None:
        contract, c_lines, cxx_lines, link_argv, log = (
            build_bluemsx_log_fixture("arm64")
        )
        arguments = self.contract_arguments(log)[1:]
        c_line = c_lines[0]
        cxx_line = cxx_lines[0]
        token = bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN
        link_line = " ".join(link_argv)
        first_objects = (
            "./synthetic/c/unit_000.o ./synthetic/c/unit_001.o"
        )
        token_moved_to_cxx = log.replace(f" {token}", "", 1).replace(
            " -std=gnu++98", f" {token} -std=gnu++98", 1
        )
        mutations = {
            "missing-compile": log.replace(c_line + "\n", "", 1),
            "duplicate-compile": log.replace(
                c_line, c_line + "\n" + c_line, 1
            ),
            "compile-option": log.replace(
                c_line, c_line.replace("-O2", "-O3", 1), 1
            ),
            "missing-c-version": log.replace(f" {token}", "", 1),
            "token-on-cxx": token_moved_to_cxx,
            "duplicate-c-token": log.replace(
                token, token + " " + token, 1
            ),
            "missing-suppression": log.replace(
                c_line, c_line.removesuffix(" -w"), 1
            ),
            "duplicate-suppression": log.replace(
                c_line, c_line + " -w", 1
            ),
            "response-file": log.replace(
                c_line,
                c_line.replace(" -std=gnu89", " @args.rsp -std=gnu89", 1),
                1,
            ),
            "c-compiler-on-cxx": log.replace(
                cxx_line,
                cxx_line.replace(
                    "aarch64-linux-gnu-g++",
                    "aarch64-linux-gnu-gcc",
                    1,
                ),
                1,
            ),
            "missing-link-object": log.replace(
                link_line,
                link_line.replace(" ./synthetic/c/unit_000.o", "", 1),
                1,
            ),
            "link-object-order": log.replace(
                link_line,
                link_line.replace(
                    first_objects,
                    "./synthetic/c/unit_001.o ./synthetic/c/unit_000.o",
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
            "c-link": log.replace(
                link_line,
                link_line.replace(
                    "aarch64-linux-gnu-g++",
                    "aarch64-linux-gnu-gcc",
                    1,
                ),
                1,
            ),
        }
        with synthetic_contract(contract):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        bluemsx.bluemsx_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_synthetic_log_rejects_every_emitted_diagnostic(self) -> None:
        contract, _c, _cxx, _link, log = build_bluemsx_log_fixture(
            "arm64"
        )
        arguments = self.contract_arguments(log)[1:]
        mutations = {
            "warning": log + "warning: synthetic warning\n",
            "note": log + "note: synthetic note\n",
            "error": log + "error: synthetic error\n",
            "fatal": log + "fatal: synthetic failure\n",
            "make": log + "make: *** [all] Error 2\n",
            "linker": log + "undefined reference to synthetic_symbol\n",
        }
        with synthetic_contract(contract):
            for label, changed in mutations.items():
                with self.subTest(mutation=label):
                    self.assertFalse(
                        bluemsx.bluemsx_log_proves_contract(
                            changed, *arguments
                        )
                    )

    def test_shared_native_version_validator_binds_c_scope_only(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][bluemsx.BLUEMSX_CORE_ID]
        version = spec["build"]["git_version"]
        source_commit = spec["source"]["commit"]
        for architecture in ("arm64", "armhf"):
            _exact, c_lines, cxx_lines, _link, log = (
                build_bluemsx_log_fixture(architecture)
            )
            c_line = c_lines[0]
            cxx_line = cxx_lines[0]
            token = bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN
            moved = log.replace(f" {token}", "", 1).replace(
                cxx_line,
                cxx_line.replace(" -std=gnu++98", f" {token} -std=gnu++98"),
                1,
            )
            without_c_compiles = log
            for line in c_lines:
                without_c_compiles = without_c_compiles.replace(
                    line + "\n", "", 1
                )
            mutations = {
                "missing-c-token": log.replace(f" {token}", "", 1),
                "token-on-cxx": moved,
                "duplicate-c-token": log.replace(
                    token, token + " " + token, 1
                ),
                "response-file": log.replace(
                    c_line,
                    c_line.replace(
                        " -std=gnu89",
                        " @compiler-options.rsp -std=gnu89",
                        1,
                    ),
                    1,
                ),
                "alternate-define": log.replace(
                    c_line, c_line + " -DGIT_VERSION=wrong", 1
                ),
                "undefine": log.replace(
                    c_line, c_line + " -UGIT_VERSION", 1
                ),
                "no-c-compile": without_c_compiles,
            }
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log, version, source_commit, architecture
                    )
                )
                for label, changed in mutations.items():
                    with self.subTest(mutation=label):
                        self.assertFalse(
                            pipeline.git_version_log_proves_contract(
                                changed,
                                version,
                                source_commit,
                                architecture,
                            )
                        )

class BluemsxCompositionIntegrationTests(unittest.TestCase):
    def test_shared_generation_surfaces_preserve_native_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        core_id = bluemsx.BLUEMSX_CORE_ID
        spec = catalog["cores"][core_id]
        expected_version = {
            "derivation": bluemsx.BLUEMSX_NATIVE_GIT_VERSION_DERIVATION,
            "value": bluemsx.BLUEMSX_NATIVE_GIT_VERSION,
            "compiler_scope": "c",
        }
        expected_normalized = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": expected_version,
        }
        version_probe = (
            "make --no-print-directory -s "
            "-C /libretro-super/libretro-bluemsx "
            "-f Makefile.libretro -f "
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
            [bluemsx.BLUEMSX_NATIVE_VERSION_MARKER],
            pipeline.git_version_log_markers(spec),
        )
        version_shell = pipeline.git_version_shell(spec)
        self.assertIn(version_probe, version_shell)
        self.assertNotIn("-f Makefile -f /tmp/core-pipeline", version_shell)
        self.assertEqual("", pipeline.make_variable_shell(spec))
        self.assertEqual([], pipeline.make_variable_log_markers(spec))

        build_shell = pipeline.libretro_build_shell(spec, core_id)
        self.assertEqual("./libretro-build.sh bluemsx", build_shell)
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
        identity = bluemsx.BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertIs(
            identity, pipeline.BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        contract = core_log_contract_for(bluemsx.BLUEMSX_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("bluemsx-mixed-language-v1", contract.contract_id)
        self.assertEqual("bluemsx_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({bluemsx.BLUEMSX_CORE_ID}), contract.core_ids
        )

    def test_catalog_guard_and_dispatch_use_individual_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        changed = copy.deepcopy(catalog)
        changed["cores"][bluemsx.BLUEMSX_CORE_ID]["build"]["git_version"].pop(
            "compiler_scope"
        )
        self.assertFalse(
            bluemsx.bluemsx_spec_is_well_formed(
                changed["cores"][bluemsx.BLUEMSX_CORE_ID]
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)

        contract, _c, _cxx, _link, log = build_bluemsx_log_fixture(
            "arm64"
        )
        identity = bluemsx.BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY
        with synthetic_contract(contract):
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    log,
                    bluemsx.BLUEMSX_CORE_ID,
                    "arm64",
                    identity["source_commit"],
                    identity["source_tree"],
                )
            )


if __name__ == "__main__":
    unittest.main()
