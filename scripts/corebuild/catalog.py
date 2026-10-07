"""Load the repository's data files and check them for consistency."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHES = ("arm64", "armhf")
DRIVERS = ("libretro-super", "direct-make", "direct-cmake", "direct-cargo")
CORE_ID = re.compile(r"^[a-z0-9][a-z0-9_]*$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
TEMPLATE = re.compile(r"\{commit:(\d+)\}")


def known_good(spec: dict) -> dict | None:
    """The core's last known-good recipe, as a full spec, or None."""
    if "known_good" not in spec:
        return None
    return {**spec, **spec["known_good"], "known_good_of": spec["source"]["commit"]}


def load_json(path: Path) -> dict:
    def no_duplicates(pairs):
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{path}: duplicate key")
        return dict(pairs)

    return json.loads(path.read_text(), object_pairs_hook=no_duplicates)


class Repo:
    """The catalog plus the board, profile and toolchain registries."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.cores = load_json(root / "manifests/core-builds.json")["cores"]
        self.boards = load_json(root / "manifests/boards.json")["boards"]
        self.profiles = load_json(root / "manifests/optimization-profiles.json")["profiles"]
        toolchains = load_json(root / "manifests/toolchains.json")
        self.toolchains = toolchains["toolchains"]
        self.toolchain_release = toolchains["release"]

    def save_catalog(self) -> None:
        path = self.root / "manifests/core-builds.json"
        data = load_json(path)
        data["cores"] = self.cores
        path.write_text(json.dumps(data, indent=2) + "\n")

    def select(self, text: str) -> list[str]:
        """Expand 'all' or a comma/space separated list of core ids."""
        names = text.replace(",", " ").split()
        if names in ([], ["all"]):
            return sorted(self.cores)
        unknown = [name for name in names if name not in self.cores]
        if unknown:
            raise ValueError("unknown cores: " + " ".join(unknown))
        return list(dict.fromkeys(names))

    def select_from(self, text: str, registry: dict, what: str) -> list[str]:
        names = text.replace(",", " ").split()
        if names in ([], ["all"]):
            return list(registry)
        unknown = [name for name in names if name not in registry]
        if unknown:
            raise ValueError(f"unknown {what}: " + " ".join(unknown))
        return list(dict.fromkeys(names))

    def check(self) -> list[str]:
        """Offline consistency problems, as readable messages."""
        errors: list[str] = []
        for core, spec in sorted(self.cores.items()):
            errors += [f"{core}: {problem}" for problem in self._check_core(core, spec)]
        for name, board in self.boards.items():
            if board["arch"] not in (None, *ARCHES):
                errors.append(f"board {name}: unknown arch {board['arch']}")
        for name, profile in self.profiles.items():
            for flag in profile["flags"]:
                if not flag.startswith(("-O", "-g")):
                    errors.append(f"profile {name}: unexpected flag {flag}")
        return errors

    def _check_core(self, core: str, spec: dict) -> list[str]:
        problems = []
        if not CORE_ID.match(core):
            problems.append("core id must match " + CORE_ID.pattern)
        previous = known_good(spec)
        if previous is not None:
            if previous["source"]["commit"] == spec["source"]["commit"]:
                problems.append("known_good repeats the current commit")
            problems += ["known_good: " + p for p in self._check_recipe(previous)]
        return problems + self._check_recipe(spec)

    def _check_recipe(self, spec: dict) -> list[str]:
        problems = []
        source, build = spec["source"], spec["build"]
        text = json.dumps(build)
        if any(not 4 <= int(n) <= 40 for n in TEMPLATE.findall(text)):
            problems.append("{commit:N} needs 4 <= N <= 40")
        if not COMMIT.match(source.get("commit", "")):
            problems.append("source.commit must be a full commit id")
        if not set(spec["targets"]) <= set(ARCHES) or not spec["targets"]:
            problems.append(f"targets must be a subset of {ARCHES}")
        if build.get("driver") not in DRIVERS:
            problems.append(f"unknown driver {build.get('driver')}")
        for arch, overlays in build.get("overlays", {}).items():
            if arch not in spec["targets"]:
                problems.append(f"overlays for untargeted arch {arch}")
            for overlay in overlays:
                if not (self.root / overlay["patch"]).is_file():
                    problems.append(f"missing patch {overlay['patch']}")
        repo_path = spec["metadata"].get("repo_path")
        if repo_path and not (self.root / repo_path).is_file():
            problems.append(f"missing metadata {repo_path}")
        if build.get("driver") == "libretro-super" and not build.get("source_key"):
            problems.append("libretro-super cores need a source_key")
        if build.get("driver") == "direct-cmake" and "target" not in build.get("cmake", {}):
            problems.append("direct-cmake cores need cmake.target")
        for entry in build.get("neon", []):
            if not re.match(r"^(?:-D[A-Za-z_][A-Za-z0-9_]*(?:=\S*)?|[A-Za-z_][A-Za-z0-9_]*=\S*)$", entry):
                problems.append(f"neon entry {entry!r} is neither NAME=VALUE nor -DNAME[=VALUE]")
        if build.get("driver") == "direct-cargo":
            missing = set(spec["targets"]) - set(build.get("cargo", {}).get("targets", {}))
            if missing:
                problems.append("cargo.targets lacks " + " ".join(sorted(missing)))
        return problems
