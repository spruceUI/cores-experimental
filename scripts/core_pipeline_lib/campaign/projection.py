"""Pure JSON-pointer delta and preserved-projection helpers.

The helpers in this module deliberately accept a canonical-byte callback.  That
keeps equality and hashing coupled to the wire contract selected by the caller
instead of silently falling back to Python's value equality.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ..errors import PipelineError
from ..foundation import sha256_bytes


__all__ = (
    "decode_json_pointer",
    "encode_json_pointer",
    "canonical_changed_pointers",
    "project_without_pointers",
    "projection_sha256",
    "require_exact_pointer_delta",
)


_CanonicalBytes = Callable[[object], bytes]


def _require_exact_string(value: object, label: str) -> str:
    if type(value) is not str:
        raise PipelineError(f"{label} must be an exact string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise PipelineError(f"{label} must be valid UTF-8 text") from exc
    return value


def decode_json_pointer(pointer: object) -> tuple[str, ...]:
    """Decode one RFC 6901 JSON pointer into its exact string tokens."""

    pointer = _require_exact_string(pointer, "JSON pointer")
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise PipelineError("non-root JSON pointer must start with '/'")

    decoded: list[str] = []
    for raw_token in pointer[1:].split("/"):
        token: list[str] = []
        index = 0
        while index < len(raw_token):
            character = raw_token[index]
            if character != "~":
                token.append(character)
                index += 1
                continue
            if index + 1 >= len(raw_token) or raw_token[index + 1] not in "01":
                raise PipelineError(
                    f"JSON pointer contains an invalid escape in {pointer!r}"
                )
            token.append("~" if raw_token[index + 1] == "0" else "/")
            index += 2
        decoded.append(_require_exact_string("".join(token), "JSON pointer token"))
    return tuple(decoded)


def encode_json_pointer(tokens: Iterable[object]) -> str:
    """Encode exact string tokens as one RFC 6901 JSON pointer."""

    if isinstance(tokens, str):
        raise PipelineError("JSON pointer tokens must be an iterable of exact strings")
    try:
        materialized = tuple(tokens)
    except TypeError as exc:
        raise PipelineError("JSON pointer tokens must be iterable") from exc

    encoded: list[str] = []
    for index, token in enumerate(materialized):
        token = _require_exact_string(token, f"JSON pointer token {index}")
        encoded.append(token.replace("~", "~0").replace("/", "~1"))
    if not encoded:
        return ""
    return "/" + "/".join(encoded)


def _canonical(value: object, canonical_bytes: _CanonicalBytes, label: str) -> bytes:
    if not callable(canonical_bytes):
        raise PipelineError("canonical_bytes must be callable")
    try:
        rendered = canonical_bytes(value)
    except PipelineError:
        raise
    except Exception as exc:
        raise PipelineError(f"cannot canonically encode {label}: {exc}") from exc
    if type(rendered) is not bytes:
        raise PipelineError("canonical_bytes must return exact bytes")
    return rendered


def _canonical_sha256(
    value: object,
    canonical_bytes: _CanonicalBytes,
    label: str,
) -> str:
    """Hash one canonical value without retaining a peer serialization."""

    return sha256_bytes(_canonical(value, canonical_bytes, label))


def _mapping_keys(value: dict[object, object], label: str) -> set[str]:
    keys: set[str] = set()
    for key in value:
        keys.add(_require_exact_string(key, f"{label} mapping key"))
    return keys


def _detached_copy(value: object, active_containers: set[int]) -> object:
    """Copy each JSON container occurrence without retaining caller aliases."""

    if type(value) is dict:
        identity = id(value)
        if identity in active_containers:
            raise PipelineError("projection document must not contain a container cycle")
        active_containers.add(identity)
        try:
            return {
                _require_exact_string(key, "projection document mapping key"): _detached_copy(
                    item,
                    active_containers,
                )
                for key, item in value.items()
            }
        finally:
            active_containers.remove(identity)
    if type(value) is list:
        identity = id(value)
        if identity in active_containers:
            raise PipelineError("projection document must not contain a container cycle")
        active_containers.add(identity)
        try:
            return [_detached_copy(item, active_containers) for item in value]
        finally:
            active_containers.remove(identity)
    return value


def canonical_changed_pointers(
    before: object,
    after: object,
    *,
    canonical_bytes: _CanonicalBytes,
) -> tuple[str, ...]:
    """Return the sorted RFC 6901 leaves changed under canonical equality.

    Objects are compared recursively.  Arrays and all non-object values are
    atomic, so a change anywhere within an array is reported at the array's
    member pointer.
    """

    changed: list[str] = []

    def visit(left: object, right: object, tokens: tuple[str, ...]) -> None:
        if type(left) is dict and type(right) is dict:
            left_keys = _mapping_keys(left, "before")
            right_keys = _mapping_keys(right, "after")
            for key in left_keys | right_keys:
                child_tokens = (*tokens, key)
                if key not in left_keys or key not in right_keys:
                    changed.append(encode_json_pointer(child_tokens))
                    continue
                visit(left[key], right[key], child_tokens)
            return

        # Arrays are atomic by policy.  Hash the two canonical forms
        # sequentially so a large preserved matrix array never requires two
        # full serialized buffers to coexist.
        if _canonical_sha256(left, canonical_bytes, "before value") == (
            _canonical_sha256(right, canonical_bytes, "after value")
        ):
            return

        changed.append(encode_json_pointer(tokens))

    visit(before, after, ())
    return tuple(sorted(changed))


def _materialize_pointer_set(
    pointers: Iterable[object],
    label: str,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if isinstance(pointers, str):
        raise PipelineError(f"{label} must be an iterable of JSON pointers")
    try:
        materialized = tuple(pointers)
    except TypeError as exc:
        raise PipelineError(f"{label} must be iterable") from exc

    decoded: list[tuple[str, tuple[str, ...]]] = []
    for pointer in materialized:
        pointer = _require_exact_string(pointer, f"{label} entry")
        tokens = decode_json_pointer(pointer)
        if not tokens:
            raise PipelineError(f"{label} cannot contain the document root pointer")
        decoded.append((pointer, tokens))

    encoded = tuple(pointer for pointer, _tokens in decoded)
    if encoded != tuple(sorted(encoded)):
        raise PipelineError(f"{label} must be sorted")
    if len(set(encoded)) != len(encoded):
        raise PipelineError(f"{label} must not contain duplicate pointers")

    for index, (pointer, tokens) in enumerate(decoded):
        for other_pointer, other_tokens in decoded[index + 1 :]:
            common_length = min(len(tokens), len(other_tokens))
            if tokens[:common_length] == other_tokens[:common_length]:
                raise PipelineError(
                    f"{label} contains overlapping pointers "
                    f"{pointer!r} and {other_pointer!r}"
                )
    return tuple(decoded)


def project_without_pointers(
    document: object,
    pointers: Iterable[object],
) -> object:
    """Deep-copy a JSON object and remove existing mapping members by pointer."""

    decoded = _materialize_pointer_set(pointers, "projection pointers")
    if type(document) is not dict:
        raise PipelineError("projection document must be an exact mapping")

    projected = _detached_copy(document, set())
    for pointer, tokens in decoded:
        current: object = projected
        for token in tokens[:-1]:
            if type(current) is list:
                raise PipelineError(
                    f"projection pointer {pointer!r} must not traverse an array"
                )
            if type(current) is not dict:
                raise PipelineError(
                    f"projection pointer {pointer!r} must traverse mappings only"
                )
            if token not in current:
                raise PipelineError(f"projection pointer {pointer!r} does not exist")
            current = current[token]

        if type(current) is list:
            raise PipelineError(
                f"projection pointer {pointer!r} must not select an array member"
            )
        if type(current) is not dict:
            raise PipelineError(
                f"projection pointer {pointer!r} must select a mapping member"
            )
        final_token = tokens[-1]
        if final_token not in current:
            raise PipelineError(f"projection pointer {pointer!r} does not exist")
        del current[final_token]
    return projected


def _canonical_projection_view(
    document: object,
    decoded: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    allow_missing_final: bool,
) -> dict[str, object]:
    """Copy only mapping spines needed to remove pointers for serialization.

    The returned view is private and immediately serialized; unlike the public
    projection helper it may share untouched descendants with the input.  This
    avoids cloning the multi-million-node legacy matrix twice merely to compare
    preserved canonical bytes.
    """

    if type(document) is not dict:
        raise PipelineError("projection document must be an exact mapping")
    root: dict[str, object] = dict(document)
    cloned: dict[tuple[str, ...], dict[str, object]] = {(): root}
    for pointer, tokens in decoded:
        source: object = document
        destination = root
        prefix: tuple[str, ...] = ()
        for token in tokens[:-1]:
            if type(source) is list:
                raise PipelineError(
                    f"projection pointer {pointer!r} must not traverse an array"
                )
            if type(source) is not dict:
                raise PipelineError(
                    f"projection pointer {pointer!r} must traverse mappings only"
                )
            if token not in source:
                raise PipelineError(f"projection pointer {pointer!r} does not exist")
            source = source[token]
            prefix = (*prefix, token)
            if prefix not in cloned:
                if type(source) is not dict:
                    if type(source) is list:
                        raise PipelineError(
                            f"projection pointer {pointer!r} must not traverse an array"
                        )
                    raise PipelineError(
                        f"projection pointer {pointer!r} must traverse mappings only"
                    )
                cloned[prefix] = dict(source)
                destination[token] = cloned[prefix]
            destination = cloned[prefix]

        if type(source) is list:
            raise PipelineError(
                f"projection pointer {pointer!r} must not select an array member"
            )
        if type(source) is not dict:
            raise PipelineError(
                f"projection pointer {pointer!r} must select a mapping member"
            )
        final_token = tokens[-1]
        if final_token not in source:
            if allow_missing_final:
                continue
            raise PipelineError(f"projection pointer {pointer!r} does not exist")
        destination.pop(final_token, None)
    return root


def projection_sha256(
    document: object,
    pointers: Iterable[object],
    *,
    canonical_bytes: _CanonicalBytes,
) -> str:
    """Hash the canonical deep projection with the selected members removed."""

    projection = project_without_pointers(document, pointers)
    return sha256_bytes(_canonical(projection, canonical_bytes, "projection"))


def _require_sha256(value: object, label: str) -> str:
    value = _require_exact_string(value, label)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise PipelineError(f"{label} must be a lowercase SHA-256 digest")
    return value


def require_exact_pointer_delta(
    before: object,
    after: object,
    *,
    allowed_pointers: Iterable[object],
    required_pointers: Iterable[object],
    canonical_bytes: _CanonicalBytes,
    expected_projection_sha256: object | None = None,
) -> tuple[str, ...]:
    """Require an exact authorized delta and equal canonical projections.

    Deep leaf changes are collapsed to the selected nonoverlapping allowed
    subtree pointer.  The returned tuple therefore uses the caller's policy
    vocabulary even when an allowed mapping value changes internally.
    """

    allowed = _materialize_pointer_set(allowed_pointers, "allowed_pointers")
    required = _materialize_pointer_set(required_pointers, "required_pointers")
    allowed_values = tuple(pointer for pointer, _tokens in allowed)
    required_values = tuple(pointer for pointer, _tokens in required)
    allowed_set = set(allowed_values)
    required_set = set(required_values)
    if not required_set <= allowed_set:
        extra = tuple(sorted(required_set - allowed_set))
        raise PipelineError(
            f"required_pointers must be a subset of allowed_pointers: {extra!r}"
        )

    leaf_changes = canonical_changed_pointers(
        before,
        after,
        canonical_bytes=canonical_bytes,
    )
    changed_set: set[str] = set()
    unexpected_leaves: list[str] = []
    for leaf_pointer in leaf_changes:
        leaf_tokens = decode_json_pointer(leaf_pointer)
        matched_pointer = next(
            (
                allowed_pointer
                for allowed_pointer, allowed_tokens in allowed
                if leaf_tokens[: len(allowed_tokens)] == allowed_tokens
            ),
            None,
        )
        if matched_pointer is None:
            unexpected_leaves.append(leaf_pointer)
        else:
            changed_set.add(matched_pointer)

    unexpected = tuple(sorted(unexpected_leaves))
    missing = tuple(sorted(required_set - changed_set))
    if unexpected:
        raise PipelineError(f"delta contains unexpected pointers: {unexpected!r}")
    if missing:
        raise PipelineError(f"delta is missing required pointers: {missing!r}")

    before_projection = _canonical_projection_view(
        before,
        allowed,
        allow_missing_final=True,
    )
    before_projection_sha256 = _canonical_sha256(
        before_projection,
        canonical_bytes,
        "before projection",
    )
    del before_projection
    after_projection = _canonical_projection_view(
        after,
        allowed,
        allow_missing_final=True,
    )
    after_projection_sha256 = _canonical_sha256(
        after_projection,
        canonical_bytes,
        "after projection",
    )
    if before_projection_sha256 != after_projection_sha256:
        raise PipelineError("canonical preserved projections differ")

    actual_projection_sha256 = before_projection_sha256
    if expected_projection_sha256 is not None:
        expected = _require_sha256(
            expected_projection_sha256,
            "expected_projection_sha256",
        )
        if actual_projection_sha256 != expected:
            raise PipelineError(
                "preserved projection SHA-256 mismatch: "
                f"expected {expected}, got {actual_projection_sha256}"
            )
    return tuple(sorted(changed_set))
