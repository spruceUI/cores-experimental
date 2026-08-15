#!/usr/bin/env python3

from __future__ import annotations

import copy
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts.core_pipeline_lib.chipsets import chipset_tunings_content_sha256


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "core_pipeline_tuned_bootstrap",
    ROOT / "scripts" / "core_pipeline.py",
)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)

SELECTED_RUNNER = {
    "profile": "github-actions",
    "mode": "simulated",
    "backend": "local-docker",
    "local_only": True,
    "publication": "disabled",
}
REPRODUCTION_RUNNER = {
    "profile": "local",
    "mode": "native",
    "backend": "local-docker",
    "local_only": True,
    "publication": "disabled",
}


def _hardened_runner(*, selected: bool) -> dict:
    registry_sha = "1" * 64
    schema_sha = "2" * 64
    telemetry_sha = ("3" if selected else "4") * 64
    return {
        "schema_version": 2,
        **(SELECTED_RUNNER if selected else REPRODUCTION_RUNNER),
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


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


class TunedBootstrapTests(unittest.TestCase):
    def test_tuned_e2e_rejects_non_utf8_json_encodings(self) -> None:
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        local_root = pipeline.ROOT / ".local-e2e"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            e2e_path = Path(directory) / "e2e-record.json"
            for encoding in ("utf-16", "utf-32"):
                with self.subTest(encoding=encoding):
                    e2e_path.write_bytes("{}".encode(encoding))
                    with self.assertRaisesRegex(
                        pipeline.PipelineError,
                        "cannot load tuning candidate E2E",
                    ):
                        pipeline.validate_tuned_e2e_evidence(
                            e2e_path,
                            pipeline.DEFAULT_CATALOG,
                            catalog,
                        )

    def test_tuned_recipe_snapshot_binds_exact_registry_bytes_and_profile(self) -> None:
        tuning = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        pin_index = pipeline.load_authoritative_core_pin_index()
        pin_entry = next(
            entry for entry in pin_index.values() if entry["core_id"] == "frodo"
        )
        pin = pipeline.load_json(pipeline.ROOT / pin_entry["path"])
        record = copy.deepcopy(
            pin["cores"]["frodo"]["selection"]["targets"]["arm64"][
                "golden_record"
            ]
        )
        catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
        record["recipe"] = pipeline.recipe_record(
            pipeline.DEFAULT_CATALOG, "frodo", catalog["cores"]["frodo"]
        )
        record["tuning_candidate"] = tuning
        record["recipe"]["chipset_tuning"] = (
            pipeline.tuning_candidate_recipe_identity(tuning)
        )
        snapshot_bytes = pipeline.recipe_snapshot(record)
        with tempfile.TemporaryDirectory() as temporary:
            snapshot_path = Path(temporary) / "recipe.json"
            snapshot_path.write_bytes(snapshot_bytes)
            self.assertEqual(
                [], pipeline.verify_recipe_snapshot(snapshot_path, record, "tuned")
            )
            self.assertEqual(
                [],
                pipeline.verify_historical_recipe_snapshot(
                    snapshot_path, record, "tuned"
                ),
            )

            snapshot = json.loads(snapshot_bytes)
            registry_path = tuning["registry"]["path"]
            registry = json.loads(snapshot["files"][registry_path]["text"])
            registry["profiles"]["a523-cortex-a55-v1"]["properties"][
                "cpu_target"
            ] = "cortex-a53"
            registry["content_sha256"] = (
                chipset_tunings_content_sha256(registry)
            )
            tampered_text = json.dumps(registry, indent=2, sort_keys=True) + "\n"
            snapshot["files"][registry_path] = {
                "sha256": pipeline.sha256_bytes(tampered_text.encode()),
                "text": tampered_text,
            }
            snapshot_path.write_bytes(_json_bytes(snapshot))
            self.assertTrue(
                pipeline.verify_recipe_snapshot(snapshot_path, record, "tuned")
            )
            self.assertTrue(
                pipeline.verify_historical_recipe_snapshot(
                    snapshot_path, record, "tuned"
                )
            )

    def test_candidate_equivalence_allows_logs_but_rejects_semantic_or_output_drift(
        self,
    ) -> None:
        tuning = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        record = {
            "schema_version": 2,
            "local_only": True,
            "publication": "disabled",
            "core_id": "alpha",
            "architecture": "arm64",
            "result": "passed",
            "build_exit_code": 0,
            "source": {"resolved_commit": "1" * 40},
            "recipe": {
                "chipset_tuning": pipeline.tuning_candidate_recipe_identity(tuning)
            },
            "toolchain": {"resolved_image_id": "sha256:" + "2" * 64},
            "build": {"driver": "libretro-super", "log_sha256": "3" * 64},
            "artifact": {"sha256": "4" * 64, "size": 10},
            "metadata": {"sha256": "5" * 64, "size": 11},
            "tuning_candidate": tuning,
        }
        selected = {
            "e2e": {"run_id": "selected", "runner": SELECTED_RUNNER},
            "e2e_path": Path("selected/e2e-record.json"),
            "record_path": Path("selected/build-record.json"),
            "log_path": Path("selected/build.log"),
            "selection": tuning,
            "record": record,
            "package_record": {
                "path": "alpha_libretro.zip",
                "sha256": "6" * 64,
                "size": 12,
            },
        }
        reproduction = copy.deepcopy(selected)
        reproduction["e2e"]["run_id"] = "reproduction"
        reproduction["e2e"]["runner"] = REPRODUCTION_RUNNER
        reproduction["e2e_path"] = Path("reproduction/e2e-record.json")
        reproduction["record_path"] = Path("reproduction/build-record.json")
        reproduction["log_path"] = Path("reproduction/build.log")
        reproduction["record"]["build"]["log_sha256"] = "7" * 64
        self.assertEqual(
            pipeline.tuned_candidate_output_identity(selected),
            pipeline.require_tuned_candidate_equivalence(selected, reproduction),
        )

        mutations = (
            ("artifact", lambda item: item["record"]["artifact"].update(sha256="8" * 64)),
            ("metadata", lambda item: item["record"]["metadata"].update(sha256="8" * 64)),
            ("package", lambda item: item["package_record"].update(sha256="8" * 64)),
            (
                "source",
                lambda item: item["record"]["source"].update(
                    resolved_commit="9" * 40
                ),
            ),
            (
                "ABI",
                lambda item: item["record"].update(architecture="armhf"),
            ),
            (
                "registry/profile",
                lambda item: item["selection"]["registry"].update(
                    content_sha256="a" * 64
                ),
            ),
        )
        for label, mutate in mutations:
            changed = copy.deepcopy(reproduction)
            mutate(changed)
            with self.subTest(label=label), self.assertRaises(
                pipeline.PipelineError
            ):
                pipeline.require_tuned_candidate_equivalence(selected, changed)

    def test_dual_e2e_promotion_creates_semantic_golden_and_pin(self) -> None:
        tuning = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        artifact_bytes = b"promoted artifact"
        metadata_bytes = b"promoted metadata"
        artifact_sha = pipeline.sha256_bytes(artifact_bytes)
        metadata_sha = pipeline.sha256_bytes(metadata_bytes)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            nightlies = root / ".local-e2e" / "nightlies"
            store_root = root / ".local-e2e" / "store"
            pin_root = root / "pins" / "core-sets"
            selected_root = runs / "selected"
            reproduction_root = runs / "reproduction"
            for directory in (selected_root, reproduction_root):
                directory.mkdir(parents=True)
            source_path = nightlies / "alpha-candidate-tuned" / "golden.json"
            source_path.parent.mkdir(parents=True)
            source_document = {
                "schema_version": 2,
                "core_id": "alpha",
                "pin_id": "alpha-candidate-tuned",
                "created_at": "2026-08-09T00:00:00+00:00",
                "baseline": {},
                "cores": {"alpha": {}},
                "build_goldens": {"alpha": {}},
            }
            source_path.write_bytes(_json_bytes(source_document))

            artifact_path = selected_root / "alpha_libretro.so"
            metadata_path = selected_root / "alpha_libretro.info"
            package_path = selected_root / "alpha_libretro.zip"
            artifact_path.write_bytes(artifact_bytes)
            metadata_path.write_bytes(metadata_bytes)
            source = {
                "url": "https://example.invalid/alpha.git",
                "requested_ref": "1" * 40,
                "commit": "1" * 40,
                "resolved_commit": "1" * 40,
                "tree": "2" * 40,
                "resolved_url": "https://example.invalid/alpha.git",
                "submodules": [],
            }
            image_id = "sha256:" + "3" * 64
            manifest = {
                "schema_version": 1,
                "local_only": True,
                "publication": "disabled",
                "core_id": "alpha",
                "artifacts": {
                    "arm64": {
                        "path": "cores64/alpha_libretro.so",
                        "sha256": artifact_sha,
                        "source_commit": source["commit"],
                        "toolchain_image_id": image_id,
                    }
                },
                "metadata": {
                    "path": "alpha_libretro.info",
                    "sha256": metadata_sha,
                },
                "tuning_candidate": tuning,
            }
            with zipfile.ZipFile(package_path, "w") as archive:
                pipeline.add_zip_entry(
                    archive, "cores64/alpha_libretro.so", artifact_bytes
                )
                pipeline.add_zip_entry(
                    archive, "alpha_libretro.info", metadata_bytes
                )
                pipeline.add_zip_entry(
                    archive, "manifest.json", _json_bytes(manifest)
                )
            package_bytes = package_path.read_bytes()
            package_sha = pipeline.sha256_bytes(package_bytes)
            profile = tuning["profile"]
            tuning_marker = "CORE_PIPELINE_CHIPSET_TUNING|" + json.dumps(
                {
                    "profile_id": profile["profile_id"],
                    "content_sha256": profile["content_sha256"],
                    "compiler_argument_mapping_version": profile[
                        "compiler_argument_mapping_version"
                    ],
                    "compiler_arguments": profile["compiler_arguments"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            compile_line = "aarch64-linux-gnu-gcc -mcpu=cortex-a55 -c core.c"
            base_record = {
                "schema_version": 2,
                "local_only": True,
                "publication": "disabled",
                "started_at": "2026-08-09T00:00:01+00:00",
                "finished_at": "2026-08-09T00:00:02+00:00",
                "core_id": "alpha",
                "architecture": "arm64",
                "result": "passed",
                "build_exit_code": 0,
                "source": source,
                "recipe": {
                    "chipset_tuning": pipeline.tuning_candidate_recipe_identity(
                        tuning
                    ),
                    "host_execution": {
                        "resource_class_id": "host-equivalent-v1",
                        "jobs": 8,
                    },
                },
                "toolchain": {
                    "image": "example.invalid/toolchain:1",
                    "image_id": image_id,
                    "resolved_image_id": image_id,
                    "libretro_super_commit": source["commit"],
                    "resolver_digests": {
                        "libretro_super_commit": source["commit"]
                    },
                },
                "build": {
                    "driver": "libretro-super",
                    "environment": "sanitized-v1",
                    "compile_definitions": [],
                    "log": "build.log",
                    "log_sha256": "",
                },
                "artifact": {
                    "path": "alpha_libretro.so",
                    "status": "valid",
                    "sha256": artifact_sha,
                    "size": len(artifact_bytes),
                },
                "metadata": {
                    "path": "alpha_libretro.info",
                    "status": "valid",
                    "sha256": metadata_sha,
                    "size": len(metadata_bytes),
                },
                "tuning_candidate": tuning,
            }

            def bundle(directory: Path, run_id: str, log: bytes) -> dict:
                log_path = directory / "build.log"
                log_path.write_bytes(log)
                record = copy.deepcopy(base_record)
                record["started_at"] = f"2026-08-09T00:00:0{run_id[-1]}+00:00"
                record["build"]["log_sha256"] = pipeline.sha256_bytes(log)
                record_path = directory / "build-record.json"
                record_path.write_bytes(_json_bytes(record))
                package_record = {
                    "core_id": "alpha",
                    "result": "packaged",
                    "path": "alpha_libretro.zip",
                    "sha256": package_sha,
                    "size": len(package_bytes),
                    "tuning_candidate": tuning,
                }
                e2e = {
                    "schema_version": 2,
                    "run_id": run_id,
                    "local_only": True,
                    "publication": "disabled",
                    "runner": _hardened_runner(selected=run_id == "run1"),
                    "result": "passed",
                    "workflow_audit": {},
                    "builds": [
                        {
                            "core_id": "alpha",
                            "architecture": "arm64",
                            "result": "passed",
                            "record": str(record_path.relative_to(root)),
                            "record_sha256": pipeline.sha256_file(record_path),
                        }
                    ],
                    "packages": [package_record],
                    "tuning_candidate": tuning,
                }
                e2e["content_sha256"] = pipeline.e2e_content_sha256(e2e)
                e2e_path = directory / "e2e-record.json"
                e2e_path.write_bytes(_json_bytes(e2e))
                return {
                    "e2e": e2e,
                    "e2e_path": e2e_path,
                    "e2e_file_sha256": pipeline.sha256_file(e2e_path),
                    "selection": tuning,
                    "core_id": "alpha",
                    "architecture": "arm64",
                    "record": record,
                    "record_path": record_path,
                    "record_sha256": pipeline.sha256_file(record_path),
                    "artifact_path": artifact_path,
                    "metadata_path": metadata_path,
                    "log_path": log_path,
                    "package_path": package_path,
                    "package_record": package_record,
                }

            selected = bundle(
                selected_root,
                "run1",
                (tuning_marker + "\n" + compile_line + "\n").encode(),
            )
            reproduced = bundle(
                reproduction_root,
                "run2",
                (
                    tuning_marker
                    + "\nindependent diagnostic line\n"
                    + compile_line
                    + "\n"
                ).encode(),
            )
            catalog = {"cores": {"alpha": {}}}

            def compose_pin(**kwargs):
                golden = pipeline.load_json(kwargs["source_paths"][0])
                selection = pipeline.complete_core_bundle(golden, "alpha")
                assert selection is not None
                pin = {
                    "pin_id": kwargs["pin_id"],
                    "scope": ["alpha"],
                    "parent": None,
                    "sources": [
                        {
                            "path": str(kwargs["source_paths"][0].relative_to(root))
                        }
                    ],
                    "cores": {
                        "alpha": {
                            "decision": "select_source",
                            "source_index": 0,
                            "selection": selection,
                        }
                    },
                    "content_sha256": "f" * 64,
                }
                kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_path"].write_bytes(_json_bytes(pin))
                return pin

            tuning_path = root / "manifests" / "chipset-tunings.json"
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_STORE", store_root),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pin_root),
                mock.patch.object(pipeline, "DEFAULT_CHIPSET_TUNINGS", tuning_path),
                mock.patch.object(pipeline, "load_catalog", return_value=catalog),
                mock.patch.object(
                    pipeline,
                    "resolve_tuning_candidate_selection",
                    return_value=tuning,
                ),
                mock.patch.object(
                    pipeline,
                    "validate_tuned_e2e_evidence",
                    side_effect=[selected, reproduced],
                ),
                mock.patch.object(
                    pipeline, "require_source_commits_eligible", return_value=None
                ),
                mock.patch.object(
                    pipeline,
                    "validate_golden_document",
                    return_value={"status": "valid", "errors": []},
                ),
                mock.patch.object(pipeline, "verify_local_store", return_value=[]),
                mock.patch.object(pipeline, "recipe_snapshot", return_value=b"{}\n"),
                mock.patch.object(
                    pipeline,
                    "validate_artifact",
                    return_value={"status": "valid", "sha256": artifact_sha},
                ),
                mock.patch.object(
                    pipeline, "_verify_recipe_snapshot", return_value=[]
                ),
                mock.patch.object(
                    pipeline,
                    "registered_core_log_contract_proves",
                    return_value=True,
                ),
                mock.patch.object(pipeline, "manifest_lock", side_effect=lambda _p: nullcontext()),
                mock.patch.object(pipeline, "compose_pin_set", side_effect=compose_pin),
            ):
                mixed_reproduction = copy.deepcopy(reproduced)
                mixed_reproduction["e2e"]["runner"] = pipeline.base_runner_evidence(
                    mixed_reproduction["e2e"]["runner"]
                )
                with mock.patch.object(
                    pipeline,
                    "validate_tuned_e2e_evidence",
                    side_effect=[selected, mixed_reproduction],
                ), self.assertRaisesRegex(
                    pipeline.PipelineError,
                    "cannot mix hardened and legacy",
                ):
                    pipeline.promote_tuned_variant(
                        core_id="alpha",
                        profile_id=tuning["profile"]["profile_id"],
                        source_golden_path=source_path,
                        selected_e2e_path=selected["e2e_path"],
                        reproduction_e2e_path=reproduced["e2e_path"],
                        store_root=store_root,
                    )
                result = pipeline.promote_tuned_variant(
                    core_id="alpha",
                    profile_id=tuning["profile"]["profile_id"],
                    source_golden_path=source_path,
                    selected_e2e_path=selected["e2e_path"],
                    reproduction_e2e_path=reproduced["e2e_path"],
                    store_root=store_root,
                )
                self.assertEqual("created", result["status"])
                promoted_path = root / result["golden"]
                self.assertTrue(promoted_path.is_file())
                self.assertTrue((root / result["pin"]).is_file())
                promoted = pipeline.load_json(promoted_path)
                selection = pipeline.complete_core_bundle(promoted, "alpha")
                assert selection is not None
                host_reproduction = selection["host_reproduction"]
                self.assertEqual(
                    host_reproduction["content_sha256"],
                    result["host_reproduction_content_sha256"],
                )
                self.assertEqual(
                    [], pipeline.verify_local_store(promoted)
                )

    def test_two_different_valid_logs_and_exact_outputs_verify_from_store(self) -> None:
        tuning = pipeline.resolve_tuning_candidate_selection(
            "a523-cortex-a55-v1"
        )
        profile = tuning["profile"]
        marker = "CORE_PIPELINE_CHIPSET_TUNING|" + json.dumps(
            {
                "profile_id": profile["profile_id"],
                "content_sha256": profile["content_sha256"],
                "compiler_argument_mapping_version": profile[
                    "compiler_argument_mapping_version"
                ],
                "compiler_arguments": profile["compiler_arguments"],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        compile_line = "aarch64-linux-gnu-gcc -mcpu=cortex-a55 -c core.c"
        artifact_bytes = b"identical tuned artifact"
        metadata_bytes = b"identical metadata"
        artifact_sha = pipeline.sha256_bytes(artifact_bytes)
        metadata_sha = pipeline.sha256_bytes(metadata_bytes)
        source_commit = "1" * 40
        source_tree = "2" * 40
        image_id = "sha256:" + "3" * 64

        with tempfile.TemporaryDirectory() as temporary:
            repository_root = Path(temporary)
            store_root = repository_root / ".local-e2e" / "store"

            def store(namespace: str, content: bytes) -> dict[str, str]:
                digest = pipeline.sha256_bytes(content)
                path = store_root / namespace / "sha256" / digest[:2] / digest
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                return {
                    "path": str(path.relative_to(repository_root)),
                    "sha256": digest,
                }

            artifact_store = store("artifacts", artifact_bytes)
            metadata_store = store("metadata", metadata_bytes)
            recipe_store = store("recipes", b"{}\n")

            manifest = {
                "schema_version": 1,
                "local_only": True,
                "publication": "disabled",
                "core_id": "alpha",
                "artifacts": {
                    "arm64": {
                        "path": "cores64/alpha_libretro.so",
                        "sha256": artifact_sha,
                        "source_commit": source_commit,
                        "toolchain_image_id": image_id,
                    }
                },
                "metadata": {
                    "path": "alpha_libretro.info",
                    "sha256": metadata_sha,
                },
                "tuning_candidate": tuning,
            }
            package_path = repository_root / "alpha_libretro.zip"
            with zipfile.ZipFile(package_path, "w") as archive:
                pipeline.add_zip_entry(
                    archive, "cores64/alpha_libretro.so", artifact_bytes
                )
                pipeline.add_zip_entry(
                    archive, "alpha_libretro.info", metadata_bytes
                )
                pipeline.add_zip_entry(
                    archive, "manifest.json", _json_bytes(manifest)
                )
            package_bytes = package_path.read_bytes()
            package_store = store("packages", package_bytes)
            package_size = len(package_bytes)

            base_record = {
                "schema_version": 2,
                "local_only": True,
                "publication": "disabled",
                "started_at": "2026-08-09T00:00:00+00:00",
                "finished_at": "2026-08-09T00:00:01+00:00",
                "core_id": "alpha",
                "architecture": "arm64",
                "result": "passed",
                "build_exit_code": 0,
                "source": {
                    "url": "https://example.invalid/alpha.git",
                    "requested_ref": source_commit,
                    "commit": source_commit,
                    "resolved_commit": source_commit,
                    "tree": source_tree,
                    "resolved_url": "https://example.invalid/alpha.git",
                    "submodules": [],
                },
                "recipe": {
                    "chipset_tuning": pipeline.tuning_candidate_recipe_identity(
                        tuning
                    )
                },
                "toolchain": {
                    "image": "example.invalid/toolchain:1",
                    "image_id": image_id,
                    "resolved_image_id": image_id,
                    "libretro_super_commit": source_commit,
                    "resolver_digests": {
                        "libretro_super_commit": source_commit
                    },
                },
                "build": {
                    "driver": "libretro-super",
                    "environment": "sanitized-v1",
                    "compile_definitions": [],
                    "log": "build.log",
                    "log_sha256": "",
                },
                "artifact": {
                    "path": "alpha_libretro.so",
                    "status": "valid",
                    "sha256": artifact_sha,
                    "size": len(artifact_bytes),
                },
                "metadata": {
                    "path": "alpha_libretro.info",
                    "status": "valid",
                    "sha256": metadata_sha,
                    "size": len(metadata_bytes),
                },
                "tuning_candidate": tuning,
            }

            def side(run_id: str, extra_log_line: str) -> tuple[dict, dict]:
                log_bytes = (marker + "\n" + extra_log_line + compile_line + "\n").encode()
                log_store = store("logs", log_bytes)
                record = copy.deepcopy(base_record)
                record["started_at"] = f"2026-08-09T00:00:0{run_id[-1]}+00:00"
                record["finished_at"] = f"2026-08-09T00:00:1{run_id[-1]}+00:00"
                record["build"]["log_sha256"] = log_store["sha256"]
                record_store = store("build-records", _json_bytes(record))
                package_record = {
                    "core_id": "alpha",
                    "result": "packaged",
                    "path": "alpha_libretro.zip",
                    "sha256": package_store["sha256"],
                    "size": package_size,
                    "tuning_candidate": tuning,
                }
                e2e = {
                    "schema_version": 2,
                    "run_id": run_id,
                    "local_only": True,
                    "publication": "disabled",
                    "runner": (
                        SELECTED_RUNNER
                        if run_id == "candidate1"
                        else REPRODUCTION_RUNNER
                    ),
                    "result": "passed",
                    "workflow_audit": {},
                    "builds": [
                        {
                            "core_id": "alpha",
                            "architecture": "arm64",
                            "result": "passed",
                            "record": f"ignored/{run_id}/build-record.json",
                            "record_sha256": record_store["sha256"],
                        }
                    ],
                    "packages": [package_record],
                    "tuning_candidate": tuning,
                }
                e2e["content_sha256"] = pipeline.e2e_content_sha256(e2e)
                e2e_store = store("e2e", _json_bytes(e2e))
                proof = {
                    "run_id": run_id,
                    "content_sha256": e2e["content_sha256"],
                    "e2e_record": e2e_store,
                    "build_record": record_store,
                    "build_log": log_store,
                    "recipe_snapshot": recipe_store,
                }
                return record, proof

            selected_record, selected = side("candidate1", "")
            reproduction_record, reproduction = side(
                "candidate2", "independent diagnostic line\n"
            )
            outputs = {
                "artifact": {
                    "sha256": artifact_sha,
                    "size": len(artifact_bytes),
                },
                "metadata": {
                    "sha256": metadata_sha,
                    "size": len(metadata_bytes),
                },
                "package": {
                    "name": "alpha_libretro.zip",
                    "sha256": package_store["sha256"],
                    "size": package_size,
                },
            }
            golden = {
                key: copy.deepcopy(selected_record[key])
                for key in (
                    "source",
                    "recipe",
                    "toolchain",
                    "build",
                    "artifact",
                    "metadata",
                    "tuning_candidate",
                )
            }
            golden.update(
                {
                    "core_id": "alpha",
                    "architecture": "arm64",
                    "e2e": {
                        "run_id": selected["run_id"],
                        "content_sha256": selected["content_sha256"],
                        "package_sha256": package_store["sha256"],
                        "build_records": {
                            "arm64": selected["build_record"]["sha256"]
                        },
                    },
                    "local_store": {
                        "availability": "local-only",
                        "artifact": artifact_store,
                        "metadata": metadata_store,
                        "e2e_record": selected["e2e_record"],
                        "package": package_store,
                        "build_records": {"arm64": selected["build_record"]},
                        "build_logs": {"arm64": selected["build_log"]},
                        "recipe_snapshots": {
                            "arm64": selected["recipe_snapshot"]
                        },
                    },
                    "reproduction": {
                        "schema_version": 1,
                        "validation_scope": pipeline.TUNED_REPRODUCTION_SCOPE,
                        "selected": selected,
                        "reproduction": reproduction,
                        "equivalent_outputs": outputs,
                    },
                }
            )
            document = {"build_goldens": {"alpha": {"arm64": golden}}}

            def valid_artifact(_path: Path, _arch: str) -> dict:
                return {"status": "valid", "sha256": artifact_sha}

            with (
                mock.patch.object(pipeline, "ROOT", repository_root),
                mock.patch.object(pipeline, "DEFAULT_STORE", store_root),
                mock.patch.object(
                    pipeline,
                    "DEFAULT_CHIPSET_TUNINGS",
                    repository_root / "manifests" / "chipset-tunings.json",
                ),
                mock.patch.object(pipeline, "validate_artifact", valid_artifact),
                mock.patch.object(pipeline, "_verify_recipe_snapshot", return_value=[]),
                mock.patch.object(
                    pipeline, "registered_core_log_contract_proves", return_value=True
                ),
            ):
                self.assertEqual([], pipeline.verify_local_store(document))

                tampered = copy.deepcopy(document)
                tampered["build_goldens"]["alpha"]["arm64"]["reproduction"][
                    "equivalent_outputs"
                ]["artifact"]["sha256"] = "f" * 64
                self.assertTrue(pipeline.verify_local_store(tampered))

                tampered = copy.deepcopy(document)
                tampered["build_goldens"]["alpha"]["arm64"]["reproduction"][
                    "reproduction"
                ]["run_id"] = selected["run_id"]
                self.assertTrue(pipeline.verify_local_store(tampered))

            self.assertNotEqual(
                selected_record["build"]["log_sha256"],
                reproduction_record["build"]["log_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
