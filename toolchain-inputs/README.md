# Toolchain image inputs

Builds use the three images published on the `toolchains` release.
`manifests/toolchains.json` pins each archive's digest and image ID, and builds
run only on those exact images.

This directory and the `Dockerfile.*` files record how the images were made.
Rebuilding produces different image IDs, so rebuild only to change a toolchain;
then publish the new archives and update `manifests/toolchains.json`.

```bash
DOCKER_BUILDKIT=0 docker build -f Dockerfile.arm64 -t cores-arm64:latest toolchain-inputs
DOCKER_BUILDKIT=0 docker build -f Dockerfile.armhf -t cores-armhf:latest toolchain-inputs
DOCKER_BUILDKIT=0 docker build -f Dockerfile.rust  -t cores-rust:latest  toolchain-inputs
```

Every input is checked against a sha256 in its Dockerfile. `rust.tar.gz` is too
large for git; fetch it first:

```bash
curl -L -o toolchain-inputs/rust.tar.gz \
  https://static.rust-lang.org/dist/rust-1.90.0-x86_64-unknown-linux-gnu.tar.gz
```

The arm64 and armhf Dockerfiles start from archived base images by image ID
(see their headers), so those base images must be loaded first.
