/*
 * Content-free libretro load test: dlopen (eager binding), then the init sequence.
 * Answers environment calls like a minimal real frontend and prints "CHECK <step> pass|fail".
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
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

/* No-op frontend callbacks, set before retro_init: some cores call them during init. */
static void video_cb(const void *data, unsigned width, unsigned height, size_t pitch) {
    (void)data; (void)width; (void)height; (void)pitch;
}
static void audio_cb(int16_t left, int16_t right) { (void)left; (void)right; }
static size_t audio_batch_cb(const int16_t *data, size_t frames) { (void)data; return frames; }
static void input_poll_cb(void) {}
static int16_t input_state_cb(unsigned port, unsigned device, unsigned index, unsigned id) {
    (void)port; (void)device; (void)index; (void)id;
    return 0;
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
    /* RetroArch reads the system info before init; doing the same separates the two failures. */
    struct retro_system_info info;
    memset(&info, 0, sizeof(info));
    if (get_system_info)
        get_system_info(&info);
    report("retro_get_system_info", info.library_name != NULL);
    if (info.library_name)
        fprintf(stderr, "library: %s %s\n", info.library_name,
                info.library_version ? info.library_version : "");
    if (set_environment)
        set_environment(env_cb);
    report("retro_set_environment", set_environment != NULL);
    void (*set_video)(void (*)(const void *, unsigned, unsigned, size_t)) =
        (void (*)(void (*)(const void *, unsigned, unsigned, size_t)))dlsym(handle, "retro_set_video_refresh");
    void (*set_audio)(void (*)(int16_t, int16_t)) =
        (void (*)(void (*)(int16_t, int16_t)))dlsym(handle, "retro_set_audio_sample");
    void (*set_audio_batch)(size_t (*)(const int16_t *, size_t)) =
        (void (*)(size_t (*)(const int16_t *, size_t)))dlsym(handle, "retro_set_audio_sample_batch");
    void (*set_poll)(void (*)(void)) = (void (*)(void (*)(void)))dlsym(handle, "retro_set_input_poll");
    void (*set_state)(int16_t (*)(unsigned, unsigned, unsigned, unsigned)) =
        (void (*)(int16_t (*)(unsigned, unsigned, unsigned, unsigned)))dlsym(handle, "retro_set_input_state");
    if (set_video) set_video(video_cb);
    if (set_audio) set_audio(audio_cb);
    if (set_audio_batch) set_audio_batch(audio_batch_cb);
    if (set_poll) set_poll(input_poll_cb);
    if (set_state) set_state(input_state_cb);
    if (init)
        init();
    report("retro_init", init != NULL);

    if (deinit)
        deinit();
    report("retro_deinit", deinit != NULL);
    dlclose(handle);
    return 0;
}
