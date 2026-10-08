"""Standalone (non-libretro) emulators: render, build and check one recipe.

A recipe in manifests/standalone-builds.json builds one executable with CMake and
bundles the libraries no device provides. There is no load test (a standalone
emulator needs a display); the check is its NEEDED list against the recipe."""

from __future__ import annotations

import json
from pathlib import Path

from . import build, recipe
from .catalog import COMMIT, Repo, load_json

MANIFEST = "manifests/standalone-builds.json"
SOURCE = "/src"
BUILD_DIR = "/tmp/standalone-build"
PREFIX = "/opt/flycast-standalone-deps-arm64"


def load(repo: Repo) -> dict:
    return load_json(repo.root / MANIFEST)["builds"]


def check(repo: Repo) -> list[str]:
    problems = []
    for name, spec in load(repo).items():
        if not COMMIT.match(spec["source"]["commit"]) or not COMMIT.match(spec["source"]["tree"]):
            problems.append(f"standalone {name}: source.commit and source.tree must be full ids")
        if spec["toolchain"] not in repo.toolchains:
            problems.append(f"standalone {name}: unknown toolchain {spec['toolchain']}")
        overlap = set(spec["needed"]["device"]) & set(spec["needed"]["forbidden"])
        if overlap:
            problems.append(f"standalone {name}: both device and forbidden: {' '.join(sorted(overlap))}")
    return problems


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


def render(name: str, spec: dict, toolchain: dict) -> recipe.Script:
    source, output, cross = spec["source"], spec["output"], toolchain["host_cc"]
    q = recipe.q
    binary, target = q(output["binary"]), q(spec["cmake"]["target"])
    lines = [
        "set -euo pipefail",
        f"export SOURCE_DATE_EPOCH={int(spec['source_date_epoch'])}",
        f"export PKG_CONFIG_PATH={q(PREFIX + '/lib/pkgconfig')}",
        f"export PKG_CONFIG_LIBDIR={q(PREFIX + '/lib/pkgconfig:/usr/lib/' + cross + '/pkgconfig')}",
        "export LC_ALL=C.UTF-8",
        "umask 022",
        f"git clone --filter=blob:none --no-checkout {q(source['url'])} {SOURCE}",
        f"git -C {SOURCE} checkout -q {source['commit']}",
        f"test \"$(git -C {SOURCE} rev-parse 'HEAD^{{tree}}')\" = {source['tree']}",
        f"git -C {SOURCE} submodule update --init --recursive --depth 1 -q",
        f"git -C {SOURCE} rev-parse HEAD > /output/source-commit.txt",
        " ".join(q(part) for part in configure(spec, cross)),
        f"cmake --build {BUILD_DIR} -j \"$(nproc)\" --target {target}",
        f"install -m 0755 {BUILD_DIR}/{target} /output/{binary}",
        f"{cross}-strip -s /output/{binary}",
        "mkdir -p /output/lib",
    ]
    for soname in output["bundled_libraries"]:
        lines += [f"cp -L {PREFIX}/lib/{q(soname)} /output/lib/{q(soname)}",
                  f"{cross}-strip -s /output/lib/{q(soname)}"]
    lines += [
        f"{cross}-readelf -d /output/{binary} | sed -n 's/.*(NEEDED).*\\[\\(.*\\)\\]/\\1/p' > /output/needed.txt",
        f"for so in /output/lib/*; do {cross}-readelf -d \"$so\" | sed -n 's/.*(NEEDED).*\\[\\(.*\\)\\]/\\1/p'; done > /output/lib-needed.txt",
        "chown -R \"$OUTPUT_UID:$OUTPUT_GID\" /output",
    ]
    return recipe.Script("\n".join(lines) + "\n")


def contract_problems(spec: dict, needed: list[str], lib_needed: list[str]) -> list[str]:
    """What the binary or its bundled libraries need that the recipe does not allow."""
    allowed = set(spec["needed"]["device"]) | set(spec["output"]["bundled_libraries"])
    forbidden = set(spec["needed"]["forbidden"])
    problems = [f"{so} is forbidden" for so in sorted(set(needed) | set(lib_needed)) if so in forbidden]
    problems += [f"{so} is neither on the device nor bundled" for so in sorted(set(needed) | set(lib_needed))
                 if so not in allowed and so not in forbidden]
    return problems


def build_one(repo: Repo, name: str, out: Path) -> dict:
    spec = load(repo)[name]
    toolchain = repo.toolchains[spec["toolchain"]]
    if not build.image_present(toolchain["image_id"]):
        raise RuntimeError(f"toolchain image {spec['toolchain']} is not loaded")
    target = out / name
    exit_code = build.run_container(repo, toolchain["image_id"], render(name, spec, toolchain), target)
    binary = target / spec["output"]["binary"]
    record = {"name": name, "source": spec["source"], "toolchain": toolchain["image_id"], "exit_code": exit_code,
              "artifact": None, "bundled": {}, "needed": [], "problems": []}
    if exit_code == 0 and binary.is_file():
        read = lambda f: [line for line in (target / f).read_text().split() if line]
        record["artifact"] = {"name": binary.name, "sha256": build.sha256(binary), "size": binary.stat().st_size}
        record["bundled"] = {lib.name: build.sha256(lib) for lib in sorted((target / "lib").iterdir())}
        record["needed"] = read("needed.txt")
        record["problems"] = contract_problems(spec, record["needed"], read("lib-needed.txt"))
    record["status"] = "built" if record["artifact"] and not record["problems"] else "failed"
    (target / "record.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
