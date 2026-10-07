"""Turn build records into device bundles and release freeze manifests."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

DEVICE_DIRS = {"arm64": "RetroArch/.retroarch/cores64", "armhf": "RetroArch/.retroarch/cores"}
INFO_DIR = "RetroArch/.retroarch/info"
# spruce's Saturn config selects these names on TrimUI devices.
ALIASES = {("yabasanshiro", "arm64"): ("yabasanshiro_a133p_libretro.so",
                                         "yabasanshiro_smartpros_libretro.so")}


def load_records(results: Path) -> list[dict]:
    records = []
    for path in sorted(results.glob("*/*/record.json")):
        record = json.loads(path.read_text())
        record["_dir"] = str(path.parent)
        records.append(record)
    return records


def bundle(results: Path, out: Path) -> dict:
    """One directory per board+profile, laid out like the device's SD card."""
    summary: dict[str, dict] = {}
    for record in load_records(results):
        variant = record["variant"]
        for board in variant["boards"]:
            key = f"{board}-{variant['profile']}"
            entry = summary.setdefault(key, {})
            entry.setdefault(record["core"], {})[variant["arch"]] = {
                "status": record["status"],
                "variant": variant["name"],
                "sha256": (record["artifact"] or {}).get("sha256"),
            }
            if record["status"] not in ("usable", "built"):
                continue
            root = out / key
            source = Path(record["_dir"])
            target = root / DEVICE_DIRS[variant["arch"]]
            target.mkdir(parents=True, exist_ok=True)
            artifact = record["artifact"]["name"]
            shutil.copy2(source / artifact, target / artifact)
            for alias in ALIASES.get((record["core"], variant["arch"]), ()):
                shutil.copy2(source / artifact, target / alias)
            if record["metadata"]:
                (root / INFO_DIR).mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / record["metadata"]["name"], root / INFO_DIR / record["metadata"]["name"])
    for key, cores in summary.items():
        root = out / key
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(json.dumps(cores, indent=2, sort_keys=True) + "\n")
    return summary


def freeze(results: Path, name: str, repository_commit: str, check: Path | None = None) -> tuple[dict, list[str]]:
    """Build a freeze manifest; with `check`, compare against a committed one."""
    problems = []
    builds = []
    for record in load_records(results):
        label = f"{record['core']} {record['variant']['name']}"
        if record["status"] not in ("usable", "built"):
            problems.append(f"{label}: {record['status']}")
            continue
        if "reproducible" not in record:
            problems.append(f"{label}: built once; a freeze needs --repeat 2")
        elif not record["reproducible"]:
            problems.append(f"{label}: second build differs ({record.get('repeat_sha256')})")
        builds.append({
            "core": record["core"],
            "commit": record["source"]["commit"],
            "variant": record["variant"]["name"],
            "boards": record["variant"]["boards"],
            "flags": record["variant"]["flags"],
            "image_id": record["toolchain"]["image_id"],
            "artifact": record["artifact"],
            "metadata": record["metadata"],
        })
    manifest = {
        "release": name,
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository_commit": repository_commit,
        "builds": sorted(builds, key=lambda b: (b["core"], b["variant"])),
    }
    if check is not None:
        expected = {(b["core"], b["variant"]): b for b in json.loads(check.read_text())["builds"]}
        actual = {(b["core"], b["variant"]): b for b in manifest["builds"]}
        for key in sorted(expected.keys() | actual.keys()):
            want, got = expected.get(key), actual.get(key)
            if want is None or got is None:
                problems.append(f"{' '.join(key)}: {'not in the frozen release' if want is None else 'not rebuilt'}")
            elif want["artifact"]["sha256"] != got["artifact"]["sha256"]:
                problems.append(f"{' '.join(key)}: rebuilt bytes differ from the frozen release")
    return manifest, problems
