from __future__ import annotations

import hashlib
import unittest

from scripts.core_pipeline_lib.campaign.json_wire import (
    canonical_changed_keys,
    canonical_json_bytes,
    canonical_json_equal,
    canonical_json_sha256,
    decode_identity_json,
    decode_identity_object,
    rendered_json_bytes,
    require_mapping_delta,
    validate_json_pointer,
)
from scripts.core_pipeline_lib.errors import PipelineError


class _IntSubclass(int):
    pass


class _StringSubclass(str):
    pass


class _ListSubclass(list[object]):
    pass


class _DictSubclass(dict[str, object]):
    pass


class CampaignJsonWireTests(unittest.TestCase):
    def test_canonical_encoding_is_exact_sorted_compact_utf8(self) -> None:
        value = {
            "z": [True, None, -2],
            "é": "雪",
            "a": {"b": 0},
        }

        encoded = canonical_json_bytes(value)

        self.assertEqual(
            encoded,
            '{"a":{"b":0},"z":[true,null,-2],"é":"雪"}'.encode(),
        )
        self.assertNotIn(b"\n", encoded)
        self.assertNotIn(b"\\u00e9", encoded)

    def test_rendered_encoding_is_exact_utf8_with_one_terminal_lf(self) -> None:
        value = {
            "z": [True, None, -2],
            "é": "雪",
            "a": {"b": 0},
        }

        self.assertEqual(
            rendered_json_bytes(value),
            (
                "{\n"
                '  "a": {\n'
                '    "b": 0\n'
                "  },\n"
                '  "z": [\n'
                "    true,\n"
                "    null,\n"
                "    -2\n"
                "  ],\n"
                '  "é": "雪"\n'
                "}\n"
            ).encode(),
        )
        self.assertTrue(rendered_json_bytes(value).endswith(b"}\n"))
        self.assertFalse(rendered_json_bytes(value).endswith(b"\n\n"))

    def test_digest_is_of_the_canonical_bytes(self) -> None:
        value = {"β": [None, False, 123456789012345678901234567890]}

        self.assertEqual(
            canonical_json_sha256(value),
            hashlib.sha256(canonical_json_bytes(value)).hexdigest(),
        )

    def test_identity_domain_accepts_only_closed_json_values(self) -> None:
        value = {
            "none": None,
            "booleans": [False, True],
            "integers": [0, -1, 123456789012345678901234567890],
            "string": "Unicode: café 雪",
            "containers": [{}, []],
        }

        decoded = decode_identity_object(value)

        self.assertEqual(decoded, value)
        self.assertIsNot(decoded, value)
        self.assertIsNot(decoded["containers"], value["containers"])

        value["containers"].append("mutated")
        self.assertEqual(decoded["containers"], [{}, []])

    def test_identity_domain_rejects_floats_and_custom_values_at_any_depth(
        self,
    ) -> None:
        rejected = (
            0.0,
            -0.0,
            1.0,
            float("nan"),
            float("inf"),
            float("-inf"),
            b"bytes",
            bytearray(b"bytes"),
            ("tuple",),
            {"set"},
            complex(1, 2),
            object(),
            _IntSubclass(1),
            _StringSubclass("string"),
            _ListSubclass([1]),
            _DictSubclass({"key": "value"}),
        )

        for value in rejected:
            with self.subTest(value=repr(value), position="root"):
                with self.assertRaises(PipelineError):
                    decode_identity_object(value)
                with self.assertRaises(PipelineError):
                    canonical_json_bytes(value)
            with self.subTest(value=repr(value), position="nested"):
                with self.assertRaises(PipelineError):
                    decode_identity_object({"outer": [value]})
                with self.assertRaises(PipelineError):
                    canonical_json_bytes({"outer": [value]})

    def test_identity_domain_requires_exact_string_mapping_keys(self) -> None:
        for key in (1, False, _StringSubclass("key")):
            with self.subTest(key=repr(key)):
                with self.assertRaises(PipelineError):
                    decode_identity_object({key: "value"})
                with self.assertRaises(PipelineError):
                    canonical_json_bytes({key: "value"})

    def test_strict_decoder_rejects_duplicate_keys(self) -> None:
        duplicate_documents = (
            b'{"a":1,"a":2}',
            b'{"outer":{"a":1,"a":2}}',
        )

        for document in duplicate_documents:
            with self.subTest(document=document):
                with self.assertRaises(PipelineError):
                    decode_identity_json(document)

    def test_strict_decoder_rejects_invalid_utf8_trailing_data_and_floats(
        self,
    ) -> None:
        rejected_documents = (
            b'"\xff"',
            b"{} null",
            b"{}\n[]",
            b"0.0",
            b"1e0",
            b"NaN",
            b"Infinity",
            b"-Infinity",
            b'{"value":-0.0}',
        )

        for document in rejected_documents:
            with self.subTest(document=document):
                with self.assertRaises(PipelineError):
                    decode_identity_json(document)

    def test_identity_domain_rejects_lone_unicode_surrogates(self) -> None:
        for value in ("\ud800", {"nested": "\udfff"}, {"\ud800": 1}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(PipelineError):
                    canonical_json_bytes(value)
        for document in (
            b'"\\ud800"',
            b'{"nested":"\\udfff"}',
            b'{"\\ud800":1}',
        ):
            with self.subTest(document=document):
                with self.assertRaises(PipelineError):
                    decode_identity_json(document)

    def test_identity_domain_rejects_container_cycles_but_accepts_shared_dags(
        self,
    ) -> None:
        self_list: list[object] = []
        self_list.append(self_list)
        self_dict: dict[str, object] = {}
        self_dict["self"] = self_dict
        left: list[object] = []
        right: dict[str, object] = {"left": left}
        left.append(right)

        for value in (self_list, self_dict, {"indirect": left}):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(PipelineError):
                    canonical_json_bytes(value)
                with self.assertRaises(PipelineError):
                    decode_identity_object(value)

        shared = {"leaf": [1, "same"]}
        dag = {"left": shared, "right": shared}
        self.assertEqual(
            decode_identity_object(dag),
            {"left": {"leaf": [1, "same"]}, "right": {"leaf": [1, "same"]}},
        )
        self.assertEqual(
            canonical_json_bytes(dag),
            b'{"left":{"leaf":[1,"same"]},"right":{"leaf":[1,"same"]}}',
        )

    def test_excessive_nesting_is_normalized_to_pipeline_error(self) -> None:
        value: object = None
        for _ in range(2_000):
            value = [value]
        with self.assertRaises(PipelineError):
            canonical_json_bytes(value)

        document = (b"[" * 2_000) + b"null" + (b"]" * 2_000)
        with self.assertRaises(PipelineError):
            decode_identity_json(document)

    def test_strict_decoder_roundtrips_every_identity_root_kind(self) -> None:
        values = (
            None,
            False,
            0,
            -7,
            "雪",
            [],
            {},
            {"nested": [True, None, 42, "é"]},
        )

        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    decode_identity_json(canonical_json_bytes(value)),
                    value,
                )

    def test_canonical_comparison_does_not_use_python_scalar_equality(self) -> None:
        self.assertTrue(
            canonical_json_equal(
                {"b": [1, None], "a": "same"},
                {"a": "same", "b": [1, None]},
            )
        )
        self.assertFalse(canonical_json_equal(True, 1))
        self.assertFalse(canonical_json_equal(False, 0))
        self.assertFalse(canonical_json_equal({}, {"value": None}))

    def test_changed_keys_are_sorted_and_distinguish_aliases_and_absence(
        self,
    ) -> None:
        before = {"bool": True, "gone": None, "same": {"b": 2, "a": 1}}
        after = {"bool": 1, "new": None, "same": {"a": 1, "b": 2}}

        self.assertEqual(
            canonical_changed_keys(before, after),
            ("bool", "gone", "new"),
        )

    def test_mapping_delta_allows_optional_unchanged_keys(self) -> None:
        before = {"authority": "old", "optional": 1, "stable": None}
        after = {"authority": "new", "optional": 1, "stable": None}

        self.assertEqual(
            require_mapping_delta(
                before,
                after,
                allowed_keys=("authority", "optional"),
                required_keys=("authority",),
            ),
            ("authority",),
        )

    def test_mapping_delta_rejects_missing_required_and_extra_changes(self) -> None:
        cases = (
            (
                {"required": 1, "stable": 1},
                {"required": 1, "stable": 1},
                ("required",),
                ("required",),
            ),
            (
                {"required": 1, "stable": 1},
                {"required": 2, "stable": 2},
                ("required",),
                ("required",),
            ),
            (
                {"required": 1},
                {"required": 2},
                (),
                ("required",),
            ),
        )

        for before, after, allowed, required in cases:
            with self.subTest(
                before=before,
                after=after,
                allowed=allowed,
                required=required,
            ):
                with self.assertRaises(PipelineError):
                    require_mapping_delta(
                        before,
                        after,
                        allowed_keys=allowed,
                        required_keys=required,
                    )

    def test_mapping_delta_counts_bool_int_and_absent_null_as_changes(self) -> None:
        self.assertEqual(
            require_mapping_delta(
                {"alias": False},
                {"alias": 0},
                allowed_keys=("alias",),
                required_keys=("alias",),
            ),
            ("alias",),
        )
        self.assertEqual(
            require_mapping_delta(
                {},
                {"nullable": None},
                allowed_keys=("nullable",),
                required_keys=("nullable",),
            ),
            ("nullable",),
        )

    def test_json_pointer_validation_accepts_only_canonical_rfc6901_strings(
        self,
    ) -> None:
        accepted = ("", "/", "/a", "/a~0b", "/a~1b", "/雪/0")
        rejected = (
            "a",
            "#/a",
            "/a~",
            "/a~2b",
            1,
            None,
            _StringSubclass("/a"),
        )

        for pointer in accepted:
            with self.subTest(pointer=pointer):
                self.assertEqual(validate_json_pointer(pointer), pointer)
        for pointer in rejected:
            with self.subTest(pointer=repr(pointer)):
                with self.assertRaises(PipelineError):
                    validate_json_pointer(pointer)


if __name__ == "__main__":
    unittest.main()
