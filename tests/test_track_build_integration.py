#!/usr/bin/env python3

from __future__ import annotations

import argparse
from contextlib import contextmanager
import copy
import importlib.util
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest import mock
import json
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "core_pipeline.py"
SPEC = importlib.util.spec_from_file_location(
    "core_pipeline_track_build_integration", MODULE_PATH
)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


class TrackBuildIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        cls.authoritative_pin_index = pipeline.load_authoritative_core_pin_index()

    @staticmethod
    @contextmanager
    def _synthetic_candidate_recipe_authentication():
        """Isolate unit-only candidate shapes from the real frozen-store tests."""

        with (
            mock.patch.object(
                pipeline,
                "require_canonical_store_entry",
                return_value=Path("/synthetic/frozen-recipe.json"),
            ),
            mock.patch.object(
                pipeline,
                "verified_json_object",
                return_value={"recipe": {}},
            ),
            mock.patch.object(
                pipeline,
                "source_candidate_record_contract_projection",
                return_value=None,
            ) as authenticate,
        ):
            yield authenticate

    def _resolve_synthetic_historical_group(
        self,
        *,
        core_id: str,
        group_tag: str,
        pin_index: dict | None = None,
    ) -> dict:
        """Exercise downstream pin behavior without claiming track admission.

        The live registry admits only the current reviewed campaign tranche;
        other historical pins have not been manually admitted to a version
        channel. A few integration tests still need to reach recipe, source,
        and output authentication boundaries, so this helper supplies one
        explicitly test-only admitted inventory row while leaving production
        track validation untouched.
        """

        if pin_index is None:
            pin_index = self.authoritative_pin_index
        matches = [
            entry
            for entry in pin_index.values()
            if entry.get("core_id") == core_id
        ]
        if len(matches) != 1:
            raise AssertionError(
                f"expected one historical pin fixture for {core_id}, got {len(matches)}"
            )
        pin = matches[0]
        track, marker, requested_chipset = pipeline.parse_group_tag(group_tag)
        if marker != "test":
            raise AssertionError("historical fixture only supports TEST groups")
        selected_architectures = (
            copy.deepcopy(pin["architectures"])
            if requested_chipset == "universal"
            else [pipeline.CHIPSET_ARCHITECTURES[requested_chipset]]
        )
        tuning_registry = pipeline.load_json(pipeline.DEFAULT_CHIPSET_TUNINGS)
        tuning = pipeline.execution_tuning_profile(
            "universal-v1",
            selected_architectures[0],
            tuning_registry,
        )
        assert tuning is not None
        tuning_projection = {
            key: copy.deepcopy(tuning[key])
            for key in (
                "profile_id",
                "content_sha256",
                "properties",
                "compiler_argument_mapping_version",
                "compiler_arguments",
            )
        }
        track_registry = pipeline.load_json(pipeline.DEFAULT_CORE_TRACKS)
        branch_bases = pipeline.load_json(pipeline.DEFAULT_SPRUCE_BRANCH_BASES)
        release_roster = pipeline.load_json(pipeline.DEFAULT_SPRUCE_RELEASE_ROSTER)
        row = {
            "core_id": core_id,
            "track": track,
            "requested_marker": marker,
            "requested_chipset": requested_chipset,
            "selected_chipset": "universal",
            "selected_state": "test",
            "stability": "unstable",
            "resolution": (
                "exact_test"
                if requested_chipset == "universal"
                else "universal_test_fallback"
            ),
            "test_origin_track": "main",
            "spruce_branch_basis": copy.deepcopy(
                track_registry["tracks"][track]["spruce_branch_basis"]
            ),
            "variant_id": pipeline.sha256_bytes(
                f"synthetic-historical:{group_tag}:{core_id}".encode()
            ),
            "pin": {
                key: pin[key]
                for key in ("path", "pin_id", "file_sha256", "content_sha256")
            },
            "source_commit": pin["source_commit"],
            "architectures": copy.deepcopy(pin["architectures"]),
            "selected_architectures": selected_architectures,
            "tuning": tuning_projection,
        }
        inventory = {
            "complete": True,
            "cores": [row],
            "deferred_cores": [],
            "unsupported_core_ids": [],
            "content_sha256": pipeline.sha256_bytes(
                f"synthetic-inventory:{group_tag}:{core_id}".encode()
            ),
            "track_registry_content_sha256": track_registry["content_sha256"],
            "tuning_registry_content_sha256": tuning_registry["content_sha256"],
        }
        with mock.patch.object(
            pipeline,
            "construct_core_track_inventory",
            return_value=inventory,
        ):
            return pipeline.resolve_core_group_build_selection(
                group_tag=group_tag,
                catalog_path=pipeline.DEFAULT_CATALOG,
                catalog=self.catalog,
                core_id=core_id,
                pin_index=pin_index,
                track_registry=track_registry,
                tuning_registry=tuning_registry,
                release_roster=release_roster,
                spruce_branch_bases=branch_bases,
            )

    def test_build_entrypoints_accept_only_canonical_group_tags(self) -> None:
        parser = pipeline.build_parser()
        build_core = parser.parse_args(
            ["build-core", "--core", "mgba", "--group-tag", "main-test:a523"]
        )
        e2e = parser.parse_args(
            ["e2e", "--core", "mgba", "--group-tag", "edge-stable:universal"]
        )
        self.assertEqual("main-test:a523", build_core.group_tag)
        self.assertEqual("edge-stable:universal", e2e.group_tag)
        with self.assertRaises(SystemExit):
            parser.parse_args(
                ["e2e", "--core", "mgba", "--group-tag", "main:universal"]
            )
        with self.assertRaises(SystemExit):
            parser.parse_args(
                [
                    "e2e",
                    "--core",
                    "mgba",
                    "--group-tag",
                    "main-test:a523",
                    "--arch",
                    "arm64",
                ]
            )

    def test_tuning_profile_is_a_distinct_one_abi_e2e_scope(self) -> None:
        parser = pipeline.build_parser()
        args = parser.parse_args(
            [
                "e2e",
                "--core",
                "frodo",
                "--tuning-profile",
                "a523-cortex-a55-v1",
            ]
        )
        self.assertEqual("a523-cortex-a55-v1", args.tuning_profile)
        for conflicting in ("--arch", "--group-tag"):
            values = [
                "e2e",
                "--core",
                "frodo",
                "--tuning-profile",
                "a523-cortex-a55-v1",
                conflicting,
                "arm64" if conflicting == "--arch" else "main-test:a523",
            ]
            with self.assertRaises(SystemExit):
                parser.parse_args(values)

    def test_registry_tuning_candidate_is_exact_and_tamper_evident(self) -> None:
        selection = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        self.assertEqual("a523", selection["profile"]["chipset"])
        self.assertEqual("arm64", selection["profile"]["architecture"])
        self.assertEqual(["-mcpu=cortex-a55"], selection["profile"]["compiler_arguments"])
        self.assertEqual(
            selection,
            pipeline.validated_tuning_candidate_selection(selection),
        )
        for mutation in ("registry", "profile", "arguments"):
            tampered = copy.deepcopy(selection)
            if mutation == "registry":
                tampered["registry"]["content_sha256"] = "0" * 64
            elif mutation == "profile":
                tampered["profile"]["content_sha256"] = "1" * 64
            else:
                tampered["profile"]["compiler_arguments"] = ["-mcpu=cortex-a53"]
            with self.assertRaises(pipeline.PipelineError):
                pipeline.validated_tuning_candidate_selection(tampered)

    def test_tuning_candidate_package_is_one_abi_and_manifest_bound(self) -> None:
        selection = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        spec = self.catalog["cores"]["frodo"]
        artifact_bytes = b"artifact"
        metadata_bytes = b"metadata"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target_root = root / "frodo" / "arm64"
            target_root.mkdir(parents=True)
            (target_root / spec["build"]["artifact_name"]).write_bytes(artifact_bytes)
            (target_root / spec["metadata"]["artifact_name"]).write_bytes(metadata_bytes)
            record = {
                "core_id": "frodo",
                "architecture": "arm64",
                "result": "passed",
                "artifact": {
                    "path": spec["build"]["artifact_name"],
                    "sha256": pipeline.sha256_bytes(artifact_bytes),
                },
                "metadata": {
                    "path": spec["metadata"]["artifact_name"],
                    "status": "valid",
                    "sha256": pipeline.sha256_bytes(metadata_bytes),
                },
                "source": {"resolved_commit": spec["source"]["commit"]},
                "toolchain": {"resolved_image_id": "sha256:" + "1" * 64},
            }
            packaged = pipeline.package_e2e_core(
                root,
                "frodo",
                [record],
                spec,
                tuning_selection=selection,
            )
            self.assertEqual("packaged", packaged["result"])
            self.assertEqual(selection, packaged["tuning_candidate"])
            with zipfile.ZipFile(root / packaged["path"]) as archive:
                manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(selection, manifest["tuning_candidate"])
            self.assertEqual({"arm64"}, set(manifest["artifacts"]))

    def test_tuned_direct_cargo_fails_before_run_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=pipeline.ROOT / ".local-e2e"
        ) as temporary:
            output_root = Path(temporary)
            run_root = output_root / "tuned-cargo-preflight"
            args = argparse.Namespace(
                catalog=pipeline.DEFAULT_CATALOG,
                runner_profile="local",
                core="libgametank",
                group_tag=None,
                tuning_profile="a523-cortex-a55-v1",
                arch=None,
                run_id="tuned-cargo-preflight",
                output_root=output_root,
                fail_fast=True,
            )
            with self.assertRaisesRegex(
                pipeline.PipelineError, "chipset-tuned direct-cargo"
            ):
                pipeline.cmd_e2e(args)
            self.assertFalse(run_root.exists())

    def test_legacy_promotion_rejects_tuning_candidate_evidence(self) -> None:
        selection = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        record = {
            "schema_version": 2,
            "local_only": True,
            "publication": "disabled",
            "result": "passed",
            "build_exit_code": 0,
            "tuning_candidate": selection,
            "recipe": {
                "chipset_tuning": pipeline.tuning_candidate_recipe_identity(
                    selection
                )
            },
        }
        with tempfile.TemporaryDirectory(
            dir=pipeline.ROOT / ".local-e2e"
        ) as temporary, self.assertRaisesRegex(
            pipeline.PipelineError, "separate promote-tuned-variant flow"
        ):
            pipeline.validate_build_record_identity(
                record,
                Path(temporary) / "build-record.json",
                pipeline.DEFAULT_CATALOG,
                self.catalog,
            )

    def test_live_group_plan_binds_pin_outputs_and_projected_architecture(self) -> None:
        selection = self._resolve_synthetic_historical_group(
            core_id="mgba",
            group_tag="main-test:a523",
        )
        self.assertEqual(["arm64"], selection["selected_architectures"])
        self.assertEqual("universal", selection["selected_chipset"])
        self.assertEqual([], selection["tuning"]["compiler_arguments"])
        self.assertEqual(
            {"url", "requested_ref", "commit", "tree", "submodules"},
            set(selection["execution_source"]),
        )
        self.assertEqual(
            selection["source_commit"],
            selection["execution_source"]["commit"],
        )
        self.assertEqual(
            "not_applicable_projected_architectures",
            selection["expected_outputs"]["package"]["comparison"],
        )
        self.assertRegex(
            selection["expected_outputs"]["targets"]["arm64"]["artifact"][
                "sha256"
            ],
            r"^[0-9a-f]{64}$",
        )

    def test_non_build_core_spec_drift_remains_explicit_and_reproducible(self) -> None:
        selection = self._resolve_synthetic_historical_group(
            core_id="ecwolf",
            group_tag="main-test:universal",
        )
        compatibility = selection["recipe_compatibility"]
        self.assertEqual(
            "source-normalized-build-contract-v1",
            compatibility["model"],
        )
        self.assertFalse(compatibility["core_spec_identity_match"])
        self.assertNotEqual(
            compatibility["selected_pin_core_spec_sha256"],
            compatibility["execution_core_spec_sha256"],
        )

    def test_normalized_historical_recipe_drift_fails_preflight(self) -> None:
        pin_index = self.authoritative_pin_index
        with mock.patch.object(
            pipeline,
            "recorded_build_contract",
            return_value={"driver": "historical-unknown"},
        ):
            with self.assertRaisesRegex(
                pipeline.PipelineError,
                "unsupported historical recipe",
            ):
                self._resolve_synthetic_historical_group(
                    core_id="mgba",
                    group_tag="main-test:universal",
                    pin_index=pin_index,
                )

    def test_live_main_universal_roster_is_explicitly_partitioned(self) -> None:
        tracks = pipeline.load_json(pipeline.DEFAULT_CORE_TRACKS)
        tunings = pipeline.load_json(pipeline.DEFAULT_CHIPSET_TUNINGS)
        roster = pipeline.load_json(pipeline.DEFAULT_SPRUCE_RELEASE_ROSTER)
        branch_bases = pipeline.load_json(pipeline.DEFAULT_SPRUCE_BRANCH_BASES)
        source_registry_index = pipeline.load_core_track_source_registry_index(
            pipeline.ROOT
        )
        inventory = pipeline.construct_core_track_inventory(
            tracks,
            catalog=self.catalog,
            pin_index=self.authoritative_pin_index,
            tunings=tunings,
            main_release_roster=roster,
            spruce_branch_bases=branch_bases,
            group_tag="main-test:universal",
            source_registry_index=source_registry_index,
        )
        self.assertFalse(inventory["complete"])
        self.assertEqual("deferred", inventory["inventory_state"])
        self.assertEqual([], inventory["unsupported_core_ids"])
        selected_core_ids = {
            "2048",
            "gambatte",
            "handy",
            "lowresnx",
            "potator",
            "prosystem",
            "quicknes",
            "race",
            "sameduck",
            "tgbdual",
            "vecx",
            "vemulator",
        }
        self.assertEqual(
            sorted(selected_core_ids),
            [row["core_id"] for row in inventory["cores"]],
        )
        self.assertEqual(86, len(inventory["deferred_cores"]))
        self.assertEqual(
            sorted(set(self.catalog["cores"]) - selected_core_ids),
            [row["core_id"] for row in inventory["deferred_cores"]],
        )
        self.assertTrue(
            all(
                row["reason"] == "no-reviewed-version-channel-build-pin"
                and row["spruce_branch_basis"]
                == tracks["tracks"]["main"]["spruce_branch_basis"]
                for row in inventory["deferred_cores"]
            )
        )
        representative = copy.deepcopy(inventory)
        representative["deferred_cores"] = [
            row
            for row in representative["deferred_cores"]
            if row["core_id"] == "mgba"
        ]
        with mock.patch.object(
            pipeline,
            "construct_core_track_inventory",
            return_value=representative,
        ), mock.patch.object(
            pipeline,
            "container_build_script",
        ) as render, mock.patch.object(
            pipeline,
            "require_source_commits_eligible",
        ) as eligibility, self.assertRaisesRegex(
            pipeline.PipelineError,
            "core group selection is deferred for mgba: main-test:universal: "
            "no-reviewed-version-channel-build-pin",
        ):
            pipeline.resolve_core_group_build_selection(
                group_tag="main-test:universal",
                catalog_path=pipeline.DEFAULT_CATALOG,
                catalog=self.catalog,
                core_id="mgba",
                pin_index=self.authoritative_pin_index,
                track_registry=tracks,
                tuning_registry=tunings,
                release_roster=roster,
                spruce_branch_bases=branch_bases,
            )
        render.assert_not_called()
        eligibility.assert_not_called()

    @staticmethod
    def _alternate_source(spec: dict) -> dict:
        return {
            "url": spec["source"]["url"],
            "requested_ref": "refs/heads/nightly-reproduction",
            "commit": "1" * 40,
            "tree": "2" * 40,
            "submodules": [],
        }

    @staticmethod
    def _swanstation_source_candidate() -> dict:
        """Return the exact frozen SwanStation candidate used by edge probing."""

        candidate = {
            "base_catalog": {
                "core_spec_sha256": (
                    "e880984e36ae029dd36dc0543e4a4f197bf378258ae20a10af36ee053ee29d6e"
                ),
                "file_sha256": (
                    "a9ba3ee4e34e38367786164bd4da61b00ac459a76f0ca7a239a23be82c582964"
                ),
                "path": "manifests/core-builds.json",
            },
            "candidate_id": "0" * 64,
            "catalog_rebase": {
                "content_sha256": (
                    "d49846fa1b7fd6d7232b273364fdcae2a9de5aec18029c7532c623acd09a78de"
                ),
                "file_sha256": (
                    "606690b8189fcef05fd9923543e45534190fd0c1402d3c2ed1add9a75b9f2a55"
                ),
                "path": (
                    ".local-e2e/source-probes/catalog-rebases/"
                    "5475fd23d2eeceaa20d8a85598520713c310b46a46b73062d1832e2fc05e7d19/"
                    "a9ba3ee4e34e38367786164bd4da61b00ac459a76f0ca7a239a23be82c582964/"
                    "swanstation.json"
                ),
            },
            "core_id": "swanstation",
            "execution": {
                "core_spec_sha256": (
                    "93fa08782f6a8c43ff458709a4a9e8d6036c8e3049cd8279b47e0a26a29fd9f2"
                ),
                "source_date_epoch_derivation": "candidate-commit-epoch",
            },
            "generator": {
                "path": "scripts/core_pipeline_lib/source_candidate.py",
                "sha256": (
                    "09af447fd8ac7ed28f8940a50e2ea95da22d5b6baa5c6efde53440dc3ac1defd"
                ),
            },
            "local_only": True,
            "mirror": {
                "frozen_local_ref": (
                    "refs/spruce-edge-refs/"
                    "3d83b77acf6a2c47b5da776ffe3ae1f620f0737eb3a83790f547709a98d8ea38"
                ),
                "origin_url": "https://github.com/libretro/swanstation.git",
                "path": ".local-e2e/source-repositories/swanstation.git",
            },
            "publication": "disabled",
            "schema_version": 1,
            "selection": {
                "catalog_commit": "f901022198dacf125d43331c6540492441ab415b",
                "catalog_is_ancestor": True,
                "catalog_tree": "c902d31b76bd3919758851e87b0adf1607601c82",
                "commit": "5430a4a53b89fa5827c97b84ada29d23317245bc",
                "commit_epoch": 1784512264,
                "frozen_local_ref": (
                    "refs/spruce-edge-refs/"
                    "3d83b77acf6a2c47b5da776ffe3ae1f620f0737eb3a83790f547709a98d8ea38"
                ),
                "latest_semantics": "exact-branch-tip",
                "recipe_risk": {
                    "catalog_declared_submodules": 0,
                    "driver": "direct-cmake",
                    "git_version": False,
                    "overlays": 1,
                    "recursive_submodules": True,
                    "source_aware_log_contract": False,
                    "source_date_epoch": True,
                    "submodule_fetch": True,
                },
                "ref_kind": "branch",
                "ref_object": "5430a4a53b89fa5827c97b84ada29d23317245bc",
                "ref_object_type": "commit",
                "requested_ref": "refs/heads/main",
                "status": "fast-forward",
                "top_level_gitlinks": [],
                "tree": "54dd6cb03c7749e159226e42b173fbaf31cfa39f",
                "url": "https://github.com/libretro/swanstation.git",
            },
            "snapshot": {
                "captured_at": "2026-08-10T05:12:51Z",
                "catalog": {
                    "file_sha256": (
                        "aa3985337035ada50e0354f7abdb9f33933a77c555faf6502b6e28033546811d"
                    ),
                    "path": "manifests/core-builds.json",
                },
                "content_sha256": (
                    "5475fd23d2eeceaa20d8a85598520713c310b46a46b73062d1832e2fc05e7d19"
                ),
                "file_sha256": (
                    "e476a4f442c204ef4b356473704ac9802a2600b23890eca92f5c81c8333b83ca"
                ),
                "path": (
                    ".local-e2e/source-probes/edge-latest-20260810/"
                    "edge-source-ref-snapshot-20260810.json"
                ),
                "snapshot_id": "edge-source-ref-snapshot-20260810",
            },
            "validation_scope": "immutable-edge-source-candidate-catalog-v1",
        }
        material = copy.deepcopy(candidate)
        material.pop("candidate_id")
        candidate["candidate_id"] = pipeline.sha256_bytes(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        )
        return candidate

    def _swanstation_candidate_group_fixture(
        self,
    ) -> tuple[dict, dict, dict, dict]:
        catalog_spec = copy.deepcopy(self.catalog["cores"]["swanstation"])
        candidate = self._swanstation_source_candidate()
        selected = candidate["selection"]
        execution_source = {
            "url": selected["url"],
            "requested_ref": selected["requested_ref"],
            "commit": selected["commit"],
            "tree": selected["tree"],
            "submodules": copy.deepcopy(selected["top_level_gitlinks"]),
        }
        candidate_spec = copy.deepcopy(catalog_spec)
        candidate_spec["source"] = {
            key: copy.deepcopy(execution_source[key])
            for key in catalog_spec["source"]
        }
        candidate_spec["build"]["source_date_epoch"] = selected["commit_epoch"]
        self.assertEqual(
            candidate["execution"]["core_spec_sha256"],
            pipeline.core_spec_sha256(candidate_spec),
        )

        def stored(kind: str, label: str) -> dict:
            digest = pipeline.sha256_bytes(label.encode())
            return {
                "path": f".local-e2e/store/{kind}/sha256/{digest[:2]}/{digest}",
                "sha256": digest,
            }

        selected_side = {
            "run_id": "swanstation-edge-selected",
            "content_sha256": pipeline.sha256_bytes(b"swanstation selected E2E"),
            "e2e_record": stored("e2e", "selected E2E"),
            "build_records": {"arm64": stored("build-records", "selected record")},
            "build_logs": {"arm64": stored("logs", "selected log")},
            "recipe_snapshots": {"arm64": stored("recipes", "selected recipe")},
        }
        reproduction_side = {
            "run_id": "swanstation-edge-reproduction",
            "content_sha256": pipeline.sha256_bytes(b"swanstation reproduction E2E"),
            "e2e_record": stored("e2e", "reproduction E2E"),
            "build_records": {
                "arm64": stored("build-records", "reproduction record")
            },
            "build_logs": {"arm64": stored("logs", "reproduction log")},
            "recipe_snapshots": {
                "arm64": stored("recipes", "reproduction recipe")
            },
        }
        artifact = {
            "path": candidate_spec["build"]["artifact_name"],
            "status": "valid",
            "sha256": pipeline.sha256_bytes(b"swanstation edge artifact"),
            "size": 25,
        }
        metadata = {
            "path": candidate_spec["metadata"]["artifact_name"],
            "status": "valid",
            "sha256": pipeline.sha256_bytes(b"swanstation edge metadata"),
            "size": 25,
        }
        package_sha256 = pipeline.sha256_bytes(b"swanstation edge package")
        proof = {
            "schema_version": 1,
            "validation_scope": pipeline.SOURCE_CANDIDATE_REPRODUCTION_SCOPE,
            "selected": selected_side,
            "reproduction": reproduction_side,
            "equivalent_outputs": {
                "artifacts": {
                    "arm64": {
                        "sha256": artifact["sha256"],
                        "size": artifact["size"],
                    }
                },
                "metadata": {
                    "sha256": metadata["sha256"],
                    "size": metadata["size"],
                },
                "package": {
                    "name": "swanstation_libretro.zip",
                    "sha256": package_sha256,
                    "size": 29,
                },
            },
        }
        golden = {
            "source": {
                **copy.deepcopy(execution_source),
                "resolved_commit": execution_source["commit"],
                "resolved_url": execution_source["url"],
                "submodules": [],
            },
            "recipe": {
                "core_spec_sha256": candidate["execution"]["core_spec_sha256"]
            },
            "build": pipeline.normalized_build_contract(candidate_spec, "arm64"),
            "artifact": artifact,
            "metadata": metadata,
            "source_candidate": copy.deepcopy(candidate),
            "output_reproduction": proof,
            "e2e": {
                "run_id": selected_side["run_id"],
                "content_sha256": selected_side["content_sha256"],
                "package_sha256": package_sha256,
            },
            "local_store": {
                "e2e_record": selected_side["e2e_record"],
                "build_records": selected_side["build_records"],
                "build_logs": selected_side["build_logs"],
                "recipe_snapshots": selected_side["recipe_snapshots"],
            },
        }
        pin_selection = {
            "source_candidate": copy.deepcopy(candidate),
            "output_reproduction": proof,
            "targets": {
                "arm64": {
                    "artifact": {
                        key: artifact[key] for key in ("path", "sha256", "size")
                    },
                    "golden_record": golden,
                }
            },
        }
        group_selection = {
            "pin": {
                "path": "pins/core-sets/swanstation-edge-unit.json",
                "pin_id": "swanstation-edge-unit",
                "file_sha256": "a" * 64,
                "content_sha256": "b" * 64,
            },
            "execution_source": execution_source,
            "source_commit": execution_source["commit"],
            "selected_architectures": ["arm64"],
        }
        return catalog_spec, candidate_spec, group_selection, pin_selection

    def _write_swanstation_deep_group_fixture(self, run_root: Path) -> dict:
        """Write a real grouped-worker evidence graph for the frozen candidate."""

        core_id = "swanstation"
        arch = "arm64"
        (
            _catalog_spec,
            candidate_spec,
            group_reference,
            pin_selection,
        ) = self._swanstation_candidate_group_fixture()
        target_root = run_root / core_id / arch
        target_root.mkdir(parents=True)
        artifact_path = target_root / candidate_spec["build"]["artifact_name"]
        metadata_path = target_root / candidate_spec["metadata"]["artifact_name"]
        log_path = target_root / "build.log"
        artifact_path.write_bytes(b"genuine SwanStation edge artifact fixture")
        metadata_path.write_bytes(b"genuine SwanStation metadata fixture")

        tuning = pipeline.execution_tuning_profile("universal-v1", arch)
        assert tuning is not None
        tuning_marker = shlex.split(
            pipeline.chipset_tuning_marker_shell(tuning)
        )[-1]
        compiler = sorted(pipeline.TARGET_COMPILERS[arch])[0]
        tool_paths = {
            role: f"/fixture/bin/{name}"
            for role, name in pipeline.TARGET_CMAKE_TOOL_NAMES[arch].items()
        }
        direct_cmake_markers = pipeline.direct_cmake_log_markers(
            candidate_spec,
            arch,
            tool_paths,
        )
        log_path.write_text(
            tuning_marker
            + "\n"
            + f"{compiler} -O2 -c source.c -o source.o\n"
            + "\n".join(direct_cmake_markers)
            + "\n",
            encoding="utf-8",
        )

        artifact = {
            "path": artifact_path.name,
            "status": "valid",
            "sha256": pipeline.sha256_file(artifact_path),
            "size": artifact_path.stat().st_size,
            "needed": [
                "libc.so.6",
                "libdl.so.2",
                "libgcc_s.so.1",
                "libm.so.6",
                "libpthread.so.0",
                "librt.so.1",
                "libstdc++.so.6",
            ],
        }
        metadata = {
            "path": metadata_path.name,
            "status": "valid",
            "sha256": pipeline.sha256_file(metadata_path),
            "size": metadata_path.stat().st_size,
        }
        toolchain_key = pipeline.build_toolchain_key(candidate_spec, arch)
        record = {
            "schema_version": 2,
            "local_only": True,
            "publication": "disabled",
            "started_at": "2026-08-10T00:00:01+00:00",
            "finished_at": "2026-08-10T00:00:02+00:00",
            "core_id": core_id,
            "architecture": arch,
            "result": "passed",
            "build_exit_code": 0,
            "source": {
                **copy.deepcopy(candidate_spec["source"]),
                "resolved_commit": candidate_spec["source"]["commit"],
                "resolved_url": candidate_spec["source"]["url"],
                "submodules": [],
            },
            "recipe": pipeline.recipe_record(
                pipeline.DEFAULT_CATALOG,
                core_id,
                candidate_spec,
            ),
            "toolchain": {
                **copy.deepcopy(self.catalog["toolchains"][toolchain_key]),
                "archive_provenance": pipeline.expected_archive_provenance(
                    self.catalog,
                    toolchain_key,
                ),
                "resolved_image_id": self.catalog["toolchains"][toolchain_key][
                    "image_id"
                ],
                "libretro_super_commit": self.catalog["resolver"][
                    "libretro_super_commit"
                ],
                "resolver_digests": copy.deepcopy(self.catalog["resolver"]),
                "compiler": "fixture aarch64 compiler",
                "sysroot": "/fixture",
            },
            "build": {
                **pipeline.normalized_build_contract(candidate_spec, arch),
                "log": log_path.name,
                "log_sha256": pipeline.sha256_file(log_path),
            },
            "artifact": artifact,
            "metadata": metadata,
        }
        package = pipeline.package_e2e_core(
            run_root,
            core_id,
            [record],
            candidate_spec,
        )
        self.assertEqual("packaged", package["result"])

        golden = pin_selection["targets"][arch]["golden_record"]
        golden["artifact"] = copy.deepcopy(artifact)
        golden["metadata"] = copy.deepcopy(metadata)
        golden["e2e"]["package_sha256"] = package["sha256"]
        proof = pin_selection["output_reproduction"]
        proof["equivalent_outputs"] = {
            "artifacts": {
                arch: {
                    "sha256": artifact["sha256"],
                    "size": artifact["size"],
                }
            },
            "metadata": {
                "sha256": metadata["sha256"],
                "size": metadata["size"],
            },
            "package": {
                "name": package["path"],
                "sha256": package["sha256"],
                "size": package["size"],
            },
        }
        pin_selection["targets"][arch]["artifact"] = {
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "size": artifact["size"],
        }

        tuning_projection = {
            key: copy.deepcopy(tuning[key])
            for key in (
                "profile_id",
                "content_sha256",
                "properties",
                "compiler_argument_mapping_version",
                "compiler_arguments",
            )
        }
        candidate_sha256 = pin_selection["source_candidate"]["execution"][
            "core_spec_sha256"
        ]
        group = {
            "schema_version": 1,
            "validation_scope": "pinned-output-reproduction-v1",
            "group_tag": "edge-test:universal",
            "inventory_content_sha256": "1" * 64,
            "track_registry_content_sha256": "2" * 64,
            "tuning_registry_content_sha256": "3" * 64,
            "spruce_branch_basis": copy.deepcopy(
                pipeline.load_json(pipeline.DEFAULT_CORE_TRACKS)["tracks"][
                    "edge"
                ]["spruce_branch_basis"]
            ),
            "core_id": core_id,
            "variant_id": pipeline.sha256_bytes(
                b"swanstation-edge-test-universal-deep-validator"
            ),
            "requested_marker": "test",
            "requested_chipset": "universal",
            "selected_chipset": "universal",
            "selected_state": "test",
            "stability": "unstable",
            "resolution": "exact_test",
            "test_origin_track": "edge",
            "pin": copy.deepcopy(group_reference["pin"]),
            "source_commit": group_reference["source_commit"],
            "execution_source": copy.deepcopy(
                group_reference["execution_source"]
            ),
            "recipe_compatibility": {
                "model": "source-normalized-build-contract-v1",
                "selected_pin_core_spec_sha256": candidate_sha256,
                "execution_core_spec_sha256": candidate_sha256,
                "core_spec_identity_match": True,
            },
            "selected_architectures": [arch],
            "tuning": tuning_projection,
            "expected_outputs": {
                "targets": {
                    arch: {
                        "artifact": {
                            "sha256": artifact["sha256"],
                            "size": artifact["size"],
                        }
                    }
                },
                "metadata": {
                    "sha256": metadata["sha256"],
                    "size": metadata["size"],
                },
                "package": {
                    "comparison": "exact",
                    "name": package["path"],
                    "sha256": package["sha256"],
                    "size": package["size"],
                },
            },
        }
        record["core_group"] = copy.deepcopy(group)
        record["recipe"]["chipset_tuning"] = {
            "profile_id": tuning["profile_id"],
            "content_sha256": tuning["content_sha256"],
        }
        record_path = target_root / "build-record.json"
        record_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        package["core_group"] = {
            "variant_id": group["variant_id"],
            "comparison": "exact",
        }
        e2e = {
            "schema_version": 2,
            "run_id": "swanstation-edge-deep-validator",
            "local_only": True,
            "publication": "disabled",
            "runner": {
                "profile": "local",
                "mode": "native",
                "backend": "local-docker",
                "local_only": True,
                "publication": "disabled",
            },
            "result": "passed",
            "workflow_audit": {},
            "builds": [
                {
                    "core_id": core_id,
                    "architecture": arch,
                    "result": "passed",
                    "record": str(record_path.relative_to(pipeline.ROOT)),
                    "record_sha256": pipeline.sha256_file(record_path),
                }
            ],
            "packages": [package],
            "core_group": copy.deepcopy(group),
        }
        e2e["content_sha256"] = pipeline.e2e_content_sha256(e2e)
        e2e_path = run_root / "e2e-record.json"
        e2e_path.write_text(
            json.dumps(e2e, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return {
            "candidate_spec": candidate_spec,
            "pin_selection": pin_selection,
            "group": group,
            "record": record,
            "record_path": record_path,
            "e2e": e2e,
            "e2e_path": e2e_path,
            "artifact_validation": artifact,
            "tuning": tuning,
        }

    def test_alternate_commit_requires_an_authenticated_candidate_pin(
        self,
    ) -> None:
        catalog_spec = copy.deepcopy(self.catalog["cores"]["frodo"])
        source = self._alternate_source(catalog_spec)
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "changed group source requires authenticated source-candidate provenance",
        ):
            pipeline.group_execution_spec(
                core_id="frodo",
                catalog_spec=catalog_spec,
                group_selection={
                    "execution_source": source,
                    "source_commit": source["commit"],
                    "selected_architectures": copy.deepcopy(
                        catalog_spec["targets"]
                    ),
                },
            )

    def test_swanstation_source_candidate_projects_its_pinned_epoch(self) -> None:
        (
            catalog_spec,
            candidate_spec,
            group_selection,
            pin_selection,
        ) = self._swanstation_candidate_group_fixture()
        original = copy.deepcopy(catalog_spec)
        with self._synthetic_candidate_recipe_authentication() as authenticate:
            execution = pipeline._group_execution_spec(
                core_id="swanstation",
                catalog_spec=catalog_spec,
                group_selection=group_selection,
                validated_pin_selection=pin_selection,
            )
        self.assertEqual(1, authenticate.call_count)
        self.assertEqual(candidate_spec["source"], execution["source"])
        self.assertEqual(1784512264, execution["build"]["source_date_epoch"])
        self.assertEqual(
            "93fa08782f6a8c43ff458709a4a9e8d6036c8e3049cd8279b47e0a26a29fd9f2",
            pipeline.core_spec_sha256(execution),
        )
        golden = pin_selection["targets"]["arm64"]["golden_record"]
        self.assertEqual(
            pipeline.recorded_build_contract(golden["build"]),
            pipeline.normalized_build_contract(execution, "arm64"),
        )
        script = pipeline.container_build_script(
            "swanstation",
            "arm64",
            execution,
            self.catalog["resolver"],
        )
        self.assertEqual(2, script.count("1784512264"))
        self.assertNotIn("1782767217", script)
        self.assertEqual(original, catalog_spec)

    def test_group_execution_reloads_and_authenticates_its_persisted_pin(
        self,
    ) -> None:
        group_selection = self._resolve_synthetic_historical_group(
            core_id="frodo",
            group_tag="main-test:universal",
        )
        execution = pipeline.group_execution_spec(
            core_id="frodo",
            catalog_spec=self.catalog["cores"]["frodo"],
            group_selection=group_selection,
        )
        self.assertEqual(
            group_selection["source_commit"],
            execution["source"]["commit"],
        )

        tampered = copy.deepcopy(group_selection)
        tampered["pin"]["file_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "group execution pin identity changed",
        ):
            pipeline.group_execution_spec(
                core_id="frodo",
                catalog_spec=self.catalog["cores"]["frodo"],
                group_selection=tampered,
            )

    def test_swanstation_source_candidate_projection_fails_closed(self) -> None:
        def fixture() -> tuple[dict, dict, dict]:
            catalog_spec, _candidate_spec, group_selection, pin_selection = (
                self._swanstation_candidate_group_fixture()
            )
            return catalog_spec, group_selection, pin_selection

        def execute(
            catalog_spec: dict,
            group_selection: dict,
            pin_selection: dict,
        ) -> dict:
            with self._synthetic_candidate_recipe_authentication():
                return pipeline._group_execution_spec(
                    core_id="swanstation",
                    catalog_spec=catalog_spec,
                    group_selection=group_selection,
                    validated_pin_selection=pin_selection,
                )

        catalog_spec, group_selection, pin_selection = fixture()
        pin_selection.pop("output_reproduction")
        with self.subTest("missing proof"), self.assertRaisesRegex(
            pipeline.PipelineError, "complete and untuned"
        ):
            execute(catalog_spec, group_selection, pin_selection)

        catalog_spec, group_selection, pin_selection = fixture()
        pin_selection["targets"]["arm64"]["golden_record"]["build"][
            "source_date_epoch"
        ] += 1
        with self.subTest("epoch"), self.assertRaisesRegex(
            pipeline.PipelineError, "commit epoch"
        ):
            execute(catalog_spec, group_selection, pin_selection)

        catalog_spec, group_selection, pin_selection = fixture()
        pin_selection["targets"]["arm64"]["golden_record"]["recipe"][
            "core_spec_sha256"
        ] = "0" * 64
        with self.subTest("recipe"), self.assertRaisesRegex(
            pipeline.PipelineError, "recipe differs"
        ):
            execute(catalog_spec, group_selection, pin_selection)

        catalog_spec, group_selection, pin_selection = fixture()
        catalog_spec["workflow"] = ".github/workflows/build-other.yml"
        with self.subTest("candidate recipe"), self.assertRaisesRegex(
            pipeline.PipelineError, "source-candidate provenance"
        ):
            execute(catalog_spec, group_selection, pin_selection)

        catalog_spec, group_selection, pin_selection = fixture()
        group_selection["execution_source"]["tree"] = "f" * 40
        with self.subTest("source"), self.assertRaisesRegex(
            pipeline.PipelineError, "source differs"
        ):
            execute(catalog_spec, group_selection, pin_selection)

        catalog_spec, group_selection, pin_selection = fixture()
        pin_selection["chipset_tuning"] = {"profile": "forbidden"}
        with self.subTest("tuned"), self.assertRaisesRegex(
            pipeline.PipelineError, "complete and untuned"
        ):
            execute(catalog_spec, group_selection, pin_selection)

    def test_swanstation_candidate_passes_the_real_deep_group_worker_boundary(
        self,
    ) -> None:
        local_root = pipeline.ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            fixture = self._write_swanstation_deep_group_fixture(Path(temporary))
            services = pipeline.release_worker_services()
            with (
                mock.patch.object(
                    pipeline,
                    "resolve_core_group_build_selection",
                    return_value=fixture["group"],
                ),
                mock.patch.object(
                    pipeline,
                    "_load_exact_group_pin_selection",
                    return_value=fixture["pin_selection"],
                ),
                mock.patch.object(
                    pipeline,
                    "validate_artifact",
                    return_value=fixture["artifact_validation"],
                ),
                self._synthetic_candidate_recipe_authentication() as authenticate,
            ):
                evidence, _digest, records, package_path, package = (
                    services.validate_group_e2e(
                        fixture["e2e_path"],
                        fixture["record_path"],
                        pipeline.DEFAULT_CATALOG,
                        self.catalog,
                        fixture["group"],
                    )
                )
            self.assertGreater(authenticate.call_count, 0)
            self.assertEqual(
                "5430a4a53b89fa5827c97b84ada29d23317245bc",
                records["arm64"][0]["source"]["resolved_commit"],
            )
            self.assertEqual(
                1784512264,
                records["arm64"][0]["build"]["source_date_epoch"],
            )
            self.assertEqual(fixture["group"], evidence["core_group"])
            self.assertEqual(package["sha256"], pipeline.sha256_file(package_path))

    def test_swanstation_deep_group_catalog_and_projection_drift_fail_closed(
        self,
    ) -> None:
        local_root = pipeline.ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as temporary:
            fixture = self._write_swanstation_deep_group_fixture(Path(temporary))
            base_record = copy.deepcopy(fixture["record"])
            base_e2e = copy.deepcopy(fixture["e2e"])
            execution_catalog = copy.deepcopy(self.catalog)
            execution_catalog["cores"]["swanstation"] = fixture[
                "candidate_spec"
            ]
            legacy_record = copy.deepcopy(base_record)
            legacy_record.pop("core_group")
            legacy_record["recipe"].pop("chipset_tuning")

            with self.subTest("ordinary API"), self.assertRaisesRegex(
                pipeline.PipelineError,
                "catalog differs from canonical disk bytes",
            ):
                pipeline.validate_build_record_identity(
                    legacy_record,
                    fixture["record_path"],
                    pipeline.DEFAULT_CATALOG,
                    execution_catalog,
                )

            drifted_snapshot = copy.deepcopy(self.catalog)
            drifted_snapshot["policy"]["publication"] = "drifted"
            with self.subTest("canonical document"), self.assertRaisesRegex(
                pipeline.PipelineError,
                "catalog changed after it was loaded",
            ):
                pipeline._validate_build_record_identity(
                    legacy_record,
                    fixture["record_path"],
                    pipeline.DEFAULT_CATALOG,
                    execution_catalog,
                    execution_tuning=fixture["tuning"],
                    authenticated_recipe_catalog_snapshot=drifted_snapshot,
                )
            with self.subTest("canonical digest"), self.assertRaisesRegex(
                pipeline.PipelineError,
                "catalog changed after it was loaded",
            ):
                pipeline._validate_build_record_identity(
                    legacy_record,
                    fixture["record_path"],
                    pipeline.DEFAULT_CATALOG,
                    execution_catalog,
                    execution_tuning=fixture["tuning"],
                    expected_catalog_file_sha256="0" * 64,
                    authenticated_recipe_catalog_snapshot=self.catalog,
                )

            def write_changed_record(record: dict) -> None:
                fixture["record_path"].write_text(
                    json.dumps(record, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                e2e = copy.deepcopy(base_e2e)
                e2e["builds"][0]["record_sha256"] = pipeline.sha256_file(
                    fixture["record_path"]
                )
                e2e["content_sha256"] = pipeline.e2e_content_sha256(e2e)
                fixture["e2e_path"].write_text(
                    json.dumps(e2e, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

            mutations = (
                (
                    "canonical recipe SHA",
                    "recipe identity mismatch: catalog_sha256",
                    lambda changed: changed["recipe"].update(
                        {"catalog_sha256": "0" * 64}
                    ),
                ),
                (
                    "projected recipe",
                    "recipe identity mismatch: core_spec_sha256",
                    lambda changed: changed["recipe"].update(
                        {"core_spec_sha256": "0" * 64}
                    ),
                ),
                (
                    "projected source",
                    "group build source identity is invalid",
                    lambda changed: changed["source"].update(
                        {"tree": "0" * 40}
                    ),
                ),
                (
                    "projected epoch",
                    "compile environment does not match",
                    lambda changed: changed["build"].update(
                        {"source_date_epoch": 1782767217}
                    ),
                ),
            )
            services = pipeline.release_worker_services()
            with (
                mock.patch.object(
                    pipeline,
                    "resolve_core_group_build_selection",
                    return_value=fixture["group"],
                ),
                mock.patch.object(
                    pipeline,
                    "_load_exact_group_pin_selection",
                    return_value=fixture["pin_selection"],
                ),
                mock.patch.object(
                    pipeline,
                    "validate_artifact",
                    return_value=fixture["artifact_validation"],
                ),
                self._synthetic_candidate_recipe_authentication(),
            ):
                for label, error, mutate in mutations:
                    changed = copy.deepcopy(base_record)
                    mutate(changed)
                    write_changed_record(changed)
                    with self.subTest(label), self.assertRaisesRegex(
                        pipeline.PipelineError,
                        error,
                    ):
                        services.validate_group_e2e(
                            fixture["e2e_path"],
                            fixture["record_path"],
                            pipeline.DEFAULT_CATALOG,
                            self.catalog,
                            fixture["group"],
                        )

    def test_alternate_source_repository_and_commit_binding_fail_closed(self) -> None:
        spec = self.catalog["cores"]["frodo"]
        source = self._alternate_source(spec)
        with self.subTest("repository"):
            changed = copy.deepcopy(source)
            changed["url"] = "https://example.invalid/not-frodo.git"
            with self.assertRaisesRegex(
                pipeline.PipelineError,
                "source repository differs from the catalog",
            ):
                pipeline.group_execution_spec(
                    core_id="frodo",
                    catalog_spec=spec,
                    group_selection={
                        "execution_source": changed,
                        "source_commit": changed["commit"],
                        "selected_architectures": ["arm64"],
                    },
                )
        with self.subTest("commit"):
            with self.assertRaisesRegex(
                pipeline.PipelineError,
                "source commit is inconsistent",
            ):
                pipeline.group_execution_spec(
                    core_id="frodo",
                    catalog_spec=spec,
                    group_selection={
                        "execution_source": source,
                        "source_commit": "3" * 40,
                        "selected_architectures": ["arm64"],
                    },
                )

    def test_alternate_source_with_source_bound_recipe_fails_closed(self) -> None:
        spec = self.catalog["cores"]["mgba"]
        source = self._alternate_source(spec)
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "changed group source requires authenticated source-candidate provenance",
        ):
            pipeline.group_execution_spec(
                core_id="mgba",
                catalog_spec=spec,
                group_selection={
                    "execution_source": source,
                    "source_commit": source["commit"],
                    "selected_architectures": ["arm64"],
                },
            )

    def test_execution_source_rejects_tree_and_resolver_tampering(self) -> None:
        source = self._alternate_source(self.catalog["cores"]["frodo"])
        malformed_tree = copy.deepcopy(source)
        malformed_tree["tree"] = "2" * 39
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "source identity is malformed",
        ):
            pipeline.validated_group_execution_source(
                malformed_tree,
                label="alternate",
            )

        pinned = {
            **source,
            "resolved_commit": source["commit"],
            "resolved_url": source["url"],
        }
        for field, changed_value in (
            ("resolved_commit", "4" * 40),
            ("resolved_url", "https://example.invalid/tampered.git"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(pinned)
                changed[field] = changed_value
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "source identity is malformed",
                ):
                    pipeline.pinned_group_execution_source(
                        changed,
                        label="alternate pin",
                    )

    def test_execution_source_rejects_submodule_tampering(self) -> None:
        source = self._alternate_source(self.catalog["cores"]["frodo"])
        pinned = {
            **source,
            "resolved_commit": source["commit"],
            "resolved_url": source["url"],
        }
        cases = {
            "dirty-state": [
                {"path": "deps/one", "commit": "5" * 40, "state": "+"}
            ],
            "unsafe-path": [
                {"path": "../escape", "commit": "5" * 40, "state": " "}
            ],
            "bad-commit": [
                {"path": "deps/one", "commit": "5" * 39, "state": " "}
            ],
            "duplicate-path": [
                {"path": "deps/one", "commit": "5" * 40, "state": " "},
                {"path": "deps/one", "commit": "6" * 40, "state": " "},
            ],
        }
        for name, submodules in cases.items():
            with self.subTest(name=name):
                changed = copy.deepcopy(pinned)
                changed["submodules"] = submodules
                with self.assertRaises(pipeline.PipelineError):
                    pipeline.pinned_group_execution_source(
                        changed,
                        label="alternate pin",
                    )

    def test_live_group_source_provenance_is_exact(self) -> None:
        source = self._alternate_source(self.catalog["cores"]["frodo"])
        source["submodules"] = [
            {"path": "deps/one", "commit": "5" * 40}
        ]
        selection = {"execution_source": source}
        observed = {
            "group_selection": selection,
            "recorded_commit": source["commit"],
            "recorded_tree": source["tree"],
            "recorded_url": source["url"],
            "recorded_submodules": [
                {"path": "deps/one", "commit": "5" * 40, "state": " "}
            ],
            "raw_submodule_line_count": 1,
            "label": "alternate",
        }
        self.assertTrue(pipeline.group_source_provenance_matches(**observed))
        cases = {
            "commit": {"recorded_commit": "6" * 40},
            "tree": {"recorded_tree": "7" * 40},
            "repository": {
                "recorded_url": "https://example.invalid/tampered.git"
            },
            "submodule": {
                "recorded_submodules": [
                    {"path": "deps/one", "commit": "8" * 40, "state": " "}
                ]
            },
            "submodule-state": {
                "recorded_submodules": [
                    {"path": "deps/one", "commit": "5" * 40, "state": "+"}
                ]
            },
            "unparsed-line": {"raw_submodule_line_count": 2},
        }
        for name, changes in cases.items():
            with self.subTest(name=name):
                tampered = {**observed, **changes}
                self.assertFalse(
                    pipeline.group_source_provenance_matches(**tampered)
                )

    def test_perform_build_rejects_unproven_selected_source_before_preflight(self) -> None:
        selection = self._resolve_synthetic_historical_group(
            core_id="frodo",
            group_tag="main-test:universal",
        )
        source = self._alternate_source(self.catalog["cores"]["frodo"])
        selection["execution_source"] = source
        selection["source_commit"] = source["commit"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "must-not-exist"
            with mock.patch.object(
                pipeline,
                "require_source_commits_eligible",
                side_effect=pipeline.PipelineError("stop after source preflight"),
            ) as eligibility:
                with self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "changed group source requires authenticated source-candidate provenance",
                ):
                    pipeline.perform_build(
                        catalog_path=pipeline.DEFAULT_CATALOG,
                        catalog=self.catalog,
                        core_id="frodo",
                        arch="arm64",
                        output_dir=output,
                        group_selection=selection,
                    )
            eligibility.assert_not_called()
            self.assertFalse(output.exists())

    def test_catalog_definitions_and_typed_tuning_share_one_export(self) -> None:
        spec = self.catalog["cores"]["neocd"]
        shell = pipeline.compile_definition_shell(
            spec,
            "armhf",
            "a33-cortex-a7-v1",
        )
        for definition in pipeline.compile_definitions_for_target(spec, "armhf"):
            self.assertIn(f"-D{definition}", shell)
        for argument in ("-mcpu=cortex-a7", "-mfpu=neon-vfpv4", "-mfloat-abi=hard"):
            self.assertIn(argument, shell)
        self.assertEqual(1, shell.count("export CFLAGS="))
        self.assertEqual(1, shell.count("export CXXFLAGS="))

    def test_tuned_compile_log_requires_exact_machine_arguments(self) -> None:
        tuning = pipeline.execution_tuning_profile("a33-cortex-a7-v1", "armhf")
        assert tuning is not None
        marker = shlex.split(pipeline.chipset_tuning_marker_shell(tuning))[-1]
        compiler = sorted(pipeline.TARGET_COMPILERS["armhf"])[0]
        arguments = " ".join(tuning["compiler_arguments"])
        valid = f"{marker}\n{compiler} {arguments} -c source.c -o source.o\n"
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(valid, tuning, "armhf")
        )
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                valid.replace(" -c ", " -mcpu=cortex-a35 -c "),
                tuning,
                "armhf",
            )
        )
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                valid.replace("-mfpu=neon-vfpv4 ", ""),
                tuning,
                "armhf",
            )
        )

    def test_universal_compile_log_allows_only_exact_architecture_baselines(
        self,
    ) -> None:
        tuning = pipeline.execution_tuning_profile("universal-v1", "arm64")
        assert tuning is not None
        self.assertEqual("any", tuning["architecture"])
        self.assertEqual([], tuning["compiler_arguments"])
        marker = shlex.split(pipeline.chipset_tuning_marker_shell(tuning))[-1]
        compiler = sorted(pipeline.TARGET_COMPILERS["arm64"])[0]
        valid = f"{marker}\n{compiler} -O2 -c source.c -o source.o\n"
        cmake_valid = (
            f"{marker}\n-- Check for working C compiler: "
            f"/opt/toolchain/bin/{compiler} - skipped\n"
            f"cd /tmp/build && /opt/toolchain/bin/{compiler} "
            "-O2 -c source.c -o source.o\n"
        )

        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(valid, tuning, "arm64")
        )
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(
                cmake_valid, tuning, "arm64"
            )
        )
        arm64_baseline = valid.replace(" -c ", " -march=armv8-a -c ")
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(
                arm64_baseline, tuning, "arm64"
            )
        )
        projected = pipeline.core_contract_log_without_tuning_arguments(
            cmake_valid,
            tuning,
            "arm64",
        )
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertNotIn("CORE_PIPELINE_CHIPSET_TUNING|", projected)
        self.assertIn(f"{compiler} -O2 -c source.c -o source.o", projected)
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                valid.replace(" -c ", " -mcpu=cortex-a55 -c "),
                tuning,
                "arm64",
            )
        )
        for argument in (
            "-march=armv8-a+crc",
            "-march=armv9-a",
            "-mtune=cortex-a53",
            "-mfpu=neon-vfpv4",
            "-mfloat-abi=hard",
        ):
            with self.subTest(argument=argument):
                self.assertFalse(
                    pipeline.chipset_tuning_log_proves_contract(
                        valid.replace(" -c ", f" {argument} -c "),
                        tuning,
                        "arm64",
                    )
                )
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                arm64_baseline.replace(
                    " -c ", " -march=armv8-a -c "
                ),
                tuning,
                "arm64",
            )
        )
        for link_line in (
            f"{compiler} -flto -mcpu=cortex-a55 input.o -o core.so",
            (
                f"cd /tmp/build && /opt/toolchain/bin/{compiler} "
                "-flto -mcpu=cortex-a55 input.o -o core.so"
            ),
            (
                f"{compiler} -march=armv8-a -march=armv8-a "
                "input.o -o core.so"
            ),
        ):
            with self.subTest(link_line=link_line):
                self.assertFalse(
                    pipeline.chipset_tuning_log_proves_contract(
                        f"{valid}{link_line}\n",
                        tuning,
                        "arm64",
                    )
                )
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                f"{marker}\nno target compiler invocation\n",
                tuning,
                "arm64",
            )
        )
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(
                f"{marker}\nno target compiler invocation\n",
                tuning,
                "arm64",
                allow_no_target_compile=True,
            )
        )

    def test_universal_armhf_accepts_only_hard_float_abi_baseline(self) -> None:
        tuning = pipeline.execution_tuning_profile("universal-v1", "armhf")
        assert tuning is not None
        marker = shlex.split(pipeline.chipset_tuning_marker_shell(tuning))[-1]
        compiler = sorted(pipeline.TARGET_COMPILERS["armhf"])[0]
        hard_float = (
            f"{marker}\n{compiler} -march=armv7-a -mfloat-abi=hard "
            "-O2 -c source.c -o source.o\n"
        )
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(
                hard_float, tuning, "armhf"
            )
        )
        projected = pipeline.core_contract_log_without_tuning_arguments(
            hard_float,
            tuning,
            "armhf",
        )
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertNotIn("CORE_PIPELINE_CHIPSET_TUNING|", projected)
        self.assertIn("-march=armv7-a -mfloat-abi=hard", projected)

        assembly_compiler = next(
            iter(
                pipeline.TARGET_COMPILERS["armhf"]
                - pipeline.TARGET_CXX_COMPILERS["armhf"]
            )
        )
        assembly_hard_float = (
            f"{marker}\n{assembly_compiler} -mfloat-abi=hard "
            "-march=armv7-a "
            "-mfloat-abi=hard -O2 -c -o bios_data.o bios_data.S\n"
        )
        self.assertTrue(
            pipeline.chipset_tuning_log_proves_contract(
                assembly_hard_float,
                tuning,
                "armhf",
            )
        )
        assembly_projected = (
            pipeline.core_contract_log_without_tuning_arguments(
                assembly_hard_float,
                tuning,
                "armhf",
            )
        )
        self.assertIsNotNone(assembly_projected)
        assert assembly_projected is not None
        self.assertEqual(2, assembly_projected.count("-mfloat-abi=hard"))

        for argument in (
            "-march=armv7-a+simd",
            "-march=armv8-a",
            "-mcpu=cortex-a7",
            "-mtune=cortex-a7",
            "-mfpu=neon-vfpv4",
            "-mfloat-abi=soft",
            "-mfloat-abi=softfp",
        ):
            with self.subTest(argument=argument):
                self.assertFalse(
                    pipeline.chipset_tuning_log_proves_contract(
                        hard_float.replace(" -O2 ", f" {argument} -O2 "),
                        tuning,
                        "armhf",
                    )
                )
        for duplicate in ("-march=armv7-a", "-mfloat-abi=hard"):
            with self.subTest(duplicate=duplicate):
                self.assertFalse(
                    pipeline.chipset_tuning_log_proves_contract(
                        hard_float.replace(" -O2 ", f" {duplicate} -O2 "),
                        tuning,
                        "armhf",
                    )
                )
        cxx = sorted(pipeline.TARGET_CXX_COMPILERS["armhf"])[0]
        cxx_duplicate = hard_float.replace(compiler, cxx).replace(
            " -O2 ", " -mfloat-abi=hard -O2 "
        ).replace("source.c", "source.cc")
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                cxx_duplicate,
                tuning,
                "armhf",
            )
        )
        for assembly_mutation in (
            assembly_hard_float.replace(
                " -O2 ", " -mfloat-abi=hard -O2 "
            ),
            assembly_hard_float.replace(
                " -O2 ", " -mfloat-abi=soft -O2 "
            ),
            assembly_hard_float.replace(
                " -O2 ", " -mfloat-abi=softfp -O2 "
            ),
            assembly_hard_float.replace(
                "-c -o bios_data.o bios_data.S",
                "-include forced.S -c -o source.o source.c",
            ),
            assembly_hard_float.replace(" -o bios_data.o", ""),
        ):
            self.assertFalse(
                pipeline.chipset_tuning_log_proves_contract(
                    assembly_mutation,
                    tuning,
                    "armhf",
                )
            )
        self.assertFalse(
            pipeline.chipset_tuning_log_proves_contract(
                hard_float.replace(" -c ", " @flags.rsp -c "),
                tuning,
                "armhf",
            )
        )

    def test_tuned_direct_cargo_fails_closed(self) -> None:
        spec = self.catalog["cores"]["libgametank"]
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "chipset-tuned direct-cargo execution is unsupported",
        ):
            pipeline.container_build_script(
                "libgametank",
                "arm64",
                spec,
                self.catalog["resolver"],
                "a523-cortex-a55-v1",
            )

    @staticmethod
    def _group_expectations() -> dict:
        return {
            "expected_outputs": {
                "targets": {
                    "arm64": {
                        "artifact": {"sha256": "a" * 64, "size": 41}
                    }
                },
                "metadata": {"sha256": "b" * 64, "size": 17},
            }
        }

    def test_selected_pin_artifact_mismatch_fails_build_validation(self) -> None:
        artifact = {"status": "valid", "sha256": "c" * 64, "size": 41}
        metadata = {"status": "valid", "sha256": "b" * 64, "size": 17}
        pipeline.apply_group_output_expectations(
            artifact_validation=artifact,
            metadata_validation=metadata,
            group_selection=self._group_expectations(),
            arch="arm64",
        )
        self.assertEqual("invalid", artifact["status"])
        self.assertIn("selected core group pin", artifact["errors"][0])
        self.assertEqual("valid", metadata["status"])

    def test_selected_pin_metadata_mismatch_fails_build_validation(self) -> None:
        artifact = {"status": "valid", "sha256": "a" * 64, "size": 41}
        metadata = {"status": "valid", "sha256": "d" * 64, "size": 17}
        pipeline.apply_group_output_expectations(
            artifact_validation=artifact,
            metadata_validation=metadata,
            group_selection=self._group_expectations(),
            arch="arm64",
        )
        self.assertEqual("valid", artifact["status"])
        self.assertEqual("invalid", metadata["status"])
        self.assertIn("selected core group pin", metadata["errors"][0])

    def _package_fixture(self, run_root: Path) -> tuple[list[dict], dict]:
        core_root = run_root / "demo" / "arm64"
        core_root.mkdir(parents=True)
        artifact = b"artifact-bytes"
        metadata = b"metadata-bytes"
        (core_root / "demo_libretro.so").write_bytes(artifact)
        (core_root / "demo_libretro.info").write_bytes(metadata)
        records = [
            {
                "core_id": "demo",
                "architecture": "arm64",
                "result": "passed",
                "artifact": {
                    "path": "demo_libretro.so",
                    "sha256": pipeline.sha256_bytes(artifact),
                },
                "metadata": {
                    "path": "demo_libretro.info",
                    "status": "valid",
                    "sha256": pipeline.sha256_bytes(metadata),
                },
                "source": {"resolved_commit": "1" * 40},
                "toolchain": {"resolved_image_id": "sha256:" + "2" * 64},
            }
        ]
        spec = {
            "targets": ["arm64"],
            "build": {"artifact_name": "demo_libretro.so"},
            "metadata": {"artifact_name": "demo_libretro.info"},
        }
        return records, spec

    def test_full_scope_group_package_compares_exact_pin_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            records, spec = self._package_fixture(run_root)
            group = {
                "selected_architectures": ["arm64"],
                "variant_id": "3" * 64,
                "expected_outputs": {
                    "package": {
                        "comparison": "exact",
                        "name": "demo_libretro.zip",
                        "sha256": "4" * 64,
                        "size": 1,
                    }
                },
            }
            result = pipeline.package_e2e_core(
                run_root, "demo", records, spec, group
            )
            self.assertEqual("not_packaged", result["result"])
            self.assertIn("selected core group pin", result["reason"])

    def test_full_scope_group_package_accepts_exact_pin_hash(self) -> None:
        with tempfile.TemporaryDirectory() as baseline_directory:
            baseline_root = Path(baseline_directory)
            baseline_records, spec = self._package_fixture(baseline_root)
            baseline = pipeline.package_e2e_core(
                baseline_root,
                "demo",
                baseline_records,
                spec,
            )
        with tempfile.TemporaryDirectory() as reproduction_directory:
            reproduction_root = Path(reproduction_directory)
            records, spec = self._package_fixture(reproduction_root)
            group = {
                "selected_architectures": ["arm64"],
                "variant_id": "3" * 64,
                "expected_outputs": {
                    "package": {
                        "comparison": "exact",
                        "name": baseline["path"],
                        "sha256": baseline["sha256"],
                        "size": baseline["size"],
                    }
                },
            }
            result = pipeline.package_e2e_core(
                reproduction_root,
                "demo",
                records,
                spec,
                group,
            )
            self.assertEqual("packaged", result["result"])
            self.assertEqual(baseline["sha256"], result["sha256"])

    def test_projected_group_package_marks_pin_package_comparison_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory)
            records, spec = self._package_fixture(run_root)
            group = {
                "selected_architectures": ["arm64"],
                "variant_id": "3" * 64,
                "expected_outputs": {
                    "package": {
                        "comparison": "not_applicable_projected_architectures",
                        "name": "demo_libretro.zip",
                        "sha256": "4" * 64,
                        "size": 1,
                    }
                },
            }
            result = pipeline.package_e2e_core(
                run_root, "demo", records, spec, group
            )
            self.assertEqual("packaged", result["result"])
            self.assertEqual(
                "not_applicable_projected_architectures",
                result["core_group"]["comparison"],
            )

    def test_group_preflight_failure_creates_no_run_root(self) -> None:
        local_root = ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            output_root = Path(directory) / "runs"
            args = argparse.Namespace(
                catalog=pipeline.DEFAULT_CATALOG,
                runner_profile="local",
                core="mgba",
                group_tag="edge-test:a523",
                arch=None,
                run_id="must-not-exist",
                output_root=output_root,
                fail_fast=False,
            )
            with mock.patch.object(
                pipeline,
                "resolve_core_group_build_selection",
                side_effect=pipeline.PipelineError("unsupported historical recipe"),
            ):
                with self.assertRaisesRegex(
                    pipeline.PipelineError, "unsupported historical recipe"
                ):
                    pipeline.cmd_e2e(args)
            self.assertFalse(output_root.exists())

    def test_e2e_digest_binds_exact_group_evidence(self) -> None:
        document = {
            "schema_version": 2,
            "run_id": "group-evidence",
            "local_only": True,
            "publication": "disabled",
            "runner": {},
            "result": "passed",
            "workflow_audit": {},
            "builds": [],
            "packages": [],
            "core_group": {"group_tag": "main-test:a523", "variant_id": "5" * 64},
        }
        digest = pipeline.e2e_content_sha256(document)
        changed = copy.deepcopy(document)
        changed["core_group"]["variant_id"] = "6" * 64
        self.assertNotEqual(digest, pipeline.e2e_content_sha256(changed))

    def test_group_release_validator_rejects_projected_package_scope(self) -> None:
        selection = self._resolve_synthetic_historical_group(
            core_id="mgba",
            group_tag="main-test:a523",
        )
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "requires exact full-package comparison",
        ):
            pipeline.validate_group_e2e_evidence(
                ROOT / ".local-e2e" / "runs" / "absent" / "e2e-record.json",
                ROOT
                / ".local-e2e"
                / "runs"
                / "absent"
                / "mgba"
                / "arm64"
                / "build-record.json",
                pipeline.DEFAULT_CATALOG,
                self.catalog,
                selection,
            )

    def test_group_build_records_are_not_accepted_by_existing_promotion(self) -> None:
        record = {
            "schema_version": 2,
            "local_only": True,
            "publication": "disabled",
            "result": "passed",
            "build_exit_code": 0,
            "core_group": {"group_tag": "main-test:a523"},
        }
        record_path = ROOT / ".local-e2e" / "runs" / "group" / "build-record.json"
        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "not supported by golden, pin, or release promotion",
        ):
            pipeline.validate_build_record_identity(
                record,
                record_path,
                pipeline.DEFAULT_CATALOG,
                self.catalog,
            )


if __name__ == "__main__":
    unittest.main()
