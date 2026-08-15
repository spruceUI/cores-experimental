"""Pure post-Gambatte matrix-authority transition planning.

This module replaces the held executable matrix-generator inheritance chain
with one explicit-input, deterministic planner.  It performs no filesystem,
audit, process, lock, clock, or publication work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..source_bundle import pipeline_source_bundle_is_well_formed
from .json_wire import (
    canonical_json_bytes,
    decode_identity_object,
    rendered_json_bytes,
)
from .legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
    render_matrix_v2,
)
from .model import (
    MATRIX_AUTHORITY_ALLOWED_CHANGES,
    MATRIX_AUTHORITY_REQUIRED_CHECKS,
    EvidenceRef,
    TransitionPlan,
    TransitionSpec,
)
from .projection import project_without_pointers, require_exact_pointer_delta
from .validate import validate_spec_plan


MATRIX_FORMAT: Final = "spruce-host-core-campaign-matrix-v2"
EXPECTED_TRANSITION_ID: Final = "post-gambatte-authority-v1"
EXPECTED_CAMPAIGN_ID: Final = "host-core-build-20260810"
EXPECTED_PREDECESSOR_PATH: Final = (
    ".local-e2e/campaigns/host-core-build-20260810/campaign-matrix.json"
)
EXPECTED_PHASE_FREEZE_PATH: Final = (
    ".local-e2e/campaigns/host-core-build-20260810/freezes/phase1/"
    "0c57e20111a6c704c1481993f60fcce0b58cf1c52b00cbd4b969aab18fb7de1c.json"
)
EXPECTED_SPEC_PATH: Final = (
    "manifests/campaign-transitions/post-gambatte-authority-v1.json"
)
EXPECTED_ENGINE_BUNDLE_PATH: Final = (
    "manifests/campaign-engine-bundles/post-gambatte-authority-v1.json"
)
TRANSITION_MEMBER_PATH: Final = (
    "scripts/core_pipeline_lib/campaign/transition.py"
)
EXPECTED_SUPERSEDES_REASON: Final = (
    "rebind the exact 9119/2dac post-VEmulator matrix to the sealed "
    "post-Gambatte contract authority; no track admission changed, so preserve "
    "all 2538 supported cells, all 108 exclusions, complete VEmulator and 2048 "
    "projections, summaries, and global totals byte-semantically"
)

EXPECTED_PREDECESSOR_CONTENT_SHA256: Final = (
    "9119385c8d6b57fb4800ad1bc9248ecef2071f54af9e5c8faa5534969dbd8601"
)
EXPECTED_PREDECESSOR_FILE_SHA256: Final = (
    "2dac212759e6c55b0351019c5d3a7471a6256fdf8eb25b0df51e36183e545940"
)
EXPECTED_PREDECESSOR_BYTES: Final = 40_426_561
EXPECTED_PREDECESSOR_LINES: Final = 900_383
EXPECTED_PHASE_FREEZE_CONTENT_SHA256: Final = (
    "0c57e20111a6c704c1481993f60fcce0b58cf1c52b00cbd4b969aab18fb7de1c"
)
EXPECTED_PHASE_FREEZE_FILE_SHA256: Final = (
    "6bdeb20ef855ceb47e2825726edb7280953e60f883f2e45d716c6c0c03d2f70f"
)
EXPECTED_PHASE_FREEZE_BYTES: Final = 281_849
EXPECTED_PHASE_FREEZE_LINES: Final = 4_294
EXPECTED_CANONICAL_INPUT_COUNT: Final = 98
EXPECTED_ADMITTED_CELL_COUNT: Final = 297
EXPECTED_EVIDENCE_PIN_COUNT: Final = 11
EXPECTED_HOST_VALIDATED_CELL_COUNT: Final = 297
EXPECTED_VEMULATOR_MAIN_CELL_COUNT: Final = 9
EXPECTED_PARENT_BINDING_COUNT: Final = 22
EXPECTED_VERSION_ALIGNMENT_MODEL: Final = "manual-version-level-only"
EXPECTED_DEFERRED_CELL_COUNT: Final = 2_241
EXPECTED_LOGICAL_REUSE_CELL_COUNT: Final = 275
EXPECTED_PRODUCER_CELL_COUNT: Final = 22
EXPECTED_SUPPORTED_COORDINATE_SET_SHA256: Final = (
    "69a76c04a120e9c7f07ffeabc39e1e40f47ffc6c8dff738b1955fef74658e936"
)
EXPECTED_UNSUPPORTED_COORDINATE_SET_SHA256: Final = (
    "4ace9dbf03f1f7437a982a25429b6c61c066eac17f849a4db21d7280a615da47"
)
EXPECTED_CATALOG_CONTENT_SHA256: Final = (
    "45551ccb96efc00224b1b24d2f1978dad3fd7eb022a2aee089b085519b222bf9"
)
EXPECTED_CATALOG_FILE_SHA256: Final = (
    "a9ba3ee4e34e38367786164bd4da61b00ac459a76f0ca7a239a23be82c582964"
)
EXPECTED_PER_CELL_HASH_ALGORITHM: Final = "sha256"
EXPECTED_PER_CELL_HASH_SERIALIZATION: Final = (
    "canonical-json-utf8-sort-keys-compact-v1"
)
EXPECTED_DOUBLE_RENDER_COMPARISON: Final = "exact-pretty-json-bytes"
EXPECTED_PREDECESSOR_CURRENT_AUTHORITY_SHA256: Final = (
    "67106d4e338b1e55365b52acf5a095d5eaf6ab10a451d01b9f7b5ae0f75bbf64"
)
EXPECTED_PREDECESSOR_HISTORICAL_CHAIN_SHA256: Final = (
    "54270d6325b4b13c31b795a184fad1dac5f78e36e1e3662af250667f1e4c14f7"
)

EXPECTED_SCHEMA_FILE_SHA256: Final = (
    "e4f8f9df63a00cdc07f564ac5fc3add29faf3ab2885f5cb752cd8e1efe2abc3f"
)
EXPECTED_SCHEMA_CANONICAL_SHA256: Final = (
    "f403970826adaed7161b8df6305d9c9202cea62f076889760dd3869bd14b11e0"
)
EXPECTED_SCHEMA_BYTES: Final = 45_949
EXPECTED_SCHEMA_LINES: Final = 1_373
EXPECTED_SCHEMA_DRAFT: Final = "https://json-schema.org/draft/2020-12/schema"
EXPECTED_SCHEMA_PATH: Final = (
    ".local-e2e/campaigns/host-core-build-20260810/matrices/"
    "spruce-host-core-campaign-matrix-v2.schema.json"
)

EXPECTED_SUPPORTED_CELL_COUNT: Final = 2_538
EXPECTED_EXCLUSION_COUNT: Final = 108
EXPECTED_VEMULATOR_CELL_COUNT: Final = 27
EXPECTED_2048_CELL_COUNT: Final = 27
EXPECTED_PRESERVED_PROJECTION_SHA256: Final = (
    "05ef400c659b28933354d6e952c5be643d41465531f7615e9b1157eeafd24d07"
)
EXPECTED_SUPPORTED_CELLS_SHA256: Final = (
    "33f83588d67a3feccb949c4493a19c236a74febdd2c4298d9328c65af3b7fca1"
)
EXPECTED_EXCLUSIONS_SHA256: Final = (
    "a6f4aaf333412d0b22a7661ea4fc3544902f20dae8f596dfd156c6adbd539e68"
)
EXPECTED_SUMMARY_SHA256: Final = (
    "11f68969164b50e3754835551e7705dbc9222756e110f7b9b94a9d3443f1350c"
)
EXPECTED_TRACKS_SHA256: Final = (
    "a45fd14500027db3bea1a22f37fdab053b508eeae3225be77eb39530f1d137e7"
)
EXPECTED_VEMULATOR_PROJECTION_SHA256: Final = (
    "91f0aaf4bb876d2608fbdb7adf7cd40277c42bf3b734dbc241725d60dec60af7"
)
EXPECTED_2048_PROJECTION_SHA256: Final = (
    "cb20017847d5902f63d76fc2c166077bf5990ccae849a572c4ae3c275fa9b210"
)

LEGACY_CHECK_IDS: Final = (
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

LEGACY_DETAIL_KEYS: Final = {
    "canonical-inputs-validated-once": frozenset(
        {
            "authoritative_suite_summary",
            "catalog_core_count",
            "current_authority",
            "historical_predecessor_chain",
            "phase_freeze_content_sha256",
            "pipeline_source_content_sha256",
            "track_registry_content_sha256",
            "tuning_registry_content_sha256",
        }
    ),
    "frozen-edge-snapshot-bound": frozenset(
        {"content_sha256", "file_sha256", "source_count"}
    ),
    "coordinate-partition-exact": frozenset(
        {
            "potential_coordinate_count",
            "supported_cell_count",
            "unsupported_exclusion_count",
        }
    ),
    "cell-order-and-uniqueness": frozenset(
        {
            "supported_coordinate_set_content_sha256",
            "unsupported_coordinate_set_content_sha256",
        }
    ),
    "independent-lifecycle-axes-cross-validated": frozenset(
        {
            "admitted_cell_count",
            "allowed_target_changes",
            "deferred_cell_count",
            "lifecycle_change_scope",
            "logical_reuse_cell_count",
            "non_target_supported_exact_count",
            "preserved_2048_cell_count",
            "preserved_vemulator_main_cell_count",
            "producer_cell_count",
            "target_cell_count",
            "unchanged_exclusion_count",
        }
    ),
    "host-reproduction-proof-required-for-test": frozenset(
        {"evidence_pin_count", "host_validated_cell_count"}
    ),
    "source-order-lineage-and-outliers-validated": frozenset(
        {"authorized_outlier_count", "parent_binding_count"}
    ),
    "branch-artifacts-observational-only": frozenset(
        {"byte_match_required", "version_alignment_model"}
    ),
    "per-cell-and-root-semantic-hash-projections": frozenset(
        {"algorithm", "serialization"}
    ),
    "json-schema-draft-2020-12": frozenset({"schema_path"}),
    "deterministic-double-render": frozenset({"comparison"}),
}

_SUPERSEDES_KEYS: Final = frozenset(
    {
        "path",
        "format",
        "content_sha256",
        "file_sha256",
        "bytes",
        "lines",
        "snapshot_path",
        "cas_path",
        "reason",
    }
)
_GENERATOR_INPUT_KEYS: Final = frozenset({"path", "file_sha256"})
_PHASE_FREEZE_INPUT_KEYS: Final = frozenset(
    {"path", "content_sha256", "file_sha256"}
)
_PIPELINE_INPUT_KEYS: Final = frozenset(
    {
        "schema_version",
        "file_count",
        "content_sha256",
        "source_phase_freeze_content_sha256",
    }
)
_LEDGER_KEYS: Final = frozenset({"check_count", "checks", "status"})
_LEGACY_CHECK_KEYS: Final = frozenset({"check_id", "details", "status"})
_COORDINATE_KEYS: Final = frozenset(
    {"architecture", "chipset", "core_id", "marker", "track"}
)
_CANONICAL_INPUT_KEYS: Final = frozenset(
    {
        "catalog",
        "commit_blacklist",
        "core_specs",
        "host_execution",
        "instrumentation",
        "recipe_auxiliaries",
        "schemas",
        "spruce_branch_bases",
        "spruce_release_roster",
        "telemetry_schema",
        "toolchain_lock",
        "tracks",
        "tunings",
        "workflows",
    }
)
_CATALOG_INPUT_KEYS: Final = frozenset(
    {
        "content_sha256",
        "core_count",
        "file_sha256",
        "path",
        "resolver",
        "toolchains",
    }
)
_PREDECESSOR_CURRENT_AUTHORITY_KEYS: Final = frozenset(
    {
        "audit",
        "classification",
        "full_suite",
        "generator_path",
        "phase_freeze",
        "phase_freeze_generator",
        "pin_directory",
        "pipeline_bundle",
        "production_bundle",
        "targeted_suite",
        "tests_bundle",
        "track_snapshot_directory",
        "tracks",
    }
)
_PREDECESSOR_HISTORICAL_CHAIN_KEYS: Final = frozenset(
    {
        "adapter",
        "classification",
        "inherited_provenance",
        "matrix",
        "phase_freeze",
    }
)


@dataclass(frozen=True, slots=True)
class PlannedMatrixAuthorityRefresh:
    """One deterministic plan and its uncommitted legacy matrix bytes."""

    plan: TransitionPlan
    candidate_raw: bytes
    changed_pointers: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.plan) is not TransitionPlan:
            raise PipelineError("planned refresh plan must be an exact TransitionPlan")
        if type(self.candidate_raw) is not bytes:
            raise PipelineError("planned refresh candidate_raw must be exact bytes")
        if type(self.changed_pointers) is not tuple or any(
            type(pointer) is not str for pointer in self.changed_pointers
        ):
            raise PipelineError("planned refresh changed_pointers must be exact strings")
        if self.changed_pointers != MATRIX_AUTHORITY_ALLOWED_CHANGES:
            raise PipelineError("planned refresh changed_pointers differ from policy")


def _require_exact_mapping(
    value: object,
    *,
    label: str,
    keys: frozenset[str] | None = None,
) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise PipelineError(f"{label} must be an exact string-keyed mapping")
    if keys is not None and frozenset(value) != keys:
        raise PipelineError(f"{label} keys are not exact")
    return value


def _require_exact_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact list")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _line_count(raw: bytes) -> int:
    return raw.count(b"\n") + int(bool(raw) and not raw.endswith(b"\n"))


def _require_reference_binding(
    reference: object,
    raw: object,
    *,
    kind: str,
    target_content_sha256: str,
    label: str,
) -> EvidenceRef:
    if type(reference) is not EvidenceRef:
        raise PipelineError(f"{label} must be an exact EvidenceRef")
    if type(raw) is not bytes:
        raise PipelineError(f"{label} raw value must be exact bytes")
    if reference.kind != kind:
        raise PipelineError(f"{label} kind is invalid")
    if reference.target_content_sha256 != target_content_sha256:
        raise PipelineError(f"{label} semantic identity is invalid")
    if reference.file_sha256 != sha256_bytes(raw):
        raise PipelineError(f"{label} raw identity is invalid")
    if reference.size != len(raw):
        raise PipelineError(f"{label} size is invalid")
    return reference


def _require_outer_digest(document: dict[str, object], *, label: str) -> str:
    embedded = _require_sha256(document.get("content_sha256"), label=f"{label} digest")
    computed = matrix_v2_semantic_sha256(document)
    if embedded != computed:
        raise PipelineError(f"{label} embedded content_sha256 is invalid")
    return computed


def _require_frozen_raw_identity(
    raw: bytes,
    *,
    semantic_sha256: str,
    expected_semantic_sha256: str,
    expected_file_sha256: str,
    expected_size: int,
    expected_lines: int,
    label: str,
) -> None:
    if semantic_sha256 != expected_semantic_sha256:
        raise PipelineError(f"{label} semantic identity is not the frozen authority")
    if sha256_bytes(raw) != expected_file_sha256:
        raise PipelineError(f"{label} raw identity is not the frozen authority")
    if len(raw) != expected_size or _line_count(raw) != expected_lines:
        raise PipelineError(f"{label} byte/line identity is not the frozen authority")


def _require_source_bundle(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise PipelineError(f"{label} must be an exact mapping document")
    detached = decode_identity_object(value, label=label)
    if not pipeline_source_bundle_is_well_formed(detached):
        raise PipelineError(f"{label} is not an exact pipeline source bundle")
    return detached


def _detached(value: object, *, label: str) -> object:
    try:
        envelope = project_without_pointers({"value": value}, ())
    except PipelineError as exc:
        raise PipelineError(f"{label} is not detached legacy JSON: {exc}") from exc
    if type(envelope) is not dict or frozenset(envelope) != {"value"}:
        raise PipelineError(f"{label} did not detach through the closed envelope")
    return envelope["value"]


def _freeze_authority_facts(freeze: dict[str, object]) -> dict[str, object]:
    canonical_inputs = _require_exact_mapping(
        freeze.get("canonical_inputs"),
        label="phase freeze canonical_inputs",
        keys=_CANONICAL_INPUT_KEYS,
    )
    core_specs = _require_exact_mapping(
        canonical_inputs.get("core_specs"),
        label="phase freeze canonical_inputs core_specs",
    )
    catalog = _require_exact_mapping(
        canonical_inputs.get("catalog"),
        label="phase freeze canonical_inputs catalog",
        keys=_CATALOG_INPUT_KEYS,
    )
    core_count = catalog.get("core_count")
    if type(core_count) is not int or core_count != len(core_specs):
        raise PipelineError("phase freeze catalog core_count is invalid")
    if core_count != EXPECTED_CANONICAL_INPUT_COUNT:
        raise PipelineError("phase freeze canonical input count is invalid")
    catalog_content_sha256 = _require_sha256(
        catalog.get("content_sha256"),
        label="phase freeze catalog content_sha256",
    )
    catalog_file_sha256 = _require_sha256(
        catalog.get("file_sha256"),
        label="phase freeze catalog file_sha256",
    )
    if catalog_content_sha256 != EXPECTED_CATALOG_CONTENT_SHA256:
        raise PipelineError("phase freeze catalog semantic identity is invalid")
    if catalog_file_sha256 != EXPECTED_CATALOG_FILE_SHA256:
        raise PipelineError("phase freeze catalog raw identity is invalid")

    tracks = _require_exact_mapping(
        canonical_inputs.get("tracks"),
        label="phase freeze canonical_inputs tracks",
    )
    tunings = _require_exact_mapping(
        canonical_inputs.get("tunings"),
        label="phase freeze canonical_inputs tunings",
    )
    track_content_sha256 = _require_sha256(
        tracks.get("content_sha256"),
        label="phase freeze track registry content_sha256",
    )
    tuning_content_sha256 = _require_sha256(
        tunings.get("content_sha256"),
        label="phase freeze tuning registry content_sha256",
    )
    validation = _require_exact_mapping(
        freeze.get("validation"),
        label="phase freeze validation",
    )
    authoritative_suite = _require_exact_mapping(
        validation.get("authoritative_post_gambatte_full_suite"),
        label="phase freeze authoritative suite",
    )
    if "summary" not in authoritative_suite:
        raise PipelineError("phase freeze authoritative suite summary is missing")
    suite_summary = _detached(
        authoritative_suite["summary"],
        label="phase freeze authoritative suite summary",
    )
    return {
        "authoritative_suite_summary": suite_summary,
        "catalog_content_sha256": catalog_content_sha256,
        "catalog_file_sha256": catalog_file_sha256,
        "catalog_core_count": core_count,
        "track_registry_content_sha256": track_content_sha256,
        "tuning_registry_content_sha256": tuning_content_sha256,
    }


def _require_phase_freeze(
    raw: bytes,
    reference: EvidenceRef,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    freeze = decode_matrix_v2(raw)
    content_sha256 = _require_outer_digest(freeze, label="phase freeze")
    _require_reference_binding(
        reference,
        raw,
        kind="phase-freeze",
        target_content_sha256=content_sha256,
        label="phase freeze reference",
    )
    if reference.path != EXPECTED_PHASE_FREEZE_PATH:
        raise PipelineError("phase freeze reference path is not authorized")
    _require_frozen_raw_identity(
        raw,
        semantic_sha256=content_sha256,
        expected_semantic_sha256=EXPECTED_PHASE_FREEZE_CONTENT_SHA256,
        expected_file_sha256=EXPECTED_PHASE_FREEZE_FILE_SHA256,
        expected_size=EXPECTED_PHASE_FREEZE_BYTES,
        expected_lines=EXPECTED_PHASE_FREEZE_LINES,
        label="phase freeze",
    )
    if freeze.get("local_only") is not True or freeze.get("publication") != "disabled":
        raise PipelineError("phase freeze must remain local and publication-disabled")
    bundles = _require_exact_mapping(freeze.get("bundles"), label="phase freeze bundles")
    pipeline_source = _require_source_bundle(
        bundles.get("pipeline_source"),
        label="phase freeze pipeline_source",
    )
    return freeze, pipeline_source, _freeze_authority_facts(freeze)


def _require_engine_bundle(
    reference: object,
    document: object,
) -> tuple[EvidenceRef, dict[str, object]]:
    bundle = _require_source_bundle(document, label="engine bundle")
    content_sha256 = _require_sha256(
        bundle.get("content_sha256"),
        label="engine bundle content_sha256",
    )
    raw = rendered_json_bytes(bundle)
    reference = _require_reference_binding(
        reference,
        raw,
        kind="engine-bundle",
        target_content_sha256=content_sha256,
        label="engine bundle reference",
    )
    if reference.path != EXPECTED_ENGINE_BUNDLE_PATH:
        raise PipelineError("engine bundle reference path is not authorized")
    files = _require_exact_mapping(bundle.get("files"), label="engine bundle files")
    _require_sha256(
        files.get(TRANSITION_MEMBER_PATH),
        label="engine transition.py member",
    )
    return reference, bundle


def _require_predecessor(
    raw: object,
    reference: EvidenceRef,
) -> tuple[bytes, dict[str, object]]:
    if type(raw) is not bytes:
        raise PipelineError("predecessor_raw must be exact bytes")
    predecessor = decode_matrix_v2(raw)
    if predecessor.get("format") != MATRIX_FORMAT:
        raise PipelineError("predecessor matrix format is invalid")
    content_sha256 = _require_outer_digest(predecessor, label="predecessor matrix")
    _require_reference_binding(
        reference,
        raw,
        kind="matrix-pointer",
        target_content_sha256=content_sha256,
        label="predecessor reference",
    )
    if reference.path != EXPECTED_PREDECESSOR_PATH:
        raise PipelineError("predecessor reference path is not authorized")
    _require_frozen_raw_identity(
        raw,
        semantic_sha256=content_sha256,
        expected_semantic_sha256=EXPECTED_PREDECESSOR_CONTENT_SHA256,
        expected_file_sha256=EXPECTED_PREDECESSOR_FILE_SHA256,
        expected_size=EXPECTED_PREDECESSOR_BYTES,
        expected_lines=EXPECTED_PREDECESSOR_LINES,
        label="predecessor matrix",
    )
    return raw, predecessor


def _semantic_sha256(value: object) -> str:
    return sha256_bytes(matrix_v2_canonical_bytes(value))


def _core_projection(
    supported_cells: list[object],
    *,
    core_name: str,
) -> list[object]:
    projection: list[object] = []
    for index, value in enumerate(supported_cells):
        cell = _require_exact_mapping(value, label=f"supported cell {index}")
        coordinate = _require_exact_mapping(
            cell.get("coordinate"),
            label=f"supported cell {index} coordinate",
            keys=_COORDINATE_KEYS,
        )
        core = coordinate.get("core_id")
        if type(core) is not str:
            raise PipelineError(f"supported cell {index} coordinate core_id is invalid")
        if core.casefold() == core_name.casefold():
            projection.append(cell)
    return projection


def _preserved_facts(document: dict[str, object]) -> dict[str, object]:
    supported_cells = _require_exact_list(
        document.get("supported_cells"),
        label="matrix supported_cells",
    )
    exclusions = _require_exact_list(
        document.get("unsupported_exclusions"),
        label="matrix unsupported_exclusions",
    )
    if len(supported_cells) != EXPECTED_SUPPORTED_CELL_COUNT:
        raise PipelineError("matrix supported cell count is invalid")
    if len(exclusions) != EXPECTED_EXCLUSION_COUNT:
        raise PipelineError("matrix exclusion count is invalid")
    summary = _require_exact_mapping(document.get("summary"), label="matrix summary")
    if _summary_count(summary, "supported_cell_count") != EXPECTED_SUPPORTED_CELL_COUNT:
        raise PipelineError("matrix summary supported cell count is invalid")
    if (
        _summary_count(summary, "unsupported_exclusion_count")
        != EXPECTED_EXCLUSION_COUNT
    ):
        raise PipelineError("matrix summary exclusion count is invalid")
    tracks = document.get("tracks")
    if type(tracks) not in {dict, list}:
        raise PipelineError("matrix tracks must be an exact mapping or list")

    vemulator = _core_projection(supported_cells, core_name="vemulator")
    core_2048 = _core_projection(supported_cells, core_name="2048")
    if len(vemulator) != EXPECTED_VEMULATOR_CELL_COUNT:
        raise PipelineError("matrix VEmulator projection count is invalid")
    if len(core_2048) != EXPECTED_2048_CELL_COUNT:
        raise PipelineError("matrix 2048 projection count is invalid")

    facts: dict[str, object] = {
        "supported_cells_sha256": _semantic_sha256(supported_cells),
        "unsupported_exclusions_sha256": _semantic_sha256(exclusions),
        "summary_sha256": _semantic_sha256(summary),
        "tracks_sha256": _semantic_sha256(tracks),
        "vemulator_projection_sha256": _semantic_sha256(vemulator),
        "2048_projection_sha256": _semantic_sha256(core_2048),
        "supported_cell_count": len(supported_cells),
        "exclusion_count": len(exclusions),
        "vemulator_cell_count": len(vemulator),
        "2048_cell_count": len(core_2048),
    }
    expected_hashes = {
        "supported_cells_sha256": EXPECTED_SUPPORTED_CELLS_SHA256,
        "unsupported_exclusions_sha256": EXPECTED_EXCLUSIONS_SHA256,
        "summary_sha256": EXPECTED_SUMMARY_SHA256,
        "tracks_sha256": EXPECTED_TRACKS_SHA256,
        "vemulator_projection_sha256": EXPECTED_VEMULATOR_PROJECTION_SHA256,
        "2048_projection_sha256": EXPECTED_2048_PROJECTION_SHA256,
    }
    for name, expected in expected_hashes.items():
        if facts[name] != expected:
            raise PipelineError(f"matrix preserved hash is invalid: {name}")
    return facts


def _summary_count(summary: dict[str, object], name: str) -> int:
    value = summary.get(name)
    if type(value) is not int or value < 0:
        raise PipelineError(f"matrix summary {name} is invalid")
    return value


def _require_legacy_ledger_template(
    value: object,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    ledger = _require_exact_mapping(
        value,
        label="legacy validation ledger",
        keys=_LEDGER_KEYS,
    )
    check_count = ledger.get("check_count")
    if type(check_count) is not int or check_count != len(LEGACY_CHECK_IDS):
        raise PipelineError("legacy validation ledger check_count is invalid")
    if ledger.get("status") != "passed":
        raise PipelineError("legacy validation ledger status is invalid")
    raw_checks = _require_exact_list(
        ledger.get("checks"),
        label="legacy validation ledger checks",
    )
    checks: list[dict[str, object]] = []
    for index, (value, expected_id) in enumerate(zip(raw_checks, LEGACY_CHECK_IDS)):
        check = _require_exact_mapping(
            value,
            label=f"legacy validation check {index}",
            keys=_LEGACY_CHECK_KEYS,
        )
        if check.get("check_id") != expected_id or check.get("status") != "passed":
            raise PipelineError(f"legacy validation check {index} identity is invalid")
        details = _require_exact_mapping(
            check.get("details"),
            label=f"legacy validation check {expected_id} details",
        )
        if frozenset(details) != LEGACY_DETAIL_KEYS[expected_id]:
            raise PipelineError(
                f"legacy validation check {expected_id} detail keys are invalid"
            )
        checks.append(check)
    if len(raw_checks) != len(LEGACY_CHECK_IDS):
        raise PipelineError("legacy validation ledger must contain exactly 11 checks")
    return ledger, checks


def _legacy_details(
    *,
    check_id: str,
    predecessor: dict[str, object],
    spec_ref: EvidenceRef,
    predecessor_ref: EvidenceRef,
    phase_freeze_ref: EvidenceRef,
    engine_bundle_ref: EvidenceRef,
    engine_member_sha256: str,
    pipeline_source: dict[str, object],
    freeze_authority: dict[str, object],
    prior_details: dict[str, object],
) -> dict[str, object]:
    summary = _require_exact_mapping(predecessor.get("summary"), label="matrix summary")
    pipeline_files = _require_exact_mapping(
        pipeline_source.get("files"),
        label="phase freeze pipeline files",
    )
    prior = _detached(prior_details, label=f"legacy {check_id} details")
    if type(prior) is not dict:
        raise PipelineError(f"legacy {check_id} details did not detach as a mapping")

    if check_id == "canonical-inputs-validated-once":
        predecessor_current_authority = prior.get("current_authority")
        inherited_predecessor_chain = prior.get("historical_predecessor_chain")
        _require_exact_mapping(
            predecessor_current_authority,
            label="legacy predecessor current authority",
            keys=_PREDECESSOR_CURRENT_AUTHORITY_KEYS,
        )
        _require_exact_mapping(
            inherited_predecessor_chain,
            label="legacy inherited predecessor chain",
            keys=_PREDECESSOR_HISTORICAL_CHAIN_KEYS,
        )
        current_authority_sha256 = _semantic_sha256(
            predecessor_current_authority
        )
        inherited_chain_sha256 = _semantic_sha256(inherited_predecessor_chain)
        if (
            current_authority_sha256
            != EXPECTED_PREDECESSOR_CURRENT_AUTHORITY_SHA256
        ):
            raise PipelineError("legacy predecessor current authority is invalid")
        if (
            inherited_chain_sha256
            != EXPECTED_PREDECESSOR_HISTORICAL_CHAIN_SHA256
        ):
            raise PipelineError("legacy inherited predecessor chain is invalid")
        return {
            "authoritative_suite_summary": freeze_authority[
                "authoritative_suite_summary"
            ],
            "catalog_core_count": freeze_authority["catalog_core_count"],
            "current_authority": {
                "engine_bundle": engine_bundle_ref.to_document(),
                "phase_freeze": phase_freeze_ref.to_document(),
                "pipeline_source": {
                    "content_sha256": pipeline_source["content_sha256"],
                    "file_count": len(pipeline_files),
                },
                "transition_spec": spec_ref.to_document(),
            },
            "historical_predecessor_chain": {
                "classification": "authority-only",
                "matrix": predecessor_ref.to_document(),
                "adapter": {
                    "classification": "tracked-pure-planner",
                    "file_sha256": engine_member_sha256,
                    "path": TRANSITION_MEMBER_PATH,
                },
                "predecessor_current_authority": {
                    "content_sha256": current_authority_sha256
                },
                "inherited_predecessor_chain": {
                    "content_sha256": inherited_chain_sha256
                },
            },
            "phase_freeze_content_sha256": phase_freeze_ref.target_content_sha256,
            "pipeline_source_content_sha256": pipeline_source["content_sha256"],
            "track_registry_content_sha256": freeze_authority[
                "track_registry_content_sha256"
            ],
            "tuning_registry_content_sha256": freeze_authority[
                "tuning_registry_content_sha256"
            ],
        }
    if check_id == "frozen-edge-snapshot-bound":
        _require_sha256(
            prior.get("content_sha256"),
            label="predecessor frozen catalog content_sha256",
        )
        _require_sha256(
            prior.get("file_sha256"),
            label="predecessor frozen catalog file_sha256",
        )
        source_count = prior.get("source_count")
        if type(source_count) is not int:
            raise PipelineError("predecessor frozen catalog source_count is invalid")
        return {
            "content_sha256": freeze_authority["catalog_content_sha256"],
            "file_sha256": freeze_authority["catalog_file_sha256"],
            "source_count": freeze_authority["catalog_core_count"],
        }
    if check_id == "coordinate-partition-exact":
        return {
            "potential_coordinate_count": (
                EXPECTED_SUPPORTED_CELL_COUNT + EXPECTED_EXCLUSION_COUNT
            ),
            "supported_cell_count": EXPECTED_SUPPORTED_CELL_COUNT,
            "unsupported_exclusion_count": EXPECTED_EXCLUSION_COUNT,
        }
    if check_id == "cell-order-and-uniqueness":
        supported = _require_sha256(
            prior.get("supported_coordinate_set_content_sha256"),
            label="legacy supported coordinate-set identity",
        )
        unsupported = _require_sha256(
            prior.get("unsupported_coordinate_set_content_sha256"),
            label="legacy unsupported coordinate-set identity",
        )
        if supported != EXPECTED_SUPPORTED_COORDINATE_SET_SHA256:
            raise PipelineError("legacy supported coordinate-set identity is invalid")
        if unsupported != EXPECTED_UNSUPPORTED_COORDINATE_SET_SHA256:
            raise PipelineError("legacy unsupported coordinate-set identity is invalid")
        return prior
    if check_id == "independent-lifecycle-axes-cross-validated":
        admitted = _summary_count(summary, "admitted_cell_count")
        deferred = _summary_count(summary, "deferred_cell_count")
        logical_reuse = _summary_count(summary, "logical_reuse_cell_count")
        producer = _summary_count(summary, "producer_cell_count")
        if admitted != EXPECTED_ADMITTED_CELL_COUNT:
            raise PipelineError("matrix admitted cell count is invalid")
        if deferred != EXPECTED_DEFERRED_CELL_COUNT:
            raise PipelineError("matrix deferred cell count is invalid")
        if logical_reuse != EXPECTED_LOGICAL_REUSE_CELL_COUNT:
            raise PipelineError("matrix logical-reuse cell count is invalid")
        if producer != EXPECTED_PRODUCER_CELL_COUNT:
            raise PipelineError("matrix producer cell count is invalid")
        return {
            "admitted_cell_count": admitted,
            "allowed_target_changes": [],
            "deferred_cell_count": deferred,
            "lifecycle_change_scope": [],
            "logical_reuse_cell_count": logical_reuse,
            "non_target_supported_exact_count": EXPECTED_SUPPORTED_CELL_COUNT,
            "preserved_2048_cell_count": EXPECTED_2048_CELL_COUNT,
            "preserved_vemulator_main_cell_count": (
                EXPECTED_VEMULATOR_MAIN_CELL_COUNT
            ),
            "producer_cell_count": producer,
            "target_cell_count": 0,
            "unchanged_exclusion_count": EXPECTED_EXCLUSION_COUNT,
        }
    if check_id == "host-reproduction-proof-required-for-test":
        evidence_pin_count = _summary_count(summary, "evidence_pin_count")
        host_validated_cell_count = _summary_count(summary, "admitted_cell_count")
        if evidence_pin_count != EXPECTED_EVIDENCE_PIN_COUNT:
            raise PipelineError("matrix evidence pin count is invalid")
        if host_validated_cell_count != EXPECTED_HOST_VALIDATED_CELL_COUNT:
            raise PipelineError("matrix host-validated cell count is invalid")
        return {
            "evidence_pin_count": evidence_pin_count,
            "host_validated_cell_count": host_validated_cell_count,
        }
    if check_id == "source-order-lineage-and-outliers-validated":
        outliers = prior.get("authorized_outlier_count")
        parent_bindings = prior.get("parent_binding_count")
        if type(outliers) is not int or outliers != 0:
            raise PipelineError("legacy authorized outlier count is invalid")
        if type(parent_bindings) is not int or (
            parent_bindings != EXPECTED_PARENT_BINDING_COUNT
        ):
            raise PipelineError("legacy parent binding count is invalid")
        return prior
    if check_id == "branch-artifacts-observational-only":
        if prior.get("byte_match_required") is not False:
            raise PipelineError("legacy byte-match policy is invalid")
        if prior.get("version_alignment_model") != EXPECTED_VERSION_ALIGNMENT_MODEL:
            raise PipelineError("legacy version-alignment model is invalid")
        return prior
    if check_id == "per-cell-and-root-semantic-hash-projections":
        if prior.get("algorithm") != EXPECTED_PER_CELL_HASH_ALGORITHM:
            raise PipelineError("legacy per-cell hash algorithm is invalid")
        if prior.get("serialization") != EXPECTED_PER_CELL_HASH_SERIALIZATION:
            raise PipelineError("legacy per-cell serialization is invalid")
        return prior
    if check_id == "json-schema-draft-2020-12":
        schema_path = prior.get("schema_path")
        if schema_path != EXPECTED_SCHEMA_PATH:
            raise PipelineError("legacy schema_path detail is invalid")
        return prior
    if check_id == "deterministic-double-render":
        if prior.get("comparison") != EXPECTED_DOUBLE_RENDER_COMPARISON:
            raise PipelineError("legacy double-render comparison is invalid")
        return prior
    raise PipelineError(f"unsupported legacy check ID: {check_id}")


def _validation_ledger(
    predecessor: dict[str, object],
    *,
    spec_ref: EvidenceRef,
    predecessor_ref: EvidenceRef,
    phase_freeze_ref: EvidenceRef,
    engine_bundle_ref: EvidenceRef,
    engine_bundle: dict[str, object],
    pipeline_source: dict[str, object],
    freeze_authority: dict[str, object],
) -> dict[str, object]:
    _ledger, checks = _require_legacy_ledger_template(
        predecessor.get("validation_ledger")
    )
    rebuilt: list[dict[str, object]] = []
    engine_files = _require_exact_mapping(
        engine_bundle.get("files"),
        label="engine bundle files",
    )
    engine_member_sha256 = _require_sha256(
        engine_files.get(TRANSITION_MEMBER_PATH),
        label="engine transition.py member",
    )
    for check in checks:
        check_id = check["check_id"]
        if type(check_id) is not str:
            raise PipelineError("legacy validation check ID is invalid")
        prior_details = check["details"]
        if type(prior_details) is not dict:
            raise PipelineError("legacy validation check details are invalid")
        rebuilt.append(
            {
                "check_id": check_id,
                "details": _legacy_details(
                    check_id=check_id,
                    predecessor=predecessor,
                    spec_ref=spec_ref,
                    predecessor_ref=predecessor_ref,
                    phase_freeze_ref=phase_freeze_ref,
                    engine_bundle_ref=engine_bundle_ref,
                    engine_member_sha256=engine_member_sha256,
                    pipeline_source=pipeline_source,
                    freeze_authority=freeze_authority,
                    prior_details=prior_details,
                ),
                "status": "passed",
            }
        )
    result: dict[str, object] = {
        "check_count": len(rebuilt),
        "checks": rebuilt,
        "status": "passed",
    }
    _require_legacy_ledger_template(result)
    return result


def _supersedes(
    predecessor: dict[str, object],
    *,
    predecessor_ref: EvidenceRef,
    predecessor_raw: bytes,
) -> dict[str, object]:
    _require_exact_mapping(
        predecessor.get("supersedes"),
        label="predecessor supersedes",
        keys=_SUPERSEDES_KEYS,
    )
    semantic = predecessor_ref.target_content_sha256
    semantic = _require_sha256(semantic, label="predecessor semantic identity")
    raw_sha256 = predecessor_ref.file_sha256
    return {
        "path": predecessor_ref.path,
        "format": MATRIX_FORMAT,
        "content_sha256": semantic,
        "file_sha256": raw_sha256,
        "bytes": len(predecessor_raw),
        "lines": _line_count(predecessor_raw),
        "snapshot_path": (
            ".local-e2e/campaigns/host-core-build-20260810/matrices/"
            f"{semantic}.json"
        ),
        "cas_path": (
            ".local-e2e/store/campaign-matrices/sha256/"
            f"{raw_sha256[:2]}/{raw_sha256}"
        ),
        "reason": EXPECTED_SUPERSEDES_REASON,
    }


def _candidate_inputs(
    candidate: dict[str, object],
    *,
    spec: TransitionSpec,
    engine_bundle: dict[str, object],
    pipeline_source: dict[str, object],
) -> None:
    inputs = _require_exact_mapping(candidate.get("inputs"), label="matrix inputs")
    _require_exact_mapping(
        inputs.get("generator"),
        label="predecessor generator input",
        keys=_GENERATOR_INPUT_KEYS,
    )
    _require_exact_mapping(
        inputs.get("phase_freeze"),
        label="predecessor phase freeze input",
        keys=_PHASE_FREEZE_INPUT_KEYS,
    )
    _require_exact_mapping(
        inputs.get("pipeline_bundle"),
        label="predecessor pipeline bundle input",
        keys=_PIPELINE_INPUT_KEYS,
    )
    engine_files = _require_exact_mapping(
        engine_bundle.get("files"),
        label="engine bundle files",
    )
    pipeline_files = _require_exact_mapping(
        pipeline_source.get("files"),
        label="phase freeze pipeline files",
    )
    inputs["generator"] = {
        "path": TRANSITION_MEMBER_PATH,
        "file_sha256": engine_files[TRANSITION_MEMBER_PATH],
    }
    inputs["phase_freeze"] = {
        "path": spec.phase_freeze.path,
        "content_sha256": spec.phase_freeze.target_content_sha256,
        "file_sha256": spec.phase_freeze.file_sha256,
    }
    inputs["pipeline_bundle"] = {
        "schema_version": 1,
        "file_count": len(pipeline_files),
        "content_sha256": pipeline_source["content_sha256"],
        "source_phase_freeze_content_sha256": (
            spec.phase_freeze.target_content_sha256
        ),
    }


def _pipeline_bundle_reference(
    freeze_reference: EvidenceRef,
    pipeline_source: dict[str, object],
) -> EvidenceRef:
    target = _require_sha256(
        pipeline_source.get("content_sha256"),
        label="pipeline source content_sha256",
    )
    return EvidenceRef(
        kind="pipeline-bundle",
        path=freeze_reference.path,
        file_sha256=freeze_reference.file_sha256,
        target_content_sha256=target,
        size=freeze_reference.size,
    )


def _successor_reference(candidate_raw: bytes, content_sha256: str) -> EvidenceRef:
    raw_sha256 = sha256_bytes(candidate_raw)
    return EvidenceRef(
        kind="matrix-snapshot",
        path=(
            ".local-e2e/campaign-state/objects/matrix-snapshot/sha256/"
            f"{raw_sha256[:2]}/{raw_sha256}"
        ),
        file_sha256=raw_sha256,
        target_content_sha256=content_sha256,
        size=len(candidate_raw),
    )


def legacy_matrix_predecessor_references(
    spec: TransitionSpec,
) -> tuple[EvidenceRef, EvidenceRef]:
    """Derive the two immutable aliases for the frozen predecessor pointer."""

    if type(spec) is not TransitionSpec:
        raise PipelineError("spec must be an exact TransitionSpec")
    predecessor = spec.predecessor
    if (
        spec.transition_id != EXPECTED_TRANSITION_ID
        or spec.campaign_id != EXPECTED_CAMPAIGN_ID
        or spec.reason != EXPECTED_SUPERSEDES_REASON
        or predecessor.path != EXPECTED_PREDECESSOR_PATH
        or spec.phase_freeze.path != EXPECTED_PHASE_FREEZE_PATH
    ):
        raise PipelineError("spec does not authorize the production predecessor")
    if predecessor.file_sha256 != EXPECTED_PREDECESSOR_FILE_SHA256:
        raise PipelineError("predecessor raw identity is not authorized")
    if (
        predecessor.target_content_sha256
        != EXPECTED_PREDECESSOR_CONTENT_SHA256
    ):
        raise PipelineError("predecessor semantic identity is not authorized")
    if predecessor.size != EXPECTED_PREDECESSOR_BYTES:
        raise PipelineError("predecessor byte size is not authorized")
    raw_sha256 = predecessor.file_sha256
    semantic_sha256 = predecessor.target_content_sha256
    common = {
        "file_sha256": raw_sha256,
        "target_content_sha256": semantic_sha256,
        "size": predecessor.size,
    }
    snapshot = EvidenceRef(
        kind="matrix-snapshot",
        path=(
            ".local-e2e/campaigns/host-core-build-20260810/matrices/"
            f"{semantic_sha256}.json"
        ),
        **common,
    )
    raw_cas = EvidenceRef(
        kind="matrix-cas",
        path=(
            ".local-e2e/store/campaign-matrices/sha256/"
            f"{raw_sha256[:2]}/{raw_sha256}"
        ),
        **common,
    )
    return snapshot, raw_cas


def legacy_matrix_compatibility_references(
    result: PlannedMatrixAuthorityRefresh,
) -> tuple[EvidenceRef, EvidenceRef]:
    """Derive immutable legacy snapshot/CAS refs without writing either path.

    These aliases remain outside the candidate and plan identities because the
    raw-CAS digest cannot be embedded in the bytes it hashes.  After full
    transition validation, the H3 executor passes both references to
    ``CampaignStore.create_or_verify_reference``.  Only the store transaction
    may replace the mutable matrix pointer.
    """

    if type(result) is not PlannedMatrixAuthorityRefresh:
        raise PipelineError("result must be an exact PlannedMatrixAuthorityRefresh")
    candidate = decode_matrix_v2(result.candidate_raw)
    if render_matrix_v2(candidate) != result.candidate_raw:
        raise PipelineError("candidate matrix bytes are not the exact legacy rendering")
    content_sha256 = _require_outer_digest(candidate, label="candidate matrix")
    raw_sha256 = sha256_bytes(result.candidate_raw)
    if result.plan.successor != _successor_reference(
        result.candidate_raw,
        content_sha256,
    ):
        raise PipelineError("plan successor does not bind compatibility bytes")
    common = {
        "file_sha256": raw_sha256,
        "target_content_sha256": content_sha256,
        "size": len(result.candidate_raw),
    }
    snapshot = EvidenceRef(
        kind="matrix-snapshot",
        path=(
            ".local-e2e/campaigns/host-core-build-20260810/matrices/"
            f"{content_sha256}.json"
        ),
        **common,
    )
    raw_cas = EvidenceRef(
        kind="matrix-cas",
        path=(
            ".local-e2e/store/campaign-matrices/sha256/"
            f"{raw_sha256[:2]}/{raw_sha256}"
        ),
        **common,
    )
    return snapshot, raw_cas


def legacy_matrix_pointer_reference(
    spec: TransitionSpec,
    result: PlannedMatrixAuthorityRefresh,
) -> EvidenceRef:
    """Derive the mutable successor pointer identity at the authorized path."""

    if type(spec) is not TransitionSpec:
        raise PipelineError("spec must be an exact TransitionSpec")
    if type(result) is not PlannedMatrixAuthorityRefresh:
        raise PipelineError("result must be an exact PlannedMatrixAuthorityRefresh")
    # Reuse the frozen predecessor policy before deriving a mutable successor
    # pointer at that same reviewed path.
    legacy_matrix_predecessor_references(spec)
    if canonical_json_bytes(result.plan.predecessor.to_document()) != canonical_json_bytes(
        spec.predecessor.to_document()
    ):
        raise PipelineError("plan predecessor does not match the pointer authority")
    # This also reauthenticates the exact rendering, outer digest, and plan
    # successor before any mutable pointer reference is exposed.
    snapshot, _raw_cas = legacy_matrix_compatibility_references(result)
    return EvidenceRef(
        kind="matrix-pointer",
        path=spec.predecessor.path,
        file_sha256=snapshot.file_sha256,
        target_content_sha256=snapshot.target_content_sha256,
        size=snapshot.size,
    )


def _require_candidate_envelope(document: dict[str, object]) -> None:
    if document.get("format") != MATRIX_FORMAT:
        raise PipelineError("candidate matrix format is invalid")
    if type(document.get("captured_at")) is not str or not document.get("captured_at"):
        raise PipelineError("candidate matrix captured_at is invalid")
    if document.get("local_only") is not True:
        raise PipelineError("candidate matrix must remain local-only")
    if document.get("publication") != "disabled":
        raise PipelineError("candidate matrix publication must remain disabled")


def _authenticate_planner_inputs(
    *,
    spec: object,
    spec_ref: object,
    predecessor_raw: object,
    phase_freeze_raw: object,
    engine_bundle_ref: object,
    engine_bundle_document: object,
) -> tuple[
    TransitionSpec,
    EvidenceRef,
    bytes,
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    EvidenceRef,
    dict[str, object],
]:
    if type(spec) is not TransitionSpec:
        raise PipelineError("spec must be an exact TransitionSpec")
    if spec.transition_id != EXPECTED_TRANSITION_ID:
        raise PipelineError("transition ID is not authorized")
    if spec.campaign_id != EXPECTED_CAMPAIGN_ID:
        raise PipelineError("campaign ID is not authorized")
    if spec.reason != EXPECTED_SUPERSEDES_REASON:
        raise PipelineError("transition spec reason is not the reviewed reason")
    if spec.predecessor.path != EXPECTED_PREDECESSOR_PATH:
        raise PipelineError("transition predecessor path is not authorized")
    if spec.phase_freeze.path != EXPECTED_PHASE_FREEZE_PATH:
        raise PipelineError("transition phase-freeze path is not authorized")
    if type(spec_ref) is not EvidenceRef:
        raise PipelineError("spec_ref must be an exact EvidenceRef")
    if spec_ref.path != EXPECTED_SPEC_PATH:
        raise PipelineError("transition spec reference path is not authorized")
    spec_raw = rendered_json_bytes(spec.to_document())
    _require_reference_binding(
        spec_ref,
        spec_raw,
        kind="transition-spec",
        target_content_sha256=spec.content_sha256,
        label="transition spec reference",
    )
    predecessor_raw, predecessor = _require_predecessor(
        predecessor_raw,
        spec.predecessor,
    )
    if type(phase_freeze_raw) is not bytes:
        raise PipelineError("phase_freeze_raw must be exact bytes")
    freeze, pipeline_source, freeze_authority = _require_phase_freeze(
        phase_freeze_raw,
        spec.phase_freeze,
    )
    engine_bundle_ref, engine_bundle = _require_engine_bundle(
        engine_bundle_ref,
        engine_bundle_document,
    )
    return (
        spec,
        spec_ref,
        predecessor_raw,
        predecessor,
        freeze,
        pipeline_source,
        freeze_authority,
        engine_bundle_ref,
        engine_bundle,
    )


def plan_matrix_authority_refresh(
    *,
    spec: TransitionSpec,
    spec_ref: EvidenceRef,
    predecessor_raw: bytes,
    phase_freeze_raw: bytes,
    engine_bundle_ref: EvidenceRef,
    engine_bundle_document: object,
) -> PlannedMatrixAuthorityRefresh:
    """Plan the exact authority-only matrix successor without writing state."""

    (
        spec,
        spec_ref,
        predecessor_raw,
        predecessor,
        _freeze,
        pipeline_source,
        freeze_authority,
        engine_bundle_ref,
        engine_bundle,
    ) = _authenticate_planner_inputs(
        spec=spec,
        spec_ref=spec_ref,
        predecessor_raw=predecessor_raw,
        phase_freeze_raw=phase_freeze_raw,
        engine_bundle_ref=engine_bundle_ref,
        engine_bundle_document=engine_bundle_document,
    )
    _require_candidate_envelope(predecessor)
    preserved = _preserved_facts(predecessor)

    candidate_value = project_without_pointers(predecessor, ())
    if type(candidate_value) is not dict:
        raise PipelineError("detached predecessor projection is not a mapping")
    candidate: dict[str, object] = candidate_value
    candidate["captured_at"] = spec.captured_at
    _candidate_inputs(
        candidate,
        spec=spec,
        engine_bundle=engine_bundle,
        pipeline_source=pipeline_source,
    )
    candidate["supersedes"] = _supersedes(
        predecessor,
        predecessor_ref=spec.predecessor,
        predecessor_raw=predecessor_raw,
    )
    candidate["validation_ledger"] = _validation_ledger(
        predecessor,
        spec_ref=spec_ref,
        predecessor_ref=spec.predecessor,
        phase_freeze_ref=spec.phase_freeze,
        engine_bundle_ref=engine_bundle_ref,
        engine_bundle=engine_bundle,
        pipeline_source=pipeline_source,
        freeze_authority=freeze_authority,
    )
    candidate["content_sha256"] = matrix_v2_semantic_sha256(candidate)
    _require_candidate_envelope(candidate)

    changed_pointers = require_exact_pointer_delta(
        predecessor,
        candidate,
        allowed_pointers=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        required_pointers=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        canonical_bytes=matrix_v2_canonical_bytes,
        expected_projection_sha256=EXPECTED_PRESERVED_PROJECTION_SHA256,
    )
    if _preserved_facts(candidate) != preserved:
        raise PipelineError("candidate preserved facts differ from predecessor")

    candidate_raw = render_matrix_v2(candidate)
    if render_matrix_v2(candidate) != candidate_raw:
        raise PipelineError("candidate matrix double-render is not deterministic")
    round_trip = decode_matrix_v2(candidate_raw)
    if render_matrix_v2(round_trip) != candidate_raw:
        raise PipelineError("candidate matrix render round-trip is not exact")
    content_sha256 = _require_outer_digest(round_trip, label="candidate matrix")
    successor = _successor_reference(candidate_raw, content_sha256)
    pipeline_bundle_ref = _pipeline_bundle_reference(
        spec.phase_freeze,
        pipeline_source,
    )
    plan = TransitionPlan(
        transition_id=spec.transition_id,
        campaign_id=spec.campaign_id,
        kind=spec.kind,
        captured_at=spec.captured_at,
        reason=spec.reason,
        spec=spec_ref,
        engine_bundle=engine_bundle_ref,
        predecessor=spec.predecessor,
        phase_freeze=spec.phase_freeze,
        pipeline_bundle=pipeline_bundle_ref,
        successor=successor,
        allowed_changes=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        preserved_projection_sha256=EXPECTED_PRESERVED_PROJECTION_SHA256,
        required_checks=MATRIX_AUTHORITY_REQUIRED_CHECKS,
    )
    validate_spec_plan(spec, plan)
    return PlannedMatrixAuthorityRefresh(
        plan=plan,
        candidate_raw=candidate_raw,
        changed_pointers=changed_pointers,
    )


def _require_same_plan(actual: TransitionPlan, expected: TransitionPlan) -> None:
    if canonical_json_bytes(actual.to_document()) != canonical_json_bytes(
        expected.to_document()
    ):
        raise PipelineError("matrix authority plan does not match reconstruction")


def _require_local_json_schema(
    candidate: dict[str, object],
    schema_raw: object,
) -> None:
    if type(schema_raw) is not bytes:
        raise PipelineError("matrix schema input must be exact bytes")
    if sha256_bytes(schema_raw) != EXPECTED_SCHEMA_FILE_SHA256:
        raise PipelineError("matrix schema raw identity is not authorized")
    if len(schema_raw) != EXPECTED_SCHEMA_BYTES:
        raise PipelineError("matrix schema byte size is not authorized")
    if _line_count(schema_raw) != EXPECTED_SCHEMA_LINES:
        raise PipelineError("matrix schema line identity is not authorized")
    schema = decode_matrix_v2(schema_raw)
    canonical_sha256 = sha256_bytes(matrix_v2_canonical_bytes(schema))
    if canonical_sha256 != EXPECTED_SCHEMA_CANONICAL_SHA256:
        raise PipelineError("matrix schema canonical identity is not authorized")
    if schema.get("$schema") != EXPECTED_SCHEMA_DRAFT:
        raise PipelineError("matrix schema must declare exact JSON Schema draft 2020-12")

    def reject_remote_references(value: object) -> None:
        if type(value) is dict:
            for key, item in value.items():
                if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                    type(item) is not str or not item.startswith("#")
                ):
                    raise PipelineError("matrix schema must not use remote references")
                reject_remote_references(item)
        elif type(value) is list:
            for item in value:
                reject_remote_references(item)

    reject_remote_references(schema)
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        raise PipelineError("jsonschema is required for matrix validation") from exc
    try:
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        first_error = next(iter(validator.iter_errors(candidate)), None)
    except SchemaError as exc:
        raise PipelineError(f"matrix schema is invalid: {exc.message}") from exc
    except Exception as exc:
        raise PipelineError(f"matrix schema validation failed closed: {exc}") from exc
    if first_error is not None:
        path = "/".join(str(part) for part in first_error.absolute_path)
        raise PipelineError(
            f"candidate matrix fails schema at /{path}: {first_error.message}"
        )


def validate_matrix_authority_refresh(
    result: PlannedMatrixAuthorityRefresh,
    *,
    spec: TransitionSpec,
    spec_ref: EvidenceRef,
    predecessor_raw: bytes,
    phase_freeze_raw: bytes,
    engine_bundle_ref: EvidenceRef,
    engine_bundle_document: object,
    schema_raw: bytes,
) -> None:
    """Reconstruct and deeply validate one planned authority refresh."""

    if type(result) is not PlannedMatrixAuthorityRefresh:
        raise PipelineError("result must be an exact PlannedMatrixAuthorityRefresh")
    expected = plan_matrix_authority_refresh(
        spec=spec,
        spec_ref=spec_ref,
        predecessor_raw=predecessor_raw,
        phase_freeze_raw=phase_freeze_raw,
        engine_bundle_ref=engine_bundle_ref,
        engine_bundle_document=engine_bundle_document,
    )
    _require_same_plan(result.plan, expected.plan)
    if result.candidate_raw != expected.candidate_raw:
        raise PipelineError("candidate matrix bytes do not match reconstruction")
    if result.changed_pointers != expected.changed_pointers:
        raise PipelineError("candidate changed pointers do not match reconstruction")

    predecessor_snapshot, predecessor_raw_cas = (
        legacy_matrix_predecessor_references(spec)
    )
    for reference in (predecessor_snapshot, predecessor_raw_cas):
        if (
            reference.file_sha256 != result.plan.predecessor.file_sha256
            or reference.target_content_sha256
            != result.plan.predecessor.target_content_sha256
            or reference.size != result.plan.predecessor.size
        ):
            raise PipelineError("legacy predecessor reference identity is invalid")

    predecessor = decode_matrix_v2(predecessor_raw)
    candidate = decode_matrix_v2(result.candidate_raw)
    if render_matrix_v2(candidate) != result.candidate_raw:
        raise PipelineError("candidate matrix bytes are not the exact legacy rendering")
    candidate_content = _require_outer_digest(candidate, label="candidate matrix")
    if result.plan.successor != _successor_reference(
        result.candidate_raw,
        candidate_content,
    ):
        raise PipelineError("plan successor does not bind the candidate matrix")
    legacy_snapshot, legacy_raw_cas = legacy_matrix_compatibility_references(result)
    pointer_successor = legacy_matrix_pointer_reference(spec, result)
    for reference in (legacy_snapshot, legacy_raw_cas):
        if (
            reference.file_sha256 != result.plan.successor.file_sha256
            or reference.target_content_sha256
            != result.plan.successor.target_content_sha256
            or reference.size != result.plan.successor.size
        ):
            raise PipelineError("legacy compatibility reference identity is invalid")
    if (
        pointer_successor.path != spec.predecessor.path
        or pointer_successor.file_sha256 != result.plan.successor.file_sha256
        or pointer_successor.target_content_sha256
        != result.plan.successor.target_content_sha256
        or pointer_successor.size != result.plan.successor.size
    ):
        raise PipelineError("matrix pointer successor identity is invalid")
    changed = require_exact_pointer_delta(
        predecessor,
        candidate,
        allowed_pointers=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        required_pointers=MATRIX_AUTHORITY_ALLOWED_CHANGES,
        canonical_bytes=matrix_v2_canonical_bytes,
        expected_projection_sha256=EXPECTED_PRESERVED_PROJECTION_SHA256,
    )
    if changed != result.changed_pointers:
        raise PipelineError("validated candidate pointer delta is inconsistent")
    before_preserved = _preserved_facts(predecessor)
    if _preserved_facts(candidate) != before_preserved:
        raise PipelineError("validated candidate preservation facts differ")
    _require_candidate_envelope(candidate)
    _require_local_json_schema(candidate, schema_raw)
    validate_spec_plan(spec, result.plan)


__all__ = (
    "PlannedMatrixAuthorityRefresh",
    "legacy_matrix_compatibility_references",
    "legacy_matrix_predecessor_references",
    "legacy_matrix_pointer_reference",
    "plan_matrix_authority_refresh",
    "validate_matrix_authority_refresh",
)
