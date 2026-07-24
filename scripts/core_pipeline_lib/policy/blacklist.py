"""Strict source-commit blacklist parsing, reporting, and enforcement.

The policy keeps historical entries in place by changing their disposition
from ``active`` to ``retired``.  Reports therefore distinguish current build
eligibility from policy history without rewriting or discarding evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Literal, Mapping
from urllib.parse import urlsplit


SCHEMA_REFERENCE = "../manifests/core-commit-blacklist.schema.json"
POLICY_ID = "core-commit-blacklist-v1"
MAX_POLICY_BYTES = 1024 * 1024
CORE_ID_RE = re.compile(r"[a-z0-9][a-z0-9_]*")
HOST_RE = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*"
)
PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9._+-]+")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")

Disposition = Literal["active", "retired"]
Eligibility = Literal["blocked", "eligible"]
PolicyDisposition = Literal["active", "retired", "unlisted"]


class CommitBlacklistError(ValueError):
    """Raised when blacklist policy is malformed or blocks a source commit."""


@dataclass(frozen=True, order=True, slots=True)
class CommitIdentity:
    """The exact identity used for blacklist matching."""

    core_id: str
    source_url: str
    commit: str


@dataclass(frozen=True, slots=True)
class CommitBlacklistEntry:
    """An immutable active or historical blacklist entry."""

    identity: CommitIdentity
    disposition: Disposition
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommitPolicyReport:
    """Current eligibility plus any matching active or retired policy history."""

    identity: CommitIdentity
    current_eligibility: Eligibility
    policy_disposition: PolicyDisposition
    reason: str | None
    evidence: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return self.current_eligibility == "blocked"

    @property
    def eligible(self) -> bool:
        return self.current_eligibility == "eligible"

    @property
    def historically_listed(self) -> bool:
        return self.policy_disposition != "unlisted"


@dataclass(frozen=True, slots=True)
class CommitBlacklist:
    """Validated blacklist policy indexed by exact source identity."""

    policy_id: str
    content_sha256: str
    entries: tuple[CommitBlacklistEntry, ...]
    _by_identity: Mapping[CommitIdentity, CommitBlacklistEntry]

    def report(
        self,
        core_id: str,
        source_url: str,
        commit: str,
    ) -> CommitPolicyReport:
        identity = _validated_identity(core_id, source_url, commit, "source identity")
        entry = self._by_identity.get(identity)
        if entry is None:
            return CommitPolicyReport(
                identity=identity,
                current_eligibility="eligible",
                policy_disposition="unlisted",
                reason=None,
                evidence=(),
            )
        blocked = entry.disposition == "active"
        return CommitPolicyReport(
            identity=identity,
            current_eligibility="blocked" if blocked else "eligible",
            policy_disposition=entry.disposition,
            reason=entry.reason,
            evidence=entry.evidence,
        )

    def require_eligible(
        self,
        core_id: str,
        source_url: str,
        commit: str,
    ) -> CommitPolicyReport:
        report = self.report(core_id, source_url, commit)
        if report.blocked:
            raise CommitBlacklistError(
                "source commit is actively blacklisted: "
                f"core_id={core_id}, source_url={source_url}, commit={commit}; "
                f"reason={report.reason}"
            )
        return report


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CommitBlacklistError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CommitBlacklistError(f"non-standard JSON constant: {value}")


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CommitBlacklistError(
            f"{label} keys differ; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _nonblank_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommitBlacklistError(f"{label} must be a non-blank string")
    if len(value) > 2048:
        raise CommitBlacklistError(f"{label} exceeds 2048 characters")
    return value


def _canonical_source_url(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise CommitBlacklistError(f"{label} must be a canonical https URL")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise CommitBlacklistError(f"{label} must be a canonical https URL") from exc
    canonical = (
        f"https://{parsed.hostname}{parsed.path}" if parsed.hostname is not None else None
    )
    if (
        value != canonical
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.hostname != parsed.hostname.lower()
        or not HOST_RE.fullmatch(parsed.hostname)
        or parsed.netloc != parsed.hostname
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.endswith("/")
        or "//" in parsed.path
        or "%" in parsed.path
    ):
        raise CommitBlacklistError(f"{label} must be a canonical https URL")
    segments = parsed.path[1:].split("/")
    if (
        not segments
        or segments[-1] == ".git"
        or not segments[-1].endswith(".git")
        or any(
            segment in {".", ".."} or not PATH_SEGMENT_RE.fullmatch(segment)
            for segment in segments
        )
    ):
        raise CommitBlacklistError(f"{label} must be a canonical https URL")
    return value


def _validated_identity(
    core_id: Any,
    source_url: Any,
    commit: Any,
    label: str,
) -> CommitIdentity:
    if not isinstance(core_id, str) or not CORE_ID_RE.fullmatch(core_id):
        raise CommitBlacklistError(f"{label}.core_id has an invalid value")
    canonical_url = _canonical_source_url(source_url, f"{label}.source_url")
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise CommitBlacklistError(
            f"{label}.commit must be a full lowercase 40-character commit"
        )
    return CommitIdentity(core_id, canonical_url, commit)


def commit_blacklist_content_sha256(document: dict[str, Any]) -> str:
    """Hash every policy field except ``content_sha256`` deterministically."""

    if not isinstance(document, dict):
        raise CommitBlacklistError("blacklist digest input must be an object")
    material = {key: value for key, value in document.items() if key != "content_sha256"}
    try:
        encoded = json.dumps(
            material,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CommitBlacklistError("blacklist digest input is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def parse_commit_blacklist(document: dict[str, Any]) -> CommitBlacklist:
    """Validate a decoded policy document and return an immutable index."""

    if not isinstance(document, dict):
        raise CommitBlacklistError("commit blacklist must be an object")
    _exact_keys(
        document,
        {
            "$schema",
            "schema_version",
            "policy_id",
            "local_only",
            "publication",
            "entries",
            "content_sha256",
        },
        "commit blacklist",
    )
    if document["$schema"] != SCHEMA_REFERENCE:
        raise CommitBlacklistError("commit blacklist has the wrong $schema reference")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise CommitBlacklistError("commit blacklist.schema_version must be integer 1")
    if document["policy_id"] != POLICY_ID:
        raise CommitBlacklistError(f"commit blacklist.policy_id must be {POLICY_ID}")
    if document["local_only"] is not True:
        raise CommitBlacklistError("commit blacklist.local_only must be true")
    if document["publication"] != "disabled":
        raise CommitBlacklistError("commit blacklist.publication must be disabled")
    if not isinstance(document["entries"], list):
        raise CommitBlacklistError("commit blacklist.entries must be an array")

    entries: list[CommitBlacklistEntry] = []
    by_identity: dict[CommitIdentity, CommitBlacklistEntry] = {}
    for index, raw_entry in enumerate(document["entries"]):
        label = f"commit blacklist.entries[{index}]"
        if not isinstance(raw_entry, dict):
            raise CommitBlacklistError(f"{label} must be an object")
        _exact_keys(
            raw_entry,
            {"core_id", "source_url", "commit", "disposition", "reason", "evidence"},
            label,
        )
        identity = _validated_identity(
            raw_entry["core_id"], raw_entry["source_url"], raw_entry["commit"], label
        )
        disposition = raw_entry["disposition"]
        if not isinstance(disposition, str) or disposition not in {"active", "retired"}:
            raise CommitBlacklistError(f"{label}.disposition must be active or retired")
        reason = _nonblank_string(raw_entry["reason"], f"{label}.reason")
        raw_evidence = raw_entry["evidence"]
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise CommitBlacklistError(f"{label}.evidence must be a non-empty array")
        evidence = tuple(
            _nonblank_string(item, f"{label}.evidence[{item_index}]")
            for item_index, item in enumerate(raw_evidence)
        )
        if len(evidence) != len(set(evidence)):
            raise CommitBlacklistError(f"{label}.evidence contains duplicates")
        if identity in by_identity:
            raise CommitBlacklistError(
                "duplicate blacklist identity: "
                f"core_id={identity.core_id}, source_url={identity.source_url}, "
                f"commit={identity.commit}"
            )
        entry = CommitBlacklistEntry(identity, disposition, reason, evidence)
        entries.append(entry)
        by_identity[identity] = entry

    digest = document["content_sha256"]
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise CommitBlacklistError(
            "commit blacklist.content_sha256 must be a lowercase SHA-256"
        )
    expected_digest = commit_blacklist_content_sha256(document)
    if digest != expected_digest:
        raise CommitBlacklistError(
            "commit blacklist.content_sha256 does not cover current content"
        )

    return CommitBlacklist(
        policy_id=POLICY_ID,
        content_sha256=digest,
        entries=tuple(entries),
        _by_identity=MappingProxyType(by_identity),
    )


def load_commit_blacklist(path: Path) -> CommitBlacklist:
    """Load strict UTF-8 JSON from ``path`` and validate the complete policy."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise CommitBlacklistError(f"cannot read commit blacklist {path}: {exc}") from exc
    if len(raw) > MAX_POLICY_BYTES:
        raise CommitBlacklistError(
            f"commit blacklist exceeds {MAX_POLICY_BYTES} bytes: {path}"
        )
    try:
        text = raw.decode("utf-8")
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommitBlacklistError(f"invalid commit blacklist JSON {path}: {exc}") from exc
    return parse_commit_blacklist(document)


def report_commit_policy(
    blacklist: CommitBlacklist,
    core_id: str,
    source_url: str,
    commit: str,
) -> CommitPolicyReport:
    """Report current eligibility while preserving matching policy history."""

    if not isinstance(blacklist, CommitBlacklist):
        raise CommitBlacklistError("blacklist must be a validated CommitBlacklist")
    return blacklist.report(core_id, source_url, commit)


def require_commit_eligible(
    blacklist: CommitBlacklist,
    core_id: str,
    source_url: str,
    commit: str,
) -> CommitPolicyReport:
    """Enforce current policy with no caller-selectable bypass."""

    if not isinstance(blacklist, CommitBlacklist):
        raise CommitBlacklistError("blacklist must be a validated CommitBlacklist")
    return blacklist.require_eligible(core_id, source_url, commit)
