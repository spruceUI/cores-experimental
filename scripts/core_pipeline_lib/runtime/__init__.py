"""Runner-profile resolution for local and GitHub Actions execution.

Runner profiles describe where the shared build implementation is running.
They are deliberately separate from the device execution profiles that
describe where a compiled core may eventually run.
"""

from .errors import RunnerProfileError
from .execution import (
    HOST_EXECUTION_PROFILE_PATH,
    HOST_EXECUTION_PROFILE_SCHEMA_PATH,
    HostExecutionProfile,
    resolve_host_execution_profile,
)
from .model import RunnerContext, RunnerRequest
from .resolve import resolve_runner_context
from .evidence import (
    base_runner_evidence,
    runner_evidence,
    runner_evidence_is_hardened,
    runner_evidence_is_well_formed,
)
from .telemetry import (
    RAW_TELEMETRY_DIRECTORY,
    TELEMETRY_SCHEMA_PATH,
    TOOL_WRAPPER_SOURCE,
    UNIT_RUNNER_COMPILE_ARGUMENTS,
    UNIT_RUNNER_SOURCE,
    build_host_execution_contract,
    build_sidecar_document,
    execute_instrumented_container,
    instrumentation_shell_prelude,
    not_applicable_phase,
    parse_bootstrap_evidence,
    parse_measured_phase,
    parse_unit_evidence,
    phase_finish_shell,
    phase_start_shell,
    unavailable_observation,
    validate_host_execution_contract,
    validate_instrumentation_contract,
    validate_job_count_log,
    validate_sidecar_reference,
    validate_sidecar_document,
    write_sidecar,
)

__all__ = [
    "RunnerContext",
    "HOST_EXECUTION_PROFILE_PATH",
    "HOST_EXECUTION_PROFILE_SCHEMA_PATH",
    "HostExecutionProfile",
    "RunnerProfileError",
    "RunnerRequest",
    "resolve_runner_context",
    "resolve_host_execution_profile",
    "runner_evidence",
    "runner_evidence_is_hardened",
    "runner_evidence_is_well_formed",
    "base_runner_evidence",
    "build_sidecar_document",
    "build_host_execution_contract",
    "TELEMETRY_SCHEMA_PATH",
    "RAW_TELEMETRY_DIRECTORY",
    "TOOL_WRAPPER_SOURCE",
    "UNIT_RUNNER_COMPILE_ARGUMENTS",
    "UNIT_RUNNER_SOURCE",
    "execute_instrumented_container",
    "instrumentation_shell_prelude",
    "not_applicable_phase",
    "parse_bootstrap_evidence",
    "parse_measured_phase",
    "parse_unit_evidence",
    "phase_finish_shell",
    "phase_start_shell",
    "unavailable_observation",
    "validate_host_execution_contract",
    "validate_instrumentation_contract",
    "validate_job_count_log",
    "validate_sidecar_reference",
    "validate_sidecar_document",
    "write_sidecar",
]
