#!/usr/bin/env python3
"""Render the device x core compatibility matrix from captured evidence.

Reads the same model as ``device_sets.py`` (canonical compatibility manifests
joined against the device runtime contracts' captured library observations and
GLIBCXX ceilings) and renders it as a Markdown table, refreshing the block
between the markers in ``README.md``:

    <!-- device-matrix:start --> ... <!-- device-matrix:end -->

Legend (each cell is a static provider-screen verdict, never a runtime guess):

  Y   eligible -- every DT_NEEDED library observed present, ceiling cleared
  C   over the device's captured GLIBCXX ceiling
  X   missing provider -- a needed library observed absent on the device
  ?   provider evidence uncaptured (device not probed, or library unobserved)
  -   no build for this device's ABI
  excl excluded by an explicit selection policy

Usage:
    python3 scripts/device_matrix.py            # print the Markdown table
    python3 scripts/device_matrix.py --write    # refresh the README block
"""

from __future__ import annotations

import argparse
import json
import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "device_sets", ROOT / "scripts" / "device_sets.py"
)
assert _spec is not None and _spec.loader is not None
device_sets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(device_sets)
_runtime_spec = importlib.util.spec_from_file_location(
    "device_runtime_evidence", ROOT / "scripts" / "device_runtime_evidence.py"
)
assert _runtime_spec is not None and _runtime_spec.loader is not None
device_runtime_evidence = importlib.util.module_from_spec(_runtime_spec)
_runtime_spec.loader.exec_module(device_runtime_evidence)

# The catalog is the authority on how many cores exist; a literal here silently
# rejects a valid projection the moment a core is added (it did, at 98).
CATALOG_CORE_COUNT = len(
    json.loads((ROOT / "manifests/core-builds.json").read_text())["cores"]
)
# Cores cataloged with pending compatibility (awaiting-local-e2e): no promoted
# evidence and no runtime projection rows. Both matrices carry them as rows so
# the catalog is fully accounted for; every cell reads as no-build/uncaptured.
PENDING_CORE_IDS = sorted(
    path.stem
    for path in (ROOT / "manifests/compatibility/pending").glob("*.json")
)

MARK_START = "<!-- device-matrix:start -->"
MARK_END = "<!-- device-matrix:end -->"

# Column order: probed devices first (arm64 then armhf), unprobed last.
DEVICE_COLUMNS = [
    ("device-trimui-a133p-family-v0", "Brick / TSP"),
    ("device-trimui-smart-pro-s-v0", "TSPS"),
    ("device-miyoo-flip-v0", "Flip"),
    ("device-gkd-pixel2-v0", "Pixel 2"),
    ("device-miyoo-a30-v0", "A30"),
    ("device-miyoo-mini-family-v0", "Mini +"),
    ("device-anbernic-h700-family-v0", "H700*"),
    ("device-magicx-zero28-v0", "Zero28*"),
]

RUNTIME_DEVICE_COLUMNS = [
    ("TRIMUI_BRICK", "Brick"),
    ("TRIMUI_SMART_PRO", "TSP"),
    ("TRIMUI_BRICK_PRO", "Brick Pro"),
    ("TRIMUI_SMART_PRO_S", "TSPS"),
    ("MIYOO_FLIP", "Flip"),
    ("GKD_PIXEL2", "Pixel 2"),
    ("MIYOO_A30", "A30"),
    ("MIYOO_MINI", "Mini"),
    ("MIYOO_MINI_V4", "Mini V4"),
    ("MIYOO_MINI_PLUS", "Mini+"),
    ("MIYOO_MINI_FLIP", "Mini Flip"),
    ("ANBERNIC_RG28XX", "RG28XX"),
    ("ANBERNIC_RG34XXSP", "RG34XXSP"),
    ("ANBERNIC_RGCUBEXX", "RGCubeXX"),
    ("ANBERNIC_RGXX640480", "RGXX 640×480"),
    ("MAGICX_ZERO28", "Zero28"),
]

RUNTIME_SYMBOL = {
    "PASS": "P",
    "FAIL": "F",
    "UNKNOWN": "?",
    "NO_BUILD": "-",
}
RUNTIME_PROJECTION_KEYS = {
    "schema_version",
    "projection_id",
    "validation_scope",
    "local_only",
    "publication",
    "core_order",
    "device_order",
    "status_counts",
    "capture",
    "current_sources",
    "devices",
    "families",
    "runtime_context_provenance",
    "content_sha256",
}
RUNTIME_DEVICE_KEYS = {
    "device_id",
    "runtime_contract_id",
    "runtime_family_id",
    "execution_profile_id",
    "architecture",
    "support_status",
    "release_default",
    "frontend_availability",
    "frontend_path",
    "frontend_sha256",
    "capture_status",
    "recorded_retroarch_binary",
    "execution_context_matches",
    "results",
}
RUNTIME_RESULT_KEYS = {
    "core_id",
    "architecture",
    "artifact",
    "load_result",
    "reason",
    "evidence_capture_id",
    "policy",
}

BUCKET_SYMBOL = {
    "eligible": "Y",
    "eligible_ceiling_uncaptured": "?",
    "over_ceiling": "C",
    "missing_provider": "X",
    "provider_uncaptured": "?",
    "policy_excluded": "excl",
    "no_arch_target": "-",
}

REPORT_KEYS = {
    "schema_version",
    "local_only",
    "publication",
    "screen",
    "note",
    "core_count",
    "devices",
}
REPORT_NOTE = (
    "necessary-not-sufficient: static cells remain provisional until a "
    "separate exact artifact and physical-device evidence join"
)
VIEW_META_KEYS = {
    "family",
    "device_ids",
    "architecture",
    "execution_profile",
    "provider_glibcxx_ceiling",
    "library_capture",
    "frontend_available",
    "counts",
}
ROW_REQUIRED_KEYS = {
    "eligible": {"core"},
    "eligible_ceiling_uncaptured": {"core", "glibcxx"},
    "over_ceiling": {"core", "glibcxx"},
    "missing_provider": {"core", "missing_providers"},
    "provider_uncaptured": {"core", "unverified_providers"},
    "policy_excluded": {"core", "reason"},
    "no_arch_target": {"core"},
}
ROW_OPTIONAL_KEYS = {
    "eligible": {"glibcxx", "constraint"},
    "eligible_ceiling_uncaptured": {"constraint"},
    "over_ceiling": {"constraint"},
    "missing_provider": {"glibcxx", "constraint"},
    "provider_uncaptured": {"glibcxx", "constraint"},
    "policy_excluded": set(),
    "no_arch_target": {"constraint"},
}


class DeviceMatrixError(Exception):
    """Raised when the source report is not one exact core/device partition."""


def _string(value: object, *, field: str, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value:
        raise DeviceMatrixError(f"{field} is invalid")


def _string_list(value: object, *, field: str, allow_empty: bool = False) -> None:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise DeviceMatrixError(f"{field} is invalid")


def _validate_row(row: object, *, contract_id: str, bucket: str) -> str:
    if not isinstance(row, dict):
        raise DeviceMatrixError(f"{contract_id} {bucket} contains an invalid row")
    required = ROW_REQUIRED_KEYS[bucket]
    allowed = required | ROW_OPTIONAL_KEYS[bucket]
    if not required <= set(row) or not set(row) <= allowed:
        raise DeviceMatrixError(f"{contract_id} {bucket} row shape is invalid")
    _string(row["core"], field=f"{contract_id} {bucket}.core")
    for field in ("glibcxx", "constraint", "reason"):
        if field in row:
            _string(row[field], field=f"{contract_id} {bucket}.{field}")
    for field in ("missing_providers", "unverified_providers"):
        if field in row:
            _string_list(row[field], field=f"{contract_id} {bucket}.{field}")
    return row["core"]


def _validate_view_metadata(contract_id: str, view: dict[str, Any]) -> None:
    if set(view) != VIEW_META_KEYS | set(BUCKET_SYMBOL):
        raise DeviceMatrixError(f"{contract_id} device view shape is invalid")
    _string(view["family"], field=f"{contract_id} family")
    _string_list(view["device_ids"], field=f"{contract_id} device_ids")
    if view["architecture"] not in {"arm64", "armhf"}:
        raise DeviceMatrixError(f"{contract_id} architecture is invalid")
    _string(view["execution_profile"], field=f"{contract_id} execution_profile")
    _string(
        view["provider_glibcxx_ceiling"],
        field=f"{contract_id} provider_glibcxx_ceiling",
        nullable=True,
    )
    _string(
        view["library_capture"],
        field=f"{contract_id} library_capture",
        nullable=True,
    )
    if not isinstance(view["frontend_available"], bool):
        raise DeviceMatrixError(f"{contract_id} frontend_available is invalid")


def build_matrix() -> tuple[list[str], dict[str, dict[str, str]]]:
    source = device_sets.build_report()
    if not isinstance(source, dict) or set(source) != REPORT_KEYS:
        raise DeviceMatrixError("device-set report envelope is invalid")
    if (
        not isinstance(source["schema_version"], int)
        or isinstance(source["schema_version"], bool)
        or source["schema_version"] != 1
        or source["local_only"] is not True
        or source["publication"] != "disabled"
        or source["screen"] != "static-abi-only"
        or source["note"] != REPORT_NOTE
    ):
        raise DeviceMatrixError("device-set report semantics are unsupported")
    report = source.get("devices")
    if not isinstance(report, dict):
        raise DeviceMatrixError("device-set report has no devices object")
    expected_devices = {contract_id for contract_id, _label in DEVICE_COLUMNS}
    if set(report) != expected_devices:
        raise DeviceMatrixError(
            "device-set report does not cover the matrix devices exactly"
        )
    core_count = source.get("core_count")
    if (
        not isinstance(core_count, int)
        or isinstance(core_count, bool)
        or core_count < 1
    ):
        raise DeviceMatrixError("device-set report core_count is invalid")

    canonical_cores: set[str] | None = None
    cells: dict[str, dict[str, str]] = {}
    for contract_id, _label in DEVICE_COLUMNS:
        view = report[contract_id]
        if not isinstance(view, dict):
            raise DeviceMatrixError(f"{contract_id} device view is invalid")
        _validate_view_metadata(contract_id, view)
        counts = view.get("counts")
        if not isinstance(counts, dict) or set(counts) != set(BUCKET_SYMBOL):
            raise DeviceMatrixError(
                f"{contract_id} bucket set does not match the renderer"
            )
        if any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in counts.values()
        ):
            raise DeviceMatrixError(f"{contract_id} bucket counts are invalid")
        device_cores: set[str] = set()
        for bucket, symbol in BUCKET_SYMBOL.items():
            rows = view.get(bucket)
            if not isinstance(rows, list) or counts[bucket] != len(rows):
                raise DeviceMatrixError(f"{contract_id} {bucket} count is invalid")
            row_cores: list[str] = []
            for row in rows:
                core = _validate_row(
                    row, contract_id=contract_id, bucket=bucket
                )
                if core in device_cores:
                    raise DeviceMatrixError(
                        f"{contract_id} classifies {core} more than once"
                    )
                device_cores.add(core)
                row_cores.append(core)
                cells.setdefault(core, {})[contract_id] = symbol
            if row_cores != sorted(row_cores):
                raise DeviceMatrixError(
                    f"{contract_id} {bucket} rows are not deterministic"
                )
        if len(device_cores) != core_count:
            raise DeviceMatrixError(
                f"{contract_id} does not classify exactly {core_count} cores"
            )
        if canonical_cores is None:
            canonical_cores = device_cores
        elif device_cores != canonical_cores:
            raise DeviceMatrixError(
                "device views do not classify the same core roster"
            )

    assert canonical_cores is not None
    for core in canonical_cores:
        if set(cells[core]) != expected_devices:
            raise DeviceMatrixError(f"matrix row for {core} is incomplete")
    for core_id in PENDING_CORE_IDS:
        if core_id in cells:
            raise DeviceMatrixError(
                f"pending core {core_id} already has a static verdict"
            )
        cells[core_id] = {
            contract_id: BUCKET_SYMBOL["provider_uncaptured"]
            for contract_id, _label in DEVICE_COLUMNS
        }
        canonical_cores.add(core_id)
    return sorted(canonical_cores), cells


def _sha256(value: object, *, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise DeviceMatrixError(f"{field} is not a canonical SHA-256")


def build_runtime_matrix() -> tuple[
    list[str], dict[str, dict[str, str]], dict[str, Any]
]:
    """Return an exact current-core by physical-device artifact matrix."""

    try:
        projection = device_runtime_evidence.project_current_physical_devices(
            repo_root=ROOT
        )
    except device_runtime_evidence.DeviceRuntimeEvidenceError as exc:
        raise DeviceMatrixError(f"runtime evidence is invalid: {exc}") from exc
    if not isinstance(projection, dict) or set(projection) != RUNTIME_PROJECTION_KEYS:
        raise DeviceMatrixError("runtime projection envelope is invalid")
    if (
        not isinstance(projection["schema_version"], int)
        or isinstance(projection["schema_version"], bool)
        or projection["schema_version"] != 1
        or projection["projection_id"]
        != "current-canonical-artifact-runtime-v1"
        or projection["validation_scope"]
        != "physical-device-artifact-load-only"
        or projection["local_only"] is not True
        or projection["publication"] != "disabled"
    ):
        raise DeviceMatrixError("runtime projection semantics are unsupported")

    core_order = projection["core_order"]
    if (
        not isinstance(core_order, list)
        or len(core_order) != CATALOG_CORE_COUNT - len(PENDING_CORE_IDS)
        or any(not isinstance(core, str) or not core for core in core_order)
        or core_order != sorted(core_order)
        or len(set(core_order)) != len(core_order)
    ):
        raise DeviceMatrixError("runtime projection core order is invalid")
    device_order = projection["device_order"]
    expected_devices = {device_id for device_id, _ in RUNTIME_DEVICE_COLUMNS}
    if (
        not isinstance(device_order, list)
        or device_order != sorted(device_order)
        or len(device_order) != len(expected_devices)
        or set(device_order) != expected_devices
    ):
        raise DeviceMatrixError("runtime projection device order is invalid")

    status_counts = projection["status_counts"]
    if (
        not isinstance(status_counts, dict)
        or set(status_counts) != set(RUNTIME_SYMBOL)
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in status_counts.values()
        )
        or sum(status_counts.values()) != len(core_order) * len(device_order)
    ):
        raise DeviceMatrixError("runtime projection status counts are invalid")

    capture = projection["capture"]
    if not isinstance(capture, dict) or set(capture) != {
        "path",
        "file_sha256",
        "capture_id",
        "content_sha256",
    }:
        raise DeviceMatrixError("runtime projection capture is invalid")
    if (
        capture["path"]
        != "manifests/device-runtime-captures/load-smoke-20260724-v2.json"
        or capture["capture_id"] != "load-smoke-20260724-v2"
    ):
        raise DeviceMatrixError("runtime projection capture is unsupported")
    _sha256(capture["file_sha256"], field="runtime capture file_sha256")
    _sha256(capture["content_sha256"], field="runtime capture content_sha256")
    _sha256(projection["content_sha256"], field="runtime projection content_sha256")
    if projection["content_sha256"] != device_runtime_evidence._document_content_sha256(
        projection
    ):
        raise DeviceMatrixError("runtime projection content hash is invalid")

    devices = projection["devices"]
    if (
        not isinstance(devices, list)
        or [row.get("device_id") if isinstance(row, dict) else None for row in devices]
        != device_order
    ):
        raise DeviceMatrixError("runtime projection devices are invalid")
    cells: dict[str, dict[str, str]] = {core: {} for core in core_order}
    observed_counts = {status: 0 for status in RUNTIME_SYMBOL}
    for device in devices:
        if set(device) != RUNTIME_DEVICE_KEYS:
            raise DeviceMatrixError("runtime projection device shape is invalid")
        device_id = device["device_id"]
        if device["architecture"] not in {"arm64", "armhf"}:
            raise DeviceMatrixError(f"{device_id} runtime architecture is invalid")
        results = device["results"]
        if (
            not isinstance(results, list)
            or [row.get("core_id") if isinstance(row, dict) else None for row in results]
            != core_order
        ):
            raise DeviceMatrixError(f"{device_id} runtime rows are incomplete")
        for row in results:
            if set(row) != RUNTIME_RESULT_KEYS:
                raise DeviceMatrixError(f"{device_id} runtime row shape is invalid")
            core_id = row["core_id"]
            status = row["load_result"]
            if status not in RUNTIME_SYMBOL or row["architecture"] != device[
                "architecture"
            ]:
                raise DeviceMatrixError(f"{device_id}/{core_id} status is invalid")
            _string(row["reason"], field=f"{device_id}/{core_id} reason")
            artifact = row["artifact"]
            if status == "NO_BUILD":
                if artifact is not None or row["evidence_capture_id"] is not None:
                    raise DeviceMatrixError(
                        f"{device_id}/{core_id} no-build evidence is invalid"
                    )
            else:
                if not isinstance(artifact, dict) or set(artifact) != {
                    "sha256",
                    "size",
                    "authority",
                }:
                    raise DeviceMatrixError(
                        f"{device_id}/{core_id} artifact is invalid"
                    )
                _sha256(
                    artifact["sha256"], field=f"{device_id}/{core_id} artifact"
                )
                if (
                    not isinstance(artifact["size"], int)
                    or isinstance(artifact["size"], bool)
                    or artifact["size"] < 1
                    or not isinstance(artifact["authority"], dict)
                ):
                    raise DeviceMatrixError(
                        f"{device_id}/{core_id} artifact authority is invalid"
                    )
                if status in {"PASS", "FAIL"}:
                    if row["evidence_capture_id"] != capture["capture_id"]:
                        raise DeviceMatrixError(
                            f"{device_id}/{core_id} evidence binding is invalid"
                        )
                elif row["evidence_capture_id"] is not None:
                    raise DeviceMatrixError(
                        f"{device_id}/{core_id} unknown evidence is invalid"
                    )
            if not isinstance(row["policy"], dict) or set(row["policy"]) != {
                "status",
                "reason",
            }:
                raise DeviceMatrixError(f"{device_id}/{core_id} policy is invalid")
            cells[core_id][device_id] = RUNTIME_SYMBOL[status]
            observed_counts[status] += 1
    if observed_counts != status_counts:
        raise DeviceMatrixError("runtime projection count projection disagrees")
    if any(set(row) != expected_devices for row in cells.values()):
        raise DeviceMatrixError("runtime matrix contains an incomplete core row")
    for core_id in PENDING_CORE_IDS:
        if core_id in cells:
            raise DeviceMatrixError(
                f"pending core {core_id} already has runtime evidence"
            )
        cells[core_id] = {
            device_id: RUNTIME_SYMBOL["NO_BUILD"]
            for device_id in expected_devices
        }
    return sorted(set(core_order) | set(PENDING_CORE_IDS)), cells, projection


def replace_marked_block(text: str, block: str) -> str:
    """Return README text with its sole ordered matrix region replaced."""

    if text.count(MARK_START) != 1 or text.count(MARK_END) != 1:
        raise DeviceMatrixError("README must contain exactly one matrix marker pair")
    start = text.index(MARK_START)
    end = text.index(MARK_END)
    if end < start:
        raise DeviceMatrixError("README matrix markers are reversed")
    end += len(MARK_END)
    replacement = MARK_START + "\n" + block + "\n" + MARK_END
    return text[:start] + replacement + text[end:]


def extract_marked_block(text: str) -> str:
    """Return the sole matrix region, rejecting stale duplicate markers."""

    replace_marked_block(text, "")
    start = text.index(MARK_START) + len(MARK_START)
    end = text.index(MARK_END)
    region = text[start:end]
    if not region.startswith("\n") or not region.endswith("\n"):
        raise DeviceMatrixError("README matrix region must be newline-delimited")
    return region[1:-1]


def _write_atomic(path: Path, content: str) -> None:
    """Atomically replace one existing regular file while preserving its mode."""

    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise DeviceMatrixError(f"refusing to replace non-regular file: {path}")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(info.st_mode))
        os.replace(temporary, path)
        temporary = None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _group_runtime_results(
    projection: dict[str, Any], status: str, *, reason_filter: str | None = None
) -> list[str]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for device in projection["devices"]:
        for result in device["results"]:
            if result["load_result"] != status or (
                reason_filter is not None and result["reason"] != reason_filter
            ):
                continue
            key = (result["core_id"], result["reason"])
            grouped.setdefault(key, []).append(device["device_id"])
    return [
        f"`{core}` on {', '.join(f'`{device}`' for device in sorted(devices))}"
        f" (`{reason}`)"
        for (core, reason), devices in sorted(grouped.items())
    ]


def render_runtime_markdown() -> str:
    cores, cells, projection = build_runtime_matrix()
    counts = projection["status_counts"]
    unknown_reasons: dict[str, int] = {}
    for device in projection["devices"]:
        for result in device["results"]:
            if result["load_result"] == "UNKNOWN":
                reason = result["reason"]
                unknown_reasons[reason] = unknown_reasons.get(reason, 0) + 1
    failures = _group_runtime_results(projection, "FAIL")
    stale = _group_runtime_results(
        projection, "UNKNOWN", reason_filter="artifact-not-observed"
    )
    capture = projection["capture"]
    lines = [
        "",
        "Artifact-bound physical-device load evidence for the current canonical"
        " artifacts:",
        "`P` exact artifact passed `dlopen`/`libretro-init` - `F` exact artifact"
        " reproduced a load failure - `?` current artifact/device/profile evidence"
        " is missing or stale - `-` no artifact for the device ABI. This is a"
        " load-only result: it does not claim content boot, input, A/V pacing,"
        " saves, gameplay, or sustained performance. Candidate and track variants"
        " inherit a cell only when their artifact bytes are identical.",
        "",
        f"Current totals: **{counts['PASS']} P / {counts['FAIL']} F /"
        f" {counts['UNKNOWN']} ? / {counts['NO_BUILD']} -** across"
        f" {len(cores) - len(PENDING_CORE_IDS)} evidence-backed cores ×"
        f" {len(RUNTIME_DEVICE_COLUMNS)} physical devices;"
        f" {len(PENDING_CORE_IDS)} pending cores"
        f" ({', '.join(PENDING_CORE_IDS)}) render as `-` awaiting local e2e."
        f" Capture `{capture['capture_id']}` file `{capture['file_sha256']}`;"
        f" content `{capture['content_sha256']}`; current projection"
        f" `{projection['content_sha256']}`.",
        "",
        "Verified failures: " + ("; ".join(failures) if failures else "none") + ".",
        "Changed-artifact observations requiring a new device run: "
        + ("; ".join(stale) if stale else "none")
        + ".",
        "Unknown reasons: "
        + ", ".join(
            f"`{reason}` {count}" for reason, count in sorted(unknown_reasons.items())
        )
        + ".",
        "",
        "<details><summary>Runtime matrix: "
        f"{len(cores)} cores x {len(RUNTIME_DEVICE_COLUMNS)} physical devices"
        "</summary>",
        "",
        "| core | "
        + " | ".join(label for _device_id, label in RUNTIME_DEVICE_COLUMNS)
        + " |",
        "|---" * (len(RUNTIME_DEVICE_COLUMNS) + 1) + "|",
    ]
    for core in cores:
        row = [core]
        for device_id, _label in RUNTIME_DEVICE_COLUMNS:
            row.append(cells[core][device_id])
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "</details>"]
    return "\n".join(lines)


def render_markdown() -> str:
    cores, cells = build_matrix()
    lines = [
        "Evidence-backed static eligibility for every canonical core:",
        "`Y` eligible (all needed libraries observed present, ceiling cleared)"
        " - `C` over the captured GLIBCXX ceiling - `X` a needed library is"
        " absent - `?` provider"
        " evidence uncaptured (fails closed) - `-` no build for that ABI -"
        " `excl` explicit policy exclusion. `Y` is a necessary static screen,"
        " not an artifact-bound runtime pass. Devices marked `*` have not been"
        " probed. Generated by `scripts/device_matrix.py --write`; regenerate"
        " after onboarding or a new device capture.",
        "",
        "<details><summary>Matrix: "
        f"{len(cores)} cores x {len(DEVICE_COLUMNS)} device families"
        "</summary>",
        "",
        "| core | " + " | ".join(label for _, label in DEVICE_COLUMNS) + " |",
        "|---" * (len(DEVICE_COLUMNS) + 1) + "|",
    ]
    for core in cores:
        row = [core]
        for contract_id, _label in DEVICE_COLUMNS:
            row.append(cells[core][contract_id])
        lines.append("| " + " | ".join(row) + " |")
    lines += ["", "</details>"]
    return "\n".join(lines) + "\n" + render_runtime_markdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        block = render_markdown()
    except DeviceMatrixError as exc:
        print(f"device matrix error: {exc}", file=sys.stderr)
        return 1
    if not args.write:
        print(block)
        return 0
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    try:
        updated = replace_marked_block(text, block)
        _write_atomic(readme, updated)
    except (DeviceMatrixError, OSError) as exc:
        print(f"device matrix error: {exc}", file=sys.stderr)
        return 1
    print(f"README matrix refreshed ({block.count(chr(10))} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
