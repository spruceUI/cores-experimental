"""Shared exact C-only compiler/linker mechanics for CPC cores."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
import shlex

from ..errors import PipelineError
from .command_line import command_uses_response_file, normalized_log_path
from .compiler import (
    COMPILER_COMMAND_RE,
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)


CPC_MAKE_TRACE_RE = re.compile(
    r"^Makefile:(\d+): update target '([^']+)' due to: (.+)$"
)


@dataclass(frozen=True, slots=True)
class CpcMakeTraceContract:
    """Exact GNU Make trace details required by one core."""

    marker: str
    compile_makefile_line: str
    link_makefile_line: str


@dataclass(frozen=True, slots=True)
class CpcLogContract:
    """Per-core parameters consumed by the shared CPC proof engine."""

    core_id: str
    expected_c_compile_count: int
    build_artifact_name: str
    expected_link_options: tuple[str, ...]
    source_commit: str
    source_tree: str
    make_trace: CpcMakeTraceContract | None = None


def normalized_cpc_log_path(value: object, suffix: str) -> str | None:
    """Normalize a relative path from a CPC compiler log."""

    return normalized_log_path(value, suffix)


def cpc_command_uses_response_file(tokens: list[str]) -> bool:
    """Return whether an argv can hide inputs in a response file."""

    return command_uses_response_file(tokens)


def cpc_allowed_linker_forwarding(
    expected_link_options: tuple[str, ...],
) -> frozenset[str]:
    """Derive the only linker arguments permitted through ``-Wl,``."""

    return frozenset(
        token.removeprefix("-Wl,")
        for token in expected_link_options
        if token.startswith("-Wl,")
    )


def cpc_link_command_has_unsupported_forwarding_for(
    tokens: list[str], allowed_arguments: frozenset[str]
) -> bool:
    """Reject forwarded linker inputs outside one core's exact options."""

    for token in tokens[1:]:
        if token == "-Xlinker" or token.startswith(("-Xlinker=", "-Wl=")):
            return True
        if token.startswith("-Wl,"):
            forwarded_arguments = token.removeprefix("-Wl,").split(",")
            if not forwarded_arguments or any(
                argument not in allowed_arguments
                for argument in forwarded_arguments
            ):
                return True
    return False


def cpc_compile_command_pair(
    tokens: list[str], expected_c_compilers: set[str]
) -> tuple[str, str] | None:
    """Parse one exact C compile command into its output/source pair."""

    if not tokens or tokens[0] not in expected_c_compilers:
        return None
    if (
        tokens.count("-c") != 1
        or tokens.count("-o") != 1
        or any(token.startswith("-o") and token != "-o" for token in tokens[1:])
        or cpc_command_uses_response_file(tokens)
        or "--" in tokens[1:]
        or any(token == "-x" or token.startswith("-x") for token in tokens[1:])
    ):
        return None
    output_index = tokens.index("-o") + 1
    if output_index >= len(tokens):
        return None
    output = normalized_cpc_log_path(tokens[output_index], ".o")
    if output is None:
        return None
    operands = [
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index != output_index
        and token not in {"-c", "-o"}
        and not token.startswith("-")
    ]
    if len(operands) != 1:
        return None
    source = normalized_cpc_log_path(operands[0], ".c")
    if source is None or source != output.removesuffix(".o") + ".c":
        return None
    return output, source


def cpc_link_command_objects_for(
    tokens: list[str],
    expected_c_compilers: set[str],
    artifact_name: str,
    expected_link_options: tuple[str, ...],
    allowed_linker_forwarding: frozenset[str] | None = None,
) -> Counter[str] | None:
    """Parse an exact CPC link command into its object multiset."""

    if not tokens or tokens[0] not in expected_c_compilers:
        return None
    allowed_forwarding = (
        cpc_allowed_linker_forwarding(expected_link_options)
        if allowed_linker_forwarding is None
        else allowed_linker_forwarding
    )
    if (
        "-c" in tokens
        or tokens.count("-o") != 1
        or any(token.startswith("-o") and token != "-o" for token in tokens[1:])
        or cpc_command_uses_response_file(tokens)
        or cpc_link_command_has_unsupported_forwarding_for(
            tokens, allowed_forwarding
        )
        or "--" in tokens[1:]
        or any(token == "-x" or token.startswith("-x") for token in tokens[1:])
    ):
        return None
    output_index = tokens.index("-o") + 1
    if output_index >= len(tokens) or tokens[output_index] != artifact_name:
        return None
    observed_options = Counter(
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index != output_index and token != "-o" and token.startswith("-")
    )
    if observed_options != Counter(expected_link_options):
        return None
    operands = [
        token
        for index, token in enumerate(tokens[1:], start=1)
        if index != output_index and token != "-o" and not token.startswith("-")
    ]
    objects: list[str] = []
    for operand in operands:
        normalized = normalized_cpc_log_path(operand, ".o")
        if normalized is None:
            return None
        objects.append(normalized)
    return Counter(objects) if objects else None


def cpc_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
    contract: CpcLogContract,
) -> bool:
    """Prove one exact CPC core compile, link, and optional trace contract."""

    if not isinstance(core_id, str) or core_id != contract.core_id:
        return False
    if (
        source_commit != contract.source_commit
        or source_tree != contract.source_tree
    ):
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    lines = build_log_text.splitlines()
    marker_lines = [
        line for line in lines if line.startswith("CORE_PIPELINE_MAKE_TRACE|")
    ]
    trace_contract = contract.make_trace
    if trace_contract is not None:
        if marker_lines != [trace_contract.marker]:
            return False
        marker_position = lines.index(trace_contract.marker)
    else:
        if marker_lines:
            return False
        marker_position = -1
    expected_c_compilers = expected_compilers - expected_cxx_compilers
    first_build_line: int | None = None
    compile_pairs: Counter[tuple[str, str]] = Counter()
    link_objects: Counter[str] | None = None
    trace_pairs: Counter[tuple[str, str]] = Counter()
    link_trace_objects: Counter[str] | None = None
    for line_number, line in enumerate(lines):
        trace_match = CPC_MAKE_TRACE_RE.fullmatch(line)
        if trace_match is not None:
            if trace_contract is None:
                return False
            if first_build_line is None:
                first_build_line = line_number
            makefile_line, raw_target, reason = trace_match.groups()
            if (
                makefile_line == trace_contract.link_makefile_line
                and raw_target == contract.build_artifact_name
            ):
                if link_trace_objects is not None:
                    return False
                traced_objects: list[str] = []
                for raw_object in reason.split():
                    normalized = normalized_cpc_log_path(raw_object, ".o")
                    if normalized is None:
                        return False
                    traced_objects.append(normalized)
                if not traced_objects:
                    return False
                link_trace_objects = Counter(traced_objects)
                continue
            if makefile_line != trace_contract.compile_makefile_line:
                return False
            target = normalized_cpc_log_path(raw_target, ".o")
            if target is None:
                return False
            expected_source = target.removesuffix(".o") + ".c"
            source = (
                expected_source
                if reason == "target does not exist"
                else normalized_cpc_log_path(reason, ".c")
            )
            if source != expected_source:
                return False
            trace_pairs[(target, source)] += 1
            continue
        if line.startswith("Makefile:") and "update target" in line:
            return False
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        if not tokens:
            continue
        compiler = tokens[0]
        is_compile_candidate = "-c" in tokens
        is_link_candidate = "-c" not in tokens and "-o" in tokens
        if not is_compile_candidate and not is_link_candidate:
            if compiler in expected_compilers:
                return False
            continue
        if (
            COMPILER_COMMAND_RE.fullmatch(compiler) is None
            or compiler not in expected_c_compilers
        ):
            return False
        if first_build_line is None:
            first_build_line = line_number
        if is_compile_candidate:
            pair = cpc_compile_command_pair(tokens, expected_c_compilers)
            if pair is None:
                return False
            compile_pairs[pair] += 1
            continue
        if link_objects is not None:
            return False
        link_objects = cpc_link_command_objects_for(
            tokens,
            expected_c_compilers,
            contract.build_artifact_name,
            contract.expected_link_options,
        )
        if link_objects is None:
            return False
    compile_objects = Counter(
        {output: count for (output, _), count in compile_pairs.items()}
    )
    common_contract = bool(
        first_build_line is not None
        and len(compile_pairs) == contract.expected_c_compile_count
        and sum(compile_pairs.values()) == contract.expected_c_compile_count
        and all(count == 1 for count in compile_pairs.values())
        and link_objects == compile_objects
    )
    if trace_contract is None:
        return common_contract
    return bool(
        common_contract
        and marker_position < first_build_line
        and trace_pairs == compile_pairs
        and len(trace_pairs) == contract.expected_c_compile_count
        and link_trace_objects == compile_objects
    )
