#!/usr/bin/env python3
"""Local-only provenance, build, and validation tooling for Cores-spruce.

The tool deliberately has no publication command.  It can import the currently
shipped SpruceOS cores as an artifact-only starting baseline, reproduce selected
Actions build steps in the pinned Docker images, and promote successful local
records to build-golden metadata.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import NamedTuple
import copy
from contextlib import contextmanager
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import profile_registry as core_profile_registry  # noqa: E402

from core_pipeline_lib.source_bundle import (  # noqa: E402
    pipeline_bundle_content_sha256,
    pipeline_source_bundle,
    pipeline_source_bundle_is_well_formed,
)
from core_pipeline_lib.errors import PipelineError  # noqa: E402
from core_pipeline_lib.foundation import (  # noqa: E402
    atomic_create_json,
    atomic_write_json,
    durable_atomic_channel_write,
    load_json,
    manifest_lock as _foundation_manifest_lock,
    require_contained,
    require_manifest_reference_path as _foundation_manifest_reference_path,
    run,
    safe_child,
    sha256_bytes,
    sha256_file,
    utc_now,
)
from core_pipeline_lib.cli import (  # noqa: E402
    ParserConfig,
    ParserHandlers,
    build_parser as build_cli_parser,
)
from core_pipeline_lib.contracts.compiler import (  # noqa: E402
    COMPILER_COMMAND_RE,
    TARGET_COMPILERS,
    TARGET_CXX_COMPILERS,
    line_may_name_target_compiler,
)
from core_pipeline_lib.contracts.command_line import (  # noqa: E402
    command_line_is_lexically_safe,
)
from core_pipeline_lib.contracts.a5200 import (  # noqa: E402
    A5200_CORE_ID,
    a5200_spec_is_well_formed,
    A5200_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.snes9x import (  # noqa: E402
    SNES9X_CORE_ID,
    snes9x_spec_is_well_formed,
    SNES9X_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.mednafen_wswan import (  # noqa: E402
    MEDNAFEN_WSWAN_CORE_ID,
    MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    mednafen_wswan_golden_build_contract_is_well_formed,
    mednafen_wswan_golden_source_is_well_formed,
    mednafen_wswan_spec_is_well_formed,
)
from core_pipeline_lib.contracts.mednafen_pcfx import (  # noqa: E402
    MEDNAFEN_PCFX_CORE_ID,
    MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS,
    MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    PCFX_PORTABLE_MAKE_PROFILE,
    PCFX_PORTABLE_MAKE_VARIABLES,
    mednafen_pcfx_combined_golden_build_contract_is_well_formed,
    mednafen_pcfx_golden_source_is_well_formed,
    mednafen_pcfx_spec_is_well_formed,
)
from core_pipeline_lib.contracts.mednafen_supergrafx import (  # noqa: E402
    MEDNAFEN_SUPERGRAFX_CORE_ID,
    MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    mednafen_supergrafx_spec_is_well_formed,
)
from core_pipeline_lib.contracts.pokemini import (  # noqa: E402
    POKEMINI_CORE_ID,
    POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    pokemini_golden_build_contract_is_well_formed,
    pokemini_golden_source_is_well_formed,
    pokemini_spec_is_well_formed,
)
from core_pipeline_lib.contracts.mgba import (  # noqa: E402
    MGBA_CORE_ID,
    MGBA_NATIVE_GIT_VERSION,
    MGBA_NATIVE_GIT_VERSION_DERIVATION,
    MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    mgba_golden_build_contract_is_well_formed,
    mgba_golden_source_is_well_formed,
    mgba_spec_is_well_formed,
    mgba_log_proves_contract,
)
from core_pipeline_lib.contracts.uzem import (  # noqa: E402
    UZEM_CORE_ID,
    UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    uzem_golden_build_contract_is_well_formed,
    uzem_golden_source_is_well_formed,
    uzem_spec_is_well_formed,
    uzem_log_proves_contract,
)
from core_pipeline_lib.contracts.vemulator import (  # noqa: E402
    VEMULATOR_CORE_ID,
    VEMULATOR_SOURCE_IDENTITY_MARKER,
    vemulator_golden_build_contract_is_well_formed,
    vemulator_golden_source_is_well_formed,
    vemulator_spec_is_well_formed,
    vemulator_log_proves_contract,
)
from core_pipeline_lib.contracts.freeintv import (  # noqa: E402
    FREEINTV_CORE_ID,
    FREEINTV_SOURCE_IDENTITY_MARKER,
    freeintv_golden_build_contract_is_well_formed,
    freeintv_golden_source_is_well_formed,
    freeintv_spec_is_well_formed,
    freeintv_log_proves_contract,
)
from core_pipeline_lib.contracts.gearboy import (  # noqa: E402
    GEARBOY_CORE_ID,
    GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    gearboy_golden_build_contract_is_well_formed,
    gearboy_golden_source_is_well_formed,
    gearboy_spec_is_well_formed,
    gearboy_log_proves_contract,
)
from core_pipeline_lib.contracts.gearsystem import (  # noqa: E402
    GEARSYSTEM_CORE_ID,
    GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    gearsystem_golden_build_contract_is_well_formed,
    gearsystem_golden_source_is_well_formed,
    gearsystem_spec_is_well_formed,
    gearsystem_log_proves_contract,
)
from core_pipeline_lib.contracts.gearcoleco import (  # noqa: E402
    GEARCOLECO_CORE_ID,
    GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    gearcoleco_golden_build_contract_is_well_formed,
    gearcoleco_golden_source_is_well_formed,
    gearcoleco_spec_is_well_formed,
)
from core_pipeline_lib.contracts.fmsx import (  # noqa: E402
    FMSX_CORE_ID,
    FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    fmsx_golden_build_contract_is_well_formed,
    fmsx_golden_source_is_well_formed,
    fmsx_spec_is_well_formed,
)
from core_pipeline_lib.contracts.bluemsx import (  # noqa: E402
    BLUEMSX_CORE_ID,
    BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    bluemsx_golden_build_contract_is_well_formed,
    bluemsx_golden_source_is_well_formed,
    bluemsx_spec_is_well_formed,
)
from core_pipeline_lib.contracts.vice_x64 import (  # noqa: E402
    VICE_X64_CORE_ID,
    VICE_X64_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    vice_x64_golden_build_contract_is_well_formed,
    vice_x64_golden_source_is_well_formed,
    vice_x64_spec_is_well_formed,
)
from core_pipeline_lib.contracts.vice_xvic import (  # noqa: E402
    VICE_XVIC_CORE_ID,
    VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    vice_xvic_golden_build_contract_is_well_formed,
    vice_xvic_golden_source_is_well_formed,
    vice_xvic_spec_is_well_formed,
)
from core_pipeline_lib.contracts.o2em import (  # noqa: E402
    O2EM_CORE_ID,
    o2em_spec_is_well_formed,
    O2EM_NATIVE_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.vecx import (  # noqa: E402
    VECX_CORE_ID,
    VECX_FORBIDDEN_COMPILE_MACROS,
    VECX_METADATA_PREIMAGE_SHA256,
    VECX_METADATA_REPLACEMENT_KIND,
    VECX_METADATA_REPLACEMENT_PATH,
    VECX_METADATA_REPLACEMENT_SHA256,
    VECX_SOFTWARE_BUILD_KEYS,
    VECX_SOFTWARE_MAKE_PROFILE,
    VECX_SOFTWARE_MAKE_VARIABLES,
    VECX_SOFTWARE_SPEC_IDENTITY,
    vecx_combined_golden_build_contract_is_well_formed,
    vecx_command_tokens_are_software_only,
    vecx_metadata_replacement_contract_is_well_formed,
    vecx_software_identity_is_well_formed,
    vecx_software_spec_is_well_formed,
)
from core_pipeline_lib.contracts.lowresnx import (  # noqa: E402
    LOWRESNX_CORE_ID,
    LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    lowresnx_golden_build_contract_is_well_formed,
    lowresnx_golden_source_is_well_formed,
    lowresnx_spec_is_well_formed,
)
from core_pipeline_lib.contracts.potator import (  # noqa: E402
    POTATOR_CORE_ID,
    POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    potator_spec_is_well_formed,
    potator_log_proves_contract,
)
from core_pipeline_lib.contracts.race import (  # noqa: E402
    RACE_CORE_ID,
    RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    race_spec_is_well_formed,
    race_log_proves_contract,
)
from core_pipeline_lib.contracts.core_2048 import (  # noqa: E402
    CORE_2048_ID,
    CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    core_2048_golden_build_contract_is_well_formed,
    core_2048_golden_source_is_well_formed,
    core_2048_spec_is_well_formed,
)
from core_pipeline_lib.contracts.core_81 import (  # noqa: E402
    CORE_81_ID,
    core_81_generated_source_contract_is_well_formed,
    core_81_generated_version_shell,
    core_81_golden_build_contract_is_well_formed,
    core_81_spec_is_well_formed,
)
from core_pipeline_lib.contracts.fceumm import (  # noqa: E402
    FCEUMM_CORE_ID,
    FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.atari800 import (  # noqa: E402
    ATARI800_CORE_ID,
    ATARI800_METADATA_PREIMAGE_SHA256,
    ATARI800_METADATA_REPLACEMENT_KIND,
    ATARI800_METADATA_REPLACEMENT_PATH,
    ATARI800_METADATA_REPLACEMENT_SHA256,
    ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    atari800_golden_build_contract_is_well_formed,
    atari800_golden_source_is_well_formed,
    atari800_identity_is_well_formed,
    atari800_metadata_replacement_contract_is_well_formed,
    atari800_spec_is_well_formed,
)
from core_pipeline_lib.contracts.picodrive import (  # noqa: E402
    PICODRIVE_CORE_ID,
    PICODRIVE_METADATA_PREIMAGE_SHA256,
    PICODRIVE_METADATA_REPLACEMENT_KIND,
    PICODRIVE_METADATA_REPLACEMENT_PATH,
    PICODRIVE_METADATA_REPLACEMENT_SHA256,
    picodrive_golden_build_contract_is_well_formed,
    picodrive_golden_source_is_well_formed,
    picodrive_identity_is_well_formed,
    picodrive_metadata_replacement_contract_is_well_formed,
    picodrive_recipe_profile_is_well_formed,
    picodrive_recipe_shell,
    picodrive_spec_is_well_formed,
)
from core_pipeline_lib.contracts.mame2003_plus import (  # noqa: E402
    MAME2003_PLUS_CORE_ID,
    MAME2003_PLUS_GIT_VERSION,
    MAME2003_PLUS_NATIVE_GIT_VERSION,
    MAME2003_PLUS_NATIVE_GIT_VERSION_DERIVATION,
    MAME2003_PLUS_SOURCE_COMMIT,
    MAME2003_PLUS_SOURCE_IDENTITY_MARKER,
    mame2003_plus_build_shell,
    mame2003_plus_git_version_contract_is_well_formed,
    mame2003_plus_git_version_markers,
    mame2003_plus_golden_build_contract_is_well_formed,
    mame2003_plus_golden_source_is_well_formed,
    mame2003_plus_spec_is_well_formed,
)
from core_pipeline_lib.contracts.fbneo import (  # noqa: E402
    FBNEO_CORE_ID,
    FBNEO_GIT_VERSION,
    FBNEO_GIT_VERSION_DERIVATION,
    FBNEO_SOURCE_COMMIT,
    fbneo_build_shell,
    fbneo_compile_tokens,
    fbneo_git_version_contract_is_well_formed,
    fbneo_git_version_markers,
    fbneo_golden_build_contract_is_well_formed,
    fbneo_golden_source_is_well_formed,
    fbneo_spec_is_well_formed,
)
from core_pipeline_lib.contracts.parallel_n64 import (  # noqa: E402
    PARALLEL_N64_MAKE_PROFILE,
    PARALLEL_N64_MAKE_VARIABLES,
    parallel_n64_spec_is_well_formed,
)
from core_pipeline_lib.contracts.km_parallel_n64_xtreme_amped_turbo import (
    km_parallel_n64_xtreme_amped_turbo_log_proves_contract,
)
from core_pipeline_lib.contracts.yabasanshiro import (
    yabasanshiro_log_proves_contract,
    yabasanshiro_spec_is_well_formed,
)
from core_pipeline_lib.contracts.mupen64plus_next import (  # noqa: E402
    MUPEN64PLUS_NEXT_MAKE_PROFILE,
    MUPEN64PLUS_NEXT_MAKE_VARIABLES,
    mupen64plus_next_spec_is_well_formed,
)
from core_pipeline_lib.contracts.gambatte import (  # noqa: E402
    GAMBATTE_CORE_ID,
    GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.tgbdual import (  # noqa: E402
    TGBDUAL_CORE_ID,
    TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.quicknes import (  # noqa: E402
    QUICKNES_CORE_ID,
    quicknes_spec_is_well_formed,
    QUICKNES_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.nestopia import (  # noqa: E402
    NESTOPIA_CORE_ID,
    nestopia_spec_is_well_formed,
    NESTOPIA_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.snes9x2005 import (  # noqa: E402
    SNES9X2005_CORE_ID,
    SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    snes9x2005_shell,
)
from core_pipeline_lib.contracts.snes9x2005_plus import (  # noqa: E402
    SNES9X2005_PLUS_CORE_ID,
    SNES9X2005_PLUS_MAKE_PROFILE,
    SNES9X2005_PLUS_MAKE_VARIABLES,
    SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.freechaf import (  # noqa: E402
    FREECHAF_NATIVE_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.mednafen_lynx import (  # noqa: E402
    MEDNAFEN_LYNX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.mednafen_ngp import (  # noqa: E402
    MEDNAFEN_NGP_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.mednafen_supafaust import (  # noqa: E402
    MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.mednafen_vb import (  # noqa: E402
    MEDNAFEN_VB_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.prosystem import (  # noqa: E402
    PROSYSTEM_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.registry import (  # noqa: E402
    CORE_LOG_CONTRACTS,
    core_log_contract_for,
)
from core_pipeline_lib.contracts.cap32 import (  # noqa: E402
    CAP32_CORE_ID,
    CAP32_MAKE_TRACE_MARKER,
    CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.crocods import (  # noqa: E402
    CROCODS_CORE_ID,
    CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.genesis_plus_gx import (  # noqa: E402
    GENESIS_PLUS_GX_CORE_ID,
    GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.genesis_plus_gx_wide import (  # noqa: E402
    GENESIS_PLUS_GX_WIDE_CORE_ID,
    GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.handy import (  # noqa: E402
    HANDY_CORE_ID,
    HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.contracts.stella2014 import (  # noqa: E402
    STELLA2014_CORE_ID,
    STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY,
)
from core_pipeline_lib.policy import (  # noqa: E402
    CommitBlacklist,
    CommitBlacklistError,
    CommitPolicyReport,
    commit_blacklist_reference_is_well_formed,
    load_catalog_commit_blacklist as _load_catalog_commit_blacklist,
    parse_commit_blacklist,
    require_catalog_cores_eligible as _require_catalog_cores_eligible,
    require_golden_sources_eligible as _require_golden_sources_eligible,
    require_pin_sources_eligible as _require_pin_sources_eligible,
    require_source_commits_eligible as _require_source_commits_eligible,
)
from core_pipeline_lib.runtime import (  # noqa: E402
    RunnerProfileError,
    RunnerRequest,
    resolve_runner_context,
    runner_evidence,
    runner_evidence_is_well_formed,
)
from core_pipeline_lib.records import (  # noqa: E402
    active_promotion_e2e_scope,
    candidate_golden_id_is_well_formed,
    core_compatibility_content_sha256,
    core_golden_v2_shape_errors,
    load_catalog_compatibility_coverage,
    one_core_golden_document,
    require_active_core_golden,
    validate_core_e2e_run,
    validate_core_compatibility_document as _validate_core_compatibility_document,
)
from core_pipeline_lib.release import (  # noqa: E402
    actions_matrix_for_plan,
    runner_selector_for_contract,
    seal_release_candidate,
    validate_release_plan,
    write_release_plan,
)
from core_pipeline_lib.release.repository import (  # noqa: E402
    ReleaseRepositoryServices,
    construct_tracked_release_plan,
    validate_plan_against_repository,
)
from core_pipeline_lib.release.worker import (  # noqa: E402
    ReleaseWorkerServices,
    record_validated_release_result,
)
from core_pipeline_lib.release.workflow_audit import (  # noqa: E402
    audit_release_workflows,
)


def _collect_spec_guards() -> dict[str, tuple]:
    """Bind core_id -> (spec validator, guard message) from contract modules.

    A module opts in by declaring ``SPEC_GUARD_MESSAGE`` beside its
    ``<core>_spec_is_well_formed`` validator and ``<CORE>_CORE_ID`` constant;
    the catalog guard then enforces the validator with that exact message.
    Replaces the hand-maintained 47-entry guard chain: onboarding a core now
    registers its guard by writing the module, with no edit here. Binding is
    restricted to functions *defined in* the module (``__module__`` check), so
    a cross-module import can never register a guard for someone else's core.
    """

    import importlib
    import pkgutil

    import core_pipeline_lib.contracts as contracts_package

    guards: dict[str, tuple] = {}
    for info in pkgutil.iter_modules(contracts_package.__path__):
        module = importlib.import_module(
            f"core_pipeline_lib.contracts.{info.name}"
        )
        message = vars(module).get("SPEC_GUARD_MESSAGE")
        if not isinstance(message, str):
            continue
        for name, value in vars(module).items():
            if not name.endswith("_spec_is_well_formed"):
                continue
            if getattr(value, "__module__", "") != module.__name__:
                continue
            prefix = name[: -len("_spec_is_well_formed")]
            guarded_core_id = vars(module).get(f"{prefix.upper()}_CORE_ID")
            if not isinstance(guarded_core_id, str):
                continue
            if guarded_core_id in guards:
                raise PipelineError(
                    f"duplicate spec guard for core: {guarded_core_id}"
                )
            guards[guarded_core_id] = (name, value, message)
    return guards


SPEC_GUARDS = _collect_spec_guards()

# Re-export every bound guard validator as a module attribute. The established
# test seam patches validators on THIS module (mock.patch.object(pipeline,
# "<core>_spec_is_well_formed", ...)), and that must keep working now that
# dispatch is registry-driven rather than fed by 89 import blocks. setdefault
# keeps any name that is still explicitly imported above.
for _guard_name, _guard_validator, _guard_message in SPEC_GUARDS.values():
    globals().setdefault(_guard_name, _guard_validator)
del _guard_name, _guard_validator, _guard_message


def metadata_replacement_contract_is_well_formed(value: object) -> bool:
    """Recognize one exact core-owned whole-file replacement contract."""

    return bool(
        vecx_metadata_replacement_contract_is_well_formed(value)
        or atari800_metadata_replacement_contract_is_well_formed(value)
        or picodrive_metadata_replacement_contract_is_well_formed(value)
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "manifests" / "core-builds.json"
DEFAULT_STORE = ROOT / ".local-e2e" / "store"
DEFAULT_RUNS = ROOT / ".local-e2e" / "runs"
DEFAULT_PIN_SET_DIR = ROOT / "pins" / "core-sets"
DEFAULT_RELEASES = ROOT / ".local-e2e" / "releases"
DEFAULT_FULL_RELEASE_PLANS = ROOT / ".local-e2e" / "release-plans"
DEFAULT_FULL_RELEASE_RESULTS = ROOT / ".local-e2e" / "release-results"
DEFAULT_FULL_RELEASE_CANDIDATES = ROOT / ".local-e2e" / "release-candidates"
DEFAULT_NIGHTLIES = ROOT / ".local-e2e" / "nightlies"
DEFAULT_CHANNELS = ROOT / ".local-e2e" / "channels"
TOOLCHAIN_LOCK_SCHEMA_REF = "../../manifests/toolchain-lock.schema.json"
STORE_SINGLE_EVIDENCE_NAMES = (
    "artifact",
    "metadata",
    "e2e_record",
    "package",
)
STORE_TARGET_EVIDENCE_NAMES = ("build_records", "build_logs", "recipe_snapshots")
NON_CORE_WORKFLOWS = {"build-docker.yml"}
AGGREGATE_WORKFLOW_GLOBS = ("build-all*.yml", "build-all*.yaml")
ARCH_LAYOUT = {
    "arm64": {
        "directory": "RetroArch/.retroarch/cores64",
        "package_directory": "cores64",
        "elf_class": "ELF64",
        "machine": "AArch64",
    },
    "armhf": {
        "directory": "RetroArch/.retroarch/cores",
        "package_directory": "cores",
        "elf_class": "ELF32",
        "machine": "ARM",
    },
}
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOCAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CORE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")
GENERATED_SOURCE_PATH_RE = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))"
    r"[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$"
)
COMPILE_DEFINITION_RE = re.compile(
    r"^([A-Z_][A-Z0-9_]*)=(0|[1-9][0-9]{0,9})$"
)
PORTABLE_FFMPEG_MAKE_VARIABLES = {
    "ARCH_AARCH64": 0,
    "ARCH_ARM": 0,
    "ARCH_X86": 0,
    "ARCH_X86_64": 0,
    "HAVE_SSA": 0,
    "LIBRETRO_EMBED_FFMPEG": 1,
    "OPENGL": 0,
}
PORTABLE_FFMPEG_MAKE_PROFILE = "portable-ffmpeg-v1"
PORTABLE_FFMPEG_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "make_variables",
        "output_path",
        "source_date_epoch",
        "source_dir",
        "source_key",
    }
)
GL_DYNAREC_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "make_variables",
        "output_path",
        "source_dir",
        "source_key",
    }
)
UZEM_NATIVE_GIT_VERSION_BUILD_KEYS = frozenset(
    {
        "artifact_name",
        "driver",
        "git_version",
        "output_path",
        "source_dir",
        "source_key",
    }
)
NATIVE_GIT_VERSION_SHORT10_BUILD_KEYS = UZEM_NATIVE_GIT_VERSION_BUILD_KEYS.union(
    {"source_date_epoch"}
)
NATIVE_GIT_MAKE_BUILD_KEYS = UZEM_NATIVE_GIT_VERSION_BUILD_KEYS.union(
    {"make_variables"}
)
COMBINED_NATIVE_MAKE_CORE_IDS = frozenset(
    {MEDNAFEN_PCFX_CORE_ID, "snes9x2005_plus", VECX_CORE_ID}
)
NATIVE_GIT_VERSION_C_SCOPE_CORE_IDS = frozenset(
    {
        ATARI800_CORE_ID,
        BLUEMSX_CORE_ID,
        "cap32",
        "crocods",
        FCEUMM_CORE_ID,
        "genesis_plus_gx",
        "genesis_plus_gx_wide",
        CORE_2048_ID,
        LOWRESNX_CORE_ID,
        MAME2003_PLUS_CORE_ID,
        MGBA_CORE_ID,
        POTATOR_CORE_ID,
        RACE_CORE_ID,
        "snes9x2005",
        "snes9x2005_plus",
    }
)
RESERVED_MAKE_VARIABLE_NAMES = frozenset(
    {
        "AR",
        "ARCH",
        "CC",
        "CFLAGS",
        "CHOST",
        "CMAKE_BUILD_PARALLEL_LEVEL",
        "CMAKE_GENERATOR",
        "CMAKE_GENERATOR_PLATFORM",
        "CMAKE_GENERATOR_TOOLSET",
        "CMAKE_TOOLCHAIN_FILE",
        "CPPFLAGS",
        "CROSS_COMPILE",
        "CXX",
        "CXXFLAGS",
        "LDFLAGS",
        "MAKE",
        "MAKEFILES",
        "MAKEFLAGS",
        "MAKEOVERRIDES",
        "GNUMAKEFLAGS",
        "MFLAGS",
        "RANLIB",
        "SHELL",
        "SOURCE_DATE_EPOCH",
        "STRIP",
    }
)
PORTABLE_FFMPEG_COMPILE_DEFINITIONS = (
    "ARCH_AARCH64=0",
    "ARCH_ARM=0",
    "ARCH_X86=0",
    "ARCH_X86_64=0",
    "LIBRETRO_EMBED_FFMPEG=1",
)
PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS = frozenset(
    {"HAVE_GL_FFT", "HAVE_OPENGL", "HAVE_OPENGLES", "HAVE_SSA", "OPENGL"}
)
GIT_VERSION_DERIVATION = "hyphen-short7-v1"
GIT_VERSION_RE = re.compile(r"^-[0-9a-f]{7}$")
GIT_VERSION_C_SCOPE = "c"
GIT_VERSION_CXX_SCOPE = "cxx"
GIT_VERSION_COMPILER_SCOPES = frozenset(
    {GIT_VERSION_C_SCOPE, GIT_VERSION_CXX_SCOPE}
)
NATIVE_GIT_VERSION_DERIVATION = "native-space-short7-v1"
NATIVE_GIT_VERSION_RE = re.compile(r"^ [0-9a-f]{7}$")
NATIVE_GIT_VERSION_SHORT8_DERIVATION = (
    MAME2003_PLUS_NATIVE_GIT_VERSION_DERIVATION
)
NATIVE_GIT_VERSION_SHORT9_DERIVATION = MGBA_NATIVE_GIT_VERSION_DERIVATION
NATIVE_GIT_VERSION_SHORT9_RE = re.compile(r"^ [0-9a-f]{9}$")
NATIVE_GIT_VERSION_SHORT10_DERIVATION = "native-space-short10-v1"
NATIVE_GIT_VERSION_SHORT10_RE = re.compile(r"^ [0-9a-f]{10}$")
NATIVE_GIT_DESCRIBE_DERIVATION = "native-git-describe-v1"
NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES = {
    MGBA_CORE_ID: MGBA_NATIVE_GIT_VERSION_SPEC_IDENTITY,
}
NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES = {
    VICE_X64_CORE_ID: VICE_X64_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    VICE_XVIC_CORE_ID: VICE_XVIC_NATIVE_GIT_VERSION_SPEC_IDENTITY,
}
NATIVE_GIT_VERSION_SPEC_IDENTITIES = {
    ATARI800_CORE_ID: ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    UZEM_CORE_ID: UZEM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    MEDNAFEN_WSWAN_CORE_ID: MEDNAFEN_WSWAN_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    MEDNAFEN_PCFX_CORE_ID: MEDNAFEN_PCFX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    MEDNAFEN_SUPERGRAFX_CORE_ID: (
        MEDNAFEN_SUPERGRAFX_NATIVE_GIT_VERSION_SPEC_IDENTITY
    ),
    POKEMINI_CORE_ID: POKEMINI_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    FMSX_CORE_ID: FMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    BLUEMSX_CORE_ID: BLUEMSX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    CORE_2048_ID: CORE_2048_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    LOWRESNX_CORE_ID: LOWRESNX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    POTATOR_CORE_ID: POTATOR_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    RACE_CORE_ID: RACE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    FCEUMM_CORE_ID: FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    GAMBATTE_CORE_ID: GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    TGBDUAL_CORE_ID: TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    CAP32_CORE_ID: CAP32_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    CROCODS_CORE_ID: CROCODS_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    GENESIS_PLUS_GX_CORE_ID: GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    GENESIS_PLUS_GX_WIDE_CORE_ID: (
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY
    ),
    HANDY_CORE_ID: HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    STELLA2014_CORE_ID: STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    SNES9X2005_CORE_ID: SNES9X2005_NATIVE_GIT_VERSION_SPEC_IDENTITY,
    SNES9X2005_PLUS_CORE_ID: (
        SNES9X2005_PLUS_NATIVE_GIT_VERSION_SPEC_IDENTITY
    ),
}
ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS = frozenset(
    {
        GENESIS_PLUS_GX_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        GENESIS_PLUS_GX_WIDE_NATIVE_GIT_VERSION_SPEC_IDENTITY[
            "source_commit"
        ],
    }
)
MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS = frozenset(
    {
        ATARI800_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        FCEUMM_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        GAMBATTE_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        TGBDUAL_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        HANDY_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
        STELLA2014_NATIVE_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    }
)
COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS = (
    ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS
    | MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS
    | {FBNEO_SOURCE_COMMIT, MAME2003_PLUS_SOURCE_COMMIT}
)
EXACT_NATIVE_GIT_VERSION_CORE_IDS = frozenset(
    NATIVE_GIT_VERSION_SPEC_IDENTITIES
).union(
    {FBNEO_CORE_ID, MAME2003_PLUS_CORE_ID},
    NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES
)
NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES = {
    GEARBOY_CORE_ID: GEARBOY_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    GEARSYSTEM_CORE_ID: GEARSYSTEM_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
    GEARCOLECO_CORE_ID: GEARCOLECO_NATIVE_GIT_DESCRIBE_SPEC_IDENTITY,
}
NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT = {
    identity["source_commit"]: identity["git_version_value"]
    for identity in NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.values()
}
NATIVE_GIT_DESCRIBE_COMPILE_MACROS_BY_COMMIT = {
    identity["source_commit"]: identity["compile_macro"]
    for identity in NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.values()
}
EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS = frozenset(
    NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES
)
EXACT_GIT_VERSION_CORE_IDS = (
    EXACT_NATIVE_GIT_VERSION_CORE_IDS | EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS
)
EXACT_SOURCE_NATIVE_CORE_IDS = frozenset(
    {FREEINTV_CORE_ID, VEMULATOR_CORE_ID}
)
MAX_SOURCE_DATE_EPOCH = 253402300799
TARGET_CMAKE_TOOL_NAMES = {
    "arm64": {
        "ar": "aarch64-linux-gnu-ar",
        "c": "aarch64-linux-gnu-gcc",
        "cxx": "aarch64-linux-gnu-g++",
        "ranlib": "aarch64-linux-gnu-ranlib",
        "strip": "aarch64-linux-gnu-strip",
    },
    "armhf": {
        "ar": "arm-a30-linux-gnueabihf-ar",
        "c": "arm-a30-linux-gnueabihf-gcc",
        "cxx": "arm-a30-linux-gnueabihf-g++",
        "ranlib": "arm-a30-linux-gnueabihf-ranlib",
        "strip": "arm-a30-linux-gnueabihf-strip",
    },
}
PIN_SELECTION_POLICY = {
    "unit": "complete-core-package",
    "source_order": "first-complete-wins",
    "failed_candidate": "retain-parent",
    "missing_candidate": "retain-parent",
    "release_action": "copy-exact-package-bytes",
}
MAX_PIN_PARENT_DEPTH = 32
CHANNEL_KINDS = {
    "nightly": "golden",
    "pinned": "pin-set",
    "release": "local-release",
}
REQUIRED_LIBRETRO_SYMBOLS = frozenset(
    {
        "retro_api_version",
        "retro_cheat_reset",
        "retro_cheat_set",
        "retro_deinit",
        "retro_get_memory_data",
        "retro_get_memory_size",
        "retro_get_region",
        "retro_get_system_av_info",
        "retro_get_system_info",
        "retro_init",
        "retro_load_game",
        "retro_load_game_special",
        "retro_reset",
        "retro_run",
        "retro_serialize",
        "retro_serialize_size",
        "retro_set_audio_sample",
        "retro_set_audio_sample_batch",
        "retro_set_controller_port_device",
        "retro_set_environment",
        "retro_set_input_poll",
        "retro_set_input_state",
        "retro_set_video_refresh",
        "retro_unload_game",
        "retro_unserialize",
    }
)


class _PinValidationContext:
    """Per-operation cache for immutable evidence proofs.

    Lineage, path, digest, scope, and store-file checks are intentionally not
    cached.  Callers may reuse only successful intrinsic proofs after the
    referenced bytes have passed their normal validation in the current walk.
    """

    def __init__(self) -> None:
        self.log_proofs: dict[
            tuple[str, str, str],
            tuple[bool, bool, bool, bool, bool],
        ] = {}
        self.pinned_packages: set[tuple[str, str, str, str, int]] = set()


@contextmanager
def manifest_lock(path: Path):
    with _foundation_manifest_lock(path, ROOT):
        yield


def require_manifest_reference_path(
    reference: dict,
    allowed_root: Path,
    label: str,
) -> Path:
    return _foundation_manifest_reference_path(
        reference,
        allowed_root,
        label,
        ROOT,
    )


def require_lexical_repository_path(
    path: Path,
    allowed_root: Path,
    label: str,
) -> Path:
    """Validate an operator path before resolving any symlink component."""

    try:
        relative = path.absolute().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise PipelineError(f"{label} must be inside the repository") from exc
    return require_manifest_reference_path(
        {"path": relative},
        allowed_root,
        label,
    )


def load_catalog_commit_blacklist(
    catalog: dict,
) -> tuple[CommitBlacklist, Path]:
    return _load_catalog_commit_blacklist(catalog, ROOT)


def require_source_commits_eligible(
    catalog: dict,
    sources: Iterable[tuple[object, object]],
) -> list[CommitPolicyReport]:
    return _require_source_commits_eligible(catalog, sources, ROOT)


def require_catalog_cores_eligible(catalog: dict, core_ids: Iterable[str]) -> None:
    _require_catalog_cores_eligible(catalog, core_ids, ROOT)


def require_pin_sources_eligible(catalog: dict, pin: dict) -> None:
    _require_pin_sources_eligible(catalog, pin, ROOT)


def require_golden_sources_eligible(catalog: dict, golden: dict) -> None:
    _require_golden_sources_eligible(catalog, golden, ROOT)


def toolchain_lock_content_sha256(document: dict) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "lock_id": document.get("lock_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "toolchains": document.get("toolchains"),
    }
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def load_toolchain_archive_validator(path: Path):
    spec = importlib.util.spec_from_file_location("cores_toolchain_archive", path)
    if spec is None or spec.loader is None:
        raise PipelineError(f"cannot load toolchain archive validator: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PipelineError(f"cannot load toolchain archive validator: {exc}") from exc
    return module


def load_catalog_toolchain_lock(catalog: dict) -> tuple[dict, Path, Path]:
    reference = catalog.get("toolchain_lock")
    if not isinstance(reference, dict) or set(reference) != {
        "path",
        "schema_version",
        "lock_id",
        "file_sha256",
        "content_sha256",
    }:
        raise PipelineError("toolchain_lock reference has an unexpected shape")
    if reference.get("path") != "pins/toolchains/local-cache-v1.json":
        raise PipelineError("toolchain_lock path must be the exact local-cache-v1 lock")
    if type(reference.get("schema_version")) is not int or reference["schema_version"] != 1:
        raise PipelineError("toolchain_lock schema_version must be the exact integer 1")
    if reference.get("lock_id") != "local-cache-v1":
        raise PipelineError("toolchain_lock lock_id must be local-cache-v1")
    for field in ("file_sha256", "content_sha256"):
        value = reference.get(field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            raise PipelineError(f"toolchain_lock {field} is invalid")
    validator_reference = catalog.get("toolchain_lock_validator")
    if (
        not isinstance(validator_reference, dict)
        or set(validator_reference) != {"path", "sha256"}
        or validator_reference.get("path") != "scripts/toolchain_archive.py"
        or not isinstance(validator_reference.get("sha256"), str)
        or not SHA256_RE.fullmatch(validator_reference["sha256"])
    ):
        raise PipelineError("toolchain_lock_validator reference is invalid")
    path = require_manifest_reference_path(
        reference, ROOT / "pins" / "toolchains", "toolchain lock"
    )
    validator_path = require_manifest_reference_path(
        validator_reference, ROOT / "scripts", "toolchain lock validator"
    )
    if not path.is_file() or sha256_file(path) != reference["file_sha256"]:
        raise PipelineError("toolchain_lock file SHA256 does not match")
    if (
        not validator_path.is_file()
        or sha256_file(validator_path) != validator_reference["sha256"]
    ):
        raise PipelineError("toolchain_lock_validator SHA256 does not match")
    validator = load_toolchain_archive_validator(validator_path)
    try:
        document = validator.strict_json_file(path)
        validator.validate_lock_document(document, repo_root=ROOT)
    except validator.ToolchainArchiveError as exc:
        raise PipelineError(f"toolchain lock is invalid: {exc}") from exc
    if set(document) != {
        "$schema",
        "schema_version",
        "lock_id",
        "local_only",
        "publication",
        "toolchains",
        "content_sha256",
    }:
        raise PipelineError("toolchain lock has an unexpected top-level shape")
    if (
        document.get("$schema") != TOOLCHAIN_LOCK_SCHEMA_REF
        or type(document.get("schema_version")) is not int
        or document["schema_version"] != reference["schema_version"]
        or document.get("lock_id") != reference["lock_id"]
        or document.get("local_only") is not True
        or document.get("publication") != "disabled"
    ):
        raise PipelineError("toolchain lock metadata does not match its catalog reference")
    if (
        document.get("content_sha256") != reference["content_sha256"]
        or document["content_sha256"] != toolchain_lock_content_sha256(document)
    ):
        raise PipelineError("toolchain lock content SHA256 does not match")
    return document, path, validator_path


def build_toolchain_key(spec: dict, arch: str) -> str:
    """The toolchain-lock entry a build for this spec runs inside.

    direct-cargo cores build every device target inside the pinned Rust
    image (cargo-zigbuild carries the cross linkage); every other driver
    uses the target architecture's C cross image.
    """

    if spec.get("build", {}).get("driver") == "direct-cargo":
        return "rust"
    return arch


def expected_archive_provenance(catalog: dict, architecture: str) -> dict:
    document, _, _ = load_catalog_toolchain_lock(catalog)
    entry = document["toolchains"][architecture]
    archive = entry["archive"]
    return {
        "lock": copy.deepcopy(catalog["toolchain_lock"]),
        "validator": copy.deepcopy(catalog["toolchain_lock_validator"]),
        "architecture": architecture,
        "archive": {
            "filename": archive["filename"],
            "sha256": archive["sha256"],
            "size": archive["size"],
        },
    }


def golden_content_sha256(document: dict) -> str:
    schema_version = document.get("schema_version")
    if schema_version == 2:
        material = {
            "schema_version": schema_version,
            "core_id": document.get("core_id"),
            "pin_id": document.get("pin_id"),
            "local_only": document.get("local_only"),
            "publication": document.get("publication"),
            "baseline": document.get("baseline"),
            "cores": document.get("cores"),
            "build_goldens": document.get("build_goldens"),
        }
    else:
        # Preserve the exact schema-v1 digest projection for immutable history.
        material = {
            "schema_version": schema_version,
            "baseline": document.get("baseline"),
            "cores": document.get("cores"),
            "build_goldens": document.get("build_goldens"),
        }
    canonical = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256_bytes(canonical)


def e2e_content_sha256(document: dict) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "run_id": document.get("run_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "result": document.get("result"),
        "workflow_audit": document.get("workflow_audit"),
        "builds": document.get("builds"),
        "packages": document.get("packages"),
    }
    if document.get("schema_version") == 2:
        material["runner"] = document.get("runner")
    canonical = json.dumps(
        material, sort_keys=True, separators=(",", ":")
    ).encode()
    return sha256_bytes(canonical)


def provenance_identity_sha256(record: dict) -> str:
    source = record.get("source", {})
    recipe = record.get("recipe", {})
    toolchain = record.get("toolchain", {})
    material = {
        "core_id": record.get("core_id"),
        "architecture": record.get("architecture"),
        "source": {
            "resolved_commit": source.get("resolved_commit"),
            "tree": source.get("tree"),
            "submodules": source.get("submodules", []),
        },
        "recipe": {
            "core_spec_sha256": recipe.get("core_spec_sha256"),
            "pipeline_sha256": recipe.get("pipeline_sha256"),
            "workflow_sha256": recipe.get("workflow_sha256"),
        },
        "toolchain": {
            "resolved_image_id": toolchain.get("resolved_image_id"),
            "dockerfile_sha256": toolchain.get("dockerfile_sha256"),
            "resolver_digests": toolchain.get("resolver_digests"),
        },
        "artifact_sha256": record.get("artifact", {}).get("sha256"),
        "metadata_sha256": record.get("metadata", {}).get("sha256"),
    }
    archive_provenance = toolchain.get("archive_provenance")
    pipeline_bundle = recipe.get("pipeline_bundle")
    if pipeline_source_bundle_is_well_formed(pipeline_bundle):
        material["recipe"]["pipeline_bundle"] = pipeline_bundle
    commit_blacklist = recipe.get("commit_blacklist")
    if commit_blacklist_reference_is_well_formed(commit_blacklist):
        material["recipe"]["commit_blacklist"] = commit_blacklist
    if archive_provenance is not None:
        material["provenance_version"] = 2
        material["toolchain"]["archive_provenance"] = archive_provenance
    build = record.get("build", {})
    if isinstance(build, dict) and (
        build.get("driver") == "direct-cmake"
        or "make_variables" in build
        or "git_version" in build
        or "generated_source" in build
        or "recipe_profile" in build
        or (
            record.get("core_id") in EXACT_SOURCE_NATIVE_CORE_IDS
            and pipeline_source_bundle_is_well_formed(
                recipe.get("pipeline_bundle")
            )
        )
    ):
        material["build"] = recorded_build_contract(build)
    elif isinstance(build, dict) and "source_date_epoch" in build:
        material["build"] = {"source_date_epoch": build["source_date_epoch"]}
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def selection_content_sha256(selection: dict) -> str:
    targets = {}
    for arch, target in sorted(selection.get("targets", {}).items()):
        targets[arch] = {
            "artifact": {
                "sha256": target.get("artifact", {}).get("sha256"),
                "size": target.get("artifact", {}).get("size"),
            },
            "build_record_sha256": target.get("build_record_sha256"),
            "provenance_identity_sha256": target.get(
                "provenance_identity_sha256"
            ),
        }
    material = {
        "tier": selection.get("tier"),
        "validation_scope": selection.get("validation_scope"),
        "e2e": selection.get("e2e"),
        "package": {
            "name": selection.get("package", {}).get("name"),
            "sha256": selection.get("package", {}).get("sha256"),
            "size": selection.get("package", {}).get("size"),
        },
        "metadata": {
            "sha256": selection.get("metadata", {}).get("sha256"),
            "size": selection.get("metadata", {}).get("size"),
        },
        "targets": targets,
    }
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def pin_set_content_sha256(document: dict) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "pin_id": document.get("pin_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "scope": document.get("scope"),
        "parent": document.get("parent"),
        "sources": document.get("sources"),
        "selection_policy": document.get("selection_policy"),
        "cores": document.get("cores"),
        "summary": document.get("summary"),
    }
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def release_content_sha256(document: dict) -> str:
    material = {
        "schema_version": document.get("schema_version"),
        "release_id": document.get("release_id"),
        "local_only": document.get("local_only"),
        "publication": document.get("publication"),
        "pin": document.get("pin"),
        "assets": document.get("assets"),
    }
    return sha256_bytes(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    )


def store_bytes(store_root: Path, namespace: str, content: bytes) -> tuple[Path, str]:
    digest = sha256_bytes(content)
    destination = store_root / namespace / "sha256" / digest[:2] / digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or sha256_file(destination) != digest:
            raise PipelineError(f"content-addressed store collision at {destination}")
        return destination, digest
    with tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.chmod(temporary, 0o644)
    os.replace(temporary, destination)
    return destination, digest


def store_file(store_root: Path, namespace: str, source: Path) -> tuple[Path, str]:
    return store_bytes(store_root, namespace, source.read_bytes())


def canonical_store_path(namespace: str, digest: str) -> Path:
    if not namespace or "/" in namespace or namespace in {".", ".."}:
        raise PipelineError("content-addressed namespace is invalid")
    if not SHA256_RE.fullmatch(digest):
        raise PipelineError("content-addressed digest is invalid")
    return DEFAULT_STORE / namespace / "sha256" / digest[:2] / digest


def require_canonical_store_entry(entry: dict, namespace: str, label: str) -> Path:
    digest = entry.get("sha256", "")
    expected = canonical_store_path(namespace, digest)
    expected_relative = str(expected.relative_to(ROOT))
    if entry.get("path") != expected_relative:
        raise PipelineError(f"{label} does not use its canonical local-store path")
    unresolved = ROOT
    for part in Path(entry["path"]).parts:
        unresolved /= part
        if unresolved.is_symlink():
            raise PipelineError(f"{label} must not traverse a symlink")
    path = safe_child(ROOT, entry["path"], label)
    try:
        path.relative_to(DEFAULT_STORE.resolve())
    except ValueError as exc:
        raise PipelineError(f"{label} escapes the local store") from exc
    return path


def recipe_snapshot(record: dict) -> bytes:
    recipe = record["recipe"]
    toolchain = record["toolchain"]
    build = record.get("build", {})
    is_direct_cmake = (
        isinstance(build, dict) and build.get("driver") == "direct-cmake"
    )
    paths = {
        recipe["catalog_path"],
        recipe["workflow"],
        str(Path(__file__).relative_to(ROOT)),
        toolchain["dockerfile"],
    }
    pipeline_bundle = recipe.get("pipeline_bundle")
    if pipeline_bundle is not None:
        if not pipeline_source_bundle_is_well_formed(pipeline_bundle):
            raise PipelineError("recipe snapshot pipeline bundle is invalid")
        if (
            pipeline_bundle["files"].get(str(Path(__file__).relative_to(ROOT)))
            != recipe.get("pipeline_sha256")
        ):
            raise PipelineError("recipe snapshot launcher digest is inconsistent")
        paths.update(pipeline_bundle["files"])
    commit_blacklist = recipe.get("commit_blacklist")
    if pipeline_bundle is not None and commit_blacklist is None:
        raise PipelineError(
            "schema-v9 recipe snapshot requires commit blacklist provenance"
        )
    if commit_blacklist is not None:
        if not commit_blacklist_reference_is_well_formed(commit_blacklist):
            raise PipelineError("recipe snapshot commit blacklist is invalid")
        paths.add(commit_blacklist["path"])
    archive_provenance = toolchain.get("archive_provenance")
    if archive_provenance is not None:
        paths.add(archive_provenance["lock"]["path"])
        paths.add(archive_provenance["validator"]["path"])
    if is_direct_cmake:
        overlays = build.get("overlays")
        if not isinstance(overlays, list):
            raise PipelineError("direct-CMake recipe snapshot overlays are invalid")
        for overlay in overlays:
            if not isinstance(overlay, dict) or not isinstance(
                overlay.get("patch_path"), str
            ):
                raise PipelineError("direct-CMake recipe snapshot overlay is invalid")
            paths.add(overlay["patch_path"])
    metadata_replacement = build.get("metadata_replacement")
    if metadata_replacement is not None:
        if not metadata_replacement_contract_is_well_formed(
            metadata_replacement
        ):
            raise PipelineError(
                "recipe snapshot metadata replacement contract is invalid"
            )
        paths.add(metadata_replacement["path"])
    files = {}
    for relative in sorted(paths):
        path = safe_child(ROOT, relative, "recipe snapshot path")
        if not path.is_file():
            raise PipelineError(f"recipe snapshot file is missing: {relative}")
        files[relative] = {
            "sha256": sha256_file(path),
            "text": path.read_text(encoding="utf-8"),
        }
    snapshot_toolchain = {
        "image_id": toolchain["resolved_image_id"],
        "dockerfile": toolchain["dockerfile"],
        "dockerfile_sha256": toolchain["dockerfile_sha256"],
        "resolver_digests": toolchain["resolver_digests"],
    }
    if archive_provenance is not None:
        snapshot_toolchain["archive_provenance"] = archive_provenance
    has_compile_definition_contract = (
        isinstance(build, dict) and "compile_definitions" in build
    )
    has_make_variable_contract = (
        isinstance(build, dict) and "make_variables" in build
    )
    has_git_version_contract = (
        isinstance(build, dict) and "git_version" in build
    )
    has_generated_source_contract = (
        isinstance(build, dict) and "generated_source" in build
    )
    has_recipe_profile_contract = (
        isinstance(build, dict) and "recipe_profile" in build
    )
    has_source_date_epoch_contract = (
        isinstance(build, dict) and "source_date_epoch" in build
    )
    snapshot = {
        "schema_version": (
            10
            if has_generated_source_contract
            else 9
            if pipeline_bundle is not None
            else 8
            if has_git_version_contract and has_make_variable_contract
            else 7
            if has_git_version_contract
            else 6
            if has_make_variable_contract
            else 5
            if is_direct_cmake
            else 4
            if has_source_date_epoch_contract
            else 3
            if has_compile_definition_contract
            else (2 if archive_provenance is not None else 1)
        ),
        "core_id": record["core_id"],
        "architecture": record["architecture"],
        "source": record["source"],
        "recipe": recipe,
        "toolchain": snapshot_toolchain,
        "files": files,
    }
    if (
        is_direct_cmake
        or has_compile_definition_contract
        or has_make_variable_contract
        or has_git_version_contract
        or has_generated_source_contract
        or has_recipe_profile_contract
        or has_source_date_epoch_contract
    ):
        snapshot["build"] = recorded_build_contract(build)
    return (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode()


def git_head(path: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=path).stdout.strip()


def core_workflows() -> dict[str, Path]:
    workflow_dir = ROOT / ".github" / "workflows"
    result: dict[str, Path] = {}
    for path in sorted(workflow_dir.glob("build-*.yml")):
        if path.name in NON_CORE_WORKFLOWS or any(
            path.match(pattern) for pattern in AGGREGATE_WORKFLOW_GLOBS
        ):
            continue
        core_id = path.stem.removeprefix("build-")
        if core_id in result:
            raise PipelineError(f"duplicate workflow core ID: {core_id}")
        result[core_id] = path
    if not result:
        raise PipelineError("no core workflows found")
    return result


def validated_compile_definitions(spec: dict) -> dict[str, list[str]]:
    build = spec.get("build", {})
    if "compile_definitions" not in build:
        return {}
    if "git_version" in build and not fbneo_spec_is_well_formed(spec):
        raise PipelineError(
            "build.compile_definitions cannot be combined with git_version "
            "outside the exact reviewed FBNeo contract"
        )
    raw = build["compile_definitions"]
    if not isinstance(raw, dict) or not raw:
        raise PipelineError("build.compile_definitions must be a non-empty object")
    targets = spec.get("targets", [])
    if not isinstance(targets, list):
        raise PipelineError("build.compile_definitions requires valid core targets")
    unexpected = sorted(set(raw) - set(targets))
    if unexpected:
        raise PipelineError(
            "build.compile_definitions contains a non-target architecture: "
            + ", ".join(unexpected)
        )
    normalized: dict[str, list[str]] = {}
    for arch, definitions in raw.items():
        if arch not in ARCH_LAYOUT:
            raise PipelineError(
                f"build.compile_definitions architecture is invalid: {arch}"
            )
        if not isinstance(definitions, list) or not definitions:
            raise PipelineError(
                f"build.compile_definitions.{arch} must be a non-empty array"
            )
        if any(not isinstance(definition, str) for definition in definitions):
            raise PipelineError(
                f"build.compile_definitions.{arch} entries must be strings"
            )
        if definitions != sorted(definitions):
            raise PipelineError(
                f"build.compile_definitions.{arch} must be sorted"
            )
        names: set[str] = set()
        for definition in definitions:
            match = COMPILE_DEFINITION_RE.fullmatch(definition)
            if match is None or int(match.group(2)) > 0xFFFFFFFF:
                raise PipelineError(
                    f"build.compile_definitions.{arch} entry is invalid: {definition}"
                )
            if match.group(1) in names:
                raise PipelineError(
                    f"build.compile_definitions.{arch} repeats {match.group(1)}"
                )
            names.add(match.group(1))
        normalized[arch] = list(definitions)
    return normalized


def compile_definitions_for_target(spec: dict, arch: str) -> list[str]:
    if arch not in ARCH_LAYOUT:
        raise PipelineError(f"unknown architecture: {arch}")
    return validated_compile_definitions(spec).get(arch, [])


class MakeVariableProfileFacts(NamedTuple):
    """Everything bookkeeping-shaped about one reviewed make-variable profile.

    Adding a profile is one entry here (plus its contract-module constants);
    the resolver, contract-name map, validated_make_variables rules, make
    shell, golden-record keys, and snapshot/macro policies all read this
    registry. Profile-specific *behavior* (the FFmpeg marker-ordering proof,
    the Snes9x 2005 Plus macro proof, VecX's divergence diagnostics) stays in
    code -- this table holds only facts. ``expected_build_keys is None`` marks
    the one bespoke profile (VecX) whose validation body remains inline.
    ``spec_validator`` is a *name*, resolved through this module's globals at
    call time, preserving the mock.patch.object test seam.
    """

    variables: Mapping[str, object]
    contract_name: str
    expected_build_keys: frozenset[str] | None
    spec_validator: str | None = None
    spec_validator_args: tuple = ()
    restriction_message: str | None = None
    forbid_rules: tuple = ()
    requires_epoch: bool = False
    make_subdir_libretro: bool = False
    makefile: str = "Makefile"
    golden_epoch: bool | None = None
    forbidden_compile_macros: frozenset[str] = frozenset()


def _make_variable_profile_facts() -> dict[str, MakeVariableProfileFacts]:
    return {
        PORTABLE_FFMPEG_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=PORTABLE_FFMPEG_MAKE_VARIABLES,
            contract_name="portable FFmpeg",
            expected_build_keys=PORTABLE_FFMPEG_BUILD_KEYS,
            forbid_rules=(
                (
                    ("git_version",),
                    "build.make_variables cannot be combined with git_version "
                    "for the portable FFmpeg contract",
                ),
            ),
            requires_epoch=True,
            make_subdir_libretro=True,
            golden_epoch=True,
            forbidden_compile_macros=PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS,
        ),
        VECX_SOFTWARE_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=VECX_SOFTWARE_MAKE_VARIABLES,
            contract_name="VecX software",
            expected_build_keys=None,
            makefile="Makefile.libretro",
            forbidden_compile_macros=VECX_FORBIDDEN_COMPILE_MACROS,
        ),
        PCFX_PORTABLE_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=PCFX_PORTABLE_MAKE_VARIABLES,
            contract_name="PC-FX portable",
            expected_build_keys=NATIVE_GIT_MAKE_BUILD_KEYS,
            spec_validator="mednafen_pcfx_spec_is_well_formed",
            restriction_message=(
                "the PC-FX portable make-variable contract is restricted to "
                "the exact reviewed source, native version, and recipe"
            ),
            forbid_rules=(
                (
                    ("source_date_epoch",),
                    "the PC-FX portable make-variable contract forbids "
                    "source_date_epoch",
                ),
            ),
            forbidden_compile_macros=MEDNAFEN_PCFX_FORBIDDEN_COMPILE_MACROS,
        ),
        SNES9X2005_PLUS_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=SNES9X2005_PLUS_MAKE_VARIABLES,
            contract_name="Snes9x 2005 Plus",
            expected_build_keys=NATIVE_GIT_MAKE_BUILD_KEYS,
            spec_validator="native_git_version_spec_is_well_formed",
            spec_validator_args=("snes9x2005_plus",),
            restriction_message=(
                "the Snes9x 2005 Plus make-variable contract is restricted to "
                "the exact reviewed source, native version, and recipe"
            ),
            forbid_rules=(
                (
                    ("source_date_epoch",),
                    "the Snes9x 2005 Plus make-variable contract forbids "
                    "source_date_epoch",
                ),
            ),
        ),
        PARALLEL_N64_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=PARALLEL_N64_MAKE_VARIABLES,
            contract_name="Parallel N64 aarch64 GLES",
            # source_date_epoch is REQUIRED here, not forbidden: the original
            # "no date-embedding source" assumption was disproven by the v2
            # re-promote wave -- Glide64mk2 embeds __DATE__, which same-day
            # dual builds can never catch and any cross-day rebuild trips.
            expected_build_keys=GL_DYNAREC_BUILD_KEYS | {"source_date_epoch"},
            spec_validator="parallel_n64_spec_is_well_formed",
            restriction_message=(
                "the Parallel N64 make-variable contract is restricted to the "
                "exact reviewed source, recipe, and arm64-only target"
            ),
            forbid_rules=(
                (
                    ("git_version",),
                    "the Parallel N64 make-variable contract forbids "
                    "git_version",
                ),
            ),
            requires_epoch=True,
            golden_epoch=True,
        ),
        MUPEN64PLUS_NEXT_MAKE_PROFILE: MakeVariableProfileFacts(
            variables=MUPEN64PLUS_NEXT_MAKE_VARIABLES,
            contract_name="Mupen64Plus-Next aarch64 GLES",
            # Its tree declares NO submodules yet carries a stray gnulib
            # gitlink with no URL, so `submodule update --init` fails either
            # way. HAVE_PARALLEL_RSP defaults to 0, so none of those sources
            # are compiled anyway.
            expected_build_keys=GL_DYNAREC_BUILD_KEYS | {"submodules"},
            spec_validator="mupen64plus_next_spec_is_well_formed",
            restriction_message=(
                "the Mupen64Plus-Next make-variable contract is restricted to "
                "the exact reviewed source, recipe, and arm64-only target"
            ),
            forbid_rules=(
                (
                    ("git_version", "source_date_epoch"),
                    "the Mupen64Plus-Next make-variable contract forbids "
                    "git_version and source_date_epoch",
                ),
            ),
            golden_epoch=False,
        ),
    }


def make_variable_profile(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    keys = list(value)
    if any(not isinstance(name, str) for name in keys):
        return None
    if keys != sorted(keys):
        return None
    # Values are the exact integer 0/1 for every switch-shaped variable. A
    # reviewed profile may also carry a short identifier-shaped string
    # (parallel_n64 selects its dynarec with WITH_DYNAREC=aarch64); the profile
    # equality below is what actually admits it, so no free-form string ever
    # reaches the make command line.
    if any(
        not (
            (type(item) is int and item in {0, 1})
            or (
                type(item) is str
                and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", item)
                is not None
            )
        )
        for item in value.values()
    ):
        return None
    for profile_id, facts in _make_variable_profile_facts().items():
        if value == facts.variables:
            return profile_id
    return None


def make_variable_mapping_is_well_formed(value: object) -> bool:
    return make_variable_profile(value) is not None


def make_variable_contract_name(value: object) -> str:
    profile = make_variable_profile(value)
    facts = _make_variable_profile_facts().get(profile or "")
    return facts.contract_name if facts is not None else "unsupported"


def native_git_version_spec_is_well_formed(
    spec: object, core_id: object
) -> bool:
    if core_id == FBNEO_CORE_ID:
        return fbneo_spec_is_well_formed(spec)
    if core_id == MAME2003_PLUS_CORE_ID:
        return mame2003_plus_spec_is_well_formed(spec)
    if core_id == ATARI800_CORE_ID:
        return atari800_spec_is_well_formed(spec)
    if core_id == UZEM_CORE_ID:
        return uzem_spec_is_well_formed(spec)
    if core_id == MEDNAFEN_WSWAN_CORE_ID:
        return mednafen_wswan_spec_is_well_formed(spec)
    if core_id == MEDNAFEN_PCFX_CORE_ID:
        return mednafen_pcfx_spec_is_well_formed(spec)
    if core_id == MEDNAFEN_SUPERGRAFX_CORE_ID:
        return mednafen_supergrafx_spec_is_well_formed(spec)
    if core_id == POKEMINI_CORE_ID:
        return pokemini_spec_is_well_formed(spec)
    if core_id == FMSX_CORE_ID:
        return fmsx_spec_is_well_formed(spec)
    if core_id == BLUEMSX_CORE_ID:
        return bluemsx_spec_is_well_formed(spec)
    if core_id == CORE_2048_ID:
        return core_2048_spec_is_well_formed(spec)
    if core_id == LOWRESNX_CORE_ID:
        return lowresnx_spec_is_well_formed(spec)
    if core_id == POTATOR_CORE_ID:
        return potator_spec_is_well_formed(spec)
    if core_id == RACE_CORE_ID:
        return race_spec_is_well_formed(spec)
    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
    }:
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    identity = NATIVE_GIT_VERSION_SPEC_IDENTITIES.get(core_id)
    if identity is None:
        return False
    expected_build_keys = (
        NATIVE_GIT_MAKE_BUILD_KEYS
        if identity.get("make_variables") is not None
        else UZEM_NATIVE_GIT_VERSION_BUILD_KEYS
    )
    if identity.get("overlays") is not None:
        # An identity may declare exact reviewed overlays; the build must
        # then carry exactly that mapping and nothing else changes shape.
        expected_build_keys = frozenset(expected_build_keys) | {"overlays"}
    expected_git_version = {
        "derivation": NATIVE_GIT_VERSION_DERIVATION,
        "value": f" {identity['source_commit'][:7]}",
    }
    compiler_scope = identity.get("compiler_scope")
    if compiler_scope is not None:
        expected_git_version["compiler_scope"] = compiler_scope
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == expected_build_keys
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version") == expected_git_version
        and (
            identity.get("make_variables") is None
            or build.get("make_variables") == identity["make_variables"]
        )
        and (
            identity.get("overlays") is None
            or build.get("overlays") == identity["overlays"]
        )
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


def exact_native_git_version_contract(core_id: object) -> dict | None:
    if core_id == FBNEO_CORE_ID:
        return copy.deepcopy(FBNEO_GIT_VERSION)
    if core_id == MAME2003_PLUS_CORE_ID:
        return copy.deepcopy(MAME2003_PLUS_GIT_VERSION)
    identity = NATIVE_GIT_VERSION_SPEC_IDENTITIES.get(core_id)
    if identity is not None:
        contract = {
            "derivation": NATIVE_GIT_VERSION_DERIVATION,
            "value": f" {identity['source_commit'][:7]}",
        }
        if identity.get("compiler_scope") is not None:
            contract["compiler_scope"] = identity["compiler_scope"]
        return contract
    identity = NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES.get(core_id)
    if identity is not None:
        return {
            "derivation": NATIVE_GIT_VERSION_SHORT9_DERIVATION,
            "value": MGBA_NATIVE_GIT_VERSION,
            "compiler_scope": identity["compiler_scope"],
        }
    identity = NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES.get(core_id)
    if identity is not None:
        return {
            "derivation": NATIVE_GIT_VERSION_SHORT10_DERIVATION,
            "value": identity["git_version_value"],
        }
    return None


def native_git_version_short9_spec_is_well_formed(
    spec: object, core_id: object
) -> bool:
    return core_id == MGBA_CORE_ID and mgba_spec_is_well_formed(spec)


def native_git_version_short10_spec_is_well_formed(
    spec: object, core_id: object
) -> bool:
    if core_id == VICE_X64_CORE_ID:
        return vice_x64_spec_is_well_formed(spec)
    if core_id == VICE_XVIC_CORE_ID:
        return vice_xvic_spec_is_well_formed(spec)
    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
    }:
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    identity = NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES.get(core_id)
    if identity is None:
        return False
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == NATIVE_GIT_VERSION_SHORT10_BUILD_KEYS
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version")
        == {
            "derivation": NATIVE_GIT_VERSION_SHORT10_DERIVATION,
            "value": identity["git_version_value"],
        }
        and build.get("source_date_epoch") == identity["source_date_epoch"]
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


def native_git_describe_spec_is_well_formed(
    spec: object, core_id: object
) -> bool:
    if core_id == GEARBOY_CORE_ID:
        return gearboy_spec_is_well_formed(spec)
    if core_id == GEARSYSTEM_CORE_ID:
        return gearsystem_spec_is_well_formed(spec)
    if core_id == GEARCOLECO_CORE_ID:
        return gearcoleco_spec_is_well_formed(spec)
    if not isinstance(spec, dict) or set(spec) != {
        "workflow",
        "source",
        "build",
        "metadata",
        "targets",
    }:
        return False
    source = spec.get("source")
    build = spec.get("build")
    metadata = spec.get("metadata")
    identity = NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.get(core_id)
    if identity is None:
        return False
    return bool(
        isinstance(source, dict)
        and set(source) == {"url", "requested_ref", "commit", "tree"}
        and isinstance(build, dict)
        and set(build) == UZEM_NATIVE_GIT_VERSION_BUILD_KEYS
        and isinstance(metadata, dict)
        and set(metadata) == {"source_path", "artifact_name"}
        and spec.get("workflow") == identity["workflow"]
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and build.get("driver") == "libretro-super"
        and build.get("source_key") == identity["source_key"]
        and build.get("source_dir") == identity["source_dir"]
        and build.get("output_path") == identity["output_path"]
        and build.get("artifact_name") == identity["artifact_name"]
        and build.get("git_version")
        == {
            "derivation": NATIVE_GIT_DESCRIBE_DERIVATION,
            "value": identity["git_version_value"],
        }
        and metadata.get("source_path") == identity["metadata_source_path"]
        and metadata.get("artifact_name") == identity["metadata_artifact_name"]
        and spec.get("targets") == identity["targets"]
    )


def exact_native_git_describe_contract(core_id: object) -> dict | None:
    identity = NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.get(core_id)
    if identity is None:
        return None
    return {
        "derivation": NATIVE_GIT_DESCRIBE_DERIVATION,
        "value": identity["git_version_value"],
    }


def uzem_native_git_version_spec_is_well_formed(spec: object) -> bool:
    return uzem_spec_is_well_formed(spec)


def validated_make_variables(spec: dict) -> dict[str, int]:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    raw_make_controls = sorted(
        str(key)
        for key in build
        if isinstance(key, str)
        and key.upper()
        in {"GNUMAKEFLAGS", "MAKEFILES", "MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS"}
    )
    if raw_make_controls:
        raise PipelineError(
            "build raw GNU Make control variables are forbidden: "
            + ", ".join(raw_make_controls)
            + "; use typed build.make_variables"
        )
    if "make_variables" not in build:
        return {}
    if build.get("driver") != "libretro-super":
        raise PipelineError(
            "build.make_variables requires driver libretro-super"
        )
    if "compile_definitions" in build:
        raise PipelineError(
            "build.make_variables cannot be combined with compile_definitions"
        )
    raw = build["make_variables"]
    if not isinstance(raw, dict):
        raise PipelineError("build.make_variables must be an object")
    if any(not isinstance(name, str) for name in raw):
        raise PipelineError("build.make_variables names must be strings")
    reserved = sorted(set(raw).intersection(RESERVED_MAKE_VARIABLE_NAMES))
    if reserved:
        raise PipelineError(
            "build.make_variables contains reserved names: " + ", ".join(reserved)
        )
    keys = list(raw)
    if keys != sorted(keys):
        raise PipelineError("build.make_variables keys must be sorted")
    for name, value in raw.items():
        if type(value) is int and value in {0, 1}:
            continue
        if (
            type(value) is str
            and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value) is not None
        ):
            continue
        raise PipelineError(
            f"build.make_variables.{name} must be the exact integer 0 or 1, or "
            "a reviewed identifier-shaped string"
        )
    profile = make_variable_profile(raw)
    looks_like_vecx = (
        vecx_software_identity_is_well_formed(spec) or "HAS_GPU" in raw
    )
    if profile is None and looks_like_vecx:
        missing = sorted(set(VECX_SOFTWARE_MAKE_VARIABLES) - set(raw))
        extra = sorted(set(raw) - set(VECX_SOFTWARE_MAKE_VARIABLES))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        if not details:
            details.append("HAS_GPU must be the exact integer 0")
        raise PipelineError(
            "build.make_variables must match the exact VecX software contract: "
            + "; ".join(details)
        )
    looks_like_snes9x2005_plus = (
        build.get("source_key") == "snes9x2005_plus"
        or "USE_BLARGG_APU" in raw
    )
    if profile is None and looks_like_snes9x2005_plus:
        missing = sorted(set(SNES9X2005_PLUS_MAKE_VARIABLES) - set(raw))
        extra = sorted(set(raw) - set(SNES9X2005_PLUS_MAKE_VARIABLES))
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        if not details:
            details.append("USE_BLARGG_APU must be the exact integer 1")
        raise PipelineError(
            "build.make_variables must match the exact Snes9x 2005 Plus "
            "contract: " + "; ".join(details)
        )
    if profile is None:
        expected_names = set(PORTABLE_FFMPEG_MAKE_VARIABLES)
        missing = sorted(expected_names - set(raw))
        extra = sorted(set(raw) - expected_names)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("extra " + ", ".join(extra))
        if not details:
            mismatched = sorted(
                name
                for name, value in raw.items()
                if value != PORTABLE_FFMPEG_MAKE_VARIABLES[name]
            )
            details.append("wrong value for " + ", ".join(mismatched))
        raise PipelineError(
            "build.make_variables must contain exactly the portable FFmpeg keys: "
            + "; ".join(details)
        )
    facts = _make_variable_profile_facts()[profile]
    if facts.expected_build_keys is not None:
        if facts.spec_validator is not None and not globals()[
            facts.spec_validator
        ](spec, *facts.spec_validator_args):
            raise PipelineError(facts.restriction_message)
        for forbidden_keys, message in facts.forbid_rules:
            if any(key in build for key in forbidden_keys):
                raise PipelineError(message)
        if facts.requires_epoch and not source_date_epoch_is_well_formed(
            build.get("source_date_epoch")
        ):
            raise PipelineError(
                "build.source_date_epoch is required with build.make_variables"
            )
        expected_build_keys = facts.expected_build_keys
        contract_name = facts.contract_name
    else:
        if not vecx_software_identity_is_well_formed(spec):
            source = spec.get("source", {})
            expected_source = {
                "url": VECX_SOFTWARE_SPEC_IDENTITY["source_url"],
                "requested_ref": VECX_SOFTWARE_SPEC_IDENTITY[
                    "source_requested_ref"
                ],
                "commit": VECX_SOFTWARE_SPEC_IDENTITY["source_commit"],
                "tree": VECX_SOFTWARE_SPEC_IDENTITY["source_tree"],
            }
            if source != expected_source:
                raise PipelineError(
                    "the VecX software source identity must match the exact "
                    "reviewed commit and tree"
                )
            validation = spec.get("validation", {})
            if not isinstance(validation, dict) or validation.get(
                "forbidden_needed_prefixes"
            ) != VECX_SOFTWARE_SPEC_IDENTITY["forbidden_needed_prefixes"]:
                raise PipelineError(
                    "the VecX software dependency policy must forbid the exact "
                    "GL/EGL/GLES/OpenGL library prefixes"
                )
            raise PipelineError(
                "the VecX software make-variable contract is restricted to the "
                "exact VecX libretro-super recipe"
            )
        if "source_date_epoch" in build:
            raise PipelineError(
                "the VecX software make-variable contract forbids source_date_epoch"
            )
        expected_build_keys = VECX_SOFTWARE_BUILD_KEYS
        contract_name = "VecX software"
    unexpected_build_keys = sorted(set(build) - expected_build_keys)
    missing_build_keys = sorted(expected_build_keys - set(build))
    if unexpected_build_keys or missing_build_keys:
        details = []
        if missing_build_keys:
            details.append("missing " + ", ".join(missing_build_keys))
        if unexpected_build_keys:
            details.append("extra " + ", ".join(unexpected_build_keys))
        raise PipelineError(
            f"build with make_variables must contain exactly the {contract_name} "
            "build keys: " + "; ".join(details)
        )
    if profile == VECX_SOFTWARE_MAKE_PROFILE:
        source_commit = spec.get("source", {}).get("commit")
        raw_git_version = build.get("git_version")
        if not isinstance(raw_git_version, dict) or raw_git_version.get(
            "derivation"
        ) != NATIVE_GIT_VERSION_DERIVATION:
            raise PipelineError(
                "the VecX software make-variable contract requires the exact "
                "native-space-short7-v1 git_version contract"
            )
        expected_native_value = f" {source_commit[:7]}"
        if raw_git_version.get("value") != expected_native_value:
            raise PipelineError(
                "build.git_version.value must equal a space plus the first seven "
                f"source commit characters: {expected_native_value!r}"
            )
        if not git_version_contract_is_well_formed(
            raw_git_version, source_commit
        ):
            raise PipelineError(
                "the VecX software make-variable contract requires the exact "
                "native-space-short7-v1 git_version contract"
            )
    return {name: raw[name] for name in sorted(raw)}


def git_version_contract_is_well_formed(
    value: object, source_commit: object
) -> bool:
    if not isinstance(source_commit, str) or not SHA1_RE.fullmatch(source_commit):
        return False
    if (
        isinstance(value, dict)
        and value.get("derivation") == FBNEO_GIT_VERSION_DERIVATION
    ):
        return bool(
            source_commit == FBNEO_SOURCE_COMMIT
            and fbneo_git_version_contract_is_well_formed(value)
        )
    required_keys = {"derivation", "value"}
    allowed_keys = required_keys.union({"compiler_scope"})
    if not (
        isinstance(value, dict)
        and required_keys.issubset(value)
        and set(value).issubset(allowed_keys)
    ):
        return False
    derivation = value.get("derivation")
    raw_value = value.get("value")
    if derivation == GIT_VERSION_DERIVATION:
        return bool(
            isinstance(raw_value, str)
            and GIT_VERSION_RE.fullmatch(raw_value)
            and raw_value == f"-{source_commit[:7]}"
            and (
                "compiler_scope" not in value
                or value.get("compiler_scope") == GIT_VERSION_CXX_SCOPE
            )
        )
    if derivation == NATIVE_GIT_VERSION_DERIVATION:
        return bool(
            isinstance(raw_value, str)
            and NATIVE_GIT_VERSION_RE.fullmatch(raw_value)
            and raw_value == f" {source_commit[:7]}"
            and (
                "compiler_scope" not in value
                or value.get("compiler_scope") in GIT_VERSION_COMPILER_SCOPES
            )
        )
    if derivation == NATIVE_GIT_VERSION_SHORT8_DERIVATION:
        return bool(
            source_commit == MAME2003_PLUS_SOURCE_COMMIT
            and mame2003_plus_git_version_contract_is_well_formed(value)
        )
    if derivation == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
        identity = NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES[MGBA_CORE_ID]
        return bool(
            set(value) == allowed_keys
            and source_commit == identity["source_commit"]
            and isinstance(raw_value, str)
            and NATIVE_GIT_VERSION_SHORT9_RE.fullmatch(raw_value)
            and raw_value == MGBA_NATIVE_GIT_VERSION
            and value.get("compiler_scope") == identity["compiler_scope"]
        )
    if derivation == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
        return bool(
            set(value) == required_keys
            and isinstance(raw_value, str)
            and NATIVE_GIT_VERSION_SHORT10_RE.fullmatch(raw_value)
            and raw_value == f" {source_commit[:10]}"
        )
    if derivation == NATIVE_GIT_DESCRIBE_DERIVATION:
        return bool(
            set(value) == required_keys
            and isinstance(raw_value, str)
            and raw_value
            == NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT.get(source_commit)
        )
    return False


def validated_git_version(spec: dict) -> dict | None:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    if "git_version" not in build:
        return None
    if build.get("driver") != "libretro-super":
        raise PipelineError("build.git_version requires driver libretro-super")
    if (
        "compile_definitions" in build
        and not fbneo_spec_is_well_formed(spec)
    ):
        raise PipelineError(
            "build.git_version cannot be combined with compile_definitions "
            "outside the exact reviewed FBNeo contract"
        )
    raw = build["git_version"]
    if not isinstance(raw, dict):
        raise PipelineError("build.git_version must be an object")
    derivation = raw.get("derivation")
    if derivation == FBNEO_GIT_VERSION_DERIVATION:
        if not fbneo_spec_is_well_formed(spec):
            raise PipelineError(
                "fbneo-native-short9-date-v1 is restricted to the exact "
                "reviewed FBNeo source, epoch, recipe, metadata, target, "
                "compiler scope, Git date, and command-scoped Make contract"
            )
        return copy.deepcopy(FBNEO_GIT_VERSION)
    required_keys = {"derivation", "value"}
    allowed_keys = required_keys.union({"compiler_scope"})
    if not required_keys.issubset(raw) or not set(raw).issubset(allowed_keys):
        raise PipelineError(
            "build.git_version must contain exactly derivation and value, "
            "with optional compiler_scope"
        )
    if derivation not in {
        GIT_VERSION_DERIVATION,
        NATIVE_GIT_VERSION_DERIVATION,
        NATIVE_GIT_VERSION_SHORT8_DERIVATION,
        NATIVE_GIT_VERSION_SHORT9_DERIVATION,
        NATIVE_GIT_VERSION_SHORT10_DERIVATION,
        NATIVE_GIT_DESCRIBE_DERIVATION,
    }:
        raise PipelineError(
            "build.git_version.derivation must be hyphen-short7-v1, "
            "native-space-short7-v1, native-space-short8-v1, "
            "native-space-short9-v1, "
            "native-space-short10-v1, or native-git-describe-v1"
        )
    source_commit = spec.get("source", {}).get("commit")
    if not isinstance(source_commit, str) or not SHA1_RE.fullmatch(source_commit):
        raise PipelineError(
            "build.git_version requires a full lowercase source commit SHA"
        )
    is_native = derivation == NATIVE_GIT_VERSION_DERIVATION
    is_native_short8 = derivation == NATIVE_GIT_VERSION_SHORT8_DERIVATION
    is_native_short9 = derivation == NATIVE_GIT_VERSION_SHORT9_DERIVATION
    is_native_short10 = derivation == NATIVE_GIT_VERSION_SHORT10_DERIVATION
    is_native_describe = derivation == NATIVE_GIT_DESCRIBE_DERIVATION
    if is_native_describe:
        expected_value = NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT.get(source_commit)
        if expected_value is None:
            raise PipelineError(
                "native-git-describe-v1 is restricted to an exact reviewed "
                "source commit and describe value"
            )
    elif is_native_short8:
        expected_value = MAME2003_PLUS_NATIVE_GIT_VERSION
    elif is_native_short9:
        if build.get("source_key") != MGBA_CORE_ID:
            raise PipelineError(
                "native-space-short9-v1 is restricted to the exact reviewed "
                "mGBA source and recipe"
            )
        expected_value = MGBA_NATIVE_GIT_VERSION
    elif is_native_short10:
        expected_value = f" {source_commit[:10]}"
    else:
        expected_value = (
            f" {source_commit[:7]}" if is_native else f"-{source_commit[:7]}"
        )
    value = raw.get("value")
    if is_native_describe:
        value_is_valid = value == expected_value
    elif is_native_short8:
        value_is_valid = bool(
            source_commit == MAME2003_PLUS_SOURCE_COMMIT
            and mame2003_plus_git_version_contract_is_well_formed(raw)
        )
    elif is_native_short9:
        value_is_valid = bool(
            isinstance(value, str)
            and NATIVE_GIT_VERSION_SHORT9_RE.fullmatch(value)
            and value == expected_value
        )
    elif is_native_short10:
        value_is_valid = bool(
            isinstance(value, str)
            and NATIVE_GIT_VERSION_SHORT10_RE.fullmatch(value)
            and value == expected_value
        )
    else:
        value_is_valid = bool(
            isinstance(value, str)
            and (NATIVE_GIT_VERSION_RE if is_native else GIT_VERSION_RE).fullmatch(
                value
            )
            and value == expected_value
        )
    if not value_is_valid:
        if is_native_describe:
            raise PipelineError(
                "build.git_version.value must equal the exact reviewed native "
                f"git describe value: {expected_value!r}"
            )
        prefix = (
            "a space"
            if (
                is_native
                or is_native_short8
                or is_native_short9
                or is_native_short10
            )
            else "'-'"
        )
        length = (
            "eight"
            if is_native_short8
            else "nine"
            if is_native_short9
            else "ten"
            if is_native_short10
            else "seven"
        )
        raise PipelineError(
            f"build.git_version.value must equal {prefix} plus the first {length} "
            f"source commit characters: {expected_value!r}"
        )
    has_compiler_scope = "compiler_scope" in raw
    compiler_scope = raw.get("compiler_scope")
    allowed_compiler_scopes = (
        GIT_VERSION_COMPILER_SCOPES
        if is_native or is_native_short8 or is_native_short9
        else frozenset({GIT_VERSION_CXX_SCOPE})
    )
    if has_compiler_scope and compiler_scope not in allowed_compiler_scopes:
        allowed_scope_text = (
            "c or cxx"
            if is_native or is_native_short8 or is_native_short9
            else "cxx"
        )
        raise PipelineError(
            "build.git_version.compiler_scope must be "
            f"{allowed_scope_text} when present"
        )
    if compiler_scope == GIT_VERSION_C_SCOPE and not (
        (is_native or is_native_short8 or is_native_short9)
        and build.get("source_key") in NATIVE_GIT_VERSION_C_SCOPE_CORE_IDS
    ):
        raise PipelineError(
            "build.git_version.compiler_scope c is restricted to the exact "
            "reviewed C-scoped native version contracts"
        )
    if (is_native_short10 or is_native_describe) and has_compiler_scope:
        contract_name = (
            NATIVE_GIT_VERSION_SHORT10_DERIVATION
            if is_native_short10
            else NATIVE_GIT_DESCRIBE_DERIVATION
        )
        raise PipelineError(
            f"{contract_name} requires its compile token on all C and C++ "
            "target compiler commands"
        )
    if "make_variables" in build:
        is_vecx_combined = (
            is_native
            and make_variable_profile(build.get("make_variables"))
            == VECX_SOFTWARE_MAKE_PROFILE
            and vecx_software_identity_is_well_formed(spec)
        )
        is_pcfx_combined = (
            is_native
            and make_variable_profile(build.get("make_variables"))
            == PCFX_PORTABLE_MAKE_PROFILE
            and mednafen_pcfx_spec_is_well_formed(spec)
        )
        is_snes9x2005_plus_combined = (
            is_native
            and make_variable_profile(build.get("make_variables"))
            == SNES9X2005_PLUS_MAKE_PROFILE
            and native_git_version_spec_is_well_formed(
                spec, "snes9x2005_plus"
            )
        )
        if not (
            is_vecx_combined
            or is_pcfx_combined
            or is_snes9x2005_plus_combined
        ):
            raise PipelineError(
                "build.git_version cannot be combined with make_variables "
                "outside an exact reviewed combined native contract"
            )
    elif is_native and not native_git_version_spec_is_well_formed(
        spec, build.get("source_key")
    ):
        raise PipelineError(
            "native-space-short7-v1 is restricted to an exact reviewed "
            "combined make-variable contract or standalone native version "
            "contract"
        )
    elif is_native_short8 and not mame2003_plus_spec_is_well_formed(spec):
        raise PipelineError(
            "native-space-short8-v1 is restricted to the exact reviewed "
            "MAME2003+ source, epoch, recipe, metadata, target, compiler "
            "scope, and command-scoped Make contract"
        )
    elif is_native_short9 and not native_git_version_short9_spec_is_well_formed(
        spec, build.get("source_key")
    ):
        raise PipelineError(
            "native-space-short9-v1 is restricted to the exact reviewed mGBA "
            "source, recipe, metadata, target, compiler scope, and Git "
            "abbreviation contract"
        )
    elif is_native_short10 and not native_git_version_short10_spec_is_well_formed(
        spec, build.get("source_key")
    ):
        raise PipelineError(
            "native-space-short10-v1 is restricted to the exact reviewed VICE "
            "source, epoch, recipe, metadata, target, and Git abbreviation "
            "contract"
        )
    elif is_native_describe and not native_git_describe_spec_is_well_formed(
        spec, build.get("source_key")
    ):
        raise PipelineError(
            "native-git-describe-v1 is restricted to an exact reviewed source, "
            "recipe, metadata, target, and compiler-macro contract"
        )
    if is_native_short8:
        return copy.deepcopy(MAME2003_PLUS_GIT_VERSION)
    contract = {"derivation": derivation, "value": expected_value}
    if has_compiler_scope:
        contract["compiler_scope"] = compiler_scope
    return contract


def make_output_sync_prefix(variables: object) -> str:
    """Make flags that force deterministic parallel output for a profile.

    The portable FFmpeg build fans out ~1268 concurrent compiles whose stderr
    (compiler diagnostics and the long -DCONFIG_* command echoes) otherwise
    interleaves at non-reproducible line boundaries, defeating the reproduction
    log comparison even though the produced binary is byte-identical.
    ``--output-sync=recurse`` emits each recipe's output as one atomic block, so
    the log line multiset is reproducible (block order may still vary). No other
    make-variable profile requests it, keeping their frozen recipes unchanged.
    """

    if make_variable_profile(variables) == PORTABLE_FFMPEG_MAKE_PROFILE:
        return "--output-sync=recurse "
    return ""


def canonical_makeflags(spec: dict) -> str:
    variables = validated_make_variables(spec)
    return make_output_sync_prefix(variables) + " ".join(
        f"{name}={value}" for name, value in variables.items()
    )


def validated_source_date_epoch(spec: dict) -> int | None:
    build = spec.get("build", {})
    if "source_date_epoch" not in build:
        return None
    value = build["source_date_epoch"]
    if not source_date_epoch_is_well_formed(value):
        raise PipelineError(
            "build.source_date_epoch must be an exact integer between 1 and "
            f"{MAX_SOURCE_DATE_EPOCH}"
        )
    return value


def validated_recipe_profile(spec: dict) -> dict | None:
    """Return the one reviewed non-generic libretro-super recipe profile."""

    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    raw = build.get("recipe_profile")
    looks_like_picodrive = build.get("source_key") == PICODRIVE_CORE_ID
    if raw is None:
        if looks_like_picodrive:
            raise PipelineError(
                "build.recipe_profile is required by the Picodrive source contract"
            )
        return None
    if build.get("driver") != "libretro-super":
        raise PipelineError(
            "build.recipe_profile requires driver libretro-super"
        )
    forbidden_combinations = sorted(
        {
            "cmake",
            "generated_source",
            "git_version",
            "make_variables",
            "platforms",
        }.intersection(build)
    )
    if forbidden_combinations:
        raise PipelineError(
            "build.recipe_profile cannot be combined with: "
            + ", ".join(forbidden_combinations)
        )
    if (
        not picodrive_recipe_profile_is_well_formed(raw)
        or not picodrive_identity_is_well_formed(spec)
    ):
        raise PipelineError(
            "build.recipe_profile is restricted to the exact reviewed "
            "Picodrive source-root recipe"
        )
    return copy.deepcopy(raw)


def source_date_epoch_is_well_formed(value: object) -> bool:
    return type(value) is int and 1 <= value <= MAX_SOURCE_DATE_EPOCH


def build_source_date_epoch_matches(build: object, expected: int | None) -> bool:
    if not isinstance(build, dict):
        return False
    if expected is None:
        return "source_date_epoch" not in build
    return (
        "source_date_epoch" in build
        and source_date_epoch_is_well_formed(build["source_date_epoch"])
        and build["source_date_epoch"] == expected
    )


def exact_relative_path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PipelineError(f"{label} must be a non-empty relative path")
    relative = Path(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise PipelineError(f"{label} must be an exact relative path")
    return value


def metadata_matches_replacement(
    metadata: object, replacement: object | None
) -> bool:
    if replacement is None:
        return True
    return bool(
        isinstance(metadata, dict)
        and metadata_replacement_contract_is_well_formed(replacement)
        and metadata.get("status") == "valid"
        and metadata.get("sha256") == replacement["replacement_sha256"]
    )


def validated_metadata_replacement(spec: dict) -> dict | None:
    metadata = spec.get("metadata", {})
    if not isinstance(metadata, dict):
        raise PipelineError("metadata must be an object")
    raw = metadata.get("replacement")
    is_vecx_identity = (
        make_variable_profile(spec.get("build", {}).get("make_variables"))
        == VECX_SOFTWARE_MAKE_PROFILE
        and vecx_software_identity_is_well_formed(spec)
    )
    is_atari800_identity = atari800_identity_is_well_formed(spec)
    is_picodrive_identity = picodrive_identity_is_well_formed(spec)
    if raw is None:
        if is_vecx_identity:
            raise PipelineError(
                "metadata.replacement is required by the VecX software contract"
            )
        if is_atari800_identity:
            raise PipelineError(
                "metadata.replacement is required by the Atari800 source contract"
            )
        if is_picodrive_identity:
            raise PipelineError(
                "metadata.replacement is required by the Picodrive source contract"
            )
        return None
    if is_vecx_identity:
        expected_kind = VECX_METADATA_REPLACEMENT_KIND
        expected_path = VECX_METADATA_REPLACEMENT_PATH
        expected_preimage = VECX_METADATA_PREIMAGE_SHA256
        expected_replacement = VECX_METADATA_REPLACEMENT_SHA256
        replacement_label = "VecX software"
        replacement_proof = vecx_metadata_replacement_contract_is_well_formed
    elif is_atari800_identity:
        expected_kind = ATARI800_METADATA_REPLACEMENT_KIND
        expected_path = ATARI800_METADATA_REPLACEMENT_PATH
        expected_preimage = ATARI800_METADATA_PREIMAGE_SHA256
        expected_replacement = ATARI800_METADATA_REPLACEMENT_SHA256
        replacement_label = "Atari800 source"
        replacement_proof = atari800_metadata_replacement_contract_is_well_formed
    elif is_picodrive_identity:
        expected_kind = PICODRIVE_METADATA_REPLACEMENT_KIND
        expected_path = PICODRIVE_METADATA_REPLACEMENT_PATH
        expected_preimage = PICODRIVE_METADATA_PREIMAGE_SHA256
        expected_replacement = PICODRIVE_METADATA_REPLACEMENT_SHA256
        replacement_label = "Picodrive source"
        replacement_proof = (
            picodrive_metadata_replacement_contract_is_well_formed
        )
    else:
        raise PipelineError(
            "metadata.replacement is restricted to an exact reviewed core contract"
        )
    if not isinstance(raw, dict):
        raise PipelineError("metadata.replacement must be an object")
    expected_keys = {
        "kind",
        "path",
        "preimage_sha256",
        "replacement_sha256",
    }
    if set(raw) != expected_keys:
        raise PipelineError(
            "metadata.replacement must contain the exact metadata replacement fields"
        )
    if raw.get("kind") != expected_kind:
        raise PipelineError("metadata.replacement.kind must be whole-file-v1")
    if raw.get("path") != expected_path:
        raise PipelineError(
            "metadata.replacement.path does not match the reviewed core contract"
        )
    if raw.get("preimage_sha256") != expected_preimage:
        raise PipelineError(
            "metadata.replacement.preimage_sha256 does not match the reviewed source"
        )
    if (
        not isinstance(raw.get("replacement_sha256"), str)
        or not SHA256_RE.fullmatch(raw["replacement_sha256"])
        or raw["replacement_sha256"] == raw["preimage_sha256"]
    ):
        raise PipelineError(
            "metadata.replacement.replacement_sha256 is invalid"
        )
    if raw["replacement_sha256"] != expected_replacement:
        raise PipelineError(
            "metadata.replacement.replacement_sha256 does not match the "
            f"reviewed {replacement_label} metadata"
        )
    if not replacement_proof(raw):
        raise PipelineError(
            "metadata.replacement must be the exact reviewed whole-file-v1 "
            f"{replacement_label} contract"
        )
    assert isinstance(raw, dict)
    replacement_path = safe_child(
        ROOT, raw["path"], "metadata replacement path"
    )
    if not replacement_path.is_file():
        raise PipelineError("metadata replacement file is missing")
    if sha256_file(replacement_path) != raw["replacement_sha256"]:
        raise PipelineError(
            "metadata.replacement.replacement_sha256 does not match its file"
        )
    if is_vecx_identity:
        replacement_text = replacement_path.read_text(encoding="utf-8")
        if (
            'hw_render = "false"' not in replacement_text
            or "required_hw_api" in replacement_text
            or "hardware-rendered" in replacement_text.lower()
        ):
            raise PipelineError(
                "metadata replacement does not describe a software-only renderer"
            )
    return {key: raw[key] for key in sorted(raw)}


def generated_source_contract_is_well_formed(value: object) -> bool:
    """Recognize the versioned, path-safe generated-source record shape."""

    return bool(
        isinstance(value, dict)
        and set(value) == {"kind", "path", "sha256"}
        and value.get("kind") == "post-build-sha256-v1"
        and isinstance(value.get("path"), str)
        and GENERATED_SOURCE_PATH_RE.fullmatch(value["path"]) is not None
        and isinstance(value.get("sha256"), str)
        and SHA256_RE.fullmatch(value["sha256"]) is not None
    )


def validated_generated_source(spec: dict) -> dict | None:
    """Return the one reviewed post-build generated-source contract."""

    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    raw = build.get("generated_source")
    if raw is None:
        return None
    if (
        not generated_source_contract_is_well_formed(raw)
        or not core_81_spec_is_well_formed(spec)
        or not core_81_generated_source_contract_is_well_formed(raw)
    ):
        raise PipelineError(
            "build.generated_source is restricted to the exact EightyOne "
            "post-build source digest contract"
        )
    return copy.deepcopy(raw)


def validate_build_overlays(
    overlays: object,
    core_id: str | None,
    source_dir: str,
    targets: object,
) -> dict:
    """Validate driver-agnostic git-apply patch overlays declared on a build.

    Overlays are a per-target map of single-file git-apply-v1 patches under
    patches/<core>/, each pinned by patch/preimage/postimage sha256. Any build
    type may carry overlays; the driver's build script applies them after
    checkout via overlay_apply_shell(). Returns a deep copy of the validated
    overlays (an empty dict when none are declared).
    """

    if not isinstance(overlays, dict):
        raise PipelineError("build.overlays must be an object")
    unexpected_overlay_targets = sorted(set(overlays) - set(targets))
    if unexpected_overlay_targets:
        raise PipelineError(
            "build.overlays contains a non-target architecture: "
            + ", ".join(unexpected_overlay_targets)
        )
    overlay_keys = {
        "kind",
        "patch_path",
        "patch_sha256",
        "source_path",
        "preimage_sha256",
        "postimage_sha256",
    }
    # `submodule_path` is optional and reviewed: it names the checked-out
    # submodule that owns source_path, because git apply and git diff at the
    # superproject cannot see or mutate files behind a gitlink (flycast's
    # vendored libchdr/lzma is the first consumer).
    optional_overlay_keys = {"submodule_path"}
    for arch, target_overlays in overlays.items():
        if not isinstance(target_overlays, list) or not target_overlays:
            raise PipelineError(f"build.overlays.{arch} must be a non-empty array")
        raw_source_paths = [
            overlay.get("source_path") if isinstance(overlay, dict) else None
            for overlay in target_overlays
        ]
        if any(not isinstance(path, str) for path in raw_source_paths) or (
            raw_source_paths != sorted(raw_source_paths)
        ):
            raise PipelineError(
                f"build.overlays.{arch} must be sorted by source_path"
            )
        seen_source_paths: set[str] = set()
        seen_patch_paths: set[str] = set()
        for index, overlay in enumerate(target_overlays):
            label = f"build.overlays.{arch}[{index}]"
            if not isinstance(overlay, dict) or not (
                overlay_keys <= set(overlay)
                and set(overlay) <= overlay_keys | optional_overlay_keys
            ):
                raise PipelineError(f"{label} must contain the exact overlay fields")
            if "submodule_path" in overlay:
                overlay_submodule = exact_relative_path(
                    overlay["submodule_path"], f"{label}.submodule_path"
                )
                if not str(overlay.get("source_path", "")).startswith(
                    overlay_submodule + "/"
                ):
                    raise PipelineError(
                        f"{label}.submodule_path must be a prefix of source_path"
                    )
            if overlay.get("kind") != "git-apply-v1":
                raise PipelineError(f"{label}.kind must be git-apply-v1")
            patch_path = exact_relative_path(
                overlay.get("patch_path"), f"{label}.patch_path"
            )
            expected_patch_prefix = f"patches/{core_id or source_dir}/"
            if not patch_path.startswith(expected_patch_prefix) or not patch_path.endswith(
                ".patch"
            ):
                raise PipelineError(
                    f"{label}.patch_path must name a core-scoped tracked patch"
                )
            source_path = exact_relative_path(
                overlay.get("source_path"), f"{label}.source_path"
            )
            if source_path in seen_source_paths or patch_path in seen_patch_paths:
                raise PipelineError(f"{label} repeats an overlay path")
            seen_source_paths.add(source_path)
            seen_patch_paths.add(patch_path)
            for digest_key in (
                "patch_sha256",
                "preimage_sha256",
                "postimage_sha256",
            ):
                if not isinstance(overlay.get(digest_key), str) or not SHA256_RE.fullmatch(
                    overlay[digest_key]
                ):
                    raise PipelineError(f"{label}.{digest_key} is invalid")
            if overlay["preimage_sha256"] == overlay["postimage_sha256"]:
                raise PipelineError(f"{label} preimage and postimage must differ")
            patch_file = require_manifest_reference_path(
                {"path": patch_path}, ROOT / "patches", f"{label}.patch"
            )
            if not patch_file.is_file():
                raise PipelineError(f"{label}.patch is missing")
            if sha256_file(patch_file) != overlay["patch_sha256"]:
                raise PipelineError(f"{label}.patch_sha256 does not match")
            try:
                patch_text = patch_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise PipelineError(f"{label}.patch is not readable UTF-8 text: {exc}") from exc
            expected_header = f"diff --git a/{source_path} b/{source_path}\n"
            if (
                not patch_text.startswith(expected_header)
                or patch_text.count("diff --git ") != 1
                or patch_text.count(f"--- a/{source_path}\n") != 1
                or patch_text.count(f"+++ b/{source_path}\n") != 1
            ):
                raise PipelineError(
                    f"{label}.patch must be a single-file git-apply-v1 patch"
                )
            numstat = run(
                [
                    "git",
                    "apply",
                    "--numstat",
                    "-z",
                    "--whitespace=error-all",
                    str(patch_file),
                ],
                cwd=ROOT,
            ).stdout
            numstat_entries = [entry for entry in numstat.split("\0") if entry]
            if len(numstat_entries) != 1:
                raise PipelineError(f"{label}.patch changes more than one path")
            fields = numstat_entries[0].split("\t", 2)
            if (
                len(fields) != 3
                or fields[0] == "-"
                or fields[1] == "-"
                or fields[2] != source_path
            ):
                raise PipelineError(
                    f"{label}.patch is binary or changes an unexpected path"
                )
    return copy.deepcopy(overlays)


def validated_direct_cmake(spec: dict, core_id: str | None = None) -> dict | None:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    if build.get("driver") != "direct-cmake":
        if "cmake" in build:
            raise PipelineError(
                "build direct-CMake fields require driver direct-cmake: cmake"
            )
        return None

    allowed_build_keys = {
        "driver",
        "source_dir",
        "output_path",
        "artifact_name",
        "source_date_epoch",
        "cmake",
        "overlays",
    }
    unexpected_build_keys = sorted(set(build) - allowed_build_keys)
    if unexpected_build_keys:
        raise PipelineError(
            "build direct-cmake contains unsupported fields: "
            + ", ".join(unexpected_build_keys)
        )
    source_dir = build.get("source_dir")
    if not isinstance(source_dir, str) or not LOCAL_ID_RE.fullmatch(source_dir):
        raise PipelineError("build.source_dir is invalid for direct-cmake")
    if core_id is not None and source_dir != core_id:
        raise PipelineError("build.source_dir must match its direct-cmake core ID")
    output_path = exact_relative_path(
        build.get("output_path"), "build.output_path"
    )
    artifact_name = build.get("artifact_name")
    # The artifact may sit in a contained build subdirectory (e.g. CMake that
    # emits into `bin/<target>.so`, like tic80); require only that the basename
    # is the artifact name (exact_relative_path already forbids `..`/absolute).
    # A rebranded fork may rename -- but only to its OWN canonical core name
    # (KMFDManic/swanstation builds `swanstation_libretro.so` and ships as
    # `km_duckswanstation_xtreme_amped_libretro.so`). Renaming to anything else
    # stays rejected, so an artifact can never impersonate another core.
    # `source_dir` is the identity anchor here: catalog validation enforces
    # source_dir == core_id for direct-cmake, and unlike core_id it is present
    # in the spec at every call site (the build path validates without the
    # catalog key in hand).
    if Path(output_path).name != artifact_name and (
        artifact_name != f"{build.get('source_dir')}_libretro.so"
    ):
        raise PipelineError(
            "build.output_path basename must equal build.artifact_name for direct-cmake"
        )
    if validated_source_date_epoch(spec) is None:
        raise PipelineError("build.source_date_epoch is required for direct-cmake")

    cmake = build.get("cmake")
    required_cmake_keys = {"generator", "build_type", "target", "systems"}
    # Optional reviewed fields: `source_subdir` is an in-tree CMakeLists directory
    # relative to the clone root (tic80's `core`, squirreljme's `nanocoat`);
    # `defines` are the exact `-D<name>=<value>` configure flags that select the
    # libretro-only build and disable the desktop/SDL/GL frontend (tic80 and
    # ardens both pull SDL2/X11 without them). When absent, CMake configures at
    # the clone root with no extra defines, as before.
    if (
        not isinstance(cmake, dict)
        or not required_cmake_keys <= set(cmake)
        or not set(cmake) <= required_cmake_keys | {"source_subdir", "defines"}
    ):
        raise PipelineError("build.cmake must contain the exact direct-CMake fields")
    cmake_source_subdir = None
    if "source_subdir" in cmake:
        cmake_source_subdir = exact_relative_path(
            cmake["source_subdir"], "build.cmake.source_subdir"
        )
    cmake_defines = None
    if "defines" in cmake:
        defines = cmake["defines"]
        if not isinstance(defines, dict) or not defines:
            raise PipelineError("build.cmake.defines must be a non-empty object")
        for name, value in defines.items():
            if (
                not isinstance(name, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                or not isinstance(value, str)
                or re.fullmatch(r"[A-Za-z0-9_./+=-]+", value) is None
            ):
                raise PipelineError("build.cmake.defines has an invalid entry")
        cmake_defines = dict(defines)
    if cmake.get("generator") != "Unix Makefiles":
        raise PipelineError("build.cmake.generator must be Unix Makefiles")
    if cmake.get("build_type") != "Release":
        raise PipelineError("build.cmake.build_type must be Release")
    target = cmake.get("target")
    # The target is validated against what the build PRODUCES (the output_path
    # basename), which equals the artifact name everywhere except a rebranded
    # fork, where the rename above already restricts the artifact to the core's
    # own canonical name.
    if (
        not isinstance(target, str)
        or not re.fullmatch(r"[A-Za-z0-9_+-]+", target)
        or Path(output_path).name != f"{target}.so"
    ):
        raise PipelineError(
            "build.cmake.target must be a safe target matching the artifact name"
        )
    systems = cmake.get("systems")
    targets = spec.get("targets")
    if not isinstance(targets, list) or not isinstance(systems, dict):
        raise PipelineError("build.cmake.systems requires valid core targets")
    if set(systems) != set(targets):
        raise PipelineError("build.cmake.systems must exactly cover core targets")
    expected_processors = {"arm64": "aarch64", "armhf": "arm"}
    for arch, system in systems.items():
        if arch not in expected_processors:
            raise PipelineError(f"build.cmake.systems architecture is invalid: {arch}")
        # Optional reviewed per-architecture `defines` (flycast selects GLES3 on
        # arm64 and GLES2 on armhf); they merge over the common defines in the
        # per-target projection. Everything else in the system block stays the
        # exact target identity.
        if not isinstance(system, dict) or not (
            set(system) == {"name", "processor"}
            or set(system) == {"name", "processor", "defines"}
        ):
            raise PipelineError(
                f"build.cmake.systems.{arch} must contain name and processor"
            )
        if {
            "name": system.get("name"),
            "processor": system.get("processor"),
        } != {
            "name": "Linux",
            "processor": expected_processors[arch],
        }:
            raise PipelineError(
                f"build.cmake.systems.{arch} does not identify the target system"
            )
        if "defines" in system:
            arch_defines = system["defines"]
            if not isinstance(arch_defines, dict) or not arch_defines:
                raise PipelineError(
                    f"build.cmake.systems.{arch}.defines must be a non-empty object"
                )
            for name, value in arch_defines.items():
                if (
                    not isinstance(name, str)
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None
                    or not isinstance(value, str)
                    or re.fullmatch(r"[A-Za-z0-9_./+=-]+", value) is None
                ):
                    raise PipelineError(
                        f"build.cmake.systems.{arch}.defines has an invalid entry"
                    )

    overlays = validate_build_overlays(
        build.get("overlays", {}), core_id, source_dir, targets
    )
    result = {
        "generator": cmake["generator"],
        "build_type": cmake["build_type"],
        "target": cmake["target"],
        "systems": copy.deepcopy(systems),
        "overlays": copy.deepcopy(overlays),
    }
    # Only surface the optional fields when set, so cores without them keep a
    # byte-identical contract (and stored golden) to before they existed.
    if cmake_source_subdir is not None:
        result["source_subdir"] = cmake_source_subdir
    if cmake_defines is not None:
        result["defines"] = cmake_defines
    return result


def direct_cmake_contract_for_target(spec: dict, arch: str) -> dict | None:
    contract = validated_direct_cmake(spec)
    if contract is None:
        return None
    if arch not in spec.get("targets", []):
        raise PipelineError(f"direct-CMake architecture is not enabled: {arch}")
    system = copy.deepcopy(contract["systems"][arch])
    arch_defines = system.pop("defines", None)
    projected_cmake = {
        "generator": contract["generator"],
        "build_type": contract["build_type"],
        "target": contract["target"],
        "system": system,
    }
    if contract.get("source_subdir") is not None:
        projected_cmake["source_subdir"] = contract["source_subdir"]
    merged_defines = dict(contract.get("defines") or {})
    if arch_defines:
        merged_defines.update(arch_defines)
    if merged_defines:
        projected_cmake["defines"] = merged_defines
    return {
        "cmake": projected_cmake,
        "overlays": copy.deepcopy(contract["overlays"].get(arch, [])),
    }


def validated_direct_cargo(spec: dict, core_id: str | None = None) -> dict | None:
    build = spec.get("build", {})
    if not isinstance(build, dict):
        raise PipelineError("build must be an object")
    if build.get("driver") != "direct-cargo":
        if "cargo" in build:
            raise PipelineError(
                "build direct-cargo fields require driver direct-cargo: cargo"
            )
        return None

    allowed_build_keys = {
        "driver",
        "source_dir",
        "output_path",
        "artifact_name",
        "source_date_epoch",
        "cargo",
    }
    unexpected_build_keys = sorted(set(build) - allowed_build_keys)
    if unexpected_build_keys:
        raise PipelineError(
            "build direct-cargo contains unsupported fields: "
            + ", ".join(unexpected_build_keys)
        )
    source_dir = build.get("source_dir")
    if not isinstance(source_dir, str) or not LOCAL_ID_RE.fullmatch(source_dir):
        raise PipelineError("build.source_dir is invalid for direct-cargo")
    if core_id is not None and source_dir != core_id:
        raise PipelineError("build.source_dir must match its direct-cargo core ID")
    # Cargo names its cdylib itself; `output_path` is that bare product file
    # name and must equal the artifact -- no rebrand support until a fork
    # needs one, and no subdirectory: the driver derives the full
    # `target/<triple>/release/` location from the reviewed target map.
    output_path = build.get("output_path")
    if (
        not isinstance(output_path, str)
        or "/" in output_path
        or output_path != build.get("artifact_name")
    ):
        raise PipelineError(
            "build.output_path must equal build.artifact_name for direct-cargo"
        )
    if validated_source_date_epoch(spec) is None:
        raise PipelineError("build.source_date_epoch is required for direct-cargo")

    cargo = build.get("cargo")
    if not isinstance(cargo, dict) or set(cargo) != {
        "subdir",
        "profile",
        "lock_sha256",
        "targets",
    }:
        raise PipelineError("build.cargo must contain the exact direct-cargo fields")
    subdir = exact_relative_path(cargo.get("subdir"), "build.cargo.subdir")
    if cargo.get("profile") != "release":
        raise PipelineError("build.cargo.profile must be release")
    lock_sha256 = cargo.get("lock_sha256")
    if not isinstance(lock_sha256, str) or not SHA256_RE.fullmatch(lock_sha256):
        raise PipelineError("build.cargo.lock_sha256 is invalid")
    targets = cargo.get("targets")
    # The triple prefixes are pinned per architecture; an optional dotted
    # suffix is cargo-zigbuild's glibc floor (e.g. `.2.23`).
    expected_triple_prefixes = {
        "arm64": "aarch64-unknown-linux-gnu",
        "armhf": "armv7-unknown-linux-gnueabihf",
    }
    if not isinstance(targets, dict) or set(targets) != set(expected_triple_prefixes):
        raise PipelineError("build.cargo.targets must name exactly arm64 and armhf")
    for target_arch, triple in targets.items():
        prefix = expected_triple_prefixes[target_arch]
        if not isinstance(triple, str) or not re.fullmatch(
            re.escape(prefix) + r"(\.[0-9]+(\.[0-9]+)*)?", triple
        ):
            raise PipelineError(
                f"build.cargo.targets.{target_arch} is not the pinned triple"
            )
    return {
        "subdir": subdir,
        "profile": "release",
        "lock_sha256": lock_sha256,
        "targets": dict(targets),
    }


def direct_cargo_contract_for_target(spec: dict, arch: str) -> dict | None:
    contract = validated_direct_cargo(spec)
    if contract is None:
        return None
    if arch not in spec.get("targets", []):
        raise PipelineError(f"direct-cargo architecture is not enabled: {arch}")
    return {
        "cargo": {
            "subdir": contract["subdir"],
            "profile": contract["profile"],
            "lock_sha256": contract["lock_sha256"],
            "target": contract["targets"][arch],
        }
    }


def normalized_build_contract(spec: dict, arch: str) -> dict:
    git_version = validated_git_version(spec)
    contract = {
        "driver": spec.get("build", {}).get("driver"),
        "environment": "sanitized-v1",
        "compile_definitions": compile_definitions_for_target(spec, arch),
    }
    if git_version is not None:
        contract["git_version"] = git_version
    generated_source = validated_generated_source(spec)
    if generated_source is not None:
        contract["generated_source"] = generated_source
    recipe_profile = validated_recipe_profile(spec)
    if recipe_profile is not None:
        contract["recipe_profile"] = recipe_profile
    make_variables = validated_make_variables(spec)
    if make_variables:
        contract["make_variables"] = make_variables
    source_date_epoch = validated_source_date_epoch(spec)
    if source_date_epoch is not None:
        contract["source_date_epoch"] = source_date_epoch
    metadata_replacement = validated_metadata_replacement(spec)
    if metadata_replacement is not None:
        contract["metadata_replacement"] = metadata_replacement
    direct_cmake = direct_cmake_contract_for_target(spec, arch)
    if direct_cmake is not None:
        contract.update(direct_cmake)
    direct_cargo = direct_cargo_contract_for_target(spec, arch)
    if direct_cargo is not None:
        contract.update(direct_cargo)
    return contract


def recorded_build_contract(build: object) -> dict:
    if not isinstance(build, dict):
        return {}
    keys = (
        "driver",
        "environment",
        "compile_definitions",
        "generated_source",
        "git_version",
        "make_variables",
        "recipe_profile",
        "source_date_epoch",
        "metadata_replacement",
        "cmake",
        "cargo",
        "overlays",
    )
    return {key: copy.deepcopy(build[key]) for key in keys if key in build}


def validated_forbidden_needed_prefixes(spec: dict) -> list[str]:
    validation = spec.get("validation")
    if validation is None:
        return []
    if not isinstance(validation, dict) or set(validation) != {
        "forbidden_needed_prefixes"
    }:
        raise PipelineError(
            "validation must contain only forbidden_needed_prefixes"
        )
    prefixes = validation["forbidden_needed_prefixes"]
    if (
        not isinstance(prefixes, list)
        or not prefixes
        or any(not isinstance(prefix, str) for prefix in prefixes)
        or prefixes != sorted(set(prefixes))
    ):
        raise PipelineError(
            "validation.forbidden_needed_prefixes must be a non-empty sorted unique array"
        )
    for prefix in prefixes:
        if not re.fullmatch(r"lib[A-Za-z0-9_+.-]+", prefix):
            raise PipelineError(
                "validation.forbidden_needed_prefixes contains an unsafe token"
            )
    return list(prefixes)


def forbidden_needed_dependencies(spec: dict, needed: object) -> list[str]:
    prefixes = validated_forbidden_needed_prefixes(spec)
    if not prefixes:
        return []
    if not isinstance(needed, list) or any(
        not isinstance(dependency, str) for dependency in needed
    ):
        raise PipelineError("artifact dynamic dependency list is invalid")
    return sorted(
        dependency
        for dependency in set(needed)
        if any(dependency.startswith(prefix) for prefix in prefixes)
    )


def apply_artifact_dependency_policy(validation: dict, spec: dict) -> dict:
    forbidden = forbidden_needed_dependencies(spec, validation.get("needed", []))
    if forbidden:
        validation.setdefault("errors", []).append(
            "forbidden dynamic dependencies: " + ", ".join(forbidden)
        )
        validation["status"] = "invalid"
    return validation


def make_variable_golden_build_contract_is_well_formed(build: object) -> bool:
    if not isinstance(build, dict):
        return False
    profile = make_variable_profile(build.get("make_variables"))
    facts = _make_variable_profile_facts().get(profile or "")
    # golden_epoch encodes whether the record pins a source_date_epoch (the
    # portable FFmpeg profile does; the GL/dynarec profiles have no
    # date-embedding source and forbid one). None means the profile's golden
    # record is validated elsewhere (the combined native+make validators).
    if facts is None or facts.golden_epoch is None:
        return False
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "make_variables",
        "log",
        "log_sha256",
    }
    if facts.golden_epoch:
        required_keys.add("source_date_epoch")
    return bool(
        set(build) == required_keys
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and (
            profile != PORTABLE_FFMPEG_MAKE_PROFILE
            or source_date_epoch_is_well_formed(build.get("source_date_epoch"))
        )
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"])
    )


def native_git_version_golden_source_is_well_formed(
    core_id: object, source: object
) -> bool:
    if core_id == FBNEO_CORE_ID:
        return fbneo_golden_source_is_well_formed(core_id, source)
    if core_id == MAME2003_PLUS_CORE_ID:
        return mame2003_plus_golden_source_is_well_formed(core_id, source)
    if core_id == ATARI800_CORE_ID:
        return atari800_golden_source_is_well_formed(core_id, source)
    if core_id == MGBA_CORE_ID:
        return mgba_golden_source_is_well_formed(core_id, source)
    if core_id == UZEM_CORE_ID:
        return uzem_golden_source_is_well_formed(core_id, source)
    if core_id == MEDNAFEN_WSWAN_CORE_ID:
        return mednafen_wswan_golden_source_is_well_formed(core_id, source)
    if core_id == MEDNAFEN_PCFX_CORE_ID:
        return mednafen_pcfx_golden_source_is_well_formed(core_id, source)
    if core_id == POKEMINI_CORE_ID:
        return pokemini_golden_source_is_well_formed(core_id, source)
    if core_id == FMSX_CORE_ID:
        return fmsx_golden_source_is_well_formed(core_id, source)
    if core_id == BLUEMSX_CORE_ID:
        return bluemsx_golden_source_is_well_formed(core_id, source)
    if core_id == CORE_2048_ID:
        return core_2048_golden_source_is_well_formed(core_id, source)
    if core_id == LOWRESNX_CORE_ID:
        return lowresnx_golden_source_is_well_formed(core_id, source)
    if core_id == VICE_X64_CORE_ID:
        return vice_x64_golden_source_is_well_formed(core_id, source)
    if core_id == VICE_XVIC_CORE_ID:
        return vice_xvic_golden_source_is_well_formed(core_id, source)
    identity = NATIVE_GIT_VERSION_SPEC_IDENTITIES.get(core_id)
    if identity is None:
        identity = NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES.get(core_id)
    if identity is None:
        identity = NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES.get(core_id)
    return bool(
        identity is not None
        and isinstance(source, dict)
        and set(source)
        == {
            "url",
            "requested_ref",
            "commit",
            "tree",
            "resolved_commit",
            "resolved_url",
            "submodules",
        }
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and source.get("resolved_commit") == identity["source_commit"]
        and source.get("resolved_url") == identity["source_url"]
        and source.get("submodules") == []
    )


def native_git_describe_golden_source_is_well_formed(
    core_id: object, source: object
) -> bool:
    if core_id == GEARBOY_CORE_ID:
        return gearboy_golden_source_is_well_formed(core_id, source)
    if core_id == GEARSYSTEM_CORE_ID:
        return gearsystem_golden_source_is_well_formed(core_id, source)
    if core_id == GEARCOLECO_CORE_ID:
        return gearcoleco_golden_source_is_well_formed(core_id, source)
    identity = NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES.get(core_id)
    return bool(
        identity is not None
        and isinstance(source, dict)
        and set(source)
        == {
            "url",
            "requested_ref",
            "commit",
            "tree",
            "resolved_commit",
            "resolved_url",
            "submodules",
        }
        and source.get("url") == identity["source_url"]
        and source.get("requested_ref") == identity["source_requested_ref"]
        and source.get("commit") == identity["source_commit"]
        and source.get("tree") == identity["source_tree"]
        and source.get("resolved_commit") == identity["source_commit"]
        and source.get("resolved_url") == identity["source_url"]
        and source.get("submodules") == []
    )


def uzem_native_golden_source_is_well_formed(
    core_id: object, source: object
) -> bool:
    return uzem_golden_source_is_well_formed(core_id, source)


def git_version_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object = None,
    source: object = None,
    arch: object = None,
) -> bool:
    if core_id == FBNEO_CORE_ID:
        return fbneo_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source, arch
        )
    if core_id == MAME2003_PLUS_CORE_ID:
        return mame2003_plus_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source, arch
        )
    if core_id == ATARI800_CORE_ID:
        return atari800_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == MGBA_CORE_ID:
        return mgba_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == MEDNAFEN_WSWAN_CORE_ID:
        return mednafen_wswan_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == POKEMINI_CORE_ID:
        return pokemini_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == UZEM_CORE_ID:
        return uzem_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == GEARBOY_CORE_ID:
        return gearboy_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == GEARSYSTEM_CORE_ID:
        return gearsystem_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == GEARCOLECO_CORE_ID:
        return gearcoleco_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == FMSX_CORE_ID:
        return fmsx_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == BLUEMSX_CORE_ID:
        return bluemsx_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == CORE_2048_ID:
        return core_2048_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == LOWRESNX_CORE_ID:
        return lowresnx_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == VICE_X64_CORE_ID:
        return vice_x64_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == VICE_XVIC_CORE_ID:
        return vice_xvic_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if not isinstance(build, dict):
        return False
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "git_version",
        "log",
        "log_sha256",
    }
    common_contract_is_well_formed = bool(
        required_keys.issubset(build)
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and git_version_contract_is_well_formed(
            build.get("git_version"), source_commit
        )
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"])
    )
    if not common_contract_is_well_formed:
        return False
    derivation = build.get("git_version", {}).get("derivation")
    if derivation == GIT_VERSION_DERIVATION:
        return bool(
            set(build).issubset(required_keys.union({"source_date_epoch"}))
            and (
                "source_date_epoch" not in build
                or source_date_epoch_is_well_formed(build["source_date_epoch"])
            )
        )
    if derivation == NATIVE_GIT_VERSION_DERIVATION:
        return bool(
            set(build) == required_keys
            and native_git_version_golden_source_is_well_formed(core_id, source)
            and build.get("git_version")
            == exact_native_git_version_contract(core_id)
        )
    if derivation == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
        return bool(
            set(build) == required_keys
            and native_git_version_golden_source_is_well_formed(core_id, source)
            and build.get("git_version")
            == exact_native_git_version_contract(core_id)
        )
    if derivation == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
        identity = NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES.get(core_id)
        return bool(
            identity is not None
            and set(build) == required_keys.union({"source_date_epoch"})
            and native_git_version_golden_source_is_well_formed(core_id, source)
            and build.get("git_version")
            == exact_native_git_version_contract(core_id)
            and build.get("source_date_epoch")
            == identity["source_date_epoch"]
        )
    if derivation == NATIVE_GIT_DESCRIBE_DERIVATION:
        return bool(
            set(build) == required_keys
            and native_git_describe_golden_source_is_well_formed(core_id, source)
            and build.get("git_version")
            == exact_native_git_describe_contract(core_id)
        )
    return False


def snes9x2005_plus_combined_golden_build_contract_is_well_formed(
    build: object, source_commit: object, core_id: object, source: object
) -> bool:
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "make_variables",
        "git_version",
        "log",
        "log_sha256",
    }
    return bool(
        isinstance(build, dict)
        and core_id == "snes9x2005_plus"
        and native_git_version_golden_source_is_well_formed(core_id, source)
        and set(build) == required_keys
        and build.get("driver") == "libretro-super"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and make_variable_profile(build.get("make_variables"))
        == SNES9X2005_PLUS_MAKE_PROFILE
        and git_version_contract_is_well_formed(
            build.get("git_version"), source_commit
        )
        and build.get("git_version")
        == exact_native_git_version_contract(core_id)
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"])
    )


def combined_git_version_make_golden_build_contract_is_well_formed(
    build: object, source_commit: object, core_id: object, source: object
) -> bool:
    if core_id == "vecx":
        return vecx_combined_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == MEDNAFEN_PCFX_CORE_ID:
        return mednafen_pcfx_combined_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    if core_id == "snes9x2005_plus":
        return snes9x2005_plus_combined_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    return False


def exact_native_golden_build_contract_is_well_formed(
    build: object,
    source_commit: object,
    core_id: object,
    source: object,
    arch: object = None,
) -> bool:
    if core_id in {MEDNAFEN_PCFX_CORE_ID, "snes9x2005_plus"}:
        return combined_git_version_make_golden_build_contract_is_well_formed(
            build, source_commit, core_id, source
        )
    return git_version_golden_build_contract_is_well_formed(
        build, source_commit, core_id, source, arch
    )


# Rebranded direct-cmake forks: the CMake target the upstream tree builds,
# reviewed per core. The artifact still ships under the core's own canonical
# name; everything not listed here keeps target == <core_id>_libretro exactly.
DIRECT_CMAKE_RENAMED_TARGETS = {
    "km_duckswanstation_xtreme_amped": "swanstation_libretro",
}


def direct_cmake_golden_build_contract_is_well_formed(
    build: object, core_id: str, arch: str
) -> bool:
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "source_date_epoch",
        "cmake",
        "overlays",
        "log",
        "log_sha256",
    }
    if not isinstance(build, dict) or set(build) != required_keys:
        return False
    expected_processor = {"arm64": "aarch64", "armhf": "arm"}.get(arch)
    cmake = build.get("cmake")
    if (
        build.get("driver") != "direct-cmake"
        or build.get("environment") != "sanitized-v1"
        or build.get("compile_definitions") != []
        or not source_date_epoch_is_well_formed(build.get("source_date_epoch"))
        or build.get("log") != "build.log"
        or not isinstance(build.get("log_sha256"), str)
        or not SHA256_RE.fullmatch(build["log_sha256"])
        or expected_processor is None
        or not isinstance(cmake, dict)
        or not {"generator", "build_type", "target", "system"} <= set(cmake)
        or not set(cmake)
        <= {"generator", "build_type", "target", "system", "source_subdir", "defines"}
        or cmake.get("generator") != "Unix Makefiles"
        or cmake.get("build_type") != "Release"
        or cmake.get("target")
        != DIRECT_CMAKE_RENAMED_TARGETS.get(core_id, f"{core_id}_libretro")
        or cmake.get("system")
        != {"name": "Linux", "processor": expected_processor}
    ):
        return False
    # Optional reviewed extensions (tic80/squirreljme/ardens): validate shape.
    if "source_subdir" in cmake and not (
        isinstance(cmake["source_subdir"], str) and cmake["source_subdir"]
    ):
        return False
    if "defines" in cmake and not (
        isinstance(cmake["defines"], dict)
        and cmake["defines"]
        and all(
            isinstance(name, str) and isinstance(value, str)
            for name, value in cmake["defines"].items()
        )
    ):
        return False
    overlays = build.get("overlays")
    if not isinstance(overlays, list):
        return False
    source_paths = [
        overlay.get("source_path") if isinstance(overlay, dict) else None
        for overlay in overlays
    ]
    if any(not isinstance(path, str) for path in source_paths) or source_paths != sorted(
        source_paths
    ):
        return False
    overlay_keys = {
        "kind",
        "patch_path",
        "patch_sha256",
        "source_path",
        "preimage_sha256",
        "postimage_sha256",
    }
    seen_sources: set[str] = set()
    seen_patches: set[str] = set()
    for overlay in overlays:
        if not isinstance(overlay, dict) or not (
            overlay_keys <= set(overlay)
            and set(overlay) <= overlay_keys | {"submodule_path"}
        ):
            return False
        if "submodule_path" in overlay and not (
            isinstance(overlay["submodule_path"], str)
            and str(overlay.get("source_path", "")).startswith(
                overlay["submodule_path"] + "/"
            )
        ):
            return False
        try:
            patch_path = exact_relative_path(
                overlay.get("patch_path"), "promoted overlay patch_path"
            )
            source_path = exact_relative_path(
                overlay.get("source_path"), "promoted overlay source_path"
            )
        except PipelineError:
            return False
        if (
            overlay.get("kind") != "git-apply-v1"
            or not patch_path.startswith(f"patches/{core_id}/")
            or not patch_path.endswith(".patch")
            or patch_path in seen_patches
            or source_path in seen_sources
        ):
            return False
        seen_patches.add(patch_path)
        seen_sources.add(source_path)
        for digest_key in (
            "patch_sha256",
            "preimage_sha256",
            "postimage_sha256",
        ):
            digest = overlay.get(digest_key)
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                return False
        if overlay["preimage_sha256"] == overlay["postimage_sha256"]:
            return False
    return True



def direct_cargo_golden_build_contract_is_well_formed(
    build: object, core_id: str, arch: str
) -> bool:
    required_keys = {
        "driver",
        "environment",
        "compile_definitions",
        "source_date_epoch",
        "cargo",
        "log",
        "log_sha256",
    }
    if not isinstance(build, dict) or set(build) != required_keys:
        return False
    expected_triple_prefix = {
        "arm64": "aarch64-unknown-linux-gnu",
        "armhf": "armv7-unknown-linux-gnueabihf",
    }.get(arch)
    cargo = build.get("cargo")
    return (
        build.get("driver") == "direct-cargo"
        and build.get("environment") == "sanitized-v1"
        and build.get("compile_definitions") == []
        and source_date_epoch_is_well_formed(build.get("source_date_epoch"))
        and build.get("log") == "build.log"
        and isinstance(build.get("log_sha256"), str)
        and SHA256_RE.fullmatch(build["log_sha256"]) is not None
        and expected_triple_prefix is not None
        and isinstance(cargo, dict)
        and set(cargo) == {"subdir", "profile", "lock_sha256", "target"}
        and isinstance(cargo.get("subdir"), str)
        and bool(cargo["subdir"])
        and cargo.get("profile") == "release"
        and isinstance(cargo.get("lock_sha256"), str)
        and SHA256_RE.fullmatch(cargo["lock_sha256"]) is not None
        and isinstance(cargo.get("target"), str)
        and re.fullmatch(
            re.escape(expected_triple_prefix) + r"(\.[0-9]+(\.[0-9]+)*)?",
            cargo["target"],
        )
        is not None
    )


def compile_definition_list_is_well_formed(definitions: object) -> bool:
    if not isinstance(definitions, list) or any(
        not isinstance(definition, str) for definition in definitions
    ):
        return False
    if definitions != sorted(definitions):
        return False
    definition_names: set[str] = set()
    for definition in definitions:
        match = COMPILE_DEFINITION_RE.fullmatch(definition)
        if (
            match is None
            or int(match.group(2)) > 0xFFFFFFFF
            or match.group(1) in definition_names
        ):
            return False
        definition_names.add(match.group(1))
    return True


def _compile_log_definition_proof(
    build_log_text: str,
    definitions: object,
    arch: str,
    *,
    forbidden_names: frozenset[str] = frozenset(),
) -> tuple[bool, int | None]:
    if not compile_definition_list_is_well_formed(definitions):
        return False, None
    assert isinstance(definitions, list)
    expected = {f"-D{definition}" for definition in definitions}
    expected_by_name = {
        definition.split("=", 1)[0]: f"-D{definition}" for definition in definitions
    }
    if not expected:
        return True, None
    expected_compilers = TARGET_COMPILERS.get(arch)
    if expected_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    target_compile_count = 0
    first_target_compile: int | None = None
    tracked_names = set(expected_by_name).union(forbidden_names)
    for line_number, line in enumerate(build_log_text.splitlines()):
        # Large verbose Make logs can contain hundreds of thousands of unrelated
        # lines.  A real target command must contain a target compiler spelling,
        # so reject other lines cheaply, then retain shell parsing for candidate
        # commands.  Quoting or escaping can otherwise turn spellings such as
        # ``-""c`` into the exact ``-c`` token.
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False, first_target_compile
        if not tokens or "-c" not in tokens:
            continue
        compiler = Path(tokens[0]).name
        if (
            not COMPILER_COMMAND_RE.fullmatch(compiler)
            or compiler not in expected_compilers
        ):
            continue
        target_compile_count += 1
        if first_target_compile is None:
            first_target_compile = line_number
        if not expected.issubset(tokens):
            return False, first_target_compile
        if any(token.startswith("@") for token in tokens):
            return False, first_target_compile
        macro_tokens: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            token = tokens[token_index]
            if token == "-Xpreprocessor":
                if token_index + 1 >= len(tokens):
                    return False, first_target_compile
                macro_tokens.append(tokens[token_index + 1])
                token_index += 2
                continue
            if token.startswith("-Xpreprocessor="):
                return False, first_target_compile
            if token.startswith("-Wp,"):
                macro_tokens.extend(token.removeprefix("-Wp,").split(","))
            else:
                macro_tokens.append(token)
            token_index += 1
        if any(token.startswith("@") for token in macro_tokens):
            return False, first_target_compile
        for index, token in enumerate(macro_tokens):
            candidate = ""
            if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                candidate = token[2:]
            elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                candidate = macro_tokens[index + 1]
            candidate_name = re.split(r"[=(]", candidate, maxsplit=1)[0]
            if candidate_name not in tracked_names:
                continue
            if (
                candidate_name in forbidden_names
                or token != expected_by_name.get(candidate_name)
            ):
                return False, first_target_compile
    return target_compile_count > 0, first_target_compile


def compile_log_proves_definitions(
    build_log_text: str, definitions: object, arch: str
) -> bool:
    proven, _first_target_compile = _compile_log_definition_proof(
        build_log_text, definitions, arch
    )
    return proven


def make_variable_log_proves_contract(
    build_log_text: str, make_variables: object, arch: str
) -> bool:
    profile = make_variable_profile(make_variables)
    if profile is None:
        return False
    expected_markers = make_variable_markers(make_variables)
    if not expected_markers:
        return False
    marker_lines = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_MAKEFLAGS|")
        or line.startswith("CORE_PIPELINE_MAKE_VARIABLE|")
    ]
    if marker_lines != expected_markers:
        return False
    portable_first_target_compile: int | None = None
    if profile == PORTABLE_FFMPEG_MAKE_PROFILE:
        portable_proven, portable_first_target_compile = (
            _compile_log_definition_proof(
                build_log_text,
                list(PORTABLE_FFMPEG_COMPILE_DEFINITIONS),
                arch,
                forbidden_names=PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS,
            )
        )
        if not portable_proven:
            return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    if expected_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    lines = build_log_text.splitlines()
    marker_positions = [lines.index(marker) for marker in expected_markers]
    if profile == PORTABLE_FFMPEG_MAKE_PROFILE:
        return bool(
            portable_first_target_compile is not None
            and max(marker_positions) < portable_first_target_compile
        )
    first_target_compile: int | None = None
    snes9x2005_plus_macro = "USE_BLARGG_APU"
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        if not tokens:
            continue
        compiler = Path(tokens[0]).name
        if (
            not COMPILER_COMMAND_RE.fullmatch(compiler)
            or compiler not in expected_compilers
        ):
            continue
        if any(token.startswith("@") for token in tokens):
            return False
        if profile == VECX_SOFTWARE_MAKE_PROFILE:
            if not vecx_command_tokens_are_software_only(tokens):
                return False
        if "-c" not in tokens:
            continue
        if (
            profile == SNES9X2005_PLUS_MAKE_PROFILE
            and compiler in expected_cxx_compilers
        ):
            return False
        if first_target_compile is None:
            first_target_compile = line_number
        macro_tokens: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            token = tokens[token_index]
            if token == "-Xpreprocessor":
                if token_index + 1 >= len(tokens):
                    return False
                macro_tokens.append(tokens[token_index + 1])
                token_index += 2
                continue
            if token.startswith("-Xpreprocessor="):
                return False
            if token.startswith("-Wp,"):
                macro_tokens.extend(token.removeprefix("-Wp,").split(","))
            else:
                macro_tokens.append(token)
            token_index += 1
        for index, token in enumerate(macro_tokens):
            candidate = ""
            if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                candidate = token[2:]
            elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                candidate = macro_tokens[index + 1]
            name = re.split(r"[=(]", candidate, maxsplit=1)[0]
            profile_facts = _make_variable_profile_facts().get(profile or "")
            forbidden_macros = (
                profile_facts.forbidden_compile_macros
                if profile_facts is not None
                else frozenset()
            )
            if name in forbidden_macros:
                return False
        if profile == SNES9X2005_PLUS_MAKE_PROFILE:
            if any(
                token == "-Xpreprocessor"
                or token.startswith("-Xpreprocessor=")
                for token in tokens
            ):
                return False
            plus_tokens = []
            for index, token in enumerate(macro_tokens):
                candidate = ""
                if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                    candidate = token[2:]
                elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                    candidate = macro_tokens[index + 1]
                if re.split(r"[=(]", candidate, maxsplit=1)[0] == snes9x2005_plus_macro:
                    plus_tokens.append(token)
            if (
                plus_tokens != ["-DUSE_BLARGG_APU"]
                or tokens.count("-DUSE_BLARGG_APU") != 1
            ):
                return False
    return (
        first_target_compile is not None
        and max(marker_positions) < first_target_compile
    )


def git_version_markers(git_version: object, source_commit: object) -> list[str]:
    if not git_version_contract_is_well_formed(git_version, source_commit):
        return []
    assert isinstance(git_version, dict)
    value = git_version["value"]
    if git_version["derivation"] == FBNEO_GIT_VERSION_DERIVATION:
        return list(fbneo_git_version_markers(git_version))
    if git_version["derivation"] == NATIVE_GIT_VERSION_DERIVATION:
        if source_commit in MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS:
            makeflags = f'-- GIT_VERSION="\\{value}"'
            return [
                (
                    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                    f'"{value}"|command-scoped-makeflags'
                ),
                f"CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|{makeflags}",
                f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|command line',
            ]
        if source_commit in ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS:
            return [
                (
                    "CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|"
                    f'"{value}"|command-scoped-environment'
                ),
                f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|environment',
            ]
        return [f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|file']
    if git_version["derivation"] == NATIVE_GIT_VERSION_SHORT8_DERIVATION:
        return list(mame2003_plus_git_version_markers(git_version))
    if git_version["derivation"] == NATIVE_GIT_VERSION_SHORT9_DERIVATION:
        return [f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|file']
    if git_version["derivation"] == NATIVE_GIT_VERSION_SHORT10_DERIVATION:
        return [
            "CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV|command line:|10",
            f'CORE_PIPELINE_NATIVE_GIT_VERSION|"{value}"|file',
        ]
    if git_version["derivation"] == NATIVE_GIT_DESCRIBE_DERIVATION:
        return [f"CORE_PIPELINE_NATIVE_GIT_VERSION|{value}|file"]
    return [
        f"CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|GIT_VERSION={value}",
        f"CORE_PIPELINE_GIT_VERSION|{value}|command line",
    ]


def git_version_log_proves_contract(
    build_log_text: str,
    git_version: object,
    source_commit: object,
    arch: str,
) -> bool:
    if source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS:
        lowered_log = build_log_text.lower()
        if "fatal:" in lowered_log or "dubious ownership" in lowered_log:
            return False
    expected_markers = git_version_markers(git_version, source_commit)
    if not expected_markers:
        return False
    marker_lines = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_GIT_VERSION_MAKEFLAGS|")
        or line.startswith("CORE_PIPELINE_GIT_VERSION|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION_BUILD_ARG|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_VERSION_MAKEFLAGS|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_DATE|")
        or line.startswith("CORE_PIPELINE_NATIVE_GIT_DATE_BUILD_ARG|")
        or line.startswith("CORE_PIPELINE_GIT_CONFIG_CORE_ABBREV|")
    ]
    if marker_lines != expected_markers:
        return False
    expected_compilers = TARGET_COMPILERS.get(arch)
    expected_cxx_compilers = TARGET_CXX_COMPILERS.get(arch)
    if expected_compilers is None or expected_cxx_compilers is None:
        raise PipelineError(f"unknown architecture: {arch}")
    assert isinstance(git_version, dict)
    derivation = git_version.get("derivation")
    if derivation == FBNEO_GIT_VERSION_DERIVATION:
        expected_tokens = fbneo_compile_tokens(git_version)
        if len(expected_tokens) != 2:
            return False
        protected_macro_names = {"GIT_DATE", "GIT_VERSION"}
    elif derivation == NATIVE_GIT_DESCRIBE_DERIVATION:
        compile_macro = NATIVE_GIT_DESCRIBE_COMPILE_MACROS_BY_COMMIT.get(
            source_commit
        )
        if not isinstance(compile_macro, str):
            return False
        expected_tokens = (
            f'-D{compile_macro}="{git_version["value"]}"',
        )
        protected_macro_names = {compile_macro, "GIT_VERSION"}
    else:
        compile_macro = "GIT_VERSION"
        expected_tokens = (
            f'-D{compile_macro}="{git_version["value"]}"',
        )
        protected_macro_names = {compile_macro}
    compiler_scope = git_version.get("compiler_scope")
    lines = build_log_text.splitlines()
    marker_positions = [lines.index(marker) for marker in expected_markers]
    first_target_compile: int | None = None
    bound_compile_count = 0
    for line_number, line in enumerate(lines):
        if not line_may_name_target_compiler(line, expected_compilers):
            continue
        if (
            source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
            and not command_line_is_lexically_safe(line)
        ):
            return False
        try:
            tokens = shlex.split(line)
        except ValueError:
            return False
        if not tokens or "-c" not in tokens:
            continue
        raw_compiler = tokens[0]
        compiler = Path(raw_compiler).name
        if (
            source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
            and raw_compiler not in expected_compilers
        ):
            return False
        if (
            not COMPILER_COMMAND_RE.fullmatch(compiler)
            or compiler not in expected_compilers
        ):
            continue
        if first_target_compile is None:
            first_target_compile = line_number
        if compiler_scope == GIT_VERSION_CXX_SCOPE:
            requires_token = compiler in expected_cxx_compilers
        elif compiler_scope == GIT_VERSION_C_SCOPE:
            requires_token = compiler not in expected_cxx_compilers
        else:
            requires_token = True
        expected_count = 1 if requires_token else 0
        if (
            any(
                tokens.count(expected_token) != expected_count
                for expected_token in expected_tokens
            )
            or any(token.startswith("@") for token in tokens)
            or (
                source_commit in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
                and any("@" in token for token in tokens[1:])
            )
        ):
            return False
        if requires_token:
            bound_compile_count += 1
        macro_tokens: list[str] = []
        token_index = 0
        while token_index < len(tokens):
            token = tokens[token_index]
            if token == "-Xpreprocessor":
                if token_index + 1 >= len(tokens):
                    return False
                macro_tokens.append(tokens[token_index + 1])
                token_index += 2
                continue
            if token.startswith("-Xpreprocessor="):
                return False
            if token.startswith("-Wp,"):
                macro_tokens.extend(token.removeprefix("-Wp,").split(","))
            else:
                macro_tokens.append(token)
            token_index += 1
        for index, token in enumerate(macro_tokens):
            if token in expected_tokens:
                continue
            candidate = ""
            if token.startswith(("-D", "-U")) and token not in {"-D", "-U"}:
                candidate = token[2:]
            elif token in {"-D", "-U"} and index + 1 < len(macro_tokens):
                candidate = macro_tokens[index + 1]
            candidate_name = re.split(r"[=(]", candidate, maxsplit=1)[0]
            if candidate_name in protected_macro_names:
                return False
    return bool(
        bound_compile_count
        and first_target_compile is not None
        and max(marker_positions) < first_target_compile
    )


def read_build_log(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PipelineError(f"{label} is not readable UTF-8 text: {exc}") from exc


def validate_catalog(catalog: dict) -> None:
    errors: list[str] = []
    if type(catalog.get("schema_version")) is not int or catalog["schema_version"] != 2:
        errors.append("schema_version must be the exact integer 2")
    if catalog.get("policy", {}).get("publication") != "disabled":
        errors.append("policy.publication must be disabled")
    if "exact_toolchain_archive_lock" not in catalog.get("policy", {}).get(
        "promotion_requires", []
    ):
        errors.append("policy.promotion_requires must include exact_toolchain_archive_lock")
    if "source_commit_not_actively_blacklisted" not in catalog.get(
        "policy", {}
    ).get("promotion_requires", []):
        errors.append(
            "policy.promotion_requires must include "
            "source_commit_not_actively_blacklisted"
        )
    try:
        load_catalog_commit_blacklist(catalog)
    except PipelineError as exc:
        errors.append(str(exc))
    locked_toolchains: dict | None = None
    try:
        lock, _, _ = load_catalog_toolchain_lock(catalog)
        locked_toolchains = lock["toolchains"]
    except PipelineError as exc:
        errors.append(str(exc))
    toolchains = catalog.get("toolchains", {})
    # The mirror must cover every locked entry: the two C cross images plus
    # the Rust image the direct-cargo driver builds inside.
    if locked_toolchains is not None and set(toolchains) != set(locked_toolchains):
        errors.append("toolchains mirror does not cover the archive lock entries")
    for arch in (*ARCH_LAYOUT, "rust"):
        toolchain = toolchains.get(arch, {})
        image_id = toolchain.get("image_id", "")
        dockerfile_digest = toolchain.get("dockerfile_sha256", "")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            errors.append(f"toolchains.{arch}.image_id is not an exact SHA256 ID")
        if not SHA256_RE.fullmatch(dockerfile_digest):
            errors.append(f"toolchains.{arch}.dockerfile_sha256 is invalid")
        if toolchain.get("dockerfile_linkage") != "unverified-local-cache":
            errors.append(
                f"toolchains.{arch}.dockerfile_linkage must preserve the unverified cache status"
            )
        dockerfile = ROOT / toolchain.get("dockerfile", "")
        if not dockerfile.is_file():
            errors.append(f"toolchains.{arch}.dockerfile does not exist")
        elif sha256_file(dockerfile) != dockerfile_digest:
            errors.append(f"toolchains.{arch}.dockerfile_sha256 does not match")
        if locked_toolchains is not None:
            locked = locked_toolchains[arch]
            if toolchain.get("image") != locked["image"].get("tag"):
                errors.append(f"toolchains.{arch}.image does not match the archive lock")
            if image_id != locked["image"].get("id"):
                errors.append(f"toolchains.{arch}.image_id does not match the archive lock")
            if toolchain.get("dockerfile") != locked["dockerfile"].get("path"):
                errors.append(
                    f"toolchains.{arch}.dockerfile does not match the archive lock"
                )
            if dockerfile_digest != locked["dockerfile"].get("sha256"):
                errors.append(
                    f"toolchains.{arch}.dockerfile_sha256 does not match the archive lock"
                )
            if toolchain.get("dockerfile_linkage") != locked["dockerfile"].get(
                "linkage"
            ):
                errors.append(
                    f"toolchains.{arch}.dockerfile_linkage does not match the archive lock"
                )
    resolver = catalog.get("resolver", {})
    if not SHA1_RE.fullmatch(resolver.get("libretro_super_commit", "")):
        errors.append("resolver.libretro_super_commit is not a full SHA")
    for prefix in ("core_rules", "fetch_script", "build_script"):
        raw_path = resolver.get(f"{prefix}_path", "")
        relative = Path(raw_path)
        if not raw_path or relative.is_absolute() or ".." in relative.parts:
            errors.append(f"resolver.{prefix}_path is not a safe relative path")
        if not SHA256_RE.fullmatch(resolver.get(f"{prefix}_sha256", "")):
            errors.append(f"resolver.{prefix}_sha256 is invalid")
    workflows = core_workflows()
    cores = catalog.get("cores", {})
    if not isinstance(cores, dict) or not cores:
        errors.append("cores must be a non-empty object")
    else:
        for core_id, spec in cores.items():
            source = spec.get("source", {})
            commit = source.get("commit", "")
            if not isinstance(commit, str) or not SHA1_RE.fullmatch(commit):
                errors.append(f"cores.{core_id}.source.commit is not a full SHA")
            source_tree = source.get("tree")
            if "tree" in source and (
                not isinstance(source_tree, str) or not SHA1_RE.fullmatch(source_tree)
            ):
                errors.append(f"cores.{core_id}.source.tree is not a full SHA")
            workflow = spec.get("workflow", "")
            if core_id not in workflows:
                errors.append(f"cores.{core_id} has no core workflow")
            elif workflow != str(workflows[core_id].relative_to(ROOT)):
                errors.append(f"cores.{core_id}.workflow does not match its workflow path")
            targets = spec.get("targets")
            if not targets or any(target not in ARCH_LAYOUT for target in targets):
                errors.append(f"cores.{core_id}.targets is invalid")
            driver = spec.get("build", {}).get("driver")
            if driver not in {"libretro-super", "direct-make", "direct-cmake", "direct-cargo"}:
                errors.append(f"cores.{core_id}.build.driver is unsupported")
            try:
                validated_compile_definitions(spec)
                make_variables = validated_make_variables(spec)
                git_version = validated_git_version(spec)
                validated_generated_source(spec)
                recipe_profile = validated_recipe_profile(spec)
                validated_source_date_epoch(spec)
                metadata_replacement = validated_metadata_replacement(spec)
                validated_direct_cmake(spec, core_id)
                validated_direct_cargo(spec, core_id)
                validate_build_overlays(
                    spec.get("build", {}).get("overlays", {}),
                    core_id,
                    spec.get("build", {}).get("source_dir", ""),
                    spec.get("targets", []),
                )
                validated_forbidden_needed_prefixes(spec)
                if core_id == PICODRIVE_CORE_ID and (
                    not picodrive_spec_is_well_formed(spec)
                    or recipe_profile is None
                ):
                    raise PipelineError(
                        "the picodrive core must preserve its exact source-root "
                        "recipe, source, metadata, target, and dependency contract"
                    )
                spec_guard = SPEC_GUARDS.get(core_id)
                if spec_guard is not None:
                    guard_name, guard_validator, guard_message = spec_guard
                    # Resolve through this module's globals first: focused
                    # boundary tests replace one validator at a time by
                    # patching the pipeline attribute, and that seam must
                    # keep working now that dispatch is registry-driven.
                    guard_validator = globals().get(guard_name, guard_validator)
                    if not guard_validator(spec):
                        raise PipelineError(guard_message)
                if core_id == QUICKNES_CORE_ID and not quicknes_spec_is_well_formed(
                    spec
                ):
                    raise PipelineError(
                        "the quicknes core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == NESTOPIA_CORE_ID and not nestopia_spec_is_well_formed(
                    spec
                ):
                    raise PipelineError(
                        "the nestopia core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == A5200_CORE_ID and not a5200_spec_is_well_formed(spec):
                    raise PipelineError(
                        "the a5200 core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == SNES9X_CORE_ID and not snes9x_spec_is_well_formed(
                    spec
                ):
                    raise PipelineError(
                        "the snes9x core must preserve its exact injected "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == O2EM_CORE_ID and not o2em_spec_is_well_formed(
                    spec
                ):
                    raise PipelineError(
                        "the o2em core must preserve its exact native version, "
                        "source, recipe, metadata, and target contract"
                    )
                if core_id == CORE_81_ID and not core_81_spec_is_well_formed(
                    spec
                ):
                    raise PipelineError(
                        "the 81 core must preserve its exact native generated "
                        "version, source, recipe, metadata, and target contract"
                    )
                if core_id == "vecx" and (
                    not vecx_software_spec_is_well_formed(spec)
                    or make_variable_profile(make_variables)
                    != VECX_SOFTWARE_MAKE_PROFILE
                    or git_version
                    != {
                        "derivation": NATIVE_GIT_VERSION_DERIVATION,
                        "value": f" {VECX_SOFTWARE_SPEC_IDENTITY['source_commit'][:7]}",
                    }
                    or metadata_replacement is None
                ):
                    raise PipelineError(
                        "the vecx core must preserve the exact VecX software "
                        "make, version, metadata, target, and dependency contract"
                    )
                if core_id in NATIVE_GIT_VERSION_SPEC_IDENTITIES:
                    identity = NATIVE_GIT_VERSION_SPEC_IDENTITIES[core_id]
                    expected_git_version = {
                        "derivation": NATIVE_GIT_VERSION_DERIVATION,
                        "value": f" {identity['source_commit'][:7]}",
                    }
                    if identity.get("compiler_scope") is not None:
                        expected_git_version["compiler_scope"] = identity[
                            "compiler_scope"
                        ]
                    if (
                        not native_git_version_spec_is_well_formed(spec, core_id)
                        or git_version != expected_git_version
                    ):
                        raise PipelineError(
                            f"the {core_id} core must preserve its exact native "
                            "version, source, recipe, metadata, and target contract"
                        )
                if core_id in NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES:
                    if (
                        not native_git_version_short9_spec_is_well_formed(
                            spec, core_id
                        )
                        or git_version
                        != exact_native_git_version_contract(core_id)
                    ):
                        raise PipelineError(
                            f"the {core_id} core must preserve its exact native "
                            "short9 version, source, recipe, metadata, target, "
                            "compiler scope, and Git abbreviation contract"
                        )
                if core_id in NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES:
                    if (
                        not native_git_version_short10_spec_is_well_formed(
                            spec, core_id
                        )
                        or git_version
                        != exact_native_git_version_contract(core_id)
                    ):
                        raise PipelineError(
                            f"the {core_id} core must preserve its exact native "
                            "short10 version, source, epoch, recipe, metadata, "
                            "target, and Git abbreviation contract"
                        )
                if core_id in EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS:
                    expected_git_version = exact_native_git_describe_contract(core_id)
                    if (
                        not native_git_describe_spec_is_well_formed(spec, core_id)
                        or git_version != expected_git_version
                    ):
                        raise PipelineError(
                            f"the {core_id} core must preserve its exact native git "
                            "describe, source, recipe, metadata, target, and "
                            "compiler-macro contract"
                        )
            except PipelineError as exc:
                errors.append(f"cores.{core_id}.{exc}")
            metadata = spec.get("metadata", {})
            expected_info = f"{core_id}_libretro.info"
            if metadata.get("artifact_name") != expected_info:
                errors.append(f"cores.{core_id}.metadata.artifact_name must be {expected_info}")
            if "repo_path" in metadata:
                # Repo-pinned metadata: for cores whose .info does not exist in
                # the image's libretro-super checkout (the KMFDManic forks have
                # no upstream rule at all). The reviewed file lives under
                # metadata/ and is pinned by sha256, so the deployed metadata is
                # exactly the bytes SpruceOS ships.
                expected_repo = {
                    "repo_path": f"metadata/{expected_info}",
                    "sha256": metadata.get("sha256"),
                    "artifact_name": expected_info,
                }
                if metadata != expected_repo or not (
                    isinstance(metadata.get("sha256"), str)
                    and SHA256_RE.fullmatch(metadata["sha256"])
                ):
                    errors.append(
                        f"cores.{core_id}.metadata repo-pinned form is malformed"
                    )
                else:
                    repo_file = ROOT / metadata["repo_path"]
                    if not repo_file.is_file():
                        errors.append(
                            f"cores.{core_id}.metadata.repo_path does not exist"
                        )
                    elif sha256_file(repo_file) != metadata["sha256"]:
                        errors.append(
                            f"cores.{core_id}.metadata.sha256 does not match the file"
                        )
            elif metadata.get("source_path") != f"/libretro-super/dist/info/{expected_info}":
                errors.append(f"cores.{core_id}.metadata.source_path is invalid")
    if errors:
        raise PipelineError("invalid build catalog:\n- " + "\n- ".join(errors))


def load_catalog(path: Path) -> dict:
    catalog = load_json(path)
    validate_catalog(catalog)
    return catalog


def readelf_header(path: Path) -> dict[str, str]:
    result = run(["readelf", "-h", str(path)])
    wanted = {"Class", "Data", "Type", "Machine", "Flags"}
    fields: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in wanted:
            fields[key.lower()] = value.strip()
    missing = {item.lower() for item in wanted} - fields.keys()
    if missing:
        raise PipelineError(f"readelf omitted {sorted(missing)} for {path}")
    return fields


def defined_libretro_symbols(readelf_output: str) -> set[str]:
    symbols: set[str] = set()
    for line in readelf_output.splitlines():
        fields = line.split()
        if len(fields) < 8 or not fields[0].rstrip(":").isdigit():
            continue
        symbol_type = fields[3]
        binding = fields[4]
        visibility = fields[5]
        section_index = fields[6]
        name = fields[7].split("@", 1)[0]
        if (
            symbol_type == "FUNC"
            and binding in {"GLOBAL", "WEAK"}
            and visibility in {"DEFAULT", "PROTECTED"}
            and section_index != "UND"
            and name.startswith("retro_")
        ):
            symbols.add(name)
    return symbols


def validate_artifact(path: Path, arch: str) -> dict:
    if arch not in ARCH_LAYOUT:
        raise PipelineError(f"unknown architecture: {arch}")
    if not path.is_file() or path.stat().st_size == 0:
        return {
            "status": "invalid",
            "errors": ["artifact is missing or empty"],
        }
    try:
        header = readelf_header(path)
    except PipelineError as exc:
        return {"status": "invalid", "errors": [str(exc)]}
    expected = ARCH_LAYOUT[arch]
    errors: list[str] = []
    if header["class"] != expected["elf_class"]:
        errors.append(f"expected {expected['elf_class']}, got {header['class']}")
    if "little endian" not in header["data"].lower():
        errors.append(f"expected little-endian ELF data, got {header['data']}")
    if header["machine"] != expected["machine"]:
        errors.append(f"expected {expected['machine']}, got {header['machine']}")
    if not header["type"].startswith("DYN"):
        errors.append(f"expected a shared object, got ELF type {header['type']}")
    if arch == "armhf" and "hard-float ABI" not in header["flags"]:
        errors.append("expected ARM hard-float ABI flag")
    dynamic = run(["readelf", "-d", str(path)], check=False)
    needed = re.findall(r"\(NEEDED\).*?\[([^]]+)\]", dynamic.stdout)
    if dynamic.returncode:
        errors.append("could not inspect dynamic dependencies")
    symbols = run(["readelf", "--dyn-syms", "--wide", str(path)], check=False)
    found_symbols = defined_libretro_symbols(symbols.stdout)
    missing_symbols = sorted(REQUIRED_LIBRETRO_SYMBOLS - found_symbols)
    if symbols.returncode:
        errors.append("could not inspect dynamic symbols")
    elif missing_symbols:
        errors.append("missing libretro symbols: " + ", ".join(missing_symbols))
    versions = run(["readelf", "--version-info", "--wide", str(path)], check=False)
    version_requirements = sorted(set(re.findall(r"Name:\s+(\S+)", versions.stdout)))
    if versions.returncode:
        errors.append("could not inspect dynamic version requirements")
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "elf": header,
        "needed": sorted(set(needed)),
        "version_requirements": version_requirements,
        "libretro_symbols": sorted(found_symbols),
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def audit_workflows(catalog: dict) -> dict:
    workflows = core_workflows()
    workflow_dir = ROOT / ".github" / "workflows"
    aggregate_workflows = sorted(
        {
            str(path.relative_to(ROOT))
            for pattern in AGGREGATE_WORKFLOW_GLOBS
            for path in workflow_dir.glob(pattern)
            if path.is_file()
        }
    )
    records = {}
    for core_id, path in workflows.items():
        text = path.read_text(encoding="utf-8")
        shared_pipeline_commands = re.findall(
            r"(?<!\S)python3\s+scripts/core_pipeline\.py\s+e2e(?=\s|$)",
            text,
        )
        runner_profiles = re.findall(
            r"--runner-profile\s+([A-Za-z0-9_-]+)(?=\s|$)", text
        )
        core_selectors = re.findall(
            r"--core\s+([A-Za-z0-9_+-]+)(?=\s|$)", text
        )
        records[core_id] = {
            "workflow": str(path.relative_to(ROOT)),
            "masked_build_failures": text.count('|| echo "::warning::'),
            "permits_info_only_package": (
                "_libretro.info" in text and 'if [ -n "$CONTENTS" ]' in text
            ),
            "uses_shared_pipeline": (
                len(shared_pipeline_commands) == 1
                and runner_profiles == ["github-actions"]
                and core_selectors == [core_id]
            ),
            "shared_pipeline_command_count": len(shared_pipeline_commands),
            "runner_profiles": runner_profiles,
            "core_selectors": core_selectors,
            "has_blank_source_default": bool(
                re.search(r"core_ref:[\s\S]{0,180}?default:\s*''", text)
            ),
        }
    workflow_ids = set(workflows)
    catalog_ids = set(catalog["cores"])
    unmigrated_workflows = sorted(
        core_id
        for core_id, record in records.items()
        if not record["uses_shared_pipeline"]
    )
    invalid_catalog_workflows = sorted(
        core_id
        for core_id in catalog_ids & workflow_ids
        if not records[core_id]["uses_shared_pipeline"]
    )
    return {
        "schema_version": 2,
        "catalog_core_count": len(catalog_ids),
        "core_workflow_count": len(workflows),
        "catalog_workflow_count": len(catalog_ids & workflow_ids),
        "missing_catalog_workflows": sorted(catalog_ids - workflow_ids),
        "uncataloged_workflows": sorted(workflow_ids - catalog_ids),
        "active_aggregate_workflows": aggregate_workflows,
        "invalid_catalog_workflows": invalid_catalog_workflows,
        "masked_build_failure_paths": sum(
            record["masked_build_failures"] for record in records.values()
        ),
        "info_only_risk_workflows": sum(
            bool(record["permits_info_only_package"]) for record in records.values()
        ),
        "shared_pipeline_workflows": sum(
            bool(record["uses_shared_pipeline"]) for record in records.values()
        ),
        "unmigrated_workflow_count": len(unmigrated_workflows),
        "unmigrated_workflows": unmigrated_workflows,
        "catalog_cores": sorted(catalog["cores"]),
        "workflows": records,
        "release_orchestration": audit_release_workflows(ROOT),
    }


def imported_core_baseline(
    spruceos: Path,
    core_id: str,
    pin_id: str,
) -> dict:
    """Import only one shipped core into a schema-v2 promotion candidate."""

    workflows = core_workflows()
    if core_id not in workflows:
        raise PipelineError(f"individual imported core is unknown: {core_id}")
    if not candidate_golden_id_is_well_formed(core_id, pin_id):
        raise PipelineError(
            "individual imported golden ID must be <core>-candidate-<label>"
        )
    if not (spruceos / ".git").exists():
        raise PipelineError(f"not a git checkout: {spruceos}")
    source_commit = git_head(spruceos)
    artifacts = {}
    for arch, layout in ARCH_LAYOUT.items():
        relative = Path(layout["directory"]) / f"{core_id}_libretro.so"
        artifact_path = spruceos / relative
        if artifact_path.is_file():
            artifacts[arch] = {
                "path": relative.as_posix(),
                **validate_artifact(artifact_path, arch),
            }
        else:
            artifacts[arch] = {"status": "not_shipped"}
    core_record = {
        "workflow": str(workflows[core_id].relative_to(ROOT)),
        "tier": "imported_baseline",
        "promotion_eligible": False,
        "artifacts": artifacts,
    }
    document = one_core_golden_document(
        core_id=core_id,
        pin_id=pin_id,
        created_at=utc_now(),
        baseline={
            "kind": "spruceos-shipped-artifacts",
            "repository_commit": source_commit,
            "provenance": "artifact-only",
            "warning": (
                "Imported binaries pin starting bytes but are not reproducible "
                "build goldens until source, submodules, recipe, and toolchain "
                "are recorded."
            ),
        },
        core_record=core_record,
        build_goldens={},
    )
    document["content_sha256"] = golden_content_sha256(document)
    return document


def verify_image(toolchain: dict) -> str:
    image = toolchain["image"]
    expected = toolchain["image_id"]
    result = run(["docker", "image", "inspect", "--format", "{{.Id}}", image])
    actual = result.stdout.strip()
    if actual != expected:
        raise PipelineError(
            f"toolchain image mismatch for {image}: expected {expected}, got {actual}"
        )
    return actual


def sanitized_shell_prelude(*, cargo: bool = False) -> str:
    """The environment-sanitizing script head every build runs under.

    The C image variant exports and verifies the cross toolchain from
    HOST_CC; the cargo variant (the Rust image carries no C cross
    toolchain) verifies the pinned cargo/zig tools instead, with the same
    hostile-environment scrub.
    """

    if cargo:
        return r"""
set -Eeuo pipefail
export LC_ALL=C
export LANG=C
umask 022
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS MAKE MAKEFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MFLAGS GIT_VERSION EMULATOR_BUILD HAS_GPU IS_X86 USE_BLARGG_APU ARCH ARCH_AARCH64 ARCH_ARM ARCH_X86 ARCH_X86_64 HAVE_SSA LIBRETRO_EMBED_FFMPEG OPENGL CMAKE_TOOLCHAIN_FILE SOURCE_DATE_EPOCH CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET CMAKE_BUILD_PARALLEL_LEVEL GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_CONFIG RUSTFLAGS RUSTC RUSTC_WRAPPER CARGO_BUILD_RUSTFLAGS CARGO_ENCODED_RUSTFLAGS
while IFS='=' read -r core_pipeline_environment_name _; do
  case "$core_pipeline_environment_name" in
    GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*|CARGO_TARGET_*_RUSTFLAGS) unset "$core_pipeline_environment_name" ;;
  esac
done < <(env)
for tool in cargo rustc zig cargo-zigbuild git; do
  command -v "$tool" >/dev/null
done
""".strip()
    return r"""
set -Eeuo pipefail
export LC_ALL=C
export LANG=C
umask 022
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS MAKE MAKEFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MFLAGS GIT_VERSION EMULATOR_BUILD HAS_GPU IS_X86 USE_BLARGG_APU ARCH ARCH_AARCH64 ARCH_ARM ARCH_X86 ARCH_X86_64 HAVE_SSA LIBRETRO_EMBED_FFMPEG OPENGL CMAKE_TOOLCHAIN_FILE SOURCE_DATE_EPOCH CMAKE_GENERATOR CMAKE_GENERATOR_PLATFORM CMAKE_GENERATOR_TOOLSET CMAKE_BUILD_PARALLEL_LEVEL GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM GIT_CONFIG_GLOBAL GIT_CONFIG_NOSYSTEM GIT_CONFIG
while IFS='=' read -r core_pipeline_environment_name _; do
  case "$core_pipeline_environment_name" in
    GIT_CONFIG_KEY_*|GIT_CONFIG_VALUE_*) unset "$core_pipeline_environment_name" ;;
  esac
done < <(env)
export CC="${HOST_CC}-gcc"
export CXX="${HOST_CC}-g++"
export AR="${HOST_CC}-ar"
export RANLIB="${HOST_CC}-ranlib"
export STRIP="${HOST_CC}-strip"
export CROSS_COMPILE="${HOST_CC}-"
export CHOST="${HOST_CC}"
for tool in "$CC" "$CXX" "$AR" "$RANLIB" "$STRIP"; do
  command -v "$tool" >/dev/null
done
""".strip()


def compile_definition_shell(spec: dict, arch: str) -> str:
    definitions = compile_definitions_for_target(spec, arch)
    if not definitions:
        return ""
    flags = " ".join(f"-D{definition}" for definition in definitions)
    value = shlex.quote(flags)
    return f"export CFLAGS={value}\nexport CXXFLAGS={value}"


def make_variable_markers(variables: object) -> list[str]:
    if not make_variable_mapping_is_well_formed(variables):
        return []
    assert isinstance(variables, dict)
    canonical = make_output_sync_prefix(variables) + " ".join(
        f"{name}={value}" for name, value in variables.items()
    )
    return [
        "CORE_PIPELINE_MAKEFLAGS|" + canonical,
        *[
            f"CORE_PIPELINE_MAKE_VARIABLE|{name}|{value}|command line"
            for name, value in variables.items()
        ],
    ]


def make_variable_log_markers(spec: dict) -> list[str]:
    return make_variable_markers(validated_make_variables(spec))


def command_scoped_native_git_version(spec: dict) -> str | None:
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
    contract = validated_git_version(spec)
    if (
        contract is None
        or contract.get("derivation") != NATIVE_GIT_VERSION_DERIVATION
        or spec.get("source", {}).get("commit")
        not in COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS
    ):
        raise PipelineError("command-scoped GIT_VERSION contract is invalid")
    return f'"{contract["value"]}"'


def libretro_build_shell(spec: dict, source_key: str) -> str:
    command_scoped_version = command_scoped_native_git_version(spec)
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
    if not native_git_version_spec_is_well_formed(spec, "cap32"):
        return f"./libretro-build.sh {source_key}"
    return "\n".join(
        [
            f"printf '%s\\n' {shlex.quote(CAP32_MAKE_TRACE_MARKER)}",
            f"MAKEFLAGS=--trace ./libretro-build.sh {source_key}",
        ]
    )


def make_variable_shell(spec: dict) -> str:
    variables = validated_make_variables(spec)
    if not variables:
        return ""
    profile = make_variable_profile(variables)
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
    canonical = shlex.quote(canonical_makeflags(spec))
    probe_path = "/tmp/core-pipeline-make-variable-origins.mk"
    facts = _make_variable_profile_facts()[profile]
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


def git_version_log_markers(spec: dict) -> list[str]:
    contract = validated_git_version(spec)
    if contract is None:
        return []
    return git_version_markers(contract, spec.get("source", {}).get("commit"))


def source_identity_log_markers(core_id: object, spec: object) -> list[str]:
    """Return exact log markers for source-native contracts without a macro."""

    if (
        core_id == MAME2003_PLUS_CORE_ID
        and mame2003_plus_spec_is_well_formed(spec)
    ):
        return [MAME2003_PLUS_SOURCE_IDENTITY_MARKER]
    if core_id == FREEINTV_CORE_ID and freeintv_spec_is_well_formed(spec):
        return [FREEINTV_SOURCE_IDENTITY_MARKER]
    if core_id == VEMULATOR_CORE_ID and vemulator_spec_is_well_formed(spec):
        return [VEMULATOR_SOURCE_IDENTITY_MARKER]
    return []


def source_identity_shell(core_id: object, spec: object) -> str:
    """Emit reviewed source identity after checkout for source-native cores."""

    return "\n".join(
        f"printf '%s\\n' {shlex.quote(marker)}"
        for marker in source_identity_log_markers(core_id, spec)
    )


def git_version_shell(spec: dict) -> str:
    contract = validated_git_version(spec)
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
        command_scoped_version = command_scoped_native_git_version(spec)
        make_environment = ""
        if command_scoped_version is not None:
            markers = git_version_markers(
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


def source_date_epoch_shell(spec: dict) -> str:
    value = validated_source_date_epoch(spec)
    return "" if value is None else f"export SOURCE_DATE_EPOCH={value}"


def source_date_epoch_provenance_shell(source_dir: str, spec: dict) -> str:
    expected = validated_source_date_epoch(spec)
    if expected is None:
        return ""
    directory = shlex.quote(source_dir)
    return f"""
actual_source_date_epoch="$(git -C {directory} show -s --format=%ct HEAD)"
printf "%s\\n" "$actual_source_date_epoch" > /output/source-date-epoch.txt
test "$actual_source_date_epoch" = {expected}
""".strip()


def direct_cmake_cache_log_document(
    spec: dict, arch: str, tool_paths: object
) -> dict:
    contract = direct_cmake_contract_for_target(spec, arch)
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
    spec: dict, arch: str, tool_paths: object | None = None
) -> list[str]:
    contract = direct_cmake_contract_for_target(spec, arch)
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
                direct_cmake_cache_log_document(spec, arch, tool_paths),
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
    build_log_text: str, spec: dict, arch: str
) -> bool:
    expected_static = direct_cmake_log_markers(spec, arch)
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
            spec, arch, cache_document.get("tools")
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


def overlay_mount_args(spec: dict, arch: str) -> list[str]:
    """Mount each declared patch read-only into the build container.

    Driver-agnostic: any build type that declares build.overlays has its
    patches mounted at /recipe-overlays/<index>.patch for overlay_apply_shell().
    """

    args: list[str] = []
    for index, overlay in enumerate(build_overlays_for_target(spec, arch)):
        patch = require_manifest_reference_path(
            {"path": overlay["patch_path"]},
            ROOT / "patches",
            f"{arch} overlay patch",
        )
        if not patch.is_file() or sha256_file(patch) != overlay["patch_sha256"]:
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


def direct_cmake_overlay_mount_args(spec: dict, arch: str) -> list[str]:
    return overlay_mount_args(spec, arch)


def metadata_replacement_container_path(replacement: object) -> str:
    if vecx_metadata_replacement_contract_is_well_formed(replacement):
        return "/metadata-replacements/vecx.info"
    if atari800_metadata_replacement_contract_is_well_formed(replacement):
        return "/metadata-replacements/atari800.info"
    if picodrive_metadata_replacement_contract_is_well_formed(replacement):
        return "/metadata-replacements/picodrive.info"
    raise PipelineError("metadata replacement contract is not reviewed")


def repo_metadata(spec: dict) -> dict | None:
    """The repo-pinned metadata contract, when the catalog selected it."""

    metadata = spec.get("metadata", {})
    if not isinstance(metadata, dict) or "repo_path" not in metadata:
        return None
    return metadata


def metadata_replacement_mount_args(spec: dict) -> list[str]:
    pinned = repo_metadata(spec)
    if pinned is not None:
        path = safe_child(ROOT, pinned["repo_path"], "repo metadata path")
        return ["-v", f"{path}:/metadata-repo/{pinned['artifact_name']}:ro"]
    replacement = validated_metadata_replacement(spec)
    if replacement is None:
        return []
    path = safe_child(ROOT, replacement["path"], "metadata replacement path")
    mounted = metadata_replacement_container_path(replacement)
    return ["-v", f"{path}:{mounted}:ro"]


def metadata_replacement_markers(replacement: object) -> list[str]:
    if not metadata_replacement_contract_is_well_formed(replacement):
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
    build_log_text: str, replacement: object
) -> bool:
    expected = metadata_replacement_markers(replacement)
    if not expected:
        return False
    actual = [
        line
        for line in build_log_text.splitlines()
        if line.startswith("CORE_PIPELINE_METADATA_REPLACEMENT|")
    ]
    return actual == expected


def metadata_install_shell(spec: dict) -> str:
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
    replacement = validated_metadata_replacement(spec)
    if replacement is None:
        return f"test -s {source}\ninstall -m 0644 {source} /output/{name}"
    mounted = metadata_replacement_container_path(replacement)
    marker = metadata_replacement_markers(replacement)[0]
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


def recipe_profile_shell(spec: dict, arch: str) -> str:
    """Render an exact reviewed source-root build, when one is selected."""

    profile = validated_recipe_profile(spec)
    if profile is None:
        return ""
    return picodrive_recipe_shell(spec, arch)


def direct_cmake_overlay_shell(spec: dict, arch: str, source_dir: str) -> str:
    contract = direct_cmake_contract_for_target(spec, arch)
    if contract is None:
        return ""
    lines: list[str] = []
    markers = direct_cmake_log_markers(spec, arch)
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


def direct_cmake_configure_shell(spec: dict, arch: str, source_dir: str) -> str:
    contract = direct_cmake_contract_for_target(spec, arch)
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
    cmake_marker = shlex.quote(direct_cmake_log_markers(spec, arch)[-1])
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
            "| awk '$2 == \"commit\" { print $3, $4 }' > /output/submodules.txt"
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


def container_build_script(core_id: str, arch: str, spec: dict, resolver: dict) -> str:
    source = spec["source"]
    build = spec["build"]
    commit = source["commit"]
    artifact_name = build["artifact_name"]
    prelude = [sanitized_shell_prelude(cargo=spec.get("build", {}).get("driver") == "direct-cargo")]
    epoch_shell = source_date_epoch_shell(spec)
    if epoch_shell:
        prelude.append(epoch_shell)
    definition_shell = compile_definition_shell(spec, arch)
    if definition_shell:
        prelude.append(definition_shell)
    common_end = f"""
{metadata_install_shell(spec)}
"$CC" --version | head -n 1 > /output/compiler.txt
"$CC" -print-sysroot > /output/sysroot.txt
chown "$OUTPUT_UID:$OUTPUT_GID" /output/*
""".strip()
    if build["driver"] == "direct-cargo":
        # The Rust image has no C cross compiler or sysroot; the recorded
        # compiler identity is the pinned rustc, and zig owns cross linkage.
        common_end = f"""
{metadata_install_shell(spec)}
rustc --version > /output/compiler.txt
zig version > /output/sysroot.txt
chown "$OUTPUT_UID:$OUTPUT_GID" /output/*
""".strip()
    if build["driver"] == "libretro-super":
        key = shlex.quote(build["source_key"])
        source_dir = build["source_dir"]
        output_path = shlex.quote(build["output_path"])
        staged_name = shlex.quote(artifact_name)
        is_fbneo_spec = fbneo_spec_is_well_formed(spec)
        is_mame2003_plus_spec = mame2003_plus_spec_is_well_formed(spec)
        if core_id == FBNEO_CORE_ID:
            selected_build_shell = fbneo_build_shell(spec, key, arch)
        elif is_fbneo_spec:
            raise PipelineError("FBNeo build spec requires its exact core identity")
        elif core_id == MAME2003_PLUS_CORE_ID:
            selected_build_shell = mame2003_plus_build_shell(spec, key, arch)
        elif is_mame2003_plus_spec:
            raise PipelineError(
                "MAME 2003-Plus build spec requires its exact core identity"
            )
        else:
            profile_build_shell = recipe_profile_shell(spec, arch)
            selected_build_shell = profile_build_shell or libretro_build_shell(
                spec, key
            )
        overlay_apply = overlay_apply_shell(spec, arch, source_dir)
        return "\n".join(
            [
                *prelude,
                "cd /libretro-super",
                resolver_provenance_shell(resolver),
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
                source_identity_shell(core_id, spec),
                source_date_epoch_provenance_shell(source_dir, spec),
                snes9x2005_shell(spec),
                make_variable_shell(spec),
                git_version_shell(spec),
                *([overlay_apply] if overlay_apply else []),
                f"rm -f {output_path}",
                selected_build_shell,
                core_81_generated_version_shell(spec),
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
                source_date_epoch_provenance_shell("/tmp/core-source", spec),
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
                f'make -j"$(nproc)" {make_subdir_arg}{platform_arg}{make_args_arg}CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB"',
                f"test -s {output_path}",
                f"install -m 0644 {output_path} /output/{staged_name}",
                common_end,
            ]
        )
    if build["driver"] == "direct-cargo":
        contract = direct_cargo_contract_for_target(spec, arch)
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
                source_date_epoch_provenance_shell("/tmp/core-source", spec),
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
                f"cargo zigbuild --locked --target {shlex.quote(triple)} --release",
                f"test -s {product}",
                f"install -m 0644 {product} /output/{staged_name}",
                common_end,
            ]
        )
    if build["driver"] == "direct-cmake":
        contract = direct_cmake_contract_for_target(spec, arch)
        assert contract is not None
        source_url = shlex.quote(source["url"])
        revision = shlex.quote(commit)
        source_dir = "/tmp/core-source"
        quoted_source_dir = shlex.quote(source_dir)
        output_path = shlex.quote(f"/tmp/core-build/{build['output_path']}")
        staged_name = shlex.quote(artifact_name)
        cmake = contract["cmake"]
        overlay_shell = direct_cmake_overlay_shell(spec, arch, source_dir)
        configure_shell = direct_cmake_configure_shell(spec, arch, source_dir)
        build_command = (
            "cmake --build /tmp/core-build "
            f"--target {shlex.quote(cmake['target'])} "
            '--parallel "$(nproc)" --verbose'
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
                source_date_epoch_provenance_shell(source_dir, spec),
                overlay_shell,
                configure_shell,
                build_command,
                f"test -s {output_path}",
                f"install -m 0644 {output_path} /output/{staged_name}",
                common_end,
            ]
        )
    raise PipelineError(f"unsupported driver for {core_id}: {build['driver']}")


def parse_submodules(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(.)([0-9a-f]{40})\s+(\S+)(?:\s+.*)?$", line)
        if match:
            records.append(
                {
                    "state": match.group(1),
                    "commit": match.group(2),
                    "path": match.group(3),
                }
            )
    return records


def core_spec_sha256(spec: dict) -> str:
    material = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(material)


def recipe_record(catalog_path: Path, core_id: str, spec: dict) -> dict:
    workflow = ROOT / spec["workflow"]
    pipeline_bundle = pipeline_source_bundle()
    catalog_snapshot = load_json(catalog_path)
    commit_blacklist = catalog_snapshot.get("commit_blacklist")
    if not commit_blacklist_reference_is_well_formed(commit_blacklist):
        raise PipelineError("recipe catalog commit_blacklist reference is invalid")
    return {
        "repository_head": git_head(ROOT),
        "repository_dirty": bool(run(["git", "status", "--short"], cwd=ROOT).stdout),
        "catalog_path": str(catalog_path.relative_to(ROOT)),
        "catalog_sha256": sha256_file(catalog_path),
        "core_spec_sha256": core_spec_sha256(spec),
        "pipeline_sha256": sha256_file(Path(__file__)),
        "pipeline_bundle": pipeline_bundle,
        "commit_blacklist": copy.deepcopy(commit_blacklist),
        "workflow": spec["workflow"],
        "workflow_sha256": sha256_file(workflow),
        "core_id": core_id,
    }


def _core_log_contract_proofs() -> dict[str, Callable[..., bool]]:
    """Bind registry names to their current individual proof callables.

    Collected by introspection over the contracts package: every
    ``*_log_proves_contract`` function *defined in* a contract module
    (``__module__`` check, so re-exports and the shared engine entry points
    never masquerade as a per-core proof) whose name the registry declares.
    The completeness check below is unchanged -- a registry entry without a
    bound callable still fails closed.
    """

    import importlib
    import pkgutil

    import core_pipeline_lib.contracts as contracts_package

    declared = {contract.proof_name for contract in CORE_LOG_CONTRACTS}
    proofs: dict[str, Callable[..., bool]] = {}
    for info in pkgutil.iter_modules(contracts_package.__path__):
        module = importlib.import_module(
            f"core_pipeline_lib.contracts.{info.name}"
        )
        for name, value in vars(module).items():
            if (
                name in declared
                and callable(value)
                and getattr(value, "__module__", "") == module.__name__
            ):
                proofs[name] = value
    # The same testability seam as the spec guards: a proof patched onto this
    # module's namespace (mock.patch.object(pipeline, ...)) overrides the
    # module-bound callable for names that remain pipeline attributes.
    for name in list(proofs):
        if name in globals():
            # Unconditional, not gated on callable(): a test (or a bug) that
            # sets the attribute to a non-callable must reach the tripwire
            # below, exactly as the literal map allowed.
            proofs[name] = globals()[name]
    registered_names = {contract.proof_name for contract in CORE_LOG_CONTRACTS}
    if set(proofs) != registered_names:
        raise PipelineError("core log contract proof mapping is incomplete")
    if any(not callable(proof) for proof in proofs.values()):
        raise PipelineError("core log contract proof mapping contains a non-callable")
    return proofs


# The same seam for proofs: every registry-declared proof becomes a module
# attribute (patched by tests via mock.patch.object), seeded from the contract
# modules. Runs at import so an unbound registry entry still fails closed at
# the earliest moment, exactly as the literal map did.
for _proof_name, _proof in _core_log_contract_proofs().items():
    globals().setdefault(_proof_name, _proof)
del _proof_name, _proof


def registered_core_log_contract_proves(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object = None,
    source_tree: object = None,
) -> bool:
    """Run the registered proof owned by one individual core."""

    contract = core_log_contract_for(core_id)
    if contract is None:
        return True
    proof = _core_log_contract_proofs()[contract.proof_name]
    if contract.proof_kind == "core-arch":
        return proof(build_log_text, core_id, arch)
    if contract.proof_kind == "core-arch-source":
        return proof(
            build_log_text,
            core_id,
            arch,
            source_commit,
            source_tree,
        )
    raise PipelineError(
        f"unsupported core log contract proof kind: {contract.proof_kind}"
    )


def perform_build(
    *,
    catalog_path: Path,
    catalog: dict,
    core_id: str,
    arch: str,
    output_dir: Path,
) -> dict:
    if core_id not in catalog["cores"]:
        raise PipelineError(f"core is not in the build catalog: {core_id}")
    spec = catalog["cores"][core_id]
    if arch not in spec["targets"]:
        raise PipelineError(f"{core_id} does not enable target {arch}")
    require_catalog_cores_eligible(catalog, [core_id])
    toolchain = catalog["toolchains"][build_toolchain_key(spec, arch)]
    compile_definitions = compile_definitions_for_target(spec, arch)
    make_variables = validated_make_variables(spec)
    git_version = validated_git_version(spec)
    metadata_replacement = validated_metadata_replacement(spec)
    source_date_epoch = validated_source_date_epoch(spec)
    expected_build_contract = normalized_build_contract(spec, arch)
    archive_provenance = expected_archive_provenance(catalog, build_toolchain_key(spec, arch))
    if output_dir.exists():
        raise PipelineError(f"refusing to reuse build output directory: {output_dir}")
    output_dir.mkdir(parents=True)
    image_id = verify_image(toolchain)
    script = container_build_script(core_id, arch, spec, catalog["resolver"])
    log_path = output_dir / "build.log"
    command = [
        "docker",
        "run",
        "--rm",
        "-e",
        f"OUTPUT_UID={os.getuid()}",
        "-e",
        f"OUTPUT_GID={os.getgid()}",
        "-v",
        f"{output_dir.resolve()}:/output",
        *metadata_replacement_mount_args(spec),
        *overlay_mount_args(spec, arch),
        image_id,
        "bash",
        "-lc",
        script,
    ]
    print(f"local build: {core_id}/{arch} ({image_id[7:19]})", flush=True)
    started = utc_now()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        exit_code = process.wait()
    artifact_path = output_dir / spec["build"]["artifact_name"]
    metadata_path = output_dir / spec["metadata"]["artifact_name"]
    validation = apply_artifact_dependency_policy(
        validate_artifact(artifact_path, arch), spec
    )
    if compile_definitions:
        build_log_text = read_build_log(log_path, "build log")
        if not compile_log_proves_definitions(
            build_log_text, compile_definitions, arch
        ):
            validation.setdefault("errors", []).append(
                "catalog compile definitions were not observed together as exact "
                "tokens on a compiler -c command: "
                + ", ".join(compile_definitions)
            )
            validation["status"] = "invalid"
    if make_variables:
        build_log_text = read_build_log(log_path, "build log")
        if not make_variable_log_proves_contract(
            build_log_text, make_variables, arch
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact "
                + make_variable_contract_name(make_variables)
                + " make-variable origin and compile contract"
            )
            validation["status"] = "invalid"
    if git_version is not None:
        build_log_text = read_build_log(log_path, "build log")
        if not git_version_log_proves_contract(
            build_log_text,
            git_version,
            spec["source"]["commit"],
            arch,
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact commit-derived GIT_VERSION "
                "GNU Make origin and target compile token"
            )
            validation["status"] = "invalid"
    log_contract = core_log_contract_for(core_id)
    if log_contract is not None:
        build_log_text = read_build_log(log_path, "build log")
        if not registered_core_log_contract_proves(
            build_log_text,
            core_id,
            arch,
            spec["source"]["commit"],
            spec["source"]["tree"],
        ):
            validation.setdefault("errors", []).append(
                log_contract.failure_message
            )
            validation["status"] = "invalid"
    if metadata_replacement is not None:
        build_log_text = read_build_log(log_path, "build log")
        if not metadata_replacement_log_proves_contract(
            build_log_text, metadata_replacement
        ):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact metadata replacement contract"
            )
            validation["status"] = "invalid"
    if spec["build"]["driver"] == "direct-cmake":
        build_log_text = read_build_log(log_path, "build log")
        if not direct_cmake_log_proves_contract(build_log_text, spec, arch):
            validation.setdefault("errors", []).append(
                "build log does not prove the exact direct-CMake and overlay contract"
            )
            validation["status"] = "invalid"
    metadata_validation = {
        "path": metadata_path.name if metadata_path.is_file() else None,
        "status": "valid" if metadata_path.is_file() and metadata_path.stat().st_size else "invalid",
    }
    if metadata_validation["status"] == "valid":
        metadata_validation.update(
            {"size": metadata_path.stat().st_size, "sha256": sha256_file(metadata_path)}
        )
    else:
        metadata_validation["errors"] = ["metadata file is missing or empty"]
    if not metadata_matches_replacement(metadata_validation, metadata_replacement):
        metadata_validation.setdefault("errors", []).append(
            "metadata output does not match the exact catalog replacement"
        )
        metadata_validation["status"] = "invalid"
    source_commit_path = output_dir / "source-commit.txt"
    recorded_commit = (
        source_commit_path.read_text(encoding="utf-8").strip()
        if source_commit_path.is_file()
        else None
    )
    source_tree_path = output_dir / "source-tree.txt"
    recorded_tree = (
        source_tree_path.read_text(encoding="utf-8").strip()
        if source_tree_path.is_file()
        else None
    )
    if recorded_commit != spec["source"]["commit"]:
        validation.setdefault("errors", []).append(
            f"source pin mismatch: expected {spec['source']['commit']}, got {recorded_commit}"
        )
        validation["status"] = "invalid"
    expected_tree = spec["source"].get("tree")
    if expected_tree is not None and recorded_tree != expected_tree:
        validation.setdefault("errors", []).append(
            f"source tree mismatch: expected {expected_tree}, got {recorded_tree}"
        )
        validation["status"] = "invalid"
    recorded_source_date_epoch: int | None = None
    source_date_epoch_path = output_dir / "source-date-epoch.txt"
    if source_date_epoch_path.is_file():
        raw_source_date_epoch = source_date_epoch_path.read_text(
            encoding="utf-8"
        ).strip()
        if raw_source_date_epoch.isdecimal():
            recorded_source_date_epoch = int(raw_source_date_epoch)
    if recorded_source_date_epoch != source_date_epoch:
        validation.setdefault("errors", []).append(
            "source commit epoch mismatch: expected "
            f"{source_date_epoch}, got {recorded_source_date_epoch}"
        )
        validation["status"] = "invalid"
    recorded_build_contract = copy.deepcopy(expected_build_contract)
    if source_date_epoch is not None:
        recorded_build_contract["source_date_epoch"] = recorded_source_date_epoch
    actual_resolver = {
        "libretro_super_commit": (
            (output_dir / "resolver-commit.txt").read_text(encoding="utf-8").strip()
            if (output_dir / "resolver-commit.txt").is_file()
            else None
        )
    }
    for prefix in ("core_rules", "fetch_script", "build_script"):
        value_path = output_dir / f"resolver-{prefix}-sha256.txt"
        actual_resolver[f"{prefix}_path"] = catalog["resolver"][f"{prefix}_path"]
        actual_resolver[f"{prefix}_sha256"] = (
            value_path.read_text(encoding="utf-8").strip() if value_path.is_file() else None
        )
    result = (
        "passed"
        if exit_code == 0
        and validation["status"] == "valid"
        and metadata_validation["status"] == "valid"
        else "failed"
    )
    record = {
        "schema_version": 2,
        "local_only": True,
        "publication": "disabled",
        "started_at": started,
        "finished_at": utc_now(),
        "core_id": core_id,
        "architecture": arch,
        "result": result,
        "build_exit_code": exit_code,
        "source": {
            **spec["source"],
            "resolved_commit": recorded_commit,
            "tree": recorded_tree,
            "resolved_url": (
                (output_dir / "source-url.txt").read_text(encoding="utf-8").strip()
                if (output_dir / "source-url.txt").is_file()
                else None
            ),
            "submodules": parse_submodules(output_dir / "submodules.txt"),
        },
        "recipe": recipe_record(catalog_path, core_id, spec),
        "toolchain": {
            **toolchain,
            "archive_provenance": archive_provenance,
            "resolved_image_id": image_id,
            "libretro_super_commit": actual_resolver["libretro_super_commit"],
            "resolver_digests": actual_resolver,
            "compiler": (
                (output_dir / "compiler.txt").read_text(encoding="utf-8").strip()
                if (output_dir / "compiler.txt").is_file()
                else None
            ),
            "sysroot": (
                (output_dir / "sysroot.txt").read_text(encoding="utf-8").strip()
                if (output_dir / "sysroot.txt").is_file()
                else None
            ),
        },
        "build": {
            **recorded_build_contract,
            "log": "build.log",
            "log_sha256": sha256_file(log_path),
        },
        "artifact": {
            "path": artifact_path.name if artifact_path.is_file() else None,
            **validation,
        },
        "metadata": metadata_validation,
    }
    atomic_write_json(output_dir / "build-record.json", record)
    print(f"result: {core_id}/{arch}: {result}", flush=True)
    return record


def validate_build_record_identity(
    record: dict,
    record_path: Path,
    catalog_path: Path,
    catalog: dict,
) -> tuple[Path, Path, Path]:
    record_path = require_contained(record_path, ROOT / ".local-e2e", "build record")
    if record.get("result") != "passed" or record.get("build_exit_code") != 0:
        raise PipelineError("only a successful build record can be promoted")
    if not record.get("local_only") or record.get("publication") != "disabled":
        raise PipelineError("build record is not marked local-only/publication-disabled")
    if type(record.get("schema_version")) is not int or record["schema_version"] != 2:
        raise PipelineError("build record schema_version must be the exact integer 2")
    core_id = record.get("core_id")
    arch = record.get("architecture")
    if core_id not in catalog["cores"]:
        raise PipelineError("build record core is not in the current catalog")
    spec = catalog["cores"][core_id]
    if arch not in spec["targets"]:
        raise PipelineError("build record architecture is not enabled for its core")
    expected_compile_definitions = compile_definitions_for_target(spec, arch)
    expected_make_variables = validated_make_variables(spec)
    expected_git_version = validated_git_version(spec)
    expected_generated_source = validated_generated_source(spec)
    expected_recipe_profile = validated_recipe_profile(spec)
    expected_metadata_replacement = validated_metadata_replacement(spec)
    expected_source_date_epoch = validated_source_date_epoch(spec)
    expected_build_contract = normalized_build_contract(spec, arch)

    recipe = record.get("recipe", {})
    catalog_path = require_contained(catalog_path, ROOT, "catalog")
    expected_recipe = {
        "catalog_path": str(catalog_path.relative_to(ROOT)),
        "catalog_sha256": sha256_file(catalog_path),
        "core_id": core_id,
        "core_spec_sha256": core_spec_sha256(spec),
        "pipeline_sha256": sha256_file(Path(__file__)),
        "pipeline_bundle": pipeline_source_bundle(),
        "commit_blacklist": copy.deepcopy(catalog["commit_blacklist"]),
        "workflow": spec["workflow"],
        "workflow_sha256": sha256_file(ROOT / spec["workflow"]),
    }
    for key, expected in expected_recipe.items():
        if recipe.get(key) != expected:
            raise PipelineError(f"build record recipe identity mismatch: {key}")
    if not SHA1_RE.fullmatch(recipe.get("repository_head", "")):
        raise PipelineError("build record repository head is not a full SHA")
    if not isinstance(recipe.get("repository_dirty"), bool):
        raise PipelineError("build record repository dirty state is missing")

    source = record.get("source", {})
    for key, expected in spec["source"].items():
        if source.get(key) != expected:
            raise PipelineError(f"build record source identity mismatch: {key}")
    if source.get("resolved_commit") != spec["source"]["commit"]:
        raise PipelineError("resolved source does not match the requested commit")
    if source.get("resolved_url") != spec["source"]["url"]:
        raise PipelineError("resolved source URL does not match the source pin")
    if not SHA1_RE.fullmatch(source.get("tree", "")):
        raise PipelineError("resolved source tree is not a full SHA")
    if (
        core_id == VEMULATOR_CORE_ID
        and not vemulator_golden_source_is_well_formed(core_id, source)
    ):
        raise PipelineError(
            "build record source does not match the exact VEmulator contract"
        )
    if (
        core_id == FREEINTV_CORE_ID
        and not freeintv_golden_source_is_well_formed(core_id, source)
    ):
        raise PipelineError(
            "build record source does not match the exact FreeIntv contract"
        )
    if (
        core_id == PICODRIVE_CORE_ID
        and not picodrive_golden_source_is_well_formed(core_id, source)
    ):
        raise PipelineError(
            "build record source does not match the exact Picodrive contract"
        )
    if (
        core_id == MAME2003_PLUS_CORE_ID
        and not mame2003_plus_golden_source_is_well_formed(core_id, source)
    ):
        raise PipelineError(
            "build record source does not match the exact MAME2003+ contract"
        )
    if (
        core_id == FBNEO_CORE_ID
        and not fbneo_golden_source_is_well_formed(core_id, source)
    ):
        raise PipelineError(
            "build record source does not match the exact FBNeo contract"
        )
    for submodule in source.get("submodules", []):
        if (
            submodule.get("state") != " "
            or not SHA1_RE.fullmatch(submodule.get("commit", ""))
            or not submodule.get("path")
        ):
            raise PipelineError("submodule state is not coherent with the pinned source")

    toolchain = record.get("toolchain", {})
    expected_toolchain = catalog["toolchains"][build_toolchain_key(spec, arch)]
    for key, expected in expected_toolchain.items():
        if toolchain.get(key) != expected:
            raise PipelineError(f"build record toolchain identity mismatch: {key}")
    if toolchain.get("resolved_image_id") != expected_toolchain["image_id"]:
        raise PipelineError("resolved toolchain image does not match the pin")
    if toolchain.get("archive_provenance") != expected_archive_provenance(
        catalog, build_toolchain_key(spec, arch)
    ):
        raise PipelineError("build record archive provenance does not match the lock")
    if build_toolchain_key(spec, arch) == "rust":
        # The Rust image carries no libretro-super checkout; a cargo record
        # must have captured NO resolver identity at all -- a value here
        # would mean the build ran in the wrong image.
        expected_absent_resolver = {"libretro_super_commit": None}
        for prefix in ("core_rules", "fetch_script", "build_script"):
            expected_absent_resolver[f"{prefix}_path"] = catalog["resolver"][
                f"{prefix}_path"
            ]
            expected_absent_resolver[f"{prefix}_sha256"] = None
        if (
            toolchain.get("libretro_super_commit") is not None
            or toolchain.get("resolver_digests") != expected_absent_resolver
        ):
            raise PipelineError(
                "cargo build record captured resolver identity from the wrong image"
            )
    else:
        if toolchain.get("libretro_super_commit") != catalog["resolver"][
            "libretro_super_commit"
        ]:
            raise PipelineError("build record resolver commit does not match the catalog")
        if toolchain.get("resolver_digests") != catalog["resolver"]:
            raise PipelineError("build record resolver digests do not match the catalog")
    if not toolchain.get("compiler") or toolchain.get("sysroot") is None:
        raise PipelineError("build record toolchain fingerprint is incomplete")

    artifact = record.get("artifact", {})
    if artifact.get("path") != spec["build"]["artifact_name"]:
        raise PipelineError("build artifact name does not match the catalog")
    artifact_path = safe_child(record_path.parent, artifact["path"], "build artifact path")
    current_artifact = apply_artifact_dependency_policy(
        validate_artifact(artifact_path, arch), spec
    )
    dependency_policy = validated_forbidden_needed_prefixes(spec)
    if (
        current_artifact.get("status") != "valid"
        or current_artifact.get("sha256") != artifact.get("sha256")
        or current_artifact.get("size") != artifact.get("size")
        or (
            dependency_policy
            and (
                not isinstance(current_artifact.get("needed"), list)
                or not isinstance(artifact.get("needed"), list)
                or current_artifact.get("needed") != artifact.get("needed")
            )
        )
    ):
        raise PipelineError("build artifact is missing, invalid, or no longer matches its record")

    metadata = record.get("metadata", {})
    if metadata.get("path") != spec["metadata"]["artifact_name"]:
        raise PipelineError("build metadata name does not match the catalog")
    metadata_path = safe_child(record_path.parent, metadata["path"], "build metadata path")
    if (
        metadata.get("status") != "valid"
        or not metadata_path.is_file()
        or metadata_path.stat().st_size != metadata.get("size")
        or sha256_file(metadata_path) != metadata.get("sha256")
    ):
        raise PipelineError("build metadata is missing or no longer matches its record")
    if not metadata_matches_replacement(metadata, expected_metadata_replacement):
        raise PipelineError(
            "build metadata does not match the exact catalog replacement"
        )

    build = record.get("build", {})
    record_has_recipe_profile = (
        isinstance(build, dict) and "recipe_profile" in build
    )
    is_direct_cmake = spec["build"]["driver"] == "direct-cmake"
    is_strict_build_contract = (
        is_direct_cmake
        or bool(expected_make_variables)
        or expected_git_version is not None
        or expected_generated_source is not None
        or expected_recipe_profile is not None
        or record_has_recipe_profile
        or core_id in EXACT_SOURCE_NATIVE_CORE_IDS
    )
    is_combined_git_make_contract = bool(expected_make_variables) and (
        expected_git_version is not None
        and expected_git_version.get("derivation")
        == NATIVE_GIT_VERSION_DERIVATION
        and core_id in COMBINED_NATIVE_MAKE_CORE_IDS
    )
    strict_record_mismatch = is_strict_build_contract and (
        not isinstance(build, dict)
        or set(build) != set(expected_build_contract).union({"log", "log_sha256"})
        or recorded_build_contract(build) != expected_build_contract
        or (
            expected_generated_source is not None
            and not core_81_golden_build_contract_is_well_formed(
                build, spec["source"]["commit"], core_id, source
            )
        )
        or (
            is_combined_git_make_contract
            and not combined_git_version_make_golden_build_contract_is_well_formed(
                build, spec["source"]["commit"], core_id, source
            )
        )
        or (
            not is_combined_git_make_contract
            and bool(expected_make_variables)
            and not make_variable_golden_build_contract_is_well_formed(build)
        )
        or (
            not is_combined_git_make_contract
            and
            expected_git_version is not None
            and not git_version_golden_build_contract_is_well_formed(
                build, spec["source"]["commit"], core_id, source, arch
            )
        )
        or (
            core_id == VEMULATOR_CORE_ID
            and not vemulator_golden_build_contract_is_well_formed(
                build, spec["source"]["commit"], core_id, source
            )
        )
        or (
            core_id == FREEINTV_CORE_ID
            and not freeintv_golden_build_contract_is_well_formed(
                build, spec["source"]["commit"], core_id, source
            )
        )
        or (
            expected_recipe_profile is not None
            and not picodrive_golden_build_contract_is_well_formed(
                build,
                spec["source"]["commit"],
                core_id,
                source,
                arch,
            )
        )
    )
    legacy_record_mismatch = not is_strict_build_contract and (
        not isinstance(build, dict)
        or build.get("driver") != spec["build"]["driver"]
        or build.get("environment") != "sanitized-v1"
        or (
            expected_source_date_epoch is not None
            and "compile_definitions" not in build
        )
        or build.get("compile_definitions", []) != expected_compile_definitions
        or not build_source_date_epoch_matches(build, expected_source_date_epoch)
    )
    if strict_record_mismatch or legacy_record_mismatch:
        raise PipelineError("build record compile environment does not match the catalog")
    build_log = safe_child(record_path.parent, build.get("log", ""), "build log path")
    if not build_log.is_file() or sha256_file(build_log) != build.get("log_sha256"):
        raise PipelineError("build log is missing or no longer matches its record")
    build_log_text = read_build_log(build_log, "build log")
    if not compile_log_proves_definitions(
        build_log_text, expected_compile_definitions, arch
    ):
        raise PipelineError(
            "build log does not prove the catalog compile definitions on a "
            "compiler -c command: "
            + ", ".join(expected_compile_definitions)
        )
    if expected_make_variables and not make_variable_log_proves_contract(
        build_log_text, expected_make_variables, arch
    ):
        raise PipelineError(
            "build log does not prove the exact "
            + make_variable_contract_name(expected_make_variables)
            + " make-variable origin and compile contract"
        )
    if expected_git_version is not None and not git_version_log_proves_contract(
        build_log_text,
        expected_git_version,
        spec["source"]["commit"],
        arch,
    ):
        raise PipelineError(
            "build log does not prove the exact commit-derived GIT_VERSION "
            "GNU Make origin and target compile token"
        )
    log_contract = core_log_contract_for(core_id)
    if log_contract is not None and not registered_core_log_contract_proves(
        build_log_text,
        core_id,
        arch,
        spec["source"]["commit"],
        spec["source"]["tree"],
    ):
        raise PipelineError(log_contract.failure_message)
    if expected_metadata_replacement is not None and not (
        metadata_replacement_log_proves_contract(
            build_log_text, expected_metadata_replacement
        )
    ):
        raise PipelineError(
            "build log does not prove the exact metadata replacement contract"
        )
    if is_direct_cmake and not direct_cmake_log_proves_contract(
        build_log_text, spec, arch
    ):
        raise PipelineError(
            "build log does not prove the exact direct-CMake and overlay contract"
        )
    return artifact_path, metadata_path, build_log


def validate_e2e_evidence(
    e2e_path: Path,
    selected_record_path: Path,
    catalog_path: Path,
    catalog: dict,
) -> tuple[dict, str, dict[str, tuple[dict, Path, str]], Path, dict]:
    e2e_path = require_contained(e2e_path, ROOT / ".local-e2e", "E2E record")
    selected_record_path = require_contained(
        selected_record_path, ROOT / ".local-e2e", "build record"
    )
    if e2e_path.name != "e2e-record.json":
        raise PipelineError("E2E evidence must be an e2e-record.json file")
    run_root = e2e_path.parent
    require_contained(selected_record_path, run_root, "selected build record")
    try:
        evidence_bytes = e2e_path.read_bytes()
        evidence = json.loads(evidence_bytes)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PipelineError(f"cannot load E2E JSON from {e2e_path}: {exc}") from exc
    if not isinstance(evidence, dict):
        raise PipelineError("E2E record must be a JSON object")
    evidence_file_sha256 = sha256_bytes(evidence_bytes)
    selected = load_json(selected_record_path)
    core_id = selected.get("core_id")
    arch = selected.get("architecture")
    if core_id not in catalog["cores"]:
        raise PipelineError("selected record core is not in the current catalog")
    matching_builds, matching_packages = active_promotion_e2e_scope(
        evidence, core_id
    )
    if not runner_evidence_is_well_formed(evidence.get("runner")):
        raise PipelineError("E2E runner evidence is missing or invalid")
    if (
        evidence.get("result") != "passed"
        or not evidence.get("local_only")
        or evidence.get("publication") != "disabled"
    ):
        raise PipelineError("E2E record is not a passed local-only run")
    if evidence.get("content_sha256") != e2e_content_sha256(evidence):
        raise PipelineError("E2E record content digest is invalid")

    spec = catalog["cores"][core_id]
    if (
        len(matching_builds) != len(spec["targets"])
        or {item.get("architecture") for item in matching_builds} != set(spec["targets"])
        or any(item.get("result") != "passed" for item in matching_builds)
    ):
        raise PipelineError("E2E record does not contain a complete passing target set")

    bound_records: dict[str, tuple[dict, Path, str]] = {}
    for item in matching_builds:
        record_path = safe_child(ROOT, item.get("record", ""), "E2E build record path")
        require_contained(record_path, run_root, "E2E build record")
        if not record_path.is_file() or sha256_file(record_path) != item.get("record_sha256"):
            raise PipelineError("E2E build record digest is missing or invalid")
        record = load_json(record_path)
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != item.get("architecture")
        ):
            raise PipelineError("E2E build entry does not match its build record")
        validate_build_record_identity(record, record_path, catalog_path, catalog)
        bound_records[record["architecture"]] = (
            record,
            record_path,
            item["record_sha256"],
        )
    if len({item[0]["metadata"]["sha256"] for item in bound_records.values()}) != 1:
        raise PipelineError("E2E target metadata digests are inconsistent")
    if bound_records.get(arch, ({}, Path()))[1].resolve() != selected_record_path:
        raise PipelineError("selected build record is not bound to this E2E run")

    if len(matching_packages) != 1 or matching_packages[0].get("result") != "packaged":
        raise PipelineError("E2E record lacks one passing package for the selected core")
    package_record = matching_packages[0]
    package_path = safe_child(run_root, package_record.get("path", ""), "E2E package path")
    if (
        package_path.name != f"{core_id}_libretro.zip"
        or not package_path.is_file()
        or sha256_file(package_path) != package_record.get("sha256")
        or package_path.stat().st_size != package_record.get("size")
    ):
        raise PipelineError("E2E package is missing or does not match its record")

    try:
        with zipfile.ZipFile(package_path) as archive:
            expected_members = {
                f"{ARCH_LAYOUT[target]['package_directory']}/{spec['build']['artifact_name']}"
                for target in spec["targets"]
            }
            expected_members.update({spec["metadata"]["artifact_name"], "manifest.json"})
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise PipelineError("E2E package contains duplicate members")
            if set(archive.namelist()) != expected_members:
                raise PipelineError("E2E package members do not match the catalog")
            manifest = json.loads(archive.read("manifest.json"))
            if (
                manifest.get("core_id") != core_id
                or not manifest.get("local_only")
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != set(spec["targets"])
            ):
                raise PipelineError("E2E package manifest identity is invalid")
            for target, (record, _, _) in bound_records.items():
                member = (
                    f"{ARCH_LAYOUT[target]['package_directory']}/"
                    f"{spec['build']['artifact_name']}"
                )
                package_artifact = manifest["artifacts"][target]
                if (
                    package_artifact.get("path") != member
                    or package_artifact.get("sha256") != record["artifact"]["sha256"]
                    or package_artifact.get("source_commit")
                    != record["source"]["resolved_commit"]
                    or package_artifact.get("toolchain_image_id")
                    != record["toolchain"]["resolved_image_id"]
                    or sha256_bytes(archive.read(member)) != record["artifact"]["sha256"]
                ):
                    raise PipelineError("E2E packaged artifact identity is invalid")
            metadata_manifest = manifest.get("metadata", {})
            metadata_name = spec["metadata"]["artifact_name"]
            expected_metadata_sha = bound_records[spec["targets"][0]][0]["metadata"][
                "sha256"
            ]
            if (
                metadata_manifest.get("path") != metadata_name
                or metadata_manifest.get("sha256") != expected_metadata_sha
                or sha256_bytes(archive.read(metadata_name)) != expected_metadata_sha
            ):
                raise PipelineError("E2E packaged metadata identity is invalid")
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise PipelineError(f"cannot validate E2E package: {exc}") from exc
    return evidence, evidence_file_sha256, bound_records, package_path, package_record


def _validate_golden_document_impl(
    document: dict, spruceos: Path | None = None
) -> dict:
    if not isinstance(document, dict):
        return {
            "status": "invalid",
            "errors": ["golden document must be an object"],
            "core_count": 0,
            "valid_imported_artifacts": 0,
            "invalid_imported_artifacts": [],
            "build_golden_count": 0,
        }

    errors: list[str] = []
    workflows = core_workflows()
    baseline = document.get("baseline")
    cores = document.get("cores")
    summary = document.get("summary")
    structural_errors = []
    if not isinstance(baseline, dict):
        structural_errors.append("baseline must be an object")
    if not isinstance(cores, dict):
        structural_errors.append("cores must be an object")
    elif any(
        not isinstance(core_id, str)
        or not isinstance(record, dict)
        or not isinstance(record.get("artifacts"), dict)
        or any(
            not isinstance(artifact, dict)
            for artifact in record.get("artifacts", {}).values()
        )
        for core_id, record in cores.items()
    ):
        structural_errors.append("core records and artifacts must be objects")
    if not isinstance(summary, dict):
        structural_errors.append("summary must be an object")
    if structural_errors:
        return {
            "status": "invalid",
            "errors": structural_errors,
            "core_count": len(cores) if isinstance(cores, dict) else 0,
            "valid_imported_artifacts": 0,
            "invalid_imported_artifacts": [],
            "build_golden_count": 0,
        }

    schema_version = document.get("schema_version")
    scoped_workflows = workflows
    if type(schema_version) is not int or schema_version not in {1, 2}:
        errors.append("schema_version must be the exact integer 1 or 2")
    elif schema_version == 1:
        if set(cores) != set(workflows):
            errors.append("golden core roster does not exactly match core workflows")
    else:
        errors.extend(core_golden_v2_shape_errors(document))
        core_id = document.get("core_id")
        if (
            not isinstance(core_id, str)
            or CORE_ID_RE.fullmatch(core_id) is None
            or core_id not in workflows
        ):
            errors.append("schema-v2 core golden core_id is invalid")
            scoped_workflows = {}
        else:
            scoped_workflows = {core_id: workflows[core_id]}
    if document.get("publication") != "disabled":
        errors.append("publication must be disabled")
    baseline_commit = baseline.get("repository_commit")
    if not isinstance(baseline_commit, str) or not SHA1_RE.fullmatch(baseline_commit):
        errors.append("baseline.repository_commit is not a full SHA")
    if document.get("content_sha256") != golden_content_sha256(document):
        errors.append("content_sha256 does not cover the current baseline and build goldens")
    valid_artifacts = 0
    invalid_artifacts: list[str] = []
    for core_id, path in scoped_workflows.items():
        record = cores.get(core_id, {})
        if record.get("workflow") != str(path.relative_to(ROOT)):
            errors.append(f"{core_id}: workflow path mismatch")
        artifacts = record.get("artifacts", {})
        core_valid = False
        for arch in ARCH_LAYOUT:
            artifact = artifacts.get(arch, {})
            status = artifact.get("status")
            if status == "valid":
                core_valid = True
                valid_artifacts += 1
                if not SHA256_RE.fullmatch(artifact.get("sha256", "")):
                    errors.append(f"{core_id}/{arch}: invalid SHA256")
                if spruceos is not None:
                    try:
                        source_path = safe_child(
                            spruceos, artifact.get("path", ""), f"{core_id}/{arch} source path"
                        )
                        current = validate_artifact(source_path, arch)
                        if current.get("status") != "valid":
                            errors.append(f"{core_id}/{arch}: source artifact is no longer valid")
                        elif current.get("sha256") != artifact.get("sha256"):
                            errors.append(f"{core_id}/{arch}: source artifact digest drift")
                    except PipelineError as exc:
                        errors.append(str(exc))
            elif status != "not_shipped":
                if status == "invalid":
                    invalid_artifacts.append(f"{core_id}/{arch}")
                    if not artifact.get("errors"):
                        errors.append(f"{core_id}/{arch}: invalid artifact lacks evidence")
                    if not SHA256_RE.fullmatch(artifact.get("sha256", "")):
                        errors.append(f"{core_id}/{arch}: invalid artifact SHA256 is invalid")
                    if spruceos is not None:
                        try:
                            source_path = safe_child(
                                spruceos,
                                artifact.get("path", ""),
                                f"{core_id}/{arch} rejected source path",
                            )
                            current = validate_artifact(source_path, arch)
                            if current.get("status") != "invalid":
                                errors.append(
                                    f"{core_id}/{arch}: rejected source artifact status drift"
                                )
                            elif current.get("sha256") != artifact.get("sha256"):
                                errors.append(
                                    f"{core_id}/{arch}: rejected source artifact digest drift"
                                )
                        except PipelineError as exc:
                            errors.append(str(exc))
                else:
                    errors.append(f"{core_id}/{arch}: unexpected status {status!r}")
        if not core_valid:
            errors.append(f"{core_id}: no valid imported artifact")
    build_goldens = document.get("build_goldens", {})
    if not isinstance(build_goldens, dict):
        errors.append("build_goldens must be an object")
        build_goldens = {}
    for core_id, targets in build_goldens.items():
        if core_id not in workflows:
            errors.append(f"build golden references unknown core {core_id}")
            continue
        if not isinstance(targets, dict):
            errors.append(f"{core_id}: build-golden targets must be an object")
            continue
        for arch, golden in targets.items():
            if not isinstance(golden, dict):
                errors.append(f"{core_id}/{arch}: build golden must be an object")
                continue
            if arch not in ARCH_LAYOUT:
                errors.append(f"{core_id}: build golden has unknown target {arch}")
            if golden.get("promotion_state") != "build_golden":
                errors.append(f"{core_id}/{arch}: invalid promotion state")
            if golden.get("core_id") != core_id or golden.get("architecture") != arch:
                errors.append(f"{core_id}/{arch}: promoted identity mismatch")
            if golden.get("validation_scope") != "static-build-only":
                errors.append(f"{core_id}/{arch}: invalid validation scope")
            artifact = golden.get("artifact")
            if not isinstance(artifact, dict):
                errors.append(f"{core_id}/{arch}: promoted artifact must be an object")
                artifact = {}
            if artifact.get("status") != "valid":
                errors.append(f"{core_id}/{arch}: promoted artifact is not valid")
            if not isinstance(artifact.get("sha256"), str) or not SHA256_RE.fullmatch(
                artifact["sha256"]
            ):
                errors.append(f"{core_id}/{arch}: promoted artifact SHA256 is invalid")
            source = golden.get("source")
            if not isinstance(source, dict):
                errors.append(f"{core_id}/{arch}: promoted source must be an object")
                source = {}
            if not isinstance(source.get("resolved_commit"), str) or not SHA1_RE.fullmatch(
                source["resolved_commit"]
            ):
                errors.append(f"{core_id}/{arch}: promoted source commit is invalid")
            if (
                core_id == VEMULATOR_CORE_ID
                and not vemulator_golden_source_is_well_formed(core_id, source)
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == FREEINTV_CORE_ID
                and not freeintv_golden_source_is_well_formed(core_id, source)
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == PICODRIVE_CORE_ID
                and not picodrive_golden_source_is_well_formed(core_id, source)
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == MAME2003_PLUS_CORE_ID
                and not mame2003_plus_golden_source_is_well_formed(
                    core_id, source
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            if (
                core_id == FBNEO_CORE_ID
                and not fbneo_golden_source_is_well_formed(core_id, source)
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted source contract is invalid"
                )
            golden_toolchain = golden.get("toolchain", {})
            if not isinstance(golden_toolchain, dict):
                errors.append(f"{core_id}/{arch}: promoted toolchain is not an object")
                archive_provenance = None
            else:
                archive_provenance = golden_toolchain.get("archive_provenance")
            if archive_provenance is not None:
                # The provenance names the LOCK ENTRY the build ran inside:
                # the target architecture for the C drivers, "rust" for a
                # direct-cargo golden.
                golden_build = golden.get("build")
                expected_lock_entry = (
                    "rust"
                    if isinstance(golden_build, dict)
                    and golden_build.get("driver") == "direct-cargo"
                    else arch
                )
                if not isinstance(archive_provenance, dict):
                    errors.append(f"{core_id}/{arch}: archive provenance is invalid")
                    lock_reference = {}
                    validator_reference = {}
                    archive = {}
                else:
                    lock_reference = archive_provenance.get("lock", {})
                    validator_reference = archive_provenance.get("validator", {})
                    archive = archive_provenance.get("archive", {})
                if not all(
                    isinstance(value, dict)
                    for value in (lock_reference, validator_reference, archive)
                ) or (
                    golden.get("provenance_version") != 2
                    or set(archive_provenance)
                    != {"lock", "validator", "architecture", "archive"}
                    or archive_provenance.get("architecture") != expected_lock_entry
                    or set(lock_reference)
                    != {
                        "path",
                        "schema_version",
                        "lock_id",
                        "file_sha256",
                        "content_sha256",
                    }
                    or lock_reference.get("path")
                    != "pins/toolchains/local-cache-v1.json"
                    or type(lock_reference.get("schema_version")) is not int
                    or lock_reference.get("schema_version") != 1
                    or lock_reference.get("lock_id") != "local-cache-v1"
                    or not isinstance(lock_reference.get("file_sha256"), str)
                    or not SHA256_RE.fullmatch(lock_reference["file_sha256"])
                    or not isinstance(lock_reference.get("content_sha256"), str)
                    or not SHA256_RE.fullmatch(lock_reference["content_sha256"])
                    or set(validator_reference) != {"path", "sha256"}
                    or validator_reference.get("path")
                    != "scripts/toolchain_archive.py"
                    or not isinstance(validator_reference.get("sha256"), str)
                    or not SHA256_RE.fullmatch(validator_reference["sha256"])
                    or set(archive) != {"filename", "sha256", "size"}
                    or archive.get("filename") != f"cores-{expected_lock_entry}.tar.gz"
                    or not isinstance(archive.get("sha256"), str)
                    or not SHA256_RE.fullmatch(archive["sha256"])
                    or type(archive.get("size")) is not int
                    or archive.get("size", 0) <= 0
                ):
                    errors.append(f"{core_id}/{arch}: archive provenance is invalid")
            elif golden.get("provenance_version") is not None:
                errors.append(f"{core_id}/{arch}: legacy provenance marker is invalid")
            metadata = golden.get("metadata")
            if not isinstance(metadata, dict):
                errors.append(f"{core_id}/{arch}: promoted metadata must be an object")
                metadata = {}
            if (
                metadata.get("status") != "valid"
                or not isinstance(metadata.get("sha256"), str)
                or not SHA256_RE.fullmatch(metadata["sha256"])
            ):
                errors.append(f"{core_id}/{arch}: promoted metadata is invalid")
            promoted_build = golden.get("build")
            build_is_required = core_id in (
                EXACT_GIT_VERSION_CORE_IDS
                | EXACT_SOURCE_NATIVE_CORE_IDS
                | {"vecx", CORE_81_ID, PICODRIVE_CORE_ID}
            )
            if (
                isinstance(promoted_build, dict)
                and "metadata_replacement" in promoted_build
                and not metadata_matches_replacement(
                    metadata, promoted_build["metadata_replacement"]
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: promoted metadata does not match its replacement"
                )
            if build_is_required and not isinstance(promoted_build, dict):
                errors.append(f"{core_id}/{arch}: promoted build contract is missing")
            elif "build" in golden:
                is_git_version_build = isinstance(promoted_build, dict) and (
                    "git_version" in promoted_build
                )
                is_make_variable_build = isinstance(promoted_build, dict) and (
                    "make_variables" in promoted_build
                )
                is_generated_source_build = isinstance(
                    promoted_build, dict
                ) and ("generated_source" in promoted_build)
                is_recipe_profile_build = isinstance(
                    promoted_build, dict
                ) and ("recipe_profile" in promoted_build)
                is_direct_cmake_build = isinstance(promoted_build, dict) and (
                    promoted_build.get("driver") == "direct-cmake"
                    or "cmake" in promoted_build
                    or "overlays" in promoted_build
                )
                is_direct_cargo_build = isinstance(promoted_build, dict) and (
                    promoted_build.get("driver") == "direct-cargo"
                    or "cargo" in promoted_build
                )
                if core_id == CORE_81_ID:
                    if not core_81_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id == PICODRIVE_CORE_ID:
                    if not picodrive_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                        arch,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif is_recipe_profile_build:
                    errors.append(
                        f"{core_id}/{arch}: recipe-profile build contract "
                        "belongs only to picodrive"
                    )
                elif is_generated_source_build:
                    errors.append(
                        f"{core_id}/{arch}: generated-source build contract "
                        "belongs only to 81"
                    )
                elif core_id == "vecx":
                    if not vecx_combined_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id == VEMULATOR_CORE_ID:
                    if not vemulator_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id == FREEINTV_CORE_ID:
                    if not freeintv_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id in EXACT_NATIVE_GIT_VERSION_CORE_IDS:
                    if not exact_native_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                        arch,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif core_id in EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS:
                    if not git_version_golden_build_contract_is_well_formed(
                        promoted_build,
                        source.get("resolved_commit"),
                        core_id,
                        source,
                        arch,
                    ):
                        errors.append(
                            f"{core_id}/{arch}: promoted build contract is invalid"
                        )
                elif is_git_version_build and not git_version_golden_build_contract_is_well_formed(
                    promoted_build,
                    source.get("resolved_commit"),
                    core_id,
                    source,
                    arch,
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_make_variable_build and not make_variable_golden_build_contract_is_well_formed(
                    promoted_build
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_direct_cmake_build and not direct_cmake_golden_build_contract_is_well_formed(
                    promoted_build, core_id, arch
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_direct_cmake_build and artifact.get("path") != (
                    f"{promoted_build.get('cmake', {}).get('target')}.so"
                ) and artifact.get("path") != f"{core_id}_libretro.so":
                    errors.append(f"{core_id}/{arch}: promoted build artifact path is invalid")
                elif is_direct_cargo_build and not direct_cargo_golden_build_contract_is_well_formed(
                    promoted_build, core_id, arch
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
                elif is_direct_cargo_build and artifact.get("path") != f"{core_id}_libretro.so":
                    errors.append(f"{core_id}/{arch}: promoted build artifact path is invalid")
                elif (
                    not is_git_version_build
                    and not is_make_variable_build
                    and not is_direct_cmake_build
                    and not is_direct_cargo_build
                    and (
                        not isinstance(promoted_build, dict)
                        or promoted_build.get("environment") != "sanitized-v1"
                        or not compile_definition_list_is_well_formed(
                            promoted_build.get("compile_definitions")
                        )
                        or (
                            "source_date_epoch" in promoted_build
                            and not source_date_epoch_is_well_formed(
                                promoted_build["source_date_epoch"]
                            )
                        )
                    )
                ):
                    errors.append(f"{core_id}/{arch}: promoted build contract is invalid")
            e2e = golden.get("e2e")
            if not isinstance(e2e, dict):
                errors.append(f"{core_id}/{arch}: E2E record must be an object")
                e2e = {}
            for digest_name in ("record_sha256", "content_sha256", "package_sha256"):
                if not isinstance(e2e.get(digest_name), str) or not SHA256_RE.fullmatch(
                    e2e[digest_name]
                ):
                    errors.append(f"{core_id}/{arch}: E2E {digest_name} is invalid")
            for path_name in ("record", "package"):
                try:
                    evidence_path = safe_child(
                        ROOT,
                        e2e.get(path_name, ""),
                        f"{core_id}/{arch} E2E {path_name} path",
                    )
                    evidence_path.relative_to((ROOT / ".local-e2e").resolve())
                except (PipelineError, ValueError):
                    errors.append(
                        f"{core_id}/{arch}: E2E {path_name} path is outside local output"
                    )
            local_store = golden.get("local_store")
            if not isinstance(local_store, dict):
                errors.append(f"{core_id}/{arch}: local store record must be an object")
                local_store = {}
            if local_store.get("availability") != "local-only":
                errors.append(f"{core_id}/{arch}: build golden lacks local store metadata")
            for stored_name in STORE_SINGLE_EVIDENCE_NAMES:
                stored = local_store.get(stored_name)
                if not isinstance(stored, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} record must be an object"
                    )
                    stored = {}
                if not isinstance(stored.get("sha256"), str) or not SHA256_RE.fullmatch(
                    stored["sha256"]
                ):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} SHA256 is invalid"
                    )
                try:
                    stored_path = safe_child(
                        ROOT,
                        stored.get("path", ""),
                        f"{core_id}/{arch} local {stored_name} path",
                    )
                    stored_path.relative_to(DEFAULT_STORE.resolve())
                except (PipelineError, ValueError):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} path is outside the local store"
                    )
            build_record_digests = e2e.get("build_records")
            if not isinstance(build_record_digests, dict):
                errors.append(f"{core_id}/{arch}: E2E build records must be an object")
                build_record_digests = {}
            if (
                not build_record_digests
                or arch not in build_record_digests
                or any(target not in ARCH_LAYOUT for target in build_record_digests)
            ):
                errors.append(f"{core_id}/{arch}: E2E build-record target set is invalid")
            for group_name in STORE_TARGET_EVIDENCE_NAMES:
                group = local_store.get(group_name)
                if not isinstance(group, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {group_name} must be an object"
                    )
                    group = {}
                if set(group) != set(build_record_digests):
                    errors.append(
                        f"{core_id}/{arch}: local {group_name} target set is incomplete"
                    )
                for target, stored in group.items():
                    if not isinstance(stored, dict):
                        errors.append(
                            f"{core_id}/{arch}: local {group_name}/{target} must be an object"
                        )
                        continue
                    if (
                        target not in ARCH_LAYOUT
                        or not isinstance(stored.get("sha256"), str)
                        or not SHA256_RE.fullmatch(stored["sha256"])
                    ):
                        errors.append(
                            f"{core_id}/{arch}: local {group_name}/{target} identity is invalid"
                        )
                    try:
                        stored_path = safe_child(
                            ROOT,
                            stored.get("path", ""),
                            f"{core_id}/{arch} local {group_name}/{target} path",
                        )
                        stored_path.relative_to(DEFAULT_STORE.resolve())
                    except (PipelineError, ValueError):
                        errors.append(
                            f"{core_id}/{arch}: local {group_name}/{target} path is outside the local store"
                        )
            for target, expected_digest in build_record_digests.items():
                if (
                    local_store.get("build_records", {}).get(target, {}).get("sha256")
                    != expected_digest
                ):
                    errors.append(
                        f"{core_id}/{arch}: stored {target} build record is not bound to E2E"
                    )
            linked_digests = {
                "artifact": artifact.get("sha256"),
                "metadata": metadata.get("sha256"),
                "e2e_record": e2e.get("record_sha256"),
                "package": e2e.get("package_sha256"),
            }
            for stored_name, expected_digest in linked_digests.items():
                if local_store.get(stored_name, {}).get("sha256") != expected_digest:
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} digest is not bound to its record"
                    )
    cores_without_valid = sorted(
        core_id
        for core_id, record in cores.items()
        if not any(
            artifact.get("status") == "valid"
            for artifact in record.get("artifacts", {}).values()
        )
    )
    expected_summary = {
        "core_count": len(cores),
        "valid_artifact_count": valid_artifacts,
        "invalid_artifacts": sorted(invalid_artifacts),
        "cores_without_valid_artifacts": cores_without_valid,
    }
    for key, expected in expected_summary.items():
        actual = summary.get(key)
        matches = (
            sorted(actual) == expected
            if isinstance(expected, list) and isinstance(actual, list)
            else actual == expected
        )
        if not matches:
            errors.append(f"summary.{key} does not match manifest contents")
    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "core_count": len(cores),
        "valid_imported_artifacts": valid_artifacts,
        "invalid_imported_artifacts": invalid_artifacts,
        "build_golden_count": sum(len(targets) for targets in build_goldens.values()),
    }


def validate_golden_document(document: dict, spruceos: Path | None = None) -> dict:
    """Validate untrusted golden JSON without exposing shape exceptions."""

    try:
        return _validate_golden_document_impl(document, spruceos)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {
            "status": "invalid",
            "errors": [
                "golden document contains malformed nested data "
                f"({type(exc).__name__})"
            ],
            "core_count": 0,
            "valid_imported_artifacts": 0,
            "invalid_imported_artifacts": [],
            "build_golden_count": 0,
        }


def verify_recipe_snapshot(path: Path, record: dict, label: str) -> list[str]:
    errors: list[str] = []
    try:
        snapshot = load_json(path)
    except PipelineError as exc:
        return [str(exc)]
    recipe = record.get("recipe", {})
    pipeline_bundle = recipe.get("pipeline_bundle") if isinstance(recipe, dict) else None
    has_pipeline_bundle = pipeline_source_bundle_is_well_formed(pipeline_bundle)
    commit_blacklist = (
        recipe.get("commit_blacklist") if isinstance(recipe, dict) else None
    )
    has_commit_blacklist = commit_blacklist_reference_is_well_formed(
        commit_blacklist
    )
    if isinstance(recipe, dict) and "pipeline_bundle" in recipe:
        if not has_pipeline_bundle:
            errors.append(f"{label}: recipe pipeline bundle is invalid")
        elif (
            pipeline_bundle["files"].get(str(Path(__file__).relative_to(ROOT)))
            != recipe.get("pipeline_sha256")
        ):
            errors.append(f"{label}: recipe launcher digest is inconsistent")
    if isinstance(recipe, dict) and "commit_blacklist" in recipe:
        if not has_commit_blacklist:
            errors.append(f"{label}: recipe commit blacklist reference is invalid")
    if (
        snapshot.get("core_id") != record.get("core_id")
        or snapshot.get("architecture") != record.get("architecture")
        or snapshot.get("source") != record.get("source")
        or snapshot.get("recipe") != record.get("recipe")
    ):
        errors.append(f"{label}: recipe snapshot identity mismatch")
    snapshot_toolchain = snapshot.get("toolchain", {})
    record_toolchain = record.get("toolchain", {})
    if not isinstance(record_toolchain, dict):
        return [f"{label}: build record toolchain is not an object"]
    archive_provenance = record_toolchain.get("archive_provenance")
    if archive_provenance is not None and not isinstance(archive_provenance, dict):
        return [f"{label}: build record archive provenance is not an object"]
    if archive_provenance is not None and (
        not isinstance(archive_provenance.get("lock"), dict)
        or not isinstance(archive_provenance.get("validator"), dict)
        or not isinstance(archive_provenance.get("archive"), dict)
    ):
        return [f"{label}: build record archive provenance shape is invalid"]
    record_build = record.get("build", {})
    has_compile_definition_contract = (
        isinstance(record_build, dict) and "compile_definitions" in record_build
    )
    has_make_variable_contract = (
        isinstance(record_build, dict) and "make_variables" in record_build
    )
    has_git_version_contract = (
        isinstance(record_build, dict) and "git_version" in record_build
    )
    has_generated_source_contract = (
        isinstance(record_build, dict) and "generated_source" in record_build
    )
    has_recipe_profile_contract = (
        isinstance(record_build, dict) and "recipe_profile" in record_build
    )
    has_source_date_epoch_contract = (
        isinstance(record_build, dict) and "source_date_epoch" in record_build
    )
    has_direct_cmake_contract = (
        isinstance(record_build, dict)
        and (
            record_build.get("driver") == "direct-cmake"
            or "cmake" in record_build
            or "overlays" in record_build
        )
    )
    snapshot_version = snapshot.get("schema_version")
    requires_v9_provenance = (
        snapshot_version in {9, 10} or has_pipeline_bundle
    )
    if requires_v9_provenance and not has_pipeline_bundle:
        errors.append(f"{label}: schema-v9 recipe requires a valid pipeline bundle")
    if requires_v9_provenance and not has_commit_blacklist:
        errors.append(
            f"{label}: schema-v9 recipe requires a valid commit blacklist binding"
        )
    is_combined_git_make_contract = bool(
        record.get("core_id") in COMBINED_NATIVE_MAKE_CORE_IDS
        and has_git_version_contract
        and has_make_variable_contract
    )
    if (
        record.get("core_id") == VEMULATOR_CORE_ID
        and not vemulator_golden_build_contract_is_well_formed(
            record_build,
            record.get("source", {}).get("resolved_commit"),
            record.get("core_id"),
            record.get("source"),
        )
    ):
        errors.append(
            f"{label}: source-native recipe snapshot lacks its normalized contract"
        )
    if (
        record.get("core_id") == FREEINTV_CORE_ID
        and not freeintv_golden_build_contract_is_well_formed(
            record_build,
            record.get("source", {}).get("resolved_commit"),
            record.get("core_id"),
            record.get("source"),
        )
    ):
        errors.append(
            f"{label}: source-native recipe snapshot lacks its normalized contract"
        )
    if has_recipe_profile_contract and (
        record.get("core_id") != PICODRIVE_CORE_ID
        or has_git_version_contract
        or has_make_variable_contract
        or has_generated_source_contract
        or has_direct_cmake_contract
        or not picodrive_golden_source_is_well_formed(
            record.get("core_id"), record.get("source")
        )
        or not picodrive_golden_build_contract_is_well_formed(
            record_build,
            record.get("source", {}).get("resolved_commit"),
            record.get("core_id"),
            record.get("source"),
            record.get("architecture"),
        )
    ):
        errors.append(
            f"{label}: recipe-profile snapshot lacks its normalized contract"
        )
    if has_generated_source_contract:
        expected_snapshot_versions = {10}
        if (
            record.get("core_id") != CORE_81_ID
            or not has_compile_definition_contract
            or has_git_version_contract
            or has_make_variable_contract
            or has_source_date_epoch_contract
            or not core_81_golden_build_contract_is_well_formed(
                record_build,
                record.get("source", {}).get("resolved_commit"),
                record.get("core_id"),
                record.get("source"),
            )
        ):
            errors.append(
                f"{label}: generated-source recipe snapshot lacks its "
                "normalized contract"
            )
    elif has_git_version_contract and has_make_variable_contract:
        expected_snapshot_versions = {8}
        if (
            not is_combined_git_make_contract
            or not has_compile_definition_contract
            or has_source_date_epoch_contract
            or not combined_git_version_make_golden_build_contract_is_well_formed(
                record_build,
                record.get("source", {}).get("resolved_commit"),
                record.get("core_id"),
                record.get("source"),
            )
        ):
            errors.append(
                f"{label}: combined native recipe snapshot lacks its normalized contract"
            )
    elif has_git_version_contract:
        expected_snapshot_versions = {7}
        if (
            not has_compile_definition_contract
            or not git_version_golden_build_contract_is_well_formed(
                record_build,
                record.get("source", {}).get("resolved_commit"),
                record.get("core_id"),
                record.get("source"),
                record.get("architecture"),
            )
        ):
            errors.append(
                f"{label}: git-version recipe snapshot lacks its normalized contract"
            )
    elif has_make_variable_contract:
        expected_snapshot_versions = {6}
        make_profile = make_variable_profile(record_build.get("make_variables"))
        snapshot_facts = _make_variable_profile_facts().get(make_profile or "")
        # golden_epoch again: profiles whose record forbids a source_date_epoch
        # carry the same snapshot minus that one contract; profiles validated
        # by the combined native+make validators never reach this branch.
        if snapshot_facts is None or snapshot_facts.golden_epoch is None:
            normalized = False
        elif snapshot_facts.golden_epoch:
            normalized = (
                has_compile_definition_contract
                and has_source_date_epoch_contract
            )
        else:
            normalized = (
                has_compile_definition_contract
                and not has_source_date_epoch_contract
            )
        if not normalized:
            errors.append(
                f"{label}: make-variable recipe snapshot lacks its normalized contract"
            )
    elif has_direct_cmake_contract:
        expected_snapshot_versions = {5}
        if not has_compile_definition_contract or not has_source_date_epoch_contract:
            errors.append(
                f"{label}: direct-CMake recipe snapshot lacks its normalized contract"
            )
    elif has_source_date_epoch_contract:
        expected_snapshot_versions = {4}
        if not has_compile_definition_contract:
            errors.append(
                f"{label}: timestamped recipe snapshot lacks compile definitions"
            )
    elif has_compile_definition_contract:
        expected_snapshot_versions = {2, 3} if archive_provenance is not None else {3}
    else:
        expected_snapshot_versions = {2 if archive_provenance is not None else 1}
    if has_pipeline_bundle and not has_generated_source_contract:
        expected_snapshot_versions = {9}
    if (
        type(snapshot_version) is not int
        or snapshot_version not in expected_snapshot_versions
    ):
        errors.append(f"{label}: recipe snapshot schema version mismatch")
    expected_toolchain = {
        "image_id": record_toolchain.get("resolved_image_id"),
        "dockerfile": record_toolchain.get("dockerfile"),
        "dockerfile_sha256": record_toolchain.get("dockerfile_sha256"),
        "resolver_digests": record_toolchain.get("resolver_digests"),
    }
    if archive_provenance is not None:
        expected_toolchain["archive_provenance"] = archive_provenance
    if snapshot_toolchain != expected_toolchain:
        errors.append(f"{label}: recipe snapshot toolchain mismatch")
    if (
        has_direct_cmake_contract
        or has_compile_definition_contract
        or has_make_variable_contract
        or has_git_version_contract
        or has_generated_source_contract
        or has_recipe_profile_contract
        or has_source_date_epoch_contract
    ) and snapshot_version in {3, 4, 5, 6, 7, 8, 9, 10}:
        expected_build = recorded_build_contract(record_build)
        if snapshot.get("build") != expected_build:
            errors.append(f"{label}: recipe snapshot build contract mismatch")
    elif "build" in snapshot:
        errors.append(f"{label}: legacy recipe snapshot has a build contract")
    expected_files = {
        recipe.get("catalog_path"),
        recipe.get("workflow"),
        str(Path(__file__).relative_to(ROOT)),
        record_toolchain.get("dockerfile"),
    }
    if has_pipeline_bundle:
        expected_files.update(pipeline_bundle["files"])
    if has_commit_blacklist:
        expected_files.add(commit_blacklist["path"])
    if archive_provenance is not None:
        expected_files.add(archive_provenance.get("lock", {}).get("path"))
        expected_files.add(archive_provenance.get("validator", {}).get("path"))
    if has_direct_cmake_contract and isinstance(record_build.get("overlays"), list):
        expected_files.update(
            overlay.get("patch_path")
            for overlay in record_build["overlays"]
            if isinstance(overlay, dict)
        )
    metadata_replacement = record_build.get("metadata_replacement")
    if metadata_replacement is not None:
        if metadata_replacement_contract_is_well_formed(metadata_replacement):
            expected_files.add(metadata_replacement["path"])
            if not metadata_matches_replacement(
                record.get("metadata"), metadata_replacement
            ):
                errors.append(
                    f"{label}: metadata does not match the recipe replacement"
                )
        else:
            errors.append(f"{label}: metadata replacement contract is invalid")
    files = snapshot.get("files", {})
    if set(files) != expected_files:
        errors.append(f"{label}: recipe snapshot file set mismatch")
        return errors
    for relative, stored in files.items():
        text = stored.get("text")
        if not isinstance(text, str) or sha256_bytes(text.encode()) != stored.get("sha256"):
            errors.append(f"{label}: recipe snapshot digest mismatch for {relative}")
    expected_hashes = {
        recipe.get("catalog_path"): recipe.get("catalog_sha256"),
        recipe.get("workflow"): recipe.get("workflow_sha256"),
        str(Path(__file__).relative_to(ROOT)): recipe.get("pipeline_sha256"),
        record_toolchain.get("dockerfile"): record_toolchain.get("dockerfile_sha256"),
    }
    if has_pipeline_bundle:
        expected_hashes.update(pipeline_bundle["files"])
    if has_commit_blacklist:
        expected_hashes[commit_blacklist["path"]] = commit_blacklist[
            "file_sha256"
        ]
    if archive_provenance is not None:
        expected_hashes[archive_provenance.get("lock", {}).get("path")] = (
            archive_provenance.get("lock", {}).get("file_sha256")
        )
        expected_hashes[archive_provenance.get("validator", {}).get("path")] = (
            archive_provenance.get("validator", {}).get("sha256")
        )
    if has_direct_cmake_contract and isinstance(record_build.get("overlays"), list):
        for overlay in record_build["overlays"]:
            if isinstance(overlay, dict):
                expected_hashes[overlay.get("patch_path")] = overlay.get(
                    "patch_sha256"
                )
    if metadata_replacement_contract_is_well_formed(metadata_replacement):
        expected_hashes[metadata_replacement["path"]] = metadata_replacement[
            "replacement_sha256"
        ]
    for relative, expected in expected_hashes.items():
        if files.get(relative, {}).get("sha256") != expected:
            errors.append(f"{label}: recipe record digest mismatch for {relative}")
    try:
        catalog_snapshot = json.loads(files[recipe["catalog_path"]]["text"])
        snapshot_spec = catalog_snapshot["cores"][record["core_id"]]
        if (
            record.get("core_id") == VEMULATOR_CORE_ID
            and not vemulator_spec_is_well_formed(snapshot_spec)
        ):
            errors.append(
                f"{label}: VEmulator catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == FREEINTV_CORE_ID
            and has_pipeline_bundle
            and not freeintv_spec_is_well_formed(snapshot_spec)
        ):
            errors.append(
                f"{label}: FreeIntv catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == MGBA_CORE_ID
            and has_pipeline_bundle
            and not mgba_spec_is_well_formed(snapshot_spec)
        ):
            errors.append(f"{label}: mGBA catalog snapshot contract is invalid")
        if (
            record.get("core_id") == PICODRIVE_CORE_ID
            and not picodrive_spec_is_well_formed(snapshot_spec)
        ):
            errors.append(
                f"{label}: Picodrive catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == MAME2003_PLUS_CORE_ID
            and not mame2003_plus_spec_is_well_formed(snapshot_spec)
        ):
            errors.append(
                f"{label}: MAME2003+ catalog snapshot contract is invalid"
            )
        if (
            record.get("core_id") == FBNEO_CORE_ID
            and not fbneo_spec_is_well_formed(snapshot_spec)
        ):
            errors.append(
                f"{label}: FBNeo catalog snapshot contract is invalid"
            )
        if has_commit_blacklist and catalog_snapshot.get(
            "commit_blacklist"
        ) != commit_blacklist:
            errors.append(f"{label}: commit blacklist catalog reference mismatch")
        if core_spec_sha256(snapshot_spec) != recipe.get("core_spec_sha256"):
            errors.append(f"{label}: core specification digest mismatch")
        snapshot_resolver = catalog_snapshot.get("resolver")
        recorded_resolver = record_toolchain.get("resolver_digests")
        snapshot_build = (
            snapshot_spec.get("build") if isinstance(snapshot_spec, dict) else None
        )
        if (
            isinstance(snapshot_build, dict)
            and snapshot_build.get("driver") == "direct-cargo"
        ):
            # A cargo record runs in the Rust image, which carries no
            # libretro-super checkout: the captured resolver identity must be
            # the absent shape (paths mirrored from the snapshot, digests
            # None). A real digest here would mean the wrong image built it.
            expected_absent = {"libretro_super_commit": None}
            if isinstance(snapshot_resolver, dict):
                for prefix in ("core_rules", "fetch_script", "build_script"):
                    expected_absent[f"{prefix}_path"] = snapshot_resolver.get(
                        f"{prefix}_path"
                    )
                    expected_absent[f"{prefix}_sha256"] = None
            if recorded_resolver != expected_absent:
                errors.append(f"{label}: resolver snapshot mismatch")
        elif snapshot_resolver != recorded_resolver:
            errors.append(f"{label}: resolver snapshot mismatch")
        record_source = record.get("source", {})
        snapshot_source = snapshot_spec.get("source", {})
        if not isinstance(record_source, dict) or not isinstance(snapshot_source, dict):
            errors.append(f"{label}: source specification shape mismatch")
        elif any(
            record_source.get(key) != value
            for key, value in snapshot_source.items()
        ):
            errors.append(f"{label}: source does not match the catalog snapshot")
        expected_definitions = compile_definitions_for_target(
            snapshot_spec, record["architecture"]
        )
        expected_source_date_epoch = validated_source_date_epoch(snapshot_spec)
        snapshot_build_spec = snapshot_spec.get("build", {})
        forbidden_needed = forbidden_needed_dependencies(
            snapshot_spec, record.get("artifact", {}).get("needed")
        )
        if forbidden_needed:
            errors.append(
                f"{label}: artifact violates the catalog dependency policy: "
                + ", ".join(forbidden_needed)
            )
        expected_make_variables = validated_make_variables(snapshot_spec)
        expected_git_version = validated_git_version(snapshot_spec)
        expected_generated_source = validated_generated_source(snapshot_spec)
        expected_recipe_profile = validated_recipe_profile(snapshot_spec)
        is_combined_git_make_contract = bool(expected_make_variables) and (
            expected_git_version is not None
            and expected_git_version.get("derivation")
            == NATIVE_GIT_VERSION_DERIVATION
            and record.get("core_id") in COMBINED_NATIVE_MAKE_CORE_IDS
        )
        if (
            snapshot_build_spec.get("driver") == "direct-cmake"
            or expected_make_variables
            or expected_git_version is not None
            or expected_generated_source is not None
            or expected_recipe_profile is not None
            or record.get("core_id") in EXACT_SOURCE_NATIVE_CORE_IDS
        ):
            expected_build_contract = normalized_build_contract(
                snapshot_spec, record["architecture"]
            )
            if (
                not isinstance(record_build, dict)
                or set(record_build)
                != set(expected_build_contract).union({"log", "log_sha256"})
                or recorded_build_contract(record_build) != expected_build_contract
                or (
                    expected_generated_source is not None
                    and not core_81_golden_build_contract_is_well_formed(
                        record_build,
                        snapshot_spec["source"]["commit"],
                        record.get("core_id"),
                        record_source,
                    )
                )
                or (
                    is_combined_git_make_contract
                    and not combined_git_version_make_golden_build_contract_is_well_formed(
                        record_build,
                        snapshot_spec["source"]["commit"],
                        record.get("core_id"),
                        record_source,
                    )
                )
                or (
                    not is_combined_git_make_contract
                    and bool(expected_make_variables)
                    and not make_variable_golden_build_contract_is_well_formed(
                        record_build
                    )
                )
                or (
                    not is_combined_git_make_contract
                    and
                    expected_git_version is not None
                    and not git_version_golden_build_contract_is_well_formed(
                        record_build,
                        snapshot_spec["source"]["commit"],
                        record.get("core_id"),
                        record_source,
                        record.get("architecture"),
                    )
                )
                or (
                    record.get("core_id") == VEMULATOR_CORE_ID
                    and not vemulator_golden_build_contract_is_well_formed(
                        record_build,
                        snapshot_spec["source"]["commit"],
                        record.get("core_id"),
                        record_source,
                    )
                )
                or (
                    record.get("core_id") == FREEINTV_CORE_ID
                    and not freeintv_golden_build_contract_is_well_formed(
                        record_build,
                        snapshot_spec["source"]["commit"],
                        record.get("core_id"),
                        record_source,
                    )
                )
                or (
                    expected_recipe_profile is not None
                    and not picodrive_golden_build_contract_is_well_formed(
                        record_build,
                        snapshot_spec["source"]["commit"],
                        record.get("core_id"),
                        record_source,
                        record.get("architecture"),
                    )
                )
                or record_build.get("log") != "build.log"
                or not isinstance(record_build.get("log_sha256"), str)
                or not SHA256_RE.fullmatch(record_build["log_sha256"])
            ):
                errors.append(f"{label}: build does not match the catalog snapshot")
        elif (
            not isinstance(record_build, dict)
            or record_build.get("driver") != snapshot_build_spec.get("driver")
            or record_build.get("environment") != "sanitized-v1"
            or record_build.get("compile_definitions", []) != expected_definitions
            or not build_source_date_epoch_matches(
                record_build, expected_source_date_epoch
            )
        ):
            errors.append(f"{label}: build does not match the catalog snapshot")
    except (KeyError, TypeError, json.JSONDecodeError, PipelineError) as exc:
        errors.append(f"{label}: cannot parse catalog recipe snapshot: {exc}")
    if has_commit_blacklist:
        try:
            blacklist_snapshot = json.loads(
                files[commit_blacklist["path"]]["text"]
            )
            parsed_blacklist = parse_commit_blacklist(blacklist_snapshot)
            if (
                parsed_blacklist.policy_id != commit_blacklist["policy_id"]
                or parsed_blacklist.content_sha256
                != commit_blacklist["content_sha256"]
            ):
                errors.append(f"{label}: recipe commit blacklist identity mismatch")
        except (
            KeyError,
            TypeError,
            json.JSONDecodeError,
            CommitBlacklistError,
        ) as exc:
            errors.append(f"{label}: cannot parse recipe commit blacklist: {exc}")
    if archive_provenance is not None:
        try:
            lock_reference = archive_provenance["lock"]
            validator_reference = archive_provenance["validator"]
            lock_snapshot = json.loads(files[lock_reference["path"]]["text"])
            architecture = archive_provenance["architecture"]
            locked = lock_snapshot["toolchains"][architecture]
            expected_archive = {
                key: locked["archive"][key] for key in ("filename", "sha256", "size")
            }
            # The provenance names the LOCK ENTRY the build ran inside. For
            # every C driver that is the record's target architecture; a
            # direct-cargo record builds both device targets inside the
            # pinned Rust image, so its entry is "rust".
            record_driver = (record.get("build") or {}).get("driver")
            expected_lock_entry = (
                "rust" if record_driver == "direct-cargo"
                else record.get("architecture")
            )
            if (
                architecture != expected_lock_entry
                or validator_reference.get("path") != "scripts/toolchain_archive.py"
                or not isinstance(validator_reference.get("sha256"), str)
                or not SHA256_RE.fullmatch(validator_reference["sha256"])
                or lock_snapshot.get("schema_version")
                != lock_reference.get("schema_version")
                or lock_snapshot.get("lock_id") != lock_reference.get("lock_id")
                or lock_snapshot.get("content_sha256")
                != lock_reference.get("content_sha256")
                or lock_snapshot.get("content_sha256")
                != toolchain_lock_content_sha256(lock_snapshot)
                or archive_provenance.get("archive") != expected_archive
                or locked.get("image", {}).get("tag")
                != record_toolchain.get("image")
                or locked.get("image", {}).get("id")
                != record_toolchain.get("resolved_image_id")
                or locked.get("dockerfile", {}).get("path")
                != record_toolchain.get("dockerfile")
                or locked.get("dockerfile", {}).get("sha256")
                != record_toolchain.get("dockerfile_sha256")
                or locked.get("dockerfile", {}).get("linkage")
                != record_toolchain.get("dockerfile_linkage")
            ):
                errors.append(f"{label}: recipe snapshot archive provenance mismatch")
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: cannot parse toolchain lock recipe snapshot: {exc}")
    return errors


def verify_historical_recipe_snapshot(
    path: Path,
    record: dict,
    label: str,
) -> list[str]:
    """Validate immutable recipe bytes without today's core policy constants."""

    errors: list[str] = []
    try:
        snapshot = load_json(path)
    except PipelineError as exc:
        return [str(exc)]
    recipe = record.get("recipe")
    source = record.get("source")
    toolchain = record.get("toolchain")
    build = record.get("build")
    if not all(
        isinstance(value, dict)
        for value in (recipe, source, toolchain, build)
    ):
        return [f"{label}: historical recipe record fields are invalid"]
    pipeline_bundle = recipe.get("pipeline_bundle")
    if not pipeline_source_bundle_is_well_formed(pipeline_bundle):
        return [f"{label}: historical recipe pipeline bundle is invalid"]
    historical_generated_source = build.get("generated_source")
    has_historical_generated_source = (
        generated_source_contract_is_well_formed(historical_generated_source)
    )
    if (
        "generated_source" in build
        and not has_historical_generated_source
    ):
        errors.append(
            f"{label}: historical generated-source contract is invalid"
        )
    expected_snapshot_version = (
        10 if has_historical_generated_source else 9
    )
    if (
        snapshot.get("schema_version") != expected_snapshot_version
        or snapshot.get("core_id") != record.get("core_id")
        or snapshot.get("architecture") != record.get("architecture")
        or snapshot.get("source") != source
        or snapshot.get("recipe") != recipe
    ):
        errors.append(f"{label}: historical recipe snapshot identity mismatch")

    archive_provenance = toolchain.get("archive_provenance")
    expected_toolchain = {
        "image_id": toolchain.get("resolved_image_id"),
        "dockerfile": toolchain.get("dockerfile"),
        "dockerfile_sha256": toolchain.get("dockerfile_sha256"),
        "resolver_digests": toolchain.get("resolver_digests"),
    }
    if archive_provenance is not None:
        if not isinstance(archive_provenance, dict):
            errors.append(f"{label}: historical archive provenance is invalid")
        else:
            expected_toolchain["archive_provenance"] = archive_provenance
    if snapshot.get("toolchain") != expected_toolchain:
        errors.append(f"{label}: historical recipe toolchain differs")
    expected_build = {
        key: value
        for key, value in build.items()
        if key not in {"log", "log_sha256"}
    }
    if snapshot.get("build") != expected_build:
        errors.append(f"{label}: historical recipe build contract differs")

    files = snapshot.get("files")
    if not isinstance(files, dict):
        return [*errors, f"{label}: historical recipe files are invalid"]
    expected_hashes = dict(pipeline_bundle["files"])
    direct_hashes = {
        recipe.get("catalog_path"): recipe.get("catalog_sha256"),
        recipe.get("workflow"): recipe.get("workflow_sha256"),
        str(Path(__file__).relative_to(ROOT)): recipe.get("pipeline_sha256"),
        toolchain.get("dockerfile"): toolchain.get("dockerfile_sha256"),
    }
    commit_blacklist = recipe.get("commit_blacklist")
    if isinstance(commit_blacklist, dict):
        direct_hashes[commit_blacklist.get("path")] = commit_blacklist.get(
            "file_sha256"
        )
    if isinstance(archive_provenance, dict):
        lock_reference = archive_provenance.get("lock")
        validator_reference = archive_provenance.get("validator")
        if isinstance(lock_reference, dict):
            direct_hashes[lock_reference.get("path")] = lock_reference.get(
                "file_sha256"
            )
        if isinstance(validator_reference, dict):
            direct_hashes[validator_reference.get("path")] = validator_reference.get(
                "sha256"
            )
    overlays = build.get("overlays")
    if isinstance(overlays, list):
        for overlay in overlays:
            if isinstance(overlay, dict):
                direct_hashes[overlay.get("patch_path")] = overlay.get(
                    "patch_sha256"
                )
    metadata_replacement = build.get("metadata_replacement")
    if isinstance(metadata_replacement, dict):
        direct_hashes[metadata_replacement.get("path")] = (
            metadata_replacement.get("replacement_sha256")
        )
    expected_hashes.update(
        {
            relative: digest
            for relative, digest in direct_hashes.items()
            if isinstance(relative, str) and relative
        }
    )
    if set(files) != set(expected_hashes):
        errors.append(f"{label}: historical recipe file set differs")
        return errors
    for relative, expected_sha256 in expected_hashes.items():
        stored = files.get(relative)
        if not isinstance(stored, dict):
            errors.append(f"{label}: historical recipe file is invalid: {relative}")
            continue
        text = stored.get("text")
        if (
            not isinstance(expected_sha256, str)
            or not SHA256_RE.fullmatch(expected_sha256)
            or not isinstance(text, str)
            or stored.get("sha256") != expected_sha256
            or sha256_bytes(text.encode()) != expected_sha256
        ):
            errors.append(f"{label}: historical recipe digest differs: {relative}")

    catalog_path = recipe.get("catalog_path")
    try:
        historical_catalog = json.loads(files[catalog_path]["text"])
        historical_spec = historical_catalog["cores"][record["core_id"]]
        if core_spec_sha256(historical_spec) != recipe.get("core_spec_sha256"):
            errors.append(f"{label}: historical core specification differs")
        if historical_spec.get("workflow") != recipe.get("workflow"):
            errors.append(f"{label}: historical workflow binding differs")
        if record.get("architecture") not in historical_spec.get("targets", []):
            errors.append(f"{label}: historical target binding differs")
        historical_source = historical_spec.get("source")
        if not isinstance(historical_source, dict) or any(
            historical_source.get(spec_key) != source.get(record_key)
            for spec_key, record_key in (
                ("url", "url"),
                ("requested_ref", "requested_ref"),
                ("commit", "commit"),
                ("tree", "tree"),
            )
            if spec_key in historical_source
        ):
            errors.append(f"{label}: historical source binding differs")
        historical_build = (
            historical_spec.get("build")
            if isinstance(historical_spec, dict)
            else None
        )
        if (
            isinstance(historical_build, dict)
            and historical_build.get("driver") == "direct-cargo"
        ):
            historical_resolver = historical_catalog.get("resolver")
            expected_absent = {"libretro_super_commit": None}
            if isinstance(historical_resolver, dict):
                for prefix in ("core_rules", "fetch_script", "build_script"):
                    expected_absent[f"{prefix}_path"] = historical_resolver.get(
                        f"{prefix}_path"
                    )
                    expected_absent[f"{prefix}_sha256"] = None
            if toolchain.get("resolver_digests") != expected_absent:
                errors.append(f"{label}: historical resolver binding differs")
        elif historical_catalog.get("resolver") != toolchain.get(
            "resolver_digests"
        ):
            errors.append(f"{label}: historical resolver binding differs")
        if isinstance(commit_blacklist, dict) and historical_catalog.get(
            "commit_blacklist"
        ) != commit_blacklist:
            errors.append(f"{label}: historical blacklist binding differs")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: cannot parse historical catalog snapshot: {exc}")
    return errors


def verify_stored_e2e_bundle(
    golden: dict,
    core_id: str,
    selected_arch: str,
    _validation_context: _PinValidationContext | None = None,
    *,
    historical_recipe_proofs: bool = False,
) -> list[str]:
    errors: list[str] = []
    label = f"{core_id}/{selected_arch}"
    log_contract = (
        None if historical_recipe_proofs else core_log_contract_for(core_id)
    )
    local_store = golden.get("local_store", {})
    try:
        e2e_path = safe_child(
            ROOT, local_store["e2e_record"]["path"], f"{label} stored E2E record"
        )
        package_path = safe_child(
            ROOT, local_store["package"]["path"], f"{label} stored package"
        )
        evidence = load_json(e2e_path)
    except (KeyError, PipelineError) as exc:
        return [f"{label}: cannot load stored E2E evidence: {exc}"]
    if (
        evidence.get("result") != "passed"
        or not evidence.get("local_only")
        or evidence.get("publication") != "disabled"
        or evidence.get("content_sha256") != e2e_content_sha256(evidence)
    ):
        errors.append(f"{label}: stored E2E record contract is invalid")
    if evidence.get("content_sha256") != golden.get("e2e", {}).get("content_sha256"):
        errors.append(f"{label}: stored E2E content is not bound to the golden")
    if evidence.get("run_id") != golden.get("e2e", {}).get("run_id"):
        errors.append(f"{label}: stored E2E run ID is not bound to the golden")
    build_entries = [
        item for item in evidence.get("builds", []) if item.get("core_id") == core_id
    ]
    expected_targets = set(golden.get("e2e", {}).get("build_records", {}))
    if not expected_targets:
        return [f"{label}: stored E2E target set is empty"]
    if (
        {item.get("architecture") for item in build_entries} != expected_targets
        or len(build_entries) != len(expected_targets)
        or any(item.get("result") != "passed" for item in build_entries)
    ):
        errors.append(f"{label}: stored E2E target set is invalid")
        return errors
    records: dict[str, dict] = {}
    for entry in build_entries:
        target = entry["architecture"]
        try:
            record_entry = local_store["build_records"][target]
            record_path = safe_child(
                ROOT, record_entry["path"], f"{label} stored {target} build record"
            )
            record = load_json(record_path)
            log_entry = local_store["build_logs"][target]
            recipe_entry = local_store["recipe_snapshots"][target]
            log_path = safe_child(ROOT, log_entry["path"], f"{label} stored {target} log")
            recipe_path = safe_child(
                ROOT, recipe_entry["path"], f"{label} stored {target} recipe"
            )
        except (KeyError, PipelineError) as exc:
            errors.append(f"{label}: cannot load stored {target} evidence: {exc}")
            continue
        if (
            record_entry.get("sha256") != entry.get("record_sha256")
            or record_entry.get("sha256")
            != golden.get("e2e", {}).get("build_records", {}).get(target)
        ):
            errors.append(f"{label}: stored {target} record digest is not E2E-bound")
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != target
            or record.get("result") != "passed"
            or record.get("build_exit_code") != 0
            or not record.get("local_only")
            or record.get("publication") != "disabled"
        ):
            errors.append(f"{label}: stored {target} build record contract is invalid")
        source = record.get("source", {})
        toolchain = record.get("toolchain", {})
        record_build = record.get("build", {})
        record_metadata_replacement = (
            record_build.get("metadata_replacement")
            if isinstance(record_build, dict)
            else None
        )
        if record_metadata_replacement is not None and not (
            metadata_matches_replacement(
                record.get("metadata"), record_metadata_replacement
            )
        ):
            errors.append(
                f"{label}: stored {target} metadata does not match its replacement"
            )
        if not isinstance(toolchain, dict):
            errors.append(f"{label}: stored {target} toolchain is not an object")
            toolchain = {}
        archive_provenance = toolchain.get("archive_provenance")
        if (
            source.get("resolved_commit") != source.get("commit")
            or source.get("resolved_url") != source.get("url")
            or not SHA1_RE.fullmatch(source.get("tree", ""))
            or toolchain.get("resolved_image_id") != toolchain.get("image_id")
            or toolchain.get("resolver_digests", {}).get("libretro_super_commit")
            != toolchain.get("libretro_super_commit")
        ):
            errors.append(f"{label}: stored {target} provenance is internally inconsistent")
        if archive_provenance is not None:
            if not isinstance(archive_provenance, dict) or (
                type(record.get("schema_version")) is not int
                or record["schema_version"] != 2
                or golden.get("provenance_version") != 2
                or archive_provenance.get("architecture")
                != (
                    "rust"
                    if isinstance(record_build, dict)
                    and record_build.get("driver") == "direct-cargo"
                    else target
                )
            ):
                errors.append(f"{label}: stored {target} archive provenance is invalid")
        elif golden.get("provenance_version") is not None:
            errors.append(f"{label}: stored {target} legacy provenance marker is invalid")
        has_make_variables = isinstance(record_build, dict) and (
            "make_variables" in record_build
        )
        has_git_version = isinstance(record_build, dict) and (
            "git_version" in record_build
        )
        has_generated_source = isinstance(record_build, dict) and (
            "generated_source" in record_build
        )
        has_recipe_profile = isinstance(record_build, dict) and (
            "recipe_profile" in record_build
        )
        is_combined_git_make_build = (
            core_id in COMBINED_NATIVE_MAKE_CORE_IDS
            and has_make_variables
            and has_git_version
        )
        if not isinstance(record_build, dict) or (
            "source_date_epoch" in record_build
            and not source_date_epoch_is_well_formed(
                record_build["source_date_epoch"]
            )
        ) or (
            has_generated_source
            and core_id != CORE_81_ID
        ) or (
            core_id == CORE_81_ID
            and (
                not has_generated_source
                or not core_81_golden_build_contract_is_well_formed(
                    record_build,
                    source.get("resolved_commit"),
                    core_id,
                    source,
                )
            )
        ) or (
            is_combined_git_make_build
            and not combined_git_version_make_golden_build_contract_is_well_formed(
                record_build, source.get("resolved_commit"), core_id, source
            )
        ) or (
            has_make_variables
            and not is_combined_git_make_build
            and not make_variable_golden_build_contract_is_well_formed(
                record_build
            )
        ) or (
            has_git_version
            and not is_combined_git_make_build
            and not git_version_golden_build_contract_is_well_formed(
                record_build,
                source.get("resolved_commit"),
                core_id,
                source,
                target,
            )
        ) or (
            core_id == VEMULATOR_CORE_ID
            and not vemulator_golden_build_contract_is_well_formed(
                record_build, source.get("resolved_commit"), core_id, source
            )
        ) or (
            core_id == FREEINTV_CORE_ID
            and not freeintv_golden_build_contract_is_well_formed(
                record_build, source.get("resolved_commit"), core_id, source
            )
        ) or (
            has_recipe_profile
            and (
                core_id != PICODRIVE_CORE_ID
                or not picodrive_golden_build_contract_is_well_formed(
                    record_build,
                    source.get("resolved_commit"),
                    core_id,
                    source,
                    target,
                )
            )
        ) or (
            core_id == PICODRIVE_CORE_ID and not has_recipe_profile
        ):
            errors.append(f"{label}: stored {target} build contract is invalid")
        if (
            not log_path.is_file()
            or log_entry.get("sha256") != record.get("build", {}).get("log_sha256")
        ):
            errors.append(f"{label}: stored {target} log is not build-record-bound")
        else:
            try:
                definitions = record.get("build", {}).get("compile_definitions", [])
                log_text = read_build_log(
                    log_path, f"{label} stored {target} log"
                )
                proof_key = (
                    target,
                    log_entry.get("sha256", ""),
                    sha256_bytes(
                        json.dumps(
                            record, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ),
                )
                proofs = (
                    _validation_context.log_proofs.get(proof_key)
                    if _validation_context is not None
                    and not historical_recipe_proofs
                    else None
                )
                make_variables = record_build.get("make_variables")
                git_version = record_build.get("git_version")
                metadata_replacement = record_build.get("metadata_replacement")
                if proofs is None:
                    proofs = (
                        isinstance(definitions, list)
                        and compile_log_proves_definitions(
                            log_text, definitions, target
                        ),
                        make_variables is None
                        or make_variable_log_proves_contract(
                            log_text, make_variables, target
                        ),
                        git_version is None
                        or git_version_log_proves_contract(
                            log_text,
                            git_version,
                            source.get("resolved_commit"),
                            target,
                        ),
                        metadata_replacement is None
                        or metadata_replacement_log_proves_contract(
                            log_text, metadata_replacement
                        ),
                        historical_recipe_proofs
                        or registered_core_log_contract_proves(
                            log_text,
                            core_id,
                            target,
                            source.get("resolved_commit"),
                            source.get("tree"),
                        ),
                    )
                    if (
                        _validation_context is not None
                        and not historical_recipe_proofs
                        and all(proofs)
                    ):
                        _validation_context.log_proofs[proof_key] = proofs
                (
                    definitions_proven,
                    make_proven,
                    version_proven,
                    metadata_proven,
                    registered_contract_proven,
                ) = proofs
                if not definitions_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its compile definitions"
                    )
                if not make_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its make-variable contract"
                    )
                if not version_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its "
                        "commit-derived GIT_VERSION contract"
                    )
                if not metadata_proven:
                    errors.append(
                        f"{label}: stored {target} log does not prove its "
                        "metadata replacement contract"
                    )
                if log_contract is not None and not registered_contract_proven:
                    errors.append(
                        f"{label}: stored {target} {log_contract.failure_message}"
                    )
            except PipelineError as exc:
                errors.append(str(exc))
        snapshot_validator = (
            verify_historical_recipe_snapshot
            if historical_recipe_proofs
            else verify_recipe_snapshot
        )
        errors.extend(snapshot_validator(recipe_path, record, f"{label}/{target}"))
        records[target] = record
    if set(records) != expected_targets or selected_arch not in records:
        return errors
    package_entries = [
        item for item in evidence.get("packages", []) if item.get("core_id") == core_id
    ]
    if (
        len(package_entries) != 1
        or package_entries[0].get("result") != "packaged"
        or package_entries[0].get("sha256")
        != golden.get("e2e", {}).get("package_sha256")
    ):
        errors.append(f"{label}: stored E2E package entry is not golden-bound")
    selected = records[selected_arch]
    selected_fields = ["source", "recipe", "toolchain", "artifact", "metadata"]
    if (
        core_id
        in (
            EXACT_GIT_VERSION_CORE_IDS
            | EXACT_SOURCE_NATIVE_CORE_IDS
            | {"vecx"}
        )
        or "build" in golden
    ):
        selected_fields.append("build")
    for field in selected_fields:
        if selected.get(field) != golden.get(field):
            errors.append(f"{label}: stored selected record {field} differs from golden")
    try:
        stored_artifact = safe_child(
            ROOT, local_store["artifact"]["path"], f"{label} stored artifact"
        )
        current_artifact = validate_artifact(stored_artifact, selected_arch)
        if (
            current_artifact.get("status") != "valid"
            or current_artifact.get("sha256") != selected["artifact"].get("sha256")
        ):
            errors.append(f"{label}: stored artifact no longer passes static validation")
    except (KeyError, PipelineError) as exc:
        errors.append(f"{label}: cannot revalidate stored artifact: {exc}")
    try:
        with zipfile.ZipFile(package_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            expected_members = {"manifest.json"}
            for target, record in records.items():
                member = (
                    f"{ARCH_LAYOUT[target]['package_directory']}/"
                    f"{record['artifact']['path']}"
                )
                expected_members.add(member)
                packaged = manifest.get("artifacts", {}).get(target, {})
                if (
                    packaged.get("path") != member
                    or packaged.get("sha256") != record["artifact"].get("sha256")
                    or packaged.get("source_commit")
                    != record["source"].get("resolved_commit")
                    or packaged.get("toolchain_image_id")
                    != record["toolchain"].get("resolved_image_id")
                    or sha256_bytes(archive.read(member)) != record["artifact"].get("sha256")
                ):
                    errors.append(f"{label}: stored package {target} artifact mismatch")
            metadata_hashes = {record["metadata"].get("sha256") for record in records.values()}
            metadata_names = {record["metadata"].get("path") for record in records.values()}
            if len(metadata_hashes) != 1 or len(metadata_names) != 1:
                errors.append(f"{label}: stored target metadata is inconsistent")
            else:
                metadata_name = next(iter(metadata_names))
                metadata_sha = next(iter(metadata_hashes))
                expected_members.add(metadata_name)
                if (
                    manifest.get("metadata", {}).get("path") != metadata_name
                    or manifest.get("metadata", {}).get("sha256") != metadata_sha
                    or sha256_bytes(archive.read(metadata_name)) != metadata_sha
                ):
                    errors.append(f"{label}: stored package metadata mismatch")
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist()) != expected_members
                or manifest.get("core_id") != core_id
                or not manifest.get("local_only")
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != expected_targets
            ):
                errors.append(f"{label}: stored package contract is invalid")
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        errors.append(f"{label}: cannot validate stored package: {exc}")
    return errors


def verify_local_store(
    document: dict,
    _validation_context: _PinValidationContext | None = None,
    *,
    historical_recipe_proofs: bool = False,
) -> list[str]:
    if _validation_context is None:
        _validation_context = _PinValidationContext()
    errors: list[str] = []
    if not isinstance(document, dict):
        return ["golden document must be an object"]
    build_goldens = document.get("build_goldens")
    if not isinstance(build_goldens, dict):
        return ["build_goldens must be an object"]
    for core_id, targets in build_goldens.items():
        if not isinstance(targets, dict):
            errors.append(f"{core_id}: build-golden targets must be an object")
            continue
        for arch, golden in targets.items():
            if not isinstance(golden, dict):
                errors.append(f"{core_id}/{arch}: build golden must be an object")
                continue
            local_store = golden.get("local_store")
            if not isinstance(local_store, dict):
                errors.append(f"{core_id}/{arch}: local store record must be an object")
                continue
            entries: list[tuple[str, dict]] = [
                (name, local_store.get(name, {}))
                for name in STORE_SINGLE_EVIDENCE_NAMES
            ]
            for group_name in STORE_TARGET_EVIDENCE_NAMES:
                group = local_store.get(group_name)
                if not isinstance(group, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {group_name} must be an object"
                    )
                    continue
                entries.extend(
                    (f"{group_name}/{target}", stored)
                    for target, stored in group.items()
                )
            all_files_valid = True
            for stored_name, stored in entries:
                if not isinstance(stored, dict):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} record must be an object"
                    )
                    all_files_valid = False
                    continue
                raw_path = stored.get("path")
                expected = stored.get("sha256")
                if (
                    not isinstance(raw_path, str)
                    or not raw_path
                    or not isinstance(expected, str)
                    or SHA256_RE.fullmatch(expected) is None
                ):
                    errors.append(
                        f"{core_id}/{arch}: local {stored_name} identity is invalid"
                    )
                    all_files_valid = False
                    continue
                try:
                    path = safe_child(
                        ROOT,
                        raw_path,
                        f"{core_id}/{arch} local {stored_name} path",
                    )
                except PipelineError as exc:
                    errors.append(str(exc))
                    all_files_valid = False
                    continue
                if not path.is_file():
                    errors.append(f"{core_id}/{arch}: local {stored_name} is unavailable")
                    all_files_valid = False
                elif sha256_file(path) != expected:
                    errors.append(f"{core_id}/{arch}: local {stored_name} digest drift")
                    all_files_valid = False
            if all_files_valid:
                errors.extend(
                    verify_stored_e2e_bundle(
                        golden,
                        core_id,
                        arch,
                        _validation_context,
                        historical_recipe_proofs=historical_recipe_proofs,
                    )
                )
    return errors


def golden_source_reference(path: Path, document: dict) -> dict:
    path = require_contained(path, ROOT, "golden source")
    return {
        "path": str(path.relative_to(ROOT)),
        "file_sha256": sha256_file(path),
        "content_sha256": document["content_sha256"],
        "pin_id": document["pin_id"],
    }


def complete_core_bundle(golden: dict, core_id: str) -> dict | None:
    build_goldens = golden.get("build_goldens")
    if not isinstance(build_goldens, dict):
        raise PipelineError("golden build_goldens must be an object")
    records = build_goldens.get(core_id, {})
    if not isinstance(records, dict):
        raise PipelineError(f"{core_id}: build-golden targets must be an object")
    if not records:
        return None
    e2e_by_arch: dict[str, dict] = {}
    target_sets: set[frozenset[str]] = set()
    for arch, record in records.items():
        if arch not in ARCH_LAYOUT or not isinstance(record, dict):
            raise PipelineError(
                f"{core_id}/{arch}: build golden must be an object for a known target"
            )
        e2e = record.get("e2e")
        if not isinstance(e2e, dict):
            raise PipelineError(f"{core_id}/{arch}: build-golden E2E must be an object")
        build_records = e2e.get("build_records")
        if (
            not isinstance(build_records, dict)
            or not build_records
            or any(target not in ARCH_LAYOUT for target in build_records)
        ):
            raise PipelineError(
                f"{core_id}/{arch}: build-golden E2E target set is invalid"
            )
        e2e_by_arch[arch] = e2e
        target_sets.add(frozenset(build_records))
    if len(target_sets) != 1:
        raise PipelineError(f"{core_id}: build goldens disagree on their E2E target set")
    expected_targets = set(next(iter(target_sets)))
    if set(records) != expected_targets:
        return None

    ordered = [records[target] for target in sorted(expected_targets)]
    first = ordered[0]
    first_e2e = e2e_by_arch[sorted(expected_targets)[0]]
    first_metadata = first.get("metadata")
    shared_source = first.get("source")
    shared_recipe = first.get("recipe")
    first_local_store = first.get("local_store")
    if (
        not isinstance(first_metadata, dict)
        or not isinstance(shared_source, dict)
        or not isinstance(shared_recipe, dict)
        or not isinstance(first_local_store, dict)
        or not isinstance(first_local_store.get("package"), dict)
    ):
        raise PipelineError(f"{core_id}: build-golden bundle fields are invalid")
    shared_e2e = {
        "run_id": first_e2e.get("run_id"),
        "content_sha256": first_e2e.get("content_sha256"),
        "package_sha256": first_e2e.get("package_sha256"),
        "build_records": first_e2e.get("build_records"),
    }
    shared_metadata_sha = first_metadata.get("sha256")
    shared_package_store = first_local_store["package"]
    for arch, record in zip(sorted(expected_targets), ordered, strict=True):
        metadata = record.get("metadata")
        source = record.get("source")
        recipe = record.get("recipe")
        local_store = record.get("local_store")
        if (
            not isinstance(metadata, dict)
            or not isinstance(source, dict)
            or not isinstance(recipe, dict)
            or not isinstance(local_store, dict)
            or not isinstance(local_store.get("package"), dict)
        ):
            raise PipelineError(f"{core_id}/{arch}: build-golden fields are invalid")
        e2e = e2e_by_arch[arch]
        current_e2e = {
            "run_id": e2e.get("run_id"),
            "content_sha256": e2e.get("content_sha256"),
            "package_sha256": e2e.get("package_sha256"),
            "build_records": e2e.get("build_records"),
        }
        if (
            record.get("core_id") != core_id
            or record.get("promotion_state") != "build_golden"
            or record.get("validation_scope") != "static-build-only"
            or current_e2e != shared_e2e
            or metadata.get("sha256") != shared_metadata_sha
            or source != shared_source
            or recipe != shared_recipe
            or local_store.get("package") != shared_package_store
        ):
            raise PipelineError(f"{core_id}: build goldens are not one coherent package")
        record_build = record.get("build", {})
        record_metadata_replacement = (
            record_build.get("metadata_replacement")
            if isinstance(record_build, dict)
            else None
        )
        if record_metadata_replacement is not None and not (
            metadata_matches_replacement(
                record.get("metadata"), record_metadata_replacement
            )
        ):
            raise PipelineError(
                f"{core_id}: metadata does not match its replacement"
            )

    package_path = require_canonical_store_entry(
        shared_package_store, "packages", f"{core_id} package"
    )
    if (
        not package_path.is_file()
        or sha256_file(package_path) != shared_e2e.get("package_sha256")
    ):
        raise PipelineError(f"{core_id}: package is missing from the local store")
    metadata_store = first_local_store.get("metadata")
    if not isinstance(metadata_store, dict):
        raise PipelineError(f"{core_id}: metadata store record is invalid")
    metadata_path = require_canonical_store_entry(
        metadata_store, "metadata", f"{core_id} metadata"
    )
    if (
        not metadata_path.is_file()
        or metadata_path.stat().st_size != first_metadata.get("size")
        or sha256_file(metadata_path) != shared_metadata_sha
    ):
        raise PipelineError(f"{core_id}: metadata is missing from the local store")

    targets = {}
    for arch in sorted(expected_targets):
        record = records[arch]
        artifact = record.get("artifact")
        local_store = record.get("local_store")
        artifact_store = (
            local_store.get("artifact") if isinstance(local_store, dict) else None
        )
        if not isinstance(artifact, dict) or not isinstance(artifact_store, dict):
            raise PipelineError(f"{core_id}/{arch}: artifact records are invalid")
        artifact_path = require_canonical_store_entry(
            artifact_store, "artifacts", f"{core_id}/{arch} artifact"
        )
        if (
            artifact.get("status") != "valid"
            or artifact_store.get("sha256") != artifact.get("sha256")
            or not artifact_path.is_file()
            or artifact_path.stat().st_size != artifact.get("size")
            or sha256_file(artifact_path) != artifact.get("sha256")
        ):
            raise PipelineError(f"{core_id}/{arch}: artifact store identity is invalid")
        targets[arch] = {
            "artifact": {
                "path": artifact_store["path"],
                "sha256": artifact["sha256"],
                "size": artifact["size"],
            },
            "build_record_sha256": shared_e2e["build_records"][arch],
            "provenance_identity_sha256": provenance_identity_sha256(record),
            "golden_record": copy.deepcopy(record),
        }

    selection = {
        "tier": "build_golden",
        "validation_scope": "static-build-only",
        "e2e": shared_e2e,
        "package": {
            "name": f"{core_id}_libretro.zip",
            "path": shared_package_store["path"],
            "sha256": shared_e2e["package_sha256"],
            "size": package_path.stat().st_size,
        },
        "metadata": {
            "path": metadata_store["path"],
            "sha256": shared_metadata_sha,
            "size": metadata_path.stat().st_size,
        },
        "targets": targets,
    }
    selection["selection_sha256"] = selection_content_sha256(selection)
    return selection


def individual_core_semantic_id(core_id: str, selection: dict) -> str:
    """Derive the canonical ID shared by one core's nightly, pin, and release."""

    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        raise PipelineError("individual core semantic identity has an invalid core ID")
    targets = selection.get("targets") if isinstance(selection, dict) else None
    if not isinstance(targets, dict) or not targets:
        raise PipelineError("individual core semantic identity has no targets")
    source_commits: set[str] = set()
    for target in targets.values():
        if not isinstance(target, dict):
            raise PipelineError(
                "individual core semantic identity has an invalid target"
            )
        golden_record = target.get("golden_record")
        source = (
            golden_record.get("source")
            if isinstance(golden_record, dict)
            else None
        )
        if not isinstance(source, dict):
            raise PipelineError(
                "individual core semantic identity has an invalid source"
            )
        source_commit = source.get("commit")
        if not isinstance(source_commit, str) or SHA1_RE.fullmatch(source_commit) is None:
            raise PipelineError("individual core semantic identity is invalid")
        source_commits.add(source_commit)
    source_commit = next(iter(source_commits), None)
    selection_sha256 = selection.get("selection_sha256")
    if (
        len(source_commits) != 1
        or not isinstance(selection_sha256, str)
        or SHA256_RE.fullmatch(selection_sha256) is None
    ):
        raise PipelineError("individual core semantic identity is invalid")
    return f"{core_id}-{source_commit[:12]}-{selection_sha256[:12]}"


def require_individual_pin_identity(
    pin: dict,
    *,
    pin_path: Path | None = None,
) -> tuple[str, str]:
    """Require the canonical parentless one-core pin used by active mutators."""

    scope = pin.get("scope")
    cores = pin.get("cores")
    sources = pin.get("sources")
    if (
        not isinstance(scope, list)
        or len(scope) != 1
        or not isinstance(scope[0], str)
        or not isinstance(cores, dict)
        or set(cores) != {scope[0]}
        or pin.get("parent") is not None
        or not isinstance(sources, list)
        or len(sources) != 1
    ):
        raise PipelineError(
            "active pin mutation requires one parentless core and one source"
        )
    core_id = scope[0]
    core_record = cores.get(core_id)
    if (
        not isinstance(core_record, dict)
        or core_record.get("decision") != "select_source"
        or core_record.get("source_index") != 0
        or not isinstance(core_record.get("selection"), dict)
    ):
        raise PipelineError("active pin mutation requires one direct core selection")
    semantic_id = individual_core_semantic_id(
        core_id,
        core_record["selection"],
    )
    if pin.get("pin_id") != semantic_id:
        raise PipelineError(
            f"individual pin ID must be semantic ID {semantic_id}"
        )
    source_reference = sources[0]
    expected_source_path = f".local-e2e/nightlies/{semantic_id}/golden.json"
    if (
        not isinstance(source_reference, dict)
        or source_reference.get("path") != expected_source_path
    ):
        raise PipelineError(
            "individual pin source must be its exact semantic nightly golden"
        )
    if pin_path is not None:
        canonical_pin_path = require_lexical_repository_path(
            pin_path,
            DEFAULT_PIN_SET_DIR,
            "individual pin",
        )
        expected_pin_path = (DEFAULT_PIN_SET_DIR / f"{semantic_id}.json").resolve()
        if canonical_pin_path != expected_pin_path:
            raise PipelineError(
                f"individual pin path must be pins/core-sets/{semantic_id}.json"
            )
    return core_id, semantic_id


def inspect_individual_core_golden(
    core_id: str,
    source_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
) -> tuple[dict, dict, str, Path]:
    """Read and identify a complete working golden owned by one core."""

    catalog = load_catalog(catalog_path)
    if core_id not in catalog["cores"]:
        raise PipelineError(f"individual golden core is not cataloged: {core_id}")
    source_path = require_lexical_repository_path(
        source_path,
        ROOT,
        "core golden source",
    )
    if not source_path.is_file() or source_path.is_symlink():
        raise PipelineError("core golden source must be a regular file")
    source = load_json(source_path)
    source_report = validate_golden_document(source)
    if source_report["status"] != "valid":
        raise PipelineError(
            "cannot project an invalid golden source:\n- "
            + "\n- ".join(source_report["errors"])
        )
    require_active_core_golden(source, core_id)
    require_active_candidate_golden_path(source_path, source)
    store_errors = verify_local_store(source)
    if store_errors:
        raise PipelineError(
            "individual core golden source store is invalid:\n- "
            + "\n- ".join(store_errors)
        )
    build_goldens = source.get("build_goldens")
    if not isinstance(build_goldens, dict) or set(build_goldens) != {core_id}:
        raise PipelineError(
            "individual core golden source must contain build evidence for exactly its core"
        )
    selection = complete_core_bundle(source, core_id)
    if selection is None:
        raise PipelineError(f"core golden source has no complete {core_id} bundle")
    semantic_id = individual_core_semantic_id(core_id, selection)
    return source, selection, semantic_id, source_path


def derive_core_id(
    *,
    core_id: str,
    source_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict:
    """Return canonical individual lifecycle paths without mutating the tree."""

    _source, _selection, semantic_id, source_path = inspect_individual_core_golden(
        core_id,
        source_path,
        catalog_path,
    )
    return {
        "status": "valid",
        "core_id": core_id,
        "semantic_id": semantic_id,
        "source_golden": str(source_path.relative_to(ROOT)),
        "nightly_golden": str(
            (DEFAULT_NIGHTLIES / semantic_id / "golden.json").relative_to(ROOT)
        ),
        "pin_set": str((DEFAULT_PIN_SET_DIR / f"{semantic_id}.json").relative_to(ROOT)),
        "release": str((DEFAULT_RELEASES / semantic_id).relative_to(ROOT)),
    }


def compose_core_golden(
    *,
    core_id: str,
    source_path: Path,
    output_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict:
    """Create one exact-scope nightly view from immutable promoted evidence."""

    output_path = require_lexical_repository_path(
        output_path,
        DEFAULT_NIGHTLIES,
        "individual core golden output",
    )
    output_relative = output_path.relative_to(DEFAULT_NIGHTLIES.resolve())
    if (
        len(output_relative.parts) != 2
        or output_relative.parts[1] != "golden.json"
        or not LOCAL_ID_RE.fullmatch(output_relative.parts[0])
    ):
        raise PipelineError(
            "individual core golden output must be <semantic-id>/golden.json"
        )
    if output_path.exists() or output_path.is_symlink():
        raise PipelineError(f"refusing to replace individual core golden: {output_path}")
    source, _selection, semantic_id, _source_path = inspect_individual_core_golden(
        core_id,
        source_path,
        catalog_path,
    )
    if output_relative.parts[0] != semantic_id:
        raise PipelineError(
            f"individual core golden directory must be semantic ID {semantic_id}"
        )

    projected = one_core_golden_document(
        core_id=core_id,
        pin_id=semantic_id,
        created_at=source["created_at"],
        updated_at=source.get("updated_at"),
        baseline=source["baseline"],
        core_record=source["cores"][core_id],
        build_goldens=source["build_goldens"][core_id],
    )
    projected["content_sha256"] = golden_content_sha256(projected)
    projected_report = validate_golden_document(projected)
    projected_errors = [
        *projected_report["errors"],
        *verify_local_store(projected),
    ]
    if projected_errors:
        raise PipelineError(
            "individual core golden projection is invalid:\n- "
            + "\n- ".join(projected_errors)
        )
    atomic_create_json(output_path, projected)
    return {
        "status": "created",
        "core_id": core_id,
        "semantic_id": semantic_id,
        "path": str(output_path.relative_to(ROOT)),
        "file_sha256": sha256_file(output_path),
        "content_sha256": projected["content_sha256"],
    }


def freeze_failed_e2e(e2e_path: Path, store_root: Path = DEFAULT_STORE) -> dict[str, dict]:
    e2e_path = require_contained(e2e_path, ROOT / ".local-e2e", "failed E2E record")
    store_root = require_contained(store_root, ROOT / ".local-e2e", "local store")
    if e2e_path.name != "e2e-record.json":
        raise PipelineError("failed E2E evidence must be an e2e-record.json file")
    evidence_bytes = e2e_path.read_bytes()
    try:
        evidence = json.loads(evidence_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PipelineError(f"cannot parse failed E2E evidence: {exc}") from exc
    if (
        not isinstance(evidence, dict)
        or evidence.get("result") != "failed"
        or not evidence.get("local_only")
        or evidence.get("publication") != "disabled"
        or evidence.get("content_sha256") != e2e_content_sha256(evidence)
    ):
        raise PipelineError("failed E2E evidence contract is invalid")

    stored_e2e, stored_e2e_sha = store_bytes(store_root, "e2e", evidence_bytes)
    build_records: dict[str, dict[str, dict]] = {}
    for entry in evidence.get("builds", []):
        core_id = entry.get("core_id")
        arch = entry.get("architecture")
        if not core_id or arch not in ARCH_LAYOUT:
            raise PipelineError("failed E2E build identity is invalid")
        record_path = safe_child(ROOT, entry.get("record", ""), "failed build record")
        require_contained(record_path, e2e_path.parent, "failed build record")
        if not record_path.is_file() or sha256_file(record_path) != entry.get(
            "record_sha256"
        ):
            raise PipelineError("failed E2E build record digest is invalid")
        record = load_json(record_path)
        if (
            record.get("core_id") != core_id
            or record.get("architecture") != arch
            or record.get("result") != entry.get("result")
            or not record.get("local_only")
            or record.get("publication") != "disabled"
        ):
            raise PipelineError("failed E2E build record identity is invalid")
        stored_record, stored_record_sha = store_file(
            store_root, "build-records", record_path
        )
        frozen = {
            "result": entry.get("result"),
            "record": {
                "path": str(stored_record.relative_to(ROOT)),
                "sha256": stored_record_sha,
            },
        }
        log_name = record.get("build", {}).get("log")
        if log_name:
            log_path = safe_child(record_path.parent, log_name, "failed build log")
            expected_log_sha = record.get("build", {}).get("log_sha256")
            if not log_path.is_file() or sha256_file(log_path) != expected_log_sha:
                raise PipelineError("failed E2E build log digest is invalid")
            stored_log, stored_log_sha = store_file(store_root, "logs", log_path)
            frozen["log"] = {
                "path": str(stored_log.relative_to(ROOT)),
                "sha256": stored_log_sha,
            }
        core_records = build_records.setdefault(core_id, {})
        if arch in core_records:
            raise PipelineError(f"duplicate failed E2E build identity for {core_id}/{arch}")
        core_records[arch] = frozen

    failures = {}
    for package in evidence.get("packages", []):
        if package.get("result") != "not_packaged":
            continue
        core_id = package.get("core_id")
        if not core_id or core_id in failures:
            raise PipelineError("failed E2E package identity is invalid")
        failures[core_id] = {
            "run_id": evidence.get("run_id"),
            "content_sha256": evidence.get("content_sha256"),
            "record": {
                "path": str(stored_e2e.relative_to(ROOT)),
                "sha256": stored_e2e_sha,
            },
            "reason": package.get("reason", "core package was not produced"),
            "build_records": build_records.get(core_id, {}),
        }
    if not failures:
        raise PipelineError("failed E2E evidence contains no rejected core package")
    return failures


def verify_pinned_package(selection: dict, core_id: str) -> list[str]:
    errors: list[str] = []
    package = selection.get("package", {})
    try:
        package_path = require_canonical_store_entry(
            package, "packages", f"{core_id} pinned package"
        )
        with zipfile.ZipFile(package_path) as archive:
            targets = selection.get("targets", {})
            expected_members = {"manifest.json"}
            manifest = json.loads(archive.read("manifest.json"))
            for arch, target in targets.items():
                record = target.get("golden_record", {})
                artifact_name = record.get("artifact", {}).get("path")
                member = f"{ARCH_LAYOUT[arch]['package_directory']}/{artifact_name}"
                expected_members.add(member)
                packaged = manifest.get("artifacts", {}).get(arch, {})
                if (
                    packaged.get("path") != member
                    or packaged.get("sha256") != target.get("artifact", {}).get("sha256")
                    or packaged.get("source_commit")
                    != record.get("source", {}).get("resolved_commit")
                    or packaged.get("toolchain_image_id")
                    != record.get("toolchain", {}).get("resolved_image_id")
                    or sha256_bytes(archive.read(member))
                    != target.get("artifact", {}).get("sha256")
                ):
                    errors.append(f"{core_id}/{arch}: pinned package artifact mismatch")
            first_record = next(iter(targets.values())).get("golden_record", {})
            metadata_name = first_record.get("metadata", {}).get("path")
            expected_members.add(metadata_name)
            metadata = selection.get("metadata", {})
            if (
                manifest.get("metadata", {}).get("path") != metadata_name
                or manifest.get("metadata", {}).get("sha256") != metadata.get("sha256")
                or sha256_bytes(archive.read(metadata_name)) != metadata.get("sha256")
            ):
                errors.append(f"{core_id}: pinned package metadata mismatch")
            if (
                len(archive.namelist()) != len(set(archive.namelist()))
                or set(archive.namelist()) != expected_members
                or manifest.get("core_id") != core_id
                or not manifest.get("local_only")
                or manifest.get("publication") != "disabled"
                or set(manifest.get("artifacts", {})) != set(targets)
            ):
                errors.append(f"{core_id}: pinned package contract is invalid")
    except (
        KeyError,
        StopIteration,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
        OSError,
        PipelineError,
    ) as exc:
        errors.append(f"{core_id}: cannot verify pinned package: {exc}")
    return errors


def _validate_pin_set_document_impl(
    document: dict,
    *,
    verify_store: bool = False,
    verify_sources: bool = False,
    document_path: Path | None = None,
    _lineage_paths: tuple[Path, ...] = (),
    _lineage_identities: frozenset[tuple[str, str]] = frozenset(),
    _lineage_depth: int = 0,
    _validation_context: _PinValidationContext | None = None,
    historical_recipe_proofs: bool = False,
) -> dict:
    if not isinstance(document, dict):
        return {"status": "invalid", "errors": ["pin set must be an object"]}
    if _validation_context is None:
        _validation_context = _PinValidationContext()
    if _lineage_depth > MAX_PIN_PARENT_DEPTH:
        return {
            "status": "invalid",
            "errors": [
                f"pin parent lineage exceeds maximum depth {MAX_PIN_PARENT_DEPTH}"
            ],
        }

    errors: list[str] = []
    pin_id = document.get("pin_id")
    content_sha256 = document.get("content_sha256")
    scope = document.get("scope")
    cores = document.get("cores")
    sources = document.get("sources")
    parent = document.get("parent")
    summary = document.get("summary")
    if not isinstance(pin_id, str) or LOCAL_ID_RE.fullmatch(pin_id) is None:
        errors.append("pin_id is invalid")
    if not isinstance(content_sha256, str) or SHA256_RE.fullmatch(
        content_sha256
    ) is None:
        errors.append("pin-set content digest is invalid")
    if not isinstance(scope, list) or any(
        not isinstance(core_id, str) for core_id in scope
    ):
        errors.append("pin-set scope must be an array of core IDs")
    if not isinstance(cores, dict) or any(
        not isinstance(core_id, str) or not isinstance(core, dict)
        for core_id, core in (cores.items() if isinstance(cores, dict) else ())
    ):
        errors.append("pin-set cores must be an object of core records")
    if not isinstance(sources, list) or any(
        not isinstance(source, dict) for source in sources
    ):
        errors.append("pin-set sources must be an array of source records")
    if parent is not None and not isinstance(parent, dict):
        errors.append("parent pin identity is invalid")
    if not isinstance(summary, dict):
        errors.append("pin-set summary must be an object")
    if errors:
        return {"status": "invalid", "errors": errors}

    lineage_paths = _lineage_paths
    if document_path is not None:
        try:
            current_path = require_contained(
                document_path, DEFAULT_PIN_SET_DIR, "pin-set document"
            )
            if current_path in lineage_paths:
                return {
                    "status": "invalid",
                    "errors": ["pin parent lineage contains a path cycle"],
                }
            lineage_paths = (*lineage_paths, current_path)
        except PipelineError as exc:
            errors.append(str(exc))

    lineage_identities = _lineage_identities
    current_identity = (
        pin_id,
        content_sha256,
    )
    if LOCAL_ID_RE.fullmatch(current_identity[0]) and SHA256_RE.fullmatch(
        current_identity[1]
    ):
        if current_identity in lineage_identities:
            return {
                "status": "invalid",
                "errors": ["pin parent lineage repeats an immutable pin identity"],
            }
        lineage_identities = lineage_identities | {current_identity}

    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not document.get("local_only") or document.get("publication") != "disabled":
        errors.append("pin set must be local-only and publication-disabled")
    if document.get("content_sha256") != pin_set_content_sha256(document):
        errors.append("pin-set content digest is invalid")
    if document.get("selection_policy") != PIN_SELECTION_POLICY:
        errors.append("pin-set selection policy is invalid")
    scope_is_well_formed = (
        all(core_id for core_id in scope)
        and scope == sorted(set(scope))
        and set(scope) == set(cores)
    )
    if not scope_is_well_formed:
        errors.append("pin-set scope does not exactly match its core selections")

    source_count = len(sources)
    source_documents: list[dict | None] = []
    for index, source in enumerate(sources):
        source_document = None
        if (
            not SHA256_RE.fullmatch(source.get("file_sha256", ""))
            or not SHA256_RE.fullmatch(source.get("content_sha256", ""))
        ):
            errors.append(f"source {index} digest is invalid")
            source_documents.append(None)
            continue
        try:
            source_path = require_manifest_reference_path(
                source, ROOT, f"source {index}"
            )
            if verify_sources:
                if not source_path.is_file() or sha256_file(source_path) != source[
                    "file_sha256"
                ]:
                    errors.append(f"source {index} no longer matches the pin")
                else:
                    source_document = load_json(source_path)
                    if (
                        source_document.get("content_sha256")
                        != source["content_sha256"]
                        or source_document.get("pin_id") != source.get("pin_id")
                    ):
                        errors.append(f"source {index} no longer matches the pin")
                        source_document = None
                    else:
                        source_report = validate_golden_document(source_document)
                        source_errors = list(source_report["errors"])
                        if verify_store:
                            source_errors.extend(
                                verify_local_store(
                                    source_document,
                                    _validation_context,
                                    historical_recipe_proofs=(
                                        historical_recipe_proofs
                                    ),
                                )
                            )
                        if source_errors:
                            errors.extend(
                                f"source {index}: {error}" for error in source_errors
                            )
                            source_document = None
        except PipelineError as exc:
            errors.append(str(exc))
        source_documents.append(source_document)

    parent_document = None
    if parent is not None and (
        not isinstance(parent.get("file_sha256"), str)
        or SHA256_RE.fullmatch(parent["file_sha256"]) is None
        or not isinstance(parent.get("content_sha256"), str)
        or SHA256_RE.fullmatch(parent["content_sha256"]) is None
        or not isinstance(parent.get("pin_id"), str)
        or LOCAL_ID_RE.fullmatch(parent["pin_id"]) is None
    ):
        errors.append("parent pin identity is invalid")
    elif parent is not None:
        try:
            parent_path = require_manifest_reference_path(
                parent, DEFAULT_PIN_SET_DIR, "parent pin"
            )
            parent_identity = (parent["pin_id"], parent["content_sha256"])
            if verify_sources and parent_path in lineage_paths:
                errors.append("pin parent lineage contains a path cycle")
            elif verify_sources and parent_identity in lineage_identities:
                errors.append("pin parent lineage repeats an immutable pin identity")
            elif verify_sources and _lineage_depth >= MAX_PIN_PARENT_DEPTH:
                errors.append(
                    f"pin parent lineage exceeds maximum depth {MAX_PIN_PARENT_DEPTH}"
                )
            elif verify_sources and (
                not parent_path.is_file()
                or sha256_file(parent_path) != parent["file_sha256"]
            ):
                errors.append("parent pin no longer matches its reference")
            elif verify_sources:
                parent_document = load_json(parent_path)
                if (
                    parent_document.get("content_sha256")
                    != parent["content_sha256"]
                    or parent_document.get("pin_id") != parent["pin_id"]
                ):
                    errors.append("parent pin no longer matches its reference")
                    parent_document = None
                else:
                    parent_scope = parent_document.get("scope", [])
                    if (
                        scope_is_well_formed
                        and isinstance(parent_scope, list)
                        and all(isinstance(core_id, str) for core_id in parent_scope)
                    ):
                        dropped = sorted(set(parent_scope) - set(scope))
                        if dropped:
                            errors.append(
                                "pin-set scope drops parent cores: "
                                + ", ".join(dropped)
                            )
                    ancestor_report = validate_pin_set_document(
                        parent_document,
                        verify_store=verify_store,
                        verify_sources=True,
                        document_path=parent_path,
                        _lineage_paths=lineage_paths,
                        _lineage_identities=lineage_identities,
                        _lineage_depth=_lineage_depth + 1,
                        _validation_context=_validation_context,
                        historical_recipe_proofs=historical_recipe_proofs,
                    )
                    errors.extend(
                        f"parent {parent['pin_id']}: {error}"
                        for error in ancestor_report["errors"]
                    )
        except PipelineError as exc:
            errors.append(str(exc))

    retained = 0
    for core_id, core in cores.items():
        decision = core.get("decision")
        if decision not in {"select_source", "retain_parent"}:
            errors.append(f"{core_id}: selection decision is invalid")
        if decision == "select_source":
            source_index = core.get("source_index")
            if (
                isinstance(source_index, bool)
                or not isinstance(source_index, int)
                or not 0 <= source_index < source_count
            ):
                errors.append(f"{core_id}: source index is invalid")
        else:
            retained += 1
            if parent is None:
                errors.append(f"{core_id}: parent retention lacks a parent pin")
        selection = core.get("selection")
        if not isinstance(selection, dict):
            errors.append(f"{core_id}: selection must be an object")
            continue
        reconstructed_sources: list[dict | None] = []
        if verify_sources:
            for source_index, source_document in enumerate(source_documents):
                if source_document is None:
                    reconstructed_sources.append(None)
                    continue
                try:
                    reconstructed_sources.append(
                        complete_core_bundle(source_document, core_id)
                    )
                except PipelineError as exc:
                    errors.append(
                        f"{core_id}: cannot reconstruct source {source_index} bundle: {exc}"
                    )
                    reconstructed_sources.append(None)
        if verify_sources and decision == "select_source":
            source_index = core.get("source_index")
            if (
                isinstance(source_index, int)
                and not isinstance(source_index, bool)
                and 0 <= source_index < len(reconstructed_sources)
            ):
                expected_selection = reconstructed_sources[source_index]
                if expected_selection is None or selection != expected_selection:
                    errors.append(
                        f"{core_id}: selection does not match its frozen source bundle"
                    )
                if any(
                    candidate is not None
                    for candidate in reconstructed_sources[:source_index]
                ):
                    errors.append(
                        f"{core_id}: selection violates first-complete source order"
                    )
        elif verify_sources and decision == "retain_parent":
            if any(candidate is not None for candidate in reconstructed_sources):
                errors.append(f"{core_id}: parent retained despite a complete source bundle")
            if parent_document is not None:
                parent_selection = (
                    parent_document.get("cores", {}).get(core_id, {}).get("selection")
                )
                if selection != parent_selection:
                    errors.append(f"{core_id}: retained selection differs from its parent")
        computed_selection_sha256 = selection_content_sha256(selection)
        full_selection_sha256 = sha256_bytes(
            json.dumps(selection, sort_keys=True, separators=(",", ":")).encode()
        )
        if selection.get("selection_sha256") != computed_selection_sha256:
            errors.append(f"{core_id}: selection digest is invalid")
        if (
            selection.get("tier") != "build_golden"
            or selection.get("validation_scope") != "static-build-only"
        ):
            errors.append(f"{core_id}: only static build-golden bundles are selectable")
        package = selection.get("package")
        if not isinstance(package, dict):
            errors.append(f"{core_id}: package must be an object")
            package = {}
        if package.get("name") != f"{core_id}_libretro.zip":
            errors.append(f"{core_id}: package name is invalid")
        package_store_valid = False
        try:
            package_path = require_canonical_store_entry(
                package, "packages", f"{core_id} pinned package"
            )
            if verify_store:
                package_store_valid = bool(
                    package_path.is_file()
                    and package_path.stat().st_size == package.get("size")
                    and sha256_file(package_path) == package.get("sha256")
                )
                if not package_store_valid:
                    errors.append(
                        f"{core_id}: pinned package store identity is invalid"
                    )
        except PipelineError as exc:
            errors.append(str(exc))

        metadata = selection.get("metadata")
        if not isinstance(metadata, dict):
            errors.append(f"{core_id}: metadata must be an object")
            metadata = {}
        try:
            metadata_path = require_canonical_store_entry(
                metadata, "metadata", f"{core_id} pinned metadata"
            )
            if verify_store and (
                not metadata_path.is_file()
                or metadata_path.stat().st_size != metadata.get("size")
                or sha256_file(metadata_path) != metadata.get("sha256")
            ):
                errors.append(f"{core_id}: pinned metadata store identity is invalid")
        except PipelineError as exc:
            errors.append(str(exc))

        targets = selection.get("targets")
        if not isinstance(targets, dict):
            errors.append(f"{core_id}: targets must be an object")
            targets = {}
        selected_e2e = selection.get("e2e")
        if not isinstance(selected_e2e, dict):
            errors.append(f"{core_id}: E2E identity must be an object")
            selected_e2e = {}
        selected_build_records = selected_e2e.get("build_records")
        if not isinstance(selected_build_records, dict):
            errors.append(f"{core_id}: E2E build records must be an object")
            selected_build_records = {}
        expected_targets = set(selected_build_records)
        if (
            not selected_e2e.get("run_id")
            or not SHA256_RE.fullmatch(selected_e2e.get("content_sha256", ""))
            or selected_e2e.get("package_sha256") != package.get("sha256")
        ):
            errors.append(f"{core_id}: pinned E2E identity is invalid")
        if not targets or set(targets) != expected_targets:
            errors.append(f"{core_id}: pinned target set is incomplete")
        reference_source = None
        reference_recipe = None
        for arch, target in targets.items():
            if not isinstance(target, dict):
                errors.append(f"{core_id}/{arch}: target must be an object")
                continue
            record = target.get("golden_record")
            artifact = target.get("artifact")
            if not isinstance(record, dict) or not isinstance(artifact, dict):
                errors.append(
                    f"{core_id}/{arch}: golden record and artifact must be objects"
                )
                continue
            if arch not in ARCH_LAYOUT:
                errors.append(f"{core_id}: unknown pinned target {arch}")
                continue
            if (
                record.get("core_id") != core_id
                or record.get("architecture") != arch
                or record.get("promotion_state") != "build_golden"
                or record.get("artifact", {}).get("sha256") != artifact.get("sha256")
                or record.get("artifact", {}).get("size") != artifact.get("size")
                or record.get("metadata", {}).get("sha256") != metadata.get("sha256")
                or record.get("local_store", {}).get("artifact", {}).get("path")
                != artifact.get("path")
                or record.get("local_store", {}).get("artifact", {}).get("sha256")
                != artifact.get("sha256")
                or record.get("local_store", {}).get("metadata", {}).get("path")
                != metadata.get("path")
                or record.get("local_store", {}).get("metadata", {}).get("sha256")
                != metadata.get("sha256")
                or record.get("local_store", {}).get("package", {}).get("path")
                != package.get("path")
                or record.get("local_store", {}).get("package", {}).get("sha256")
                != package.get("sha256")
                or record.get("e2e", {}).get("package_sha256")
                != package.get("sha256")
                or record.get("e2e", {}).get("content_sha256")
                != selection.get("e2e", {}).get("content_sha256")
                or record.get("e2e", {}).get("build_records")
                != selection.get("e2e", {}).get("build_records")
                or target.get("build_record_sha256")
                != selected_build_records.get(arch)
                or target.get("provenance_identity_sha256")
                != provenance_identity_sha256(record)
            ):
                errors.append(f"{core_id}/{arch}: embedded golden record is inconsistent")
            record_build = record.get("build", {})
            record_metadata_replacement = (
                record_build.get("metadata_replacement")
                if isinstance(record_build, dict)
                else None
            )
            if record_metadata_replacement is not None and not (
                metadata_matches_replacement(
                    record.get("metadata"), record_metadata_replacement
                )
            ):
                errors.append(
                    f"{core_id}/{arch}: embedded metadata does not match its replacement"
                )
            if reference_source is None:
                reference_source = record.get("source")
                reference_recipe = record.get("recipe")
            elif record.get("source") != reference_source or record.get("recipe") != reference_recipe:
                errors.append(f"{core_id}: target provenance is not package-coherent")
            try:
                artifact_path = require_canonical_store_entry(
                    artifact, "artifacts", f"{core_id}/{arch} pinned artifact"
                )
                if verify_store and (
                    not artifact_path.is_file()
                    or artifact_path.stat().st_size != artifact.get("size")
                    or sha256_file(artifact_path) != artifact.get("sha256")
                ):
                    errors.append(f"{core_id}/{arch}: pinned artifact store identity is invalid")
            except PipelineError as exc:
                errors.append(str(exc))

        if verify_store:
            package_cache_key = None
            if (
                package_store_valid
                and isinstance(package.get("path"), str)
                and isinstance(package.get("sha256"), str)
                and type(package.get("size")) is int
            ):
                package_cache_key = (
                    core_id,
                    full_selection_sha256,
                    package["path"],
                    package["sha256"],
                    package["size"],
                )
            if (
                package_cache_key is None
                or package_cache_key not in _validation_context.pinned_packages
            ):
                package_errors = verify_pinned_package(selection, core_id)
                errors.extend(package_errors)
                if package_cache_key is not None and not package_errors:
                    _validation_context.pinned_packages.add(package_cache_key)

        failure = core.get("failed_candidate")
        if failure is not None:
            if not isinstance(failure, dict):
                errors.append(f"{core_id}: failed candidate must be an object")
                continue
            if decision != "retain_parent":
                errors.append(f"{core_id}: failed candidate did not retain its parent")
            try:
                evidence_path = require_canonical_store_entry(
                    failure.get("record", {}), "e2e", f"{core_id} failed candidate"
                )
                if verify_store and (
                    not evidence_path.is_file()
                    or sha256_file(evidence_path) != failure.get("record", {}).get("sha256")
                ):
                    errors.append(f"{core_id}: failed-candidate evidence drift")
                elif verify_store:
                    evidence = load_json(evidence_path)
                    if (
                        evidence.get("result") != "failed"
                        or not evidence.get("local_only")
                        or evidence.get("publication") != "disabled"
                        or evidence.get("run_id") != failure.get("run_id")
                        or evidence.get("content_sha256")
                        != failure.get("content_sha256")
                        or evidence.get("content_sha256")
                        != e2e_content_sha256(evidence)
                    ):
                        errors.append(f"{core_id}: failed-candidate contract is invalid")
                    matching_packages = [
                        item
                        for item in evidence.get("packages", [])
                        if item.get("core_id") == core_id
                    ]
                    if (
                        len(matching_packages) != 1
                        or matching_packages[0].get("result") != "not_packaged"
                        or matching_packages[0].get("reason") != failure.get("reason")
                    ):
                        errors.append(
                            f"{core_id}: failed-candidate package evidence is not bound"
                        )
                    matching_builds = {}
                    for item in evidence.get("builds", []):
                        if item.get("core_id") != core_id:
                            continue
                        arch = item.get("architecture")
                        if arch in matching_builds:
                            errors.append(
                                f"{core_id}/{arch}: duplicate failed E2E build evidence"
                            )
                        else:
                            matching_builds[arch] = item
                    frozen_builds = failure.get("build_records", {})
                    if set(matching_builds) != set(frozen_builds):
                        errors.append(
                            f"{core_id}: failed-candidate build target set is not bound"
                        )
                    for arch, frozen in frozen_builds.items():
                        entry = matching_builds.get(arch, {})
                        record_entry = frozen.get("record", {})
                        if (
                            entry.get("result") != frozen.get("result")
                            or entry.get("record_sha256") != record_entry.get("sha256")
                        ):
                            errors.append(
                                f"{core_id}/{arch}: failed build record is not E2E-bound"
                            )
                        try:
                            record_path = require_canonical_store_entry(
                                record_entry,
                                "build-records",
                                f"{core_id}/{arch} failed build record",
                            )
                            if (
                                not record_path.is_file()
                                or sha256_file(record_path)
                                != record_entry.get("sha256")
                            ):
                                errors.append(
                                    f"{core_id}/{arch}: failed build record drift"
                                )
                                continue
                            record = load_json(record_path)
                            if (
                                record.get("core_id") != core_id
                                or record.get("architecture") != arch
                                or record.get("result") != frozen.get("result")
                                or not record.get("local_only")
                                or record.get("publication") != "disabled"
                            ):
                                errors.append(
                                    f"{core_id}/{arch}: failed build record identity is invalid"
                                )
                            expected_log_sha = record.get("build", {}).get("log_sha256")
                            log_entry = frozen.get("log")
                            if expected_log_sha and log_entry is None:
                                errors.append(
                                    f"{core_id}/{arch}: failed build log evidence is missing"
                                )
                            elif not expected_log_sha and log_entry is not None:
                                errors.append(
                                    f"{core_id}/{arch}: failed build log is not record-bound"
                                )
                            elif log_entry is not None:
                                log_path = require_canonical_store_entry(
                                    log_entry,
                                    "logs",
                                    f"{core_id}/{arch} failed build log",
                                )
                                if (
                                    log_entry.get("sha256") != expected_log_sha
                                    or not log_path.is_file()
                                    or sha256_file(log_path) != log_entry.get("sha256")
                                ):
                                    errors.append(
                                        f"{core_id}/{arch}: failed build log drift"
                                    )
                        except PipelineError as exc:
                            errors.append(str(exc))
            except PipelineError as exc:
                errors.append(str(exc))

    if summary.get("core_count") != len(cores):
        errors.append("summary.core_count does not match")
    if summary.get("retained_parent_count") != retained:
        errors.append("summary.retained_parent_count does not match")
    if summary.get("selected_source_count") != len(cores) - retained:
        errors.append("summary.selected_source_count does not match")
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def validate_pin_set_document(
    document: dict,
    *,
    verify_store: bool = False,
    verify_sources: bool = False,
    document_path: Path | None = None,
    _lineage_paths: tuple[Path, ...] = (),
    _lineage_identities: frozenset[tuple[str, str]] = frozenset(),
    _lineage_depth: int = 0,
    _validation_context: _PinValidationContext | None = None,
    historical_recipe_proofs: bool = False,
) -> dict:
    """Validate untrusted pin JSON without exposing shape exceptions."""

    try:
        return _validate_pin_set_document_impl(
            document,
            verify_store=verify_store,
            verify_sources=verify_sources,
            document_path=document_path,
            _lineage_paths=_lineage_paths,
            _lineage_identities=_lineage_identities,
            _lineage_depth=_lineage_depth,
            _validation_context=_validation_context,
            historical_recipe_proofs=historical_recipe_proofs,
        )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {
            "status": "invalid",
            "errors": [
                "pin set contains malformed nested data "
                f"({type(exc).__name__})"
            ],
        }


# CMake's Unix Makefiles generator prefixes each build line with a "[ NN%]"
# progress counter whose value depends on parallel completion order and is
# therefore not reproducible even when the produced objects are byte-identical.
# Reproduction proves the set of build actions, not this counter, so the prefix
# is normalized away before the log multiset comparison. The action identity
# ("Building <object>", "Linking ...") is preserved.
_CMAKE_PROGRESS_PREFIX_RE = re.compile(r"^\[ *[0-9]+%\] ")
# CMake also prints its own wall-clock step timings, e.g.
# "-- Configuring done (0.4s)" / "-- Generating done (0.3s)", which vary run to
# run without changing build identity; the duration is normalized to "(Ns)".
_CMAKE_STEP_TIMING_RE = re.compile(
    r"^(-- (?:Configuring|Generating) done) \([0-9]+(?:\.[0-9]+)?s\)"
)
# A verbose (-v) link makes gcc echo its collect2/lto-wrapper invocation, which
# names gcc's own intermediate files with a random 6-character mkstemp stem, e.g.
# "/tmp/ccgpIrkz.res" (the LTO symbol-resolution file). The stem varies run to
# run without changing build identity (the artifact stays byte-identical), so it
# is normalized to a fixed placeholder while keeping the extension.
_GCC_TEMP_FILE_RE = re.compile(r"/cc[A-Za-z0-9]{6}(\.[A-Za-z0-9]+)")
# cargo's completion line carries build wall-clock ("Finished `release`
# profile [optimized] target(s) in 14.05s"), which varies run to run while
# the compiled-crate set stays pinned by the cargo log contract.
_CARGO_FINISHED_TIME_RE = re.compile(
    r"^(\s+Finished `release` profile \[optimized\] target\(s\) in )\S+"
)
# CMake try_compile scratch targets are named cmTC_<random hex>; a VERBOSE
# configure embeds that name in build-command, object, and link lines, so two
# correct runs differ only by the random id.
_CMAKE_TRY_COMPILE_ID_RE = re.compile(r"\bcmTC_[0-9a-f]+\b")


def _reproduction_comparable_log_multiset(text: str) -> "Counter[str]":
    """Multiset of log lines with non-reproducible progress counters normalized."""

    return Counter(
        _CMAKE_TRY_COMPILE_ID_RE.sub(
            "cmTC_XXXXX",
            _GCC_TEMP_FILE_RE.sub(
                r"/ccXXXXXX\1",
                _CMAKE_STEP_TIMING_RE.sub(
                    r"\1 (Ns)",
                    _CARGO_FINISHED_TIME_RE.sub(
                        r"\1Ns",
                        _CMAKE_PROGRESS_PREFIX_RE.sub("[NN%] ", line),
                    ),
                ),
            ),
        )
        for line in text.splitlines(keepends=True)
    )


def _validate_canonical_compatibility_build_record(
    record: dict,
    record_path: Path,
    expected_target: dict,
    build_log_text: str,
) -> None:
    """Prove a canonical compatibility build against frozen and current gates.

    This deliberately does not compare the record with the current catalog,
    workflows, pipeline bytes, or toolchain files.  The selected pin binds a
    content-addressed recipe snapshot containing those historical bytes; both
    the selected and reproduction records must match that same snapshot.
    Canonical compatibility is also a current admission record, so it
    reapplies any registered core-owned log proof. A changed proof can require
    a new per-core compatibility successor without changing the immutable pin
    or legacy fixture.
    """

    expected_record = expected_target.get("golden_record")
    if not isinstance(expected_record, dict):
        raise PipelineError("compatibility expected build record is invalid")
    core_id = record.get("core_id")
    architecture = record.get("architecture")
    label = f"{core_id}/{architecture} compatibility build"
    required_keys = {
        "schema_version",
        "local_only",
        "publication",
        "started_at",
        "finished_at",
        "core_id",
        "architecture",
        "result",
        "build_exit_code",
        "source",
        "recipe",
        "toolchain",
        "build",
        "artifact",
        "metadata",
    }
    if set(record) != required_keys:
        raise PipelineError(f"{label}: build record fields are invalid")
    if (
        expected_record.get("core_id") != core_id
        or expected_record.get("architecture") != architecture
    ):
        raise PipelineError(f"{label}: promoted build identity differs")
    for field in (
        "source",
        "recipe",
        "toolchain",
        "artifact",
        "metadata",
    ):
        if record.get(field) != expected_record.get(field):
            raise PipelineError(f"{label}: historical {field} differs")

    build = record.get("build")
    expected_build = expected_record.get("build")
    if not isinstance(build, dict) or not isinstance(expected_build, dict):
        raise PipelineError(f"{label}: historical build differs")
    comparable_build = {
        key: value for key, value in build.items() if key != "log_sha256"
    }
    comparable_expected_build = {
        key: value
        for key, value in expected_build.items()
        if key != "log_sha256"
    }
    if comparable_build != comparable_expected_build:
        raise PipelineError(f"{label}: historical build differs")
    if build.get("log_sha256") != expected_build.get("log_sha256"):
        local_store = expected_record.get("local_store")
        build_logs = (
            local_store.get("build_logs")
            if isinstance(local_store, dict)
            else None
        )
        selected_log_reference = (
            build_logs.get(architecture)
            if isinstance(build_logs, dict)
            else None
        )
        if not isinstance(selected_log_reference, dict):
            raise PipelineError(f"{label}: historical build differs")
        selected_log_path = require_canonical_store_entry(
            selected_log_reference,
            "logs",
            f"{label} selected build log",
        )
        if (
            not selected_log_path.is_file()
            or selected_log_path.is_symlink()
            or selected_log_reference.get("sha256")
            != expected_build.get("log_sha256")
            or sha256_file(selected_log_path)
            != selected_log_reference.get("sha256")
        ):
            raise PipelineError(f"{label}: historical build differs")
        try:
            selected_log_text = selected_log_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise PipelineError(f"{label}: historical build differs") from exc
        if _reproduction_comparable_log_multiset(
            selected_log_text
        ) != _reproduction_comparable_log_multiset(build_log_text):
            raise PipelineError(f"{label}: historical build differs")

    recipe = record.get("recipe")
    if not isinstance(recipe, dict) or not pipeline_source_bundle_is_well_formed(
        recipe.get("pipeline_bundle")
    ):
        raise PipelineError(f"{label}: historical recipe bundle is invalid")
    pipeline_bundle = recipe["pipeline_bundle"]
    launcher_path = str(Path(__file__).relative_to(ROOT))
    if pipeline_bundle["files"].get(launcher_path) != recipe.get(
        "pipeline_sha256"
    ):
        raise PipelineError(f"{label}: historical recipe launcher is inconsistent")

    local_store = expected_record.get("local_store")
    snapshot_references = (
        local_store.get("recipe_snapshots")
        if isinstance(local_store, dict)
        else None
    )
    snapshot_reference = (
        snapshot_references.get(architecture)
        if isinstance(snapshot_references, dict)
        else None
    )
    if not isinstance(snapshot_reference, dict):
        raise PipelineError(f"{label}: promoted recipe snapshot is missing")
    snapshot_path = require_canonical_store_entry(
        snapshot_reference,
        "recipes",
        f"{label} recipe snapshot",
    )
    if (
        not snapshot_path.is_file()
        or snapshot_path.is_symlink()
        or sha256_file(snapshot_path) != snapshot_reference.get("sha256")
    ):
        raise PipelineError(f"{label}: promoted recipe snapshot bytes are invalid")
    snapshot_errors = verify_historical_recipe_snapshot(
        snapshot_path,
        record,
        label,
    )
    if snapshot_errors:
        raise PipelineError("\n- ".join(snapshot_errors))

    source = record.get("source")
    if not isinstance(build, dict) or not isinstance(source, dict):
        raise PipelineError(f"{label}: historical build/source contract is invalid")
    if core_id == MAME2003_PLUS_CORE_ID and (
        not mame2003_plus_golden_source_is_well_formed(core_id, source)
        or not mame2003_plus_golden_build_contract_is_well_formed(
            build,
            source.get("resolved_commit"),
            core_id,
            source,
            architecture,
        )
    ):
        raise PipelineError(f"{label}: MAME2003+ build/source contract is invalid")
    if core_id == FBNEO_CORE_ID and (
        not fbneo_golden_source_is_well_formed(core_id, source)
        or not fbneo_golden_build_contract_is_well_formed(
            build,
            source.get("resolved_commit"),
            core_id,
            source,
            architecture,
        )
    ):
        raise PipelineError(f"{label}: FBNeo build/source contract is invalid")
    if not compile_log_proves_definitions(
        build_log_text,
        build.get("compile_definitions"),
        architecture,
    ):
        raise PipelineError(f"{label}: compile-definition log proof failed")
    has_recipe_profile = "recipe_profile" in build
    if has_recipe_profile and (
        core_id != PICODRIVE_CORE_ID
        or not picodrive_golden_build_contract_is_well_formed(
            build,
            source.get("resolved_commit"),
            core_id,
            source,
            architecture,
        )
    ):
        raise PipelineError(f"{label}: recipe-profile contract is invalid")
    if core_id == PICODRIVE_CORE_ID and not has_recipe_profile:
        raise PipelineError(f"{label}: recipe-profile contract is missing")
    if "make_variables" in build and not make_variable_log_proves_contract(
        build_log_text,
        build["make_variables"],
        architecture,
    ):
        raise PipelineError(f"{label}: make-variable log proof failed")
    if "git_version" in build and not git_version_log_proves_contract(
        build_log_text,
        build["git_version"],
        source.get("resolved_commit"),
        architecture,
    ):
        raise PipelineError(f"{label}: Git-version log proof failed")
    log_contract = core_log_contract_for(core_id)
    if log_contract is not None and not registered_core_log_contract_proves(
        build_log_text,
        core_id,
        architecture,
        source.get("resolved_commit"),
        source.get("tree"),
    ):
        raise PipelineError(f"{label}: {log_contract.failure_message}")
    snapshot = load_json(snapshot_path)
    if build.get("driver") == "direct-cmake":
        files = snapshot.get("files")
        catalog_path = recipe.get("catalog_path")
        try:
            historical_catalog = json.loads(files[catalog_path]["text"])
            historical_spec = historical_catalog["cores"][core_id]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise PipelineError(
                f"{label}: historical direct-CMake recipe is invalid"
            ) from exc
        if not direct_cmake_log_proves_contract(
            build_log_text,
            historical_spec,
            architecture,
        ):
            raise PipelineError(f"{label}: direct-CMake log proof failed")
    metadata_replacement = build.get("metadata_replacement")
    if metadata_replacement is not None and not (
        metadata_replacement_log_proves_contract(
            build_log_text,
            metadata_replacement,
        )
    ):
        raise PipelineError(f"{label}: metadata-replacement log proof failed")


def _validate_compatibility_e2e_run(
    e2e_path: Path,
    core_id: str,
    expected_build_records: dict[str, dict],
) -> dict:
    """Validate canonical evidence against frozen recipes and current log gates."""

    expected_targets = set(expected_build_records)
    package_directories = {
        architecture: ARCH_LAYOUT[architecture]["package_directory"]
        for architecture in expected_targets
        if architecture in ARCH_LAYOUT
    }

    return validate_core_e2e_run(
        e2e_path,
        core_id,
        repository_root=ROOT,
        runs_root=DEFAULT_RUNS,
        expected_targets=expected_targets,
        package_directories=package_directories,
        expected_build_records=expected_build_records,
        artifact_validator=validate_artifact,
        build_record_validator=_validate_canonical_compatibility_build_record,
        content_hasher=e2e_content_sha256,
        runner_validator=runner_evidence_is_well_formed,
    )


def _validate_historical_pin_set_document(
    document: dict,
    **kwargs,
) -> dict:
    """Deeply validate a pin using its frozen recipe rather than current policy."""

    return validate_pin_set_document(
        document,
        historical_recipe_proofs=True,
        **kwargs,
    )


def validate_core_compatibility_document(
    document: dict,
    *,
    document_path: Path | None = None,
    repository_root: Path,
    verify_pin: bool = True,
) -> dict:
    """Inject the pipeline's deep pin and E2E validators."""

    return _validate_core_compatibility_document(
        document,
        document_path=document_path,
        repository_root=repository_root,
        verify_pin=verify_pin,
        pin_validator=_validate_historical_pin_set_document,
        e2e_validator=_validate_compatibility_e2e_run,
    )


def compose_pin_set(
    *,
    pin_id: str,
    core_ids: list[str],
    source_paths: list[Path],
    output_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict:
    """Create one canonical parentless pin for one individual core."""

    validation_context = _PinValidationContext()
    catalog = load_json(catalog_path)
    if (
        not isinstance(core_ids, list)
        or len(core_ids) != 1
        or not isinstance(core_ids[0], str)
        or CORE_ID_RE.fullmatch(core_ids[0]) is None
        or not isinstance(source_paths, list)
        or len(source_paths) != 1
        or not isinstance(source_paths[0], Path)
        or not isinstance(output_path, Path)
        or not isinstance(pin_id, str)
    ):
        raise PipelineError(
            "active pin composition requires exactly one core and one source"
        )
    core_id = core_ids[0]
    source_path = require_lexical_repository_path(
        source_paths[0], DEFAULT_NIGHTLIES, "individual pin source golden"
    )
    output_path = require_lexical_repository_path(
        output_path, DEFAULT_PIN_SET_DIR, "individual pin output"
    )
    source = load_json(source_path)
    report = validate_golden_document(source)
    if report["status"] == "valid":
        report["errors"].extend(verify_local_store(source, validation_context))
    if report["errors"]:
        raise PipelineError(
            f"golden source is invalid ({source_path}):\n- "
            + "\n- ".join(report["errors"])
        )
    require_active_core_golden(source, core_id)
    build_goldens = source.get("build_goldens")
    if not isinstance(build_goldens, dict) or set(build_goldens) != {core_id}:
        raise PipelineError(
            "active pin composition requires an exact one-core nightly golden"
        )
    selection = complete_core_bundle(source, core_id)
    if selection is None:
        raise PipelineError(f"no complete build-golden bundle is available for {core_id}")
    semantic_id = individual_core_semantic_id(core_id, selection)
    if pin_id != semantic_id:
        raise PipelineError(f"individual pin ID must be semantic ID {semantic_id}")
    expected_source = (DEFAULT_NIGHTLIES / semantic_id / "golden.json").resolve()
    expected_output = (DEFAULT_PIN_SET_DIR / f"{semantic_id}.json").resolve()
    if source_path != expected_source:
        raise PipelineError(
            "individual pin source must be its exact semantic nightly golden"
        )
    if output_path != expected_output:
        raise PipelineError(
            f"individual pin output must be pins/core-sets/{semantic_id}.json"
        )
    cores = {
        core_id: {
            "decision": "select_source",
            "source_index": 0,
            "selection": selection,
        }
    }
    candidate_pin = {"scope": [core_id], "cores": cores}
    require_pin_sources_eligible(catalog, candidate_pin)
    document = {
        "$schema": "../../manifests/core-set.schema.json",
        "schema_version": 1,
        "pin_id": pin_id,
        # The immutable pin derives its timestamp from its first immutable
        # source so recreating lost bytes cannot change a semantic ID's file.
        "created_at": source.get("updated_at"),
        "local_only": True,
        "publication": "disabled",
        "scope": [core_id],
        "parent": None,
        "sources": [golden_source_reference(source_path, source)],
        "selection_policy": copy.deepcopy(PIN_SELECTION_POLICY),
        "cores": cores,
        "summary": {
            "core_count": 1,
            "retained_parent_count": 0,
            "selected_source_count": 1,
        },
    }
    document["content_sha256"] = pin_set_content_sha256(document)
    report = validate_pin_set_document(
        document,
        verify_store=True,
        verify_sources=True,
        document_path=output_path,
        _validation_context=validation_context,
    )
    if report["status"] != "valid":
        raise PipelineError("composed pin set is invalid:\n- " + "\n- ".join(report["errors"]))
    atomic_create_json(output_path, document)
    return document


def validate_local_release(
    release_root: Path,
    pin: dict,
    pin_file_sha256: str,
    expected_release_id: str | None = None,
) -> dict:
    errors: list[str] = []
    release_root = require_lexical_repository_path(
        release_root, DEFAULT_RELEASES, "local release"
    )
    manifest_path = release_root / "release-manifest.json"
    try:
        manifest = load_json(manifest_path)
    except PipelineError as exc:
        return {"status": "invalid", "errors": [str(exc)]}
    if (
        manifest.get("schema_version") != 1
        or not manifest.get("local_only")
        or manifest.get("publication") != "disabled"
    ):
        errors.append("release manifest contract is invalid")
    expected_release_id = expected_release_id or release_root.name
    if (
        manifest.get("release_id") != expected_release_id
        or not isinstance(manifest.get("release_id"), str)
        or not LOCAL_ID_RE.fullmatch(manifest["release_id"])
    ):
        errors.append("release ID is invalid")
    if manifest.get("content_sha256") != release_content_sha256(manifest):
        errors.append("release content digest is invalid")
    expected_pin = {
        "pin_id": pin.get("pin_id"),
        "content_sha256": pin.get("content_sha256"),
        "file_sha256": pin_file_sha256,
    }
    if manifest.get("pin") != expected_pin:
        errors.append("release is not bound to the supplied pin")
    assets = manifest.get("assets", [])
    if not isinstance(assets, list):
        errors.append("release assets must be an array")
        assets = []
    expected_names = {"release-manifest.json"}
    seen_cores: set[str] = set()
    pin_cores = pin.get("cores")
    if not isinstance(pin_cores, dict):
        errors.append("release pin cores must be an object")
        pin_cores = {}
    pin_scope = pin.get("scope")
    if not isinstance(pin_scope, list) or any(
        not isinstance(core_id, str) for core_id in pin_scope
    ):
        errors.append("release pin scope must be an array of core IDs")
        pin_scope_set: set[str] | None = None
    else:
        pin_scope_set = set(pin_scope)
    for asset in assets:
        if not isinstance(asset, dict):
            errors.append("release asset must be an object")
            continue
        core_id = asset.get("core_id")
        name = asset.get("path")
        if (
            not isinstance(core_id, str)
            or CORE_ID_RE.fullmatch(core_id) is None
            or not isinstance(name, str)
            or core_id in seen_cores
            or name != f"{core_id}_libretro.zip"
        ):
            errors.append("release asset identity is invalid")
            continue
        seen_cores.add(core_id)
        expected_names.add(name)
        core_record = pin_cores.get(core_id)
        selection = (
            core_record.get("selection") if isinstance(core_record, dict) else None
        )
        if not isinstance(selection, dict):
            errors.append(f"{core_id}: release pin selection is invalid")
            continue
        package = selection.get("package")
        if not isinstance(package, dict):
            errors.append(f"{core_id}: release pin package is invalid")
            continue
        path = require_lexical_repository_path(
            release_root / name,
            release_root,
            f"{core_id} release asset",
        )
        if (
            asset.get("sha256") != package.get("sha256")
            or asset.get("size") != package.get("size")
            or asset.get("selection_sha256") != selection.get("selection_sha256")
            or asset.get("source_tier") != selection.get("tier")
            or not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != asset.get("size")
            or sha256_file(path) != asset.get("sha256")
        ):
            errors.append(f"{core_id}: released package differs from its pin")
    if pin_scope_set is not None and seen_cores != pin_scope_set:
        errors.append("release core scope does not match the pin")
    actual_names = {
        str(path.relative_to(release_root))
        for path in release_root.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual_names != expected_names:
        errors.append("release contains missing or unexpected files")
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def promote_local_release(
    pin_path: Path,
    output_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict:
    pin_path = require_lexical_repository_path(
        pin_path, DEFAULT_PIN_SET_DIR, "individual release pin"
    )
    output_path = require_lexical_repository_path(
        output_path, DEFAULT_RELEASES, "individual release output"
    )
    if not LOCAL_ID_RE.fullmatch(output_path.name):
        raise PipelineError("release directory name is invalid")
    pin = load_json(pin_path)
    report = validate_pin_set_document(
        pin,
        verify_store=True,
        verify_sources=True,
        document_path=pin_path,
    )
    if report["status"] != "valid":
        raise PipelineError("release pin is invalid:\n- " + "\n- ".join(report["errors"]))
    _core_id, semantic_id = require_individual_pin_identity(
        pin,
        pin_path=pin_path,
    )
    expected_output = (DEFAULT_RELEASES / semantic_id).resolve()
    if output_path != expected_output:
        raise PipelineError(
            f"individual release output must be .local-e2e/releases/{semantic_id}"
        )
    catalog = load_json(catalog_path)
    require_pin_sources_eligible(catalog, pin)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_lock(output_path):
        if output_path.exists():
            raise PipelineError(f"refusing to replace existing local release: {output_path}")
        temporary = Path(tempfile.mkdtemp(prefix=f".{output_path.name}.", dir=output_path.parent))
        try:
            assets = []
            for core_id in pin["scope"]:
                selection = pin["cores"][core_id]["selection"]
                package = selection["package"]
                source = require_canonical_store_entry(
                    package, "packages", f"{core_id} release source"
                )
                destination = safe_child(
                    temporary, package["name"], f"{core_id} release destination"
                )
                shutil.copyfile(source, destination)
                os.chmod(destination, 0o644)
                if (
                    destination.stat().st_size != package["size"]
                    or sha256_file(destination) != package["sha256"]
                ):
                    raise PipelineError(f"{core_id}: copied release package changed")
                assets.append(
                    {
                        "core_id": core_id,
                        "path": package["name"],
                        "sha256": package["sha256"],
                        "size": package["size"],
                        "source_tier": selection["tier"],
                        "selection_sha256": selection["selection_sha256"],
                    }
                )
            manifest = {
                "$schema": "../../../manifests/local-release.schema.json",
                "schema_version": 1,
                "release_id": output_path.name,
                # Releases are immutable views of the pin and inherit its
                # timestamp for deterministic byte-for-byte reconstruction.
                "created_at": pin.get("created_at"),
                "local_only": True,
                "publication": "disabled",
                "pin": {
                    "pin_id": pin["pin_id"],
                    "content_sha256": pin["content_sha256"],
                    "file_sha256": sha256_file(pin_path),
                },
                "assets": assets,
            }
            manifest["content_sha256"] = release_content_sha256(manifest)
            atomic_write_json(temporary / "release-manifest.json", manifest)
            validation = validate_local_release(
                temporary,
                pin,
                sha256_file(pin_path),
                expected_release_id=output_path.name,
            )
            if validation["status"] != "valid":
                raise PipelineError(
                    "staged local release is invalid:\n- "
                    + "\n- ".join(validation["errors"])
                )
            temporary.rename(output_path)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
    return manifest


def channel_pointer_path(channel: str, core_id: str | None = None) -> Path:
    if channel not in CHANNEL_KINDS:
        raise PipelineError(f"unknown local channel: {channel}")
    if core_id is not None and not CORE_ID_RE.fullmatch(core_id):
        raise PipelineError("individual channel core ID is invalid")
    filename = f"{channel}.{core_id}.json" if core_id else f"{channel}.json"
    try:
        relative = (DEFAULT_CHANNELS / filename).relative_to(ROOT)
    except ValueError as exc:
        raise PipelineError("channel pointer directory must be inside the repository") from exc
    return require_manifest_reference_path(
        {"path": str(relative)}, DEFAULT_CHANNELS, "channel pointer"
    )


def channel_target_root(channel: str) -> Path:
    if channel == "nightly":
        return DEFAULT_NIGHTLIES
    if channel == "pinned":
        return DEFAULT_PIN_SET_DIR
    if channel == "release":
        return DEFAULT_RELEASES
    raise PipelineError(f"unknown local channel: {channel}")


def resolve_release_pin(manifest: dict) -> tuple[dict, Path]:
    release_pin = manifest.get("pin")
    if not isinstance(release_pin, dict):
        raise PipelineError("release manifest pin identity is invalid")
    matches: list[tuple[dict, Path]] = []
    if DEFAULT_PIN_SET_DIR.is_dir():
        for candidate in sorted(DEFAULT_PIN_SET_DIR.glob("*.json")):
            if not candidate.is_file() or candidate.is_symlink():
                continue
            if sha256_file(candidate) != release_pin.get("file_sha256"):
                continue
            pin = load_json(candidate)
            try:
                require_individual_pin_identity(pin, pin_path=candidate)
            except PipelineError:
                continue
            if (
                pin.get("pin_id") == release_pin.get("pin_id")
                and pin.get("content_sha256") == release_pin.get("content_sha256")
            ):
                matches.append((pin, candidate))
    if len(matches) != 1:
        raise PipelineError(
            "release manifest must resolve exactly one immutable pin-set document"
        )
    return matches[0]


def derive_channel_target(
    channel: str,
    target_path: Path,
    _validation_context: _PinValidationContext | None = None,
    *,
    core_id: str | None = None,
) -> dict:
    if _validation_context is None:
        _validation_context = _PinValidationContext()
    kind = CHANNEL_KINDS.get(channel)
    if kind is None:
        raise PipelineError(f"unknown local channel: {channel}")
    target_path = require_lexical_repository_path(
        target_path,
        channel_target_root(channel),
        f"{channel} channel target",
    )
    relative = str(target_path.relative_to(ROOT))
    if not target_path.is_file() or target_path.is_symlink():
        raise PipelineError(f"{channel} channel target must be a regular file")
    if channel == "release" and target_path.name != "release-manifest.json":
        raise PipelineError("release channel target must be a release-manifest.json")

    before_sha256 = sha256_file(target_path)
    document = load_json(target_path)
    identity = (
        target_path.parent.name
        if channel == "nightly" and core_id is not None
        else document.get("release_id" if channel == "release" else "pin_id", "")
    )
    content_sha256 = document.get("content_sha256", "")
    preflight_errors = []
    if not isinstance(identity, str) or not LOCAL_ID_RE.fullmatch(identity):
        preflight_errors.append(f"{channel} channel target ID is invalid")
    if not isinstance(content_sha256, str) or not SHA256_RE.fullmatch(content_sha256):
        preflight_errors.append(f"{channel} channel target content digest is invalid")
    if preflight_errors:
        raise PipelineError(
            f"{channel} channel target is invalid:\n- " + "\n- ".join(preflight_errors)
        )
    if channel == "nightly":
        report = validate_golden_document(document)
        if report["status"] == "valid":
            report["errors"].extend(
                verify_local_store(document, _validation_context)
            )
        complete_bundle = None
        build_goldens = document.get("build_goldens")
        if core_id is not None and (
            not isinstance(build_goldens, dict)
            or set(build_goldens) != {core_id}
        ):
            report["errors"].append(
                "individual nightly channel target must contain exactly its core"
            )
        candidates = (
            (core_id,)
            if core_id is not None and isinstance(build_goldens, dict)
            else (build_goldens if isinstance(build_goldens, dict) else ())
        )
        for candidate_core_id in candidates:
            try:
                candidate_bundle = complete_core_bundle(document, candidate_core_id)
                if candidate_bundle is not None:
                    complete_bundle = candidate_bundle
                    break
            except PipelineError as exc:
                report["errors"].append(str(exc))
        if complete_bundle is None:
            report["errors"].append(
                (
                    f"nightly channel target has no complete {core_id} bundle"
                    if core_id is not None
                    else "nightly channel target has no complete build-golden bundle"
                )
            )
        elif core_id is not None:
            try:
                semantic_id = individual_core_semantic_id(
                    core_id, complete_bundle
                )
                if identity != semantic_id:
                    report["errors"].append(
                        "individual nightly channel target ID is not semantic"
                    )
            except PipelineError as exc:
                report["errors"].append(str(exc))
    elif channel == "pinned":
        report = validate_pin_set_document(
            document,
            verify_store=True,
            verify_sources=True,
            document_path=target_path,
            _validation_context=_validation_context,
        )
        if core_id is not None:
            try:
                pinned_core_id, semantic_id = require_individual_pin_identity(
                    document,
                    pin_path=target_path,
                )
                if pinned_core_id != core_id or identity != semantic_id:
                    report["errors"].append(
                        "individual pinned channel target identity differs"
                    )
            except PipelineError as exc:
                report["errors"].append(str(exc))
    else:
        pin, pin_path = resolve_release_pin(document)
        pin_report = validate_pin_set_document(
            pin,
            verify_store=True,
            verify_sources=True,
            document_path=pin_path,
            _validation_context=_validation_context,
        )
        report = validate_local_release(
            target_path.parent, pin, sha256_file(pin_path), expected_release_id=identity
        )
        report["errors"] = [*pin_report["errors"], *report["errors"]]
        if core_id is not None:
            try:
                released_core_id, semantic_id = require_individual_pin_identity(
                    pin,
                    pin_path=pin_path,
                )
                if released_core_id != core_id or identity != semantic_id:
                    report["errors"].append(
                        "individual release channel target identity differs"
                    )
            except PipelineError as exc:
                report["errors"].append(str(exc))

    canonical_relative = target_path.relative_to(channel_target_root(channel).resolve())
    if channel == "nightly" and (
        len(canonical_relative.parts) != 2
        or not LOCAL_ID_RE.fullmatch(canonical_relative.parts[0])
        or canonical_relative.parts[1] != "golden.json"
    ):
        report["errors"].append(
            "nightly channel target must be <nightly-id>/golden.json"
        )
    elif channel == "pinned" and canonical_relative.parts != (f"{identity}.json",):
        report["errors"].append("pinned channel target filename must match its pin ID")
    elif channel == "release" and canonical_relative.parts != (
        identity,
        "release-manifest.json",
    ):
        report["errors"].append(
            "release channel target directory must match its release ID"
        )
    after_sha256 = sha256_file(target_path)
    if after_sha256 != before_sha256:
        report["errors"].append(f"{channel} channel target changed during validation")
    if report["errors"]:
        raise PipelineError(
            f"{channel} channel target is invalid:\n- " + "\n- ".join(report["errors"])
        )
    return {
        "kind": kind,
        "path": relative,
        "id": identity,
        "file_sha256": after_sha256,
        "content_sha256": content_sha256,
    }


def validate_channel_pointer_document(
    document: dict,
    *,
    expected_channel: str | None = None,
    expected_core: str | None = None,
    verify_target: bool = True,
    _validation_context: _PinValidationContext | None = None,
) -> dict:
    if _validation_context is None:
        _validation_context = _PinValidationContext()
    errors: list[str] = []
    required_fields = {
        "$schema",
        "schema_version",
        "channel",
        "updated_at",
        "local_only",
        "publication",
        "target",
    }
    schema_version = document.get("schema_version")
    if schema_version == 2:
        required_fields.add("core_id")
    if set(document) != required_fields:
        errors.append("channel pointer fields are not exact")
    if document.get("$schema") != "../../manifests/channel-pointer.schema.json":
        errors.append("channel pointer schema reference is invalid")
    if type(schema_version) is not int or schema_version not in {1, 2}:
        errors.append("schema_version must be 1 or 2")
    if expected_core is None:
        if type(schema_version) is not int or schema_version != 1:
            errors.append("aggregate channel alias must use schema_version 1")
    elif type(schema_version) is not int or schema_version != 2:
        errors.append("individual channel alias must use schema_version 2")
    if document.get("local_only") is not True or document.get("publication") != "disabled":
        errors.append("channel pointer must be local-only and publication-disabled")
    channel = document.get("channel")
    if not isinstance(channel, str) or channel not in CHANNEL_KINDS:
        errors.append("channel is invalid")
    if expected_channel is not None and channel != expected_channel:
        errors.append("channel pointer document does not match its alias filename")
    core_id = document.get("core_id") if schema_version == 2 else None
    if schema_version == 2 and (
        not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None
    ):
        errors.append("individual channel core ID is invalid")
    if expected_core is not None and core_id != expected_core:
        errors.append("channel pointer document does not match its core alias filename")
    if expected_core is None and "core_id" in document:
        errors.append("aggregate channel pointer must not name a core")
    updated_at = document.get("updated_at")
    try:
        parsed_updated_at = dt.datetime.fromisoformat(updated_at)
        if parsed_updated_at.utcoffset() != dt.timedelta(0):
            raise ValueError
    except (TypeError, ValueError):
        errors.append("updated_at must be an aware UTC timestamp")

    target = document.get("target")
    target_fields = {"kind", "path", "id", "file_sha256", "content_sha256"}
    if not isinstance(target, dict) or set(target) != target_fields:
        errors.append("channel target fields are not exact")
        target = None
    elif isinstance(channel, str) and channel in CHANNEL_KINDS:
        if target.get("kind") != CHANNEL_KINDS[channel]:
            errors.append("channel target kind is invalid")
        if not isinstance(target.get("id"), str) or not LOCAL_ID_RE.fullmatch(
            target["id"]
        ):
            errors.append("channel target ID is invalid")
        if not isinstance(target.get("file_sha256"), str) or not SHA256_RE.fullmatch(
            target["file_sha256"]
        ):
            errors.append("channel target file digest is invalid")
        if not isinstance(
            target.get("content_sha256"), str
        ) or not SHA256_RE.fullmatch(target["content_sha256"]):
            errors.append("channel target content digest is invalid")
        if not isinstance(target.get("path"), str):
            errors.append("channel target path is invalid")
        else:
            try:
                target_path = require_manifest_reference_path(
                    target, channel_target_root(channel), f"{channel} channel target"
                )
                if verify_target:
                    if core_id is None:
                        derived = derive_channel_target(
                            channel, target_path, _validation_context
                        )
                    else:
                        derived = derive_channel_target(
                            channel,
                            target_path,
                            _validation_context,
                            core_id=core_id,
                        )
                    if target != derived:
                        errors.append("channel target identity no longer matches the pointer")
            except PipelineError as exc:
                errors.append(str(exc))
    return {"status": "valid" if not errors else "invalid", "errors": errors}


def require_channel_target_sources_eligible(
    catalog: dict,
    channel: str,
    target_path: Path,
    *,
    core_id: str | None = None,
) -> None:
    target_path = require_lexical_repository_path(
        target_path,
        channel_target_root(channel),
        f"{channel} channel target",
    )
    document = load_json(target_path)
    if channel == "nightly":
        if core_id is None:
            require_golden_sources_eligible(catalog, document)
        else:
            selection = complete_core_bundle(document, core_id)
            if selection is None:
                raise PipelineError(
                    f"nightly channel target has no complete {core_id} bundle"
                )
            require_source_commits_eligible(
                catalog,
                (
                    (core_id, target["golden_record"].get("source"))
                    for target in selection["targets"].values()
                ),
            )
    elif channel == "pinned":
        require_pin_sources_eligible(catalog, document)
    elif channel == "release":
        pin, _ = resolve_release_pin(document)
        require_pin_sources_eligible(catalog, pin)
    else:
        raise PipelineError(f"unknown local channel: {channel}")


def update_channel(
    channel: str,
    target_path: Path,
    *,
    core_id: str,
    expect_absent: bool = False,
    expect_current: str | None = None,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict:
    validation_context = _PinValidationContext()
    if expect_absent == (expect_current is not None):
        raise PipelineError(
            "exactly one of --expect-absent or --expect-current is required"
        )
    if expect_current is not None and not SHA256_RE.fullmatch(expect_current):
        raise PipelineError("--expect-current must be an exact SHA256")
    catalog = load_json(catalog_path)
    catalog_cores = catalog.get("cores")
    if not isinstance(catalog_cores, dict):
        raise PipelineError("catalog cores must be an object")
    if not isinstance(core_id, str) or CORE_ID_RE.fullmatch(core_id) is None:
        raise PipelineError("individual channel core ID is invalid")
    if core_id not in catalog_cores:
        raise PipelineError(f"individual channel core is not cataloged: {core_id}")
    pointer_path = channel_pointer_path(channel, core_id)
    with manifest_lock(pointer_path):
        current_document = None
        pointer_exists = pointer_path.exists() or pointer_path.is_symlink()
        if expect_absent:
            if pointer_exists:
                raise PipelineError(f"channel pointer already exists: {pointer_path}")
            current_sha256 = None
        else:
            if not pointer_exists or not pointer_path.is_file() or pointer_path.is_symlink():
                raise PipelineError(f"current channel pointer is unavailable: {pointer_path}")
            current_bytes = pointer_path.read_bytes()
            current_sha256 = sha256_bytes(current_bytes)
            if current_sha256 != expect_current:
                raise PipelineError(
                    f"channel compare-and-swap failed: expected {expect_current}, "
                    f"found {current_sha256}"
                )
            try:
                current_document = json.loads(current_bytes)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PipelineError("current channel pointer is not valid JSON") from exc
            if not isinstance(current_document, dict):
                raise PipelineError("current channel pointer must be a JSON object")
            current_report = validate_channel_pointer_document(
                current_document,
                expected_channel=channel,
                expected_core=core_id,
                _validation_context=validation_context,
            )
            if current_report["status"] != "valid":
                raise PipelineError(
                    "current channel pointer is invalid:\n- "
                    + "\n- ".join(current_report["errors"])
                )

        target = derive_channel_target(
            channel,
            target_path,
            validation_context,
            core_id=core_id,
        )
        if channel == "nightly":
            require_active_core_golden(load_json(target_path), core_id)
        require_channel_target_sources_eligible(
            catalog,
            channel,
            target_path,
            core_id=core_id,
        )
        if current_document is not None and current_document.get("target") == target:
            return {
                "status": "unchanged",
                "channel": channel,
                "pointer": str(pointer_path.relative_to(ROOT)),
                "pointer_file_sha256": current_sha256,
                "target": target,
            }
        document = {
            "$schema": "../../manifests/channel-pointer.schema.json",
            "schema_version": 2,
            "channel": channel,
            "core_id": core_id,
            "updated_at": utc_now(),
            "local_only": True,
            "publication": "disabled",
            "target": target,
        }
        report = validate_channel_pointer_document(
            document,
            expected_channel=channel,
            expected_core=core_id,
            _validation_context=validation_context,
        )
        if report["status"] != "valid":
            raise PipelineError(
                "new channel pointer is invalid:\n- " + "\n- ".join(report["errors"])
            )
        if current_sha256 is not None and sha256_file(pointer_path) != current_sha256:
            raise PipelineError("channel pointer changed during compare-and-swap")
        canonical_target = safe_child(ROOT, target["path"], f"{channel} channel target")
        if sha256_file(canonical_target) != target["file_sha256"]:
            raise PipelineError("channel target changed before pointer update")
        durable_atomic_channel_write(pointer_path, document, create=expect_absent)
        return {
            "status": "created" if expect_absent else "updated",
            "channel": channel,
            "pointer": str(pointer_path.relative_to(ROOT)),
            "pointer_file_sha256": sha256_file(pointer_path),
            "target": target,
        }


def require_empty_golden_slot(golden: dict, core_id: str, arch: str) -> None:
    if golden.get("build_goldens", {}).get(core_id, {}).get(arch) is not None:
        raise PipelineError(
            f"immutable build golden already exists for {core_id}/{arch}; create a new pin set"
        )


def require_active_candidate_golden_path(
    golden_path: Path,
    golden: dict,
) -> Path:
    """Bind a mutable working golden to its exact candidate identity."""

    golden_path = require_lexical_repository_path(
        golden_path,
        DEFAULT_NIGHTLIES,
        "active core candidate golden",
    )
    relative = golden_path.relative_to(DEFAULT_NIGHTLIES.resolve())
    core_id = golden.get("core_id")
    candidate_id = golden.get("pin_id")
    if (
        len(relative.parts) != 2
        or relative.parts[1] != "golden.json"
        or relative.parts[0] != candidate_id
        or not candidate_golden_id_is_well_formed(core_id, candidate_id)
    ):
        raise PipelineError(
            "active core candidate must be its exact "
            "<core>-candidate-<label>/golden.json path"
        )
    return golden_path


def promote_build_record(
    golden_path: Path,
    record_path: Path,
    e2e_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    store_root: Path = DEFAULT_STORE,
) -> dict:
    golden_path = require_lexical_repository_path(
        golden_path, DEFAULT_NIGHTLIES, "individual promotion golden"
    )
    record_path = require_lexical_repository_path(
        record_path, DEFAULT_RUNS, "build record"
    )
    e2e_path = require_lexical_repository_path(
        e2e_path, DEFAULT_RUNS, "E2E record"
    )
    catalog = load_catalog(catalog_path)
    candidate_record = load_json(record_path)
    require_source_commits_eligible(
        catalog,
        [(candidate_record.get("core_id"), candidate_record.get("source"))],
    )
    with manifest_lock(golden_path):
        return _promote_build_record_locked(
            golden_path, record_path, e2e_path, catalog_path, store_root
        )


def _promote_build_record_locked(
    golden_path: Path,
    record_path: Path,
    e2e_path: Path,
    catalog_path: Path = DEFAULT_CATALOG,
    store_root: Path = DEFAULT_STORE,
) -> dict:
    golden_path = require_lexical_repository_path(
        golden_path, DEFAULT_NIGHTLIES, "individual promotion golden"
    )
    record_path = require_lexical_repository_path(
        record_path, DEFAULT_RUNS, "build record"
    )
    e2e_path = require_lexical_repository_path(
        e2e_path, DEFAULT_RUNS, "E2E record"
    )
    store_root = require_contained(store_root, ROOT / ".local-e2e", "local store")
    catalog = load_catalog(catalog_path)
    candidate_record = load_json(record_path)
    require_source_commits_eligible(
        catalog,
        [(candidate_record.get("core_id"), candidate_record.get("source"))],
    )
    golden = load_json(golden_path)
    before = validate_golden_document(golden)
    if before["status"] != "valid":
        raise PipelineError("cannot promote into an invalid golden manifest")
    candidate_core_id = candidate_record.get("core_id")
    require_active_core_golden(golden, candidate_core_id)
    require_active_candidate_golden_path(golden_path, golden)
    build_goldens = golden.get("build_goldens")
    if (
        not isinstance(candidate_core_id, str)
        or not isinstance(build_goldens, dict)
        or set(build_goldens) - {candidate_core_id}
    ):
        raise PipelineError(
            "active promotion golden may contain build evidence for only one core"
        )
    (
        evidence,
        validated_e2e_sha,
        bound_records,
        package_path,
        package_record,
    ) = validate_e2e_evidence(
        e2e_path, record_path, catalog_path, catalog
    )
    record, record_path, _ = bound_records[load_json(record_path)["architecture"]]
    core_id = record["core_id"]
    arch = record["architecture"]
    require_empty_golden_slot(golden, core_id, arch)
    target_store: dict[str, dict[str, dict[str, str]]] = {
        name: {} for name in STORE_TARGET_EVIDENCE_NAMES
    }
    artifact_path: Path | None = None
    metadata_path: Path | None = None
    for target, (target_record, target_record_path, expected_record_sha) in bound_records.items():
        target_artifact, target_metadata, target_log = validate_build_record_identity(
            target_record, target_record_path, catalog_path, catalog
        )
        stored_record, stored_record_sha = store_file(
            store_root, "build-records", target_record_path
        )
        stored_log, stored_log_sha = store_file(store_root, "logs", target_log)
        stored_recipe, stored_recipe_sha = store_bytes(
            store_root, "recipes", recipe_snapshot(target_record)
        )
        if stored_record_sha != expected_record_sha:
            raise PipelineError(f"stored {target} build record changed after E2E validation")
        if stored_log_sha != target_record["build"]["log_sha256"]:
            raise PipelineError(f"stored {target} build log changed after E2E validation")
        target_store["build_records"][target] = {
            "path": str(stored_record.relative_to(ROOT)),
            "sha256": stored_record_sha,
        }
        target_store["build_logs"][target] = {
            "path": str(stored_log.relative_to(ROOT)),
            "sha256": stored_log_sha,
        }
        target_store["recipe_snapshots"][target] = {
            "path": str(stored_recipe.relative_to(ROOT)),
            "sha256": stored_recipe_sha,
        }
        if target == arch:
            artifact_path = target_artifact
            metadata_path = target_metadata
    if artifact_path is None or metadata_path is None:
        raise PipelineError("selected target evidence disappeared during promotion")
    artifact = record["artifact"]
    metadata = record["metadata"]
    recipe = record["recipe"]
    source = record["source"]
    toolchain = record["toolchain"]
    build = record["build"]
    stored_artifact, artifact_store_sha = store_file(store_root, "artifacts", artifact_path)
    stored_metadata, metadata_store_sha = store_file(store_root, "metadata", metadata_path)
    stored_e2e, e2e_store_sha = store_file(store_root, "e2e", e2e_path)
    stored_package, package_store_sha = store_file(store_root, "packages", package_path)
    if artifact_store_sha != artifact["sha256"]:
        raise PipelineError("stored artifact digest differs from validated artifact digest")
    if metadata_store_sha != metadata["sha256"]:
        raise PipelineError("stored metadata digest differs from its build record")
    if e2e_store_sha != validated_e2e_sha:
        raise PipelineError("stored E2E record changed after validation")
    if package_store_sha != package_record["sha256"]:
        raise PipelineError("stored E2E package changed after validation")
    promoted = {
        "core_id": core_id,
        "architecture": arch,
        "promotion_state": "build_golden",
        "promotion_reason": "initial-local-golden",
        "validation_scope": "static-build-only",
        "promoted_at": utc_now(),
        "local_record": str(record_path.relative_to(ROOT)),
        "source": source,
        "recipe": recipe,
        "toolchain": toolchain,
        "build": build,
        "artifact": artifact,
        "metadata": metadata,
        "e2e": {
            "run_id": evidence["run_id"],
            "record": str(e2e_path.relative_to(ROOT)),
            "record_sha256": e2e_store_sha,
            "content_sha256": evidence["content_sha256"],
            "package": str(package_path.relative_to(ROOT)),
            "package_sha256": package_store_sha,
            "build_records": {
                target: details["sha256"]
                for target, details in target_store["build_records"].items()
            },
        },
        "local_store": {
            "availability": "local-only",
            "artifact": {
                "path": str(stored_artifact.relative_to(ROOT)),
                "sha256": artifact_store_sha,
            },
            "metadata": {
                "path": str(stored_metadata.relative_to(ROOT)),
                "sha256": metadata_store_sha,
            },
            "e2e_record": {
                "path": str(stored_e2e.relative_to(ROOT)),
                "sha256": e2e_store_sha,
            },
            "package": {
                "path": str(stored_package.relative_to(ROOT)),
                "sha256": package_store_sha,
            },
            **target_store,
        },
    }
    if toolchain.get("archive_provenance") is not None:
        promoted["provenance_version"] = 2
    golden.setdefault("build_goldens", {}).setdefault(core_id, {})[arch] = promoted
    golden["content_sha256"] = golden_content_sha256(golden)
    golden["updated_at"] = utc_now()
    validation = validate_golden_document(golden)
    if validation["status"] != "valid":
        raise PipelineError("promotion would invalidate golden manifest:\n" + "\n".join(validation["errors"]))
    atomic_write_json(golden_path, golden)
    return promoted


def add_zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, data)


def package_e2e_core(
    run_root: Path, core_id: str, records: list[dict], spec: dict
) -> dict:
    expected_targets = set(spec["targets"])
    actual_targets = {record["architecture"] for record in records}
    if actual_targets != expected_targets:
        return {
            "core_id": core_id,
            "result": "not_packaged",
            "reason": "E2E target set is incomplete",
        }
    if not records or any(record["result"] != "passed" for record in records):
        return {"core_id": core_id, "result": "not_packaged", "reason": "target build failed"}
    metadata_records = [record.get("metadata", {}) for record in records]
    metadata_hashes = {item.get("sha256") for item in metadata_records}
    if (
        any(item.get("status") != "valid" for item in metadata_records)
        or len(metadata_hashes) != 1
    ):
        return {
            "core_id": core_id,
            "result": "not_packaged",
            "reason": "target metadata is missing or inconsistent",
        }
    metadata_replacement = validated_metadata_replacement(spec)
    if metadata_replacement is not None and any(
        not metadata_matches_replacement(metadata, metadata_replacement)
        for metadata in metadata_records
    ):
        return {
            "core_id": core_id,
            "result": "not_packaged",
            "reason": "target metadata does not match the catalog replacement",
        }
    package_path = run_root / f"{core_id}_libretro.zip"
    manifest = {
        "schema_version": 1,
        "local_only": True,
        "publication": "disabled",
        "core_id": core_id,
        "artifacts": {},
    }
    with zipfile.ZipFile(package_path, "w") as archive:
        for record in sorted(records, key=lambda item: item["architecture"]):
            arch = record["architecture"]
            source_path = run_root / core_id / arch / record["artifact"]["path"]
            member = f"{ARCH_LAYOUT[arch]['package_directory']}/{source_path.name}"
            add_zip_entry(archive, member, source_path.read_bytes())
            manifest["artifacts"][arch] = {
                "path": member,
                "sha256": record["artifact"]["sha256"],
                "source_commit": record["source"]["resolved_commit"],
                "toolchain_image_id": record["toolchain"]["resolved_image_id"],
            }
        metadata = metadata_records[0]
        metadata_path = run_root / core_id / records[0]["architecture"] / metadata["path"]
        metadata_name = spec["metadata"]["artifact_name"]
        add_zip_entry(archive, metadata_name, metadata_path.read_bytes())
        manifest["metadata"] = {
            "path": metadata_name,
            "sha256": metadata["sha256"],
        }
        add_zip_entry(
            archive,
            "manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
        )
    return {
        "core_id": core_id,
        "result": "packaged",
        "path": package_path.name,
        "sha256": sha256_file(package_path),
        "size": package_path.stat().st_size,
    }


def cmd_catalog_check(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    report = {
        "status": "valid",
        "catalog_cores": sorted(catalog["cores"]),
        "publication": catalog["policy"]["publication"],
    }
    if args.catalog.resolve() == DEFAULT_CATALOG.resolve():
        report.update(
            load_catalog_compatibility_coverage(
                catalog=catalog,
                repository_root=ROOT,
            )
        )
    print(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    report = audit_workflows(catalog)
    if args.output:
        atomic_write_json(args.output, report)
    summary = {key: value for key, value in report.items() if key != "workflows"}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return (
        1
        if report["missing_catalog_workflows"]
        or report["active_aggregate_workflows"]
        or report["invalid_catalog_workflows"]
        or report["release_orchestration"].get("status") != "valid"
        else 0
    )


def cmd_import_golden(args: argparse.Namespace) -> int:
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_NIGHTLIES,
        "individual imported golden output",
    )
    output_relative = output_path.relative_to(DEFAULT_NIGHTLIES.resolve())
    candidate_name = output_relative.parts[0] if output_relative.parts else ""
    if (
        len(output_relative.parts) != 2
        or output_relative.parts[1] != "golden.json"
        or not candidate_golden_id_is_well_formed(args.core, candidate_name)
    ):
        raise PipelineError(
            "individual imported golden output must be "
            "<core>-candidate-<label>/golden.json"
        )
    document = imported_core_baseline(
        args.spruceos,
        args.core,
        output_relative.parts[0],
    )
    report = validate_golden_document(document)
    missing_baseline_error = f"{args.core}: no valid imported artifact"
    validation_errors = report["errors"]
    tolerated_missing_baseline = (
        args.allow_missing
        and validation_errors == [missing_baseline_error]
        and document["summary"]["cores_without_valid_artifacts"] == [args.core]
    )
    if report["status"] != "valid" and not tolerated_missing_baseline:
        raise PipelineError(
            "individual imported golden is invalid:\n- "
            + "\n- ".join(validation_errors)
        )
    atomic_create_json(output_path, document)
    print(json.dumps(document["summary"], indent=2, sort_keys=True))
    return 0


def cmd_validate_golden(args: argparse.Namespace) -> int:
    document = load_json(args.golden)
    report = validate_golden_document(document, args.spruceos if args.verify_files else None)
    if args.verify_store:
        store_errors = verify_local_store(document)
        report["errors"].extend(store_errors)
        report["local_store"] = "valid" if not store_errors else "invalid"
        if store_errors:
            report["status"] = "invalid"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1


def cmd_build(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    record = perform_build(
        catalog_path=args.catalog,
        catalog=catalog,
        core_id=args.core,
        arch=args.arch,
        output_dir=args.output,
    )
    return 0 if record["result"] == "passed" else 1


def cmd_build_core(args: argparse.Namespace) -> int:
    """Build every catalog target and package exactly one selected core."""

    return cmd_e2e(
        argparse.Namespace(
            catalog=args.catalog,
            runner_profile=args.runner_profile,
            core=args.core,
            arch=None,
            run_id=args.run_id,
            output_root=args.output_root,
            fail_fast=True,
        )
    )


def cmd_e2e(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    if not isinstance(args.core, str) or not args.core:
        raise PipelineError("E2E requires exactly one --core")
    core_ids = [args.core]
    unknown = sorted(set(core_ids) - set(catalog["cores"]))
    if unknown:
        raise PipelineError(f"unknown core: {', '.join(unknown)}")
    requested_arches = args.arch
    if requested_arches:
        duplicate_arches = sorted(
            arch for arch, count in Counter(requested_arches).items() if count > 1
        )
        if duplicate_arches:
            raise PipelineError(
                "duplicate E2E architectures: " + ", ".join(duplicate_arches)
            )
    require_catalog_cores_eligible(catalog, core_ids)
    output_root = require_contained(args.output_root, ROOT / ".local-e2e", "E2E output root")
    repository_head = git_head(ROOT)
    repository_clean = not bool(
        run(
            ["git", "status", "--short", "--untracked-files=no"],
            cwd=ROOT,
        ).stdout
    )
    try:
        runner_context = resolve_runner_context(
            RunnerRequest(
                profile=args.runner_profile,
                repository_root=ROOT,
                output_root=output_root,
                run_id=args.run_id,
                repository_head=repository_head,
                repository_clean=repository_clean,
            ),
            env=os.environ,
        )
    except RunnerProfileError as exc:
        raise PipelineError(str(exc)) from exc
    run_id = runner_context.run_id
    run_root = runner_context.run_root
    if run_root.exists():
        raise PipelineError(f"refusing to reuse E2E run directory: {run_root}")
    run_root.mkdir(parents=True)
    audit = audit_workflows(catalog)
    records: list[dict] = []
    packages: list[dict] = []
    for core_id in core_ids:
        core_records = []
        targets = requested_arches or catalog["cores"][core_id]["targets"]
        for arch in targets:
            record = perform_build(
                catalog_path=args.catalog,
                catalog=catalog,
                core_id=core_id,
                arch=arch,
                output_dir=run_root / core_id / arch,
            )
            records.append(record)
            core_records.append(record)
            if args.fail_fast and record["result"] != "passed":
                break
        packages.append(
            package_e2e_core(run_root, core_id, core_records, catalog["cores"][core_id])
        )
        if args.fail_fast and any(item["result"] != "passed" for item in core_records):
            break
    result = (
        "passed"
        if records
        and all(item["result"] == "passed" for item in records)
        and all(item["result"] == "packaged" for item in packages)
        else "failed"
    )
    summary = {
        "schema_version": 2,
        "run_id": run_id,
        "local_only": True,
        "publication": "disabled",
        "runner": runner_evidence(runner_context),
        "result": result,
        "workflow_audit": {
            "core_workflow_count": audit["core_workflow_count"],
            "masked_build_failure_paths": audit["masked_build_failure_paths"],
            "info_only_risk_workflows": audit["info_only_risk_workflows"],
            "shared_pipeline_workflows": audit["shared_pipeline_workflows"],
        },
        "builds": [
            {
                "core_id": record["core_id"],
                "architecture": record["architecture"],
                "result": record["result"],
                "record": str(
                    (run_root / record["core_id"] / record["architecture"] / "build-record.json").relative_to(ROOT)
                ),
                "record_sha256": sha256_file(
                    run_root / record["core_id"] / record["architecture"] / "build-record.json"
                ),
            }
            for record in records
        ],
        "packages": packages,
    }
    summary["content_sha256"] = e2e_content_sha256(summary)
    atomic_write_json(run_root / "e2e-record.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if result == "passed" else 1


def cmd_promote(args: argparse.Namespace) -> int:
    promoted = promote_build_record(args.golden, args.record, args.e2e_record, args.catalog)
    print(json.dumps(promoted, indent=2, sort_keys=True))
    return 0


def cmd_derive_core_id(args: argparse.Namespace) -> int:
    result = derive_core_id(
        core_id=args.core,
        source_path=args.source_golden,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_compose_core_golden(args: argparse.Namespace) -> int:
    result = compose_core_golden(
        core_id=args.core,
        source_path=args.source_golden,
        output_path=args.output,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_compose_pin_set(args: argparse.Namespace) -> int:
    source_path = require_lexical_repository_path(
        args.source_golden,
        DEFAULT_NIGHTLIES,
        "individual pin source golden",
    )
    source = load_json(source_path)
    require_active_core_golden(source, args.core)
    build_goldens = source.get("build_goldens")
    if not isinstance(build_goldens, dict) or set(build_goldens) != {args.core}:
        raise PipelineError(
            "active pin composition requires an exact one-core nightly golden"
        )
    selection = complete_core_bundle(source, args.core)
    if selection is None:
        raise PipelineError(
            f"individual pin source has no complete {args.core} bundle"
        )
    semantic_id = individual_core_semantic_id(args.core, selection)
    if args.pin_id != semantic_id:
        raise PipelineError(f"--pin-id must be semantic ID {semantic_id}")
    expected_source = (DEFAULT_NIGHTLIES / semantic_id / "golden.json").resolve()
    if source_path != expected_source:
        raise PipelineError(
            "individual pin source path must use its exact semantic nightly ID"
        )
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_PIN_SET_DIR,
        "individual pin output",
    )
    expected_output = (DEFAULT_PIN_SET_DIR / f"{semantic_id}.json").resolve()
    if output_path != expected_output:
        raise PipelineError(
            f"individual pin output must be pins/core-sets/{semantic_id}.json"
        )
    document = compose_pin_set(
        pin_id=args.pin_id,
        core_ids=[args.core],
        source_paths=[source_path],
        output_path=output_path,
        catalog_path=args.catalog,
    )
    require_individual_pin_identity(document, pin_path=output_path)
    print(
        json.dumps(
            {
                "status": "created",
                "pin_id": document["pin_id"],
                "content_sha256": document["content_sha256"],
                **document["summary"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_validate_pin_set(args: argparse.Namespace) -> int:
    document = load_json(args.pin_set)
    report = validate_pin_set_document(
        document,
        verify_store=args.verify_store,
        verify_sources=args.verify_sources,
        document_path=args.pin_set,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1


def cmd_promote_release(args: argparse.Namespace) -> int:
    pin_path = require_lexical_repository_path(
        args.pin_set,
        DEFAULT_PIN_SET_DIR,
        "individual release pin",
    )
    pin = load_json(pin_path)
    _core_id, semantic_id = require_individual_pin_identity(
        pin,
        pin_path=pin_path,
    )
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_RELEASES,
        "individual release output",
    )
    expected_output = (DEFAULT_RELEASES / semantic_id).resolve()
    if output_path != expected_output:
        raise PipelineError(
            f"individual release output must be .local-e2e/releases/{semantic_id}"
        )
    manifest = promote_local_release(pin_path, output_path, args.catalog)
    print(
        json.dumps(
            {
                "status": "created",
                "release_id": manifest["release_id"],
                "content_sha256": manifest["content_sha256"],
                "asset_count": len(manifest["assets"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_validate_release(args: argparse.Namespace) -> int:
    pin = load_json(args.pin_set)
    pin_report = validate_pin_set_document(
        pin,
        verify_store=args.verify_store,
        verify_sources=True,
        document_path=args.pin_set,
    )
    if pin_report["status"] != "valid":
        report = {
            "status": "invalid",
            "errors": ["supplied pin set is invalid", *pin_report["errors"]],
        }
    else:
        report = validate_local_release(args.release, pin, sha256_file(args.pin_set))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1


def cmd_update_channel(args: argparse.Namespace) -> int:
    core_id = getattr(args, "core", None)
    if core_id is None:
        raise PipelineError("active channel mutation requires --core")
    result = update_channel(
        args.channel,
        args.target,
        core_id=core_id,
        expect_absent=args.expect_absent,
        expect_current=args.expect_current,
        catalog_path=args.catalog,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_validate_channel(args: argparse.Namespace) -> int:
    core_id = getattr(args, "core", None)
    if core_id is None:
        raise PipelineError("active channel validation requires --core")
    pointer_path = channel_pointer_path(args.channel, core_id)
    if not pointer_path.is_file() or pointer_path.is_symlink():
        raise PipelineError(f"channel pointer is unavailable: {pointer_path}")
    document = load_json(pointer_path)
    report = validate_channel_pointer_document(
        document,
        expected_channel=args.channel,
        expected_core=core_id,
    )
    details = {
        "channel": args.channel,
        "pointer": str(pointer_path.relative_to(ROOT)),
        "pointer_file_sha256": sha256_file(pointer_path),
    }
    if core_id is not None:
        details["core_id"] = core_id
    report.update(details)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "valid" else 1


def release_profile_report(source_set_path: str) -> dict:
    """Adapt the read-only profile registry to the pipeline error boundary."""

    try:
        return core_profile_registry.report_data(
            source_set_path=source_set_path,
            repo_root=ROOT,
        )
    except core_profile_registry.RegistryError as exc:
        raise PipelineError(f"profile registry error: {exc}") from exc


def release_repository_services() -> ReleaseRepositoryServices:
    """Return the launcher-owned validators used by release planning."""

    return ReleaseRepositoryServices(
        load_catalog=load_catalog,
        audit_workflows=audit_workflows,
        require_catalog_cores_eligible=require_catalog_cores_eligible,
        require_pin_sources_eligible=require_pin_sources_eligible,
        validate_pin_set=validate_pin_set_document,
        require_individual_pin_identity=require_individual_pin_identity,
        validate_compatibility=validate_core_compatibility_document,
        profile_report=release_profile_report,
        core_spec_sha256=core_spec_sha256,
    )


def release_worker_services() -> ReleaseWorkerServices:
    """Return the launcher-owned deep validators used by one worker."""

    return ReleaseWorkerServices(
        active_e2e_scope=active_promotion_e2e_scope,
        validate_e2e=validate_e2e_evidence,
    )


def _canonical_full_release_plan(path: Path) -> tuple[Path, dict]:
    plan_path = require_lexical_repository_path(
        path,
        DEFAULT_FULL_RELEASE_PLANS,
        "full-release plan",
    )
    plan = validate_release_plan(load_json(plan_path))
    expected = (DEFAULT_FULL_RELEASE_PLANS / f"{plan['candidate_id']}.json").resolve()
    if plan_path != expected:
        raise PipelineError(
            "full-release plan must be "
            f".local-e2e/release-plans/{plan['candidate_id']}.json"
        )
    return plan_path, plan


def cmd_plan_release(args: argparse.Namespace) -> int:
    scope = args.scope if args.scope is not None else "explicit"
    services = release_repository_services()
    plan = construct_tracked_release_plan(
        candidate_id=args.candidate_id,
        scope=scope,
        requested_cores=args.core,
        repository_root=ROOT,
        catalog_path=args.catalog,
        services=services,
    )
    output_path = require_lexical_repository_path(
        args.output,
        DEFAULT_FULL_RELEASE_PLANS,
        "full-release plan output",
    )
    expected = (
        DEFAULT_FULL_RELEASE_PLANS / f"{plan['candidate_id']}.json"
    ).resolve()
    if output_path != expected:
        raise PipelineError(
            "full-release plan output must be "
            f".local-e2e/release-plans/{plan['candidate_id']}.json"
        )
    with manifest_lock(output_path):
        write_release_plan(plan=plan, output_path=output_path)
    print(
        json.dumps(
            {
                "status": "planned",
                "candidate_id": plan["candidate_id"],
                "scope": plan["scope"],
                "core_count": plan["summary"]["core_count"],
                "target_count": plan["summary"]["target_count"],
                "content_sha256": plan["content_sha256"],
                "path": str(output_path.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_release_matrix(args: argparse.Namespace) -> int:
    """Print the exact one-core Actions matrix for a current release plan."""

    _, loaded_plan = _canonical_full_release_plan(args.plan)
    plan = validate_plan_against_repository(
        loaded_plan,
        repository_root=ROOT,
        catalog_path=args.catalog,
        services=release_repository_services(),
    )
    print(
        json.dumps(
            actions_matrix_for_plan(plan),
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def cmd_record_release_result(args: argparse.Namespace) -> int:
    plan_path, plan = _canonical_full_release_plan(args.plan)
    e2e_path = require_lexical_repository_path(
        args.e2e_record,
        DEFAULT_RUNS,
        "full-release worker E2E record",
    )
    runner_selector = runner_selector_for_contract(load_json(e2e_path).get("runner"))
    output_dir = require_lexical_repository_path(
        args.output_dir,
        DEFAULT_FULL_RELEASE_RESULTS,
        "full-release worker output",
    )
    expected = (
        DEFAULT_FULL_RELEASE_RESULTS
        / plan["candidate_id"]
        / runner_selector
        / args.core
    ).resolve()
    if output_dir != expected:
        raise PipelineError(
            "full-release worker output must be "
            ".local-e2e/release-results/"
            f"{plan['candidate_id']}/{runner_selector}/{args.core}"
        )
    with manifest_lock(output_dir):
        result, validated_runner = record_validated_release_result(
            plan_path=plan_path,
            core_id=args.core,
            e2e_path=e2e_path,
            output_dir=output_dir,
            repository_root=ROOT,
            catalog_path=args.catalog,
            repository_services=release_repository_services(),
            worker_services=release_worker_services(),
        )
    if validated_runner != runner_selector:
        raise AssertionError("release worker runner changed after deep validation")
    print(
        json.dumps(
            {
                "status": "recorded",
                "candidate_id": result["candidate_id"],
                "core_id": result["core_id"],
                "runner_profile": validated_runner,
                "content_sha256": result["content_sha256"],
                "path": str(output_dir.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_seal_release(args: argparse.Namespace) -> int:
    plan_path, loaded_plan = _canonical_full_release_plan(args.plan)
    plan = validate_plan_against_repository(
        loaded_plan,
        repository_root=ROOT,
        catalog_path=args.catalog,
        services=release_repository_services(),
    )
    results_root = require_lexical_repository_path(
        args.results_root,
        DEFAULT_FULL_RELEASE_RESULTS,
        "full-release result set",
    )
    expected_results = (
        DEFAULT_FULL_RELEASE_RESULTS
        / plan["candidate_id"]
        / args.runner_profile
    ).resolve()
    if results_root != expected_results:
        raise PipelineError(
            "full-release results root must be "
            ".local-e2e/release-results/"
            f"{plan['candidate_id']}/{args.runner_profile}"
        )
    output_dir = require_lexical_repository_path(
        args.output_dir,
        DEFAULT_FULL_RELEASE_CANDIDATES,
        "sealed full-release output",
    )
    expected_output = (
        DEFAULT_FULL_RELEASE_CANDIDATES
        / plan["candidate_id"]
        / args.runner_profile
    ).resolve()
    if output_dir != expected_output:
        raise PipelineError(
            "sealed full-release output must be "
            ".local-e2e/release-candidates/"
            f"{plan['candidate_id']}/{args.runner_profile}"
        )
    with manifest_lock(output_dir):
        candidate = seal_release_candidate(
            plan=plan,
            plan_path=plan_path,
            results_root=results_root,
            output_dir=output_dir,
            runner_selector=args.runner_profile,
        )
    print(
        json.dumps(
            {
                "status": "sealed",
                "candidate_id": candidate["candidate_id"],
                "runner_profile": args.runner_profile,
                "asset_count": candidate["summary"]["asset_count"],
                "asset_set_sha256": candidate["asset_set_sha256"],
                "content_sha256": candidate["content_sha256"],
                "path": str(output_dir.relative_to(ROOT)),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def path_value(value: str) -> Path:
    # Preserve lexical symlink components so contained-path validators can
    # reject them before any mutating command resolves the target.
    return Path(value).expanduser().absolute()


def build_parser() -> argparse.ArgumentParser:
    handlers = ParserHandlers(
        catalog_check=cmd_catalog_check,
        audit_workflows=cmd_audit,
        import_golden=cmd_import_golden,
        validate_golden=cmd_validate_golden,
        build=cmd_build,
        build_core=cmd_build_core,
        e2e=cmd_e2e,
        promote=cmd_promote,
        derive_core_id=cmd_derive_core_id,
        compose_core_golden=cmd_compose_core_golden,
        compose_pin_set=cmd_compose_pin_set,
        validate_pin_set=cmd_validate_pin_set,
        promote_release=cmd_promote_release,
        validate_release=cmd_validate_release,
        update_channel=cmd_update_channel,
        validate_channel=cmd_validate_channel,
        plan_release=cmd_plan_release,
        release_matrix=cmd_release_matrix,
        record_release_result=cmd_record_release_result,
        seal_release=cmd_seal_release,
    )
    config = ParserConfig(
        description=__doc__,
        path_value=path_value,
        default_catalog=DEFAULT_CATALOG,
        default_runs=DEFAULT_RUNS,
        default_spruceos=ROOT.parent / "spruceOS",
        arch_choices=tuple(sorted(ARCH_LAYOUT)),
        runner_profile_choices=(
            "local",
            "github-actions",
            "github-actions-sim",
        ),
        default_runner_profile="local",
        channel_choices=tuple(sorted(CHANNEL_KINDS)),
        release_scope_choices=("canonical", "full-workflow-roster"),
    )
    return build_cli_parser(handlers=handlers, config=config)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
