"""Canonical per-core surfaces are unique, complete, and duplicate-free.

Successor coverage for the retired legacy-tranche package (2026-07-23): the
active surfaces previously asserted through the frozen aggregate matrix are
now asserted directly for every catalog core.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from .cores.support import pipeline
from scripts import profile_registry as registry
from scripts.core_pipeline_lib.records import compatibility_pending as pending
from scripts.core_pipeline_lib.errors import PipelineError

ROOT = Path(__file__).resolve().parents[1]


class CanonicalSurfaceTests(unittest.TestCase):
    def test_every_core_binds_exactly_one_pin_and_source_set(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        canonical: dict[str, str] = {}
        for path in sorted((ROOT / "manifests/compatibility").glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            core_id = document["core_id"]
            golden_source = document["golden_source"]
            semantic_id = Path(golden_source).stem
            self.assertEqual(f"{core_id}.json", path.name)
            self.assertNotIn(core_id, canonical)
            canonical[core_id] = semantic_id
            self.assertTrue(
                (ROOT / "pins/core-sets" / f"{semantic_id}.json").is_file(),
                golden_source,
            )
            composed = registry.composed_source_set(semantic_id)
            self.assertEqual({core_id}, set(composed["sources"]), golden_source)
        pending = {
            path.stem
            for path in (ROOT / "manifests/compatibility/pending").glob("*.json")
        }
        # Pending cores (awaiting-local-e2e) are cataloged without promoted
        # evidence; canonical records and pending records partition the catalog.
        self.assertEqual(set(), pending & set(canonical))
        self.assertEqual(set(catalog["cores"]), set(canonical) | pending)

        expected = {f"{sid}.json" for sid in canonical.values()}
        self.assertEqual(len(canonical), len(expected))
        pin_paths = {
            path.name: path
            for path in (ROOT / "pins/core-sets").glob("*.json")
        }
        self.assertLessEqual(expected, set(pin_paths))

        # Immutable historical and proof-bearing pins may coexist with the
        # one pin selected by canonical compatibility.  They remain admitted
        # only when the full frozen-recipe/store/source validator proves their
        # bytes and they retain the exact parentless one-core semantic identity.
        for pin_name in sorted(set(pin_paths) - expected):
            path = pin_paths[pin_name]
            with self.subTest(extra_pin=pin_name):
                document = json.loads(path.read_text(encoding="utf-8"))
                core_id, semantic_id = pipeline.require_individual_pin_identity(
                    document,
                    pin_path=path,
                )
                self.assertIn(core_id, catalog["cores"])
                self.assertEqual(f"{semantic_id}.json", pin_name)
                report = pipeline._validate_historical_pin_set_document(
                    document,
                    verify_store=True,
                    verify_sources=True,
                    document_path=path,
                )
                self.assertEqual("valid", report.get("status"), report)
                self.assertEqual([], report.get("errors"), report)

    def test_duplicate_canonical_compatibility_is_rejected(self) -> None:
        source = ROOT / "manifests/compatibility/vecx.json"
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compatibility = root / "manifests" / "compatibility"
            compatibility.mkdir(parents=True)
            payload = source.read_text(encoding="utf-8")
            (compatibility / "vecx.json").write_text(payload, encoding="utf-8")
            (compatibility / "duplicate.json").write_text(
                payload, encoding="utf-8"
            )
            catalog_slice = {"cores": {"vecx": catalog["cores"]["vecx"]}}
            with self.assertRaisesRegex(
                PipelineError,
                "duplicate canonical compatibility evidence for vecx|"
                "compatibility path does not bind core_id",
            ):
                pending.load_catalog_compatibility_coverage(
                    catalog=catalog_slice,
                    repository_root=root,
                )


if __name__ == "__main__":
    unittest.main()
