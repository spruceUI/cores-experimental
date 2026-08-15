from __future__ import annotations

import copy
import hashlib
import unittest

from scripts.core_pipeline_lib.campaign.legacy_matrix_v2 import (
    decode_matrix_v2,
    matrix_v2_canonical_bytes,
    matrix_v2_semantic_sha256,
    render_matrix_v2,
)
from scripts.core_pipeline_lib.errors import PipelineError


class _BoolLikeInt(int):
    pass


class _FloatSubclass(float):
    pass


class _StringSubclass(str):
    pass


class _ListSubclass(list[object]):
    pass


class _DictSubclass(dict[str, object]):
    pass


class CampaignLegacyMatrixV2Tests(unittest.TestCase):
    def test_decoder_accepts_exact_legacy_domain_including_finite_floats(
        self,
    ) -> None:
        raw = (
            '{"bool":false,"finite":[-0.0,1.25,6.02e+23],'
            '"integer":1,"none":null,"text":"café 雪"}'
        ).encode("utf-8")

        decoded = decode_matrix_v2(raw)

        self.assertEqual(decoded["finite"], [-0.0, 1.25, 6.02e23])
        self.assertIs(type(decoded["bool"]), bool)
        self.assertIs(type(decoded["integer"]), int)
        self.assertIs(type(decoded["finite"][1]), float)  # type: ignore[index]
        self.assertEqual(decoded["text"], "café 雪")

    def test_canonical_bytes_are_sorted_compact_utf8_and_type_exact(self) -> None:
        value = {
            "z": [False, 0, 1.0, -2.5],
            "é": "雪",
            "a": {"b": None},
        }

        self.assertEqual(
            matrix_v2_canonical_bytes(value),
            '{"a":{"b":null},"z":[false,0,1.0,-2.5],"é":"雪"}'.encode(
                "utf-8"
            ),
        )
        self.assertNotEqual(
            matrix_v2_canonical_bytes(False),
            matrix_v2_canonical_bytes(0),
        )
        self.assertNotEqual(
            matrix_v2_canonical_bytes(1.0),
            matrix_v2_canonical_bytes(1),
        )

    def test_rendering_is_exact_sorted_utf8_with_one_terminal_lf(self) -> None:
        document = {
            "z": [True, 1.5],
            "é": "雪",
            "a": {"b": 0},
        }

        rendered = render_matrix_v2(document)

        self.assertEqual(
            rendered,
            (
                "{\n"
                '  "a": {\n'
                '    "b": 0\n'
                "  },\n"
                '  "z": [\n'
                "    true,\n"
                "    1.5\n"
                "  ],\n"
                '  "é": "雪"\n'
                "}\n"
            ).encode("utf-8"),
        )
        self.assertTrue(rendered.endswith(b"}\n"))
        self.assertFalse(rendered.endswith(b"\n\n"))

    def test_decoder_rejects_duplicate_keys_invalid_utf8_and_nonfinite_numbers(
        self,
    ) -> None:
        rejected = (
            b'{"a":1,"a":2}',
            b'{"outer":{"a":1,"a":2}}',
            b'{"text":"\xff"}',
            b"{} null",
            b'{"value":NaN}',
            b'{"value":Infinity}',
            b'{"value":-Infinity}',
            b'{"value":1e400}',
        )

        for raw in rejected:
            with self.subTest(raw=raw):
                with self.assertRaises(PipelineError):
                    decode_matrix_v2(raw)

    def test_decoder_requires_bytes_and_an_exact_object_root(self) -> None:
        with self.assertRaises(PipelineError):
            decode_matrix_v2(bytearray(b"{}"))  # type: ignore[arg-type]
        for raw in (b"null", b"false", b"0", b"1.5", b'"text"', b"[]"):
            with self.subTest(raw=raw):
                with self.assertRaises(PipelineError):
                    decode_matrix_v2(raw)

    def test_in_memory_domain_rejects_nonfinite_and_custom_values(self) -> None:
        rejected = (
            float("nan"),
            float("inf"),
            float("-inf"),
            _BoolLikeInt(1),
            _FloatSubclass(1.0),
            _StringSubclass("text"),
            _ListSubclass([1]),
            _DictSubclass({"key": "value"}),
            b"bytes",
            ("tuple",),
            object(),
        )

        for value in rejected:
            with self.subTest(value=repr(value)):
                with self.assertRaises(PipelineError):
                    matrix_v2_canonical_bytes({"nested": [value]})
                with self.assertRaises(PipelineError):
                    render_matrix_v2({"nested": [value]})

    def test_in_memory_domain_requires_exact_utf8_string_keys(self) -> None:
        for key in (1, False, _StringSubclass("key")):
            with self.subTest(key=repr(key)):
                with self.assertRaises(PipelineError):
                    matrix_v2_canonical_bytes({key: "value"})
                with self.assertRaises(PipelineError):
                    render_matrix_v2({key: "value"})

    def test_lone_unicode_surrogates_are_rejected_in_keys_and_values(self) -> None:
        for value in ({"value": "\ud800"}, {"\udfff": "value"}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(PipelineError):
                    matrix_v2_canonical_bytes(value)
                with self.assertRaises(PipelineError):
                    render_matrix_v2(value)
        for raw in (b'{"value":"\\ud800"}', b'{"\\udfff":"value"}'):
            with self.subTest(raw=raw):
                with self.assertRaises(PipelineError):
                    decode_matrix_v2(raw)

    def test_cycles_are_rejected_and_shared_acyclic_values_are_accepted(self) -> None:
        self_list: list[object] = []
        self_list.append(self_list)
        self_dict: dict[str, object] = {}
        self_dict["self"] = self_dict
        left: list[object] = []
        right: dict[str, object] = {"left": left}
        left.append(right)

        for value in (
            {"cycle": self_list},
            self_dict,
            {"indirect": left},
        ):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(PipelineError):
                    matrix_v2_canonical_bytes(value)
                with self.assertRaises(PipelineError):
                    render_matrix_v2(value)
                with self.assertRaises(PipelineError):
                    matrix_v2_semantic_sha256(value)

        shared = {"leaf": [1, 1.5, "same"]}
        dag = {"left": shared, "right": shared}
        self.assertEqual(
            matrix_v2_canonical_bytes(dag),
            (
                b'{"left":{"leaf":[1,1.5,"same"]},'
                b'"right":{"leaf":[1,1.5,"same"]}}'
            ),
        )

    def test_excessive_nesting_is_normalized_to_pipeline_error(self) -> None:
        value: object = None
        for _ in range(2_000):
            value = [value]
        for encode in (matrix_v2_canonical_bytes,):
            with self.subTest(encode=encode.__name__):
                with self.assertRaises(PipelineError):
                    encode(value)
        with self.assertRaises(PipelineError):
            render_matrix_v2({"nested": value})
        with self.assertRaises(PipelineError):
            matrix_v2_semantic_sha256({"nested": value})

        raw = b'{"nested":' + (b"[" * 2_000) + b"null" + (b"]" * 2_000) + b"}"
        with self.assertRaises(PipelineError):
            decode_matrix_v2(raw)

    def test_semantic_hash_drops_only_outer_digest_without_mutation(self) -> None:
        document = {
            "content_sha256": "stale-outer-value",
            "finite": 1.25,
            "nested": {
                "content_sha256": "authenticated-nested-value",
                "unicode": "雪",
            },
        }
        snapshot = copy.deepcopy(document)
        expected_material = {
            "finite": 1.25,
            "nested": {
                "content_sha256": "authenticated-nested-value",
                "unicode": "雪",
            },
        }
        expected = hashlib.sha256(
            matrix_v2_canonical_bytes(expected_material)
        ).hexdigest()

        observed = matrix_v2_semantic_sha256(document)

        self.assertEqual(observed, expected)
        self.assertEqual(document, snapshot)
        changed_outer = copy.deepcopy(document)
        changed_outer["content_sha256"] = "different-outer-value"
        self.assertEqual(matrix_v2_semantic_sha256(changed_outer), expected)
        self.assertEqual(matrix_v2_semantic_sha256(expected_material), expected)
        changed_nested = copy.deepcopy(document)
        changed_nested["nested"]["content_sha256"] = "changed-nested-value"
        self.assertNotEqual(matrix_v2_semantic_sha256(changed_nested), expected)

    def test_semantic_hash_and_renderer_require_exact_object_roots(self) -> None:
        for value in (None, False, 0, 1.5, "text", []):
            with self.subTest(value=value):
                with self.assertRaises(PipelineError):
                    matrix_v2_semantic_sha256(value)
                with self.assertRaises(PipelineError):
                    render_matrix_v2(value)


if __name__ == "__main__":
    unittest.main()
