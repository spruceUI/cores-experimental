"""Tests for the checked-in device compatibility matrix renderer."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "device_matrix.py"

_spec = importlib.util.spec_from_file_location("device_matrix", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
device_matrix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(device_matrix)


class DeviceMatrixTests(unittest.TestCase):
    def test_matrix_is_an_exact_98_by_8_partition(self) -> None:
        cores, cells = device_matrix.build_matrix()
        expected_devices = {
            contract_id for contract_id, _label in device_matrix.DEVICE_COLUMNS
        }
        self.assertEqual(100, len(cores))
        self.assertEqual(set(cores), set(cells))
        for core in cores:
            self.assertEqual(expected_devices, set(cells[core]), core)

    def test_runtime_constraints_do_not_replace_static_verdicts(self) -> None:
        _cores, cells = device_matrix.build_matrix()
        mini = "device-miyoo-mini-family-v0"
        self.assertEqual(
            "?", cells["km_parallel_n64_xtreme_amped_turbo"][mini]
        )
        self.assertEqual("Y", cells["puae2021"][mini])

    def test_runtime_matrix_is_exact_and_artifact_bound(self) -> None:
        cores, cells, projection = device_matrix.build_runtime_matrix()
        self.assertEqual(100, len(cores))
        self.assertEqual(
            {"FAIL": 4, "NO_BUILD": 64, "PASS": 650, "UNKNOWN": 850},
            projection["status_counts"],
        )
        expected_devices = {
            device_id for device_id, _label in device_matrix.RUNTIME_DEVICE_COLUMNS
        }
        self.assertEqual(set(cores), set(cells))
        for core in cores:
            self.assertEqual(expected_devices, set(cells[core]), core)

        failures = {
            (core, device_id)
            for core, row in cells.items()
            for device_id, symbol in row.items()
            if symbol == "F"
        }
        self.assertEqual(
            {
                ("km_parallel_n64_xtreme_amped_turbo", "MIYOO_MINI_FLIP"),
                ("km_parallel_n64_xtreme_amped_turbo", "MIYOO_MINI_PLUS"),
                ("puae2021", "MIYOO_MINI_FLIP"),
                ("puae2021", "MIYOO_MINI_PLUS"),
            },
            failures,
        )
        for core in ("km_parallel_n64_xtreme_amped_turbo", "puae2021"):
            self.assertEqual("?", cells[core]["MIYOO_MINI"])
            self.assertEqual("?", cells[core]["MIYOO_MINI_V4"])
        for device_id in (
            "MIYOO_FLIP",
            "TRIMUI_BRICK",
            "TRIMUI_SMART_PRO",
            "TRIMUI_SMART_PRO_S",
        ):
            self.assertEqual("?", cells["yabasanshiro"][device_id])

    def test_render_is_deterministic_and_checked_in(self) -> None:
        rendered = device_matrix.render_markdown()
        self.assertEqual(rendered, device_matrix.render_markdown())
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(1, readme.count(device_matrix.MARK_START))
        self.assertEqual(1, readme.count(device_matrix.MARK_END))
        self.assertEqual(rendered, device_matrix.extract_marked_block(readme))

    def test_report_semantic_drift_fails_closed(self) -> None:
        for key, replacement in (
            ("schema_version", 2),
            ("schema_version", True),
            ("screen", "artifact-runtime-v2"),
            ("publication", "enabled"),
        ):
            with self.subTest(key=key):
                report = copy.deepcopy(device_matrix.device_sets.build_report())
                report[key] = replacement
                with mock.patch.object(
                    device_matrix.device_sets, "build_report", return_value=report
                ):
                    with self.assertRaises(device_matrix.DeviceMatrixError):
                        device_matrix.build_matrix()

    def test_unknown_bucket_fails_closed(self) -> None:
        report = copy.deepcopy(device_matrix.device_sets.build_report())
        device_id = device_matrix.DEVICE_COLUMNS[0][0]
        report["devices"][device_id]["counts"]["new_unmapped_bucket"] = 0
        report["devices"][device_id]["new_unmapped_bucket"] = []
        with mock.patch.object(
            device_matrix.device_sets, "build_report", return_value=report
        ):
            with self.assertRaises(device_matrix.DeviceMatrixError):
                device_matrix.build_matrix()

    def test_unknown_view_or_row_field_fails_closed(self) -> None:
        for target in ("view", "row"):
            with self.subTest(target=target):
                report = copy.deepcopy(device_matrix.device_sets.build_report())
                device_id = device_matrix.DEVICE_COLUMNS[0][0]
                if target == "view":
                    report["devices"][device_id]["runtime_v2"] = {}
                else:
                    report["devices"][device_id]["eligible"][0][
                        "runtime_verdict"
                    ] = "PASS"
                with mock.patch.object(
                    device_matrix.device_sets, "build_report", return_value=report
                ):
                    with self.assertRaises(device_matrix.DeviceMatrixError):
                        device_matrix.build_matrix()

    def test_runtime_projection_tampering_fails_closed(self) -> None:
        projection = copy.deepcopy(
            device_matrix.device_runtime_evidence.project_current_physical_devices()
        )
        projection["devices"][0]["results"][0]["load_result"] = "PASS"
        with mock.patch.object(
            device_matrix.device_runtime_evidence,
            "project_current_physical_devices",
            return_value=projection,
        ):
            with self.assertRaises(device_matrix.DeviceMatrixError):
                device_matrix.build_runtime_matrix()

    def test_bucket_required_field_fails_closed(self) -> None:
        report = copy.deepcopy(device_matrix.device_sets.build_report())
        device_id = device_matrix.DEVICE_COLUMNS[0][0]
        view = report["devices"][device_id]
        row = view["eligible"].pop()
        row["glibcxx"] = "3.4.1"
        view["counts"]["eligible"] -= 1
        view["eligible_ceiling_uncaptured"].append(row)
        view["counts"]["eligible_ceiling_uncaptured"] += 1
        del row["glibcxx"]
        with mock.patch.object(
            device_matrix.device_sets, "build_report", return_value=report
        ):
            with self.assertRaises(device_matrix.DeviceMatrixError):
                device_matrix.build_matrix()

    def test_duplicate_core_fails_closed(self) -> None:
        report = copy.deepcopy(device_matrix.device_sets.build_report())
        device_id = device_matrix.DEVICE_COLUMNS[0][0]
        view = report["devices"][device_id]
        duplicate = copy.deepcopy(view["eligible"][0])
        view["provider_uncaptured"].append(duplicate)
        view["counts"]["provider_uncaptured"] += 1
        with mock.patch.object(
            device_matrix.device_sets, "build_report", return_value=report
        ):
            with self.assertRaises(device_matrix.DeviceMatrixError):
                device_matrix.build_matrix()

    def test_marker_replacement_requires_one_ordered_pair(self) -> None:
        valid = (
            "before\n"
            + device_matrix.MARK_START
            + "\nold\n"
            + device_matrix.MARK_END
            + "\nafter\n"
        )
        self.assertEqual(
            "before\n"
            + device_matrix.MARK_START
            + "\nnew\n"
            + device_matrix.MARK_END
            + "\nafter\n",
            device_matrix.replace_marked_block(valid, "new"),
        )
        invalid = (
            "",
            device_matrix.MARK_START,
            device_matrix.MARK_END,
            device_matrix.MARK_END + "\n" + device_matrix.MARK_START,
            valid + device_matrix.MARK_START,
            valid + device_matrix.MARK_END,
            valid + valid,
        )
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(device_matrix.DeviceMatrixError):
                    device_matrix.replace_marked_block(text, "new")


if __name__ == "__main__":
    unittest.main()
