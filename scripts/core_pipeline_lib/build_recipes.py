"""Build recipe shell rendering and log-proof helpers.

The launcher remains the composition root. It supplies contract services and
repository I/O at each compatibility wrapper so existing patch seams remain
call-time bindings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import shlex

from .build_contracts import (
    COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS,
    ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS,
    MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS,
    NATIVE_GIT_DESCRIBE_DERIVATION,
    NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_DERIVATION,
    NATIVE_GIT_VERSION_SHORT10_DERIVATION,
    NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_SHORT8_DERIVATION,
    NATIVE_GIT_VERSION_SHORT9_DERIVATION,
    NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_SPEC_IDENTITIES,
    TARGET_CMAKE_TOOL_NAMES,
)
from .contracts.atari800 import ATARI800_CORE_ID
from .contracts.cap32 import CAP32_MAKE_TRACE_MARKER
from .contracts.fbneo import FBNEO_CORE_ID, FBNEO_GIT_VERSION_DERIVATION
from .contracts.fceumm import FCEUMM_CORE_ID
from .contracts.freeintv import (
    FREEINTV_CORE_ID,
    FREEINTV_SOURCE_IDENTITY_MARKER,
)
from .contracts.gambatte import GAMBATTE_CORE_ID
from .contracts.genesis_plus_gx import GENESIS_PLUS_GX_CORE_ID
from .contracts.genesis_plus_gx_wide import GENESIS_PLUS_GX_WIDE_CORE_ID
from .contracts.handy import HANDY_CORE_ID
from .contracts.mame2003_plus import (
    MAME2003_PLUS_CORE_ID,
    MAME2003_PLUS_SOURCE_IDENTITY_MARKER,
)
from .contracts.stella2014 import STELLA2014_CORE_ID
from .contracts.tgbdual import TGBDUAL_CORE_ID
from .contracts.vemulator import (
    VEMULATOR_CORE_ID,
    VEMULATOR_SOURCE_IDENTITY_MARKER,
)
from .errors import PipelineError
from .source_candidate import SourceCandidateContractProjection


@dataclass(frozen=True, slots=True)
class BuildRecipeServices:
    """Call-time launcher services needed by recipe rendering."""

    callables: Mapping[str, Callable[..., object]]


@dataclass(frozen=True, slots=True)
class BuildRecipeIO:
    """Repository-local services needed by recipe mount rendering."""

    repository_root: Path
    reference_path: Callable[[dict, Path, str], Path]
    sha256_file: Callable[[Path], str]
    safe_child: Callable[[Path, str, str], Path]


def compile_definition_shell(
    spec: dict,
    arch: str,
    tuning_profile_id: str | None = None,
    tuning_registry: Mapping[str, object] | None = None,
    *,
    services: BuildRecipeServices,
) -> str:
    """Export one combined catalog-definition and typed-tuning flag value."""

    definitions = services.callables["compile_definitions_for_target"](
        spec, arch
    )
    tuning = services.callables["execution_tuning_profile"](
        tuning_profile_id,
        arch,
        tuning_registry,
    )
    compiler_arguments = [] if tuning is None else tuning["compiler_arguments"]
    flags = [*(f"-D{definition}" for definition in definitions), *compiler_arguments]
    if not flags:
        return ""
    value = shlex.quote(" ".join(flags))
    return f"export CFLAGS={value}\nexport CXXFLAGS={value}"


def direct_cmake_assembly_tuning_shell(
    spec: dict,
    arch: str,
    tuning_profile_id: str | None = None,
    tuning_registry: Mapping[str, object] | None = None,
    *,
    services: BuildRecipeServices,
) -> str:
    """Export typed machine flags for direct-CMake assembly only.

    ``ASMFLAGS`` is a CMake-defined environment input that initializes the
    target assembler flags.  It is deliberately narrower than CFLAGS/CXXFLAGS:
    catalog compile definitions are C/C++ preprocessor contracts and must not
    leak into assembly.  Every build scrubs both conventional assembly flag
    variables in :func:`sanitized_shell_prelude`; only a nonempty, registry-
    owned direct-CMake tuning may restore ``ASMFLAGS``.  ``ASFLAGS`` remains
    unset for every driver.
    """

    build = spec.get("build")
    if not isinstance(build, dict) or build.get("driver") != "direct-cmake":
        return ""
    tuning = services.callables["execution_tuning_profile"](
        tuning_profile_id,
        arch,
        tuning_registry,
    )
    if tuning is None or not tuning["compiler_arguments"]:
        return ""
    return "export ASMFLAGS=" + shlex.quote(
        " ".join(tuning["compiler_arguments"])
    )


def chipset_tuning_marker_shell(tuning: dict | None) -> str:
    """Emit an exact, non-executable statement of the resolved tuning input."""

    if tuning is None:
        return ""
    marker = "CORE_PIPELINE_CHIPSET_TUNING|" + json.dumps(
        {
            "profile_id": tuning["profile_id"],
            "content_sha256": tuning["content_sha256"],
            "compiler_argument_mapping_version": tuning[
                "compiler_argument_mapping_version"
            ],
            "compiler_arguments": tuning["compiler_arguments"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"printf '%s\\n' {shlex.quote(marker)}"


def make_variable_log_markers(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> list[str]:
    variables = services.callables["validated_make_variables"](spec)
    return services.callables["make_variable_markers"](variables)


def command_scoped_native_git_version(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> str | None:
    core_id = spec.get("build", {}).get("source_key")
    if core_id not in {
        ATARI800_CORE_ID,
        GENESIS_PLUS_GX_CORE_ID,
        GENESIS_PLUS_GX_WIDE_CORE_ID,
        FCEUMM_CORE_ID,
        GAMBATTE_CORE_ID,
        TGBDUAL_CORE_ID,
        HANDY_CORE_ID,
        STELLA2014_CORE_ID,
    }:
        return None
    # Upstream uses an unqualified ``git rev-parse --short``.  Its width can
    # grow with unrelated objects, so the reviewed seven-character value must
    # be supplied by this sanitized command rather than rediscovered at build.
    contract = services.callables["validated_git_version"](spec)
    if (
        contract is None
        or contract.get("derivation") != NATIVE_GIT_VERSION_DERIVATION
        or spec.get("source", {}).get("commit")
        not in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
    ):
        raise PipelineError("command-scoped GIT_VERSION contract is invalid")
    return f'"{contract["value"]}"'


def libretro_build_shell(
    spec: dict,
    source_key: str,
    *,
    services: BuildRecipeServices,
) -> str:
    command_scoped_version = command_scoped_native_git_version(
        spec,
        services=services,
    )
    source_commit = spec.get("source", {}).get("commit")
    if (
        command_scoped_version is not None
        and source_commit in ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS
    ):
        return (
            f"GIT_VERSION={shlex.quote(command_scoped_version)} "
            f"./libretro-build.sh {source_key}"
        )
    if source_commit in MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS:
        if command_scoped_version is None:
            raise PipelineError("MAKEFLAGS-scoped GIT_VERSION contract is invalid")
        return f"./libretro-build.sh {source_key}"
    if not services.callables["native_git_version_spec_is_well_formed"](
        spec, "cap32"
    ):
        return f"./libretro-build.sh {source_key}"
    return "\n".join(
        [
            f"printf '%s\\n' {shlex.quote(CAP32_MAKE_TRACE_MARKER)}",
            f"MAKEFLAGS=--trace ./libretro-build.sh {source_key}",
        ]
    )


def make_variable_shell(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> str:
    variables = services.callables["validated_make_variables"](spec)
    if not variables:
        return ""
    profile = services.callables["make_variable_profile"](variables)
    if profile is None:
        raise PipelineError("build.make_variables has no supported profile")
    makefile_lines = [
        ".PHONY: core_pipeline_make_variable_origins",
        "core_pipeline_make_variable_origins:",
    ]
    for name in variables:
        marker = (
            f"CORE_PIPELINE_MAKE_VARIABLE|{name}|$({name})|$(origin {name})"
        )
        makefile_lines.append(
            "\t@printf '%s\\n' " + shlex.quote(marker)
        )
    makefile_text = "\n".join(makefile_lines)
    canonical = shlex.quote(services.callables["canonical_makeflags"](spec))
    probe_path = "/tmp/core-pipeline-make-variable-origins.mk"
    facts = services.callables["_make_variable_profile_facts"]()[profile]
    subdir = "/libretro" if facts.make_subdir_libretro else ""
    make_directory = shlex.quote(
        f"/libretro-super/{spec['build']['source_dir']}{subdir}"
    )
    makefile = facts.makefile
    return "\n".join(
        [
            f"export MAKEFLAGS={canonical}",
            "printf '%s\\n' \"CORE_PIPELINE_MAKEFLAGS|$MAKEFLAGS\"",
            f"printf '%s\\n' {shlex.quote(makefile_text)} > {probe_path}",
            (
                f"make --no-print-directory -s -C {make_directory} "
                f"-f {makefile} -f {probe_path} core_pipeline_make_variable_origins"
            ),
        ]
    )


def git_version_log_markers(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> list[str]:
    contract = services.callables["validated_git_version"](spec)
    if contract is None:
        return []
    return services.callables["git_version_markers"](
        contract, spec.get("source", {}).get("commit")
    )


def source_identity_log_markers(
    core_id: object,
    spec: object,
    *,
    services: BuildRecipeServices,
) -> list[str]:
    """Return exact log markers for source-native contracts without a macro."""

    if (
        core_id == MAME2003_PLUS_CORE_ID
        and services.callables["mame2003_plus_spec_is_well_formed"](spec)
    ):
        return [MAME2003_PLUS_SOURCE_IDENTITY_MARKER]
    if core_id == FREEINTV_CORE_ID and services.callables[
        "freeintv_spec_is_well_formed"
    ](spec):
        return [FREEINTV_SOURCE_IDENTITY_MARKER]
    if core_id == VEMULATOR_CORE_ID and services.callables[
        "vemulator_spec_is_well_formed"
    ](spec):
        return [VEMULATOR_SOURCE_IDENTITY_MARKER]
    return []


def source_identity_shell(
    core_id: object,
    spec: object,
    *,
    services: BuildRecipeServices,
) -> str:
    """Emit reviewed source identity after checkout for source-native cores."""

    return "\n".join(
        f"printf '%s\\n' {shlex.quote(marker)}"
        for marker in source_identity_log_markers(
            core_id,
            spec,
            services=services,
        )
    )


def git_version_shell(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> str:
    contract = services.callables["validated_git_version"](spec)
    if contract is None:
        return ""
    value = contract["value"]
    if contract["derivation"] == FBNEO_GIT_VERSION_DERIVATION:
        # FBNeo's exact wrapper emits both version/date origin markers and
        # keeps their MAKEFLAGS binding scoped to one build command.
        return ""
    if contract["derivation"] == NATIVE_GIT_VERSION_SHORT8_DERIVATION:
        # The exact MAME wrapper emits the origin markers and scopes MAKEFLAGS
        # to its single build command. Nothing may leak through the shared
        # environment before or after that command.
        return ""
    if contract["derivation"] in {
        NATIVE_GIT_VERSION_DERIVATION,
        NATIVE_GIT_VERSION_SHORT9_DERIVATION,
        NATIVE_GIT_VERSION_SHORT10_DERIVATION,
        NATIVE_GIT_DESCRIBE_DERIVATION,
    }:
        if contract["derivation"] == NATIVE_GIT_DESCRIBE_DERIVATION:
            identities = NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES
        elif contract["derivation"] == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
            identities = NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES
        elif contract["derivation"] == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
            identities = NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES
        else:
            identities = NATIVE_GIT_VERSION_SPEC_IDENTITIES
        identity = identities.get(spec.get("build", {}).get("source_key"))
        if identity is None:
            makefile_path = Path("Makefile.libretro")
        else:
            makefile_path = Path(identity["native_makefile"])
        makefile_text = "\n".join(
            [
                ".PHONY: core_pipeline_native_git_version_origin",
                "core_pipeline_native_git_version_origin:",
                (
                    "\t@printf '%s\\n' "
                    + shlex.quote(
                        "CORE_PIPELINE_NATIVE_GIT_VERSION|$(GIT_VERSION)|"
                        "$(origin GIT_VERSION)"
                    )
                ),
            ]
        )
        probe_path = "/tmp/core-pipeline-native-git-version-origin.mk"
        make_directory = shlex.quote(
            str(
                Path(f"/libretro-super/{spec['build']['source_dir']}")
                / makefile_path.parent
            )
        )
        makefile = shlex.quote(makefile_path.name)
        commands = []
        command_scoped_version = command_scoped_native_git_version(
            spec,
            services=services,
        )
        make_environment = ""
        if command_scoped_version is not None:
            markers = services.callables["git_version_markers"](
                contract, spec.get("source", {}).get("commit")
            )
            build_arg_marker = markers[0]
            commands.append(
                f"printf '%s\\n' {shlex.quote(build_arg_marker)}"
            )
            source_commit = spec.get("source", {}).get("commit")
            if source_commit in MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS:
                makeflags = f'-- GIT_VERSION="\\{value}"'
                commands.extend(
                    [
                        f"export MAKEFLAGS={shlex.quote(makeflags)}",
                        (
                            "printf '%s\\n' "
                            '"CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|'
                            '$MAKEFLAGS"'
                        ),
                    ]
                )
            else:
                make_environment = (
                    f"GIT_VERSION={shlex.quote(command_scoped_version)} "
                )
        if contract["derivation"] == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
            commands.extend(
                [
                    "export GIT_CONFIG_SYSTEM=/dev/null",
                    "export GIT_CONFIG_GLOBAL=/dev/null",
                    "export GIT_CONFIG_PARAMETERS=\"'core.abbrev=9'\"",
                    (
                        "core_pipeline_git_config_core_abbrev="
                        "\"$(git config --show-origin --get core.abbrev)\""
                    ),
                    (
                        "test \"$core_pipeline_git_config_core_abbrev\" = "
                        "\"$(printf 'command line:\\t9')\""
                    ),
                ]
            )
        if contract["derivation"] == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
            commands.extend(
                [
                    "export GIT_CONFIG_SYSTEM=/dev/null",
                    "export GIT_CONFIG_GLOBAL=/dev/null",
                    "export GIT_CONFIG_PARAMETERS=\"'core.abbrev=10'\"",
                    (
                        "core_pipeline_git_config_core_abbrev="
                        "\"$(git config --show-origin --get core.abbrev)\""
                    ),
                    (
                        "test \"$core_pipeline_git_config_core_abbrev\" = "
                        "\"$(printf 'command line:\\t10')\""
                    ),
                    (
                        "printf '%s\\n' "
                        "'CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV|command line:|10'"
                    ),
                ]
            )
        commands.extend(
            [
                f"printf '%s\\n' {shlex.quote(makefile_text)} > {probe_path}",
                (
                    f"{make_environment}make --no-print-directory -s "
                    f"-C {make_directory} "
                    f"-f {makefile} -f {probe_path} "
                    "core_pipeline_native_git_version_origin"
                ),
            ]
        )
        return "\n".join(commands)
    makefile_text = "\n".join(
        [
            ".PHONY: core_pipeline_git_version_origin",
            "core_pipeline_git_version_origin:",
            (
                "\t@printf '%s\\n' "
                + shlex.quote(
                    "CORE_PIPELINE_GIT_VERSION|$(GIT_VERSION)|"
                    "$(origin GIT_VERSION)"
                )
            ),
        ]
    )
    canonical = shlex.quote(f"GIT_VERSION={value}")
    probe_path = "/tmp/core-pipeline-git-version-origin.mk"
    return "\n".join(
        [
            f"export MAKEFLAGS={canonical}",
            (
                "printf '%s\\n' "
                f'"CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|$MAKEFLAGS"'
            ),
            f"printf '%s\\n' {shlex.quote(makefile_text)} > {probe_path}",
            (
                "make --no-print-directory -s "
                f"-f {probe_path} core_pipeline_git_version_origin"
            ),
        ]
    )


def source_date_epoch_shell(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> str:
    value = services.callables["validated_source_date_epoch"](spec)
    return "" if value is None else f"export SOURCE_DATE_EPOCH={value}"


def source_date_epoch_provenance_shell(
    source_dir: str,
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> str:
    expected = services.callables["validated_source_date_epoch"](spec)
    if expected is None:
        return ""
    directory = shlex.quote(source_dir)
    return f"""
actual_source_date_epoch="$(git -C {directory} show -s --format=%ct HEAD)"
printf "%s\\n" "$actual_source_date_epoch" > /output/source-date-epoch.txt
test "$actual_source_date_epoch" = {expected}
""".strip()


def direct_cmake_cache_log_document(
    spec: dict,
    arch: str,
    tool_paths: object,
    *,
    services: BuildRecipeServices,
) -> dict:
    contract = services.callables["direct_cmake_contract_for_target"](
        spec, arch
    )
    if contract is None:
        raise PipelineError("direct-CMake cache proof requires a direct-CMake core")
    expected_names = TARGET_CMAKE_TOOL_NAMES.get(arch)
    if not isinstance(tool_paths, dict) or expected_names is None:
        raise PipelineError("direct-CMake cache proof tool paths are invalid")
    if set(tool_paths) != set(expected_names):
        raise PipelineError("direct-CMake cache proof tool path set is invalid")
    normalized_paths: dict[str, str] = {}
    for role, expected_name in expected_names.items():
        path = tool_paths.get(role)
        if (
            not isinstance(path, str)
            or not re.fullmatch(r"/[A-Za-z0-9_+./-]+", path)
            or Path(path).as_posix() != path
            or any(part in {"", ".", ".."} for part in Path(path).parts[1:])
            or Path(path).name != expected_name
        ):
            raise PipelineError(
                f"direct-CMake cache proof {role} tool path is invalid"
            )
        normalized_paths[role] = path
    return {
        "build_type": contract["cmake"]["build_type"],
        "generator": contract["cmake"]["generator"],
        "system": copy.deepcopy(contract["cmake"]["system"]),
        "tools": normalized_paths,
    }


def direct_cmake_log_markers(
    spec: dict,
    arch: str,
    tool_paths: object | None = None,
    *,
    services: BuildRecipeServices,
) -> list[str]:
    contract = services.callables["direct_cmake_contract_for_target"](
        spec, arch
    )
    if contract is None:
        return []
    markers: list[str] = []
    for overlay in contract["overlays"]:
        rendered = json.dumps(overlay, sort_keys=True, separators=(",", ":"))
        markers.extend(
            [
                "CORE_PIPELINE_OVERLAY_V1_PRE=" + rendered,
                "CORE_PIPELINE_OVERLAY_V1_POST=" + rendered,
            ]
        )
    if not contract["overlays"]:
        markers.append(
            "CORE_PIPELINE_OVERLAY_V1_NONE="
            + json.dumps({"target": arch}, sort_keys=True, separators=(",", ":"))
        )
    if tool_paths is not None:
        markers.append(
            "CORE_PIPELINE_CMAKE_CACHE_V1="
            + json.dumps(
                direct_cmake_cache_log_document(
                    spec,
                    arch,
                    tool_paths,
                    services=services,
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    markers.append(
        "CORE_PIPELINE_CMAKE_CONTRACT_V1="
        + json.dumps(contract["cmake"], sort_keys=True, separators=(",", ":"))
    )
    return markers


def direct_cmake_log_proves_contract(
    build_log_text: str,
    spec: dict,
    arch: str,
    *,
    services: BuildRecipeServices,
) -> bool:
    expected_static = direct_cmake_log_markers(
        spec,
        arch,
        services=services,
    )
    observed = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_CMAKE_CONTRACT_V1=")
        or line.startswith("CORE_PIPELINE_CMAKE_CACHE_V1=")
        or line.startswith("CORE_PIPELINE_OVERLAY_V1_PRE=")
        or line.startswith("CORE_PIPELINE_OVERLAY_V1_POST=")
        or line.startswith("CORE_PIPELINE_OVERLAY_V1_NONE=")
    ]
    if (
        len(observed) != len(expected_static) + 1
        or observed[:-2] != expected_static[:-1]
        or observed[-1] != expected_static[-1]
        or not observed[-2].startswith("CORE_PIPELINE_CMAKE_CACHE_V1=")
    ):
        return False
    try:
        cache_document = json.loads(observed[-2].split("=", 1)[1])
        expected_cache = direct_cmake_cache_log_document(
            spec,
            arch,
            cache_document.get("tools"),
            services=services,
        )
    except (json.JSONDecodeError, AttributeError, PipelineError):
        return False
    return cache_document == expected_cache


def build_overlays_for_target(spec: dict, arch: str) -> list:
    """Return the validated git-apply overlays declared for one target, or []."""

    build = spec.get("build", {})
    overlays = build.get("overlays", {}) if isinstance(build, dict) else {}
    if not isinstance(overlays, dict):
        return []
    target_overlays = overlays.get(arch)
    return target_overlays if isinstance(target_overlays, list) else []


def overlay_mount_args(
    spec: dict,
    arch: str,
    *,
    io: BuildRecipeIO,
) -> list[str]:
    """Mount each declared patch read-only into the build container.

    Driver-agnostic: any build type that declares build.overlays has its
    patches mounted at /recipe-overlays/<index>.patch for overlay_apply_shell().
    """

    args: list[str] = []
    for index, overlay in enumerate(build_overlays_for_target(spec, arch)):
        patch = io.reference_path(
            {"path": overlay["patch_path"]},
            io.repository_root / "patches",
            f"{arch} overlay patch",
        )
        if (
            not patch.is_file()
            or io.sha256_file(patch) != overlay["patch_sha256"]
        ):
            raise PipelineError(
                f"{arch} overlay patch no longer matches its contract"
            )
        args.extend(["-v", f"{patch}:/recipe-overlays/{index}.patch:ro"])
    return args


def overlay_git_apply_lines(
    overlay: dict, source_root: str, quoted_patch: str
) -> list[str]:
    """Emit the git apply --check/apply pair for one overlay.

    A superproject `git apply` cannot mutate files behind a gitlink, so an
    overlay with a reviewed `submodule_path` applies from that submodule's own
    checkout, stripping the leading path components the patch carries.
    """

    submodule = overlay.get("submodule_path")
    if not submodule:
        quoted_root = shlex.quote(source_root)
        return [
            f"git -C {quoted_root} apply --check --whitespace=error-all {quoted_patch}",
            f"git -C {quoted_root} apply --whitespace=error-all {quoted_patch}",
        ]
    strip = 1 + len(PurePosixPath(submodule).parts)
    quoted_sub_root = shlex.quote(f"{source_root}/{submodule}")
    return [
        f"git -C {quoted_sub_root} apply -p{strip} --check --whitespace=error-all {quoted_patch}",
        f"git -C {quoted_sub_root} apply -p{strip} --whitespace=error-all {quoted_patch}",
    ]


def overlay_apply_shell(spec: dict, arch: str, source_root: str) -> str:
    """Verify and git-apply each declared patch to a checked-out source root.

    Emits, per overlay: a patch-sha check, a preimage-sha check, git apply
    --check then git apply, and a postimage-sha check. Returns "" when the
    target has no overlays. Callers place this after provenance capture and
    before the build, so the pinned commit/tree still reflects clean upstream.
    """

    overlays = build_overlays_for_target(spec, arch)
    if not overlays:
        return ""
    quoted_root = shlex.quote(source_root)
    lines: list[str] = []
    for index, overlay in enumerate(overlays):
        patch = shlex.quote(f"/recipe-overlays/{index}.patch")
        source_path = shlex.quote(f"{source_root}/{overlay['source_path']}")
        lines.extend(
            [
                f'actual_overlay_patch_{index}="$(sha256sum {patch} | awk \'{{print $1}}\')"',
                f'test "$actual_overlay_patch_{index}" = {shlex.quote(overlay["patch_sha256"])}',
                f'actual_overlay_pre_{index}="$(sha256sum {source_path} | awk \'{{print $1}}\')"',
                f'test "$actual_overlay_pre_{index}" = {shlex.quote(overlay["preimage_sha256"])}',
                *overlay_git_apply_lines(overlay, source_root, patch),
                f'actual_overlay_post_{index}="$(sha256sum {source_path} | awk \'{{print $1}}\')"',
                f'test "$actual_overlay_post_{index}" = {shlex.quote(overlay["postimage_sha256"])}',
            ]
        )
    return "\n".join(lines)


def direct_cmake_overlay_mount_args(
    spec: dict,
    arch: str,
    *,
    io: BuildRecipeIO,
) -> list[str]:
    return overlay_mount_args(spec, arch, io=io)


def metadata_replacement_container_path(
    replacement: object,
    *,
    services: BuildRecipeServices,
) -> str:
    if services.callables[
        "vecx_metadata_replacement_contract_is_well_formed"
    ](replacement):
        return "/metadata-replacements/vecx.info"
    if services.callables[
        "atari800_metadata_replacement_contract_is_well_formed"
    ](replacement):
        return "/metadata-replacements/atari800.info"
    if services.callables[
        "picodrive_metadata_replacement_contract_is_well_formed"
    ](replacement):
        return "/metadata-replacements/picodrive.info"
    raise PipelineError("metadata replacement contract is not reviewed")


def repo_metadata(spec: dict) -> dict | None:
    """The repo-pinned metadata contract, when the catalog selected it."""

    metadata = spec.get("metadata", {})
    if not isinstance(metadata, dict) or "repo_path" not in metadata:
        return None
    return metadata


def metadata_replacement_mount_args(
    spec: dict,
    *,
    services: BuildRecipeServices,
    io: BuildRecipeIO,
) -> list[str]:
    pinned = repo_metadata(spec)
    if pinned is not None:
        path = io.safe_child(
            io.repository_root,
            pinned["repo_path"],
            "repo metadata path",
        )
        return ["-v", f"{path}:/metadata-repo/{pinned['artifact_name']}:ro"]
    replacement = services.callables["validated_metadata_replacement"](spec)
    if replacement is None:
        return []
    path = io.safe_child(
        io.repository_root,
        replacement["path"],
        "metadata replacement path",
    )
    mounted = metadata_replacement_container_path(
        replacement,
        services=services,
    )
    return ["-v", f"{path}:{mounted}:ro"]


def metadata_replacement_markers(
    replacement: object,
    *,
    services: BuildRecipeServices,
) -> list[str]:
    if not services.callables[
        "metadata_replacement_contract_is_well_formed"
    ](replacement):
        return []
    assert isinstance(replacement, dict)
    return [
        "CORE_PIPELINE_METADATA_REPLACEMENT|"
        + "|".join(
            (
                replacement["kind"],
                replacement["preimage_sha256"],
                replacement["replacement_sha256"],
            )
        )
    ]


def metadata_replacement_log_proves_contract(
    build_log_text: str,
    replacement: object,
    *,
    services: BuildRecipeServices,
) -> bool:
    expected = metadata_replacement_markers(
        replacement,
        services=services,
    )
    if not expected:
        return False
    actual = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_METADATA_REPLACEMENT|")
    ]
    return actual == expected


def metadata_install_shell(
    spec: dict,
    *,
    services: BuildRecipeServices,
) -> str:
    pinned = repo_metadata(spec)
    if pinned is not None:
        mounted = shlex.quote(f"/metadata-repo/{pinned['artifact_name']}")
        name = shlex.quote(pinned["artifact_name"])
        marker = "CORE_PIPELINE_METADATA_REPO|" + pinned["sha256"]
        return "\n".join(
            [
                f"test -s {mounted}",
                (
                    'actual_repo_metadata_sha256="$(sha256sum '
                    f"{mounted} | awk '{{print $1}}')\""
                ),
                (
                    'test "$actual_repo_metadata_sha256" = '
                    + shlex.quote(pinned["sha256"])
                ),
                f"printf '%s\\n' {shlex.quote(marker)}",
                f"install -m 0644 {mounted} /output/{name}",
            ]
        )
    source = shlex.quote(spec["metadata"]["source_path"])
    name = shlex.quote(spec["metadata"]["artifact_name"])
    replacement = services.callables["validated_metadata_replacement"](spec)
    if replacement is None:
        return f"test -s {source}\ninstall -m 0644 {source} /output/{name}"
    mounted = metadata_replacement_container_path(
        replacement,
        services=services,
    )
    marker = metadata_replacement_markers(
        replacement,
        services=services,
    )[0]
    return "\n".join(
        [
            f"test -s {source}",
            f"test -s {mounted}",
            (
                'actual_metadata_preimage_sha256="$(sha256sum '
                f"{source} | awk '{{print $1}}')\""
            ),
            (
                'test "$actual_metadata_preimage_sha256" = '
                + shlex.quote(replacement["preimage_sha256"])
            ),
            (
                'actual_metadata_replacement_sha256="$(sha256sum '
                f"{mounted} | awk '{{print $1}}')\""
            ),
            (
                'test "$actual_metadata_replacement_sha256" = '
                + shlex.quote(replacement["replacement_sha256"])
            ),
            f"printf '%s\\n' {shlex.quote(marker)}",
            f"install -m 0644 {mounted} /output/{name}",
        ]
    )


def recipe_profile_shell(
    spec: dict,
    arch: str,
    *,
    services: BuildRecipeServices,
) -> str:
    """Render an exact reviewed source-root build, when one is selected."""

    profile = services.callables["validated_recipe_profile"](spec)
    if profile is None:
        return ""
    return services.callables["picodrive_recipe_shell"](spec, arch)


def direct_cmake_overlay_shell(
    spec: dict,
    arch: str,
    source_dir: str,
    *,
    services: BuildRecipeServices,
) -> str:
    contract = services.callables["direct_cmake_contract_for_target"](
        spec, arch
    )
    if contract is None:
        return ""
    lines: list[str] = []
    markers = direct_cmake_log_markers(
        spec,
        arch,
        services=services,
    )
    source_root = shlex.quote(source_dir)
    apply_shell = overlay_apply_shell(spec, arch, source_dir)
    if apply_shell:
        lines.append(apply_shell)
    if contract["overlays"]:
        # Group expectations by owning repo: a superproject diff cannot see
        # file changes behind a gitlink, so submodule-owned overlays are
        # verified against their own submodule's diff.
        overlay_owners: dict[str, list[str]] = {}
        for overlay in contract["overlays"]:
            submodule = overlay.get("submodule_path") or ""
            relative = (
                overlay["source_path"][len(submodule) + 1 :]
                if submodule
                else overlay["source_path"]
            )
            overlay_owners.setdefault(submodule, []).append(relative)
        guard_lines: list[str] = []
        for owner_index, (submodule, paths) in enumerate(
            sorted(overlay_owners.items())
        ):
            owner_root = (
                f"{source_root}/{submodule}" if submodule else source_root
            )
            expected_paths = " ".join(shlex.quote(path) for path in paths)
            expected_file = f"/tmp/expected-overlay-paths-{owner_index}"
            actual_file = f"/tmp/actual-overlay-paths-{owner_index}"
            guard_lines.extend(
                [
                    f"git -C {owner_root} diff --check",
                    f"printf '%s\\0' {expected_paths} > {expected_file}",
                    f"git -C {owner_root} diff --name-only -z --ignore-submodules=dirty > {actual_file}",
                    f"cmp {expected_file} {actual_file}",
                ]
            )
        lines.extend(
            [
                *guard_lines,
                *[
                    f"printf '%s\\n' {shlex.quote(marker)}"
                    for marker in markers[:-1]
                ],
            ]
        )
    else:
        lines.extend(
            [
                f"git -C {source_root} diff --quiet",
                f"printf '%s\\n' {shlex.quote(markers[0])}",
            ]
        )
    return "\n".join(lines)


def direct_cmake_configure_shell(
    spec: dict,
    arch: str,
    source_dir: str,
    *,
    services: BuildRecipeServices,
) -> str:
    contract = services.callables["direct_cmake_contract_for_target"](
        spec, arch
    )
    if contract is None:
        return ""
    cmake = contract["cmake"]
    expected_names = TARGET_CMAKE_TOOL_NAMES[arch]
    # CMake configures at the clone root unless a reviewed source_subdir names an
    # in-tree CMakeLists directory (e.g. tic80's `core`).
    cmake_source = source_dir
    if cmake.get("source_subdir"):
        cmake_source = f"{source_dir}/{cmake['source_subdir']}"
    source_root = shlex.quote(cmake_source)
    # Reviewed core-specific configure flags (select the libretro-only build).
    cmake_defines_args = "".join(
        f" -D{name}={shlex.quote(value)}"
        for name, value in (cmake.get("defines") or {}).items()
    )
    cmake_marker = shlex.quote(
        direct_cmake_log_markers(
            spec,
            arch,
            services=services,
        )[-1]
    )
    cache_format = (
        "CORE_PIPELINE_CMAKE_CACHE_V1="
        + json.dumps(
            {
                "build_type": cmake["build_type"],
                "generator": cmake["generator"],
                "system": cmake["system"],
                "tools": {
                    "ar": "%s",
                    "c": "%s",
                    "cxx": "%s",
                    "ranlib": "%s",
                    "strip": "%s",
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    lines = [
        'cmake_cc="$(command -v "$CC")"',
        'cmake_cxx="$(command -v "$CXX")"',
        'cmake_ar="$(command -v "$AR")"',
        'cmake_ranlib="$(command -v "$RANLIB")"',
        'cmake_strip="$(command -v "$STRIP")"',
        'for cmake_tool_path in "$cmake_cc" "$cmake_cxx" "$cmake_ar" "$cmake_ranlib" "$cmake_strip"; do',
        '  case "$cmake_tool_path" in',
        '    /*) ;;',
        '    *) exit 1 ;;',
        '  esac',
        '  case "$cmake_tool_path" in',
        '    *[!A-Za-z0-9_+./-]*) exit 1 ;;',
        '  esac',
        '  test -x "$cmake_tool_path"',
        'done',
    ]
    for variable, role in (
        ("cmake_cc", "c"),
        ("cmake_cxx", "cxx"),
        ("cmake_ar", "ar"),
        ("cmake_ranlib", "ranlib"),
        ("cmake_strip", "strip"),
    ):
        lines.append(
            f'test "$(basename "${variable}")" = {shlex.quote(expected_names[role])}'
        )
    lines.extend(
        [
            "test ! -e /tmp/core-build",
            (
                f"cmake -S {source_root} -B /tmp/core-build "
                f"-G {shlex.quote(cmake['generator'])} "
                f"-DCMAKE_BUILD_TYPE:STRING={shlex.quote(cmake['build_type'])} "
                f"-DCMAKE_SYSTEM_NAME:STRING={shlex.quote(cmake['system']['name'])} "
                f"-DCMAKE_SYSTEM_PROCESSOR:STRING={shlex.quote(cmake['system']['processor'])} "
                '-DCMAKE_C_COMPILER:FILEPATH="$cmake_cc" '
                '-DCMAKE_CXX_COMPILER:FILEPATH="$cmake_cxx" '
                '-DCMAKE_AR:FILEPATH="$cmake_ar" '
                '-DCMAKE_RANLIB:FILEPATH="$cmake_ranlib" '
                '-DCMAKE_STRIP:FILEPATH="$cmake_strip"'
                + cmake_defines_args
            ),
            "cmake_cache=/tmp/core-build/CMakeCache.txt",
            'test -s "$cmake_cache"',
            "require_cmake_cache_entry() {",
            '  if test "$(grep -Fxc -- "$1" "$cmake_cache")" != 1; then',
            '    cmake_cache_key="${1%%:*}"',
            '    printf "CMake cache contract mismatch; expected: %s\\n" "$1" >&2',
            '    grep -F -- "$cmake_cache_key:" "$cmake_cache" >&2 || true',
            "    return 1",
            "  fi",
            "}",
            "require_cmake_cache_tool_path() {",
            "  cmake_cache_match_count=0",
            '  if grep -Fxq -- "$1:FILEPATH=$2" "$cmake_cache"; then',
            "    cmake_cache_match_count=$((cmake_cache_match_count + 1))",
            "  fi",
            '  if grep -Fxq -- "$1:STRING=$2" "$cmake_cache"; then',
            "    cmake_cache_match_count=$((cmake_cache_match_count + 1))",
            "  fi",
            '  if test "$cmake_cache_match_count" != 1; then',
            '    printf "CMake cache tool-path contract mismatch; expected %s at %s\\n" "$1" "$2" >&2',
            '    grep -F -- "$1:" "$cmake_cache" >&2 || true',
            "    return 1",
            "  fi",
            "}",
            f"require_cmake_cache_entry {shlex.quote('CMAKE_BUILD_TYPE:STRING=' + cmake['build_type'])}",
            f"require_cmake_cache_entry {shlex.quote('CMAKE_SYSTEM_NAME:STRING=' + cmake['system']['name'])}",
            f"require_cmake_cache_entry {shlex.quote('CMAKE_SYSTEM_PROCESSOR:STRING=' + cmake['system']['processor'])}",
            f"require_cmake_cache_entry {shlex.quote('CMAKE_GENERATOR:INTERNAL=' + cmake['generator'])}",
            'require_cmake_cache_tool_path CMAKE_C_COMPILER "$cmake_cc"',
            'require_cmake_cache_tool_path CMAKE_CXX_COMPILER "$cmake_cxx"',
            'require_cmake_cache_entry "CMAKE_AR:FILEPATH=$cmake_ar"',
            'require_cmake_cache_entry "CMAKE_RANLIB:FILEPATH=$cmake_ranlib"',
            'require_cmake_cache_entry "CMAKE_STRIP:FILEPATH=$cmake_strip"',
            f"require_cmake_cache_entry CMAKE_HOME_DIRECTORY:INTERNAL={cmake_source}",
            "require_cmake_cache_entry CMAKE_CACHEFILE_DIR:INTERNAL=/tmp/core-build",
            (
                f"printf {shlex.quote(cache_format + chr(10))} "
                '"$cmake_ar" "$cmake_cc" "$cmake_cxx" '
                '"$cmake_ranlib" "$cmake_strip"'
            ),
            f"printf '%s\\n' {cmake_marker}",
        ]
    )
    return "\n".join(lines)


def spec_submodules_recursive(spec: dict) -> bool:
    """Whether to fetch/record submodules recursively (the default).

    A core sets ``build.recursive_submodules: false`` when ``--recursive`` fails
    on an unneeded nested submodule (e.g. puzzlescript's quickjs-ng carries a
    relative-URL ``test262`` conformance-suite submodule that does not resolve
    and is not built). Top-level fetch still checks out every submodule the root
    ``.gitmodules`` declares, and the non-recursive status keeps those pinned.
    """

    build = spec.get("build")
    return not (isinstance(build, dict) and build.get("recursive_submodules") is False)


def spec_submodules_enabled(spec: dict) -> bool:
    """Whether to fetch submodules at all (the default).

    A core sets ``build.submodules: false`` when its tree declares **no**
    submodules yet carries a stray gitlink -- mupen64plus_next has no
    ``.gitmodules`` at all but a dangling ``mupen64plus-rsp-paraLLEl/lightning/
    gnulib`` entry, so ``git submodule update --init`` fails with "No url found
    for submodule path" whether or not ``--recursive`` is passed. There is
    nothing to fetch, and the sources behind that gitlink are not compiled
    (``HAVE_PARALLEL_RSP`` defaults to 0). Provenance still records
    ``submodule status``, so the stray gitlink stays visible rather than hidden.
    """

    build = spec.get("build")
    return not (isinstance(build, dict) and build.get("submodules") is False)


def provenance_shell(
    source_dir: str,
    recursive_submodules: bool = True,
    submodules: bool = True,
) -> str:
    directory = shlex.quote(source_dir)
    recurse = " --recursive" if recursive_submodules else ""
    # `git submodule status` itself fails on a gitlink that has no .gitmodules
    # mapping, so a tree with a stray gitlink is recorded straight from the
    # tree instead. That records the same thing the status line would -- the
    # pinned commit for each gitlink path -- without hiding it.
    if submodules:
        submodule_record = (
            f"git -C {directory} submodule status{recurse} > /output/submodules.txt"
        )
    else:
        submodule_record = (
            f"git -C {directory} ls-tree -r HEAD "
            "| awk '$2 == \"commit\" { print \" \" $3, $4 }' "
            "> /output/submodules.txt"
        )
    return f"""
git -C {directory} rev-parse HEAD > /output/source-commit.txt
git -C {directory} rev-parse HEAD^{{tree}} > /output/source-tree.txt
git -C {directory} remote get-url origin > /output/source-url.txt
{submodule_record}
""".strip()


def checkout_shell(
    source_dir: str,
    commit: str,
    recursive_submodules: bool = True,
    submodules: bool = True,
) -> str:
    directory = shlex.quote(source_dir)
    revision = shlex.quote(commit)
    recurse = " --recursive" if recursive_submodules else ""
    submodule_lines = (
        f"git -C {directory} submodule sync{recurse}\n"
        f"git -C {directory} submodule update --init{recurse}\n"
        if submodules
        else ""
    )
    return f"""
if ! git -C {directory} cat-file -e {revision}^{{commit}} 2>/dev/null; then
  git -C {directory} fetch --force origin {revision}
fi
git -C {directory} checkout --detach {revision}
{submodule_lines}test "$(git -C {directory} rev-parse HEAD)" = {revision}
""".strip()


def resolver_provenance_shell(resolver: dict) -> str:
    lines = [
        'actual_resolver_commit="$(git -C /libretro-super rev-parse HEAD)"',
        'printf "%s\\n" "$actual_resolver_commit" > /output/resolver-commit.txt',
        (
            'test "$actual_resolver_commit" = '
            + shlex.quote(resolver["libretro_super_commit"])
        ),
    ]
    for prefix in ("core_rules", "fetch_script", "build_script"):
        source = shlex.quote(f"/libretro-super/{resolver[f'{prefix}_path']}")
        output = shlex.quote(f"/output/resolver-{prefix}-sha256.txt")
        expected = shlex.quote(resolver[f"{prefix}_sha256"])
        variable = f"actual_{prefix}_sha256"
        lines.extend(
            [
                f'{variable}="$(sha256sum {source} | awk \'{{print $1}}\')"',
                f'printf "%s\\n" "${variable}" > {output}',
                f'test "${variable}" = {expected}',
            ]
        )
    return "\n".join(lines)


def instrumented_phase_shell(
    name: str,
    body: str,
    *,
    services: BuildRecipeServices,
) -> str:
    """Measure a shell phase and retain its end timestamp on command failure."""

    if not body:
        raise PipelineError("instrumented shell phase body is empty")
    status_name = f"core_pipeline_{name}_status"
    return "\n".join(
        [
            services.callables["phase_start_shell"](name),
            "set +e",
            "(",
            "set -e",
            body,
            ")",
            f"{status_name}=$?",
            "set -e",
            services.callables["phase_finish_shell"](name),
            f'test "${{{status_name}}}" = 0 || exit "${{{status_name}}}"',
        ]
    )

def container_build_script(
    core_id: str,
    arch: str,
    spec: dict,
    resolver: dict,
    tuning_profile_id: str | None = None,
    tuning_registry: Mapping[str, object] | None = None,
    *,
    jobs: int | None = None,
    instrumentation: bool = False,
    source_candidate_contract_spec: dict | None = None,
    source_candidate_projection: SourceCandidateContractProjection | None = None,
    services: BuildRecipeServices,
) -> str:
    contract_spec = services.callables["_source_candidate_contract_spec"](
        core_id,
        spec,
        source_candidate_contract_spec,
        source_candidate_projection,
    )
    source = spec["source"]
    build = spec["build"]
    if jobs is not None and (type(jobs) is not int or jobs <= 0):
        raise PipelineError("configured build jobs must be a positive integer")
    if instrumentation and (jobs != 8 or build.get("driver") != "libretro-super"):
        raise PipelineError(
            "admissible host telemetry initially requires an 8-job libretro-super build"
        )
    commit = source["commit"]
    artifact_name = build["artifact_name"]
    tuning = services.callables["execution_tuning_profile"](
        tuning_profile_id,
        arch,
        tuning_registry,
    )
    if (
        tuning is not None
        and tuning["compiler_arguments"]
        and build["driver"] == "direct-cargo"
    ):
        raise PipelineError(
            "chipset-tuned direct-cargo execution is unsupported: " + core_id
        )
    prelude = [
        services.callables["sanitized_shell_prelude"](
            cargo=spec.get("build", {}).get("driver") == "direct-cargo"
        )
    ]
    if instrumentation:
        prelude.append(services.callables["instrumentation_shell_prelude"]())
    epoch_shell = source_date_epoch_shell(spec, services=services)
    if epoch_shell:
        prelude.append(epoch_shell)
    definition_shell = compile_definition_shell(
        spec,
        arch,
        tuning_profile_id,
        tuning_registry,
        services=services,
    )
    if definition_shell:
        prelude.append(definition_shell)
    assembly_tuning_shell = direct_cmake_assembly_tuning_shell(
        spec,
        arch,
        tuning_profile_id,
        tuning_registry,
        services=services,
    )
    if assembly_tuning_shell:
        prelude.append(assembly_tuning_shell)
    tuning_marker_shell = chipset_tuning_marker_shell(tuning)
    if tuning_marker_shell:
        prelude.append(tuning_marker_shell)
    common_end = f"""
{metadata_install_shell(contract_spec, services=services)}
"$CC" --version | head -n 1 > /output/compiler.txt
"$CC" -print-sysroot > /output/sysroot.txt
chown "$OUTPUT_UID:$OUTPUT_GID" /output/*
""".strip()
    if build["driver"] == "direct-cargo":
        # The Rust image has no C cross compiler or sysroot; the recorded
        # compiler identity is the pinned rustc, and zig owns cross linkage.
        common_end = f"""
{metadata_install_shell(contract_spec, services=services)}
rustc --version > /output/compiler.txt
zig version > /output/sysroot.txt
chown "$OUTPUT_UID:$OUTPUT_GID" /output/*
""".strip()
    if build["driver"] == "libretro-super":
        key = shlex.quote(build["source_key"])
        source_dir = build["source_dir"]
        output_path = shlex.quote(build["output_path"])
        staged_name = shlex.quote(artifact_name)
        is_fbneo_spec = services.callables["fbneo_spec_is_well_formed"](
            contract_spec
        )
        is_mame2003_plus_spec = services.callables[
            "mame2003_plus_spec_is_well_formed"
        ](contract_spec)
        if core_id == FBNEO_CORE_ID:
            selected_build_shell = services.callables["fbneo_build_shell"](
                contract_spec, key, arch
            )
        elif is_fbneo_spec:
            raise PipelineError("FBNeo build spec requires its exact core identity")
        elif core_id == MAME2003_PLUS_CORE_ID:
            selected_build_shell = services.callables[
                "mame2003_plus_build_shell"
            ](
                contract_spec, key, arch
            )
        elif is_mame2003_plus_spec:
            raise PipelineError(
                "MAME 2003-Plus build spec requires its exact core identity"
            )
        else:
            profile_build_shell = recipe_profile_shell(
                contract_spec,
                arch,
                services=services,
            )
            selected_build_shell = profile_build_shell or libretro_build_shell(
                contract_spec,
                key,
                services=services,
            )
        overlay_apply = overlay_apply_shell(spec, arch, source_dir)
        source_hydration_shell = "\n".join(
            [
                f"./libretro-fetch.sh {key}",
                checkout_shell(
                    source_dir,
                    commit,
                    spec_submodules_recursive(spec),
                    spec_submodules_enabled(spec),
                ),
                provenance_shell(
                    source_dir,
                    spec_submodules_recursive(spec),
                    spec_submodules_enabled(spec),
                ),
                source_identity_shell(
                    core_id,
                    contract_spec,
                    services=services,
                ),
                source_date_epoch_provenance_shell(
                    source_dir,
                    spec,
                    services=services,
                ),
            ]
        )
        return "\n".join(
            [
                *prelude,
                "cd /libretro-super",
                resolver_provenance_shell(resolver),
                (
                    instrumented_phase_shell(
                        "source_hydration",
                        source_hydration_shell,
                        services=services,
                    )
                    if instrumentation
                    else source_hydration_shell
                ),
                services.callables["snes9x2005_shell"](contract_spec),
                make_variable_shell(contract_spec, services=services),
                git_version_shell(contract_spec, services=services),
                *([overlay_apply] if overlay_apply else []),
                f"rm -f {output_path}",
                (
                    instrumented_phase_shell(
                        "build_command",
                        selected_build_shell,
                        services=services,
                    )
                    if instrumentation
                    else selected_build_shell
                ),
                services.callables["core_81_generated_version_shell"](
                    contract_spec
                ),
                f"test -s {output_path}",
                f"install -m 0644 {output_path} /output/{staged_name}",
                common_end,
            ]
        )
    if build["driver"] == "direct-make":
        source_url = shlex.quote(source["url"])
        revision = shlex.quote(commit)
        output_path = shlex.quote(build["output_path"])
        staged_name = shlex.quote(artifact_name)
        # `platforms` (the `platform=<val>` make variable, per arch) and
        # `make_subdir` (a `-C <dir>` build directory, e.g. fake08's
        # platform/libretro) are both optional: a core that builds at the source
        # root with a platform variable (gpsp) sets platforms and no subdir; a
        # core whose libretro Makefile lives in a subdirectory and takes no
        # platform variable (fake08) sets make_subdir and no platforms.
        platform_arg = (
            f"platform={shlex.quote(build['platforms'][arch])} "
            if "platforms" in build
            else ""
        )
        make_subdir_arg = (
            f"-C {shlex.quote(build['make_subdir'])} "
            if build.get("make_subdir")
            else ""
        )
        # Optional extra make arguments (e.g. fake08's `V=1`, which flips its
        # `Q := @` echo guard so the compile argv becomes visible without
        # changing the compilation — the artifact stays byte-identical). This is
        # NOT the libretro-super `make_variables` typed profile; it is a plain
        # list of `KEY=VALUE` args appended to the direct-make invocation.
        make_args_arg = "".join(
            f"{shlex.quote(assignment)} " for assignment in build.get("make_args", [])
        )
        return "\n".join(
            [
                *prelude,
                resolver_provenance_shell(resolver),
                "mkdir /tmp/core-source",
                "git -C /tmp/core-source init",
                f"git -C /tmp/core-source remote add origin {source_url}",
                f"git -C /tmp/core-source fetch --depth 1 origin {revision}",
                "git -C /tmp/core-source checkout --detach FETCH_HEAD",
                f'test "$(git -C /tmp/core-source rev-parse HEAD)" = {revision}',
                *( ["git -C /tmp/core-source submodule sync --recursive",
                   "git -C /tmp/core-source submodule update --init --recursive"]
                  if spec_submodules_recursive(spec) else
                  ["git -C /tmp/core-source submodule sync",
                   "git -C /tmp/core-source submodule update --init"] ),
                provenance_shell(
                    "/tmp/core-source",
                    spec_submodules_recursive(spec),
                    spec_submodules_enabled(spec),
                ),
                source_date_epoch_provenance_shell(
                    "/tmp/core-source",
                    spec,
                    services=services,
                ),
                # Reviewed build overlays apply after provenance capture and
                # before the build, exactly as in the other drivers; the
                # mounts are already driver-agnostic.
                *(
                    [overlay_apply_shell(spec, arch, "/tmp/core-source")]
                    if build_overlays_for_target(spec, arch)
                    else []
                ),
                "cd /tmp/core-source",
                f"rm -f {output_path}",
                f'make -j"$CORE_PIPELINE_JOBS" {make_subdir_arg}{platform_arg}{make_args_arg}CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB"'
                if jobs is not None
                else f'make -j"$(nproc)" {make_subdir_arg}{platform_arg}{make_args_arg}CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB"',
                f"test -s {output_path}",
                f"install -m 0644 {output_path} /output/{staged_name}",
                common_end,
            ]
        )
    if build["driver"] == "direct-cargo":
        contract = services.callables["direct_cargo_contract_for_target"](
            contract_spec, arch
        )
        assert contract is not None
        cargo = contract["cargo"]
        source_url = shlex.quote(source["url"])
        revision = shlex.quote(commit)
        triple = cargo["target"]
        # cargo writes into the bare triple directory; the dotted suffix is
        # only cargo-zigbuild's glibc floor selector.
        triple_dir = triple.split(".")[0]
        product = shlex.quote(
            f"/tmp/core-source/target/{triple_dir}/release/{build['output_path']}"
        )
        staged_name = shlex.quote(artifact_name)
        subdir = shlex.quote(f"/tmp/core-source/{cargo['subdir']}")
        return "\n".join(
            [
                *prelude,
                # No resolver provenance: the Rust image carries no
                # libretro-super checkout and the cargo driver never
                # consults it.
                "mkdir /tmp/core-source",
                "git -C /tmp/core-source init",
                f"git -C /tmp/core-source remote add origin {source_url}",
                f"git -C /tmp/core-source fetch --depth 1 origin {revision}",
                "git -C /tmp/core-source checkout --detach FETCH_HEAD",
                f'test "$(git -C /tmp/core-source rev-parse HEAD)" = {revision}',
                "git -C /tmp/core-source submodule sync",
                "git -C /tmp/core-source submodule update --init",
                provenance_shell(
                    "/tmp/core-source",
                    spec_submodules_recursive(spec),
                    spec_submodules_enabled(spec),
                ),
                source_date_epoch_provenance_shell(
                    "/tmp/core-source",
                    spec,
                    services=services,
                ),
                # The workspace Cargo.lock is the dependency pin: upstream
                # commits it (so it is already inside the verified source
                # tree), the catalog pins its exact bytes, and --locked
                # refuses any drift or regeneration.
                f'echo "{cargo["lock_sha256"]}  /tmp/core-source/Cargo.lock" | sha256sum -c -',
                # The two marker lines are what the log proof pins: the exact
                # dependency-lock digest and the exact zigbuild invocation
                # (the make-variables CORE_PIPELINE_MAKEFLAGS precedent).
                "printf '%s\n' "
                + shlex.quote(f"CORE_PIPELINE_CARGO_LOCK|{cargo['lock_sha256']}"),
                "printf '%s\n' "
                + shlex.quote(
                    f"CORE_PIPELINE_CARGO|--locked --target {triple} --release"
                ),
                "export CARGO_HOME=/tmp/cargo-home",
                f"cd {subdir}",
                f"rm -f {product}",
                (
                    f'cargo zigbuild --locked --target {shlex.quote(triple)} '
                    '--release --jobs "$CORE_PIPELINE_JOBS"'
                    if jobs is not None
                    else f"cargo zigbuild --locked --target {shlex.quote(triple)} --release"
                ),
                f"test -s {product}",
                f"install -m 0644 {product} /output/{staged_name}",
                common_end,
            ]
        )
    if build["driver"] == "direct-cmake":
        contract = services.callables["direct_cmake_contract_for_target"](
            contract_spec, arch
        )
        assert contract is not None
        source_url = shlex.quote(source["url"])
        revision = shlex.quote(commit)
        source_dir = "/tmp/core-source"
        quoted_source_dir = shlex.quote(source_dir)
        output_path = shlex.quote(f"/tmp/core-build/{build['output_path']}")
        staged_name = shlex.quote(artifact_name)
        cmake = contract["cmake"]
        overlay_shell = direct_cmake_overlay_shell(
            spec,
            arch,
            source_dir,
            services=services,
        )
        configure_shell = direct_cmake_configure_shell(
            spec,
            arch,
            source_dir,
            services=services,
        )
        build_command = (
            "cmake --build /tmp/core-build "
            f"--target {shlex.quote(cmake['target'])} "
            + (
                '--parallel "$CORE_PIPELINE_JOBS" --verbose'
                if jobs is not None
                else '--parallel "$(nproc)" --verbose'
            )
        )
        return "\n".join(
            [
                *prelude,
                resolver_provenance_shell(resolver),
                f"mkdir {quoted_source_dir}",
                f"git -C {quoted_source_dir} init",
                f"git -C {quoted_source_dir} remote add origin {source_url}",
                f"git -C {quoted_source_dir} fetch --depth 1 origin {revision}",
                f"git -C {quoted_source_dir} checkout --detach FETCH_HEAD",
                f'test "$(git -C {quoted_source_dir} rev-parse HEAD)" = {revision}',
                f"git -C {quoted_source_dir} submodule sync --recursive",
                f"git -C {quoted_source_dir} submodule update --init --recursive",
                provenance_shell(
                    source_dir,
                    spec_submodules_recursive(spec),
                    spec_submodules_enabled(spec),
                ),
                source_date_epoch_provenance_shell(
                    source_dir,
                    spec,
                    services=services,
                ),
                overlay_shell,
                configure_shell,
                build_command,
                f"test -s {output_path}",
                f"install -m 0644 {output_path} /output/{staged_name}",
                common_end,
            ]
        )
    raise PipelineError(f"unsupported driver for {core_id}: {build['driver']}")
