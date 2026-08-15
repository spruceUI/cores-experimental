"""Static policy registry for generic campaign transitions.

The registry contains reviewed data only.  It has no runtime registration,
dynamic import, module path, handler discovery, or dispatch surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from types import MappingProxyType

from ..errors import PipelineError
from .json_wire import validate_utf8_string
from .model import EVIDENCE_KINDS
from .transition_model import INTENT_FORMAT, PROCESS_TIERS


IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
TEMPLATE_TOKEN = "{transition_id}"
SPEC_PATH_TEMPLATE = "manifests/campaign-transitions/{transition_id}.json"
ENGINE_BUNDLE_PATH_TEMPLATE = (
    "manifests/campaign-engine-bundles/{transition_id}.json"
)
PHASE_FREEZE_FORMAT = "spruce-phase-freeze-v1"

REQUIRED_ENGINE_MEMBERS = (
    "scripts/core_pipeline_lib/campaign/json_wire.py",
    "scripts/core_pipeline_lib/campaign/model.py",
    "scripts/core_pipeline_lib/campaign/phase_freeze.py",
    "scripts/core_pipeline_lib/campaign/projection.py",
    "scripts/core_pipeline_lib/campaign/transition_model.py",
    "scripts/core_pipeline_lib/campaign/transition_registry.py",
    "scripts/core_pipeline_lib/core_spec.py",
)

INPUT_ROLE_NAMES = (
    "catalog",
    "commit-blacklist",
    "core-spec-set",
    "host-execution",
    "instrumentation",
    "recipe-auxiliaries",
    "schemas",
    "spruce-branch-bases",
    "spruce-release-roster",
    "telemetry-schema",
    "toolchain-lock",
    "tracks",
    "tunings",
    "workflows",
)

BOOTSTRAP_REQUIRED_CHECKS = (
    "campaign.plan.identity",
    "phase-freeze.inputs.identity",
    "phase-freeze.core-spec-set",
    "phase-freeze.legacy-lineage",
    "phase-freeze.schema",
    "phase-freeze.successor.identity",
    "publication.disabled",
)

REFRESH_REQUIRED_CHECKS = (
    "campaign.plan.identity",
    "phase-freeze.inputs.identity",
    "phase-freeze.core-spec-set",
    "phase-freeze.delta",
    "phase-freeze.schema",
    "phase-freeze.successor.identity",
    "publication.disabled",
)


def _require_identifier(value: object, label: str) -> str:
    if type(value) is not str or not IDENTIFIER_RE.fullmatch(value):
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_sorted_unique_strings(
    values: object,
    *,
    label: str,
    registered_kinds: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PipelineError(f"{label} must be a tuple")
    if any(type(item) is not str or not item for item in values):
        raise PipelineError(f"{label} must contain nonempty exact strings")
    if values != tuple(sorted(values)) or len(values) != len(set(values)):
        raise PipelineError(f"{label} must be sorted and unique")
    for item in values:
        if registered_kinds:
            if item not in EVIDENCE_KINDS:
                raise PipelineError(f"{label} contains an unknown evidence kind")
        else:
            _require_identifier(item, f"{label} item")
    return values


def _require_relative_member_path(value: object, label: str) -> str:
    value = validate_utf8_string(value, label=label)
    if (
        not value
        or "\\" in value
        or "//" in value
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative POSIX path")
    return value


def _require_path_template(value: object, label: str) -> str:
    if type(value) is not str or value.count(TEMPLATE_TOKEN) != 1:
        raise PipelineError(f"{label} must contain exactly one transition ID token")
    probe = value.replace(TEMPLATE_TOKEN, "transition-id")
    _require_relative_member_path(probe, label)
    if not probe.endswith(".json"):
        raise PipelineError(f"{label} must name a JSON document")
    return value


@dataclass(frozen=True, slots=True, kw_only=True)
class InputRoleDefinition:
    """Allowed evidence kinds and semantic binding for one named input role."""

    name: str
    allowed_kinds: tuple[str, ...]
    target_content_required: bool

    def __post_init__(self) -> None:
        _require_identifier(self.name, "transition input role name")
        _require_sorted_unique_strings(
            self.allowed_kinds,
            label=f"transition input role {self.name} allowed_kinds",
            registered_kinds=True,
        )
        if not self.allowed_kinds:
            raise PipelineError("transition input role must allow an evidence kind")
        if type(self.target_content_required) is not bool:
            raise PipelineError(
                "transition input role target_content_required must be boolean"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class TransitionDefinition:
    """One complete, immutable policy entry for a code-owned handler ID."""

    kind: str
    handler_id: str
    spec_format: str
    candidate_format: str
    spec_path_template: str
    engine_bundle_path_template: str
    required_engine_members: tuple[str, ...]
    input_roles: tuple[InputRoleDefinition, ...]
    output_kind: str
    required_checks: tuple[str, ...]
    process_tier: str
    predecessor_policy: str
    mutation_policy: str

    def __post_init__(self) -> None:
        _require_identifier(self.kind, "transition definition kind")
        _require_identifier(self.handler_id, "transition definition handler_id")
        _require_identifier(self.spec_format, "transition definition spec_format")
        _require_identifier(
            self.candidate_format,
            "transition definition candidate_format",
        )
        _require_path_template(
            self.spec_path_template,
            "transition definition spec_path_template",
        )
        _require_path_template(
            self.engine_bundle_path_template,
            "transition definition engine_bundle_path_template",
        )
        if type(self.required_engine_members) is not tuple:
            raise PipelineError("required engine members must be a tuple")
        if any(
            type(member) is not str or not member
            for member in self.required_engine_members
        ):
            raise PipelineError(
                "required engine members must contain nonempty exact strings"
            )
        if (
            not self.required_engine_members
            or self.required_engine_members
            != tuple(sorted(self.required_engine_members))
            or len(self.required_engine_members)
            != len(set(self.required_engine_members))
        ):
            raise PipelineError("required engine members must be sorted and unique")
        for path in self.required_engine_members:
            _require_relative_member_path(path, "required engine member")
            if not path.endswith(".py"):
                raise PipelineError("required engine members must be Python sources")
        if type(self.input_roles) is not tuple or any(
            type(role) is not InputRoleDefinition for role in self.input_roles
        ):
            raise PipelineError(
                "transition definition input_roles must be exact role definitions"
            )
        role_names = tuple(role.name for role in self.input_roles)
        if (
            not role_names
            or role_names != tuple(sorted(role_names))
            or len(role_names) != len(set(role_names))
        ):
            raise PipelineError(
                "transition definition input_roles must be sorted and unique"
            )
        if (
            type(self.output_kind) is not str
            or self.output_kind not in EVIDENCE_KINDS
        ):
            raise PipelineError("transition definition output_kind is unknown")
        if type(self.required_checks) is not tuple or not self.required_checks:
            raise PipelineError("transition definition required_checks must be a tuple")
        if any(
            type(check_id) is not str or not check_id
            for check_id in self.required_checks
        ):
            raise PipelineError(
                "transition definition required_checks must contain exact strings"
            )
        if len(self.required_checks) != len(set(self.required_checks)):
            raise PipelineError("transition definition required_checks must be unique")
        for check_id in self.required_checks:
            _require_identifier(check_id, "transition definition required check")
        if type(self.process_tier) is not str or self.process_tier not in PROCESS_TIERS:
            raise PipelineError("transition definition process_tier is invalid")
        _require_identifier(
            self.predecessor_policy,
            "transition definition predecessor_policy",
        )
        _require_identifier(
            self.mutation_policy,
            "transition definition mutation_policy",
        )


INPUT_ROLES = tuple(
    InputRoleDefinition(
        name=name,
        allowed_kinds=("artifact", "track-registry")
        if name == "tracks"
        else ("artifact",),
        target_content_required=True,
    )
    for name in INPUT_ROLE_NAMES
)

TRANSITION_DEFINITIONS = (
    TransitionDefinition(
        kind="phase-freeze-bootstrap-v1",
        handler_id="phase-freeze.bootstrap.v1",
        spec_format=INTENT_FORMAT,
        candidate_format=PHASE_FREEZE_FORMAT,
        spec_path_template=SPEC_PATH_TEMPLATE,
        engine_bundle_path_template=ENGINE_BUNDLE_PATH_TEMPLATE,
        required_engine_members=REQUIRED_ENGINE_MEMBERS,
        input_roles=INPUT_ROLES,
        output_kind="phase-freeze-cas",
        required_checks=BOOTSTRAP_REQUIRED_CHECKS,
        process_tier="evidence",
        predecessor_policy="opaque-legacy-phase-freeze-v2",
        mutation_policy="construct-strict-phase-freeze-v1",
    ),
    TransitionDefinition(
        kind="phase-freeze-refresh-v1",
        handler_id="phase-freeze.refresh.v1",
        spec_format=INTENT_FORMAT,
        candidate_format=PHASE_FREEZE_FORMAT,
        spec_path_template=SPEC_PATH_TEMPLATE,
        engine_bundle_path_template=ENGINE_BUNDLE_PATH_TEMPLATE,
        required_engine_members=REQUIRED_ENGINE_MEMBERS,
        input_roles=INPUT_ROLES,
        output_kind="phase-freeze-cas",
        required_checks=REFRESH_REQUIRED_CHECKS,
        process_tier="evidence",
        predecessor_policy="strict-phase-freeze-v1",
        mutation_policy="exact-authority-delta-v1",
    ),
)

TRANSITION_BY_KIND = MappingProxyType(
    {definition.kind: definition for definition in TRANSITION_DEFINITIONS}
)


def definition_for(kind: str) -> TransitionDefinition:
    """Return one exact static definition, rejecting unknown transition kinds."""

    if type(kind) is not str:
        raise PipelineError("transition kind must be an exact string")
    try:
        return TRANSITION_BY_KIND[kind]
    except KeyError as exc:
        raise PipelineError(f"unknown transition kind: {kind}") from exc


def _validate_registry() -> None:
    kinds = tuple(definition.kind for definition in TRANSITION_DEFINITIONS)
    if kinds != tuple(sorted(kinds)) or len(kinds) != len(set(kinds)):
        raise RuntimeError("transition registry kinds must be sorted and unique")
    handlers = tuple(definition.handler_id for definition in TRANSITION_DEFINITIONS)
    if len(handlers) != len(set(handlers)):
        raise RuntimeError("transition registry handler IDs must be unique")
    if tuple(TRANSITION_BY_KIND) != kinds:
        raise RuntimeError("transition registry mapping differs from definitions")


_validate_registry()


__all__ = [
    "BOOTSTRAP_REQUIRED_CHECKS",
    "ENGINE_BUNDLE_PATH_TEMPLATE",
    "INPUT_ROLES",
    "INPUT_ROLE_NAMES",
    "PHASE_FREEZE_FORMAT",
    "REFRESH_REQUIRED_CHECKS",
    "REQUIRED_ENGINE_MEMBERS",
    "SPEC_PATH_TEMPLATE",
    "TRANSITION_BY_KIND",
    "TRANSITION_DEFINITIONS",
    "InputRoleDefinition",
    "TransitionDefinition",
    "definition_for",
]
