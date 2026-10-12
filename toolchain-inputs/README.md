# Toolchain images

Every core builds in one of three Docker images, and standalone emulators in
images of their own. `manifests/toolchains.json` pins each by image ID and names its archive
on the `toolchains` release; a build refuses to run on any other image.

| toolchain | image ID | archive | recipe |
|---|---|---|---|
| arm64 | `538411e2759c` | `cores-arm64.tar.gz` | `Dockerfile.arm64` on base `c9c1332ce018` |
| armhf | `3c5f1e9c40cb` (v4) | `cores-armhf-v4.tar.gz` | `Dockerfile.armhf` on base `6ac154886195` |
| rust | `aa42a12ced6b` | `cores-rust.tar.gz` | `Dockerfile.rust` (on Ubuntu, no base) |
| arm64-standalone | `c630f837fad0` (v1) | `cores-arm64-standalone-v1.tar.gz` | `Dockerfile.arm64.standalone` on the arm64 image `538411e2759c` ([standalone emulators](../docs/standalone.md)) |
| standalone-* | see `manifests/toolchains.json` | `cores-standalone-<name>-v1.tar.gz` | `Dockerfile.standalone.<name>`, one per spruceUI wrapper build environment, on base `c9c1332ce018` or `6ac154886195` (Flip: Debian bookworm by digest) |

`cores-armhf.tar.gz` (armhf v2, `393a23661c41`) stays on the release because
older commits pin it. Never replace a published archive: give a new image a new
archive name.

## How the images are built

- **Bases** (`Dockerfile.arm64.base`, `Dockerfile.armhf.base`): Ubuntu, the
  cross compiler and libretro-super at `60f5c627`. Their apt steps install
  whatever the Ubuntu mirrors serve that day, so a rebuilt base is never the
  same image. The two bases in use are archived on the release:

  | base | archive | sha256 |
  |---|---|---|
  | arm64 `c9c1332ce018` | `cores-arm64-base-c9c1332ce018.tar.gz` (259 MB) | `9c4816d569bcaae1d2ce59d7ea8e4749eeb05468015390da401e09fa0eff7aa7` |
  | armhf `6ac154886195` | `cores-armhf-base-6ac154886195.tar.gz` (653 MB) | `6a193cc28412f1636fc128f36990452fbf189b4fabd5b0112641747bab343734` |

- **Toolchain images** (`Dockerfile.arm64`, `Dockerfile.armhf`) start `FROM`
  the base by image ID and add the pinned tarballs in this folder (CMake, inih,
  libpng, easyrpg's static dependencies). Every input is checked against a
  sha256 in its Dockerfile. `Dockerfile.arm64.standalone` starts from the arm64
  toolchain image itself and adds OpenSSL, curl and SDL2 from this folder.
- **Rust image** (`Dockerfile.rust`): Ubuntu by digest plus pinned tarballs.

Inputs that are too large for git, each sha256-checked by its Dockerfile:

| file | for | where |
|---|---|---|
| `rust.tar.gz` | `Dockerfile.rust` | https://static.rust-lang.org/dist/rust-1.90.0-x86_64-unknown-linux-gnu.tar.gz |
| `a30_toolchain-v1.0.tar.gz` | `Dockerfile.armhf.base` | this repository's `toolchains` release (a copy of the one on spruceUI/Cores-spruce's) |
| `flip-toolchain-v1.0.tar.gz` | `Dockerfile.standalone.flip` | https://github.com/steward-fu/website/releases/download/miyoo-flip/flip-toolchain-v1.0.tar.gz |
| `aarch64-linux-gnu-7.5.0-linaro.tgz`, `SDK_usr_tg5040_a133p.tgz` | `Dockerfile.standalone.trimui` | spruceUI/PPSSPP-spruce's `sdk-toolchains` release |
| `sdk_tg5050_linux_v1.0.0.tgz` (1.1 GB) | `Dockerfile.standalone.tsps` | spruceUI/PPSSPP-spruce's `sdk-toolchains` release |
| `onion_toolchain.tar.gz` | `Dockerfile.standalone.mini` | https://github.com/steward-fu/website/releases/download/miyoo-mini/onion_toolchain.tar.gz |

## Changing a toolchain image

Use this to add or change anything above the base (the usual case).

```bash
gh release download toolchains -p cores-armhf-base-6ac154886195.tar.gz
gunzip -c cores-armhf-base-6ac154886195.tar.gz | docker load
DOCKER_BUILDKIT=0 docker build -f Dockerfile.armhf -t cores-armhf:v5 toolchain-inputs
docker save cores-armhf:v5 | gzip -n > cores-armhf-v5.tar.gz
docker image inspect -f '{{.Id}}' cores-armhf:v5; sha256sum cores-armhf-v5.tar.gz; stat -c %s cores-armhf-v5.tar.gz
```

1. Put the new image ID, archive name, size and sha256 in `manifests/toolchains.json`.
2. Build every core of that arch (`python3 scripts/cores.py plan --arch armhf`
   lists them) and compare the artifacts' sha256 with the previous image's
   builds. Only cores that use what changed may differ; armhf v4 left 92 of 94
   byte-identical.
3. Upload the archive to the `toolchains` release under its new name.

## Changing a base

Only to change the compiler, the OS or libretro-super. Every core's bytes will
change, so rebuild and check all of them.

```bash
DOCKER_BUILDKIT=0 docker build -f Dockerfile.arm64.base -t cores-arm64-base:new toolchain-inputs
gh release download toolchains -p a30_toolchain-v1.0.tar.gz -D toolchain-inputs   # armhf only
DOCKER_BUILDKIT=0 docker build -f Dockerfile.armhf.base -t cores-armhf-base:new toolchain-inputs
```

Then point the `FROM` line of `Dockerfile.<arch>` at the new base's image ID,
rebuild the toolchain image as above, and archive the new base on the release
too (`cores-<arch>-base-<id>.tar.gz`).

## History

- The bases were built on 2026-04-05. The `cores-arm64.tar.gz` and
  `cores-armhf.tar.gz` on spruceUI/Cores-spruce's release are an earlier
  generation (images `63f40dda`, `122b2008`), not these bases.
- arm64 v2 and armhf v2 (2026-07) added CMake 3.31, easyrpg's dependencies and
  libpng on top of the bases.
- armhf v4 (2026-10-07): libpng built with `-fPIC`, so easyrpg links it
  statically; mpg123 built with `--with-cpu=arm_fpu` (NEON decoder, chosen at
  run time).
- Standalone images (2026-10-12): one per spruceUI wrapper repository's build
  environment, so each recipe reproduces what spruce ships. None is on the
  release yet.
