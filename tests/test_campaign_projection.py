from __future__ import annotations

import copy
import json
import unittest

from scripts.core_pipeline_lib.campaign.projection import (
    canonical_changed_pointers,
    decode_json_pointer,
    encode_json_pointer,
    project_without_pointers,
    projection_sha256,
    require_exact_pointer_delta,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class _StringSubclass(str):
    pass


class CampaignProjectionTests(unittest.TestCase):
    def test_pointer_round_trip_including_root_empty_and_escaped_tokens(self) -> None:
        tokens = ("", "/", "~", "a/b~c", "snowman-☃")
        pointer = "/" + "/".join(("", "~1", "~0", "a~1b~0c", "snowman-☃"))
        self.assertEqual(encode_json_pointer(()), "")
        self.assertEqual(decode_json_pointer(""), ())
        self.assertEqual(encode_json_pointer(tokens), pointer)
        self.assertEqual(decode_json_pointer(pointer), tokens)

    def test_pointer_codec_rejects_non_exact_strings_and_bad_escapes(self) -> None:
        for pointer in (1, _StringSubclass("/a")):
            with self.subTest(pointer=pointer):
                with self.assertRaises(PipelineError):
                    decode_json_pointer(pointer)
        for pointer in ("a", "/~", "/~2", "/a~x", "/\ud800"):
            with self.subTest(pointer=pointer.encode("unicode_escape")):
                with self.assertRaises(PipelineError):
                    decode_json_pointer(pointer)

        for tokens in (
            "abc",
            _StringSubclass("abc"),
            (1,),
            (_StringSubclass("a"),),
            ("\ud800",),
        ):
            with self.subTest(tokens=tokens):
                with self.assertRaises(PipelineError):
                    encode_json_pointer(tokens)

    def test_changed_scalar_document_reports_the_root_pointer(self) -> None:
        self.assertEqual(
            canonical_changed_pointers(1, 2, canonical_bytes=_canonical_bytes),
            ("",),
        )

    def test_changed_pointers_are_deep_escaped_sorted_and_arrays_are_atomic(self) -> None:
        before = {
            "a/b": {"~key": 1},
            "array": [{"inside": 1}],
            "nested": {"same": True, "value": 1},
        }
        after = {
            "a/b": {"~key": 2},
            "array": [{"inside": 2}],
            "nested": {"same": True, "value": 3},
        }
        self.assertEqual(
            canonical_changed_pointers(
                before,
                after,
                canonical_bytes=_canonical_bytes,
            ),
            ("/array", "/a~1b/~0key", "/nested/value"),
        )

    def test_additions_removals_and_absent_null_report_member_leaf(self) -> None:
        before = {"gone": {"child": 1}, "stable": 1}
        after = {"nullable": None, "stable": 1}
        self.assertEqual(
            canonical_changed_pointers(
                before,
                after,
                canonical_bytes=_canonical_bytes,
            ),
            ("/gone", "/nullable"),
        )
        self.assertEqual(
            canonical_changed_pointers(
                {},
                {"value": None},
                canonical_bytes=_canonical_bytes,
            ),
            ("/value",),
        )

    def test_bool_int_and_finite_float_follow_canonical_codec(self) -> None:
        cases = (
            ({"value": False}, {"value": 0}),
            ({"value": True}, {"value": 1}),
            ({"value": 1}, {"value": 1.0}),
            ({"value": -0.0}, {"value": 0.0}),
        )
        for before, after in cases:
            with self.subTest(before=before, after=after):
                self.assertEqual(
                    canonical_changed_pointers(
                        before,
                        after,
                        canonical_bytes=_canonical_bytes,
                    ),
                    ("/value",),
                )

        def aliasing_codec(value: object) -> bytes:
            if type(value) in (bool, int, float):
                return b"numeric-alias"
            if type(value) is dict and set(value) == {"value"}:
                return b"mapping-differs"
            return _canonical_bytes(value)

        self.assertEqual(
            canonical_changed_pointers(
                {"value": False},
                {"value": 0},
                canonical_bytes=aliasing_codec,
            ),
            (),
        )

    def test_canonical_callback_must_return_exact_bytes(self) -> None:
        for result in ("bytes", bytearray(b"bytes")):
            with self.subTest(result=result):
                with self.assertRaises(PipelineError):
                    canonical_changed_pointers(
                        {"a": 1},
                        {"a": 2},
                        canonical_bytes=lambda _value, result=result: result,
                    )

    def test_projection_requires_sorted_unique_nonoverlapping_leaf_pointers(self) -> None:
        document = {"a": {"b": 1}, "b": 2}
        invalid_sets = (
            ("/b", "/a/b"),
            ("/a/b", "/a/b"),
            ("/a", "/a/b"),
            ("",),
        )
        for pointers in invalid_sets:
            with self.subTest(pointers=pointers):
                with self.assertRaises(PipelineError):
                    project_without_pointers(document, pointers)

    def test_projection_rejects_missing_nonmapping_and_array_paths(self) -> None:
        document = {
            "array": [{"value": 1}],
            "mapping": {"value": 1},
            "scalar": 1,
        }
        for pointers in (
            ("/missing",),
            ("/mapping/missing",),
            ("/scalar/value",),
            ("/array/0",),
        ):
            with self.subTest(pointers=pointers):
                with self.assertRaises(PipelineError):
                    project_without_pointers(document, pointers)

    def test_projection_is_a_deep_copy_with_no_caller_aliases(self) -> None:
        document = {
            "drop": {"entire": [1, 2]},
            "keep": {"nested": [1, {"value": 2}]},
        }
        original = copy.deepcopy(document)
        projected = project_without_pointers(document, ("/drop",))
        self.assertEqual(document, original)
        self.assertEqual(projected, {"keep": {"nested": [1, {"value": 2}]}})

        projected["keep"]["nested"][1]["value"] = 9
        self.assertEqual(document["keep"]["nested"][1]["value"], 2)
        document["keep"]["nested"].append(3)
        self.assertEqual(len(projected["keep"]["nested"]), 2)

    def test_projection_does_not_retain_shared_container_aliases(self) -> None:
        shared = {"drop": 1, "keep": [2]}
        document = {"left": shared, "right": shared}
        projected = project_without_pointers(document, ("/left/drop",))
        self.assertEqual(projected["left"], {"keep": [2]})
        self.assertEqual(projected["right"], {"drop": 1, "keep": [2]})
        self.assertIsNot(projected["left"], projected["right"])
        self.assertIsNot(projected["left"]["keep"], document["left"]["keep"])

    def test_projection_hash_uses_canonical_projected_bytes(self) -> None:
        document = {"drop": 1, "keep": {"value": 2}}
        expected = sha256_bytes(_canonical_bytes({"keep": {"value": 2}}))
        self.assertEqual(
            projection_sha256(
                document,
                ("/drop",),
                canonical_bytes=_canonical_bytes,
            ),
            expected,
        )

    def test_exact_delta_accepts_required_changes_and_optional_allowed_change(self) -> None:
        before = {
            "authority": "old",
            "inputs": {"generator": "old", "pipeline": "same"},
            "optional": 1,
            "stable": {"value": 7},
        }
        after = {
            "authority": "new",
            "inputs": {"generator": "new", "pipeline": "same"},
            "optional": 1,
            "stable": {"value": 7},
        }
        pointers = ("/authority", "/inputs/generator", "/optional")
        expected_hash = projection_sha256(
            before,
            pointers,
            canonical_bytes=_canonical_bytes,
        )
        self.assertEqual(
            require_exact_pointer_delta(
                before,
                after,
                allowed_pointers=pointers,
                required_pointers=("/authority", "/inputs/generator"),
                canonical_bytes=_canonical_bytes,
                expected_projection_sha256=expected_hash,
            ),
            ("/authority", "/inputs/generator"),
        )

    def test_exact_delta_accepts_authorized_direct_addition_and_removal(self) -> None:
        before = {"removed": {"value": 1}, "stable": [1, 2]}
        after = {"added": None, "stable": [1, 2]}
        pointers = ("/added", "/removed")
        self.assertEqual(
            require_exact_pointer_delta(
                before,
                after,
                allowed_pointers=pointers,
                required_pointers=pointers,
                canonical_bytes=_canonical_bytes,
            ),
            pointers,
        )

    def test_exact_delta_rejects_unexpected_or_missing_changes(self) -> None:
        before = {"allowed": 1, "required": 1, "stable": 1}
        cases = (
            ({"allowed": 2, "required": 2, "stable": 2}, PipelineError),
            ({"allowed": 2, "required": 1, "stable": 1}, PipelineError),
        )
        for after, error in cases:
            with self.subTest(after=after):
                with self.assertRaises(error):
                    require_exact_pointer_delta(
                        before,
                        after,
                        allowed_pointers=("/allowed", "/required"),
                        required_pointers=("/required",),
                        canonical_bytes=_canonical_bytes,
                    )

    def test_exact_delta_rejects_invalid_policy_sets_and_digest(self) -> None:
        before = {"a": {"b": 1}, "b": 1}
        after = {"a": {"b": 2}, "b": 2}
        cases = (
            (("/b", "/a/b"), ("/a/b",)),
            (("/a/b", "/a/b"), ("/a/b",)),
            (("/a", "/a/b"), ("/a",)),
            (("/a/b",), ("/b",)),
        )
        for allowed, required in cases:
            with self.subTest(allowed=allowed, required=required):
                with self.assertRaises(PipelineError):
                    require_exact_pointer_delta(
                        before,
                        after,
                        allowed_pointers=allowed,
                        required_pointers=required,
                        canonical_bytes=_canonical_bytes,
                    )

        with self.assertRaises(PipelineError):
            require_exact_pointer_delta(
                before,
                after,
                allowed_pointers=("/a/b", "/b"),
                required_pointers=("/a/b", "/b"),
                canonical_bytes=_canonical_bytes,
                expected_projection_sha256="0" * 64,
            )

        for policy in (_StringSubclass("/a/b"),):
            with self.assertRaises(PipelineError):
                require_exact_pointer_delta(
                    before,
                    after,
                    allowed_pointers=policy,
                    required_pointers=("/a/b",),
                    canonical_bytes=_canonical_bytes,
                )

    def test_exact_delta_does_not_mutate_callers(self) -> None:
        before = {"change": {"value": 1}, "stable": {"items": [1, 2]}}
        after = {"change": {"value": 2}, "stable": {"items": [1, 2]}}
        before_original = copy.deepcopy(before)
        after_original = copy.deepcopy(after)
        self.assertEqual(
            require_exact_pointer_delta(
                before,
                after,
                allowed_pointers=("/change",),
                required_pointers=("/change",),
                canonical_bytes=_canonical_bytes,
            ),
            ("/change",),
        )
        self.assertEqual(before, before_original)
        self.assertEqual(after, after_original)


if __name__ == "__main__":
    unittest.main()
