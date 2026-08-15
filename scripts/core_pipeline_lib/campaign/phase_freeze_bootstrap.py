"""Read-only repository bootstrap for the first strict phase freeze.

The strict phase-freeze policy in :mod:`campaign.phase_freeze` intentionally
accepts hydrated bytes only.  This module is the small repository adapter for
that pure boundary: it snapshots the maintained authorities, constructs the
registered bootstrap intent and request in memory, and asks the pure planner
to reconstruct and validate the result.

There is deliberately no clock, Git, audit, store publication, mutable
pointer, or CLI surface here.  The legacy predecessor is authenticated only
by its reviewed raw and semantic identities; its historical JSON shape is
never decoded or imported.  The engine bundle is derived from the current
tracked Python source in memory, so a tracked self-hashing bundle is neither
needed nor accepted as an implicit build step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Final, Mapping

from ..chipsets import chipset_tunings_content_sha256, validate_chipset_tunings
from ..core_spec import decode_core_spec_set, render_core_spec_set
from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..immutable_evidence import toolchain_lock_content_sha256
from ..policy.blacklist import parse_commit_blacklist_bytes
from ..source_bundle import (
    PIPELINE_LAUNCHER_MODE,
    PIPELINE_LAUNCHER_RELATIVE,
    PIPELINE_PACKAGE_ROOT_RELATIVE,
    REPOSITORY_ROOT,
    REPOSITORY_SOURCE_MODE,
    RepositorySourceCapture,
    RepositorySourceFileSet,
    RepositorySourceMember,
    capture_repository_sources,
    pipeline_source_bundle_from_members,
    pipeline_source_bundle_is_well_formed,
)
from ..spruce_branch_bases import (
    spruce_branch_bases_content_sha256,
    validate_spruce_branch_bases,
)
from ..tracks import (
    core_tracks_content_sha256,
    spruce_release_roster_content_sha256,
    spruce_release_roster_errors,
)
from .json_wire import (
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
)
from .model import EvidenceRef
from .phase_freeze import (
    BOOTSTRAP_KIND,
    CAMPAIGN_STATE_RELATIVE,
    PHASE_FREEZE_SCHEMA_PATH,
    PlannedPhaseFreeze,
    plan_phase_freeze,
    validate_phase_freeze,
)
from .store import CampaignStore
from .transition_model import (
    AuthenticatedInput,
    NamedEvidenceRef,
    TransitionIntentV1,
    TransitionRequest,
)
from .transition_registry import INPUT_ROLE_NAMES, definition_for


CAMPAIGN_ID: Final = "host-core-build-20260810"
DEFAULT_TRANSITION_ID: Final = (
    "post-gambatte-admission-phase-freeze-bootstrap-v1"
)
DEFAULT_REASON: Final = (
    "Bootstrap the first strict phase-freeze authority after Gambatte "
    "track admission."
)

LEGACY_PREDECESSOR_PATH: Final = (
    ".local-e2e/campaigns/host-core-build-20260810/freezes/phase1/"
    "0c57e20111a6c704c1481993f60fcce0b58cf1c52b00cbd4b969aab18fb7de1c.json"
)
LEGACY_PREDECESSOR_CONTENT_SHA256: Final = (
    "0c57e20111a6c704c1481993f60fcce0b58cf1c52b00cbd4b969aab18fb7de1c"
)
LEGACY_PREDECESSOR_FILE_SHA256: Final = (
    "6bdeb20ef855ceb47e2825726edb7280953e60f883f2e45d716c6c0c03d2f70f"
)
LEGACY_PREDECESSOR_SIZE: Final = 281_849

CATALOG_PATH: Final = "manifests/core-builds.json"
CORE_SPEC_SET_PATH: Final = "manifests/core-spec-sets/catalog-v1.json"
TRACKS_PATH: Final = "manifests/core-tracks.json"
TUNINGS_PATH: Final = "manifests/chipset-tunings.json"
BRANCH_BASES_PATH: Final = "manifests/spruce-core-branch-bases.json"
RELEASE_ROSTER_PATH: Final = "manifests/spruce-release-roster.json"
BLACKLIST_PATH: Final = "policies/core-commit-blacklist.json"
TOOLCHAIN_LOCK_PATH: Final = "pins/toolchains/local-cache-v1.json"
HOST_EXECUTION_PATH: Final = "manifests/host-build-execution-profiles.json"
HOST_EXECUTION_SCHEMA_PATH: Final = (
    "manifests/host-build-execution-profiles.schema.json"
)
TELEMETRY_SCHEMA_PATH: Final = "manifests/host-build-telemetry.schema.json"
WORKFLOW_ROOT: Final = ".github/workflows"

_INSTRUMENTATION_PATHS: Final = (
    "scripts/host_build_tool_wrapper.sh",
    "scripts/host_build_unit_runner.c",
)
_DIRECT_AUTHORITY_PATHS: Final = (
    BLACKLIST_PATH,
    BRANCH_BASES_PATH,
    CATALOG_PATH,
    CORE_SPEC_SET_PATH,
    HOST_EXECUTION_PATH,
    HOST_EXECUTION_SCHEMA_PATH,
    PHASE_FREEZE_SCHEMA_PATH,
    RELEASE_ROSTER_PATH,
    TELEMETRY_SCHEMA_PATH,
    TOOLCHAIN_LOCK_PATH,
    TRACKS_PATH,
    TUNINGS_PATH,
)
_FILE_SET_FORMAT: Final = "spruce-repository-file-set-v1"


SemanticDigest = Callable[[Mapping[str, object]], str]


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedRepositoryPhaseFreezeBootstrap:
    """One authenticated repository request and its validated pure result."""

    request: TransitionRequest
    result: PlannedPhaseFreeze
    source_members: tuple[RepositorySourceMember, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not TransitionRequest:
            raise PipelineError("repository bootstrap request is invalid")
        if type(self.result) is not PlannedPhaseFreeze:
            raise PipelineError("repository bootstrap result is invalid")
        if type(self.source_members) is not tuple or any(
            type(item) is not RepositorySourceMember for item in self.source_members
        ):
            raise PipelineError("repository bootstrap source members are invalid")
        paths = tuple(item.path for item in self.source_members)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise PipelineError(
                "repository bootstrap source members must be sorted and unique"
            )
        _validate_source_member_closure(self.request, self.source_members)
        validate_phase_freeze(self.result, request=self.request)


def _require_repository_root(repository_root: object) -> Path:
    if not isinstance(repository_root, Path) or not repository_root.is_absolute():
        raise PipelineError("phase-freeze repository root must be an absolute Path")
    expected = REPOSITORY_ROOT.absolute()
    if repository_root.absolute() != expected:
        raise PipelineError(
            "phase-freeze repository root differs from the loaded pipeline source"
        )
    return repository_root


def _require_relative_path(value: object, *, label: str) -> str:
    if type(value) is not str or not value or "\\" in value or "//" in value:
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return value


def _read_document(
    sources: Mapping[str, RepositorySourceMember],
    path: str,
    *,
    label: str,
) -> tuple[bytes, dict[str, object]]:
    raw = _source_raw(sources, path, label=label)
    return raw, decode_identity_object(raw, label=label)


def _source_raw(
    sources: Mapping[str, RepositorySourceMember],
    path: str,
    *,
    label: str,
) -> bytes:
    member = sources.get(path)
    if type(member) is not RepositorySourceMember:
        raise PipelineError(f"{label} is absent from the repository source capture")
    return member.raw


def _validate_source_member_closure(
    request: TransitionRequest,
    members: tuple[RepositorySourceMember, ...],
) -> None:
    sources = {member.path: member for member in members}
    bound_paths = {HOST_EXECUTION_SCHEMA_PATH}
    for member in members:
        expected_mode = (
            PIPELINE_LAUNCHER_MODE
            if member.path == PIPELINE_LAUNCHER_RELATIVE
            else REPOSITORY_SOURCE_MODE
        )
        if member.mode != expected_mode:
            raise PipelineError(
                f"repository bootstrap source member mode is invalid: {member.path}"
            )

    synthetic_roles = {"instrumentation", "recipe-auxiliaries", "workflows"}
    by_name = {item.name: item for item in request.inputs}
    if set(by_name) != set(INPUT_ROLE_NAMES):
        raise PipelineError("repository bootstrap source roles are incomplete")
    for name, item in by_name.items():
        if name not in synthetic_roles:
            member = sources.get(item.reference.path)
            if member is None or member.raw != item.raw:
                raise PipelineError(
                    f"repository bootstrap source closure is stale for {name}"
                )
            bound_paths.add(member.path)
            continue
        document = decode_identity_object(
            item.raw,
            label=f"repository bootstrap {name} file set",
        )
        files = document.get("files")
        if type(files) is not dict or not files:
            raise PipelineError(
                f"repository bootstrap {name} file-set closure is invalid"
            )
        for path, identity in files.items():
            member = sources.get(path) if type(path) is str else None
            if (
                member is None
                or type(identity) is not dict
                or identity.get("file_sha256") != sha256_bytes(member.raw)
                or identity.get("size") != len(member.raw)
            ):
                raise PipelineError(
                    f"repository bootstrap {name} member closure is stale"
                )
            bound_paths.add(member.path)

    engine = decode_identity_object(
        request.engine_bundle_raw,
        label="repository bootstrap engine bundle",
    )
    if not pipeline_source_bundle_is_well_formed(engine):
        raise PipelineError("repository bootstrap engine bundle is invalid")
    engine_files = engine.get("files")
    assert type(engine_files) is dict
    for path, digest in engine_files.items():
        member = sources.get(path) if type(path) is str else None
        if member is None or digest != sha256_bytes(member.raw):
            raise PipelineError("repository bootstrap engine member closure is stale")
        bound_paths.add(member.path)

    host_schema = sources.get(HOST_EXECUTION_SCHEMA_PATH)
    host_input = by_name["host-execution"]
    host_document = decode_identity_object(
        host_input.raw,
        label="repository bootstrap host execution",
    )
    if (
        host_schema is None
        or host_document.get("schema_file_sha256")
        != sha256_bytes(host_schema.raw)
    ):
        raise PipelineError("repository bootstrap host schema closure is stale")
    if bound_paths != set(sources):
        raise PipelineError("repository bootstrap source closure has unbound members")


def _reference(
    *,
    kind: str,
    path: str,
    raw: bytes,
    semantic_sha256: str,
) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,
        path=path,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=semantic_sha256,
        size=len(raw),
    )


def _declared_semantic(
    document: Mapping[str, object],
    *,
    digest: SemanticDigest,
    label: str,
) -> str:
    declared = document.get("content_sha256")
    actual = digest(document)
    if type(declared) is not str or declared != actual:
        raise PipelineError(f"{label} semantic identity is stale")
    return actual


def _semantic_without_content(document: Mapping[str, object]) -> str:
    return canonical_json_sha256(
        {key: value for key, value in document.items() if key != "content_sha256"}
    )


def _file_set_input(
    sources: Mapping[str, RepositorySourceMember],
    *,
    role: str,
    paths: tuple[str, ...],
) -> AuthenticatedInput:
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)) or not paths:
        raise PipelineError(f"{role} file set must be sorted, unique, and nonempty")
    files: dict[str, object] = {}
    for path in paths:
        _require_relative_path(path, label=f"{role} file-set path")
        raw = _source_raw(
            sources,
            path,
            label=f"{role} file-set member",
        )
        files[path] = {
            "file_sha256": sha256_bytes(raw),
            "size": len(raw),
        }
    material: dict[str, object] = {
        "schema_version": 1,
        "format": _FILE_SET_FORMAT,
        "role": role,
        "files": files,
    }
    semantic = canonical_json_sha256(material)
    document = {**material, "content_sha256": semantic}
    raw = rendered_json_bytes(document)
    return AuthenticatedInput(
        name=role,
        reference=_reference(
            kind="artifact",
            path=f"campaign/evidence/{role}-file-set-v1.json",
            raw=raw,
            semantic_sha256=semantic,
        ),
        raw=raw,
    )


def _catalog_reference_paths(catalog: Mapping[str, object]) -> tuple[str, ...]:
    cores = catalog.get("cores")
    toolchains = catalog.get("toolchains")
    if type(cores) is not dict or type(toolchains) is not dict:
        raise PipelineError("core catalog reference roots are invalid")
    paths: set[str] = set()
    for core_id, value in cores.items():
        if type(core_id) is not str or type(value) is not dict:
            raise PipelineError("core catalog recipe entries are invalid")
        workflow = value.get("workflow")
        paths.add(_require_relative_path(workflow, label=f"{core_id} workflow"))
        build = value.get("build")
        if type(build) is not dict:
            raise PipelineError(f"{core_id} build recipe is invalid")
        overlays = build.get("overlays", {})
        if type(overlays) is not dict:
            raise PipelineError(f"{core_id} overlay map is invalid")
        for entries in overlays.values():
            if type(entries) is not list:
                raise PipelineError(f"{core_id} overlay entries are invalid")
            for entry in entries:
                if type(entry) is not dict:
                    raise PipelineError(f"{core_id} overlay entry is invalid")
                paths.add(
                    _require_relative_path(
                        entry.get("patch_path"),
                        label=f"{core_id} overlay patch",
                    )
                )
        metadata = value.get("metadata", {})
        if type(metadata) is not dict:
            raise PipelineError(f"{core_id} metadata is invalid")
        replacement = metadata.get("replacement")
        if replacement is not None:
            if type(replacement) is not dict:
                raise PipelineError(f"{core_id} replacement metadata is invalid")
            paths.add(
                _require_relative_path(
                    replacement.get("path"),
                    label=f"{core_id} replacement path",
                )
            )
        repo_path = metadata.get("repo_path")
        if repo_path is not None:
            paths.add(
                _require_relative_path(
                    repo_path,
                    label=f"{core_id} repository path",
                )
            )
    for architecture, value in toolchains.items():
        if type(architecture) is not str or type(value) is not dict:
            raise PipelineError("core catalog toolchain entries are invalid")
        paths.add(
            _require_relative_path(
                value.get("dockerfile"),
                label=f"{architecture} Dockerfile",
            )
        )
    paths.update(("Dockerfile.arm64.base", "Dockerfile.armhf.base"))
    for key, label in (
        ("toolchain_lock", "toolchain lock"),
        ("toolchain_lock_validator", "toolchain lock validator"),
        ("commit_blacklist", "commit blacklist"),
    ):
        value = catalog.get(key)
        if type(value) is not dict:
            raise PipelineError(f"core catalog {label} reference is invalid")
        paths.add(
            _require_relative_path(
                value.get("path"),
                label=f"core catalog {label} path",
            )
        )
    return tuple(sorted(paths))


def _workflow_paths(
    sources: Mapping[str, RepositorySourceMember],
) -> tuple[str, ...]:
    prefix = f"{WORKFLOW_ROOT}/"
    paths = tuple(
        sorted(
            path
            for path in sources
            if path.startswith(prefix) and path.endswith((".yaml", ".yml"))
        )
    )
    if not paths or len(paths) != len(set(paths)):
        raise PipelineError("workflow authority set is empty or duplicated")
    return paths


def _capture_repository_sources(
    reader: CampaignStore,
    repository_root: Path,
) -> RepositorySourceCapture:
    """Capture every physical authority and engine member in one window."""

    discovery_raw = reader.read_snapshot(CATALOG_PATH)
    discovery = decode_identity_object(
        discovery_raw,
        label="phase-freeze core catalog discovery",
    )
    exact_paths = set(_DIRECT_AUTHORITY_PATHS)
    exact_paths.update(_INSTRUMENTATION_PATHS)
    exact_paths.update(_catalog_reference_paths(discovery))
    exact_modes = {path: REPOSITORY_SOURCE_MODE for path in exact_paths}
    if (
        PIPELINE_LAUNCHER_RELATIVE in exact_modes
        and exact_modes[PIPELINE_LAUNCHER_RELATIVE] != PIPELINE_LAUNCHER_MODE
    ):
        raise PipelineError(
            "pipeline launcher conflicts with a repository authority mode"
        )
    exact_modes[PIPELINE_LAUNCHER_RELATIVE] = PIPELINE_LAUNCHER_MODE
    capture = capture_repository_sources(
        repository_root=repository_root,
        exact_file_modes=exact_modes,
        file_sets=(
            RepositorySourceFileSet(
                root=WORKFLOW_ROOT,
                suffixes=(".yaml", ".yml"),
                recursive=False,
                mode=REPOSITORY_SOURCE_MODE,
                label="workflow authority",
            ),
            RepositorySourceFileSet(
                root=PIPELINE_PACKAGE_ROOT_RELATIVE,
                suffixes=(".py",),
                recursive=True,
                mode=REPOSITORY_SOURCE_MODE,
                label="pipeline package entry",
            ),
        ),
    )
    sources = {member.path: member for member in capture.members}
    captured_catalog = _source_raw(
        sources,
        CATALOG_PATH,
        label="phase-freeze core catalog",
    )
    if captured_catalog != discovery_raw:
        raise PipelineError("core catalog moved during repository source discovery")
    return capture


def _direct_input(
    *,
    name: str,
    kind: str,
    path: str,
    raw: bytes,
    semantic_sha256: str,
) -> AuthenticatedInput:
    return AuthenticatedInput(
        name=name,
        reference=_reference(
            kind=kind,
            path=path,
            raw=raw,
            semantic_sha256=semantic_sha256,
        ),
        raw=raw,
    )


def _authority_inputs(
    source_capture: RepositorySourceCapture,
) -> tuple[AuthenticatedInput, ...]:
    sources = {member.path: member for member in source_capture.members}
    catalog_raw, catalog = _read_document(
        sources, CATALOG_PATH, label="phase-freeze core catalog"
    )
    catalog_semantic = canonical_json_sha256(catalog)

    core_spec_raw = _source_raw(
        sources,
        CORE_SPEC_SET_PATH,
        label="tracked CoreSpec set",
    )
    core_spec_set = decode_core_spec_set(core_spec_raw)
    if render_core_spec_set(core_spec_set) != core_spec_raw:
        raise PipelineError("tracked CoreSpec set bytes are not canonical")
    catalog_reference = _reference(
        kind="artifact",
        path=CATALOG_PATH,
        raw=catalog_raw,
        semantic_sha256=catalog_semantic,
    )
    if core_spec_set.catalog != catalog_reference:
        raise PipelineError("tracked CoreSpec set does not bind the live catalog")

    blacklist_raw, _blacklist_document = _read_document(
        sources, BLACKLIST_PATH, label="phase-freeze commit blacklist"
    )
    try:
        blacklist = parse_commit_blacklist_bytes(
            blacklist_raw, "phase-freeze commit blacklist"
        )
    except ValueError as exc:
        raise PipelineError(f"commit blacklist authority is invalid: {exc}") from exc

    host_raw, host = _read_document(
        sources, HOST_EXECUTION_PATH, label="phase-freeze host execution"
    )
    host_semantic = _declared_semantic(
        host,
        digest=_semantic_without_content,
        label="host execution authority",
    )
    host_schema_raw, _host_schema = _read_document(
        sources,
        HOST_EXECUTION_SCHEMA_PATH,
        label="host execution schema",
    )
    if host.get("schema_file_sha256") != sha256_bytes(host_schema_raw):
        raise PipelineError("host execution schema binding is stale")

    schema_raw, schema = _read_document(
        sources, PHASE_FREEZE_SCHEMA_PATH, label="phase-freeze schema"
    )
    telemetry_raw, telemetry_schema = _read_document(
        sources, TELEMETRY_SCHEMA_PATH, label="host telemetry schema"
    )

    branch_raw, branch_bases = _read_document(
        sources, BRANCH_BASES_PATH, label="Spruce branch bases"
    )
    roster_raw, roster = _read_document(
        sources, RELEASE_ROSTER_PATH, label="Spruce release roster"
    )
    roster_errors = spruce_release_roster_errors(roster, catalog=catalog)
    if roster_errors:
        raise PipelineError(
            "Spruce release roster authority is invalid:\n- "
            + "\n- ".join(roster_errors)
        )
    validate_spruce_branch_bases(
        branch_bases,
        catalog=catalog,
        catalog_file_sha256=sha256_bytes(catalog_raw),
        roster_file_sha256=sha256_bytes(roster_raw),
        release_roster=roster,
    )

    toolchain_raw, toolchain = _read_document(
        sources, TOOLCHAIN_LOCK_PATH, label="toolchain lock"
    )
    toolchain_semantic = _declared_semantic(
        toolchain,
        digest=lambda value: toolchain_lock_content_sha256(dict(value)),
        label="toolchain lock authority",
    )

    tracks_raw, tracks = _read_document(
        sources, TRACKS_PATH, label="core track registry"
    )
    tracks_semantic = _declared_semantic(
        tracks,
        digest=core_tracks_content_sha256,
        label="core track authority",
    )

    tunings_raw, tunings = _read_document(
        sources, TUNINGS_PATH, label="chipset tuning registry"
    )
    tunings = validate_chipset_tunings(tunings)
    tunings_semantic = _declared_semantic(
        tunings,
        digest=chipset_tunings_content_sha256,
        label="chipset tuning authority",
    )

    by_name = {
        "catalog": _direct_input(
            name="catalog",
            kind="artifact",
            path=CATALOG_PATH,
            raw=catalog_raw,
            semantic_sha256=catalog_semantic,
        ),
        "commit-blacklist": _direct_input(
            name="commit-blacklist",
            kind="artifact",
            path=BLACKLIST_PATH,
            raw=blacklist_raw,
            semantic_sha256=blacklist.content_sha256,
        ),
        "core-spec-set": _direct_input(
            name="core-spec-set",
            kind="artifact",
            path=CORE_SPEC_SET_PATH,
            raw=core_spec_raw,
            semantic_sha256=core_spec_set.content_sha256,
        ),
        "host-execution": _direct_input(
            name="host-execution",
            kind="artifact",
            path=HOST_EXECUTION_PATH,
            raw=host_raw,
            semantic_sha256=host_semantic,
        ),
        "instrumentation": _file_set_input(
            sources,
            role="instrumentation",
            paths=_INSTRUMENTATION_PATHS,
        ),
        "recipe-auxiliaries": _file_set_input(
            sources,
            role="recipe-auxiliaries",
            paths=_catalog_reference_paths(catalog),
        ),
        "schemas": _direct_input(
            name="schemas",
            kind="artifact",
            path=PHASE_FREEZE_SCHEMA_PATH,
            raw=schema_raw,
            semantic_sha256=canonical_json_sha256(schema),
        ),
        "spruce-branch-bases": _direct_input(
            name="spruce-branch-bases",
            kind="artifact",
            path=BRANCH_BASES_PATH,
            raw=branch_raw,
            semantic_sha256=_declared_semantic(
                branch_bases,
                digest=spruce_branch_bases_content_sha256,
                label="Spruce branch bases authority",
            ),
        ),
        "spruce-release-roster": _direct_input(
            name="spruce-release-roster",
            kind="artifact",
            path=RELEASE_ROSTER_PATH,
            raw=roster_raw,
            semantic_sha256=_declared_semantic(
                roster,
                digest=spruce_release_roster_content_sha256,
                label="Spruce release roster authority",
            ),
        ),
        "telemetry-schema": _direct_input(
            name="telemetry-schema",
            kind="artifact",
            path=TELEMETRY_SCHEMA_PATH,
            raw=telemetry_raw,
            semantic_sha256=canonical_json_sha256(telemetry_schema),
        ),
        "toolchain-lock": _direct_input(
            name="toolchain-lock",
            kind="artifact",
            path=TOOLCHAIN_LOCK_PATH,
            raw=toolchain_raw,
            semantic_sha256=toolchain_semantic,
        ),
        "tracks": _direct_input(
            name="tracks",
            kind="track-registry",
            path=TRACKS_PATH,
            raw=tracks_raw,
            semantic_sha256=tracks_semantic,
        ),
        "tunings": _direct_input(
            name="tunings",
            kind="artifact",
            path=TUNINGS_PATH,
            raw=tunings_raw,
            semantic_sha256=tunings_semantic,
        ),
        "workflows": _file_set_input(
            sources,
            role="workflows",
            paths=_workflow_paths(sources),
        ),
    }
    if tuple(sorted(by_name)) != INPUT_ROLE_NAMES:
        raise PipelineError("repository authorities differ from registered roles")
    return tuple(by_name[name] for name in INPUT_ROLE_NAMES)


def _legacy_predecessor(reader: CampaignStore) -> tuple[EvidenceRef, bytes]:
    raw = reader.read_snapshot(LEGACY_PREDECESSOR_PATH)
    reference = _reference(
        kind="phase-freeze",
        path=LEGACY_PREDECESSOR_PATH,
        raw=raw,
        semantic_sha256=LEGACY_PREDECESSOR_CONTENT_SHA256,
    )
    if (
        reference.file_sha256 != LEGACY_PREDECESSOR_FILE_SHA256
        or reference.size != LEGACY_PREDECESSOR_SIZE
    ):
        raise PipelineError("opaque legacy phase-freeze predecessor moved")
    return reference, raw


def _engine_bundle(
    source_capture: RepositorySourceCapture,
) -> tuple[dict[str, object], bytes]:
    document = pipeline_source_bundle_from_members(source_capture.members)
    if not pipeline_source_bundle_is_well_formed(document):
        raise PipelineError("live phase-freeze engine bundle is invalid")
    raw = rendered_json_bytes(document)
    return document, raw


@dataclass(frozen=True, slots=True, kw_only=True)
class _CollectedRepositoryPhaseFreezeBootstrap:
    request: TransitionRequest
    source_capture: RepositorySourceCapture


def _collect_repository_phase_freeze_bootstrap(
    *,
    repository_root: Path,
    captured_at: str,
    transition_id: str,
    reason: str,
) -> _CollectedRepositoryPhaseFreezeBootstrap:
    root = _require_repository_root(repository_root)
    reader = CampaignStore(root, CAMPAIGN_STATE_RELATIVE)
    definition = definition_for(BOOTSTRAP_KIND)
    source_capture = _capture_repository_sources(reader, root)
    inputs = _authority_inputs(source_capture)
    predecessor, predecessor_raw = _legacy_predecessor(reader)
    intent = TransitionIntentV1(
        transition_id=transition_id,
        campaign_id=CAMPAIGN_ID,
        kind=definition.kind,
        captured_at=captured_at,
        reason=reason,
        predecessor=predecessor,
        inputs=tuple(
            NamedEvidenceRef(name=item.name, reference=item.reference)
            for item in inputs
        ),
        changed_authorities=tuple(role.name for role in definition.input_roles),
    )
    spec_raw = rendered_json_bytes(intent.to_document())
    spec_ref = _reference(
        kind="transition-spec",
        path=definition.spec_path_template.format(transition_id=transition_id),
        raw=spec_raw,
        semantic_sha256=intent.content_sha256,
    )
    engine_document, engine_raw = _engine_bundle(source_capture)
    engine_semantic = engine_document.get("content_sha256")
    if type(engine_semantic) is not str:
        raise PipelineError("phase-freeze engine bundle has no semantic identity")
    engine_ref = _reference(
        kind="engine-bundle",
        path=definition.engine_bundle_path_template.format(
            transition_id=transition_id
        ),
        raw=engine_raw,
        semantic_sha256=engine_semantic,
    )
    return _CollectedRepositoryPhaseFreezeBootstrap(
        request=TransitionRequest(
            spec_ref=spec_ref,
            spec_raw=spec_raw,
            engine_bundle_ref=engine_ref,
            engine_bundle_raw=engine_raw,
            predecessor_raw=predecessor_raw,
            inputs=inputs,
        ),
        source_capture=source_capture,
    )


def collect_repository_phase_freeze_bootstrap(
    *,
    repository_root: Path,
    captured_at: str,
    transition_id: str = DEFAULT_TRANSITION_ID,
    reason: str = DEFAULT_REASON,
) -> TransitionRequest:
    """Hydrate one exact registered bootstrap request without mutating state."""

    return _collect_repository_phase_freeze_bootstrap(
        repository_root=repository_root,
        captured_at=captured_at,
        transition_id=transition_id,
        reason=reason,
    ).request


def capture_repository_phase_freeze_sources(
    *,
    repository_root: Path,
) -> RepositorySourceCapture:
    """Capture the bootstrap's complete source policy without selecting a root.

    This is the shared read-only descriptor boundary for historical/live
    provenance comparisons.  Unlike the repository bootstrap planner it does
    not require ``repository_root`` to be the source tree that loaded this
    module; it performs no planning and reads no legacy predecessor.
    """

    if not isinstance(repository_root, Path) or not repository_root.is_absolute():
        raise PipelineError(
            "phase-freeze source capture root must be an absolute Path"
        )
    return _capture_repository_sources(
        CampaignStore(repository_root, CAMPAIGN_STATE_RELATIVE),
        repository_root,
    )


def plan_repository_phase_freeze_bootstrap(
    *,
    repository_root: Path,
    captured_at: str,
    transition_id: str = DEFAULT_TRANSITION_ID,
    reason: str = DEFAULT_REASON,
) -> PlannedRepositoryPhaseFreezeBootstrap:
    """Double-snapshot, plan, and independently validate one bootstrap."""

    arguments = {
        "repository_root": repository_root,
        "captured_at": captured_at,
        "transition_id": transition_id,
        "reason": reason,
    }
    first = _collect_repository_phase_freeze_bootstrap(**arguments)
    second = _collect_repository_phase_freeze_bootstrap(**arguments)
    if first != second:
        raise PipelineError("phase-freeze repository authorities moved during capture")
    result = plan_phase_freeze(first.request)
    validate_phase_freeze(result, request=first.request)
    return PlannedRepositoryPhaseFreezeBootstrap(
        request=first.request,
        result=result,
        source_members=first.source_capture.members,
    )


__all__ = [
    "CAMPAIGN_ID",
    "DEFAULT_REASON",
    "DEFAULT_TRANSITION_ID",
    "LEGACY_PREDECESSOR_CONTENT_SHA256",
    "LEGACY_PREDECESSOR_FILE_SHA256",
    "LEGACY_PREDECESSOR_PATH",
    "LEGACY_PREDECESSOR_SIZE",
    "PlannedRepositoryPhaseFreezeBootstrap",
    "capture_repository_phase_freeze_sources",
    "collect_repository_phase_freeze_bootstrap",
    "plan_repository_phase_freeze_bootstrap",
]
