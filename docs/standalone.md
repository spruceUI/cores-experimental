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
| `source` | repository `url`, full `commit`, its `tree` (checked after checkout), `requested_ref`, and `submodules: true` to fetch them |
| `extra_sources` | more repositories, the same fields plus an absolute `path` to check out into |
| `downloads` | files fetched at build time: `url`, `sha256` (checked before use) and an absolute `path` |
| `patches` | `{"diff": "patches/standalone/..."}`, applied with `git apply` (which fails if the diff no longer applies), or `{"script": ...}`, run with Python; `dir` picks the tree (default `/src`) |
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

## Flycast v2.7

`flycast-standalone` is the `Emu/DC/flycast` spruce ships (Dreamcast, NAOMI and
Atomiswave on every 64-bit device). It builds in the `arm64-standalone` image
([`Dockerfile.arm64.standalone`](../Dockerfile.arm64.standalone)): the arm64 image
plus ALSA and udev headers, and OpenSSL 1.1.1w, curl 8.7.1 and SDL2 2.28.5 in
`/opt/flycast-standalone-deps-arm64`. It reproduces the shipped executable,
`libcurl.so.4` and `libssl.so.1.1` byte for byte. `libcrypto.so.1.1` differs only
in OpenSSL's embedded build date and the build ID derived from it (33 bytes):
spruce's copy comes from an earlier build of the same image recipe.
