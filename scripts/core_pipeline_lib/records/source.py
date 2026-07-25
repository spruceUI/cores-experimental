"""Composed source-identity records: the source lock and the source-set.

Both documents are pure functions of tracked state — the lock of the
catalog's source block, the source-set of the composed lock and the
evidence pin — so neither is stored as a file. Every consumer composes
them through this module. The serialized form reproduces the retired
files' bytes exactly, so every file_sha256 embedded in pins, goldens,
release manifests, and evidence indexes keeps binding; the historical
``pins/sources/...`` and ``pins/source-sets/...`` strings survive as
identity coordinates inside the documents and their references.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..errors import PipelineError


SOURCE_LOCK_SCHEMA_REF = "../../../manifests/core-source-lock.schema.json"
SOURCE_SET_SCHEMA_REF = "../../manifests/core-source-set.schema.json"


def serialize_record(document: dict[str, Any]) -> bytes:
    """The exact byte serialization the retired record files carried."""

    return (json.dumps(document, indent=2) + "\n").encode()


def record_file_sha256(document: dict[str, Any]) -> str:
    return hashlib.sha256(serialize_record(document)).hexdigest()


def record_content_sha256(document: dict[str, Any]) -> str:
    material = {
        key: value
        for key, value in document.items()
        if key not in {"$schema", "content_sha256"}
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def source_lock_coordinate(core_id: str, commit: str) -> str:
    return f"pins/sources/{core_id}/{commit}.json"


def source_set_coordinate(semantic_id: str) -> str:
    return f"pins/source-sets/{semantic_id}.json"


def compose_source_lock(
    core_id: str, *, repository_root: Path, catalog: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compose a core's source lock from its catalog source block.

    The lock is fully determined by the pinned catalog entry: exact HTTPS
    Git URL, requested ref, commit, content tree, and resolved submodule
    pins.
    """

    if catalog is None:
        catalog = _load(repository_root / "manifests" / "core-builds.json")
    spec = catalog.get("cores", {}).get(core_id)
    if not isinstance(spec, dict):
        raise PipelineError(f"catalog has no core {core_id}")
    source = spec["source"]
    document = {
        "$schema": SOURCE_LOCK_SCHEMA_REF,
        "schema_version": 1,
        "source_lock_id": f"{core_id}-{source['commit'][:12]}",
        "core_id": core_id,
        "source": {
            "url": source["url"],
            "requested_ref": source["requested_ref"],
            "commit": source["commit"],
            "tree": source["tree"],
            "submodules": [dict(entry) for entry in source.get("submodules", [])],
        },
        "local_only": True,
        "publication": "disabled",
    }
    document["content_sha256"] = record_content_sha256(document)
    return document


def compose_source_set(
    semantic_id: str, *, repository_root: Path, catalog: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Compose the source-set from the pin and the composed source lock."""

    core_id = semantic_id.split("-", 1)[0]
    pin_relative = f"pins/core-sets/{semantic_id}.json"
    pin_path = repository_root / pin_relative
    pin = _load(pin_path)
    lock = compose_source_lock(
        core_id, repository_root=repository_root, catalog=catalog
    )
    document = {
        "$schema": SOURCE_SET_SCHEMA_REF,
        "schema_version": 1,
        "source_set_id": semantic_id,
        "local_only": True,
        "publication": "disabled",
        "evidence_pin": {
            "path": pin_relative,
            "pin_id": semantic_id,
            "file_sha256": hashlib.sha256(pin_path.read_bytes()).hexdigest(),
            "content_sha256": pin["content_sha256"],
        },
        "sources": {
            core_id: {
                "path": source_lock_coordinate(core_id, lock["source"]["commit"]),
                "source_lock_id": lock["source_lock_id"],
                "commit": lock["source"]["commit"],
                "file_sha256": record_file_sha256(lock),
                "content_sha256": lock["content_sha256"],
            }
        },
    }
    document["content_sha256"] = record_content_sha256(document)
    return document


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"invalid JSON in {path}: {exc}") from exc
