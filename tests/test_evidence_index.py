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
import tempfile
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

_verify_spec = importlib.util.spec_from_file_location(
    "verify_core", ROOT / "scripts" / "verify_core.py"
)
assert _verify_spec is not None and _verify_spec.loader is not None
verify_core = importlib.util.module_from_spec(_verify_spec)
_verify_spec.loader.exec_module(verify_core)


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
        pending = {
            path.stem
            for path in (
                evidence_index.ROOT / "manifests/compatibility/pending"
            ).glob("*.json")
        }
        for core in cores:
            with self.subTest(core=core):
                path = evidence_index.index_path(core)
                if core in pending:
                    # awaiting-local-e2e: no promoted evidence yet, by design
                    self.assertFalse(path.is_file(), f"pending core has index: {core}")
                    continue
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
        core = "2048"
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

        pin_matches = sorted((ROOT / "pins" / "core-sets").glob(f"{core}-*.json"))
        self.assertGreater(len(pin_matches), 1)
        self.assertEqual(index["semantic_id"], verify_core.discover_sid(core))

        semantic_id = "sample-0123456789ab-abcdef012345"
        canonical_pin = f"pins/core-sets/{semantic_id}.json"
        valid_compatibility = {
            "core_id": "sample",
            "golden_source": canonical_pin,
        }
        valid_index = {
            "core_id": "sample",
            "semantic_id": semantic_id,
            "pin_path": canonical_pin,
        }

        def write_json(path: Path, document: object) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document), encoding="utf-8")

        cases = {
            "missing-compatibility": (None, valid_index, True),
            "malformed-compatibility": ("{", valid_index, True),
            "compatibility-core-disagreement": (
                {**valid_compatibility, "core_id": "different"},
                valid_index,
                True,
            ),
            "noncanonical-compatibility-pin": (
                {**valid_compatibility, "golden_source": f"./{canonical_pin}"},
                valid_index,
                True,
            ),
            "missing-evidence-index": (valid_compatibility, None, True),
            "malformed-evidence-index": (valid_compatibility, "[", True),
            "evidence-core-disagreement": (
                valid_compatibility,
                {**valid_index, "core_id": "different"},
                True,
            ),
            "evidence-semantic-disagreement": (
                valid_compatibility,
                {**valid_index, "semantic_id": "sample-111111111111-222222222222"},
                True,
            ),
            "evidence-path-disagreement": (
                valid_compatibility,
                {
                    **valid_index,
                    "pin_path": "pins/core-sets/sample-111111111111-222222222222.json",
                },
                True,
            ),
            "missing-canonical-pin": (valid_compatibility, valid_index, False),
        }
        for label, (compatibility_fixture, index_fixture, create_pin) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                compatibility_fixture_path = (
                    root / "manifests" / "compatibility" / "sample.json"
                )
                evidence_fixture_path = root / "pins" / "evidence" / "sample.json"
                if isinstance(compatibility_fixture, str):
                    compatibility_fixture_path.parent.mkdir(parents=True)
                    compatibility_fixture_path.write_text(
                        compatibility_fixture, encoding="utf-8"
                    )
                elif compatibility_fixture is not None:
                    write_json(compatibility_fixture_path, compatibility_fixture)
                if isinstance(index_fixture, str):
                    evidence_fixture_path.parent.mkdir(parents=True)
                    evidence_fixture_path.write_text(index_fixture, encoding="utf-8")
                elif index_fixture is not None:
                    write_json(evidence_fixture_path, index_fixture)
                if create_pin:
                    write_json(root / canonical_pin, {})
                with mock.patch.object(verify_core, "ROOT", root):
                    with self.assertRaises(SystemExit):
                        verify_core.discover_sid("sample")


if __name__ == "__main__":
    unittest.main()
