"""Exact Mednafen Supafaust C++ build-log contract."""

from __future__ import annotations

from collections import Counter
import re

from .mixed_language import (
    MixedLanguageLogContract,
    mixed_language_log_proves_contract,
)


MEDNAFEN_SUPAFAUST_CORE_ID = "mednafen_supafaust"
MEDNAFEN_SUPAFAUST_EXPECTED_COMPILE_COUNT = 44
MEDNAFEN_SUPAFAUST_EXPECTED_LANGUAGE_COUNTS = {"cxx": 44}
MEDNAFEN_SUPAFAUST_EXPECTED_COMPILE_PAIR_SHA256 = (
    "7dd41788976cdf6d1565bd301f04be1d597e191156f9cf48a4707a55ce204451"
)
MEDNAFEN_SUPAFAUST_EXPECTED_COMPILE_INVOCATION_SHA256 = {
    "arm64": "0d29c247ec1558f6267ee2c2028a4865b7311d15ea46bf1527f7170b8dba8fa7",
    "armhf": "2c37be190952b0e69b240d8cbde7a15a412fb8f594e2f2d79de905c4021fa476",
}
MEDNAFEN_SUPAFAUST_EXPECTED_LINK_OBJECT_SHA256 = (
    "b857c8382f4199eb69efdbe0006bdd103e89e7a991562040893a820aa595b4a9"
)
MEDNAFEN_SUPAFAUST_EXPECTED_RAW_LINK_OBJECT_SHA256 = (
    "b857c8382f4199eb69efdbe0006bdd103e89e7a991562040893a820aa595b4a9"
)
MEDNAFEN_SUPAFAUST_BUILD_ARTIFACT_NAME = (
    "mednafen_supafaust_libretro.so"
)
MEDNAFEN_SUPAFAUST_EXPECTED_LINK_OPTIONS = (
    "-pthread",
    "-lpthread",
    "-fPIC",
    "-shared",
    "-Wl,--no-undefined",
    "-Wl,--version-script=link.T",
)
MEDNAFEN_SUPAFAUST_MAKE_FAILURE_RE = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*", re.IGNORECASE | re.MULTILINE
)


def _diagnostic_block(headline: str, source_line: str, marker_line: str) -> str:
    return "\n".join((headline, source_line, marker_line))


def _diagnostic_context_lines_are_exact(
    build_log_text: str,
    expected_context_blocks: tuple[str, ...],
) -> bool:
    """Match an exact shuffle of ordered parallel diagnostic streams."""

    expected_streams = tuple(
        tuple(block.splitlines()) for block in expected_context_blocks
    )
    expected_lines = Counter(
        line for stream in expected_streams for line in stream
    )
    actual_lines = tuple(
        line
        for line in build_log_text.splitlines()
        if line in expected_lines
    )
    if Counter(actual_lines) != expected_lines:
        return False

    states = {tuple(0 for _stream in expected_streams)}
    for line in actual_lines:
        next_states: set[tuple[int, ...]] = set()
        for state in states:
            for stream_index, stream in enumerate(expected_streams):
                position = state[stream_index]
                if position >= len(stream) or stream[position] != line:
                    continue
                advanced = list(state)
                advanced[stream_index] += 1
                next_states.add(tuple(advanced))
        if not next_states:
            return False
        states = next_states
    return any(
        all(
            position == len(expected_streams[index])
            for index, position in enumerate(state)
        )
        for state in states
    )


MEDNAFEN_SUPAFAUST_MTHREAD_WARNING_BLOCK = _diagnostic_block(
    "mednafen/mthreading/MThreading_POSIX.cpp:571:2: warning: #warning "
    '"Using realtime-clock-based sem_timedwait()" [-Wcpp]',
    '  571 | #warning "Using realtime-clock-based sem_timedwait()"',
    "      |  ^~~~~~~",
)
MEDNAFEN_SUPAFAUST_SPC700_WARNING_BLOCK = _diagnostic_block(
    "mednafen/snes_faust/spc700.inc:23:3: warning: #warning "
    '"Compiling with sketchy SPC700 optimization." [-Wcpp]',
    '   23 |  #warning "Compiling with sketchy SPC700 optimization."',
    "      |   ^~~~~~~",
)
MEDNAFEN_SUPAFAUST_OWL_WARNING_BLOCKS = (
    _diagnostic_block(
        "mednafen/sound/OwlResampler.cpp:507:7: warning: unused variable "
        "'a' [-Wunused-variable]",
        "  507 |   int a = SDP2<int32, 3>(i);",
        "      |       ^",
    ),
    _diagnostic_block(
        "mednafen/sound/OwlResampler.cpp:508:7: warning: unused variable "
        "'b' [-Wunused-variable]",
        "  508 |   int b = SDP2<int32, 3>(-i);",
        "      |       ^",
    ),
    _diagnostic_block(
        "mednafen/sound/OwlResampler.cpp:509:7: warning: unused variable "
        "'c' [-Wunused-variable]",
        "  509 |   int c = i / (1 << 3);",
        "      |       ^",
    ),
    _diagnostic_block(
        "mednafen/sound/OwlResampler.cpp:528:10: warning: variable 'ratio' "
        "set but not used [-Wunused-but-set-variable]",
        "  528 |   double ratio = (double)output_rate / input_rate;",
        "      |          ^~~~~",
    ),
    _diagnostic_block(
        "mednafen/sound/OwlResampler.cpp:524:15: warning: unused variable "
        "'cpuext' [-Wunused-variable]",
        "  524 |  const uint32 cpuext = cputest_get_flags();",
        "      |               ^~~~~~",
    ),
)
MEDNAFEN_SUPAFAUST_ARM64_STATE_WARNING_BLOCK = _diagnostic_block(
    "/usr/aarch64-linux-gnu/include/bits/string_fortified.h:106:34: warning: "
    "'char* __builtin_strncpy(char*, const char*, long unsigned int)' "
    "specified bound 32 equals destination size [-Wstringop-truncation]",
    "  106 |   return __builtin___strncpy_chk (__dest, __src, __len, __bos (__dest));",
    "      |          ~~~~~~~~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
)
MEDNAFEN_SUPAFAUST_ARMHF_NO_SIMD_WARNING_BLOCK = _diagnostic_block(
    "mednafen/sound/OwlResampler.cpp:694:4: warning: #warning "
    '"OwlResampler is being compiled without SIMD support." [-Wcpp]',
    '  694 |   #warning "OwlResampler is being compiled without SIMD support."',
    "      |    ^~~~~~~",
)
MEDNAFEN_SUPAFAUST_ARMHF_STATE_WARNING_BLOCK = _diagnostic_block(
    "mednafen/state.cpp:411:12: warning: 'char* strncpy(char*, const char*, "
    "size_t)' specified bound 32 equals destination size "
    "[-Wstringop-truncation]",
    "  411 |     strncpy((char *)sname_tmp, sname, 32);",
    "      |     ~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
)
MEDNAFEN_SUPAFAUST_EXPECTED_WARNING_BLOCKS = {
    "arm64": (
        MEDNAFEN_SUPAFAUST_MTHREAD_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_SPC700_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_ARM64_STATE_WARNING_BLOCK,
        *MEDNAFEN_SUPAFAUST_OWL_WARNING_BLOCKS,
    ),
    "armhf": (
        MEDNAFEN_SUPAFAUST_ARMHF_NO_SIMD_WARNING_BLOCK,
        *MEDNAFEN_SUPAFAUST_OWL_WARNING_BLOCKS,
        MEDNAFEN_SUPAFAUST_MTHREAD_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_SPC700_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_STATE_WARNING_BLOCK,
    ),
}
MEDNAFEN_SUPAFAUST_EXPECTED_WARNING_LINES = {
    architecture: tuple(block.splitlines()[0] for block in blocks)
    for architecture, blocks in MEDNAFEN_SUPAFAUST_EXPECTED_WARNING_BLOCKS.items()
}

MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS = (
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:445:7: note: parameter passing for argument of type "
        "'std::vector<Mednafen::MemoryPatch>::iterator' changed in GCC 7.1",
        "  445 |       vector<_Tp, _Alloc>::",
        "      |       ^~~~~~~~~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "stl_vector.h:1289:28: note: parameter passing for argument of type "
        "'__gnu_cxx::__normal_iterator<Mednafen::MemoryPatch*, "
        "std::vector<Mednafen::MemoryPatch> >' changed in GCC 7.1",
        " 1289 |           _M_realloc_insert(end(), __x);",
        "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:445:7: note: parameter passing for argument of type "
        "'std::vector<Mednafen::MTStreamReader::StreamInfo>::iterator' "
        "changed in GCC 7.1",
        "  445 |       vector<_Tp, _Alloc>::",
        "      |       ^~~~~~~~~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:123:28: note: parameter passing for argument of type "
        "'__gnu_cxx::__normal_iterator<Mednafen::MTStreamReader::StreamInfo*, "
        "std::vector<Mednafen::MTStreamReader::StreamInfo> >' changed in GCC 7.1",
        "  123 |           _M_realloc_insert(end(), std::forward<_Args>(__args)...);",
        "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:445:7: note: parameter passing for argument of type "
        "'std::vector<long long unsigned int>::iterator' changed in GCC 7.1",
        "  445 |       vector<_Tp, _Alloc>::",
        "      |       ^~~~~~~~~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:123:28: note: parameter passing for argument of type "
        "'__gnu_cxx::__normal_iterator<long long unsigned int*, "
        "std::vector<long long unsigned int> >' changed in GCC 7.1",
        "  123 |           _M_realloc_insert(end(), std::forward<_Args>(__args)...);",
        "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:445:7: note: parameter passing for argument of type "
        "'std::vector<long long int>::iterator' changed in GCC 7.1",
        "  445 |       vector<_Tp, _Alloc>::",
        "      |       ^~~~~~~~~~~~~~~~~~~",
    ),
    _diagnostic_block(
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc:123:28: note: parameter passing for argument of type "
        "'__gnu_cxx::__normal_iterator<long long int*, "
        "std::vector<long long int> >' changed in GCC 7.1",
        "  123 |           _M_realloc_insert(end(), std::forward<_Args>(__args)...);",
        "      |           ~~~~~~~~~~~~~~~~~^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~",
    ),
)
MEDNAFEN_SUPAFAUST_EXPECTED_NOTE_BLOCKS = {
    "arm64": (),
    "armhf": MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS,
}
MEDNAFEN_SUPAFAUST_EXPECTED_NOTE_LINES = {
    architecture: tuple(block.splitlines()[0] for block in blocks)
    for architecture, blocks in MEDNAFEN_SUPAFAUST_EXPECTED_NOTE_BLOCKS.items()
}

MEDNAFEN_SUPAFAUST_SPC700_CONTEXT_BLOCK = "\n".join(
    (
        "In file included from mednafen/snes_faust/apu.cpp:78:",
        MEDNAFEN_SUPAFAUST_SPC700_WARNING_BLOCK,
    )
)
MEDNAFEN_SUPAFAUST_OWL_CONTEXT_BLOCK = "\n".join(
    (
        "mednafen/sound/OwlResampler.cpp: In constructor "
        "'Mednafen::OwlResampler::OwlResampler(double, double, double, "
        "double, int, double, double, int32, int32)':",
        *MEDNAFEN_SUPAFAUST_OWL_WARNING_BLOCKS,
    )
)
MEDNAFEN_SUPAFAUST_ARM64_STATE_CONTEXT_BLOCK = "\n".join(
    (
        "In file included from /usr/aarch64-linux-gnu/include/string.h:495,",
        "                 from mednafen/types.h:50,",
        "                 from mednafen/mednafen.h:4,",
        "                 from mednafen/state.cpp:18:",
        "In function 'char* strncpy(char*, const char*, size_t)',",
        "    inlined from 'bool Mednafen::MDFNSS_StateAction(Mednafen::StateMem*, "
        "unsigned int, bool, const Mednafen::SFORMAT*, const char*)' at "
        "mednafen/state.cpp:411:12:",
        MEDNAFEN_SUPAFAUST_ARM64_STATE_WARNING_BLOCK,
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_STATE_CONTEXT_BLOCK = "\n".join(
    (
        "mednafen/state.cpp: In function 'bool Mednafen::MDFNSS_StateAction("
        "StateMem*, unsigned int, bool, const SFORMAT*, const char*)':",
        MEDNAFEN_SUPAFAUST_ARMHF_STATE_WARNING_BLOCK,
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_MEMPATCHER_NOTE_CONTEXT_BLOCK = "\n".join(
    (
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:72,",
        "                 from mednafen/types.h:65,",
        "                 from mednafen/mednafen.h:4,",
        "                 from mednafen/mempatcher.cpp:18:",
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc: In member function 'void std::vector<_Tp, "
        "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
        "{const Mednafen::MemoryPatch&}; _Tp = Mednafen::MemoryPatch; "
        "_Alloc = std::allocator<Mednafen::MemoryPatch>]':",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[0],
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:66:",
        "In member function 'void std::vector<_Tp, _Alloc>::push_back(const "
        "value_type&) [with _Tp = Mednafen::MemoryPatch; _Alloc = "
        "std::allocator<Mednafen::MemoryPatch>]',",
        "    inlined from 'void Mednafen::MDFNI_AddCheat(const MemoryPatch&)' "
        "at mednafen/mempatcher.cpp:82:19:",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[1],
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_MTSTREAM_NOTE_CONTEXT_BLOCK = "\n".join(
    (
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:72,",
        "                 from ./mednafen/types.h:65,",
        "                 from ./mednafen/mednafen.h:4,",
        "                 from mednafen/MTStreamReader.cpp:22:",
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc: In member function 'void std::vector<_Tp, "
        "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
        "{Mednafen::MTStreamReader::StreamInfo}; _Tp = "
        "Mednafen::MTStreamReader::StreamInfo; _Alloc = "
        "std::allocator<Mednafen::MTStreamReader::StreamInfo>]':",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[2],
        "In member function 'void std::vector<_Tp, _Alloc>::emplace_back("
        "_Args&& ...) [with _Args = {Mednafen::MTStreamReader::StreamInfo}; "
        "_Tp = Mednafen::MTStreamReader::StreamInfo; _Alloc = "
        "std::allocator<Mednafen::MTStreamReader::StreamInfo>]',",
        "    inlined from 'void std::vector<_Tp, _Alloc>::push_back(value_type&&) "
        "[with _Tp = Mednafen::MTStreamReader::StreamInfo; _Alloc = "
        "std::allocator<Mednafen::MTStreamReader::StreamInfo>]' at "
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "stl_vector.h:1296:21,",
        "    inlined from 'void Mednafen::MTStreamReader::add_stream(StreamInfo)' "
        "at mednafen/MTStreamReader.cpp:200:19:",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[3],
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_UNSIGNED_FIRST_NOTE_CONTEXT_BLOCK = "\n".join(
    (
        "In file included from /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/vector:72,",
        "                 from mednafen/types.h:65,",
        "                 from mednafen/mednafen.h:4,",
        "                 from mednafen/settings.cpp:26:",
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc: In member function 'void std::vector<_Tp, "
        "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
        "{long long unsigned int}; _Tp = long long unsigned int; _Alloc = "
        "std::allocator<long long unsigned int>]':",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[4],
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_UNSIGNED_SECOND_NOTE_CONTEXT_BLOCK = "\n".join(
    (
        "In member function 'void std::vector<_Tp, _Alloc>::emplace_back("
        "_Args&& ...) [with _Args = {long long unsigned int}; _Tp = long "
        "long unsigned int; _Alloc = std::allocator<long long unsigned int>]',",
        "    inlined from 'void std::vector<_Tp, _Alloc>::push_back(value_type&&) "
        "[with _Tp = long long unsigned int; _Alloc = std::allocator<long "
        "long unsigned int>]' at /opt/a30/arm-a30-linux-gnueabihf/include/"
        "c++/13.2.0/bits/stl_vector.h:1296:21,",
        "    inlined from 'std::vector<T> Mednafen::GetMultiEnum(const MDFNCS*, "
        "const char*) [with T = long long unsigned int]' at "
        "mednafen/settings.cpp:525:18,",
        "    inlined from 'std::vector<long long unsigned int> Mednafen::"
        "SettingsManager::GetMultiUI(const char*)' at "
        "mednafen/settings.cpp:577:45:",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[5],
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_SIGNED_FIRST_NOTE_CONTEXT_BLOCK = "\n".join(
    (
        "/opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "vector.tcc: In member function 'void std::vector<_Tp, "
        "_Alloc>::_M_realloc_insert(iterator, _Args&& ...) [with _Args = "
        "{long long int}; _Tp = long long int; _Alloc = "
        "std::allocator<long long int>]':",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[6],
    )
)
MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_SIGNED_SECOND_NOTE_CONTEXT_BLOCK = "\n".join(
    (
        "In member function 'void std::vector<_Tp, _Alloc>::emplace_back("
        "_Args&& ...) [with _Args = {long long int}; _Tp = long long int; "
        "_Alloc = std::allocator<long long int>]',",
        "    inlined from 'void std::vector<_Tp, _Alloc>::push_back(value_type&&) "
        "[with _Tp = long long int; _Alloc = std::allocator<long long int>]' "
        "at /opt/a30/arm-a30-linux-gnueabihf/include/c++/13.2.0/bits/"
        "stl_vector.h:1296:21,",
        "    inlined from 'std::vector<T> Mednafen::GetMultiEnum(const MDFNCS*, "
        "const char*) [with T = long long int]' at "
        "mednafen/settings.cpp:525:18,",
        "    inlined from 'std::vector<long long int> Mednafen::SettingsManager::"
        "GetMultiI(const char*)' at mednafen/settings.cpp:588:44:",
        MEDNAFEN_SUPAFAUST_ARMHF_NOTE_BLOCKS[7],
    )
)
MEDNAFEN_SUPAFAUST_EXPECTED_DIAGNOSTIC_CONTEXT_BLOCKS = {
    "arm64": (
        MEDNAFEN_SUPAFAUST_MTHREAD_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_SPC700_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARM64_STATE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_OWL_CONTEXT_BLOCK,
    ),
    "armhf": (
        MEDNAFEN_SUPAFAUST_ARMHF_NO_SIMD_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_OWL_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_MTHREAD_WARNING_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_MEMPATCHER_NOTE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_SPC700_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_STATE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_MTSTREAM_NOTE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_UNSIGNED_FIRST_NOTE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_UNSIGNED_SECOND_NOTE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_SIGNED_FIRST_NOTE_CONTEXT_BLOCK,
        MEDNAFEN_SUPAFAUST_ARMHF_SETTINGS_SIGNED_SECOND_NOTE_CONTEXT_BLOCK,
    ),
}

MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY = {
    "workflow": ".github/workflows/build-mednafen_supafaust.yml",
    "source_url": "https://github.com/libretro/supafaust.git",
    "source_requested_ref": "refs/heads/master",
    "source_commit": "2b93c0d7dff5b8f6c4e60e049d66849923fa8bba",
    "source_tree": "68dcc9b53118d9933f716c7219989822a89d10d7",
    "source_key": MEDNAFEN_SUPAFAUST_CORE_ID,
    "source_dir": "libretro-mednafen_supafaust",
    "output_path": "dist/unix/mednafen_supafaust_libretro.so",
    "artifact_name": MEDNAFEN_SUPAFAUST_BUILD_ARTIFACT_NAME,
    "metadata_source_path": (
        "/libretro-super/dist/info/mednafen_supafaust_libretro.info"
    ),
    "metadata_artifact_name": "mednafen_supafaust_libretro.info",
    "targets": ["arm64", "armhf"],
    "git_version": {
        "derivation": "hyphen-short7-v1",
        "value": "-2b93c0d",
        "compiler_scope": "cxx",
    },
}


# Raised by the catalog guard when this core's spec drifts from the
# reviewed identity above; bound by core_pipeline's guard registry.
SPEC_GUARD_MESSAGE = (
    "the mednafen_supafaust core must preserve its exact "
    "injected version, source, recipe, metadata, and "
    "target contract"
)


def mednafen_supafaust_spec_is_well_formed(spec: object) -> bool:
    """Require the complete immutable Mednafen Supafaust catalog identity."""

    identity = MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY
    return bool(
        isinstance(spec, dict)
        and spec
        == {
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
                "git_version": identity["git_version"],
            },
            "metadata": {
                "source_path": identity["metadata_source_path"],
                "artifact_name": identity["metadata_artifact_name"],
            },
            "targets": identity["targets"],
        }
    )


MEDNAFEN_SUPAFAUST_LOG_CONTRACT = MixedLanguageLogContract(
    core_id=MEDNAFEN_SUPAFAUST_CORE_ID,
    expected_compile_count=MEDNAFEN_SUPAFAUST_EXPECTED_COMPILE_COUNT,
    expected_language_counts=MEDNAFEN_SUPAFAUST_EXPECTED_LANGUAGE_COUNTS,
    expected_compile_pair_sha256=(
        MEDNAFEN_SUPAFAUST_EXPECTED_COMPILE_PAIR_SHA256
    ),
    expected_compile_invocation_sha256=(
        MEDNAFEN_SUPAFAUST_EXPECTED_COMPILE_INVOCATION_SHA256
    ),
    expected_link_object_sha256=(
        MEDNAFEN_SUPAFAUST_EXPECTED_LINK_OBJECT_SHA256
    ),
    expected_raw_link_object_sha256=(
        MEDNAFEN_SUPAFAUST_EXPECTED_RAW_LINK_OBJECT_SHA256
    ),
    build_artifact_name=MEDNAFEN_SUPAFAUST_BUILD_ARTIFACT_NAME,
    expected_link_options=MEDNAFEN_SUPAFAUST_EXPECTED_LINK_OPTIONS,
    source_commit=MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY["source_commit"],
    source_tree=MEDNAFEN_SUPAFAUST_GIT_VERSION_SPEC_IDENTITY["source_tree"],
)


def mednafen_supafaust_log_proves_contract(
    build_log_text: str,
    core_id: object,
    arch: str,
    source_commit: object,
    source_tree: object,
) -> bool:
    """Prove Supafaust's exact C++ build and reviewed diagnostics."""

    if not isinstance(build_log_text, str):
        return False
    expected_warning_lines = MEDNAFEN_SUPAFAUST_EXPECTED_WARNING_LINES.get(arch)
    expected_warning_blocks = MEDNAFEN_SUPAFAUST_EXPECTED_WARNING_BLOCKS.get(arch)
    expected_note_lines = MEDNAFEN_SUPAFAUST_EXPECTED_NOTE_LINES.get(arch)
    expected_note_blocks = MEDNAFEN_SUPAFAUST_EXPECTED_NOTE_BLOCKS.get(arch)
    expected_context_blocks = (
        MEDNAFEN_SUPAFAUST_EXPECTED_DIAGNOSTIC_CONTEXT_BLOCKS.get(arch)
    )
    if (
        expected_warning_lines is None
        or expected_warning_blocks is None
        or expected_note_lines is None
        or expected_note_blocks is None
        or expected_context_blocks is None
    ):
        return False
    lowered_log = build_log_text.casefold()
    if any(
        marker in lowered_log
        for marker in (
            "error:",
            "fatal:",
            "undefined reference",
            "dubious ownership",
            "collect2: error",
            "ld returned",
            "linker command failed",
        )
    ) or MEDNAFEN_SUPAFAUST_MAKE_FAILURE_RE.search(build_log_text):
        return False
    warning_lines = (
        line
        for line in build_log_text.splitlines()
        if "warning:" in line.casefold()
    )
    note_lines = (
        line
        for line in build_log_text.splitlines()
        if "note:" in line.casefold()
    )
    if (
        Counter(warning_lines) != Counter(expected_warning_lines)
        or Counter(note_lines) != Counter(expected_note_lines)
        or any(
            build_log_text.count(block) != 1
            for block in (*expected_warning_blocks, *expected_note_blocks)
        )
        or not _diagnostic_context_lines_are_exact(
            build_log_text, expected_context_blocks
        )
    ):
        return False
    return mixed_language_log_proves_contract(
        build_log_text,
        core_id,
        arch,
        source_commit,
        source_tree,
        MEDNAFEN_SUPAFAUST_LOG_CONTRACT,
    )
