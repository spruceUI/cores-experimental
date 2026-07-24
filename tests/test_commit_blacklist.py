#!/usr/bin/env python3

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core_pipeline_lib.policy.blacklist import (  # noqa: E402
    CommitBlacklistError,
    commit_blacklist_content_sha256,
    load_commit_blacklist,
    parse_commit_blacklist,
    report_commit_policy,
    require_commit_eligible,
)


CORE_ID = "gambatte"
SOURCE_URL = "https://github.com/libretro/gambatte-libretro.git"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def policy_document(*entries: dict[str, object]) -> dict[str, object]:
    document: dict[str, object] = {
        "$schema": "../manifests/core-commit-blacklist.schema.json",
        "schema_version": 1,
        "policy_id": "core-commit-blacklist-v1",
        "local_only": True,
        "publication": "disabled",
        "entries": list(entries),
        "content_sha256": "0" * 64,
    }
    document["content_sha256"] = commit_blacklist_content_sha256(document)
    return document


def policy_entry(disposition: str = "active") -> dict[str, object]:
    return {
        "core_id": CORE_ID,
        "source_url": SOURCE_URL,
        "commit": COMMIT,
        "disposition": disposition,
        "reason": "Reproducible compiler regression in this exact source revision.",
        "evidence": ["local-e2e/source-probes/gambatte-regression-v1"],
    }


class CommitBlacklistTests(unittest.TestCase):
    def test_tracked_empty_policy_is_valid_and_publication_disabled(self) -> None:
        path = ROOT / "policies" / "core-commit-blacklist.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        policy = load_commit_blacklist(path)

        self.assertEqual([], raw["entries"])
        self.assertIs(raw["local_only"], True)
        self.assertEqual("disabled", raw["publication"])
        self.assertEqual(commit_blacklist_content_sha256(raw), raw["content_sha256"])
        self.assertEqual((), policy.entries)

    def test_active_exact_match_blocks_without_bypass(self) -> None:
        policy = parse_commit_blacklist(policy_document(policy_entry()))
        report = report_commit_policy(policy, CORE_ID, SOURCE_URL, COMMIT)

        self.assertTrue(report.blocked)
        self.assertFalse(report.eligible)
        self.assertEqual("blocked", report.current_eligibility)
        self.assertEqual("active", report.policy_disposition)
        with self.assertRaisesRegex(CommitBlacklistError, "actively blacklisted"):
            require_commit_eligible(policy, CORE_ID, SOURCE_URL, COMMIT)

        parameters = inspect.signature(require_commit_eligible).parameters
        self.assertEqual(
            ["blacklist", "core_id", "source_url", "commit"], list(parameters)
        )
        with self.assertRaises(TypeError):
            require_commit_eligible(
                policy, CORE_ID, SOURCE_URL, COMMIT, bypass=True  # type: ignore[call-arg]
            )

    def test_near_misses_are_eligible(self) -> None:
        policy = parse_commit_blacklist(policy_document(policy_entry()))
        near_misses = (
            ("gambatte_alt", SOURCE_URL, COMMIT),
            (CORE_ID, "https://github.com/libretro/gambatte-libretro-fork.git", COMMIT),
            (CORE_ID, SOURCE_URL, "1123456789abcdef0123456789abcdef01234567"),
        )
        for identity in near_misses:
            with self.subTest(identity=identity):
                report = require_commit_eligible(policy, *identity)
                self.assertTrue(report.eligible)
                self.assertFalse(report.blocked)
                self.assertEqual("unlisted", report.policy_disposition)

    def test_retired_entry_preserves_history_but_is_currently_eligible(self) -> None:
        document = policy_document(policy_entry("retired"))
        original = copy.deepcopy(document)
        policy = parse_commit_blacklist(document)

        report = require_commit_eligible(policy, CORE_ID, SOURCE_URL, COMMIT)

        self.assertTrue(report.eligible)
        self.assertFalse(report.blocked)
        self.assertTrue(report.historically_listed)
        self.assertEqual("retired", report.policy_disposition)
        self.assertEqual(tuple(policy_entry("retired")["evidence"]), report.evidence)
        self.assertEqual(original, document)

    def test_duplicate_identity_is_rejected_across_dispositions(self) -> None:
        with self.assertRaisesRegex(CommitBlacklistError, "duplicate blacklist identity"):
            parse_commit_blacklist(
                policy_document(policy_entry("active"), policy_entry("retired"))
            )

    def test_content_digest_excludes_only_its_own_field(self) -> None:
        document = policy_document()
        changed_digest = copy.deepcopy(document)
        changed_digest["content_sha256"] = "f" * 64
        self.assertEqual(
            commit_blacklist_content_sha256(document),
            commit_blacklist_content_sha256(changed_digest),
        )

        changed_schema = copy.deepcopy(document)
        changed_schema["$schema"] = "elsewhere.json"
        self.assertNotEqual(
            commit_blacklist_content_sha256(document),
            commit_blacklist_content_sha256(changed_schema),
        )

    def test_strict_document_and_entry_shapes_are_enforced(self) -> None:
        cases: list[tuple[str, dict[str, object]]] = []
        extra_header = policy_document()
        extra_header["unexpected"] = True
        cases.append(("header-extra", extra_header))

        wrong_scope = policy_document()
        wrong_scope["local_only"] = False
        wrong_scope["content_sha256"] = commit_blacklist_content_sha256(wrong_scope)
        cases.append(("non-local", wrong_scope))

        extra_entry = policy_entry()
        extra_entry["note"] = "not allowed"
        cases.append(("entry-extra", policy_document(extra_entry)))

        blank_reason = policy_entry()
        blank_reason["reason"] = "  "
        cases.append(("blank-reason", policy_document(blank_reason)))

        empty_evidence = policy_entry()
        empty_evidence["evidence"] = []
        cases.append(("empty-evidence", policy_document(empty_evidence)))

        non_string_disposition = policy_entry()
        non_string_disposition["disposition"] = []
        cases.append(
            ("non-string-disposition", policy_document(non_string_disposition))
        )

        bad_digest = policy_document()
        bad_digest["content_sha256"] = "0" * 64
        cases.append(("bad-digest", bad_digest))

        for name, document in cases:
            with self.subTest(name=name):
                with self.assertRaises(CommitBlacklistError):
                    parse_commit_blacklist(document)

    def test_identity_requires_canonical_https_url_and_full_lowercase_commit(self) -> None:
        root_repository = policy_entry()
        root_repository["source_url"] = "https://git.example/repository.git"
        parse_commit_blacklist(policy_document(root_repository))

        invalid_urls = (
            "http://github.com/libretro/gambatte-libretro.git",
            "https://GitHub.com/libretro/gambatte-libretro.git",
            "https://github.com/libretro/../gambatte-libretro.git",
            "https://github.com/libretro/gambatte-libretro.git/",
            "https://github.com/libretro/gambatte-libretro.git?ref=main",
            "https://user@github.com/libretro/gambatte-libretro.git",
            "https://github..com/libretro/gambatte-libretro.git",
            "https://github.com/libretro/gambatte-libretro.git\n",
        )
        for source_url in invalid_urls:
            entry = policy_entry()
            entry["source_url"] = source_url
            with self.subTest(source_url=source_url):
                with self.assertRaisesRegex(CommitBlacklistError, "canonical https"):
                    parse_commit_blacklist(policy_document(entry))

        for commit in (COMMIT[:-1], COMMIT.upper(), "g" * 40):
            entry = policy_entry()
            entry["commit"] = commit
            with self.subTest(commit=commit):
                with self.assertRaisesRegex(CommitBlacklistError, "full lowercase"):
                    parse_commit_blacklist(policy_document(entry))

    def test_loader_rejects_duplicate_json_keys_and_nonstandard_constants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text('{"schema_version":1,"schema_version":1}\n', encoding="utf-8")
            with self.assertRaisesRegex(CommitBlacklistError, "duplicate JSON key"):
                load_commit_blacklist(path)

            path.write_text('{"value":NaN}\n', encoding="utf-8")
            with self.assertRaisesRegex(CommitBlacklistError, "non-standard JSON"):
                load_commit_blacklist(path)


if __name__ == "__main__":
    unittest.main()
