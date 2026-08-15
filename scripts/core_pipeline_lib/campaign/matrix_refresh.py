"""Pure projections for cell-changing campaign matrix refreshes.

The historical matrix generators mixed filesystem discovery, evidence
hydration, selection policy, projection, and publication in one executable.
This module owns only the deterministic projection boundary.  Callers must
hydrate and validate the maintained track inventory, track registry, pin, and
run evidence before entering these functions.  The functions below perform
no filesystem, process, clock, import-discovery, CAS, or publication work.

An admission projection deliberately preserves catalog, frozen-edge, and
branch-artifact observations from the authenticated predecessor cell.  Those
observations are not track-selection authority and rebuilding them during a
track transaction would silently widen the transition.  Every lifecycle,
selection, build, evidence, output, reuse, performance, lineage, and hash
field is instead reconstructed from the supplied maintained authorities.
"""

from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass
import datetime as dt
from pathlib import PurePosixPath
import re
from typing import Final, Mapping

from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..immutable_evidence import (
    host_reproduction_content_sha256,
    pin_set_content_sha256,
    selection_content_sha256,
)
from ..tracks import (
    canonical_group_tag,
    core_track_inventory_content_sha256,
    core_track_test_assignment_content_sha256,
    core_tracks_content_sha256,
)
from .legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
    render_matrix_v2,
)
from .matrix_materialize import (
    NormalizedMatrixV1,
    derive_legacy_summary,
    materialize_matrix_v2,
    matrix_object_reference,
    validate_normalized_matrix,
)
from .matrix_model import (
    EXCLUSION_PARTITION,
    EXPECTED_UNIVERSE_CELL_COUNT,
    LEGACY_MATRIX_FORMAT,
    PROJECTION_ORDER,
    SUPPORTED_PARTITION,
    TRACK_ORDER,
    UNIVERSE_CELLS_PER_CORE,
    LegacyMatrixV2Identity,
    MatrixCellV1,
    MatrixCoordinateV1,
    MatrixRootV1,
    MatrixShardV1,
)
from .model import EvidenceRef


_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_UTC_SECONDS_RE: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_SUPPORTED_CELL_KEYS: Final = frozenset(
    {
        "branch_artifact_observation",
        "build_identity",
        "content_sha256",
        "coordinate",
        "evidence",
        "lifecycle",
        "lineage",
        "outlier",
        "outputs",
        "performance",
        "resolution",
        "reuse",
        "version_slice",
    }
)
_DIMENSION_NAMES: Final = (
    "source",
    "recipe",
    "toolchain",
    "image",
    "tuning",
    "build",
)
_ROOT_PROJECTION_KEYS: Final = frozenset(
    {
        "$schema",
        "audit",
        "campaign_id",
        "captured_at",
        "directory_fingerprint_model",
        "expansion",
        "format",
        "hash_model",
        "inputs",
        "local_only",
        "marker",
        "publication",
        "schema_version",
        "supersedes",
        "tracks",
        "validation_ledger",
        "validation_scope",
    }
)
_ROOT_INPUT_KEYS: Final = frozenset(
    {
        "branch_bases",
        "catalog",
        "commit_blacklist",
        "edge_source_snapshot",
        "evidence_records",
        "generator",
        "host_execution_profiles",
        "host_telemetry_schema",
        "phase_freeze",
        "pin_directory",
        "pipeline_bundle",
        "release_roster",
        "schema",
        "toolchain_lock",
        "track_registry_snapshot_directory",
        "tracks",
        "tunings",
    }
)
_LEDGER_CHECK_IDS: Final = (
    "canonical-inputs-validated-once",
    "frozen-edge-snapshot-bound",
    "coordinate-partition-exact",
    "cell-order-and-uniqueness",
    "independent-lifecycle-axes-cross-validated",
    "host-reproduction-proof-required-for-test",
    "source-order-lineage-and-outliers-validated",
    "branch-artifacts-observational-only",
    "per-cell-and-root-semantic-hash-projections",
    "json-schema-draft-2020-12",
    "deterministic-double-render",
)
_ROOT_EVIDENCE_RECORD_KEYS: Final = frozenset(
    {
        "core_id",
        "pin",
        "golden",
        "selected_e2e",
        "reproduction_e2e",
        "selected_telemetry",
        "reproduction_telemetry",
        "host_reproduction_content_sha256",
    }
)
_ROOT_EVIDENCE_REFERENCE_KEYS: Final = frozenset(
    {"path", "file_sha256", "content_sha256"}
)
_ABSENT_CELL_EVIDENCE: Final = {
    "state": "absent-not-run",
    "selected": None,
    "reproduction": None,
    "host_reproduction": None,
    "golden": None,
}


def _require_mapping(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise PipelineError(f"{label} must be an exact string-keyed object")
    return value


def _require_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact array")
    return value


def _require_string(value: object, *, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PipelineError(f"{label} must be a nonempty stripped string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PipelineError(f"{label} must be valid UTF-8") from exc
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _require_identifier(value: object, *, label: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_timestamp(value: object, *, label: str) -> str:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be an exact UTC-second timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise PipelineError(f"{label} must be a real UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise PipelineError(f"{label} must be canonical")
    return value


def _require_relative_path(value: object, *, label: str) -> str:
    value = _require_string(value, label=label)
    if "\\" in value or "//" in value or "\x00" in value:
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return value


def _semantic(value: object) -> str:
    return sha256_bytes(matrix_v2_canonical_bytes(value))


def _deep(value: object) -> object:
    return copy.deepcopy(value)


def _store_path(kind: str, digest: str) -> str:
    _require_identifier(kind, label="store kind")
    digest = _require_sha256(digest, label=f"{kind} store digest")
    return f".local-e2e/store/{kind}/sha256/{digest[:2]}/{digest}"


def _line_count(raw: bytes) -> int:
    return raw.count(b"\n") + int(bool(raw) and not raw.endswith(b"\n"))


def _branch_basis_authority(
    value: object,
    *,
    label: str,
) -> dict[str, object]:
    """Return the exact maintained branch-authority projection."""

    basis = _require_mapping(value, label=label)
    return {
        "basis_id": _require_identifier(
            basis.get("basis_id"), label=f"{label} basis_id"
        ),
        "basis_content_sha256": _require_sha256(
            basis.get("basis_content_sha256"),
            label=f"{label} basis_content_sha256",
        ),
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class HydratedArtifactV1:
    """One already-hydrated repository-relative artifact and its exact bytes."""

    path: str
    raw: bytes

    def __post_init__(self) -> None:
        _require_relative_path(self.path, label="hydrated artifact path")
        if type(self.raw) is not bytes:
            raise PipelineError("hydrated artifact raw value must be exact bytes")

    @property
    def file_sha256(self) -> str:
        return sha256_bytes(self.raw)

    def document(self, *, label: str) -> dict[str, object]:
        try:
            return decode_matrix_v2(self.raw)
        except PipelineError as exc:
            raise PipelineError(f"{label} is not strict JSON: {exc}") from exc

    def file_projection(self) -> dict[str, object]:
        return {"path": self.path, "file_sha256": self.file_sha256}


@dataclass(frozen=True, slots=True, kw_only=True)
class TrackCellEvidenceV1:
    """Hydrated immutable evidence needed to project one admitted pin."""

    pin: HydratedArtifactV1
    golden: HydratedArtifactV1
    selected_e2e: HydratedArtifactV1
    reproduction_e2e: HydratedArtifactV1
    selected_telemetry: HydratedArtifactV1
    reproduction_telemetry: HydratedArtifactV1
    selected_build_record: HydratedArtifactV1
    reproduction_build_record: HydratedArtifactV1
    telemetry_schema: HydratedArtifactV1

    def __post_init__(self) -> None:
        for name in self.__slots__:
            if type(getattr(self, name)) is not HydratedArtifactV1:
                raise PipelineError(
                    f"track cell evidence {name} must be a HydratedArtifactV1"
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class DirectoryFingerprintV1:
    """Hydrated input set for the legacy recursive-JSON fingerprint model."""

    path: str
    files: tuple[HydratedArtifactV1, ...]

    def __post_init__(self) -> None:
        root = _require_relative_path(self.path, label="fingerprint directory path")
        if type(self.files) is not tuple or any(
            type(item) is not HydratedArtifactV1 for item in self.files
        ):
            raise PipelineError("fingerprint files must be an exact artifact tuple")
        prefix = root + "/"
        relative = []
        for item in self.files:
            if not item.path.startswith(prefix) or not item.path.endswith(".json"):
                raise PipelineError(
                    "fingerprint entries must be JSON files below the exact root"
                )
            relative.append(item.path.removeprefix(prefix))
        if relative != sorted(relative) or len(relative) != len(set(relative)):
            raise PipelineError("fingerprint entries must be sorted and unique")

    def to_document(self) -> dict[str, object]:
        prefix = self.path + "/"
        entries = [
            {
                "path": item.path.removeprefix(prefix),
                "file_sha256": item.file_sha256,
                "bytes": len(item.raw),
            }
            for item in self.files
        ]
        return {
            "path": self.path,
            "file_count": len(entries),
            "entries": entries,
            "content_sha256": _semantic(entries),
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineBundleIdentityV1:
    """The maintained identity projection of one validated source bundle."""

    schema_version: int
    file_count: int
    content_sha256: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version < 1:
            raise PipelineError("pipeline bundle schema_version is invalid")
        if type(self.file_count) is not int or self.file_count < 1:
            raise PipelineError("pipeline bundle file_count is invalid")
        _require_sha256(
            self.content_sha256, label="pipeline bundle content_sha256"
        )


def _json_content_ref(
    artifact: HydratedArtifactV1,
    document: Mapping[str, object],
    *,
    label: str,
) -> dict[str, object]:
    digest = _require_sha256(
        document.get("content_sha256"), label=f"{label} content_sha256"
    )
    if matrix_v2_semantic_sha256(dict(document)) != digest:
        raise PipelineError(f"{label} semantic identity is stale")
    return {
        "path": artifact.path,
        "file_sha256": artifact.file_sha256,
        "content_sha256": digest,
    }


def _dimension(state: str, identity: object) -> dict[str, object]:
    material = _require_mapping(_deep(identity), label=f"{state} dimension")
    return {
        "state": state,
        "identity": material,
        "content_sha256": _semantic(material),
    }


def _find_e2e_build(
    document: Mapping[str, object],
    *,
    core_id: str,
    architecture: str,
    label: str,
) -> dict[str, object]:
    builds = _require_list(document.get("builds"), label=f"{label} builds")
    matches = [
        item
        for item in builds
        if type(item) is dict
        and item.get("core_id") == core_id
        and item.get("architecture") == architecture
    ]
    if len(matches) != 1 or matches[0].get("result") != "passed":
        raise PipelineError(
            f"{label} lacks one passed build row for {core_id}/{architecture}"
        )
    return matches[0]


def _architecture_summary(
    telemetry: Mapping[str, object],
    *,
    core_id: str,
    architecture: str,
    label: str,
) -> dict[str, object]:
    builds = _require_list(telemetry.get("builds"), label=f"{label} builds")
    matches = [
        item
        for item in builds
        if type(item) is dict
        and item.get("core_id") == core_id
        and item.get("architecture") == architecture
    ]
    if len(matches) != 1:
        raise PipelineError(
            f"{label} lacks one row for {core_id}/{architecture}"
        )
    row = matches[0]
    phases = _require_mapping(row.get("phases"), label=f"{label} phases")
    resources = _require_mapping(
        row.get("resources"), label=f"{label} resources"
    )
    units = _require_mapping(row.get("units"), label=f"{label} units")
    container = _require_mapping(
        row.get("container"), label=f"{label} container"
    )
    end = _require_mapping(resources.get("end"), label=f"{label} resources.end")
    delta = _require_mapping(
        resources.get("delta"), label=f"{label} resources.delta"
    )
    cpu = _require_mapping(delta.get("cpu_stat"), label=f"{label} cpu_stat")
    memory_events = _require_mapping(
        delta.get("memory_events_local"), label=f"{label} memory events"
    )
    swap_events = _require_mapping(
        delta.get("swap_events"), label=f"{label} swap events"
    )
    phase_summary = {
        name: {
            "status": phase.get("status"),
            "duration_ns": phase.get("duration_ns"),
        }
        for name, phase in sorted(phases.items())
        if type(phase) is dict
    }
    longest = units.get("longest_compile_units")
    return {
        "result": telemetry.get("result"),
        "driver": row.get("driver"),
        "container_execution_duration_ns": container.get(
            "execution_duration_ns"
        ),
        "phases": phase_summary,
        "resources": {
            "memory_peak_bytes": end.get("memory_peak_bytes"),
            "pids_peak": end.get("pids_peak"),
            "swap_current_bytes": end.get("swap_current_bytes"),
            "cpu_usage_usec": cpu.get("usage_usec"),
            "cpu_user_usec": cpu.get("user_usec"),
            "cpu_system_usec": cpu.get("system_usec"),
            "cpu_nr_throttled": cpu.get("nr_throttled"),
            "cpu_throttled_usec": cpu.get("throttled_usec"),
            "memory_events": _deep(memory_events),
            "swap_events": _deep(swap_events),
        },
        "compile_units": {
            "counts": _deep(units.get("counts")),
            "configured_jobs": units.get("configured_jobs"),
            "compile_cpu_aggregate": _deep(
                units.get("compile_cpu_aggregate")
            ),
            "estimated_critical_path_ns": units.get(
                "estimated_critical_path_ns"
            ),
            "longest_compile_units": _deep(
                longest[:3] if type(longest) is list else longest
            ),
        },
    }


def _compact_parent_binding(binding: Mapping[str, object]) -> dict[str, object]:
    parent_cell = (
        binding.get("parent_cell")
        if type(binding.get("parent_cell")) is dict
        else {}
    )
    child_cell = (
        binding.get("child_cell")
        if type(binding.get("child_cell")) is dict
        else {}
    )
    return {
        "model": binding.get("model"),
        "track": binding.get("track"),
        "core_id": binding.get("core_id"),
        "chipset": binding.get("chipset"),
        "content_sha256": binding.get("content_sha256"),
        "captured_registry_content_sha256": binding.get(
            "captured_registry_content_sha256"
        ),
        "parent_track": binding.get("parent_track"),
        "parent_origin_track": binding.get("parent_origin_track"),
        "parent_selected_chipset": binding.get("parent_selected_chipset"),
        "parent_variant_id": binding.get("parent_variant_id"),
        "parent_build_pin_id": binding.get("parent_build_pin_id"),
        "parent_pin_content_sha256": binding.get("parent_pin_content_sha256"),
        "parent_source": {
            "repository": binding.get("parent_source_repository"),
            "requested_ref": binding.get("parent_source_requested_ref"),
            "commit": binding.get("parent_source_commit"),
            "tree": binding.get("parent_source_tree"),
        },
        "parent_version_slice": _deep(parent_cell.get("version_slice")),
        "parent_selection_content_sha256": binding.get(
            "parent_selection_content_sha256"
        ),
        "child_variant_id": binding.get("child_variant_id"),
        "child_build_pin_id": binding.get("child_build_pin_id"),
        "child_pin_content_sha256": binding.get("child_pin_content_sha256"),
        "child_source": {
            "repository": binding.get("child_source_repository"),
            "requested_ref": binding.get("child_source_requested_ref"),
            "commit": binding.get("child_source_commit"),
            "tree": binding.get("child_source_tree"),
        },
        "child_version_slice": _deep(child_cell.get("version_slice")),
        "parent_lineage": _deep(binding.get("parent_lineage")),
        "source_order_result": (
            "equal"
            if binding.get("parent_source_commit")
            == binding.get("child_source_commit")
            else "ancestor-validated-by-track-registry"
        ),
    }


def _lineage_and_outlier(
    track_registry: Mapping[str, object],
    *,
    track: str,
    core_id: str,
    selected_chipset: str,
    origin_track: str,
    source_registry_snapshots: Mapping[str, HydratedArtifactV1],
) -> tuple[dict[str, object], dict[str, object]]:
    bindings = _require_list(
        track_registry.get("source_order_parent_bindings"),
        label="track registry parent bindings",
    )
    outliers = _require_list(
        track_registry.get("source_order_outliers"),
        label="track registry outliers",
    )
    binding_matches = [
        item
        for item in bindings
        if type(item) is dict
        and item.get("track") == track
        and item.get("core_id") == core_id
        and item.get("chipset") == selected_chipset
    ]
    outlier_matches = [
        item
        for item in outliers
        if type(item) is dict
        and item.get("track") == track
        and item.get("core_id") == core_id
        and item.get("chipset") == selected_chipset
    ]
    if len(binding_matches) > 1 or len(outlier_matches) > 1:
        raise PipelineError("track lineage authority is ambiguous")
    authorization = outlier_matches[0] if outlier_matches else None
    outlier = {
        "state": "authorized" if authorization is not None else "none",
        "authorization": _deep(authorization),
    }
    if track == "main":
        if binding_matches or authorization is not None:
            raise PipelineError("main track cannot carry child lineage authority")
        return (
            {
                "state": "root-track-assignment",
                "parent_binding": None,
                "source_registry_snapshot": None,
            },
            outlier,
        )
    if binding_matches:
        binding = binding_matches[0]
        digest = _require_sha256(
            binding.get("captured_registry_content_sha256"),
            label="captured source registry content_sha256",
        )
        snapshot = source_registry_snapshots.get(digest)
        if type(snapshot) is not HydratedArtifactV1:
            raise PipelineError(
                f"captured source registry snapshot is unavailable: {digest}"
            )
        snapshot_document = snapshot.document(label="source registry snapshot")
        source_registry = _require_mapping(
            snapshot_document.get("source_registry"),
            label="captured source registry",
        )
        if core_tracks_content_sha256(source_registry) != digest:
            raise PipelineError("captured source registry identity is stale")
        return (
            {
                "state": "frozen-parent-assignment",
                "parent_binding": _compact_parent_binding(binding),
                "source_registry_snapshot": {
                    "path": snapshot.path,
                    "file_sha256": snapshot.file_sha256,
                    "registry_content_sha256": digest,
                },
            },
            outlier,
        )
    if origin_track != track:
        if authorization is not None:
            raise PipelineError("inherited assignment cannot carry an outlier")
        return (
            {
                "state": "inherited-track-assignment",
                "parent_binding": None,
                "source_registry_snapshot": None,
            },
            outlier,
        )
    if authorization is not None:
        return (
            {
                "state": "authorized-outlier",
                "parent_binding": None,
                "source_registry_snapshot": None,
            },
            outlier,
        )
    raise PipelineError(
        f"direct child assignment has no frozen parent: "
        f"{track}/{core_id}/{selected_chipset}"
    )


def _validated_inventory_row(
    inventory: object,
    *,
    coordinate: MatrixCoordinateV1,
    track_registry: Mapping[str, object],
) -> tuple[dict[str, object], bool]:
    document = _require_mapping(inventory, label="core track inventory")
    if document.get("content_sha256") != core_track_inventory_content_sha256(
        document
    ):
        raise PipelineError("core track inventory identity is stale")
    if document.get("track_registry_content_sha256") != track_registry.get(
        "content_sha256"
    ):
        raise PipelineError("inventory and track registry identities differ")
    expected_tag = canonical_group_tag(
        coordinate.track, "test", coordinate.chipset
    )
    if document.get("group_tag") != expected_tag:
        raise PipelineError("inventory group does not match the matrix coordinate")
    rows = _require_list(document.get("cores"), label="inventory cores")
    deferred = _require_list(
        document.get("deferred_cores"), label="inventory deferred cores"
    )
    unsupported = _require_list(
        document.get("unsupported_core_ids"), label="inventory unsupported cores"
    )
    admitted = len(rows) == 1 and not deferred and not unsupported
    deferred_selection = not rows and len(deferred) == 1 and not unsupported
    if not admitted and not deferred_selection:
        raise PipelineError(
            "cell projection requires one selected or one deferred core row"
        )
    row = _require_mapping(
        rows[0] if admitted else deferred[0],
        label="inventory selected row" if admitted else "inventory deferred row",
    )
    expected = {
        "core_id": coordinate.core_id,
        "track": coordinate.track,
        "requested_marker": "test",
        "requested_chipset": coordinate.chipset,
    }
    for key, value in expected.items():
        if row.get(key) != value:
            raise PipelineError(f"inventory row {key} differs from coordinate")
    if admitted:
        if row.get("selected_state") != "test":
            raise PipelineError("inventory selected state is not TEST")
        selected_architectures = _require_list(
            row.get("selected_architectures"),
            label="inventory selected architectures",
        )
        if coordinate.architecture not in selected_architectures:
            raise PipelineError("inventory row does not select this architecture")
    elif row.get("state") != "deferred":
        raise PipelineError("inventory deferred state is invalid")
    return row, admitted


def _validated_evidence(
    evidence: TrackCellEvidenceV1,
    *,
    row: Mapping[str, object],
    architecture: str,
) -> dict[str, object]:
    core_id = _require_string(row.get("core_id"), label="inventory core_id")
    pin_document = evidence.pin.document(label="pin")
    pin_id = _require_identifier(pin_document.get("pin_id"), label="pin_id")
    if pin_document.get("content_sha256") != pin_set_content_sha256(pin_document):
        raise PipelineError("pin semantic identity is stale")
    row_pin = _require_mapping(row.get("pin"), label="inventory pin")
    expected_pin = {
        "path": evidence.pin.path,
        "pin_id": pin_id,
        "file_sha256": evidence.pin.file_sha256,
        "content_sha256": pin_document.get("content_sha256"),
    }
    if row_pin != expected_pin:
        raise PipelineError("inventory pin binding differs from hydrated pin")
    scope = _require_list(pin_document.get("scope"), label="pin scope")
    cores = _require_mapping(pin_document.get("cores"), label="pin cores")
    if scope != [core_id] or frozenset(cores) != {core_id}:
        raise PipelineError("pin is not an exact one-core authority")
    core_record = _require_mapping(cores.get(core_id), label="pin core record")
    selection = _require_mapping(
        core_record.get("selection"), label="pin selection"
    )
    if selection.get("selection_sha256") != selection_content_sha256(selection):
        raise PipelineError("pin selection identity is stale")
    targets = _require_mapping(selection.get("targets"), label="pin targets")
    target = _require_mapping(targets.get(architecture), label="pin target")
    golden_record = _require_mapping(
        target.get("golden_record"), label="pin target golden record"
    )
    if golden_record.get("core_id") != core_id or golden_record.get(
        "architecture"
    ) != architecture:
        raise PipelineError("pin target coordinate is inconsistent")
    golden_document = evidence.golden.document(label="golden record")
    sources = _require_list(pin_document.get("sources"), label="pin sources")
    source_matches = [
        item
        for item in sources
        if type(item) is dict and item.get("pin_id") == pin_id
    ]
    if len(source_matches) != 1:
        raise PipelineError("pin does not bind one golden source")
    source = source_matches[0]
    golden_digest = _require_sha256(
        golden_document.get("content_sha256"),
        label="golden content_sha256",
    )
    if source != {
        "path": evidence.golden.path,
        "pin_id": pin_id,
        "file_sha256": evidence.golden.file_sha256,
        "content_sha256": golden_digest,
    }:
        raise PipelineError("pin golden source binding is inconsistent")
    build_goldens = _require_mapping(
        golden_document.get("build_goldens"), label="golden build records"
    )
    core_goldens = _require_mapping(
        build_goldens.get(core_id), label="golden core records"
    )
    if core_goldens.get(architecture) != golden_record:
        raise PipelineError("pin target differs from the authenticated golden")

    selected = evidence.selected_e2e.document(label="selected E2E")
    reproduction = evidence.reproduction_e2e.document(label="reproduction E2E")
    selected_telemetry = evidence.selected_telemetry.document(
        label="selected telemetry"
    )
    reproduction_telemetry = evidence.reproduction_telemetry.document(
        label="reproduction telemetry"
    )
    selected_build = _find_e2e_build(
        selected,
        core_id=core_id,
        architecture=architecture,
        label="selected E2E",
    )
    reproduction_build = _find_e2e_build(
        reproduction,
        core_id=core_id,
        architecture=architecture,
        label="reproduction E2E",
    )
    selected_record_digest = _require_sha256(
        selected_build.get("record_sha256"),
        label="selected build record digest",
    )
    reproduction_record_digest = _require_sha256(
        reproduction_build.get("record_sha256"),
        label="reproduction build record digest",
    )
    if (
        evidence.selected_build_record.file_sha256 != selected_record_digest
        or evidence.reproduction_build_record.file_sha256
        != reproduction_record_digest
    ):
        raise PipelineError("E2E build record binding is inconsistent")
    selected_record = evidence.selected_build_record.document(
        label="selected build record"
    )
    reproduction_record = evidence.reproduction_build_record.document(
        label="reproduction build record"
    )
    host = _require_mapping(
        selection.get("host_reproduction"), label="host reproduction proof"
    )
    if host.get("content_sha256") != host_reproduction_content_sha256(host):
        raise PipelineError("host reproduction proof identity is stale")
    for role, document, artifact in (
        ("selected", selected, evidence.selected_e2e),
        ("reproduction", reproduction, evidence.reproduction_e2e),
    ):
        proof = _require_mapping(host.get(role), label=f"host proof {role}")
        store = _require_mapping(
            proof.get("e2e_record"), label=f"host proof {role} E2E"
        )
        if (
            proof.get("run_id") != document.get("run_id")
            or proof.get("content_sha256") != document.get("content_sha256")
            or store.get("path") != artifact.path
            or store.get("sha256") != artifact.file_sha256
        ):
            raise PipelineError(f"host proof {role} E2E binding is inconsistent")
        _json_content_ref(artifact, document, label=f"{role} E2E")
    for role, e2e, telemetry, artifact in (
        ("selected", selected, selected_telemetry, evidence.selected_telemetry),
        (
            "reproduction",
            reproduction,
            reproduction_telemetry,
            evidence.reproduction_telemetry,
        ),
    ):
        runner = _require_mapping(e2e.get("runner"), label=f"{role} runner")
        telemetry_ref = _require_mapping(
            runner.get("telemetry"), label=f"{role} runner telemetry"
        )
        expected = {
            "path": artifact.path,
            "file_sha256": artifact.file_sha256,
            "content_sha256": telemetry.get("content_sha256"),
        }
        if telemetry_ref != expected:
            raise PipelineError(f"{role} telemetry binding is inconsistent")
        _json_content_ref(artifact, telemetry, label=f"{role} telemetry")
    host_execution = _require_mapping(
        _require_mapping(
            golden_record.get("recipe"), label="golden recipe"
        ).get("host_execution"),
        label="golden host execution",
    )
    schema_ref = _require_mapping(
        host_execution.get("telemetry_schema"),
        label="golden telemetry schema",
    )
    if schema_ref.get("file_sha256") != evidence.telemetry_schema.file_sha256:
        raise PipelineError("telemetry schema file identity is inconsistent")
    return {
        "pin": pin_document,
        "pin_id": pin_id,
        "selection": selection,
        "target": target,
        "golden_record": golden_record,
        "golden_document": golden_document,
        "selected": selected,
        "reproduction": reproduction,
        "selected_telemetry": selected_telemetry,
        "reproduction_telemetry": reproduction_telemetry,
        "selected_build": selected_build,
        "reproduction_build": reproduction_build,
        "selected_record": selected_record,
        "reproduction_record": reproduction_record,
        "host": host,
    }


def _require_inventory_variant(
    row: Mapping[str, object],
    *,
    track_registry: Mapping[str, object],
) -> str:
    core_id = _require_string(row.get("core_id"), label="variant core_id")
    origin_track = _require_string(
        row.get("test_origin_track"), label="variant origin track"
    )
    selected_chipset = _require_string(
        row.get("selected_chipset"), label="variant selected chipset"
    )
    tracks = _require_mapping(
        track_registry.get("tracks"), label="variant track registry"
    )
    origin = _require_mapping(
        tracks.get(origin_track), label=f"variant origin {origin_track}"
    )
    tests = _require_mapping(
        origin.get("test"), label=f"variant origin {origin_track} TEST"
    )
    core = _require_mapping(
        tests.get(core_id), label=f"variant origin {origin_track}/{core_id}"
    )
    cell = _require_mapping(
        core.get(selected_chipset),
        label=f"variant origin {origin_track}/{core_id}/{selected_chipset}",
    )
    pin = _require_mapping(row.get("pin"), label="variant inventory pin")
    tuning = _require_mapping(
        row.get("tuning"), label="variant inventory tuning"
    )
    material = {
        "core_id": core_id,
        "cell_chipset": selected_chipset,
        "pin": {
            key: pin.get(key)
            for key in ("path", "pin_id", "file_sha256", "content_sha256")
        },
        "source_commit": row.get("source_commit"),
        "architectures": row.get("architectures"),
        "tuning": {
            key: tuning.get(key)
            for key in (
                "profile_id",
                "content_sha256",
                "properties",
                "compiler_argument_mapping_version",
                "compiler_arguments",
            )
        },
        "applicable_chipsets": cell.get("applicable_chipsets"),
    }
    expected = _semantic(material)
    actual = _require_sha256(row.get("variant_id"), label="inventory variant_id")
    if actual != expected:
        raise PipelineError("inventory variant identity is stale")
    return actual


def _flatten_track_cells(
    value: object,
    *,
    label: str,
) -> dict[tuple[str, str], dict[str, object]]:
    document = _require_mapping(value, label=label)
    result: dict[tuple[str, str], dict[str, object]] = {}
    for core_id, chipsets_value in document.items():
        core_id = _require_string(core_id, label=f"{label} core_id")
        chipsets = _require_mapping(
            chipsets_value, label=f"{label}.{core_id}"
        )
        for chipset, cell in chipsets.items():
            chipset = _require_string(chipset, label=f"{label} chipset")
            result[(core_id, chipset)] = _require_mapping(
                cell, label=f"{label}.{core_id}.{chipset}"
            )
    return result


def _effective_test_cells(
    track_registry: Mapping[str, object],
) -> dict[str, dict[tuple[str, str], tuple[dict[str, object], str]]]:
    tracks = _require_mapping(
        track_registry.get("tracks"), label="producer track registry"
    )
    effective: dict[
        str, dict[tuple[str, str], tuple[dict[str, object], str]]
    ] = {}
    deferred: dict[str, set[tuple[str, str]]] = {}
    for track in TRACK_ORDER:
        track_document = _require_mapping(
            tracks.get(track), label=f"producer track {track}"
        )
        parent = {"main": None, "nightly": "main", "edge": "nightly"}[track]
        selected = dict(effective[parent]) if parent is not None else {}
        deferred_keys = set(deferred[parent]) if parent is not None else set()
        direct_deferred = _flatten_track_cells(
            track_document.get("deferred"),
            label=f"producer track {track} deferred",
        )
        for key in direct_deferred:
            selected.pop(key, None)
            deferred_keys.add(key)
        direct_test = _flatten_track_cells(
            track_document.get("test"), label=f"producer track {track} TEST"
        )
        for key, cell in direct_test.items():
            deferred_keys.discard(key)
            selected[key] = (cell, track)
        effective[track] = selected
        deferred[track] = deferred_keys
    return effective


def _canonical_producer_coordinate(
    track_registry: Mapping[str, object],
    *,
    row: Mapping[str, object],
    architecture: str,
) -> MatrixCoordinateV1:
    core_id = _require_string(row.get("core_id"), label="producer core_id")
    origin_track = _require_string(
        row.get("test_origin_track"), label="producer origin track"
    )
    selected_chipset = _require_string(
        row.get("selected_chipset"), label="producer selected chipset"
    )
    effective = _effective_test_cells(track_registry)
    try:
        source_cell, source_origin = effective[origin_track][
            (core_id, selected_chipset)
        ]
    except KeyError as exc:
        raise PipelineError("producer source TEST cell is unavailable") from exc
    if source_origin != origin_track:
        raise PipelineError("inventory origin track is not the direct TEST owner")
    expected_variant = _inventory_variant_for_cell(
        row,
        cell_chipset=selected_chipset,
        cell=source_cell,
    )
    if expected_variant != row.get("variant_id"):
        raise PipelineError("producer source TEST variant identity is stale")
    source_authority = _variant_cell_authority(
        source_cell,
        cell_chipset=selected_chipset,
    )
    for track in TRACK_ORDER:
        for requested_chipset, projected_architecture in PROJECTION_ORDER:
            if projected_architecture != architecture:
                continue
            order = (
                ("universal",)
                if requested_chipset == "universal"
                else (requested_chipset, "universal")
            )
            selected: tuple[str, dict[str, object]] | None = None
            for candidate_chipset in order:
                candidate = effective[track].get((core_id, candidate_chipset))
                if candidate is None:
                    continue
                candidate_cell, _candidate_origin = candidate
                applicable = candidate_cell.get("applicable_chipsets")
                if candidate_chipset == requested_chipset or (
                    candidate_chipset == "universal"
                    and type(applicable) is list
                    and requested_chipset in applicable
                ):
                    selected = (candidate_chipset, candidate_cell)
                    break
            if selected is None:
                continue
            candidate_chipset, candidate_cell = selected
            candidate_authority = _variant_cell_authority(
                candidate_cell,
                cell_chipset=candidate_chipset,
            )
            candidate_variant = _inventory_variant_for_cell(
                row,
                cell_chipset=candidate_chipset,
                cell=candidate_cell,
            )
            if (
                candidate_authority == source_authority
                and candidate_variant == expected_variant
            ):
                return MatrixCoordinateV1(
                    core_id=core_id,
                    track=track,
                    chipset=requested_chipset,
                    architecture=architecture,
                )
    raise PipelineError("admitted build identity has no canonical producer")


def canonical_track_inventory_producer_v1(
    inventory: object,
    *,
    coordinate: MatrixCoordinateV1,
    track_registry: object,
) -> MatrixCoordinateV1:
    """Return the projector's canonical producer for one admitted inventory row."""

    if type(coordinate) is not MatrixCoordinateV1:
        raise PipelineError("producer coordinate must be exact")
    registry = _require_mapping(track_registry, label="track registry")
    if registry.get("content_sha256") != core_tracks_content_sha256(registry):
        raise PipelineError("track registry identity is stale")
    row, admitted = _validated_inventory_row(
        inventory,
        coordinate=coordinate,
        track_registry=registry,
    )
    if not admitted:
        raise PipelineError("deferred inventory row has no producer")
    return _canonical_producer_coordinate(
        registry,
        row=row,
        architecture=coordinate.architecture,
    )


def _variant_cell_authority(
    cell: Mapping[str, object],
    *,
    cell_chipset: str,
) -> dict[str, object]:
    """Project registry inputs that decide physical variant equivalence."""

    cell_chipset = _require_string(
        cell_chipset, label="variant authority cell chipset"
    )
    applicable = _require_list(
        cell.get("applicable_chipsets"),
        label="variant authority applicable chipsets",
    )
    return {
        "cell_chipset": cell_chipset,
        "build_pin_id": _require_identifier(
            cell.get("build_pin_id"), label="variant authority build pin"
        ),
        "tuning_profile": _require_identifier(
            cell.get("tuning_profile"), label="variant authority tuning profile"
        ),
        "applicable_chipsets": _deep(applicable),
    }


def _inventory_variant_for_cell(
    row: Mapping[str, object],
    *,
    cell_chipset: str,
    cell: Mapping[str, object],
) -> str:
    """Derive ``core_variant_id`` material using an inventory's authorities."""

    pin = _require_mapping(row.get("pin"), label="producer inventory pin")
    tuning = _require_mapping(
        row.get("tuning"), label="producer inventory tuning"
    )
    authority = _variant_cell_authority(cell, cell_chipset=cell_chipset)
    material = {
        "core_id": row.get("core_id"),
        "cell_chipset": authority["cell_chipset"],
        "pin": {
            key: pin.get(key)
            for key in ("path", "pin_id", "file_sha256", "content_sha256")
        },
        "source_commit": row.get("source_commit"),
        "architectures": _deep(row.get("architectures")),
        "tuning": {
            key: _deep(tuning.get(key))
            for key in (
                "profile_id",
                "content_sha256",
                "properties",
                "compiler_argument_mapping_version",
                "compiler_arguments",
            )
        },
        "applicable_chipsets": authority["applicable_chipsets"],
    }
    return _semantic(material)


def _build_identity(
    *,
    row: Mapping[str, object],
    architecture: str,
    evidence: TrackCellEvidenceV1,
    validated: Mapping[str, object],
) -> dict[str, object]:
    golden = _require_mapping(
        validated.get("golden_record"), label="validated golden record"
    )
    toolchain_full = _require_mapping(
        golden.get("toolchain"), label="golden toolchain"
    )
    image_keys = {
        "image",
        "image_id",
        "resolved_image_id",
        "dockerfile",
        "dockerfile_sha256",
        "dockerfile_linkage",
    }
    toolchain = {
        key: _deep(value)
        for key, value in toolchain_full.items()
        if key not in image_keys
    }
    image = {
        key: _deep(toolchain_full.get(key))
        for key in (
            "image",
            "image_id",
            "resolved_image_id",
            "dockerfile",
            "dockerfile_sha256",
            "dockerfile_linkage",
        )
    }
    recipe_full = _require_mapping(golden.get("recipe"), label="golden recipe")
    local_store = _require_mapping(
        golden.get("local_store"), label="golden local store"
    )
    recipe_snapshots = _require_mapping(
        local_store.get("recipe_snapshots"), label="golden recipe snapshots"
    )
    pipeline_bundle = _require_mapping(
        recipe_full.get("pipeline_bundle"), label="golden pipeline bundle"
    )
    files = _require_mapping(
        pipeline_bundle.get("files"), label="golden pipeline files"
    )
    recipe = {
        "catalog_path": recipe_full.get("catalog_path"),
        "catalog_file_sha256": recipe_full.get("catalog_sha256"),
        "core_id": recipe_full.get("core_id"),
        "core_spec_content_sha256": recipe_full.get("core_spec_sha256"),
        "pipeline_bundle": {
            "schema_version": pipeline_bundle.get("schema_version"),
            "file_count": len(files),
            "content_sha256": pipeline_bundle.get("content_sha256"),
        },
        "pipeline_sha256": recipe_full.get("pipeline_sha256"),
        "workflow": recipe_full.get("workflow"),
        "workflow_sha256": recipe_full.get("workflow_sha256"),
        "commit_blacklist": _deep(recipe_full.get("commit_blacklist")),
        "host_execution": _deep(recipe_full.get("host_execution")),
        "recipe_snapshot": _deep(recipe_snapshots.get(architecture)),
    }
    dimensions = {
        "source": _dimension("established", golden.get("source")),
        "recipe": _dimension("established", recipe),
        "toolchain": _dimension("established", toolchain),
        "image": _dimension("established", image),
        "tuning": _dimension("established", row.get("tuning")),
        "build": _dimension("established", golden.get("build")),
    }
    pin_document = _require_mapping(validated.get("pin"), label="validated pin")
    selection = _require_mapping(
        validated.get("selection"), label="validated selection"
    )
    pin = {
        "path": evidence.pin.path,
        "pin_id": validated.get("pin_id"),
        "file_sha256": evidence.pin.file_sha256,
        "content_sha256": pin_document.get("content_sha256"),
        "selection_content_sha256": selection.get("selection_sha256"),
    }
    identity_material = {
        "core_id": row.get("core_id"),
        "architecture": architecture,
        "dimension_content_sha256": {
            name: dimensions[name]["content_sha256"] for name in _DIMENSION_NAMES
        },
    }
    return {
        "state": "established",
        "content_sha256": _semantic(identity_material),
        "variant_id": row.get("variant_id"),
        "pin": pin,
        **dimensions,
    }


def _run_projection(
    *,
    role: str,
    evidence: TrackCellEvidenceV1,
    validated: Mapping[str, object],
) -> dict[str, object]:
    if role == "selected":
        e2e_artifact = evidence.selected_e2e
        telemetry_artifact = evidence.selected_telemetry
        e2e = _require_mapping(validated.get("selected"), label="selected E2E")
        telemetry = _require_mapping(
            validated.get("selected_telemetry"), label="selected telemetry"
        )
        build_record = _require_mapping(
            validated.get("selected_record"), label="selected build record"
        )
        build = _require_mapping(
            validated.get("selected_build"), label="selected build"
        )
    elif role == "reproduction":
        e2e_artifact = evidence.reproduction_e2e
        telemetry_artifact = evidence.reproduction_telemetry
        e2e = _require_mapping(
            validated.get("reproduction"), label="reproduction E2E"
        )
        telemetry = _require_mapping(
            validated.get("reproduction_telemetry"),
            label="reproduction telemetry",
        )
        build_record = _require_mapping(
            validated.get("reproduction_record"),
            label="reproduction build record",
        )
        build = _require_mapping(
            validated.get("reproduction_build"), label="reproduction build"
        )
    else:
        raise PipelineError("evidence role is invalid")
    digest = _require_sha256(
        build.get("record_sha256"), label=f"{role} build record digest"
    )
    build_projection = _require_mapping(
        build_record.get("build"), label=f"{role} build record build"
    )
    log_digest = _require_sha256(
        build_projection.get("log_sha256"), label=f"{role} build log digest"
    )
    host = _require_mapping(validated.get("host"), label="host proof")
    host_role = _require_mapping(host.get(role), label=f"host proof {role}")
    store_e2e = _require_mapping(
        host_role.get("e2e_record"), label=f"host proof {role} store E2E"
    )
    return {
        "run_id": e2e.get("run_id"),
        "e2e": _json_content_ref(e2e_artifact, e2e, label=f"{role} E2E"),
        "store_e2e": {
            "path": store_e2e.get("path"),
            "file_sha256": store_e2e.get("sha256"),
        },
        "build_record": {
            "path": _store_path("build-records", digest),
            "file_sha256": digest,
            "store_path": _store_path("build-records", digest),
        },
        "build_log": {
            "path": _store_path("logs", log_digest),
            "file_sha256": log_digest,
        },
        "telemetry": _json_content_ref(
            telemetry_artifact, telemetry, label=f"{role} telemetry"
        ),
        "telemetry_schema": evidence.telemetry_schema.file_projection(),
        "runner": _deep(e2e.get("runner")),
    }


def _evidence_projection(
    *,
    evidence: TrackCellEvidenceV1,
    validated: Mapping[str, object],
    architecture: str,
) -> dict[str, object]:
    host = _require_mapping(validated.get("host"), label="host proof")
    target = _require_mapping(validated.get("target"), label="pin target")
    golden = _require_mapping(
        validated.get("golden_document"), label="golden document"
    )
    return {
        "state": "validated",
        "selected": _run_projection(
            role="selected", evidence=evidence, validated=validated
        ),
        "reproduction": _run_projection(
            role="reproduction", evidence=evidence, validated=validated
        ),
        "host_reproduction": {
            "validation_scope": host.get("validation_scope"),
            "schema_version": host.get("schema_version"),
            "content_sha256": host.get("content_sha256"),
            "equivalent_build_sha256": _require_mapping(
                host.get("equivalent_builds"), label="host equivalent builds"
            ).get(architecture),
            "equivalent_outputs": {
                "artifact": _deep(
                    _require_mapping(
                        _require_mapping(
                            host.get("equivalent_outputs"),
                            label="host equivalent outputs",
                        ).get("artifacts"),
                        label="host equivalent artifacts",
                    ).get(architecture)
                ),
                "metadata": _deep(
                    _require_mapping(
                        host.get("equivalent_outputs"),
                        label="host equivalent outputs",
                    ).get("metadata")
                ),
                "package": _deep(
                    _require_mapping(
                        host.get("equivalent_outputs"),
                        label="host equivalent outputs",
                    ).get("package")
                ),
            },
        },
        "golden": {
            "path": evidence.golden.path,
            "file_sha256": evidence.golden.file_sha256,
            "content_sha256": golden.get("content_sha256"),
            "architecture": architecture,
            "provenance_identity_sha256": target.get(
                "provenance_identity_sha256"
            ),
        },
    }


def _outputs_projection(
    *,
    evidence: TrackCellEvidenceV1,
    validated: Mapping[str, object],
    row: Mapping[str, object],
    architecture: str,
    build_identity_sha256: str,
) -> dict[str, object]:
    selection = _require_mapping(
        validated.get("selection"), label="validated selection"
    )
    target = _require_mapping(validated.get("target"), label="validated target")
    golden = _require_mapping(
        validated.get("golden_document"), label="validated golden"
    )
    selected = _require_mapping(
        validated.get("selected_build"), label="selected build"
    )
    reproduction = _require_mapping(
        validated.get("reproduction_build"), label="reproduction build"
    )
    selected_digest = _require_sha256(
        selected.get("record_sha256"), label="selected build record digest"
    )
    reproduction_digest = _require_sha256(
        reproduction.get("record_sha256"),
        label="reproduction build record digest",
    )
    pin = _require_mapping(validated.get("pin"), label="validated pin")
    pin_record = {
        "path": evidence.pin.path,
        "pin_id": validated.get("pin_id"),
        "file_sha256": evidence.pin.file_sha256,
        "content_sha256": pin.get("content_sha256"),
        "selection_content_sha256": selection.get("selection_sha256"),
    }
    return {
        "state": "available",
        "artifact": _deep(target.get("artifact")),
        "metadata": _deep(selection.get("metadata")),
        "package": _deep(selection.get("package")),
        "selected_build_record": {
            "path": _store_path("build-records", selected_digest),
            "file_sha256": selected_digest,
            "store_path": _store_path("build-records", selected_digest),
        },
        "reproduction_build_record": {
            "path": _store_path("build-records", reproduction_digest),
            "file_sha256": reproduction_digest,
            "store_path": _store_path("build-records", reproduction_digest),
        },
        "golden_record": {
            "path": evidence.golden.path,
            "file_sha256": evidence.golden.file_sha256,
            "content_sha256": golden.get("content_sha256"),
            "architecture": architecture,
            "provenance_identity_sha256": target.get(
                "provenance_identity_sha256"
            ),
        },
        "pin_record": pin_record,
        "variant": {
            "variant_id": row.get("variant_id"),
            "architecture": architecture,
            "build_identity_content_sha256": build_identity_sha256,
        },
    }


def _performance_projection(
    *,
    evidence: TrackCellEvidenceV1,
    validated: Mapping[str, object],
    coordinate: MatrixCoordinateV1,
    producer_coordinate: MatrixCoordinateV1,
) -> dict[str, object]:
    selected = _require_mapping(
        validated.get("selected_telemetry"), label="selected telemetry"
    )
    reproduction = _require_mapping(
        validated.get("reproduction_telemetry"),
        label="reproduction telemetry",
    )
    reused = coordinate != producer_coordinate
    return {
        "state": "reused-measurement" if reused else "measured",
        "producer_coordinate": producer_coordinate.to_document(),
        "selected": {
            "telemetry": _json_content_ref(
                evidence.selected_telemetry,
                selected,
                label="selected telemetry",
            ),
            "architecture_summary": _architecture_summary(
                selected,
                core_id=coordinate.core_id,
                architecture=coordinate.architecture,
                label="selected telemetry",
            ),
        },
        "reproduction": {
            "telemetry": _json_content_ref(
                evidence.reproduction_telemetry,
                reproduction,
                label="reproduction telemetry",
            ),
            "architecture_summary": _architecture_summary(
                reproduction,
                core_id=coordinate.core_id,
                architecture=coordinate.architecture,
                label="reproduction telemetry",
            ),
        },
    }


def _preserved_observations(
    predecessor_cell: MatrixCellV1,
    *,
    coordinate: MatrixCoordinateV1,
    row: Mapping[str, object],
    admitted: bool,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    if predecessor_cell.coordinate != coordinate:
        raise PipelineError("predecessor cell coordinate differs from projection")
    if predecessor_cell.partition != SUPPORTED_PARTITION:
        raise PipelineError("track admission requires a supported predecessor cell")
    predecessor = decode_matrix_v2(
        predecessor_cell.legacy_payload_json.encode("utf-8")
    )
    resolution = _require_mapping(
        predecessor.get("resolution"), label="predecessor resolution"
    )
    catalog_candidate = _require_mapping(
        resolution.get("catalog_candidate"),
        label="predecessor catalog candidate",
    )
    if catalog_candidate.get("architecture") != coordinate.architecture:
        raise PipelineError("predecessor catalog candidate coordinate is stale")
    edge_candidate = _require_mapping(
        resolution.get("edge_candidate"), label="predecessor edge candidate"
    )
    branch = _require_mapping(
        predecessor.get("branch_artifact_observation"),
        label="predecessor branch observation",
    )
    basis = _require_mapping(branch.get("basis"), label="branch observation basis")
    row_basis = _require_mapping(
        row.get("spruce_branch_basis"), label="inventory branch basis"
    )
    if _branch_basis_authority(
        basis, label="predecessor branch observation basis"
    ) != _branch_basis_authority(
        row_basis, label="inventory branch basis"
    ):
        raise PipelineError("predecessor and inventory branch bases differ")
    catalog_cell = _require_mapping(
        branch.get("catalog_cell"), label="branch observation catalog cell"
    )
    if (
        catalog_cell.get("core_id") != coordinate.core_id
        or catalog_cell.get("architecture") != coordinate.architecture
    ):
        raise PipelineError("predecessor branch observation coordinate is stale")
    branch_projection = _require_mapping(
        _deep(branch), label="branch observation projection"
    )
    if admitted:
        version_slice = _require_mapping(
            row.get("version_slice"), label="inventory version slice"
        )
        branch_projection["version_alignment"] = {
            "state": "manual-version-level-aligned",
            "authority": "track-version-slice",
            "version_slice_content_sha256": version_slice.get("content_sha256"),
            "artifact_byte_match_required": False,
            "artifact_byte_equality": "not-required-not-evaluated",
        }
    else:
        branch_projection["version_alignment"] = {
            "state": "not-assigned",
            "authority": None,
            "version_slice_content_sha256": None,
            "artifact_byte_match_required": False,
            "artifact_byte_equality": "not-required-not-evaluated",
        }
    return (
        _require_mapping(_deep(catalog_candidate), label="catalog candidate copy"),
        _require_mapping(_deep(edge_candidate), label="edge candidate copy"),
        branch_projection,
    )


def _candidate_build_identity(
    predecessor_cell: MatrixCellV1,
    *,
    coordinate: MatrixCoordinateV1,
    selected_chipset: str,
    pipeline_bundle_content_sha256: str,
) -> dict[str, object]:
    pipeline_bundle_content_sha256 = _require_sha256(
        pipeline_bundle_content_sha256,
        label="deferred pipeline bundle content_sha256",
    )
    predecessor = decode_matrix_v2(
        predecessor_cell.legacy_payload_json.encode("utf-8")
    )
    identity = _require_mapping(
        _deep(predecessor.get("build_identity")),
        label="predecessor candidate build identity",
    )
    expected_keys = frozenset(
        {"state", "content_sha256", "variant_id", "pin", *_DIMENSION_NAMES}
    )
    if frozenset(identity) != expected_keys or identity.get("state") != "candidate":
        raise PipelineError(
            "deferred projection requires a predecessor candidate build identity"
        )
    if identity.get("variant_id") is not None or identity.get("pin") is not None:
        raise PipelineError("predecessor candidate carries admitted pin state")
    dimensions: dict[str, dict[str, object]] = {}
    for name in _DIMENSION_NAMES:
        dimension = _require_mapping(
            identity.get(name), label=f"predecessor candidate {name}"
        )
        if frozenset(dimension) != {"state", "identity", "content_sha256"}:
            raise PipelineError(f"predecessor candidate {name} fields are not exact")
        material = _require_mapping(
            dimension.get("identity"), label=f"predecessor candidate {name} identity"
        )
        if (
            dimension.get("state") != "candidate"
            or dimension.get("content_sha256") != _semantic(material)
        ):
            raise PipelineError(f"predecessor candidate {name} identity is stale")
        dimensions[name] = dimension
    build = _require_mapping(
        dimensions["build"].get("identity"), label="candidate build dimension"
    )
    if (
        build.get("architecture") != coordinate.architecture
        or build.get("selected_chipset") != selected_chipset
    ):
        raise PipelineError("predecessor candidate build coordinate is stale")
    recipe_identity = _require_mapping(
        _deep(dimensions["recipe"].get("identity")),
        label="candidate recipe identity",
    )
    if "pipeline_bundle_content_sha256" not in recipe_identity:
        raise PipelineError("candidate recipe lacks a pipeline bundle binding")
    recipe_identity["pipeline_bundle_content_sha256"] = (
        pipeline_bundle_content_sha256
    )
    dimensions["recipe"] = _dimension("candidate", recipe_identity)
    identity_material = {
        "core_id": coordinate.core_id,
        "architecture": coordinate.architecture,
        "dimension_content_sha256": {
            name: dimensions[name]["content_sha256"] for name in _DIMENSION_NAMES
        },
    }
    return {
        "state": "candidate",
        "content_sha256": _semantic(identity_material),
        "variant_id": None,
        "pin": None,
        **dimensions,
    }


def _deferred_assignment_content_sha256(
    track_registry: Mapping[str, object],
    *,
    origin_track: str,
    core_id: str,
    selected_chipset: str,
) -> str:
    tracks = _require_mapping(
        track_registry.get("tracks"), label="track registry tracks"
    )
    origin = _require_mapping(
        tracks.get(origin_track), label=f"track registry {origin_track}"
    )
    deferred = _require_mapping(
        origin.get("deferred"), label=f"track registry {origin_track} deferred"
    )
    core = _require_mapping(
        deferred.get(core_id),
        label=f"track registry {origin_track} deferred {core_id}",
    )
    cell = _require_mapping(
        core.get(selected_chipset),
        label=(
            f"track registry {origin_track} deferred "
            f"{core_id}/{selected_chipset}"
        ),
    )
    return _semantic(
        {
            "model": "effective-deferred-track-cell-v1",
            "track": origin_track,
            "core_id": core_id,
            "chipset": selected_chipset,
            "cell": cell,
        }
    )


def _deferred_reason(
    *,
    track: str,
    edge_candidate: Mapping[str, object],
) -> str:
    if track == "main":
        return "no-reviewed-main-version-level-build-pin"
    if track == "nightly":
        return "no-reviewed-nightly-version-level-build-pin"
    if track != "edge":
        raise PipelineError("deferred matrix track is invalid")
    source = _require_mapping(
        edge_candidate.get("source"), label="deferred Edge candidate source"
    )
    status = source.get("status")
    reasons = {
        "unchanged": "reviewed-edge-head-needs-hardened-build-pin",
        "fast-forward": (
            "reviewed-edge-fast-forward-needs-build-and-host-reproduction"
        ),
        "diverged": (
            "reviewed-edge-divergence-needs-build-and-explicit-source-order-"
            "authorization"
        ),
    }
    if status not in reasons:
        raise PipelineError("frozen Edge candidate status is unsupported")
    return reasons[status]


def _project_deferred_cell(
    *,
    coordinate: MatrixCoordinateV1,
    row: Mapping[str, object],
    registry: Mapping[str, object],
    predecessor_cell: MatrixCellV1,
    pipeline_bundle_content_sha256: str,
) -> MatrixCellV1:
    selected_chipset = _require_string(
        row.get("selected_chipset"), label="deferred selected_chipset"
    )
    origin_track = _require_string(
        row.get("origin_track"), label="deferred origin_track"
    )
    catalog_candidate, edge_candidate, branch = _preserved_observations(
        predecessor_cell,
        coordinate=coordinate,
        row=row,
        admitted=False,
    )
    build_identity = _candidate_build_identity(
        predecessor_cell,
        coordinate=coordinate,
        selected_chipset=selected_chipset,
        pipeline_bundle_content_sha256=pipeline_bundle_content_sha256,
    )
    selected_assignment = _deferred_assignment_content_sha256(
        registry,
        origin_track=origin_track,
        core_id=coordinate.core_id,
        selected_chipset=selected_chipset,
    )
    cell: dict[str, object] = {
        "coordinate": coordinate.to_document(),
        "lifecycle": {
            "evidence_state": "candidate",
            "execution_state": "not-run",
            "admission_state": "deferred",
            "gha_state": "gha-not-requested",
            "reason": _deferred_reason(
                track=coordinate.track,
                edge_candidate=edge_candidate,
            ),
        },
        "resolution": {
            "requested_chipset": coordinate.chipset,
            "selected_chipset": selected_chipset,
            "selected_state": "deferred",
            "resolution": row.get("resolution"),
            "origin_track": origin_track,
            "assignment_mode": (
                "direct-deferred"
                if origin_track == coordinate.track
                else "inherited-deferred"
            ),
            "requested_assignment_content_sha256": row.get(
                "current_assignment_content_sha256"
            ),
            "selected_assignment_content_sha256": selected_assignment,
            "catalog_candidate": catalog_candidate,
            "edge_candidate": edge_candidate,
        },
        "build_identity": build_identity,
        "evidence": {
            "state": "absent-not-run",
            "selected": None,
            "reproduction": None,
            "host_reproduction": None,
            "golden": None,
        },
        "outputs": {
            "state": "absent-not-run",
            "artifact": None,
            "metadata": None,
            "package": None,
            "selected_build_record": None,
            "reproduction_build_record": None,
            "golden_record": None,
            "pin_record": None,
            "variant": None,
        },
        "version_slice": {"slice": None, "comparison_basis": None},
        "lineage": {
            "state": "not-applicable-unassigned",
            "parent_binding": None,
            "source_registry_snapshot": None,
        },
        "outlier": {
            "state": "not-applicable-unassigned",
            "authorization": None,
        },
        "reuse": {
            "mode": "none",
            "producer_coordinate": None,
            "equivalence": None,
        },
        "performance": {
            "state": "not-observed",
            "producer_coordinate": None,
            "selected": None,
            "reproduction": None,
        },
        "branch_artifact_observation": branch,
        "content_sha256": "",
    }
    cell["content_sha256"] = matrix_v2_semantic_sha256(cell)
    if frozenset(cell) != _SUPPORTED_CELL_KEYS:
        raise AssertionError("deferred cell projection fields drifted")
    return MatrixCellV1(
        universe_ordinal=coordinate.universe_ordinal,
        coordinate=coordinate,
        partition=SUPPORTED_PARTITION,
        legacy_payload_json=matrix_v2_canonical_bytes(cell).decode("utf-8"),
    )


def project_track_inventory_cell_v1(
    inventory: object,
    *,
    coordinate: MatrixCoordinateV1,
    track_registry: object,
    predecessor_cell: MatrixCellV1,
    evidence: TrackCellEvidenceV1 | None,
    producer_coordinate: MatrixCoordinateV1 | None,
    pipeline_bundle_content_sha256: str | None = None,
    source_registry_snapshots: Mapping[str, HydratedArtifactV1] | None = None,
) -> MatrixCellV1:
    """Project one TEST or deferred inventory row to the full 13-key cell.

    ``inventory`` must be the exact one-core output of the maintained
    ``construct_core_track_inventory`` validator.  ``predecessor_cell`` is
    authority only for the three explicitly preserved observational
    projections; it is never copied as lifecycle or build authority.
    """

    if type(coordinate) is not MatrixCoordinateV1:
        raise PipelineError("projection coordinate must be exact")
    registry = _require_mapping(track_registry, label="track registry")
    if registry.get("content_sha256") != core_tracks_content_sha256(registry):
        raise PipelineError("track registry identity is stale")
    row, admitted = _validated_inventory_row(
        inventory, coordinate=coordinate, track_registry=registry
    )
    if type(predecessor_cell) is not MatrixCellV1:
        raise PipelineError("projection predecessor cell must be exact")
    if not admitted:
        if evidence is not None or producer_coordinate is not None:
            raise PipelineError("deferred projection cannot carry admitted evidence")
        if pipeline_bundle_content_sha256 is None:
            raise PipelineError("deferred projection requires a pipeline bundle")
        return _project_deferred_cell(
            coordinate=coordinate,
            row=row,
            registry=registry,
            predecessor_cell=predecessor_cell,
            pipeline_bundle_content_sha256=pipeline_bundle_content_sha256,
        )
    if type(evidence) is not TrackCellEvidenceV1:
        raise PipelineError("admitted projection evidence must be exact")
    if type(producer_coordinate) is not MatrixCoordinateV1:
        raise PipelineError("admitted producer coordinate must be exact")
    if (
        producer_coordinate.core_id != coordinate.core_id
        or producer_coordinate.architecture != coordinate.architecture
    ):
        raise PipelineError("producer coordinate cannot produce this build identity")
    variant_id = _require_inventory_variant(row, track_registry=registry)
    expected_producer = _canonical_producer_coordinate(
        registry,
        row=row,
        architecture=coordinate.architecture,
    )
    if producer_coordinate != expected_producer:
        raise PipelineError("producer coordinate is not the canonical first use")
    validated = _validated_evidence(
        evidence, row=row, architecture=coordinate.architecture
    )
    build_identity = _build_identity(
        row=row,
        architecture=coordinate.architecture,
        evidence=evidence,
        validated=validated,
    )
    if variant_id != build_identity.get("variant_id"):
        raise PipelineError("inventory variant and projected build identity differ")
    selected_chipset = _require_string(
        row.get("selected_chipset"), label="inventory selected_chipset"
    )
    origin_track = _require_string(
        row.get("test_origin_track"), label="inventory test_origin_track"
    )
    selected_assignment = core_track_test_assignment_content_sha256(
        registry,
        track=origin_track,
        core_id=coordinate.core_id,
        chipset=selected_chipset,
    )
    if selected_assignment is None:
        raise PipelineError("selected TEST assignment has no maintained identity")
    catalog_candidate, edge_candidate, branch = _preserved_observations(
        predecessor_cell, coordinate=coordinate, row=row, admitted=True
    )
    lineage, outlier = _lineage_and_outlier(
        registry,
        track=coordinate.track,
        core_id=coordinate.core_id,
        selected_chipset=selected_chipset,
        origin_track=origin_track,
        source_registry_snapshots=source_registry_snapshots or {},
    )
    target = _require_mapping(validated.get("target"), label="validated target")
    host = _require_mapping(validated.get("host"), label="validated host proof")
    equivalent_builds = _require_mapping(
        host.get("equivalent_builds"), label="host equivalent builds"
    )
    equivalence = {
        "build_identity_content_sha256": build_identity["content_sha256"],
        "variant_id": build_identity["variant_id"],
        "architecture": coordinate.architecture,
        "pin_content_sha256": _require_mapping(
            build_identity.get("pin"), label="build identity pin"
        ).get("content_sha256"),
        "artifact_sha256": _require_mapping(
            target.get("artifact"), label="target artifact"
        ).get("sha256"),
        "equivalent_build_sha256": equivalent_builds.get(
            coordinate.architecture
        ),
        "host_reproduction_content_sha256": host.get("content_sha256"),
    }
    is_producer = coordinate == producer_coordinate
    cell: dict[str, object] = {
        "coordinate": coordinate.to_document(),
        "lifecycle": {
            "evidence_state": "host-validated",
            "execution_state": "built" if is_producer else "reused",
            "admission_state": "admitted",
            "gha_state": "gha-not-requested",
            "reason": None,
        },
        "resolution": {
            "requested_chipset": coordinate.chipset,
            "selected_chipset": selected_chipset,
            "selected_state": "test",
            "resolution": row.get("resolution"),
            "origin_track": origin_track,
            "assignment_mode": (
                "direct-test" if origin_track == coordinate.track else "inherited-test"
            ),
            "requested_assignment_content_sha256": row.get(
                "current_assignment_content_sha256"
            ),
            "selected_assignment_content_sha256": selected_assignment,
            "catalog_candidate": catalog_candidate,
            "edge_candidate": edge_candidate,
        },
        "build_identity": build_identity,
        "evidence": _evidence_projection(
            evidence=evidence,
            validated=validated,
            architecture=coordinate.architecture,
        ),
        "outputs": _outputs_projection(
            evidence=evidence,
            validated=validated,
            row=row,
            architecture=coordinate.architecture,
            build_identity_sha256=_require_sha256(
                build_identity.get("content_sha256"),
                label="build identity content_sha256",
            ),
        ),
        "version_slice": {
            "slice": _deep(row.get("version_slice")),
            "comparison_basis": _deep(row.get("slice_comparison_basis")),
        },
        "lineage": lineage,
        "outlier": outlier,
        "reuse": {
            "mode": "producer" if is_producer else "logical-reuse",
            "producer_coordinate": producer_coordinate.to_document(),
            "equivalence": equivalence,
        },
        "performance": _performance_projection(
            evidence=evidence,
            validated=validated,
            coordinate=coordinate,
            producer_coordinate=producer_coordinate,
        ),
        "branch_artifact_observation": branch,
        "content_sha256": "",
    }
    cell["content_sha256"] = matrix_v2_semantic_sha256(cell)
    if frozenset(cell) != _SUPPORTED_CELL_KEYS:
        raise AssertionError("supported cell projection fields drifted")
    return MatrixCellV1(
        universe_ordinal=coordinate.universe_ordinal,
        coordinate=coordinate,
        partition=SUPPORTED_PARTITION,
        legacy_payload_json=matrix_v2_canonical_bytes(cell).decode("utf-8"),
    )


def _evidence_input_projection(
    evidence: TrackCellEvidenceV1,
) -> tuple[str, dict[str, object]]:
    pin = evidence.pin.document(label="evidence input pin")
    pin_id = _require_identifier(pin.get("pin_id"), label="evidence pin_id")
    if pin.get("content_sha256") != pin_set_content_sha256(pin):
        raise PipelineError("evidence input pin identity is stale")
    scope = _require_list(pin.get("scope"), label="evidence pin scope")
    cores = _require_mapping(pin.get("cores"), label="evidence pin cores")
    if len(scope) != 1 or frozenset(cores) != frozenset(scope):
        raise PipelineError("evidence input pin is not an exact one-core pin")
    core_id = _require_string(scope[0], label="evidence core_id")
    core = _require_mapping(cores.get(core_id), label="evidence pin core")
    selection = _require_mapping(
        core.get("selection"), label="evidence pin selection"
    )
    if selection.get("selection_sha256") != selection_content_sha256(selection):
        raise PipelineError("evidence input selection identity is stale")
    host = _require_mapping(
        selection.get("host_reproduction"),
        label="evidence host reproduction",
    )
    if host.get("content_sha256") != host_reproduction_content_sha256(host):
        raise PipelineError("evidence host reproduction identity is stale")
    golden = evidence.golden.document(label="evidence golden")
    golden_reference = {
        "path": evidence.golden.path,
        "file_sha256": evidence.golden.file_sha256,
        "content_sha256": _require_sha256(
            golden.get("content_sha256"),
            label="evidence golden content_sha256",
        ),
    }
    sources = _require_list(pin.get("sources"), label="evidence pin sources")
    expected_source = {
        **golden_reference,
        "pin_id": pin_id,
    }
    if sources != [expected_source]:
        raise PipelineError("evidence pin golden input binding is inconsistent")
    documents = {
        "selected_e2e": (
            evidence.selected_e2e,
            evidence.selected_e2e.document(label="evidence selected E2E"),
        ),
        "reproduction_e2e": (
            evidence.reproduction_e2e,
            evidence.reproduction_e2e.document(
                label="evidence reproduction E2E"
            ),
        ),
        "selected_telemetry": (
            evidence.selected_telemetry,
            evidence.selected_telemetry.document(
                label="evidence selected telemetry"
            ),
        ),
        "reproduction_telemetry": (
            evidence.reproduction_telemetry,
            evidence.reproduction_telemetry.document(
                label="evidence reproduction telemetry"
            ),
        ),
    }
    for name, (artifact, document) in documents.items():
        _json_content_ref(artifact, document, label=name.replace("_", " "))
    for role, name in (
        ("selected", "selected_e2e"),
        ("reproduction", "reproduction_e2e"),
    ):
        artifact, document = documents[name]
        proof = _require_mapping(host.get(role), label=f"evidence host {role}")
        stored = _require_mapping(
            proof.get("e2e_record"), label=f"evidence host {role} E2E"
        )
        if (
            proof.get("run_id") != document.get("run_id")
            or proof.get("content_sha256") != document.get("content_sha256")
            or stored.get("path") != artifact.path
            or stored.get("sha256") != artifact.file_sha256
        ):
            raise PipelineError(f"evidence input {role} binding is inconsistent")
        telemetry_artifact, telemetry_document = documents[f"{role}_telemetry"]
        runner = _require_mapping(
            document.get("runner"), label=f"evidence input {role} runner"
        )
        telemetry_reference = _require_mapping(
            runner.get("telemetry"),
            label=f"evidence input {role} runner telemetry",
        )
        if telemetry_reference != _json_content_ref(
            telemetry_artifact,
            telemetry_document,
            label=f"evidence input {role} telemetry",
        ):
            raise PipelineError(
                f"evidence input {role} telemetry binding is inconsistent"
            )
    return (
        pin_id,
        {
            "core_id": core_id,
            "pin": {
                "path": evidence.pin.path,
                "file_sha256": evidence.pin.file_sha256,
                "content_sha256": pin.get("content_sha256"),
            },
            "golden": {
                **golden_reference,
            },
            **{
                name: _json_content_ref(
                    artifact,
                    document,
                    label=name.replace("_", " "),
                )
                for name, (artifact, document) in documents.items()
            },
            "host_reproduction_content_sha256": host.get("content_sha256"),
        },
    )


def _root_evidence_reference(
    value: object,
    *,
    label: str,
) -> dict[str, object]:
    reference = _require_mapping(value, label=label)
    if frozenset(reference) != _ROOT_EVIDENCE_REFERENCE_KEYS:
        raise PipelineError(f"{label} fields are not exact")
    return {
        "path": _require_relative_path(reference.get("path"), label=f"{label} path"),
        "file_sha256": _require_sha256(
            reference.get("file_sha256"), label=f"{label} file_sha256"
        ),
        "content_sha256": _require_sha256(
            reference.get("content_sha256"), label=f"{label} content_sha256"
        ),
    }


def _root_evidence_record(
    value: object,
    *,
    pin_id: str,
) -> dict[str, object]:
    record = _require_mapping(value, label=f"root evidence record {pin_id}")
    if frozenset(record) != _ROOT_EVIDENCE_RECORD_KEYS:
        raise PipelineError(f"root evidence record {pin_id} fields are not exact")
    return {
        "core_id": _require_string(
            record.get("core_id"), label=f"root evidence {pin_id} core_id"
        ),
        **{
            name: _root_evidence_reference(
                record.get(name), label=f"root evidence {pin_id} {name}"
            )
            for name in (
                "pin",
                "golden",
                "selected_e2e",
                "reproduction_e2e",
                "selected_telemetry",
                "reproduction_telemetry",
            )
        },
        "host_reproduction_content_sha256": _require_sha256(
            record.get("host_reproduction_content_sha256"),
            label=f"root evidence {pin_id} host reproduction",
        ),
    }


def _merge_root_evidence_records(
    predecessor_records: object,
    incoming_records: tuple[tuple[str, dict[str, object]], ...],
) -> dict[str, object]:
    """Merge evidence without permitting same-ID replacement or collision."""

    predecessor = _require_mapping(
        predecessor_records, label="predecessor evidence records"
    )
    if type(incoming_records) is not tuple:
        raise PipelineError("incoming evidence records must be an exact tuple")
    merged = {
        _require_identifier(pin_id, label="predecessor evidence pin_id"):
        _root_evidence_record(value, pin_id=pin_id)
        for pin_id, value in predecessor.items()
    }
    seen: dict[str, dict[str, object]] = {}
    for pair in incoming_records:
        if type(pair) is not tuple or len(pair) != 2:
            raise PipelineError("incoming evidence record pair is invalid")
        pin_id = _require_identifier(pair[0], label="incoming evidence pin_id")
        projection = _root_evidence_record(pair[1], pin_id=pin_id)
        if pin_id in seen and seen[pin_id] != projection:
            raise PipelineError(f"incoming evidence pin_id collision: {pin_id}")
        seen[pin_id] = projection
        if pin_id in merged and merged[pin_id] != projection:
            raise PipelineError(f"predecessor evidence pin_id collision: {pin_id}")
        merged[pin_id] = projection
    return {pin_id: _deep(merged[pin_id]) for pin_id in sorted(merged)}


def _cell_evidence_reference(
    value: object,
    *,
    label: str,
) -> dict[str, object]:
    reference = _require_mapping(value, label=label)
    return _root_evidence_reference(
        {key: reference.get(key) for key in _ROOT_EVIDENCE_REFERENCE_KEYS},
        label=label,
    )


def _admitted_cell_evidence_binding(
    payload: Mapping[str, object],
) -> tuple[str, dict[str, object], dict[str, object]]:
    coordinate = _require_mapping(
        payload.get("coordinate"), label="admitted evidence coordinate"
    )
    core_id = _require_string(
        coordinate.get("core_id"), label="admitted evidence core_id"
    )
    build = _require_mapping(
        payload.get("build_identity"), label="admitted evidence build identity"
    )
    pin = _require_mapping(build.get("pin"), label="admitted evidence pin")
    pin_id = _require_identifier(pin.get("pin_id"), label="admitted pin_id")
    pin_reference = _cell_evidence_reference(pin, label="admitted pin reference")
    selection_digest = _require_sha256(
        pin.get("selection_content_sha256"),
        label="admitted pin selection_content_sha256",
    )
    evidence = _require_mapping(
        payload.get("evidence"), label="admitted cell evidence"
    )
    if evidence.get("state") != "validated":
        raise PipelineError("admitted cell evidence state is not validated")
    golden = _cell_evidence_reference(
        evidence.get("golden"), label="admitted golden reference"
    )
    role_material: dict[str, object] = {}
    run_ids: dict[str, str] = {}
    for role in ("selected", "reproduction"):
        run = _require_mapping(
            evidence.get(role), label=f"admitted {role} evidence"
        )
        run_ids[role] = _require_string(
            run.get("run_id"), label=f"admitted {role} run_id"
        )
        role_material[f"{role}_e2e"] = _cell_evidence_reference(
            run.get("e2e"), label=f"admitted {role} E2E reference"
        )
        role_material[f"{role}_telemetry"] = _cell_evidence_reference(
            run.get("telemetry"),
            label=f"admitted {role} telemetry reference",
        )
    host = _require_mapping(
        evidence.get("host_reproduction"),
        label="admitted host reproduction",
    )
    record = {
        "core_id": core_id,
        "pin": pin_reference,
        "golden": golden,
        **role_material,
        "host_reproduction_content_sha256": _require_sha256(
            host.get("content_sha256"),
            label="admitted host reproduction content_sha256",
        ),
    }
    shared = {
        "record": record,
        "selection_content_sha256": selection_digest,
        "run_ids": run_ids,
    }
    return pin_id, record, shared


def _cross_validate_root_evidence(
    payloads: tuple[dict[str, object], ...],
    records: Mapping[str, object],
) -> frozenset[str]:
    """Bind every admitted cell to exactly one root evidence projection."""

    if type(payloads) is not tuple or any(type(item) is not dict for item in payloads):
        raise PipelineError("root evidence payloads must be an exact object tuple")
    projected = {
        _require_identifier(pin_id, label="root evidence pin_id"):
        _root_evidence_record(value, pin_id=pin_id)
        for pin_id, value in records.items()
    }
    shared_by_pin: dict[str, dict[str, object]] = {}
    admitted_pin_ids: set[str] = set()
    for payload in payloads:
        lifecycle = _require_mapping(
            payload.get("lifecycle"), label="root evidence lifecycle"
        )
        admission = lifecycle.get("admission_state")
        if admission == "deferred":
            build = _require_mapping(
                payload.get("build_identity"),
                label="deferred root evidence build identity",
            )
            evidence = _require_mapping(
                payload.get("evidence"), label="deferred root cell evidence"
            )
            if build.get("pin") is not None or evidence != _ABSENT_CELL_EVIDENCE:
                raise PipelineError("deferred cell carries admitted evidence")
            continue
        if admission != "admitted":
            raise PipelineError("root evidence admission state is invalid")
        pin_id, expected, shared = _admitted_cell_evidence_binding(payload)
        admitted_pin_ids.add(pin_id)
        if pin_id not in projected:
            raise PipelineError(
                f"root refresh lacks evidence projection for admitted pin: {pin_id}"
            )
        if projected[pin_id] != expected:
            raise PipelineError(
                f"root evidence projection differs from admitted cells: {pin_id}"
            )
        if pin_id in shared_by_pin and shared_by_pin[pin_id] != shared:
            raise PipelineError(
                f"admitted cells disagree on evidence identity: {pin_id}"
            )
        shared_by_pin[pin_id] = shared
    extra = frozenset(projected) - admitted_pin_ids
    if extra:
        raise PipelineError(
            "root evidence records lack admitted cells: " + ", ".join(sorted(extra))
        )
    return frozenset(admitted_pin_ids)


def _payload(cell: MatrixCellV1) -> dict[str, object]:
    payload = decode_matrix_v2(cell.legacy_payload_json.encode("utf-8"))
    if payload.get("content_sha256") != matrix_v2_semantic_sha256(payload):
        raise PipelineError("matrix cell payload identity is stale")
    return payload


def _require_cell_refresh_universe(
    predecessor: NormalizedMatrixV1,
    cells: object,
) -> tuple[MatrixCellV1, ...]:
    if type(cells) is not tuple or any(
        type(item) is not MatrixCellV1 for item in cells
    ):
        raise PipelineError("root refresh cells must be an exact MatrixCellV1 tuple")
    if len(cells) != EXPECTED_UNIVERSE_CELL_COUNT:
        raise PipelineError("root refresh requires the complete 2646-cell universe")
    predecessor_coordinates = tuple(
        (cell.coordinate, cell.partition) for cell in predecessor.cells
    )
    successor_coordinates = tuple((cell.coordinate, cell.partition) for cell in cells)
    if successor_coordinates != predecessor_coordinates:
        raise PipelineError(
            "cell refresh cannot change coordinate order or support partition"
        )
    return cells


def _nested_assignment_count(value: object, *, label: str) -> int:
    assignments = _require_mapping(value, label=label)
    count = 0
    for core_id, chipsets in assignments.items():
        _require_string(core_id, label=f"{label} core_id")
        count += len(_require_mapping(chipsets, label=f"{label}.{core_id}"))
    return count


def _track_summaries(
    track_registry: Mapping[str, object],
    cells: tuple[MatrixCellV1, ...],
) -> list[dict[str, object]]:
    registry_tracks = _require_mapping(
        track_registry.get("tracks"), label="track registry tracks"
    )
    version_policy = _require_mapping(
        track_registry.get("version_policy"), label="track version policy"
    )
    levels = _require_mapping(
        version_policy.get("levels"), label="track version levels"
    )
    payloads = tuple(
        _payload(cell) for cell in cells if cell.partition == SUPPORTED_PARTITION
    )
    result: list[dict[str, object]] = []
    for track in TRACK_ORDER:
        selected = [
            payload
            for payload in payloads
            if _require_mapping(
                payload.get("coordinate"), label="track summary coordinate"
            ).get("track")
            == track
        ]
        registry_track = _require_mapping(
            registry_tracks.get(track), label=f"track registry {track}"
        )
        branch_binding = _require_mapping(
            registry_track.get("spruce_branch_basis"),
            label=f"track registry {track} branch basis",
        )
        basis_values: dict[bytes, dict[str, object]] = {}
        for payload in selected:
            observation = _require_mapping(
                payload.get("branch_artifact_observation"),
                label=f"{track} branch observation",
            )
            authority = _branch_basis_authority(
                observation.get("basis"), label=f"{track} branch basis"
            )
            branch_basis = {
                **authority,
                "branch": _deep(observation.get("branch")),
            }
            basis_values[matrix_v2_canonical_bytes(branch_basis)] = branch_basis
        if len(basis_values) != 1:
            raise PipelineError(f"track {track} cells do not share one branch basis")
        branch_basis = next(iter(basis_values.values()))
        if _branch_basis_authority(
            branch_basis, label=f"projected {track} branch basis"
        ) != _branch_basis_authority(
            branch_binding, label=f"track registry {track} branch basis"
        ):
            raise PipelineError(f"track {track} branch authority is inconsistent")
        slices: dict[str, object] = {}
        for payload in selected:
            version_slice = _require_mapping(
                payload.get("version_slice"), label=f"{track} version slice"
            ).get("slice")
            if type(version_slice) is dict:
                digest = _require_sha256(
                    version_slice.get("content_sha256"),
                    label=f"{track} version slice content_sha256",
                )
                slices[digest] = _deep(version_slice)
        lifecycle = {
            axis: dict(
                sorted(
                    Counter(
                        _require_mapping(
                            payload.get("lifecycle"),
                            label=f"{track} lifecycle",
                        ).get(field)
                        for payload in selected
                    ).items()
                )
            )
            for axis, field in (
                ("evidence", "evidence_state"),
                ("execution", "execution_state"),
                ("admission", "admission_state"),
                ("gha", "gha_state"),
            )
        }
        deferred_cores = {
            _require_mapping(
                payload.get("coordinate"), label=f"{track} deferred coordinate"
            ).get("core_id")
            for payload in selected
            if _require_mapping(
                payload.get("lifecycle"), label=f"{track} deferred lifecycle"
            ).get("admission_state")
            == "deferred"
        }
        result.append(
            {
                "track": track,
                "version_level": levels.get(track),
                "branch_basis": branch_basis,
                "direct_test_assignment_count": _nested_assignment_count(
                    registry_track.get("test"), label=f"{track} direct test"
                ),
                "direct_stable_assignment_count": _nested_assignment_count(
                    registry_track.get("stable"), label=f"{track} direct stable"
                ),
                "effective_deferred_core_count": len(deferred_cores),
                "version_slices": [slices[key] for key in sorted(slices)],
                "supported_cell_count": len(selected),
                "lifecycle_counts": lifecycle,
                "resolution_counts": dict(
                    sorted(
                        Counter(
                            _require_mapping(
                                payload.get("resolution"),
                                label=f"{track} resolution",
                            ).get("resolution")
                            for payload in selected
                        ).items()
                    )
                ),
                "branch_artifact_correlation": dict(
                    sorted(
                        Counter(
                            _require_mapping(
                                payload.get("branch_artifact_observation"),
                                label=f"{track} branch observation",
                            ).get("artifact_validity")
                            for payload in selected
                        ).items()
                    )
                ),
                "source_order_outlier_count": sum(
                    _require_mapping(
                        payload.get("outlier"), label=f"{track} outlier"
                    ).get("state")
                    == "authorized"
                    for payload in selected
                ),
            }
        )
    return result


def _input_content_sha256(inputs: Mapping[str, object], key: str) -> str:
    value = _require_mapping(inputs.get(key), label=f"matrix input {key}")
    return _require_sha256(
        value.get("content_sha256"), label=f"matrix input {key} content_sha256"
    )


def _validation_ledger(
    *,
    predecessor: NormalizedMatrixV1,
    cells: tuple[MatrixCellV1, ...],
    root_projection: Mapping[str, object],
    track_registry: Mapping[str, object],
    authoritative_suite_summary: str,
    edge_source_count: int,
) -> dict[str, object]:
    inputs = _require_mapping(root_projection.get("inputs"), label="root inputs")
    supported = tuple(
        cell for cell in cells if cell.partition == SUPPORTED_PARTITION
    )
    exclusions = tuple(
        cell for cell in cells if cell.partition == EXCLUSION_PARTITION
    )
    payloads = tuple(_payload(cell) for cell in supported)
    old_by_coordinate = {
        cell.coordinate: cell.content_sha256 for cell in predecessor.cells
    }
    changed = tuple(
        cell
        for cell in cells
        if old_by_coordinate[cell.coordinate] != cell.content_sha256
    )
    admission = Counter(
        _require_mapping(payload.get("lifecycle"), label="ledger lifecycle").get(
            "admission_state"
        )
        for payload in payloads
    )
    execution = Counter(
        _require_mapping(payload.get("lifecycle"), label="ledger lifecycle").get(
            "execution_state"
        )
        for payload in payloads
    )
    admitted_pin_ids = {
        _require_mapping(
            _require_mapping(
                payload.get("build_identity"), label="ledger build identity"
            ).get("pin"),
            label="ledger admitted pin",
        ).get("pin_id")
        for payload in payloads
        if _require_mapping(
            payload.get("lifecycle"), label="ledger admitted lifecycle"
        ).get("admission_state")
        == "admitted"
    }
    edge_input = _require_mapping(
        inputs.get("edge_source_snapshot"), label="edge source snapshot input"
    )
    pipeline = _require_mapping(
        inputs.get("pipeline_bundle"), label="pipeline bundle input"
    )
    expansion = _require_mapping(
        root_projection.get("expansion"), label="root expansion"
    )
    source_bindings = _require_list(
        track_registry.get("source_order_parent_bindings"),
        label="track parent bindings",
    )
    outliers = _require_list(
        track_registry.get("source_order_outliers"), label="track outliers"
    )
    checks = [
        {
            "check_id": "canonical-inputs-validated-once",
            "status": "passed",
            "details": {
                "catalog_core_count": expansion.get("catalog_core_count"),
                "track_registry_content_sha256": _input_content_sha256(
                    inputs, "tracks"
                ),
                "tuning_registry_content_sha256": _input_content_sha256(
                    inputs, "tunings"
                ),
                "phase_freeze_content_sha256": _input_content_sha256(
                    inputs, "phase_freeze"
                ),
                "pipeline_source_content_sha256": pipeline.get(
                    "content_sha256"
                ),
                "authoritative_suite_summary": authoritative_suite_summary,
            },
        },
        {
            "check_id": "frozen-edge-snapshot-bound",
            "status": "passed",
            "details": {
                "content_sha256": edge_input.get("content_sha256"),
                "file_sha256": edge_input.get("file_sha256"),
                "source_count": edge_source_count,
            },
        },
        {
            "check_id": "coordinate-partition-exact",
            "status": "passed",
            "details": {
                "supported_cell_count": len(supported),
                "unsupported_exclusion_count": len(exclusions),
                "potential_coordinate_count": len(cells),
            },
        },
        {
            "check_id": "cell-order-and-uniqueness",
            "status": "passed",
            "details": {
                "supported_coordinate_set_content_sha256": _semantic(
                    [cell.coordinate.to_document() for cell in supported]
                ),
                "unsupported_coordinate_set_content_sha256": _semantic(
                    [cell.coordinate.to_document() for cell in exclusions]
                ),
            },
        },
        {
            "check_id": "independent-lifecycle-axes-cross-validated",
            "status": "passed",
            "details": {
                "admitted_cell_count": admission.get("admitted", 0),
                "deferred_cell_count": admission.get("deferred", 0),
                "producer_cell_count": execution.get("built", 0),
                "logical_reuse_cell_count": execution.get("reused", 0),
                "lifecycle_change_scope": sorted(
                    {cell.coordinate.core_id for cell in changed}
                ),
                "target_cell_count": len(changed),
                "unchanged_supported_cell_count": len(supported)
                - sum(cell.partition == SUPPORTED_PARTITION for cell in changed),
                "unchanged_exclusion_count": len(exclusions)
                - sum(cell.partition == EXCLUSION_PARTITION for cell in changed),
            },
        },
        {
            "check_id": "host-reproduction-proof-required-for-test",
            "status": "passed",
            "details": {
                "evidence_pin_count": len(admitted_pin_ids),
                "host_validated_cell_count": sum(
                    _require_mapping(
                        payload.get("lifecycle"), label="ledger evidence lifecycle"
                    ).get("evidence_state")
                    == "host-validated"
                    for payload in payloads
                ),
            },
        },
        {
            "check_id": "source-order-lineage-and-outliers-validated",
            "status": "passed",
            "details": {
                "parent_binding_count": len(source_bindings),
                "authorized_outlier_count": len(outliers),
            },
        },
        {
            "check_id": "branch-artifacts-observational-only",
            "status": "passed",
            "details": {
                "byte_match_required": False,
                "version_alignment_model": "manual-version-level-only",
            },
        },
        {
            "check_id": "per-cell-and-root-semantic-hash-projections",
            "status": "passed",
            "details": {
                "algorithm": "sha256",
                "serialization": "canonical-json-utf8-sort-keys-compact-v1",
            },
        },
        {
            "check_id": "json-schema-draft-2020-12",
            "status": "passed",
            "details": {
                "schema_path": _require_mapping(
                    inputs.get("schema"), label="matrix schema input"
                ).get("path")
            },
        },
        {
            "check_id": "deterministic-double-render",
            "status": "passed",
            "details": {"comparison": "exact-pretty-json-bytes"},
        },
    ]
    if tuple(item["check_id"] for item in checks) != _LEDGER_CHECK_IDS:
        raise AssertionError("matrix refresh ledger check order drifted")
    return {"status": "passed", "check_count": len(checks), "checks": checks}


def _expand_identity_template(
    template: object,
    *,
    semantic_sha256: str,
    file_sha256: str,
    label: str,
) -> str:
    value = _require_string(template, label=label)
    value = value.replace("<root-content-sha256>", semantic_sha256)
    value = value.replace("<raw-sha256[0:2]>", file_sha256[:2])
    value = value.replace("<raw-sha256>", file_sha256)
    if "<" in value or ">" in value:
        raise PipelineError(f"{label} contains an unsupported placeholder")
    return _require_relative_path(value, label=label)


def project_matrix_root_refresh_v1(
    predecessor: NormalizedMatrixV1,
    *,
    cells: tuple[MatrixCellV1, ...],
    captured_at: str,
    audit_label: str,
    leaf_audit_id: str,
    reason: str,
    predecessor_pointer_path: str,
    generator: HydratedArtifactV1,
    phase_freeze: EvidenceRef,
    track_registry_artifact: HydratedArtifactV1,
    pipeline_bundle: PipelineBundleIdentityV1,
    authoritative_suite_summary: str,
    edge_source_count: int,
    evidence_records: tuple[TrackCellEvidenceV1, ...] = (),
    pin_directory: DirectoryFingerprintV1 | None = None,
    track_registry_snapshot_directory: DirectoryFingerprintV1 | None = None,
) -> dict[str, object]:
    """Project all cell-changing legacy root fields from maintained inputs."""

    if type(predecessor) is not NormalizedMatrixV1:
        raise PipelineError("root refresh predecessor must be exact")
    validate_normalized_matrix(predecessor)
    cells = _require_cell_refresh_universe(predecessor, cells)
    captured_at = _require_timestamp(captured_at, label="root refresh captured_at")
    audit_label = _require_identifier(audit_label, label="root refresh audit label")
    leaf_audit_id = _require_identifier(
        leaf_audit_id, label="root refresh leaf audit id"
    )
    reason = _require_string(reason, label="root refresh reason")
    predecessor_pointer_path = _require_relative_path(
        predecessor_pointer_path, label="matrix predecessor pointer path"
    )
    if type(generator) is not HydratedArtifactV1:
        raise PipelineError("root refresh generator must be hydrated")
    if (
        type(phase_freeze) is not EvidenceRef
        or phase_freeze.kind not in {"phase-freeze", "phase-freeze-cas"}
        or phase_freeze.target_content_sha256 is None
    ):
        raise PipelineError("root refresh phase freeze reference is invalid")
    if type(track_registry_artifact) is not HydratedArtifactV1:
        raise PipelineError("root refresh track registry must be hydrated")
    if type(pipeline_bundle) is not PipelineBundleIdentityV1:
        raise PipelineError("root refresh pipeline bundle identity is invalid")
    authoritative_suite_summary = _require_string(
        authoritative_suite_summary,
        label="authoritative suite summary",
    )
    if type(edge_source_count) is not int or edge_source_count < 1:
        raise PipelineError("edge source count must be a positive integer")
    if type(evidence_records) is not tuple or any(
        type(item) is not TrackCellEvidenceV1 for item in evidence_records
    ):
        raise PipelineError("root evidence records must be an exact tuple")
    if pin_directory is not None and type(pin_directory) is not DirectoryFingerprintV1:
        raise PipelineError("pin directory fingerprint input is invalid")
    if (
        track_registry_snapshot_directory is not None
        and type(track_registry_snapshot_directory) is not DirectoryFingerprintV1
    ):
        raise PipelineError("track snapshot directory fingerprint input is invalid")

    registry = track_registry_artifact.document(label="track registry")
    if registry.get("content_sha256") != core_tracks_content_sha256(registry):
        raise PipelineError("track registry input identity is stale")
    predecessor_raw = materialize_matrix_v2(predecessor)
    predecessor_projection = decode_matrix_v2(
        predecessor.root.legacy_root_json.encode("utf-8")
    )
    if frozenset(predecessor_projection) != _ROOT_PROJECTION_KEYS:
        raise PipelineError("predecessor legacy root projection fields are invalid")
    inputs = _require_mapping(
        _deep(predecessor_projection.get("inputs")),
        label="predecessor matrix inputs",
    )
    if frozenset(inputs) != _ROOT_INPUT_KEYS:
        raise PipelineError("predecessor matrix input fields are not exact")
    inputs["generator"] = generator.file_projection()
    inputs["phase_freeze"] = {
        "path": phase_freeze.path,
        "file_sha256": phase_freeze.file_sha256,
        "content_sha256": phase_freeze.target_content_sha256,
    }
    inputs["tracks"] = {
        "path": track_registry_artifact.path,
        "file_sha256": track_registry_artifact.file_sha256,
        "content_sha256": registry.get("content_sha256"),
    }
    inputs["pipeline_bundle"] = {
        "source_phase_freeze_content_sha256": phase_freeze.target_content_sha256,
        "schema_version": pipeline_bundle.schema_version,
        "file_count": pipeline_bundle.file_count,
        "content_sha256": pipeline_bundle.content_sha256,
    }
    if pin_directory is not None:
        inputs["pin_directory"] = pin_directory.to_document()
    if track_registry_snapshot_directory is not None:
        inputs[
            "track_registry_snapshot_directory"
        ] = track_registry_snapshot_directory.to_document()
    old_evidence = _require_mapping(
        inputs.get("evidence_records"), label="predecessor evidence records"
    )
    projected_evidence = _merge_root_evidence_records(
        old_evidence,
        tuple(_evidence_input_projection(bundle) for bundle in evidence_records),
    )
    supported_payloads = tuple(
        _payload(cell) for cell in cells if cell.partition == SUPPORTED_PARTITION
    )
    admitted_pin_ids = _cross_validate_root_evidence(
        supported_payloads, projected_evidence
    )
    projected_evidence = {
        pin_id: projected_evidence[pin_id]
        for pin_id in sorted(admitted_pin_ids)
    }
    inputs["evidence_records"] = projected_evidence

    hash_model = _require_mapping(
        predecessor_projection.get("hash_model"),
        label="predecessor hash model",
    )
    semantic_sha256 = predecessor.root.legacy_matrix.semantic_sha256
    file_sha256 = predecessor.root.legacy_matrix.file_sha256
    if (
        sha256_bytes(predecessor_raw) != file_sha256
        or matrix_v2_semantic_sha256(decode_matrix_v2(predecessor_raw))
        != semantic_sha256
    ):
        raise PipelineError("predecessor materialized identity is inconsistent")
    supersedes = {
        "path": predecessor_pointer_path,
        "format": LEGACY_MATRIX_FORMAT,
        "content_sha256": semantic_sha256,
        "file_sha256": file_sha256,
        "bytes": len(predecessor_raw),
        "lines": _line_count(predecessor_raw),
        "reason": reason,
        "snapshot_path": _expand_identity_template(
            hash_model.get("semantic_snapshot_path_template"),
            semantic_sha256=semantic_sha256,
            file_sha256=file_sha256,
            label="matrix predecessor snapshot path",
        ),
        "cas_path": _expand_identity_template(
            hash_model.get("raw_cas_path_template"),
            semantic_sha256=semantic_sha256,
            file_sha256=file_sha256,
            label="matrix predecessor CAS path",
        ),
    }
    projection = _require_mapping(
        _deep(predecessor_projection), label="root refresh projection"
    )
    projection["captured_at"] = captured_at
    projection["audit"] = {
        "label": audit_label,
        "leaf_audit_id": leaf_audit_id,
    }
    projection["supersedes"] = supersedes
    projection["inputs"] = inputs
    projection["tracks"] = _track_summaries(registry, cells)
    projection["validation_ledger"] = _validation_ledger(
        predecessor=predecessor,
        cells=cells,
        root_projection=projection,
        track_registry=registry,
        authoritative_suite_summary=authoritative_suite_summary,
        edge_source_count=edge_source_count,
    )
    if frozenset(projection) != _ROOT_PROJECTION_KEYS:
        raise AssertionError("root refresh projection fields drifted")
    return projection


def _legacy_identity(
    projection: Mapping[str, object],
    cells: tuple[MatrixCellV1, ...],
) -> LegacyMatrixV2Identity:
    document = _require_mapping(_deep(projection), label="legacy root projection")
    document["supported_cells"] = [
        _payload(cell) for cell in cells if cell.partition == SUPPORTED_PARTITION
    ]
    document["unsupported_exclusions"] = [
        _payload(cell) for cell in cells if cell.partition == EXCLUSION_PARTITION
    ]
    document["summary"] = derive_legacy_summary(cells)
    document["content_sha256"] = matrix_v2_semantic_sha256(document)
    raw = render_matrix_v2(document)
    return LegacyMatrixV2Identity(
        semantic_sha256=_require_sha256(
            document.get("content_sha256"), label="legacy successor identity"
        ),
        file_sha256=sha256_bytes(raw),
        size=len(raw),
        lines=_line_count(raw),
    )


def _require_exact_replacement_coordinates(
    predecessor: tuple[tuple[MatrixCoordinateV1, str], ...],
    replacement: tuple[tuple[MatrixCoordinateV1, str], ...],
) -> str:
    """Validate a replacement as one exact coordinate/partition shard."""

    if type(predecessor) is not tuple or type(replacement) is not tuple:
        raise PipelineError("replacement coordinate sets must be exact tuples")
    if len(replacement) != UNIVERSE_CELLS_PER_CORE:
        raise PipelineError("matrix splicer requires exactly 27 replacement cells")
    if any(
        type(coordinate) is not MatrixCoordinateV1 or type(partition) is not str
        for coordinate, partition in (*predecessor, *replacement)
    ):
        raise PipelineError("replacement coordinate entries are invalid")
    core_ids = {coordinate.core_id for coordinate, _partition in replacement}
    ordinals = tuple(
        sorted(coordinate.universe_ordinal for coordinate, _partition in replacement)
    )
    if len(core_ids) != 1 or ordinals != tuple(range(UNIVERSE_CELLS_PER_CORE)):
        raise PipelineError("replacement cells must cover one exact core shard")
    core_id = next(iter(core_ids))
    predecessor_by_key = {
        (coordinate.core_id, coordinate.universe_ordinal): (coordinate, partition)
        for coordinate, partition in predecessor
    }
    for coordinate, partition in replacement:
        prior = predecessor_by_key.get((core_id, coordinate.universe_ordinal))
        if prior != (coordinate, partition):
            raise PipelineError(
                "replacement cell changes a coordinate or support partition"
            )
    return core_id


def _preserved_core_spec_set(
    predecessor: EvidenceRef,
    requested: EvidenceRef | None,
) -> EvidenceRef:
    """Keep H6 core-spec authority immutable across a one-shard refresh."""

    if type(predecessor) is not EvidenceRef:
        raise PipelineError("matrix predecessor core spec set must be exact")
    if requested is not None:
        if type(requested) is not EvidenceRef:
            raise PipelineError("matrix splicer core spec set must be exact")
        if requested != predecessor:
            raise PipelineError(
                "matrix splicer cannot override predecessor core spec authority"
            )
    return predecessor


def splice_matrix_core_refresh_v1(
    predecessor: NormalizedMatrixV1,
    *,
    replacement_cells: tuple[MatrixCellV1, ...],
    legacy_root_projection: object,
    phase_freeze: EvidenceRef,
    core_spec_set: EvidenceRef | None = None,
) -> NormalizedMatrixV1:
    """Splice one exact 27-cell core shard and derive the successor root."""

    if type(predecessor) is not NormalizedMatrixV1:
        raise PipelineError("matrix splicer predecessor must be exact")
    validate_normalized_matrix(predecessor)
    if type(replacement_cells) is not tuple or any(
        type(item) is not MatrixCellV1 for item in replacement_cells
    ):
        raise PipelineError("replacement cells must be an exact tuple")
    core_id = _require_exact_replacement_coordinates(
        tuple((cell.coordinate, cell.partition) for cell in predecessor.cells),
        tuple((cell.coordinate, cell.partition) for cell in replacement_cells),
    )
    predecessor_by_key = {
        (cell.coordinate.core_id, cell.universe_ordinal): cell
        for cell in predecessor.cells
    }
    for cell in replacement_cells:
        prior = predecessor_by_key.get((core_id, cell.universe_ordinal))
        if prior is None or (
            cell.coordinate != prior.coordinate or cell.partition != prior.partition
        ):
            raise PipelineError(
                "replacement cell changes a coordinate or support partition"
            )
    if all(
        cell == predecessor_by_key[(core_id, cell.universe_ordinal)]
        for cell in replacement_cells
    ):
        raise PipelineError("matrix splicer requires at least one changed cell")
    projection = _require_mapping(
        legacy_root_projection, label="legacy root refresh projection"
    )
    if frozenset(projection) != _ROOT_PROJECTION_KEYS:
        raise PipelineError("legacy root refresh projection fields are not exact")
    if type(phase_freeze) is not EvidenceRef:
        raise PipelineError("matrix splicer phase freeze must be exact")
    core_spec_set = _preserved_core_spec_set(
        predecessor.root.core_spec_set, core_spec_set
    )
    phase_input = _require_mapping(
        _require_mapping(projection.get("inputs"), label="splicer root inputs").get(
            "phase_freeze"
        ),
        label="splicer phase freeze input",
    )
    if (
        phase_input.get("path") != phase_freeze.path
        or phase_input.get("file_sha256") != phase_freeze.file_sha256
        or phase_input.get("content_sha256")
        != phase_freeze.target_content_sha256
    ):
        raise PipelineError("splicer phase freeze binding is inconsistent")

    replacements = {
        (cell.coordinate.core_id, cell.universe_ordinal): cell
        for cell in replacement_cells
    }
    cells = tuple(
        replacements.get((cell.coordinate.core_id, cell.universe_ordinal), cell)
        for cell in predecessor.cells
    )
    by_key = {
        (cell.coordinate.core_id, cell.universe_ordinal): cell for cell in cells
    }
    shards = tuple(
        MatrixShardV1(
            core_id=shard.core_id,
            cells=tuple(
                by_key[(shard.core_id, ordinal)].link(
                    matrix_object_reference(by_key[(shard.core_id, ordinal)])
                )
                for ordinal in range(UNIVERSE_CELLS_PER_CORE)
            ),
        )
        for shard in predecessor.shards
    )
    changed_shards = tuple(
        shard.core_id
        for prior, shard in zip(predecessor.shards, shards)
        if prior.content_sha256 != shard.content_sha256
    )
    if changed_shards != (core_id,):
        raise PipelineError("matrix splicer changed more than the selected shard")
    legacy_identity = _legacy_identity(projection, cells)
    root = MatrixRootV1(
        campaign_id=projection.get("campaign_id"),  # type: ignore[arg-type]
        captured_at=projection.get("captured_at"),  # type: ignore[arg-type]
        phase_freeze=phase_freeze,
        core_spec_set=core_spec_set,
        legacy_matrix=legacy_identity,
        legacy_root_json=matrix_v2_canonical_bytes(projection).decode("utf-8"),
        shards=tuple(
            shard.link(matrix_object_reference(shard)) for shard in shards
        ),
    )
    successor = NormalizedMatrixV1(
        root=root,
        root_reference=matrix_object_reference(root),
        shards=shards,
        cells=cells,
    )
    validate_normalized_matrix(successor)
    return successor


__all__ = [
    "DirectoryFingerprintV1",
    "HydratedArtifactV1",
    "PipelineBundleIdentityV1",
    "TrackCellEvidenceV1",
    "canonical_track_inventory_producer_v1",
    "project_matrix_root_refresh_v1",
    "project_track_inventory_cell_v1",
    "splice_matrix_core_refresh_v1",
]
