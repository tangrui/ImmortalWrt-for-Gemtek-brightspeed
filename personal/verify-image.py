#!/usr/bin/env python3
"""Verify downloaded ITBs, their actual NPU kernel code and personal rootfs policy."""
from pathlib import Path
import gzip
import hashlib
import re
import struct
import subprocess
import sys
import tempfile
import zlib

CORE_SHA256 = '8c73570d9a5f388bc2f58eee0b347ccfab84fb3cf1a0f8f2cf5eac7005fbcdc0'


def fit_images(blob):
    magic, total, pos, strings, *_ = struct.unpack_from('>10I', blob)
    assert magic == 0xd00dfeed, 'Not a FIT image'
    stack, nodes = [], {}
    while True:
        token = struct.unpack_from('>I', blob, pos)[0]
        pos += 4
        if token == 1:
            end = blob.index(0, pos)
            stack.append(blob[pos:end].decode())
            pos = (end + 4) & ~3
        elif token == 2:
            stack.pop()
        elif token == 3:
            size, nameoff = struct.unpack_from('>II', blob, pos)
            pos += 8
            end = blob.index(0, strings + nameoff)
            name = blob[strings + nameoff:end].decode()
            nodes.setdefault('/'.join(stack), {})[name] = blob[pos:pos + size]
            pos = (pos + size + 3) & ~3
        elif token == 9:
            break
        else:
            assert token == 4, f'Unexpected FDT token: {token}'
    for path, props in nodes.items():
        if not path.startswith('/images/') or 'type' not in props:
            continue
        if 'data' in props:
            data = props['data']
        else:
            start = int.from_bytes(props.get('data-position', b'\0'), 'big')
            if not start:
                start = ((total + 3) & ~3) + int.from_bytes(props['data-offset'], 'big')
            size = int.from_bytes(props['data-size'], 'big')
            data = blob[start:start + size]
            assert len(data) == size, 'Truncated FIT payload'
        hashes = [v for k, v in nodes.items() if k.startswith(path + '/hash-')]
        assert hashes, f'Missing FIT hash: {path}'
        for item in hashes:
            algo = item['algo'].rstrip(b'\0').decode()
            actual = struct.pack('>I', zlib.crc32(data)) if algo == 'crc32' else hashlib.new(algo, data).digest()
            assert actual == item['value'], f'FIT payload hash mismatch: {path}'
        yield props, data


def module_metadata(path):
    blob = path.read_bytes()
    assert blob[:6] == b'\x7fELF\x02\x01', f'Expected AArch64 ELF module: {path}'
    assert struct.unpack_from('<H', blob, 18)[0] == 183, 'Wrong module architecture'
    table = struct.unpack_from('<Q', blob, 40)[0]
    entry, count, names_idx = struct.unpack_from('<HHH', blob, 58)
    name_header = table + names_idx * entry
    name_offset, name_size = struct.unpack_from('<QQ', blob, name_header + 24)
    names = blob[name_offset:name_offset + name_size]
    values = {}
    for i in range(count):
        header = table + i * entry
        name_pos = struct.unpack_from('<I', blob, header)[0]
        name = names[name_pos:names.find(b'\0', name_pos)].decode()
        offset, size = struct.unpack_from('<QQ', blob, header + 24)
        if name == '.gnu.linkonce.this_module':
            values['module_struct_size'] = size
        if name == '.modinfo':
            for field in blob[offset:offset + size].split(b'\0'):
                if field.startswith(b'vermagic='):
                    values['vermagic'] = field.split(b'=', 1)[1].decode()
    assert values.get('module_struct_size') and values.get('vermagic'), f'Missing ABI metadata: {path}'
    return values


def verify_button_module(root):
    modules = root / 'lib/modules'
    buttons = list(modules.rglob('gpio-button-hotplug.ko'))
    references = list(modules.rglob('mt7996e.ko'))
    assert len(buttons) == len(references) == 1, 'Expected GPIO and MT7996 modules'
    button, reference = module_metadata(buttons[0]), module_metadata(references[0])
    assert button == reference, f'GPIO module ABI differs from WiFi driver: {button} vs {reference}'
    print(f'GPIO MODULE ABI VERIFIED: {button}', flush=True)


def verify_rootfs(data):
    with tempfile.TemporaryDirectory(prefix='verify-xr1710g-') as tmp:
        image, root = Path(tmp) / 'root.squashfs', Path(tmp) / 'root'
        image.write_bytes(data)
        # Extract inspected files only; a normal CI user cannot create /dev/console.
        subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-d', str(root), str(image),
                        'etc', 'usr/lib/lua/luci/controller/openclash.lua', 'usr/share/ucode/fw4.uc',
                        'lib/functions/personal-upgrade.sh', 'lib/preinit/80_mount_root',
                        'lib/preinit/81_personal_config_state', 'bin/config_generate',
                        'lib/wifi/mac80211.uc', 'lib/upgrade/keep.d/personal-firmware', 'sbin/sysupgrade',
                        'lib/modules', 'usr/sbin/tailscale', 'usr/sbin/tailscaled',
                        'usr/share/rpcd', 'usr/share/luci', 'www/luci-static/resources/view/tailscale.js',
                        'usr/lib/lua/luci/i18n/tailscale-community.zh-cn.lmo'],
                       check=True, stdout=subprocess.DEVNULL)
        verify_button_module(root)
        assert (root / 'usr/sbin/tailscaled').is_file(), 'Tailscale daemon missing'
        assert (root / 'usr/sbin/tailscale').is_file(), 'Tailscale CLI missing'
        tsconf = (root / 'etc/config/tailscale').read_text()
        assert '/etc/tailscale/tailscaled.state' in tsconf
        assert 'nftables' in tsconf
        assert 'service_enabled' not in tsconf, 'Do not take ownership before explicit GUI save'
        menu = (root / 'usr/share/luci/menu.d/luci-app-tailscale-community.json').read_text()
        assert 'admin/vpn/tailscale' in menu
        assert (root / 'usr/lib/lua/luci/i18n/tailscale-community.zh-cn.lmo').is_file()
        for path in ['etc/init.d/tailscale-settings', 'usr/share/rpcd/ucode/tailscale.uc']:
            assert 'personal-tailscale-preservation-v1' in (root / path).read_text(), path
        # LuCI minifies JS and strips comments. Exercise the installed view instead.
        subprocess.run(['node', 'personal/test-tailscale-view.cjs',
                        str(root / 'www/luci-static/resources/view/tailscale.js')], check=True)
        assert not list((root / 'etc/tailscale').glob('*.state')), 'Tailscale identity embedded in firmware'
        core = root / 'etc/openclash/core/clash_meta'
        assert hashlib.sha256(core.read_bytes()).hexdigest() == CORE_SHA256, 'Unexpected Mihomo core'
        assert core.stat().st_mode & 0o111, 'Core is not executable'
        assert (root / 'usr/lib/lua/luci/controller/openclash.lua').is_file(), 'OpenClash UI missing'
        for name in ['watchcat', 'miniupnpd']:
            assert not (root / 'etc/init.d' / name).exists(), f'Removed service remains: {name}'
        assert 'PERSONAL_PRESERVE_OPENCLASH' in (root / 'etc/uci-defaults/luci-openclash').read_text()
        defaults = root / 'etc/uci-defaults/99-personal-patch'
        assert defaults.read_bytes() == Path('files/etc/uci-defaults/99-personal-patch').read_bytes()
        assert '(defs.fullcone || defs.fullcone6) && !nft_try_fullcone()' in (root / 'usr/share/ucode/fw4.uc').read_text()
        firewall = (root / 'etc/config/firewall').read_text()
        assert re.search(r'option\s+fullcone\s+0', firewall)
        assert re.search(r'option\s+fullcone6\s+0', firewall)
        autoload = root / 'etc/modules.d/nft-fullcone'
        assert not autoload.exists() or not any(s.strip() == 'nft_fullcone' for s in autoload.read_text().splitlines())
        assert "ucidef_set_country 'CN'" in (root / 'etc/board.d/03_wifi_defaults').read_text()
        for name in ['03_wireless', '11-xr1710g-cpufreq-defaults', '18-xr1710g-firewall-defaults',
                     '22_airoha-network-migrate-v4', '98-watchcat-defaults']:
            assert not (root / 'etc/uci-defaults' / name).exists(), f'Preference reset remains: {name}'
        for source, target in {
            'package/emortal/default-settings/files/99-default-settings': 'etc/uci-defaults/99-default-settings',
            'package/emortal/default-settings/files/99-default-settings-chinese': 'etc/uci-defaults/99-default-settings-chinese',
            'files/lib/functions/personal-upgrade.sh': 'lib/functions/personal-upgrade.sh',
            'package/base-files/files/lib/preinit/80_mount_root': 'lib/preinit/80_mount_root',
            'package/base-files/files/lib/preinit/81_personal_config_state': 'lib/preinit/81_personal_config_state',
            'package/base-files/files/bin/config_generate': 'bin/config_generate',
            'package/base-files/files/sbin/sysupgrade': 'sbin/sysupgrade',
            'package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc': 'lib/wifi/mac80211.uc',
            'files/lib/upgrade/keep.d/personal-firmware': 'lib/upgrade/keep.d/personal-firmware',
        }.items():
            assert (root / target).read_bytes() == Path(source).read_bytes(), target
        assert "'/luci-static/bootstrap-dark'" in (root / 'etc/config/luci').read_text()
        assert "option governor0 'performance'" in (root / 'etc/config/cpufreq').read_text()
        cron = (root / 'etc/crontabs/root').read_text()
        assert re.search(r'^30 21 \* \* \* ', cron, re.M)
        assert re.search(r'^0 7 \* \* \* ', cron, re.M)
        assert re.search(r"DISTRIB_RELEASE='20261016-custom-[0-9a-f]{8}'", (root / 'etc/openwrt_release').read_text())
        feeds = (root / 'etc/apk/repositories.d/distfeeds.list').read_text()
        assert 'https://mirrors.vsean.net/openwrt/snapshots' in feeds
        assert not any('/app_airoha/' in line and not line.startswith('#') for line in feeds.splitlines())


def main():
    directory = Path(sys.argv[1]).resolve()
    config = [Path(sys.argv[2]).resolve()] if len(sys.argv) > 2 else list(directory.rglob('.config'))
    assert len(config) == 1, 'Expected one build configuration'
    manifest = list(directory.rglob('*.manifest'))
    assert len(manifest) == 1, 'Expected one package manifest'
    subprocess.run([sys.executable, 'personal/check-packages.py', str(config[0])], check=True)
    subprocess.run([sys.executable, 'personal/check-packages.py', str(manifest[0])], check=True)
    assert re.search(r'^luci-app-openclash\s+-\s+0\.48\.002(?:\b|[-~])', manifest[0].read_text(), re.M)
    assert re.search(r'^tailscale\s+-\s+1\.104\.1(?:\b|[-~])', manifest[0].read_text(), re.M)
    subprocess.run(['bash', 'scripts/check-gemtek-profile-isolation.sh', '--config', str(config[0]),
                    '--manifest', str(manifest[0])], check=True)
    images = list(directory.rglob('*.itb'))
    assert len(images) == 2, 'Expected XR1710G and XR1710G-UBI images'
    subprocess.run(['bash', 'scripts/check-firmware-artifacts.sh', '--config', str(config[0]),
                    '--directory', str(images[0].parent)], check=True)
    checksums = dict(line.split(None, 1)[::-1] for line in (images[0].parent / 'sha256sums').read_text().splitlines())
    checksums = {name.lstrip('*'): digest for name, digest in checksums.items()}
    for image in images:
        blob = image.read_bytes()
        assert hashlib.sha256(blob).hexdigest() == checksums[image.name], f'SHA256 mismatch: {image}'
        seen = set()
        for props, data in fit_images(blob):
            kind = props['type'].rstrip(b'\0').decode()
            if kind == 'kernel':
                kernel = gzip.decompress(data) if props.get('compression') == b'gzip\0' else data
                # This symbol is in the actual built-in NPU driver, not a build-dir config.
                assert b'airoha_npu_probe' in kernel, 'Built-in NPU driver missing from kernel'
                seen.add(kind)
            elif kind == 'filesystem':
                verify_rootfs(data)
                seen.add(kind)
        assert seen == {'kernel', 'filesystem'}, 'Missing kernel or root filesystem'
        print(f'IMAGE VERIFIED: {image.name} SHA256={checksums[image.name]}', flush=True)
    print('Both images passed integrity, NPU, package and personal configuration checks.', flush=True)


if __name__ == '__main__':
    main()
