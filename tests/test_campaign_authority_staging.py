from __future__ import annotations

import ast
import copy
from dataclasses import fields, replace
import inspect
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

from scripts.core_pipeline_lib.campaign import authority_staging as staging
from scripts.core_pipeline_lib.campaign import phase_freeze_bootstrap as phase_bootstrap
from scripts.core_pipeline_lib.campaign import workflow
from scripts.core_pipeline_lib.campaign.authority_staging import (
    AuthorityCopyV1,
    AuthorityStagePlanV1,
    DirectoryReplayV1,
    EvidenceReplayV1,
    LegacyMatrixStageV1,
    MatrixCellReplayV1,
    MatrixCoreDeltaV1,
    MatrixRefreshReplayV1,
    authoritative_suite_summary,
    decode_authority_stage_plan,
    decode_matrix_refresh_replay,
    render_authority_stage_plan,
    render_matrix_refresh_replay,
)
from scripts.core_pipeline_lib.campaign.json_wire import (
    decode_identity_object,
    rendered_json_bytes,
)
from scripts.core_pipeline_lib.campaign.check_adapter import (
    StoredCheckReceipt,
    run_and_store_check_receipt,
)
from scripts.core_pipeline_lib.campaign.legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
)
from scripts.core_pipeline_lib.campaign.matrix_materialize import (
    derive_legacy_summary,
    materialize_matrix_v2,
    normalize_matrix_v2,
)
from scripts.core_pipeline_lib.campaign.matrix_model import (
    EXCLUSION_PARTITION,
    SUPPORTED_PARTITION,
    MatrixCellV1,
    MatrixCoordinateV1,
    coordinate_for_ordinal,
    legacy_coordinate_order,
)
from scripts.core_pipeline_lib.campaign.model import (
    EvidenceRef,
    StateRoot,
)
from scripts.core_pipeline_lib.campaign.phase_freeze import (
    CAMPAIGN_STATE_RELATIVE,
    plan_phase_freeze,
)
from scripts.core_pipeline_lib.campaign.phase_freeze_bootstrap import (
    PlannedRepositoryPhaseFreezeBootstrap,
    capture_repository_phase_freeze_sources,
    plan_repository_phase_freeze_bootstrap,
)
from scripts.core_pipeline_lib.campaign.store import CampaignStore, StoreResult
from scripts.core_pipeline_lib.campaign.transition_model import (
    AuthenticatedInput,
    NamedEvidenceRef,
    TransitionIntentV1,
    TransitionRequest,
)
from scripts.core_pipeline_lib.checks import (
    CONTROLLED_ENVIRONMENT_KEYS,
    FULL_STATIC_ALLOWED_SKIPS,
    CapturedStructuredOutput,
    CheckReceipt,
    CheckResult,
    CheckStatus,
    CheckTier,
    ResultOrigin,
    StructuredFormat,
    canonical_json_bytes,
    checks_for_tier,
)
from scripts.core_pipeline_lib.checks.artifacts import (
    argv_sha256,
    authenticate_captured_outputs,
    subject_sha256,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes
from scripts.core_pipeline_lib.tracks import (
    canonical_group_tag,
    core_track_inventory_content_sha256,
    core_track_test_assignment_content_sha256,
    core_tracks_content_sha256,
)
from tests import test_campaign_authority_composition as composition_suite
from tests import test_campaign_matrix_materialize as matrix_fixture
from tests import test_campaign_matrix_refresh as matrix_refresh_suite
from tests.test_campaign_check_adapter import _junit_bytes, _pytest_executed_argv
from tests.test_campaign_workflow import WorkflowFixture


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "authority_staging.py"
)
SCHEMA_FILE = ROOT / staging.SCHEMA_PATH
CAPTURED_AT = "2026-08-15T04:00:00Z"


def _digest(number: int) -> str:
    return f"{number:064x}"


def _reference(
    kind: str,
    path: str,
    number: int,
    *,
    target: bool = True,
    size: int = 1,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=_digest(number),
        target_content_sha256=_digest(number + 10_000) if target else None,
        size=size,
    )


def _canonical_reference(
    kind: str,
    number: int,
    *,
    target: bool = True,
    size: int = 1,
) -> EvidenceRef:
    digest = _digest(number)
    return _reference(
        kind,
        (
            f"{CAMPAIGN_STATE_RELATIVE}/objects/{kind}/sha256/"
            f"{digest[:2]}/{digest}"
        ),
        number,
        target=target,
        size=size,
    )


def _copy(
    name: str,
    kind: str,
    path: str,
    number: int,
    *,
    source_mode: int | None = None,
    stored_kind: str | None = None,
) -> AuthorityCopyV1:
    return AuthorityCopyV1(
        name=name,
        source=_reference(kind, path, number),
        stored=_canonical_reference(stored_kind or kind, number),
        source_mode=source_mode,
    )


def _delta(core_id: str, number: int) -> MatrixCoreDeltaV1:
    return MatrixCoreDeltaV1(
        core_id=core_id,
        predecessor_cells=tuple(
            _canonical_reference("matrix-cell", number + ordinal)
            for ordinal in range(27)
        ),
        successor_cells=tuple(
            _canonical_reference("matrix-cell", number + 100 + ordinal)
            for ordinal in range(27)
        ),
        predecessor_shard=_canonical_reference("matrix-shard", number + 200),
        successor_shard=_canonical_reference("matrix-shard", number + 201),
    )


def _legacy(campaign_id: str) -> LegacyMatrixStageV1:
    predecessor = _reference(
        "matrix-pointer",
        f".local-e2e/campaigns/{campaign_id}/campaign-matrix.json",
        600,
        size=11,
    )
    successor = _reference(
        "matrix-pointer",
        predecessor.path,
        601,
        size=12,
    )
    digest = successor.file_sha256
    target = successor.target_content_sha256
    assert target is not None
    common = {
        "file_sha256": digest,
        "target_content_sha256": target,
        "size": successor.size,
    }
    return LegacyMatrixStageV1(
        predecessor_pointer=predecessor,
        successor_pointer=successor,
        canonical_object=EvidenceRef(
            kind="matrix-snapshot",
            path=(
                f"{CAMPAIGN_STATE_RELATIVE}/objects/matrix-snapshot/sha256/"
                f"{digest[:2]}/{digest}"
            ),
            **common,
        ),
        semantic_alias=EvidenceRef(
            kind="matrix-snapshot",
            path=f".local-e2e/campaigns/{campaign_id}/matrices/{target}.json",
            **common,
        ),
        raw_alias=EvidenceRef(
            kind="matrix-cas",
            path=f".local-e2e/store/campaign-matrices/sha256/{digest[:2]}/{digest}",
            **common,
        ),
    )


def _plan(*, changes: tuple[MatrixCoreDeltaV1, ...] | None = None) -> AuthorityStagePlanV1:
    campaign_id = "host-core-build-20260810"
    transition_id = "gambatte-authority-refresh-v1"
    return AuthorityStagePlanV1(
        campaign_id=campaign_id,
        transition_id=transition_id,
        captured_at=CAPTURED_AT,
        schema=_copy("stage.schema", "artifact", staging.SCHEMA_PATH, 1),
        matrix_replay=_copy(
            "matrix.replay",
            "artifact",
            f"campaign/evidence/{transition_id}-matrix-refresh-replay-v1.json",
            2,
        ),
        copies=(
            _copy(
                "phase.engine-bundle",
                "engine-bundle",
                "campaign/evidence/engine.json",
                3,
            ),
        ),
        current_state_root=_canonical_reference("state-root", 4),
        phase_plan=_canonical_reference("transition-plan", 5),
        phase_successor=_canonical_reference("phase-freeze-cas", 6),
        predecessor_matrix_root=_canonical_reference("matrix-root", 7),
        successor_matrix_root=_canonical_reference("matrix-root", 8),
        matrix_changes=changes or (_delta("gambatte", 1_000),),
        legacy_matrix=_legacy(campaign_id),
    )


def _replay() -> MatrixRefreshReplayV1:
    return MatrixRefreshReplayV1(
        transition_id="gambatte-authority-refresh-v1",
        core_id="gambatte",
        cells=tuple(
            MatrixCellReplayV1(
                coordinate=coordinate_for_ordinal("gambatte", ordinal),
                inventory_copy=f"inventory.{ordinal:02d}",
                evidence=None,
                producer_coordinate=None,
                pipeline_bundle_content_sha256=_digest(9_000),
            )
            for ordinal in range(27)
        ),
        audit_label="spruce-core-build-campaign-20260810",
        leaf_audit_id="gambatte-refresh-v1",
        reason="replay one exact post-Gambatte matrix shard",
        predecessor_pointer_path=(
            ".local-e2e/campaigns/host-core-build-20260810/campaign-matrix.json"
        ),
        generator_copy="matrix.generator",
        track_registry_copy="matrix.tracks",
        pipeline_bundle_copy="matrix.pipeline-bundle",
        authoritative_suite_summary=authoritative_suite_summary(passed_count=1),
        edge_source_count=98,
        pin_directory=None,
        track_registry_snapshot_directory=None,
    )


def _start_small_matrix_universe(test_case: unittest.TestCase) -> None:
    """Use one exact 27-cell shard for staging-boundary integration.

    Full 98-core normalization, materialization, and Gambatte replay stay owned
    by their dedicated suites; this test-local universe changes no production
    code path and keeps the durable store/load topology exact.
    """

    values = (
        (
            "scripts.core_pipeline_lib.campaign.matrix_model."
            "EXPECTED_CORE_COUNT",
            1,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_model."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_materialize."
            "EXPECTED_CORE_COUNT",
            1,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_materialize."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_refresh."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_store."
            "EXPECTED_CORE_COUNT",
            1,
        ),
        (
            "scripts.core_pipeline_lib.campaign.matrix_store."
            "EXPECTED_UNIVERSE_CELL_COUNT",
            27,
        ),
    )
    for target, value in values:
        patcher = mock.patch(target, value)
        patcher.start()
        test_case.addCleanup(patcher.stop)


class _RecordingStore(CampaignStore):
    _MEMORY_KINDS = frozenset({"matrix-cell", "matrix-shard", "matrix-root"})

    def __init__(self, repository_root: Path) -> None:
        super().__init__(repository_root, CAMPAIGN_STATE_RELATIVE)
        self.publications: list[EvidenceRef] = []
        self.matrix_objects: dict[tuple[str, str], bytes] = {}

    def create_or_verify(self, *, reference: EvidenceRef, raw: bytes):
        self.publications.append(reference)
        if reference.kind in self._MEMORY_KINDS:
            expected = self.reference_for(
                kind=reference.kind,
                raw=raw,
                target_content_sha256=reference.target_content_sha256,
            )
            if reference != expected:
                raise PipelineError("in-memory matrix reference is not canonical")
            key = (reference.kind, reference.path)
            previous = self.matrix_objects.get(key)
            if previous is not None and previous != raw:
                raise PipelineError("in-memory matrix object collides")
            self.matrix_objects[key] = raw
            return StoreResult(
                reference=reference,
                disposition="verified" if previous is not None else "created",
            )
        return super().create_or_verify(reference=reference, raw=raw)

    def read_exact(self, reference: EvidenceRef) -> bytes:
        if reference.kind in self._MEMORY_KINDS:
            try:
                raw = self.matrix_objects[(reference.kind, reference.path)]
            except KeyError as exc:
                raise PipelineError("in-memory matrix evidence object is missing") from exc
            expected = self.reference_for(
                kind=reference.kind,
                raw=raw,
                target_content_sha256=reference.target_content_sha256,
            )
            if reference != expected:
                raise PipelineError("in-memory matrix evidence is not authentic")
            return raw
        return super().read_exact(reference)

    def create_or_verify_reference(self, *, reference: EvidenceRef, raw: bytes):
        self.publications.append(reference)
        return super().create_or_verify_reference(reference=reference, raw=raw)


class _ReceiptRunner:
    def __init__(self, receipt: CheckReceipt) -> None:
        self.receipt = receipt

    def run_tier(self, tier, *, subject, parameters_by_check=None):
        if tier is not CheckTier.EVIDENCE or subject != self.receipt.subject:
            raise AssertionError("integration receipt runner arguments drifted")
        return self.receipt


def _evidence_receipt(subject: str) -> CheckReceipt:
    results: list[CheckResult] = []
    for index, definition in enumerate(checks_for_tier(CheckTier.EVIDENCE)):
        run_id = f"authority-stage-run-{index:03d}"
        parameters = (
            {
                "arm64_archive": "artifacts/cores-arm64.tar.gz",
                "armhf_archive": "artifacts/cores-armhf.tar.gz",
            }
            if definition.check_id == "evidence.toolchain-downloads"
            else None
        )
        argv = definition.render_argv(parameters)
        executed_argv = argv
        structured_outputs = ()
        skipped = ()
        stdout = "complete stdout\n"
        if definition.check_id == "tests.full-static":
            executed_argv = _pytest_executed_argv(
                argv,
                check_id=definition.check_id,
                subject=subject,
                run_id=run_id,
            )
            report = canonical_json_bytes(
                {
                    "schema_version": 1,
                    "check_id": definition.check_id,
                    "subject_sha256": subject_sha256(subject),
                    "run_id": run_id,
                    "argv_sha256": argv_sha256(argv),
                    "exitstatus": 0,
                    "tests": [
                        {
                            "node_id": "tests/test_synthetic.py::test_passed",
                            "outcome": "passed",
                        },
                        *(
                            {"node_id": node_id, "outcome": "skipped"}
                            for node_id in FULL_STATIC_ALLOWED_SKIPS
                        ),
                    ],
                }
            )
            structured_outputs, skipped = authenticate_captured_outputs(
                definition,
                check_id=definition.check_id,
                subject=subject,
                run_id=run_id,
                argv=argv,
                executed_argv=executed_argv,
                returncode=0,
                outputs=(
                    CapturedStructuredOutput(
                        format=StructuredFormat.JSON,
                        content=report,
                    ),
                    CapturedStructuredOutput(
                        format=StructuredFormat.JUNIT,
                        content=_junit_bytes(FULL_STATIC_ALLOWED_SKIPS),
                    ),
                ),
            )
            stdout = "1 passed, 2 skipped in 0.01s\n"
        results.append(
            CheckResult(
                check_id=definition.check_id,
                tier=definition.tier,
                subject=subject,
                run_id=run_id,
                status=CheckStatus.PASSED,
                origin=ResultOrigin.LOCAL,
                argv=argv,
                executed_argv=executed_argv,
                environment_keys=CONTROLLED_ENVIRONMENT_KEYS,
                duration_milliseconds=1,
                returncode=0,
                signal=None,
                timed_out=False,
                logs_complete=True,
                stdout=stdout,
                stderr="complete stderr\n",
                skipped_tests=skipped,
                structured_outputs=structured_outputs,
                failure_kind=None,
                message=None,
            )
        )
    return CheckReceipt(
        tier=CheckTier.EVIDENCE,
        subject=subject,
        status=CheckStatus.PASSED,
        origin=ResultOrigin.LOCAL,
        attestor_id=None,
        results=tuple(results),
    )


def _write_fixture_file(root: Path, relative: str, raw: bytes, mode: int = 0o644) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)


class _AuthorityH3Fixture(WorkflowFixture):
    spec_path = ".local-e2e/h3-fixture/transition.json"
    engine_path = ".local-e2e/h3-fixture/engine.json"
    schema_path = ".local-e2e/h3-fixture/matrix.schema.json"
    freeze_path = ".local-e2e/h3-fixture/freeze.json"
    pointer_path = (
        ".local-e2e/campaigns/host-core-build-20260810/campaign-matrix.json"
    )

    def configure_successor(
        self,
        *,
        campaign_id: str,
        candidate_raw: bytes,
        candidate_semantic_sha256: str,
    ) -> None:
        self.predecessor_raw = b"synthetic H3 predecessor\n"
        self.candidate_raw = candidate_raw
        self.candidate_semantic_sha256 = candidate_semantic_sha256
        self.predecessor_ref = EvidenceRef(
            kind="matrix-pointer",
            path=self.pointer_path,
            file_sha256=sha256_bytes(self.predecessor_raw),
            target_content_sha256=_digest(61_000),
            size=len(self.predecessor_raw),
        )
        self.spec = replace(
            self.spec,
            transition_id="synthetic-prior-h3-v1",
            campaign_id=campaign_id,
            predecessor=self.predecessor_ref,
        )
        _write_fixture_file(
            self.root,
            self.spec_path,
            rendered_json_bytes(self.spec.to_document()),
        )
        _write_fixture_file(self.root, self.pointer_path, self.predecessor_raw)

    def plan(self, **arguments):
        result = super().plan(**arguments)
        semantic = getattr(
            self,
            "candidate_semantic_sha256",
            result.plan.successor.target_content_sha256,
        )
        successor = replace(
            result.plan.successor,
            target_content_sha256=semantic,
        )
        return replace(result, plan=replace(result.plan, successor=successor))


def _synthetic_phase_bootstrap(repository_root: Path):
    original = plan_repository_phase_freeze_bootstrap(
        repository_root=ROOT,
        captured_at=CAPTURED_AT,
    )
    for member in original.source_members:
        _write_fixture_file(
            repository_root,
            member.path,
            member.raw,
            member.mode,
        )
    _write_fixture_file(
        repository_root,
        staging.SCHEMA_PATH,
        SCHEMA_FILE.read_bytes(),
    )

    tracks_path = repository_root / "manifests/core-tracks.json"
    tracks = decode_identity_object(
        tracks_path.read_bytes(), label="synthetic track registry"
    )
    track_documents = tracks["tracks"]
    assert type(track_documents) is dict
    for track_name in ("main", "nightly", "edge"):
        track = track_documents[track_name]
        assert type(track) is dict
        tests = track["test"]
        deferred = track["deferred"]
        assert type(tests) is dict and type(deferred) is dict
        tests.pop("gambatte", None)
        deferred["gambatte"] = {
            "universal": {
                "reason": "synthetic-authority-stage-deferred",
                "state": "deferred",
            }
        }
    tracks["content_sha256"] = core_tracks_content_sha256(tracks)
    _write_fixture_file(
        repository_root,
        "manifests/core-tracks.json",
        rendered_json_bytes(tracks),
    )
    capture = capture_repository_phase_freeze_sources(
        repository_root=repository_root
    )
    inputs = phase_bootstrap._authority_inputs(capture)
    original_intent = TransitionIntentV1.from_document(original.request.spec_raw)
    intent = replace(
        original_intent,
        inputs=tuple(
            NamedEvidenceRef(name=item.name, reference=item.reference)
            for item in inputs
        ),
    )
    spec_raw = rendered_json_bytes(intent.to_document())
    spec_ref = EvidenceRef(
        kind="transition-spec",
        path=original.request.spec_ref.path,
        file_sha256=sha256_bytes(spec_raw),
        target_content_sha256=intent.content_sha256,
        size=len(spec_raw),
    )
    engine, engine_raw = phase_bootstrap._engine_bundle(capture)
    engine_ref = EvidenceRef(
        kind="engine-bundle",
        path=original.request.engine_bundle_ref.path,
        file_sha256=sha256_bytes(engine_raw),
        target_content_sha256=engine["content_sha256"],  # type: ignore[arg-type]
        size=len(engine_raw),
    )
    request = TransitionRequest(
        spec_ref=spec_ref,
        spec_raw=spec_raw,
        engine_bundle_ref=engine_ref,
        engine_bundle_raw=engine_raw,
        predecessor_raw=original.request.predecessor_raw,
        inputs=inputs,
    )
    result = plan_phase_freeze(request)
    return PlannedRepositoryPhaseFreezeBootstrap(
        request=request,
        result=result,
        source_members=capture.members,
    )


def _ref_projection(
    reference: EvidenceRef,
    *,
    semantic: bool = True,
) -> dict[str, object]:
    result: dict[str, object] = {
        "path": reference.path,
        "file_sha256": reference.file_sha256,
    }
    if semantic:
        result["content_sha256"] = reference.target_content_sha256
    return result


def _candidate_dimension(identity: dict[str, object]) -> dict[str, object]:
    return {
        "state": "candidate",
        "identity": identity,
        "content_sha256": matrix_v2_semantic_sha256(identity),
    }


def _candidate_cell(
    coordinate,
    *,
    branch_basis: dict[str, object],
    pipeline_content_sha256: str,
) -> dict[str, object]:
    dimensions = {
        "source": _candidate_dimension({"source": "synthetic"}),
        "recipe": _candidate_dimension(
            {
                "recipe": "synthetic",
                "pipeline_bundle_content_sha256": pipeline_content_sha256,
            }
        ),
        "toolchain": _candidate_dimension({"toolchain": "synthetic"}),
        "image": _candidate_dimension({"image": "synthetic"}),
        "tuning": _candidate_dimension({"tuning": "synthetic"}),
        "build": _candidate_dimension(
            {
                "architecture": coordinate.architecture,
                "selected_chipset": "universal",
            }
        ),
    }
    identity_material = {
        "core_id": coordinate.core_id,
        "architecture": coordinate.architecture,
        "dimension_content_sha256": {
            name: value["content_sha256"] for name, value in dimensions.items()
        },
    }
    build_identity = {
        "state": "candidate",
        "content_sha256": matrix_v2_semantic_sha256(identity_material),
        "variant_id": None,
        "pin": None,
        **dimensions,
    }
    payload: dict[str, object] = {
        "coordinate": coordinate.to_document(),
        "lifecycle": {
            "evidence_state": "candidate",
            "execution_state": "not-run",
            "admission_state": "deferred",
            "gha_state": "gha-not-requested",
            "reason": "synthetic predecessor candidate",
        },
        "resolution": {
            "requested_chipset": coordinate.chipset,
            "selected_chipset": "universal",
            "selected_state": "deferred",
            "resolution": (
                "exact_deferred"
                if coordinate.chipset == "universal"
                else "universal_deferred_fallback"
            ),
            "origin_track": coordinate.track,
            "assignment_mode": "direct-deferred",
            "requested_assignment_content_sha256": _digest(62_000),
            "selected_assignment_content_sha256": _digest(62_001),
            "catalog_candidate": {"architecture": coordinate.architecture},
            "edge_candidate": {"source": {"status": "unchanged"}},
        },
        "build_identity": build_identity,
        "evidence": {
            "state": "absent-not-run",
            "selected": None,
            "reproduction": None,
            "host_reproduction": None,
            "golden": None,
        },
        "outputs": {"state": "absent-not-run"},
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
        "branch_artifact_observation": {
            "basis": copy.deepcopy(branch_basis),
            "branch": "Development",
            "catalog_cell": {
                "core_id": coordinate.core_id,
                "architecture": coordinate.architecture,
            },
            "artifact_validity": "not-observed",
            "version_alignment": {"state": "synthetic-predecessor"},
        },
        "content_sha256": "",
    }
    payload["content_sha256"] = matrix_v2_semantic_sha256(payload)
    return payload


def _unsafe_replace(value, **changes):
    """Build an adversarial frozen record without invoking its constructor."""

    result = object.__new__(type(value))
    for field in fields(value):
        object.__setattr__(
            result,
            field.name,
            changes.get(field.name, getattr(value, field.name)),
        )
    return result


def _synthetic_inventory(
    *,
    coordinate,
    registry: dict[str, object],
    authorities: dict[str, EvidenceRef],
) -> dict[str, object]:
    tracks = registry["tracks"]
    assert type(tracks) is dict
    track = tracks[coordinate.track]
    assert type(track) is dict
    deferred = track["deferred"]
    assert type(deferred) is dict
    core = deferred["gambatte"]
    assert type(core) is dict
    cell = core["universal"]
    assert type(cell) is dict
    row = {
        "core_id": "gambatte",
        "track": coordinate.track,
        "requested_marker": "test",
        "requested_chipset": coordinate.chipset,
        "selected_chipset": "universal",
        "state": "deferred",
        "reason": cell["reason"],
        "origin_track": coordinate.track,
        "current_assignment_content_sha256": (
            core_track_test_assignment_content_sha256(
                registry,
                track=coordinate.track,
                core_id="gambatte",
                chipset=coordinate.chipset,
            )
        ),
        "resolution": (
            "exact_deferred"
            if coordinate.chipset == "universal"
            else "universal_deferred_fallback"
        ),
        "spruce_branch_basis": copy.deepcopy(track["spruce_branch_basis"]),
    }
    inventory: dict[str, object] = {
        "schema_version": 2,
        "validation_scope": "static-build-selection-only",
        "local_only": True,
        "publication": "disabled",
        "group_tag": canonical_group_tag(
            coordinate.track, "test", coordinate.chipset
        ),
        "applicability_scope": copy.deepcopy(registry["applicability_scope"]),
        "catalog_content_sha256": authorities["catalog"].target_content_sha256,
        "track_registry_content_sha256": authorities[
            "tracks"
        ].target_content_sha256,
        "tuning_registry_content_sha256": authorities[
            "tunings"
        ].target_content_sha256,
        "cores": [],
        "deferred_cores": [row],
        "unsupported_core_ids": [],
        "inventory_state": "deferred",
        "complete": False,
        "summary": {
            "selected_core_count": 0,
            "stable_core_count": 0,
            "unstable_core_count": 0,
            "deferred_core_count": 1,
            "unsupported_core_count": 0,
            "universal_fallback_count": int(
                coordinate.chipset != "universal"
            ),
        },
        "content_sha256": "",
    }
    inventory["content_sha256"] = core_track_inventory_content_sha256(
        inventory
    )
    return inventory


def _synthetic_replay_closure(
    store: CampaignStore,
    phase: PlannedRepositoryPhaseFreezeBootstrap,
):
    authorities = {
        item.name: item.reference
        for item in phase.result.phase_freeze.authorities
    }
    phase_inputs = {item.name: item for item in phase.request.inputs}
    source_members = {item.path: item for item in phase.source_members}
    tracks_input = phase_inputs["tracks"]
    registry = decode_identity_object(
        tracks_input.raw, label="synthetic tracks"
    )
    engine = decode_identity_object(
        phase.request.engine_bundle_raw, label="synthetic engine bundle"
    )
    engine_content = engine["content_sha256"]
    assert type(engine_content) is str

    core_ids = ("gambatte",)
    exclusions: frozenset[tuple[str, int]] = frozenset()
    with mock.patch.object(matrix_fixture, "CORE_IDS", core_ids):
        predecessor_document = matrix_fixture._fixture_document(
            exclusions=exclusions,
            captured_at="2026-08-15T03:00:00Z",
        )
    registry_tracks = registry["tracks"]
    assert type(registry_tracks) is dict
    supported: list[dict[str, object]] = []
    payloads_by_coordinate = {
        (
            coordinate.core_id,
            coordinate.universe_ordinal,
        ): item
        for item in predecessor_document["unsupported_exclusions"]  # type: ignore[union-attr]
        for coordinate in (MatrixCoordinateV1.from_document(item["coordinate"]),)
    }
    for coordinate in (
        coordinate_for_ordinal("gambatte", ordinal) for ordinal in range(27)
    ):
        track = registry_tracks[coordinate.track]
        assert type(track) is dict
        payload = _candidate_cell(
            coordinate,
            branch_basis=track["spruce_branch_basis"],  # type: ignore[arg-type]
            pipeline_content_sha256=engine_content,
        )
        supported.append(payload)
        payloads_by_coordinate[(coordinate.core_id, coordinate.universe_ordinal)] = (
            payload
        )
    predecessor_document["supported_cells"] = supported
    cells = tuple(
        MatrixCellV1(
            universe_ordinal=coordinate.universe_ordinal,
            coordinate=coordinate,
            partition=(
                SUPPORTED_PARTITION
                if coordinate.core_id == "gambatte"
                else EXCLUSION_PARTITION
            ),
            legacy_payload_json=matrix_v2_canonical_bytes(
                payloads_by_coordinate[
                    (coordinate.core_id, coordinate.universe_ordinal)
                ]
            ).decode("utf-8"),
        )
        for coordinate in legacy_coordinate_order(core_ids)
    )
    predecessor_document["summary"] = derive_legacy_summary(tuple(cells))
    expansion = predecessor_document["expansion"]
    assert type(expansion) is dict
    expansion["catalog_core_count"] = len(core_ids)
    predecessor_document["audit"] = {"label": "synthetic-authority-stage"}
    predecessor_document["hash_model"] = {
        "semantic_snapshot_path_template": (
            ".local-e2e/campaigns/host-core-build-20260810/matrices/"
            "<root-content-sha256>.json"
        ),
        "raw_cas_path_template": (
            ".local-e2e/store/campaign-matrices/sha256/"
            "<raw-sha256[0:2]>/<raw-sha256>"
        ),
    }
    generator_path = "scripts/core_pipeline_lib/campaign/matrix_refresh.py"
    generator_member = source_members[generator_path]
    generator_ref = EvidenceRef(
        kind="artifact",
        path=generator_path,
        file_sha256=sha256_bytes(generator_member.raw),
        target_content_sha256=None,
        size=len(generator_member.raw),
    )
    predecessor_document["inputs"] = {
        "branch_bases": _ref_projection(authorities["spruce-branch-bases"]),
        "catalog": _ref_projection(authorities["catalog"]),
        "commit_blacklist": _ref_projection(authorities["commit-blacklist"]),
        "edge_source_snapshot": _ref_projection(authorities["catalog"]),
        "evidence_records": {},
        "generator": _ref_projection(generator_ref, semantic=False),
        "host_execution_profiles": _ref_projection(
            authorities["host-execution"]
        ),
        "host_telemetry_schema": _ref_projection(
            authorities["telemetry-schema"]
        ),
        "phase_freeze": _ref_projection(phase.result.plan.successor),
        "pin_directory": {},
        "pipeline_bundle": {
            "source_phase_freeze_content_sha256": (
                phase.result.plan.successor.target_content_sha256
            ),
            "schema_version": engine["schema_version"],
            "file_count": len(engine["files"]),  # type: ignore[arg-type]
            "content_sha256": engine_content,
        },
        "release_roster": _ref_projection(
            authorities["spruce-release-roster"]
        ),
        "schema": _ref_projection(authorities["schemas"]),
        "toolchain_lock": _ref_projection(authorities["toolchain-lock"]),
        "track_registry_snapshot_directory": {},
        "tracks": _ref_projection(authorities["tracks"]),
        "tunings": _ref_projection(authorities["tunings"]),
    }
    predecessor_raw = matrix_fixture._seal(predecessor_document)
    predecessor = normalize_matrix_v2(
        predecessor_raw,
        phase_freeze=phase.result.plan.successor,
        core_spec_set=authorities["core-spec-set"],
    )

    inventory_by_tag: dict[str, tuple[str, bytes]] = {}
    replay_cells: list[MatrixCellReplayV1] = []
    for coordinate in (
        item.coordinate
        for item in predecessor.cells
        if item.coordinate.core_id == "gambatte"
    ):
        tag = canonical_group_tag(
            coordinate.track, "test", coordinate.chipset
        )
        name = f"inventory-{coordinate.track}-{coordinate.chipset}"
        if tag not in inventory_by_tag:
            inventory = _synthetic_inventory(
                coordinate=coordinate,
                registry=registry,
                authorities=authorities,
            )
            inventory_by_tag[tag] = (name, rendered_json_bytes(inventory))
        replay_cells.append(
            MatrixCellReplayV1(
                coordinate=coordinate,
                inventory_copy=name,
                evidence=None,
                producer_coordinate=None,
                pipeline_bundle_content_sha256=engine_content,
            )
        )

    telemetry = phase_inputs["telemetry-schema"]
    matrix_members: list[AuthenticatedInput] = [
        AuthenticatedInput(
            name="generator",
            reference=generator_ref,
            raw=generator_member.raw,
        ),
        AuthenticatedInput(
            name="pipeline-bundle",
            reference=phase.request.engine_bundle_ref,
            raw=phase.request.engine_bundle_raw,
        ),
        AuthenticatedInput(
            name="telemetry-schema",
            reference=telemetry.reference,
            raw=telemetry.raw,
        ),
        AuthenticatedInput(
            name="tracks",
            reference=tracks_input.reference,
            raw=tracks_input.raw,
        ),
    ]
    for name, raw in inventory_by_tag.values():
        inventory = decode_identity_object(raw, label=name)
        matrix_members.append(
            AuthenticatedInput(
                name=name,
                reference=EvidenceRef(
                    kind="artifact",
                    path=f"campaign/evidence/{name}.json",
                    file_sha256=sha256_bytes(raw),
                    target_content_sha256=inventory["content_sha256"],  # type: ignore[arg-type]
                    size=len(raw),
                ),
                raw=raw,
            )
        )
    member_tuple = tuple(sorted(matrix_members, key=lambda item: item.name))
    replay = MatrixRefreshReplayV1(
        transition_id=phase.result.plan.transition_id,
        core_id="gambatte",
        cells=tuple(replay_cells),
        audit_label="synthetic-authority-stage",
        leaf_audit_id="synthetic-gambatte-refresh-v1",
        reason=phase.result.plan.reason,
        predecessor_pointer_path=_AuthorityH3Fixture.pointer_path,
        generator_copy="generator",
        track_registry_copy="tracks",
        pipeline_bundle_copy="pipeline-bundle",
        authoritative_suite_summary=authoritative_suite_summary(passed_count=1),
        edge_source_count=98,
        pin_directory=None,
        track_registry_snapshot_directory=DirectoryReplayV1(
            path="manifests",
            members=("telemetry-schema",),
        ),
    )
    payloads = tuple(
        staging._copy_payload(
            store,
            name=f"matrix.member.{item.name}",
            source=item.reference,
            raw=item.raw,
        )
        for item in member_tuple
    )
    successor = staging.replay_matrix_refresh(
        predecessor,
        replay=replay,
        copies=payloads,
        phase_freeze=phase.result.plan.successor,
        captured_at=CAPTURED_AT,
    )
    staging.validate_h5_h6_authority_bindings(
        phase_result=phase.result,
        predecessor_matrix=predecessor,
        successor_matrix=successor,
        matrix_replay=replay,
        copies=tuple(
            sorted(
                (*staging._phase_copy_payloads(
                    store, phase.request, phase.source_members
                ), *payloads),
                key=lambda item: item.copy.name,
            )
        ),
    )
    return predecessor, successor, replay, member_tuple


def _resign_planned_matrix_replay(store, planned, replay):
    """Coordinate every replay-derived identity except the binding under test."""

    replay_raw = render_matrix_refresh_replay(replay)
    replay_source = replace(
        planned.plan.matrix_replay.source,
        file_sha256=sha256_bytes(replay_raw),
        target_content_sha256=replay.content_sha256,
        size=len(replay_raw),
    )
    replay_payload = staging._copy_payload(
        store,
        name="matrix.replay",
        source=replay_source,
        raw=replay_raw,
    )
    members = staging._matrix_member_payloads(planned.copies)
    bundle = decode_identity_object(
        members[replay.pipeline_bundle_copy].raw,
        label="coordinated matrix replay pipeline bundle",
    )
    bundle_content = bundle["content_sha256"]
    assert type(bundle_content) is str
    # The real small replay has already authenticated all 27 successor cells.
    # Pointer path and reason affect only the root projection, so coordinated
    # re-sign adversaries reuse those cells and exercise the real projection,
    # splice, materialization, and staging cross-field gates.
    with mock.patch(
        "scripts.core_pipeline_lib.campaign.matrix_refresh."
        "validate_normalized_matrix"
    ):
        root_projection = staging.project_matrix_root_refresh_v1(
            planned.predecessor_matrix,
            cells=planned.successor_matrix.cells,
            captured_at=planned.plan.captured_at,
            audit_label=replay.audit_label,
            leaf_audit_id=replay.leaf_audit_id,
            reason=replay.reason,
            predecessor_pointer_path=replay.predecessor_pointer_path,
            generator=staging._hydrated_member(
                members, replay.generator_copy, label="coordinated matrix generator"
            ),
            phase_freeze=planned.phase_result.plan.successor,
            track_registry_artifact=staging._hydrated_member(
                members,
                replay.track_registry_copy,
                label="coordinated track registry",
            ),
            pipeline_bundle=staging.PipelineBundleIdentityV1(
                schema_version=bundle["schema_version"],  # type: ignore[arg-type]
                file_count=len(bundle["files"]),  # type: ignore[arg-type]
                content_sha256=bundle_content,
            ),
            authoritative_suite_summary=replay.authoritative_suite_summary,
            edge_source_count=replay.edge_source_count,
            evidence_records=(),
            pin_directory=staging._directory_from_replay(
                replay.pin_directory, members
            ),
            track_registry_snapshot_directory=staging._directory_from_replay(
                replay.track_registry_snapshot_directory, members
            ),
        )
        successor = staging.splice_matrix_core_refresh_v1(
            planned.predecessor_matrix,
            replacement_cells=tuple(
                item
                for item in planned.successor_matrix.cells
                if item.coordinate.core_id == replay.core_id
            ),
            legacy_root_projection=root_projection,
            phase_freeze=planned.phase_result.plan.successor,
        )
    legacy_raw = materialize_matrix_v2(successor)
    legacy = staging._legacy_stage(
        store,
        campaign_id=planned.plan.campaign_id,
        predecessor_pointer=planned.plan.legacy_matrix.predecessor_pointer,
        successor_raw=legacy_raw,
        successor_content_sha256=successor.root.legacy_matrix.semantic_sha256,
    )
    plan = replace(
        planned.plan,
        matrix_replay=replay_payload.copy,
        successor_matrix_root=successor.root_reference,
        matrix_changes=staging._matrix_changes(
            planned.predecessor_matrix,
            successor,
        ),
        legacy_matrix=legacy,
    )
    plan_raw = render_authority_stage_plan(plan)
    return _unsafe_replace(
        planned,
        plan=plan,
        plan_reference=store.reference_for(
            kind="transition-plan",
            raw=plan_raw,
            target_content_sha256=plan.content_sha256,
        ),
        matrix_replay=replay,
        matrix_replay_raw=replay_raw,
        successor_matrix=successor,
        legacy_raw=legacy_raw,
    )


class CampaignAuthorityStagingTests(unittest.TestCase):
    def test_plan_wire_and_stored_schema_are_exact_and_deterministic(self) -> None:
        plan = _plan()
        raw = render_authority_stage_plan(plan)
        self.assertEqual(plan, decode_authority_stage_plan(raw))
        self.assertEqual(raw, render_authority_stage_plan(decode_authority_stage_plan(raw)))

        schema_raw = SCHEMA_FILE.read_bytes()
        schema = decode_identity_object(schema_raw, label="authority-stage schema")
        self.assertEqual(schema_raw, rendered_json_bytes(schema))
        Draft202012Validator.check_schema(schema)
        errors = tuple(Draft202012Validator(schema).iter_errors(plan.to_document()))
        self.assertEqual((), errors)

        tampered = plan.to_document()
        tampered["process_tier"] = "quick"
        with self.assertRaises(PipelineError):
            AuthorityStagePlanV1.from_document(tampered)

    def test_schema_and_state_root_semantic_targets_are_not_caller_facts(self) -> None:
        schema_raw = SCHEMA_FILE.read_bytes()
        schema = decode_identity_object(schema_raw, label="authority-stage schema")
        schema_digest = staging.canonical_json_sha256(schema)
        plan = _plan()
        schema_copy = replace(
            plan.schema,
            source=replace(
                plan.schema.source,
                target_content_sha256=schema_digest,
            ),
            stored=replace(
                plan.schema.stored,
                target_content_sha256=schema_digest,
            ),
        )
        bound_plan = replace(plan, schema=schema_copy)
        staging._validate_schema(schema_raw, bound_plan)
        for field_name in ("source", "stored"):
            reference = getattr(schema_copy, field_name)
            tampered_copy = _unsafe_replace(
                schema_copy,
                **{
                    field_name: replace(
                        reference,
                        target_content_sha256="f" * 64,
                    )
                },
            )
            with self.assertRaisesRegex(PipelineError, "canonical schema"):
                staging._validate_schema(
                    schema_raw,
                    _unsafe_replace(bound_plan, schema=tampered_copy),
                )

        with tempfile.TemporaryDirectory() as temporary:
            store = CampaignStore(Path(temporary), CAMPAIGN_STATE_RELATIVE)
            root = StateRoot(
                campaign_id="semantic-target-test",
                generation=1,
                transition_id="semantic-target-test-v1",
                plan=_canonical_reference("transition-plan", 51_001),
                receipt=_canonical_reference("validation-receipt", 51_002),
                current=_canonical_reference("matrix-snapshot", 51_003),
            )
            raw = rendered_json_bytes(root.to_document())
            wrong = store.reference_for(
                kind="state-root",
                raw=raw,
                target_content_sha256="f" * 64,
            )
            store.create_or_verify(reference=wrong, raw=raw)
            with self.assertRaisesRegex(PipelineError, "semantic reference"):
                staging._state_root_value(store, store, wrong)

    def test_wire_supports_a_sorted_nonempty_multi_core_batch(self) -> None:
        plan = _plan(
            changes=(
                _delta("core_001", 2_000),
                _delta("gambatte", 3_000),
            )
        )
        self.assertEqual(
            ("core_001", "gambatte"),
            tuple(item.core_id for item in plan.matrix_changes),
        )
        self.assertEqual(plan, decode_authority_stage_plan(render_authority_stage_plan(plan)))
        with self.assertRaisesRegex(PipelineError, "sorted and unique"):
            replace(plan, matrix_changes=tuple(reversed(plan.matrix_changes)))

    def test_matrix_replay_wire_covers_one_exact_27_cell_shard(self) -> None:
        replay = _replay()
        raw = render_matrix_refresh_replay(replay)
        self.assertEqual(replay, decode_matrix_refresh_replay(raw))
        self.assertEqual(tuple(range(27)), tuple(
            item.coordinate.universe_ordinal for item in replay.cells
        ))
        with self.assertRaisesRegex(PipelineError, "27 cell rows"):
            replace(replay, cells=replay.cells[:-1])
        with self.assertRaises(PipelineError):
            decode_matrix_refresh_replay(raw.replace(b"gambatte", b"fabricat", 1))

    def test_repository_source_copies_bind_modes_only_for_captured_members(self) -> None:
        source_path = "manifests/example.json"
        source_name = (
            f"phase.source.{sha256_bytes(source_path.encode('utf-8'))[:24]}"
        )
        captured = _copy(
            source_name,
            "artifact",
            source_path,
            100,
            source_mode=0o644,
            stored_kind="repository-snapshot",
        )
        self.assertEqual(captured, AuthorityCopyV1.from_document(captured.to_document()))
        with self.assertRaisesRegex(PipelineError, "bind its source mode"):
            replace(captured, source_mode=None)
        with self.assertRaisesRegex(PipelineError, "name is not canonical"):
            replace(captured, name="phase.source.0123456789abcdef01234567")
        with self.assertRaisesRegex(PipelineError, "only captured"):
            replace(_plan().copies[0], source_mode=0o644)

    def test_full_matrix_materialize_owner_remains_explicit_and_callable(self) -> None:
        materialize_owner = (
            matrix_fixture.CampaignMatrixMaterializeTests.
            test_normalization_closes_all_links_and_round_trips_exact_bytes
        )
        self.assertTrue(callable(materialize_owner))
        materialize_source = inspect.getsource(materialize_owner)
        self.assertIn("validate_normalized_matrix(", materialize_source)
        self.assertIn("materialize_matrix_v2(", materialize_source)
        self.assertIn("self.assertEqual(98, len(closure.shards))", materialize_source)
        self.assertIn("2_646", materialize_source)
        self.assertFalse(getattr(materialize_owner, "__unittest_skip__", False))
        self.assertFalse(getattr(materialize_owner, "pytestmark", ()))

    def test_full_matrix_refresh_and_composition_owners_remain_callable(self) -> None:
        refresh_owner = (
            matrix_refresh_suite.
            test_live_gambatte_projection_changes_one_shard_and_root_in_memory
        )
        composition_owner = (
            composition_suite.
            test_composer_has_one_pure_replay_boundary_and_no_launcher_or_write_calls
        )
        self.assertTrue(callable(refresh_owner))
        self.assertTrue(callable(composition_owner))
        refresh_source = inspect.getsource(refresh_owner)
        for call in (
            "normalize_matrix_v2(",
            "project_matrix_root_refresh_v1(",
            "splice_matrix_core_refresh_v1(",
            "validate_normalized_matrix(",
            "materialize_matrix_v2(",
        ):
            self.assertIn(call, refresh_source)
        self.assertIn(
            'calls.count("replay_matrix_refresh") == 1',
            inspect.getsource(composition_owner),
        )

    def test_exact_h5_h6_authority_rebinds_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = CampaignStore(Path(temporary), CAMPAIGN_STATE_RELATIVE)
            replay = _replay()
            roles = (
                "catalog",
                "commit-blacklist",
                "core-spec-set",
                "host-execution",
                "spruce-branch-bases",
                "spruce-release-roster",
                "telemetry-schema",
                "toolchain-lock",
                "tracks",
                "tunings",
            )
            authorities = {
                name: _reference(
                    "artifact", f"manifests/{name}.json", 60_000 + index
                )
                for index, name in enumerate(roles)
            }

            def source(path: str, raw: bytes, *, target: str | None = None):
                return EvidenceRef(
                    kind="artifact",
                    path=path,
                    file_sha256=sha256_bytes(raw),
                    target_content_sha256=target,
                    size=len(raw),
                )

            generator_raw = b"synthetic generator\n"
            generator_source = source("scripts/generator.py", generator_raw)
            tracks_raw = b'{"tracks":"frozen"}\n'
            tracks_source = source(
                authorities["tracks"].path,
                tracks_raw,
                target=authorities["tracks"].target_content_sha256,
            )
            telemetry_raw = b'{"telemetry":"frozen"}\n'
            telemetry_source = source(
                authorities["telemetry-schema"].path,
                telemetry_raw,
                target=authorities[
                    "telemetry-schema"
                ].target_content_sha256,
            )
            authorities["telemetry-schema"] = telemetry_source
            telemetry_evidence = EvidenceReplayV1(
                pin="matrix.telemetry",
                golden="matrix.telemetry",
                selected_e2e="matrix.telemetry",
                reproduction_e2e="matrix.telemetry",
                selected_telemetry="matrix.telemetry",
                reproduction_telemetry="matrix.telemetry",
                selected_build_record="matrix.telemetry",
                reproduction_build_record="matrix.telemetry",
                telemetry_schema="matrix.telemetry",
            )
            replay = replace(
                replay,
                cells=(
                    replace(
                        replay.cells[0],
                        evidence=telemetry_evidence,
                        producer_coordinate=replay.cells[0].coordinate,
                        pipeline_bundle_content_sha256=None,
                    ),
                    *replay.cells[1:],
                ),
            )

            def phase_source_payload(reference: EvidenceRef, raw: bytes):
                return staging._copy_payload(
                    store,
                    name=(
                        "phase.source."
                        f"{sha256_bytes(reference.path.encode('utf-8'))[:24]}"
                    ),
                    source=reference,
                    raw=raw,
                    stored_kind="repository-snapshot",
                    source_mode=0o644,
                )

            inventory_document = {
                "catalog_content_sha256": authorities[
                    "catalog"
                ].target_content_sha256,
                "track_registry_content_sha256": authorities[
                    "tracks"
                ].target_content_sha256,
                "tuning_registry_content_sha256": authorities[
                    "tunings"
                ].target_content_sha256,
            }
            inventory_raw = matrix_v2_canonical_bytes(inventory_document)
            payloads = [
                phase_source_payload(generator_source, generator_raw),
                phase_source_payload(tracks_source, tracks_raw),
                phase_source_payload(
                    replace(
                        telemetry_source,
                        target_content_sha256=None,
                    ),
                    telemetry_raw,
                ),
                staging._copy_payload(
                    store,
                    name="matrix.member.matrix.generator",
                    source=generator_source,
                    raw=generator_raw,
                ),
                staging._copy_payload(
                    store,
                    name="matrix.member.matrix.tracks",
                    source=tracks_source,
                    raw=tracks_raw,
                ),
                staging._copy_payload(
                    store,
                    name="matrix.member.matrix.telemetry",
                    source=telemetry_source,
                    raw=telemetry_raw,
                ),
            ]
            for ordinal in range(27):
                inventory_source = source(
                    f"campaign/evidence/inventory-{ordinal:02d}.json",
                    inventory_raw,
                )
                payloads.append(
                    staging._copy_payload(
                        store,
                        name=f"matrix.member.inventory.{ordinal:02d}",
                        source=inventory_source,
                        raw=inventory_raw,
                    )
                )
            copies = tuple(sorted(payloads, key=lambda item: item.copy.name))

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

            def legacy_root(
                replacements: dict[str, EvidenceRef] | None = None,
            ) -> str:
                selected = dict(authorities)
                selected.update(replacements or {})
                inputs = {}
                for root_name, role in root_roles.items():
                    reference = selected[role]
                    inputs[root_name] = {
                        "path": reference.path,
                        "file_sha256": reference.file_sha256,
                        "content_sha256": reference.target_content_sha256,
                    }
                return matrix_v2_canonical_bytes({"inputs": inputs}).decode("utf-8")

            class TinyPhase:
                pass

            class TinyRoot:
                def __init__(
                    self,
                    *,
                    core_spec_set: EvidenceRef,
                    legacy_root_json: str,
                ) -> None:
                    self.core_spec_set = core_spec_set
                    self.legacy_root_json = legacy_root_json

            class TinyMatrix:
                def __init__(self, root: TinyRoot) -> None:
                    self.root = root

            predecessor = TinyMatrix(
                TinyRoot(
                    core_spec_set=authorities["core-spec-set"],
                    legacy_root_json=legacy_root(),
                )
            )
            successor = TinyMatrix(
                TinyRoot(
                    core_spec_set=authorities["core-spec-set"],
                    legacy_root_json=legacy_root(),
                )
            )

            def replace_copy(name: str, replacement):
                return tuple(
                    replacement if item.copy.name == name else item
                    for item in copies
                )

            with (
                mock.patch.object(staging, "PlannedPhaseFreeze", TinyPhase),
                mock.patch.object(staging, "NormalizedMatrixV1", TinyMatrix),
                mock.patch.object(staging, "validate_normalized_matrix"),
                mock.patch.object(
                    staging,
                    "_phase_authority_references",
                    return_value=authorities,
                ),
            ):
                arguments = {
                    "phase_result": TinyPhase(),
                    "predecessor_matrix": predecessor,
                    "successor_matrix": successor,
                    "matrix_replay": replay,
                    "copies": copies,
                }
                staging.validate_h5_h6_authority_bindings(**arguments)

                raw_only_telemetry = staging._copy_payload(
                    store,
                    name="matrix.member.matrix.telemetry",
                    source=replace(
                        telemetry_source,
                        target_content_sha256=None,
                    ),
                    raw=telemetry_raw,
                )
                with self.assertRaisesRegex(
                    PipelineError, "telemetry schema differs from H5 authority"
                ):
                    staging.validate_h5_h6_authority_bindings(
                        **{
                            **arguments,
                            "copies": replace_copy(
                                "matrix.member.matrix.telemetry",
                                raw_only_telemetry,
                            ),
                        }
                    )

                alternate_tracks_raw = b'{"tracks":"coordinated-rebind"}\n'
                alternate_tracks_source = source(
                    tracks_source.path,
                    alternate_tracks_raw,
                    target=_digest(70_000),
                )
                alternate_tracks = staging._copy_payload(
                    store,
                    name="matrix.member.matrix.tracks",
                    source=alternate_tracks_source,
                    raw=alternate_tracks_raw,
                )
                with self.assertRaisesRegex(PipelineError, "captured H5 source"):
                    staging.validate_h5_h6_authority_bindings(
                        **{
                            **arguments,
                            "copies": replace_copy(
                                "matrix.member.matrix.tracks", alternate_tracks
                            ),
                        }
                    )

                alternate_inventory_raw = matrix_v2_canonical_bytes(
                    {
                        **inventory_document,
                        "track_registry_content_sha256": _digest(70_001),
                    }
                )
                alternate_inventory = staging._copy_payload(
                    store,
                    name="matrix.member.inventory.00",
                    source=source(
                        "campaign/evidence/inventory-00.json",
                        alternate_inventory_raw,
                    ),
                    raw=alternate_inventory_raw,
                )
                with self.assertRaisesRegex(PipelineError, "inventor.*H5"):
                    staging.validate_h5_h6_authority_bindings(
                        **{
                            **arguments,
                            "copies": replace_copy(
                                "matrix.member.inventory.00", alternate_inventory
                            ),
                        }
                    )

                alternate_authority = _reference(
                    "artifact", "manifests/rebound-tracks.json", 70_002
                )
                alternate_successor = TinyMatrix(
                    TinyRoot(
                        core_spec_set=authorities["core-spec-set"],
                        legacy_root_json=legacy_root(
                            {"tracks": alternate_authority}
                        ),
                    )
                )
                with self.assertRaisesRegex(PipelineError, "legacy input differs"):
                    staging.validate_h5_h6_authority_bindings(
                        **{
                            **arguments,
                            "successor_matrix": alternate_successor,
                        }
                    )

                alternate_core_spec = TinyMatrix(
                    TinyRoot(
                        core_spec_set=_reference(
                            "artifact", "manifests/rebound-spec.json", 70_003
                        ),
                        legacy_root_json=legacy_root(),
                    )
                )
                with self.assertRaisesRegex(PipelineError, "CoreSpec authority"):
                    staging.validate_h5_h6_authority_bindings(
                        **{
                            **arguments,
                            "successor_matrix": alternate_core_spec,
                        }
                    )

    def test_h4_suite_summary_requires_receipt_stdout_and_reporter_agreement(self) -> None:
        report = canonical_json_bytes(
            {
                "tests": [
                    {"node_id": "tests/test_ok.py::test_ok", "outcome": "passed"},
                    *(
                        {"node_id": node_id, "outcome": "skipped"}
                        for node_id in FULL_STATIC_ALLOWED_SKIPS
                    ),
                ]
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = CampaignStore(Path(temporary), "campaign-state")
            artifact = store.reference_for(
                kind="artifact",
                raw=report,
                target_content_sha256=None,
            )
            store.create_or_verify(reference=artifact, raw=report)
            result = SimpleNamespace(
                check_id="tests.full-static",
                structured_outputs=(
                    SimpleNamespace(
                        format=StructuredFormat.JSON,
                        sha256=artifact.file_sha256,
                        size=artifact.size,
                    ),
                ),
                skipped_tests=FULL_STATIC_ALLOWED_SKIPS,
                stdout="1 passed, 2 skipped in 0.01s\n",
            )
            receipt = SimpleNamespace(results=(result,))
            self.assertEqual(
                authoritative_suite_summary(passed_count=1),
                staging._suite_summary_from_process_receipt(
                    store,
                    receipt,
                    (artifact,),
                ),
            )
            result.stdout = "2 passed, 2 skipped in 0.01s\n"
            with self.assertRaisesRegex(PipelineError, "stdout differs"):
                staging._suite_summary_from_process_receipt(
                    store,
                    receipt,
                    (artifact,),
                )

    def test_plan_stage_receipt_last_and_deep_reload_form_one_durable_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository_root = Path(temporary)
            h3 = _AuthorityH3Fixture(repository_root)
            self.addCleanup(h3.close)
            phase = _synthetic_phase_bootstrap(repository_root)
            self.assertIn(
                "manifests/host-build-execution-profiles.schema.json",
                {member.path for member in phase.source_members},
            )
            _start_small_matrix_universe(self)
            replay_patcher = mock.patch.object(
                staging,
                "replay_matrix_refresh",
                wraps=staging.replay_matrix_refresh,
            )
            replay_spy = replay_patcher.start()
            self.addCleanup(replay_patcher.stop)
            predecessor, successor, replay, matrix_members = (
                _synthetic_replay_closure(h3.store, phase)
            )
            self.assertEqual(
                (1, 27, 1, 27),
                (
                    len(predecessor.shards),
                    len(predecessor.cells),
                    len(successor.shards),
                    len(successor.cells),
                ),
            )
            predecessor_raw = materialize_matrix_v2(predecessor)
            h3.configure_successor(
                campaign_id=phase.result.plan.campaign_id,
                candidate_raw=predecessor_raw,
                candidate_semantic_sha256=(
                    predecessor.root.legacy_matrix.semantic_sha256
                ),
            )
            h3_staged = workflow.stage_transition(
                h3.store,
                process_receipt_ref=h3.process_ref,
                clock=lambda: "2026-08-15T03:30:00Z",
            )
            _post, current_state_root_ref = workflow.commit_transition(
                h3.store,
                staged_receipt_ref=h3_staged,
                clock=lambda: "2026-08-15T03:31:00Z",
            )
            pointer = EvidenceRef(
                kind="matrix-pointer",
                path=h3.pointer_path,
                file_sha256=sha256_bytes(predecessor_raw),
                target_content_sha256=(
                    predecessor.root.legacy_matrix.semantic_sha256
                ),
                size=len(predecessor_raw),
            )
            alias_pointer = replace(
                pointer,
                path=(
                    ".local-e2e/campaigns/host-core-build-20260810/"
                    "campaign-matrix-alias.json"
                ),
            )
            _write_fixture_file(
                repository_root,
                alias_pointer.path,
                predecessor_raw,
            )
            state_directory = repository_root / CAMPAIGN_STATE_RELATIVE
            state_before_alias_plan = tuple(
                sorted(
                    (
                        path.relative_to(state_directory).as_posix(),
                        path.read_bytes(),
                    )
                    for path in state_directory.rglob("*")
                    if path.is_file()
                )
            )
            with self.assertRaisesRegex(
                PipelineError, "H3 pointer differs from the planned predecessor"
            ):
                staging.plan_repository_authority_stage(
                    h3.store,
                    phase_bootstrap=phase,
                    current_state_root_ref=current_state_root_ref,
                    expected_pointer=alias_pointer,
                    predecessor_matrix=predecessor,
                    successor_matrix=successor,
                    matrix_replay=replay,
                    matrix_members=matrix_members,
                )
            state_after_alias_plan = tuple(
                sorted(
                    (
                        path.relative_to(state_directory).as_posix(),
                        path.read_bytes(),
                    )
                    for path in state_directory.rglob("*")
                    if path.is_file()
                )
            )
            self.assertEqual(state_before_alias_plan, state_after_alias_plan)
            planned = staging.plan_repository_authority_stage(
                h3.store,
                phase_bootstrap=phase,
                current_state_root_ref=current_state_root_ref,
                expected_pointer=pointer,
                predecessor_matrix=predecessor,
                successor_matrix=successor,
                matrix_replay=replay,
                matrix_members=matrix_members,
            )
            phase_reuses: list[str] = []
            original_plan_phase_freeze = staging.plan_phase_freeze

            def reuse_validated_phase_request(request):
                if request == phase.request:
                    phase_reuses.append(phase.result.plan.content_sha256)
                    return phase.result
                return original_plan_phase_freeze(request)

            phase_patcher = mock.patch.object(
                staging,
                "plan_phase_freeze",
                side_effect=reuse_validated_phase_request,
            )
            phase_patcher.start()
            self.addCleanup(phase_patcher.stop)
            original_validate = staging.validate_planned_authority_stage

            def validate_once_then_reuse(candidate) -> None:
                if candidate == planned:
                    return
                original_validate(candidate)

            validation_patcher = mock.patch.object(
                staging,
                "validate_planned_authority_stage",
                side_effect=validate_once_then_reuse,
            )
            validation_patcher.start()
            self.addCleanup(validation_patcher.stop)
            store = _RecordingStore(repository_root)

            wrong_process = run_and_store_check_receipt(
                runner=_ReceiptRunner(_evidence_receipt("f" * 64)),  # type: ignore[arg-type]
                store=store,
                tier=CheckTier.EVIDENCE,
                subject="f" * 64,
            )
            store.publications.clear()
            with self.assertRaisesRegex(PipelineError, "subject mismatch"):
                staging._require_process_receipt(
                    store,
                    store,
                    planned,
                    wrong_process,
                )
            self.assertEqual([], store.publications)

            process_receipt = run_and_store_check_receipt(
                runner=_ReceiptRunner(
                    _evidence_receipt(planned.plan.content_sha256)
                ),  # type: ignore[arg-type]
                store=store,
                tier=CheckTier.EVIDENCE,
                subject=planned.plan.content_sha256,
            )
            self.assertIsInstance(process_receipt, StoredCheckReceipt)

            semantic_telemetry = next(
                item
                for item in planned.copies
                if item.copy.name == "matrix.member.telemetry-schema"
            )
            phase_telemetry = next(
                item
                for item in planned.copies
                if item.copy.name == "phase.authority.telemetry-schema"
            )
            self.assertIsNotNone(
                semantic_telemetry.copy.stored.target_content_sha256
            )
            self.assertEqual(
                semantic_telemetry.copy.stored,
                phase_telemetry.copy.stored,
            )
            self.assertEqual(
                1,
                staging._plan_receipt_outputs(planned).count(
                    semantic_telemetry.copy.stored
                ),
            )

            raw_only_telemetry = staging._copy_payload(
                store,
                name=semantic_telemetry.copy.name,
                source=replace(
                    semantic_telemetry.copy.source,
                    target_content_sha256=None,
                ),
                raw=semantic_telemetry.raw,
            )
            self.assertNotEqual(
                semantic_telemetry.copy.stored,
                raw_only_telemetry.copy.stored,
            )
            self.assertEqual(
                (
                    semantic_telemetry.copy.stored.kind,
                    semantic_telemetry.copy.stored.path,
                    semantic_telemetry.copy.stored.file_sha256,
                    semantic_telemetry.copy.stored.size,
                ),
                (
                    raw_only_telemetry.copy.stored.kind,
                    raw_only_telemetry.copy.stored.path,
                    raw_only_telemetry.copy.stored.file_sha256,
                    raw_only_telemetry.copy.stored.size,
                ),
            )
            self.assertIsNone(
                raw_only_telemetry.copy.stored.target_content_sha256
            )
            colliding_copies = tuple(
                raw_only_telemetry if item is semantic_telemetry else item
                for item in planned.copies
            )
            colliding_plan = replace(
                planned.plan,
                copies=tuple(item.copy for item in colliding_copies),
            )
            colliding = _unsafe_replace(
                planned,
                plan=colliding_plan,
                copies=colliding_copies,
            )
            store.publications.clear()
            with self.assertRaisesRegex(PipelineError, "outputs collide by kind/path"):
                staging.validate_planned_authority_stage(colliding)
            self.assertEqual([], store.publications)
            with self.assertRaisesRegex(PipelineError, "outputs collide by kind/path"):
                staging.stage_authority_plan(
                    store,
                    colliding,
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)

            def failing_clock() -> str:
                raise RuntimeError("injected receipt clock failure")

            with self.assertRaisesRegex(RuntimeError, "receipt clock failure"):
                staging.stage_authority_plan(
                    store,
                    planned,
                    process_receipt=process_receipt,
                    clock=failing_clock,
                )
            self.assertEqual([], store.publications)

            coordinated_replays = (
                (
                    replace(
                        replay,
                        predecessor_pointer_path=alias_pointer.path,
                    ),
                    "predecessor pointer path differs",
                ),
                (
                    replace(
                        replay,
                        reason="coordinated-but-different-H6-refresh-reason",
                    ),
                    "reason differs from the H5 phase plan",
                ),
            )
            for coordinated_replay, message in coordinated_replays:
                coordinated = _resign_planned_matrix_replay(
                    store,
                    planned,
                    coordinated_replay,
                )
                self.assertNotEqual(
                    planned.successor_matrix.root_reference,
                    coordinated.successor_matrix.root_reference,
                )
                with self.assertRaisesRegex(PipelineError, message):
                    staging.validate_planned_authority_stage(coordinated)
                store.publications.clear()
                with self.assertRaisesRegex(PipelineError, message):
                    staging.stage_authority_plan(
                        store,
                        coordinated,
                        process_receipt=process_receipt,
                    )
                self.assertEqual([], store.publications)

            alias_legacy = replace(
                planned.plan.legacy_matrix,
                predecessor_pointer=alias_pointer,
                successor_pointer=replace(
                    planned.plan.legacy_matrix.successor_pointer,
                    path=alias_pointer.path,
                ),
            )
            alias_plan = replace(planned.plan, legacy_matrix=alias_legacy)
            store.publications.clear()
            with self.assertRaisesRegex(
                PipelineError, "historical H3 closure moved"
            ):
                staging.stage_authority_plan(
                    store,
                    _unsafe_replace(planned, plan=alias_plan),
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)

            phase_source = next(
                item
                for item in planned.copies
                if item.copy.name.startswith("phase.source.")
            )
            alias_name = "phase.source.ffffffffffffffffffffffff"
            if alias_name == phase_source.copy.name:
                alias_name = "phase.source.eeeeeeeeeeeeeeeeeeeeeeee"
            aliased_copy = _unsafe_replace(phase_source.copy, name=alias_name)
            aliased_payload = _unsafe_replace(phase_source, copy=aliased_copy)
            duplicate_source_copies = tuple(
                sorted(
                    (*planned.copies, aliased_payload),
                    key=lambda item: item.copy.name,
                )
            )
            duplicate_source_plan = _unsafe_replace(
                planned.plan,
                copies=tuple(item.copy for item in duplicate_source_copies),
            )
            with self.assertRaisesRegex(PipelineError, "source paths are not unique"):
                staging.validate_planned_authority_stage(
                    _unsafe_replace(
                        planned,
                        plan=duplicate_source_plan,
                        copies=duplicate_source_copies,
                    )
                )

            renamed_source_copies = tuple(
                sorted(
                    (
                        *(
                            item
                            for item in planned.copies
                            if item is not phase_source
                        ),
                        aliased_payload,
                    ),
                    key=lambda item: item.copy.name,
                )
            )
            renamed_source_plan = _unsafe_replace(
                planned.plan,
                copies=tuple(item.copy for item in renamed_source_copies),
            )
            with self.assertRaisesRegex(PipelineError, "name is not canonical"):
                staging.validate_planned_authority_stage(
                    _unsafe_replace(
                        planned,
                        plan=renamed_source_plan,
                        copies=renamed_source_copies,
                    )
                )
            self.assertEqual([], store.publications)

            # Unknown, unused, and missing copy topology is rejected before
            # publication, including syntactically valid unused matrix input.
            unused_raw = b"unused matrix authority\n"
            unused_source = EvidenceRef(
                kind="artifact",
                path="campaign/evidence/unused.json",
                file_sha256=sha256_bytes(unused_raw),
                target_content_sha256=None,
                size=len(unused_raw),
            )
            unused = staging._copy_payload(
                store,
                name="matrix.member.unused",
                source=unused_source,
                raw=unused_raw,
            )
            unused_copies = tuple(
                sorted((*planned.copies, unused), key=lambda item: item.copy.name)
            )
            unused_plan = replace(
                planned.plan,
                copies=tuple(item.copy for item in unused_copies),
            )
            store.publications.clear()
            with self.assertRaisesRegex(PipelineError, "copy graph is not exact"):
                staging.stage_authority_plan(
                    store,
                    _unsafe_replace(
                        planned, plan=unused_plan, copies=unused_copies
                    ),
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)

            used_name = f"matrix.member.{replay.generator_copy}"
            missing_copies = tuple(
                item for item in planned.copies if item.copy.name != used_name
            )
            missing_plan = replace(
                planned.plan,
                copies=tuple(item.copy for item in missing_copies),
            )
            with self.assertRaisesRegex(PipelineError, "copy graph is not exact"):
                staging.stage_authority_plan(
                    store,
                    _unsafe_replace(
                        planned, plan=missing_plan, copies=missing_copies
                    ),
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)
            with self.assertRaisesRegex(PipelineError, "copy name is unknown"):
                replace(
                    planned.plan,
                    copies=tuple(
                        sorted(
                            (
                                *planned.plan.copies,
                                replace(
                                    planned.plan.copies[0],
                                    name="phase.unknown",
                                ),
                            ),
                            key=lambda item: item.name,
                        )
                    ),
                )

            corrupt_replay = _unsafe_replace(
                planned,
                matrix_replay_raw=planned.matrix_replay_raw + b"\n",
            )
            with self.assertRaisesRegex(PipelineError, "replay bytes differ"):
                staging.stage_authority_plan(
                    store,
                    corrupt_replay,
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)

            workflow_addition = repository_root / ".github/workflows/new.yml"
            workflow_addition.write_bytes(b"name: newly-added\n")
            workflow_addition.chmod(0o644)
            with self.assertRaisesRegex(PipelineError, "source differs"):
                staging.stage_authority_plan(
                    store,
                    planned,
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)
            workflow_addition.unlink()

            schema_path = repository_root / staging.SCHEMA_PATH
            schema_raw = schema_path.read_bytes()
            schema_path.write_bytes(schema_raw + b"\n")
            schema_path.chmod(0o644)
            with self.assertRaisesRegex(PipelineError, "schema differs"):
                staging.stage_authority_plan(
                    store,
                    planned,
                    process_receipt=process_receipt,
                )
            self.assertEqual([], store.publications)
            schema_path.write_bytes(schema_raw)
            schema_path.chmod(0o644)

            original_read = store.read_exact
            h4_refs = {
                process_receipt.receipt_ref,
                *process_receipt.artifact_refs,
            }

            class RoutedReader:
                def read_exact(self, reference: EvidenceRef) -> bytes:
                    return original_read(reference)

                def read_pointer(self, _reference: EvidenceRef):
                    raise AssertionError("pointer-free mode read a pointer")

            def reject_h4_bypass(reference: EvidenceRef) -> bytes:
                if reference in h4_refs:
                    raise AssertionError("H4 evidence bypassed the injected reader")
                return original_read(reference)

            original_load = staging.load_staged_authority_plan
            captured_loads = []

            def capture_real_deep_load(
                exact_store,
                staged_receipt_ref,
                *,
                require_live_engine,
            ):
                with mock.patch.object(
                    exact_store,
                    "read_exact",
                    side_effect=reject_h4_bypass,
                ):
                    result = original_load(
                        exact_store,
                        staged_receipt_ref,
                        require_live_engine=require_live_engine,
                        reader=RoutedReader(),
                        historical_root_loader=lambda reader, reference: (
                            workflow.load_historical_transition(
                                h3.store,
                                reader=reader,
                                state_root_ref=reference,
                            )
                        ),
                    )
                captured_loads.append(result)
                return result

            store.publications.clear()
            with mock.patch.object(
                staging,
                "load_staged_authority_plan",
                side_effect=capture_real_deep_load,
            ):
                receipt_ref = staging.stage_authority_plan(
                    store,
                    planned,
                    process_receipt=process_receipt,
                    clock=lambda: "2026-08-15T04:05:00Z",
                )
            self.assertEqual(receipt_ref, store.publications[-1])
            self.assertEqual("validation-receipt", receipt_ref.kind)
            self.assertTrue(
                all(
                    item.kind != "validation-receipt"
                    for item in store.publications[:-1]
                )
            )
            self.assertEqual(1, len(captured_loads))
            loaded = captured_loads[0]
            self.assertEqual(planned.plan, loaded.planned.plan)
            self.assertEqual(
                (semantic_telemetry.copy.stored,),
                tuple(
                    item
                    for item in loaded.receipt.outputs
                    if (item.kind, item.path)
                    == (
                        semantic_telemetry.copy.stored.kind,
                        semantic_telemetry.copy.stored.path,
                    )
                ),
            )
            self.assertEqual(pointer, loaded.predecessor_pointer)
            self.assertEqual(planned.legacy_raw, loaded.successor_raw)
            self.assertEqual(
                planned.plan.legacy_matrix.canonical_object,
                loaded.canonical_successor_matrix,
            )
            self.assertEqual(current_state_root_ref, loaded.prior_state_root)
            expected_staged = staging._sorted_unique_refs(
                *loaded.receipt.outputs,
                loaded.receipt_reference,
                *(
                    staging.matrix_object_reference(item)
                    for closure in (
                        loaded.planned.predecessor_matrix,
                        loaded.planned.successor_matrix,
                    )
                    for item in (*closure.cells, *closure.shards)
                ),
            )
            self.assertEqual(expected_staged, loaded.staged_required_objects)
            self.assertFalse(
                any(
                    item.kind == "matrix-pointer"
                    for item in loaded.staged_required_objects
                )
            )
            self.assertEqual(15, len(loaded.historical_transition.required_objects))
            alias_historical = _unsafe_replace(
                loaded.historical_transition,
                current_pointer_ref=alias_pointer,
            )
            with self.assertRaisesRegex(
                PipelineError, "historical H3 transition differs"
            ):
                replace(loaded, historical_transition=alias_historical)
            with self.assertRaisesRegex(
                PipelineError, "different StateRoot or pointer"
            ):
                staging.load_staged_authority_plan(
                    store,
                    receipt_ref,
                    require_live_engine=False,
                    historical_root_loader=lambda _reader, _reference: (
                        alias_historical
                    ),
                )
            class SelectionReader(RoutedReader):
                def __init__(self) -> None:
                    self.pointer_reads: list[EvidenceRef] = []

                def read_pointer(self, reference: EvidenceRef):
                    self.pointer_reads.append(reference)
                    return store.read_pointer(reference)

            selection_reader = SelectionReader()
            pointer_free_reader = RoutedReader()

            def reuse_authenticated_selection(
                exact_store,
                exact_receipt_ref,
                *,
                require_live_engine,
                reader=None,
                historical_root_loader=None,
            ):
                if (
                    exact_store is store
                    and exact_receipt_ref == receipt_ref
                    and require_live_engine is False
                    and reader in {pointer_free_reader, selection_reader}
                    and historical_root_loader is None
                ):
                    return loaded
                return original_load(
                    exact_store,
                    exact_receipt_ref,
                    require_live_engine=require_live_engine,
                    reader=reader,
                    historical_root_loader=historical_root_loader,
                )

            with mock.patch.object(
                staging,
                "load_staged_authority_plan",
                side_effect=reuse_authenticated_selection,
            ) as cached_loader:
                self.assertIs(
                    loaded,
                    staging.verify_staged_authority_plan(
                        store,
                        receipt_ref,
                        require_live_engine=False,
                        expected_pointer=None,
                        reader=pointer_free_reader,
                    ),
                )
                selected_predecessor = staging.verify_staged_authority_plan(
                    store,
                    receipt_ref,
                    require_live_engine=False,
                    expected_pointer="predecessor",
                    reader=selection_reader,
                )
                with self.assertRaisesRegex(
                    PipelineError, "planned predecessor|evidence bytes"
                ):
                    staging.verify_staged_authority_plan(
                        store,
                        receipt_ref,
                        require_live_engine=False,
                        expected_pointer="successor",
                        reader=selection_reader,
                    )
            self.assertEqual(3, cached_loader.call_count)
            self.assertEqual(receipt_ref, selected_predecessor.receipt_reference)
            self.assertEqual(
                [loaded.predecessor_pointer, loaded.successor_pointer],
                selection_reader.pointer_reads,
            )

            class FailingH4Reader(RoutedReader):
                def __init__(self, target: EvidenceRef, *, corrupt: bool) -> None:
                    self.target = target
                    self.corrupt = corrupt

                def read_exact(self, reference: EvidenceRef) -> bytes:
                    if reference == self.target:
                        if self.corrupt:
                            return original_read(reference) + b"tampered\n"
                        raise PipelineError("injected H4 object is missing")
                    return original_read(reference)

            target_artifact = process_receipt.artifact_refs[0]
            for corrupt in (False, True):
                with self.assertRaises(PipelineError):
                    staging._require_process_receipt(
                        store,
                        FailingH4Reader(target_artifact, corrupt=corrupt),
                        planned,
                        process_receipt,
                    )
            extra_raw = b"extra H4 artifact\n"
            extra_ref = store.reference_for(
                kind="artifact", raw=extra_raw, target_content_sha256=None
            )

            class ExtraReader(RoutedReader):
                def read_exact(self, reference: EvidenceRef) -> bytes:
                    if reference == extra_ref:
                        return extra_raw
                    return original_read(reference)

            with self.assertRaises(PipelineError):
                staging._require_process_receipt(
                    store,
                    ExtraReader(),
                    planned,
                    StoredCheckReceipt(
                        receipt_ref=process_receipt.receipt_ref,
                        artifact_refs=tuple(
                            sorted(
                                (*process_receipt.artifact_refs, extra_ref),
                                key=lambda item: (item.kind, item.path),
                            )
                        ),
                    ),
                )

            replay_reader = FailingH4Reader(
                planned.plan.matrix_replay.stored,
                corrupt=False,
            )
            with self.assertRaises(PipelineError):
                staging.load_staged_authority_plan(
                    store,
                    receipt_ref,
                    require_live_engine=False,
                    reader=replay_reader,
                )
            copy_target = planned.copies[0].copy.stored
            with self.assertRaises(PipelineError):
                staging.load_staged_authority_plan(
                    store,
                    receipt_ref,
                    require_live_engine=False,
                    reader=FailingH4Reader(copy_target, corrupt=True),
                )

            # Remove the first predecessor leaf so the deep loader proves its
            # recursive child gate before hydrating the rest of the shard.
            child = staging.matrix_object_reference(predecessor.cells[0])
            child_key = (child.kind, child.path)
            child_raw = store.matrix_objects.pop(child_key)
            try:
                with self.assertRaisesRegex(PipelineError, "matrix evidence"):
                    staging.load_staged_authority_plan(
                        store,
                        receipt_ref,
                        require_live_engine=False,
                    )
            finally:
                store.matrix_objects[child_key] = child_raw
            self.assertTrue(phase_reuses)
            self.assertEqual(2, replay_spy.call_count)

    def test_outer_lock_reader_seam_is_explicit_and_load_has_no_pointer_call(self) -> None:
        signature = inspect.signature(staging.load_staged_authority_plan)
        self.assertIn("reader", signature.parameters)
        self.assertIn("historical_root_loader", signature.parameters)

        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertNotIn("pointer_transaction", calls)
        load_source = inspect.getsource(staging.load_staged_authority_plan)
        self.assertNotIn("_assert_pointer", load_source)
        self.assertNotIn("verify_transition", load_source)
        self.assertIn("load_historical_transition", load_source)
        self.assertNotIn("main", staging.__all__)


if __name__ == "__main__":
    unittest.main()
