from __future__ import annotations

from pathlib import Path
import shlex
import unittest

from scripts import core_pipeline as pipeline
from scripts.core_pipeline_lib.contracts import cap32
from scripts.core_pipeline_lib.errors import PipelineError


ROOT = Path(__file__).resolve().parents[1]
COMPILERS = {
    "arm64": "aarch64-linux-gnu-gcc",
    "armhf": "arm-a30-linux-gnueabihf-gcc",
}
CXX_COMPILERS = {
    "arm64": "aarch64-linux-gnu-g++",
    "armhf": "arm-a30-linux-gnueabihf-g++",
}
CURRENT_REAL_LOG_RUNS = (
    "actions-sim-build-core-cap32-w3",
    "build-core-cap32-local-w3",
)
CAP32_OBJECTS = (
    "libretro/libretro-core.o",
    "cap32/cap32.o",
    "cap32/slots.o",
    "cap32/crtc.o",
    "cap32/fdc.o",
    "cap32/psg.o",
    "cap32/tape.o",
    "cap32/cart.o",
    "cap32/asic.o",
    "cap32/z80.o",
    "cap32/kbdauto.o",
    "cap32/lightgun/gunstick.o",
    "cap32/lightgun/phaser.o",
    "libretro/microui/microui.o",
    "libretro/db/database.o",
    "libretro/dsk/loader.o",
    "libretro/dsk/format.o",
    "libretro/dsk/amsdos_catalog.o",
    "libretro/gfx/software.o",
    "libretro/gfx/video.o",
    "libretro/gfx/video8bpp.o",
    "libretro/gfx/video16bpp.o",
    "libretro/gfx/video24bpp.o",
    "libretro/assets/ui_keyboard_bg_crop.o",
    "libretro/assets/ui_keyboard_bg.o",
    "libretro/assets/ui_keyboard_en.o",
    "libretro/assets/ui_keyboard_es.o",
    "libretro/assets/ui_keyboard_fr.o",
    "libretro/assets/font.o",
    "libretro/retro_strings.o",
    "libretro/retro_utils.o",
    "libretro/retro_disk_control.o",
    "libretro/retro_events.o",
    "libretro/retro_snd.o",
    "libretro/retro_render.o",
    "libretro/retro_ui.o",
    "libretro/retro_gun.o",
    "libretro/retro_keyboard.o",
    "libretro-common/file/file_path.o",
    "libretro-common/string/stdstring.o",
    "libretro-common/compat/compat_strl.o",
    "libretro-common/encodings/encoding_utf.o",
    "libretro-common/time/rtime.o",
    "libretro-common/memmap/memalign.o",
)


def build_cap32_fixture(arch: str) -> dict:
    compiler = COMPILERS[arch]
    cxx_compiler = CXX_COMPILERS[arch]
    pairs = [
        (output, output.removesuffix(".o") + ".c")
        for output in CAP32_OBJECTS
    ]
    compile_lines = [
        shlex.join(
            (
                compiler,
                "-c",
                "-o",
                output,
                source,
                "-O3",
                f'-DGIT_VERSION="{cap32.CAP32_NATIVE_GIT_VERSION}"',
                "-fPIC",
                "-D__LIBRETRO__",
                "-DINLINE=inline",
                "-DHAVE_CONFIG_H",
                "-Wall",
                "-I.",
                "-I./cap32",
                "-I./libretro",
                "-I./libretro/microui",
                "-I./libretro-common/include",
            )
        )
        for output, source in pairs
    ]
    link_line = shlex.join(
        (
            compiler,
            "-o",
            cap32.CAP32_BUILD_ARTIFACT_NAME,
            *cap32.CAP32_EXPECTED_LINK_OPTIONS[:-1],
            *(f"./{output}" for output, _source in pairs),
            cap32.CAP32_EXPECTED_LINK_OPTIONS[-1],
        )
    )
    trace_lines = [
        (
            f"Makefile:485: update target '{output}' due to: "
            + (source if index % 2 == 0 else "target does not exist")
        )
        for index, (output, source) in enumerate(pairs)
    ]
    link_trace = (
        "Makefile:511: update target "
        f"'{cap32.CAP32_BUILD_ARTIFACT_NAME}' due to: "
        + " ".join(output for output, _source in pairs)
    )
    trace_order = [
        *range(1, len(pairs), 2),
        *range(0, len(pairs), 2),
    ]
    compile_order = list(reversed(range(len(pairs))))
    lines = [
        "configure: deterministic Cap32 fixture",
        cap32.CAP32_NATIVE_GIT_VERSION_MARKER,
        cap32.CAP32_MAKE_TRACE_MARKER,
    ]
    for position in range(len(pairs)):
        lines.extend(
            [
                trace_lines[trace_order[position]],
                f"make: parallel slot {position % 4}",
                compile_lines[compile_order[position]],
            ]
        )
    lines.extend(
        [link_trace, link_line, *cap32.CAP32_SUCCESS_TRAILER]
    )
    return {
        "compile_lines": compile_lines,
        "compiler": compiler,
        "cxx_compiler": cxx_compiler,
        "link_line": link_line,
        "link_trace": link_trace,
        "log": "\n".join(lines) + "\n",
        "pairs": pairs,
        "trace_lines": trace_lines,
    }


def build_cap32_log(arch: str) -> str:
    return build_cap32_fixture(arch)["log"]


class Cap32LogContractTests(unittest.TestCase):
    def test_identity_and_contract_are_owned_by_cap32(self) -> None:
        identity = cap32.CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY
        contract = cap32.CAP32_LOG_CONTRACT
        self.assertEqual("cap32", cap32.CAP32_CORE_ID)
        self.assertEqual(cap32.CAP32_CORE_ID, identity["source_key"])
        self.assertEqual(44, contract.expected_c_compile_count)
        self.assertEqual(44, len(CAP32_OBJECTS))
        self.assertEqual(identity["source_commit"], contract.source_commit)
        self.assertEqual(identity["source_tree"], contract.source_tree)
        exact = cap32.CAP32_EXACT_LOG_CONTRACT
        self.assertEqual(
            cap32.CAP32_EXPECTED_COMPILE_PAIR_SHA256,
            exact.expected_compile_pair_sha256,
        )
        self.assertEqual(
            cap32.CAP32_EXPECTED_COMPILE_INVOCATION_SHA256,
            exact.expected_compile_invocation_sha256,
        )
        self.assertEqual(
            cap32.CAP32_EXPECTED_LINK_OBJECT_SHA256,
            exact.expected_link_object_sha256,
        )
        self.assertEqual(
            cap32.CAP32_EXPECTED_RAW_LINK_OBJECT_SHA256,
            exact.expected_raw_link_object_sha256,
        )
        self.assertEqual(
            cap32.CAP32_EXPECTED_LINK_INVOCATION_SHA256,
            exact.expected_link_invocation_sha256,
        )
        self.assertIsNotNone(contract.make_trace)
        assert contract.make_trace is not None
        self.assertEqual(
            cap32.CAP32_MAKE_TRACE_MARKER, contract.make_trace.marker
        )

    def test_exact_log_is_accepted_for_each_architecture(self) -> None:
        identity = cap32.CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY
        for arch in COMPILERS:
            with self.subTest(arch=arch):
                self.assertTrue(
                    cap32.cap32_log_proves_contract(
                        build_cap32_log(arch),
                        cap32.CAP32_CORE_ID,
                        arch,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_current_workspace_logs_prove_exact_contract(self) -> None:
        identity = cap32.CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY
        paths = {
            (run_id, architecture): (
                ROOT
                / ".local-e2e"
                / "runs"
                / run_id
                / cap32.CAP32_CORE_ID
                / architecture
                / "build.log"
            )
            for run_id in CURRENT_REAL_LOG_RUNS
            for architecture in COMPILERS
        }
        if any(not path.is_file() for path in paths.values()):
            self.skipTest("workspace-local Cap32 logs are unavailable")
        for (run_id, architecture), path in paths.items():
            with self.subTest(run_id=run_id, architecture=architecture):
                self.assertTrue(
                    cap32.cap32_log_proves_contract(
                        path.read_text(encoding="utf-8"),
                        cap32.CAP32_CORE_ID,
                        architecture,
                        identity["source_commit"],
                        identity["source_tree"],
                    )
                )

    def test_build_shell_scopes_trace_and_sanitizes_make_environment(
        self,
    ) -> None:
        catalog = pipeline.load_catalog(ROOT / "manifests" / "core-builds.json")
        spec = catalog["cores"][cap32.CAP32_CORE_ID]
        build_shell = pipeline.libretro_build_shell(spec, cap32.CAP32_CORE_ID)
        self.assertIn(
            f"printf '%s\\n' '{cap32.CAP32_MAKE_TRACE_MARKER}'",
            build_shell,
        )
        self.assertIn(
            "MAKEFLAGS=--trace ./libretro-build.sh cap32", build_shell
        )
        self.assertNotIn("export MAKE", build_shell)

        prelude = pipeline.sanitized_shell_prelude()
        unset_line = next(
            line for line in prelude.splitlines() if line.startswith("unset ")
        )
        self.assertIn(" MAKE ", f" {unset_line} ")
        self.assertIn(" MAKEFLAGS ", f" {unset_line} ")

    def test_trace_compile_link_and_identity_contract_fail_closed(self) -> None:
        identity = cap32.CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY
        fixture = build_cap32_fixture("arm64")
        baseline = fixture["log"]
        arguments = (
            cap32.CAP32_CORE_ID,
            "arm64",
            identity["source_commit"],
            identity["source_tree"],
        )
        marker = cap32.CAP32_MAKE_TRACE_MARKER
        first_trace = fixture["trace_lines"][0]
        first_compile = fixture["compile_lines"][0]
        second_compile = fixture["compile_lines"][1]
        first_output, first_source = fixture["pairs"][0]
        second_output, _second_source = fixture["pairs"][1]
        native_marker = cap32.CAP32_NATIVE_GIT_VERSION_MARKER
        version_option = (
            f'-DGIT_VERSION="{cap32.CAP32_NATIVE_GIT_VERSION}"'
        )
        first_compile_tokens = shlex.split(first_compile)
        version_index = first_compile_tokens.index(version_option)
        missing_version = shlex.join(
            first_compile_tokens[:version_index]
            + first_compile_tokens[version_index + 1 :]
        )
        wrong_version_tokens = list(first_compile_tokens)
        wrong_version_tokens[version_index] = '-DGIT_VERSION=" rogue"'
        duplicate_version_tokens = list(first_compile_tokens)
        duplicate_version_tokens.insert(version_index, version_option)
        link_tokens = shlex.split(fixture["link_line"])
        first_link_object = link_tokens.index(f"./{first_output}")
        second_link_object = link_tokens.index(f"./{second_output}")
        reordered_link_tokens = list(link_tokens)
        reordered_link_tokens[first_link_object], reordered_link_tokens[
            second_link_object
        ] = (
            reordered_link_tokens[second_link_object],
            reordered_link_tokens[first_link_object],
        )
        reordered_option_tokens = list(link_tokens)
        first_option = reordered_option_tokens.index("-shared")
        second_option = reordered_option_tokens.index(
            "-Wl,-version-script=link.T"
        )
        reordered_option_tokens[first_option], reordered_option_tokens[
            second_option
        ] = (
            reordered_option_tokens[second_option],
            reordered_option_tokens[first_option],
        )
        success_trailer = "\n".join(cap32.CAP32_SUCCESS_TRAILER) + "\n"

        def before_success(line: str) -> str:
            return baseline.replace(
                success_trailer,
                line + "\n" + success_trailer,
                1,
            )

        mutations = {
            "missing-native-version": baseline.replace(
                native_marker + "\n", "", 1
            ),
            "wrong-native-version": baseline.replace(
                native_marker,
                native_marker.replace("4abfb8b", "0000000"),
                1,
            ),
            "duplicate-native-version": baseline.replace(
                native_marker + "\n",
                native_marker + "\n" + native_marker + "\n",
                1,
            ),
            "missing-marker": baseline.replace(marker + "\n", "", 1),
            "duplicate-marker": marker + "\n" + baseline,
            "late-marker": baseline.replace(marker + "\n", "", 1)
            + marker
            + "\n",
            "missing-compile-trace": baseline.replace(
                first_trace + "\n", "", 1
            ),
            "missing-link-trace": "\n".join(
                line
                for line in baseline.splitlines()
                if not line.startswith("Makefile:511:")
            )
            + "\n",
            "wrong-trace-line": baseline.replace(
                first_trace, first_trace.replace("Makefile:485", "Makefile:486")
            ),
            "wrong-trace-target": baseline.replace(
                first_trace,
                first_trace.replace(f"'{first_output}'", "'cpc/unexpected.o'"),
            ),
            "wrong-trace-source": baseline.replace(
                first_trace,
                first_trace.replace(first_source, "cpc/unexpected.c"),
            ),
            "wrong-link-trace-target": baseline.replace(
                fixture["link_trace"],
                fixture["link_trace"].replace(
                    "'cap32_libretro.so'", "'unexpected_libretro.so'"
                ),
            ),
            "link-trace-object-mismatch": baseline.replace(
                fixture["link_trace"],
                fixture["link_trace"].replace(
                    f" {first_output}", f" {second_output}", 1
                ),
                1,
            ),
            "compile-count-mismatch": baseline.replace(
                first_compile + "\n", "", 1
            ),
            "missing-compile-version": baseline.replace(
                first_compile, missing_version, 1
            ),
            "wrong-compile-version": baseline.replace(
                first_compile, shlex.join(wrong_version_tokens), 1
            ),
            "duplicate-compile-version": baseline.replace(
                first_compile, shlex.join(duplicate_version_tokens), 1
            ),
            "changed-compile-option": baseline.replace(
                first_compile,
                first_compile.replace(" -Wall ", " -Wextra ", 1),
                1,
            ),
            "injected-compile-definition": baseline.replace(
                first_compile,
                first_compile.replace(
                    " -fPIC ", " -DROGUE=1 -fPIC ", 1
                ),
                1,
            ),
            "duplicate-compile-pair": baseline.replace(
                second_compile, first_compile, 1
            ),
            "extra-source-operand": baseline.replace(
                first_compile,
                first_compile.replace(
                    f" {first_source} ",
                    f" {first_source} cpc/extra.c ",
                    1,
                ),
            ),
            "compiler-wrapper": baseline.replace(
                first_compile, "ccache " + first_compile, 1
            ),
            "compiler-path-wrapper": baseline.replace(
                first_compile,
                first_compile.replace(
                    fixture["compiler"], f"/tmp/{fixture['compiler']}", 1
                ),
                1,
            ),
            "target-cxx": baseline.replace(
                first_compile,
                first_compile.replace(
                    fixture["compiler"], fixture["cxx_compiler"], 1
                ),
                1,
            ),
            "response-file": baseline.replace(
                first_compile,
                first_compile.replace(" -O3 ", " @compiler.rsp -O3 ", 1),
                1,
            ),
            "forwarded-preprocessor-response": baseline.replace(
                first_compile,
                first_compile.replace(" -O3 ", " -Wp,@compiler.rsp -O3 ", 1),
                1,
            ),
            "explicit-language": baseline.replace(
                first_compile,
                first_compile.replace(" -O3 ", " -x c -O3 ", 1),
                1,
            ),
            "link-object-mismatch": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    f" ./{first_output}", f" ./{second_output}", 1
                ),
                1,
            ),
            "link-object-order": baseline.replace(
                fixture["link_line"], shlex.join(reordered_link_tokens), 1
            ),
            "link-option-order": baseline.replace(
                fixture["link_line"], shlex.join(reordered_option_tokens), 1
            ),
            "forwarded-linker-response": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,@link.rsp -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "forwarded-link-archive": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,cpc/rogue.a -shared ", 1
                ),
                1,
            ),
            "forwarded-link-arbitrary-input": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl,cpc/rogue.data -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object-wl-equals": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Wl=cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object-xlinker-equals": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Xlinker=cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "forwarded-link-object-xlinker-split": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -shared ", " -Xlinker cpc/rogue.o -shared ", 1
                ),
                1,
            ),
            "unexpected-link-library": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(
                    " -lm", " -l:rogue.a -L/tmp -lm", 1
                ),
                1,
            ),
            "unexpected-link-script": baseline.replace(
                fixture["link_line"],
                fixture["link_line"].replace(" -lm", " -Trogue.ld -lm", 1),
                1,
            ),
            "extra-warning": before_success(
                "rogue.c:1: warning: injected warning"
            ),
            "extra-note": before_success("rogue.c:1: note: injected note"),
            "compiler-error": before_success(
                "cc1: error: injected compiler failure"
            ),
            "linker-error": before_success(
                "collect2: error: ld returned 1 exit status"
            ),
            "make-error": before_success("make: *** [all] Error 2"),
            "extra-compiler-invocation": before_success(first_compile),
            "missing-success-trailer": baseline.replace(
                success_trailer, "", 1
            ),
            "wrong-success-core": baseline.replace("\tcap32\n", "\trogue\n", 1),
            "post-success-failure": baseline
            + "make: *** [all] Error 2\n"
            + "collect2: error: ld returned 1 exit status\n",
            "post-success-output": baseline + "unexpected tail\n",
        }
        for label, changed in mutations.items():
            with self.subTest(label=label):
                self.assertFalse(
                    cap32.cap32_log_proves_contract(changed, *arguments)
                )
        self.assertFalse(
            cap32.cap32_log_proves_contract(
                baseline,
                "crocods",
                "arm64",
                identity["source_commit"],
                identity["source_tree"],
            )
        )
        for label, commit, tree in (
            ("wrong-commit", "0" * 40, identity["source_tree"]),
            ("wrong-tree", identity["source_commit"], "0" * 40),
        ):
            with self.subTest(identity=label):
                self.assertFalse(
                    cap32.cap32_log_proves_contract(
                        baseline,
                        cap32.CAP32_CORE_ID,
                        "arm64",
                        commit,
                        tree,
                    )
                )
        with self.assertRaises(PipelineError):
            cap32.cap32_log_proves_contract(
                baseline,
                cap32.CAP32_CORE_ID,
                "unknown",
                identity["source_commit"],
                identity["source_tree"],
            )


if __name__ == "__main__":
    unittest.main()
