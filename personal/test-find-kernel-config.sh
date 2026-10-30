#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/linux-airoha/backports" "$fixture/linux-airoha/linux-6.18.55/nested"
printf '# CONFIG_NET_AIROHA_NPU is not set\n' > "$fixture/linux-airoha/backports/.config"
printf 'CONFIG_NET_AIROHA_NPU=y\n' > "$fixture/linux-airoha/linux-6.18.55/.config"
printf 'wrong config\n' > "$fixture/linux-airoha/linux-6.18.55/nested/.config"
actual=$(bash personal/find-kernel-config.sh "$fixture/linux-airoha")
[[ "$actual" == "$fixture/linux-airoha/linux-6.18.55/.config" ]]
grep -q '^CONFIG_NET_AIROHA_NPU=y$' "$actual"
# The original recursive expression accepts unrelated configs too.
[[ $(find "$fixture/linux-airoha" -path '*/linux-*/.config' | wc -l) -eq 3 ]]
printf 'Kernel config selection regression check passed.\n'
