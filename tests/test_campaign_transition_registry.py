from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, fields, replace
import json
from pathlib import Path
from types import MappingProxyType
import unittest

from jsonschema import Draft202012Validator

from scripts.core_pipeline_lib.campaign.json_wire import rendered_json_bytes
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.campaign.transition_model import (
    INTENT_FORMAT,
    PLAN_FORMAT,
    NamedEvidenceRef,
    ResolvedTransitionPlanV1,
    TransitionDeltaV1,
    TransitionIntentV1,
)
from scripts.core_pipeline_lib.campaign.transition_registry import (
    BOOTSTRAP_REQUIRED_CHECKS,
    ENGINE_BUNDLE_PATH_TEMPLATE,
    INPUT_ROLES,
    INPUT_ROLE_NAMES,
    PHASE_FREEZE_FORMAT,
    REFRESH_REQUIRED_CHECKS,
    REQUIRED_ENGINE_MEMBERS,
    SPEC_PATH_TEMPLATE,
    TRANSITION_BY_KIND,
    TRANSITION_DEFINITIONS,
    InputRoleDefinition,
    TransitionDefinition,
    definition_for,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "transition_registry.py"
)
INTENT_SCHEMA_PATH = ROOT / "manifests" / "campaign-transition-intent-v1.schema.json"
PLAN_SCHEMA_PATH = ROOT / "manifests" / "campaign-transition-plan-v1.schema.json"

EXPECTED_ENGINE_MEMBERS = (
    "scripts/core_pipeline_lib/campaign/json_wire.py",
    "scripts/core_pipeline_lib/campaign/model.py",
    "scripts/core_pipeline_lib/campaign/phase_freeze.py",
    "scripts/core_pipeline_lib/campaign/projection.py",
    "scripts/core_pipeline_lib/campaign/transition_model.py",
    "scripts/core_pipeline_lib/campaign/transition_registry.py",
    "scripts/core_pipeline_lib/core_spec.py",
)

EXPECTED_ROLE_NAMES = (
    "catalog",
    "commit-blacklist",
    "core-spec-set",
    "host-execution",
    "instrumentation",
    "recipe-auxiliaries",
    "schemas",
    "spruce-branch-bases",
    "spruce-release-roster",
    "telemetry-schema",
    "toolchain-lock",
    "tracks",
    "tunings",
    "workflows",
)

EXPECTED_BOOTSTRAP_CHECKS = (
    "campaign.plan.identity",
    "phase-freeze.inputs.identity",
    "phase-freeze.core-spec-set",
    "phase-freeze.legacy-lineage",
    "phase-freeze.schema",
    "phase-freeze.successor.identity",
    "publication.disabled",
)

EXPECTED_REFRESH_CHECKS = (
    "campaign.plan.identity",
    "phase-freeze.inputs.identity",
    "phase-freeze.core-spec-set",
    "phase-freeze.delta",
    "phase-freeze.schema",
    "phase-freeze.successor.identity",
    "publication.disabled",
)


def _sha256(number: int) -> str:
    return f"{number:064x}"


def _ref(kind: str, name: str, raw: bytes, semantic: int) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=f"campaign/evidence/{name}.json",
        file_sha256=sha256_bytes(raw),
        target_content_sha256=_sha256(semantic),
        size=len(raw),
    )


def _intent() -> TransitionIntentV1:
    predecessor_raw = b"legacy freeze"
    catalog_raw = b"catalog"
    return TransitionIntentV1(
        transition_id="phase-freeze-bootstrap-20260814",
        campaign_id="host-core-build-20260810",
        kind="phase-freeze-bootstrap-v1",
        captured_at="2026-08-14T20:00:00Z",
        reason="Bootstrap the strict phase-freeze authority.",
        predecessor=_ref("phase-freeze", "predecessor", predecessor_raw, 1),
        inputs=(
            NamedEvidenceRef(
                name="catalog",
                reference=_ref("artifact", "catalog", catalog_raw, 2),
            ),
        ),
        changed_authorities=("catalog",),
    )


def _plan() -> ResolvedTransitionPlanV1:
    intent = _intent()
    intent_raw = rendered_json_bytes(intent.to_document())
    candidate_raw = b"strict phase freeze"
    return ResolvedTransitionPlanV1(
        transition_id=intent.transition_id,
        campaign_id=intent.campaign_id,
        kind=intent.kind,
        handler_id="phase-freeze.bootstrap.v1",
        captured_at=intent.captured_at,
        reason=intent.reason,
        intent=_ref("transition-spec", "intent", intent_raw, 3),
        engine_bundle=_ref("engine-bundle", "engine", b"engine", 4),
        predecessor=intent.predecessor,
        inputs=intent.inputs,
        successor=_ref("phase-freeze-cas", "successor", candidate_raw, 5),
        delta=TransitionDeltaV1(
            allowed_changes=("/captured_at",),
            required_changes=("/captured_at",),
            changed_pointers=("/captured_at",),
            preserved_projection_sha256=_sha256(6),
        ),
        required_checks=EXPECTED_BOOTSTRAP_CHECKS,
        process_tier="evidence",
    )


class CampaignTransitionRegistryTests(unittest.TestCase):
    def test_registry_contains_only_exact_bootstrap_and_refresh_definitions(self) -> None:
        self.assertEqual(
            ("phase-freeze-bootstrap-v1", "phase-freeze-refresh-v1"),
            tuple(definition.kind for definition in TRANSITION_DEFINITIONS),
        )
        self.assertIsInstance(TRANSITION_BY_KIND, MappingProxyType)
        self.assertEqual(
            tuple(TRANSITION_BY_KIND),
            tuple(definition.kind for definition in TRANSITION_DEFINITIONS),
        )
        for definition in TRANSITION_DEFINITIONS:
            self.assertIs(definition, definition_for(definition.kind))
            self.assertEqual(INTENT_FORMAT, definition.spec_format)
            self.assertEqual(PHASE_FREEZE_FORMAT, definition.candidate_format)
            self.assertEqual(SPEC_PATH_TEMPLATE, definition.spec_path_template)
            self.assertEqual(
                ENGINE_BUNDLE_PATH_TEMPLATE,
                definition.engine_bundle_path_template,
            )
            self.assertEqual(EXPECTED_ENGINE_MEMBERS, definition.required_engine_members)
            self.assertEqual("phase-freeze-cas", definition.output_kind)
            self.assertEqual("evidence", definition.process_tier)

    def test_exact_handler_predecessor_mutation_and_check_policies_are_frozen(self) -> None:
        bootstrap = definition_for("phase-freeze-bootstrap-v1")
        refresh = definition_for("phase-freeze-refresh-v1")
        self.assertEqual("phase-freeze.bootstrap.v1", bootstrap.handler_id)
        self.assertEqual(
            "opaque-legacy-phase-freeze-v2",
            bootstrap.predecessor_policy,
        )
        self.assertEqual(
            "construct-strict-phase-freeze-v1",
            bootstrap.mutation_policy,
        )
        self.assertEqual(EXPECTED_BOOTSTRAP_CHECKS, bootstrap.required_checks)

        self.assertEqual("phase-freeze.refresh.v1", refresh.handler_id)
        self.assertEqual("strict-phase-freeze-v1", refresh.predecessor_policy)
        self.assertEqual("exact-authority-delta-v1", refresh.mutation_policy)
        self.assertEqual(EXPECTED_REFRESH_CHECKS, refresh.required_checks)
        self.assertEqual(
            {"phase-freeze.legacy-lineage", "phase-freeze.delta"},
            set(bootstrap.required_checks) ^ set(refresh.required_checks),
        )
        self.assertEqual(BOOTSTRAP_REQUIRED_CHECKS, EXPECTED_BOOTSTRAP_CHECKS)
        self.assertEqual(REFRESH_REQUIRED_CHECKS, EXPECTED_REFRESH_CHECKS)

    def test_all_fourteen_input_roles_require_semantic_targets(self) -> None:
        self.assertEqual(EXPECTED_ROLE_NAMES, INPUT_ROLE_NAMES)
        self.assertEqual(EXPECTED_ROLE_NAMES, tuple(role.name for role in INPUT_ROLES))
        self.assertEqual(14, len(INPUT_ROLES))
        for role in INPUT_ROLES:
            with self.subTest(role=role.name):
                self.assertIs(role.target_content_required, True)
                self.assertEqual(
                    ("artifact", "track-registry")
                    if role.name == "tracks"
                    else ("artifact",),
                    role.allowed_kinds,
                )
        for definition in TRANSITION_DEFINITIONS:
            self.assertIs(INPUT_ROLES, definition.input_roles)

    def test_exact_required_engine_members_are_sorted_code_owned_sources(self) -> None:
        self.assertEqual(EXPECTED_ENGINE_MEMBERS, REQUIRED_ENGINE_MEMBERS)
        self.assertEqual(tuple(sorted(REQUIRED_ENGINE_MEMBERS)), REQUIRED_ENGINE_MEMBERS)
        self.assertEqual(7, len(REQUIRED_ENGINE_MEMBERS))
        self.assertTrue(
            all(
                member.startswith("scripts/core_pipeline_lib/")
                and member.endswith(".py")
                for member in REQUIRED_ENGINE_MEMBERS
            )
        )

    def test_registry_models_and_mapping_are_frozen_slotted_and_closed(self) -> None:
        role = INPUT_ROLES[0]
        definition = TRANSITION_DEFINITIONS[0]
        for value in (role, definition):
            self.assertFalse(hasattr(value, "__dict__"))
            with self.assertRaises(FrozenInstanceError):
                setattr(value, fields(value)[0].name, "replacement")
        with self.assertRaises(TypeError):
            TRANSITION_BY_KIND["replacement"] = definition  # type: ignore[index]
        self.assertEqual(
            ("name", "allowed_kinds", "target_content_required"),
            tuple(field.name for field in fields(InputRoleDefinition)),
        )
        self.assertEqual(
            (
                "kind",
                "handler_id",
                "spec_format",
                "candidate_format",
                "spec_path_template",
                "engine_bundle_path_template",
                "required_engine_members",
                "input_roles",
                "output_kind",
                "required_checks",
                "process_tier",
                "predecessor_policy",
                "mutation_policy",
            ),
            tuple(field.name for field in fields(TransitionDefinition)),
        )

    def test_registry_has_no_dynamic_import_registration_or_dispatch_surface(self) -> None:
        tree = ast.parse(
            REGISTRY_PATH.read_text(encoding="utf-8"),
            filename=str(REGISTRY_PATH),
        )
        imports: set[str] = set()
        called_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called_names.add(node.func.id)
        self.assertNotIn("importlib", imports)
        self.assertNotIn("__import__", called_names)
        self.assertTrue(
            {"module", "module_path", "callable", "handler"}.isdisjoint(
                field.name for field in fields(TransitionDefinition)
            )
        )
        public_functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not node.name.startswith("_")
        }
        self.assertEqual({"definition_for"}, public_functions)

    def test_unknown_or_nonexact_kind_fails_closed(self) -> None:
        for kind in ("unknown", 1, None):
            with self.subTest(kind=kind):
                with self.assertRaises(PipelineError):
                    definition_for(kind)  # type: ignore[arg-type]

    def test_role_definition_rejects_unordered_duplicate_unknown_and_unbound_policy(self) -> None:
        valid = InputRoleDefinition(
            name="tracks",
            allowed_kinds=("artifact", "track-registry"),
            target_content_required=True,
        )
        mutations = (
            {"allowed_kinds": ("track-registry", "artifact")},
            {"allowed_kinds": ("artifact", "artifact")},
            {"allowed_kinds": ("unknown",)},
            {"allowed_kinds": []},
            {"target_content_required": 1},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(PipelineError):
                    replace(valid, **mutation)

    def test_definition_rejects_invalid_templates_members_roles_checks_and_policies(self) -> None:
        definition = TRANSITION_DEFINITIONS[0]
        mutations = (
            {"spec_path_template": "manifests/static.json"},
            {"engine_bundle_path_template": "../{transition_id}.json"},
            {"required_engine_members": tuple(reversed(REQUIRED_ENGINE_MEMBERS))},
            {"required_engine_members": (["unhashable"],)},
            {"required_engine_members": ("scripts/core_pipeline_lib/bad\x00.py",)},
            {"required_engine_members": ("scripts/core_pipeline_lib/bad\n.py",)},
            {"required_engine_members": ("scripts/core_pipeline_lib/bad\ud800.py",)},
            {"input_roles": tuple(reversed(INPUT_ROLES))},
            {"output_kind": "unknown"},
            {"output_kind": ["unhashable"]},
            {"required_checks": ("duplicate", "duplicate")},
            {"required_checks": (["unhashable"],)},
            {"required_checks": []},
            {"process_tier": "unknown"},
            {"predecessor_policy": "OpaquePolicy"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(PipelineError):
                    replace(definition, **mutation)

    def test_intent_and_plan_schemas_are_closed_valid_draft_202012(self) -> None:
        schemas_and_documents = (
            (
                json.loads(INTENT_SCHEMA_PATH.read_text(encoding="utf-8")),
                _intent().to_document(),
            ),
            (
                json.loads(PLAN_SCHEMA_PATH.read_text(encoding="utf-8")),
                _plan().to_document(),
            ),
        )
        for schema, document in schemas_and_documents:
            with self.subTest(schema=schema["$id"]):
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(document)
                self.assertIs(schema["additionalProperties"], False)
                self.assertEqual(
                    set(schema["required"]),
                    set(schema["properties"]),
                )
                for definition in schema["$defs"].values():
                    if definition.get("type") == "object":
                        self.assertIs(definition["additionalProperties"], False)
                        self.assertEqual(
                            set(definition["required"]),
                            set(definition["properties"]),
                        )

                unexpected = copy.deepcopy(document)
                unexpected["unexpected"] = True
                self.assertTrue(
                    tuple(Draft202012Validator(schema).iter_errors(unexpected))
                )

    def test_schemas_do_not_admit_generic_number_types_or_runtime_handlers(self) -> None:
        for path in (INTENT_SCHEMA_PATH, PLAN_SCHEMA_PATH):
            schema = json.loads(path.read_text(encoding="utf-8"))
            encoded = json.dumps(schema, sort_keys=True)
            with self.subTest(path=path.name):
                self.assertNotIn('"type": "number"', encoded)
                self.assertNotIn("module_path", encoded)
                self.assertNotIn("importlib", encoded)
                self.assertNotIn("handler_module", encoded)


if __name__ == "__main__":
    unittest.main()
