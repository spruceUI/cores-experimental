# Cores-spruce session handoff

Updated 2026-07-24 in `/home/arkun/ai/CFW/Spruce/git/Cores-spruce` on `main`.

## Continuity

- Dev-workflow audit chain label: `cores-local-promotion-long-horizon-20260716`
- Current leaf audit: `acl-20260716-174134-8ef65a` (active)
- Checkpoint: `c6b480f` (libgametank/cargo — migration complete) on `main`
- Milestone: legacy workflow migration — **COMPLETE, canonical 98 / unmigrated 0**
- Last completed row: image batch v4 (full easyrpg static dependency
  closure, both ABIs) + easyrpg onboarding. easyrpg is eligible on every
  probed device; the shipped arm64 build loaded on none.
- libgametank landed 2026-07-24 (deferral reversed by user approval): the
  `direct-cargo` driver, the Cargo.lock-shaped proof engine, and the
  standalone Rust image as the lock's THIRD entry. Zero fail-open
  workflows remain.

## State

- The toolchain lock holds THREE images: arm64 538411e2759c / armhf
  393a23661c41 (v4) / rust aa42a12ced6b (standalone Rust 1.90 + zig 0.13;
  rust.tar.gz image input is sha-pinned but NOT repo-tracked — 365 MB
  exceeds GitHub's file limit; fetch URL in Dockerfile.rust). Promoted pin-sets for the
  96 pre-v4 cores still record their v2 image ids — the re-promote wave
  is DEFERRED hygiene (v2-cutover precedent: suite stays green; compilers
  and sysroots are inherited layers, artifacts byte-identical).
- Migration scoreboard literal in `tests/expected_counts.py`
  (catalog 98, unmigrated 0, masked 0, info-only 0, contracts 89).
- Full suite at checkpoint: 1326 passed, 2 env-gated skips. The full
  workflow roster constructs a release-ready plan for the first time.
- Image-input tarballs (cmake/inih/libpng/pixman/expat/fmt/ogg/vorbis/
  mpg123/sndfile/icu/icudata + icu-fix-data.patch) are repo-tracked and
  sha-pinned in the Dockerfiles; the dep block must stay ONE COPY + ONE
  RUN per image (toolchain lock 16 MiB small-member capture cap).

## Standing human gates (unchanged)

- GH toolchains release upload (CI parity) — outward-facing, explicit
  approval required; upload all THREE lock archives
  (cores-arm64/armhf/rust.tar.gz).
- spruceOS Development `ee825739d` (bundled libstdc++ 6.0.32) push.
- Device probe rerun when the fleet is up (`scripts/device_probe.sh` now
  captures unversioned GLES/EGL/mali/gomp — turns the flycast/km Mini
  `?` cells into verdicts).
- Nothing is pushed, dispatched, deployed, or published; publication stays
  disabled everywhere.
