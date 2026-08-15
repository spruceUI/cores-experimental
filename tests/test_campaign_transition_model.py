from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, fields, replace
import inspect
import json
from pathlib import Path
import unittest

from scripts.core_pipeline_lib.campaign.json_wire import rendered_json_bytes
from scripts.core_pipeline_lib.campaign.model import EvidenceRef, StateRoot
from scripts.core_pipeline_lib.campaign.transition_model import (
    INTENT_FORMAT,
    PLAN_FORMAT,
    AuthenticatedInput,
    NamedEvidenceRef,
    PlannedTransition,
    ResolvedTransitionPlanV1,
    TransitionDeltaV1,
    TransitionIntentV1,
    TransitionRequest,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "transition_model.py"
)

BOOTSTRAP_CHECKS = (
    "campaign.plan.identity",
    "phase-freeze.inputs.identity",
    "phase-freeze.core-spec-set",
    "phase-freeze.legacy-lineage",
    "phase-freeze.schema",
    "phase-freeze.successor.identity",
    "publication.disabled",
)


class _StringSubclass(str):
    pass


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _ref(
    kind: str,
    name: str,
    raw: bytes,
    *,
    semantic: str | None = None,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=sha256_bytes(raw),
        target_content_sha256=semantic or _sha256(len(raw) + 100),
        size=len(raw),
    )


PREDECESSOR_RAW = b"opaque legacy phase-freeze v2\n"
CATALOG_RAW = b'{"catalog":"sealed"}\n'
TRACKS_RAW = b'{"tracks":"sealed"}\n'
ENGINE_RAW = b'{"engine":"sealed"}\n'
CANDIDATE_RAW = b'{"candidate":"phase-freeze-v1"}\n'


def _predecessor_ref() -> EvidenceRef:
    return _ref("phase-freeze", "predecessor", PREDECESSOR_RAW)


def _named_inputs() -> tuple[NamedEvidenceRef, ...]:
    return (
        NamedEvidenceRef(
            name="catalog",
            reference=_ref("artifact", "catalog", CATALOG_RAW),
        ),
        NamedEvidenceRef(
            name="tracks",
            reference=_ref("track-registry", "tracks", TRACKS_RAW),
        ),
    )


def _intent() -> TransitionIntentV1:
    return TransitionIntentV1(
        transition_id="phase-freeze-bootstrap-20260814",
        campaign_id="host-core-build-20260810",
        kind="phase-freeze-bootstrap-v1",
        captured_at="2026-08-14T20:00:00Z",
        reason="Bootstrap the strict phase-freeze authority from sealed inputs.",
        predecessor=_predecessor_ref(),
        inputs=_named_inputs(),
        changed_authorities=("catalog", "tracks"),
    )


def _delta() -> TransitionDeltaV1:
    pointers = ("/authorities/catalog", "/captured_at")
    return TransitionDeltaV1(
        allowed_changes=pointers,
        required_changes=pointers,
        changed_pointers=pointers,
        preserved_projection_sha256=_sha256(900),
    )


def _plan() -> ResolvedTransitionPlanV1:
    intent = _intent()
    intent_raw = rendered_json_bytes(intent.to_document())
    return ResolvedTransitionPlanV1(
        transition_id=intent.transition_id,
        campaign_id=intent.campaign_id,
        kind=intent.kind,
        handler_id="phase-freeze.bootstrap.v1",
        captured_at=intent.captured_at,
        reason=intent.reason,
        intent=_ref(
            "transition-spec",
            "intent",
            intent_raw,
            semantic=intent.content_sha256,
        ),
        engine_bundle=_ref("engine-bundle", "engine", ENGINE_RAW),
        predecessor=intent.predecessor,
        inputs=intent.inputs,
        successor=_ref("phase-freeze-cas", "successor", CANDIDATE_RAW),
        delta=_delta(),
        required_checks=BOOTSTRAP_CHECKS,
        process_tier="evidence",
    )


class CampaignTransitionModelTests(unittest.TestCase):
    def test_wire_records_round_trip_with_exact_derived_digests(self) -> None:
        records = (_named_inputs()[0], _intent(), _delta(), _plan())
        for record in records:
            with self.subTest(record=type(record).__name__):
                document = record.to_document()
                self.assertEqual(record.content_sha256, document["content_sha256"])
                decoded = type(record).from_document(
                    rendered_json_bytes(document)
                )
                self.assertEqual(record, decoded)
                self.assertEqual(document, decoded.to_document())

        self.assertEqual(INTENT_FORMAT, _intent().to_document()["format"])
        self.assertEqual(PLAN_FORMAT, _plan().to_document()["format"])

    def test_wire_records_are_frozen_slotted_and_digest_is_not_constructor_data(self) -> None:
        records = (_named_inputs()[0], _intent(), _delta(), _plan())
        for record in records:
            with self.subTest(record=type(record).__name__):
                self.assertFalse(hasattr(record, "__dict__"))
                self.assertNotIn(
                    "content_sha256",
                    inspect.signature(type(record)).parameters,
                )
                with self.assertRaises(FrozenInstanceError):
                    setattr(record, fields(record)[0].name, "replacement")

    def test_documents_are_independent_and_nested_records_remain_immutable(self) -> None:
        intent = _intent()
        document = intent.to_document()
        document["inputs"][0]["name"] = "mutated"  # type: ignore[index]
        document["predecessor"]["path"] = "mutated"  # type: ignore[index]
        self.assertEqual("catalog", intent.inputs[0].name)
        self.assertEqual(
            "campaign/evidence/predecessor.json",
            intent.predecessor.path,
        )

    def test_exact_keys_fixed_envelopes_and_digests_fail_closed(self) -> None:
        records = (_named_inputs()[0], _intent(), _delta(), _plan())
        for record in records:
            with self.subTest(record=type(record).__name__, mutation="extra"):
                document = record.to_document()
                document["unexpected"] = True
                with self.assertRaises(PipelineError):
                    type(record).from_document(document)
            with self.subTest(record=type(record).__name__, mutation="missing"):
                document = record.to_document()
                document.pop("content_sha256")
                with self.assertRaises(PipelineError):
                    type(record).from_document(document)
            with self.subTest(record=type(record).__name__, mutation="digest"):
                document = record.to_document()
                document["content_sha256"] = _sha256(99)
                with self.assertRaises(PipelineError):
                    type(record).from_document(document)

        for key, bad in (
            ("schema_version", True),
            ("format", "spruce-campaign-transition-intent-v2"),
            ("local_only", 1),
            ("publication", "enabled"),
        ):
            document = _intent().to_document()
            document[key] = bad
            with self.subTest(key=key, bad=bad):
                with self.assertRaises(PipelineError):
                    TransitionIntentV1.from_document(document)

    def test_duplicate_keys_floats_nonfinite_numbers_and_scalar_aliases_fail(self) -> None:
        raw = rendered_json_bytes(_intent().to_document())
        duplicate = raw.replace(
            b'  "campaign_id":',
            b'  "campaign_id": "duplicate",\n  "campaign_id":',
            1,
        )
        with self.assertRaises(PipelineError):
            TransitionIntentV1.from_document(duplicate)

        document = _intent().to_document()
        document["predecessor"]["size"] = float(  # type: ignore[index]
            document["predecessor"]["size"]  # type: ignore[index]
        )
        with self.assertRaises(PipelineError):
            TransitionIntentV1.from_document(document)

        nonfinite = raw.replace(b'"local_only": true', b'"local_only": NaN')
        with self.assertRaises(PipelineError):
            TransitionIntentV1.from_document(nonfinite)

        with self.assertRaises(PipelineError):
            replace(_intent(), campaign_id=_StringSubclass("host-core-build"))
        with self.assertRaises(PipelineError):
            replace(
                _plan(),
                required_checks=("campaign.plan.identity", 1),  # type: ignore[arg-type]
            )
        with self.assertRaises(PipelineError):
            replace(_plan(), required_checks=(["unhashable"],))  # type: ignore[arg-type,list-item]

    def test_intent_requires_sorted_unique_named_inputs_and_changed_subset(self) -> None:
        intent = _intent()
        with self.assertRaises(PipelineError):
            replace(intent, inputs=tuple(reversed(intent.inputs)))
        with self.assertRaises(PipelineError):
            replace(intent, inputs=(intent.inputs[0], intent.inputs[0]))
        with self.assertRaises(PipelineError):
            replace(intent, inputs=list(intent.inputs))  # type: ignore[arg-type]
        with self.assertRaises(PipelineError):
            replace(intent, inputs=(), changed_authorities=())
        with self.assertRaises(PipelineError):
            replace(intent, changed_authorities=("tracks", "catalog"))
        with self.assertRaises(PipelineError):
            replace(intent, changed_authorities=("catalog", "unknown"))

    def test_delta_enforces_canonical_sorted_exact_pointer_policy(self) -> None:
        delta = _delta()
        mutations = (
            {"allowed_changes": tuple(reversed(delta.allowed_changes))},
            {
                "allowed_changes": ("/captured_at",),
                "required_changes": ("/authorities/catalog",),
                "changed_pointers": ("/authorities/catalog",),
            },
            {"changed_pointers": ("/authorities/catalog",)},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(PipelineError):
                    replace(delta, **mutation)
        for pointer in ("captured_at", "/bad~escape", "/bad~2escape"):
            with self.subTest(pointer=pointer):
                with self.assertRaises(PipelineError):
                    TransitionDeltaV1(
                        allowed_changes=(pointer,),
                        required_changes=(pointer,),
                        changed_pointers=(pointer,),
                        preserved_projection_sha256=_sha256(2),
                    )

    def test_plan_requires_semantic_fixed_role_refs_and_valid_process_tier(self) -> None:
        plan = _plan()
        wrong_intent = replace(plan.intent, kind="artifact")
        no_semantic = replace(plan.engine_bundle, target_content_sha256=None)
        for changes in (
            {"intent": wrong_intent},
            {"engine_bundle": no_semantic},
            {"inputs": tuple(reversed(plan.inputs))},
            {"inputs": ()},
            {"process_tier": "unknown"},
            {"required_checks": ("duplicate", "duplicate")},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PipelineError):
                    replace(plan, **changes)

    def test_runtime_request_authenticates_spec_predecessor_and_all_inputs(self) -> None:
        intent = _intent()
        spec_raw = rendered_json_bytes(intent.to_document())
        request = TransitionRequest(
            spec_ref=_ref(
                "transition-spec",
                "intent",
                spec_raw,
                semantic=intent.content_sha256,
            ),
            spec_raw=spec_raw,
            engine_bundle_ref=_ref("engine-bundle", "engine", ENGINE_RAW),
            engine_bundle_raw=ENGINE_RAW,
            predecessor_raw=PREDECESSOR_RAW,
            inputs=(
                AuthenticatedInput(
                    name="catalog",
                    reference=intent.inputs[0].reference,
                    raw=CATALOG_RAW,
                ),
                AuthenticatedInput(
                    name="tracks",
                    reference=intent.inputs[1].reference,
                    raw=TRACKS_RAW,
                ),
            ),
        )
        self.assertFalse(hasattr(request, "__dict__"))

        with self.assertRaises(PipelineError):
            replace(request, spec_raw=spec_raw + b" ")
        with self.assertRaises(PipelineError):
            replace(request, predecessor_raw=PREDECESSOR_RAW + b"x")
        with self.assertRaises(PipelineError):
            replace(request, inputs=tuple(reversed(request.inputs)))
        with self.assertRaises(PipelineError):
            replace(
                request,
                spec_ref=replace(
                    request.spec_ref,
                    target_content_sha256=_sha256(1234),
                ),
            )

    def test_runtime_input_and_planned_candidate_detect_missing_hydration_or_drift(self) -> None:
        reference = _ref("artifact", "catalog", CATALOG_RAW)
        for raw in (b"", CATALOG_RAW + b"x"):
            with self.subTest(raw=raw):
                with self.assertRaises(PipelineError):
                    AuthenticatedInput(name="catalog", reference=reference, raw=raw)

        planned = PlannedTransition(plan=_plan(), candidate_raw=CANDIDATE_RAW)
        self.assertFalse(hasattr(planned, "__dict__"))
        with self.assertRaises(PipelineError):
            replace(planned, candidate_raw=CANDIDATE_RAW + b"drift")

    def test_generic_model_does_not_redefine_or_weaken_h3_state_root(self) -> None:
        exports = MODEL_PATH.read_text(encoding="utf-8").split("__all__ =", 1)[1]
        self.assertNotIn("StateRoot", exports)
        self.assertEqual(
            (
                "campaign_id",
                "generation",
                "transition_id",
                "plan",
                "receipt",
                "current",
                "previous",
            ),
            tuple(field.name for field in fields(StateRoot)),
        )
        with self.assertRaises(PipelineError):
            StateRoot(
                campaign_id="campaign",
                generation=1,
                transition_id="transition",
                plan=_ref("transition-plan", "plan", b"plan"),
                receipt=_ref("validation-receipt", "receipt", b"receipt"),
                current=_ref("phase-freeze-cas", "freeze", CANDIDATE_RAW),
            )

    def test_json_round_trip_does_not_alias_mutable_input_documents(self) -> None:
        original = _plan().to_document()
        working = copy.deepcopy(original)
        decoded = ResolvedTransitionPlanV1.from_document(working)
        working["inputs"][0]["reference"]["path"] = "changed"  # type: ignore[index]
        self.assertEqual(original, decoded.to_document())
        self.assertEqual(original, json.loads(json.dumps(original)))


if __name__ == "__main__":
    unittest.main()
