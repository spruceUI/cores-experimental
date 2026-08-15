"""Pure planning for strict, immutable campaign phase-freeze authorities.

The bootstrap handler authenticates an opaque legacy predecessor without
decoding it.  The refresh handler accepts only the exact v1 rendering and
derives its complete RFC 6901 delta.  Both handlers consume already-hydrated
bytes and perform no filesystem, process, clock, transaction, or publication
work.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import re
from typing import ClassVar, Final

from ..core_spec import (
    CATALOG_SCHEMA_CONTENT_SHA256,
    CATALOG_SCHEMA_PATH,
    EXPECTED_CORE_COUNT,
    CoreSpecSetV1,
    decode_core_spec_set,
    legacy_core_spec_sha256,
    render_core_spec_set,
)
from ..errors import PipelineError
from ..foundation import sha256_bytes
from ..source_bundle import pipeline_source_bundle_is_well_formed
from .json_wire import (
    canonical_json_bytes,
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
)
from .model import EvidenceRef
from .projection import (
    encode_json_pointer,
    projection_sha256,
    require_exact_pointer_delta,
)
from .store import canonical_object_reference
from .transition_model import (
    AuthenticatedInput,
    NamedEvidenceRef,
    PlannedTransition,
    ResolvedTransitionPlanV1,
    TransitionDeltaV1,
    TransitionIntentV1,
    TransitionRequest,
)
from .transition_registry import (
    INPUT_ROLE_NAMES,
    PHASE_FREEZE_FORMAT,
    TransitionDefinition,
    definition_for,
)


SCHEMA_VERSION: Final = 1
PUBLICATION: Final = "disabled"
BOOTSTRAP_KIND: Final = "phase-freeze-bootstrap-v1"
REFRESH_KIND: Final = "phase-freeze-refresh-v1"
PHASE_FREEZE_SCHEMA_PATH: Final = (
    "manifests/campaign-phase-freeze-v1.schema.json"
)
PHASE_FREEZE_SCHEMA_DRAFT: Final = (
    "https://json-schema.org/draft/2020-12/schema"
)
PHASE_FREEZE_SCHEMA_ID: Final = (
    "https://spruceui.local/schemas/campaign-phase-freeze-v1.schema.json"
)
PHASE_FREEZE_SCHEMA_CONTENT_SHA256: Final = (
    "5cbe07dc185bfc9f49c5b4676a2aa1442b06dfd90c5a75bc7cc0e13bfe316a45"
)
PHASE_FREEZE_SCHEMA_FILE_SHA256: Final = (
    "1f1224115df7ee2948bb80adff532739def347800fd28bb95b9f204abc5fbd27"
)
PHASE_FREEZE_SCHEMA_SIZE: Final = 4_837
CATALOG_SCHEMA_FILE_SHA256: Final = (
    "4289b6f3a443907a766ce419515a33f34fd86074f9659cc1724ca978f8d04343"
)
CATALOG_SCHEMA_SIZE: Final = 28_681
CAMPAIGN_STATE_RELATIVE: Final = ".local-e2e/campaign-state"

_IDENTIFIER_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECONDS_RE: Final = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)
_REFRESH_METADATA_POINTERS: Final = (
    "/captured_at",
    "/content_sha256",
    "/predecessor",
    "/transition_id",
)
_BOOTSTRAP_PROJECTION_SHA256: Final = canonical_json_sha256({})
_CORE_CATALOG_KEYS: Final = frozenset(
    {
        "$schema",
        "schema_version",
        "policy",
        "commit_blacklist",
        "toolchain_lock",
        "toolchain_lock_validator",
        "toolchains",
        "resolver",
        "cores",
    }
)


def _require_identifier(value: object, *, label: str) -> str:
    if type(value) is not str or _IDENTIFIER_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a stable lowercase identifier")
    return value


def _require_timestamp(value: object, *, label: str) -> str:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be an exact UTC-second timestamp")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise PipelineError(f"{label} must be a real UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise PipelineError(f"{label} is not canonical")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _require_exact_mapping(
    value: object,
    *,
    label: str,
    keys: frozenset[str] | None = None,
) -> dict[str, object]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise PipelineError(f"{label} must be an exact object with string keys")
    if keys is not None and frozenset(value) != keys:
        missing = sorted(keys - frozenset(value))
        extra = sorted(frozenset(value) - keys)
        raise PipelineError(
            f"{label} fields are not exact: missing={missing}; extra={extra}"
        )
    return value


def _require_semantic_reference(
    value: object,
    *,
    label: str,
    allowed_kinds: tuple[str, ...],
) -> EvidenceRef:
    if type(value) is not EvidenceRef or value.kind not in allowed_kinds:
        raise PipelineError(f"{label} kind is invalid")
    if value.target_content_sha256 is None:
        raise PipelineError(f"{label} must bind a semantic identity")
    return value


def _require_authorities(
    values: object,
) -> tuple[NamedEvidenceRef, ...]:
    if type(values) is not tuple or any(
        type(item) is not NamedEvidenceRef for item in values
    ):
        raise PipelineError(
            "phase-freeze authorities must be exact NamedEvidenceRef values"
        )
    names = tuple(item.name for item in values)
    if names != INPUT_ROLE_NAMES:
        raise PipelineError("phase-freeze authorities differ from the exact roles")
    definition = definition_for(BOOTSTRAP_KIND)
    role_by_name = {role.name: role for role in definition.input_roles}
    for item in values:
        role = role_by_name[item.name]
        reference = item.reference
        if reference.kind not in role.allowed_kinds:
            raise PipelineError(
                f"phase-freeze authority {item.name} kind is invalid"
            )
        if role.target_content_required and (
            reference.target_content_sha256 is None
        ):
            raise PipelineError(
                f"phase-freeze authority {item.name} lacks semantic identity"
            )
    return values


def _with_content_sha256(material: dict[str, object]) -> dict[str, object]:
    document = dict(material)
    document["content_sha256"] = canonical_json_sha256(material)
    return document


@dataclass(frozen=True, slots=True, kw_only=True)
class PhaseFreezeV1:
    """One closed snapshot of all registered campaign authorities."""

    campaign_id: str
    transition_id: str
    captured_at: str
    predecessor: EvidenceRef
    authorities: tuple[NamedEvidenceRef, ...]

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = PHASE_FREEZE_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "campaign_id",
            "transition_id",
            "captured_at",
            "predecessor",
            "authorities",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_identifier(self.campaign_id, label="phase-freeze campaign_id")
        _require_identifier(
            self.transition_id,
            label="phase-freeze transition_id",
        )
        _require_timestamp(self.captured_at, label="phase-freeze captured_at")
        _require_semantic_reference(
            self.predecessor,
            label="phase-freeze predecessor",
            allowed_kinds=("phase-freeze", "phase-freeze-cas"),
        )
        _require_authorities(self.authorities)

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": PHASE_FREEZE_FORMAT,
            "campaign_id": self.campaign_id,
            "transition_id": self.transition_id,
            "captured_at": self.captured_at,
            "predecessor": self.predecessor.to_document(),
            "authorities": {
                item.name: item.reference.to_document()
                for item in self.authorities
            },
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "PhaseFreezeV1":
        document = decode_identity_object(value, label="phase freeze")
        _require_exact_mapping(
            document,
            label="phase freeze",
            keys=cls._KEYS,
        )
        if type(document.get("schema_version")) is not int or document.get(
            "schema_version"
        ) != SCHEMA_VERSION:
            raise PipelineError("phase-freeze schema_version is invalid")
        if type(document.get("format")) is not str or document.get(
            "format"
        ) != PHASE_FREEZE_FORMAT:
            raise PipelineError("phase-freeze format is invalid")
        if document.get("local_only") is not True:
            raise PipelineError("phase freeze must remain local-only")
        if type(document.get("publication")) is not str or document.get(
            "publication"
        ) != PUBLICATION:
            raise PipelineError("phase-freeze publication must remain disabled")
        authority_documents = _require_exact_mapping(
            document.get("authorities"),
            label="phase-freeze authorities",
            keys=frozenset(INPUT_ROLE_NAMES),
        )
        result = cls(
            campaign_id=document.get("campaign_id"),  # type: ignore[arg-type]
            transition_id=document.get("transition_id"),  # type: ignore[arg-type]
            captured_at=document.get("captured_at"),  # type: ignore[arg-type]
            predecessor=EvidenceRef.from_document(document.get("predecessor")),
            authorities=tuple(
                NamedEvidenceRef(
                    name=name,
                    reference=EvidenceRef.from_document(
                        authority_documents[name]
                    ),
                )
                for name in INPUT_ROLE_NAMES
            ),
        )
        persisted_content = _require_sha256(
            document.get("content_sha256"),
            label="phase-freeze content_sha256",
        )
        if persisted_content != result.content_sha256:
            raise PipelineError("phase-freeze content_sha256 is invalid")
        return result


def render_phase_freeze(value: PhaseFreezeV1) -> bytes:
    """Render one phase freeze in its sole accepted persisted encoding."""

    if type(value) is not PhaseFreezeV1:
        raise PipelineError("phase freeze must be an exact PhaseFreezeV1")
    return rendered_json_bytes(value.to_document())


def decode_phase_freeze(raw: bytes) -> PhaseFreezeV1:
    """Decode strict phase-freeze bytes without accepting legacy shapes."""

    if type(raw) is not bytes:
        raise PipelineError("phase-freeze raw input must be exact bytes")
    return PhaseFreezeV1.from_document(raw)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlannedPhaseFreeze:
    """One resolved transition and its exact parsed and rendered successor."""

    plan: ResolvedTransitionPlanV1
    phase_freeze: PhaseFreezeV1
    candidate_raw: bytes

    def __post_init__(self) -> None:
        if type(self.plan) is not ResolvedTransitionPlanV1:
            raise PipelineError("planned phase-freeze plan is invalid")
        if type(self.phase_freeze) is not PhaseFreezeV1:
            raise PipelineError("planned phase-freeze candidate is invalid")
        if type(self.candidate_raw) is not bytes:
            raise PipelineError("planned phase-freeze bytes are invalid")
        if render_phase_freeze(self.phase_freeze) != self.candidate_raw:
            raise PipelineError(
                "planned phase-freeze bytes differ from the parsed candidate"
            )
        if (
            self.plan.campaign_id != self.phase_freeze.campaign_id
            or self.plan.transition_id != self.phase_freeze.transition_id
            or self.plan.captured_at != self.phase_freeze.captured_at
            or self.plan.predecessor != self.phase_freeze.predecessor
            or self.plan.inputs != self.phase_freeze.authorities
            or self.plan.successor.target_content_sha256
            != self.phase_freeze.content_sha256
        ):
            raise PipelineError(
                "planned phase-freeze plan differs from the candidate"
            )
        PlannedTransition(plan=self.plan, candidate_raw=self.candidate_raw)


def _load_intent(request: TransitionRequest) -> TransitionIntentV1:
    intent = TransitionIntentV1.from_document(request.spec_raw)
    expected_raw = rendered_json_bytes(intent.to_document())
    if request.spec_raw != expected_raw:
        raise PipelineError("transition intent bytes are not the exact rendering")
    return intent


def _require_definition_and_spec(
    request: TransitionRequest,
    intent: TransitionIntentV1,
) -> TransitionDefinition:
    definition = definition_for(intent.kind)
    if definition.kind not in {BOOTSTRAP_KIND, REFRESH_KIND}:
        raise PipelineError("phase-freeze transition kind is unsupported")
    if definition.candidate_format != PHASE_FREEZE_FORMAT:
        raise PipelineError("phase-freeze registry candidate format is invalid")
    if tuple(role.name for role in definition.input_roles) != INPUT_ROLE_NAMES:
        raise PipelineError("phase-freeze registry input roles are invalid")
    expected_path = definition.spec_path_template.format(
        transition_id=intent.transition_id
    )
    if request.spec_ref.path != expected_path:
        raise PipelineError("transition intent reference path is invalid")
    if request.spec_ref.target_content_sha256 != intent.content_sha256:
        raise PipelineError("transition intent semantic reference is invalid")
    return definition


def _require_authority_inputs(
    request: TransitionRequest,
    definition: TransitionDefinition,
) -> dict[str, AuthenticatedInput]:
    if type(request.inputs) is not tuple or any(
        type(item) is not AuthenticatedInput for item in request.inputs
    ):
        raise PipelineError("phase-freeze inputs are invalid")
    if tuple(item.name for item in request.inputs) != INPUT_ROLE_NAMES:
        raise PipelineError("phase-freeze inputs differ from the exact roles")
    role_by_name = {role.name: role for role in definition.input_roles}
    result = {item.name: item for item in request.inputs}
    for name in INPUT_ROLE_NAMES:
        role = role_by_name[name]
        reference = result[name].reference
        if reference.kind not in role.allowed_kinds:
            raise PipelineError(f"phase-freeze input {name} kind is invalid")
        if role.target_content_required and (
            reference.target_content_sha256 is None
        ):
            raise PipelineError(
                f"phase-freeze input {name} lacks semantic identity"
            )
    return result


def _validate_engine_bundle(
    request: TransitionRequest,
    definition: TransitionDefinition,
    intent: TransitionIntentV1,
) -> None:
    expected_path = definition.engine_bundle_path_template.format(
        transition_id=intent.transition_id
    )
    if request.engine_bundle_ref.path != expected_path:
        raise PipelineError("engine bundle reference path is invalid")
    document = decode_identity_object(
        request.engine_bundle_raw,
        label="phase-freeze engine bundle",
    )
    if rendered_json_bytes(document) != request.engine_bundle_raw:
        raise PipelineError("engine bundle bytes are not the exact rendering")
    if not pipeline_source_bundle_is_well_formed(document):
        raise PipelineError("engine bundle is not a well-formed source bundle")
    if request.engine_bundle_ref.target_content_sha256 != document.get(
        "content_sha256"
    ):
        raise PipelineError("engine bundle semantic reference is invalid")
    files = _require_exact_mapping(
        document.get("files"),
        label="engine bundle files",
    )
    missing = tuple(
        member
        for member in definition.required_engine_members
        if member not in files
    )
    if missing:
        raise PipelineError(
            f"engine bundle lacks required phase-freeze sources: {missing}"
        )


def _reject_remote_schema_references(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                type(item) is not str or not item.startswith("#")
            ):
                raise PipelineError(
                    "phase-freeze schema must not use remote references"
                )
            _reject_remote_schema_references(item)
    elif type(value) is list:
        for item in value:
            _reject_remote_schema_references(item)


def _load_phase_freeze_schema(
    schema_input: AuthenticatedInput,
) -> dict[str, object]:
    reference = schema_input.reference
    if reference.kind != "artifact" or reference.path != PHASE_FREEZE_SCHEMA_PATH:
        raise PipelineError("phase-freeze schema reference kind or path is invalid")
    if (
        reference.file_sha256 != PHASE_FREEZE_SCHEMA_FILE_SHA256
        or reference.size != PHASE_FREEZE_SCHEMA_SIZE
    ):
        raise PipelineError("phase-freeze schema raw identity is not authorized")
    schema = decode_identity_object(
        schema_input.raw,
        label="phase-freeze schema",
    )
    content_sha256 = canonical_json_sha256(schema)
    if reference.target_content_sha256 != content_sha256:
        raise PipelineError("phase-freeze schema semantic reference is invalid")
    if content_sha256 != PHASE_FREEZE_SCHEMA_CONTENT_SHA256:
        raise PipelineError("phase-freeze schema content is not authorized")
    if schema.get("$schema") != PHASE_FREEZE_SCHEMA_DRAFT or type(
        schema.get("$schema")
    ) is not str:
        raise PipelineError("phase-freeze schema must declare exact Draft 2020-12")
    if schema.get("$id") != PHASE_FREEZE_SCHEMA_ID or type(
        schema.get("$id")
    ) is not str:
        raise PipelineError("phase-freeze schema ID is not canonical")
    _reject_remote_schema_references(schema)
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        raise PipelineError(
            "jsonschema is required for phase-freeze planning"
        ) from exc
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise PipelineError(
            f"phase-freeze schema is invalid: {exc.message}"
        ) from exc
    except Exception as exc:
        raise PipelineError(
            f"phase-freeze schema check failed closed: {exc}"
        ) from exc
    return schema


def _validate_candidate_schema(
    schema: dict[str, object],
    candidate: PhaseFreezeV1,
) -> None:
    try:
        from jsonschema import Draft202012Validator

        first_error = next(
            iter(Draft202012Validator(schema).iter_errors(candidate.to_document())),
            None,
        )
    except Exception as exc:
        raise PipelineError(
            f"phase-freeze schema validation failed closed: {exc}"
        ) from exc
    if first_error is not None:
        path = "/".join(str(part) for part in first_error.absolute_path)
        raise PipelineError(
            f"phase freeze fails schema at /{path}: {first_error.message}"
        )


def _validate_core_spec_authority(
    *,
    catalog_input: AuthenticatedInput,
    core_spec_input: AuthenticatedInput,
) -> CoreSpecSetV1:
    catalog = decode_identity_object(
        catalog_input.raw,
        label="phase-freeze core catalog",
    )
    if catalog_input.reference.target_content_sha256 != canonical_json_sha256(
        catalog
    ):
        raise PipelineError("core catalog semantic reference is invalid")
    _require_exact_mapping(
        catalog,
        label="phase-freeze core catalog",
        keys=_CORE_CATALOG_KEYS,
    )
    if type(catalog.get("$schema")) is not str or catalog.get(
        "$schema"
    ) != "./core-builds.schema.json":
        raise PipelineError("core catalog schema route is invalid")
    if type(catalog.get("schema_version")) is not int or catalog.get(
        "schema_version"
    ) != 2:
        raise PipelineError("core catalog schema_version is invalid")
    policy = _require_exact_mapping(
        catalog.get("policy"),
        label="phase-freeze core catalog policy",
    )
    if type(policy.get("publication")) is not str or policy.get(
        "publication"
    ) != PUBLICATION:
        raise PipelineError("core catalog publication must remain disabled")
    cores = _require_exact_mapping(
        catalog.get("cores"),
        label="phase-freeze core catalog cores",
    )
    if len(cores) != EXPECTED_CORE_COUNT:
        raise PipelineError("core catalog must contain exactly 98 cores")
    core_spec_set = decode_core_spec_set(core_spec_input.raw)
    if render_core_spec_set(core_spec_set) != core_spec_input.raw:
        raise PipelineError("CoreSpec set bytes are not the exact rendering")
    if (
        core_spec_input.reference.target_content_sha256
        != core_spec_set.content_sha256
    ):
        raise PipelineError("CoreSpec set semantic reference is invalid")
    if core_spec_set.catalog != catalog_input.reference:
        raise PipelineError("CoreSpec set does not bind the catalog authority")
    # The catalog schema is validator provenance established by the upstream
    # CoreSpec derivation, not a live validation dependency of this planner.
    # Pin its complete immutable reference; a future validator may hydrate the
    # raw bytes without adding it to the persisted 14-role authority set.
    catalog_schema = core_spec_set.catalog_schema
    if (
        catalog_schema.path != CATALOG_SCHEMA_PATH
        or catalog_schema.file_sha256 != CATALOG_SCHEMA_FILE_SHA256
        or catalog_schema.size != CATALOG_SCHEMA_SIZE
        or catalog_schema.target_content_sha256
        != CATALOG_SCHEMA_CONTENT_SHA256
    ):
        raise PipelineError("CoreSpec set catalog schema provenance is not authorized")

    identities = {item.core_id: item for item in core_spec_set.cores}
    if frozenset(cores) != frozenset(identities):
        raise PipelineError("CoreSpec set core IDs differ from the catalog")
    for core_id in sorted(cores):
        spec = _require_exact_mapping(
            cores[core_id],
            label=f"phase-freeze CoreSpec {core_id}",
        )
        build = _require_exact_mapping(
            spec.get("build"),
            label=f"phase-freeze CoreSpec {core_id} build",
        )
        identity = identities[core_id]
        if (
            identity.driver != build.get("driver")
            or identity.legacy_catalog_spec_sha256
            != legacy_core_spec_sha256(spec)
            or identity.strict_spec_sha256 != canonical_json_sha256(spec)
        ):
            raise PipelineError(
                f"CoreSpec identity differs from the catalog: {core_id}"
            )
    return core_spec_set


def _bootstrap_candidate(
    intent: TransitionIntentV1,
) -> tuple[PhaseFreezeV1, TransitionDeltaV1]:
    if intent.predecessor.kind != "phase-freeze":
        raise PipelineError(
            "bootstrap predecessor must be opaque phase-freeze evidence"
        )
    if intent.changed_authorities != INPUT_ROLE_NAMES:
        raise PipelineError(
            "bootstrap must declare every authority as newly constructed"
        )
    candidate = PhaseFreezeV1(
        campaign_id=intent.campaign_id,
        transition_id=intent.transition_id,
        captured_at=intent.captured_at,
        predecessor=intent.predecessor,
        authorities=intent.inputs,
    )
    return candidate, TransitionDeltaV1(
        allowed_changes=(),
        required_changes=(),
        changed_pointers=(),
        preserved_projection_sha256=_BOOTSTRAP_PROJECTION_SHA256,
    )


def _refresh_candidate(
    request: TransitionRequest,
    intent: TransitionIntentV1,
) -> tuple[PhaseFreezeV1, TransitionDeltaV1]:
    if intent.predecessor.kind != "phase-freeze-cas":
        raise PipelineError("refresh predecessor must be strict phase-freeze CAS")
    predecessor = decode_phase_freeze(request.predecessor_raw)
    if render_phase_freeze(predecessor) != request.predecessor_raw:
        raise PipelineError("refresh predecessor bytes are not the exact rendering")
    canonical_predecessor = canonical_object_reference(
        state_relative=CAMPAIGN_STATE_RELATIVE,
        kind="phase-freeze-cas",
        raw=request.predecessor_raw,
        target_content_sha256=predecessor.content_sha256,
    )
    if intent.predecessor != canonical_predecessor:
        raise PipelineError("refresh predecessor reference is not canonical CAS")
    if intent.campaign_id != predecessor.campaign_id:
        raise PipelineError("refresh campaign differs from its predecessor")
    if intent.transition_id == predecessor.transition_id:
        raise PipelineError("refresh transition_id must advance")
    if intent.captured_at <= predecessor.captured_at:
        raise PipelineError("refresh captured_at must strictly advance")

    previous_by_name = {
        item.name: item.reference for item in predecessor.authorities
    }
    next_by_name = {item.name: item.reference for item in intent.inputs}
    changed_authorities = tuple(
        name
        for name in INPUT_ROLE_NAMES
        if previous_by_name[name] != next_by_name[name]
    )
    if not changed_authorities:
        raise PipelineError("refresh must change at least one authority")
    if intent.changed_authorities != changed_authorities:
        raise PipelineError(
            "refresh changed_authorities differ from the exact reference delta"
        )

    candidate = PhaseFreezeV1(
        campaign_id=intent.campaign_id,
        transition_id=intent.transition_id,
        captured_at=intent.captured_at,
        predecessor=intent.predecessor,
        authorities=intent.inputs,
    )
    authority_pointers = tuple(
        encode_json_pointer(("authorities", name))
        for name in changed_authorities
    )
    allowed = tuple(sorted((*_REFRESH_METADATA_POINTERS, *authority_pointers)))
    predecessor_document = predecessor.to_document()
    candidate_document = candidate.to_document()
    preserved = projection_sha256(
        predecessor_document,
        allowed,
        canonical_bytes=canonical_json_bytes,
    )
    changed_pointers = require_exact_pointer_delta(
        predecessor_document,
        candidate_document,
        allowed_pointers=allowed,
        required_pointers=allowed,
        canonical_bytes=canonical_json_bytes,
        expected_projection_sha256=preserved,
    )
    if changed_pointers != allowed:
        raise PipelineError("refresh changed pointers differ from exact policy")
    return candidate, TransitionDeltaV1(
        allowed_changes=allowed,
        required_changes=allowed,
        changed_pointers=changed_pointers,
        preserved_projection_sha256=preserved,
    )


def plan_phase_freeze(request: TransitionRequest) -> PlannedPhaseFreeze:
    """Resolve one registered phase-freeze transition using hydrated bytes."""

    if type(request) is not TransitionRequest:
        raise PipelineError("phase-freeze request must be an exact TransitionRequest")
    intent = _load_intent(request)
    definition = _require_definition_and_spec(request, intent)
    inputs = _require_authority_inputs(request, definition)
    _validate_engine_bundle(request, definition, intent)
    schema = _load_phase_freeze_schema(inputs["schemas"])
    _validate_core_spec_authority(
        catalog_input=inputs["catalog"],
        core_spec_input=inputs["core-spec-set"],
    )

    if intent.kind == BOOTSTRAP_KIND:
        candidate, delta = _bootstrap_candidate(intent)
    elif intent.kind == REFRESH_KIND:
        candidate, delta = _refresh_candidate(request, intent)
    else:  # The registry lookup above is fail closed; retain local exhaustiveness.
        raise PipelineError("phase-freeze transition kind is unsupported")

    first_raw = render_phase_freeze(candidate)
    second_raw = render_phase_freeze(candidate)
    if first_raw != second_raw:
        raise PipelineError("phase-freeze double render is not deterministic")
    round_trip = decode_phase_freeze(first_raw)
    if render_phase_freeze(round_trip) != first_raw or round_trip != candidate:
        raise PipelineError("phase-freeze render round trip is not exact")
    _validate_candidate_schema(schema, candidate)
    successor = canonical_object_reference(
        state_relative=CAMPAIGN_STATE_RELATIVE,
        kind=definition.output_kind,
        raw=first_raw,
        target_content_sha256=candidate.content_sha256,
    )
    plan = ResolvedTransitionPlanV1(
        transition_id=intent.transition_id,
        campaign_id=intent.campaign_id,
        kind=intent.kind,
        handler_id=definition.handler_id,
        captured_at=intent.captured_at,
        reason=intent.reason,
        intent=request.spec_ref,
        engine_bundle=request.engine_bundle_ref,
        predecessor=intent.predecessor,
        inputs=intent.inputs,
        successor=successor,
        delta=delta,
        required_checks=definition.required_checks,
        process_tier=definition.process_tier,
    )
    plan_raw = rendered_json_bytes(plan.to_document())
    if rendered_json_bytes(plan.to_document()) != plan_raw or (
        ResolvedTransitionPlanV1.from_document(plan_raw) != plan
    ):
        raise PipelineError("resolved phase-freeze plan round trip is not exact")
    return PlannedPhaseFreeze(
        plan=plan,
        phase_freeze=candidate,
        candidate_raw=first_raw,
    )


def validate_phase_freeze(
    value: PlannedPhaseFreeze,
    *,
    request: TransitionRequest,
) -> None:
    """Independently reconstruct and compare one planned phase freeze."""

    if type(value) is not PlannedPhaseFreeze:
        raise PipelineError("phase-freeze result must be an exact PlannedPhaseFreeze")
    expected = plan_phase_freeze(request)
    if canonical_json_bytes(value.plan.to_document()) != canonical_json_bytes(
        expected.plan.to_document()
    ):
        raise PipelineError("phase-freeze plan differs from reconstruction")
    if value.candidate_raw != expected.candidate_raw:
        raise PipelineError("phase-freeze bytes differ from reconstruction")
    if canonical_json_bytes(value.phase_freeze.to_document()) != canonical_json_bytes(
        expected.phase_freeze.to_document()
    ):
        raise PipelineError("phase-freeze candidate differs from reconstruction")


__all__ = [
    "BOOTSTRAP_KIND",
    "CAMPAIGN_STATE_RELATIVE",
    "CATALOG_SCHEMA_FILE_SHA256",
    "CATALOG_SCHEMA_SIZE",
    "PHASE_FREEZE_SCHEMA_CONTENT_SHA256",
    "PHASE_FREEZE_SCHEMA_DRAFT",
    "PHASE_FREEZE_SCHEMA_FILE_SHA256",
    "PHASE_FREEZE_SCHEMA_ID",
    "PHASE_FREEZE_SCHEMA_PATH",
    "PHASE_FREEZE_SCHEMA_SIZE",
    "PUBLICATION",
    "REFRESH_KIND",
    "SCHEMA_VERSION",
    "PhaseFreezeV1",
    "PlannedPhaseFreeze",
    "decode_phase_freeze",
    "plan_phase_freeze",
    "render_phase_freeze",
    "validate_phase_freeze",
]
