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
from types import ModuleType
from typing import NamedTuple
import copy
from contextlib import contextmanager
import datetime as dt
import io
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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
from core_pipeline_lib.source_candidate import (  # noqa: E402
    LEGACY_REUSABLE_REF_GENERATOR_SHA256,
    RECIPE_RISK_KEYS,
    SOURCE_KEYS,
    SourceCandidateContractProjection,
    prepare_source_candidate_catalog,
    prepare_source_snapshot_catalog_rebase,
    source_candidate_execution_spec,
    validated_source_candidate_contract_projection,
    validate_promoted_source_candidate_contract,
    validate_source_candidate_catalog,
)
from core_pipeline_lib.tracks import (  # noqa: E402
    CORE_TRACKS,
    TRACK_MARKERS,
    construct_core_track_inventory,
    load_core_pin_index,
    load_core_track_source_registry_index,
    local_git_source_ancestry_verifier,
    parse_group_tag,
    plan_core_track_test,
    promote_core_track_test,
    set_core_track_test,
    validate_core_tracks,
)
from core_pipeline_lib.chipsets import (  # noqa: E402
    CHIPSET_ARCHITECTURES,
    CHIPSETS,
    COMPILER_ARGUMENT_MAPPING_VERSION,
    REAL_CHIPSETS,
    resolved_tuning_profile,
    validate_chipset_tunings,
)
from core_pipeline_lib.errors import PipelineError  # noqa: E402
from core_pipeline_lib.foundation import (  # noqa: E402
    atomic_create_json,
    atomic_write_json,
    decode_json_object,
    durable_atomic_channel_write,
    load_json,
    load_json_with_sha256,
    manifest_lock as _foundation_manifest_lock,
    require_contained,
    require_manifest_reference_path as _foundation_manifest_reference_path,
    run,
    safe_child,
    sha256_bytes,
    sha256_file,
    utc_now,
)
from core_pipeline_lib.immutable_evidence import (  # noqa: E402
    canonical_store_path as _immutable_canonical_store_path,
    e2e_content_sha256 as _immutable_e2e_content_sha256,
    golden_content_sha256 as _immutable_golden_content_sha256,
    host_reproduction_content_sha256 as _immutable_host_reproduction_content_sha256,
    lexical_repository_relative_path as _immutable_lexical_path,
    pin_set_content_sha256 as _immutable_pin_set_content_sha256,
    release_content_sha256 as _immutable_release_content_sha256,
    require_canonical_store_entry as _immutable_require_canonical_store_entry,
    selection_content_sha256 as _immutable_selection_content_sha256,
    snapshot_json_file as _immutable_snapshot_json_file,
    store_bytes as _immutable_store_bytes,
    store_file as _immutable_store_file,
    toolchain_lock_content_sha256 as _immutable_toolchain_lock_content_sha256,
    verified_file_bytes as _immutable_verified_file_bytes,
    verified_json_object as _immutable_verified_json_object,
    verified_utf8_text as _immutable_verified_utf8_text,
)
from core_pipeline_lib import build_contracts as _build_contracts  # noqa: E402
from core_pipeline_lib import build_execution as _build_execution  # noqa: E402
from core_pipeline_lib import build_recipes as _build_recipes  # noqa: E402
from core_pipeline_lib import candidate_models as _candidate_models  # noqa: E402
from core_pipeline_lib import catalog_contracts as _catalog_contracts  # noqa: E402
from core_pipeline_lib import catalog_validation as _catalog_validation  # noqa: E402
from core_pipeline_lib.cli import catalog_build as _cli_catalog_build  # noqa: E402
from core_pipeline_lib.cli import track_commands as _cli_track_commands  # noqa: E402
from core_pipeline_lib.cli import promotion_commands as _cli_promotion_commands  # noqa: E402
from core_pipeline_lib.cli import full_release_commands as _cli_full_release_commands  # noqa: E402
from core_pipeline_lib import evidence_validation as _evidence_validation  # noqa: E402
from core_pipeline_lib import pipeline_inputs as _pipeline_inputs  # noqa: E402
from core_pipeline_lib import pin_lifecycle as _pin_lifecycle  # noqa: E402
from core_pipeline_lib import release_lifecycle as _release_lifecycle  # noqa: E402
from core_pipeline_lib import stored_evidence as _stored_evidence  # noqa: E402
from core_pipeline_lib.build_contracts import (  # noqa: E402
    ARCH_LAYOUT,
    COMBINED_NATIVE_MAKE_CORE_IDS,
    COMMAND_SCOPED_NATIVE_GIT_VERSION_COMMITS,
    COMPILE_DEFINITION_RE,
    CORE_ID_RE,
    DIRECT_CMAKE_RENAMED_TARGETS,
    ENVIRONMENT_SCOPED_NATIVE_GIT_VERSION_COMMITS,
    EXACT_GIT_VERSION_CORE_IDS,
    EXACT_NATIVE_GIT_DESCRIBE_CORE_IDS,
    EXACT_NATIVE_GIT_VERSION_CORE_IDS,
    EXACT_SOURCE_NATIVE_CORE_IDS,
    GENERATED_SOURCE_PATH_RE,
    GIT_VERSION_COMPILER_SCOPES,
    GIT_VERSION_CXX_SCOPE,
    GIT_VERSION_C_SCOPE,
    GIT_VERSION_DERIVATION,
    GIT_VERSION_RE,
    GL_DYNAREC_BUILD_KEYS,
    LOCAL_ID_RE,
    MAKEFLAGS_SCOPED_NATIVE_GIT_VERSION_COMMITS,
    MAX_SOURCE_DATE_EPOCH,
    NATIVE_GIT_DESCRIBE_COMPILE_MACROS_BY_COMMIT,
    NATIVE_GIT_DESCRIBE_DERIVATION,
    NATIVE_GIT_DESCRIBE_SPEC_IDENTITIES,
    NATIVE_GIT_DESCRIBE_VALUES_BY_COMMIT,
    NATIVE_GIT_MAKE_BUILD_KEYS,
    NATIVE_GIT_VERSION_C_SCOPE_CORE_IDS,
    NATIVE_GIT_VERSION_DERIVATION,
    NATIVE_GIT_VERSION_RE,
    NATIVE_GIT_VERSION_SHORT10_BUILD_KEYS,
    NATIVE_GIT_VERSION_SHORT10_DERIVATION,
    NATIVE_GIT_VERSION_SHORT10_RE,
    NATIVE_GIT_VERSION_SHORT10_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_SHORT8_DERIVATION,
    NATIVE_GIT_VERSION_SHORT9_DERIVATION,
    NATIVE_GIT_VERSION_SHORT9_RE,
    NATIVE_GIT_VERSION_SHORT9_SPEC_IDENTITIES,
    NATIVE_GIT_VERSION_SPEC_IDENTITIES,
    PORTABLE_FFMPEG_BUILD_KEYS,
    PORTABLE_FFMPEG_COMPILE_DEFINITIONS,
    PORTABLE_FFMPEG_FORBIDDEN_COMPILE_MACROS,
    PORTABLE_FFMPEG_MAKE_PROFILE,
    PORTABLE_FFMPEG_MAKE_VARIABLES,
    PORTABLE_FFMPEG_OVERLAY,
    PORTABLE_FFMPEG_OVERLAYS,
    RESERVED_MAKE_VARIABLE_NAMES,
    SHA1_RE,
    SHA256_RE,
    TARGET_CMAKE_TOOL_NAMES,
    UZEM_NATIVE_GIT_VERSION_BUILD_KEYS,
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
from core_pipeline_lib.contracts.c_asm import (  # noqa: E402
    c_asm_compile_invocation,
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
    HostExecutionProfile,
    HOST_EXECUTION_PROFILE_PATH,
    HOST_EXECUTION_PROFILE_SCHEMA_PATH,
    RAW_TELEMETRY_DIRECTORY,
    TELEMETRY_SCHEMA_PATH,
    TOOL_WRAPPER_SOURCE,
    UNIT_RUNNER_COMPILE_ARGUMENTS,
    UNIT_RUNNER_SOURCE,
    RunnerProfileError,
    RunnerRequest,
    base_runner_evidence,
    build_host_execution_contract,
    build_sidecar_document,
    execute_instrumented_container,
    instrumentation_shell_prelude,
    not_applicable_phase,
    parse_bootstrap_evidence,
    parse_measured_phase,
    parse_unit_evidence,
    phase_finish_shell,
    phase_start_shell,
    resolve_host_execution_profile,
    resolve_runner_context,
    runner_evidence,
    runner_evidence_is_hardened,
    runner_evidence_is_well_formed,
    unavailable_observation,
    validate_host_execution_contract,
    validate_job_count_log,
    validate_sidecar_reference,
    write_sidecar,
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
    prepare_release_source_graph,
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


def source_aware_candidate_contract_is_registered(core_id: str) -> bool:
    """Derive candidate eligibility from the live canonical log registry."""

    contract = core_log_contract_for(core_id)
    return bool(contract is not None and contract.proof_kind == "core-arch-source")


def metadata_replacement_contract_is_well_formed(value: object) -> bool:
    """Recognize one exact core-owned whole-file replacement contract."""

    return bool(
        vecx_metadata_replacement_contract_is_well_formed(value)
        or atari800_metadata_replacement_contract_is_well_formed(value)
        or picodrive_metadata_replacement_contract_is_well_formed(value)
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = ROOT / "manifests" / "core-builds.json"
DEFAULT_CORE_TRACKS = ROOT / "manifests" / "core-tracks.json"
DEFAULT_CHIPSET_TUNINGS = ROOT / "manifests" / "chipset-tunings.json"
DEFAULT_SPRUCE_RELEASE_ROSTER = ROOT / "manifests" / "spruce-release-roster.json"
DEFAULT_SPRUCE_BRANCH_BASES = (
    ROOT / "manifests" / "spruce-core-branch-bases.json"
)
DEFAULT_CORE_TRACK_SOURCE_REPOSITORIES = (
    ROOT / ".local-e2e" / "source-repositories"
)
DEFAULT_STORE = ROOT / ".local-e2e" / "store"
DEFAULT_RUNS = ROOT / ".local-e2e" / "runs"
DEFAULT_PIN_SET_DIR = ROOT / "pins" / "core-sets"
DEFAULT_RELEASES = ROOT / ".local-e2e" / "releases"
DEFAULT_FULL_RELEASE_PLANS = ROOT / ".local-e2e" / "release-plans"
DEFAULT_FULL_RELEASE_RESULTS = ROOT / ".local-e2e" / "release-results"
DEFAULT_FULL_RELEASE_CANDIDATES = ROOT / ".local-e2e" / "release-candidates"
DEFAULT_RELEASE_OVERLAY_INPUT = ROOT / ".local-e2e" / "overlay-input"
DEFAULT_RELEASE_OVERLAYS = ROOT / ".local-e2e" / "overlays"
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

    Lineage, path, and scope checks are intentionally not cached. Callers may
    reuse only exact, digest-verified byte snapshots and successful intrinsic
    proofs after the references have passed their normal validation in the
    current walk. Semantic decisions about a stored file must consume the
    cached snapshot rather than reopening its path.
    """

    def __init__(self) -> None:
        self.log_proofs: dict[
            tuple[str, str, str, str],
            tuple[bool, bool, bool, bool, bool, bool],
        ] = {}
        self.pinned_packages: set[tuple[str, str, str, str, int]] = set()
        self.verified_bytes: dict[tuple[str, str], bytes] = {}


_FACADE_REGISTRY: dict[
    str, tuple[str, tuple[tuple[str, str], ...], inspect.Signature]
] = {}


def _make_facade(
    public_name: str,
    leaf_module_name: str,
    injections: tuple[tuple[str, str], ...],
    public_signature: inspect.Signature,
) -> Callable[..., object]:
    """Close over immutable routing state without exposing control kwargs."""

    def facade(*args: object, **kwargs: object) -> object:
        public_signature.bind(*args, **kwargs)
        current_leaf = globals()[leaf_module_name]
        current_target = getattr(current_leaf, public_name)
        injected = {
            name: globals()[factory_name]()
            for name, factory_name in injections
        }
        return current_target(*args, **kwargs, **injected)

    return facade


def _install_facade_group(
    leaf_module_name: str,
    injections: tuple[tuple[str, str], ...],
    public_names: Iterable[str],
) -> None:
    """Install exact public facades with fresh call-time dependencies."""

    leaf_module = globals().get(leaf_module_name)
    if leaf_module is None:
        raise RuntimeError(f"unknown facade leaf module: {leaf_module_name}")
    injection_names = tuple(name for name, _factory in injections)
    if len(injection_names) != len(set(injection_names)):
        raise RuntimeError("duplicate facade injection name")
    for public_name in public_names:
        if public_name in _FACADE_REGISTRY:
            raise RuntimeError(f"duplicate facade registration: {public_name}")
        target = getattr(leaf_module, public_name, None)
        if not callable(target):
            raise RuntimeError(
                f"facade target is unavailable: {leaf_module_name}.{public_name}"
            )
        leaf_signature = inspect.signature(target)
        missing = set(injection_names).difference(leaf_signature.parameters)
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(
                f"facade {public_name} has unknown injections: {names}"
            )
        public_signature = leaf_signature.replace(
            parameters=[
                parameter
                for name, parameter in leaf_signature.parameters.items()
                if name not in injection_names
            ]
        )

        facade = _make_facade(
            public_name,
            leaf_module_name,
            injections,
            public_signature,
        )

        facade.__name__ = public_name
        facade.__qualname__ = public_name
        facade.__module__ = __name__
        facade.__doc__ = target.__doc__
        facade.__annotations__ = {
            name: annotation
            for name, annotation in target.__annotations__.items()
            if name not in injection_names
        }
        facade.__signature__ = public_signature
        globals()[public_name] = facade
        _FACADE_REGISTRY[public_name] = (
            leaf_module_name,
            injections,
            public_signature,
        )


def _pipeline_input_services() -> _pipeline_inputs.PipelineInputServices:
    """Capture verified input and recipe dependencies at call time."""

    return _pipeline_inputs.PipelineInputServices.from_namespace(globals())


def _build_contract_resolvers() -> _build_contracts.BuildContractResolvers:
    """Bind patchable launcher validators for one contract operation."""

    return _build_contracts.BuildContractResolvers(
        spec_validators={
            "fbneo_spec_is_well_formed": fbneo_spec_is_well_formed,
            "mame2003_plus_spec_is_well_formed": (
                mame2003_plus_spec_is_well_formed
            ),
            "mednafen_pcfx_spec_is_well_formed": (
                mednafen_pcfx_spec_is_well_formed
            ),
            "vecx_software_identity_is_well_formed": (
                vecx_software_identity_is_well_formed
            ),
            "picodrive_identity_is_well_formed": (
                picodrive_identity_is_well_formed
            ),
            "picodrive_recipe_profile_is_well_formed": (
                picodrive_recipe_profile_is_well_formed
            ),
            "native_git_version_spec_is_well_formed": (
                globals()['native_git_version_spec_is_well_formed']
            ),
            "native_git_version_short9_spec_is_well_formed": (
                globals()['native_git_version_short9_spec_is_well_formed']
            ),
            "native_git_version_short10_spec_is_well_formed": (
                globals()['native_git_version_short10_spec_is_well_formed']
            ),
            "native_git_describe_spec_is_well_formed": (
                globals()['native_git_describe_spec_is_well_formed']
            ),
            "parallel_n64_spec_is_well_formed": (
                parallel_n64_spec_is_well_formed
            ),
            "mupen64plus_next_spec_is_well_formed": (
                mupen64plus_next_spec_is_well_formed
            ),
        },
        git_version_validators={
            "fbneo_git_version_contract_is_well_formed": (
                fbneo_git_version_contract_is_well_formed
            ),
            "mame2003_plus_git_version_contract_is_well_formed": (
                mame2003_plus_git_version_contract_is_well_formed
            ),
        },
    )


def _build_contract_io() -> _build_contracts.BuildContractIO:
    """Bind repository-local, patchable I/O services for one operation."""

    return _build_contracts.BuildContractIO(
        repository_root=ROOT,
        reference_path=globals()['require_manifest_reference_path'],
        verified_text=globals()['verified_utf8_text'],
        run_command=run,
    )


MakeVariableProfileFacts = _build_contracts.MakeVariableProfileFacts
_make_variable_profile_facts = _build_contracts._make_variable_profile_facts
make_variable_profile = _build_contracts.make_variable_profile
make_variable_mapping_is_well_formed = (
    _build_contracts.make_variable_mapping_is_well_formed
)
make_variable_contract_name = _build_contracts.make_variable_contract_name


def _catalog_contract_services(
) -> _catalog_contracts.CatalogContractServices:
    """Capture catalog contract dispatch dependencies at call time."""

    return _catalog_contracts.CatalogContractServices.from_namespace(globals())


make_output_sync_prefix = _build_contracts.make_output_sync_prefix


validated_source_date_epoch = _build_contracts.validated_source_date_epoch


source_date_epoch_is_well_formed = (
    _build_contracts.source_date_epoch_is_well_formed
)


build_source_date_epoch_matches = (
    _build_contracts.build_source_date_epoch_matches
)


exact_relative_path = _build_contracts.exact_relative_path


validated_direct_cargo = _build_contracts.validated_direct_cargo


direct_cargo_contract_for_target = (
    _build_contracts.direct_cargo_contract_for_target
)


recorded_build_contract = _build_contracts.recorded_build_contract


validated_forbidden_needed_prefixes = (
    _build_contracts.validated_forbidden_needed_prefixes
)


forbidden_needed_dependencies = _build_contracts.forbidden_needed_dependencies


apply_artifact_dependency_policy = (
    _build_contracts.apply_artifact_dependency_policy
)


make_variable_golden_build_contract_is_well_formed = (
    _build_contracts.make_variable_golden_build_contract_is_well_formed
)


direct_cmake_golden_build_contract_is_well_formed = (
    _build_contracts.direct_cmake_golden_build_contract_is_well_formed
)


direct_cargo_golden_build_contract_is_well_formed = (
    _build_contracts.direct_cargo_golden_build_contract_is_well_formed
)


compile_definition_list_is_well_formed = (
    _build_contracts.compile_definition_list_is_well_formed
)


_compile_log_definition_proof = _build_contracts._compile_log_definition_proof


compile_log_proves_definitions = (
    _build_contracts.compile_log_proves_definitions
)


_chipset_tuning_log_proves_resolved = (
    _build_contracts._chipset_tuning_log_proves_resolved
)


core_contract_log_without_tuning_arguments = (
    _build_contracts.core_contract_log_without_tuning_arguments
)


make_variable_log_proves_contract = (
    _build_contracts.make_variable_log_proves_contract
)


def _catalog_validation_services(
) -> _catalog_validation.CatalogValidationServices:
    """Capture catalog, source, and artifact validators at call time."""

    return _catalog_validation.CatalogValidationServices.from_namespace(
        globals()
    )


def _candidate_model_services() -> _candidate_models.CandidateModelServices:
    """Capture tuning and reproduction model dependencies at call time."""

    return _candidate_models.CandidateModelServices.from_namespace(globals())


TUNING_CANDIDATE_SCOPE = _candidate_models.TUNING_CANDIDATE_SCOPE
TUNED_REPRODUCTION_SCOPE = _candidate_models.TUNED_REPRODUCTION_SCOPE
SOURCE_CANDIDATE_REPRODUCTION_SCOPE = (
    _candidate_models.SOURCE_CANDIDATE_REPRODUCTION_SCOPE
)
HOST_REPRODUCTION_SCOPE = _candidate_models.HOST_REPRODUCTION_SCOPE
TUNING_CANDIDATE_KEYS = _candidate_models.TUNING_CANDIDATE_KEYS
TUNING_CANDIDATE_REGISTRY_KEYS = (
    _candidate_models.TUNING_CANDIDATE_REGISTRY_KEYS
)
TUNING_PROFILE_KEYS = _candidate_models.TUNING_PROFILE_KEYS


def _build_recipe_services() -> _build_recipes.BuildRecipeServices:
    """Bind patchable launcher services for one recipe operation."""

    return _build_recipes.BuildRecipeServices(
        callables={
            "_make_variable_profile_facts": _make_variable_profile_facts,
            "_source_candidate_contract_spec": globals()['_source_candidate_contract_spec'],
            "atari800_metadata_replacement_contract_is_well_formed": (
                atari800_metadata_replacement_contract_is_well_formed
            ),
            "canonical_makeflags": globals()['canonical_makeflags'],
            "compile_definitions_for_target": globals()['compile_definitions_for_target'],
            "core_81_generated_version_shell": core_81_generated_version_shell,
            "direct_cargo_contract_for_target": direct_cargo_contract_for_target,
            "direct_cmake_contract_for_target": (
                globals()['direct_cmake_contract_for_target']
            ),
            "execution_tuning_profile": globals()['execution_tuning_profile'],
            "fbneo_build_shell": fbneo_build_shell,
            "fbneo_spec_is_well_formed": fbneo_spec_is_well_formed,
            "freeintv_spec_is_well_formed": freeintv_spec_is_well_formed,
            "git_version_markers": globals()['git_version_markers'],
            "instrumentation_shell_prelude": instrumentation_shell_prelude,
            "make_variable_markers": make_variable_markers,
            "make_variable_profile": make_variable_profile,
            "mame2003_plus_spec_is_well_formed": (
                mame2003_plus_spec_is_well_formed
            ),
            "mame2003_plus_build_shell": mame2003_plus_build_shell,
            "metadata_replacement_contract_is_well_formed": (
                metadata_replacement_contract_is_well_formed
            ),
            "native_git_version_spec_is_well_formed": (
                globals()['native_git_version_spec_is_well_formed']
            ),
            "phase_finish_shell": phase_finish_shell,
            "phase_start_shell": phase_start_shell,
            "picodrive_metadata_replacement_contract_is_well_formed": (
                picodrive_metadata_replacement_contract_is_well_formed
            ),
            "picodrive_recipe_shell": picodrive_recipe_shell,
            "sanitized_shell_prelude": globals()['sanitized_shell_prelude'],
            "snes9x2005_shell": snes9x2005_shell,
            "validated_git_version": globals()['validated_git_version'],
            "validated_make_variables": globals()['validated_make_variables'],
            "validated_metadata_replacement": globals()['validated_metadata_replacement'],
            "validated_recipe_profile": globals()['validated_recipe_profile'],
            "validated_source_date_epoch": validated_source_date_epoch,
            "vecx_metadata_replacement_contract_is_well_formed": (
                vecx_metadata_replacement_contract_is_well_formed
            ),
            "vemulator_spec_is_well_formed": vemulator_spec_is_well_formed,
        }
    )


def _build_recipe_io() -> _build_recipes.BuildRecipeIO:
    """Bind patchable repository I/O for one recipe operation."""

    return _build_recipes.BuildRecipeIO(
        repository_root=ROOT,
        reference_path=globals()['require_manifest_reference_path'],
        sha256_file=sha256_file,
        safe_child=safe_child,
    )


chipset_tuning_marker_shell = _build_recipes.chipset_tuning_marker_shell


make_variable_markers = _build_contracts.make_variable_markers


build_overlays_for_target = _build_recipes.build_overlays_for_target


overlay_git_apply_lines = _build_recipes.overlay_git_apply_lines



overlay_apply_shell = _build_recipes.overlay_apply_shell


repo_metadata = _build_recipes.repo_metadata


spec_submodules_recursive = _build_recipes.spec_submodules_recursive


spec_submodules_enabled = _build_recipes.spec_submodules_enabled


provenance_shell = _build_recipes.provenance_shell


checkout_shell = _build_recipes.checkout_shell


resolver_provenance_shell = _build_recipes.resolver_provenance_shell


SUBMODULE_STATUS_RE = _build_execution.SUBMODULE_STATUS_RE
PREFIXLESS_GITLINK_RE = _build_execution.PREFIXLESS_GITLINK_RE


def _build_execution_services() -> _build_execution.BuildExecutionServices:
    """Capture build planning and execution dependencies at call time."""

    return _build_execution.BuildExecutionServices.from_namespace(globals())


SOURCE_CANDIDATE_GIT_VERSION_TOKEN_RE = (
    _build_execution.SOURCE_CANDIDATE_GIT_VERSION_TOKEN_RE
)
GROUP_EXECUTION_SOURCE_KEYS = _build_execution.GROUP_EXECUTION_SOURCE_KEYS
GROUP_PIN_SOURCE_KEYS = _build_execution.GROUP_PIN_SOURCE_KEYS
GROUP_SUBMODULE_KEYS = _build_execution.GROUP_SUBMODULE_KEYS
GROUP_PIN_SUBMODULE_KEYS = _build_execution.GROUP_PIN_SUBMODULE_KEYS
GROUP_PIN_REFERENCE_KEYS = _build_execution.GROUP_PIN_REFERENCE_KEYS
GROUP_SOURCE_REF_RE = _build_execution.GROUP_SOURCE_REF_RE


def _evidence_validation_services(
) -> _evidence_validation.EvidenceValidationServices:
    """Capture the live evidence validator's exact call-time dependencies."""

    return _evidence_validation.EvidenceValidationServices.from_namespace(
        globals()
    )


def _stored_evidence_services() -> _stored_evidence.StoredEvidenceServices:
    """Capture the stored evidence verifier's exact call-time dependencies."""

    return _stored_evidence.StoredEvidenceServices.from_namespace(globals())


TUNED_BUILD_RECORD_KEYS = _evidence_validation.TUNED_BUILD_RECORD_KEYS
TUNED_E2E_KEYS = _evidence_validation.TUNED_E2E_KEYS
SOURCE_CANDIDATE_E2E_KEYS = _evidence_validation.SOURCE_CANDIDATE_E2E_KEYS
SOURCE_CANDIDATE_BUILD_RECORD_KEYS = (
    _evidence_validation.SOURCE_CANDIDATE_BUILD_RECORD_KEYS
)


def _pin_lifecycle_services() -> _pin_lifecycle.PinLifecycleServices:
    """Capture the pin lifecycle's exact call-time dependencies."""

    return _pin_lifecycle.PinLifecycleServices.from_namespace(globals())


def _release_lifecycle_services(
) -> _release_lifecycle.ReleaseLifecycleServices:
    """Capture the release lifecycle's exact call-time dependencies."""

    return _release_lifecycle.ReleaseLifecycleServices.from_namespace(
        globals()
    )


def _cli_catalog_build_services() -> _cli_catalog_build.CatalogBuildServices:
    """Capture catalog build dependencies at call time."""

    return _cli_catalog_build.CatalogBuildServices.from_namespace(globals())


def _cli_track_command_services() -> _cli_track_commands.TrackCommandServices:
    """Capture track commands dependencies at call time."""

    return _cli_track_commands.TrackCommandServices.from_namespace(globals())


def _cli_promotion_command_services() -> _cli_promotion_commands.PromotionCommandServices:
    """Capture promotion commands dependencies at call time."""

    return _cli_promotion_commands.PromotionCommandServices.from_namespace(globals())


def _cli_full_release_command_services() -> _cli_full_release_commands.FullReleaseCommandServices:
    """Capture full release commands dependencies at call time."""

    return _cli_full_release_commands.FullReleaseCommandServices.from_namespace(globals())



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
        load_catalog=globals()['load_catalog'],
        audit_workflows=globals()['audit_workflows'],
        require_catalog_cores_eligible=globals()['require_catalog_cores_eligible'],
        require_pin_sources_eligible=globals()['require_pin_sources_eligible'],
        validate_pin_set=globals()['validate_pin_set_document'],
        require_individual_pin_identity=globals()['require_individual_pin_identity'],
        validate_compatibility=globals()['validate_core_compatibility_document'],
        profile_report=release_profile_report,
        core_spec_sha256=globals()['core_spec_sha256'],
        group_execution_spec=globals()['_group_execution_spec'],
        load_core_pin_index=globals()['load_authoritative_core_pin_index'],
        resolve_core_group_build_selection=globals()['resolve_core_group_build_selection'],
    )


def release_worker_services() -> ReleaseWorkerServices:
    """Return the launcher-owned deep validators used by one worker."""

    return ReleaseWorkerServices(
        active_e2e_scope=active_promotion_e2e_scope,
        validate_e2e=globals()['validate_e2e_evidence'],
        validate_group_e2e=globals()['validate_group_e2e_evidence'],
    )


_install_facade_group(
    '_pipeline_inputs',
    (('services', '_pipeline_input_services'),),
    (
        'verified_file_bytes verified_json_object snapshot_json_file verified_utf8_text '
        'manifest_lock require_manifest_reference_path require_lexical_repository_path '
        'load_catalog_commit_blacklist require_source_commits_eligible '
        'require_catalog_cores_eligible require_pin_sources_eligible '
        'require_golden_sources_eligible toolchain_lock_content_sha256 '
        'load_toolchain_archive_validator load_catalog_toolchain_lock build_toolchain_key '
        'expected_archive_provenance golden_content_sha256 e2e_content_sha256 '
        'provenance_identity_sha256 selection_content_sha256 host_reproduction_content_sha256 '
        'pin_set_content_sha256 release_content_sha256 store_bytes store_file '
        '_host_store_reference prepare_host_execution_context canonical_store_path '
        'require_canonical_store_entry recipe_snapshot git_head core_workflows'
    ).split(),
)

_install_facade_group(
    '_build_contracts',
    (('resolvers', '_build_contract_resolvers'),),
    (
        'validated_compile_definitions compile_definitions_for_target'
    ).split(),
)

_install_facade_group(
    '_catalog_contracts',
    (('services', '_catalog_contract_services'),),
    (
        'native_git_version_spec_is_well_formed exact_native_git_version_contract '
        'native_git_version_short9_spec_is_well_formed '
        'native_git_version_short10_spec_is_well_formed native_git_describe_spec_is_well_formed '
        'exact_native_git_describe_contract uzem_native_git_version_spec_is_well_formed '
        'validated_make_variables git_version_contract_is_well_formed validated_git_version '
        'canonical_makeflags validated_recipe_profile metadata_matches_replacement '
        'validated_metadata_replacement generated_source_contract_is_well_formed '
        'validated_generated_source validate_build_overlays validated_direct_cmake '
        'direct_cmake_contract_for_target _source_candidate_contract_spec '
        'normalized_build_contract native_git_version_golden_source_is_well_formed '
        'native_git_describe_golden_source_is_well_formed '
        'uzem_native_golden_source_is_well_formed '
        'git_version_golden_build_contract_is_well_formed '
        'snes9x2005_plus_combined_golden_build_contract_is_well_formed '
        'combined_git_version_make_golden_build_contract_is_well_formed '
        'exact_native_golden_build_contract_is_well_formed chipset_tuning_log_proves_contract '
        'git_version_markers git_version_log_proves_contract read_build_log'
    ).split(),
)

_install_facade_group(
    '_catalog_validation',
    (('services', '_catalog_validation_services'),),
    (
        '_validate_catalog validate_catalog _validate_source_candidate_execution_catalog '
        'render_source_candidate_build_contract load_catalog_with_sha256 load_catalog '
        '_canonical_source_candidate_spec source_candidate_contract_context '
        '_recorded_source_matches_source_candidate_projection '
        '_source_candidate_contract_source_for_guard _source_candidate_contract_build_for_guard '
        'source_candidate_record_contract_projection '
        '_golden_source_candidate_contract_projection require_ordinary_promotion_catalog '
        'immutable_promotion_output_paths readelf_header defined_libretro_symbols '
        'validate_artifact _validate_artifact_bytes audit_workflows'
    ).split(),
)

_install_facade_group(
    '_candidate_models',
    (('services', '_candidate_model_services'),),
    (
        'imported_core_baseline verify_image sanitized_shell_prelude execution_tuning_profile '
        'resolve_tuning_candidate_selection validated_tuning_candidate_selection '
        'validated_tuning_candidate_shape tuning_candidate_recipe_identity '
        'validated_tuned_reproduction_shape _stored_reference_is_well_formed '
        'validated_embedded_source_candidate_shape validated_output_reproduction_shape '
        'host_reproduction_build_identity host_reproduction_build_content_sha256 '
        'host_reproduction_output_identity validated_host_reproduction_shape'
    ).split(),
)

_install_facade_group(
    '_build_recipes',
    (('services', '_build_recipe_services'),),
    (
        'compile_definition_shell direct_cmake_assembly_tuning_shell make_variable_log_markers '
        'command_scoped_native_git_version libretro_build_shell make_variable_shell '
        'git_version_log_markers source_identity_log_markers source_identity_shell '
        'git_version_shell source_date_epoch_shell source_date_epoch_provenance_shell '
        'direct_cmake_cache_log_document direct_cmake_log_markers '
        'direct_cmake_log_proves_contract metadata_replacement_container_path '
        'metadata_replacement_markers metadata_replacement_log_proves_contract '
        'metadata_install_shell recipe_profile_shell direct_cmake_overlay_shell '
        'direct_cmake_configure_shell instrumented_phase_shell container_build_script'
    ).split(),
)

_install_facade_group(
    '_build_recipes',
    (('io', '_build_recipe_io'),),
    (
        'overlay_mount_args direct_cmake_overlay_mount_args'
    ).split(),
)

_install_facade_group(
    '_build_recipes',
    (('services', '_build_recipe_services'), ('io', '_build_recipe_io')),
    (
        'metadata_replacement_mount_args'
    ).split(),
)

_install_facade_group(
    '_build_execution',
    (('services', '_build_execution_services'),),
    (
        'parse_submodule_provenance parse_submodules core_spec_sha256 recipe_record '
        '_core_log_contract_proofs _candidate_log_with_canonical_git_version_tokens '
        '_registered_core_log_contract_proves registered_core_log_contract_proves '
        '_group_submodule_path_is_safe pinned_group_execution_source '
        'validated_group_execution_source _validated_group_pin_reference '
        '_load_exact_group_pin_selection _source_candidate_group_recipe_projection '
        '_group_execution_spec group_execution_spec group_source_candidate_contract_projection '
        'resolve_core_group_build_selection _group_execution_tuning '
        'apply_group_output_expectations group_source_provenance_matches perform_build'
    ).split(),
)

_install_facade_group(
    '_evidence_validation',
    (('services', '_evidence_validation_services'),),
    (
        '_validate_build_record_identity validate_build_record_identity '
        '_require_public_ordinary_catalog validate_bound_host_telemetry '
        'require_host_execution_runner_coupling _validate_e2e_evidence validate_e2e_evidence '
        'validate_group_e2e_evidence validate_tuned_e2e_evidence '
        'tuned_candidate_output_identity tuned_candidate_build_identity '
        'require_selected_reproduction_runner_pair require_tuned_candidate_equivalence '
        'validate_source_candidate_e2e_evidence source_candidate_build_identity '
        'source_candidate_output_identity require_source_candidate_equivalence '
        'validate_host_reproduction_e2e_evidence require_host_reproduction_equivalence '
        'create_host_reproduction_proof'
    ).split(),
)

_install_facade_group(
    '_stored_evidence',
    (('services', '_stored_evidence_services'),),
    (
        '_validate_golden_document_impl validate_golden_document _verify_recipe_snapshot '
        'verify_recipe_snapshot _verify_historical_recipe_snapshot '
        'verify_historical_recipe_snapshot _verify_stored_e2e_bundle verify_stored_e2e_bundle '
        '_verify_tuned_reproduction_bundle verify_tuned_reproduction_bundle '
        '_verify_output_reproduction_bundle verify_output_reproduction_bundle '
        '_verify_host_reproduction_bundle verify_host_reproduction_bundle _verify_local_store '
        'verify_local_store golden_source_reference complete_core_bundle'
    ).split(),
)

_install_facade_group(
    '_pin_lifecycle',
    (('services', '_pin_lifecycle_services'),),
    (
        'individual_core_semantic_id require_individual_pin_identity '
        '_require_current_selection_source_authority '
        '_require_catalog_bound_source_candidate_selection inspect_individual_core_golden '
        'derive_core_id compose_core_golden freeze_failed_e2e _verify_pinned_package '
        'verify_pinned_package _validate_pin_set_document_impl _validate_pin_set_document '
        'validate_pin_set_document _require_pin_current_selection_authority '
        '_authoritative_core_track_pin_report authoritative_core_track_pin_report '
        'load_authoritative_core_pin_index core_track_source_ancestry_verifier '
        'release_source_graph_requirements prepare_release_group_source_graph '
        '_build_equivalence_identity _validate_canonical_compatibility_build_record '
        '_validate_compatibility_e2e_run _validate_historical_pin_set_document '
        'validate_core_compatibility_document compose_pin_set'
    ).split(),
)

_install_facade_group(
    '_release_lifecycle',
    (('services', '_release_lifecycle_services'),),
    (
        '_validate_local_release validate_local_release promote_local_release '
        'channel_pointer_path channel_target_root _resolve_release_pin resolve_release_pin '
        '_derive_channel_target derive_channel_target _validate_channel_pointer_document '
        'validate_channel_pointer_document _require_channel_target_sources_eligible '
        'require_channel_target_sources_eligible update_channel require_empty_golden_slot '
        'require_active_candidate_golden_path promote_build_record _promote_build_record_locked '
        '_store_reference promote_tuned_variant promote_source_candidate '
        'promote_host_reproduction add_zip_entry package_e2e_core'
    ).split(),
)

_install_facade_group(
    '_cli_catalog_build',
    (('services', '_cli_catalog_build_services'),),
    (
        'cmd_catalog_check cmd_core_source_candidate_rebase cmd_core_source_candidate_prepare '
        'cmd_audit cmd_import_golden cmd_validate_golden cmd_build cmd_build_core cmd_e2e'
    ).split(),
)

_install_facade_group(
    '_cli_track_commands',
    (('services', '_cli_track_command_services'),),
    (
        'cmd_core_track_inventory _canonical_core_track_json_bytes '
        '_atomic_create_core_track_snapshot _atomic_restore_core_track_bytes '
        '_durably_remove_owned_core_track_snapshot _rollback_core_track_registry_transaction '
        '_commit_core_track_registry_transaction cmd_core_track_promote '
        'cmd_core_track_plan_test cmd_core_track_set_test'
    ).split(),
)

_install_facade_group(
    '_cli_promotion_commands',
    (('services', '_cli_promotion_command_services'),),
    (
        'cmd_promote cmd_promote_host_reproduction cmd_promote_source_candidate '
        'cmd_promote_tuned_variant cmd_derive_core_id cmd_compose_core_golden '
        'cmd_compose_pin_set cmd_validate_pin_set cmd_promote_release cmd_validate_release '
        'cmd_update_channel cmd_validate_channel'
    ).split(),
)

_install_facade_group(
    '_cli_full_release_commands',
    (('services', '_cli_full_release_command_services'),),
    (
        '_canonical_full_release_plan cmd_prepare_release_source_graph '
        'cmd_convert_release_overlay cmd_plan_release cmd_release_matrix '
        'cmd_record_release_result cmd_seal_release'
    ).split(),
)


def path_value(value: str) -> Path:
    # Preserve lexical symlink components so contained-path validators can
    # reject them before any mutating command resolves the target.
    return Path(value).expanduser().absolute()


def build_parser() -> argparse.ArgumentParser:
    handlers = ParserHandlers(
        catalog_check=globals()['cmd_catalog_check'],
        core_source_candidate_rebase=globals()['cmd_core_source_candidate_rebase'],
        core_source_candidate_prepare=globals()['cmd_core_source_candidate_prepare'],
        core_track_inventory=globals()['cmd_core_track_inventory'],
        core_track_promote=globals()['cmd_core_track_promote'],
        core_track_plan_test=globals()['cmd_core_track_plan_test'],
        core_track_set_test=globals()['cmd_core_track_set_test'],
        audit_workflows=globals()['cmd_audit'],
        import_golden=globals()['cmd_import_golden'],
        validate_golden=globals()['cmd_validate_golden'],
        build=globals()['cmd_build'],
        build_core=globals()['cmd_build_core'],
        e2e=globals()['cmd_e2e'],
        promote=globals()['cmd_promote'],
        promote_host_reproduction=globals()['cmd_promote_host_reproduction'],
        promote_source_candidate=globals()['cmd_promote_source_candidate'],
        promote_tuned_variant=globals()['cmd_promote_tuned_variant'],
        derive_core_id=globals()['cmd_derive_core_id'],
        compose_core_golden=globals()['cmd_compose_core_golden'],
        compose_pin_set=globals()['cmd_compose_pin_set'],
        validate_pin_set=globals()['cmd_validate_pin_set'],
        promote_release=globals()['cmd_promote_release'],
        validate_release=globals()['cmd_validate_release'],
        update_channel=globals()['cmd_update_channel'],
        validate_channel=globals()['cmd_validate_channel'],
        prepare_release_source_graph=globals()['cmd_prepare_release_source_graph'],
        convert_release_overlay=globals()['cmd_convert_release_overlay'],
        plan_release=globals()['cmd_plan_release'],
        release_matrix=globals()['cmd_release_matrix'],
        record_release_result=globals()['cmd_record_release_result'],
        seal_release=globals()['cmd_seal_release'],
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


# These compatibility exports depend on services defined throughout this
# composition root, so bind them only after every facade exists.
for _proof_name, _proof in globals()['_core_log_contract_proofs']().items():
    globals().setdefault(_proof_name, _proof)
del _proof_name, _proof


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
