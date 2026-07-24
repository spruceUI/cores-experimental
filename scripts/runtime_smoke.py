#!/usr/bin/env python3
"""Target runtime smoke-test contract and its feed into device fitness.

The smoke test is the one gate the end goal actually needs: proof that a built
libretro core *loads and runs* under a device's ABI, not merely that it compiled.
Execution happens on GitHub Actions (an x86 runner with qemu-user-static via
binfmt, or a native arm64 runner), which is where the ARM artifacts can actually
run; it is human-dispatched, never automatic, and never publishes.

This module owns the parts that are portable and verifiable without an ARM
executor:

* the smoke-result contract (which libretro entry points must succeed),
* validation of a captured result,
* merging a result into a fitness record's ``runtime_smoke`` field, and
* eligibility promotion: a captured runtime pass on a device's provider
  overrides the static ABI screen (an over-ceiling core that actually runs
  becomes runtime-verified for that device).

The ARM executor that produces raw results is a thin, dispatched adapter; it is
intentionally not implemented here.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = 1

# Ordered libretro entry points a content-free load smoke must exercise. Passing
# all of them means the core resolved its symbols, reported the API version,
# negotiated the environment, initialised, reported its static system info, and
# tore down cleanly under the target ABI. dlopen is where an insufficient device
# provider (an unmet GLIBCXX version) fails, and retro_init runs the core's real
# construction, so this sequence is the device-fitness signal. Content-dependent
# calls (retro_get_system_av_info, retro_run) need a loaded game and belong to a
# later playability tier, not this smoke.
SMOKE_CHECKS: tuple[str, ...] = (
    "dlopen",
    "retro_api_version",
    "retro_set_environment",
    "retro_init",
    "retro_get_system_info",
    "retro_deinit",
)

RUNNERS = ("qemu-user", "native-arm64", "fake")
ARCHITECTURES = ("arm64", "armhf")
STATUSES = ("pass", "fail", "skip")


class RuntimeSmokeError(Exception):
    """Raised for malformed smoke results."""


def build_smoke_result(
    *,
    core_id: str,
    architecture: str,
    runner: str,
    provider_profile: str,
    checks: Mapping[str, bool],
    frames: int = 0,
) -> dict[str, Any]:
    """Normalise one core/ABI load smoke into a validated result record.

    ``provider_profile`` is the device contract id whose provider libraries the
    core was loaded against, so a result is only ever credited to the device it
    was actually exercised on. ``frames`` is informational: the content-free load
    smoke leaves it at 0; a later playability tier records frames actually run.
    """

    if architecture not in ARCHITECTURES:
        raise RuntimeSmokeError(f"unknown architecture: {architecture}")
    if runner not in RUNNERS:
        raise RuntimeSmokeError(f"unknown runner: {runner}")
    if frames < 0:
        raise RuntimeSmokeError("frames must be non-negative")
    missing = set(SMOKE_CHECKS) - set(checks)
    if missing:
        raise RuntimeSmokeError(
            "smoke result is missing checks: " + ", ".join(sorted(missing))
        )
    unexpected = set(checks) - set(SMOKE_CHECKS)
    if unexpected:
        raise RuntimeSmokeError(
            "smoke result has unknown checks: " + ", ".join(sorted(unexpected))
        )
    passed = all(checks[name] for name in SMOKE_CHECKS)
    return {
        "schema_version": SCHEMA_VERSION,
        "core_id": core_id,
        "architecture": architecture,
        "runner": runner,
        "provider_profile": provider_profile,
        "checks": {name: bool(checks[name]) for name in SMOKE_CHECKS},
        "frames": frames,
        "status": "pass" if passed else "fail",
        "local_only": True,
        "publication": "disabled",
    }


def validate_smoke_result(result: object) -> list[str]:
    """Return a list of shape errors for one smoke result (empty means valid)."""

    errors: list[str] = []
    if not isinstance(result, dict):
        return ["smoke result must be an object"]
    for key in ("core_id", "provider_profile"):
        if not isinstance(result.get(key), str) or not result.get(key):
            errors.append(f"{key} must be a non-empty string")
    if result.get("architecture") not in ARCHITECTURES:
        errors.append("architecture is invalid")
    if result.get("runner") not in RUNNERS:
        errors.append("runner is invalid")
    if result.get("status") not in STATUSES:
        errors.append("status is invalid")
    frames = result.get("frames")
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < 0:
        errors.append("frames must be a non-negative integer")
    checks = result.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(SMOKE_CHECKS):
        errors.append("checks must cover exactly the smoke checks")
    elif not all(isinstance(value, bool) for value in checks.values()):
        errors.append("each check must be a boolean")
    else:
        expected = "pass" if all(checks.values()) else "fail"
        if result.get("status") in STATUSES and result.get("status") != "skip" and result.get("status") != expected:
            errors.append("status does not match its checks")
    return errors


def _summarise(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": result["status"],
        "runner": result["runner"],
        "provider_profile": result["provider_profile"],
        "frames": result["frames"],
    }


def apply_to_fitness(
    fitness: Mapping[str, Any], results: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return a copy of a fitness record with runtime_smoke filled from results.

    Only results whose ``core_id`` matches and whose architecture is a present
    target are applied; unmatched targets keep their ``pending`` marker.
    """

    updated = copy.deepcopy(dict(fitness))
    core_id = updated.get("core_id")
    targets = updated.get("targets", {})
    by_arch: dict[str, Mapping[str, Any]] = {}
    for result in results:
        if result.get("core_id") != core_id:
            continue
        errors = validate_smoke_result(result)
        if errors:
            raise RuntimeSmokeError("; ".join(errors))
        by_arch[result["architecture"]] = result
    for architecture, target in targets.items():
        if architecture in by_arch:
            target["runtime_smoke"] = _summarise(by_arch[architecture])
    return updated


def annotate_device_set(
    device_view: Mapping[str, Any], smoke_status_by_core: Mapping[str, str]
) -> dict[str, Any]:
    """Overlay captured runtime results onto one device's static screen.

    ``smoke_status_by_core`` maps core_id -> status for runs on *this* device's
    provider. A ``pass`` promotes the core to ``runtime_verified`` regardless of
    its static bucket (the runtime overrides the ABI screen); a ``fail`` moves it
    to ``runtime_failed``. Cores without a result keep their static bucket.
    """

    buckets = (
        "eligible",
        "eligible_ceiling_uncaptured",
        "over_ceiling",
        "policy_excluded",
        "no_arch_target",
    )
    view = copy.deepcopy(dict(device_view))
    verified: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for name in buckets:
        remaining: list[dict[str, Any]] = []
        for row in view.get(name, []):
            status = smoke_status_by_core.get(row.get("core"))
            if status == "pass":
                verified.append({**row, "from": name})
            elif status == "fail":
                failed.append({**row, "from": name})
            else:
                remaining.append(row)
        view[name] = remaining
    view["runtime_verified"] = sorted(verified, key=lambda row: row["core"])
    view["runtime_failed"] = sorted(failed, key=lambda row: row["core"])
    view["counts"] = {
        name: len(view[name])
        for name in (*buckets, "runtime_verified", "runtime_failed")
    }
    return view


__all__ = [
    "SCHEMA_VERSION",
    "SMOKE_CHECKS",
    "RuntimeSmokeError",
    "annotate_device_set",
    "apply_to_fitness",
    "build_smoke_result",
    "validate_smoke_result",
]
