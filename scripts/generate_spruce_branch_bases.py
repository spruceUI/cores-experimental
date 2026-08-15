#!/usr/bin/env python3
"""Generate the exact artifact-only Spruce main/Development branch bases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.core_pipeline_lib.errors import PipelineError  # noqa: E402
from scripts.core_pipeline_lib.foundation import (  # noqa: E402
    atomic_write_json,
    load_json_with_sha256,
)
from scripts.core_pipeline_lib.spruce_branch_bases import (  # noqa: E402
    ARCHITECTURES,
    SPRUCE_BRANCH_BASES_MODEL,
    SPRUCE_BRANCH_BASES_PROVENANCE_MODEL,
    SPRUCE_BRANCH_BASES_SCHEMA_REF,
    SPRUCE_BRANCH_BASES_SCHEMA_VERSION,
    SPRUCE_BRANCH_SPECS,
    SPRUCE_CATALOG_PATH,
    SPRUCE_CORE_TREES,
    SPRUCE_RELEASE_ROSTER_PATH,
    SPRUCE_REPOSITORY,
    catalog_semantic_sha256,
    release_roster_semantic_sha256,
    spruce_branch_artifact_identity_set_sha256,
    spruce_branch_basis_content_sha256,
    spruce_branch_bases_content_sha256,
    validate_spruce_branch_bases,
)


MACHINE_NAMES = {
    3: "x86",
    40: "ARM",
    62: "X86-64",
    183: "AArch64",
}


def _git(repository: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise PipelineError(
            f"git {' '.join(args)} failed in {repository}: {detail}"
        )
    return result.stdout


def _git_text(repository: Path, *args: str) -> str:
    try:
        return _git(repository, *args).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise PipelineError(f"git {' '.join(args)} returned non-UTF-8 text") from exc


def _elf_identity(data: bytes, label: str) -> dict[str, Any]:
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise PipelineError(f"{label} is not a complete ELF file")
    elf_class_id = data[4]
    data_id = data[5]
    if elf_class_id not in {1, 2}:
        raise PipelineError(f"{label} has unsupported ELF class {elf_class_id}")
    if data_id not in {1, 2}:
        raise PipelineError(f"{label} has unsupported ELF data encoding {data_id}")
    byteorder = "little" if data_id == 1 else "big"
    elf_class = "ELF32" if elf_class_id == 1 else "ELF64"
    e_type = int.from_bytes(data[16:18], byteorder)
    e_machine = int.from_bytes(data[18:20], byteorder)
    flags_offset = 36 if elf_class_id == 1 else 48
    flags = int.from_bytes(data[flags_offset : flags_offset + 4], byteorder)
    if e_type != 3:
        raise PipelineError(f"{label} is ELF type {e_type}, not DYN")
    if e_machine == 40:
        float_abi = "hard" if flags & 0x400 else "soft"
    else:
        float_abi = "not-applicable"
    return {
        "class": elf_class,
        "data": "little-endian" if data_id == 1 else "big-endian",
        "version": data[6],
        "osabi": data[7],
        "abi_version": data[8],
        "type": "DYN",
        "machine": MACHINE_NAMES.get(e_machine, f"machine-{e_machine}"),
        "flags": f"0x{flags:08x}",
        "float_abi": float_abi,
    }


def _architecture_valid(architecture: str, elf: dict[str, Any]) -> bool:
    if elf["data"] != "little-endian" or elf["type"] != "DYN":
        return False
    if architecture == "arm64":
        return elf["class"] == "ELF64" and elf["machine"] == "AArch64"
    return (
        architecture == "armhf"
        and elf["class"] == "ELF32"
        and elf["machine"] == "ARM"
        and elf["float_abi"] == "hard"
    )


def _tree_artifacts(
    repository: Path,
    commit: str,
    *,
    catalog_core_ids: set[str],
    aliases: dict[str, str],
    uncataloged: set[str],
) -> list[dict[str, Any]]:
    raw = _git(
        repository,
        "ls-tree",
        "-r",
        "-z",
        "--long",
        commit,
        SPRUCE_CORE_TREES["armhf"]["path"],
        SPRUCE_CORE_TREES["arm64"]["path"],
    )
    artifacts: list[dict[str, Any]] = []
    for raw_record in raw.split(b"\0"):
        if not raw_record:
            continue
        try:
            metadata, raw_path = raw_record.split(b"\t", 1)
            mode, object_type, blob, raw_size = metadata.decode("ascii").split()
            path = raw_path.decode("utf-8")
            size = int(raw_size)
        except (ValueError, UnicodeDecodeError) as exc:
            raise PipelineError("cannot parse exact Spruce core-tree record") from exc
        if not path.endswith("_libretro.so"):
            continue
        architecture = "arm64" if path.startswith(
            SPRUCE_CORE_TREES["arm64"]["path"] + "/"
        ) else "armhf"
        shipped_core_id = Path(path).name.removesuffix("_libretro.so")
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise PipelineError(f"{path} is not a supported regular Git blob")
        data = _git(repository, "cat-file", "blob", blob)
        if len(data) != size:
            raise PipelineError(f"{path} Git size differs from blob bytes")
        computed_blob = hashlib.sha1(
            f"blob {len(data)}\0".encode("ascii") + data
        ).hexdigest()
        if computed_blob != blob:
            raise PipelineError(f"{path} Git blob SHA-1 does not verify")
        elf = _elf_identity(data, path)
        if shipped_core_id in catalog_core_ids:
            correlation = {
                "status": "catalog_exact",
                "catalog_core_id": shipped_core_id,
            }
        elif shipped_core_id in aliases:
            correlation = {
                "status": "catalog_alias",
                "catalog_core_id": aliases[shipped_core_id],
            }
        elif shipped_core_id in uncataloged:
            correlation = {"status": "uncataloged", "catalog_core_id": None}
        else:
            raise PipelineError(
                f"{path} has no exact catalog, alias, or uncataloged roster correlation"
            )
        artifacts.append(
            {
                "path": path,
                "architecture": architecture,
                "shipped_core_id": shipped_core_id,
                "catalog_correlation": correlation,
                "git": {
                    "mode": mode,
                    "object_type": object_type,
                    "blob": blob,
                    "size": size,
                },
                "sha256": hashlib.sha256(data).hexdigest(),
                "elf": elf,
                "architecture_validation": (
                    "valid" if _architecture_valid(architecture, elf) else "invalid"
                ),
            }
        )
    artifacts.sort(key=lambda artifact: artifact["path"])
    if len(artifacts) != 184:
        raise PipelineError(
            f"expected exactly 184 Spruce branch .so artifacts, found {len(artifacts)}"
        )
    return artifacts


def _catalog_cells(
    catalog_core_ids: set[str], artifacts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    exact = {
        (artifact["shipped_core_id"], artifact["architecture"]): artifact
        for artifact in artifacts
        if artifact["catalog_correlation"]["status"] == "catalog_exact"
    }
    cells: list[dict[str, Any]] = []
    for core_id in sorted(catalog_core_ids):
        for architecture in ARCHITECTURES:
            artifact = exact.get((core_id, architecture))
            if artifact is None:
                cells.append(
                    {
                        "core_id": core_id,
                        "architecture": architecture,
                        "status": "not_shipped",
                    }
                )
                continue
            cells.append(
                {
                    "core_id": core_id,
                    "architecture": architecture,
                    "status": artifact["architecture_validation"],
                    "artifact_path": artifact["path"],
                    "artifact_sha256": artifact["sha256"],
                }
            )
    return cells


def _build_basis(
    repository: Path,
    basis_id: str,
    *,
    catalog_core_ids: set[str],
    aliases: dict[str, str],
    uncataloged: set[str],
) -> dict[str, Any]:
    spec = SPRUCE_BRANCH_SPECS[basis_id]
    commit = _git_text(repository, "rev-parse", f"{spec['local_ref']}^{{commit}}")
    tree = _git_text(repository, "rev-parse", f"{commit}^{{tree}}")
    if commit != spec["commit"] or tree != spec["tree"]:
        raise PipelineError(
            f"{spec['local_ref']} moved: expected {spec['commit']} / {spec['tree']}, "
            f"found {commit} / {tree}"
        )
    for architecture, expected in SPRUCE_CORE_TREES.items():
        actual_tree = _git_text(repository, "rev-parse", f"{commit}:{expected['path']}")
        if actual_tree != expected["tree"]:
            raise PipelineError(
                f"{basis_id} {architecture} core tree moved: "
                f"expected {expected['tree']}, found {actual_tree}"
            )
    artifacts = _tree_artifacts(
        repository,
        commit,
        catalog_core_ids=catalog_core_ids,
        aliases=aliases,
        uncataloged=uncataloged,
    )
    cells = _catalog_cells(catalog_core_ids, artifacts)
    status_counts = {
        status: sum(cell["status"] == status for cell in cells)
        for status in ("valid", "not_shipped", "invalid")
    }
    summary = {
        "artifact_count": len(artifacts),
        "shipped_core_name_count": len(
            {artifact["shipped_core_id"] for artifact in artifacts}
        ),
        "catalog_core_count": len(catalog_core_ids),
        "catalog_cell_count": len(cells),
        "valid_catalog_cell_count": status_counts["valid"],
        "not_shipped_catalog_cell_count": status_counts["not_shipped"],
        "invalid_catalog_cell_count": status_counts["invalid"],
        "alias_artifact_count": sum(
            artifact["catalog_correlation"]["status"] == "catalog_alias"
            for artifact in artifacts
        ),
        "uncataloged_artifact_count": sum(
            artifact["catalog_correlation"]["status"] == "uncataloged"
            for artifact in artifacts
        ),
        "artifact_identity_set_sha256": spruce_branch_artifact_identity_set_sha256(
            artifacts
        ),
    }
    basis = {
        "basis_id": basis_id,
        "track": spec["track"],
        "branch": {
            "repository": SPRUCE_REPOSITORY,
            "ref": spec["ref"],
            "commit": commit,
            "tree": tree,
        },
        "core_trees": SPRUCE_CORE_TREES,
        "provenance": {
            "kind": "artifact-only",
            "source_commits": "not-established",
            "submodule_commits": "not-established",
            "build_recipes": "not-established",
            "toolchains": "not-established",
            "reproducible_builds": "not-established",
        },
        "artifacts": artifacts,
        "catalog_cells": cells,
        "summary": summary,
        "content_sha256": "",
    }
    basis["content_sha256"] = spruce_branch_basis_content_sha256(basis)
    return basis


def generate_document(
    *,
    repository: Path,
    catalog_path: Path,
    roster_path: Path,
) -> dict[str, Any]:
    if not (repository / ".git").exists():
        raise PipelineError(f"Spruce repository is not a Git checkout: {repository}")
    catalog, catalog_file_sha256 = load_json_with_sha256(catalog_path)
    roster, roster_file_sha256 = load_json_with_sha256(roster_path)
    catalog_cores = catalog.get("cores")
    if not isinstance(catalog_cores, dict):
        raise PipelineError("core catalog has no exact cores object")
    catalog_core_ids = set(catalog_cores)
    aliases = {
        shipped_id: catalog_core_id
        for catalog_core_id, shipped_ids in roster.get("alias_core_ids", {}).items()
        for shipped_id in shipped_ids
    }
    uncataloged = set(roster.get("uncataloged_core_ids", []))
    bases = {
        basis_id: _build_basis(
            repository,
            basis_id,
            catalog_core_ids=catalog_core_ids,
            aliases=aliases,
            uncataloged=uncataloged,
        )
        for basis_id in sorted(SPRUCE_BRANCH_SPECS)
    }
    artifact_hashes = {
        basis["summary"]["artifact_identity_set_sha256"] for basis in bases.values()
    }
    if len(artifact_hashes) != 1:
        raise PipelineError("reviewed Spruce main and Development core bytes differ")
    artifact_hash = next(iter(artifact_hashes))
    document = {
        "$schema": SPRUCE_BRANCH_BASES_SCHEMA_REF,
        "schema_version": SPRUCE_BRANCH_BASES_SCHEMA_VERSION,
        "basis_model": SPRUCE_BRANCH_BASES_MODEL,
        "provenance_model": SPRUCE_BRANCH_BASES_PROVENANCE_MODEL,
        "catalog": {
            "path": SPRUCE_CATALOG_PATH,
            "file_sha256": catalog_file_sha256,
            "semantic_sha256": catalog_semantic_sha256(catalog),
        },
        "release_roster": {
            "path": SPRUCE_RELEASE_ROSTER_PATH,
            "file_sha256": roster_file_sha256,
            "content_sha256": release_roster_semantic_sha256(roster),
        },
        "bases": bases,
        "cross_branch_core_identity": {
            "basis_ids": sorted(SPRUCE_BRANCH_SPECS),
            "core_trees_identical": True,
            "artifact_bytes_identical": True,
            "core_trees": SPRUCE_CORE_TREES,
            "artifact_identity_set_sha256": artifact_hash,
        },
        "content_sha256": "",
    }
    document["content_sha256"] = spruce_branch_bases_content_sha256(document)
    validate_spruce_branch_bases(
        document,
        catalog=catalog,
        catalog_file_sha256=catalog_file_sha256,
        roster=roster,
        roster_file_sha256=roster_file_sha256,
    )
    return document


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spruce-repository",
        type=Path,
        default=ROOT.parent / "spruceOS",
        help="local SpruceOS Git checkout containing exact origin branch refs",
    )
    parser.add_argument(
        "--catalog", type=Path, default=ROOT / SPRUCE_CATALOG_PATH
    )
    parser.add_argument(
        "--release-roster", type=Path, default=ROOT / SPRUCE_RELEASE_ROSTER_PATH
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "manifests/spruce-core-branch-bases.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail unless the existing output exactly matches regenerated content",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        document = generate_document(
            repository=args.spruce_repository.resolve(),
            catalog_path=args.catalog.resolve(),
            roster_path=args.release_roster.resolve(),
        )
        if args.check:
            if not args.output.is_file():
                raise PipelineError(f"branch-basis registry does not exist: {args.output}")
            existing = json.loads(args.output.read_text(encoding="utf-8"))
            if existing != document:
                raise PipelineError(
                    f"branch-basis registry is stale: regenerate {args.output}"
                )
        else:
            atomic_write_json(args.output, document)
    except (OSError, json.JSONDecodeError, PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "output": str(args.output),
                "content_sha256": document["content_sha256"],
                "bases": {
                    basis_id: {
                        "commit": basis["branch"]["commit"],
                        "content_sha256": basis["content_sha256"],
                        "summary": basis["summary"],
                    }
                    for basis_id, basis in document["bases"].items()
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
