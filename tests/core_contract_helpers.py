"""Shared synthetic fixtures for core-owned contract tests."""

from __future__ import annotations

from pathlib import Path
import shlex
from types import ModuleType

from scripts import core_pipeline as pipeline
from core_pipeline_lib.contracts import (
    atari800,
    c_only,
    core_81,
    core_2048,
    gambatte,
    gearboy,
    gearsystem,
    handy,
    lowresnx,
    mednafen_supafaust,
    mednafen_supergrafx,
    mixed_language,
    nestopia,
    potator,
    prosystem,
    quicknes,
    race,
    snes9x,
    stella2014,
    tgbdual,
    uzem,
)


def _individual_c_only_contract(core_id: str) -> c_only.COnlyLogContract:
    if core_id == race.RACE_CORE_ID:
        return race.race_c_only_contract()
    if core_id == core_2048.CORE_2048_ID:
        return core_2048.core_2048_c_only_contract()
    if core_id == lowresnx.LOWRESNX_CORE_ID:
        return lowresnx.lowresnx_c_only_contract()
    if core_id == potator.POTATOR_CORE_ID:
        return potator.potator_c_only_contract()
    if core_id == atari800.ATARI800_CORE_ID:
        return atari800.atari800_c_only_contract()
    raise AssertionError(f"no synthetic C-only fixture for {core_id}")


def _individual_mixed_language_contract(
    core_id: str,
) -> mixed_language.MixedLanguageLogContract:
    if core_id == handy.HANDY_CORE_ID:
        return handy.handy_mixed_language_contract()
    if core_id == gambatte.GAMBATTE_CORE_ID:
        return gambatte.gambatte_mixed_language_contract()
    if core_id == stella2014.STELLA2014_CORE_ID:
        return stella2014.stella2014_mixed_language_contract()
    if core_id == tgbdual.TGBDUAL_CORE_ID:
        return tgbdual.tgbdual_cxx_contract()
    if core_id == quicknes.QUICKNES_CORE_ID:
        return quicknes.quicknes_cxx_contract()
    if core_id == nestopia.NESTOPIA_CORE_ID:
        return nestopia.nestopia_cxx_contract()
    if core_id == prosystem.PROSYSTEM_CORE_ID:
        return prosystem.PROSYSTEM_LOG_CONTRACT
    if core_id == snes9x.SNES9X_CORE_ID:
        return snes9x.SNES9X_LOG_CONTRACT
    if core_id == mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID:
        return mednafen_supafaust.MEDNAFEN_SUPAFAUST_LOG_CONTRACT
    if core_id == uzem.UZEM_CORE_ID:
        return uzem.uzem_mixed_language_contract()
    if core_id == gearboy.GEARBOY_CORE_ID:
        return gearboy.gearboy_mixed_language_contract()
    if core_id == gearsystem.GEARSYSTEM_CORE_ID:
        return gearsystem.gearsystem_mixed_language_contract()
    if core_id == core_81.CORE_81_ID:
        return core_81.core_81_mixed_language_contract()
    if core_id == mednafen_supergrafx.MEDNAFEN_SUPERGRAFX_CORE_ID:
        return mednafen_supergrafx.mednafen_supergrafx_mixed_language_contract()
    raise AssertionError(f"no synthetic mixed-language fixture for {core_id}")


def build_mixed_language_log_fixture(
    pipeline: ModuleType,
    repository_root: Path,
    core_id: str,
    arch: str,
) -> dict:
    """Build deterministic log material from one core's owned contract."""

    compilers = {
        "arm64": ("aarch64-linux-gnu-gcc", "aarch64-linux-gnu-g++"),
        "armhf": (
            "arm-a30-linux-gnueabihf-gcc",
            "arm-a30-linux-gnueabihf-g++",
        ),
    }
    contract = _individual_mixed_language_contract(core_id)
    catalog = pipeline.load_catalog(
        repository_root / "manifests" / "core-builds.json"
    )
    spec = catalog["cores"][core_id]
    c_compiler, cxx_compiler = compilers[arch]
    git_version = spec["build"].get("git_version")
    version_token = (
        '-DGIT_VERSION=\\""' + git_version["value"] + '"\\"'
        if git_version is not None
        else None
    )
    scoped_to_cxx = (
        git_version is not None and git_version.get("compiler_scope") == "cxx"
    )
    cxx_suffix = (
        ".cxx" if core_id == stella2014.STELLA2014_CORE_ID else ".cpp"
    )
    entries: list[tuple[str, str, str, str]] = []
    for language, suffix, compiler in (
        ("c", ".c", c_compiler),
        ("cxx", cxx_suffix, cxx_compiler),
    ):
        for index in range(contract.expected_language_counts.get(language, 0)):
            stem = f"mixed/{language}/unit_{index:03d}"
            entries.append((stem + ".o", stem + suffix, language, compiler))

    compile_lines = []
    compile_invocations = []
    for output, source, language, compiler in entries:
        version = (
            f" {version_token}"
            if version_token is not None
            and (not scoped_to_cxx or language == "cxx")
            else ""
        )
        line = (
            f"{compiler} -c -o{output} {source}{version} "
            "-O2 -DNDEBUG -fPIC"
        )
        compile_lines.append(line)
        invocation = mixed_language.mixed_language_compile_invocation(
            shlex.split(line),
            {c_compiler, cxx_compiler},
            {cxx_compiler},
            contract.semantic_path_aliases,
        )
        if invocation is None:
            raise AssertionError("synthetic mixed-language compile is invalid")
        compile_invocations.append(invocation)

    link_compiler = (
        c_compiler
        if contract.expected_link_language == "c"
        else cxx_compiler
    )
    link_line = " ".join(
        [
            link_compiler,
            "-o",
            contract.build_artifact_name,
            *contract.expected_link_options,
            *[
                f"./{output}"
                for output, _source, _language, _compiler in reversed(entries)
            ],
        ]
    )
    link = mixed_language.mixed_language_link_command(
        shlex.split(link_line),
        {link_compiler},
        contract,
        include_raw_sha256=True,
    )
    if link is None:
        raise AssertionError("synthetic mixed-language link is invalid")
    link_objects, link_object_sha256, raw_link_object_sha256 = link
    compile_order = [*range(0, len(entries), 2), *range(1, len(entries), 2)]
    if core_id == prosystem.PROSYSTEM_CORE_ID:
        reviewed_diagnostics = [prosystem.PROSYSTEM_EXPECTED_WARNING_BLOCK]
    elif core_id == snes9x.SNES9X_CORE_ID:
        reviewed_diagnostics = list(snes9x.SNES9X_EXPECTED_WARNING_BLOCKS[arch])
    elif core_id == mednafen_supafaust.MEDNAFEN_SUPAFAUST_CORE_ID:
        reviewed_diagnostics = list(
            mednafen_supafaust.MEDNAFEN_SUPAFAUST_EXPECTED_DIAGNOSTIC_CONTEXT_BLOCKS[
                arch
            ]
        )
    else:
        reviewed_diagnostics = []
    log = (
        "\n".join(
            [
                *pipeline.git_version_log_markers(spec),
                *[compile_lines[index] for index in compile_order],
                *reviewed_diagnostics,
                link_line,
            ]
        )
        + "\n"
    )
    return {
        "artifact": contract.build_artifact_name,
        "c_compiler": c_compiler,
        "compile_invocation_sha256": (
            mixed_language.mixed_language_compile_invocation_sha256(
                compile_invocations
            )
        ),
        "compile_lines": compile_lines,
        "compile_pair_sha256": (
            mixed_language.mixed_language_compile_pair_sha256(
                (output, source)
                for output, source, _language, _compiler in entries
            )
        ),
        "cxx_compiler": cxx_compiler,
        "entries": entries,
        "link_line": link_line,
        "link_object_sha256": link_object_sha256,
        "link_objects": link_objects,
        "log": log,
        "raw_link_object_sha256": raw_link_object_sha256,
        "spec": spec,
        "version_token": version_token,
    }


def build_c_only_log_fixture(
    pipeline: ModuleType,
    repository_root: Path,
    core_id: str,
    arch: str,
) -> dict:
    """Build deterministic C-only log material from one core's owned contract."""

    c_compilers = {
        "arm64": "aarch64-linux-gnu-gcc",
        "armhf": "arm-a30-linux-gnueabihf-gcc",
    }
    contract = _individual_c_only_contract(core_id)
    catalog = pipeline.load_catalog(
        repository_root / "manifests" / "core-builds.json"
    )
    spec = catalog["cores"][core_id]
    c_compiler = c_compilers[arch]
    git_version = spec["build"].get("git_version")
    version_token = (
        '-DGIT_VERSION=\\""' + git_version["value"] + '"\\"'
        if git_version is not None
        else None
    )
    entries: list[tuple[str, str]] = []
    for index in range(contract.expected_compile_count):
        stem = f"src/unit_{index:03d}"
        entries.append((stem + ".o", stem + ".c"))

    compile_lines = []
    compile_invocations = []
    for output, source in entries:
        version = f" {version_token}" if version_token is not None else ""
        line = f"{c_compiler} -c -o{output} {source}{version} -O2 -DNDEBUG -fPIC"
        compile_lines.append(line)
        invocation = c_only.c_only_compile_invocation(
            shlex.split(line),
            {c_compiler},
            contract.semantic_path_aliases,
        )
        if invocation is None:
            raise AssertionError("synthetic C-only compile is invalid")
        compile_invocations.append(invocation)

    link_line = " ".join(
        [
            c_compiler,
            "-o",
            contract.build_artifact_name,
            *contract.expected_link_options,
            *[f"./{output}" for output, _source in reversed(entries)],
        ]
    )
    link = c_only.c_only_link_command(
        shlex.split(link_line),
        {c_compiler},
        contract,
        include_raw_sha256=True,
    )
    if link is None:
        raise AssertionError("synthetic C-only link is invalid")
    _link_objects, link_object_sha256, _archives, raw_link_object_sha256 = link
    compile_order = [*range(0, len(entries), 2), *range(1, len(entries), 2)]
    log = (
        "\n".join(
            [
                *pipeline.git_version_log_markers(spec),
                *[compile_lines[index] for index in compile_order],
                link_line,
            ]
        )
        + "\n"
    )
    return {
        "artifact": contract.build_artifact_name,
        "c_compiler": c_compiler,
        "compile_invocation_sha256": (
            c_only.c_only_compile_invocation_sha256(compile_invocations)
        ),
        "compile_lines": compile_lines,
        "compile_pair_sha256": c_only.c_only_compile_pair_sha256(entries),
        "entries": entries,
        "link_line": link_line,
        "link_object_sha256": link_object_sha256,
        "log": log,
        "raw_link_object_sha256": raw_link_object_sha256,
        "spec": spec,
        "version_token": version_token,
    }
