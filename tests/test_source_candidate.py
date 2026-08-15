"""Focused offline tests for unpinned source-candidate catalogs."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib import source_candidate


def _run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        list(args),
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout.strip()


def _write_json(path: Path, value: object) -> bytes:
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


class SourceCandidateFixture:
    def __init__(self, root: Path, *, overlay_mismatch: bool = False) -> None:
        self.root = root
        self.core_id = "demo"
        self.url = "https://example.invalid/demo.git"
        source = root / "source"
        self.source = source
        source.mkdir(parents=True)
        _run("git", "init", "-q", "-b", "main", cwd=source)
        _run("git", "config", "user.email", "candidate@example.invalid", cwd=source)
        _run("git", "config", "user.name", "Candidate Test", cwd=source)
        (source / "overlay.txt").write_text("stable preimage\n", encoding="utf-8")
        (source / "state.txt").write_text("base\n", encoding="utf-8")
        _run("git", "add", ".", cwd=source)
        first_env = dict(os.environ)
        first_env.update(
            {
                "GIT_AUTHOR_DATE": "1700000000 +0000",
                "GIT_COMMITTER_DATE": "1700000000 +0000",
            }
        )
        _run("git", "commit", "-q", "-m", "base", cwd=source, env=first_env)
        self.base_commit = _run("git", "rev-parse", "HEAD", cwd=source)
        self.base_tree = _run("git", "rev-parse", "HEAD^{tree}", cwd=source)

        (source / "state.txt").write_text("edge\n", encoding="utf-8")
        _run("git", "add", "state.txt", cwd=source)
        second_env = dict(os.environ)
        second_env.update(
            {
                "GIT_AUTHOR_DATE": "1700000100 +0000",
                "GIT_COMMITTER_DATE": "1700000100 +0000",
            }
        )
        _run("git", "commit", "-q", "-m", "edge", cwd=source, env=second_env)
        self.commit = _run("git", "rev-parse", "HEAD", cwd=source)
        self.tree = _run("git", "rev-parse", "HEAD^{tree}", cwd=source)
        self.epoch = int(_run("git", "show", "-s", "--format=%ct", "HEAD", cwd=source))

        self.mirror = root / ".local-e2e" / "source-repositories" / "demo.git"
        self.mirror.parent.mkdir(parents=True)
        _run("git", "clone", "-q", "--bare", str(source), str(self.mirror), cwd=root)
        _run(
            "git",
            f"--git-dir={self.mirror}",
            "remote",
            "set-url",
            "origin",
            self.url,
            cwd=root,
        )
        self.frozen_ref = "refs/spruce-edge-refs/" + hashlib.sha256(
            b"refs/heads/main"
        ).hexdigest()
        _run(
            "git",
            f"--git-dir={self.mirror}",
            "update-ref",
            self.frozen_ref,
            self.commit,
            cwd=root,
        )

        overlay_sha = hashlib.sha256(b"stable preimage\n").hexdigest()
        build: dict[str, object] = {
            "artifact_name": "demo_libretro.so",
            "driver": "direct-make",
            "output_path": "demo_libretro.so",
            "platforms": {"arm64": "unix"},
            "source_date_epoch": 1700000000,
            "source_dir": "demo",
        }
        if overlay_mismatch:
            build["overlays"] = {
                "arm64": [
                    {
                        "kind": "git-apply-v1",
                        "patch_path": "patches/demo.patch",
                        "patch_sha256": "2" * 64,
                        "source_path": "overlay.txt",
                        "preimage_sha256": "0" * 64,
                        "postimage_sha256": "3" * 64,
                    }
                ]
            }
        self.spec = {
            "build": build,
            "metadata": {
                "artifact_name": "demo_libretro.info",
                "source_path": "/libretro-super/dist/info/demo_libretro.info",
            },
            "source": {
                "commit": self.base_commit,
                "requested_ref": "refs/heads/main",
                "tree": self.base_tree,
                "url": self.url,
            },
            "targets": ["arm64"],
            "workflow": ".github/workflows/build-demo.yml",
        }
        self.catalog = {
            "$schema": "./core-builds.schema.json",
            "schema_version": 2,
            "policy": {"publication": "disabled"},
            "resolver": {},
            "toolchains": {},
            "cores": {self.core_id: self.spec},
        }
        self.catalog_path = root / "manifests" / "core-builds.json"
        catalog_raw = _write_json(self.catalog_path, self.catalog)
        self.snapshot_path = (
            root
            / ".local-e2e"
            / "source-probes"
            / "edge-test"
            / "edge-source-ref-snapshot-test.json"
        )
        risk = {
            "catalog_declared_submodules": 0,
            "driver": "direct-make",
            "git_version": False,
            "overlays": 1 if overlay_mismatch else 0,
            "recursive_submodules": True,
            "source_aware_log_contract": False,
            "source_date_epoch": True,
            "submodule_fetch": True,
        }
        self.snapshot = {
            "captured_at": "2026-08-10T05:12:51Z",
            "catalog": {
                "file_sha256": hashlib.sha256(catalog_raw).hexdigest(),
                "path": "manifests/core-builds.json",
            },
            "local_only": True,
            "publication": "disabled",
            "resolution_window": {
                "first_fetch_mtime": "2026-08-10T05:07:16Z",
                "last_fetch_mtime": "2026-08-10T05:10:41Z",
            },
            "schema_version": 1,
            "snapshot_id": "edge-source-ref-snapshot-test",
            "sources": {
                self.core_id: {
                    "catalog_commit": self.base_commit,
                    "catalog_is_ancestor": True,
                    "catalog_tree": self.base_tree,
                    "commit": self.commit,
                    "commit_epoch": self.epoch,
                    "frozen_local_ref": self.frozen_ref,
                    "latest_semantics": "exact-branch-tip",
                    "recipe_risk": risk,
                    "ref_kind": "branch",
                    "ref_object": self.commit,
                    "ref_object_type": "commit",
                    "requested_ref": "refs/heads/main",
                    "status": "fast-forward",
                    "top_level_gitlinks": [],
                    "tree": self.tree,
                    "url": self.url,
                }
            },
            "summary": {
                "branch_core_count": 1,
                "core_count": 1,
                "diverged_core_count": 0,
                "fast-forward_core_count": 1,
                "latest_policy_gap_core_count": 0,
                "latest_semantics_defined_core_count": 1,
                "source_aware_log_contract_core_count": 0,
                "tag_core_count": 0,
                "top_level_gitlink_core_count": 0,
                "top_level_gitlink_count": 0,
                "unchanged_core_count": 0,
                "unique_url_ref_count": 1,
            },
            "validation_scope": "remote-ref-resolution-only",
        }
        self.write_snapshot()
        generator = root / "scripts" / "core_pipeline_lib" / "source_candidate.py"
        generator.parent.mkdir(parents=True)
        generator.write_text("# frozen test generator\n", encoding="utf-8")
        self.generator_path = generator

    def write_snapshot(self) -> None:
        self.snapshot["content_sha256"] = source_candidate._content_sha256(  # noqa: SLF001
            self.snapshot
        )
        _write_json(self.snapshot_path, self.snapshot)

    def mutate_catalog_recipe(self) -> None:
        self.catalog["cores"][self.core_id]["build"]["recipe_revision"] = 2
        _write_json(self.catalog_path, self.catalog)


class SourceCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="source-candidate-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _catalog_validator(_catalog: dict) -> None:
        return None

    @staticmethod
    def _eligibility_validator(_catalog: dict, _cores: list[str]) -> None:
        return None

    @staticmethod
    def _candidate_catalog_validator(
        _catalog: dict,
        _core: str,
        _canonical_spec: dict,
        projection: source_candidate.SourceCandidateContractProjection | None,
    ) -> None:
        if projection is not None:
            raise AssertionError("ordinary fixture unexpectedly requested projection")

    @staticmethod
    def _source_aware_contract_resolver(_core: str) -> bool:
        return False

    @staticmethod
    def _renderer(
        _core: str,
        _arch: str,
        _spec: dict,
        _resolver: dict,
        _canonical_spec: dict,
        projection: source_candidate.SourceCandidateContractProjection | None,
    ) -> str:
        if projection is not None:
            raise AssertionError("ordinary fixture unexpectedly requested projection")
        return "set -eu\n"

    def _prepare(
        self,
        fixture: SourceCandidateFixture,
        *,
        catalog_rebase: Path | None = None,
    ) -> dict:
        with mock.patch.object(
            source_candidate, "__file__", str(fixture.generator_path)
        ):
            return source_candidate.prepare_source_candidate_catalog(
                repository_root=fixture.root,
                catalog_path=fixture.catalog_path,
                snapshot_path=fixture.snapshot_path,
                core_id=fixture.core_id,
                catalog_rebase_path=catalog_rebase,
                catalog_validator=self._catalog_validator,
                candidate_catalog_validator=self._candidate_catalog_validator,
                eligibility_validator=self._eligibility_validator,
                build_renderer=self._renderer,
                source_aware_contract_resolver=(
                    self._source_aware_contract_resolver
                ),
            )

    def _validate(self, fixture: SourceCandidateFixture, catalog_path: Path) -> dict:
        with mock.patch.object(
            source_candidate, "__file__", str(fixture.generator_path)
        ):
            return source_candidate.validate_source_candidate_catalog(
                repository_root=fixture.root,
                canonical_catalog_path=fixture.catalog_path,
                candidate_catalog_path=catalog_path,
                catalog_validator=self._catalog_validator,
                candidate_catalog_validator=self._candidate_catalog_validator,
                eligibility_validator=self._eligibility_validator,
                build_renderer=self._renderer,
                source_aware_contract_resolver=(
                    self._source_aware_contract_resolver
                ),
            )

    def test_prepare_creates_exact_one_core_catalog_and_derives_epoch(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        report = self._prepare(fixture)
        output = self.root / report["catalog"]["path"]
        candidate = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual({fixture.core_id}, set(candidate["cores"]))
        spec = candidate["cores"][fixture.core_id]
        self.assertEqual(fixture.commit, spec["source"]["commit"])
        self.assertEqual(fixture.tree, spec["source"]["tree"])
        self.assertEqual(fixture.epoch, spec["build"]["source_date_epoch"])
        self.assertEqual(
            "candidate-commit-epoch", report["source_date_epoch_derivation"]
        )
        self.assertEqual(
            fixture.snapshot["content_sha256"],
            candidate["source_candidate"]["snapshot"]["content_sha256"],
        )
        retained_ref = candidate["source_candidate"]["selection"][
            "frozen_local_ref"
        ]
        self.assertNotEqual(fixture.frozen_ref, retained_ref)
        self.assertEqual(
            fixture.commit,
            _run(
                "git",
                f"--git-dir={fixture.mirror}",
                "show-ref",
                "--verify",
                "--hash",
                retained_ref,
                cwd=fixture.root,
            ),
        )
        validated = self._validate(fixture, output)
        self.assertEqual("valid", validated["status"])
        self.assertEqual(report["candidate_id"], validated["candidate_id"])
        self.assertEqual(report["catalog"], validated["catalog"])
        from .core_contract_helpers import pipeline

        with self.assertRaisesRegex(
            pipeline.PipelineError,
            "ordinary catalog validation rejects source-candidate provenance",
        ):
            pipeline.validate_catalog(candidate)
        with self.assertRaisesRegex(PipelineError, "refusing to reuse"):
            self._prepare(fixture)
        _run(
            "git",
            f"--git-dir={fixture.mirror}",
            "update-ref",
            fixture.frozen_ref,
            fixture.base_commit,
            cwd=fixture.root,
        )
        self.assertIsNone(
            source_candidate.validate_promoted_source_candidate_contract(
                repository_root=fixture.root,
                canonical_catalog_path=fixture.catalog_path,
                candidate_catalog=candidate,
                catalog_validator=self._catalog_validator,
                source_aware_contract_resolver=(
                    self._source_aware_contract_resolver
                ),
            )
        )

    def test_source_aware_fast_forward_yields_authenticated_projection(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        fixture.snapshot["sources"][fixture.core_id]["recipe_risk"][
            "source_aware_log_contract"
        ] = True
        fixture.snapshot["summary"]["source_aware_log_contract_core_count"] = 1
        fixture.write_snapshot()
        projections: list[source_candidate.SourceCandidateContractProjection] = []

        def candidate_validator(
            _catalog: dict,
            _core: str,
            _canonical_spec: dict,
            projection: source_candidate.SourceCandidateContractProjection | None,
        ) -> None:
            self.assertIsNotNone(projection)
            assert projection is not None
            projections.append(projection)

        def renderer(
            _core: str,
            _arch: str,
            _spec: dict,
            _resolver: dict,
            _canonical_spec: dict,
            projection: source_candidate.SourceCandidateContractProjection | None,
        ) -> str:
            self.assertIsNotNone(projection)
            return "set -eu\n"

        with mock.patch.object(
            source_candidate, "__file__", str(fixture.generator_path)
        ):
            report = source_candidate.prepare_source_candidate_catalog(
                repository_root=fixture.root,
                catalog_path=fixture.catalog_path,
                snapshot_path=fixture.snapshot_path,
                core_id=fixture.core_id,
                catalog_rebase_path=None,
                catalog_validator=self._catalog_validator,
                candidate_catalog_validator=candidate_validator,
                eligibility_validator=self._eligibility_validator,
                build_renderer=renderer,
                source_aware_contract_resolver=lambda _core: True,
            )
        self.assertGreaterEqual(len(projections), 2)
        projection = projections[0]
        self.assertEqual(report["candidate_id"], projection.candidate_id)
        self.assertEqual(fixture.base_commit, projection.canonical_commit)
        self.assertEqual(fixture.commit, projection.candidate_commit)
        self.assertEqual(fixture.base_tree, projection.canonical_tree)
        self.assertEqual(fixture.tree, projection.candidate_tree)

    def test_source_aware_projection_rejects_explicit_git_version(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        fixture.catalog["cores"][fixture.core_id]["build"]["git_version"] = {
            "derivation": "test"
        }
        catalog_raw = _write_json(fixture.catalog_path, fixture.catalog)
        fixture.snapshot["catalog"]["file_sha256"] = hashlib.sha256(
            catalog_raw
        ).hexdigest()
        risk = fixture.snapshot["sources"][fixture.core_id]["recipe_risk"]
        risk["git_version"] = True
        risk["source_aware_log_contract"] = True
        fixture.snapshot["summary"]["source_aware_log_contract_core_count"] = 1
        fixture.write_snapshot()
        with self.assertRaisesRegex(PipelineError, "git-version projection"):
            with mock.patch.object(
                source_candidate, "__file__", str(fixture.generator_path)
            ):
                source_candidate.prepare_source_candidate_catalog(
                    repository_root=fixture.root,
                    catalog_path=fixture.catalog_path,
                    snapshot_path=fixture.snapshot_path,
                    core_id=fixture.core_id,
                    catalog_rebase_path=None,
                    catalog_validator=self._catalog_validator,
                    candidate_catalog_validator=lambda *_args: None,
                    eligibility_validator=self._eligibility_validator,
                    build_renderer=lambda *_args: "set -eu\n",
                    source_aware_contract_resolver=lambda _core: True,
                )

    def test_promoted_projection_uses_frozen_bytes_not_transient_candidate(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        fixture.snapshot["sources"][fixture.core_id]["recipe_risk"][
            "source_aware_log_contract"
        ] = True
        fixture.snapshot["summary"]["source_aware_log_contract_core_count"] = 1
        fixture.write_snapshot()
        with mock.patch.object(
            source_candidate, "__file__", str(fixture.generator_path)
        ):
            report = source_candidate.prepare_source_candidate_catalog(
                repository_root=fixture.root,
                catalog_path=fixture.catalog_path,
                snapshot_path=fixture.snapshot_path,
                core_id=fixture.core_id,
                catalog_rebase_path=None,
                catalog_validator=self._catalog_validator,
                candidate_catalog_validator=lambda *_args: None,
                eligibility_validator=self._eligibility_validator,
                build_renderer=lambda *_args: "set -eu\n",
                source_aware_contract_resolver=lambda _core: True,
            )
        candidate_path = fixture.root / report["catalog"]["path"]
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        retained_ref = candidate["source_candidate"]["selection"][
            "frozen_local_ref"
        ]
        self.assertNotEqual(fixture.frozen_ref, retained_ref)
        self.assertEqual(
            fixture.commit,
            _run(
                "git",
                f"--git-dir={fixture.mirror}",
                "show-ref",
                "--verify",
                "--hash",
                retained_ref,
                cwd=fixture.root,
            ),
        )
        # A later same-branch probe may move the snapshot producer's reusable
        # branch ref.  The promoted candidate remains bound to its unique,
        # commit-specific retained ref.
        _run(
            "git",
            f"--git-dir={fixture.mirror}",
            "update-ref",
            fixture.frozen_ref,
            fixture.base_commit,
            cwd=fixture.root,
        )
        candidate_path.unlink()
        fixture.generator_path.write_text("# changed current generator\n", encoding="utf-8")
        # Evolution of another core does not invalidate this exact one-core
        # candidate.  Non-core resolver/toolchain/policy bytes remain part of
        # the active canonical trust boundary below.
        fixture.catalog["cores"]["unrelated"] = copy.deepcopy(fixture.spec)
        _write_json(fixture.catalog_path, fixture.catalog)
        projection = source_candidate.validate_promoted_source_candidate_contract(
            repository_root=fixture.root,
            canonical_catalog_path=fixture.catalog_path,
            candidate_catalog=candidate,
            catalog_validator=self._catalog_validator,
            source_aware_contract_resolver=lambda _core: True,
        )
        self.assertIsNotNone(projection)
        assert projection is not None
        self.assertEqual(fixture.commit, projection.candidate_commit)

        for label, mutate in (
            (
                "resolver",
                lambda value: value["resolver"].update(
                    {"forged": "0" * 40}
                ),
            ),
            (
                "policy",
                lambda value: value["policy"].update(
                    {"publication": "enabled-forged"}
                ),
            ),
        ):
            with self.subTest(label=label):
                changed = copy.deepcopy(candidate)
                mutate(changed)
                with self.assertRaisesRegex(
                    PipelineError,
                    "non-core catalog bytes differ",
                ):
                    source_candidate.validate_promoted_source_candidate_contract(
                        repository_root=fixture.root,
                        canonical_catalog_path=fixture.catalog_path,
                        candidate_catalog=changed,
                        catalog_validator=self._catalog_validator,
                        source_aware_contract_resolver=lambda _core: True,
                    )

        tampered = copy.deepcopy(candidate)
        tampered["source_candidate"]["candidate_id"] = "0" * 64
        with self.assertRaisesRegex(PipelineError, "provenance identity"):
            source_candidate.validate_promoted_source_candidate_contract(
                repository_root=fixture.root,
                canonical_catalog_path=fixture.catalog_path,
                candidate_catalog=tampered,
                catalog_validator=self._catalog_validator,
                source_aware_contract_resolver=lambda _core: True,
            )

        for label, mutate in (
            (
                "epoch",
                lambda value: value["source_candidate"]["selection"].update(
                    {"commit_epoch": fixture.epoch + 1}
                ),
            ),
            (
                "gitlinks",
                lambda value: value["source_candidate"]["selection"].update(
                    {
                        "top_level_gitlinks": [
                            {"path": "foreign", "commit": "f" * 40}
                        ]
                    }
                ),
            ),
        ):
            with self.subTest(label=label):
                changed = copy.deepcopy(candidate)
                mutate(changed)
                provenance = changed["source_candidate"]
                provenance["candidate_id"] = source_candidate._content_sha256(
                    provenance
                )
                with self.assertRaisesRegex(
                    PipelineError, "selection differs from its frozen snapshot"
                ):
                    source_candidate.validate_promoted_source_candidate_contract(
                        repository_root=fixture.root,
                        canonical_catalog_path=fixture.catalog_path,
                        candidate_catalog=changed,
                        catalog_validator=self._catalog_validator,
                        source_aware_contract_resolver=lambda _core: True,
                    )

        fixture.catalog["cores"][fixture.core_id]["source"]["commit"] = "0" * 40
        _write_json(fixture.catalog_path, fixture.catalog)
        with self.assertRaisesRegex(PipelineError, "snapshot baseline differs"):
            source_candidate.validate_promoted_source_candidate_contract(
                repository_root=fixture.root,
                canonical_catalog_path=fixture.catalog_path,
                candidate_catalog=candidate,
                catalog_validator=self._catalog_validator,
                source_aware_contract_resolver=lambda _core: True,
            )

    def test_recipe_risk_counts_overlay_targets_not_overlay_items(self) -> None:
        fixture = SourceCandidateFixture(self.root, overlay_mismatch=True)
        spec = copy.deepcopy(fixture.spec)
        overlays = spec["build"]["overlays"]["arm64"]
        overlays.append(copy.deepcopy(overlays[0]))
        entry = copy.deepcopy(fixture.snapshot["sources"][fixture.core_id])
        self.assertEqual(1, entry["recipe_risk"]["overlays"])
        validated = source_candidate._validated_source_entry(
            entry,
            core_id=fixture.core_id,
            catalog_spec=spec,
            source_aware_log_contract=False,
        )
        self.assertEqual(entry["commit"], validated["commit"])

    def test_stale_catalog_requires_exact_explicit_rebase(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        fixture.mutate_catalog_recipe()
        with self.assertRaisesRegex(PipelineError, "catalog binding is stale"):
            self._prepare(fixture)
        rebase = source_candidate.prepare_source_snapshot_catalog_rebase(
            repository_root=self.root,
            catalog_path=fixture.catalog_path,
            snapshot_path=fixture.snapshot_path,
            core_id=fixture.core_id,
            catalog_validator=self._catalog_validator,
            source_aware_contract_resolver=self._source_aware_contract_resolver,
        )
        rebase_path = self.root / rebase["catalog_rebase"]["path"]
        report = self._prepare(fixture, catalog_rebase=rebase_path)
        candidate = json.loads(
            (self.root / report["catalog"]["path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            rebase["catalog_rebase"],
            candidate["source_candidate"]["catalog_rebase"],
        )
        validated = self._validate(
            fixture,
            self.root / report["catalog"]["path"],
        )
        self.assertEqual("valid", validated["status"])

    def test_catalog_rebase_rejects_changed_source_tuple(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        fixture.mutate_catalog_recipe()
        fixture.catalog["cores"][fixture.core_id]["source"]["requested_ref"] = (
            "refs/heads/other"
        )
        _write_json(fixture.catalog_path, fixture.catalog)
        with self.assertRaisesRegex(PipelineError, "snapshot baseline differs"):
            source_candidate.prepare_source_snapshot_catalog_rebase(
                repository_root=self.root,
                catalog_path=fixture.catalog_path,
                snapshot_path=fixture.snapshot_path,
                core_id=fixture.core_id,
                catalog_validator=self._catalog_validator,
                source_aware_contract_resolver=(
                    self._source_aware_contract_resolver
                ),
            )

    def test_validator_rejects_provenance_execution_and_path_tampering(self) -> None:
        mutations = (
            ("generator", lambda value: value["source_candidate"]["generator"].update(
                {"sha256": "0" * 64}
            )),
            ("source", lambda value: value["cores"]["demo"]["source"].update(
                {"commit": "0" * 40}
            )),
            ("epoch", lambda value: value["cores"]["demo"]["build"].update(
                {"source_date_epoch": 1700000300}
            )),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                root = self.root / label
                fixture = SourceCandidateFixture(root)
                report = self._prepare(fixture)
                output = root / report["catalog"]["path"]
                candidate = json.loads(output.read_text(encoding="utf-8"))
                mutate(candidate)
                _write_json(output, candidate)
                with self.assertRaisesRegex(PipelineError, "exact provenance"):
                    self._validate(fixture, output)

        fixture = SourceCandidateFixture(self.root / "path")
        report = self._prepare(fixture)
        output = fixture.root / report["catalog"]["path"]
        wrong = output.parent.parent / ("f" * 64) / "core-builds.json"
        _write_json(wrong, json.loads(output.read_text(encoding="utf-8")))
        with self.assertRaisesRegex(PipelineError, "path is non-canonical"):
            self._validate(fixture, wrong)

    def test_validator_reopens_snapshot_rebase_mirror_and_current_base(self) -> None:
        fixture = SourceCandidateFixture(self.root / "snapshot")
        report = self._prepare(fixture)
        output = fixture.root / report["catalog"]["path"]
        fixture.snapshot["captured_at"] = "2026-08-10T05:12:52Z"
        fixture.write_snapshot()
        with self.assertRaisesRegex(PipelineError, "exact provenance"):
            self._validate(fixture, output)

        fixture = SourceCandidateFixture(self.root / "mirror")
        report = self._prepare(fixture)
        output = fixture.root / report["catalog"]["path"]
        _run(
            "git",
            f"--git-dir={fixture.mirror}",
            "remote",
            "set-url",
            "origin",
            "https://example.invalid/redirected.git",
            cwd=fixture.root,
        )
        with self.assertRaisesRegex(PipelineError, "frozen snapshot"):
            self._validate(fixture, output)

        fixture = SourceCandidateFixture(self.root / "base")
        report = self._prepare(fixture)
        output = fixture.root / report["catalog"]["path"]
        fixture.mutate_catalog_recipe()
        with self.assertRaisesRegex(PipelineError, "required stale-snapshot rebase"):
            self._validate(fixture, output)

        fixture = SourceCandidateFixture(self.root / "rebase")
        fixture.mutate_catalog_recipe()
        rebase = source_candidate.prepare_source_snapshot_catalog_rebase(
            repository_root=fixture.root,
            catalog_path=fixture.catalog_path,
            snapshot_path=fixture.snapshot_path,
            core_id=fixture.core_id,
            catalog_validator=self._catalog_validator,
            source_aware_contract_resolver=self._source_aware_contract_resolver,
        )
        rebase_path = fixture.root / rebase["catalog_rebase"]["path"]
        report = self._prepare(fixture, catalog_rebase=rebase_path)
        output = fixture.root / report["catalog"]["path"]
        rebase_document = json.loads(rebase_path.read_text(encoding="utf-8"))
        rebase_document["current_catalog"]["core_spec_sha256"] = "0" * 64
        rebase_document["content_sha256"] = source_candidate._content_sha256(
            rebase_document
        )
        _write_json(rebase_path, rebase_document)
        with self.assertRaisesRegex(PipelineError, "rebase is stale"):
            self._validate(fixture, output)

    def test_create_roots_reject_parent_symlinks(self) -> None:
        fixture = SourceCandidateFixture(self.root / "candidate")
        outside = fixture.root / "outside"
        outside.mkdir()
        candidate_root = fixture.root / ".local-e2e" / "source-candidates"
        candidate_root.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(PipelineError, "parent symlink"):
            self._prepare(fixture)
        self.assertEqual([], list(outside.iterdir()))

        fixture = SourceCandidateFixture(self.root / "rebase-parent")
        fixture.mutate_catalog_recipe()
        outside = fixture.root / "outside"
        outside.mkdir()
        rebase_root = (
            fixture.root
            / ".local-e2e"
            / "source-probes"
            / "catalog-rebases"
        )
        rebase_root.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(PipelineError, "parent symlink"):
            source_candidate.prepare_source_snapshot_catalog_rebase(
                repository_root=fixture.root,
                catalog_path=fixture.catalog_path,
                snapshot_path=fixture.snapshot_path,
                core_id=fixture.core_id,
                catalog_validator=self._catalog_validator,
                source_aware_contract_resolver=(
                    self._source_aware_contract_resolver
                ),
            )
        self.assertEqual([], list(outside.iterdir()))

    def test_flycast_tag_and_uae4arm_divergence_are_explicitly_deferred(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        tag_spec = copy.deepcopy(fixture.spec)
        tag_entry = copy.deepcopy(fixture.snapshot["sources"][fixture.core_id])
        tag_ref = "refs/tags/v2.6"
        tag_spec["source"]["requested_ref"] = tag_ref
        tag_entry.update(
            {
                "requested_ref": tag_ref,
                "ref_kind": "tag",
                "latest_semantics": "catalog-tag-only-not-latest",
                "frozen_local_ref": "refs/spruce-edge-refs/"
                + hashlib.sha256(tag_ref.encode()).hexdigest(),
            }
        )
        with self.assertRaisesRegex(
            PipelineError, "tag policy is unsupported/deferred: flycast"
        ):
            source_candidate._validated_source_entry(
                tag_entry,
                core_id="flycast",
                catalog_spec=tag_spec,
                source_aware_log_contract=False,
            )

        diverged_entry = copy.deepcopy(
            fixture.snapshot["sources"][fixture.core_id]
        )
        diverged_entry.update(
            {"status": "diverged", "catalog_is_ancestor": False}
        )
        with self.assertRaisesRegex(
            PipelineError, "divergence policy is unsupported/deferred: uae4arm"
        ):
            source_candidate._validated_source_entry(
                diverged_entry,
                core_id="uae4arm",
                catalog_spec=fixture.spec,
                source_aware_log_contract=False,
            )

    def test_mirror_rejects_commondir_and_alternate_object_store(self) -> None:
        for forbidden in ("commondir", "objects/info/alternates"):
            with self.subTest(forbidden=forbidden):
                root = self.root / forbidden.replace("/", "-")
                fixture = SourceCandidateFixture(root)
                path = fixture.mirror / forbidden
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("/tmp/untrusted\n", encoding="utf-8")
                with self.assertRaisesRegex(PipelineError, "forbidden graph inputs"):
                    with mock.patch.object(
                        source_candidate, "__file__", str(fixture.generator_path)
                    ):
                        source_candidate.prepare_source_candidate_catalog(
                            repository_root=root,
                            catalog_path=fixture.catalog_path,
                            snapshot_path=fixture.snapshot_path,
                            core_id=fixture.core_id,
                            catalog_rebase_path=None,
                            catalog_validator=self._catalog_validator,
                            candidate_catalog_validator=(
                                self._candidate_catalog_validator
                            ),
                            eligibility_validator=self._eligibility_validator,
                            build_renderer=self._renderer,
                            source_aware_contract_resolver=(
                                self._source_aware_contract_resolver
                            ),
                        )

    def test_mirror_rejects_false_forward_ancestry_claim(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        _run("git", "checkout", "-q", "-b", "sibling", fixture.base_commit, cwd=fixture.source)
        (fixture.source / "state.txt").write_text("sibling\n", encoding="utf-8")
        _run("git", "add", "state.txt", cwd=fixture.source)
        sibling_env = dict(os.environ)
        sibling_env.update(
            {
                "GIT_AUTHOR_DATE": "1700000200 +0000",
                "GIT_COMMITTER_DATE": "1700000200 +0000",
            }
        )
        _run("git", "commit", "-q", "-m", "sibling", cwd=fixture.source, env=sibling_env)
        sibling_commit = _run("git", "rev-parse", "HEAD", cwd=fixture.source)
        sibling_tree = _run("git", "rev-parse", "HEAD^{tree}", cwd=fixture.source)
        _run(
            "git",
            f"--git-dir={fixture.mirror}",
            "fetch",
            "-q",
            "--no-tags",
            str(fixture.source),
            sibling_commit,
            cwd=self.root,
        )
        fixture.catalog["cores"][fixture.core_id]["source"].update(
            {"commit": sibling_commit, "tree": sibling_tree}
        )
        catalog_raw = _write_json(fixture.catalog_path, fixture.catalog)
        entry = fixture.snapshot["sources"][fixture.core_id]
        entry.update({"catalog_commit": sibling_commit, "catalog_tree": sibling_tree})
        fixture.snapshot["catalog"]["file_sha256"] = hashlib.sha256(
            catalog_raw
        ).hexdigest()
        fixture.write_snapshot()
        with self.assertRaisesRegex(PipelineError, "mirror command failed"):
            self._prepare(fixture)

    def test_overlay_preimage_is_checked_against_candidate_tree(self) -> None:
        fixture = SourceCandidateFixture(self.root, overlay_mismatch=True)
        with self.assertRaisesRegex(PipelineError, "overlay preimage changed"):
            self._prepare(fixture)

    def test_snapshot_bytes_and_frozen_ref_are_fail_closed(self) -> None:
        fixture = SourceCandidateFixture(self.root)
        compact = json.dumps(fixture.snapshot, sort_keys=True).encode()
        fixture.snapshot_path.write_bytes(compact)
        with self.assertRaisesRegex(PipelineError, "non-canonical"):
            self._prepare(fixture)

        fixture.write_snapshot()
        fixture.snapshot["sources"][fixture.core_id]["frozen_local_ref"] = (
            "refs/spruce-edge-refs/" + "9" * 64
        )
        fixture.write_snapshot()
        with self.assertRaisesRegex(PipelineError, "frozen ref is non-canonical"):
            self._prepare(fixture)

    def test_real_easyrpg_promoted_identity_is_generic_and_fail_closed(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        candidates = sorted(
            (
                repository_root
                / ".local-e2e"
                / "source-candidates"
            ).glob("*/easyrpg/*/core-builds.json")
        )
        if not candidates:
            self.skipTest("real EasyRPG source-candidate evidence is unavailable")
        candidate = json.loads(candidates[-1].read_text(encoding="utf-8"))

        def validate(value: dict):
            return source_candidate.validate_promoted_source_candidate_contract(
                repository_root=repository_root,
                canonical_catalog_path=(
                    repository_root / "manifests" / "core-builds.json"
                ),
                candidate_catalog=value,
                catalog_validator=lambda _catalog: None,
                source_aware_contract_resolver=lambda _core: False,
            )

        self.assertIsNone(validate(candidate))

        for label, mutate in (
            (
                "resolver",
                lambda value: value["resolver"].update(
                    {"libretro_super_commit": "0" * 40}
                ),
            ),
            (
                "policy",
                lambda value: value["policy"].update(
                    {"publication": "enabled-forged"}
                ),
            ),
        ):
            with self.subTest(label=label):
                forged = copy.deepcopy(candidate)
                mutate(forged)
                with self.assertRaisesRegex(
                    PipelineError,
                    "non-core catalog bytes differ",
                ):
                    validate(forged)

        bad_id = copy.deepcopy(candidate)
        bad_id["source_candidate"]["candidate_id"] = "0" * 64
        with self.assertRaisesRegex(PipelineError, "provenance identity"):
            validate(bad_id)

        bad_execution = copy.deepcopy(candidate)
        provenance = bad_execution["source_candidate"]
        provenance["execution"]["core_spec_sha256"] = "0" * 64
        provenance["candidate_id"] = source_candidate._content_sha256(
            {
                key: value
                for key, value in provenance.items()
                if key != "candidate_id"
            }
        )
        with self.assertRaisesRegex(PipelineError, "provenance identity"):
            validate(bad_execution)


if __name__ == "__main__":
    unittest.main()
