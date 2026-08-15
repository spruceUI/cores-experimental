"""Focused mGBA catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from .support import pipeline
from scripts.core_pipeline_lib.contracts import core_log_contract_for
from scripts.core_pipeline_lib.contracts import mgba
from tests.test_contract_mgba import build_mgba_log_fixture

from .support import ROOT, load_document


CORE_ID = "mgba"
SOURCE_COMMIT = "6dce57eef127dc4cc292644f38196e0e7c58590c"
SOURCE_TREE = "72edb48f24f569f2b00c850cac61f6db0c80bf4e"
SOURCE_URL = "https://github.com/libretro/mgba.git"
GIT_VERSION = " 6dce57eef"
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
        "derivation": "native-space-short9-v1",
        "value": GIT_VERSION,
        "compiler_scope": "c",
    },
    "log": "build.log",
    "log_sha256": "a" * 64,
}


class MgbaCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog_path = ROOT / "manifests" / "core-builds.json"
        self.catalog = pipeline.load_catalog(self.catalog_path)
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_short9_native_identity_and_c_scope(
        self,
    ) -> None:
        self.assertTrue(mgba.mgba_spec_is_well_formed(self.spec))
        self.assertTrue(
            pipeline.native_git_version_short9_spec_is_well_formed(
                self.spec, CORE_ID
            )
        )
        self.assertEqual(
            mgba.MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES[CORE_ID],
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
        expected_version = {
            "derivation": "native-space-short9-v1",
            "value": GIT_VERSION,
            "compiler_scope": "c",
        }
        self.assertEqual(expected_version, pipeline.validated_git_version(self.spec))
        self.assertEqual(
            expected_version, pipeline.exact_native_git_version_contract(CORE_ID)
        )
        self.assertIn(CORE_ID, pipeline.NATIVE_GIT_VERSION_C_SCOPE_CORE_IDS)
        self.assertEqual(
            [], pipeline.compile_definitions_for_target(self.spec, "arm64")
        )
        self.assertEqual(
            [], pipeline.compile_definitions_for_target(self.spec, "armhf")
        )
        self.assertEqual(
            [mgba.MGBA_NATIVE_VERSION_MARKER],
            pipeline.git_version_log_markers(self.spec),
        )

    def test_shell_pins_git_abbreviation_without_a_second_marker(self) -> None:
        shell = pipeline.git_version_shell(self.spec)
        self.assertIn("export GIT_CONFIG_SYSTEM=/dev/null", shell)
        self.assertIn("export GIT_CONFIG_GLOBAL=/dev/null", shell)
        self.assertIn("GIT_CONFIG_PARAMETERS=\"'core.abbrev=9'\"", shell)
        self.assertIn("git config --show-origin --get core.abbrev", shell)
        self.assertIn("printf 'command line:\\t9'", shell)
        self.assertNotIn("CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV", shell)
        self.assertEqual(1, shell.count("CORE_PIPELINE_NATIVE_GIT_VERSION|"))

        build_script = pipeline.container_build_script(
            CORE_ID,
            "arm64",
            self.spec,
            self.catalog["resolver"],
        )
        self.assertEqual(
            1, build_script.count("CORE_PIPELINE_NATIVE_GIT_VERSION|")
        )
        build_lines = [
            line.strip()
            for line in build_script.splitlines()
            if line.strip().startswith("./libretro-build.sh")
        ]
        self.assertEqual(["./libretro-build.sh mgba"], build_lines)
        self.assertNotIn("GIT_VERSION=", build_lines[0])

    def test_catalog_rejects_partial_cross_core_and_short7_identities(
        self,
    ) -> None:
        mutations = {
            "source-commit": (("source", "commit"), "0" * 40),
            "source-tree": (("source", "tree"), "0" * 40),
            "source-key": (("build", "source_key"), "uzem"),
            "short7-derivation": (
                ("build", "git_version", "derivation"),
                "native-space-short7-v1",
            ),
            "version": (("build", "git_version", "value"), " 6dce57ee0"),
            "compiler-scope": (
                ("build", "git_version", "compiler_scope"),
                "cxx",
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

        copied = copy.deepcopy(self.spec["build"]["git_version"])
        self.assertFalse(
            pipeline.git_version_contract_is_well_formed(copied, "0" * 40)
        )

    def test_pipeline_dispatches_core_owned_spec_and_golden_contracts(
        self,
    ) -> None:
        self.assertTrue(
            pipeline.native_git_version_golden_source_is_well_formed(
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
            pipeline, "mgba_spec_is_well_formed", return_value=True
        ) as spec_proof:
            self.assertTrue(
                pipeline.native_git_version_short9_spec_is_well_formed(
                    {}, CORE_ID
                )
            )
            spec_proof.assert_called_once_with({})
        with mock.patch.object(
            pipeline,
            "mgba_golden_source_is_well_formed",
            return_value=True,
        ) as source_proof:
            self.assertTrue(
                pipeline.native_git_version_golden_source_is_well_formed(
                    CORE_ID, {}
                )
            )
            source_proof.assert_called_once_with(CORE_ID, {})
        with mock.patch.object(
            pipeline,
            "mgba_golden_build_contract_is_well_formed",
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

    def test_schemas_bind_mgba_to_exact_source_version_and_scope(self) -> None:
        catalog_schema = load_document(
            ROOT / "manifests" / "core-builds.schema.json"
        )
        self.assertNotIn(
            "mgba",
            catalog_schema["properties"]["cores"].get(
                "properties", {}
            ),
        )
        version_schema = catalog_schema["$defs"]["mgbaNativeGitVersion"]
        self.assertEqual(
            ["derivation", "value", "compiler_scope"],
            version_schema["required"],
        )
        self.assertEqual(
            "native-space-short9-v1",
            version_schema["properties"]["derivation"]["const"],
        )
        self.assertEqual(
            GIT_VERSION, version_schema["properties"]["value"]["const"]
        )
        self.assertEqual(
            "c", version_schema["properties"]["compiler_scope"]["const"]
        )
        golden_schema = load_document(
            ROOT / "manifests" / "golden-start.schema.json"
        )
        self.assertEqual(
            version_schema, golden_schema["$defs"]["mgbaNativeGitVersion"]
        )
        branches = golden_schema["$defs"]["buildGolden"][
            "dependentSchemas"
        ]["build"]["then"]["oneOf"]
        branch = next(
            item
            for item in branches
            if item["properties"]["core_id"].get("const") == CORE_ID
        )
        source_schema = branch["properties"]["source"]["properties"]
        self.assertEqual(SOURCE_URL, source_schema["url"]["const"])
        self.assertEqual(SOURCE_COMMIT, source_schema["commit"]["const"])
        self.assertEqual(SOURCE_TREE, source_schema["tree"]["const"])
        self.assertEqual(
            {"$ref": "#/$defs/mgbaNativeGitVersion"},
            branch["properties"]["build"]["properties"]["git_version"],
        )
        build_golden = golden_schema["$defs"]["buildGolden"]
        trigger_core_ids = build_golden["dependentSchemas"]["build"]["if"][
            "anyOf"
        ][0]["properties"]["core_id"]["enum"]
        required_build_core_ids = build_golden["allOf"][0]["if"][
            "properties"
        ]["core_id"]["enum"]
        self.assertIn(CORE_ID, trigger_core_ids)
        self.assertNotIn(CORE_ID, required_build_core_ids)
        core_golden_schema = load_document(
            ROOT / "manifests" / "core-golden.schema.json"
        )
        target_wrapper = core_golden_schema["properties"]["build_goldens"][
            "additionalProperties"
        ]["additionalProperties"]["allOf"]
        self.assertEqual(
            {"$ref": "golden-start.schema.json#/$defs/buildGolden"},
            target_wrapper[0],
        )
        self.assertEqual(
            {"core_id": {"const": CORE_ID}},
            target_wrapper[1]["if"]["properties"],
        )
        self.assertEqual(["build"], target_wrapper[1]["then"]["required"])

    def test_recipe_snapshot_and_golden_contract_reject_recomputed_tampering(
        self,
    ) -> None:
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
        self.assertTrue(
            pipeline.git_version_golden_build_contract_is_well_formed(
                record["build"], SOURCE_COMMIT, CORE_ID, record["source"]
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            snapshot_path = Path(directory) / "mgba-recipe.json"
            snapshot_path.write_bytes(pipeline.recipe_snapshot(record))
            self.assertEqual(
                [],
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "mgba/current"
                ),
            )
            original_identity = pipeline.provenance_identity_sha256(record)

            changed = copy.deepcopy(record)
            changed["build"]["git_version"]["value"] = " 6dce57ee0"
            self.assertNotEqual(
                original_identity, pipeline.provenance_identity_sha256(changed)
            )
            self.assertFalse(
                pipeline.git_version_golden_build_contract_is_well_formed(
                    changed["build"], SOURCE_COMMIT, CORE_ID, changed["source"]
                )
            )
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, changed, "mgba/version-tamper"
                )
            )

            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            snapshot["source"]["tree"] = "0" * 40
            snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
            self.assertTrue(
                pipeline.verify_recipe_snapshot(
                    snapshot_path, record, "mgba/snapshot-tamper"
                )
            )

    def test_registry_accepts_active_marker_and_rejects_stored_marker_free_log(
        self,
    ) -> None:
        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("mgba-c-only-v1", contract.contract_id)
        self.assertEqual(frozenset({CORE_ID}), contract.core_ids)
        self.assertEqual("mgba_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)

        active_log = build_mgba_log_fixture("arm64")
        stored_log = build_mgba_log_fixture("arm64", native_marker=False)
        self.assertTrue(
            pipeline.registered_core_log_contract_proves(
                active_log,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )
        self.assertFalse(
            pipeline.registered_core_log_contract_proves(
                stored_log,
                CORE_ID,
                "arm64",
                SOURCE_COMMIT,
                SOURCE_TREE,
            )
        )
        # The golden-start-era historical oracle was retired with the legacy
        # tranche cohort on 2026-07-23: a stored marker-free log is now simply
        # rejected by the active proof above, with no fallback.

        with mock.patch.object(
            pipeline, "mgba_log_proves_contract", return_value=True
        ) as proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "build log",
                    CORE_ID,
                    "armhf",
                    SOURCE_COMMIT,
                    SOURCE_TREE,
                )
            )
            proof.assert_called_once_with(
                "build log", CORE_ID, "armhf", SOURCE_COMMIT, SOURCE_TREE
            )


if __name__ == "__main__":
    unittest.main()
