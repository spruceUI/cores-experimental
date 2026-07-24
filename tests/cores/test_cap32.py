"""Pinned Cap32 build-evidence and individual-lifecycle tests."""

from __future__ import annotations

from collections import Counter
import json
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import cap32

from .support import ROOT, file_sha256, load_core_documents, load_document


CORE_ID = "cap32"
OTHER_CORE_ID = "crocods"
PIN_NAME = "cap32-4abfb8be233b-afbc043051e8.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_LOCK_PATH = (
    "pins/sources/cap32/4abfb8be233bec630f369379fb6c1d92d31f1c7d.json"
)
SOURCE_COMMIT = "4abfb8be233bec630f369379fb6c1d92d31f1c7d"
SOURCE_TREE = "c9704612f7acd0459125bc28427212def1cce681"
SOURCE_URL = "https://github.com/libretro/libretro-cap32.git"
SOURCE_LOCK_ID = "cap32-4abfb8be233b"
SOURCE_LOCK_FILE_SHA256 = (
    "12ea97147599eaf8f7d7a4ae90bebf014a67e9a18a958e5296b0d54d1251a8b7"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "dd74cb116a010edd1c9366003e89d4c956f2c2324e6721c9a31afeb3388805db"
)
PIN_FILE_SHA256 = (
    "d6d4516884a0f3e1d5654944e601bad8688e7467ef1fe758acfc50194d4981c1"
)
PIN_CONTENT_SHA256 = (
    "232867bdbb6ad7b7d9ea5316d11421f5307a51b35b8e355ea2126bf2ee0d908b"
)
SOURCE_SET_FILE_SHA256 = (
    "16926bd8b787a31d4221bccd1c5cd708e91132e7454ccba6f5a2af836d6418b7"
)
SOURCE_SET_CONTENT_SHA256 = (
    "bb93108924bfb9754aca7f40dac6f8417e677529e705bf580c1c23048564946c"
)
COMPATIBILITY_FILE_SHA256 = (
    "b5f5e46666088f483f6738da0ab65a0ad2e2ff893b7359168e8ed7a802f50ac0"
)
COMPATIBILITY_CONTENT_SHA256 = (
    "701e50d56cbc44305404566da17d203c6f994ed37560cfa66f00fd84013b8855"
)
SELECTION_SHA256 = (
    "afbc043051e809ce29dc4f871215a19d4305a9050b8afe94a91182408ae58727"
)
SELECTED_RUN = "actions-sim-build-core-cap32-v1"
REPRODUCTION_RUN = "build-core-cap32-local-v1"
E2E_CONTENT_SHA256 = {
    SELECTED_RUN: (
        "3fcbf9eabc505f5774204ee2af85578f0c9bee03f11e019df69bc14a1858f15c"
    ),
    REPRODUCTION_RUN: (
        "5cc9c57888b1fe86d2d6d83a84aafebc62a07db45c16d0db0b65ebf30e2df556"
    ),
}
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "6c7f085b74d88f76e152af870d6bb7b32cb26b367899367d4f2284cb9b7db5ef"
    ),
    REPRODUCTION_RUN: (
        "f887546597823e7f3ba9dffefdc35a3178d73f463314a7f95f0393f352430f69"
    ),
}
PACKAGE_SHA256 = (
    "202f2729cc163b855a6b8a61637e0f847070e0d71c3eb83b2513164d95bba29d"
)
PACKAGE_SIZE = 717267
METADATA_SHA256 = (
    "7ef5d3ad67d195a5dc87ed62d9edf6732169cbde6da045583cc81a1264aad6fb"
)
METADATA_SIZE = 1282
PIPELINE_BUNDLE_SHA256 = (
    "d4f5928d2c412e75ee02378aa03b944d58625e35eae8bc047d50cf03eeed0c0d"
)
REPOSITORY_HEAD = "9d95cda3d6dce32c8d33d85a58f37adad19d38d7"
WORKFLOW_SHA256 = (
    "ad66cca95b366603feca6e38bb929cb9278551160746148808e6f30347bfd5bd"
)
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
            "b3afb302b744bce4e927bcca7e9a0f22f87ef8668c98b4c9fd4682843fbc16a9"
        ),
        "artifact_size": 1603256,
        "record_sha256": {
            SELECTED_RUN: (
                "b89e606b30b887d2e22479ec44c157885d5010a1ef29821deef37959891b607a"
            ),
            REPRODUCTION_RUN: (
                "698a413c35ce00129e7616aec41688495bf20e4c12cec23a045e00c564336bce"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "101837733cbeda6c8201f82188a30cc89939005fb194fdcdb0cc2c61af525863"
            ),
            REPRODUCTION_RUN: (
                "101837733cbeda6c8201f82188a30cc89939005fb194fdcdb0cc2c61af525863"
            ),
        },
        "log_size": 21868,
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
            "a00a763c3b6ab37da10a0b3fdb384bc939bb47c2a4df540140aa22b6646b1f71"
        ),
        "recipe_snapshot_size": 1980830,
    },
    "armhf": {
        "artifact_sha256": (
            "39025efe23d35dbeb392b376e140f83c0e11eeb5976a9c97c9fe4fbfc52b5a6b"
        ),
        "artifact_size": 1541028,
        "record_sha256": {
            SELECTED_RUN: (
                "4e5abcdab92d2c42a2b04d73c51bdaa5b37f246583e585fcc07db4223059515e"
            ),
            REPRODUCTION_RUN: (
                "166e6d4f7bb0b163f70b7ceb6db586f700ceea0a5fd0f057d80bfd00bdd539f1"
            ),
        },
        "log_sha256": {
            SELECTED_RUN: (
                "4015d39b7d3febae693b95be087c8e9b22b7ee274b88805968cbc1887c9b3088"
            ),
            REPRODUCTION_RUN: (
                "4015d39b7d3febae693b95be087c8e9b22b7ee274b88805968cbc1887c9b3088"
            ),
        },
        "log_size": 22194,
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4"],
        "execution_profile_id": "ra32-a30-v1",
        "image_id": (
            "sha256:e09ffce413cf62c14a24fd8aa3beebbbfaccd5b0b5223ac529d132f4aabd92b9"
        ),
        "archive_sha256": (
            "e2b103c7bf1fdc9bb3ce3cf7bcde9cf2f3fd473fb0d916e8b4d0b4d278fd1afe"
        ),
        "recipe_snapshot_sha256": (
            "a5f8dc713b1919d12b23a8cb0cea045bae9bc2994441555ad7fc8621791d22f1"
        ),
        "recipe_snapshot_size": 1980539,
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
    "44 C compile commands",
    "Makefile lines 485 and 511",
    "4.5.4 4abfb8b HI",
    "display_version v4.2.0",
    "GPLv2",
    "non-commercial redistribution terms",
    "human legal and policy gate",
    "no offline source bundle",
    "dockerfile_linkage=unverified-local-cache",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)


class Cap32CoreEvidenceTests(unittest.TestCase):
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
                        "value": cap32.CAP32_NATIVE_GIT_VERSION,
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
                    ".github/workflows/build-cap32.yml", recipe["workflow"]
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
        self.assertTrue(profile_report["device_views"])
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
                            "cores64/cap32_libretro.so",
                            "cores/cap32_libretro.so",
                            "cap32_libretro.info",
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
                            cap32.CAP32_NATIVE_GIT_VERSION,
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
                        self.assertNotIn("warning:", log_text.casefold())
                        self.assertNotIn("note:", log_text.casefold())
                        log_lines[architecture].append(Counter(log_text.splitlines()))
                        logs[architecture].append(log_path.read_bytes())

                        artifact_path = record_path.parent / record["artifact"]["path"]
                        self.assertEqual(
                            expected["artifact_sha256"], file_sha256(artifact_path)
                        )
                        artifacts[architecture].append(artifact_path.read_bytes())
                        metadata_path = record_path.parent / record["metadata"]["path"]
                        self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                        metadata_payloads.append(metadata_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads)
        )
        metadata_text = metadata_payloads[0].decode("utf-8")
        self.assertIn('display_version = "v4.2.0"', metadata_text)
        self.assertIn('license = "GPLv2"', metadata_text)
        self.assertIn(
            'supported_extensions = "dsk|sna|zip|tap|cdt|voc|cpr|m3u"',
            metadata_text,
        )
        self.assertIn('supports_no_game = "true"', metadata_text)
        self.assertIn('needs_fullpath = "true"', metadata_text)
        self.assertIn('disk_control = "true"', metadata_text)
        self.assertIn('needs_kbd_mouse_focus = "true"', metadata_text)
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
                self.assertEqual(log_lines[architecture][0], log_lines[architecture][1])
                # The pinned per-run log hashes state whether the independent
                # runs reproduced the log byte for byte or merely reordered
                # complete lines under parallel make; hold the bytes to it.
                pinned = TARGETS[architecture]["log_sha256"]
                if pinned[SELECTED_RUN] == pinned[REPRODUCTION_RUN]:
                    self.assertEqual(logs[architecture][0], logs[architecture][1])
                else:
                    self.assertNotEqual(logs[architecture][0], logs[architecture][1])


if __name__ == "__main__":
    unittest.main()
