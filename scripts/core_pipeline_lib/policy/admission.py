"""Shared source-commit policy references and state-creation admission gates."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import re

from ..errors import PipelineError
from ..foundation import require_manifest_reference_path, sha256_bytes
from .blacklist import (
    CommitBlacklist,
    CommitBlacklistError,
    CommitPolicyReport,
    parse_commit_blacklist_bytes,
    require_commit_eligible,
)


COMMIT_BLACKLIST_PATH = "policies/core-commit-blacklist.json"
COMMIT_BLACKLIST_POLICY_ID = "core-commit-blacklist-v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def commit_blacklist_reference_is_well_formed(reference: object) -> bool:
    expected_fields = {
        "path",
        "schema_version",
        "policy_id",
        "file_sha256",
        "content_sha256",
    }
    return bool(
        isinstance(reference, dict)
        and set(reference) == expected_fields
        and reference.get("path") == COMMIT_BLACKLIST_PATH
        and type(reference.get("schema_version")) is int
        and reference["schema_version"] == 1
        and reference.get("policy_id") == COMMIT_BLACKLIST_POLICY_ID
        and isinstance(reference.get("file_sha256"), str)
        and SHA256_RE.fullmatch(reference["file_sha256"])
        and isinstance(reference.get("content_sha256"), str)
        and SHA256_RE.fullmatch(reference["content_sha256"])
    )


def load_catalog_commit_blacklist(
    catalog: dict,
    repository_root: Path,
) -> tuple[CommitBlacklist, Path]:
    reference = catalog.get("commit_blacklist")
    if not isinstance(reference, dict) or not commit_blacklist_reference_is_well_formed(
        reference
    ):
        raise PipelineError("commit_blacklist reference has an unexpected shape")
    path = require_manifest_reference_path(
        reference,
        repository_root / "policies",
        "commit blacklist",
        repository_root,
    )
    try:
        raw = path.read_bytes() if path.is_file() else None
    except OSError as exc:
        raise PipelineError(f"cannot read commit blacklist: {exc}") from exc
    file_sha256 = sha256_bytes(raw) if raw is not None else None
    if file_sha256 != reference["file_sha256"]:
        raise PipelineError("commit_blacklist file SHA256 does not match")
    try:
        assert raw is not None
        blacklist = parse_commit_blacklist_bytes(raw, path)
    except CommitBlacklistError as exc:
        raise PipelineError(f"commit blacklist is invalid: {exc}") from exc
    if (
        blacklist.policy_id != reference["policy_id"]
        or blacklist.content_sha256 != reference["content_sha256"]
    ):
        raise PipelineError("commit_blacklist metadata does not match its reference")
    return blacklist, path


def source_commit_identity(
    core_id: object,
    source: object,
) -> tuple[str, str, str]:
    if not isinstance(core_id, str) or not isinstance(source, dict):
        raise PipelineError("source commit identity is incomplete")
    pinned_url = source.get("url")
    resolved_url = source.get("resolved_url")
    pinned_commit = source.get("commit")
    resolved_commit = source.get("resolved_commit")
    if (
        pinned_url is not None
        and resolved_url is not None
        and pinned_url != resolved_url
    ):
        raise PipelineError(f"{core_id}: pinned and resolved source URLs differ")
    if (
        pinned_commit is not None
        and resolved_commit is not None
        and pinned_commit != resolved_commit
    ):
        raise PipelineError(f"{core_id}: pinned and resolved source commits differ")
    source_url = resolved_url if resolved_url is not None else pinned_url
    commit = resolved_commit if resolved_commit is not None else pinned_commit
    if not isinstance(source_url, str) or not isinstance(commit, str):
        raise PipelineError(f"{core_id}: source commit identity is incomplete")
    return core_id, source_url, commit


def require_source_commits_eligible(
    catalog: dict,
    sources: Iterable[tuple[object, object]],
    repository_root: Path,
) -> list[CommitPolicyReport]:
    blacklist, _ = load_catalog_commit_blacklist(catalog, repository_root)
    reports: list[CommitPolicyReport] = []
    seen: set[tuple[str, str, str]] = set()
    for core_id, source in sources:
        identity = source_commit_identity(core_id, source)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            reports.append(require_commit_eligible(blacklist, *identity))
        except CommitBlacklistError as exc:
            raise PipelineError(
                f"source commit policy rejected the operation: {exc}"
            ) from exc
    return reports


def require_catalog_cores_eligible(
    catalog: dict,
    core_ids: Iterable[str],
    repository_root: Path,
) -> None:
    require_source_commits_eligible(
        catalog,
        ((core_id, catalog["cores"][core_id].get("source")) for core_id in core_ids),
        repository_root,
    )


def pin_source_records(pin: dict) -> list[tuple[object, object]]:
    records: list[tuple[object, object]] = []
    cores = pin.get("cores", {})
    scope = pin.get("scope", [])
    if not isinstance(cores, dict) or not isinstance(scope, list):
        raise PipelineError("pin source selections are unavailable")
    for core_id in scope:
        selection = cores.get(core_id, {}).get("selection", {})
        targets = selection.get("targets", {})
        if not isinstance(targets, dict) or not targets:
            raise PipelineError(f"{core_id}: pin source selection is unavailable")
        for target in targets.values():
            record = target.get("golden_record", {}) if isinstance(target, dict) else {}
            source = record.get("source") if isinstance(record, dict) else None
            records.append((core_id, source))
    return records


def golden_source_records(golden: dict) -> list[tuple[object, object]]:
    records: list[tuple[object, object]] = []
    build_goldens = golden.get("build_goldens", {})
    if not isinstance(build_goldens, dict):
        raise PipelineError("golden source selections are unavailable")
    for core_id, targets in build_goldens.items():
        if not isinstance(targets, dict):
            raise PipelineError(f"{core_id}: golden target selections are unavailable")
        for record in targets.values():
            source = record.get("source") if isinstance(record, dict) else None
            records.append((core_id, source))
    return records


def require_pin_sources_eligible(
    catalog: dict,
    pin: dict,
    repository_root: Path,
) -> None:
    require_source_commits_eligible(
        catalog, pin_source_records(pin), repository_root
    )


def require_golden_sources_eligible(
    catalog: dict,
    golden: dict,
    repository_root: Path,
) -> None:
    require_source_commits_eligible(
        catalog, golden_source_records(golden), repository_root
    )
