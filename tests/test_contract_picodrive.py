from __future__ import annotations

import copy
import json
from pathlib import Path
import shlex
import unittest

from scripts.core_pipeline_lib.contracts import picodrive
from scripts.core_pipeline_lib.contracts.command_line import output_option
from scripts.core_pipeline_lib.contracts.registry import core_log_contract_for
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes, sha256_file


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "manifests/core-builds.json"
METADATA_PATH = ROOT / picodrive.PICODRIVE_METADATA_REPLACEMENT_PATH
CONTROL_ROOT = Path("/tmp/picodrive-evidence")
CONTROL_LOGS = {
    architecture: tuple(
        CONTROL_ROOT / architecture / f"control{index}.log"
        for index in (1, 2)
    )
    for architecture in ("arm64", "armhf")
}
CONTROL_ARTIFACTS = {
    architecture: tuple(
        CONTROL_ROOT / architecture / f"control{index}.so"
        for index in (1, 2)
    )
    for architecture in ("arm64", "armhf")
}
EXPECTED_CORE_SPEC_SHA256 = (
    "e00b3c9850a97003fe2803f3761c5aa273d844fa67a6100d94739d2fb410c14a"
)


def load_spec() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return catalog["cores"][picodrive.PICODRIVE_CORE_ID]


def active_log(build_body: str, architecture: str) -> str:
    return (
        "\n".join(
            (
                picodrive.PICODRIVE_RECIPE_MARKER[architecture],
                picodrive.PICODRIVE_BUILD_BEGIN_MARKER[architecture],
            )
        )
        + "\n"
        + build_body
        + picodrive.PICODRIVE_BUILD_END_MARKER[architecture]
        + "\n"
    )


def contract_arguments(build_log: str, architecture: str) -> tuple[object, ...]:
    return (
        build_log,
        picodrive.PICODRIVE_CORE_ID,
        architecture,
        picodrive.PICODRIVE_SOURCE_COMMIT,
        picodrive.PICODRIVE_SOURCE_TREE,
    )


class PicodriveContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_spec()

    def require_controls(self) -> None:
        if any(
            not path.is_file()
            for paths in CONTROL_LOGS.values()
            for path in paths
        ):
            self.skipTest("workspace-local Picodrive controls are unavailable")

    def assert_rejected(self, log: str, architecture: str) -> None:
        self.assertFalse(
            picodrive.picodrive_log_proves_contract(
                *contract_arguments(log, architecture)
            )
        )

    def test_catalog_spec_profile_metadata_and_digest_are_exact(self) -> None:
        self.assertTrue(picodrive.picodrive_spec_is_well_formed(self.spec))
        self.assertTrue(
            picodrive.picodrive_identity_is_well_formed(self.spec)
        )
        self.assertTrue(
            picodrive.picodrive_recipe_profile_is_well_formed(
                self.spec["build"]["recipe_profile"]
            )
        )
        self.assertTrue(
            picodrive.picodrive_metadata_replacement_contract_is_well_formed(
                self.spec["metadata"]["replacement"]
            )
        )
        self.assertEqual(
            EXPECTED_CORE_SPEC_SHA256,
            sha256_bytes(
                json.dumps(
                    self.spec, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ),
        )
        self.assertEqual(
            "libretro-picodrive/picodrive_libretro.so",
            self.spec["build"]["output_path"],
        )
        self.assertEqual(
            picodrive.PICODRIVE_FORBIDDEN_NEEDED_PREFIXES,
            self.spec["validation"]["forbidden_needed_prefixes"],
        )
        self.assertEqual(
            picodrive.PICODRIVE_METADATA_REPLACEMENT_SHA256,
            sha256_file(METADATA_PATH),
        )
        self.assertEqual(
            picodrive.PICODRIVE_REVIEWED_OUTPUT_FACTS["metadata"]["size"],
            METADATA_PATH.stat().st_size,
        )

    def test_spec_mutations_fail_closed(self) -> None:
        mutations: dict[str, tuple[str, ...]] = {
            "workflow": ("workflow",),
            "source-url": ("source", "url"),
            "source-ref": ("source", "requested_ref"),
            "source-commit": ("source", "commit"),
            "source-tree": ("source", "tree"),
            "driver": ("build", "driver"),
            "source-key": ("build", "source_key"),
            "source-dir": ("build", "source_dir"),
            "output": ("build", "output_path"),
            "artifact": ("build", "artifact_name"),
            "epoch": ("build", "source_date_epoch"),
            "revision": ("build", "recipe_profile", "git_revision"),
            "profile-kind": ("build", "recipe_profile", "kind"),
            "host-cc": (
                "build",
                "recipe_profile",
                "armhf_host_tools",
                "CYCLONE_CC",
            ),
            "host-cxx": (
                "build",
                "recipe_profile",
                "armhf_host_tools",
                "CYCLONE_CXX",
            ),
            "metadata-source": ("metadata", "source_path"),
            "metadata-artifact": ("metadata", "artifact_name"),
            "metadata-preimage": (
                "metadata",
                "replacement",
                "preimage_sha256",
            ),
            "metadata-replacement": (
                "metadata",
                "replacement",
                "replacement_sha256",
            ),
            "targets": ("targets",),
            "dependency-policy": (
                "validation",
                "forbidden_needed_prefixes",
            ),
        }
        for label, path in mutations.items():
            changed = copy.deepcopy(self.spec)
            parent: object = changed
            for key in path[:-1]:
                assert isinstance(parent, dict)
                parent = parent[key]
            assert isinstance(parent, dict)
            value = parent[path[-1]]
            if isinstance(value, str):
                parent[path[-1]] = value + "-changed"
            elif isinstance(value, int):
                parent[path[-1]] = value + 1
            elif isinstance(value, list):
                parent[path[-1]] = [*value, "changed"]
            else:
                self.fail(f"unsupported mutation fixture for {label}")
            with self.subTest(label=label):
                self.assertFalse(
                    picodrive.picodrive_spec_is_well_formed(changed)
                )

        for label, path in {
            "extra-top-level": (),
            "extra-build": ("build",),
            "extra-profile": ("build", "recipe_profile"),
            "extra-host-tool": (
                "build",
                "recipe_profile",
                "armhf_host_tools",
            ),
        }.items():
            changed = copy.deepcopy(self.spec)
            target = changed
            for key in path:
                target = target[key]
            target["unexpected"] = True
            with self.subTest(label=label):
                self.assertFalse(
                    picodrive.picodrive_spec_is_well_formed(changed)
                )

    def test_identity_tolerates_only_replacement_presence_for_diagnostics(
        self,
    ) -> None:
        missing = copy.deepcopy(self.spec)
        del missing["metadata"]["replacement"]
        self.assertTrue(
            picodrive.picodrive_identity_is_well_formed(missing)
        )
        self.assertFalse(picodrive.picodrive_spec_is_well_formed(missing))

        malformed = copy.deepcopy(self.spec)
        malformed["metadata"]["replacement"] = {"unexpected": True}
        self.assertTrue(
            picodrive.picodrive_identity_is_well_formed(malformed)
        )
        unrelated = copy.deepcopy(self.spec)
        unrelated["build"]["source_key"] = "other"
        self.assertFalse(
            picodrive.picodrive_identity_is_well_formed(unrelated)
        )

    def test_source_root_recipe_shell_is_exact_and_arch_scoped(self) -> None:
        for architecture, make_program in picodrive.PICODRIVE_MAKE_PROGRAM.items():
            with self.subTest(architecture=architecture):
                shell = picodrive.picodrive_recipe_shell(
                    self.spec, architecture
                )
                self.assertIn(
                    "unset GIT_REVISION CYCLONE_CC CYCLONE_CXX", shell
                )
                self.assertIn("export GIT_REVISION=-f0d4a011", shell)
                self.assertIn(
                    "cd /libretro-super/libretro-picodrive", shell
                )
                build_line = next(
                    line
                    for line in shell.splitlines()
                    if line.startswith(make_program + " ")
                )
                self.assertEqual(
                    f'{make_program} -f Makefile.libretro '
                    'platform="unix" -j7',
                    build_line,
                )
                self.assertNotIn(" CC=", build_line)
                self.assertNotIn(" CXX=", build_line)
                self.assertNotIn("./libretro-build.sh", shell)
                self.assertIn(
                    picodrive.PICODRIVE_RECIPE_MARKER[architecture], shell
                )
                self.assertIn(
                    picodrive.PICODRIVE_BUILD_BEGIN_MARKER[architecture],
                    shell,
                )
                self.assertIn(
                    picodrive.PICODRIVE_BUILD_END_MARKER[architecture], shell
                )
                if architecture == "armhf":
                    self.assertIn("export CYCLONE_CC=gcc", shell)
                    self.assertIn("export CYCLONE_CXX=g++", shell)
                else:
                    self.assertNotIn("export CYCLONE_CC=", shell)
                    self.assertNotIn("export CYCLONE_CXX=", shell)

        changed = copy.deepcopy(self.spec)
        changed["build"]["recipe_profile"]["git_revision"] = "-f0000000"
        with self.assertRaises(PipelineError):
            picodrive.picodrive_recipe_shell(changed, "arm64")
        with self.assertRaises(PipelineError):
            picodrive.picodrive_recipe_shell(self.spec, "x86_64")

    def test_golden_source_and_build_contracts_bind_submodules(self) -> None:
        identity = picodrive.PICODRIVE_SPEC_IDENTITY
        source = {
            **self.spec["source"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": copy.deepcopy(picodrive.PICODRIVE_SUBMODULES),
        }
        self.assertTrue(
            picodrive.picodrive_golden_source_is_well_formed(
                picodrive.PICODRIVE_CORE_ID, source
            )
        )
        for architecture, definitions in {
            "arm64": [],
            "armhf": picodrive.PICODRIVE_ARMHF_COMPILE_DEFINITIONS,
        }.items():
            build = {
                "driver": "libretro-super",
                "environment": "sanitized-v1",
                "compile_definitions": definitions,
                "recipe_profile": copy.deepcopy(
                    picodrive.PICODRIVE_RECIPE_PROFILE
                ),
                "source_date_epoch": picodrive.PICODRIVE_SOURCE_DATE_EPOCH,
                "metadata_replacement": copy.deepcopy(
                    picodrive.PICODRIVE_METADATA_REPLACEMENT
                ),
                "log": "build.log",
                "log_sha256": "a" * 64,
            }
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    picodrive.picodrive_golden_build_contract_is_well_formed(
                        build,
                        picodrive.PICODRIVE_SOURCE_COMMIT,
                        picodrive.PICODRIVE_CORE_ID,
                        source,
                        architecture,
                    )
                )
                other_architecture = (
                    "armhf" if architecture == "arm64" else "arm64"
                )
                self.assertFalse(
                    picodrive.picodrive_golden_build_contract_is_well_formed(
                        build,
                        picodrive.PICODRIVE_SOURCE_COMMIT,
                        picodrive.PICODRIVE_CORE_ID,
                        source,
                        other_architecture,
                    )
                )
                for key in (
                    "recipe_profile",
                    "source_date_epoch",
                    "metadata_replacement",
                ):
                    changed = copy.deepcopy(build)
                    del changed[key]
                    self.assertFalse(
                        picodrive.picodrive_golden_build_contract_is_well_formed(
                            changed,
                            picodrive.PICODRIVE_SOURCE_COMMIT,
                            picodrive.PICODRIVE_CORE_ID,
                            source,
                            architecture,
                        )
                    )

        arm64_build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "recipe_profile": copy.deepcopy(
                picodrive.PICODRIVE_RECIPE_PROFILE
            ),
            "source_date_epoch": picodrive.PICODRIVE_SOURCE_DATE_EPOCH,
            "metadata_replacement": copy.deepcopy(
                picodrive.PICODRIVE_METADATA_REPLACEMENT
            ),
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertFalse(
            picodrive.picodrive_golden_build_contract_is_well_formed(
                arm64_build,
                picodrive.PICODRIVE_SOURCE_COMMIT,
                picodrive.PICODRIVE_CORE_ID,
                source,
                "x86_64",
            )
        )

        changed_source = copy.deepcopy(source)
        changed_source["submodules"][0]["commit"] = "0" * 40
        self.assertFalse(
            picodrive.picodrive_golden_source_is_well_formed(
                picodrive.PICODRIVE_CORE_ID, changed_source
            )
        )
        changed_source = copy.deepcopy(source)
        changed_source["submodules"].reverse()
        self.assertFalse(
            picodrive.picodrive_golden_source_is_well_formed(
                picodrive.PICODRIVE_CORE_ID, changed_source
            )
        )

    def test_registry_owns_one_exact_picodrive_contract(self) -> None:
        contract = core_log_contract_for(picodrive.PICODRIVE_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(picodrive.PICODRIVE_LOG_CONTRACT_ID, contract.contract_id)
        self.assertEqual(
            "picodrive_log_proves_contract", contract.proof_name
        )
        self.assertEqual(picodrive.PICODRIVE_LOG_PROOF_KIND, contract.proof_kind)
        self.assertEqual(
            frozenset({picodrive.PICODRIVE_CORE_ID}), contract.core_ids
        )

    def test_malformed_log_values_fail_closed(self) -> None:
        for malformed in (None, b"", [], {}, 0):
            with self.subTest(malformed=type(malformed).__name__):
                self.assertFalse(
                    picodrive.picodrive_log_proves_contract(
                        malformed,
                        picodrive.PICODRIVE_CORE_ID,
                        "arm64",
                        picodrive.PICODRIVE_SOURCE_COMMIT,
                        picodrive.PICODRIVE_SOURCE_TREE,
                    )
                )


if __name__ == "__main__":
    unittest.main()
