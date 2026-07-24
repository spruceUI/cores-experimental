"""Strict compiler/linker command parsing shared by core families."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
import re

from ..foundation import sha256_bytes


FORBIDDEN_SHELL_CHARACTERS = frozenset(";&|<>$`*?[]{}~#()!")

# Compiler flags whose *separate* next token is a path operand, not a source.
# A compile-invocation parser must skip these operands so a forced-include
# header (e.g. "-include deps/.../rename.h") is not mistaken for a second
# source file. The attached forms ("-I.", "-includefoo") already look like
# options because they start with "-", so only the separate forms need this.
FILE_OPERAND_FLAGS = frozenset(
    {"-I", "-include", "-isystem", "-iquote", "-imacros", "-idirafter"}
)


def ordered_command_argv_sha256(tokens: object) -> str | None:
    """Hash one complete ordered ASCII argv, or reject malformed input."""

    if (
        not isinstance(tokens, (list, tuple))
        or not tokens
        or any(
            not isinstance(token, str) or not token.isascii()
            for token in tokens
        )
    ):
        return None
    return sha256_bytes(
        json.dumps(
            tokens,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii")
    )


def normalized_log_path(value: object, suffix: str) -> str | None:
    """Return an exact contained POSIX path ending in ``suffix``."""

    if not isinstance(value, str) or not value.endswith(suffix):
        return None
    normalized = value.removeprefix("./")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or path.as_posix() != normalized
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(re.fullmatch(r"[A-Za-z0-9_+.-]+", part) is None for part in path.parts)
    ):
        return None
    return normalized


def semantic_log_path(
    value: object,
    suffix: str,
    semantic_path_aliases: tuple[tuple[str, str], ...] = (),
) -> str | None:
    """Return a contained lexical path after one explicit prefix mapping.

    A single reviewed ``semantic_path_aliases`` prefix is substituted first, so
    a core whose build writes objects to an absolute root
    (``/libretro-super/libretro-<core>/source/`` -> ``source/``) or links its
    artifact into a subdirectory (``obj/player/`` -> ``""``) can be mapped to a
    contained relative path. The substitution never relaxes containment: after
    it, the value is still rejected unless it is a clean relative path with no
    leading ``/``, no ``..``/``.`` component, and no empty segment. Every alias
    prefix in the catalog carries a ``..``/``.``/absolute marker, so a clean
    relative object path never matches an alias and is normalized unchanged.

    A segment may contain ``~`` but must never begin with one. Some Makefiles
    flatten a source tree into one object directory by mangling ``/`` to ``~``
    (``build/release/src~hardware~vga.cpp.o``, dosbox_pure), which is an
    ordinary filename character. A *leading* ``~`` is different: make runs its
    recipes through ``/bin/sh``, so ``~/x.o`` or ``~user/x.o`` is expanded to a
    home directory before the compiler sees it, and the log echoes only the
    unexpanded text -- exactly the escape this containment guard exists to
    catch. So the first character of every segment stays strictly alphanumeric-
    or ``_+.-``.
    """

    if not isinstance(value, str) or not value or not value.endswith(suffix):
        return None
    aliased = next(
        (
            replacement_prefix + value.removeprefix(raw_prefix)
            for raw_prefix, replacement_prefix in semantic_path_aliases
            if value.startswith(raw_prefix) and value.removeprefix(raw_prefix)
        ),
        None,
    )
    if aliased is not None:
        value = aliased
    if value.startswith("/"):
        return None
    raw_parts = value.removeprefix("./").split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return None
    if any(
        re.fullmatch(r"[A-Za-z0-9_+.-][A-Za-z0-9_+.~-]*", part) is None
        for part in raw_parts
    ):
        return None
    normalized = "/".join(raw_parts)
    if not normalized or not normalized.endswith(suffix):
        return None
    return normalized


def command_uses_response_file(tokens: list[str]) -> bool:
    return any("@" in token for token in tokens[1:])


def output_option(tokens: list[str]) -> tuple[str, frozenset[int]] | None:
    """Parse the single split or attached ``-o`` option."""

    output_options = [
        (index, token)
        for index, token in enumerate(tokens[1:], start=1)
        if token == "-o" or token.startswith("-o")
    ]
    if len(output_options) != 1:
        return None
    output_index, option = output_options[0]
    if option == "-o":
        value_index = output_index + 1
        if value_index >= len(tokens) or tokens[value_index].startswith("-"):
            return None
        return tokens[value_index], frozenset({output_index, value_index})
    value = option[2:]
    if not value:
        return None
    return value, frozenset({output_index})


def command_line_is_lexically_safe(
    line: str,
    allow_embedded_tilde: bool = False,
) -> bool:
    """Reject control characters and active shell syntax before ``shlex``.

    ``allow_embedded_tilde`` is an opt-in for the one shape that needs it: a
    Makefile that mangles ``/`` to ``~`` to flatten objects into one directory
    (``build/release/src~hardware~vga.cpp.o``, dosbox_pure). A shell expands
    ``~`` only at the start of a word, so the relaxation admits it *only* when
    the preceding character is itself an ordinary path character -- ``~`` after
    whitespace, a quote, ``:``, ``=`` or at the start of the line stays
    forbidden, and every other metacharacter is untouched. Left unset the guard
    is byte-for-byte the original one.
    """

    forbidden = FORBIDDEN_SHELL_CHARACTERS
    if allow_embedded_tilde:
        forbidden = forbidden - {"~"}
        if any(
            index == 0
            or re.fullmatch(r"[A-Za-z0-9_+./-]", line[index - 1]) is None
            for index, character in enumerate(line)
            if character == "~"
        ):
            return False
    if (
        not line
        or not line.isascii()
        or any(ord(character) < 32 or ord(character) == 127 for character in line)
        or any(character in forbidden for character in line)
    ):
        return False
    return all(
        index + 1 < len(line) and line[index + 1] == '"'
        for index, character in enumerate(line)
        if character == "\\"
    )
