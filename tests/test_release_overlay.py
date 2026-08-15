from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import scripts.release_overlay as release_overlay
from scripts.release_overlay import (
    OverlayError,
    YABASANSHIRO_SOURCE,
    YABASANSHIRO_VARIANTS,
    build_overlay,
)
from scripts.core_pipeline_lib.release import (
    construct_release_plan,
    release_candidate_content_sha256,
    seal_release_candidate,
    write_core_result,
    write_release_plan,
)
from tests.test_full_release_support import (
    normalized_e2e,
    release_row,
    repository_facts,
)
from tests.test_full_release_track_group import group_facts, group_selection


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_asset_zip(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)


def default_asset_members(core_id: str) -> dict[str, bytes]:
    return {
        f"cores/{core_id}_libretro.so": f"armhf-{core_id}".encode(),
        f"cores64/{core_id}_libretro.so": f"arm64-{core_id}".encode(),
        f"{core_id}_libretro.info": f"info-{core_id}".encode(),
        "manifest.json": b"{}",
    }


def write_candidate(
    root: Path,
    asset_members: dict[str, dict[str, bytes]],
    mutate: dict | None = None,
    track_states: dict[str, str] | None = None,
    repository: dict | None = None,
    candidate_id: str = "cand-test-v1-123-1",
) -> Path:
    package_bytes: dict[str, bytes] = {}
    rows = []
    for core_id, members in sorted(asset_members.items()):
        package_path = root / "candidate-input-packages" / f"{core_id}_libretro.zip"
        write_asset_zip(package_path, members)
        data = package_path.read_bytes()
        package_bytes[core_id] = data
        row = release_row(core_id)
        row["package"] = {
            "name": f"{core_id}_libretro.zip",
            "sha256": sha256(data),
            "size": len(data),
        }
        rows.append(row)

    group = None
    scope = "explicit"
    if track_states is not None:
        if set(track_states) != set(asset_members):
            raise AssertionError("track state fixture must cover every core")
        scope = "track-group"
        for row in rows:
            row["core_group"] = group_selection(
                row,
                track_states[row["core_id"]],
            )
        group = group_facts()
        group["stable_core_count"] = sum(
            state == "stable" for state in track_states.values()
        )
        group["unstable_fallback_core_count"] = sum(
            state == "unstable_fallback" for state in track_states.values()
        )
        group["test_core_count"] = sum(
            state == "test" for state in track_states.values()
        )
        group["inventory_state"] = (
            "stable"
            if group["stable_core_count"] == len(track_states)
            else "unstable"
        )
    plan = construct_release_plan(
        candidate_id=candidate_id,
        scope=scope,
        repository=repository or repository_facts(),
        cores=rows,
        group=group,
    )
    plan_path = root / "candidate-input-plan.json"
    write_release_plan(plan=plan, output_path=plan_path)
    results_root = root / "candidate-input-results"
    for row in plan["cores"]:
        core_id = row["core_id"]
        package_path = root / "candidate-input-packages" / row["package"]["name"]
        assert package_path.read_bytes() == package_bytes[core_id]
        write_core_result(
            plan=plan,
            plan_path=plan_path,
            core_id=core_id,
            runner_selector="local",
            e2e=normalized_e2e(plan, core_id, "local"),
            package_path=package_path,
            output_dir=results_root / core_id,
        )
    candidate_dir = root / "candidate"
    seal_release_candidate(
        plan=plan,
        plan_path=plan_path,
        results_root=results_root,
        output_dir=candidate_dir,
        runner_selector="local",
    )
    if mutate:
        candidate_path = candidate_dir / "candidate.json"
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        candidate.update(mutate)
        candidate_path.write_text(
            json.dumps(candidate, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return candidate_dir


def trusted_build_overlay(
    candidate_dir: Path,
    output_dir: Path,
    *,
    expected_repository_head: str | None = None,
    expected_run_id: str = "123",
    expected_run_attempt: int = 1,
    trusted_plan_validator=None,
) -> dict:
    plan = json.loads((candidate_dir / "plan.json").read_text(encoding="utf-8"))
    validator = trusted_plan_validator or (lambda supplied: supplied)
    return build_overlay(
        candidate_dir,
        output_dir,
        trusted_plan_validator=validator,
        expected_repository_head=(
            expected_repository_head or plan["repository"]["head"]
        ),
        expected_coordinator_run_id=expected_run_id,
        expected_coordinator_run_attempt=expected_run_attempt,
    )


class ReleaseOverlayTests(unittest.TestCase):
    def test_forged_seal_bindings_are_rejected_before_projection(self) -> None:
        cases = {
            "candidate-content": "content_sha256",
            "asset-set": "asset_set_sha256",
            "result-reference": "sealed result content identity",
            "group": "group does not match plan",
        }
        for case, expected_error in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                track_states = {"alpha": "unstable_fallback"} if case == "group" else None
                candidate_dir = write_candidate(
                    root,
                    {"alpha": default_asset_members("alpha")},
                    track_states=track_states,
                )
                candidate_path = candidate_dir / "candidate.json"
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                if case == "candidate-content":
                    candidate["content_sha256"] = "f" * 64
                elif case == "asset-set":
                    candidate["asset_set_sha256"] = "f" * 64
                elif case == "result-reference":
                    candidate["assets"][0]["result"]["content_sha256"] = "f" * 64
                else:
                    candidate["group"]["track_registry"]["content_sha256"] = "f" * 64
                if case != "candidate-content":
                    candidate["content_sha256"] = release_candidate_content_sha256(
                        candidate
                    )
                candidate_path.write_text(
                    json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(OverlayError, expected_error):
                    trusted_build_overlay(candidate_dir, root / "overlay")

    def test_track_group_inventory_survives_overlay_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root,
                {
                    "alpha": default_asset_members("alpha"),
                    "beta": default_asset_members("beta"),
                },
                track_states={"alpha": "stable", "beta": "unstable_fallback"},
            )
            candidate_path = candidate_dir / "candidate.json"
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

            manifest = trusted_build_overlay(candidate_dir, root / "overlay")

            self.assertEqual(manifest["source"]["group"], candidate["group"])
            self.assertEqual(manifest["summary"]["stable_core_count"], 1)
            self.assertEqual(
                manifest["summary"]["unstable_fallback_core_count"], 1
            )
            states_by_core = {
                member["source_core_id"]: member["core_group"]["selected_state"]
                for member in manifest["members"]
            }
            self.assertEqual(
                states_by_core,
                {"alpha": "stable", "beta": "unstable_fallback"},
            )
            self.assertEqual(
                {
                    member["core_group"]["source_commit"]
                    for member in manifest["members"]
                },
                {
                    asset["core_group"]["source_commit"]
                    for asset in candidate["assets"]
                },
            )

            candidate["group"]["stable_core_count"] = 2
            candidate_path.write_text(
                json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(OverlayError, "inventory counts"):
                trusted_build_overlay(candidate_dir, root / "drifted-overlay")

    def test_invalid_track_asset_state_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root,
                {"alpha": default_asset_members("alpha")},
                track_states={"alpha": "unstable_fallback"},
            )
            candidate_path = candidate_dir / "candidate.json"
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate["assets"][0]["core_group"]["selected_state"] = "forged"
            candidate_path.write_text(
                json.dumps(candidate, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(
                release_overlay,
                "validate_sealed_candidate_directory",
                return_value=candidate,
            ), self.assertRaisesRegex(OverlayError, "asset state"):
                trusted_build_overlay(candidate_dir, root / "overlay")

    def test_overlay_layout_and_yabasanshiro_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root,
                {
                    "alpha": default_asset_members("alpha"),
                    "yabasanshiro": {
                        "cores64/yabasanshiro_libretro.so": b"arm64-yaba",
                        "yabasanshiro_libretro.info": b"info-yaba",
                        "manifest.json": b"{}",
                    },
                },
            )
            output_dir = root / "overlay"
            manifest = trusted_build_overlay(candidate_dir, output_dir)

            overlay_path = output_dir / "cand-test-v1-123-1-file-overlay.zip"
            self.assertTrue(overlay_path.is_file())
            with zipfile.ZipFile(overlay_path) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertEqual(
                    set(names),
                    {
                        "RetroArch/.retroarch/cores/alpha_libretro.so",
                        "RetroArch/.retroarch/cores64/alpha_libretro.so",
                        "RetroArch/.retroarch/info/alpha_libretro.info",
                        YABASANSHIRO_SOURCE,
                        *YABASANSHIRO_VARIANTS,
                        "RetroArch/.retroarch/info/yabasanshiro_libretro.info",
                    },
                )
                source_bytes = archive.read(YABASANSHIRO_SOURCE)
                for variant in YABASANSHIRO_VARIANTS:
                    self.assertEqual(archive.read(variant), source_bytes)

            self.assertTrue(manifest["yabasanshiro_variants"]["applied"])
            self.assertEqual(
                manifest["yabasanshiro_variants"]["copies"],
                list(YABASANSHIRO_VARIANTS),
            )
            self.assertEqual(manifest["summary"]["core_count"], 2)
            self.assertEqual(manifest["summary"]["cores_armhf"], 1)
            self.assertEqual(manifest["summary"]["cores_arm64"], 4)
            self.assertEqual(manifest["overlay"]["member_count"], 7)
            self.assertEqual(
                manifest["overlay"]["sha256"],
                sha256(overlay_path.read_bytes()),
            )
            written = json.loads(
                (output_dir / "overlay-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written, manifest)

    def test_overlay_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            first = trusted_build_overlay(candidate_dir, root / "first")
            second = trusted_build_overlay(candidate_dir, root / "second")
            first_bytes = (root / "first" / first["overlay"]["path"]).read_bytes()
            second_bytes = (root / "second" / second["overlay"]["path"]).read_bytes()
            self.assertEqual(first_bytes, second_bytes)

    def test_asset_tamper_fails_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            asset_path = candidate_dir / "assets" / "alpha_libretro.zip"
            write_asset_zip(
                asset_path,
                {
                    **default_asset_members("alpha"),
                    f"cores/alpha_libretro.so": b"tampered",
                },
            )
            output_dir = root / "overlay"
            with self.assertRaisesRegex(OverlayError, "sealed asset bytes"):
                trusted_build_overlay(candidate_dir, output_dir)
            self.assertFalse(output_dir.exists())

    def test_unexpected_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            members = default_asset_members("alpha")
            members["cores/../escape.so"] = b"evil"
            candidate_dir = write_candidate(root, {"alpha": members})
            output_dir = root / "overlay"
            with self.assertRaisesRegex(OverlayError, "unexpected member"):
                trusted_build_overlay(candidate_dir, output_dir)
            self.assertFalse(output_dir.exists())

    def test_unsealed_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root,
                {"alpha": default_asset_members("alpha")},
                mutate={"result": "pending"},
            )
            with self.assertRaisesRegex(OverlayError, "must be sealed"):
                trusted_build_overlay(candidate_dir, root / "overlay")

    def test_missing_yabasanshiro_is_recorded_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            manifest = trusted_build_overlay(candidate_dir, root / "overlay")
            self.assertFalse(manifest["yabasanshiro_variants"]["applied"])
            self.assertEqual(manifest["yabasanshiro_variants"]["copies"], [])
            self.assertIsNone(manifest["yabasanshiro_variants"]["source"])

    def test_output_directory_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            output_dir = root / "overlay"
            output_dir.mkdir()
            with self.assertRaisesRegex(OverlayError, "already exists"):
                trusted_build_overlay(candidate_dir, output_dir)
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_repository_head_and_run_identity_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            with self.assertRaisesRegex(OverlayError, "repository head differs"):
                trusted_build_overlay(
                    candidate_dir,
                    root / "wrong-head",
                    expected_repository_head="f" * 40,
                )
            with self.assertRaisesRegex(OverlayError, "candidate_id is not bound"):
                trusted_build_overlay(
                    candidate_dir,
                    root / "wrong-run",
                    expected_run_id="999",
                )

    def test_self_consistent_candidate_requires_trusted_repository_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forged_repository = repository_facts()
            forged_repository["catalog"]["file_sha256"] = "f" * 64
            candidate_dir = write_candidate(
                root,
                {"alpha": default_asset_members("alpha")},
                repository=forged_repository,
            )

            def reject_forged(_plan: dict) -> dict:
                raise release_overlay.PipelineError(
                    "plan differs from trusted repository"
                )

            with self.assertRaisesRegex(OverlayError, "trusted repository"):
                trusted_build_overlay(
                    candidate_dir,
                    root / "overlay",
                    trusted_plan_validator=reject_forged,
                )

    def test_swap_after_deep_validation_is_rejected_before_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            original_validator = release_overlay.validate_sealed_candidate_directory

            def validate_then_swap(**kwargs):
                candidate = original_validator(**kwargs)
                write_asset_zip(
                    candidate_dir / "assets" / "alpha_libretro.zip",
                    {
                        **default_asset_members("alpha"),
                        "cores/alpha_libretro.so": b"swapped-after-validation",
                    },
                )
                return candidate

            with mock.patch.object(
                release_overlay,
                "validate_sealed_candidate_directory",
                side_effect=validate_then_swap,
            ), self.assertRaisesRegex(OverlayError, "asset .* drift"):
                trusted_build_overlay(candidate_dir, root / "overlay")
            self.assertFalse((root / "overlay").exists())

    def test_asset_snapshot_is_used_for_member_planning_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            original_plan_members = release_overlay._plan_members

            def plan_then_swap(assets):
                destinations = original_plan_members(assets)
                write_asset_zip(
                    candidate_dir / "assets" / "alpha_libretro.zip",
                    {
                        **default_asset_members("alpha"),
                        "cores/alpha_libretro.so": b"swapped-after-snapshot",
                    },
                )
                return destinations

            with mock.patch.object(
                release_overlay, "_plan_members", side_effect=plan_then_swap
            ):
                manifest = trusted_build_overlay(candidate_dir, root / "overlay")
            overlay_path = root / "overlay" / manifest["overlay"]["path"]
            with zipfile.ZipFile(overlay_path) as archive:
                self.assertEqual(
                    archive.read("RetroArch/.retroarch/cores/alpha_libretro.so"),
                    b"armhf-alpha",
                )


if __name__ == "__main__":
    unittest.main()
