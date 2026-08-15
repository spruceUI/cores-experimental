#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from scripts.core_pipeline_lib import source_candidate


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "core_pipeline_prebuild_freeze",
    ROOT / "scripts" / "core_pipeline.py",
)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _source_candidate(core_id: str = "swanstation") -> dict:
    commit = "1" * 40
    tree = "2" * 40
    requested_ref = "refs/heads/master"
    frozen_ref = "refs/spruce-edge-refs/" + hashlib.sha256(
        requested_ref.encode() + b"\0" + commit.encode()
    ).hexdigest()
    material = {
        "schema_version": 1,
        "validation_scope": "immutable-edge-source-candidate-catalog-v1",
        "local_only": True,
        "publication": "disabled",
        "core_id": core_id,
        "generator": {
            "path": "scripts/core_pipeline_lib/source_candidate.py",
            "sha256": "3" * 64,
        },
        "snapshot": {
            "path": ".local-e2e/source-probes/unit/snapshot.json",
            "file_sha256": "4" * 64,
            "content_sha256": "5" * 64,
            "snapshot_id": "unit-snapshot",
            "captured_at": "2026-08-10T00:00:00Z",
            "catalog": {
                "path": "manifests/core-builds.json",
                "file_sha256": "6" * 64,
            },
        },
        "base_catalog": {
            "path": "manifests/core-builds.json",
            "file_sha256": "7" * 64,
            "core_spec_sha256": "8" * 64,
        },
        "mirror": {
            "path": f".local-e2e/source-repositories/{core_id}.git",
            "origin_url": "https://example.invalid/swanstation.git",
            "frozen_local_ref": frozen_ref,
        },
        "selection": {
            "url": "https://example.invalid/swanstation.git",
            "requested_ref": requested_ref,
            "catalog_commit": "a" * 40,
            "catalog_tree": "b" * 40,
            "commit": commit,
            "tree": tree,
            "commit_epoch": 1780000000,
            "frozen_local_ref": frozen_ref,
            "ref_kind": "branch",
            "ref_object": commit,
            "ref_object_type": "commit",
            "latest_semantics": "exact-branch-tip",
            "catalog_is_ancestor": True,
            "status": "fast-forward",
            "top_level_gitlinks": [],
            "recipe_risk": {
                "catalog_declared_submodules": 0,
                "driver": "libretro-super",
                "git_version": False,
                "overlays": 0,
                "recursive_submodules": True,
                "source_aware_log_contract": False,
                "source_date_epoch": True,
                "submodule_fetch": True,
            },
        },
        "execution": {
            "core_spec_sha256": "c" * 64,
            "source_date_epoch_derivation": "candidate-commit-epoch",
        },
    }
    return {
        **material,
        "candidate_id": pipeline.sha256_bytes(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        ),
    }


def _hardened_host_runner(*, selected: bool) -> dict:
    registry_sha = "1" * 64
    schema_sha = "2" * 64
    telemetry_sha = ("3" if selected else "4") * 64
    return {
        "schema_version": 2,
        "profile": "github-actions" if selected else "local",
        "mode": "simulated" if selected else "native",
        "backend": "local-docker",
        "local_only": True,
        "publication": "disabled",
        "execution_profile": {
            "path": (
                ".local-e2e/store/host-execution-profiles/sha256/11/"
                + registry_sha
            ),
            "file_sha256": registry_sha,
            "content_sha256": "5" * 64,
            "schema": {
                "path": ".local-e2e/store/schemas/sha256/22/" + schema_sha,
                "file_sha256": schema_sha,
            },
            "profile_id": "host-selected-v1" if selected else "host-local-v1",
            "profile_content_sha256": ("6" if selected else "7") * 64,
            "resource_class_id": "host-equivalent-v1",
            "resource_class_content_sha256": "8" * 64,
            "execution_label": "selected" if selected else "reproduction",
        },
        "telemetry": {
            "path": (
                ".local-e2e/store/host-build-telemetry/sha256/"
                + telemetry_sha[:2]
                + "/"
                + telemetry_sha
            ),
            "file_sha256": telemetry_sha,
            "content_sha256": ("9" if selected else "a") * 64,
        },
    }


class AssemblyTuningFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)

    def test_only_nonempty_direct_cmake_tuning_exports_asmflags(self) -> None:
        swanstation = self.catalog["cores"]["swanstation"]
        tuned = pipeline.container_build_script(
            "swanstation",
            "arm64",
            swanstation,
            self.catalog["resolver"],
            "a523-cortex-a55-v1",
        )
        self.assertIn("ASMFLAGS ASFLAGS", tuned)
        self.assertIn("export ASMFLAGS=-mcpu=cortex-a55", tuned)
        self.assertNotIn("export ASFLAGS=", tuned)
        self.assertLess(
            tuned.index("unset CFLAGS"),
            tuned.index("export ASMFLAGS=-mcpu=cortex-a55"),
        )

        with_definitions = copy.deepcopy(swanstation)
        with_definitions["build"]["compile_definitions"] = {
            "arm64": ["CATALOG_DEFINITION=1"]
        }
        assembly_export = pipeline.direct_cmake_assembly_tuning_shell(
            with_definitions,
            "arm64",
            "a523-cortex-a55-v1",
        )
        self.assertEqual("export ASMFLAGS=-mcpu=cortex-a55", assembly_export)
        self.assertNotIn("CATALOG_DEFINITION", assembly_export)

        universal = pipeline.container_build_script(
            "swanstation",
            "arm64",
            swanstation,
            self.catalog["resolver"],
            "universal-v1",
        )
        self.assertNotIn("export ASMFLAGS=", universal)
        self.assertNotIn("export ASFLAGS=", universal)

        other_driver = pipeline.container_build_script(
            "2048",
            "arm64",
            self.catalog["cores"]["2048"],
            self.catalog["resolver"],
            "a523-cortex-a55-v1",
        )
        self.assertIn("ASMFLAGS ASFLAGS", other_driver)
        self.assertNotIn("export ASMFLAGS=", other_driver)
        self.assertNotIn("export ASFLAGS=", other_driver)

    def test_assembly_proof_is_target_bound_and_ignores_host_tools(self) -> None:
        tuning = pipeline.execution_tuning_profile(
            "a523-cortex-a55-v1", "arm64"
        )
        assert tuning is not None
        marker = __import__("shlex").split(
            pipeline.chipset_tuning_marker_shell(tuning)
        )[-1]
        compiler = sorted(
            pipeline.TARGET_COMPILERS["arm64"]
            - pipeline.TARGET_CXX_COMPILERS["arm64"]
        )[0]
        valid = (
            f"{marker}\n"
            "gcc -O2 -c host_tool.S -o host_tool.o\n"
            f"{compiler} -mcpu=cortex-a55 -c target.S -o target.o\n"
        )
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(valid, tuning, "arm64")
        )
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                valid.replace("-mcpu=cortex-a55 -c target.S", "-c target.S"),
                tuning,
                "arm64",
            )
        )
        host_decoy = valid.replace(
            "gcc -O2", "gcc -mcpu=cortex-a55 -O2"
        ).replace("-mcpu=cortex-a55 -c target.S", "-c target.S")
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                host_decoy,
                tuning,
                "arm64",
            )
        )


class SourceCandidatePromotionFreezeTests(unittest.TestCase):
    def test_record_projection_rejects_malformed_nested_provenance(self) -> None:
        def source_aware_candidate() -> dict:
            candidate = _source_candidate("reminiscence")
            candidate["selection"]["recipe_risk"][
                "source_aware_log_contract"
            ] = True
            retained_ref = "refs/spruce-edge-refs/" + hashlib.sha256(
                (
                    candidate["selection"]["requested_ref"]
                    + "\0"
                    + candidate["selection"]["commit"]
                ).encode()
            ).hexdigest()
            candidate["selection"]["frozen_local_ref"] = retained_ref
            candidate["mirror"]["frozen_local_ref"] = retained_ref
            material = copy.deepcopy(candidate)
            material.pop("candidate_id")
            candidate["candidate_id"] = pipeline.sha256_bytes(
                json.dumps(
                    material,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            return candidate

        with mock.patch.object(
            pipeline,
            "source_aware_candidate_contract_is_registered",
            return_value=True,
        ):
            malformed_generator = source_aware_candidate()
            malformed_generator["generator"]["path"] = ["not", "hashable"]
            material = copy.deepcopy(malformed_generator)
            material.pop("candidate_id")
            malformed_generator["candidate_id"] = pipeline.sha256_bytes(
                json.dumps(
                    material,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            with self.subTest("generator path"), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.source_candidate_record_contract_projection(
                    malformed_generator,
                    core_id="reminiscence",
                    recorded_source={},
                    recorded_recipe={},
                    recipe_snapshot={},
                )

            candidate = source_aware_candidate()
            recipe = {
                "catalog_path": "candidate.json",
                "catalog_sha256": "0" * 64,
                "pipeline_bundle": [],
            }
            with self.subTest("pipeline bundle"), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.source_candidate_record_contract_projection(
                    candidate,
                    core_id="reminiscence",
                    recorded_source={},
                    recorded_recipe=recipe,
                    recipe_snapshot={"recipe": recipe, "files": {}},
                )

    def test_authenticated_catalog_loader_binds_validator_to_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical = root / "manifests" / "core-builds.json"
            candidate_path = root / ".local-e2e" / "source-candidates" / "core-builds.json"
            candidate_path.parent.mkdir(parents=True)
            canonical.parent.mkdir(parents=True)
            canonical.write_bytes(_json_bytes({"cores": {}}))
            document = {
                "cores": {"swanstation": {}},
                "source_candidate": _source_candidate(),
            }
            candidate_path.write_bytes(_json_bytes(document))
            digest = pipeline.sha256_file(candidate_path)
            report = {
                "status": "valid",
                "catalog": {"file_sha256": digest},
            }
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_CATALOG", canonical),
                mock.patch.object(pipeline, "validate_catalog"),
                mock.patch.object(
                    pipeline,
                    "validate_source_candidate_catalog",
                    return_value=report,
                ) as provenance_validator,
            ):
                loaded, loaded_digest = pipeline.load_catalog_with_sha256(
                    candidate_path
                )
            self.assertEqual(document, loaded)
            self.assertEqual(digest, loaded_digest)
            provenance_validator.assert_called_once()

            candidate_path.write_bytes(_json_bytes(document))

            def mutate_after_validation(**_kwargs) -> dict:
                changed = copy.deepcopy(document)
                changed["unexpected"] = True
                candidate_path.write_bytes(_json_bytes(changed))
                return report

            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_CATALOG", canonical),
                mock.patch.object(pipeline, "validate_catalog"),
                mock.patch.object(
                    pipeline,
                    "validate_source_candidate_catalog",
                    side_effect=mutate_after_validation,
                ),
                self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "changed during authenticated load",
                ),
            ):
                pipeline.load_catalog_with_sha256(candidate_path)

    def test_source_candidate_e2e_rejects_group_and_tuned_fields(self) -> None:
        candidate = _source_candidate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            catalog_path = root / ".local-e2e" / "source-candidates" / "core-builds.json"
            catalog_path.parent.mkdir(parents=True)
            catalog = {
                "cores": {"swanstation": {}},
                "source_candidate": candidate,
            }
            catalog_path.write_bytes(_json_bytes(catalog))
            catalog_digest = pipeline.sha256_file(catalog_path)
            base_e2e = {
                "schema_version": 2,
                "run_id": "candidate",
                "local_only": True,
                "publication": "disabled",
                "runner": {},
                "result": "passed",
                "workflow_audit": {},
                "builds": [],
                "packages": [],
                "content_sha256": "1" * 64,
            }
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(
                    pipeline,
                    "load_catalog_with_sha256",
                    return_value=(catalog, catalog_digest),
                ),
            ):
                for forbidden in ("core_group", "tuning_candidate"):
                    with self.subTest(forbidden=forbidden):
                        e2e_path = runs / forbidden / "e2e-record.json"
                        e2e_path.parent.mkdir(parents=True)
                        e2e_path.write_bytes(
                            _json_bytes({**base_e2e, forbidden: {}})
                        )
                        with self.assertRaisesRegex(
                            pipeline.PipelineError,
                            "fields are not exact",
                        ):
                            pipeline.validate_source_candidate_e2e_evidence(
                                e2e_path,
                                catalog_path,
                                catalog,
                                expected_core="swanstation",
                                catalog_file_sha256=catalog_digest,
                            )

            e2e_path = runs / "forged" / "e2e-record.json"
            e2e_path.parent.mkdir(parents=True)
            e2e_path.write_bytes(_json_bytes(base_e2e))
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(
                    pipeline,
                    "load_catalog_with_sha256",
                    side_effect=pipeline.PipelineError(
                        "authenticated candidate provenance is invalid"
                    ),
                ) as deep_load,
                self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "authenticated candidate provenance is invalid",
                ),
            ):
                pipeline.validate_source_candidate_e2e_evidence(
                    e2e_path,
                    catalog_path,
                    catalog,
                    expected_core="swanstation",
                    catalog_file_sha256=catalog_digest,
                )
            deep_load.assert_called_once_with(catalog_path)

    def test_generic_promotion_refuses_plain_alternate_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            nightlies = root / ".local-e2e" / "nightlies"
            store = root / ".local-e2e" / "store"
            pins = root / "pins" / "core-sets"
            catalog_path = root / ".local-e2e" / "alternate.json"
            plain_catalog = {"cores": {"swanstation": {}}}
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_STORE", store),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                mock.patch.object(
                    pipeline,
                    "load_catalog_with_sha256",
                    return_value=(plain_catalog, "1" * 64),
                ),
                self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "authenticated generated catalog",
                ),
            ):
                pipeline.promote_source_candidate(
                    core_id="swanstation",
                    source_golden_path=(
                        nightlies
                        / "swanstation-candidate-plain"
                        / "golden.json"
                    ),
                    selected_e2e_path=runs / "selected" / "e2e-record.json",
                    reproduction_e2e_path=(
                        runs / "reproduction" / "e2e-record.json"
                    ),
                    catalog_path=catalog_path,
                    store_root=store,
                )

    def test_source_candidate_catalog_cannot_bypass_dual_admission(self) -> None:
        candidate_catalog = {
            "cores": {"swanstation": {}},
            "source_candidate": _source_candidate(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            nightlies = root / ".local-e2e" / "nightlies"
            store = root / ".local-e2e" / "store"
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_STORE", store),
                mock.patch.object(
                    pipeline, "load_catalog", return_value=candidate_catalog
                ),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "legacy promotion rejects source-candidate catalogs",
                ):
                    pipeline.promote_build_record(
                        nightlies
                        / "swanstation-candidate-bypass"
                        / "golden.json",
                        runs / "selected" / "build-record.json",
                        runs / "selected" / "e2e-record.json",
                        root / ".local-e2e" / "source-candidates" / "core-builds.json",
                        store,
                    )
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "tuned promotion rejects source-candidate catalogs",
                ):
                    pipeline.promote_tuned_variant(
                        core_id="swanstation",
                        profile_id="a523-cortex-a55-v1",
                        source_golden_path=(
                            nightlies
                            / "swanstation-candidate-bypass"
                            / "golden.json"
                        ),
                        selected_e2e_path=(
                            runs / "selected" / "e2e-record.json"
                        ),
                        reproduction_e2e_path=(
                            runs / "reproduction" / "e2e-record.json"
                        ),
                        catalog_path=(
                            root
                            / ".local-e2e"
                            / "source-candidates"
                            / "core-builds.json"
                        ),
                        store_root=store,
                    )

    def test_changed_source_custom_catalog_cannot_use_ordinary_promotion(
        self,
    ) -> None:
        custom_catalog = copy.deepcopy(
            pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        )
        custom_catalog["cores"]["reminiscence"]["source"]["commit"] = "1" * 40
        custom_catalog["cores"]["reminiscence"]["source"]["tree"] = "2" * 40
        custom_catalog["source_candidate"] = _source_candidate()
        stripped_candidate_catalog = copy.deepcopy(custom_catalog)
        stripped_candidate_catalog.pop("source_candidate")
        self.assertNotIn("source_candidate", stripped_candidate_catalog)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            nightlies = root / ".local-e2e" / "nightlies"
            store = root / ".local-e2e" / "store"
            custom_path = root / ".local-e2e" / "custom-core-builds.json"
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_STORE", store),
                mock.patch.object(
                    pipeline,
                    "load_catalog",
                    return_value=stripped_candidate_catalog,
                ),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "legacy promotion requires the exact canonical catalog path",
                ):
                    pipeline.promote_build_record(
                        nightlies / "reminiscence-candidate-bypass" / "golden.json",
                        runs / "selected" / "build-record.json",
                        runs / "selected" / "e2e-record.json",
                        custom_path,
                        store,
                    )
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "tuned promotion requires the exact canonical catalog path",
                ):
                    pipeline.promote_tuned_variant(
                        core_id="reminiscence",
                        profile_id="a523-cortex-a55-v1",
                        source_golden_path=(
                            nightlies / "reminiscence-candidate-bypass" / "golden.json"
                        ),
                        selected_e2e_path=runs / "selected" / "e2e-record.json",
                        reproduction_e2e_path=(
                            runs / "reproduction" / "e2e-record.json"
                        ),
                        catalog_path=custom_path,
                        store_root=store,
                    )

    def test_stripped_candidate_selection_cannot_launder_candidate_source(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        candidate_source = {
            "commit": "212f3466c9f276ff7cade5a5ead78d3a151343ac",
            "requested_ref": "refs/heads/master",
            "resolved_commit": "212f3466c9f276ff7cade5a5ead78d3a151343ac",
            "resolved_url": "https://github.com/EasyRPG/Player.git",
            "submodules": [
                {
                    "commit": "20a43ba79fe6b4ec094b3b20b7bc88f4cfe916fa",
                    "path": "builds/libretro/libretro-common",
                    "state": " ",
                }
            ],
            "tree": "31f05c2712348b7fdd3dee70dab39a6ac61801ae",
            "url": "https://github.com/EasyRPG/Player.git",
        }
        selection = {
            "source_candidate": _source_candidate(),
            "output_reproduction": {},
            "targets": {
                "arm64": {
                    "golden_record": {
                        "source": candidate_source,
                    }
                }
            },
        }
        selection.pop("source_candidate")
        selection.pop("output_reproduction")
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "ordinary selection source differs from the canonical core",
        ):
            pipeline._require_catalog_bound_source_candidate_selection(
                catalog,
                selection,
                core_id="easyrpg",
                operation="stripped candidate",
                catalog_path=pipeline.DEFAULT_CATALOG,
            )

        forged_catalog = copy.deepcopy(catalog)
        forged_catalog["cores"]["easyrpg"]["source"] = {
            key: copy.deepcopy(candidate_source[key])
            for key in ("url", "requested_ref", "commit", "tree")
        }
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "catalog differs from the canonical bytes",
        ):
            pipeline._require_catalog_bound_source_candidate_selection(
                forged_catalog,
                selection,
                core_id="easyrpg",
                operation="forged catalog",
                catalog_path=pipeline.DEFAULT_CATALOG,
            )

    def test_stripped_candidate_rejects_release_and_every_channel_path(
        self,
    ) -> None:
        candidate_source = {
            "commit": "212f3466c9f276ff7cade5a5ead78d3a151343ac",
            "requested_ref": "refs/heads/master",
            "resolved_commit": "212f3466c9f276ff7cade5a5ead78d3a151343ac",
            "resolved_url": "https://github.com/EasyRPG/Player.git",
            "submodules": [
                {
                    "commit": "20a43ba79fe6b4ec094b3b20b7bc88f4cfe916fa",
                    "path": "builds/libretro/libretro-common",
                    "state": " ",
                }
            ],
            "tree": "31f05c2712348b7fdd3dee70dab39a6ac61801ae",
            "url": "https://github.com/EasyRPG/Player.git",
        }
        stripped_selection = {
            "targets": {
                "arm64": {"golden_record": {"source": candidate_source}}
            }
        }
        pin_id = "easyrpg-stripped-v1"
        stripped_pin = {
            "pin_id": pin_id,
            "content_sha256": "1" * 64,
            "scope": ["easyrpg"],
            "cores": {
                "easyrpg": {"selection": stripped_selection}
            },
        }

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            canonical_document = pipeline.load_catalog(
                pipeline.DEFAULT_CATALOG
            )
            canonical_catalog = root / "manifests" / "core-builds.json"
            canonical_catalog.parent.mkdir(parents=True)
            canonical_catalog.write_bytes(pipeline.DEFAULT_CATALOG.read_bytes())
            nightlies = root / ".local-e2e" / "nightlies"
            pins = root / "pins" / "core-sets"
            releases = root / ".local-e2e" / "releases"
            channels = root / ".local-e2e" / "channels"
            pin_path = pins / f"{pin_id}.json"
            pin_path.parent.mkdir(parents=True)
            pin_path.write_bytes(_json_bytes(stripped_pin))

            release_root = releases / pin_id
            release_root.mkdir(parents=True)
            release_manifest_path = release_root / "release-manifest.json"
            release_manifest_path.write_bytes(
                _json_bytes(
                    {
                        "release_id": pin_id,
                        "content_sha256": "2" * 64,
                        "pin": {"file_sha256": pipeline.sha256_file(pin_path)},
                    }
                )
            )

            nightly_path = nightlies / pin_id / "golden.json"
            nightly_path.parent.mkdir(parents=True)
            nightly_path.write_bytes(
                _json_bytes(
                    {
                        "content_sha256": "3" * 64,
                        "build_goldens": {"easyrpg": {}},
                    }
                )
            )

            common = (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                mock.patch.object(pipeline, "DEFAULT_RELEASES", releases),
                mock.patch.object(pipeline, "DEFAULT_CHANNELS", channels),
                mock.patch.object(
                    pipeline, "DEFAULT_CATALOG", canonical_catalog
                ),
                mock.patch.object(
                    pipeline,
                    "load_catalog",
                    return_value=canonical_document,
                ),
            )
            with (
                common[0],
                common[1],
                common[2],
                common[3],
                common[4],
                common[5],
                common[6],
            ):
                with (
                    mock.patch.object(
                        pipeline,
                        "validate_pin_set_document",
                        return_value={"status": "valid", "errors": []},
                    ),
                    mock.patch.object(
                        pipeline,
                        "require_individual_pin_identity",
                        return_value=("easyrpg", pin_id),
                    ),
                    mock.patch.object(
                        pipeline,
                        "_require_public_ordinary_catalog",
                        return_value=pipeline.sha256_file(canonical_catalog),
                    ),
                    self.assertRaisesRegex(
                        pipeline.PipelineError,
                        "ordinary selection source differs from the canonical core",
                    ),
                ):
                    pipeline.promote_local_release(
                        pin_path,
                        release_root,
                        catalog_path=canonical_catalog,
                    )

                with (
                    mock.patch.object(
                        pipeline,
                        "_resolve_release_pin",
                        return_value=(stripped_pin, pin_path),
                    ),
                    mock.patch.object(
                        pipeline,
                        "_validate_pin_set_document",
                        return_value={"status": "valid", "errors": []},
                    ),
                ):
                    validation = pipeline.validate_local_release(
                        release_root,
                        stripped_pin,
                        pipeline.sha256_file(pin_path),
                    )
                self.assertEqual("invalid", validation["status"])
                self.assertTrue(
                    any(
                        "ordinary selection source differs from the canonical core"
                        in error
                        for error in validation["errors"]
                    ),
                    validation,
                )

                channel_cases = (
                    ("nightly", nightly_path),
                    ("pinned", pin_path),
                    ("release", release_manifest_path),
                )
                for channel, target_path in channel_cases:
                    patches = []
                    if channel == "nightly":
                        patches.extend(
                            (
                                mock.patch.object(
                                    pipeline,
                                    "validate_golden_document",
                                    return_value={
                                        "status": "valid",
                                        "errors": [],
                                    },
                                ),
                                mock.patch.object(
                                    pipeline,
                                    "_verify_local_store",
                                    return_value=[],
                                ),
                                mock.patch.object(
                                    pipeline,
                                    "complete_core_bundle",
                                    return_value=stripped_selection,
                                ),
                            )
                        )
                    elif channel == "pinned":
                        patches.append(
                            mock.patch.object(
                                pipeline,
                                "_validate_pin_set_document",
                                return_value={"status": "valid", "errors": []},
                            )
                        )
                    else:
                        patches.extend(
                            (
                                mock.patch.object(
                                    pipeline,
                                    "_resolve_release_pin",
                                    return_value=(stripped_pin, pin_path),
                                ),
                                mock.patch.object(
                                    pipeline,
                                    "_validate_pin_set_document",
                                    return_value={"status": "valid", "errors": []},
                                ),
                                mock.patch.object(
                                    pipeline,
                                    "_validate_local_release",
                                    return_value={"status": "valid", "errors": []},
                                ),
                            )
                        )
                    with self.subTest(channel=channel):
                        with patches[0]:
                            if len(patches) == 1:
                                remaining = ()
                            else:
                                remaining = patches[1:]
                            if remaining:
                                with remaining[0]:
                                    if len(remaining) == 1:
                                        tail = ()
                                    else:
                                        tail = remaining[1:]
                                    if tail:
                                        with tail[0]:
                                            with self.assertRaisesRegex(
                                                pipeline.PipelineError,
                                                "ordinary selection source differs "
                                                "from the canonical core",
                                            ):
                                                pipeline._derive_channel_target(
                                                    channel,
                                                    target_path,
                                                    core_id="easyrpg",
                                                )
                                    else:
                                        with self.assertRaisesRegex(
                                            pipeline.PipelineError,
                                            "ordinary selection source differs "
                                            "from the canonical core",
                                        ):
                                            pipeline._derive_channel_target(
                                                channel,
                                                target_path,
                                                core_id="easyrpg",
                                            )
                            else:
                                with self.assertRaisesRegex(
                                    pipeline.PipelineError,
                                    "ordinary selection source differs "
                                    "from the canonical core",
                                ):
                                    pipeline._derive_channel_target(
                                        channel,
                                        target_path,
                                        core_id="easyrpg",
                                    )

    def test_candidate_pin_composition_cannot_strip_dual_e2e_proof(self) -> None:
        core_id = "swanstation"
        candidate_catalog = {
            "cores": {core_id: {}},
            "source_candidate": _source_candidate(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nightlies = root / ".local-e2e" / "nightlies"
            pins = root / "pins" / "core-sets"
            source_path = (
                nightlies
                / "swanstation-candidate-ordinary"
                / "golden.json"
            )
            source_path.parent.mkdir(parents=True)
            source_path.write_bytes(
                _json_bytes(
                    {
                        "schema_version": 2,
                        "core_id": core_id,
                        "pin_id": "swanstation-candidate-ordinary",
                        "cores": {core_id: {}},
                        "build_goldens": {core_id: {"arm64": {}}},
                    }
                )
            )
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                mock.patch.object(
                    pipeline, "load_catalog", return_value=candidate_catalog
                ),
                mock.patch.object(
                    pipeline,
                    "validate_golden_document",
                    return_value={"status": "valid", "errors": []},
                ),
                mock.patch.object(pipeline, "_verify_local_store", return_value=[]),
                mock.patch.object(
                    pipeline,
                    "complete_core_bundle",
                    return_value={"tier": "build_golden"},
                ),
                self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "requires source-candidate provenance in both",
                ),
            ):
                pipeline.compose_pin_set(
                    pin_id="swanstation-ordinary",
                    core_ids=[core_id],
                    source_paths=[source_path],
                    output_path=pins / "swanstation-ordinary.json",
                    catalog_path=root / ".local-e2e" / "candidate.json",
                )
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(
                    pipeline, "load_catalog", return_value=candidate_catalog
                ),
                mock.patch.object(
                    pipeline,
                    "validate_golden_document",
                    return_value={"status": "valid", "errors": []},
                ),
                mock.patch.object(pipeline, "verify_local_store", return_value=[]),
                mock.patch.object(
                    pipeline,
                    "complete_core_bundle",
                    return_value={"tier": "build_golden"},
                ),
                self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "requires source-candidate provenance in both",
                ),
            ):
                pipeline.inspect_individual_core_golden(
                    core_id,
                    source_path,
                    root / ".local-e2e" / "candidate.json",
                )
            candidate_selection = {
                "tier": "build_golden",
                "source_candidate": candidate_catalog["source_candidate"],
                "output_reproduction": {},
            }
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                mock.patch.object(
                    pipeline,
                    "load_catalog",
                    return_value={"cores": {core_id: {}}},
                ),
                mock.patch.object(
                    pipeline,
                    "validate_golden_document",
                    return_value={"status": "valid", "errors": []},
                ),
                mock.patch.object(pipeline, "_verify_local_store", return_value=[]),
                mock.patch.object(
                    pipeline,
                    "complete_core_bundle",
                    return_value=candidate_selection,
                ),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "requires source-candidate provenance in both",
                ):
                    pipeline.compose_pin_set(
                        pin_id="swanstation-ordinary",
                        core_ids=[core_id],
                        source_paths=[source_path],
                        output_path=pins / "swanstation-ordinary.json",
                        catalog_path=root / "manifests" / "core-builds.json",
                    )
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "requires source-candidate provenance in both",
                ):
                    pipeline.inspect_individual_core_golden(
                        core_id,
                        source_path,
                        root / "manifests" / "core-builds.json",
                    )

    def test_immutable_promotion_paths_reject_output_symlinks(self) -> None:
        semantic_id = "swanstation-symlink-guard"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nightlies = root / ".local-e2e" / "nightlies"
            pins = root / "pins" / "core-sets"
            outside = root.parent / f"{root.name}-outside"
            nightlies.mkdir(parents=True)
            pins.mkdir(parents=True)
            outside.mkdir()
            semantic_directory = nightlies / semantic_id
            semantic_directory.symlink_to(outside, target_is_directory=True)
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
            ):
                for label in ("source-candidate", "tuned"):
                    with self.subTest(label=label), self.assertRaisesRegex(
                        pipeline.PipelineError,
                        "must not traverse a symlink",
                    ):
                        pipeline.immutable_promotion_output_paths(
                            semantic_id,
                            label=label,
                        )
            self.assertFalse((outside / "golden.json").exists())

            semantic_directory.unlink()
            pin_link = pins / f"{semantic_id}.json"
            pin_link.symlink_to(outside / "pin.json")
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "must not traverse a symlink",
                ),
            ):
                pipeline.immutable_promotion_output_paths(
                    semantic_id,
                    label="source-candidate",
                )
            self.assertFalse((outside / "pin.json").exists())
            outside.rmdir()

    def test_content_store_rejects_symlinked_evidence_parents(self) -> None:
        content = b"candidate evidence bytes"
        digest = pipeline.sha256_bytes(content)
        for namespace in ("e2e", "logs", "recipes"):
            for symlink_parent in ("namespace", "sha256", "digest-prefix"):
                with self.subTest(
                    namespace=namespace,
                    symlink_parent=symlink_parent,
                ), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    store = root / "store"
                    outside = root / "outside"
                    store.mkdir()
                    outside.mkdir()
                    if symlink_parent == "namespace":
                        (store / namespace).symlink_to(
                            outside, target_is_directory=True
                        )
                    elif symlink_parent == "sha256":
                        (store / namespace).mkdir()
                        (store / namespace / "sha256").symlink_to(
                            outside, target_is_directory=True
                        )
                    else:
                        (store / namespace / "sha256").mkdir(parents=True)
                        (store / namespace / "sha256" / digest[:2]).symlink_to(
                            outside, target_is_directory=True
                        )
                    with self.assertRaisesRegex(
                        pipeline.PipelineError,
                        "must not traverse a symlink",
                    ):
                        pipeline.store_bytes(store, namespace, content)
                    self.assertEqual([], list(outside.iterdir()))

    def test_content_store_create_race_is_create_only(self) -> None:
        content = b"race-safe candidate evidence"
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "store"

            def concurrent_exact(_temporary: Path, destination: Path) -> None:
                destination.write_bytes(content)
                raise FileExistsError

            with mock.patch.object(
                pipeline.os,
                "link",
                side_effect=concurrent_exact,
            ):
                destination, digest = pipeline.store_bytes(
                    store,
                    "e2e",
                    content,
                )
            self.assertEqual(content, destination.read_bytes())
            self.assertEqual(pipeline.sha256_bytes(content), digest)

        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "store"

            def concurrent_collision(_temporary: Path, destination: Path) -> None:
                destination.write_bytes(b"different bytes")
                raise FileExistsError

            with mock.patch.object(
                pipeline.os,
                "link",
                side_effect=concurrent_collision,
            ), self.assertRaisesRegex(
                pipeline.PipelineError,
                "content-addressed store collision",
            ):
                pipeline.store_bytes(store, "e2e", content)

    def test_schema_contracts_are_meta_valid_and_accept_generic_proofs(self) -> None:
        golden_schema = json.loads(
            (ROOT / "manifests" / "golden-start.schema.json").read_text()
        )
        pin_schema = json.loads(
            (ROOT / "manifests" / "core-set.schema.json").read_text()
        )
        Draft202012Validator.check_schema(golden_schema)
        Draft202012Validator.check_schema(pin_schema)

        candidate = _source_candidate()
        stored = {"path": ".local-e2e/store/e2e/sha256/aa/" + "a" * 64, "sha256": "a" * 64}
        side = {
            "run_id": "selected",
            "content_sha256": "b" * 64,
            "e2e_record": stored,
            "build_records": {"arm64": stored},
            "build_logs": {"arm64": stored},
            "recipe_snapshots": {"arm64": stored},
        }
        proof = {
            "schema_version": 1,
            "validation_scope": pipeline.SOURCE_CANDIDATE_REPRODUCTION_SCOPE,
            "selected": side,
            "reproduction": {
                **side,
                "run_id": "reproduction",
                "content_sha256": "c" * 64,
                "e2e_record": {**stored, "sha256": "d" * 64},
                "build_records": {
                    "arm64": {**stored, "sha256": "e" * 64}
                },
            },
            "equivalent_outputs": {
                "artifacts": {"arm64": {"sha256": "f" * 64, "size": 10}},
                "metadata": {"sha256": "1" * 64, "size": 11},
                "package": {
                    "name": "swanstation_libretro.zip",
                    "sha256": "2" * 64,
                    "size": 12,
                },
            },
        }
        defs = golden_schema["$defs"]
        Draft202012Validator(
            {"$schema": golden_schema["$schema"], "$defs": defs, "$ref": "#/$defs/sourceCandidate"}
        ).validate(candidate)
        Draft202012Validator(
            {"$schema": golden_schema["$schema"], "$defs": defs, "$ref": "#/$defs/outputReproduction"}
        ).validate(proof)
        registry = Registry().with_resource(
            golden_schema["$id"], Resource.from_contents(golden_schema)
        ).with_resource(
            pin_schema["$id"], Resource.from_contents(pin_schema)
        )
        selection = {
            "tier": "build_golden",
            "validation_scope": "static-build-only",
            "e2e": {},
            "package": {**stored, "size": 12},
            "metadata": {**stored, "size": 11},
            "source_candidate": candidate,
            "output_reproduction": proof,
            "targets": {"arm64": {}},
            "selection_sha256": "3" * 64,
        }
        Draft202012Validator(
            {
                "$schema": pin_schema["$schema"],
                "$ref": pin_schema["$id"] + "#/$defs/selection",
            },
            registry=registry,
        ).validate(selection)

    def test_dual_untuned_source_candidate_promotion_creates_golden_and_pin(
        self,
    ) -> None:
        core_id = "swanstation"
        candidate = _source_candidate(core_id)
        repository_catalog = copy.deepcopy(
            pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        )
        candidate_spec = copy.deepcopy(repository_catalog["cores"][core_id])
        candidate_spec["source"] = {
            "url": candidate["selection"]["url"],
            "requested_ref": candidate["selection"]["requested_ref"],
            "commit": candidate["selection"]["commit"],
            "tree": candidate["selection"]["tree"],
        }
        candidate_spec["build"]["source_date_epoch"] = candidate[
            "selection"
        ]["commit_epoch"]
        catalog = copy.deepcopy(repository_catalog)
        catalog["cores"] = {core_id: candidate_spec}
        catalog["source_candidate"] = candidate
        source = {
            "url": candidate["selection"]["url"],
            "requested_ref": candidate["selection"]["requested_ref"],
            "commit": candidate["selection"]["commit"],
            "resolved_commit": candidate["selection"]["commit"],
            "tree": candidate["selection"]["tree"],
            "resolved_url": candidate["selection"]["url"],
            "submodules": [],
        }
        artifact_bytes = b"identical edge artifact"
        metadata_bytes = b"identical metadata"
        artifact_sha = pipeline.sha256_bytes(artifact_bytes)
        metadata_sha = pipeline.sha256_bytes(metadata_bytes)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            nightlies = root / ".local-e2e" / "nightlies"
            store = root / ".local-e2e" / "store"
            pins = root / "pins" / "core-sets"
            candidate_catalog_path = (
                root
                / ".local-e2e"
                / "source-candidates"
                / "snapshot"
                / core_id
                / candidate["candidate_id"]
                / "core-builds.json"
            )
            candidate_catalog_path.parent.mkdir(parents=True)
            candidate_catalog_path.write_bytes(_json_bytes(catalog))
            catalog_file_sha256 = pipeline.sha256_file(candidate_catalog_path)
            blacklist_path = root / catalog["commit_blacklist"]["path"]
            blacklist_path.parent.mkdir(parents=True, exist_ok=True)
            blacklist_path.write_bytes(
                (ROOT / catalog["commit_blacklist"]["path"]).read_bytes()
            )
            source_golden_path = (
                nightlies
                / f"{core_id}-candidate-edge-unit"
                / "golden.json"
            )
            source_golden_path.parent.mkdir(parents=True)
            imported_artifact = {
                "path": "Cores/swanstation_libretro.so",
                "status": "valid",
                "size": 1,
                "sha256": "9" * 64,
                "elf": {
                    "class": "ELF64",
                    "data": "little endian",
                    "type": "DYN",
                    "machine": "AArch64",
                    "flags": "0x0",
                },
                "needed": [],
                "version_requirements": [],
                "libretro_symbols": [],
                "errors": [],
            }
            source_golden = pipeline.one_core_golden_document(
                core_id=core_id,
                pin_id=f"{core_id}-candidate-edge-unit",
                created_at="2026-08-10T00:00:00+00:00",
                baseline={
                    "kind": "spruceos-shipped-artifacts",
                    "repository_commit": "a" * 40,
                    "provenance": "artifact-only",
                    "warning": "unit baseline",
                },
                core_record={
                    "workflow": candidate_spec["workflow"],
                    "tier": "imported_baseline",
                    "promotion_eligible": False,
                    "artifacts": {
                        "arm64": imported_artifact,
                        "armhf": {"status": "not_shipped"},
                    },
                },
                build_goldens={},
            )
            source_golden["content_sha256"] = pipeline.golden_content_sha256(
                source_golden
            )
            source_golden_path.write_bytes(_json_bytes(source_golden))

            def build_bundle(run_id: str, diagnostic: str) -> dict:
                run_root = runs / run_id
                target_root = run_root / core_id / "arm64"
                target_root.mkdir(parents=True)
                artifact_path = target_root / "swanstation_libretro.so"
                metadata_path = target_root / "swanstation_libretro.info"
                log_path = target_root / "build.log"
                package_path = run_root / "swanstation_libretro.zip"
                artifact_path.write_bytes(artifact_bytes)
                metadata_path.write_bytes(metadata_bytes)
                image_id = "sha256:" + "c" * 64
                package_manifest = {
                    "schema_version": 1,
                    "local_only": True,
                    "publication": "disabled",
                    "core_id": core_id,
                    "artifacts": {
                        "arm64": {
                            "path": "cores64/swanstation_libretro.so",
                            "sha256": artifact_sha,
                            "source_commit": source["resolved_commit"],
                            "toolchain_image_id": image_id,
                        }
                    },
                    "metadata": {
                        "path": metadata_path.name,
                        "sha256": metadata_sha,
                    },
                }
                with zipfile.ZipFile(package_path, "w") as archive:
                    pipeline.add_zip_entry(
                        archive,
                        "cores64/swanstation_libretro.so",
                        artifact_bytes,
                    )
                    pipeline.add_zip_entry(
                        archive,
                        metadata_path.name,
                        metadata_bytes,
                    )
                    pipeline.add_zip_entry(
                        archive,
                        "manifest.json",
                        _json_bytes(package_manifest),
                    )
                package_bytes = package_path.read_bytes()
                package_sha = pipeline.sha256_bytes(package_bytes)
                log_path.write_text(
                    diagnostic
                    + "aarch64-linux-gnu-gcc -O2 -c source.c -o source.o\n"
                )
                record = {
                    "schema_version": 2,
                    "local_only": True,
                    "publication": "disabled",
                    "started_at": "2026-08-10T00:00:01+00:00",
                    "finished_at": "2026-08-10T00:00:02+00:00",
                    "core_id": core_id,
                    "architecture": "arm64",
                    "result": "passed",
                    "build_exit_code": 0,
                    "source": copy.deepcopy(source),
                    "recipe": {
                        "catalog_path": str(candidate_catalog_path.relative_to(root)),
                        "catalog_sha256": catalog_file_sha256,
                        "host_execution": {
                            "resource_class_id": "host-equivalent-v1",
                            "jobs": 8,
                        },
                    },
                    "toolchain": {
                        "image_id": image_id,
                        "resolved_image_id": image_id,
                        "libretro_super_commit": "d" * 40,
                        "resolver_digests": {
                            "libretro_super_commit": "d" * 40,
                        },
                    },
                    "build": {
                        **pipeline.normalized_build_contract(
                            candidate_spec, "arm64"
                        ),
                        "log": "build.log",
                        "log_sha256": pipeline.sha256_file(log_path),
                    },
                    "artifact": {
                        "path": artifact_path.name,
                        "status": "valid",
                        "sha256": artifact_sha,
                        "size": len(artifact_bytes),
                    },
                    "metadata": {
                        "path": metadata_path.name,
                        "status": "valid",
                        "sha256": metadata_sha,
                        "size": len(metadata_bytes),
                    },
                }
                record_path = target_root / "build-record.json"
                record_path.write_bytes(_json_bytes(record))
                package_record = {
                    "core_id": core_id,
                    "result": "packaged",
                    "path": package_path.name,
                    "sha256": package_sha,
                    "size": len(package_bytes),
                }
                e2e = {
                    "schema_version": 2,
                    "run_id": run_id,
                    "local_only": True,
                    "publication": "disabled",
                    "runner": _hardened_host_runner(
                        selected=run_id == "selected"
                    ),
                    "result": "passed",
                    "workflow_audit": {},
                    "builds": [
                        {
                            "core_id": core_id,
                            "architecture": "arm64",
                            "result": "passed",
                            "record": str(record_path.relative_to(root)),
                            "record_sha256": pipeline.sha256_file(record_path),
                        }
                    ],
                    "packages": [package_record],
                }
                e2e["content_sha256"] = pipeline.e2e_content_sha256(e2e)
                e2e_path = run_root / "e2e-record.json"
                e2e_path.write_bytes(_json_bytes(e2e))
                return {
                    "e2e": e2e,
                    "e2e_path": e2e_path,
                    "e2e_file_sha256": pipeline.sha256_file(e2e_path),
                    "core_id": core_id,
                    "source_candidate": candidate,
                    "targets": {
                        "arm64": {
                            "record": record,
                            "record_path": record_path,
                            "record_sha256": pipeline.sha256_file(record_path),
                            "artifact_path": artifact_path,
                            "metadata_path": metadata_path,
                            "log_path": log_path,
                        }
                    },
                    "package_path": package_path,
                    "package_record": package_record,
                }

            selected = build_bundle("selected", "")
            reproduction = build_bundle(
                "reproduction", "independent diagnostic line\n"
            )

            def validated_bundle(e2e_path: Path, *_args, **_kwargs) -> dict:
                return selected if e2e_path == selected["e2e_path"] else reproduction

            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_STORE", store),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                mock.patch.object(
                    pipeline,
                    "core_workflows",
                    return_value={core_id: root / candidate_spec["workflow"]},
                ),
                mock.patch.object(pipeline, "load_catalog", return_value=catalog),
                mock.patch.object(
                    pipeline,
                    "load_catalog_with_sha256",
                    return_value=(catalog, catalog_file_sha256),
                ),
                mock.patch.object(
                    pipeline,
                    "validate_source_candidate_e2e_evidence",
                    side_effect=validated_bundle,
                ),
                mock.patch.object(pipeline, "recipe_snapshot", return_value=b"{}\n"),
                mock.patch.object(
                    pipeline,
                    "_verify_recipe_snapshot",
                    return_value=[],
                ),
                mock.patch.object(
                    pipeline,
                    "validate_bound_host_telemetry",
                    return_value={},
                ),
                mock.patch.object(
                    pipeline,
                    "_verify_host_reproduction_bundle",
                    return_value=[],
                ),
                mock.patch.object(
                    pipeline,
                    "source_candidate_record_contract_projection",
                    return_value=None,
                ) as authenticate_frozen_candidate,
                mock.patch.object(
                    pipeline,
                    "_validate_artifact_bytes",
                    side_effect=lambda content, _arch: {
                        "status": "valid",
                        "sha256": pipeline.sha256_bytes(content),
                        "size": len(content),
                    },
                ),
                mock.patch.object(
                    pipeline,
                    "utc_now",
                    return_value="2026-08-10T00:00:03+00:00",
                ),
            ):
                mixed_reproduction = copy.deepcopy(reproduction)
                mixed_reproduction["e2e"]["runner"] = pipeline.base_runner_evidence(
                    mixed_reproduction["e2e"]["runner"]
                )
                with mock.patch.object(
                    pipeline,
                    "validate_source_candidate_e2e_evidence",
                    side_effect=[selected, mixed_reproduction],
                ), self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "cannot mix hardened and legacy",
                ):
                    pipeline.promote_source_candidate(
                        core_id=core_id,
                        source_golden_path=source_golden_path,
                        selected_e2e_path=selected["e2e_path"],
                        reproduction_e2e_path=reproduction["e2e_path"],
                        catalog_path=candidate_catalog_path,
                        store_root=store,
                    )
                result = pipeline.promote_source_candidate(
                    core_id=core_id,
                    source_golden_path=source_golden_path,
                    selected_e2e_path=selected["e2e_path"],
                    reproduction_e2e_path=reproduction["e2e_path"],
                    catalog_path=candidate_catalog_path,
                    store_root=store,
                )
                golden = pipeline.load_json(root / result["golden"])
                pin = pipeline.load_json(root / result["pin"])
                golden_report = pipeline.validate_golden_document(golden)
                store_errors = pipeline.verify_local_store(golden)
                pin_report = pipeline.validate_pin_set_document(
                    pin,
                    verify_store=True,
                    verify_sources=True,
                    document_path=root / result["pin"],
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "refusing to replace an existing source-candidate golden or pin",
                ):
                    pipeline.promote_source_candidate(
                        core_id=core_id,
                        source_golden_path=source_golden_path,
                        selected_e2e_path=selected["e2e_path"],
                        reproduction_e2e_path=reproduction["e2e_path"],
                        catalog_path=candidate_catalog_path,
                        store_root=store,
                    )

            self.assertGreater(authenticate_frozen_candidate.call_count, 0)
            self.assertEqual("created", result["status"])
            self.assertEqual(candidate["candidate_id"], result["candidate_id"])
            self.assertEqual("valid", golden_report["status"])
            self.assertEqual([], store_errors)
            self.assertEqual("valid", pin_report["status"], pin_report["errors"])
            records = golden["build_goldens"][core_id]
            proof = records["arm64"]["output_reproduction"]
            self.assertEqual(candidate, records["arm64"]["source_candidate"])
            self.assertNotEqual(
                proof["selected"]["build_logs"]["arm64"]["sha256"],
                proof["reproduction"]["build_logs"]["arm64"]["sha256"],
            )
            self.assertEqual(
                proof,
                pipeline.validated_output_reproduction_shape(
                    proof,
                    core_id=core_id,
                    golden_records=records,
                ),
            )
            selection = pin["cores"][core_id]["selection"]
            self.assertEqual(candidate, selection["source_candidate"])
            self.assertEqual(proof, selection["output_reproduction"])
            host_reproduction = records["arm64"]["host_reproduction"]
            self.assertEqual(
                host_reproduction["content_sha256"],
                result["host_reproduction_content_sha256"],
            )
            self.assertEqual(host_reproduction, selection["host_reproduction"])
            schema_documents = {
                name: json.loads(
                    (ROOT / "manifests" / name).read_text(encoding="utf-8")
                )
                for name in (
                    "golden-start.schema.json",
                    "core-golden.schema.json",
                    "core-set.schema.json",
                )
            }
            registry = Registry()
            for schema in schema_documents.values():
                Draft202012Validator.check_schema(schema)
                registry = registry.with_resource(
                    schema["$id"], Resource.from_contents(schema)
                )
            Draft202012Validator(
                schema_documents["core-golden.schema.json"],
                registry=registry,
            ).validate(golden)
            Draft202012Validator(
                schema_documents["core-set.schema.json"],
                registry=registry,
            ).validate(pin)

    def test_real_picodrive_candidate_stored_e2e_projects_raw_records(self) -> None:
        core_id = "picodrive"
        selected_arch = "arm64"
        snapshot_relative = Path(
            ".local-e2e/source-probes/edge-latest-20260810/"
            "edge-source-ref-snapshot-20260810.json"
        )
        base_golden_path = (
            ROOT
            / ".local-e2e/nightlies/"
            "picodrive-f0d4a0118a97-87be52efda9b/golden.json"
        )
        mirror_relative = Path(
            ".local-e2e/source-repositories/picodrive.git"
        )
        if not all(
            path.exists()
            for path in (
                ROOT / snapshot_relative,
                ROOT / mirror_relative,
                base_golden_path,
            )
        ):
            self.skipTest("real Picodrive source/store evidence is unavailable")

        canonical_catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        canonical_spec = canonical_catalog["cores"][core_id]
        base_document = pipeline.load_json(base_golden_path)
        base_golden = copy.deepcopy(
            base_document["build_goldens"][core_id][selected_arch]
        )
        base_store = base_golden["local_store"]
        base_e2e = pipeline.load_json(ROOT / base_store["e2e_record"]["path"])
        base_records = {
            arch: pipeline.load_json(ROOT / reference["path"])
            for arch, reference in base_store["build_records"].items()
        }
        base_logs = {
            arch: (ROOT / reference["path"]).read_bytes()
            for arch, reference in base_store["build_logs"].items()
        }
        base_package = (ROOT / base_store["package"]["path"]).read_bytes()
        base_artifact = (ROOT / base_store["artifact"]["path"]).read_bytes()
        base_metadata = (ROOT / base_store["metadata"]["path"]).read_bytes()

        with tempfile.TemporaryDirectory(prefix="picodrive-candidate-store-") as raw:
            temporary_root = Path(raw)

            def copy_repository_file(relative: str | Path) -> None:
                relative = Path(relative)
                destination = temporary_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)

            copy_repository_file("manifests/core-builds.json")
            copy_repository_file(snapshot_relative)
            copy_repository_file("scripts/core_pipeline.py")
            copy_repository_file("scripts/core_pipeline_lib/source_candidate.py")
            copy_repository_file(
                "patches/picodrive/tools-makefile-single-line-offsets.patch"
            )
            shutil.copytree(
                ROOT / mirror_relative,
                temporary_root / mirror_relative,
            )
            temporary_catalog = temporary_root / "manifests/core-builds.json"
            temporary_snapshot = temporary_root / snapshot_relative
            temporary_generator = (
                temporary_root / "scripts/core_pipeline_lib/source_candidate.py"
            )

            with mock.patch.object(
                source_candidate, "__file__", str(temporary_generator)
            ):
                rebase_report = (
                    source_candidate.prepare_source_snapshot_catalog_rebase(
                        repository_root=temporary_root,
                        catalog_path=temporary_catalog,
                        snapshot_path=temporary_snapshot,
                        core_id=core_id,
                        catalog_validator=lambda _catalog: None,
                        source_aware_contract_resolver=lambda _core: True,
                    )
                )
                rebase_path = temporary_root / rebase_report["catalog_rebase"][
                    "path"
                ]
                candidate_report = source_candidate.prepare_source_candidate_catalog(
                    repository_root=temporary_root,
                    catalog_path=temporary_catalog,
                    snapshot_path=temporary_snapshot,
                    core_id=core_id,
                    catalog_rebase_path=rebase_path,
                    catalog_validator=lambda _catalog: None,
                    candidate_catalog_validator=lambda *_args: None,
                    eligibility_validator=lambda *_args: None,
                    build_renderer=lambda *_args: "set -eu\n",
                    source_aware_contract_resolver=lambda _core: True,
                )
            candidate_path = temporary_root / candidate_report["catalog"]["path"]
            candidate_catalog = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate = candidate_catalog["source_candidate"]
            candidate_spec = candidate_catalog["cores"][core_id]
            candidate_selection = candidate["selection"]
            projection = source_candidate.validated_source_candidate_contract_projection(
                candidate,
                core_id=core_id,
                canonical_spec=canonical_spec,
                execution_spec=candidate_spec,
                source_aware_log_contract=True,
            )

            pipeline_bundle = pipeline.pipeline_source_bundle()
            required_files = set(pipeline_bundle["files"])
            required_files.update(
                {
                    canonical_spec["workflow"],
                    canonical_catalog["commit_blacklist"]["path"],
                }
            )
            metadata_replacement = canonical_spec.get("metadata", {}).get(
                "replacement"
            )
            if isinstance(metadata_replacement, dict):
                required_files.add(metadata_replacement["path"])
            for arch, record in base_records.items():
                required_files.add(record["toolchain"]["dockerfile"])
                archive = record["toolchain"].get("archive_provenance")
                if isinstance(archive, dict):
                    required_files.add(archive["lock"]["path"])
                    required_files.add(archive["validator"]["path"])
                normalized = pipeline.normalized_build_contract(
                    candidate_spec,
                    arch,
                    core_id=core_id,
                    source_candidate_contract_spec=canonical_spec,
                    source_candidate_projection=projection,
                )
                for overlay in normalized.get("overlays", []):
                    required_files.add(overlay["patch_path"])
            for relative in sorted(required_files):
                if not (temporary_root / relative).exists():
                    copy_repository_file(relative)

            def store_bytes(namespace: str, content: bytes) -> dict:
                digest = pipeline.sha256_bytes(content)
                path = (
                    temporary_root
                    / ".local-e2e/store"
                    / namespace
                    / "sha256"
                    / digest[:2]
                    / digest
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                return {
                    "path": str(path.relative_to(temporary_root)),
                    "sha256": digest,
                }

            with (
                mock.patch.object(pipeline, "ROOT", temporary_root),
                mock.patch.object(pipeline, "DEFAULT_CATALOG", temporary_catalog),
                mock.patch.object(
                    pipeline,
                    "DEFAULT_STORE",
                    temporary_root / ".local-e2e/store",
                ),
                mock.patch.object(
                    pipeline,
                    "__file__",
                    str(temporary_root / "scripts/core_pipeline.py"),
                ),
                mock.patch.object(
                    pipeline,
                    "validate_catalog",
                    side_effect=lambda _catalog: None,
                ),
            ):
                stored_records: dict[str, dict] = {}
                record_references: dict[str, dict] = {}
                recipe_references: dict[str, dict] = {}
                log_references: dict[str, dict] = {}
                for arch, base_record in sorted(base_records.items()):
                    record = copy.deepcopy(base_record)
                    recursive = [
                        item
                        for item in record["source"]["submodules"]
                        if any(
                            item["path"] == gitlink["path"]
                            or item["path"].startswith(gitlink["path"] + "/")
                            for gitlink in candidate_selection["top_level_gitlinks"]
                        )
                    ]
                    top_level = {
                        item["path"]: item["commit"]
                        for item in candidate_selection["top_level_gitlinks"]
                    }
                    for item in recursive:
                        if item["path"] in top_level:
                            item["commit"] = top_level[item["path"]]
                    record["source"] = {
                        "url": candidate_selection["url"],
                        "resolved_url": candidate_selection["url"],
                        "requested_ref": candidate_selection["requested_ref"],
                        "commit": candidate_selection["commit"],
                        "resolved_commit": candidate_selection["commit"],
                        "tree": candidate_selection["tree"],
                        "submodules": recursive,
                    }
                    record["recipe"] = {
                        **record["recipe"],
                        "catalog_path": str(candidate_path.relative_to(temporary_root)),
                        "catalog_sha256": pipeline.sha256_file(candidate_path),
                        "core_spec_sha256": pipeline.core_spec_sha256(candidate_spec),
                        "pipeline_sha256": pipeline.sha256_file(
                            temporary_root / "scripts/core_pipeline.py"
                        ),
                        "pipeline_bundle": copy.deepcopy(pipeline_bundle),
                        "commit_blacklist": copy.deepcopy(
                            candidate_catalog["commit_blacklist"]
                        ),
                        "workflow": candidate_spec["workflow"],
                        "workflow_sha256": pipeline.sha256_file(
                            temporary_root / candidate_spec["workflow"]
                        ),
                        "core_id": core_id,
                    }
                    record["build"] = {
                        **pipeline.normalized_build_contract(
                            candidate_spec,
                            arch,
                            core_id=core_id,
                            source_candidate_contract_spec=canonical_spec,
                            source_candidate_projection=projection,
                        ),
                        "log": base_record["build"]["log"],
                        "log_sha256": pipeline.sha256_bytes(base_logs[arch]),
                    }
                    record_raw = _json_bytes(record)
                    stored_records[arch] = record
                    record_references[arch] = store_bytes(
                        "build-records", record_raw
                    )
                    recipe_references[arch] = store_bytes(
                        "recipes", pipeline.recipe_snapshot(record)
                    )
                    log_references[arch] = store_bytes("logs", base_logs[arch])

                with zipfile.ZipFile(io.BytesIO(base_package)) as archive:
                    members = {
                        name: archive.read(name) for name in archive.namelist()
                    }
                package_manifest = json.loads(members["manifest.json"])
                for target in package_manifest["artifacts"].values():
                    target["source_commit"] = candidate_selection["commit"]
                package_buffer = io.BytesIO()
                with zipfile.ZipFile(package_buffer, "w") as archive:
                    for name in sorted(members):
                        content = (
                            _json_bytes(package_manifest)
                            if name == "manifest.json"
                            else members[name]
                        )
                        pipeline.add_zip_entry(archive, name, content)
                package_raw = package_buffer.getvalue()
                package_reference = store_bytes("packages", package_raw)

                e2e = copy.deepcopy(base_e2e)
                for entry in e2e["builds"]:
                    arch = entry["architecture"]
                    entry["record_sha256"] = record_references[arch]["sha256"]
                e2e["packages"][0].update(
                    {
                        "sha256": package_reference["sha256"],
                        "size": len(package_raw),
                    }
                )
                e2e["content_sha256"] = pipeline.e2e_content_sha256(e2e)
                e2e_reference = store_bytes("e2e", _json_bytes(e2e))
                artifact_reference = store_bytes("artifacts", base_artifact)
                metadata_reference = store_bytes("metadata", base_metadata)

                selected = stored_records[selected_arch]
                golden = copy.deepcopy(base_golden)
                for field in (
                    "source",
                    "recipe",
                    "toolchain",
                    "build",
                    "artifact",
                    "metadata",
                ):
                    golden[field] = copy.deepcopy(selected[field])
                golden["source_candidate"] = copy.deepcopy(candidate)
                golden["e2e"].update(
                    {
                        "content_sha256": e2e["content_sha256"],
                        "package_sha256": package_reference["sha256"],
                        "build_records": {
                            arch: reference["sha256"]
                            for arch, reference in record_references.items()
                        },
                    }
                )
                golden["local_store"] = {
                    "availability": "local-only",
                    "artifact": artifact_reference,
                    "metadata": metadata_reference,
                    "e2e_record": e2e_reference,
                    "package": package_reference,
                    "build_records": record_references,
                    "build_logs": log_references,
                    "recipe_snapshots": recipe_references,
                }

                self.assertEqual(
                    [],
                    pipeline.verify_stored_e2e_bundle(
                        golden,
                        core_id,
                        selected_arch,
                    ),
                )
                selected_record_path = (
                    temporary_root / record_references[selected_arch]["path"]
                )
                pipeline._validate_canonical_compatibility_build_record(
                    copy.deepcopy(selected),
                    selected_record_path,
                    {"golden_record": golden},
                    base_logs[selected_arch].decode("utf-8"),
                )
                compatibility_tamper = copy.deepcopy(golden)
                compatibility_tamper["source_candidate"]["candidate_id"] = (
                    "0" * 64
                )
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "source-candidate binding differs",
                ):
                    pipeline._validate_canonical_compatibility_build_record(
                        copy.deepcopy(selected),
                        selected_record_path,
                        {"golden_record": compatibility_tamper},
                        base_logs[selected_arch].decode("utf-8"),
                    )

                tampered = copy.deepcopy(golden)
                tampered["source_candidate"]["candidate_id"] = "0" * 64
                self.assertTrue(
                    pipeline.verify_stored_e2e_bundle(
                        tampered,
                        core_id,
                        selected_arch,
                    )
                )

                tampered_snapshot = copy.deepcopy(golden)
                provenance = tampered_snapshot["source_candidate"]
                provenance["snapshot"]["file_sha256"] = "0" * 64
                material = copy.deepcopy(provenance)
                material.pop("candidate_id")
                provenance["candidate_id"] = pipeline.sha256_bytes(
                    json.dumps(
                        material,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                self.assertTrue(
                    pipeline.verify_stored_e2e_bundle(
                        tampered_snapshot,
                        core_id,
                        selected_arch,
                    )
                )


if __name__ == "__main__":
    unittest.main()
