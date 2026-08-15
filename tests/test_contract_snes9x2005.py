from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from .core_contract_helpers import pipeline
from scripts.core_pipeline_lib.contracts import snes9x2005
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
}
ORACLE_DIRECTORY = (
    ROOT
    / "tests"
    / "fixtures"
    / "per-core-oracles"
    / "snes9x2005"
)
ORACLE_LOGS = {
    arch: ORACLE_DIRECTORY / f"{arch}-build.txt"
    for arch in ("arm64", "armhf")
}


def lines_sha256(lines: list[str], *, unordered: bool = False) -> str:
    """Independently reproduce the contract's newline-framed fingerprints."""

    material = sorted(lines) if unordered else lines
    return hashlib.sha256(
        "".join(f"{line}\n" for line in material).encode("utf-8")
    ).hexdigest()


class Snes9x2005ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(
                encoding="utf-8"
            )
        )

    def test_catalog_identity_and_default_probe_are_base_owned(self) -> None:
        spec = self.catalog["cores"][snes9x2005.SNES9X2005_CORE_ID]
        plus = self.catalog["cores"]["snes9x2005_plus"]

        self.assertTrue(snes9x2005.snes9x2005_spec_is_well_formed(spec))
        self.assertFalse(snes9x2005.snes9x2005_spec_is_well_formed(plus))
        self.assertEqual(
            [snes9x2005.SNES9X2005_DEFAULT_MARKER],
            snes9x2005.snes9x2005_log_markers(spec),
        )
        shell = snes9x2005.snes9x2005_shell(spec)
        self.assertIn("core_pipeline_snes9x2005_default", shell)
        self.assertIn("$(origin USE_BLARGG_APU)", shell)
        self.assertEqual([], snes9x2005.snes9x2005_log_markers(plus))
        self.assertEqual("", snes9x2005.snes9x2005_shell(plus))
        changed = copy.deepcopy(spec)
        changed["build"]["source_dir"] += "-changed"
        self.assertFalse(snes9x2005.snes9x2005_spec_is_well_formed(changed))

    def test_recipe_is_exact_scoped_and_normalized(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        core_id = snes9x2005.SNES9X2005_CORE_ID
        spec = catalog["cores"][core_id]
        expected_spec = {
            "workflow": ".github/workflows/build-snes9x2005.yml",
            "source": EXPECTED_SOURCE,
            "build": {
                "driver": "libretro-super",
                "source_key": core_id,
                "source_dir": "libretro-snes9x2005",
                "output_path": "dist/unix/snes9x2005_libretro.so",
                "artifact_name": "snes9x2005_libretro.so",
                "git_version": EXPECTED_GIT_VERSION,
            },
            "metadata": {
                "source_path": (
                    "/libretro-super/dist/info/snes9x2005_libretro.info"
                ),
                "artifact_name": "snes9x2005_libretro.info",
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
        self.assertEqual({}, pipeline.validated_make_variables(spec))
        self.assertEqual("", pipeline.make_variable_shell(spec))
        self.assertEqual([], pipeline.make_variable_log_markers(spec))
        self.assertEqual(
            [snes9x2005.SNES9X2005_DEFAULT_MARKER],
            snes9x2005.snes9x2005_log_markers(spec),
        )
        variant_shell = snes9x2005.snes9x2005_shell(spec)
        self.assertIn(
            "CORE_PIPELINE_MAKE_DEFAULT|USE_BLARGG_APU|", variant_shell
        )
        self.assertIn(
            "-f Makefile -f /tmp/core-pipeline-snes9x2005-default.mk",
            variant_shell,
        )
        self.assertNotIn("Makefile.libretro", variant_shell)
        for arch in ("arm64", "armhf"):
            normalized = pipeline.normalized_build_contract(spec, arch)
            with self.subTest(arch=arch):
                self.assertEqual(
                    EXPECTED_GIT_VERSION, normalized["git_version"]
                )
                self.assertNotIn("make_variables", normalized)
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
        core_id = snes9x2005.SNES9X2005_CORE_ID

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(catalog)
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "source-tree",
                lambda changed: changed["cores"][core_id]["source"].update(
                    {"tree": "a" * 40}
                ),
            ),
            mutation(
                "missing-c-scope",
                lambda changed: changed["cores"][core_id]["build"][
                    "git_version"
                ].pop("compiler_scope"),
            ),
            mutation(
                "wrong-version",
                lambda changed: changed["cores"][core_id]["build"][
                    "git_version"
                ].update({"value": " 0000000"}),
            ),
            mutation(
                "unexpected-plus-variable",
                lambda changed: changed["cores"][core_id]["build"].update(
                    {"make_variables": {"USE_BLARGG_APU": 1}}
                ),
            ),
        )
        for label, changed in mutations:
            with self.subTest(label=label), self.assertRaises(
                pipeline.PipelineError
            ):
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
        core_id = snes9x2005.SNES9X2005_CORE_ID
        self.assertNotIn(
            core_id,
            catalog_schema["properties"]["cores"].get("properties", {}),
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

    def test_registry_dispatch_is_source_bound(self) -> None:
        contract = core_log_contract_for(snes9x2005.SNES9X2005_CORE_ID)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("snes9x2005-c-only-v1", contract.contract_id)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertEqual(
            "snes9x2005_log_proves_contract", contract.proof_name
        )

    def test_historical_oracles_prove_exact_contract(self) -> None:
        identity = snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY

        self.assertEqual(
            35, snes9x2005.SNES9X2005_LOG_CONTRACT.expected_compile_count
        )
        for arch, log_path in ORACLE_LOGS.items():
            self.assertTrue(log_path.is_file())
            log = log_path.read_text(encoding="utf-8")
            arguments = (
                log,
                snes9x2005.SNES9X2005_CORE_ID,
                arch,
                identity["source_commit"],
                identity["source_tree"],
            )
            with self.subTest(arch=arch):
                self.assertEqual(
                    35,
                    log.count(
                        snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_LOG_TOKEN
                    ),
                )
                self.assertEqual(12, log.casefold().count("warning:"))
                self.assertEqual(12, log.casefold().count("note:"))
                self.assertTrue(
                    snes9x2005.snes9x2005_log_proves_contract(*arguments)
                )
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

    def test_historical_control_without_default_marker_is_rejected(
        self,
    ) -> None:
        identity = snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY
        for arch in identity["targets"]:
            log = ORACLE_LOGS[arch].read_text(encoding="utf-8").replace(
                snes9x2005.SNES9X2005_DEFAULT_MARKER + "\n", "", 1
            )
            with self.subTest(arch=arch):
                self.assertNotIn(snes9x2005.SNES9X2005_DEFAULT_MARKER, log)
                self.assertFalse(
                    snes9x2005.snes9x2005_log_proves_contract(
                        log,
                        snes9x2005.SNES9X2005_CORE_ID,
                        arch,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_reviewed_diagnostic_fingerprints_are_exact(self) -> None:
        for arch in ("arm64", "armhf"):
            lines = ORACLE_LOGS[arch].read_text(encoding="utf-8").splitlines()
            tagged = [
                line
                for line in lines
                if "warning:" in line.casefold()
                or "note:" in line.casefold()
            ]
            headings: list[str] = []
            block_fingerprints: dict[str, int] = {}
            start = next(
                index
                for index, line in enumerate(lines)
                if line.startswith("source/memmap.c: In function")
            )
            link = next(
                index
                for index, line in enumerate(lines)
                if f" -o {snes9x2005.SNES9X2005_BUILD_ARTIFACT_NAME} "
                in line
            )
            position = start
            while position < link:
                line = lines[position]
                if line.startswith("source/memmap.c: In function"):
                    headings.append(line)
                    position += 1
                    continue
                block = lines[position : position + 6]
                fingerprint = lines_sha256(block)
                block_fingerprints[fingerprint] = (
                    block_fingerprints.get(fingerprint, 0) + 1
                )
                position += 6
            with self.subTest(arch=arch):
                self.assertEqual(24, len(tagged))
                self.assertEqual(
                    snes9x2005.SNES9X2005_EXPECTED_DIAGNOSTIC_LINES_SHA256[
                        arch
                    ],
                    lines_sha256(tagged, unordered=True),
                )
                self.assertEqual(
                    list(snes9x2005.SNES9X2005_EXPECTED_DIAGNOSTIC_HEADINGS),
                    headings,
                )
                self.assertEqual(
                    snes9x2005.SNES9X2005_EXPECTED_DIAGNOSTIC_BLOCK_SHA256_COUNTS[
                        arch
                    ],
                    block_fingerprints,
                )

    def test_reordered_reviewed_diagnostic_blocks_are_accepted(self) -> None:
        identity = snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY
        lines = ORACLE_LOGS["arm64"].read_text(encoding="utf-8").splitlines()
        first_diagnostic = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("source/memmap.c: In function")
        )
        link = next(
            index
            for index, line in enumerate(lines)
            if f" -o {snes9x2005.SNES9X2005_BUILD_ARTIFACT_NAME} " in line
        )
        headings: list[str] = []
        blocks: list[list[str]] = []
        position = first_diagnostic
        while position < link:
            if lines[position].startswith("source/memmap.c: In function"):
                headings.append(lines[position])
                position += 1
                continue
            blocks.append(lines[position : position + 6])
            position += 6
        reordered_region = headings + [
            line for block in reversed(blocks) for line in block
        ]
        reordered_log = (
            "\n".join(
                lines[:first_diagnostic]
                + reordered_region
                + lines[link:]
            )
            + "\n"
        )

        self.assertTrue(
            snes9x2005.snes9x2005_log_proves_contract(
                reordered_log,
                snes9x2005.SNES9X2005_CORE_ID,
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )

        first_block = lines[first_diagnostic + 1 : first_diagnostic + 7]
        insertion = next(
            index + 1
            for index, line in enumerate(lines)
            if line.startswith(COMPILERS["arm64"][0]) and " -c " in line
        )
        interleaved_lines = (
            lines[:insertion]
            + first_block
            + lines[insertion : first_diagnostic + 1]
            + lines[first_diagnostic + 7 :]
        )
        interleaved_log = "\n".join(interleaved_lines) + "\n"
        self.assertTrue(
            snes9x2005.snes9x2005_log_proves_contract(
                interleaved_log,
                snes9x2005.SNES9X2005_CORE_ID,
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )

    def test_compiler_echo_inside_reviewed_diagnostic_block_is_accepted(
        self,
    ) -> None:
        identity = snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY
        lines = ORACLE_LOGS["arm64"].read_text(encoding="utf-8").splitlines()
        moved_compile_position = max(
            index
            for index, line in enumerate(lines)
            if line.startswith(COMPILERS["arm64"][0]) and " -c " in line
        )
        moved_compile = lines.pop(moved_compile_position)
        first_warning_position = next(
            index for index, line in enumerate(lines) if "warning:" in line
        )
        lines.insert(first_warning_position + 2, moved_compile)
        interleaved_log = "\n".join(lines) + "\n"

        self.assertTrue(
            snes9x2005.snes9x2005_log_proves_contract(
                interleaved_log,
                snes9x2005.SNES9X2005_CORE_ID,
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )
        self.assertTrue(
            pipeline.registered_core_log_contract_proves(
                interleaved_log,
                snes9x2005.SNES9X2005_CORE_ID,
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )

    def test_exact_oracle_rejects_source_compile_link_and_diagnostic_tampering(
        self,
    ) -> None:
        identity = snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY
        log = ORACLE_LOGS["arm64"].read_text(encoding="utf-8")
        lines = log.splitlines()
        compile_line = next(
            line
            for line in lines
            if line.startswith(COMPILERS["arm64"][0]) and " -c " in line
        )
        link_line = next(
            line
            for line in lines
            if f" -o {snes9x2005.SNES9X2005_BUILD_ARTIFACT_NAME} " in line
        )
        warning_line = next(line for line in lines if "warning:" in line)
        note_line = next(line for line in lines if "note:" in line)
        context_line = next(line for line in lines if "Memory.Map [c + 6]" in line)
        first_warning_position = next(
            index for index, line in enumerate(lines) if "warning:" in line
        )
        first_block = lines[first_warning_position : first_warning_position + 6]
        reordered_block = list(first_block)
        reordered_block[1], reordered_block[2] = (
            reordered_block[2],
            reordered_block[1],
        )
        link_tokens = link_line.split()
        first_object = next(
            index for index, token in enumerate(link_tokens) if token.endswith(".o")
        )
        reordered_link_tokens = list(link_tokens)
        reordered_link_tokens[first_object : first_object + 2] = reversed(
            reordered_link_tokens[first_object : first_object + 2]
        )
        mutations = {
            "missing-default": log.replace(
                snes9x2005.SNES9X2005_DEFAULT_MARKER + "\n", "", 1
            ),
            "wrong-version": log.replace(
                snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_LOG_TOKEN,
                r'-DGIT_VERSION=\"" 0000000"\"',
                1,
            ),
            "variant-macro": log.replace(
                " -c -osource/c4.o",
                " -DUSE_BLARGG_APU=0 -c -osource/c4.o",
                1,
            ),
            "cxx-compile": log.replace(
                compile_line,
                compile_line.replace(
                    COMPILERS["arm64"][0], COMPILERS["arm64"][1], 1
                ),
                1,
            ),
            "duplicate-compile": log.replace(
                compile_line, compile_line + "\n" + compile_line, 1
            ),
            "reordered-link-objects": log.replace(
                link_line, " ".join(reordered_link_tokens), 1
            ),
            "changed-link-option": log.replace(
                " -Wl,--no-undefined ", " -Wl,-z,defs ", 1
            ),
            "changed-warning": log.replace(
                warning_line, warning_line.replace("-24576", "-24575"), 1
            ),
            "changed-note": log.replace(
                note_line, note_line.replace("bytes0x2000", "bytes0x2001"), 1
            ),
            "changed-context": log.replace(
                context_line, context_line.replace("c + 6", "c + 5"), 1
            ),
            "extra-context": log.replace(
                context_line, context_line + "\n" + context_line, 1
            ),
            "reordered-block-members": log.replace(
                "\n".join(first_block),
                "\n".join(reordered_block),
                1,
            ),
            "extra-warning": log + "source/rogue.c:1: warning: rogue\n",
            "make-failure": log + "make: *** [all] Error 2\n",
        }
        arguments = (
            snes9x2005.SNES9X2005_CORE_ID,
            "arm64",
            identity["source_commit"],
            identity["source_tree"],
        )
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    snes9x2005.snes9x2005_log_proves_contract(
                        changed, *arguments
                    )
                )
        identity_mutations = (
            ("snes9x2005_plus", "arm64", *arguments[2:]),
            (arguments[0], "arm64", "0" * 40, arguments[3]),
            (arguments[0], "arm64", arguments[2], "0" * 40),
        )
        for changed_arguments in identity_mutations:
            self.assertFalse(
                snes9x2005.snes9x2005_log_proves_contract(
                    log, *changed_arguments
                )
            )

    def test_golden_boundary_binds_exact_native_contract(self) -> None:
        catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        core_id = snes9x2005.SNES9X2005_CORE_ID
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
            pipeline.git_version_golden_build_contract_is_well_formed(
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
        build_mutations = {
            "missing-scope": missing_scope,
            "wrong-scope": wrong_scope,
            "epoch": {**build, "source_date_epoch": 1},
            "extra": {**build, "unexpected": True},
            "unexpected-plus-variable": {
                **build,
                "make_variables": {"USE_BLARGG_APU": 1},
            },
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
        identity = snes9x2005.SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY
        with self.assertRaisesRegex(PipelineError, "unknown architecture"):
            snes9x2005.snes9x2005_log_proves_contract(
                "",
                snes9x2005.SNES9X2005_CORE_ID,
                "unknown",
                identity["source_commit"],
                identity["source_tree"],
            )
        self.assertFalse(
            snes9x2005.snes9x2005_log_proves_contract(
                "",
                "snes9x2005_plus",
                "unknown",
                identity["source_commit"],
                identity["source_tree"],
            )
        )


if __name__ == "__main__":
    unittest.main()
