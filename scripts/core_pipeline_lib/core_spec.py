"""Strict identity aggregation for the canonical 100-core build catalog.

The build catalog remains the full CoreSpec authority in this migration slice.
This module derives a small immutable identity set from one authenticated
catalog/schema byte pair.  It deliberately retains both the historical compact
ASCII-escaped CoreSpec digest and the new strict UTF-8 campaign digest.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import re
from types import MappingProxyType
from typing import ClassVar, Final

from .campaign.json_wire import (
    canonical_json_bytes,
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
    validate_identity_json,
    validate_utf8_string,
)
from .campaign.model import EvidenceRef
from .contracts.registry import CORE_LOG_CONTRACTS, CoreLogContract
from .errors import PipelineError
from .foundation import sha256_bytes


SCHEMA_VERSION: Final = 1
CORE_SPEC_SET_FORMAT: Final = "spruce-core-spec-set-v1"
PUBLICATION: Final = "disabled"

CATALOG_PATH: Final = "manifests/core-builds.json"
CATALOG_SCHEMA_PATH: Final = "manifests/core-builds.schema.json"
CATALOG_SCHEMA_DRAFT: Final = "https://json-schema.org/draft/2020-12/schema"
CATALOG_SCHEMA_ID: Final = "https://spruceui.local/schemas/core-builds.schema.json"
CATALOG_SCHEMA_CONTENT_SHA256: Final = (
    "4eb4f5025f64e1a847ebfb1b88f492cd111eb14d1ebe3cc042b63f85905dd88e"
)

EXPECTED_CORE_COUNT: Final = 100
EXPECTED_REGISTERED_CONTRACT_COUNT: Final = 89
EXPECTED_DRIVER_COUNTS: Final = MappingProxyType(
    {
        "direct-cargo": 1,
        "direct-cmake": 8,
        "direct-make": 4,
        "libretro-super": 85,
    }
)
LEGACY_VALIDATOR_CORE_IDS: Final = frozenset(
    {
        "ardens",
        "arduous",
        "easyrpg",
        "ffmpeg",
        "flycast",
        "km_duckswanstation_xtreme_amped",
        "squirreljme",
        "swanstation",
        "tic80",
    }
)

_CATALOG_KEYS: Final = frozenset(
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
_DRIVERS: Final = frozenset(EXPECTED_DRIVER_COUNTS)
_REGISTERED_PROOF_KINDS: Final = frozenset({"core-arch", "core-arch-source"})
_CORE_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_CONTRACT_ID_RE: Final = re.compile(r"^[a-z][a-z0-9-]*-v[1-9][0-9]*$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")


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


def _require_exact_list(value: object, *, label: str) -> list[object]:
    if type(value) is not list:
        raise PipelineError(f"{label} must be an exact array")
    return value


def _require_core_id(value: object, *, label: str = "core_id") -> str:
    value = validate_utf8_string(value, label=label)
    if _CORE_ID_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} is not a canonical core identifier")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PipelineError(f"{label} must be a lowercase SHA-256")
    return value


def _with_content_sha256(material: dict[str, object]) -> dict[str, object]:
    document = dict(material)
    document["content_sha256"] = canonical_json_sha256(material)
    return document


def _require_content_sha256(
    document: dict[str, object],
    material: dict[str, object],
    *,
    label: str,
) -> None:
    actual = _require_sha256(
        document.get("content_sha256"), label=f"{label} content_sha256"
    )
    if actual != canonical_json_sha256(material):
        raise PipelineError(f"{label} content_sha256 is invalid")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProofBinding:
    """Code-owned proof authority for one catalog core."""

    binding_kind: str
    binding_id: str
    proof_kind: str

    schema_version: ClassVar[int] = SCHEMA_VERSION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {"schema_version", "binding_kind", "binding_id", "proof_kind"}
    )

    def __post_init__(self) -> None:
        if type(self.binding_kind) is not str or self.binding_kind not in {
            "registered-log-contract",
            "legacy-validator",
        }:
            raise PipelineError("proof binding kind is invalid")
        if type(self.binding_id) is not str or type(self.proof_kind) is not str:
            raise PipelineError("proof binding values must be exact strings")
        if self.binding_kind == "registered-log-contract":
            if _CONTRACT_ID_RE.fullmatch(self.binding_id) is None:
                raise PipelineError("registered proof binding ID is invalid")
            if self.proof_kind not in _REGISTERED_PROOF_KINDS:
                raise PipelineError("registered proof kind is invalid")
        elif (
            self.binding_id not in LEGACY_VALIDATOR_CORE_IDS
            or self.proof_kind != "legacy-validator"
        ):
            raise PipelineError("legacy proof binding is not an explicit exception")

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "binding_kind": self.binding_kind,
            "binding_id": self.binding_id,
            "proof_kind": self.proof_kind,
        }

    @classmethod
    def from_document(cls, value: object) -> "ProofBinding":
        document = _require_exact_mapping(
            value, label="proof binding", keys=cls._KEYS
        )
        if type(document.get("schema_version")) is not int or document.get(
            "schema_version"
        ) != SCHEMA_VERSION:
            raise PipelineError("proof binding schema_version is invalid")
        return cls(
            binding_kind=document.get("binding_kind"),  # type: ignore[arg-type]
            binding_id=document.get("binding_id"),  # type: ignore[arg-type]
            proof_kind=document.get("proof_kind"),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CoreSpecIdentity:
    """One core's two catalog-spec identities and exact proof owner."""

    core_id: str
    driver: str
    legacy_catalog_spec_sha256: str
    strict_spec_sha256: str
    proof_binding: ProofBinding

    schema_version: ClassVar[int] = SCHEMA_VERSION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "core_id",
            "driver",
            "legacy_catalog_spec_sha256",
            "strict_spec_sha256",
            "proof_binding",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_core_id(self.core_id)
        if type(self.driver) is not str or self.driver not in _DRIVERS:
            raise PipelineError("CoreSpec driver is invalid")
        _require_sha256(
            self.legacy_catalog_spec_sha256,
            label="legacy catalog CoreSpec SHA-256",
        )
        _require_sha256(self.strict_spec_sha256, label="strict CoreSpec SHA-256")
        if type(self.proof_binding) is not ProofBinding:
            raise PipelineError("CoreSpec proof_binding must be an exact ProofBinding")
        expected_binding = _expected_proof_bindings().get(self.core_id)
        if expected_binding is None or self.proof_binding != expected_binding:
            raise PipelineError(
                f"CoreSpec proof binding differs from policy: {self.core_id}"
            )

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "core_id": self.core_id,
            "driver": self.driver,
            "legacy_catalog_spec_sha256": self.legacy_catalog_spec_sha256,
            "strict_spec_sha256": self.strict_spec_sha256,
            "proof_binding": self.proof_binding.to_document(),
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "CoreSpecIdentity":
        document = _require_exact_mapping(
            value, label="CoreSpec identity", keys=cls._KEYS
        )
        if type(document.get("schema_version")) is not int or document.get(
            "schema_version"
        ) != SCHEMA_VERSION:
            raise PipelineError("CoreSpec identity schema_version is invalid")
        result = cls(
            core_id=document.get("core_id"),  # type: ignore[arg-type]
            driver=document.get("driver"),  # type: ignore[arg-type]
            legacy_catalog_spec_sha256=document.get(  # type: ignore[arg-type]
                "legacy_catalog_spec_sha256"
            ),
            strict_spec_sha256=document.get(  # type: ignore[arg-type]
                "strict_spec_sha256"
            ),
            proof_binding=ProofBinding.from_document(document.get("proof_binding")),
        )
        _require_content_sha256(
            document, result._material(), label="CoreSpec identity"
        )
        return result


def _expected_proof_bindings() -> dict[str, ProofBinding]:
    result: dict[str, ProofBinding] = {}
    contract_ids: set[str] = set()
    for contract in CORE_LOG_CONTRACTS:
        if type(contract) is not CoreLogContract or len(contract.core_ids) != 1:
            raise PipelineError("core log contract registry shape is invalid")
        core_id = next(iter(contract.core_ids))
        _require_core_id(core_id, label="registered contract core_id")
        if core_id in result or contract.contract_id in contract_ids:
            raise PipelineError("core log contract registry is not unique")
        contract_ids.add(contract.contract_id)
        result[core_id] = ProofBinding(
            binding_kind="registered-log-contract",
            binding_id=contract.contract_id,
            proof_kind=contract.proof_kind,
        )
    if len(result) != EXPECTED_REGISTERED_CONTRACT_COUNT:
        raise PipelineError("registered core log contract count is not exactly 89")
    overlap = frozenset(result) & LEGACY_VALIDATOR_CORE_IDS
    if overlap:
        raise PipelineError(
            "legacy validator exceptions overlap registered contracts: "
            f"{sorted(overlap)}"
        )
    for core_id in sorted(LEGACY_VALIDATOR_CORE_IDS):
        result[core_id] = ProofBinding(
            binding_kind="legacy-validator",
            binding_id=core_id,
            proof_kind="legacy-validator",
        )
    if len(result) != EXPECTED_CORE_COUNT:
        raise PipelineError("CoreSpec proof binding closure is not exactly 98")
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class CoreSpecSetV1:
    """Closed identity set for every core in one authenticated catalog."""

    catalog: EvidenceRef
    catalog_schema: EvidenceRef
    cores: tuple[CoreSpecIdentity, ...]

    schema_version: ClassVar[int] = SCHEMA_VERSION
    format: ClassVar[str] = CORE_SPEC_SET_FORMAT
    local_only: ClassVar[bool] = True
    publication: ClassVar[str] = PUBLICATION
    _KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "schema_version",
            "format",
            "catalog",
            "catalog_schema",
            "core_count",
            "driver_counts",
            "cores",
            "local_only",
            "publication",
            "content_sha256",
        }
    )

    def __post_init__(self) -> None:
        _require_artifact_reference(
            self.catalog, path=CATALOG_PATH, label="CoreSpec set catalog"
        )
        _require_artifact_reference(
            self.catalog_schema,
            path=CATALOG_SCHEMA_PATH,
            label="CoreSpec set catalog schema",
        )
        if type(self.cores) is not tuple or any(
            type(item) is not CoreSpecIdentity for item in self.cores
        ):
            raise PipelineError("CoreSpec set cores must be exact CoreSpec identities")
        if len(self.cores) != EXPECTED_CORE_COUNT:
            raise PipelineError("CoreSpec set must contain exactly 98 cores")
        core_ids = tuple(item.core_id for item in self.cores)
        if core_ids != tuple(sorted(core_ids)) or len(core_ids) != len(set(core_ids)):
            raise PipelineError("CoreSpec set cores must be sorted and unique")
        expected_bindings = _expected_proof_bindings()
        if frozenset(core_ids) != frozenset(expected_bindings):
            raise PipelineError("CoreSpec set core IDs do not close proof ownership")
        for item in self.cores:
            if item.proof_binding != expected_bindings[item.core_id]:
                raise PipelineError(
                    f"CoreSpec proof binding differs from policy: {item.core_id}"
                )
        if self.driver_counts != dict(EXPECTED_DRIVER_COUNTS):
            raise PipelineError("CoreSpec set driver partition is not exact")
        legacy_digests = tuple(
            item.legacy_catalog_spec_sha256 for item in self.cores
        )
        strict_digests = tuple(item.strict_spec_sha256 for item in self.cores)
        if len(set(legacy_digests)) != EXPECTED_CORE_COUNT:
            raise PipelineError("legacy catalog CoreSpec identities are not distinct")
        if len(set(strict_digests)) != EXPECTED_CORE_COUNT:
            raise PipelineError("strict CoreSpec identities are not distinct")

    @property
    def core_count(self) -> int:
        return len(self.cores)

    @property
    def driver_counts(self) -> dict[str, int]:
        counts = Counter(item.driver for item in self.cores)
        return {driver: counts[driver] for driver in sorted(_DRIVERS)}

    def _material(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "format": CORE_SPEC_SET_FORMAT,
            "catalog": self.catalog.to_document(),
            "catalog_schema": self.catalog_schema.to_document(),
            "core_count": self.core_count,
            "driver_counts": self.driver_counts,
            "cores": [item.to_document() for item in self.cores],
            "local_only": True,
            "publication": PUBLICATION,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_json_sha256(self._material())

    def to_document(self) -> dict[str, object]:
        return _with_content_sha256(self._material())

    @classmethod
    def from_document(cls, value: object) -> "CoreSpecSetV1":
        document = _require_exact_mapping(
            value, label="CoreSpec set", keys=cls._KEYS
        )
        if type(document.get("schema_version")) is not int or document.get(
            "schema_version"
        ) != SCHEMA_VERSION:
            raise PipelineError("CoreSpec set schema_version is invalid")
        if document.get("format") != CORE_SPEC_SET_FORMAT or type(
            document.get("format")
        ) is not str:
            raise PipelineError("CoreSpec set format is invalid")
        if document.get("local_only") is not True:
            raise PipelineError("CoreSpec set must remain local-only")
        if document.get("publication") != PUBLICATION or type(
            document.get("publication")
        ) is not str:
            raise PipelineError("CoreSpec set publication must remain disabled")
        core_documents = _require_exact_list(
            document.get("cores"), label="CoreSpec set cores"
        )
        result = cls(
            catalog=EvidenceRef.from_document(document.get("catalog")),
            catalog_schema=EvidenceRef.from_document(document.get("catalog_schema")),
            cores=tuple(
                CoreSpecIdentity.from_document(item) for item in core_documents
            ),
        )
        if type(document.get("core_count")) is not int or document.get(
            "core_count"
        ) != result.core_count:
            raise PipelineError("CoreSpec set core_count is invalid")
        persisted_counts = _require_exact_mapping(
            document.get("driver_counts"),
            label="CoreSpec set driver_counts",
            keys=_DRIVERS,
        )
        if any(type(value) is not int for value in persisted_counts.values()) or (
            persisted_counts != result.driver_counts
        ):
            raise PipelineError("CoreSpec set driver_counts are invalid")
        _require_content_sha256(document, result._material(), label="CoreSpec set")
        return result


def legacy_core_spec_sha256(spec: object) -> str:
    """Return the historical compact, sorted, ASCII-escaped CoreSpec digest."""

    if type(spec) is not dict:
        raise PipelineError("legacy CoreSpec input must be an exact object")
    validate_identity_json(spec, label="legacy CoreSpec")
    try:
        raw = json.dumps(
            spec,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise PipelineError(f"legacy CoreSpec cannot be encoded: {exc}") from exc
    return sha256_bytes(raw)


def _require_artifact_reference(
    value: object,
    *,
    path: str,
    label: str,
) -> EvidenceRef:
    if type(value) is not EvidenceRef:
        raise PipelineError(f"{label} must be an exact EvidenceRef")
    if value.kind != "artifact" or value.path != path:
        raise PipelineError(f"{label} kind or path is invalid")
    if value.target_content_sha256 is None:
        raise PipelineError(f"{label} must bind a semantic identity")
    return value


def _require_reference_binding(
    reference: object,
    raw: object,
    document: dict[str, object],
    *,
    path: str,
    label: str,
) -> EvidenceRef:
    reference = _require_artifact_reference(reference, path=path, label=label)
    if type(raw) is not bytes:
        raise PipelineError(f"{label} raw input must be exact bytes")
    if reference.file_sha256 != sha256_bytes(raw):
        raise PipelineError(f"{label} raw SHA-256 is invalid")
    if reference.size != len(raw):
        raise PipelineError(f"{label} byte size is invalid")
    if reference.target_content_sha256 != canonical_json_sha256(document):
        raise PipelineError(f"{label} semantic SHA-256 is invalid")
    return reference


def _reject_remote_schema_references(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                type(item) is not str or not item.startswith("#")
            ):
                raise PipelineError("catalog schema must not use remote references")
            _reject_remote_schema_references(item)
    elif type(value) is list:
        for item in value:
            _reject_remote_schema_references(item)


def _validate_catalog_schema(schema: dict[str, object]) -> None:
    """Authenticate the schema contract without reclassifying legacy specs.

    The v2 catalog intentionally still contains entries owned by the legacy
    validators.  H5 aggregates their exact bytes and proof ownership; it does
    not claim that those historical entries have already migrated to every
    prospective constraint in the catalog schema.
    """

    if canonical_json_sha256(schema) != CATALOG_SCHEMA_CONTENT_SHA256:
        raise PipelineError("catalog schema semantic identity is not authorized")
    if schema.get("$schema") != CATALOG_SCHEMA_DRAFT:
        raise PipelineError("catalog schema must declare exact Draft 2020-12")
    if schema.get("$id") != CATALOG_SCHEMA_ID:
        raise PipelineError("catalog schema ID is not canonical")
    _reject_remote_schema_references(schema)
    try:
        from jsonschema import Draft202012Validator
        from jsonschema.exceptions import SchemaError
    except ImportError as exc:
        raise PipelineError("jsonschema is required for CoreSpec aggregation") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise PipelineError(f"catalog schema is invalid: {exc.message}") from exc
    except Exception as exc:
        raise PipelineError(f"catalog schema check failed closed: {exc}") from exc


def _validate_catalog_envelope(catalog: dict[str, object]) -> dict[str, object]:
    _require_exact_mapping(catalog, label="core catalog", keys=_CATALOG_KEYS)
    if catalog.get("$schema") != "./core-builds.schema.json":
        raise PipelineError("core catalog schema route is invalid")
    if type(catalog.get("schema_version")) is not int or catalog.get(
        "schema_version"
    ) != 2:
        raise PipelineError("core catalog schema_version is invalid")
    policy = _require_exact_mapping(catalog.get("policy"), label="core catalog policy")
    if policy.get("publication") != PUBLICATION or type(
        policy.get("publication")
    ) is not str:
        raise PipelineError("core catalog publication must remain disabled")
    cores = _require_exact_mapping(catalog.get("cores"), label="core catalog cores")
    if len(cores) != EXPECTED_CORE_COUNT:
        raise PipelineError("core catalog must contain exactly 98 cores")
    return cores


def derive_core_spec_set(
    *,
    catalog_ref: EvidenceRef,
    catalog_raw: bytes,
    catalog_schema_ref: EvidenceRef,
    catalog_schema_raw: bytes,
) -> CoreSpecSetV1:
    """Derive the exact 98-core identity set from authenticated input bytes."""

    if type(catalog_raw) is not bytes or type(catalog_schema_raw) is not bytes:
        raise PipelineError("catalog and schema inputs must be exact bytes")
    catalog = decode_identity_object(catalog_raw, label="core catalog")
    schema = decode_identity_object(catalog_schema_raw, label="core catalog schema")
    catalog_ref = _require_reference_binding(
        catalog_ref,
        catalog_raw,
        catalog,
        path=CATALOG_PATH,
        label="core catalog reference",
    )
    catalog_schema_ref = _require_reference_binding(
        catalog_schema_ref,
        catalog_schema_raw,
        schema,
        path=CATALOG_SCHEMA_PATH,
        label="core catalog schema reference",
    )
    _validate_catalog_schema(schema)
    cores = _validate_catalog_envelope(catalog)
    expected_bindings = _expected_proof_bindings()
    if frozenset(cores) != frozenset(expected_bindings):
        missing = sorted(frozenset(expected_bindings) - frozenset(cores))
        extra = sorted(frozenset(cores) - frozenset(expected_bindings))
        raise PipelineError(
            "core catalog differs from proof ownership: "
            f"missing={missing}; extra={extra}"
        )

    identities: list[CoreSpecIdentity] = []
    for core_id in sorted(cores):
        _require_core_id(core_id)
        spec = _require_exact_mapping(
            cores[core_id], label=f"CoreSpec {core_id}"
        )
        build = _require_exact_mapping(
            spec.get("build"), label=f"CoreSpec {core_id} build"
        )
        driver = build.get("driver")
        if type(driver) is not str or driver not in _DRIVERS:
            raise PipelineError(f"CoreSpec {core_id} driver is invalid")
        identities.append(
            CoreSpecIdentity(
                core_id=core_id,
                driver=driver,
                legacy_catalog_spec_sha256=legacy_core_spec_sha256(spec),
                strict_spec_sha256=canonical_json_sha256(spec),
                proof_binding=expected_bindings[core_id],
            )
        )
    return CoreSpecSetV1(
        catalog=catalog_ref,
        catalog_schema=catalog_schema_ref,
        cores=tuple(identities),
    )


def validate_core_spec_set(
    value: CoreSpecSetV1,
    *,
    catalog_ref: EvidenceRef,
    catalog_raw: bytes,
    catalog_schema_ref: EvidenceRef,
    catalog_schema_raw: bytes,
) -> None:
    """Independently reconstruct and compare one CoreSpecSetV1."""

    if type(value) is not CoreSpecSetV1:
        raise PipelineError("CoreSpec set must be an exact CoreSpecSetV1")
    expected = derive_core_spec_set(
        catalog_ref=catalog_ref,
        catalog_raw=catalog_raw,
        catalog_schema_ref=catalog_schema_ref,
        catalog_schema_raw=catalog_schema_raw,
    )
    if canonical_json_bytes(value.to_document()) != canonical_json_bytes(
        expected.to_document()
    ):
        raise PipelineError("CoreSpec set does not match authenticated inputs")


def decode_core_spec_set(raw: bytes) -> CoreSpecSetV1:
    """Strictly decode one self-authenticating CoreSpecSetV1 document."""

    return CoreSpecSetV1.from_document(
        decode_identity_object(raw, label="CoreSpec set")
    )


def render_core_spec_set(value: CoreSpecSetV1) -> bytes:
    """Render one CoreSpecSetV1 using the strict human-readable wire format."""

    if type(value) is not CoreSpecSetV1:
        raise PipelineError("CoreSpec set must be an exact CoreSpecSetV1")
    return rendered_json_bytes(value.to_document())


__all__ = [
    "CATALOG_PATH",
    "CATALOG_SCHEMA_CONTENT_SHA256",
    "CATALOG_SCHEMA_DRAFT",
    "CATALOG_SCHEMA_ID",
    "CATALOG_SCHEMA_PATH",
    "CORE_SPEC_SET_FORMAT",
    "EXPECTED_CORE_COUNT",
    "EXPECTED_DRIVER_COUNTS",
    "EXPECTED_REGISTERED_CONTRACT_COUNT",
    "LEGACY_VALIDATOR_CORE_IDS",
    "CoreSpecIdentity",
    "CoreSpecSetV1",
    "ProofBinding",
    "decode_core_spec_set",
    "derive_core_spec_set",
    "legacy_core_spec_sha256",
    "render_core_spec_set",
    "validate_core_spec_set",
]
