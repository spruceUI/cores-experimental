from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import unittest

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.checks import (
    CHECK_BY_ID,
    CHECK_DEFINITIONS,
    FULL_STATIC_ALLOWED_SKIPS,
    FULL_STATIC_ARGV,
    FULL_STATIC_BASELINE_MILLISECONDS,
    FULL_STATIC_CEILING_MILLISECONDS,
    CheckInstrumentation,
    CheckReceipt,
    CheckResult,
    CheckTier,
    LocalSubprocessService,
    StructuredFormat,
    check_ids_for_tier,
    checks_for_tiers,
    definition_for,
)


ROOT = Path(__file__).resolve().parents[1]
CHECK_PACKAGE = ROOT / "scripts" / "core_pipeline_lib" / "checks"


QUICK_IDS = (
    "toolchain.lock-metadata",
    "pipeline.workflow-audit",
    "tests.runner-contracts",
    "tests.pipeline-regression",
    "repository.diff-check",
)
STATIC_IDS = QUICK_IDS + ("pipeline.catalog", "tests.full-static")
EVIDENCE_IDS = STATIC_IDS + (
    "evidence.promoted-core-sweep",
    "evidence.toolchain-store",
    "evidence.toolchain-downloads",
)
REBUILD_IDS = EVIDENCE_IDS + ("release-candidate-roster",)


class ConsolidatedCheckRegistryTests(unittest.TestCase):
    def test_tiers_expand_cumulatively_in_stable_order(self) -> None:
        self.assertEqual(QUICK_IDS, check_ids_for_tier("quick"))
        self.assertEqual(STATIC_IDS, check_ids_for_tier(CheckTier.STATIC))
        self.assertEqual(EVIDENCE_IDS, check_ids_for_tier("evidence"))
        self.assertEqual(REBUILD_IDS, check_ids_for_tier("rebuild"))

    def test_multi_tier_expansion_deduplicates_in_registry_order(self) -> None:
        definitions = checks_for_tiers(
            (CheckTier.STATIC, CheckTier.QUICK, CheckTier.STATIC)
        )
        self.assertEqual(STATIC_IDS, tuple(item.check_id for item in definitions))

    def test_documented_commands_are_exact_argv_tuples(self) -> None:
        expected = {
            "toolchain.lock-metadata": (
                "python3",
                "scripts/toolchain_archive.py",
                "validate-lock",
            ),
            "pipeline.workflow-audit": (
                "python3",
                "scripts/core_pipeline.py",
                "audit-workflows",
            ),
            "tests.runner-contracts": (
                "python3",
                "-m",
                "unittest",
                "tests.test_runner_profiles",
                "tests.test_runner_evidence",
                "tests.test_pipeline_source_bundle",
                "tests.test_commit_blacklist",
            ),
            "tests.pipeline-regression": (
                "python3",
                "-m",
                "unittest",
                "tests.test_core_pipeline",
            ),
            "repository.diff-check": ("git", "diff", "--check"),
            "pipeline.catalog": (
                "python3",
                "scripts/core_pipeline.py",
                "catalog-check",
            ),
            "tests.full-static": FULL_STATIC_ARGV,
            "evidence.promoted-core-sweep": (
                "python3",
                "scripts/verify_core.py",
                "--all",
            ),
            "evidence.toolchain-store": (
                "python3",
                "scripts/toolchain_archive.py",
                "validate-lock",
                "--verify-store",
            ),
        }
        for check_id, argv in expected.items():
            with self.subTest(check_id=check_id):
                definition = definition_for(check_id)
                self.assertIs(type(definition.argv_prefix), tuple)
                self.assertEqual(argv, definition.render_argv())

    def test_full_static_contract_freezes_runtime_and_exact_skips(self) -> None:
        definition = definition_for("tests.full-static")
        self.assertEqual(
            (
                "python3",
                "-B",
                "-m",
                "pytest",
                "--import-mode=importlib",
                "-p",
                "no:cacheprovider",
                "tests/",
                "-q",
            ),
            definition.render_argv(),
        )
        self.assertEqual(917_350, FULL_STATIC_BASELINE_MILLISECONDS)
        self.assertEqual(1_009_085, FULL_STATIC_CEILING_MILLISECONDS)
        self.assertEqual(
            FULL_STATIC_CEILING_MILLISECONDS,
            definition.timeout_milliseconds,
        )
        self.assertEqual(
            (
                "tests/test_toolchain_archive.py::RealToolchainArchiveTests::"
                "test_current_archives_reproduce_the_complete_tracked_lock",
                "tests/test_toolchain_archive.py::RealToolchainArchiveTests::"
                "test_real_downloads_match_the_tracked_lock",
            ),
            FULL_STATIC_ALLOWED_SKIPS,
        )
        self.assertIs(definition.instrumentation, CheckInstrumentation.PYTEST)
        self.assertEqual(
            (StructuredFormat.JSON, StructuredFormat.JUNIT),
            definition.required_structured_formats,
        )

    def test_registry_exposes_a_concrete_no_shell_subprocess_service(self) -> None:
        self.assertTrue(callable(LocalSubprocessService().run))

    def test_toolchain_download_template_uses_validated_separate_tokens(self) -> None:
        definition = definition_for("evidence.toolchain-downloads")
        workflow_parameters = {
            "arm64_archive": "cores-arm64.tar.gz",
            "armhf_archive": "cores-armhf.tar.gz",
        }
        workflow_argv = (
            "python3",
            "-B",
            "scripts/toolchain_archive.py",
            "verify-downloads",
            "--lock",
            "pins/toolchains/local-cache-v1.json",
            "--arm64",
            "cores-arm64.tar.gz",
            "--armhf",
            "cores-armhf.tar.gz",
        )
        self.assertEqual(workflow_argv, definition.render_argv(workflow_parameters))
        self.assertTrue(definition.accepts_argv(workflow_argv))

        with_rust = definition.render_argv(
            {**workflow_parameters, "rust_archive": "archives/cores-rust.tar.gz"}
        )
        self.assertEqual(
            workflow_argv + ("--rust", "archives/cores-rust.tar.gz"), with_rust
        )
        self.assertTrue(definition.accepts_argv(with_rust))
        self.assertFalse(
            definition.accepts_argv(
                workflow_argv[:6]
                + (
                    "--armhf",
                    "cores-armhf.tar.gz",
                    "--arm64",
                    "cores-arm64.tar.gz",
                )
            )
        )

    def test_toolchain_download_template_rejects_missing_extra_and_unsafe_values(self) -> None:
        definition = definition_for("evidence.toolchain-downloads")
        valid = {
            "arm64_archive": "cores-arm64.tar.gz",
            "armhf_archive": "cores-armhf.tar.gz",
        }
        invalid_values = (
            {"arm64_archive": "cores-arm64.tar.gz"},
            {**valid, "other": "archive.tar.gz"},
            {**valid, "arm64_archive": Path("cores-arm64.tar.gz")},
            {**valid, "arm64_archive": "bad\x00path"},
            {**valid, "arm64_archive": "--output=owned"},
        )
        for parameters in invalid_values:
            with self.subTest(parameters=parameters):
                with self.assertRaises(PipelineError):
                    definition.render_argv(parameters)

    def test_registry_models_and_mapping_are_immutable_and_slotted(self) -> None:
        definition = CHECK_DEFINITIONS[0]
        self.assertFalse(hasattr(definition, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            definition.check_id = "replacement"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            CHECK_BY_ID["replacement"] = definition  # type: ignore[index]

    def test_check_models_remain_process_facts_not_campaign_authority(self) -> None:
        campaign_fields = {
            "campaign_id",
            "transition_id",
            "plan",
            "stage",
            "inputs",
            "outputs",
            "state_root",
        }
        self.assertTrue(
            campaign_fields.isdisjoint(field.name for field in fields(CheckResult))
        )
        self.assertTrue(
            campaign_fields.isdisjoint(field.name for field in fields(CheckReceipt))
        )

    def test_check_package_does_not_import_campaign_or_launcher_layers(self) -> None:
        violations: list[str] = []
        for path in sorted(CHECK_PACKAGE.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imported = (node.module or "",)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = (node.module,)
                else:
                    continue
                for module in imported:
                    if module == "campaign" or module.startswith("campaign."):
                        violations.append(f"{path.name}: {module}")
                    if module == "scripts.core_pipeline" or module.startswith(
                        "scripts.core_pipeline."
                    ):
                        violations.append(f"{path.name}: {module}")
                    if (
                        module == "scripts.core_pipeline_lib.campaign"
                        or module.startswith("scripts.core_pipeline_lib.campaign.")
                    ):
                        violations.append(f"{path.name}: {module}")
        self.assertEqual([], violations)

    def test_unknown_tier_check_and_incomplete_tier_input_fail_closed(self) -> None:
        with self.assertRaises(PipelineError):
            check_ids_for_tier("unknown")
        with self.assertRaises(PipelineError):
            definition_for("unknown.check")
        with self.assertRaises(PipelineError):
            checks_for_tiers("quick")
        with self.assertRaises(PipelineError):
            checks_for_tiers(())


if __name__ == "__main__":
    unittest.main()
