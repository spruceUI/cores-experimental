# Catalog reference

`manifests/core-builds.json` holds one entry per core under `cores`. The entry
is the whole recipe: `scripts/cores.py script <core> <arch>` prints the shell
script it becomes, and `scripts/cores.py check` validates it offline.

```json
"np2kai": {
  "source": {"url": "https://github.com/libretro/NP2kai.git",
             "commit": "54ec39f50d197cc02909cd4fd2a8591bb38651b0",
             "requested_ref": "refs/heads/master"},
  "targets": ["arm64", "armhf"],
  "build": {
    "driver": "libretro-super",
    "source_key": "np2kai", "source_dir": "libretro-np2kai",
    "output_path": "dist/unix/np2kai_libretro.so", "artifact_name": "np2kai_libretro.so",
    "overlays": {"arm64": [{"patch": "patches/np2kai/makefile-sort-wildcard-sources.patch"}],
                 "armhf": [{"patch": "patches/np2kai/makefile-sort-wildcard-sources.patch"}]}
  },
  "metadata": {"artifact_name": "np2kai_libretro.info",
               "source_path": "/libretro-super/dist/info/np2kai_libretro.info"}
}
```

## Fields

**`source`** — `url` and the full 40-character `commit` that is built;
`requested_ref` records which branch or tag the commit came from.

**`targets`** — `arm64`, `armhf` or both. `universal` builds every target; a
board builds only its own arch.

**`build.driver`** picks the template:

| driver | how it builds | driver fields |
|---|---|---|
| `libretro-super` | `./libretro-fetch.sh` + `./libretro-build.sh <source_key>` inside the image's libretro-super checkout, then checks out `commit` | `source_key`, `source_dir`, `output_path` (relative to `/libretro-super`) |
| `direct-make` | shallow fetch of `commit`, then `make -j$(nproc) [-C make_subdir] [platform=…] [make_args] CC=… CXX=… AR=… RANLIB=…` | `make_subdir`, `platforms` (`{arch: value}`), `make_args` (list), `output_path` (relative to the source) |
| `direct-cmake` | shallow fetch, `cmake` Release with the cross tools, `cmake --build --target` | `cmake.target`, `cmake.defines`, `cmake.arch_defines` (`{arch: {name: value}}`), `cmake.source_subdir`, `output_path` (relative to the build dir) |
| `direct-cargo` | shallow fetch, `cargo zigbuild --locked --release` | `cargo.subdir`, `cargo.targets` (`{arch: triple}`), `output_path` (file name in `target/<triple>/release/`) |

`artifact_name` is the file the core is installed as.

**Recipe knobs** (all optional, every driver):

| field | effect |
|---|---|
| `overlays` | `{arch: [{"patch": path, "submodule": path?}]}` — applied in order with `git apply --check` then `git apply`; `submodule` applies inside that submodule with the leading path stripped |
| `compile_definitions` | `{arch: ["NAME=VALUE", …]}` — exported as `-D` flags in `CFLAGS` and `CXXFLAGS` |
| `source_date_epoch` | `true` — exports `SOURCE_DATE_EPOCH` as the commit's timestamp, for cores that embed build dates |
| `git_abbrev` | `N` — pins git's `core.abbrev` for cores whose makefile bakes `git rev-parse --short` into the binary; without it the length grows with the upstream repository and the bytes change |
| `env` | `[[NAME, value], …]` — exported before the build |
| `makeflags` | exported as `MAKEFLAGS`, so its variables override the core's makefile |
| `command_env` | `[[NAME, value], …]` — set only on the `libretro-build.sh` command |
| `command` | a list of shell lines, or `{arch: [lines]}`, that replaces the driver's build command (picodrive) |
| `neon` | switches for armhf builds whose flags turn NEON on (the a33 and ssd202d boards): `NAME=VALUE` make variables (CMake defines for `direct-cmake`) and `-DNAME` compile definitions. Needed where a makefile only compiles its NEON assembly under a switch such as `HAVE_NEON=1`, because the board's `-mfpu=neon-vfpv4` makes the C side call it |
| `submodules` | `false` — skip submodule checkout (a stray gitlink without `.gitmodules`) |
| `recursive_submodules` | `false` — check out top-level submodules only |

Values in `env`, `makeflags`, `command_env` and `command` may use
`{commit:N}`, which expands to the first N characters of `commit`. This is how
cores that bake a short hash into their version string stay correct when the
commit changes, e.g. `"makeflags": "GIT_VERSION=-{commit:7}"`.

**`metadata`** — `artifact_name` plus either `source_path` (an `.info` file
inside the image's libretro-super) or `repo_path` (a file under `metadata/`).

**`known_good`** — a previous `source`/`build`/`metadata` that is known to
work. Only CI uses it, as the fallback when the current commit fails.

## Adding a core

1. Add the entry. Start from a core with the same driver; `check` reports
   missing fields, unknown drivers and patches that are not on disk.
2. `python3 scripts/cores.py script <core> arm64` to read what will run.
3. `python3 scripts/cores.py build --core <core>` locally, or run the *Build
   cores* workflow with that core. It passes when the core builds and loads.

## Moving a core to a new commit

```bash
python3 scripts/cores.py bump fbneo --commit <new sha> [--ref refs/heads/master]
python3 scripts/cores.py build --core fbneo
```

`bump` stores the current recipe as `known_good` and switches `commit`;
`{commit:N}` values and `SOURCE_DATE_EPOCH` follow automatically. It warns
about values it cannot derive (fbneo's `GIT_DATE`, the commit date). If a
patch stops applying, refresh or drop it (see [patches](../patches/README.md)).
Bump from a commit that passes, so `known_good` really is.
