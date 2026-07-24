from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import unittest

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import snes9x2005_plus
from scripts.core_pipeline_lib.contracts.registry import core_log_contract_for
from scripts.core_pipeline_lib.errors import PipelineError


ROOT = Path(__file__).resolve().parents[1]
COMPILERS = {
    "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
    "armhf": (
        "arm-a30-linux-gnueabihf-gcc",
        "arm-a30-linux-gnueabihf-g++",
    ),
}
EXPECTED_SOURCE = {
    "url": "https://github.com/libretro/snes9x2005.git",
    "requested_ref": "refs/heads/master",
    "commit": "b60356971fc9caae02cd0853676dced886a08be7",
    "tree": "5a13440308796f67a77f7e8fc16bbeee61ab301d",
}
EXPECTED_GIT_VERSION = {
    "derivation": "native-space-short7-v1",
    "value": " b603569",
    "compiler_scope": "c",
}
EXPECTED_SOURCE_KEYS = {
    "url",
    "requested_ref",
    "commit",
    "tree",
    "resolved_commit",
    "resolved_url",
    "submodules",
}
EXPECTED_BUILD_KEYS = {
    "driver",
    "environment",
    "compile_definitions",
    "git_version",
    "log",
    "log_sha256",
    "make_variables",
}
EXPECTED_MAKE_VARIABLE_SCHEMA = {
    "type": "object",
    "required": ["USE_BLARGG_APU"],
    "properties": {"USE_BLARGG_APU": {"const": 1}},
    "additionalProperties": False,
}
ORACLE_DIRECTORY = (
    ROOT
    / "tests"
    / "fixtures"
    / "per-core-oracles"
    / "snes9x2005_plus"
)
ORACLE_LOGS = {
    arch: ORACLE_DIRECTORY / f"{arch}-build.txt"
    for arch in ("arm64", "armhf")
}
ORACLE_LOG_IDENTITIES = {
    "arm64": (
        "7d96670dc3d50d2953874695f616fa9e28f92e746079a79a66e71b06c4fe37e9",
        25_326,
    ),
    "armhf": (
        "a526846c10ccc1dd916e21f13976bb4a03218e593ec42fb2979ab4cf5d32d7d3",
        24_971,
    ),
}


def lines_sha256(lines: list[str], *, unordered: bool = False) -> str:
    """Independently reproduce the contract's newline-framed fingerprints."""

    material = sorted(lines) if unordered else lines
    return hashlib.sha256(
        "".join(f"{line}\n" for line in material).encode("utf-8")
    ).hexdigest()


def valid_snes9x2005_plus_log(spec: dict, arch: str) -> str:
    marker = pipeline.git_version_log_markers(spec)[0]
    token = '-DGIT_VERSION=\\\"" b603569"\\\"'
    c_compiler, _cxx_compiler = COMPILERS[arch]
    prefix = "\n".join(
        [*pipeline.make_variable_log_markers(spec), marker]
    )
    return (
        f"{prefix}\n"
        f"{c_compiler} {token} -DUSE_BLARGG_APU "
        "-c first.c -ofirst.o\n"
        f"{c_compiler} {token} -DUSE_BLARGG_APU "
        "-c second.c -osecond.o\n"
    )


class Snes9x2005PlusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(
                encoding="utf-8"
            )
        )

    def test_catalog_identity_and_make_contract_are_plus_owned(self) -> None:
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        spec = self.catalog["cores"][core_id]
        base = self.catalog["cores"]["snes9x2005"]

        self.assertTrue(
            snes9x2005_plus.snes9x2005_plus_spec_is_well_formed(spec)
        )
        self.assertFalse(
            snes9x2005_plus.snes9x2005_plus_spec_is_well_formed(base)
        )
        self.assertEqual(
            snes9x2005_plus.SNES9X2005_PLUS_MAKE_VARIABLES,
            spec["build"]["make_variables"],
        )
        self.assertEqual(
            "snes9x2005-plus-v1",
            snes9x2005_plus.SNES9X2005_PLUS_MAKE_PROFILE,
        )

        changed = copy.deepcopy(spec)
        changed["build"]["make_variables"]["USE_BLARGG_APU"] = 0
        self.assertFalse(
            snes9x2005_plus.snes9x2005_plus_spec_is_well_formed(changed)
        )

    def test_recipe_is_exact_scoped_and_normalized(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        spec = catalog["cores"][core_id]
        expected_spec = {
            "workflow": ".github/workflows/build-snes9x2005_plus.yml",
            "source": EXPECTED_SOURCE,
            "build": {
                "driver": "libretro-super",
                "source_key": core_id,
                "source_dir": "libretro-snes9x2005_plus",
                "output_path": "dist/unix/snes9x2005_plus_libretro.so",
                "artifact_name": "snes9x2005_plus_libretro.so",
                "git_version": EXPECTED_GIT_VERSION,
                "make_variables": {"USE_BLARGG_APU": 1},
            },
            "metadata": {
                "source_path": (
                    "/libretro-super/dist/info/"
                    "snes9x2005_plus_libretro.info"
                ),
                "artifact_name": "snes9x2005_plus_libretro.info",
            },
            "targets": ["arm64", "armhf"],
        }

        self.assertEqual(expected_spec, spec)
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(spec, core_id)
        )
        self.assertEqual(
            EXPECTED_GIT_VERSION, pipeline.validated_git_version(spec)
        )
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" b603569"|file'],
            pipeline.git_version_log_markers(spec),
        )
        self.assertIn("-f Makefile -f", pipeline.git_version_shell(spec))
        self.assertNotIn(
            "Makefile.libretro", pipeline.git_version_shell(spec)
        )
        make_variables = {"USE_BLARGG_APU": 1}
        self.assertEqual(
            make_variables, pipeline.validated_make_variables(spec)
        )
        make_shell = pipeline.make_variable_shell(spec)
        self.assertIn("export MAKEFLAGS=USE_BLARGG_APU=1", make_shell)
        self.assertIn("-f Makefile -f", make_shell)
        self.assertEqual(
            [
                "CORE_PIPELINE_MAKEFLAGS|USE_BLARGG_APU=1",
                (
                    "CORE_PIPELINE_MAKE_VARIABLE|USE_BLARGG_APU|"
                    "1|command line"
                ),
            ],
            pipeline.make_variable_log_markers(spec),
        )
        for arch in ("arm64", "armhf"):
            normalized = pipeline.normalized_build_contract(spec, arch)
            with self.subTest(arch=arch):
                self.assertEqual(
                    EXPECTED_GIT_VERSION, normalized["git_version"]
                )
                self.assertEqual(
                    make_variables, normalized["make_variables"]
                )
                self.assertNotIn("source_date_epoch", normalized)

        workflow_template = (
            ROOT / ".github" / "workflows" / "build-vice_x64.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            workflow_template.replace("vice_x64", core_id),
            (ROOT / spec["workflow"]).read_text(encoding="utf-8"),
        )

    def test_catalog_contract_fails_closed(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(catalog)
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "wrong-ref",
                lambda changed: changed["cores"][core_id]["source"].update(
                    {"requested_ref": "refs/heads/main"}
                ),
            ),
            mutation(
                "cxx-scope",
                lambda changed: changed["cores"][core_id]["build"][
                    "git_version"
                ].update({"compiler_scope": "cxx"}),
            ),
            mutation(
                "missing-variable",
                lambda changed: changed["cores"][core_id]["build"].pop(
                    "make_variables"
                ),
            ),
            mutation(
                "disabled-variable",
                lambda changed: changed["cores"][core_id]["build"][
                    "make_variables"
                ].update({"USE_BLARGG_APU": 0}),
            ),
            mutation(
                "boolean-variable",
                lambda changed: changed["cores"][core_id]["build"][
                    "make_variables"
                ].update({"USE_BLARGG_APU": True}),
            ),
            mutation(
                "extra-variable",
                lambda changed: changed["cores"][core_id]["build"][
                    "make_variables"
                ].update({"EXTRA": 1}),
            ),
            mutation(
                "source-date-epoch",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"source_date_epoch": 1776706168}
                ),
            ),
        )
        for label, changed in mutations:
            with self.subTest(label=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validate_catalog(changed)

    def test_make_variable_cannot_escape_plus_owner(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        changed = copy.deepcopy(catalog)
        changed["cores"]["uzem"]["build"]["make_variables"] = {
            "USE_BLARGG_APU": 1
        }
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)

    def test_catalog_and_golden_schemas_bind_exact_contract(self) -> None:
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
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        definition = "snes9x2005PlusCore"
        self.assertEqual(
            {"$ref": f"#/$defs/{definition}"},
            catalog_schema["properties"]["cores"]["properties"][core_id],
        )
        exact = catalog_schema["$defs"][definition]["allOf"][1]
        git_version = exact["properties"]["build"]["properties"][
            "git_version"
        ]["allOf"][1]
        self.assertEqual(["compiler_scope"], git_version["required"])
        self.assertEqual(
            {"const": " b603569"}, git_version["properties"]["value"]
        )
        self.assertEqual(
            {"const": "c"},
            git_version["properties"]["compiler_scope"],
        )

        for schema in (catalog_schema, golden_schema):
            with self.subTest(schema=schema["$id"]):
                self.assertEqual(
                    EXPECTED_MAKE_VARIABLE_SCHEMA,
                    schema["$defs"]["snes9x2005PlusMakeVariables"],
                )
        catalog_build = catalog_schema["$defs"][definition]["allOf"][1][
            "properties"
        ]["build"]
        self.assertIn("make_variables", catalog_build["required"])
        self.assertEqual(
            {"$ref": "#/$defs/snes9x2005PlusMakeVariables"},
            catalog_build["properties"]["make_variables"],
        )

        exact_build = golden_schema["$defs"]["buildGolden"][
            "dependentSchemas"
        ]["build"]
        branches = {
            branch["properties"]["core_id"]["const"]: branch
            for branch in exact_build["then"]["oneOf"]
        }
        branch = branches[core_id]["properties"]
        self.assertEqual(
            EXPECTED_SOURCE_KEYS, set(branch["source"]["required"])
        )
        self.assertEqual(
            EXPECTED_BUILD_KEYS, set(branch["build"]["required"])
        )
        self.assertEqual(
            EXPECTED_BUILD_KEYS,
            set(branch["build"]["propertyNames"]["enum"]),
        )
        self.assertEqual(
            {"$ref": "#/$defs/snes9x2005NativeGitVersion"},
            branch["build"]["properties"]["git_version"],
        )
        self.assertEqual(
            {"$ref": "#/$defs/snes9x2005PlusMakeVariables"},
            branch["build"]["properties"]["make_variables"],
        )

    def test_registry_dispatch_is_source_bound(self) -> None:
        contract = core_log_contract_for(
            snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        )

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("snes9x2005-plus-c-only-v1", contract.contract_id)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertEqual(
            "snes9x2005_plus_log_proves_contract", contract.proof_name
        )

    def test_historical_oracles_prove_exact_contract(self) -> None:
        identity = (
            snes9x2005_plus.SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )

        self.assertEqual(
            33,
            snes9x2005_plus.SNES9X2005_PLUS_LOG_CONTRACT.expected_compile_count,
        )
        for arch, log_path in ORACLE_LOGS.items():
            self.assertTrue(log_path.is_file())
            log_bytes = log_path.read_bytes()
            log = log_path.read_text(encoding="utf-8")
            arguments = (
                log,
                snes9x2005_plus.SNES9X2005_PLUS_CORE_ID,
                arch,
                identity["source_commit"],
                identity["source_tree"],
            )
            with self.subTest(arch=arch):
                self.assertEqual(ORACLE_LOG_IDENTITIES[arch][1], len(log_bytes))
                self.assertEqual(
                    ORACLE_LOG_IDENTITIES[arch][0],
                    hashlib.sha256(log_bytes).hexdigest(),
                )
                self.assertEqual(
                    33,
                    log.count(
                        snes9x2005_plus.SNES9X2005_PLUS_NATIVE_GIT_VERSION_LOG_TOKEN
                    ),
                )
                self.assertEqual(
                    33,
                    log.count(
                        snes9x2005_plus.SNES9X2005_PLUS_APU_COMPILE_TOKEN
                    ),
                )
                self.assertEqual(
                    snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_WARNING_COUNT[
                        arch
                    ],
                    log.casefold().count("warning:"),
                )
                self.assertEqual(
                    snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_NOTE_COUNT[arch],
                    log.casefold().count("note:"),
                )
                self.assertTrue(
                    snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                        *arguments
                    )
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

    def test_reviewed_diagnostic_fingerprints_are_exact(self) -> None:
        context_re = re.compile(r"^\s+(?:\d+ )?\|")
        for arch, log_path in ORACLE_LOGS.items():
            lines = log_path.read_text(encoding="utf-8").splitlines()
            tagged = [
                line
                for line in lines
                if "warning:" in line.casefold()
                or "note:" in line.casefold()
            ]
            headings = [
                line
                for line in lines
                if line.startswith("source/apu_blargg.c: In function")
                or line.startswith("source/memmap.c: In function")
            ]
            members = [
                line
                for line in lines
                if "warning:" in line.casefold()
                or "note:" in line.casefold()
                or context_re.match(line) is not None
            ]
            block_fingerprints: dict[str, int] = {}
            position = 0
            while position < len(members):
                block_size = (
                    6
                    if position + 3 < len(members)
                    and "note:" in members[position + 3].casefold()
                    else 3
                )
                block = members[position : position + block_size]
                fingerprint = lines_sha256(block)
                block_fingerprints[fingerprint] = (
                    block_fingerprints.get(fingerprint, 0) + 1
                )
                position += block_size
            with self.subTest(arch=arch):
                self.assertEqual(
                    snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_LINES_SHA256[
                        arch
                    ],
                    lines_sha256(tagged, unordered=True),
                )
                self.assertEqual(
                    list(
                        snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_HEADINGS[
                            arch
                        ]
                    ),
                    headings,
                )
                self.assertEqual(
                    snes9x2005_plus.SNES9X2005_PLUS_EXPECTED_DIAGNOSTIC_BLOCK_SHA256_COUNTS[
                        arch
                    ],
                    block_fingerprints,
                )

    def test_exact_contract_rejects_unreviewed_mutations(self) -> None:
        identity = (
            snes9x2005_plus.SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        baseline = ORACLE_LOGS["arm64"].read_text(encoding="utf-8")
        first_compile = next(
            line
            for line in baseline.splitlines()
            if line.startswith(COMPILERS["arm64"][0]) and " -c " in line
        )
        link = next(
            line
            for line in baseline.splitlines()
            if f" -o {snes9x2005_plus.SNES9X2005_PLUS_BUILD_ARTIFACT_NAME} "
            in line
        )
        warning = next(
            line for line in baseline.splitlines() if "warning:" in line
        )
        mutations = {
            "missing-source-marker": baseline.replace(
                snes9x2005_plus.SNES9X2005_PLUS_SOURCE_HEAD_MARKER + "\n",
                "",
                1,
            ),
            "duplicate-make-marker": baseline.replace(
                snes9x2005_plus.SNES9X2005_PLUS_MAKEFLAGS_MARKER,
                "\n".join(
                    (
                        snes9x2005_plus.SNES9X2005_PLUS_MAKEFLAGS_MARKER,
                        snes9x2005_plus.SNES9X2005_PLUS_MAKEFLAGS_MARKER,
                    )
                ),
                1,
            ),
            "base-default-marker": baseline.replace(
                snes9x2005_plus.SNES9X2005_PLUS_NATIVE_VERSION_MARKER,
                "CORE_PIPELINE_MAKE_DEFAULT|USE_BLARGG_APU|0|file\n"
                + snes9x2005_plus.SNES9X2005_PLUS_NATIVE_VERSION_MARKER,
                1,
            ),
            "missing-apu": baseline.replace("-DUSE_BLARGG_APU ", "", 1),
            "disabled-apu": baseline.replace(
                "-DUSE_BLARGG_APU", "-DUSE_BLARGG_APU=0", 1
            ),
            "changed-source": baseline.replace(
                "source/c4.c", "source/rogue.c", 1
            ),
            "duplicate-compile": baseline.replace(
                first_compile, first_compile + "\n" + first_compile, 1
            ),
            "cxx-compile": baseline.replace(
                first_compile,
                first_compile.replace(
                    COMPILERS["arm64"][0], COMPILERS["arm64"][1], 1
                ),
                1,
            ),
            "response-file": baseline.replace(
                first_compile,
                first_compile.replace(" -c ", " @options.rsp -c ", 1),
                1,
            ),
            "changed-link-option": baseline.replace(
                link, link.replace("-Wl,--no-undefined ", "", 1), 1
            ),
            "reordered-link-objects": baseline.replace(
                link,
                link.replace(
                    "./source/c4.o ./source/c4emu.o",
                    "./source/c4emu.o ./source/c4.o",
                    1,
                ),
                1,
            ),
            "changed-warning": baseline.replace(
                warning, warning.replace("negative value", "signed value", 1), 1
            ),
            "fatal-after-success": baseline + "fatal: forged failure\n",
            "make-failure-after-success": baseline + "make: *** failed\n",
        }
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                        changed,
                        core_id,
                        "arm64",
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
        self.assertFalse(
            snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                baseline,
                core_id,
                "arm64",
                "0" * 40,
                identity["source_tree"],
            )
        )
        self.assertFalse(
            snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                baseline,
                core_id,
                "arm64",
                identity["source_commit"],
                "0" * 40,
            )
        )

    def test_parallel_log_order_variants_preserve_exact_evidence(self) -> None:
        identity = (
            snes9x2005_plus.SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        lines = ORACLE_LOGS["arm64"].read_text(encoding="utf-8").splitlines()
        first_diagnostic = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("source/apu_blargg.c: In function")
        )
        link_position = next(
            index
            for index, line in enumerate(lines)
            if f" -o {snes9x2005_plus.SNES9X2005_PLUS_BUILD_ARTIFACT_NAME} "
            in line
        )
        headings: list[str] = []
        blocks: list[list[str]] = []
        position = first_diagnostic
        while position < link_position:
            if ": In function " in lines[position]:
                headings.append(lines[position])
                position += 1
                continue
            block_size = (
                6
                if position + 3 < link_position
                and "note:" in lines[position + 3].casefold()
                else 3
            )
            blocks.append(lines[position : position + block_size])
            position += block_size
        reordered_region = headings + [
            line for block in reversed(blocks) for line in block
        ]
        reordered_log = (
            "\n".join(
                lines[:first_diagnostic]
                + reordered_region
                + lines[link_position:]
            )
            + "\n"
        )

        moved_lines = list(lines)
        compile_position = next(
            index
            for index, line in enumerate(moved_lines)
            if line.startswith(COMPILERS["arm64"][0]) and " -c " in line
        )
        compile_line = moved_lines.pop(compile_position)
        diagnostic_position = next(
            index
            for index, line in enumerate(moved_lines)
            if "warning:" in line.casefold()
        )
        moved_lines.insert(diagnostic_position + 1, compile_line)
        interleaved_log = "\n".join(moved_lines) + "\n"

        for label, log in (
            ("reordered-blocks", reordered_log),
            ("compiler-interleaving", interleaved_log),
        ):
            with self.subTest(label=label):
                self.assertTrue(
                    snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                        log,
                        snes9x2005_plus.SNES9X2005_PLUS_CORE_ID,
                        "arm64",
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_version_variant_and_make_log_proofs_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        spec = catalog["cores"][core_id]
        for arch, (_c_compiler, cxx_compiler) in COMPILERS.items():
            log = valid_snes9x2005_plus_log(spec, arch)
            with self.subTest(arch=arch):
                self.assertNotIn(cxx_compiler, log)
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log,
                        spec["build"]["git_version"],
                        spec["source"]["commit"],
                        arch,
                    )
                )
                self.assertTrue(
                    pipeline.make_variable_log_proves_contract(
                        log,
                        spec["build"]["make_variables"],
                        arch,
                    )
                )

        baseline = valid_snes9x2005_plus_log(spec, "arm64")
        c_compiler, cxx_compiler = COMPILERS["arm64"]
        first_compile = next(
            line for line in baseline.splitlines() if " -c first.c" in line
        )
        cxx_log = baseline.replace(c_compiler, cxx_compiler, 1)
        self.assertFalse(
            pipeline.git_version_log_proves_contract(
                cxx_log,
                spec["build"]["git_version"],
                spec["source"]["commit"],
                "arm64",
            )
        )
        self.assertFalse(
            pipeline.make_variable_log_proves_contract(
                cxx_log,
                spec["build"]["make_variables"],
                "arm64",
            )
        )

        markers = pipeline.make_variable_log_markers(spec)
        marker_block = "\n".join(markers) + "\n"
        make_mutations = {
            "missing-marker": baseline.replace(markers[0] + "\n", "", 1),
            "wrong-origin": baseline.replace(
                "|command line", "|environment", 1
            ),
            "duplicate-marker": markers[0] + "\n" + baseline,
            "late-markers": baseline.replace(marker_block, "", 1)
            + marker_block,
            "missing-apu-token": baseline.replace(
                " -DUSE_BLARGG_APU", "", 1
            ),
            "disabled-apu": baseline.replace(
                "-DUSE_BLARGG_APU", "-DUSE_BLARGG_APU=0", 1
            ),
            "undefine-apu": baseline.replace(
                "-DUSE_BLARGG_APU", "-UUSE_BLARGG_APU", 1
            ),
            "duplicate-apu": baseline.replace(
                "-DUSE_BLARGG_APU",
                "-DUSE_BLARGG_APU -DUSE_BLARGG_APU",
                1,
            ),
            "xpreprocessor-apu": baseline.replace(
                "-DUSE_BLARGG_APU",
                "-Xpreprocessor -DUSE_BLARGG_APU",
                1,
            ),
            "response-file": baseline.replace(
                first_compile,
                first_compile.replace(" -c ", " @compiler-options.rsp -c "),
                1,
            ),
        }
        for label, changed_log in make_mutations.items():
            with self.subTest(make_log=label):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        changed_log,
                        spec["build"]["make_variables"],
                        "arm64",
                    )
                )

    def test_golden_boundary_binds_combined_plus_contract(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        spec = catalog["cores"][core_id]
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
            pipeline.native_git_version_golden_source_is_well_formed(
                core_id, source
            )
        )
        self.assertTrue(
            pipeline.exact_native_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                core_id,
                source,
            )
        )
        self.assertTrue(
            pipeline.combined_git_version_make_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                core_id,
                source,
            )
        )

        source_mutations = {
            "tree": {**source, "tree": "b" * 40},
            "resolved-commit": {**source, "resolved_commit": "b" * 40},
            "resolved-url": {
                **source,
                "resolved_url": "https://example.com/other.git",
            },
            "submodule": {
                **source,
                "submodules": [
                    {"path": "deps/foreign", "commit": "c" * 40}
                ],
            },
        }
        for label, changed_source in source_mutations.items():
            with self.subTest(source=label):
                self.assertFalse(
                    pipeline.exact_native_golden_build_contract_is_well_formed(
                        build,
                        spec["source"]["commit"],
                        core_id,
                        changed_source,
                    )
                )

        missing_scope = copy.deepcopy(build)
        missing_scope["git_version"].pop("compiler_scope")
        wrong_scope = copy.deepcopy(build)
        wrong_scope["git_version"]["compiler_scope"] = "cxx"
        missing_variable = copy.deepcopy(build)
        missing_variable.pop("make_variables")
        wrong_variable = copy.deepcopy(build)
        wrong_variable["make_variables"]["USE_BLARGG_APU"] = 0
        build_mutations = {
            "missing-scope": missing_scope,
            "wrong-scope": wrong_scope,
            "epoch": {**build, "source_date_epoch": 1},
            "extra": {**build, "unexpected": True},
            "missing-variable": missing_variable,
            "wrong-variable": wrong_variable,
        }
        for label, changed_build in build_mutations.items():
            with self.subTest(build=label):
                self.assertFalse(
                    pipeline.exact_native_golden_build_contract_is_well_formed(
                        changed_build,
                        spec["source"]["commit"],
                        core_id,
                        source,
                    )
                )

    def test_recognized_core_rejects_unknown_architecture(self) -> None:
        core_id = snes9x2005_plus.SNES9X2005_PLUS_CORE_ID
        identity = (
            snes9x2005_plus.SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
        )
        with self.assertRaisesRegex(PipelineError, "unknown architecture"):
            snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                "",
                core_id,
                "unknown",
                identity["source_commit"],
                identity["source_tree"],
            )
        self.assertFalse(
            snes9x2005_plus.snes9x2005_plus_log_proves_contract(
                "", "snes9x2005", "unknown", None, None
            )
        )


if __name__ == "__main__":
    unittest.main()
