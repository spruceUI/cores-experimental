#!/usr/bin/env python3
"""Tracked per-core evidence index: promotion-derived bindings in one document.

Every value here is DERIVED from promoted disk state (pin-set, compatibility
manifest, E2E records, build records, channel-independent stores) — never
hand-transcribed. The index is written at promotion time and committed with
the promotion, so review happens on the same diff; tests and tools read
expectations from it instead of embedding copied literals.

Reviewed CONTRACT pins (compile counts, invocation digests, link options,
caveat tokens) deliberately stay hand-written in the per-core contract
modules and tests — this index only covers the mechanical bindings.

Usage:
  python3 scripts/evidence_index.py compose --core handy          # print
  python3 scripts/evidence_index.py write --core handy            # write one
  python3 scripts/evidence_index.py backfill --all                # write all
  python3 scripts/evidence_index.py verify --all                  # regenerate + compare
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INDEX_DIR = ROOT / "pins" / "evidence"


def _snapshot_bytes(path: Path) -> tuple[bytes, str]:
    raw = path.read_bytes()
    return raw, hashlib.sha256(raw).hexdigest()


def _snapshot_json(path: Path) -> tuple[dict[str, Any], str]:
    raw, digest = _snapshot_bytes(path)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value, digest


def _load(path: Path) -> dict[str, Any]:
    value, _file_sha256 = _snapshot_json(path)
    return value


def compose(core: str) -> dict[str, Any]:
    compatibility_path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    compatibility, compatibility_file_sha256 = _snapshot_json(compatibility_path)
    pin_path = ROOT / compatibility["golden_source"]
    pin, _pin_file_sha256 = _snapshot_json(pin_path)
    semantic_id = pin["pin_id"]

    selection = pin["cores"][core]["selection"]
    selected_run = selection["e2e"]["run_id"]
    reproduction_run = Path(compatibility["reproduction_run"]).parts[-2]

    runs: dict[str, Any] = {}
    run_documents: dict[str, dict[str, Any]] = {}
    selected_records: dict[str, dict[str, Any]] = {}
    for role, run_id in (("selected", selected_run), ("reproduction", reproduction_run)):
        e2e_path = ROOT / ".local-e2e" / "runs" / run_id / "e2e-record.json"
        e2e, e2e_file_sha256 = _snapshot_json(e2e_path)
        run_documents[role] = e2e
        builds = {}
        for build in e2e["builds"]:
            record_path = ROOT / build["record"]
            record, record_file_sha256 = _snapshot_json(record_path)
            log_path = record_path.parent / record["build"]["log"]
            log_bytes, log_file_sha256 = _snapshot_bytes(log_path)
            if role == "selected":
                selected_records[build["architecture"]] = record
            builds[build["architecture"]] = {
                "record_sha256": record_file_sha256,
                "log_sha256": log_file_sha256,
                "log_size": len(log_bytes),
                "repository_head": record["recipe"]["repository_head"],
                "repository_dirty": record["recipe"]["repository_dirty"],
            }
        runs[role] = {
            "run_id": run_id,
            "e2e_file_sha256": e2e_file_sha256,
            "e2e_content_sha256": e2e["content_sha256"],
            "builds": builds,
        }

    targets: dict[str, Any] = {}
    selected_e2e = run_documents["selected"]
    for build in selected_e2e["builds"]:
        architecture = build["architecture"]
        record = selected_records[architecture]
        toolchain = record["toolchain"]
        archive = toolchain["archive_provenance"]["archive"]
        targets[architecture] = {
            "artifact_sha256": record["artifact"]["sha256"],
            "artifact_size": record["artifact"]["size"],
            "image_id": toolchain["image_id"],
            "toolchain_archive_sha256": archive["sha256"],
            "toolchain_archive_size": archive["size"],
        }

    package = selection["package"]
    return {
        "$schema": "../../manifests/evidence-index.schema.json",
        "schema_version": 1,
        "core_id": core,
        "semantic_id": semantic_id,
        "pin_path": str(pin_path.relative_to(ROOT)),
        "source_set_path": f"pins/source-sets/{semantic_id}.json",
        "source_commit": compatibility["source_commit"],
        "selection_sha256": selection["selection_sha256"],
        "package": {
            "sha256": package["sha256"],
            "size": package.get("size"),
        },
        "compatibility": {
            "file_sha256": compatibility_file_sha256,
            "content_sha256": compatibility["content_sha256"],
        },
        "runs": runs,
        "targets": targets,
        "local_only_evidence": True,
        "publication": "disabled",
    }


def index_path(core: str) -> Path:
    return INDEX_DIR / f"{core}.json"


def write(core: str) -> Path:
    document = compose(core)
    path = index_path(core)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def catalog_cores() -> list[str]:
    catalog = _load(ROOT / "manifests" / "core-builds.json")
    return sorted(catalog["cores"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["compose", "write", "backfill", "verify"])
    parser.add_argument("--core", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.command == "compose":
        for core in args.core:
            print(json.dumps(compose(core), indent=2, sort_keys=True))
        return 0

    cores = catalog_cores() if args.all else args.core
    if not cores:
        parser.error("select cores with --core or --all")

    if args.command in ("write", "backfill"):
        for core in cores:
            path = write(core)
            print(f"wrote {path.relative_to(ROOT)}")
        return 0

    if args.command == "verify":
        bad = []
        for core in cores:
            path = index_path(core)
            if not path.exists():
                bad.append((core, "missing index"))
                continue
            if _load(path) != compose(core):
                bad.append((core, "index differs from disk-derived evidence"))
        for core, reason in bad:
            print(f"FAIL {core}: {reason}")
        print(f"{len(cores) - len(bad)}/{len(cores)} indexes verified")
        return 1 if bad else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
