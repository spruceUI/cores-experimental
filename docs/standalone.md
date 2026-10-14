# Standalone emulators

Some emulators spruce ships are executables rather than libretro cores. Each
variant is a recipe in [`manifests/standalone-builds.json`](../manifests/standalone-builds.json):
pinned sources, a pinned toolchain image, the build commands, what it ships, and the
hashes of the files spruce ships today.

```bash
python3 scripts/cores.py standalone list
python3 scripts/cores.py standalone script flycast-standalone   # the build script
python3 scripts/cores.py standalone build flycast-standalone --out results
```

A build leaves the shipped files in `results/<name>/dist/`, laid out as the
recipe's `output.spruce` map puts them on the card. Next to `dist/` are the build
script, `build.log`, `elf.tsv` (every shipped ELF's SONAME and NEEDED entries) and
`record.json`.

## Recipe fields

| field | meaning |
|---|---|
| `extends` | start from another recipe's fields; any top-level key given here replaces the parent's whole |
| `abstract` | a base for `extends` only, never built |
| `description` | which emulator, version and devices |
| `source` | repository `url`, full `commit`, its `tree` (checked after checkout), `requested_ref`, `submodules: true` to fetch them, and `path` to check it out somewhere other than `/src` (some builds embed their paths) |
| `extra_sources` | more repositories, the same fields plus an absolute `path` to check out into |
| `downloads` | files fetched at build time: `url`, `sha256` (checked before use) and an absolute `path` |
| `patches` | `{"diff": "patches/standalone/..."}`, applied with `git apply` (which fails if the diff no longer applies); `{"script": ...}`, run with Python; or `{"mail": ..., "committer": "Name <email>", "commit": ...}`, `git format-patch` mails applied with `git am` as that committer at the mails' dates, which recreates their commits: `HEAD` must then be `commit`. `dir` picks the tree (default `/src`) |
| `toolchain` | the image in `manifests/toolchains.json` |
| `source_date_epoch` | fixed build date, so the output does not depend on when it was built |
| `env` | variables exported before the build |
| `cmake` | `target`, `cross_defines` and `defines` for an arm64 CMake build of one target |
| `steps` | shell commands instead of `cmake`, run in `/src` with `$CROSS` (the toolchain's target triplet), `$SOURCE`, `$BUILD_DIR` and `$DIST` set |
| `output.files` | what ships: `from` (a path in the container), `to` (under `dist/`), `strip` (`-s` or `--strip-unneeded`), `mode`, or `dir: true` to copy a directory |
| `output.spruce` | where `dist/` paths go on the card |
| `needed` | `device`: libraries the target devices provide; `forbidden`: libraries no shipped ELF may need (some devices lack them, or they must be opened at run time) |
| `shipped` | the spruceOS commit and the sha256 of each file spruce ships, to compare a build with (`match`, `differs` or `missing` in `record.json`) |

Python patch scripts from the spruceUI wrapper repositories are kept as diffs,
generated once against the pinned source: a script that no longer matches does
nothing and still succeeds, while a diff that no longer applies stops the build.

## What passes

There is no load test: a standalone emulator needs a display. A build passes when
every output exists and every library a shipped ELF needs is either on the
`device` list or shipped by the build itself, and nothing is `forbidden`. SDL2 is
never shipped: each device's SDL2 carries its own video driver. Whether the bytes
match what spruce ships is recorded, not required.

## Images

Each recipe builds in the environment its spruceUI wrapper repository used, rebuilt
from pinned parts (`Dockerfile.standalone.<name>`, loaded by `manifests/toolchains.json`):

| image | used by | built on |
|---|---|---|
| `arm64-standalone` | `flycast-standalone` | the arm64 image, with OpenSSL, curl and SDL2 built in |
| `standalone-vtree`, `-pcsx_rearmed`, `-moonlight`, `-gl4es`, `-ppsspp`, `-mupen64plus`, `-scummvm` | the 64-bit build of that emulator (`gl4es`: BigPEmu; `ppsspp`: H700) | the pinned arm64 base plus the wrapper's package list |
| `standalone-dsperate`, `standalone-yabasanshiro` | `dsperate-arm64`, `yabasanshiro-arm64` | the same, plus the Kitware CMake release the wrapper's build used |
| `standalone-armhf` | every `-a30` recipe | the pinned armhf base (the A30 GCC 13.2 toolchain and its glibc 2.23 sysroot) plus the tools the wrappers' `Dockerfile.a30` install |
| `standalone-flip` | `ppsspp-flip`, `ppsspp-rgb30` | Debian bookworm (by digest) with steward-fu's Flip toolchain (GCC 13.3) |
| `standalone-trimui` | `ppsspp-trimui` | the arm64 base's GCC 9.4 over Linaro 7.5's glibc and TrimUI's tg5040 SDK |
| `standalone-tsps` | `ppsspp-smartpros` | the compiler and sysroot of TrimUI's tg5050 SDK (GCC 10.3) |
| `standalone-yabasanshiro-pgo` | `yabasanshiro-arm64-pgo`, `yabasanshiro-libretro` | `standalone-yabasanshiro` plus Arm's GNU Toolchain 10.3-2021.07, a generic sysroot (its glibc 2.33, Khronos GLES headers, a stub libGLESv2) and the two builds' PGO profiles ([Saturn](#saturn-builds-spruceos-455)) |
| `standalone-mini` | `pcsx_rearmed-mini`, `scummvm-mini` | the armhf base (Ubuntu 24.04) with steward-fu's Onion toolchain (GCC 8.3, glibc 2.28) |
| `standalone-miyoomini` | `vtree-mini` | `aemiii91/miyoomini-toolchain`, by the digest its `latest` tag has had since 2026-01-20 |

The arm64 base is Ubuntu 20.04, whose archive no longer changes, so a package list
pins its versions. Libraries a wrapper built from source inside its image are built
by the recipe instead, from pinned sources or checked downloads.

## Reproducing a wrapper's build

- **Paths.** Build in the wrapper's paths: `__FILE__`, RUNPATH and install
  prefixes end up in binaries.
- **Build times.** A file that embeds `__DATE__ __TIME__` needs the original time as
  `source_date_epoch`. When two files embed different times (pcsx_rearmed's
  `main.c` and `menu.c`, ScummVM's `base/version.cpp` and
  `engines/bagel/spacebar/master_win.cpp`), the recipe builds at the earlier one,
  deletes the later object and runs `make` again at the later time.
- **Revisions.** `git config core.abbrev N` keeps an embedded `git describe` hash
  at the length the wrapper's shallow clone produced.
- **autoconf.** On a build host where qemu runs foreign binaries (`binfmt_misc`),
  a `configure` given only `--host` runs its target test programs, decides it is
  not cross-compiling and configures differently. Recipes always pass `--build`.
- **Link order.** Ubuntu 20.04's make 4.2.1 does not sort the glob in ScummVM's
  `-include engines/*/module.mk`, so the detection objects link in whatever order
  the build host's filesystem lists `engines/`. `scummvm-arm64` pins the order the
  wrapper's runner had (`arm64-1-detection-order.patch`); make 4.3 (Ubuntu 24.04)
  sorts it.
- **Which run shipped.** A wrapper's latest release asset is not always what spruce
  ships: spruceOS's import commit dates the run it took. spruce's 64-bit
  mupen64plus mixes two runs, so it takes two recipes.
- **The A30 toolchain's `python3`** comes first on that image's PATH and has no SSL
  module; downloads use the system one.
- **PGO builds** need the compiler at the path their training build used: GCC
  resolves a symlinked install to its real path, and header paths go into the
  profile's function ids, so a different path matches the profile differently
  and changes inlining and LTO partitioning. `standalone-yabasanshiro-pgo` keeps
  the compiler at both paths its two builds were trained with.

## Status

Built against spruceOS `73bb91a19` (2026-10-11); "match" is byte for byte.

| recipe | ships | result |
|---|---|---|
| `flycast-standalone` | `Emu/DC/flycast`, `lib64/` | 3 of 4 match; `libcrypto.so.1.1` differs only in OpenSSL's build date |
| `vtree-arm64`, `vtree-a30`, `vtree-mini` | `App/FileManagement/vtree.*`, `lib-A30/` | match |
| `pcsx_rearmed-arm64`, `-a30`, `-mini` | `Emu/PS/pcsx_64`, `pcsx_a30`, `pcsx_mini`, the `libSDL-1.2.so.0` copies | match |
| `moonlight` | `App/Moonlight/.../moonlight` and 32 libraries | match |
| `bigpemu` | `Emu/JAGUAR/bigpemu/` (134 files, gl4es included) | match |
| `dsperate-arm64`, `dsperate-a30` | `Emu/NDS/dsperate`, `dsperate.a30` | match |
| `ppsspp-h700`, `-a30`, `-flip`, `-rgb30`, `-trimui`, `-smartpros` | `Emu/PSP/PPSSPPSDL_*` | match |
| `yabasanshiro-arm64` | `Emu/SATURN/yabasanshiro`, `lib64/` | match |
| `yabasanshiro-arm64-pgo` | `Emu/SATURN/yabasanshiro`, `lib64/` of spruceOS `da37a290e` (4.5.5) | match |
| `yabasanshiro-libretro` | `RetroArch/.retroarch/cores64/yabasanshiro_generic_libretro.so` of spruceOS `da37a290e` (4.5.5) | match |
| `mupen64plus-arm64-20260404`, `mupen64plus-arm64` | `Emu/N64/mupen64plus/`: frontend, core, audio, input and RSP plugins from the first, video plugins and overlay settings from the second | match |
| `mupen64plus-a30` | `Emu/N64/mupen64plus-a30/` | match |
| `scummvm-a30`, `scummvm-mini` | `Emu/SCUMMVM/scummvm.a30`, `scummvm.mini` and its 96 plugins (inside spruceOS's 7z files), `liba30/`, `fixjoy`, `libmini/libfluidlite.so` | match |
| `scummvm-arm64` | `Emu/SCUMMVM/scummvm.64` (inside spruceOS's 7z), 12 libraries of `lib/` | match |

Some files next to these in spruceOS come from elsewhere and are not compared:
ScummVM's `lib/` extras and seven of `libmini/`'s libraries, among others.

## Flycast v2.7

`flycast-standalone` is the `Emu/DC/flycast` spruce ships (Dreamcast, NAOMI and
Atomiswave on every 64-bit device). It builds in the `arm64-standalone` image
([`Dockerfile.arm64.standalone`](../Dockerfile.arm64.standalone)): the arm64 image
plus ALSA and udev headers, and OpenSSL 1.1.1w, curl 8.7.1 and SDL2 2.28.5 in
`/opt/flycast-standalone-deps-arm64`. It reproduces the shipped executable,
`libcurl.so.4` and `libssl.so.1.1` byte for byte. `libcrypto.so.1.1` differs only
in OpenSSL's embedded build date and the build ID derived from it (33 bytes):
spruce's copy comes from an earlier build of the same image recipe.

## Saturn builds (spruceOS 4.5.5)

spruceOS 4.5.5 (branch `feat/opt-defaults-4.5.5`, `da37a290e`) ships two Saturn
builds picked by device benchmarks. Both were first built for those benchmarks, in
the research records `20261013-1113-yabasanshiro-rbgfix` and
`20261013-1351-saturn-sa-pgo-rbgfix` (outside this repository); these recipes
rebuild them.

- **`yabasanshiro-libretro`**: `RetroArch/.retroarch/cores64/yabasanshiro_generic_libretro.so`.
  libretro/yabause `f448097` plus two mails that recreate commit `892985a4`, so the
  core reports `v3.4.2 892985a`:
  - the GLES 3.1/3.2 entry points the libretro build declared but never
    resolved (the compute-shader and tessellation options called NULL);
  - the compute-shader rotation background (RBG): the window and CRAM buffers
    bound on every dispatch, which Mali and PowerVR drivers need or they drop the
    dispatch; a texture-fetch barrier and an orphaned VRAM map; `uint` literals
    in the 16bpp palette fetch.

  Then `dynarec-fix-nopragma.patch`: the AArch64 dynarec's templates kept
  values in caller-saved registers across memory-handler calls; it renames them
  and drops the 2020 `-O1` pragma that hid the bug. Built with Arm's GNU Toolchain
  10.3-2021.07 (GCC 10.3), `-O3 -flto` and PGO. The core catalog builds every core in its own
  image and takes no profile, so this build is a recipe here.
- **`yabasanshiro-arm64-pgo`**: `Emu/SATURN/yabasanshiro`. `yabasanshiro-arm64`
  plus the same dynarec fix and RBG fix for devMiyax's tree (whose `getTexture`
  already uses `GL_ALL_BARRIER_BITS`), and `bench-framelimit-env.patch`:
  `YB_FRAMELIMIT=1` switches the 60 Hz limiter off, and unset it limits as before.
  Built with the same GCC 10.3, `-O3 -flto=8` and PGO, against the image's focal
  arm64 packages; `cc-wrapper-t3.sh` adds what Ubuntu's cross GCC does by default
  (PIE, `--as-needed`), so the binary needs only the libraries the CI build needs.

**No vendor SDK.** Both were first built with the compiler from TrimUI's tg5050 SDK, and the core
also with its sysroot. That compiler is Arm's GNU Toolchain 10.3-2021.07, unmodified, and the
sysroot's C library is that toolchain's glibc 2.33, so the image takes the toolchain from Arm and
builds the core's sysroot from it, the Khronos GLES headers the core was compiled against, and a
stub `libGLESv2.so.2`.

**Profiles.** `toolchain-inputs/yabasanshiro-pgo/` holds gcov counters of the
emulator's own code (no game data), written by `-fprofile-generate` builds of the
same sources running Sega Rally from power-on to frame 1680 on four lab boards
(Smart Pro S, Brick Pro, two RG XX; the libretro set adds the Flip). Each recipe
sums its set with the toolchain's `gcov-tool` (`pgo-merge.sh`). GCC drops the
profile of a function whose code changed after training: `context_reset`,
`retro_run` and the RBG generator's `init` and `update` in the core, the RBG
generator's `init` and `update` in the standalone. The other
`-Wcoverage-mismatch` warnings are line shifts, whose profiles GCC still uses.
