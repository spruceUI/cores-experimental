from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.release_overlay import (
    OverlayError,
    YABASANSHIRO_SOURCE,
    YABASANSHIRO_VARIANTS,
    build_overlay,
)


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
) -> Path:
    candidate_dir = root / "candidate"
    assets = []
    for core_id, members in sorted(asset_members.items()):
        asset_path = candidate_dir / "assets" / f"{core_id}_libretro.zip"
        write_asset_zip(asset_path, members)
        data = asset_path.read_bytes()
        assets.append(
            {
                "core_id": core_id,
                "path": f"assets/{core_id}_libretro.zip",
                "sha256": sha256(data),
                "size": len(data),
            }
        )
    candidate = {
        "candidate_id": "cand-test-v1",
        "result": "sealed",
        "publication": "disabled",
        "local_only": True,
        "schema_version": 1,
        "content_sha256": "0" * 64,
        "asset_set_sha256": "1" * 64,
        "runner": {"profile": "local"},
        "assets": assets,
        "summary": {"asset_count": len(assets)},
    }
    if mutate:
        candidate.update(mutate)
    (candidate_dir / "candidate.json").write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return candidate_dir


class ReleaseOverlayTests(unittest.TestCase):
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
            manifest = build_overlay(candidate_dir, output_dir)

            overlay_path = output_dir / "cand-test-v1-file-overlay.zip"
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
            first = build_overlay(candidate_dir, root / "first")
            second = build_overlay(candidate_dir, root / "second")
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
            with self.assertRaisesRegex(OverlayError, "drift"):
                build_overlay(candidate_dir, output_dir)
            self.assertFalse(output_dir.exists())

    def test_unexpected_member_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            members = default_asset_members("alpha")
            members["cores/../escape.so"] = b"evil"
            candidate_dir = write_candidate(root, {"alpha": members})
            output_dir = root / "overlay"
            with self.assertRaisesRegex(OverlayError, "unexpected member"):
                build_overlay(candidate_dir, output_dir)
            self.assertFalse(output_dir.exists())

    def test_unsealed_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root,
                {"alpha": default_asset_members("alpha")},
                mutate={"result": "pending"},
            )
            with self.assertRaisesRegex(OverlayError, "not sealed"):
                build_overlay(candidate_dir, root / "overlay")

    def test_missing_yabasanshiro_is_recorded_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate_dir = write_candidate(
                root, {"alpha": default_asset_members("alpha")}
            )
            manifest = build_overlay(candidate_dir, root / "overlay")
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
                build_overlay(candidate_dir, output_dir)
            self.assertEqual(list(output_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
