# Exclusions and open items

Post-migration record of what stays excluded, what is still an open
decision, and the minimal history behind each. The full analysis —
symbol-level evidence, per-device scratch builds, the TG5050 SDK
teardown, and the per-core triage table — is preserved in this file's
git history.

## Open decisions

- **parallel_n64 / mupen64plus_next armhf for the A30.** Scratch builds
  at the pinned commits pass (`WITH_DYNAREC=arm FORCE_GLES=1`) and the
  A30 clears both ceilings, but the catalog ships them arm64-only,
  matching spruceOS; A30 N64 is served by the overlay-repaired
  km_parallel_n64 fork. Onboarding armhf profile variants is a scope
  decision, not a blocker.
- **ffmpeg default-excluded.** Built, reproducible, portable profile;
  turning selection on is a human review gate.
- **Uncataloged tail (4).** mkxp-z, mupen64plus, km_flycast_xtreme, and
  km_ludicrousn64_2k22_xtreme_amped ship without a build recipe in this
  repository; per-core reasons live in the uncataloged tail in
  [`pipeline-overview.md`](pipeline-overview.md).

## Structural exclusions (device firmware, out of pipeline scope)

- **Miyoo Mini Plus has no GLES2 stack at all** (fleet-captured; its
  shipped flycast fails to load with exactly the missing soname). Any
  GL-linking armhf core — flycast, an armhf N64 build — can never run
  there regardless of build choices.

## Resolved, kept for reference

- **The Mini over-ceiling class is empty.** The family's bundled SD
  libstdc++ provider was replaced with the A30 build (GLIBCXX 3.4.32),
  the Mini was re-probed on-device, and `MINI_OVER_CEILING` emptied.
  Symbol evidence had ruled out pinning older core versions: the
  breaching symbols (`__throw_bad_array_new_length`,
  `ios_base_library_init`, …) are GCC-13-emitted for any source version,
  so only a provider or `-static-libstdc++` remedy could work. The
  spruceOS-side change is committed locally (`ee825739d`); pushing it
  remains the user's call.
- **TSPS is Mali, not PowerVR.** The TG5050 SDK teardown (aarch64-only
  buildroot, sysroot GLIBCXX 3.4.28 — exactly the captured device
  ceiling — and a Mali blob with wrapper libEGL/libGLESv2) retired the
  "PowerVR userspace may be mislocated" re-probe hypothesis: the failing
  yabasanshiro/ffmpeg cells were the wrong variant for the device, and
  the provider screen was correct. If a TSPS-native Mali build is ever
  needed, that SDK is the right sysroot (a third toolchain-image entry —
  same decision class as `cores-rust`). Since superseded in practice by
  the single generic yabasanshiro build.
- **Everything else in the old triage table landed canonically** —
  easyrpg, yabasanshiro, squirreljme, libgametank, km_parallel_n64,
  flycast; see [`fail-open-workflow-migration.md`](fail-open-workflow-migration.md).
