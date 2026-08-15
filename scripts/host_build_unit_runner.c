#define _GNU_SOURCE

#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t child_pid = -1;

static void forward_signal(int signal_number) {
    pid_t target = (pid_t)child_pid;
    if (target > 0) {
        (void)kill(target, signal_number);
    }
}

static int install_forwarder(int signal_number) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = forward_signal;
    sigemptyset(&action.sa_mask);
    return sigaction(signal_number, &action, NULL);
}

static void restore_default_signal(int signal_number) {
    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = SIG_DFL;
    sigemptyset(&action.sa_mask);
    if (sigaction(signal_number, &action, NULL) != 0) {
        _exit(125);
    }
}

static uint64_t monotonic_nanoseconds(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) {
        perror("clock_gettime");
        exit(125);
    }
    return (uint64_t)value.tv_sec * UINT64_C(1000000000) +
           (uint64_t)value.tv_nsec;
}

static uint64_t timeval_microseconds(struct timeval value) {
    return (uint64_t)value.tv_sec * UINT64_C(1000000) +
           (uint64_t)value.tv_usec;
}

static int write_metrics(
    const char *path,
    uint64_t started_ns,
    uint64_t finished_ns,
    const struct rusage *usage,
    int wait_status
) {
    FILE *output = fopen(path, "wx");
    if (output == NULL) {
        perror("fopen metrics");
        return 125;
    }
    int exit_code = 0;
    int signal_number = 0;
    if (WIFEXITED(wait_status)) {
        exit_code = WEXITSTATUS(wait_status);
    } else if (WIFSIGNALED(wait_status)) {
        signal_number = WTERMSIG(wait_status);
    }
    int failed = fprintf(
        output,
        "started_monotonic_ns=%" PRIu64 "\n"
        "finished_monotonic_ns=%" PRIu64 "\n"
        "elapsed_ns=%" PRIu64 "\n"
        "user_cpu_us=%" PRIu64 "\n"
        "system_cpu_us=%" PRIu64 "\n"
        "max_rss_kib=%ld\n"
        "exit_code=%d\n"
        "signal=%d\n",
        started_ns,
        finished_ns,
        finished_ns - started_ns,
        timeval_microseconds(usage->ru_utime),
        timeval_microseconds(usage->ru_stime),
        usage->ru_maxrss,
        exit_code,
        signal_number
    ) < 0;
    if (fflush(output) != 0 || fsync(fileno(output)) != 0 || fclose(output) != 0) {
        perror("write metrics");
        return 125;
    }
    return failed ? 125 : 0;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--clock") == 0) {
        printf("%" PRIu64 "\n", monotonic_nanoseconds());
        return fflush(stdout) == 0 ? 0 : 125;
    }
    if (argc < 4) {
        fprintf(
            stderr,
            "usage: %s METRICS_PATH EXECUTABLE ARGV0 [ARG ...]\n",
            argv[0]
        );
        return 125;
    }

    if (
        install_forwarder(SIGINT) != 0 ||
        install_forwarder(SIGTERM) != 0 ||
        install_forwarder(SIGHUP) != 0
    ) {
        perror("sigaction");
        return 125;
    }

    uint64_t started_ns = monotonic_nanoseconds();
    pid_t child = fork();
    if (child < 0) {
        perror("fork");
        return 125;
    }
    if (child == 0) {
        restore_default_signal(SIGINT);
        restore_default_signal(SIGTERM);
        restore_default_signal(SIGHUP);
        execv(argv[2], &argv[3]);
        perror("execv");
        _exit(127);
    }
    child_pid = child;

    struct rusage usage;
    memset(&usage, 0, sizeof(usage));
    int wait_status = 0;
    while (wait4(child, &wait_status, 0, &usage) < 0) {
        if (errno != EINTR) {
            perror("wait4");
            return 125;
        }
    }
    child_pid = -1;
    uint64_t finished_ns = monotonic_nanoseconds();
    int metrics_status = write_metrics(
        argv[1], started_ns, finished_ns, &usage, wait_status
    );
    if (metrics_status != 0) {
        return metrics_status;
    }
    if (WIFEXITED(wait_status)) {
        return WEXITSTATUS(wait_status);
    }
    if (WIFSIGNALED(wait_status)) {
        return 128 + WTERMSIG(wait_status);
    }
    return 125;
}
