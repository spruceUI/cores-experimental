# Nightly audit

Which spruceOS nightlies ship emulators built from this repository's recipes, and whether each nightly
ships the bytes the recipe records. There is one entry per nightly, starting with the first nightly after
the v4.5.4 stable release.

## Scope

- The 30 recipes in [`manifests/standalone-builds.json`](manifests/standalone-builds.json) that have a
  `shipped` record (`main` 67aa677). The other 9 recipes have no `shipped` record: spruce doesn't ship
  what they build.
- No core from [`manifests/core-builds.json`](manifests/core-builds.json). That catalog has no `shipped`
  records: none of its builds is recorded as shipping in spruce. A recipe joins this log when it gains a
  `shipped` record.

## Method

1. **Which commit a nightly is.** spruceOS's `create-nightly` workflow makes each release of
   `spruceUI/spruceOSNightlies`. Its run log prints the tag ("Release tag for this run") and the commit
   ("Current Development commit"). The release notes name the commit as well, but upstream deletes old
   releases, and the leftover tags all point at the same commit of that repository (72dfe24, a README
   change), not at spruceOS.
2. **The recorded bytes.** For each file in a recipe's `shipped.files`, the card path comes from
   `output.spruce` (a key ending in `/` maps a whole folder), and the sha256 comes from `shipped.files`.
3. **The shipped bytes.** The file at that path in the nightly's commit, hashed from `git cat-file blob`.
   ScummVM ships its binaries in `Emu/SCUMMVM/*.7z`, so those archives are unpacked and hashed.
4. **Cross-check.** For each nightly that is still published, every recipe path in its OTA package
   (`spruceOTA-v4.5.4-to-*.7z`, which holds the files changed since v4.5.4) is hashed and compared with
   step 3.

| status | meaning |
|---|---|
| match | the nightly ships the bytes the recipe records |
| not shipped | the recipe's card path holds other bytes or nothing: its build is not in this nightly yet |
| replaced | a newer recipe's bytes are at that path, and the newer recipe matches |
| other | bytes that no recipe here records: not built from this repository |
| moved | the recorded bytes ship at a different path: the recipe's `output.spruce` is out of date |

## v4.5.5-20261011 (baseline)

The first nightly built from v4.5.4: Development fa4e98962, workflow run 38110794304.

| recipe | files | main card path | status |
|---|---|---|---|
| flycast-standalone | 4 | `Emu/DC/flycast` | match |
| flycast-standalone-t3-lto | 4 | `Emu/DC/flycast` | not shipped (its 3 libraries are the same files as flycast-standalone's, and match) |
| flycast-libretro-t3 | 1 | `RetroArch/.retroarch/cores64/flycast_libretro.so` | not shipped (other bytes there: b95510d7) |
| vtree-arm64 | 1 | `App/FileManagement/vtree.aarch64` | match |
| pcsx_rearmed-arm64 | 2 | `Emu/PS/pcsx_64` | match |
| moonlight | 33 | `App/Moonlight/ports/moonlightnew/moonlight/moonlight` | match |
| bigpemu | 134 | `Emu/JAGUAR/bigpemu/` | match |
| dsperate-arm64 | 1 | `Emu/NDS/dsperate` | match |
| ppsspp-h700 | 1 | `Emu/PSP/PPSSPPSDL_h700` | match |
| yabasanshiro-arm64 | 4 | `Emu/SATURN/yabasanshiro` | match; libboost_filesystem.so.1.71.0 moved (it ships in `spruce/flip/lib/`) |
| yabasanshiro-arm64-pgo | 4 | `Emu/SATURN/yabasanshiro` | not shipped (libpng16 and libz match; boost moved as above) |
| yabasanshiro-libretro | 1 | `RetroArch/.retroarch/cores64/yabasanshiro_generic_libretro.so` | not shipped (the path is absent) |
| mupen64plus-arm64 | 4 | `Emu/N64/mupen64plus/` video plugins + `overlay_settings.json` | match |
| mupen64plus-arm64-gliden64 | 1 | `Emu/N64/mupen64plus/mupen64plus-video-GLideN64.so` | match |
| mupen64plus-arm64-gliden64-ovl | 1 | `Emu/N64/mupen64plus/mupen64plus-video-GLideN64.so` | not shipped |
| mupen64plus-arm64-20260404 | 5 | `Emu/N64/mupen64plus/mupen64plus` + core and plugins | match |
| dsperate-a30 | 1 | `Emu/NDS/dsperate.a30` | match |
| pcsx_rearmed-a30 | 2 | `Emu/PS/pcsx_a30` | match |
| ppsspp-a30 | 1 | `Emu/PSP/PPSSPPSDL_A30` | match |
| vtree-a30 | 3 | `App/FileManagement/vtree.a30` | match |
| mupen64plus-a30 | 9 | `Emu/N64/mupen64plus-a30/mupen64plus` | match |
| scummvm-a30 | 8 | `Emu/SCUMMVM/scummvm.a30` | match (the binary inside `scummvm_a30.7z`) |
| scummvm-arm64 | 13 | `Emu/SCUMMVM/scummvm.64` | match (the binary inside `scummvm_64.7z`) |
| scummvm-mini | 98 | `Emu/SCUMMVM/scummvm.mini` | match (the binary and 96 plugins inside `scummvm_mini.7z`, `scummvm_mini_plugins.7z`) |
| ppsspp-flip | 1 | `Emu/PSP/PPSSPPSDL_Flip` | match |
| ppsspp-rgb30 | 1 | `Emu/PSP/PPSSPPSDL_RGB30` | match |
| ppsspp-trimui | 1 | `Emu/PSP/PPSSPPSDL_TrimUI` | match |
| ppsspp-smartpros | 1 | `Emu/PSP/PPSSPPSDL_SmartProS` | match |
| pcsx_rearmed-mini | 1 | `Emu/PS/pcsx_mini` | match |
| vtree-mini | 1 | `App/FileManagement/vtree.mini` | match |

## Entries

| nightly | Development | run | change from the previous nightly |
|---|---|---|---|
| v4.5.5-20261011 | fa4e98962 | 38110794304 | baseline (above) |
| v4.5.5-20261011.2 | c75fe27d1 | 38151377140 | none |
| v4.5.5-20261011.3 | d9f2211ee | 38181072840 | none |
| v4.5.5-20261012 | b3eae4869 | 38244780292 | none |
| v4.5.5-20261012.2 | 05bafd5df | 38283108740 | none |
| v4.5.5-20261012.3 | 5dd1259e2 | 38304872469 | none |
| v4.5.5-20261012.4 | 7bcd72177 | 38314520216 | none |
| v4.5.5-20261013 | 783b8a7a5 | 38335310337 | none |
| v4.5.5-20261013.2 | 62ef5c06f | 38393311032 | none |
| v4.5.5-20261013.3 | ca92a8c3c | 38450792827 | none |
| v4.5.5-20261013.4 | 346b4092d | 38466296653 | none |
| v4.5.5-20261014 | c1a030dea | 38495701087 | none |
| v4.5.5-20261015 | 926c106ab | 38657911104 | dsperate-arm64 and dsperate-a30: other (49fa199f, 6a139747), from 926c106ab "DSperate: update to v3.0.4", which no recipe here builds |
| v4.5.5-20261016 | a8ad00192 | 38843091229 | none |
| v4.5.5-20261016.2 | 0bc9dbab7 | 38851163505 | none |
| v4.5.5-20261017 | 9d1633e61 | 38985257210 | none |
| v4.5.5-20261017.2 | 0266514cb | 38988749670 | none |
| v4.5.5-20261017.3 | e12e6f51c | 39000863290 | #1873, #1874 and #1875: five recipes start to match (see below) |
| v4.5.5-20261017.4 | efb3630de | 39005916332 | none |
| v4.5.5-20261017.5 | 4c6f64f55 | 39007416524 | none |
| v4.5.5-20261017.6 | b38340697 | 39047693878 | none |

In v4.5.5-20261017.3:

| recipe | card path | before | now |
|---|---|---|---|
| flycast-standalone-t3-lto | `Emu/DC/flycast` | flycast-standalone (d96cfdd5) | match (3fc30ddf); flycast-standalone is replaced |
| flycast-libretro-t3 | `RetroArch/.retroarch/cores64/flycast_libretro.so` | other (b95510d7) | match (eff7ae72) |
| yabasanshiro-arm64-pgo | `Emu/SATURN/yabasanshiro` | yabasanshiro-arm64 (85f56d08) | match (059cdbbf); yabasanshiro-arm64 is replaced |
| yabasanshiro-libretro | `RetroArch/.retroarch/cores64/yabasanshiro_generic_libretro.so` | absent | match |
| mupen64plus-arm64-gliden64-ovl | `Emu/N64/mupen64plus/mupen64plus-video-GLideN64.so` | mupen64plus-arm64-gliden64 (80589b9c) | match (ffbf531b); mupen64plus-arm64-gliden64 and that file of mupen64plus-arm64 are replaced |

## Cross-check against the published packages

The five nightlies still published on 2026-10-17. In each one, every recipe path inside the OTA package is
byte-identical to the file at the same path in that nightly's Development commit.

| nightly | OTA package | size | sha256 | recipe paths inside | equal to the tree |
|---|---|---|---|---|---|
| v4.5.5-20261017.2 | `spruceOTA-v4.5.4-to-v4.5.5-20261017.7z` | 8258681 | 63965cf1 | 2 (the DSperate pair) | yes |
| v4.5.5-20261017.3 | the same name | 20567053 | a00ca277 | 7 (the DSperate pair and the five above) | yes |
| v4.5.5-20261017.4 | the same name | 20568519 | 62c688a8 | 7 | yes |
| v4.5.5-20261017.5 | the same name | 20568754 | 52c13da2 | 7 | yes |
| v4.5.5-20261017.6 | the same name | 20579411 | 575ef289 | 7 | yes |

## State at v4.5.5-20261017.6

- **Built here and shipping (24 recipes match):**
  - flycast-standalone-t3-lto, flycast-libretro-t3
  - yabasanshiro-arm64-pgo, yabasanshiro-libretro
  - mupen64plus-arm64-gliden64-ovl, mupen64plus-arm64-20260404, mupen64plus-a30
  - pcsx_rearmed-arm64, pcsx_rearmed-a30, pcsx_rearmed-mini
  - every ppsspp, vtree and scummvm recipe
  - moonlight, bigpemu
- **mupen64plus-arm64:** its rice and glide64mk2 plugins and `overlay_settings.json` still match. Its GLideN64
  plugin is replaced.
- **Replaced by newer recipes:** flycast-standalone's binary (its libraries still ship as flycast-standalone-t3-lto's),
  yabasanshiro-arm64's binary (its libpng16 and libz still match), and mupen64plus-arm64-gliden64.
- **Not built from this repository:** DSperate v3.0.4 (`Emu/NDS/dsperate`, `Emu/NDS/dsperate.a30`), since
  v4.5.5-20261015. dsperate-arm64 and dsperate-a30 record the earlier binaries.
- **Out-of-date map:** yabasanshiro-arm64 and yabasanshiro-arm64-pgo map `libs/` to `Emu/SATURN/lib64/`, but
  libboost_filesystem.so.1.71.0 ships in `spruce/flip/lib/`, as their `shipped` note says.
