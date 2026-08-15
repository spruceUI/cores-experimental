from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.core_pipeline_lib.campaign import matrix_refresh as matrix_refresh_module
from scripts.core_pipeline_lib.campaign.legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
)
from scripts.core_pipeline_lib.campaign.matrix_materialize import (
    materialize_matrix_v2,
    normalize_matrix_v2,
    validate_normalized_matrix,
)
from scripts.core_pipeline_lib.campaign.matrix_model import (
    EXCLUSION_PARTITION,
    SUPPORTED_PARTITION,
    MatrixCellV1,
    MatrixCoordinateV1,
    coordinate_for_ordinal,
)
from scripts.core_pipeline_lib.campaign.matrix_refresh import (
    DirectoryFingerprintV1,
    HydratedArtifactV1,
    PipelineBundleIdentityV1,
    TrackCellEvidenceV1,
    project_matrix_root_refresh_v1,
    project_track_inventory_cell_v1,
    splice_matrix_core_refresh_v1,
)
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.chipsets import resolved_tuning_profile
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes
from scripts.core_pipeline_lib.tracks import (
    core_track_inventory_content_sha256,
    core_track_test_assignment_content_sha256,
    core_tracks_content_sha256,
    core_variant_id,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_ROOT = Path(
    ".local-e2e/campaigns/host-core-build-20260810"
)
MATRIX_PATH = CAMPAIGN_ROOT / "campaign-matrix.json"
TRACKS_PATH = Path("manifests/core-tracks.json")
TUNINGS_PATH = Path("manifests/chipset-tunings.json")
TELEMETRY_SCHEMA_PATH = Path("manifests/host-build-telemetry.schema.json")
GAMBATTE_PIN_PATH = Path(
    "pins/core-sets/gambatte-dfc165599f3f-e141e6b01b6b.json"
)


def _path(relative: str | Path) -> Path:
    return REPOSITORY_ROOT / relative


def _json(relative: str | Path) -> dict[str, object]:
    value = json.loads(_path(relative).read_bytes())
    assert type(value) is dict
    return value


def _artifact(relative: str | Path) -> HydratedArtifactV1:
    relative = Path(relative).as_posix()
    return HydratedArtifactV1(path=relative, raw=_path(relative).read_bytes())


def _content_reference(
    *, kind: str, path: str, file_sha256: str, content_sha256: str, size: int
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=file_sha256,
        target_content_sha256=content_sha256,
        size=size,
    )


def _phase_freeze_reference(matrix: dict[str, object]) -> EvidenceRef:
    inputs = matrix["inputs"]
    assert type(inputs) is dict
    value = inputs["phase_freeze"]
    assert type(value) is dict
    raw = _path(value["path"]).read_bytes()
    return _content_reference(
        kind="phase-freeze",
        path=value["path"],
        file_sha256=value["file_sha256"],
        content_sha256=value["content_sha256"],
        size=len(raw),
    )


def _core_spec_reference(matrix: dict[str, object]) -> EvidenceRef:
    inputs = matrix["inputs"]
    assert type(inputs) is dict
    catalog = inputs["catalog"]
    assert type(catalog) is dict
    raw = _path(catalog["path"]).read_bytes()
    return _content_reference(
        kind="artifact",
        path=catalog["path"],
        file_sha256=catalog["file_sha256"],
        content_sha256=catalog["content_sha256"],
        size=len(raw),
    )


def _matrix_cell(payload: dict[str, object]) -> MatrixCellV1:
    coordinate = MatrixCoordinateV1.from_document(payload["coordinate"])
    return MatrixCellV1(
        universe_ordinal=coordinate.universe_ordinal,
        coordinate=coordinate,
        partition=SUPPORTED_PARTITION,
        legacy_payload_json=matrix_v2_canonical_bytes(payload).decode("utf-8"),
    )


def _evidence_for(
    pin_path: str | Path,
    *,
    core_id: str,
    architecture: str,
) -> TrackCellEvidenceV1:
    pin = _json(pin_path)
    cores = pin["cores"]
    assert type(cores) is dict
    core = cores[core_id]
    assert type(core) is dict
    selection = core["selection"]
    assert type(selection) is dict
    host = selection["host_reproduction"]
    assert type(host) is dict
    selected_proof = host["selected"]
    reproduction_proof = host["reproduction"]
    assert type(selected_proof) is dict and type(reproduction_proof) is dict
    selected_store = selected_proof["e2e_record"]
    reproduction_store = reproduction_proof["e2e_record"]
    assert type(selected_store) is dict and type(reproduction_store) is dict
    selected_path = selected_store["path"]
    reproduction_path = reproduction_store["path"]
    selected = _json(selected_path)
    reproduction = _json(reproduction_path)

    def build_path(document: dict[str, object]) -> str:
        builds = document["builds"]
        assert type(builds) is list
        rows = [
            row
            for row in builds
            if type(row) is dict
            and row.get("core_id") == core_id
            and row.get("architecture") == architecture
        ]
        assert len(rows) == 1
        digest = rows[0]["record_sha256"]
        assert type(digest) is str
        return f".local-e2e/store/build-records/sha256/{digest[:2]}/{digest}"

    selected_runner = selected["runner"]
    reproduction_runner = reproduction["runner"]
    assert type(selected_runner) is dict and type(reproduction_runner) is dict
    selected_telemetry = selected_runner["telemetry"]
    reproduction_telemetry = reproduction_runner["telemetry"]
    assert type(selected_telemetry) is dict
    assert type(reproduction_telemetry) is dict
    sources = pin["sources"]
    assert type(sources) is list and len(sources) == 1
    golden = sources[0]
    assert type(golden) is dict
    return TrackCellEvidenceV1(
        pin=_artifact(pin_path),
        golden=_artifact(golden["path"]),
        selected_e2e=_artifact(selected_path),
        reproduction_e2e=_artifact(reproduction_path),
        selected_telemetry=_artifact(selected_telemetry["path"]),
        reproduction_telemetry=_artifact(reproduction_telemetry["path"]),
        selected_build_record=_artifact(build_path(selected)),
        reproduction_build_record=_artifact(build_path(reproduction)),
        telemetry_schema=_artifact(TELEMETRY_SCHEMA_PATH),
    )


def _inventory(
    *,
    matrix: dict[str, object],
    registry: dict[str, object],
    coordinate: MatrixCoordinateV1,
    row: dict[str, object],
) -> dict[str, object]:
    inputs = matrix["inputs"]
    assert type(inputs) is dict
    catalog = inputs["catalog"]
    assert type(catalog) is dict
    tunings = _json(TUNINGS_PATH)
    admitted = row.get("state") != "deferred"
    result: dict[str, object] = {
        "schema_version": 2,
        "validation_scope": "static-build-selection-only",
        "local_only": True,
        "publication": "disabled",
        "group_tag": (
            f"{coordinate.track}-test:{coordinate.chipset}"
        ),
        "applicability_scope": copy.deepcopy(registry["applicability_scope"]),
        "catalog_content_sha256": catalog["content_sha256"],
        "track_registry_content_sha256": registry["content_sha256"],
        "tuning_registry_content_sha256": tunings["content_sha256"],
        "cores": [row] if admitted else [],
        "deferred_cores": [] if admitted else [row],
        "unsupported_core_ids": [],
        "inventory_state": "unstable" if admitted else "deferred",
        "complete": admitted,
        "summary": {
            "selected_core_count": int(admitted),
            "stable_core_count": 0,
            "unstable_core_count": int(admitted),
            "deferred_core_count": int(not admitted),
            "unsupported_core_count": 0,
            "universal_fallback_count": int(coordinate.chipset != "universal"),
        },
        "content_sha256": "",
    }
    result["content_sha256"] = core_track_inventory_content_sha256(result)
    return result


def _row_from_admitted_payload(
    *,
    payload: dict[str, object],
    registry: dict[str, object],
    pin: dict[str, object],
) -> dict[str, object]:
    coordinate = payload["coordinate"]
    resolution = payload["resolution"]
    build_identity = payload["build_identity"]
    version_slice = payload["version_slice"]
    assert type(coordinate) is dict
    assert type(resolution) is dict
    assert type(build_identity) is dict
    assert type(version_slice) is dict
    pin_identity = build_identity["pin"]
    source = build_identity["source"]
    tuning = build_identity["tuning"]
    assert type(pin_identity) is dict
    assert type(source) is dict and type(source["identity"]) is dict
    assert type(tuning) is dict and type(tuning["identity"]) is dict
    cores = pin["cores"]
    assert type(cores) is dict and type(cores[coordinate["core_id"]]) is dict
    selection = cores[coordinate["core_id"]]["selection"]
    assert type(selection) is dict and type(selection["targets"]) is dict
    tracks = registry["tracks"]
    assert type(tracks) is dict and type(tracks[coordinate["track"]]) is dict
    return {
        "core_id": coordinate["core_id"],
        "track": coordinate["track"],
        "requested_marker": "test",
        "requested_chipset": coordinate["chipset"],
        "selected_chipset": resolution["selected_chipset"],
        "selected_state": "test",
        "stability": "unstable",
        "resolution": resolution["resolution"],
        "test_origin_track": resolution["origin_track"],
        "current_assignment_content_sha256": (
            core_track_test_assignment_content_sha256(
                registry,
                track=coordinate["track"],
                core_id=coordinate["core_id"],
                chipset=coordinate["chipset"],
            )
        ),
        "spruce_branch_basis": copy.deepcopy(
            tracks[coordinate["track"]]["spruce_branch_basis"]
        ),
        "version_slice": copy.deepcopy(version_slice["slice"]),
        "slice_comparison_basis": copy.deepcopy(
            version_slice["comparison_basis"]
        ),
        "variant_id": build_identity["variant_id"],
        "pin": {
            key: pin_identity[key]
            for key in ("path", "pin_id", "file_sha256", "content_sha256")
        },
        "source_commit": source["identity"]["resolved_commit"],
        "architectures": sorted(selection["targets"]),
        "selected_architectures": sorted(selection["targets"]),
        "tuning": copy.deepcopy(tuning["identity"]),
    }


def _pin_index_projection(
    *,
    pin_path: Path,
    pin: dict[str, object],
    core_id: str,
) -> dict[str, dict[str, object]]:
    cores = pin["cores"]
    assert type(cores) is dict and type(cores[core_id]) is dict
    selection = cores[core_id]["selection"]
    assert type(selection) is dict and type(selection["targets"]) is dict
    targets = selection["targets"]
    first = targets[sorted(targets)[0]]
    assert type(first) is dict and type(first["golden_record"]) is dict
    golden = first["golden_record"]
    source = golden["source"]
    recipe = golden["recipe"]
    assert type(source) is dict and type(recipe) is dict
    tuning_identity = recipe.get("chipset_tuning")
    host = selection["host_reproduction"]
    assert type(host) is dict
    return {
        pin["pin_id"]: {
            "path": pin_path.as_posix(),
            "pin_id": pin["pin_id"],
            "file_sha256": sha256_bytes(_path(pin_path).read_bytes()),
            "content_sha256": pin["content_sha256"],
            "core_id": core_id,
            "architectures": sorted(targets),
            "artifact_sha256": {
                architecture: target["artifact"]["sha256"]
                for architecture, target in sorted(targets.items())
            },
            "source_commit": source["resolved_commit"],
            "source_repository": source["resolved_url"],
            "source_requested_ref": source["requested_ref"],
            "source_tree": source["tree"],
            "tuning_identity": copy.deepcopy(tuning_identity),
            "host_reproduction_content_sha256": host["content_sha256"],
        }
    }


def _gambatte_row(
    *,
    registry: dict[str, object],
    pin: dict[str, object],
    coordinate: MatrixCoordinateV1,
) -> dict[str, object]:
    assert coordinate.track in {"main", "nightly"}
    tracks = registry["tracks"]
    assert type(tracks) is dict and type(tracks["main"]) is dict
    main_test = tracks["main"]["test"]
    assert type(main_test) is dict and type(main_test["gambatte"]) is dict
    cell = main_test["gambatte"]["universal"]
    assert type(cell) is dict
    tunings = _json(TUNINGS_PATH)
    tuning = resolved_tuning_profile(tunings, cell["tuning_profile"])
    pin_index = _pin_index_projection(
        pin_path=GAMBATTE_PIN_PATH,
        pin=pin,
        core_id="gambatte",
    )
    version_policy = registry["version_policy"]
    assert type(version_policy) is dict
    comparison = version_policy["slice_comparison_bases"]
    assert type(comparison) is dict
    targets = pin["cores"]["gambatte"]["selection"]["targets"]
    assert type(targets) is dict
    requested_assignment = core_track_test_assignment_content_sha256(
        registry,
        track=coordinate.track,
        core_id="gambatte",
        chipset=coordinate.chipset,
    )
    return {
        "core_id": "gambatte",
        "track": coordinate.track,
        "requested_marker": "test",
        "requested_chipset": coordinate.chipset,
        "selected_chipset": "universal",
        "selected_state": "test",
        "stability": "unstable",
        "resolution": (
            "exact_test"
            if coordinate.chipset == "universal"
            else "universal_test_fallback"
        ),
        "test_origin_track": "main",
        "current_assignment_content_sha256": requested_assignment,
        "spruce_branch_basis": copy.deepcopy(
            tracks[coordinate.track]["spruce_branch_basis"]
        ),
        "version_slice": copy.deepcopy(cell["version_slice"]),
        "slice_comparison_basis": copy.deepcopy(
            comparison[cell["version_slice"]["content_sha256"]]
        ),
        "variant_id": core_variant_id(
            core_id="gambatte",
            cell_chipset="universal",
            cell=cell,
            pin_index=pin_index,
            tunings=tunings,
        ),
        "pin": {
            key: pin_index[pin["pin_id"]][key]
            for key in ("path", "pin_id", "file_sha256", "content_sha256")
        },
        "source_commit": pin_index[pin["pin_id"]]["source_commit"],
        "architectures": sorted(targets),
        "selected_architectures": (
            sorted(targets)
            if coordinate.chipset == "universal"
            else [coordinate.architecture]
        ),
        "tuning": {
            key: copy.deepcopy(tuning[key])
            for key in (
                "profile_id",
                "content_sha256",
                "properties",
                "compiler_argument_mapping_version",
                "compiler_arguments",
            )
        },
    }


def _gambatte_deferred_row(
    *,
    registry: dict[str, object],
    coordinate: MatrixCoordinateV1,
) -> dict[str, object]:
    assert coordinate.track == "edge"
    tracks = registry["tracks"]
    assert type(tracks) is dict and type(tracks["edge"]) is dict
    deferred = tracks["edge"]["deferred"]
    assert type(deferred) is dict and type(deferred["gambatte"]) is dict
    cell = deferred["gambatte"]["universal"]
    assert type(cell) is dict
    return {
        "core_id": "gambatte",
        "track": "edge",
        "requested_marker": "test",
        "requested_chipset": coordinate.chipset,
        "selected_chipset": "universal",
        "state": "deferred",
        "reason": cell["reason"],
        "origin_track": "edge",
        "current_assignment_content_sha256": (
            core_track_test_assignment_content_sha256(
                registry,
                track="edge",
                core_id="gambatte",
                chipset=coordinate.chipset,
            )
        ),
        "resolution": (
            "exact_deferred"
            if coordinate.chipset == "universal"
            else "universal_deferred_fallback"
        ),
        "spruce_branch_basis": copy.deepcopy(
            tracks["edge"]["spruce_branch_basis"]
        ),
    }


def _digest(character: str) -> str:
    assert len(character) == 1 and character in "0123456789abcdef"
    return character * 64


def _synthetic_reference(name: str, character: str) -> dict[str, object]:
    return {
        "path": f"evidence/{name}.json",
        "file_sha256": _digest(character),
        "content_sha256": _digest(hex((int(character, 16) + 1) % 16)[2:]),
    }


def _synthetic_root_evidence_record(
    *,
    core_id: str = "synthetic_core",
) -> dict[str, object]:
    return {
        "core_id": core_id,
        "pin": _synthetic_reference("pin", "1"),
        "golden": _synthetic_reference("golden", "2"),
        "selected_e2e": _synthetic_reference("selected-e2e", "3"),
        "reproduction_e2e": _synthetic_reference("reproduction-e2e", "4"),
        "selected_telemetry": _synthetic_reference("selected-telemetry", "5"),
        "reproduction_telemetry": _synthetic_reference(
            "reproduction-telemetry", "6"
        ),
        "host_reproduction_content_sha256": _digest("7"),
    }


def _synthetic_admitted_payload(
    record: dict[str, object],
    *,
    pin_id: str = "synthetic-pin-v1",
) -> dict[str, object]:
    pin = record["pin"]
    golden = record["golden"]
    assert type(pin) is dict and type(golden) is dict
    return {
        "coordinate": {
            "core_id": record["core_id"],
            "track": "main",
            "marker": "test",
            "chipset": "universal",
            "architecture": "arm64",
        },
        "lifecycle": {"admission_state": "admitted"},
        "build_identity": {
            "pin": {
                **copy.deepcopy(pin),
                "pin_id": pin_id,
                "selection_content_sha256": _digest("8"),
            }
        },
        "evidence": {
            "state": "validated",
            "golden": {
                **copy.deepcopy(golden),
                "architecture": "arm64",
                "provenance_identity_sha256": _digest("9"),
            },
            "selected": {
                "run_id": "selected-run-v1",
                "e2e": copy.deepcopy(record["selected_e2e"]),
                "telemetry": copy.deepcopy(record["selected_telemetry"]),
            },
            "reproduction": {
                "run_id": "reproduction-run-v1",
                "e2e": copy.deepcopy(record["reproduction_e2e"]),
                "telemetry": copy.deepcopy(record["reproduction_telemetry"]),
            },
            "host_reproduction": {
                "content_sha256": record[
                    "host_reproduction_content_sha256"
                ]
            },
        },
    }


def _synthetic_supported_cell(
    *,
    coordinate: MatrixCoordinateV1,
    basis_id: str,
    basis_content_sha256: str,
) -> MatrixCellV1:
    payload: dict[str, object] = {
        "coordinate": coordinate.to_document(),
        "lifecycle": {
            "evidence_state": "candidate",
            "execution_state": "not-run",
            "admission_state": "deferred",
            "gha_state": "gha-not-requested",
            "reason": "synthetic",
        },
        "resolution": {
            "resolution": "exact_deferred",
            "catalog_candidate": {"architecture": coordinate.architecture},
            "edge_candidate": {},
        },
        "build_identity": {"pin": None},
        "evidence": copy.deepcopy(matrix_refresh_module._ABSENT_CELL_EVIDENCE),
        "outputs": {},
        "version_slice": {"slice": None, "comparison_basis": None},
        "lineage": {},
        "outlier": {"state": "not-applicable-unassigned"},
        "reuse": {},
        "performance": {},
        "branch_artifact_observation": {
            "basis": {
                "basis_id": basis_id,
                "basis_content_sha256": basis_content_sha256,
                "registry_content_sha256": _digest("a"),
            },
            "branch": "Development",
            "catalog_cell": {
                "core_id": coordinate.core_id,
                "architecture": coordinate.architecture,
            },
            "artifact_validity": "not-observed",
        },
        "content_sha256": "",
    }
    payload["content_sha256"] = matrix_v2_semantic_sha256(payload)
    return MatrixCellV1(
        universe_ordinal=coordinate.universe_ordinal,
        coordinate=coordinate,
        partition=SUPPORTED_PARTITION,
        legacy_payload_json=matrix_v2_canonical_bytes(payload).decode("utf-8"),
    )


@pytest.mark.skipif(
    not _path(MATRIX_PATH).is_file(),
    reason="local campaign matrix evidence is unavailable",
)
def test_live_admission_projection_reproduces_existing_cell_exactly() -> None:
    matrix = _json(MATRIX_PATH)
    registry = _json(TRACKS_PATH)
    supported = matrix["supported_cells"]
    assert type(supported) is list
    payload = next(
        cell
        for cell in supported
        if cell["coordinate"]
        == {
            "track": "main",
            "marker": "test",
            "core_id": "2048",
            "chipset": "universal",
            "architecture": "arm64",
        }
    )
    assert type(payload) is dict
    pin_path = Path(payload["build_identity"]["pin"]["path"])
    pin = _json(pin_path)
    coordinate = MatrixCoordinateV1.from_document(payload["coordinate"])
    row = _row_from_admitted_payload(
        payload=payload,
        registry=registry,
        pin=pin,
    )
    inventory = _inventory(
        matrix=matrix,
        registry=registry,
        coordinate=coordinate,
        row=row,
    )
    inventory_before = copy.deepcopy(inventory)
    registry_before = copy.deepcopy(registry)
    predecessor_cell = _matrix_cell(payload)
    evidence = _evidence_for(
        pin_path,
        core_id="2048",
        architecture="arm64",
    )
    projected = project_track_inventory_cell_v1(
        inventory,
        coordinate=coordinate,
        track_registry=registry,
        predecessor_cell=predecessor_cell,
        evidence=evidence,
        producer_coordinate=MatrixCoordinateV1.from_document(
            payload["reuse"]["producer_coordinate"]
        ),
    )
    assert decode_matrix_v2(
        projected.legacy_payload_json.encode("utf-8")
    ) == payload
    assert inventory == inventory_before
    assert registry == registry_before
    with pytest.raises(PipelineError, match="canonical first use"):
        project_track_inventory_cell_v1(
            inventory,
            coordinate=coordinate,
            track_registry=registry,
            predecessor_cell=predecessor_cell,
            evidence=evidence,
            producer_coordinate=MatrixCoordinateV1(
                core_id="2048",
                track="main",
                chipset="a133p",
                architecture="arm64",
            ),
        )


@pytest.mark.skipif(
    not all(
        _path(path).is_file()
        for path in (MATRIX_PATH, TRACKS_PATH, GAMBATTE_PIN_PATH)
    ),
    reason="live Gambatte admission evidence is unavailable",
)
def test_live_gambatte_projection_changes_one_shard_and_root_in_memory() -> None:
    matrix_raw = _path(MATRIX_PATH).read_bytes()
    matrix = json.loads(matrix_raw)
    assert type(matrix) is dict
    registry = _json(TRACKS_PATH)
    pin = _json(GAMBATTE_PIN_PATH)
    phase_freeze = _phase_freeze_reference(matrix)
    predecessor = normalize_matrix_v2(
        matrix_raw,
        phase_freeze=phase_freeze,
        core_spec_set=_core_spec_reference(matrix),
    )
    predecessor_cells = {
        cell.coordinate: cell
        for cell in predecessor.cells
        if cell.coordinate.core_id == "gambatte"
    }
    assert len(predecessor_cells) == 27
    evidence = {
        architecture: _evidence_for(
            GAMBATTE_PIN_PATH,
            core_id="gambatte",
            architecture=architecture,
        )
        for architecture in ("arm64", "armhf")
    }
    replacements: list[MatrixCellV1] = []
    for coordinate, prior in sorted(
        predecessor_cells.items(), key=lambda item: item[0].universe_ordinal
    ):
        admitted = coordinate.track != "edge"
        row = (
            _gambatte_row(
                registry=registry,
                pin=pin,
                coordinate=coordinate,
            )
            if admitted
            else _gambatte_deferred_row(
                registry=registry,
                coordinate=coordinate,
            )
        )
        inventory = _inventory(
            matrix=matrix,
            registry=registry,
            coordinate=coordinate,
            row=row,
        )
        producer = MatrixCoordinateV1(
            core_id="gambatte",
            track="main",
            chipset="universal",
            architecture=coordinate.architecture,
        )
        replacements.append(
            project_track_inventory_cell_v1(
                inventory,
                coordinate=coordinate,
                track_registry=registry,
                predecessor_cell=prior,
                evidence=evidence[coordinate.architecture] if admitted else None,
                producer_coordinate=producer if admitted else None,
                pipeline_bundle_content_sha256=(
                    matrix["inputs"]["pipeline_bundle"]["content_sha256"]
                    if not admitted
                    else None
                ),
            )
        )
    replacement_tuple = tuple(replacements)
    replacement_payloads = tuple(
        decode_matrix_v2(cell.legacy_payload_json.encode("utf-8"))
        for cell in replacement_tuple
    )
    assert sum(
        payload["lifecycle"]["execution_state"] == "built"
        for payload in replacement_payloads
    ) == 2
    assert sum(
        payload["lifecycle"]["execution_state"] == "reused"
        for payload in replacement_payloads
    ) == 16
    assert sum(
        payload["lifecycle"]["execution_state"] == "not-run"
        for payload in replacement_payloads
    ) == 9
    assert sum(
        payload["lifecycle"]["admission_state"] == "admitted"
        for payload in replacement_payloads
    ) == 18
    replacement_by_coordinate = {
        cell.coordinate: cell for cell in replacement_tuple
    }
    successor_cells = tuple(
        replacement_by_coordinate.get(cell.coordinate, cell)
        for cell in predecessor.cells
    )
    inputs = matrix["inputs"]
    assert type(inputs) is dict and type(inputs["pipeline_bundle"]) is dict
    pipeline = inputs["pipeline_bundle"]
    pin_files = tuple(
        _artifact(path.relative_to(REPOSITORY_ROOT))
        for path in sorted(_path("pins/core-sets").glob("*.json"))
    )
    root_projection = project_matrix_root_refresh_v1(
        predecessor,
        cells=successor_cells,
        captured_at="2026-08-15T01:00:00Z",
        audit_label="spruce-core-build-campaign-20260810",
        leaf_audit_id="matrix-refresh-characterization-v1",
        reason="characterize the generic one-core admission projection in memory",
        predecessor_pointer_path=CAMPAIGN_ROOT.joinpath(
            "campaign-matrix.json"
        ).as_posix(),
        generator=_artifact(
            "scripts/core_pipeline_lib/campaign/matrix_refresh.py"
        ),
        phase_freeze=phase_freeze,
        track_registry_artifact=_artifact(TRACKS_PATH),
        pipeline_bundle=PipelineBundleIdentityV1(
            schema_version=pipeline["schema_version"],
            file_count=pipeline["file_count"],
            content_sha256=pipeline["content_sha256"],
        ),
        authoritative_suite_summary="focused matrix refresh characterization passed",
        edge_source_count=98,
        evidence_records=(evidence["arm64"],),
        pin_directory=DirectoryFingerprintV1(
            path="pins/core-sets",
            files=pin_files,
        ),
    )
    successor = splice_matrix_core_refresh_v1(
        predecessor,
        replacement_cells=replacement_tuple,
        legacy_root_projection=root_projection,
        phase_freeze=phase_freeze,
    )
    validate_normalized_matrix(successor)
    successor_raw = materialize_matrix_v2(successor)
    assert successor_raw != matrix_raw
    successor_document = decode_matrix_v2(successor_raw)
    summary = successor_document["summary"]
    assert type(summary) is dict
    assert {
        key: summary[key]
        for key in (
            "admitted_core_count",
            "admitted_cell_count",
            "deferred_cell_count",
            "evidence_pin_count",
            "selected_run_count",
            "reproduction_run_count",
            "producer_cell_count",
            "logical_reuse_cell_count",
        )
    } == {
        "admitted_core_count": 12,
        "admitted_cell_count": 315,
        "deferred_cell_count": 2_223,
        "evidence_pin_count": 12,
        "selected_run_count": 12,
        "reproduction_run_count": 12,
        "producer_cell_count": 24,
        "logical_reuse_cell_count": 291,
    }
    tracks = {
        item["track"]: item
        for item in successor_document["tracks"]
    }
    assert {
        track: value["lifecycle_counts"]["admission"]
        for track, value in tracks.items()
    } == {
        "main": {"admitted": 108, "deferred": 738},
        "nightly": {"admitted": 108, "deferred": 738},
        "edge": {"admitted": 99, "deferred": 747},
    }
    projected_by_track = {
        payload["coordinate"]["track"]: payload
        for payload in replacement_payloads
        if payload["coordinate"]["chipset"] == "universal"
        and payload["coordinate"]["architecture"] == "arm64"
    }
    assert projected_by_track["main"]["resolution"]["assignment_mode"] == (
        "direct-test"
    )
    assert projected_by_track["nightly"]["resolution"]["assignment_mode"] == (
        "inherited-test"
    )
    assert projected_by_track["edge"]["resolution"]["assignment_mode"] == (
        "direct-deferred"
    )
    assert sum(
        old.content_sha256 != new.content_sha256
        for old, new in zip(predecessor.cells, successor.cells)
    ) == 27
    assert [
        new.core_id
        for old, new in zip(predecessor.shards, successor.shards)
        if old.content_sha256 != new.content_sha256
    ] == ["gambatte"]
    assert predecessor.root.content_sha256 != successor.root.content_sha256


def test_projection_rejects_stale_inventory_identity() -> None:
    registry: dict[str, object] = {}
    registry["content_sha256"] = core_tracks_content_sha256(registry)
    inventory = {
        "schema_version": 2,
        "validation_scope": "static-build-selection-only",
        "local_only": True,
        "publication": "disabled",
        "group_tag": "main-test:universal",
        "applicability_scope": {},
        "catalog_content_sha256": "0" * 64,
        "track_registry_content_sha256": "1" * 64,
        "tuning_registry_content_sha256": "2" * 64,
        "cores": [],
        "deferred_cores": [],
        "unsupported_core_ids": [],
        "inventory_state": "unavailable",
        "complete": False,
        "summary": {},
        "content_sha256": "3" * 64,
    }
    with pytest.raises(PipelineError, match="inventory identity is stale"):
        project_track_inventory_cell_v1(
            inventory,
            coordinate=MatrixCoordinateV1(
                core_id="gambatte",
                track="main",
                chipset="universal",
                architecture="arm64",
            ),
            track_registry=registry,
            predecessor_cell=object(),  # type: ignore[arg-type]
            evidence=object(),  # type: ignore[arg-type]
            producer_coordinate=object(),  # type: ignore[arg-type]
        )
    inventory["group_tag"] = "main-test-universal"
    inventory["track_registry_content_sha256"] = registry["content_sha256"]
    inventory["content_sha256"] = core_track_inventory_content_sha256(inventory)
    with pytest.raises(
        PipelineError,
        match="inventory group does not match the matrix coordinate",
    ):
        project_track_inventory_cell_v1(
            inventory,
            coordinate=MatrixCoordinateV1(
                core_id="gambatte",
                track="main",
                chipset="universal",
                architecture="arm64",
            ),
            track_registry=registry,
            predecessor_cell=object(),  # type: ignore[arg-type]
            evidence=object(),  # type: ignore[arg-type]
            producer_coordinate=object(),  # type: ignore[arg-type]
        )


def test_preserved_branch_observation_rejects_same_id_digest_drift() -> None:
    coordinate = coordinate_for_ordinal("synthetic_core", 0)
    predecessor = _synthetic_supported_cell(
        coordinate=coordinate,
        basis_id="spruce-main",
        basis_content_sha256=_digest("1"),
    )
    row = {
        "spruce_branch_basis": {
            "basis_id": "spruce-main",
            "basis_content_sha256": _digest("2"),
        }
    }
    with pytest.raises(PipelineError, match="branch bases differ"):
        matrix_refresh_module._preserved_observations(
            predecessor,
            coordinate=coordinate,
            row=row,
            admitted=False,
        )


def test_preserved_branch_observation_is_a_deep_copy() -> None:
    coordinate = coordinate_for_ordinal("synthetic_core", 0)
    predecessor = _synthetic_supported_cell(
        coordinate=coordinate,
        basis_id="spruce-main",
        basis_content_sha256=_digest("1"),
    )
    row = {
        "spruce_branch_basis": {
            "basis_id": "spruce-main",
            "basis_content_sha256": _digest("1"),
        }
    }
    _catalog, _edge, branch = matrix_refresh_module._preserved_observations(
        predecessor,
        coordinate=coordinate,
        row=row,
        admitted=False,
    )
    branch["branch"] = "mutated"
    original = decode_matrix_v2(predecessor.legacy_payload_json.encode("utf-8"))
    assert original["branch_artifact_observation"]["branch"] == "Development"


def test_track_summary_rejects_registry_branch_digest_drift() -> None:
    cells = tuple(
        _synthetic_supported_cell(
            coordinate=MatrixCoordinateV1(
                core_id="synthetic_core",
                track=track,
                chipset="universal",
                architecture="arm64",
            ),
            basis_id=f"spruce-{track}",
            basis_content_sha256=_digest(character),
        )
        for track, character in zip(("main", "nightly", "edge"), "123")
    )
    registry = {
        "version_policy": {
            "levels": {"main": "major", "nightly": "minor", "edge": "head"}
        },
        "tracks": {
            track: {
                "spruce_branch_basis": {
                    "basis_id": f"spruce-{track}",
                    "basis_content_sha256": (
                        _digest("4") if track == "main" else _digest(character)
                    ),
                },
                "test": {},
                "stable": {},
            }
            for track, character in zip(("main", "nightly", "edge"), "123")
        },
    }
    with pytest.raises(PipelineError, match="branch authority is inconsistent"):
        matrix_refresh_module._track_summaries(registry, cells)


def test_canonical_producer_uses_full_variant_applicability() -> None:
    universal = {
        "build_pin_id": "synthetic-pin-v1",
        "tuning_profile": "universal-v1",
        "applicable_chipsets": ["a133p", "a523"],
        "version_slice": {},
    }
    exact = {
        "build_pin_id": "synthetic-pin-v1",
        "tuning_profile": "universal-v1",
        "applicable_chipsets": ["a133p"],
        "version_slice": {},
    }
    registry = {
        "tracks": {
            "main": {
                "test": {"synthetic_core": {"universal": universal, "a133p": exact}},
                "deferred": {},
            },
            "nightly": {"test": {}, "deferred": {}},
            "edge": {"test": {}, "deferred": {}},
        }
    }
    row: dict[str, object] = {
        "core_id": "synthetic_core",
        "test_origin_track": "main",
        "selected_chipset": "a133p",
        "pin": {
            "path": "pins/core-sets/synthetic-pin-v1.json",
            "pin_id": "synthetic-pin-v1",
            "file_sha256": _digest("1"),
            "content_sha256": _digest("2"),
        },
        "source_commit": _digest("3")[:40],
        "architectures": ["arm64", "armhf"],
        "tuning": {
            "profile_id": "universal-v1",
            "content_sha256": _digest("4"),
            "properties": {},
            "compiler_argument_mapping_version": "gcc-machine-flags-v1",
            "compiler_arguments": [],
        },
    }
    row["variant_id"] = matrix_refresh_module._inventory_variant_for_cell(
        row, cell_chipset="a133p", cell=exact
    )
    producer = matrix_refresh_module._canonical_producer_coordinate(
        registry, row=row, architecture="arm64"
    )
    assert producer == MatrixCoordinateV1(
        core_id="synthetic_core",
        track="main",
        chipset="a133p",
        architecture="arm64",
    )


def test_root_evidence_rejects_stale_same_id_projection() -> None:
    pin_id = "synthetic-pin-v1"
    record = _synthetic_root_evidence_record()
    payload = _synthetic_admitted_payload(record, pin_id=pin_id)
    stale = copy.deepcopy(record)
    stale["pin"]["content_sha256"] = _digest("f")
    with pytest.raises(PipelineError, match="differs from admitted cells"):
        matrix_refresh_module._cross_validate_root_evidence(
            (payload,), {pin_id: stale}
        )


def test_root_evidence_rejects_same_id_collision() -> None:
    pin_id = "synthetic-pin-v1"
    predecessor = _synthetic_root_evidence_record()
    alternate = copy.deepcopy(predecessor)
    alternate["selected_e2e"]["content_sha256"] = _digest("f")
    with pytest.raises(PipelineError, match="pin_id collision"):
        matrix_refresh_module._merge_root_evidence_records(
            {pin_id: predecessor}, ((pin_id, alternate),)
        )


def test_root_evidence_merge_is_deterministic_and_deep_copying() -> None:
    first = _synthetic_root_evidence_record(core_id="first_core")
    second = _synthetic_root_evidence_record(core_id="second_core")
    predecessor = {"z-pin": second, "a-pin": first}
    before = copy.deepcopy(predecessor)
    merged = matrix_refresh_module._merge_root_evidence_records(
        predecessor, ()
    )
    assert list(merged) == ["a-pin", "z-pin"]
    assert predecessor == before
    merged["a-pin"]["pin"]["path"] = "mutated.json"
    assert predecessor == before


def test_root_evidence_rejects_disagreeing_run_identity() -> None:
    pin_id = "synthetic-pin-v1"
    record = _synthetic_root_evidence_record()
    first = _synthetic_admitted_payload(record, pin_id=pin_id)
    second = copy.deepcopy(first)
    second["evidence"]["selected"]["run_id"] = "selected-run-v2"
    with pytest.raises(PipelineError, match="disagree on evidence identity"):
        matrix_refresh_module._cross_validate_root_evidence(
            (first, second), {pin_id: record}
        )


def test_root_evidence_rejects_deferred_evidence_misuse() -> None:
    payload = {
        "lifecycle": {"admission_state": "deferred"},
        "build_identity": {"pin": None},
        "evidence": {
            **copy.deepcopy(matrix_refresh_module._ABSENT_CELL_EVIDENCE),
            "state": "validated",
        },
    }
    with pytest.raises(PipelineError, match="deferred cell carries"):
        matrix_refresh_module._cross_validate_root_evidence((payload,), {})


def test_replacement_coordinates_reject_partition_and_shard_drift() -> None:
    predecessor = tuple(
        (coordinate_for_ordinal("synthetic_core", ordinal), SUPPORTED_PARTITION)
        for ordinal in range(27)
    )
    assert matrix_refresh_module._require_exact_replacement_coordinates(
        predecessor, predecessor
    ) == "synthetic_core"
    with pytest.raises(PipelineError, match="exactly 27"):
        matrix_refresh_module._require_exact_replacement_coordinates(
            predecessor, predecessor[:-1]
        )
    wrong_partition = list(predecessor)
    wrong_partition[0] = (wrong_partition[0][0], EXCLUSION_PARTITION)
    with pytest.raises(PipelineError, match="support partition"):
        matrix_refresh_module._require_exact_replacement_coordinates(
            predecessor, tuple(wrong_partition)
        )
    wrong_core = list(predecessor)
    wrong_core[0] = (coordinate_for_ordinal("other_core", 0), SUPPORTED_PARTITION)
    with pytest.raises(PipelineError, match="one exact core shard"):
        matrix_refresh_module._require_exact_replacement_coordinates(
            predecessor, tuple(wrong_core)
        )


def test_splicer_rejects_core_spec_authority_override() -> None:
    predecessor = _content_reference(
        kind="artifact",
        path="manifests/core-builds.json",
        file_sha256=_digest("1"),
        content_sha256=_digest("2"),
        size=1,
    )
    alternate = _content_reference(
        kind="artifact",
        path="manifests/alternate-core-builds.json",
        file_sha256=_digest("3"),
        content_sha256=_digest("4"),
        size=1,
    )
    assert matrix_refresh_module._preserved_core_spec_set(
        predecessor, predecessor
    ) is predecessor
    with pytest.raises(PipelineError, match="cannot override"):
        matrix_refresh_module._preserved_core_spec_set(predecessor, alternate)
