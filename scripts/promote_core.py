#!/usr/bin/env python3
"""Compose the hand-authored tail of a canonical core promotion.

The pipeline provides commands for the build/promote chain (import-golden,
promote, derive-core-id, compose-core-golden, compose-pin-set); this tool owns
the lifecycle tail. The source lock and source-set are composed in memory
(records.source is the single composer; they are never written as files), and
the one remaining written lifecycle artifact is the compatibility manifest
(manifests/compatibility/<core>.json), fully determined by evidence that
already exists after the pin is composed. The device-eligibility caveat (the
ABI-ceiling reasoning) is derived from the captured version_requirements
rather than retyped per core.

Full promotion sequence (this tool is the last step):

  build-core --runner-profile github-actions-sim --core C --run-id SEL
  build-core --runner-profile local            --core C --run-id REP
  import-golden --core C --spruceos ../spruceOS --output NIGHTLY_CANDIDATE
  promote (arm64) ; promote (armhf) into the candidate
  derive-core-id --core C --source-golden CANDIDATE
  compose-core-golden ; compose-pin-set
  promote_core.py compose-lifecycle --core C --semantic-id SID \\
      --selected-run SEL --reproduction-run REP [--caveat "..."]

Local, read-only over inputs, create-only over outputs; never publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, NamedTuple


ROOT = Path(__file__).resolve().parents[1]

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from core_pipeline_lib.errors import PipelineError  # noqa: E402
from core_pipeline_lib.foundation import (  # noqa: E402
    decode_json_object,
    manifest_lock,
)
from core_pipeline_lib.records import source as records_source  # noqa: E402

# Captured device provider ceilings (device-runtime-contracts.json). Used only
# to phrase the device-eligibility caveat; the machine-readable screen lives in
# device_sets.py.
MINI_GLIBCXX_CEILING = (3, 4, 24)
A30_GLIBCXX_CEILING = (3, 4, 32)
ELF_LABEL = {"arm64": "ELF64/AArch64", "armhf": "ELF32/ARM hard-float"}


class PromoteCoreError(Exception):
    """Raised for missing or inconsistent promotion inputs."""


class PipelineCommandError(PromoteCoreError):
    """A pipeline command failed after emitting captured process output."""

    def __init__(self, message: str, *, stdout: str, stderr: str) -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class _OrdinaryLifecycleSnapshot(NamedTuple):
    """One operation's exact pin, catalog, golden, and E2E authority."""

    source_set: dict[str, Any]
    semantic_pin: tuple[str, dict[str, Any], str, dict[str, Any]]
    catalog: dict[str, Any]
    evidence_files: tuple[tuple[Path, str, str], ...]


def _exact_file_digest(path: Path, label: str) -> str:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PromoteCoreError(f"cannot read {label}: {exc}") from exc
    if path.is_symlink() or not path.is_file():
        raise PromoteCoreError(f"{label} is not a regular file: {path}")
    return hashlib.sha256(raw).hexdigest()


def _require_lifecycle_snapshot_unchanged(
    snapshot: _OrdinaryLifecycleSnapshot,
) -> None:
    """Recheck all captured authority immediately before returning/writing."""

    for path, expected_sha256, label in snapshot.evidence_files:
        if _exact_file_digest(path, label) != expected_sha256:
            raise PromoteCoreError(f"{label} changed during lifecycle composition")


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromoteCoreError(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PromoteCoreError(f"invalid JSON in {path}: {exc}") from exc


def _load_with_sha256(path: Path) -> tuple[dict[str, Any], str]:
    """Load and hash one exact JSON snapshot from the same bytes."""

    try:
        raw = path.read_bytes()
        document = decode_json_object(raw, path)
    except (OSError, PipelineError) as exc:
        raise PromoteCoreError(f"cannot load exact input {path}: {exc}") from exc
    if path.is_symlink() or not path.is_file():
        raise PromoteCoreError(f"input is not a regular file: {path}")
    return document, hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_sha256(document: dict[str, Any]) -> str:
    material = {k: v for k, v in document.items() if k not in {"$schema", "content_sha256"}}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    return tuple(int(p) for p in parts) if all(p.isdecimal() for p in parts) else ()


def max_glibcxx(version_requirements: list[str]) -> tuple[str | None, tuple[int, ...]]:
    best_value, best_key = None, ()
    for symbol in version_requirements:
        if symbol.startswith("GLIBCXX_"):
            key = _version_tuple(symbol[len("GLIBCXX_") :])
            if key and key >= best_key:
                best_key, best_value = key, symbol[len("GLIBCXX_") :]
    return best_value, best_key


def _require_ordinary_selection(
    core_id: str,
    selection: dict[str, Any],
    *,
    operation: str,
) -> None:
    """Keep the canonical lifecycle writer out of candidate lanes."""

    if "source_candidate" in selection or "output_reproduction" in selection:
        raise PromoteCoreError(
            f"{operation} refuses source-candidate/output-reproduction evidence"
        )
    targets = selection.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise PromoteCoreError(f"{operation} has no selected targets for {core_id}")
    for architecture, raw_target in targets.items():
        golden_record = (
            raw_target.get("golden_record")
            if isinstance(raw_target, dict)
            else None
        )
        if not isinstance(golden_record, dict):
            raise PromoteCoreError(
                f"{operation} has a malformed selected golden for "
                f"{core_id}/{architecture}"
            )
        if (
            "source_candidate" in golden_record
            or "output_reproduction" in golden_record
        ):
            raise PromoteCoreError(
                f"{operation} refuses source-candidate/output-reproduction "
                f"evidence for {core_id}/{architecture}"
            )


def _validation_pipeline():
    """Return the launcher module that owns deep historical evidence proof."""

    import core_pipeline as pipeline

    if pipeline.ROOT.resolve() != ROOT.resolve():
        raise PromoteCoreError(
            "canonical lifecycle validation root differs from the writer root"
        )
    return pipeline


def _require_deep_ordinary_pin_evidence(
    semantic_id: str,
    semantic_pin: tuple[str, dict[str, Any], str, dict[str, Any]],
    catalog: dict[str, Any],
    catalog_file_sha256: str,
) -> None:
    """Bind the semantic pin to raw historical E2E/store/recipe bytes."""

    _core_id, pin, pin_file_sha256, _selection = semantic_pin
    pin_path = ROOT / "pins" / "core-sets" / f"{semantic_id}.json"
    pipeline = _validation_pipeline()
    authenticated_catalog, authenticated_catalog_file_sha256 = (
        pipeline.load_catalog_with_sha256(
            ROOT / "manifests" / "core-builds.json"
        )
    )
    if (
        authenticated_catalog != catalog
        or authenticated_catalog_file_sha256 != catalog_file_sha256
    ):
        raise PromoteCoreError(
            "canonical catalog changed before lifecycle evidence validation"
        )
    report = pipeline._validate_pin_set_document(
        pin,
        verify_store=True,
        verify_sources=True,
        document_path=pin_path,
        historical_recipe_proofs=True,
    )
    errors = report.get("errors") if isinstance(report, dict) else None
    if (
        not isinstance(report, dict)
        or report.get("status") != "valid"
        or not isinstance(errors, list)
        or errors
    ):
        details = (
            "; ".join(str(error) for error in errors)
            if isinstance(errors, list) and errors
            else "validator returned no exact valid report"
        )
        raise PromoteCoreError(
            "canonical lifecycle pin lacks complete historical evidence: "
            + details
        )
    final_pin, final_pin_file_sha256 = records_source._load_with_sha256(pin_path)
    final_catalog, final_catalog_file_sha256 = records_source._load_with_sha256(
        ROOT / "manifests" / "core-builds.json"
    )
    if final_pin != pin or final_pin_file_sha256 != pin_file_sha256:
        raise PromoteCoreError(
            "canonical lifecycle pin changed during deep validation"
        )
    if (
        final_catalog != catalog
        or final_catalog_file_sha256 != catalog_file_sha256
    ):
        raise PromoteCoreError(
            "canonical catalog changed during lifecycle composition"
        )


def _ordinary_source_set_snapshot(
    semantic_id: str,
    *,
    operation: str,
) -> _OrdinaryLifecycleSnapshot:
    """Read one semantic pin, reject candidates, and compose canonically."""

    try:
        semantic_pin = records_source.load_semantic_pin(
            semantic_id,
            repository_root=ROOT,
        )
        core_id, pin, pin_file_sha256, selection = semantic_pin
        _require_ordinary_selection(
            core_id,
            selection,
            operation=operation,
        )
        catalog, catalog_file_sha256 = records_source._load_with_sha256(
            ROOT / "manifests" / "core-builds.json"
        )
        source_set = records_source._compose_source_set_from_semantic_pin(
            semantic_id,
            semantic_pin,
            repository_root=ROOT,
            catalog=catalog,
        )
        golden_path = ROOT / pin["sources"][0]["path"]
        golden_file_sha256 = _exact_file_digest(
            golden_path, "canonical semantic golden"
        )
        _require_deep_ordinary_pin_evidence(
            semantic_id,
            semantic_pin,
            catalog,
            catalog_file_sha256,
        )
    except PipelineError as exc:
        raise PromoteCoreError(str(exc)) from exc
    snapshot = _OrdinaryLifecycleSnapshot(
        source_set=source_set,
        semantic_pin=semantic_pin,
        catalog=catalog,
        evidence_files=(
            (
                ROOT / "manifests" / "core-builds.json",
                catalog_file_sha256,
                "canonical catalog",
            ),
            (
                ROOT / "pins" / "core-sets" / f"{semantic_id}.json",
                pin_file_sha256,
                "canonical semantic pin",
            ),
            (
                golden_path,
                golden_file_sha256,
                "canonical semantic golden",
            ),
        ),
    )
    _require_lifecycle_snapshot_unchanged(snapshot)
    return snapshot


def compose_source_set(semantic_id: str) -> dict[str, Any]:
    """Compose one canonical, ordinary source-set from its exact pin."""

    snapshot = _ordinary_source_set_snapshot(
        semantic_id,
        operation="canonical source-set composition",
    )
    _require_lifecycle_snapshot_unchanged(snapshot)
    return snapshot.source_set


def compose_source_lock(core_id: str) -> dict[str, Any]:
    """Compose a core's source lock (records.source is the single composer)."""

    try:
        return records_source.compose_source_lock(core_id, repository_root=ROOT)
    except PipelineError as exc:
        raise PromoteCoreError(str(exc)) from exc


def _device_caveat(targets: dict[str, Any]) -> str:
    armhf = targets.get("armhf", {})
    value, key = max_glibcxx(armhf.get("version_requirements", []))
    if value is None:
        return (
            "The armhf artifact has no libstdc++ dependency, so it clears every "
            "captured provider ceiling; ARM64 is bound to ra64-universal-v1 and "
            "ARMHF to ra32-a30-v1. Provider inspection and target-runtime capture "
            "are absent, so every device view remains provisional and ineligible "
            "pending a runtime smoke result."
        )
    if key > MINI_GLIBCXX_CEILING:
        eligibility = (
            f"ARMHF requires GLIBCXX_{value}, above the observed non-enforcing "
            "Miyoo Mini fallback provider value GLIBCXX_3.4.24, so the Mini "
            "profile is ineligible; A30 is the eligible 32-bit consumer at the "
            "ABI screen."
        )
    else:
        eligibility = (
            f"ARMHF's maximum GLIBCXX_{value} is within the observed Miyoo Mini "
            "fallback provider ceiling GLIBCXX_3.4.24, so both the Mini and A30 "
            "profiles clear the ABI screen."
        )
    return (
        "This is static build/package evidence only. ARM64 is build-identity-"
        f"bound to ra64-universal-v1 and ARMHF to ra32-a30-v1. {eligibility} "
        "Provider inspection and target-runtime capture are absent, so every "
        "execution profile and device view remains provisional and ineligible "
        "pending a runtime smoke result."
    )


def _compose_compatibility_from_snapshot(
    snapshot: _OrdinaryLifecycleSnapshot,
    core_id: str,
    semantic_id: str,
    selected_run: str,
    reproduction_run: str,
    extra_caveats: list[str] | None = None,
) -> tuple[dict[str, Any], _OrdinaryLifecycleSnapshot]:
    """Compose compatibility from one shared, exact lifecycle snapshot."""

    source_set = snapshot.source_set
    semantic_pin = snapshot.semantic_pin
    catalog = snapshot.catalog
    selected_core, pin, _pin_file_sha256, selection = semantic_pin
    if selected_core != core_id or set(source_set.get("sources", {})) != {core_id}:
        raise PromoteCoreError(
            "compatibility core differs from its exact semantic pin"
        )
    source_reference = pin["sources"][0]
    golden_path = ROOT / source_reference["path"]
    golden, golden_file_sha256 = _load_with_sha256(golden_path)
    if (
        golden_file_sha256 != source_reference["file_sha256"]
        or golden.get("content_sha256") != source_reference["content_sha256"]
        or golden.get("pin_id") != semantic_id
        or golden.get("core_id") != core_id
    ):
        raise PromoteCoreError(
            "compatibility golden differs from its exact semantic pin"
        )
    build_goldens = golden.get("build_goldens", {}).get(core_id)
    if not isinstance(build_goldens, dict):
        raise PromoteCoreError(f"golden has no build_goldens for {core_id}")
    selected_targets = selection["targets"]
    expected_goldens = {
        architecture: target.get("golden_record")
        for architecture, target in selected_targets.items()
        if isinstance(target, dict)
    }
    if build_goldens != expected_goldens:
        raise PromoteCoreError(
            "compatibility golden records differ from their exact semantic pin"
        )
    for architecture, golden_record in build_goldens.items():
        if (
            not isinstance(golden_record, dict)
            or "source_candidate" in golden_record
            or "output_reproduction" in golden_record
        ):
            raise PromoteCoreError(
                "canonical compatibility composition refuses "
                "source-candidate/output-reproduction evidence for "
                f"{core_id}/{architecture}"
            )
    try:
        records_source.require_selected_source_identity(
            core_id,
            {
                architecture: {"golden_record": record}
                for architecture, record in build_goldens.items()
            },
            records_source.compose_source_lock(
                core_id,
                repository_root=ROOT,
                catalog=catalog,
            )["source"],
            label="compatibility golden",
        )
    except PipelineError as exc:
        raise PromoteCoreError(str(exc)) from exc
    source_commit = source_set["sources"][core_id]["commit"]

    selected_e2e = selection.get("e2e")
    selected_package = selection.get("package")
    if (
        not isinstance(selected_e2e, dict)
        or selected_e2e.get("run_id") != selected_run
        or not isinstance(selected_package, dict)
    ):
        raise PromoteCoreError(
            "selected compatibility run differs from its exact semantic pin"
        )

    selected_e2e_path = (
        ROOT / ".local-e2e" / "runs" / selected_run / "e2e-record.json"
    )
    reproduction_e2e_path = (
        ROOT
        / ".local-e2e"
        / "runs"
        / reproduction_run
        / "e2e-record.json"
    )
    snapshot = _OrdinaryLifecycleSnapshot(
        source_set=snapshot.source_set,
        semantic_pin=snapshot.semantic_pin,
        catalog=snapshot.catalog,
        evidence_files=snapshot.evidence_files
        + (
            (
                selected_e2e_path,
                _exact_file_digest(
                    selected_e2e_path, "selected compatibility E2E"
                ),
                "selected compatibility E2E",
            ),
            (
                reproduction_e2e_path,
                _exact_file_digest(
                    reproduction_e2e_path,
                    "reproduction compatibility E2E",
                ),
                "reproduction compatibility E2E",
            ),
        ),
    )
    pipeline = _validation_pipeline()
    try:
        selected = pipeline._validate_compatibility_e2e_run(
            selected_e2e_path,
            core_id,
            selected_targets,
        )
        reproduction = pipeline._validate_compatibility_e2e_run(
            reproduction_e2e_path,
            core_id,
            selected_targets,
        )
    except PipelineError as exc:
        raise PromoteCoreError(
            f"compatibility E2E evidence is invalid: {exc}"
        ) from exc
    if (
        selected.get("content_sha256") != selected_e2e.get("content_sha256")
        or selected.get("package_sha256") != selected_e2e.get("package_sha256")
        or selected.get("package_sha256") != selected_package.get("sha256")
    ):
        raise PromoteCoreError(
            "selected compatibility evidence differs from its exact semantic pin"
        )
    package_sha = selected["package_sha256"]
    reproducible = reproduction.get("package_sha256") == package_sha

    targets: dict[str, Any] = {}
    for arch in ("arm64", "armhf"):
        target = build_goldens.get(arch)
        if not isinstance(target, dict):
            continue
        artifact = target["artifact"]
        targets[arch] = {
            "state": "local_static_build_golden",
            "validation_scope": "static-build-only",
            "runtime_validation": "needs-target-runtime",
            "artifact_sha256": artifact["sha256"],
            "elf": ELF_LABEL[arch],
            "needed": artifact["needed"],
            "version_requirements": artifact["version_requirements"],
        }

    caveats = [
        (
            "The publication-disabled simulated-Actions build-core run and the "
            "independent native-local build-core run "
            + ("reproduced" if reproducible else "did not reproduce")
            + f" the exact {core_id}_libretro.zip package bytes. The selected and "
            "reproduction build logs remain separate content-addressed execution "
            "evidence; each must independently satisfy the applicable build and "
            "core-owned log contracts, and transcript byte equality is not "
            "required. Execution "
            "was local; both builds cloned the pinned source over the network, so "
            "no offline source cache is proven."
        ),
        _device_caveat(targets),
        (
            "Content, BIOS/firmware handling, controls, audio/video pacing, saves "
            "and state round trips, reset and unload behavior, frontend "
            "integration, compatibility, licensing review, and sustained "
            "performance remain target-runtime and human gates. Publication "
            "remains disabled regardless of local byte reproducibility."
        ),
    ]
    caveats.extend(extra_caveats or [])

    document = {
        "$schema": "../core-compatibility.schema.json",
        "schema_version": 1,
        "core_id": core_id,
        "publication": "disabled",
        "evidence_availability": "workspace-local-ignored",
        "golden_source": f"pins/core-sets/{semantic_id}.json",
        "source_commit": source_commit,
        "e2e_run": f".local-e2e/runs/{selected_run}/e2e-record.json",
        "selected_e2e_content_sha256": selected["content_sha256"],
        "reproduction_run": f".local-e2e/runs/{reproduction_run}/e2e-record.json",
        "reproduction_e2e_content_sha256": reproduction["content_sha256"],
        "package_state": "reproducible" if reproducible else "not-reproducible",
        "package_sha256": package_sha,
        "caveats": caveats,
        "targets": targets,
    }
    document["content_sha256"] = content_sha256(document)
    report = pipeline.validate_core_compatibility_document(
        document,
        repository_root=ROOT,
        verify_pin=True,
    )
    if report.get("status") != "valid":
        raise PromoteCoreError(
            "composed compatibility failed deep validation:\n- "
            + "\n- ".join(report.get("errors", []))
        )
    _require_lifecycle_snapshot_unchanged(snapshot)
    return document, snapshot


def compose_compatibility(
    core_id: str,
    semantic_id: str,
    selected_run: str,
    reproduction_run: str,
    extra_caveats: list[str] | None = None,
) -> dict[str, Any]:
    """Compose compatibility from one exact ordinary pin and its evidence."""

    snapshot = _ordinary_source_set_snapshot(
        semantic_id,
        operation="canonical compatibility composition",
    )
    document, snapshot = _compose_compatibility_from_snapshot(
        snapshot,
        core_id,
        semantic_id,
        selected_run,
        reproduction_run,
        extra_caveats,
    )
    _require_lifecycle_snapshot_unchanged(snapshot)
    return document


def _write_create_only(path: Path, document: dict[str, Any]) -> None:
    if path.exists():
        raise PromoteCoreError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _pipeline(*args: str) -> str:
    """Run one core_pipeline.py subcommand, failing loudly with its output."""

    command = [sys.executable, str(ROOT / "scripts" / "core_pipeline.py"), *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise PipelineCommandError(
            f"`{' '.join(args)}` failed:\n{result.stdout}\n{result.stderr}",
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return result.stdout


def _decode_pipeline_json(output: str, args: tuple[str, ...]) -> dict[str, Any]:
    """Require one strict UTF-8 JSON object from captured command output."""

    try:
        return decode_json_object(
            output.encode("utf-8"), f"core_pipeline.py {' '.join(args)} output"
        )
    except (PipelineError, UnicodeEncodeError) as exc:
        raise PromoteCoreError(
            f"`{' '.join(args)}` did not return a UTF-8 JSON object"
        ) from exc


def _pipeline_json(*args: str) -> dict[str, Any]:
    """Run one pipeline command and require one strict JSON object result."""

    return _decode_pipeline_json(_pipeline(*args), args)


def _pipeline_report(*args: str) -> dict[str, Any]:
    """Parse a structured report even when its command reports invalid state."""

    try:
        output = _pipeline(*args)
    except PipelineCommandError as exc:
        output = exc.stdout
    return _decode_pipeline_json(output, args)


def _pointer_snapshot(pointer: Path) -> tuple[bytes, dict[str, Any], str] | None:
    """Capture, parse, and hash an existing pointer from the same bytes."""

    try:
        raw = pointer.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PromoteCoreError(f"cannot read channel pointer {pointer}: {exc}") from exc
    if pointer.is_symlink() or not pointer.is_file():
        raise PromoteCoreError(f"channel pointer is not a regular file: {pointer}")
    try:
        document = decode_json_object(raw, pointer)
    except PipelineError as exc:
        raise PromoteCoreError(f"invalid channel pointer {pointer}: {exc}") from exc
    return raw, document, hashlib.sha256(raw).hexdigest()


def _remove_exact_pointer(pointer: Path, raw: bytes, digest: str) -> None:
    """Remove only the exact stale pointer rejected by the pipeline CAS."""

    with manifest_lock(pointer, ROOT):
        snapshot = _pointer_snapshot(pointer)
        if snapshot is None or snapshot[0] != raw or snapshot[2] != digest:
            raise PromoteCoreError(
                f"channel pointer changed after compare-and-swap failure: {pointer}"
            )
        try:
            pointer.unlink()
        except OSError as exc:
            raise PromoteCoreError(
                f"cannot remove stale channel pointer {pointer}: {exc}"
            ) from exc


def _require_pointer_result(
    result: dict[str, Any],
    *,
    channel: str,
    core: str,
    semantic_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return the digest and target bound by an update-channel result."""

    digest = result.get("pointer_file_sha256")
    target = result.get("target")
    if (
        result.get("status") not in {"created", "updated", "unchanged"}
        or result.get("channel") != channel
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or not isinstance(target, dict)
        or target.get("id") != semantic_id
    ):
        raise PromoteCoreError(
            f"update-channel returned an invalid {channel}.{core} pointer result"
        )
    return digest, target


def _write_evidence_index(core: str) -> None:
    """Regenerate the tracked evidence index from the promoted disk state."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "evidence_index", ROOT / "scripts" / "evidence_index.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = module.write(core)
    print(f"evidence index: {path.relative_to(ROOT)}")


def finish_promotion(core: str, semantic_id: str) -> None:
    """Materialize the release and repoint the three channels for a promotion.

    Goldens and pin-sets embed created_at, so every re-promotion invalidates
    the previous release bytes and all three channel pointers; the repair is
    mandatory follow-up work, so the promote chain finishes it. The
    compare-and-swap path is tried first; a pointer whose current target no
    longer deep-validates (stale or dangling after a refresh) is removed only
    if its exact rejected bytes are still current, then re-created with
    --expect-absent.
    """

    pin = f"pins/core-sets/{semantic_id}.json"
    release = f".local-e2e/releases/{semantic_id}"
    if not (ROOT / release).exists():
        _pipeline("promote-release", "--pin-set", pin, "--output", release)
    _pipeline("validate-release", "--pin-set", pin, "--release", release)
    print(f"release materialized: {release}")
    channel_targets = {
        "nightly": f".local-e2e/nightlies/{semantic_id}/golden.json",
        "pinned": pin,
        "release": f"{release}/release-manifest.json",
    }
    for channel, target in channel_targets.items():
        pointer = ROOT / ".local-e2e" / "channels" / f"{channel}.{core}.json"
        snapshot = _pointer_snapshot(pointer)
        if snapshot is None:
            update_result = _pipeline_json(
                "update-channel", "--channel", channel, "--core", core,
                "--target", target, "--expect-absent",
            )
        else:
            raw, _current, digest = snapshot
            current_proven_invalid = False
            try:
                current_report = _pipeline_report(
                    "validate-channel", "--channel", channel, "--core", core
                )
            except PromoteCoreError:
                # An unavailable/unstructured validation result is not proof
                # that a current pointer may be discarded.
                current_report = None
            if isinstance(current_report, dict):
                report_matches_snapshot = (
                    current_report.get("channel") == channel
                    and current_report.get("core_id") == core
                    and current_report.get("pointer_file_sha256") == digest
                )
                current_proven_invalid = (
                    report_matches_snapshot
                    and current_report.get("status") == "invalid"
                )
            try:
                # Even an apparently current semantic ID goes through the
                # pipeline's byte-exact compare-and-swap and deep validation.
                update_result = _pipeline_json(
                    "update-channel", "--channel", channel, "--core", core,
                    "--target", target, "--expect-current", digest,
                )
            except PromoteCoreError:
                if not current_proven_invalid:
                    raise
                _remove_exact_pointer(pointer, raw, digest)
                update_result = _pipeline_json(
                    "update-channel", "--channel", channel, "--core", core,
                    "--target", target, "--expect-absent",
                )
        accepted_digest, accepted_target = _require_pointer_result(
            update_result,
            channel=channel,
            core=core,
            semantic_id=semantic_id,
        )
        validation = _pipeline_json(
            "validate-channel", "--channel", channel, "--core", core
        )
        if (
            validation.get("status") != "valid"
            or validation.get("channel") != channel
            or validation.get("core_id") != core
            or validation.get("pointer_file_sha256") != accepted_digest
        ):
            raise PromoteCoreError(
                f"validated {channel}.{core} pointer does not match the "
                "update-channel result"
            )
        final_snapshot = _pointer_snapshot(pointer)
        if (
            final_snapshot is None
            or final_snapshot[2] != accepted_digest
            or final_snapshot[1].get("channel") != channel
            or final_snapshot[1].get("core_id") != core
            or final_snapshot[1].get("target") != accepted_target
        ):
            raise PromoteCoreError(
                f"channel pointer changed after validation: {pointer}"
            )
        print(f"channel {channel} -> {semantic_id}")


def _worktree_is_clean() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0 and not result.stdout.strip()


def current_extra_caveats(core: str) -> list[str]:
    """The promoted document's caveats past the standard trio, for carry-over."""

    path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    if not path.exists():
        return []
    return list(_load(path).get("caveats", [])[3:])


def run_wave(
    cores: list[str],
    label: str,
    refresh: bool,
    carry_caveats: bool,
    finish: bool,
) -> None:
    """Two-phase multi-core rebuild + re-promote.

    Build records snapshot repository_head/repository_dirty, and promotion
    dirties tracked pins — so a wave must build EVERY core first (builds
    write only ignored .local-e2e paths) and only then promote. Interleaving
    the phases stamps repository_dirty=true into every post-first-promote
    record; this command exists so that sequencing mistake cannot recur.
    """

    if not _worktree_is_clean():
        raise PromoteCoreError(
            "wave requires a clean committed tree: build records snapshot "
            "repository_dirty, and every build must complete before any "
            "promote dirties tracked pins"
        )
    runs = {
        core: (
            f"actions-sim-build-core-{core}-{label}",
            f"build-core-{core}-local-{label}",
        )
        for core in cores
    }
    for index, core in enumerate(cores, 1):
        for profile, run_id in zip(("github-actions-sim", "local"), runs[core]):
            if (ROOT / ".local-e2e" / "runs" / run_id).exists():
                continue
            _pipeline("build-core", "--runner-profile", profile,
                      "--core", core, "--run-id", run_id)
        print(f"[{index}/{len(cores)}] {core}: built")
    for index, core in enumerate(cores, 1):
        caveats = current_extra_caveats(core) if carry_caveats else []
        selected, reproduction = runs[core]
        semantic_id = run_promotion(
            core, selected, reproduction, caveats, refresh
        )
        if finish:
            finish_promotion(core, semantic_id)
        _write_evidence_index(core)
        print(f"[{index}/{len(cores)}] {core}: promoted {semantic_id}")


def run_promotion(
    core: str,
    selected_run: str,
    reproduction_run: str,
    caveats: list[str],
    refresh: bool,
) -> str:
    """Sequence the whole promote chain; returns the semantic id.

    Each step is the existing reviewed CLI subcommand, invoked exactly as the
    documented manual ritual did -- this adds orchestration, not new policy.
    """

    catalog = _load(ROOT / "manifests" / "core-builds.json")
    spec = catalog.get("cores", {}).get(core)
    if spec is None:
        raise PromoteCoreError(f"core is not in the catalog: {core}")
    targets = spec.get("targets", [])
    if not targets:
        raise PromoteCoreError(f"core has no targets: {core}")
    for run_id in (selected_run, reproduction_run):
        for arch in targets:
            record = ROOT / ".local-e2e" / "runs" / run_id / core / arch / "build-record.json"
            if not record.is_file():
                raise PromoteCoreError(f"missing build record: {record}")

    compatibility_path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    retired: list[tuple[Path, Path]] = []
    if compatibility_path.exists():
        if not refresh:
            raise PromoteCoreError(
                f"{core} is already promoted; pass --refresh to re-promote "
                "(retires the previous source-set/pin-set/compatibility first)"
            )
        # Move the previous promotion's derived artifacts ASIDE rather than
        # deleting them: a failed refresh must never destroy outputs (learned
        # the hard way -- a retire-then-fail sequence deleted 27 cores' files
        # during the v2 re-promote wave). They are restored on any failure and
        # removed only after the whole chain, catalog-check included, passes.
        previous = _load(compatibility_path)
        previous_pin = previous.get("golden_source", "")
        previous_sid = Path(previous_pin).stem if previous_pin else ""
        candidates = [compatibility_path]
        if previous_sid:
            candidates.append(ROOT / "pins" / "core-sets" / f"{previous_sid}.json")
        for stale in candidates:
            if stale.exists():
                aside = stale.with_name(stale.name + ".retiring")
                stale.rename(aside)
                retired.append((stale, aside))
                print(f"retiring {stale.relative_to(ROOT)}")

    try:
        return _run_promotion_chain(
            core, targets, selected_run, reproduction_run, caveats, retired
        )
    except BaseException:
        for original, aside in retired:
            if aside.exists() and not original.exists():
                aside.rename(original)
                print(f"restored {original.relative_to(ROOT)}")
        raise


def _run_promotion_chain(
    core: str,
    targets: list[str],
    selected_run: str,
    reproduction_run: str,
    caveats: list[str],
    retired: list[tuple[Path, Path]],
) -> str:
    compatibility_path = ROOT / "manifests" / "compatibility" / f"{core}.json"
    candidate_dir = ROOT / ".local-e2e" / "nightlies" / f"{core}-candidate-01"
    if candidate_dir.exists():
        shutil.rmtree(candidate_dir)
    candidate_dir.mkdir(parents=True)
    candidate = candidate_dir / "golden.json"

    _pipeline("import-golden", "--core", core, "--spruceos", "../spruceOS",
              "--output", str(candidate))
    for arch in targets:
        record = ROOT / ".local-e2e" / "runs" / selected_run / core / arch / "build-record.json"
        e2e = ROOT / ".local-e2e" / "runs" / selected_run / "e2e-record.json"
        _pipeline("promote", "--golden", str(candidate),
                  "--record", str(record), "--e2e-record", str(e2e))
        print(f"promoted {core}/{arch}")
    derived = json.loads(_pipeline(
        "derive-core-id", "--core", core, "--source-golden", str(candidate)
    ))
    semantic_id = derived["semantic_id"]
    print(f"semantic id: {semantic_id}")

    semantic_dir = ROOT / ".local-e2e" / "nightlies" / semantic_id
    semantic_dir.mkdir(parents=True, exist_ok=True)
    golden = semantic_dir / "golden.json"
    if golden.exists():
        golden.unlink()
    _pipeline("compose-core-golden", "--core", core,
              "--source-golden", str(candidate), "--output", str(golden))
    _pipeline("validate-golden", "--golden", str(golden), "--verify-store")
    print("golden valid")
    pin_path = ROOT / "pins" / "core-sets" / f"{semantic_id}.json"
    _pipeline("compose-pin-set", "--pin-id", semantic_id, "--core", core,
              "--source-golden", str(golden), "--output", str(pin_path))
    _pipeline("validate-pin-set", "--pin-set", str(pin_path),
              "--verify-store", "--verify-sources")
    print("pin-set valid")

    lifecycle_snapshot = _ordinary_source_set_snapshot(
        semantic_id,
        operation="canonical compatibility composition",
    )
    compatibility, lifecycle_snapshot = _compose_compatibility_from_snapshot(
        lifecycle_snapshot,
        core,
        semantic_id,
        selected_run,
        reproduction_run,
        caveats,
    )
    _require_lifecycle_snapshot_unchanged(lifecycle_snapshot)
    _write_create_only(compatibility_path, compatibility)
    print(f"wrote manifests/compatibility/{core}.json")
    _pipeline("catalog-check")
    print("catalog valid")
    for original, aside in retired:
        aside.unlink(missing_ok=True)
    return semantic_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    lock = subparsers.add_parser(
        "compose-source-lock",
        help="create the catalog-derived source lock for a core",
    )
    lock.add_argument("--core", required=True)
    lock.add_argument(
        "--print", action="store_true", help="print the lock instead of writing it"
    )
    compose = subparsers.add_parser(
        "compose-lifecycle",
        help="create the source-set and compatibility manifest for a promoted core",
    )
    compose.add_argument("--core", required=True)
    compose.add_argument("--semantic-id", required=True)
    compose.add_argument("--selected-run", required=True)
    compose.add_argument("--reproduction-run", required=True)
    compose.add_argument(
        "--caveat", action="append", default=[], help="extra core-specific caveat (repeatable)"
    )
    compose.add_argument(
        "--print", action="store_true", help="print the documents instead of writing them"
    )
    runner = subparsers.add_parser(
        "run",
        help="sequence the whole promote chain for a built core "
             "(import-golden through compose-lifecycle plus catalog-check)",
    )
    runner.add_argument("--core", required=True)
    runner.add_argument("--selected-run", required=True)
    runner.add_argument("--reproduction-run", required=True)
    runner.add_argument(
        "--caveat", action="append", default=[], help="extra core-specific caveat (repeatable)"
    )
    runner.add_argument(
        "--refresh", action="store_true",
        help="re-promote an already-promoted core, retiring its previous "
             "source-set, pin-set, and compatibility manifest first",
    )
    runner.add_argument(
        "--carry-caveats", action="store_true",
        help="carry the promoted document's extra caveats (past the standard "
             "trio) into the refresh instead of passing each --caveat",
    )
    runner.add_argument(
        "--no-finish", action="store_true",
        help="skip the release materialization and channel repoint that "
             "normally complete the promotion",
    )
    wave = subparsers.add_parser(
        "wave",
        help="two-phase multi-core rebuild + re-promote: build every core "
             "on the clean tree first, then promote every core",
    )
    wave.add_argument("--core", action="append", required=True)
    wave.add_argument(
        "--label", required=True,
        help="run-id suffix; runs are actions-sim-build-core-<core>-<label> "
             "and build-core-<core>-local-<label>",
    )
    wave.add_argument("--refresh", action="store_true")
    wave.add_argument("--carry-caveats", action="store_true")
    wave.add_argument("--no-finish", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "compose-source-lock":
            print(json.dumps(compose_source_lock(args.core), indent=2))
            return 0
        if args.command == "run":
            caveats = args.caveat
            if args.carry_caveats:
                if caveats:
                    raise PromoteCoreError(
                        "pass either --carry-caveats or explicit --caveat "
                        "values, not both"
                    )
                caveats = current_extra_caveats(args.core)
            semantic_id = run_promotion(
                args.core, args.selected_run, args.reproduction_run,
                caveats, args.refresh,
            )
            if not args.no_finish:
                finish_promotion(args.core, semantic_id)
            _write_evidence_index(args.core)
            print(f"promotion complete: {semantic_id}")
            return 0
        if args.command == "wave":
            run_wave(
                args.core, args.label, args.refresh,
                args.carry_caveats, not args.no_finish,
            )
            print(f"wave complete: {len(args.core)} cores")
            return 0
        if args.command == "compose-lifecycle":
            lifecycle_snapshot = _ordinary_source_set_snapshot(
                args.semantic_id,
                operation="canonical lifecycle composition",
            )
            compatibility, lifecycle_snapshot = (
                _compose_compatibility_from_snapshot(
                    lifecycle_snapshot,
                    args.core,
                    args.semantic_id,
                    args.selected_run,
                    args.reproduction_run,
                    args.caveat,
                )
            )
            source_set = lifecycle_snapshot.source_set
            _require_lifecycle_snapshot_unchanged(lifecycle_snapshot)
            if args.print:
                print(json.dumps({"source_set": source_set, "compatibility": compatibility}, indent=2))
                return 0
            _write_create_only(
                ROOT / "manifests" / "compatibility" / f"{args.core}.json", compatibility
            )
            print(f"wrote manifests/compatibility/{args.core}.json")
            return 0
    except PromoteCoreError as exc:
        print(f"promote-core error: {exc}", file=sys.stderr)
        return 1
    build_parser().error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
