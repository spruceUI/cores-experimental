from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import quicknes
from core_pipeline_lib.contracts import mgba


ROOT = Path(__file__).resolve().parents[1]


class NativeGitVersionContractTests(unittest.TestCase):
    def test_global_schema_compiler_scopes_are_exact_and_in_parity(self) -> None:
        for relative_path in (
            "manifests/core-builds.schema.json",
            "manifests/golden-start.schema.json",
        ):
            schema = json.loads(
                (ROOT / relative_path).read_text(encoding="utf-8")
            )
            with self.subTest(schema=schema["$id"]):
                self.assertEqual(
                    ["c", "cxx"],
                    schema["$defs"]["nativeGitVersion"]["properties"][
                        "compiler_scope"
                    ]["enum"],
                )
                self.assertEqual(
                    "cxx",
                    schema["$defs"]["gitVersion"]["properties"][
                        "compiler_scope"
                    ]["const"],
                )

    def test_c_scope_cannot_be_copied_to_unreviewed_contracts(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        mutations = {}
        for core_id in ("uzem", quicknes.QUICKNES_CORE_ID):
            changed = copy.deepcopy(catalog)
            changed["cores"][core_id]["build"]["git_version"][
                "compiler_scope"
            ] = "c"
            mutations[core_id] = changed

        for core_id, changed in mutations.items():
            with self.subTest(core_id=core_id):
                spec = changed["cores"][core_id]
                if core_id == quicknes.QUICKNES_CORE_ID:
                    self.assertFalse(quicknes.quicknes_spec_is_well_formed(spec))
                else:
                    self.assertFalse(
                        pipeline.native_git_version_spec_is_well_formed(
                            spec, core_id
                        )
                    )
                with self.assertRaises(pipeline.PipelineError):
                    pipeline.validate_catalog(changed)

    def test_short10_contract_cannot_be_copied_to_unreviewed_core(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        changed = copy.deepcopy(catalog)
        source_commit = changed["cores"]["potator"]["source"]["commit"]
        changed["cores"]["potator"]["build"].update(
            {
                "source_date_epoch": 1780486798,
                "git_version": {
                    "derivation": "native-space-short10-v1",
                    "value": f" {source_commit[:10]}",
                },
            }
        )
        spec = changed["cores"]["potator"]
        self.assertTrue(
            pipeline.git_version_contract_is_well_formed(
                spec["build"]["git_version"], source_commit
            )
        )
        self.assertFalse(
            pipeline.native_git_version_short10_spec_is_well_formed(
                spec, "potator"
            )
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)

    def test_short9_contract_is_exact_and_cannot_be_copied(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][mgba.MGBA_CORE_ID]
        contract = spec["build"]["git_version"]
        self.assertEqual(
            {
                "derivation": "native-space-short9-v1",
                "value": " 6dce57eef",
                "compiler_scope": "c",
            },
            contract,
        )
        self.assertTrue(
            pipeline.git_version_contract_is_well_formed(
                contract, spec["source"]["commit"]
            )
        )
        self.assertEqual(
            contract, pipeline.exact_native_git_version_contract("mgba")
        )

        changed = copy.deepcopy(catalog)
        target = changed["cores"]["potator"]
        target["build"]["git_version"] = {
            "derivation": "native-space-short9-v1",
            "value": f" {target['source']['commit'][:9]}",
            "compiler_scope": "c",
        }
        self.assertFalse(
            pipeline.git_version_contract_is_well_formed(
                target["build"]["git_version"], target["source"]["commit"]
            )
        )
        self.assertFalse(
            pipeline.native_git_version_spec_is_well_formed(target, "potator")
        )
        with self.assertRaises(pipeline.PipelineError):
            pipeline.validate_catalog(changed)


if __name__ == "__main__":
    unittest.main()
