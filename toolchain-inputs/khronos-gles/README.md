# Khronos GLES headers

The GLES 2/3 and KHR headers `yabasanshiro-libretro` compiles against, byte for byte the versions in TrimUI's tg5050
SDK sysroot it was first built with, taken here from Khronos's own registries (MIT-style Khronos licence in each file):

| file | source | commit |
|---|---|---|
| `GLES2/gl2.h` | KhronosGroup/OpenGL-Registry `api/GLES2/gl2.h` | `7443932dcac7` (2018-09-05) |
| `GLES2/gl2ext.h` | KhronosGroup/OpenGL-Registry `api/GLES2/gl2ext.h` | `a84809c3b385` (2018-09-05) |
| `GLES2/gl2platform.h` | KhronosGroup/OpenGL-Registry `api/GLES2/gl2platform.h` | `f37a01b810c6` (2017-01-21) |
| `GLES3/gl3.h` | KhronosGroup/OpenGL-Registry `api/GLES3/gl3.h` | `7443932dcac7` (2018-09-05) |
| `GLES3/gl31.h`, `gl32.h`, `gl3platform.h` | KhronosGroup/OpenGL-Registry `api/GLES3/` | `f37a01b810c6` (2017-01-21) |
| `KHR/khrplatform.h` | KhronosGroup/EGL-Registry `api/KHR/khrplatform.h` | `5804dc63f9ca` (2018-03-15) |

`Dockerfile.standalone.yabasanshiro-pgo` checks each file's sha256 and puts them in its generic sysroot.
