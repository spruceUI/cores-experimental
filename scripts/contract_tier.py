#!/usr/bin/env python3
"""Contract-tier policy and the tiered promotion gate.

Two tiers, per the approved policy:

* heavy - a core with a registered exact compile/link/diagnostic log contract
  (registering that contract is the "heavy" flag). Its promotion keeps the full
  transcript proof.
* light - every other core. Its promotion gate is the cheaper, device-relevant
  evidence: a valid static build golden (artifact hash + libretro exports +
  version_requirements, all already validated when the compatibility manifest
  is written) PLUS a passing target-runtime smoke result.

Runtime smoke is the universal component: both tiers require it for a full
(non-static-only) promotion, so the device end-goal is captured once per core
rather than deferred. This module is read-only and standalone; it unifies the
device screen (device_sets), the fitness projection, and the smoke contract into
one tier-aware view. It does not itself mutate the pipeline's fail-closed
promotion; wiring a light-tier core's promotion to defer here happens per core
during migration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from core_pipeline_lib.contracts import registry  # noqa: E402

COMPATIBILITY_DIR = ROOT / "manifests" / "compatibility"
MINI_GLIBCXX_CEILING = (3, 4, 24)
SMOKE_STATES = ("pass", "fail", "pending")


def heavy_cores() -> frozenset[str]:
    """Cores with a registered exact-transcript log contract (the heavy flag)."""

    cores: set[str] = set()
    for contract in registry.CORE_LOG_CONTRACTS:
        cores.update(contract.core_ids)
    return frozenset(cores)


def core_tier(core_id: str) -> str:
    return "heavy" if core_id in heavy_cores() else "light"


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    return tuple(int(p) for p in parts) if all(p.isdecimal() for p in parts) else ()


def _armhf_over_mini(manifest: dict[str, Any]) -> bool:
    reqs = manifest.get("targets", {}).get("armhf", {}).get("version_requirements", [])
    best: tuple[int, ...] = ()
    for symbol in reqs:
        if symbol.startswith("GLIBCXX_"):
            key = _version_tuple(symbol[len("GLIBCXX_") :])
            if key > best:
                best = key
    return best > MINI_GLIBCXX_CEILING


def _static_evidence_ok(manifest: dict[str, Any]) -> bool:
    """The compatibility manifest's static build evidence is well-formed.

    A written manifest already implies the e2e gate validated ELF/ABI and
    libretro exports, so the light gate checks the manifest carries both ABI
    targets with an artifact hash and captured version_requirements.
    """

    if manifest.get("publication") != "disabled":
        return False
    targets = manifest.get("targets", {})
    if set(targets) != {"arm64", "armhf"}:
        return False
    for target in targets.values():
        if not isinstance(target.get("artifact_sha256"), str):
            return False
        if not isinstance(target.get("version_requirements"), list) or not target["version_requirements"]:
            return False
        if not isinstance(target.get("needed"), list) or not target["needed"]:
            return False
    return True


def light_gate_status(core_id: str, smoke_status: str = "pending") -> dict[str, Any]:
    """Evaluate the light promotion gate for one core.

    Returns a verdict: ``pass`` (static evidence valid and smoke passed),
    ``pending-runtime`` (static evidence valid, no smoke captured yet),
    ``fail`` (smoke failed or static evidence malformed), or ``no-manifest``.
    """

    if smoke_status not in SMOKE_STATES:
        raise ValueError(f"unknown smoke status: {smoke_status}")
    path = COMPATIBILITY_DIR / f"{core_id}.json"
    if not path.is_file():
        return {"core": core_id, "verdict": "no-manifest"}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    static_ok = _static_evidence_ok(manifest)
    if not static_ok:
        verdict = "fail"
    elif smoke_status == "pass":
        verdict = "pass"
    elif smoke_status == "fail":
        verdict = "fail"
    else:
        verdict = "pending-runtime"
    return {
        "core": core_id,
        "verdict": verdict,
        "static_evidence": "valid" if static_ok else "invalid",
        "runtime_smoke": smoke_status,
    }


def tier_report(smoke_index: dict[str, str] | None = None) -> dict[str, Any]:
    """One tier-aware row per canonical core: tier, light gate, device screen."""

    smoke_index = smoke_index or {}
    rows = []
    for path in sorted(COMPATIBILITY_DIR.glob("*.json")):
        core_id = path.stem
        manifest = json.loads(path.read_text(encoding="utf-8"))
        smoke = smoke_index.get(core_id, "pending")
        gate = light_gate_status(core_id, smoke)
        rows.append({
            "core": core_id,
            "tier": core_tier(core_id),
            "light_gate": gate["verdict"],
            "runtime_smoke": smoke,
            "armhf_mini_ineligible": _armhf_over_mini(manifest),
        })
    heavy = sum(1 for r in rows if r["tier"] == "heavy")
    return {
        "schema_version": 1,
        "local_only": True,
        "publication": "disabled",
        "policy": "tiered-light-default-heavy-on-registered-contract",
        "runtime_gate": "required-for-full-promotion-both-tiers",
        "counts": {
            "cores": len(rows),
            "heavy": heavy,
            "light": len(rows) - heavy,
            "runtime_verified": sum(1 for r in rows if r["runtime_smoke"] == "pass"),
        },
        "cores": rows,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("report", help="print the tier-aware promotion view as JSON")
    gate = subparsers.add_parser("gate", help="evaluate one core's light gate")
    gate.add_argument("--core", required=True)
    gate.add_argument("--smoke", default="pending", choices=SMOKE_STATES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "report":
        print(json.dumps(tier_report(), indent=2, sort_keys=True))
        return 0
    if args.command == "gate":
        verdict = light_gate_status(args.core, args.smoke)
        print(json.dumps(verdict, indent=2, sort_keys=True))
        return 0 if verdict["verdict"] in {"pass", "pending-runtime"} else 1
    build_parser().error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
