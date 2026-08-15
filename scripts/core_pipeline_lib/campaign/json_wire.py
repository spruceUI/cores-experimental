"""Strict canonical JSON for new campaign identity documents.

Historical pipeline records intentionally retain their existing codecs.  This
module defines the wire format for new campaign records only: closed JSON
types, duplicate-key rejection, no floats, sorted compact UTF-8 semantic
bytes, and exact type-preserving comparisons.
"""

from __future__ import annotations

from collections.abc import Iterable
import json
import re
from typing import TypeAlias

from ..errors import PipelineError
from ..foundation import sha256_bytes


JsonScalar: TypeAlias = None | bool | int | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_BAD_POINTER_ESCAPE_RE = re.compile(r"~(?![01])")


def _identity_error(label: str, detail: str) -> PipelineError:
    return PipelineError(f"{label} is not strict identity JSON: {detail}")


def validate_utf8_string(value: object, *, label: str = "string") -> str:
    """Require one exact string that has a lossless UTF-8 representation."""

    if type(value) is not str:
        raise PipelineError(f"{label} must be an exact string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PipelineError(f"{label} must not contain a lone surrogate") from exc
    return value


def _validate_identity_json(
    value: object,
    *,
    label: str,
    path: str,
    active_containers: set[int],
) -> None:
    value_type = type(value)
    if value is None or value_type in {bool, int}:
        return
    if value_type is str:
        validate_utf8_string(value, label=f"{label} {path}")
        return
    if value_type is float:
        raise _identity_error(label, f"{path} contains a float")
    if value_type is list:
        identity = id(value)
        if identity in active_containers:
            raise _identity_error(label, f"{path} contains a container cycle")
        active_containers.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_identity_json(
                    item,
                    label=label,
                    path=f"{path}[{index}]",
                    active_containers=active_containers,
                )
        finally:
            active_containers.remove(identity)
        return
    if value_type is dict:
        identity = id(value)
        if identity in active_containers:
            raise _identity_error(label, f"{path} contains a container cycle")
        active_containers.add(identity)
        try:
            for key, item in value.items():
                validate_utf8_string(key, label=f"{label} {path} key")
                _validate_identity_json(
                    item,
                    label=label,
                    path=f"{path}.{key}",
                    active_containers=active_containers,
                )
        finally:
            active_containers.remove(identity)
        return
    raise _identity_error(
        label,
        f"{path} contains unsupported type {value_type.__name__}",
    )


def validate_identity_json(value: object, *, label: str = "JSON value") -> JsonValue:
    """Validate and return one value in the campaign identity JSON domain."""

    try:
        _validate_identity_json(
            value,
            label=label,
            path="$",
            active_containers=set(),
        )
    except RecursionError as exc:
        raise _identity_error(label, "nesting exceeds the supported depth") from exc
    return value  # type: ignore[return-value]


def _reject_float(token: str) -> None:
    raise _identity_error("JSON input", f"float literal {token!r} is forbidden")


def _reject_constant(token: str) -> None:
    raise _identity_error("JSON input", f"constant {token!r} is forbidden")


def _closed_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise _identity_error("JSON input", f"duplicate object key {key!r}")
        result[key] = value
    return result


def decode_identity_json(raw: bytes, *, label: str = "JSON input") -> JsonValue:
    """Decode one strict UTF-8 identity JSON value from a single byte snapshot."""

    if type(raw) is not bytes:
        raise PipelineError(f"{label} must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _identity_error(label, f"invalid UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise _identity_error(label, f"invalid JSON: {exc}") from exc
    validate_identity_json(value, label=label)
    return value


def decode_identity_object(
    value: object,
    *,
    label: str = "JSON input",
) -> dict[str, JsonValue]:
    """Decode one strict top-level object and return independent mutable data."""

    if type(value) is bytes:
        decoded = decode_identity_json(value, label=label)
    else:
        validate_identity_json(value, label=label)
        # Re-decode canonical bytes to return a completely independent graph.
        decoded = decode_identity_json(canonical_json_bytes(value), label=label)
    if type(decoded) is not dict:
        raise _identity_error(label, "top-level value must be an object")
    return decoded


def canonical_json_bytes(value: object) -> bytes:
    """Return sorted compact UTF-8 bytes for one strict identity value."""

    validated = validate_identity_json(value)
    try:
        return json.dumps(
            validated,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _identity_error("JSON value", f"cannot encode: {exc}") from exc


def rendered_json_bytes(value: object) -> bytes:
    """Return deterministic, human-readable UTF-8 bytes with one final LF."""

    validated = validate_identity_json(value)
    try:
        rendered = json.dumps(
            validated,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        return (rendered + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise _identity_error("JSON value", f"cannot encode: {exc}") from exc


def canonical_json_sha256(value: object) -> str:
    """Hash one strict semantic JSON value."""

    return sha256_bytes(canonical_json_bytes(value))


def canonical_json_equal(left: object, right: object) -> bool:
    """Compare strict JSON values by canonical bytes, preserving scalar types."""

    return canonical_json_bytes(left) == canonical_json_bytes(right)


def canonical_changed_keys(before: object, after: object) -> tuple[str, ...]:
    """Return sorted top-level keys whose presence or canonical bytes changed."""

    validate_identity_json(before, label="before mapping")
    validate_identity_json(after, label="after mapping")
    if type(before) is not dict or type(after) is not dict:
        raise PipelineError("canonical delta operands must be JSON objects")
    changed: list[str] = []
    for key in sorted(set(before) | set(after)):
        if key not in before or key not in after:
            changed.append(key)
            continue
        if canonical_json_bytes(before[key]) != canonical_json_bytes(after[key]):
            changed.append(key)
    return tuple(changed)


def _normalized_key_set(values: Iterable[str], *, label: str) -> frozenset[str]:
    items = tuple(values)
    if any(type(item) is not str or not item for item in items):
        raise PipelineError(f"{label} must contain nonempty strings")
    if len(items) != len(set(items)):
        raise PipelineError(f"{label} must not contain duplicates")
    return frozenset(items)


def require_mapping_delta(
    before: object,
    after: object,
    *,
    allowed_keys: Iterable[str],
    required_keys: Iterable[str],
    label: str = "mapping delta",
) -> tuple[str, ...]:
    """Require an exact canonical top-level change policy and return changes."""

    allowed = _normalized_key_set(allowed_keys, label=f"{label} allowed keys")
    required = _normalized_key_set(required_keys, label=f"{label} required keys")
    if not required <= allowed:
        raise PipelineError(f"{label} required keys must be a subset of allowed keys")
    changed = canonical_changed_keys(before, after)
    changed_set = frozenset(changed)
    unexpected = sorted(changed_set - allowed)
    missing = sorted(required - changed_set)
    if unexpected or missing:
        details: list[str] = []
        if unexpected:
            details.append(f"unexpected={unexpected}")
        if missing:
            details.append(f"missing={missing}")
        raise PipelineError(f"{label} is not exact: {'; '.join(details)}")
    return changed


def validate_json_pointer(value: object) -> str:
    """Validate one non-root canonical JSON pointer used by delta policies."""

    value = validate_utf8_string(value, label="JSON pointer")
    if value == "":
        return value
    if not value.startswith("/"):
        raise PipelineError("non-root JSON pointer must begin with /")
    tokens = value[1:].split("/")
    for token in tokens:
        if _BAD_POINTER_ESCAPE_RE.search(token):
            raise PipelineError("JSON pointer contains a non-canonical escape")
        decoded = token.replace("~1", "/").replace("~0", "~")
        encoded = decoded.replace("~", "~0").replace("/", "~1")
        if encoded != token:
            raise PipelineError("JSON pointer is not canonically escaped")
    return value


__all__ = [
    "JsonValue",
    "canonical_changed_keys",
    "canonical_json_bytes",
    "canonical_json_equal",
    "canonical_json_sha256",
    "decode_identity_json",
    "decode_identity_object",
    "rendered_json_bytes",
    "require_mapping_delta",
    "validate_identity_json",
    "validate_json_pointer",
    "validate_utf8_string",
]
