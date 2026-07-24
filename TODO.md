# Cores-spruce TODO

Updated 2026-07-24. Work remains local-only and publication-disabled. Do not
push, dispatch Actions, publish a release, mutate a device, or change external
state without a new explicit approval.

## Legacy workflow migration — COMPLETE, 98/98

- [x] Flycast v2.6 — DONE 2026-07-23 (`e8a747d`): canonical, both ABIs
  byte-identical, per-arch GLES defines, submodule-owned lzma overlay.
- [x] yabasanshiro — DONE 2026-07-23: ONE generic arm64_cortex_a53_gles3
  build (versioned libGLESv2.so.2) supersedes all three vendor variants.
- [x] easyrpg — DONE 2026-07-24 (`a73706c`): image batch v4 built the full
  static dependency closure (pixman/expat/fmt/ogg/vorbis/mpg123/sndfile/
  ICU-78.3-trimmed) into both images; liblcf pinned via configure-time
  clone overlay; DT_NEEDED is exactly the loader base + capture-proven
  libpng16/libz — eligible on every probed device (shipped arm64 loaded
  on none).
- [x] km_parallel_n64_xtreme_amped_turbo — DONE 2026-07-23 (`b9d2398`): no
  bisect needed; five reviewed overlays (incl. -fcommon) restore the fork.
- [x] libgametank — DONE 2026-07-24 (deferral reversed by approval): first
  `direct-cargo` core; standalone Rust 1.90/zig 0.13 image is the lock's
  third entry; upstream Cargo.lock is the checksummed dependency pin;
  proof = lock digest + zigbuild invocation + 69-crate multiset. THE
  MIGRATION QUEUE IS CLOSED: 98/98.

## Resolved policy decisions

- ffmpeg selection (approved 2026-07-24): the portable pure-C build is the
  selected canonical artifact — the shipped PowerVR-linked build fails to
  load on Flip and TSPS, while ours needs only libc/libm/libpthread and
  reproduces byte for byte. The dormant `trimui-a133p-pvr` accelerated
  flavor stays a variant-set candidate (see
  docs/device-abi-variant-sets-design.md), not a selection; revisit only
  with device benchmarks demanding it.
- Image batch v4 (approved as the libpng batch, widened by evidence,
  audit-logged): easyrpg's full static dep prefix in both images; the
  Rust/cargo layer stays deferred; dep layers must stay ONE COPY + ONE
  RUN (toolchain-lock 16 MiB small-member capture cap).

## Deferred hygiene

- [ ] Re-promote wave: refresh the 96 pre-v4 pin-sets onto the v4 image
  ids (artifacts byte-identical by layer inheritance; v2-cutover precedent
  keeps the suite green meanwhile). Batch with the next evidence-refresh
  wave rather than running it alone.
- [ ] Superseded toolchain archives (v2/v3) still staged in
  `.local-e2e/store/toolchain-archives` — prune only with an explicit
  cleanup decision (deletion gate).

## Awaiting user

- [ ] GH toolchains release upload (cores-arm64/armhf/rust.tar.gz — all
  three lock entries) — outward-facing, explicit approval required.
- [ ] spruceOS Development `ee825739d` (Mini bundled libstdc++ 6.0.32) push.
- [ ] Device probe rerun when the fleet is up (script now captures
  unversioned GLES/EGL/mali/gomp; resolves the flycast/km Mini `?` cells).

## Pipeline follow-up

- [ ] Continue splitting catalog validation, build execution,
  evidence/snapshots, promotion, and command handlers out of
  `scripts/core_pipeline.py` without reintroducing multi-core contract files.
- [ ] Make exact detached-checkout validation easier when tests require the
  ignored `.local-e2e` evidence store; do not weaken path containment to do so.
