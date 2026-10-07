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


@dataclass(frozen=True)
class Variant:
    arch: str
    profile: str
    board_flags: tuple[str, ...] = ()
    profile_flags: tuple[str, ...] = ()
    extra_flags: tuple[str, ...] = ()
    cargo: tuple[tuple[str, str], ...] = ()
    boards: tuple[str, ...] = field(default=(), compare=False)

    @property
    def flags(self) -> tuple[str, ...]:
        return self.board_flags + self.profile_flags + self.extra_flags

    @property
    def is_baseline(self) -> bool:
        return not self.flags and not self.cargo

    @property
    def name(self) -> str:
        cpu = [f.split("=", 1)[1] for f in self.board_flags if f.startswith(("-mcpu=", "-mfpu="))]
        name = f"{self.profile}-{self.arch}-{'-'.join(cpu) or 'generic'}"
        if self.extra_flags:
            digest = hashlib.sha256(" ".join(self.extra_flags).encode()).hexdigest()[:8]
            name += f"-x{digest}"
        return name

    def describe(self) -> dict:
        return {
            "name": self.name,
            "arch": self.arch,
            "profile": self.profile,
            "boards": list(self.boards),
            "flags": list(self.flags),
            "cargo": dict(self.cargo),
        }


def parse_flags(text: str) -> tuple[str, ...]:
    tokens = tuple(text.split())
    bad = [token for token in tokens if not FLAG.match(token)]
    if bad:
        raise ValueError("unsupported extra flags: " + " ".join(bad))
    return tokens


def plan(spec: dict, boards: dict, profiles: dict, board_names: list[str],
         profile_names: list[str], extra_flags: tuple[str, ...] = (),
         arch: str | None = None) -> list[Variant]:
    """Every distinct build of one core; each lists the boards it serves."""
    cargo = spec["build"]["driver"] == "direct-cargo"
    builds: dict[Variant, Variant] = {}
    for board in board_names:
        board_arch = boards[board]["arch"]
        arches = [a for a in spec["targets"] if board_arch in (None, a) and arch in (None, a)]
        for profile in profile_names:
            settings = profiles[profile]
            for target in arches:
                if cargo:
                    # Rust cores take the profile through cargo settings only.
                    variant = Variant(target, profile, cargo=tuple(sorted(settings["cargo"].items())))
                else:
                    variant = Variant(target, profile, tuple(boards[board]["flags"]),
                                      tuple(settings["flags"]), extra_flags)
                seen = builds.get(variant)
                builds[variant] = replace(variant, boards=(seen.boards if seen else ()) + (board,))
    return list(builds.values())
