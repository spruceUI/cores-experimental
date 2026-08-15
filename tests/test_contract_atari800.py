"""Atari800 shared C-only compile/link contract tests (leveled to the handy standard)."""

from __future__ import annotations

import copy
from pathlib import Path
import shlex
import unittest

from .core_contract_helpers import pipeline
from core_pipeline_lib.contracts import atari800, c_only
from core_pipeline_lib.contracts.compiler import (
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
)
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]

# The exact reviewed C compile options, in order, that the stored compile and
# link sha256 constants were computed from. Rebuilding the commands from the
# reviewed object list plus these options and proving them without mocking any
# constant is what pins those constants against a copy error (Atari800 has no
# committed end-to-end log to replay).
COMMON_COMPILE_OPTIONS = (
    r'-DGIT_VERSION=\"" 9d3bcf2"\"',
    "-O2",
    "-DNDEBUG",
    "-fPIC",
    "-D__LIBRETRO__",
    '-DINLINE="inline"',
    "-DHAVE_CONFIG_H",
    "-Wall",
    "-I.",
    "-I./atari800/src",
    "-I./libretro",
    "-I./libretro/libretro-common/include",
    "-I./libretro/libretro-common/include/compat/zlib",
    "-I./deps/zlib",
)
C_COMPILERS = {
    "arm64": "aarch64-linux-gnu-gcc",
    "armhf": "arm-a30-linux-gnueabihf-gcc",
}


def reviewed_build_log(architecture: str) -> str:
    """Rebuild Atari800's exact compile and link commands from the object list."""

    c_compiler = C_COMPILERS[architecture]
    compile_lines = [
        " ".join((c_compiler, "-c", f"-o{output}", source, *COMMON_COMPILE_OPTIONS))
        for output, source in atari800.ATARI800_EXPECTED_COMPILE_PAIRS
    ]
    link_line = " ".join(
        (
            c_compiler,
            "-o",
            atari800.ATARI800_BUILD_ARTIFACT_NAME,
            "-shared",
            "-Wl,-version-script=link.T",
            "-Wl,-no-undefined",
            *atari800.ATARI800_EXPECTED_RAW_LINK_OBJECTS,
            "-lm",
        )
    )
    return "\n".join((*compile_lines, link_line)) + "\n"


def hardened_spec() -> dict:
    identity = atari800.ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
    return {
        "workflow": identity["workflow"],
        "source": {
            "url": identity["source_url"],
            "requested_ref": identity["source_requested_ref"],
            "commit": identity["source_commit"],
            "tree": identity["source_tree"],
        },
        "build": {
            "driver": "libretro-super",
            "source_key": identity["source_key"],
            "source_dir": identity["source_dir"],
            "output_path": identity["output_path"],
            "artifact_name": identity["artifact_name"],
            "git_version": {
                "derivation": (
                    atari800.ATARI800_NATIVE_GIT_VERSION_DERIVATION
                ),
                "value": atari800.ATARI800_NATIVE_GIT_VERSION,
                "compiler_scope": "c",
            },
        },
        "metadata": {
            "source_path": identity["metadata_source_path"],
            "artifact_name": identity["metadata_artifact_name"],
            "replacement": copy.deepcopy(
                atari800.ATARI800_METADATA_REPLACEMENT
            ),
        },
        "targets": list(identity["targets"]),
        "validation": {
            "forbidden_needed_prefixes": list(
                atari800.ATARI800_FORBIDDEN_NEEDED_PREFIXES
            )
        },
    }


class Atari800ContractTests(unittest.TestCase):
    def test_registry_identity_is_owned_by_atari800(self) -> None:
        contract = core_log_contract_for(atari800.ATARI800_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("atari800-c-only-v1", contract.contract_id)
        self.assertEqual("atari800_log_proves_contract", contract.proof_name)
        self.assertEqual("core-arch-source", contract.proof_kind)
        self.assertEqual(
            frozenset({atari800.ATARI800_CORE_ID}), contract.core_ids
        )

    def test_exact_identity_replacement_and_golden_contracts_are_owned(
        self,
    ) -> None:
        spec = hardened_spec()
        identity = atari800.ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertTrue(atari800.atari800_identity_is_well_formed(spec))
        self.assertTrue(atari800.atari800_spec_is_well_formed(spec))
        self.assertEqual("Makefile", identity["native_makefile"])
        self.assertEqual("c", identity["compiler_scope"])
        self.assertEqual(
            [
                "libEGL",
                "libGL",
                "libGLES",
                "libOpenGL",
                "libSDL",
                "libstdc++",
                "libz",
            ],
            spec["validation"]["forbidden_needed_prefixes"],
        )
        self.assertEqual(
            {
                "kind": "whole-file-v1",
                "path": "metadata/atari800/source-v1.info",
                "preimage_sha256": (
                    "1682c00740626f0bc709dbbcdae1777222773b93a1007bc02e4"
                    "024df7b181653"
                ),
                "replacement_sha256": (
                    "4b56fa399760a8c48e6ac8b08ecc2ae2f7163bbfb34f3f0835"
                    "1bc7e092602e5e"
                ),
            },
            atari800.ATARI800_METADATA_REPLACEMENT,
        )
        self.assertTrue(
            atari800.atari800_metadata_replacement_contract_is_well_formed(
                spec["metadata"]["replacement"]
            )
        )

        for label, replacement in {
            "missing": None,
            "scalar": "source-v1.info",
            "wrong-kind": {
                **atari800.ATARI800_METADATA_REPLACEMENT,
                "kind": "patch-v1",
            },
            "wrong-path": {
                **atari800.ATARI800_METADATA_REPLACEMENT,
                "path": "metadata/atari800/other.info",
            },
            "wrong-preimage": {
                **atari800.ATARI800_METADATA_REPLACEMENT,
                "preimage_sha256": "0" * 64,
            },
            "wrong-replacement": {
                **atari800.ATARI800_METADATA_REPLACEMENT,
                "replacement_sha256": "0" * 64,
            },
            "extra": {
                **atari800.ATARI800_METADATA_REPLACEMENT,
                "unexpected": True,
            },
        }.items():
            changed = copy.deepcopy(spec)
            if replacement is None:
                changed["metadata"].pop("replacement")
            else:
                changed["metadata"]["replacement"] = replacement
            with self.subTest(replacement=label):
                self.assertTrue(
                    atari800.atari800_identity_is_well_formed(changed),
                    "the identity recognizer leaves precise replacement "
                    "diagnostics to the replacement validator",
                )
                self.assertFalse(
                    atari800.atari800_spec_is_well_formed(changed)
                )
                self.assertFalse(
                    atari800.atari800_metadata_replacement_contract_is_well_formed(
                        changed["metadata"].get("replacement")
                    )
                )

        def changed(path: tuple[str, ...], value: object) -> dict:
            result = copy.deepcopy(spec)
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return result

        nonreplacement_mutations = {
            "workflow": changed(("workflow",), "build.yml"),
            "source-url": changed(
                ("source", "url"), "https://example.com/atari800.git"
            ),
            "source-ref": changed(
                ("source", "requested_ref"), "refs/heads/main"
            ),
            "source-commit": changed(("source", "commit"), "0" * 40),
            "source-tree": changed(("source", "tree"), "0" * 40),
            "driver": changed(("build", "driver"), "direct-make"),
            "source-key": changed(("build", "source_key"), "other"),
            "source-dir": changed(("build", "source_dir"), "other"),
            "output": changed(("build", "output_path"), "other.so"),
            "artifact": changed(
                ("build", "artifact_name"), "other_libretro.so"
            ),
            "derivation": changed(
                ("build", "git_version", "derivation"),
                "hyphen-short7-v1",
            ),
            "version": changed(
                ("build", "git_version", "value"), " 0000000"
            ),
            "compiler-scope": changed(
                ("build", "git_version", "compiler_scope"), "all"
            ),
            "metadata-source": changed(
                ("metadata", "source_path"), "/tmp/other.info"
            ),
            "metadata-artifact": changed(
                ("metadata", "artifact_name"), "other.info"
            ),
            "targets": changed(("targets",), ["arm64"]),
            "validation": changed(
                ("validation", "forbidden_needed_prefixes"), ["libz"]
            ),
        }
        extra = copy.deepcopy(spec)
        extra["unexpected"] = True
        nonreplacement_mutations["extra"] = extra
        for label, mutation in nonreplacement_mutations.items():
            with self.subTest(identity=label):
                self.assertFalse(
                    atari800.atari800_identity_is_well_formed(mutation)
                )
                self.assertFalse(
                    atari800.atari800_spec_is_well_formed(mutation)
                )

        source = {
            **spec["source"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        build = {
            "driver": "libretro-super",
            "environment": "sanitized-v1",
            "compile_definitions": [],
            "git_version": copy.deepcopy(spec["build"]["git_version"]),
            "metadata_replacement": copy.deepcopy(
                atari800.ATARI800_METADATA_REPLACEMENT
            ),
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            atari800.atari800_golden_source_is_well_formed(
                atari800.ATARI800_CORE_ID, source
            )
        )
        self.assertTrue(
            atari800.atari800_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                atari800.ATARI800_CORE_ID,
                source,
            )
        )
        for label, mutation in {
            "driver": {**build, "driver": "direct-make"},
            "environment": {**build, "environment": "inherited"},
            "definition": {
                **build,
                "compile_definitions": ["SYSTEM_ZLIB=1"],
            },
            "version": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "value": " 0000000",
                },
            },
            "metadata": {
                **build,
                "metadata_replacement": {
                    **build["metadata_replacement"],
                    "replacement_sha256": "0" * 64,
                },
            },
            "log": {**build, "log": "other.log"},
            "digest": {**build, "log_sha256": "a" * 63},
            "extra": {**build, "unexpected": True},
        }.items():
            with self.subTest(golden_build=label):
                self.assertFalse(
                    atari800.atari800_golden_build_contract_is_well_formed(
                        mutation,
                        identity["source_commit"],
                        atari800.ATARI800_CORE_ID,
                        source,
                    )
                )
        changed_source = copy.deepcopy(source)
        changed_source["tree"] = "0" * 40
        self.assertFalse(
            atari800.atari800_golden_source_is_well_formed(
                atari800.ATARI800_CORE_ID, changed_source
            )
        )
        self.assertFalse(
            atari800.atari800_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                atari800.ATARI800_CORE_ID,
                changed_source,
            )
        )

    def test_reviewed_object_list_pins_exact_compile_and_link_constants(
        self,
    ) -> None:
        identity = atari800.ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY
        self.assertEqual(87, atari800.ATARI800_EXPECTED_COMPILE_COUNT)
        self.assertEqual(
            12,
            sum(
                path.startswith("./deps/zlib/")
                for path in atari800.ATARI800_EXPECTED_RAW_LINK_OBJECTS
            ),
        )
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                log = reviewed_build_log(architecture)
                arguments = (
                    log,
                    atari800.ATARI800_CORE_ID,
                    architecture,
                    identity["source_commit"],
                    identity["source_tree"],
                )
                # No constant is mocked: the reviewed reconstruction must match
                # the stored compile/link sha256 constants exactly.
                self.assertTrue(atari800.atari800_log_proves_contract(*arguments))
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

                c_compilers = TARGET_COMPILERS[architecture] - (
                    TARGET_CXX_COMPILERS[architecture]
                )
                invocations = []
                for line in log.splitlines():
                    tokens = shlex.split(line)
                    if not tokens or tokens[0] not in c_compilers or "-c" not in tokens:
                        continue
                    invocation = c_only.c_only_compile_invocation(
                        tokens, c_compilers
                    )
                    self.assertIsNotNone(invocation)
                    assert invocation is not None
                    invocations.append(invocation)
                self.assertEqual(87, len(invocations))
                self.assertEqual(
                    atari800.ATARI800_EXPECTED_COMPILE_PAIR_SHA256,
                    c_only.c_only_compile_pair_sha256(
                        (output, source)
                        for output, source, _tokens in invocations
                    ),
                )
                self.assertEqual(
                    atari800.ATARI800_EXPECTED_COMPILE_INVOCATION_SHA256[
                        architecture
                    ],
                    c_only.c_only_compile_invocation_sha256(invocations),
                )

                self.assertFalse(
                    atari800.atari800_log_proves_contract(
                        log,
                        "stella2014",
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )
                self.assertFalse(
                    atari800.atari800_log_proves_contract(
                        log + "fatal: synthetic failure\n",
                        atari800.ATARI800_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )


if __name__ == "__main__":
    unittest.main()
