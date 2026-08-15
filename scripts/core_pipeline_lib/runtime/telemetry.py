"""Measured local-host build execution and canonical telemetry evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import shlex
import subprocess
import tempfile
import time
from typing import Mapping
import uuid

from ..errors import PipelineError
from ..foundation import atomic_write_json, sha256_file
from .errors import RunnerProfileError
from .execution import HostExecutionProfile, resolve_host_execution_profile


TELEMETRY_SCHEMA_REFERENCE = "../../../manifests/host-build-telemetry.schema.json"
TELEMETRY_SCHEMA_PATH = Path("manifests/host-build-telemetry.schema.json")
TELEMETRY_FILENAME = "telemetry.json"
RAW_TELEMETRY_DIRECTORY = ".host-build-telemetry"
TOOL_SOURCE_DIRECTORY = "/host-build-telemetry-tools"
UNIT_RUNNER_SOURCE = "scripts/host_build_unit_runner.c"
TOOL_WRAPPER_SOURCE = "scripts/host_build_tool_wrapper.sh"
UNIT_RUNNER_COMPILE_ARGUMENTS = (
    "-O2",
    "-std=c11",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-o",
    "/tmp/core-pipeline-host-telemetry-bin/unit-runner",
    f"{TOOL_SOURCE_DIRECTORY}/unit-runner.c",
)
CONTAINER_ID_PATTERN = re.compile(r"[0-9a-f]{64}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
CGROUP_FILES = (
    "cgroup.controllers",
    "cgroup.type",
    "cpu.max",
    "cpu.stat",
    "cpuset.cpus.effective",
    "memory.current",
    "memory.max",
    "memory.peak",
    "memory.events",
    "memory.events.local",
    "memory.swap.current",
    "memory.swap.max",
    "memory.swap.peak",
    "memory.swap.events",
    "io.stat",
    "pids.current",
    "pids.max",
    "pids.peak",
)
INTEGER_MAP_FILES = frozenset(
    {"cpu.stat", "memory.events", "memory.events.local", "memory.swap.events"}
)
COMPILE_SUFFIXES = {
    ".c": "c",
    ".cc": "c++",
    ".cpp": "c++",
    ".cxx": "c++",
    ".C": "c++",
    ".s": "assembly",
    ".S": "assembly",
    ".asm": "assembly",
}
REQUIRED_CPU_STAT_KEYS = frozenset(
    {
        "usage_usec",
        "user_usec",
        "system_usec",
        "nr_periods",
        "nr_throttled",
        "throttled_usec",
    }
)
REQUIRED_MEMORY_EVENT_KEYS = frozenset(
    {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"}
)
FAILED_SOURCE_PHASE_REASON = "build-failed-before-source-hydration-phase"
FAILED_BUILD_PHASE_REASON = "build-failed-before-build-command-phase"
FAILED_UNITS_REASON = "no-compile-or-link-units-observed-before-build-failure"
FAILED_LINK_REASON = "build-failed-before-link-unit-observed"
REQUIRED_SWAP_EVENT_KEYS = frozenset({"high", "max", "fail"})


def telemetry_content_sha256(document: dict) -> str:
    material = copy.deepcopy(document)
    material.pop("content_sha256", None)
    canonical = json.dumps(
        material, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _validated_cas_reference(
    reference: object,
    *,
    repository_root: Path,
    namespace: str,
    label: str,
) -> Path:
    if not isinstance(reference, dict) or set(reference) != {
        "path",
        "file_sha256",
    }:
        raise PipelineError(f"{label} content-addressed reference is malformed")
    digest = reference.get("file_sha256")
    if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
        raise PipelineError(f"{label} content-addressed digest is invalid")
    expected = (
        Path(".local-e2e")
        / "store"
        / namespace
        / "sha256"
        / digest[:2]
        / digest
    )
    if reference.get("path") != expected.as_posix():
        raise PipelineError(f"{label} content-addressed path is not canonical")
    path = repository_root / expected
    current = repository_root
    for part in expected.parts:
        current /= part
        if current.is_symlink():
            raise PipelineError(f"{label} content-addressed path traverses a symlink")
    if not path.is_file() or sha256_file(path) != digest:
        raise PipelineError(f"{label} content-addressed bytes are unavailable")
    return path


def validate_instrumentation_contract(
    value: object, *, repository_root: Path
) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "tool_wrapper",
        "unit_runner_source",
        "unit_runner_compile",
    }:
        raise PipelineError("host-build instrumentation contract is malformed")
    if value.get("schema_version") != 1 or type(value.get("schema_version")) is not int:
        raise PipelineError("host-build instrumentation contract version is invalid")
    _validated_cas_reference(
        value.get("tool_wrapper"),
        repository_root=repository_root,
        namespace="host-build-tools",
        label="host-build tool wrapper",
    )
    _validated_cas_reference(
        value.get("unit_runner_source"),
        repository_root=repository_root,
        namespace="host-build-tools",
        label="host-build unit runner source",
    )
    compile_contract = value.get("unit_runner_compile")
    if not isinstance(compile_contract, dict) or compile_contract != {
        "compiler_command": "cc",
        "arguments": list(UNIT_RUNNER_COMPILE_ARGUMENTS),
    }:
        raise PipelineError("host-build unit runner compile contract is invalid")
    return copy.deepcopy(value)


def instrumentation_mount_args(
    repository_root: Path, instrumentation: Mapping[str, object]
) -> list[str]:
    contract = validate_instrumentation_contract(
        instrumentation, repository_root=repository_root
    )
    source = repository_root / contract["unit_runner_source"]["path"]
    wrapper = repository_root / contract["tool_wrapper"]["path"]
    return [
        "-v",
        f"{source.resolve()}:{TOOL_SOURCE_DIRECTORY}/unit-runner.c:ro",
        "-v",
        f"{wrapper.resolve()}:{TOOL_SOURCE_DIRECTORY}/tool-wrapper.sh:ro",
    ]


def instrumentation_shell_prelude() -> str:
    """Install versioned probes before source hydration or target compilation."""

    files = " ".join(shlex.quote(item) for item in CGROUP_FILES)
    return f"""
test "$CORE_PIPELINE_JOBS" = "8"
export CORE_PIPELINE_TELEMETRY_ROOT=/output/{RAW_TELEMETRY_DIRECTORY}
mkdir -p "$CORE_PIPELINE_TELEMETRY_ROOT/phases"
core_pipeline_real_cc="$(command -v "$CC")"
core_pipeline_real_cxx="$(command -v "$CXX")"
test -x "$core_pipeline_real_cc"
test -x "$core_pipeline_real_cxx"
core_pipeline_cc_basename="${{CC##*/}}"
core_pipeline_cxx_basename="${{CXX##*/}}"
test "$core_pipeline_cc_basename" != nproc
test "$core_pipeline_cxx_basename" != nproc
core_pipeline_tool_bin=/tmp/core-pipeline-host-telemetry-bin
mkdir -p "$core_pipeline_tool_bin"
core_pipeline_bootstrap_cc="$(command -v cc)"
test -x "$core_pipeline_bootstrap_cc"
printf '%s\n' "$core_pipeline_bootstrap_cc" \
  > "$CORE_PIPELINE_TELEMETRY_ROOT/bootstrap-compiler-path.txt"
"$core_pipeline_bootstrap_cc" --version | head -n 1 \
  > "$CORE_PIPELINE_TELEMETRY_ROOT/bootstrap-compiler-version.txt"
printf '%s\\0' "$core_pipeline_bootstrap_cc" \
  {' '.join(shlex.quote(item) for item in UNIT_RUNNER_COMPILE_ARGUMENTS)} \
  > "$CORE_PIPELINE_TELEMETRY_ROOT/bootstrap-compile-argv.bin"
"$core_pipeline_bootstrap_cc" -O2 -std=c11 -Wall -Wextra -Werror \
  -o "$core_pipeline_tool_bin/unit-runner" \
  {TOOL_SOURCE_DIRECTORY}/unit-runner.c
sha256sum "$core_pipeline_tool_bin/unit-runner" \
  | awk '{{print $1}}' > "$CORE_PIPELINE_TELEMETRY_ROOT/unit-runner-sha256.txt"
install -m 0755 {TOOL_SOURCE_DIRECTORY}/tool-wrapper.sh \
  "$core_pipeline_tool_bin/$core_pipeline_cc_basename"
if test "$core_pipeline_cxx_basename" != "$core_pipeline_cc_basename"; then
  install -m 0755 {TOOL_SOURCE_DIRECTORY}/tool-wrapper.sh \
    "$core_pipeline_tool_bin/$core_pipeline_cxx_basename"
fi
install -m 0755 {TOOL_SOURCE_DIRECTORY}/tool-wrapper.sh \
  "$core_pipeline_tool_bin/nproc"
export CORE_PIPELINE_REAL_CC="$core_pipeline_real_cc"
export CORE_PIPELINE_REAL_CXX="$core_pipeline_real_cxx"
export CORE_PIPELINE_CC_BASENAME="$core_pipeline_cc_basename"
export CORE_PIPELINE_CXX_BASENAME="$core_pipeline_cxx_basename"
export CORE_PIPELINE_UNIT_RUNNER="$core_pipeline_tool_bin/unit-runner"
export PATH="$core_pipeline_tool_bin:$PATH"
core_pipeline_capture_cgroup() {{
  core_pipeline_snapshot=$1
  core_pipeline_snapshot_dir="$CORE_PIPELINE_TELEMETRY_ROOT/cgroup-$core_pipeline_snapshot"
  mkdir "$core_pipeline_snapshot_dir"
  for core_pipeline_cgroup_file in {files}; do
    test -r "/sys/fs/cgroup/$core_pipeline_cgroup_file"
    cp "/sys/fs/cgroup/$core_pipeline_cgroup_file" \
      "$core_pipeline_snapshot_dir/$core_pipeline_cgroup_file"
  done
}}
core_pipeline_phase_start() {{
  core_pipeline_phase=$1
  core_pipeline_phase_path="$CORE_PIPELINE_TELEMETRY_ROOT/phases/$core_pipeline_phase.started-ns"
  test ! -e "$core_pipeline_phase_path"
  "$CORE_PIPELINE_UNIT_RUNNER" --clock > "$core_pipeline_phase_path"
}}
core_pipeline_phase_finish() {{
  core_pipeline_phase=$1
  core_pipeline_phase_path="$CORE_PIPELINE_TELEMETRY_ROOT/phases/$core_pipeline_phase.finished-ns"
  test ! -e "$core_pipeline_phase_path"
  "$CORE_PIPELINE_UNIT_RUNNER" --clock > "$core_pipeline_phase_path"
}}
core_pipeline_telemetry_finalize() {{
  core_pipeline_original_status=$?
  trap - EXIT
  set +e
  core_pipeline_capture_cgroup end
  core_pipeline_capture_status=$?
  chown -R "$OUTPUT_UID:$OUTPUT_GID" "$CORE_PIPELINE_TELEMETRY_ROOT"
  core_pipeline_chown_status=$?
  if test "$core_pipeline_original_status" = 0 \
    && test "$core_pipeline_capture_status" != 0; then
    core_pipeline_original_status=86
  fi
  if test "$core_pipeline_original_status" = 0 \
    && test "$core_pipeline_chown_status" != 0; then
    core_pipeline_original_status=87
  fi
  exit "$core_pipeline_original_status"
}}
trap core_pipeline_telemetry_finalize EXIT
core_pipeline_capture_cgroup start
printf 'CORE_PIPELINE_JOBS|%s\n' "$CORE_PIPELINE_JOBS"
""".strip()


def phase_start_shell(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise PipelineError("host-build telemetry phase name is invalid")
    return f"core_pipeline_phase_start {name}"


def phase_finish_shell(name: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise PipelineError("host-build telemetry phase name is invalid")
    return f"core_pipeline_phase_finish {name}"


def _docker_json(args: list[str], *, cwd: Path) -> dict:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PipelineError(
            f"Docker telemetry command failed ({result.returncode}): "
            f"{shlex.join(args)}\n{detail}"
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineError("Docker inspect returned malformed JSON") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise PipelineError("Docker inspect returned an unexpected document")
    return value[0]


def _verify_host_config(config: object, profile: HostExecutionProfile) -> dict:
    if not isinstance(config, dict):
        raise PipelineError("Docker HostConfig is missing")
    expected = {
        "AutoRemove": False,
        "NanoCpus": profile.cpu_quota * 1_000_000_000,
        "Memory": profile.memory_bytes,
        "MemorySwap": profile.memory_swap_bytes,
        "PidsLimit": profile.pids_limit,
        "CgroupnsMode": "private",
    }
    for key, value in expected.items():
        if config.get(key) != value or (
            isinstance(value, int)
            and not isinstance(value, bool)
            and type(config.get(key)) is not int
        ):
            raise PipelineError(
                f"Docker HostConfig {key} differs from the execution profile"
            )
    return expected


def execute_instrumented_container(
    *,
    repository_root: Path,
    output_dir: Path,
    image_id: str,
    script: str,
    mount_args: list[str],
    log_path: Path,
    profile: HostExecutionProfile,
    instrumentation: Mapping[str, object],
) -> dict:
    """Create, inspect, attach, observe, and remove exactly one build container."""

    container_name = "core-pipeline-host-" + uuid.uuid4().hex
    temporary = tempfile.TemporaryDirectory(prefix="core-pipeline-host-cid-")
    cidfile = Path(temporary.name) / "container-id"
    create_command = [
        "docker",
        "container",
        "create",
        "--name",
        container_name,
        "--cidfile",
        str(cidfile),
        "--cgroupns=private",
        "--cpus",
        str(profile.cpu_quota),
        "--memory",
        str(profile.memory_bytes),
        "--memory-swap",
        str(profile.memory_swap_bytes),
        "--pids-limit",
        str(profile.pids_limit),
        "-e",
        f"CORE_PIPELINE_JOBS={profile.jobs}",
        "-e",
        f"OUTPUT_UID={os.getuid()}",
        "-e",
        f"OUTPUT_GID={os.getgid()}",
        "-v",
        f"{output_dir.resolve()}:/output",
        *mount_args,
        *instrumentation_mount_args(repository_root, instrumentation),
        image_id,
        "bash",
        "-lc",
        script,
    ]
    orchestration_started = time.monotonic_ns()
    container_id: str | None = None
    create_succeeded = False
    try:
        if any("\x00" in argument for argument in create_command):
            raise PipelineError("Docker create command contains an embedded NUL byte")
        create = subprocess.run(
            create_command,
            cwd=repository_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if create.returncode:
            detail = create.stderr.strip() or create.stdout.strip()
            raise PipelineError(
                f"Docker create failed ({create.returncode}): {detail}"
            )
        create_succeeded = True
        try:
            candidate_container_id = cidfile.read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise PipelineError("Docker create did not produce a readable cidfile") from exc
        if (
            CONTAINER_ID_PATTERN.fullmatch(candidate_container_id) is None
            or create.stdout.strip() != candidate_container_id
        ):
            raise PipelineError("Docker create returned an invalid container ID")
        container_id = candidate_container_id
        before = _docker_json(
            ["docker", "container", "inspect", container_id], cwd=repository_root
        )
        requested_host_config = _verify_host_config(before.get("HostConfig"), profile)
        orchestration_finished = time.monotonic_ns()
        execution_started = time.monotonic_ns()
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["docker", "container", "start", "--attach", container_id],
                cwd=repository_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
            client_exit_code = process.wait()
        execution_finished = time.monotonic_ns()
        after = _docker_json(
            ["docker", "container", "inspect", container_id], cwd=repository_root
        )
        state = after.get("State")
        after_host_config = _verify_host_config(after.get("HostConfig"), profile)
        if after_host_config != requested_host_config:
            raise PipelineError("Docker HostConfig changed during execution")
        if not isinstance(state, dict):
            raise PipelineError("Docker final container State is missing")
        exit_code = state.get("ExitCode")
        if type(exit_code) is not int or exit_code != client_exit_code:
            raise PipelineError("Docker client and container exit codes differ")
        final_state = {
            "status": state.get("Status"),
            "oom_killed": state.get("OOMKilled"),
            "dead": state.get("Dead"),
            "exit_code": exit_code,
            "error": state.get("Error"),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
        }
        if (
            final_state["status"] != "exited"
            or type(final_state["oom_killed"]) is not bool
            or type(final_state["dead"]) is not bool
            or not isinstance(final_state["error"], str)
            or not isinstance(final_state["started_at"], str)
            or not isinstance(final_state["finished_at"], str)
        ):
            raise PipelineError("Docker final container State is malformed")
        resources = parse_resource_evidence(output_dir, profile)
        return {
            "container_id": container_id,
            "requested_host_config": requested_host_config,
            "docker_state": final_state,
            "orchestration_duration_ns": orchestration_finished
            - orchestration_started,
            "container_execution_duration_ns": execution_finished
            - execution_started,
            "resources": resources,
        }
    finally:
        try:
            if create_succeeded:
                removal_target = container_id or container_name
                remove = subprocess.run(
                    ["docker", "container", "rm", "--force", removal_target],
                    cwd=repository_root,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if remove.returncode != 0 and not remove.stderr.strip().endswith(
                    "No such container"
                ):
                    raise PipelineError(
                        "failed to remove exact host-build container "
                        + removal_target
                    )
        finally:
            temporary.cleanup()


def _read_required_text(path: Path, label: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise PipelineError(f"host-build telemetry {label} is missing")
    try:
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PipelineError(f"cannot read host-build telemetry {label}") from exc
    if not value:
        raise PipelineError(f"host-build telemetry {label} is empty")
    return value


def _integer_text(value: str, label: str) -> int:
    stripped = value.strip()
    if not stripped.isdecimal():
        raise PipelineError(f"host-build telemetry {label} is not an integer")
    return int(stripped)


def _integer_map(value: str, label: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in value.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[1].isdecimal() or fields[0] in result:
            raise PipelineError(f"host-build telemetry {label} is malformed")
        result[fields[0]] = int(fields[1])
    if not result:
        raise PipelineError(f"host-build telemetry {label} is empty")
    return result


def _io_map(value: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for line in value.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0] in result:
            raise PipelineError("host-build telemetry io.stat is malformed")
        counters: dict[str, int] = {}
        for item in fields[1:]:
            name, separator, raw = item.partition("=")
            if separator != "=" or not raw.isdecimal() or name in counters:
                raise PipelineError("host-build telemetry io.stat is malformed")
            counters[name] = int(raw)
        result[fields[0]] = counters
    return result


def _cpuset_count(value: str) -> int:
    seen: set[int] = set()
    for item in value.strip().split(","):
        if not item:
            raise PipelineError("host-build telemetry effective cpuset is malformed")
        start_text, separator, end_text = item.partition("-")
        if (
            not start_text.isdecimal()
            or (separator and (not end_text or not end_text.isdecimal()))
        ):
            raise PipelineError("host-build telemetry effective cpuset is malformed")
        start = int(start_text)
        end = int(end_text) if separator else start
        if end < start:
            raise PipelineError("host-build telemetry effective cpuset is malformed")
        seen.update(range(start, end + 1))
    if not seen:
        raise PipelineError("host-build telemetry effective cpuset is empty")
    return len(seen)


def _validate_cpu_stat_invariants(value: Mapping[str, int], label: str) -> None:
    if abs(value["usage_usec"] - value["user_usec"] - value["system_usec"]) > 1:
        raise PipelineError(f"host-build telemetry {label} CPU time is inconsistent")
    if value["nr_throttled"] > value["nr_periods"]:
        raise PipelineError(f"host-build telemetry {label} throttle count is inconsistent")


def _snapshot(root: Path, name: str) -> dict:
    directory = root / f"cgroup-{name}"
    if directory.is_symlink() or not directory.is_dir():
        raise PipelineError(f"host-build telemetry cgroup {name} snapshot is missing")
    raw = {
        filename: _read_required_text(directory / filename, f"{name} {filename}")
        for filename in CGROUP_FILES
    }
    if "cpu" not in raw["cgroup.controllers"].split() or raw["cgroup.type"].strip() != "domain":
        raise PipelineError("host-build telemetry cgroup identity is unsupported")
    cpu_max = raw["cpu.max"].split()
    if len(cpu_max) != 2 or not all(item.isdecimal() for item in cpu_max):
        raise PipelineError("host-build telemetry cpu.max is malformed")
    cpu_stat = _integer_map(raw["cpu.stat"], f"{name} cpu.stat")
    memory_events = _integer_map(
        raw["memory.events"], f"{name} memory.events"
    )
    memory_events_local = _integer_map(
        raw["memory.events.local"], f"{name} memory.events.local"
    )
    swap_events = _integer_map(
        raw["memory.swap.events"], f"{name} memory.swap.events"
    )
    if not REQUIRED_CPU_STAT_KEYS.issubset(cpu_stat):
        raise PipelineError("host-build telemetry cpu.stat lacks required counters")
    _validate_cpu_stat_invariants(cpu_stat, f"{name} cpu.stat")
    if not REQUIRED_MEMORY_EVENT_KEYS.issubset(memory_events) or not (
        REQUIRED_MEMORY_EVENT_KEYS.issubset(memory_events_local)
    ):
        raise PipelineError("host-build telemetry memory.events lacks required counters")
    if not REQUIRED_SWAP_EVENT_KEYS.issubset(swap_events):
        raise PipelineError("host-build telemetry swap events lack required counters")
    return {
        "cpu_max": {"quota_us": int(cpu_max[0]), "period_us": int(cpu_max[1])},
        "cpu_stat": cpu_stat,
        "effective_cpuset": raw["cpuset.cpus.effective"].strip(),
        "effective_cpuset_count": _cpuset_count(raw["cpuset.cpus.effective"]),
        "memory_current_bytes": _integer_text(
            raw["memory.current"], f"{name} memory.current"
        ),
        "memory_max_bytes": _integer_text(raw["memory.max"], f"{name} memory.max"),
        "memory_peak_bytes": _integer_text(raw["memory.peak"], f"{name} memory.peak"),
        "memory_events": memory_events,
        "memory_events_local": memory_events_local,
        "swap_current_bytes": _integer_text(
            raw["memory.swap.current"], f"{name} memory.swap.current"
        ),
        "swap_max_bytes": _integer_text(
            raw["memory.swap.max"], f"{name} memory.swap.max"
        ),
        "swap_peak_bytes": _integer_text(
            raw["memory.swap.peak"], f"{name} memory.swap.peak"
        ),
        "swap_events": swap_events,
        "io_stat": _io_map(raw["io.stat"]),
        "pids_current": _integer_text(raw["pids.current"], f"{name} pids.current"),
        "pids_max": _integer_text(raw["pids.max"], f"{name} pids.max"),
        "pids_peak": _integer_text(raw["pids.peak"], f"{name} pids.peak"),
    }


def _counter_delta(before: Mapping[str, int], after: Mapping[str, int], label: str) -> dict:
    if set(before) != set(after):
        raise PipelineError(f"host-build telemetry {label} counter set changed")
    result: dict[str, int] = {}
    for key in sorted(before):
        difference = after[key] - before[key]
        if difference < 0:
            raise PipelineError(f"host-build telemetry {label} counter regressed")
        result[key] = difference
    return result


def _io_totals(value: Mapping[str, Mapping[str, int]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for counters in value.values():
        for name, amount in counters.items():
            result[name] = result.get(name, 0) + amount
    return dict(sorted(result.items()))


def parse_resource_evidence(output_dir: Path, profile: HostExecutionProfile) -> dict:
    root = output_dir / RAW_TELEMETRY_DIRECTORY
    start = _snapshot(root, "start")
    end = _snapshot(root, "end")
    expected_cpu_max = {
        "quota_us": profile.cpu_quota * 100_000,
        "period_us": 100_000,
    }
    for snapshot in (start, end):
        if snapshot["cpu_max"] != expected_cpu_max:
            raise PipelineError("observed cgroup CPU limit differs from profile")
        if snapshot["memory_max_bytes"] != profile.memory_bytes:
            raise PipelineError("observed cgroup memory limit differs from profile")
        if snapshot["swap_max_bytes"] != 0:
            raise PipelineError("observed cgroup swap limit does not disable swap")
        if snapshot["swap_current_bytes"] != 0 or snapshot["swap_peak_bytes"] != 0:
            raise PipelineError("observed cgroup used swap despite the disabled limit")
        if snapshot["pids_max"] != profile.pids_limit:
            raise PipelineError("observed cgroup PID limit differs from profile")
        if snapshot["effective_cpuset_count"] < profile.cpu_quota:
            raise PipelineError("effective cgroup cpuset is smaller than CPU quota")
        if not (
            snapshot["memory_current_bytes"]
            <= snapshot["memory_peak_bytes"]
            <= snapshot["memory_max_bytes"]
            and snapshot["swap_current_bytes"]
            <= snapshot["swap_peak_bytes"]
            <= snapshot["swap_max_bytes"]
            and snapshot["pids_current"]
            <= snapshot["pids_peak"]
            <= snapshot["pids_max"]
        ):
            raise PipelineError("observed cgroup current/peak/limit ordering is invalid")
    cpu_delta = _counter_delta(start["cpu_stat"], end["cpu_stat"], "cpu.stat")
    memory_event_delta = _counter_delta(
        start["memory_events_local"], end["memory_events_local"], "memory.events.local"
    )
    _counter_delta(start["memory_events"], end["memory_events"], "memory.events")
    swap_event_delta = _counter_delta(
        start["swap_events"], end["swap_events"], "memory.swap.events"
    )
    io_delta = _counter_delta(
        _io_totals(start["io_stat"]), _io_totals(end["io_stat"]), "io.stat"
    )
    if any(
        end[name] < start[name]
        for name in ("memory_peak_bytes", "swap_peak_bytes", "pids_peak")
    ):
        raise PipelineError("observed cgroup peak counter regressed")
    return {
        "start": start,
        "end": end,
        "delta": {
            "cpu_stat": cpu_delta,
            "memory_events_local": memory_event_delta,
            "swap_events": swap_event_delta,
            "io_stat": io_delta,
        },
        "oom_observed": any(
            memory_event_delta.get(name, 0) > 0
            for name in ("oom", "oom_kill", "oom_group_kill")
        ),
    }


def _parse_metrics(path: Path) -> dict[str, int]:
    value: dict[str, int] = {}
    for line in _read_required_text(path, "compile-unit metrics").splitlines():
        key, separator, raw = line.partition("=")
        if (
            separator != "="
            or not key
            or not raw.isdecimal()
            or key in value
        ):
            raise PipelineError("host-build compile-unit metrics are malformed")
        value[key] = int(raw)
    expected = {
        "started_monotonic_ns",
        "finished_monotonic_ns",
        "elapsed_ns",
        "user_cpu_us",
        "system_cpu_us",
        "max_rss_kib",
        "exit_code",
        "signal",
    }
    if set(value) != expected:
        raise PipelineError("host-build compile-unit metric keys are invalid")
    if (
        value["finished_monotonic_ns"] < value["started_monotonic_ns"]
        or value["elapsed_ns"]
        != value["finished_monotonic_ns"] - value["started_monotonic_ns"]
    ):
        raise PipelineError("host-build compile-unit elapsed time is invalid")
    return value


def _argv(path: Path) -> list[str]:
    if path.is_symlink() or not path.is_file():
        raise PipelineError("host-build compile-unit argv is missing")
    raw = path.read_bytes()
    if not raw or not raw.endswith(b"\0"):
        raise PipelineError("host-build compile-unit argv is malformed")
    try:
        values = [item.decode("utf-8") for item in raw[:-1].split(b"\0")]
    except UnicodeDecodeError as exc:
        raise PipelineError("host-build compile-unit argv is not UTF-8") from exc
    if not values or any(not item or "\0" in item for item in values):
        raise PipelineError("host-build compile-unit argv is malformed")
    return values


def parse_bootstrap_evidence(output_dir: Path) -> dict:
    root = output_dir / RAW_TELEMETRY_DIRECTORY
    compiler_path = _read_required_text(
        root / "bootstrap-compiler-path.txt", "bootstrap compiler path"
    ).strip()
    compiler_version = _read_required_text(
        root / "bootstrap-compiler-version.txt", "bootstrap compiler version"
    ).strip()
    compile_argv = _argv(root / "bootstrap-compile-argv.bin")
    binary_sha256 = _read_required_text(
        root / "unit-runner-sha256.txt", "unit runner binary digest"
    ).strip()
    if (
        not compiler_path.startswith("/")
        or "\n" in compiler_path
        or not compiler_version
        or "\n" in compiler_version
        or compile_argv != [compiler_path, *UNIT_RUNNER_COMPILE_ARGUMENTS]
        or SHA256_PATTERN.fullmatch(binary_sha256) is None
    ):
        raise PipelineError("host-build unit runner bootstrap evidence is invalid")
    return {
        "compiler_resolved_path": compiler_path,
        "compiler_version": compiler_version,
        "compile_argv": compile_argv,
        "unit_runner_binary_sha256": binary_sha256,
    }


def _normalized_source_path(cwd: str, argument: str, source_root: str) -> str:
    absolute = (
        posixpath.normpath(argument)
        if argument.startswith("/")
        else posixpath.normpath(posixpath.join(cwd, argument))
    )
    normalized_root = posixpath.normpath(source_root)
    if posixpath.commonpath([absolute, normalized_root]) != normalized_root:
        raise PipelineError("compile-unit source path escapes the checked-out source")
    relative = posixpath.relpath(absolute, normalized_root)
    if relative.startswith("../") or relative in {".", ".."}:
        raise PipelineError("compile-unit source path is not source-relative")
    return relative


def _unit_record(
    directory: Path,
    *,
    source_root: str,
    architecture: str,
    allow_failed: bool,
) -> dict:
    compiler = _read_required_text(directory / "compiler.txt", "unit compiler").strip()
    kind = _read_required_text(directory / "kind.txt", "unit kind").strip()
    cwd = _read_required_text(directory / "cwd.txt", "unit cwd").strip()
    arguments = _argv(directory / "argv.bin")
    metrics = _parse_metrics(directory / "metrics.txt")
    wrapper_exit = _integer_text(
        _read_required_text(directory / "wrapper-exit-code.txt", "wrapper exit code"),
        "wrapper exit code",
    )
    expected_wrapper_exit = (
        128 + metrics["signal"]
        if metrics["signal"]
        else metrics["exit_code"]
    )
    if (
        kind not in {"compile", "link"}
        or wrapper_exit != expected_wrapper_exit
        or (metrics["signal"] and metrics["exit_code"] != 0)
    ):
        raise PipelineError("host-build compile-unit result is inconsistent")
    if not allow_failed and (metrics["signal"] != 0 or metrics["exit_code"] != 0):
        raise PipelineError("host-build compile or link unit failed")
    source_path: str | None = None
    language = "link"
    normalized_arguments = list(arguments)
    if kind == "compile":
        candidates = [
            (index, argument)
            for index, argument in enumerate(arguments)
            if Path(argument).suffix in COMPILE_SUFFIXES
        ]
        if len(candidates) != 1:
            raise PipelineError("compile unit does not name exactly one source file")
        index, source_argument = candidates[0]
        source_path = _normalized_source_path(cwd, source_argument, source_root)
        language = COMPILE_SUFFIXES[Path(source_argument).suffix]
        normalized_arguments[index] = source_path
    command_material = {
        "compiler": compiler,
        "arguments": normalized_arguments,
    }
    command_sha256 = hashlib.sha256(
        json.dumps(
            command_material, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return {
        "kind": kind,
        "source_path": source_path,
        "compiler": compiler,
        "command_sha256": command_sha256,
        "language": language,
        "target_abi": architecture,
        "result": (
            "passed"
            if metrics["exit_code"] == 0 and metrics["signal"] == 0
            else "failed"
        ),
        "exit_code": metrics["exit_code"],
        "signal": metrics["signal"],
        "started_monotonic_ns": metrics["started_monotonic_ns"],
        "finished_monotonic_ns": metrics["finished_monotonic_ns"],
        "elapsed_ns": metrics["elapsed_ns"],
        "user_cpu_us": metrics["user_cpu_us"],
        "system_cpu_us": metrics["system_cpu_us"],
        "max_rss_bytes": metrics["max_rss_kib"] * 1024,
    }


def _nearest_rank(values: list[int], percentile: float) -> int:
    if not values:
        raise PipelineError("cannot aggregate an empty compile-unit set")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def validate_job_count_log(
    build_log_text: str, jobs: int, *, require_parallel_invocation: bool
) -> None:
    """Require one configured-jobs marker and reject every competing job spelling."""

    job_markers = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_JOBS|")
    ]
    if job_markers != [f"CORE_PIPELINE_JOBS|{jobs}"]:
        raise PipelineError("build log does not bind the configured job count")
    invocation_pattern = re.compile(
        r"(?<!\S)(?:"
        r"-j(?:(?P<short_attached>[0-9]+)|(?:\s+(?P<short_space>[0-9]+)))?"
        r"|--jobs(?:=(?P<long_equals>[0-9]+)|(?:\s+(?P<long_space>[0-9]+))?)"
        r")(?=\s|$)"
    )
    observed: list[str | None] = []
    for match in invocation_pattern.finditer(build_log_text):
        observed.append(
            match.group("short_attached")
            or match.group("short_space")
            or match.group("long_equals")
            or match.group("long_space")
        )
    if require_parallel_invocation and not observed:
        raise PipelineError("build log does not prove a parallel build invocation")
    if any(value != str(jobs) for value in observed):
        raise PipelineError("build log contains a competing or unbounded job count")


def parse_unit_evidence(
    output_dir: Path,
    *,
    source_dir: str,
    architecture: str,
    jobs: int,
    build_log_text: str,
    build_command_phase: Mapping[str, object],
    require_complete: bool = True,
) -> dict:
    root = output_dir / RAW_TELEMETRY_DIRECTORY
    observations = _read_required_text(
        root / "nproc-observations.txt", "nproc observations"
    ).splitlines()
    if not observations or any(item != str(jobs) for item in observations):
        raise PipelineError("libretro-super did not consistently observe the configured jobs")
    validate_job_count_log(
        build_log_text, jobs, require_parallel_invocation=True
    )
    units_root = root / "units"
    if units_root.is_symlink() or not units_root.is_dir():
        raise PipelineError("host-build compile-unit directory is missing")
    source_root = "/libretro-super/" + source_dir.strip("/")
    unit_entries = sorted(units_root.iterdir())
    if not unit_entries or any(
        path.is_symlink() or not path.is_dir() for path in unit_entries
    ):
        raise PipelineError("host-build compile-unit directory contains invalid entries")
    units = [
        _unit_record(
            path,
            source_root=source_root,
            architecture=architecture,
            allow_failed=not require_complete,
        )
        for path in unit_entries
    ]
    units.sort(
        key=lambda item: (
            item["started_monotonic_ns"],
            item["kind"],
            item["source_path"] or "",
        )
    )
    compile_units = [item for item in units if item["kind"] == "compile"]
    link_units = [item for item in units if item["kind"] == "link"]
    if not compile_units or (require_complete and not link_units):
        raise PipelineError("host-build telemetry requires compile and link units")
    phase_started = build_command_phase.get("started_monotonic_ns")
    phase_finished = build_command_phase.get("finished_monotonic_ns")
    if (
        build_command_phase.get("status") != "measured"
        or type(phase_started) is not int
        or type(phase_finished) is not int
        or any(
            unit["started_monotonic_ns"] < phase_started
            or unit["finished_monotonic_ns"] > phase_finished
            for unit in units
        )
    ):
        raise PipelineError("compile/link units escape the measured build-command phase")
    counts = {"c": 0, "c++": 0, "assembly": 0, "rust": 0, "link": len(link_units)}
    for unit in compile_units:
        counts[unit["language"]] += 1
    cpu_costs = [item["user_cpu_us"] + item["system_cpu_us"] for item in compile_units]
    compile_started = min(item["started_monotonic_ns"] for item in compile_units)
    compile_finished = max(item["finished_monotonic_ns"] for item in compile_units)
    longest = sorted(
        compile_units,
        key=lambda item: (-item["elapsed_ns"], item["source_path"] or ""),
    )[:10]
    return {
        "configured_jobs": jobs,
        "nproc_observation_count": len(observations),
        "nproc_observations": observations,
        "counts": counts,
        "units": units,
        "compile_cpu_aggregate": {
            "method": "nearest-rank-v1",
            "p50_us": _nearest_rank(cpu_costs, 0.50),
            "p95_us": _nearest_rank(cpu_costs, 0.95),
            "max_us": max(cpu_costs),
            "total_us": sum(cpu_costs),
        },
        "longest_compile_units": [
            {
                "source_path": item["source_path"],
                "elapsed_ns": item["elapsed_ns"],
                "cpu_us": item["user_cpu_us"] + item["system_cpu_us"],
            }
            for item in longest
        ],
        "phase_bounds": {
            "compile": {
                "started_monotonic_ns": compile_started,
                "finished_monotonic_ns": compile_finished,
                "duration_ns": compile_finished - compile_started,
            },
            **(
                {
                    "link": {
                        "started_monotonic_ns": min(
                            item["started_monotonic_ns"] for item in link_units
                        ),
                        "finished_monotonic_ns": max(
                            item["finished_monotonic_ns"] for item in link_units
                        ),
                        "duration_ns": max(
                            item["finished_monotonic_ns"] for item in link_units
                        )
                        - min(
                            item["started_monotonic_ns"] for item in link_units
                        ),
                    }
                }
                if link_units
                else {}
            ),
        },
        "estimated_critical_path_ns": (compile_finished - compile_started)
        + (
            max(item["finished_monotonic_ns"] for item in link_units)
            - min(item["started_monotonic_ns"] for item in link_units)
            if link_units
            else 0
        ),
    }


def parse_measured_phase(output_dir: Path, name: str) -> dict:
    root = output_dir / RAW_TELEMETRY_DIRECTORY / "phases"
    started = _integer_text(
        _read_required_text(root / f"{name}.started-ns", f"{name} phase start"),
        f"{name} phase start",
    )
    finished = _integer_text(
        _read_required_text(root / f"{name}.finished-ns", f"{name} phase finish"),
        f"{name} phase finish",
    )
    if finished < started:
        raise PipelineError(f"host-build telemetry {name} phase regressed")
    return {
        "status": "measured",
        "clock": "CLOCK_MONOTONIC",
        "started_monotonic_ns": started,
        "finished_monotonic_ns": finished,
        "duration_ns": finished - started,
    }


def not_applicable_phase(reason: str) -> dict:
    if not isinstance(reason, str) or not reason:
        raise PipelineError("not-applicable telemetry phase requires a reason")
    return {"status": "not_applicable", "reason": reason}


def unavailable_observation(reason: str, **bindings: object) -> dict:
    if not isinstance(reason, str) or not reason:
        raise PipelineError("unavailable telemetry observation requires a reason")
    return {"status": "unavailable", "reason": reason, **bindings}


def build_host_execution_contract(
    *,
    profile: HostExecutionProfile,
    instrumentation: Mapping[str, object],
    telemetry_schema: Mapping[str, object],
    repository_root: Path,
) -> dict:
    """Bind deterministic build-affecting host inputs, never observations."""

    instrumentation_contract = validate_instrumentation_contract(
        instrumentation, repository_root=repository_root
    )
    _validated_cas_reference(
        telemetry_schema,
        repository_root=repository_root,
        namespace="schemas",
        label="host-build telemetry schema",
    )
    return {
        "schema_version": 1,
        "resource_class": {
            "resource_class_id": profile.resource_class_id,
            "content_sha256": profile.resource_class_content_sha256,
        },
        "resources": profile.resources(),
        "cache": profile.cache(),
        "instrumentation": instrumentation_contract,
        "telemetry_schema": copy.deepcopy(dict(telemetry_schema)),
    }


def validate_host_execution_contract(
    value: object, *, repository_root: Path
) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "resource_class",
        "resources",
        "cache",
        "instrumentation",
        "telemetry_schema",
    }:
        raise PipelineError("host execution recipe contract is malformed")
    if value.get("schema_version") != 1 or type(value.get("schema_version")) is not int:
        raise PipelineError("host execution recipe contract version is invalid")
    resource_class = value.get("resource_class")
    if (
        not isinstance(resource_class, dict)
        or set(resource_class) != {"resource_class_id", "content_sha256"}
        or resource_class.get("resource_class_id") != "host-8c-4g-noswap-v1"
        or not isinstance(resource_class.get("content_sha256"), str)
        or SHA256_PATTERN.fullmatch(resource_class["content_sha256"]) is None
    ):
        raise PipelineError("host execution resource-class identity is invalid")
    expected_resources = {
        "jobs": 8,
        "cpu_quota": 8,
        "memory_bytes": 4 * 1024**3,
        "memory_swap_bytes": 4 * 1024**3,
        "pids_limit": 1024,
        "matrix_parallelism": 1,
        "pair_execution": "selected-then-reproduction-sequential",
    }
    if value.get("resources") != expected_resources:
        raise PipelineError("host execution recipe resources are invalid")
    expected_cache = {
        "classification": "cold",
        "scope": "pipeline-source-build-and-compiler-state",
        "identity": "fresh-container-network-clone-no-restored-compiler-cache-v1",
        "container_filesystem": "fresh",
        "source": "fresh-network-clone",
        "compiler": "disabled",
        "image_layers": "preloaded-content-addressed-image",
        "host_page_cache": "uncontrolled",
    }
    if value.get("cache") != expected_cache:
        raise PipelineError("host execution recipe cache contract is invalid")
    validate_instrumentation_contract(
        value.get("instrumentation"), repository_root=repository_root
    )
    _validated_cas_reference(
        value.get("telemetry_schema"),
        repository_root=repository_root,
        namespace="schemas",
        label="host-build telemetry schema",
    )
    return copy.deepcopy(value)


def build_sidecar_document(
    *,
    run_id: str,
    profile: HostExecutionProfile,
    builds: list[dict],
    packages: list[dict],
    package_duration_ns: int,
    result: str,
    telemetry_schema: Mapping[str, object],
    repository_root: Path,
) -> dict:
    if result not in {"passed", "failed"}:
        raise PipelineError("host-build telemetry result is invalid")
    _validated_cas_reference(
        telemetry_schema,
        repository_root=repository_root,
        namespace="schemas",
        label="host-build telemetry schema",
    )
    document = {
        "$schema": TELEMETRY_SCHEMA_REFERENCE,
        "schema": copy.deepcopy(dict(telemetry_schema)),
        "schema_version": 1,
        "telemetry_contract": profile.telemetry_contract,
        "run_id": run_id,
        "local_only": True,
        "publication": "disabled",
        "runner": {
            "selector": profile.selector,
            **profile.runner_identity(),
            "execution_label": profile.execution_label,
        },
        "execution_profile": {
            **profile.reference(),
            "resources": profile.resources(),
        },
        "cache": profile.cache(),
        "phases": {
            "queue": not_applicable_phase("local-direct-execution-has-no-queue"),
            "package": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "duration_ns": package_duration_ns,
            },
        },
        "builds": builds,
        "packages": packages,
        "result": result,
    }
    document["content_sha256"] = telemetry_content_sha256(document)
    return document


def write_sidecar(
    run_root: Path, document: dict, *, repository_root: Path
) -> dict:
    path = run_root / TELEMETRY_FILENAME
    if path.exists():
        raise PipelineError("refusing to replace an existing host-build telemetry sidecar")
    if document.get("content_sha256") != telemetry_content_sha256(document):
        raise PipelineError("host-build telemetry content digest mismatch")
    validate_sidecar_document(document, repository_root=repository_root)
    atomic_write_json(path, document)
    return {
        "path": TELEMETRY_FILENAME,
        "file_sha256": sha256_file(path),
        "content_sha256": document["content_sha256"],
    }


def _exact_document(value: object, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise PipelineError(f"host-build telemetry {label} fields are not exact")
    return value


def _uint(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise PipelineError(f"host-build telemetry {label} is not a nonnegative integer")
    return value


def _validate_measured_phase(
    value: object, label: str, *, bounds: bool
) -> dict:
    expected = {"status", "clock", "duration_ns"}
    if bounds:
        expected.update({"started_monotonic_ns", "finished_monotonic_ns"})
    phase = _exact_document(value, expected, f"{label} phase")
    if phase.get("status") != "measured" or phase.get("clock") != "CLOCK_MONOTONIC":
        raise PipelineError(f"host-build telemetry {label} phase identity is invalid")
    duration = _uint(phase.get("duration_ns"), f"{label} duration")
    if bounds:
        started = _uint(
            phase.get("started_monotonic_ns"), f"{label} phase start"
        )
        finished = _uint(
            phase.get("finished_monotonic_ns"), f"{label} phase finish"
        )
        if finished < started or duration != finished - started:
            raise PipelineError(f"host-build telemetry {label} phase bounds are invalid")
    return phase


def _validate_unavailable(
    value: object, label: str, *, reason: str, bindings: Mapping[str, object] | None = None
) -> dict:
    expected = {"status", "reason", *(bindings or {})}
    observation = _exact_document(value, expected, f"{label} unavailable observation")
    if observation.get("status") != "unavailable" or observation.get("reason") != reason:
        raise PipelineError(f"host-build telemetry {label} unavailable reason is invalid")
    if bindings is not None and any(
        observation.get(key) != expected_value
        for key, expected_value in bindings.items()
    ):
        raise PipelineError(f"host-build telemetry {label} unavailable binding is invalid")
    return observation


def _validated_uint_map(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or not value:
        raise PipelineError(f"host-build telemetry {label} counters are invalid")
    for key, amount in value.items():
        if not isinstance(key, str) or not key:
            raise PipelineError(f"host-build telemetry {label} counter name is invalid")
        _uint(amount, f"{label}.{key}")
    return value


def _validate_resource_snapshot(value: object, resources: Mapping[str, object]) -> dict:
    snapshot = _exact_document(
        value,
        {
            "cpu_max",
            "cpu_stat",
            "effective_cpuset",
            "effective_cpuset_count",
            "memory_current_bytes",
            "memory_max_bytes",
            "memory_peak_bytes",
            "memory_events",
            "memory_events_local",
            "swap_current_bytes",
            "swap_max_bytes",
            "swap_peak_bytes",
            "swap_events",
            "io_stat",
            "pids_current",
            "pids_max",
            "pids_peak",
        },
        "resource snapshot",
    )
    cpu_max = _exact_document(
        snapshot.get("cpu_max"), {"quota_us", "period_us"}, "cpu.max"
    )
    if cpu_max != {
        "quota_us": resources["cpu_quota"] * 100_000,
        "period_us": 100_000,
    }:
        raise PipelineError("host-build telemetry cpu.max differs from resources")
    cpu_stat = _validated_uint_map(snapshot.get("cpu_stat"), "cpu.stat")
    memory_events = _validated_uint_map(
        snapshot.get("memory_events"), "memory.events"
    )
    memory_events_local = _validated_uint_map(
        snapshot.get("memory_events_local"), "memory.events.local"
    )
    swap_events = _validated_uint_map(
        snapshot.get("swap_events"), "memory.swap.events"
    )
    if not REQUIRED_CPU_STAT_KEYS.issubset(cpu_stat):
        raise PipelineError("host-build telemetry cpu.stat lacks required counters")
    _validate_cpu_stat_invariants(cpu_stat, "cpu.stat")
    if not REQUIRED_MEMORY_EVENT_KEYS.issubset(memory_events) or not (
        REQUIRED_MEMORY_EVENT_KEYS.issubset(memory_events_local)
    ):
        raise PipelineError("host-build telemetry memory events lack required counters")
    if not REQUIRED_SWAP_EVENT_KEYS.issubset(swap_events):
        raise PipelineError("host-build telemetry swap events lack required counters")
    cpuset = snapshot.get("effective_cpuset")
    if not isinstance(cpuset, str) or (
        snapshot.get("effective_cpuset_count") != _cpuset_count(cpuset)
    ) or snapshot["effective_cpuset_count"] < resources["cpu_quota"]:
        raise PipelineError("host-build telemetry effective cpuset is invalid")
    scalar_names = (
        "memory_current_bytes",
        "memory_max_bytes",
        "memory_peak_bytes",
        "swap_current_bytes",
        "swap_max_bytes",
        "swap_peak_bytes",
        "pids_current",
        "pids_max",
        "pids_peak",
    )
    for name in scalar_names:
        _uint(snapshot.get(name), name)
    if (
        snapshot["memory_max_bytes"] != resources["memory_bytes"]
        or not (
            snapshot["memory_current_bytes"]
            <= snapshot["memory_peak_bytes"]
            <= snapshot["memory_max_bytes"]
        )
        or snapshot["memory_peak_bytes"] > snapshot["memory_max_bytes"]
        or not (
            snapshot["swap_current_bytes"]
            <= snapshot["swap_peak_bytes"]
            <= snapshot["swap_max_bytes"]
        )
        or snapshot["swap_current_bytes"] != 0
        or snapshot["swap_max_bytes"] != 0
        or snapshot["swap_peak_bytes"] != 0
        or snapshot["pids_max"] != resources["pids_limit"]
        or not (
            snapshot["pids_current"]
            <= snapshot["pids_peak"]
            <= snapshot["pids_max"]
        )
    ):
        raise PipelineError("host-build telemetry resource limits are inconsistent")
    io_stat = snapshot.get("io_stat")
    if not isinstance(io_stat, dict):
        raise PipelineError("host-build telemetry io.stat is invalid")
    for device, counters in io_stat.items():
        if not isinstance(device, str) or not device:
            raise PipelineError("host-build telemetry io.stat device is invalid")
        _validated_uint_map(counters, f"io.stat.{device}")
    return snapshot


def _validate_resource_document(value: object, resources: Mapping[str, object]) -> dict:
    document = _exact_document(
        value, {"start", "end", "delta", "oom_observed"}, "resources"
    )
    start = _validate_resource_snapshot(document.get("start"), resources)
    end = _validate_resource_snapshot(document.get("end"), resources)
    delta = _exact_document(
        document.get("delta"),
        {"cpu_stat", "memory_events_local", "swap_events", "io_stat"},
        "resource delta",
    )
    expected_delta = {
        "cpu_stat": _counter_delta(start["cpu_stat"], end["cpu_stat"], "cpu.stat"),
        "memory_events_local": _counter_delta(
            start["memory_events_local"],
            end["memory_events_local"],
            "memory.events.local",
        ),
        "swap_events": _counter_delta(
            start["swap_events"], end["swap_events"], "memory.swap.events"
        ),
        "io_stat": _counter_delta(
            _io_totals(start["io_stat"]), _io_totals(end["io_stat"]), "io.stat"
        ),
    }
    _counter_delta(start["memory_events"], end["memory_events"], "memory.events")
    if any(
        end[name] < start[name]
        for name in ("memory_peak_bytes", "swap_peak_bytes", "pids_peak")
    ):
        raise PipelineError("host-build telemetry peak counter regressed")
    if delta != expected_delta:
        raise PipelineError("host-build telemetry resource deltas are invalid")
    expected_oom = any(
        expected_delta["memory_events_local"].get(name, 0) > 0
        for name in ("oom", "oom_kill", "oom_group_kill")
    )
    if type(document.get("oom_observed")) is not bool or (
        document["oom_observed"] != expected_oom
    ):
        raise PipelineError("host-build telemetry OOM result is invalid")
    return document


def _validate_unit_document(
    value: object,
    *,
    architecture: str,
    build_phase: Mapping[str, object],
    require_complete: bool,
) -> dict:
    if isinstance(value, dict) and value.get("status") == "unavailable":
        if require_complete:
            raise PipelineError("passed host-build telemetry cannot omit unit evidence")
        unavailable = _validate_unavailable(
            value,
            "compile units",
            reason=FAILED_UNITS_REASON,
            bindings={
                "configured_jobs": 8,
                "nproc_observation_count": value.get("nproc_observation_count"),
                "nproc_observations": value.get("nproc_observations"),
            },
        )
        observations = unavailable["nproc_observations"]
        if (
            not isinstance(observations, list)
            or any(item != "8" for item in observations)
            or type(unavailable["nproc_observation_count"]) is not int
            or unavailable["nproc_observation_count"] != len(observations)
        ):
            raise PipelineError("host-build telemetry unavailable job proof is invalid")
        return unavailable
    units_document = _exact_document(
        value,
        {
            "configured_jobs",
            "nproc_observation_count",
            "nproc_observations",
            "counts",
            "units",
            "compile_cpu_aggregate",
            "longest_compile_units",
            "phase_bounds",
            "estimated_critical_path_ns",
        },
        "compile units",
    )
    observations = units_document.get("nproc_observations")
    if (
        units_document.get("configured_jobs") != 8
        or not isinstance(observations, list)
        or not observations
        or any(item != "8" for item in observations)
        or units_document.get("nproc_observation_count") != len(observations)
    ):
        raise PipelineError("host-build telemetry job-count proof is invalid")
    raw_units = units_document.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise PipelineError("host-build telemetry compile-unit list is invalid")
    units: list[dict] = []
    unit_keys = {
        "kind",
        "source_path",
        "compiler",
        "command_sha256",
        "language",
        "target_abi",
        "result",
        "exit_code",
        "signal",
        "started_monotonic_ns",
        "finished_monotonic_ns",
        "elapsed_ns",
        "user_cpu_us",
        "system_cpu_us",
        "max_rss_bytes",
    }
    for raw_unit in raw_units:
        unit = _exact_document(raw_unit, unit_keys, "compile unit")
        if (
            unit.get("kind") not in {"compile", "link"}
            or unit.get("target_abi") != architecture
            or not isinstance(unit.get("compiler"), str)
            or not unit["compiler"]
            or not isinstance(unit.get("command_sha256"), str)
            or SHA256_PATTERN.fullmatch(unit["command_sha256"]) is None
        ):
            raise PipelineError("host-build telemetry compile-unit identity is invalid")
        if unit["kind"] == "compile":
            if (
                not isinstance(unit.get("source_path"), str)
                or not unit["source_path"]
                or unit["source_path"].startswith("/")
                or posixpath.normpath(unit["source_path"]) != unit["source_path"]
                or unit["source_path"] in {".", ".."}
                or unit["source_path"].startswith("../")
                or unit.get("language") not in {"c", "c++", "assembly", "rust"}
            ):
                raise PipelineError("host-build telemetry compile unit is invalid")
        elif unit.get("source_path") is not None or unit.get("language") != "link":
            raise PipelineError("host-build telemetry link unit is invalid")
        exit_code = _uint(unit.get("exit_code"), "unit exit code")
        signal_number = _uint(unit.get("signal"), "unit signal")
        expected_unit_result = (
            "passed" if exit_code == 0 and signal_number == 0 else "failed"
        )
        if (
            exit_code > 255
            or signal_number > 255
            or (signal_number and exit_code)
            or unit.get("result") != expected_unit_result
            or (require_complete and expected_unit_result != "passed")
        ):
            raise PipelineError("host-build telemetry compile-unit result is invalid")
        started = _uint(unit.get("started_monotonic_ns"), "unit start")
        finished = _uint(unit.get("finished_monotonic_ns"), "unit finish")
        elapsed = _uint(unit.get("elapsed_ns"), "unit elapsed")
        for name in ("user_cpu_us", "system_cpu_us", "max_rss_bytes"):
            _uint(unit.get(name), f"unit {name}")
        if (
            finished < started
            or elapsed != finished - started
            or started < build_phase["started_monotonic_ns"]
            or finished > build_phase["finished_monotonic_ns"]
        ):
            raise PipelineError("host-build telemetry compile-unit bounds are invalid")
        units.append(unit)
    if units != sorted(
        units,
        key=lambda item: (
            item["started_monotonic_ns"], item["kind"], item["source_path"] or ""
        ),
    ):
        raise PipelineError("host-build telemetry compile units are not canonical")
    compile_units = [item for item in units if item["kind"] == "compile"]
    link_units = [item for item in units if item["kind"] == "link"]
    if not compile_units or (require_complete and not link_units):
        raise PipelineError("host-build telemetry needs compile and link units")
    counts = {"c": 0, "c++": 0, "assembly": 0, "rust": 0, "link": len(link_units)}
    for unit in compile_units:
        counts[unit["language"]] += 1
    if units_document.get("counts") != counts:
        raise PipelineError("host-build telemetry language/unit counts are invalid")
    cpu_costs = [item["user_cpu_us"] + item["system_cpu_us"] for item in compile_units]
    expected_aggregate = {
        "method": "nearest-rank-v1",
        "p50_us": _nearest_rank(cpu_costs, 0.50),
        "p95_us": _nearest_rank(cpu_costs, 0.95),
        "max_us": max(cpu_costs),
        "total_us": sum(cpu_costs),
    }
    if units_document.get("compile_cpu_aggregate") != expected_aggregate:
        raise PipelineError("host-build telemetry CPU aggregate is invalid")
    longest = sorted(
        compile_units,
        key=lambda item: (-item["elapsed_ns"], item["source_path"]),
    )[:10]
    expected_longest = [
        {
            "source_path": item["source_path"],
            "elapsed_ns": item["elapsed_ns"],
            "cpu_us": item["user_cpu_us"] + item["system_cpu_us"],
        }
        for item in longest
    ]
    if units_document.get("longest_compile_units") != expected_longest:
        raise PipelineError("host-build telemetry longest-unit aggregate is invalid")
    expected_bounds = {
        "compile": {
            "started_monotonic_ns": min(
                item["started_monotonic_ns"] for item in compile_units
            ),
            "finished_monotonic_ns": max(
                item["finished_monotonic_ns"] for item in compile_units
            ),
        },
        **(
            {
                "link": {
                    "started_monotonic_ns": min(
                        item["started_monotonic_ns"] for item in link_units
                    ),
                    "finished_monotonic_ns": max(
                        item["finished_monotonic_ns"] for item in link_units
                    ),
                }
            }
            if link_units
            else {}
        ),
    }
    for bounds in expected_bounds.values():
        bounds["duration_ns"] = (
            bounds["finished_monotonic_ns"] - bounds["started_monotonic_ns"]
        )
    if units_document.get("phase_bounds") != expected_bounds:
        raise PipelineError("host-build telemetry unit phase bounds are invalid")
    expected_critical = sum(
        bounds["duration_ns"] for bounds in expected_bounds.values()
    )
    if units_document.get("estimated_critical_path_ns") != expected_critical:
        raise PipelineError("host-build telemetry estimated critical path is invalid")
    return units_document


def validate_sidecar_document(document: object, *, repository_root: Path) -> dict:
    """Validate every self-contained telemetry claim before external binding."""

    sidecar = _exact_document(
        document,
        {
            "$schema",
            "schema",
            "schema_version",
            "telemetry_contract",
            "run_id",
            "local_only",
            "publication",
            "runner",
            "execution_profile",
            "cache",
            "phases",
            "builds",
            "packages",
            "result",
            "content_sha256",
        },
        "sidecar",
    )
    if (
        sidecar.get("$schema") != TELEMETRY_SCHEMA_REFERENCE
        or sidecar.get("schema_version") != 1
        or type(sidecar.get("schema_version")) is not int
        or sidecar.get("telemetry_contract") != "host-build-telemetry-v1"
        or not isinstance(sidecar.get("run_id"), str)
        or not sidecar["run_id"]
        or sidecar.get("local_only") is not True
        or sidecar.get("publication") != "disabled"
        or sidecar.get("result") not in {"passed", "failed"}
    ):
        raise PipelineError("host-build telemetry sidecar header is invalid")
    schema_path = _validated_cas_reference(
        sidecar.get("schema"),
        repository_root=repository_root,
        namespace="schemas",
        label="host-build telemetry schema",
    )
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("host-build telemetry schema is unreadable") from exc
    if (
        not isinstance(schema, dict)
        or schema.get("$id")
        != "https://spruceui.local/schemas/host-build-telemetry.schema.json"
    ):
        raise PipelineError("host-build telemetry schema identity is invalid")
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError

        Draft202012Validator.check_schema(schema)
        validation_errors = sorted(
            Draft202012Validator(schema).iter_errors(sidecar),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except (ImportError, SchemaError) as exc:
        raise PipelineError("host-build telemetry schema validator is unavailable") from exc
    if validation_errors:
        first = validation_errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise PipelineError(
            f"host-build telemetry schema validation failed at {location}: "
            + first.message
        )
    runner = _exact_document(
        sidecar.get("runner"),
        {"selector", "profile", "mode", "backend", "execution_label"},
        "runner",
    )
    expected_runners = {
        "local": {
            "selector": "local",
            "profile": "local",
            "mode": "native",
            "backend": "local-docker",
            "execution_label": "host-local",
        },
        "github-actions-sim": {
            "selector": "github-actions-sim",
            "profile": "github-actions",
            "mode": "simulated",
            "backend": "local-docker",
            "execution_label": "local-gha-sim",
        },
    }
    if runner != expected_runners.get(runner.get("selector")):
        raise PipelineError("host-build telemetry runner identity is invalid")
    execution = _exact_document(
        sidecar.get("execution_profile"),
        {
            "path",
            "file_sha256",
            "content_sha256",
            "schema",
            "profile_id",
            "profile_content_sha256",
            "resource_class_id",
            "resource_class_content_sha256",
            "resources",
        },
        "execution profile",
    )
    resources = execution.get("resources")
    expected_resources = {
        "jobs": 8,
        "cpu_quota": 8,
        "memory_bytes": 4 * 1024**3,
        "memory_swap_bytes": 4 * 1024**3,
        "pids_limit": 1024,
        "matrix_parallelism": 1,
        "pair_execution": "selected-then-reproduction-sequential",
    }
    if resources != expected_resources:
        raise PipelineError("host-build telemetry execution resources are invalid")
    execution_schema = execution.get("schema")
    if not isinstance(execution_schema, dict):
        raise PipelineError("host-build telemetry profile schema reference is invalid")
    try:
        resolved_profile = resolve_host_execution_profile(
            runner["selector"],
            repository_root=repository_root,
            registry_path=repository_root / str(execution.get("path", "")),
            registry_schema_path=repository_root
            / str(execution_schema.get("path", "")),
        )
    except RunnerProfileError as exc:
        raise PipelineError("host-build telemetry profile snapshot is invalid") from exc
    if (
        execution != {**resolved_profile.reference(), "resources": resolved_profile.resources()}
        or runner
        != {
            "selector": resolved_profile.selector,
            **resolved_profile.runner_identity(),
            "execution_label": resolved_profile.execution_label,
        }
    ):
        raise PipelineError("host-build telemetry profile binding is invalid")
    expected_cache = {
        "classification": "cold",
        "scope": "pipeline-source-build-and-compiler-state",
        "identity": "fresh-container-network-clone-no-restored-compiler-cache-v1",
        "container_filesystem": "fresh",
        "source": "fresh-network-clone",
        "compiler": "disabled",
        "image_layers": "preloaded-content-addressed-image",
        "host_page_cache": "uncontrolled",
    }
    if sidecar.get("cache") != expected_cache:
        raise PipelineError("host-build telemetry cache contract is invalid")
    if sidecar["cache"] != resolved_profile.cache():
        raise PipelineError("host-build telemetry cache/profile binding is invalid")
    run_phases = _exact_document(
        sidecar.get("phases"), {"queue", "package"}, "run phases"
    )
    if run_phases.get("queue") != {
        "status": "not_applicable",
        "reason": "local-direct-execution-has-no-queue",
    }:
        raise PipelineError("host-build telemetry queue phase is invalid")
    _validate_measured_phase(run_phases.get("package"), "package", bounds=False)
    builds = sidecar.get("builds")
    if not isinstance(builds, list) or not builds:
        raise PipelineError("host-build telemetry build list is invalid")
    seen_targets: set[tuple[str, str]] = set()
    for value in builds:
        build = _exact_document(
            value,
            {
                "core_id",
                "architecture",
                "driver",
                "result",
                "bindings",
                "instrumentation",
                "phases",
                "container",
                "resources",
                "units",
            },
            "build",
        )
        if (
            not isinstance(build.get("core_id"), str)
            or not build["core_id"]
            or not isinstance(build.get("architecture"), str)
            or not build["architecture"]
            or build.get("driver") != "libretro-super"
            or build.get("result") not in {"passed", "failed"}
            or (build["core_id"], build["architecture"]) in seen_targets
        ):
            raise PipelineError("host-build telemetry build identity is invalid")
        seen_targets.add((build["core_id"], build["architecture"]))
        bindings = _exact_document(
            build.get("bindings"),
            {"build_record", "source", "recipe", "toolchain", "abi", "tuning", "outputs"},
            "build bindings",
        )
        _exact_document(
            bindings.get("build_record"), {"path", "file_sha256"}, "build-record binding"
        )
        for name in ("source", "recipe", "toolchain"):
            if not isinstance(bindings.get(name), dict):
                raise PipelineError(f"host-build telemetry {name} binding is invalid")
        _exact_document(
            bindings.get("abi"),
            {"architecture", "elf_class", "machine", "interpreter"},
            "ABI binding",
        )
        outputs = _exact_document(
            bindings.get("outputs"),
            {"artifact", "metadata", "build_log"},
            "output bindings",
        )
        _exact_document(outputs.get("artifact"), {"path", "sha256", "size"}, "artifact binding")
        _exact_document(outputs.get("metadata"), {"path", "sha256", "size"}, "metadata binding")
        log_binding = _exact_document(
            outputs.get("build_log"), {"path", "sha256"}, "log binding"
        )
        if (
            not isinstance(log_binding.get("path"), str)
            or not log_binding["path"]
            or not isinstance(log_binding.get("sha256"), str)
            or SHA256_PATTERN.fullmatch(log_binding["sha256"]) is None
        ):
            raise PipelineError("host-build telemetry log binding is invalid")
        for output_name in ("artifact", "metadata"):
            output = outputs[output_name]
            populated = all(
                value is not None
                for value in (output.get("path"), output.get("sha256"), output.get("size"))
            )
            if populated:
                if (
                    not isinstance(output["path"], str)
                    or not output["path"]
                    or not isinstance(output["sha256"], str)
                    or SHA256_PATTERN.fullmatch(output["sha256"]) is None
                    or type(output["size"]) is not int
                    or output["size"] < 0
                ):
                    raise PipelineError(
                        f"host-build telemetry {output_name} binding is invalid"
                    )
            elif build["result"] == "passed" or any(
                value is not None
                for value in (output.get("path"), output.get("sha256"), output.get("size"))
            ):
                raise PipelineError(
                    f"host-build telemetry {output_name} binding is incomplete"
                )
        instrumentation = _exact_document(
            build.get("instrumentation"), {"contract", "bootstrap"}, "instrumentation"
        )
        contract = validate_instrumentation_contract(
            instrumentation.get("contract"), repository_root=repository_root
        )
        bootstrap = _exact_document(
            instrumentation.get("bootstrap"),
            {
                "compiler_resolved_path",
                "compiler_version",
                "compile_argv",
                "unit_runner_binary_sha256",
            },
            "instrumentation bootstrap",
        )
        compiler_path = bootstrap.get("compiler_resolved_path")
        if (
            not isinstance(compiler_path, str)
            or not compiler_path.startswith("/")
            or not isinstance(bootstrap.get("compiler_version"), str)
            or not bootstrap["compiler_version"]
            or bootstrap.get("compile_argv")
            != [compiler_path, *UNIT_RUNNER_COMPILE_ARGUMENTS]
            or not isinstance(bootstrap.get("unit_runner_binary_sha256"), str)
            or SHA256_PATTERN.fullmatch(bootstrap["unit_runner_binary_sha256"])
            is None
        ):
            raise PipelineError("host-build telemetry bootstrap identity is invalid")
        phases = _exact_document(
            build.get("phases"),
            {"orchestration", "source_hydration", "configure", "build_command", "compile", "link", "validation"},
            "build phases",
        )
        _validate_measured_phase(phases.get("orchestration"), "orchestration", bounds=False)
        if (
            build["result"] == "failed"
            and isinstance(phases.get("source_hydration"), dict)
            and phases["source_hydration"].get("status") == "unavailable"
        ):
            hydration = _validate_unavailable(
                phases["source_hydration"],
                "source hydration",
                reason=FAILED_SOURCE_PHASE_REASON,
            )
        else:
            hydration = _validate_measured_phase(
                phases.get("source_hydration"), "source hydration", bounds=True
            )
        if phases.get("configure") != {
            "status": "not_applicable",
            "reason": "libretro-super-make-driver-has-no-separate-configure-phase",
        }:
            raise PipelineError("host-build telemetry configure phase is invalid")
        if (
            build["result"] == "failed"
            and isinstance(phases.get("build_command"), dict)
            and phases["build_command"].get("status") == "unavailable"
        ):
            build_phase = _validate_unavailable(
                phases["build_command"],
                "build command",
                reason=FAILED_BUILD_PHASE_REASON,
            )
        else:
            build_phase = _validate_measured_phase(
                phases.get("build_command"), "build command", bounds=True
            )
        _validate_measured_phase(phases.get("validation"), "validation", bounds=False)
        if (
            hydration.get("status") == "unavailable"
            and build_phase.get("status") != "unavailable"
        ):
            raise PipelineError("host-build telemetry build ran without source hydration")
        if (
            hydration.get("status") == "measured"
            and build_phase.get("status") == "measured"
            and hydration["finished_monotonic_ns"]
            > build_phase["started_monotonic_ns"]
        ):
            raise PipelineError("host-build telemetry phase ordering is invalid")
        units = _validate_unit_document(
            build.get("units"),
            architecture=build["architecture"],
            build_phase=build_phase,
            require_complete=build["result"] == "passed",
        )
        if units.get("status") == "unavailable":
            if build_phase.get("status") == "measured" and build["result"] != "failed":
                raise PipelineError("host-build telemetry unit availability is invalid")
            _validate_unavailable(
                phases.get("compile"), "compile", reason=FAILED_UNITS_REASON
            )
            _validate_unavailable(
                phases.get("link"), "link", reason=FAILED_UNITS_REASON
            )
        else:
            if build_phase.get("status") != "measured":
                raise PipelineError("host-build telemetry units lack a build phase")
            compile_phase = _validate_measured_phase(
                phases.get("compile"), "compile", bounds=True
            )
            if compile_phase != {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                **units["phase_bounds"]["compile"],
            }:
                raise PipelineError("host-build telemetry compile phase is invalid")
            if "link" in units["phase_bounds"]:
                link_phase = _validate_measured_phase(
                    phases.get("link"), "link", bounds=True
                )
                if link_phase != {
                    "status": "measured",
                    "clock": "CLOCK_MONOTONIC",
                    **units["phase_bounds"]["link"],
                }:
                    raise PipelineError("host-build telemetry link phase is invalid")
            else:
                if build["result"] != "failed":
                    raise PipelineError("passed host-build telemetry lacks link units")
                _validate_unavailable(
                    phases.get("link"), "link", reason=FAILED_LINK_REASON
                )
        resource_document = _validate_resource_document(build.get("resources"), resources)
        container = _exact_document(
            build.get("container"),
            {"container_id", "requested_host_config", "state", "execution_duration_ns"},
            "container",
        )
        if (
            not isinstance(container.get("container_id"), str)
            or CONTAINER_ID_PATTERN.fullmatch(container["container_id"]) is None
        ):
            raise PipelineError("host-build telemetry container ID is invalid")
        expected_host_config = {
            "AutoRemove": False,
            "NanoCpus": resources["cpu_quota"] * 1_000_000_000,
            "Memory": resources["memory_bytes"],
            "MemorySwap": resources["memory_swap_bytes"],
            "PidsLimit": resources["pids_limit"],
            "CgroupnsMode": "private",
        }
        if container.get("requested_host_config") != expected_host_config:
            raise PipelineError("host-build telemetry Docker HostConfig is invalid")
        state = _exact_document(
            container.get("state"),
            {"status", "oom_killed", "dead", "exit_code", "error", "started_at", "finished_at"},
            "container state",
        )
        if (
            state.get("status") != "exited"
            or type(state.get("oom_killed")) is not bool
            or state.get("dead") is not False
            or type(state.get("exit_code")) is not int
            or not 0 <= state["exit_code"] <= 255
            or not isinstance(state.get("error"), str)
            or not isinstance(state.get("started_at"), str)
            or not isinstance(state.get("finished_at"), str)
            or (build["result"] == "passed" and state["exit_code"] != 0)
            or (
                build["result"] == "passed"
                and (state["oom_killed"] or resource_document["oom_observed"])
            )
        ):
            raise PipelineError("host-build telemetry container result is invalid")
        _uint(container.get("execution_duration_ns"), "container duration")
        recipe_host = bindings["recipe"].get("host_execution")
        host_contract = validate_host_execution_contract(
            recipe_host, repository_root=repository_root
        )
        if (
            host_contract["resources"] != resources
            or host_contract["cache"] != sidecar["cache"]
            or host_contract["telemetry_schema"] != sidecar["schema"]
            or host_contract["instrumentation"] != contract
            or host_contract["resource_class"]
            != {
                "resource_class_id": execution.get("resource_class_id"),
                "content_sha256": execution.get("resource_class_content_sha256"),
            }
        ):
            raise PipelineError("host-build telemetry recipe/profile binding is invalid")
    packages = sidecar.get("packages")
    if not isinstance(packages, list) or not packages:
        raise PipelineError("host-build telemetry package list is invalid")
    for package in packages:
        if not isinstance(package, dict) or package.get("result") not in {
            "packaged",
            "not_packaged",
        }:
            raise PipelineError("host-build telemetry package entry is invalid")
        allowed_package_keys = {
            "core_id", "result", "path", "sha256", "size", "reason",
            "core_group", "tuning_candidate",
        }
        if (
            not isinstance(package.get("core_id"), str)
            or not package["core_id"]
            or not set(package).issubset(allowed_package_keys)
        ):
            raise PipelineError("host-build telemetry package identity is invalid")
        if package["result"] == "packaged":
            if (
                "reason" in package
                or not {"path", "sha256", "size"}.issubset(package)
                or not isinstance(package.get("path"), str)
                or not package["path"]
                or not isinstance(package.get("sha256"), str)
                or SHA256_PATTERN.fullmatch(package["sha256"]) is None
                or type(package.get("size")) is not int
                or package["size"] < 0
            ):
                raise PipelineError("host-build telemetry packaged output is invalid")
        elif (
            not isinstance(package.get("reason"), str)
            or not package["reason"]
            or any(
                key in package and package[key] is None
                for key in ("path", "sha256", "size")
            )
        ):
            raise PipelineError("host-build telemetry package failure is invalid")
    expected_result = (
        "passed"
        if all(item["result"] == "passed" for item in builds)
        and all(item["result"] == "packaged" for item in packages)
        else "failed"
    )
    if sidecar["result"] != expected_result:
        raise PipelineError("host-build telemetry aggregate result is invalid")
    if sidecar.get("content_sha256") != telemetry_content_sha256(sidecar):
        raise PipelineError("host-build telemetry content digest is invalid")
    return sidecar


def validate_sidecar_reference(reference: object, repository_root: Path) -> dict:
    if not isinstance(reference, dict) or set(reference) != {
        "path",
        "file_sha256",
        "content_sha256",
    }:
        raise PipelineError("host-build telemetry reference is malformed")
    for key in ("file_sha256", "content_sha256"):
        if (
            not isinstance(reference.get(key), str)
            or SHA256_PATTERN.fullmatch(reference[key]) is None
        ):
            raise PipelineError("host-build telemetry reference digest is invalid")
    path = _validated_cas_reference(
        {"path": reference.get("path"), "file_sha256": reference.get("file_sha256")},
        repository_root=repository_root,
        namespace="host-build-telemetry",
        label="host-build telemetry sidecar",
    )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PipelineError("host-build telemetry sidecar is unreadable") from exc
    if not isinstance(document, dict):
        raise PipelineError("host-build telemetry sidecar is not an object")
    if (
        document.get("content_sha256") != reference["content_sha256"]
        or document.get("content_sha256") != telemetry_content_sha256(document)
        or document.get("local_only") is not True
        or document.get("publication") != "disabled"
    ):
        raise PipelineError("host-build telemetry sidecar identity is invalid")
    return validate_sidecar_document(document, repository_root=repository_root)


__all__ = [
    "RAW_TELEMETRY_DIRECTORY",
    "TELEMETRY_FILENAME",
    "TOOL_WRAPPER_SOURCE",
    "UNIT_RUNNER_SOURCE",
    "TELEMETRY_SCHEMA_PATH",
    "UNIT_RUNNER_COMPILE_ARGUMENTS",
    "build_host_execution_contract",
    "build_sidecar_document",
    "execute_instrumented_container",
    "instrumentation_shell_prelude",
    "not_applicable_phase",
    "parse_measured_phase",
    "parse_bootstrap_evidence",
    "parse_unit_evidence",
    "phase_finish_shell",
    "phase_start_shell",
    "unavailable_observation",
    "telemetry_content_sha256",
    "validate_sidecar_reference",
    "validate_sidecar_document",
    "validate_host_execution_contract",
    "validate_instrumentation_contract",
    "validate_job_count_log",
    "write_sidecar",
]
