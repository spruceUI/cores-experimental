/*
 * Content-free libretro load test: dlopen (eager binding), then the init sequence.
 * Answers environment calls like a minimal real frontend and prints "CHECK <step> pass|fail".
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#define RETRO_API_VERSION 1
#define ENV_EXPERIMENTAL 0x10000
#define ENV_GET_SYSTEM_DIRECTORY 9
#define ENV_SET_PIXEL_FORMAT 10
#define ENV_GET_LIBRETRO_PATH 19
#define ENV_GET_LOG_INTERFACE 27
#define ENV_GET_CONTENT_DIRECTORY 30
#define ENV_GET_SAVE_DIRECTORY 31

struct retro_system_info {
    const char *library_name;
    const char *library_version;
    const char *valid_extensions;
    bool need_fullpath;
    bool block_extract;
};

struct retro_log_callback {
    void (*log)(int level, const char *fmt, ...);
};

static const char *core_path;

static void log_cb(int level, const char *fmt, ...) {
    va_list args;
    (void)level;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);
}

static bool env_cb(unsigned cmd, void *data) {
    if (!data)
        return false;
    switch (cmd & ~ENV_EXPERIMENTAL) {
    case ENV_GET_SYSTEM_DIRECTORY:
    case ENV_GET_CONTENT_DIRECTORY:
    case ENV_GET_SAVE_DIRECTORY:
        *(const char **)data = "/tmp";
        return true;
    case ENV_GET_LIBRETRO_PATH:
        *(const char **)data = core_path;
        return true;
    case ENV_SET_PIXEL_FORMAT:
        return true;
    case ENV_GET_LOG_INTERFACE:
        ((struct retro_log_callback *)data)->log = log_cb;
        return true;
    default:
        return false;
    }
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
    core_path = argv[1];
    void *handle = dlopen(core_path, RTLD_NOW | RTLD_LOCAL);
    report("dlopen", handle != NULL);
    if (!handle) {
        fprintf(stderr, "dlopen: %s\n", dlerror());
        return 1;
    }

    unsigned (*api_version)(void) = (unsigned (*)(void))dlsym(handle, "retro_api_version");
    void (*set_environment)(bool (*)(unsigned, void *)) =
        (void (*)(bool (*)(unsigned, void *)))dlsym(handle, "retro_set_environment");
    void (*init)(void) = (void (*)(void))dlsym(handle, "retro_init");
    void (*get_system_info)(struct retro_system_info *) =
        (void (*)(struct retro_system_info *))dlsym(handle, "retro_get_system_info");
    void (*deinit)(void) = (void (*)(void))dlsym(handle, "retro_deinit");

    report("retro_api_version", api_version && api_version() == RETRO_API_VERSION);
    if (set_environment)
        set_environment(env_cb);
    report("retro_set_environment", set_environment != NULL);
    if (init)
        init();
    report("retro_init", init != NULL);

    struct retro_system_info info;
    memset(&info, 0, sizeof(info));
    if (get_system_info)
        get_system_info(&info);
    report("retro_get_system_info", info.library_name != NULL);
    if (info.library_name)
        fprintf(stderr, "library: %s %s\n", info.library_name,
                info.library_version ? info.library_version : "");

    if (deinit)
        deinit();
    report("retro_deinit", deinit != NULL);
    dlclose(handle);
    return 0;
}
