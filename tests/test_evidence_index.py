"""The tracked per-core evidence index matches disk-derived evidence.

Each `pins/evidence/<core>.json` is generated at promotion time from the
promoted documents and run records; this gate regenerates every index and
fails closed on any drift, so a stale or hand-edited index cannot survive
the suite. Reviewed contract pins are NOT covered here — they stay in the
per-core contract modules and tests.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "evidence_index", ROOT / "scripts" / "evidence_index.py"
)
assert _spec is not None and _spec.loader is not None
evidence_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(evidence_index)


class EvidenceIndexTests(unittest.TestCase):
    def test_compose_consumes_each_evidence_path_once(self) -> None:
        core = evidence_index.catalog_cores()[0]
        observed: set[Path] = set()
        original = evidence_index._snapshot_bytes

        def one_snapshot(path: Path):
            resolved = path.resolve()
            self.assertNotIn(resolved, observed)
            observed.add(resolved)
            return original(path)

        with mock.patch.object(
            evidence_index,
            "_snapshot_bytes",
            side_effect=one_snapshot,
        ):
            document = evidence_index.compose(core)
        self.assertEqual(core, document["core_id"])
        self.assertGreater(len(observed), 4)

    def test_every_catalog_core_has_a_current_index(self) -> None:
        cores = evidence_index.catalog_cores()
        self.assertEqual(len(cores), len(set(cores)))
        for core in cores:
            with self.subTest(core=core):
                path = evidence_index.index_path(core)
                self.assertTrue(path.is_file(), f"missing index for {core}")
                stored = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(stored, evidence_index.compose(core))

    def test_index_directory_has_no_orphans(self) -> None:
        cores = set(evidence_index.catalog_cores())
        on_disk = {p.stem for p in (ROOT / "pins" / "evidence").glob("*.json")}
        self.assertEqual(set(), on_disk - cores)

    def test_index_binds_the_promoted_pin(self) -> None:
        # Spot-check the derivation contract on one core: the index's
        # semantic_id and package sha must match the pin the compatibility
        # document names.
        core = evidence_index.catalog_cores()[0]
        index = json.loads(
            evidence_index.index_path(core).read_text(encoding="utf-8")
        )
        compatibility = json.loads(
            (ROOT / "manifests" / "compatibility" / f"{core}.json").read_text(
                encoding="utf-8"
            )
        )
        pin = json.loads(
            (ROOT / compatibility["golden_source"]).read_text(encoding="utf-8")
        )
        self.assertEqual(pin["pin_id"], index["semantic_id"])
        self.assertEqual(
            pin["cores"][core]["selection"]["package"]["sha256"],
            index["package"]["sha256"],
        )
        self.assertEqual(compatibility["source_commit"], index["source_commit"])


if __name__ == "__main__":
    unittest.main()
