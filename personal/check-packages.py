#!/usr/bin/env python3
"""Reject dependencies that reintroduce removed packages, and missing essentials."""
from pathlib import Path
import sys
p = Path(sys.argv[1])
removed = set(Path('personal/removed-packages.txt').read_text().split())
required = {'luci-app-openclash', 'arp-scan', 'arp-scan-database', 'luci-theme-bootstrap',
            'luci-app-airoha-factory', 'luci-app-airoha-fancontrol', 'luci-app-airoha-npu',
            'luci-app-autoreboot', 'luci-app-firewall', 'luci-app-mlo', 'luci-app-netmode',
            'luci-app-package-manager', 'luci-app-upnp', 'luci-app-watchcat', 'luci-app-wifihistory',
            'ruby', 'ruby-yaml', 'lyaml', 'curl', 'bash', 'jq', 'openssh-client',
            'openssh-keygen', 'openssh-sftp-server', 'iputils-arping', 'wireguard-tools',
            'tcpdump', 'tcping', 'iperf3', 'ip-full', 'i2c-tools', 'pciutils', 'pppoe-discovery'}
if p.name.endswith('.config') or p.name == '.config':
    packages = {s.removeprefix('CONFIG_PACKAGE_').removesuffix('=y')
                for s in p.read_text().splitlines() if s.startswith('CONFIG_PACKAGE_') and s.endswith('=y')}
else:
    packages = {line.split()[0] for line in p.read_text().splitlines() if line.strip()}
assert not (removed & packages), f'Removed packages reintroduced: {sorted(removed & packages)}'
assert required <= packages, f'Missing required packages: {sorted(required - packages)}'
print(f'Personal package policy passed: {p}')
