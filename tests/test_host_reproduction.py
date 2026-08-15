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


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "core_pipeline_host_reproduction_tests",
    ROOT / "scripts" / "core_pipeline.py",
)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _hardened_runner(*, selected: bool) -> dict:
    registry = "1" * 64
    schema = "2" * 64
    telemetry = ("3" if selected else "4") * 64
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
                + registry
            ),
            "file_sha256": registry,
            "content_sha256": "5" * 64,
            "schema": {
                "path": ".local-e2e/store/schemas/sha256/22/" + schema,
                "file_sha256": schema,
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
                + telemetry[:2]
                + "/"
                + telemetry
            ),
            "file_sha256": telemetry,
            "content_sha256": ("9" if selected else "a") * 64,
        },
    }


def _record(*, log_sha256: str) -> dict:
    return {
        "schema_version": 2,
        "local_only": True,
        "publication": "disabled",
        "core_id": "alpha",
        "architecture": "arm64",
        "result": "passed",
        "build_exit_code": 0,
        "source": {
            "url": "https://example.invalid/alpha.git",
            "requested_ref": "1" * 40,
            "commit": "1" * 40,
            "resolved_commit": "1" * 40,
            "tree": "2" * 40,
            "resolved_url": "https://example.invalid/alpha.git",
            "submodules": [],
        },
        "recipe": {"host_execution": {"resource_class_id": "host-equivalent-v1"}},
        "toolchain": {"resolved_image_id": "sha256:" + "3" * 64},
        "build": {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "log": "build.log",
            "log_sha256": log_sha256,
        },
        "artifact": {
            "status": "valid",
            "path": "alpha_libretro.so",
            "sha256": "4" * 64,
            "size": 8,
        },
        "metadata": {
            "status": "valid",
            "path": "alpha_libretro.info",
            "sha256": "5" * 64,
            "size": 9,
        },
    }


class HostReproductionTests(unittest.TestCase):
    def test_equivalence_rejects_legacy_roles_drift_and_nonindependence(self) -> None:
        selected_record = _record(log_sha256="6" * 64)
        reproduction_record = _record(log_sha256="7" * 64)

        def bundle(*, selected: bool, record: dict) -> dict:
            label = "selected" if selected else "reproduction"
            return {
                "e2e": {
                    "run_id": label,
                    "content_sha256": ("b" if selected else "c") * 64,
                    "runner": _hardened_runner(selected=selected),
                },
                "e2e_path": Path(label) / "e2e-record.json",
                "targets": {
                    "arm64": {
                        "record": record,
                        "record_path": Path(label) / "build-record.json",
                        "log_path": Path(label) / "build.log",
                    }
                },
                "package_record": {
                    "path": "alpha_libretro.zip",
                    "sha256": "8" * 64,
                    "size": 10,
                },
            }

        selected = bundle(selected=True, record=selected_record)
        reproduction = bundle(selected=False, record=reproduction_record)
        build_digests, outputs = pipeline.require_host_reproduction_equivalence(
            selected, reproduction
        )
        self.assertEqual(
            pipeline.host_reproduction_build_content_sha256(selected_record),
            build_digests["arm64"],
        )
        self.assertEqual("8" * 64, outputs["package"]["sha256"])

        legacy = copy.deepcopy(reproduction)
        legacy["e2e"]["runner"] = pipeline.base_runner_evidence(
            legacy["e2e"]["runner"]
        )
        with self.assertRaisesRegex(pipeline.PipelineError, "hardened"):
            pipeline.require_host_reproduction_equivalence(selected, legacy)

        swapped = copy.deepcopy(reproduction)
        swapped["e2e"]["runner"] = _hardened_runner(selected=True)
        with self.assertRaisesRegex(pipeline.PipelineError, "github-actions-sim"):
            pipeline.require_host_reproduction_equivalence(selected, swapped)

        drift = copy.deepcopy(reproduction)
        drift["targets"]["arm64"]["record"]["source"]["tree"] = "9" * 40
        with self.assertRaisesRegex(pipeline.PipelineError, "source, recipe"):
            pipeline.require_host_reproduction_equivalence(selected, drift)

        output_mismatch = copy.deepcopy(reproduction)
        output_mismatch["package_record"]["sha256"] = "a" * 64
        with self.assertRaisesRegex(pipeline.PipelineError, "package bytes"):
            pipeline.require_host_reproduction_equivalence(
                selected, output_mismatch
            )

        same_run = copy.deepcopy(reproduction)
        same_run["e2e_path"] = selected["e2e_path"]
        with self.assertRaisesRegex(pipeline.PipelineError, "independent"):
            pipeline.require_host_reproduction_equivalence(selected, same_run)

        selected_ref = {
            "path": ".local-e2e/store/e2e/sha256/dd/" + "d" * 64,
            "sha256": "d" * 64,
        }
        reproduction_ref = {
            "path": ".local-e2e/store/e2e/sha256/ee/" + "e" * 64,
            "sha256": "e" * 64,
        }
        source_candidate = {"candidate_id": "f" * 64}
        selected["source_candidate"] = source_candidate
        reproduction["source_candidate"] = copy.deepcopy(source_candidate)
        proof = pipeline.create_host_reproduction_proof(
            selected,
            reproduction,
            selected_e2e_record=selected_ref,
            reproduction_e2e_record=reproduction_ref,
        )
        promoted = copy.deepcopy(selected_record)
        promoted["source_candidate"] = copy.deepcopy(source_candidate)
        promoted["e2e"] = {
            "run_id": "selected",
            "content_sha256": "b" * 64,
            "package_sha256": "8" * 64,
        }
        promoted["local_store"] = {"e2e_record": selected_ref}
        promoted["host_reproduction"] = copy.deepcopy(proof)
        self.assertEqual(
            proof,
            pipeline.validated_host_reproduction_shape(
                proof,
                core_id="alpha",
                golden_records={"arm64": promoted},
            ),
        )

    def test_promote_host_reproduction_is_create_only_and_projects_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs = root / ".local-e2e" / "runs"
            nightlies = root / ".local-e2e" / "nightlies"
            store_root = root / ".local-e2e" / "store"
            pins = root / "pins" / "core-sets"
            catalog_path = root / "manifests" / "core-builds.json"
            catalog_path.parent.mkdir(parents=True)
            catalog_path.write_text("{}\n", encoding="utf-8")
            source_path = nightlies / "alpha-candidate-host" / "golden.json"
            source_path.parent.mkdir(parents=True)
            source_document = {
                "schema_version": 2,
                "core_id": "alpha",
                "pin_id": "alpha-candidate-host",
                "created_at": "2026-08-10T00:00:00+00:00",
                "baseline": {},
                "cores": {"alpha": {"artifacts": {}}},
                "build_goldens": {"alpha": {}},
            }
            source_path.write_bytes(_json_bytes(source_document))

            artifact = b"artifact"
            metadata = b"metadata!"
            package = b"package!!!"
            selected_root = runs / "selected"
            reproduction_root = runs / "reproduction"
            selected_root.mkdir(parents=True)
            reproduction_root.mkdir(parents=True)
            (selected_root / "alpha_libretro.so").write_bytes(artifact)
            (selected_root / "alpha_libretro.info").write_bytes(metadata)
            (selected_root / "alpha_libretro.zip").write_bytes(package)
            selected_log = selected_root / "build.log"
            reproduction_log = reproduction_root / "build.log"
            selected_log.write_bytes(b"selected log")
            reproduction_log.write_bytes(b"reproduction log")
            selected_record = _record(
                log_sha256=pipeline.sha256_file(selected_log)
            )
            reproduction_record = _record(
                log_sha256=pipeline.sha256_file(reproduction_log)
            )
            selected_record["artifact"]["sha256"] = pipeline.sha256_bytes(artifact)
            selected_record["artifact"]["size"] = len(artifact)
            selected_record["metadata"]["sha256"] = pipeline.sha256_bytes(metadata)
            selected_record["metadata"]["size"] = len(metadata)
            reproduction_record["artifact"] = copy.deepcopy(
                selected_record["artifact"]
            )
            reproduction_record["metadata"] = copy.deepcopy(
                selected_record["metadata"]
            )
            selected_record_path = selected_root / "build-record.json"
            reproduction_record_path = reproduction_root / "build-record.json"
            selected_record_path.write_bytes(_json_bytes(selected_record))
            reproduction_record_path.write_bytes(_json_bytes(reproduction_record))
            selected_e2e_path = selected_root / "e2e-record.json"
            reproduction_e2e_path = reproduction_root / "e2e-record.json"
            selected_e2e_path.write_bytes(b"{\"selected\":true}\n")
            reproduction_e2e_path.write_bytes(b"{\"reproduction\":true}\n")
            package_record = {
                "path": "alpha_libretro.zip",
                "sha256": pipeline.sha256_bytes(package),
                "size": len(package),
            }

            def bundle(*, selected: bool) -> dict:
                run_root = selected_root if selected else reproduction_root
                record = selected_record if selected else reproduction_record
                record_path = (
                    selected_record_path
                    if selected
                    else reproduction_record_path
                )
                e2e_path = selected_e2e_path if selected else reproduction_e2e_path
                run_id = "selected" if selected else "reproduction"
                return {
                    "e2e": {
                        "run_id": run_id,
                        "content_sha256": ("a" if selected else "b") * 64,
                        "runner": _hardened_runner(selected=selected),
                    },
                    "e2e_path": e2e_path,
                    "e2e_file_sha256": pipeline.sha256_file(e2e_path),
                    "targets": {
                        "arm64": {
                            "record": record,
                            "record_path": record_path,
                            "record_sha256": pipeline.sha256_file(record_path),
                            "artifact_path": selected_root / "alpha_libretro.so",
                            "metadata_path": selected_root / "alpha_libretro.info",
                            "log_path": run_root / "build.log",
                        }
                    },
                    "package_path": selected_root / "alpha_libretro.zip",
                    "package_record": package_record,
                }

            selected = bundle(selected=True)
            reproduction = bundle(selected=False)

            def compose_pin(**kwargs) -> dict:
                golden = pipeline.load_json(kwargs["source_paths"][0])
                selection = pipeline.complete_core_bundle(golden, "alpha")
                assert selection is not None
                pin = {
                    "pin_id": kwargs["pin_id"],
                    "scope": ["alpha"],
                    "parent": None,
                    "sources": [
                        {
                            "path": str(
                                kwargs["source_paths"][0].relative_to(root)
                            )
                        }
                    ],
                    "cores": {
                        "alpha": {
                            "decision": "select_source",
                            "source_index": 0,
                            "selection": selection,
                        }
                    },
                    "content_sha256": "c" * 64,
                }
                kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
                kwargs["output_path"].write_bytes(_json_bytes(pin))
                return pin

            catalog = {"cores": {"alpha": {}}}
            with (
                mock.patch.object(pipeline, "ROOT", root),
                mock.patch.object(pipeline, "DEFAULT_RUNS", runs),
                mock.patch.object(pipeline, "DEFAULT_NIGHTLIES", nightlies),
                mock.patch.object(pipeline, "DEFAULT_STORE", store_root),
                mock.patch.object(pipeline, "DEFAULT_PIN_SET_DIR", pins),
                mock.patch.object(pipeline, "DEFAULT_CATALOG", catalog_path),
                mock.patch.object(
                    pipeline,
                    "load_catalog_with_sha256",
                    return_value=(catalog, "d" * 64),
                ),
                mock.patch.object(
                    pipeline,
                    "validate_host_reproduction_e2e_evidence",
                    side_effect=[selected, reproduction],
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
                    pipeline, "manifest_lock", side_effect=lambda _path: nullcontext()
                ),
                mock.patch.object(
                    pipeline, "compose_pin_set", side_effect=compose_pin
                ),
            ):
                result = pipeline.promote_host_reproduction(
                    core_id="alpha",
                    source_golden_path=source_path,
                    selected_e2e_path=selected_e2e_path,
                    reproduction_e2e_path=reproduction_e2e_path,
                    catalog_path=catalog_path,
                    store_root=store_root,
                )
                golden_path = root / result["golden"]
                pin_path = root / result["pin"]
                self.assertTrue(golden_path.is_file())
                self.assertTrue(pin_path.is_file())
                golden = pipeline.load_json(golden_path)
                selection = pipeline.complete_core_bundle(golden, "alpha")
                assert selection is not None
                proof = selection["host_reproduction"]
                self.assertEqual(
                    proof["content_sha256"],
                    result["host_reproduction_content_sha256"],
                )
                self.assertEqual(
                    proof["content_sha256"],
                    pipeline.load_json(pin_path)["cores"]["alpha"]["selection"][
                        "host_reproduction"
                    ]["content_sha256"],
                )

                successor = copy.deepcopy(golden)
                successor_proof = successor["build_goldens"]["alpha"][
                    "arm64"
                ]["host_reproduction"]
                successor_proof["reproduction"] = {
                    "run_id": "reproduction-successor",
                    "content_sha256": "e" * 64,
                    "e2e_record": {
                        "path": (
                            ".local-e2e/store/e2e/sha256/ff/" + "f" * 64
                        ),
                        "sha256": "f" * 64,
                    },
                }
                successor_proof["content_sha256"] = (
                    pipeline.host_reproduction_content_sha256(successor_proof)
                )
                successor_selection = pipeline.complete_core_bundle(
                    successor, "alpha"
                )
                assert successor_selection is not None
                self.assertNotEqual(
                    result["semantic_id"],
                    pipeline.individual_core_semantic_id(
                        "alpha", successor_selection
                    ),
                )

                with self.assertRaisesRegex(
                    pipeline.PipelineError, "refusing to replace"
                ), mock.patch.object(
                    pipeline,
                    "validate_host_reproduction_e2e_evidence",
                    side_effect=[selected, reproduction],
                ):
                    pipeline.promote_host_reproduction(
                        core_id="alpha",
                        source_golden_path=source_path,
                        selected_e2e_path=selected_e2e_path,
                        reproduction_e2e_path=reproduction_e2e_path,
                        catalog_path=catalog_path,
                        store_root=store_root,
                    )


if __name__ == "__main__":
    unittest.main()
