/*
 * Minimal libretro content-free load smoke loader.
 *
 * dlopens a libretro core (RTLD_NOW forces eager symbol resolution, so an
 * insufficient provider — e.g. a libstdc++ whose GLIBCXX is below what the core
 * needs — fails here) and exercises the content-free load sequence, printing one
 *   CHECK <name> pass|fail
 * line per step for the executor to parse. It loads no content and runs no
 * frames; those need a game and belong to a later playability tier.
 *
 * Built and run inside the target-ABI container under qemu (or on a native ARM
 * runner). Compile: cc -O0 smoke_loader.c -o smoke_loader -ldl
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define RETRO_API_VERSION 1

struct retro_system_info {
    const char *library_name;
    const char *library_version;
    const char *valid_extensions;
    bool need_fullpath;
    bool block_extract;
};

typedef bool (*retro_environment_t)(unsigned cmd, void *data);

/* Minimal frontend: decline every optional environment request. A core must
 * tolerate a frontend that supports nothing in order to initialise. */
static bool env_cb(unsigned cmd, void *data) {
    (void)cmd;
    (void)data;
    return false;
}

static void report(const char *name, int ok) {
    printf("CHECK %s %s\n", name, ok ? "pass" : "fail");
    fflush(stdout);
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <core.so>\n", argv[0]);
        return 2;
    }

    void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    report("dlopen", handle != NULL);
    if (!handle) {
        fprintf(stderr, "dlopen: %s\n", dlerror());
        return 1;
    }

    unsigned (*p_api_version)(void) =
        (unsigned (*)(void))dlsym(handle, "retro_api_version");
    void (*p_set_environment)(retro_environment_t) =
        (void (*)(retro_environment_t))dlsym(handle, "retro_set_environment");
    void (*p_init)(void) = (void (*)(void))dlsym(handle, "retro_init");
    void (*p_get_system_info)(struct retro_system_info *) =
        (void (*)(struct retro_system_info *))dlsym(handle, "retro_get_system_info");
    void (*p_deinit)(void) = (void (*)(void))dlsym(handle, "retro_deinit");

    report("retro_api_version",
           p_api_version != NULL && p_api_version() == RETRO_API_VERSION);

    int set_env_ok = p_set_environment != NULL;
    if (set_env_ok) {
        p_set_environment(env_cb);
    }
    report("retro_set_environment", set_env_ok);

    int init_ok = p_init != NULL;
    if (init_ok) {
        p_init();
    }
    report("retro_init", init_ok);

    int info_ok = 0;
    if (p_get_system_info) {
        struct retro_system_info info;
        memset(&info, 0, sizeof(info));
        p_get_system_info(&info);
        info_ok = info.library_name != NULL;
        if (info_ok) {
            fprintf(stderr, "library: %s %s\n", info.library_name,
                    info.library_version ? info.library_version : "");
        }
    }
    report("retro_get_system_info", info_ok);

    int deinit_ok = p_deinit != NULL;
    if (deinit_ok) {
        p_deinit();
    }
    report("retro_deinit", deinit_ok);

    dlclose(handle);
    return 0;
}
