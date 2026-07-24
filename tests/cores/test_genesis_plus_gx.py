"""Pinned Genesis Plus GX build-evidence and individual-lifecycle tests."""

from __future__ import annotations

from collections import Counter
import json
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "genesis_plus_gx"
OTHER_CORE_ID = "genesis_plus_gx_wide"
PIN_NAME = "genesis_plus_gx-fa4dca561e08-0e5a55ff8180.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/genesis_plus_gx/"
    "fa4dca561e08d5be9077419f7b255e1da213ed21.json"
)
SOURCE_COMMIT = "fa4dca561e08d5be9077419f7b255e1da213ed21"
SOURCE_TREE = "7f4b0916e938e15e046e1c35acd0173aab1aaac3"
SOURCE_URL = "https://github.com/libretro/Genesis-Plus-GX.git"
SOURCE_LOCK_ID = "genesis_plus_gx-fa4dca561e08"
SOURCE_LOCK_FILE_SHA256 = (
    "dabdd8886b8de980cb3c208b6dab068f367f85b5f70e1aa28ab68d5e6bed3e98"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "c8f9eb3c43905052f6897b247f4229c661db58d96c2c92bb3894d749d9e1117c"
)
PIN_FILE_SHA256 = (
    "8446aaf5c2ff982ec5d72e5b64a87f1ba2c7869faa067bfd4d19bf4eebbd1bca"
)
PIN_CONTENT_SHA256 = (
    "1e8cb13f847835bf9d5b1a890e506d9307525f2f61e7e47a223bf6f57c78bd76"
)
SOURCE_SET_FILE_SHA256 = (
    "377450a819350c198f97356c471b24ed4897e8b53c47f9b2fa503a1e5ccbd074"
)
SOURCE_SET_CONTENT_SHA256 = (
    "edd3c9950da5d7129fa641732c2d92dbc9b50cf589897015ebeb7470c9f4851c"
)
COMPATIBILITY_FILE_SHA256 = (
    "46c95757283a2cfc5d126e098bb420647765aacada0ca51577c7c9aac42e68d9"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "3f1526cf4f779fbceb9a16f168149eb27b2bcc9e090362f2c64c27a0ca9261f2"
)
SELECTION_SHA256 = (
    "0e5a55ff8180895a8880000f6041323cb3f319f299782e75cc54ecf7534774e8"
)
SELECTED_RUN = "actions-sim-build-core-genesis_plus_gx-v1"
REPRODUCTION_RUN = "build-core-genesis_plus_gx-local-v1"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "f37d05ad0925787dd4d350a3bf79430a9e1b046cb4fcb57f22640c90d24a5000"
    ),
    REPRODUCTION_RUN: (
        "a19c73b1fb7ffe95c8e42804af49e371037b1ca5f6d9bc1bc28d2698dc941ee7"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "6a3a66bff78af02772e571db3e6c00f8033c4fad5d6e49c7b3a31c3bd6ee9255"
    ),
    REPRODUCTION_RUN: (
        "fd74c4a6cb0d663d2846dcd06cf2b3a25a74abff7b285e1e12f995312fd2bbca"
    ),
}
PACKAGE_SHA256 = (
    "06375fd783735dbc46ba41fdd47d7f774bee35bfa121d74bd6ceb92cdc9bb61f"
)
PACKAGE_SIZE = 2433019
METADATA_SHA256 = (
    "9793bff8d9e298a7ee0c94c0511dab242200ca60fbe87e3720eb9231a3e0166a"
)
METADATA_SIZE = 2788
PIPELINE_BUNDLE_SHA256 = (
    "d4f5928d2c412e75ee02378aa03b944d58625e35eae8bc047d50cf03eeed0c0d"
)
REPOSITORY_HEAD = "9d95cda3d6dce32c8d33d85a58f37adad19d38d7"
WORKFLOW_SHA256 = (
    "cbb408b254dd1adbda2acb07f3dd9d767193f431be58badd7beaf37e387d3d97"
)
NATIVE_GIT_VERSION = " fa4dca5"
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
            "fb8fadec4b547e2b51076c06baa4b46c69b1928ac89f9c1c77ceb056eda03982"
        ),
        "artifact_size": 13067184,
        "imported_artifact_sha256": (
            "d4cbc507414db7e587352fda530918abed1945f6a1a3efea61ad776e9da8e1b9"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "1605ce3471f565f6518ceb73b344fdb5f062d88e834cae5161782a54019bb771"
            ),
            REPRODUCTION_RUN: (
                "196af5f6b85f1395805e6580459193616a6ac196afa742dc1697c8e98c9781ea"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "1b946fc9d4e4cb700c12aab1deaa8ccb03943405b401bf19ad47db1f1e0cc93c"
            ),
            REPRODUCTION_RUN: (
                "6b90b5ab7fb16cfcd21ed58d7b2f1e492b1c31aa79b86110d5feea1bbcb4ffae"
            ),
        },
        "log_size": 110092,
        "warning_count": 2,
        "note_count": 1,
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.17", "GLIBC_2.29"],
        "execution_profile_id": "ra64-universal-v1",
        "image_id": (
            "sha256:cc8a545183ab61910e87b86b9d498ebff596ec8a253e28272e96f3f7a7fd4488"
        ),
        "archive_sha256": (
            "bb1c69cf19fcf3cbccaee06cc8b8a01bf7020fb1ac306d3d876530b6e9636012"
        ),
        "recipe_snapshot_sha256": (
            "b3cf1e554f4a4bb1dfaead93d495e5f13ddded4e1fef872eb9fd0cd8c3afc98a"
        ),
        "recipe_snapshot_size": 1980892,
    },
    "armhf": {
        "artifact_sha256": (
            "c122bf99857172e79fae360a4e5f7a314cb408065cf29c98ae08a57dcfda983b"
        ),
        "artifact_size": 6793332,
        "imported_artifact_sha256": (
            "6615fe3eb7e17a2ca9b40c38c1e9bea1002badef7e44eeeb2f741858eda77c18"
        ),
        "record_sha256": {
            SELECTED_RUN: (
                "9ce55a0ab2c47f66602d1327a654fd8a03298c2524e4e452d237fde974f0a676"
            ),
            REPRODUCTION_RUN: (
                "415d5f1158cb29185087305d50231de504feb7b07c7ebfc15644d5501828224d"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "fcac51db9ea06dee58581de12c2dd1b62674ebb7f74c2d1b173415ad91ca4140"
            ),
            REPRODUCTION_RUN: (
                "fcac51db9ea06dee58581de12c2dd1b62674ebb7f74c2d1b173415ad91ca4140"
            ),
        },
        "log_size": 109116,
        "warning_count": 0,
        "note_count": 0,
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4", "GLIBC_2.7"],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:e09ffce413cf62c14a24fd8aa3beebbbfaccd5b0b5223ac529d132f4aabd92b9"
        ),
        "archive_sha256": (
            "e2b103c7bf1fdc9bb3ce3cf7bcde9cf2f3fd473fb0d916e8b4d0b4d278fd1afe"
        ),
        "recipe_snapshot_sha256": (
            "78e0dce89bfd5698aff873d8c9f0253d24094fd63ba97677eff4e08fc7495653"
        ),
        "recipe_snapshot_size": 1980601,
    },
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
    "117 C compile commands",
    "two reviewed warnings and one note",
    "v1.7.4 fa4dca5",
    "core_options_version 2.0",
    "genesis_plus_gx_bram",
    "system-BRAM",
    "Non-commercial",
    "corresponding source",
    "human legal and policy gate",
    "no offline source bundle",
    "dockerfile_linkage=unverified-local-cache",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "Miyoo Mini",
    "Pixel 2",
    "Base-to-Wide",
    "all device views remain ineligible",
)


class GenesisPlusGxCoreEvidenceTests(unittest.TestCase):
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
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(
            COMPATIBILITY_FILE_SHA256, file_sha256(compatibility_path)
        )
        self.assertEqual(
            COMPATIBILITY_CONTENT_SHA256, compatibility["content_sha256"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SIZE, selection["package"]["size"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN], selection["e2e"]["content_sha256"]
        )
        self.assertEqual(
            E2E_CONTENT_SHA256[SELECTED_RUN],
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            E2E_CONTENT_SHA256[REPRODUCTION_RUN],
            compatibility["reproduction_e2e_content_sha256"],
        )
        self.assertEqual(
            f".local-e2e/runs/{SELECTED_RUN}/e2e-record.json",
            compatibility["e2e_run"],
        )
        self.assertEqual(
            f".local-e2e/runs/{REPRODUCTION_RUN}/e2e-record.json",
            compatibility["reproduction_run"],
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

        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden = selected_target["golden_record"]
                artifact = golden["artifact"]

                self.assertEqual(CORE_ID, golden["core_id"])
                self.assertEqual(architecture, golden["architecture"])
                self.assertEqual(SOURCE_RECORD_IDENTITY, golden["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual(
                    "needs-target-runtime", target["runtime_validation"]
                )
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
                self.assertEqual([], golden["build"]["compile_definitions"])
                self.assertEqual(
                    {
                        "compiler_scope": "c",
                        "derivation": "native-space-short7-v1",
                        "value": NATIVE_GIT_VERSION,
                    },
                    golden["build"]["git_version"],
                )
                self.assertEqual(METADATA_SHA256, golden["metadata"]["sha256"])
                self.assertEqual(METADATA_SIZE, golden["metadata"]["size"])

                recipe = golden["recipe"]
                self.assertFalse(recipe["repository_dirty"])
                self.assertEqual(REPOSITORY_HEAD, recipe["repository_head"])
                self.assertEqual(
                    PIPELINE_BUNDLE_SHA256,
                    recipe["pipeline_bundle"]["content_sha256"],
                )
                self.assertEqual(
                    ".github/workflows/build-genesis_plus_gx.yml", recipe["workflow"]
                )
                self.assertEqual(WORKFLOW_SHA256, recipe["workflow_sha256"])
                self.assertEqual(
                    "policies/core-commit-blacklist.json",
                    recipe["commit_blacklist"]["path"],
                )

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

                snapshot_reference = golden["local_store"]["recipe_snapshots"][
                    architecture
                ]
                self.assertEqual(
                    expected["recipe_snapshot_sha256"],
                    snapshot_reference["sha256"],
                )
                snapshot_path = ROOT / snapshot_reference["path"]
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
        profile_report = registry.report_data(source_set_path=SOURCE_SET_PATH)

        self.assertEqual(SOURCE_SET_FILE_SHA256, file_sha256(source_set_path))
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
        self.assertEqual(SEMANTIC_ID, source_set["evidence_pin"]["pin_id"])
        self.assertEqual(PIN_FILE_SHA256, source_set["evidence_pin"]["file_sha256"])
        self.assertEqual(
            PIN_CONTENT_SHA256, source_set["evidence_pin"]["content_sha256"]
        )
        self.assertEqual({CORE_ID}, set(source_set["sources"]))

        source = source_set["sources"][CORE_ID]
        self.assertEqual(SOURCE_LOCK_PATH, source["path"])
        self.assertEqual(SOURCE_LOCK_ID, source["source_lock_id"])
        self.assertEqual(SOURCE_COMMIT, source["commit"])
        self.assertEqual(SOURCE_LOCK_FILE_SHA256, source["file_sha256"])
        self.assertEqual(SOURCE_LOCK_CONTENT_SHA256, source["content_sha256"])
        source_lock = load_document(ROOT / SOURCE_LOCK_PATH)
        self.assertEqual(
            SOURCE_LOCK_FILE_SHA256, file_sha256(ROOT / SOURCE_LOCK_PATH)
        )
        self.assertEqual(SOURCE_LOCK_ID, source_lock["source_lock_id"])
        self.assertEqual(CORE_ID, source_lock["core_id"])
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
                "submodules": [],
            },
            source_lock["source"],
        )

        self.assertEqual(1, profile_report["counts"]["source_locks"])
        self.assertEqual(2, profile_report["counts"]["build_evidence_cells"])
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
        self.assertEqual(8, len(profile_report["device_views"]))
        self.assertEqual(
            16,
            sum(len(view["devices"]) for view in profile_report["device_views"]),
        )
        self.assertTrue(
            all(
                view["status"] == "provisional"
                and view["eligibility"] == "provisional-unverified"
                and not view["eligible_build_evidence_cells"]
                for view in profile_report["device_views"]
            )
        )

        target_paths = {
            "nightly": f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json",
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
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
        self.assertEqual(SEMANTIC_ID, release["release_id"])
        self.assertEqual([CORE_ID], [asset["core_id"] for asset in release["assets"]])
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])
        self.assertEqual(PACKAGE_SIZE, release["assets"][0]["size"])

        nightly = load_document(
            ROOT / ".local-e2e" / "nightlies" / SEMANTIC_ID / "golden.json"
        )
        for architecture, expected in TARGETS.items():
            imported = nightly["cores"][CORE_ID]["artifacts"][architecture]
            self.assertEqual(
                expected["imported_artifact_sha256"], imported["sha256"]
            )
            self.assertNotEqual(expected["artifact_sha256"], imported["sha256"])

    def test_selected_and_reproduction_runs_are_byte_reproducible(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        log_lines: dict[str, list[Counter[str]]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }

        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                run_root = ROOT / ".local-e2e" / "runs" / run_id
                evidence_path = run_root / "e2e-record.json"
                evidence = load_document(evidence_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
                self.assertEqual(E2E_CONTENT_SHA256[run_id], evidence["content_sha256"])
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    [CORE_ID], [package["core_id"] for package in evidence["packages"]]
                )

                package = evidence["packages"][0]
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                self.assertEqual(PACKAGE_SIZE, package_path.stat().st_size)
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/genesis_plus_gx_libretro.so",
                            "cores/genesis_plus_gx_libretro.so",
                            "genesis_plus_gx_libretro.info",
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
                    self.assertEqual(CORE_ID, package_manifest["core_id"])
                    self.assertTrue(package_manifest["local_only"])
                    self.assertEqual("disabled", package_manifest["publication"])
                    self.assertEqual(
                        METADATA_SHA256, package_manifest["metadata"]["sha256"]
                    )
                    for architecture, expected in TARGETS.items():
                        packaged_artifact = package_manifest["artifacts"][architecture]
                        self.assertEqual(
                            expected["artifact_sha256"], packaged_artifact["sha256"]
                        )
                        self.assertEqual(
                            expected["image_id"],
                            packaged_artifact["toolchain_image_id"],
                        )
                        self.assertEqual(
                            SOURCE_COMMIT, packaged_artifact["source_commit"]
                        )

                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        record_path = (
                            run_root / CORE_ID / architecture / "build-record.json"
                        )
                        record = load_document(record_path)
                        self.assertEqual(
                            expected["record_sha256"][run_id], file_sha256(record_path)
                        )
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual([], record["build"]["compile_definitions"])
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
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                log_text,
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
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
                        log_lines[architecture].append(Counter(log_text.splitlines()))
                        logs[architecture].append(log_path.read_bytes())

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifact_bytes = artifact_path.read_bytes()
                        self.assertIn(b"v1.7.4 fa4dca5", artifact_bytes)
                        artifacts[architecture].append(artifact_bytes)
                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata_payloads.append(metadata_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads)
        )
        metadata_text = metadata_payloads[0].decode("utf-8")
        self.assertIn('display_version = "v1.7.4"', metadata_text)
        self.assertIn('license = "Non-commercial"', metadata_text)
        self.assertIn('core_options_version = "2.0"', metadata_text)
        self.assertIn('firmware_count = 12', metadata_text)
        self.assertIn('needs_fullpath = "true"', metadata_text)
        self.assertIn('disk_control = "true"', metadata_text)
        self.assertIn('libretro_saves = "true"', metadata_text)
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                self.assertEqual(log_lines[architecture][0], log_lines[architecture][1])
        self.assertNotEqual(logs["arm64"][0], logs["arm64"][1])
        self.assertEqual(logs["armhf"][0], logs["armhf"][1])


if __name__ == "__main__":
    unittest.main()
