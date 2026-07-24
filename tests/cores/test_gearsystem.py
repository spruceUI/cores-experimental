"""Focused Gearsystem catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import unittest
import zipfile
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts import profile_registry as registry
from scripts.core_pipeline_lib.contracts import core_log_contract_for
from scripts.core_pipeline_lib.contracts import gearsystem

from .support import (
    ROOT,
    copied_e2e_run,
    file_sha256,
    load_core_documents,
    load_document,
    refresh_copied_e2e,
    write_document,
)


CORE_ID = "gearsystem"
SOURCE_COMMIT = "4f029e43f2d5207c5da78792503b0fff89b7b2c5"
SOURCE_TREE = "8adfb454298c169327d705bebf94e699e5dbf480"
SOURCE_URL = "https://github.com/drhelius/Gearsystem.git"
GIT_DESCRIBE = "3.9.12-5-g4f029e4"
PIN_NAME = "gearsystem-4f029e43f2d5-0f8b301c259a.json"
SEMANTIC_ID = PIN_NAME.removesuffix(".json")
PIN_PATH = f"pins/core-sets/{PIN_NAME}"
SOURCE_SET_PATH = f"pins/source-sets/{PIN_NAME}"
GOLDEN_PATH = f".local-e2e/nightlies/{SEMANTIC_ID}/golden.json"
SOURCE_LOCK_ID = "gearsystem-4f029e43f2d5"
SOURCE_LOCK_PATH = (
    "pins/sources/gearsystem/4f029e43f2d5207c5da78792503b0fff89b7b2c5.json"
)
SOURCE_LOCK_FILE_SHA256 = (
    "ef38461e30fe2b2769247456f8ebb717c5280169a11aa37b07684dfa8319e3fa"
)
SOURCE_LOCK_CONTENT_SHA256 = (
    "c51f145625a63362c4d0f2f13c7d4c17a1332b5ffbfbeeb6e0b483bbf8bd40e1"
)
SOURCE_SET_FILE_SHA256 = (
    "7a6f4e6d602612412a29dc83183b772a274917effd1e19136b0ed561d3fb5f95"
)
SOURCE_SET_CONTENT_SHA256 = (
    "530b657e87b53a8cb4e21705707fbab7c7ea6e033dc2069ad8869a8c1e2a9bc2"
)
PIN_FILE_SHA256 = (
    "19ecf86867b720ed686fc04a2b6c66a023be8d6842badd549de974809d7d30f4"
)
PIN_CONTENT_SHA256 = (
    "3dd4a65dd0aa23c761c5717f184d47722fd74031f3015a3332df64b354677e6a"
)
GOLDEN_FILE_SHA256 = (
    "c199b5ec39e092a5dfb31f49f9e93798bb6a73fa6f6a34943dc400ad80861bb9"
)
GOLDEN_CONTENT_SHA256 = (
    "c9b6282890077f266c176d488579a39243de6c7d54bc1f5ea26d20377c381b01"
)
SELECTION_SHA256 = (
    "0f8b301c259a10d2bfd1975b2f7f10cc589407adef7e1e3826f1d0b673e2de9f"
)
SELECTED_RUN = "actions-sim-build-core-gearsystem-w3"
REPRODUCTION_RUN = "build-core-gearsystem-local-w3"
SELECTED_E2E_CONTENT_SHA256 = (
    "c3c0b532f86bb348e950c4e5f6be1a792dc5678e137a55dc68d1e74f0ef15174"
)
REPRODUCTION_E2E_CONTENT_SHA256 = (
    "2f73799fa424217047d660faa69587ab277fe74c1dd4e3652c20baa09cf1e9ec"
)
E2E_FILE_SHA256 = {
    SELECTED_RUN: (
        "2404ab81deadaa6a4c61a86f3ac700f437a99813f5fe30ddb8e84996330e491b"
    ),
    REPRODUCTION_RUN: (
        "20b19ea9a6e34574592beeace548088c230b7db860d97da615c85cf6ef375f0b"
    ),
}
PACKAGE_SHA256 = (
    "9ccebf7679a70f1125cc64a5908f4526b3f3e99ac47998980944ecb30e90b5d1"
)
PACKAGE_SIZE = 420969
METADATA_SHA256 = (
    "5300f8dd5608747e1244f3c44c4e5b0f7f9ba1bb28911282a2f086f3a49cb4a4"
)
METADATA_SIZE = 1568
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
            "5d9ef0dbfebce0af563dbc54b71cc70296bef708e0dcbbb3a64fa28cd6b28123"
        ),
        "artifact_size": 702584,
        "record_sha256": {
            SELECTED_RUN: (
                "6150b16c20371a405d202252772b9c2d9b9a4242eea7d0e8cddf196f9e41a087"
            ),
            REPRODUCTION_RUN: (
                "3ae751323bd65499fffc6c3710d76b9083112595c7d627ba0effa28a1a7bd59a"
            ),
        },
        "log_sha256": (
            "1eacdb55a5a5b159fa027e07c2d508b29aaea8a92861d3063daef7530d4ddc41"
        ),
        "elf": "ELF64/AArch64",
        "needed": [
            "ld-linux-aarch64.so.1",
            "libc.so.6",
            "libm.so.6",
            "libstdc++.so.6",
        ],
        "version_requirements": [
            "CXXABI_1.3",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.15",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.9",
            "GLIBC_2.17",
            "GLIBC_2.29",
        ],
        "execution_profile_id": "ra64-universal-v1",
    },
    "armhf": {
        "artifact_sha256": (
            "fab48e2180cdec4a54458d9cfde22c719143c3cab686d751590c6bd1d47fd082"
        ),
        "artifact_size": 519824,
        "record_sha256": {
            SELECTED_RUN: (
                "120b13f29def17646618e574015be1219763cf68346b1754bdcd1b6b9728c147"
            ),
            REPRODUCTION_RUN: (
                "bef07e5f14f9986e1951edf00c0396a68e7ef23e40dcaf52ef94aeda7f26af88"
            ),
        },
        "log_sha256": (
            "71d473e6037d74c2f4801888d53b9bf60e3335e29042769da8aac38c089e32e1"
        ),
        "elf": "ELF32/ARM hard-float",
        "needed": ["libc.so.6", "libgcc_s.so.1", "libm.so.6", "libstdc++.so.6"],
        "version_requirements": [
            "CXXABI_1.3",
            "GLIBCXX_3.4",
            "GLIBCXX_3.4.15",
            "GLIBCXX_3.4.20",
            "GLIBCXX_3.4.21",
            "GLIBCXX_3.4.32",
            "GLIBCXX_3.4.9",
            "GLIBC_2.4",
        ],
        "execution_profile_id": "ra32-a30-v1",
    },
}
SOURCE_RECORD = {
    "url": SOURCE_URL,
    "requested_ref": "refs/heads/master",
    "commit": SOURCE_COMMIT,
    "tree": SOURCE_TREE,
    "resolved_commit": SOURCE_COMMIT,
    "resolved_url": SOURCE_URL,
    "submodules": [],
}
GOLDEN_BUILD = {
    "driver": "libretro-super",
    "environment": "sanitized-v1",
    "compile_definitions": [],
    "git_version": {
        "derivation": "native-git-describe-v1",
        "value": GIT_DESCRIBE,
    },
    "log": "build.log",
    "log_sha256": "a" * 64,
}


class GearsystemCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(
            ROOT / "manifests" / "core-builds.json"
        )
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_native_describe_identity(self) -> None:
        identity = gearsystem.GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY
        self.assertTrue(gearsystem.gearsystem_spec_is_well_formed(self.spec))
        self.assertTrue(
            pipeline.native_git_describe_spec_is_well_formed(
                self.spec, CORE_ID
            )
        )
        self.assertEqual(
            identity,
            pipeline.NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES[CORE_ID],
        )
        self.assertEqual(
            {
                "url": SOURCE_URL,
                "requested_ref": "refs/heads/master",
                "commit": SOURCE_COMMIT,
                "tree": SOURCE_TREE,
            },
            self.spec["source"],
        )
        self.assertEqual(
            {
                "derivation": "native-git-describe-v1",
                "value": GIT_DESCRIBE,
            },
            pipeline.validated_git_version(self.spec),
        )
        self.assertEqual(
            {
                "derivation": "native-git-describe-v1",
                "value": GIT_DESCRIBE,
            },
            pipeline.exact_native_git_describe_contract(CORE_ID),
        )
        self.assertEqual(
            ["CORE_PIPELINE_NATIVE_GIT_VERSION|3.9.12-5-g4f029e4|file"],
            pipeline.git_version_log_markers(self.spec),
        )
        shell = pipeline.git_version_shell(self.spec)
        self.assertIn(
            "/libretro-super/libretro-gearsystem/platforms/libretro",
            shell,
        )
        self.assertIn("-f Makefile", shell)

    def test_catalog_rejects_cross_core_and_partial_describe_identities(
        self,
    ) -> None:
        mutations = {
            "gearboy-version": (
                ("build", "git_version", "value"),
                "3.8.9-8-g36d723f",
            ),
            "unreviewed-version": (
                ("build", "git_version", "value"),
                "3.9.12-6-g4f029e4",
            ),
            "wrong-source-tree": (("source", "tree"), "0" * 40),
            "wrong-source-key": (("build", "source_key"), "gearboy"),
            "wrong-makefile-ref": (
                ("source", "requested_ref"),
                "refs/heads/main",
            ),
        }
        for label, (path, value) in mutations.items():
            catalog = copy.deepcopy(self.catalog)
            target = catalog["cores"][CORE_ID]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(mutation=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.validate_catalog(catalog)

    def test_schema_keeps_gear_family_identities_exact_and_disjoint(
        self,
    ) -> None:
        schema = load_document(ROOT / "manifests" / "core-builds.schema.json")
        cores = schema["properties"]["cores"]["properties"]
        self.assertEqual({"$ref": "#/$defs/gearsystemCore"}, cores[CORE_ID])

        version = schema["$defs"]["gearsystemNativeGitDescribeVersion"]
        self.assertEqual(
            {
                "type": "object",
                "required": ["derivation", "value"],
                "properties": {
                    "derivation": {"const": "native-git-describe-v1"},
                    "value": {"const": GIT_DESCRIBE},
                },
                "additionalProperties": False,
            },
            version,
        )
        core_schema = schema["$defs"]["gearsystemCore"]
        self.assertEqual(
            {"$ref": "#/$defs/gearsystemNativeGitDescribeVersion"},
            core_schema["properties"]["build"]["properties"]["git_version"],
        )
        self.assertEqual(
            "3.8.9-8-g36d723f",
            schema["$defs"]["gearboyNativeGitDescribeVersion"][
                "properties"
            ]["value"]["const"],
        )
        self.assertEqual(
            "1.6.6-11-g1123457",
            schema["$defs"]["nativeGitDescribeVersion"]["properties"][
                "value"
            ]["const"],
        )
        generic_refs = {
            branch["$ref"]
            for branch in schema["$defs"]["core"]["properties"]["build"]
            ["properties"]["git_version"]["oneOf"]
        }
        self.assertNotIn(
            "#/$defs/gearsystemNativeGitDescribeVersion", generic_refs
        )

    def test_golden_schema_binds_exact_gearsystem_source_and_version(
        self,
    ) -> None:
        schema = load_document(
            ROOT / "manifests" / "golden-start.schema.json"
        )
        self.assertEqual(
            GIT_DESCRIBE,
            schema["$defs"]["gearsystemNativeGitDescribeVersion"][
                "properties"
            ]["value"]["const"],
        )
        branches = schema["$defs"]["buildGolden"]["dependentSchemas"][
            "build"
        ]["then"]["oneOf"]
        branch = next(
            item
            for item in branches
            if item["properties"]["core_id"].get("const") == CORE_ID
        )
        source = branch["properties"]["source"]["properties"]
        self.assertEqual(SOURCE_URL, source["url"]["const"])
        self.assertEqual(SOURCE_COMMIT, source["commit"]["const"])
        self.assertEqual(SOURCE_TREE, source["tree"]["const"])
        self.assertEqual(
            {"$ref": "#/$defs/gearsystemNativeGitDescribeVersion"},
            branch["properties"]["build"]["properties"]["git_version"],
        )

    def test_copied_gearboy_golden_identity_is_rejected(self) -> None:
        copied_source = copy.deepcopy(SOURCE_RECORD)
        copied_source.update(
            {
                "url": "https://github.com/drhelius/Gearboy.git",
                "commit": "36d723ff44109e6d9eefba34e1c9a089c2d50e18",
                "tree": "d01d828b1e5e7330bcf908b19b1afae8c9f8897b",
                "resolved_commit": (
                    "36d723ff44109e6d9eefba34e1c9a089c2d50e18"
                ),
                "resolved_url": "https://github.com/drhelius/Gearboy.git",
            }
        )
        copied_build = copy.deepcopy(GOLDEN_BUILD)
        copied_build["git_version"]["value"] = "3.8.9-8-g36d723f"
        self.assertFalse(
            pipeline.native_git_describe_golden_source_is_well_formed(
                CORE_ID, copied_source
            )
        )
        self.assertFalse(
            pipeline.git_version_golden_build_contract_is_well_formed(
                copied_build, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
            )
        )

    def test_pipeline_dispatches_core_owned_identity_and_golden_contracts(
        self,
    ) -> None:
        self.assertTrue(
            pipeline.native_git_describe_golden_source_is_well_formed(
                CORE_ID, SOURCE_RECORD
            )
        )
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                GOLDEN_BUILD,
                SOURCE_COMMIT,
                CORE_ID,
                SOURCE_RECORD,
            )
        )

        with mock.patch.object(
            pipeline, "gearsystem_spec_is_well_formed", return_value=True
        ) as spec_proof:
            self.assertTrue(
                pipeline.native_git_describe_spec_is_well_formed({}, CORE_ID)
            )
            spec_proof.assert_called_once_with({})
        with mock.patch.object(
            pipeline,
            "gearsystem_golden_source_is_well_formed",
            return_value=True,
        ) as source_proof:
            self.assertTrue(
                pipeline.native_git_describe_golden_source_is_well_formed(
                    CORE_ID, {}
                )
            )
            source_proof.assert_called_once_with(CORE_ID, {})
        with mock.patch.object(
            pipeline,
            "gearsystem_golden_build_contract_is_well_formed",
            return_value=True,
        ) as build_proof:
            self.assertTrue(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    {}, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
                )
            )
            build_proof.assert_called_once_with(
                {}, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
            )

    def test_registry_and_proof_dispatch_are_singleton_and_core_owned(
        self,
    ) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("gearsystem-mixed-language-v1", contract.contract_id)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual("gearsystem_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)

        with mock.patch.object(
            pipeline, "gearsystem_log_proves_contract", return_value=True
        ) as proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "build log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )
            proof.assert_called_once_with(
                "build log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
            )


class GearsystemLifecycleTests(unittest.TestCase):
    def test_semantic_documents_bind_selected_evidence(self) -> None:
        pin_path, pin, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        pin_report = pipeline.validate_pin_set_document(pin, document_path=pin_path)
        self.assertEqual("valid", pin_report["status"], pin_report["errors"])
        compatibility_report = pipeline.validate_core_compatibility_document(
            compatibility,
            document_path=compatibility_path,
            repository_root=ROOT,
            verify_pin=True,
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
        self.assertEqual(PIN_PATH, compatibility["golden_source"])
        self.assertEqual(SOURCE_COMMIT, compatibility["source_commit"])
        self.assertEqual("reproducible", compatibility["package_state"])
        self.assertEqual(PACKAGE_SHA256, compatibility["package_sha256"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256,
            compatibility["selected_e2e_content_sha256"],
        )
        self.assertEqual(
            REPRODUCTION_E2E_CONTENT_SHA256,
            compatibility["reproduction_e2e_content_sha256"],
        )

        self.assertEqual(1, len(pin["sources"]))
        golden_reference = pin["sources"][0]
        self.assertEqual(GOLDEN_PATH, golden_reference["path"])
        self.assertEqual(SEMANTIC_ID, golden_reference["pin_id"])
        self.assertEqual(GOLDEN_FILE_SHA256, golden_reference["file_sha256"])
        self.assertEqual(
            GOLDEN_CONTENT_SHA256, golden_reference["content_sha256"]
        )
        golden_path = ROOT / GOLDEN_PATH
        golden = load_document(golden_path)
        self.assertEqual(GOLDEN_FILE_SHA256, file_sha256(golden_path))
        self.assertEqual(GOLDEN_CONTENT_SHA256, golden["content_sha256"])

        selection = pin["cores"][CORE_ID]["selection"]
        self.assertEqual(SELECTION_SHA256, selection["selection_sha256"])
        self.assertEqual(PACKAGE_SHA256, selection["package"]["sha256"])
        self.assertEqual(PACKAGE_SIZE, selection["package"]["size"])
        self.assertEqual(METADATA_SHA256, selection["metadata"]["sha256"])
        self.assertEqual(METADATA_SIZE, selection["metadata"]["size"])
        self.assertEqual(SELECTED_RUN, selection["e2e"]["run_id"])
        self.assertEqual(
            SELECTED_E2E_CONTENT_SHA256, selection["e2e"]["content_sha256"]
        )

        caveats = "\n".join(compatibility["caveats"])
        for token in (
            "46-command mixed-language native-describe compile",
            "two C and 44 C++ compile commands",
            GIT_DESCRIBE,
            "no warnings, notes, errors, or fatal diagnostics",
            "GPLv3",
            "display version 3.2.0",
            "bios.sms and bios.gg",
            "neither firmware file is packaged",
            "GLIBCXX_3.4.32",
            "every device view remains ineligible",
        ):
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
                self.assertEqual(SOURCE_RECORD, golden_record["source"])
                self.assertEqual("local_static_build_golden", target["state"])
                self.assertEqual("static-build-only", target["validation_scope"])
                self.assertEqual("needs-target-runtime", target["runtime_validation"])
                self.assertEqual(
                    expected["record_sha256"][SELECTED_RUN],
                    selected_target["build_record_sha256"],
                )
                self.assertEqual(expected["artifact_sha256"], target["artifact_sha256"])
                self.assertEqual(
                    expected["artifact_sha256"], golden_record["artifact"]["sha256"]
                )
                self.assertEqual(
                    expected["artifact_size"], golden_record["artifact"]["size"]
                )
                self.assertEqual(expected["elf"], target["elf"])
                self.assertEqual(expected["needed"], target["needed"])
                self.assertEqual(
                    expected["version_requirements"], target["version_requirements"]
                )
                self.assertEqual(
                    {
                        "derivation": "native-git-describe-v1",
                        "value": GIT_DESCRIBE,
                    },
                    golden_record["build"]["git_version"],
                )
                snapshot_reference = golden_record["local_store"][
                    "recipe_snapshots"
                ][architecture]
                snapshot_path = ROOT / snapshot_reference["path"]
                self.assertEqual(9, load_document(snapshot_path)["schema_version"])
                self.assertEqual(
                    [],
                    pipeline.verify_recipe_snapshot(
                        snapshot_path,
                        golden_record,
                        f"{CORE_ID}/{architecture}",
                    ),
                )

    def test_source_set_maps_profiles_without_device_claims(self) -> None:
        source_set_path = ROOT / SOURCE_SET_PATH
        source_set = load_document(source_set_path)
        registry.validate_source_set(source_set)
        report = registry.report_data(source_set_path=SOURCE_SET_PATH)
        catalog_core_count = len(
            load_document(ROOT / "manifests/core-builds.json")["cores"]
        )

        self.assertEqual(SOURCE_SET_FILE_SHA256, file_sha256(source_set_path))
        self.assertEqual(SEMANTIC_ID, source_set["source_set_id"])
        self.assertEqual(SOURCE_SET_CONTENT_SHA256, source_set["content_sha256"])
        self.assertTrue(source_set["local_only"])
        self.assertEqual("disabled", source_set["publication"])
        self.assertEqual(PIN_PATH, source_set["evidence_pin"]["path"])
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
        self.assertEqual(
            {
                "source_locks": 1,
                "execution_profiles": 5,
                "runtime_contracts": 8,
                "devices": 16,
                "build_evidence_cells": 2,
            },
            report["counts"],
        )
        self.assertEqual(
            {
                "catalog_cores": catalog_core_count,
                "catalog_unlocked_cores": catalog_core_count - 1,
                "evidence_cells": 2,
                "locked_cores": 1,
            },
            report["mirror"],
        )
        cells = {
            cell["architecture"]: cell for cell in report["build_evidence_cells"]
        }
        for architecture, expected in TARGETS.items():
            self.assertEqual(
                expected["artifact_sha256"], cells[architecture]["artifact_sha256"]
            )
            self.assertEqual(
                expected["execution_profile_id"],
                cells[architecture]["execution_profile_id"],
            )
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                and view["eligibility"] == "provisional-unverified"
                for view in report["device_views"]
            )
        )

    def test_selected_and_reproduction_runs_are_byte_identical(self) -> None:
        packages: list[bytes] = []
        metadata_payloads: list[bytes] = []
        artifacts = {architecture: [] for architecture in TARGETS}
        logs = {architecture: [] for architecture in TARGETS}
        for run_id, expected_runner in RUNNERS.items():
            with self.subTest(run_id=run_id):
                run_root = ROOT / ".local-e2e/runs" / run_id
                evidence_path = run_root / "e2e-record.json"
                evidence = load_document(evidence_path)
                self.assertEqual(E2E_FILE_SHA256[run_id], file_sha256(evidence_path))
                self.assertEqual("passed", evidence["result"])
                self.assertEqual(expected_runner, evidence["runner"])
                self.assertEqual(
                    SELECTED_E2E_CONTENT_SHA256
                    if run_id == SELECTED_RUN
                    else REPRODUCTION_E2E_CONTENT_SHA256,
                    evidence["content_sha256"],
                )
                package = evidence["packages"][0]
                self.assertEqual(CORE_ID, package["core_id"])
                self.assertEqual("packaged", package["result"])
                self.assertEqual(PACKAGE_SHA256, package["sha256"])
                self.assertEqual(PACKAGE_SIZE, package["size"])
                package_path = run_root / package["path"]
                packages.append(package_path.read_bytes())
                with zipfile.ZipFile(package_path) as archive:
                    self.assertEqual(
                        {
                            "cores64/gearsystem_libretro.so",
                            "cores/gearsystem_libretro.so",
                            "gearsystem_libretro.info",
                            "manifest.json",
                        },
                        set(archive.namelist()),
                    )

                builds = {
                    build["architecture"]: build for build in evidence["builds"]
                }
                self.assertEqual(set(TARGETS), set(builds))
                for architecture, expected in TARGETS.items():
                    build = builds[architecture]
                    self.assertEqual(
                        expected["record_sha256"][run_id], build["record_sha256"]
                    )
                    record_path = ROOT / build["record"]
                    self.assertEqual(build["record_sha256"], file_sha256(record_path))
                    record = load_document(record_path)
                    self.assertEqual(SOURCE_RECORD, record["source"])
                    self.assertEqual(
                        {"derivation": "native-git-describe-v1", "value": GIT_DESCRIBE},
                        record["build"]["git_version"],
                    )
                    log_path = record_path.parent / record["build"]["log"]
                    log_text = log_path.read_text(encoding="utf-8")
                    self.assertEqual(expected["log_sha256"], file_sha256(log_path))
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
                        gearsystem.GEARSYSTEM_EXPECTED_COMPILE_COUNT,
                        log_text.count(
                            r'-DEMULATOR_BUILD=\"3.9.12-5-g4f029e4\"'
                        ),
                    )
                    logs[architecture].append(log_path.read_bytes())

                    metadata_path = record_path.parent / record["metadata"]["path"]
                    self.assertEqual(METADATA_SHA256, file_sha256(metadata_path))
                    self.assertEqual(METADATA_SIZE, record["metadata"]["size"])
                    metadata_payloads.append(metadata_path.read_bytes())
                    artifact_path = record_path.parent / record["artifact"]["path"]
                    self.assertEqual(
                        expected["artifact_sha256"], file_sha256(artifact_path)
                    )
                    artifact = artifact_path.read_bytes()
                    self.assertIn(GIT_DESCRIBE.encode(), artifact)
                    artifacts[architecture].append(artifact)

        self.assertEqual(packages[0], packages[1])
        self.assertTrue(
            all(payload == metadata_payloads[0] for payload in metadata_payloads[1:])
        )
        for architecture in TARGETS:
            self.assertEqual(artifacts[architecture][0], artifacts[architecture][1])
            self.assertEqual(logs[architecture][0], logs[architecture][1])

    def test_channels_release_and_mutations_fail_closed(self) -> None:
        target_paths = {
            "nightly": GOLDEN_PATH,
            "pinned": PIN_PATH,
            "release": f".local-e2e/releases/{SEMANTIC_ID}/release-manifest.json",
        }
        for channel, target_path in target_paths.items():
            pointer = load_document(
                ROOT / ".local-e2e/channels" / f"{channel}.{CORE_ID}.json"
            )
            report = pipeline.validate_channel_pointer_document(
                pointer, expected_channel=channel, expected_core=CORE_ID
            )
            self.assertEqual("valid", report["status"], report["errors"])
            self.assertEqual(2, pointer["schema_version"])
            self.assertTrue(pointer["local_only"])
            self.assertEqual("disabled", pointer["publication"])
            self.assertEqual(SEMANTIC_ID, pointer["target"]["id"])
            self.assertEqual(target_path, pointer["target"]["path"])

        pin_path = ROOT / PIN_PATH
        pin = load_document(pin_path)
        release_root = ROOT / ".local-e2e/releases" / SEMANTIC_ID
        release_report = pipeline.validate_local_release(
            release_root,
            pin,
            file_sha256(pin_path),
            expected_release_id=SEMANTIC_ID,
        )
        self.assertEqual("valid", release_report["status"], release_report["errors"])

        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        mutations = {
            "digest": copy.deepcopy(compatibility),
            "publication": copy.deepcopy(compatibility),
            "runtime": copy.deepcopy(compatibility),
            "artifact": copy.deepcopy(compatibility),
            "run_identity": copy.deepcopy(compatibility),
        }
        mutations["digest"]["content_sha256"] = "0" * 64
        mutations["publication"]["publication"] = "enabled"
        mutations["runtime"]["targets"]["arm64"]["runtime_validation"] = "passed"
        mutations["artifact"]["targets"]["arm64"]["artifact_sha256"] = "0" * 64
        mutations["run_identity"]["reproduction_run"] = mutations["run_identity"][
            "e2e_run"
        ]
        mutations["run_identity"]["reproduction_e2e_content_sha256"] = mutations[
            "run_identity"
        ]["selected_e2e_content_sha256"]
        for label, mutated in mutations.items():
            if label != "digest":
                mutated["content_sha256"] = (
                    pipeline.core_compatibility_content_sha256(mutated)
                )
            with self.subTest(compatibility_mutation=label):
                report = pipeline.validate_core_compatibility_document(
                    mutated,
                    document_path=compatibility_path,
                    repository_root=ROOT,
                    verify_pin=label not in {"digest", "publication"},
                )
                self.assertEqual("invalid", report["status"], report["errors"])

    def test_reproduction_rejects_recomputed_log_tampering(self) -> None:
        _, _, compatibility_path, compatibility = load_core_documents(
            CORE_ID, PIN_NAME
        )
        with copied_e2e_run(
            REPRODUCTION_RUN,
            prefix="compat-tamper-gearsystem-log-",
            content_hasher=pipeline.e2e_content_sha256,
        ) as (run_root, evidence):
            record_path = run_root / CORE_ID / "arm64" / "build-record.json"
            record = load_document(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_path.write_text(
                log_path.read_text(encoding="utf-8") + "warning: extra\n",
                encoding="utf-8",
            )
            record["build"]["log_sha256"] = file_sha256(log_path)
            write_document(record_path, record)
            refresh_copied_e2e(run_root, evidence, pipeline.e2e_content_sha256)

            mutated = copy.deepcopy(compatibility)
            mutated["reproduction_run"] = (
                f".local-e2e/runs/{run_root.name}/e2e-record.json"
            )
            mutated["reproduction_e2e_content_sha256"] = evidence["content_sha256"]
            mutated["content_sha256"] = (
                pipeline.core_compatibility_content_sha256(mutated)
            )
            report = pipeline.validate_core_compatibility_document(
                mutated,
                document_path=compatibility_path,
                repository_root=ROOT,
            )
            self.assertEqual("invalid", report["status"], report["errors"])

    def test_catalog_coverage_uses_canonical_state(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        coverage = pipeline.load_catalog_compatibility_coverage(
            catalog=catalog,
            repository_root=ROOT,
        )
        self.assertNotIn(CORE_ID, coverage["pending_compatibility_cores"])
        # Derive the expected canonical count from the filesystem so promoting a
        # bridge core never forces an edit here; the coverage tool must agree.
        canonical_manifests = len(
            list((ROOT / "manifests" / "compatibility").glob("*.json"))
        )
        self.assertEqual(
            canonical_manifests, coverage["canonical_compatibility_core_count"]
        )
        self.assertEqual(
            canonical_manifests,
            coverage["compatibility_coverage_core_count"],
        )
        self.assertEqual(
            len(catalog["cores"]),
            coverage["compatibility_coverage_core_count"]
            + coverage["pending_compatibility_core_count"],
        )


if __name__ == "__main__":
    unittest.main()
