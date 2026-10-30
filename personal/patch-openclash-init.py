#!/usr/bin/env python3
"""Keep restored app preferences while retaining upstream compatibility migrations."""
from pathlib import Path
import sys


def patch(path):
    text = path.read_text()
    if 'PERSONAL_PRESERVE_OPENCLASH' in text:
        return
    text = text.replace('#!/bin/bash\n', """#!/bin/bash
PERSONAL_PRESERVE_OPENCLASH=1
PERSONAL_BOOT_MODE=$(cat /tmp/personal-upgrade/mode 2>/dev/null) || exit 1
case "$PERSONAL_BOOT_MODE" in
factory) PERSONAL_PRESERVE_OPENCLASH=0 ;;
upgrade-preserve)
    [ -e /tmp/personal-upgrade/openclash-preserved ] || PERSONAL_PRESERVE_OPENCLASH=0 ;;
configured) ;;
*) exit 1 ;;
esac
""", 1)
    guards = [
        'if [ -z "$(uci_get_config "dashboard_password")" ]; then',
        'if [ -z "$(uci -q get openclash.@authentication[0])" ]; then',
        'if [ -n "$(uci -q get dhcp.@dnsmasq[0].resolvfile)" ]; then',
    ]
    for old in guards:
        assert text.count(old) == 1, f'OpenClash initializer changed: {old}'
        text = text.replace(old, 'if [ "$PERSONAL_PRESERVE_OPENCLASH" = 0 ] && ' + old[3:])
    old = 'uci -q set openclash.config.core_version="${CORE_ARCH}"'
    assert text.count(old) == 1
    text = text.replace(old, 'if [ "$PERSONAL_PRESERVE_OPENCLASH" = 0 ]; then\n' + old + '\nfi')
    lines = text.splitlines(keepends=True)
    matched = 0
    for i, line in enumerate(lines):
        if line.startswith('if ') and '"$current_kernel" "6.6"' in line:
            lines[i] = 'if [ "$PERSONAL_PRESERVE_OPENCLASH" = 0 ] && ' + line[3:]
            matched += 1
    assert matched == 1
    text = ''.join(lines)
    old = 'if [ -x /etc/init.d/uhttpd ]; then'
    assert text.count(old) == 1
    text = text.replace(old, 'if [ "$(cat /tmp/personal-upgrade/mode 2>/dev/null)" = factory ] && [ -x /etc/init.d/uhttpd ]; then')
    old = 'if [ -d /etc/nginx/conf.d ]; then'
    assert text.count(old) == 1
    text = text.replace(old, 'if [ -d /etc/nginx/conf.d ] && [ ! -e /etc/nginx/conf.d/openclash.conf ]; then')
    path.write_text(text)


if __name__ == '__main__':
    patch(Path(sys.argv[1]))
