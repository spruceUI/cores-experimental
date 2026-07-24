#!/usr/bin/env python3
"""One-command read-only verification sweep for promoted cores.

For each selected core this discovers the promoted surfaces from the core id
alone and runs the full static verification chain that previously required
six hand-assembled commands per core:

  1. validate-golden          .local-e2e/nightlies/<sid>/golden.json
  2. validate-pin-set         pins/core-sets/<sid>.json  (--verify-store --verify-sources)
  3. profile_registry report  pins/source-sets/<sid>.json
  4. validate-release         .local-e2e/releases/<sid>
  5. validate-channel x3      nightly / pinned / release

The sweep is read-only: it never writes, promotes, or repoints anything.
Local tier only — rebuild reproducibility is proven exclusively by the
GitHub Actions release-candidate roster.

Usage:
  python3 scripts/verify_core.py --core handy [--core gambatte ...]
  python3 scripts/verify_core.py --all [--skip-store] [--jobs N]

Exit code 0 only when every selected core passes every step.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def discover_sid(core: str) -> str:
    matches = sorted((ROOT / "pins" / "core-sets").glob(f"{core}-*.json"))
    matches = [m for m in matches if m.stem.rsplit("-", 2)[0] == core]
    if len(matches) != 1:
        raise SystemExit(
            f"error: expected exactly one pin-set for {core!r}, found "
            f"{[m.name for m in matches]}"
        )
    return matches[0].stem


def run_step(label: str, argv: list[str]) -> tuple[str, bool, str]:
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    detail = (proc.stderr or proc.stdout).strip().splitlines()
    return label, proc.returncode == 0, detail[-1] if detail else ""


def verify_core(core: str, skip_store: bool) -> tuple[str, list[tuple[str, bool, str]]]:
    sid = discover_sid(core)
    store = [] if skip_store else ["--verify-store"]
    pipeline = [PYTHON, "scripts/core_pipeline.py"]
    steps = [
        ("golden", pipeline + [
            "validate-golden",
            "--golden", f".local-e2e/nightlies/{sid}/golden.json", *store,
        ]),
        ("pin-set", pipeline + [
            "validate-pin-set",
            "--pin-set", f"pins/core-sets/{sid}.json",
            *store, "--verify-sources",
        ]),
        ("source-registry", [PYTHON, "scripts/profile_registry.py", "report",
                             "--source-set", f"pins/source-sets/{sid}.json"]),
        ("release", pipeline + [
            "validate-release",
            "--pin-set", f"pins/core-sets/{sid}.json",
            "--release", f".local-e2e/releases/{sid}", *store,
        ]),
    ]
    steps += [
        (f"channel-{channel}", pipeline + [
            "validate-channel", "--channel", channel, "--core", core,
        ])
        for channel in ("nightly", "pinned", "release")
    ]
    return sid, [run_step(label, argv) for label, argv in steps]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--skip-store", action="store_true",
                        help="skip --verify-store (no local archive store)")
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()

    if args.all == bool(args.core):
        parser.error("select cores with --core ... or --all (not both, not neither)")
    if args.all:
        catalog = json.loads((ROOT / "manifests" / "core-builds.json").read_text())
        cores = sorted(catalog["cores"])
    else:
        cores = args.core

    failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(verify_core, core, args.skip_store): core
                   for core in cores}
        for future in concurrent.futures.as_completed(futures):
            core = futures[future]
            sid, results = future.result()
            bad = [(label, tail) for label, ok, tail in results if not ok]
            if bad:
                failures += 1
                print(f"FAIL {core} ({sid})")
                for label, tail in bad:
                    print(f"  {label}: {tail}")
            else:
                print(f"ok   {core} ({sid})")
    print(f"{len(cores) - failures}/{len(cores)} cores verified")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
