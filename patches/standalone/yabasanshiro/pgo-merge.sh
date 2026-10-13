#!/bin/sh
# pgo-merge.sh GCOV_TOOL TAR...: sum profile tars (rooted at build/, the paths the counters carry) pairwise in the
# order given with the toolchain's own gcov-tool, then unpack the sum over /, into the build tree.
set -eu
tool=$1
shift
i=0
for tar in "$@"; do
    mkdir -p "/tmp/prof/$i" && tar -xf "$tar" -C "/tmp/prof/$i"
    i=$((i + 1))
done
merged=/tmp/prof/0
for j in $(seq 1 $((i - 1))); do
    (cd /tmp/prof && "$tool" merge -o "/tmp/prof/m$j" "$merged" "/tmp/prof/$j")
    merged=/tmp/prof/m$j
done
cp -a "$merged/build" /
echo "pgo-merge: $(find "$merged/build" -name '*.gcda' | wc -l) gcda from $#"
