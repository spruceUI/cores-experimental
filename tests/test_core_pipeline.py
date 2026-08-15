#!/usr/bin/env python3

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import importlib.util
import io
import json
import re
import stat
from pathlib import Path
import tempfile
import unittest

from tests import expected_counts
from unittest import mock
import zipfile

from scripts.core_pipeline_lib.contracts.picodrive import PICODRIVE_SUBMODULES

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "core_pipeline.py"
SPEC = importlib.util.spec_from_file_location("core_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)

class CatalogTests(unittest.TestCase):
    def test_json_object_and_file_digest_share_one_byte_snapshot(self) -> None:
        raw = b'{"value":"first"}\n'
        path = Path("record.json")
        with mock.patch.object(
            Path,
            "read_bytes",
            side_effect=[raw, b'{"value":"second"}\n'],
        ) as read_bytes:
            document, file_sha256 = pipeline.load_json_with_sha256(path)

        self.assertEqual({"value": "first"}, document)
        self.assertEqual(pipeline.sha256_bytes(raw), file_sha256)
        read_bytes.assert_called_once_with()

    def test_json_loader_rejects_utf16_and_utf32(self) -> None:
        path = Path("record.json")
        for encoding in ("utf-16", "utf-32"):
            with self.subTest(encoding=encoding), mock.patch.object(
                Path,
                "read_bytes",
                return_value='{"value":"wrong encoding"}'.encode(encoding),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "cannot load JSON"
                ):
                    pipeline.load_json_with_sha256(path)

    def test_validation_context_reuses_the_verified_byte_snapshot(self) -> None:
        first = b'{"value":"first"}\n'
        second = b'{"value":"second"}\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_bytes(first)
            context = pipeline._PinValidationContext()
            expected = pipeline.sha256_bytes(first)

            self.assertEqual(
                {"value": "first"},
                pipeline.verified_json_object(
                    path, expected, "fixture record", context
                ),
            )
            path.write_bytes(second)
            self.assertEqual(
                {"value": "first"},
                pipeline.verified_json_object(
                    path, expected, "fixture record", context
                ),
            )

    def _legacy_recipe_without_pipeline_bundle(self, recipe: dict) -> dict:
        legacy_recipe = copy.deepcopy(recipe)
        pipeline_bundle = legacy_recipe.pop("pipeline_bundle")
        commit_blacklist = legacy_recipe.pop("commit_blacklist")
        self.assertTrue(
            pipeline.pipeline_source_bundle_is_well_formed(pipeline_bundle)
        )
        self.assertTrue(
            pipeline.commit_blacklist_reference_is_well_formed(commit_blacklist)
        )
        self.assertNotIn("pipeline_bundle", legacy_recipe)
        self.assertNotIn("commit_blacklist", legacy_recipe)
        return legacy_recipe

    def _assert_current_workflow_uses_shared_actions_profile(
        self, recipe: dict
    ) -> None:
        """Check current workflow migration without rewriting old recipe hashes."""

        workflow_path = ROOT / recipe["workflow"]
        self.assertTrue(workflow_path.is_file())
        workflow_text = workflow_path.read_text(encoding="utf-8")
        self.assertEqual(1, workflow_text.count("--runner-profile github-actions"))
        self.assertIn("scripts/core_pipeline.py e2e", workflow_text)

    def test_catalog_is_valid_and_sources_are_full_pins(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        self.assertEqual("disabled", catalog["policy"]["publication"])
        self.assertEqual(
            {
                "2048",
                "81",
                "a5200",
                "arduous",
                "atari800",
                "bluemsx",
                "cap32",
                "crocods",
                "ecwolf",
                "fbneo",
                "fceumm",
                "ffmpeg",
                "flycast",
                "fmsx",
                "freechaf",
                "freeintv",
                "gambatte",
                "gearboy",
                "gearcoleco",
                "gearsystem",
                "genesis_plus_gx",
                "genesis_plus_gx_wide",
                "gpsp",
                "handy",
                "lowresnx",
                "mame2003_plus",
                "mednafen_ngp",
                "mednafen_lynx",
                "mednafen_pcfx",
                "mednafen_pce_fast",
                "mednafen_supafaust",
                "mednafen_supergrafx",
                "mednafen_vb",
                "mednafen_wswan",
                "mgba",
                "neocd",
                "nestopia",
                "o2em",
                "pcsx_rearmed",
                "picodrive",
                "prboom",
                "fuse",
                "gme",
                "frodo",
                "quasi88",
                "retro8",
                "reminiscence",
                "gw",
                "mu",
                "hatari",
                "theodore",
                "bk",
                "numero",
                "opera",
                "fbalpha2012",
                "chimerasnes",
                "px68k",
                "x1",
                "yabasanshiro",
                "daphne",
                "uae4arm",
                "puae2021",
                "lutro",
                "np2kai",
                "sameduck",
                "puzzlescript",
                "fake08",
                "uw8",
                "chailove",
                "dosbox_pure",
            "easyrpg",
                "parallel_n64",
                "mupen64plus_next",
                "km_duckswanstation_xtreme_amped",
                "km_parallel_n64_xtreme_amped_turbo",
            "libgametank",
                "tic80",
                "ardens",
                "pokemini",
                "potator",
                "prosystem",
                "quicknes",
                "race",
                "snes9x",
                "snes9x2005",
                "snes9x2005_plus",
                "snes9x2002",
                "snes9x2010",
                "squirreljme",
                "tyrquake",
                "stella2014",
                "swanstation",
                "tgbdual",
                "uzem",
                "vecx",
                "vemulator",
                "vice_x64",
                "vice_xvic",
            },
            set(catalog["cores"]),
        )
        for core in catalog["cores"].values():
            self.assertRegex(core["source"]["commit"], r"^[0-9a-f]{40}$")

    def test_individual_workflows_cover_every_catalog_core(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        audit = pipeline.audit_workflows(catalog)
        self.assertEqual(2, audit["schema_version"])
        self.assertEqual(expected_counts.CATALOG_CORE_COUNT, audit["catalog_core_count"])
        self.assertEqual(expected_counts.CORE_WORKFLOW_COUNT, audit["core_workflow_count"])
        self.assertEqual(expected_counts.CATALOG_CORE_COUNT, audit["catalog_workflow_count"])
        self.assertEqual([], audit["missing_catalog_workflows"])
        self.assertEqual(expected_counts.UNMIGRATED_WORKFLOW_COUNT, len(audit["uncataloged_workflows"]))
        self.assertEqual([], audit["active_aggregate_workflows"])
        self.assertEqual([], audit["invalid_catalog_workflows"])
        self.assertEqual("valid", audit["release_orchestration"]["status"])
        for record in audit["workflows"].values():
            self.assertEqual(
                pipeline.sha256_file(ROOT / record["workflow"]),
                record["file_sha256"],
            )
        self.assertEqual(
            1,
            audit["release_orchestration"]["summary"][
                "unique_reusable_workflow_count"
            ],
        )
        self.assertFalse(any(key.startswith("batch_") for key in audit))

    def test_audit_keeps_legacy_false_green_risk_visible(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        audit = pipeline.audit_workflows(catalog)
        self.assertEqual(expected_counts.MASKED_BUILD_FAILURE_PATHS, audit["masked_build_failure_paths"])
        self.assertEqual(expected_counts.INFO_ONLY_RISK_WORKFLOWS, audit["info_only_risk_workflows"])
        self.assertEqual(expected_counts.CATALOG_CORE_COUNT, audit["shared_pipeline_workflows"])
        self.assertEqual(expected_counts.UNMIGRATED_WORKFLOW_COUNT, audit["unmigrated_workflow_count"])
        self.assertEqual(expected_counts.UNMIGRATED_WORKFLOW_COUNT, len(audit["unmigrated_workflows"]))
        self.assertEqual(
            set(audit["uncataloged_workflows"]), set(audit["unmigrated_workflows"])
        )

    def test_audit_detects_missing_core_and_active_aggregate_without_reading_it(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "build-handy.yml").write_text(
                "scripts/core_pipeline.py e2e --runner-profile github-actions "
                "--core handy\n",
                encoding="utf-8",
            )
            (workflow_dir / "build-all-nightly.yml").write_bytes(b"\xff\xfe")
            (workflow_dir / "build-all-release.yaml").write_text(
                "ignored aggregate fixture\n", encoding="utf-8"
            )
            with mock.patch.object(pipeline, "ROOT", root):
                audit = pipeline.audit_workflows(
                    {"cores": {"handy": {}, "missing": {}}}
                )
        self.assertEqual(["missing"], audit["missing_catalog_workflows"])
        self.assertEqual(
            [
                ".github/workflows/build-all-nightly.yml",
                ".github/workflows/build-all-release.yaml",
            ],
            audit["active_aggregate_workflows"],
        )

    def test_audit_rejects_catalog_workflow_binding_drift(self) -> None:
        commands = {
            "wrong-core": (
                "python3 scripts/core_pipeline.py e2e "
                "--runner-profile github-actions --core stella2014\n"
            ),
            "missing-core": (
                "python3 scripts/core_pipeline.py e2e "
                "--runner-profile github-actions\n"
            ),
            "simulated-profile": (
                "python3 scripts/core_pipeline.py e2e "
                "--runner-profile github-actions-sim --core handy\n"
            ),
        }
        for label, command in commands.items():
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    workflow_dir = root / ".github" / "workflows"
                    workflow_dir.mkdir(parents=True)
                    (workflow_dir / "build-handy.yml").write_text(
                        command, encoding="utf-8"
                    )
                    with mock.patch.object(pipeline, "ROOT", root):
                        audit = pipeline.audit_workflows(
                            {"cores": {"handy": {}}}
                        )
                self.assertEqual(
                    ["handy"], audit["invalid_catalog_workflows"]
                )
                self.assertFalse(
                    audit["workflows"]["handy"]["uses_shared_pipeline"]
                )

    def test_cmd_audit_fails_for_missing_aggregate_or_invalid_bindings(self) -> None:
        base_report = {
            "schema_version": 2,
            "missing_catalog_workflows": [],
            "active_aggregate_workflows": [],
            "invalid_catalog_workflows": [],
            "unmigrated_workflow_count": 1,
            "unmigrated_workflows": ["legacy"],
            "uncataloged_workflows": ["legacy"],
            "masked_build_failure_paths": 1,
            "info_only_risk_workflows": 1,
            "workflows": {},
            "release_orchestration": {"status": "valid"},
        }
        args = argparse.Namespace(catalog=Path("catalog.json"), output=None)
        for field in (
            None,
            "missing_catalog_workflows",
            "active_aggregate_workflows",
            "invalid_catalog_workflows",
            "release_orchestration",
        ):
            report = copy.deepcopy(base_report)
            if field == "release_orchestration":
                report[field] = {"status": "invalid"}
            elif field is not None:
                report[field] = ["fixture"]
            with self.subTest(field=field), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {}}
            ), mock.patch.object(
                pipeline, "audit_workflows", return_value=report
            ), mock.patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(0 if field is None else 1, pipeline.cmd_audit(args))

    def test_migrated_workflows_are_read_only_and_publication_disabled(self) -> None:
        for core_id in (
            "2048",
            "81",
            "a5200",
            "atari800",
            "bluemsx",
            "cap32",
            "crocods",
            "mgba",
            "gpsp",
            "fceumm",
            "ffmpeg",
            "fmsx",
            "ecwolf",
            "fbneo",
            "freechaf",
            "freeintv",
            "gambatte",
            "gearboy",
            "gearcoleco",
            "gearsystem",
            "genesis_plus_gx",
            "genesis_plus_gx_wide",
            "handy",
            "mame2003_plus",
            "mednafen_lynx",
            "mednafen_ngp",
            "mednafen_pcfx",
            "mednafen_pce_fast",
            "mednafen_supafaust",
            "mednafen_supergrafx",
            "mednafen_vb",
            "mednafen_wswan",
            "neocd",
            "nestopia",
            "o2em",
            "pcsx_rearmed",
            "pokemini",
            "potator",
            "prosystem",
            "quicknes",
            "race",
            "snes9x",
            "snes9x2005",
            "snes9x2005_plus",
            "stella2014",
            "swanstation",
            "tgbdual",
            "uzem",
            "vecx",
            "vemulator",
            "vice_x64",
            "vice_xvic",
        ):
            text = (ROOT / ".github" / "workflows" / f"build-{core_id}.yml").read_text(
                encoding="utf-8"
            )
            self.assertIn("contents: read", text)
            self.assertIn("scripts/core_pipeline.py e2e", text)
            self.assertEqual(1, text.count("--runner-profile github-actions"))
            self.assertEqual(1, text.count(f"--core {core_id}"))
            self.assertLess(
                text.index("scripts/core_pipeline.py e2e"),
                text.index("--runner-profile github-actions"),
            )
            self.assertLess(
                text.index("--runner-profile github-actions"),
                text.index(f"--core {core_id}"),
            )
            self.assertIn(
                "actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5", text
            )
            self.assertNotIn("actions/checkout@v4", text)
            self.assertNotIn("contents: write", text)
            self.assertNotIn("gh release create", text)
            self.assertNotIn("gh release upload", text)
            self.assertNotIn('|| echo "::warning::', text)

    def test_migrated_workflows_verify_both_archives_before_any_load(self) -> None:
        command = (
            "python3 scripts/toolchain_archive.py verify-downloads "
            "--lock pins/toolchains/local-cache-v1.json "
            "--arm64 cores-arm64.tar.gz --armhf cores-armhf.tar.gz"
        )
        for core_id in (
            "2048",
            "81",
            "a5200",
            "atari800",
            "bluemsx",
            "cap32",
            "crocods",
            "mgba",
            "gpsp",
            "fceumm",
            "ffmpeg",
            "fmsx",
            "ecwolf",
            "fbneo",
            "freechaf",
            "freeintv",
            "gambatte",
            "gearboy",
            "gearcoleco",
            "gearsystem",
            "genesis_plus_gx",
            "genesis_plus_gx_wide",
            "handy",
            "mame2003_plus",
            "mednafen_lynx",
            "mednafen_ngp",
            "mednafen_pcfx",
            "mednafen_pce_fast",
            "mednafen_supafaust",
            "mednafen_supergrafx",
            "mednafen_vb",
            "mednafen_wswan",
            "neocd",
            "nestopia",
            "o2em",
            "pcsx_rearmed",
            "pokemini",
            "potator",
            "prosystem",
            "quicknes",
            "race",
            "snes9x",
            "snes9x2005",
            "snes9x2005_plus",
            "stella2014",
            "swanstation",
            "tgbdual",
            "uzem",
            "vecx",
            "vemulator",
            "vice_x64",
            "vice_xvic",
        ):
            text = (ROOT / ".github" / "workflows" / f"build-{core_id}.yml").read_text(
                encoding="utf-8"
            )
            download64 = text.index(
                'gh release download toolchains --pattern "cores-arm64.tar.gz"'
            )
            downloadhf = text.index(
                'gh release download toolchains --pattern "cores-armhf.tar.gz"'
            )
            verify = text.index(command)
            load64 = text.index("gunzip -c cores-arm64.tar.gz | docker load")
            loadhf = text.index("gunzip -c cores-armhf.tar.gz | docker load")
            e2e = text.index("scripts/core_pipeline.py e2e")
            self.assertLess(max(download64, downloadhf), verify)
            self.assertLess(verify, min(load64, loadhf))
            self.assertLess(max(load64, loadhf), e2e)
            self.assertEqual(1, text.count(command))
            self.assertEqual(1, text.count("gunzip -c cores-arm64.tar.gz | docker load"))
            self.assertEqual(1, text.count("gunzip -c cores-armhf.tar.gz | docker load"))
            self.assertNotIn("continue-on-error", text)
            self.assertNotIn("|| true", text)

    def test_compile_definitions_are_strict_target_bound_and_sanitized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["neocd"]
        expected = [
            "HWCAP2_AES=0",
            "HWCAP2_CRC32=0",
            "HWCAP2_SHA1=0",
            "HWCAP2_SHA2=0",
        ]
        pcsx_spec = catalog["cores"]["pcsx_rearmed"]
        self.assertEqual(
            expected,
            pipeline.compile_definitions_for_target(pcsx_spec, "armhf"),
        )
        self.assertEqual([], pipeline.compile_definitions_for_target(pcsx_spec, "arm64"))
        self.assertEqual(expected, pipeline.compile_definitions_for_target(spec, "armhf"))
        self.assertEqual(
            [], pipeline.compile_definitions_for_target(spec, "arm64")
        )
        armhf_script = pipeline.container_build_script(
            "neocd", "armhf", spec, catalog["resolver"]
        )
        arm64_script = pipeline.container_build_script(
            "neocd", "arm64", spec, catalog["resolver"]
        )
        self.assertLess(armhf_script.index("unset CFLAGS"), armhf_script.index("export CFLAGS="))
        self.assertLess(
            armhf_script.index("export CFLAGS="),
            armhf_script.index("./libretro-build.sh neocd"),
        )
        for definition in expected:
            self.assertIn(f"-D{definition}", armhf_script)
            self.assertNotIn(f"-D{definition}", arm64_script)

        flags = " ".join(f"-D{definition}" for definition in expected)
        valid_compile = (
            f"arm-a30-linux-gnueabihf-gcc {flags} -c -o source.o source.c\n"
        )
        self.assertTrue(
            pipeline.compile_log_proves_definitions(valid_compile, expected, "armhf")
        )
        self.assertFalse(
            pipeline.compile_log_proves_definitions(
                valid_compile
                + "arm-a30-linux-gnueabihf-gcc -c -o unbound.o unbound.c\n",
                expected,
                "armhf",
            )
        )
        self.assertFalse(
            pipeline.compile_log_proves_definitions(
                f"gcc {flags} -c -o host.o host.c\n", expected, "armhf"
            )
        )
        for malformed in ([0], [None], [{}], ["Z=0", "A=0"], ["DUP=0", "DUP=1"]):
            with self.subTest(malformed=malformed):
                self.assertFalse(
                    pipeline.compile_log_proves_definitions(
                        valid_compile, malformed, "armhf"
                    )
                )
        self.assertFalse(
            pipeline.compile_log_proves_definitions(
                "printf '" + valid_compile.rstrip() + "'\n", expected, "armhf"
            )
        )
        self.assertTrue(
            pipeline.compile_log_proves_definitions(
                ("unrelated verbose make output\n" * 10000) + valid_compile,
                expected,
                "armhf",
            )
        )
        for conflicting_option in (
            "-DHWCAP2_AES=1",
            "-DHWCAP2_AES",
            '-D"HWCAP2_AES"=1',
            "'-DHWCAP2_AES=1'",
            '"-DHWCAP2_AES=1"',
            r"\-DHWCAP2_AES=1",
            "-UHWCAP2_AES",
            "-D HWCAP2_AES=1",
            "-U HWCAP2_AES",
            "-Wp,-DHWCAP2_AES=1",
            "-Wp,-UHWCAP2_AES",
            "-Wp,-D,HWCAP2_AES=1",
            "-DHWCAP2_AES()=1",
            "-Wp,-D,HWCAP2_AES()=1",
            "-Xpreprocessor -DHWCAP2_AES=1",
            "-Xpreprocessor -D -Xpreprocessor HWCAP2_AES=1",
            "-Xpreprocessor -U -Xpreprocessor HWCAP2_AES",
            "@compiler-options.rsp",
        ):
            with self.subTest(conflicting_option=conflicting_option):
                self.assertFalse(
                    pipeline.compile_log_proves_definitions(
                        valid_compile.rstrip()
                        + " "
                        + conflicting_option
                        + "\n",
                        expected,
                        "armhf",
                    )
                )

        for obfuscated_compile in (
            'arm-a30-linux-gnueabihf-gcc -""c -o unbound.o unbound.c',
            r"arm-a30-linux-gnueabihf-gcc -\c -o unbound.o unbound.c",
            'arm-a30-linux-gnueabihf-g""cc -c -o unbound.o unbound.c',
        ):
            with self.subTest(obfuscated_compile=obfuscated_compile):
                self.assertFalse(
                    pipeline.compile_log_proves_definitions(
                        valid_compile + obfuscated_compile + "\n",
                        expected,
                        "armhf",
                    )
                )

        mutations = (
            ({}, "non-empty object"),
            ({"arm64": []}, "non-empty array"),
            ({"bogus": ["SAFE=0"]}, "non-target architecture"),
            ({"armhf": [0]}, "entries must be strings"),
            ({"armhf": ["Z=0", "A=0"]}, "must be sorted"),
            ({"armhf": ["DUP=0", "DUP=1"]}, "repeats DUP"),
            ({"armhf": ["UNSAFE=-1"]}, "entry is invalid"),
            ({"armhf": ["UNSAFE=0 -Wl,--bad"]}, "entry is invalid"),
            ({"armhf": ["TOO_BIG=4294967296"]}, "entry is invalid"),
            ({"armhf": ["TOO_LONG=" + "1" * 11]}, "entry is invalid"),
        )
        for definitions, message in mutations:
            changed = copy.deepcopy(catalog)
            changed["cores"]["neocd"]["build"]["compile_definitions"] = definitions
            with self.subTest(definitions=definitions), self.assertRaisesRegex(
                pipeline.PipelineError, message
            ):
                pipeline.validate_catalog(changed)

        for invalid_tree in ("not-a-tree", None, 1, []):
            changed = copy.deepcopy(catalog)
            changed["cores"]["neocd"]["source"]["tree"] = invalid_tree
            with self.subTest(tree=invalid_tree), self.assertRaisesRegex(
                pipeline.PipelineError, "source.tree"
            ):
                pipeline.validate_catalog(changed)

    def test_source_date_epoch_is_strict_commit_bound_and_sanitized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["pcsx_rearmed"]
        epoch = 1782602899
        self.assertEqual(epoch, pipeline.validated_source_date_epoch(spec))
        self.assertIsNone(
            pipeline.validated_source_date_epoch(catalog["cores"]["mgba"])
        )

        for arch in ("arm64", "armhf"):
            script = pipeline.container_build_script(
                "pcsx_rearmed", arch, spec, catalog["resolver"]
            )
            self.assertLess(
                script.index("unset CFLAGS"),
                script.index(f"export SOURCE_DATE_EPOCH={epoch}"),
            )
            self.assertLess(
                script.index(f"export SOURCE_DATE_EPOCH={epoch}"),
                script.index("actual_source_date_epoch="),
            )
            self.assertLess(
                script.index("actual_source_date_epoch="),
                script.index("./libretro-build.sh pcsx_rearmed"),
            )
            self.assertIn(
                'test "$actual_source_date_epoch" = 1782602899', script
            )

        untimestamped_script = pipeline.container_build_script(
            "mgba", "arm64", catalog["cores"]["mgba"], catalog["resolver"]
        )
        self.assertIn("SOURCE_DATE_EPOCH", untimestamped_script.splitlines()[4])
        self.assertNotIn("export SOURCE_DATE_EPOCH=", untimestamped_script)
        self.assertNotIn("actual_source_date_epoch=", untimestamped_script)

        self.assertFalse(
            pipeline.build_source_date_epoch_matches(
                {"source_date_epoch": True}, 1
            )
        )
        for value in (
            True,
            None,
            1.5,
            "1782602899",
            -1,
            0,
            pipeline.MAX_SOURCE_DATE_EPOCH + 1,
        ):
            changed = copy.deepcopy(catalog)
            changed["cores"]["pcsx_rearmed"]["build"]["source_date_epoch"] = value
            with self.subTest(value=value), self.assertRaisesRegex(
                pipeline.PipelineError, "source_date_epoch"
            ):
                pipeline.validate_catalog(changed)

    def test_picodrive_recipe_profile_is_closed_and_uses_source_root_make(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["picodrive"]
        profile = spec["build"]["recipe_profile"]

        self.assertEqual(profile, pipeline.validated_recipe_profile(spec))
        self.assertIsNot(profile, pipeline.validated_recipe_profile(spec))
        self.assertEqual(
            "/metadata-replacements/picodrive.info",
            pipeline.metadata_replacement_container_path(
                spec["metadata"]["replacement"]
            ),
        )
        self.assertEqual(
            [
                "-v",
                (
                    f"{ROOT / spec['metadata']['replacement']['path']}:"
                    "/metadata-replacements/picodrive.info:ro"
                ),
            ],
            pipeline.metadata_replacement_mount_args(spec),
        )

        expected_make = {
            "arm64": "/usr/bin/make",
            "armhf": "/usr/bin/gmake",
        }
        for arch, make_program in expected_make.items():
            with self.subTest(arch=arch):
                normalized = pipeline.normalized_build_contract(spec, arch)
                self.assertEqual(profile, normalized["recipe_profile"])
                self.assertEqual(
                    pipeline.compile_definitions_for_target(spec, arch),
                    normalized["compile_definitions"],
                )
                script = pipeline.container_build_script(
                    "picodrive", arch, spec, catalog["resolver"]
                )
                make_line = (
                    f'{make_program} -f Makefile.libretro platform="unix" -j7'
                )
                self.assertIn(make_line, script)
                self.assertNotIn("./libretro-build.sh picodrive", script)
                self.assertNotIn(" CC=", make_line)
                self.assertNotIn(" CXX=", make_line)
                self.assertLess(
                    script.index("git -C libretro-picodrive checkout --detach"),
                    script.index("CORE_PIPELINE_PICODRIVE_RECIPE|"),
                )
                self.assertLess(
                    script.index(f"CORE_PIPELINE_PICODRIVE_BUILD_BEGIN|{arch}"),
                    script.index(make_line),
                )
                self.assertLess(
                    script.index(make_line),
                    script.index(f"CORE_PIPELINE_PICODRIVE_BUILD_END|{arch}"),
                )
                self.assertLess(
                    script.index("export CC=\"${HOST_CC}-gcc\""),
                    script.index(make_line),
                )
                self.assertIn(
                    "test -s libretro-picodrive/picodrive_libretro.so",
                    script,
                )
                if arch == "armhf":
                    self.assertLess(
                        script.index("export CYCLONE_CC=gcc"),
                        script.index(make_line),
                    )
                    self.assertLess(
                        script.index("export CYCLONE_CXX=g++"),
                        script.index(make_line),
                    )
                else:
                    self.assertNotIn("export CYCLONE_CC=", script)
                    self.assertNotIn("export CYCLONE_CXX=", script)

        missing = copy.deepcopy(spec)
        missing["build"].pop("recipe_profile")
        with self.assertRaisesRegex(pipeline.PipelineError, "is required"):
            pipeline.validated_recipe_profile(missing)

        for label, value in (
            ("not-object", "picodrive-v1"),
            ("missing-host-tools", {"kind": "picodrive-v1", "git_revision": "-f0d4a011"}),
            ("wrong-revision", {**profile, "git_revision": "-00000000"}),
            ("extra", {**profile, "extra": True}),
        ):
            changed = copy.deepcopy(spec)
            changed["build"]["recipe_profile"] = value
            with self.subTest(label=label), self.assertRaisesRegex(
                pipeline.PipelineError, "exact reviewed Picodrive"
            ):
                pipeline.validated_recipe_profile(changed)

        for field, value in (
            ("cmake", {}),
            ("generated_source", {}),
            ("git_version", {}),
            ("make_variables", {}),
            ("platforms", {}),
        ):
            changed = copy.deepcopy(spec)
            changed["build"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                pipeline.PipelineError, "cannot be combined"
            ):
                pipeline.validated_recipe_profile(changed)

        wrong_core = copy.deepcopy(catalog["cores"]["pcsx_rearmed"])
        wrong_core["build"]["recipe_profile"] = copy.deepcopy(profile)
        with self.assertRaisesRegex(
            pipeline.PipelineError, "restricted to the exact reviewed Picodrive"
        ):
            pipeline.validated_recipe_profile(wrong_core)

    def test_fbneo_combines_only_exact_armhf_header_definitions_and_version(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["fbneo"]
        definitions = [
            "HWCAP2_AES=1",
            "HWCAP2_CRC32=16",
            "HWCAP2_SHA1=4",
            "HWCAP2_SHA2=8",
        ]
        self.assertEqual(
            {"armhf": definitions},
            pipeline.validated_compile_definitions(spec),
        )
        self.assertEqual([], pipeline.compile_definitions_for_target(spec, "arm64"))
        self.assertEqual(
            definitions,
            pipeline.compile_definitions_for_target(spec, "armhf"),
        )
        self.assertEqual(
            spec["build"]["git_version"],
            pipeline.validated_git_version(spec),
        )
        self.assertEqual(
            [],
            pipeline.normalized_build_contract(spec, "arm64")[
                "compile_definitions"
            ],
        )
        self.assertEqual(
            definitions,
            pipeline.normalized_build_contract(spec, "armhf")[
                "compile_definitions"
            ],
        )

        armhf_script = pipeline.container_build_script(
            "fbneo", "armhf", spec, catalog["resolver"]
        )
        flags = " ".join(f"-D{definition}" for definition in definitions)
        self.assertIn(f"export CFLAGS='{flags}'", armhf_script)
        self.assertIn(f"export CXXFLAGS='{flags}'", armhf_script)
        build_command = (
            "MAKEFLAGS='-- GIT_VERSION=9d7716aa2 "
            "GIT_DATE=260503 HIDE=' ./libretro-build.sh fbneo"
        )
        self.assertLess(
            armhf_script.index("export CFLAGS="),
            armhf_script.index(build_command),
        )
        arm64_script = pipeline.container_build_script(
            "fbneo", "arm64", spec, catalog["resolver"]
        )
        self.assertNotIn("HWCAP2_", arm64_script)

        wrong = copy.deepcopy(spec)
        wrong["build"]["compile_definitions"]["armhf"][0] = "HWCAP2_AES=2"
        with self.assertRaisesRegex(
            pipeline.PipelineError, "outside the exact reviewed FBNeo contract"
        ):
            pipeline.validated_compile_definitions(wrong)
        with self.assertRaisesRegex(
            pipeline.PipelineError, "outside the exact reviewed FBNeo contract"
        ):
            pipeline.validated_git_version(wrong)

    def test_mame2003_plus_short8_version_is_closed_and_command_scoped(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["mame2003_plus"]
        expected_version = {
            "derivation": "native-space-short8-v1",
            "value": " 5373e38e",
            "compiler_scope": "c",
        }

        validated = pipeline.validated_git_version(spec)
        self.assertEqual(expected_version, validated)
        self.assertIsNot(spec["build"]["git_version"], validated)
        self.assertEqual(
            expected_version,
            pipeline.exact_native_git_version_contract("mame2003_plus"),
        )
        self.assertTrue(
            pipeline.git_version_contract_is_well_formed(
                expected_version, spec["source"]["commit"]
            )
        )
        self.assertFalse(
            pipeline.git_version_contract_is_well_formed(
                expected_version,
                spec["source"]["commit"][:8] + "0" * 32,
            )
        )

        command = (
            "MAKEFLAGS='-- GIT_VERSION=\"\\ 5373e38e\" HIDE=' "
            "./libretro-build.sh mame2003_plus"
        )
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                normalized = pipeline.normalized_build_contract(spec, arch)
                self.assertEqual(expected_version, normalized["git_version"])
                self.assertEqual(1777763287, normalized["source_date_epoch"])
                self.assertEqual([], normalized["compile_definitions"])
                script = pipeline.container_build_script(
                    "mame2003_plus", arch, spec, catalog["resolver"]
                )
                lines = script.splitlines()
                self.assertEqual(1, lines.count(command))
                source_marker = (
                    "CORE_PIPELINE_SOURCE_IDENTITY|mame2003_plus|"
                    "5373e38e1091eb28f075513ecdc2575bafc8a5e3|"
                    "990e22f33a33cbfe733e22b3b5fef6cda76056fb|catalog"
                )
                self.assertEqual(1, script.count(source_marker))
                self.assertFalse(
                    any(line.startswith("export MAKEFLAGS=") for line in lines)
                )
                self.assertNotIn("HIDE=@", script)
                self.assertLess(
                    script.index(source_marker),
                    script.index(
                        "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
                    ),
                )
                self.assertLess(
                    script.index(
                        "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
                    ),
                    script.index(
                        f"CORE_PIPELINE_MAME2003_PLUS_BUILD_BEGIN|{arch}"
                    ),
                )
                self.assertLess(
                    script.index(
                        f"CORE_PIPELINE_MAME2003_PLUS_BUILD_BEGIN|{arch}"
                    ),
                    script.index(command),
                )
                self.assertLess(
                    script.index(command),
                    script.index(
                        f"CORE_PIPELINE_MAME2003_PLUS_BUILD_END|{arch}"
                    ),
                )
        with self.assertRaisesRegex(
            pipeline.PipelineError, "exact core identity"
        ):
            pipeline.container_build_script(
                "pcsx_rearmed", "arm64", spec, catalog["resolver"]
            )

        mutations = (
            ("missing-leading-space", {**expected_version, "value": "5373e38e"}),
            ("wrong-width", {**expected_version, "value": " 5373e38"}),
            ("wrong-scope", {**expected_version, "compiler_scope": "cxx"}),
            (
                "missing-scope",
                {
                    "derivation": "native-space-short8-v1",
                    "value": " 5373e38e",
                },
            ),
            ("extra-field", {**expected_version, "MAKEFLAGS": "unsafe"}),
        )
        for label, version in mutations:
            changed = copy.deepcopy(spec)
            changed["build"]["git_version"] = version
            with self.subTest(label=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validated_git_version(changed)

        for field, value in (
            ("source_key", "mame2003"),
            ("source_date_epoch", 1777763286),
            ("output_path", "mame2003_plus_libretro.so"),
        ):
            changed = copy.deepcopy(spec)
            changed["build"][field] = value
            with self.subTest(field=field), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validated_git_version(changed)

        raw_makeflags = copy.deepcopy(spec)
        raw_makeflags["build"]["MAKEFLAGS"] = "-- GIT_VERSION=foreign HIDE=@"
        with self.assertRaisesRegex(
            pipeline.PipelineError, "raw GNU Make control variables"
        ):
            pipeline.validated_make_variables(raw_makeflags)

        foreign = copy.deepcopy(catalog["cores"]["pcsx_rearmed"])
        foreign["build"]["git_version"] = copy.deepcopy(expected_version)
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validated_git_version(foreign)

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
            pipeline.git_version_golden_build_contract_is_well_formed(
                build,
                source["resolved_commit"],
                "mame2003_plus",
                source,
                "arm64",
            )
        )
        for core_id, arch in (
            ("pcsx_rearmed", "arm64"),
            ("mame2003_plus", "x86_64"),
            ("mame2003_plus", None),
        ):
            with self.subTest(core_id=core_id, arch=arch):
                self.assertFalse(
                    pipeline.git_version_golden_build_contract_is_well_formed(
                        build,
                        source["resolved_commit"],
                        core_id,
                        source,
                        arch,
                    )
                )

    def test_mame2003_plus_record_snapshot_and_promotion_fail_closed(
        self,
    ) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "mame2003_plus"
        arch = "arm64"
        spec = catalog["cores"][core_id]
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"mame2003-plus artifact fixture")
            metadata.write_bytes(b"mame2003-plus metadata fixture")
            log.write_text("reviewed log fixture\n", encoding="utf-8")
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
                "needed": [],
            }
            source = {
                **spec["source"],
                "resolved_commit": spec["source"]["commit"],
                "resolved_url": spec["source"]["url"],
                "submodules": [],
            }
            document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": arch,
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "source": source,
                "toolchain": {
                    **catalog["toolchains"][arch],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, arch
                    ),
                    "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
                "build": {
                    **pipeline.normalized_build_contract(spec, arch),
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
            }
            record_path = root / "build-record.json"
            record_path.write_text(json.dumps(document), encoding="utf-8")
            snapshot_path = root / "recipe-snapshot.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(document))
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, document, f"{core_id}/{arch}"
                ),
            )

            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ), mock.patch.object(
                pipeline, "compile_log_proves_definitions", return_value=True
            ), mock.patch.object(
                pipeline, "git_version_log_proves_contract", return_value=True
            ), mock.patch.object(
                pipeline,
                "_registered_core_log_contract_proves",
                return_value=True,
            ):
                self.assertEqual(
                    (artifact, metadata, log),
                    pipeline.validate_build_record_identity(
                        document, record_path, catalog_path, catalog
                    ),
                )

                changed_version = copy.deepcopy(document)
                changed_version["build"]["git_version"]["value"] = "5373e38e"
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "compile environment"
                ):
                    pipeline.validate_build_record_identity(
                        changed_version, record_path, catalog_path, catalog
                    )

                changed_source = copy.deepcopy(document)
                changed_source["source"]["resolved_url"] = (
                    "https://github.com/libretro/mame2003-plus-libretro"
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "resolved source URL"
                ):
                    pipeline.validate_build_record_identity(
                        changed_source, record_path, catalog_path, catalog
                    )

            changed_snapshot = copy.deepcopy(document)
            changed_snapshot["build"]["source_date_epoch"] -= 1
            self.assertTrue(
                any(
                    "git-version recipe snapshot lacks its normalized contract"
                    in error
                    or "build does not match the catalog snapshot" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        changed_snapshot,
                        f"{core_id}/{arch}-changed",
                    )
                )
            )
            self.assertNotEqual(
                pipeline.provenance_identity_sha256(document),
                pipeline.provenance_identity_sha256(changed_version),
            )

            promoted = {
                "core_id": core_id,
                "architecture": arch,
                "promotion_state": "build_golden",
                "validation_scope": "static-build-only",
                "artifact": copy.deepcopy(expected_artifact),
                "source": copy.deepcopy(source),
                "toolchain": {},
                "metadata": copy.deepcopy(document["metadata"]),
                "build": copy.deepcopy(document["build"]),
                "e2e": {
                    "record_sha256": "b" * 64,
                    "content_sha256": "c" * 64,
                    "package_sha256": "d" * 64,
                },
            }
            golden = {
                "schema_version": 2,
                "core_id": core_id,
                "pin_id": "fixture-mame2003-plus",
                "local_only": True,
                "publication": "disabled",
                "baseline": {"repository_commit": "e" * 40},
                "cores": {
                    core_id: {
                        "workflow": spec["workflow"],
                        "artifacts": {
                            "arm64": {
                                "status": "valid",
                                "path": artifact.name,
                                "sha256": expected_artifact["sha256"],
                            },
                            "armhf": {"status": "not_shipped"},
                        },
                    }
                },
                "build_goldens": {core_id: {arch: promoted}},
                "summary": {},
            }
            golden["content_sha256"] = pipeline.golden_content_sha256(golden)
            report = pipeline.validate_golden_document(golden)
            self.assertFalse(
                any(
                    "promoted build contract is invalid" in error
                    for error in report["errors"]
                )
            )
            changed_golden = copy.deepcopy(golden)
            changed_golden["build_goldens"][core_id][arch]["build"][
                "source_date_epoch"
            ] -= 1
            changed_golden["content_sha256"] = pipeline.golden_content_sha256(
                changed_golden
            )
            self.assertTrue(
                any(
                    "promoted build contract is invalid" in error
                    for error in pipeline.validate_golden_document(
                        changed_golden
                    )["errors"]
                )
            )

    def test_mame2003_plus_stored_e2e_and_compatibility_do_not_fall_through(
        self,
    ) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "mame2003_plus"
        arch = "arm64"
        spec = catalog["cores"][core_id]
        source = {
            **spec["source"],
            "resolved_commit": spec["source"]["commit"],
            "resolved_url": spec["source"]["url"],
            "submodules": [],
        }
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            log_path = root / "build.log"
            log_path.write_text("stored log fixture\n", encoding="utf-8")
            recipe_path = root / "recipe-snapshot.json"
            recipe_path.write_text("{}\n", encoding="utf-8")
            package_path = root / "package.zip"
            package_path.write_bytes(b"not-a-package")
            artifact_path = root / spec["build"]["artifact_name"]
            artifact_path.write_bytes(b"stored artifact fixture")
            record_path = root / "build-record.json"
            e2e_path = root / "e2e-record.json"

            record = {
                "schema_version": 2,
                "local_only": True,
                "publication": "disabled",
                "result": "passed",
                "build_exit_code": 0,
                "core_id": core_id,
                "architecture": arch,
                "source": copy.deepcopy(source),
                "recipe": {"fixture": True},
                "toolchain": {
                    "image_id": f"sha256:{'1' * 64}",
                    "resolved_image_id": f"sha256:{'1' * 64}",
                    "libretro_super_commit": "2" * 40,
                    "resolver_digests": {
                        "libretro_super_commit": "2" * 40,
                    },
                },
                "build": {
                    **pipeline.normalized_build_contract(spec, arch),
                    "log": log_path.name,
                    "log_sha256": pipeline.sha256_file(log_path),
                },
                "artifact": {
                    "status": "valid",
                    "path": artifact_path.name,
                    "sha256": pipeline.sha256_file(artifact_path),
                    "size": artifact_path.stat().st_size,
                    "needed": [],
                },
                "metadata": {
                    "status": "valid",
                    "path": spec["metadata"]["artifact_name"],
                    "sha256": "3" * 64,
                    "size": 1,
                },
            }
            candidate_provenance = {
                "candidate_id": "a" * 64,
                "fixture": "exact authenticated golden provenance",
            }
            self.assertNotIn("source_candidate", record)

            def stored_fixture(current_record: dict) -> dict:
                record_path.write_text(
                    json.dumps(current_record), encoding="utf-8"
                )
                record_sha = pipeline.sha256_file(record_path)
                evidence = {
                    "schema_version": 2,
                    "run_id": "stored-mame-fixture",
                    "local_only": True,
                    "publication": "disabled",
                    "result": "passed",
                    "workflow_audit": {},
                    "runner": {},
                    "builds": [
                        {
                            "core_id": core_id,
                            "architecture": arch,
                            "result": "passed",
                            "record_sha256": record_sha,
                        }
                    ],
                    "packages": [],
                }
                evidence["content_sha256"] = pipeline.e2e_content_sha256(
                    evidence
                )
                e2e_path.write_text(json.dumps(evidence), encoding="utf-8")
                relative = lambda path: str(path.relative_to(ROOT))
                return {
                    "source_candidate": copy.deepcopy(candidate_provenance),
                    "source": copy.deepcopy(current_record["source"]),
                    "recipe": copy.deepcopy(current_record["recipe"]),
                    "toolchain": copy.deepcopy(current_record["toolchain"]),
                    "artifact": copy.deepcopy(current_record["artifact"]),
                    "metadata": copy.deepcopy(current_record["metadata"]),
                    "build": copy.deepcopy(current_record["build"]),
                    "e2e": {
                        "run_id": evidence["run_id"],
                        "content_sha256": evidence["content_sha256"],
                        "package_sha256": "4" * 64,
                        "build_records": {arch: record_sha},
                    },
                    "local_store": {
                        "e2e_record": {
                            "path": relative(e2e_path),
                            "sha256": pipeline.sha256_file(e2e_path),
                        },
                        "package": {
                            "path": relative(package_path),
                            "sha256": pipeline.sha256_file(package_path),
                        },
                        "artifact": {
                            "path": relative(artifact_path),
                            "sha256": pipeline.sha256_file(artifact_path),
                        },
                        "build_records": {
                            arch: {
                                "path": relative(record_path),
                                "sha256": record_sha,
                            }
                        },
                        "build_logs": {
                            arch: {
                                "path": relative(log_path),
                                "sha256": current_record["build"][
                                    "log_sha256"
                                ],
                            }
                        },
                        "recipe_snapshots": {
                            arch: {
                                "path": relative(recipe_path),
                                "sha256": pipeline.sha256_file(recipe_path),
                            }
                        },
                    },
                }

            projected_records: list[dict] = []
            snapshot_records: list[dict] = []

            def project_candidate(
                provenance: object,
                **_kwargs: object,
            ) -> None:
                self.assertEqual(candidate_provenance, provenance)
                projected_records.append(copy.deepcopy(record))
                return None

            def verify_candidate_snapshot(
                _path: Path,
                snapshot_record: dict,
                _label: str,
                **_kwargs: object,
            ) -> list[str]:
                self.assertEqual(
                    candidate_provenance,
                    snapshot_record.get("source_candidate"),
                )
                snapshot_records.append(copy.deepcopy(snapshot_record))
                return []

            with mock.patch.object(
                pipeline, "compile_log_proves_definitions", return_value=True
            ), mock.patch.object(
                pipeline, "git_version_log_proves_contract", return_value=True
            ), mock.patch.object(
                pipeline,
                "_registered_core_log_contract_proves",
                return_value=True,
            ), mock.patch.object(
                pipeline,
                "source_candidate_record_contract_projection",
                side_effect=project_candidate,
            ), mock.patch.object(
                pipeline,
                "_verify_recipe_snapshot",
                side_effect=verify_candidate_snapshot,
            ), mock.patch.object(
                pipeline,
                "validate_artifact",
                return_value=copy.deepcopy(record["artifact"]),
            ):
                valid_errors = pipeline.verify_stored_e2e_bundle(
                    stored_fixture(record), core_id, arch
                )
                self.assertFalse(
                    any(
                        "stored arm64 build contract is invalid" in error
                        for error in valid_errors
                    )
                )

                changed = copy.deepcopy(record)
                changed["build"]["source_date_epoch"] -= 1
                changed_errors = pipeline.verify_stored_e2e_bundle(
                    stored_fixture(changed), core_id, arch
                )
                self.assertTrue(
                    any(
                        "stored arm64 build contract is invalid" in error
                        for error in changed_errors
                    )
                )
            self.assertGreaterEqual(len(projected_records), 2)
            self.assertGreaterEqual(len(snapshot_records), 2)
            self.assertNotIn("source_candidate", record)

            compatibility_snapshot = root / "compatibility-snapshot.json"
            compatibility_snapshot.write_text("{}\n", encoding="utf-8")
            compatibility_record = {
                "schema_version": 2,
                "local_only": True,
                "publication": "disabled",
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:01:00+00:00",
                "core_id": core_id,
                "architecture": arch,
                "result": "passed",
                "build_exit_code": 0,
                "source": copy.deepcopy(source),
                "recipe": {
                    "pipeline_sha256": "5" * 64,
                    "pipeline_bundle": {
                        "files": {
                            "scripts/core_pipeline.py": "5" * 64,
                        }
                    },
                },
                "toolchain": {},
                "build": copy.deepcopy(record["build"]),
                "artifact": {},
                "metadata": {},
            }

            def expected_target(current_record: dict) -> dict:
                expected = copy.deepcopy(current_record)
                expected["source_candidate"] = copy.deepcopy(
                    candidate_provenance
                )
                expected["local_store"] = {
                    "recipe_snapshots": {
                        arch: {
                            "sha256": pipeline.sha256_file(
                                compatibility_snapshot
                            )
                        }
                    }
                }
                return {"golden_record": expected}

            historical_snapshot_records: list[dict] = []

            def verify_candidate_historical_snapshot(
                _path: Path,
                snapshot_record: dict,
                _label: str,
                **_kwargs: object,
            ) -> list[str]:
                self.assertEqual(
                    candidate_provenance,
                    snapshot_record.get("source_candidate"),
                )
                historical_snapshot_records.append(
                    copy.deepcopy(snapshot_record)
                )
                return []

            compatibility_log = "compatibility log fixture\n"
            with mock.patch.object(
                pipeline, "pipeline_source_bundle_is_well_formed", return_value=True
            ), mock.patch.object(
                pipeline,
                "require_canonical_store_entry",
                return_value=compatibility_snapshot,
            ), mock.patch.object(
                pipeline,
                "_verify_historical_recipe_snapshot",
                side_effect=verify_candidate_historical_snapshot,
            ), mock.patch.object(
                pipeline,
                "source_candidate_record_contract_projection",
                side_effect=project_candidate,
            ), mock.patch.object(
                pipeline, "compile_log_proves_definitions", return_value=True
            ), mock.patch.object(
                pipeline, "git_version_log_proves_contract", return_value=True
            ), mock.patch.object(
                pipeline,
                "_registered_core_log_contract_proves",
                return_value=True,
            ):
                pipeline._validate_canonical_compatibility_build_record(
                    compatibility_record,
                    record_path,
                    expected_target(compatibility_record),
                    compatibility_log,
                )
                changed_compatibility = copy.deepcopy(compatibility_record)
                changed_compatibility["build"]["source_date_epoch"] -= 1
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    r"MAME2003\+ build/source contract",
                ):
                    pipeline._validate_canonical_compatibility_build_record(
                        changed_compatibility,
                        record_path,
                        expected_target(changed_compatibility),
                        compatibility_log,
                    )
            self.assertGreaterEqual(len(historical_snapshot_records), 2)
            self.assertNotIn("source_candidate", compatibility_record)

    def test_picodrive_build_record_rejects_cross_arch_profile_substitution(
        self,
    ) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "picodrive"
        spec = catalog["cores"][core_id]
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)

        for arch, other_arch in (("arm64", "armhf"), ("armhf", "arm64")):
            with self.subTest(arch=arch), tempfile.TemporaryDirectory(
                dir=local_root
            ) as directory:
                root = Path(directory)
                artifact = root / spec["build"]["artifact_name"]
                metadata = root / spec["metadata"]["artifact_name"]
                log = root / "build.log"
                artifact.write_bytes(b"picodrive artifact fixture")
                metadata.write_bytes(
                    (ROOT / spec["metadata"]["replacement"]["path"]).read_bytes()
                )
                log.write_text(
                    pipeline.metadata_replacement_markers(
                        spec["metadata"]["replacement"]
                    )[0]
                    + "\n",
                    encoding="utf-8",
                )
                expected_artifact = {
                    "status": "valid",
                    "path": artifact.name,
                    "sha256": pipeline.sha256_file(artifact),
                    "size": artifact.stat().st_size,
                    "needed": [],
                }
                source = {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "submodules": copy.deepcopy(PICODRIVE_SUBMODULES),
                }
                document = {
                    "schema_version": 2,
                    "result": "passed",
                    "build_exit_code": 0,
                    "local_only": True,
                    "publication": "disabled",
                    "core_id": core_id,
                    "architecture": arch,
                    "recipe": pipeline.recipe_record(
                        catalog_path, core_id, spec
                    ),
                    "source": source,
                    "toolchain": {
                        **catalog["toolchains"][arch],
                        "archive_provenance": pipeline.expected_archive_provenance(
                            catalog, arch
                        ),
                        "resolved_image_id": catalog["toolchains"][arch][
                            "image_id"
                        ],
                        "libretro_super_commit": catalog["resolver"][
                            "libretro_super_commit"
                        ],
                        "resolver_digests": catalog["resolver"],
                        "compiler": "fixture compiler",
                        "sysroot": "/fixture",
                    },
                    "artifact": expected_artifact,
                    "metadata": {
                        "status": "valid",
                        "path": metadata.name,
                        "sha256": pipeline.sha256_file(metadata),
                        "size": metadata.stat().st_size,
                    },
                    "build": {
                        **pipeline.normalized_build_contract(spec, arch),
                        "log": log.name,
                        "log_sha256": pipeline.sha256_file(log),
                    },
                }
                record = root / "build-record.json"
                record.write_text(json.dumps(document), encoding="utf-8")
                snapshot_path = root / "recipe-snapshot.json"
                snapshot_path.write_bytes(pipeline.recipe_snapshot(document))
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path, document, f"picodrive/{arch}"
                    ),
                )
                changed_profile = copy.deepcopy(document)
                changed_profile["build"]["recipe_profile"][
                    "git_revision"
                ] = "-00000000"
                self.assertNotEqual(
                    pipeline.provenance_identity_sha256(document),
                    pipeline.provenance_identity_sha256(changed_profile),
                )
                with mock.patch.object(
                    pipeline, "validate_artifact", return_value=expected_artifact
                ), mock.patch.object(
                    pipeline,
                    "compile_log_proves_definitions",
                    return_value=True,
                ), mock.patch.object(
                    pipeline,
                "_registered_core_log_contract_proves",
                    return_value=True,
                ):
                    self.assertEqual(
                        (artifact, metadata, log),
                        pipeline.validate_build_record_identity(
                            document, record, catalog_path, catalog
                        ),
                    )

                    swapped = copy.deepcopy(document)
                    swapped["build"]["compile_definitions"] = (
                        pipeline.compile_definitions_for_target(spec, other_arch)
                    )
                    snapshot_errors = pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        swapped,
                        f"picodrive/{arch}-cross-arch",
                    )
                    self.assertTrue(
                        any(
                            "recipe-profile snapshot lacks its normalized contract"
                            in error
                            for error in snapshot_errors
                        )
                    )
                    with self.assertRaisesRegex(
                        pipeline.PipelineError, "compile environment"
                    ):
                        pipeline.validate_build_record_identity(
                            swapped, record, catalog_path, catalog
                        )

    def test_ffmpeg_make_variables_are_exact_typed_and_sanitized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["ffmpeg"]
        expected = {
            "ARCH_AARCH64": 0,
            "ARCH_ARM": 0,
            "ARCH_X86": 0,
            "ARCH_X86_64": 0,
            "HAVE_SSA": 0,
            "LIBRETRO_EMBED_FFMPEG": 1,
            "OPENGL": 0,
        }
        canonical = (
            "--output-sync=recurse "
            "ARCH_AARCH64=0 ARCH_ARM=0 ARCH_X86=0 ARCH_X86_64=0 "
            "HAVE_SSA=0 LIBRETRO_EMBED_FFMPEG=1 OPENGL=0"
        )
        self.assertEqual(
            {
                "url": "https://github.com/libretro/FFmpeg.git",
                "requested_ref": "refs/heads/master",
                "commit": "4920879d2f09a78cdf855403c349457cee1c31da",
                "tree": "72377e12026a2f034d12a2ac3fcea35aa29200eb",
            },
            spec["source"],
        )
        self.assertEqual("libretro-super", spec["build"]["driver"])
        self.assertEqual(1598579820, pipeline.validated_source_date_epoch(spec))
        self.assertEqual(expected, pipeline.validated_make_variables(spec))
        self.assertEqual(canonical, pipeline.canonical_makeflags(spec))
        self.assertNotIn("compile_definitions", spec["build"])

        script = pipeline.container_build_script(
            "ffmpeg", "arm64", spec, catalog["resolver"]
        )
        unset_index = script.index("unset CFLAGS")
        export_index = script.index("export MAKEFLAGS=")
        origin_index = script.index("core_pipeline_make_variable_origins")
        build_index = script.index("./libretro-build.sh ffmpeg")
        self.assertLess(unset_index, export_index)
        self.assertLess(export_index, origin_index)
        self.assertLess(origin_index, build_index)
        self.assertIn(f"export MAKEFLAGS='{canonical}'", script)
        unset_variables = set(
            next(
                line for line in script.splitlines() if line.startswith("unset ")
            ).split()[1:]
        )
        self.assertTrue(
            {
                "MAKEFLAGS",
                "GNUMAKEFLAGS",
                "MAKEFILES",
                "MAKEOVERRIDES",
                "MFLAGS",
                *expected,
            }.issubset(unset_variables)
        )
        self.assertIn("-f Makefile -f /tmp/core-pipeline", script)
        self.assertIn("/libretro-super/libretro-ffmpeg/libretro", script)
        self.assertEqual(
            [
                "CORE_PIPELINE_MAKEFLAGS|" + canonical,
                *[
                    f"CORE_PIPELINE_MAKE_VARIABLE|{name}|{value}|command line"
                    for name, value in expected.items()
                ],
            ],
            pipeline.make_variable_log_markers(spec),
        )

        def changed_variables(value: object) -> dict:
            changed = copy.deepcopy(catalog)
            changed["cores"]["ffmpeg"]["build"]["make_variables"] = value
            return changed

        mutations = []
        missing = copy.deepcopy(expected)
        missing.pop("OPENGL")
        mutations.append(("missing", changed_variables(missing), "missing OPENGL"))
        extra = copy.deepcopy(expected)
        extra["SAFE_EXTRA"] = 0
        mutations.append(("extra", changed_variables(extra), "extra SAFE_EXTRA"))
        non_string_name = copy.deepcopy(expected)
        non_string_name[1] = 0
        mutations.append(
            ("non-string-name", changed_variables(non_string_name), "names must be strings")
        )
        reserved = copy.deepcopy(expected)
        reserved["CC"] = 0
        mutations.append(("reserved", changed_variables(reserved), "reserved names"))
        raw_reserved = copy.deepcopy(expected)
        raw_reserved["MAKEFLAGS"] = 0
        mutations.append(
            ("reserved-makeflags", changed_variables(raw_reserved), "reserved names")
        )
        unsorted = {name: expected[name] for name in reversed(expected)}
        mutations.append(("unsorted", changed_variables(unsorted), "keys must be sorted"))
        for label, name, value, message in (
            # An identifier-shaped string clears the type guard (parallel_n64
            # needs WITH_DYNAREC=aarch64) but still fails this profile, which
            # declares OPENGL as the integer 0.
            ("string", "OPENGL", "0", "portable FFmpeg"),
            ("free-form-string", "OPENGL", "$(shell id)", "exact integer"),
            ("empty-string", "OPENGL", "", "exact integer"),
            ("bool", "OPENGL", False, "exact integer"),
            ("negative", "OPENGL", -1, "exact integer"),
            ("nonbinary", "OPENGL", 2, "exact integer"),
            ("wrong-binary", "LIBRETRO_EMBED_FFMPEG", 0, "portable FFmpeg"),
        ):
            values = copy.deepcopy(expected)
            values[name] = value
            mutations.append((label, changed_variables(values), message))
        mutations.append(("not-object", changed_variables([]), "must be an object"))
        for raw_name in (
            "MAKEFLAGS",
            "makeflags",
            "GNUMAKEFLAGS",
            "MAKEFILES",
            "MAKEOVERRIDES",
            "MFLAGS",
        ):
            raw = copy.deepcopy(catalog)
            raw["cores"]["ffmpeg"]["build"][raw_name] = canonical
            mutations.append((f"raw-{raw_name}", raw, "raw GNU Make"))
        for ignored_name in ("make_flags", "arbitrary"):
            ignored = copy.deepcopy(catalog)
            ignored["cores"]["ffmpeg"]["build"][ignored_name] = canonical
            mutations.append(
                (f"ignored-{ignored_name}", ignored, "portable FFmpeg build keys")
            )
        missing_build_key = copy.deepcopy(catalog)
        missing_build_key["cores"]["ffmpeg"]["build"].pop("source_key")
        mutations.append(
            (
                "missing-build-key",
                missing_build_key,
                "portable FFmpeg build keys",
            )
        )
        no_epoch = copy.deepcopy(catalog)
        no_epoch["cores"]["ffmpeg"]["build"].pop("source_date_epoch")
        mutations.append(("missing-epoch", no_epoch, "source_date_epoch is required"))
        with_definitions = copy.deepcopy(catalog)
        with_definitions["cores"]["ffmpeg"]["build"]["compile_definitions"] = {
            "arm64": ["SAFE=0"]
        }
        mutations.append(
            (
                "compile-definitions",
                with_definitions,
                "cannot be combined with compile_definitions",
            )
        )
        wrong_driver = copy.deepcopy(catalog)
        wrong_driver["cores"]["ffmpeg"]["build"]["driver"] = "direct-make"
        mutations.append(("wrong-driver", wrong_driver, "requires driver libretro-super"))
        for label, changed, message in mutations:
            with self.subTest(label=label), self.assertRaisesRegex(
                pipeline.PipelineError, message
            ):
                pipeline.validate_catalog(changed)

    def test_ffmpeg_make_log_and_dependency_policy_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["ffmpeg"]
        variables = spec["build"]["make_variables"]
        markers = pipeline.make_variable_log_markers(spec)
        definitions = [
            f"-D{definition}"
            for definition in pipeline.PORTABLE_FFMPEG_COMPILE_DEFINITIONS
        ]
        compilers = {
            "arm64": "aarch64-linux-gnu-gcc",
            "armhf": "arm-a30-linux-gnueabihf-gcc",
        }

        def valid_log(arch: str) -> str:
            compile_line = (
                f"{compilers[arch]} -c source.c -o source.o "
                + " ".join(definitions)
            )
            return "\n".join([*markers, compile_line]) + "\n"

        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                self.assertTrue(
                    pipeline.make_variable_log_proves_contract(
                        valid_log(arch), variables, arch
                    )
                )

        baseline = valid_log("arm64")
        for marker in markers:
            with self.subTest(missing_marker=marker):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        baseline.replace(marker + "\n", "", 1), variables, "arm64"
                    )
                )
        for label, changed_log in (
            (
                "environment-origin",
                baseline.replace("|command line", "|environment", 1),
            ),
            ("duplicate-marker", markers[0] + "\n" + baseline),
            (
                "extra-marker",
                baseline.replace(
                    markers[-1] + "\n",
                    markers[-1]
                    + "\nCORE_PIPELINE_MAKE_VARIABLE|EXTRA|0|command line\n",
                ),
            ),
            (
                "markers-after-compile",
                baseline.splitlines()[-1]
                + "\n"
                + "\n".join(markers)
                + "\n",
            ),
            (
                "host-compiler-decoy",
                "\n".join(markers)
                + "\ngcc -c source.c -o source.o "
                + " ".join(definitions)
                + "\n",
            ),
            (
                "unbound-target-compile",
                baseline + "aarch64-linux-gnu-gcc -c other.c -o other.o\n",
            ),
            (
                "printed-decoy",
                "\n".join(markers)
                + "\nprintf 'aarch64-linux-gnu-gcc -c source.c "
                + " ".join(definitions)
                + "'\n",
            ),
        ):
            with self.subTest(label=label):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        changed_log, variables, "arm64"
                    )
                )
        for definition in definitions:
            with self.subTest(missing_definition=definition):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        baseline.replace(" " + definition, "", 1),
                        variables,
                        "arm64",
                    )
                )
        for hostile in (
            "-DARCH_ARM=1",
            "-UARCH_ARM",
            "-Wp,-D,ARCH_ARM=1",
            "-Xpreprocessor -D -Xpreprocessor ARCH_ARM=1",
            "@compiler-options.rsp",
            "-DHAVE_SSA=0",
            "-DHAVE_OPENGL",
            "-DHAVE_OPENGLES=1",
            "-Wp,-DHAVE_GL_FFT=1",
            "-DOPENGL=0",
            "-D OPENGL=1",
            "-Wp,-D,OPENGL=0",
            "-Wp,-DOPENGL=1",
            "-Xpreprocessor -DOPENGL=0",
        ):
            with self.subTest(hostile=hostile):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        baseline.rstrip() + " " + hostile + "\n",
                        variables,
                        "arm64",
                    )
                )

        accepted = [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libgcc_s.so.1",
            "libm.so.6",
            "libpthread.so.0",
            "libstdc++.so.6",
            "libavahi-client.so.3",
        ]
        self.assertEqual(
            [
                "libEGL",
                "libGL",
                "libIMG",
                "libOpenGL",
                "libass",
                "libavcodec",
                "libavdevice",
                "libavfilter",
                "libavformat",
                "libavresample",
                "libavutil",
                "libglslcompiler",
                "libpostproc",
                "libpvr",
                "libsrv",
                "libswresample",
                "libswscale",
                "libusc",
                "libvulkan",
            ],
            pipeline.validated_forbidden_needed_prefixes(spec),
        )
        forbidden = [
            "libEGL.so.1",
            "libGL.so.1",
            "libGLESv2.so.2",
            "libIMGegl.so",
            "libOpenGL.so.0",
            "libass.so.9",
            "libavcodec.so.56",
            "libavdevice.so.56",
            "libavfilter.so.5",
            "libavformat.so.56",
            "libavresample.so.2",
            "libavutil.so.54",
            "libglslcompiler.so",
            "libpostproc.so.53",
            "libpvrPVR2D.so",
            "libsrv_um.so",
            "libswresample.so.1",
            "libswscale.so.3",
            "libusc.so",
            "libvulkan.so.1",
        ]
        self.assertEqual(
            sorted(forbidden),
            pipeline.forbidden_needed_dependencies(spec, accepted + forbidden),
        )
        self.assertEqual([], pipeline.forbidden_needed_dependencies(spec, accepted))



    def test_uzem_native_version_recipe_is_exact_and_normalized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["uzem"]
        expected_git_version = {
            "derivation": "native-space-short7-v1",
            "value": " d4fe82c",
        }
        self.assertEqual(
            {
                "workflow": ".github/workflows/build-uzem.yml",
                "source": {
                    "url": "https://github.com/libretro/libretro-uzem.git",
                    "requested_ref": "refs/heads/master",
                    "commit": "d4fe82c38bf3fc789b955bcfcc81dc2e3a2ea89f",
                    "tree": "949f7cb3c2f61295335ea59e35e7d9f031693ac1",
                },
                "build": {
                    "driver": "libretro-super",
                    "source_key": "uzem",
                    "source_dir": "libretro-uzem",
                    "output_path": "dist/unix/uzem_libretro.so",
                    "artifact_name": "uzem_libretro.so",
                    "git_version": expected_git_version,
                },
                "metadata": {
                    "source_path": "/libretro-super/dist/info/uzem_libretro.info",
                    "artifact_name": "uzem_libretro.info",
                },
                "targets": ["arm64", "armhf"],
            },
            spec,
        )
        self.assertTrue(pipeline.uzem_native_git_version_spec_is_well_formed(spec))
        self.assertEqual(expected_git_version, pipeline.validated_git_version(spec))
        self.assertEqual(
            ['CORE_PIPELINE_NATIVE_GIT_VERSION|" d4fe82c"|file'],
            pipeline.git_version_log_markers(spec),
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

    def test_uzem_catalog_identity_and_contract_copy_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")

        def mutation(label: str, mutate) -> tuple[str, dict]:
            changed = copy.deepcopy(catalog)
            mutate(changed)
            return label, changed

        mutations = (
            mutation(
                "source-identity",
                lambda changed: changed["cores"]["uzem"]["source"].update(
                    {"tree": "a" * 40}
                ),
            ),
            mutation(
                "workflow-identity",
                lambda changed: changed["cores"]["uzem"].update(
                    {"workflow": ".github/workflows/build-vemulator.yml"}
                ),
            ),
            mutation(
                "missing-version",
                lambda changed: changed["cores"]["uzem"]["build"].pop(
                    "git_version"
                ),
            ),
            mutation(
                "hyphen-version",
                lambda changed: changed["cores"]["uzem"]["build"][
                    "git_version"
                ].update(
                    {
                        "derivation": "hyphen-short7-v1",
                        "value": "-d4fe82c",
                    }
                ),
            ),
            mutation(
                "wrong-native-version",
                lambda changed: changed["cores"]["uzem"]["build"][
                    "git_version"
                ].update({"value": " 0000000"}),
            ),
            mutation(
                "native-compiler-scope",
                lambda changed: changed["cores"]["uzem"]["build"][
                    "git_version"
                ].update({"compiler_scope": "cxx"}),
            ),
            mutation(
                "extra-build-key",
                lambda changed: changed["cores"]["uzem"]["build"].update(
                    {"source_date_epoch": 1}
                ),
            ),
            mutation(
                "extra-metadata-key",
                lambda changed: changed["cores"]["uzem"]["metadata"].update(
                    {"extra": True}
                ),
            ),
            mutation(
                "extra-spec-key",
                lambda changed: changed["cores"]["uzem"].update(
                    {"validation": {"forbidden_needed_prefixes": []}}
                ),
            ),
            mutation(
                "target-shape",
                lambda changed: changed["cores"]["uzem"].update(
                    {"targets": ["arm64"]}
                ),
            ),
            mutation(
                "native-contract-copied-to-vemulator",
                lambda changed: changed["cores"]["vemulator"]["build"].update(
                    {
                        "git_version": {
                            "derivation": "native-space-short7-v1",
                            "value": " 7fade95",
                        }
                    }
                ),
            ),
            mutation(
                "native-only-vecx",
                lambda changed: changed["cores"]["vecx"]["build"].pop(
                    "make_variables"
                ),
            ),
            mutation(
                "native-plus-make-uzem",
                lambda changed: changed["cores"]["uzem"]["build"].update(
                    {"make_variables": {"HAS_GPU": 0}}
                ),
            ),
        )
        for label, changed in mutations:
            with self.subTest(label=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validate_catalog(changed)

    def test_uzem_native_version_log_proof_binds_all_c_and_cxx_compiles(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["uzem"]
        contract = spec["build"]["git_version"]
        marker = pipeline.git_version_log_markers(spec)[0]
        version_token = r'-DGIT_VERSION=\"" d4fe82c"\"'
        compilers = {
            "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
            "armhf": (
                "arm-a30-linux-gnueabihf-gcc",
                "arm-a30-linux-gnueabihf-g++",
            ),
        }

        def valid_log(arch: str) -> str:
            c_compiler, cxx_compiler = compilers[arch]
            return (
                f"{marker}\n"
                f"{c_compiler} {version_token} -c source.c -o source.o\n"
                f"{cxx_compiler} {version_token} -c source.cpp -o source-cxx.o\n"
            )

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
        compile_lines = baseline.splitlines()[1:]
        mutations = {
            "malformed-command": baseline
            + "aarch64-linux-gnu-gcc 'unterminated\n",
            "missing-marker": baseline.replace(marker + "\n", "", 1),
            "duplicate-marker": marker + "\n" + baseline,
            "late-marker": "\n".join([compile_lines[0], marker, compile_lines[1]])
            + "\n",
            "wrong-origin": baseline.replace("|file", "|environment", 1),
            "wrong-value": baseline.replace(" d4fe82c", " 0000000"),
            "unquoted-value": baseline.replace(
                version_token, "-DGIT_VERSION=d4fe82c", 1
            ),
            "conflicting-value": baseline.replace(
                version_token,
                version_token + r' -DGIT_VERSION=\"" 0000000"\"',
                1,
            ),
            "response-file": baseline.replace(
                " -c source.c", " @compiler-options.rsp -c source.c", 1
            ),
            "partial-compile-proof": baseline.replace(
                " " + version_token, "", 1
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


    def test_git_version_is_exact_commit_derived_and_recursively_injected(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        changed = copy.deepcopy(catalog)
        core_id = "quicknes"
        spec = changed["cores"][core_id]
        unscoped = {
            "derivation": "hyphen-short7-v1",
            "value": "-26bb785",
        }
        expected = {**unscoped, "compiler_scope": "cxx"}
        spec["build"]["git_version"] = expected
        pipeline.validate_catalog(changed)
        self.assertEqual(expected, pipeline.validated_git_version(spec))
        self.assertEqual(
            expected,
            pipeline.normalized_build_contract(spec, "arm64")["git_version"],
        )
        self.assertTrue(
            pipeline.git_version_contract_is_well_formed(
                unscoped, spec["source"]["commit"]
            )
        )
        self.assertTrue(
            pipeline.git_version_contract_is_well_formed(
                expected, spec["source"]["commit"]
            )
        )

        script = pipeline.container_build_script(
            core_id, "arm64", spec, changed["resolver"]
        )
        unset_index = script.index("unset CFLAGS")
        export_index = script.index("export MAKEFLAGS=GIT_VERSION=-26bb785")
        origin_index = script.index("core_pipeline_git_version_origin")
        build_index = script.index("./libretro-build.sh quicknes")
        self.assertLess(unset_index, export_index)
        self.assertLess(export_index, origin_index)
        self.assertLess(origin_index, build_index)
        unset_variables = set(
            next(
                line for line in script.splitlines() if line.startswith("unset ")
            ).split()[1:]
        )
        self.assertIn("GIT_VERSION", unset_variables)
        self.assertEqual(
            [
                "CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION=-26bb785",
                "CORE_PIPELINE_GIT_VERSION|-26bb785|command line",
            ],
            pipeline.git_version_log_markers(spec),
        )

        schema = json.loads(
            (ROOT / "manifests" / "core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            ["derivation", "value"], schema["$defs"]["gitVersion"]["required"]
        )
        self.assertEqual(
            "cxx",
            schema["$defs"]["gitVersion"]["properties"]["compiler_scope"][
                "const"
            ],
        )
        self.assertFalse(schema["$defs"]["gitVersion"]["additionalProperties"])
        git_condition = schema["$defs"]["core"]["properties"]["build"]["allOf"][0]
        self.assertEqual(["git_version"], git_condition["if"]["required"])

        def invalid_git_version(value: object) -> dict:
            invalid = copy.deepcopy(catalog)
            invalid["cores"][core_id]["build"]["git_version"] = value
            return invalid

        malformed = [
            ("array", invalid_git_version([]), "must be an object"),
            (
                "missing",
                invalid_git_version({"derivation": "hyphen-short7-v1"}),
                "exactly derivation and value",
            ),
            (
                "extra",
                invalid_git_version({**expected, "extra": True}),
                "exactly derivation and value",
            ),
            (
                "derivation",
                invalid_git_version({**expected, "derivation": "git-describe"}),
                "derivation must be",
            ),
            (
                "wrong-prefix",
                invalid_git_version({**expected, "value": "-0000000"}),
                "first seven source commit",
            ),
            (
                "unsafe",
                invalid_git_version({**expected, "value": "-26bb785 dirty"}),
                "first seven source commit",
            ),
            (
                "compiler-scope",
                invalid_git_version({**expected, "compiler_scope": "all"}),
                "compiler_scope must be cxx",
            ),
            (
                "null-compiler-scope",
                invalid_git_version({**expected, "compiler_scope": None}),
                "compiler_scope must be cxx",
            ),
        ]
        wrong_driver = invalid_git_version(expected)
        wrong_driver["cores"][core_id]["build"]["driver"] = "direct-make"
        malformed.append(("driver", wrong_driver, "requires driver libretro-super"))
        with_definitions = invalid_git_version(expected)
        with_definitions["cores"][core_id]["build"]["compile_definitions"] = {
            "arm64": ["SAFE=1"]
        }
        malformed.append(
            ("compile-definitions", with_definitions, "cannot be combined")
        )
        with_make_variables = invalid_git_version(expected)
        ffmpeg_build = catalog["cores"]["ffmpeg"]["build"]
        with_make_variables["cores"][core_id]["build"]["make_variables"] = (
            copy.deepcopy(ffmpeg_build["make_variables"])
        )
        malformed.append(("make-variables", with_make_variables, "cannot be combined"))
        for label, invalid, message in malformed:
            with self.subTest(label=label), self.assertRaisesRegex(
                pipeline.PipelineError, message
            ):
                pipeline.validate_catalog(invalid)

    def test_git_version_log_proof_requires_origin_and_exact_compile_token(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = copy.deepcopy(catalog["cores"]["quicknes"])
        contract = {
            "derivation": "hyphen-short7-v1",
            "value": "-26bb785",
        }
        spec["build"]["git_version"] = contract
        markers = pipeline.git_version_log_markers(spec)
        compilers = {
            "arm64": "aarch64-linux-gnu-g++",
            "armhf": "arm-a30-linux-gnueabihf-g++",
        }
        compile_token = r'-DGIT_VERSION=\"-26bb785\"'

        def valid_log(arch: str) -> str:
            return (
                "\n".join(markers)
                + f"\n{compilers[arch]} -c source.cpp -o source.o {compile_token}\n"
            )

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
        compile_line = baseline.splitlines()[-1]
        mutations = {
            "environment-origin": baseline.replace("|command line", "|environment"),
            "duplicate-marker": markers[0] + "\n" + baseline,
            "markers-after-compile": compile_line + "\n" + "\n".join(markers) + "\n",
            "missing-token": baseline.replace(" " + compile_token, ""),
            "wrong-value": baseline.replace("-26bb785", "-0000000", 1),
            "unquoted-value": baseline.replace(compile_token, "-DGIT_VERSION=-26bb785"),
            "host-decoy": "\n".join(markers)
            + f"\ng++ -c source.cpp -o source.o {compile_token}\n",
            "response-file": baseline.rstrip() + " @compiler-options.rsp\n",
            "conflicting-token": baseline.rstrip() + " -DGIT_VERSION=\"-0000000\"\n",
            "unbound-second-compile": baseline
            + "aarch64-linux-gnu-g++ -c other.cpp -o other.o\n",
            "obfuscated-unbound-second-compile": baseline
            + 'aarch64-linux-gnu-g""++ -""c other.cpp -o other.o\n',
        }
        for label, mutated in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        mutated,
                        contract,
                        spec["source"]["commit"],
                        "arm64",
                    )
                )

        scoped_contract = {**contract, "compiler_scope": "cxx"}
        scoped_markers = pipeline.git_version_markers(
            scoped_contract, spec["source"]["commit"]
        )
        scoped_baseline = (
            "\n".join(scoped_markers)
            + "\naarch64-linux-gnu-gcc -c source.c -o source.o\n"
            + "aarch64-linux-gnu-g++ -c source.cpp -o source-cxx.o "
            + compile_token
            + "\n"
        )
        self.assertTrue(
            pipeline.git_version_log_proves_contract(
                scoped_baseline,
                scoped_contract,
                spec["source"]["commit"],
                "arm64",
            )
        )
        scoped_mutations = {
            "version-on-c-compile": scoped_baseline.replace(
                "source.c -o source.o",
                f"source.c -o source.o {compile_token}",
            ),
            "missing-on-cxx-compile": scoped_baseline.replace(
                " " + compile_token, "", 1
            ),
            "duplicate-on-cxx-compile": scoped_baseline.replace(
                compile_token, f"{compile_token} {compile_token}", 1
            ),
            "no-cxx-compile": "\n".join(scoped_markers)
            + "\naarch64-linux-gnu-gcc -c source.c -o source.o\n",
        }
        for label, mutated in scoped_mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        mutated,
                        scoped_contract,
                        spec["source"]["commit"],
                        "arm64",
                    )
                )
        self.assertFalse(
            pipeline.git_version_log_proves_contract(
                scoped_baseline,
                contract,
                spec["source"]["commit"],
                "arm64",
            )
        )

    def test_build_equivalence_excludes_only_run_local_log_identity(self) -> None:
        selected = {
            "driver": "direct-cmake",
            "environment": "sanitized-v1",
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        reproduced = {**selected, "log_sha256": "b" * 64}
        self.assertEqual(
            pipeline._build_equivalence_identity(selected),
            pipeline._build_equivalence_identity(reproduced),
        )

        for field, value in (
            ("driver", "direct-make"),
            ("environment", "unsanitized"),
            ("log", "other.log"),
        ):
            with self.subTest(field=field):
                changed = {**reproduced, field: value}
                self.assertNotEqual(
                    pipeline._build_equivalence_identity(selected),
                    pipeline._build_equivalence_identity(changed),
                )

    def test_output_sync_makeflag_is_scoped_to_portable_ffmpeg(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        ffmpeg = catalog["cores"]["ffmpeg"]["build"]["make_variables"]
        self.assertEqual(
            "--output-sync=recurse ",
            pipeline.make_output_sync_prefix(ffmpeg),
        )
        # Every other make-variable core keeps its frozen recipe (empty prefix),
        # so this change does not disturb their already-promoted goldens.
        for core_id, spec in catalog["cores"].items():
            make_variables = spec["build"].get("make_variables")
            if make_variables is None or core_id == "ffmpeg":
                continue
            self.assertEqual(
                "", pipeline.make_output_sync_prefix(make_variables), core_id
            )

    def test_swanstation_direct_cmake_contract_is_exact_and_target_scoped(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["swanstation"]
        patch_path = "patches/swanstation/openbios-cmake-3.16.patch"
        overlay = {
            "kind": "git-apply-v1",
            "patch_path": patch_path,
            "patch_sha256": "4cfef36e9516b30853c9f23b1886821ffe21a25769abddd4246310a19e85f423",
            "source_path": "dep/openbios/CMakeLists.txt",
            "preimage_sha256": "df18f952f03c19525a82ac485cc19abcf360f25d452336b993983a80ae63b870",
            "postimage_sha256": "8c84dfdb832ce0c1440d9db3ed2e8d95df4359f6032727389cc4d760a50756b3",
        }
        self.assertEqual(
            "c902d31b76bd3919758851e87b0adf1607601c82",
            spec["source"]["tree"],
        )
        self.assertEqual(1782767217, spec["build"]["source_date_epoch"])
        self.assertEqual([overlay], spec["build"]["overlays"]["arm64"])
        self.assertNotIn("armhf", spec["build"]["overlays"])
        self.assertEqual(
            overlay["patch_sha256"], pipeline.sha256_file(ROOT / patch_path)
        )

        # swanstation is arm64-only: the spruceOS-shipped armhf baseline is an
        # invalid ELF64 binary and its device policy marks armhf not-consumed,
        # so armhf is not a build target and cmake.systems covers only arm64.
        self.assertEqual(["arm64"], spec["targets"])
        self.assertEqual({"arm64"}, set(spec["build"]["cmake"]["systems"]))
        arm64_contract = pipeline.normalized_build_contract(spec, "arm64")
        self.assertEqual([overlay], arm64_contract["overlays"])
        self.assertEqual(
            {"name": "Linux", "processor": "aarch64"},
            arm64_contract["cmake"]["system"],
        )

        arm64_script = pipeline.container_build_script(
            "swanstation", "arm64", spec, catalog["resolver"]
        )
        for arch, processor, script in (
            ("arm64", "aarch64", arm64_script),
        ):
            self.assertIn("mkdir /tmp/core-source", script)
            self.assertNotIn("/tmp/swanstation", script)
            self.assertIn("-B /tmp/core-build", script)
            self.assertIn("-G 'Unix Makefiles'", script)
            self.assertIn("-DCMAKE_BUILD_TYPE:STRING=Release", script)
            self.assertIn("-DCMAKE_SYSTEM_NAME:STRING=Linux", script)
            self.assertIn(
                f"-DCMAKE_SYSTEM_PROCESSOR:STRING={processor}", script
            )
            for variable in (
                "C_COMPILER",
                "CXX_COMPILER",
                "AR",
                "RANLIB",
                "STRIP",
            ):
                self.assertIn(f"-DCMAKE_{variable}:FILEPATH=", script)
            self.assertIn("--target swanstation_libretro", script)
            self.assertIn("/tmp/core-build/swanstation_libretro.so", script)
            configure_index = script.index("cmake -S /tmp/core-source")
            cache_check_index = script.index("require_cmake_cache_entry CMAKE_BUILD_TYPE")
            cache_marker_index = script.index("CORE_PIPELINE_CMAKE_CACHE_V1=")
            contract_marker_index = script.index("CORE_PIPELINE_CMAKE_CONTRACT_V1=")
            epoch_index = script.index("actual_source_date_epoch=")
            overlay_marker = (
                "CORE_PIPELINE_OVERLAY_V1_PRE="
                if arch == "arm64"
                else "CORE_PIPELINE_OVERLAY_V1_NONE="
            )
            overlay_index = script.index(overlay_marker)
            build_index = script.index("cmake --build /tmp/core-build")
            self.assertLess(epoch_index, overlay_index)
            self.assertLess(overlay_index, configure_index)
            self.assertLess(configure_index, cache_check_index)
            self.assertLess(cache_check_index, cache_marker_index)
            self.assertLess(cache_marker_index, contract_marker_index)
            self.assertLess(contract_marker_index, build_index)
            self.assertIn('cmake_cc="$(command -v "$CC")"', script)
            self.assertIn('CMAKE_C_COMPILER:FILEPATH="$cmake_cc"', script)
            self.assertIn('CMAKE_CXX_COMPILER:FILEPATH="$cmake_cxx"', script)
            self.assertIn(
                'require_cmake_cache_tool_path CMAKE_C_COMPILER "$cmake_cc"',
                script,
            )
            self.assertIn(
                'require_cmake_cache_tool_path CMAKE_CXX_COMPILER "$cmake_cxx"',
                script,
            )
            self.assertIn('$1:FILEPATH=$2', script)
            self.assertIn('$1:STRING=$2', script)
            self.assertIn(
                "CMAKE_HOME_DIRECTORY:INTERNAL=/tmp/core-source", script
            )
            self.assertIn(
                "CMAKE_CACHEFILE_DIR:INTERNAL=/tmp/core-build", script
            )
            self.assertNotIn("./libretro-build.sh swanstation", script)
            self.assertNotIn("./libretro-fetch.sh swanstation", script)

        self.assertIn("CORE_PIPELINE_OVERLAY_V1_PRE=", arm64_script)
        self.assertIn("CORE_PIPELINE_OVERLAY_V1_POST=", arm64_script)
        self.assertIn("apply --check --whitespace=error-all", arm64_script)
        self.assertIn("apply --whitespace=error-all", arm64_script)
        self.assertIn("diff --check", arm64_script)
        self.assertIn("diff --name-only -z", arm64_script)
        self.assertIn("cmp /tmp/expected-overlay-paths", arm64_script)
        self.assertLess(
            arm64_script.index("cmp /tmp/expected-overlay-paths"),
            arm64_script.index("CORE_PIPELINE_OVERLAY_V1_PRE="),
        )
        arm64_mounts = pipeline.direct_cmake_overlay_mount_args(spec, "arm64")
        self.assertEqual("-v", arm64_mounts[0])
        self.assertEqual(
            f"{ROOT / patch_path}:/recipe-overlays/0.patch:ro", arm64_mounts[1]
        )

        for arch in ("arm64",):
            tool_paths = {
                role: f"/fixture/bin/{name}"
                for role, name in pipeline.TARGET_CMAKE_TOOL_NAMES[arch].items()
            }
            markers = pipeline.direct_cmake_log_markers(spec, arch, tool_paths)
            valid_log = "\n".join(markers) + "\n"
            self.assertTrue(
                pipeline.direct_cmake_log_proves_contract(valid_log, spec, arch)
            )
            self.assertFalse(
                pipeline.direct_cmake_log_proves_contract(
                    valid_log + markers[-1] + "\n", spec, arch
                )
            )
            self.assertFalse(
                pipeline.direct_cmake_log_proves_contract(
                    "\n".join(reversed(markers)) + "\n", spec, arch
                )
            )
            marker_only = "\n".join(
                pipeline.direct_cmake_log_markers(spec, arch)
            ) + "\n"
            self.assertFalse(
                pipeline.direct_cmake_log_proves_contract(marker_only, spec, arch)
            )
            mismatched_cache = valid_log.replace(
                f'"processor":"{pipeline.normalized_build_contract(spec, arch)["cmake"]["system"]["processor"]}"',
                '"processor":"mismatched"',
                1,
            )
            self.assertFalse(
                pipeline.direct_cmake_log_proves_contract(
                    mismatched_cache, spec, arch
                )
            )

    def test_swanstation_direct_cmake_catalog_tampering_fails_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        mutations = []
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["cmake"]["generator"] = "Ninja"
        mutations.append(("generator", changed, "generator"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["cmake"]["systems"]["arm64"][
            "processor"
        ] = "arm"
        mutations.append(("processor", changed, "target system"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["cmake"]["extra"] = True
        mutations.append(("extra-cmake", changed, "exact direct-CMake fields"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["artifact_name"] = "other.so"
        mutations.append(("artifact", changed, "must equal"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["overlays"]["arm64"][0][
            "patch_path"
        ] = "patches/other/openbios.patch"
        mutations.append(("scope", changed, "core-scoped"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["overlays"]["arm64"][0][
            "patch_sha256"
        ] = "0" * 64
        mutations.append(("patch-digest", changed, "does not match"))
        changed = copy.deepcopy(catalog)
        overlay = changed["cores"]["swanstation"]["build"]["overlays"]["arm64"][0]
        overlay["postimage_sha256"] = overlay["preimage_sha256"]
        mutations.append(("same-image", changed, "must differ"))
        changed = copy.deepcopy(catalog)
        overlays = changed["cores"]["swanstation"]["build"]["overlays"]["arm64"]
        second = copy.deepcopy(overlays[0])
        second["source_path"] = "aaa/CMakeLists.txt"
        second["patch_path"] = "patches/swanstation/aaa.patch"
        overlays.append(second)
        mutations.append(("sort", changed, "sorted by source_path"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["overlays"]["arm64"][0][
            "extra"
        ] = "ignored"
        mutations.append(("extra-overlay", changed, "exact overlay fields"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["cmake"]["systems"].pop(
            "arm64"
        )
        mutations.append(("missing-system", changed, "exactly cover"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["cmake"]["target"] = "bad target"
        mutations.append(("unsafe-target", changed, "safe target"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["output_path"] = "../core.so"
        mutations.append(("unsafe-output", changed, "exact relative path"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["source_dir"] = "../source"
        mutations.append(("unsafe-source", changed, "source_dir is invalid"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["build"]["overlays"]["arm64"][0][
            "patch_path"
        ] = "patches/swanstation/../escape.patch"
        mutations.append(("unsafe-patch", changed, "exact relative path"))
        changed = copy.deepcopy(catalog)
        duplicate_overlays = changed["cores"]["swanstation"]["build"]["overlays"][
            "arm64"
        ]
        duplicate_overlays.append(copy.deepcopy(duplicate_overlays[0]))
        mutations.append(("duplicate-overlay", changed, "repeats an overlay path"))
        changed = copy.deepcopy(catalog)
        policy = changed["cores"]["swanstation"]["validation"][
            "forbidden_needed_prefixes"
        ]
        policy.reverse()
        mutations.append(("unsorted-policy", changed, "sorted unique"))
        changed = copy.deepcopy(catalog)
        changed["cores"]["swanstation"]["validation"][
            "forbidden_needed_prefixes"
        ] = ["not a library"]
        mutations.append(("unsafe-policy", changed, "unsafe token"))
        for label, changed, message in mutations:
            with self.subTest(label=label), self.assertRaisesRegex(
                pipeline.PipelineError, message
            ):
                pipeline.validate_catalog(changed)

        spec = catalog["cores"]["swanstation"]
        for output, message in (
            ("-\t-\tdep/openbios/CMakeLists.txt\0", "binary"),
            (
                "1\t1\tdep/openbios/CMakeLists.txt\0"
                "1\t1\tother/path.txt\0",
                "more than one path",
            ),
        ):
            with self.subTest(numstat=message), mock.patch.object(
                pipeline,
                "run",
                return_value=argparse.Namespace(stdout=output),
            ), self.assertRaisesRegex(pipeline.PipelineError, message):
                pipeline.validated_direct_cmake(spec)

    def test_swanstation_dependency_policy_rejects_gui_and_driver_families(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["swanstation"]
        accepted = [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libdl.so.2",
            "libgcc_s.so.1",
            "libm.so.6",
            "libpthread.so.0",
            "librt.so.1",
            "libstdc++.so.6",
        ]
        self.assertEqual([], pipeline.forbidden_needed_dependencies(spec, accepted))
        forbidden = [
            "libEGL_mesa.so.0",
            "libGL.so.1",
            "libGLESv2.so.2",
            "libGLX.so.0",
            "libOpenGL.so.0",
            "libQt6Core.so.6",
            "libSDL2.so.0",
            "libX11.so.6",
            "libvulkan_radeon.so",
            "libwayland-client.so.0",
            "libxcb.so.1",
            "libxkbcommon.so.0",
        ]
        self.assertEqual(
            forbidden,
            pipeline.forbidden_needed_dependencies(spec, accepted + forbidden),
        )
        validation = pipeline.apply_artifact_dependency_policy(
            {"status": "valid", "errors": [], "needed": accepted + forbidden},
            spec,
        )
        self.assertEqual("invalid", validation["status"])
        self.assertIn("forbidden dynamic dependencies", validation["errors"][0])

    def test_catalog_binds_the_exact_portable_toolchain_lock(self) -> None:
        """The lock/validator digests move when the Dockerfile is re-pinned.

        The archive digests below must NOT move with them: they identify the
        image bytes, and re-pinning the Dockerfile documents that image rather
        than rebuilding it.
        """

        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        self.assertEqual(2, catalog["schema_version"])
        reference = catalog["toolchain_lock"]
        self.assertEqual("pins/toolchains/local-cache-v1.json", reference["path"])
        self.assertEqual(
            "7606e9357490f451df4374d38aad73a0426e3bb956a732dcaaa6b32393ee8639",
            reference["file_sha256"],
        )
        self.assertEqual(
            "253f7d84cc71fa859553fa05fab4c2356b842196104953b092501850c217a794",
            reference["content_sha256"],
        )
        self.assertEqual(
            {
                "path": "scripts/toolchain_archive.py",
                "sha256": "b2493119922f6a83b341be34d217f45b63ac4befc98cd76065c097d42e943f8c",
            },
            catalog["toolchain_lock_validator"],
        )
        expected = {
            "arm64": (
                "cores-arm64.tar.gz",
                "8a3bdd7f36a10a092209cd8f308d2d2a85e316be7ede6d42562074243b25bc64",
                502531978,
            ),
            "armhf": (
                "cores-armhf.tar.gz",
                "f297cbf988aeb15c3de90c1bc900494aaf4214320aa5fcfa2cbbf10d2e32f16e",
                835303648,
            ),
        }
        for architecture, (filename, digest, size) in expected.items():
            provenance = pipeline.expected_archive_provenance(catalog, architecture)
            self.assertEqual(architecture, provenance["architecture"])
            self.assertEqual(reference, provenance["lock"])
            self.assertEqual(
                catalog["toolchain_lock_validator"], provenance["validator"]
            )
            self.assertEqual(
                {"filename": filename, "sha256": digest, "size": size},
                provenance["archive"],
            )

    def test_catalog_rejects_lock_reference_and_toolchain_mapping_drift(self) -> None:
        current = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8")
        )
        mutations = []
        for field, value in (
            ("path", "../outside.json"),
            ("schema_version", True),
            ("lock_id", "other"),
            ("file_sha256", 7),
            ("file_sha256", "0" * 64),
            ("content_sha256", 7),
            ("content_sha256", "0" * 64),
        ):
            changed = copy.deepcopy(current)
            changed["toolchain_lock"][field] = value
            mutations.append((f"lock-{field}", changed))
        for field, value in (
            ("image", "wrong:latest"),
            ("image_id", f"sha256:{'0' * 64}"),
            ("dockerfile", "Dockerfile.armhf"),
            ("dockerfile_sha256", "0" * 64),
            ("dockerfile_linkage", "verified"),
        ):
            changed = copy.deepcopy(current)
            changed["toolchains"]["arm64"][field] = value
            mutations.append((f"arm64-{field}", changed))
        changed = copy.deepcopy(current)
        changed["schema_version"] = True
        mutations.append(("catalog-schema-bool", changed))
        for field, value in (
            ("path", "scripts/other.py"),
            ("sha256", 7),
            ("sha256", "0" * 64),
        ):
            changed = copy.deepcopy(current)
            changed["toolchain_lock_validator"][field] = value
            mutations.append((f"validator-{field}-{value!r}", changed))
        for label, changed in mutations:
            with self.subTest(label=label), self.assertRaises(pipeline.PipelineError):
                pipeline.validate_catalog(changed)

    def test_catalog_uses_the_complete_normative_lock_validator(self) -> None:
        catalog = json.loads(
            (ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8")
        )
        lock = json.loads(
            (ROOT / catalog["toolchain_lock"]["path"]).read_text(encoding="utf-8")
        )
        lock["toolchains"]["arm64"]["archive"]["format"] = "untrusted-format"
        lock["content_sha256"] = pipeline.toolchain_lock_content_sha256(lock)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "Dockerfile.arm64",
                "Dockerfile.armhf",
                catalog["toolchain_lock_validator"]["path"],
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())
            lock_path = root / catalog["toolchain_lock"]["path"]
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            catalog["toolchain_lock"]["content_sha256"] = lock["content_sha256"]
            catalog["toolchain_lock"]["file_sha256"] = pipeline.sha256_file(lock_path)
            with mock.patch.object(pipeline, "ROOT", root), self.assertRaisesRegex(
                pipeline.PipelineError, "archive metadata mismatch"
            ):
                pipeline.load_catalog_toolchain_lock(catalog)

    def test_catalog_executes_the_digest_verified_validator_snapshot_after_swap(
        self,
    ) -> None:
        catalog = pipeline.load_json(ROOT / "manifests" / "core-builds.json")
        validator_relative = catalog["toolchain_lock_validator"]["path"]
        validator_source = (ROOT / validator_relative).read_bytes()
        replacement = b'raise RuntimeError("replacement validator executed")\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "Dockerfile.arm64",
                "Dockerfile.armhf",
                "Dockerfile.rust",
                catalog["toolchain_lock"]["path"],
                validator_relative,
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())

            validator_path = root / validator_relative
            captured_sources: list[bytes] = []
            real_loader = pipeline.load_toolchain_archive_validator

            def swap_before_execution(path: Path, source: bytes):
                self.assertEqual(validator_path, path)
                captured_sources.append(source)
                path.write_bytes(replacement)
                return real_loader(path, source)

            with mock.patch.object(
                pipeline, "ROOT", root
            ), mock.patch.object(
                pipeline,
                "load_toolchain_archive_validator",
                side_effect=swap_before_execution,
            ):
                document, lock_path, loaded_validator_path = (
                    pipeline.load_catalog_toolchain_lock(catalog)
                )

            self.assertEqual("local-cache-v1", document["lock_id"])
            self.assertEqual(root / catalog["toolchain_lock"]["path"], lock_path)
            self.assertEqual(validator_path, loaded_validator_path)
            self.assertEqual([validator_source], captured_sources)
            self.assertEqual(replacement, validator_path.read_bytes())

    def test_catalog_validates_the_digest_verified_toolchain_lock_snapshot_after_swap(
        self,
    ) -> None:
        catalog = pipeline.load_json(ROOT / "manifests" / "core-builds.json")
        validator_relative = catalog["toolchain_lock_validator"]["path"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "Dockerfile.arm64",
                "Dockerfile.armhf",
                "Dockerfile.rust",
                catalog["toolchain_lock"]["path"],
                validator_relative,
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())

            lock_path = root / catalog["toolchain_lock"]["path"]
            replacement = b'{"replacement":true}\n'
            real_loader = pipeline.load_toolchain_archive_validator

            def swap_before_validation(path: Path, source: bytes):
                lock_path.write_bytes(replacement)
                return real_loader(path, source)

            with mock.patch.object(
                pipeline, "ROOT", root
            ), mock.patch.object(
                pipeline,
                "load_toolchain_archive_validator",
                side_effect=swap_before_validation,
            ):
                document, loaded_lock_path, _validator_path = (
                    pipeline.load_catalog_toolchain_lock(catalog)
                )

            self.assertEqual("local-cache-v1", document["lock_id"])
            self.assertEqual(lock_path, loaded_lock_path)
            self.assertEqual(replacement, lock_path.read_bytes())

    def test_authoritative_pin_index_reuses_one_exact_catalog_snapshot(self) -> None:
        catalog = {"cores": {"alpha": {}}}
        catalog_digest = "a" * 64
        admitted_catalogs: list[object] = []

        def fake_index(_root, *, pin_validator):
            for suffix in ("one", "two"):
                pin_validator({}, Path(f"{suffix}.json"))
            return {"admitted": {}}

        def fake_report(_document, _path, *, catalog):
            admitted_catalogs.append(catalog)
            return {"status": "valid", "errors": []}

        with mock.patch.object(
            pipeline,
            "load_catalog_with_sha256",
            return_value=(catalog, catalog_digest),
        ) as load_catalog, mock.patch.object(
            pipeline,
            "load_core_pin_index",
            side_effect=fake_index,
        ), mock.patch.object(
            pipeline,
            "_authoritative_core_track_pin_report",
            side_effect=fake_report,
        ), mock.patch.object(
            pipeline,
            "load_json_with_sha256",
            return_value=(catalog, catalog_digest),
        ) as final_read:
            index = pipeline.load_authoritative_core_pin_index()

        self.assertEqual({"admitted": {}}, index)
        load_catalog.assert_called_once_with(pipeline.DEFAULT_CATALOG)
        final_read.assert_called_once_with(pipeline.DEFAULT_CATALOG)
        self.assertEqual(2, len(admitted_catalogs))
        self.assertTrue(all(item is catalog for item in admitted_catalogs))

    def test_public_authoritative_pin_report_binds_exact_path_bytes(self) -> None:
        pin_path = (
            ROOT
            / "pins"
            / "core-sets"
            / "uzem-d4fe82c38bf3-34eca38274ae.json"
        )
        document = pipeline.load_json(pin_path)
        forged = copy.deepcopy(document)
        forged["created_at"] = "2099-01-01T00:00:00+00:00"
        forged["content_sha256"] = pipeline.pin_set_content_sha256(forged)

        report = pipeline.authoritative_core_track_pin_report(forged, pin_path)

        self.assertEqual("invalid", report["status"])
        self.assertIn(
            "differs from exact path bytes",
            "\n".join(report["errors"]),
        )

    def test_authoritative_pin_index_rejects_pin_path_swap(self) -> None:
        catalog = {"cores": {"alpha": {}}}
        pin_path = Path("alpha.json")
        initial_pin = {"pin_id": "alpha-initial"}
        replacement_pin = {"pin_id": "alpha-replacement"}

        def fake_index(_root, *, pin_validator):
            report = pin_validator(initial_pin, pin_path)
            if report.get("status") != "valid":
                raise pipeline.PipelineError("; ".join(report["errors"]))
            return {"alpha": initial_pin}

        with mock.patch.object(
            pipeline,
            "load_catalog_with_sha256",
            return_value=(catalog, "c" * 64),
        ), mock.patch.object(
            pipeline,
            "load_core_pin_index",
            side_effect=fake_index,
        ), mock.patch.object(
            pipeline,
            "load_json_with_sha256",
            side_effect=[
                (initial_pin, "a" * 64),
                (replacement_pin, "b" * 64),
            ],
        ), mock.patch.object(
            pipeline,
            "_validate_pin_set_document",
            return_value={"status": "valid", "errors": []},
        ), mock.patch.object(
            pipeline,
            "require_individual_pin_identity",
            return_value=("alpha", "alpha-initial"),
        ), mock.patch.object(
            pipeline,
            "_require_pin_current_selection_authority",
        ), self.assertRaisesRegex(
            pipeline.PipelineError,
            "authoritative core pin changed during admission",
        ):
            pipeline.load_authoritative_core_pin_index()

    def test_authoritative_pin_index_rejects_catalog_swap(self) -> None:
        catalog = {"cores": {"alpha": {}}}
        with mock.patch.object(
            pipeline,
            "load_catalog_with_sha256",
            return_value=(catalog, "a" * 64),
        ), mock.patch.object(
            pipeline,
            "load_core_pin_index",
            return_value={},
        ), mock.patch.object(
            pipeline,
            "load_json_with_sha256",
            return_value=({"cores": {"replacement": {}}}, "b" * 64),
        ), self.assertRaisesRegex(
            pipeline.PipelineError,
            "catalog changed during authoritative core pin indexing",
        ):
            pipeline.load_authoritative_core_pin_index()

    def test_core_track_set_test_rejects_pin_identity_drift_after_indexing(
        self,
    ) -> None:
        pin_id = "handy-authoritative"
        pin_path = ROOT / "pins" / "core-sets" / f"{pin_id}.json"
        entry = {
            "path": str(pin_path.relative_to(ROOT)),
            "pin_id": pin_id,
            "file_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
        args = argparse.Namespace(
            catalog=pipeline.DEFAULT_CATALOG,
            pin_id=pin_id,
        )
        cases = (
            (
                "file",
                {"pin_id": pin_id, "content_sha256": "b" * 64},
                "c" * 64,
                "file identity changed",
            ),
            (
                "content",
                {"pin_id": pin_id, "content_sha256": "d" * 64},
                "a" * 64,
                "content identity changed",
            ),
        )
        for label, document, file_sha256, error in cases:
            with self.subTest(label=label), mock.patch.object(
                pipeline, "manifest_lock", return_value=mock.MagicMock()
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), mock.patch.object(
                pipeline,
                "load_authoritative_core_pin_index",
                return_value={pin_id: entry},
            ), mock.patch.object(
                pipeline, "load_json", return_value={}
            ), mock.patch.object(
                pipeline,
                "load_json_with_sha256",
                return_value=(document, file_sha256),
            ) as snapshot, mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                side_effect=AssertionError("drifted pin was validated"),
            ), mock.patch.object(
                pipeline,
                "set_core_track_test",
                side_effect=AssertionError("track registry was mutated"),
            ), mock.patch.object(
                pipeline,
                "atomic_write_json",
                side_effect=AssertionError("track registry was written"),
            ), self.assertRaisesRegex(pipeline.PipelineError, error):
                pipeline.cmd_core_track_set_test(args)
            snapshot.assert_called_once_with(pin_path)

    def test_core_track_set_test_rechecks_pin_bytes_immediately_before_mutation(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        pin_id = "handy-authoritative"
        original = (
            json.dumps(
                {"pin_id": pin_id, "content_sha256": "b" * 64},
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        replacement = b'{"pin_id":"replacement"}\n'
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            pin_path = Path(directory) / f"{pin_id}.json"
            pin_path.write_bytes(original)
            entry = {
                "path": str(pin_path.relative_to(ROOT)),
                "pin_id": pin_id,
                "file_sha256": pipeline.sha256_bytes(original),
                "content_sha256": "b" * 64,
            }
            args = argparse.Namespace(
                catalog=pipeline.DEFAULT_CATALOG,
                pin_id=pin_id,
                track="nightly",
                core="handy",
                chipset="a523",
                tuning_profile="a523-cortex-a55-v1",
                slice_time="2026-08-10T12:00:00Z",
                expected_current_test="absent",
                expected_current_assignment="absent",
                expected_new_variant="a" * 64,
                applicable_chipset=[],
            )

            def swap_before_mutation(*_args, **_kwargs) -> dict:
                pin_path.write_bytes(replacement)
                return {"registry": {}}

            with mock.patch.object(
                pipeline, "manifest_lock", return_value=mock.MagicMock()
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), mock.patch.object(
                pipeline,
                "load_authoritative_core_pin_index",
                return_value={pin_id: entry},
            ), mock.patch.object(
                pipeline, "load_json", return_value={}
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "load_core_track_source_registry_index",
                return_value={},
            ), mock.patch.object(
                pipeline,
                "core_track_source_ancestry_verifier",
                return_value=lambda *_args: True,
            ), mock.patch.object(
                pipeline,
                "set_core_track_test",
                side_effect=swap_before_mutation,
            ), mock.patch.object(
                pipeline,
                "atomic_write_json",
                side_effect=AssertionError("track registry was written"),
            ) as write, self.assertRaisesRegex(
                pipeline.PipelineError,
                "changed before track registry mutation",
            ):
                pipeline.cmd_core_track_set_test(args)

            write.assert_not_called()
            self.assertEqual(replacement, pin_path.read_bytes())

    def test_core_track_transaction_removes_new_snapshot_after_registry_write_failure(
        self,
    ) -> None:
        prior = {"content_sha256": "before", "tracks": {}}
        prior_bytes = b'{"content_sha256":"before", "tracks":{}}\n'
        updated = {"content_sha256": "after", "tracks": {}}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_sha256 = pipeline.sha256_bytes(
            pipeline._canonical_core_track_json_bytes(snapshot)
        )
        failure = pipeline.PipelineError("registry write failed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshots" / "before.json"
            registry_path.write_bytes(prior_bytes)

            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline, "atomic_write_json", side_effect=failure
            ), self.assertRaises(pipeline.PipelineError) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=snapshot_sha256,
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception)
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertFalse(snapshot_path.exists())

    def test_core_track_transaction_commits_registry_and_snapshot(self) -> None:
        prior = {"content_sha256": "before", "tracks": {}}
        prior_bytes = b'{ "tracks": {}, "content_sha256": "before" }\n'
        updated = {"content_sha256": "after", "tracks": {}}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_bytes = pipeline._canonical_core_track_json_bytes(snapshot)
        validated: list[object] = []

        def validate(document: object) -> dict:
            validated.append(document)
            return updated

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshots" / "before.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ):
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=pipeline.sha256_bytes(snapshot_bytes),
                    validator=validate,
                )

            self.assertEqual([updated], validated)
            self.assertEqual(
                pipeline._canonical_core_track_json_bytes(updated),
                registry_path.read_bytes(),
            )
            self.assertEqual(snapshot_bytes, snapshot_path.read_bytes())

    def test_core_track_transaction_removes_snapshot_when_create_mutates_then_raises(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256" : "before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_bytes = pipeline._canonical_core_track_json_bytes(snapshot)
        failure = KeyboardInterrupt("snapshot helper interrupted")

        real_link = pipeline.os.link

        def link_then_raise(source: Path, destination: Path) -> None:
            real_link(source, destination)
            raise failure

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline.os, "link", side_effect=link_then_raise
            ), mock.patch.object(
                pipeline,
                "atomic_write_json",
                side_effect=AssertionError("registry write was reached"),
            ) as write, self.assertRaises(KeyboardInterrupt) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=pipeline.sha256_bytes(snapshot_bytes),
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception)
            write.assert_not_called()
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertFalse(snapshot_path.exists())

    def test_core_track_transaction_preserves_foreign_snapshot_race_winner(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256" : "before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_bytes = pipeline._canonical_core_track_json_bytes(snapshot)

        def foreign_link_wins(_source: Path, destination: Path) -> None:
            Path(destination).write_bytes(snapshot_bytes)
            raise FileExistsError("foreign creator won the link race")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline.os, "link", side_effect=foreign_link_wins
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "refusing to replace existing core-track snapshot",
            ):
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=pipeline.sha256_bytes(snapshot_bytes),
                    validator=lambda document: document,
                )

            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertEqual(snapshot_bytes, snapshot_path.read_bytes())

    def test_core_track_snapshot_create_cleans_temp_on_prelink_fsync_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "snapshots" / "snapshot.json"
            ownership: dict[str, object] = {}
            with mock.patch.object(
                pipeline.os,
                "fsync",
                side_effect=OSError("snapshot fsync failed"),
            ), self.assertRaisesRegex(OSError, "snapshot fsync failed"):
                pipeline._atomic_create_core_track_snapshot(
                    snapshot_path,
                    b'{"snapshot":true}\n',
                    ownership,
                )

            self.assertFalse(snapshot_path.exists())
            self.assertEqual([], list(snapshot_path.parent.iterdir()))

    def test_core_track_registry_restore_cleans_temp_on_prereplace_fsync_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "core-tracks.json"
            prior_bytes = b'{"content_sha256":"prior"}\n'
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline.os,
                "fsync",
                side_effect=OSError("registry fsync failed"),
            ), self.assertRaisesRegex(OSError, "registry fsync failed"):
                pipeline._atomic_restore_core_track_bytes(
                    registry_path,
                    b'{"content_sha256":"restored"}\n',
                )

            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertEqual([registry_path], list(registry_path.parent.iterdir()))

    def test_core_track_transaction_rolls_back_no_snapshot_on_base_exception(
        self,
    ) -> None:
        prior = {"content_sha256": "before", "tracks": {}}
        prior_bytes = b'{ "tracks": {}, "content_sha256": "before" }\n'
        updated = {"content_sha256": "after", "tracks": {}}
        failure = KeyboardInterrupt("post-write validation interrupted")

        def fail_validation(_document: object) -> dict:
            raise failure

        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "core-tracks.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), self.assertRaises(KeyboardInterrupt) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=None,
                    snapshot=None,
                    snapshot_file_sha256=None,
                    validator=fail_validation,
                )

            self.assertIs(failure, caught.exception)
            self.assertEqual(prior_bytes, registry_path.read_bytes())

    def test_core_track_transaction_preserves_preexisting_valid_snapshot(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256" : "before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_bytes = pipeline._canonical_core_track_json_bytes(snapshot)
        snapshot_sha256 = pipeline.sha256_bytes(snapshot_bytes)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshots" / "before.json"
            registry_path.write_bytes(prior_bytes)
            snapshot_path.parent.mkdir()
            snapshot_path.write_bytes(snapshot_bytes)

            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline,
                "atomic_create_json",
                side_effect=AssertionError("preexisting snapshot was replaced"),
            ) as create, self.assertRaisesRegex(
                pipeline.PipelineError,
                "changed during post-write validation",
            ):
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=snapshot_sha256,
                    validator=lambda _document: {"unexpected": True},
                )

            create.assert_not_called()
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertEqual(snapshot_bytes, snapshot_path.read_bytes())

    def test_core_track_transaction_preserves_changed_preexisting_snapshot(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256" : "before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_bytes = pipeline._canonical_core_track_json_bytes(snapshot)
        foreign_snapshot_bytes = b'{"foreign":true}\n'
        failure = KeyboardInterrupt("validator interrupted")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            snapshot_path.write_bytes(snapshot_bytes)

            def mutate_snapshot_then_raise(_document: object) -> dict:
                snapshot_path.write_bytes(foreign_snapshot_bytes)
                raise failure

            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "rollback incomplete[\\s\\S]*preexisting snapshot changed",
            ) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=pipeline.sha256_bytes(snapshot_bytes),
                    validator=mutate_snapshot_then_raise,
                )

            self.assertIs(failure, caught.exception.__cause__)
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertEqual(foreign_snapshot_bytes, snapshot_path.read_bytes())

    def test_core_track_transaction_restores_partial_registry_and_removes_owned_snapshot(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{ "content_sha256": "before" }\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_bytes = pipeline._canonical_core_track_json_bytes(snapshot)
        failure = KeyboardInterrupt("registry helper interrupted")

        def mutate_then_raise(path: Path, _document: object) -> None:
            path.write_bytes(b'{"content_sha256":"partial"')
            raise failure

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline, "atomic_write_json", side_effect=mutate_then_raise
            ), self.assertRaises(KeyboardInterrupt) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=pipeline.sha256_bytes(snapshot_bytes),
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception)
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertFalse(snapshot_path.exists())

    def test_core_track_transaction_fails_closed_when_restore_acknowledgement_fails(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{ "content_sha256": "before" }\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_sha256 = pipeline.sha256_bytes(
            pipeline._canonical_core_track_json_bytes(snapshot)
        )
        failure = KeyboardInterrupt("registry helper interrupted")
        real_restore = pipeline._atomic_restore_core_track_bytes

        def mutate_then_raise(path: Path, _document: object) -> None:
            path.write_bytes(b'{"content_sha256":"partial"')
            raise failure

        def restore_then_raise(path: Path, raw: bytes) -> None:
            real_restore(path, raw)
            raise OSError("durability acknowledgement failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline, "atomic_write_json", side_effect=mutate_then_raise
            ), mock.patch.object(
                pipeline,
                "_atomic_restore_core_track_bytes",
                side_effect=restore_then_raise,
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "rollback incomplete[\\s\\S]*durability was not acknowledged",
            ) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=snapshot_sha256,
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception.__cause__)
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertTrue(snapshot_path.exists())

    def test_core_track_transaction_fails_closed_and_keeps_snapshot_when_restore_fails(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256":"before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_sha256 = pipeline.sha256_bytes(
            pipeline._canonical_core_track_json_bytes(snapshot)
        )
        failure = KeyboardInterrupt("registry helper interrupted")
        partial_registry_bytes = b'{"content_sha256":"partial"'

        def mutate_then_raise(path: Path, _document: object) -> None:
            path.write_bytes(partial_registry_bytes)
            raise failure

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline, "atomic_write_json", side_effect=mutate_then_raise
            ), mock.patch.object(
                pipeline,
                "_atomic_restore_core_track_bytes",
                side_effect=OSError("restore failed"),
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "rollback incomplete[\\s\\S]*registry bytes could not be "
                "restored exactly",
            ) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=snapshot_sha256,
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception.__cause__)
            self.assertEqual(partial_registry_bytes, registry_path.read_bytes())
            self.assertTrue(snapshot_path.exists())

    def test_core_track_transaction_fails_closed_when_owned_snapshot_unlink_fails(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256":"before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_sha256 = pipeline.sha256_bytes(
            pipeline._canonical_core_track_json_bytes(snapshot)
        )
        failure = pipeline.PipelineError("registry write failed")
        real_unlink = Path.unlink

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)

            def fail_owned_snapshot_unlink(
                path: Path, *args, **kwargs
            ) -> None:
                if path == snapshot_path:
                    raise OSError("unlink failed")
                real_unlink(path, *args, **kwargs)

            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline, "atomic_write_json", side_effect=failure
            ), mock.patch.object(
                Path, "unlink", autospec=True,
                side_effect=fail_owned_snapshot_unlink,
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "rollback incomplete[\\s\\S]*removal did not complete durably",
            ) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=snapshot_sha256,
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception.__cause__)
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertTrue(snapshot_path.exists())

    def test_core_track_transaction_surfaces_unacknowledged_snapshot_unlink(
        self,
    ) -> None:
        prior = {"content_sha256": "before"}
        prior_bytes = b'{"content_sha256":"before"}\n'
        updated = {"content_sha256": "after"}
        snapshot = {"model": "core-track-source-snapshot", "registry": prior}
        snapshot_sha256 = pipeline.sha256_bytes(
            pipeline._canonical_core_track_json_bytes(snapshot)
        )
        failure = pipeline.PipelineError("registry write failed")

        def unlink_then_raise(path: Path) -> None:
            path.unlink()
            raise OSError("directory durability acknowledgement failed")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "core-tracks.json"
            snapshot_path = root / "snapshot.json"
            registry_path.write_bytes(prior_bytes)
            with mock.patch.object(
                pipeline, "DEFAULT_CORE_TRACKS", registry_path
            ), mock.patch.object(
                pipeline, "atomic_write_json", side_effect=failure
            ), mock.patch.object(
                pipeline,
                "_durably_remove_owned_core_track_snapshot",
                side_effect=unlink_then_raise,
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "rollback incomplete[\\s\\S]*removal did not complete durably",
            ) as caught:
                pipeline._commit_core_track_registry_transaction(
                    prior_registry=prior,
                    registry=updated,
                    snapshot_path=snapshot_path,
                    snapshot=snapshot,
                    snapshot_file_sha256=snapshot_sha256,
                    validator=lambda document: document,
                )

            self.assertIs(failure, caught.exception.__cause__)
            self.assertEqual(prior_bytes, registry_path.read_bytes())
            self.assertFalse(snapshot_path.exists())

    def test_core_track_set_test_emits_slice_and_parent_snapshot_contract(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        pin_id = "handy-authoritative"
        pin_file_sha256 = "a" * 64
        pin_content_sha256 = "b" * 64
        registry = {"content_sha256": "c" * 64}
        version_slice = {
            "model": "immutable-track-version-slice-v1",
            "track": "nightly",
            "slice_time": "2026-08-10T12:00:00Z",
            "content_sha256": "d" * 64,
        }
        comparison_basis = {
            "model": "immutable-track-slice-comparison-basis-v1",
            "track": "nightly",
            "slice_time": "2026-08-10T12:00:00Z",
            "content_sha256": "e" * 64,
        }
        branch_basis_snapshot = {
            "model": "immutable-spruce-branch-basis-snapshot-v1",
            "content_sha256": "6" * 64,
        }
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            snapshot_path = Path(directory) / "parent.json"
            snapshot_relative = str(snapshot_path.relative_to(ROOT))
            events: list[str] = []
            result = {
                "registry": registry,
                "snapshot": {"snapshot": "parent"},
                "snapshot_path": snapshot_relative,
                "snapshot_file_sha256": "f" * 64,
                "previous_variant_id": None,
                "variant_id": "1" * 64,
                "previous_assignment_content_sha256": None,
                "parent_variant_id": "2" * 64,
                "parent_selection_content_sha256": "3" * 64,
                "parent_registry_content_sha256": "4" * 64,
                "version_slice": version_slice,
                "slice_comparison_basis": comparison_basis,
                "slice_branch_basis_registry_content_sha256": "7" * 64,
                "slice_branch_basis_snapshot": branch_basis_snapshot,
                "assignment_content_sha256": "5" * 64,
                "source_order_parent_binding": {"model": "binding-v1"},
                "source_order_outlier": None,
                "edge_deferred_by_admission": None,
            }
            args = argparse.Namespace(
                catalog=pipeline.DEFAULT_CATALOG,
                track="nightly",
                core="handy",
                chipset="a523",
                pin_id=pin_id,
                tuning_profile="a523-cortex-a55-v1",
                slice_time="2026-08-10T12:00:00Z",
                expected_current_test="absent",
                expected_current_assignment="absent",
                expected_new_variant="1" * 64,
                expected_parent_variant="2" * 64,
                expected_parent_registry="4" * 64,
                outlier_authorized_at=None,
                outlier_authorized_by=None,
                outlier_reason=None,
                applicable_chipset=[],
            )

            def commit_transaction(**kwargs) -> None:
                self.assertEqual(registry, kwargs["prior_registry"])
                self.assertEqual(registry, kwargs["registry"])
                self.assertEqual(snapshot_path, kwargs["snapshot_path"])
                self.assertEqual(result["snapshot"], kwargs["snapshot"])
                self.assertEqual(
                    result["snapshot_file_sha256"],
                    kwargs["snapshot_file_sha256"],
                )
                self.assertTrue(callable(kwargs["validator"]))
                events.append("transaction")

            output = io.StringIO()
            with mock.patch.object(
                pipeline, "manifest_lock", return_value=mock.MagicMock()
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), mock.patch.object(
                pipeline,
                "load_authoritative_core_pin_index",
                return_value={
                    pin_id: {
                        "path": f"pins/core-sets/{pin_id}.json",
                        "file_sha256": pin_file_sha256,
                        "content_sha256": pin_content_sha256,
                    }
                },
            ), mock.patch.object(
                pipeline,
                "load_json_with_sha256",
                return_value=(
                    {"pin_id": pin_id, "content_sha256": pin_content_sha256},
                    pin_file_sha256,
                ),
            ), mock.patch.object(
                pipeline, "load_json", return_value=registry
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "load_core_track_source_registry_index",
                return_value={},
            ), mock.patch.object(
                pipeline,
                "core_track_source_ancestry_verifier",
                return_value=lambda *_args: True,
            ), mock.patch.object(
                pipeline, "set_core_track_test", return_value=result
            ) as setter, mock.patch.object(
                pipeline, "sha256_file", return_value=pin_file_sha256
            ), mock.patch.object(
                pipeline,
                "_commit_core_track_registry_transaction",
                side_effect=commit_transaction,
            ), mock.patch("sys.stdout", new=output):
                self.assertEqual(0, pipeline.cmd_core_track_set_test(args))

            self.assertEqual(["transaction"], events)
            self.assertEqual(
                "2026-08-10T12:00:00Z",
                setter.call_args.kwargs["slice_time"],
            )
            self.assertEqual(
                "4" * 64,
                setter.call_args.kwargs["expected_parent_registry"],
            )
            self.assertEqual(
                "absent",
                setter.call_args.kwargs["expected_current_assignment"],
            )
            emitted = json.loads(output.getvalue())
            self.assertEqual(version_slice, emitted["version_slice"])
            self.assertEqual(
                comparison_basis, emitted["slice_comparison_basis"]
            )
            self.assertEqual(
                "7" * 64,
                emitted["slice_branch_basis_registry_content_sha256"],
            )
            self.assertEqual(
                branch_basis_snapshot,
                emitted["slice_branch_basis_snapshot"],
            )
            self.assertEqual(
                "5" * 64, emitted["assignment_content_sha256"]
            )
            self.assertIsNone(
                emitted["previous_assignment_content_sha256"]
            )
            self.assertEqual(snapshot_relative, emitted["source_registry_snapshot_path"])
            self.assertEqual("f" * 64, emitted["source_registry_snapshot_file_sha256"])

    def test_core_track_promote_uses_transaction_and_emits_stable_payload(
        self,
    ) -> None:
        prior_registry = {"content_sha256": "1" * 64}
        promoted_registry = {"content_sha256": "2" * 64}
        snapshot = {"model": "core-track-source-registry-snapshot-v1"}
        snapshot_relative = (
            ".local-e2e/core-track-transaction-test/source.json"
        )
        result = {
            "registry": promoted_registry,
            "snapshot": snapshot,
            "snapshot_path": snapshot_relative,
            "snapshot_file_sha256": "3" * 64,
            "stable_cell": {
                "approved_test_variant_id": "4" * 64,
                "source_registry_content_sha256": "1" * 64,
            },
            "previous_stable_variant_id": None,
        }
        args = argparse.Namespace(
            catalog=pipeline.DEFAULT_CATALOG,
            track="nightly",
            core="handy",
            chipset="a523",
            approved_at="2026-08-10T12:00:00Z",
            approved_by="local-reviewer",
            reason="focused transaction test",
            expected_test_variant="4" * 64,
            expected_current_stable="absent",
        )
        output = io.StringIO()
        with mock.patch.object(
            pipeline, "manifest_lock", return_value=mock.MagicMock()
        ), mock.patch.object(
            pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
        ), mock.patch.object(
            pipeline, "load_authoritative_core_pin_index", return_value={}
        ), mock.patch.object(
            pipeline, "load_json", return_value=prior_registry
        ), mock.patch.object(
            pipeline, "load_core_track_source_registry_index", return_value={}
        ), mock.patch.object(
            pipeline,
            "core_track_source_ancestry_verifier",
            return_value=lambda *_args: True,
        ), mock.patch.object(
            pipeline, "promote_core_track_test", return_value=result
        ), mock.patch.object(
            pipeline, "validate_core_tracks", return_value=promoted_registry
        ), mock.patch.object(
            pipeline, "_commit_core_track_registry_transaction"
        ) as transaction, mock.patch("sys.stdout", new=output):
            self.assertEqual(0, pipeline.cmd_core_track_promote(args))
            transaction_validator_result = transaction.call_args.kwargs[
                "validator"
            ](promoted_registry)

        transaction.assert_called_once()
        transaction_args = transaction.call_args.kwargs
        self.assertEqual(prior_registry, transaction_args["prior_registry"])
        self.assertEqual(promoted_registry, transaction_args["registry"])
        self.assertEqual(ROOT / snapshot_relative, transaction_args["snapshot_path"])
        self.assertEqual(snapshot, transaction_args["snapshot"])
        self.assertEqual("3" * 64, transaction_args["snapshot_file_sha256"])
        self.assertEqual(promoted_registry, transaction_validator_result)
        emitted = json.loads(output.getvalue())
        self.assertEqual("stable", emitted["status"])
        self.assertEqual("4" * 64, emitted["variant_id"])
        self.assertEqual("1" * 64, emitted["source_registry_content_sha256"])
        self.assertEqual(snapshot_relative, emitted["source_registry_snapshot_path"])
        self.assertEqual("disabled", emitted["publication"])

    def test_recipe_snapshots_branch_without_changing_the_v1_file_contract(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        core_id = "ecwolf"
        spec = catalog["cores"][core_id]
        source = {
            **spec["source"],
            "resolved_commit": spec["source"]["commit"],
            "resolved_url": spec["source"]["url"],
            "tree": spec["source"]["tree"],
            "submodules": [
                        {"state": " ", **entry}
                        for entry in spec["source"].get("submodules", [])
                    ],
        }
        base_toolchain = {
            **catalog["toolchains"]["arm64"],
            "resolved_image_id": catalog["toolchains"]["arm64"]["image_id"],
            "resolver_digests": catalog["resolver"],
        }
        base = {
            "core_id": core_id,
            "architecture": "arm64",
            "source": source,
            "recipe": self._legacy_recipe_without_pipeline_bundle(
                pipeline.recipe_record(
                    ROOT / "manifests" / "core-builds.json", core_id, spec
                )
            ),
            "toolchain": base_toolchain,
            "build": {
                "driver": spec["build"]["driver"],
                "environment": "sanitized-v1",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "recipe.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(base))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(1, snapshot["schema_version"])
            self.assertEqual(4, len(snapshot["files"]))
            self.assertEqual([], pipeline.verify_recipe_snapshot(snapshot_path, base, "v1"))

            current = copy.deepcopy(base)
            current["schema_version"] = 2
            current["toolchain"]["archive_provenance"] = (
                pipeline.expected_archive_provenance(catalog, "arm64")
            )
            snapshot_path.write_bytes(pipeline.recipe_snapshot(current))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(2, snapshot["schema_version"])
            self.assertEqual(6, len(snapshot["files"]))
            self.assertIn(catalog["toolchain_lock"]["path"], snapshot["files"])
            self.assertIn(
                catalog["toolchain_lock_validator"]["path"], snapshot["files"]
            )
            self.assertEqual(
                [], pipeline.verify_recipe_snapshot(snapshot_path, current, "v2")
            )
            contracted = copy.deepcopy(current)
            contracted["build"]["compile_definitions"] = []
            snapshot_path.write_bytes(pipeline.recipe_snapshot(contracted))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(3, snapshot["schema_version"])
            self.assertEqual(contracted["build"], snapshot["build"])
            self.assertEqual(
                [], pipeline.verify_recipe_snapshot(snapshot_path, contracted, "v3")
            )
            pcsx_spec = catalog["cores"]["pcsx_rearmed"]
            timestamped = copy.deepcopy(contracted)
            timestamped["core_id"] = "pcsx_rearmed"
            timestamped["source"] = {
                **pcsx_spec["source"],
                "resolved_commit": pcsx_spec["source"]["commit"],
                "resolved_url": pcsx_spec["source"]["url"],
                "submodules": [
                    {"state": " ", **entry}
                    for entry in pcsx_spec["source"].get("submodules", [])
                ],
            }
            timestamped["recipe"] = self._legacy_recipe_without_pipeline_bundle(
                pipeline.recipe_record(
                    ROOT / "manifests" / "core-builds.json",
                    "pcsx_rearmed",
                    pcsx_spec,
                )
            )
            timestamped["build"] = {
                "driver": pcsx_spec["build"]["driver"],
                "environment": "sanitized-v1",
                "compile_definitions": [],
                "source_date_epoch": pcsx_spec["build"]["source_date_epoch"],
            }
            snapshot_path.write_bytes(pipeline.recipe_snapshot(timestamped))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(4, snapshot["schema_version"])
            self.assertEqual(timestamped["build"], snapshot["build"])
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, timestamped, "v4-source-date-epoch"
                ),
            )
            tampered_epoch = copy.deepcopy(timestamped)
            tampered_epoch["build"]["source_date_epoch"] += 1
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, tampered_epoch, "v4-source-date-epoch-tampered"
                )
            )
            missing_definitions = copy.deepcopy(timestamped)
            missing_definitions["build"].pop("compile_definitions")
            snapshot_path.write_bytes(pipeline.recipe_snapshot(missing_definitions))
            missing_snapshot = json.loads(
                snapshot_path.read_text(encoding="utf-8")
            )
            self.assertEqual(4, missing_snapshot["schema_version"])
            self.assertIn("build", missing_snapshot)
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path,
                    missing_definitions,
                    "v4-source-date-epoch-missing-definitions",
                )
            )
            legacy_contract = json.loads(
                pipeline.recipe_snapshot(contracted).decode("utf-8")
            )
            legacy_contract["schema_version"] = 2
            legacy_contract.pop("build")
            snapshot_path.write_text(json.dumps(legacy_contract), encoding="utf-8")
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, contracted, "v2-contract-backcompat"
                ),
            )
            snapshot_path.write_bytes(pipeline.recipe_snapshot(contracted))
            stripped = copy.deepcopy(contracted)
            stripped["build"] = {}
            self.assertTrue(
                pipeline.verify_recipe_snapshot(snapshot_path, stripped, "stripped")
            )
            malformed = copy.deepcopy(current)
            malformed["toolchain"]["archive_provenance"] = "invalid"
            self.assertTrue(
                pipeline.verify_recipe_snapshot(snapshot_path, malformed, "malformed")
            )
            snapshot["toolchain"]["archive_provenance"]["archive"]["size"] += 1
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            self.assertTrue(
                pipeline.verify_recipe_snapshot(snapshot_path, current, "tampered")
            )

    def test_swanstation_recipe_snapshot_v5_binds_patch_bytes_and_contract(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        spec = catalog["cores"]["swanstation"]
        patch_path = spec["build"]["overlays"]["arm64"][0]["patch_path"]
        accepted_needed = [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libdl.so.2",
            "libgcc_s.so.1",
            "libm.so.6",
            "libpthread.so.0",
            "librt.so.1",
            "libstdc++.so.6",
        ]
        records = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for arch in ("arm64",):
                record = {
                    "core_id": "swanstation",
                    "architecture": arch,
                    "source": {
                        **spec["source"],
                        "resolved_commit": spec["source"]["commit"],
                        "resolved_url": spec["source"]["url"],
                        "submodules": [],
                    },
                    "recipe": self._legacy_recipe_without_pipeline_bundle(
                        pipeline.recipe_record(catalog_path, "swanstation", spec)
                    ),
                    "toolchain": {
                        **catalog["toolchains"][arch],
                        "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                        "resolver_digests": catalog["resolver"],
                        "archive_provenance": pipeline.expected_archive_provenance(
                            catalog, arch
                        ),
                    },
                    "artifact": {"needed": accepted_needed},
                    "build": {
                        **pipeline.normalized_build_contract(spec, arch),
                        "log": "build.log",
                        "log_sha256": "a" * 64,
                    },
                }
                records[arch] = record
                snapshot_path = root / f"{arch}.json"
                snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                self.assertEqual(5, snapshot["schema_version"])
                self.assertEqual(
                    pipeline.recorded_build_contract(record["build"]),
                    snapshot["build"],
                )
                self.assertEqual(
                    arch == "arm64", patch_path in snapshot["files"]
                )
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path, record, f"swanstation/{arch}"
                    ),
                )

            arm64_path = root / "arm64.json"
            original = json.loads(arm64_path.read_text(encoding="utf-8"))
            tampered = copy.deepcopy(original)
            tampered["files"][patch_path]["text"] += "\n"
            arm64_path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    arm64_path, records["arm64"], "swanstation/patch-bytes"
                )
            )
            tampered = copy.deepcopy(original)
            tampered["schema_version"] = 4
            arm64_path.write_text(json.dumps(tampered), encoding="utf-8")
            self.assertIn(
                "swanstation/version: recipe snapshot schema version mismatch",
                pipeline.verify_recipe_snapshot(
                    arm64_path, records["arm64"], "swanstation/version"
                ),
            )
            arm64_path.write_text(json.dumps(original), encoding="utf-8")
            changed_record = copy.deepcopy(records["arm64"])
            changed_record["build"]["cmake"]["system"]["processor"] = "arm"
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    arm64_path, changed_record, "swanstation/build-contract"
                )
            )
            self.assertNotEqual(
                pipeline.provenance_identity_sha256(records["arm64"]),
                pipeline.provenance_identity_sha256(changed_record),
            )
            forbidden_record = copy.deepcopy(records["arm64"])
            forbidden_record["artifact"]["needed"].append("libvulkan.so.1")
            self.assertTrue(
                any(
                    "dependency policy" in error
                    for error in pipeline.verify_recipe_snapshot(
                        arm64_path,
                        forbidden_record,
                        "swanstation/dependency-policy",
                    )
                )
            )

    def test_ffmpeg_recipe_snapshot_v6_binds_make_contract_and_preserves_legacy(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        spec = catalog["cores"]["ffmpeg"]
        record = {
            "core_id": "ffmpeg",
            "architecture": "arm64",
            "source": {
                **spec["source"],
                "resolved_commit": spec["source"]["commit"],
                "resolved_url": spec["source"]["url"],
                "submodules": [],
            },
            "recipe": self._legacy_recipe_without_pipeline_bundle(
                pipeline.recipe_record(catalog_path, "ffmpeg", spec)
            ),
            "toolchain": {
                **catalog["toolchains"]["arm64"],
                "resolved_image_id": catalog["toolchains"]["arm64"]["image_id"],
                "resolver_digests": catalog["resolver"],
                "archive_provenance": pipeline.expected_archive_provenance(
                    catalog, "arm64"
                ),
            },
            "artifact": {
                "needed": [
                    "ld-linux-aarch64.so.1",
                    "libc.so.6",
                    "libm.so.6",
                    "libpthread.so.0",
                ]
            },
            "build": {
                **pipeline.normalized_build_contract(spec, "arm64"),
                "log": "build.log",
                "log_sha256": "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "ffmpeg-v6.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(6, snapshot["schema_version"])
            self.assertEqual(
                pipeline.recorded_build_contract(record["build"]),
                snapshot["build"],
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "ffmpeg/v6"
                ),
            )

            original_identity = pipeline.provenance_identity_sha256(record)
            changed = copy.deepcopy(record)
            changed["build"]["make_variables"]["LIBRETRO_EMBED_FFMPEG"] = 0
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, changed, "ffmpeg/v6-build-contract"
                )
            )
            self.assertNotEqual(
                original_identity, pipeline.provenance_identity_sha256(changed)
            )

            tampered_snapshot = copy.deepcopy(snapshot)
            tampered_snapshot["schema_version"] = 5
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertIn(
                "ffmpeg/v6-version: recipe snapshot schema version mismatch",
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "ffmpeg/v6-version"
                ),
            )
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            stripped = copy.deepcopy(record)
            stripped["build"].pop("make_variables")
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, stripped, "ffmpeg/v6-stripped"
                )
            )
            forbidden = copy.deepcopy(record)
            forbidden["artifact"]["needed"].append("libavcodec.so.56")
            self.assertTrue(
                any(
                    "dependency policy" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, forbidden, "ffmpeg/v6-dependency"
                    )
                )
            )

    def test_git_version_v7_record_provenance_and_snapshot_are_bound(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        catalog = copy.deepcopy(catalog)
        core_id = "quicknes"
        arch = "arm64"
        spec = catalog["cores"][core_id]
        spec["build"]["git_version"] = {
            "derivation": "hyphen-short7-v1",
            "value": "-26bb785",
            "compiler_scope": "cxx",
        }
        pipeline.validate_catalog(catalog)
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(catalog, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes(b"metadata")
            log.write_text(
                "\n".join(pipeline.git_version_log_markers(spec))
                + "\naarch64-linux-gnu-g++ -c source.cpp -o source.o "
                + r'-DGIT_VERSION=\"-26bb785\"'
                + "\n",
                encoding="utf-8",
            )
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
                "needed": [],
            }
            record_document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": arch,
                "source": {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "submodules": [],
                },
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "toolchain": {
                    **catalog["toolchains"][arch],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, arch
                    ),
                    "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "build": {
                    **pipeline.normalized_build_contract(spec, arch),
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
            }
            record_path = root / "build-record.json"
            record_path.write_text(json.dumps(record_document), encoding="utf-8")
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ), mock.patch.object(
                pipeline,
                "_registered_core_log_contract_proves",
                return_value=True,
            ):
                self.assertEqual(
                    (artifact, metadata, log),
                    pipeline._validate_build_record_identity(
                        record_document, record_path, catalog_path, catalog
                    ),
                )

            record_document["recipe"] = self._legacy_recipe_without_pipeline_bundle(
                record_document["recipe"]
            )

            snapshot_path = root / "recipe.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record_document))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(7, snapshot["schema_version"])
            self.assertEqual(
                pipeline.recorded_build_contract(record_document["build"]),
                snapshot["build"],
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record_document, "quicknes/v7"
                ),
            )

            original_identity = pipeline.provenance_identity_sha256(record_document)
            changed = copy.deepcopy(record_document)
            changed["build"]["git_version"]["value"] = "-0000000"
            self.assertNotEqual(
                original_identity, pipeline.provenance_identity_sha256(changed)
            )
            self.assertFalse(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    changed["build"], changed["source"]["resolved_commit"]
                )
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, changed, "quicknes/v7-build-contract"
                )
            )
            changed_scope = copy.deepcopy(record_document)
            changed_scope["build"]["git_version"]["compiler_scope"] = "all"
            self.assertNotEqual(
                original_identity,
                pipeline.provenance_identity_sha256(changed_scope),
            )
            self.assertFalse(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    changed_scope["build"],
                    changed_scope["source"]["resolved_commit"],
                )
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path,
                    changed_scope,
                    "quicknes/v7-compiler-scope",
                )
            )
            snapshot["schema_version"] = 6
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            self.assertIn(
                "quicknes/v7-version: recipe snapshot schema version mismatch",
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record_document, "quicknes/v7-version"
                ),
            )

    def test_uzem_recipe_snapshot_v7_binds_full_native_identity(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "uzem"
        arch = "arm64"
        spec = catalog["cores"][core_id]
        source = {
            **spec["source"],
            "resolved_commit": spec["source"]["commit"],
            "resolved_url": spec["source"]["url"],
            "submodules": [],
        }
        record = {
            "core_id": core_id,
            "architecture": arch,
            "source": source,
            "recipe": self._legacy_recipe_without_pipeline_bundle(
                pipeline.recipe_record(catalog_path, core_id, spec)
            ),
            "toolchain": {
                **catalog["toolchains"][arch],
                "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                "resolver_digests": catalog["resolver"],
                "archive_provenance": pipeline.expected_archive_provenance(
                    catalog, arch
                ),
            },
            "artifact": {"sha256": "a" * 64, "needed": []},
            "metadata": {"status": "valid", "sha256": "b" * 64},
            "build": {
                **pipeline.normalized_build_contract(spec, arch),
                "log": "build.log",
                "log_sha256": "c" * 64,
            },
        }
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                record["build"],
                source["resolved_commit"],
                core_id,
                source,
            )
        )
        self.assertFalse(
            pipeline.git_version_golden_build_contract_is_well_formed(
                record["build"], source["resolved_commit"]
            )
        )
        shallow_source = {
            "resolved_commit": source["resolved_commit"],
            "resolved_url": source["resolved_url"],
        }
        self.assertFalse(
            pipeline.git_version_golden_build_contract_is_well_formed(
                record["build"],
                source["resolved_commit"],
                core_id,
                shallow_source,
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "uzem-v7.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(7, snapshot["schema_version"])
            self.assertEqual(
                pipeline.recorded_build_contract(record["build"]),
                snapshot["build"],
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "uzem/v7"
                ),
            )

            original_identity = pipeline.provenance_identity_sha256(record)
            changed = copy.deepcopy(record)
            changed["source"]["tree"] = "a" * 40
            self.assertNotEqual(
                original_identity, pipeline.provenance_identity_sha256(changed)
            )
            self.assertFalse(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    changed["build"],
                    changed["source"]["resolved_commit"],
                    core_id,
                    changed["source"],
                )
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, changed, "uzem/v7-source-identity"
                )
            )

            tampered_snapshot = copy.deepcopy(snapshot)
            tampered_snapshot["core_id"] = "vemulator"
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "recipe snapshot identity mismatch" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, record, "uzem/v7-snapshot-identity"
                    )
                )
            )

    def test_pipeline_has_no_github_publication_command(self) -> None:
        text = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("gh release", text)
        self.assertNotIn("gh api", text)

    def test_golden_content_digest_covers_imported_artifacts(self) -> None:
        document = {
            "schema_version": 1,
            "baseline": {"repository_commit": "a" * 40},
            "cores": {"mgba": {"artifacts": {"arm64": {"sha256": "b" * 64}}}},
            "build_goldens": {},
        }
        before = pipeline.golden_content_sha256(document)
        document["cores"]["mgba"]["artifacts"]["arm64"]["sha256"] = "c" * 64
        self.assertNotEqual(before, pipeline.golden_content_sha256(document))
        after_import_change = pipeline.golden_content_sha256(document)
        document["build_goldens"]["mgba"] = {"arm64": {"artifact": {"sha256": "d" * 64}}}
        self.assertNotEqual(after_import_change, pipeline.golden_content_sha256(document))

    def test_safe_child_rejects_path_escape(self) -> None:
        with self.assertRaises(pipeline.PipelineError):
            pipeline.safe_child(ROOT, "../outside", "fixture")

    def test_local_e2e_output_rejects_external_root(self) -> None:
        with self.assertRaises(pipeline.PipelineError):
            pipeline.require_contained(Path("/tmp"), ROOT / ".local-e2e", "fixture")

    def test_content_addressed_store_preserves_bytes_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination, digest = pipeline.store_bytes(
                Path(directory), "fixtures", b"golden bytes"
            )
            duplicate, duplicate_digest = pipeline.store_bytes(
                Path(directory), "fixtures", b"golden bytes"
            )
            self.assertEqual(destination, duplicate)
            self.assertEqual(digest, duplicate_digest)
            self.assertEqual(b"golden bytes", destination.read_bytes())
            self.assertEqual(0o644, stat.S_IMODE(destination.stat().st_mode))

    def test_pin_creation_refuses_to_replace_existing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "golden.json"
            pipeline.atomic_create_json(path, {"pin": "first"})
            with self.assertRaisesRegex(pipeline.PipelineError, "refusing to replace"):
                pipeline.atomic_create_json(path, {"pin": "second"})
            self.assertEqual({"pin": "first"}, json.loads(path.read_text(encoding="utf-8")))

    def test_golden_schema_requires_local_evidence_contract(self) -> None:
        schema = json.loads(
            (ROOT / "manifests" / "golden-start.schema.json").read_text(encoding="utf-8")
        )
        self.assertIn("content_sha256", schema["required"])
        build_golden = schema["$defs"]["buildGolden"]
        self.assertNotIn("build", build_golden["required"])
        native_core_contract = next(
            contract
            for contract in build_golden["allOf"]
            if set(
                contract.get("if", {})
                .get("properties", {})
                .get("core_id", {})
                .get("enum", [])
            )
            == {
                "81",
                "atari800",
                "bluemsx",
                "cap32",
                "crocods",
                "fbneo",
                "fmsx",
                "gearboy",
                "gearcoleco",
                "gearsystem",
                "genesis_plus_gx",
                "genesis_plus_gx_wide",
                "handy",
                "mame2003_plus",
                "mednafen_pcfx",
                "mednafen_wswan",
                "picodrive",
                "pokemini",
                "snes9x2005",
                "snes9x2005_plus",
                "stella2014",
                "uzem",
                "vecx",
                "vice_x64",
                "vice_xvic",
            }
        )
        self.assertEqual(["build"], native_core_contract["then"]["required"])
        exact_build_contract = build_golden["dependentSchemas"]["build"]
        exact_build_triggers = exact_build_contract["if"]["anyOf"]
        self.assertTrue(
            any(
                set(trigger.get("properties", {}).get("core_id", {}).get("enum", []))
                == {
                    "81",
                    "atari800",
                    "bluemsx",
                    "cap32",
                    "crocods",
                    "fbneo",
                    "fmsx",
                    "freeintv",
                    "gearboy",
                    "gearcoleco",
                    "gearsystem",
                    "genesis_plus_gx",
                    "genesis_plus_gx_wide",
                    "handy",
                    "mame2003_plus",
                    "mgba",
                    "mednafen_pcfx",
                    "mednafen_wswan",
                    "picodrive",
                    "pokemini",
                    "snes9x2005",
                    "snes9x2005_plus",
                    "stella2014",
                    "uzem",
                    "vecx",
                    "vice_x64",
                    "vice_xvic",
                }
                and trigger.get("required") == ["core_id"]
                for trigger in exact_build_triggers
            )
        )
        self.assertTrue(
            any(
                trigger.get("properties", {})
                .get("build", {})
                .get("properties", {})
                .get("git_version")
                == {
                    "oneOf": [
                        {"$ref": "#/$defs/nativeGitVersion"},
                        {"$ref": "#/$defs/fbneoNativeVersion"},
                        {"$ref": "#/$defs/mame2003PlusNativeGitVersion"},
                        {"$ref": "#/$defs/mgbaNativeGitVersion"},
                        {"$ref": "#/$defs/nativeGitDescribeVersion"},
                        {"$ref": "#/$defs/gearboyNativeGitDescribeVersion"},
                        {"$ref": "#/$defs/gearsystemNativeGitDescribeVersion"},
                        {"$ref": "#/$defs/viceNativeGitVersion"},
                    ]
                }
                for trigger in exact_build_triggers
            )
        )
        self.assertEqual(
            {
                "81",
                "atari800",
                "bluemsx",
                "cap32",
                "crocods",
                "fbneo",
                "fmsx",
                "freeintv",
                "gearboy",
                "gearcoleco",
                "gearsystem",
                "genesis_plus_gx",
                "genesis_plus_gx_wide",
                "handy",
                "mame2003_plus",
                "mgba",
                "mednafen_pcfx",
                "mednafen_wswan",
                "picodrive",
                "pokemini",
                "snes9x2005",
                "snes9x2005_plus",
                "stella2014",
                "uzem",
                "vecx",
                "vice_x64",
                "vice_xvic",
            },
            {
                branch["properties"]["core_id"]["const"]
                for branch in exact_build_contract["then"]["oneOf"]
            },
        )
        required = schema["$defs"]["buildGolden"]["properties"]["local_store"][
            "required"
        ]
        self.assertEqual(
            {
                "availability",
                "artifact",
                "metadata",
                "e2e_record",
                "package",
                "build_records",
                "build_logs",
                "recipe_snapshots",
            },
            set(required),
        )
        self.assertEqual(
            {"lock", "validator", "architecture", "archive"},
            set(schema["$defs"]["archiveProvenance"]["required"]),
        )
        version_contract = next(
            contract
            for contract in build_golden["allOf"]
            if contract.get("if") == {"required": ["provenance_version"]}
        )
        self.assertEqual(["provenance_version"], version_contract["if"]["required"])
        self.assertIn("then", version_contract)
        self.assertIn("else", version_contract)
        self.assertNotIn("build", version_contract["then"].get("required", []))
        build_contract = schema["$defs"]["buildContract"]
        self.assertIn(
            "direct-cmake", build_contract["properties"]["driver"]["enum"]
        )
        generated_source_contract = build_contract["allOf"][0]
        self.assertEqual(
            ["generated_source"],
            generated_source_contract["if"]["required"],
        )
        self.assertEqual(
            "libretro-super",
            generated_source_contract["then"]["properties"]["driver"]["const"],
        )
        self.assertEqual(
            [],
            generated_source_contract["then"]["properties"]
            ["compile_definitions"]["const"],
        )
        recipe_profile_contract = build_contract["allOf"][1]
        self.assertEqual(
            ["recipe_profile"],
            recipe_profile_contract["if"]["required"],
        )
        self.assertEqual(
            {"$ref": "#/$defs/picodriveRecipeProfile"},
            recipe_profile_contract["then"]["properties"]["recipe_profile"],
        )
        self.assertEqual(
            {"$ref": "#/$defs/picodriveMetadataReplacement"},
            recipe_profile_contract["then"]["properties"]
            ["metadata_replacement"],
        )
        git_contract = build_contract["allOf"][2]
        self.assertEqual(["git_version"], git_contract["if"]["required"])
        self.assertEqual(
            "libretro-super",
            git_contract["then"]["properties"]["driver"]["const"],
        )
        self.assertEqual(
            [
                {
                    "properties": {
                        "compile_definitions": {"const": []},
                    },
                },
                {
                    "properties": {
                        "git_version": {
                            "$ref": "#/$defs/fbneoNativeVersion",
                        },
                        "compile_definitions": {
                            "const": [
                                "HWCAP2_AES=1",
                                "HWCAP2_CRC32=16",
                                "HWCAP2_SHA1=4",
                                "HWCAP2_SHA2=8",
                            ],
                        },
                    },
                },
            ],
            git_contract["then"]["oneOf"],
        )
        hyphen_git_contract = build_contract["allOf"][3]
        self.assertEqual(
            ["make_variables"],
            hyphen_git_contract["then"]["not"]["required"],
        )
        native_git_contract = build_contract["allOf"][4]
        self.assertEqual(
            {"make_variables", "metadata_replacement"},
            set(native_git_contract["then"]["required"]),
        )
        self.assertEqual(
            {"derivation", "value"},
            set(schema["$defs"]["gitVersion"]["required"]),
        )
        self.assertEqual(
            "cxx",
            schema["$defs"]["gitVersion"]["properties"]["compiler_scope"][
                "const"
            ],
        )
        make_contract = build_contract["allOf"][5]
        self.assertEqual(
            ["make_variables"], make_contract["if"]["required"]
        )
        ffmpeg_make_contract = build_contract["allOf"][6]
        self.assertEqual(
            ["source_date_epoch"],
            ffmpeg_make_contract["then"]["required"],
        )
        self.assertEqual(
            [],
            make_contract["then"]["properties"]["compile_definitions"]["const"],
        )
        metadata_contract = build_contract["allOf"][7]
        self.assertEqual(
            ["metadata_replacement"], metadata_contract["if"]["required"]
        )
        self.assertEqual(
            {"git_version", "make_variables"},
            set(metadata_contract["then"]["required"]),
        )
        atari800_metadata_contract = build_contract["allOf"][8]
        self.assertEqual(
            ["metadata_replacement"],
            atari800_metadata_contract["if"]["required"],
        )
        self.assertEqual(
            ["git_version"],
            atari800_metadata_contract["then"]["required"],
        )
        self.assertEqual(
            {"make_variables", "source_date_epoch"},
            {
                item["required"][0]
                for item in atari800_metadata_contract["then"]["not"]["anyOf"]
            },
        )
        vecx_make_contract = build_contract["allOf"][9]
        self.assertEqual(
            {"git_version", "metadata_replacement"},
            set(vecx_make_contract["then"]["required"]),
        )
        self.assertEqual(
            {"source_date_epoch", "cmake", "overlays"},
            set(build_contract["allOf"][10]["then"]["required"]),
        )
        catalog_schema = json.loads(
            (ROOT / "manifests" / "core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            catalog_schema["$defs"]["gitVersion"],
            schema["$defs"]["gitVersion"],
        )
        self.assertEqual(
            catalog_schema["$defs"]["core"]["properties"]["build"]
            ["properties"]["generated_source"],
            schema["$defs"]["generatedSource"],
        )
        for schema_document in (schema, catalog_schema):
            replacement = schema_document["$defs"]["metadataReplacement"]
            self.assertEqual(
                {
                    "#/$defs/atari800MetadataReplacement",
                    "#/$defs/picodriveMetadataReplacement",
                    "#/$defs/vecxMetadataReplacement",
                },
                {branch["$ref"] for branch in replacement["oneOf"]},
            )
            vecx_replacement = schema_document["$defs"][
                "vecxMetadataReplacement"
            ]
            self.assertEqual(
                pipeline.VECX_METADATA_PREIMAGE_SHA256,
                vecx_replacement["properties"]["preimage_sha256"]["const"],
            )
            self.assertEqual(
                pipeline.VECX_METADATA_REPLACEMENT_SHA256,
                vecx_replacement["properties"]["replacement_sha256"]["const"],
            )
            atari800_replacement = schema_document["$defs"][
                "atari800MetadataReplacement"
            ]
            self.assertEqual(
                pipeline.ATARI800_METADATA_PREIMAGE_SHA256,
                atari800_replacement["properties"]["preimage_sha256"]["const"],
            )
            self.assertEqual(
                pipeline.ATARI800_METADATA_REPLACEMENT_SHA256,
                atari800_replacement["properties"]["replacement_sha256"]["const"],
            )
            variables = schema_document["$defs"]["portableFfmpegMakeVariables"]
            self.assertEqual(
                set(pipeline.PORTABLE_FFMPEG_MAKE_VARIABLES),
                set(variables["required"]),
            )
            self.assertFalse(variables["additionalProperties"])
            for name, value in pipeline.PORTABLE_FFMPEG_MAKE_VARIABLES.items():
                self.assertEqual(value, variables["properties"][name]["const"])
            plus_variables = schema_document["$defs"][
                "snes9x2005PlusMakeVariables"
            ]
            self.assertEqual(
                {"USE_BLARGG_APU"}, set(plus_variables["required"])
            )
            self.assertFalse(plus_variables["additionalProperties"])
            self.assertEqual(
                1,
                plus_variables["properties"]["USE_BLARGG_APU"]["const"],
            )
        architecture_contracts = [
            contract
            for contract in build_golden["allOf"]
            if contract.get("if", {})
            .get("properties", {})
            .get("architecture", {})
            .get("const")
            in {"arm64", "armhf"}
        ]
        self.assertEqual(
            {"aarch64", "arm"},
            {
                contract["then"]["properties"]["build"]["properties"]["cmake"][
                    "properties"
                ]["system"]["properties"]["processor"]["const"]
                for contract in architecture_contracts
            },
        )
        overlay_pattern = schema["$defs"]["overlay"]["properties"]["patch_path"][
            "pattern"
        ]
        self.assertIsNone(re.fullmatch(overlay_pattern, "patches/x/../y.patch"))

    def test_documented_rejected_baseline_does_not_invalidate_manifest(self) -> None:
        workflows = pipeline.core_workflows()
        cores = {}
        for core_id, path in workflows.items():
            cores[core_id] = {
                "workflow": str(path.relative_to(ROOT)),
                "artifacts": {
                    "arm64": {
                        "status": "valid",
                        "sha256": "a" * 64,
                    },
                    "armhf": {"status": "not_shipped"},
                },
            }
        first = sorted(cores)[0]
        cores[first]["artifacts"]["armhf"] = {
            "status": "invalid",
            "sha256": "b" * 64,
            "errors": ["wrong architecture"],
        }
        document = {
            "schema_version": 1,
            "publication": "disabled",
            "baseline": {"repository_commit": "c" * 40},
            "summary": {
                "core_count": len(cores),
                "valid_artifact_count": len(cores),
                "invalid_artifacts": [f"{first}/armhf"],
                "cores_without_valid_artifacts": [],
            },
            "cores": cores,
            "build_goldens": {},
        }
        document["content_sha256"] = pipeline.golden_content_sha256(document)
        report = pipeline.validate_golden_document(document)
        self.assertEqual("valid", report["status"])
        self.assertEqual([f"{first}/armhf"], report["invalid_imported_artifacts"])


class ArtifactValidationTests(unittest.TestCase):
    def fake_header(self, *, elf_class: str, machine: str, flags: str) -> dict[str, str]:
        return {
            "class": elf_class,
            "data": "2's complement, little endian",
            "type": "DYN (Shared object file)",
            "machine": machine,
            "flags": flags,
        }

    def validate_with_header(
        self,
        arch: str,
        header: dict[str, str],
        *,
        symbols: set[str] | None = None,
    ) -> dict:
        exported = pipeline.REQUIRED_LIBRETRO_SYMBOLS if symbols is None else symbols
        symbol_output = "\n".join(
            f"{index}: 0000000000001000 4 FUNC GLOBAL DEFAULT 1 {name}"
            for index, name in enumerate(sorted(exported), start=1)
        )
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "fixture_libretro.so"
            artifact.write_bytes(b"fixture")
            with mock.patch.object(pipeline, "readelf_header", return_value=header), mock.patch.object(
                pipeline,
                "run",
                side_effect=[
                    mock.Mock(returncode=0, stdout="", stderr=""),
                    mock.Mock(returncode=0, stdout=symbol_output, stderr=""),
                    mock.Mock(returncode=0, stdout="", stderr=""),
                ],
            ):
                return pipeline.validate_artifact(artifact, arch)

    def test_byte_validator_isolated_from_original_path_replacement(self) -> None:
        original_bytes = b"original artifact bytes"
        replacement_bytes = b"replacement artifact bytes"
        with tempfile.TemporaryDirectory() as directory:
            original_path = Path(directory) / "fixture_libretro.so"
            original_path.write_bytes(original_bytes)
            snapshot = original_path.read_bytes()
            original_path.write_bytes(replacement_bytes)

            def inspect_snapshot(path: Path, arch: str) -> dict:
                self.assertEqual("arm64", arch)
                self.assertNotEqual(original_path, path)
                observed = path.read_bytes()
                return {
                    "status": "valid",
                    "errors": [],
                    "sha256": pipeline.sha256_bytes(observed),
                    "size": len(observed),
                }

            with mock.patch.object(
                pipeline, "validate_artifact", side_effect=inspect_snapshot
            ):
                result = pipeline._validate_artifact_bytes(snapshot, "arm64")

        self.assertEqual(
            pipeline.sha256_bytes(original_bytes), result["sha256"]
        )
        self.assertEqual(len(original_bytes), result["size"])

    def test_accepts_aarch64_shared_object_contract(self) -> None:
        result = self.validate_with_header(
            "arm64", self.fake_header(elf_class="ELF64", machine="AArch64", flags="0x0")
        )
        self.assertEqual("valid", result["status"])

    def test_accepts_arm_hard_float_shared_object_contract(self) -> None:
        result = self.validate_with_header(
            "armhf",
            self.fake_header(
                elf_class="ELF32",
                machine="ARM",
                flags="0x5000400, Version5 EABI, hard-float ABI",
            ),
        )
        self.assertEqual("valid", result["status"])

    def test_rejects_x86_host_output_for_arm_target(self) -> None:
        result = self.validate_with_header(
            "armhf", self.fake_header(elf_class="ELF64", machine="Advanced Micro Devices X86-64", flags="0x0")
        )
        self.assertEqual("invalid", result["status"])
        self.assertTrue(any("expected ARM" in error for error in result["errors"]))

    def test_rejects_arm_soft_float_output(self) -> None:
        result = self.validate_with_header(
            "armhf",
            self.fake_header(elf_class="ELF32", machine="ARM", flags="0x5000200, Version5 EABI, soft-float ABI"),
        )
        self.assertEqual("invalid", result["status"])
        self.assertIn("expected ARM hard-float ABI flag", result["errors"])

    def test_rejects_big_endian_target_output(self) -> None:
        header = self.fake_header(elf_class="ELF64", machine="AArch64", flags="0x0")
        header["data"] = "2's complement, big endian"
        result = self.validate_with_header("arm64", header)
        self.assertEqual("invalid", result["status"])
        self.assertTrue(any("expected little-endian" in error for error in result["errors"]))

    def test_missing_mandatory_export_invalidates_artifact(self) -> None:
        symbols = set(pipeline.REQUIRED_LIBRETRO_SYMBOLS) - {"retro_set_environment"}
        result = self.validate_with_header(
            "arm64",
            self.fake_header(elf_class="ELF64", machine="AArch64", flags="0x0"),
            symbols=symbols,
        )
        self.assertEqual("invalid", result["status"])
        self.assertIn("missing libretro symbols: retro_set_environment", result["errors"])

    def test_undefined_dynamic_symbol_does_not_satisfy_libretro_contract(self) -> None:
        output = "1: 0000000000000000 0 FUNC GLOBAL DEFAULT UND retro_init\n"
        self.assertEqual(set(), pipeline.defined_libretro_symbols(output))

    def test_hidden_or_local_symbol_does_not_satisfy_libretro_contract(self) -> None:
        output = "\n".join(
            [
                "1: 0000000000001000 4 FUNC GLOBAL HIDDEN 1 retro_init",
                "2: 0000000000001000 4 FUNC LOCAL DEFAULT 1 retro_run",
                "3: 0000000000001000 4 OBJECT GLOBAL DEFAULT 1 retro_load_game",
            ]
        )
        self.assertEqual(set(), pipeline.defined_libretro_symbols(output))


class PackagingTests(unittest.TestCase):
    def make_record(self, root: Path, arch: str) -> dict:
        output = root / "mgba" / arch
        output.mkdir(parents=True)
        artifact = output / "mgba_libretro.so"
        metadata = output / "mgba_libretro.info"
        artifact.write_bytes(f"artifact-{arch}".encode())
        metadata.write_bytes(b"display_name = mGBA\n")
        return {
            "result": "passed",
            "architecture": arch,
            "artifact": {
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
            },
            "metadata": {
                "path": metadata.name,
                "status": "valid",
                "sha256": pipeline.sha256_file(metadata),
            },
            "source": {"resolved_commit": "a" * 40},
            "toolchain": {"resolved_image_id": f"sha256:{'b' * 64}"},
        }

    def test_complete_package_preserves_both_targets_and_info(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [self.make_record(root, arch) for arch in ("arm64", "armhf")]
            spec = {
                "targets": ["arm64", "armhf"],
                "build": {"artifact_name": "mgba_libretro.so"},
                "metadata": {"artifact_name": "mgba_libretro.info"},
            }
            result = pipeline.package_e2e_core(root, "mgba", records, spec)
            self.assertEqual("packaged", result["result"])
            with zipfile.ZipFile(root / result["path"]) as archive:
                self.assertEqual(
                    {
                        "cores64/mgba_libretro.so",
                        "cores/mgba_libretro.so",
                        "mgba_libretro.info",
                        "manifest.json",
                    },
                    set(archive.namelist()),
                )

    def test_incomplete_target_set_is_not_packaged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [self.make_record(root, "arm64")]
            spec = {
                "targets": ["arm64", "armhf"],
                "build": {"artifact_name": "mgba_libretro.so"},
                "metadata": {"artifact_name": "mgba_libretro.info"},
            }
            result = pipeline.package_e2e_core(root, "mgba", records, spec)
            self.assertEqual("not_packaged", result["result"])


class PinSetAndReleaseTests(unittest.TestCase):
    def make_selection(self, core_id: str = "fixture") -> dict:
        artifact_bytes = b"fixture-arm64-artifact"
        metadata_bytes = b"display_name = Fixture\n"
        artifact_name = f"{core_id}_libretro.so"
        metadata_name = f"{core_id}_libretro.info"
        artifact_path, artifact_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "artifacts", artifact_bytes
        )
        metadata_path, metadata_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "metadata", metadata_bytes
        )
        source = {
            "commit": "1" * 40,
            "resolved_url": f"https://github.com/example/{core_id}.git",
            "resolved_commit": "1" * 40,
            "tree": "2" * 40,
            "submodules": [],
        }
        toolchain = {
            "resolved_image_id": f"sha256:{'6' * 64}",
            "dockerfile_sha256": "7" * 64,
            "resolver_digests": {"libretro_super_commit": "8" * 40},
        }
        package_manifest = {
            "schema_version": 1,
            "local_only": True,
            "publication": "disabled",
            "core_id": core_id,
            "artifacts": {
                "arm64": {
                    "path": f"cores64/{artifact_name}",
                    "sha256": artifact_sha,
                    "source_commit": source["resolved_commit"],
                    "toolchain_image_id": toolchain["resolved_image_id"],
                }
            },
            "metadata": {"path": metadata_name, "sha256": metadata_sha},
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            pipeline.add_zip_entry(archive, f"cores64/{artifact_name}", artifact_bytes)
            pipeline.add_zip_entry(archive, metadata_name, metadata_bytes)
            pipeline.add_zip_entry(
                archive,
                "manifest.json",
                (json.dumps(package_manifest, indent=2, sort_keys=True) + "\n").encode(),
            )
        package_bytes = buffer.getvalue()
        package_path, package_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "packages", package_bytes
        )
        build_record_sha = "d" * 64
        e2e = {
            "run_id": "fixture-nightly",
            "content_sha256": "e" * 64,
            "package_sha256": package_sha,
            "build_records": {"arm64": build_record_sha},
        }
        record = {
            "core_id": core_id,
            "architecture": "arm64",
            "promotion_state": "build_golden",
            "validation_scope": "static-build-only",
            "source": source,
            "recipe": {
                "core_spec_sha256": "3" * 64,
                "pipeline_sha256": "4" * 64,
                "workflow_sha256": "5" * 64,
            },
            "toolchain": toolchain,
            "artifact": {
                "status": "valid",
                "path": artifact_name,
                "sha256": artifact_sha,
                "size": len(artifact_bytes),
            },
            "metadata": {
                "status": "valid",
                "path": metadata_name,
                "sha256": metadata_sha,
                "size": len(metadata_bytes),
            },
            "e2e": copy.deepcopy(e2e),
            "local_store": {
                "artifact": {
                    "path": str(artifact_path.relative_to(ROOT)),
                    "sha256": artifact_sha,
                },
                "metadata": {
                    "path": str(metadata_path.relative_to(ROOT)),
                    "sha256": metadata_sha,
                },
                "package": {
                    "path": str(package_path.relative_to(ROOT)),
                    "sha256": package_sha,
                },
            },
        }
        selection = {
            "tier": "build_golden",
            "validation_scope": "static-build-only",
            "e2e": e2e,
            "package": {
                "name": f"{core_id}_libretro.zip",
                "path": str(package_path.relative_to(ROOT)),
                "sha256": package_sha,
                "size": len(package_bytes),
            },
            "metadata": {
                "path": str(metadata_path.relative_to(ROOT)),
                "sha256": metadata_sha,
                "size": len(metadata_bytes),
            },
            "targets": {
                "arm64": {
                    "artifact": {
                        "path": str(artifact_path.relative_to(ROOT)),
                        "sha256": artifact_sha,
                        "size": len(artifact_bytes),
                    },
                    "build_record_sha256": build_record_sha,
                    "provenance_identity_sha256": pipeline.provenance_identity_sha256(
                        record
                    ),
                    "golden_record": record,
                }
            },
        }
        selection["selection_sha256"] = pipeline.selection_content_sha256(selection)
        return selection

    def make_pin(self, selection: dict, pin_id: str = "fixture-pin") -> dict:
        core_id = next(iter(selection["targets"].values()))["golden_record"]["core_id"]
        document = {
            "schema_version": 1,
            "pin_id": pin_id,
            "local_only": True,
            "publication": "disabled",
            "scope": [core_id],
            "parent": None,
            "sources": [
                {
                    "path": "pins/fixture-parent.json",
                    "pin_id": "fixture-parent",
                    "file_sha256": "a" * 64,
                    "content_sha256": "b" * 64,
                }
            ],
            "selection_policy": copy.deepcopy(pipeline.PIN_SELECTION_POLICY),
            "cores": {
                core_id: {
                    "decision": "select_source",
                    "source_index": 0,
                    "selection": selection,
                }
            },
            "summary": {
                "core_count": 1,
                "retained_parent_count": 0,
                "selected_source_count": 1,
            },
        }
        document["content_sha256"] = pipeline.pin_set_content_sha256(document)
        return document

    def make_retained_pin(
        self,
        parent: dict,
        parent_path: Path,
        pin_id: str,
    ) -> dict:
        selection = copy.deepcopy(
            next(iter(parent["cores"].values()))["selection"]
        )
        document = self.make_pin(selection, pin_id)
        document["parent"] = {
            "path": str(parent_path.relative_to(ROOT)),
            "pin_id": parent["pin_id"],
            "file_sha256": pipeline.sha256_file(parent_path),
            "content_sha256": parent["content_sha256"],
        }
        document["sources"] = []
        core = next(iter(document["cores"].values()))
        core["decision"] = "retain_parent"
        core.pop("source_index")
        document["summary"]["retained_parent_count"] = 1
        document["summary"]["selected_source_count"] = 0
        document["content_sha256"] = pipeline.pin_set_content_sha256(document)
        return document

    def make_three_level_lineage(
        self,
        pin_dir: Path,
        source_dir: Path,
        selection: dict | None = None,
    ) -> dict:
        selection = selection or self.make_selection()
        source_path = source_dir / "lineage-source.json"
        source = {
            "pin_id": "lineage-source",
            "content_sha256": "c" * 64,
        }
        source_path.write_text(json.dumps(source), encoding="utf-8")

        grandparent_path = pin_dir / "grandparent.json"
        grandparent = self.make_pin(copy.deepcopy(selection), "grandparent-pin")
        grandparent["sources"] = [
            pipeline.golden_source_reference(source_path, source)
        ]
        grandparent["content_sha256"] = pipeline.pin_set_content_sha256(grandparent)
        pipeline.atomic_create_json(grandparent_path, grandparent)

        parent_path = pin_dir / "parent.json"
        parent = self.make_retained_pin(
            grandparent, grandparent_path, "parent-pin"
        )
        pipeline.atomic_create_json(parent_path, parent)

        child_path = pin_dir / "child.json"
        child = self.make_retained_pin(parent, parent_path, "child-pin")
        pipeline.atomic_create_json(child_path, child)
        return {
            "selection": selection,
            "source": source,
            "source_path": source_path,
            "grandparent": grandparent,
            "grandparent_path": grandparent_path,
            "parent": parent,
            "parent_path": parent_path,
            "child": child,
            "child_path": child_path,
        }

    def test_provenance_identity_changes_for_source_recipe_and_toolchain(self) -> None:
        selection = self.make_selection()
        record = selection["targets"]["arm64"]["golden_record"]
        original = pipeline.provenance_identity_sha256(record)
        for path, replacement in (
            (("source", "resolved_commit"), "9" * 40),
            (("recipe", "pipeline_sha256"), "9" * 64),
            (("toolchain", "resolved_image_id"), f"sha256:{'9' * 64}"),
        ):
            changed = copy.deepcopy(record)
            changed[path[0]][path[1]] = replacement
            self.assertNotEqual(original, pipeline.provenance_identity_sha256(changed))

        legacy_build = copy.deepcopy(record)
        legacy_build["build"] = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
        }
        self.assertEqual(
            original, pipeline.provenance_identity_sha256(legacy_build)
        )
        timestamped = copy.deepcopy(legacy_build)
        timestamped["build"]["source_date_epoch"] = 1782602899
        timestamped_digest = pipeline.provenance_identity_sha256(timestamped)
        self.assertNotEqual(original, timestamped_digest)
        timestamped["build"]["source_date_epoch"] += 1
        self.assertNotEqual(
            timestamped_digest, pipeline.provenance_identity_sha256(timestamped)
        )

    def test_v2_provenance_identity_covers_the_complete_archive_binding(self) -> None:
        selection = self.make_selection()
        legacy = selection["targets"]["arm64"]["golden_record"]
        legacy_digest = pipeline.provenance_identity_sha256(legacy)
        current = copy.deepcopy(legacy)
        current["toolchain"]["archive_provenance"] = {
            "lock": {
                "path": "pins/toolchains/local-cache-v1.json",
                "schema_version": 1,
                "lock_id": "local-cache-v1",
                "file_sha256": "1" * 64,
                "content_sha256": "2" * 64,
            },
            "validator": {
                "path": "scripts/toolchain_archive.py",
                "sha256": "7" * 64,
            },
            "architecture": "arm64",
            "archive": {
                "filename": "cores-arm64.tar.gz",
                "sha256": "3" * 64,
                "size": 10,
            },
        }
        current_digest = pipeline.provenance_identity_sha256(current)
        self.assertNotEqual(legacy_digest, current_digest)
        mutations = (
            (("lock", "path"), "pins/toolchains/other.json"),
            (("lock", "schema_version"), 2),
            (("lock", "lock_id"), "other"),
            (("lock", "file_sha256"), "4" * 64),
            (("lock", "content_sha256"), "5" * 64),
            (("validator", "path"), "scripts/other.py"),
            (("validator", "sha256"), "8" * 64),
            (("archive", "filename"), "other.tar.gz"),
            (("archive", "sha256"), "6" * 64),
            (("archive", "size"), 11),
        )
        for path, value in mutations:
            changed = copy.deepcopy(current)
            changed["toolchain"]["archive_provenance"][path[0]][path[1]] = value
            self.assertNotEqual(
                current_digest, pipeline.provenance_identity_sha256(changed)
            )
        changed = copy.deepcopy(current)
        changed["toolchain"]["archive_provenance"]["architecture"] = "armhf"
        self.assertNotEqual(current_digest, pipeline.provenance_identity_sha256(changed))

    def test_pin_digest_and_canonical_store_path_are_enforced(self) -> None:
        document = self.make_pin(self.make_selection())
        self.assertEqual("valid", pipeline.validate_pin_set_document(document)["status"])
        document["cores"]["fixture"]["selection"]["package"]["path"] = "../escape"
        report = pipeline.validate_pin_set_document(document)
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("content digest" in error for error in report["errors"]))
        self.assertTrue(any("canonical" in error for error in report["errors"]))

    def test_selection_policy_is_normative(self) -> None:
        document = self.make_pin(self.make_selection())
        document["selection_policy"]["release_action"] = "recompile"
        document["content_sha256"] = pipeline.pin_set_content_sha256(document)
        report = pipeline.validate_pin_set_document(document)
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("selection policy" in error for error in report["errors"]))

    def test_non_zip_package_cannot_satisfy_complete_core_lock(self) -> None:
        selection = self.make_selection()
        package_path, package_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "packages", b"not a zip package"
        )
        selection["package"].update(
            {
                "path": str(package_path.relative_to(ROOT)),
                "sha256": package_sha,
                "size": package_path.stat().st_size,
            }
        )
        selection["e2e"]["package_sha256"] = package_sha
        for target in selection["targets"].values():
            record = target["golden_record"]
            record["e2e"]["package_sha256"] = package_sha
            record["local_store"]["package"] = {
                "path": str(package_path.relative_to(ROOT)),
                "sha256": package_sha,
            }
        selection["selection_sha256"] = pipeline.selection_content_sha256(selection)
        pin = self.make_pin(selection)
        report = pipeline.validate_pin_set_document(pin, verify_store=True)
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("cannot verify pinned package" in error for error in report["errors"]))

    def test_missing_cas_package_is_a_validation_error_not_an_exception(self) -> None:
        selection = self.make_selection()
        missing_sha = pipeline.sha256_bytes(b"fixture package that was never stored")
        missing_path = pipeline.canonical_store_path("packages", missing_sha)
        self.assertFalse(missing_path.exists())
        selection["package"].update(
            {
                "path": str(missing_path.relative_to(ROOT)),
                "sha256": missing_sha,
            }
        )
        selection["e2e"]["package_sha256"] = missing_sha
        for target in selection["targets"].values():
            record = target["golden_record"]
            record["e2e"]["package_sha256"] = missing_sha
            record["local_store"]["package"] = {
                "path": str(missing_path.relative_to(ROOT)),
                "sha256": missing_sha,
            }
        selection["selection_sha256"] = pipeline.selection_content_sha256(selection)
        report = pipeline.validate_pin_set_document(
            self.make_pin(selection), verify_store=True
        )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("store identity" in error for error in report["errors"]))
        self.assertTrue(any("cannot verify pinned package" in error for error in report["errors"]))

    def test_first_complete_source_order_is_enforced(self) -> None:
        selection = self.make_selection()
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / ".local-e2e") as directory:
            root = Path(directory)
            sources = []
            for index in range(2):
                path = root / f"source-{index}.json"
                source = {
                    "pin_id": f"source-{index}",
                    "content_sha256": str(index + 1) * 64,
                }
                path.write_text(json.dumps(source), encoding="utf-8")
                sources.append(pipeline.golden_source_reference(path, source))
            document = self.make_pin(selection)
            document["sources"] = sources
            document["cores"]["fixture"]["source_index"] = 1
            document["content_sha256"] = pipeline.pin_set_content_sha256(document)
            with mock.patch.object(
                pipeline, "complete_core_bundle", return_value=selection
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ):
                report = pipeline.validate_pin_set_document(
                    document, verify_sources=True
                )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("first-complete" in error for error in report["errors"]))

    def test_three_level_parent_lineage_validates_transitively(self) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory)
            )
            with mock.patch.object(
                pipeline,
                "complete_core_bundle",
                return_value=lineage["selection"],
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "_verify_local_store", return_value=[]
            ):
                report = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
        self.assertEqual({"status": "valid", "errors": []}, report)

    def test_lineage_reuses_intrinsic_package_proof_only_within_one_walk(
        self,
    ) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory)
            )
            with mock.patch.object(
                pipeline,
                "complete_core_bundle",
                return_value=lineage["selection"],
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "_verify_local_store", return_value=[]
            ), mock.patch.object(
                pipeline,
                "_verify_pinned_package",
                wraps=pipeline._verify_pinned_package,
            ) as package_proof:
                first = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
                self.assertEqual({"status": "valid", "errors": []}, first)
                self.assertEqual(1, package_proof.call_count)

                second = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
                self.assertEqual({"status": "valid", "errors": []}, second)
                self.assertEqual(2, package_proof.call_count)

    def test_package_cache_identity_covers_embedded_record_paths(self) -> None:
        selection = self.make_selection()
        context = pipeline._PinValidationContext()
        valid = pipeline._validate_pin_set_document(
            self.make_pin(copy.deepcopy(selection), "cache-source"),
            verify_store=True,
            _validation_context=context,
        )
        self.assertEqual({"status": "valid", "errors": []}, valid)

        changed = copy.deepcopy(selection)
        changed["targets"]["arm64"]["golden_record"]["artifact"][
            "path"
        ] = "alternate_libretro.so"
        self.assertEqual(
            selection["selection_sha256"],
            pipeline.selection_content_sha256(changed),
        )
        report = pipeline._validate_pin_set_document(
            self.make_pin(changed, "cache-collision"),
            verify_store=True,
            _validation_context=context,
        )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(
            any("pinned package" in error for error in report["errors"]),
            report["errors"],
        )

    def test_transitive_lineage_rejects_tampered_grandparent_file(self) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory)
            )
            tampered = copy.deepcopy(lineage["grandparent"])
            tampered["created_at"] = "tampered-without-changing-content-identity"
            pipeline.atomic_write_json(lineage["grandparent_path"], tampered)
            with mock.patch.object(
                pipeline,
                "complete_core_bundle",
                return_value=lineage["selection"],
            ):
                report = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(
            any("parent pin no longer matches its reference" in error for error in report["errors"])
        )

    def test_transitive_lineage_rejects_tampered_ancestor_source(self) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory)
            )
            lineage["source_path"].write_text(
                json.dumps({**lineage["source"], "tampered": True}),
                encoding="utf-8",
            )
            with mock.patch.object(
                pipeline,
                "complete_core_bundle",
                return_value=lineage["selection"],
            ):
                report = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(
            any("source 0 no longer matches the pin" in error for error in report["errors"])
        )

    def test_transitive_lineage_rejects_missing_ancestor_store_entry(self) -> None:
        selection = self.make_selection()
        missing_sha = pipeline.sha256_bytes(b"lineage package that was never stored")
        missing_path = pipeline.canonical_store_path("packages", missing_sha)
        self.assertFalse(missing_path.exists())
        selection["package"].update(
            {
                "path": str(missing_path.relative_to(ROOT)),
                "sha256": missing_sha,
            }
        )
        selection["e2e"]["package_sha256"] = missing_sha
        for target in selection["targets"].values():
            record = target["golden_record"]
            record["e2e"]["package_sha256"] = missing_sha
            record["local_store"]["package"] = {
                "path": str(missing_path.relative_to(ROOT)),
                "sha256": missing_sha,
            }
        selection["selection_sha256"] = pipeline.selection_content_sha256(selection)

        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory), selection
            )
            with mock.patch.object(
                pipeline, "complete_core_bundle", return_value=selection
            ):
                report = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("store identity is invalid" in error for error in report["errors"]))

    def test_transitive_lineage_rejects_parent_scope_drop(self) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory)
            )
            child = copy.deepcopy(lineage["child"])
            child["scope"] = []
            child["cores"] = {}
            child["summary"] = {
                "core_count": 0,
                "retained_parent_count": 0,
                "selected_source_count": 0,
            }
            child["content_sha256"] = pipeline.pin_set_content_sha256(child)
            pipeline.atomic_write_json(lineage["child_path"], child)
            with mock.patch.object(
                pipeline,
                "complete_core_bundle",
                return_value=lineage["selection"],
            ):
                report = pipeline.validate_pin_set_document(
                    child,
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("scope drops parent cores" in error for error in report["errors"]))

    def test_transitive_lineage_rejects_path_cycle_and_excessive_depth(self) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        (ROOT / ".local-e2e").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_directory, tempfile.TemporaryDirectory(
            dir=ROOT / ".local-e2e"
        ) as source_directory:
            lineage = self.make_three_level_lineage(
                Path(pin_directory), Path(source_directory)
            )
            with mock.patch.object(
                pipeline,
                "complete_core_bundle",
                return_value=lineage["selection"],
            ), mock.patch.object(pipeline, "MAX_PIN_PARENT_DEPTH", 1):
                depth_report = pipeline.validate_pin_set_document(
                    lineage["child"],
                    verify_store=True,
                    verify_sources=True,
                    document_path=lineage["child_path"],
                )

            cycle = copy.deepcopy(lineage["child"])
            cycle["parent"] = {
                "path": str(lineage["child_path"].relative_to(ROOT)),
                "pin_id": cycle["pin_id"],
                "file_sha256": "a" * 64,
                "content_sha256": cycle["content_sha256"],
            }
            cycle["content_sha256"] = pipeline.pin_set_content_sha256(cycle)
            pipeline.atomic_write_json(lineage["child_path"], cycle)
            cycle_report = pipeline.validate_pin_set_document(
                cycle,
                verify_store=True,
                verify_sources=True,
                document_path=lineage["child_path"],
            )
        self.assertEqual("invalid", depth_report["status"])
        self.assertTrue(any("maximum depth" in error for error in depth_report["errors"]))
        self.assertEqual("invalid", cycle_report["status"])
        self.assertTrue(any("path cycle" in error for error in cycle_report["errors"]))

    def test_lineage_context_rejects_repeated_immutable_identity(self) -> None:
        document = self.make_pin(self.make_selection(), "repeated-pin")
        identity = (document["pin_id"], document["content_sha256"])
        report = pipeline._validate_pin_set_document(
            document,
            verify_sources=True,
            _lineage_identities=frozenset({identity}),
        )
        self.assertEqual("invalid", report["status"])
        self.assertTrue(
            any("repeats an immutable pin identity" in error for error in report["errors"])
        )

    def test_compose_api_has_no_parent_lineage_form(self) -> None:
        with self.assertRaisesRegex(TypeError, "parent_path"):
            pipeline.compose_pin_set(
                pin_id="fixture",
                core_ids=["fixture"],
                source_paths=[Path("source.json")],
                output_path=Path("pin.json"),
                parent_path=Path("parent.json"),  # type: ignore[call-arg]
            )

    def test_compose_rejects_multiple_core_scope(self) -> None:
        with self.assertRaisesRegex(pipeline.PipelineError, "exactly one core"):
            pipeline.compose_pin_set(
                pin_id="fixture",
                core_ids=["fixture", "added"],
                source_paths=[Path("source.json")],
                output_path=Path("pin.json"),
            )

    def test_compose_rejects_multiple_sources(self) -> None:
        with self.assertRaisesRegex(pipeline.PipelineError, "one source"):
            pipeline.compose_pin_set(
                pin_id="fixture",
                core_ids=["fixture"],
                source_paths=[Path("one.json"), Path("two.json")],
                output_path=Path("pin.json"),
            )

    def test_failed_candidate_requires_record_bound_log_evidence(self) -> None:
        selection = self.make_selection()
        log_path, log_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "logs", b"failed build log\n"
        )
        self.assertTrue(log_path.is_file())
        record = {
            "core_id": "fixture",
            "architecture": "arm64",
            "result": "failed",
            "local_only": True,
            "publication": "disabled",
            "build": {"log_sha256": log_sha},
        }
        record_bytes = (json.dumps(record, sort_keys=True) + "\n").encode()
        record_path, record_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "build-records", record_bytes
        )
        reason = "core target set is incomplete"
        evidence = {
            "schema_version": 1,
            "run_id": "failed-fixture",
            "local_only": True,
            "publication": "disabled",
            "result": "failed",
            "workflow_audit": {},
            "builds": [
                {
                    "core_id": "fixture",
                    "architecture": "arm64",
                    "result": "failed",
                    "record": "ignored-by-frozen-validation.json",
                    "record_sha256": record_sha,
                }
            ],
            "packages": [
                {"core_id": "fixture", "result": "not_packaged", "reason": reason}
            ],
        }
        evidence["content_sha256"] = pipeline.e2e_content_sha256(evidence)
        evidence_bytes = (json.dumps(evidence, sort_keys=True) + "\n").encode()
        evidence_path, evidence_sha = pipeline.store_bytes(
            pipeline.DEFAULT_STORE, "e2e", evidence_bytes
        )
        document = self.make_pin(selection)
        document["parent"] = {
            "path": "pins/core-sets/fixture-parent.json",
            "pin_id": "fixture-parent",
            "file_sha256": "a" * 64,
            "content_sha256": "b" * 64,
        }
        core = document["cores"]["fixture"]
        core["decision"] = "retain_parent"
        core.pop("source_index")
        core["failed_candidate"] = {
            "run_id": evidence["run_id"],
            "content_sha256": evidence["content_sha256"],
            "record": {
                "path": str(evidence_path.relative_to(ROOT)),
                "sha256": evidence_sha,
            },
            "reason": reason,
            "build_records": {
                "arm64": {
                    "result": "failed",
                    "record": {
                        "path": str(record_path.relative_to(ROOT)),
                        "sha256": record_sha,
                    },
                }
            },
        }
        document["summary"]["retained_parent_count"] = 1
        document["summary"]["selected_source_count"] = 0
        document["content_sha256"] = pipeline.pin_set_content_sha256(document)
        report = pipeline.validate_pin_set_document(document, verify_store=True)
        self.assertEqual("invalid", report["status"])
        self.assertTrue(any("log evidence is missing" in error for error in report["errors"]))

    def test_release_copies_exact_bytes_without_building_and_is_immutable(self) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        pipeline.DEFAULT_RELEASES.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=pipeline.DEFAULT_PIN_SET_DIR) as pin_dir, tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_RELEASES
        ) as release_parent:
            selection = self.make_selection()
            semantic_id = pipeline.individual_core_semantic_id(
                "fixture", selection
            )
            pin_path = Path(pin_dir) / f"{semantic_id}.json"
            pin = self.make_pin(selection, semantic_id)
            pin["created_at"] = "2026-01-02T03:04:05+00:00"
            pin["sources"] = [
                {
                    "path": f".local-e2e/nightlies/{semantic_id}/golden.json",
                    "pin_id": "fixture-golden",
                    "file_sha256": "a" * 64,
                    "content_sha256": "b" * 64,
                }
            ]
            pin["content_sha256"] = pipeline.pin_set_content_sha256(pin)
            pipeline.atomic_create_json(pin_path, pin)
            release_path = Path(release_parent) / semantic_id
            with mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", Path(pin_dir)
            ), mock.patch.object(
                pipeline, "DEFAULT_RELEASES", Path(release_parent)
            ), mock.patch.object(
                pipeline, "perform_build", side_effect=AssertionError("build called")
            ), mock.patch.object(
                pipeline, "run", side_effect=AssertionError("subprocess called")
            ), mock.patch.object(
                pipeline,
                "validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "require_pin_sources_eligible", return_value=None
            ), mock.patch.object(
                pipeline,
                "_require_public_ordinary_catalog",
                return_value=pipeline.sha256_file(pipeline.DEFAULT_CATALOG),
            ), mock.patch.object(
                pipeline,
                "_require_pin_current_selection_authority",
                return_value=None,
            ):
                manifest = pipeline.promote_local_release(pin_path, release_path)
                package = pin["cores"]["fixture"]["selection"]["package"]
                released = release_path / package["name"]
                self.assertEqual(package["sha256"], pipeline.sha256_file(released))
                self.assertEqual(
                    "valid",
                    pipeline.validate_local_release(
                        release_path, pin, pipeline.sha256_file(pin_path)
                    )["status"],
                )
                self.assertEqual(pin["created_at"], manifest["created_at"])
                with self.assertRaisesRegex(pipeline.PipelineError, "refusing to replace"):
                    pipeline.promote_local_release(pin_path, release_path)
                released.write_bytes(b"tampered")
                self.assertEqual(
                    "invalid",
                    pipeline.validate_local_release(
                        release_path, pin, pipeline.sha256_file(pin_path)
                    )["status"],
                )
                self.assertEqual("disabled", manifest["publication"])

    def test_release_rechecks_the_catalog_snapshot_after_source_authority(
        self,
    ) -> None:
        pipeline.DEFAULT_PIN_SET_DIR.mkdir(parents=True, exist_ok=True)
        pipeline.DEFAULT_RELEASES.mkdir(parents=True, exist_ok=True)
        canonical_catalog = pipeline.load_json(pipeline.DEFAULT_CATALOG)
        real_sha256_file = pipeline.sha256_file
        digest_a = "a" * 64
        digest_b = "b" * 64
        events: list[str] = []

        with tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_PIN_SET_DIR
        ) as pin_dir, tempfile.TemporaryDirectory(
            dir=pipeline.DEFAULT_RELEASES
        ) as release_parent:
            selection = self.make_selection()
            semantic_id = pipeline.individual_core_semantic_id(
                "fixture", selection
            )
            pin_path = Path(pin_dir) / f"{semantic_id}.json"
            pin = self.make_pin(selection, semantic_id)
            pin["sources"] = [
                {
                    "path": (
                        f".local-e2e/nightlies/{semantic_id}/golden.json"
                    ),
                    "pin_id": "fixture-golden",
                    "file_sha256": "c" * 64,
                    "content_sha256": "d" * 64,
                }
            ]
            pin["content_sha256"] = pipeline.pin_set_content_sha256(pin)
            pipeline.atomic_create_json(pin_path, pin)
            release_path = Path(release_parent) / semantic_id

            def capture_catalog(
                _path: Path,
                document: dict,
                **_kwargs: object,
            ) -> str:
                events.append("catalog-snapshot-a")
                self.assertEqual(canonical_catalog, document)
                return digest_a

            def authorize_pin(
                _pin: dict,
                *,
                operation: str,
                catalog: dict | None = None,
            ) -> None:
                events.append("source-authority-a")
                self.assertEqual("local release promotion", operation)
                self.assertEqual(canonical_catalog, catalog)

            def drifted_sha256(path: Path) -> str:
                if path.resolve() == pipeline.DEFAULT_CATALOG.resolve():
                    events.append("catalog-recheck-b")
                    return digest_b
                return real_sha256_file(path)

            with mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", Path(pin_dir)
            ), mock.patch.object(
                pipeline, "DEFAULT_RELEASES", Path(release_parent)
            ), mock.patch.object(
                pipeline,
                "validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "_require_public_ordinary_catalog",
                side_effect=capture_catalog,
            ), mock.patch.object(
                pipeline,
                "_require_pin_current_selection_authority",
                side_effect=authorize_pin,
            ), mock.patch.object(
                pipeline, "require_pin_sources_eligible", return_value=None
            ), mock.patch.object(
                pipeline, "sha256_file", side_effect=drifted_sha256
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "canonical catalog changed before release promotion",
            ):
                pipeline.promote_local_release(pin_path, release_path)

            self.assertEqual(
                [
                    "catalog-snapshot-a",
                    "source-authority-a",
                    "catalog-recheck-b",
                ],
                events,
            )
            self.assertFalse(release_path.exists())

    def test_validate_release_reports_the_validated_pin_snapshot_digest(self) -> None:
        original = b'{"pin_id":"original"}\n'
        replacement = b'{"pin_id":"replacement"}\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pin_path = root / "pin.json"
            pin_path.write_bytes(original)
            release_path = root / "release"

            def validate_and_replace(document: dict, **_kwargs) -> dict:
                self.assertEqual({"pin_id": "original"}, document)
                pin_path.write_bytes(replacement)
                return {"status": "valid", "errors": []}

            with mock.patch.object(
                pipeline,
                "validate_pin_set_document",
                side_effect=validate_and_replace,
            ), mock.patch.object(
                pipeline,
                "validate_local_release",
                return_value={"status": "valid", "errors": []},
            ) as validate_release, mock.patch.object(
                pipeline,
                "sha256_file",
                side_effect=AssertionError("validated pin path was rehashed"),
            ) as rehash, mock.patch("sys.stdout", new=io.StringIO()):
                result = pipeline.cmd_validate_release(
                    argparse.Namespace(
                        pin_set=pin_path,
                        release=release_path,
                        verify_store=False,
                    )
                )

            self.assertEqual(0, result)
            validate_release.assert_called_once_with(
                release_path,
                {"pin_id": "original"},
                pipeline.sha256_bytes(original),
            )
            rehash.assert_not_called()
            self.assertEqual(replacement, pin_path.read_bytes())


class ChannelPointerTests(unittest.TestCase):
    def test_validate_local_release_uses_bound_manifest_without_reopening(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            releases = Path(directory) / "releases"
            release_root = releases / "release-one"
            release_root.mkdir(parents=True)
            pin = {
                "pin_id": "pin-one",
                "content_sha256": "a" * 64,
                "scope": [],
                "cores": {},
            }
            pin_file_sha256 = "b" * 64
            manifest = {
                "schema_version": 1,
                "release_id": "release-one",
                "local_only": True,
                "publication": "disabled",
                "pin": {
                    "pin_id": pin["pin_id"],
                    "content_sha256": pin["content_sha256"],
                    "file_sha256": pin_file_sha256,
                },
                "assets": [],
            }
            manifest["content_sha256"] = pipeline.release_content_sha256(
                manifest
            )
            # The directory inventory still requires this path, but its bytes
            # must not replace the already-bound manifest snapshot.
            (release_root / "release-manifest.json").write_bytes(b"not JSON")

            with mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ), mock.patch.object(
                pipeline,
                "load_json_with_sha256",
                side_effect=AssertionError("release manifest reopened"),
            ) as reopen:
                report = pipeline._validate_local_release(
                    release_root,
                    pin,
                    pin_file_sha256,
                    manifest_document=manifest,
                )

            self.assertEqual({"status": "valid", "errors": []}, report)
            reopen.assert_not_called()

    def test_release_channel_derivation_keeps_one_manifest_snapshot_through_aba(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            releases = root / "releases"
            target = releases / "release-one" / "release-manifest.json"
            target.parent.mkdir(parents=True)
            pin_path = root / "pins" / "pin-one.json"
            pin_path.parent.mkdir()
            pin_path.write_text("{}\n", encoding="utf-8")
            pin = {"pin_id": "pin-one", "content_sha256": "c" * 64}
            original = {
                "release_id": "release-one",
                "content_sha256": "a" * 64,
                "pin": {"file_sha256": "b" * 64},
            }
            replacement = {
                "release_id": "release-two",
                "content_sha256": "d" * 64,
                "pin": {"file_sha256": "e" * 64},
            }
            original_bytes = (
                json.dumps(original, sort_keys=True) + "\n"
            ).encode()
            replacement_bytes = (
                json.dumps(replacement, sort_keys=True) + "\n"
            ).encode()
            target.write_bytes(original_bytes)
            bound_documents: list[dict | None] = []

            def swap_to_replacement(
                manifest: dict,
                _validation_context: object | None = None,
            ) -> tuple[dict, Path]:
                self.assertEqual(original, manifest)
                target.write_bytes(replacement_bytes)
                return pin, pin_path

            def validate_bound_manifest(
                _release_root: Path,
                _pin: dict,
                _pin_file_sha256: str,
                expected_release_id: str | None = None,
                *,
                manifest_document: dict | None = None,
            ) -> dict:
                self.assertEqual("release-one", expected_release_id)
                self.assertEqual(replacement_bytes, target.read_bytes())
                bound_documents.append(manifest_document)
                target.write_bytes(original_bytes)
                return {
                    "status": (
                        "valid" if manifest_document == original else "invalid"
                    ),
                    "errors": (
                        []
                        if manifest_document == original
                        else ["release manifest was reopened"]
                    ),
                }

            real_snapshot_json_file = pipeline.snapshot_json_file
            with mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ), mock.patch.object(
                pipeline,
                "snapshot_json_file",
                wraps=real_snapshot_json_file,
            ) as snapshot, mock.patch.object(
                pipeline,
                "load_json_with_sha256",
                side_effect=AssertionError("release manifest reopened"),
            ) as reopen, mock.patch.object(
                pipeline,
                "load_json",
                side_effect=AssertionError("release manifest reopened"),
            ) as legacy_reopen, mock.patch.object(
                pipeline,
                "_resolve_release_pin",
                side_effect=swap_to_replacement,
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "_require_pin_current_selection_authority",
                return_value=None,
            ), mock.patch.object(
                pipeline,
                "_validate_local_release",
                side_effect=validate_bound_manifest,
            ):
                derived = pipeline.derive_channel_target("release", target)

            self.assertEqual("release-one", derived["id"])
            self.assertEqual(
                pipeline.sha256_bytes(original_bytes), derived["file_sha256"]
            )
            self.assertEqual([original], bound_documents)
            self.assertEqual(original_bytes, target.read_bytes())
            snapshot.assert_called_once()
            reopen.assert_not_called()
            legacy_reopen.assert_not_called()

    def test_current_channel_pointer_rejects_utf16_and_utf32(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            channels = Path(directory) / "channels"
            channels.mkdir()
            pointer_path = channels / "nightly.handy.json"
            target = (
                ROOT
                / ".local-e2e"
                / "nightlies"
                / "missing"
                / "golden.json"
            )
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline,
                "load_json",
                return_value={"cores": {"handy": {}}},
            ), mock.patch.object(
                pipeline,
                "_require_public_ordinary_catalog",
                return_value=pipeline.sha256_file(pipeline.DEFAULT_CATALOG),
            ), mock.patch.object(
                pipeline,
                "derive_channel_target",
                side_effect=AssertionError("invalid pointer was accepted"),
            ) as derive:
                for encoding in ("utf-16", "utf-32"):
                    with self.subTest(encoding=encoding):
                        encoded = json.dumps({"channel": "nightly"}).encode(
                            encoding
                        )
                        pointer_path.write_bytes(encoded)
                        with self.assertRaisesRegex(
                            pipeline.PipelineError,
                            "current channel pointer is not valid JSON",
                        ):
                            pipeline.update_channel(
                                "nightly",
                                target,
                                core_id="handy",
                                expect_current=pipeline.sha256_bytes(encoded),
                            )
                        self.assertEqual(encoded, pointer_path.read_bytes())

            derive.assert_not_called()

    def test_validate_channel_reports_the_validated_pointer_snapshot_digest(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        original = b'{"channel":"nightly","marker":"original"}\n'
        replacement = b'{"channel":"nightly","marker":"replacement"}\n'
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            channels = Path(directory) / "channels"
            channels.mkdir()
            pointer_path = channels / "nightly.handy.json"
            pointer_path.write_bytes(original)

            def validate_and_replace(document: dict, **_kwargs) -> dict:
                self.assertEqual(
                    {"channel": "nightly", "marker": "original"}, document
                )
                pointer_path.write_bytes(replacement)
                return {"status": "valid", "errors": []}

            output = io.StringIO()
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline,
                "validate_channel_pointer_document",
                side_effect=validate_and_replace,
            ), mock.patch.object(
                pipeline,
                "sha256_file",
                side_effect=AssertionError("validated pointer path was rehashed"),
            ) as rehash, mock.patch("sys.stdout", new=output):
                result = pipeline.cmd_validate_channel(
                    argparse.Namespace(channel="nightly", core="handy")
                )

            report = json.loads(output.getvalue())
            self.assertEqual(0, result)
            self.assertEqual(
                pipeline.sha256_bytes(original), report["pointer_file_sha256"]
            )
            rehash.assert_not_called()
            self.assertEqual(replacement, pointer_path.read_bytes())

    def test_release_pin_resolution_hashes_and_parses_one_captured_snapshot(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        source_pin_path = (
            ROOT
            / "pins"
            / "core-sets"
            / "handy-bc55d462f0b2-c82a2178b4f0.json"
        )
        source_bytes = source_pin_path.read_bytes()
        source_pin = json.loads(source_bytes)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            pins = Path(directory) / "pins"
            pins.mkdir()
            candidate = pins / source_pin_path.name
            candidate.write_bytes(source_bytes)
            manifest = {
                "pin": {
                    "pin_id": source_pin["pin_id"],
                    "file_sha256": pipeline.sha256_bytes(source_bytes),
                    "content_sha256": source_pin["content_sha256"],
                }
            }
            context = pipeline._PinValidationContext()

            with mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                Path,
                "read_bytes",
                side_effect=[source_bytes, b'{"pin_id":"replacement"}\n'],
            ) as read_bytes, mock.patch.object(
                pipeline,
                "sha256_file",
                side_effect=AssertionError("pin hashed before parsing"),
            ) as separate_hash, mock.patch.object(
                pipeline,
                "load_json",
                side_effect=AssertionError("pin reopened after hashing"),
            ) as reopen:
                resolved, resolved_path = pipeline._resolve_release_pin(
                    manifest, context
                )

            self.assertEqual(source_pin, resolved)
            self.assertEqual(candidate, resolved_path)
            read_bytes.assert_called_once_with()
            separate_hash.assert_not_called()
            reopen.assert_not_called()

    def test_release_pin_resolution_uses_only_flat_canonical_singletons(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        source_pin_path = (
            ROOT
            / "pins"
            / "core-sets"
            / "handy-bc55d462f0b2-c82a2178b4f0.json"
        )
        source_pin = pipeline.load_json(source_pin_path)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            pins = Path(directory) / "pins"
            pins.mkdir()
            flat_pin_path = pins / source_pin_path.name
            flat_pin_path.write_bytes(source_pin_path.read_bytes())
            nested_pin_path = pins / "legacy" / source_pin_path.name
            nested_pin_path.parent.mkdir()
            nested_pin_path.write_bytes(source_pin_path.read_bytes())
            release_manifest = {
                "pin": {
                    "pin_id": source_pin["pin_id"],
                    "file_sha256": pipeline.sha256_file(flat_pin_path),
                    "content_sha256": source_pin["content_sha256"],
                }
            }

            with mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins):
                resolved, resolved_path = pipeline.resolve_release_pin(
                    release_manifest
                )
                self.assertEqual(source_pin, resolved)
                self.assertEqual(flat_pin_path, resolved_path)

                aggregate = copy.deepcopy(source_pin)
                aggregate["parent"] = {
                    "path": "pins/core-sets/historical.json"
                }
                aggregate_path = pins / "historical.json"
                aggregate_path.write_text(
                    json.dumps(aggregate),
                    encoding="utf-8",
                )
                aggregate_manifest = {
                    "pin": {
                        "pin_id": aggregate["pin_id"],
                        "file_sha256": pipeline.sha256_file(aggregate_path),
                        "content_sha256": aggregate["content_sha256"],
                    }
                }
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "exactly one immutable pin-set document",
                ):
                    pipeline.resolve_release_pin(aggregate_manifest)

    def nightly_semantic_id(
        self,
        selection_sha256: str,
        source_commit: str = "bc55d462f0b2d6b073ea93dc552ebd73cec60fd1",
        core_id: str = "handy",
    ) -> str:
        return (
            f"{core_id}-{source_commit[:12]}-{selection_sha256[:12]}"
        )

    def make_nightly_target(
        self,
        path: Path,
        selection_sha256: str = "1" * 64,
        source_commit: str = "bc55d462f0b2d6b073ea93dc552ebd73cec60fd1",
        core_id: str = "handy",
    ) -> bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 2,
            "core_id": core_id,
            "pin_id": path.parent.name,
            "content_sha256": "c" * 64,
            "cores": {core_id: {}},
            "build_goldens": {
                core_id: {
                    "test_selection_sha256": selection_sha256,
                    "test_source_commit": source_commit,
                    "test_source_url": (
                        "https://github.com/libretro/libretro-handy.git"
                    ),
                }
            },
        }
        rendered = (json.dumps(document, sort_keys=True) + "\n").encode()
        path.write_bytes(rendered)
        return rendered

    def nightly_validation_patches(self):
        canonical_catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)

        def complete(document: dict, core_id: str) -> dict | None:
            build_goldens = document.get("build_goldens")
            if not isinstance(build_goldens, dict):
                return None
            fixture = build_goldens.get(core_id)
            if not isinstance(fixture, dict):
                return None
            return {
                "selection_sha256": fixture["test_selection_sha256"],
                "targets": {
                    "arm64": {
                        "golden_record": {
                            "source": {
                                "url": fixture["test_source_url"],
                                "commit": fixture["test_source_commit"],
                            }
                        }
                    }
                },
            }

        @contextmanager
        def complete_and_authorize():
            with (
                mock.patch.object(
                    pipeline, "complete_core_bundle", side_effect=complete
                ) as complete_mock,
                mock.patch.object(
                    pipeline,
                    "_require_current_selection_source_authority",
                    return_value=None,
                ),
                mock.patch.object(
                    pipeline,
                    "load_catalog",
                    return_value=canonical_catalog,
                ),
                mock.patch.object(
                    pipeline,
                    "_require_public_ordinary_catalog",
                    return_value=pipeline.sha256_file(
                        pipeline.DEFAULT_CATALOG
                    ),
                ),
            ):
                yield complete_mock

        return (
            mock.patch.object(
                pipeline,
                "validate_golden_document",
                side_effect=lambda _document: {"status": "valid", "errors": []},
            ),
            mock.patch.object(pipeline, "_verify_local_store", return_value=[]),
            complete_and_authorize(),
        )

    def make_individual_nightly_target(
        self, path: Path, core_id: str, pin_id: str
    ) -> bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 2,
            "core_id": core_id,
            "pin_id": pin_id,
            "content_sha256": "c" * 64,
            "cores": {core_id: {}},
            "build_goldens": {core_id: {"arm64": {}, "armhf": {}}},
        }
        rendered = (json.dumps(document, sort_keys=True) + "\n").encode()
        path.write_bytes(rendered)
        return rendered

    def test_compose_core_golden_creates_exact_scope_semantic_projection(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            source = (
                nightlies / "handy-candidate-fixture" / "golden.json"
            )
            source.parent.mkdir(parents=True)
            source.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "core_id": "handy",
                        "pin_id": "handy-candidate-fixture",
                        "created_at": "2026-01-02T03:04:05+00:00",
                        "baseline": {"repository_commit": "f" * 40},
                        "cores": {"handy": {}},
                        "build_goldens": {
                            "handy": {"arm64": {}, "armhf": {}},
                        }
                    }
                ),
                encoding="utf-8",
            )
            selection_sha256 = "b" * 64
            source_commit = "a" * 40
            semantic_id = f"handy-{source_commit[:12]}-{selection_sha256[:12]}"
            output = nightlies / semantic_id / "golden.json"
            selection = {
                "selection_sha256": selection_sha256,
                "targets": {
                    architecture: {
                        "golden_record": {
                            "source": {"commit": source_commit}
                        }
                    }
                    for architecture in ("arm64", "armhf")
                },
            }
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "load_catalog", return_value={"cores": {"handy": {}}}
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "complete_core_bundle", return_value=selection
            ), mock.patch.object(
                pipeline,
                "_require_catalog_bound_source_candidate_selection",
                return_value=None,
            ), mock.patch.object(
                pipeline, "verify_local_store", return_value=[]
            ):
                identity = pipeline.derive_core_id(
                    core_id="handy",
                    source_path=source,
                )
                self.assertEqual(semantic_id, identity["semantic_id"])
                self.assertEqual(
                    str(output.relative_to(ROOT)),
                    identity["nightly_golden"],
                )
                result = pipeline.compose_core_golden(
                    core_id="handy",
                    source_path=source,
                    output_path=output,
                )
                projected = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual("created", result["status"])
                self.assertEqual(semantic_id, result["semantic_id"])
                self.assertEqual({"handy"}, set(projected["build_goldens"]))
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "refusing to replace"
                ):
                    pipeline.compose_core_golden(
                        core_id="handy",
                        source_path=source,
                        output_path=output,
                    )

    def test_individual_channel_create_cas_and_core_namespaces_are_isolated(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            source_commits = {"handy": "a" * 40, "stella2014": "b" * 40}
            selection_digests = {
                "handy-one": "1" * 64,
                "handy-two": "2" * 64,
                "stella-one": "3" * 64,
            }

            def semantic_id(core_id: str, label: str) -> str:
                return (
                    f"{core_id}-{source_commits[core_id][:12]}-"
                    f"{selection_digests[label][:12]}"
                )

            handy_one_id = semantic_id("handy", "handy-one")
            handy_two_id = semantic_id("handy", "handy-two")
            stella_id = semantic_id("stella2014", "stella-one")
            handy_one = nightlies / handy_one_id / "golden.json"
            handy_two = nightlies / handy_two_id / "golden.json"
            stella = nightlies / stella_id / "golden.json"
            self.make_individual_nightly_target(
                handy_one, "handy", handy_one_id
            )
            self.make_individual_nightly_target(
                handy_two, "handy", handy_two_id
            )
            self.make_individual_nightly_target(
                stella, "stella2014", stella_id
            )

            def complete(document: dict, core_id: str) -> dict | None:
                if core_id not in document.get("build_goldens", {}):
                    return None
                label_by_pin_id = {
                    handy_one_id: "handy-one",
                    handy_two_id: "handy-two",
                    stella_id: "stella-one",
                }
                label = label_by_pin_id[document["pin_id"]]
                return {
                    "selection_sha256": selection_digests[label],
                    "targets": {
                        "arm64": {
                            "golden_record": {
                                "source": {"commit": source_commits[core_id]}
                            }
                        }
                    },
                }

            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline, "_verify_local_store", return_value=[]
            ), mock.patch.object(
                pipeline, "complete_core_bundle", side_effect=complete
            ), mock.patch.object(
                pipeline,
                "_require_current_selection_source_authority",
                return_value=None,
            ), mock.patch.object(
                pipeline,
                "_require_channel_target_sources_eligible",
                return_value=None,
            ):
                handy_created = pipeline.update_channel(
                    "nightly",
                    handy_one,
                    core_id="handy",
                    expect_absent=True,
                )
                pipeline.update_channel(
                    "nightly",
                    stella,
                    core_id="stella2014",
                    expect_absent=True,
                )
                stella_before = (channels / "nightly.stella2014.json").read_bytes()
                pipeline.update_channel(
                    "nightly",
                    handy_two,
                    core_id="handy",
                    expect_current=handy_created["pointer_file_sha256"],
                )
                self.assertEqual(
                    stella_before,
                    (channels / "nightly.stella2014.json").read_bytes(),
                )
                self.assertFalse((channels / "nightly.json").exists())
                handy_pointer = json.loads(
                    (channels / "nightly.handy.json").read_text(encoding="utf-8")
                )
                self.assertEqual(2, handy_pointer["schema_version"])
                self.assertEqual("handy", handy_pointer["core_id"])
                self.assertEqual(handy_two_id, handy_pointer["target"]["id"])
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "exactly its core"
                ):
                    pipeline.update_channel(
                        "nightly",
                        stella,
                        core_id="handy",
                        expect_current=pipeline.sha256_file(
                            channels / "nightly.handy.json"
                        ),
                    )

    def test_individual_channel_rejects_malformed_catalog_core_map(self) -> None:
        with mock.patch.object(
            pipeline, "load_json", return_value={"cores": None}
        ), mock.patch.object(
            pipeline,
            "_require_public_ordinary_catalog",
            return_value=pipeline.sha256_file(pipeline.DEFAULT_CATALOG),
        ), self.assertRaisesRegex(
            pipeline.PipelineError, "catalog cores must be an object"
        ):
            pipeline.update_channel(
                "nightly",
                ROOT / ".local-e2e" / "nightlies" / "missing" / "golden.json",
                core_id="handy",
                expect_absent=True,
            )

    def test_individual_nightly_rejects_non_object_build_goldens_fail_closed(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            nightlies = Path(directory) / "nightlies"
            for label, malformed in (("null", None), ("list", [])):
                with self.subTest(label=label):
                    target = nightlies / f"handy-{label}" / "golden.json"
                    target.parent.mkdir(parents=True)
                    target.write_text(
                        json.dumps(
                            {
                                "pin_id": "base",
                                "content_sha256": "c" * 64,
                                "build_goldens": malformed,
                            }
                        ),
                        encoding="utf-8",
                    )
                    with mock.patch.object(
                        pipeline, "DEFAULT_NIGHTLIES", nightlies
                    ), mock.patch.object(
                        pipeline,
                        "validate_golden_document",
                        return_value={"status": "valid", "errors": []},
                    ), mock.patch.object(
                        pipeline, "_verify_local_store", return_value=[]
                    ), self.assertRaisesRegex(
                        pipeline.PipelineError,
                        "individual nightly channel target must contain exactly its core",
                    ):
                        pipeline.derive_channel_target(
                            "nightly", target, core_id="handy"
                        )

    def test_channel_create_is_durable_pointer_only_and_returns_validation_token(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            semantic_id = self.nightly_semantic_id("1" * 64)
            target_path = nightlies / semantic_id / "golden.json"
            target_bytes = self.make_nightly_target(target_path)
            validation, store, complete = self.nightly_validation_patches()
            real_link = pipeline.os.link
            real_unlink = pipeline.os.unlink
            real_fsync = pipeline.os.fsync
            durability_events: list[str] = []

            def recording_link(source, destination):
                durability_events.append("link")
                return real_link(source, destination)

            def recording_unlink(path, *args, **kwargs):
                durability_events.append("unlink")
                return real_unlink(path, *args, **kwargs)

            def recording_fsync(file_descriptor):
                durability_events.append("fsync")
                return real_fsync(file_descriptor)

            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), validation, store, complete, mock.patch.object(
                pipeline, "perform_build", side_effect=AssertionError("build called")
            ), mock.patch.object(
                pipeline, "run", side_effect=AssertionError("subprocess called")
            ), mock.patch.object(
                pipeline,
                "promote_local_release",
                side_effect=AssertionError("release promotion called"),
            ), mock.patch.object(
                pipeline.shutil,
                "copyfile",
                side_effect=AssertionError("copy called"),
            ), mock.patch.object(
                pipeline.os, "link", side_effect=recording_link
            ) as link, mock.patch.object(
                pipeline.os, "unlink", side_effect=recording_unlink
            ), mock.patch.object(
                pipeline.os, "fsync", side_effect=recording_fsync
            ) as fsync:
                result = pipeline.update_channel(
                    "nightly",
                    target_path,
                    core_id="handy",
                    expect_absent=True,
                )
                pointer_path = channels / "nightly.handy.json"
                pointer_bytes = pointer_path.read_bytes()
                pointer = json.loads(pointer_bytes)
                self.assertEqual(target_bytes, target_path.read_bytes())
                self.assertEqual(
                    {
                        "$schema",
                        "schema_version",
                        "channel",
                        "core_id",
                        "updated_at",
                        "local_only",
                        "publication",
                        "target",
                    },
                    set(pointer),
                )
                self.assertEqual(
                    {"kind", "path", "id", "file_sha256", "content_sha256"},
                    set(pointer["target"]),
                )
                self.assertEqual(pipeline.sha256_bytes(pointer_bytes), result["pointer_file_sha256"])
                output = io.StringIO()
                with mock.patch("sys.stdout", new=output):
                    exit_code = pipeline.cmd_validate_channel(
                        argparse.Namespace(channel="nightly", core="handy")
                    )
                validated = json.loads(output.getvalue())
                self.assertEqual(0, exit_code)
                self.assertEqual(result["pointer_file_sha256"], validated["pointer_file_sha256"])
                self.assertEqual("handy", validated["core_id"])
                self.assertTrue(link.called)
                self.assertGreaterEqual(fsync.call_count, 2)
                link_index = durability_events.index("link")
                unlink_index = durability_events.index("unlink")
                self.assertLess(link_index, unlink_index)
                self.assertIn("fsync", durability_events[unlink_index + 1 :])
                self.assertEqual(
                    {"nightly.handy.json"},
                    {path.name for path in channels.iterdir()},
                )

    def test_channel_update_returns_the_exact_rendered_pointer_digest_without_reopen(
        self,
    ) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            semantic_id = self.nightly_semantic_id("1" * 64)
            target_path = nightlies / semantic_id / "golden.json"
            self.make_nightly_target(target_path)
            pointer_path = channels / "nightly.handy.json"
            real_sha256_file = pipeline.sha256_file

            def reject_pointer_reopen(path: Path) -> str:
                if path == pointer_path:
                    raise AssertionError("written channel pointer was reopened")
                return real_sha256_file(path)

            validation, store, complete = self.nightly_validation_patches()
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), validation, store, complete, mock.patch.object(
                pipeline,
                "sha256_file",
                side_effect=reject_pointer_reopen,
            ):
                result = pipeline.update_channel(
                    "nightly",
                    target_path,
                    core_id="handy",
                    expect_absent=True,
                )

            pointer_bytes = pointer_path.read_bytes()
            pointer_document = json.loads(pointer_bytes)
            expected_bytes = (
                json.dumps(pointer_document, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            self.assertEqual(expected_bytes, pointer_bytes)
            self.assertEqual(
                pipeline.sha256_bytes(expected_bytes),
                result["pointer_file_sha256"],
            )

    def test_channel_compare_and_swap_is_exact_and_same_target_is_noop(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            first_selection = "1" * 64
            second_selection = "2" * 64
            first_target = (
                nightlies
                / self.nightly_semantic_id(first_selection)
                / "golden.json"
            )
            second_target = (
                nightlies
                / self.nightly_semantic_id(second_selection)
                / "golden.json"
            )
            first_bytes = self.make_nightly_target(
                first_target, first_selection
            )
            second_bytes = self.make_nightly_target(
                second_target, second_selection
            )
            validation, store, complete = self.nightly_validation_patches()
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), validation, store, complete:
                created = pipeline.update_channel(
                    "nightly",
                    first_target,
                    core_id="handy",
                    expect_absent=True,
                )
                pointer_path = channels / "nightly.handy.json"
                original_pointer = pointer_path.read_bytes()
                with self.assertRaisesRegex(pipeline.PipelineError, "exactly one"):
                    pipeline.update_channel(
                        "nightly", second_target, core_id="handy"
                    )
                with self.assertRaisesRegex(pipeline.PipelineError, "already exists"):
                    pipeline.update_channel(
                        "nightly",
                        second_target,
                        core_id="handy",
                        expect_absent=True,
                    )
                with self.assertRaisesRegex(pipeline.PipelineError, "compare-and-swap"):
                    pipeline.update_channel(
                        "nightly",
                        second_target,
                        core_id="handy",
                        expect_current="0" * 64,
                    )
                self.assertEqual(original_pointer, pointer_path.read_bytes())
                with mock.patch.object(
                    pipeline,
                    "durable_atomic_channel_write",
                    side_effect=AssertionError("no-op rewrote pointer"),
                ):
                    unchanged = pipeline.update_channel(
                        "nightly",
                        first_target,
                        core_id="handy",
                        expect_current=created["pointer_file_sha256"],
                    )
                self.assertEqual("unchanged", unchanged["status"])
                self.assertEqual(original_pointer, pointer_path.read_bytes())
                updated = pipeline.update_channel(
                    "nightly",
                    second_target,
                    core_id="handy",
                    expect_current=created["pointer_file_sha256"],
                )
                self.assertEqual("updated", updated["status"])
                self.assertNotEqual(created["pointer_file_sha256"], updated["pointer_file_sha256"])
                self.assertEqual(first_bytes, first_target.read_bytes())
                self.assertEqual(second_bytes, second_target.read_bytes())

    def test_channel_rejects_malformed_current_pointer_and_swapped_alias(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            first_selection = "1" * 64
            second_selection = "2" * 64
            first_target = (
                nightlies
                / self.nightly_semantic_id(first_selection)
                / "golden.json"
            )
            second_target = (
                nightlies
                / self.nightly_semantic_id(second_selection)
                / "golden.json"
            )
            self.make_nightly_target(first_target, first_selection)
            self.make_nightly_target(second_target, second_selection)
            validation, store, complete = self.nightly_validation_patches()
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), validation, store, complete:
                pipeline.update_channel(
                    "nightly",
                    first_target,
                    core_id="handy",
                    expect_absent=True,
                )
                pointer_path = channels / "nightly.handy.json"
                valid_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
                legacy_pointer = copy.deepcopy(valid_pointer)
                legacy_pointer["schema_version"] = 1
                legacy_pointer.pop("core_id")
                legacy_report = pipeline.validate_channel_pointer_document(
                    legacy_pointer,
                    expected_channel="nightly",
                    verify_target=False,
                )
                self.assertEqual("valid", legacy_report["status"])
                swapped = copy.deepcopy(legacy_pointer)
                swapped["channel"] = "pinned"
                swapped_report = pipeline.validate_channel_pointer_document(
                    swapped, expected_channel="nightly", verify_target=False
                )
                self.assertEqual("invalid", swapped_report["status"])
                self.assertTrue(any("alias filename" in error for error in swapped_report["errors"]))
                aggregate_report = pipeline.validate_channel_pointer_document(
                    valid_pointer,
                    expected_channel="nightly",
                    verify_target=False,
                )
                self.assertEqual("invalid", aggregate_report["status"])
                self.assertIn(
                    "aggregate channel alias must use schema_version 1",
                    aggregate_report["errors"],
                )
                self.assertIn(
                    "aggregate channel pointer must not name a core",
                    aggregate_report["errors"],
                )
                primitive_cases = (
                    ("schema-bool", {"schema_version": True}),
                    ("schema-string", {"schema_version": "1"}),
                    ("local-int", {"local_only": 1}),
                    ("local-string", {"local_only": "true"}),
                )
                for label, replacement in primitive_cases:
                    with self.subTest(label=label):
                        malformed = {**valid_pointer, **replacement}
                        report = pipeline.validate_channel_pointer_document(
                            malformed,
                            expected_channel="nightly",
                            expected_core="handy",
                            verify_target=False,
                        )
                        self.assertEqual("invalid", report["status"])
                        pipeline.atomic_write_json(pointer_path, malformed)
                        malformed_bytes = pointer_path.read_bytes()
                        malformed_sha = pipeline.sha256_bytes(malformed_bytes)
                        with self.assertRaisesRegex(
                            pipeline.PipelineError,
                            "current channel pointer is invalid",
                        ):
                            pipeline.update_channel(
                                "nightly",
                                second_target,
                                core_id="handy",
                                expect_current=malformed_sha,
                            )
                        self.assertEqual(malformed_bytes, pointer_path.read_bytes())

                malformed = copy.deepcopy(valid_pointer)
                malformed["unexpected"] = True
                pipeline.atomic_write_json(pointer_path, malformed)
                malformed_bytes = pointer_path.read_bytes()
                malformed_sha = pipeline.sha256_bytes(malformed_bytes)
                with self.assertRaisesRegex(pipeline.PipelineError, "current channel pointer is invalid"):
                    pipeline.update_channel(
                        "nightly",
                        second_target,
                        core_id="handy",
                        expect_current=malformed_sha,
                    )
                self.assertEqual(malformed_bytes, pointer_path.read_bytes())

    def test_channel_enforces_canonical_targets_and_complete_nightly(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            flat_target = nightlies / "golden.json"
            self.make_nightly_target(flat_target)
            canonical_target = (
                nightlies
                / self.nightly_semantic_id("1" * 64)
                / "golden.json"
            )
            self.make_nightly_target(canonical_target)
            validation, store, complete = self.nightly_validation_patches()
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), validation, store, complete:
                with self.assertRaisesRegex(pipeline.PipelineError, "<nightly-id>/golden.json"):
                    pipeline.update_channel(
                        "nightly",
                        flat_target,
                        core_id="handy",
                        expect_absent=True,
                    )
            validation, store, _complete = self.nightly_validation_patches()
            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), validation, store, mock.patch.object(
                pipeline, "complete_core_bundle", return_value=None
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "no complete handy bundle",
                ):
                    pipeline.update_channel(
                        "nightly",
                        canonical_target,
                        core_id="handy",
                        expect_absent=True,
                    )
            self.assertFalse((channels / "nightly.handy.json").exists())

            pins = root / "pins"
            nested_pin = pins / "nested" / "pin-one.json"
            nested_pin.parent.mkdir(parents=True)
            nested_pin.write_text(
                json.dumps({"pin_id": "pin-one", "content_sha256": "a" * 64}),
                encoding="utf-8",
            )
            with mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ):
                with self.assertRaisesRegex(pipeline.PipelineError, "filename must match"):
                    pipeline.derive_channel_target("pinned", nested_pin)

            releases = root / "releases"
            mismatched_release = releases / "wrong-name" / "release-manifest.json"
            mismatched_release.parent.mkdir(parents=True)
            mismatched_release.write_text(
                json.dumps(
                    {
                        "release_id": "release-one",
                        "content_sha256": "b" * 64,
                        "pin": {},
                    }
                ),
                encoding="utf-8",
            )
            pin_path = pins / "pin-one.json"
            pin_path.write_text("{}\n", encoding="utf-8")
            with mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ), mock.patch.object(
                pipeline, "_resolve_release_pin", return_value=({}, pin_path)
            ), mock.patch.object(
                pipeline,
                "_validate_pin_set_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "_validate_local_release",
                return_value={"status": "valid", "errors": []},
            ):
                with self.assertRaisesRegex(pipeline.PipelineError, "directory must match"):
                    pipeline.derive_channel_target("release", mismatched_release)

    def test_channel_pointer_directory_rejects_symlink_traversal(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            actual = root / "actual-channels"
            actual.mkdir()
            linked = root / "channels"
            linked.symlink_to(actual, target_is_directory=True)
            with mock.patch.object(pipeline, "DEFAULT_CHANNELS", linked):
                with self.assertRaisesRegex(pipeline.PipelineError, "must not traverse a symlink"):
                    pipeline.channel_pointer_path("nightly")

    def test_channel_rejects_non_string_target_digest_for_every_kind(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            nightlies = root / "nightlies"
            pins = root / "pins"
            releases = root / "releases"
            targets = {
                "nightly": nightlies / "run-one" / "golden.json",
                "pinned": pins / "pin-one.json",
                "release": releases / "release-one" / "release-manifest.json",
            }
            documents = {
                "nightly": {
                    "pin_id": "nightly-one",
                    "content_sha256": 7,
                    "build_goldens": {"fixture": {}},
                },
                "pinned": {"pin_id": "pin-one", "content_sha256": 7},
                "release": {
                    "release_id": "release-one",
                    "content_sha256": 7,
                    "pin": {},
                },
            }
            for channel, path in targets.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(documents[channel]), encoding="utf-8")
            with mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ):
                for channel, target in targets.items():
                    with self.subTest(channel=channel), self.assertRaisesRegex(
                        pipeline.PipelineError, "content digest is invalid"
                    ):
                        pipeline.derive_channel_target(channel, target)

    def test_channel_aliases_advance_independently(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            channels = root / "channels"
            nightlies = root / "nightlies"
            pins = root / "pins"
            releases = root / "releases"
            targets = {
                "nightly": nightlies / "run-one" / "golden.json",
                "pinned": pins / "pin-one.json",
                "release": releases / "release-one" / "release-manifest.json",
            }
            identities = {
                "nightly": "nightly-one",
                "pinned": "pin-one",
                "release": "release-one",
            }
            for channel, path in targets.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                document = {
                    "id": identities[channel],
                    "content_sha256": "d" * 64,
                }
                if channel == "nightly":
                    document.update(
                        {
                            "schema_version": 2,
                            "core_id": "handy",
                            "cores": {"handy": {}},
                            "build_goldens": {"handy": {}},
                        }
                    )
                path.write_text(
                    json.dumps(document),
                    encoding="utf-8",
                )

            def fake_derive(
                channel: str,
                path: Path,
                _validation_context: object | None = None,
                *,
                core_id: str | None = None,
            ) -> dict:
                self.assertEqual("handy", core_id)
                document = pipeline.load_json(path)
                return {
                    "kind": pipeline.CHANNEL_KINDS[channel],
                    "path": str(path.relative_to(ROOT)),
                    "id": document["id"],
                    "file_sha256": pipeline.sha256_file(path),
                    "content_sha256": document["content_sha256"],
                }

            with mock.patch.object(
                pipeline, "DEFAULT_CHANNELS", channels
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "DEFAULT_PIN_SET_DIR", pins
            ), mock.patch.object(
                pipeline, "DEFAULT_RELEASES", releases
            ), mock.patch.object(
                pipeline, "_derive_channel_target", side_effect=fake_derive
            ), mock.patch.object(
                pipeline, "_require_channel_target_sources_eligible", return_value=None
            ):
                results = {
                    channel: pipeline.update_channel(
                        channel,
                        target,
                        core_id="handy",
                        expect_absent=True,
                    )
                    for channel, target in targets.items()
                }
                pinned_before = (channels / "pinned.handy.json").read_bytes()
                release_before = (channels / "release.handy.json").read_bytes()
                advanced = nightlies / "run-two" / "golden.json"
                advanced.parent.mkdir(parents=True)
                advanced.write_text(
                    json.dumps(
                        {
                            "id": "nightly-two",
                            "content_sha256": "e" * 64,
                            "schema_version": 2,
                            "core_id": "handy",
                            "cores": {"handy": {}},
                            "build_goldens": {"handy": {}},
                        }
                    ),
                    encoding="utf-8",
                )
                pipeline.update_channel(
                    "nightly",
                    advanced,
                    core_id="handy",
                    expect_current=results["nightly"]["pointer_file_sha256"],
                )
                self.assertEqual(
                    pinned_before,
                    (channels / "pinned.handy.json").read_bytes(),
                )
                self.assertEqual(
                    release_before,
                    (channels / "release.handy.json").read_bytes(),
                )


class GoldenPromotionTests(unittest.TestCase):
    def test_failed_build_cannot_be_promoted(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            record = root / "record.json"
            document = {"result": "failed", "build_exit_code": 1}
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_build_record_identity(
                    document,
                    record,
                    ROOT / "manifests" / "core-builds.json",
                    pipeline.load_catalog(ROOT / "manifests" / "core-builds.json"),
                )

    def test_stale_recipe_cannot_be_promoted(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            record = root / "build-record.json"
            artifact = root / "fixture_libretro.so"
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            log.write_text("build\n", encoding="utf-8")
            document = {
                        "schema_version": 2,
                        "result": "passed",
                        "build_exit_code": 0,
                        "local_only": True,
                        "publication": "disabled",
                        "core_id": "mgba",
                        "architecture": "arm64",
                        "artifact": {
                            "status": "valid",
                            "path": artifact.name,
                            "sha256": pipeline.sha256_file(artifact),
                        },
                        "build": {
                            "log": log.name,
                            "log_sha256": pipeline.sha256_file(log),
                        },
                        "recipe": {
                            "catalog_path": "manifests/core-builds.json",
                            "catalog_sha256": "0" * 64,
                            "pipeline_sha256": pipeline.sha256_file(MODULE_PATH),
                            "workflow": ".github/workflows/build-mgba.yml",
                            "workflow_sha256": pipeline.sha256_file(
                                ROOT / ".github" / "workflows" / "build-mgba.yml"
                            ),
                        },
                    }
            record.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(pipeline.PipelineError, "catalog_sha256"):
                pipeline.validate_build_record_identity(
                    document,
                    record,
                    ROOT / "manifests" / "core-builds.json",
                    pipeline.load_catalog(ROOT / "manifests" / "core-builds.json"),
                )

    def test_new_build_record_requires_the_exact_archive_provenance(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "ecwolf"
        spec = catalog["cores"][core_id]
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes(b"metadata")
            log.write_bytes(b"build log")
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
            }
            document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": "arm64",
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "source": {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "tree": spec["source"]["tree"],
                    "submodules": [
                        {"state": " ", **entry}
                        for entry in spec["source"].get("submodules", [])
                    ],
                },
                "toolchain": {
                    **catalog["toolchains"]["arm64"],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, "arm64"
                    ),
                    "resolved_image_id": catalog["toolchains"]["arm64"]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
                "build": {
                    "driver": spec["build"]["driver"],
                    "environment": "sanitized-v1",
                    "compile_definitions": [],
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
            }
            record = root / "build-record.json"
            record.write_text(json.dumps(document), encoding="utf-8")
            # This test isolates archive-provenance identity; the synthetic log
            # is not a real build, so bypass the (now registered) ecwolf log
            # contract, which fires only after the provenance gate below.
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ), mock.patch.object(
                pipeline, "_registered_core_log_contract_proves", return_value=True
            ):
                paths = pipeline.validate_build_record_identity(
                    document, record, catalog_path, catalog
                )
            self.assertEqual((artifact, metadata, log), paths)
            mutations = (
                (("lock", "path"), "pins/toolchains/other.json"),
                (("lock", "schema_version"), 2),
                (("lock", "lock_id"), "other"),
                (("lock", "file_sha256"), "0" * 64),
                (("lock", "content_sha256"), "0" * 64),
                (("validator", "path"), "scripts/other.py"),
                (("validator", "sha256"), "0" * 64),
                (("archive", "filename"), "other.tar.gz"),
                (("archive", "sha256"), "0" * 64),
                (("archive", "size"), 1),
            )
            for path, value in mutations:
                changed = copy.deepcopy(document)
                changed["toolchain"]["archive_provenance"][path[0]][path[1]] = value
                with self.subTest(path=path), self.assertRaisesRegex(
                    pipeline.PipelineError, "archive provenance"
                ):
                    pipeline.validate_build_record_identity(
                        changed, record, catalog_path, catalog
                    )

    def test_direct_cmake_build_record_and_log_proof_fail_closed(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "swanstation"
        spec = catalog["cores"][core_id]
        arch = "arm64"
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes(b"metadata")
            tool_paths = {
                role: f"/fixture/bin/{name}"
                for role, name in pipeline.TARGET_CMAKE_TOOL_NAMES[arch].items()
            }
            markers = pipeline.direct_cmake_log_markers(spec, arch, tool_paths)
            log.write_text("\n".join(markers) + "\n", encoding="utf-8")
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
                "needed": [
                    "libc.so.6",
                    "libdl.so.2",
                    "libgcc_s.so.1",
                    "libm.so.6",
                    "libpthread.so.0",
                    "librt.so.1",
                    "libstdc++.so.6",
                ],
            }
            document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": arch,
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "source": {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "submodules": [],
                },
                "toolchain": {
                    **catalog["toolchains"][arch],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, arch
                    ),
                    "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
                "build": {
                    **pipeline.normalized_build_contract(spec, arch),
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
            }
            record = root / "build-record.json"
            record.write_text(json.dumps(document), encoding="utf-8")
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ):
                self.assertEqual(
                    (artifact, metadata, log),
                    pipeline.validate_build_record_identity(
                        document, record, catalog_path, catalog
                    ),
                )

                for label, mutate in (
                    (
                        "system",
                        lambda changed: changed["build"]["cmake"]["system"].update(
                            {"processor": "arm"}
                        ),
                    ),
                    (
                        "overlay",
                        lambda changed: changed["build"]["overlays"][0].update(
                            {"patch_sha256": "0" * 64}
                        ),
                    ),
                    (
                        "epoch",
                        lambda changed: changed["build"].update(
                            {"source_date_epoch": spec["build"]["source_date_epoch"] + 1}
                        ),
                    ),
                    (
                        "extra",
                        lambda changed: changed["build"].update({"ignored": True}),
                    ),
                ):
                    changed = copy.deepcopy(document)
                    mutate(changed)
                    with self.subTest(label=label), self.assertRaisesRegex(
                        pipeline.PipelineError, "compile environment"
                    ):
                        pipeline.validate_build_record_identity(
                            changed, record, catalog_path, catalog
                        )

                log.write_text(
                    "\n".join(reversed(markers)) + "\n", encoding="utf-8"
                )
                changed = copy.deepcopy(document)
                changed["build"]["log_sha256"] = pipeline.sha256_file(log)
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "does not prove the exact direct-CMake"
                ):
                    pipeline.validate_build_record_identity(
                        changed, record, catalog_path, catalog
                    )


    def test_ffmpeg_make_variable_record_and_log_proof_fail_closed(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "ffmpeg"
        spec = catalog["cores"][core_id]
        arch = "arm64"
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes(b"metadata")
            markers = pipeline.make_variable_log_markers(spec)
            definitions = [
                f"-D{definition}"
                for definition in pipeline.PORTABLE_FFMPEG_COMPILE_DEFINITIONS
            ]

            def valid_log() -> str:
                return (
                    "\n".join(markers)
                    + "\naarch64-linux-gnu-gcc -c source.c -o source.o "
                    + " ".join(definitions)
                    + "\n"
                )

            log.write_text(valid_log(), encoding="utf-8")
            accepted_needed = [
                "ld-linux-aarch64.so.1",
                "libc.so.6",
                "libm.so.6",
                "libpthread.so.0",
            ]
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
                "needed": accepted_needed,
            }
            document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": arch,
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "source": {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "submodules": [],
                },
                "toolchain": {
                    **catalog["toolchains"][arch],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, arch
                    ),
                    "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
                "build": {
                    **pipeline.normalized_build_contract(spec, arch),
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
            }
            record = root / "build-record.json"
            record.write_text(json.dumps(document), encoding="utf-8")
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ):
                self.assertEqual(
                    (artifact, metadata, log),
                    pipeline.validate_build_record_identity(
                        document, record, catalog_path, catalog
                    ),
                )
                for label, mutate in (
                    (
                        "missing",
                        lambda changed: changed["build"]["make_variables"].pop(
                            "OPENGL"
                        ),
                    ),
                    (
                        "extra",
                        lambda changed: changed["build"]["make_variables"].update(
                            {"EXTRA": 0}
                        ),
                    ),
                    (
                        "bool",
                        lambda changed: changed["build"]["make_variables"].update(
                            {"OPENGL": False}
                        ),
                    ),
                    (
                        "raw-MAKEFLAGS",
                        lambda changed: changed["build"].update(
                            {"MAKEFLAGS": "OPENGL=0"}
                        ),
                    ),
                ):
                    changed = copy.deepcopy(document)
                    mutate(changed)
                    with self.subTest(label=label), self.assertRaisesRegex(
                        pipeline.PipelineError, "compile environment"
                    ):
                        pipeline.validate_build_record_identity(
                            changed, record, catalog_path, catalog
                        )

                log_mutations = (
                    valid_log().replace("|command line", "|environment", 1),
                    markers[0] + "\n" + valid_log(),
                    valid_log().replace(" -DARCH_ARM=0", "", 1),
                    valid_log().rstrip() + " -DARCH_ARM=1\n",
                    valid_log().rstrip() + " -DHAVE_OPENGL=0\n",
                )
                for changed_log in log_mutations:
                    log.write_text(changed_log, encoding="utf-8")
                    changed = copy.deepcopy(document)
                    changed["build"]["log_sha256"] = pipeline.sha256_file(log)
                    with self.subTest(log=changed_log[:80]), self.assertRaisesRegex(
                        pipeline.PipelineError, "portable FFmpeg"
                    ):
                        pipeline.validate_build_record_identity(
                            changed, record, catalog_path, catalog
                        )

            log.write_text(valid_log(), encoding="utf-8")
            forbidden_artifact = copy.deepcopy(expected_artifact)
            forbidden_artifact["needed"].append("libavcodec.so.56")
            forbidden_document = copy.deepcopy(document)
            forbidden_document["artifact"] = forbidden_artifact
            forbidden_document["build"]["log_sha256"] = pipeline.sha256_file(log)
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=forbidden_artifact
            ), self.assertRaisesRegex(pipeline.PipelineError, "artifact"):
                pipeline.validate_build_record_identity(
                    forbidden_document, record, catalog_path, catalog
                )

    def test_compile_definition_record_and_log_proof_fail_closed(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "pcsx_rearmed"
        spec = catalog["cores"][core_id]
        arch = "armhf"
        definitions = pipeline.compile_definitions_for_target(spec, arch)
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes(b"metadata")
            log.write_text(
                "arm-a30-linux-gnueabihf-gcc -c source.c "
                + " ".join(f"-D{item}" for item in definitions)
                + "\n",
                encoding="utf-8",
            )
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
            }
            document = {
                "schema_version": 2,
                "result": "passed",
                "build_exit_code": 0,
                "local_only": True,
                "publication": "disabled",
                "core_id": core_id,
                "architecture": arch,
                "recipe": pipeline.recipe_record(catalog_path, core_id, spec),
                "source": {
                    **spec["source"],
                    "resolved_commit": spec["source"]["commit"],
                    "resolved_url": spec["source"]["url"],
                    "submodules": [
                        {"state": " ", **entry}
                        for entry in spec["source"].get("submodules", [])
                    ],
                },
                "toolchain": {
                    **catalog["toolchains"][arch],
                    "archive_provenance": pipeline.expected_archive_provenance(
                        catalog, arch
                    ),
                    "resolved_image_id": catalog["toolchains"][arch]["image_id"],
                    "libretro_super_commit": catalog["resolver"][
                        "libretro_super_commit"
                    ],
                    "resolver_digests": catalog["resolver"],
                    "compiler": "fixture compiler",
                    "sysroot": "/fixture",
                },
                "artifact": expected_artifact,
                "metadata": {
                    "status": "valid",
                    "path": metadata.name,
                    "sha256": pipeline.sha256_file(metadata),
                    "size": metadata.stat().st_size,
                },
                "build": {
                    "driver": spec["build"]["driver"],
                    "environment": "sanitized-v1",
                    "compile_definitions": definitions,
                    "source_date_epoch": spec["build"]["source_date_epoch"],
                    "log": log.name,
                    "log_sha256": pipeline.sha256_file(log),
                },
            }
            record = root / "build-record.json"
            record.write_text(json.dumps(document), encoding="utf-8")
            recipe_snapshot = root / "recipe.json"
            recipe_snapshot.write_bytes(pipeline.recipe_snapshot(document))
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    recipe_snapshot, document, "pcsx_rearmed/armhf"
                ),
            )
            snapshot_tamper = copy.deepcopy(document)
            snapshot_tamper["build"]["compile_definitions"] = []
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    recipe_snapshot,
                    snapshot_tamper,
                    "pcsx_rearmed/armhf-tampered",
                )
            )
            # Isolate the compile-definition / epoch / source identity checks
            # from the now-registered pcsx_rearmed c_asm log contract; the
            # synthetic one-line log is not a full build. The decoy-log cases
            # below still fail at compile_log_proves_definitions, which is not
            # the registered contract and so is unaffected by this mock.
            with mock.patch.object(
                pipeline, "validate_artifact", return_value=expected_artifact
            ), mock.patch.object(
                pipeline, "_registered_core_log_contract_proves", return_value=True
            ):
                pipeline.validate_build_record_identity(
                    document, record, catalog_path, catalog
                )

                with mock.patch.object(
                    pipeline,
                    "load_json_with_sha256",
                    return_value=({}, document["recipe"]["catalog_sha256"]),
                ), self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "catalog differs from canonical disk bytes",
                ):
                    pipeline.validate_build_record_identity(
                        document, record, catalog_path, catalog
                    )

                changed = copy.deepcopy(document)
                changed["build"]["compile_definitions"] = []
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "compile environment"
                ):
                    pipeline.validate_build_record_identity(
                        changed, record, catalog_path, catalog
                    )

                for epoch in (
                    None,
                    True,
                    spec["build"]["source_date_epoch"] + 1,
                ):
                    changed = copy.deepcopy(document)
                    if epoch is None:
                        changed["build"].pop("source_date_epoch")
                    else:
                        changed["build"]["source_date_epoch"] = epoch
                    with self.subTest(epoch=epoch), self.assertRaisesRegex(
                        pipeline.PipelineError, "compile environment"
                    ):
                        pipeline.validate_build_record_identity(
                            changed, record, catalog_path, catalog
                        )

                changed = copy.deepcopy(document)
                changed["source"]["tree"] = "a" * 40
                with self.assertRaisesRegex(pipeline.PipelineError, "source identity"):
                    pipeline.validate_build_record_identity(
                        changed, record, catalog_path, catalog
                    )

                decoy_logs = (
                    "export CFLAGS='"
                    + " ".join(f"-D{item}" for item in definitions)
                    + "'\n",
                    "\n".join(
                        "arm-a30-linux-gnueabihf-gcc -c source.c -D" + item
                        for item in definitions
                    )
                    + "\n",
                    "printf 'arm-a30-linux-gnueabihf-gcc -c source.c "
                    + " ".join(f"-D{item}" for item in definitions)
                    + "'\n",
                )
                for decoy_log in decoy_logs:
                    log.write_text(decoy_log, encoding="utf-8")
                    changed = copy.deepcopy(document)
                    changed["build"]["log_sha256"] = pipeline.sha256_file(log)
                    with self.subTest(log=decoy_log), self.assertRaisesRegex(
                        pipeline.PipelineError, "does not prove"
                    ):
                        pipeline.validate_build_record_identity(
                            changed, record, catalog_path, catalog
                        )

                log.write_bytes(b"\xff\xfe\x00not-utf8")
                changed = copy.deepcopy(document)
                changed["build"]["log_sha256"] = pipeline.sha256_file(log)
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "readable UTF-8"
                ):
                    pipeline.validate_build_record_identity(
                        changed, record, catalog_path, catalog
                    )

    def test_existing_build_golden_is_immutable(self) -> None:
        golden = {"build_goldens": {"mgba": {"arm64": {"promotion_state": "build_golden"}}}}
        with self.assertRaisesRegex(pipeline.PipelineError, "immutable build golden"):
            pipeline.require_empty_golden_slot(golden, "mgba", "arm64")

    def test_promotion_policy_uses_the_exact_e2e_bound_record_snapshot(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            runs = root / "runs"
            nightlies = root / "nightlies"
            store = root / "store"
            runs.mkdir()
            nightlies.mkdir()
            record_path = runs / "build-record.json"
            e2e_path = runs / "e2e-record.json"
            golden_path = nightlies / "bound-candidate-fixture" / "golden.json"
            golden_path.parent.mkdir()
            for path in (record_path, e2e_path, golden_path):
                path.write_text("{}\n", encoding="utf-8")

            catalog = {"cores": {"bound-core": {}}}
            golden = {"core_id": "bound-core", "build_goldens": {}}
            bound_source = {
                "url": "https://example.invalid/bound.git",
                "resolved_commit": "b" * 40,
            }
            bound_record = {
                "core_id": "bound-core",
                "architecture": "arm64",
                "source": bound_source,
            }
            bound_records = {
                "arm64": (bound_record, record_path, "a" * 64),
            }

            def load_only_golden(path: Path) -> dict:
                self.assertEqual(golden_path, path)
                return golden

            with mock.patch.object(
                pipeline, "DEFAULT_RUNS", runs
            ), mock.patch.object(
                pipeline, "DEFAULT_NIGHTLIES", nightlies
            ), mock.patch.object(
                pipeline, "load_catalog", return_value=catalog
            ), mock.patch.object(
                pipeline, "load_json", side_effect=load_only_golden
            ), mock.patch.object(
                pipeline,
                "validate_golden_document",
                return_value={"status": "valid", "errors": []},
            ), mock.patch.object(
                pipeline,
                "validate_e2e_evidence",
                return_value=(
                    {"run_id": "bound"},
                    "c" * 64,
                    bound_records,
                    runs / "package.zip",
                    {"sha256": "d" * 64},
                ),
            ), mock.patch.object(
                pipeline,
                "require_source_commits_eligible",
            ) as source_policy, mock.patch.object(
                pipeline,
                "require_active_core_golden",
                side_effect=pipeline.PipelineError("bound active policy"),
            ) as active_policy:
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "bound active policy"
                ):
                    pipeline._promote_build_record_locked(
                        golden_path,
                        record_path,
                        e2e_path,
                        store_root=store,
                    )

            source_policy.assert_called_once_with(
                catalog, [("bound-core", bound_source)]
            )
            active_policy.assert_called_once_with(golden, "bound-core")

    def test_failed_e2e_record_cannot_bind_a_promotion(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            record_path = root / "build-record.json"
            e2e_path = root / "e2e-record.json"
            record_path.write_text(
                json.dumps(
                    {"core_id": "quicknes", "architecture": "arm64"}
                ),
                encoding="utf-8",
            )
            evidence = {
                "schema_version": 2,
                "run_id": "failed-fixture",
                "local_only": True,
                "publication": "disabled",
                "runner": {
                    "profile": "local",
                    "mode": "native",
                    "backend": "local-docker",
                    "local_only": True,
                    "publication": "disabled",
                },
                "result": "failed",
                "workflow_audit": {},
                "builds": [{"core_id": "quicknes"}],
                "packages": [{"core_id": "quicknes"}],
            }
            evidence["content_sha256"] = pipeline.e2e_content_sha256(evidence)
            e2e_path.write_text(json.dumps(evidence), encoding="utf-8")
            with self.assertRaisesRegex(pipeline.PipelineError, "not a passed"):
                pipeline.validate_e2e_evidence(
                    e2e_path,
                    record_path,
                    ROOT / "manifests" / "core-builds.json",
                    pipeline.load_catalog(ROOT / "manifests" / "core-builds.json"),
                )


if __name__ == "__main__":
    unittest.main()
