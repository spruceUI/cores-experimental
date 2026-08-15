"""blueMSX reviewed pins, lifecycle behaviors, and negative controls.

Promotion-derived bindings are covered for every core by
``tests/test_evidence_bindings.py`` against
``pins/evidence/bluemsx.json``; this file keeps the reviewed caveat
tokens and the fail-closed mutation/tamper behaviors, plus the channel
lifecycle the parametric gate does not exercise.
"""

from __future__ import annotations

import copy
from collections import Counter
import shlex
import unittest
from unittest import mock
import zipfile

from .support import pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import bluemsx
from core_pipeline_lib.records import compatibility as compatibility_records

from .support import (
    ROOT,
    copied_e2e_run,
    evidence_handles,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "bluemsx"
OTHER_CORE_ID = "fmsx"

_H = evidence_handles(CORE_ID)
PIN_NAME = _H["PIN_NAME"]
SEMANTIC_ID = _H["SEMANTIC_ID"]
PIN_PATH = _H["PIN_PATH"]
SOURCE_SET_PATH = _H["SOURCE_SET_PATH"]
SOURCE_COMMIT = _H["SOURCE_COMMIT"]
SOURCE_TREE = _H["SOURCE_TREE"]
SELECTION_SHA256 = _H["SELECTION_SHA256"]
SELECTED_RUN = _H["SELECTED_RUN"]
REPRODUCTION_RUN = _H["REPRODUCTION_RUN"]
PACKAGE_SHA256 = _H["PACKAGE_SHA256"]
PACKAGE_SIZE = _H["PACKAGE_SIZE"]
PIN_FILE_SHA256 = _H["PIN_FILE_SHA256"]
PIN_CONTENT_SHA256 = _H["PIN_CONTENT_SHA256"]
CATALOG_SHA256 = _H["CATALOG_SHA256"]
CORE_SPEC_SHA256 = _H["CORE_SPEC_SHA256"]
PIPELINE_SHA256 = _H["PIPELINE_SHA256"]
PIPELINE_BUNDLE_CONTENT_SHA256 = _H["PIPELINE_BUNDLE_CONTENT_SHA256"]
WORKFLOW_SHA256 = _H["WORKFLOW_SHA256"]
RECIPE_HEAD = _H["RECIPE_HEAD"]
TOOLCHAIN_LOCK_FILE_SHA256 = _H["TOOLCHAIN_LOCK_FILE_SHA256"]
TOOLCHAIN_LOCK_CONTENT_SHA256 = _H["TOOLCHAIN_LOCK_CONTENT_SHA256"]
LIBRETRO_SUPER_COMMIT = _H["LIBRETRO_SUPER_COMMIT"]
GIT_VERSION = _H["GIT_VERSION"]
TARGETS = _H["TARGETS"]

BLUEMSX_NATIVE_VERSION_MARKER = bluemsx.BLUEMSX_NATIVE_VERSION_MARKER
BLUEMSX_SOURCE_HEAD_MARKER = bluemsx.BLUEMSX_SOURCE_HEAD_MARKER
BLUEMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN = (
    bluemsx.BLUEMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN
)
BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN = (
    bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN
)
BLUEMSX_WARNING_SUPPRESSION_OPTION = (
    bluemsx.BLUEMSX_WARNING_SUPPRESSION_OPTION
)

CAVEAT_TOKENS = (
    "both ABI logs byte for byte",
    "no offline source cache",
    "exactly 269 compiles (255 C and 14 C++)",
    "native version ' 5f595c7' on every C compile and no C++ compile",
    "exactly one upstream -w warning-suppression option on every compile",
    "suppression consistency, not warning-free source code",
    "GPLv2",
    "mixed tree",
    "Public distribution",
    "302 candidate system files",
    "nine C-BIOS ROMs",
    "correctly staged Machines and Databases directories",
    "system-data redistribution remain human legal and policy gates",
    "Metadata declares no-game support, full-path loading, disk control",
    "ten-image M3U handling",
    "disk-overlay persistence",
    "fixed 4 MiB allocation",
    "non-default fixed-epoch RTC option",
    "Mouse entry points are stubs",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "All eight device views have empty eligibility sets",
    "all 16 device entries remain ineligible",
)



class BlueMsxCoreEvidenceTests(unittest.TestCase):
    def test_compatibility_retains_reviewed_caveat_tokens(self) -> None:
        _, _, _, compatibility = load_core_documents(CORE_ID, PIN_NAME)
        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)

    def test_channels_and_release_are_core_scoped_and_local_only(self) -> None:
        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        target_hashes = {
            "nightly": (
                "4309e5a4582bb319f7ba3a95ca527fe5f214be85a0975698863c4b0661f4145d"
            ),
            "pinned": PIN_FILE_SHA256,
            "release": (
                "ad937feb5dcb77e46a9f7656c947d23a21e237d3e1993bb2b07ec6570569844b"
            ),
        }
        content_hashes = {
            "nightly": (
                "659e7a247a681a4857aeb7a44149bfcbe1043d6809929b56542f5d8c96128c1e"
            ),
            "pinned": PIN_CONTENT_SHA256,
            "release": (
                "b632741f02bc3776f1d21fb76b679604c508b452090a1e32a19b9683f000c25a"
            ),
        }
        for channel, target_path in target_paths.items():
            with self.subTest(channel=channel):
                pointer = load_document(
                    ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
                )
                report = pipeline.validate_channel_pointer_document(
                    pointer, expected_channel=channel, expected_core=CORE_ID
                )
                self.assertEqual("valid", report["status"], report["errors"])
                self.assertEqual(2, pointer["schema_version"])
                self.assertEqual(CORE_ID, pointer["core_id"])
                self.assertEqual(channel, pointer["channel"])
                self.assertTrue(pointer["local_only"])
                self.assertEqual("disabled", pointer["publication"])
                self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
                self.assertEqual(target_path, pointer["target"]["path"])
                self.assertEqual(target_hashes[channel], pointer["target"]["file_sha256"])
                self.assertEqual(
                    content_hashes[channel], pointer["target"]["content_sha256"]
                )
                wrong_core = pipeline.validate_channel_pointer_document(
                    pointer,
                    expected_channel=channel,
                    expected_core=OTHER_CORE_ID,
                    verify_target=False,
                )
                self.assertEqual("invalid", wrong_core["status"])

        pin_path = ROOT / PIN_PATH
        pin = load_document(pin_path)
        release_root = ROOT / ".local-e2e" / "releases" / SEMANTIC_ID
        release_report = pipeline.validate_local_release(
            release_root,
            pin,
            file_sha256(pin_path),
            expected_release_id=SEMANTIC_ID,
        )
        self.assertEqual("valid", release_report["status"], release_report["errors"])
        release = load_document(release_root / "release-manifest.json")
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertTrue(release["local_only"])
        self.assertEqual("disabled", release["publication"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])
        self.assertEqual(PACKAGE_SIZE, release["assets"][0]["size"])
        self.assertEqual(SELECTION_SHA256, release["assets"][0]["selection_sha256"])


    def test_contract_rejects_source_version_suppression_and_order_mutations(
        self,
    ) -> None:
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
        lines = log_text.splitlines(keepends=True)
        compile_position = next(
            index
            for index, line in enumerate(lines)
            if " -c " in line
            and bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN in line
        )
        compile_line = lines.pop(compile_position)
        link_position = next(
            index
            for index, line in enumerate(lines)
            if "-o bluemsx_libretro.so" in line
        )
        lines.insert(link_position + 1, compile_line)
        reordered_log = "".join(lines)
        self.assertEqual(
            Counter(log_text.splitlines(keepends=True)),
            Counter(reordered_log.splitlines(keepends=True)),
        )
        cxx_line = next(
            line
            for line in log_text.splitlines(keepends=True)
            if line.startswith("aarch64-linux-gnu-g++") and " -c " in line
        )
        versioned_cxx_line = cxx_line.replace(
            " -c ",
            f" -c {bluemsx.BLUEMSX_NATIVE_GIT_VERSION_LOG_TOKEN} ",
            1,
        )
        mutations = {
            "source": log_text.replace(
                bluemsx.BLUEMSX_SOURCE_HEAD_MARKER,
                "HEAD is now at 0000000 tampered",
                1,
            ),
            "native-version-marker": log_text.replace(
                bluemsx.BLUEMSX_NATIVE_VERSION_MARKER, "", 1
            ),
            "native-version-on-cxx": log_text.replace(
                cxx_line, versioned_cxx_line, 1
            ),
            "missing-warning-suppression": log_text.replace(" -w ", " ", 1),
            "extra-warning": log_text + "warning: synthetic\n",
            "compile-after-link": reordered_log,
        }
        for label, mutated_log in mutations.items():
            with self.subTest(mutation=label):
                self.assertNotEqual(log_text, mutated_log)
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(
                        mutated_log, CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                    )
                )

    def test_manifest_pin_source_set_and_reproduction_tampering_fail_closed(
        self,
    ) -> None:
        _, pin, compatibility_path, compatibility = load_core_documents(
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
            same_run, document_path=compatibility_path, repository_root=ROOT
        )
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        malformed_pin = copy.deepcopy(pin)
        malformed_pin["sources"][0]["file_sha256"] = "0" * 64
        malformed_pin["content_sha256"] = pipeline.pin_set_content_sha256(
            malformed_pin
        )
        with mock.patch.object(
            compatibility_records, "load_json", return_value=malformed_pin
        ):
            pin_report = pipeline.validate_core_compatibility_document(
                compatibility,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
        self.assertEqual("invalid", pin_report["status"])
        self.assertIn(
            "individual core pin: source 0 no longer matches the pin",
            pin_report["errors"],
        )

        source_set = registry.composed_source_set(SEMANTIC_ID)
        malformed_source_set = copy.deepcopy(source_set)
        malformed_source_set["sources"][CORE_ID]["commit"] = "0" * 40
        with self.assertRaisesRegex(
            registry.RegistryError, "source set reference path does not bind bluemsx"
        ):
            registry.validate_source_set(malformed_source_set)

        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-bluemsx-log-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_path.write_text(
                log_path.read_text(encoding="utf-8") + "warning: synthetic\n",
                encoding="utf-8",
            )
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)
            with self.assertRaisesRegex(
                pipeline.PipelineError, "build log does not prove"
            ):
                pipeline._validate_compatibility_e2e_run(
                    run_root / "e2e-record.json", CORE_ID, expected_targets
                )

    def _assert_recipe(self, recipe: dict[str, object]) -> None:
        self.assertEqual(CORE_ID, recipe["core_id"])
        self.assertEqual(".github/workflows/build-bluemsx.yml", recipe["workflow"])
        self.assertEqual(WORKFLOW_SHA256, recipe["workflow_sha256"])
        self.assertEqual(RECIPE_HEAD, recipe["repository_head"])
        self.assertFalse(recipe["repository_dirty"])
        self.assertEqual(CORE_SPEC_SHA256, recipe["core_spec_sha256"])
        self.assertEqual(CATALOG_SHA256, recipe["catalog_sha256"])
        self.assertEqual(PIPELINE_SHA256, recipe["pipeline_sha256"])
        pipeline_bundle = recipe["pipeline_bundle"]
        self.assertIsInstance(pipeline_bundle, dict)
        assert isinstance(pipeline_bundle, dict)
        self.assertEqual(
            PIPELINE_BUNDLE_CONTENT_SHA256, pipeline_bundle["content_sha256"]
        )
        files = pipeline_bundle["files"]
        self.assertIsInstance(files, dict)
        assert isinstance(files, dict)
        self.assertIn("scripts/core_pipeline_lib/contracts/bluemsx.py", files)

    def _assert_toolchain(
        self, toolchain: dict[str, object], expected: dict[str, object]
    ) -> None:
        self.assertEqual(expected["image_id"], toolchain["image_id"])
        self.assertEqual(expected["image_id"], toolchain["resolved_image_id"])
        self.assertEqual(LIBRETRO_SUPER_COMMIT, toolchain["libretro_super_commit"])
        provenance = toolchain["archive_provenance"]
        self.assertIsInstance(provenance, dict)
        assert isinstance(provenance, dict)
        archive = provenance["archive"]
        self.assertIsInstance(archive, dict)
        assert isinstance(archive, dict)
        self.assertEqual(expected["toolchain_archive_sha256"], archive["sha256"])
        self.assertEqual(expected["toolchain_archive_size"], archive["size"])
        lock = provenance["lock"]
        self.assertIsInstance(lock, dict)
        assert isinstance(lock, dict)
        self.assertEqual("local-cache-v1", lock["lock_id"])
        self.assertEqual(TOOLCHAIN_LOCK_FILE_SHA256, lock["file_sha256"])
        self.assertEqual(TOOLCHAIN_LOCK_CONTENT_SHA256, lock["content_sha256"])

    def _assert_compile_scope(
        self, log_text: str, expected: dict[str, object]
    ) -> None:
        compilers = expected["compilers"]
        self.assertIsInstance(compilers, tuple)
        compile_commands: list[list[str]] = []
        for line in log_text.splitlines():
            try:
                tokens = shlex.split(line)
            except ValueError:
                continue
            if tokens and tokens[0] in compilers and "-c" in tokens:
                compile_commands.append(tokens)
        self.assertEqual(269, len(compile_commands))
        cxx_compiler = expected["cxx_compiler"]
        c_commands = [tokens for tokens in compile_commands if tokens[0] != cxx_compiler]
        cxx_commands = [tokens for tokens in compile_commands if tokens[0] == cxx_compiler]
        self.assertEqual(255, len(c_commands))
        self.assertEqual(14, len(cxx_commands))
        for tokens in compile_commands:
            self.assertEqual(1, tokens.count(bluemsx.BLUEMSX_WARNING_SUPPRESSION_OPTION))
        for tokens in c_commands:
            self.assertEqual(
                [bluemsx.BLUEMSX_NATIVE_GIT_VERSION_COMPILE_TOKEN],
                [token for token in tokens if "GIT_VERSION" in token],
            )
        for tokens in cxx_commands:
            self.assertEqual([], [token for token in tokens if "GIT_VERSION" in token])


if __name__ == "__main__":
    unittest.main()
