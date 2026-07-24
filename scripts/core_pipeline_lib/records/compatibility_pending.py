"""Strict transition records between a clean core contract and E2E admission."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from ..errors import PipelineError
from ..foundation import (
    load_json,
    require_manifest_reference_path,
    sha256_bytes,
)
from .compatibility import validate_core_compatibility_document


CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SCHEMA_REFERENCE = "../../core-compatibility-pending.schema.json"
PENDING_KEYS = {
    "$schema",
    "schema_version",
    "core_id",
    "state",
    "publication",
    "core_spec_sha256",
    "source_commit",
    "targets",
    "next_gate",
    "content_sha256",
}
PENDING_STATE = "awaiting-local-e2e"
NEXT_GATE = "selected-and-independent-reproduction-e2e"


def _canonical_sha256(value: object) -> str:
    return sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    )


def catalog_core_spec_sha256(spec: dict[str, Any]) -> str:
    """Bind a pending record to every field of one validated catalog spec."""

    return _canonical_sha256(spec)


def pending_compatibility_content_sha256(
    document: dict[str, Any],
) -> str:
    """Hash semantic pending state while excluding schema routing and itself."""

    return _canonical_sha256(
        {
            key: value
            for key, value in document.items()
            if key not in {"$schema", "content_sha256"}
        }
    )


def validate_pending_compatibility_document(
    document: dict[str, Any],
    *,
    document_path: Path | None,
    repository_root: Path,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Validate one non-admitting, exact catalog-to-E2E transition record."""

    errors: list[str] = []
    if set(document) != PENDING_KEYS:
        errors.append("pending compatibility fields are incomplete or unknown")
    if document.get("$schema") != SCHEMA_REFERENCE:
        errors.append("pending compatibility schema reference is invalid")
    if type(document.get("schema_version")) is not int or document.get(
        "schema_version"
    ) != 1:
        errors.append("pending compatibility schema_version must be 1")
    core_id = document.get("core_id")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        errors.append("pending compatibility core_id is invalid")
        core_id = ""
    if document.get("state") != PENDING_STATE:
        errors.append("pending compatibility state is invalid")
    if document.get("publication") != "disabled":
        errors.append("pending compatibility publication must remain disabled")
    if document.get("next_gate") != NEXT_GATE:
        errors.append("pending compatibility next gate is invalid")
    digest = document.get("content_sha256")
    if (
        not isinstance(digest, str)
        or SHA256_RE.fullmatch(digest) is None
        or digest != pending_compatibility_content_sha256(document)
    ):
        errors.append("pending compatibility content digest is invalid")

    cores = catalog.get("cores") if isinstance(catalog, dict) else None
    spec = cores.get(core_id) if isinstance(cores, dict) else None
    if not isinstance(spec, dict):
        errors.append("pending compatibility core is absent from the catalog")
        spec = {}
    expected_spec_sha256 = catalog_core_spec_sha256(spec)
    if document.get("core_spec_sha256") != expected_spec_sha256:
        errors.append("pending compatibility catalog core digest differs")
    source = spec.get("source") if isinstance(spec, dict) else None
    expected_commit = source.get("commit") if isinstance(source, dict) else None
    source_commit = document.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or SHA1_RE.fullmatch(source_commit) is None
        or source_commit != expected_commit
    ):
        errors.append("pending compatibility source commit differs")
    expected_targets = spec.get("targets") if isinstance(spec, dict) else None
    targets = document.get("targets")
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(target, str) for target in targets)
        or any(target not in {"arm64", "armhf"} for target in targets)
        or targets != sorted(set(targets))
        or not isinstance(expected_targets, list)
        or any(not isinstance(target, str) for target in expected_targets)
        or targets != sorted(expected_targets)
    ):
        errors.append("pending compatibility target set differs")

    if document_path is not None and core_id:
        expected_relative = (
            f"manifests/compatibility/pending/{core_id}.json"
        )
        try:
            expected_path = require_manifest_reference_path(
                {"path": expected_relative},
                repository_root / "manifests" / "compatibility" / "pending",
                "pending compatibility document",
                repository_root,
            )
            if document_path.absolute() != expected_path.absolute():
                errors.append("pending compatibility path does not bind core_id")
        except PipelineError as exc:
            errors.append(str(exc))
    return {
        "status": "valid" if not errors else "invalid",
        "core_id": core_id,
        "errors": errors,
    }


def load_pending_compatibility_records(
    *,
    pending_directory: Path,
    repository_root: Path,
    catalog: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Load exact pending records without admitting them as compatibility."""

    expected_directory = (
        repository_root / "manifests" / "compatibility" / "pending"
    )
    if pending_directory.absolute() != expected_directory.absolute():
        raise PipelineError(
            "pending compatibility directory is not the canonical path"
        )
    current = repository_root.absolute()
    for part in Path("manifests/compatibility/pending").parts:
        current /= part
        if current.is_symlink():
            raise PipelineError(
                "pending compatibility directory must not traverse a symlink"
            )
    if not pending_directory.is_dir():
        return {}

    records: dict[str, dict[str, Any]] = {}
    for path in sorted(pending_directory.glob("*.json")):
        document = load_json(path)
        report = validate_pending_compatibility_document(
            document,
            document_path=path,
            repository_root=repository_root,
            catalog=catalog,
        )
        if report["errors"]:
            raise PipelineError(
                f"invalid pending compatibility document {path}:\n- "
                + "\n- ".join(report["errors"])
            )
        core_id = document["core_id"]
        if core_id in records:
            raise PipelineError(
                f"duplicate pending compatibility record for {core_id}"
            )
        records[core_id] = document
    return records


def compatibility_coverage_errors(
    *,
    catalog_cores: set[str],
    compatibility_coverage_cores: set[str],
    golden_source_cores: set[str],
    pending_cores: set[str],
) -> list[str]:
    """Require exact, disjoint compatibility-or-pending catalog coverage."""

    errors: list[str] = []
    overlap = compatibility_coverage_cores & pending_cores
    if overlap:
        errors.append(
            "pending and compatibility coverage overlap: "
            + ", ".join(sorted(overlap))
        )
    pending_goldens = pending_cores & golden_source_cores
    if pending_goldens:
        errors.append(
            "pending compatibility appears in golden_sources: "
            + ", ".join(sorted(pending_goldens))
        )
    unknown_goldens = golden_source_cores - compatibility_coverage_cores
    if unknown_goldens:
        errors.append(
            "golden_sources names non-compatibility cores: "
            + ", ".join(sorted(unknown_goldens))
        )
    covered = compatibility_coverage_cores | pending_cores
    missing = catalog_cores - covered
    extra = covered - catalog_cores
    if missing:
        errors.append(
            "catalog cores lack compatibility or pending state: "
            + ", ".join(sorted(missing))
        )
    if extra:
        errors.append(
            "compatibility or pending state names uncataloged cores: "
            + ", ".join(sorted(extra))
        )
    return errors


def load_catalog_compatibility_coverage(
    *,
    catalog: dict[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    """Validate canonical admission and pending coverage.

    The aggregate-era legacy compatibility matrix was retired on 2026-07-23;
    every catalog core must be covered by a canonical per-core document or an
    explicit pending record.
    """

    canonical_directory = repository_root / "manifests" / "compatibility"
    pending_directory = canonical_directory / "pending"
    compatibility_coverage_cores: set[str] = set()
    golden_source_cores: set[str] = set()
    canonical_owners: set[str] = set()
    for path in sorted(canonical_directory.glob("*.json")):
        document = load_json(path)
        report = validate_core_compatibility_document(
            document,
            document_path=path,
            repository_root=repository_root,
            verify_pin=False,
        )
        if report["errors"]:
            raise PipelineError(
                f"invalid canonical compatibility document {path}:\n- "
                + "\n- ".join(report["errors"])
            )
        core_id = document.get("core_id")
        if (
            not isinstance(core_id, str)
            or CORE_ID_RE.fullmatch(core_id) is None
            or path.name != f"{core_id}.json"
        ):
            raise PipelineError(
                f"canonical compatibility path does not bind core_id: {path}"
            )
        if core_id in canonical_owners:
            raise PipelineError(
                f"duplicate canonical compatibility evidence for {core_id}"
            )
        canonical_owners.add(core_id)
        compatibility_coverage_cores.add(core_id)
        golden_source_cores.add(core_id)

    pending = load_pending_compatibility_records(
        pending_directory=pending_directory,
        repository_root=repository_root,
        catalog=catalog,
    )
    catalog_cores = catalog.get("cores")
    if not isinstance(catalog_cores, dict):
        raise PipelineError("catalog core coverage is invalid")
    errors = compatibility_coverage_errors(
        catalog_cores=set(catalog_cores),
        compatibility_coverage_cores=compatibility_coverage_cores,
        golden_source_cores=golden_source_cores,
        pending_cores=set(pending),
    )
    if errors:
        raise PipelineError("invalid compatibility coverage:\n- " + "\n- ".join(errors))
    return {
        "catalog_core_count": len(catalog_cores),
        "compatibility_coverage_core_count": len(
            compatibility_coverage_cores
        ),
        "canonical_compatibility_core_count": len(canonical_owners),
        "pending_compatibility_core_count": len(pending),
        "pending_compatibility_cores": sorted(pending),
    }
