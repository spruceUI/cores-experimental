# Compiler flags

What the boards and profiles append, why, and what is deliberately left out.
The research behind it (sources for every claim, and the core Makefiles read at
their pinned commits) was recorded in October 2026 outside this repository, in
the spruce workspace's `artifacts/cores-flags-research-20261007/`.

## Boards

| board | flags | why |
|---|---|---|
| `universal` | none | the catalog build; arm64 is `-march=armv8-a`, armhf is the A30 toolchain's default (`cortex-a7`, `vfpv4-d16`, ARM mode, hard float), so no NEON |
| `a133p`, `h700` | `-mcpu=cortex-a53` | both are quad Cortex-A53 (the H700 is the H616/H618 die) |
| `a523`, `rk3566` | `-mcpu=cortex-a55` | A523 is 8 × A55 (not big.LITTLE), RK3566 4 × A55 |
| `rk3326` | `-mcpu=cortex-a35` | quad Cortex-A35 |
| `a33`, `ssd202d` | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` | both Cortex-A7 with NEON and VFPv4; the Miyoo Mini's own toolchain defaults to exactly this |

- **A55 builds usually equal A53 builds.** GCC (9 and 13) has no Cortex-A55 tuning
  model and schedules it like the A53; only ARMv8.2 instructions differ, which
  emulators rarely use.
- **`-mcpu=cortex-a53` and `-mcpu=cortex-a35` assume the CRC32 extension**; GCC
  always does for those CPUs.
- **ARM64 always has NEON**, so arm64 boards need no NEON flag. The armhf toolchain
  already defaults to ARM (not Thumb) mode, so `-marm` adds nothing.

## Profiles

- `max` is `-O3`. On the armhf toolchain (GCC 13) `-O2` already auto-vectorizes; on
  the arm64 toolchain (GCC 9) only `-O3` does, so `max` changes more on arm64.
  `-O3` is not reliably faster on the small-cache A7, A35 and A53 cores: measure.
- `debug` is `-O0 -g`. Some cores rely on the optimizer to drop references to code
  they never compile (mame2003_plus then fails to load); use `debug-og` there.
- No profile uses `-ffast-math` or `-funsafe-math-optimizations`: emulators depend on
  exact floating point, and FBNeo's own Makefile keeps fast-math opt-in after a
  correctness bug.

## NEON switches (`neon` in the catalog)

`-mfpu=neon-vfpv4` makes the compiler define `__ARM_NEON__`. Some cores then call
NEON assembly that their makefile only compiles under a switch, so the build fails
to link; others simply never reach their NEON code. A core gets a `neon` entry once
its switch is verified by a real a33 build:

| core | switch | effect |
|---|---|---|
| km_parallel_n64_xtreme_amped_turbo | `HAVE_NEON=1` | compiles libretro-common's NEON audio converters and resampler; without it the NEON build does not link |
| uae4arm | `HAVE_NEON=1` | compiles its NEON helper (`neon_helper.s`) and NEON code paths |

Checked and not needed: `HAVE_NEON=1` changes nothing for chimerasnes, mgba,
genesis_plus_gx(_wide), mame2003_plus and opera (only their `classic_armv7_a7`-style
platform blocks set it, and nothing reads it under `platform=unix`). pcsx_rearmed
probes `$(CC)` itself, so the board flags alone switch it to its NEON GPU and NEON
assembly (`BUILTIN_GPU: neon`, `NEON_ASM: 1`) where the universal armhf build uses
the software `peops` renderer.

## Worth benchmarking, not defaults

| candidate | why | risk |
|---|---|---|
| `-fno-plt -fno-semantic-interposition -fvisibility=hidden` as an extra profile | fewer indirect calls in a shared-object core | a core that exports `retro_*` only through a version script with an old `libretro.h` would lose its exports (the load test catches it) |
| `-mfix-cortex-a53-835769` on a133p/h700 | off by default in this GCC 9 (843419 is already on) | none known; depends on the silicon revision |
| `-mcpu=cortex-a55+crypto` on a523/rk3566 | the silicon has it | no core in the catalog uses crypto instructions |
| gpsp with `platform=miyoomini` on ssd202d | upstream's device-specific recipe | it adds `-flto`, which made Flycast slower here |
| per-core `-flto` | some cores gain | measured slower for Flycast; never as a blanket flag |
| mupen64plus_next / parallel_n64 NEON RSP paths | unused fast paths | they need `-funsafe-math-optimizations` |
