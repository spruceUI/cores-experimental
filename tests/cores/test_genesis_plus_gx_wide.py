"""Pinned Genesis Plus GX Wide build-evidence and lifecycle tests."""

from __future__ import annotations

import copy
import json
import unittest
from collections import Counter
from unittest import mock
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.records import compatibility as compatibility_records

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "genesis_plus_gx_wide"
OTHER_CORE_ID = "genesis_plus_gx"
PIN_NAME = "genesis_plus_gx_wide-29d9d104338f-6184c4659fe1.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/genesis_plus_gx_wide/"
    "29d9d104338f46bc2e65438fb207bcf54f701e92.json"
)
SOURCE_COMMIT = "29d9d104338f46bc2e65438fb207bcf54f701e92"
SOURCE_TREE = "27e05ed457d9c10e51b6c69067e1c05599df08fb"
SOURCE_URL = "https://github.com/libretro/Genesis-Plus-GX-Wide.git"
SOURCE_LOCK_ID = "genesis_plus_gx_wide-29d9d104338f"
SOURCE_LOCK_FILE_SHA256 = (
    "bebe6a156f6096563160e53131ba51e722e1ee9be5044cdc6482395a466fd410"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "6fe3c024bf90d9b06a0a20794b4bb2093258f6c2062716b62ed179597fe5d19d"
)
PIN_FILE_SHA256 = (
    "f01910057d7ff502756d7f88ce37d7b3b3598835fef4d209cbe59e9e22b9ea59"
)
PIN_CONTENT_SHA256 = (
    "84349c820bdea177c583303e57de384176411d45c8ee81e0c718ec93f0cd6dc9"
)
SOURCE_SET_FILE_SHA256 = (
    "18faddaba3af2cb18c8af38336fe873f1daca81587f22fc62816acb300299173"
)
SOURCE_SET_CONTENT_SHA256 = (
    "0d55183d152232cc9c8b78afd5240726264026d2f3665f47085be38b6601f010"
)
COMPATIBILITY_FILE_SHA256 = (
    "a32315be581ad74a5d7b16f3a28b1fe473e60808aac622f13dee38edef8f2239"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "d7092e306609699a3a1f6fecc3044d432ecac24437cfb62c603248ad491ee8e1"
)
SELECTION_SHA256 = (
    "6184c4659fe120b95186d6ed505a3b528767ac8d6ed3c1014f876c3ba0d5f9bf"
)
SELECTED_RUN = "actions-sim-build-core-genesis_plus_gx_wide-w3c"
REPRODUCTION_RUN = "build-core-genesis_plus_gx_wide-local-w3c"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "4d578c0bc71f475fc10fd9749d5f784f7376a3aba5f30bfdbe7b20e5b0cd8ae4"
    ),
    REPRODUCTION_RUN: (
        "8c68eea6dd90219ae98cab6072b5ccb28298963c9f1411b5dbf97e8a70b63340"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "98e08a7bf11afb4b55bb64771d367a6841add1dc1f50823a153fcf330b3b5e8a"
    ),
    REPRODUCTION_RUN: (
        "a2d5fcfb0895b77ef50fb9aa0d9d47e14fcd64d50d502970d10e30886dabb69f"
    ),
}
PACKAGE_SHA256 = (
    "192a09032d5d6d087131b1fd4507d1c01eeff3eba8bf60e590d65b558d7d7ebc"
)
PACKAGE_SIZE = 2218602
METADATA_SHA256 = (
    "8aa2205e8a3ea2cf2ed04d5ae83eed52c4e9ca6b8d2722afa2bb853a9939357c"
)
METADATA_SIZE = 2917
PIPELINE_BUNDLE_SHA256 = (
    "964db21eb766f5fae148f4e6c7df3ab15ac7ca5e7e281d8f3daaee56da35df73"
)
REPOSITORY_HEAD = "197d7cc1f9a4bb96cf9af4c7292e95a0826ee7af"
WORKFLOW_SHA256 = (
    "58227c8bf376e523894d1a83c66036c09df5b00d359fef10bb5836ffd753c047"
)
NATIVE_GIT_VERSION = " 29d9d10"
BASE_SOURCE_COMMIT = "fa4dca561e08d5be9077419f7b255e1da213ed21"
BASE_SOURCE_TREE = "7f4b0916e938e15e046e1c35acd0173aab1aaac3"
BASE_SELECTED_RUN = "actions-sim-build-core-genesis_plus_gx-w3"
RUNNERS = {
    SELECTED_RUN: {
        "backend": "local-docker",
        "local_only": True,
        "mode": "simulated",
        "profile": "github-actions",
        "publication": "disabled",
    },
    REPRODUCTION_RUN: {
        "backend": "local-docker",
        "local_only": True,
        "mode": "native",
        "profile": "local",
        "publication": "disabled",
    },
}
TARGETS = {
    "arm64": {
        "artifact_sha256": (
            "d9a21808b8ec081d0f44134feca26d73d1648e157d249173ef7948e1f17a6e58"
        ),
        "artifact_size": 12383136,
        "record_sha256": {
            SELECTED_RUN: (
                "1293ac3012191c67c06b4a63ec76f4bfbaef1250dafdd5f53bf688edc1512707"
            ),
            REPRODUCTION_RUN: (
                "4a5ee6c3b913ad04272c9cefe2eabffa650bcb1c0f8f51e9878a03896d34ca0f"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "1df0194482739b79b6a6c740f6b5d8b945018eea6874daed1d70e8dc0419dbe7"
            ),
            REPRODUCTION_RUN: (
                "d2dbd8892dd356a66d1c433af44a5beb82d8084d0e957dd8f782696bed4c125c"
            ),
        },
        "log_size": 90711,
        "log_lines": 163,
        "warning_count": 2,
        "note_count": 1,
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6"],
        "version_requirements": ["GLIBC_2.17"],
        "execution_profile_id": "ra64-universal-v1",
        "image_id": (
            "sha256:538411e2759cd5482068fd0c1f24d5a033138cd9f49db31f2c620929a8b046a9"
        ),
        "archive_sha256": (
            "8a3bdd7f36a10a092209cd8f308d2d2a85e316be7ede6d42562074243b25bc64"
        ),
        "recipe_snapshot_sha256": (
            "a0d5ee950845078e01914169783ef0e1336601e4cd58e5a21afd7eeb497318c4"
        ),
        "recipe_snapshot_size": 2047204,
    },
    "armhf": {
        "artifact_sha256": (
            "4cd1ef2a6296c52707ccd5ea4263a02b4f0ffb4b1b90931b68e388d429a9ffa6"
        ),
        "artifact_size": 6374200,
        "record_sha256": {
            SELECTED_RUN: (
                "f92d0023424fd4db453f61a69986c74fb1f80a04ab4b7e9942797966dfa53f6d"
            ),
            REPRODUCTION_RUN: (
                "21e5540ee4cc1489f5e430ad1b8f957ea230d042ba39cea82bdd17af8a60cf18"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "9d52149408262de1a3b22b549ecc07b9283ce7c1968e728c2188927ea39551f4"
            ),
            REPRODUCTION_RUN: (
                "9d52149408262de1a3b22b549ecc07b9283ce7c1968e728c2188927ea39551f4"
            ),
        },
        "log_size": 89680,
        "log_lines": 142,
        "warning_count": 0,
        "note_count": 0,
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:393a23661c4178edfc4e5ea0221e5de317a40f2f50a9fff1cb76e9e322189dd9"
        ),
        "archive_sha256": (
            "f297cbf988aeb15c3de90c1bc900494aaf4214320aa5fcfa2cbbf10d2e32f16e"
        ),
        "recipe_snapshot_sha256": (
            "5e69d08a3e694d3b94e80bf1b1c94674b146e60d0f6432003f48dd0e5cb12140"
        ),
        "recipe_snapshot_size": 2047212,
    },
}
SOURCE_RECORD_IDENTITY = {
    "commit": SOURCE_COMMIT,
    "requested_ref": "refs/heads/main",
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
    "tree": SOURCE_TREE,
    "url": SOURCE_URL,
}
CAVEAT_TOKENS = (
    "both build logs byte for byte",
    "106 C compile commands",
    "two reviewed warnings and one note",
    "genesis_plus_gx_wide_*",
    "GENPLUS-GX 1.7.6",
    "GENPLUS-GX 1.7.7",
    "Base-to-Wide",
    "Non-commercial",
    "corresponding source",
    "human legal and policy gate",
    "no offline source bundle",
    "dockerfile_linkage=unverified-local-cache",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "TRIMUI_SMART_PRO",
    "all device views remain ineligible",
)


class GenesisPlusGxWideCoreEvidenceTests(unittest.TestCase):
    def test_semantic_pin_and_compatibility_bind_promoted_evidence(self) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        pin_report = pipeline.validate_pin_set_document(pin, document_path=pin_path)
        self.assertEqual("valid", pin_report["status"], pin_report["errors"])
        compatibility_report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual(
            "valid", compatibility_report["status"], compatibility_report["errors"]
        )

        self.assertEqual(PIN_FILE_SHA256, file_sha256(pin_path))
        self.assertEqual(PIN_CONTENT_SHA256, pin["content_sha256"])
        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertIsNone(pin["parent"])
        self.assertTrue(pin["local_only"])
        self.assertEqual("disabled", pin["publication"])

        self.assertEqual(
            COMPATIBILITY_FILE_SHA256, file_sha256(compatibility_path)
        )
        self.assertEqual(
            COMPATIBILITY_CONTENT_SHA256, compatibility["content_sha256"]
        )
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual(PIN_PATH, compatibility["golden_source"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN],
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            E2E_CONTENT_SHA256[REPRODUCTION_RUN],
            compatibility["reproduction_e2e_content_sha256"],
        )

        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)
        for reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            SOURCE_LOCK_PATH,
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
        ):
            self.assertNotIn("tranche", reference.casefold())

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SIZE, selection["package"]["size"])
        self.assertEqual(METADATA_SHA256, selection["metadata"]["sha256"])
        self.assertEqual(METADATA_SIZE, selection["metadata"]["size"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        self.assertEqual(set(TARGETS), set(compatibility["targets"]))

        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                selected_target = selection["targets"][architecture]
                golden = selected_target["golden_record"]
                artifact = golden["artifact"]
                target = compatibility["targets"][architecture]

                self.assertEqual(SOURCE_RECORD_IDENTITY, golden["source"])
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    expected["version_requirements"], artifact["version_requirements"]
                )
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual([], golden["build"]["compile_definitions"])
                self.assertEqual(
                    NATIVE_GIT_VERSION,
                    golden["build"]["git_version"]["value"],
                )

                recipe = golden["recipe"]
                self.assertFalse(recipe["repository_dirty"])
                self.assertEqual(REPOSITORY_HEAD, recipe["repository_head"])
                self.assertEqual(
                    PIPELINE_BUNDLE_SHA256,
                    recipe["pipeline_bundle"]["content_sha256"],
                )
                self.assertEqual(
                    ".github/workflows/build-genesis_plus_gx_wide.yml",
                    recipe["workflow"],
                )
                self.assertEqual(WORKFLOW_SHA256, recipe["workflow_sha256"])

                toolchain = golden["toolchain"]
                self.assertEqual(expected["image_id"], toolchain["image_id"])
                self.assertEqual(expected["image_id"], toolchain["resolved_image_id"])
                self.assertEqual(
                    "unverified-local-cache", toolchain["dockerfile_linkage"]
                )
                self.assertEqual(
                    expected["archive_sha256"],
                    toolchain["archive_provenance"]["archive"]["sha256"],
                )
                snapshot = golden["local_store"]["recipe_snapshots"][architecture]
                self.assertEqual(expected["recipe_snapshot_sha256"], snapshot["sha256"])
                snapshot_path = ROOT / snapshot["path"]
                self.assertEqual(
                    expected["recipe_snapshot_size"], snapshot_path.stat().st_size
                )
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path, golden, f"{CORE_ID}/{architecture}"
                    ),
                )

    def test_source_set_release_and_channels_are_core_owned(self) -> None:
        source_set_path = ROOT / SOURCE_SET_PATH
        source_set = load_document(source_set_path)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SOURCE_SET_FILE_SHA256, file_sha256(source_set_path))
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"])
        self.assertEqual({CORE_ID}, set(source_set["sources"]))

        source = source_set["sources"][CORE_ID]
        source_lock = load_document(ROOT / SOURCE_LOCK_PATH)
        self.assertEqual(SOURCE_LOCK_PATH, source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, source["file_sha256"])
        self.assertEqual(SOURCE_LOCK_CONTENT_SHA256, source["content_sha256"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, file_sha256(ROOT / SOURCE_LOCK_PATH))
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/main",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
                "submodules": [],
            },
            source_lock["source"],
        )

        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
        cells = {cell["architecture"]: cell for cell in report["build_evidence_cells"]}
        self.assertEqual(set(TARGETS), set(cells))
        for architecture, expected in TARGETS.items():
            self.assertEqual(
                expected["artifact_sha256"], cells[architecture]["artifact_sha256"]
            )
            self.assertEqual(
                expected["execution_profile_id"],
                cells[architecture]["execution_profile_id"],
            )
        self.assertEqual(8, len(report["device_views"]))
        self.assertTrue(
            all(
                view["status"] == "provisional"
                and view["eligibility"] == "provisional-unverified"
                and not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )

        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            pointer = load_document(
                ROOT / ".local-e2e" / "channels" / f"{channel}.{CORE_ID}.json"
            )
            pointer_report = pipeline.validate_channel_pointer_document(
                pointer, expected_channel=channel, expected_core=CORE_ID
            )
            self.assertEqual(
                "valid", pointer_report["status"], pointer_report["errors"]
            )
            self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
            self.assertEqual(target_path, pointer["target"]["path"])
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
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

        nightly = load_document(
            ROOT / ".local-e2e" / "nightlies" / SEMANTIC_ID / "golden.json"
        )
        imported = nightly["cores"][CORE_ID]["artifacts"]
        self.assertEqual(
            "96eb5e2771e03ae3c867b31db8d8413e951c2dff4e3fb4b7ac8b1749b3f44742",
            imported["arm64"]["sha256"],
        )
        self.assertEqual(11534200, imported["arm64"]["size"])
        self.assertEqual({"status": "not_shipped"}, imported["armhf"])

    def test_selected_and_reproduction_runs_are_byte_reproducible(self) -> None:
        pin = load_document(ROOT / PIN_PATH)
        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts = {architecture: [] for architecture in TARGETS}
        logs = {architecture: [] for architecture in TARGETS}

        for run_id, expected_runner in RUNNERS.items():
            run_root = ROOT / ".local-e2e" / "runs" / run_id
            evidence_path = run_root / "e2e-record.json"
            evidence = load_document(evidence_path)
            self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
            self.assertEqual(E2E_CONTENT_SHA256[run_id], evidence["content_sha256"])
            self.assertEqual("passed", evidence["result"])
            self.assertEqual(expected_runner, evidence["runner"])
            validated = pipeline._validate_compatibility_e2e_run(
                evidence_path, CORE_ID, expected_targets
            )
            self.assertEqual(run_id, validated["run_id"])

            package = evidence["packages"][0]
            package_path = run_root / package["path"]
            self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
            self.assertEqual(PACKAGE_SIZE, package_path.stat().st_size)
            packages.append(package_path.read_bytes())
            with zipfile.ZipFile(package_path) as archive:
                self.assertEqual(
                    {
                        "cores64/genesis_plus_gx_wide_libretro.so",
                        "cores/genesis_plus_gx_wide_libretro.so",
                        "genesis_plus_gx_wide_libretro.info",
                        "manifest.json",
                    },
                    set(archive.namelist()),
                )
                self.assertTrue(
                    all(
                        info.date_time == (1980, 1, 1, 0, 0, 0)
                        for info in archive.infolist()
                    )
                )
                package_manifest = json.loads(archive.read("manifest.json"))
                self.assertTrue(package_manifest["local_only"])
                self.assertEqual("disabled", package_manifest["publication"])

            for architecture, expected in TARGETS.items():
                record_path = run_root / CORE_ID / architecture / "build-record.json"
                record = load_document(record_path)
                self.assertEqual(
                    expected["record_sha256"][run_id], file_sha256(record_path)
                )
                self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                self.assertEqual(
                    NATIVE_GIT_VERSION,
                    record["build"]["git_version"]["value"],
                )

                log_path = record_path.parent / record["build"]["log"]
                log_text = log_path.read_text(encoding="utf-8")
                self.assertEqual(
                    expected["log_sha256"][run_id], file_sha256(log_path)
                )
                self.assertEqual(expected["log_size"], log_path.stat().st_size)
                self.assertEqual(expected["log_lines"], len(log_text.splitlines()))
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(
                        log_text, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
                    )
                )
                self.assertEqual(
                    expected["warning_count"],
                    sum("warning:" in line for line in log_text.splitlines()),
                )
                self.assertEqual(
                    expected["note_count"],
                    sum("note:" in line for line in log_text.splitlines()),
                )
                logs[architecture].append(log_path.read_bytes())

                artifact_path = record_path.parent / record["artifact"]["path"]
                artifact_bytes = artifact_path.read_bytes()
                self.assertEqual(
                    expected["artifact_sha256"], file_sha256(artifact_path)
                )
                self.assertIn(b"GENPLUS-GX 1.7.7", artifact_bytes)
                self.assertIn(b"v1.7.4 29d9d10", artifact_bytes)
                artifacts[architecture].append(artifact_bytes)

                metadata_path = record_path.parent / record["metadata"]["path"]
                self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                metadata_payloads.append(metadata_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads)
        )
        metadata_text = metadata_payloads[0].decode("utf-8")
        self.assertIn(
            'display_name = "Sega - MS/GG/MD/CD (Genesis Plus GX Wide)"',
            metadata_text,
        )
        self.assertIn('license = "Non-commercial"', metadata_text)
        self.assertIn('core_options_version = "1.0"', metadata_text)
        self.assertIn('savestate_features = "deterministic"', metadata_text)
        for architecture in TARGETS:
            self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
            # The pinned per-run log hashes state whether the independent runs
            # reproduced the log byte for byte or merely reordered complete
            # lines under parallel make; hold the bytes to it.
            pinned = TARGETS[architecture]["log_sha256"]
            if pinned[SELECTED_RUN] == pinned[REPRODUCTION_RUN]:
                self.assertEqual(logs[architecture][0], logs[architecture][1])
            else:
                self.assertNotEqual(logs[architecture][0], logs[architecture][1])
                self.assertEqual(
                    Counter(logs[architecture][0].splitlines(keepends=True)),
                    Counter(logs[architecture][1].splitlines(keepends=True)),
                )

    def test_fresh_base_and_wide_logs_are_reciprocally_rejected(self) -> None:
        for architecture in TARGETS:
            wide_log = (
                ROOT
                / ".local-e2e"
                / "runs"
                / SELECTED_RUN
                / CORE_ID
                / architecture
                / "build.log"
            ).read_text(encoding="utf-8")
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    wide_log, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
                )
            )
            self.assertFalse(
                pipeline.registered_core_log_contract_proves(
                    wide_log,
                    OTHER_CORE_ID,
                    architecture,
                    BASE_SOURCE_COMMIT,
                    BASE_SOURCE_TREE,
                )
            )

            base_log = (
                ROOT
                / ".local-e2e"
                / "runs"
                / BASE_SELECTED_RUN
                / OTHER_CORE_ID
                / architecture
                / "build.log"
            ).read_text(encoding="utf-8")
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    base_log,
                    OTHER_CORE_ID,
                    architecture,
                    BASE_SOURCE_COMMIT,
                    BASE_SOURCE_TREE,
                )
            )
            self.assertFalse(
                pipeline.registered_core_log_contract_proves(
                    base_log, CORE_ID, architecture, SOURCE_COMMIT, SOURCE_TREE
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
            "core compatibility content digest is invalid",
            digest_report["errors"],
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
        malformed_pin["content_sha256"] = pipeline.pin_set_content_sha256(malformed_pin)
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

        malformed_source_set = load_document(ROOT / SOURCE_SET_PATH)
        malformed_source_set["sources"][CORE_ID]["commit"] = "0" * 40
        with self.assertRaisesRegex(
            registry.RegistryError,
            "source set reference path does not bind genesis_plus_gx_wide",
        ):
            registry.validate_source_set(malformed_source_set)

        expected_targets = pin["cores"][CORE_ID]["selection"]["targets"]
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-genesis-plus-gx-wide-log-",
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
                pipeline.PipelineError, "historical build differs"
            ):
                pipeline._validate_compatibility_e2e_run(
                    run_root / "e2e-record.json", CORE_ID, expected_targets
                )


if __name__ == "__main__":
    unittest.main()
