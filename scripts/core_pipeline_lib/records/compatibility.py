"""Individual-core compatibility records over existing one-core pin sets."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
from typing import Any
import zipfile

from ..errors import PipelineError
from ..foundation import (
    load_json,
    sha256_bytes,
    sha256_file,
)


CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORE_PIN_PATH_RE = re.compile(
    r"^pins/core-sets/[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json$"
)
E2E_RUN_PATH_RE = re.compile(
    r"^\.local-e2e/runs/[A-Za-z0-9][A-Za-z0-9._-]{0,127}/e2e-record\.json$"
)
SCHEMA_REFERENCE = "../core-compatibility.schema.json"
HEADER_KEYS = {
    "$schema",
    "schema_version",
    "core_id",
    "publication",
    "evidence_availability",
    "golden_source",
    "content_sha256",
}
CORE_KEYS = {
    "source_commit",
    "e2e_run",
    "selected_e2e_content_sha256",
    "reproduction_run",
    "reproduction_e2e_content_sha256",
    "package_state",
    "package_sha256",
    "caveats",
    "targets",
}
TARGET_KEYS = {
    "state",
    "validation_scope",
    "runtime_validation",
    "artifact_sha256",
    "elf",
    "needed",
    "version_requirements",
}

PinValidator = Callable[..., dict[str, Any]]
E2EValidator = Callable[
    [Path, str, dict[str, dict[str, Any]]], dict[str, Any]
]
ArtifactValidator = Callable[[Path, str], dict[str, Any]]
BuildRecordValidator = Callable[
    [dict[str, Any], Path, dict[str, Any], str], None
]
ContentHasher = Callable[[dict[str, Any]], str]
RunnerValidator = Callable[[object], bool]

SELECTED_RUNNER = {
    "profile": "github-actions",
    "mode": "simulated",
    "backend": "local-docker",
    "local_only": True,
    "publication": "disabled",
}
REPRODUCTION_RUNNER = {
    "profile": "local",
    "mode": "native",
    "backend": "local-docker",
    "local_only": True,
    "publication": "disabled",
}
RESERVED_LEGACY_RUN_TOKEN = "tranche"


def _uses_reserved_legacy_run_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and RESERVED_LEGACY_RUN_TOKEN in value.casefold()
    )


def _require_lexical_evidence_path(
    path: Path,
    allowed_root: Path,
    label: str,
) -> Path:
    """Keep an evidence path contained without resolving away symlinks."""

    lexical_path = path if path.is_absolute() else Path.cwd() / path
    lexical_root = (
        allowed_root
        if allowed_root.is_absolute()
        else Path.cwd() / allowed_root
    )
    if ".." in lexical_path.parts or ".." in lexical_root.parts:
        raise PipelineError(f"{label} path must not contain parent traversal")
    lexical_path = lexical_path.absolute()
    lexical_root = lexical_root.absolute()
    try:
        lexical_path.relative_to(lexical_root)
    except ValueError as exc:
        raise PipelineError(
            f"{label} must be contained by {lexical_root}"
        ) from exc

    current = Path(lexical_path.parts[0])
    try:
        if current.is_symlink():
            raise PipelineError(f"{label} path must not traverse a symlink")
        for part in lexical_path.parts[1:]:
            current /= part
            if current.is_symlink():
                raise PipelineError(
                    f"{label} path must not traverse a symlink"
                )
    except OSError as exc:
        raise PipelineError(f"cannot inspect {label} path: {exc}") from exc
    try:
        resolved_path = lexical_path.resolve()
        resolved_root = lexical_root.resolve()
    except (OSError, RuntimeError) as exc:
        raise PipelineError(f"cannot inspect {label} path: {exc}") from exc
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise PipelineError(
            f"{label} must be contained by {lexical_root}"
        ) from exc
    return lexical_path


def _lexical_evidence_child(
    root: Path,
    relative: object,
    allowed_root: Path,
    label: str,
) -> Path:
    """Return one exact relative evidence child without symlink traversal."""

    if not isinstance(relative, str) or not relative:
        raise PipelineError(f"{label} path is not an exact relative path")
    child = Path(relative)
    if (
        child.is_absolute()
        or child.as_posix() != relative
        or any(part in {"", ".", ".."} for part in child.parts)
    ):
        raise PipelineError(f"{label} path is not an exact relative path")
    return _require_lexical_evidence_path(
        root / child,
        allowed_root,
        label,
    )


def core_compatibility_content_sha256(document: dict[str, Any]) -> str:
    """Hash semantic fields while excluding schema routing and the digest."""

    material = {
        key: value
        for key, value in document.items()
        if key not in {"$schema", "content_sha256"}
    }
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def _is_string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and item for item in value)
    )


def _compatibility_elf_label(
    architecture: str, artifact: dict[str, Any]
) -> str:
    """Derive the compact compatibility label from validated ELF evidence."""

    elf = artifact.get("elf")
    if not isinstance(elf, dict):
        raise PipelineError("compatibility artifact ELF evidence is invalid")
    label = f"{elf.get('class')}/{elf.get('machine')}"
    if architecture == "armhf":
        label += " hard-float"
    return label


def validate_core_e2e_run(
    e2e_path: Path,
    core_id: str,
    *,
    repository_root: Path,
    runs_root: Path,
    expected_targets: set[str],
    package_directories: dict[str, str],
    expected_build_records: dict[str, dict[str, Any]],
    artifact_validator: ArtifactValidator,
    build_record_validator: BuildRecordValidator,
    content_hasher: ContentHasher,
    runner_validator: RunnerValidator,
) -> dict[str, Any]:
    """Validate immutable ignored E2E bytes without current-recipe coupling."""

    e2e_path = _require_lexical_evidence_path(
        e2e_path, runs_root, "individual core compatibility E2E record"
    )
    if e2e_path.name != "e2e-record.json":
        raise PipelineError("compatibility E2E record path is invalid")
    try:
        evidence_bytes = e2e_path.read_bytes()
        evidence = json.loads(evidence_bytes)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PipelineError(f"cannot load compatibility E2E record: {exc}") from exc
    if not isinstance(evidence, dict):
        raise PipelineError("compatibility E2E record must be a JSON object")
    schema_version = evidence.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        raise PipelineError("compatibility E2E schema version is invalid")
    if schema_version == 1 and "runner" in evidence:
        raise PipelineError("legacy compatibility E2E record names runner evidence")
    if schema_version == 2 and not runner_validator(evidence.get("runner")):
        raise PipelineError("compatibility E2E runner evidence is invalid")
    run_id = evidence.get("run_id")
    if _uses_reserved_legacy_run_name(run_id):
        raise PipelineError(
            "individual core compatibility E2E run_id uses reserved legacy "
            "tranche name"
        )
    if (
        run_id != e2e_path.parent.name
        or evidence.get("result") != "passed"
        or evidence.get("local_only") is not True
        or evidence.get("publication") != "disabled"
        or evidence.get("content_sha256") != content_hasher(evidence)
    ):
        raise PipelineError("compatibility E2E record contract is invalid")
    if (
        not expected_targets
        or set(package_directories) != expected_targets
        or set(expected_build_records) != expected_targets
    ):
        raise PipelineError("compatibility E2E target contract is invalid")

    builds = evidence.get("builds")
    if not isinstance(builds, list) or any(
        not isinstance(item, dict) for item in builds
    ):
        raise PipelineError("compatibility E2E builds are invalid")
    if (
        len(builds) != len(expected_targets)
        or {item.get("core_id") for item in builds} != {core_id}
        or {item.get("architecture") for item in builds} != expected_targets
        or any(item.get("result") != "passed" for item in builds)
    ):
        raise PipelineError(
            "compatibility E2E must contain exactly one core's passing targets"
        )

    run_root = e2e_path.parent
    records: dict[str, dict[str, Any]] = {}
    normalized_targets: dict[str, dict[str, Any]] = {}
    for entry in builds:
        architecture = entry["architecture"]
        record_path = _lexical_evidence_child(
            repository_root,
            entry.get("record", ""),
            run_root,
            "compatibility E2E build record",
        )
        if (
            not record_path.is_file()
            or sha256_file(record_path) != entry.get("record_sha256")
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility build record digest is invalid"
            )
        record = load_json(record_path)
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != architecture
            or record.get("result") != "passed"
            or record.get("build_exit_code") != 0
            or record.get("local_only") is not True
            or record.get("publication") != "disabled"
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility build record is invalid"
            )
        source = record.get("source")
        if (
            not isinstance(source, dict)
            or not SHA1_RE.fullmatch(source.get("commit", ""))
            or source.get("resolved_commit") != source.get("commit")
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility source is invalid"
            )
        build = record.get("build")
        if not isinstance(build, dict) or not isinstance(build.get("log"), str):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility build contract is invalid"
            )
        log_path = _lexical_evidence_child(
            record_path.parent,
            build["log"],
            record_path.parent,
            "compatibility build log",
        )
        if (
            log_path.name != "build.log"
            or not log_path.is_file()
            or sha256_file(log_path) != build.get("log_sha256")
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility build log bytes are invalid"
            )
        try:
            build_log_text = log_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PipelineError(
                f"{core_id}/{architecture}: cannot read compatibility build log: {exc}"
            ) from exc
        build_record_validator(
            record,
            record_path,
            expected_build_records[architecture],
            build_log_text,
        )
        artifact = record.get("artifact")
        if not isinstance(artifact, dict) or not isinstance(
            artifact.get("path"), str
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility artifact record is invalid"
            )
        artifact_path = _lexical_evidence_child(
            record_path.parent,
            artifact["path"],
            record_path.parent,
            "compatibility build artifact",
        )
        current_artifact = artifact_validator(artifact_path, architecture)
        if not isinstance(current_artifact, dict):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility artifact validator failed"
            )
        bound_artifact_fields = (
            "sha256",
            "size",
            "elf",
            "needed",
            "version_requirements",
        )
        if (
            artifact.get("status") != "valid"
            or current_artifact.get("status") != "valid"
            or any(
                current_artifact.get(field) != artifact.get(field)
                for field in bound_artifact_fields
            )
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility artifact bytes are invalid"
            )
        metadata = record.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("path"), str
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility metadata is invalid"
            )
        metadata_path = _lexical_evidence_child(
            record_path.parent,
            metadata["path"],
            record_path.parent,
            "compatibility build metadata",
        )
        if (
            metadata.get("status") != "valid"
            or not metadata_path.is_file()
            or metadata_path.stat().st_size != metadata.get("size")
            or sha256_file(metadata_path) != metadata.get("sha256")
        ):
            raise PipelineError(
                f"{core_id}/{architecture}: compatibility metadata bytes are invalid"
            )
        records[architecture] = record
        normalized_targets[architecture] = {
            "record_sha256": entry["record_sha256"],
            "source_commit": source["commit"],
            "artifact_sha256": current_artifact["sha256"],
            "elf": _compatibility_elf_label(architecture, current_artifact),
            "needed": current_artifact["needed"],
            "version_requirements": current_artifact["version_requirements"],
        }

    packages = evidence.get("packages")
    if (
        not isinstance(packages, list)
        or len(packages) != 1
        or not isinstance(packages[0], dict)
        or packages[0].get("core_id") != core_id
        or packages[0].get("result") != "packaged"
    ):
        raise PipelineError(
            "compatibility E2E must contain exactly one packaged core"
        )
    package_record = packages[0]
    package_path = _lexical_evidence_child(
        run_root,
        package_record.get("path", ""),
        run_root,
        "compatibility E2E package",
    )
    if (
        package_path.name != f"{core_id}_libretro.zip"
        or not package_path.is_file()
        or package_path.stat().st_size != package_record.get("size")
        or sha256_file(package_path) != package_record.get("sha256")
    ):
        raise PipelineError("compatibility E2E package bytes are invalid")

    try:
        with zipfile.ZipFile(package_path) as archive:
            expected_members = {"manifest.json"}
            manifest = json.loads(archive.read("manifest.json"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("core_id") != core_id
                or manifest.get("local_only") is not True
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != expected_targets
            ):
                raise PipelineError("compatibility package manifest is invalid")
            metadata_names = {
                record.get("metadata", {}).get("path") for record in records.values()
            }
            metadata_hashes = {
                record.get("metadata", {}).get("sha256")
                for record in records.values()
            }
            if len(metadata_names) != 1 or len(metadata_hashes) != 1:
                raise PipelineError("compatibility package metadata is inconsistent")
            metadata_name = next(iter(metadata_names))
            metadata_sha256 = next(iter(metadata_hashes))
            if not isinstance(metadata_name, str) or not isinstance(
                metadata_sha256, str
            ):
                raise PipelineError("compatibility package metadata is invalid")
            expected_members.add(metadata_name)
            if (
                manifest.get("metadata", {}).get("path") != metadata_name
                or manifest.get("metadata", {}).get("sha256") != metadata_sha256
                or sha256_bytes(archive.read(metadata_name)) != metadata_sha256
            ):
                raise PipelineError("compatibility package metadata bytes are invalid")
            for architecture, record in records.items():
                artifact = record["artifact"]
                member = f"{package_directories[architecture]}/{artifact['path']}"
                expected_members.add(member)
                packaged = manifest["artifacts"][architecture]
                if (
                    packaged.get("path") != member
                    or packaged.get("sha256") != artifact.get("sha256")
                    or packaged.get("source_commit")
                    != record.get("source", {}).get("resolved_commit")
                    or sha256_bytes(archive.read(member)) != artifact.get("sha256")
                ):
                    raise PipelineError(
                        f"{core_id}/{architecture}: compatibility package artifact "
                        "bytes are invalid"
                    )
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist()) != expected_members
            ):
                raise PipelineError("compatibility package members are invalid")
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        raise PipelineError(f"cannot validate compatibility package: {exc}") from exc

    return {
        "run_id": evidence["run_id"],
        "runner": evidence.get("runner"),
        "content_sha256": evidence["content_sha256"],
        "package_sha256": package_record["sha256"],
        "targets": normalized_targets,
    }


def validate_core_compatibility_document(
    document: dict[str, Any],
    *,
    document_path: Path | None = None,
    repository_root: Path,
    verify_pin: bool = True,
    pin_validator: PinValidator | None = None,
    e2e_validator: E2EValidator | None = None,
) -> dict[str, Any]:
    """Validate one core-owned compatibility document and its pinned evidence."""

    errors: list[str] = []
    if set(document) != HEADER_KEYS | CORE_KEYS:
        errors.append("core compatibility fields are incomplete or unknown")
    if document.get("$schema") != SCHEMA_REFERENCE:
        errors.append("core compatibility schema reference is invalid")
    if type(document.get("schema_version")) is not int or document.get(
        "schema_version"
    ) != 1:
        errors.append("core compatibility schema_version must be 1")
    core_id = document.get("core_id")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        errors.append("core compatibility core_id is invalid")
        core_id = ""
    if (
        document.get("publication") != "disabled"
        or document.get("evidence_availability") != "workspace-local-ignored"
    ):
        errors.append("core compatibility must remain local-only evidence")
    if document.get("content_sha256") != core_compatibility_content_sha256(document):
        errors.append("core compatibility content digest is invalid")
    source_commit = document.get("source_commit")
    if not isinstance(source_commit, str) or SHA1_RE.fullmatch(source_commit) is None:
        errors.append("core compatibility source_commit is invalid")
    if document.get("package_state") != "reproducible":
        errors.append("individual promoted core must have a reproducible package")
    e2e_run = document.get("e2e_run")
    if not isinstance(e2e_run, str) or E2E_RUN_PATH_RE.fullmatch(e2e_run) is None:
        errors.append("core compatibility e2e_run is invalid")
    elif _uses_reserved_legacy_run_name(e2e_run):
        errors.append(
            "core compatibility e2e_run uses reserved legacy tranche name"
        )
    selected_e2e_content_sha256 = document.get(
        "selected_e2e_content_sha256"
    )
    if (
        not isinstance(selected_e2e_content_sha256, str)
        or SHA256_RE.fullmatch(selected_e2e_content_sha256) is None
    ):
        errors.append("core compatibility selected E2E content digest is invalid")
    reproduction_run = document.get("reproduction_run")
    if (
        not isinstance(reproduction_run, str)
        or E2E_RUN_PATH_RE.fullmatch(reproduction_run) is None
    ):
        errors.append("core compatibility reproduction_run is invalid")
    elif _uses_reserved_legacy_run_name(reproduction_run):
        errors.append(
            "core compatibility reproduction_run uses reserved legacy tranche name"
        )
    elif reproduction_run == e2e_run:
        errors.append("core compatibility reproduction_run must be independent")
    reproduction_e2e_content_sha256 = document.get(
        "reproduction_e2e_content_sha256"
    )
    if (
        not isinstance(reproduction_e2e_content_sha256, str)
        or SHA256_RE.fullmatch(reproduction_e2e_content_sha256) is None
    ):
        errors.append(
            "core compatibility reproduction E2E content digest is invalid"
        )
    if not _is_string_list(document.get("caveats")):
        errors.append("core compatibility caveats are invalid")
    package_sha256 = document.get("package_sha256")
    if (
        not isinstance(package_sha256, str)
        or SHA256_RE.fullmatch(package_sha256) is None
    ):
        errors.append("core compatibility package digest is invalid")

    targets = document.get("targets")
    valid_targets: dict[str, dict[str, Any]] = {}
    if not isinstance(targets, dict) or not targets:
        errors.append("core compatibility targets must not be empty")
        targets = {}
    for architecture, target in targets.items():
        label = f"{core_id}/{architecture}"
        if architecture not in {"arm64", "armhf"} or not isinstance(target, dict):
            errors.append(f"{label}: compatibility target is invalid")
            continue
        valid_targets[architecture] = target
        if set(target) != TARGET_KEYS:
            errors.append(f"{label}: compatibility target fields are invalid")
        if (
            target.get("state") != "local_static_build_golden"
            or target.get("validation_scope") != "static-build-only"
            or target.get("runtime_validation") != "needs-target-runtime"
        ):
            errors.append(f"{label}: compatibility target state is invalid")
        artifact_sha256 = target.get("artifact_sha256")
        if (
            not isinstance(artifact_sha256, str)
            or SHA256_RE.fullmatch(artifact_sha256) is None
        ):
            errors.append(f"{label}: artifact digest is invalid")
        expected_elf = {
            "arm64": "ELF64/AArch64",
            "armhf": "ELF32/ARM hard-float",
        }.get(architecture)
        if target.get("elf") != expected_elf:
            errors.append(f"{label}: ELF label is invalid")
        if not _is_string_list(target.get("needed")):
            errors.append(f"{label}: needed libraries are invalid")
        if not _is_string_list(target.get("version_requirements")):
            errors.append(f"{label}: version requirements are invalid")

    pin_relative = document.get("golden_source")
    pin = None
    pin_path = None
    if (
        not isinstance(pin_relative, str)
        or CORE_PIN_PATH_RE.fullmatch(pin_relative) is None
    ):
        errors.append("core compatibility golden_source is invalid")
    elif verify_pin:
        try:
            pin_path = _lexical_evidence_child(
                repository_root,
                pin_relative,
                repository_root / "pins" / "core-sets",
                "individual core pin",
            )
            pin = load_json(pin_path)
        except PipelineError as exc:
            errors.append(str(exc))

    if pin is not None:
        if pin_validator is None:
            errors.append("individual core pin deep validator is unavailable")
        else:
            try:
                pin_report = pin_validator(
                    pin,
                    verify_store=True,
                    verify_sources=True,
                    document_path=pin_path,
                )
                pin_errors = (
                    pin_report.get("errors") if isinstance(pin_report, dict) else None
                )
                if not isinstance(pin_errors, list):
                    errors.append("individual core pin deep validator failed closed")
                else:
                    errors.extend(
                        f"individual core pin: {error}" for error in pin_errors
                    )
            except (
                AttributeError,
                KeyError,
                OSError,
                PipelineError,
                TypeError,
                ValueError,
            ) as exc:
                errors.append(f"individual core pin deep validation failed: {exc}")

        pin_cores = pin.get("cores")
        if not isinstance(pin_cores, dict):
            errors.append("individual core pin selections are invalid")
            pin_cores = {}
        if pin.get("scope") != [core_id] or set(pin_cores) != {core_id}:
            errors.append("individual core pin scope differs")
        core_pin = pin_cores.get(core_id)
        selection = (
            core_pin.get("selection", {}) if isinstance(core_pin, dict) else {}
        )
        if not isinstance(selection, dict):
            errors.append("individual core pin selection is invalid")
            selection = {}
        selection_sha256 = selection.get("selection_sha256")
        if (
            not isinstance(selection_sha256, str)
            or SHA256_RE.fullmatch(selection_sha256) is None
        ):
            errors.append("individual core pin selection digest is invalid")
        if pin.get("parent") is not None:
            errors.append("individual core pin parent must be null")
        if (
            core_id
            and isinstance(source_commit, str)
            and SHA1_RE.fullmatch(source_commit) is not None
            and isinstance(selection_sha256, str)
            and SHA256_RE.fullmatch(selection_sha256) is not None
        ):
            semantic_id = (
                f"{core_id}-{source_commit[:12]}-{selection_sha256[:12]}"
            )
            if pin.get("pin_id") != semantic_id:
                errors.append("individual core pin ID is not semantic")
            if pin_relative != f"pins/core-sets/{semantic_id}.json":
                errors.append("individual core pin filename is not semantic")
        selected_e2e = selection.get("e2e")
        selected_run_id = (
            selected_e2e.get("run_id") if isinstance(selected_e2e, dict) else None
        )
        if (
            not isinstance(selected_run_id, str)
            or e2e_run
            != f".local-e2e/runs/{selected_run_id}/e2e-record.json"
        ):
            errors.append("individual core selected E2E run differs from compatibility")
        selected_package = selection.get("package")
        if (
            not isinstance(selected_package, dict)
            or selected_package.get("sha256") != package_sha256
        ):
            errors.append("individual core package differs from compatibility")
        selected_targets = selection.get("targets", {})
        if not isinstance(selected_targets, dict):
            errors.append("individual core pin targets are invalid")
            selected_targets = {}
        if set(selected_targets) != set(targets):
            errors.append("individual core target set differs from compatibility")
        expected_build_records: dict[str, dict[str, Any]] = {}
        for architecture, target in valid_targets.items():
            selected_target = selected_targets.get(architecture)
            golden = (
                selected_target.get("golden_record", {})
                if isinstance(selected_target, dict)
                else {}
            )
            if not isinstance(golden, dict):
                golden = {}
            if isinstance(selected_target, dict):
                expected_build_records[architecture] = selected_target
            artifact = golden.get("artifact", {})
            if not isinstance(artifact, dict):
                artifact = {}
            source = golden.get("source")
            if (
                not isinstance(source, dict)
                or source.get("commit") != source_commit
            ):
                errors.append(
                    f"{core_id}/{architecture}: source differs from compatibility"
                )
            if artifact.get("sha256") != target.get("artifact_sha256"):
                errors.append(
                    f"{core_id}/{architecture}: artifact differs from compatibility"
                )
            if artifact.get("needed") != target.get("needed"):
                errors.append(
                    f"{core_id}/{architecture}: libraries differ from compatibility"
                )
            if artifact.get("version_requirements") != target.get(
                "version_requirements"
            ):
                errors.append(
                    f"{core_id}/{architecture}: versions differ from compatibility"
                )

        verified_runs: dict[str, dict[str, Any]] = {}
        for run_kind, run_reference in (
            ("selected", e2e_run),
            ("reproduction", reproduction_run),
        ):
            if not isinstance(run_reference, str) or E2E_RUN_PATH_RE.fullmatch(
                run_reference
            ) is None:
                continue
            if e2e_validator is None:
                errors.append(
                    f"individual core {run_kind} E2E deep validator is unavailable"
                )
                continue
            try:
                run_path = _lexical_evidence_child(
                    repository_root,
                    run_reference,
                    repository_root / ".local-e2e" / "runs",
                    f"individual core {run_kind} E2E record",
                )
                if not run_path.is_file():
                    errors.append(
                        f"individual core {run_kind} E2E record is unavailable"
                    )
                    continue
                verified = e2e_validator(
                    run_path,
                    core_id,
                    expected_build_records,
                )
                if not isinstance(verified, dict):
                    errors.append(
                        f"individual core {run_kind} E2E validator failed closed"
                    )
                    continue
                verified_runs[run_kind] = verified
            except (
                AttributeError,
                KeyError,
                OSError,
                PipelineError,
                TypeError,
                ValueError,
            ) as exc:
                errors.append(
                    f"individual core {run_kind} E2E validation failed: {exc}"
                )

        for run_kind, verified in verified_runs.items():
            run_reference = e2e_run if run_kind == "selected" else reproduction_run
            expected_run_id = Path(run_reference).parent.name
            if _uses_reserved_legacy_run_name(verified.get("run_id")):
                errors.append(
                    f"individual core {run_kind} E2E run_id uses reserved legacy "
                    "tranche name"
                )
            if verified.get("run_id") != expected_run_id:
                errors.append(
                    f"individual core {run_kind} E2E run ID is not path-bound"
                )
            expected_runner = (
                SELECTED_RUNNER
                if run_kind == "selected"
                else REPRODUCTION_RUNNER
            )
            if verified.get("runner") != expected_runner:
                errors.append(
                    f"individual core {run_kind} E2E runner profile is invalid"
                )
            expected_content_sha256 = (
                selected_e2e_content_sha256
                if run_kind == "selected"
                else reproduction_e2e_content_sha256
            )
            if verified.get("content_sha256") != expected_content_sha256:
                errors.append(
                    f"individual core {run_kind} E2E content differs from compatibility"
                )
            if verified.get("package_sha256") != package_sha256:
                errors.append(
                    f"individual core {run_kind} E2E package differs from compatibility"
                )
            run_targets = verified.get("targets")
            if not isinstance(run_targets, dict) or set(run_targets) != set(targets):
                errors.append(
                    f"individual core {run_kind} E2E target set differs from compatibility"
                )
                run_targets = {}
            for architecture, target in valid_targets.items():
                evidence_target = run_targets.get(architecture)
                if not isinstance(evidence_target, dict):
                    continue
                expected_fields = {
                    "source_commit": source_commit,
                    "artifact_sha256": target.get("artifact_sha256"),
                    "elf": target.get("elf"),
                    "needed": target.get("needed"),
                    "version_requirements": target.get("version_requirements"),
                }
                for field, expected in expected_fields.items():
                    if evidence_target.get(field) != expected:
                        errors.append(
                            f"{core_id}/{architecture}: {run_kind} E2E {field} "
                            "differs from compatibility"
                        )

        selected_verified = verified_runs.get("selected")
        if selected_verified is not None:
            if (
                not isinstance(selected_e2e, dict)
                or selected_verified.get("content_sha256")
                != selected_e2e.get("content_sha256")
            ):
                errors.append("individual core selected E2E content differs from pin")
            if (
                isinstance(selected_e2e, dict)
                and selected_e2e.get("content_sha256")
                != selected_e2e_content_sha256
            ):
                errors.append(
                    "individual core selected E2E content binding differs from pin"
                )
            selected_run_targets = selected_verified.get("targets")
            if isinstance(selected_run_targets, dict):
                raw_build_records = (
                    selected_e2e.get("build_records", {})
                    if isinstance(selected_e2e, dict)
                    else {}
                )
                build_records = (
                    raw_build_records
                    if isinstance(raw_build_records, dict)
                    else {}
                )
                for architecture, evidence_target in selected_run_targets.items():
                    if (
                        not isinstance(evidence_target, dict)
                        or evidence_target.get("record_sha256")
                        != build_records.get(architecture)
                    ):
                        errors.append(
                            f"{core_id}/{architecture}: selected E2E build record "
                            "differs from pin"
                        )

        selected_verified = verified_runs.get("selected")
        reproduction_verified = verified_runs.get("reproduction")
        if (
            selected_verified is not None
            and reproduction_verified is not None
            and selected_verified.get("run_id")
            == reproduction_verified.get("run_id")
        ):
            errors.append("individual core E2E run IDs must be distinct")

    if document_path is not None and core_id:
        try:
            checked_document_path = _require_lexical_evidence_path(
                document_path,
                repository_root / "manifests" / "compatibility",
                "core compatibility document",
            )
            relative = checked_document_path.relative_to(
                repository_root.absolute()
            )
            if relative.as_posix() != f"manifests/compatibility/{core_id}.json":
                errors.append("core compatibility path does not bind core_id")
        except (PipelineError, ValueError) as exc:
            errors.append(str(exc))
    return {"status": "valid" if not errors else "invalid", "errors": errors}
