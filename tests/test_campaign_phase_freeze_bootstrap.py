from __future__ import annotations

import ast
import copy
from pathlib import Path
import unittest
from unittest import mock

from scripts.core_pipeline_lib.campaign.json_wire import (
    decode_identity_object,
)
from scripts.core_pipeline_lib.campaign.phase_freeze import (
    BOOTSTRAP_KIND,
    CAMPAIGN_STATE_RELATIVE,
    render_phase_freeze,
    validate_phase_freeze,
)
from scripts.core_pipeline_lib.campaign import phase_freeze_bootstrap as bootstrap
from scripts.core_pipeline_lib.campaign.phase_freeze_bootstrap import (
    CAMPAIGN_ID,
    DEFAULT_TRANSITION_ID,
    LEGACY_PREDECESSOR_CONTENT_SHA256,
    LEGACY_PREDECESSOR_FILE_SHA256,
    LEGACY_PREDECESSOR_PATH,
    LEGACY_PREDECESSOR_SIZE,
    collect_repository_phase_freeze_bootstrap,
    plan_repository_phase_freeze_bootstrap,
)
from scripts.core_pipeline_lib.campaign.transition_model import TransitionIntentV1
from scripts.core_pipeline_lib.campaign.transition_registry import (
    INPUT_ROLE_NAMES,
    REQUIRED_ENGINE_MEMBERS,
    definition_for,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.source_bundle import (
    pipeline_bundle_content_sha256,
    pipeline_source_bundle_is_well_formed,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "scripts"
    / "core_pipeline_lib"
    / "campaign"
    / "phase_freeze_bootstrap.py"
)
CAPTURED_AT = "2026-08-15T02:00:00Z"


class CampaignPhaseFreezeBootstrapTests(unittest.TestCase):
    def test_collector_hydrates_the_exact_registered_repository_authorities(
        self,
    ) -> None:
        request = collect_repository_phase_freeze_bootstrap(
            repository_root=ROOT,
            captured_at=CAPTURED_AT,
        )
        intent = TransitionIntentV1.from_document(request.spec_raw)
        definition = definition_for(BOOTSTRAP_KIND)

        self.assertEqual(INPUT_ROLE_NAMES, tuple(item.name for item in request.inputs))
        self.assertEqual(INPUT_ROLE_NAMES, intent.changed_authorities)
        self.assertEqual(
            INPUT_ROLE_NAMES,
            tuple(item.name for item in intent.inputs),
        )
        self.assertEqual(CAMPAIGN_ID, intent.campaign_id)
        self.assertEqual(DEFAULT_TRANSITION_ID, intent.transition_id)
        self.assertEqual(CAPTURED_AT, intent.captured_at)
        self.assertEqual(BOOTSTRAP_KIND, intent.kind)
        self.assertEqual(
            definition.spec_path_template.format(
                transition_id=DEFAULT_TRANSITION_ID
            ),
            request.spec_ref.path,
        )
        self.assertEqual(
            definition.engine_bundle_path_template.format(
                transition_id=DEFAULT_TRANSITION_ID
            ),
            request.engine_bundle_ref.path,
        )

        predecessor = intent.predecessor
        self.assertEqual("phase-freeze", predecessor.kind)
        self.assertEqual(LEGACY_PREDECESSOR_PATH, predecessor.path)
        self.assertEqual(
            LEGACY_PREDECESSOR_CONTENT_SHA256,
            predecessor.target_content_sha256,
        )
        self.assertEqual(LEGACY_PREDECESSOR_FILE_SHA256, predecessor.file_sha256)
        self.assertEqual(LEGACY_PREDECESSOR_SIZE, predecessor.size)
        self.assertEqual(
            (ROOT / LEGACY_PREDECESSOR_PATH).read_bytes(),
            request.predecessor_raw,
        )

        by_name = {item.name: item for item in request.inputs}
        self.assertEqual("track-registry", by_name["tracks"].reference.kind)
        self.assertEqual(
            "manifests/campaign-phase-freeze-v1.schema.json",
            by_name["schemas"].reference.path,
        )
        for role in ("instrumentation", "recipe-auxiliaries", "workflows"):
            document = decode_identity_object(
                by_name[role].raw,
                label=f"{role} file set",
            )
            self.assertEqual("spruce-repository-file-set-v1", document["format"])
            self.assertEqual(role, document["role"])
            self.assertTrue(document["files"])
            self.assertEqual(
                sorted(document["files"]),
                list(document["files"]),
            )

        engine = decode_identity_object(
            request.engine_bundle_raw,
            label="repository bootstrap engine bundle",
        )
        self.assertTrue(pipeline_source_bundle_is_well_formed(engine))
        self.assertEqual(
            request.engine_bundle_ref.target_content_sha256,
            engine["content_sha256"],
        )
        self.assertTrue(set(REQUIRED_ENGINE_MEMBERS) <= set(engine["files"]))
        self.assertIn(
            "scripts/core_pipeline_lib/campaign/phase_freeze_bootstrap.py",
            engine["files"],
        )

    def test_planner_double_snapshots_and_validates_the_pure_successor(self) -> None:
        first = plan_repository_phase_freeze_bootstrap(
            repository_root=ROOT,
            captured_at=CAPTURED_AT,
        )
        second = plan_repository_phase_freeze_bootstrap(
            repository_root=ROOT,
            captured_at=CAPTURED_AT,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first.result.candidate_raw,
            render_phase_freeze(first.result.phase_freeze),
        )
        self.assertEqual(
            INPUT_ROLE_NAMES,
            tuple(item.name for item in first.result.phase_freeze.authorities),
        )
        self.assertEqual(
            LEGACY_PREDECESSOR_CONTENT_SHA256,
            first.result.phase_freeze.predecessor.target_content_sha256,
        )
        self.assertEqual(
            first.result.phase_freeze.content_sha256,
            first.result.plan.successor.target_content_sha256,
        )
        self.assertEqual("phase-freeze.bootstrap.v1", first.result.plan.handler_id)
        self.assertEqual("disabled", first.result.phase_freeze.publication)
        self.assertTrue(first.result.phase_freeze.local_only)
        validate_phase_freeze(first.result, request=first.request)

    def test_legacy_predecessor_is_authenticated_without_decoding(self) -> None:
        original = bootstrap.CampaignStore.read_snapshot

        def tampered_read(store: object, relative: str) -> bytes:
            raw = original(store, relative)  # type: ignore[arg-type]
            if relative == LEGACY_PREDECESSOR_PATH:
                return raw[:-1] + bytes((raw[-1] ^ 1,))
            return raw

        with mock.patch.object(
            bootstrap.CampaignStore,
            "read_snapshot",
            new=tampered_read,
        ):
            with self.assertRaisesRegex(
                PipelineError,
                "opaque legacy phase-freeze predecessor moved",
            ):
                collect_repository_phase_freeze_bootstrap(
                    repository_root=ROOT,
                    captured_at=CAPTURED_AT,
                )

    def test_unstable_live_engine_bundle_fails_closed_without_a_manifest(self) -> None:
        first = bootstrap.pipeline_source_bundle()
        second = copy.deepcopy(first)
        files = second["files"]
        self.assertIsInstance(files, dict)
        files["scripts/core_pipeline.py"] = "f" * 64
        second["content_sha256"] = pipeline_bundle_content_sha256(files)
        self.assertTrue(pipeline_source_bundle_is_well_formed(second))
        with mock.patch.object(
            bootstrap,
            "pipeline_source_bundle",
            side_effect=(first, second),
        ):
            with self.assertRaisesRegex(
                PipelineError,
                "engine bundle is unstable",
            ):
                collect_repository_phase_freeze_bootstrap(
                    repository_root=ROOT,
                    captured_at=CAPTURED_AT,
                )

    def test_adapter_source_has_no_mutation_process_clock_or_cli_surface(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            {"subprocess", "datetime", "time", "argparse"}.isdisjoint(
                imported_roots
            )
        )
        forbidden_calls = {
            "create_or_verify",
            "mkdir",
            "open",
            "replace",
            "rename",
            "run",
            "system",
            "transaction",
            "unlink",
            "write_bytes",
            "write_text",
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertTrue(forbidden_calls.isdisjoint(called_names | called_attributes))
        self.assertNotIn("main", bootstrap.__all__)
        self.assertEqual(".local-e2e/campaign-state", CAMPAIGN_STATE_RELATIVE)

    def test_collector_rejects_a_root_other_than_the_loaded_pipeline(self) -> None:
        with self.assertRaisesRegex(
            PipelineError,
            "differs from the loaded pipeline source",
        ):
            collect_repository_phase_freeze_bootstrap(
                repository_root=Path("/tmp"),
                captured_at=CAPTURED_AT,
            )


if __name__ == "__main__":
    unittest.main()
