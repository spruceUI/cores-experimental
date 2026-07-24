"""Shared build-log validation primitives.

These small, pure helpers are used identically by several core contracts to
hash and locate build-log lines. They live here so there is one definition to
read and maintain rather than a copy per core.
"""

from __future__ import annotations

from ..foundation import sha256_bytes


def lines_sha256(lines: tuple[str, ...]) -> str:
    """Hash ordered log lines with their original newline framing."""

    material = "".join(f"{line}\n" for line in lines)
    return sha256_bytes(material.encode("utf-8"))


def multiset_lines_sha256(lines: tuple[str, ...]) -> str:
    """Hash a complete line multiset independent of parallel ordering."""

    return lines_sha256(tuple(sorted(lines)))


def sequence_positions(
    lines: list[str], sequence: tuple[str, ...]
) -> tuple[int, ...]:
    """Return every start index at which ``sequence`` occurs contiguously."""

    return tuple(
        position
        for position in range(len(lines) - len(sequence) + 1)
        if tuple(lines[position : position + len(sequence)]) == sequence
    )


def compiler_token_name(token: str) -> str:
    """Reduce a compiler token to its bare command name (drop path/`VAR=`)."""

    candidate = token.rsplit("=", 1)[-1]
    return candidate.rsplit("/", 1)[-1]
