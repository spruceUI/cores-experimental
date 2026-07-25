"""Focused Atari800 catalog and shared-pipeline integration tests."""

from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import atari800
from scripts.core_pipeline_lib.contracts import core_log_contract_for

from .support import ROOT, file_sha256, load_document


CORE_ID = "atari800"
SOURCE_COMMIT = "9d3bcf283502512052e21c6f1453fbdf7aa3122b"
SOURCE_TREE = "b42ab0f0a498f3aa076c62825a9082fb7e5889e8"
SOURCE_URL = "https://github.com/libretro/libretro-atari800.git"
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
        "derivation": "native-space-short7-v1",
        "value": " 9d3bcf2",
        "compiler_scope": "c",
    },
    "metadata_replacement": atari800.ATARI800_METADATA_REPLACEMENT,
    "log": "build.log",
    "log_sha256": "a" * 64,
}


class Atari800CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(
            ROOT / "manifests/core-builds.json"
        )
        self.spec = self.catalog["cores"][CORE_ID]

    def test_catalog_binds_exact_native_source_and_metadata(self) -> None:
        self.assertTrue(atari800.atari800_spec_is_well_formed(self.spec))
        self.assertTrue(
            pipeline.native_git_version_spec_is_well_formed(
                self.spec, CORE_ID
            )
        )
        self.assertEqual(
            atari800.ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY,
            pipeline.NATIVE_GIT_VERSION_SPEC_IDENTITIES[CORE_ID],
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
                "derivation": "native-space-short7-v1",
                "value": " 9d3bcf2",
                "compiler_scope": "c",
            },
            pipeline.validated_git_version(self.spec),
        )
        self.assertEqual(
            atari800.ATARI800_METADATA_REPLACEMENT,
            pipeline.validated_metadata_replacement(self.spec),
        )
        self.assertEqual(
            atari800.ATARI800_FORBIDDEN_NEEDED_PREFIXES,
            pipeline.validated_forbidden_needed_prefixes(self.spec),
        )
        replacement_path = ROOT / atari800.ATARI800_METADATA_REPLACEMENT_PATH
        self.assertEqual(
            atari800.ATARI800_METADATA_REPLACEMENT_SHA256,
            file_sha256(replacement_path),
        )
        replacement_text = replacement_path.read_text(encoding="utf-8")
        self.assertIn('display_version = "7.0.0"', replacement_text)
        self.assertIn('disk_control = "true"', replacement_text)

    def test_shared_build_uses_pinned_makeflags_and_metadata_mount(self) -> None:
        self.assertEqual(
            '" 9d3bcf2"',
            pipeline.command_scoped_native_git_version(self.spec),
        )
        self.assertIn(
            SOURCE_COMMIT,
            pipeline.MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS,
        )
        self.assertEqual(
            [
                "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                '" 9d3bcf2"|command-scoped-makeflags',
                "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
                '-- GIT_VERSION="\\ 9d3bcf2"',
                'CORE_PIPELINE_NATIVE_GIT_VERSION|" 9d3bcf2"|command line',
            ],
            pipeline.git_version_log_markers(self.spec),
        )
        mount_args = pipeline.metadata_replacement_mount_args(self.spec)
        self.assertEqual("-v", mount_args[0])
        self.assertTrue(
            mount_args[1].endswith(
                "/metadata/atari800/source-v1.info:"
                "/metadata-replacements/atari800.info:ro"
            )
        )

        script = pipeline.container_build_script(
            CORE_ID, "arm64", self.spec, self.catalog["resolver"]
        )
        checkout = (
            "git -C libretro-atari800 checkout --detach " + SOURCE_COMMIT
        )
        makeflags = 'export MAKEFLAGS=\'-- GIT_VERSION="\\ 9d3bcf2"\''
        build = "./libretro-build.sh atari800"
        metadata = "/metadata-replacements/atari800.info"
        self.assertIn(checkout, script)
        self.assertIn(makeflags, script)
        self.assertEqual(1, script.count(build))
        self.assertIn(metadata, script)
        self.assertIn(atari800.ATARI800_METADATA_PREIMAGE_SHA256, script)
        self.assertIn(atari800.ATARI800_METADATA_REPLACEMENT_SHA256, script)
        self.assertLess(script.index(checkout), script.index(makeflags))
        self.assertLess(script.index(makeflags), script.index(build))
        self.assertLess(script.index(build), script.index(metadata))

    def test_catalog_and_replacement_tampering_fail_closed(self) -> None:
        mutations = {
            "source-commit": (("source", "commit"), "0" * 40),
            "source-tree": (("source", "tree"), "0" * 40),
            "source-key": (("build", "source_key"), "fceumm"),
            "version": (("build", "git_version", "value"), " 0000000"),
            "scope": (("build", "git_version", "compiler_scope"), "cxx"),
            "metadata-path": (
                ("metadata", "replacement", "path"),
                "metadata/vecx/software-v1.info",
            ),
            "metadata-preimage": (
                ("metadata", "replacement", "preimage_sha256"),
                "0" * 64,
            ),
            "dependency-policy": (
                ("validation", "forbidden_needed_prefixes"),
                ["libz"],
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

        self.assertFalse(
            pipeline.metadata_replacement_contract_is_well_formed(
                {
                    **atari800.ATARI800_METADATA_REPLACEMENT,
                    "replacement_sha256": "0" * 64,
                }
            )
        )

    def test_core_owned_golden_and_log_proofs_are_composition_roots(self) -> None:
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
        self.assertEqual(
            {
                key: value
                for key, value in GOLDEN_BUILD.items()
                if key not in {"log", "log_sha256"}
            },
            pipeline.normalized_build_contract(self.spec, "arm64"),
        )

        with mock.patch.object(
            pipeline, "atari800_spec_is_well_formed", return_value=False
        ) as spec_proof:
            self.assertFalse(
                pipeline.native_git_version_spec_is_well_formed(
                    self.spec, CORE_ID
                )
            )
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validate_catalog(copy.deepcopy(self.catalog))
            self.assertGreaterEqual(spec_proof.call_count, 2)

        contract = core_log_contract_for(CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("atari800-c-only-v1", contract.contract_id)
        self.assertEqual("atari800_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)
        with mock.patch.object(
            pipeline, "atari800_log_proves_contract", return_value=True
        ) as proof:
            self.assertTrue(
                pipeline.registered_core_log_contract_proves(
                    "log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
                )
            )
            proof.assert_called_once_with(
                "log", CORE_ID, "arm64", SOURCE_COMMIT, SOURCE_TREE
            )

    def test_schemas_bind_atari800_and_require_exact_build_goldens(self) -> None:
        catalog_schema = load_document(
            ROOT / "manifests/core-builds.schema.json"
        )
        self.assertNotIn(
            "atari800",
            catalog_schema["properties"]["cores"].get(
                "properties", {}
            ),
        )
        golden_schema = load_document(
            ROOT / "manifests/golden-start.schema.json"
        )
        build_golden = golden_schema["$defs"]["buildGolden"]
        required_build_cores = build_golden["allOf"][0]["if"]["properties"][
            "core_id"
        ]["enum"]
        self.assertIn(CORE_ID, required_build_cores)
        exact_branch = next(
            branch
            for branch in build_golden["dependentSchemas"]["build"]["then"][
                "oneOf"
            ]
            if branch["properties"]["core_id"].get("const") == CORE_ID
        )
        self.assertEqual(
            ["core_id", "source", "build"], exact_branch["required"]
        )
        self.assertIn(
            "metadata_replacement",
            exact_branch["properties"]["build"]["required"],
        )
        core_golden_schema = load_document(
            ROOT / "manifests/core-golden.schema.json"
        )
        wrappers = core_golden_schema["properties"]["build_goldens"][
            "additionalProperties"
        ]["additionalProperties"]["allOf"]
        wrapper = next(
            branch
            for branch in wrappers[1:]
            if branch["if"]["properties"]["core_id"].get("const") == CORE_ID
        )
        self.assertEqual(["build"], wrapper["then"]["required"])

    def test_workflow_is_read_only_and_dependency_policy_rejects_drift(
        self,
    ) -> None:
        workflow = (
            ROOT / ".github/workflows/build-atari800.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("contents: read", workflow)
        self.assertEqual(1, workflow.count("scripts/core_pipeline.py e2e"))
        self.assertEqual(1, workflow.count("--runner-profile github-actions"))
        self.assertEqual(1, workflow.count("--core atari800"))
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("gh release upload", workflow)
        self.assertNotIn("core_ref", workflow)
        self.assertNotIn('|| echo "::warning::', workflow)

        valid = pipeline.apply_artifact_dependency_policy(
            {"status": "valid", "needed": ["libc.so.6", "libm.so.6"]},
            self.spec,
        )
        self.assertEqual("valid", valid["status"])
        invalid = pipeline.apply_artifact_dependency_policy(
            {
                "status": "valid",
                "needed": ["libc.so.6", "libm.so.6", "libz.so.1"],
            },
            self.spec,
        )
        self.assertEqual("invalid", invalid["status"])
        self.assertIn("libz.so.1", invalid["errors"][0])


if __name__ == "__main__":
    unittest.main()
