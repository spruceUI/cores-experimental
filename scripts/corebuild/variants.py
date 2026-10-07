"""Boards x optimization profiles -> the distinct builds of one core.

Boards with identical flags share a build (a523/rk3566 are both A55, a33/ssd202d both A7+NEON)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace

# Extra flags from the tunable workflow: GCC options only, no paths or specs.
FLAG = re.compile(
    r"^-(?:O(?:[0-3gsz]|fast)?|g[a-z0-9-]*|f[a-z0-9][a-z0-9=_.,+-]*"
    r"|m[a-z0-9][a-z0-9=_.,+-]*|D[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_.,+-]*)?)$"
)
# 'static' links the C++ runtime into the core and keeps its symbols private, so the
# core does not depend on the device's libstdc++ (docs/flags.md#c-runtime).
RUNTIMES = {"shared": (), "static": ("-static-libstdc++", "-static-libgcc", "-Wl,--exclude-libs,ALL")}


@dataclass(frozen=True)
class Variant:
    arch: str
    profile: str
    board_flags: tuple[str, ...] = ()
    profile_flags: tuple[str, ...] = ()
    extra_flags: tuple[str, ...] = ()
    cargo: tuple[tuple[str, str], ...] = ()
    unless: tuple[str, ...] = ()  # profile flags are skipped on a call that has one of these
    runtime: str = "shared"
    strip: bool = False
    boards: tuple[str, ...] = field(default=(), compare=False)

    @property
    def kept_flags(self) -> tuple[str, ...]:
        """Every flag but the profile's: these apply even where `unless` skips the profile."""
        return self.board_flags + self.extra_flags + RUNTIMES[self.runtime]

    @property
    def flags(self) -> tuple[str, ...]:
        return self.board_flags + self.profile_flags + self.extra_flags + RUNTIMES[self.runtime]

    @property
    def is_baseline(self) -> bool:
        return not self.flags and not self.cargo and not self.strip

    @property
    def suffix(self) -> str:
        return ("-static" if self.runtime == "static" else "") + ("-stripped" if self.strip else "")

    @property
    def name(self) -> str:
        cpu = [f.split("=", 1)[1] for f in self.board_flags if f.startswith(("-mcpu=", "-mfpu="))]
        name = f"{self.profile}-{self.arch}-{'-'.join(cpu) or 'generic'}"
        if self.extra_flags:
            digest = hashlib.sha256(" ".join(self.extra_flags).encode()).hexdigest()[:8]
            name += f"-x{digest}"
        return name + self.suffix

    def describe(self) -> dict:
        return {
            "name": self.name,
            "arch": self.arch,
            "profile": self.profile,
            "boards": list(self.boards),
            "flags": list(self.flags),
            "cargo": dict(self.cargo),
            "runtime": self.runtime,
            "strip": self.strip,
            "suffix": self.suffix,
        }


def parse_flags(text: str) -> tuple[str, ...]:
    tokens = tuple(text.split())
    bad = [token for token in tokens if not FLAG.match(token)]
    if bad:
        raise ValueError("unsupported extra flags: " + " ".join(bad))
    return tokens


def plan(spec: dict, boards: dict, profiles: dict, board_names: list[str],
         profile_names: list[str], extra_flags: tuple[str, ...] = (),
         arch: str | None = None, runtimes: tuple[str, ...] = ("shared",),
         strip: bool = False) -> list[Variant]:
    """Every distinct build of one core; each lists the boards it serves."""
    cargo = spec["build"]["driver"] == "direct-cargo"
    builds: dict[Variant, Variant] = {}
    for board in board_names:
        board_arch = boards[board]["arch"]
        arches = [a for a in spec["targets"] if board_arch in (None, a) and arch in (None, a)]
        for profile in profile_names:
            settings = profiles[profile]
            for target in arches:
                for runtime in runtimes:
                    if cargo:
                        # Rust cores take the profile through cargo settings only; std is always static.
                        variant = Variant(target, profile, cargo=tuple(sorted(settings["cargo"].items())), strip=strip)
                    else:
                        variant = Variant(target, profile, tuple(boards[board]["flags"]),
                                          tuple(settings["flags"]), extra_flags,
                                          unless=tuple(settings.get("unless", ())), runtime=runtime, strip=strip)
                    seen = builds.get(variant)
                    if seen is None or board not in seen.boards:
                        builds[variant] = replace(variant, boards=(seen.boards if seen else ()) + (board,))
    return list(builds.values())
