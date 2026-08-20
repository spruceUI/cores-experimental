# Flycast candidate compatibility — projected

> **This is a projection, not evidence.** Nothing here has been built or run.
> No candidate has been compiled and no device has executed any of these cores;
> the fleet was offline when this was produced. Every verdict below is derived
> from source inspection, config gating and ELF analysis of the already-built
> v2.6 artifacts. Treat it as a plan for what to test, not as a result.

Generated 2026-08-20.

## Candidates

| core_id | tag | released | commit | cmake floor | targets | libchdr lzma | onboarded |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `flycast2021` | v1.2 | 2021-12-17 | `7555263e3872` | 3.10.2 | arm64 | lzma-19.00 | **no — candidate only** |
| `flycast2024` | v2.4 | 2024-10-21 | `8108e63907fc` | 3.10.2 | arm64 | lzma-24.05 | **no — candidate only** |
| `flycast` | v2.6 | 2026-01-10 | `392a429e8b04` | 3.24 | arm64, armhf | lzma-24.05 | yes |

Why these two tags: **v1.2** is the last 2021 release and the one that introduced the
libretro core; **v2.4** is the last 2024 release. If a different reading of "2021" and
"2024" is wanted, the alternatives are v1.0/v1.1 and v2.3/v2.3.2.

## Device matrix

| device | arch | chipset | DC offered | wired bucket | flycast2021 | flycast2024 | flycast (v2.6) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ANBERNIC_RG28XX` | aarch64 | h700 | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `ANBERNIC_RG34XXSP` | aarch64 | h700 | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `ANBERNIC_RGCUBEXX` | aarch64 | h700 | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `ANBERNIC_RGXX640480` | aarch64 | h700 | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `GKD_PIXEL2` | aarch64 | rk3326 | yes | Emulator_Pixel2 | projected ✓ | projected ✓ | projected ✓ |
| `MAGICX_ZERO28` | aarch64 | unverified | no | — | n/a | n/a | n/a |
| `MIYOO_A30` | armhf | a33-class (allwinner sun8i, R16) | yes | Emulator_A30 | not targeted | not targeted | projected ✓ |
| `MIYOO_FLIP` | aarch64 | rk3566 | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `MIYOO_MINI` | armhf | ssd202d | no | — | n/a | n/a | n/a |
| `MIYOO_MINI_PLUS` | armhf | ssd202d | no | — | n/a | n/a | n/a |
| `MIYOO_MINI_V4` | armhf | ssd202d | no | — | n/a | n/a | n/a |
| `MIYOO_MINI_FLIP` | armhf | ssd202d | no | — | n/a | n/a | n/a |
| `TRIMUI_BRICK` | aarch64 | a133p | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `TRIMUI_BRICK_PRO` | aarch64 | a133p | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `TRIMUI_SMART_PRO` | aarch64 | a133p | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |
| `TRIMUI_SMART_PRO_S` | aarch64 | a523 | yes | Emulator_64 | projected ✓ | projected ✓ | projected ✓ |

### Chipset attribution confidence

Not every chipset is equally established. Attributions marked INFERRED were not
confirmed by probe or by anything in the repo:

- `GKD_PIXEL2` → rk3326 — INFERRED - not verified in repo or by probe
- `MAGICX_ZERO28` → unverified — not established
- `MIYOO_MINI_FLIP` → ssd202d — INFERRED - Mini family, no dedicated platform cfg
- `TRIMUI_BRICK_PRO` → a133p — INFERRED - shares Brick lineage, not probed

## What the verdicts mean

- **projected ✓** — the tag exposes the `flycast_libretro` target and `USE_GLES`, its
  cmake floor clears the toolchain's 3.31.6, and the recipe matches the v2.6 core that
  is already proven to build and run. Nothing was actually compiled.
- **not targeted** — the candidate pins arm64 only. No armhf device is offered these
  options, and for v1.2 the armhf overlay provably cannot apply.
- **n/a** — Dreamcast is not offered on that device at all.

## The armhf question

Both candidates are arm64-only, and that is a deliberate call rather than an oversight.

The armhf overlay patches `core/deps/libchdr/deps/lzma-24.05/src/CpuArch.c`. At **v1.2**
the libchdr submodule (`d3ffd20ca716`) ships **lzma-19.00**, so that path does not exist
and the overlay cannot apply. At **v2.4** libchdr (`9b6ff6c3c243`) does carry lzma-24.05,
but its `CpuArch.c` preimage hash has not been checked against the overlay's recorded
`preimage_sha256`, so applicability is unverified.

Neither matters today: the only armhf device offered Dreamcast is the A30, and it is
wired to `Emulator_A30` (`flycast`, `km_flycast_xtreme`) using the 32-bit RetroArch cores.
Extending either candidate to armhf would mean resolving the overlay first.

## Onboarding status

Runbook steps 1–3 are done — source pin, catalog entry, dispatcher workflow — plus the
roster mirror and count constants the fail-closed guards require.

**Onboarding is not complete, by design.** The core-track registry still rejects both
cores (*"Edge reviewed heads differ from the core catalog"*) because a track entry binds
a `build_pin_id`, which exists only after a real build. This pipeline's local host
profile admits `libretro-super` only and flycast is `direct-cmake`, so steps 4–13 cannot
run here. Per standing policy the driver allowlist is not being widened to get around it.

No evidence was fabricated: `pins/`, `manifests/compatibility/` and the track registry
hold nothing for these cores. That absence is what marks them as candidates.

