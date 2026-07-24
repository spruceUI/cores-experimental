"""Focused FreeIntv catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import core_log_contract_for
from scripts.core_pipeline_lib.contracts import freeintv
from tests.test_contract_freeintv import active_log

from .support import ROOT, load_document


CORE_ID = "freeintv"
SOURCE_COMMIT = "428915baf2bfc032fc03e645f4f8f9c6c3144979"
SOURCE_TREE = "ca7bcc22845ae696dd0fa011bd7c2486db7990e4"
SOURCE_URL = "https://github.com/libretro/FreeIntv.git"
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
    "log": "build.log",
    "log_sha256": "a" * 64,
}


class FreeIntvCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog_path = ROOT / "manifests" / "core-builds.json"
        self.catalog = pipeline.load_catalog(self.catalog_path)
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_plain_source_native_identity(self) -> None:
        self.assertTrue(freeintv.freeintv_spec_is_well_formed(self.spec))
        self.assertEqual(
            {"vemulator", CORE_ID}, pipeline.EXACT_SOURCE_NATIVE_CORE_IDS
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
        self.assertNotIn("git_version", self.spec["build"])
        self.assertIsNone(pipeline.validated_git_version(self.spec))
        self.assertEqual([], pipeline.git_version_log_markers(self.spec))
        self.assertEqual("", pipeline.git_version_shell(self.spec))
        self.assertEqual(
            [freeintv.FREEINTV_SOURCE_IDENTITY_MARKER],
            pipeline.source_identity_log_markers(CORE_ID, self.spec),
        )

    def test_source_marker_shell_is_unique_and_precedes_the_plain_build(self) -> None:
        shell = pipeline.source_identity_shell(CORE_ID, self.spec)
        self.assertEqual(1, shell.count("CORE_PIPELINE_SOURCE_IDENTITY|"))
        self.assertIn(freeintv.FREEINTV_SOURCE_IDENTITY_MARKER, shell)

        build_script = pipeline.container_build_script(
            CORE_ID,
            "arm64",
            self.spec,
            self.catalog["resolver"],
        )
        marker = freeintv.FREEINTV_SOURCE_IDENTITY_MARKER
        self.assertEqual(1, build_script.count(marker))
        self.assertLess(
            build_script.index(
                "git -C libretro-freeintv checkout --detach " + SOURCE_COMMIT
            ),
            build_script.index(marker),
        )
        self.assertLess(
            build_script.index(marker),
            build_script.index("rm -f dist/unix/freeintv_libretro.so"),
        )
        build_lines = [
            line.strip()
            for line in build_script.splitlines()
            if line.strip().startswith("./libretro-build.sh")
        ]
        self.assertEqual(["./libretro-build.sh freeintv"], build_lines)
        self.assertNotIn("GIT_VERSION=", build_lines[0])

    def test_catalog_and_marker_dispatch_reject_partial_identity(self) -> None:
        mutations = {
            "source-commit": (("source", "commit"), "0" * 40),
            "source-tree": (("source", "tree"), "0" * 40),
            "source-key": (("build", "source_key"), "potator"),
            "artifact": (
                ("build", "artifact_name"),
                "potator_libretro.so",
            ),
            "injected-version": (
                ("build", "git_version"),
                {
                    "derivation": "native-space-short7-v1",
                    "value": " 428915b",
                    "compiler_scope": "c",
                },
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
            self.assertEqual(
                [],
                pipeline.source_identity_log_markers(CORE_ID, target),
            )
        self.assertEqual(
            [], pipeline.source_identity_log_markers("potator", self.spec)
        )

    def test_schemas_bind_exact_source_and_require_plain_build_golden(
        self,
    ) -> None:
        catalog_schema = load_document(
            ROOT / "manifests" / "core-builds.schema.json"
        )
        self.assertEqual(
            {"$ref": "#/$defs/freeintvCore"},
            catalog_schema["properties"]["cores"]["properties"][CORE_ID],
        )
        exact_core = catalog_schema["$defs"]["freeintvCore"]["allOf"][1][
            "properties"
        ]
        source_schema = exact_core["source"]["properties"]
        self.assertEqual(SOURCE_URL, source_schema["url"]["const"])
        self.assertEqual(SOURCE_COMMIT, source_schema["commit"]["const"])
        self.assertEqual(SOURCE_TREE, source_schema["tree"]["const"])
        build_schema = exact_core["build"]
        self.assertNotIn("git_version", build_schema["required"])
        self.assertNotIn(
            "git_version", build_schema["propertyNames"]["enum"]
        )

        golden_schema = load_document(
            ROOT / "manifests" / "golden-start.schema.json"
        )
        build_golden = golden_schema["$defs"]["buildGolden"]
        trigger_core_ids = build_golden["dependentSchemas"]["build"]["if"][
            "anyOf"
        ][0]["properties"]["core_id"]["enum"]
        self.assertIn(CORE_ID, trigger_core_ids)
        branch = next(
            item
            for item in build_golden["dependentSchemas"]["build"]["then"][
                "oneOf"
            ]
            if item["properties"]["core_id"].get("const") == CORE_ID
        )
        self.assertEqual(
            ["core_id", "source", "build"], branch["required"]
        )
        golden_source = branch["properties"]["source"]["properties"]
        self.assertEqual(SOURCE_URL, golden_source["url"]["const"])
        self.assertEqual(SOURCE_COMMIT, golden_source["commit"]["const"])
        self.assertEqual(SOURCE_TREE, golden_source["tree"]["const"])
        golden_build = branch["properties"]["build"]
        self.assertEqual(
            [
                "driver",
                "environment",
                "compile_definitions",
                "log",
                "log_sha256",
            ],
            golden_build["required"],
        )
        self.assertNotIn(
            "git_version", golden_build["propertyNames"]["enum"]
        )

        core_golden_schema = load_document(
            ROOT / "manifests" / "core-golden.schema.json"
        )
        wrappers = core_golden_schema["properties"]["build_goldens"][
            "additionalProperties"
        ]["additionalProperties"]["allOf"]
        freeintv_wrapper = next(
            item
            for item in wrappers[1:]
            if item["if"]["properties"]["core_id"].get("const") == CORE_ID
        )
        self.assertEqual(["build"], freeintv_wrapper["then"]["required"])

    def test_public_composition_roots_use_core_owned_contracts(self) -> None:
        with mock.patch.object(
            pipeline, "freeintv_spec_is_well_formed", return_value=False
        ) as spec_proof:
            self.assertEqual(
                [], pipeline.source_identity_log_markers(CORE_ID, self.spec)
            )
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_catalog(copy.deepcopy(self.catalog))
            self.assertGreaterEqual(spec_proof.call_count, 2)

        self.assertTrue(
            pipeline.freeintv_golden_source_is_well_formed(
                CORE_ID, SOURCE_RECORD
            )
        )
        self.assertTrue(
            pipeline.freeintv_golden_build_contract_is_well_formed(
                GOLDEN_BUILD,
                SOURCE_COMMIT,
                CORE_ID,
                SOURCE_RECORD,
            )
        )
        with mock.patch.object(
            pipeline,
            "freeintv_golden_build_contract_is_well_formed",
            return_value=False,
        ) as build_proof:
            changed = copy.deepcopy(GOLDEN_BUILD)
            changed["compile_definitions"] = ["SYNTHETIC=1"]
            self.assertFalse(
                pipeline.freeintv_golden_build_contract_is_well_formed(
                    changed, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
                )
            )
            build_proof.assert_called_once_with(
                changed, SOURCE_COMMIT, CORE_ID, SOURCE_RECORD
            )

    def test_recipe_snapshot_binds_exact_golden_without_git_version(self) -> None:
        architecture = "arm64"
        record = {
            "core_id": CORE_ID,
            "architecture": architecture,
            "source": copy.deepcopy(SOURCE_RECORD),
            "recipe": pipeline.recipe_record(
                self.catalog_path, CORE_ID, self.spec
            ),
            "toolchain": {
                **self.catalog["toolchains"][architecture],
                "resolved_image_id": self.catalog["toolchains"][architecture][
                    "image_id"
                ],
                "resolver_digests": self.catalog["resolver"],
                "archive_provenance": pipeline.expected_archive_provenance(
                    self.catalog, architecture
                ),
            },
            "artifact": {"sha256": "b" * 64, "needed": []},
            "metadata": {"status": "valid", "sha256": "c" * 64},
            "build": copy.deepcopy(GOLDEN_BUILD),
        }
        self.assertNotIn("git_version", record["build"])
        self.assertTrue(
            pipeline.freeintv_golden_build_contract_is_well_formed(
                record["build"], SOURCE_COMMIT, CORE_ID, record["source"]
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "freeintv-recipe.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "freeintv/current"
                ),
            )
            original_identity = pipeline.provenance_identity_sha256(record)

            changed = copy.deepcopy(record)
            changed["build"]["compile_definitions"] = ["SYNTHETIC=1"]
            self.assertNotEqual(
                original_identity,
                pipeline.provenance_identity_sha256(changed),
            )
            self.assertFalse(
                pipeline.freeintv_golden_build_contract_is_well_formed(
                    changed["build"],
                    SOURCE_COMMIT,
                    CORE_ID,
                    changed["source"],
                )
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, changed, "freeintv/build-tamper"
                )
            )

            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["source"]["tree"] = "0" * 40
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "freeintv/source-tamper"
                )
            )

    def test_registry_and_historical_bridge_dispatch_core_owned_proofs(
        self,
    ) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("freeintv-c-only-v1", contract.contract_id)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual("freeintv_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)

        with mock.patch.object(
            pipeline, "freeintv_log_proves_contract", return_value=True
        ) as active_proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "active log",
                    CORE_ID,
                    "arm64",
                    SOURCE_COMMIT,
                    SOURCE_TREE,
                )
            )
            active_proof.assert_called_once_with(
                "active log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
            )

        # The golden-start-era historical oracle was retired with the legacy
        # tranche cohort on 2026-07-23; marker-free logs have no fallback.

if __name__ == "__main__":
    unittest.main()
