#!/usr/bin/env bash
set -Eeuo pipefail

tool_name=${0##*/}
jobs=${CORE_PIPELINE_JOBS:?CORE_PIPELINE_JOBS is required}
telemetry_root=${CORE_PIPELINE_TELEMETRY_ROOT:?CORE_PIPELINE_TELEMETRY_ROOT is required}

if [[ "$tool_name" == "nproc" ]]; then
  printf '%s\n' "$jobs" >> "$telemetry_root/nproc-observations.txt"
  printf '%s\n' "$jobs"
  exit 0
fi

case "$tool_name" in
  "$CORE_PIPELINE_CC_BASENAME") real_tool=$CORE_PIPELINE_REAL_CC ;;
  "$CORE_PIPELINE_CXX_BASENAME") real_tool=$CORE_PIPELINE_REAL_CXX ;;
  *)
    printf 'unsupported host-build wrapper invocation: %s\n' "$tool_name" >&2
    exit 125
    ;;
esac

unit_kind=other
for argument in "$@"; do
  if [[ "$argument" == "-c" ]]; then
    unit_kind=compile
    break
  fi
done
if [[ "$unit_kind" == "other" ]]; then
  previous=
  for argument in "$@"; do
    if [[ "$argument" == "-shared" || "$argument" == *.so ]]; then
      unit_kind=link
    fi
    if [[ "$previous" == "-o" && "$argument" == *.so ]]; then
      unit_kind=link
    fi
    previous=$argument
  done
fi
if [[ "$unit_kind" == "other" ]]; then
  exec "$real_tool" "$@"
fi

unit_root="$telemetry_root/units"
mkdir -p "$unit_root"
unit_directory=$(mktemp -d "$unit_root/unit.XXXXXXXXXXXX")
printf '%s\n' "$tool_name" > "$unit_directory/compiler.txt"
printf '%s\n' "$unit_kind" > "$unit_directory/kind.txt"
pwd -P > "$unit_directory/cwd.txt"
printf '%s\0' "$@" > "$unit_directory/argv.bin"

set +e
"$CORE_PIPELINE_UNIT_RUNNER" \
  "$unit_directory/metrics.txt" "$real_tool" "$real_tool" "$@"
status=$?
set -e
printf '%s\n' "$status" > "$unit_directory/wrapper-exit-code.txt"
exit "$status"
