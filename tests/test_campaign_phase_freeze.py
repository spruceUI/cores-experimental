from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, fields, replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

from scripts.core_pipeline_lib.campaign import phase_freeze as phase_freeze_module
from scripts.core_pipeline_lib.campaign.json_wire import (
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
)
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.campaign.phase_freeze import (
    BOOTSTRAP_KIND,
    CAMPAIGN_STATE_RELATIVE,
    CATALOG_SCHEMA_FILE_SHA256,
    CATALOG_SCHEMA_SIZE,
    PHASE_FREEZE_SCHEMA_CONTENT_SHA256,
    PHASE_FREEZE_SCHEMA_DRAFT,
    PHASE_FREEZE_SCHEMA_FILE_SHA256,
    PHASE_FREEZE_SCHEMA_ID,
    PHASE_FREEZE_SCHEMA_PATH,
    PHASE_FREEZE_SCHEMA_SIZE,
    REFRESH_KIND,
    PhaseFreezeV1,
    PlannedPhaseFreeze,
    decode_phase_freeze,
    plan_phase_freeze,
    render_phase_freeze,
    validate_phase_freeze,
)
from scripts.core_pipeline_lib.campaign.store import canonical_object_reference
from scripts.core_pipeline_lib.campaign.transition_model import (
    AuthenticatedInput,
    NamedEvidenceRef,
    TransitionIntentV1,
    TransitionRequest,
)
from scripts.core_pipeline_lib.campaign.transition_registry import (
    INPUT_ROLE_NAMES,
    REQUIRED_ENGINE_MEMBERS,
)
from scripts.core_pipeline_lib.core_spec import (
    CATALOG_PATH,
    CATALOG_SCHEMA_CONTENT_SHA256,
    CATALOG_SCHEMA_PATH,
    derive_core_spec_set,
    render_core_spec_set,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes
from scripts.core_pipeline_lib.source_bundle import pipeline_bundle_content_sha256


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "phase_freeze.py"
)
SCHEMA_PATH = ROOT / PHASE_FREEZE_SCHEMA_PATH


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _reseal(document: dict[str, object]) -> None:
    material = copy.deepcopy(document)
    material.pop("content_sha256", None)
    document["content_sha256"] = canonical_json_sha256(material)


def _reference(
    *,
    kind: str,
    path: str,
    raw: bytes,
    semantic: str,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=semantic,
        size=len(raw),
    )


def _json_reference(*, kind: str, path: str, raw: bytes) -> EvidenceRef:
    return _reference(
        kind=kind,
        path=path,
        raw=raw,
        semantic=canonical_json_sha256(
            decode_identity_object(raw, label=f"{path} fixture")
        ),
    )


class PhaseFreezeFixture:
    def __init__(self) -> None:
        self.catalog_raw = (ROOT / CATALOG_PATH).read_bytes()
        self.catalog_schema_raw = (ROOT / CATALOG_SCHEMA_PATH).read_bytes()
        self.schema_raw = SCHEMA_PATH.read_bytes()
        self.catalog_ref = _json_reference(
            kind="artifact",
            path=CATALOG_PATH,
            raw=self.catalog_raw,
        )
        self.catalog_schema_ref = _json_reference(
            kind="artifact",
            path=CATALOG_SCHEMA_PATH,
            raw=self.catalog_schema_raw,
        )
        core_spec_set = derive_core_spec_set(
            catalog_ref=self.catalog_ref,
            catalog_raw=self.catalog_raw,
            catalog_schema_ref=self.catalog_schema_ref,
            catalog_schema_raw=self.catalog_schema_raw,
        )
        self.core_spec_raw = render_core_spec_set(core_spec_set)
        self.core_spec_ref = _reference(
            kind="artifact",
            path="campaign/evidence/core-spec-set-v1.json",
            raw=self.core_spec_raw,
            semantic=core_spec_set.content_sha256,
        )
        self.schema_ref = _json_reference(
            kind="artifact",
            path=PHASE_FREEZE_SCHEMA_PATH,
            raw=self.schema_raw,
        )
        self.inputs = self._inputs()
        self.engine_document = self._engine_document()
        self.engine_raw = rendered_json_bytes(self.engine_document)
        self.legacy_raw = (
            b'\xff{"duplicate":1,"duplicate":2,"nonfinite":NaN}\n'
        )
        self.legacy_ref = _reference(
            kind="phase-freeze",
            path="campaign/legacy/phase-freeze-v2.json",
            raw=self.legacy_raw,
            semantic=_sha256(700),
        )

    def _inputs(self) -> tuple[AuthenticatedInput, ...]:
        result: list[AuthenticatedInput] = []
        for index, name in enumerate(INPUT_ROLE_NAMES):
            if name == "catalog":
                raw = self.catalog_raw
                reference = self.catalog_ref
            elif name == "core-spec-set":
                raw = self.core_spec_raw
                reference = self.core_spec_ref
            elif name == "schemas":
                raw = self.schema_raw
                reference = self.schema_ref
            else:
                raw = f"sealed authority: {name}\n".encode("utf-8")
                reference = _reference(
                    kind="track-registry" if name == "tracks" else "artifact",
                    path=f"campaign/evidence/{name}.json",
                    raw=raw,
                    semantic=_sha256(800 + index),
                )
            result.append(
                AuthenticatedInput(name=name, reference=reference, raw=raw)
            )
        return tuple(result)

    @staticmethod
    def _engine_document() -> dict[str, object]:
        required = {
            path: _sha256(index + 1)
            for index, path in enumerate(REQUIRED_ENGINE_MEMBERS)
        }
        files = {
            "scripts/core_pipeline.py": _sha256(90),
            "scripts/core_pipeline_lib/__init__.py": _sha256(91),
            **required,
        }
        document: dict[str, object] = {
            "schema_version": 1,
            "files": dict(sorted(files.items())),
        }
        document["content_sha256"] = pipeline_bundle_content_sha256(
            document["files"]  # type: ignore[arg-type]
        )
        return document

    @staticmethod
    def replace_input(
        inputs: tuple[AuthenticatedInput, ...],
        *,
        name: str,
        raw: bytes,
        semantic: str,
        kind: str | None = None,
        path: str | None = None,
    ) -> tuple[AuthenticatedInput, ...]:
        result: list[AuthenticatedInput] = []
        for item in inputs:
            if item.name != name:
                result.append(item)
                continue
            reference = _reference(
                kind=item.reference.kind if kind is None else kind,
                path=item.reference.path if path is None else path,
                raw=raw,
                semantic=semantic,
            )
            result.append(
                AuthenticatedInput(name=name, reference=reference, raw=raw)
            )
        return tuple(result)

    def changed_input(
        self,
        inputs: tuple[AuthenticatedInput, ...],
        name: str,
    ) -> tuple[AuthenticatedInput, ...]:
        raw = f"refreshed authority: {name}\n".encode("utf-8")
        return self.replace_input(
            inputs,
            name=name,
            raw=raw,
            semantic=sha256_bytes(b"semantic\0" + raw),
        )

    def coordinated_catalog_inputs(
        self,
        catalog: dict[str, object],
    ) -> tuple[AuthenticatedInput, ...]:
        catalog_raw = rendered_json_bytes(catalog)
        catalog_ref = _json_reference(
            kind="artifact",
            path=CATALOG_PATH,
            raw=catalog_raw,
        )
        core_spec = decode_identity_object(
            self.core_spec_raw,
            label="coordinated CoreSpec fixture",
        )
        core_spec["catalog"] = catalog_ref.to_document()
        _reseal(core_spec)
        core_spec_raw = rendered_json_bytes(core_spec)
        inputs = self.replace_input(
            self.inputs,
            name="catalog",
            raw=catalog_raw,
            semantic=catalog_ref.target_content_sha256,  # type: ignore[arg-type]
        )
        return self.replace_input(
            inputs,
            name="core-spec-set",
            raw=core_spec_raw,
            semantic=core_spec["content_sha256"],  # type: ignore[arg-type]
        )

    def request(
        self,
        *,
        kind: str = BOOTSTRAP_KIND,
        transition_id: str = "phase-freeze-bootstrap-20260814",
        captured_at: str = "2026-08-14T20:00:00Z",
        predecessor: EvidenceRef | None = None,
        predecessor_raw: bytes | None = None,
        inputs: tuple[AuthenticatedInput, ...] | None = None,
        changed_authorities: tuple[str, ...] = INPUT_ROLE_NAMES,
        engine_document: dict[str, object] | None = None,
        engine_raw: bytes | None = None,
        spec_suffix: bytes = b"",
        campaign_id: str = "host-core-build-20260810",
    ) -> TransitionRequest:
        predecessor = self.legacy_ref if predecessor is None else predecessor
        predecessor_raw = (
            self.legacy_raw if predecessor_raw is None else predecessor_raw
        )
        inputs = self.inputs if inputs is None else inputs
        intent = TransitionIntentV1(
            transition_id=transition_id,
            campaign_id=campaign_id,
            kind=kind,
            captured_at=captured_at,
            reason="Freeze exact authenticated campaign authorities.",
            predecessor=predecessor,
            inputs=tuple(
                NamedEvidenceRef(name=item.name, reference=item.reference)
                for item in inputs
            ),
            changed_authorities=changed_authorities,
        )
        canonical_spec_raw = rendered_json_bytes(intent.to_document())
        spec_raw = canonical_spec_raw + spec_suffix
        spec_ref = _reference(
            kind="transition-spec",
            path=f"manifests/campaign-transitions/{transition_id}.json",
            raw=spec_raw,
            semantic=intent.content_sha256,
        )
        if engine_document is None:
            engine_document = self.engine_document
        if engine_raw is None:
            engine_raw = rendered_json_bytes(engine_document)
        engine_ref = _reference(
            kind="engine-bundle",
            path=f"manifests/campaign-engine-bundles/{transition_id}.json",
            raw=engine_raw,
            semantic=engine_document["content_sha256"],  # type: ignore[arg-type]
        )
        return TransitionRequest(
            spec_ref=spec_ref,
            spec_raw=spec_raw,
            engine_bundle_ref=engine_ref,
            engine_bundle_raw=engine_raw,
            predecessor_raw=predecessor_raw,
            inputs=inputs,
        )

    def bootstrap(self) -> tuple[TransitionRequest, PlannedPhaseFreeze]:
        request = self.request()
        return request, plan_phase_freeze(request)

    def refresh_request(
        self,
        predecessor_result: PlannedPhaseFreeze,
        *,
        inputs: tuple[AuthenticatedInput, ...] | None = None,
        changed_authorities: tuple[str, ...] = ("tracks",),
        transition_id: str = "phase-freeze-refresh-20260814",
        captured_at: str = "2026-08-14T20:00:01Z",
        campaign_id: str = "host-core-build-20260810",
    ) -> TransitionRequest:
        if inputs is None:
            inputs = self.changed_input(self.inputs, "tracks")
        return self.request(
            kind=REFRESH_KIND,
            transition_id=transition_id,
            captured_at=captured_at,
            predecessor=predecessor_result.plan.successor,
            predecessor_raw=predecessor_result.candidate_raw,
            inputs=inputs,
            changed_authorities=changed_authorities,
            campaign_id=campaign_id,
        )


class CampaignPhaseFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = PhaseFreezeFixture()

    def test_bootstrap_is_deterministic_and_legacy_predecessor_is_opaque(self) -> None:
        request = self.fixture.request()
        first = plan_phase_freeze(request)
        second = plan_phase_freeze(request)
        self.assertEqual(first, second)
        self.assertEqual(first.candidate_raw, render_phase_freeze(first.phase_freeze))
        self.assertEqual(first.phase_freeze, decode_phase_freeze(first.candidate_raw))
        self.assertEqual(INPUT_ROLE_NAMES, tuple(
            item.name for item in first.phase_freeze.authorities
        ))
        self.assertEqual(self.fixture.legacy_ref, first.phase_freeze.predecessor)
        self.assertEqual((), first.plan.delta.allowed_changes)
        self.assertEqual((), first.plan.delta.required_changes)
        self.assertEqual((), first.plan.delta.changed_pointers)
        self.assertEqual(
            canonical_json_sha256({}),
            first.plan.delta.preserved_projection_sha256,
        )
        self.assertEqual("phase-freeze.bootstrap.v1", first.plan.handler_id)
        self.assertEqual("disabled", first.phase_freeze.publication)
        self.assertIs(first.phase_freeze.local_only, True)
        self.assertEqual(
            canonical_object_reference(
                state_relative=CAMPAIGN_STATE_RELATIVE,
                kind="phase-freeze-cas",
                raw=first.candidate_raw,
                target_content_sha256=first.phase_freeze.content_sha256,
            ),
            first.plan.successor,
        )
        validate_phase_freeze(first, request=request)

    def test_refresh_derives_the_exact_authority_and_metadata_pointer_delta(
        self,
    ) -> None:
        _bootstrap_request, bootstrap = self.fixture.bootstrap()
        inputs = self.fixture.changed_input(self.fixture.inputs, "tracks")
        request = self.fixture.refresh_request(bootstrap, inputs=inputs)
        result = plan_phase_freeze(request)
        expected = (
            "/authorities/tracks",
            "/captured_at",
            "/content_sha256",
            "/predecessor",
            "/transition_id",
        )
        self.assertEqual(expected, result.plan.delta.allowed_changes)
        self.assertEqual(expected, result.plan.delta.required_changes)
        self.assertEqual(expected, result.plan.delta.changed_pointers)
        self.assertEqual(bootstrap.plan.successor, result.phase_freeze.predecessor)
        before = {
            item.name: item.reference for item in bootstrap.phase_freeze.authorities
        }
        after = {
            item.name: item.reference for item in result.phase_freeze.authorities
        }
        self.assertEqual(
            ("tracks",),
            tuple(name for name in INPUT_ROLE_NAMES if before[name] != after[name]),
        )
        validate_phase_freeze(result, request=request)

    def test_bootstrap_and_refresh_changed_authority_claims_fail_closed(self) -> None:
        with self.assertRaises(PipelineError):
            plan_phase_freeze(
                self.fixture.request(changed_authorities=INPUT_ROLE_NAMES[:-1])
            )

        _bootstrap_request, bootstrap = self.fixture.bootstrap()
        changed = self.fixture.changed_input(self.fixture.inputs, "tracks")
        for inputs, declared in (
            (changed, ()),
            (changed, ("catalog",)),
            (self.fixture.inputs, ("tracks",)),
            (self.fixture.inputs, ()),
        ):
            with self.subTest(declared=declared):
                request = self.fixture.refresh_request(
                    bootstrap,
                    inputs=inputs,
                    changed_authorities=declared,
                )
                with self.assertRaises(PipelineError):
                    plan_phase_freeze(request)

    def test_refresh_requires_exact_canonical_strict_predecessor_and_lineage(
        self,
    ) -> None:
        _bootstrap_request, bootstrap = self.fixture.bootstrap()
        changed = self.fixture.changed_input(self.fixture.inputs, "tracks")

        noncanonical_raw = bootstrap.candidate_raw + b"\n"
        noncanonical_ref = canonical_object_reference(
            state_relative=CAMPAIGN_STATE_RELATIVE,
            kind="phase-freeze-cas",
            raw=noncanonical_raw,
            target_content_sha256=bootstrap.phase_freeze.content_sha256,
        )
        request = self.fixture.request(
            kind=REFRESH_KIND,
            transition_id="phase-freeze-refresh-noncanonical",
            captured_at="2026-08-14T20:00:01Z",
            predecessor=noncanonical_ref,
            predecessor_raw=noncanonical_raw,
            inputs=changed,
            changed_authorities=("tracks",),
        )
        with self.assertRaises(PipelineError):
            plan_phase_freeze(request)

        aliases = (
            replace(bootstrap.plan.successor, path="campaign/alias/freeze.json"),
            replace(bootstrap.plan.successor, kind="phase-freeze"),
        )
        for predecessor in aliases:
            with self.subTest(predecessor=predecessor.kind):
                request = self.fixture.request(
                    kind=REFRESH_KIND,
                    transition_id="phase-freeze-refresh-alias",
                    captured_at="2026-08-14T20:00:01Z",
                    predecessor=predecessor,
                    predecessor_raw=bootstrap.candidate_raw,
                    inputs=changed,
                    changed_authorities=("tracks",),
                )
                with self.assertRaises(PipelineError):
                    plan_phase_freeze(request)

        for transition_id, captured_at, campaign_id in (
            (
                bootstrap.phase_freeze.transition_id,
                "2026-08-14T20:00:01Z",
                bootstrap.phase_freeze.campaign_id,
            ),
            (
                "phase-freeze-refresh-stale",
                bootstrap.phase_freeze.captured_at,
                bootstrap.phase_freeze.campaign_id,
            ),
            (
                "phase-freeze-refresh-campaign",
                "2026-08-14T20:00:01Z",
                "other-campaign",
            ),
        ):
            with self.subTest(
                transition_id=transition_id,
                captured_at=captured_at,
                campaign_id=campaign_id,
            ):
                request = self.fixture.refresh_request(
                    bootstrap,
                    inputs=changed,
                    transition_id=transition_id,
                    captured_at=captured_at,
                    campaign_id=campaign_id,
                )
                with self.assertRaises(PipelineError):
                    plan_phase_freeze(request)

    def test_exact_input_role_kind_semantic_and_path_bindings_are_enforced(
        self,
    ) -> None:
        catalog = next(
            item for item in self.fixture.inputs if item.name == "catalog"
        )
        wrong_kind = replace(catalog.reference, kind="track-registry")
        no_semantic = replace(catalog.reference, target_content_sha256=None)
        for reference in (wrong_kind, no_semantic):
            inputs = tuple(
                AuthenticatedInput(
                    name=item.name,
                    reference=reference if item.name == "catalog" else item.reference,
                    raw=item.raw,
                )
                for item in self.fixture.inputs
            )
            request = self.fixture.request(inputs=inputs)
            with self.subTest(reference=reference):
                with self.assertRaises(PipelineError):
                    plan_phase_freeze(request)

        schema_wrong_path = self.fixture.replace_input(
            self.fixture.inputs,
            name="schemas",
            raw=self.fixture.schema_raw,
            semantic=PHASE_FREEZE_SCHEMA_CONTENT_SHA256,
            path="manifests/other.schema.json",
        )
        with self.assertRaises(PipelineError):
            plan_phase_freeze(self.fixture.request(inputs=schema_wrong_path))

    def test_schema_is_exact_authenticated_local_and_candidate_is_validated(
        self,
    ) -> None:
        schema = decode_identity_object(
            self.fixture.schema_raw,
            label="phase-freeze test schema",
        )
        self.assertEqual(PHASE_FREEZE_SCHEMA_DRAFT, schema["$schema"])
        self.assertEqual(PHASE_FREEZE_SCHEMA_ID, schema["$id"])
        self.assertEqual(
            PHASE_FREEZE_SCHEMA_CONTENT_SHA256,
            canonical_json_sha256(schema),
        )
        self.assertEqual(
            PHASE_FREEZE_SCHEMA_FILE_SHA256,
            sha256_bytes(self.fixture.schema_raw),
        )
        self.assertEqual(PHASE_FREEZE_SCHEMA_SIZE, len(self.fixture.schema_raw))
        Draft202012Validator.check_schema(schema)
        _request, result = self.fixture.bootstrap()
        validator = Draft202012Validator(schema)
        self.assertEqual([], list(validator.iter_errors(
            result.phase_freeze.to_document()
        )))

        document = result.phase_freeze.to_document()
        adversaries: list[dict[str, object]] = []
        extra = copy.deepcopy(document)
        extra["unexpected"] = None
        adversaries.append(extra)
        missing = copy.deepcopy(document)
        del missing["authorities"]["tracks"]  # type: ignore[index]
        adversaries.append(missing)
        wrong_kind = copy.deepcopy(document)
        wrong_kind["authorities"]["catalog"]["kind"] = (  # type: ignore[index]
            "track-registry"
        )
        adversaries.append(wrong_kind)
        boolean_size = copy.deepcopy(document)
        boolean_size["predecessor"]["size"] = True  # type: ignore[index]
        adversaries.append(boolean_size)
        for adversary in adversaries:
            with self.subTest(keys=tuple(adversary)):
                self.assertNotEqual([], list(validator.iter_errors(adversary)))

        changed_schema = copy.deepcopy(schema)
        changed_schema["title"] = "unauthorized replacement"
        changed_raw = rendered_json_bytes(changed_schema)
        inputs = self.fixture.replace_input(
            self.fixture.inputs,
            name="schemas",
            raw=changed_raw,
            semantic=canonical_json_sha256(changed_schema),
        )
        with self.assertRaises(PipelineError):
            plan_phase_freeze(self.fixture.request(inputs=inputs))

        remote_schema = copy.deepcopy(schema)
        remote_schema["$defs"]["sha256"]["$ref"] = (  # type: ignore[index]
            "https://example.invalid/x"
        )
        remote_raw = rendered_json_bytes(remote_schema)
        inputs = self.fixture.replace_input(
            self.fixture.inputs,
            name="schemas",
            raw=remote_raw,
            semantic=canonical_json_sha256(remote_schema),
        )
        with mock.patch.object(
            phase_freeze_module,
            "PHASE_FREEZE_SCHEMA_CONTENT_SHA256",
            canonical_json_sha256(remote_schema),
        ), mock.patch.object(
            phase_freeze_module,
            "PHASE_FREEZE_SCHEMA_FILE_SHA256",
            sha256_bytes(remote_raw),
        ), mock.patch.object(
            phase_freeze_module,
            "PHASE_FREEZE_SCHEMA_SIZE",
            len(remote_raw),
        ):
            with self.assertRaisesRegex(PipelineError, "remote references"):
                plan_phase_freeze(self.fixture.request(inputs=inputs))

    def test_core_spec_is_recomputed_and_catalog_schema_provenance_is_exact(
        self,
    ) -> None:
        document = decode_identity_object(
            self.fixture.core_spec_raw,
            label="CoreSpec fixture mutation",
        )
        document["cores"][0]["strict_spec_sha256"] = "0" * 64  # type: ignore[index]
        _reseal(document["cores"][0])  # type: ignore[index,arg-type]
        _reseal(document)
        raw = rendered_json_bytes(document)
        inputs = self.fixture.replace_input(
            self.fixture.inputs,
            name="core-spec-set",
            raw=raw,
            semantic=document["content_sha256"],  # type: ignore[arg-type]
        )
        with self.assertRaisesRegex(PipelineError, "differs from the catalog"):
            plan_phase_freeze(self.fixture.request(inputs=inputs))

        mutations = (
            ("path", "manifests/other.schema.json"),
            ("file_sha256", "1" * 64),
            ("size", CATALOG_SCHEMA_SIZE + 1),
            ("target_content_sha256", "2" * 64),
        )
        for key, value in mutations:
            document = decode_identity_object(
                self.fixture.core_spec_raw,
                label="CoreSpec schema provenance mutation",
            )
            document["catalog_schema"][key] = value  # type: ignore[index]
            _reseal(document["catalog_schema"])  # type: ignore[index,arg-type]
            _reseal(document)
            raw = rendered_json_bytes(document)
            inputs = self.fixture.replace_input(
                self.fixture.inputs,
                name="core-spec-set",
                raw=raw,
                semantic=document["content_sha256"],  # type: ignore[arg-type]
            )
            with self.subTest(key=key):
                with self.assertRaises(PipelineError):
                    plan_phase_freeze(self.fixture.request(inputs=inputs))

        self.assertEqual(
            CATALOG_SCHEMA_FILE_SHA256,
            self.fixture.catalog_schema_ref.file_sha256,
        )
        self.assertEqual(CATALOG_SCHEMA_SIZE, self.fixture.catalog_schema_ref.size)
        self.assertEqual(
            CATALOG_SCHEMA_CONTENT_SHA256,
            self.fixture.catalog_schema_ref.target_content_sha256,
        )

    def test_core_catalog_intrinsic_envelope_rejects_coordinated_adversaries(
        self,
    ) -> None:
        catalog = decode_identity_object(
            self.fixture.catalog_raw,
            label="core catalog envelope fixture",
        )
        adversaries: list[tuple[str, dict[str, object]]] = []

        missing = copy.deepcopy(catalog)
        del missing["resolver"]
        adversaries.append(("missing-root", missing))

        extra = copy.deepcopy(catalog)
        extra["unexpected"] = None
        adversaries.append(("extra-root", extra))

        wrong_route = copy.deepcopy(catalog)
        wrong_route["$schema"] = "./other.schema.json"
        adversaries.append(("wrong-schema-route", wrong_route))

        boolean_version = copy.deepcopy(catalog)
        boolean_version["schema_version"] = True
        adversaries.append(("boolean-schema-version", boolean_version))

        enabled = copy.deepcopy(catalog)
        enabled["policy"]["publication"] = "enabled"  # type: ignore[index]
        adversaries.append(("enabled-publication", enabled))

        nonmapping_policy = copy.deepcopy(catalog)
        nonmapping_policy["policy"] = []
        adversaries.append(("nonmapping-policy", nonmapping_policy))

        nonmapping_cores = copy.deepcopy(catalog)
        nonmapping_cores["cores"] = []
        adversaries.append(("nonmapping-cores", nonmapping_cores))

        for label, adversary in adversaries:
            with self.subTest(label=label):
                inputs = self.fixture.coordinated_catalog_inputs(adversary)
                with self.assertRaises(PipelineError):
                    plan_phase_freeze(self.fixture.request(inputs=inputs))

    def test_engine_and_intent_require_exact_rendering_paths_and_members(self) -> None:
        with self.assertRaisesRegex(PipelineError, "intent bytes"):
            plan_phase_freeze(self.fixture.request(spec_suffix=b"\n"))
        with self.assertRaisesRegex(PipelineError, "engine bundle bytes"):
            plan_phase_freeze(
                self.fixture.request(engine_raw=self.fixture.engine_raw + b"\n")
            )

        engine = copy.deepcopy(self.fixture.engine_document)
        del engine["files"][REQUIRED_ENGINE_MEMBERS[0]]  # type: ignore[index]
        engine["content_sha256"] = pipeline_bundle_content_sha256(
            engine["files"]  # type: ignore[arg-type]
        )
        with self.assertRaisesRegex(PipelineError, "lacks required"):
            plan_phase_freeze(self.fixture.request(engine_document=engine))

        request = self.fixture.request()
        wrong_spec = replace(
            request.spec_ref,
            path="manifests/campaign-transitions/other.json",
        )
        with self.assertRaisesRegex(PipelineError, "intent reference path"):
            plan_phase_freeze(replace(request, spec_ref=wrong_spec))
        wrong_engine = replace(
            request.engine_bundle_ref,
            path="manifests/campaign-engine-bundles/other.json",
        )
        with self.assertRaisesRegex(PipelineError, "engine bundle reference path"):
            plan_phase_freeze(replace(request, engine_bundle_ref=wrong_engine))

    def test_wire_record_is_closed_strict_detached_frozen_and_exactly_sorted(
        self,
    ) -> None:
        _request, result = self.fixture.bootstrap()
        value = result.phase_freeze
        self.assertFalse(hasattr(value, "__dict__"))
        self.assertEqual(
            (
                "campaign_id",
                "transition_id",
                "captured_at",
                "predecessor",
                "authorities",
            ),
            tuple(field.name for field in fields(PhaseFreezeV1)),
        )
        with self.assertRaises(FrozenInstanceError):
            value.campaign_id = "changed"  # type: ignore[misc]
        with self.assertRaises(PipelineError):
            replace(value, authorities=tuple(reversed(value.authorities)))

        detached = value.to_document()
        detached["authorities"]["catalog"]["path"] = "changed"  # type: ignore[index]
        self.assertEqual(CATALOG_PATH, value.authorities[0].reference.path)

        raw = value.to_document()
        raw["unexpected"] = None
        with self.assertRaises(PipelineError):
            PhaseFreezeV1.from_document(raw)
        boolean_alias = value.to_document()
        boolean_alias["predecessor"]["size"] = True  # type: ignore[index]
        with self.assertRaises(PipelineError):
            PhaseFreezeV1.from_document(boolean_alias)
        duplicate = result.candidate_raw.replace(
            b'  "campaign_id":',
            b'  "campaign_id": "duplicate",\n  "campaign_id":',
            1,
        )
        with self.assertRaises(PipelineError):
            decode_phase_freeze(duplicate)
        floating = result.candidate_raw.replace(
            f'"size": {value.predecessor.size}'.encode(),
            f'"size": {value.predecessor.size}.0'.encode(),
            1,
        )
        with self.assertRaises(PipelineError):
            decode_phase_freeze(floating)

    def test_validator_reconstructs_and_rejects_plan_or_byte_tampering(self) -> None:
        request, result = self.fixture.bootstrap()
        tampered_plan = replace(
            result.plan,
            reason="Tampered but structurally valid reason.",
        )
        tampered = PlannedPhaseFreeze(
            plan=tampered_plan,
            phase_freeze=result.phase_freeze,
            candidate_raw=result.candidate_raw,
        )
        with self.assertRaisesRegex(PipelineError, "plan differs"):
            validate_phase_freeze(tampered, request=request)
        with self.assertRaises(PipelineError):
            replace(result, candidate_raw=result.candidate_raw + b" ")
        with self.assertRaises(PipelineError):
            validate_phase_freeze(object(), request=request)  # type: ignore[arg-type]

    def test_planner_is_pure_from_hydrated_bytes_in_an_adversarial_temp_root(
        self,
    ) -> None:
        request = self.fixture.request()
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary_root:
            try:
                os.chdir(temporary_root)
                with mock.patch(
                    "builtins.open",
                    side_effect=AssertionError("planner attempted a live read"),
                ):
                    result = plan_phase_freeze(request)
            finally:
                os.chdir(original)
        self.assertEqual(request.spec_ref, result.plan.intent)

        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            {"os", "pathlib", "subprocess", "importlib", "time"}.isdisjoint(
                imported_roots
            )
        )
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(
            {"open", "exec", "eval", "compile", "__import__"}.isdisjoint(calls)
        )

    def test_schema_and_module_publish_only_the_closed_phase_freeze_surface(
        self,
    ) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        authorities = schema["properties"]["authorities"]
        self.assertEqual(set(INPUT_ROLE_NAMES), set(authorities["required"]))
        self.assertEqual(set(INPUT_ROLE_NAMES), set(authorities["properties"]))
        self.assertIs(authorities["additionalProperties"], False)
        self.assertNotIn("payload", schema["properties"])
        self.assertNotIn("allowed_changes", schema["properties"])
        self.assertNotIn("workflow", phase_freeze_module.__all__)
        self.assertEqual(
            {
                "PhaseFreezeV1",
                "PlannedPhaseFreeze",
                "decode_phase_freeze",
                "render_phase_freeze",
                "plan_phase_freeze",
                "validate_phase_freeze",
            },
            {
                name
                for name in phase_freeze_module.__all__
                if name.endswith("V1")
                or name.startswith(("decode_", "render_", "plan_", "validate_"))
                or name == "PlannedPhaseFreeze"
            },
        )


if __name__ == "__main__":
    unittest.main()
