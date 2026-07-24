# Source patches inventory

Every source patch applied during a core build lives under `patches/<core>/` and
**must be listed here**. A patch is pinned to an exact pinned source commit by
three digests: the patch file's own `patch_sha256`, the `preimage_sha256` of the
file it modifies (before the patch), and the `postimage_sha256` (after). Each
patch is a single-file `git-apply-v1` diff and must apply cleanly with
`git apply --whitespace=error-all` to the pinned checkout.

## Repo norm: revalidate patches on every source update

Patches are pinned to exact source content, so a source bump silently
invalidates them. **When a core's pinned source commit (or tree) is updated, you
MUST, before promoting the new pin:**

1. Re-fetch the new pinned source and confirm each patch still applies cleanly.
2. Recompute and update `preimage_sha256` / `postimage_sha256` (and
   `patch_sha256` if the patch text changed).
3. Confirm the underlying issue the patch addresses still exists and the fix is
   still correct/minimal — delete the patch if upstream fixed it.
4. Add or update the patch's row in this inventory.

The build is fail-closed on all three digests, so a stale patch blocks the
build rather than silently mis-applying.

## Inventory

| core | patch | source file | fixes | applied via |
|------|-------|-------------|-------|-------------|
| swanstation | `swanstation/openbios-cmake-3.16.patch` | `dep/openbios/CMakeLists.txt` | OpenBIOS CMake 3.16 compatibility | `direct-cmake` `build.overlays` |
| picodrive | `picodrive/tools-makefile-single-line-offsets.patch` | `tools/Makefile` | collapse the multi-line offsets `if/then/else/fi` recipe to one line so `make`'s echo does not emit a compiler-naming line ending in a bare `\` (which breaks the compile-definitions checker's `shlex.split` on armhf) | `libretro-super` `picodrive-v1` recipe |

### Digests

**swanstation/openbios-cmake-3.16.patch** — `source_path: dep/openbios/CMakeLists.txt`
- patch_sha256: `4cfef36e9516b30853c9f23b1886821ffe21a25769abddd4246310a19e85f423`
- preimage_sha256: `df18f952f03c19525a82ac485cc19abcf360f25d452336b993983a80ae63b870`
- postimage_sha256: `8c84dfdb832ce0c1440d9db3ed2e8d95df4359f6032727389cc4d760a50756b3`

**picodrive/tools-makefile-single-line-offsets.patch** — `source_path: tools/Makefile`
- pinned source commit: `f0d4a0118a9733a1f10bce5a4ac772c474f9300d`
- patch_sha256: `2c442768b54d5ffd52ab06530e67dc582c4f9b0dac8f2d1d9ccea9739444053c`
- preimage_sha256: `9c738f02c4afb1b13d95421f74092d9af77b8c8f0f8ae55dfa0e9b7b4f6df44d`
- postimage_sha256: `2d36ea4092510e7547274ac4361897c9992ccb7db2362c622c6d9e1d76426843`
