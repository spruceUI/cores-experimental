# Excluded-cores analysis (read-only), part 1: the Mini over-ceiling class

> **Resolved (2026-07-24):** the Mini over-ceiling class this analysis
> examines is empty — the family's bundled libstdc++ provider is now the
> A30 build (GLIBCXX 3.4.32, spruceOS `ee825739d`), and no pinned core is
> over any probed device's ceiling (see the ABI floors and ceilings
> section of [`pipeline-overview.md`](pipeline-overview.md)). The
> analysis below is the evidence record that ruled out version-pinning
> alternatives and motivated the provider swap.

Question (a): would an earlier core version compile under the older GLIBCXX
ceiling? **Answer for all 22 cores: NO — the requirement is toolchain-emitted,
not source-driven.** Symbol-level evidence from the promoted armhf artifacts:

- `__throw_bad_array_new_length@3.4.29` — 15 of 22 cores. Emitted by GCC >= 11
  for every `new T[n]`; no source version avoids it.
- `ios_base_library_init@3.4.32` — 13 of 22. Emitted by GCC 13 for any TU that
  includes <iostream>.
- Long tail (condition_variable::wait@3.4.30, _Sp_make_shared_tag@3.4.26,
  string::reserve@3.4.29) — also GCC-13 libstdc++ artifacts.

The shipped builds load on the Mini because they were compiled with an older
GCC, not because they are older core versions. Rebuilding ANY version with the
A30 buildroot (GCC 13.2) reproduces the ceiling breach.

Remedies, ranked:
1. **Provider bundle (Lever B, already in the design doc):** ship a newer
   libstdc++.so.6 on the Mini SD ahead of the system path. Fixes all 22 at
   once, zero rebuilds, zero artifact changes. The A30 already runs this
   pattern (its spruce/a30/lib libstdc++ IS a bundled provider).
2. `-static-libstdc++` build flavor for armhf C++ cores: removes libstdc++
   from DT_NEEDED entirely (~+1MB/core, artifact change, per-core re-promote).
3. Older core versions: ruled out by the evidence above.

Part 2 (question b, pending deeper passes):
- uae4arm arm64: excluded because the pinned source hardcodes armv7 inline asm
  (`rev16 r2,x0` fails under aarch64) — an arch-option gap in the SOURCE, not
  the build; newer upstream aarch64 support would be the inverse of (a).
- TSPS yabasanshiro/ffmpeg X cells: loader-truth says libIMGegl/libsrv_um
  unresolvable, but TSPS is the PowerVR device — the vendor userspace may live
  outside the probed search paths. Worth one targeted re-probe (find / -name
  'libIMGegl*') before concluding the deps are absent rather than mislocated.
- mupen64plus_next / parallel_n64 armhf: not exclusions but unexercised arch
  options (WITH_DYNAREC=arm FORCE_GLES=1 builds exist upstream); we ship
  arm64-only matching SpruceOS, so this is scope, not a miss.

## Part 2a: armhf mupen64plus_next / parallel_n64 — viable for exactly one device

Scratch-built both at their pinned commits in the cores-armhf image (A30
buildroot, GCC 13.2, glibc-2.23 sysroot), `WITH_DYNAREC=arm FORCE_GLES=1`:

| core | build | GLIBC floor | GLIBCXX max | DT_NEEDED (GL) |
|---|---|---|---|---|
| parallel_n64 | OK (3.6 MB) | 2.15 | 3.4.30 | libGLESv2.so |
| mupen64plus_next | OK (4.3 MB) | 2.17 | 3.4.32 | libEGL.so, libGLESv2.so |

Per device:
- **A30: VIABLE** — GLES2+EGL captured present, provider GLIBCXX 3.4.32 clears
  both (mupen64plus_next sits exactly at the ceiling), glibc floors clear 2.23.
  Two caveats: the builds link the *unversioned* sonames (one loader-truth
  check on-device should confirm `libGLESv2.so` resolves, or relink versioned),
  and N64 runtime performance on the A30's Cortex-A7-class CPU is a
  target-runtime gate like every other runtime claim. Note: an upstream
  parallel_n64 armhf would be a healthy-source alternative to the
  broken-at-HEAD km_parallel_n64 fork that currently serves A30 N64.
- **Mini Plus: NOT VIABLE, doubly** — no GLES2 provider at all (captured), and
  both cores exceed its 3.4.24 GLIBCXX ceiling. Notated as structural.
- All other devices are arm64 and served by the existing arm64 builds.

## Part 2b: the TG5050 SDK (TSPS) — report only

`sdk_tg5050_linux_v1.0.0.tgz` (1.1 GB) is TSPS's native SDK:
- aarch64-only buildroot (`aarch64-buildroot-linux-gnu`, ext-toolchain
  `aarch64-none-linux-gnu`); no armhf toolchain inside.
- sysroot libstdc++ 6.0.28 → GLIBCXX 3.4.28 — exactly the TSPS device ceiling
  the fleet captured. Self-consistent.
- GL stack is a **Mali blob** (`libmali.so.0.32.0`) with wrapper
  libEGL/libGLESv2 that `DT_NEEDED` libmali.so.0 — precisely the soname
  `yabasanshiro_smartpros` needs.

Consequences:
1. **It corrects part 1's TSPS hypothesis: TSPS is Mali, not PowerVR.** The
   PowerVR sonames (libIMGegl, libsrv_um, libglslcompiler, libusc) belong to
   the a133p/base yabasanshiro and shipped-ffmpeg variants targeting the
   A133P's PowerVR GE8300 (Brick/TSP). Those X cells on TSPS are the *wrong
   variant for the device* — expected failures, provider screen correct, no
   re-probe needed. Hypothesis retired.
2. **It is the right sysroot to build `yabasanshiro_smartpros`** (and any
   TSPS-native Mali-GL core): correct glibc/libstdc++ ceilings by
   construction, vendor GL present for linking. A cores-tg5050 image derived
   from this SDK would be a third toolchain entry — same lock-extension
   decision class as cores-rust.
3. Not useful for the armhf questions (no armhf toolchain).

## Part 3: per-core triage — fixable or not

| combination | verdict | path / reason |
|---|---|---|
| 22 × Mini+ over-ceiling | FIXABLE (shared remedy, decision needed) | Lever B bundled libstdc++ on Mini SD (all 22, no rebuilds) or -static-libstdc++ flavor (per-core, +1MB). Older source versions ruled out by symbol evidence. |
| flycast(armhf) × Mini+ | NOT POSSIBLE | Device has no GLES2 stack at all; flycast has no software renderer. Firmware-level, out of pipeline scope. |
| parallel_n64/mupen64plus_next armhf × A30 | FIXABLE (proven) | Scratch builds pass; ceilings clear. Onboard armhf profile variants + confirm unversioned GL soname resolves on device. |
| parallel_n64/mupen64plus_next armhf × Mini+ | NOT POSSIBLE | Doubly excluded: no GLES2 + over ceiling. |
| uae4arm × arm64 devices | REDUNDANT (fix unnecessary) | Source hardcodes armv7 asm; but puae2021 (dual-ABI) already covers arm64 Amiga. Newer-upstream aarch64 JIT possible if ever wanted. |
| km_duckswanstation × arm64 devices | REDUNDANT | Canonical swanstation (arm64) covers those devices; the pair is complementary by design. |
| swanstation × armhf devices (policy) | REDUNDANT | km_duckswanstation (armhf) is the armhf PSX core. |
| ffmpeg × all (policy default-excluded) | FIXABLE (pure decision) | Built, reproducible, portable profile; selection is a human review gate. |
| easyrpg arm64 (broken shipped) | FIXABLE (unblocked) | v2 image has CMake+deps; build libretro target w/ PLAYER_BUILD_LIBLCF; replaces a build broken on every arm64 device. |
| easyrpg armhf × A30 | FIXABLE (work) | Deps must be cross-built into the buildroot sysroot. × Mini+ additionally hits the ceiling → needs the shared remedy too. |
| yabasanshiro (all 3 variants) | FIXABLE (likely simpler than planned) | Key insight: variants exist because shipped builds link VENDOR GL directly. A single generic-GLES2 build (mesa stubs, like our N64 cores) should resolve against each device's wrapper libGLESv2 — potentially one artifact instead of three. Fallback: TG5050 SDK sysroot for smartpros, A133P vendor sysroot for a133p. Exploratory build decides. |
| km_parallel_n64 (broken at HEAD) | FIXABLE (two paths) | Bisect to last building commit, or glsm overlay; OR retire in favor of upstream parallel_n64 armhf (healthy source, proven build) for A30. |
| squirreljme | LIKELY FIXABLE (untested) | v2 armhf image now has qemu-arm + QEMU_LD_PREFIX at the A30 sysroot — the configure-executes-host-tool blocker should clear; binfmt availability in-container is the remaining risk. One exploratory build decides. |
| libgametank | FIXABLE (machinery pending) | cores-rust image exists; needs the cargo driver + Cargo.lock proof engine. |
| 96 armhf cores staged on Brick/TSP | FIXABLE (out of remit) | SpruceOS packaging: stop staging armhf cores on devices with no armhf loader. Reported. |
| mkxp-z, plain mupen64plus | UNKNOWN (uninvestigated) | Newly inventoried by the assessment; need first-pass triage. |

## Part 4: Mini-series fix APPLIED (Lever B, staged in spruceOS working tree)

The Mini family's libstdc++ was already a bundled SD provider
(`miyoo/lib/libstdc++.so.6`, sha 2b281292..., GLIBCXX 3.4.24 -- exactly what
the fleet captured on the Mini Plus). Replaced in the spruceOS working tree
with the A30 buildroot's libstdc++.so.6.0.32:

- new sha `8014989515dc...` -- **byte-identical to the A30's own bundled
  provider**, already proven in production on that device
- GLIBCXX 3.4.32: satisfies the worst armhf requirement in the catalog
  (3.4.32, verified across all 92) -- clears all 22 Mini exclusions
- GLIBC floor 2.18 <= Mini Plus's captured 2.28; armhf EABI5
- libstdc++ is backward-compatible: every existing binary needing <= 3.4.24
  keeps working
- `Emu/PSP/libstdc++.so.6` (emulator-local copy) deliberately left alone: it
  serves that emulator's own binary, not the cores' loader path

NOT yet claimed in the eligibility model, deliberately: the device contract
records observed truth, and the device still runs the old file until the SD
syncs. The flip is: sync SD -> re-run device_probe on the Mini -> transcribe
(ceiling 3.4.24 -> 3.4.32) -> MINI_OVER_CEILING empties -> matrix turns 22
C cells to Y. spruceOS commit is the user's call (working-tree change only).
