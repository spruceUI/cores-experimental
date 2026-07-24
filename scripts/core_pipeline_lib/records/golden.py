"""Exact-one-core golden document construction."""

from __future__ import annotations

import copy
from collections.abc import Mapping
import datetime as dt
import re

from ..errors import PipelineError


CORE_GOLDEN_SCHEMA_REF = "../../../manifests/core-golden.schema.json"
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
PIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*-[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_TOP_LEVEL_FIELDS = {
    "$schema",
    "schema_version",
    "core_id",
    "pin_id",
    "created_at",
    "updated_at",
    "local_only",
    "publication",
    "baseline",
    "summary",
    "build_goldens",
    "cores",
    "content_sha256",
}
_BASELINE_FIELDS = {"kind", "repository_commit", "provenance", "warning"}
_SUMMARY_FIELDS = {
    "core_count",
    "valid_artifact_count",
    "invalid_artifacts",
    "cores_without_valid_artifacts",
}
_CORE_RECORD_FIELDS = {"workflow", "tier", "promotion_eligible", "artifacts"}
_IMPORTED_ARTIFACT_FIELDS = {
    "path",
    "status",
    "size",
    "sha256",
    "elf",
    "needed",
    "version_requirements",
    "libretro_symbols",
    "errors",
}
_ELF_FIELDS = {"class", "data", "type", "machine", "flags"}
_ARCHITECTURES = {"arm64", "armhf"}


def candidate_golden_id_is_well_formed(core_id: object, candidate_id: object) -> bool:
    """Return whether an active imported-candidate ID is core-owned and new."""

    if (
        not isinstance(core_id, str)
        or CORE_ID_RE.fullmatch(core_id) is None
        or not isinstance(candidate_id, str)
        or len(candidate_id) > 128
        or PIN_ID_RE.fullmatch(candidate_id) is None
    ):
        return False
    prefix = f"{core_id}-candidate-"
    label = candidate_id.removeprefix(prefix)
    return (
        candidate_id.startswith(prefix)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", label) is not None
        and "tranche" not in candidate_id.casefold()
    )


def _is_string_list(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and len(value) == len(set(value))
    )


def _is_aware_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.utcoffset() == dt.timedelta(0)


def _imported_artifact_shape_errors(
    artifact: object,
    label: str,
) -> list[str]:
    if not isinstance(artifact, dict):
        return [f"{label}: imported artifact must be an object"]
    status = artifact.get("status")
    if status == "not_shipped":
        return [] if set(artifact) == {"status"} else [
            f"{label}: not-shipped artifact fields are not exact"
        ]
    errors: list[str] = []
    if set(artifact) != _IMPORTED_ARTIFACT_FIELDS:
        errors.append(f"{label}: imported artifact fields are not exact")
    if status not in {"valid", "invalid"}:
        errors.append(f"{label}: imported artifact status is invalid")
    if not isinstance(artifact.get("path"), str) or not artifact["path"]:
        errors.append(f"{label}: imported artifact path is invalid")
    if type(artifact.get("size")) is not int or artifact["size"] <= 0:
        errors.append(f"{label}: imported artifact size is invalid")
    if not isinstance(artifact.get("sha256"), str) or SHA256_RE.fullmatch(
        artifact["sha256"]
    ) is None:
        errors.append(f"{label}: imported artifact SHA256 is invalid")
    elf = artifact.get("elf")
    if (
        not isinstance(elf, dict)
        or set(elf) != _ELF_FIELDS
        or any(not isinstance(value, str) or not value for value in elf.values())
    ):
        errors.append(f"{label}: imported artifact ELF metadata is invalid")
    for field in ("needed", "version_requirements", "libretro_symbols"):
        if not _is_string_list(artifact.get(field)):
            errors.append(f"{label}: imported artifact {field} is invalid")
    artifact_errors = artifact.get("errors")
    if not _is_string_list(artifact_errors):
        errors.append(f"{label}: imported artifact errors are invalid")
    elif status == "valid" and artifact_errors:
        errors.append(f"{label}: valid imported artifact has errors")
    elif status == "invalid" and not artifact_errors:
        errors.append(f"{label}: invalid imported artifact lacks errors")
    return errors


def core_golden_v2_shape_errors(document: object) -> list[str]:
    """Validate strict schema-v2 structure before semantic/store checks."""

    if not isinstance(document, dict):
        return ["schema-v2 core golden must be an object"]
    errors: list[str] = []
    document_fields = set(document)
    if document_fields != _TOP_LEVEL_FIELDS and document_fields != (
        _TOP_LEVEL_FIELDS - {"updated_at"}
    ):
        errors.append("schema-v2 core golden fields are not exact")
    if document.get("$schema") != CORE_GOLDEN_SCHEMA_REF:
        errors.append("schema-v2 core golden schema reference is invalid")
    if document.get("schema_version") != 2:
        errors.append("schema-v2 core golden schema_version is invalid")
    core_id = document.get("core_id")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        errors.append("schema-v2 core golden core_id is invalid")
    pin_id = document.get("pin_id")
    if (
        not isinstance(pin_id, str)
        or len(pin_id) > 128
        or PIN_ID_RE.fullmatch(pin_id) is None
        or not isinstance(core_id, str)
        or not pin_id.startswith(f"{core_id}-")
    ):
        errors.append("schema-v2 core golden pin_id is invalid")
    if document.get("local_only") is not True:
        errors.append("schema-v2 core golden must be local-only")
    if document.get("publication") != "disabled":
        errors.append("schema-v2 core golden publication is invalid")
    if not _is_aware_utc_timestamp(document.get("created_at")):
        errors.append("schema-v2 core golden created_at must be an aware UTC timestamp")
    if "updated_at" in document and not _is_aware_utc_timestamp(
        document.get("updated_at")
    ):
        errors.append("schema-v2 core golden updated_at must be an aware UTC timestamp")

    baseline = document.get("baseline")
    if not isinstance(baseline, dict) or set(baseline) != _BASELINE_FIELDS:
        errors.append("schema-v2 core golden baseline fields are not exact")
    elif (
        baseline.get("kind") != "spruceos-shipped-artifacts"
        or not isinstance(baseline.get("repository_commit"), str)
        or SHA1_RE.fullmatch(baseline["repository_commit"]) is None
        or baseline.get("provenance") != "artifact-only"
        or not isinstance(baseline.get("warning"), str)
        or not baseline["warning"]
    ):
        errors.append("schema-v2 core golden baseline is invalid")

    summary = document.get("summary")
    if not isinstance(summary, dict) or set(summary) != _SUMMARY_FIELDS:
        errors.append("schema-v2 core golden summary fields are not exact")
    else:
        if type(summary.get("core_count")) is not int or summary["core_count"] != 1:
            errors.append("schema-v2 core golden summary.core_count is invalid")
        valid_count = summary.get("valid_artifact_count")
        if type(valid_count) is not int or not 0 <= valid_count <= 2:
            errors.append(
                "schema-v2 core golden summary.valid_artifact_count is invalid"
            )
        invalid_artifacts = summary.get("invalid_artifacts")
        if not _is_string_list(invalid_artifacts) or any(
            re.fullmatch(r"[a-z0-9][a-z0-9_]*/(arm64|armhf)", item) is None
            for item in invalid_artifacts or []
        ):
            errors.append(
                "schema-v2 core golden summary.invalid_artifacts is invalid"
            )
        missing_cores = summary.get("cores_without_valid_artifacts")
        if (
            not _is_string_list(missing_cores)
            or len(missing_cores) > 1
            or any(CORE_ID_RE.fullmatch(item) is None for item in missing_cores or [])
        ):
            errors.append(
                "schema-v2 core golden summary.cores_without_valid_artifacts is invalid"
            )

    cores = document.get("cores")
    if not isinstance(cores, dict) or not isinstance(core_id, str) or set(cores) != {
        core_id
    }:
        errors.append("schema-v2 cores must contain exactly core_id")
    else:
        record = cores[core_id]
        if not isinstance(record, dict) or set(record) != _CORE_RECORD_FIELDS:
            errors.append(f"{core_id}: schema-v2 core record fields are not exact")
        else:
            if (
                not isinstance(record.get("workflow"), str)
                or re.fullmatch(
                    r"\.github/workflows/build-[A-Za-z0-9._-]+\.ya?ml",
                    record["workflow"],
                )
                is None
                or record.get("tier") != "imported_baseline"
                or record.get("promotion_eligible") is not False
            ):
                errors.append(f"{core_id}: schema-v2 core record identity is invalid")
            artifacts = record.get("artifacts")
            if not isinstance(artifacts, dict) or set(artifacts) != _ARCHITECTURES:
                errors.append(f"{core_id}: schema-v2 artifact map is not exact")
            else:
                for architecture in sorted(_ARCHITECTURES):
                    errors.extend(
                        _imported_artifact_shape_errors(
                            artifacts[architecture],
                            f"{core_id}/{architecture}",
                        )
                    )

    build_goldens = document.get("build_goldens")
    if (
        not isinstance(build_goldens, dict)
        or not isinstance(core_id, str)
        or set(build_goldens) != {core_id}
    ):
        errors.append("schema-v2 build_goldens must contain exactly core_id")
    else:
        targets = build_goldens[core_id]
        if (
            not isinstance(targets, dict)
            or not set(targets).issubset(_ARCHITECTURES)
            or any(not isinstance(record, dict) for record in targets.values())
        ):
            errors.append(f"{core_id}: schema-v2 build-golden map is invalid")
    if not isinstance(document.get("content_sha256"), str) or SHA256_RE.fullmatch(
        document["content_sha256"]
    ) is None:
        errors.append("schema-v2 core golden content SHA256 is invalid")
    return errors


def require_active_core_golden(document: object, core_id: object) -> dict:
    """Require schema-v2 state whose baseline and evidence maps own one core."""

    cores = document.get("cores") if isinstance(document, dict) else None
    build_goldens = (
        document.get("build_goldens") if isinstance(document, dict) else None
    )
    if (
        not isinstance(document, dict)
        or not isinstance(core_id, str)
        or document.get("schema_version") != 2
        or document.get("core_id") != core_id
        or not isinstance(cores, dict)
        or set(cores) != {core_id}
        or not isinstance(build_goldens, dict)
        or set(build_goldens) != {core_id}
    ):
        raise PipelineError(
            "active core golden must be schema-v2 state owned by exactly its core"
        )
    return document


def one_core_golden_summary(core_id: str, core_record: Mapping) -> dict:
    """Summarize one imported baseline record without cross-core state."""

    artifacts = core_record.get("artifacts", {})
    valid_count = sum(
        artifact.get("status") == "valid" for artifact in artifacts.values()
    )
    invalid_artifacts = sorted(
        f"{core_id}/{architecture}"
        for architecture, artifact in artifacts.items()
        if artifact.get("status") == "invalid"
    )
    return {
        "core_count": 1,
        "valid_artifact_count": valid_count,
        "invalid_artifacts": invalid_artifacts,
        "cores_without_valid_artifacts": [] if valid_count else [core_id],
    }


def one_core_golden_document(
    *,
    core_id: str,
    pin_id: str,
    created_at: str,
    baseline: Mapping,
    core_record: Mapping,
    build_goldens: Mapping,
    updated_at: str | None = None,
) -> dict:
    """Construct schema-v2 state for one core; the caller binds its digest."""

    document = {
        "$schema": CORE_GOLDEN_SCHEMA_REF,
        "schema_version": 2,
        "core_id": core_id,
        "pin_id": pin_id,
        "created_at": created_at,
        "local_only": True,
        "publication": "disabled",
        "baseline": copy.deepcopy(dict(baseline)),
        "summary": one_core_golden_summary(core_id, core_record),
        "build_goldens": {core_id: copy.deepcopy(dict(build_goldens))},
        "cores": {core_id: copy.deepcopy(dict(core_record))},
    }
    if updated_at is not None:
        document["updated_at"] = updated_at
    return document
