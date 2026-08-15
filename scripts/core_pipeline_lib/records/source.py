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
import re
from typing import Any

from ..errors import PipelineError


SOURCE_LOCK_SCHEMA_REF = "../../../manifests/core-source-lock.schema.json"
SOURCE_SET_SCHEMA_REF = "../../manifests/core-source-set.schema.json"
PIN_SET_SCHEMA_REF = "../../manifests/core-set.schema.json"

CORE_ID_RE = re.compile(r"[a-z0-9_]+")
SEMANTIC_ID_RE = re.compile(r"([a-z0-9_]+)-([0-9a-f]{12})-([0-9a-f]{12})")
SHA1_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")

PIN_SET_KEYS = {
    "$schema",
    "schema_version",
    "pin_id",
    "local_only",
    "publication",
    "scope",
    "parent",
    "sources",
    "selection_policy",
    "cores",
    "summary",
    "created_at",
    "content_sha256",
}
PIN_SELECTION_POLICY = {
    "unit": "complete-core-package",
    "source_order": "first-complete-wins",
    "failed_candidate": "retain-parent",
    "missing_candidate": "retain-parent",
    "release_action": "copy-exact-package-bytes",
}


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


def _selection_content_sha256(selection: dict[str, Any]) -> str:
    """Hash the same selected evidence fields as the core pipeline."""

    targets: dict[str, Any] = {}
    raw_targets = selection.get("targets")
    if isinstance(raw_targets, dict):
        for architecture, raw_target in sorted(raw_targets.items()):
            target = raw_target if isinstance(raw_target, dict) else {}
            artifact = target.get("artifact")
            artifact = artifact if isinstance(artifact, dict) else {}
            targets[architecture] = {
                "artifact": {
                    "sha256": artifact.get("sha256"),
                    "size": artifact.get("size"),
                },
                "build_record_sha256": target.get("build_record_sha256"),
                "provenance_identity_sha256": target.get(
                    "provenance_identity_sha256"
                ),
            }
    package = selection.get("package")
    package = package if isinstance(package, dict) else {}
    metadata = selection.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    material: dict[str, Any] = {
        "tier": selection.get("tier"),
        "validation_scope": selection.get("validation_scope"),
        "e2e": selection.get("e2e"),
        "package": {
            "name": package.get("name"),
            "sha256": package.get("sha256"),
            "size": package.get("size"),
        },
        "metadata": {
            "sha256": metadata.get("sha256"),
            "size": metadata.get("size"),
        },
        "targets": targets,
    }
    for optional in (
        "chipset_tuning",
        "reproduction",
        "source_candidate",
        "output_reproduction",
        "host_reproduction",
    ):
        if optional in selection:
            material[optional] = selection.get(optional)
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _pin_set_content_sha256(document: dict[str, Any]) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "pin_id": document.get("pin_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "scope": document.get("scope"),
        "parent": document.get("parent"),
        "sources": document.get("sources"),
        "selection_policy": document.get("selection_policy"),
        "cores": document.get("cores"),
        "summary": document.get("summary"),
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _normalized_submodules(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PipelineError(f"{label} must be an array")
    normalized: list[dict[str, str]] = []
    for index, raw_entry in enumerate(value):
        if (
            not isinstance(raw_entry, dict)
            or set(raw_entry) not in ({"path", "commit"}, {"path", "commit", "state"})
            or not isinstance(raw_entry.get("path"), str)
            or not raw_entry["path"]
            or not isinstance(raw_entry.get("commit"), str)
            or SHA1_RE.fullmatch(raw_entry["commit"]) is None
        ):
            raise PipelineError(f"{label}[{index}] is malformed")
        normalized.append(
            {"path": raw_entry["path"], "commit": raw_entry["commit"]}
        )
    return normalized


def require_selected_source_identity(
    core_id: str,
    targets: Any,
    expected_source: dict[str, Any],
    *,
    label: str = "selected pin",
) -> None:
    """Bind every selected golden source to one catalog source identity.

    A catalog source with no explicit submodule list uses the established
    superproject-tree convention: captured recursive submodules remain build
    evidence. When the catalog enumerates submodules, their normalized list is
    exact as well.
    """

    if not isinstance(targets, dict) or not targets:
        raise PipelineError(f"{label} has no targets for {core_id}")
    expected_submodules = _normalized_submodules(
        expected_source.get("submodules", []),
        f"catalog source {core_id}.submodules",
    )
    for architecture, raw_target in targets.items():
        golden = (
            raw_target.get("golden_record")
            if isinstance(raw_target, dict)
            else None
        )
        source = golden.get("source") if isinstance(golden, dict) else None
        if not isinstance(source, dict):
            raise PipelineError(
                f"{label} source is malformed for {core_id}/{architecture}"
            )
        recorded_submodules = _normalized_submodules(
            source.get("submodules"),
            f"{label} source {core_id}/{architecture}.submodules",
        )
        if (
            source.get("url") != expected_source.get("url")
            or source.get("resolved_url") != expected_source.get("url")
            or source.get("requested_ref") != expected_source.get("requested_ref")
            or source.get("commit") != expected_source.get("commit")
            or source.get("resolved_commit") != expected_source.get("commit")
            or source.get("tree") != expected_source.get("tree")
            or (
                expected_submodules
                and recorded_submodules != expected_submodules
            )
        ):
            raise PipelineError(
                f"{label} source differs from the catalog source for "
                f"{core_id}/{architecture}"
            )


def load_semantic_pin(
    semantic_id: str, *, repository_root: Path
) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    """Load and authenticate one parentless, direct semantic pin snapshot."""

    match = SEMANTIC_ID_RE.fullmatch(semantic_id)
    if match is None:
        raise PipelineError("source-set semantic ID is invalid")
    core_id = match.group(1)
    pin_relative = f"pins/core-sets/{semantic_id}.json"
    pin_path = repository_root / pin_relative
    if pin_path.is_symlink():
        raise PipelineError(f"semantic pin must not be a symlink: {pin_path}")
    pin, pin_file_sha256 = _load_with_sha256(pin_path)
    if set(pin) != PIN_SET_KEYS:
        raise PipelineError("semantic pin fields are not exact")
    cores = pin.get("cores")
    sources = pin.get("sources")
    scope = pin.get("scope")
    core_record = cores.get(core_id) if isinstance(cores, dict) else None
    selection = (
        core_record.get("selection") if isinstance(core_record, dict) else None
    )
    if (
        pin.get("$schema") != PIN_SET_SCHEMA_REF
        or pin.get("schema_version") != 1
        or pin.get("pin_id") != semantic_id
        or pin.get("local_only") is not True
        or pin.get("publication") != "disabled"
        or pin.get("selection_policy") != PIN_SELECTION_POLICY
        or pin.get("summary")
        != {
            "core_count": 1,
            "retained_parent_count": 0,
            "selected_source_count": 1,
        }
        or not isinstance(pin.get("created_at"), str)
        or not pin["created_at"]
        or pin.get("parent") is not None
        or scope != [core_id]
        or not isinstance(cores, dict)
        or set(cores) != {core_id}
        or not isinstance(core_record, dict)
        or set(core_record) != {"decision", "selection", "source_index"}
        or core_record.get("decision") != "select_source"
        or core_record.get("source_index") != 0
        or not isinstance(selection, dict)
        or selection.get("tier") != "build_golden"
        or selection.get("validation_scope") != "static-build-only"
        or not isinstance(sources, list)
        or len(sources) != 1
        or not isinstance(sources[0], dict)
    ):
        raise PipelineError("source-set pin is not one exact direct core selection")
    if pin.get("content_sha256") != _pin_set_content_sha256(pin):
        raise PipelineError("source-set pin content digest is invalid")
    selection_sha256 = selection.get("selection_sha256")
    if (
        not isinstance(selection_sha256, str)
        or SHA256_RE.fullmatch(selection_sha256) is None
        or selection_sha256 != _selection_content_sha256(selection)
    ):
        raise PipelineError("source-set pin selection digest is invalid")
    targets = selection.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise PipelineError("source-set pin selection has no targets")
    source_commits: set[str] = set()
    for architecture, raw_target in targets.items():
        if not isinstance(architecture, str) or not architecture:
            raise PipelineError("source-set target architecture is invalid")
        golden = (
            raw_target.get("golden_record")
            if isinstance(raw_target, dict)
            else None
        )
        artifact = raw_target.get("artifact") if isinstance(raw_target, dict) else None
        if (
            not isinstance(artifact, dict)
            or not isinstance(artifact.get("sha256"), str)
            or SHA256_RE.fullmatch(artifact["sha256"]) is None
            or not isinstance(artifact.get("size"), int)
            or artifact["size"] < 0
            or not isinstance(raw_target.get("build_record_sha256"), str)
            or SHA256_RE.fullmatch(raw_target["build_record_sha256"]) is None
            or not isinstance(raw_target.get("provenance_identity_sha256"), str)
            or SHA256_RE.fullmatch(raw_target["provenance_identity_sha256"])
            is None
        ):
            raise PipelineError("source-set selected target identity is invalid")
        source = golden.get("source") if isinstance(golden, dict) else None
        commit = source.get("commit") if isinstance(source, dict) else None
        if not isinstance(commit, str) or SHA1_RE.fullmatch(commit) is None:
            raise PipelineError("source-set semantic source commit is invalid")
        source_commits.add(commit)
    if len(source_commits) != 1:
        raise PipelineError("source-set semantic source commits differ")
    source_commit = next(iter(source_commits))
    expected_semantic_id = (
        f"{core_id}-{source_commit[:12]}-{selection_sha256[:12]}"
    )
    if semantic_id != expected_semantic_id:
        raise PipelineError(
            f"source-set pin ID must be semantic ID {expected_semantic_id}"
        )
    source_reference = sources[0]
    expected_source_path = f".local-e2e/nightlies/{semantic_id}/golden.json"
    if (
        set(source_reference)
        != {"path", "pin_id", "file_sha256", "content_sha256"}
        or source_reference.get("path") != expected_source_path
        or source_reference.get("pin_id") != semantic_id
        or not isinstance(source_reference.get("file_sha256"), str)
        or SHA256_RE.fullmatch(source_reference["file_sha256"]) is None
        or not isinstance(source_reference.get("content_sha256"), str)
        or SHA256_RE.fullmatch(source_reference["content_sha256"]) is None
    ):
        raise PipelineError(
            "source-set pin does not reference its exact semantic nightly golden"
        )
    return core_id, pin, pin_file_sha256, selection


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
    """Compose a source-set from one authenticated semantic pin."""

    semantic_pin = load_semantic_pin(
        semantic_id,
        repository_root=repository_root,
    )
    return _compose_source_set_from_semantic_pin(
        semantic_id,
        semantic_pin,
        repository_root=repository_root,
        catalog=catalog,
    )


def _compose_source_set_from_semantic_pin(
    semantic_id: str,
    semantic_pin: tuple[str, dict[str, Any], str, dict[str, Any]],
    *,
    repository_root: Path,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose from a single already-read semantic-pin snapshot."""

    core_id, pin, pin_file_sha256, selection = semantic_pin
    if pin.get("pin_id") != semantic_id:
        raise PipelineError("source-set semantic pin snapshot differs")
    pin_relative = f"pins/core-sets/{semantic_id}.json"
    lock = compose_source_lock(
        core_id, repository_root=repository_root, catalog=catalog
    )
    require_selected_source_identity(
        core_id,
        selection.get("targets"),
        lock["source"],
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
            "file_sha256": pin_file_sha256,
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
    document, _file_sha256 = _load_with_sha256(path)
    return document


def _load_with_sha256(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        document = json.loads(text)
    except OSError as exc:
        raise PipelineError(f"missing input: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise PipelineError(f"expected a JSON object in {path}")
    return document, hashlib.sha256(raw).hexdigest()
