#!/usr/bin/env python3

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.core_pipeline_lib.runtime import (
    HOST_EXECUTION_PROFILE_PATH,
    HOST_EXECUTION_PROFILE_SCHEMA_PATH,
    RunnerProfileError,
    resolve_host_execution_profile,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_canonical_files(root: Path) -> None:
    for relative in (
        HOST_EXECUTION_PROFILE_PATH,
        HOST_EXECUTION_PROFILE_SCHEMA_PATH,
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def _store(root: Path, namespace: str, source: Path) -> Path:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target = root / ".local-e2e" / "store" / namespace / "sha256" / digest[:2] / digest
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return target


class HostExecutionProfileTests(unittest.TestCase):
    def test_exact_profiles_share_one_resource_class_but_not_runner_identity(self) -> None:
        local = resolve_host_execution_profile("local", repository_root=ROOT)
        simulated = resolve_host_execution_profile(
            "github-actions-sim", repository_root=ROOT
        )

        self.assertEqual(local.resources(), simulated.resources())
        self.assertEqual(local.cache(), simulated.cache())
        self.assertEqual(local.resource_class_id, simulated.resource_class_id)
        self.assertEqual(
            "selected-then-reproduction-sequential",
            local.pair_execution,
        )
        self.assertNotEqual(local.profile_id, simulated.profile_id)
        self.assertNotEqual(local.runner_identity(), simulated.runner_identity())
        self.assertEqual(("libretro-super",), local.admissible_build_drivers)

    def test_native_github_actions_is_not_falsely_resolved_as_local(self) -> None:
        with self.assertRaisesRegex(
            RunnerProfileError, "outside the local host profile tranche"
        ):
            resolve_host_execution_profile(
                "github-actions", repository_root=ROOT
            )

    def test_immutable_snapshot_survives_canonical_registry_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _copy_canonical_files(root)
            registry_snapshot = _store(
                root,
                "host-execution-profiles",
                root / HOST_EXECUTION_PROFILE_PATH,
            )
            schema_snapshot = _store(
                root,
                "schemas",
                root / HOST_EXECUTION_PROFILE_SCHEMA_PATH,
            )
            before = resolve_host_execution_profile(
                "local",
                repository_root=root,
                registry_path=registry_snapshot,
                registry_schema_path=schema_snapshot,
            )

            (root / HOST_EXECUTION_PROFILE_PATH).write_text("{}\n", encoding="utf-8")
            after = resolve_host_execution_profile(
                "local",
                repository_root=root,
                registry_path=registry_snapshot,
                registry_schema_path=schema_snapshot,
            )

            self.assertEqual(before, after)
            self.assertEqual(
                registry_snapshot.relative_to(root).as_posix(),
                after.registry_path,
            )
            self.assertEqual(
                schema_snapshot.relative_to(root).as_posix(),
                after.registry_schema_path,
            )

    def test_bound_schema_bytes_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _copy_canonical_files(root)
            (root / HOST_EXECUTION_PROFILE_SCHEMA_PATH).write_text(
                "{}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RunnerProfileError, "schema digest mismatch"):
                resolve_host_execution_profile("local", repository_root=root)


if __name__ == "__main__":
    unittest.main()
