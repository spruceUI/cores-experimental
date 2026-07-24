"""LowRes NX individual lifecycle and evidence tests."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest
import zipfile

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from core_pipeline_lib.contracts import lowresnx

from .support import (
    ROOT,
    file_sha256,
    load_core_documents,
    load_document,
)


CORE_ID = "lowresnx"
OTHER_CORE_ID = "prosystem"
PIN_NAME = "lowresnx-35adc1a215e9-bcaea00ea240.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
SOURCE_COMMIT = "35adc1a215e975be964b2ef4b652117acd7beba1"
SOURCE_TREE = "766c70ca84d3a48769781072913a01db7f488a7b"
SOURCE_URL = "https://github.com/timoinutilis/lowres-nx.git"
SOURCE_LOCK_ID = "lowresnx-35adc1a215e9"
SELECTION_SHA256 = (
    "bcaea00ea240aa049a4cd341baf74c63d832ebf7c37d27a742afef9daf9a7201"
)
SELECTED_RUN = "actions-sim-build-core-lowresnx-w3"
REPRODUCTION_RUN = "build-core-lowresnx-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "b416de0fceb94aa968cfa04552b623e3f180b082e88026e39da0cdd74e15b713"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "a91179ddc86eaa2f1d8564e132e070c3029e3bf95d69c3498eb65e199c0d29bb"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "c2ca5841e4b5beb65e3b29f319226782055681268cf552793dd461acfab13924"
    ),
    REPRODUCTION_RUN: (
        "697b3803b46c91963303fc8607cedf04d869b43ae92650516385ef224f9b9f2b"
    ),
}
PACKAGE_SHA256 = (
    "e1db09b30c49fcb68f5fc1989fbbc7329d0666df39a36c3f85b937b2c19c91d3"
)
METADATA_SHA256 = (
    "3e6b2bf33038acb57158183eb030ac069ce95febc65bc61b79d1305273ad8d7a"
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
            "5e2bac4ee644665a6dbadefed0f050fb24edf51edce0f1c8219dceae836eb416"
        ),
        "artifact_size": 155672,
        "record_sha256": {
            SELECTED_RUN: (
                "c23c240973df13a68e0cd838797b89ae2cd77e959033daaf4972c13a879f657d"
            ),
            REPRODUCTION_RUN: (
                "c37129051475728bc3318c568f65a9a0160d66be666efbd3d6bcdb2579dcf288"
            ),
        },
        "log_sha256": (
            "266ffed71feed3711ebb532b37e4b7a1ed81ae38edfacfdc5b481d29c7a7294e"
        ),
        "elf": "ELF64/AArch64",
        "needed": ["ld-linux-aarch64.so.1", "libc.so.6", "libm.so.6"],
        "version_requirements": [
            "GLIBC_2.17",
            "GLIBC_2.27",
            "GLIBC_2.29",
        ],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "404cfb5b99f5b63638c1b20c15888664075a4e2c48944e52e69eb45915951d73"
        ),
        "artifact_size": 117208,
        "record_sha256": {
            SELECTED_RUN: (
                "f38da6cc05feea93ffd72441ea68c2e9965df0f9f745de68bda3d2843933b6d4"
            ),
            REPRODUCTION_RUN: (
                "cd3ae49e5200a131e7ededbb95a28d3331c7fcf05b16a0bb7ba30ba64d7a6409"
            ),
        },
        "log_sha256": (
            "b4ea85c19ca20991a2be6afd2435dd45bbd8d48790dd5a32e7075f3622388102"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libm.so.6"],
        "version_requirements": ["GLIBC_2.4"],
        "execution_profile_id": "ra32-a30-v1",
    },
}
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
    "all 43 C compile commands",
    "GLIBC_2.29",
    "zlib license",
    "no save-state support",
    "ra64-universal-v1",
    "ra32-a30-v1",
    "all device views remain ineligible",
)


class LowResNxCoreTests(unittest.TestCase):
    def test_semantic_pin_and_compatibility_bind_promoted_evidence(
        self,
    ) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )

        pin_report = pipeline.validate_pin_set_document(
            pin, document_path=pin_path
        )
        self.assertEqual("valid", pin_report["status"], pin_report["errors"])
        compatibility_report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual(
            "valid",
            compatibility_report["status"],
            compatibility_report["errors"],
        )
        self.assertEqual(SEMANTIC_ID, pin["pin_id"])
        self.assertEqual([CORE_ID], pin["scope"])
        self.assertEqual({CORE_ID}, set(pin["cores"]))
        self.assertIsNone(pin["parent"])
        self.assertEqual(CORE_ID, compatibility["core_id"])
        self.assertEqual("disabled", compatibility["publication"])
        self.assertEqual(
            "workspace-local-ignored", compatibility["evidence_availability"]
        )
        self.assertEqual(PIN_PATH, compatibility["golden_source"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["e2e"]["package_sha256"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )
        self.assertEqual(
            f".local-e2e/runs/{SELECTED_RUN}/e2e-record.json",
            compatibility["e2e_run"],
        )
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            f".local-e2e/runs/{REPRODUCTION_RUN}/e2e-record.json",
            compatibility["reproduction_run"],
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
            compatibility["reproduction_e2e_content_sha256"],
        )

        caveats = "\n".join(compatibility["caveats"])
        for token in CAVEAT_TOKENS:
            self.assertIn(token, caveats)
        for active_reference in (
            SEMANTIC_ID,
            PIN_PATH,
            SOURCE_SET_PATH,
            compatibility["e2e_run"],
            compatibility["reproduction_run"],
            caveats,
        ):
            self.assertNotIn("tranche", active_reference.casefold())

        self.assertEqual(set(TARGETS), set(compatibility["targets"]))
        self.assertEqual(set(TARGETS), set(selection["targets"]))
        for architecture, expected in TARGETS.items():
            with self.subTest(architecture=architecture):
                target = compatibility["targets"][architecture]
                selected_target = selection["targets"][architecture]
                golden_record = selected_target["golden_record"]
                artifact = golden_record["artifact"]

                self.assertEqual(CORE_ID, golden_record["core_id"])
                self.assertEqual(architecture, golden_record["architecture"])
                self.assertEqual(SOURCE_RECORD_IDENTITY, golden_record["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual(
                    "needs-target-runtime", target["runtime_validation"]
                )
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(
                    expected["artifact_sha256"], target["artifact_sha256"]
                )
                self.assertEqual(
                    expected["artifact_sha256"],
                    selected_target["artifact"]["sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], artifact["sha256"])
                self.assertEqual(expected["artifact_size"], artifact["size"])
                self.assertEqual([], golden_record["build"]["compile_definitions"])
                self.assertEqual(
                    {
                        "compiler_scope": "c",
                        "derivation": (
                            lowresnx.LOWRESNX_NATIVE_GIT_VERSION_DERIVATION
                        ),
                        "value": lowresnx.LOWRESNX_NATIVE_GIT_VERSION,
                    },
                    golden_record["build"]["git_version"],
                )
                self.assertEqual(
                    METADATA_SHA256, golden_record["metadata"]["sha256"]
                )
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(expected["needed"], artifact["needed"])
                self.assertEqual(
                    expected["version_requirements"],
                    target["version_requirements"],
                )
                self.assertEqual(
                    expected["version_requirements"],
                    artifact["version_requirements"],
                )

                snapshot_reference = golden_record["local_store"][
                    "recipe_snapshots"
                ][architecture]
                snapshot_path = ROOT / snapshot_reference["path"]
                snapshot = load_document(snapshot_path)
                self.assertEqual(9, snapshot["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        golden_record,
                        f"{CORE_ID}/{architecture}",
                    ),
                )

    def test_source_set_release_and_channels_are_core_owned(self) -> None:
        source_set = load_document(ROOT / SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests/core-builds.json")["cores"]
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
        source_lock = load_document(ROOT / source["path"])
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
                    ROOT / ".local-e2e/channels" / f"{channel}.{CORE_ID}.json"
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
                self.assertNotIn(
                    "tranche", pointer["target"]["path"].casefold()
                )

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
        release_root = ROOT / ".local-e2e/releases" / SEMANTIC_ID
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
        self.assertEqual(
            [CORE_ID], [asset["core_id"] for asset in release["assets"]]
        )
        self.assertEqual(PACKAGE_SHA256, release["assets"][0]["sha256"])

    def test_selected_and_local_runs_reproduce_exact_bytes(self) -> None:
        contract = lowresnx.lowresnx_c_only_contract()
        registered_contract = pipeline.core_log_contract_for(CORE_ID)
        self.assertIsNotNone(registered_contract)
        assert registered_contract is not None
        self.assertEqual("lowresnx-c-only-v1", registered_contract.contract_id)
        self.assertEqual(
            "lowresnx_log_proves_contract", registered_contract.proof_name
        )
        self.assertEqual(43, contract.expected_compile_count)
        self.assertEqual(
            lowresnx.LOWRESNX_EXPECTED_COMPILE_PAIR_SHA256,
            contract.expected_compile_pair_sha256,
        )
        self.assertEqual(
            lowresnx.LOWRESNX_EXPECTED_COMPILE_INVOCATION_SHA256,
            dict(contract.expected_compile_invocation_sha256),
        )
        self.assertEqual(
            lowresnx.LOWRESNX_EXPECTED_LINK_OBJECT_SHA256,
            contract.expected_link_object_sha256,
        )
        self.assertEqual(
            lowresnx.LOWRESNX_EXPECTED_LINK_OPTIONS,
            contract.expected_link_options,
        )
        self.assertEqual(
            lowresnx.LOWRESNX_EXPECTED_RAW_LINK_OBJECT_SHA256,
            contract.expected_raw_link_object_sha256,
        )

        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        logs: dict[str, list[bytes]] = {
            architecture: [] for architecture in TARGETS
        }
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                self.assertNotIn("tranche", run_id.casefold())
                run_root = ROOT / ".local-e2e/runs" / run_id
                e2e_path = run_root / "e2e-record.json"
                evidence = load_document(e2e_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(e2e_path))
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    SELECTED_E2E_CONTENT_SHA256
                    if run_id == SELECTED_RUN
                    else REPRODUCTION_E2E_CONTENT_SHA256,
                    evidence["content_sha256"],
                )
                self.assertEqual(
                    [CORE_ID],
                    [item["core_id"] for item in evidence["packages"]],
                )
                package = evidence["packages"][0]
                self.assertEqual("packaged", package["result"])
                self.assertEqual(119288, package["size"])
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                package_path = run_root / package["path"]
                self.assertEqual(PACKAGE_SHA256, file_sha256(package_path))
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/lowresnx_libretro.so",
                            "cores/lowresnx_libretro.so",
                            "lowresnx_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )

                builds = {
                    build["architecture"]: build for build in evidence["builds"]
                }
                self.assertEqual(set(TARGETS), set(builds))
                for architecture, expected in TARGETS.items():
                    with self.subTest(run_id=run_id, architecture=architecture):
                        build = builds[architecture]
                        self.assertEqual(CORE_ID, build["core_id"])
                        self.assertEqual("passed", build["result"])
                        self.assertEqual(
                            expected["record_sha256"][run_id],
                            build["record_sha256"],
                        )
                        record_path = ROOT / build["record"]
                        self.assertEqual(
                            build["record_sha256"], file_sha256(record_path)
                        )
                        record = load_document(record_path)
                        self.assertEqual(CORE_ID, record["core_id"])
                        self.assertEqual(architecture, record["architecture"])
                        self.assertEqual(SOURCE_RECORD_IDENTITY, record["source"])
                        self.assertEqual(
                            "libretro-super", record["build"]["driver"]
                        )
                        self.assertEqual(
                            "sanitized-v1", record["build"]["environment"]
                        )
                        self.assertEqual(
                            [], record["build"]["compile_definitions"]
                        )
                        self.assertEqual(
                            {
                                "compiler_scope": "c",
                                "derivation": (
                                    lowresnx.LOWRESNX_NATIVE_GIT_VERSION_DERIVATION
                                ),
                                "value": lowresnx.LOWRESNX_NATIVE_GIT_VERSION,
                            },
                            record["build"]["git_version"],
                        )

                        log_path = record_path.parent / record["build"]["log"]
                        log_bytes = log_path.read_bytes()
                        log_text = log_bytes.decode("utf-8")
                        self.assertEqual(
                            expected["log_sha256"], file_sha256(log_path)
                        )
                        self.assertEqual(
                            expected["log_sha256"],
                            record["build"]["log_sha256"],
                        )
                        logs[architecture].append(log_bytes)
                        self.assertEqual(
                            43,
                            log_text.count(r'-DGIT_VERSION=\"" 35adc1a"\"'),
                        )
                        self.assertEqual(43, log_text.count("-DGIT_VERSION="))
                        self.assertTrue(
                            pipeline.registered_core_log_contract_proves(
                                log_text,
                                CORE_ID,
                                architecture,
                                SOURCE_COMMIT,
                                SOURCE_TREE,
                            )
                        )

                        metadata_path = (
                            record_path.parent / record["metadata"]["path"]
                        )
                        self.assertEqual(
                            METADATA_SHA256, file_sha256(metadata_path)
                        )
                        metadata = metadata_path.read_bytes()
                        self.assertIn(b'license = "zlib"', metadata)
                        self.assertIn(b'hw_render = "false"', metadata)
                        self.assertIn(b'savestate = "false"', metadata)
                        self.assertIn(b'needs_fullpath = "false"', metadata)
                        metadata_payloads.append(metadata)

                        artifact_path = (
                            record_path.parent / record["artifact"]["path"]
                        )
                        self.assertEqual(
                            expected["artifact_sha256"],
                            file_sha256(artifact_path),
                        )
                        self.assertEqual(
                            expected["needed"], record["artifact"]["needed"]
                        )
                        self.assertEqual(
                            expected["version_requirements"],
                            record["artifact"]["version_requirements"],
                        )
                        artifacts[architecture].append(artifact_path.read_bytes())

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(
                payload == metadata_payloads[0]
                for payload in metadata_payloads[1:]
            )
        )
        for architecture in TARGETS:
            with self.subTest(byte_reproduction=architecture):
                self.assertEqual(
                    artifacts[architecture][0], artifacts[architecture][1]
                )
                self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_compatibility_and_registered_proof_fail_closed(self) -> None:
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
            same_run,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", same_run_report["status"])
        self.assertIn(
            "core compatibility reproduction_run must be independent",
            same_run_report["errors"],
        )

        changed_artifact = copy.deepcopy(compatibility)
        changed_artifact["targets"]["arm64"]["artifact_sha256"] = "0" * 64
        changed_artifact["content_sha256"] = (
            pipeline.core_compatibility_content_sha256(changed_artifact)
        )
        changed_report = pipeline.validate_core_compatibility_document(
            changed_artifact,
            document_path=compatibility_path,
            repository_root=ROOT,
        )
        self.assertEqual("invalid", changed_report["status"])
        self.assertTrue(
            any(
                "artifact differs from compatibility" in error
                for error in changed_report["errors"]
            )
        )

        log_path = (
            ROOT
            / ".local-e2e/runs"
            / REPRODUCTION_RUN
            / CORE_ID
            / "arm64/build.log"
        )
        log_text = log_path.read_text(encoding="utf-8")
        proof_mutations = {
            "native_version": log_text.replace(
                r'-DGIT_VERSION=\"" 35adc1a"\"',
                r'-DGIT_VERSION=\"" 0000000"\"',
                1,
            ),
            "link": log_text.replace(
                "-Wl,-no-undefined", "-Wl,--allow-shlib-undefined", 1
            ),
        }
        for label, mutated_log in proof_mutations.items():
            with self.subTest(proof_mutation=label):
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(
                        mutated_log,
                        CORE_ID,
                        "arm64",
                        SOURCE_COMMIT,
                        SOURCE_TREE,
                    )
                )

    def test_catalog_coverage_uses_canonical_state_not_pending(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.assertTrue(
            lowresnx.lowresnx_spec_is_well_formed(catalog["cores"][CORE_ID])
        )
        self.assertFalse(
            (ROOT / "manifests/compatibility/pending/lowresnx.json").exists()
        )
        coverage = pipeline.load_catalog_compatibility_coverage(
            catalog=catalog,
            repository_root=ROOT,
        )
        self.assertNotIn(CORE_ID, coverage["pending_compatibility_cores"])
        self.assertEqual(
            len(catalog["cores"]),
            coverage["compatibility_coverage_core_count"]
            + coverage["pending_compatibility_core_count"],
        )


if __name__ == "__main__":
    unittest.main()
