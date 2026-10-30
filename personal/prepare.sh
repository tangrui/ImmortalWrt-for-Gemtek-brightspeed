#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
commit=e553e82e01c697aefbe1555261a503f425e00ccd
if [[ ! -d /tmp/personal-openclash/.git ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/vernesong/OpenClash.git /tmp/personal-openclash
fi
git -C /tmp/personal-openclash checkout --detach "$commit"
mkdir -p package/personal
cp -a /tmp/personal-openclash/luci-app-openclash package/personal/
mkdir -p files/etc/openclash/core
curl --fail --location --retry 3 -o /tmp/mihomo.gz https://github.com/MetaCubeX/mihomo/releases/download/v1.19.33/mihomo-linux-arm64-v1.19.33.gz
echo 'ba408b317080ee265c46cb923a50018c1b82cbd708551cdd46a1e3e307396187  /tmp/mihomo.gz' | sha256sum -c -
gzip -dc /tmp/mihomo.gz > files/etc/openclash/core/clash_meta
chmod 755 files/etc/openclash/core/clash_meta
# Source feeds needed for build are not necessarily usable binary repositories.
# Prevent custom feed indexes from being published into the runtime config.
