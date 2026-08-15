"""Pure codec for historical ``spruce-host-core-campaign-matrix-v2`` JSON.

The legacy matrix format predates the campaign identity wire format.  It uses
the same deterministic UTF-8 encodings, but finite JSON floats remain part of
its authenticated domain.  Keeping that distinction in this small module lets
the H3 planner reproduce historical matrix identities without importing a
held executable generator.
"""

from __future__ import annotations

import json
import math
from typing import TypeAlias

from ..errors import PipelineError
from ..foundation import sha256_bytes


MatrixV2Scalar: TypeAlias = None | bool | int | float | str
MatrixV2Value: TypeAlias = (
    MatrixV2Scalar | list["MatrixV2Value"] | dict[str, "MatrixV2Value"]
)


def _matrix_error(label: str, detail: str) -> PipelineError:
    return PipelineError(f"{label} is not legacy matrix v2 JSON: {detail}")


def _require_utf8_string(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise _matrix_error(label, "must be an exact string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _matrix_error(label, "must not contain a lone surrogate") from exc
    return value


def _validate_matrix_value(
    value: object,
    *,
    label: str,
    path: str,
    active_containers: set[int],
) -> None:
    value_type = type(value)
    if value is None or value_type in {bool, int}:
        return
    if value_type is float:
        if not math.isfinite(value):
            raise _matrix_error(label, f"{path} contains a non-finite float")
        return
    if value_type is str:
        _require_utf8_string(value, label=f"{label} {path}")
        return
    if value_type is list:
        identity = id(value)
        if identity in active_containers:
            raise _matrix_error(label, f"{path} contains a container cycle")
        active_containers.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_matrix_value(
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
            raise _matrix_error(label, f"{path} contains a container cycle")
        active_containers.add(identity)
        try:
            for key, item in value.items():
                key = _require_utf8_string(key, label=f"{label} {path} key")
                _validate_matrix_value(
                    item,
                    label=label,
                    path=f"{path}.{key}",
                    active_containers=active_containers,
                )
        finally:
            active_containers.remove(identity)
        return
    raise _matrix_error(
        label,
        f"{path} contains unsupported type {value_type.__name__}",
    )


def _validate_matrix_json(
    value: object,
    *,
    label: str = "legacy matrix v2 value",
) -> MatrixV2Value:
    try:
        _validate_matrix_value(
            value,
            label=label,
            path="$",
            active_containers=set(),
        )
    except RecursionError as exc:
        raise _matrix_error(label, "nesting exceeds the supported depth") from exc
    return value  # type: ignore[return-value]


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise _matrix_error("legacy matrix v2 input", f"non-finite float {token!r}")
    return value


def _reject_constant(token: str) -> None:
    raise _matrix_error("legacy matrix v2 input", f"constant {token!r} is forbidden")


def _closed_object(
    pairs: list[tuple[str, MatrixV2Value]],
) -> dict[str, MatrixV2Value]:
    result: dict[str, MatrixV2Value] = {}
    for key, value in pairs:
        if key in result:
            raise _matrix_error(
                "legacy matrix v2 input",
                f"duplicate object key {key!r}",
            )
        result[key] = value
    return result


def decode_matrix_v2(raw: bytes) -> dict[str, object]:
    """Decode one strict UTF-8 historical matrix-v2 object."""

    if type(raw) is not bytes:
        raise PipelineError("legacy matrix v2 input must be bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _matrix_error("legacy matrix v2 input", f"invalid UTF-8: {exc}") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_float=_parse_finite_float,
            parse_constant=_reject_constant,
        )
    except PipelineError:
        raise
    except (ValueError, RecursionError) as exc:
        raise _matrix_error("legacy matrix v2 input", f"invalid JSON: {exc}") from exc
    decoded = _validate_matrix_json(value, label="legacy matrix v2 input")
    if type(decoded) is not dict:
        raise _matrix_error("legacy matrix v2 input", "top-level value must be an object")
    return decoded  # type: ignore[return-value]


def matrix_v2_canonical_bytes(value: object) -> bytes:
    """Return sorted compact UTF-8 semantic bytes for a legacy matrix value."""

    validated = _validate_matrix_json(value)
    try:
        return json.dumps(
            validated,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeEncodeError,
        RecursionError,
    ) as exc:
        raise _matrix_error("legacy matrix v2 value", f"cannot encode: {exc}") from exc


def matrix_v2_semantic_sha256(document: object) -> str:
    """Hash a matrix object after omitting only its outer content digest."""

    validated = _validate_matrix_json(document, label="legacy matrix v2 document")
    if type(validated) is not dict:
        raise _matrix_error(
            "legacy matrix v2 document",
            "top-level value must be an object",
        )
    material = {
        key: value
        for key, value in validated.items()
        if key != "content_sha256"
    }
    return sha256_bytes(matrix_v2_canonical_bytes(material))


def render_matrix_v2(document: object) -> bytes:
    """Render deterministic human-readable UTF-8 bytes with one final LF."""

    validated = _validate_matrix_json(document, label="legacy matrix v2 document")
    if type(validated) is not dict:
        raise _matrix_error(
            "legacy matrix v2 document",
            "top-level value must be an object",
        )
    try:
        rendered = json.dumps(
            validated,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        return (rendered + "\n").encode("utf-8")
    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeEncodeError,
        RecursionError,
    ) as exc:
        raise _matrix_error("legacy matrix v2 document", f"cannot encode: {exc}") from exc


__all__ = [
    "decode_matrix_v2",
    "matrix_v2_canonical_bytes",
    "matrix_v2_semantic_sha256",
    "render_matrix_v2",
]
