#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.runtime import (
    HOST_EXECUTION_PROFILE_PATH,
    HOST_EXECUTION_PROFILE_SCHEMA_PATH,
    TELEMETRY_SCHEMA_PATH,
    TOOL_WRAPPER_SOURCE,
    UNIT_RUNNER_COMPILE_ARGUMENTS,
    UNIT_RUNNER_SOURCE,
    build_host_execution_contract,
    build_sidecar_document,
    execute_instrumented_container,
    parse_unit_evidence,
    resolve_host_execution_profile,
    validate_job_count_log,
    validate_sidecar_document,
)
from scripts.core_pipeline_lib.runtime import telemetry


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_SPEC = importlib.util.spec_from_file_location(
    "core_pipeline_host_build_telemetry_tests", ROOT / "scripts" / "core_pipeline.py"
)
assert PIPELINE_SPEC and PIPELINE_SPEC.loader
pipeline = importlib.util.module_from_spec(PIPELINE_SPEC)
PIPELINE_SPEC.loader.exec_module(pipeline)
SHA_A = "a" * 64
SHA_B = "b" * 64
CONTAINER_ID = "c" * 64


def _copy(root: Path, relative: Path | str) -> Path:
    relative = Path(relative)
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, target)
    return target


def _store(root: Path, namespace: str, source: Path) -> dict:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    relative = (
        Path(".local-e2e")
        / "store"
        / namespace
        / "sha256"
        / digest[:2]
        / digest
    )
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    return {"path": relative.as_posix(), "file_sha256": digest}


def _snapshot(*, end: bool) -> dict:
    amount = 1 if end else 0
    return {
        "cpu_max": {"quota_us": 800000, "period_us": 100000},
        # This intentionally matches the live WSL2/Docker portable subset and
        # does not require nice_usec or core_sched.force_idle_usec.
        "cpu_stat": {
            "usage_usec": 100 + 100 * amount,
            "user_usec": 60 + 60 * amount,
            "system_usec": 40 + 40 * amount,
            "nr_periods": 2 + 2 * amount,
            "nr_throttled": amount,
            "throttled_usec": 10 * amount,
            "nr_bursts": 0,
            "burst_usec": 0,
        },
        "effective_cpuset": "0-7",
        "effective_cpuset_count": 8,
        "memory_current_bytes": 100 + 100 * amount,
        "memory_max_bytes": 4 * 1024**3,
        "memory_peak_bytes": 200 + 100 * amount,
        "memory_events": {
            "low": 0,
            "high": 0,
            "max": 0,
            "oom": 0,
            "oom_kill": 0,
            "oom_group_kill": 0,
        },
        "memory_events_local": {
            "low": 0,
            "high": 0,
            "max": 0,
            "oom": 0,
            "oom_kill": 0,
            "oom_group_kill": 0,
        },
        "swap_current_bytes": 0,
        "swap_max_bytes": 0,
        "swap_peak_bytes": 0,
        "swap_events": {"high": 0, "max": 0, "fail": 0},
        "io_stat": {
            "8:0": {
                "rbytes": 10 + 10 * amount,
                "wbytes": 20 + 20 * amount,
                "rios": 1 + amount,
                "wios": 2 + 2 * amount,
                "dbytes": 0,
                "dios": 0,
            }
        },
        "pids_current": 2 + amount,
        "pids_max": 1024,
        "pids_peak": 3 + amount,
    }


def _resources() -> dict:
    return {
        "start": _snapshot(end=False),
        "end": _snapshot(end=True),
        "delta": {
            "cpu_stat": {
                "usage_usec": 100,
                "user_usec": 60,
                "system_usec": 40,
                "nr_periods": 2,
                "nr_throttled": 1,
                "throttled_usec": 10,
                "nr_bursts": 0,
                "burst_usec": 0,
            },
            "memory_events_local": {
                "low": 0,
                "high": 0,
                "max": 0,
                "oom": 0,
                "oom_kill": 0,
                "oom_group_kill": 0,
            },
            "swap_events": {"high": 0, "max": 0, "fail": 0},
            "io_stat": {
                "rbytes": 10,
                "wbytes": 20,
                "rios": 1,
                "wios": 2,
                "dbytes": 0,
                "dios": 0,
            },
        },
        "oom_observed": False,
    }


def _unit(kind: str, start: int, finish: int) -> dict:
    return {
        "kind": kind,
        "source_path": "src/example.c" if kind == "compile" else None,
        "compiler": "aarch64-linux-gnu-gcc",
        "command_sha256": SHA_A if kind == "compile" else SHA_B,
        "language": "c" if kind == "compile" else "link",
        "target_abi": "arm64",
        "result": "passed",
        "exit_code": 0,
        "signal": 0,
        "started_monotonic_ns": start,
        "finished_monotonic_ns": finish,
        "elapsed_ns": finish - start,
        "user_cpu_us": 30 if kind == "compile" else 10,
        "system_cpu_us": 10 if kind == "compile" else 5,
        "max_rss_bytes": 4096,
    }


def _fixture(
    root: Path,
    *,
    selector: str = "local",
    run_id: str = "potator-host-fixture",
) -> tuple[dict, object, dict]:
    registry = _copy(root, HOST_EXECUTION_PROFILE_PATH)
    profile_schema = _copy(root, HOST_EXECUTION_PROFILE_SCHEMA_PATH)
    telemetry_schema_file = _copy(root, TELEMETRY_SCHEMA_PATH)
    unit_runner = _copy(root, UNIT_RUNNER_SOURCE)
    wrapper = _copy(root, TOOL_WRAPPER_SOURCE)
    registry_ref = _store(root, "host-execution-profiles", registry)
    profile_schema_ref = _store(root, "schemas", profile_schema)
    telemetry_schema = _store(root, "schemas", telemetry_schema_file)
    unit_runner_ref = _store(root, "host-build-tools", unit_runner)
    wrapper_ref = _store(root, "host-build-tools", wrapper)
    profile = resolve_host_execution_profile(
        selector,
        repository_root=root,
        registry_path=root / registry_ref["path"],
        registry_schema_path=root / profile_schema_ref["path"],
    )
    instrumentation = {
        "schema_version": 1,
        "tool_wrapper": wrapper_ref,
        "unit_runner_source": unit_runner_ref,
        "unit_runner_compile": {
            "compiler_command": "cc",
            "arguments": list(UNIT_RUNNER_COMPILE_ARGUMENTS),
        },
    }
    host_execution = build_host_execution_contract(
        profile=profile,
        instrumentation=instrumentation,
        telemetry_schema=telemetry_schema,
        repository_root=root,
    )
    compile_unit = _unit("compile", 220, 260)
    link_unit = _unit("link", 270, 290)
    build = {
        "core_id": "potator",
        "architecture": "arm64",
        "driver": "libretro-super",
        "result": "passed",
        "bindings": {
            "build_record": {
                "path": ".local-e2e/store/build-records/sha256/bb/" + SHA_B,
                "file_sha256": SHA_B,
            },
            "source": {"commit": "1" * 40},
            "recipe": {"host_execution": host_execution},
            "toolchain": {"image_id": "sha256:" + SHA_A},
            "abi": {
                "architecture": "arm64",
                "elf_class": "ELF64",
                "machine": "AArch64",
                "interpreter": None,
            },
            "tuning": None,
            "outputs": {
                "artifact": {"path": "potator_libretro.so", "sha256": SHA_A, "size": 10},
                "metadata": {"path": "potator_libretro.info", "sha256": SHA_B, "size": 11},
                "build_log": {"path": ".local-e2e/store/logs/sha256/aa/" + SHA_A, "sha256": SHA_A},
            },
        },
        "instrumentation": {
            "contract": instrumentation,
            "bootstrap": {
                "compiler_resolved_path": "/usr/bin/cc",
                "compiler_version": "cc fixture 1",
                "compile_argv": ["/usr/bin/cc", *UNIT_RUNNER_COMPILE_ARGUMENTS],
                "unit_runner_binary_sha256": SHA_A,
            },
        },
        "phases": {
            "orchestration": {"status": "measured", "clock": "CLOCK_MONOTONIC", "duration_ns": 5},
            "source_hydration": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "started_monotonic_ns": 100,
                "finished_monotonic_ns": 150,
                "duration_ns": 50,
            },
            "configure": {
                "status": "not_applicable",
                "reason": "libretro-super-make-driver-has-no-separate-configure-phase",
            },
            "build_command": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "started_monotonic_ns": 200,
                "finished_monotonic_ns": 300,
                "duration_ns": 100,
            },
            "compile": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "started_monotonic_ns": 220,
                "finished_monotonic_ns": 260,
                "duration_ns": 40,
            },
            "link": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "started_monotonic_ns": 270,
                "finished_monotonic_ns": 290,
                "duration_ns": 20,
            },
            "validation": {"status": "measured", "clock": "CLOCK_MONOTONIC", "duration_ns": 7},
        },
        "container": {
            "container_id": CONTAINER_ID,
            "requested_host_config": {
                "AutoRemove": False,
                "NanoCpus": 8_000_000_000,
                "Memory": 4 * 1024**3,
                "MemorySwap": 4 * 1024**3,
                "PidsLimit": 1024,
                "CgroupnsMode": "private",
            },
            "state": {
                "status": "exited",
                "oom_killed": False,
                "dead": False,
                "exit_code": 0,
                "error": "",
                "started_at": "fixture-start",
                "finished_at": "fixture-finish",
            },
            "execution_duration_ns": 100,
        },
        "resources": _resources(),
        "units": {
            "configured_jobs": 8,
            "nproc_observation_count": 1,
            "nproc_observations": ["8"],
            "counts": {"c": 1, "c++": 0, "assembly": 0, "rust": 0, "link": 1},
            "units": [compile_unit, link_unit],
            "compile_cpu_aggregate": {
                "method": "nearest-rank-v1",
                "p50_us": 40,
                "p95_us": 40,
                "max_us": 40,
                "total_us": 40,
            },
            "longest_compile_units": [
                {"source_path": "src/example.c", "elapsed_ns": 40, "cpu_us": 40}
            ],
            "phase_bounds": {
                "compile": {"started_monotonic_ns": 220, "finished_monotonic_ns": 260, "duration_ns": 40},
                "link": {"started_monotonic_ns": 270, "finished_monotonic_ns": 290, "duration_ns": 20},
            },
            "estimated_critical_path_ns": 60,
        },
    }
    document = build_sidecar_document(
        run_id=run_id,
        profile=profile,
        builds=[build],
        packages=[
            {
                "core_id": "potator",
                "result": "packaged",
                "path": "potator_libretro.zip",
                "sha256": SHA_A,
                "size": 12,
            }
        ],
        package_duration_ns=9,
        result="passed",
        telemetry_schema=telemetry_schema,
        repository_root=root,
    )
    return document, profile, instrumentation


def _rehash(document: dict) -> None:
    document["content_sha256"] = telemetry.telemetry_content_sha256(document)


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _bound_e2e_fixture(
    root: Path,
    *,
    selector: str = "local",
    run_id: str = "potator-host-fixture",
    log_marker: str = "fixture",
) -> tuple[dict, dict, Path]:
    document, profile, _ = _fixture(
        root, selector=selector, run_id=run_id
    )
    build = document["builds"][0]
    log_path = root / "build.log"
    log_path.write_text(
        f"CORE_PIPELINE_JOBS|8\nmake -j8 target # {log_marker}\n",
        encoding="utf-8",
    )
    log_ref = _store(root, "logs", log_path)
    build["bindings"]["outputs"]["build_log"] = {
        "path": log_ref["path"],
        "sha256": log_ref["file_sha256"],
    }
    record = {
        "schema_version": 2,
        "local_only": True,
        "publication": "disabled",
        "core_id": "potator",
        "architecture": "arm64",
        "result": "passed",
        "build_exit_code": 0,
        "source": copy.deepcopy(build["bindings"]["source"]),
        "recipe": copy.deepcopy(build["bindings"]["recipe"]),
        "toolchain": copy.deepcopy(build["bindings"]["toolchain"]),
        "build": {
            "driver": "libretro-super",
            "log": "build.log",
            "log_sha256": log_ref["file_sha256"],
        },
        "artifact": {
            "path": "potator_libretro.so",
            "sha256": SHA_A,
            "size": 10,
            "elf_class": "ELF64",
            "machine": "AArch64",
            "interpreter": None,
        },
        "metadata": {
            "path": "potator_libretro.info",
            "sha256": SHA_B,
            "size": 11,
        },
    }
    record_path = root / "build-record.json"
    _write_json(record_path, record)
    record_ref = _store(root, "build-records", record_path)
    build["bindings"]["build_record"] = {
        "path": record_ref["path"],
        "file_sha256": record_ref["file_sha256"],
    }
    _rehash(document)
    sidecar_path = root / "sidecar.json"
    _write_json(sidecar_path, document)
    sidecar_ref = _store(root, "host-build-telemetry", sidecar_path)
    evidence = {
        "schema_version": 2,
        "run_id": document["run_id"],
        "local_only": True,
        "publication": "disabled",
        "result": "passed",
        "runner": {
            "schema_version": 2,
            **profile.runner_identity(),
            "local_only": True,
            "publication": "disabled",
            "execution_profile": {
                **profile.reference(),
                "execution_label": profile.execution_label,
            },
            "telemetry": {
                **sidecar_ref,
                "content_sha256": document["content_sha256"],
            },
        },
        "builds": [
            {
                "core_id": "potator",
                "architecture": "arm64",
                "result": "passed",
                "record": "ignored-by-hardened-cas-binding",
                "record_sha256": record_ref["file_sha256"],
            }
        ],
        "packages": copy.deepcopy(document["packages"]),
    }
    evidence["content_sha256"] = pipeline.e2e_content_sha256(evidence)
    return evidence, document, root / sidecar_ref["path"]


class HostBuildTelemetryTests(unittest.TestCase):
    def test_host_reproduction_deeply_validates_hardened_cas_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected, selected_telemetry, _ = _bound_e2e_fixture(
                root,
                selector="github-actions-sim",
                run_id="selected-host-fixture",
                log_marker="selected",
            )
            selected_file = root / "selected-e2e-record.json"
            _write_json(selected_file, selected)
            selected_ref_raw = _store(root, "e2e", selected_file)

            reproduction, reproduction_telemetry, _ = _bound_e2e_fixture(
                root,
                selector="local",
                run_id="reproduction-host-fixture",
                log_marker="reproduction",
            )
            reproduction_file = root / "reproduction-e2e-record.json"
            _write_json(reproduction_file, reproduction)
            reproduction_ref_raw = _store(root, "e2e", reproduction_file)

            def stored_reference(raw: dict) -> dict:
                return {
                    "path": raw["path"],
                    "sha256": raw["file_sha256"],
                }

            selected_record_raw = selected_telemetry["builds"][0]["bindings"][
                "build_record"
            ]
            reproduction_record_raw = reproduction_telemetry["builds"][0][
                "bindings"
            ]["build_record"]
            selected_record = json.loads(
                (root / selected_record_raw["path"]).read_text(encoding="utf-8")
            )
            reproduction_record = json.loads(
                (root / reproduction_record_raw["path"]).read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                pipeline.host_reproduction_build_identity(selected_record),
                pipeline.host_reproduction_build_identity(reproduction_record),
            )
            package = selected["packages"][0]
            proof = {
                "schema_version": 1,
                "validation_scope": pipeline.HOST_REPRODUCTION_SCOPE,
                "selected": {
                    "run_id": selected["run_id"],
                    "content_sha256": selected["content_sha256"],
                    "e2e_record": stored_reference(selected_ref_raw),
                },
                "reproduction": {
                    "run_id": reproduction["run_id"],
                    "content_sha256": reproduction["content_sha256"],
                    "e2e_record": stored_reference(reproduction_ref_raw),
                },
                "equivalent_builds": {
                    "arm64": pipeline.host_reproduction_build_content_sha256(
                        selected_record
                    )
                },
                "equivalent_outputs": pipeline.host_reproduction_output_identity(
                    {"arm64": selected_record}, package
                ),
            }
            proof["content_sha256"] = (
                pipeline.host_reproduction_content_sha256(proof)
            )
            selected_build_reference = {
                "path": selected_record_raw["path"],
                "sha256": selected_record_raw["file_sha256"],
            }
            golden = {
                **copy.deepcopy(selected_record),
                "promotion_state": "build_golden",
                "validation_scope": "static-build-only",
                "host_reproduction": proof,
                "e2e": {
                    "run_id": selected["run_id"],
                    "content_sha256": selected["content_sha256"],
                    "package_sha256": package["sha256"],
                    "build_records": {
                        "arm64": selected_record_raw["file_sha256"]
                    },
                },
                "local_store": {
                    "e2e_record": stored_reference(selected_ref_raw),
                    "build_records": {"arm64": selected_build_reference},
                },
            }
            with mock.patch.object(pipeline, "ROOT", root), mock.patch.object(
                pipeline, "DEFAULT_STORE", root / ".local-e2e" / "store"
            ):
                self.assertEqual(
                    [],
                    pipeline.verify_host_reproduction_bundle(
                        {"arm64": golden}, "potator"
                    ),
                )

                swapped = copy.deepcopy(golden)
                swapped_proof = swapped["host_reproduction"]
                swapped_proof["selected"], swapped_proof["reproduction"] = (
                    swapped_proof["reproduction"],
                    swapped_proof["selected"],
                )
                swapped_proof["content_sha256"] = (
                    pipeline.host_reproduction_content_sha256(swapped_proof)
                )
                self.assertTrue(
                    pipeline.verify_host_reproduction_bundle(
                        {"arm64": swapped}, "potator"
                    )
                )

                mismatch = copy.deepcopy(golden)
                mismatch["host_reproduction"]["equivalent_outputs"][
                    "package"
                ]["sha256"] = SHA_B
                mismatch["host_reproduction"]["content_sha256"] = (
                    pipeline.host_reproduction_content_sha256(
                        mismatch["host_reproduction"]
                    )
                )
                self.assertTrue(
                    pipeline.verify_host_reproduction_bundle(
                        {"arm64": mismatch}, "potator"
                    )
                )

    def test_deep_sidecar_accepts_portable_wsl_cpu_stat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document, _, _ = _fixture(root)
            self.assertEqual(
                document,
                validate_sidecar_document(document, repository_root=root),
            )

    def test_external_binding_survives_promotion_copy_and_registry_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, _, _ = _bound_e2e_fixture(root)
            (root / HOST_EXECUTION_PROFILE_PATH).write_text("{}\n", encoding="utf-8")
            promoted_e2e_path = (
                root / ".local-e2e" / "store" / "e2e" / "sha256" / "ff" / ("f" * 64)
            )
            with mock.patch.object(pipeline, "ROOT", root), mock.patch.object(
                pipeline, "DEFAULT_STORE", root / ".local-e2e" / "store"
            ):
                document = pipeline.validate_bound_host_telemetry(
                    evidence, promoted_e2e_path
                )
            self.assertEqual(evidence["run_id"], document["run_id"])

    def test_external_binding_rejects_self_hashed_nested_output_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, document, _ = _bound_e2e_fixture(root)
            forged = copy.deepcopy(document)
            forged["builds"][0]["bindings"]["outputs"]["artifact"]["sha256"] = "d" * 64
            _rehash(forged)
            forged_path = root / "forged-sidecar.json"
            _write_json(forged_path, forged)
            forged_ref = _store(root, "host-build-telemetry", forged_path)
            evidence["runner"]["telemetry"] = {
                **forged_ref,
                "content_sha256": forged["content_sha256"],
            }
            with mock.patch.object(pipeline, "ROOT", root), mock.patch.object(
                pipeline, "DEFAULT_STORE", root / ".local-e2e" / "store"
            ), self.assertRaisesRegex(pipeline.PipelineError, "nested build binding"):
                pipeline.validate_bound_host_telemetry(
                    evidence, root / "promoted-e2e-record.json"
                )

    def test_external_binding_rejects_symlinked_build_record_cas(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence, document, _ = _bound_e2e_fixture(root)
            record_path = root / document["builds"][0]["bindings"]["build_record"]["path"]
            real = record_path.with_name(record_path.name + ".real")
            record_path.rename(real)
            record_path.symlink_to(real.name)
            with mock.patch.object(pipeline, "ROOT", root), mock.patch.object(
                pipeline, "DEFAULT_STORE", root / ".local-e2e" / "store"
            ), self.assertRaisesRegex(
                pipeline.PipelineError, "build-record reference is invalid"
            ):
                pipeline.validate_bound_host_telemetry(
                    evidence, root / "promoted-e2e-record.json"
                )

    def test_self_hashed_nested_mutations_fail_closed(self) -> None:
        mutations = {
            "malformed cpuset": lambda build: build["resources"]["end"].update(
                {"effective_cpuset": "0-"}
            ),
            "counter delta": lambda build: build["resources"]["delta"]["cpu_stat"].update(
                {"usage_usec": 99}
            ),
            "unit aggregate": lambda build: build["units"]["compile_cpu_aggregate"].update(
                {"p95_us": 41}
            ),
            "phase escape": lambda build: build["units"]["units"][0].update(
                {"started_monotonic_ns": 199, "elapsed_ns": 61}
            ),
            "host config": lambda build: build["container"]["requested_host_config"].update(
                {"Memory": 1}
            ),
            "output digest type": lambda build: build["bindings"]["outputs"]["artifact"].update(
                {"sha256": "not-a-digest"}
            ),
            "memory peak regression": lambda build: build["resources"]["end"].update(
                {"memory_current_bytes": 100, "memory_peak_bytes": 100}
            ),
            "pids peak regression": lambda build: build["resources"]["end"].update(
                {"pids_current": 2, "pids_peak": 2}
            ),
            "global memory event regression": lambda build: (
                build["resources"]["start"]["memory_events"].update({"high": 2}),
                build["resources"]["end"]["memory_events"].update({"high": 1}),
            ),
            "absolute source path": lambda build: (
                build["units"]["units"][0].update({"source_path": "/etc/passwd"}),
                build["units"]["longest_compile_units"][0].update(
                    {"source_path": "/etc/passwd"}
                ),
            ),
            "impossible cpu accounting": lambda build: build["resources"]["end"]["cpu_stat"].update(
                {"usage_usec": 250}
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pristine, _, _ = _fixture(root)
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    document = copy.deepcopy(pristine)
                    mutate(document["builds"][0])
                    _rehash(document)
                    with self.assertRaises(PipelineError):
                        validate_sidecar_document(document, repository_root=root)

    def test_every_make_job_spelling_is_checked(self) -> None:
        accepted = (
            "make -j8 target",
            "make -j 8 target",
            "make --jobs=8 target",
            "make --jobs 8 target",
        )
        for invocation in accepted:
            validate_job_count_log(
                "CORE_PIPELINE_JOBS|8\n" + invocation + "\n",
                8,
                require_parallel_invocation=True,
            )
        for invocation in (
            "make -j target",
            "make --jobs target",
            "make -j8 --jobs=24 target",
            "make -j8 --jobs 24 target",
        ):
            with self.subTest(invocation=invocation), self.assertRaises(PipelineError):
                validate_job_count_log(
                    "CORE_PIPELINE_JOBS|8\n" + invocation + "\n",
                    8,
                    require_parallel_invocation=True,
                )

    def test_failed_container_exit_code_is_still_a_docker_byte(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document, _, _ = _fixture(root)
            build = document["builds"][0]
            build["result"] = "failed"
            build["container"]["state"]["exit_code"] = -1
            document["packages"] = [
                {
                    "core_id": "potator",
                    "result": "not_packaged",
                    "reason": "build-failed",
                }
            ]
            document["result"] = "failed"
            _rehash(document)
            with self.assertRaisesRegex(PipelineError, "exit_code|container result"):
                validate_sidecar_document(document, repository_root=root)

    def test_instrumented_prelude_reaches_real_create_process_without_nul(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, profile, instrumentation = _fixture(root)
            output = root / "output"
            output.mkdir()
            fake_bin = root / "bin"
            fake_bin.mkdir()
            marker = root / "docker-called"
            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                "#!/bin/sh\n"
                ': > "$FAKE_DOCKER_MARKER"\n'
                "printf '%s\\n' 'synthetic create rejection' >&2\n"
                "exit 73\n",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            catalog = pipeline.load_catalog(pipeline.DEFAULT_CATALOG)
            script = pipeline.container_build_script(
                "potator",
                "arm64",
                catalog["cores"]["potator"],
                catalog["resolver"],
                jobs=profile.jobs,
                instrumentation=True,
            )
            self.assertNotIn("\x00", script)
            self.assertIn("printf '%s\\0'", script)

            with mock.patch.dict(
                os.environ,
                {
                    "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
                    "FAKE_DOCKER_MARKER": str(marker),
                },
            ):
                with self.assertRaisesRegex(
                    PipelineError,
                    r"Docker create failed \(73\): synthetic create rejection",
                ):
                    execute_instrumented_container(
                        repository_root=root,
                        output_dir=output,
                        image_id="sha256:" + SHA_A,
                        script=script,
                        mount_args=[],
                        log_path=output / "build.log",
                        profile=profile,
                        instrumentation=instrumentation,
                    )

            self.assertTrue(marker.is_file())

    def test_create_rejects_embedded_nul_before_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, profile, instrumentation = _fixture(root)
            output = root / "output"
            output.mkdir()
            with mock.patch.object(telemetry.subprocess, "run") as run:
                with self.assertRaisesRegex(PipelineError, "embedded NUL byte"):
                    execute_instrumented_container(
                        repository_root=root,
                        output_dir=output,
                        image_id="sha256:" + SHA_A,
                        script="true\x00false",
                        mount_args=[],
                        log_path=output / "build.log",
                        profile=profile,
                        instrumentation=instrumentation,
                    )
            run.assert_not_called()

    def test_malformed_successful_cidfile_cleans_up_by_exact_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, profile, instrumentation = _fixture(root)
            output = root / "output"
            output.mkdir()
            calls: list[list[str]] = []

            def fake_run(command: list[str], **_: object) -> SimpleNamespace:
                calls.append(command)
                if command[:3] == ["docker", "container", "create"]:
                    cidfile = Path(command[command.index("--cidfile") + 1])
                    cidfile.write_text("malformed\n", encoding="ascii")
                    return SimpleNamespace(returncode=0, stdout="malformed\n", stderr="")
                if command[:4] == ["docker", "container", "rm", "--force"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                self.fail(f"unexpected command: {command}")

            with mock.patch.object(telemetry.uuid, "uuid4") as mocked_uuid, mock.patch.object(
                telemetry.subprocess, "run", side_effect=fake_run
            ):
                mocked_uuid.return_value.hex = "d" * 32
                with self.assertRaisesRegex(PipelineError, "invalid container ID"):
                    execute_instrumented_container(
                        repository_root=root,
                        output_dir=output,
                        image_id="sha256:" + SHA_A,
                        script="true",
                        mount_args=[],
                        log_path=output / "build.log",
                        profile=profile,
                        instrumentation=instrumentation,
                    )

            self.assertEqual(
                [
                    "docker",
                    "container",
                    "rm",
                    "--force",
                    "core-pipeline-host-" + "d" * 32,
                ],
                calls[-1],
            )

    def test_successful_container_lifecycle_observes_both_host_configs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, profile, instrumentation = _fixture(root)
            output = root / "output"
            output.mkdir()
            events: list[object] = []
            expected_host_config = {
                "AutoRemove": False,
                "NanoCpus": 8_000_000_000,
                "Memory": 4 * 1024**3,
                "MemorySwap": 4 * 1024**3,
                "PidsLimit": 1024,
                "CgroupnsMode": "private",
            }
            final_state = {
                "Status": "exited",
                "OOMKilled": False,
                "Dead": False,
                "ExitCode": 0,
                "Error": "",
                "StartedAt": "fixture-start",
                "FinishedAt": "fixture-finish",
            }

            def fake_run(command: list[str], **_: object) -> SimpleNamespace:
                events.append(("run", command))
                if command[:3] == ["docker", "container", "create"]:
                    cidfile = Path(command[command.index("--cidfile") + 1])
                    cidfile.write_text(CONTAINER_ID + "\n", encoding="ascii")
                    return SimpleNamespace(
                        returncode=0, stdout=CONTAINER_ID + "\n", stderr=""
                    )
                if command[:4] == ["docker", "container", "rm", "--force"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                self.fail(f"unexpected command: {command}")

            inspections = [
                {"HostConfig": copy.deepcopy(expected_host_config)},
                {
                    "HostConfig": copy.deepcopy(expected_host_config),
                    "State": final_state,
                },
            ]

            def fake_inspect(command: list[str], *, cwd: Path) -> dict:
                events.append(("inspect", command, cwd))
                return inspections.pop(0)

            class FakePopen:
                def __init__(self, command: list[str], **_: object) -> None:
                    events.append(("popen", command))
                    self.stdout = iter(["CORE_PIPELINE_JOBS|8\n", "make -j8 target\n"])

                def wait(self) -> int:
                    events.append("wait")
                    return 0

            with mock.patch.object(
                telemetry.subprocess, "run", side_effect=fake_run
            ), mock.patch.object(
                telemetry.subprocess, "Popen", FakePopen
            ), mock.patch.object(
                telemetry, "_docker_json", side_effect=fake_inspect
            ), mock.patch.object(
                telemetry, "parse_resource_evidence", return_value=_resources()
            ) as parse_resources:
                result = execute_instrumented_container(
                    repository_root=root,
                    output_dir=output,
                    image_id="sha256:" + SHA_A,
                    script="true",
                    mount_args=[],
                    log_path=output / "build.log",
                    profile=profile,
                    instrumentation=instrumentation,
                )

            create = events[0][1]
            self.assertIn("--cpus", create)
            self.assertEqual("8", create[create.index("--cpus") + 1])
            self.assertEqual(str(4 * 1024**3), create[create.index("--memory") + 1])
            self.assertEqual(
                str(4 * 1024**3), create[create.index("--memory-swap") + 1]
            )
            self.assertEqual("1024", create[create.index("--pids-limit") + 1])
            inspect_events = [event for event in events if event[0] == "inspect"]
            self.assertEqual(2, len(inspect_events))
            self.assertIn(
                ("popen", ["docker", "container", "start", "--attach", CONTAINER_ID]),
                events,
            )
            self.assertEqual(
                ("run", ["docker", "container", "rm", "--force", CONTAINER_ID]),
                events[-1],
            )
            parse_resources.assert_called_once_with(output, profile)
            self.assertEqual(expected_host_config, result["requested_host_config"])
            self.assertEqual(final_state["ExitCode"], result["docker_state"]["exit_code"])

    def test_unit_runner_preserves_argv0_and_normalizes_signal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "runner"
            subprocess.run(
                [
                    "cc", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-o", str(runner), str(ROOT / UNIT_RUNNER_SOURCE),
                ],
                check=True,
            )
            fake_source = root / "fake.c"
            fake_source.write_text(
                """
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
  FILE *f = fopen(getenv("CAPTURE"), "w");
  if (!f) return 126;
  fprintf(f, "%s|%s|%d\\n", argv[0], getenv("MARKER"), argc);
  fclose(f);
  if (getenv("SIGNAL_SELF")) raise(SIGTERM);
  fputs("fake-stdout\\n", stdout);
  fputs("fake-stderr\\n", stderr);
  return 7;
}
""".strip()
                + "\n",
                encoding="utf-8",
            )
            fake = root / "fake-compiler"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-o", str(fake), str(fake_source)],
                check=True,
            )
            capture = root / "capture.txt"
            metrics = root / "metrics.txt"
            environment = {"CAPTURE": str(capture), "MARKER": "kept"}
            completed = subprocess.run(
                [str(runner), str(metrics), str(fake), "aarch64-linux-gnu-gcc", "--flag"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
            )
            self.assertEqual(7, completed.returncode)
            self.assertEqual("fake-stdout\n", completed.stdout)
            self.assertEqual("fake-stderr\n", completed.stderr)
            self.assertEqual("aarch64-linux-gnu-gcc|kept|2\n", capture.read_text())
            self.assertIn("exit_code=7\n", metrics.read_text())
            self.assertIn("signal=0\n", metrics.read_text())

            signal_metrics = root / "signal-metrics.txt"
            environment["SIGNAL_SELF"] = "1"
            signaled = subprocess.run(
                [str(runner), str(signal_metrics), str(fake), "aarch64-linux-gnu-gcc"],
                env=environment,
                check=False,
            )
            self.assertEqual(128 + 15, signaled.returncode)
            self.assertIn("exit_code=0\n", signal_metrics.read_text())
            self.assertIn("signal=15\n", signal_metrics.read_text())

            output = root / "output"
            units_root = output / ".host-build-telemetry" / "units"
            compile_root = units_root / "unit.compile"
            link_root = units_root / "unit.link"
            compile_root.mkdir(parents=True)
            link_root.mkdir()
            for directory, kind, metric_source, wrapper_exit, arguments in (
                (
                    compile_root,
                    "compile",
                    metrics,
                    7,
                    ["-c", "/libretro-super/core/src/failure.c"],
                ),
                (
                    link_root,
                    "link",
                    signal_metrics,
                    143,
                    ["-shared", "-o", "failure.so"],
                ),
            ):
                (directory / "compiler.txt").write_text(
                    "aarch64-linux-gnu-gcc\n", encoding="utf-8"
                )
                (directory / "kind.txt").write_text(kind + "\n", encoding="utf-8")
                (directory / "cwd.txt").write_text(
                    "/libretro-super/core\n", encoding="utf-8"
                )
                (directory / "argv.bin").write_bytes(
                    b"".join(item.encode() + b"\0" for item in arguments)
                )
                shutil.copyfile(metric_source, directory / "metrics.txt")
                (directory / "wrapper-exit-code.txt").write_text(
                    str(wrapper_exit) + "\n", encoding="utf-8"
                )
            telemetry_root = output / ".host-build-telemetry"
            (telemetry_root / "nproc-observations.txt").write_text(
                "8\n", encoding="utf-8"
            )
            metric_values = []
            for metric_path in (metrics, signal_metrics):
                metric_values.append(
                    {
                        key: int(value)
                        for key, value in (
                            line.split("=", 1)
                            for line in metric_path.read_text().splitlines()
                        )
                    }
                )
            phase_start = min(item["started_monotonic_ns"] for item in metric_values) - 1
            phase_finish = max(item["finished_monotonic_ns"] for item in metric_values) + 1
            units = parse_unit_evidence(
                output,
                source_dir="core",
                architecture="arm64",
                jobs=8,
                build_log_text="CORE_PIPELINE_JOBS|8\nmake -j8 target\n",
                build_command_phase={
                    "status": "measured",
                    "clock": "CLOCK_MONOTONIC",
                    "started_monotonic_ns": phase_start,
                    "finished_monotonic_ns": phase_finish,
                    "duration_ns": phase_finish - phase_start,
                },
                require_complete=False,
            )
            observed = {(item["kind"], item["result"]): item for item in units["units"]}
            self.assertEqual(7, observed[("compile", "failed")]["exit_code"])
            self.assertEqual(0, observed[("compile", "failed")]["signal"])
            self.assertEqual(0, observed[("link", "failed")]["exit_code"])
            self.assertEqual(15, observed[("link", "failed")]["signal"])

    def test_wrapper_preserves_gcc_prefix_under_shadowed_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "unit-runner"
            subprocess.run(
                [
                    "cc",
                    "-O2",
                    "-std=c11",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-o",
                    str(runner),
                    str(ROOT / UNIT_RUNNER_SOURCE),
                ],
                check=True,
            )
            real_cc = shutil.which("cc")
            real_cxx = shutil.which("c++")
            self.assertIsNotNone(real_cc)
            self.assertIsNotNone(real_cxx)
            assert real_cc is not None and real_cxx is not None
            wrapper_bin = root / "wrapper-bin"
            wrapper_bin.mkdir()
            wrapper = wrapper_bin / "cc"
            shutil.copyfile(ROOT / TOOL_WRAPPER_SOURCE, wrapper)
            wrapper.chmod(0o755)
            telemetry_root = root / "telemetry"
            telemetry_root.mkdir()
            source = root / "probe.c"
            source.write_text("int probe(void) { return 0; }\n", encoding="utf-8")
            output = root / "probe.o"
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": str(wrapper_bin)
                    + os.pathsep
                    + environment["PATH"],
                    "CORE_PIPELINE_JOBS": "8",
                    "CORE_PIPELINE_TELEMETRY_ROOT": str(telemetry_root),
                    "CORE_PIPELINE_CC_BASENAME": "cc",
                    "CORE_PIPELINE_CXX_BASENAME": "c++",
                    "CORE_PIPELINE_REAL_CC": real_cc,
                    "CORE_PIPELINE_REAL_CXX": real_cxx,
                    "CORE_PIPELINE_UNIT_RUNNER": str(runner),
                }
            )
            arguments = ["-c", str(source), "-o", str(output)]
            completed = subprocess.run(
                ["cc", *arguments],
                cwd=root,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(output.is_file())
            unit_directories = list((telemetry_root / "units").iterdir())
            self.assertEqual(1, len(unit_directories))
            unit = unit_directories[0]
            self.assertEqual("cc\n", (unit / "compiler.txt").read_text())
            self.assertEqual(
                b"".join(argument.encode() + b"\0" for argument in arguments),
                (unit / "argv.bin").read_bytes(),
            )
            self.assertEqual("0\n", (unit / "wrapper-exit-code.txt").read_text())
            self.assertIn("exit_code=0\n", (unit / "metrics.txt").read_text())


if __name__ == "__main__":
    unittest.main()
