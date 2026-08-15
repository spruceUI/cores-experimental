"""Build selection, group planning, and local build execution.

The launcher remains the composition root. Global dependencies are captured in
a filtered call-time service record so legacy wrappers and monkeypatch seams
remain dynamic without introducing a reverse import.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any

from .runtime import HostExecutionProfile
from .source_candidate import SourceCandidateContractProjection


SUBMODULE_STATUS_RE = re.compile(
    r"^(?P<state>[ +\-U])(?P<commit>[0-9a-f]{40})\s+"
    r"(?P<path>\S+)(?:\s+\([^()\s]+\))?$"
)
PREFIXLESS_GITLINK_RE = re.compile(
    r"^(?P<commit>[0-9a-f]{40})\s+(?P<path>\S+)$"
)


@dataclass(frozen=True, slots=True)
class BuildExecutionServices:
    """Call-time namespace required by build planning and execution."""

    namespace: Mapping[str, Any]

    def __getitem__(self, name: str) -> Any:
        return self.namespace[name]

    @classmethod
    def from_namespace(
        cls, namespace: Mapping[str, Any]
    ) -> "BuildExecutionServices":
        missing = _REQUIRED_BINDINGS.difference(namespace)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(f"missing build execution services: {names}")
        declared_proofs = {
            contract.proof_name
            for contract in namespace["CORE_LOG_CONTRACTS"]
        }
        proof_overrides = declared_proofs.intersection(namespace)
        captured_names = _REQUIRED_BINDINGS | proof_overrides
        return cls(
            MappingProxyType(
                {name: namespace[name] for name in captured_names}
            )
        )


def required_binding_names() -> frozenset[str]:
    """Return the exact launcher bindings consumed by this leaf."""

    return _REQUIRED_BINDINGS


_REQUIRED_BINDINGS = frozenset(
    {
        'COMPILER_COMMAND_RE',
        'CORE_LOG_CONTRACTS',
        'DEFAULT_CATALOG',
        'DEFAULT_CHIPSET_TUNINGS',
        'DEFAULT_CORE_TRACKS',
        'DEFAULT_PIN_SET_DIR',
        'DEFAULT_SPRUCE_BRANCH_BASES',
        'DEFAULT_SPRUCE_RELEASE_ROSTER',
        'GROUP_EXECUTION_SOURCE_KEYS',
        'GROUP_PIN_REFERENCE_KEYS',
        'GROUP_PIN_SOURCE_KEYS',
        'GROUP_PIN_SUBMODULE_KEYS',
        'GROUP_SOURCE_REF_RE',
        'GROUP_SUBMODULE_KEYS',
        'LOCAL_ID_RE',
        'Mapping',
        'Path',
        'PipelineError',
        'PurePosixPath',
        'RAW_TELEMETRY_DIRECTORY',
        'ROOT',
        'SHA1_RE',
        'SHA256_RE',
        'SOURCE_CANDIDATE_GIT_VERSION_TOKEN_RE',
        'TARGET_COMPILERS',
        'TARGET_CXX_COMPILERS',
        '__file__',
        '_candidate_log_with_canonical_git_version_tokens',
        '_core_log_contract_proofs',
        '_group_execution_spec',
        '_group_execution_tuning',
        '_group_submodule_path_is_safe',
        '_load_exact_group_pin_selection',
        '_registered_core_log_contract_proves',
        '_source_candidate_contract_spec',
        '_source_candidate_group_recipe_projection',
        '_validate_pin_set_document',
        '_validated_group_pin_reference',
        'apply_artifact_dependency_policy',
        'apply_group_output_expectations',
        'atomic_write_json',
        'build_toolchain_key',
        'chipset_tuning_log_proves_contract',
        'commit_blacklist_reference_is_well_formed',
        'compile_definitions_for_target',
        'compile_log_proves_definitions',
        'construct_core_track_inventory',
        'container_build_script',
        'copy',
        'core_contract_log_without_tuning_arguments',
        'core_log_contract_for',
        'core_spec_sha256',
        'core_track_source_ancestry_verifier',
        'direct_cmake_log_proves_contract',
        'execute_instrumented_container',
        'execution_tuning_profile',
        'expected_archive_provenance',
        'git_head',
        'git_version_log_proves_contract',
        'group_execution_spec',
        'group_source_candidate_contract_projection',
        'group_source_provenance_matches',
        'json',
        'line_may_name_target_compiler',
        'load_authoritative_core_pin_index',
        'load_core_track_source_registry_index',
        'load_json',
        'load_json_with_sha256',
        'make_variable_contract_name',
        'make_variable_log_proves_contract',
        'metadata_matches_replacement',
        'metadata_replacement_log_proves_contract',
        'metadata_replacement_mount_args',
        'normalized_build_contract',
        'not_applicable_phase',
        'os',
        'overlay_mount_args',
        'parse_bootstrap_evidence',
        'parse_group_tag',
        'parse_measured_phase',
        'parse_submodule_provenance',
        'parse_unit_evidence',
        'pinned_group_execution_source',
        'pipeline_source_bundle',
        'read_build_log',
        'recipe_record',
        'recorded_build_contract',
        'require_canonical_store_entry',
        'require_catalog_cores_eligible',
        'require_individual_pin_identity',
        'require_manifest_reference_path',
        'require_source_commits_eligible',
        'run',
        'safe_child',
        'sha256_bytes',
        'sha256_file',
        'shlex',
        'source_candidate_contract_context',
        'source_candidate_record_contract_projection',
        'source_date_epoch_is_well_formed',
        'subprocess',
        'time',
        'tuning_candidate_recipe_identity',
        'unavailable_observation',
        'utc_now',
        'validate_artifact',
        'validate_host_execution_contract',
        'validate_job_count_log',
        'validated_embedded_source_candidate_shape',
        'validated_git_version',
        'validated_group_execution_source',
        'validated_make_variables',
        'validated_metadata_replacement',
        'validated_output_reproduction_shape',
        'validated_source_date_epoch',
        'validated_tuning_candidate_selection',
        'verified_json_object',
        'verify_image',
    }
)


def parse_submodule_provenance(path: Path, *, services: BuildExecutionServices) -> tuple[list[dict], int | None]:
    """Parse one complete, status-shaped submodule provenance snapshot.

    The prefixless shape remains accepted for build records produced before
    ``provenance_shell`` canonicalized stray gitlinks. It denotes the clean
    state because ``ls-tree`` records the commit pinned by ``HEAD`` itself.
    Every non-empty file line must parse so callers cannot mistake a partial
    projection for the complete gitlink graph.
    """

    if not path.is_file():
        return [], None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise services['PipelineError']("submodule provenance is not readable UTF-8") from exc
    records: list[dict[str, str]] = []
    for line_number, line in enumerate(lines, start=1):
        match = SUBMODULE_STATUS_RE.fullmatch(line)
        state = match.group("state") if match is not None else " "
        if match is None:
            match = PREFIXLESS_GITLINK_RE.fullmatch(line)
        if match is None:
            raise services['PipelineError'](
                f"submodule provenance line {line_number} is malformed"
            )
        records.append(
            {
                "state": state,
                "commit": match.group("commit"),
                "path": match.group("path"),
            }
        )
    return records, len(lines)


def parse_submodules(path: Path, *, services: BuildExecutionServices) -> list[dict]:
    records, _ = services['parse_submodule_provenance'](path)
    return records


def core_spec_sha256(spec: dict, *, services: BuildExecutionServices) -> str:
    material = services['json'].dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    return services['sha256_bytes'](material)


def recipe_record(
    catalog_path: Path,
    core_id: str,
    spec: dict,
    *,
    host_execution: Mapping[str, object] | None = None,
    services: BuildExecutionServices,
) -> dict:
    workflow = services['ROOT'] / spec["workflow"]
    pipeline_bundle = services['pipeline_source_bundle']()
    catalog_snapshot, catalog_file_sha256 = services['load_json_with_sha256'](catalog_path)
    commit_blacklist = catalog_snapshot.get("commit_blacklist")
    if not services['commit_blacklist_reference_is_well_formed'](commit_blacklist):
        raise services['PipelineError']("recipe catalog commit_blacklist reference is invalid")
    record = {
        "repository_head": services['git_head'](services['ROOT']),
        "repository_dirty": bool(services['run'](["git", "status", "--short"], cwd=services['ROOT']).stdout),
        "catalog_path": str(catalog_path.relative_to(services['ROOT'])),
        "catalog_sha256": catalog_file_sha256,
        "core_spec_sha256": services['core_spec_sha256'](spec),
        "pipeline_sha256": services['sha256_file'](services['Path'](services['__file__'])),
        "pipeline_bundle": pipeline_bundle,
        "commit_blacklist": services['copy'].deepcopy(commit_blacklist),
        "workflow": spec["workflow"],
        "workflow_sha256": services['sha256_file'](workflow),
        "core_id": core_id,
    }
    if host_execution is not None:
        record["host_execution"] = services['validate_host_execution_contract'](
            host_execution, repository_root=services['ROOT']
        )
    return record


def _core_log_contract_proofs(*, services: BuildExecutionServices) -> dict[str, Callable[..., bool]]:
    """Bind registry names to their current individual proof callables.

    Collected by introspection over the contracts package: every
    ``*_log_proves_contract`` function *defined in* a contract module
    (``__module__`` check, so re-exports and the shared engine entry points
    never masquerade as a per-core proof) whose name the registry declares.
    The completeness check below is unchanged -- a registry entry without a
    bound callable still fails closed.
    """

    import importlib
    import pkgutil

    import core_pipeline_lib.contracts as contracts_package

    declared = {contract.proof_name for contract in services['CORE_LOG_CONTRACTS']}
    proofs: dict[str, Callable[..., bool]] = {}
    for info in pkgutil.iter_modules(contracts_package.__path__):
        module = importlib.import_module(
            f"core_pipeline_lib.contracts.{info.name}"
        )
        for name, value in vars(module).items():
            if (
                name in declared
                and callable(value)
                and getattr(value, "__module__", "") == module.__name__
            ):
                proofs[name] = value
    # The same testability seam as the spec guards: a proof patched onto the
    # launcher namespace overrides the contract-module callable.
    for name in list(proofs):
        if name in services.namespace:
            # Unconditional, not gated on callable(): a test (or a bug) that
            # sets the attribute to a non-callable must reach the tripwire
            # below, exactly as the literal map allowed.
            proofs[name] = services[name]
    registered_names = {contract.proof_name for contract in services['CORE_LOG_CONTRACTS']}
    if set(proofs) != registered_names:
        raise services['PipelineError']("core log contract proof mapping is incomplete")
    if any(not callable(proof) for proof in proofs.values()):
        raise services['PipelineError']("core log contract proof mapping contains a non-callable")
    return proofs


# The same seam for proofs: every registry-declared proof becomes a module
# attribute (patched by tests via mock.patch.object), seeded from the contract
# modules. Runs at import so an unbound registry entry still fails closed at
# the earliest moment, exactly as the literal map did.


SOURCE_CANDIDATE_GIT_VERSION_TOKEN_RE = re.compile(
    r'^-DGIT_VERSION="(?P<space> ?)(?P<commit>[0-9a-f]{7,40})"$'
)


def _candidate_log_with_canonical_git_version_tokens(
    build_log_text: str,
    arch: str,
    projection: SourceCandidateContractProjection,
    *,
    services: BuildExecutionServices,
) -> str | None:
    """Project only authenticated target-compile candidate SHA tokens."""

    compilers = set(services['TARGET_COMPILERS'].get(arch, ())).union(
        services['TARGET_CXX_COMPILERS'].get(arch, ())
    )
    if not compilers:
        raise services['PipelineError'](f"unknown architecture: {arch}")
    raw_lines = build_log_text.splitlines(keepends=True)
    replacements: list[tuple[int, int, int, str]] = []
    for line_index, raw_line in enumerate(raw_lines):
        line = raw_line.rstrip("\r\n")
        if not services['line_may_name_target_compiler'](line, compilers):
            continue
        try:
            tokens = services['shlex'].split(line)
        except ValueError:
            return None
        compiler_indexes = [
            index
            for index, token in enumerate(tokens)
            if services['Path'](token).name in compilers
            and services['COMPILER_COMMAND_RE'].fullmatch(services['Path'](token).name)
        ]
        if not compiler_indexes:
            continue
        if len(compiler_indexes) != 1:
            continue
        compiler_index = compiler_indexes[0]
        if compiler_index not in {0, 3} or (
            compiler_index == 3
            and not (tokens[0] == "cd" and tokens[2] == "&&")
        ):
            continue
        command_tokens = tokens[compiler_index:]
        if "-c" not in command_tokens:
            continue
        git_version_indexes = [
            index
            for index, token in enumerate(command_tokens)
            if "GIT_VERSION" in token
        ]
        if not git_version_indexes:
            continue
        if len(git_version_indexes) != 1:
            return None
        token_index = git_version_indexes[0]
        token = command_tokens[token_index]
        match = services['SOURCE_CANDIDATE_GIT_VERSION_TOKEN_RE'].fullmatch(token)
        if match is None:
            return None
        candidate_abbreviation = match.group("commit")
        if not projection.candidate_commit.startswith(candidate_abbreviation):
            return None
        canonical_abbreviation = projection.canonical_commit[
            : len(candidate_abbreviation)
        ]
        if line.count(candidate_abbreviation) != 1:
            return None
        replacement_start = line.index(candidate_abbreviation)
        replacement_end = replacement_start + len(candidate_abbreviation)
        projected_line = (
            line[:replacement_start]
            + canonical_abbreviation
            + line[replacement_end:]
        )
        try:
            projected_tokens = services['shlex'].split(projected_line)
        except ValueError:
            return None
        expected_tokens = list(tokens)
        expected_tokens[compiler_index + token_index] = (
            token[: match.start("commit")]
            + canonical_abbreviation
            + token[match.end("commit") :]
        )
        if projected_tokens != expected_tokens:
            return None
        replacements.append(
            (
                line_index,
                replacement_start,
                replacement_end,
                canonical_abbreviation,
            )
        )
    projected_lines = list(raw_lines)
    for line_index, start, end, replacement in replacements:
        projected_lines[line_index] = (
            projected_lines[line_index][:start]
            + replacement
            + projected_lines[line_index][end:]
        )
    return "".join(projected_lines)


def _registered_core_log_contract_proves(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object = None,
    source_tree: object = None,
    *,
    tuning: Mapping[str, object] | None = None,
    source_candidate_projection: SourceCandidateContractProjection | None = None,
    services: BuildExecutionServices,
) -> bool:
    """Run one core proof, composing an independently proven tuning delta."""

    contract = services['core_log_contract_for'](core_id)
    if contract is None:
        return True
    proof_log = build_log_text
    if tuning is not None:
        projected = services['core_contract_log_without_tuning_arguments'](
            build_log_text,
            tuning,
            arch,
        )
        if projected is None:
            return False
        proof_log = projected
    if source_candidate_projection is not None:
        if (
            contract.proof_kind != "core-arch-source"
            or source_candidate_projection.core_id != core_id
            or source_commit != source_candidate_projection.candidate_commit
            or source_tree != source_candidate_projection.candidate_tree
        ):
            return False
        projected = services['_candidate_log_with_canonical_git_version_tokens'](
            proof_log,
            arch,
            source_candidate_projection,
        )
        if projected is None:
            return False
        proof_log = projected
        source_commit = source_candidate_projection.canonical_commit
        source_tree = source_candidate_projection.canonical_tree
    proof = services['_core_log_contract_proofs']()[contract.proof_name]
    if contract.proof_kind == "core-arch":
        return proof(proof_log, core_id, arch)
    if contract.proof_kind == "core-arch-source":
        return proof(
            proof_log,
            core_id,
            arch,
            source_commit,
            source_tree,
        )
    raise services['PipelineError'](
        f"unsupported core log contract proof kind: {contract.proof_kind}"
    )


def registered_core_log_contract_proves(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object = None,
    source_tree: object = None,
    *,
    services: BuildExecutionServices,
) -> bool:
    """Run an ordinary core proof without a caller-supplied relaxation."""

    return services['_registered_core_log_contract_proves'](
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
    )


GROUP_EXECUTION_SOURCE_KEYS = frozenset(
    {"url", "requested_ref", "commit", "tree", "submodules"}
)
GROUP_PIN_SOURCE_KEYS = frozenset(
    {*GROUP_EXECUTION_SOURCE_KEYS, "resolved_commit", "resolved_url"}
)
GROUP_SUBMODULE_KEYS = frozenset({"path", "commit"})
GROUP_PIN_SUBMODULE_KEYS = frozenset({*GROUP_SUBMODULE_KEYS, "state"})
GROUP_PIN_REFERENCE_KEYS = frozenset(
    {"path", "pin_id", "file_sha256", "content_sha256"}
)
GROUP_SOURCE_REF_RE = re.compile(r"^refs/(?:heads|tags)/[^\s]+$")


def _group_submodule_path_is_safe(value: object, *, services: BuildExecutionServices) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = services['PurePosixPath'](value)
    return (
        not any(character.isspace() for character in value)
        and "\\" not in value
        and not path.is_absolute()
        and path.as_posix() == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


def pinned_group_execution_source(
    golden_source: object,
    *,
    label: str,
    services: BuildExecutionServices,
) -> dict:
    """Extract one exact immutable source projection from pinned evidence."""

    if not isinstance(golden_source, services['Mapping']) or set(golden_source) != set(
        services['GROUP_PIN_SOURCE_KEYS']
    ):
        raise services['PipelineError'](f"{label} source fields are not exact")
    url = golden_source.get("url")
    requested_ref = golden_source.get("requested_ref")
    commit = golden_source.get("commit")
    tree = golden_source.get("tree")
    if (
        not isinstance(url, str)
        or not url
        or golden_source.get("resolved_url") != url
        or not isinstance(requested_ref, str)
        or services['GROUP_SOURCE_REF_RE'].fullmatch(requested_ref) is None
        or not isinstance(commit, str)
        or services['SHA1_RE'].fullmatch(commit) is None
        or golden_source.get("resolved_commit") != commit
        or not isinstance(tree, str)
        or services['SHA1_RE'].fullmatch(tree) is None
    ):
        raise services['PipelineError'](f"{label} source identity is malformed")
    raw_submodules = golden_source.get("submodules")
    if not isinstance(raw_submodules, list):
        raise services['PipelineError'](f"{label} source submodules must be a list")
    submodules: list[dict[str, str]] = []
    for index, item in enumerate(raw_submodules):
        if (
            not isinstance(item, services['Mapping'])
            or set(item) != set(services['GROUP_PIN_SUBMODULE_KEYS'])
            or item.get("state") != " "
            or not services['_group_submodule_path_is_safe'](item.get("path"))
            or not isinstance(item.get("commit"), str)
            or services['SHA1_RE'].fullmatch(item["commit"]) is None
        ):
            raise services['PipelineError'](f"{label} source submodule {index} is malformed")
        submodules.append({"path": item["path"], "commit": item["commit"]})
    paths = [item["path"] for item in submodules]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise services['PipelineError'](f"{label} source submodules must have unique sorted paths")
    return {
        "url": url,
        "requested_ref": requested_ref,
        "commit": commit,
        "tree": tree,
        "submodules": submodules,
    }


def validated_group_execution_source(value: object, *, label: str, services: BuildExecutionServices) -> dict:
    """Validate a persisted execution-source projection without widening it."""

    if not isinstance(value, services['Mapping']) or set(value) != set(
        services['GROUP_EXECUTION_SOURCE_KEYS']
    ):
        raise services['PipelineError'](f"{label} fields are not exact")
    raw_submodules = value.get("submodules")
    if not isinstance(raw_submodules, list):
        raise services['PipelineError'](f"{label} submodules must be a list")
    synthetic = {
        **services['copy'].deepcopy(dict(value)),
        "resolved_commit": value.get("commit"),
        "resolved_url": value.get("url"),
        "submodules": [
            {**services['copy'].deepcopy(item), "state": " "}
            if isinstance(item, services['Mapping'])
            else item
            for item in raw_submodules
        ],
    }
    return services['pinned_group_execution_source'](synthetic, label=label)


def _validated_group_pin_reference(
    value: object,
    *,
    core_id: str,
    services: BuildExecutionServices,
) -> dict:
    if not isinstance(value, services['Mapping']) or set(value) != set(
        services['GROUP_PIN_REFERENCE_KEYS']
    ):
        raise services['PipelineError'](f"{core_id} group pin reference fields are not exact")
    pin_id = value.get("pin_id")
    if (
        not isinstance(pin_id, str)
        or services['LOCAL_ID_RE'].fullmatch(pin_id) is None
        or not pin_id.startswith(f"{core_id}-")
        or value.get("path") != f"pins/core-sets/{pin_id}.json"
        or not isinstance(value.get("file_sha256"), str)
        or services['SHA256_RE'].fullmatch(value["file_sha256"]) is None
        or not isinstance(value.get("content_sha256"), str)
        or services['SHA256_RE'].fullmatch(value["content_sha256"]) is None
    ):
        raise services['PipelineError'](f"{core_id} group pin reference is malformed")
    return services['copy'].deepcopy(dict(value))


def _load_exact_group_pin_selection(
    *,
    core_id: str,
    group_selection: Mapping[str, object],
    services: BuildExecutionServices,
) -> dict:
    """Reload and deeply validate the exact pin bound to persisted group state."""

    reference = services['_validated_group_pin_reference'](
        group_selection.get("pin"),
        core_id=core_id,
    )
    pin_path = services['require_manifest_reference_path'](
        reference,
        services['DEFAULT_PIN_SET_DIR'],
        f"{core_id} group execution pin",
    )
    pin, file_sha256 = services['load_json_with_sha256'](pin_path)
    if (
        file_sha256 != reference["file_sha256"]
        or pin.get("pin_id") != reference["pin_id"]
        or pin.get("content_sha256") != reference["content_sha256"]
    ):
        raise services['PipelineError'](f"{core_id} group execution pin identity changed")
    report = services['_validate_pin_set_document'](
        pin,
        verify_store=False,
        verify_sources=False,
        document_path=pin_path,
    )
    if report["status"] != "valid":
        raise services['PipelineError'](
            f"{core_id} group execution pin is invalid:\n- "
            + "\n- ".join(report["errors"])
        )
    pinned_core_id, _semantic_id = services['require_individual_pin_identity'](
        pin,
        pin_path=pin_path,
    )
    selection = pin.get("cores", {}).get(core_id, {}).get("selection")
    if pinned_core_id != core_id or not isinstance(selection, services['Mapping']):
        raise services['PipelineError'](f"{core_id} group execution pin owns another core")
    return services['copy'].deepcopy(dict(selection))


def _source_candidate_group_recipe_projection(
    *,
    core_id: str,
    catalog_spec: Mapping[str, object],
    execution_source: Mapping[str, object],
    pin_selection: Mapping[str, object],
    services: BuildExecutionServices,
) -> tuple[bool, int | None, SourceCandidateContractProjection | None]:
    """Return the source-candidate-proven epoch frozen by promoted goldens.

    The golden build record is the runtime authority.  Candidate provenance is
    used only to prove why that exact value may differ from the current catalog;
    live Git is never consulted to derive it.
    """

    targets = pin_selection.get("targets")
    if not isinstance(targets, services['Mapping']) or not targets:
        raise services['PipelineError'](f"{core_id} group pin target selection is missing")
    golden_records: dict[str, services['Mapping'][str, object]] = {}
    for arch, target in sorted(targets.items()):
        golden = target.get("golden_record") if isinstance(target, services['Mapping']) else None
        if not isinstance(arch, str) or not isinstance(golden, services['Mapping']):
            raise services['PipelineError'](f"{core_id} group pin golden record is missing")
        golden_records[arch] = golden

    raw_candidate = pin_selection.get("source_candidate")
    raw_reproduction = pin_selection.get("output_reproduction")
    golden_candidate_fields = any(
        golden.get("source_candidate") is not None
        or golden.get("output_reproduction") is not None
        for golden in golden_records.values()
    )
    if raw_candidate is None and raw_reproduction is None:
        if golden_candidate_fields:
            raise services['PipelineError'](
                f"{core_id} group pin source-candidate projection is incomplete"
            )
        return False, None, None
    if (
        raw_candidate is None
        or raw_reproduction is None
        or pin_selection.get("chipset_tuning") is not None
        or pin_selection.get("reproduction") is not None
    ):
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate projection must be complete and untuned"
        )

    candidate = services['validated_embedded_source_candidate_shape'](
        raw_candidate,
        core_id=core_id,
    )
    reproduction = services['validated_output_reproduction_shape'](
        raw_reproduction,
        core_id=core_id,
        golden_records=golden_records,
    )
    candidate_selection = candidate["selection"]
    golden_recipes: dict[str, services['Mapping'][str, object]] = {}
    golden_builds: dict[str, services['Mapping'][str, object]] = {}
    contract_projections: list[SourceCandidateContractProjection | None] = []
    for arch, golden in golden_records.items():
        recipe = golden.get("recipe")
        build = golden.get("build")
        if not isinstance(recipe, services['Mapping']) or not isinstance(build, services['Mapping']):
            raise services['PipelineError'](
                f"{core_id}/{arch} group pin source-candidate recipe is malformed"
            )
        golden_recipes[arch] = recipe
        golden_builds[arch] = build
        local_store = golden.get("local_store")
        recipe_references = (
            local_store.get("recipe_snapshots")
            if isinstance(local_store, services['Mapping'])
            else None
        )
        recipe_reference = (
            recipe_references.get(arch)
            if isinstance(recipe_references, services['Mapping'])
            else None
        )
        if not isinstance(recipe_reference, dict):
            raise services['PipelineError'](
                f"{core_id}/{arch} group pin frozen recipe is missing"
            )
        recipe_path = services['require_canonical_store_entry'](
            recipe_reference,
            "recipes",
            f"{core_id}/{arch} group pin frozen recipe",
        )
        recipe_snapshot = services['verified_json_object'](
            recipe_path,
            recipe_reference.get("sha256"),
            f"{core_id}/{arch} group pin frozen recipe",
        )
        contract_projections.append(
            services['source_candidate_record_contract_projection'](
                candidate,
                core_id=core_id,
                recorded_source=golden.get("source"),
                recorded_recipe=recipe,
                recipe_snapshot=recipe_snapshot,
            )
        )
    if any(
        golden.get("source_candidate") != candidate
        or golden.get("output_reproduction") != reproduction
        or golden.get("tuning_candidate") is not None
        or golden.get("reproduction") is not None
        or golden_recipes[arch].get("chipset_tuning") is not None
        for arch, golden in golden_records.items()
    ):
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate evidence differs by target"
        )
    if any(projection != contract_projections[0] for projection in contract_projections):
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate contract differs by target"
        )
    contract_projection = contract_projections[0]

    raw_gitlinks = candidate_selection.get("top_level_gitlinks")
    if not isinstance(raw_gitlinks, list) or any(
        not isinstance(item, services['Mapping']) or set(item) != set(services['GROUP_SUBMODULE_KEYS'])
        for item in raw_gitlinks
    ):
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate gitlinks are malformed"
        )
    candidate_source = services['validated_group_execution_source'](
        {
            "url": candidate_selection.get("url"),
            "requested_ref": candidate_selection.get("requested_ref"),
            "commit": candidate_selection.get("commit"),
            "tree": candidate_selection.get("tree"),
            "submodules": services['copy'].deepcopy(raw_gitlinks),
        },
        label=f"{core_id} source-candidate selection",
    )
    expected_top_level = {
        item["path"]: item["commit"] for item in candidate_source["submodules"]
    }
    recorded_recursive = {
        item["path"]: item["commit"] for item in execution_source["submodules"]
    }
    if (
        any(
            candidate_source[key] != execution_source[key]
            for key in ("url", "requested_ref", "commit", "tree")
        )
        or any(
            recorded_recursive.get(path) != commit
            for path, commit in expected_top_level.items()
        )
        or any(
            path not in expected_top_level
            and not any(
                path.startswith(f"{parent}/") for parent in expected_top_level
            )
            for path in recorded_recursive
        )
    ):
        raise services['PipelineError'](
            f"{core_id} group pin source differs from source-candidate provenance"
        )

    execution = candidate["execution"]
    candidate_core_spec_sha256 = execution.get("core_spec_sha256")
    if any(
        recipe.get("core_spec_sha256") != candidate_core_spec_sha256
        for recipe in golden_recipes.values()
    ):
        raise services['PipelineError'](
            f"{core_id} group pin recipe differs from source-candidate execution"
        )

    catalog_epoch = services['validated_source_date_epoch'](dict(catalog_spec))
    derivation = execution.get("source_date_epoch_derivation")
    recipe_risk = candidate_selection.get("recipe_risk")
    if not isinstance(recipe_risk, services['Mapping']) or type(
        recipe_risk.get("source_date_epoch")
    ) is not bool:
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate epoch risk is malformed"
        )
    if catalog_epoch is None:
        if derivation != "absent" or recipe_risk["source_date_epoch"] is not False:
            raise services['PipelineError'](
                f"{core_id} group pin source-candidate epoch presence changed"
            )
        if any(
            "source_date_epoch" in build for build in golden_builds.values()
        ):
            raise services['PipelineError'](
                f"{core_id} group pin source-candidate unexpectedly pins an epoch"
            )
        return True, None, contract_projection

    commit_epoch = candidate_selection.get("commit_epoch")
    if (
        derivation != "candidate-commit-epoch"
        or recipe_risk["source_date_epoch"] is not True
        or not services['source_date_epoch_is_well_formed'](commit_epoch)
    ):
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate epoch derivation is invalid"
        )
    pinned_epochs = {
        build.get("source_date_epoch") for build in golden_builds.values()
    }
    if (
        len(pinned_epochs) != 1
        or any(not services['source_date_epoch_is_well_formed'](epoch) for epoch in pinned_epochs)
    ):
        raise services['PipelineError'](
            f"{core_id} group pin source-candidate epoch differs by target"
        )
    pinned_epoch = next(iter(pinned_epochs))
    assert isinstance(pinned_epoch, int)
    if pinned_epoch != commit_epoch:
        raise services['PipelineError'](
            f"{core_id} group pin epoch differs from source-candidate commit epoch"
        )
    return True, pinned_epoch, contract_projection


def _group_execution_spec(
    *,
    core_id: str,
    catalog_spec: Mapping[str, object],
    group_selection: Mapping[str, object],
    validated_pin_selection: Mapping[str, object] | None = None,
    services: BuildExecutionServices,
) -> dict:
    """Return a copied current recipe bound to the group's immutable source."""

    source = services['validated_group_execution_source'](
        group_selection.get("execution_source"),
        label=f"{core_id} group execution source",
    )
    catalog_source = catalog_spec.get("source")
    allowed_catalog_source_keys = services['GROUP_EXECUTION_SOURCE_KEYS']
    if (
        not isinstance(catalog_source, services['Mapping'])
        or set(catalog_source)
        not in (
            set(allowed_catalog_source_keys),
            set(allowed_catalog_source_keys) - {"submodules"},
        )
        or source["url"] != catalog_source.get("url")
    ):
        raise services['PipelineError'](
            f"core group source repository differs from the catalog: {core_id}"
        )
    if group_selection.get("source_commit") != source["commit"]:
        raise services['PipelineError'](f"core group source commit is inconsistent: {core_id}")
    architectures = group_selection.get("selected_architectures")
    targets = catalog_spec.get("targets")
    if (
        not isinstance(architectures, list)
        or not architectures
        or any(not isinstance(arch, str) for arch in architectures)
        or len(architectures) != len(set(architectures))
        or not isinstance(targets, list)
        or any(arch not in targets for arch in architectures)
    ):
        raise services['PipelineError'](f"core group execution architectures are invalid: {core_id}")
    # Keep the current catalog's source *shape* in the recipe copy.  In
    # particular, an absent ``submodules`` key is semantically distinct from
    # adding an empty list to the core-spec digest.  The complete selected
    # submodule projection remains in ``core_group.execution_source`` and is
    # checked explicitly against live provenance below.
    execution_spec = services['copy'].deepcopy(dict(catalog_spec))
    execution_spec["source"] = {
        key: services['copy'].deepcopy(source[key]) for key in catalog_source
    }
    pin_selection = validated_pin_selection
    if pin_selection is not None:
        if not isinstance(pin_selection, services['Mapping']):
            raise services['PipelineError'](f"{core_id} validated group pin selection is malformed")
        services['_validated_group_pin_reference'](group_selection.get("pin"), core_id=core_id)
        pin_selection = services['copy'].deepcopy(dict(pin_selection))
    elif group_selection.get("pin") is not None:
        pin_selection = services['_load_exact_group_pin_selection'](
            core_id=core_id,
            group_selection=group_selection,
        )
    candidate_proven = False
    source_candidate_projection: SourceCandidateContractProjection | None = None
    if pin_selection is not None:
        (
            candidate_proven,
            pinned_epoch,
            source_candidate_projection,
        ) = services['_source_candidate_group_recipe_projection'](
            core_id=core_id,
            catalog_spec=catalog_spec,
            execution_source=source,
            pin_selection=pin_selection,
        )
        if pinned_epoch is not None:
            execution_build = execution_spec.get("build")
            if not isinstance(execution_build, dict):
                raise services['PipelineError'](f"{core_id} group execution build is malformed")
            execution_build["source_date_epoch"] = pinned_epoch
        if candidate_proven:
            candidate = pin_selection["source_candidate"]
            assert isinstance(candidate, services['Mapping'])
            candidate_execution = candidate["execution"]
            assert isinstance(candidate_execution, services['Mapping'])
            if services['core_spec_sha256'](execution_spec) != candidate_execution.get(
                "core_spec_sha256"
            ):
                raise services['PipelineError'](
                    f"{core_id} group execution recipe differs from its "
                    "source-candidate provenance"
                )
    source_differs = any(
        source.get(key) != catalog_source.get(key)
        for key in ("requested_ref", "commit", "tree")
    )
    if source_differs and not candidate_proven:
        raise services['PipelineError'](
            f"{core_id} changed group source requires authenticated "
            "source-candidate provenance"
        )
    for arch in architectures:
        try:
            catalog_contract = services['normalized_build_contract'](dict(catalog_spec), arch)
            execution_contract = services['normalized_build_contract'](
                execution_spec,
                arch,
                core_id=core_id,
                source_candidate_contract_spec=(
                    dict(catalog_spec)
                    if source_candidate_projection is not None
                    else None
                ),
                source_candidate_projection=source_candidate_projection,
            )
        except services['PipelineError'] as exc:
            raise services['PipelineError'](
                f"core group source is incompatible with the current recipe: "
                f"{core_id}/{arch}: {exc}"
            ) from exc
        compatible = execution_contract == catalog_contract
        if candidate_proven:
            projected_catalog_contract = services['copy'].deepcopy(catalog_contract)
            projected_execution_contract = services['copy'].deepcopy(execution_contract)
            projected_catalog_contract.pop("source_date_epoch", None)
            projected_execution_contract.pop("source_date_epoch", None)
            compatible = projected_execution_contract == projected_catalog_contract
        if not compatible:
            if candidate_proven:
                raise services['PipelineError'](
                    f"core group source changes the normalized build contract beyond "
                    f"its promoted source-candidate epoch: "
                    f"{core_id}/{arch}"
                )
            raise services['PipelineError'](
                f"core group source changes the normalized build contract: "
                f"{core_id}/{arch}"
            )
    return execution_spec


def group_execution_spec(
    *,
    core_id: str,
    catalog_spec: Mapping[str, object],
    group_selection: Mapping[str, object],
    services: BuildExecutionServices,
) -> dict:
    """Resolve group execution only from its exact persisted pin reference."""

    return services['_group_execution_spec'](
        core_id=core_id,
        catalog_spec=catalog_spec,
        group_selection=group_selection,
    )


def group_source_candidate_contract_projection(
    *,
    core_id: str,
    catalog_spec: Mapping[str, object],
    execution_spec: Mapping[str, object],
    group_selection: Mapping[str, object],
    services: BuildExecutionServices,
) -> SourceCandidateContractProjection | None:
    """Recover one promoted projection from the group's exact referenced pin."""

    if group_selection.get("pin") is None:
        return None
    pin_selection = services['_load_exact_group_pin_selection'](
        core_id=core_id,
        group_selection=group_selection,
    )
    execution_source = services['validated_group_execution_source'](
        group_selection.get("execution_source"),
        label=f"{core_id} group execution source",
    )
    _candidate_proven, _pinned_epoch, projection = (
        services['_source_candidate_group_recipe_projection'](
            core_id=core_id,
            catalog_spec=catalog_spec,
            execution_source=execution_source,
            pin_selection=pin_selection,
        )
    )
    if projection is not None:
        services['_source_candidate_contract_spec'](
            core_id,
            dict(execution_spec),
            dict(catalog_spec),
            projection,
        )
    return projection


def resolve_core_group_build_selection(
    *,
    group_tag: str,
    catalog_path: Path,
    catalog: dict,
    core_id: str,
    pin_index: Mapping[str, Mapping[str, object]] | None = None,
    track_registry: Mapping[str, object] | None = None,
    tuning_registry: Mapping[str, object] | None = None,
    release_roster: Mapping[str, object] | None = None,
    spruce_branch_bases: Mapping[str, object] | None = None,
    services: BuildExecutionServices,
) -> dict:
    """Resolve and preflight one group as an exact pinned-output build plan.

    Historical recipes are not interpreted.  A selected pin is executable only
    when its source and normalized per-target build contract still match the
    canonical catalog.  Its artifact identities remain the acceptance oracle.
    """

    services['parse_group_tag'](group_tag)
    if catalog_path.resolve() != services['DEFAULT_CATALOG'].resolve():
        raise services['PipelineError']("group-selected builds require the canonical core catalog")
    if core_id not in catalog["cores"]:
        raise services['PipelineError'](f"unknown core: {core_id}")
    if pin_index is None:
        pin_index = services['load_authoritative_core_pin_index']()
    if track_registry is None:
        track_registry = services['load_json'](services['DEFAULT_CORE_TRACKS'])
    if tuning_registry is None:
        tuning_registry = services['load_json'](services['DEFAULT_CHIPSET_TUNINGS'])
    if release_roster is None:
        release_roster = services['load_json'](services['DEFAULT_SPRUCE_RELEASE_ROSTER'])
    if spruce_branch_bases is None:
        spruce_branch_bases = services['load_json'](services['DEFAULT_SPRUCE_BRANCH_BASES'])
    inventory = services['construct_core_track_inventory'](
        track_registry,
        catalog=catalog,
        pin_index=pin_index,
        tunings=tuning_registry,
        main_release_roster=release_roster,
        spruce_branch_bases=spruce_branch_bases,
        group_tag=group_tag,
        requested_cores=[core_id],
        source_registry_index=services['load_core_track_source_registry_index'](services['ROOT']),
        source_ancestry_verifier=services['core_track_source_ancestry_verifier'](),
        source_ancestry_core_id=core_id,
    )
    if not inventory["complete"] or len(inventory["cores"]) != 1:
        deferred = inventory.get("deferred_cores")
        if isinstance(deferred, list) and deferred:
            row = deferred[0]
            reason = row.get("reason", "unspecified") if isinstance(row, services['Mapping']) else "unspecified"
            raise services['PipelineError'](
                f"core group selection is deferred for {core_id}: "
                f"{group_tag}: {reason}"
            )
        raise services['PipelineError'](
            f"core group selection is unsupported for {core_id}: {group_tag}"
        )
    row = inventory["cores"][0]
    pin_path = services['safe_child'](services['ROOT'], row["pin"]["path"], "core group pin path")
    pin, pin_file_sha256 = services['load_json_with_sha256'](pin_path)
    if pin_file_sha256 != row["pin"]["file_sha256"]:
        raise services['PipelineError']("core group pin changed after inventory resolution")
    if pin.get("content_sha256") != row["pin"]["content_sha256"]:
        raise services['PipelineError']("core group pin content identity changed after resolution")
    core_pin = pin.get("cores", {}).get(core_id)
    selection = core_pin.get("selection") if isinstance(core_pin, services['Mapping']) else None
    targets = selection.get("targets") if isinstance(selection, services['Mapping']) else None
    if not isinstance(targets, services['Mapping']):
        raise services['PipelineError']("core group pin has no executable target selection")
    catalog_spec = catalog["cores"][core_id]
    selected_architectures = row["selected_architectures"]
    if (
        not isinstance(selected_architectures, list)
        or not selected_architectures
        or any(
            not isinstance(arch, str) or arch not in catalog_spec["targets"]
            for arch in selected_architectures
        )
        or len(selected_architectures) != len(set(selected_architectures))
    ):
        raise services['PipelineError']("core group selected architecture set is invalid")

    # A pin is one source identity even when this group projects only one of
    # its ABIs.  Validate every target so an unselected target cannot smuggle
    # a different tree or submodule graph into the package oracle.
    pin_sources: dict[str, dict] = {}
    for target_arch, target in sorted(targets.items()):
        golden = target.get("golden_record") if isinstance(target, services['Mapping']) else None
        if not isinstance(target_arch, str) or not isinstance(golden, services['Mapping']):
            raise services['PipelineError']("core group pin target source identity is missing")
        pin_sources[target_arch] = services['pinned_group_execution_source'](
            golden.get("source"),
            label=f"{core_id}/{target_arch} group pin",
        )
    if not pin_sources:
        raise services['PipelineError']("core group pin has no source identity")
    execution_source = next(iter(pin_sources.values()))
    if any(source != execution_source for source in pin_sources.values()):
        raise services['PipelineError']("core group pin source identity differs by architecture")
    if row.get("source_commit") != execution_source["commit"]:
        raise services['PipelineError']("core group inventory source commit is inconsistent")
    execution_spec = services['_group_execution_spec'](
        core_id=core_id,
        catalog_spec=catalog_spec,
        group_selection={
            "pin": services['copy'].deepcopy(row["pin"]),
            "execution_source": execution_source,
            "source_commit": row["source_commit"],
            "selected_architectures": selected_architectures,
        },
        validated_pin_selection=selection,
    )
    _candidate_proven, _candidate_epoch, source_candidate_projection = (
        services['_source_candidate_group_recipe_projection'](
            core_id=core_id,
            catalog_spec=catalog_spec,
            execution_source=execution_source,
            pin_selection=selection,
        )
    )
    services['require_source_commits_eligible'](catalog, [(core_id, execution_source)])
    expected_core_spec_sha256 = services['core_spec_sha256'](execution_spec)
    resolved_tuning = services['execution_tuning_profile'](
        row["tuning"]["profile_id"],
        selected_architectures[0],
        tuning_registry,
    )
    assert resolved_tuning is not None
    tuning_projection = {
        key: services['copy'].deepcopy(resolved_tuning[key])
        for key in (
            "profile_id",
            "content_sha256",
            "properties",
            "compiler_argument_mapping_version",
            "compiler_arguments",
        )
    }
    if row["tuning"] != tuning_projection:
        raise services['PipelineError']("core group tuning identity changed after resolution")
    if (
        resolved_tuning["compiler_arguments"]
        and execution_spec["build"]["driver"] == "direct-cargo"
    ):
        raise services['PipelineError'](
            "chipset-tuned direct-cargo group builds are unsupported: " + core_id
        )
    expected_tuning_identity = {
        "profile_id": resolved_tuning["profile_id"],
        "content_sha256": resolved_tuning["content_sha256"],
    }
    expected_targets: dict[str, dict] = {}
    selected_recipe_core_spec_sha256: set[str] = set()
    for arch in selected_architectures:
        # Rendering is side-effect free and catches a source/recipe pairing
        # that a driver-specific exact contract cannot honestly execute.  It
        # happens during group resolution, before cmd_e2e creates its run root.
        services['container_build_script'](
            core_id,
            arch,
            execution_spec,
            catalog["resolver"],
            resolved_tuning["profile_id"],
            tuning_registry,
            source_candidate_contract_spec=(
                catalog_spec
                if source_candidate_projection is not None
                else None
            ),
            source_candidate_projection=source_candidate_projection,
        )
        target = targets.get(arch)
        golden = target.get("golden_record") if isinstance(target, services['Mapping']) else None
        recipe = golden.get("recipe") if isinstance(golden, services['Mapping']) else None
        golden_artifact = (
            golden.get("artifact") if isinstance(golden, services['Mapping']) else None
        )
        golden_metadata = (
            golden.get("metadata") if isinstance(golden, services['Mapping']) else None
        )
        if (
            not isinstance(golden, services['Mapping'])
            or not isinstance(recipe, services['Mapping'])
            or not isinstance(golden_artifact, services['Mapping'])
            or not isinstance(golden_metadata, services['Mapping'])
            or pin_sources.get(arch) != execution_source
            or services['recorded_build_contract'](golden.get("build"))
            != services['normalized_build_contract'](
                execution_spec,
                arch,
                core_id=core_id,
                source_candidate_contract_spec=(
                    catalog_spec
                    if source_candidate_projection is not None
                    else None
                ),
                source_candidate_projection=source_candidate_projection,
            )
            or golden_artifact.get("path")
            != execution_spec["build"]["artifact_name"]
            or golden_metadata.get("path")
            != execution_spec["metadata"]["artifact_name"]
        ):
            raise services['PipelineError'](
                f"core group pin requires an unsupported historical recipe: {core_id}/{arch}"
            )
        selected_core_spec_sha256 = recipe.get("core_spec_sha256")
        if not isinstance(selected_core_spec_sha256, str) or services['SHA256_RE'].fullmatch(
            selected_core_spec_sha256
        ) is None:
            raise services['PipelineError'](
                f"core group pin recipe identity is malformed: {core_id}/{arch}"
            )
        selected_recipe_core_spec_sha256.add(selected_core_spec_sha256)
        recorded_tuning = recipe.get("chipset_tuning")
        if resolved_tuning["chipset"] == "universal":
            if recorded_tuning not in (None, expected_tuning_identity):
                raise services['PipelineError'](
                    f"core group pin tuning differs from universal: {core_id}/{arch}"
                )
        elif recorded_tuning != expected_tuning_identity:
            raise services['PipelineError'](
                f"core group pin lacks its selected tuning identity: {core_id}/{arch}"
            )
        artifact = target.get("artifact")
        if not isinstance(artifact, services['Mapping']):
            raise services['PipelineError'](f"core group pin artifact is missing: {core_id}/{arch}")
        expected_targets[arch] = {
            "artifact": {
                "sha256": artifact.get("sha256"),
                "size": artifact.get("size"),
            }
        }
    metadata = selection.get("metadata")
    package = selection.get("package")
    if not isinstance(metadata, services['Mapping']) or not isinstance(package, services['Mapping']):
        raise services['PipelineError']("core group pin output identities are incomplete")
    if len(selected_recipe_core_spec_sha256) != 1:
        raise services['PipelineError']("core group pin recipe identity differs by architecture")
    selected_core_spec_sha256 = next(iter(selected_recipe_core_spec_sha256))
    package_comparison = (
        "exact"
        if set(selected_architectures) == set(targets)
        else "not_applicable_projected_architectures"
    )
    evidence = {
        "schema_version": 1,
        "validation_scope": "pinned-output-reproduction-v1",
        "group_tag": group_tag,
        "inventory_content_sha256": inventory["content_sha256"],
        "track_registry_content_sha256": inventory[
            "track_registry_content_sha256"
        ],
        "tuning_registry_content_sha256": inventory[
            "tuning_registry_content_sha256"
        ],
        "spruce_branch_basis": services['copy'].deepcopy(row["spruce_branch_basis"]),
        "core_id": core_id,
        "variant_id": row["variant_id"],
        "requested_marker": row["requested_marker"],
        "requested_chipset": row["requested_chipset"],
        "selected_chipset": row["selected_chipset"],
        "selected_state": row["selected_state"],
        "stability": row["stability"],
        "resolution": row["resolution"],
        "test_origin_track": row["test_origin_track"],
        "pin": services['copy'].deepcopy(row["pin"]),
        "source_commit": row["source_commit"],
        "execution_source": services['copy'].deepcopy(execution_source),
        "recipe_compatibility": {
            "model": "source-normalized-build-contract-v1",
            "selected_pin_core_spec_sha256": selected_core_spec_sha256,
            "execution_core_spec_sha256": expected_core_spec_sha256,
            "core_spec_identity_match": (
                selected_core_spec_sha256 == expected_core_spec_sha256
            ),
        },
        "selected_architectures": services['copy'].deepcopy(selected_architectures),
        "tuning": services['copy'].deepcopy(row["tuning"]),
        "expected_outputs": {
            "targets": expected_targets,
            "metadata": {
                "sha256": metadata.get("sha256"),
                "size": metadata.get("size"),
            },
            "package": {
                "comparison": package_comparison,
                "name": package.get("name"),
                "sha256": package.get("sha256"),
                "size": package.get("size"),
            },
        },
    }
    if "approval" in row:
        evidence["approval"] = services['copy'].deepcopy(row["approval"])
    return evidence


def _group_execution_tuning(
    selection: object,
    *,
    core_id: str,
    arch: str,
    services: BuildExecutionServices,
) -> dict | None:
    if selection is None:
        return None
    if (
        not isinstance(selection, services['Mapping'])
        or selection.get("core_id") != core_id
        or arch not in selection.get("selected_architectures", ())
        or not isinstance(selection.get("tuning"), services['Mapping'])
    ):
        raise services['PipelineError']("core group execution selection is malformed")
    services['parse_group_tag'](selection.get("group_tag"))
    tuning = services['execution_tuning_profile'](selection["tuning"].get("profile_id"), arch)
    if tuning is None:
        raise services['PipelineError']("core group execution tuning is missing")
    projection = {
        key: tuning[key]
        for key in (
            "profile_id",
            "content_sha256",
            "properties",
            "compiler_argument_mapping_version",
            "compiler_arguments",
        )
    }
    if selection["tuning"] != projection:
        raise services['PipelineError']("core group execution tuning identity is stale")
    return tuning


def apply_group_output_expectations(
    *,
    artifact_validation: dict,
    metadata_validation: dict,
    group_selection: Mapping[str, object] | None,
    arch: str,
    services: BuildExecutionServices,
) -> None:
    """Apply the selected pin's exact per-ABI artifact acceptance oracle."""

    if group_selection is None:
        return
    expected_outputs = group_selection.get("expected_outputs")
    expected_target = (
        expected_outputs.get("targets", {}).get(arch)
        if isinstance(expected_outputs, services['Mapping'])
        else None
    )
    expected_artifact = (
        expected_target.get("artifact")
        if isinstance(expected_target, services['Mapping'])
        else None
    )
    if not isinstance(expected_artifact, services['Mapping']) or (
        artifact_validation.get("sha256") != expected_artifact.get("sha256")
        or artifact_validation.get("size") != expected_artifact.get("size")
    ):
        artifact_validation.setdefault("errors", []).append(
            "artifact does not match the selected core group pin"
        )
        artifact_validation["status"] = "invalid"
    expected_metadata = (
        expected_outputs.get("metadata")
        if isinstance(expected_outputs, services['Mapping'])
        else None
    )
    if not isinstance(expected_metadata, services['Mapping']) or (
        metadata_validation.get("sha256") != expected_metadata.get("sha256")
        or metadata_validation.get("size") != expected_metadata.get("size")
    ):
        metadata_validation.setdefault("errors", []).append(
            "metadata does not match the selected core group pin"
        )
        metadata_validation["status"] = "invalid"


def group_source_provenance_matches(
    *,
    group_selection: Mapping[str, object],
    recorded_commit: object,
    recorded_tree: object,
    recorded_url: object,
    recorded_submodules: object,
    raw_submodule_line_count: int | None,
    label: str,
    services: BuildExecutionServices,
) -> bool:
    """Compare live checkout provenance with the complete selected source."""

    expected = services['validated_group_execution_source'](
        group_selection.get("execution_source"),
        label=label,
    )
    if (
        not isinstance(recorded_submodules, list)
        or raw_submodule_line_count is None
        or raw_submodule_line_count != len(recorded_submodules)
    ):
        return False
    submodules: list[dict[str, str]] = []
    for item in recorded_submodules:
        if (
            not isinstance(item, services['Mapping'])
            or set(item) != set(services['GROUP_PIN_SUBMODULE_KEYS'])
            or item.get("state") != " "
        ):
            return False
        submodules.append({"path": item.get("path"), "commit": item.get("commit")})
    actual = {
        "url": recorded_url,
        # requested_ref selects operator intent; execution itself fetches and
        # checks the immutable commit, so the canonical selection supplies it.
        "requested_ref": expected["requested_ref"],
        "commit": recorded_commit,
        "tree": recorded_tree,
        "submodules": submodules,
    }
    return actual == expected


def perform_build(
    *,
    catalog_path: Path,
    catalog: dict,
    core_id: str,
    arch: str,
    output_dir: Path,
    group_selection: dict | None = None,
    tuning_selection: dict | None = None,
    execution_profile: HostExecutionProfile | None = None,
    host_execution: dict | None = None,
    telemetry_sink: list[dict] | None = None,
    services: BuildExecutionServices,
) -> dict:
    if group_selection is not None and tuning_selection is not None:
        raise services['PipelineError']("group and tuning-candidate execution are mutually exclusive")
    if core_id not in catalog["cores"]:
        raise services['PipelineError'](f"core is not in the build catalog: {core_id}")
    catalog_spec = catalog["cores"][core_id]
    spec = (
        services['group_execution_spec'](
            core_id=core_id,
            catalog_spec=catalog_spec,
            group_selection=group_selection,
        )
        if group_selection is not None
        else catalog_spec
    )
    if group_selection is None:
        source_candidate_contract_spec, source_candidate_projection = (
            services['source_candidate_contract_context'](
                catalog,
                core_id,
                catalog_path=catalog_path,
            )
        )
    else:
        source_candidate_projection = services['group_source_candidate_contract_projection'](
            core_id=core_id,
            catalog_spec=catalog_spec,
            execution_spec=spec,
            group_selection=group_selection,
        )
        source_candidate_contract_spec = (
            catalog_spec if source_candidate_projection is not None else spec
        )
    if arch not in spec["targets"]:
        raise services['PipelineError'](f"{core_id} does not enable target {arch}")
    group_tuning = services['_group_execution_tuning'](
        group_selection, core_id=core_id, arch=arch
    )
    candidate_selection = (
        services['validated_tuning_candidate_selection'](tuning_selection)
        if tuning_selection is not None
        else None
    )
    candidate_tuning = (
        services['copy'].deepcopy(candidate_selection["profile"])
        if candidate_selection is not None
        else None
    )
    if (
        candidate_tuning is not None
        and candidate_tuning.get("architecture") != arch
    ):
        raise services['PipelineError']("tuning candidate architecture does not match the build")
    execution_tuning = group_tuning or candidate_tuning
    expected_group_outputs = (
        group_selection.get("expected_outputs")
        if isinstance(group_selection, services['Mapping'])
        else None
    )
    expected_group_target = (
        expected_group_outputs.get("targets", {}).get(arch)
        if isinstance(expected_group_outputs, services['Mapping'])
        else None
    )
    if group_selection is not None and not isinstance(expected_group_target, services['Mapping']):
        raise services['PipelineError']("core group expected target output is missing")
    if group_selection is None:
        services['require_catalog_cores_eligible'](catalog, [core_id])
    else:
        services['require_source_commits_eligible'](catalog, [(core_id, spec["source"])])
    toolchain = catalog["toolchains"][services['build_toolchain_key'](spec, arch)]
    if (execution_profile is None) != (host_execution is None):
        raise services['PipelineError'](
            "host-build execution requires both a resolved profile and recipe contract"
        )
    if execution_profile is not None and telemetry_sink is None:
        raise services['PipelineError'](
            "admissible host-build execution requires a retained telemetry sink"
        )
    if host_execution is not None:
        host_execution = services['validate_host_execution_contract'](
            host_execution, repository_root=services['ROOT']
        )
        assert execution_profile is not None
        if (
            host_execution["resource_class"]["resource_class_id"]
            != execution_profile.resource_class_id
            or host_execution["resource_class"]["content_sha256"]
            != execution_profile.resource_class_content_sha256
            or host_execution["resources"] != execution_profile.resources()
            or host_execution["cache"] != execution_profile.cache()
        ):
            raise services['PipelineError']("host-build recipe contract differs from its profile")
    if execution_profile is not None and (
        spec["build"]["driver"] not in execution_profile.admissible_build_drivers
    ):
        raise services['PipelineError'](
            "host-build telemetry does not yet admit build driver "
            + spec["build"]["driver"]
        )
    compile_definitions = services['compile_definitions_for_target'](spec, arch)
    make_variables = services['validated_make_variables'](source_candidate_contract_spec)
    git_version = services['validated_git_version'](source_candidate_contract_spec)
    metadata_replacement = services['validated_metadata_replacement'](
        source_candidate_contract_spec
    )
    source_date_epoch = services['validated_source_date_epoch'](spec)
    expected_build_contract = services['normalized_build_contract'](
        spec,
        arch,
        core_id=core_id,
        source_candidate_contract_spec=(
            source_candidate_contract_spec
            if source_candidate_projection is not None
            else None
        ),
        source_candidate_projection=source_candidate_projection,
    )
    archive_provenance = services['expected_archive_provenance'](catalog, services['build_toolchain_key'](spec, arch))
    if output_dir.exists():
        raise services['PipelineError'](f"refusing to reuse build output directory: {output_dir}")
    output_dir.mkdir(parents=True)
    image_id = services['verify_image'](toolchain)
    script = services['container_build_script'](
        core_id,
        arch,
        spec,
        catalog["resolver"],
        None if execution_tuning is None else execution_tuning["profile_id"],
        jobs=None if execution_profile is None else execution_profile.jobs,
        instrumentation=execution_profile is not None,
        source_candidate_contract_spec=(
            source_candidate_contract_spec
            if source_candidate_projection is not None
            else None
        ),
        source_candidate_projection=source_candidate_projection,
    )
    log_path = output_dir / "build.log"
    print(f"local build: {core_id}/{arch} ({image_id[7:19]})", flush=True)
    started = services['utc_now']()
    build_mount_args = [
        *services['metadata_replacement_mount_args'](source_candidate_contract_spec),
        *services['overlay_mount_args'](spec, arch),
    ]
    execution: dict | None = None
    if execution_profile is not None:
        assert host_execution is not None
        execution = services['execute_instrumented_container'](
            repository_root=services['ROOT'],
            output_dir=output_dir,
            image_id=image_id,
            script=script,
            mount_args=build_mount_args,
            log_path=log_path,
            profile=execution_profile,
            instrumentation=host_execution["instrumentation"],
        )
        exit_code = execution["docker_state"]["exit_code"]
    else:
        command = [
            "docker",
            "run",
            "--rm",
            "-e",
            f"OUTPUT_UID={services['os'].getuid()}",
            "-e",
            f"OUTPUT_GID={services['os'].getgid()}",
            "-v",
            f"{output_dir.resolve()}:/output",
            *build_mount_args,
            image_id,
            "bash",
            "-lc",
            script,
        ]
        with log_path.open("w", encoding="utf-8") as log:
            process = services['subprocess'].Popen(
                command,
                cwd=services['ROOT'],
                text=True,
                stdout=services['subprocess'].PIPE,
                stderr=services['subprocess'].STDOUT,
            )
            assert process.stdout is not None
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
            exit_code = process.wait()
    validation_started_ns = services['time'].monotonic_ns()
    artifact_path = output_dir / spec["build"]["artifact_name"]
    metadata_path = output_dir / spec["metadata"]["artifact_name"]
    validation = services['apply_artifact_dependency_policy'](
        services['validate_artifact'](artifact_path, arch), spec
    )
    if execution is not None and (
        execution["docker_state"]["oom_killed"]
        or execution["resources"]["oom_observed"]
    ):
        validation.setdefault("errors", []).append(
            "host-build execution observed an OOM condition"
        )
        validation["status"] = "invalid"
    if compile_definitions:
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['compile_log_proves_definitions'](
            build_log_text, compile_definitions, arch
        ):
            validation.setdefault("errors", []).append(
                "catalog compile definitions were not observed together as exact "
                "tokens on a compiler -c command: "
                + ", ".join(compile_definitions)
            )
            validation["status"] = "invalid"
    if execution_tuning is not None:
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['chipset_tuning_log_proves_contract'](
            build_log_text,
            execution_tuning,
            arch,
            allow_no_target_compile=spec["build"]["driver"] == "direct-cargo",
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact selected chipset tuning contract"
            )
            validation["status"] = "invalid"
    if make_variables:
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['make_variable_log_proves_contract'](
            build_log_text, make_variables, arch
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact "
                + services['make_variable_contract_name'](make_variables)
                + " make-variable origin and compile contract"
            )
            validation["status"] = "invalid"
    if git_version is not None:
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['git_version_log_proves_contract'](
            build_log_text,
            git_version,
            spec["source"]["commit"],
            arch,
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact commit-derived GIT_VERSION "
                "GNU Make origin and target compile token"
            )
            validation["status"] = "invalid"
    log_contract = services['core_log_contract_for'](core_id)
    if log_contract is not None:
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['_registered_core_log_contract_proves'](
            build_log_text,
            core_id,
            arch,
            spec["source"]["commit"],
            spec["source"]["tree"],
            tuning=execution_tuning,
            source_candidate_projection=source_candidate_projection,
        ):
            validation.setdefault("errors", []).append(
                log_contract.failure_message
            )
            validation["status"] = "invalid"
    if metadata_replacement is not None:
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['metadata_replacement_log_proves_contract'](
            build_log_text, metadata_replacement
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact metadata replacement contract"
            )
            validation["status"] = "invalid"
    if spec["build"]["driver"] == "direct-cmake":
        build_log_text = services['read_build_log'](log_path, "build log")
        if not services['direct_cmake_log_proves_contract'](build_log_text, spec, arch):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact direct-CMake and overlay contract"
            )
            validation["status"] = "invalid"
    metadata_validation = {
        "path": metadata_path.name if metadata_path.is_file() else None,
        "status": "valid" if metadata_path.is_file() and metadata_path.stat().st_size else "invalid",
    }
    if metadata_validation["status"] == "valid":
        metadata_validation.update(
            {"size": metadata_path.stat().st_size, "sha256": services['sha256_file'](metadata_path)}
        )
    else:
        metadata_validation["errors"] = ["metadata file is missing or empty"]
    if not services['metadata_matches_replacement'](metadata_validation, metadata_replacement):
        metadata_validation.setdefault("errors", []).append(
            "metadata output does not match the exact catalog replacement"
        )
        metadata_validation["status"] = "invalid"
    services['apply_group_output_expectations'](
        artifact_validation=validation,
        metadata_validation=metadata_validation,
        group_selection=group_selection,
        arch=arch,
    )
    source_commit_path = output_dir / "source-commit.txt"
    recorded_commit = (
        source_commit_path.read_text(encoding="utf-8").strip()
        if source_commit_path.is_file()
        else None
    )
    source_tree_path = output_dir / "source-tree.txt"
    recorded_tree = (
        source_tree_path.read_text(encoding="utf-8").strip()
        if source_tree_path.is_file()
        else None
    )
    source_url_path = output_dir / "source-url.txt"
    recorded_url = (
        source_url_path.read_text(encoding="utf-8").strip()
        if source_url_path.is_file()
        else None
    )
    submodules_path = output_dir / "submodules.txt"
    recorded_submodules, raw_submodule_line_count = services['parse_submodule_provenance'](
        submodules_path
    )
    if recorded_commit != spec["source"]["commit"]:
        validation.setdefault("errors", []).append(
            f"source pin mismatch: expected {spec['source']['commit']}, got {recorded_commit}"
        )
        validation["status"] = "invalid"
    expected_tree = spec["source"].get("tree")
    if expected_tree is not None and recorded_tree != expected_tree:
        validation.setdefault("errors", []).append(
            f"source tree mismatch: expected {expected_tree}, got {recorded_tree}"
        )
        validation["status"] = "invalid"
    if recorded_url != spec["source"]["url"]:
        validation.setdefault("errors", []).append(
            f"source URL mismatch: expected {spec['source']['url']}, got {recorded_url}"
        )
        validation["status"] = "invalid"
    if group_selection is not None:
        if not services['group_source_provenance_matches'](
            group_selection=group_selection,
            recorded_commit=recorded_commit,
            recorded_tree=recorded_tree,
            recorded_url=recorded_url,
            recorded_submodules=recorded_submodules,
            raw_submodule_line_count=raw_submodule_line_count,
            label=f"{core_id} group execution source",
        ):
            validation.setdefault("errors", []).append(
                "live source provenance does not match the selected core group source"
            )
            validation["status"] = "invalid"
    recorded_source_date_epoch: int | None = None
    source_date_epoch_path = output_dir / "source-date-epoch.txt"
    if source_date_epoch_path.is_file():
        raw_source_date_epoch = source_date_epoch_path.read_text(
            encoding="utf-8"
        ).strip()
        if raw_source_date_epoch.isdecimal():
            recorded_source_date_epoch = int(raw_source_date_epoch)
    if recorded_source_date_epoch != source_date_epoch:
        validation.setdefault("errors", []).append(
            "source commit epoch mismatch: expected "
            f"{source_date_epoch}, got {recorded_source_date_epoch}"
        )
        validation["status"] = "invalid"
    recorded_build_contract = services['copy'].deepcopy(expected_build_contract)
    if source_date_epoch is not None:
        recorded_build_contract["source_date_epoch"] = recorded_source_date_epoch
    actual_resolver = {
        "libretro_super_commit": (
            (output_dir / "resolver-commit.txt").read_text(encoding="utf-8").strip()
            if (output_dir / "resolver-commit.txt").is_file()
            else None
        )
    }
    for prefix in ("core_rules", "fetch_script", "build_script"):
        value_path = output_dir / f"resolver-{prefix}-sha256.txt"
        actual_resolver[f"{prefix}_path"] = catalog["resolver"][f"{prefix}_path"]
        actual_resolver[f"{prefix}_sha256"] = (
            value_path.read_text(encoding="utf-8").strip() if value_path.is_file() else None
        )
    build_log_text = services['read_build_log'](log_path, "build log")
    validation_finished_ns = services['time'].monotonic_ns()
    result = (
        "passed"
        if exit_code == 0
        and validation["status"] == "valid"
        and metadata_validation["status"] == "valid"
        else "failed"
    )
    unit_evidence: dict | None = None
    source_hydration_phase: dict | None = None
    build_command_phase: dict | None = None
    bootstrap_evidence: dict | None = None
    if execution_profile is not None:
        bootstrap_evidence = services['parse_bootstrap_evidence'](output_dir)

        def phase_or_failed_unavailable(name: str, reason: str) -> dict:
            phase_root = output_dir / services['RAW_TELEMETRY_DIRECTORY'] / "phases"
            started_path = phase_root / f"{name}.started-ns"
            finished_path = phase_root / f"{name}.finished-ns"
            started_exists = started_path.exists() or started_path.is_symlink()
            finished_exists = finished_path.exists() or finished_path.is_symlink()
            if started_exists and finished_exists:
                return services['parse_measured_phase'](output_dir, name)
            if not started_exists and not finished_exists and result == "failed":
                return services['unavailable_observation'](reason)
            raise services['PipelineError'](
                f"host-build telemetry {name} phase observation is incomplete"
            )

        source_hydration_phase = phase_or_failed_unavailable(
            "source_hydration", "build-failed-before-source-hydration-phase"
        )
        build_command_phase = phase_or_failed_unavailable(
            "build_command", "build-failed-before-build-command-phase"
        )
        if build_command_phase["status"] == "measured":
            units_root = output_dir / services['RAW_TELEMETRY_DIRECTORY'] / "units"
            observations_path = (
                output_dir
                / services['RAW_TELEMETRY_DIRECTORY']
                / "nproc-observations.txt"
            )
            if units_root.is_symlink() or (
                units_root.exists() and not units_root.is_dir()
            ):
                raise services['PipelineError']("host-build compile-unit directory is invalid")
            unit_entries = list(units_root.iterdir()) if units_root.is_dir() else []
            if unit_entries or result == "passed":
                unit_evidence = services['parse_unit_evidence'](
                    output_dir,
                    source_dir=spec["build"]["source_dir"],
                    architecture=arch,
                    jobs=execution_profile.jobs,
                    build_log_text=build_log_text,
                    build_command_phase=build_command_phase,
                    require_complete=result == "passed",
                )
            else:
                if observations_path.is_symlink():
                    raise services['PipelineError']("host-build nproc observations are invalid")
                observations = (
                    observations_path.read_text(encoding="utf-8").splitlines()
                    if observations_path.is_file()
                    else []
                )
                if any(item != str(execution_profile.jobs) for item in observations):
                    raise services['PipelineError']("host-build nproc observations are invalid")
                services['validate_job_count_log'](
                    build_log_text,
                    execution_profile.jobs,
                    require_parallel_invocation=bool(observations),
                )
                unit_evidence = services['unavailable_observation'](
                    "no-compile-or-link-units-observed-before-build-failure",
                    configured_jobs=execution_profile.jobs,
                    nproc_observation_count=len(observations),
                    nproc_observations=observations,
                )
        else:
            services['validate_job_count_log'](
                build_log_text,
                execution_profile.jobs,
                require_parallel_invocation=False,
            )
            unit_evidence = services['unavailable_observation'](
                "no-compile-or-link-units-observed-before-build-failure",
                configured_jobs=execution_profile.jobs,
                nproc_observation_count=0,
                nproc_observations=[],
            )
    record = {
        "schema_version": 2,
        "local_only": True,
        "publication": "disabled",
        "started_at": started,
        "finished_at": services['utc_now'](),
        "core_id": core_id,
        "architecture": arch,
        "result": result,
        "build_exit_code": exit_code,
        "source": {
            **spec["source"],
            "resolved_commit": recorded_commit,
            "tree": recorded_tree,
            "resolved_url": recorded_url,
            "submodules": recorded_submodules,
        },
        "recipe": services['recipe_record'](
            catalog_path,
            core_id,
            spec,
            host_execution=host_execution,
        ),
        "toolchain": {
            **toolchain,
            "archive_provenance": archive_provenance,
            "resolved_image_id": image_id,
            "libretro_super_commit": actual_resolver["libretro_super_commit"],
            "resolver_digests": actual_resolver,
            "compiler": (
                (output_dir / "compiler.txt").read_text(encoding="utf-8").strip()
                if (output_dir / "compiler.txt").is_file()
                else None
            ),
            "sysroot": (
                (output_dir / "sysroot.txt").read_text(encoding="utf-8").strip()
                if (output_dir / "sysroot.txt").is_file()
                else None
            ),
        },
        "build": {
            **recorded_build_contract,
            "log": "build.log",
            "log_sha256": services['sha256_file'](log_path),
        },
        "artifact": {
            "path": artifact_path.name if artifact_path.is_file() else None,
            **validation,
        },
        "metadata": metadata_validation,
    }
    if group_selection is not None:
        record["core_group"] = services['copy'].deepcopy(group_selection)
        record["recipe"]["chipset_tuning"] = {
            "profile_id": group_selection["tuning"]["profile_id"],
            "content_sha256": group_selection["tuning"]["content_sha256"],
        }
    if candidate_selection is not None:
        record["tuning_candidate"] = services['copy'].deepcopy(candidate_selection)
        record["recipe"]["chipset_tuning"] = services['tuning_candidate_recipe_identity'](
            candidate_selection
        )
    services['atomic_write_json'](output_dir / "build-record.json", record)
    build_record_path = output_dir / "build-record.json"
    if execution_profile is None:
        print(f"result: {core_id}/{arch}: {result}", flush=True)
        return record
    assert execution is not None
    assert unit_evidence is not None
    assert source_hydration_phase is not None
    assert build_command_phase is not None
    assert bootstrap_evidence is not None
    assert host_execution is not None
    if unit_evidence.get("status") == "unavailable":
        compile_phase = services['unavailable_observation'](
            "no-compile-or-link-units-observed-before-build-failure"
        )
        link_phase = services['unavailable_observation'](
            "no-compile-or-link-units-observed-before-build-failure"
        )
    else:
        compile_phase = {
            "status": "measured",
            "clock": "CLOCK_MONOTONIC",
            **unit_evidence["phase_bounds"]["compile"],
        }
        link_phase = (
            {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                **unit_evidence["phase_bounds"]["link"],
            }
            if "link" in unit_evidence["phase_bounds"]
            else services['unavailable_observation'](
                "build-failed-before-link-unit-observed"
            )
        )
    telemetry_record = {
        "core_id": core_id,
        "architecture": arch,
        "driver": spec["build"]["driver"],
        "result": result,
        "bindings": {
            "build_record": {
                "path": str(build_record_path.relative_to(services['ROOT'])),
                "file_sha256": services['sha256_file'](build_record_path),
            },
            "source": services['copy'].deepcopy(record["source"]),
            "recipe": services['copy'].deepcopy(record["recipe"]),
            "toolchain": services['copy'].deepcopy(record["toolchain"]),
            "abi": {
                "architecture": arch,
                "elf_class": record["artifact"].get("elf_class"),
                "machine": record["artifact"].get("machine"),
                "interpreter": record["artifact"].get("interpreter"),
            },
            "tuning": services['copy'].deepcopy(
                record["recipe"].get("chipset_tuning")
            ),
            "outputs": {
                "artifact": {
                    "path": record["artifact"].get("path"),
                    "sha256": record["artifact"].get("sha256"),
                    "size": record["artifact"].get("size"),
                },
                "metadata": {
                    "path": record["metadata"].get("path"),
                    "sha256": record["metadata"].get("sha256"),
                    "size": record["metadata"].get("size"),
                },
                "build_log": {
                    "path": record["build"]["log"],
                    "sha256": record["build"]["log_sha256"],
                },
            },
        },
        "instrumentation": {
            "contract": services['copy'].deepcopy(host_execution["instrumentation"]),
            "bootstrap": bootstrap_evidence,
        },
        "phases": {
            "orchestration": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "duration_ns": execution["orchestration_duration_ns"],
            },
            "source_hydration": source_hydration_phase,
            "configure": services['not_applicable_phase'](
                "libretro-super-make-driver-has-no-separate-configure-phase"
            ),
            "build_command": build_command_phase,
            "compile": compile_phase,
            "link": link_phase,
            "validation": {
                "status": "measured",
                "clock": "CLOCK_MONOTONIC",
                "duration_ns": validation_finished_ns - validation_started_ns,
            },
        },
        "container": {
            "container_id": execution["container_id"],
            "requested_host_config": execution["requested_host_config"],
            "state": execution["docker_state"],
            "execution_duration_ns": execution["container_execution_duration_ns"],
        },
        "resources": execution["resources"],
        "units": unit_evidence,
    }
    telemetry_sink.append(telemetry_record)
    print(f"result: {core_id}/{arch}: {result}", flush=True)
    return record
