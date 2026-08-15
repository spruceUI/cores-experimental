"""Strict chipset tuning profiles for core-track inventories.

The public vocabulary is deliberately typed.  A profile describes intent;
code owns the only mapping from that intent to compiler arguments.  Raw flags,
environment assignments, make variables, and shell fragments are not accepted
as tuning data.
"""

from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
import json
import re
from typing import Any

from .errors import PipelineError


REAL_CHIPSETS = (
    "a133p",
    "a33",
    "a523",
    "h700",
    "rk3326",
    "rk3566",
    "ssd202d",
)
CHIPSETS = ("universal", *REAL_CHIPSETS)
CHIPSET_ARCHITECTURES = {
    "universal": "any",
    "a133p": "arm64",
    "a33": "armhf",
    "a523": "arm64",
    "h700": "arm64",
    "rk3326": "arm64",
    "rk3566": "arm64",
    "ssd202d": "armhf",
}
CHIPSET_TUNING_SCHEMA_REF = "./chipset-tunings.schema.json"
CHIPSET_TUNING_SCHEMA_VERSION = 1
UNIVERSAL_TUNING_PROFILE = "universal-v1"
COMPILER_ARGUMENT_MAPPING_VERSION = "gcc-machine-flags-v1"

PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-v[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CPU_TARGETS = ("cortex-a7", "cortex-a35", "cortex-a53", "cortex-a55")
FPU_TARGETS = ("neon-vfpv4",)
FLOAT_ABIS = ("hard",)
PROPERTY_KEYS = frozenset({"cpu_target", "tune_target", "fpu", "float_abi"})


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def chipset_tunings_content_sha256(document: Mapping[str, Any]) -> str:
    """Hash the complete semantic tuning registry."""

    return _semantic_sha256(
        {
            "schema_version": document.get("schema_version"),
            "compiler_argument_mapping_version": document.get(
                "compiler_argument_mapping_version"
            ),
            "chipsets": document.get("chipsets"),
            "profiles": document.get("profiles"),
        }
    )


def _properties_errors(
    value: object,
    *,
    architecture: object,
    label: str,
) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{label} must be an object"]
    errors: list[str] = []
    unknown = sorted(set(value) - PROPERTY_KEYS)
    if unknown:
        errors.append(f"{label} contains unsupported properties: " + ", ".join(unknown))
    cpu = value.get("cpu_target")
    tune = value.get("tune_target")
    if cpu is not None and cpu not in CPU_TARGETS:
        errors.append(f"{label}.cpu_target is invalid")
    if tune is not None and tune not in CPU_TARGETS:
        errors.append(f"{label}.tune_target is invalid")
    if value.get("fpu") is not None and value.get("fpu") not in FPU_TARGETS:
        errors.append(f"{label}.fpu is invalid")
    if (
        value.get("float_abi") is not None
        and value.get("float_abi") not in FLOAT_ABIS
    ):
        errors.append(f"{label}.float_abi is invalid")
    if architecture == "arm64" and any(key in value for key in ("fpu", "float_abi")):
        errors.append(f"{label} arm64 profiles cannot set fpu or float_abi")
    if architecture == "armhf" and cpu in {"cortex-a35", "cortex-a53", "cortex-a55"}:
        errors.append(f"{label}.cpu_target is incompatible with armhf")
    if architecture == "armhf" and tune in {"cortex-a35", "cortex-a53", "cortex-a55"}:
        errors.append(f"{label}.tune_target is incompatible with armhf")
    if architecture == "arm64" and cpu == "cortex-a7":
        errors.append(f"{label}.cpu_target is incompatible with arm64")
    if architecture == "arm64" and tune == "cortex-a7":
        errors.append(f"{label}.tune_target is incompatible with arm64")
    return errors


def _resolve_profile_properties(
    profiles: Mapping[str, object],
    profile_id: str,
    *,
    active: tuple[str, ...] = (),
) -> dict[str, str]:
    if profile_id in active:
        raise PipelineError(
            "chipset tuning profile inheritance is cyclic: "
            + " -> ".join((*active, profile_id))
        )
    profile = profiles.get(profile_id)
    if not isinstance(profile, Mapping):
        raise PipelineError(f"unknown chipset tuning profile: {profile_id}")
    parent = profile.get("extends")
    resolved: dict[str, str] = {}
    if isinstance(parent, str):
        resolved.update(
            _resolve_profile_properties(
                profiles, parent, active=(*active, profile_id)
            )
        )
    properties = profile.get("properties")
    if not isinstance(properties, Mapping):
        raise PipelineError(f"chipset tuning profile is malformed: {profile_id}")
    resolved.update({str(key): str(value) for key, value in properties.items()})
    return resolved


def chipset_tuning_errors(document: object) -> list[str]:
    """Return strict, deterministic tuning-registry errors."""

    if not isinstance(document, Mapping):
        return ["chipset tunings must be an object"]
    expected_fields = {
        "$schema",
        "schema_version",
        "compiler_argument_mapping_version",
        "chipsets",
        "profiles",
        "content_sha256",
    }
    if set(document) != expected_fields:
        return ["chipset tuning fields are not exact"]
    errors: list[str] = []
    if document.get("$schema") != CHIPSET_TUNING_SCHEMA_REF:
        errors.append("chipset tuning schema reference is invalid")
    if (
        type(document.get("schema_version")) is not int
        or document.get("schema_version") != CHIPSET_TUNING_SCHEMA_VERSION
    ):
        errors.append("chipset tuning schema_version is invalid")
    if (
        document.get("compiler_argument_mapping_version")
        != COMPILER_ARGUMENT_MAPPING_VERSION
    ):
        errors.append("chipset tuning compiler argument mapping version is invalid")

    chipsets = document.get("chipsets")
    if not isinstance(chipsets, Mapping) or set(chipsets) != set(CHIPSETS):
        errors.append("chipsets must contain exactly: " + ", ".join(CHIPSETS))
    else:
        for chipset in CHIPSETS:
            value = chipsets.get(chipset)
            label = f"chipsets.{chipset}"
            if not isinstance(value, Mapping) or set(value) != {
                "architecture",
                "fallback",
            }:
                errors.append(f"{label} fields must be exactly architecture and fallback")
                continue
            if value.get("architecture") != CHIPSET_ARCHITECTURES[chipset]:
                errors.append(f"{label}.architecture is invalid")
            expected_fallback = None if chipset == "universal" else "universal"
            if value.get("fallback") != expected_fallback:
                errors.append(f"{label}.fallback is invalid")

    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        errors.append("chipset tuning profiles must be a nonempty object")
    else:
        if list(profiles) != sorted(profiles):
            errors.append("chipset tuning profiles must be sorted by profile ID")
        for profile_id, profile in profiles.items():
            label = f"profiles.{profile_id}"
            if not isinstance(profile_id, str) or PROFILE_ID_RE.fullmatch(profile_id) is None:
                errors.append(f"{label} profile ID is invalid")
            if not isinstance(profile, Mapping) or set(profile) != {
                "extends",
                "chipset",
                "architecture",
                "properties",
            }:
                errors.append(
                    f"{label} fields must be exactly extends, chipset, architecture, and properties"
                )
                continue
            parent = profile.get("extends")
            if parent is not None and (
                not isinstance(parent, str) or parent not in profiles
            ):
                errors.append(f"{label}.extends is invalid")
            chipset = profile.get("chipset")
            if chipset not in CHIPSETS:
                errors.append(f"{label}.chipset is invalid")
                continue
            architecture = profile.get("architecture")
            if architecture != CHIPSET_ARCHITECTURES[chipset]:
                errors.append(f"{label}.architecture is invalid")
            errors.extend(
                _properties_errors(
                    profile.get("properties"),
                    architecture=architecture,
                    label=f"{label}.properties",
                )
            )
            if isinstance(parent, str) and isinstance(profiles.get(parent), Mapping):
                parent_profile = profiles[parent]
                if parent != UNIVERSAL_TUNING_PROFILE and (
                    parent_profile.get("chipset") != chipset
                    or parent_profile.get("architecture") != architecture
                ):
                    errors.append(
                        f"{label}.extends crosses a chipset or architecture boundary"
                    )
        if UNIVERSAL_TUNING_PROFILE not in profiles:
            errors.append("universal tuning profile is missing")
        else:
            universal = profiles[UNIVERSAL_TUNING_PROFILE]
            if universal != {
                "extends": None,
                "chipset": "universal",
                "architecture": "any",
                "properties": {},
            }:
                errors.append("universal tuning profile must be the exact empty profile")
        for profile_id in profiles:
            try:
                resolved = _resolve_profile_properties(profiles, profile_id)
            except PipelineError as exc:
                errors.append(str(exc))
                continue
            profile = profiles[profile_id]
            architecture = profile.get("architecture")
            errors.extend(
                _properties_errors(
                    resolved,
                    architecture=architecture,
                    label=f"profiles.{profile_id}.resolved_properties",
                )
            )
            if architecture == "armhf" and resolved:
                required = {
                    "cpu_target": "cortex-a7",
                    "fpu": "neon-vfpv4",
                    "float_abi": "hard",
                }
                if any(resolved.get(key) != value for key, value in required.items()):
                    errors.append(
                        f"profiles.{profile_id} armhf tuning requires the complete "
                        "cortex-a7/neon-vfpv4/hard triple"
                    )
            if resolved.get("cpu_target") == resolved.get("tune_target") and (
                "cpu_target" in resolved and "tune_target" in resolved
            ):
                errors.append(
                    f"profiles.{profile_id} redundantly repeats cpu_target as tune_target"
                )

    digest = document.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        errors.append("chipset tuning content_sha256 is invalid")
    elif digest != chipset_tunings_content_sha256(document):
        errors.append("chipset tuning content_sha256 is stale")
    return errors


def validate_chipset_tunings(document: object) -> dict[str, Any]:
    """Require and independently copy one complete tuning registry."""

    errors = chipset_tuning_errors(document)
    if errors:
        raise PipelineError("invalid chipset tunings:\n- " + "\n- ".join(errors))
    assert isinstance(document, Mapping)
    return copy.deepcopy(dict(document))


def resolved_tuning_profile(
    document: object, profile_id: str
) -> dict[str, Any]:
    """Resolve one profile to immutable typed properties and their identity."""

    validated = validate_chipset_tunings(document)
    profiles = validated["profiles"]
    if profile_id not in profiles:
        raise PipelineError(f"unknown chipset tuning profile: {profile_id}")
    profile = profiles[profile_id]
    properties = _resolve_profile_properties(profiles, profile_id)
    compiler_arguments = _compiler_arguments_for_properties(properties)
    material = {
        "profile_id": profile_id,
        "chipset": profile["chipset"],
        "architecture": profile["architecture"],
        "properties": properties,
        "compiler_argument_mapping_version": COMPILER_ARGUMENT_MAPPING_VERSION,
        "compiler_arguments": compiler_arguments,
    }
    return {**material, "content_sha256": _semantic_sha256(material)}


def _compiler_arguments_for_properties(properties: Mapping[str, str]) -> list[str]:
    arguments: list[str] = []
    mapping = (
        ("cpu_target", "-mcpu="),
        ("tune_target", "-mtune="),
        ("fpu", "-mfpu="),
        ("float_abi", "-mfloat-abi="),
    )
    for key, prefix in mapping:
        if key in properties:
            arguments.append(prefix + properties[key])
    return arguments


def compiler_arguments_for_profile(document: object, profile_id: str) -> list[str]:
    """Return the versioned allowlisted compiler arguments for one profile."""

    resolved = resolved_tuning_profile(document, profile_id)
    return copy.deepcopy(resolved["compiler_arguments"])
