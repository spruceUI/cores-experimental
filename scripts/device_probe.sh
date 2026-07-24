#!/bin/sh
# device_probe.sh - capture everything the Cores-spruce build/eligibility
# pipeline needs to know about a target device, with zero arguments, either
# locally on the device or over SSH (`ssh user@dev 'sh -s' < device_probe.sh`).
#
# It is READ-ONLY: it inspects the running system and writes exactly one log
# file on the device (and echoes the same content to stdout so an SSH caller
# captures it). It fills the pipeline's uncaptured-evidence gaps:
#   effective-runtime-provider-capture, target-loader-capture,
#   target-sysroot-capture (runtime side), frontend-binary,
#   target-rootfs-load-validation (v3: loader-truth dependency resolution).
#
# v3 additions answer "is every library a core needs actually resolvable here?"
# -- not just libstdc++. The pipeline records each core's exact DT_NEEDED set,
# and cores now exist whose needs go beyond libc/libstdc++ (parallel_n64 links
# libGLESv2.so.2 directly). Three new evidence classes:
#   1. Loader-truth resolution: ask the device's own dynamic loader to resolve
#      each installed core's dependencies, which is the only answer that
#      accounts for the real search path, symlink farms and vendor blobs.
#   2. A machine-readable soname -> provider table for the union of libraries
#      the catalog's cores need, so non-versioned providers get the same
#      treatment libstdc++ already gets.
#   3. Graphics-stack detail (nodes, EGL/GLES vendor+version, hashes) and the
#      frontend's own GL capability -- the gate for the many cores that reach
#      GL through the frontend rather than through DT_NEEDED.
#
# Portability: POSIX sh / busybox ash only. No bashisms, no arrays. Version
# symbols are read with `strings` (falling back to `tr`) so no readelf/ldd/
# objdump is required - those are usually absent on handheld firmware.
#
# The final "CAPTURE" block is key=value lines that map directly onto
# manifests/device-runtime-contracts.json provider_observations fields.

set -u

# ----------------------------------------------------------------------------
# Output plumbing: pick the first writable location for the on-device log.
# ----------------------------------------------------------------------------
STAMP=$(date +%Y%m%d-%H%M%S 2>/dev/null || echo unknown-time)
HOSTID=$(uname -n 2>/dev/null || echo device)
LOGNAME="device-probe-${HOSTID}-${STAMP}.log"

pick_logdir() {
    for d in "$PWD" /mnt/SDCARD /mnt/mmc /roms "$HOME" /tmp /var/tmp; do
        [ -n "$d" ] || continue
        if [ -d "$d" ] && ( : >"$d/.probe_write_test" ) 2>/dev/null; then
            rm -f "$d/.probe_write_test" 2>/dev/null
            printf '%s\n' "$d"
            return 0
        fi
    done
    printf '%s\n' "."
}
LOGDIR=$(pick_logdir)
LOGFILE="${LOGDIR}/${LOGNAME}"

# Emit to both the log file and stdout.
: >"$LOGFILE" 2>/dev/null || LOGFILE=/dev/null
say() { printf '%s\n' "$*" | tee -a "$LOGFILE"; }
sec() { say ""; say "=== $* ==="; }

# ----------------------------------------------------------------------------
# Helpers.
# ----------------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

# Collapse leading/trailing whitespace. Space-separated accumulators are built
# with a leading space, which is fine for the human-readable lines but must not
# leak into the machine-readable CAPTURE values.
trim() { printf '%s' "$*" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'; }

# Dump printable strings from a binary (strings if present, else a tr shim).
dump_strings() {
    if have strings; then
        strings -a "$1" 2>/dev/null
    else
        tr -c '[:print:]' '\n' <"$1" 2>/dev/null
    fi
}

# Highest dotted version symbol of a given prefix (e.g. GLIBCXX) in a library,
# compared numerically field-by-field. Prints the full symbol or nothing.
max_symbol() {
    _lib=$1; _prefix=$2
    [ -r "$_lib" ] || return 0
    dump_strings "$_lib" \
        | grep -oE "${_prefix}_[0-9]+(\.[0-9]+)*" 2>/dev/null \
        | awk -v p="${_prefix}_" '
            {
                v = substr($0, length(p) + 1)
                n = split(v, f, ".")
                better = 0
                if (!seen) { better = 1 }
                else {
                    m = (n > bn) ? n : bn
                    for (i = 1; i <= m; i++) {
                        a = (i <= n)  ? f[i]  + 0 : 0
                        b = (i <= bn) ? bf[i] + 0 : 0
                        if (a > b) { better = 1; break }
                        if (a < b) { better = 0; break }
                    }
                }
                if (better) {
                    seen = 1; best = $0; bn = n
                    for (i = 1; i <= n; i++) bf[i] = f[i]
                }
            }
            END { if (seen) print best }'
}

# sha256 of a file, with graceful fallbacks; prints "algo:hex" or "unavailable".
file_hash() {
    _f=$1
    [ -r "$_f" ] || { printf 'unavailable'; return 0; }
    if have sha256sum; then
        printf 'sha256:%s' "$(sha256sum "$_f" 2>/dev/null | cut -d' ' -f1)"
    elif have openssl; then
        printf 'sha256:%s' "$(openssl dgst -sha256 "$_f" 2>/dev/null | awk '{print $NF}')"
    elif have shasum; then
        printf 'sha256:%s' "$(shasum -a 256 "$_f" 2>/dev/null | cut -d' ' -f1)"
    elif have md5sum; then
        printf 'md5:%s' "$(md5sum "$_f" 2>/dev/null | cut -d' ' -f1)"
    else
        printf 'unavailable'
    fi
}

# Dynamic-loader (ELF interpreter) name referenced by a binary.
interp_of() {
    dump_strings "$1" 2>/dev/null | grep -oE '/?ld-[a-zA-Z0-9._-]*\.so[0-9.]*' \
        | head -1
}

# Absolute, executable path of the dynamic loader named by interp_of.
LOADER_ABS=""
resolve_loader() {
    _name=${1##*/}
    [ -n "$_name" ] || return 0
    for d in /lib /lib64 /usr/lib /usr/lib64 /lib/aarch64-linux-gnu \
             /lib/arm-linux-gnueabihf /usr/lib/aarch64-linux-gnu \
             /usr/lib/arm-linux-gnueabihf; do
        [ -x "$d/$_name" ] && { printf '%s' "$d/$_name"; return 0; }
    done
    [ -x "$1" ] && printf '%s' "$1"
}

# DT_NEEDED entries of an ELF object, read straight out of .dynstr. This is the
# requirement side and needs no loader, so it works even for a foreign ABI.
needed_of() {
    dump_strings "$1" 2>/dev/null \
        | grep -oE '^lib[A-Za-z0-9._+-]*\.so[0-9.]*$' | sort -u
}

# Ask the DEVICE'S OWN loader to resolve an object's dependencies. This is the
# authoritative answer -- it applies the real search path, ld.so.cache, symlink
# farms and vendor blob layouts, none of which a manual directory scan models
# correctly. LD_TRACE_LOADED_OBJECTS is the same mechanism ldd uses: the loader
# resolves and reports, it does not run the object's code.
# Prints "<soname> => <path|not found>" lines, or nothing if unavailable.
loader_list() {
    _obj=$1
    [ -r "$_obj" ] || return 0
    if [ -n "$LOADER_ABS" ]; then
        LD_TRACE_LOADED_OBJECTS=1 "$LOADER_ABS" "$_obj" 2>/dev/null \
            | sed 's/^[[:space:]]*//' | grep '=>' && return 0
    fi
    if have ldd; then
        ldd "$_obj" 2>/dev/null | sed 's/^[[:space:]]*//' | grep '=>'
    fi
}

# Unresolved sonames for one object, one per line. Empty output means the
# object fully resolves on this device.
missing_deps_of() {
    loader_list "$1" | grep -i 'not found' | awk '{print $1}'
}

# Where a bare soname resolves on the loader search path (or "absent").
# Prefers a copy whose ELF target matches the cores' ABI: multilib firmware
# carries 32-bit copies that would otherwise mask the real provider. This
# models the loader's search; the per-core resolution above performs it, and
# remains the authoritative answer.
soname_path() {
    _first=""
    for d in $LDPATH_DIRS; do
        [ -e "$d/$1" ] || continue
        _p=$(readlink -f "$d/$1" 2>/dev/null || printf '%s' "$d/$1")
        [ -n "$_first" ] || _first=$_p
        if [ "$(elf_target "$_p")" = "$PIPELINE_TARGET" ]; then
            printf '%s' "$_p"; return 0
        fi
    done
    printf '%s' "${_first:-absent}"
}

# First N bytes of a file as contiguous lowercase hex, using whichever hex
# dumper exists (busybox firmware may ship od OR hexdump OR xxd, not all).
hex_head() {
    _f=$1; _n=$2
    if have od; then
        head -c "$_n" "$_f" 2>/dev/null | od -An -tx1 2>/dev/null | tr -d ' \n'
    elif have hexdump; then
        hexdump -v -n "$_n" -e '1/1 "%02x"' "$_f" 2>/dev/null
    elif have xxd; then
        xxd -p -l "$_n" "$_f" 2>/dev/null | tr -d '\n'
    fi
}

# ELF class+machine of a file, normalized to a pipeline-target token
# (arm64 / armhf / x86_64 / x86 / other), or empty if unreadable / not ELF.
# Reads only the 20-byte ELF header, so no readelf/file is needed. This is what
# lets a multilib device (e.g. a /usr/lib32 alongside /usr/lib) pick the
# libstdc++ that actually matches the cores' ABI.
elf_target() {
    _f=$1
    [ -r "$_f" ] || return 0
    _hx=$(hex_head "$_f" 20)
    case "$_hx" in 7f454c46*) : ;; *) return 0 ;; esac
    _cls=$(printf '%s' "$_hx" | cut -c9-10)   # EI_CLASS: 01=32-bit 02=64-bit
    _m0=$(printf '%s' "$_hx" | cut -c37-38)   # e_machine low byte (LE)
    case "${_cls}:${_m0}" in
        02:b7) printf 'arm64' ;;
        01:28) printf 'armhf' ;;
        02:3e) printf 'x86_64' ;;
        01:03) printf 'x86' ;;
        *)     printf 'other' ;;
    esac
}

# Map ARM CPU implementer:part (from /proc/cpuinfo) to a core name usable as a
# gcc -mcpu/-mtune target. Feeds the device-specific optimization (build-flavor)
# axis; "model name"/"Hardware" are usually blank on these SoCs, so the
# implementer/part pair is the reliable identity.
arm_part_name() {
    case "$1:$2" in
        0x41:0xc05) echo cortex-a5 ;;
        0x41:0xc07) echo cortex-a7 ;;
        0x41:0xc08) echo cortex-a8 ;;
        0x41:0xc09) echo cortex-a9 ;;
        0x41:0xc0d|0x41:0xc0e|0x41:0xc0f) echo cortex-a17 ;;
        0x41:0xd02) echo cortex-a34 ;;
        0x41:0xd03) echo cortex-a53 ;;
        0x41:0xd04) echo cortex-a35 ;;
        0x41:0xd05) echo cortex-a55 ;;
        0x41:0xd07) echo cortex-a57 ;;
        0x41:0xd08) echo cortex-a72 ;;
        0x41:0xd09) echo cortex-a73 ;;
        0x41:0xd0a) echo cortex-a75 ;;
        0x41:0xd0b) echo cortex-a76 ;;
        *)          echo unknown ;;
    esac
}

# Launcher scripts usually export their own LD_LIBRARY_PATH before starting the
# frontend, so the probe's inherited environment is NOT the search path cores
# are loaded with. Harvest the assignments so resolution below reflects the
# path that actually applies at play time.
FE_LD_PATHS=""
discover_launcher_ld_path() {
    for s in /mnt/SDCARD/RetroArch/ra32.sh /mnt/SDCARD/RetroArch/ra64.sh \
             /mnt/SDCARD/RetroArch/launch.sh /mnt/SDCARD/Emu/.emu_setup/launch.sh \
             /mnt/SDCARD/spruce/scripts/*.sh /usr/miyoo/bin/runemu.sh \
             /mnt/SDCARD/App/*/launch.sh; do
        [ -r "$s" ] || continue
        # Take the right-hand side of any LD_LIBRARY_PATH assignment and keep
        # the absolute directories from it. $LD_LIBRARY_PATH self-references and
        # unexpanded variables are skipped rather than guessed at.
        grep -h 'LD_LIBRARY_PATH=' "$s" 2>/dev/null \
            | sed 's/.*LD_LIBRARY_PATH=//; s/^"//; s/".*$//; s/^'\''//; s/'\''.*$//' \
            | tr ':' '\n' \
            | while IFS= read -r p; do
                case "$p" in
                    /*) [ -d "$p" ] && printf '%s|%s\n' "$s" "$p" ;;
                esac
              done
    done
}

# First existing path for a library name across the loader search order.
LDPATH_DIRS=""
build_search_dirs() {
    _dirs=""
    # 1. LD_LIBRARY_PATH (highest priority, colon-separated).
    _old_ifs=$IFS; IFS=:
    for d in ${LD_LIBRARY_PATH:-}; do [ -n "$d" ] && _dirs="$_dirs $d"; done
    IFS=$_old_ifs
    # 1b. LD_LIBRARY_PATH the launcher scripts set for the frontend.
    for pair in $(discover_launcher_ld_path 2>/dev/null); do
        d=${pair#*|}
        [ -n "$d" ] && _dirs="$_dirs $d"
        FE_LD_PATHS="$FE_LD_PATHS $pair"
    done
    # 2. ld.so.conf include dirs.
    if [ -r /etc/ld.so.conf ]; then
        for f in /etc/ld.so.conf /etc/ld.so.conf.d/*.conf; do
            [ -r "$f" ] || continue
            while IFS= read -r line; do
                case "$line" in
                    /*) [ -d "$line" ] && _dirs="$_dirs $line" ;;
                esac
            done <"$f"
        done
    fi
    # 3. Standard system dirs + common handheld firmware bundle dirs.
    for d in /lib /usr/lib /lib/arm-linux-gnueabihf /usr/lib/arm-linux-gnueabihf \
             /lib/aarch64-linux-gnu /usr/lib/aarch64-linux-gnu \
             /usr/local/lib /mnt/SDCARD/spruce/lib /mnt/SDCARD/miyoo/lib \
             /mnt/SDCARD/trimui/lib /usr/miyoo/lib /usr/trimui/lib; do
        [ -d "$d" ] && _dirs="$_dirs $d"
    done
    LDPATH_DIRS=$_dirs
}

# ----------------------------------------------------------------------------
# Report.
# ----------------------------------------------------------------------------
say "Cores-spruce device probe"
say "log: $LOGFILE"
say "generated: $STAMP"
say "probe-schema: device-probe-v3"

sec "Identity and kernel"
say "uname-a: $(uname -a 2>/dev/null)"
say "machine: $(uname -m 2>/dev/null)"
say "kernel-release: $(uname -r 2>/dev/null)"
if [ -r /etc/os-release ]; then
    say "os-release:"; sed 's/^/  /' /etc/os-release | tee -a "$LOGFILE"
fi
for f in /etc/spruce_version /mnt/SDCARD/spruce/version.txt /etc/version; do
    [ -r "$f" ] && say "firmware-version($f): $(head -1 "$f" 2>/dev/null)"
done

sec "CPU / ABI"
CPU_CORE=unknown; SUGGESTED_MCPU=""; SUGGESTED_OPT=""; SUGGESTED_MFPU=""
CPU_IMPL=""; CPU_PART=""; CPU_FEATURES=""
if [ -r /proc/cpuinfo ]; then
    say "cpu-model: $(grep -iE 'model name|Processor|Hardware' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2- | sed 's/^ *//')"
    say "cpu-count: $(grep -c '^processor' /proc/cpuinfo 2>/dev/null)"
    CPU_FEATURES=$(grep -iE '^Features|^flags' /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2- | sed 's/^ *//')
    say "cpu-features: $CPU_FEATURES"
    # "model name"/"Hardware" are usually blank on these SoCs; the ARM
    # implementer:part pair is the reliable identity for -mcpu selection.
    CPU_IMPL=$(grep -iE '^CPU implementer' /proc/cpuinfo 2>/dev/null | head -1 | awk '{print $NF}')
    CPU_PART=$(grep -iE '^CPU part' /proc/cpuinfo 2>/dev/null | head -1 | awk '{print $NF}')
    say "cpu-implementer: ${CPU_IMPL:-unknown}"
    say "cpu-part: ${CPU_PART:-unknown}"
    say "cpu-architecture: $(grep -iE '^CPU architecture' /proc/cpuinfo 2>/dev/null | head -1 | awk '{print $NF}')"
    CPU_CORE=$(arm_part_name "${CPU_IMPL:-x}" "${CPU_PART:-x}")
    say "cpu-core-name: $CPU_CORE"
    [ "$CPU_CORE" != unknown ] && SUGGESTED_MCPU=$CPU_CORE
fi
# Clock (context, not a flag) and cache sizes (gcc --param l1/l2-cache-size).
_maxkhz=$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq 2>/dev/null)
[ -n "$_maxkhz" ] && say "cpu-max-mhz: $((_maxkhz / 1000))"
for ci in /sys/devices/system/cpu/cpu0/cache/index*; do
    [ -r "$ci/size" ] || continue
    say "cache: L$(cat "$ci/level" 2>/dev/null)$(cat "$ci/type" 2>/dev/null | cut -c1) $(cat "$ci/size" 2>/dev/null)"
done
# Probe ABI/float and the dynamic loader from a known system binary.
REFBIN=""
for b in /bin/sh /bin/busybox /bin/cat "$0"; do
    [ -r "$b" ] && { REFBIN=$b; break; }
done
LOADER=""
[ -n "$REFBIN" ] && LOADER=$(interp_of "$REFBIN")
say "reference-binary: ${REFBIN:-none}"
say "dynamic-loader: ${LOADER:-unknown}"
[ -n "$LOADER" ] && LOADER_ABS=$(resolve_loader "$LOADER")
say "dynamic-loader-abs: ${LOADER_ABS:-not-found}"
# Whether loader-truth resolution is available at all decides how much of the
# v3 evidence this run can produce; say so once, up front.
if [ -n "$LOADER_ABS" ]; then
    DEP_METHOD=loader
elif have ldd; then
    DEP_METHOD=ldd
else
    DEP_METHOD=none
fi
say "dependency-resolution-method: $DEP_METHOD"
case "$LOADER" in
    *aarch64*) ABI=arm64;  PIPELINE_TARGET=arm64 ;;
    *armhf*)   ABI=armhf-hardfloat; PIPELINE_TARGET=armhf ;;
    *arm*)     ABI=arm-softfloat;   PIPELINE_TARGET="armhf(soft?)" ;;
    *)         ABI=unknown;         PIPELINE_TARGET=unknown ;;
esac
say "derived-abi: $ABI"
say "pipeline-target: $PIPELINE_TARGET"
# Advisory only: a reasonable -mcpu/-march the pipeline COULD pin for a
# device-tuned build flavor. Not applied here; the generic per-ABI build stays
# the default. -mcpu already implies a known core's ISA features.
case "$PIPELINE_TARGET" in
    armhf)
        case "$CPU_FEATURES" in
            *vfpv4*) SUGGESTED_MFPU=neon-vfpv4 ;;
            *neon*)  SUGGESTED_MFPU=neon ;;
        esac
        if [ -n "$SUGGESTED_MCPU" ]; then
            SUGGESTED_OPT="-mcpu=$SUGGESTED_MCPU${SUGGESTED_MFPU:+ -mfpu=$SUGGESTED_MFPU} -mfloat-abi=hard"
        fi
        ;;
    arm64)
        _f=""
        case "$CPU_FEATURES" in *crc32*) _f="$_f+crc" ;; esac
        case "$CPU_FEATURES" in *aes*|*pmull*|*sha1*|*sha2*) _f="$_f+crypto" ;; esac
        case "$CPU_FEATURES" in *asimddp*) _f="$_f+dotprod" ;; esac
        case "$CPU_FEATURES" in *asimdhp*|*fphp*) _f="$_f+fp16" ;; esac
        if [ -n "$SUGGESTED_MCPU" ]; then SUGGESTED_OPT="-mcpu=$SUGGESTED_MCPU"
        else SUGGESTED_OPT="-march=armv8-a$_f"; fi
        ;;
esac
say "suggested-mcpu: ${SUGGESTED_MCPU:-unknown}"
say "suggested-opt-flags: ${SUGGESTED_OPT:-unknown}"

sec "C runtime ceiling (libc)"
LIBC=""
build_search_dirs
for d in $LDPATH_DIRS; do
    for c in "$d/libc.so.6" "$d/libc.so"; do
        [ -e "$c" ] && { LIBC=$c; break; }
    done
    [ -n "$LIBC" ] && break
done
if have ldd; then say "ldd-version: $(ldd --version 2>&1 | head -1)"; fi
say "libc-path: ${LIBC:-not-found}"
if [ -n "$LIBC" ]; then
    say "libc-hash: $(file_hash "$LIBC")"
    say "libc-max-GLIBC: $(max_symbol "$LIBC" GLIBC)"
fi

sec "C++ runtime providers (GLIBCXX ceiling)"
# Enumerate every reachable libstdc++.so.6 in loader order; the first is the
# effective provider, the rest are fallbacks. Role labels are heuristic and
# should be confirmed against the firmware layout.
CXX_EFFECTIVE=""; CXX_EFFECTIVE_MAX=""; CXX_EFFECTIVE_ELF=""
CXX_MATCH=""; CXX_FIRST=""
SECONDARY_ABI=""; SECONDARY_ABI_MAX=""
idx=0
for d in $LDPATH_DIRS; do
    for lib in "$d/libstdc++.so.6" "$d/libstdc++.so"; do
        [ -e "$lib" ] || continue
        idx=$((idx + 1))
        real=$(readlink -f "$lib" 2>/dev/null || echo "$lib")
        gx=$(max_symbol "$real" GLIBCXX)
        cx=$(max_symbol "$real" CXXABI)
        h=$(file_hash "$real")
        parch=$(elf_target "$real")
        case "$d" in
            *LD_LIBRARY*|/mnt/*|/usr/local/*) role=bundled-first-search-path-provider ;;
            *) role=packaged-fallback-provider ;;
        esac
        [ "$idx" -gt 1 ] && role=packaged-fallback-provider
        say "provider[$idx]: $lib"
        say "  real-path: $real"
        say "  elf-target: ${parch:-unknown}"
        say "  role(heuristic): $role"
        say "  hash: $h"
        say "  max-GLIBCXX: ${gx:-none}"
        say "  max-CXXABI: ${cx:-none}"
        # First provider of ANY abi is the last-resort fallback.
        if [ -z "$CXX_FIRST" ]; then
            CXX_FIRST=$real; CXX_FIRST_MAX=$gx; CXX_FIRST_CXXABI=$cx
            CXX_FIRST_HASH=$h; CXX_FIRST_ROLE=$role; CXX_FIRST_ELF=${parch:-unknown}
        fi
        # Prefer the first provider whose ELF abi matches the cores' target,
        # so a /usr/lib32 (armhf) copy never masks the real arm64 provider.
        if [ -z "$CXX_MATCH" ] && [ "$parch" = "$PIPELINE_TARGET" ]; then
            CXX_MATCH=$real; CXX_MATCH_MAX=$gx; CXX_MATCH_CXXABI=$cx
            CXX_MATCH_HASH=$h; CXX_MATCH_ROLE=$role; CXX_MATCH_ELF=$parch
        fi
        # A provider of the OTHER abi means the device is multilib and could
        # also host that abi's cores.
        if [ -n "$parch" ] && [ "$parch" != "$PIPELINE_TARGET" ] \
           && [ "$parch" != other ] && [ -z "$SECONDARY_ABI" ]; then
            SECONDARY_ABI=$parch; SECONDARY_ABI_MAX=$gx
        fi
    done
done
if [ -n "$CXX_MATCH" ]; then
    CXX_EFFECTIVE=$CXX_MATCH; CXX_EFFECTIVE_MAX=$CXX_MATCH_MAX
    CXX_EFFECTIVE_CXXABI=$CXX_MATCH_CXXABI; CXX_EFFECTIVE_HASH=$CXX_MATCH_HASH
    CXX_EFFECTIVE_ROLE=$CXX_MATCH_ROLE; CXX_EFFECTIVE_ELF=$CXX_MATCH_ELF
elif [ -n "$CXX_FIRST" ]; then
    CXX_EFFECTIVE=$CXX_FIRST; CXX_EFFECTIVE_MAX=$CXX_FIRST_MAX
    CXX_EFFECTIVE_CXXABI=$CXX_FIRST_CXXABI; CXX_EFFECTIVE_HASH=$CXX_FIRST_HASH
    CXX_EFFECTIVE_ROLE=$CXX_FIRST_ROLE; CXX_EFFECTIVE_ELF=$CXX_FIRST_ELF
    say "note: no libstdc++ matched pipeline target $PIPELINE_TARGET; using first-found (elf=$CXX_EFFECTIVE_ELF)"
fi
[ "$idx" -eq 0 ] && say "no libstdc++.so.6 found on the loader search path (C-only device?)"
say "effective-cxx-provider: ${CXX_EFFECTIVE:-none} (elf=${CXX_EFFECTIVE_ELF:-unknown}, GLIBCXX=${CXX_EFFECTIVE_MAX:-none})"
[ -n "$SECONDARY_ABI" ] && say "secondary-abi-provider: $SECONDARY_ABI (max-GLIBCXX=${SECONDARY_ABI_MAX:-none})"
# Also scan common mount points for firmware-bundled copies the loader path missed.
say "-- broad scan for stray libstdc++ (depth-limited) --"
for base in /mnt /roms /media /storage; do
    [ -d "$base" ] || continue
    find "$base" -maxdepth 5 -name 'libstdc++.so*' 2>/dev/null | head -20 | while IFS= read -r extra; do
        say "  found: $extra  max-GLIBCXX=$(max_symbol "$extra" GLIBCXX)"
    done
done

sec "libgcc"
for d in $LDPATH_DIRS; do
    if [ -e "$d/libgcc_s.so.1" ]; then
        say "libgcc-path: $d/libgcc_s.so.1"
        say "libgcc-max-GCC: $(max_symbol "$d/libgcc_s.so.1" GCC)"
        break
    fi
done

sec "Runtime library providers (soname -> provider table)"
# The union of sonames the catalog's cores carry in DT_NEEDED, plus the ones a
# frontend needs to give a core a GL context. Each line is machine-readable:
#   lib: <soname> <path|absent> <elf-target> <hash>
# so a non-versioned provider can be transcribed into provider_observations the
# same way the libstdc++ ceiling already is.
LIB_ABSENT=""
for name in libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1 libz.so.1 \
            libstdc++.so.6 libgcc_s.so.1 libatomic.so.1 \
            libGL.so.1 libGLESv2.so.2 libGLESv2.so libGLESv1_CM.so.1 \
            libEGL.so.1 libEGL.so libmali.so.0 libgomp.so.1 \
            libgbm.so.1 libdrm.so.2 libvulkan.so.1 libmali.so \
            libSDL2-2.0.so.0 libSDL-1.2.so.0 libasound.so.2 libpulse.so.0 \
            libudev.so.1 libusb-1.0.so.0 libpng16.so.16 libfreetype.so.6 \
            libxml2.so.2 libbz2.so.1 liblzma.so.5; do
    p=$(soname_path "$name")
    if [ "$p" = absent ]; then
        say "lib: $name absent - -"
        LIB_ABSENT="$LIB_ABSENT $name"
    else
        say "lib: $name $p $(elf_target "$p") $(file_hash "$p")"
    fi
done
say "libs-absent:${LIB_ABSENT:- none}"

sec "GPU / graphics stack"
# The GPU is not a gcc target, but it selects the *video backend flavor* a
# GL/3D core must ship (glcore vs gles2/3 vs vulkan) and gates whether such
# cores are viable at all.
GPU_NODES=""
for node in /dev/dri/card0 /dev/dri/card1 /dev/dri/renderD128 /dev/mali0 \
            /dev/mali /dev/galcore /dev/pvrsrvkm /dev/rga /dev/ion \
            /dev/disp /dev/fb0; do
    [ -e "$node" ] || continue
    # Readability matters as much as existence: a node the frontend's user
    # cannot open provides nothing, and that is a common handheld failure.
    if [ -r "$node" ]; then acc=readable; else acc=present-not-readable; fi
    say "gpu-node: $node ($acc)"
    GPU_NODES="$GPU_NODES $node:$acc"
done
[ -n "$GPU_NODES" ] || say "gpu-node: none"
if [ -d /sys/class/drm ]; then
    for u in /sys/class/drm/card*/device/uevent; do
        [ -r "$u" ] || continue
        grep -iE '^DRIVER=|^OF_COMPATIBLE_0=|^PRODUCT=' "$u" 2>/dev/null \
            | sed 's/^/  drm: /' | tee -a "$LOGFILE"
    done
fi
# Append an API token only once, so two sonames backed by the same stack
# (libGLESv2.so.2 and libGLESv2.so) do not double-report it.
add_gpu_api() {
    for _a in $GPU_APIS; do [ "$_a" = "$1" ] && return 0; done
    GPU_APIS="$GPU_APIS $1"
}
GPU_APIS=""
GLES2_PROVIDER=""; GLES2_PROVIDER_HASH=""; GLES2_PROVIDER_ELF=""
EGL_PROVIDER=""
for gl in libmali.so libmali.so.1 libGLESv2.so.2 libGLESv2.so libGLESv1_CM.so.1 \
          libGL.so.1 libEGL.so.1 libgbm.so.1 libvulkan.so.1; do
    hit=""
    for d in $LDPATH_DIRS; do [ -e "$d/$gl" ] && { hit="$d/$gl"; break; }; done
    [ -n "$hit" ] || continue
    real=$(readlink -f "$hit" 2>/dev/null || echo "$hit")
    ver=$(dump_strings "$real" 2>/dev/null \
        | grep -oiE 'Mesa [0-9][0-9.]+|OpenGL ES [0-9.]+|OpenGL ES-CM [0-9.]+' | head -1)
    # Vendor identifies the stack flavor (Mali blob vs Mesa/panfrost vs
    # PowerVR), which decides which GL backend a core has to be built for.
    # Case-SENSITIVE and distinctive: a bare case-insensitive "lima"/"mesa"
    # matches unrelated substrings inside unrelated blobs.
    vendor=$(dump_strings "$real" 2>/dev/null \
        | grep -oE 'Mali-[A-Za-z0-9]+|ARM Ltd|Mesa[ /][0-9][0-9.]*|PowerVR|Adreno|Vivante|panfrost|etnaviv|lima_dri|libmali' \
        | head -1)
    elfp=$(elf_target "$real")
    say "gpu-lib: $gl -> $real ${ver:+($ver)}${vendor:+ [$vendor]} elf=${elfp:-unknown}"
    say "  hash: $(file_hash "$real")"
    case "$gl" in
        libmali*)   add_gpu_api mali ;;
        libGLESv2*)
            add_gpu_api gles2
            # Prefer the provider whose ABI matches the cores' target, exactly
            # as the libstdc++ scan does. Multilib firmware puts a 32-bit copy
            # earlier on the search path (/usr/lib32 on gkd-pixel2, a
            # .32bit_chroot on miyoo-flip), and taking the first hit reports an
            # armhf provider for an arm64 device -- a false mismatch, since the
            # real loader resolves an arm64 core to the arm64 copy.
            if [ -z "$GLES2_PROVIDER" ] \
               || { [ "$GLES2_PROVIDER_ELF" != "$PIPELINE_TARGET" ] \
                    && [ "${elfp:-unknown}" = "$PIPELINE_TARGET" ]; }; then
                GLES2_PROVIDER=$real
                GLES2_PROVIDER_HASH=$(file_hash "$real")
                GLES2_PROVIDER_ELF=${elfp:-unknown}
            fi
            ;;
        libGL.so*)  add_gpu_api gl ;;
        libEGL*)    add_gpu_api egl
                    [ -n "$EGL_PROVIDER" ] || EGL_PROVIDER=$real ;;
        libvulkan*) add_gpu_api vulkan ;;
    esac
done
say "gpu-apis:${GPU_APIS:- none}"
# A core that links libGLESv2 directly (parallel_n64) needs its soname to
# resolve for the CORE's ABI. Report the mismatch explicitly rather than
# letting a wrong-ABI copy read as a provider.
if [ -n "$GLES2_PROVIDER" ] && [ "$GLES2_PROVIDER_ELF" != "$PIPELINE_TARGET" ] \
   && { [ "$PIPELINE_TARGET" = arm64 ] || [ "$PIPELINE_TARGET" = armhf ]; }; then
    say "warning: GLESv2 provider elf=$GLES2_PROVIDER_ELF does not match pipeline target $PIPELINE_TARGET"
fi
say "effective-gles2-provider: ${GLES2_PROVIDER:-none} (elf=${GLES2_PROVIDER_ELF:-unknown})"
say "effective-egl-provider: ${EGL_PROVIDER:-none}"

sec "Installed core dependency resolution (loader truth)"
# The decisive evidence. For every libretro core installed on the device, ask
# the device's own loader to resolve its dependencies. A core that reports no
# missing sonames here is loadable; one that reports any is not, regardless of
# what a ceiling comparison says. This is what turns eligibility from an
# inference into an observation, and it is the only check that catches a core
# needing a provider the device simply does not have (GLES2 being the live
# example).
CORE_DIRS=""
# Still zero-argument by default; PROBE_CORE_DIRS is an optional escape hatch
# for firmware whose layout none of the known paths match.
for d in ${PROBE_CORE_DIRS:-} \
         /mnt/SDCARD/RetroArch/.retroarch/cores /mnt/SDCARD/RetroArch/.retroarch/cores64 \
         /mnt/SDCARD/Emu/.emu_setup/cores /mnt/SDCARD/cores /roms/cores \
         /usr/lib/libretro /usr/local/lib/libretro; do
    [ -d "$d" ] && CORE_DIRS="$CORE_DIRS $d"
done
# Fall back to a depth-limited search when the layout is unfamiliar.
if [ -z "$CORE_DIRS" ]; then
    for base in /mnt /roms /media /storage; do
        [ -d "$base" ] || continue
        for d in $(find "$base" -maxdepth 5 -type d -name 'cores*' 2>/dev/null | head -5); do
            CORE_DIRS="$CORE_DIRS $d"
        done
    done
fi
say "core-dirs:${CORE_DIRS:- none}"
CORE_COUNT=0; CORE_OK=0; CORE_BROKEN=0; CORE_FOREIGN=0
BROKEN_CORES=""; FOREIGN_CORES=""; ALL_MISSING=""

# Resolve one core's dependencies against the search path using DT_NEEDED. This
# is the requirement side, so it works for any ABI, but it models the loader's
# search rather than performing it.
dt_needed_missing() {
    _m=""
    for _n in $(needed_of "$1"); do
        [ "$(soname_path "$_n")" = absent ] && _m="$_m $_n"
    done
    printf '%s' "$_m"
}

for d in $CORE_DIRS; do
    for so in "$d"/*_libretro.so; do
        [ -r "$so" ] || continue
        CORE_COUNT=$((CORE_COUNT + 1))
        base=${so##*/}
        name=${base%_libretro.so}
        celf=$(elf_target "$so")
        # A core built for a different ABI than this device runs is not a
        # resolution question at all -- record it and move on, rather than
        # letting the loader's refusal read as a clean result.
        if [ -n "$celf" ] && [ "$celf" != other ] && [ "$celf" != "$PIPELINE_TARGET" ] \
           && { [ "$PIPELINE_TARGET" = arm64 ] || [ "$PIPELINE_TARGET" = armhf ]; }; then
            CORE_FOREIGN=$((CORE_FOREIGN + 1))
            FOREIGN_CORES="$FOREIGN_CORES $name"
            say "core: $base elf=$celf foreign-abi (device target $PIPELINE_TARGET) - not resolved"
            continue
        fi
        # Loader truth first. CRITICAL: empty output means the loader could not
        # report (foreign ABI, missing loader, stripped ldd), which is
        # UNDETERMINED, not "everything resolved". Only a non-empty report is
        # evidence, so fall back to DT_NEEDED whenever it is empty.
        method=$DEP_METHOD
        deps=""
        [ "$DEP_METHOD" = none ] || deps=$(loader_list "$so")
        if [ -n "$deps" ]; then
            miss=$(printf '%s\n' "$deps" | grep -i 'not found' | awk '{print $1}' | tr '\n' ' ')
        else
            method=dt-needed
            miss=$(dt_needed_missing "$so")
        fi
        miss=$(printf '%s' "$miss" | sed 's/^ *//; s/ *$//')
        if [ -n "$miss" ]; then
            CORE_BROKEN=$((CORE_BROKEN + 1))
            BROKEN_CORES="$BROKEN_CORES $name"
            ALL_MISSING="$ALL_MISSING $miss"
            say "core: $base elf=${celf:-unknown} via=$method MISSING: $miss"
        else
            CORE_OK=$((CORE_OK + 1))
            say "core: $base elf=${celf:-unknown} via=$method ok"
        fi
    done
done
[ "$CORE_COUNT" -eq 0 ] && say "no installed cores found (nothing to resolve)"
MISSING_UNIQ=$(printf '%s' "$ALL_MISSING" | tr ' ' '\n' \
    | grep -v '^$' | sort -u | tr '\n' ' ' | sed 's/ *$//')
say "cores-scanned: $CORE_COUNT"
say "cores-resolvable: $CORE_OK"
say "cores-unresolvable: $CORE_BROKEN"
say "cores-unresolvable-list:${BROKEN_CORES:- none}"
say "cores-foreign-abi: $CORE_FOREIGN"
say "cores-foreign-abi-list:${FOREIGN_CORES:- none}"
say "missing-sonames-union:${MISSING_UNIQ:- none}"

sec "Memory"
# Not a compiler flag, but a viability gate: whether heavy (N64/PSX/DOS) cores
# can realistically run, and headroom for aggressive-inlining build flavors.
if [ -r /proc/meminfo ]; then
    say "mem-total-kb: $(grep -i '^MemTotal' /proc/meminfo 2>/dev/null | awk '{print $2}')"
    say "mem-available-kb: $(grep -i '^MemAvailable' /proc/meminfo 2>/dev/null | awk '{print $2}')"
    say "swap-total-kb: $(grep -i '^SwapTotal' /proc/meminfo 2>/dev/null | awk '{print $2}')"
fi

sec "Frontend (RetroArch / libretro host)"
FE=""
for cand in retroarch ra32 ra64; do
    if have "$cand"; then FE=$(command -v "$cand"); break; fi
done
if [ -z "$FE" ]; then
    for p in /mnt/SDCARD/RetroArch/retroarch /usr/bin/retroarch /usr/local/bin/retroarch \
             /mnt/SDCARD/.retroarch/retroarch; do
        [ -x "$p" ] && { FE=$p; break; }
    done
fi
say "frontend-binary: ${FE:-not-found}"
FE_GL_APIS=""; FE_MISSING=""
if [ -n "$FE" ]; then
    say "frontend-hash: $(file_hash "$FE")"
    ver=$("$FE" --version 2>&1 | head -1 || true)
    say "frontend-version: ${ver:-unknown}"
    say "frontend-loader: $(interp_of "$FE")"
    say "frontend-elf-target: $(elf_target "$FE")"
    # Most cores never link GL themselves -- they ask the FRONTEND for a
    # context via SET_HW_RENDER + get_proc_address. So the frontend's own
    # linkage, not the core's, is what gates every HW-render core. Read it off
    # the frontend binary's DT_NEEDED.
    for n in $(needed_of "$FE"); do
        case "$n" in
            libGLESv2*) FE_GL_APIS="$FE_GL_APIS gles2" ;;
            libGL.so*)  FE_GL_APIS="$FE_GL_APIS gl" ;;
            libEGL*)    FE_GL_APIS="$FE_GL_APIS egl" ;;
            libvulkan*) FE_GL_APIS="$FE_GL_APIS vulkan" ;;
            libSDL2*)   FE_GL_APIS="$FE_GL_APIS sdl2" ;;
        esac
    done
    say "frontend-linked-video-apis:${FE_GL_APIS:- none}"
    FE_MISSING=$(missing_deps_of "$FE" | tr '\n' ' ' | sed 's/ *$//')
    say "frontend-missing-deps:${FE_MISSING:- none}"
    # --features is authoritative when the binary can run here; it lists the
    # video drivers actually compiled in, which linkage alone cannot show
    # (a dlopen-ing build links nothing yet still supports GL).
    feat=$("$FE" --features 2>&1 | tr -d '\r' | head -40 || true)
    if [ -n "$feat" ]; then
        say "frontend-features:"
        printf '%s\n' "$feat" | sed 's/^/  /' | tee -a "$LOGFILE" >/dev/null
        printf '%s\n' "$feat" | sed 's/^/  /' >>"$LOGFILE" 2>/dev/null
        for drv in gl glcore gles gles2 gles3 vulkan sdl2 drm kms; do
            printf '%s' "$feat" | grep -qi "[+]${drv}\b" \
                && say "  frontend-video-driver: $drv"
        done
    fi
fi
say "launcher-ld-library-path:${FE_LD_PATHS:- none}"

sec "Storage / rootfs"
if have df; then
    say "filesystems:"; df -h 2>/dev/null | tee -a "$LOGFILE" >/dev/null; df -h 2>/dev/null | sed 's/^/  /' | tee -a "$LOGFILE"
fi
say "rootfs-type: $(grep -E ' / ' /proc/mounts 2>/dev/null | head -1 | awk '{print $3}')"

sec "Environment"
say "LD_LIBRARY_PATH: ${LD_LIBRARY_PATH:-<unset>}"
say "HOME: ${HOME:-<unset>}"
say "PATH: ${PATH:-<unset>}"
say "searched-lib-dirs:$LDPATH_DIRS"

# ----------------------------------------------------------------------------
# Machine-readable capture block: transcribe straight into
# device-runtime-contracts.json (provider_observations + arch/ceiling).
# ----------------------------------------------------------------------------
sec "CAPTURE (machine-readable)"
say "capture.schema=device-probe-v3"
say "capture.machine=$(uname -m 2>/dev/null)"
say "capture.pipeline_target=$PIPELINE_TARGET"
say "capture.dynamic_loader=${LOADER:-unknown}"
say "capture.libc_max_glibc=$(max_symbol "${LIBC:-/nonexistent}" GLIBC)"
say "capture.effective_cxx_provider=${CXX_EFFECTIVE:-none}"
say "capture.effective_cxx_role=${CXX_EFFECTIVE_ROLE:-none}"
say "capture.effective_cxx_hash=${CXX_EFFECTIVE_HASH:-none}"
say "capture.effective_cxx_elf=${CXX_EFFECTIVE_ELF:-unknown}"
say "capture.effective_max_glibcxx=${CXX_EFFECTIVE_MAX:-none}"
say "capture.effective_max_cxxabi=${CXX_EFFECTIVE_CXXABI:-none}"
say "capture.cxx_provider_count=$idx"
say "capture.secondary_abi=${SECONDARY_ABI:-none}"
say "capture.secondary_abi_max_glibcxx=${SECONDARY_ABI_MAX:-none}"
say "capture.cpu_core=${CPU_CORE:-unknown}"
say "capture.cpu_implementer=${CPU_IMPL:-unknown}"
say "capture.cpu_part=${CPU_PART:-unknown}"
say "capture.suggested_mcpu=${SUGGESTED_MCPU:-unknown}"
say "capture.suggested_opt_flags=${SUGGESTED_OPT:-unknown}"
say "capture.gpu_apis=$(trim "${GPU_APIS:-none}")"
say "capture.gpu_nodes=$(trim "${GPU_NODES:-none}")"
say "capture.gles2_provider=${GLES2_PROVIDER:-none}"
say "capture.gles2_provider_hash=${GLES2_PROVIDER_HASH:-none}"
say "capture.gles2_provider_elf=${GLES2_PROVIDER_ELF:-unknown}"
say "capture.egl_provider=${EGL_PROVIDER:-none}"
say "capture.mem_total_kb=$(grep -i '^MemTotal' /proc/meminfo 2>/dev/null | awk '{print $2}')"
say "capture.frontend_binary=${FE:-none}"
say "capture.frontend_video_apis=$(trim "${FE_GL_APIS:-none}")"
say "capture.frontend_missing_deps=$(trim "${FE_MISSING:-none}")"
# The eligibility join reads these four: how deps were resolved, how many cores
# resolve, which do not, and which sonames are missing device-wide.
say "capture.dependency_resolution_method=$DEP_METHOD"
say "capture.cores_scanned=$CORE_COUNT"
say "capture.cores_resolvable=$CORE_OK"
say "capture.cores_unresolvable=$(trim "${BROKEN_CORES:-none}")"
say "capture.cores_foreign_abi=$(trim "${FOREIGN_CORES:-none}")"
say "capture.missing_sonames=$(trim "${MISSING_UNIQ:-none}")"
say "capture.libs_absent=$(trim "${LIB_ABSENT:-none}")"
say "capture.enforcing=false"
say ""
say "Probe complete. On-device log: $LOGFILE"
