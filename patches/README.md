# Source patches

Each core's patches are listed in its catalog entry (`build.overlays.<arch>`,
see [docs/catalog.md](../docs/catalog.md)) and applied in order with
`git apply --check` then `git apply` after the pinned checkout. A patch that
no longer applies fails the build.

When a core moves to a new commit, rebuild it: if a patch stopped applying,
refresh it; if upstream fixed the problem, delete the patch and its entry.

| core | patch | fixes | arch |
|------|-------|-------|------|
| chailove | `chailove/makefile-sort-wildcard-sources.patch` | sort `$(wildcard)` sources so link order is stable | arm64+armhf |
| easyrpg | `easyrpg/liblcf-pinned-clone.patch` | pin the configure-time liblcf clone to commit `666e6c02` | arm64+armhf |
| flycast | `flycast/lzma-hwcap2-guards.patch` | ifndef-zero guards for `HWCAP2_*` names absent from the A30 sysroot headers | armhf |
| km_parallel_n64_xtreme_amped_turbo | `makefile-fcommon.patch` | `COREFLAGS += -fcommon` (fork predates GCC 10's -fno-common default) | armhf |
| km_parallel_n64_xtreme_amped_turbo | `glide64-rdp-gspvertex-def.patch` | single definition for the tentative `_gSPVertex` | armhf |
| km_parallel_n64_xtreme_amped_turbo | `rdp-gspvertex-extern.patch` | extern declaration for `_gSPVertex` in rdp.h | armhf |
| km_parallel_n64_xtreme_amped_turbo | `glsm-gldouble-typedef.patch` | restore the fork's commented-out `GLdouble` typedef under GLES2 | armhf |
| km_parallel_n64_xtreme_amped_turbo | `parallel-al-stdexcept.patch` | missing `<stdexcept>` include | armhf |
| squirreljme | `squirreljme/system-map-arm32-or.patch` | upstream system-map.cmake ARM32 elseif missing a trailing `OR` | armhf |
| squirreljme | `squirreljme/decode-host-cc.patch` | build the configure-time decode tool with the host `cc` | armhf |
| squirreljme | `squirreljme/sourceize-host-cc.patch` | build the configure-time sourceize tool with the host `cc` | armhf |
| swanstation | `swanstation/openbios-cmake-3.16.patch` | OpenBIOS CMake 3.16 compatibility | arm64 |

The remaining `*-sort-wildcard-sources.patch` files (crocods, dosbox_pure,
fbalpha2012, fbneo, fceumm, genesis_plus_gx, np2kai, ...) sort `$(wildcard)`
results so the link order, and therefore the artifact bytes, do not depend on
directory order.
