"""Potator shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import potator
from core_pipeline_lib.contracts.registry import core_log_contract_for
from core_pipeline_lib.foundation import sha256_file
from tests.core_contract_helpers import build_c_only_log_fixture


ROOT = Path(__file__).resolve().parents[1]


def hardened_catalog_spec() -> dict:
    catalog = json.loads(
        (ROOT / "manifests/core-builds.json").read_text(encoding="utf-8")
    )
    spec = copy.deepcopy(catalog["cores"][potator.POTATOR_CORE_ID])
    spec["build"]["git_version"] = {
        "derivation": potator.POTATOR_NATIVE_GIT_VERSION_DERIVATION,
        "value": potator.POTATOR_NATIVE_GIT_VERSION,
        "compiler_scope": "c",
    }
    return spec


class PotatorContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_potator(self) -> None:
        contract = core_log_contract_for(potator.POTATOR_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("potator-c-only-v1", contract.contract_id)
        self.assertEqual("potator_log_proves_contract", contract.proof_name)
        self.assertEqual(
            frozenset({potator.POTATOR_CORE_ID}), contract.core_ids
        )

    def test_exact_catalog_and_schema_identity_is_core_owned(self) -> None:
        spec = hardened_catalog_spec()
        identity = potator.POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertTrue(potator.potator_spec_is_well_formed(spec))
        self.assertEqual("platform/libretro/Makefile", identity["native_makefile"])
        self.assertEqual("c", identity["compiler_scope"])
        self.assertEqual(
            {
                "derivation": "native-space-short7-v1",
                "value": " 227c5f6",
                "compiler_scope": "c",
            },
            spec["build"]["git_version"],
        )
        self.assertNotIn("submodules", spec["source"])
        self.assertNotIn("compile_definitions", spec["build"])
        self.assertNotIn("make_variables", spec["build"])
        self.assertNotIn("source_date_epoch", spec["build"])
        schema = json.loads(
            (ROOT / "manifests/core-builds.schema.json").read_text(
                encoding="utf-8"
            )
        )

    def test_catalog_predicate_rejects_every_owned_boundary(self) -> None:
        spec = hardened_catalog_spec()

        def changed(path: tuple[str, ...], value: object) -> dict:
            result = copy.deepcopy(spec)
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return result

        mutations = {
            "workflow": changed(("workflow",), ".github/workflows/build.yml"),
            "source-url": changed(
                ("source", "url"), "https://example.com/potator.git"
            ),
            "source-ref": changed(
                ("source", "requested_ref"), "refs/heads/main"
            ),
            "source-commit": changed(("source", "commit"), "0" * 40),
            "source-tree": changed(("source", "tree"), "0" * 40),
            "driver": changed(("build", "driver"), "direct-make"),
            "source-key": changed(("build", "source_key"), "other"),
            "source-dir": changed(("build", "source_dir"), "other"),
            "output": changed(("build", "output_path"), "other.so"),
            "artifact": changed(("build", "artifact_name"), "other.so"),
            "version-derivation": changed(
                ("build", "git_version", "derivation"),
                "hyphen-short7-v1",
            ),
            "version-value": changed(
                ("build", "git_version", "value"), " 0000000"
            ),
            "version-scope": changed(
                ("build", "git_version", "compiler_scope"), "cxx"
            ),
            "metadata-source": changed(
                ("metadata", "source_path"), "/tmp/other.info"
            ),
            "metadata-artifact": changed(
                ("metadata", "artifact_name"), "other.info"
            ),
            "targets": changed(("targets",), ["arm64"]),
        }
        for path in (
            ("source", "tree"),
            ("build", "source_dir"),
            ("build", "git_version"),
            ("metadata", "artifact_name"),
        ):
            missing = copy.deepcopy(spec)
            target = missing
            for key in path[:-1]:
                target = target[key]
            target.pop(path[-1])
            mutations["missing-" + "-".join(path)] = missing
        extra = copy.deepcopy(spec)
        extra["unexpected"] = True
        mutations["extra-top-level"] = extra
        extra_build = copy.deepcopy(spec)
        extra_build["build"]["make_variables"] = {"SYNTHETIC": 1}
        mutations["extra-build"] = extra_build

        for label, mutation in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(potator.potator_spec_is_well_formed(mutation))
        for malformed in (None, [], "potator", {}, {"workflow": "x"}):
            with self.subTest(malformed=malformed):
                self.assertFalse(potator.potator_spec_is_well_formed(malformed))

    def test_source_lock_is_exact_and_catalog_bound(self) -> None:
        identity = potator.POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY
        source_lock_path = (
            ROOT
            / "pins/sources/potator"
            / f"{identity['source_commit']}.json"
        )
        self.assertEqual(
            "8044bbf6398ccefa73b2dc1c2b123b4e67c52ca185cb45b4641314cfdd949bd8",
            sha256_file(source_lock_path),
        )
        source_lock = json.loads(source_lock_path.read_text(encoding="utf-8"))
        self.assertEqual("potator-227c5f6f3ce7", source_lock["source_lock_id"])
        self.assertEqual(
            "5fcaf01f34d511e0d37d086b8962d4a689ffad1be725f895a66c9137c5bb5086",
            source_lock["content_sha256"],
        )
        self.assertEqual([], source_lock["source"]["submodules"])
        for key in ("url", "requested_ref", "commit", "tree"):
            identity_key = "source_" + key if key != "url" else "source_url"
            self.assertEqual(identity[identity_key], source_lock["source"][key])

    def test_exact_potator_log_dispatches_through_individual_proof(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                fixture = build_c_only_log_fixture(
                    pipeline, ROOT, potator.POTATOR_CORE_ID, architecture
                )
                spec = fixture["spec"]
                arguments = (
                    fixture["log"],
                    potator.POTATOR_CORE_ID,
                    architecture,
                    spec["source"]["commit"],
                    spec["source"]["tree"],
                )
                with mock.patch.object(
                    potator,
                    "POTATOR_EXPECTED_COMPILE_PAIR_SHA256",
                    fixture["compile_pair_sha256"],
                ), mock.patch.dict(
                    potator.POTATOR_EXPECTED_COMPILE_INVOCATION_SHA256,
                    {architecture: fixture["compile_invocation_sha256"]},
                ), mock.patch.object(
                    potator,
                    "POTATOR_EXPECTED_LINK_OBJECT_SHA256",
                    fixture["link_object_sha256"],
                ), mock.patch.object(
                    potator,
                    "POTATOR_EXPECTED_RAW_LINK_OBJECT_SHA256",
                    fixture["raw_link_object_sha256"],
                ):
                    self.assertTrue(
                        potator.potator_log_proves_contract(*arguments)
                    )
                    self.assertTrue(
                        pipeline.registered_core_log_contract_proves(*arguments)
                    )
                    self.assertFalse(
                        potator.potator_log_proves_contract(
                            fixture["log"],
                            "stella2014",
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )
                    self.assertFalse(
                        potator.potator_log_proves_contract(
                            fixture["log"] + "fatal: synthetic failure\n",
                            potator.POTATOR_CORE_ID,
                            architecture,
                            spec["source"]["commit"],
                            spec["source"]["tree"],
                        )
                    )


if __name__ == "__main__":
    unittest.main()
