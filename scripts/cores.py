#!/usr/bin/env python3
"""Build libretro cores for spruce devices in pinned toolchain images.

  check                                  validate the catalog and registries
  list                                   list cores, drivers and targets
  script CORE ARCH [variant options]     print the container build script
  plan   [selection]                     list the builds a selection expands to
  build  --core CORE [selection]         build one core's variants into --out
  bump   CORE --commit SHA               move a core to a new commit, keeping the old as known-good
  toolchains --dir DIR [--names ...]     verify and load the image archives
  bundle --results DIR --out DIR         device-layout bundles per board+profile
  freeze --results DIR --name NAME       write or check a release freeze manifest
  summary --results DIR                  markdown status table
  standalone list|script|build [NAME]    standalone emulators (docs/standalone.md)

Selection options: --cores, --boards, --profiles (each 'all' or a list),
--flags (extra GCC flags), --arch (limit universal builds to one ABI),
--runtime (shared, static or both: how the C++ runtime is linked), --strip.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from corebuild import build, recipe, release, standalone
from corebuild.catalog import COMMIT, Repo
from corebuild.variants import RUNTIMES, Variant, parse_flags, plan


def selection_args(parser: argparse.ArgumentParser, cores: bool = True) -> None:
    if cores:
        parser.add_argument("--cores", default="all")
    parser.add_argument("--boards", default="universal")
    parser.add_argument("--profiles", default="release")
    parser.add_argument("--flags", default="")
    parser.add_argument("--arch", choices=("arm64", "armhf"))
    parser.add_argument("--runtime", default="shared", help="shared, static, or both as 'shared,static'")
    parser.add_argument("--strip", action="store_true", help="strip symbols and debug info before the load test")


def expand(repo: Repo, args: argparse.Namespace, core: str) -> list[Variant]:
    boards = repo.select_from(args.boards, repo.boards, "boards")
    profiles = repo.select_from(args.profiles, repo.profiles, "profiles")
    runtimes = repo.select_from(args.runtime, RUNTIMES, "runtimes")
    return plan(repo.cores[core], repo.boards, repo.profiles, boards, profiles,
                parse_flags(args.flags), args.arch, tuple(runtimes), args.strip)


def cmd_check(repo: Repo, args) -> int:
    errors = repo.check() + standalone.check(repo)
    for error in errors:
        print(error)
    print(f"{len(repo.cores)} cores, {len(repo.boards)} boards, {len(repo.profiles)} profiles: "
          + ("ok" if not errors else f"{len(errors)} problems"))
    return 1 if errors else 0


def cmd_list(repo: Repo, args) -> int:
    for core, spec in sorted(repo.cores.items()):
        print(f"{core:36} {spec['build']['driver']:15} {' '.join(spec['targets'])}")
    return 0


def cmd_script(repo: Repo, args) -> int:
    variants = [v for v in expand(repo, args, args.core) if v.arch == args.arch_name]
    if len(variants) != 1:
        print("the options must select exactly one build for that arch", file=sys.stderr)
        return 2
    script = recipe.render(args.core, repo.cores[args.core], args.arch_name, variants[0])
    print(script.text, end="")
    for host, container in script.mounts:
        print(f"# mount {host} -> {container}")
    return 0


def cmd_plan(repo: Repo, args) -> int:
    rows = []
    for core in repo.select(args.cores):
        variants = expand(repo, args, core)
        if variants:
            toolchains = sorted({recipe.toolchain_for(repo.cores[core], v.arch) for v in variants})
            rows.append({"core": core, "toolchains": " ".join(toolchains),
                         "builds": [v.describe() for v in variants]})
    if args.github:
        if not rows:
            print("the selection has no builds", file=sys.stderr)
            return 2
        if len(rows) > 256:
            print("more than 256 cores selected; GitHub caps a matrix at 256 jobs", file=sys.stderr)
            return 2
        print(json.dumps({"include": [{"core": r["core"], "toolchains": r["toolchains"]} for r in rows]}))
    else:
        for row in rows:
            for item in row["builds"]:
                print(f"{row['core']:36} {item['name']:40} {','.join(item['boards'])}")
        print(f"{sum(len(r['builds']) for r in rows)} builds for {len(rows)} cores")
    return 0


def cmd_build(repo: Repo, args) -> int:
    variants = expand(repo, args, args.core)
    if not variants:
        print(f"{args.core}: the selection has no build for this core")
        return 0
    missing = {recipe.toolchain_for(repo.cores[args.core], v.arch) for v in variants}
    missing = [t for t in sorted(missing) if not build.image_present(repo.toolchains[t]["image_id"])]
    if missing:
        print("toolchain images not loaded: " + " ".join(missing)
              + " (scripts/cores.py toolchains --dir <archives>)", file=sys.stderr)
        return 2
    records = build.build_core(repo, args.core, variants, Path(args.out), args.repeat, args.fallback)
    bad = [r for r in records if r["status"] in ("failed", "unusable")
           or (args.repeat > 1 and r.get("reproducible") is False)]
    return 1 if bad else 0


def cmd_bump(repo: Repo, args) -> int:
    spec = repo.cores[args.core]
    old = spec["source"]["commit"]
    if not COMMIT.match(args.commit) or args.commit == old:
        print("--commit must be a new, full 40-character commit id", file=sys.stderr)
        return 2
    spec["known_good"] = json.loads(json.dumps({k: spec[k] for k in ("source", "build", "metadata")}))
    spec["source"]["commit"] = args.commit
    if args.ref:
        spec["source"]["requested_ref"] = args.ref
    repo.save_catalog()
    print(f"{args.core}: {old[:12]} -> {args.commit[:12]}; {old[:12]} kept as known_good")
    if "GIT_DATE=" in json.dumps(spec["build"]):
        print("  GIT_DATE is the commit's date (YYMMDD) and is not derived: update it")
    print(f"  then check it: scripts/cores.py build --core {args.core}")
    return 0


def cmd_toolchains(repo: Repo, args) -> int:
    for name in repo.select_from(args.names, repo.toolchains, "toolchains"):
        toolchain = repo.toolchains[name]
        if build.image_present(toolchain["image_id"]):
            print(f"{name}: already loaded")
            continue
        archive = Path(args.dir) / toolchain["archive"]["name"]
        if not archive.is_file():
            print(f"{name}: missing {archive}", file=sys.stderr)
            return 2
        size, digest = archive.stat().st_size, build.sha256(archive)
        if (size, digest) != (toolchain["archive"]["size"], toolchain["archive"]["sha256"]):
            print(f"{name}: {archive} does not match manifests/toolchains.json", file=sys.stderr)
            return 2
        subprocess.run(f"gunzip -c {shlex.quote(str(archive))} | docker load", shell=True, check=True)
        if not build.image_present(toolchain["image_id"]):
            print(f"{name}: loaded archive did not produce {toolchain['image_id']}", file=sys.stderr)
            return 2
        print(f"{name}: loaded {toolchain['image_id'][:19]}")
    return 0


def cmd_bundle(repo: Repo, args) -> int:
    summary = release.bundle(Path(args.results), Path(args.out))
    for key, cores in sorted(summary.items()):
        good = sum(1 for arches in cores.values() for item in arches.values()
                   if item["status"] in ("usable", "built"))
        total = sum(len(arches) for arches in cores.values())
        print(f"{key:24} {good}/{total} builds")
    return 0


def cmd_freeze(repo: Repo, args) -> int:
    commit = subprocess.run(["git", "-C", str(repo.root), "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    manifest, problems = release.freeze(Path(args.results), args.name, commit,
                                        Path(args.check) if args.check else None)
    if args.out:
        Path(args.out).write_text(json.dumps(manifest, indent=2) + "\n")
    for problem in problems:
        print(problem)
    print(f"{len(manifest['builds'])} frozen builds, {len(problems)} problems")
    return 1 if problems else 0


def cmd_summary(repo: Repo, args) -> int:
    records = release.load_records(Path(args.results))
    if args.annotations:
        # GitHub workflow commands: one warning per fallback, one error per unusable result.
        for r in records:
            where = f"{r['core']} {r['variant']['name']}"
            if r.get("fallback"):
                print(f"::warning::{where}: commit {r['fallback']['from_commit'][:12]} failed; "
                      f"built known-good {r['source']['commit'][:12]}")
            if r["status"] in ("failed", "unusable"):
                print(f"::error::{where}: {r['status']}")
        return 0
    columns = sorted({release.column(r["variant"], b) for r in records for b in r["variant"]["boards"]})
    marks = {"usable": "✅", "built": "☑️", "unusable": "⚠️", "failed": "❌"}
    table: dict[str, dict[str, list[str]]] = {}
    for record in records:
        mark = marks[record["status"]]
        if record.get("reproducible") is False:
            mark += " ≠"
        if record.get("fallback"):
            mark += " ↩"
        calls = record.get("variant_calls")
        if calls is not None and calls["compiles"] == 0:
            mark += " (flags unused)"
        for board in record["variant"]["boards"]:
            table.setdefault(record["core"], {}).setdefault(release.column(record["variant"], board), []).append(mark)
    print("| core | " + " | ".join(columns) + " |")
    print("|---" * (len(columns) + 1) + "|")
    for core in sorted(table):
        print(f"| {core} | " + " | ".join(" ".join(table[core].get(c, ["–"])) for c in columns) + " |")
    print("\n✅ usable (loads and initializes) · ☑️ built, not load-tested · ⚠️ built but does not load · "
          "❌ no artifact · ≠ second build differs · ↩ current commit failed, built the known-good one")
    return 0


def cmd_standalone(repo: Repo, args) -> int:
    builds = standalone.load(repo)
    if args.action == "list":
        for name, spec in builds.items():
            print(f"{name:24} {spec['source']['requested_ref']:16} {spec['output']['spruce_path']}")
        return 0
    if args.name not in builds:
        print(f"unknown standalone build {args.name}; see `standalone list`", file=sys.stderr)
        return 2
    if args.action == "script":
        spec = builds[args.name]
        print(standalone.render(args.name, spec, repo.toolchains[spec["toolchain"]]).text, end="")
        return 0
    record = standalone.build_one(repo, args.name, Path(args.out))
    print(f"{args.name}: {record['status']}" + "".join(f"\n  {p}" for p in record["problems"]))
    return 0 if record["status"] == "built" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("list")
    p = sub.add_parser("script")
    p.add_argument("core")
    p.add_argument("arch_name", choices=("arm64", "armhf"))
    selection_args(p, cores=False)
    p = sub.add_parser("plan")
    selection_args(p)
    p.add_argument("--github", action="store_true", help="print a GitHub Actions matrix")
    p = sub.add_parser("build")
    p.add_argument("--core", required=True)
    selection_args(p, cores=False)
    p.add_argument("--repeat", type=int, default=1, choices=(1, 2))
    p.add_argument("--fallback", action="store_true", help="retry failures at the known-good recipe")
    p.add_argument("--out", default="out")
    p = sub.add_parser("bump")
    p.add_argument("core")
    p.add_argument("--commit", required=True)
    p.add_argument("--ref")
    p = sub.add_parser("toolchains")
    p.add_argument("--dir", required=True)
    p.add_argument("--names", default="all", help="arm64, armhf, rust or all")
    p = sub.add_parser("bundle")
    p.add_argument("--results", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("freeze")
    p.add_argument("--results", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--check")
    p.add_argument("--out")
    p = sub.add_parser("summary")
    p.add_argument("--results", required=True)
    p.add_argument("--annotations", action="store_true", help="print GitHub warning/error lines")
    p = sub.add_parser("standalone")
    p.add_argument("action", choices=("list", "script", "build"))
    p.add_argument("name", nargs="?")
    p.add_argument("--out", default="out")
    args = parser.parse_args(argv)
    repo = Repo()
    if getattr(args, "core", None) and args.core not in repo.cores:
        parser.error(f"unknown core {args.core}")
    try:
        return globals()["cmd_" + args.command](repo, args)
    except (ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
