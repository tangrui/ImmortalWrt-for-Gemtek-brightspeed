#!/usr/bin/env bash
# A recursive '*linux-*/.config' also matches backports and other child trees.
set -euo pipefail
shopt -s nullglob
configs=("${1:?kernel build directory required}"/linux-[0-9]*/.config)
if (( ${#configs[@]} != 1 )); then
  printf 'Expected one Linux root config, found %s\n' "${#configs[@]}" >&2
  exit 1
fi
printf '%s\n' "${configs[0]}"
