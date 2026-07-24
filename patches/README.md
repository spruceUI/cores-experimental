# Source patches inventory

Every source patch applied during a core build lives under
`patches/<core>/` and is pinned by three digests: the patch file's own
`patch_sha256`, the `preimage_sha256` of the file it modifies, and the
`postimage_sha256` after. Each patch is a single-file `git-apply-v1` diff
that must apply cleanly with `git apply --whitespace=error-all` to the
pinned checkout. The build is fail-closed on all three digests, so a
stale patch blocks the build rather than silently mis-applying.

**The authoritative digest record is the catalog**
(`manifests/core-builds.json`, each core's `build.overlays`); this
inventory is the human index and is regenerable from it.

## Repo norm: revalidate patches on every source update

Patches are pinned to exact source content, so a source bump silently
invalidates them. **When a core's pinned source commit (or tree) is
updated, you MUST, before promoting the new pin:**

1. Re-fetch the new pinned source and confirm each patch still applies
   cleanly.
2. Recompute and update `preimage_sha256` / `postimage_sha256` (and
   `patch_sha256` if the patch text changed) in the catalog entry.
3. Confirm the underlying issue the patch addresses still exists and the
   fix is still correct/minimal — delete the patch if upstream fixed it.
4. Regenerate this inventory if the patch set changed.

## Inventory

| core | patch | fixes | arch |
|------|-------|-------|------|
| chailove | `chailove/makefile-echo-compile.patch` | unsilence the hardcoded `Q=@` compile echo (log-proof visibility; artifact byte-identical) | arm64+armhf |
| dosbox_pure | `dosbox_pure/makefile-echo-compile.patch` | unsilence the hardcoded `@` compile echo (log-proof visibility; artifact byte-identical) | arm64+armhf |
| easyrpg | `easyrpg/liblcf-pinned-clone.patch` | pin the configure-time liblcf clone to commit `666e6c02` with a hard tree assert | arm64+armhf |
| flycast | `flycast/lzma-hwcap2-guards.patch` | ifndef-zero guards for `HWCAP2_*` names absent from the A30 sysroot UAPI headers | armhf |
| km_parallel_n64_xtreme_amped_turbo | `km_parallel_n64_xtreme_amped_turbo/makefile-fcommon.patch` | `COREFLAGS += -fcommon` (fork predates GCC 10's -fno-common default) | armhf |
| km_parallel_n64_xtreme_amped_turbo | `km_parallel_n64_xtreme_amped_turbo/glide64-rdp-gspvertex-def.patch` | single definition for the tentative `_gSPVertex` | armhf |
| km_parallel_n64_xtreme_amped_turbo | `km_parallel_n64_xtreme_amped_turbo/rdp-gspvertex-extern.patch` | extern declaration for `_gSPVertex` in rdp.h | armhf |
| km_parallel_n64_xtreme_amped_turbo | `km_parallel_n64_xtreme_amped_turbo/glsm-gldouble-typedef.patch` | restore the fork's commented-out `GLdouble` typedef under GLES2 | armhf |
| km_parallel_n64_xtreme_amped_turbo | `km_parallel_n64_xtreme_amped_turbo/parallel-al-stdexcept.patch` | missing `<stdexcept>` include | armhf |
| picodrive | `picodrive/tools-makefile-single-line-offsets.patch` | collapse a multi-line offsets recipe whose echo broke compile-line parsing | armhf |
| squirreljme | `squirreljme/system-map-arm32-or.patch` | upstream system-map.cmake ARM32 elseif missing a trailing `OR` | armhf |
| squirreljme | `squirreljme/decode-host-cc.patch` | build the configure-time decode tool with the host `cc`, not the cross compiler | armhf |
| squirreljme | `squirreljme/sourceize-host-cc.patch` | build the configure-time sourceize tool with the host `cc` | armhf |
| swanstation | `swanstation/openbios-cmake-3.16.patch` | OpenBIOS CMake 3.16 compatibility | arm64 |

## Digests

Per-patch `patch_sha256` / `preimage_sha256` / `postimage_sha256` live in
the catalog next to each overlay (and, for picodrive's recipe-profile
patch, in its recipe profile). Query them directly:

```bash
python3 - <<'PY'
import json
c = json.load(open('manifests/core-builds.json'))
for cid, s in sorted(c['cores'].items()):
    for arch, ovs in s.get('build', {}).get('overlays', {}).items():
        for o in ovs:
            print(cid, arch, o['patch_path'], o['patch_sha256'][:12])
PY
```
