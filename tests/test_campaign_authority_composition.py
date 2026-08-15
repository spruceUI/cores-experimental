from __future__ import annotations

import ast
import copy
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.core_pipeline_lib.campaign import (
    authority_composition as composition,
)
from scripts.core_pipeline_lib.campaign import authority_staging
from scripts.core_pipeline_lib.campaign import matrix_refresh
from scripts.core_pipeline_lib.campaign.json_wire import rendered_json_bytes
from scripts.core_pipeline_lib.campaign.matrix_model import MatrixCoordinateV1
from scripts.core_pipeline_lib.campaign.matrix_refresh import (
    DirectoryFingerprintV1,
    HydratedArtifactV1,
    canonical_track_inventory_producer_v1,
    project_track_inventory_cell_v1,
)
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.campaign.phase_freeze import (
    CAMPAIGN_STATE_RELATIVE,
)
from scripts.core_pipeline_lib.campaign.store import CampaignStore
from scripts.core_pipeline_lib.campaign.transition_model import (
    AuthenticatedInput,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes
from scripts.core_pipeline_lib.tracks import (
    core_track_inventory_content_sha256,
    core_tracks_content_sha256,
)


def _digest(character: str) -> str:
    return character * 64


def _input(name: str, document: dict[str, object]) -> AuthenticatedInput:
    raw = rendered_json_bytes(document)
    return AuthenticatedInput(
        name=name,
        reference=EvidenceRef(
            kind="artifact",
            path=f"authorities/{name}.json",
            file_sha256=sha256_bytes(raw),
            target_content_sha256=None,
            size=len(raw),
        ),
        raw=raw,
    )


def _member(
    path: str,
    raw: bytes,
    *,
    inode: int = 1,
) -> composition.RepositorySourceMember:
    return composition.RepositorySourceMember(
        path=path,
        raw=raw,
        mode=0o644,
        device=1,
        inode=inode,
        size=len(raw),
        mtime_ns=1,
        ctime_ns=1,
    )


def _raw_input(
    name: str,
    *,
    path: str,
    raw: bytes,
    target: str | None = None,
) -> AuthenticatedInput:
    return AuthenticatedInput(
        name=name,
        reference=EvidenceRef(
            kind="artifact",
            path=path,
            file_sha256=sha256_bytes(raw),
            target_content_sha256=target,
            size=len(raw),
        ),
        raw=raw,
    )


def _synthetic_producer_inputs() -> tuple[
    dict[str, object], dict[str, object], MatrixCoordinateV1
]:
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
    registry: dict[str, object] = {
        "tracks": {
            "main": {
                "test": {
                    "synthetic_core": {
                        "universal": universal,
                        "a133p": exact,
                    }
                },
                "deferred": {},
            },
            "nightly": {"test": {}, "deferred": {}},
            "edge": {"test": {}, "deferred": {}},
        }
    }
    registry["content_sha256"] = core_tracks_content_sha256(registry)
    coordinate = MatrixCoordinateV1(
        core_id="synthetic_core",
        track="main",
        chipset="a133p",
        architecture="arm64",
    )
    row: dict[str, object] = {
        "core_id": "synthetic_core",
        "track": "main",
        "requested_marker": "test",
        "requested_chipset": "a133p",
        "selected_chipset": "a133p",
        "selected_state": "test",
        "selected_architectures": ["arm64"],
        "test_origin_track": "main",
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
    row["variant_id"] = matrix_refresh._inventory_variant_for_cell(
        row, cell_chipset="a133p", cell=exact
    )
    inventory: dict[str, object] = {
        "schema_version": 2,
        "validation_scope": "static-build-selection-only",
        "local_only": True,
        "publication": "disabled",
        "group_tag": "main-test:a133p",
        "applicability_scope": {},
        "catalog_content_sha256": _digest("5"),
        "track_registry_content_sha256": registry["content_sha256"],
        "tuning_registry_content_sha256": _digest("6"),
        "cores": [row],
        "deferred_cores": [],
        "unsupported_core_ids": [],
        "inventory_state": "unstable",
        "complete": True,
        "summary": {},
        "content_sha256": "",
    }
    inventory["content_sha256"] = core_track_inventory_content_sha256(
        inventory
    )
    return inventory, registry, coordinate


def test_composer_has_one_pure_replay_boundary_and_no_launcher_or_write_calls() -> None:
    module_path = Path(composition.__file__)
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "scripts.core_pipeline" not in imports
    calls = [
        node.func.id
        if isinstance(node.func, ast.Name)
        else node.func.attr
        if isinstance(node.func, ast.Attribute)
        else ""
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    ]
    assert calls.count("replay_matrix_refresh") == 1
    assert not {
        "create_or_verify",
        "create_or_verify_reference",
        "replace_pointer",
        "stage_authority_plan",
        "write_bytes",
        "write_text",
    } & set(calls)


def test_public_producer_matches_projector_gate_and_rejects_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory, registry, coordinate = _synthetic_producer_inputs()
    producer = canonical_track_inventory_producer_v1(
        inventory,
        coordinate=coordinate,
        track_registry=registry,
    )
    assert producer == coordinate

    class _Predecessor:
        pass

    class _Evidence:
        pass

    class _ProducerAccepted(Exception):
        pass

    monkeypatch.setattr(matrix_refresh, "MatrixCellV1", _Predecessor)
    monkeypatch.setattr(matrix_refresh, "TrackCellEvidenceV1", _Evidence)

    def accepted(*_args: object, **_kwargs: object) -> None:
        raise _ProducerAccepted

    monkeypatch.setattr(matrix_refresh, "_validated_evidence", accepted)
    with pytest.raises(_ProducerAccepted):
        project_track_inventory_cell_v1(
            inventory,
            coordinate=coordinate,
            track_registry=registry,
            predecessor_cell=_Predecessor(),  # type: ignore[arg-type]
            evidence=_Evidence(),  # type: ignore[arg-type]
            producer_coordinate=producer,
        )

    drift = MatrixCoordinateV1(
        core_id=coordinate.core_id,
        track="main",
        chipset="universal",
        architecture=coordinate.architecture,
    )
    with pytest.raises(PipelineError, match="canonical first use"):
        project_track_inventory_cell_v1(
            inventory,
            coordinate=coordinate,
            track_registry=registry,
            predecessor_cell=_Predecessor(),  # type: ignore[arg-type]
            evidence=_Evidence(),  # type: ignore[arg-type]
            producer_coordinate=drift,
        )


def test_producer_rejects_obsolete_hyphen_inventory_group() -> None:
    inventory, registry, coordinate = _synthetic_producer_inputs()
    stale = copy.deepcopy(inventory)
    stale["group_tag"] = "main-test-a133p"
    stale["content_sha256"] = core_track_inventory_content_sha256(stale)
    with pytest.raises(PipelineError, match="group does not match"):
        canonical_track_inventory_producer_v1(
            stale,
            coordinate=coordinate,
            track_registry=registry,
        )


def test_inventory_construction_covers_27_rows_with_24_canonical_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = {"cores": {"gambatte": {}, **{f"core{i}": {} for i in range(97)}}}
    authorities = {
        name: _input(name, document)
        for name, document in {
            "catalog": catalog,
            "tracks": {"tracks": {}},
            "tunings": {},
            "spruce-release-roster": {},
            "spruce-branch-bases": {},
            "telemetry-schema": {},
        }.items()
    }
    calls: list[dict[str, object]] = []

    def construct(
        _tracks: object,
        **kwargs: object,
    ) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "group_tag": kwargs["group_tag"],
            "cores": [{"core_id": "gambatte"}],
            "deferred_cores": [],
            "content_sha256": _digest("7"),
        }

    monkeypatch.setattr(composition, "construct_core_track_inventory", construct)
    verifier = lambda *_args: True
    inventories, by_ordinal, returned_catalog, returned_tracks = (
        composition._construct_inventories(
            authorities=authorities,
            pin_index={},
            source_registry_index={},
            source_ancestry_verifier=verifier,
        )
    )
    assert len(inventories) == 24
    assert len(by_ordinal) == 27
    assert returned_catalog == catalog
    assert returned_tracks == {"tracks": {}}
    assert len(calls) == 24
    assert all(call["requested_cores"] == ["gambatte"] for call in calls)
    assert all(call["source_ancestry_core_id"] == "gambatte" for call in calls)
    assert all(call["source_ancestry_verifier"] is verifier for call in calls)
    assert all(
        isinstance(call["group_tag"], str) and ":" in call["group_tag"]
        for call in calls
    )


def test_capture_extension_rejects_same_size_second_capture_drift(
    tmp_path: Path,
) -> None:
    for relative, raw in {
        "authority.json": b"one\n",
        f"{composition.PIN_DIRECTORY_PATH}/pin.json": b"pin\n",
        f"{composition.TRACK_SNAPSHOT_DIRECTORY_PATH}/snapshot.json": b"snap\n",
    }.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o644)
    earlier = composition._capture_sources(
        tmp_path, exact_paths=("authority.json",)
    )
    authority = tmp_path / "authority.json"
    authority.write_bytes(b"two\n")
    authority.chmod(0o644)
    later = composition._capture_sources(
        tmp_path, exact_paths=("authority.json",)
    )
    assert earlier != later
    with pytest.raises(PipelineError, match="moved during discovery"):
        composition._require_capture_extension(earlier, later)


def test_pin_index_requires_exact_directory_coverage_and_raw_identity() -> None:
    first_raw = b"first pin"
    second_raw = b"second pin"
    first_path = f"{composition.PIN_DIRECTORY_PATH}/first.json"
    second_path = f"{composition.PIN_DIRECTORY_PATH}/second.json"
    members = {
        first_path: _member(first_path, first_raw),
        second_path: _member(second_path, second_raw, inode=2),
    }
    index = {
        "first": {
            "path": first_path,
            "file_sha256": sha256_bytes(first_raw),
        },
        "second": {
            "path": second_path,
            "file_sha256": sha256_bytes(second_raw),
        },
    }
    composition._require_pin_index(index, members)
    with pytest.raises(PipelineError, match="does not cover"):
        composition._require_pin_index({"first": index["first"]}, members)
    drifted = copy.deepcopy(index)
    drifted["second"]["file_sha256"] = _digest("f")
    with pytest.raises(PipelineError, match="raw identity differs"):
        composition._require_pin_index(drifted, members)


def test_source_registry_index_requires_exact_coverage_and_raw_identity() -> None:
    first_raw = b"first snapshot"
    second_raw = b"second snapshot"
    first_path = f"{composition.TRACK_SNAPSHOT_DIRECTORY_PATH}/first.json"
    second_path = f"{composition.TRACK_SNAPSHOT_DIRECTORY_PATH}/second.json"
    members = {
        first_path: _member(first_path, first_raw),
        second_path: _member(second_path, second_raw, inode=2),
    }
    index = {
        _digest("1"): {
            "path": first_path,
            "file_sha256": sha256_bytes(first_raw),
        },
        _digest("2"): {
            "path": second_path,
            "file_sha256": sha256_bytes(second_raw),
        },
    }
    composition._require_source_registry_index(index, members)
    with pytest.raises(PipelineError, match="does not cover"):
        composition._require_source_registry_index(
            {_digest("1"): index[_digest("1")]}, members
        )
    drifted = copy.deepcopy(index)
    drifted[_digest("2")]["file_sha256"] = _digest("f")
    with pytest.raises(PipelineError, match="raw identity differs"):
        composition._require_source_registry_index(drifted, members)


def test_evidence_closure_rejects_missing_path_and_raw_mismatch() -> None:
    raw = b"shared evidence"
    binding = composition._FileBinding(
        path="evidence/shared.json", file_sha256=sha256_bytes(raw)
    )
    seed = composition._EvidenceSeed(
        pin=binding,
        golden=binding,
        selected_e2e=binding,
        reproduction_e2e=binding,
        telemetry_schema=binding,
    )
    evidence = composition._EvidenceClosure(
        seed=seed,
        selected_telemetry=binding,
        reproduction_telemetry=binding,
        selected_build_records=(("arm64", binding), ("armhf", binding)),
        reproduction_build_records=(("arm64", binding), ("armhf", binding)),
    )
    members = {binding.path: _member(binding.path, raw)}
    composition._require_evidence_bindings(evidence, members)
    with pytest.raises(PipelineError, match="absent from the source capture"):
        composition._require_evidence_bindings(evidence, {})
    with pytest.raises(PipelineError, match="raw identity moved"):
        composition._require_evidence_bindings(
            evidence, {binding.path: _member(binding.path, b"other")}
        )


def test_pin_directory_must_be_exact_one_pin_extension() -> None:
    prior = DirectoryFingerprintV1(
        path=composition.PIN_DIRECTORY_PATH,
        files=(
            HydratedArtifactV1(
                path=f"{composition.PIN_DIRECTORY_PATH}/prior.json",
                raw=b"prior",
            ),
        ),
    )
    current = DirectoryFingerprintV1(
        path=composition.PIN_DIRECTORY_PATH,
        files=(
            HydratedArtifactV1(
                path=f"{composition.PIN_DIRECTORY_PATH}/gambatte.json",
                raw=b"gambatte",
            ),
            *prior.files,
        ),
    )
    composition._require_post_gambatte_pin_directory(
        prior.to_document(),
        current=current,
        gambatte_pin_path=f"{composition.PIN_DIRECTORY_PATH}/gambatte.json",
    )

    drifted = DirectoryFingerprintV1(
        path=composition.PIN_DIRECTORY_PATH,
        files=(
            current.files[0],
            HydratedArtifactV1(
                path=f"{composition.PIN_DIRECTORY_PATH}/prior.json",
                raw=b"other",
            ),
        ),
    )
    with pytest.raises(PipelineError, match="predecessor pin entry moved"):
        composition._require_post_gambatte_pin_directory(
            prior.to_document(),
            current=drifted,
            gambatte_pin_path=f"{composition.PIN_DIRECTORY_PATH}/gambatte.json",
        )


def test_track_snapshot_fingerprint_must_match_predecessor_exactly() -> None:
    prior = DirectoryFingerprintV1(
        path=composition.TRACK_SNAPSHOT_DIRECTORY_PATH,
        files=(
            HydratedArtifactV1(
                path=(
                    f"{composition.TRACK_SNAPSHOT_DIRECTORY_PATH}/snapshot.json"
                ),
                raw=b"prior",
            ),
        ),
    )
    composition._require_unchanged_track_snapshot_directory(
        prior.to_document(), current=prior
    )
    drifted = DirectoryFingerprintV1(
        path=composition.TRACK_SNAPSHOT_DIRECTORY_PATH,
        files=(
            HydratedArtifactV1(path=prior.files[0].path, raw=b"drift"),
        ),
    )
    with pytest.raises(PipelineError, match="moved from the selected predecessor"):
        composition._require_unchanged_track_snapshot_directory(
            prior.to_document(), current=drifted
        )


def test_copy_payload_bridge_matches_staging_recipe(tmp_path: Path) -> None:
    store = CampaignStore(tmp_path, CAMPAIGN_STATE_RELATIVE)
    raw = b"authority-member"
    source = EvidenceRef(
        kind="artifact",
        path="authorities/member.bin",
        file_sha256=sha256_bytes(raw),
        target_content_sha256=_digest("8"),
        size=len(raw),
    )
    item = AuthenticatedInput(name="member", reference=source, raw=raw)
    (payload,) = composition._copy_payloads(store, (item,))
    assert payload.copy.name == "matrix.member.member"
    assert payload.copy.source == source
    assert payload.copy.stored == store.reference_for(
        kind=source.kind,
        raw=raw,
        target_content_sha256=source.target_content_sha256,
    )
    assert payload.raw == raw


def test_current_state_root_binds_pointer_alias_by_exact_raw_identity(
    tmp_path: Path,
) -> None:
    store = CampaignStore(tmp_path, CAMPAIGN_STATE_RELATIVE)
    matrix_raw = b"synthetic matrix"
    matrix_target = _digest("9")
    current = store.reference_for(
        kind="matrix-snapshot",
        raw=matrix_raw,
        target_content_sha256=matrix_target,
    )
    plan = EvidenceRef(
        kind="transition-plan",
        path="evidence/plan.json",
        file_sha256=_digest("1"),
        target_content_sha256=_digest("2"),
        size=1,
    )
    receipt = EvidenceRef(
        kind="validation-receipt",
        path="evidence/receipt.json",
        file_sha256=_digest("3"),
        target_content_sha256=_digest("4"),
        size=1,
    )
    state = composition.StateRoot(
        campaign_id=composition.CAMPAIGN_ID,
        generation=1,
        transition_id="synthetic-prior-v1",
        plan=plan,
        receipt=receipt,
        current=current,
    )
    state_raw = rendered_json_bytes(state.to_document())
    state_ref = store.reference_for(
        kind="state-root",
        raw=state_raw,
        target_content_sha256=state.content_sha256,
    )
    store.create_or_verify(reference=state_ref, raw=state_raw)
    pointer = EvidenceRef(
        kind="matrix-pointer",
        path=composition.MATRIX_POINTER_PATH,
        file_sha256=current.file_sha256,
        target_content_sha256=current.target_content_sha256,
        size=current.size,
    )
    assert composition._authenticate_current_root(
        store, reference=state_ref, pointer=pointer
    ) == state
    with pytest.raises(PipelineError, match="does not select"):
        composition._authenticate_current_root(
            store,
            reference=state_ref,
            pointer=replace(pointer, target_content_sha256=_digest("f")),
        )


def test_predecessor_authentication_rejects_normalized_and_raw_pointer_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predecessor = SimpleNamespace(
        root=SimpleNamespace(
            legacy_matrix=SimpleNamespace(semantic_sha256=_digest("a")),
            phase_freeze=object(),
            core_spec_set=object(),
        )
    )
    member = _member(composition.MATRIX_POINTER_PATH, b"live matrix")
    monkeypatch.setattr(
        composition, "load_normalized_matrix", lambda *_args: predecessor
    )
    monkeypatch.setattr(
        composition, "normalize_matrix_v2", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        composition, "materialize_matrix_v2", lambda *_args: member.raw
    )
    with pytest.raises(PipelineError, match="differs from the selected"):
        composition._authenticate_predecessor(
            object(),  # type: ignore[arg-type]
            predecessor_matrix_root_ref=EvidenceRef(
                kind="matrix-root",
                path="evidence/predecessor.json",
                file_sha256=_digest("b"),
                target_content_sha256=_digest("c"),
                size=1,
            ),
            pointer_member=member,
        )

    monkeypatch.setattr(
        composition,
        "normalize_matrix_v2",
        lambda *_args, **_kwargs: predecessor,
    )
    monkeypatch.setattr(
        composition, "materialize_matrix_v2", lambda *_args: b"other matrix"
    )
    with pytest.raises(PipelineError, match="differs from the selected"):
        composition._authenticate_predecessor(
            object(),  # type: ignore[arg-type]
            predecessor_matrix_root_ref=EvidenceRef(
                kind="matrix-root",
                path="evidence/predecessor.json",
                file_sha256=_digest("b"),
                target_content_sha256=_digest("c"),
                size=1,
            ),
            pointer_member=member,
        )


def test_matrix_members_reject_name_and_path_collisions() -> None:
    first = _raw_input(
        "first", path="evidence/shared.json", raw=b"first"
    )
    repeated_name = _raw_input(
        "first", path="evidence/other.json", raw=b"other"
    )
    with pytest.raises(PipelineError, match="names collide"):
        composition._canonical_matrix_members((first, repeated_name))

    repeated_path = _raw_input(
        "second", path="evidence/shared.json", raw=b"first"
    )
    with pytest.raises(PipelineError, match="paths collide"):
        composition._canonical_matrix_members((first, repeated_path))


def test_result_model_rejects_transition_phase_and_member_tamper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase_successor = EvidenceRef(
        kind="phase-freeze-cas",
        path="evidence/phase.json",
        file_sha256=_digest("1"),
        target_content_sha256=_digest("2"),
        size=1,
    )

    class _Phase:
        def __init__(self) -> None:
            self.result = SimpleNamespace(
                plan=SimpleNamespace(
                    transition_id="synthetic-transition-v1",
                    successor=phase_successor,
                )
            )

    class _Matrix:
        def __init__(self, phase: EvidenceRef) -> None:
            self.root = SimpleNamespace(phase_freeze=phase)

    class _Replay:
        def __init__(self, transition_id: str) -> None:
            self.transition_id = transition_id

    monkeypatch.setattr(
        composition, "PlannedRepositoryPhaseFreezeBootstrap", _Phase
    )
    monkeypatch.setattr(composition, "NormalizedMatrixV1", _Matrix)
    monkeypatch.setattr(composition, "MatrixRefreshReplayV1", _Replay)
    monkeypatch.setattr(
        composition, "validate_normalized_matrix", lambda _value: None
    )
    first = _raw_input("a", path="evidence/a.json", raw=b"a")
    second = _raw_input("b", path="evidence/b.json", raw=b"b")
    pointer = EvidenceRef(
        kind="matrix-pointer",
        path=composition.MATRIX_POINTER_PATH,
        file_sha256=_digest("3"),
        target_content_sha256=_digest("4"),
        size=1,
    )
    state_root = EvidenceRef(
        kind="state-root",
        path="evidence/state-root.json",
        file_sha256=_digest("5"),
        target_content_sha256=_digest("6"),
        size=1,
    )
    valid = composition.PlannedRepositoryAuthorityCompositionV1(
        phase_bootstrap=_Phase(),  # type: ignore[arg-type]
        current_state_root_ref=state_root,
        expected_pointer=pointer,
        predecessor_matrix=_Matrix(phase_successor),  # type: ignore[arg-type]
        successor_matrix=_Matrix(phase_successor),  # type: ignore[arg-type]
        matrix_replay=_Replay("synthetic-transition-v1"),  # type: ignore[arg-type]
        matrix_members=(first, second),
    )
    with pytest.raises(PipelineError, match="transition identities differ"):
        replace(valid, matrix_replay=_Replay("tampered"))
    with pytest.raises(PipelineError, match="successor phase is stale"):
        replace(
            valid,
            successor_matrix=_Matrix(
                replace(phase_successor, file_sha256=_digest("f"))
            ),
        )
    with pytest.raises(PipelineError, match="sorted and unique"):
        replace(valid, matrix_members=(second, first))


def test_synthetic_repository_planner_captures_and_composes_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def write(relative: str, raw: bytes) -> None:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o644)

    golden_path = "evidence/golden.json"
    selected_telemetry_path = "evidence/selected-telemetry.json"
    reproduction_telemetry_path = "evidence/reproduction-telemetry.json"
    selected_e2e_path = "evidence/selected-e2e.json"
    reproduction_e2e_path = "evidence/reproduction-e2e.json"
    golden_raw = b"golden"
    selected_telemetry_raw = b"selected telemetry"
    reproduction_telemetry_raw = b"reproduction telemetry"
    write(golden_path, golden_raw)
    write(selected_telemetry_path, selected_telemetry_raw)
    write(reproduction_telemetry_path, reproduction_telemetry_raw)

    build_bindings: dict[tuple[str, str], tuple[str, bytes, str]] = {}
    for role, role_character in (("selected", "1"), ("reproduction", "2")):
        for architecture, architecture_character in (("arm64", "3"), ("armhf", "4")):
            raw = f"{role}-{architecture}-build".encode("utf-8")
            digest = sha256_bytes(raw)
            path = (
                f"{composition.LOCAL_STORE_PATH}/build-records/sha256/"
                f"{digest[:2]}/{digest}"
            )
            write(path, raw)
            build_bindings[(role, architecture)] = (
                path,
                raw,
                role_character + architecture_character,
            )

    def e2e_raw(role: str, telemetry_path: str, telemetry_raw: bytes) -> bytes:
        return rendered_json_bytes(
            {
                "runner": {
                    "telemetry": {
                        "path": telemetry_path,
                        "file_sha256": sha256_bytes(telemetry_raw),
                    }
                },
                "builds": [
                    {
                        "core_id": composition.CORE_ID,
                        "architecture": architecture,
                        "result": "passed",
                        "record_sha256": sha256_bytes(
                            build_bindings[(role, architecture)][1]
                        ),
                    }
                    for architecture in ("arm64", "armhf")
                ],
            }
        )

    selected_e2e_raw = e2e_raw(
        "selected", selected_telemetry_path, selected_telemetry_raw
    )
    reproduction_e2e_raw = e2e_raw(
        "reproduction",
        reproduction_telemetry_path,
        reproduction_telemetry_raw,
    )
    write(selected_e2e_path, selected_e2e_raw)
    write(reproduction_e2e_path, reproduction_e2e_raw)

    gambatte_pin_id = "gambatte-pin-v1"
    gambatte_pin_path = f"{composition.PIN_DIRECTORY_PATH}/gambatte.json"
    prior_pin_path = f"{composition.PIN_DIRECTORY_PATH}/prior.json"
    prior_pin_raw = b"prior pin"
    gambatte_pin_raw = rendered_json_bytes(
        {
            "pin_id": gambatte_pin_id,
            "sources": [
                {
                    "pin_id": gambatte_pin_id,
                    "path": golden_path,
                    "file_sha256": sha256_bytes(golden_raw),
                }
            ],
            "cores": {
                composition.CORE_ID: {
                    "selection": {
                        "host_reproduction": {
                            "selected": {
                                "e2e_record": {
                                    "path": selected_e2e_path,
                                    "sha256": sha256_bytes(selected_e2e_raw),
                                }
                            },
                            "reproduction": {
                                "e2e_record": {
                                    "path": reproduction_e2e_path,
                                    "sha256": sha256_bytes(
                                        reproduction_e2e_raw
                                    ),
                                }
                            },
                        }
                    }
                }
            },
        }
    )
    write(prior_pin_path, prior_pin_raw)
    write(gambatte_pin_path, gambatte_pin_raw)

    snapshot_path = (
        f"{composition.TRACK_SNAPSHOT_DIRECTORY_PATH}/snapshot.json"
    )
    snapshot_raw = b"snapshot"
    write(snapshot_path, snapshot_raw)
    generator_raw = b"synthetic matrix generator"
    write(composition.MATRIX_GENERATOR_PATH, generator_raw)
    pointer_raw = b"synthetic predecessor matrix"
    write(composition.MATRIX_POINTER_PATH, pointer_raw)

    tracks_document = {
        "tracks": {
            "main": {
                "test": {
                    composition.CORE_ID: {
                        "universal": {"build_pin_id": gambatte_pin_id}
                    }
                }
            },
            "nightly": {"test": {}},
            "edge": {"test": {}},
        }
    }
    catalog_document = {
        "cores": {
            composition.CORE_ID: {},
            **{f"core{i}": {} for i in range(97)},
        }
    }
    role_documents = {
        "catalog": catalog_document,
        "spruce-branch-bases": {"branch": "synthetic"},
        "spruce-release-roster": {"release": "synthetic"},
        "telemetry-schema": {"schema": "synthetic"},
        "tracks": tracks_document,
        "tunings": {"tunings": "synthetic"},
        "commit-blacklist": {"commits": []},
        "core-spec-set": {"cores": "synthetic"},
        "host-execution": {"profiles": "synthetic"},
        "toolchain-lock": {"toolchain": "synthetic"},
    }
    role_paths = {
        role: f"authorities/{role}.json" for role in role_documents
    }
    phase_inputs = []
    phase_references: dict[str, EvidenceRef] = {}
    for index, role in enumerate(sorted(role_documents), start=1):
        raw = rendered_json_bytes(role_documents[role])
        write(role_paths[role], raw)
        item = _raw_input(
            role,
            path=role_paths[role],
            raw=raw,
            target=f"{index:064x}",
        )
        phase_inputs.append(item)
        phase_references[role] = item.reference

    engine_raw = rendered_json_bytes({"content_sha256": _digest("e")})
    engine_ref = EvidenceRef(
        kind="engine-bundle",
        path="campaign/evidence/synthetic-engine.json",
        file_sha256=sha256_bytes(engine_raw),
        target_content_sha256=_digest("e"),
        size=len(engine_raw),
    )
    phase_successor = EvidenceRef(
        kind="phase-freeze-cas",
        path="campaign/evidence/synthetic-phase.json",
        file_sha256=_digest("d"),
        target_content_sha256=_digest("c"),
        size=1,
    )
    transition_id = "synthetic-gambatte-refresh-v1"

    class _PhaseResult:
        def __init__(self) -> None:
            self.plan = SimpleNamespace(
                transition_id=transition_id,
                successor=phase_successor,
            )

    class _PhaseBootstrap:
        def __init__(self, source_members: tuple[object, ...]) -> None:
            self.request = SimpleNamespace(
                inputs=tuple(sorted(phase_inputs, key=lambda item: item.name)),
                engine_bundle_ref=engine_ref,
                engine_bundle_raw=engine_raw,
            )
            self.result = _PhaseResult()
            self.source_members = source_members

    overlap_paths = tuple(
        sorted(
            {
                composition.MATRIX_POINTER_PATH,
                composition.MATRIX_GENERATOR_PATH,
                *(role_paths[role] for role in composition._AUTHORITY_INPUT_ROLES),
            }
        )
    )

    def phase_plan(**_kwargs: object) -> _PhaseBootstrap:
        capture = composition._capture_sources(
            tmp_path, exact_paths=overlap_paths
        )
        return _PhaseBootstrap(capture.members)

    pin_index = {
        "prior-pin-v1": {
            "pin_id": "prior-pin-v1",
            "path": prior_pin_path,
            "file_sha256": sha256_bytes(prior_pin_raw),
        },
        gambatte_pin_id: {
            "pin_id": gambatte_pin_id,
            "path": gambatte_pin_path,
            "file_sha256": sha256_bytes(gambatte_pin_raw),
        },
    }
    source_index = {
        _digest("a"): {
            "path": snapshot_path,
            "file_sha256": sha256_bytes(snapshot_raw),
        }
    }
    pin_loader_calls = 0
    source_loader_calls = 0

    def pin_loader(*, services: object) -> dict[str, dict[str, object]]:
        nonlocal pin_loader_calls
        assert services is pin_services
        pin_loader_calls += 1
        return copy.deepcopy(pin_index)

    def source_loader(_root: Path) -> dict[str, dict[str, object]]:
        nonlocal source_loader_calls
        source_loader_calls += 1
        return copy.deepcopy(source_index)

    prior_fingerprint = DirectoryFingerprintV1(
        path=composition.PIN_DIRECTORY_PATH,
        files=(HydratedArtifactV1(path=prior_pin_path, raw=prior_pin_raw),),
    )
    snapshot_fingerprint = DirectoryFingerprintV1(
        path=composition.TRACK_SNAPSHOT_DIRECTORY_PATH,
        files=(HydratedArtifactV1(path=snapshot_path, raw=snapshot_raw),),
    )

    class _Matrix:
        def __init__(self, *, phase: EvidenceRef, legacy_root_json: str) -> None:
            self.root = SimpleNamespace(
                phase_freeze=phase,
                core_spec_set=phase_references["core-spec-set"],
                legacy_root_json=legacy_root_json,
            )

    predecessor_root_raw = rendered_json_bytes(
        {
            "inputs": {
                "pin_directory": prior_fingerprint.to_document(),
                "track_registry_snapshot_directory": (
                    snapshot_fingerprint.to_document()
                ),
            }
        }
    )
    predecessor = _Matrix(
        phase=phase_successor,
        legacy_root_json=predecessor_root_raw.decode("utf-8"),
    )
    root_roles = {
        "catalog": "catalog",
        "commit_blacklist": "commit-blacklist",
        "branch_bases": "spruce-branch-bases",
        "release_roster": "spruce-release-roster",
        "host_execution_profiles": "host-execution",
        "host_telemetry_schema": "telemetry-schema",
        "toolchain_lock": "toolchain-lock",
        "tracks": "tracks",
        "tunings": "tunings",
    }
    successor_inputs = {
        root_name: {
            "path": phase_references[role].path,
            "file_sha256": phase_references[role].file_sha256,
            "content_sha256": phase_references[role].target_content_sha256,
        }
        for root_name, role in root_roles.items()
    }
    successor_inputs.update(
        {
            "pin_directory": prior_fingerprint.to_document(),
            "track_registry_snapshot_directory": (
                snapshot_fingerprint.to_document()
            ),
        }
    )
    successor_root_raw = rendered_json_bytes({"inputs": successor_inputs})
    successor = _Matrix(
        phase=phase_successor,
        legacy_root_json=successor_root_raw.decode("utf-8"),
    )
    expected_pointer = EvidenceRef(
        kind="matrix-pointer",
        path=composition.MATRIX_POINTER_PATH,
        file_sha256=sha256_bytes(pointer_raw),
        target_content_sha256=_digest("b"),
        size=len(pointer_raw),
    )

    def inventories(**_kwargs: object):
        result: dict[str, dict[str, object]] = {}
        by_ordinal: dict[int, str] = {}
        for ordinal in range(27):
            coordinate = composition.coordinate_for_ordinal(
                composition.CORE_ID, ordinal
            )
            group_tag = composition.canonical_group_tag(
                coordinate.track, "test", coordinate.chipset
            )
            if group_tag not in result:
                admitted = coordinate.track != "edge"
                result[group_tag] = {
                    "group_tag": group_tag,
                    "catalog_content_sha256": phase_references[
                        "catalog"
                    ].target_content_sha256,
                    "track_registry_content_sha256": phase_references[
                        "tracks"
                    ].target_content_sha256,
                    "tuning_registry_content_sha256": phase_references[
                        "tunings"
                    ].target_content_sha256,
                    "cores": [{"core_id": composition.CORE_ID}]
                    if admitted
                    else [],
                    "deferred_cores": []
                    if admitted
                    else [{"core_id": composition.CORE_ID}],
                    "content_sha256": _digest("f"),
                }
            by_ordinal[ordinal] = group_tag
        return result, by_ordinal, catalog_document, tracks_document

    replay_calls: list[tuple[object, ...]] = []

    def replay(
        _predecessor: object,
        *,
        replay: object,
        copies: tuple[object, ...],
        phase_freeze: EvidenceRef,
        captured_at: str,
    ) -> _Matrix:
        assert phase_freeze == phase_successor
        assert captured_at == "2026-08-15T05:00:00Z"
        replay_calls.append((replay, *copies))
        return successor

    monkeypatch.setattr(
        composition, "PlannedRepositoryPhaseFreezeBootstrap", _PhaseBootstrap
    )
    monkeypatch.setattr(composition, "NormalizedMatrixV1", _Matrix)
    monkeypatch.setattr(
        composition, "validate_normalized_matrix", lambda _value: None
    )
    monkeypatch.setattr(
        composition, "plan_repository_phase_freeze_bootstrap", phase_plan
    )
    monkeypatch.setattr(
        composition, "load_authoritative_core_pin_index", pin_loader
    )
    monkeypatch.setattr(
        composition, "load_core_track_source_registry_index", source_loader
    )
    monkeypatch.setattr(
        composition,
        "core_track_source_ancestry_verifier",
        lambda **_kwargs: lambda *_args: True,
    )
    monkeypatch.setattr(
        composition,
        "_authenticate_predecessor",
        lambda *_args, **_kwargs: (predecessor, expected_pointer),
    )
    monkeypatch.setattr(
        composition, "_authenticate_current_root", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(composition, "_construct_inventories", inventories)
    monkeypatch.setattr(
        composition,
        "canonical_track_inventory_producer_v1",
        lambda _inventory, *, coordinate, track_registry: coordinate,
    )
    monkeypatch.setattr(composition, "replay_matrix_refresh", replay)
    pin_services = composition.PinLifecycleServices(namespace={})
    store = CampaignStore(tmp_path, CAMPAIGN_STATE_RELATIVE)
    result = composition.plan_repository_authority_composition(
        store,
        pin_services=pin_services,
        current_state_root_ref=EvidenceRef(
            kind="state-root",
            path="evidence/current-state.json",
            file_sha256=_digest("5"),
            target_content_sha256=_digest("6"),
            size=1,
        ),
        predecessor_matrix_root_ref=EvidenceRef(
            kind="matrix-root",
            path="evidence/predecessor-root.json",
            file_sha256=_digest("7"),
            target_content_sha256=_digest("8"),
            size=1,
        ),
        captured_at="2026-08-15T05:00:00Z",
        audit_label="synthetic-audit",
        leaf_audit_id="synthetic-leaf",
        reason="synthetic composition replay",
        authoritative_suite_summary="synthetic suite passed",
        transition_id=transition_id,
    )
    assert pin_loader_calls == 2
    assert source_loader_calls == 2
    assert len(result.matrix_replay.cells) == 27
    assert sum(row.evidence is not None for row in result.matrix_replay.cells) == 18
    assert sum(row.evidence is None for row in result.matrix_replay.cells) == 9
    assert all(
        row.source_registry_snapshots == () for row in result.matrix_replay.cells
    )
    assert result.matrix_replay.track_registry_snapshot_directory is None
    assert result.matrix_replay.pin_directory is not None
    assert len(result.matrix_replay.pin_directory.members) == 2
    assert replay_calls and replay_calls[0][0] == result.matrix_replay
    names = tuple(item.name for item in result.matrix_members)
    assert names == tuple(sorted(set(names)))
    assert any(name.startswith("inventory.main.") for name in names)
    assert "engine-bundle" in names
    telemetry_member = next(
        item
        for item in result.matrix_members
        if item.reference.path == role_paths["telemetry-schema"]
    )
    assert telemetry_member.name == composition._source_name(
        role_paths["telemetry-schema"]
    )
    assert telemetry_member.reference == phase_references["telemetry-schema"]
    assert telemetry_member.raw == next(
        item.raw
        for item in result.phase_bootstrap.request.inputs
        if item.name == "telemetry-schema"
    )

    phase_source_copies = []
    for member in result.phase_bootstrap.source_members:
        source = EvidenceRef(
            kind="artifact",
            path=member.path,
            file_sha256=sha256_bytes(member.raw),
            target_content_sha256=None,
            size=len(member.raw),
        )
        phase_source_copies.append(
            authority_staging.AuthorityCopyPayloadV1(
                copy=authority_staging.AuthorityCopyV1(
                    name=(
                        "phase.source."
                        f"{sha256_bytes(member.path.encode())[:24]}"
                    ),
                    source=source,
                    stored=store.reference_for(
                        kind="repository-snapshot",
                        raw=member.raw,
                        target_content_sha256=None,
                    ),
                    source_mode=member.mode,
                ),
                raw=member.raw,
            )
        )
    combined_copies = tuple(
        sorted(
            (
                *phase_source_copies,
                *composition._copy_payloads(store, result.matrix_members),
            ),
            key=lambda item: item.copy.name,
        )
    )
    monkeypatch.setattr(authority_staging, "PlannedPhaseFreeze", _PhaseResult)
    monkeypatch.setattr(authority_staging, "NormalizedMatrixV1", _Matrix)
    monkeypatch.setattr(
        authority_staging, "validate_normalized_matrix", lambda _value: None
    )
    monkeypatch.setattr(
        authority_staging,
        "_phase_authority_references",
        lambda _phase: phase_references,
    )
    authority_staging.validate_h5_h6_authority_bindings(
        phase_result=result.phase_bootstrap.result,
        predecessor_matrix=result.predecessor_matrix,
        successor_matrix=result.successor_matrix,
        matrix_replay=result.matrix_replay,
        copies=combined_copies,
    )


def test_result_fields_are_exact_staging_arguments() -> None:
    assert tuple(field.name for field in fields(
        composition.PlannedRepositoryAuthorityCompositionV1
    )) == (
        "phase_bootstrap",
        "current_state_root_ref",
        "expected_pointer",
        "predecessor_matrix",
        "successor_matrix",
        "matrix_replay",
        "matrix_members",
    )
