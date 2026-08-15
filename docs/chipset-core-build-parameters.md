# Chipset and core build-parameter reference

This document is a human-readable snapshot of the build parameters in
[`core-builds.json`](../manifests/core-builds.json) and the typed machine
profiles in
[`chipset-tunings.json`](../manifests/chipset-tunings.json). Read a requested
chipset/core build by combining one chipset row with one core row below.

The manifest and pipeline validators remain authoritative. This document does
not create a build pin, prove that a recipe produced a Spruce branch binary,
or authorize publication. As of 2026-08-10, track cells without a manually
reviewed version-channel build pin remain deferred. Spruce `main` and
`Development` artifact bytes are comparison evidence only; a track assignment
instead binds an exact reproducible pin and must preserve the ordered
`main <= nightly <= edge` source policy against the parent captured when each
direct child TEST assignment is created, unless an exact outlier is authorized.
Later parent movement does not rewrite an admitted child's binding.

Snapshot inputs:

- core catalog file SHA-256:
  `a9ba3ee4e34e38367786164bd4da61b00ac459a76f0ca7a239a23be82c582964`;
- chipset registry file SHA-256:
  `ea2284a3fdbade2f1bdcd1c1bf1cdd444316a1f138accb43bbb4f11a28ae8da6`;
- chipset registry semantic SHA-256:
  `bfd465e63575b83a2ac6667c9c7aa864d169684cda7c360a2eb1e72d804eee00`;
- compiler mapping: `gcc-machine-flags-v1`.

The live runtime catalog validator is the effective recipe authority. The
current `core-builds.schema.json` does not yet describe every live direct-Make,
direct-CMake, overlay, submodule, and one-ABI field, so this guide does not
claim that generic JSON Schema validation alone proves the catalog.

## How parameters compose

The effective build is:

```text
locked architecture/toolchain contract
  + exact core recipe
  + optional typed chipset profile
```

Ambient `CFLAGS`, `CXXFLAGS`, `CPPFLAGS`, `LDFLAGS`, `ASMFLAGS`, `ASFLAGS`,
and Rust flag variables are scrubbed before execution. Chipset arguments are
resolved from a closed registry, added to C and C++ flags, and proved on every
visible target compile. Direct-CMake also receives the same machine arguments
through `ASMFLAGS`; `ASFLAGS` stays unset. The chipset layer adds no linker
flags.

The log validator recognizes these architecture baselines, but they are not
chipset-profile arguments:

| Catalog ABI | ELF/package location | Recognized target compilers | Recognized baseline |
|---|---|---|---|
| `arm64` | ELF64 AArch64 / `cores64` | `aarch64-linux-gnu-gcc`, `aarch64-linux-gnu-g++` | `-march=armv8-a` |
| `armhf` | ELF32 ARM hard-float / `cores` | `arm-a30-linux-gnueabihf-gcc`, `arm-a30-linux-gnueabihf-g++` | `-march=armv7-a -mfloat-abi=hard` |

Only the allowlisted ABI baseline plus the exact resolved profile arguments are
accepted. Duplicate baseline/profile arguments and any other `-march`,
`-mcpu`, `-mtune`, `-mfpu`, or `-mfloat-abi` fail the proof. A live profile's
exact `-mcpu` is therefore valid alongside the ABI baseline; an unapproved
`-mcpu` is not. Response-file-hidden machine flags also fail the proof.

## Established chipset parameters

These are accepted registry definitions. They are not evidence of a
performance improvement for every core.

| Requested chipset | ABI | Live profile | Exact added compiler arguments | Profile/fallback policy |
|---|---|---|---|---|
| `universal` | any catalog ABI | `universal-v1` | none | exact empty profile |
| `h700` | `arm64` | none | none | may use an admitted compatible universal cell; the device is unprobed and CPU tuning is unreviewed |
| `a133p` | `arm64` | `a133p-cortex-a53-v1` | `-mcpu=cortex-a53` | exact typed profile |
| `a33` | `armhf` | `a33-cortex-a7-v1` | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` | exact typed profile |
| `a523` | `arm64` | `a523-cortex-a55-v1` | `-mcpu=cortex-a55` | exact typed profile |
| `rk3326` | `arm64` | `rk3326-cortex-a35-v1` | `-mcpu=cortex-a35` | exact typed profile |
| `rk3566` | `arm64` | `rk3566-cortex-a55-v1` | `-mcpu=cortex-a55` | exact typed profile |
| `ssd202d` | `armhf` | `ssd202d-cortex-a7-v1` | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` | exact typed profile |

All non-universal profiles extend the empty `universal-v1` profile. There is
no fallback from one real chipset to another. These rows describe profile
availability and fallback policy, not a live track resolution: every current
track core is deferred and produces no build row. After pins are admitted, a
stable request resolves exact stable, compatible universal stable, exact test,
then compatible universal test. Both TEST fallbacks remain
`stability: test`/`unstable_fallback`; they are not promoted implicitly. A test
request resolves exact test, then compatible universal test. `libgametank`
uses the `direct-cargo` driver, for
which nonempty chipset tuning is currently rejected before execution.

The known runtime constraints still apply after an ABI/profile match. In
particular, SSD202D/Mini lacks a GLES2 provider and cannot run the ARMHF
`km_parallel_n64_xtreme_amped_turbo` GLES recipe; the A33/A30 provider case is
the viable ARMHF target for that core. H700 has not been probed at all.

The only supported way to request an established non-universal, nonempty tuned
candidate is by profile identity, for example:

```bash
python3 -B scripts/core_pipeline.py e2e \
  --runner-profile github-actions-sim \
  --core mgba \
  --tuning-profile a523-cortex-a55-v1 \
  --run-id actions-sim-mgba-a523-selected
python3 -B scripts/core_pipeline.py e2e \
  --runner-profile local \
  --core mgba \
  --tuning-profile a523-cortex-a55-v1 \
  --run-id local-mgba-a523-reproduction
```

These runs do not admit a result into a track. The simulated-Actions run is the
selected side and the native-local run is the independent reproduction. Their
artifact, metadata, package, normalized build semantics, and hardened resource
class must match, while valid log transcripts, timings, and resource counters
may differ. Then use `promote-tuned-variant`, followed by read-only
`core-track-plan-test` and `core-track-set-test` compare-and-swap admission.
A later `core-track-promote` is the separate STABLE approval step.
Universal and H700 controls do not use `--tuning-profile`. A universal control
omits both tuning and architecture selectors and builds the core's complete
catalog target set. For a dual-ABI core, an H700/ARM64 diagnostic uses
`--arch arm64`; that subset is not package-capable or promotable. A future
admitted compatible universal group is the track-policy path that projects a
portable pin to ARM64 for H700.

## Established per-core parameters

Legend:

- `LS`: `libretro-super`; the default row uses the core ID as `source_key` and
  collects `dist/unix/<core>_libretro.so` unless the row says otherwise.
- `CM`: direct CMake with `Unix Makefiles`, `Release`, explicit cross tools,
  Linux system name, and processor `aarch64` or `arm`.
- `DM`: direct Make with exact target tools.
- `Cargo`: `cargo zigbuild --locked` with the catalog target triple.
- `D:` C/C++ compile definitions; `MV:` Make variables; `P` means the hashed
  overlays in the overlay table are applied; `E=` is `SOURCE_DATE_EPOCH`.
- `U0` through `U6` and `SC` are hypotheses defined in the explicitly
  **untested** section. They are not current recipe inputs.

| Core | Catalog ABI | Established recipe parameters | Untested trials |
|---|---|---|---|
| `2048` | `arm64`, `armhf` | LS default | U0 |
| `81` | `arm64`, `armhf` | LS; pinned generated `src/version.c` SHA-256 `5a07d38a3bcd84ee5fa9abbdbe0bd706288d8ec4ee8095485447e35dc28a2862` | U0, U3 |
| `a5200` | `arm64`, `armhf` | LS default | U0 |
| `ardens` | `arm64`, `armhf` | CM `target=ardens_libretro`; `D: ARDENS_DEBUGGER=0 ARDENS_LIBRETRO=1 ARDENS_LLVM=0 ARDENS_PLAYER=0`; `E=1784658210` | U0, U3 |
| `arduous` | `arm64`, `armhf` | CM `target=arduous_libretro`; `E=1776706246` | U0, U3 |
| `atari800` | `arm64`, `armhf` | LS default | U0, U2 |
| `bk` | `arm64`, `armhf` | LS default | U0 |
| `bluemsx` | `arm64`, `armhf` | LS default | U0, U2 |
| `cap32` | `arm64`, `armhf` | LS default | U0, U3 |
| `chailove` | `arm64`, `armhf` | LS; P | U0, SC |
| `chimerasnes` | `arm64`, `armhf` | LS; existing upstream LTO | U0, SC |
| `crocods` | `arm64`, `armhf` | LS; P | U0, U3 |
| `daphne` | `arm64`, `armhf` | LS default | U0, U2, U4 |
| `dosbox_pure` | `arm64`, `armhf` | LS; P | U0, U2, U4 |
| `easyrpg` | `arm64`, `armhf` | CM `target=easyrpg_libretro`; bundled liblcf; ICU/XML/libsndfile/mpg123/ogg-vorbis ON; tests and optional desktop/audio stacks OFF; arch dependency prefix; P; `E=1784044064` | U0, U3, U4, U5 |
| `ecwolf` | `arm64`, `armhf` | LS default | U0, U4, SC |
| `fake08` | `arm64`, `armhf` | DM `-C platform/libretro V=1` | U0, U2 |
| `fbalpha2012` | `arm64`, `armhf` | LS; P | U0, U2, U4, U5 |
| `fbneo` | `arm64`, `armhf` | LS; ARMHF `D: HWCAP2_AES=1 HWCAP2_CRC32=16 HWCAP2_SHA1=4 HWCAP2_SHA2=8`; P; `E=1777823586` | U0, U4, U5, SC |
| `fceumm` | `arm64`, `armhf` | LS; P | U0, U2 |
| `ffmpeg` | `arm64`, `armhf` | LS; `MV: ARCH_AARCH64=0 ARCH_ARM=0 ARCH_X86=0 ARCH_X86_64=0 HAVE_SSA=0 LIBRETRO_EMBED_FFMPEG=1 OPENGL=0`; P; `E=1598579820` | U0, U3, U4, U5 |
| `flycast` | `arm64`, `armhf` | CM `target=flycast_libretro`; PIC/LIBRETRO ON; host-libzip/OpenMP/Vulkan OFF; ARM64 GLES, ARMHF GLES2; ARMHF P; `E=1767792512` | U0, U3, U4, U5 |
| `fmsx` | `arm64`, `armhf` | LS default | U0, U2 |
| `freechaf` | `arm64`, `armhf` | LS default | U0 |
| `freeintv` | `arm64`, `armhf` | LS default | U0 |
| `frodo` | `arm64`, `armhf` | LS default | U0, U3 |
| `fuse` | `arm64`, `armhf` | LS default | U0, U3 |
| `gambatte` | `arm64`, `armhf` | LS default | U0, U2 |
| `gearboy` | `arm64`, `armhf` | LS default | U0, U3 |
| `gearcoleco` | `arm64`, `armhf` | LS default | U0, U3 |
| `gearsystem` | `arm64`, `armhf` | LS default | U0, U3 |
| `genesis_plus_gx` | `arm64`, `armhf` | LS; P | U0, U2, U5 |
| `genesis_plus_gx_wide` | `arm64`, `armhf` | LS; P | U0, U2, U5 |
| `gme` | `arm64`, `armhf` | LS default | U0, U1 |
| `gpsp` | `arm64`, `armhf` | DM `platform=arm64` or `platform=armv7hardfloat` | U0, SC |
| `gw` | `arm64`, `armhf` | LS default | U0 |
| `handy` | `arm64`, `armhf` | LS default | U0, U2 |
| `hatari` | `arm64`, `armhf` | LS; `E=1781097623` | U0, SC |
| `km_duckswanstation_xtreme_amped` | `armhf` only | CM `target=swanstation_libretro`, renamed to canonical artifact; `E=1687912698`; existing upstream LTO | U0, U4 |
| `km_parallel_n64_xtreme_amped_turbo` | `armhf` only | DM `platform=unix WITH_DYNAREC=arm FORCE_GLES=1 NOSSE=1`; output `parallel_n64_libretro.so` renamed to `km_parallel_n64_xtreme_amped_turbo_libretro.so`; P; `E=1671482574` | U0, U4 |
| `libgametank` | `arm64`, `armhf` | Cargo in `tools/gte/libretro`; `zigbuild --locked --release`; lock SHA-256 `b8c66e6924352eb35603df6a921ef43ecd91fa6b79ab8b44def74098069ce360`; `aarch64-unknown-linux-gnu.2.23` or `armv7-unknown-linux-gnueabihf.2.23`; `E=1784593754` | U6 |
| `lowresnx` | `arm64`, `armhf` | LS; P | U0 |
| `lutro` | `arm64`, `armhf` | LS default | U0, U3 |
| `mame2003_plus` | `arm64`, `armhf` | LS; `E=1777763287` | U0, U2, U4, U5 |
| `mednafen_lynx` | `arm64`, `armhf` | LS default | U0, U2 |
| `mednafen_ngp` | `arm64`, `armhf` | LS default | U0, U2 |
| `mednafen_pce_fast` | `arm64`, `armhf` | LS default | U0, U2 |
| `mednafen_pcfx` | `arm64`, `armhf` | LS; `MV: IS_X86=0` | U0, U2, U4 |
| `mednafen_supafaust` | `arm64`, `armhf` | LS default | U0, U2 |
| `mednafen_supergrafx` | `arm64`, `armhf` | LS; P | U0, U2 |
| `mednafen_vb` | `arm64`, `armhf` | LS default | U0, U2 |
| `mednafen_wswan` | `arm64`, `armhf` | LS default | U0, U2 |
| `mgba` | `arm64`, `armhf` | LS default | U0, U3 |
| `mu` | `arm64`, `armhf` | LS default | U0 |
| `mupen64plus_next` | `arm64` only | LS; `MV: FORCE_GLES=1 WITH_DYNAREC=aarch64`; all submodule fetching disabled (`build.submodules=false`) | U0, U4, SC |
| `neocd` | `arm64`, `armhf` | LS; ARMHF `D: HWCAP2_AES=0 HWCAP2_CRC32=0 HWCAP2_SHA1=0 HWCAP2_SHA2=0`; existing upstream LTO | U0, U4, SC |
| `nestopia` | `arm64`, `armhf` | LS default | U0, U2 |
| `np2kai` | `arm64`, `armhf` | LS; P | U0, U2 |
| `numero` | `arm64`, `armhf` | LS default | U0 |
| `o2em` | `arm64`, `armhf` | LS default | U0 |
| `opera` | `arm64`, `armhf` | LS default | U0, U2 |
| `parallel_n64` | `arm64` only | LS; `MV: GLES=1 NOSSE=1 WITH_DYNAREC=aarch64`; `E=1784512327` | U0, U4, SC |
| `pcsx_rearmed` | `arm64`, `armhf` | LS; ARMHF `D: HWCAP2_AES=0 HWCAP2_CRC32=0 HWCAP2_SHA1=0 HWCAP2_SHA2=0`; `E=1782602899` | U0, U4, SC |
| `picodrive` | `arm64`, `armhf` | LS; output `libretro-picodrive/picodrive_libretro.so`; ARMHF `D: HWCAP2_AES=1 HWCAP2_CRC32=16 HWCAP2_SHA1=4 HWCAP2_SHA2=8`; `picodrive-v1` uses `git_revision=-f0d4a011` and host tools `CYCLONE_CC=gcc CYCLONE_CXX=g++`; ARMHF P; `E=1775134253`; existing upstream LTO | U0 |
| `pokemini` | `arm64`, `armhf` | LS default | U0 |
| `potator` | `arm64`, `armhf` | LS default | U0 |
| `prboom` | `arm64`, `armhf` | LS default | U0, U2 |
| `prosystem` | `arm64`, `armhf` | LS default | U0 |
| `puae2021` | `arm64`, `armhf` | LS; `E=1784565128` | U0, U3, U4, U5 |
| `puzzlescript` | `arm64`, `armhf` | LS; recursive submodules disabled; P | U0 |
| `px68k` | `arm64`, `armhf` | LS default | U0, SC |
| `quasi88` | `arm64`, `armhf` | LS default | U0 |
| `quicknes` | `arm64`, `armhf` | LS default | U0, U2 |
| `race` | `arm64`, `armhf` | LS default | U0 |
| `reminiscence` | `arm64`, `armhf` | LS default | U0, U2 |
| `retro8` | `arm64`, `armhf` | LS; P | U0, U3 |
| `sameduck` | `arm64`, `armhf` | LS default | U0 |
| `snes9x` | `arm64`, `armhf` | LS; existing upstream LTO | U0 |
| `snes9x2002` | `arm64`, `armhf` | LS default | U0, U3 |
| `snes9x2005` | `arm64`, `armhf` | LS default | U0, U2 |
| `snes9x2005_plus` | `arm64`, `armhf` | LS; `MV: USE_BLARGG_APU=1` | U0, U2 |
| `snes9x2010` | `arm64`, `armhf` | LS; existing upstream LTO | U0 |
| `squirreljme` | `armhf` only | CM source `nanocoat`, `target=squirreljme_libretro`, `D: SQUIRRELJME_ENABLE_FRONTEND_LIBRETRO=ON`; P; `E=1784151532` | U0, U5 |
| `stella2014` | `arm64`, `armhf` | LS default | U0, U2 |
| `swanstation` | `arm64` only | CM `target=swanstation_libretro`; P; `E=1782767217`; existing upstream LTO | U0, U4 |
| `tgbdual` | `arm64`, `armhf` | LS default | U0, SC |
| `theodore` | `arm64`, `armhf` | LS default | U0 |
| `tic80` | `arm64`, `armhf` | CM source `core`, `target=tic80_libretro`; LIBRETRO ON; demo carts/player/SDL/Sokol/MRuby OFF; `E=1777441655`; existing upstream LTO | U0, U4 |
| `tyrquake` | `arm64`, `armhf` | LS; `E=1784135314` | U0, U2 |
| `uae4arm` | `armhf` only | LS default | U0, U3, U4 |
| `uw8` | `arm64`, `armhf` | LS default | U0 |
| `uzem` | `arm64`, `armhf` | LS default | U0, U3 |
| `vecx` | `arm64`, `armhf` | LS; `MV: HAS_GPU=0` | U0 |
| `vemulator` | `arm64`, `armhf` | LS default | U0, U1 |
| `vice_x64` | `arm64`, `armhf` | LS source directory `libretro-vice`; `source_key=vice_x64`; `E=1780486798` | U0, U3, U4 |
| `vice_xvic` | `arm64`, `armhf` | LS source directory `libretro-vice`; `source_key=vice_xvic`; `E=1780486798` | U0, U3 |
| `x1` | `arm64`, `armhf` | LS; P | U0, SC |
| `yabasanshiro` | `arm64` only | DM `-C yabause/src/libretro platform=arm64 FORCE_GLES=1` | U0, U4, SC |

The eight one-ABI exclusions above are catalog policy. They must not be filled
by copying an artifact from another directory. In particular, the Spruce
ARMHF `swanstation` path is an invalid x86-64 ELF, while Spruce's AArch64
`uae4arm` is a valid observed artifact but is not a catalog target.

Fifteen catalog-supported branch cells are currently explicit `not_shipped`:
`2048:arm64`, `arduous:arm64`, `bk:arm64`, `ffmpeg:armhf`, `frodo:arm64`,
`genesis_plus_gx_wide:armhf`, `lutro:arm64`, `mu:arm64`, `numero:arm64`,
`retro8:armhf`, `snes9x2002:arm64`, `snes9x2005:arm64`,
`snes9x2005_plus:arm64`, `snes9x2010:arm64`, and `uw8:arm64`.

### Exact direct-CMake expansion

All eight `CM` rows use `Unix Makefiles`, `Release`, the catalog target shown
below, Linux as the target system, and `aarch64`/`arm` as the processor. Empty
definition sets are intentional.

| Core | CMake source (`-S`) | Target | Output path | Common definitions | ABI definitions |
|---|---|---|---|---|---|
| `ardens` | clone root | `ardens_libretro` | `ardens_libretro.so` | `ARDENS_DEBUGGER=0`, `ARDENS_LIBRETRO=1`, `ARDENS_LLVM=0`, `ARDENS_PLAYER=0` | none |
| `arduous` | clone root | `arduous_libretro` | `arduous_libretro.so` | none | none |
| `easyrpg` | clone root | `easyrpg_libretro` | `easyrpg_libretro.so` | `LIBLCF_WITH_ICU=ON`, `LIBLCF_WITH_XML=ON`, `PLAYER_BUILD_LIBLCF=ON`, `PLAYER_ENABLE_TESTS=OFF`, `PLAYER_TARGET_PLATFORM=libretro`, `PLAYER_WITH_FLUIDLITE=OFF`, `PLAYER_WITH_FLUIDSYNTH=OFF`, `PLAYER_WITH_FREETYPE=OFF`, `PLAYER_WITH_LHASA=OFF`, `PLAYER_WITH_LIBSNDFILE=ON`, `PLAYER_WITH_MPG123=ON`, `PLAYER_WITH_OGGVORBIS=ON`, `PLAYER_WITH_OPUS=OFF`, `PLAYER_WITH_SAMPLERATE=OFF`, `PLAYER_WITH_SPEEXDSP=OFF`, `PLAYER_WITH_WILDMIDI=OFF`, `PLAYER_WITH_XMP=OFF` | ARM64 `CMAKE_PREFIX_PATH=/usr/local/easyrpg-deps-arm64`; ARMHF `CMAKE_PREFIX_PATH=/usr/local/easyrpg-deps-armhf` |
| `flycast` | clone root | `flycast_libretro` | `flycast_libretro.so` | `CMAKE_POSITION_INDEPENDENT_CODE=TRUE`, `LIBRETRO=ON`, `USE_HOST_LIBZIP=OFF`, `USE_OPENMP=OFF`, `USE_VULKAN=OFF` | ARM64 `USE_GLES=ON`; ARMHF `USE_GLES2=ON` |
| `km_duckswanstation_xtreme_amped` | clone root | `swanstation_libretro` | `swanstation_libretro.so`, renamed to `km_duckswanstation_xtreme_amped_libretro.so` | none | ARMHF only |
| `squirreljme` | `nanocoat` | `squirreljme_libretro` | `bin/squirreljme_libretro.so` | `SQUIRRELJME_ENABLE_FRONTEND_LIBRETRO=ON` | ARMHF only |
| `swanstation` | clone root | `swanstation_libretro` | `swanstation_libretro.so` | none | ARM64 only |
| `tic80` | `core` | `tic80_libretro` | `bin/tic80_libretro.so` | `BUILD_DEMO_CARTS=OFF`, `BUILD_LIBRETRO=ON`, `BUILD_PLAYER=OFF`, `BUILD_SDL=OFF`, `BUILD_SOKOL=OFF`, `BUILD_WITH_MRUBY=OFF` | none |

### Exact native version-macro inputs

These 38 values are artifact-affecting recipe inputs. The value column uses a
JSON string representation so intentional leading spaces and hyphens remain
visible. A dash in the scope/date columns means the field is absent.

| Core | Derivation | Compiler scope | Exact value | Git date |
|---|---|---|---|---|
| `2048` | `native-space-short7-v1` | `c` | `" c90437d"` | — |
| `a5200` | `hyphen-short7-v1` | — | `"-23c1ea4"` | — |
| `atari800` | `native-space-short7-v1` | `c` | `" 9d3bcf2"` | — |
| `bluemsx` | `native-space-short7-v1` | `c` | `" 5f595c7"` | — |
| `cap32` | `native-space-short7-v1` | `c` | `" 4abfb8b"` | — |
| `crocods` | `native-space-short7-v1` | `c` | `" 87bbb3d"` | — |
| `fbneo` | `fbneo-native-short9-date-v1` | `cxx` | `"9d7716aa2"` | `260503` |
| `fceumm` | `native-space-short7-v1` | `c` | `" 718c5a2"` | — |
| `fmsx` | `native-space-short7-v1` | — | `" f013e21"` | — |
| `gambatte` | `native-space-short7-v1` | `cxx` | `" dfc1655"` | — |
| `gearboy` | `native-git-describe-v1` | — | `"3.8.9-8-g36d723f"` | — |
| `gearcoleco` | `native-git-describe-v1` | — | `"1.6.6-11-g1123457"` | — |
| `gearsystem` | `native-git-describe-v1` | — | `"3.9.12-5-g4f029e4"` | — |
| `genesis_plus_gx` | `native-space-short7-v1` | `c` | `" fa4dca5"` | — |
| `genesis_plus_gx_wide` | `native-space-short7-v1` | `c` | `" 29d9d10"` | — |
| `handy` | `native-space-short7-v1` | `cxx` | `" bc55d46"` | — |
| `lowresnx` | `native-space-short7-v1` | `c` | `" 35adc1a"` | — |
| `mame2003_plus` | `native-space-short8-v1` | `c` | `" 5373e38e"` | — |
| `mednafen_pcfx` | `native-space-short7-v1` | `cxx` | `" 650c30e"` | — |
| `mednafen_supafaust` | `hyphen-short7-v1` | `cxx` | `"-2b93c0d"` | — |
| `mednafen_supergrafx` | `native-space-short7-v1` | `cxx` | `" 3c6fcd3"` | — |
| `mednafen_wswan` | `native-space-short7-v1` | — | `" da6d0d9"` | — |
| `mgba` | `native-space-short9-v1` | `c` | `" 6dce57eef"` | — |
| `nestopia` | `hyphen-short7-v1` | `cxx` | `"-b0fd87d"` | — |
| `pokemini` | `native-space-short7-v1` | — | `" bb009b1"` | — |
| `potator` | `native-space-short7-v1` | `c` | `" 227c5f6"` | — |
| `prosystem` | `hyphen-short7-v1` | — | `"-363b6df"` | — |
| `quicknes` | `hyphen-short7-v1` | `cxx` | `"-26bb785"` | — |
| `race` | `native-space-short7-v1` | `c` | `" c7810dd"` | — |
| `snes9x` | `hyphen-short7-v1` | `cxx` | `"-185488c"` | — |
| `snes9x2005` | `native-space-short7-v1` | `c` | `" b603569"` | — |
| `snes9x2005_plus` | `native-space-short7-v1` | `c` | `" b603569"` | — |
| `stella2014` | `native-space-short7-v1` | — | `" 4a7da82"` | — |
| `tgbdual` | `native-space-short7-v1` | `cxx` | `" bf816b0"` | — |
| `uzem` | `native-space-short7-v1` | — | `" d4fe82c"` | — |
| `vecx` | `native-space-short7-v1` | — | `" 8f671cc"` | — |
| `vice_x64` | `native-space-short10-v1` | — | `" 7946cfa0d3"` | — |
| `vice_xvic` | `native-space-short10-v1` | — | `" 7946cfa0d3"` | — |

## Untested flags and build-parameter experiments

Everything in this section is a hypothesis. None of these codes means that the
flag is accepted by the current CLI, faster, correct, reproducible, compatible
with a device, or eligible for a track. Run one variable at a time against the
unchanged established recipe.

| Code | Proposed experiment | Exact candidate input | Notes |
|---|---|---|---|
| U0 | Machine-profile-only control | Existing real chipset: use its exact live nonempty profile. Universal: untuned full-target E2E. H700: untuned `--arch arm64` diagnostic, or a future admitted universal-group projection. Add no other flags. | Safest first measurement. An architecture diagnostic is not a promotable package. H700 remains universal and unprobed. Nonempty tuning is not supported for `direct-cargo`. |
| U1 | Add a missing conventional optimizer | Replace the current absence of an optimization flag with `-O2` | Recommended first for `gme` and `vemulator`, whose representative exact logs show no `-O*`. |
| U2 | Optimization-level A/B | Replace the existing optimization level with `-O3` | Never append a second ambiguous `-O` flag. Compare against the exact current level. |
| U3 | Link-time optimization A/B | C/C++ compile and final link: `-flto=1`; archives: matching `gcc-ar`/`gcc-ranlib`; CMake: `CMAKE_INTERPROCEDURAL_OPTIMIZATION=ON` | Keep the existing optimization level. Do not add this to a core already using upstream LTO. |
| U4 | Profile-guided optimization | Training compile and final link: `-fprofile-generate`; candidate compile and final link: `-fprofile-use -fprofile-correction` | Pin the profile-data hash and training corpus description. PGO is workload-biased and must run on target-class hardware. |
| U5 | Size/I-cache A/B | Compile: `-Os -ffunction-sections -fdata-sections`; final link: `-Wl,--gc-sections` | May reduce size rather than improve speed. Verify registration tables and exported symbols are retained. |
| U6 | Rust release-shape A/B | `RUSTFLAGS='-C opt-level=3 -C lto=thin -C codegen-units=1'` | `libgametank` only; future contract work is required because tuned direct-Cargo and arbitrary Rust flags are currently rejected. |
| SC | Strict-math one-variable control | Current `-Ofast`: replace with `-O3` and remove or negate any separately present `-ffast-math`, retaining all other optimization flags. Standalone `-ffast-math`: remove or negate only that flag while retaining the current effective `-O` level. | Measures whether aggressive math changes state, audio, video, or determinism without also changing the optimization level. It is a correctness control, not an assumption that strict math is faster. |

The portable ARM64 `-mtune=cortex-a53` idea recorded in the device design is
also a reasonable scheduling-only experiment. It is deliberately not U0: no
live universal profile admits it, and the current candidate resolver rejects
every empty or universal profile. Supporting it requires a pipeline, schema,
resolver, and contract extension plus new identities and complete evidence;
adding a profile alone is insufficient. Do not pair
`-mtune=<cpu>` with the same existing `-mcpu=<cpu>`; the registry rejects that
redundancy.

Representative logs already show LTO in `chimerasnes`,
`km_duckswanstation_xtreme_amped`, `neocd`, `picodrive`, `snes9x`,
`snes9x2010`, `swanstation`, and `tic80`. Preserve that as the control instead
of adding a second LTO setting.

Representative logs already contain `-Ofast` or `-ffast-math` for `chailove`,
`chimerasnes`, `ecwolf`, `fbneo`, `gpsp`, `hatari`, `mupen64plus_next`,
`neocd`, `parallel_n64`, `pcsx_rearmed`, `px68k`, `tgbdual`, `x1`, and the
current portable `yabasanshiro` recipe. Do not recommend blanket `-Ofast` or
`-ffast-math`; use SC to measure the correctness cost instead.

Never use `-march=native`: the build container host is not the target device.
Do not add CRC, crypto, dot-product, FP16, or other ISA extensions without
captured HWCAP evidence for every device claimed by that exact artifact.

Graphics and dynarec settings are also not generic optimization flags. Retain
the established Flycast GLES/GLES2 split, the exact N64 dynarec/GLES/NOSSE
settings, and YabaSanshiro's portable `FORCE_GLES=1` path. Do not combine the
ARMHF KM Parallel GLES recipe with SSD202D/Mini: its required GLES2 provider is
known absent there; current provider evidence supports the A33/A30 case.
Vulkan, OpenMP, GPU
backends, and vendor EGL/GLES libraries require separate runtime-provider and
device-flavor evidence; CPU/chipset identity alone does not admit them.

### How a future experiment must be encoded

| Parameter type | Required repository representation |
|---|---|
| non-universal machine selection | New or existing nonempty typed profile in `chipset-tunings.json`, then `--tuning-profile <profile-id>` |
| nonempty portable/universal scheduling | Pipeline, schema, resolver, and contract extension; the current candidate CLI rejects universal profiles |
| C/C++ optimization or link flag | Versioned catalog recipe field plus validator, normalized contract, compile/link-log proof, and new identities; there is no arbitrary flag passthrough |
| CMake option | Reviewed `build.cmake.defines` entry and regenerated recipe evidence |
| Make option | Reviewed `build.make_variables` or driver-specific `build.make_args` entry and regenerated recipe evidence |
| Cargo/Rust option | New direct-Cargo contract/schema support; current arbitrary Rust flags are scrubbed |

### Minimum acceptance gate

Before describing an experiment as a better build, require all of the
following:

1. two independent builds with identical artifact, metadata, and package
   bytes under the same final pipeline bundle;
2. exact source/tree/submodule, recipe, toolchain, tuning, job-count, path, and
   `SOURCE_DATE_EPOCH` identities;
3. ELF class/machine/ARMHF float ABI, `DT_NEEDED` provider, and exported
   `retro_*` ABI validation;
4. compile and link logs proving each intended flag exactly once and rejecting
   conflicting or ambient flags;
5. a versioned workload with frame-time distribution, audio underruns, RSS,
   thermal throttling, and sustained clock measurements, not just build time;
6. savestate, audio/video, and deterministic-state comparisons against the
   established build; and
7. load and playback smoke on every claimed target chipset.

Use distributable or clean-room workloads for tracked performance fixtures.
Keep proprietary local content out of Git, synchronization, publication, and
tracked profile data.

## Hashed overlay inputs

The manifest additionally pins patch, preimage, and postimage hashes. Paths
are listed here to make the per-core recipe readable; the manifest owns the
hashes.

| Core | ABI | Overlay paths |
|---|---|---|
| `chailove` | both | `patches/chailove/makefile-echo-compile.patch`; `patches/chailove/makefile-sort-wildcard-sources.patch` |
| `crocods` | both | `patches/crocods/makefile-sort-wildcard-sources.patch` |
| `dosbox_pure` | both | `patches/dosbox_pure/makefile-echo-and-sort.patch` |
| `easyrpg` | both | `patches/easyrpg/liblcf-pinned-clone.patch` |
| `fbalpha2012` | both | `patches/fbalpha2012/makefile-sort-wildcard-sources.patch` |
| `fbneo` | both | `patches/fbneo/makefile-sort-wildcard-sources.patch` |
| `fceumm` | both | `patches/fceumm/makefile-sort-wildcard-sources.patch` |
| `ffmpeg` | both | `patches/ffmpeg/makefile-ffmpeg-sort-wildcard-sources.patch` |
| `flycast` | `armhf` | `patches/flycast/lzma-hwcap2-guards.patch` in submodule `core/deps/libchdr` |
| `genesis_plus_gx` | both | `patches/genesis_plus_gx/makefile-sort-wildcard-sources.patch` |
| `genesis_plus_gx_wide` | both | `patches/genesis_plus_gx_wide/makefile-sort-wildcard-sources.patch` |
| `km_parallel_n64_xtreme_amped_turbo` | `armhf` | `patches/km_parallel_n64_xtreme_amped_turbo/makefile-fcommon.patch`; `glide64-rdp-gspvertex-def.patch`; `rdp-gspvertex-extern.patch`; `glsm-gldouble-typedef.patch`; `parallel-al-stdexcept.patch` in the same directory |
| `lowresnx` | both | `patches/lowresnx/makefile-sort-wildcard-sources.patch` |
| `mednafen_supergrafx` | both | `patches/mednafen_supergrafx/makefile-sort-wildcard-sources.patch` |
| `np2kai` | both | `patches/np2kai/makefile-sort-wildcard-sources.patch`; `patches/np2kai/makefile-libretro-sort-wildcard-sources.patch` |
| `picodrive` | `armhf` | `patches/picodrive/tools-makefile-single-line-offsets.patch` |
| `puzzlescript` | both | `patches/puzzlescript/makefile-sort-wildcard-sources.patch` |
| `retro8` | both | `patches/retro8/makefile-sort-wildcard-sources.patch` |
| `squirreljme` | `armhf` | `patches/squirreljme/system-map-arm32-or.patch`; `decode-host-cc.patch`; `sourceize-host-cc.patch` in the same directory |
| `swanstation` | `arm64` | `patches/swanstation/openbios-cmake-3.16.patch` |
| `x1` | both | `patches/x1/makefile-sort-wildcard-sources.patch` |
