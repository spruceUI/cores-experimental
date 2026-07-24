#!/usr/bin/env python3
"""Propagate a Dockerfile edit through the toolchain digest chain.

The chain has five hand-synchronized layers, in dependency order:

  1. Dockerfile.arm64 / Dockerfile.armhf              (the source of truth)
  2. scripts/toolchain_archive.py TOOLCHAIN_CONTRACTS  (hardcoded digests)
  3. pins/toolchains/local-cache-v1.json               (per-arch dockerfile
     sha256 + the lock's own content_sha256)
  4. manifests/core-builds.json                        (toolchains mirror +
     toolchain_lock file/content + toolchain_lock_validator self-pin)
  5. manifests/execution-profiles.json                 (per-profile digests +
     its content_sha256) and the pinned literals in tests/test_core_pipeline.py

The mirrors are deliberate — validation compares independently stored copies,
which is how the armhf base-tag drift was caught — but updating them is pure
mechanism. This tool recomputes the whole chain from the Dockerfiles outward
and reports what moved. It changes provenance bookkeeping only: image_id and
the archive sha256s identify the image *bytes* and are never touched here.

Read-only when nothing drifted. Lives outside the hashed pipeline bundle.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

LOCK_PATH = ROOT / "pins" / "toolchains" / "local-cache-v1.json"
VALIDATOR_PATH = ROOT / "scripts" / "toolchain_archive.py"
CATALOG_PATH = ROOT / "manifests" / "core-builds.json"
PROFILES_PATH = ROOT / "manifests" / "execution-profiles.json"
TEST_PATH = ROOT / "tests" / "test_core_pipeline.py"
DOCKERFILES = {
    "arm64": "Dockerfile.arm64",
    "armhf": "Dockerfile.armhf",
    "rust": "Dockerfile.rust",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace(path: Path, mapping: dict[str, str]) -> int:
    text = path.read_text(encoding="utf-8")
    hits = 0
    for old, new in mapping.items():
        if old == new:
            continue
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            hits += count
    if hits:
        path.write_text(text, encoding="utf-8")
    return hits


def main() -> int:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    changes: dict[str, str] = {}

    # Layer 1 -> 2/3: the Dockerfile digests.
    for arch, name in DOCKERFILES.items():
        old = lock["toolchains"][arch]["dockerfile"]["sha256"]
        new = _sha256(ROOT / name)
        if old != new:
            print(f"{name}: {old[:12]} -> {new[:12]}")
            changes[old] = new
    if not changes:
        print("digest chain is already synchronized")
        return 0

    # Capture the pre-edit identities that other layers mirror.
    old_lock_file = _sha256(LOCK_PATH)
    old_lock_content = lock["content_sha256"]
    old_validator = _sha256(VALIDATOR_PATH)

    # Layer 2: the validator's hardcoded contract, then its new self-hash.
    _replace(VALIDATOR_PATH, changes)
    changes[old_validator] = _sha256(VALIDATOR_PATH)

    # Layer 3: the lock, then its recomputed content hash and file hash.
    _replace(LOCK_PATH, changes)
    from toolchain_archive import lock_content_sha256  # noqa: E402

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    lock["content_sha256"] = lock_content_sha256(lock)
    LOCK_PATH.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    changes[old_lock_content] = lock["content_sha256"]
    changes[old_lock_file] = _sha256(LOCK_PATH)

    # Layers 4 and 5: textual mirrors, then recomputed content hashes.
    _replace(CATALOG_PATH, changes)
    _replace(PROFILES_PATH, changes)
    from profile_registry import canonical_content_sha256  # noqa: E402

    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    profiles["content_sha256"] = canonical_content_sha256(profiles)
    PROFILES_PATH.write_text(
        json.dumps(profiles, indent=2) + "\n", encoding="utf-8"
    )
    _replace(TEST_PATH, changes)

    for old, new in changes.items():
        print(f"  {old[:12]} -> {new[:12]}")
    print("synchronized; run catalog-check and the suite to confirm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
