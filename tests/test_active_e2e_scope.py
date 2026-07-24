from __future__ import annotations

import copy
import unittest

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.records.e2e import active_promotion_e2e_scope


class ActivePromotionE2eScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = {
            "schema_version": 2,
            "builds": [
                {"core_id": "quicknes", "architecture": "arm64"},
                {"core_id": "quicknes", "architecture": "armhf"},
            ],
            "packages": [{"core_id": "quicknes"}],
        }

    def test_exact_one_core_schema_v2_scope_is_returned(self) -> None:
        builds, packages = active_promotion_e2e_scope(
            self.evidence, "quicknes"
        )
        self.assertIs(self.evidence["builds"], builds)
        self.assertIs(self.evidence["packages"], packages)

    def test_legacy_and_foreign_core_evidence_are_rejected(self) -> None:
        legacy = {**self.evidence, "schema_version": 1}
        with self.assertRaisesRegex(PipelineError, "schema-v2"):
            active_promotion_e2e_scope(legacy, "quicknes")

        for field, item in (
            ("builds", {"core_id": "nestopia", "architecture": "arm64"}),
            ("packages", {"core_id": "nestopia"}),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.evidence)
                changed[field].append(item)
                with self.assertRaisesRegex(PipelineError, "exactly one core"):
                    active_promotion_e2e_scope(changed, "quicknes")

    def test_malformed_build_and_package_lists_fail_closed(self) -> None:
        for field, value in (
            ("builds", None),
            ("builds", [None]),
            ("packages", {}),
            ("packages", ["quicknes"]),
        ):
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(self.evidence)
                changed[field] = value
                with self.assertRaisesRegex(PipelineError, "malformed"):
                    active_promotion_e2e_scope(changed, "quicknes")


if __name__ == "__main__":
    unittest.main()
