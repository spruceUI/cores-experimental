"""Render the script that builds one core for one arch in its toolchain image.

Per-core behaviour is catalog data (docs/catalog.md); this file is one template per driver.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from .variants import Variant

SCRUBBED = (
    "CFLAGS CXXFLAGS CPPFLAGS LDFLAGS ASMFLAGS ASFLAGS MAKE MAKEFLAGS GNUMAKEFLAGS "
    "MAKEFILES MAKEOVERRIDES MFLAGS GIT_VERSION EMULATOR_BUILD HAS_GPU IS_X86 "
    "USE_BLARGG_APU ARCH ARCH_AARCH64 ARCH_ARM ARCH_X86 ARCH_X86_64 HAVE_SSA "
    "LIBRETRO_EMBED_FFMPEG OPENGL CMAKE_TOOLCHAIN_FILE SOURCE_DATE_EPOCH CMAKE_GENERATOR "
    "CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET CMAKE_BUILD_PARALLEL_LEVEL "
    "GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM GIT_CONFIG_GLOBAL "
    "GIT_CONFIG_NOSYSTEM GIT_CONFIG"
)
CARGO_SCRUBBED = "RUSTFLAGS RUSTC RUSTC_WRAPPER CARGO_BUILD_RUSTFLAGS CARGO_ENCODED_RUSTFLAGS"
CMAKE_PROCESSOR = {"arm64": "aarch64", "armhf": "arm"}
QEMU = {"arm64": "qemu-aarch64", "armhf": "qemu-arm"}
SOURCE = "/tmp/core-source"
TEMPLATE = re.compile(r"\{commit:(\d+)\}")


@dataclass
class Script:
    text: str
    # read-only mounts: (path relative to the repo, path in the container)
    mounts: list[tuple[str, str]] = field(default_factory=list)


def q(value: object) -> str:
    return shlex.quote(str(value))


def fill(value: str, commit: str) -> str:
    """Expand {commit:N} to the first N characters of the pinned commit."""
    return TEMPLATE.sub(lambda match: commit[: int(match.group(1))], value)


def toolchain_for(spec: dict, arch: str) -> str:
    return "rust" if spec["build"]["driver"] == "direct-cargo" else arch


def render(core: str, spec: dict, arch: str, variant: Variant | None = None) -> Script:
    build = spec["build"]
    driver = build["driver"]
    if arch not in spec["targets"]:
        raise ValueError(f"{core} does not target {arch}")
    lines = prelude(cargo=driver == "direct-cargo")
    definitions = build.get("compile_definitions", {}).get(arch, [])
    if definitions:
        flags = q(" ".join("-D" + item for item in definitions))
        lines += [f"export CFLAGS={flags}", f"export CXXFLAGS={flags}"]
    if variant is not None and not variant.is_baseline:
        lines += cargo_variant(variant) if driver == "direct-cargo" else wrapper(variant)

    mounts = [(o["patch"], f"/recipe-overlays/{i}.patch") for i, o in enumerate(build.get("overlays", {}).get(arch, []))]
    if driver == "libretro-super":
        body = libretro_super(spec, arch)
    elif driver == "direct-make":
        body = direct_make(spec, arch)
    elif driver == "direct-cmake":
        body = direct_cmake(spec, arch)
    elif driver == "direct-cargo":
        body = direct_cargo(spec, arch)
    else:
        raise ValueError(f"{core}: unknown driver {driver}")
    lines += body

    metadata = spec["metadata"]
    name = q(metadata["artifact_name"])
    if "repo_path" in metadata:
        mounts.append((metadata["repo_path"], f"/metadata-repo/{metadata['artifact_name']}"))
        lines.append(f"install -m 0644 /metadata-repo/{name} /output/{name}")
    else:
        source = q(metadata["source_path"])
        lines += [f"test -s {source}", f"install -m 0644 {source} /output/{name}"]

    if driver == "direct-cargo":
        lines += ["rustc --version > /output/compiler.txt", "zig version > /output/sysroot.txt"]
    else:
        lines += [
            '"$CC" --version | head -n 1 > /output/compiler.txt',
            '"$CC" -print-sysroot > /output/sysroot.txt',
        ]
        mounts.append(("runtime/smoke_loader.c", "/smoke/smoke_loader.c"))
        lines += smoke(spec, arch)
    lines.append('chown "$OUTPUT_UID:$OUTPUT_GID" /output/*')
    return Script("\n".join(lines) + "\n", mounts)


def prelude(cargo: bool) -> list[str]:
    scrubbed = SCRUBBED + (" " + CARGO_SCRUBBED if cargo else "")
    extra = "|CARGO_TARGET_*_RUSTFLAGS" if cargo else ""
    lines = [
        "set -Eeuo pipefail",
        "export LC_ALL=C",
        "export LANG=C",
        "umask 022",
        f"unset {scrubbed}",
        "while IFS='=' read -r core_pipeline_environment_name _; do",
        '  case "$core_pipeline_environment_name" in',
        f'    GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*{extra}) unset "$core_pipeline_environment_name" ;;',
        "  esac",
        "done < <(env)",
    ]
    if cargo:
        tools = "cargo rustc zig cargo-zigbuild git"
    else:
        lines += [
            'export CC="${HOST_CC}-gcc"',
            'export CXX="${HOST_CC}-g++"',
            'export AR="${HOST_CC}-ar"',
            'export RANLIB="${HOST_CC}-ranlib"',
            'export STRIP="${HOST_CC}-strip"',
            'export CROSS_COMPILE="${HOST_CC}-"',
            'export CHOST="${HOST_CC}"',
        ]
        tools = '"$CC" "$CXX" "$AR" "$RANLIB" "$STRIP"'
    return lines + [f"for tool in {tools}; do", '  command -v "$tool" >/dev/null', "done"]


def wrapper(variant: Variant) -> list[str]:
    """Shadow the cross compilers so the variant flags come last on every call.

    GCC honours the last -O and machine flag; each call is logged to /output."""
    flags = " ".join(q(flag) for flag in variant.flags)
    return [
        'cores_cc_real="$(command -v "$CC")"',
        "mkdir -p /tmp/cores-variant",
        ": > /output/variant-calls.log",
        "cores_wrap() {",
        '  cores_real="$(command -v "$1")" || return 0',
        "  printf '%s\\n' '#!/bin/sh' 'printf \"%s\\n\" \"$*\" >> /output/variant-calls.log' "
        f'"exec $cores_real \\"\\$@\\" {flags}" > "/tmp/cores-variant/$1"',
        '  chmod 0755 "/tmp/cores-variant/$1"',
        "}",
        'for cores_tool in "$CC" "$CXX" "${HOST_CC}-c++" "${HOST_CC}-cc"; do',
        '  cores_wrap "$cores_tool"',
        "done",
        'export PATH="/tmp/cores-variant:$PATH"',
        f"printf 'cores variant %s: %s\\n' {q(variant.name)} {q(' '.join(variant.flags))}",
    ]


def cargo_variant(variant: Variant) -> list[str]:
    return [f"export CARGO_PROFILE_RELEASE_{key.upper().replace('-', '_')}={q(value)}"
            for key, value in variant.cargo]


def checkout_libretro(directory: str, commit: str, submodules: bool, recursive: str) -> list[str]:
    lines = [
        f"if ! git -C {directory} cat-file -e {commit}^{{commit}} 2>/dev/null; then",
        f"  git -C {directory} fetch --force origin {commit}",
        "fi",
        f"git -C {directory} checkout --detach {commit}",
    ]
    if submodules:
        lines += [
            f"git -C {directory} submodule sync{recursive}",
            f"git -C {directory} submodule update --init{recursive}",
        ]
    return lines + [f'test "$(git -C {directory} rev-parse HEAD)" = {commit}']


def checkout_direct(url: str, commit: str, recursive: str) -> list[str]:
    return [
        f"mkdir {SOURCE}",
        f"git -C {SOURCE} init",
        f"git -C {SOURCE} remote add origin {q(url)}",
        f"git -C {SOURCE} fetch --depth 1 origin {commit}",
        f"git -C {SOURCE} checkout --detach FETCH_HEAD",
        f'test "$(git -C {SOURCE} rev-parse HEAD)" = {commit}',
        f"git -C {SOURCE} submodule sync{recursive}",
        f"git -C {SOURCE} submodule update --init{recursive}",
    ]


def provenance(directory: str, submodules: bool, recursive: str) -> list[str]:
    if submodules:
        record = f"git -C {directory} submodule status{recursive} > /output/submodules.txt"
    else:
        # `submodule status` fails on a gitlink with no .gitmodules entry.
        record = (f"git -C {directory} ls-tree -r HEAD "
                  "| awk '$2 == \"commit\" { print \" \" $3, $4 }' > /output/submodules.txt")
    return [
        f"git -C {directory} rev-parse HEAD > /output/source-commit.txt",
        f"git -C {directory} rev-parse HEAD^{{tree}} > /output/source-tree.txt",
        f"git -C {directory} remote get-url origin > /output/source-url.txt",
        record,
    ]


def environment(spec: dict, directory: str) -> list[str]:
    build, commit = spec["build"], spec["source"]["commit"]
    lines = []
    if build.get("source_date_epoch"):
        lines.append(f'export SOURCE_DATE_EPOCH="$(git -C {directory} show -s --format=%ct HEAD)"')
    if build.get("git_abbrev"):
        # Short hashes baked in by the makefile must not grow with the upstream repo.
        abbrev = int(build["git_abbrev"])
        lines += ["export GIT_CONFIG_SYSTEM=/dev/null", "export GIT_CONFIG_GLOBAL=/dev/null",
                  f"export GIT_CONFIG_PARAMETERS=\"'core.abbrev={abbrev}'\""]
    lines += [f"export {name}={q(fill(value, commit))}" for name, value in build.get("env", [])]
    if "makeflags" in build:
        lines.append(f"export MAKEFLAGS={q(fill(build['makeflags'], commit))}")
    return lines


def overlays(build: dict, arch: str, root: str) -> list[str]:
    lines = []
    for index, overlay in enumerate(build.get("overlays", {}).get(arch, [])):
        patch = f"/recipe-overlays/{index}.patch"
        target, strip = root, ""
        if overlay.get("submodule"):
            target = f"{root}/{overlay['submodule']}"
            strip = f" -p{1 + overlay['submodule'].count('/') + 1}"
        lines += [
            f"git -C {q(target)} apply{strip} --check --whitespace=error-all {patch}",
            f"git -C {q(target)} apply{strip} --whitespace=error-all {patch}",
        ]
    return lines


def install(path: str, artifact: str) -> list[str]:
    return [f"test -s {q(path)}", f"install -m 0644 {q(path)} /output/{q(artifact)}"]


def flags(build: dict) -> tuple[bool, str]:
    submodules = build.get("submodules", True)
    recursive = "" if build.get("recursive_submodules") is False else " --recursive"
    return submodules, recursive


def libretro_super(spec: dict, arch: str) -> list[str]:
    build, commit = spec["build"], spec["source"]["commit"]
    directory, key = build["source_dir"], build["source_key"]
    submodules, recursive = flags(build)
    output = build["output_path"]
    command = build.get("command")
    if isinstance(command, dict):
        command = command[arch]
    if command is None:
        prefix = "".join(f"{name}={q(fill(value, commit))} " for name, value in build.get("command_env", []))
        command = [f"{prefix}./libretro-build.sh {key}"]
    command = [fill(line, commit) for line in command]
    return [
        "cd /libretro-super",
        f"./libretro-fetch.sh {key}",
        *checkout_libretro(directory, commit, submodules, recursive),
        *provenance(directory, submodules, recursive),
        *environment(spec, directory),
        *overlays(build, arch, directory),
        f"rm -f {q(output)}",
        *command,
        *install(output, build["artifact_name"]),
    ]


def direct_make(spec: dict, arch: str) -> list[str]:
    build, commit = spec["build"], spec["source"]["commit"]
    _, recursive = flags(build)
    args = ""
    if build.get("make_subdir"):
        args += f"-C {q(build['make_subdir'])} "
    if "platforms" in build:
        args += f"platform={q(build['platforms'][arch])} "
    args += "".join(f"{q(item)} " for item in build.get("make_args", []))
    output = build["output_path"]
    return [
        *checkout_direct(spec["source"]["url"], commit, recursive),
        *provenance(SOURCE, True, recursive),
        *environment(spec, SOURCE),
        *overlays(build, arch, SOURCE),
        f"cd {SOURCE}",
        f"rm -f {q(output)}",
        f'make -j"$(nproc)" {args}CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB"',
        *install(output, build["artifact_name"]),
    ]


def direct_cmake(spec: dict, arch: str) -> list[str]:
    build, commit = spec["build"], spec["source"]["commit"]
    cmake = build["cmake"]
    source = SOURCE + (f"/{cmake['source_subdir']}" if cmake.get("source_subdir") else "")
    defines = {**cmake.get("defines", {}), **cmake.get("arch_defines", {}).get(arch, {})}
    tools = "".join(
        f' -DCMAKE_{name}:FILEPATH="$cmake_{var}"'
        for name, var in (("C_COMPILER", "cc"), ("CXX_COMPILER", "cxx"), ("AR", "ar"),
                          ("RANLIB", "ranlib"), ("STRIP", "strip"))
    )
    configure = (
        f"cmake -S {q(source)} -B /tmp/core-build -G 'Unix Makefiles' "
        "-DCMAKE_BUILD_TYPE:STRING=Release -DCMAKE_SYSTEM_NAME:STRING=Linux "
        f"-DCMAKE_SYSTEM_PROCESSOR:STRING={CMAKE_PROCESSOR[arch]}{tools}"
        + "".join(f" -D{name}={q(value)}" for name, value in defines.items())
    )
    return [
        *checkout_direct(spec["source"]["url"], commit, " --recursive"),
        *provenance(SOURCE, True, " --recursive"),
        *environment(spec, SOURCE),
        *overlays(build, arch, SOURCE),
        *(f'cmake_{var}="$(command -v "${env}")"' for var, env in
          (("cc", "CC"), ("cxx", "CXX"), ("ar", "AR"), ("ranlib", "RANLIB"), ("strip", "STRIP"))),
        configure,
        f'cmake --build /tmp/core-build --target {q(cmake["target"])} --parallel "$(nproc)" --verbose',
        *install(f"/tmp/core-build/{build['output_path']}", build["artifact_name"]),
    ]


def direct_cargo(spec: dict, arch: str) -> list[str]:
    build, commit = spec["build"], spec["source"]["commit"]
    cargo = build["cargo"]
    triple = cargo["targets"][arch]
    product = f"{SOURCE}/target/{triple.split('.')[0]}/release/{build['output_path']}"
    return [
        *checkout_direct(spec["source"]["url"], commit, ""),
        *provenance(SOURCE, True, " --recursive"),
        *environment(spec, SOURCE),
        *overlays(build, arch, SOURCE),
        "export CARGO_HOME=/tmp/cargo-home",
        f"cd {q(SOURCE + '/' + cargo['subdir'])}",
        f"rm -f {q(product)}",
        f"cargo zigbuild --locked --target {q(triple)} --release",
        *install(product, build["artifact_name"]),
    ]


def smoke(spec: dict, arch: str) -> list[str]:
    """Load the core under qemu and run its content-free init sequence."""
    artifact = q(spec["build"]["artifact_name"])
    return [
        # RetroArch has libm and libpthread loaded; some cores rely on that instead of linking them.
        '"${cores_cc_real:-$CC}" -O0 -o /tmp/smoke-loader /smoke/smoke_loader.c -Wl,--no-as-needed -lm -lpthread -ldl',
        f"timeout 300 {QEMU[arch]} /tmp/smoke-loader /output/{artifact} > /output/smoke.txt 2>&1"
        ' || printf "exit %s\\n" "$?" >> /output/smoke.txt',
    ]
