# cores-experimental

Builds the libretro cores spruceOS ships, for every spruce device, from pinned
upstream sources inside pinned cross-toolchain images. One small driver,
[`scripts/cores.py`](scripts/cores.py), turns the catalog into container build
scripts; every core's recipe is data in
[`manifests/core-builds.json`](manifests/core-builds.json)
([field reference](docs/catalog.md)).

## What gets built

A build is one **core × arch × board × profile**.

| board | arch | flags appended | devices |
|---|---|---|---|
| `universal` | every ABI the core targets | none (the catalog build) | all |
| `a133p` | arm64 | `-mcpu=cortex-a53` | TrimUI Brick / Brick Pro / Smart Pro, MagicX Zero 28 |
| `h700` | arm64 | `-mcpu=cortex-a53` | Anbernic RG35XX / RG40XX family |
| `a523` | arm64 | `-mcpu=cortex-a55` | TrimUI Smart Pro S |
| `rk3566` | arm64 | `-mcpu=cortex-a55` | Miyoo Flip |
| `rk3326` | arm64 | `-mcpu=cortex-a35` | GKD Pixel 2 |
| `a33` | armhf | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` | Miyoo A30 |
| `ssd202d` | armhf | `-mcpu=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard` | Miyoo Mini family |

| profile | flags appended | use |
|---|---|---|
| `release` | none | the core's own optimization (what ships) |
| `max` | `-O3` (not on compiles already at `-Ofast`) | highest standard level, IEEE-safe; never lowers a core's own level |
| `debug` | `-O0 -g` | full debug info, unoptimized |
| `debug-og` | `-Og -g` | debuggable and fast enough to run heavy cores |
| `release-g` | `-g` | shipping optimization plus symbols, for profiling |
| `size` | `-Os` | smallest code |

Boards and profiles live in [`manifests/boards.json`](manifests/boards.json) and
[`manifests/optimization-profiles.json`](manifests/optimization-profiles.json).
Boards with identical flags share one build (a523 and rk3566; a33 and ssd202d;
a133p and h700).

**How the flags reach the compiler.** A core's makefile sets its own `-O2`
after any `CFLAGS` from the environment, and GCC uses the last `-O` it sees, so
flags cannot be injected through `CFLAGS`. For any non-release build the
container puts small wrappers in front of the cross compilers that append the
board and profile flags as the last arguments of every compile and link, and
log each call to `variant-calls.log`. The `universal` + `release` build runs
without wrappers, exactly as the catalog describes. Rust cores (`direct-cargo`)
take profiles through cargo's profile settings and ignore board flags.

## Workflows

| workflow | trigger | builds | passes when |
|---|---|---|---|
| [CI](.github/workflows/ci.yml) | push to `main`, weekly, manual | every core, `universal` + `release` | every core is usable at its catalog commit, or at its `known_good` recipe (flagged as a warning) |
| [Build cores](.github/workflows/build.yml) | manual | chosen cores × boards × profiles, plus optional extra GCC flags | each build is a usable core |
| [Cross product](.github/workflows/cross-product.yml) | manual | every core × every board at `max` | each build is a usable core |
| [Freeze a release](.github/workflows/freeze.yml) | manual | chosen cores × boards × profiles, each built twice | usable, and both builds are byte-identical |
| [Check](.github/workflows/check.yml) | every push and PR | nothing | the catalog checks and unit tests pass |

**Usable** means the build produced the core and the core loads: inside the
toolchain image, [`runtime/smoke_loader.c`](runtime/smoke_loader.c) runs under
qemu against the target sysroot, dlopens the core with eager binding (with
`libm` and `libpthread` loaded, as in RetroArch) and calls `retro_api_version`,
`retro_get_system_info`, `retro_set_environment` and `retro_init`. It answers the
environment like a minimal RetroArch: system, save and content directories, the
pixel format, a log interface and every core option's default value.
`retro_deinit` is called and recorded but not required. Cargo cores are built but
not load-tested (the Rust image has no qemu).

Every run ends with a `bundles` artifact: one directory per board+profile laid
out like the SD card (`RetroArch/.retroarch/cores64`, `cores`, `info`) with a
`manifest.json`, plus a status table in the run summary. Nothing is published;
publication stays a manual step.

**Freezing a release.** Run *Freeze a release* with a name; it fails unless
every build is usable and reproducible (the second build runs on half the
CPUs). Commit the `<name>.json` from its bundles under `releases/`. Running it
again later with `check: releases/<name>.json` proves the release still
rebuilds bit for bit.

**Known-good fallback.** `scripts/cores.py bump CORE --commit SHA` moves a core
to a new commit and keeps the current recipe as `known_good`. CI builds the new
commit; if it fails or does not load, CI builds the known-good recipe instead and
says so. Experiments and freezes never fall back.

## Running locally

Needs Docker and Python 3.9+ (standard library only).

```bash
gh release download toolchains --dir /tmp/tc          # the three image archives
python3 scripts/cores.py toolchains --dir /tmp/tc       # verify digests, docker load
python3 scripts/cores.py check                          # catalog consistency
python3 scripts/cores.py script np2kai arm64 --boards a133p --profiles max   # what would run
python3 scripts/cores.py plan --cores np2kai --boards all --profiles max,debug
python3 scripts/cores.py build --core np2kai --boards a133p,a33 --profiles max --out results
python3 scripts/cores.py bundle --results results --out bundles
python3 -m unittest discover -s tests
```

`build` writes `results/<core>/<variant>/` with the core, its `.info`, the exact
`script.sh` that ran, `build.log`, `smoke.txt`, the source provenance and a
`record.json`.

## Layout

| path | what |
|---|---|
| `manifests/core-builds.json` | the catalog: one recipe per core |
| `manifests/boards.json`, `optimization-profiles.json` | variant flags |
| `manifests/toolchains.json` | image archive digests and image IDs (release `toolchains`) |
| `patches/` | source patches applied by the recipes ([index](patches/README.md)) |
| `metadata/` | `.info` files for cores libretro-super has none for |
| `scripts/cores.py`, `scripts/corebuild/` | the driver |
| `runtime/smoke_loader.c` | the load test |
| `Dockerfile.*`, `toolchain-inputs/` | how the toolchain images were made ([notes](toolchain-inputs/README.md)) |
| `docs/` | [catalog reference](docs/catalog.md), [compiler flags](docs/flags.md), [excluded cores](docs/excluded-cores-analysis.md), [audit and reduction record](docs/audit-2026-10.md) |
