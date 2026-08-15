from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from jsonschema import Draft202012Validator

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.spruce_branch_bases import (
    SPRUCE_BRANCH_BASES_MODEL,
    SPRUCE_BRANCH_BASES_PROVENANCE_MODEL,
    SPRUCE_BRANCH_SPECS,
    SPRUCE_CORE_TREES,
    load_spruce_branch_basis_index,
    spruce_branch_basis_catalog_cell_index,
    spruce_branch_basis_content_sha256,
    spruce_branch_bases_content_sha256,
    spruce_branch_bases_errors,
    validate_spruce_branch_bases,
)


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class SpruceBranchBasisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = _load(ROOT / "manifests/spruce-core-branch-bases.json")
        cls.schema = _load(
            ROOT / "manifests/spruce-core-branch-bases.schema.json"
        )
        cls.catalog = _load(ROOT / "manifests/core-builds.json")
        cls.roster = _load(ROOT / "manifests/spruce-release-roster.json")
        cls.catalog_file_sha256 = hashlib.sha256(
            (ROOT / "manifests/core-builds.json").read_bytes()
        ).hexdigest()
        cls.roster_file_sha256 = hashlib.sha256(
            (ROOT / "manifests/spruce-release-roster.json").read_bytes()
        ).hexdigest()

    def test_live_registry_passes_schema_and_semantic_validation(self) -> None:
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.document)
        self.assertEqual(
            [],
            spruce_branch_bases_errors(
                self.document,
                catalog=self.catalog,
                catalog_file_sha256=self.catalog_file_sha256,
                roster=self.roster,
                roster_file_sha256=self.roster_file_sha256,
            ),
        )
        validate_spruce_branch_bases(
            self.document,
            catalog=self.catalog,
            catalog_file_sha256=self.catalog_file_sha256,
            release_roster=self.roster,
            roster_file_sha256=self.roster_file_sha256,
        )
        self.assertEqual(
            self.document["content_sha256"],
            spruce_branch_bases_content_sha256(self.document),
        )

    def test_registry_is_explicitly_artifact_only(self) -> None:
        self.assertEqual(SPRUCE_BRANCH_BASES_MODEL, self.document["basis_model"])
        self.assertEqual(
            SPRUCE_BRANCH_BASES_PROVENANCE_MODEL,
            self.document["provenance_model"],
        )
        expected = {
            "kind": "artifact-only",
            "source_commits": "not-established",
            "submodule_commits": "not-established",
            "build_recipes": "not-established",
            "toolchains": "not-established",
            "reproducible_builds": "not-established",
        }
        for basis in self.document["bases"].values():
            self.assertEqual(expected, basis["provenance"])
            self.assertNotIn("source", basis)
            self.assertNotIn("recipe", basis)
            self.assertNotIn("toolchain", basis)

    def test_exact_reviewed_branches_and_shared_core_trees_are_bound(self) -> None:
        bases = load_spruce_branch_basis_index(self.document)
        self.assertEqual(set(SPRUCE_BRANCH_SPECS), set(bases))
        for basis_id, spec in SPRUCE_BRANCH_SPECS.items():
            basis = bases[basis_id]
            self.assertEqual(basis_id, basis["basis_id"])
            self.assertEqual(spec["track"], basis["track"])
            self.assertEqual(spec["ref"], basis["branch"]["ref"])
            self.assertEqual(spec["commit"], basis["branch"]["commit"])
            self.assertEqual(spec["tree"], basis["branch"]["tree"])
            self.assertEqual(SPRUCE_CORE_TREES, basis["core_trees"])
            self.assertEqual(
                basis["content_sha256"],
                spruce_branch_basis_content_sha256(basis),
            )
        cross = self.document["cross_branch_core_identity"]
        self.assertTrue(cross["core_trees_identical"])
        self.assertTrue(cross["artifact_bytes_identical"])
        self.assertEqual(SPRUCE_CORE_TREES, cross["core_trees"])

    def test_every_physical_so_and_every_catalog_cell_is_accounted_for(self) -> None:
        artifact_sets = []
        for basis in self.document["bases"].values():
            artifacts = basis["artifacts"]
            artifact_sets.append(artifacts)
            self.assertEqual(184, len(artifacts))
            self.assertEqual(184, len({entry["path"] for entry in artifacts}))
            self.assertTrue(all(entry["git"]["object_type"] == "blob" for entry in artifacts))
            self.assertTrue(all(entry["git"]["size"] > 0 for entry in artifacts))
            self.assertTrue(all(len(entry["sha256"]) == 64 for entry in artifacts))
            cells = spruce_branch_basis_catalog_cell_index(basis)
            self.assertEqual(196, len(cells))
            counts = {status: 0 for status in ("valid", "not_shipped", "invalid")}
            for cell in cells.values():
                counts[cell["status"]] += 1
            self.assertEqual(
                {"valid": 174, "not_shipped": 21, "invalid": 1}, counts
            )
            self.assertEqual(98, basis["summary"]["catalog_core_count"])
            self.assertEqual(104, basis["summary"]["shipped_core_name_count"])
            self.assertEqual(2, basis["summary"]["alias_artifact_count"])
            self.assertEqual(7, basis["summary"]["uncataloged_artifact_count"])
        self.assertEqual(artifact_sets[0], artifact_sets[1])

    def test_invalid_swanstation_armhf_is_preserved_not_normalized(self) -> None:
        for basis in self.document["bases"].values():
            cells = spruce_branch_basis_catalog_cell_index(basis)
            invalid = [cell for cell in cells.values() if cell["status"] == "invalid"]
            self.assertEqual(1, len(invalid))
            self.assertEqual("swanstation", invalid[0]["core_id"])
            self.assertEqual("armhf", invalid[0]["architecture"])
            artifact_by_path = {
                artifact["path"]: artifact for artifact in basis["artifacts"]
            }
            artifact = artifact_by_path[invalid[0]["artifact_path"]]
            self.assertEqual("ELF64", artifact["elf"]["class"])
            self.assertEqual("X86-64", artifact["elf"]["machine"])
            self.assertEqual("invalid", artifact["architecture_validation"])

    def test_alias_and_uncataloged_correlations_are_exactly_roster_backed(self) -> None:
        expected_aliases = {
            alias: core_id
            for core_id, aliases in self.roster["alias_core_ids"].items()
            for alias in aliases
        }
        expected_uncataloged = set(self.roster["uncataloged_core_ids"])
        for basis in self.document["bases"].values():
            seen_aliases = {
                artifact["shipped_core_id"]: artifact["catalog_correlation"][
                    "catalog_core_id"
                ]
                for artifact in basis["artifacts"]
                if artifact["catalog_correlation"]["status"] == "catalog_alias"
            }
            seen_uncataloged = {
                artifact["shipped_core_id"]
                for artifact in basis["artifacts"]
                if artifact["catalog_correlation"]["status"] == "uncataloged"
            }
            self.assertEqual(expected_aliases, seen_aliases)
            self.assertEqual(expected_uncataloged, seen_uncataloged)

    def test_deep_identity_and_provenance_mutations_fail_closed(self) -> None:
        changed = copy.deepcopy(self.document)
        basis = changed["bases"]["spruce-main"]
        basis["artifacts"][0]["sha256"] = "0" * 64
        self.assertNotEqual(
            basis["content_sha256"], spruce_branch_basis_content_sha256(basis)
        )
        errors = spruce_branch_bases_errors(
            changed,
            catalog=self.catalog,
            catalog_file_sha256=self.catalog_file_sha256,
            roster=self.roster,
            roster_file_sha256=self.roster_file_sha256,
        )
        self.assertTrue(any("content_sha256 is stale" in error for error in errors))
        self.assertTrue(any("catalog cell" in error for error in errors))

        claimed = copy.deepcopy(self.document)
        claimed["bases"]["spruce-main"]["provenance"]["source_commits"] = (
            "established"
        )
        with self.assertRaises(PipelineError):
            validate_spruce_branch_bases(
                claimed,
                catalog=self.catalog,
                catalog_file_sha256=self.catalog_file_sha256,
                roster=self.roster,
                roster_file_sha256=self.roster_file_sha256,
            )

    def test_catalog_drift_and_duplicate_cells_fail_closed(self) -> None:
        catalog = copy.deepcopy(self.catalog)
        catalog["cores"].pop("2048")
        errors = spruce_branch_bases_errors(
            self.document,
            catalog=catalog,
            catalog_file_sha256=self.catalog_file_sha256,
            roster=self.roster,
            roster_file_sha256=self.roster_file_sha256,
        )
        self.assertTrue(any("catalog semantic identity is stale" in error for error in errors))
        self.assertTrue(any("cataloged ids do not match" in error for error in errors))

        basis = copy.deepcopy(self.document["bases"]["spruce-main"])
        basis["catalog_cells"].append(copy.deepcopy(basis["catalog_cells"][0]))
        with self.assertRaises(PipelineError):
            spruce_branch_basis_catalog_cell_index(basis)

    def test_catalog_and_roster_raw_file_bindings_fail_closed(self) -> None:
        for field, expected_error in (
            ("catalog", "catalog file identity is stale"),
            ("release_roster", "release roster file identity is stale"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.document)
                changed[field]["file_sha256"] = "0" * 64
                changed["content_sha256"] = spruce_branch_bases_content_sha256(
                    changed
                )
                errors = spruce_branch_bases_errors(
                    changed,
                    catalog=self.catalog,
                    catalog_file_sha256=self.catalog_file_sha256,
                    roster=self.roster,
                    roster_file_sha256=self.roster_file_sha256,
                )
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_generator_reproduces_every_reviewed_git_identity(self) -> None:
        result = subprocess.run(
            [
                "python3",
                "-B",
                "scripts/generate_spruce_branch_bases.py",
                "--check",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        generated = json.loads(result.stdout)
        self.assertEqual(self.document["content_sha256"], generated["content_sha256"])


if __name__ == "__main__":
    unittest.main()
