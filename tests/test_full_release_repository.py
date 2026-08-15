from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests import expected_counts
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release import (
    construct_release_plan,
    release_plan_content_sha256,
)
from scripts.core_pipeline_lib.release import repository as release_repository
from scripts.core_pipeline_lib.records.source import (
    compose_source_set,
    record_file_sha256,
)
from scripts.core_pipeline_lib.tracks import core_tracks_content_sha256
from tests.test_full_release_support import repository_facts, sha1, sha256
from tests.test_full_release_track_group import track_plan


class FullReleaseRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = pipeline.release_repository_services()
        self.real_run = release_repository.run

    def clean_run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if args == ["git", "status", "--short"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if (
            len(args) == 4
            and args[:3] == ["git", "ls-files", "--error-unmatch"]
            and args[3] != "--"
        ):
            return subprocess.CompletedProcess(args, 0, args[3] + "\n", "")
        if args[:4] == ["git", "ls-files", "--error-unmatch", "--"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "\n".join(args[4:]) + "\n",
                "",
            )
        return self.real_run(args, cwd=cwd, check=check)

    def construct(self, *, core_ids: list[str]) -> dict:
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ):
            return release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-2048-gambatte-v2",
                scope="explicit",
                requested_cores=core_ids,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_actual_two_core_plan_is_tracked_only_and_profile_bound(self) -> None:
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text

        def guarded_read_bytes(path: Path) -> bytes:
            if ".local-e2e" in path.parts:
                raise AssertionError(f"planner read ignored evidence: {path}")
            return original_read_bytes(path)

        def guarded_read_text(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> str:
            if ".local-e2e" in path.parts:
                raise AssertionError(f"planner read ignored evidence: {path}")
            return original_read_text(path, *args, **kwargs)

        with mock.patch.object(Path, "read_bytes", guarded_read_bytes), mock.patch.object(
            Path,
            "read_text",
            guarded_read_text,
        ):
            plan = self.construct(core_ids=["gambatte", "2048"])

        self.assertEqual(
            [row["core_id"] for row in plan["cores"]],
            ["2048", "gambatte"],
        )
        self.assertEqual(plan["summary"]["core_count"], 2)
        self.assertEqual(plan["summary"]["target_count"], 4)
        for row in plan["cores"]:
            self.assertEqual(
                [target["execution_profile"] for target in row["targets"]],
                ["ra64-universal-v1", "ra32-a30-v1"],
            )
        for role, relative in (
            ("coordinator", ".github/workflows/release-candidate.yml"),
            ("worker", ".github/workflows/_build-one-core.yml"),
        ):
            self.assertEqual(
                {
                    "path": relative,
                    "file_sha256": pipeline.sha256_file(pipeline.ROOT / relative),
                },
                plan["repository"]["orchestration"][role],
            )

    def test_tracked_json_references_use_their_parsed_byte_snapshots(self) -> None:
        real_sha256_file = release_repository.sha256_file

        def reject_json_rehash(path: Path) -> str:
            if path.suffix == ".json":
                raise AssertionError(f"tracked JSON was rehashed after parsing: {path}")
            return real_sha256_file(path)

        with mock.patch.object(
            release_repository,
            "sha256_file",
            side_effect=reject_json_rehash,
        ):
            plan = self.construct(core_ids=["2048"])

        row = plan["cores"][0]
        for reference in (
            plan["repository"]["catalog"],
            row["compatibility"],
            row["pin"],
        ):
            path = pipeline.ROOT / reference["path"]
            self.assertEqual(
                reference["file_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

        tracks, _ = release_repository.load_json_with_sha256(
            pipeline.ROOT / "manifests" / "core-tracks.json"
        )
        tunings, _ = release_repository.load_json_with_sha256(
            pipeline.ROOT / "manifests" / "chipset-tunings.json"
        )
        selection = {
            "group_tag": "main-stable:universal",
            "selected_state": "unstable_fallback",
            "track_registry_content_sha256": tracks["content_sha256"],
            "tuning_registry_content_sha256": tunings["content_sha256"],
            "spruce_branch_basis": copy.deepcopy(
                tracks["tracks"]["main"]["spruce_branch_basis"]
            ),
        }
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "sha256_file",
            side_effect=reject_json_rehash,
        ):
            group = release_repository._tracked_group_facts(
                group_tag="main-stable:universal",
                selections={"2048": selection},
                repository_root=pipeline.ROOT,
            )
        for field in (
            "track_registry",
            "tuning_registry",
            "release_roster",
            "spruce_branch_bases",
        ):
            reference = group[field]
            path = pipeline.ROOT / reference["path"]
            self.assertEqual(
                reference["file_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_release_group_digest_binds_temporal_parent_records(self) -> None:
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ):
            documents, references = release_repository._tracked_group_inputs(
                pipeline.ROOT
            )
        original_tracks = documents["track_registry"]
        selection = {
            "group_tag": "main-stable:universal",
            "selected_state": "unstable_fallback",
            "track_registry_content_sha256": original_tracks["content_sha256"],
            "tuning_registry_content_sha256": documents["tuning_registry"][
                "content_sha256"
            ],
            "spruce_branch_basis": copy.deepcopy(
                original_tracks["tracks"]["main"]["spruce_branch_basis"]
            ),
        }

        changed_documents = copy.deepcopy(documents)
        changed_references = copy.deepcopy(references)
        changed_tracks = changed_documents["track_registry"]
        changed_tracks["source_order_parent_bindings"] = [
            {"content_sha256": sha256("new-temporal-parent-binding")}
        ]
        changed_tracks["content_sha256"] = core_tracks_content_sha256(
            changed_tracks
        )
        changed_references["track_registry"]["content_sha256"] = changed_tracks[
            "content_sha256"
        ]

        self.assertNotEqual(
            selection["track_registry_content_sha256"],
            changed_tracks["content_sha256"],
        )
        with self.assertRaisesRegex(
            PipelineError,
            "release track registry identity changed",
        ):
            release_repository._tracked_group_facts(
                group_tag="main-stable:universal",
                selections={"2048": selection},
                repository_root=pipeline.ROOT,
                documents=changed_documents,
                references=changed_references,
            )

    def test_full_workflow_roster_constructs_a_release_ready_plan(self) -> None:
        # The 2026-07-24 milestone: with every shipped-core workflow
        # canonical (98/98, zero uncataloged, zero pending), the FULL roster
        # constructs a valid release plan for the first time -- the
        # "not release-ready" blocker report this test used to pin is no
        # longer reachable from real repository state.
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ):
            plan = release_repository.construct_tracked_release_plan(
                candidate_id="full-roster-v1",
                scope="full-workflow-roster",
                requested_cores=None,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        self.assertEqual(
            plan["summary"]["core_count"], expected_counts.CATALOG_CORE_COUNT
        )
        self.assertEqual(
            plan["summary"]["target_count"],
            sum(len(spec["targets"]) for spec in catalog["cores"].values()),
        )
        self.assertEqual(
            [row["core_id"] for row in plan["cores"]],
            sorted(catalog["cores"]),
        )

    def test_main_stable_universal_track_group_fails_closed_when_deferred(
        self,
    ) -> None:
        pin_index_loader = mock.Mock(
            wraps=self.services.load_core_pin_index
        )
        group_resolver = mock.Mock(
            side_effect=pipeline.PipelineError(
                "core group selection is deferred for synthetic-core: "
                "main-stable:universal: "
                "no-reviewed-version-channel-build-pin"
            )
        )
        services = replace(
            self.services,
            load_core_pin_index=pin_index_loader,
            resolve_core_group_build_selection=group_resolver,
        )
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), self.assertRaisesRegex(
            pipeline.PipelineError,
            "core group selection is deferred.*no-reviewed-version-channel-build-pin",
        ):
            release_repository.construct_tracked_release_plan(
                candidate_id="main-stable-universal-v1",
                scope="track-group",
                requested_cores=None,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=services,
                group_tag="main-stable:universal",
            )
        pin_index_loader.assert_called_once_with()
        group_resolver.assert_called_once()

    def test_differing_track_source_projects_trusted_profiles_into_plan(
        self,
    ) -> None:
        """The repository forwards a changed source only to its trusted service."""

        core_id = "alpha"
        canonical_source = {
            "url": "https://example.invalid/libretro-alpha.git",
            "requested_ref": "refs/heads/main",
            "commit": sha1("alpha-current-commit"),
            "tree": sha1("alpha-current-tree"),
        }
        execution_source = {
            "url": canonical_source["url"],
            "requested_ref": "refs/heads/nightly",
            "commit": sha1("alpha-nightly-commit"),
            "tree": sha1("alpha-nightly-tree"),
            "submodules": [],
        }
        canonical_artifact = {
            "sha256": sha256("alpha-current-artifact"),
            "size": 101,
        }
        selected_artifact = {
            "sha256": sha256("alpha-nightly-artifact"),
            "size": 103,
        }

        def captured_source(source: dict) -> dict:
            return {
                **copy.deepcopy(source),
                "resolved_url": source["url"],
                "resolved_commit": source["commit"],
                "submodules": copy.deepcopy(source.get("submodules", [])),
            }

        def pin_document(
            source: dict,
            artifact: dict,
            package_label: str,
        ) -> dict:
            package = {
                "name": "alpha_libretro.zip",
                "sha256": sha256(package_label),
                "size": 211,
            }
            selection = {
                "tier": "build_golden",
                "validation_scope": "static-build-only",
                "package": package,
                "metadata": {
                    "sha256": sha256(f"metadata:{package_label}"),
                    "size": 59,
                },
                "e2e": {
                    "run_id": f"run-{package_label}",
                    "content_sha256": sha256(f"e2e:{package_label}"),
                    "package_sha256": package["sha256"],
                    "build_records": {
                        "arm64": sha256(f"record:{package_label}")
                    },
                },
                "targets": {
                    "arm64": {
                        "artifact": copy.deepcopy(artifact),
                        "build_record_sha256": sha256(
                            f"record:{package_label}"
                        ),
                        "provenance_identity_sha256": sha256(
                            f"provenance:{package_label}"
                        ),
                        "golden_record": {
                            "source": captured_source(source)
                        },
                    }
                },
            }
            selection["selection_sha256"] = pipeline.selection_content_sha256(
                selection
            )
            pin_id = (
                f"{core_id}-{source['commit'][:12]}-"
                f"{selection['selection_sha256'][:12]}"
            )
            document = {
                "$schema": "../../manifests/core-set.schema.json",
                "schema_version": 1,
                "pin_id": pin_id,
                "local_only": True,
                "publication": "disabled",
                "scope": [core_id],
                "parent": None,
                "sources": [
                    {
                        "path": (
                            f".local-e2e/nightlies/{pin_id}/golden.json"
                        ),
                        "pin_id": pin_id,
                        "file_sha256": sha256(f"golden-file:{package_label}"),
                        "content_sha256": sha256(
                            f"golden-content:{package_label}"
                        ),
                    }
                ],
                "selection_policy": copy.deepcopy(
                    pipeline.PIN_SELECTION_POLICY
                ),
                "cores": {
                    core_id: {
                        "decision": "select_source",
                        "source_index": 0,
                        "selection": selection,
                    }
                },
                "summary": {
                    "core_count": 1,
                    "retained_parent_count": 0,
                    "selected_source_count": 1,
                },
                "created_at": "2026-08-10T00:00:00+00:00",
            }
            document["content_sha256"] = pipeline.pin_set_content_sha256(
                document
            )
            return document

        canonical_pin = pin_document(
            canonical_source,
            canonical_artifact,
            "alpha-current-package",
        )
        selected_pin = pin_document(
            execution_source,
            selected_artifact,
            "alpha-nightly-package",
        )
        canonical_pin_id = canonical_pin["pin_id"]
        selected_pin_id = selected_pin["pin_id"]
        catalog = {
            "cores": {
                core_id: {
                    "workflow": ".github/workflows/build-alpha.yml",
                    "source": canonical_source,
                    "build": {"artifact_name": "alpha_libretro.so"},
                    "metadata": {"artifact_name": "alpha_libretro.info"},
                    "targets": ["arm64"],
                }
            }
        }

        def spec_sha256(spec: dict) -> str:
            return hashlib.sha256(
                json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()

        execution_spec = copy.deepcopy(catalog["cores"][core_id])
        execution_spec["source"] = {
            key: execution_source[key]
            for key in catalog["cores"][core_id]["source"]
        }
        group_selection = {
            "schema_version": 1,
            "validation_scope": "pinned-output-reproduction-v1",
            "group_tag": "nightly-test:universal",
            "inventory_content_sha256": sha256("nightly-inventory"),
            "track_registry_content_sha256": sha256("track-registry"),
            "tuning_registry_content_sha256": sha256("tuning-registry"),
            "spruce_branch_basis": {
                "basis_id": "spruce-development",
                "basis_content_sha256": sha256("spruce-development-basis"),
            },
            "core_id": core_id,
            "variant_id": sha256("alpha-nightly-variant"),
            "requested_marker": "test",
            "requested_chipset": "universal",
            "selected_chipset": "universal",
            "selected_state": "test",
            "stability": "unstable",
            "resolution": "exact_test",
            "test_origin_track": "nightly",
            "pin": {},
            "source_commit": execution_source["commit"],
            "execution_source": execution_source,
            "recipe_compatibility": {
                "model": "source-normalized-build-contract-v1",
                "selected_pin_core_spec_sha256": sha256(
                    "alpha-selected-recipe"
                ),
                "execution_core_spec_sha256": spec_sha256(execution_spec),
                "core_spec_identity_match": False,
            },
            "selected_architectures": ["arm64"],
            "tuning": {
                "profile_id": "universal-v1",
                "content_sha256": sha256("universal-tuning"),
                "properties": {},
                "compiler_argument_mapping_version": "gcc-machine-flags-v1",
                "compiler_arguments": [],
            },
            "expected_outputs": {
                "targets": {"arm64": {"artifact": selected_artifact}},
                "metadata": {"sha256": sha256("nightly-metadata"), "size": 59},
                "package": {
                    "comparison": "exact",
                    **selected_pin["cores"][core_id]["selection"]["package"],
                },
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifests" / "compatibility").mkdir(parents=True)
            (root / "pins" / "core-sets").mkdir(parents=True)
            (root / ".github" / "workflows").mkdir(parents=True)
            catalog_path = root / "manifests" / "core-builds.json"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            canonical_pin_path = (
                root / "pins" / "core-sets" / f"{canonical_pin_id}.json"
            )
            selected_pin_path = (
                root / "pins" / "core-sets" / f"{selected_pin_id}.json"
            )
            canonical_pin_path.write_text(
                json.dumps(canonical_pin), encoding="utf-8"
            )
            selected_pin_path.write_text(
                json.dumps(selected_pin), encoding="utf-8"
            )
            group_selection["pin"] = {
                "path": f"pins/core-sets/{selected_pin_id}.json",
                "pin_id": selected_pin_id,
                "file_sha256": release_repository.sha256_file(selected_pin_path),
                "content_sha256": selected_pin["content_sha256"],
            }
            compatibility = {
                "golden_source": f"pins/core-sets/{canonical_pin_id}.json",
                "source_commit": canonical_source["commit"],
                "package_sha256": canonical_pin["cores"][core_id]["selection"][
                    "package"
                ]["sha256"],
                "e2e_run": ".local-e2e/runs/"
                + canonical_pin["cores"][core_id]["selection"]["e2e"][
                    "run_id"
                ]
                + "/e2e-record.json",
                "selected_e2e_content_sha256": canonical_pin["cores"][core_id][
                    "selection"
                ]["e2e"]["content_sha256"],
                "targets": {
                    "arm64": {
                        "artifact_sha256": canonical_artifact["sha256"]
                    }
                },
                "content_sha256": sha256("alpha-compatibility"),
            }
            (root / "manifests" / "compatibility" / "alpha.json").write_text(
                json.dumps(compatibility), encoding="utf-8"
            )
            (root / ".github" / "workflows" / "build-alpha.yml").write_text(
                "name: alpha\n", encoding="utf-8"
            )

            profile_calls: list[str] = []

            def profile_report(relative: str) -> dict:
                profile_calls.append(relative)
                if relative != f"pins/source-sets/{canonical_pin_id}.json":
                    raise AssertionError("alternate pin reached legacy profile mirror")
                return {
                    "build_evidence_cells": [
                        {
                            "core_id": core_id,
                            "architecture": "arm64",
                            "execution_profile_id": "ra64-universal-v1",
                            "artifact_sha256": canonical_artifact["sha256"],
                        }
                    ],
                    "device_views": [],
                }

            # Source-candidate authentication belongs to the launcher-owned
            # service.  This repository unit test isolates the handoff and
            # proves that the exact already-validated selection reaches it.
            group_projector = mock.Mock(
                return_value=copy.deepcopy(execution_spec)
            )
            services = replace(
                self.services,
                require_pin_sources_eligible=lambda _catalog, _pin: None,
                validate_pin_set=lambda *_args, **_kwargs: {
                    "status": "valid",
                    "errors": [],
                },
                require_individual_pin_identity=lambda document, **_kwargs: (
                    core_id,
                    document["pin_id"],
                ),
                validate_compatibility=lambda *_args, **_kwargs: {
                    "status": "valid",
                    "errors": [],
                },
                profile_report=profile_report,
                core_spec_sha256=spec_sha256,
                group_execution_spec=group_projector,
            )
            workflow_audit = {
                "workflows": {
                    core_id: {
                        "uses_shared_pipeline": True,
                        "workflow": ".github/workflows/build-alpha.yml",
                        "file_sha256": release_repository.sha256_file(
                            root / ".github" / "workflows" / "build-alpha.yml"
                        ),
                    }
                }
            }
            with mock.patch.object(
                release_repository,
                "run",
                side_effect=self.clean_run,
            ):
                row = release_repository._release_core_row(
                    core_id=core_id,
                    repository_root=root,
                    catalog=catalog,
                    workflow_audit=workflow_audit,
                    services=services,
                    group_selection=group_selection,
                )

            expected_catalog = copy.deepcopy(catalog)
            expected_catalog["cores"][core_id]["source"] = execution_source
            expected_source_set = compose_source_set(
                selected_pin_id,
                repository_root=root,
                catalog=expected_catalog,
            )
            self.assertEqual(
                profile_calls,
                [f"pins/source-sets/{canonical_pin_id}.json"],
            )
            self.assertIs(
                pipeline.release_repository_services().group_execution_spec,
                pipeline._group_execution_spec,
            )
            group_projector.assert_called_once()
            self.assertEqual(
                group_projector.call_args.kwargs["validated_pin_selection"],
                selected_pin["cores"][core_id]["selection"],
            )
            self.assertEqual(row["source"], execution_source)
            self.assertEqual(row["core_spec_sha256"], spec_sha256(execution_spec))
            self.assertEqual(
                row["source_set"]["content_sha256"],
                expected_source_set["content_sha256"],
            )
            self.assertEqual(
                row["source_set"]["file_sha256"],
                record_file_sha256(expected_source_set),
            )
            self.assertEqual(
                row["targets"][0]["execution_profile"],
                "ra64-universal-v1",
            )

            facts = repository_facts()
            plan = construct_release_plan(
                candidate_id="alpha-nightly-plan-v1",
                scope="track-group",
                repository=facts,
                cores=[row],
                group={
                    "group_tag": "nightly-test:universal",
                    "inventory_state": "unstable",
                    "track_registry": {
                        "path": "manifests/core-tracks.json",
                        "file_sha256": sha256("track-file"),
                        "content_sha256": sha256("track-registry"),
                    },
                    "tuning_registry": {
                        "path": "manifests/chipset-tunings.json",
                        "file_sha256": sha256("tuning-file"),
                        "content_sha256": sha256("tuning-registry"),
                    },
                    "release_roster": {
                        "path": "manifests/spruce-release-roster.json",
                        "file_sha256": sha256("roster-file"),
                        "content_sha256": sha256("roster-content"),
                    },
                    "spruce_branch_bases": {
                        "path": "manifests/spruce-core-branch-bases.json",
                        "file_sha256": sha256("branch-bases-file"),
                        "content_sha256": sha256("branch-bases-content"),
                    },
                    "stable_core_count": 0,
                    "unstable_fallback_core_count": 0,
                    "test_core_count": 1,
                },
            )
            self.assertEqual(plan["cores"][0], row)

            tampered_source = copy.deepcopy(group_selection)
            tampered_source["execution_source"]["tree"] = sha1(
                "forged-nightly-tree"
            )
            with mock.patch.object(
                release_repository,
                "run",
                side_effect=self.clean_run,
            ), self.assertRaisesRegex(PipelineError, "pin source changed"):
                release_repository._release_core_row(
                    core_id=core_id,
                    repository_root=root,
                    catalog=catalog,
                    workflow_audit=workflow_audit,
                    services=services,
                    group_selection=tampered_source,
                )

            tampered_recipe = copy.deepcopy(group_selection)
            tampered_recipe["recipe_compatibility"][
                "execution_core_spec_sha256"
            ] = "0" * 64
            with mock.patch.object(
                release_repository,
                "run",
                side_effect=self.clean_run,
            ), self.assertRaisesRegex(PipelineError, "recipe identity changed"):
                release_repository._release_core_row(
                    core_id=core_id,
                    repository_root=root,
                    catalog=catalog,
                    workflow_audit=workflow_audit,
                    services=services,
                    group_selection=tampered_recipe,
                )

    def test_deferred_chipset_group_fails_before_release_rows(self) -> None:
        selection_resolver = mock.Mock(
            side_effect=[
                {"selected_state": "synthetic-admitted"},
                pipeline.PipelineError(
                    "core group selection is deferred for synthetic-core: "
                    "main-stable:a523: "
                    "no-reviewed-version-channel-build-pin"
                ),
            ]
        )
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "_resolve_release_group_selection",
            selection_resolver,
        ), mock.patch.object(
            release_repository,
            "_release_core_row",
        ) as compose_row, self.assertRaisesRegex(
            pipeline.PipelineError,
            "core group selection is deferred.*no-reviewed-version-channel-build-pin",
        ):
            release_repository.construct_tracked_release_plan(
                candidate_id="main-stable-a523-v1",
                scope="track-group",
                requested_cores=None,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
                group_tag="main-stable:a523",
            )
        self.assertEqual(selection_resolver.call_count, 2)
        compose_row.assert_not_called()

    def test_historical_recipe_failure_fails_before_release_rows(self) -> None:
        resolver = mock.Mock(
            side_effect=PipelineError(
                "historical recipe snapshot is unavailable for selected pin"
            )
        )
        services = replace(
            self.services,
            resolve_core_group_build_selection=resolver,
        )
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "_release_core_row",
        ) as compose_row, self.assertRaisesRegex(
            PipelineError,
            "historical recipe snapshot is unavailable",
        ):
            release_repository.construct_tracked_release_plan(
                candidate_id="historical-pin-v1",
                scope="track-group",
                requested_cores=None,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=services,
                group_tag="main-stable:universal",
            )
        resolver.assert_called_once()
        resolver_arguments = resolver.call_args.kwargs
        self.assertEqual(
            pipeline.load_json(pipeline.DEFAULT_CORE_TRACKS),
            resolver_arguments["track_registry"],
        )
        self.assertEqual(
            pipeline.load_json(pipeline.DEFAULT_CHIPSET_TUNINGS),
            resolver_arguments["tuning_registry"],
        )
        self.assertEqual(
            pipeline.load_json(pipeline.DEFAULT_SPRUCE_RELEASE_ROSTER),
            resolver_arguments["release_roster"],
        )
        self.assertEqual(
            pipeline.load_json(pipeline.DEFAULT_SPRUCE_BRANCH_BASES),
            resolver_arguments["spruce_branch_bases"],
        )
        compose_row.assert_not_called()

    def test_planner_rejects_compatibility_e2e_drift_from_pin(self) -> None:
        real_load_json_with_sha256 = release_repository.load_json_with_sha256

        def drifted_load(path: Path) -> tuple[dict, str]:
            document, file_sha256 = real_load_json_with_sha256(path)
            if path == pipeline.ROOT / "manifests" / "compatibility" / "2048.json":
                document = copy.deepcopy(document)
                document["selected_e2e_content_sha256"] = "0" * 64
                document["content_sha256"] = (
                    pipeline.core_compatibility_content_sha256(document)
                )
            return document, file_sha256

        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "load_json_with_sha256",
            side_effect=drifted_load,
        ), self.assertRaisesRegex(PipelineError, "E2E identity differs from pin"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v1",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_planner_requires_a_clean_repository(self) -> None:
        def dirty_run(
            args: list[str],
            *,
            cwd: Path | None = None,
            check: bool = True,
        ) -> subprocess.CompletedProcess[str]:
            if args == ["git", "status", "--short"]:
                return subprocess.CompletedProcess(args, 0, " M tracked-file\n", "")
            return self.real_run(args, cwd=cwd, check=check)

        with mock.patch.object(
            release_repository,
            "run",
            side_effect=dirty_run,
        ), self.assertRaisesRegex(PipelineError, "requires a clean repository"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v1",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_planner_rejects_untracked_workflow_or_pipeline_roster(self) -> None:
        for case in ("workflow", "pipeline"):
            with self.subTest(case=case):
                def untracked_run(
                    args: list[str],
                    *,
                    cwd: Path | None = None,
                    check: bool = True,
                ) -> subprocess.CompletedProcess[str]:
                    result = self.clean_run(args, cwd=cwd, check=check)
                    if args[:4] != ["git", "ls-files", "--error-unmatch", "--"]:
                        return result
                    paths = args[4:]
                    is_workflow_roster = all(
                        path.startswith(".github/workflows/") for path in paths
                    )
                    if (case == "workflow") == is_workflow_roster:
                        return subprocess.CompletedProcess(
                            args,
                            1,
                            "",
                            "simulated untracked path",
                        )
                    return result

                expected = (
                    "release workflow roster"
                    if case == "workflow"
                    else "release pipeline source bundle"
                )
                with mock.patch.object(
                    release_repository,
                    "run",
                    side_effect=untracked_run,
                ), self.assertRaisesRegex(PipelineError, expected):
                    release_repository.construct_tracked_release_plan(
                        candidate_id="release-canary-v1",
                        scope="explicit",
                        requested_cores=["2048"],
                        repository_root=pipeline.ROOT,
                        catalog_path=pipeline.DEFAULT_CATALOG,
                        services=self.services,
                    )

    def test_planner_rejects_invalid_or_inconsistent_release_orchestration(
        self,
    ) -> None:
        invalid = {
            "status": "invalid",
            "errors": ["coordinator: simulated unsafe workflow"],
        }
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "audit_release_workflows",
            return_value=invalid,
        ), self.assertRaisesRegex(PipelineError, "release orchestration is invalid"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v2",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

        inconsistent = copy.deepcopy(
            release_repository.audit_release_workflows(pipeline.ROOT)
        )
        inconsistent["coordinator"]["file_sha256"] = "0" * 64
        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), mock.patch.object(
            release_repository,
            "audit_release_workflows",
            return_value=inconsistent,
        ), self.assertRaisesRegex(PipelineError, "audit identity is inconsistent"):
            release_repository.construct_tracked_release_plan(
                candidate_id="release-canary-v2",
                scope="explicit",
                requested_cores=["2048"],
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_planner_rejects_untracked_release_orchestration_files(self) -> None:
        for relative in (
            ".github/workflows/release-candidate.yml",
            ".github/workflows/_build-one-core.yml",
            ".github/workflows/release-overlay.yml",
        ):
            with self.subTest(relative=relative):
                def untracked_run(
                    args: list[str],
                    *,
                    cwd: Path | None = None,
                    check: bool = True,
                ) -> subprocess.CompletedProcess[str]:
                    if args == ["git", "ls-files", "--error-unmatch", relative]:
                        return subprocess.CompletedProcess(
                            args,
                            1,
                            "",
                            "simulated untracked orchestration",
                        )
                    return self.clean_run(args, cwd=cwd, check=check)

                with mock.patch.object(
                    release_repository,
                    "run",
                    side_effect=untracked_run,
                ), self.assertRaisesRegex(PipelineError, "not tracked by Git"):
                    release_repository.construct_tracked_release_plan(
                        candidate_id="release-canary-v2",
                        scope="explicit",
                        requested_cores=["2048"],
                        repository_root=pipeline.ROOT,
                        catalog_path=pipeline.DEFAULT_CATALOG,
                        services=self.services,
                    )

    def test_repository_revalidation_rejects_forged_orchestration_identity(
        self,
    ) -> None:
        forged = self.construct(core_ids=["2048"])
        forged["repository"]["orchestration"]["worker"]["file_sha256"] = "0" * 64
        forged["content_sha256"] = release_plan_content_sha256(forged)

        with mock.patch.object(
            release_repository,
            "run",
            side_effect=self.clean_run,
        ), self.assertRaisesRegex(
            PipelineError,
            "differs from the current tracked repository",
        ):
            release_repository.validate_plan_against_repository(
                forged,
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=self.services,
            )

    def test_worker_revalidation_does_not_require_an_unrelated_core_graph(
        self,
    ) -> None:
        plan = track_plan()
        alpha_row = next(
            row for row in plan["cores"] if row["core_id"] == "alpha"
        )
        pin_index: dict[str, dict[str, object]] = {}
        pin_index_loader = mock.Mock(return_value=pin_index)
        resolver = mock.Mock(return_value=copy.deepcopy(alpha_row["core_group"]))
        services = replace(
            self.services,
            load_catalog=lambda _path: {"cores": {"alpha": {}, "beta": {}}},
            audit_workflows=lambda _catalog: {"workflows": {}},
            require_catalog_cores_eligible=lambda _catalog, _cores: None,
            load_core_pin_index=pin_index_loader,
            resolve_core_group_build_selection=resolver,
        )

        def reconstruct(**kwargs: object) -> dict:
            if kwargs.get("scope") == "explicit":
                return {"repository": copy.deepcopy(plan["repository"])}
            raise PipelineError("missing source graph for unrelated beta")

        with mock.patch.object(
            release_repository,
            "construct_tracked_release_plan",
            side_effect=reconstruct,
        ), mock.patch.object(
            release_repository,
            "_release_core_row",
            return_value=copy.deepcopy(alpha_row),
        ), mock.patch.object(
            release_repository,
            "_tracked_group_facts",
            return_value=copy.deepcopy(plan["group"]),
        ):
            validated = release_repository.validate_plan_core_against_repository(
                plan,
                core_id="alpha",
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=services,
            )
            self.assertEqual(validated, plan)
            pin_index_loader.assert_called_once_with()
            self.assertIs(resolver.call_args.kwargs["pin_index"], pin_index)
            with self.assertRaisesRegex(PipelineError, "unrelated beta"):
                release_repository.validate_plan_against_repository(
                    plan,
                    repository_root=pipeline.ROOT,
                    catalog_path=pipeline.DEFAULT_CATALOG,
                    services=services,
                )

        self.assertEqual(resolver.call_count, 1)
        self.assertEqual(resolver.call_args.kwargs["core_id"], "alpha")

        forged_row = copy.deepcopy(alpha_row)
        forged_row["source"]["tree"] = "f" * 40
        with mock.patch.object(
            release_repository,
            "construct_tracked_release_plan",
            side_effect=reconstruct,
        ), mock.patch.object(
            release_repository,
            "_release_core_row",
            return_value=forged_row,
        ), mock.patch.object(
            release_repository,
            "_tracked_group_facts",
            return_value=copy.deepcopy(plan["group"]),
        ), self.assertRaisesRegex(PipelineError, "core alpha differs"):
            release_repository.validate_plan_core_against_repository(
                plan,
                core_id="alpha",
                repository_root=pipeline.ROOT,
                catalog_path=pipeline.DEFAULT_CATALOG,
                services=services,
            )


if __name__ == "__main__":
    unittest.main()
