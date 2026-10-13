"""Standalone (non-libretro) emulators: render, build and check their recipes.

A recipe in manifests/standalone-builds.json builds one emulator variant from pinned
sources in a pinned toolchain image (docs/standalone.md). There is no load test (a
standalone emulator needs a display): after a build, every shipped ELF's NEEDED list
is checked against the recipe, and every file against the hashes of what spruce ships."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import build, recipe
from .catalog import COMMIT, Repo, load_json

MANIFEST = "manifests/standalone-builds.json"
SOURCE = "/src"
BUILD_DIR = "/tmp/standalone-build"
DIST = "/output/dist"
RECIPE_MOUNT = "/recipe"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMITTER = re.compile(r"^(.+) <([^<>]+)>$")
STRIP_MODES = ("-s", "--strip-unneeded")
# readelf -d lines -> "file<TAB>needed|soname<TAB>value"
ELF_FIELDS = r'''/\((NEEDED|SONAME)\)/ { match($0, /\[.*\]/); kind = ($2 ~ /NEEDED/) ? "needed" : "soname"; print file "\t" kind "\t" substr($0, RSTART + 1, RLENGTH - 2) }'''


def load(repo: Repo) -> dict:
    """Every build with its `extends` chain applied, abstract bases included."""
    raw = load_json(repo.root / MANIFEST)["builds"]
    return {name: resolve(raw, name) for name in raw}


def resolve(raw: dict, name: str, chain: tuple = ()) -> dict:
    """A build's fields over its parent's, top-level keys replaced whole."""
    if name in chain:
        raise ValueError(f"standalone {name}: extends loop through {' -> '.join(chain)}")
    spec = raw[name]
    parent = spec.get("extends")
    if parent is None:
        return dict(spec)
    if parent not in raw:
        raise ValueError(f"standalone {name}: extends unknown build {parent}")
    merged = resolve(raw, parent, chain + (name,))
    merged.pop("abstract", None)
    merged.update({key: value for key, value in spec.items() if key != "extends"})
    return merged


def buildable(builds: dict) -> dict:
    return {name: spec for name, spec in builds.items() if not spec.get("abstract")}


def check(repo: Repo) -> list[str]:
    try:
        builds = load(repo)
    except ValueError as error:
        return [str(error)]
    return [f"standalone {name}: {problem}" for name, spec in buildable(builds).items()
            for problem in spec_problems(repo, spec)]


def spec_problems(repo: Repo, spec: dict) -> list[str]:
    problems = []
    sources = [spec.get("source") or {}] + list(spec.get("extra_sources", []))
    for source in sources:
        if not COMMIT.match(source.get("commit", "")) or not COMMIT.match(source.get("tree", "")):
            problems.append(f"source {source.get('url')}: commit and tree must be full ids")
    for extra in spec.get("extra_sources", []):
        if not str(extra.get("path", "")).startswith("/"):
            problems.append(f"extra source {extra.get('url')}: path must be absolute")
    if "cmake" in spec and spec.get("source", {}).get("path", SOURCE) != SOURCE:
        problems.append(f"the cmake driver builds {SOURCE}; give steps for another source path")
    if spec.get("toolchain") not in repo.toolchains:
        problems.append(f"unknown toolchain {spec.get('toolchain')}")
    if not isinstance(spec.get("source_date_epoch"), int):
        problems.append("source_date_epoch must be an integer")
    if ("cmake" in spec) == ("steps" in spec):
        problems.append("give exactly one of cmake and steps")
    for item in spec.get("downloads", []):
        if not SHA256.match(item.get("sha256", "")) or not str(item.get("path", "")).startswith("/"):
            problems.append(f"download {item.get('url')}: needs a sha256 and an absolute path")
    for patch in spec.get("patches", []):
        kinds = [kind for kind in ("diff", "script", "mail") if kind in patch]
        if len(kinds) != 1:
            problems.append(f"patch {patch}: give exactly one of diff, script and mail")
        elif not (repo.root / patch[kinds[0]]).is_file():
            problems.append(f"patch {patch[kinds[0]]} does not exist")
        elif kinds == ["mail"] and not (COMMIT.match(patch.get("commit", "")) and COMMITTER.match(patch.get("committer", ""))):
            problems.append(f"mail {patch['mail']}: needs the full commit it recreates and a committer \"Name <email>\"")
    files = spec.get("output", {}).get("files", [])
    if not files:
        problems.append("output.files is empty")
    for item in files:
        if not item.get("from") or not item.get("to") or item["to"].startswith("/"):
            problems.append(f"output file {item}: needs from and a relative to")
        if item.get("strip") not in (None, *STRIP_MODES):
            problems.append(f"output file {item.get('to')}: strip must be one of {STRIP_MODES}")
    targets = [item.get("to", "") for item in files]
    for path in spec.get("shipped", {}).get("files", {}):
        if not any(path == to or path.startswith(to.rstrip("/") + "/") for to in targets):
            problems.append(f"shipped file {path} is not an output")
    for path, digest in spec.get("shipped", {}).get("files", {}).items():
        if not SHA256.match(digest):
            problems.append(f"shipped file {path}: sha256 must be 64 hex digits")
    needed = spec.get("needed", {})
    overlap = set(needed.get("device", [])) & set(needed.get("forbidden", []))
    if overlap:
        problems.append(f"both device and forbidden: {' '.join(sorted(overlap))}")
    return problems


def clone(source: dict, path: str) -> list[str]:
    q = recipe.q
    lines = [f"git clone --filter=blob:none --no-checkout {q(source['url'])} {q(path)}",
             f"git -C {q(path)} checkout -q {source['commit']}",
             f"test \"$(git -C {q(path)} rev-parse 'HEAD^{{tree}}')\" = {source['tree']}"]
    if source.get("submodules"):
        lines.append(f"git -C {q(path)} submodule update --init --recursive --depth 1 -q")
    return lines


def download(item: dict) -> list[str]:
    q = recipe.q
    path = q(item["path"])
    # Some hosts refuse Python's default User-Agent (HTTP 406).
    fetch = ('import shutil, sys, urllib.request; request = urllib.request.Request(sys.argv[1], '
             'headers={"User-Agent": "cores-experimental"}); '
             'shutil.copyfileobj(urllib.request.urlopen(request), open(sys.argv[2], "wb"))')
    # The A30 toolchain's python3, first on that image's PATH, has no ssl module.
    return [f"mkdir -p \"$(dirname {path})\"",
            f"PATH=/usr/bin:$PATH python3 -c {q(fetch)} {q(item['url'])} {path}",
            f"echo {q(item['sha256'] + '  ' + item['path'])} | sha256sum -c -"]


def apply_patch(patch: dict, source: str) -> list[str]:
    q = recipe.q
    target = q(patch.get("dir", source))
    if "diff" in patch:
        path = q(f"{RECIPE_MOUNT}/{patch['diff']}")
        return [f"git -C {target} apply --check {path}", f"git -C {target} apply {path}"]
    if "mail" in patch:
        # git am recreates the mails' commits; with the original committer and dates they get their ids back.
        name, email = COMMITTER.match(patch["committer"]).groups()
        path = q(f"{RECIPE_MOUNT}/{patch['mail']}")
        return [f"GIT_COMMITTER_NAME={q(name)} GIT_COMMITTER_EMAIL={q(email)} "
                f"git -C {target} am -q --committer-date-is-author-date {path}",
                f"test \"$(git -C {target} rev-parse HEAD)\" = {patch['commit']}"]
    return [f"(cd {target} && python3 {q(RECIPE_MOUNT + '/' + patch['script'])})"]


def configure(spec: dict, cross: str) -> list[str]:
    cmake = spec["cmake"]
    argv = ["cmake", "-S", SOURCE, "-B", BUILD_DIR, "-G", "Unix Makefiles",
            "-DCMAKE_BUILD_TYPE:STRING=Release", "-DCMAKE_SYSTEM_NAME:STRING=Linux",
            "-DCMAKE_SYSTEM_PROCESSOR:STRING=aarch64"]
    argv += [f"-DCMAKE_{tool}:FILEPATH=/usr/bin/{cross}-{name}" for tool, name in
             (("C_COMPILER", "gcc"), ("CXX_COMPILER", "g++"), ("AR", "ar"), ("RANLIB", "ranlib"), ("STRIP", "strip"))]
    argv += [f"-D{name}:STRING={value}" for name, value in cmake["cross_defines"].items()]
    argv += [f"-D{name}={value}" for name, value in cmake["defines"].items()]
    return argv


def collect(output: dict, cross: str) -> list[str]:
    """Copy the outputs into dist/, then list every ELF's SONAME and NEEDED entries."""
    q = recipe.q
    lines = [f"mkdir -p {DIST}"]
    for item in output["files"]:
        target = q(f"{DIST}/{item['to']}")
        if item.get("dir"):
            lines += [f"mkdir -p \"$(dirname {target})\"", f"cp -a {q(item['from'])} {target}"]
            continue
        lines.append(f"install -D -m {item.get('mode', '0755')} {q(item['from'])} {target}")
        if item.get("strip"):
            lines.append(f"{cross}-strip {item['strip']} {target}")
    lines += [
        f"(cd {DIST} && find . -type f | LC_ALL=C sort | while read -r file; do",
        f"  if {cross}-readelf -h \"$file\" >/dev/null 2>&1; then",
        f"    {cross}-readelf -d \"$file\" | awk -v file=\"${{file#./}}\" {q(ELF_FIELDS)}",
        "  fi",
        "done) > /output/elf.tsv",
    ]
    return lines


def render(name: str, spec: dict, toolchain: dict) -> recipe.Script:
    q = recipe.q
    cross = toolchain["host_cc"]
    source = spec["source"].get("path", SOURCE)
    lines = ["set -euo pipefail",
             "trap 'chown -R \"$OUTPUT_UID:$OUTPUT_GID\" /output' EXIT",
             f"unset {recipe.SCRUBBED}",
             f"export SOURCE_DATE_EPOCH={int(spec['source_date_epoch'])}",
             "export LC_ALL=C.UTF-8",
             "umask 022",
             f"export CROSS={q(cross)} SOURCE={q(source)} BUILD_DIR={BUILD_DIR} DIST={DIST}"]
    lines += [f"export {key}={q(value)}" for key, value in spec.get("env", {}).items()]
    lines += clone(spec["source"], source)
    lines.append(f"git -C {q(source)} rev-parse HEAD > /output/source-commit.txt")
    for extra in spec.get("extra_sources", []):
        lines += clone(extra, extra["path"])
    for item in spec.get("downloads", []):
        lines += download(item)
    for patch in spec.get("patches", []):
        lines += apply_patch(patch, source)
    lines.append(f"cd {q(source)}")
    if "cmake" in spec:
        lines += [" ".join(q(part) for part in configure(spec, cross)),
                  f"cmake --build {BUILD_DIR} -j \"$(nproc)\" --target {q(spec['cmake']['target'])}"]
    else:
        lines += list(spec["steps"])
    lines += collect(spec["output"], cross)
    mounts = [("patches", f"{RECIPE_MOUNT}/patches")] if spec.get("patches") else []
    return recipe.Script("\n".join(lines) + "\n", mounts)


def read_elf(path: Path) -> dict:
    """elf.tsv as {file: {"soname": str | None, "needed": [str]}}."""
    elf: dict = {}
    if not path.exists():
        return elf
    for line in path.read_text().splitlines():
        file, kind, value = line.split("\t")
        entry = elf.setdefault(file, {"soname": None, "needed": []})
        if kind == "soname":
            entry["soname"] = value
        else:
            entry["needed"].append(value)
    return elf


def contract_problems(spec: dict, elf: dict, shipped_names: frozenset = frozenset()) -> list[str]:
    """What the shipped ELFs need that neither the device nor the build provides."""
    needed = spec.get("needed", {})
    forbidden = set(needed.get("forbidden", []))
    provided = set(needed.get("device", [])) | set(shipped_names)
    provided |= {entry["soname"] for entry in elf.values() if entry["soname"]}
    provided |= {Path(file).name for file in elf}
    users: dict[str, list[str]] = {}
    for file, entry in elf.items():
        for lib in entry["needed"]:
            users.setdefault(lib, []).append(file)
    problems = []
    for lib in sorted(users):
        if lib in forbidden:
            problems.append(f"{lib} is forbidden (needed by {', '.join(users[lib])})")
        elif lib not in provided:
            problems.append(f"{lib} is neither on the device nor shipped (needed by {', '.join(users[lib])})")
    return problems


def inventory(dist: Path) -> dict:
    files = {}
    if dist.is_dir():
        for path in sorted(dist.rglob("*")):
            relative = path.relative_to(dist).as_posix()
            if path.is_symlink():
                files[relative] = {"link": str(path.readlink())}
            elif path.is_file():
                files[relative] = {"sha256": build.sha256(path), "size": path.stat().st_size}
    return files


def compare_shipped(spec: dict, files: dict) -> dict:
    result = {}
    for path, digest in spec.get("shipped", {}).get("files", {}).items():
        entry = files.get(path)
        result[path] = "missing" if not entry else "match" if entry.get("sha256") == digest else "differs"
    return result


def build_one(repo: Repo, name: str, out: Path) -> dict:
    spec = load(repo)[name]
    if spec.get("abstract"):
        raise RuntimeError(f"{name} is an abstract base, not a build")
    toolchain = repo.toolchains[spec["toolchain"]]
    if not build.image_present(toolchain["image_id"]):
        raise RuntimeError(f"toolchain image {spec['toolchain']} is not loaded")
    target = out / name
    exit_code = build.run_container(repo, toolchain["image_id"], render(name, spec, toolchain), target)
    files = inventory(target / "dist")
    elf = read_elf(target / "elf.tsv")
    problems = [f"{item['to']} was not produced" for item in spec["output"]["files"]
                if item["to"] not in files and not any(path.startswith(item["to"].rstrip("/") + "/") for path in files)]
    if exit_code == 0 and not problems:
        problems += contract_problems(spec, elf, frozenset(Path(path).name for path in files))
    record = {"name": name, "source": spec["source"], "extra_sources": spec.get("extra_sources", []),
              "downloads": spec.get("downloads", []), "toolchain": toolchain["image_id"],
              "exit_code": exit_code, "files": files, "elf": elf, "problems": problems,
              "shipped": compare_shipped(spec, files)}
    record["status"] = "built" if exit_code == 0 and not problems else "failed"
    (target / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
