from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

from jsonschema import Draft202012Validator

from scripts.core_pipeline_lib import core_spec as core_spec_module
from scripts.core_pipeline_lib.campaign.json_wire import (
    canonical_json_sha256,
    decode_identity_object,
    rendered_json_bytes,
)
from scripts.core_pipeline_lib.campaign.model import EvidenceRef
from scripts.core_pipeline_lib.contracts.registry import CORE_LOG_CONTRACTS
from scripts.core_pipeline_lib.core_spec import (
    CATALOG_PATH,
    CATALOG_SCHEMA_CONTENT_SHA256,
    CATALOG_SCHEMA_DRAFT,
    CATALOG_SCHEMA_ID,
    CATALOG_SCHEMA_PATH,
    EXPECTED_DRIVER_COUNTS,
    LEGACY_VALIDATOR_CORE_IDS,
    CoreSpecIdentity,
    CoreSpecSetV1,
    ProofBinding,
    decode_core_spec_set,
    EXPECTED_REGISTERED_CONTRACT_COUNT,
    EXPECTED_CORE_COUNT,
    derive_core_spec_set,
    legacy_core_spec_sha256,
    render_core_spec_set,
    validate_core_spec_set,
)
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
CATALOG_RAW_SHA256 = (
    "d781451c35be44de0698ee3ca42a1209fa5f74da6b753c246d9b28d916d81692"
)
CATALOG_CONTENT_SHA256 = (
    "60f8bf70b2b4c88354560a2afe1a49e822f6c9949236812ff8fee6772583f269"
)
CATALOG_SCHEMA_RAW_SHA256 = (
    "4289b6f3a443907a766ce419515a33f34fd86074f9659cc1724ca978f8d04343"
)
CORE_SPEC_SET_CONTENT_SHA256 = (
    "a27133450f87409a4f0a475faffa7dbe3e0215c331ec4278776460428f682d5c"
)
CORE_SPEC_SET_PATH = "manifests/core-spec-sets/catalog-v1.json"
CORE_SPEC_SET_RAW_SHA256 = (
    "bae9d79053fc0a0e96b9f1a836c7725a5af8b5d0ea456cd942ec126b347bcdbf"
)


def _artifact_reference(path: str, raw: bytes) -> EvidenceRef:
    document = decode_identity_object(raw, label=f"{path} fixture")
    return EvidenceRef(
        kind="artifact",
        path=path,
        file_sha256=sha256_bytes(raw),
        target_content_sha256=canonical_json_sha256(document),
        size=len(raw),
    )


def _reseal(document: dict[str, object]) -> None:
    material = copy.deepcopy(document)
    material.pop("content_sha256", None)
    document["content_sha256"] = canonical_json_sha256(material)


class CoreSpecSetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog_raw = (ROOT / CATALOG_PATH).read_bytes()
        cls.catalog_schema_raw = (ROOT / CATALOG_SCHEMA_PATH).read_bytes()
        cls.catalog = decode_identity_object(
            cls.catalog_raw, label="production core catalog"
        )
        cls.catalog_schema = decode_identity_object(
            cls.catalog_schema_raw, label="production core catalog schema"
        )
        cls.catalog_ref = _artifact_reference(CATALOG_PATH, cls.catalog_raw)
        cls.catalog_schema_ref = _artifact_reference(
            CATALOG_SCHEMA_PATH, cls.catalog_schema_raw
        )

    def _derive(
        self,
        *,
        catalog_ref: EvidenceRef | None = None,
        catalog_raw: bytes | None = None,
        schema_ref: EvidenceRef | None = None,
        schema_raw: bytes | None = None,
    ) -> CoreSpecSetV1:
        return derive_core_spec_set(
            catalog_ref=self.catalog_ref if catalog_ref is None else catalog_ref,
            catalog_raw=self.catalog_raw if catalog_raw is None else catalog_raw,
            catalog_schema_ref=(
                self.catalog_schema_ref if schema_ref is None else schema_ref
            ),
            catalog_schema_raw=(
                self.catalog_schema_raw if schema_raw is None else schema_raw
            ),
        )

    def test_tracked_core_spec_set_is_exactly_the_production_derivation(
        self,
    ) -> None:
        raw = (ROOT / CORE_SPEC_SET_PATH).read_bytes()
        self.assertEqual(sha256_bytes(raw), CORE_SPEC_SET_RAW_SHA256)
        self.assertEqual(len(raw), 60_705)
        self.assertEqual(raw.count(b"\n"), 1_434)
        value = decode_core_spec_set(raw)
        self.assertEqual(value.content_sha256, CORE_SPEC_SET_CONTENT_SHA256)
        self.assertEqual(value, self._derive())
        validate_core_spec_set(
            value,
            catalog_ref=self.catalog_ref,
            catalog_raw=self.catalog_raw,
            catalog_schema_ref=self.catalog_schema_ref,
            catalog_schema_raw=self.catalog_schema_raw,
        )

    def _bound_catalog(
        self, document: dict[str, object]
    ) -> tuple[EvidenceRef, bytes]:
        raw = rendered_json_bytes(document)
        return _artifact_reference(CATALOG_PATH, raw), raw

    def _bound_schema(
        self, document: dict[str, object]
    ) -> tuple[EvidenceRef, bytes]:
        raw = rendered_json_bytes(document)
        return _artifact_reference(CATALOG_SCHEMA_PATH, raw), raw

    def test_production_inputs_and_aggregate_have_frozen_identities(self) -> None:
        self.assertEqual(CATALOG_RAW_SHA256, sha256_bytes(self.catalog_raw))
        self.assertEqual(127584, len(self.catalog_raw))
        self.assertEqual(3616, len(self.catalog_raw.splitlines()))
        self.assertEqual(
            CATALOG_CONTENT_SHA256, canonical_json_sha256(self.catalog)
        )
        self.assertEqual(
            CATALOG_SCHEMA_RAW_SHA256, sha256_bytes(self.catalog_schema_raw)
        )
        self.assertEqual(28681, len(self.catalog_schema_raw))
        self.assertEqual(1133, len(self.catalog_schema_raw.splitlines()))
        self.assertEqual(
            CATALOG_SCHEMA_CONTENT_SHA256,
            canonical_json_sha256(self.catalog_schema),
        )

        result = self._derive()
        self.assertEqual(CORE_SPEC_SET_CONTENT_SHA256, result.content_sha256)
        self.assertEqual(EXPECTED_CORE_COUNT, result.core_count)
        self.assertEqual(dict(EXPECTED_DRIVER_COUNTS), result.driver_counts)
        self.assertEqual(
            tuple(sorted(self.catalog["cores"])),
            tuple(identity.core_id for identity in result.cores),
        )
        self.assertEqual(
            98, len({identity.content_sha256 for identity in result.cores})
        )
        self.assertEqual(
            98,
            len({identity.legacy_catalog_spec_sha256 for identity in result.cores}),
        )
        self.assertEqual(
            98, len({identity.strict_spec_sha256 for identity in result.cores})
        )

    def test_proof_bindings_close_the_registered_and_legacy_cores(
        self,
    ) -> None:
        result = self._derive()
        contracts = {
            next(iter(contract.core_ids)): contract
            for contract in CORE_LOG_CONTRACTS
        }
        self.assertEqual(89, len(contracts))
        self.assertEqual(
            set(LEGACY_VALIDATOR_CORE_IDS), set(self.catalog["cores"]) - set(contracts)
        )

        registered_count = 0
        legacy_count = 0
        for identity in result.cores:
            binding = identity.proof_binding
            if identity.core_id in LEGACY_VALIDATOR_CORE_IDS:
                legacy_count += 1
                self.assertEqual("legacy-validator", binding.binding_kind)
                self.assertEqual(identity.core_id, binding.binding_id)
                self.assertEqual("legacy-validator", binding.proof_kind)
            else:
                registered_count += 1
                contract = contracts[identity.core_id]
                self.assertEqual("registered-log-contract", binding.binding_kind)
                self.assertEqual(contract.contract_id, binding.binding_id)
                self.assertEqual(contract.proof_kind, binding.proof_kind)
        self.assertEqual(
            (EXPECTED_REGISTERED_CONTRACT_COUNT, len(LEGACY_VALIDATOR_CORE_IDS)),
            (registered_count, legacy_count),
        )

        with mock.patch.object(
            core_spec_module,
            "CORE_LOG_CONTRACTS",
            CORE_LOG_CONTRACTS[:-1],
        ):
            with self.assertRaises(PipelineError):
                self._derive()

    def test_legacy_and_strict_spec_digest_algorithms_are_independent(self) -> None:
        result = self._derive()
        identities = {identity.core_id: identity for identity in result.cores}
        for core_id, spec in self.catalog["cores"].items():
            independent_legacy = hashlib.sha256(
                json.dumps(
                    spec,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            self.assertEqual(
                independent_legacy,
                identities[core_id].legacy_catalog_spec_sha256,
            )
            self.assertEqual(
                canonical_json_sha256(spec), identities[core_id].strict_spec_sha256
            )

        unicode_spec = {"name": "Pokémon – 日本語", "nested": {"enabled": True}}
        self.assertNotEqual(
            legacy_core_spec_sha256(unicode_spec),
            canonical_json_sha256(unicode_spec),
        )
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    unicode_spec,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
            ).hexdigest(),
            legacy_core_spec_sha256(unicode_spec),
        )

    def test_digest_domain_rejects_floats_cycles_and_non_objects(self) -> None:
        for value in ({"value": 1.0}, {"value": float("nan")}, ["not-object"]):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(PipelineError):
                    legacy_core_spec_sha256(value)
        cyclic: dict[str, object] = {}
        cyclic["self"] = cyclic
        with self.assertRaises(PipelineError):
            legacy_core_spec_sha256(cyclic)

    def test_render_decode_validate_are_deterministic_and_detached(self) -> None:
        first = self._derive()
        second = self._derive()
        self.assertEqual(first, second)
        first_raw = render_core_spec_set(first)
        self.assertEqual(first_raw, render_core_spec_set(first))
        self.assertEqual(first, decode_core_spec_set(first_raw))
        validate_core_spec_set(
            first,
            catalog_ref=self.catalog_ref,
            catalog_raw=self.catalog_raw,
            catalog_schema_ref=self.catalog_schema_ref,
            catalog_schema_raw=self.catalog_schema_raw,
        )

        detached = first.to_document()
        detached["driver_counts"]["libretro-super"] = 0
        detached["cores"][0]["core_id"] = "changed"
        self.assertEqual(85, first.driver_counts["libretro-super"])
        self.assertNotEqual("changed", first.cores[0].core_id)
        with self.assertRaises(FrozenInstanceError):
            first.cores[0].driver = "direct-make"  # type: ignore[misc]

    def test_tracked_output_schema_is_closed_and_accepts_the_production_set(
        self,
    ) -> None:
        schema = json.loads(
            (ROOT / "manifests/core-spec-set-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(CATALOG_SCHEMA_DRAFT, schema["$schema"])
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        document = self._derive().to_document()
        self.assertEqual([], list(validator.iter_errors(document)))

        adversaries = []
        extra = copy.deepcopy(document)
        extra["unexpected"] = None
        adversaries.append(extra)
        wrong_count = copy.deepcopy(document)
        wrong_count["core_count"] = 97
        adversaries.append(wrong_count)
        numeric_alias = copy.deepcopy(document)
        numeric_alias["driver_counts"]["direct-cargo"] = True
        adversaries.append(numeric_alias)
        wrong_path = copy.deepcopy(document)
        wrong_path["catalog"]["path"] = "manifests/elsewhere.json"
        adversaries.append(wrong_path)
        wrong_legacy_binding = copy.deepcopy(document)
        legacy = next(
            item
            for item in wrong_legacy_binding["cores"]
            if item["core_id"] in LEGACY_VALIDATOR_CORE_IDS
        )
        legacy["proof_binding"]["binding_id"] = "not-an-exception"
        adversaries.append(wrong_legacy_binding)
        for adversary in adversaries:
            with self.subTest(keys=tuple(adversary)):
                self.assertNotEqual([], list(validator.iter_errors(adversary)))

    def test_references_bind_kind_path_raw_size_and_semantic_identity(self) -> None:
        mutations = (
            replace(self.catalog_ref, kind="check-log"),
            replace(self.catalog_ref, path="manifests/other.json"),
            replace(self.catalog_ref, file_sha256="0" * 64),
            replace(self.catalog_ref, target_content_sha256="1" * 64),
            replace(self.catalog_ref, size=self.catalog_ref.size + 1),
        )
        for reference in mutations:
            with self.subTest(reference=reference):
                with self.assertRaises(PipelineError):
                    self._derive(catalog_ref=reference)

        schema_mutations = (
            replace(self.catalog_schema_ref, kind="check-log"),
            replace(self.catalog_schema_ref, path="manifests/other.schema.json"),
            replace(self.catalog_schema_ref, file_sha256="2" * 64),
            replace(self.catalog_schema_ref, target_content_sha256="3" * 64),
            replace(self.catalog_schema_ref, size=self.catalog_schema_ref.size + 1),
        )
        for reference in schema_mutations:
            with self.subTest(reference=reference):
                with self.assertRaises(PipelineError):
                    self._derive(schema_ref=reference)

        with self.assertRaises(PipelineError):
            self._derive(catalog_raw=self.catalog_raw + b" ")
        with self.assertRaises(PipelineError):
            self._derive(schema_raw=self.catalog_schema_raw + b" ")

    def test_equivalent_layouts_preserve_semantics_but_remain_raw_bound(self) -> None:
        compact_catalog = json.dumps(
            self.catalog,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        compact_ref = _artifact_reference(CATALOG_PATH, compact_catalog)
        compact_result = self._derive(
            catalog_ref=compact_ref, catalog_raw=compact_catalog
        )
        original_result = self._derive()
        self.assertEqual(original_result.cores, compact_result.cores)
        self.assertEqual(
            original_result.catalog.target_content_sha256,
            compact_result.catalog.target_content_sha256,
        )
        self.assertNotEqual(
            original_result.catalog.file_sha256, compact_result.catalog.file_sha256
        )
        self.assertNotEqual(
            original_result.content_sha256, compact_result.content_sha256
        )

    def test_catalog_intrinsic_shape_and_partition_tampering_fail_closed(self) -> None:
        cases: list[dict[str, object]] = []
        extra_root = copy.deepcopy(self.catalog)
        extra_root["unexpected"] = None
        cases.append(extra_root)
        wrong_route = copy.deepcopy(self.catalog)
        wrong_route["$schema"] = "./other.schema.json"
        cases.append(wrong_route)
        numeric_alias = copy.deepcopy(self.catalog)
        numeric_alias["schema_version"] = True
        cases.append(numeric_alias)
        publication = copy.deepcopy(self.catalog)
        publication["policy"]["publication"] = "enabled"
        cases.append(publication)
        missing = copy.deepcopy(self.catalog)
        missing["cores"].pop("2048")
        cases.append(missing)
        renamed = copy.deepcopy(self.catalog)
        renamed["cores"]["unregistered_core"] = renamed["cores"].pop("2048")
        cases.append(renamed)
        wrong_driver = copy.deepcopy(self.catalog)
        wrong_driver["cores"]["2048"]["build"]["driver"] = "direct-make"
        cases.append(wrong_driver)
        missing_build = copy.deepcopy(self.catalog)
        missing_build["cores"]["2048"].pop("build")
        cases.append(missing_build)

        for document in cases:
            reference, raw = self._bound_catalog(document)
            with self.subTest(case=len(raw)):
                with self.assertRaises(PipelineError):
                    self._derive(catalog_ref=reference, catalog_raw=raw)

    def test_catalog_strict_decoder_rejects_duplicates_and_float_aliases(self) -> None:
        for raw in (
            b'{"schema_version":2,"schema_version":2}',
            b'{"schema_version":2.0}',
            b'{"value":NaN}',
            b'not-json',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(PipelineError):
                    self._derive(catalog_raw=raw)

    def test_catalog_content_change_requires_rebinding_and_changes_one_identity(
        self,
    ) -> None:
        changed = copy.deepcopy(self.catalog)
        changed["cores"]["2048"]["metadata"]["artifact_name"] = (
            "2048_variant_libretro.so"
        )
        reference, raw = self._bound_catalog(changed)
        with self.assertRaises(PipelineError):
            self._derive(catalog_raw=raw)

        before = {item.core_id: item for item in self._derive().cores}
        after = {
            item.core_id: item
            for item in self._derive(catalog_ref=reference, catalog_raw=raw).cores
        }
        changed_ids = {
            core_id for core_id in before if before[core_id] != after[core_id]
        }
        self.assertEqual({"2048"}, changed_ids)
        self.assertNotEqual(
            before["2048"].legacy_catalog_spec_sha256,
            after["2048"].legacy_catalog_spec_sha256,
        )
        self.assertNotEqual(
            before["2048"].strict_spec_sha256,
            after["2048"].strict_spec_sha256,
        )

    def test_catalog_schema_is_exact_valid_local_draft_2020_12(self) -> None:
        permissive = {
            "$schema": CATALOG_SCHEMA_DRAFT,
            "$id": CATALOG_SCHEMA_ID,
            "type": "object",
        }
        permissive_ref, permissive_raw = self._bound_schema(permissive)
        with self.assertRaises(PipelineError):
            self._derive(schema_ref=permissive_ref, schema_raw=permissive_raw)

        altered_schemas = []
        wrong_draft = copy.deepcopy(self.catalog_schema)
        wrong_draft["$schema"] = "https://json-schema.org/draft/2019-09/schema"
        altered_schemas.append(wrong_draft)
        wrong_id = copy.deepcopy(self.catalog_schema)
        wrong_id["$id"] = "https://spruceui.local/schemas/other.json"
        altered_schemas.append(wrong_id)
        remote_ref = copy.deepcopy(self.catalog_schema)
        remote_ref["properties"]["cores"]["additionalProperties"] = {
            "$ref": "https://example.invalid/remote.json"
        }
        altered_schemas.append(remote_ref)
        malformed = copy.deepcopy(self.catalog_schema)
        malformed["type"] = 7
        altered_schemas.append(malformed)

        for schema in altered_schemas:
            reference, raw = self._bound_schema(schema)
            with self.subTest(schema_id=schema.get("$id")):
                with mock.patch.object(
                    core_spec_module,
                    "CATALOG_SCHEMA_CONTENT_SHA256",
                    canonical_json_sha256(schema),
                ):
                    with self.assertRaises(PipelineError):
                        self._derive(schema_ref=reference, schema_raw=raw)

    def test_wire_model_rejects_reordering_numeric_alias_and_proof_tamper(self) -> None:
        document = self._derive().to_document()
        adversaries: list[dict[str, object]] = []

        reordered = copy.deepcopy(document)
        reordered["cores"] = list(reversed(reordered["cores"]))
        _reseal(reordered)
        adversaries.append(reordered)

        numeric_alias = copy.deepcopy(document)
        numeric_alias["core_count"] = 98.0
        adversaries.append(numeric_alias)

        boolean_alias = copy.deepcopy(document)
        boolean_alias["driver_counts"]["direct-cargo"] = True
        _reseal(boolean_alias)
        adversaries.append(boolean_alias)

        proof_tamper = copy.deepcopy(document)
        registered = next(
            item
            for item in proof_tamper["cores"]
            if item["core_id"] not in LEGACY_VALIDATOR_CORE_IDS
        )
        registered["proof_binding"]["binding_id"] = "wrong-contract-v1"
        _reseal(registered)
        _reseal(proof_tamper)
        adversaries.append(proof_tamper)

        extra = copy.deepcopy(document)
        extra["unexpected"] = None
        _reseal(extra)
        adversaries.append(extra)

        for adversary in adversaries:
            with self.subTest(core_count=adversary.get("core_count")):
                with self.assertRaises(PipelineError):
                    CoreSpecSetV1.from_document(adversary)

    def test_every_nested_and_outer_content_digest_is_authenticated(self) -> None:
        document = self._derive().to_document()
        tampered_entry = copy.deepcopy(document)
        tampered_entry["cores"][0]["strict_spec_sha256"] = "0" * 64
        _reseal(tampered_entry)
        with self.assertRaises(PipelineError):
            CoreSpecSetV1.from_document(tampered_entry)

        tampered_ref = copy.deepcopy(document)
        tampered_ref["catalog"]["file_sha256"] = "0" * 64
        _reseal(tampered_ref)
        with self.assertRaises(PipelineError):
            CoreSpecSetV1.from_document(tampered_ref)

        tampered_outer = copy.deepcopy(document)
        tampered_outer["content_sha256"] = "0" * 64
        with self.assertRaises(PipelineError):
            CoreSpecSetV1.from_document(tampered_outer)

    def test_independent_validation_rejects_a_well_formed_wrong_identity(self) -> None:
        expected = self._derive()
        first = expected.cores[0]
        changed = replace(first, strict_spec_sha256="0" * 64)
        candidate = replace(expected, cores=(changed, *expected.cores[1:]))
        with self.assertRaises(PipelineError):
            validate_core_spec_set(
                candidate,
                catalog_ref=self.catalog_ref,
                catalog_raw=self.catalog_raw,
                catalog_schema_ref=self.catalog_schema_ref,
                catalog_schema_raw=self.catalog_schema_raw,
            )

    def test_model_constructors_require_exact_types_and_policy_values(self) -> None:
        with self.assertRaises(PipelineError):
            ProofBinding(
                binding_kind="legacy-validator",
                binding_id="2048",
                proof_kind="legacy-validator",
            )
        with self.assertRaises(PipelineError):
            ProofBinding(
                binding_kind="registered-log-contract",
                binding_id="contract-v1",
                proof_kind="legacy-validator",
            )
        with self.assertRaises(PipelineError):
            CoreSpecIdentity(
                core_id="ardens",
                driver="libretro-super",
                legacy_catalog_spec_sha256="0" * 64,
                strict_spec_sha256="1" * 64,
                proof_binding=ProofBinding(
                    binding_kind="legacy-validator",
                    binding_id="tic80",
                    proof_kind="legacy-validator",
                ),
            )
        with self.assertRaises(PipelineError):
            CoreSpecIdentity(
                core_id="2048",
                driver=True,  # type: ignore[arg-type]
                legacy_catalog_spec_sha256="0" * 64,
                strict_spec_sha256="1" * 64,
                proof_binding=self._derive().cores[0].proof_binding,
            )
        with self.assertRaises(PipelineError):
            render_core_spec_set(object())  # type: ignore[arg-type]
        with self.assertRaises(PipelineError):
            validate_core_spec_set(
                object(),  # type: ignore[arg-type]
                catalog_ref=self.catalog_ref,
                catalog_raw=self.catalog_raw,
                catalog_schema_ref=self.catalog_schema_ref,
                catalog_schema_raw=self.catalog_schema_raw,
            )


if __name__ == "__main__":
    unittest.main()
