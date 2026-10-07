"""Strict optimization profiles, orthogonal to chipset tuning.

The vocabulary is typed the same way chipset tuning is: a profile describes
intent and code owns the only mapping from that intent to build inputs.  Raw
flags and shell fragments are not accepted as optimization data.

Optimization cannot ride on CFLAGS the way tuning does.  A core's own makefile
appends its optimization level after the environment's CFLAGS, and GCC lets the
last ``-O`` win, so an injected ``-O`` is silently discarded.  A profile
therefore declares a make variable (intent ``variant``) and the ``-O`` level it
must produce (intent ``expect_opt_level``); the build contract proves the level
in the build log.  Asserting the outcome rather than the input is what keeps a
profile from quietly shipping an optimization level it did not ask for.
"""

from __future__ import annotations

from collections.abc import Mapping
import copy
import hashlib
import json
import re
from typing import Any

from .errors import PipelineError


BUILD_ARGUMENT_MAPPING_VERSION = "libretro-make-optimization-v1"
BASELINE_OPTIMIZATION_PROFILE = "release-v1"

PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*-v[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VARIANTS = ("release", "debug")
OPT_LEVELS = ("0", "1", "2", "3", "s")
PROPERTY_KEYS = frozenset({"variant", "expect_opt_level", "expect_debug_info"})
# libretro's conventional switch: cores declare DEBUG ?= 0 and gate -O0 -g on it.
VARIANT_MAKE_VARIABLES = {"release": ("DEBUG", "0"), "debug": ("DEBUG", "1")}


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def optimization_profiles_content_sha256(document: Mapping[str, Any]) -> str:
    """Hash the complete semantic optimization registry."""

    return _semantic_sha256(
        {
            "schema_version": document.get("schema_version"),
            "build_argument_mapping_version": document.get(
                "build_argument_mapping_version"
            ),
            "profiles": document.get("profiles"),
        }
    )


def _properties_errors(value: object, *, label: str) -> list[str]:
    if not isinstance(value, Mapping):
        return [f"{label} must be an object"]
    errors: list[str] = []
    unknown = sorted(set(value) - PROPERTY_KEYS)
    if unknown:
        errors.append(f"{label} contains unsupported properties: " + ", ".join(unknown))
    variant = value.get("variant")
    if variant is not None and variant not in VARIANTS:
        errors.append(f"{label}.variant is invalid")
    level = value.get("expect_opt_level")
    if level is not None and level not in OPT_LEVELS:
        errors.append(f"{label}.expect_opt_level is invalid")
    debug_info = value.get("expect_debug_info")
    if debug_info is not None and not isinstance(debug_info, bool):
        errors.append(f"{label}.expect_debug_info must be a boolean")
    if value and variant is None:
        errors.append(f"{label} must name a variant whenever it sets any property")
    # A debug variant that does not expect -O0 would assert nothing useful, and a
    # release variant expecting -O0 contradicts itself.
    if variant == "debug" and level not in (None, "0"):
        errors.append(f"{label}.expect_opt_level must be 0 for the debug variant")
    if variant == "release" and level == "0":
        errors.append(f"{label}.expect_opt_level 0 contradicts the release variant")
    return errors


def _resolve_profile_properties(
    profiles: Mapping[str, object],
    profile_id: str,
    *,
    active: tuple[str, ...] = (),
) -> dict[str, Any]:
    if profile_id in active:
        raise PipelineError(
            "optimization profile inheritance is cyclic: "
            + " -> ".join((*active, profile_id))
        )
    profile = profiles.get(profile_id)
    if not isinstance(profile, Mapping):
        raise PipelineError(f"unknown optimization profile: {profile_id}")
    parent = profile.get("extends")
    resolved: dict[str, Any] = {}
    if isinstance(parent, str):
        resolved.update(
            _resolve_profile_properties(profiles, parent, active=(*active, profile_id))
        )
    properties = profile.get("properties")
    if isinstance(properties, Mapping):
        resolved.update(properties)
    elif properties is not None:
        raise PipelineError(f"optimization profile is malformed: {profile_id}")
    return resolved


def optimization_profile_errors(document: object) -> list[str]:
    """Collect every structural fault in one optimization registry."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return ["optimization profiles must be an object"]
    if set(document) != {
        "$schema",
        "schema_version",
        "build_argument_mapping_version",
        "profiles",
        "content_sha256",
    }:
        return ["optimization profile fields are not exact"]
    if document.get("$schema") != "./optimization-profiles.schema.json":
        errors.append("optimization schema reference is invalid")
    if document.get("schema_version") != 1:
        errors.append("optimization schema_version is invalid")
    if document.get("build_argument_mapping_version") != BUILD_ARGUMENT_MAPPING_VERSION:
        errors.append("optimization build argument mapping version is invalid")

    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        errors.append("optimization profiles must be a nonempty object")
    else:
        if list(profiles) != sorted(profiles):
            errors.append("optimization profiles must be sorted by profile ID")
        for profile_id, profile in profiles.items():
            label = f"profiles.{profile_id}"
            if not isinstance(profile_id, str) or PROFILE_ID_RE.fullmatch(profile_id) is None:
                errors.append(f"{label} profile ID is invalid")
            if not isinstance(profile, Mapping) or set(profile) != {
                "extends",
                "properties",
            }:
                errors.append(f"{label} fields must be exactly extends and properties")
                continue
            parent = profile.get("extends")
            if parent is not None and (
                not isinstance(parent, str) or parent not in profiles
            ):
                errors.append(f"{label}.extends is invalid")
            errors.extend(
                _properties_errors(
                    profile.get("properties"), label=f"{label}.properties"
                )
            )
        if BASELINE_OPTIMIZATION_PROFILE not in profiles:
            errors.append("baseline optimization profile is missing")
        else:
            baseline = profiles[BASELINE_OPTIMIZATION_PROFILE]
            if baseline != {"extends": None, "properties": {}}:
                errors.append(
                    "baseline optimization profile must be the exact empty profile"
                )
        for profile_id in profiles:
            try:
                resolved = _resolve_profile_properties(profiles, profile_id)
            except PipelineError as exc:
                errors.append(str(exc))
                continue
            errors.extend(
                _properties_errors(
                    resolved, label=f"profiles.{profile_id}.resolved_properties"
                )
            )

    digest = document.get("content_sha256")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        errors.append("optimization content_sha256 is invalid")
    elif digest != optimization_profiles_content_sha256(document):
        errors.append("optimization content_sha256 is stale")
    return errors


def validate_optimization_profiles(document: object) -> dict[str, Any]:
    """Require and independently copy one complete optimization registry."""

    errors = optimization_profile_errors(document)
    if errors:
        raise PipelineError(
            "invalid optimization profiles:\n- " + "\n- ".join(errors)
        )
    assert isinstance(document, Mapping)
    return copy.deepcopy(dict(document))


def _make_variables_for_properties(
    properties: Mapping[str, Any],
) -> list[str]:
    variant = properties.get("variant")
    if variant is None:
        return []
    name, value = VARIANT_MAKE_VARIABLES[variant]
    return [f"{name}={value}"]


def _expected_compile_tokens(properties: Mapping[str, Any]) -> list[str]:
    tokens: list[str] = []
    level = properties.get("expect_opt_level")
    if level is not None:
        tokens.append(f"-O{level}")
    if properties.get("expect_debug_info"):
        tokens.append("-g")
    return tokens


def resolved_optimization_profile(
    document: object, profile_id: str
) -> dict[str, Any]:
    """Resolve one profile to immutable typed properties and their identity."""

    validated = validate_optimization_profiles(document)
    profiles = validated["profiles"]
    if profile_id not in profiles:
        raise PipelineError(f"unknown optimization profile: {profile_id}")
    properties = _resolve_profile_properties(profiles, profile_id)
    material = {
        "profile_id": profile_id,
        "properties": properties,
        "build_argument_mapping_version": BUILD_ARGUMENT_MAPPING_VERSION,
        "make_variables": _make_variables_for_properties(properties),
        "expected_compile_tokens": _expected_compile_tokens(properties),
    }
    return {**material, "content_sha256": _semantic_sha256(material)}


def make_variables_for_profile(document: object, profile_id: str) -> list[str]:
    """Return the versioned make-variable overrides for one profile."""

    resolved = resolved_optimization_profile(document, profile_id)
    return copy.deepcopy(resolved["make_variables"])


def require_supported_optimization_profile(profile_id: str | None) -> str:
    """Accept only a selection this pipeline can honestly honour.

    The registry and its identity are complete, but make-variable injection and
    the build-log proof are not wired into the drivers yet.  Until they are, a
    non-baseline selection must fail here: a core's own makefile would supply
    its optimization level and the run would record a profile it never applied.
    """

    if profile_id is None:
        return BASELINE_OPTIMIZATION_PROFILE
    if profile_id != BASELINE_OPTIMIZATION_PROFILE:
        raise PipelineError(
            f"optimization profile {profile_id} is not wired into the build "
            "drivers yet; only "
            f"{BASELINE_OPTIMIZATION_PROFILE} may be selected, and it "
            "contributes nothing"
        )
    return profile_id
