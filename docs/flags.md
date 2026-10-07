# Compiler flags

Why the boards and profiles use the flags they do, and what was left out on
purpose.

## Boards

| board | flags | why |
|---|---|---|
| `universal` | none | the build spruce ships; arm64 targets plain ARMv8-A, armhf the A30 toolchain's default (Cortex-A7, no NEON) |
| `a133p`, `h700` | `-mcpu=cortex-a53` | both are quad Cortex-A53 |
| `a523`, `rk3566` | `-mcpu=cortex-a55` | the A523 is 8 × A55, the RK3566 4 × A55 |
| `rk3326` | `-mcpu=cortex-a35` | quad Cortex-A35 |
| `a33`, `ssd202d` | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` | Cortex-A7 with NEON; the Miyoo Mini's own toolchain defaults to NEON-VFPv4 and hard float too |

- GCC has no separate Cortex-A55 tuning and treats it like the A53, so A55 and
  A53 builds are usually identical.
- ARM64 always has NEON, so the arm64 boards need no NEON flag.

## Profiles

- `max` adds `-O3`, except to compiles that already use `-Ofast` (chimerasnes,
  neocd, parallel_n64, pcsx_rearmed): a later `-O3` would switch off the
  fast-math that `-Ofast` turns on.
- Most cores build at `-O2`, so `max` changes their code; about 40 already use
  `-O3`, so for them only the board flags matter. gme passes no `-O` at all, so
  its `release` build is unoptimized.
- `-O3` is not always faster on these small-cache CPUs: measure before shipping it.
- `debug` (`-O0`) breaks cores that rely on the optimizer to remove calls to code
  they never compile; mame2003_plus is one. Use `debug-og` for those.
- No profile uses `-ffast-math`: emulators depend on exact floating point.

## NEON switches

With the a33 and ssd202d flags, the compiler tells the code NEON is available
(`__ARM_NEON__`). Some cores then call
NEON assembly that their makefile only builds when a switch is set, and fail to
link; others never reach their NEON code. The catalog's `neon` field sets the
switch for those builds only, and an entry is added once a real a33 build
confirms it:

| core | switch | effect |
|---|---|---|
| km_parallel_n64_xtreme_amped_turbo | `HAVE_NEON=1` | builds libretro-common's NEON audio code; without it the build does not link |
| uae4arm | `HAVE_NEON=1` | builds its NEON helper and NEON code paths |

`HAVE_NEON=1` was tried and changes nothing for chimerasnes, mgba,
genesis_plus_gx(_wide), mame2003_plus and opera. pcsx_rearmed needs no switch:
it detects NEON itself and switches to its NEON renderer on a33 and ssd202d,
where the `universal` armhf build uses the slower software renderer.

## Worth benchmarking, not defaults

| candidate | possible gain | risk |
|---|---|---|
| `-fno-plt -fno-semantic-interposition -fvisibility=hidden` | fewer indirect calls | a core exporting `retro_*` through an old `libretro.h` loses its exports (the load test catches it) |
| `-mfix-cortex-a53-835769` on a133p, h700 | works around an A53 erratum; off by default in this GCC | depends on the chip revision |
| `-mcpu=cortex-a55+crypto` on a523, rk3566 | the chips have it | no core here uses crypto instructions |
| gpsp's `platform=miyoomini` recipe on ssd202d | upstream's tuned build for the Mini | it includes `-flto` |
| `-flto` per core | some cores gain | made Flycast slower; never as a blanket flag |
| mupen64plus_next / parallel_n64 NEON paths | faster N64 RSP | needs `-funsafe-math-optimizations` |
