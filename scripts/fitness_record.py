#!/usr/bin/env python3
"""Compose the consolidated per-core device-fitness record.

Read-only. Projects each core's already-captured, tracked evidence into a
compact record that carries exactly what is needed to (a) locate the
authoritative build identity and (b) decide device fitness:

    source commit + authoritative pin reference
    + per ABI: artifact hash, ELF class, execution profile, toolchain image id,
      runtime deps, max GLIBCXX/GLIBC, libretro-ABI status, runtime-smoke status

It deliberately does not duplicate the pin's 170-file provenance bundle or the
per-compile transcript proofs; it references the pin for full identity and keeps
only the device-relevant facts. ``runtime_smoke`` is ``pending`` until a later
phase captures a target-runtime result. Nothing here promotes or publishes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EXECUTION_PROFILES_PATH = ROOT / "manifests" / "execution-profiles.json"
COMPATIBILITY_DIR = ROOT / "manifests" / "compatibility"

SCHEMA_VERSION = 1
ARCHITECTURES = ("arm64", "armhf")


class FitnessRecordError(Exception):
    """Raised for missing or malformed fitness inputs."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise FitnessRecordError(f"missing manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FitnessRecordError(f"invalid JSON in {path}: {exc}") from exc


def _version_key(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    if not all(part.isdecimal() for part in parts):
        return ()
    return tuple(int(part) for part in parts)


def max_symbol(symbols: list[str], prefix: str) -> str | None:
    """Return the highest ``PREFIX``-qualified symbol's version, or ``None``."""

    best_value: str | None = None
    best_key: tuple[int, ...] = ()
    for symbol in symbols:
        if not symbol.startswith(prefix):
            continue
        value = symbol[len(prefix) :]
        key = _version_key(value)
        if key and key >= best_key:
            best_key = key
            best_value = value
    return best_value


def locked_toolchain_images(profiles: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Map architecture -> {profile, image_id} for each locked build identity.

    A locked build identity is the single profile per architecture that carries
    a concrete toolchain image; provisional profiles (image-less) are ignored.
    """

    images: dict[str, dict[str, str]] = {}
    for profile_id, profile in sorted(profiles.get("profiles", {}).items()):
        build_identity = profile.get("build_identity")
        if not isinstance(build_identity, dict):
            continue
        architecture = build_identity.get("toolchain_architecture")
        image_id = build_identity.get("image_id")
        if not isinstance(architecture, str) or not isinstance(image_id, str):
            continue
        if architecture in images:
            raise FitnessRecordError(
                f"multiple locked build identities for {architecture}"
            )
        images[architecture] = {"profile": profile_id, "image_id": image_id}
    return images


def _target_fitness(
    target: dict[str, Any], toolchain: dict[str, str] | None
) -> dict[str, Any]:
    reqs = target.get("version_requirements", [])
    fitness: dict[str, Any] = {
        "artifact_sha256": target.get("artifact_sha256"),
        "elf": target.get("elf"),
        "runtime_deps": target.get("needed", []),
        "max_glibcxx": max_symbol(reqs, "GLIBCXX_"),
        "max_glibc": max_symbol(reqs, "GLIBC_"),
        # The e2e gate rejects an artifact missing the required libretro exports,
        # so a recorded static-build golden implies the ABI surface was checked.
        "libretro_abi": "validated-at-build",
        # Filled by the target-runtime smoke phase; screen-only until then.
        "runtime_smoke": "pending",
    }
    if toolchain is not None:
        fitness["execution_profile"] = toolchain["profile"]
        fitness["toolchain_image_id"] = toolchain["image_id"]
    else:
        fitness["execution_profile"] = None
        fitness["toolchain_image_id"] = None
    return fitness


def compose_fitness(core_id: str, *, images: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """Compose one core's fitness record from its tracked compatibility record."""

    path = COMPATIBILITY_DIR / f"{core_id}.json"
    document = _load_json(path)
    if document.get("core_id") != core_id:
        raise FitnessRecordError(f"compatibility record core mismatch: {core_id}")
    if images is None:
        images = locked_toolchain_images(_load_json(EXECUTION_PROFILES_PATH))
    targets = document.get("targets", {})
    if not isinstance(targets, dict) or not targets:
        raise FitnessRecordError(f"{core_id} has no targets")
    record_targets: dict[str, Any] = {}
    for architecture in ARCHITECTURES:
        target = targets.get(architecture)
        if isinstance(target, dict):
            record_targets[architecture] = _target_fitness(
                target, images.get(architecture)
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "core_id": core_id,
        "local_only": True,
        "publication": "disabled",
        "validation_scope": "static-build-only",
        "source_commit": document.get("source_commit"),
        "pin": document.get("golden_source"),
        "targets": record_targets,
    }


def canonical_core_ids() -> list[str]:
    return sorted(
        path.stem for path in COMPATIBILITY_DIR.glob("*.json") if path.is_file()
    )


def build_report(core_id: str | None = None) -> dict[str, Any]:
    images = locked_toolchain_images(_load_json(EXECUTION_PROFILES_PATH))
    if core_id is not None:
        return {
            "schema_version": SCHEMA_VERSION,
            "records": {core_id: compose_fitness(core_id, images=images)},
        }
    records = {
        core: compose_fitness(core, images=images) for core in canonical_core_ids()
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "core_count": len(records),
        "records": records,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    report = subparsers.add_parser(
        "report", help="print consolidated device-fitness records as JSON"
    )
    report.add_argument("--core", help="limit the report to one core id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            print(json.dumps(build_report(args.core), indent=2, sort_keys=True))
            return 0
    except FitnessRecordError as exc:
        print(f"fitness record error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
