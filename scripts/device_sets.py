#!/usr/bin/env python3
"""Assemble per-device candidate core sets from the local device model.

Read-only. Combines the device runtime contracts (provider ABI ceilings and
per-core policies), the execution profiles (profile -> architecture and frontend
availability), and each core's captured ``version_requirements`` to compute, per
device family, the set of cores that build for the device architecture and clear
its libstdc++ provider ceiling.

This is a static ABI screen only. It is necessary, not sufficient: every device
view remains provisional until a target-runtime smoke test is captured (a later
pipeline phase fills that in). Nothing here promotes, packages, or publishes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEVICE_CONTRACTS_PATH = ROOT / "manifests" / "device-runtime-contracts.json"
EXECUTION_PROFILES_PATH = ROOT / "manifests" / "execution-profiles.json"
COMPATIBILITY_DIR = ROOT / "manifests" / "compatibility"

SCHEMA_VERSION = 1
CXX_PROVIDER_LIB = "libstdc++.so.6"
# The ELF interpreter appears in DT_NEEDED but is not a library the device has
# to provide separately: it is implied by the ABI the device runs.
ABI_INTERPRETERS = {
    "arm64": "ld-linux-aarch64.so.1",
    "armhf": "ld-linux-armhf.so.3",
}


class DeviceSetError(Exception):
    """Raised for malformed inputs to the device-set assembly."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise DeviceSetError(f"missing manifest: {path}") from exc
    except json.JSONDecodeError as exc:
        raise DeviceSetError(f"invalid JSON in {path}: {exc}") from exc


def version_tuple(version: str) -> tuple[int, ...]:
    """Parse a dotted numeric version (``3.4.32``) into a comparable tuple.

    A bare ``3.4`` sorts below any ``3.4.N`` because it is the shorter tuple.
    """

    parts = version.split(".")
    result: list[int] = []
    for part in parts:
        if not part.isdecimal():
            return ()
        result.append(int(part))
    return tuple(result)


def _symbol_version(symbol: str, prefix: str) -> tuple[int, ...]:
    if not symbol.startswith(prefix):
        return ()
    return version_tuple(symbol[len(prefix) :])


def max_symbol_version(symbols: list[str], prefix: str) -> str | None:
    """Return the highest ``PREFIX``-qualified symbol string, or ``None``."""

    best_symbol: str | None = None
    best_key: tuple[int, ...] = ()
    for symbol in symbols:
        key = _symbol_version(symbol, prefix)
        if key and key >= best_key:
            best_key = key
            best_symbol = symbol
    return best_symbol


def profile_architecture(profiles: dict[str, Any], profile_id: str) -> str:
    profile = profiles.get("profiles", {}).get(profile_id)
    if not isinstance(profile, dict) or "architecture" not in profile:
        raise DeviceSetError(f"unknown execution profile: {profile_id}")
    return profile["architecture"]


def profile_frontend_available(profiles: dict[str, Any], profile_id: str) -> bool:
    profile = profiles.get("profiles", {}).get(profile_id, {})
    frontend = profile.get("frontend", {}) if isinstance(profile, dict) else {}
    return frontend.get("availability") == "present"


def device_glibcxx_ceiling(contract: dict[str, Any]) -> str | None:
    """Highest GLIBCXX the device's provider observations can satisfy.

    ``None`` means no provider was captured (the ceiling is unknown, so the
    screen cannot confirm or deny eligibility for C++ cores).
    """

    best: str | None = None
    best_key: tuple[int, ...] = ()
    for observation in contract.get("provider_observations", []):
        symbols = observation.get("max_versioned_symbols", {})
        value = symbols.get("GLIBCXX")
        if not isinstance(value, str):
            continue
        key = version_tuple(value)
        if key and key >= best_key:
            best_key = key
            best = value
    return best


def device_library_availability(
    contract: dict[str, Any],
) -> tuple[set[str], set[str]] | None:
    """Return (available, absent) sonames a device_probe run observed.

    ``None`` means no probe has run on this device, so provider availability is
    unknown and every non-trivial core must be reported as uncaptured rather
    than assumed loadable.
    """

    observations = contract.get("library_observations")
    if not isinstance(observations, dict):
        return None
    available = observations.get("available")
    absent = observations.get("absent")
    if not isinstance(available, list) or not isinstance(absent, list):
        return None
    return (
        {item for item in available if isinstance(item, str)},
        {item for item in absent if isinstance(item, str)},
    )


def _core_policies(contracts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    policies = contracts.get("core_policies", {})
    return policies if isinstance(policies, dict) else {}


def _policy_exclusion(
    core_id: str, architecture: str, policies: dict[str, dict[str, Any]]
) -> str | None:
    policy = policies.get(core_id)
    if not isinstance(policy, dict):
        return None
    if policy.get("default_selection") == "excluded":
        return "default-excluded"
    if architecture == "armhf" and policy.get("armhf_device_views") == "not-consumed":
        return "armhf-not-consumed"
    return None


def _profile_constraints(
    contracts: dict[str, Any], profile_id: str
) -> dict[str, str]:
    """Map core_id -> constraint_id for constraints bound to this profile."""

    result: dict[str, str] = {}
    for constraint in contracts.get("compatibility_constraints", []):
        if constraint.get("execution_profile_id") != profile_id:
            continue
        constraint_id = constraint.get("constraint_id", "")
        for core_id in constraint.get("core_ids", []):
            result[core_id] = constraint_id
    return result


def load_core_targets() -> dict[str, dict[str, Any]]:
    """Return {core_id: {arch: target}} for every canonical compatibility record."""

    cores: dict[str, dict[str, Any]] = {}
    for path in sorted(COMPATIBILITY_DIR.glob("*.json")):
        document = _load_json(path)
        core_id = document.get("core_id")
        targets = document.get("targets")
        if isinstance(core_id, str) and isinstance(targets, dict):
            cores[core_id] = targets
    return cores


def classify_core(
    target: dict[str, Any] | None,
    ceiling: str | None,
    architecture: str | None = None,
    libraries: tuple[set[str], set[str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Classify one core's target against a device's captured providers.

    Returns ``(bucket, detail)`` where bucket is one of ``eligible``,
    ``eligible_ceiling_uncaptured``, ``over_ceiling``, ``missing_provider``,
    ``provider_uncaptured``, or ``no_arch_target``.

    Two independent screens run here. The library screen asks whether every
    soname in the core's DT_NEEDED is actually present on the device; the
    ceiling screen asks whether the device's libstdc++ is new enough. The
    library screen runs first because a missing provider is fatal regardless of
    any version comparison -- that is the case a ceiling-only screen missed
    entirely, and it is why a core linking libGLESv2 could be reported eligible
    on a device with no GLES2 at all.
    """

    if not isinstance(target, dict):
        return "no_arch_target", {}
    needed = target.get("needed", [])
    reqs = target.get("version_requirements", [])
    max_cxx = max_symbol_version(reqs, "GLIBCXX_")
    detail: dict[str, Any] = {}
    if max_cxx is not None:
        detail["glibcxx"] = max_cxx[len("GLIBCXX_") :]

    interpreter = ABI_INTERPRETERS.get(architecture or "")
    externals = [
        soname
        for soname in needed
        if isinstance(soname, str) and soname != interpreter
    ]
    available, absent = libraries if libraries is not None else (None, None)
    missing = (
        sorted(soname for soname in externals if soname in absent)
        if absent is not None
        else []
    )
    unverified = (
        sorted(externals)
        if available is None
        else sorted(soname for soname in externals if soname not in available)
    )
    needs_cxx = CXX_PROVIDER_LIB in needed and max_cxx is not None
    over_ceiling = bool(
        needs_cxx
        and ceiling is not None
        and _symbol_version(max_cxx, "GLIBCXX_") > version_tuple(ceiling)
    )

    # Definite disqualifications are reported ahead of uncertainty, so an
    # unprobed device still surfaces what IS known about it (the Mini's
    # over-ceiling C++ cores stay over-ceiling rather than collapsing into
    # "uncaptured"). A missing provider outranks a version ceiling: no version
    # comparison matters for a library that is not there at all.
    if missing:
        detail["missing_providers"] = missing
        return "missing_provider", detail
    if over_ceiling:
        return "over_ceiling", detail
    if unverified:
        # Observed neither present nor absent -- absence of evidence, so fail
        # closed rather than assume the device provides it.
        detail["unverified_providers"] = unverified
        return "provider_uncaptured", detail
    if needs_cxx and ceiling is None:
        return "eligible_ceiling_uncaptured", detail
    return "eligible", detail


def assemble_device_sets(
    contracts: dict[str, Any], profiles: dict[str, Any]
) -> dict[str, Any]:
    """Compute the per-device candidate core sets from the local model."""

    core_targets = load_core_targets()
    policies = _core_policies(contracts)
    devices: dict[str, Any] = {}
    for contract_id, contract in sorted(contracts.get("contracts", {}).items()):
        profile_id = contract.get("default_execution_profile")
        if not isinstance(profile_id, str):
            raise DeviceSetError(f"{contract_id} has no default execution profile")
        architecture = profile_architecture(profiles, profile_id)
        ceiling = device_glibcxx_ceiling(contract)
        constraints = _profile_constraints(contracts, profile_id)
        libraries = device_library_availability(contract)
        buckets: dict[str, list[dict[str, Any]]] = {
            "eligible": [],
            "eligible_ceiling_uncaptured": [],
            "over_ceiling": [],
            "missing_provider": [],
            "provider_uncaptured": [],
            "policy_excluded": [],
            "no_arch_target": [],
        }
        for core_id in sorted(core_targets):
            excluded = _policy_exclusion(core_id, architecture, policies)
            if excluded is not None:
                buckets["policy_excluded"].append(
                    {"core": core_id, "reason": excluded}
                )
                continue
            bucket, detail = classify_core(
                core_targets[core_id].get(architecture),
                ceiling,
                architecture,
                libraries,
            )
            entry: dict[str, Any] = {"core": core_id, **detail}
            if core_id in constraints:
                entry["constraint"] = constraints[core_id]
            buckets[bucket].append(entry)
        devices[contract_id] = {
            "family": contract.get("runtime_family_id"),
            "device_ids": [
                device.get("device_id")
                for device in contract.get("devices", [])
            ],
            "architecture": architecture,
            "execution_profile": profile_id,
            "provider_glibcxx_ceiling": ceiling,
            "library_capture": (
                contract.get("library_observations", {}).get("resolution_method")
                if libraries is not None
                else None
            ),
            "frontend_available": profile_frontend_available(profiles, profile_id),
            "runtime_capture": contract.get("runtime_capture"),
            "counts": {name: len(rows) for name, rows in buckets.items()},
            **buckets,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "local_only": True,
        "publication": "disabled",
        "screen": "static-abi-only",
        "note": (
            "necessary-not-sufficient: every device view remains provisional "
            "until a target-runtime smoke test is captured"
        ),
        "core_count": len(core_targets),
        "devices": devices,
    }


def build_report(device_id: str | None = None) -> dict[str, Any]:
    contracts = _load_json(DEVICE_CONTRACTS_PATH)
    profiles = _load_json(EXECUTION_PROFILES_PATH)
    report = assemble_device_sets(contracts, profiles)
    if device_id is not None:
        selected = report["devices"].get(device_id)
        if selected is None:
            raise DeviceSetError(f"unknown device contract: {device_id}")
        report["devices"] = {device_id: selected}
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    report = subparsers.add_parser(
        "report", help="print the per-device candidate core sets as JSON"
    )
    report.add_argument(
        "--device",
        help="limit the report to one device contract id",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "report":
            report = build_report(args.device)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0
    except DeviceSetError as exc:
        print(f"device sets error: {exc}", file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
