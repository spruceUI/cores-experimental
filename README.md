# Cores-spruce
[![Build release candidate](https://github.com/spruceUI/cores-experimental/actions/workflows/release-candidate.yml/badge.svg)](https://github.com/spruceUI/cores-experimental/actions/workflows/release-candidate.yml)

A fail-closed, hash-locked build pipeline for the libretro cores SpruceOS
ships. Every one of the 98 workflow cores is built from a pinned source
(url + commit + tree) inside locked toolchain images, proven by a
per-architecture build-log contract, reproduced byte-identically by two
independent builds, and screened against captured device evidence before
it is eligible anywhere. Publication is disabled at every layer;
artifacts are published only through the GitHub Actions release path,
never as checked-in binaries.

The full reference lives in
[docs/pipeline-overview.md](docs/pipeline-overview.md) (repository map,
migration status, golden tiers, build and validation walkthroughs, the
toolchain archive lock, release paths); the other documents in
[docs/](docs/) are focused runbooks.

Ordered `main`, `nightly`, and `edge` policies, track-local stable
promotion, typed chipset tuning, and the zero-tuning `universal` fallback are
documented in [docs/core-track-groups.md](docs/core-track-groups.md). `main`
is the manually selected Spruce stable/Main version level, `nightly` is the
manually selected Spruce Development version level, and `edge` is an exact
upstream branch tip captured and reviewed at admission. Their exact source
commits and trees remain pinned and normally satisfy
`main <= nightly <= edge` by Git ancestry or equality when each direct child
TEST assignment is created. Nightly and Edge record a content-addressed copy of
the parent TEST identity reviewed by that assignment. Later parent movement
does not rewrite or invalidate the child; even a direct child equal to its
parent is an intentional temporal freeze. The immutable Spruce branch artifact
bases are comparison evidence only, and the Spruce v4.3.0 roster is retained
only as historical logical-name correlation; neither is selection authority or
build provenance.

The composable chipset table, all 98 established core recipe parameters, and a
strictly separated set of untested optimization experiments are documented in
[docs/chipset-core-build-parameters.md](docs/chipset-core-build-parameters.md).
The manifest and pipeline validators remain authoritative.

Every effective universal state is build-pinned XOR deferred. The initial v3
registry deliberately defers all 98 cores until a reproducible build pin
satisfies the ordered track policy. An exact recorded outlier authorization is
the only exception to repository/ancestry ordering; it never permits the same
commit to be paired with a different tree. Deferred groups remain visible in
read-only inventories but stop `build-core`, `e2e`, and release planning before
a run directory, plan, or matrix is created. It is local-only and
publication-disabled; an inventory alone is not a device compatibility or
release claim.

Once admitted, a group tag is a pinned-output reproduction gate with an exact
selected URL/ref/commit/tree/submodule identity, exact artifact/metadata
hashes, and registry-owned tuning. Track revisions may differ from the catalog
default when they use the same repository and remain compatible with the
current normalized build/output contract. The full-release path additionally
requires every selected row to retain a complete, hash-pinned package;
projected chipset packages fail during planning.

Legacy golden, pin, and release promotion still rejects grouped records.
A separate two-E2E candidate gate can create a new immutable one-ABI tuned pin
when both independently validated logs produce exact artifact, metadata, and
package bytes; log transcripts themselves may differ. Track TEST admission
atomically CASes the direct cell and new variant; a child assignment also CASes
and captures its current effective parent. The same admission command accepts
an existing untuned `universal-v1` pin only with explicit real-chipset
applicability and complete ABI coverage; neither form changes stable approval.

Host-side tests have one canonical dependency lock at
`requirements-test.txt`; install it before running the suite so Draft 2020-12
inventory schema validation is a required gate:

```bash
python3 -m pip install --requirement requirements-test.txt
```

`Dockerfile.tests` provides the same version-locked validator in an isolated
test-only image. It does not alter or derive any core compiler image.

## Supported devices

| Arch | Devices |
|------|---------|
| arm64 | Trimui Brick, Smart Pro, Smart Pro S, Miyoo Flip |
| armhf | Miyoo Mini/Mini+, Miyoo A30 |

## Device compatibility matrix

With the Mini family's bundled libstdc++ updated to the A30 provider, no
currently pinned core is blocked by a glibc/libstdc++ floor or ceiling on
any probed device — see the measured per-arch requirements and per-device
ceilings in
[docs/pipeline-overview.md](docs/pipeline-overview.md#abi-floors-and-ceilings-glibc--libstdc).

<!-- device-matrix:start -->
Evidence-backed per-device eligibility for every canonical core:
`Y` eligible (all needed libraries observed present, ceiling cleared) - `C` over the captured GLIBCXX ceiling - `X` a needed library is absent on the device - `?` unverified (fails closed) - `-` no build for that ABI. Devices marked `*` have not been probed yet, so every C core there reports `?` rather than an assumed yes. Generated by `scripts/device_matrix.py --write`; regenerate after onboarding or a new device capture.

<details><summary>Matrix: 98 cores x 8 device families</summary>

| core | Brick / TSP | TSPS | Flip | Pixel 2 | A30 | Mini + | H700* | Zero28* |
|---|---|---|---|---|---|---|---|---|
| 2048 | Y | Y | Y | Y | Y | Y | ? | ? |
| 81 | Y | Y | Y | Y | Y | Y | ? | ? |
| a5200 | Y | Y | Y | Y | Y | Y | ? | ? |
| ardens | Y | Y | Y | Y | Y | Y | ? | ? |
| arduous | Y | Y | Y | Y | Y | Y | ? | ? |
| atari800 | Y | Y | Y | Y | Y | Y | ? | ? |
| bk | Y | Y | Y | Y | Y | Y | ? | ? |
| bluemsx | Y | Y | Y | Y | Y | Y | ? | ? |
| cap32 | Y | Y | Y | Y | Y | Y | ? | ? |
| chailove | Y | Y | Y | Y | Y | Y | ? | ? |
| chimerasnes | Y | Y | Y | Y | Y | Y | ? | ? |
| crocods | Y | Y | Y | Y | Y | Y | ? | ? |
| daphne | Y | Y | Y | Y | Y | Y | ? | ? |
| dosbox_pure | Y | Y | Y | Y | Y | Y | ? | ? |
| easyrpg | Y | Y | Y | Y | Y | Y | ? | ? |
| ecwolf | Y | Y | Y | Y | Y | Y | ? | ? |
| fake08 | Y | Y | Y | Y | Y | Y | ? | ? |
| fbalpha2012 | Y | Y | Y | Y | Y | Y | ? | ? |
| fbneo | Y | Y | Y | Y | Y | Y | ? | ? |
| fceumm | Y | Y | Y | Y | Y | Y | ? | ? |
| ffmpeg | excl | excl | excl | excl | excl | excl | excl | excl |
| flycast | Y | Y | Y | Y | ? | ? | ? | ? |
| fmsx | Y | Y | Y | Y | Y | Y | ? | ? |
| freechaf | Y | Y | Y | Y | Y | Y | ? | ? |
| freeintv | Y | Y | Y | Y | Y | Y | ? | ? |
| frodo | Y | Y | Y | Y | Y | Y | ? | ? |
| fuse | Y | Y | Y | Y | Y | Y | ? | ? |
| gambatte | Y | Y | Y | Y | Y | Y | ? | ? |
| gearboy | Y | Y | Y | Y | Y | Y | ? | ? |
| gearcoleco | Y | Y | Y | Y | Y | Y | ? | ? |
| gearsystem | Y | Y | Y | Y | Y | Y | ? | ? |
| genesis_plus_gx | Y | Y | Y | Y | Y | Y | ? | ? |
| genesis_plus_gx_wide | Y | Y | Y | Y | Y | Y | ? | ? |
| gme | Y | Y | Y | Y | Y | Y | ? | ? |
| gpsp | Y | Y | Y | Y | Y | Y | ? | ? |
| gw | Y | Y | Y | Y | Y | Y | ? | ? |
| handy | Y | Y | Y | Y | Y | Y | ? | ? |
| hatari | Y | Y | Y | Y | Y | Y | ? | ? |
| km_duckswanstation_xtreme_amped | - | - | - | - | Y | Y | - | - |
| km_parallel_n64_xtreme_amped_turbo | - | - | - | - | ? | ? | - | - |
| libgametank | Y | Y | Y | Y | Y | Y | ? | ? |
| lowresnx | Y | Y | Y | Y | Y | Y | ? | ? |
| lutro | Y | Y | Y | Y | Y | Y | ? | ? |
| mame2003_plus | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_lynx | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_ngp | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_pce_fast | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_pcfx | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_supafaust | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_supergrafx | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_vb | Y | Y | Y | Y | Y | Y | ? | ? |
| mednafen_wswan | Y | Y | Y | Y | Y | Y | ? | ? |
| mgba | Y | Y | Y | Y | Y | Y | ? | ? |
| mu | Y | Y | Y | Y | Y | Y | ? | ? |
| mupen64plus_next | Y | Y | Y | Y | - | - | ? | ? |
| neocd | Y | Y | Y | Y | Y | Y | ? | ? |
| nestopia | Y | Y | Y | Y | Y | Y | ? | ? |
| np2kai | Y | Y | Y | Y | Y | Y | ? | ? |
| numero | Y | Y | Y | Y | Y | Y | ? | ? |
| o2em | Y | Y | Y | Y | Y | Y | ? | ? |
| opera | Y | Y | Y | Y | Y | Y | ? | ? |
| parallel_n64 | Y | Y | Y | Y | - | - | ? | ? |
| pcsx_rearmed | Y | Y | Y | Y | Y | Y | ? | ? |
| picodrive | Y | Y | Y | Y | Y | Y | ? | ? |
| pokemini | Y | Y | Y | Y | Y | Y | ? | ? |
| potator | Y | Y | Y | Y | Y | Y | ? | ? |
| prboom | Y | Y | Y | Y | Y | Y | ? | ? |
| prosystem | Y | Y | Y | Y | Y | Y | ? | ? |
| puae2021 | Y | Y | Y | Y | Y | Y | ? | ? |
| puzzlescript | Y | Y | Y | Y | Y | Y | ? | ? |
| px68k | Y | Y | Y | Y | Y | Y | ? | ? |
| quasi88 | Y | Y | Y | Y | Y | Y | ? | ? |
| quicknes | Y | Y | Y | Y | Y | Y | ? | ? |
| race | Y | Y | Y | Y | Y | Y | ? | ? |
| reminiscence | Y | Y | Y | Y | Y | Y | ? | ? |
| retro8 | Y | Y | Y | Y | Y | Y | ? | ? |
| sameduck | Y | Y | Y | Y | Y | Y | ? | ? |
| snes9x | Y | Y | Y | Y | Y | Y | ? | ? |
| snes9x2002 | Y | Y | Y | Y | Y | Y | ? | ? |
| snes9x2005 | Y | Y | Y | Y | Y | Y | ? | ? |
| snes9x2005_plus | Y | Y | Y | Y | Y | Y | ? | ? |
| snes9x2010 | Y | Y | Y | Y | Y | Y | ? | ? |
| squirreljme | - | - | - | - | Y | Y | - | - |
| stella2014 | Y | Y | Y | Y | Y | Y | ? | ? |
| swanstation | Y | Y | Y | Y | excl | excl | ? | ? |
| tgbdual | Y | Y | Y | Y | Y | Y | ? | ? |
| theodore | Y | Y | Y | Y | Y | Y | ? | ? |
| tic80 | Y | Y | Y | Y | Y | Y | ? | ? |
| tyrquake | Y | Y | Y | Y | Y | Y | ? | ? |
| uae4arm | - | - | - | - | Y | Y | - | - |
| uw8 | Y | Y | Y | Y | Y | Y | ? | ? |
| uzem | Y | Y | Y | Y | Y | Y | ? | ? |
| vecx | Y | Y | Y | Y | Y | Y | ? | ? |
| vemulator | Y | Y | Y | Y | Y | Y | ? | ? |
| vice_x64 | Y | Y | Y | Y | Y | Y | ? | ? |
| vice_xvic | Y | Y | Y | Y | Y | Y | ? | ? |
| x1 | Y | Y | Y | Y | Y | Y | ? | ? |
| yabasanshiro | Y | Y | Y | Y | - | - | ? | ? |

</details>
<!-- device-matrix:end -->
