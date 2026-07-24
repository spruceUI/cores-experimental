#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "profile_registry.py"
SPEC = importlib.util.spec_from_file_location("profile_registry", MODULE_PATH)
assert SPEC and SPEC.loader
registry = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registry)

SOURCE_SET_RELATIVE = (
    "pins/source-sets/freechaf-76c7a84f1f7e-0fced3806666.json"
)
SOURCE_SET_PATH = ROOT / SOURCE_SET_RELATIVE
EXECUTION_PATH = ROOT / "manifests" / "execution-profiles.json"
RUNTIME_PATH = ROOT / "manifests" / "device-runtime-contracts.json"
CATALOG_CORE_COUNT = len(
    json.loads((ROOT / "manifests" / "core-builds.json").read_text(encoding="utf-8"))[
        "cores"
    ]
)

def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_digest(document: dict) -> None:
    document["content_sha256"] = registry.canonical_content_sha256(document)


class ProfileRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_set = load(SOURCE_SET_PATH)
        self.execution = load(EXECUTION_PATH)
        self.runtime = load(RUNTIME_PATH)

    def test_new_schemas_are_valid_json_and_patterns_are_string_typed(self) -> None:
        schema_names = {
            "core-source-lock.schema.json": "https://spruceui.local/schemas/core-source-lock.schema.json",
            "core-source-set.schema.json": "https://spruceui.local/schemas/core-source-set.schema.json",
            "execution-profiles.schema.json": "https://spruceui.local/schemas/execution-profiles.schema.json",
            "device-runtime-contracts.schema.json": "https://spruceui.local/schemas/device-runtime-contracts.schema.json",
        }

        def inspect(value: object, path: str) -> None:
            if isinstance(value, dict):
                if "pattern" in value:
                    self.assertEqual("string", value.get("type"), path)
                for key, child in value.items():
                    inspect(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    inspect(child, f"{path}[{index}]")

        for name, schema_id in schema_names.items():
            schema = load(ROOT / "manifests" / name)
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
            self.assertEqual(schema_id, schema["$id"])
            inspect(schema, name)

    def test_source_schema_patterns_reject_the_same_unsafe_values_as_validator(self) -> None:
        schema = load(ROOT / "manifests" / "core-source-lock.schema.json")
        source_properties = schema["$defs"]["source"]["properties"]
        url_pattern = re.compile(source_properties["url"]["pattern"])
        ref_pattern = re.compile(source_properties["requested_ref"]["pattern"])
        path_pattern = re.compile(
            schema["$defs"]["submodule"]["properties"]["path"]["pattern"]
        )
        for value in (
            "https://repository.git",
            "https://user@github.com/libretro/FreeChaF.git",
            "https://github.com/libretro/FreeChaF.git?ref=main",
            "https://github.com/libretro/FreeChaF.git#fragment",
        ):
            self.assertIsNone(url_pattern.fullmatch(value), value)
        for value in ("refs/heads/", "refs/heads/has space"):
            self.assertIsNone(ref_pattern.fullmatch(value), value)
        for value in ("bad path/libretro-common", "src/./libretro-common", "src/../libretro-common"):
            self.assertIsNone(path_pattern.fullmatch(value), value)
        self.assertIsNotNone(
            url_pattern.fullmatch("https://github.com/libretro/FreeChaF.git")
        )
        self.assertIsNotNone(ref_pattern.fullmatch("refs/heads/master"))
        self.assertIsNotNone(
            path_pattern.fullmatch("src/deps/libretro-common")
        )

    def test_source_locks_exclude_recipe_inputs_and_catalog_epochs_stay_exact(self) -> None:
        for reference in self.source_set["sources"].values():
            document = load(ROOT / reference["path"])
            self.assertNotIn("source_date_epoch", json.dumps(document))
            self.assertNotIn("build", document)
        catalog = load(ROOT / "manifests" / "core-builds.json")
        expected_epochs = {
            "ffmpeg": 1598579820,
            "pcsx_rearmed": 1782602899,
            "swanstation": 1782767217,
        }
        for core_id, epoch in expected_epochs.items():
            self.assertEqual(
                epoch,
                catalog["cores"][core_id]["build"]["source_date_epoch"],
            )

    def test_source_lock_tampering_fails_closed(self) -> None:
        base = load(ROOT / self.source_set["sources"]["freechaf"]["path"])
        mutations = []
        changed_url = copy.deepcopy(base)
        changed_url["source"]["url"] = "https://example.com/freechaf.git"
        mutations.append(changed_url)
        changed_commit = copy.deepcopy(base)
        changed_commit["source"]["commit"] = "a" * 40
        mutations.append(changed_commit)
        changed_tree = copy.deepcopy(base)
        changed_tree["source"]["tree"] = "b" * 40
        mutations.append(changed_tree)
        changed_submodule_path = copy.deepcopy(base)
        changed_submodule_path["source"]["submodules"][0]["path"] = "other/path"
        mutations.append(changed_submodule_path)
        changed_submodule_commit = copy.deepcopy(base)
        changed_submodule_commit["source"]["submodules"][0]["commit"] = "c" * 40
        mutations.append(changed_submodule_commit)
        missing_submodules = copy.deepcopy(base)
        del missing_submodules["source"]["submodules"]
        mutations.append(missing_submodules)
        extra = copy.deepcopy(base)
        extra["unexpected"] = True
        mutations.append(extra)
        wrong_digest = copy.deepcopy(base)
        wrong_digest["content_sha256"] = "0" * 64
        mutations.append(wrong_digest)
        for document in mutations:
            with self.subTest(document=document):
                with self.assertRaises(registry.RegistryError):
                    registry.validate_source_lock(document)

    def test_source_lock_rejects_unsafe_urls_empty_refs_and_paths_after_rehash(self) -> None:
        base = load(ROOT / self.source_set["sources"]["freechaf"]["path"])
        mutations = []
        for url in (
            "https://user@github.com/libretro/FreeChaF.git",
            "https://github.com/libretro/FreeChaF.git?ref=main",
            "https://github.com/libretro/FreeChaF.git?",
            "https://github.com/libretro/FreeChaF.git#fragment",
            "https://github.com/libretro/FreeChaF.git#",
            "https://repository.git",
        ):
            changed = copy.deepcopy(base)
            changed["source"]["url"] = url
            mutations.append(changed)
        for requested_ref in ("refs/heads/", "refs/heads/has space"):
            changed = copy.deepcopy(base)
            changed["source"]["requested_ref"] = requested_ref
            mutations.append(changed)
        changed_path = copy.deepcopy(base)
        changed_path["source"]["submodules"][0]["path"] = (
            "bad path/libretro-common"
        )
        mutations.append(changed_path)
        changed_dot_path = copy.deepcopy(base)
        changed_dot_path["source"]["submodules"][0]["path"] = (
            "src/./libretro-common"
        )
        mutations.append(changed_dot_path)
        for document in mutations:
            refresh_digest(document)
            with self.subTest(document=document):
                with self.assertRaises(registry.RegistryError):
                    registry.validate_source_lock(document)

    def test_source_set_rejects_file_and_content_digest_tampering(self) -> None:
        for field in ("file_sha256", "content_sha256"):
            changed = copy.deepcopy(self.source_set)
            changed["sources"]["freechaf"][field] = "0" * 64
            refresh_digest(changed)
            with self.subTest(field=field):
                with self.assertRaises(registry.RegistryError):
                    registry.validate_source_set(changed)

    def test_explicit_empty_source_set_is_rejected(self) -> None:
        with self.assertRaises(registry.RegistryError):
            registry.verify_catalog_source_mirror(source_set={})

    def _copy_mirror_inputs(self, destination: Path) -> None:
        relative_paths = [
            Path("manifests/core-builds.json"),
            Path(SOURCE_SET_RELATIVE),
            Path(self.source_set["evidence_pin"]["path"]),
        ] + [Path(reference["path"]) for reference in self.source_set["sources"].values()]
        for relative in relative_paths:
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

    def _noncanonical_multi_core_source_set(self):
        source_set = copy.deepcopy(self.source_set)
        second_source_set = load(
            ROOT / "pins/source-sets/handy-bc55d462f0b2-6923119e1743.json"
        )
        source_set["source_set_id"] = "noncanonical-multi-core"
        source_set["sources"].update(second_source_set["sources"])
        refresh_digest(source_set)
        temporary = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            prefix="noncanonical-multi-core-",
            suffix=".json",
            dir=ROOT / "pins/source-sets",
        )
        json.dump(source_set, temporary)
        temporary.flush()
        return temporary

    def test_source_mirror_allows_future_catalog_superset_but_rejects_locked_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._copy_mirror_inputs(repo)
            catalog_path = repo / "manifests" / "core-builds.json"
            catalog = load(catalog_path)
            baseline_catalog_cores = len(catalog["cores"])
            locked_cores = len(self.source_set["sources"])
            catalog["cores"]["future_core"] = copy.deepcopy(
                catalog["cores"]["freechaf"]
            )
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            result = registry.verify_catalog_source_mirror(
                source_set=self.source_set,
                repo_root=repo,
            )
            self.assertEqual(locked_cores, result["locked_cores"])
            self.assertEqual(baseline_catalog_cores + 1, result["catalog_cores"])
            self.assertEqual(
                baseline_catalog_cores + 1 - locked_cores,
                result["catalog_unlocked_cores"],
            )
            url_drift = copy.deepcopy(catalog)
            url_drift["cores"]["freechaf"]["source"]["url"] = (
                "https://example.com/freechaf.git"
            )
            catalog_path.write_text(json.dumps(url_drift), encoding="utf-8")
            with self.assertRaises(registry.RegistryError):
                registry.verify_catalog_source_mirror(
                    source_set=self.source_set,
                    repo_root=repo,
                )
            tree_drift = copy.deepcopy(catalog)
            tree_drift["cores"]["freechaf"]["source"]["tree"] = "a" * 40
            catalog_path.write_text(json.dumps(tree_drift), encoding="utf-8")
            with self.assertRaises(registry.RegistryError):
                registry.verify_catalog_source_mirror(
                    source_set=self.source_set,
                    repo_root=repo,
                )

    def test_source_set_accepts_generic_pin_path_but_requires_local_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._copy_mirror_inputs(repo)
            source_set = load(repo / SOURCE_SET_RELATIVE)
            original_pin = repo / source_set["evidence_pin"]["path"]
            successor_pin = repo / "pins/core-sets/successor-evidence.json"
            shutil.copy2(original_pin, successor_pin)
            source_set["evidence_pin"]["path"] = (
                "pins/core-sets/successor-evidence.json"
            )
            source_set["evidence_pin"]["file_sha256"] = registry.sha256_file(
                successor_pin
            )
            refresh_digest(source_set)
            registry.validate_source_set(source_set, repo_root=repo)

            nonlocal_pin = load(successor_pin)
            nonlocal_pin["local_only"] = False
            nonlocal_pin["content_sha256"] = registry._pin_set_content_sha256(
                nonlocal_pin
            )
            successor_pin.write_text(json.dumps(nonlocal_pin), encoding="utf-8")
            source_set["evidence_pin"]["file_sha256"] = registry.sha256_file(
                successor_pin
            )
            source_set["evidence_pin"]["content_sha256"] = nonlocal_pin[
                "content_sha256"
            ]
            refresh_digest(source_set)
            with self.assertRaises(registry.RegistryError):
                registry.validate_source_set(source_set, repo_root=repo)

            published_pin = load(original_pin)
            published_pin["publication"] = "enabled"
            published_pin["content_sha256"] = registry._pin_set_content_sha256(
                published_pin
            )
            successor_pin.write_text(json.dumps(published_pin), encoding="utf-8")
            source_set["evidence_pin"]["file_sha256"] = registry.sha256_file(
                successor_pin
            )
            source_set["evidence_pin"]["content_sha256"] = published_pin[
                "content_sha256"
            ]
            refresh_digest(source_set)
            with self.assertRaises(registry.RegistryError):
                registry.validate_source_set(source_set, repo_root=repo)

    def test_source_set_rejects_evidence_pin_artifact_tamper_with_rehashed_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            self._copy_mirror_inputs(repo)
            source_set_path = repo / SOURCE_SET_RELATIVE
            source_set = load(source_set_path)
            pin_path = repo / source_set["evidence_pin"]["path"]
            pin = load(pin_path)
            pin["cores"]["freechaf"]["selection"]["targets"]["arm64"][
                "artifact"
            ]["sha256"] = "0" * 64
            pin_path.write_text(json.dumps(pin), encoding="utf-8")
            source_set["evidence_pin"]["file_sha256"] = registry.sha256_file(pin_path)
            refresh_digest(source_set)
            source_set_path.write_text(json.dumps(source_set), encoding="utf-8")
            with self.assertRaises(registry.RegistryError):
                registry.validate_source_set(source_set, repo_root=repo)

    def test_execution_profiles_bind_exact_frontends_and_only_two_build_identities(self) -> None:
        registry.validate_execution_profiles(self.execution)
        expected = {
            "ra32-a30-v1": ("armhf", "RetroArch/ra32.a30", "91c1e475371d1035bfec94c1f39f5df8132203e9feec38764f5a34ccd29eae37", "locked-build-identity"),
            "ra32-mini-v0": ("armhf", "RetroArch/ra32.mini", "f7350c5755277b4aca957ce08055c71685bd59cf5967cfbb72899e932d8fae4d", "provisional"),
            "ra32-universal-v0": ("armhf", "RetroArch/ra32.universal", "1fdf00d848e61a0703fa51ccc968d207e712017b9af28be7c2a07cb8577c7586", "provisional"),
            "ra64-pixel2-v0": ("arm64", "RetroArch/ra64.pixel2", None, "provisional-missing-frontend"),
            "ra64-universal-v1": ("arm64", "RetroArch/ra64.universal", "b94fd5ea8bdc5a969d2639e7365088b246fa8241d00428c86be00a6d807c4c11", "locked-build-identity"),
        }
        self.assertEqual(set(expected), set(self.execution["profiles"]))
        for profile_id, (architecture, path, digest, status) in expected.items():
            profile = self.execution["profiles"][profile_id]
            self.assertEqual((architecture, status), (profile["architecture"], profile["status"]))
            self.assertEqual((path, digest), (profile["frontend"]["spruce_path"], profile["frontend"]["sha256"]))
            if status == "locked-build-identity":
                self.assertIsNotNone(profile["build_identity"])
                self.assertEqual([], profile["missing_evidence"])
                self.assertEqual(
                    "unverified-local-cache",
                    profile["build_identity"]["dockerfile_linkage"],
                )
            else:
                self.assertIsNone(profile["build_identity"])
                self.assertTrue(profile["missing_evidence"])

    def test_provisional_profiles_require_explicit_missing_evidence(self) -> None:
        mutations = []
        empty = copy.deepcopy(self.execution)
        empty["profiles"]["ra32-mini-v0"]["missing_evidence"] = []
        mutations.append(empty)
        incomplete = copy.deepcopy(self.execution)
        incomplete["profiles"]["ra32-mini-v0"]["missing_evidence"].remove(
            "target-toolchain-lock"
        )
        mutations.append(incomplete)
        contradictory = copy.deepcopy(self.execution)
        contradictory["profiles"]["ra32-mini-v0"]["missing_evidence"].append(
            "frontend-binary"
        )
        mutations.append(contradictory)
        for changed in mutations:
            refresh_digest(changed)
            with self.subTest(changed=changed):
                with self.assertRaises(registry.RegistryError):
                    registry.validate_execution_profiles(changed)

    def test_execution_profile_snapshot_frontend_and_compiler_tampering_fail(self) -> None:
        mutations = []
        changed_snapshot = copy.deepcopy(self.execution)
        changed_snapshot["spruce_snapshot"]["commit"] = "a" * 40
        mutations.append(changed_snapshot)
        changed_frontend = copy.deepcopy(self.execution)
        changed_frontend["profiles"]["ra32-mini-v0"]["frontend"]["sha256"] = "b" * 64
        mutations.append(changed_frontend)
        changed_compiler = copy.deepcopy(self.execution)
        changed_compiler["profiles"]["ra32-a30-v1"]["build_identity"]["compiler"] = "different compiler"
        mutations.append(changed_compiler)
        changed_linkage = copy.deepcopy(self.execution)
        changed_linkage["profiles"]["ra32-a30-v1"]["build_identity"][
            "dockerfile_linkage"
        ] = "verified"
        mutations.append(changed_linkage)
        for changed in mutations:
            refresh_digest(changed)
            with self.subTest(changed=changed):
                with self.assertRaises(registry.RegistryError):
                    registry.validate_execution_profiles(changed)

    def test_execution_profiles_recompute_toolchain_lock_semantic_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            lock_relative = Path("pins/toolchains/local-cache-v1.json")
            lock_path = repo / lock_relative
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / lock_relative, lock_path)
            lock = load(lock_path)
            changed_image = "sha256:" + "a" * 64
            lock["toolchains"]["armhf"]["image"]["id"] = changed_image
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            changed = copy.deepcopy(self.execution)
            file_digest = registry.sha256_file(lock_path)
            for profile_id in ("ra32-a30-v1", "ra64-universal-v1"):
                changed["profiles"][profile_id]["build_identity"]["toolchain_lock_file_sha256"] = file_digest
            changed["profiles"]["ra32-a30-v1"]["build_identity"]["image_id"] = changed_image
            refresh_digest(changed)
            with self.assertRaises(registry.RegistryError):
                registry.validate_execution_profiles(changed, repo_root=repo)

    def test_device_groups_are_exact_unique_and_nonofficial_are_not_defaults(self) -> None:
        registry.validate_runtime_contracts(self.runtime, execution_profiles=self.execution)
        expected = {
            "device-miyoo-a30-v0": {"MIYOO_A30"},
            "device-miyoo-mini-family-v0": {"MIYOO_MINI", "MIYOO_MINI_V4", "MIYOO_MINI_PLUS", "MIYOO_MINI_FLIP"},
            "device-trimui-a133p-family-v0": {"TRIMUI_SMART_PRO", "TRIMUI_BRICK", "TRIMUI_BRICK_PRO"},
            "device-trimui-smart-pro-s-v0": {"TRIMUI_SMART_PRO_S"},
            "device-miyoo-flip-v0": {"MIYOO_FLIP"},
            "device-gkd-pixel2-v0": {"GKD_PIXEL2"},
            "device-anbernic-h700-family-v0": {"ANBERNIC_RG28XX", "ANBERNIC_RG34XXSP", "ANBERNIC_RGCUBEXX", "ANBERNIC_RGXX640480"},
            "device-magicx-zero28-v0": {"MAGICX_ZERO28"},
        }
        expected_defaults = {
            "device-miyoo-a30-v0": "ra32-a30-v1",
            "device-miyoo-mini-family-v0": "ra32-mini-v0",
            "device-trimui-a133p-family-v0": "ra64-universal-v1",
            "device-trimui-smart-pro-s-v0": "ra64-universal-v1",
            "device-miyoo-flip-v0": "ra64-universal-v1",
            "device-gkd-pixel2-v0": "ra64-pixel2-v0",
            "device-anbernic-h700-family-v0": "ra64-universal-v1",
            "device-magicx-zero28-v0": "ra64-universal-v1",
        }
        seen = set()
        for contract_id, device_ids in expected.items():
            devices = self.runtime["contracts"][contract_id]["devices"]
            self.assertEqual(device_ids, {device["device_id"] for device in devices})
            self.assertEqual(
                expected_defaults[contract_id],
                self.runtime["contracts"][contract_id]["default_execution_profile"],
            )
            for device in devices:
                self.assertNotIn(device["device_id"], seen)
                seen.add(device["device_id"])
                if device["support_status"] != "official":
                    self.assertFalse(device["release_default"])
        self.assertEqual("a133p-v0", self.runtime["contracts"]["device-trimui-a133p-family-v0"]["runtime_family_id"])
        self.assertEqual("a133p-v0", self.runtime["contracts"]["device-magicx-zero28-v0"]["runtime_family_id"])
        self.assertEqual([], self.runtime["contracts"]["device-miyoo-a30-v0"]["candidate_build_flavors"])

    def test_runtime_contract_canonical_facts_reject_coordinated_rehash(self) -> None:
        mutations = []
        changed_default = copy.deepcopy(self.runtime)
        changed_default["contracts"]["device-miyoo-a30-v0"][
            "default_execution_profile"
        ] = "ra64-universal-v1"
        mutations.append(changed_default)
        changed_device = copy.deepcopy(self.runtime)
        changed_device["contracts"]["device-miyoo-a30-v0"]["devices"][0][
            "device_id"
        ] = "UNRELATED_DEVICE"
        mutations.append(changed_device)
        changed_support = copy.deepcopy(self.runtime)
        changed_support["contracts"]["device-miyoo-a30-v0"]["devices"][0][
            "support_status"
        ] = "staged"
        changed_support["contracts"]["device-miyoo-a30-v0"]["devices"][0][
            "release_default"
        ] = False
        mutations.append(changed_support)
        changed_family = copy.deepcopy(self.runtime)
        changed_family["contracts"]["device-magicx-zero28-v0"][
            "runtime_family_id"
        ] = "different-family-v0"
        mutations.append(changed_family)
        changed_optional = copy.deepcopy(self.runtime)
        changed_optional["contracts"]["device-miyoo-a30-v0"][
            "optional_execution_profiles"
        ] = ["ra32-universal-v0"]
        mutations.append(changed_optional)
        changed_provider_path = copy.deepcopy(self.runtime)
        changed_provider_path["contracts"]["device-miyoo-a30-v0"][
            "provider_observations"
        ][0]["path"] = "spruce/other/lib/libstdc++.so.6"
        mutations.append(changed_provider_path)
        changed_provider_digest = copy.deepcopy(self.runtime)
        changed_provider_digest["contracts"]["device-miyoo-a30-v0"][
            "provider_observations"
        ][0]["sha256"] = "a" * 64
        mutations.append(changed_provider_digest)
        changed_provider_version = copy.deepcopy(self.runtime)
        changed_provider_version["contracts"]["device-miyoo-a30-v0"][
            "provider_observations"
        ][0]["max_versioned_symbols"]["GLIBCXX"] = "3.4.31"
        mutations.append(changed_provider_version)
        # target-loader-capture was retired by the 2026-07-22 on-device probe;
        # dropping a still-missing class must stay a rejection.
        changed_missing = copy.deepcopy(self.runtime)
        changed_missing["contracts"]["device-miyoo-a30-v0"][
            "missing_evidence"
        ].remove("target-rootfs-load-validation")
        mutations.append(changed_missing)
        for changed in mutations:
            refresh_digest(changed)
            with self.subTest(changed=changed):
                with self.assertRaises(registry.RegistryError):
                    registry.validate_runtime_contracts(
                        changed,
                        execution_profiles=self.execution,
                    )

    def test_provider_observations_do_not_become_abi_ceilings_or_mini_rejections(self) -> None:
        a30 = self.runtime["contracts"]["device-miyoo-a30-v0"]
        mini = self.runtime["contracts"]["device-miyoo-mini-family-v0"]
        self.assertEqual("unknown", a30["effective_abi_ceiling"])
        self.assertEqual("unknown", mini["effective_abi_ceiling"])
        self.assertEqual("3.4.32", a30["provider_observations"][0]["max_versioned_symbols"]["GLIBCXX"])
        self.assertEqual(
            "8014989515dc003f669e87abe4cbd89dcc4d68a458248ceee2528d73ed457a72",
            a30["provider_observations"][0]["sha256"],
        )
        # The 2026-07-22 on-device probe found this provider at
        # /mnt/SDCARD/miyoo/lib, first on the loader search path -- the same
        # file (sha256 below is unchanged) but bundled rather than a packaged
        # fallback, which is what the pre-probe label had guessed.
        self.assertEqual(
            "bundled-first-search-path-provider",
            mini["provider_observations"][0]["role"],
        )
        # 2026-07-23: the Mini family's bundled provider was upgraded on-SD
        # to the A30 buildroot libstdc++ (observed on-device by probe), so the
        # Mini and A30 now share the identical provider file.
        self.assertEqual(
            "8014989515dc003f669e87abe4cbd89dcc4d68a458248ceee2528d73ed457a72",
            mini["provider_observations"][0]["sha256"],
        )
        self.assertFalse(mini["provider_observations"][0]["enforcing"])
        constraint = self.runtime["compatibility_constraints"][0]
        self.assertEqual(["gearboy", "gearsystem"], constraint["core_ids"])
        self.assertEqual("unverified-for-profile", constraint["disposition"])
        self.assertNotIn("swanstation", constraint["core_ids"])

    def test_ffmpeg_and_swanstation_policies_remain_fail_closed(self) -> None:
        policies = self.runtime["core_policies"]
        ffmpeg = policies["ffmpeg"]
        self.assertEqual("software-diagnostic-only", ffmpeg["portable_role"])
        self.assertEqual("excluded", ffmpeg["default_selection"])
        candidate = ffmpeg["accelerated_candidates"][0]
        self.assertEqual(["a133p-v0"], candidate["runtime_family_ids"])
        self.assertEqual("provisional", candidate["status"])
        self.assertEqual(
            {"device-miyoo-flip-v0", "device-trimui-smart-pro-s-v0"},
            set(ffmpeg["accelerated_denied_runtime_contracts"]),
        )
        swan = policies["swanstation"]
        self.assertEqual("not-consumed", swan["armhf_device_views"])
        self.assertEqual("unsupported", swan["catalog_menu_eligibility"])


    def test_report_rejects_source_set_paths_outside_the_registry(self) -> None:
        for path in (
            "../noncanonical-source-set.json",
            "/tmp/noncanonical-source-set.json",
            "pins/core-sets/noncanonical-source-set.json",
        ):
            with self.subTest(path=path):
                with self.assertRaises(registry.RegistryError):
                    registry.report_data(source_set_path=path)

    def test_report_api_requires_explicit_source_inputs(self) -> None:
        with self.assertRaises(TypeError):
            registry.report_data()
        with self.assertRaises(TypeError):
            registry.verify_catalog_source_mirror()

    def test_report_enforces_individual_source_set_cardinality(self) -> None:
        with self._noncanonical_multi_core_source_set() as temporary:
            source_set_path = Path(temporary.name).relative_to(ROOT).as_posix()
            with self.assertRaisesRegex(
                registry.RegistryError,
                "individual source set must contain exactly one core",
            ):
                registry.report_data(source_set_path=source_set_path)

    def test_production_profile_registry_has_no_legacy_audit_api(self) -> None:
        self.assertFalse(hasattr(registry, "audit_legacy_data"))

    def test_cli_report_requires_an_explicit_source_set(self) -> None:
        completed = subprocess.run(
            ["python3", str(MODULE_PATH), "report", "--json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("--source-set", completed.stderr)
        self.assertIn("required", completed.stderr)

    def test_cli_report_help_describes_the_required_individual_source_set(
        self,
    ) -> None:
        completed = subprocess.run(
            ["python3", str(MODULE_PATH), "report", "--help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("--source-set SOURCE_SET", completed.stdout)
        self.assertIn(
            "required repo-relative individual source-set manifest",
            completed.stdout,
        )

    def test_cli_report_rejects_multi_core_input(self) -> None:
        with self._noncanonical_multi_core_source_set() as temporary:
            source_set_path = Path(temporary.name).relative_to(ROOT).as_posix()
            completed = subprocess.run(
                [
                    "python3",
                    str(MODULE_PATH),
                    "report",
                    "--source-set",
                    source_set_path,
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(2, completed.returncode)
        self.assertIn(
            "individual source set must contain exactly one core",
            completed.stderr,
        )

    def test_cli_has_no_legacy_audit_command(self) -> None:
        completed = subprocess.run(
            ["python3", str(MODULE_PATH), "audit-legacy"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("invalid choice", completed.stderr)

    def test_cli_report_accepts_an_individual_core_source_set(self) -> None:
        completed = subprocess.run(
            [
                "python3",
                str(MODULE_PATH),
                "report",
                "--source-set",
                SOURCE_SET_RELATIVE,
                "--json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        report = json.loads(completed.stdout)
        self.assertTrue(report["local_only"])
        self.assertEqual("disabled", report["publication"])
        self.assertEqual(
            "freechaf-76c7a84f1f7e-0fced3806666",
            report["source_set_id"],
        )
        self.assertEqual(1, report["counts"]["source_locks"])
        self.assertEqual(2, report["counts"]["build_evidence_cells"])
        self.assertEqual(
            CATALOG_CORE_COUNT - 1,
            report["mirror"]["catalog_unlocked_cores"],
        )
        self.assertTrue(
            all(
                not view["eligible_build_evidence_cells"]
                for view in report["device_views"]
            )
        )


if __name__ == "__main__":
    unittest.main()
