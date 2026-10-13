#!/bin/sh
# Installed as /tmp/wrap/gcc and g++: $WRAP_CROSS<name> with the sysroot and $WRAP_FLAGS after the Makefile's flags
# (GCC honours the last -O; a call pinned at -O0 gets $WRAP_KEEP_FLAGS), and $WRAP_SHARED_LINK on -shared links.
tool=${0##*/}
link=""
case " $* " in *" -shared "*) link="$WRAP_SHARED_LINK" ;; esac
case " $* " in *" -O0 "*) opt="$WRAP_KEEP_FLAGS" ;; *) opt="$WRAP_FLAGS" ;; esac
[ -z "${WRAP_LOG:-}" ] || printf '%s\n' "$* --sysroot=$WRAP_SYSROOT $opt $link" >> "$WRAP_LOG"
exec "$WRAP_CROSS$tool" "$@" --sysroot="$WRAP_SYSROOT" $opt $link
