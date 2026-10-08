# Standalone emulators

Some emulators spruce ships are executables rather than libretro cores. Their
recipes are in [`manifests/standalone-builds.json`](../manifests/standalone-builds.json)
and they build in the `arm64-standalone` toolchain image
([`Dockerfile.arm64.standalone`](../Dockerfile.arm64.standalone)): the arm64 image
plus ALSA and udev headers, and OpenSSL 1.1.1w, curl 8.7.1 and SDL2 2.28.5 built
into `/opt/flycast-standalone-deps-arm64`.

```bash
python3 scripts/cores.py standalone list
python3 scripts/cores.py standalone script flycast-standalone   # the build script
python3 scripts/cores.py standalone build flycast-standalone --out results
```

A build leaves the executable, its bundled libraries in `lib/`, the build script,
`build.log` and `record.json` in `results/<name>/`. Copy the executable to
`spruce_path` and the libraries to `spruce_library_dir` on the card.

## Recipe fields

| field | meaning |
|---|---|
| `source` | repository `url`, full `commit`, its `tree` (checked after checkout) and `requested_ref` |
| `toolchain` | the image in `manifests/toolchains.json` |
| `source_date_epoch` | fixed build date, so the output does not depend on when it was built |
| `cmake` | `target`, then `cross_defines` and `defines`, passed in that order |
| `output` | `binary`; `bundled_libraries` copied from the dependency prefix (no device has them); `spruce_path` and `spruce_library_dir` on the card |
| `needed` | `device`: libraries every 64-bit device provides; `forbidden`: libraries the binary must not need (some devices lack them, or they must be opened at run time) |

## What passes

There is no load test: a standalone emulator needs a display. A build passes
when it produces the executable and everything it and its bundled libraries need
is either on the `device` list or bundled, and nothing is `forbidden`. SDL2 is
never bundled: each device's SDL2 carries its own video driver, so the binary
is linked against SDL2 2.28.5's headers and uses whatever SDL2 the device has.

## Flycast v2.7

`flycast-standalone` is the `Emu/DC/flycast` spruce ships (Dreamcast, NAOMI and
Atomiswave on every 64-bit device). This recipe reproduces the shipped
executable, `libcurl.so.4` and `libssl.so.1.1` byte for byte. `libcrypto.so.1.1`
differs only in OpenSSL's embedded build date and the build ID derived from it
(33 bytes): spruce's copy comes from an earlier build of the same image recipe.
