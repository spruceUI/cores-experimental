from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib import tracks as track_model
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.release.source_graph import (
    prepare_release_source_graph,
    source_commit_fetch_argv,
    source_ref_fetch_argv,
    validated_source_graph_requirements,
)
from scripts.core_pipeline_lib.tracks import local_git_source_ancestry_verifier


PINNED_REPOSITORY = "https://github.com/example/release-core.git"


def git(*arguments: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def source_history(root: Path) -> tuple[Path, list[dict[str, str]]]:
    work = root / "work"
    work.mkdir()
    git("init", "-b", "main", cwd=work)
    (work / "source.txt").write_text("one\n", encoding="utf-8")
    git("add", "source.txt", cwd=work)
    git(
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release@example.invalid",
        "commit",
        "-m",
        "one",
        cwd=work,
    )
    ancestor = git("rev-parse", "HEAD", cwd=work)
    ancestor_tree = git("rev-parse", "HEAD^{tree}", cwd=work)
    (work / "source.txt").write_text("two\n", encoding="utf-8")
    git("add", "source.txt", cwd=work)
    git(
        "-c",
        "user.name=Release Test",
        "-c",
        "user.email=release@example.invalid",
        "commit",
        "-m",
        "two",
        cwd=work,
    )
    descendant = git("rev-parse", "HEAD", cwd=work)
    descendant_tree = git("rev-parse", "HEAD^{tree}", cwd=work)
    remote = root / "remote.git"
    git("clone", "--bare", str(work), str(remote), cwd=root)
    sources = sorted(
        [
            {
                "requested_ref": "refs/heads/main",
                "commit": ancestor,
                "tree": ancestor_tree,
            },
            {
                "requested_ref": "refs/heads/main",
                "commit": descendant,
                "tree": descendant_tree,
            },
        ],
        key=lambda item: (item["requested_ref"], item["commit"], item["tree"]),
    )
    return remote, sources


class RewritingGitRunner:
    def __init__(self, remote: Path) -> None:
        self.remote = remote
        self.commands: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        exact = list(argv)
        self.commands.append(exact)
        rewritten = (
            [str(self.remote) if item == PINNED_REPOSITORY else item for item in exact]
            if "fetch" in exact
            else exact
        )
        return subprocess.run(rewritten, **kwargs)


class ReleaseSourceGraphTests(unittest.TestCase):
    def test_plan_row_scope_preserves_the_cores_complete_requirement(self) -> None:
        alpha = {
            "core_id": "alpha",
            "repository": "https://example.invalid/alpha.git",
            "sources": [
                {
                    "requested_ref": "refs/heads/main",
                    "commit": "1" * 40,
                    "tree": "2" * 40,
                },
                {
                    "requested_ref": "refs/heads/nightly",
                    "commit": "3" * 40,
                    "tree": "4" * 40,
                },
            ],
            "ancestry": [{"ancestor": "1" * 40, "descendant": "3" * 40}],
        }
        beta = {
            **alpha,
            "core_id": "beta",
            "repository": "https://example.invalid/beta.git",
        }
        prepared = mock.Mock()
        complete_inventory = {
            "complete": True,
            "unsupported_core_ids": [],
            "track_registry_content_sha256": "5" * 64,
            "content_sha256": "6" * 64,
        }
        prepared_state = {"done": False}

        def prepare(**_kwargs):
            prepared_state["done"] = True
            return {
                "status": "verified",
                "repository_count": 1,
                "source_count": 2,
                "ancestry_count": 1,
                "network_fetch_required": True,
            }

        prepared.side_effect = prepare
        verifier = mock.Mock()

        def inventory_pass(*_args, **kwargs):
            if kwargs["source_ancestry_verifier"] is verifier:
                self.assertTrue(
                    prepared_state["done"],
                    "real ancestry verification ran before source preparation",
                )
            return copy.deepcopy(complete_inventory)

        inventory = mock.Mock(side_effect=inventory_pass)
        with mock.patch.object(
            pipeline,
            "load_catalog",
            return_value={"cores": {"alpha": {}, "beta": {}}},
        ), mock.patch.object(
            pipeline,
            "load_authoritative_core_pin_index",
            return_value={},
        ), mock.patch.object(
            pipeline,
            "release_source_graph_requirements",
            return_value=[alpha, beta],
        ), mock.patch.object(
            pipeline,
            "core_track_source_ancestry_verifier",
            return_value=verifier,
        ), mock.patch.object(
            pipeline,
            "prepare_release_source_graph",
            prepared,
        ), mock.patch.object(
            pipeline,
            "construct_core_track_inventory",
            inventory,
        ), mock.patch.object(
            pipeline,
            "load_json",
            return_value={},
        ), mock.patch.object(
            pipeline,
            "load_core_track_source_registry_index",
            return_value={},
        ):
            report = pipeline.prepare_release_group_source_graph(
                "nightly-test:universal",
                core_id="alpha",
            )
            with self.assertRaisesRegex(pipeline.PipelineError, "not cataloged"):
                pipeline.prepare_release_group_source_graph(
                    "nightly-test:universal",
                    core_id="gamma",
                )

        self.assertEqual(report["core_scope"], "alpha")
        self.assertEqual(prepared.call_args.kwargs["requirements"], [alpha])
        self.assertEqual(2, inventory.call_count)
        self.assertIsNot(
            inventory.call_args_list[0].kwargs["source_ancestry_verifier"],
            verifier,
        )
        self.assertIs(
            inventory.call_args_list[1].kwargs["source_ancestry_verifier"],
            verifier,
        )
        self.assertEqual(inventory.call_args.kwargs["requested_cores"], ["alpha"])
        self.assertEqual(
            inventory.call_args.kwargs["source_ancestry_core_id"], "alpha"
        )
        self.assertIn("spruce_branch_bases", inventory.call_args.kwargs)

    def test_deferred_group_stops_before_source_graph_preparation(self) -> None:
        requirements = mock.Mock()
        prepared = mock.Mock()
        inventory = mock.Mock(
            return_value={
                "complete": False,
                "unsupported_core_ids": [],
                "deferred_cores": [
                    {
                        "core_id": "alpha",
                        "reason": "no-reviewed-version-channel-build-pin",
                    }
                ],
            }
        )
        with mock.patch.object(
            pipeline,
            "load_catalog",
            return_value={"cores": {"alpha": {}}},
        ), mock.patch.object(
            pipeline,
            "load_authoritative_core_pin_index",
            return_value={},
        ), mock.patch.object(
            pipeline,
            "release_source_graph_requirements",
            requirements,
        ), mock.patch.object(
            pipeline,
            "core_track_source_ancestry_verifier",
        ) as verifier_factory, mock.patch.object(
            pipeline,
            "prepare_release_source_graph",
            prepared,
        ), mock.patch.object(
            pipeline,
            "construct_core_track_inventory",
            inventory,
        ), mock.patch.object(
            pipeline,
            "load_json",
            return_value={},
        ), mock.patch.object(
            pipeline,
            "load_core_track_source_registry_index",
            return_value={},
        ), self.assertRaisesRegex(
            pipeline.PipelineError,
            "release source graph group inventory is incomplete: alpha",
        ):
            pipeline.prepare_release_group_source_graph(
                "main-test:universal",
                core_id="alpha",
            )

        requirements.assert_not_called()
        prepared.assert_not_called()
        verifier_factory.assert_not_called()
        self.assertIn("spruce_branch_bases", inventory.call_args.kwargs)

    def test_authorized_outlier_is_not_reintroduced_as_graph_ancestry(self) -> None:
        """The track validator, not the graph adapter, owns outlier policy."""

        registry = {
            "source_order_parent_bindings": [
                {"content_sha256": "1" * 64}
            ],
            "source_order_outliers": [
                {"parent_binding_content_sha256": "1" * 64}
            ],
        }
        validated = mock.Mock(return_value=registry)

        def load_manifest(path: Path) -> dict:
            if path == pipeline.DEFAULT_CORE_TRACKS:
                return registry
            return {}

        with mock.patch.object(
            pipeline,
            "load_json",
            side_effect=load_manifest,
        ), mock.patch.object(
            pipeline,
            "load_core_track_source_registry_index",
            return_value={},
        ), mock.patch.object(
            pipeline,
            "validate_core_tracks",
            validated,
        ):
            requirements = pipeline.release_source_graph_requirements(
                catalog={"cores": {"alpha": {}}},
                pin_index={},
            )

        self.assertEqual([], requirements)
        ancestry_recorder = validated.call_args.kwargs[
            "source_ancestry_verifier"
        ]
        self.assertTrue(callable(ancestry_recorder))
        self.assertEqual(
            registry,
            validated.call_args.args[0],
        )

    def test_frozen_parent_edge_reaches_graph_after_current_parent_moves(
        self,
    ) -> None:
        repository = "https://example.invalid/alpha.git"
        frozen_parent_commit = "1" * 40
        child_commit = "2" * 40
        current_parent_commit = "3" * 40
        frozen_parent_tree = "4" * 40
        child_tree = "5" * 40
        tuning_registry = pipeline.load_json(pipeline.DEFAULT_CHIPSET_TUNINGS)
        spruce_branch_bases = pipeline.load_json(
            pipeline.DEFAULT_SPRUCE_BRANCH_BASES
        )
        frozen_parent_slice, frozen_parent_basis = (
            track_model.core_track_version_slice(
                track="main",
                slice_time="2026-08-10T10:00:00Z",
                spruce_branch_bases=spruce_branch_bases,
            )
        )
        child_slice, _child_basis = track_model.core_track_version_slice(
            track="nightly",
            slice_time="2026-08-10T11:00:00Z",
            spruce_branch_bases=spruce_branch_bases,
        )
        current_parent_slice, _current_parent_basis = (
            track_model.core_track_version_slice(
                track="main",
                slice_time="2026-08-10T12:00:00Z",
                spruce_branch_bases=spruce_branch_bases,
            )
        )

        def source(commit: str, tree: str, requested_ref: str) -> dict:
            return {
                "url": repository,
                "requested_ref": requested_ref,
                "commit": commit,
                "tree": tree,
                "submodules": [],
                "resolved_commit": commit,
                "resolved_url": repository,
            }

        def pin_document(
            *, content_sha256: str, golden_source: dict
        ) -> dict:
            return {
                "content_sha256": content_sha256,
                "cores": {
                    "alpha": {
                        "selection": {
                            "targets": {
                                "arm64": {
                                    "golden_record": {
                                        "source": golden_source,
                                    }
                                }
                            }
                        }
                    }
                },
            }

        parent_entry = {
            "path": "pins/core-sets/alpha-frozen-parent.json",
            "pin_id": "alpha-frozen-parent",
            "file_sha256": "6" * 64,
            "content_sha256": "7" * 64,
            "core_id": "alpha",
            "architectures": ["arm64"],
            "tuning_identity": None,
            "source_repository": repository,
            "source_requested_ref": "refs/heads/main",
            "source_commit": frozen_parent_commit,
            "source_tree": frozen_parent_tree,
            "host_reproduction_content_sha256": "d" * 64,
        }
        child_entry = {
            "path": "pins/core-sets/alpha-child.json",
            "pin_id": "alpha-child",
            "file_sha256": "8" * 64,
            "content_sha256": "9" * 64,
            "core_id": "alpha",
            "architectures": ["arm64"],
            "tuning_identity": None,
            "source_repository": repository,
            "source_requested_ref": "refs/heads/nightly",
            "source_commit": child_commit,
            "source_tree": child_tree,
            "host_reproduction_content_sha256": "e" * 64,
        }
        current_parent_entry = {
            "path": "pins/core-sets/alpha-current-parent.json",
            "pin_id": "alpha-current-parent",
            "file_sha256": "b" * 64,
            "content_sha256": "c" * 64,
            "core_id": "alpha",
            "architectures": ["arm64"],
            "tuning_identity": None,
            "source_repository": repository,
            "source_requested_ref": "refs/heads/main",
            "source_commit": current_parent_commit,
            "source_tree": "a" * 40,
            "host_reproduction_content_sha256": "f" * 64,
        }
        pin_index = {
            "alpha-frozen-parent": parent_entry,
            "alpha-child": child_entry,
            "alpha-current-parent": current_parent_entry,
        }
        frozen_parent_cell = {
            "build_pin_id": "alpha-frozen-parent",
            "tuning_profile": "universal-v1",
            "applicable_chipsets": ["a523"],
            "version_slice": frozen_parent_slice,
        }
        current_parent_cell = {
            "build_pin_id": "alpha-current-parent",
            "tuning_profile": "universal-v1",
            "applicable_chipsets": ["a523"],
            "version_slice": current_parent_slice,
        }
        child_cell = {
            "build_pin_id": "alpha-child",
            "tuning_profile": "universal-v1",
            "applicable_chipsets": ["a523"],
            "version_slice": child_slice,
        }
        frozen_parent_variant = track_model.core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=frozen_parent_cell,
            pin_index=pin_index,
            tunings=tuning_registry,
        )
        child_variant = track_model.core_variant_id(
            core_id="alpha",
            cell_chipset="universal",
            cell=child_cell,
            pin_index=pin_index,
            tunings=tuning_registry,
        )
        captured_registry = copy.deepcopy(
            pipeline.load_json(pipeline.DEFAULT_CORE_TRACKS)
        )
        for track in track_model.CORE_TRACKS:
            captured_registry["tracks"][track]["test"] = {}
            captured_registry["tracks"][track]["stable"] = {}
            captured_registry["tracks"][track]["deferred"] = {}
        captured_registry["source_order_parent_bindings"] = []
        captured_registry["source_order_outliers"] = []
        captured_registry["tracks"]["main"]["test"] = {
            "alpha": {"universal": copy.deepcopy(frozen_parent_cell)}
        }
        captured_registry["version_policy"]["slice_comparison_bases"] = {
            frozen_parent_slice["content_sha256"]: frozen_parent_basis
        }
        captured_registry["version_policy"]["slice_branch_basis_snapshots"] = {
            spruce_branch_bases["content_sha256"]: (
                track_model._slice_branch_basis_snapshot(
                    spruce_branch_bases=spruce_branch_bases,
                    catalog=pipeline.load_json(pipeline.DEFAULT_CATALOG),
                    main_release_roster=pipeline.load_json(
                        pipeline.DEFAULT_SPRUCE_RELEASE_ROSTER
                    ),
                    catalog_file_sha256=pipeline.sha256_file(
                        pipeline.DEFAULT_CATALOG
                    ),
                    release_roster_file_sha256=pipeline.sha256_file(
                        pipeline.DEFAULT_SPRUCE_RELEASE_ROSTER
                    ),
                )
            )
        }
        captured_registry["content_sha256"] = (
            track_model.core_tracks_content_sha256(captured_registry)
        )
        captured_registry_digest, captured_registry_entry = (
            track_model._snapshot_index_entry(
                repository_root=pipeline.ROOT,
                snapshot=track_model.core_track_source_snapshot(
                    captured_registry
                ),
            )
        )
        source_registry_index = {
            captured_registry_digest: captured_registry_entry
        }
        parent_binding = track_model._source_order_parent_binding(
            source_registry_content_sha256=captured_registry_digest,
            track="nightly",
            core_id="alpha",
            chipset="universal",
            parent_origin_track="main",
            parent_selected_chipset="universal",
            parent_cell=frozen_parent_cell,
            parent_pin=parent_entry,
            parent_variant=frozen_parent_variant,
            parent_lineage=None,
            child_cell=child_cell,
            child_pin=child_entry,
            child_variant=child_variant,
        )
        tracks = {
            "main": {
                "test": {"alpha": {"universal": current_parent_cell}},
                "deferred": {},
            },
            "nightly": {
                "test": {"alpha": {"universal": child_cell}},
                "deferred": {},
            },
            "edge": {"test": {}, "deferred": {}},
        }
        registry = {
            "tracks": tracks,
            "source_order_parent_bindings": [parent_binding],
            "source_order_outliers": [],
        }
        pin_documents = {
            "alpha-frozen-parent.json": (
                pin_document(
                    content_sha256=parent_entry["content_sha256"],
                    golden_source=source(
                        frozen_parent_commit,
                        frozen_parent_tree,
                        "refs/heads/main",
                    ),
                ),
                parent_entry["file_sha256"],
            ),
            "alpha-child.json": (
                pin_document(
                    content_sha256=child_entry["content_sha256"],
                    golden_source=source(
                        child_commit,
                        child_tree,
                        "refs/heads/nightly",
                    ),
                ),
                child_entry["file_sha256"],
            ),
        }

        def validate_temporal_binding(document: dict, **kwargs) -> dict:
            self.assertEqual(registry, document)
            self.assertEqual(
                [],
                track_model._source_order_errors(
                    tracks,
                    source_order_parent_bindings=document[
                        "source_order_parent_bindings"
                    ],
                    source_order_outliers=document["source_order_outliers"],
                    source_registry_index=source_registry_index,
                    pin_index=pin_index,
                    tunings=tuning_registry,
                    source_ancestry_verifier=kwargs[
                        "source_ancestry_verifier"
                    ],
                    source_ancestry_core_id=None,
                ),
            )
            return document

        def load_manifest(path: Path) -> dict:
            if path == pipeline.DEFAULT_CORE_TRACKS:
                return registry
            if path == pipeline.DEFAULT_CHIPSET_TUNINGS:
                return tuning_registry
            return {}

        with mock.patch.object(
            pipeline,
            "load_json",
            side_effect=load_manifest,
        ), mock.patch.object(
            pipeline,
            "load_json_with_sha256",
            side_effect=lambda path: pin_documents[path.name],
        ), mock.patch.object(
            pipeline,
            "load_core_track_source_registry_index",
            return_value=source_registry_index,
        ), mock.patch.object(
            pipeline,
            "validate_core_tracks",
            side_effect=validate_temporal_binding,
        ):
            requirements = pipeline.release_source_graph_requirements(
                catalog={"cores": {"alpha": {}}},
                pin_index=pin_index,
            )

        self.assertEqual(
            [
                {
                    "core_id": "alpha",
                    "repository": repository,
                    "sources": [
                        {
                            "requested_ref": "refs/heads/main",
                            "commit": frozen_parent_commit,
                            "tree": frozen_parent_tree,
                        },
                        {
                            "requested_ref": "refs/heads/nightly",
                            "commit": child_commit,
                            "tree": child_tree,
                        },
                    ],
                    "ancestry": [
                        {
                            "ancestor": frozen_parent_commit,
                            "descendant": child_commit,
                        }
                    ],
                }
            ],
            requirements,
        )

    def test_full_history_ref_fetch_and_exact_ancestry_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, sources = source_history(root)
            cache = root / ".local-e2e" / "source-repositories"
            runner = RewritingGitRunner(remote)
            descendant = git("rev-parse", "refs/heads/main", cwd=remote)
            ancestor = git("rev-parse", f"{descendant}^", cwd=remote)
            requirement = {
                "core_id": "alpha",
                "repository": PINNED_REPOSITORY,
                "sources": sources,
                "ancestry": [
                    {"ancestor": ancestor, "descendant": descendant}
                ],
            }

            report = prepare_release_source_graph(
                requirements=[requirement],
                repository_root=root,
                repository_cache=cache,
                ancestry_verifier=local_git_source_ancestry_verifier(cache),
                git_runner=runner,
            )

            self.assertEqual(report["status"], "verified")
            self.assertEqual(report["repository_count"], 1)
            self.assertEqual(report["ancestry_count"], 1)
            fetches = [command for command in runner.commands if "fetch" in command]
            self.assertEqual(
                fetches,
                [
                    source_ref_fetch_argv(
                        cache / "alpha.git",
                        PINNED_REPOSITORY,
                        "refs/heads/main",
                    )
                ],
            )
            flat = "\n".join(" ".join(command) for command in runner.commands)
            self.assertNotIn("--depth", flat)
            self.assertNotIn("--filter", flat)
            self.assertNotIn("--shallow", flat)
            self.assertFalse((cache / "alpha.git" / "commondir").exists())
            self.assertEqual(
                git(
                    f"--git-dir={cache / 'alpha.git'}",
                    "rev-parse",
                    "--is-shallow-repository",
                    cwd=root,
                ),
                "false",
            )

    def test_missing_requested_ref_fails_before_ancestry_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, sources = source_history(root)
            descendant = git("rev-parse", "refs/heads/main", cwd=remote)
            ancestor = git("rev-parse", f"{descendant}^", cwd=remote)
            for source in sources:
                source["requested_ref"] = "refs/heads/unavailable"
            sources.sort(
                key=lambda item: (item["requested_ref"], item["commit"], item["tree"])
            )
            cache = root / ".local-e2e" / "source-repositories"

            with self.assertRaisesRegex(PipelineError, "fetch exact release source ref"):
                prepare_release_source_graph(
                    requirements=[
                        {
                            "core_id": "alpha",
                            "repository": PINNED_REPOSITORY,
                            "sources": sources,
                            "ancestry": [
                                {"ancestor": ancestor, "descendant": descendant}
                            ],
                        }
                    ],
                    repository_root=root,
                    repository_cache=cache,
                    ancestry_verifier=local_git_source_ancestry_verifier(cache),
                    git_runner=RewritingGitRunner(remote),
                )

    def test_equal_commit_registry_needs_no_cache_or_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / ".local-e2e" / "source-repositories"
            requirement = {
                "core_id": "alpha",
                "repository": PINNED_REPOSITORY,
                "sources": [
                    {
                        "requested_ref": "refs/heads/main",
                        "commit": "1" * 40,
                        "tree": "2" * 40,
                    }
                ],
                "ancestry": [],
            }

            def forbidden_runner(*_args, **_kwargs):
                raise AssertionError("equal source commits must not invoke Git")

            report = prepare_release_source_graph(
                requirements=[requirement],
                repository_root=root,
                repository_cache=cache,
                ancestry_verifier=lambda *_args: True,
                git_runner=forbidden_runner,
            )
            self.assertFalse(cache.exists())
            self.assertFalse(report["network_fetch_required"])

    def test_requirement_and_fetch_argv_are_fail_closed(self) -> None:
        valid = {
            "core_id": "alpha",
            "repository": PINNED_REPOSITORY,
            "sources": [
                {
                    "requested_ref": "refs/tags/v1.0.0",
                    "commit": "1" * 40,
                    "tree": "2" * 40,
                },
                {
                    "requested_ref": "refs/tags/v2.0.0",
                    "commit": "3" * 40,
                    "tree": "4" * 40,
                },
            ],
            "ancestry": [{"ancestor": "1" * 40, "descendant": "3" * 40}],
        }
        self.assertEqual(validated_source_graph_requirements([valid]), [valid])
        with self.assertRaisesRegex(PipelineError, "repository is invalid"):
            validated_source_graph_requirements(
                [{**valid, "repository": "ext::sh -c unsafe"}]
            )
        with self.assertRaisesRegex(PipelineError, "source 0 is invalid"):
            forged = {**valid, "sources": [
                {**valid["sources"][0], "requested_ref": "refs/heads/main:evil"},
                valid["sources"][1],
            ]}
            validated_source_graph_requirements([forged])
        commit_argv = source_commit_fetch_argv(
            Path("/repo/.local-e2e/source-repositories/alpha.git"),
            PINNED_REPOSITORY,
            "3" * 40,
        )
        self.assertEqual(commit_argv[-2], PINNED_REPOSITORY)
        self.assertEqual(
            commit_argv[-1],
            "+" + "3" * 40 + ":refs/spruce-source-commits/" + "3" * 40,
        )


if __name__ == "__main__":
    unittest.main()
