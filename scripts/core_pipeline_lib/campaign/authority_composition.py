"""Read-only repository composition for the first combined H5/H6 stage.

This adapter selects no mutable authority and performs no durable write.  The
caller supplies the exact historical H3 StateRoot and normalized H6 root; the
adapter reauthenticates those records, captures the live repository inputs,
constructs the maintained Gambatte inventories, and returns the exact keyword
arguments consumed by :func:`plan_repository_authority_stage`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Final

from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..immutable_evidence import canonical_store_path
from ..pin_lifecycle import (
    PinLifecycleServices,
    core_track_source_ancestry_verifier,
    load_authoritative_core_pin_index,
)
from ..source_bundle import (
    REPOSITORY_SOURCE_MODE,
    RepositorySourceCapture,
    RepositorySourceFileSet,
    RepositorySourceMember,
    capture_repository_sources,
)
from ..tracks import (
    CORE_TRACK_SOURCE_SNAPSHOT_ROOT,
    canonical_group_tag,
    construct_core_track_inventory,
    load_core_track_source_registry_index,
    parse_group_tag,
)
from .authority_staging import (
    AuthorityCopyPayloadV1,
    AuthorityCopyV1,
    DirectoryReplayV1,
    EvidenceReplayV1,
    MatrixCellReplayV1,
    MatrixRefreshReplayV1,
    replay_matrix_refresh,
)
from .json_wire import decode_identity_object, rendered_json_bytes
from .legacy_matrix_v2 import decode_matrix_v2
from .matrix_materialize import (
    NormalizedMatrixV1,
    materialize_matrix_v2,
    normalize_matrix_v2,
    validate_normalized_matrix,
)
from .matrix_model import (
    EXPECTED_CORE_COUNT,
    MatrixCoordinateV1,
    coordinate_for_ordinal,
)
from .matrix_refresh import (
    DirectoryFingerprintV1,
    HydratedArtifactV1,
    canonical_track_inventory_producer_v1,
)
from .matrix_store import load_normalized_matrix
from .model import EvidenceRef, StateRoot
from .phase_freeze import CAMPAIGN_STATE_RELATIVE
from .phase_freeze_bootstrap import (
    CAMPAIGN_ID,
    DEFAULT_TRANSITION_ID,
    PlannedRepositoryPhaseFreezeBootstrap,
    plan_repository_phase_freeze_bootstrap,
)
from .store import CampaignStore
from .transition_model import AuthenticatedInput


CORE_ID: Final = "gambatte"
MATRIX_POINTER_PATH: Final = (
    ".local-e2e/campaigns/host-core-build-20260810/campaign-matrix.json"
)
MATRIX_GENERATOR_PATH: Final = (
    "scripts/core_pipeline_lib/campaign/matrix_refresh.py"
)
PIN_DIRECTORY_PATH: Final = "pins/core-sets"
TRACK_SNAPSHOT_DIRECTORY_PATH: Final = CORE_TRACK_SOURCE_SNAPSHOT_ROOT.as_posix()
LOCAL_STORE_PATH: Final = ".local-e2e/store"

_AUTHORITY_INPUT_ROLES: Final = (
    "catalog",
    "spruce-branch-bases",
    "spruce-release-roster",
    "telemetry-schema",
    "tracks",
    "tunings",
)
_ARCHITECTURES: Final = ("arm64", "armhf")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedRepositoryAuthorityCompositionV1:
    """Exact in-memory arguments for the pointer-free authority-stage planner."""

    phase_bootstrap: PlannedRepositoryPhaseFreezeBootstrap
    current_state_root_ref: EvidenceRef
    expected_pointer: EvidenceRef
    predecessor_matrix: NormalizedMatrixV1
    successor_matrix: NormalizedMatrixV1
    matrix_replay: MatrixRefreshReplayV1
    matrix_members: tuple[AuthenticatedInput, ...]

    def __post_init__(self) -> None:
        if type(self.phase_bootstrap) is not PlannedRepositoryPhaseFreezeBootstrap:
            raise PipelineError("authority composition phase bootstrap is invalid")
        if (
            type(self.current_state_root_ref) is not EvidenceRef
            or self.current_state_root_ref.kind != "state-root"
        ):
            raise PipelineError("authority composition StateRoot is invalid")
        if (
            type(self.expected_pointer) is not EvidenceRef
            or self.expected_pointer.kind != "matrix-pointer"
        ):
            raise PipelineError("authority composition matrix pointer is invalid")
        if type(self.predecessor_matrix) is not NormalizedMatrixV1 or type(
            self.successor_matrix
        ) is not NormalizedMatrixV1:
            raise PipelineError("authority composition matrices are invalid")
        validate_normalized_matrix(self.predecessor_matrix)
        validate_normalized_matrix(self.successor_matrix)
        if type(self.matrix_replay) is not MatrixRefreshReplayV1:
            raise PipelineError("authority composition replay is invalid")
        if (
            self.matrix_replay.transition_id
            != self.phase_bootstrap.result.plan.transition_id
        ):
            raise PipelineError("authority composition transition identities differ")
        if (
            self.successor_matrix.root.phase_freeze
            != self.phase_bootstrap.result.plan.successor
        ):
            raise PipelineError("authority composition successor phase is stale")
        if type(self.matrix_members) is not tuple or any(
            type(item) is not AuthenticatedInput for item in self.matrix_members
        ):
            raise PipelineError("authority composition matrix members are invalid")
        names = tuple(item.name for item in self.matrix_members)
        if names != tuple(sorted(names)) or len(names) != len(set(names)):
            raise PipelineError(
                "authority composition matrix members must be sorted and unique"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class _FileBinding:
    path: str
    file_sha256: str

    def __post_init__(self) -> None:
        if type(self.path) is not str or not self.path:
            raise PipelineError("authority evidence path is invalid")
        if (
            type(self.file_sha256) is not str
            or _SHA256_RE.fullmatch(self.file_sha256) is None
        ):
            raise PipelineError("authority evidence file identity is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class _EvidenceSeed:
    pin: _FileBinding
    golden: _FileBinding
    selected_e2e: _FileBinding
    reproduction_e2e: _FileBinding
    telemetry_schema: _FileBinding


@dataclass(frozen=True, slots=True, kw_only=True)
class _EvidenceClosure:
    seed: _EvidenceSeed
    selected_telemetry: _FileBinding
    reproduction_telemetry: _FileBinding
    selected_build_records: tuple[tuple[str, _FileBinding], ...]
    reproduction_build_records: tuple[tuple[str, _FileBinding], ...]

    def __post_init__(self) -> None:
        for label, values in (
            ("selected", self.selected_build_records),
            ("reproduction", self.reproduction_build_records),
        ):
            architectures = tuple(item[0] for item in values)
            if architectures != _ARCHITECTURES or any(
                type(item[1]) is not _FileBinding for item in values
            ):
                raise PipelineError(
                    f"{label} evidence build records do not cover both ABIs"
                )

    @property
    def bindings(self) -> tuple[_FileBinding, ...]:
        return (
            self.seed.pin,
            self.seed.golden,
            self.seed.selected_e2e,
            self.seed.reproduction_e2e,
            self.selected_telemetry,
            self.reproduction_telemetry,
            *(item[1] for item in self.selected_build_records),
            *(item[1] for item in self.reproduction_build_records),
            self.seed.telemetry_schema,
        )


def _require_store(value: object) -> CampaignStore:
    if not isinstance(value, CampaignStore) or (
        value.state_relative != CAMPAIGN_STATE_RELATIVE
    ):
        raise PipelineError("authority composition requires the campaign store")
    return value


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
    return value


def _file_binding(value: object, *, label: str) -> _FileBinding:
    document = _require_mapping(value, label=label)
    digest = document.get("file_sha256", document.get("sha256"))
    return _FileBinding(
        path=_require_string(document.get("path"), label=f"{label} path"),
        file_sha256=_require_string(digest, label=f"{label} file_sha256"),
    )


def _member_map(
    capture: RepositorySourceCapture,
) -> dict[str, RepositorySourceMember]:
    return {item.path: item for item in capture.members}


def _source_member(
    members: Mapping[str, RepositorySourceMember],
    path: str,
    *,
    label: str,
) -> RepositorySourceMember:
    try:
        return members[path]
    except KeyError as exc:
        raise PipelineError(f"{label} is absent from the source capture") from exc


def _capture_sources(
    repository_root: Path,
    *,
    exact_paths: tuple[str, ...],
) -> RepositorySourceCapture:
    if exact_paths != tuple(sorted(set(exact_paths))):
        raise PipelineError("authority capture exact paths must be sorted and unique")
    return capture_repository_sources(
        repository_root=repository_root,
        exact_file_modes={path: REPOSITORY_SOURCE_MODE for path in exact_paths},
        file_sets=(
            RepositorySourceFileSet(
                root=PIN_DIRECTORY_PATH,
                suffixes=(".json",),
                recursive=False,
                label="core pin directory",
            ),
            RepositorySourceFileSet(
                root=TRACK_SNAPSHOT_DIRECTORY_PATH,
                suffixes=(".json",),
                recursive=False,
                label="core track snapshot directory",
            ),
        ),
    )


def _require_capture_extension(
    earlier: RepositorySourceCapture,
    later: RepositorySourceCapture,
) -> None:
    later_members = _member_map(later)
    for member in earlier.members:
        if later_members.get(member.path) != member:
            raise PipelineError(
                f"repository authority moved during discovery: {member.path}"
            )
    later_directories = {item.path: item for item in later.directories}
    for directory in earlier.directories:
        if later_directories.get(directory.path) != directory:
            raise PipelineError(
                "repository authority path chain moved during discovery: "
                f"{directory.path}"
            )


def _phase_inputs(
    phase_bootstrap: PlannedRepositoryPhaseFreezeBootstrap,
) -> dict[str, AuthenticatedInput]:
    result = {item.name: item for item in phase_bootstrap.request.inputs}
    if len(result) != len(phase_bootstrap.request.inputs):
        raise PipelineError("phase bootstrap repeats an authority input")
    missing = sorted(set(_AUTHORITY_INPUT_ROLES) - set(result))
    if missing:
        raise PipelineError(
            "phase bootstrap lacks matrix authorities: " + ", ".join(missing)
        )
    return result


def _phase_overlap_paths(
    phase_bootstrap: PlannedRepositoryPhaseFreezeBootstrap,
) -> tuple[str, ...]:
    inputs = _phase_inputs(phase_bootstrap)
    return tuple(
        sorted(
            {
                MATRIX_GENERATOR_PATH,
                *(inputs[role].reference.path for role in _AUTHORITY_INPUT_ROLES),
            }
        )
    )


def _require_phase_overlap(
    phase_bootstrap: PlannedRepositoryPhaseFreezeBootstrap,
    capture: RepositorySourceCapture,
) -> None:
    phase_sources = {item.path: item for item in phase_bootstrap.source_members}
    captured = _member_map(capture)
    for path in _phase_overlap_paths(phase_bootstrap):
        phase_member = _source_member(
            phase_sources, path, label=f"phase source {path}"
        )
        if captured.get(path) != phase_member:
            raise PipelineError(f"H5/H6 repository capture differs for {path}")
    for role in _AUTHORITY_INPUT_ROLES:
        item = _phase_inputs(phase_bootstrap)[role]
        if phase_sources[item.reference.path].raw != item.raw:
            raise PipelineError(f"phase input source closure differs for {role}")


def _gambatte_pin_id(track_registry: Mapping[str, object]) -> str:
    tracks = _require_mapping(
        track_registry.get("tracks"), label="track registry tracks"
    )
    pin_ids: set[str] = set()
    for track_name, track_value in tracks.items():
        track = _require_mapping(track_value, label=f"track {track_name}")
        tests = _require_mapping(track.get("test"), label=f"track {track_name} TEST")
        core = tests.get(CORE_ID)
        if core is None:
            continue
        for cell_value in _require_mapping(
            core, label=f"track {track_name} {CORE_ID} TEST"
        ).values():
            cell = _require_mapping(cell_value, label=f"track {track_name} TEST cell")
            pin_ids.add(
                _require_string(
                    cell.get("build_pin_id"), label="Gambatte TEST build pin"
                )
            )
    if len(pin_ids) != 1:
        raise PipelineError("Gambatte TEST authority does not select one exact pin")
    return next(iter(pin_ids))


def _pin_seed(
    *,
    pin_entry: Mapping[str, object],
    pin_raw: bytes,
    telemetry_schema: AuthenticatedInput,
) -> _EvidenceSeed:
    pin_id = _require_string(pin_entry.get("pin_id"), label="Gambatte pin_id")
    pin = decode_identity_object(pin_raw, label="Gambatte pin")
    if pin.get("pin_id") != pin_id:
        raise PipelineError("Gambatte pin index and captured pin differ")
    cores = _require_mapping(pin.get("cores"), label="Gambatte pin cores")
    core = _require_mapping(cores.get(CORE_ID), label="Gambatte pin core")
    selection = _require_mapping(core.get("selection"), label="Gambatte selection")
    host = _require_mapping(
        selection.get("host_reproduction"), label="Gambatte host reproduction"
    )
    sources = _require_list(pin.get("sources"), label="Gambatte pin sources")
    golden_matches = [
        item
        for item in sources
        if type(item) is dict and item.get("pin_id") == pin_id
    ]
    if len(golden_matches) != 1:
        raise PipelineError("Gambatte pin does not bind one golden source")
    return _EvidenceSeed(
        pin=_FileBinding(
            path=_require_string(pin_entry.get("path"), label="Gambatte pin path"),
            file_sha256=_require_string(
                pin_entry.get("file_sha256"), label="Gambatte pin file_sha256"
            ),
        ),
        golden=_file_binding(golden_matches[0], label="Gambatte golden source"),
        selected_e2e=_file_binding(
            _require_mapping(host.get("selected"), label="selected host proof").get(
                "e2e_record"
            ),
            label="selected E2E",
        ),
        reproduction_e2e=_file_binding(
            _require_mapping(
                host.get("reproduction"), label="reproduction host proof"
            ).get("e2e_record"),
            label="reproduction E2E",
        ),
        telemetry_schema=_FileBinding(
            path=telemetry_schema.reference.path,
            file_sha256=telemetry_schema.reference.file_sha256,
        ),
    )


def _e2e_evidence(
    *,
    repository_root: Path,
    seed: _EvidenceSeed,
    members: Mapping[str, RepositorySourceMember],
) -> _EvidenceClosure:
    def role(
        binding: _FileBinding,
        *,
        label: str,
    ) -> tuple[_FileBinding, tuple[tuple[str, _FileBinding], ...]]:
        raw = _source_member(members, binding.path, label=label).raw
        if sha256_bytes(raw) != binding.file_sha256:
            raise PipelineError(f"{label} moved after its declaring pin")
        document = decode_identity_object(raw, label=label)
        runner = _require_mapping(document.get("runner"), label=f"{label} runner")
        telemetry = _file_binding(
            runner.get("telemetry"), label=f"{label} telemetry"
        )
        builds = _require_list(document.get("builds"), label=f"{label} builds")
        records: list[tuple[str, _FileBinding]] = []
        for architecture in _ARCHITECTURES:
            matches = [
                item
                for item in builds
                if type(item) is dict
                and item.get("core_id") == CORE_ID
                and item.get("architecture") == architecture
                and item.get("result") == "passed"
            ]
            if len(matches) != 1:
                raise PipelineError(
                    f"{label} does not contain one passed {architecture} build"
                )
            digest = _require_string(
                matches[0].get("record_sha256"),
                label=f"{label} {architecture} build record",
            )
            path = canonical_store_path(
                repository_root / LOCAL_STORE_PATH,
                "build-records",
                digest,
            ).relative_to(repository_root).as_posix()
            records.append(
                (architecture, _FileBinding(path=path, file_sha256=digest))
            )
        return telemetry, tuple(records)

    selected_telemetry, selected_records = role(
        seed.selected_e2e, label="selected E2E"
    )
    reproduction_telemetry, reproduction_records = role(
        seed.reproduction_e2e, label="reproduction E2E"
    )
    return _EvidenceClosure(
        seed=seed,
        selected_telemetry=selected_telemetry,
        reproduction_telemetry=reproduction_telemetry,
        selected_build_records=selected_records,
        reproduction_build_records=reproduction_records,
    )


def _captured_binding_paths(value: _EvidenceClosure) -> tuple[str, ...]:
    return tuple(sorted({item.path for item in value.bindings}))


def _require_evidence_bindings(
    evidence: _EvidenceClosure,
    members: Mapping[str, RepositorySourceMember],
) -> None:
    for binding in evidence.bindings:
        member = _source_member(
            members, binding.path, label=f"evidence {binding.path}"
        )
        if sha256_bytes(member.raw) != binding.file_sha256:
            raise PipelineError(f"evidence raw identity moved for {binding.path}")


def _require_pin_index(
    pin_index: Mapping[str, Mapping[str, object]],
    members: Mapping[str, RepositorySourceMember],
) -> None:
    indexed: dict[str, str] = {}
    for pin_id, value in pin_index.items():
        path = _require_string(value.get("path"), label=f"pin {pin_id} path")
        digest = _require_string(
            value.get("file_sha256"), label=f"pin {pin_id} file_sha256"
        )
        if path in indexed:
            raise PipelineError("pin index repeats a physical path")
        indexed[path] = digest
    captured = {
        path: member
        for path, member in members.items()
        if path.startswith(PIN_DIRECTORY_PATH + "/") and path.endswith(".json")
    }
    if set(indexed) != set(captured):
        raise PipelineError("pin index does not cover the captured pin directory")
    for path, digest in indexed.items():
        if sha256_bytes(captured[path].raw) != digest:
            raise PipelineError(f"pin index raw identity differs for {path}")


def _require_source_registry_index(
    index: Mapping[str, Mapping[str, object]],
    members: Mapping[str, RepositorySourceMember],
) -> None:
    indexed: dict[str, str] = {}
    for digest, value in index.items():
        if _SHA256_RE.fullmatch(digest) is None:
            raise PipelineError("source registry index key is invalid")
        path = _require_string(value.get("path"), label="source snapshot path")
        file_sha256 = _require_string(
            value.get("file_sha256"), label="source snapshot file_sha256"
        )
        if path in indexed:
            raise PipelineError("source registry index repeats a physical path")
        indexed[path] = file_sha256
    captured = {
        path: member
        for path, member in members.items()
        if path.startswith(TRACK_SNAPSHOT_DIRECTORY_PATH + "/")
        and path.endswith(".json")
    }
    if set(indexed) != set(captured):
        raise PipelineError(
            "source registry index does not cover the captured snapshot directory"
        )
    for path, digest in indexed.items():
        if sha256_bytes(captured[path].raw) != digest:
            raise PipelineError(
                f"source registry index raw identity differs for {path}"
            )


def _fingerprint(
    path: str,
    members: Mapping[str, RepositorySourceMember],
) -> DirectoryFingerprintV1:
    prefix = path + "/"
    files = tuple(
        HydratedArtifactV1(path=member.path, raw=member.raw)
        for member in sorted(members.values(), key=lambda item: item.path)
        if member.path.startswith(prefix) and member.path.endswith(".json")
    )
    if not files:
        raise PipelineError(f"captured directory is empty: {path}")
    return DirectoryFingerprintV1(path=path, files=files)


def _require_post_gambatte_pin_directory(
    predecessor: object,
    *,
    current: DirectoryFingerprintV1,
    gambatte_pin_path: str,
) -> None:
    if current.path != PIN_DIRECTORY_PATH:
        raise PipelineError("current pin directory path is invalid")
    prior = _require_mapping(
        predecessor, label="predecessor pin directory fingerprint"
    )
    if prior.get("path") != PIN_DIRECTORY_PATH:
        raise PipelineError("predecessor pin directory path is invalid")
    current_document = current.to_document()
    prior_entries = _require_list(
        prior.get("entries"), label="predecessor pin directory entries"
    )
    current_entries = _require_list(
        current_document.get("entries"), label="current pin directory entries"
    )

    def by_path(
        values: list[object], *, label: str
    ) -> dict[str, dict[str, object]]:
        result: dict[str, dict[str, object]] = {}
        for value in values:
            entry = _require_mapping(value, label=f"{label} entry")
            path = _require_string(entry.get("path"), label=f"{label} path")
            if path in result:
                raise PipelineError(f"{label} repeats a path")
            result[path] = entry
        return result

    prior_by_path = by_path(prior_entries, label="predecessor pin directory")
    current_by_path = by_path(current_entries, label="current pin directory")
    prefix = PIN_DIRECTORY_PATH + "/"
    if not gambatte_pin_path.startswith(prefix):
        raise PipelineError("Gambatte pin is outside the authoritative directory")
    added_path = gambatte_pin_path.removeprefix(prefix)
    if not added_path or "/" in added_path:
        raise PipelineError("Gambatte pin is outside the authoritative directory")
    if set(current_by_path) - set(prior_by_path) != {added_path} or set(
        prior_by_path
    ) - set(current_by_path):
        raise PipelineError(
            "post-Gambatte pin directory is not the exact one-pin extension"
        )
    for path, entry in prior_by_path.items():
        if current_by_path[path] != entry:
            raise PipelineError(f"predecessor pin entry moved: {path}")


def _require_unchanged_track_snapshot_directory(
    predecessor: object,
    *,
    current: DirectoryFingerprintV1,
) -> None:
    if predecessor != current.to_document():
        raise PipelineError(
            "track snapshot directory moved from the selected predecessor"
        )


def _authenticate_predecessor(
    store: CampaignStore,
    *,
    predecessor_matrix_root_ref: EvidenceRef,
    pointer_member: RepositorySourceMember,
) -> tuple[NormalizedMatrixV1, EvidenceRef]:
    predecessor = load_normalized_matrix(store, predecessor_matrix_root_ref)
    pointer = EvidenceRef(
        kind="matrix-pointer",
        path=MATRIX_POINTER_PATH,
        file_sha256=sha256_bytes(pointer_member.raw),
        target_content_sha256=predecessor.root.legacy_matrix.semantic_sha256,
        size=len(pointer_member.raw),
    )
    normalized = normalize_matrix_v2(
        pointer_member.raw,
        phase_freeze=predecessor.root.phase_freeze,
        core_spec_set=predecessor.root.core_spec_set,
    )
    if normalized != predecessor or (
        materialize_matrix_v2(predecessor) != pointer_member.raw
    ):
        raise PipelineError(
            "live matrix pointer differs from the selected normalized predecessor"
        )
    return predecessor, pointer


def _authenticate_current_root(
    store: CampaignStore,
    *,
    reference: EvidenceRef,
    pointer: EvidenceRef,
) -> StateRoot:
    if type(reference) is not EvidenceRef or reference.kind != "state-root":
        raise PipelineError("current StateRoot reference is invalid")
    raw = store.read_exact(reference)
    value = StateRoot.from_document(
        decode_identity_object(raw, label="current StateRoot")
    )
    if rendered_json_bytes(value.to_document()) != raw or store.reference_for(
        kind="state-root",
        raw=raw,
        target_content_sha256=value.content_sha256,
    ) != reference:
        raise PipelineError("current StateRoot reference is not canonical")
    # H3 selected the canonical matrix snapshot while H6 guards the legacy
    # pointer alias, so bind their complete raw/semantic identity rather than
    # requiring the intentionally different kind and path.
    if value.campaign_id != CAMPAIGN_ID or (
        value.current.file_sha256 != pointer.file_sha256
        or value.current.target_content_sha256 != pointer.target_content_sha256
        or value.current.size != pointer.size
    ):
        raise PipelineError("current StateRoot does not select the live matrix")
    return value


def _source_name(path: str) -> str:
    return f"source.{sha256_bytes(path.encode('utf-8'))[:24]}"


def _physical_input(
    *,
    path: str,
    members: Mapping[str, RepositorySourceMember],
) -> AuthenticatedInput:
    member = _source_member(members, path, label=f"matrix source {path}")
    return AuthenticatedInput(
        name=_source_name(path),
        reference=EvidenceRef(
            kind="artifact",
            path=path,
            file_sha256=sha256_bytes(member.raw),
            target_content_sha256=None,
            size=len(member.raw),
        ),
        raw=member.raw,
    )


def _inventory_input(
    *,
    transition_id: str,
    group_tag: str,
    inventory: Mapping[str, object],
) -> AuthenticatedInput:
    track, marker, chipset = parse_group_tag(group_tag)
    if marker != "test":
        raise PipelineError("matrix inventory is not a TEST inventory")
    raw = rendered_json_bytes(dict(inventory))
    content_sha256 = _require_string(
        inventory.get("content_sha256"), label=f"{group_tag} inventory identity"
    )
    return AuthenticatedInput(
        name=f"inventory.{track}.{chipset}",
        reference=EvidenceRef(
            kind="artifact",
            path=(
                f"campaign/evidence/{transition_id}/inventories/"
                f"{track}-test-{chipset}.json"
            ),
            file_sha256=sha256_bytes(raw),
            target_content_sha256=content_sha256,
            size=len(raw),
        ),
        raw=raw,
    )


def _matrix_members(
    *,
    phase_bootstrap: PlannedRepositoryPhaseFreezeBootstrap,
    captured: Mapping[str, RepositorySourceMember],
    evidence: _EvidenceClosure,
    inventories: Mapping[str, Mapping[str, object]],
) -> tuple[AuthenticatedInput, ...]:
    physical_paths = {
        MATRIX_GENERATOR_PATH,
        _phase_inputs(phase_bootstrap)["tracks"].reference.path,
        evidence.seed.telemetry_schema.path,
        *(item.path for item in evidence.bindings),
        *(
            path
            for path in captured
            if path.startswith(PIN_DIRECTORY_PATH + "/") and path.endswith(".json")
        ),
    }
    members = [
        _physical_input(path=path, members=captured)
        for path in sorted(physical_paths)
    ]
    members.extend(
        _inventory_input(
            transition_id=phase_bootstrap.result.plan.transition_id,
            group_tag=group_tag,
            inventory=inventories[group_tag],
        )
        for group_tag in sorted(inventories)
    )
    members.append(
        AuthenticatedInput(
            name="engine-bundle",
            reference=phase_bootstrap.request.engine_bundle_ref,
            raw=phase_bootstrap.request.engine_bundle_raw,
        )
    )
    return _canonical_matrix_members(tuple(members))


def _canonical_matrix_members(
    members: tuple[AuthenticatedInput, ...],
) -> tuple[AuthenticatedInput, ...]:
    if type(members) is not tuple or any(
        type(item) is not AuthenticatedInput for item in members
    ):
        raise PipelineError("matrix members are invalid")
    result = tuple(sorted(members, key=lambda item: item.name))
    names = tuple(item.name for item in result)
    if len(names) != len(set(names)):
        raise PipelineError("matrix member names collide")
    paths = tuple(item.reference.path for item in result)
    if len(paths) != len(set(paths)):
        raise PipelineError("matrix member paths collide")
    return result


def _copy_payloads(
    store: CampaignStore,
    members: tuple[AuthenticatedInput, ...],
) -> tuple[AuthorityCopyPayloadV1, ...]:
    return tuple(
        AuthorityCopyPayloadV1(
            copy=AuthorityCopyV1(
                name=f"matrix.member.{item.name}",
                source=item.reference,
                stored=store.reference_for(
                    kind=item.reference.kind,
                    raw=item.raw,
                    target_content_sha256=item.reference.target_content_sha256,
                ),
            ),
            raw=item.raw,
        )
        for item in members
    )


def _inventory_row(inventory: Mapping[str, object]) -> tuple[dict[str, object], bool]:
    admitted = _require_list(inventory.get("cores"), label="inventory cores")
    deferred = _require_list(
        inventory.get("deferred_cores"), label="inventory deferred cores"
    )
    if len(admitted) == 1 and not deferred and type(admitted[0]) is dict:
        return admitted[0], True
    if len(deferred) == 1 and not admitted and type(deferred[0]) is dict:
        return deferred[0], False
    raise PipelineError("one-core inventory does not have one terminal row")


def _evidence_replays(
    evidence: _EvidenceClosure,
    names: Mapping[str, str],
) -> dict[str, EvidenceReplayV1]:
    selected = dict(evidence.selected_build_records)
    reproduction = dict(evidence.reproduction_build_records)

    def name(binding: _FileBinding) -> str:
        try:
            return names[binding.path]
        except KeyError as exc:
            raise PipelineError(
                f"evidence matrix member is unavailable: {binding.path}"
            ) from exc

    return {
        architecture: EvidenceReplayV1(
            pin=name(evidence.seed.pin),
            golden=name(evidence.seed.golden),
            selected_e2e=name(evidence.seed.selected_e2e),
            reproduction_e2e=name(evidence.seed.reproduction_e2e),
            selected_telemetry=name(evidence.selected_telemetry),
            reproduction_telemetry=name(evidence.reproduction_telemetry),
            selected_build_record=name(selected[architecture]),
            reproduction_build_record=name(reproduction[architecture]),
            telemetry_schema=name(evidence.seed.telemetry_schema),
        )
        for architecture in _ARCHITECTURES
    }


def _construct_inventories(
    *,
    authorities: Mapping[str, AuthenticatedInput],
    pin_index: Mapping[str, Mapping[str, object]],
    source_registry_index: Mapping[str, Mapping[str, object]],
    source_ancestry_verifier: object,
) -> tuple[
    dict[str, dict[str, object]],
    dict[int, str],
    dict[str, object],
    dict[str, object],
]:
    documents = {
        name: decode_identity_object(item.raw, label=f"phase authority {name}")
        for name, item in authorities.items()
        if name in _AUTHORITY_INPUT_ROLES
    }
    catalog = documents["catalog"]
    tracks = documents["tracks"]
    cores = _require_mapping(catalog.get("cores"), label="catalog cores")
    if len(cores) != EXPECTED_CORE_COUNT or CORE_ID not in cores:
        raise PipelineError("catalog does not contain the exact campaign core set")
    verifier = source_ancestry_verifier
    if verifier is not None and not callable(verifier):
        raise PipelineError("source ancestry verifier is invalid")
    inventories: dict[str, dict[str, object]] = {}
    by_ordinal: dict[int, str] = {}
    for ordinal in range(27):
        coordinate = coordinate_for_ordinal(CORE_ID, ordinal)
        group_tag = canonical_group_tag(
            coordinate.track, "test", coordinate.chipset
        )
        if group_tag not in inventories:
            inventories[group_tag] = construct_core_track_inventory(
                tracks,
                catalog=catalog,
                pin_index=pin_index,
                tunings=documents["tunings"],
                main_release_roster=documents["spruce-release-roster"],
                spruce_branch_bases=documents["spruce-branch-bases"],
                group_tag=group_tag,
                requested_cores=[CORE_ID],
                source_registry_index=source_registry_index,
                source_ancestry_verifier=verifier,  # type: ignore[arg-type]
                source_ancestry_core_id=CORE_ID,
            )
        by_ordinal[ordinal] = group_tag
    if len(inventories) != 24 or len(by_ordinal) != 27:
        raise PipelineError("Gambatte inventories do not cover the 27-cell shard")
    return inventories, by_ordinal, catalog, tracks


def plan_repository_authority_composition(
    store: CampaignStore,
    *,
    pin_services: PinLifecycleServices,
    current_state_root_ref: EvidenceRef,
    predecessor_matrix_root_ref: EvidenceRef,
    captured_at: str,
    audit_label: str,
    leaf_audit_id: str,
    reason: str,
    authoritative_suite_summary: str,
    transition_id: str = DEFAULT_TRANSITION_ID,
) -> PlannedRepositoryAuthorityCompositionV1:
    """Capture and replay the exact live post-Gambatte authority composition."""

    store = _require_store(store)
    if type(pin_services) is not PinLifecycleServices:
        raise PipelineError("authority composition pin services are invalid")
    if (
        type(predecessor_matrix_root_ref) is not EvidenceRef
        or predecessor_matrix_root_ref.kind != "matrix-root"
    ):
        raise PipelineError("selected predecessor matrix root is invalid")

    phase_bootstrap = plan_repository_phase_freeze_bootstrap(
        repository_root=store.repository_root,
        captured_at=captured_at,
        transition_id=transition_id,
        reason=reason,
    )
    phase_inputs = _phase_inputs(phase_bootstrap)
    track_registry = decode_identity_object(
        phase_inputs["tracks"].raw, label="phase track registry"
    )

    first_pin_index = load_authoritative_core_pin_index(services=pin_services)
    first_source_index = load_core_track_source_registry_index(store.repository_root)
    pin_id = _gambatte_pin_id(track_registry)
    try:
        pin_entry = first_pin_index[pin_id]
    except KeyError as exc:
        raise PipelineError(
            "Gambatte TEST pin is absent from the authoritative index"
        ) from exc

    base_paths = tuple(
        sorted({MATRIX_POINTER_PATH, *_phase_overlap_paths(phase_bootstrap)})
    )
    base_capture = _capture_sources(
        store.repository_root,
        exact_paths=base_paths,
    )
    base_members = _member_map(base_capture)
    pin_path = _require_string(pin_entry.get("path"), label="Gambatte pin path")
    telemetry_schema = phase_inputs["telemetry-schema"]
    seed = _pin_seed(
        pin_entry=pin_entry,
        pin_raw=_source_member(
            base_members, pin_path, label="Gambatte captured pin"
        ).raw,
        telemetry_schema=telemetry_schema,
    )

    e2e_capture = _capture_sources(
        store.repository_root,
        exact_paths=tuple(
            sorted(
                {
                    *base_paths,
                    seed.selected_e2e.path,
                    seed.reproduction_e2e.path,
                }
            )
        ),
    )
    _require_capture_extension(base_capture, e2e_capture)
    evidence = _e2e_evidence(
        repository_root=store.repository_root,
        seed=seed,
        members=_member_map(e2e_capture),
    )
    final_paths = tuple(
        sorted({*base_paths, *_captured_binding_paths(evidence)})
    )
    first_capture = _capture_sources(
        store.repository_root,
        exact_paths=final_paths,
    )
    _require_capture_extension(e2e_capture, first_capture)
    second_capture = _capture_sources(
        store.repository_root,
        exact_paths=final_paths,
    )
    if first_capture != second_capture:
        raise PipelineError("repository H6 authorities moved during final capture")

    second_pin_index = load_authoritative_core_pin_index(services=pin_services)
    second_source_index = load_core_track_source_registry_index(store.repository_root)
    if first_pin_index != second_pin_index:
        raise PipelineError("authoritative core pin index moved during capture")
    if first_source_index != second_source_index:
        raise PipelineError("source registry index moved during capture")

    captured = _member_map(first_capture)
    _require_phase_overlap(phase_bootstrap, first_capture)
    _require_pin_index(first_pin_index, captured)
    _require_source_registry_index(first_source_index, captured)
    _require_evidence_bindings(evidence, captured)

    predecessor, expected_pointer = _authenticate_predecessor(
        store,
        predecessor_matrix_root_ref=predecessor_matrix_root_ref,
        pointer_member=_source_member(
            captured, MATRIX_POINTER_PATH, label="live campaign matrix pointer"
        ),
    )
    _authenticate_current_root(
        store,
        reference=current_state_root_ref,
        pointer=expected_pointer,
    )
    root_projection = decode_matrix_v2(
        predecessor.root.legacy_root_json.encode("utf-8")
    )
    predecessor_inputs = _require_mapping(
        root_projection.get("inputs"), label="predecessor matrix inputs"
    )
    snapshot_fingerprint = _fingerprint(
        TRACK_SNAPSHOT_DIRECTORY_PATH, captured
    )
    _require_unchanged_track_snapshot_directory(
        predecessor_inputs.get("track_registry_snapshot_directory"),
        current=snapshot_fingerprint,
    )
    pin_fingerprint = _fingerprint(PIN_DIRECTORY_PATH, captured)
    _require_post_gambatte_pin_directory(
        predecessor_inputs.get("pin_directory"),
        current=pin_fingerprint,
        gambatte_pin_path=pin_path,
    )

    inventories, inventory_by_ordinal, catalog, tracks = _construct_inventories(
        authorities=phase_inputs,
        pin_index=first_pin_index,
        source_registry_index=first_source_index,
        source_ancestry_verifier=core_track_source_ancestry_verifier(
            services=pin_services
        ),
    )
    matrix_members = _matrix_members(
        phase_bootstrap=phase_bootstrap,
        captured=captured,
        evidence=evidence,
        inventories=inventories,
    )
    member_names = {item.reference.path: item.name for item in matrix_members}
    inventory_names = {
        group_tag: _inventory_input(
            transition_id=phase_bootstrap.result.plan.transition_id,
            group_tag=group_tag,
            inventory=inventories[group_tag],
        ).name
        for group_tag in inventories
    }
    evidence_by_arch = _evidence_replays(evidence, member_names)
    pipeline_bundle = decode_identity_object(
        phase_bootstrap.request.engine_bundle_raw,
        label="phase engine bundle",
    )
    pipeline_content = _require_string(
        pipeline_bundle.get("content_sha256"), label="pipeline bundle identity"
    )

    rows: list[MatrixCellReplayV1] = []
    for ordinal in range(27):
        coordinate = coordinate_for_ordinal(CORE_ID, ordinal)
        group_tag = inventory_by_ordinal[ordinal]
        inventory = inventories[group_tag]
        _row, admitted = _inventory_row(inventory)
        producer = (
            canonical_track_inventory_producer_v1(
                inventory,
                coordinate=coordinate,
                track_registry=tracks,
            )
            if admitted
            else None
        )
        rows.append(
            MatrixCellReplayV1(
                coordinate=coordinate,
                inventory_copy=inventory_names[group_tag],
                evidence=(
                    evidence_by_arch[coordinate.architecture] if admitted else None
                ),
                producer_coordinate=producer,
                pipeline_bundle_content_sha256=(
                    None if admitted else pipeline_content
                ),
                source_registry_snapshots=(),
            )
        )

    pin_member_names = tuple(
        sorted(
            member_names[path]
            for path in captured
            if path.startswith(PIN_DIRECTORY_PATH + "/")
            and path.endswith(".json")
        )
    )
    replay = MatrixRefreshReplayV1(
        transition_id=phase_bootstrap.result.plan.transition_id,
        core_id=CORE_ID,
        cells=tuple(rows),
        audit_label=audit_label,
        leaf_audit_id=leaf_audit_id,
        reason=reason,
        predecessor_pointer_path=MATRIX_POINTER_PATH,
        generator_copy=member_names[MATRIX_GENERATOR_PATH],
        track_registry_copy=member_names[phase_inputs["tracks"].reference.path],
        pipeline_bundle_copy="engine-bundle",
        authoritative_suite_summary=authoritative_suite_summary,
        edge_source_count=len(
            _require_mapping(catalog.get("cores"), label="catalog cores")
        ),
        pin_directory=DirectoryReplayV1(
            path=PIN_DIRECTORY_PATH,
            members=pin_member_names,
        ),
        track_registry_snapshot_directory=None,
    )
    successor = replay_matrix_refresh(
        predecessor,
        replay=replay,
        copies=_copy_payloads(store, matrix_members),
        phase_freeze=phase_bootstrap.result.plan.successor,
        captured_at=captured_at,
    )
    return PlannedRepositoryAuthorityCompositionV1(
        phase_bootstrap=phase_bootstrap,
        current_state_root_ref=current_state_root_ref,
        expected_pointer=expected_pointer,
        predecessor_matrix=predecessor,
        successor_matrix=successor,
        matrix_replay=replay,
        matrix_members=matrix_members,
    )


__all__ = [
    "CORE_ID",
    "MATRIX_GENERATOR_PATH",
    "MATRIX_POINTER_PATH",
    "PIN_DIRECTORY_PATH",
    "PlannedRepositoryAuthorityCompositionV1",
    "TRACK_SNAPSHOT_DIRECTORY_PATH",
    "plan_repository_authority_composition",
]
