#!/bin/bash
# Installed as /tmp/wrap/gcc and g++: $WRAP_CROSS<name> with $WRAP_FLAGS last (-O0 calls get $WRAP_KEEP_FLAGS), and as
# Ubuntu's GCC does: -fPIE unless PIC is asked for, -pie on executable links, --as-needed ahead of a link's libraries.
tool=${0##*/}
case " $* " in
    *" -c "*|*" -E "*|*" -S "*) kind=compile ;;
    *" -shared "*) kind=shared ;;
    *) kind=exe ;;
esac
pie=""
if [ "$kind" != shared ]; then
    case " $* " in *" -fPIC "*|*" -fpic "*) ;; *) pie="-fPIE" ;; esac
    [ "$kind" = exe ] && pie="$pie -pie"
fi
link=""
first=""
if [ "$kind" != compile ]; then
    link="$WRAP_LINK"
    first="-Wl,--as-needed"
fi
case " $* " in *" -O0 "*) opt="$WRAP_KEEP_FLAGS" ;; *) opt="$WRAP_FLAGS" ;; esac
[ -z "${WRAP_LOG:-}" ] || printf '%s\n' "$first $* $WRAP_SYSFLAGS $opt $pie $link" >> "$WRAP_LOG"
exec "$WRAP_CROSS$tool" $first "$@" $WRAP_SYSFLAGS $opt $pie $link
