#!/usr/bin/env python3
"""Convert one sealed release candidate into a device file-overlay archive.

Read-only over the sealed candidate. Every asset ZIP is verified against
``candidate.json`` (existence, size, sha256) and every ZIP member must match
the exact package shape (``cores/<core>_libretro.so``,
``cores64/<core>_libretro.so``, ``<core>_libretro.info``, ``manifest.json``)
before anything is staged. Members are projected into the on-device layout the
spruce launcher already searches:

    cores/    -> RetroArch/.retroarch/cores/
    cores64/  -> RetroArch/.retroarch/cores64/
    *.info    -> RetroArch/.retroarch/info/

When the candidate ships ``cores64/yabasanshiro_libretro.so``, byte-identical
copies are added under the two vendor-variant names the shipped
``Emu/SATURN/config.json`` selects on TrimUI devices, so the overlay is usable
there without a spruceOS change.

The output directory is create-only and holds exactly one deterministic
``<candidate_id>-file-overlay.zip`` (sorted members, fixed 1980 timestamps)
plus ``overlay-manifest.json`` describing the conversion. Nothing here
publishes, fetches, or mutates release state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any
import zipfile


SCHEMA_VERSION = 1
PUBLICATION = "disabled"

CORES_PREFIX = "cores/"
CORES64_PREFIX = "cores64/"
DEVICE_CORES_DIR = "RetroArch/.retroarch/cores"
DEVICE_CORES64_DIR = "RetroArch/.retroarch/cores64"
DEVICE_INFO_DIR = "RetroArch/.retroarch/info"

YABASANSHIRO_SOURCE = f"{DEVICE_CORES64_DIR}/yabasanshiro_libretro.so"
YABASANSHIRO_VARIANTS = (
    f"{DEVICE_CORES64_DIR}/yabasanshiro_a133p_libretro.so",
    f"{DEVICE_CORES64_DIR}/yabasanshiro_smartpros_libretro.so",
)

OVERLAY_MANIFEST_NAME = "overlay-manifest.json"


class OverlayError(Exception):
    """Raised for any invalid, tampered, or unexpected conversion input."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_candidate(candidate_dir: Path) -> dict[str, Any]:
    candidate_path = candidate_dir / "candidate.json"
    try:
        with candidate_path.open("r", encoding="utf-8") as handle:
            candidate = json.load(handle)
    except FileNotFoundError as exc:
        raise OverlayError(f"missing candidate manifest: {candidate_path}") from exc
    except json.JSONDecodeError as exc:
        raise OverlayError(f"invalid JSON in {candidate_path}: {exc}") from exc
    if not isinstance(candidate, dict):
        raise OverlayError("candidate manifest must be a JSON object")

    if candidate.get("result") != "sealed":
        raise OverlayError("candidate is not sealed")
    if candidate.get("publication") != PUBLICATION:
        raise OverlayError("candidate publication must be disabled")
    if candidate.get("local_only") is not True:
        raise OverlayError("candidate must be local-only")
    if candidate.get("schema_version") != 1:
        raise OverlayError("unsupported candidate schema_version")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise OverlayError("candidate_id must be a non-empty string")
    runner = candidate.get("runner")
    if not isinstance(runner, dict) or not isinstance(runner.get("profile"), str):
        raise OverlayError("candidate runner profile is missing")

    assets = candidate.get("assets")
    if not isinstance(assets, list) or not assets:
        raise OverlayError("candidate assets must be a non-empty list")
    summary = candidate.get("summary")
    if not isinstance(summary, dict) or summary.get("asset_count") != len(assets):
        raise OverlayError("candidate summary asset_count does not match assets")
    return candidate


def _verify_assets(
    candidate_dir: Path, assets: list[Any]
) -> list[tuple[str, Path]]:
    verified: list[tuple[str, Path]] = []
    seen_cores: set[str] = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise OverlayError("candidate asset entries must be objects")
        core_id = asset.get("core_id")
        if not isinstance(core_id, str) or not core_id:
            raise OverlayError("asset core_id must be a non-empty string")
        if core_id in seen_cores:
            raise OverlayError(f"duplicate asset core_id: {core_id}")
        seen_cores.add(core_id)
        expected_path = f"assets/{core_id}_libretro.zip"
        if asset.get("path") != expected_path:
            raise OverlayError(f"asset path for {core_id} must be {expected_path}")
        asset_path = candidate_dir / expected_path
        if not asset_path.is_file():
            raise OverlayError(f"missing asset package: {asset_path}")
        size = asset_path.stat().st_size
        if asset.get("size") != size:
            raise OverlayError(f"asset size drift for {core_id}")
        if asset.get("sha256") != _sha256_file(asset_path):
            raise OverlayError(f"asset sha256 drift for {core_id}")
        verified.append((core_id, asset_path))
    return verified


def _plan_members(
    assets: list[tuple[str, Path]]
) -> dict[str, tuple[str, Path, str]]:
    """Map each overlay destination to (core_id, package path, member name)."""

    destinations: dict[str, tuple[str, Path, str]] = {}
    for core_id, asset_path in assets:
        allowed = {
            f"{CORES_PREFIX}{core_id}_libretro.so": f"{DEVICE_CORES_DIR}/{core_id}_libretro.so",
            f"{CORES64_PREFIX}{core_id}_libretro.so": f"{DEVICE_CORES64_DIR}/{core_id}_libretro.so",
            f"{core_id}_libretro.info": f"{DEVICE_INFO_DIR}/{core_id}_libretro.info",
        }
        try:
            with zipfile.ZipFile(asset_path) as archive:
                names = archive.namelist()
        except zipfile.BadZipFile as exc:
            raise OverlayError(f"asset package for {core_id} is not a ZIP") from exc
        staged_so = False
        for name in names:
            if name == "manifest.json":
                continue
            destination = allowed.get(name)
            if destination is None:
                raise OverlayError(
                    f"unexpected member in {core_id} package: {name}"
                )
            if destination in destinations:
                raise OverlayError(f"duplicate overlay destination: {destination}")
            destinations[destination] = (core_id, asset_path, name)
            if name.endswith("_libretro.so"):
                staged_so = True
        if not staged_so:
            raise OverlayError(f"asset package for {core_id} contains no core")
    return destinations


def _add_zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, data)


def build_overlay(candidate_dir: Path, output_dir: Path) -> dict[str, Any]:
    candidate_dir = candidate_dir.resolve()
    candidate = _load_candidate(candidate_dir)
    assets = _verify_assets(candidate_dir, candidate["assets"])
    destinations = _plan_members(assets)

    variants_applied = YABASANSHIRO_SOURCE in destinations
    if variants_applied:
        for variant in YABASANSHIRO_VARIANTS:
            if variant in destinations:
                raise OverlayError(f"duplicate overlay destination: {variant}")
            destinations[variant] = destinations[YABASANSHIRO_SOURCE]

    if output_dir.exists():
        raise OverlayError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    try:
        candidate_id = candidate["candidate_id"]
        overlay_name = f"{candidate_id}-file-overlay.zip"
        overlay_path = output_dir / overlay_name
        members: list[dict[str, Any]] = []
        with zipfile.ZipFile(overlay_path, "w") as archive:
            for destination in sorted(destinations):
                core_id, asset_path, member = destinations[destination]
                with zipfile.ZipFile(asset_path) as package:
                    data = package.read(member)
                _add_zip_entry(archive, destination, data)
                members.append(
                    {
                        "path": destination,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                        "source_core_id": core_id,
                    }
                )

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "publication": PUBLICATION,
            "local_only": True,
            "source": {
                "candidate_id": candidate_id,
                "candidate_content_sha256": candidate.get("content_sha256"),
                "asset_set_sha256": candidate.get("asset_set_sha256"),
                "runner_profile": candidate["runner"]["profile"],
            },
            "overlay": {
                "path": overlay_name,
                "sha256": _sha256_file(overlay_path),
                "size": overlay_path.stat().st_size,
                "member_count": len(members),
            },
            "yabasanshiro_variants": {
                "applied": variants_applied,
                "source": YABASANSHIRO_SOURCE if variants_applied else None,
                "copies": list(YABASANSHIRO_VARIANTS) if variants_applied else [],
            },
            "summary": {
                "core_count": len(assets),
                "cores_armhf": sum(
                    1
                    for path in destinations
                    if path.startswith(f"{DEVICE_CORES_DIR}/")
                ),
                "cores_arm64": sum(
                    1
                    for path in destinations
                    if path.startswith(f"{DEVICE_CORES64_DIR}/")
                ),
                "info_count": sum(
                    1
                    for path in destinations
                    if path.startswith(f"{DEVICE_INFO_DIR}/")
                ),
            },
            "members": members,
        }
        manifest_path = output_dir / OVERLAY_MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except BaseException:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a sealed release candidate into a file-overlay archive"
    )
    parser.add_argument(
        "--candidate-dir",
        required=True,
        type=Path,
        help="sealed candidate directory containing candidate.json",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="create-only output directory for the overlay archive",
    )
    args = parser.parse_args(argv)
    try:
        manifest = build_overlay(args.candidate_dir, args.output_dir)
    except OverlayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "ok",
                "candidate_id": manifest["source"]["candidate_id"],
                "overlay": str(args.output_dir / manifest["overlay"]["path"]),
                "sha256": manifest["overlay"]["sha256"],
                "member_count": manifest["overlay"]["member_count"],
                "yabasanshiro_variants": manifest["yabasanshiro_variants"]["applied"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
