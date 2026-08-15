from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.core_pipeline_lib.campaign.matrix_materialize import (
    MATRIX_STATE_RELATIVE,
    materialize_matrix_v2,
)
from scripts.core_pipeline_lib.campaign.matrix_model import render_matrix_v1
from scripts.core_pipeline_lib.campaign.matrix_store import (
    StoredNormalizedMatrixV1,
    load_normalized_matrix,
    stage_normalized_matrix,
)
from scripts.core_pipeline_lib.campaign.store import CampaignStore
from scripts.core_pipeline_lib.errors import PipelineError
from tests.test_campaign_matrix_materialize import (
    _immutable_full_fixture,
    _immutable_small_fixture,
    _start_small_matrix_universe,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/core_pipeline_lib/campaign/matrix_store.py"


class CampaignMatrixStoreTests(unittest.TestCase):
    _SMALL_CLOSURE_TESTS = frozenset(
        {
            "test_invalid_closure_creates_no_storage_state",
            "test_load_rejects_missing_or_tampered_cell_bytes",
            "test_restage_is_idempotent_and_preserves_the_root_locator",
        }
    )
    _SMALL_STORED_TESTS = frozenset(
        {
            "test_load_rejects_missing_or_tampered_cell_bytes",
            "test_restage_is_idempotent_and_preserves_the_root_locator",
        }
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.raw, cls.closure = _immutable_full_fixture()
        cls.temporary = tempfile.TemporaryDirectory()
        cls.repository_root = Path(cls.temporary.name)
        cls.store = CampaignStore(cls.repository_root, MATRIX_STATE_RELATIVE)
        cls.publication_order: list[str] = []
        original = cls.store.create_or_verify

        def recording_create_or_verify(*, reference, raw):
            cls.publication_order.append(reference.kind)
            return original(reference=reference, raw=raw)

        with patch.object(
            cls.store,
            "create_or_verify",
            side_effect=recording_create_or_verify,
        ):
            cls.first_store = stage_normalized_matrix(cls.store, cls.closure)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        # The dependency-order/load owner keeps the one real full-store closure.
        if self._testMethodName not in self._SMALL_CLOSURE_TESTS:
            return
        _start_small_matrix_universe(self)
        self.raw, self.closure = _immutable_small_fixture()
        if self._testMethodName not in self._SMALL_STORED_TESTS:
            return

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repository_root = Path(temporary.name)
        self.store = CampaignStore(self.repository_root, MATRIX_STATE_RELATIVE)
        self.publication_order = []
        original = self.store.create_or_verify

        def recording_create_or_verify(*, reference, raw):
            self.publication_order.append(reference.kind)
            return original(reference=reference, raw=raw)

        with patch.object(
            self.store,
            "create_or_verify",
            side_effect=recording_create_or_verify,
        ):
            self.first_store = stage_normalized_matrix(self.store, self.closure)

    def test_stage_is_dependency_ordered_and_loads_exact_closure(self) -> None:
        stored = self.first_store
        self.assertIsInstance(stored, StoredNormalizedMatrixV1)
        self.assertEqual(2_646, len(stored.cells))
        self.assertEqual(98, len(stored.shards))
        self.assertEqual(self.closure.root_reference, stored.root_reference)
        self.assertEqual(
            ["matrix-cell"] * 2_646
            + ["matrix-shard"] * 98
            + ["matrix-root"],
            self.publication_order,
        )
        self.assertEqual(
            {"created"},
            {item.disposition for item in (*stored.cells, *stored.shards, stored.root)},
        )

        loaded = load_normalized_matrix(self.store, stored.root_reference)
        self.assertEqual(self.closure, loaded)
        self.assertEqual(self.raw, materialize_matrix_v2(loaded))

    def test_restage_is_idempotent_and_preserves_the_root_locator(self) -> None:
        stored = stage_normalized_matrix(self.store, self.closure)
        self.assertEqual(self.closure.root_reference, stored.root_reference)
        self.assertEqual(
            {"verified"},
            {item.disposition for item in (*stored.cells, *stored.shards, stored.root)},
        )
        self.assertEqual(
            self.closure,
            load_normalized_matrix(self.store, stored.root_reference),
        )

    def test_load_rejects_missing_or_tampered_cell_bytes(self) -> None:
        reference = self.closure.shards[0].cells[0].reference
        path = self.repository_root / reference.path
        original = path.read_bytes()
        path.unlink()
        try:
            with self.assertRaisesRegex(PipelineError, "missing"):
                load_normalized_matrix(self.store, self.closure.root_reference)
        finally:
            self.store.create_or_verify(reference=reference, raw=original)

        path.write_bytes(b"{}\n")
        try:
            with self.assertRaisesRegex(PipelineError, "do not match"):
                load_normalized_matrix(self.store, self.closure.root_reference)
        finally:
            path.write_bytes(original)
            path.chmod(0o644)
        self.assertEqual(
            self.closure,
            load_normalized_matrix(self.store, self.closure.root_reference),
        )

    def test_wrong_root_kind_is_rejected_before_store_access(self) -> None:
        wrong = replace(self.closure.root_reference, kind="matrix-shard")
        with patch.object(self.store, "read_exact") as read_exact:
            with self.assertRaisesRegex(PipelineError, "root reference"):
                load_normalized_matrix(self.store, wrong)
        read_exact.assert_not_called()

    def test_invalid_closure_creates_no_storage_state(self) -> None:
        invalid = replace(
            self.closure,
            cells=(self.closure.cells[1], self.closure.cells[0], *self.closure.cells[2:]),
        )
        with tempfile.TemporaryDirectory() as temporary:
            repository_root = Path(temporary)
            store = CampaignStore(repository_root, MATRIX_STATE_RELATIVE)
            with patch.object(store, "create_or_verify") as create_or_verify:
                with self.assertRaises(PipelineError):
                    stage_normalized_matrix(store, invalid)
            create_or_verify.assert_not_called()
            self.assertFalse((repository_root / MATRIX_STATE_RELATIVE).exists())

    def test_module_delegates_all_filesystem_and_path_policy_to_store(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse({"os", "pathlib", "shutil", "tempfile"} & imported)
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue({"create_or_verify", "read_exact"} <= calls)
        self.assertFalse({"unlink", "replace", "rename", "mkdir", "open"} & calls)


if __name__ == "__main__":
    unittest.main()
