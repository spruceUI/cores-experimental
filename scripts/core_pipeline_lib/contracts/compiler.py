"""Shared target-compiler identities and conservative log discovery."""

from __future__ import annotations

import re


COMPILER_COMMAND_RE = re.compile(
    r"^(?:[A-Za-z0-9_.+~-]+-)?(?:gcc|g\+\+|cc|c\+\+|clang|clang\+\+)"
    r"(?:-[0-9]+(?:\.[0-9]+)*)?$"
)
TARGET_COMPILERS = {
    "arm64": {"aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"},
    "armhf": {
        "arm-a30-linux-gnueabihf-gcc",
        "arm-a30-linux-gnueabihf-g++",
    },
}
TARGET_CXX_COMPILERS = {
    "arm64": {"aarch64-linux-gnu-g++"},
    "armhf": {"arm-a30-linux-gnueabihf-g++"},
}


def line_may_name_target_compiler(
    line: str, expected_compilers: set[str]
) -> bool:
    if any(compiler in line for compiler in expected_compilers):
        return True
    if not any(character in line for character in "'\"\\"):
        return False
    collapsed = line.translate(str.maketrans("", "", "'\"\\"))
    return any(compiler in collapsed for compiler in expected_compilers)
