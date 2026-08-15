from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from .cores.support import pipeline
from core_pipeline_lib.errors import PipelineError
from core_pipeline_lib.records import compatibility_pending as pending


ROOT = Path(__file__).resolve().parents[1]
PENDING_DIRECTORY = ROOT / "manifests" / "compatibility" / "pending"
LOWRESNX_PENDING_PATH = PENDING_DIRECTORY / "lowresnx.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pending_document(catalog: dict, core_id: str) -> dict:
    spec = catalog["cores"][core_id]
    document = {
        "$schema": pending.SCHEMA_REFERENCE,
        "schema_version": 1,
        "core_id": core_id,
        "state": pending.PENDING_STATE,
        "publication": "disabled",
        "core_spec_sha256": pending.catalog_core_spec_sha256(spec),
        "source_commit": spec["source"]["commit"],
        "targets": sorted(spec["targets"]),
        "next_gate": pending.NEXT_GATE,
        "content_sha256": "",
    }
    document["content_sha256"] = (
        pending.pending_compatibility_content_sha256(document)
    )
    return document


class PendingCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        self.document = pending_document(self.catalog, "lowresnx")

    def test_repository_pending_records_are_exact_and_non_admitting(self) -> None:
        records = pending.load_pending_compatibility_records(
            pending_directory=PENDING_DIRECTORY,
            repository_root=ROOT,
            catalog=self.catalog,
        )
        coverage = pending.load_catalog_compatibility_coverage(
            catalog=self.catalog,
            repository_root=ROOT,
        )
        self.assertEqual(
            len(self.catalog["cores"]), coverage["catalog_core_count"]
        )

        canonical_admissions = {
            path.stem
            for path in (ROOT / "manifests/compatibility").glob("*.json")
        }
        expected_pending = set(self.catalog["cores"]) - canonical_admissions
        self.assertEqual(expected_pending, set(records))
        self.assertEqual(
            sorted(records), coverage["pending_compatibility_cores"]
        )
        self.assertEqual(
            len(records), coverage["pending_compatibility_core_count"]
        )
        self.assertEqual(
            len(canonical_admissions),
            coverage["compatibility_coverage_core_count"],
        )
        self.assertEqual(
            len(canonical_admissions),
            coverage["canonical_compatibility_core_count"],
        )
        self.assertFalse(set(records) & canonical_admissions)
        for core_id, document in records.items():
            with self.subTest(core_id=core_id):
                self.assertEqual(
                    pending_document(self.catalog, core_id), document
                )

    def test_validator_rejects_every_bound_field_mutation(self) -> None:
        mutations = {
            "unknown-field": lambda value: value.update({"extra": True}),
            "schema": lambda value: value.update({"$schema": "elsewhere.json"}),
            "version": lambda value: value.update({"schema_version": 2}),
            "core": lambda value: value.update({"core_id": "other"}),
            "state": lambda value: value.update({"state": "compatible"}),
            "publication": lambda value: value.update({"publication": "enabled"}),
            "core-spec": lambda value: value.update(
                {"core_spec_sha256": "0" * 64}
            ),
            "source": lambda value: value.update({"source_commit": "0" * 40}),
            "targets-order": lambda value: value.update(
                {"targets": ["armhf", "arm64"]}
            ),
            "targets-duplicate": lambda value: value.update(
                {"targets": ["arm64", "arm64"]}
            ),
            "targets-nested-list": lambda value: value.update(
                {"targets": [["arm64"]]}
            ),
            "targets-nested-object": lambda value: value.update(
                {"targets": [{"architecture": "arm64"}]}
            ),
            "next-gate": lambda value: value.update({"next_gate": "release"}),
        }
        for label, mutate in mutations.items():
            changed = copy.deepcopy(self.document)
            mutate(changed)
            changed["content_sha256"] = (
                pending.pending_compatibility_content_sha256(changed)
            )
            with self.subTest(mutation=label):
                report = pending.validate_pending_compatibility_document(
                    changed,
                    document_path=LOWRESNX_PENDING_PATH,
                    repository_root=ROOT,
                    catalog=self.catalog,
                )
                self.assertEqual("invalid", report["status"])
                self.assertTrue(report["errors"])

        changed_digest = copy.deepcopy(self.document)
        changed_digest["content_sha256"] = "0" * 64
        report = pending.validate_pending_compatibility_document(
            changed_digest,
            document_path=LOWRESNX_PENDING_PATH,
            repository_root=ROOT,
            catalog=self.catalog,
        )
        self.assertIn(
            "pending compatibility content digest is invalid",
            report["errors"],
        )

    def test_document_path_must_bind_core_id(self) -> None:
        report = pending.validate_pending_compatibility_document(
            self.document,
            document_path=PENDING_DIRECTORY / "other.json",
            repository_root=ROOT,
            catalog=self.catalog,
        )
        self.assertIn(
            "pending compatibility path does not bind core_id",
            report["errors"],
        )

    def test_pending_and_promoted_coverage_are_disjoint_and_exact(self) -> None:
        catalog = {"one", "two"}
        self.assertEqual(
            [],
            pending.compatibility_coverage_errors(
                catalog_cores=catalog,
                compatibility_coverage_cores={"one"},
                golden_source_cores={"one"},
                pending_cores={"two"},
            ),
        )
        self.assertEqual(
            [],
            pending.compatibility_coverage_errors(
                catalog_cores=catalog,
                compatibility_coverage_cores=catalog,
                golden_source_cores=catalog,
                pending_cores=set(),
            ),
        )
        invalid_cases = (
            ({"one"}, {"one"}, {"one"}),
            ({"one"}, {"one", "two"}, {"two"}),
            ({"one"}, {"one"}, set()),
            ({"one", "three"}, {"one", "three"}, {"two"}),
        )
        for compatibility, goldens, pending_cores in invalid_cases:
            with self.subTest(
                compatibility=compatibility,
                goldens=goldens,
                pending=pending_cores,
            ):
                self.assertTrue(
                    pending.compatibility_coverage_errors(
                        catalog_cores=catalog,
                        compatibility_coverage_cores=compatibility,
                        golden_source_cores=goldens,
                        pending_cores=pending_cores,
                    )
                )

    def test_pending_directory_must_not_be_a_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compatibility = root / "manifests" / "compatibility"
            compatibility.mkdir(parents=True)
            target = root / "pending-target"
            target.mkdir()
            (compatibility / "pending").symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(PipelineError, "must not traverse a symlink"):
                pending.load_pending_compatibility_records(
                    pending_directory=compatibility / "pending",
                    repository_root=root,
                    catalog={"cores": {}},
                )

    def test_coverage_rejects_malformed_canonical_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compatibility = root / "manifests" / "compatibility"
            compatibility.mkdir(parents=True)
            (compatibility / "vecx.json").write_text(
                json.dumps(
                    {
                        "core_id": "vecx",
                        "golden_source": "pins/core-sets/not-evidence.json",
                    }
                ),
                encoding="utf-8",
            )
            catalog = {"cores": {"vecx": self.catalog["cores"]["vecx"]}}
            with self.assertRaisesRegex(
                PipelineError, "invalid canonical compatibility document"
            ):
                pending.load_catalog_compatibility_coverage(
                    catalog=catalog,
                    repository_root=root,
                )

    def test_coverage_rejects_canonical_file_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compatibility = root / "manifests" / "compatibility"
            compatibility.mkdir(parents=True)
            target = root / "vecx-target.json"
            target.write_text(
                (ROOT / "manifests/compatibility/vecx.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            (compatibility / "vecx.json").symlink_to(target)
            catalog = {"cores": {"vecx": self.catalog["cores"]["vecx"]}}
            with self.assertRaisesRegex(
                PipelineError, "must not traverse a symlink"
            ):
                pending.load_catalog_compatibility_coverage(
                    catalog=catalog,
                    repository_root=root,
                )

    def test_coverage_rejects_canonical_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "compatibility-target"
            target.mkdir()
            (target / "vecx.json").write_text(
                (ROOT / "manifests/compatibility/vecx.json").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            manifests = root / "manifests"
            manifests.mkdir()
            (manifests / "compatibility").symlink_to(
                target, target_is_directory=True
            )
            catalog = {"cores": {"vecx": self.catalog["cores"]["vecx"]}}
            with self.assertRaisesRegex(
                PipelineError, "must not traverse a symlink"
            ):
                pending.load_catalog_compatibility_coverage(
                    catalog=catalog,
                    repository_root=root,
                )

    def test_default_catalog_check_reports_pending_coverage(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = pipeline.cmd_catalog_check(
                SimpleNamespace(catalog=pipeline.DEFAULT_CATALOG)
            )
        self.assertEqual(0, result)
        report = json.loads(output.getvalue())
        expected = pending.load_catalog_compatibility_coverage(
            catalog=self.catalog,
            repository_root=ROOT,
        )
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(value, report[key])

    def test_default_catalog_check_propagates_coverage_failure(self) -> None:
        with mock.patch.object(
            pipeline,
            "load_catalog_compatibility_coverage",
            side_effect=PipelineError("coverage failed"),
        ):
            with self.assertRaisesRegex(PipelineError, "coverage failed"):
                pipeline.cmd_catalog_check(
                    SimpleNamespace(catalog=pipeline.DEFAULT_CATALOG)
                )

    def test_custom_catalog_check_remains_shape_only(self) -> None:
        custom_catalog = ROOT / "tests" / "fixtures" / "custom-catalog.json"
        output = io.StringIO()
        with mock.patch.object(
            pipeline, "load_catalog", return_value=self.catalog
        ), mock.patch.object(
            pipeline, "load_catalog_compatibility_coverage"
        ) as coverage_loader, redirect_stdout(output):
            result = pipeline.cmd_catalog_check(
                SimpleNamespace(catalog=custom_catalog)
            )
        self.assertEqual(0, result)
        coverage_loader.assert_not_called()
        self.assertEqual(
            {
                "catalog_cores": sorted(self.catalog["cores"]),
                "publication": self.catalog["policy"]["publication"],
                "status": "valid",
            },
            json.loads(output.getvalue()),
        )

    def test_schema_is_exact_and_pending_only(self) -> None:
        schema = load(ROOT / "manifests/core-compatibility-pending.schema.json")
        self.assertEqual(
            "https://spruceui.local/schemas/core-compatibility-pending.schema.json",
            schema["$id"],
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            pending.PENDING_STATE,
            schema["properties"]["state"]["const"],
        )
        self.assertEqual(
            pending.NEXT_GATE,
            schema["properties"]["next_gate"]["const"],
        )
        self.assertNotIn("golden_source", schema["properties"])
        self.assertNotIn("artifact_sha256", schema["properties"])


if __name__ == "__main__":
    unittest.main()
