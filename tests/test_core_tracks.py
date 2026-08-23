from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

from .cores import support as core_test_support
from .cores.support import load_live_authoritative_core_pin_index, pipeline
from scripts.core_pipeline_lib import tracks as track_model
from scripts.core_pipeline_lib.chipsets import (
    CHIPSETS,
    COMPILER_ARGUMENT_MAPPING_VERSION,
    UNIVERSAL_TUNING_PROFILE,
    chipset_tuning_errors,
    chipset_tunings_content_sha256,
    compiler_arguments_for_profile,
    resolved_tuning_profile,
    validate_chipset_tunings,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib import spruce_branch_bases as branch_basis_model
from scripts.core_pipeline_lib.tracks import (
    MAX_STABLE_PROVENANCE_DEPTH,
    construct_core_track_inventory,
    core_track_inventory_content_sha256,
    core_track_source_snapshot,
    core_tracks_content_sha256,
    core_variant_id,
    load_core_pin_index,
    load_core_track_source_registry_index,
    local_git_source_ancestry_verifier,
    plan_core_track_test,
    promote_core_track_test,
    resolve_core_track_cell,
    set_core_track_test,
    spruce_release_roster_content_sha256,
    spruce_release_roster_errors,
    validate_core_tracks,
)


ROOT = Path(__file__).resolve().parents[1]
_ORIGINAL_EDGE_LATEST_ERRORS = track_model._edge_latest_errors


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _semantic_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _rehash_tunings(document: dict) -> dict:
    document["content_sha256"] = chipset_tunings_content_sha256(document)
    return document


def _rehash_tracks(document: dict) -> dict:
    document["content_sha256"] = core_tracks_content_sha256(document)
    return document


def _rehash_pin(document: dict) -> dict:
    document["content_sha256"] = _semantic_sha256(
        {
            key: document.get(key)
            for key in (
                "schema_version",
                "pin_id",
                "local_only",
                "publication",
                "scope",
                "parent",
                "sources",
                "selection_policy",
                "cores",
                "summary",
            )
        }
    )
    return document


class CoreTrackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.live_catalog = _read_json(ROOT / "manifests/core-builds.json")
        cls.live_tunings = _read_json(ROOT / "manifests/chipset-tunings.json")
        cls.live_tracks = _read_json(ROOT / "manifests/core-tracks.json")
        cls.live_release_roster = _read_json(
            ROOT / "manifests/spruce-release-roster.json"
        )
        cls.live_branch_bases = _read_json(
            ROOT / "manifests/spruce-core-branch-bases.json"
        )
        cls.live_pins = load_live_authoritative_core_pin_index(
            repository_root=ROOT,
            loader=pipeline.load_authoritative_core_pin_index,
        )
        cls.live_source_registries = load_core_track_source_registry_index(ROOT)

    def setUp(self) -> None:
        self._basis_errors_patcher = mock.patch(
            "scripts.core_pipeline_lib.spruce_branch_bases."
            "spruce_branch_bases_errors",
            return_value=[],
        )
        self._detached_basis_errors_patcher = mock.patch(
            "scripts.core_pipeline_lib.spruce_branch_bases."
            "spruce_branch_bases_detached_snapshot_errors",
            return_value=[],
        )
        self._edge_latest_errors_patcher = mock.patch.object(
            track_model, "_edge_latest_errors", return_value=[]
        )
        self._basis_errors_patcher.start()
        self._detached_basis_errors_patcher.start()
        self._edge_latest_errors_patcher.start()
        self.addCleanup(self._basis_errors_patcher.stop)
        self.addCleanup(self._detached_basis_errors_patcher.stop)
        self.addCleanup(self._edge_latest_errors_patcher.stop)
        self.source_registry_index: dict[str, dict] = {}
        self.catalog = {
            "cores": {
                "alpha": {
                    "source": {
                        "url": "https://example.invalid/alpha.git",
                        "requested_ref": "refs/heads/main",
                    }
                }
            }
        }
        self.release_roster = self._release_roster(["alpha"])
        self.branch_bases = {
            "content_sha256": "",
            "bases": {
                "spruce-main": {
                    "basis_id": "spruce-main",
                    "content_sha256": "1" * 64,
                    "branch": {
                        "repository": "https://example.invalid/spruce.git",
                        "ref": "refs/heads/main",
                        "commit": "1" * 40,
                        "tree": "2" * 40,
                    },
                },
                "spruce-development": {
                    "basis_id": "spruce-development",
                    "content_sha256": "2" * 64,
                    "branch": {
                        "repository": "https://example.invalid/spruce.git",
                        "ref": "refs/heads/Development",
                        "commit": "3" * 40,
                        "tree": "4" * 40,
                    },
                },
            },
        }
        self.branch_bases["content_sha256"] = _semantic_sha256(
            {"bases": self.branch_bases["bases"]}
        )
        self.tunings = copy.deepcopy(self.live_tunings)
        self.tunings["profiles"]["h700-cortex-a53-v1"] = {
            "extends": UNIVERSAL_TUNING_PROFILE,
            "chipset": "h700",
            "architecture": "arm64",
            "properties": {"cpu_target": "cortex-a53"},
        }
        self.tunings["profiles"] = dict(sorted(self.tunings["profiles"].items()))
        _rehash_tunings(self.tunings)

        h700_tuning = resolved_tuning_profile(
            self.tunings, "h700-cortex-a53-v1"
        )
        self.pin_index = {
            "alpha-universal": self._pin("alpha-universal", "1", None),
            "alpha-h700": self._pin(
                "alpha-h700",
                "2",
                {
                    "profile_id": h700_tuning["profile_id"],
                    "content_sha256": h700_tuning["content_sha256"],
                },
            ),
        }
        self.universal_cell = {
            "build_pin_id": "alpha-universal",
            "tuning_profile": UNIVERSAL_TUNING_PROFILE,
            "applicable_chipsets": ["h700", "rk3566"],
        }
        self.h700_cell = {
            "build_pin_id": "alpha-h700",
            "tuning_profile": "h700-cortex-a53-v1",
            "applicable_chipsets": ["h700"],
        }

    def test_live_registry_validates_with_unmocked_comparison_and_edge_policy(self) -> None:
        """Walk every live dependency through the real policy adapters."""

        cached_loader = mock.Mock(
            side_effect=AssertionError("same-root cache reuse called the loader")
        )
        detached_pins = load_live_authoritative_core_pin_index(
            repository_root=ROOT,
            loader=cached_loader,
        )
        cached_loader.assert_not_called()
        self.assertEqual(self.live_pins, detached_pins)
        self.assertIsNot(self.live_pins, detached_pins)
        first_pin_id = next(iter(detached_pins))
        detached_pins[first_pin_id]["path"] = "tampered-test-copy.json"
        self.assertNotEqual(self.live_pins, detached_pins)
        self.assertEqual(
            self.live_pins,
            load_live_authoritative_core_pin_index(
                repository_root=ROOT,
                loader=cached_loader,
            ),
        )
        with self.assertRaisesRegex(
            ValueError, "bound to a different repository root"
        ):
            load_live_authoritative_core_pin_index(
                repository_root=ROOT.parent,
                loader=cached_loader,
            )
        cached_loader.assert_not_called()

        with (
            mock.patch.object(
                core_test_support, "_LIVE_AUTHORITY_CACHE_ROOT", None
            ),
            mock.patch.object(core_test_support, "_LIVE_AUTHORITY_CACHE", None),
        ):
            failing_loader = mock.Mock(
                side_effect=RuntimeError("synthetic authority load failure")
            )
            with self.assertRaisesRegex(RuntimeError, "synthetic authority"):
                load_live_authoritative_core_pin_index(
                    repository_root=ROOT,
                    loader=failing_loader,
                )
            self.assertIsNone(core_test_support._LIVE_AUTHORITY_CACHE_ROOT)
            self.assertIsNone(core_test_support._LIVE_AUTHORITY_CACHE)

            loader_call_count = 0
            loader_call_lock = threading.Lock()
            concurrent_loader_entry = threading.Event()
            concurrent_source = {"synthetic-pin": {"path": "synthetic-pin.json"}}

            def slow_loader() -> dict[str, dict[str, str]]:
                nonlocal loader_call_count
                with loader_call_lock:
                    loader_call_count += 1
                    if loader_call_count == 2:
                        concurrent_loader_entry.set()
                concurrent_loader_entry.wait(timeout=0.2)
                return concurrent_source

            worker_start = threading.Barrier(3)
            worker_results: list[dict[str, dict[str, object]]] = []
            worker_errors: list[BaseException] = []

            def load_worker() -> None:
                worker_start.wait()
                try:
                    worker_results.append(
                        load_live_authoritative_core_pin_index(
                            repository_root=ROOT,
                            loader=slow_loader,
                        )
                    )
                except BaseException as exc:
                    worker_errors.append(exc)

            workers = [threading.Thread(target=load_worker) for _ in range(2)]
            for worker in workers:
                worker.start()
            worker_start.wait()
            for worker in workers:
                worker.join(timeout=5)
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual([], worker_errors)
            self.assertEqual(1, loader_call_count)
            self.assertEqual([concurrent_source, concurrent_source], worker_results)
            self.assertIsNot(worker_results[0], worker_results[1])

        self._edge_latest_errors_patcher.stop()
        self._basis_errors_patcher.stop()
        try:
            validated = validate_core_tracks(
                self.live_tracks,
                catalog=self.live_catalog,
                pin_index=self.live_pins,
                tunings=self.live_tunings,
                main_release_roster=self.live_release_roster,
                spruce_branch_bases=self.live_branch_bases,
                source_registry_index=self.live_source_registries,
            )
        finally:
            self._basis_errors_patcher.start()
            self._edge_latest_errors_patcher.start()
        self.assertEqual(
            "98eae53abc7fc347f45600cce1c0c25d3bab6db19584115d1b1c4dc0ede8a5d4",
            validated["content_sha256"],
        )

    def test_historical_slice_basis_is_reviewed_detached_and_durable(self) -> None:
        catalog_file_sha256 = hashlib.sha256(
            (ROOT / "manifests/core-builds.json").read_bytes()
        ).hexdigest()
        roster_file_sha256 = hashlib.sha256(
            (ROOT / "manifests/spruce-release-roster.json").read_bytes()
        ).hexdigest()
        old_snapshot = track_model._slice_branch_basis_snapshot(
            spruce_branch_bases=self.live_branch_bases,
            catalog=self.live_catalog,
            main_release_roster=self.live_release_roster,
            catalog_file_sha256=catalog_file_sha256,
            release_roster_file_sha256=roster_file_sha256,
        )

        self._detached_basis_errors_patcher.stop()
        try:
            self.assertEqual(
                [],
                track_model._slice_branch_basis_snapshot_errors(
                    old_snapshot,
                    registry_digest=self.live_branch_bases["content_sha256"],
                    label="old_snapshot",
                ),
            )
            frozen_roster_mutations = (
                ("schema", "$schema", "./forged-roster.schema.json"),
                ("extra", "forged_review", True),
            )
            for mutation, field, value in frozen_roster_mutations:
                with self.subTest(frozen_roster_mutation=mutation):
                    tampered_snapshot = copy.deepcopy(old_snapshot)
                    tampered_snapshot["release_roster"][field] = value
                    tampered_snapshot["content_sha256"] = (
                        track_model.slice_branch_basis_snapshot_content_sha256(
                            tampered_snapshot
                        )
                    )
                    tampered_errors = (
                        track_model._slice_branch_basis_snapshot_errors(
                            tampered_snapshot,
                            registry_digest=self.live_branch_bases[
                                "content_sha256"
                            ],
                            label="tampered_roster_snapshot",
                        )
                    )
                    self.assertTrue(
                        any(
                            "frozen Spruce release roster" in error
                            for error in tampered_errors
                        ),
                        tampered_errors,
                    )

            forged_bases = copy.deepcopy(self.live_branch_bases)
            forged_main = forged_bases["bases"]["spruce-main"]
            forged_main["branch"]["commit"] = "f" * 40
            forged_main["content_sha256"] = (
                branch_basis_model.spruce_branch_basis_content_sha256(
                    forged_main
                )
            )
            forged_bases["content_sha256"] = (
                branch_basis_model.spruce_branch_bases_content_sha256(
                    forged_bases
                )
            )
            forged_snapshot = track_model._slice_branch_basis_snapshot(
                spruce_branch_bases=forged_bases,
                catalog=self.live_catalog,
                main_release_roster=self.live_release_roster,
                catalog_file_sha256=catalog_file_sha256,
                release_roster_file_sha256=roster_file_sha256,
            )
            forged_errors = track_model._slice_branch_basis_snapshot_errors(
                forged_snapshot,
                registry_digest=forged_bases["content_sha256"],
                label="forged_snapshot",
            )
            self.assertTrue(
                any("append-only reviewed registry" in error for error in forged_errors),
                forged_errors,
            )

            old_slice, old_comparison = track_model.core_track_version_slice(
                track="main",
                slice_time="2026-08-10T10:00:00Z",
                spruce_branch_bases=self.live_branch_bases,
            )
            parent_cell = {
                **self.universal_cell,
                "version_slice": old_slice,
            }
            source = self._track_document()
            source["tracks"]["main"]["test"] = {
                "alpha": {"universal": copy.deepcopy(parent_cell)}
            }
            source["tracks"]["main"]["deferred"] = {}
            source["version_policy"]["slice_comparison_bases"] = {
                old_slice["content_sha256"]: old_comparison
            }
            source["version_policy"]["slice_branch_basis_snapshots"] = {
                self.live_branch_bases["content_sha256"]: old_snapshot
            }
            _rehash_tracks(source)

            advanced_bases = copy.deepcopy(self.live_branch_bases)
            advanced_main = advanced_bases["bases"]["spruce-main"]
            advanced_main["branch"]["commit"] = "e" * 40
            advanced_main["content_sha256"] = (
                branch_basis_model.spruce_branch_basis_content_sha256(
                    advanced_main
                )
            )
            advanced_bases["content_sha256"] = (
                branch_basis_model.spruce_branch_bases_content_sha256(
                    advanced_bases
                )
            )
            advanced_catalog = copy.deepcopy(self.live_catalog)
            advanced_catalog["future_review_marker"] = True
            advanced_roster = copy.deepcopy(self.live_release_roster)
            advanced_roster["release"]["version"] = "4.4.0"
            self.assertNotEqual(old_snapshot["catalog"], advanced_catalog)
            self.assertNotEqual(old_snapshot["release_roster"], advanced_roster)
            self.assertEqual(
                [],
                track_model._version_slice_registry_errors(
                    source,
                    spruce_branch_bases=advanced_bases,
                    canonical_basis_authenticated=True,
                ),
            )

            child_slice, _child_comparison = (
                track_model.core_track_version_slice(
                    track="nightly",
                    slice_time="2026-08-10T11:00:00Z",
                    spruce_branch_bases=self.live_branch_bases,
                )
            )
            child_cell = {**self.h700_cell, "version_slice": child_slice}
            parent_variant = core_variant_id(
                core_id="alpha",
                cell_chipset="universal",
                cell=parent_cell,
                pin_index=self.pin_index,
                tunings=self.tunings,
            )
            child_variant = core_variant_id(
                core_id="alpha",
                cell_chipset="h700",
                cell=child_cell,
                pin_index=self.pin_index,
                tunings=self.tunings,
            )
            binding = track_model._source_order_parent_binding(
                source_registry_content_sha256=source["content_sha256"],
                track="nightly",
                core_id="alpha",
                chipset="h700",
                parent_origin_track="main",
                parent_selected_chipset="universal",
                parent_cell=parent_cell,
                parent_pin=self.pin_index["alpha-universal"],
                parent_variant=parent_variant,
                parent_lineage=None,
                child_cell=child_cell,
                child_pin=self.pin_index["alpha-h700"],
                child_variant=child_variant,
            )
            _digest, source_entry = track_model._snapshot_index_entry(
                repository_root=ROOT,
                snapshot=core_track_source_snapshot(source),
            )
            self.assertEqual(
                [],
                track_model._captured_parent_selection_errors(
                    binding,
                    source_registry_index={source["content_sha256"]: source_entry},
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                    label="frozen_parent",
                ),
            )
        finally:
            self._detached_basis_errors_patcher.start()

    @staticmethod
    def _pin(pin_id: str, identity_digit: str, tuning_identity: dict | None) -> dict:
        return {
            "path": f"pins/core-sets/{pin_id}.json",
            "pin_id": pin_id,
            "file_sha256": identity_digit * 64,
            "content_sha256": identity_digit * 64,
            "core_id": "alpha",
            "architectures": ["arm64"],
            "artifact_sha256": {"arm64": identity_digit * 64},
            "source_commit": "a" * 40,
            "source_repository": "https://example.invalid/alpha.git",
            "source_requested_ref": "refs/heads/main",
            "source_tree": "b" * 40,
            "tuning_identity": copy.deepcopy(tuning_identity),
            "host_reproduction_content_sha256": identity_digit * 64,
        }

    @staticmethod
    def _release_roster(core_ids: list[str]) -> dict:
        document = {
            "$schema": "./spruce-release-roster.schema.json",
            "schema_version": 1,
            "roster_model": "spruce-release-git-tree-v1",
            "correlation_model": "logical-core-name-correlation-only-v1",
            "release": {
                "repository": "https://github.com/spruceUI/spruceOS.git",
                "ref": "refs/tags/v4.3.0",
                "version": "4.3.0",
                "commit": "a" * 40,
                "tree": "b" * 40,
            },
            "cataloged_core_ids": sorted(core_ids),
            "alias_core_ids": {},
            "uncataloged_core_ids": [],
            "content_sha256": "",
        }
        document["content_sha256"] = spruce_release_roster_content_sha256(document)
        return document

    @staticmethod
    def _pin_document() -> dict:
        targets = {
            architecture: {
                "artifact": {
                    "sha256": "1" * 64,
                },
                "golden_record": {
                    "source": {
                        "requested_ref": "refs/heads/main",
                        "resolved_commit": "a" * 40,
                        "resolved_url": "https://example.invalid/alpha.git",
                        "tree": "b" * 40,
                    },
                    "recipe": {},
                }
            }
            for architecture in ("arm64", "armhf")
        }
        return _rehash_pin(
            {
                "schema_version": 1,
                "pin_id": "alpha-pin",
                "local_only": True,
                "publication": "disabled",
                "scope": ["alpha"],
                "parent": None,
                "sources": [],
                "selection_policy": {},
                "cores": {"alpha": {"selection": {"targets": targets}}},
                "summary": {"core_count": 1},
                "content_sha256": "",
            }
        )

    @staticmethod
    def _write_pin_fixture(root: Path, document: object) -> None:
        pin_root = root / "pins" / "core-sets"
        pin_root.mkdir(parents=True)
        (pin_root / "alpha-pin.json").write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _core_cells(cells: dict[str, dict] | None) -> dict:
        if not cells:
            return {}
        return {"alpha": {key: copy.deepcopy(cells[key]) for key in sorted(cells)}}

    @staticmethod
    def _slice_time(track: str) -> str:
        return {
            "main": "2026-08-10T10:00:00Z",
            "nightly": "2026-08-10T11:00:00Z",
            "edge": "2026-08-10T12:00:00Z",
        }[track]

    def _versioned_cell(
        self,
        cell: dict,
        *,
        track: str,
        slice_time: str | None = None,
    ) -> tuple[dict, dict]:
        selected = copy.deepcopy(cell)
        version_slice, comparison_basis = track_model.core_track_version_slice(
            track=track,
            slice_time=slice_time or self._slice_time(track),
            spruce_branch_bases=self.branch_bases,
        )
        selected["version_slice"] = version_slice
        return selected, comparison_basis

    def _register_cell_slice(
        self,
        document: dict,
        cell: dict,
        *,
        catalog: dict | None = None,
        roster: dict | None = None,
    ) -> None:
        version_slice = cell["version_slice"]
        expected_slice, comparison_basis = track_model.core_track_version_slice(
            track=version_slice["track"],
            slice_time=version_slice["slice_time"],
            spruce_branch_bases=self.branch_bases,
        )
        self.assertEqual(expected_slice, version_slice)
        registry = document["version_policy"]["slice_comparison_bases"]
        registry[version_slice["content_sha256"]] = comparison_basis
        document["version_policy"]["slice_comparison_bases"] = dict(
            sorted(registry.items())
        )
        branch_snapshot = track_model._slice_branch_basis_snapshot(
            spruce_branch_bases=self.branch_bases,
            catalog=catalog or self.catalog,
            main_release_roster=roster or self.release_roster,
            catalog_file_sha256=hashlib.sha256(
                (ROOT / "manifests/core-builds.json").read_bytes()
            ).hexdigest(),
            release_roster_file_sha256=hashlib.sha256(
                (ROOT / "manifests/spruce-release-roster.json").read_bytes()
            ).hexdigest(),
        )
        document["version_policy"]["slice_branch_basis_snapshots"][
            self.branch_bases["content_sha256"]
        ] = branch_snapshot
        document["version_policy"]["slice_branch_basis_snapshots"] = dict(
            sorted(
                document["version_policy"][
                    "slice_branch_basis_snapshots"
                ].items()
            )
        )

    def _stable_cell(
        self, cell: dict, *, chipset: str, origin_track: str = "main"
    ) -> dict:
        stable = copy.deepcopy(cell)
        if stable.get("version_slice", {}).get("track") != origin_track:
            stable, _comparison_basis = self._versioned_cell(
                stable,
                track=origin_track,
            )
        stable.update(
            {
                "approved_test_variant_id": core_variant_id(
                    core_id="alpha",
                    cell_chipset=chipset,
                    cell=stable,
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                ),
                "approved_test_origin_track": origin_track,
                "approved_at": "2026-08-09T12:00:00Z",
                "approved_by": "test-approver",
                "reason": "Synthetic approval used to verify resolution semantics.",
                "previous_stable_variant_id": None,
                "source_registry_content_sha256": "a" * 64,
            }
        )
        return stable

    def _index_source_registry(self, source: dict) -> str:
        snapshot = core_track_source_snapshot(source)
        digest, entry = track_model._snapshot_index_entry(
            repository_root=ROOT,
            snapshot=snapshot,
        )
        self.source_registry_index[digest] = entry
        return digest

    def _index_setter_snapshot(self, result: dict) -> None:
        snapshot = result.get("snapshot")
        if snapshot is None:
            return
        digest, entry = track_model._snapshot_index_entry(
            repository_root=ROOT,
            snapshot=snapshot,
        )
        self.assertEqual(result["snapshot_path"], entry["path"])
        self.assertEqual(result["snapshot_file_sha256"], entry["file_sha256"])
        self.assertEqual(result["parent_registry_content_sha256"], digest)
        self.source_registry_index[digest] = entry

    def _track_document(
        self,
        *,
        main_test: dict[str, dict] | None = None,
        nightly_test: dict[str, dict] | None = None,
        edge_test: dict[str, dict] | None = None,
        main_stable: dict[str, dict] | None = None,
        nightly_stable: dict[str, dict] | None = None,
        edge_stable: dict[str, dict] | None = None,
        pin_index: dict[str, dict] | None = None,
    ) -> dict:
        selected_pins = self.pin_index if pin_index is None else pin_index

        def normalized_cells(
            cells: dict[str, dict] | None,
            *,
            direct_track: str,
            stable: bool = False,
        ) -> dict[str, dict] | None:
            if cells is None:
                return None
            normalized: dict[str, dict] = {}
            for chipset, raw_cell in cells.items():
                cell = copy.deepcopy(raw_cell)
                slice_track = (
                    cell.get("approved_test_origin_track", direct_track)
                    if stable
                    else direct_track
                )
                if cell.get("version_slice", {}).get("track") != slice_track:
                    cell, _comparison_basis = self._versioned_cell(
                        cell,
                        track=slice_track,
                    )
                normalized[chipset] = cell
            return normalized

        main_test = normalized_cells(main_test, direct_track="main")
        nightly_test = normalized_cells(nightly_test, direct_track="nightly")
        edge_test = normalized_cells(edge_test, direct_track="edge")
        main_stable = normalized_cells(
            main_stable, direct_track="main", stable=True
        )
        nightly_stable = normalized_cells(
            nightly_stable, direct_track="nightly", stable=True
        )
        edge_stable = normalized_cells(
            edge_stable, direct_track="edge", stable=True
        )
        document = {
            "$schema": "./core-tracks.schema.json",
            "schema_version": 3,
            "selection_model": "manual-version-channel-build-pins-v3",
            "applicability_scope": "architecture-only",
            "version_policy": {
                "assignment_model": "manual-reviewed-build-pin-v1",
                "slice_model": "manual-track-version-slice-v1",
                "slice_comparison_bases": {},
                "slice_branch_basis_snapshots": {},
                "source_order_model": (
                    "assignment-time-git-ancestry-or-authorized-outlier-v1"
                ),
                "levels": {
                    "main": "spruce-main",
                    "nightly": "spruce-development",
                    "edge": "latest-reviewed-upstream",
                },
                "edge_latest": {
                    "model": "reviewed-remote-ref-snapshot-v1",
                    "snapshot": {
                        "snapshot_id": "synthetic-edge-review",
                        "captured_at": "2026-08-10T05:12:51Z",
                        "file_sha256": "e" * 64,
                        "content_sha256": "d" * 64,
                    },
                    "heads": {
                        "alpha": {
                            "repository": "https://example.invalid/alpha.git",
                            "requested_ref": "refs/heads/main",
                            "commit": "a" * 40,
                            "tree": "b" * 40,
                            "latest_semantics": "exact-branch-tip",
                            "status": "unchanged",
                        }
                    },
                },
            },
            "source_order_parent_bindings": [],
            "source_order_outliers": [],
            "spruce_branch_bases": {
                "path": "manifests/spruce-core-branch-bases.json",
                "content_sha256": self.branch_bases["content_sha256"],
            },
            "historical_release_correlation": {
                "roster_path": "manifests/spruce-release-roster.json",
                "roster_content_sha256": self.release_roster["content_sha256"],
            },
            "tracks": {
                "main": {
                    "extends": None,
                    "spruce_branch_basis": {
                        "basis_id": "spruce-main",
                        "basis_content_sha256": self.branch_bases["bases"][
                            "spruce-main"
                        ]["content_sha256"],
                    },
                    "test": self._core_cells(main_test),
                    "stable": self._core_cells(main_stable),
                    "deferred": (
                        {}
                        if "universal" in (main_test or {})
                        else {
                            "alpha": {
                                "universal": {
                                    "state": "deferred",
                                    "reason": (
                                        "no-reviewed-version-channel-build-pin"
                                    ),
                                }
                            }
                        }
                    ),
                },
                "nightly": {
                    "extends": "main",
                    "spruce_branch_basis": {
                        "basis_id": "spruce-development",
                        "basis_content_sha256": self.branch_bases["bases"][
                            "spruce-development"
                        ]["content_sha256"],
                    },
                    "test": self._core_cells(nightly_test),
                    "stable": self._core_cells(nightly_stable),
                    "deferred": {},
                },
                "edge": {
                    "extends": "nightly",
                    "spruce_branch_basis": {
                        "basis_id": "spruce-development",
                        "basis_content_sha256": self.branch_bases["bases"][
                            "spruce-development"
                        ]["content_sha256"],
                    },
                    "test": self._core_cells(edge_test),
                    "stable": self._core_cells(edge_stable),
                    "deferred": {},
                },
            },
            "content_sha256": "",
        }
        for cells in document["tracks"]["main"]["test"].values():
            for cell in cells.values():
                self._register_cell_slice(document, cell)
        for track in track_model.CORE_TRACKS:
            for cells in document["tracks"][track]["stable"].values():
                for cell in cells.values():
                    self._register_cell_slice(document, cell)
        requested_child_tests = {
            track: copy.deepcopy(document["tracks"][track]["test"])
            for track in ("nightly", "edge")
        }
        stable_maps = {
            track: copy.deepcopy(document["tracks"][track]["stable"])
            for track in track_model.CORE_TRACKS
        }
        for track in track_model.CORE_TRACKS:
            document["tracks"][track]["stable"] = {}
        for track in ("nightly", "edge"):
            document["tracks"][track]["test"] = {}
        _rehash_tracks(document)
        for track in ("nightly", "edge"):
            parent_track = track_model.TRACK_PARENTS[track]
            assert parent_track is not None
            for core_id, cells in requested_child_tests[track].items():
                for chipset, cell in cells.items():
                    self._index_source_registry(document)
                    predecessor = track_model._parent_test_candidate(
                        document["tracks"],
                        parent=parent_track,
                        core_id=core_id,
                        chipset=chipset,
                    )
                    self._register_cell_slice(document, cell)
                    document["tracks"][track]["test"].setdefault(core_id, {})[
                        chipset
                    ] = copy.deepcopy(cell)
                    if predecessor is None:
                        continue
                    parent_cell, parent_origin, parent_chipset = predecessor
                    parent_pin = selected_pins[parent_cell["build_pin_id"]]
                    child_pin = selected_pins[cell["build_pin_id"]]
                    parent_variant = core_variant_id(
                        core_id=core_id,
                        cell_chipset=parent_chipset,
                        cell=parent_cell,
                        pin_index=selected_pins,
                        tunings=self.tunings,
                    )
                    child_variant = core_variant_id(
                        core_id=core_id,
                        cell_chipset=chipset,
                        cell=cell,
                        pin_index=selected_pins,
                        tunings=self.tunings,
                    )
                    parent_lineage = None
                    if track == "edge" and parent_origin == "nightly":
                        parent_coordinate = (
                            "nightly",
                            core_id,
                            parent_chipset,
                        )
                        binding_index, _ = (
                            track_model._source_order_parent_binding_index(
                                document["source_order_parent_bindings"]
                            )
                        )
                        outlier_index, _ = track_model._source_order_outlier_index(
                            document["source_order_outliers"]
                        )
                        parent_lineage = {
                            "binding": copy.deepcopy(
                                binding_index[parent_coordinate]
                            ),
                            "outlier": copy.deepcopy(
                                outlier_index.get(parent_coordinate)
                            ),
                        }
                    binding = track_model._source_order_parent_binding(
                        source_registry_content_sha256=document["content_sha256"],
                        track=track,
                        core_id=core_id,
                        chipset=chipset,
                        parent_origin_track=parent_origin,
                        parent_selected_chipset=parent_chipset,
                        parent_cell=parent_cell,
                        parent_pin=parent_pin,
                        parent_variant=parent_variant,
                        parent_lineage=parent_lineage,
                        child_cell=cell,
                        child_pin=child_pin,
                        child_variant=child_variant,
                    )
                    document["source_order_parent_bindings"].append(binding)
                    _rehash_tracks(document)
        document["source_order_parent_bindings"].sort(
            key=lambda record: (
                track_model.CORE_TRACKS.index(record["track"]),
                record["core_id"],
                record["chipset"],
            )
        )
        _rehash_tracks(document)
        source = copy.deepcopy(document)
        _rehash_tracks(source)
        source_digest = source["content_sha256"]
        self._index_source_registry(source)
        for track in track_model.CORE_TRACKS:
            document["tracks"][track]["stable"] = stable_maps[track]
            for cells in document["tracks"][track]["stable"].values():
                for cell in cells.values():
                    cell["source_registry_content_sha256"] = source_digest
        return _rehash_tracks(document)

    def _resolve(self, document: dict, *, track: str, marker: str, chipset: str):
        return resolve_core_track_cell(
            document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            track=track,
            marker=marker,
            chipset=chipset,
            core_id="alpha",
        )

    def test_universal_is_the_empty_no_flags_fallback(self) -> None:
        tunings = validate_chipset_tunings(self.live_tunings)
        universal = resolved_tuning_profile(tunings, UNIVERSAL_TUNING_PROFILE)

        self.assertEqual("universal", universal["chipset"])
        self.assertEqual("any", universal["architecture"])
        self.assertEqual({}, universal["properties"])
        self.assertEqual(
            COMPILER_ARGUMENT_MAPPING_VERSION,
            universal["compiler_argument_mapping_version"],
        )
        self.assertEqual([], universal["compiler_arguments"])
        self.assertEqual(
            [], compiler_arguments_for_profile(tunings, UNIVERSAL_TUNING_PROFILE)
        )
        for chipset in set(CHIPSETS) - {"universal"}:
            with self.subTest(chipset=chipset):
                self.assertEqual("universal", tunings["chipsets"][chipset]["fallback"])

        self.assertEqual(
            ["-mcpu=cortex-a53"],
            compiler_arguments_for_profile(tunings, "a133p-cortex-a53-v1"),
        )
        self.assertEqual(
            ["-mcpu=cortex-a55"],
            compiler_arguments_for_profile(tunings, "a523-cortex-a55-v1"),
        )
        self.assertEqual(
            ["-mcpu=cortex-a7", "-mfpu=neon-vfpv4", "-mfloat-abi=hard"],
            compiler_arguments_for_profile(tunings, "a33-cortex-a7-v1"),
        )
        self.assertEqual(
            ["-mcpu=cortex-a7", "-mfpu=neon-vfpv4", "-mfloat-abi=hard"],
            compiler_arguments_for_profile(tunings, "ssd202d-cortex-a7-v1"),
        )

    def test_universal_cells_accept_only_empty_or_absent_pin_tuning(self) -> None:
        absent_identity = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        validate_core_tracks(
            absent_identity,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
        )

        universal = resolved_tuning_profile(
            self.tunings, UNIVERSAL_TUNING_PROFILE
        )
        self.pin_index["alpha-recorded-universal"] = self._pin(
            "alpha-recorded-universal",
            "3",
            {
                "profile_id": universal["profile_id"],
                "content_sha256": universal["content_sha256"],
            },
        )
        recorded_cell = copy.deepcopy(self.universal_cell)
        recorded_cell["build_pin_id"] = "alpha-recorded-universal"
        recorded_identity = self._track_document(
            main_test={"universal": recorded_cell}
        )
        validate_core_tracks(
            recorded_identity,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
        )

        chipset_tuned_cell = copy.deepcopy(self.universal_cell)
        chipset_tuned_cell["build_pin_id"] = "alpha-h700"
        chipset_tuned = self._track_document(
            main_test={"universal": chipset_tuned_cell}
        )
        with self.assertRaisesRegex(
            PipelineError, "universal pin binds chipset-specific tuning"
        ):
            validate_core_tracks(
                chipset_tuned,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

    def test_test_cells_inherit_but_stable_approvals_are_track_local(self) -> None:
        main_stable = self._stable_cell(self.universal_cell, chipset="universal")
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            main_stable={"universal": main_stable},
        )

        main = self._resolve(document, track="main", marker="test", chipset="h700")
        nightly = self._resolve(
            document, track="nightly", marker="test", chipset="h700"
        )
        edge = self._resolve(document, track="edge", marker="test", chipset="h700")
        edge_stable = self._resolve(
            document, track="edge", marker="stable", chipset="h700"
        )

        self.assertEqual(
            ("universal", "main"),
            (main["selected_chipset"], main["test_origin_track"]),
        )
        self.assertIsNone(main["current_assignment_content_sha256"])
        self.assertEqual(
            ("h700", "nightly"),
            (nightly["selected_chipset"], nightly["test_origin_track"]),
        )
        self.assertEqual(
            track_model.core_track_test_assignment_content_sha256(
                document,
                track="nightly",
                core_id="alpha",
                chipset="h700",
            ),
            nightly["current_assignment_content_sha256"],
        )
        self.assertEqual(
            ("h700", "nightly"),
            (edge["selected_chipset"], edge["test_origin_track"]),
        )
        self.assertIsNone(edge["current_assignment_content_sha256"])
        self.assertEqual("unstable_fallback", edge_stable["selected_state"])
        self.assertEqual("exact_test_unstable_fallback", edge_stable["resolution"])
        self.assertIsNone(edge_stable["current_assignment_content_sha256"])

    def test_differing_child_source_requires_verified_git_ancestry(self) -> None:
        pins = copy.deepcopy(self.pin_index)
        pins["alpha-h700"]["source_commit"] = "c" * 40
        pins["alpha-h700"]["source_tree"] = "d" * 40
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            pin_index=pins,
        )

        with self.assertRaisesRegex(PipelineError, "source ancestry is unverified"):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=pins,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        calls: list[tuple[str, str, str, str]] = []

        def verifier(
            core_id: str,
            repository: str,
            ancestor: str,
            descendant: str,
        ) -> bool:
            calls.append((core_id, repository, ancestor, descendant))
            return True

        validate_core_tracks(
            document,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=verifier,
        )
        self.assertEqual(
            [
                (
                    "alpha",
                    "https://example.invalid/alpha.git",
                    "a" * 40,
                    "c" * 40,
                )
            ],
            calls,
        )

        with self.assertRaisesRegex(PipelineError, "not a verified descendant"):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=pins,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: False,
            )

        same_commit_different_tree = copy.deepcopy(pins)
        same_commit_different_tree["alpha-h700"]["source_commit"] = "a" * 40
        same_commit_different_tree["alpha-h700"]["source_tree"] = "d" * 40
        same_commit_document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            pin_index=same_commit_different_tree,
        )
        with self.assertRaisesRegex(PipelineError, "differing trees"):
            validate_core_tracks(
                same_commit_document,
                catalog=self.catalog,
                pin_index=same_commit_different_tree,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: True,
            )

    def test_same_commit_tree_repository_change_requires_exact_outlier(self) -> None:
        pin_index = copy.deepcopy(self.pin_index)
        pin_index["alpha-h700"]["source_repository"] = (
            "https://example.invalid/alpha-mirror.git"
        )
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            pin_index=pin_index,
        )

        with self.assertRaisesRegex(PipelineError, "changes source repository"):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: True,
            )

        binding = track_model._source_order_outlier_binding(
            parent_binding=document["source_order_parent_bindings"][0],
        )
        authorized = copy.deepcopy(document)
        authorized["source_order_outliers"] = [
            {
                **binding,
                "authorized_at": "2026-08-10T12:00:00Z",
                "authorized_by": "test-operator",
                "reason": "Reviewed repository identity transition.",
            }
        ]
        _rehash_tracks(authorized)
        validate_core_tracks(
            authorized,
            catalog=self.catalog,
            pin_index=pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
        )
        direct_child = authorized["tracks"]["nightly"]["test"]["alpha"]["h700"]
        self.assertEqual(
            direct_child["version_slice"],
            authorized["source_order_parent_bindings"][0]["child_cell"][
                "version_slice"
            ],
        )
        self.assertEqual(
            direct_child["version_slice"],
            authorized["source_order_outliers"][0]["child_cell"][
                "version_slice"
            ],
        )

        resliced_child, _comparison = self._versioned_cell(
            direct_child,
            track="nightly",
            slice_time="2026-08-10T11:30:00Z",
        )
        stale_child_binding = copy.deepcopy(authorized)
        stale_child_binding["tracks"]["nightly"]["test"]["alpha"][
            "h700"
        ] = resliced_child
        self._register_cell_slice(stale_child_binding, resliced_child)
        _rehash_tracks(stale_child_binding)
        with self.assertRaisesRegex(PipelineError, "frozen child identity is stale"):
            validate_core_tracks(
                stale_child_binding,
                catalog=self.catalog,
                pin_index=pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: False,
            )

    def test_child_order_uses_creation_time_parent_after_main_advances(self) -> None:
        pins = copy.deepcopy(self.pin_index)
        pins["alpha-h700"]["source_commit"] = "c" * 40
        pins["alpha-h700"]["source_tree"] = "d" * 40
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            pin_index=pins,
        )
        frozen_binding = copy.deepcopy(
            document["source_order_parent_bindings"][0]
        )
        pins["alpha-main-next"] = copy.deepcopy(pins["alpha-universal"])
        pins["alpha-main-next"].update(
            {
                "path": "pins/core-sets/alpha-main-next.json",
                "pin_id": "alpha-main-next",
                "file_sha256": "8" * 64,
                "content_sha256": "8" * 64,
                "source_commit": "e" * 40,
                "source_tree": "f" * 40,
            }
        )
        next_main_cell, _next_main_basis = self._versioned_cell(
            {
                **self.universal_cell,
                "build_pin_id": "alpha-main-next",
            },
            track="main",
            slice_time="2026-08-10T10:30:00Z",
        )
        document["tracks"]["main"]["test"]["alpha"][
            "universal"
        ] = next_main_cell
        self._register_cell_slice(document, next_main_cell)
        _rehash_tracks(document)
        calls: list[tuple[str, str, str, str]] = []

        def verifier(*edge: str) -> bool:
            calls.append(edge)
            return True

        validate_core_tracks(
            document,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=verifier,
        )
        self.assertEqual(frozen_binding, document["source_order_parent_bindings"][0])
        self.assertEqual(
            self._slice_time("main"),
            frozen_binding["parent_cell"]["version_slice"]["slice_time"],
        )
        self.assertEqual(
            "2026-08-10T10:30:00Z",
            document["tracks"]["main"]["test"]["alpha"]["universal"][
                "version_slice"
            ]["slice_time"],
        )
        self.assertNotEqual(
            frozen_binding["parent_cell"]["version_slice"],
            document["tracks"]["main"]["test"]["alpha"]["universal"][
                "version_slice"
            ],
        )
        self.assertEqual(
            [
                (
                    "alpha",
                    "https://example.invalid/alpha.git",
                    "a" * 40,
                    "c" * 40,
                )
            ],
            calls,
        )

    def test_version_slice_changes_assignment_not_build_variant(self) -> None:
        document = self._track_document()
        variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        first = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=None,
            track="main",
            core_id="alpha",
            chipset="universal",
            pin_id="alpha-universal",
            tuning_profile=UNIVERSAL_TUNING_PROFILE,
            slice_time="2026-08-10T10:00:00Z",
            applicable_chipsets=["h700", "rk3566"],
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=variant,
            expected_parent_variant=None,
            expected_parent_registry=None,
        )
        with self.assertRaisesRegex(
            PipelineError, "TEST assignment changed since review"
        ):
            set_core_track_test(
                first["registry"],
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=None,
                track="main",
                core_id="alpha",
                chipset="universal",
                pin_id="alpha-universal",
                tuning_profile=UNIVERSAL_TUNING_PROFILE,
                slice_time="2026-08-10T10:30:00Z",
                applicable_chipsets=["h700", "rk3566"],
                expected_source_registry=first["registry"]["content_sha256"],
                expected_current_test=variant,
                expected_current_assignment="f" * 64,
                expected_new_variant=variant,
                expected_parent_variant=None,
                expected_parent_registry=None,
            )

        second = set_core_track_test(
            first["registry"],
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=None,
            track="main",
            core_id="alpha",
            chipset="universal",
            pin_id="alpha-universal",
            tuning_profile=UNIVERSAL_TUNING_PROFILE,
            slice_time="2026-08-10T10:30:00Z",
            applicable_chipsets=["h700", "rk3566"],
            expected_source_registry=first["registry"]["content_sha256"],
            expected_current_test=variant,
            expected_current_assignment=first["assignment_content_sha256"],
            expected_new_variant=variant,
            expected_parent_variant=None,
            expected_parent_registry=None,
        )

        self.assertEqual(variant, first["variant_id"])
        self.assertEqual(variant, second["variant_id"])
        self.assertEqual(variant, second["previous_variant_id"])
        self.assertIsNone(first["previous_assignment_content_sha256"])
        self.assertEqual(
            first["assignment_content_sha256"],
            second["previous_assignment_content_sha256"],
        )
        self.assertNotEqual(first["version_slice"], second["version_slice"])
        self.assertNotEqual(
            first["assignment_content_sha256"],
            second["assignment_content_sha256"],
        )
        self.assertEqual(
            2,
            len(second["registry"]["version_policy"]["slice_comparison_bases"]),
        )
        self.assertEqual(
            1,
            len(
                second["registry"]["version_policy"][
                    "slice_branch_basis_snapshots"
                ]
            ),
        )
        self.assertEqual(
            {"model", "track", "slice_time", "content_sha256"},
            set(second["version_slice"]),
        )
        with self.assertRaisesRegex(
            PipelineError, "TEST assignment changed since review"
        ):
            set_core_track_test(
                second["registry"],
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=None,
                track="main",
                core_id="alpha",
                chipset="universal",
                pin_id="alpha-universal",
                tuning_profile=UNIVERSAL_TUNING_PROFILE,
                slice_time="2026-08-10T11:00:00Z",
                applicable_chipsets=["h700", "rk3566"],
                expected_source_registry=second["registry"]["content_sha256"],
                expected_current_test=variant,
                expected_current_assignment=first[
                    "assignment_content_sha256"
                ],
                expected_new_variant=variant,
                expected_parent_variant=None,
                expected_parent_registry=None,
            )

    def test_test_admission_plan_is_deterministic_and_setter_exact(self) -> None:
        document = self._track_document()
        original = copy.deepcopy(document)
        proposal = {
            "repository_root": ROOT,
            "catalog": self.catalog,
            "pin_index": self.pin_index,
            "tunings": self.tunings,
            "main_release_roster": self.release_roster,
            "spruce_branch_bases": self.branch_bases,
            "source_registry_index": self.source_registry_index,
            "source_ancestry_verifier": None,
            "track": "main",
            "core_id": "alpha",
            "chipset": "universal",
            "pin_id": "alpha-universal",
            "tuning_profile": UNIVERSAL_TUNING_PROFILE,
            "slice_time": self._slice_time("main"),
            "applicable_chipsets": ["h700", "rk3566"],
        }

        first = plan_core_track_test(document, **proposal)
        second = plan_core_track_test(document, **proposal)

        self.assertEqual(first, second)
        self.assertEqual(original, document)
        self.assertEqual(
            {
                "expected_source_registry": document["content_sha256"],
                "expected_current_test": "absent",
                "expected_current_assignment": "absent",
                "expected_new_variant": first["variant_id"],
                "expected_parent_variant": None,
                "expected_parent_registry": None,
            },
            first["expectations"],
        )
        applied = set_core_track_test(
            document,
            **proposal,
            **first["expectations"],
        )
        self.assertEqual(first, applied)

        stale_expectations = {
            **first["expectations"],
            "expected_source_registry": "f" * 64,
        }
        with self.assertRaisesRegex(
            PipelineError, "source track registry changed since admission review"
        ):
            set_core_track_test(
                document,
                **proposal,
                **stale_expectations,
            )

    def test_version_slice_and_host_reproduction_admission_fail_closed(self) -> None:
        document = self._track_document(main_test={"universal": self.universal_cell})
        mutations = (
            ("track", "nightly", "version_slice.track is invalid"),
            ("slice_time", "2026-08-10T10:00:00+00:00", "slice_time is invalid"),
            ("content_sha256", "f" * 64, "has no comparison-basis record"),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field), self.assertRaisesRegex(
                PipelineError, expected_error
            ):
                changed = copy.deepcopy(document)
                changed["tracks"]["main"]["test"]["alpha"]["universal"][
                    "version_slice"
                ][field] = value
                _rehash_tracks(changed)
                validate_core_tracks(
                    changed,
                    catalog=self.catalog,
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                    main_release_roster=self.release_roster,
                    spruce_branch_bases=self.branch_bases,
                    source_registry_index=self.source_registry_index,
                )

        legacy_pins = copy.deepcopy(self.pin_index)
        legacy_pins["alpha-universal"]["host_reproduction_content_sha256"] = None
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_pin_fixture(root, self._pin_document())
            indexed_legacy = load_core_pin_index(
                root,
                pin_validator=lambda _document, _path: {
                    "status": "valid",
                    "errors": [],
                },
            )
        self.assertIsNone(
            indexed_legacy["alpha-pin"][
                "host_reproduction_content_sha256"
            ]
        )
        legacy_document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        with self.assertRaisesRegex(
            PipelineError, "has no validated host reproduction proof"
        ):
            validate_core_tracks(
                legacy_document,
                catalog=self.catalog,
                pin_index=legacy_pins,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        empty = self._track_document()
        variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=legacy_pins,
            tunings=self.tunings,
        )
        with self.assertRaisesRegex(
            PipelineError, "has no validated host reproduction proof"
        ):
            set_core_track_test(
                empty,
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=legacy_pins,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=None,
                track="main",
                core_id="alpha",
                chipset="universal",
                pin_id="alpha-universal",
                tuning_profile=UNIVERSAL_TUNING_PROFILE,
                slice_time=self._slice_time("main"),
                applicable_chipsets=["h700", "rk3566"],
                expected_source_registry=empty["content_sha256"],
                expected_current_test="absent",
                expected_current_assignment="absent",
                expected_new_variant=variant,
                expected_parent_variant=None,
                expected_parent_registry=None,
            )

    def test_temporal_parent_bindings_are_mandatory_exact_and_allow_equal_freeze(
        self,
    ) -> None:
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"universal": self.universal_cell},
        )
        validate_core_tracks(
            document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
        )
        captured_digest = document["source_order_parent_bindings"][0][
            "captured_registry_content_sha256"
        ]
        self.assertIn(captured_digest, self.source_registry_index)

        missing_snapshot_index = copy.deepcopy(self.source_registry_index)
        missing_snapshot_index.pop(captured_digest)
        with self.assertRaisesRegex(
            PipelineError, "captured parent registry snapshot is missing"
        ):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=missing_snapshot_index,
            )

        mutated_snapshot_index = copy.deepcopy(self.source_registry_index)
        mutated_snapshot_index[captured_digest]["source_registry"]["tracks"][
            "main"
        ]["test"] = {}
        with self.assertRaisesRegex(
            PipelineError, "captured parent registry snapshot is invalid"
        ):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=mutated_snapshot_index,
            )

        missing = copy.deepcopy(document)
        missing["source_order_parent_bindings"] = []
        _rehash_tracks(missing)
        with self.assertRaisesRegex(PipelineError, "has no frozen parent"):
            validate_core_tracks(
                missing,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        tampered = copy.deepcopy(document)
        tampered["source_order_parent_bindings"][0][
            "captured_registry_content_sha256"
        ] = "f" * 64
        _rehash_tracks(tampered)
        with self.assertRaisesRegex(PipelineError, "content_sha256 is stale"):
            validate_core_tracks(
                tampered,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        arbitrary_capture = copy.deepcopy(document)
        arbitrary_binding = arbitrary_capture["source_order_parent_bindings"][0]
        arbitrary_binding["captured_registry_content_sha256"] = "f" * 64
        arbitrary_binding["content_sha256"] = (
            track_model.source_order_parent_binding_content_sha256(
                arbitrary_binding
            )
        )
        _rehash_tracks(arbitrary_capture)
        with self.assertRaisesRegex(
            PipelineError, "captured parent registry snapshot is missing"
        ):
            validate_core_tracks(
                arbitrary_capture,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        selection_tamper = copy.deepcopy(document)
        selection_binding = selection_tamper["source_order_parent_bindings"][0]
        selection_binding["parent_selection_content_sha256"] = "f" * 64
        selection_binding["content_sha256"] = (
            track_model.source_order_parent_binding_content_sha256(
                selection_binding
            )
        )
        _rehash_tracks(selection_tamper)
        with self.assertRaisesRegex(
            PipelineError, "parent_selection_content_sha256 is stale"
        ):
            validate_core_tracks(
                selection_tamper,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        extra = copy.deepcopy(document)
        extra["tracks"]["nightly"]["test"] = {}
        _rehash_tracks(extra)
        with self.assertRaisesRegex(PipelineError, "unused or stale record"):
            validate_core_tracks(
                extra,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

    def test_edge_parent_capture_cannot_rewrite_direct_nightly_as_main(
        self,
    ) -> None:
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            edge_test={"h700": self.h700_cell},
        )
        edge_binding = next(
            record
            for record in document["source_order_parent_bindings"]
            if record["track"] == "edge"
        )
        main_cell = document["tracks"]["main"]["test"]["alpha"][
            "universal"
        ]
        main_pin = self.pin_index[main_cell["build_pin_id"]]
        edge_binding.update(
            {
                "parent_origin_track": "main",
                "parent_selected_chipset": "universal",
                "parent_cell": copy.deepcopy(main_cell),
                "parent_variant_id": core_variant_id(
                    core_id="alpha",
                    cell_chipset="universal",
                    cell=main_cell,
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                ),
                "parent_build_pin_id": main_cell["build_pin_id"],
                "parent_pin_content_sha256": main_pin["content_sha256"],
                "parent_source_repository": main_pin["source_repository"],
                "parent_source_requested_ref": main_pin[
                    "source_requested_ref"
                ],
                "parent_source_commit": main_pin["source_commit"],
                "parent_source_tree": main_pin["source_tree"],
                "parent_lineage": None,
            }
        )
        edge_binding["parent_selection_content_sha256"] = (
            track_model.source_order_parent_selection_content_sha256(
                edge_binding
            )
        )
        edge_binding["content_sha256"] = (
            track_model.source_order_parent_binding_content_sha256(edge_binding)
        )
        _rehash_tracks(document)

        with self.assertRaisesRegex(
            PipelineError, "frozen parent differs from its captured registry"
        ):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

    def test_edge_copies_nightly_binding_and_outlier_lineage(self) -> None:
        document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        pins = copy.deepcopy(self.pin_index)
        pins["alpha-diverged"] = copy.deepcopy(pins["alpha-h700"])
        pins["alpha-diverged"].update(
            {
                "path": "pins/core-sets/alpha-diverged.json",
                "pin_id": "alpha-diverged",
                "file_sha256": "7" * 64,
                "content_sha256": "7" * 64,
                "source_commit": "c" * 40,
                "source_tree": "d" * 40,
            }
        )
        diverged_cell = {
            **self.h700_cell,
            "build_pin_id": "alpha-diverged",
        }
        parent_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        diverged_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=diverged_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        nightly = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
            track="nightly",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-diverged",
            tuning_profile="h700-cortex-a53-v1",
            slice_time=self._slice_time("nightly"),
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=diverged_variant,
            expected_parent_variant=parent_variant,
            expected_parent_registry=document["content_sha256"],
            outlier_authorized_at="2026-08-10T12:00:00Z",
            outlier_authorized_by="test-operator",
            outlier_reason="Reviewed historical Nightly divergence.",
        )
        self._index_setter_snapshot(nightly)
        nightly_binding = copy.deepcopy(nightly["source_order_parent_binding"])
        nightly_outlier = copy.deepcopy(nightly["source_order_outlier"])
        edge_source = copy.deepcopy(nightly["registry"])
        edge_source["version_policy"]["edge_latest"]["heads"]["alpha"].update(
            {
                "commit": pins["alpha-diverged"]["source_commit"],
                "tree": pins["alpha-diverged"]["source_tree"],
            }
        )
        _rehash_tracks(edge_source)
        edge = set_core_track_test(
            edge_source,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
            track="edge",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-diverged",
            tuning_profile="h700-cortex-a53-v1",
            slice_time=self._slice_time("edge"),
            expected_source_registry=edge_source["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=diverged_variant,
            expected_parent_variant=diverged_variant,
            expected_parent_registry=edge_source["content_sha256"],
        )
        self._index_setter_snapshot(edge)
        self.assertEqual(
            {"binding": nightly_binding, "outlier": nightly_outlier},
            edge["source_order_parent_binding"]["parent_lineage"],
        )
        normalized = set_core_track_test(
            edge["registry"],
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
            track="nightly",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-h700",
            tuning_profile="h700-cortex-a53-v1",
            slice_time="2026-08-10T11:30:00Z",
            expected_source_registry=edge["registry"]["content_sha256"],
            expected_current_test=diverged_variant,
            expected_current_assignment=nightly[
                "assignment_content_sha256"
            ],
            expected_new_variant=core_variant_id(
                core_id="alpha",
                cell_chipset="h700",
                cell=self.h700_cell,
                pin_index=pins,
                tunings=self.tunings,
            ),
            expected_parent_variant=parent_variant,
            expected_parent_registry=edge["registry"]["content_sha256"],
        )
        self._index_setter_snapshot(normalized)
        validate_core_tracks(
            normalized["registry"],
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
        )
        edge_binding = next(
            record
            for record in normalized["registry"]["source_order_parent_bindings"]
            if record["track"] == "edge"
        )
        self.assertEqual(
            {"binding": nightly_binding, "outlier": nightly_outlier},
            edge_binding["parent_lineage"],
        )

    def test_one_core_inventory_scopes_only_external_ancestry_edges(self) -> None:
        catalog = {
            "cores": {
                "alpha": copy.deepcopy(self.catalog["cores"]["alpha"]),
                "beta": {
                    "source": {
                        "url": "https://example.invalid/beta.git",
                        "requested_ref": "refs/heads/main",
                    }
                },
            }
        }
        roster = self._release_roster(["alpha", "beta"])
        pin_index = copy.deepcopy(self.pin_index)
        pin_index["alpha-next"] = self._pin("alpha-next", "4", None)
        pin_index["alpha-next"]["source_commit"] = "c" * 40
        pin_index["beta-base"] = self._pin("beta-base", "5", None)
        pin_index["beta-base"].update(
            {
                "core_id": "beta",
                "source_repository": "https://example.invalid/beta.git",
            }
        )
        pin_index["beta-next"] = copy.deepcopy(pin_index["beta-base"])
        pin_index["beta-next"].update(
            {
                "path": "pins/core-sets/beta-next.json",
                "pin_id": "beta-next",
                "file_sha256": "6" * 64,
                "content_sha256": "6" * 64,
                "source_commit": "d" * 40,
            }
        )
        document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        document["version_policy"]["edge_latest"]["heads"]["beta"] = {
            "repository": "https://example.invalid/beta.git",
            "requested_ref": "refs/heads/main",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "latest_semantics": "exact-branch-tip",
            "status": "unchanged",
        }
        document["version_policy"]["edge_latest"]["heads"] = dict(
            sorted(document["version_policy"]["edge_latest"]["heads"].items())
        )
        document["historical_release_correlation"][
            "roster_content_sha256"
        ] = roster["content_sha256"]
        beta_base, _beta_main_basis = self._versioned_cell(
            {
                "build_pin_id": "beta-base",
                "tuning_profile": UNIVERSAL_TUNING_PROFILE,
                "applicable_chipsets": ["h700"],
            },
            track="main",
        )
        document["tracks"]["main"]["test"]["beta"] = {
            "universal": beta_base
        }
        self._register_cell_slice(
            document, beta_base, catalog=catalog, roster=roster
        )
        _rehash_tracks(document)
        alpha_nightly, _alpha_nightly_basis = self._versioned_cell(
            {
                **self.universal_cell,
                "build_pin_id": "alpha-next",
            },
            track="nightly",
        )
        beta_nightly, _beta_nightly_basis = self._versioned_cell(
            {
                **beta_base,
                "build_pin_id": "beta-next",
            },
            track="nightly",
        )
        nightly_cells = {
            "alpha": {"universal": alpha_nightly},
            "beta": {"universal": beta_nightly},
        }
        for core_id, cells in nightly_cells.items():
            for chipset, cell in cells.items():
                self._index_source_registry(document)
                predecessor = track_model._parent_test_candidate(
                    document["tracks"],
                    parent="main",
                    core_id=core_id,
                    chipset=chipset,
                )
                assert predecessor is not None
                self._register_cell_slice(
                    document, cell, catalog=catalog, roster=roster
                )
                parent_cell, parent_origin, parent_chipset = predecessor
                parent_pin = pin_index[parent_cell["build_pin_id"]]
                child_pin = pin_index[cell["build_pin_id"]]
                binding = track_model._source_order_parent_binding(
                    source_registry_content_sha256=document["content_sha256"],
                    track="nightly",
                    core_id=core_id,
                    chipset=chipset,
                    parent_origin_track=parent_origin,
                    parent_selected_chipset=parent_chipset,
                    parent_cell=parent_cell,
                    parent_pin=parent_pin,
                    parent_variant=core_variant_id(
                        core_id=core_id,
                        cell_chipset=parent_chipset,
                        cell=parent_cell,
                        pin_index=pin_index,
                        tunings=self.tunings,
                    ),
                    parent_lineage=None,
                    child_cell=cell,
                    child_pin=child_pin,
                    child_variant=core_variant_id(
                        core_id=core_id,
                        cell_chipset=chipset,
                        cell=cell,
                        pin_index=pin_index,
                        tunings=self.tunings,
                    ),
                )
                document["tracks"]["nightly"]["test"].setdefault(
                    core_id, {}
                )[chipset] = cell
                document["source_order_parent_bindings"].append(binding)
                _rehash_tracks(document)
        document["source_order_parent_bindings"].sort(
            key=lambda record: (
                track_model.CORE_TRACKS.index(record["track"]),
                record["core_id"],
                record["chipset"],
            )
        )
        _rehash_tracks(document)
        calls: list[str] = []

        def alpha_only(
            core_id: str, _repository: str, _ancestor: str, _descendant: str
        ) -> bool:
            calls.append(core_id)
            return core_id == "alpha"

        inventory = construct_core_track_inventory(
            document,
            catalog=catalog,
            pin_index=pin_index,
            tunings=self.tunings,
            main_release_roster=roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="nightly-test:universal",
            requested_cores=["alpha"],
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=alpha_only,
            source_ancestry_core_id="alpha",
        )
        self.assertTrue(inventory["complete"])
        self.assertEqual(["alpha"], calls)

        with self.assertRaisesRegex(PipelineError, "not a verified descendant"):
            validate_core_tracks(
                document,
                catalog=catalog,
                pin_index=pin_index,
                tunings=self.tunings,
                main_release_roster=roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=alpha_only,
            )

        mismatched_repository = copy.deepcopy(pin_index)
        mismatched_repository["beta-next"]["source_repository"] = (
            "https://example.invalid/not-beta.git"
        )
        with self.assertRaisesRegex(PipelineError, "frozen child identity is stale"):
            construct_core_track_inventory(
                document,
                catalog=catalog,
                pin_index=mismatched_repository,
                tunings=self.tunings,
                main_release_roster=roster,
                spruce_branch_bases=self.branch_bases,
                group_tag="nightly-test:universal",
                requested_cores=["alpha"],
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=alpha_only,
                source_ancestry_core_id="alpha",
            )

    def test_tuned_pin_test_admission_is_two_sided_cas_and_stable_immutable(
        self,
    ) -> None:
        stable = self._stable_cell(self.universal_cell, chipset="universal")
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            main_stable={"universal": stable},
        )
        new_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=self.h700_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        parent_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        stable_before = copy.deepcopy(document["tracks"]["nightly"]["stable"])
        planned = plan_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: True,
            track="nightly",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-h700",
            tuning_profile="h700-cortex-a53-v1",
            slice_time=self._slice_time("nightly"),
        )
        self.assertEqual(
            document["content_sha256"],
            planned["expectations"]["expected_source_registry"],
        )
        self.assertEqual(
            parent_variant,
            planned["expectations"]["expected_parent_variant"],
        )
        self.assertEqual(
            document["content_sha256"],
            planned["expectations"]["expected_parent_registry"],
        )
        result = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: True,
            track="nightly",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-h700",
            tuning_profile="h700-cortex-a53-v1",
            slice_time=self._slice_time("nightly"),
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=new_variant,
            expected_parent_variant=parent_variant,
            expected_parent_registry=document["content_sha256"],
        )
        self.assertEqual(planned, result)
        self._index_setter_snapshot(result)
        self.assertEqual(new_variant, result["variant_id"])
        self.assertIsNone(result["previous_variant_id"])
        self.assertEqual(
            {**self.h700_cell, "version_slice": result["version_slice"]},
            result["registry"]["tracks"]["nightly"]["test"]["alpha"]["h700"],
        )
        self.assertEqual(
            stable_before,
            result["registry"]["tracks"]["nightly"]["stable"],
        )
        self.assertEqual(parent_variant, result["parent_variant_id"])
        self.assertEqual(
            document["content_sha256"],
            result["source_order_parent_binding"][
                "captured_registry_content_sha256"
            ],
        )
        self.assertEqual(
            parent_variant,
            result["source_order_parent_binding"]["parent_variant_id"],
        )
        self.assertEqual(
            result["source_order_parent_binding"],
            result["registry"]["source_order_parent_bindings"][0],
        )
        self.assertEqual(
            result["parent_selection_content_sha256"],
            result["source_order_parent_binding"][
                "parent_selection_content_sha256"
            ],
        )
        self.assertEqual(document, result["snapshot"]["source_registry"])
        self.assertIsNone(result["source_order_outlier"])
        self.assertIsNone(result["edge_deferred_by_admission"])

        missing_parent_cas = {
            "track": "nightly",
            "core_id": "alpha",
            "chipset": "h700",
            "pin_id": "alpha-h700",
            "tuning_profile": "h700-cortex-a53-v1",
            "expected_source_registry": document["content_sha256"],
            "expected_current_test": "absent",
            "expected_current_assignment": "absent",
            "expected_new_variant": new_variant,
        }
        with self.assertRaisesRegex(PipelineError, "expected parent variant"):
            set_core_track_test(
                document,
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: True,
                slice_time=self._slice_time("nightly"),
                expected_parent_variant=None,
                expected_parent_registry=document["content_sha256"],
                **missing_parent_cas,
            )

        with self.assertRaisesRegex(PipelineError, "parent registry changed"):
            set_core_track_test(
                document,
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: True,
                track="nightly",
                core_id="alpha",
                chipset="h700",
                pin_id="alpha-h700",
                tuning_profile="h700-cortex-a53-v1",
                slice_time=self._slice_time("nightly"),
                expected_source_registry=document["content_sha256"],
                expected_current_test="absent",
                expected_current_assignment="absent",
                expected_new_variant=new_variant,
                expected_parent_variant=parent_variant,
                expected_parent_registry="f" * 64,
            )

        for label, changes, error in (
            (
                "source registry CAS",
                {"expected_source_registry": "f" * 64},
                "source track registry changed",
            ),
            (
                "current CAS",
                {"expected_current_test": "f" * 64},
                "changed since review",
            ),
            (
                "new CAS",
                {"expected_new_variant": "f" * 64},
                "new core track TEST variant",
            ),
            (
                "profile",
                {"tuning_profile": "a523-cortex-a55-v1"},
                "exact one-ABI tuning profile",
            ),
        ):
            arguments = {
                "track": "nightly",
                "core_id": "alpha",
                "chipset": "h700",
                "pin_id": "alpha-h700",
                "tuning_profile": "h700-cortex-a53-v1",
                "expected_source_registry": document["content_sha256"],
                "expected_current_test": "absent",
                "expected_current_assignment": "absent",
                "expected_new_variant": new_variant,
                "expected_parent_variant": parent_variant,
            }
            arguments.update(changes)
            with self.subTest(label=label), self.assertRaisesRegex(
                PipelineError, error
            ):
                set_core_track_test(
                    document,
                    repository_root=ROOT,
                    catalog=self.catalog,
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                    main_release_roster=self.release_roster,
                    spruce_branch_bases=self.branch_bases,
                    source_registry_index=self.source_registry_index,
                    source_ancestry_verifier=lambda *_args: True,
                    slice_time=self._slice_time("nightly"),
                    expected_parent_registry=document["content_sha256"],
                    **arguments,
                )

        wrong_abi_pins = copy.deepcopy(self.pin_index)
        wrong_abi_pins["alpha-h700"]["architectures"] = ["armhf"]
        with self.assertRaisesRegex(PipelineError, "exact one-ABI tuning profile"):
            set_core_track_test(
                document,
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=wrong_abi_pins,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: True,
                track="nightly",
                core_id="alpha",
                chipset="h700",
                pin_id="alpha-h700",
                tuning_profile="h700-cortex-a53-v1",
                slice_time=self._slice_time("nightly"),
                expected_source_registry=document["content_sha256"],
                expected_current_test="absent",
                expected_current_assignment="absent",
                expected_new_variant=new_variant,
                expected_parent_variant=parent_variant,
                expected_parent_registry=document["content_sha256"],
            )

    def test_test_admission_replaces_and_removes_exact_source_outlier(self) -> None:
        document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        pins = copy.deepcopy(self.pin_index)
        pins["alpha-diverged"] = copy.deepcopy(pins["alpha-h700"])
        pins["alpha-diverged"].update(
            {
                "path": "pins/core-sets/alpha-diverged.json",
                "pin_id": "alpha-diverged",
                "file_sha256": "7" * 64,
                "content_sha256": "7" * 64,
                "source_commit": "c" * 40,
                "source_tree": "d" * 40,
            }
        )
        diverged_cell = {
            **self.h700_cell,
            "build_pin_id": "alpha-diverged",
        }
        parent_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        diverged_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=diverged_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        admitted = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
            track="nightly",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-diverged",
            tuning_profile="h700-cortex-a53-v1",
            slice_time=self._slice_time("nightly"),
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=diverged_variant,
            expected_parent_variant=parent_variant,
            expected_parent_registry=document["content_sha256"],
            outlier_authorized_at="2026-08-10T12:00:00Z",
            outlier_authorized_by="test-operator",
            outlier_reason="Reviewed non-linear upstream source edge.",
        )
        self._index_setter_snapshot(admitted)
        self.assertEqual(parent_variant, admitted["parent_variant_id"])
        self.assertEqual(
            admitted["source_order_outlier"],
            admitted["registry"]["source_order_outliers"][0],
        )
        self.assertIsNotNone(admitted["edge_deferred_by_admission"])

        normal_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=self.h700_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        normalized = set_core_track_test(
            admitted["registry"],
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
            track="nightly",
            core_id="alpha",
            chipset="h700",
            pin_id="alpha-h700",
            tuning_profile="h700-cortex-a53-v1",
            slice_time="2026-08-10T11:30:00Z",
            expected_source_registry=admitted["registry"]["content_sha256"],
            expected_current_test=diverged_variant,
            expected_current_assignment=admitted[
                "assignment_content_sha256"
            ],
            expected_new_variant=normal_variant,
            expected_parent_variant=parent_variant,
            expected_parent_registry=admitted["registry"]["content_sha256"],
        )
        self.assertEqual([], normalized["registry"]["source_order_outliers"])
        self.assertIsNone(normalized["source_order_outlier"])
        self.assertEqual({}, normalized["registry"]["tracks"]["edge"]["deferred"])

    def test_universal_test_admission_requires_explicit_supported_applicability(
        self,
    ) -> None:
        pin_index = copy.deepcopy(self.pin_index)
        pin_index["alpha-universal-dual"] = self._pin(
            "alpha-universal-dual", "3", None
        )
        pin_index["alpha-universal-dual"]["architectures"] = ["arm64", "armhf"]
        document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        new_cell = {
            "build_pin_id": "alpha-universal-dual",
            "tuning_profile": UNIVERSAL_TUNING_PROFILE,
            "applicable_chipsets": ["a33", "a523"],
        }
        new_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=new_cell,
            pin_index=pin_index,
            tunings=self.tunings,
        )
        parent_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=pin_index,
            tunings=self.tunings,
        )
        result = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: True,
            track="edge",
            core_id="alpha",
            chipset="universal",
            pin_id="alpha-universal-dual",
            tuning_profile=UNIVERSAL_TUNING_PROFILE,
            slice_time=self._slice_time("edge"),
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=new_variant,
            expected_parent_variant=parent_variant,
            expected_parent_registry=document["content_sha256"],
            applicable_chipsets=["a33", "a523"],
        )
        self.assertEqual(
            {**new_cell, "version_slice": result["version_slice"]},
            result["registry"]["tracks"]["edge"]["test"]["alpha"][
                "universal"
            ],
        )

        cases = (
            (None, UNIVERSAL_TUNING_PROFILE, pin_index, "explicit applicable"),
            (
                ["a523", "a33"],
                UNIVERSAL_TUNING_PROFILE,
                pin_index,
                "unique sorted",
            ),
            (
                ["a33", "a523"],
                "h700-cortex-a53-v1",
                pin_index,
                "universal profile",
            ),
        )
        arm64_only = copy.deepcopy(pin_index)
        arm64_only["alpha-universal-dual"]["architectures"] = ["arm64"]
        cases += (
            (
                ["a33", "a523"],
                UNIVERSAL_TUNING_PROFILE,
                arm64_only,
                "universal profile and applicability",
            ),
        )
        for applicability, profile, case_pins, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(
                PipelineError, error
            ):
                set_core_track_test(
                    document,
                    repository_root=ROOT,
                    catalog=self.catalog,
                    pin_index=case_pins,
                    tunings=self.tunings,
                    main_release_roster=self.release_roster,
                    spruce_branch_bases=self.branch_bases,
                    source_registry_index=self.source_registry_index,
                    source_ancestry_verifier=lambda *_args: True,
                    track="edge",
                    core_id="alpha",
                    chipset="universal",
                    pin_id="alpha-universal-dual",
                    tuning_profile=profile,
                    slice_time=self._slice_time("edge"),
                    expected_source_registry=document["content_sha256"],
                    expected_current_test="absent",
                    expected_current_assignment="absent",
                    expected_new_variant=new_variant,
                    expected_parent_variant=parent_variant,
                    expected_parent_registry=document["content_sha256"],
                    applicable_chipsets=applicability,
                )

    def test_local_git_ancestry_verifier_uses_only_matching_cached_graphs(
        self,
    ) -> None:
        repository = "https://example.invalid/alpha.git"
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "source-repositories"
            worktree = Path(temporary) / "worktree"
            pipeline.run(["git", "init", str(worktree)])
            pipeline.run(["git", "-C", str(worktree), "config", "user.name", "Test"])
            pipeline.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "config",
                    "user.email",
                    "test@example.invalid",
                ]
            )
            tracked = worktree / "tracked.txt"
            tracked.write_text("one\n", encoding="utf-8")
            pipeline.run(["git", "-C", str(worktree), "add", "tracked.txt"])
            pipeline.run(["git", "-C", str(worktree), "commit", "-m", "one"])
            ancestor = pipeline.run(
                ["git", "-C", str(worktree), "rev-parse", "HEAD"]
            ).stdout.strip()
            tracked.write_text("two\n", encoding="utf-8")
            pipeline.run(["git", "-C", str(worktree), "commit", "-am", "two"])
            descendant = pipeline.run(
                ["git", "-C", str(worktree), "rev-parse", "HEAD"]
            ).stdout.strip()
            pipeline.run(
                ["git", "-C", str(worktree), "checkout", "--orphan", "unrelated"]
            )
            pipeline.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "commit",
                    "--allow-empty",
                    "-m",
                    "unrelated",
                ]
            )
            unrelated = pipeline.run(
                ["git", "-C", str(worktree), "rev-parse", "HEAD"]
            ).stdout.strip()
            cache.mkdir()
            source = cache / "alpha.git"
            pipeline.run(["git", "clone", "--mirror", str(worktree), str(source)])
            pipeline.run(
                [
                    "git",
                    f"--git-dir={source}",
                    "config",
                    "remote.origin.url",
                    repository,
                ]
            )

            verifier = local_git_source_ancestry_verifier(cache)
            self.assertTrue(verifier("alpha", repository, ancestor, descendant))

            original_run = subprocess.run
            observed_git_commands: list[list[str]] = []

            def capture_git(*args, **kwargs):
                command = args[0]
                if isinstance(command, list) and command[:1] == ["git"]:
                    observed_git_commands.append(command)
                return original_run(*args, **kwargs)

            with mock.patch("core_pipeline_lib.tracks.subprocess.run", capture_git):
                self.assertTrue(verifier("alpha", repository, ancestor, descendant))
            self.assertTrue(observed_git_commands)
            self.assertTrue(
                all(
                    command[1:4] == [
                        "--no-replace-objects",
                        "-c",
                        "core.commitGraph=false",
                    ]
                    for command in observed_git_commands
                )
            )
            self.assertTrue(
                any(
                    command[-3:]
                    == ["rev-parse", "--path-format=absolute", "--git-common-dir"]
                    for command in observed_git_commands
                )
            )
            self.assertFalse(verifier("alpha", repository, descendant, ancestor))
            self.assertFalse(
                verifier(
                    "alpha",
                    "https://example.invalid/other.git",
                    ancestor,
                    descendant,
                )
            )
            self.assertFalse(verifier("alpha", repository, "f" * 40, descendant))
            self.assertFalse(verifier("missing", repository, ancestor, descendant))

            pipeline.run(
                [
                    "git",
                    f"--git-dir={source}",
                    "replace",
                    unrelated,
                    descendant,
                ]
            )
            self.assertEqual(
                0,
                pipeline.run(
                    [
                        "git",
                        f"--git-dir={source}",
                        "merge-base",
                        "--is-ancestor",
                        ancestor,
                        unrelated,
                    ],
                    check=False,
                ).returncode,
            )
            self.assertFalse(verifier("alpha", repository, ancestor, unrelated))

            (source / "objects" / "info" / "alternates").write_text(
                str(worktree / ".git" / "objects") + "\n",
                encoding="utf-8",
            )
            self.assertFalse(verifier("alpha", repository, ancestor, descendant))
            (source / "objects" / "info" / "alternates").unlink()
            (source / "shallow").write_text(descendant + "\n", encoding="utf-8")
            self.assertFalse(verifier("alpha", repository, ancestor, descendant))
            (source / "shallow").unlink()
            external_common = Path(temporary) / "external-common.git"
            external_common.mkdir()
            (source / "commondir").write_text(
                str(external_common) + "\n", encoding="utf-8"
            )
            with mock.patch(
                "core_pipeline_lib.tracks.subprocess.run",
                side_effect=AssertionError("Git must not run for commondir mirrors"),
            ):
                self.assertFalse(
                    verifier("alpha", repository, ancestor, descendant)
                )

    def test_tracks_bind_branch_bases_and_roster_is_historical_only(self) -> None:
        self.assertEqual(
            [],
            spruce_release_roster_errors(
                self.live_release_roster,
                catalog=self.live_catalog,
            ),
        )
        self.assertEqual(
            "45810e6b2b5915f83e426ba6e8aeb801472de879",
            self.live_release_roster["release"]["commit"],
        )
        self.assertEqual(
            "00b53dd6081d4bef7d3609610d3211f86fd180e9",
            self.live_release_roster["release"]["tree"],
        )
        self.assertEqual(
            "logical-core-name-correlation-only-v1",
            self.live_release_roster["correlation_model"],
        )
        self.assertEqual(100, len(self.live_release_roster["cataloged_core_ids"]))
        self.assertEqual(
            {
                "km_flycast_xtreme",
                "km_ludicrousn64_2k22_xtreme_amped",
                "mkxp-z",
                "mupen64plus",
            },
            set(self.live_release_roster["uncataloged_core_ids"]),
        )
        self.assertEqual(
            "spruce-main",
            self.live_tracks["tracks"]["main"]["spruce_branch_basis"][
                "basis_id"
            ],
        )
        for track in ("nightly", "edge"):
            self.assertEqual(
                "spruce-development",
                self.live_tracks["tracks"][track]["spruce_branch_basis"][
                    "basis_id"
                ],
            )

        stale_binding = copy.deepcopy(self.live_tracks)
        stale_binding["tracks"]["main"]["spruce_branch_basis"][
            "basis_content_sha256"
        ] = "0" * 64
        _rehash_tracks(stale_binding)
        with self.assertRaisesRegex(PipelineError, "spruce_branch_basis is stale"):
            validate_core_tracks(
                stale_binding,
                catalog=self.live_catalog,
                pin_index=self.live_pins,
                tunings=self.live_tunings,
                main_release_roster=self.live_release_roster,
                spruce_branch_bases=self.live_branch_bases,
                source_registry_index=self.live_source_registries,
            )

        invalid_correlation = copy.deepcopy(self.live_release_roster)
        invalid_correlation["correlation_model"] = "artifact-reproduction-v1"
        invalid_correlation["content_sha256"] = (
            spruce_release_roster_content_sha256(invalid_correlation)
        )
        self.assertIn(
            "Spruce release roster correlation model is invalid",
            spruce_release_roster_errors(
                invalid_correlation,
                catalog=self.live_catalog,
            ),
        )

    def test_stable_rows_project_approval_and_origins_stay_in_ancestry(self) -> None:
        approval_keys = {
            "approved_test_variant_id",
            "approved_test_origin_track",
            "approved_at",
            "approved_by",
            "reason",
            "previous_stable_variant_id",
            "source_registry_content_sha256",
        }
        stable_cell = self._stable_cell(self.h700_cell, chipset="h700")
        document = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={"h700": stable_cell},
        )

        row = self._resolve(
            document, track="main", marker="stable", chipset="h700"
        )
        recorded_stable = document["tracks"]["main"]["stable"]["alpha"]["h700"]
        self.assertEqual(
            {key: recorded_stable[key] for key in approval_keys}, row["approval"]
        )
        self.assertTrue(approval_keys.isdisjoint(row))
        self.assertEqual("main", row["test_origin_track"])
        self.assertEqual(["arm64"], row["selected_architectures"])

        future_origin = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(
                    self.h700_cell, chipset="h700", origin_track="nightly"
                )
            },
        )
        with self.assertRaisesRegex(
            PipelineError, "approved_test_origin_track is invalid"
        ):
            validate_core_tracks(
                future_origin,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

        ancestral_origin = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            edge_stable={
                "h700": self._stable_cell(
                    self.h700_cell, chipset="h700", origin_track="nightly"
                )
            },
        )
        validated = validate_core_tracks(
            ancestral_origin,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
        )
        edge_row = self._resolve(
            validated, track="edge", marker="stable", chipset="h700"
        )
        self.assertEqual("nightly", edge_row["approval"]["approved_test_origin_track"])

    def test_stable_requires_a_tracked_source_registry_snapshot(self) -> None:
        document = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700")
            },
        )
        with self.assertRaisesRegex(PipelineError, "has no tracked snapshot"):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index={},
            )

    def test_stable_provenance_recursively_rejects_fabricated_prior_approval(
        self,
    ) -> None:
        prior = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700")
            },
        )
        prior_stable = prior["tracks"]["main"]["stable"]["alpha"]["h700"]
        prior_stable["source_registry_content_sha256"] = "f" * 64
        _rehash_tracks(prior)

        current = copy.deepcopy(prior)
        current_stable = current["tracks"]["main"]["stable"]["alpha"]["h700"]
        current_stable["source_registry_content_sha256"] = prior["content_sha256"]
        current_stable["previous_stable_variant_id"] = current_stable[
            "approved_test_variant_id"
        ]
        _rehash_tracks(current)
        source_index = dict(self.source_registry_index)
        source_index[prior["content_sha256"]] = {
            "path": "synthetic-prior.json",
            "file_sha256": "0" * 64,
            "source_registry": prior,
        }

        with self.assertRaisesRegex(PipelineError, "has no tracked snapshot"):
            validate_core_tracks(
                current,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=source_index,
            )

    def test_stable_provenance_rejects_cycles_and_excessive_depth(self) -> None:
        cyclic = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700")
            },
        )
        cyclic_digest = "c" * 64
        cyclic_stable = cyclic["tracks"]["main"]["stable"]["alpha"]["h700"]
        cyclic_stable["previous_stable_variant_id"] = cyclic_stable[
            "approved_test_variant_id"
        ]
        cyclic["tracks"]["main"]["stable"]["alpha"]["h700"][
            "source_registry_content_sha256"
        ] = cyclic_digest
        cyclic["content_sha256"] = cyclic_digest
        cyclic_index = {
            cyclic_digest: {
                "path": "synthetic-cycle.json",
                "file_sha256": "0" * 64,
                "source_registry": cyclic,
            }
        }
        with mock.patch(
            "scripts.core_pipeline_lib.tracks.core_tracks_content_sha256",
            side_effect=lambda document: document["content_sha256"],
        ), self.assertRaisesRegex(PipelineError, "snapshot cycle detected"):
            validate_core_tracks(
                cyclic,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=cyclic_index,
            )

        base = self._track_document(main_test={"h700": self.h700_cell})
        source_index = dict(self.source_registry_index)
        previous = base
        variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=self.h700_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        for depth in range(MAX_STABLE_PROVENANCE_DEPTH + 1):
            current = copy.deepcopy(previous)
            stable = self._stable_cell(self.h700_cell, chipset="h700")
            stable["source_registry_content_sha256"] = previous["content_sha256"]
            stable["previous_stable_variant_id"] = None if depth == 0 else variant
            current["tracks"]["main"]["stable"] = {"alpha": {"h700": stable}}
            _rehash_tracks(current)
            source_index[previous["content_sha256"]] = {
                "path": f"synthetic-depth-{depth}.json",
                "file_sha256": "0" * 64,
                "source_registry": previous,
            }
            previous = current

        with self.assertRaisesRegex(PipelineError, "depth exceeds"):
            validate_core_tracks(
                previous,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=source_index,
            )

    def test_stable_provenance_depth_is_per_coordinate_not_global_history(
        self,
    ) -> None:
        core_ids = [f"core{index:03d}" for index in range(65)]
        catalog = {
            "cores": {
                core_id: {
                    "source": {
                        "url": f"https://example.invalid/{core_id}.git",
                        "requested_ref": "refs/heads/main",
                    }
                }
                for core_id in core_ids
            }
        }
        roster = self._release_roster(core_ids)
        pin_index: dict[str, dict] = {}
        test_cells: dict[str, dict] = {}
        heads: dict[str, dict] = {}
        main_slice, main_slice_basis = track_model.core_track_version_slice(
            track="main",
            slice_time=self._slice_time("main"),
            spruce_branch_bases=self.branch_bases,
        )
        for core_id in core_ids:
            identity = hashlib.sha256(core_id.encode()).hexdigest()
            pin_id = f"{core_id}-universal"
            pin = self._pin(pin_id, "1", None)
            pin.update(
                {
                    "path": f"pins/core-sets/{pin_id}.json",
                    "pin_id": pin_id,
                    "file_sha256": identity,
                    "content_sha256": identity,
                    "core_id": core_id,
                    "artifact_sha256": {"arm64": identity},
                    "source_repository": f"https://example.invalid/{core_id}.git",
                }
            )
            pin_index[pin_id] = pin
            test_cells[core_id] = {
                "universal": {
                    "build_pin_id": pin_id,
                    "tuning_profile": UNIVERSAL_TUNING_PROFILE,
                    "applicable_chipsets": ["h700"],
                    "version_slice": copy.deepcopy(main_slice),
                }
            }
            heads[core_id] = {
                "repository": pin["source_repository"],
                "requested_ref": pin["source_requested_ref"],
                "commit": pin["source_commit"],
                "tree": pin["source_tree"],
                "latest_semantics": "exact-branch-tip",
                "status": "unchanged",
            }

        document = self._track_document()
        document["version_policy"]["edge_latest"]["heads"] = heads
        document["historical_release_correlation"][
            "roster_content_sha256"
        ] = roster["content_sha256"]
        document["tracks"]["main"]["test"] = test_cells
        document["version_policy"]["slice_comparison_bases"] = {
            main_slice["content_sha256"]: main_slice_basis
        }
        document["version_policy"]["slice_branch_basis_snapshots"] = {
            self.branch_bases["content_sha256"]: (
                track_model._slice_branch_basis_snapshot(
                    spruce_branch_bases=self.branch_bases,
                    catalog=catalog,
                    main_release_roster=roster,
                    catalog_file_sha256="a" * 64,
                    release_roster_file_sha256="b" * 64,
                )
            )
        }
        document["tracks"]["main"]["deferred"] = {}
        document["tracks"]["main"]["stable"] = {}
        _rehash_tracks(document)
        source_index: dict[str, dict] = {}
        for core_id in core_ids:
            source = copy.deepcopy(document)
            digest = source["content_sha256"]
            source_index[digest] = {
                "path": f"synthetic-distinct-{core_id}.json",
                "file_sha256": "0" * 64,
                "source_registry": source,
            }
            cell = test_cells[core_id]["universal"]
            stable = copy.deepcopy(cell)
            stable.update(
                {
                    "approved_test_variant_id": core_variant_id(
                        core_id=core_id,
                        cell_chipset="universal",
                        cell=cell,
                        pin_index=pin_index,
                        tunings=self.tunings,
                    ),
                    "approved_test_origin_track": "main",
                    "approved_at": "2026-08-10T12:00:00Z",
                    "approved_by": "test-approver",
                    "reason": "First approval for one independent coordinate.",
                    "previous_stable_variant_id": None,
                    "source_registry_content_sha256": digest,
                }
            )
            document["tracks"]["main"]["stable"][core_id] = {
                "universal": stable
            }
            document["tracks"]["main"]["stable"] = dict(
                sorted(document["tracks"]["main"]["stable"].items())
            )
            _rehash_tracks(document)

        validate_core_tracks(
            document,
            catalog=catalog,
            pin_index=pin_index,
            tunings=self.tunings,
            main_release_roster=roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=source_index,
        )

    def test_stable_must_be_effective_test_in_its_source_snapshot(self) -> None:
        document = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700")
            },
        )
        unrelated_source = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        document["tracks"]["main"]["stable"]["alpha"]["h700"][
            "source_registry_content_sha256"
        ] = unrelated_source["content_sha256"]
        _rehash_tracks(document)
        with self.assertRaisesRegex(PipelineError, "not an effective test cell"):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

    def test_promotion_compare_and_swap_matches_exact_test_variant(self) -> None:
        source = self._track_document(main_test={"h700": self.h700_cell})
        expected = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=self.h700_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        result = promote_core_track_test(
            source,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index={},
            track="main",
            core_id="alpha",
            chipset="h700",
            approved_at="2026-08-09T12:00:00Z",
            approved_by="test-approver",
            reason="Reviewed exact TEST variant.",
            expected_test_variant=expected,
            expected_current_stable="absent",
        )
        self.assertEqual(expected, result["stable_cell"]["approved_test_variant_id"])
        self.assertEqual(
            source["content_sha256"],
            result["stable_cell"]["source_registry_content_sha256"],
        )
        test_slice = source["tracks"]["main"]["test"]["alpha"]["h700"][
            "version_slice"
        ]
        self.assertEqual(test_slice, result["stable_cell"]["version_slice"])
        self.assertEqual(
            test_slice,
            result["registry"]["tracks"]["main"]["stable"]["alpha"][
                "h700"
            ]["version_slice"],
        )
        resolved = self._resolve(
            result["registry"],
            track="main",
            marker="stable",
            chipset="h700",
        )
        self.assertEqual(test_slice, resolved["version_slice"])
        self.assertEqual(
            source["version_policy"]["slice_comparison_bases"][
                test_slice["content_sha256"]
            ],
            resolved["slice_comparison_basis"],
        )

        with self.assertRaisesRegex(PipelineError, "changed since approval review"):
            promote_core_track_test(
                source,
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index={},
                track="main",
                core_id="alpha",
                chipset="h700",
                approved_at="2026-08-09T12:00:00Z",
                approved_by="test-approver",
                reason="Reviewed exact TEST variant.",
                expected_test_variant="0" * 64,
                expected_current_stable="absent",
            )

        with self.assertRaisesRegex(PipelineError, "expected .* found absent"):
            promote_core_track_test(
                source,
                repository_root=ROOT,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index={},
                track="main",
                core_id="alpha",
                chipset="h700",
                approved_at="2026-08-09T12:00:00Z",
                approved_by="test-approver",
                reason="Reviewed exact TEST variant.",
                expected_test_variant=expected,
                expected_current_stable="f" * 64,
            )

    def test_promotion_advances_stable_only_with_exact_current_stable_cas(self) -> None:
        source = self._track_document(main_test={"h700": self.h700_cell})
        first_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=self.h700_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        first = promote_core_track_test(
            source,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index={},
            track="main",
            core_id="alpha",
            chipset="h700",
            approved_at="2026-08-09T12:00:00Z",
            approved_by="first-approver",
            reason="Initial approval.",
            expected_test_variant=first_variant,
            expected_current_stable="absent",
        )
        first_source_digest = first["stable_cell"][
            "source_registry_content_sha256"
        ]
        first_source_index = {
            first_source_digest: {
                "path": first["snapshot_path"],
                "file_sha256": first["snapshot_file_sha256"],
                "source_registry": copy.deepcopy(first["snapshot"]["source_registry"]),
            }
        }

        h700_tuning = resolved_tuning_profile(
            self.tunings, "h700-cortex-a53-v1"
        )
        self.pin_index["alpha-h700-next"] = self._pin(
            "alpha-h700-next",
            "4",
            {
                "profile_id": h700_tuning["profile_id"],
                "content_sha256": h700_tuning["content_sha256"],
            },
        )
        next_cell, _next_slice_basis = self._versioned_cell(
            {
                **self.h700_cell,
                "build_pin_id": "alpha-h700-next",
            },
            track="main",
            slice_time="2026-08-10T10:30:00Z",
        )
        advanced_source = copy.deepcopy(first["registry"])
        advanced_source["tracks"]["main"]["test"]["alpha"]["h700"] = next_cell
        self._register_cell_slice(advanced_source, next_cell)
        _rehash_tracks(advanced_source)
        next_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=next_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )

        for expected_current in ("absent", "0" * 64):
            with self.subTest(expected_current=expected_current), self.assertRaisesRegex(
                PipelineError, "current stable core track cell changed"
            ):
                promote_core_track_test(
                    advanced_source,
                    repository_root=ROOT,
                    catalog=self.catalog,
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                    main_release_roster=self.release_roster,
                    spruce_branch_bases=self.branch_bases,
                    source_registry_index=first_source_index,
                    track="main",
                    core_id="alpha",
                    chipset="h700",
                    approved_at="2026-08-10T12:00:00Z",
                    approved_by="second-approver",
                    reason="Advance reviewed stable.",
                    expected_test_variant=next_variant,
                    expected_current_stable=expected_current,
                )

        advanced = promote_core_track_test(
            advanced_source,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=first_source_index,
            track="main",
            core_id="alpha",
            chipset="h700",
            approved_at="2026-08-10T12:00:00Z",
            approved_by="second-approver",
            reason="Advance reviewed stable.",
            expected_test_variant=next_variant,
            expected_current_stable=first_variant,
        )

        self.assertEqual(first_variant, advanced["previous_stable_variant_id"])
        self.assertEqual(next_variant, advanced["stable_cell"]["approved_test_variant_id"])
        self.assertEqual(
            first_variant,
            advanced["stable_cell"]["previous_stable_variant_id"],
        )
        self.assertEqual(advanced_source, advanced["snapshot"]["source_registry"])
        self.assertEqual(
            first_variant,
            advanced["snapshot"]["source_registry"]["tracks"]["main"]["stable"]
            ["alpha"]["h700"]["approved_test_variant_id"],
        )
        self.assertEqual(
            advanced_source["content_sha256"],
            advanced["stable_cell"]["source_registry_content_sha256"],
        )

        forged_lineage = copy.deepcopy(advanced["registry"])
        forged_lineage["tracks"]["main"]["stable"]["alpha"]["h700"][
            "previous_stable_variant_id"
        ] = None
        _rehash_tracks(forged_lineage)
        advanced_source_digest = advanced_source["content_sha256"]
        advanced_index = dict(first_source_index)
        advanced_index[advanced_source_digest] = {
            "path": advanced["snapshot_path"],
            "file_sha256": advanced["snapshot_file_sha256"],
            "source_registry": advanced["snapshot"]["source_registry"],
        }
        with self.assertRaisesRegex(
            PipelineError, "previous_stable_variant_id differs"
        ):
            validate_core_tracks(
                forged_lineage,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=advanced_index,
            )

    def test_approval_metadata_is_nonblank_and_timestamp_is_real_canonical_utc(self) -> None:
        source = self._track_document(main_test={"h700": self.h700_cell})
        expected = core_variant_id(
            core_id="alpha",
            cell_chipset="h700",
            cell=self.h700_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        common = {
            "document": source,
            "repository_root": ROOT,
            "catalog": self.catalog,
            "pin_index": self.pin_index,
            "tunings": self.tunings,
            "main_release_roster": self.release_roster,
            "spruce_branch_bases": self.branch_bases,
            "source_registry_index": {},
            "track": "main",
            "core_id": "alpha",
            "chipset": "h700",
            "approved_at": "2028-02-29T12:00:00Z",
            "approved_by": "approver",
            "reason": "Reviewed.",
            "expected_test_variant": expected,
            "expected_current_stable": "absent",
        }
        accepted = promote_core_track_test(**common)
        self.assertEqual(
            "2028-02-29T12:00:00Z", accepted["stable_cell"]["approved_at"]
        )

        invalid_values = (
            ("approved_at", "2026-02-29T12:00:00Z", "timestamp is invalid"),
            ("approved_at", "2028-02-29T12:00:00+00:00", "timestamp is invalid"),
            ("approved_by", " \t", "approver is invalid"),
            ("reason", "\n ", "reason is invalid"),
        )
        for field, value, message in invalid_values:
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                PipelineError, message
            ):
                arguments = dict(common)
                arguments[field] = value
                promote_core_track_test(**arguments)

        invalid_registry = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700")
            },
        )
        for field, value in (
            ("approved_at", "2026-02-31T12:00:00Z"),
            ("approved_by", " \t"),
            ("reason", "\n "),
        ):
            with self.subTest(registry_field=field), self.assertRaisesRegex(
                PipelineError, rf"{field} is invalid"
            ):
                mutated = copy.deepcopy(invalid_registry)
                mutated["tracks"]["main"]["stable"]["alpha"]["h700"][field] = value
                _rehash_tracks(mutated)
                validate_core_tracks(
                    mutated,
                    catalog=self.catalog,
                    pin_index=self.pin_index,
                    tunings=self.tunings,
                    main_release_roster=self.release_roster,
                    spruce_branch_bases=self.branch_bases,
                    source_registry_index=self.source_registry_index,
                )

    def test_stable_resolution_precedence_is_exact_then_universal_then_tests(self) -> None:
        document = self._track_document(
            main_test={"h700": self.h700_cell, "universal": self.universal_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700"),
                "universal": self._stable_cell(
                    self.universal_cell, chipset="universal"
                ),
            },
        )

        exact_stable = self._resolve(
            document, track="main", marker="stable", chipset="h700"
        )
        self.assertEqual(
            ("h700", "exact_stable"),
            (exact_stable["selected_chipset"], exact_stable["resolution"]),
        )

        del document["tracks"]["main"]["stable"]["alpha"]["h700"]
        _rehash_tracks(document)
        universal_stable = self._resolve(
            document, track="main", marker="stable", chipset="h700"
        )
        self.assertEqual("universal_stable_fallback", universal_stable["resolution"])
        self.assertEqual("stable", universal_stable["selected_state"])

        del document["tracks"]["main"]["stable"]["alpha"]["universal"]
        del document["tracks"]["main"]["stable"]["alpha"]
        _rehash_tracks(document)
        exact_test = self._resolve(
            document, track="main", marker="stable", chipset="h700"
        )
        self.assertEqual("exact_test_unstable_fallback", exact_test["resolution"])

        del document["tracks"]["main"]["test"]["alpha"]["h700"]
        _rehash_tracks(document)
        universal_test = self._resolve(
            document, track="main", marker="stable", chipset="h700"
        )
        self.assertEqual(
            "universal_test_unstable_fallback", universal_test["resolution"]
        )

    def test_universal_stable_outranks_an_exact_unapproved_test(self) -> None:
        document = self._track_document(
            main_test={"h700": self.h700_cell, "universal": self.universal_cell},
            main_stable={
                "universal": self._stable_cell(
                    self.universal_cell, chipset="universal"
                )
            },
        )

        selected = self._resolve(
            document, track="main", marker="stable", chipset="h700"
        )

        self.assertEqual("universal", selected["selected_chipset"])
        self.assertEqual("stable", selected["stability"])
        self.assertEqual("universal_stable_fallback", selected["resolution"])

    def test_test_view_ignores_stable_cells_and_prefers_exact_test(self) -> None:
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            main_stable={
                "universal": self._stable_cell(
                    self.universal_cell, chipset="universal"
                )
            },
        )

        fallback = self._resolve(
            document, track="main", marker="test", chipset="h700"
        )
        self.assertEqual("test", fallback["selected_state"])
        self.assertEqual("universal_test_fallback", fallback["resolution"])

        h700_cell, _h700_basis = self._versioned_cell(
            self.h700_cell,
            track="main",
        )
        document["tracks"]["main"]["test"]["alpha"]["h700"] = h700_cell
        document["tracks"]["main"]["test"]["alpha"] = dict(
            sorted(document["tracks"]["main"]["test"]["alpha"].items())
        )
        self._register_cell_slice(document, h700_cell)
        _rehash_tracks(document)
        exact = self._resolve(
            document, track="main", marker="test", chipset="h700"
        )
        self.assertEqual("test", exact["selected_state"])
        self.assertEqual("exact_test", exact["resolution"])
        self.assertEqual("alpha-h700", exact["pin"]["pin_id"])

    def test_real_chipset_cells_never_cross_fallback(self) -> None:
        universal_h700_only = copy.deepcopy(self.universal_cell)
        universal_h700_only["applicable_chipsets"] = ["h700"]
        document = self._track_document(
            main_test={"universal": universal_h700_only},
            nightly_test={"h700": self.h700_cell},
            nightly_stable={
                "h700": self._stable_cell(
                    self.h700_cell, chipset="h700", origin_track="nightly"
                )
            },
        )

        self.assertIsNone(
            self._resolve(
                document, track="nightly", marker="stable", chipset="rk3566"
            )
        )
        self.assertIsNone(
            self._resolve(
                document, track="edge", marker="test", chipset="rk3566"
            )
        )

    def test_inventory_state_and_completeness_are_explicit(self) -> None:
        stable_document = self._track_document(
            main_test={"h700": self.h700_cell},
            main_stable={
                "h700": self._stable_cell(self.h700_cell, chipset="h700")
            },
        )
        stable = construct_core_track_inventory(
            stable_document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="main-stable:h700",
            source_registry_index=self.source_registry_index,
        )
        self.assertEqual("stable", stable["inventory_state"])
        self.assertIs(stable["complete"], True)
        self.assertEqual("static-build-selection-only", stable["validation_scope"])
        self.assertEqual(
            _semantic_sha256(self.catalog), stable["catalog_content_sha256"]
        )
        self.assertEqual(["arm64"], stable["cores"][0]["selected_architectures"])

        unavailable_document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        unavailable = construct_core_track_inventory(
            unavailable_document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="main-test:ssd202d",
            source_registry_index=self.source_registry_index,
        )
        self.assertEqual("unavailable", unavailable["inventory_state"])
        self.assertIs(unavailable["complete"], False)
        self.assertEqual([], unavailable["cores"])
        self.assertEqual(["alpha"], unavailable["unsupported_core_ids"])

    def test_deferred_inventory_and_test_admission_are_atomic(self) -> None:
        document = self._track_document()
        deferred = construct_core_track_inventory(
            document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="main-test:universal",
            source_registry_index=self.source_registry_index,
        )
        self.assertEqual("deferred", deferred["inventory_state"])
        self.assertIs(deferred["complete"], False)
        self.assertEqual([], deferred["cores"])
        self.assertEqual(
            "no-reviewed-version-channel-build-pin",
            deferred["deferred_cores"][0]["reason"],
        )
        self.assertIsNone(
            deferred["deferred_cores"][0][
                "current_assignment_content_sha256"
            ]
        )

        new_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=self.pin_index,
            tunings=self.tunings,
        )
        result = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=None,
            track="main",
            core_id="alpha",
            chipset="universal",
            pin_id="alpha-universal",
            tuning_profile=UNIVERSAL_TUNING_PROFILE,
            slice_time=self._slice_time("main"),
            applicable_chipsets=["h700", "rk3566"],
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=new_variant,
            expected_parent_variant=None,
            expected_parent_registry=None,
        )
        self.assertEqual(
            {**self.universal_cell, "version_slice": result["version_slice"]},
            result["registry"]["tracks"]["main"]["test"]["alpha"][
                "universal"
            ],
        )
        self.assertEqual(
            {"state": "deferred", "reason": "no-reviewed-version-channel-build-pin"},
            result["previous_deferred"],
        )
        self.assertEqual({}, result["registry"]["tracks"]["main"]["deferred"])
        self.assertIsNone(result["edge_deferred_by_admission"])
        admitted_inventory = construct_core_track_inventory(
            result["registry"],
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="main-test:universal",
            source_registry_index=self.source_registry_index,
        )
        self.assertEqual(
            result["assignment_content_sha256"],
            admitted_inventory["cores"][0][
                "current_assignment_content_sha256"
            ],
        )

    def test_main_admission_masks_and_unmasks_inherited_edge_source(self) -> None:
        document = self._track_document()
        pins = copy.deepcopy(self.pin_index)
        pins["alpha-stale"] = self._pin("alpha-stale", "9", None)
        pins["alpha-stale"]["source_commit"] = "c" * 40
        pins["alpha-stale"]["source_tree"] = "d" * 40
        stale_cell = {
            **self.universal_cell,
            "build_pin_id": "alpha-stale",
        }
        stale_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=stale_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        stale = set_core_track_test(
            document,
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=None,
            track="main",
            core_id="alpha",
            chipset="universal",
            pin_id="alpha-stale",
            tuning_profile=UNIVERSAL_TUNING_PROFILE,
            slice_time=self._slice_time("main"),
            applicable_chipsets=["h700", "rk3566"],
            expected_source_registry=document["content_sha256"],
            expected_current_test="absent",
            expected_current_assignment="absent",
            expected_new_variant=stale_variant,
            expected_parent_variant=None,
            expected_parent_registry=None,
        )
        expected_mask = {
            "track": "edge",
            "core_id": "alpha",
            "chipset": "universal",
            "state": "deferred",
            "reason": "no-reviewed-version-channel-build-pin",
        }
        self.assertEqual(expected_mask, stale["edge_deferred_by_admission"])
        self.assertEqual(
            {"state": "deferred", "reason": "no-reviewed-version-channel-build-pin"},
            stale["registry"]["tracks"]["edge"]["deferred"]["alpha"][
                "universal"
            ],
        )

        latest_variant = core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=self.universal_cell,
            pin_index=pins,
            tunings=self.tunings,
        )
        latest = set_core_track_test(
            stale["registry"],
            repository_root=ROOT,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=None,
            track="main",
            core_id="alpha",
            chipset="universal",
            pin_id="alpha-universal",
            tuning_profile=UNIVERSAL_TUNING_PROFILE,
            slice_time="2026-08-10T10:30:00Z",
            applicable_chipsets=["h700", "rk3566"],
            expected_source_registry=stale["registry"]["content_sha256"],
            expected_current_test=stale_variant,
            expected_current_assignment=stale[
                "assignment_content_sha256"
            ],
            expected_new_variant=latest_variant,
            expected_parent_variant=None,
            expected_parent_registry=None,
        )
        self.assertIsNone(latest["edge_deferred_by_admission"])
        self.assertEqual({}, latest["registry"]["tracks"]["edge"]["deferred"])

    def test_edge_latest_gate_uses_reviewed_source_not_branch_artifact_bytes(
        self,
    ) -> None:
        document = self._track_document(
            main_test={"universal": self.universal_cell}
        )
        self.assertEqual(
            [],
            _ORIGINAL_EDGE_LATEST_ERRORS(document, pin_index=self.pin_index),
        )

        changed_artifact = copy.deepcopy(self.pin_index)
        changed_artifact["alpha-universal"]["artifact_sha256"]["arm64"] = "9" * 64
        self.assertEqual(
            [],
            _ORIGINAL_EDGE_LATEST_ERRORS(document, pin_index=changed_artifact),
        )

        changed_source = copy.deepcopy(self.pin_index)
        changed_source["alpha-universal"]["source_commit"] = "c" * 40
        self.assertEqual(
            [
                "tracks.edge.test.alpha.universal pin does not match the "
                "latest reviewed upstream head"
            ],
            _ORIGINAL_EDGE_LATEST_ERRORS(document, pin_index=changed_source),
        )

        tag_gap = copy.deepcopy(document)
        tag_gap["version_policy"]["edge_latest"]["heads"]["alpha"].update(
            {
                "requested_ref": "refs/tags/v1",
                "latest_semantics": "catalog-tag-only-not-latest",
            }
        )
        self.assertTrue(
            _ORIGINAL_EDGE_LATEST_ERRORS(tag_gap, pin_index=self.pin_index)
        )

        divergent = copy.deepcopy(document)
        divergent["version_policy"]["edge_latest"]["heads"]["alpha"][
            "status"
        ] = "diverged"
        self.assertEqual(
            [],
            _ORIGINAL_EDGE_LATEST_ERRORS(divergent, pin_index=self.pin_index),
        )

    def test_edge_latest_gate_leaves_stable_to_historical_provenance(self) -> None:
        self.pin_index["alpha-stale"] = self._pin("alpha-stale", "9", None)
        self.pin_index["alpha-stale"]["source_commit"] = "c" * 40
        stale_cell = copy.deepcopy(self.universal_cell)
        stale_cell["build_pin_id"] = "alpha-stale"
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            edge_stable={
                "universal": self._stable_cell(
                    stale_cell,
                    chipset="universal",
                    origin_track="main",
                )
            },
        )
        self.assertEqual(
            [],
            _ORIGINAL_EDGE_LATEST_ERRORS(document, pin_index=self.pin_index),
        )

    def test_exact_source_order_outlier_is_bound_and_recorder_safe(self) -> None:
        child_pin = copy.deepcopy(self.pin_index["alpha-h700"])
        child_pin["source_commit"] = "c" * 40
        child_pin["source_tree"] = "d" * 40
        pins = copy.deepcopy(self.pin_index)
        pins["alpha-h700"] = child_pin
        document = self._track_document(
            main_test={"universal": self.universal_cell},
            nightly_test={"h700": self.h700_cell},
            pin_index=pins,
        )
        binding = track_model._source_order_outlier_binding(
            parent_binding=document["source_order_parent_bindings"][0],
        )
        document["source_order_outliers"] = [
            {
                **binding,
                "authorized_at": "2026-08-10T12:00:00Z",
                "authorized_by": "test-operator",
                "reason": "Reviewed non-linear upstream source edge.",
            }
        ]
        _rehash_tracks(document)

        validate_core_tracks(
            document,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: True,
        )
        validate_core_tracks(
            document,
            catalog=self.catalog,
            pin_index=pins,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            source_registry_index=self.source_registry_index,
            source_ancestry_verifier=lambda *_args: False,
        )

        stale = copy.deepcopy(document)
        stale["source_order_outliers"][0]["child_pin_content_sha256"] = "f" * 64
        _rehash_tracks(stale)
        with self.assertRaisesRegex(PipelineError, "outlier binding is stale"):
            validate_core_tracks(
                stale,
                catalog=self.catalog,
                pin_index=pins,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
                source_ancestry_verifier=lambda *_args: False,
            )

    def test_live_manifest_hashes_and_inventory_counts_are_deterministic(self) -> None:
        tunings = validate_chipset_tunings(self.live_tunings)
        tracks = validate_core_tracks(
            self.live_tracks,
            catalog=self.live_catalog,
            pin_index=self.live_pins,
            tunings=tunings,
            main_release_roster=self.live_release_roster,
            spruce_branch_bases=self.live_branch_bases,
            source_registry_index=self.live_source_registries,
        )

        self.assertEqual(
            "bfd465e63575b83a2ac6667c9c7aa864d169684cda7c360a2eb1e72d804eee00",
            tunings["content_sha256"],
        )
        self.assertEqual(
            chipset_tunings_content_sha256(tunings), tunings["content_sha256"]
        )
        self.assertEqual(
            "98eae53abc7fc347f45600cce1c0c25d3bab6db19584115d1b1c4dc0ede8a5d4",
            tracks["content_sha256"],
        )
        self.assertEqual(
            core_tracks_content_sha256(tracks), tracks["content_sha256"]
        )
        self.assertEqual(
            34, len(tracks["version_policy"]["slice_comparison_bases"])
        )
        self.assertEqual(
            1,
            len(tracks["version_policy"]["slice_branch_basis_snapshots"]),
        )
        self.assertEqual(22, len(tracks["source_order_parent_bindings"]))
        self.assertEqual([], tracks["source_order_outliers"])
        admitted = {
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
            {
                "main": admitted,
                "nightly": admitted - {"gambatte"},
                "edge": admitted - {"gambatte"},
            },
            {
                track: set(tracks["tracks"][track]["test"])
                for track in track_model.CORE_TRACKS
            },
        )
        self.assertTrue(
            all(
                tracks["tracks"][track]["stable"] == {}
                for track in track_model.CORE_TRACKS
            )
        )
        self.assertEqual(88, len(tracks["tracks"]["main"]["deferred"]))
        self.assertEqual({}, tracks["tracks"]["nightly"]["deferred"])
        self.assertEqual(
            {
                "gambatte": {
                    "universal": {
                        "state": "deferred",
                        "reason": "no-reviewed-version-channel-build-pin",
                    }
                }
            },
            tracks["tracks"]["edge"]["deferred"],
        )

        cases = {
            "main-stable:h700": {
                "content_sha256": (
                    "74f7cea60a88aebeb642c37ef1163f2bb0227fa840626cf286d60b32e11e316e"
                ),
            },
            "main-stable:a523": {
                "content_sha256": (
                    "c58f1fce145f20b5f9b64e833ec1bdad2eb08ce1e01a9f1af0352d8d8827b4f8"
                ),
            },
            "main-stable:a33": {
                "content_sha256": (
                    "b62debba27b036a581a14e21e1bb85858a1e2935cf7c853a2e05a7e9f8e90919"
                ),
            },
            "main-stable:ssd202d": {
                "content_sha256": (
                    "3057a5926a83de23a729b5d75d9607c8d2bce0097e1979ae2ebe8f38e3a6700b"
                ),
            },
        }
        expected_summary = {
            "selected_core_count": 12,
            "stable_core_count": 0,
            "unstable_core_count": 12,
            "deferred_core_count": 88,
            "unsupported_core_count": 0,
            "universal_fallback_count": 100,
        }
        catalog_identity = (
            "60f8bf70b2b4c88354560a2afe1a49e822f6c9949236812ff8fee6772583f269"
        )
        self.assertEqual(_semantic_sha256(self.live_catalog), catalog_identity)
        for group_tag, expected in cases.items():
            with self.subTest(group_tag=group_tag):
                inventory = construct_core_track_inventory(
                    tracks,
                    catalog=self.live_catalog,
                    pin_index=self.live_pins,
                    tunings=tunings,
                    main_release_roster=self.live_release_roster,
                    spruce_branch_bases=self.live_branch_bases,
                    group_tag=group_tag,
                    source_registry_index=self.live_source_registries,
                )
                self.assertEqual(expected_summary, inventory["summary"])
                self.assertEqual([], inventory["unsupported_core_ids"])
                self.assertEqual("static-build-selection-only", inventory["validation_scope"])
                self.assertIs(inventory["local_only"], True)
                self.assertEqual("disabled", inventory["publication"])
                self.assertEqual(catalog_identity, inventory["catalog_content_sha256"])
                self.assertEqual("deferred", inventory["inventory_state"])
                self.assertIs(inventory["complete"], False)
                self.assertEqual(
                    tracks["content_sha256"],
                    inventory["track_registry_content_sha256"],
                )
                self.assertEqual(
                    tunings["content_sha256"],
                    inventory["tuning_registry_content_sha256"],
                )
                self.assertEqual(
                    core_track_inventory_content_sha256(inventory),
                    inventory["content_sha256"],
                )
                self.assertEqual(
                    expected["content_sha256"], inventory["content_sha256"]
                )
                self.assertEqual(
                    sorted(admitted),
                    [row["core_id"] for row in inventory["cores"]],
                )
                self.assertEqual(88, len(inventory["deferred_cores"]))
                self.assertTrue(
                    all(
                        row["reason"]
                        == "no-reviewed-version-channel-build-pin"
                        and row["spruce_branch_basis"]
                        == tracks["tracks"]["main"]["spruce_branch_basis"]
                        for row in inventory["deferred_cores"]
                    )
                )

        universal = construct_core_track_inventory(
            tracks,
            catalog=self.live_catalog,
            pin_index=self.live_pins,
            tunings=tunings,
            main_release_roster=self.live_release_roster,
            spruce_branch_bases=self.live_branch_bases,
            group_tag="main-stable:universal",
            source_registry_index=self.live_source_registries,
        )
        self.assertEqual(
            "8706c4baac3af7ac94db68664c0bddd4a1787b857774aa6c7f4721bb4235b63d",
            universal["content_sha256"],
        )
        self.assertEqual("deferred", universal["inventory_state"])
        self.assertIs(universal["complete"], False)
        self.assertEqual(
            {
                **expected_summary,
                "universal_fallback_count": 0,
            },
            universal["summary"],
        )
        self.assertEqual(
            sorted(admitted),
            [row["core_id"] for row in universal["cores"]],
        )
        self.assertEqual(88, len(universal["deferred_cores"]))

    def test_live_registries_match_the_published_json_schemas(self) -> None:
        for stem in (
            "chipset-tunings",
            "core-tracks",
            "spruce-release-roster",
        ):
            with self.subTest(stem=stem):
                schema = _read_json(ROOT / "manifests" / f"{stem}.schema.json")
                document = _read_json(ROOT / "manifests" / f"{stem}.json")
                Draft202012Validator.check_schema(schema)
                errors = sorted(
                    Draft202012Validator(schema).iter_errors(document),
                    key=lambda error: tuple(str(part) for part in error.path),
                )
                self.assertEqual([], [error.message for error in errors])

    def test_live_inventories_match_the_published_json_schema(self) -> None:
        schema = _read_json(ROOT / "manifests/core-track-inventory.schema.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        for group_tag in (
            "main-stable:universal",
            "main-stable:h700",
            "main-stable:a523",
            "main-stable:a33",
            "main-stable:ssd202d",
        ):
            with self.subTest(group_tag=group_tag):
                inventory = construct_core_track_inventory(
                    self.live_tracks,
                    catalog=self.live_catalog,
                    pin_index=self.live_pins,
                    tunings=self.live_tunings,
                    main_release_roster=self.live_release_roster,
                    spruce_branch_bases=self.live_branch_bases,
                    group_tag=group_tag,
                    source_registry_index=self.live_source_registries,
                )
                errors = sorted(
                    validator.iter_errors(inventory),
                    key=lambda error: tuple(str(part) for part in error.path),
                )
                self.assertEqual([], [error.message for error in errors])

    def test_inventory_schema_rejects_cross_field_selection_contradictions(self) -> None:
        schema = _read_json(ROOT / "manifests/core-track-inventory.schema.json")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)

        exact_document = self._track_document(main_test={"h700": self.h700_cell})
        exact = construct_core_track_inventory(
            exact_document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="main-test:h700",
            source_registry_index=self.source_registry_index,
        )
        self.assertTrue(validator.is_valid(exact))

        stable_document = self._track_document(
            main_test={"universal": self.universal_cell},
            main_stable={
                "universal": self._stable_cell(
                    self.universal_cell, chipset="universal"
                )
            },
        )
        universal_fallback = construct_core_track_inventory(
            stable_document,
            catalog=self.catalog,
            pin_index=self.pin_index,
            tunings=self.tunings,
            main_release_roster=self.release_roster,
            spruce_branch_bases=self.branch_bases,
            group_tag="main-stable:h700",
            source_registry_index=self.source_registry_index,
        )
        self.assertTrue(validator.is_valid(universal_fallback))

        mutations = {
            "test-state-stable-stability": (exact, "stability", "stable"),
            "test-state-stable-marker": (exact, "requested_marker", "stable"),
            "test-state-stable-resolution": (exact, "resolution", "exact_stable"),
            "exact-resolution-chipset-mismatch": (
                exact,
                "selected_chipset",
                "universal",
            ),
            "universal-fallback-selected-exact": (
                universal_fallback,
                "selected_chipset",
                "h700",
            ),
            "universal-fallback-requested-universal": (
                universal_fallback,
                "requested_chipset",
                "universal",
            ),
            "stable-state-unstable-stability": (
                universal_fallback,
                "stability",
                "unstable",
            ),
        }
        for label, (source, field, value) in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(source)
                invalid["cores"][0][field] = value
                self.assertFalse(validator.is_valid(invalid))

        whitespace_approval = copy.deepcopy(universal_fallback)
        whitespace_approval["cores"][0]["approval"]["approved_by"] = " \t"
        self.assertFalse(validator.is_valid(whitespace_approval))

    def test_tuned_cells_require_matching_pin_tuning_evidence(self) -> None:
        mismatched = copy.deepcopy(self.h700_cell)
        mismatched["build_pin_id"] = "alpha-universal"
        document = self._track_document(main_test={"h700": mismatched})

        with self.assertRaisesRegex(
            PipelineError, "pin does not bind the selected tuning profile"
        ):
            validate_core_tracks(
                document,
                catalog=self.catalog,
                pin_index=self.pin_index,
                tunings=self.tunings,
                main_release_roster=self.release_roster,
                spruce_branch_bases=self.branch_bases,
                source_registry_index=self.source_registry_index,
            )

    def test_malformed_pin_and_tuning_fields_fail_deterministically(self) -> None:
        invalid_profile_id = self._pin_document()
        invalid_profile_id["cores"]["alpha"]["selection"]["targets"]["arm64"][
            "golden_record"
        ]["recipe"]["chipset_tuning"] = {
            "profile_id": 7,
            "content_sha256": "1" * 64,
        }
        _rehash_pin(invalid_profile_id)

        invalid_tuning_digest = self._pin_document()
        invalid_tuning_digest["cores"]["alpha"]["selection"]["targets"][
            "arm64"
        ]["golden_record"]["recipe"]["chipset_tuning"] = {
            "profile_id": "universal-v1",
            "content_sha256": "not-a-digest",
        }
        _rehash_pin(invalid_tuning_digest)

        mixed_tuning_presence = self._pin_document()
        universal = resolved_tuning_profile(
            self.tunings, UNIVERSAL_TUNING_PROFILE
        )
        mixed_tuning_presence["cores"]["alpha"]["selection"]["targets"][
            "arm64"
        ]["golden_record"]["recipe"]["chipset_tuning"] = {
            "profile_id": universal["profile_id"],
            "content_sha256": universal["content_sha256"],
        }
        _rehash_pin(mixed_tuning_presence)

        malformed_publication = self._pin_document()
        malformed_publication["publication"] = "enabled"
        _rehash_pin(malformed_publication)

        malformed_commit = self._pin_document()
        malformed_commit["cores"]["alpha"]["selection"]["targets"]["arm64"][
            "golden_record"
        ]["source"]["resolved_commit"] = "short"
        _rehash_pin(malformed_commit)

        extra_tuning_field = self._pin_document()
        extra_tuning_field["cores"]["alpha"]["selection"]["targets"]["arm64"][
            "golden_record"
        ]["recipe"]["chipset_tuning"] = {
            "profile_id": "universal-v1",
            "content_sha256": "1" * 64,
            "compiler_arguments": [],
        }
        _rehash_pin(extra_tuning_field)

        cases = {
            "profile-id": (
                invalid_profile_id,
                "core pin tuning identity is malformed: alpha-pin.json/arm64",
            ),
            "tuning-digest": (
                invalid_tuning_digest,
                "core pin tuning identity is malformed: alpha-pin.json/arm64",
            ),
            "mixed-presence": (
                mixed_tuning_presence,
                "core pin tuning presence differs by target: alpha-pin.json",
            ),
            "publication": (
                malformed_publication,
                "core pin document identity is malformed: alpha-pin.json",
            ),
            "source-commit": (
                malformed_commit,
                "core pin source identity is malformed: alpha-pin.json/arm64",
            ),
            "extra-tuning-field": (
                extra_tuning_field,
                "core pin tuning identity fields are not exact: alpha-pin.json/arm64",
            ),
            "non-object": (
                [],
                "core pin must be an object: alpha-pin.json",
            ),
        }
        for label, (document, expected) in cases.items():
            with self.subTest(label=label):
                messages = []
                for _ in range(2):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        self._write_pin_fixture(root, document)
                        with self.assertRaises(PipelineError) as raised:
                            load_core_pin_index(
                                root,
                                pin_validator=lambda _document, _path: {
                                    "status": "valid",
                                    "errors": [],
                                },
                            )
                        messages.append(str(raised.exception))
                self.assertEqual([expected, expected], messages)

    def test_pin_index_cannot_fall_back_to_shallow_pin_trust(self) -> None:
        fake = self._pin_document()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_pin_fixture(root, fake)
            with self.assertRaisesRegex(
                PipelineError, "authoritative core pin validator is required"
            ):
                load_core_pin_index(root)
            with self.assertRaisesRegex(
                PipelineError, "authoritative core pin validation failed"
            ):
                load_core_pin_index(
                    root,
                    pin_validator=pipeline.authoritative_core_track_pin_report,
                )

    def test_tuning_registry_rejects_untyped_or_unsafe_profiles(self) -> None:
        raw_flag = copy.deepcopy(self.live_tunings)
        raw_flag["profiles"][UNIVERSAL_TUNING_PROFILE]["properties"]["cflags"] = "-O3"
        _rehash_tunings(raw_flag)

        cyclic = copy.deepcopy(self.live_tunings)
        cyclic["profiles"]["a133p-cortex-a53-v1"]["extends"] = (
            "a133p-cortex-a53-v1"
        )
        _rehash_tunings(cyclic)

        cross_chipset = copy.deepcopy(self.live_tunings)
        cross_chipset["profiles"]["rk3566-cortex-a55-v1"]["extends"] = (
            "a133p-cortex-a53-v1"
        )
        _rehash_tunings(cross_chipset)

        incomplete_armhf = copy.deepcopy(self.live_tunings)
        del incomplete_armhf["profiles"]["ssd202d-cortex-a7-v1"]["properties"][
            "fpu"
        ]
        _rehash_tunings(incomplete_armhf)

        stale_mapping_version = copy.deepcopy(self.live_tunings)
        stale_mapping_version["compiler_argument_mapping_version"] = (
            "gcc-machine-flags-v2"
        )
        _rehash_tunings(stale_mapping_version)

        cases = {
            "raw-flag": (raw_flag, "unsupported properties"),
            "cyclic": (cyclic, "cyclic"),
            "cross-chipset": (cross_chipset, "crosses a chipset"),
            "incomplete-armhf": (incomplete_armhf, "complete cortex-a7"),
            "mapping-version": (stale_mapping_version, "mapping version"),
        }
        for label, (document, expected) in cases.items():
            with self.subTest(label=label):
                errors = chipset_tuning_errors(document)
                self.assertTrue(any(expected in error for error in errors), errors)
                with self.assertRaises(PipelineError):
                    validate_chipset_tunings(document)


if __name__ == "__main__":
    unittest.main()
