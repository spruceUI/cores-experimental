"""MAME 2003-Plus shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import mame2003_plus as mame
from core_pipeline_lib.contracts.registry import core_log_contract_for
from core_pipeline_lib.errors import PipelineError
from core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CORE_SPEC_SHA256 = (
    "1fe6588648a5b52cc172699edf6ae5591ff5e00a8d6349d4d4ad21ad9eb00da0"
)


def load_spec() -> dict:
    catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
    return catalog["cores"][mame.MAME2003_PLUS_CORE_ID]


class Mame2003PlusContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = load_spec()

    def test_catalog_spec_version_and_digest_are_exact(self) -> None:
        self.assertTrue(mame.mame2003_plus_spec_is_well_formed(self.spec))
        self.assertTrue(mame.mame2003_plus_identity_is_well_formed(self.spec))
        self.assertTrue(
            mame.mame2003_plus_git_version_contract_is_well_formed(
                self.spec["build"]["git_version"]
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
            "dist/unix/mame2003_plus_libretro.so",
            self.spec["build"]["output_path"],
        )
        self.assertEqual(
            mame.MAME2003_PLUS_FORBIDDEN_NEEDED_PREFIXES,
            self.spec["validation"]["forbidden_needed_prefixes"],
        )
        self.assertNotIn("recipe_profile", self.spec["build"])

    def test_spec_and_version_mutations_fail_closed(self) -> None:
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
            "derivation": ("build", "git_version", "derivation"),
            "version": ("build", "git_version", "value"),
            "scope": ("build", "git_version", "compiler_scope"),
            "metadata-source": ("metadata", "source_path"),
            "metadata-artifact": ("metadata", "artifact_name"),
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
                    mame.mame2003_plus_spec_is_well_formed(changed)
                )

        for path in ((), ("build",), ("build", "git_version")):
            changed = copy.deepcopy(self.spec)
            target = changed
            for key in path:
                target = target[key]
            target["unexpected"] = True
            with self.subTest(extra=path):
                self.assertFalse(
                    mame.mame2003_plus_spec_is_well_formed(changed)
                )

        self.assertFalse(
            mame.mame2003_plus_git_version_contract_is_well_formed(None)
        )
        self.assertEqual((), mame.mame2003_plus_git_version_markers({}))

    def test_command_scoped_build_shell_and_markers_are_exact(self) -> None:
        self.assertEqual(
            mame.MAME2003_PLUS_NATIVE_GIT_VERSION_MARKERS,
            mame.mame2003_plus_git_version_markers(
                self.spec["build"]["git_version"]
            ),
        )
        self.assertEqual(
            mame.MAME2003_PLUS_NATIVE_GIT_VERSION_MARKERS,
            mame.mame2003_plus_git_version_markers(self.spec),
        )
        self.assertEqual(
            '-- GIT_VERSION="\\ 5373e38e" HIDE=',
            mame.mame2003_plus_command_scoped_makeflags(self.spec),
        )
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                shell = mame.mame2003_plus_build_shell(
                    self.spec, mame.MAME2003_PLUS_CORE_ID, architecture
                )
                lines = shell.splitlines()
                self.assertEqual(7, len(lines))
                for marker in mame.MAME2003_PLUS_NATIVE_GIT_VERSION_MARKERS:
                    self.assertIn(marker, shell)
                self.assertIn(mame.MAME2003_PLUS_RECIPE_MARKER, shell)
                self.assertIn(
                    mame.MAME2003_PLUS_BUILD_BEGIN_MARKER[architecture], shell
                )
                self.assertIn(
                    mame.MAME2003_PLUS_BUILD_END_MARKER[architecture], shell
                )
                self.assertEqual(
                    "MAKEFLAGS='-- GIT_VERSION=\"\\ 5373e38e\" HIDE=' "
                    "./libretro-build.sh mame2003_plus",
                    lines[-2],
                )
                self.assertNotIn("export MAKEFLAGS", shell)

        with self.assertRaises(PipelineError):
            mame.mame2003_plus_build_shell(self.spec, "other", "arm64")
        with self.assertRaises(PipelineError):
            mame.mame2003_plus_build_shell(
                self.spec, mame.MAME2003_PLUS_CORE_ID, "x86_64"
            )
        changed = copy.deepcopy(self.spec)
        changed["build"]["git_version"]["value"] = " 00000000"
        with self.assertRaises(PipelineError):
            mame.mame2003_plus_command_scoped_makeflags(changed)

    def test_golden_source_and_build_contracts_are_exact(self) -> None:
        identity = mame.MAME2003_PLUS_SPEC_IDENTITY
        source = {
            **self.spec["source"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        self.assertTrue(
            mame.mame2003_plus_golden_source_is_well_formed(
                mame.MAME2003_PLUS_CORE_ID, source
            )
        )
        for architecture in ("arm64", "armhf"):
            build = {
                "driver": "libretro-super",
                "environment": "sanitized-v1",
                "compile_definitions": [],
                "git_version": copy.deepcopy(mame.MAME2003_PLUS_GIT_VERSION),
                "source_date_epoch": mame.MAME2003_PLUS_SOURCE_DATE_EPOCH,
                "log": "build.log",
                "log_sha256": "a" * 64,
            }
            with self.subTest(architecture=architecture):
                self.assertTrue(
                    mame.mame2003_plus_golden_build_contract_is_well_formed(
                        build,
                        mame.MAME2003_PLUS_SOURCE_COMMIT,
                        mame.MAME2003_PLUS_CORE_ID,
                        source,
                        architecture,
                    )
                )
                for key in ("git_version", "source_date_epoch"):
                    changed = copy.deepcopy(build)
                    del changed[key]
                    self.assertFalse(
                        mame.mame2003_plus_golden_build_contract_is_well_formed(
                            changed,
                            mame.MAME2003_PLUS_SOURCE_COMMIT,
                            mame.MAME2003_PLUS_CORE_ID,
                            source,
                            architecture,
                        )
                    )
        self.assertFalse(
            mame.mame2003_plus_golden_build_contract_is_well_formed(
                build,
                mame.MAME2003_PLUS_SOURCE_COMMIT,
                mame.MAME2003_PLUS_CORE_ID,
                source,
                "x86_64",
            )
        )
        changed_source = copy.deepcopy(source)
        changed_source["submodules"] = [
            {"state": " ", "commit": "0" * 40, "path": "vendor"}
        ]
        self.assertFalse(
            mame.mame2003_plus_golden_source_is_well_formed(
                mame.MAME2003_PLUS_CORE_ID, changed_source
            )
        )

    def test_registry_owns_one_exact_contract(self) -> None:
        contract = core_log_contract_for(mame.MAME2003_PLUS_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(mame.MAME2003_PLUS_LOG_CONTRACT_ID, contract.contract_id)
        self.assertEqual(
            "mame2003_plus_log_proves_contract", contract.proof_name
        )
        self.assertEqual(mame.MAME2003_PLUS_LOG_PROOF_KIND, contract.proof_kind)
        self.assertEqual(
            frozenset({mame.MAME2003_PLUS_CORE_ID}), contract.core_ids
        )


if __name__ == "__main__":
    unittest.main()
