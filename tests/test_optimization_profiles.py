from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from core_pipeline_lib.errors import PipelineError  # noqa: E402
from core_pipeline_lib.optimizations import (  # noqa: E402
    BASELINE_OPTIMIZATION_PROFILE,
    BUILD_ARGUMENT_MAPPING_VERSION,
    make_variables_for_profile,
    optimization_profile_errors,
    optimization_profiles_content_sha256,
    resolved_optimization_profile,
    validate_optimization_profiles,
)

REGISTRY_PATH = REPOSITORY_ROOT / "manifests/optimization-profiles.json"
SCHEMA_PATH = REPOSITORY_ROOT / "manifests/optimization-profiles.schema.json"


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def _rehash(document: dict) -> dict:
    document["content_sha256"] = optimization_profiles_content_sha256(document)
    return document


class OptimizationRegistryTests(unittest.TestCase):
    def test_the_shipped_registry_validates_against_its_schema(self):
        Draft202012Validator(json.loads(SCHEMA_PATH.read_text())).validate(_registry())

    def test_the_shipped_registry_passes_the_typed_contract(self):
        self.assertEqual(optimization_profile_errors(_registry()), [])

    def test_the_baseline_profile_contributes_nothing(self):
        """An unselected optimization dimension must reproduce the recorded goldens."""

        resolved = resolved_optimization_profile(
            _registry(), BASELINE_OPTIMIZATION_PROFILE
        )
        self.assertEqual(resolved["make_variables"], [])
        self.assertEqual(resolved["expected_compile_tokens"], [])
        self.assertEqual(resolved["properties"], {})

    def test_debug_asks_make_for_the_libretro_debug_switch(self):
        resolved = resolved_optimization_profile(_registry(), "debug-v1")
        self.assertEqual(resolved["make_variables"], ["DEBUG=1"])
        self.assertEqual(resolved["expected_compile_tokens"], ["-O0", "-g"])

    def test_o3_states_the_level_the_build_log_must_prove(self):
        """A core whose makefile hardcodes -O2 must fail this profile, not pass quietly.

        The expectation is an outcome assertion precisely because an injected -O
        loses to the makefile's own -O, which GCC resolves last-wins.
        """

        resolved = resolved_optimization_profile(_registry(), "release-o3-v1")
        self.assertEqual(resolved["make_variables"], ["DEBUG=0"])
        self.assertEqual(resolved["expected_compile_tokens"], ["-O3"])

    def test_identity_separates_every_profile(self):
        digests = {
            profile_id: resolved_optimization_profile(_registry(), profile_id)[
                "content_sha256"
            ]
            for profile_id in _registry()["profiles"]
        }
        self.assertEqual(len(set(digests.values())), len(digests))

    def test_mapping_version_is_pinned(self):
        self.assertEqual(
            _registry()["build_argument_mapping_version"],
            BUILD_ARGUMENT_MAPPING_VERSION,
        )


class OptimizationRegistryRejectionTests(unittest.TestCase):
    def test_a_stale_content_hash_is_rejected(self):
        document = _registry()
        document["content_sha256"] = "0" * 64
        self.assertIn(
            "optimization content_sha256 is stale",
            optimization_profile_errors(document),
        )

    def test_unsorted_profiles_are_rejected(self):
        document = _registry()
        document["profiles"] = dict(reversed(list(document["profiles"].items())))
        self.assertIn(
            "optimization profiles must be sorted by profile ID",
            optimization_profile_errors(_rehash(document)),
        )

    def test_a_raw_flag_is_not_accepted_as_optimization_data(self):
        document = _registry()
        document["profiles"]["debug-v1"]["properties"]["cflags"] = "-O0"
        errors = optimization_profile_errors(_rehash(document))
        self.assertTrue(
            any("unsupported properties: cflags" in error for error in errors), errors
        )

    def test_a_nonempty_baseline_is_rejected(self):
        document = _registry()
        document["profiles"][BASELINE_OPTIMIZATION_PROFILE]["properties"] = {
            "variant": "release"
        }
        errors = optimization_profile_errors(_rehash(document))
        self.assertIn(
            "baseline optimization profile must be the exact empty profile", errors
        )

    def test_debug_cannot_claim_an_optimized_level(self):
        document = _registry()
        document["profiles"]["debug-v1"]["properties"]["expect_opt_level"] = "3"
        errors = optimization_profile_errors(_rehash(document))
        self.assertTrue(
            any("expect_opt_level must be 0 for the debug variant" in e for e in errors),
            errors,
        )

    def test_release_cannot_claim_the_unoptimized_level(self):
        document = _registry()
        document["profiles"]["release-o3-v1"]["properties"]["expect_opt_level"] = "0"
        errors = optimization_profile_errors(_rehash(document))
        self.assertTrue(
            any("contradicts the release variant" in e for e in errors), errors
        )

    def test_an_expectation_without_a_variant_is_rejected(self):
        document = _registry()
        document["profiles"]["release-o3-v1"]["properties"] = {"expect_opt_level": "3"}
        errors = optimization_profile_errors(_rehash(document))
        self.assertTrue(
            any("must name a variant" in e for e in errors), errors
        )

    def test_cyclic_inheritance_is_reported(self):
        document = _registry()
        document["profiles"]["debug-v1"]["extends"] = "release-o3-v1"
        document["profiles"]["release-o3-v1"]["extends"] = "debug-v1"
        errors = optimization_profile_errors(_rehash(document))
        self.assertTrue(any("cyclic" in e for e in errors), errors)

    def test_an_unknown_profile_raises(self):
        with self.assertRaises(PipelineError):
            resolved_optimization_profile(_registry(), "no-such-v1")

    def test_validation_returns_an_independent_copy(self):
        document = _registry()
        validated = validate_optimization_profiles(document)
        validated["profiles"]["debug-v1"]["properties"]["variant"] = "release"
        self.assertEqual(
            document["profiles"]["debug-v1"]["properties"]["variant"], "debug"
        )

    def test_make_variables_accessor_does_not_alias_the_registry(self):
        document = _registry()
        variables = make_variables_for_profile(document, "debug-v1")
        variables.append("INJECTED=1")
        self.assertEqual(make_variables_for_profile(document, "debug-v1"), ["DEBUG=1"])

    def test_an_unexpected_top_level_field_is_rejected(self):
        document = _registry()
        document["extra"] = True
        self.assertEqual(
            optimization_profile_errors(document),
            ["optimization profile fields are not exact"],
        )


if __name__ == "__main__":
    unittest.main()
