from __future__ import annotations

import copy
from pathlib import Path
import unittest

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import vecx
from core_pipeline_lib.contracts.registry import core_log_contract_for


ROOT = Path(__file__).resolve().parents[1]
ORACLE_FIXTURE = pipeline.load_json(
    ROOT / "tests/fixtures/per-core-oracles/vecx.json"
)
POSITIVE_RUNS = tuple(
    run["run_id"] for run in ORACLE_FIXTURE["positive_runs"]
)


def build_vecx_log_fixture(architecture: str) -> str:
    """Build a small exact log independent of ignored workspace evidence."""

    compiler = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }[architecture]
    compile_options = (
        vecx.VECX_NATIVE_GIT_VERSION_LOG_TOKEN,
        "-O2",
        "-DNDEBUG",
        "-D__LIBRETRO__",
        "-DHAVE_STRINGS_H",
        "-DHAVE_STDINT_H",
        "-DHAVE_INTTYPES_H",
        "-DINLINE=inline",
        "-Wall",
        "-W",
        "-Wno-unused-parameter",
        "-Wno-sign-compare",
        "-Wno-uninitialized",
        "-fPIC",
        "-DFRONTEND_SUPPORTS_RGB565",
        "-I.",
        "-I./libretro-common/include",
    )
    pairs = (
        ("e6809.o", "e6809.c"),
        ("vecx_psg.o", "vecx_psg.c"),
        ("libretro.o", "libretro.c"),
        ("vecx.o", "vecx.c"),
    )
    compile_lines = [
        " ".join(
            (
                compiler,
                *compile_options,
                "-c",
                f"-o{output}",
                source,
            )
        )
        for output, source in pairs
    ]
    link_line = " ".join(
        (
            compiler,
            "-ovecx_libretro.so",
            *vecx.VECX_EXPECTED_LINK_OPTIONS[:-1],
            "./e6809.o",
            "./vecx_psg.o",
            "./libretro.o",
            "./vecx.o",
            vecx.VECX_EXPECTED_LINK_OPTIONS[-1],
        )
    )
    return (
        "\n".join(
            (
                vecx.VECX_SOURCE_HEAD_MARKER,
                *vecx.VECX_MAKE_MARKERS,
                vecx.VECX_NATIVE_VERSION_MARKER,
                *compile_lines,
                link_line,
                vecx.VECX_METADATA_REPLACEMENT_MARKER,
            )
        )
        + "\n"
    )


class VecxLogContractTests(unittest.TestCase):
    def contract_arguments(
        self, build_log_text: str, architecture: str = "arm64"
    ) -> tuple[str, str, str, str, str]:
        identity = vecx.VECX_SOFTWARE_SPEC_IDENTITY
        return (
            build_log_text,
            vecx.VECX_CORE_ID,
            architecture,
            identity["source_commit"],
            identity["source_tree"],
        )

    def test_registry_identity_is_owned_by_vecx(self) -> None:
        contract = core_log_contract_for(vecx.VECX_CORE_ID)
        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual("vecx-software-c-only-v1", contract.contract_id)
        self.assertEqual("vecx_log_proves_contract", contract.proof_name)
        self.assertEqual(frozenset({vecx.VECX_CORE_ID}), contract.core_ids)

    def test_exact_catalog_and_promoted_contracts_are_vecx_owned(self) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests/core-builds.json")
        spec = catalog["cores"][vecx.VECX_CORE_ID]
        identity = vecx.VECX_SOFTWARE_SPEC_IDENTITY
        self.assertTrue(vecx.vecx_software_spec_is_well_formed(spec))
        self.assertTrue(vecx.vecx_software_identity_is_well_formed(spec))
        self.assertIs(identity, pipeline.VECX_SOFTWARE_SPEC_IDENTITY)
        self.assertEqual(
            vecx.VECX_SOFTWARE_MAKE_VARIABLES,
            pipeline.validated_make_variables(spec),
        )
        self.assertEqual(
            vecx.VECX_METADATA_REPLACEMENT,
            pipeline.validated_metadata_replacement(spec),
        )
        self.assertTrue(
            pipeline.metadata_replacement_contract_is_well_formed(
                vecx.VECX_METADATA_REPLACEMENT
            )
        )

        source = {
            **spec["source"],
            "resolved_commit": identity["source_commit"],
            "resolved_url": identity["source_url"],
            "submodules": [],
        }
        build = {
            **pipeline.normalized_build_contract(spec, "arm64"),
            "log": "build.log",
            "log_sha256": "a" * 64,
        }
        self.assertTrue(
            vecx.vecx_software_golden_source_is_well_formed(
                vecx.VECX_CORE_ID, source
            )
        )
        self.assertTrue(
            vecx.vecx_combined_golden_build_contract_is_well_formed(
                build,
                identity["source_commit"],
                vecx.VECX_CORE_ID,
                source,
            )
        )
        for label, mutate in (
            (
                "source",
                lambda changed_source, _build: changed_source.update(
                    {"tree": "0" * 40}
                ),
            ),
            (
                "make",
                lambda _source, changed_build: changed_build[
                    "make_variables"
                ].update({"HAS_GPU": 1}),
            ),
            (
                "version",
                lambda _source, changed_build: changed_build[
                    "git_version"
                ].update({"value": " 0000000"}),
            ),
            (
                "metadata",
                lambda _source, changed_build: changed_build[
                    "metadata_replacement"
                ].update({"replacement_sha256": "b" * 64}),
            ),
            (
                "extra",
                lambda _source, changed_build: changed_build.update(
                    {"extra": True}
                ),
            ),
        ):
            changed_source = copy.deepcopy(source)
            changed_build = copy.deepcopy(build)
            mutate(changed_source, changed_build)
            with self.subTest(label=label):
                self.assertFalse(
                    vecx.vecx_combined_golden_build_contract_is_well_formed(
                        changed_build,
                        identity["source_commit"],
                        vecx.VECX_CORE_ID,
                        changed_source,
                    )
                )

    def test_synthetic_logs_prove_exact_contract_for_both_targets(self) -> None:
        for architecture in ("arm64", "armhf"):
            with self.subTest(architecture=architecture):
                log = build_vecx_log_fixture(architecture)
                arguments = self.contract_arguments(log, architecture)
                self.assertTrue(vecx.vecx_log_proves_contract(*arguments))
                self.assertTrue(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

    def test_synthetic_log_rejects_compile_link_and_diagnostic_mutations(
        self,
    ) -> None:
        baseline = build_vecx_log_fixture("arm64")
        lines = baseline.splitlines()
        compile_lines = [line for line in lines if " -c " in line]
        link_line = next(
            line for line in lines if " -ovecx_libretro.so " in line
        )
        metadata_line = vecx.VECX_METADATA_REPLACEMENT_MARKER
        mutations = {
            "missing-compile": baseline.replace(compile_lines[0] + "\n", "", 1),
            "duplicate-compile": baseline.replace(
                link_line, compile_lines[0] + "\n" + link_line, 1
            ),
            "cxx-substitution": baseline.replace(
                "aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"
            ),
            "missing-link-object": baseline.replace(" ./vecx.o", "", 1),
            "link-order": baseline.replace(
                "./e6809.o ./vecx_psg.o",
                "./vecx_psg.o ./e6809.o",
                1,
            ),
            "link-option-order": baseline.replace(
                "-fPIC -shared",
                "-shared -fPIC",
                1,
            ),
            "link-library-order": baseline.replace(
                "./e6809.o ./vecx_psg.o ./libretro.o ./vecx.o -lm",
                "-lm ./e6809.o ./vecx_psg.o ./libretro.o ./vecx.o",
                1,
            ),
            "link-script-order": baseline.replace(
                "-Wl,--version-script=./link.T ./e6809.o",
                "./e6809.o -Wl,--version-script=./link.T",
                1,
            ),
            "extra-link-object": baseline.replace(
                " ./vecx.o", " ./vecx.o ./extra.o", 1
            ),
            "extra-link-option": baseline.replace(" -lm\n", " -pthread -lm\n", 1),
            "wrong-output": baseline.replace(
                "-ovecx_libretro.so", "-oevil_libretro.so", 1
            ),
            "missing-head": baseline.replace(
                vecx.VECX_SOURCE_HEAD_MARKER + "\n", "", 1
            ),
            "wrong-head": baseline.replace("8f671cc", "0000000", 1),
            "duplicate-marker": vecx.VECX_MAKE_MARKERS[0] + "\n" + baseline,
            "metadata-before-build": baseline.replace(
                metadata_line + "\n", "", 1
            ).replace(
                vecx.VECX_NATIVE_VERSION_MARKER + "\n",
                vecx.VECX_NATIVE_VERSION_MARKER
                + "\n"
                + metadata_line
                + "\n",
                1,
            ),
            "gpu-macro": baseline.replace(" -c ", " -DHAS_GPU -c ", 1),
            "gl-link": baseline.replace(" -lm\n", " -lGL -lm\n", 1),
            "glsym-source": baseline.replace(
                "e6809.c", "libretro-common/glsym/glsym_gl.c", 1
            ),
            "warning": baseline + "warning: synthetic warning\n",
            "error": baseline + "error: synthetic error\n",
            "undefined": baseline + "undefined reference to synthetic\n",
            "make-failure": baseline + "make: *** [all] Error 2\n",
            "terminated": baseline + "Terminated\n",
            "bus-error": baseline + "Bus error\n",
            "illegal-instruction": baseline + "Illegal instruction\n",
        }
        for label, changed in mutations.items():
            arguments = self.contract_arguments(changed)
            with self.subTest(label=label):
                self.assertFalse(vecx.vecx_log_proves_contract(*arguments))
                self.assertFalse(
                    pipeline.registered_core_log_contract_proves(*arguments)
                )

    def test_source_and_architecture_boundaries_fail_closed(self) -> None:
        log = build_vecx_log_fixture("arm64")
        identity = vecx.VECX_SOFTWARE_SPEC_IDENTITY
        self.assertFalse(
            vecx.vecx_log_proves_contract(
                log,
                "freechaf",
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )
        self.assertFalse(
            vecx.vecx_log_proves_contract(
                log,
                vecx.VECX_CORE_ID,
                "armhf",
                identity["source_commit"],
                identity["source_tree"],
            )
        )
        self.assertFalse(
            vecx.vecx_log_proves_contract(
                log,
                vecx.VECX_CORE_ID,
                "arm64",
                "0" * 40,
                identity["source_tree"],
            )
        )

if __name__ == "__main__":
    unittest.main()
