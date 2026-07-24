"""Shared Cargo.lock-shaped build-log proof for direct-cargo cores.

A cargo build's provenance model differs from the C engines: rustc argv is
not the reviewable surface (cargo synthesizes hundreds of flags), the crate
DEPENDENCY SET is. Upstream commits Cargo.lock, whose per-crate sha256
checksums make every crates.io fetch content-addressed, and the driver
builds with ``--locked`` so any drift refuses to build. The proof therefore
pins, per architecture:

* the ``CORE_PIPELINE_CARGO_LOCK|<sha256>`` marker -- the exact Cargo.lock
  bytes the catalog reviewed (the driver also verifies the digest with
  ``sha256sum -c`` before building, whose ``: OK`` line is required here);
* the ``CORE_PIPELINE_CARGO|--locked --target <triple> --release`` marker --
  the exact zigbuild invocation (the CORE_PIPELINE_MAKEFLAGS precedent);
* the full multiset of cargo ``Compiling name vX.Y.Z (source)`` lines --
  the crates actually compiled, including git-sourced crates whose pinned
  revision appears in the line (libretro-rs-ffi's ``?rev=`` url), pinned by
  count and by sha256 over the sorted lines;
* exactly one ``Finished`` line for the release profile.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping

from .log_checks import multiset_lines_sha256


COMPILING_LINE_RE = re.compile(r"^\s+(Compiling [^\s]+ v\S+(?: \([^)]+\))?)$")
FINISHED_LINE_RE = re.compile(
    r"^\s+Finished `release` profile \[optimized\] target\(s\) in \S+$"
)
CARGO_MARKER_PREFIX = "CORE_PIPELINE_CARGO|"
CARGO_LOCK_MARKER_PREFIX = "CORE_PIPELINE_CARGO_LOCK|"


@dataclasses.dataclass(frozen=True)
class CargoLogContract:
    core_id: str
    build_artifact_name: str
    source_commit: str
    source_tree: str
    lock_sha256: str
    expected_target: Mapping[str, str]
    expected_compiling_count: Mapping[str, int]
    expected_compiling_multiset_sha256: Mapping[str, str]


def cargo_compiling_lines(build_log_text: str) -> list[str]:
    """Every cargo ``Compiling`` line, whitespace-normalized."""

    lines = []
    for line in build_log_text.splitlines():
        match = COMPILING_LINE_RE.match(line)
        if match is not None:
            lines.append(match.group(1))
    return lines


def cargo_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
    contract: CargoLogContract,
) -> bool:
    if (
        core_id != contract.core_id
        or source_commit != contract.source_commit
        or source_tree != contract.source_tree
        or arch not in contract.expected_target
    ):
        return False
    lines = build_log_text.splitlines()

    lock_marker = CARGO_LOCK_MARKER_PREFIX + contract.lock_sha256
    if sum(1 for line in lines if line == lock_marker) != 1:
        return False
    if (
        sum(
            1
            for line in lines
            if line.startswith(CARGO_LOCK_MARKER_PREFIX) and line != lock_marker
        )
        != 0
    ):
        return False
    # The driver's pre-build digest verification of the pinned lock bytes.
    if sum(1 for line in lines if line == "/tmp/core-source/Cargo.lock: OK") != 1:
        return False

    invocation_marker = (
        CARGO_MARKER_PREFIX
        + f"--locked --target {contract.expected_target[arch]} --release"
    )
    if sum(1 for line in lines if line == invocation_marker) != 1:
        return False
    if (
        sum(
            1
            for line in lines
            if line.startswith(CARGO_MARKER_PREFIX) and line != invocation_marker
        )
        != 0
    ):
        return False

    compiling = cargo_compiling_lines(build_log_text)
    if len(compiling) != contract.expected_compiling_count[arch]:
        return False
    if (
        multiset_lines_sha256(compiling)
        != contract.expected_compiling_multiset_sha256[arch]
    ):
        return False

    if sum(1 for line in lines if FINISHED_LINE_RE.match(line)) != 1:
        return False
    return True


__all__ = [
    "CARGO_LOCK_MARKER_PREFIX",
    "CARGO_MARKER_PREFIX",
    "CargoLogContract",
    "cargo_compiling_lines",
    "cargo_log_proves_contract",
]
