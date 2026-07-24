# Toolchain image inputs

This directory is the **docker build context** for the three toolchain
images. Every input is pinned: the Dockerfiles refuse any bytes whose
sha256 differs from the value hardcoded next to the COPY.

Build the images from the repository root:

```bash
DOCKER_BUILDKIT=0 docker build -f Dockerfile.arm64 -t cores-arm64:latest toolchain-inputs
DOCKER_BUILDKIT=0 docker build -f Dockerfile.armhf -t cores-armhf:latest toolchain-inputs
DOCKER_BUILDKIT=0 docker build -f Dockerfile.rust  -t cores-rust:latest  toolchain-inputs
```

One input is not repo-tracked: `rust.tar.gz` (the Rust 1.90.0 host
toolchain, 365 MB, over GitHub's 100 MB file limit). Fetch it before
building the Rust image; the sha gate in `Dockerfile.rust` verifies it:

```bash
curl -L -o toolchain-inputs/rust.tar.gz \
  https://static.rust-lang.org/dist/rust-1.90.0-x86_64-unknown-linux-gnu.tar.gz
```

The arm64/armhf images additionally derive FROM archived base images by
immutable ID (see the Dockerfile headers): rebuilding them byte-exact
requires those bases loaded locally, which is the point — the canonical
image bytes live in the locked archives
(`pins/toolchains/local-cache-v1.json`), not in a re-runnable recipe.
