"""Fail-closed audit for publication-disabled release orchestration workflows.

The audit deliberately has no runtime YAML dependency. Canonical byte hashes
close the executable configuration over the reviewed files, while a lexical
projection supplies specific diagnostics for common unsafe mutations. Any
syntax, alias, tag, duplicate key, unknown field, step, or command change also
changes the required byte identity and therefore fails closed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re
import stat
from typing import Any


SCHEMA_VERSION = 1
PUBLICATION = "disabled"
MAX_WORKFLOW_BYTES = 256 * 1024
MAX_PARALLEL = 8

COORDINATOR_PATH = Path(".github/workflows/release-candidate.yml")
WORKER_PATH = Path(".github/workflows/_build-one-core.yml")
WORKER_REFERENCE = "./.github/workflows/_build-one-core.yml"
EXPECTED_WORKFLOW_SHA256 = {
    "coordinator": "f621bb5c002728c8f23aabf9ae426ca71a074c819fbdd3d4e398a8c605625df3",
    "worker": "cf12caba053e99521cf173255b78e04fe50968b0172359c3b3025ee3bdbfd5b6",
}

APPROVED_ACTION_REVISIONS = {
    "actions/checkout": "34e114876b0b11c390a56381ad16ebd13914f8d5",
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
}
ALLOWED_ACTIONS = frozenset(APPROVED_ACTION_REVISIONS)
EXPECTED_ACTION_COUNTS = {
    "coordinator": Counter(
        {
            "actions/checkout": 2,
            "actions/download-artifact": 2,
            "actions/upload-artifact": 2,
            WORKER_REFERENCE: 1,
        }
    ),
    "worker": Counter(
        {
            "actions/checkout": 1,
            "actions/download-artifact": 1,
            "actions/upload-artifact": 2,
        }
    ),
}
WORKER_INPUTS = frozenset(
    {
        "candidate_id",
        "core_id",
        "plan_artifact_name",
        "result_artifact_prefix",
    }
)

USES_RE = re.compile(
    r"(?m)^[ \t]*(?:-[ \t]+)?uses:[ \t]*([^#\r\n]+?)[ \t]*(?:#.*)?$"
)
PINNED_ACTION_RE = re.compile(
    r"(?P<action>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(?P<revision>[0-9a-f]{40})"
)
MAPPING_LINE_RE = re.compile(r"([A-Za-z0-9_-]+):(?:[ \t]*(.*))?")
COMMANDS = {
    "plan-release": re.compile(
        r"(?<![A-Za-z0-9_.-])python3\s+scripts/core_pipeline\.py\s+plan-release(?=\s|$)"
    ),
    "release-matrix": re.compile(
        r"(?<![A-Za-z0-9_.-])python3\s+scripts/core_pipeline\.py\s+release-matrix(?=\s|$)"
    ),
    "seal-release": re.compile(
        r"(?<![A-Za-z0-9_.-])python3\s+scripts/core_pipeline\.py\s+seal-release(?=\s|$)"
    ),
    "build-core": re.compile(
        r"(?<![A-Za-z0-9_.-])python3\s+scripts/core_pipeline\.py\s+build-core(?=\s|$)"
    ),
    "record-release-result": re.compile(
        r"(?<![A-Za-z0-9_.-])python3\s+scripts/core_pipeline\.py\s+record-release-result(?=\s|$)"
    ),
}

FORBIDDEN_TRIGGERS = frozenset(
    {
        "branch_protection_rule",
        "check_run",
        "create",
        "delete",
        "deployment",
        "deployment_status",
        "issue_comment",
        "issues",
        "pull_request",
        "pull_request_target",
        "push",
        "repository_dispatch",
        "schedule",
        "workflow_run",
    }
)
FORBIDDEN_TEXT_PATTERNS = (
    (re.compile(r"(?im)^\s*permissions:\s*write-all\s*$"), "write-all permission"),
    (
        re.compile(
            r"(?im)^\s*(?:actions|checks|contents|deployments|id-token|issues|"
            r"packages|pages|pull-requests|security-events|statuses):\s*write\s*$"
        ),
        "write permission",
    ),
    (re.compile(r"(?i)secrets\s*:\s*inherit"), "inherited secrets"),
    (re.compile(r"\$\{\{\s*secrets\."), "secret expression"),
    (re.compile(r"(?im)^\s*continue-on-error\s*:\s*true\s*$"), "continue-on-error"),
    (re.compile(r"\|\|\s*(?:true|echo\s+['\"]?::warning::)"), "masked failure"),
)
FORBIDDEN_PUBLICATION_PATTERNS = (
    re.compile(r"(?i)\bgh\s+release\s+(?:create|delete|edit|upload)\b"),
    re.compile(r"(?i)\bgit\s+push\b"),
    re.compile(r"(?i)\bdocker\s+push\b"),
    re.compile(r"(?i)\b(?:npm|cargo)\s+publish\b"),
    re.compile(r"(?i)\btwine\s+upload\b"),
    re.compile(r"(?i)\b(?:update-channel|promote-release|publish-release)\b"),
    re.compile(r"(?i)softprops/action-gh-release|actions/create-release"),
)
UNSAFE_SCRIPT_PATTERNS = (
    (re.compile(r"(?m)(?:^|[;&|]\s*)eval(?:\s|$)"), "eval"),
    (re.compile(r"(?m)(?:^|[;&|]\s*)(?:ba)?sh\s+-c(?:\s|$)"), "shell -c"),
    (re.compile(r"(?m)(?:^|[;&|]\s*)sudo(?:\s|$)"), "sudo"),
    (re.compile(r"(?m)\brm\s+-[^\n]*r"), "recursive removal"),
    (re.compile(r"(?m)\bgit\s+(?:clean|reset)\b"), "destructive Git command"),
    (
        re.compile(r"(?m)\b(?:curl|wget)\b[^\n|]*\|\s*(?:ba)?sh\b"),
        "download piped to shell",
    ),
    (re.compile(r"`[^`]+`"), "backtick command substitution"),
)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _one_block(
    lines: list[str],
    name: str,
    indentation: int,
    errors: list[str],
    label: str,
) -> list[str] | None:
    prefix = " " * indentation + name + ":"
    matches = [index for index, line in enumerate(lines) if line == prefix]
    if len(matches) != 1:
        errors.append(f"{label} must occur exactly once")
        return None
    start = matches[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and _indent(line) <= indentation:
            end = index
            break
    return lines[start + 1 : end]


def _direct_mapping(lines: list[str], indentation: int) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        if not line.strip() or _indent(line) != indentation:
            continue
        match = MAPPING_LINE_RE.fullmatch(line.strip())
        if match is not None:
            result[match.group(1)] = (match.group(2) or "").strip()
    return result


def _sequence_values(lines: list[str], indentation: int) -> list[str]:
    prefix = " " * indentation + "- "
    return [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]


def _command_count(text: str, command: str) -> int:
    return len(COMMANDS[command].findall(text))


def _run_scripts(lines: list[str]) -> list[str]:
    scripts: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^( *)(?:-[ ]+)?run:\s*(.*)$", line)
        if match is None:
            index += 1
            continue
        indentation = len(match.group(1))
        scalar = match.group(2).strip()
        if scalar not in {"|", "|-", ">", ">-"}:
            scripts.append(scalar)
            index += 1
            continue
        collected: list[str] = []
        index += 1
        while index < len(lines):
            child = lines[index]
            if child.strip() and _indent(child) <= indentation:
                break
            collected.append(child)
            index += 1
        scripts.append("\n".join(collected))
    return scripts


def _action_blocks(lines: list[str], action: str) -> list[list[str]]:
    result: list[list[str]] = []
    for index, line in enumerate(lines):
        step = re.match(r"^( *)-[ ]+", line)
        if step is None:
            continue
        indentation = len(step.group(1))
        end = len(lines)
        for child_index in range(index + 1, len(lines)):
            child = lines[child_index]
            if child.strip() and _indent(child) <= indentation:
                end = child_index
                break
        block = lines[index:end]
        action_values = []
        for child in block:
            match = re.match(r"^\s*(?:-[ ]+)?uses:\s*([^#\s]+)", child)
            if match is not None:
                action_values.append(match.group(1).split("@", 1)[0])
        if action_values == [action]:
            result.append(block)
    return result


def _action_options(block: list[str]) -> dict[str, str]:
    if not block:
        return {}
    action_indent = _indent(block[0])
    with_lines = _one_block(block, "with", action_indent + 2, [], "with")
    if with_lines is None:
        return {}
    return _direct_mapping(with_lines, action_indent + 4)


def _record(relative_path: Path) -> dict[str, Any]:
    return {
        "path": relative_path.as_posix(),
        "status": "invalid",
        "file_sha256": None,
        "size": None,
        "uses": [],
        "max_parallel": None,
        "errors": [],
    }


def _read_workflow(
    repository_root: Path,
    relative_path: Path,
    record: dict[str, Any],
) -> str | None:
    errors = record["errors"]
    current = repository_root
    try:
        root_stat = current.lstat()
    except OSError as exc:
        errors.append(f"repository root is unavailable: {exc}")
        return None
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        errors.append("repository root must be a non-symlink directory")
        return None

    for index, part in enumerate(relative_path.parts):
        current = current / part
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            errors.append(f"workflow path is missing: {relative_path.as_posix()}")
            return None
        except OSError as exc:
            errors.append(f"cannot inspect workflow path: {exc}")
            return None
        if stat.S_ISLNK(current_stat.st_mode):
            errors.append(f"workflow path traverses a symlink: {current}")
            return None
        is_final = index == len(relative_path.parts) - 1
        expected_type = stat.S_ISREG if is_final else stat.S_ISDIR
        if not expected_type(current_stat.st_mode):
            kind = "regular file" if is_final else "directory"
            errors.append(f"workflow path component must be a {kind}: {current}")
            return None

    try:
        raw = current.read_bytes()
    except OSError as exc:
        errors.append(f"cannot read workflow: {exc}")
        return None
    record["size"] = len(raw)
    record["file_sha256"] = hashlib.sha256(raw).hexdigest()
    if not raw or len(raw) > MAX_WORKFLOW_BYTES:
        errors.append(
            f"workflow size must be between 1 and {MAX_WORKFLOW_BYTES} bytes"
        )
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("workflow must be valid UTF-8")
        return None
    if "\x00" in text:
        errors.append("workflow must not contain NUL bytes")
        return None
    if not text.endswith("\n"):
        errors.append("workflow must end with a newline")
    return text


def _audit_permissions_and_triggers(
    text: str,
    *,
    role: str,
    lines: list[str],
    errors: list[str],
) -> None:
    permissions = _one_block(lines, "permissions", 0, errors, "permissions block")
    if permissions is not None and _direct_mapping(permissions, 2) != {
        "contents": "read"
    }:
        errors.append("permissions must be exactly contents: read")
    if len([line for line in lines if line.lstrip().startswith("permissions:")]) != 1:
        errors.append("job-level or duplicate permissions are forbidden")

    on_block = _one_block(lines, "on", 0, errors, "on block")
    expected_trigger = "workflow_dispatch" if role == "coordinator" else "workflow_call"
    if on_block is not None:
        triggers = set(_direct_mapping(on_block, 2))
        if triggers != {expected_trigger}:
            errors.append(f"trigger must be exactly {expected_trigger}")
        forbidden = sorted(triggers & FORBIDDEN_TRIGGERS)
        if forbidden:
            errors.append("forbidden triggers: " + ", ".join(forbidden))

    for pattern, label in FORBIDDEN_TEXT_PATTERNS:
        if pattern.search(text):
            errors.append(f"unsafe workflow contract contains {label}")
    for pattern in FORBIDDEN_PUBLICATION_PATTERNS:
        if pattern.search(text):
            errors.append("publication or deployment command is forbidden")
            break
    for script in _run_scripts(lines):
        if "${{" in script:
            errors.append("run scripts must not interpolate Actions expressions")
        for pattern, label in UNSAFE_SCRIPT_PATTERNS:
            if pattern.search(script):
                errors.append(f"unsafe run script contains {label}")


def _input_contract(
    lines: list[str],
    name: str,
    errors: list[str],
) -> dict[str, str]:
    input_block = _one_block(lines, name, 6, errors, f"input {name}")
    return _direct_mapping(input_block or [], 8)


def _audit_worker_inputs(
    lines: list[str],
    *,
    errors: list[str],
) -> None:
    inputs = _one_block(lines, "inputs", 4, errors, "workflow inputs block")
    if inputs is None:
        return
    names = set(_direct_mapping(inputs, 6))
    if names != WORKER_INPUTS:
        errors.append(
            "workflow inputs must be exactly: "
            + ", ".join(sorted(WORKER_INPUTS))
        )
    for name in sorted(WORKER_INPUTS & names):
        contract = _input_contract(lines, name, errors)
        if contract.get("required") != "true" or contract.get("type") != "string":
            errors.append(f"input {name} must be a required string")
        if set(contract) - {"description", "required", "type"}:
            errors.append(f"input {name} has unsupported fields")


def _audit_coordinator_inputs(lines: list[str], errors: list[str]) -> None:
    inputs = _one_block(lines, "inputs", 4, errors, "workflow inputs block")
    if inputs is None:
        return
    expected = frozenset({"candidate_label", "scope"})
    names = set(_direct_mapping(inputs, 6))
    if names != expected:
        errors.append("coordinator inputs must be exactly candidate_label and scope")

    if "candidate_label" in names:
        candidate = _input_contract(lines, "candidate_label", errors)
        if candidate.get("required") != "true" or candidate.get("type") != "string":
            errors.append("candidate_label input must be a required string")
        if set(candidate) - {"description", "required", "type"}:
            errors.append("candidate_label input has unsupported fields")

    if "scope" in names:
        scope = _input_contract(lines, "scope", errors)
        if (
            scope.get("required") != "true"
            or scope.get("type") != "choice"
            or scope.get("default") != "canonical"
        ):
            errors.append("scope input must be a required choice defaulting to canonical")
        if set(scope) - {"description", "required", "type", "default", "options"}:
            errors.append("scope input has unsupported fields")
        options = _one_block(lines, "options", 8, errors, "scope options")
        if _sequence_values(options or [], 10) != [
            "canonical",
            "full-workflow-roster",
        ]:
            errors.append("scope choices must be canonical and full-workflow-roster")


def _audit_uses(
    text: str,
    *,
    role: str,
    record: dict[str, Any],
) -> None:
    errors = record["errors"]
    values = [match.group(1).strip() for match in USES_RE.finditer(text)]
    record["uses"] = values
    action_counts: Counter[str] = Counter()
    revisions: dict[str, set[str]] = defaultdict(set)
    for value in values:
        if value.startswith("./"):
            action_counts[value] += 1
            if role != "coordinator" or value != WORKER_REFERENCE:
                errors.append(f"unapproved local reusable workflow: {value}")
            continue
        match = PINNED_ACTION_RE.fullmatch(value)
        if match is None:
            errors.append(f"action must use an exact 40-character commit: {value}")
            continue
        action = match.group("action")
        revision = match.group("revision")
        action_counts[action] += 1
        revisions[action].add(revision)
        if action not in ALLOWED_ACTIONS:
            errors.append(f"unapproved action: {action}")
        elif revision != APPROVED_ACTION_REVISIONS[action]:
            errors.append(f"{action} must use its exact reviewed revision")
    for action, action_revisions in sorted(revisions.items()):
        if len(action_revisions) != 1:
            errors.append(f"{action} must use one exact revision throughout")
    expected = EXPECTED_ACTION_COUNTS[role]
    if action_counts != expected:
        errors.append(
            "action inventory is not exact: expected "
            + repr(dict(sorted(expected.items())))
            + ", got "
            + repr(dict(sorted(action_counts.items())))
        )


def _require_action_options(
    lines: list[str],
    action: str,
    *,
    count: int,
    errors: list[str],
) -> list[dict[str, str]]:
    blocks = _action_blocks(lines, action)
    if len(blocks) != count:
        errors.append(f"{action} must have exactly {count} step(s)")
    return [_action_options(block) for block in blocks]


def _audit_action_safety(
    lines: list[str],
    *,
    role: str,
    errors: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    checkout_count = 2 if role == "coordinator" else 1
    checkout_options = _require_action_options(
        lines, "actions/checkout", count=checkout_count, errors=errors
    )
    for options in checkout_options:
        if options.get("persist-credentials") != "false":
            errors.append("checkout must set persist-credentials: false")

    upload_count = 2
    uploads = _require_action_options(
        lines, "actions/upload-artifact", count=upload_count, errors=errors
    )
    for options in uploads:
        if options.get("include-hidden-files") != "true":
            errors.append("artifact uploads must include hidden files")

    download_count = 2 if role == "coordinator" else 1
    downloads = _require_action_options(
        lines, "actions/download-artifact", count=download_count, errors=errors
    )
    return uploads, downloads


def _audit_coordinator(text: str, record: dict[str, Any]) -> None:
    errors = record["errors"]
    lines = text.splitlines()
    _audit_permissions_and_triggers(
        text, role="coordinator", lines=lines, errors=errors
    )
    _audit_coordinator_inputs(lines, errors)
    _audit_uses(text, role="coordinator", record=record)
    uploads, downloads = _audit_action_safety(
        lines, role="coordinator", errors=errors
    )

    jobs = _one_block(lines, "jobs", 0, errors, "jobs block")
    if jobs is not None and set(_direct_mapping(jobs, 2)) != {"plan", "build", "seal"}:
        errors.append("coordinator jobs must be exactly plan, build, and seal")
    plan = _one_block(lines, "plan", 2, errors, "plan job")
    build = _one_block(lines, "build", 2, errors, "build job")
    seal = _one_block(lines, "seal", 2, errors, "seal job")

    plan_text = "\n".join(plan or [])
    plan_environment = _one_block(plan or [], "env", 4, errors, "plan environment")
    if _direct_mapping(plan_environment or [], 6) != {
        "CANDIDATE_ID": (
            "${{ inputs.candidate_label }}-${{ github.run_id }}-"
            "${{ github.run_attempt }}"
        ),
        "PLAN_PATH": (
            ".local-e2e/release-plans/${{ inputs.candidate_label }}-"
            "${{ github.run_id }}-${{ github.run_attempt }}.json"
        ),
        "PLAN_ARTIFACT": "release-plan-${{ github.run_id }}-${{ github.run_attempt }}",
        "RESULT_ARTIFACT_PREFIX": (
            "release-result-${{ github.run_id }}-${{ github.run_attempt }}"
        ),
    }:
        errors.append("plan environment bindings are not exact")
    scope_environment = _one_block(
        plan or [], "env", 8, errors, "plan-release environment"
    )
    if _direct_mapping(scope_environment or [], 10) != {
        "RELEASE_SCOPE": "${{ inputs.scope }}"
    }:
        errors.append("plan-release scope binding is not exact")
    plan_outputs = _one_block(plan or [], "outputs", 4, errors, "plan outputs")
    if _direct_mapping(plan_outputs or [], 6) != {
        "candidate_id": "${{ steps.matrix.outputs.candidate_id }}",
        "matrix": "${{ steps.matrix.outputs.matrix }}",
        "plan_artifact_name": "${{ steps.matrix.outputs.plan_artifact_name }}",
        "result_artifact_prefix": "${{ steps.matrix.outputs.result_artifact_prefix }}",
    }:
        errors.append("plan job outputs are not exact")
    if _command_count(plan_text, "plan-release") != 1:
        errors.append("plan job must invoke plan-release exactly once")
    if not re.search(r'--scope\s+"\$RELEASE_SCOPE"(?=\s|$)', plan_text):
        errors.append("plan-release must select the validated scope input")
    if _command_count(plan_text, "release-matrix") != 1:
        errors.append("plan job must invoke release-matrix exactly once")
    if "$GITHUB_OUTPUT" not in plan_text:
        errors.append("plan job must expose the release matrix through GITHUB_OUTPUT")

    build_text = "\n".join(build or [])
    if build_text.count(f"uses: {WORKER_REFERENCE}") != 1:
        errors.append("build matrix must call the reusable worker exactly once")
    strategy = _one_block(lines, "strategy", 4, errors, "build strategy")
    strategy_values = _direct_mapping(strategy or [], 6)
    if strategy_values.get("fail-fast") != "false":
        errors.append("build matrix must set fail-fast: false")
    max_parallel_text = strategy_values.get("max-parallel")
    if max_parallel_text is None or not max_parallel_text.isdecimal():
        errors.append("build matrix max-parallel must be a decimal integer")
    else:
        max_parallel = int(max_parallel_text)
        record["max_parallel"] = max_parallel
        if not 1 <= max_parallel <= MAX_PARALLEL:
            errors.append(f"build matrix max-parallel must be between 1 and {MAX_PARALLEL}")
    if strategy_values.get("matrix") != "${{ fromJSON(needs.plan.outputs.matrix) }}":
        errors.append("build matrix must come exactly from the plan job")
    build_values = _direct_mapping(build or [], 4)
    if build_values.get("needs") != "plan":
        errors.append("build matrix must depend on the plan job")
    worker_inputs = _one_block(lines, "with", 4, errors, "reusable worker inputs")
    expected_worker_inputs = {
        "candidate_id": "${{ needs.plan.outputs.candidate_id }}",
        "core_id": "${{ matrix.core_id }}",
        "plan_artifact_name": "${{ needs.plan.outputs.plan_artifact_name }}",
        "result_artifact_prefix": "${{ needs.plan.outputs.result_artifact_prefix }}",
    }
    if _direct_mapping(worker_inputs or [], 6) != expected_worker_inputs:
        errors.append("reusable worker input bindings are not exact")

    seal_text = "\n".join(seal or [])
    seal_environment = _one_block(seal or [], "env", 4, errors, "seal environment")
    if _direct_mapping(seal_environment or [], 6) != {
        "CANDIDATE_ID": "${{ needs.plan.outputs.candidate_id }}",
        "PLAN_PATH": (
            ".local-e2e/release-plans/${{ needs.plan.outputs.candidate_id }}.json"
        ),
        "RESULT_ROOT": (
            ".local-e2e/release-results/"
            "${{ needs.plan.outputs.candidate_id }}/github-actions"
        ),
        "CANDIDATE_ROOT": (
            ".local-e2e/release-candidates/"
            "${{ needs.plan.outputs.candidate_id }}/github-actions"
        ),
    }:
        errors.append("seal environment bindings are not exact")
    if _command_count(seal_text, "seal-release") != 1:
        errors.append("seal job must invoke seal-release exactly once")
    if not re.search(r"--runner-profile\s+github-actions(?=\s|$)", seal_text):
        errors.append("seal-release must select the native github-actions runner")
    seal_needs = _one_block(seal or [], "needs", 4, errors, "seal dependencies")
    if _sequence_values(seal_needs or [], 6) != ["plan", "build"]:
        errors.append("seal job must depend on plan and build")

    upload_paths = {options.get("path") for options in uploads}
    if upload_paths != {
        "${{ env.PLAN_PATH }}",
        "${{ env.CANDIDATE_ROOT }}/",
    }:
        errors.append("coordinator artifact upload paths are not exact")
    if any(options.get("if-no-files-found") != "error" for options in uploads):
        errors.append("coordinator artifact uploads must fail when files are absent")
    plan_downloads = [options for options in downloads if "name" in options]
    result_downloads = [options for options in downloads if "pattern" in options]
    if len(plan_downloads) != 1 or plan_downloads[0].get("path") != (
        ".local-e2e/release-plans"
    ):
        errors.append("coordinator must download the exact plan artifact")
    if (
        len(result_downloads) != 1
        or result_downloads[0].get("path") != "${{ env.RESULT_ROOT }}"
        or result_downloads[0].get("merge-multiple") != "true"
        or result_downloads[0].get("pattern")
        != "${{ needs.plan.outputs.result_artifact_prefix }}-*"
    ):
        errors.append("coordinator result fan-in layout is not exact")
    if "always()" in text:
        errors.append("coordinator must not use always()")

    for command in ("build-core", "record-release-result"):
        if _command_count(text, command):
            errors.append(f"coordinator must not invoke worker command {command}")


def _audit_worker(text: str, record: dict[str, Any]) -> None:
    errors = record["errors"]
    lines = text.splitlines()
    _audit_permissions_and_triggers(text, role="worker", lines=lines, errors=errors)
    _audit_worker_inputs(lines, errors=errors)
    _audit_uses(text, role="worker", record=record)
    uploads, downloads = _audit_action_safety(lines, role="worker", errors=errors)

    jobs = _one_block(lines, "jobs", 0, errors, "jobs block")
    if jobs is not None and set(_direct_mapping(jobs, 2)) != {"build"}:
        errors.append("worker must contain exactly one build job")
    build = _one_block(lines, "build", 2, errors, "build job")
    build_text = "\n".join(build or [])
    build_environment = _one_block(
        build or [], "env", 4, errors, "worker build environment"
    )
    if _direct_mapping(build_environment or [], 6) != {
        "CANDIDATE_ID": "${{ inputs.candidate_id }}",
        "CORE_ID": "${{ inputs.core_id }}",
        "PLAN_PATH": ".local-e2e/release-plans/${{ inputs.candidate_id }}.json",
        "RESULT_PARENT": (
            ".local-e2e/release-results/${{ inputs.candidate_id }}/github-actions"
        ),
        "RUN_ID": "actions-${{ github.run_id }}-${{ github.run_attempt }}",
    }:
        errors.append("worker build environment bindings are not exact")

    if _command_count(build_text, "build-core") != 1:
        errors.append("worker must invoke build-core exactly once")
    if not re.search(r"--runner-profile\s+github-actions(?=\s|$)", build_text):
        errors.append("build-core must select the native github-actions runner")
    if _command_count(build_text, "record-release-result") != 1:
        errors.append("worker must invoke record-release-result exactly once")
    build_position = build_text.find("scripts/core_pipeline.py build-core")
    record_position = build_text.find("scripts/core_pipeline.py record-release-result")
    if build_position < 0 or record_position < 0 or build_position >= record_position:
        errors.append("worker must build before recording its release result")

    if "$RUNNER_TEMP/core-toolchains" not in build_text:
        errors.append("toolchain archives must be staged below RUNNER_TEMP")
    if re.search(r"gh\s+release\s+download[^\n]*--dir\s+\.(?:\s|$)", build_text):
        errors.append("toolchain archives must not be downloaded into the repository")
    if len(re.findall(r"gh\s+release\s+download\s+toolchains", build_text)) != 2:
        errors.append("worker must download exactly two toolchain archives")
    for architecture in ("arm64", "armhf"):
        archive = f"cores-{architecture}.tar.gz"
        if f'--pattern "{archive}"' not in build_text:
            errors.append(f"worker must download {archive}")
        if f'--{architecture} "$RUNNER_TEMP/core-toolchains/{archive}"' not in build_text:
            errors.append(f"worker must verify {archive} from RUNNER_TEMP")
        if f'gunzip -c "$RUNNER_TEMP/core-toolchains/{archive}" | docker load' not in (
            build_text
        ):
            errors.append(f"worker must load verified {archive}")
    verify_position = build_text.find("scripts/toolchain_archive.py verify-downloads")
    load_position = build_text.find("docker load")
    if verify_position < 0 or load_position < 0 or verify_position >= load_position:
        errors.append("worker must verify both archives before loading either image")

    if '--output-dir "$RESULT_PARENT/$CORE_ID"' not in build_text:
        errors.append("record-release-result output must preserve the core directory")
    result_uploads = [
        options for options in uploads if options.get("path") == "${{ env.RESULT_PARENT }}/"
    ]
    diagnostic_uploads = [
        options
        for options in uploads
        if options.get("path") == ".local-e2e/runs/${{ env.RUN_ID }}/"
    ]
    if len(result_uploads) != 1:
        errors.append("worker must upload the runner root with a top-level core directory")
    elif (
        result_uploads[0].get("name")
        != (
            "${{ inputs.result_artifact_prefix }}-${{ github.run_attempt }}-"
            "${{ inputs.core_id }}"
        )
        or result_uploads[0].get("if-no-files-found") != "error"
    ):
        errors.append("worker result artifact name must include its exact core ID")
    if len(diagnostic_uploads) != 1 or (
        diagnostic_uploads[0].get("name")
        != "release-e2e-${{ github.run_id }}-${{ github.run_attempt }}-${{ inputs.core_id }}"
        or diagnostic_uploads[0].get("if-no-files-found") != "ignore"
    ):
        errors.append("worker diagnostic artifact exception is not exact")
    diagnostic_blocks = [
        block
        for block in _action_blocks(lines, "actions/upload-artifact")
        if _action_options(block).get("path") == ".local-e2e/runs/${{ env.RUN_ID }}/"
    ]
    if (
        len(diagnostic_blocks) != 1
        or len(
            [
                line
                for line in diagnostic_blocks[0]
                if line.strip() == "if: ${{ always() }}"
            ]
        )
        != 1
        or text.count("always()") != 1
    ):
        errors.append("always() is allowed only on the exact diagnostic upload")
    if not downloads or downloads[0].get("path") != ".local-e2e/release-plans":
        errors.append("worker must download the release plan to its canonical directory")
    if not downloads or downloads[0].get("name") != "${{ inputs.plan_artifact_name }}":
        errors.append("worker must download the plan artifact selected by the coordinator")

    for command in ("plan-release", "release-matrix", "seal-release"):
        if _command_count(text, command):
            errors.append(f"worker must not invoke coordinator command {command}")


def audit_release_workflows(repository_root: Path) -> dict[str, Any]:
    """Return a structured report without raising for workflow contract errors."""

    records: dict[str, dict[str, Any]] = {
        "coordinator": _record(COORDINATOR_PATH),
        "worker": _record(WORKER_PATH),
    }
    if not isinstance(repository_root, Path):
        message = "repository root must be a pathlib.Path"
        for record in records.values():
            record["errors"].append(message)
        texts: dict[str, str | None] = {"coordinator": None, "worker": None}
    else:
        texts = {
            role: _read_workflow(repository_root, relative_path, records[role])
            for role, relative_path in (
                ("coordinator", COORDINATOR_PATH),
                ("worker", WORKER_PATH),
            )
        }

    for role, text in texts.items():
        if (
            text is not None
            and records[role]["file_sha256"] != EXPECTED_WORKFLOW_SHA256[role]
        ):
            records[role]["errors"].append(
                "workflow bytes differ from the reviewed canonical contract"
            )

    if texts["coordinator"] is not None:
        _audit_coordinator(texts["coordinator"], records["coordinator"])
    if texts["worker"] is not None:
        _audit_worker(texts["worker"], records["worker"])

    for record in records.values():
        record["status"] = "valid" if not record["errors"] else "invalid"
    errors = [
        f"{role}: {error}"
        for role, record in records.items()
        for error in record["errors"]
    ]
    unique_reusable_workflows = {
        value
        for value in records["coordinator"]["uses"]
        if isinstance(value, str) and value.startswith("./.github/workflows/")
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "valid" if not errors else "invalid",
        "publication": PUBLICATION,
        "coordinator": records["coordinator"],
        "worker": records["worker"],
        "summary": {
            "workflow_count": 2,
            "valid_workflow_count": sum(
                record["status"] == "valid" for record in records.values()
            ),
            "error_count": len(errors),
            "unique_reusable_workflow_count": len(unique_reusable_workflows),
            "max_parallel": records["coordinator"]["max_parallel"],
        },
        "errors": errors,
    }


__all__ = [
    "APPROVED_ACTION_REVISIONS",
    "COORDINATOR_PATH",
    "EXPECTED_WORKFLOW_SHA256",
    "MAX_PARALLEL",
    "SCHEMA_VERSION",
    "WORKER_PATH",
    "audit_release_workflows",
]
