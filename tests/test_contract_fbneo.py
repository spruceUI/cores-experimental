from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from .core_contract_helpers import pipeline
from scripts.core_pipeline_lib.contracts import fbneo
from scripts.core_pipeline_lib.contracts.registry import core_log_contract_for
from scripts.core_pipeline_lib.errors import PipelineError
from scripts.core_pipeline_lib.foundation import sha256_bytes


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "manifests/core-builds.json"
EXPECTED_CORE_SPEC_SHA256 = (
    "a55d0e4f5508d4a7ac56d4d953e8958ad55773881f48bc9086e5241fd663c05d"
)


EXPECTED_SPEC = {
    "workflow": ".github/workflows/build-fbneo.yml",
    "source": {
        "url": "https://github.com/libretro/FBNeo.git",
        "requested_ref": "refs/heads/master",
        "commit": "9d7716aa20cbdf49024f42980c33c7cd366e784f",
        "tree": "e533af34d2db18f11cefadbb93e509579580d0b7",
    },
    "build": {
        "driver": "libretro-super",
        "source_key": "fbneo",
        "source_dir": "libretro-fbneo",
        "output_path": "dist/unix/fbneo_libretro.so",
        "artifact_name": "fbneo_libretro.so",
        "compile_definitions": {
            "armhf": [
                "HWCAP2_AES=1",
                "HWCAP2_CRC32=16",
                "HWCAP2_SHA1=4",
                "HWCAP2_SHA2=8",
            ]
        },
        "source_date_epoch": 1777823586,
        "git_version": {
            "derivation": "fbneo-native-short9-date-v1",
            "value": "9d7716aa2",
            "git_date": "260503",
            "compiler_scope": "cxx",
        },
        "overlays": {
            arch: [
                {
                    "kind": "git-apply-v1",
                    "patch_path": (
                        "patches/fbneo/makefile-sort-wildcard-sources.patch"
                    ),
                    "patch_sha256": (
                        "36359710caa6b337253ea7acf3cc0fe43083a3eb1977f62cc"
                        "764fd888eceb54e"
                    ),
                    "preimage_sha256": (
                        "b7030bbeb7c69a46e846084a1a852c972d5360b8f319caca9"
                        "87dc1ec9dfefb73"
                    ),
                    "postimage_sha256": (
                        "d7e2bd630fffafb6def25a52295e2b582fe5bcf31b8e246dc"
                        "adc53f2f437bc0b"
                    ),
                    "source_path": "src/burner/libretro/Makefile.all",
                }
            ]
            for arch in ("arm64", "armhf")
        },
    },
    "metadata": {
        "source_path": "/libretro-super/dist/info/fbneo_libretro.info",
        "artifact_name": "fbneo_libretro.info",
    },
    "validation": {
        "forbidden_needed_prefixes": [
            "libEGL",
            "libGL",
            "libGLES",
            "libOpenGL",
            "libSDL",
            "libz",
        ],
    },
    "targets": ["arm64", "armhf"],
}


def golden_source() -> dict:
    return {
        "url": "https://github.com/libretro/FBNeo.git",
        "requested_ref": "refs/heads/master",
        "commit": "9d7716aa20cbdf49024f42980c33c7cd366e784f",
        "tree": "e533af34d2db18f11cefadbb93e509579580d0b7",
        "resolved_commit": (
            "9d7716aa20cbdf49024f42980c33c7cd366e784f"
        ),
        "resolved_url": "https://github.com/libretro/FBNeo.git",
        "submodules": [],
    }


def golden_build(arch: str) -> dict:
    return {
        "driver": "libretro-super",
        "environment": "sanitized-v1",
        "compile_definitions": (
            []
            if arch == "arm64"
            else copy.deepcopy(fbneo.FBNEO_ARMHF_COMPILE_DEFINITIONS)
        ),
        "git_version": copy.deepcopy(EXPECTED_SPEC["build"]["git_version"]),
        "source_date_epoch": 1777823586,
        "log": "build.log",
        "log_sha256": "a" * 64,
    }


def version_log(arch: str) -> str:
    compilers = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }
    cc, cxx = compilers[arch]
    definitions = (
        []
        if arch == "arm64"
        else [
            f"-D{definition}"
            for definition in fbneo.FBNEO_ARMHF_COMPILE_DEFINITIONS
        ]
    )
    common = " ".join(definitions)
    c_line = f"{cc} {common} -O2 -c source.c -o source.o"
    cxx_line = (
        f"{cxx} {common} {fbneo.FBNEO_GIT_VERSION_LOG_TOKEN} "
        f"{fbneo.FBNEO_GIT_DATE_LOG_TOKEN} -O2 -c source.cpp "
        "-o source-cxx.o"
    )
    return "\n".join(
        (*fbneo.FBNEO_NATIVE_GIT_VERSION_MARKERS, c_line, cxx_line)
    ) + "\n"


class FbneoContractTests(unittest.TestCase):
    def setUp(self) -> None:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.spec = catalog["cores"][fbneo.FBNEO_CORE_ID]

    def test_exact_spec_identity_and_version_are_accepted(self) -> None:
        self.assertEqual(EXPECTED_SPEC, self.spec)
        self.assertEqual(
            EXPECTED_CORE_SPEC_SHA256,
            sha256_bytes(
                json.dumps(
                    self.spec, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ),
        )
        self.assertTrue(fbneo.fbneo_spec_is_well_formed(self.spec))
        self.assertTrue(fbneo.fbneo_identity_is_well_formed(self.spec))
        self.assertTrue(
            fbneo.fbneo_git_version_contract_is_well_formed(
                self.spec["build"]["git_version"]
            )
        )
        self.assertEqual(
            "9d7716aa20cbdf49024f42980c33c7cd366e784f",
            fbneo.FBNEO_SOURCE_COMMIT,
        )
        self.assertEqual(
            "e533af34d2db18f11cefadbb93e509579580d0b7",
            fbneo.FBNEO_SOURCE_TREE,
        )
        self.assertEqual(1777823586, fbneo.FBNEO_SOURCE_DATE_EPOCH)

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
            "compile-definitions": ("build", "compile_definitions"),
            "epoch": ("build", "source_date_epoch"),
            "derivation": ("build", "git_version", "derivation"),
            "version": ("build", "git_version", "value"),
            "date": ("build", "git_version", "git_date"),
            "scope": ("build", "git_version", "compiler_scope"),
            "metadata-source": ("metadata", "source_path"),
            "metadata-artifact": ("metadata", "artifact_name"),
            "validation": (
                "validation",
                "forbidden_needed_prefixes",
            ),
            "targets": ("targets",),
        }
        for label, path in mutations.items():
            with self.subTest(mutation=label):
                changed = copy.deepcopy(self.spec)
                owner = changed
                for component in path[:-1]:
                    owner = owner[component]
                key = path[-1]
                value = owner[key]
                if isinstance(value, list):
                    owner[key] = [*value, "changed"]
                elif isinstance(value, int):
                    owner[key] = value + 1
                else:
                    owner[key] = f"{value}-changed"
                self.assertFalse(
                    fbneo.fbneo_spec_is_well_formed(changed)
                )

        for label, changed in {
            "extra-top-level": {**self.spec, "extra": True},
            "extra-build": {
                **self.spec,
                "build": {**self.spec["build"], "extra": True},
            },
            "boolean-epoch": {
                **self.spec,
                "build": {
                    **self.spec["build"],
                    "source_date_epoch": True,
                },
            },
            "wrong-type": [],
        }.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    fbneo.fbneo_spec_is_well_formed(changed)
                )

    def test_version_markers_and_compile_tokens_are_exact(self) -> None:
        contract = self.spec["build"]["git_version"]
        markers = fbneo.fbneo_git_version_markers(contract)
        self.assertEqual(
            (
                "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                '"9d7716aa2"|command-scoped-makeflags',
                "CORE_PIPELINE_NATIVE_GIT_DATE_BUILD_ARG|"
                '"260503"|command-scoped-makeflags',
                "CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|"
                "-- GIT_VERSION=9d7716aa2 GIT_DATE=260503 HIDE=",
                "CORE_PIPELINE_NATIVE_GIT_VERSION|"
                '"9d7716aa2"|command line',
                'CORE_PIPELINE_NATIVE_GIT_DATE|"260503"|command line',
            ),
            markers,
        )
        self.assertEqual(markers, fbneo.fbneo_git_version_markers(self.spec))
        self.assertEqual(
            (
                '-DGIT_VERSION="GIT9d7716aa2"',
                '-DGIT_DATE="260503"',
            ),
            fbneo.fbneo_compile_tokens(contract),
        )
        self.assertEqual(
            r'-DGIT_VERSION=\"GIT9d7716aa2\"',
            fbneo.FBNEO_GIT_VERSION_LOG_TOKEN,
        )
        self.assertEqual(
            r'-DGIT_DATE=\"260503\"',
            fbneo.FBNEO_GIT_DATE_LOG_TOKEN,
        )

        for field, value in {
            "derivation": "native-space-short9-v1",
            "value": "9d7716aa",
            "git_date": "260504",
            "compiler_scope": "c",
        }.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(contract)
                changed[field] = value
                self.assertFalse(
                    fbneo.fbneo_git_version_contract_is_well_formed(changed)
                )
                self.assertEqual((), fbneo.fbneo_git_version_markers(changed))
                self.assertEqual((), fbneo.fbneo_compile_tokens(changed))

    def test_shared_version_log_proof_accepts_exact_cxx_scope(self) -> None:
        for arch in ("arm64", "armhf"):
            log = version_log(arch)
            with self.subTest(arch=arch):
                self.assertTrue(
                    pipeline.git_version_log_proves_contract(
                        log,
                        self.spec["build"]["git_version"],
                        fbneo.FBNEO_SOURCE_COMMIT,
                        arch,
                    )
                )
                self.assertTrue(
                    pipeline.compile_log_proves_definitions(
                        log,
                        (
                            []
                            if arch == "arm64"
                            else fbneo.FBNEO_ARMHF_COMPILE_DEFINITIONS
                        ),
                        arch,
                    )
                )

    def test_shared_version_log_proof_rejects_marker_and_scope_drift(
        self,
    ) -> None:
        log = version_log("armhf")
        markers = fbneo.FBNEO_NATIVE_GIT_VERSION_MARKERS
        c_line = next(line for line in log.splitlines() if "source.c " in line)
        cxx_line = next(
            line for line in log.splitlines() if "source.cpp " in line
        )
        mutations = {
            "missing-version-build-arg": log.replace(
                markers[0] + "\n", "", 1
            ),
            "missing-date-build-arg": log.replace(markers[1] + "\n", "", 1),
            "duplicate-version-marker": log.replace(
                markers[3] + "\n", markers[3] + "\n" + markers[3] + "\n", 1
            ),
            "reordered-version-date-markers": log.replace(
                markers[3] + "\n" + markers[4] + "\n",
                markers[4] + "\n" + markers[3] + "\n",
                1,
            ),
            "markers-after-first-compile": log.replace(
                c_line + "\n", "", 1
            ).replace(markers[0] + "\n", c_line + "\n" + markers[0] + "\n", 1),
            "missing-version-token": log.replace(
                cxx_line,
                cxx_line.replace(
                    " " + fbneo.FBNEO_GIT_VERSION_LOG_TOKEN, "", 1
                ),
                1,
            ),
            "wrong-date-token": log.replace(
                cxx_line,
                cxx_line.replace('260503', '260504', 1),
                1,
            ),
            "duplicate-date-token": log.replace(
                cxx_line,
                cxx_line.replace(
                    fbneo.FBNEO_GIT_DATE_LOG_TOKEN,
                    (
                        fbneo.FBNEO_GIT_DATE_LOG_TOKEN
                        + " "
                        + fbneo.FBNEO_GIT_DATE_LOG_TOKEN
                    ),
                    1,
                ),
                1,
            ),
            "version-on-c-compile": log.replace(
                c_line,
                c_line.replace(
                    " -O2",
                    " " + fbneo.FBNEO_GIT_VERSION_LOG_TOKEN + " -O2",
                    1,
                ),
                1,
            ),
        }
        for label, changed in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    pipeline.git_version_log_proves_contract(
                        changed,
                        self.spec["build"]["git_version"],
                        fbneo.FBNEO_SOURCE_COMMIT,
                        "armhf",
                    )
                )

        wrong_scope = copy.deepcopy(self.spec["build"]["git_version"])
        wrong_scope["compiler_scope"] = "c"
        self.assertFalse(
            pipeline.git_version_log_proves_contract(
                log, wrong_scope, fbneo.FBNEO_SOURCE_COMMIT, "armhf"
            )
        )

    def test_armhf_header_definition_drift_fails_its_independent_proof(
        self,
    ) -> None:
        log = version_log("armhf")
        changed = log.replace("-DHWCAP2_AES=1", "-DHWCAP2_AES=2", 1)
        self.assertTrue(
            pipeline.git_version_log_proves_contract(
                changed,
                self.spec["build"]["git_version"],
                fbneo.FBNEO_SOURCE_COMMIT,
                "armhf",
            )
        )
        self.assertFalse(
            pipeline.compile_log_proves_definitions(
                changed,
                fbneo.FBNEO_ARMHF_COMPILE_DEFINITIONS,
                "armhf",
            )
        )

    def test_build_shell_scopes_makeflags_to_one_command(self) -> None:
        shell = fbneo.fbneo_build_shell(self.spec, "fbneo", "arm64")
        lines = shell.splitlines()
        self.assertEqual(
            "printf '%s\\n' "
            "'CORE_PIPELINE_SOURCE_IDENTITY|fbneo|"
            "9d7716aa20cbdf49024f42980c33c7cd366e784f|"
            "e533af34d2db18f11cefadbb93e509579580d0b7|catalog'",
            lines[0],
        )
        self.assertEqual(
            "MAKEFLAGS='-- GIT_VERSION=9d7716aa2 "
            "GIT_DATE=260503 HIDE=' ./libretro-build.sh fbneo",
            lines[-2],
        )
        self.assertEqual(
            "printf '%s\\n' "
            "'CORE_PIPELINE_FBNEO_BUILD_END|arm64'",
            lines[-1],
        )
        self.assertEqual(1, shell.count("./libretro-build.sh fbneo"))
        self.assertNotIn("export MAKEFLAGS", shell)
        self.assertNotIn("\nMAKEFLAGS=", "\n".join(lines[:-2]))
        self.assertIn(fbneo.FBNEO_RECIPE_MARKER, shell)
        self.assertIn(fbneo.FBNEO_BUILD_BEGIN_MARKER["arm64"], shell)

    def test_build_shell_rejects_ambiguous_or_wrong_inputs(self) -> None:
        wrong_spec = copy.deepcopy(self.spec)
        wrong_spec["source"]["commit"] = "0" * 40
        cases = (
            (wrong_spec, "fbneo", "arm64"),
            (self.spec, "fbneo_alias", "arm64"),
            (self.spec, "fbneo", "x86_64"),
            (None, "fbneo", "arm64"),
        )
        for spec, source_key, arch in cases:
            with self.subTest(source_key=source_key, arch=arch):
                with self.assertRaises(PipelineError):
                    fbneo.fbneo_build_shell(spec, source_key, arch)
        with self.assertRaises(PipelineError):
            fbneo.fbneo_command_scoped_makeflags(wrong_spec)

    def test_golden_source_requires_full_identity_and_no_submodules(self) -> None:
        source = golden_source()
        self.assertTrue(
            fbneo.fbneo_golden_source_is_well_formed("fbneo", source)
        )
        mutations = {
            "core": ("other", source),
            "url": ("fbneo", {**source, "url": source["url"][:-4]}),
            "commit": ("fbneo", {**source, "commit": "0" * 40}),
            "resolved": (
                "fbneo",
                {**source, "resolved_commit": "0" * 40},
            ),
            "tree": ("fbneo", {**source, "tree": "0" * 40}),
            "submodule": (
                "fbneo",
                {
                    **source,
                    "submodules": [
                        {
                            "state": " ",
                            "commit": "0" * 40,
                            "path": "vendor",
                        }
                    ],
                },
            ),
            "extra": ("fbneo", {**source, "extra": True}),
        }
        for label, (core_id, changed) in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    fbneo.fbneo_golden_source_is_well_formed(
                        core_id, changed
                    )
                )

    def test_golden_build_requires_exact_shape_and_registers_the_oracle(self) -> None:
        source = golden_source()
        for arch in ("arm64", "armhf"):
            with self.subTest(arch=arch):
                build = golden_build(arch)
                self.assertTrue(
                    fbneo.fbneo_golden_build_contract_is_well_formed(
                        build,
                        fbneo.FBNEO_SOURCE_COMMIT,
                        "fbneo",
                        source,
                        arch,
                    )
                )

        build = golden_build("arm64")
        mutations = {
            "driver": {**build, "driver": "direct-make"},
            "environment": {**build, "environment": "inherited"},
            "definitions": {
                **build,
                "compile_definitions": ["SYNTHETIC=1"],
            },
            "version": {
                **build,
                "git_version": {
                    **build["git_version"],
                    "git_date": "260504",
                },
            },
            "epoch": {**build, "source_date_epoch": 0},
            "log": {**build, "log": "other.log"},
            "digest-shape": {**build, "log_sha256": "a" * 63},
            "extra": {**build, "artifact_sha256": "a" * 64},
        }
        for label, changed in mutations.items():
            with self.subTest(mutation=label):
                self.assertFalse(
                    fbneo.fbneo_golden_build_contract_is_well_formed(
                        changed,
                        fbneo.FBNEO_SOURCE_COMMIT,
                        "fbneo",
                        source,
                        "arm64",
                    )
                )
        self.assertFalse(
            fbneo.fbneo_golden_build_contract_is_well_formed(
                golden_build("arm64"),
                "0" * 40,
                "fbneo",
                source,
                "arm64",
            )
        )
        self.assertFalse(
            fbneo.fbneo_golden_build_contract_is_well_formed(
                build,
                fbneo.FBNEO_SOURCE_COMMIT,
                "fbneo",
                source,
                "x86_64",
            )
        )
        self.assertFalse(
            fbneo.fbneo_golden_build_contract_is_well_formed(
                golden_build("arm64"),
                fbneo.FBNEO_SOURCE_COMMIT,
                "fbneo",
                source,
                "armhf",
            )
        )

        # The mixed-language compile/link oracle is now registered from fresh
        # reproducible controls.
        self.assertTrue(hasattr(fbneo, "fbneo_log_proves_contract"))
        contract = core_log_contract_for(fbneo.FBNEO_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("fbneo-mixed-language-v1", contract.contract_id)
        self.assertEqual(
            "fbneo_log_proves_contract", contract.proof_name
        )
        self.assertEqual(frozenset({fbneo.FBNEO_CORE_ID}), contract.core_ids)


if __name__ == "__main__":
    unittest.main()
