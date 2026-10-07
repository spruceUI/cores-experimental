# Catalog reference

`manifests/core-builds.json` has one entry per core under `cores`. The entry is
the whole recipe. `scripts/cores.py script <core> <arch>` prints the build script
it becomes, and `scripts/cores.py check` validates the catalog without building.

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
    "git_abbrev": 7,
    "overlays": {
      "arm64": [{"patch": "patches/np2kai/makefile-sort-wildcard-sources.patch"},
                {"patch": "patches/np2kai/makefile-libretro-sort-wildcard-sources.patch"}],
      "armhf": [{"patch": "patches/np2kai/makefile-sort-wildcard-sources.patch"},
                {"patch": "patches/np2kai/makefile-libretro-sort-wildcard-sources.patch"}]}
  },
  "metadata": {"artifact_name": "np2kai_libretro.info",
               "source_path": "/libretro-super/dist/info/np2kai_libretro.info"}
}
```

## Fields

**`source`**: the repository `url` and the full 40-character `commit` to build;
`requested_ref` notes which branch or tag the commit came from.

**`targets`**: `arm64`, `armhf` or both.

**`build.driver`** picks how the core is built:

| driver | build | fields |
|---|---|---|
| `libretro-super` | `libretro-fetch.sh` and `libretro-build.sh` from the image's libretro-super, at `commit` | `source_key`, `source_dir`, `output_path` (relative to `/libretro-super`) |
| `direct-make` | `make` in the source tree | `make_subdir`, `platforms` (`{arch: value}`), `make_args`, `output_path` (relative to the source) |
| `direct-cmake` | CMake Release build of one target | `cmake.target`, `cmake.defines`, `cmake.arch_defines` (`{arch: {name: value}}`), `cmake.source_subdir`, `output_path` (relative to the build directory) |
| `direct-cargo` | `cargo zigbuild --release` | `cargo.subdir`, `cargo.targets` (`{arch: triple}`), `output_path` |

`artifact_name` is the file name the core is installed under.

Optional fields, for any driver:

| field | effect |
|---|---|
| `overlays` | patches to apply per arch: `{arch: [{"patch": path}]}`; add `"submodule": path` for a patch to a submodule |
| `compile_definitions` | `{arch: ["NAME=VALUE", …]}`, passed as `-D` flags |
| `source_date_epoch` | `true` for cores that embed the build date: the date becomes the commit's |
| `git_abbrev` | for cores that embed a short git hash: fixes its length, which git otherwise grows as the upstream repository grows |
| `env` | `[[NAME, value], …]` exported before the build |
| `makeflags` | exported as `MAKEFLAGS`; its variables override the core's makefile |
| `command_env` | `[[NAME, value], …]` set only on the `libretro-build.sh` command |
| `command` | shell lines, or `{arch: [lines]}`, that replace the build command (picodrive) |
| `neon` | switches for builds with NEON flags only ([why](flags.md#neon-switches)): make variables `NAME=VALUE` (CMake defines for `direct-cmake`) or `-DNAME` |
| `submodules` | `false` to skip submodules |
| `recursive_submodules` | `false` to fetch top-level submodules only |

In `env`, `makeflags`, `command_env` and `command`, `{commit:N}` stands for the
first N characters of `commit`, e.g. `"makeflags": "GIT_VERSION=-{commit:7}"`.

**`metadata`**: the core's `.info` file, by `artifact_name` plus either
`source_path` (a file in the image's libretro-super) or `repo_path` (a file
under `metadata/`).

**`known_good`**: an earlier `source`, `build` and `metadata` that worked. CI
builds it when the current commit fails; nothing else uses it.

## Adding a core

1. Add an entry, starting from a core with the same driver. `check` reports
   missing fields and patches that are not on disk.
2. Read the build script with `python3 scripts/cores.py script <core> arm64`.
3. Build it with `python3 scripts/cores.py build --core <core>`, or with the
   *Build cores* workflow. It passes when the core builds and loads.

## Moving a core to a new commit

```bash
python3 scripts/cores.py bump fbneo --commit <new sha> [--ref refs/heads/master]
python3 scripts/cores.py build --core fbneo
```

`bump` keeps the current recipe as `known_good` and switches `commit`; values
that use `{commit:N}` and the build date follow automatically. It warns about
values it cannot work out itself, such as fbneo's `GIT_DATE`. If a patch no
longer applies, update or remove it ([patches](../patches/README.md)). Bump
from a commit that works, so `known_good` is really good.
