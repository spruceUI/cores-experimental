"""VecX individual catalog and build-contract tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from .support import pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import vecx
from tests.test_contract_vecx import build_vecx_log_fixture

from .support import (
    ROOT,
    file_sha256,
    load_core_documents,
    load_document,
)
from .support import evidence_handles


CORE_ID = "vecx"
OTHER_CORE_ID = "prosystem"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SOURCE_URL = _H["SOURCE_URL"]
SOURCE_LOCK_ID = _H["SOURCE_LOCK_ID"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
PACKAGE_SHA256 = _H["PACKAGE_SHA256"]
TARGETS = _H["TARGETS"]

SOURCE_LOCK_IDENTITY = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "submodules": [],
}

SOURCE_RECORD_IDENTITY = {
    "commit": SOURCE_COMMIT,
    "requested_ref": "refs/heads/master",
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
    "tree": SOURCE_TREE,
    "url": SOURCE_URL,
}

CAVEAT_TOKENS = (
    "all four C compile commands",
    "complete ordered link invocation",
    "1.2 8f671cc",
    "GPLv3",
    "No external firmware",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)

class VecxCoreTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)

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


    def test_vecx_source_set_release_and_channels_are_core_owned(self) -> None:
        source_set = registry.composed_source_set(SEMANTIC_ID)
        catalog_core_count = len(
            load_document(ROOT / "manifests" / "core-builds.json")["cores"]
        )
        registry.validate_source_set(source_set)
        profile_report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SEMANTIC_ID, profile_report["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))
        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        source_lock = registry.composed_source_lock(CORE_ID)
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(SOURCE_LOCK_IDENTITY, source_lock["source"])
        self.assertEqual(1, profile_report["counts"]["source_locks"])
        self.assertEqual(2, profile_report["counts"]["build_evidence_cells"])
        self.assertEqual(
            {
                "catalog_cores": catalog_core_count,
                "catalog_unlocked_cores": catalog_core_count - 1,
                "evidence_cells": 2,
                "locked_cores": 1,
            },
            profile_report["mirror"],
        )
        cells = {
            cell["architecture"]: cell
            for cell in profile_report["build_evidence_cells"]
        }
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            with self.subTest(profile=architecture):
                self.assertEqual(CORE_ID, cells[architecture]["core_id"])
                self.assertEqual(
                    SOURCE_LOCK_ID, cells[architecture]["source_lock_id"]
                )
                self.assertEqual(
                    expected["artifact_sha256"],
                    cells[architecture]["artifact_sha256"],
                )
                self.assertEqual(
                    expected["execution_profile_id"],
                    cells[architecture]["execution_profile_id"],
                )
        self.assertTrue(profile_report["device_views"])
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in profile_report["device_views"]
            )
        )

        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": (
                f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json"
            ),
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
                )
                report = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=CORE_ID,
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(channel, pointer["channel"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertNotIn("tranche", pointer["target"]["path"].casefold())

                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])
                self.assertIn(
                    "channel pointer document does not match its core alias filename",
                    wrong_core["errors"],
                )

        pin_path = ROOT / PIN_PATH
        pin = load_document(pin_path)
        release_root = ROOT / ".local-e2e" / "releases" / SEMANTIC_ID
        release_report = pipeline.validate_local_release(
            release_root,
            pin,
            file_sha256(pin_path),
            expected_release_id=SEMANTIC_ID,
        )
        self.assertEqual(
            "valid", release_report["status"], release_report["errors"]
        )
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])


    def test_vecx_compatibility_and_registered_proof_fail_closed(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        wrong_digest = copy.deepcopy(compatibility)
        wrong_digest["content_sha256"] = "0" * 64
        digest_report = pipeline.validate_core_compatibility_document(
            wrong_digest,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=False,
        )
        self.assertEqual("invalid", digest_report["status"])
        self.assertIn(
            "core compatibility content digest is invalid", digest_report["errors"]
        )

        same_run = copy.deepcopy(compatibility)
        same_run["reproduction_run"] = same_run["e2e_run"]
        same_run["reproduction_e2e_content_sha256"] = same_run[
            "selected_e2e_content_sha256"
        ]
        same_run["content_sha256"] = pipeline.core_compatibility_content_sha256(
            same_run
        )
        same_run_report = pipeline.validate_core_compatibility_document(
            same_run,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        log_path = (
            ROOT
            / ".local-e2e"
            / "runs"
            / REPRODUCTION_RUN
            / CORE_ID
            / "arm64"
            / "build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        link_line = next(
            line
            for line in log_text.splitlines()
            if " -ovecx_libretro.so " in line and " -c " not in line
        )
        reordered_link = link_line.replace(
            "./e6809.o ./vecx_psg.o", "./vecx_psg.o ./e6809.o"
        )
        self.assertNotEqual(link_line, reordered_link)
        self.assertFalse(
            pipeline.registered_core_log_contract_proves(
                log_text.replace(link_line, reordered_link, 1),
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )

    def test_vecx_software_recipe_is_exact_typed_and_sanitized(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["vecx"]
        expected_git_version = {
            "derivation": "native-space-short7-v1",
            "value": " 8f671cc",
        }
        expected_replacement = {
            "kind": "whole-file-v1",
            "path": "metadata/vecx/software-v1.info",
            "preimage_sha256": (
                "9eec259b2b84256aca32cdcd37b084732"
                "b17d2fce829dac01bab9a84ea01b4e3"
            ),
            "replacement_sha256": (
                "2f22e8069a304878b52aeb5d7f789812"
                "bf271c61e5c41e0cb0fbd6acb5d28c1a"
            ),
        }
        self.assertEqual(
            {
                "url": "https://github.com/libretro/libretro-vecx.git",
                "requested_ref": "refs/heads/master",
                "commit": "8f671cc9d737f2890c3ce19e177e2984dcae121f",
                "tree": "49ae584713edede2a70792ecf6cb744b11fff2e6",
            },
            spec["source"],
        )
        self.assertEqual({"HAS_GPU": 0}, pipeline.validated_make_variables(spec))
        self.assertEqual(expected_git_version, pipeline.validated_git_version(spec))
        self.assertEqual(expected_replacement, spec["metadata"]["replacement"])
        self.assertEqual(
            expected_replacement,
            pipeline.validated_metadata_replacement(spec),
        )
        self.assertTrue(
            pipeline.metadata_replacement_contract_is_well_formed(
                expected_replacement
            )
        )
        self.assertFalse(
            pipeline.metadata_replacement_contract_is_well_formed(
                {**expected_replacement, "replacement_sha256": "b" * 64}
            )
        )
        self.assertEqual(
            expected_replacement["replacement_sha256"],
            pipeline.sha256_file(ROOT / expected_replacement["path"]),
        )
        self.assertEqual(
            ["libEGL", "libGL", "libGLES", "libOpenGL"],
            pipeline.validated_forbidden_needed_prefixes(spec),
        )
        self.assertNotIn("source_date_epoch", spec["build"])
        self.assertNotIn("compile_definitions", spec["build"])
        schema = json.loads(
            (ROOT / "manifests" / "core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for arch in ("arm64", "armhf"):
            contract = pipeline.normalized_build_contract(spec, arch)
            self.assertEqual({"HAS_GPU": 0}, contract["make_variables"])
            self.assertEqual(expected_git_version, contract["git_version"])
            self.assertEqual(
                expected_replacement, contract["metadata_replacement"]
            )
        script = pipeline.container_build_script(
            "vecx", "arm64", spec, catalog["resolver"]
        )
        unset_variables = set(
            next(
                line for line in script.splitlines() if line.startswith("unset ")
            ).split()[1:]
        )
        self.assertTrue({"GIT_VERSION", "HAS_GPU"}.issubset(unset_variables))
        self.assertIn("HAS_GPU=0", script)
        self.assertIn(" 8f671cc", script)
        self.assertIn(expected_replacement["preimage_sha256"], script)
        self.assertIn(expected_replacement["replacement_sha256"], script)
        self.assertIn("/metadata-replacements/vecx.info", script)
        self.assertGreater(
            script.index(expected_replacement["preimage_sha256"]),
            script.index("./libretro-build.sh vecx"),
        )
        self.assertLess(
            script.index(expected_replacement["preimage_sha256"]),
            script.rindex(expected_replacement["replacement_sha256"]),
        )

    def test_vecx_catalog_contract_mutations_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")

        def mutation(label: str, mutate, message: str) -> tuple[str, dict, str]:
            changed = copy.deepcopy(catalog)
            mutate(changed["cores"]["vecx"])
            return label, changed, message

        def remove_software_contract(
            spec: dict, *, single_target: bool = False
        ) -> None:
            spec["build"].pop("make_variables")
            spec["build"].pop("git_version")
            spec["metadata"].pop("replacement")
            spec.pop("validation")
            if single_target:
                spec["targets"] = ["arm64"]

        mutations = (
            mutation(
                "missing-make-variable",
                lambda spec: spec["build"]["make_variables"].pop("HAS_GPU"),
                "make_variables",
            ),
            mutation(
                "extra-make-variable",
                lambda spec: spec["build"]["make_variables"].update(
                    {"OPENGL": 0}
                ),
                "make_variables",
            ),
            mutation(
                "gpu-enabled",
                lambda spec: spec["build"]["make_variables"].update(
                    {"HAS_GPU": 1}
                ),
                "VecX software",
            ),
            mutation(
                "boolean-gpu",
                lambda spec: spec["build"]["make_variables"].update(
                    {"HAS_GPU": False}
                ),
                "exact integer",
            ),
            mutation(
                "missing-native-version",
                lambda spec: spec["build"].pop("git_version"),
                "VecX software build keys",
            ),
            mutation(
                "hyphen-version",
                lambda spec: spec["build"]["git_version"].update(
                    {
                        "derivation": "hyphen-short7-v1",
                        "value": "-8f671cc",
                    }
                ),
                "native-space-short7-v1",
            ),
            mutation(
                "wrong-native-version",
                lambda spec: spec["build"]["git_version"].update(
                    {"value": " 0000000"}
                ),
                "first seven source commit",
            ),
            mutation(
                "replacement-kind",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"kind": "line-edit-v1"}
                ),
                "whole-file-v1",
            ),
            mutation(
                "replacement-path",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"path": "metadata/vecx/../software-v1.info"}
                ),
                "path",
            ),
            mutation(
                "preimage",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"preimage_sha256": "a" * 64}
                ),
                "preimage_sha256",
            ),
            mutation(
                "replacement-digest",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"replacement_sha256": "b" * 64}
                ),
                "replacement_sha256",
            ),
            mutation(
                "replacement-extra",
                lambda spec: spec["metadata"]["replacement"].update(
                    {"extra": True}
                ),
                "exact metadata replacement fields",
            ),
            mutation(
                "dependency-policy",
                lambda spec: spec["validation"][
                    "forbidden_needed_prefixes"
                ].remove("libGL"),
                "VecX software dependency policy",
            ),
            mutation(
                "source-identity",
                lambda spec: spec["source"].update({"tree": "a" * 40}),
                "VecX software source",
            ),
            mutation(
                "all-software-controls-removed",
                remove_software_contract,
                "exact VecX software",
            ),
            mutation(
                "all-software-controls-removed-single-target",
                lambda spec: remove_software_contract(
                    spec, single_target=True
                ),
                "exact VecX software",
            ),
        )
        for label, changed, message in mutations:
            with self.subTest(label=label), self.assertRaisesRegex(
                pipeline.PipelineError, message
            ):
                pipeline.validate_catalog(changed)

    def test_vecx_make_and_native_version_log_proofs_fail_closed(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"]["vecx"]
        variables = spec["build"]["make_variables"]
        git_version = spec["build"]["git_version"]
        metadata_replacement = spec["metadata"]["replacement"]
        make_markers = pipeline.make_variable_log_markers(spec)
        version_markers = pipeline.git_version_log_markers(spec)
        metadata_markers = pipeline.metadata_replacement_markers(
            metadata_replacement
        )
        compilers = {
            "arm64": "aarch64-linux-gnu-gcc",
            "armhf": "arm-a30-linux-gnueabihf-gcc",
        }
        version_token = r'-DGIT_VERSION=\"" 8f671cc"\"'

        def valid_log(arch: str) -> str:
            compiler = compilers[arch]
            return (
                "\n".join([*make_markers, *version_markers])
                + f"\n{compiler} {version_token} -c source.c -o source.o\n"
                + f"{compiler} -shared source.o -lm -o vecx_libretro.so\n"
                + "\n".join(metadata_markers)
                + "\n"
            )

        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                log = valid_log(arch)
                self.assertTrue(
                    pipeline.make_variable_log_proves_contract(
                        log, variables, arch
                    )
                )
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log,
                        git_version,
                        spec["source"]["commit"],
                        arch,
                    )
                )
                self.assertTrue(
                    pipeline.metadata_replacement_log_proves_contract(
                        log, metadata_replacement
                    )
                )

        baseline = valid_log("arm64")
        compile_line = next(
            line for line in baseline.splitlines() if " -c " in line
        )
        make_mutations = {
            "missing-marker": baseline.replace(make_markers[0] + "\n", "", 1),
            "environment-origin": baseline.replace(
                "|command line", "|environment", 1
            ),
            "duplicate-marker": make_markers[0] + "\n" + baseline,
            "markers-after-compile": compile_line
            + "\n"
            + "\n".join([*make_markers, *version_markers])
            + "\naarch64-linux-gnu-gcc -shared source.o -lm "
            + "-o vecx_libretro.so\n",
            "has-gpu-define": baseline.replace(
                " -c source.c", " -DHAS_GPU -c source.c", 1
            ),
            "has-gpu-undef": baseline.replace(
                " -c source.c", " -UHAS_GPU -c source.c", 1
            ),
            "has-gpu-wp": baseline.replace(
                " -c source.c", " -Wp,-DHAS_GPU=0 -c source.c", 1
            ),
            "gl-link": baseline.replace(" -lm ", " -lm -lGL ", 1),
            "obfuscated-compiler-gl-link": baseline.replace(
                "aarch64-linux-gnu-gcc -shared",
                'aarch64-linux-gnu-g""cc -shared',
            ).replace(" -lm ", " -lm -lGL ", 1),
            "opengl-link": baseline.replace(" -lm ", " -lm -lOpenGL ", 1),
            "gles-link": baseline.replace(" -lm ", " -lm -lGLESv2 ", 1),
            "egl-link": baseline.replace(" -lm ", " -lm -lEGL ", 1),
            "gpu-source": baseline.replace(
                "source.c", "libretro-common/glsym/glsym_gl.c", 1
            ),
            "gpu-object": baseline.replace(
                "source.o -lm", "libretro-common/glsym/rglgen.o -lm", 1
            ),
            "response-file": baseline.replace(
                " -c source.c", " @compiler-options.rsp -c source.c", 1
            ),
        }
        for label, changed_log in make_mutations.items():
            with self.subTest(make_log=label):
                self.assertFalse(
                    pipeline.make_variable_log_proves_contract(
                        changed_log, variables, "arm64"
                    )
                )

        version_mutations = {
            "missing-marker": baseline.replace(version_markers[0] + "\n", "", 1),
            "environment-origin": baseline.replace(
                version_markers[-1],
                version_markers[-1].replace("|file", "|environment"),
            ),
            "duplicate-marker": version_markers[0] + "\n" + baseline,
            "markers-after-compile": compile_line
            + "\n"
            + "\n".join([*make_markers, *version_markers])
            + "\naarch64-linux-gnu-gcc -shared source.o -lm "
            + "-o vecx_libretro.so\n",
            "hyphen-version": baseline.replace(" 8f671cc", "-8f671cc"),
            "wrong-native-version": baseline.replace(" 8f671cc", " 0000000"),
            "missing-compile-token": baseline.replace(" " + version_token, "", 1),
            "unquoted-version": baseline.replace(
                version_token, "-DGIT_VERSION=8f671cc"
            ),
            "obfuscated-unbound-compile": baseline
            + 'aarch64-linux-gnu-g""cc -""c other.c -o other.o\n',
        }
        for label, changed_log in version_mutations.items():
            with self.subTest(version_log=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        changed_log,
                        git_version,
                        spec["source"]["commit"],
                        "arm64",
                    )
                )

        for label, changed_log in {
            "missing-marker": baseline.replace(
                metadata_markers[0] + "\n", "", 1
            ),
            "duplicate-marker": metadata_markers[0] + "\n" + baseline,
            "wrong-preimage": baseline.replace(
                metadata_replacement["preimage_sha256"], "a" * 64
            ),
            "wrong-replacement": baseline.replace(
                metadata_replacement["replacement_sha256"], "b" * 64
            ),
        }.items():
            with self.subTest(metadata_log=label):
                self.assertFalse(
                    pipeline.metadata_replacement_log_proves_contract(
                        changed_log, metadata_replacement
                    )
                )

    def test_vecx_recipe_snapshot_v8_binds_combined_software_contract(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "vecx"
        arch = "arm64"
        spec = catalog["cores"][core_id]
        replacement_path = spec["metadata"]["replacement"]["path"]
        record = {
            "core_id": core_id,
            "architecture": arch,
            "source": {
                **spec["source"],
                "resolved_commit": spec["source"]["commit"],
                "resolved_url": spec["source"]["url"],
                "submodules": [],
            },
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
            "artifact": {
                "needed": [
                    "ld-linux-aarch64.so.1",
                    "libc.so.6",
                    "libm.so.6",
                ]
            },
            "metadata": {
                "status": "valid",
                "sha256": spec["metadata"]["replacement"]["replacement_sha256"],
            },
            "build": {
                **pipeline.normalized_build_contract(spec, arch),
                "log": "build.log",
                "log_sha256": "a" * 64,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "vecx-v8.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(8, snapshot["schema_version"])
            self.assertEqual(
                pipeline.recorded_build_contract(record["build"]),
                snapshot["build"],
            )
            self.assertIn(replacement_path, snapshot["files"])
            self.assertEqual(
                spec["metadata"]["replacement"]["replacement_sha256"],
                snapshot["files"][replacement_path]["sha256"],
            )
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "vecx/v8"
                ),
            )

            original_identity = pipeline.provenance_identity_sha256(record)
            for label, mutate in (
                (
                    "make-variable",
                    lambda changed: changed["build"]["make_variables"].update(
                        {"HAS_GPU": 1}
                    ),
                ),
                (
                    "native-version",
                    lambda changed: changed["build"]["git_version"].update(
                        {"value": " 0000000"}
                    ),
                ),
                (
                    "metadata-replacement",
                    lambda changed: changed["build"][
                        "metadata_replacement"
                    ].update({"replacement_sha256": "b" * 64}),
                ),
            ):
                changed = copy.deepcopy(record)
                mutate(changed)
                with self.subTest(build=label):
                    self.assertNotEqual(
                        original_identity,
                        pipeline.provenance_identity_sha256(changed),
                    )
                    self.assertTrue(
                        pipeline.verify_recipe_snapshot(
                            snapshot_path, changed, f"vecx/v8-{label}"
                        )
                    )

            tampered_snapshot = copy.deepcopy(snapshot)
            tampered_snapshot["schema_version"] = 7
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertIn(
                "vecx/v8-version: recipe snapshot schema version mismatch",
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "vecx/v8-version"
                ),
            )

            tampered_snapshot = copy.deepcopy(snapshot)
            tampered_snapshot["files"][replacement_path]["text"] += "\n"
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "vecx/v8-metadata-bytes"
                )
            )

            tampered_snapshot["files"][replacement_path]["sha256"] = (
                pipeline.sha256_bytes(
                    tampered_snapshot["files"][replacement_path]["text"].encode()
                )
            )
            snapshot_path.write_text(
                json.dumps(tampered_snapshot), encoding="utf-8"
            )
            self.assertTrue(
                any(
                    "recipe record digest mismatch" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, record, "vecx/v8-metadata-rehashed"
                    )
                )
            )

            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            wrong_metadata = copy.deepcopy(record)
            wrong_metadata["metadata"]["sha256"] = "b" * 64
            self.assertTrue(
                any(
                    "metadata does not match" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, wrong_metadata, "vecx/v8-output-metadata"
                    )
                )
            )

            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            forbidden = copy.deepcopy(record)
            forbidden["artifact"]["needed"].append("libGL.so.1")
            self.assertTrue(
                any(
                    "dependency policy" in error
                    for error in pipeline.verify_recipe_snapshot(
                        snapshot_path, forbidden, "vecx/v8-dependency"
                    )
                )
            )

    def test_vecx_metadata_replacement_is_output_bound(self) -> None:
        catalog_path = ROOT / "manifests" / "core-builds.json"
        catalog = pipeline.load_catalog(catalog_path)
        core_id = "vecx"
        spec = catalog["cores"][core_id]
        arch = "arm64"
        replacement = spec["metadata"]["replacement"]
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            root = Path(directory)
            artifact = root / spec["build"]["artifact_name"]
            metadata = root / spec["metadata"]["artifact_name"]
            log = root / "build.log"
            artifact.write_bytes(b"artifact")
            metadata.write_bytes((ROOT / replacement["path"]).read_bytes())
            log.write_text(
                build_vecx_log_fixture(arch),
                encoding="utf-8",
            )
            expected_artifact = {
                "status": "valid",
                "path": artifact.name,
                "sha256": pipeline.sha256_file(artifact),
                "size": artifact.stat().st_size,
                "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
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

                metadata.write_bytes(b"self-consistent wrong metadata\n")
                wrong = copy.deepcopy(document)
                wrong["metadata"].update(
                    {
                        "sha256": pipeline.sha256_file(metadata),
                        "size": metadata.stat().st_size,
                    }
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "exact catalog replacement"
                ):
                    pipeline.validate_build_record_identity(
                        wrong, record, catalog_path, catalog
                    )

            wrong_metadata = {
                "status": "valid",
                "path": spec["metadata"]["artifact_name"],
                "sha256": "b" * 64,
                "size": 1,
            }
            package_result = pipeline.package_e2e_core(
                root,
                core_id,
                [
                    {
                        "architecture": target,
                        "result": "passed",
                        "metadata": copy.deepcopy(wrong_metadata),
                    }
                    for target in spec["targets"]
                ],
                spec,
            )
            self.assertEqual("not_packaged", package_result["result"])
            self.assertIn("catalog replacement", package_result["reason"])


if __name__ == "__main__":
    unittest.main()
