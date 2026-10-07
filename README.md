# cores-experimental

Builds the libretro cores spruceOS ships, for each spruce device, from pinned
upstream sources in pinned cross-compiler images. Each core's recipe is data in
[`manifests/core-builds.json`](manifests/core-builds.json)
([fields](docs/catalog.md)); [`scripts/cores.py`](scripts/cores.py) turns a
recipe into a build script and runs it in Docker.

## Boards and profiles

A build is one core × board × profile.

| board | devices | flags |
|---|---|---|
| `universal` | every device (what spruce ships) | none |
| `a133p` | TrimUI Brick, Brick Pro, Smart Pro; MagicX Zero 28 | `-mcpu=cortex-a53` |
| `h700` | Anbernic RG35XX / RG40XX family | `-mcpu=cortex-a53` |
| `a523` | TrimUI Smart Pro S | `-mcpu=cortex-a55` |
| `rk3566` | Miyoo Flip | `-mcpu=cortex-a55` |
| `rk3326` | GKD Pixel 2 | `-mcpu=cortex-a35` |
| `a33` | Miyoo A30 | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` |
| `ssd202d` | Miyoo Mini family | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` |

| profile | flags | for |
|---|---|---|
| `release` | none | what ships: the core's own optimization |
| `max` | `-O3` | maximum optimization (left alone where a core already uses `-Ofast`) |
| `debug` | `-O0 -g` | debugging |
| `debug-og` | `-Og -g` | debugging cores that are too slow at `-O0` |
| `release-g` | `-g` | profiling and symbolized crashes |
| `size` | `-Os` | smallest code |

The flags are appended last to every compile, so they override the core's own
(GCC uses the last `-O`). Boards with the same flags share one build. Why these
flags: [docs/flags.md](docs/flags.md).

Two more options apply to any build: `--runtime static` links the C++ runtime
into the core instead of using the device's ([why](docs/flags.md#c-runtime)),
and `--strip` strips the core before it is load-tested. Such builds are named
with `-static` and `-stripped` and bundled separately.

## Workflows

| workflow | builds | passes when |
|---|---|---|
| [CI](.github/workflows/ci.yml) (push to `main`, weekly) | every core, `universal` + `release` | every core builds and loads; a core whose current commit fails is rebuilt from its known-good recipe, with a warning |
| [Build cores](.github/workflows/build.yml) (manual) | the cores, boards, profiles and extra flags you choose | every build loads |
| [Cross product](.github/workflows/cross-product.yml) (manual) | every core × every board at `max` | every build loads |
| [Freeze a release](.github/workflows/freeze.yml) (manual) | the chosen set, each built twice | every build loads and both builds are byte-identical |
| [Check](.github/workflows/check.yml) (every push and PR) | nothing | the catalog check and unit tests pass |

"Loads" means the core is loaded under qemu with the toolchain's ARM libraries
and runs its startup sequence with a minimal RetroArch-like frontend
([`runtime/smoke_loader.c`](runtime/smoke_loader.c)). Rust cores are built but
not load-tested.

Each run ends with a `bundles` artifact: one folder per board and profile, laid
out like the SD card (`RetroArch/.retroarch/cores64`, `cores`, `info`). Nothing
is published automatically.

To freeze a release, run *Freeze a release* and commit the `<name>.json` from its
`freeze-<name>` artifact under `releases/`. Running it again later with
`check: releases/<name>.json` confirms the release still rebuilds byte for byte.

## Running locally

Needs Docker and Python 3.9 or later (no packages).

```bash
gh release download toolchains --dir /tmp/tc       # the three toolchain images
python3 scripts/cores.py toolchains --dir /tmp/tc   # verify and load them
python3 scripts/cores.py check                      # validate the catalog
python3 scripts/cores.py build --core np2kai --boards a133p --profiles max --out results
python3 scripts/cores.py build --core gearboy --runtime shared,static --strip --out results
python3 scripts/cores.py bundle --results results --out bundles
python3 -m unittest discover -s tests
```

`scripts/cores.py script np2kai arm64` prints the exact build script, `plan`
lists what a selection expands to, and `bump` moves a core to a new commit
([how](docs/catalog.md#moving-a-core-to-a-new-commit)). Each build leaves the
core, its `.info`, the script, `build.log` and `record.json` in
`results/<core>/<variant>/`.

## Known issues

- mame2003_plus does not load when built at `-O0`; use `debug-og`.
- 26 armhf C++ cores need GCC 13's libstdc++, which the 32-bit RetroArch on
  the Anbernic XX family and the Flip lack; build them with `--runtime static`
  or ship that libstdc++ ([details](docs/flags.md#c-runtime)).
- The Miyoo Mini Plus has no GLES2, so GL cores (flycast, N64) cannot run there
  whatever the flags.
- On a Miyoo Mini Plus (2026-10-07), pcsx_rearmed (r26l) hangs in `retro_init`
  after starting its compiler thread, where spruce's r25l loads; puae2021 needs
  61 MB of zero-filled memory and the Mini had 55 MB free (spruce's needs 55).
- Nothing has been benchmarked on a device yet: `max` and the board builds are
  proven to load, not to be faster.
- Shipped by spruceOS but not built here: mkxp-z (the hyphen in its name breaks
  libretro-super), mupen64plus (removed from libretro-super), km_flycast_xtreme
  (assembles with a bare `as`) and km_ludicrousn64_2k22_xtreme_amped (broken
  aarch64 dynarec).

## Layout

| path | contents |
|---|---|
| `manifests/core-builds.json` | one recipe per core |
| `manifests/boards.json`, `manifests/optimization-profiles.json` | board and profile flags |
| `manifests/toolchains.json` | the toolchain images: archive digests and image IDs |
| `patches/` | source patches used by the recipes ([list](patches/README.md)) |
| `metadata/` | `.info` files libretro-super does not provide |
| `scripts/` | `cores.py` and the `corebuild` package |
| `runtime/smoke_loader.c` | the load test |
| `Dockerfile.*`, `toolchain-inputs/` | how the toolchain images were made ([notes](toolchain-inputs/README.md)) |

[docs/history.md](docs/history.md) explains what this repository replaced in
October 2026.
