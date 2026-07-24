"""Adversarial lexical-path tests for individual compatibility evidence."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
from typing import Iterator
import unittest
import zipfile

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.records import compatibility


CORE_ID = "handy"
ARCHITECTURE = "arm64"
SOURCE_COMMIT = "a" * 40
E2E_CONTENT_SHA256 = "b" * 64
ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def _compatibility_document() -> dict:
    document = {
        "$schema": compatibility.SCHEMA_REFERENCE,
        "schema_version": 1,
        "core_id": CORE_ID,
        "publication": "disabled",
        "evidence_availability": "workspace-local-ignored",
        "golden_source": "pins/core-sets/handy-aaaaaaaaaaaa-bbbbbbbbbbbb.json",
        "source_commit": SOURCE_COMMIT,
        "e2e_run": ".local-e2e/runs/selected/e2e-record.json",
        "selected_e2e_content_sha256": "c" * 64,
        "reproduction_run": ".local-e2e/runs/reproduction/e2e-record.json",
        "reproduction_e2e_content_sha256": "d" * 64,
        "package_state": "reproducible",
        "package_sha256": "e" * 64,
        "caveats": ["fixture"],
        "targets": {
            ARCHITECTURE: {
                "state": "local_static_build_golden",
                "validation_scope": "static-build-only",
                "runtime_validation": "needs-target-runtime",
                "artifact_sha256": "f" * 64,
                "elf": "ELF64/AArch64",
                "needed": ["libc.so.6"],
                "version_requirements": ["GLIBC_2.17"],
            }
        },
    }
    document["content_sha256"] = (
        compatibility.core_compatibility_content_sha256(document)
    )
    return document


@contextmanager
def compatibility_evidence() -> Iterator[SimpleNamespace]:
    """Create the smallest fully valid compatibility E2E evidence tree."""

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runs_root = root / ".local-e2e" / "runs"
        run_root = runs_root / "run-one"
        build_root = run_root / CORE_ID / ARCHITECTURE
        build_root.mkdir(parents=True)

        log_path = build_root / "build.log"
        log_path.write_text("compile proof\n", encoding="utf-8")
        artifact_path = build_root / f"{CORE_ID}_libretro.so"
        artifact_path.write_bytes(b"artifact bytes")
        metadata_path = build_root / f"{CORE_ID}_libretro.info"
        metadata_path.write_bytes(b"metadata bytes")

        artifact = {
            "path": artifact_path.name,
            "status": "valid",
            "sha256": _sha256(artifact_path),
            "size": artifact_path.stat().st_size,
            "elf": {"class": "ELF64", "machine": "AArch64"},
            "needed": ["libc.so.6"],
            "version_requirements": ["GLIBC_2.17"],
        }
        record = {
            "core_id": CORE_ID,
            "architecture": ARCHITECTURE,
            "result": "passed",
            "build_exit_code": 0,
            "local_only": True,
            "publication": "disabled",
            "source": {
                "commit": SOURCE_COMMIT,
                "resolved_commit": SOURCE_COMMIT,
            },
            "build": {
                "log": log_path.name,
                "log_sha256": _sha256(log_path),
            },
            "artifact": artifact,
            "metadata": {
                "path": metadata_path.name,
                "status": "valid",
                "sha256": _sha256(metadata_path),
                "size": metadata_path.stat().st_size,
            },
        }
        record_path = build_root / "build-record.json"
        _write_json(record_path, record)

        package_path = run_root / f"{CORE_ID}_libretro.zip"
        artifact_member = f"lib64/{artifact_path.name}"
        manifest = {
            "core_id": CORE_ID,
            "local_only": True,
            "publication": "disabled",
            "metadata": {
                "path": metadata_path.name,
                "sha256": _sha256(metadata_path),
            },
            "artifacts": {
                ARCHITECTURE: {
                    "path": artifact_member,
                    "sha256": _sha256(artifact_path),
                    "source_commit": SOURCE_COMMIT,
                }
            },
        }
        with zipfile.ZipFile(package_path, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.write(metadata_path, metadata_path.name)
            archive.write(artifact_path, artifact_member)

        record_relative = record_path.relative_to(root).as_posix()
        evidence = {
            "schema_version": 2,
            "runner": {},
            "run_id": run_root.name,
            "result": "passed",
            "local_only": True,
            "publication": "disabled",
            "content_sha256": E2E_CONTENT_SHA256,
            "builds": [
                {
                    "core_id": CORE_ID,
                    "architecture": ARCHITECTURE,
                    "result": "passed",
                    "record": record_relative,
                    "record_sha256": _sha256(record_path),
                }
            ],
            "packages": [
                {
                    "core_id": CORE_ID,
                    "result": "packaged",
                    "path": package_path.name,
                    "sha256": _sha256(package_path),
                    "size": package_path.stat().st_size,
                }
            ],
        }
        e2e_path = run_root / "e2e-record.json"
        _write_json(e2e_path, evidence)
        yield SimpleNamespace(
            root=root,
            runs_root=runs_root,
            run_root=run_root,
            e2e_path=e2e_path,
            record_path=record_path,
            log_path=log_path,
            artifact_path=artifact_path,
            metadata_path=metadata_path,
            package_path=package_path,
            artifact=artifact,
        )


def _validate_e2e(fixture: SimpleNamespace, e2e_path: Path | None = None) -> dict:
    def validate_artifact(path: Path, architecture: str) -> dict:
        if architecture != ARCHITECTURE:
            raise AssertionError(architecture)
        return {
            **fixture.artifact,
            "sha256": _sha256(path),
            "size": path.stat().st_size,
        }

    return compatibility.validate_core_e2e_run(
        e2e_path or fixture.e2e_path,
        CORE_ID,
        repository_root=fixture.root,
        runs_root=fixture.runs_root,
        expected_targets={ARCHITECTURE},
        package_directories={ARCHITECTURE: "lib64"},
        expected_build_records={ARCHITECTURE: {}},
        artifact_validator=validate_artifact,
        build_record_validator=lambda *_: None,
        content_hasher=lambda _: E2E_CONTENT_SHA256,
        runner_validator=lambda _: True,
    )


def _replace_with_in_root_symlink(path: Path, *, preserve_name: bool) -> None:
    if preserve_name:
        target_directory = path.parent / "real"
        target_directory.mkdir(exist_ok=True)
        target = target_directory / path.name
    else:
        target = path.with_name(f"{path.stem}.real{path.suffix}")
    path.rename(target)
    path.symlink_to(target.relative_to(path.parent))


class CompatibilityPathSafetyTests(unittest.TestCase):
    def test_valid_synthetic_evidence_is_accepted(self) -> None:
        with compatibility_evidence() as fixture:
            report = _validate_e2e(fixture)
        self.assertEqual("run-one", report["run_id"])

    def test_each_evidence_file_rejects_a_symlink_to_in_root_bytes(self) -> None:
        cases = {
            "build record": ("record_path", False),
            "build log": ("log_path", True),
            "artifact": ("artifact_path", True),
            "metadata": ("metadata_path", True),
            "package": ("package_path", True),
        }
        for label, (attribute, preserve_name) in cases.items():
            with self.subTest(evidence=label), compatibility_evidence() as fixture:
                _replace_with_in_root_symlink(
                    getattr(fixture, attribute),
                    preserve_name=preserve_name,
                )
                with self.assertRaisesRegex(PipelineError, "symlink"):
                    _validate_e2e(fixture)

    def test_e2e_parent_symlink_resolving_inside_runs_root_is_rejected(self) -> None:
        with compatibility_evidence() as fixture:
            alias = fixture.runs_root / "run-alias"
            alias.symlink_to(fixture.run_root.name, target_is_directory=True)
            with self.assertRaisesRegex(PipelineError, "symlink"):
                _validate_e2e(fixture, alias / "e2e-record.json")

    def test_canonical_run_references_reject_reserved_name_case_insensitively(
        self,
    ) -> None:
        mutations = {
            "e2e_run": ".local-e2e/runs/selected-TrAnChE/e2e-record.json",
            "reproduction_run": (
                ".local-e2e/runs/reproduction-TRANCHE/e2e-record.json"
            ),
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                document = _compatibility_document()
                document[field] = value
                document["content_sha256"] = (
                    compatibility.core_compatibility_content_sha256(document)
                )
                report = compatibility.validate_core_compatibility_document(
                    document,
                    repository_root=ROOT,
                    verify_pin=False,
                )
                self.assertEqual("invalid", report["status"])
                self.assertIn(
                    f"core compatibility {field} uses reserved legacy tranche name",
                    report["errors"],
                )

    def test_deep_e2e_run_id_rejects_reserved_name_case_insensitively(
        self,
    ) -> None:
        with compatibility_evidence() as fixture:
            evidence = json.loads(fixture.e2e_path.read_text(encoding="utf-8"))
            evidence["run_id"] = "run-TrAnChE-one"
            _write_json(fixture.e2e_path, evidence)
            with self.assertRaisesRegex(
                PipelineError,
                "E2E run_id uses reserved legacy tranche name",
            ):
                _validate_e2e(fixture)

    def test_schema_rejects_reserved_canonical_run_names(self) -> None:
        schema = json.loads(
            (ROOT / "manifests" / "core-compatibility.schema.json").read_text(
                encoding="utf-8"
            )
        )
        for field in ("e2e_run", "reproduction_run"):
            with self.subTest(field=field):
                pattern = re.compile(schema["properties"][field]["pattern"])
                self.assertIsNotNone(
                    pattern.fullmatch(
                        ".local-e2e/runs/individual-core/e2e-record.json"
                    )
                )
                self.assertIsNone(
                    pattern.fullmatch(
                        ".local-e2e/runs/individual-TrAnChE-core/e2e-record.json"
                    )
                )

    def test_build_record_parent_symlink_resolving_inside_run_is_rejected(
        self,
    ) -> None:
        with compatibility_evidence() as fixture:
            alias = fixture.run_root / "core-alias"
            alias.symlink_to(CORE_ID, target_is_directory=True)
            evidence = json.loads(fixture.e2e_path.read_text(encoding="utf-8"))
            aliased_record = alias / ARCHITECTURE / "build-record.json"
            evidence["builds"][0]["record"] = aliased_record.relative_to(
                fixture.root
            ).as_posix()
            _write_json(fixture.e2e_path, evidence)
            with self.assertRaisesRegex(PipelineError, "symlink"):
                _validate_e2e(fixture)

    def test_pin_parent_symlink_resolving_inside_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual_pins = root / "actual-pins" / "core-sets"
            actual_pins.mkdir(parents=True)
            pin_name = "handy-aaaaaaaaaaaa-bbbbbbbbbbbb.json"
            _write_json(actual_pins / pin_name, {})
            (root / "pins").symlink_to(
                actual_pins.parent,
                target_is_directory=True,
            )
            document = _compatibility_document()
            document["golden_source"] = f"pins/core-sets/{pin_name}"
            document["content_sha256"] = (
                compatibility.core_compatibility_content_sha256(document)
            )
            report = compatibility.validate_core_compatibility_document(
                document,
                repository_root=root,
                pin_validator=lambda *_args, **_kwargs: {"errors": []},
            )
        self.assertIn(
            "individual core pin path must not traverse a symlink",
            report["errors"],
        )


if __name__ == "__main__":
    unittest.main()
