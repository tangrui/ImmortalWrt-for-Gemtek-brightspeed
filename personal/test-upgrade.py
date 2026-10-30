#!/usr/bin/env python3
"""Run firmware UCI/ucode in isolated fixture roots (native ARM64 or QEMU binfmt)."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import shlex
import stat
import subprocess
import sys
import tarfile
import tempfile
from runpy import run_path
fit_images = run_path(str(Path(__file__).with_name('verify-image.py')))['fit_images']
patch_openclash = run_path(str(Path(__file__).with_name('patch-openclash-init.py')))['patch']


def run(root, command, check=True):
    p = subprocess.run(['chroot', str(root), '/bin/sh', '-c', command], text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    if check and p.returncode:
        raise AssertionError(f'{command}\n{p.stdout}\n{p.stderr}')
    return p


def write(root, path, content):
    p = root / path.lstrip('/')
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.is_symlink():
        p.unlink()
    p.write_text(content)


def board_fixture(root):
    bands = [('2G', 40), ('5G', 160), ('6G', 320)]
    board = {'model': {'id': 'gemtek,xr1710g'}, 'network': {
        'lan': {'ports': ['lan2', 'lan3', 'lan4'], 'protocol': 'static', 'ipaddr': '192.168.50.1'},
        'wan': {'device': 'wan', 'protocol': 'dhcp'}}, 'wlan': {}}
    for i, (band, width) in enumerate(bands):
        board['wlan'][f'phy{i}'] = {'path': f'platform/test/radio{i}', 'info': {
            'bands': {band: {'max_width': width, 'he': True, 'eht': True}}}}
        write(root, f'/sys/class/ieee80211/phy{i}/macaddress', f'02:00:00:00:00:0{i}\n')
    write(root, '/etc/board.json', json.dumps(board))
    write(root, '/etc/board-base.json', json.dumps(board))
    write(root, '/tmp/sysinfo/board_name', 'gemtek,xr1710g\n')
    (root / 'proc/sys/net/ipv6').mkdir(parents=True, exist_ok=True)


def capture(root):
    run(root, '. /lib/functions/personal-upgrade.sh; personal_capture_boot_context')
    return (root / 'tmp/personal-upgrade/mode').read_text().strip()


def generate(root):
    run(root, 'set -e; CFG=/etc/board-base.json sh /etc/board.d/03_wifi_defaults; /bin/board_detect; /bin/config_generate; '
              'touch /etc/config/wireless; /usr/bin/ucode /lib/wifi/mac80211.uc > /tmp/wifi.batch && '
              'uci batch < /tmp/wifi.batch')


def migrate(root):
    return run(root, 'sh /etc/uci-defaults/99-personal-patch', check=False)


def snapshot(root):
    paths = [p for p in (root / 'etc/config').glob('*') if p.is_file()]
    paths += [root / 'etc/crontabs/root', root / 'etc/dnsmasq.conf', root / 'etc/apk/repositories.d/customfeeds.list',
              root / 'etc/openclash/config/user.yaml', root / 'etc/openclash/custom/user.list',
              root / 'etc/openclash/rule_provider/user.yaml', root / 'etc/dropbear/authorized_keys',
              root / 'etc/tailscale/user-node.state']
    result = {}
    for p in paths:
        if not p.is_file():
            continue
        key = str(p.relative_to(root))
        if p.parent == root / 'etc/config':
            value = run(root, 'uci -q show ' + shlex.quote(p.name), check=False)
            if value.returncode == 0:
                lines = value.stdout.splitlines()
                if p.name == 'firewall':
                    lines = [s for s in lines if not s.startswith(('firewall.old_zt=', 'firewall.old_zt.', 'firewall.old_upnp=', 'firewall.old_upnp.'))]
                result[key] = frozenset(lines)
                continue
        result[key] = p.read_bytes()
    return result


def assert_preserved(before, after, case):
    for path, value in before.items():
        assert path in after, f'User file removed ({case}): {path}'
        if isinstance(value, frozenset):
            assert value <= after[path], f'User settings changed ({case}): {path}: {value - after[path]}'
        else:
            assert value == after[path], f'User file changed ({case}): {path}'



def restore(root, archive, valid=True):
    p = run(root, 'INITRAMFS=1; . /lib/preinit/80_mount_root; cd /; '
                  f'personal_restore_config_archive {archive} plain', check=False)
    assert (p.returncode == 0) == valid, p.stderr


def main():
    image = Path(sys.argv[1]).resolve()
    overlay = '--overlay' in sys.argv[2:]
    with tempfile.TemporaryDirectory(prefix='upgrade-contract-') as temp:
        temp = Path(temp)
        fs_image = temp / 'root.squashfs'
        for props, payload in fit_images(image.read_bytes()):
            if props['type'] == b'filesystem\0':
                fs_image.write_bytes(payload)
        base = temp / 'base'
        exclude = temp / 'exclude.txt'
        exclude.write_text('dev\n')
        subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-exclude-file', str(exclude), '-d', str(base), str(fs_image)],
                       check=True, stdout=subprocess.DEVNULL)
        if overlay:
            for path in Path('files').rglob('*'):
                if path.is_file():
                    target = base / path.relative_to('files')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
            paths = {
                'package/emortal/default-settings/files/99-default-settings': 'etc/uci-defaults/99-default-settings',
                'package/emortal/default-settings/files/99-default-settings-chinese': 'etc/uci-defaults/99-default-settings-chinese',
                'package/base-files/files/bin/config_generate': 'bin/config_generate',
                'package/base-files/files/lib/preinit/80_mount_root': 'lib/preinit/80_mount_root',
                'package/base-files/files/lib/preinit/81_personal_config_state': 'lib/preinit/81_personal_config_state',
                'package/base-files/files/sbin/sysupgrade': 'sbin/sysupgrade',
                'package/network/config/wifi-scripts/files/lib/wifi/mac80211.uc': 'lib/wifi/mac80211.uc',
                'package/network/config/airoha-an7581-mt7996-board/files/etc/board.d/03_wifi_defaults': 'etc/board.d/03_wifi_defaults',
                'target/linux/airoha/an7581/base-files/etc/uci-defaults/99-crontab': 'etc/uci-defaults/99-crontab',
                'package/emortal/cpufreq/files/cpufreq-xr1710g.config': 'etc/config/cpufreq',
            }
            for source, target in paths.items():
                shutil.copy2(source, base / target)
            patch_openclash(base / 'etc/uci-defaults/luci-openclash')
            for name in ['03_wireless', '11-xr1710g-cpufreq-defaults', '18-xr1710g-firewall-defaults',
                         '22_airoha-network-migrate-v4', '98-watchcat-defaults']:
                (base / 'etc/uci-defaults' / name).unlink(missing_ok=True)
            write(base, '/etc/config/tailscale', "config settings 'settings'\n option log_stderr '1'\n option log_stdout '1'\n option port '41641'\n option state_file '/etc/tailscale/tailscaled.state'\n option fw_mode 'nftables'\n")
            p = base / 'etc/config/luci'
            p.write_text(p.read_text().replace("'/luci-static/bootstrap'", "'/luci-static/bootstrap-dark'"))
        assert not list((base / 'etc/tailscale').glob('*.state')), 'Identity must not be embedded in firmware'
        new_core = (base / 'etc/openclash/core/clash_meta').read_bytes()
        rom = base / 'rom/etc/openclash/core'
        rom.mkdir(parents=True, exist_ok=True)
        (rom / 'clash_meta').write_bytes(new_core)
        for name in ['03_wireless', '11-xr1710g-cpufreq-defaults', '18-xr1710g-firewall-defaults',
                     '22_airoha-network-migrate-v4', '98-watchcat-defaults']:
            assert not (base / 'etc/uci-defaults' / name).exists(), name
        # Baseline without any persistent state, including upgrades from the author's firmware.
        for case in ['factory', 'preserve', 'new-app', 'orphans', 'restore-failure', 'commit-failure']:
            root = temp / case
            shutil.copytree(base, root, symlinks=True)
            (root / 'dev').mkdir(exist_ok=True)
            os.mknod(root / 'dev/null', stat.S_IFCHR | 0o666, os.makedev(1, 3))
            os.mknod(root / 'dev/urandom', stat.S_IFCHR | 0o666, os.makedev(1, 9))
            print(f'TESTING UPGRADE CONTRACT: {case}', flush=True)
            board_fixture(root)
            if case == 'factory':
                if not overlay:
                    assert '1.104.1' in run(root, '/usr/sbin/tailscale version').stdout
                for pkg in ['network', 'system', 'dhcp', 'wireless']:
                    (root / 'etc/config' / pkg).unlink(missing_ok=True)
                assert run(root, 'uci get tailscale.settings.state_file').stdout.strip() == '/etc/tailscale/tailscaled.state'
                assert run(root, 'uci get tailscale.settings.fw_mode').stdout.strip() == 'nftables'
                assert capture(root) == 'factory'
                generate(root)
                assert run(root, 'uci get network.wan6.auto').stdout.strip() == '0'
                assert run(root, 'uci get dhcp.lan.ra').stdout.strip() == 'disabled'
                assert run(root, 'uci get wireless.radio1.htmode').stdout.strip() == 'EHT160'
                assert run(root, 'uci get wireless.radio2.disabled').stdout.strip() == '1'
                assert run(root, 'uci get wireless.default_radio2.disabled').stdout.strip() == '1'
                assert run(root, 'uci get wireless.radio0.country').stdout.strip() == 'CN'
                run(root, 'sh /etc/uci-defaults/99-default-settings; sh /etc/uci-defaults/99-default-settings-chinese; sh /etc/uci-defaults/30_luci-theme-bootstrap; bash /etc/uci-defaults/luci-openclash')
                assert run(root, 'uci get openclash.config.enable').stdout.strip() == '0'
                assert migrate(root).returncode == 0
                before = snapshot(root)
                generate(root)
                assert migrate(root).returncode == 0
                assert before == snapshot(root), 'Factory initialization not idempotent'
            else:
                write(root, '/etc/config/network', "config interface 'wan'\n option proto 'pppoe'\n option username 'fixture-user'\n option password 'fixture-not-a-secret'\n option device 'wan.42'\n option sendclientid 'none'\nconfig interface 'wan6'\n option proto 'dhcpv6'\n option auto '1'\nconfig device 'br_lan'\n option name 'br-lan'\n option type 'bridge'\n list ports 'lan2'\n list ports 'lan4'\n option vlan_filtering '1'\n")
                write(root, '/etc/config/system', "config system\n option hostname 'MyRouter'\n option timezone 'UTC0'\n option zonename 'Etc/UTC'\nconfig timeserver 'ntp'\n list server 'pool.ntp.org'\n")
                write(root, '/etc/config/dhcp', "config dnsmasq\n option noresolv '1'\n list server '127.0.0.1#7874'\nconfig dhcp 'lan'\n option ra 'server'\n option dhcpv6 'server'\n")
                wireless = ''
                for i in range(3):
                    wireless += f"config wifi-device 'myradio{i}'\n option type 'mac80211'\n option path 'platform/test/radio{i}'\n option country 'US'\n option channel '149'\n option htmode 'HE80'\n option disabled '0'\nconfig wifi-iface 'myssid{i}'\n option device 'myradio{i}'\n option ssid 'UserWifi'\n option key 'fixture-wifi-key'\n"
                write(root, '/etc/config/wireless', wireless)
                write(root, '/etc/config/luci', "config core 'main'\n option mediaurlbase '/luci-static/my-theme'\n option lang 'en'\n")
                write(root, '/etc/config/openclash', "config openclash 'config'\n option enable '1'\n option dashboard_password 'fixture-password'\n option config_path '/etc/openclash/config/user.yaml'\n option core_version 'linux-arm64'\n option disable_quic_go_gso '0'\n option default_resolvfile '/tmp/user-dns'\n")
                write(root, '/etc/config/tailscale', "config settings 'settings'\n option port '41642'\n option state_file '/etc/tailscale/user-node.state'\n option fw_mode 'nftables'\n option log_stdout '0'\n option log_stderr '0'\n option future_option 'preserve-me'\n")
                write(root, '/etc/tailscale/user-node.state', '{"fixture_node_identity":"not-a-real-key","advertise_routes":["192.168.50.0/24"]}\n')
                write(root, '/etc/config/uhttpd', "config uhttpd 'main'\n option script_timeout '180'\n option max_requests '8'\n")
                write(root, '/etc/config/cpufreq', "config settings 'cpufreq'\n option governor0 'schedutil'\n option maxfreq0 '1300000'\nconfig settings 'global'\n option set '0'\n")
                write(root, '/etc/config/firewall', "config defaults\n option fullcone '1'\n option flow_offloading '0'\n option flow_offloading_hw '0'\nconfig include 'user_rule'\n option path '/etc/user-rule.sh'\n")
                for path, content in {'/etc/crontabs/root': '', '/etc/dnsmasq.conf': 'log-facility=/tmp/user-dns.log\ncache-size=2048\n', '/etc/apk/repositories.d/customfeeds.list': 'https://example.invalid/user/packages.adb\n',
                                      '/etc/openclash/config/user.yaml': 'mode: rule\n', '/etc/openclash/custom/user.list': '# custom fixture\n',
                                      '/etc/openclash/rule_provider/user.yaml': 'payload: []\n', '/etc/dropbear/authorized_keys': 'fixture-key\n'}.items():
                    write(root, path, content)
                if case in ['orphans', 'commit-failure']:
                    with (root / 'etc/config/firewall').open('a') as f:
                        f.write("config include 'old_zt'\n option path '/var/run/zerotier-one/_fw4/input.nft'\nconfig include 'old_upnp'\n option path '/usr/share/miniupnpd/firewall.include'\n")
                    # The prebuild fixture image still contains UPnP; the new image must not.
                    (root / 'usr/sbin/miniupnpd').unlink(missing_ok=True)
                with tarfile.open(root / 'tmp/restore.tar', 'w') as archive:
                    for name in snapshot(root):
                        if case == 'new-app' and (name == 'etc/config/openclash' or name.startswith('etc/openclash/')):
                            continue
                        archive.add(root / name, arcname=name)
                if case == 'restore-failure':
                    write(root, '/tmp/broken.tar', 'not a tar archive')
                    restore(root, '/tmp/broken.tar', valid=False)
                    assert capture(root) == 'restore-failed'
                    before = snapshot(root)
                    assert run(root, 'bash /etc/uci-defaults/luci-openclash', check=False).returncode != 0
                    assert migrate(root).returncode != 0
                    assert not (root / 'etc/personal-firmware/migrations/001-orphan-includes').exists()
                    assert before == snapshot(root)
                else:
                    if case == 'new-app':
                        shutil.copy2(base / 'etc/config/openclash', root / 'etc/config/openclash')
                    restore(root, '/tmp/restore.tar')
                    assert capture(root) == 'upgrade-preserve'
                    before = snapshot(root)
                    if case == 'new-app':
                        assert not (root / 'tmp/personal-upgrade/openclash-preserved').exists()
                        before.pop('etc/config/openclash')
                    generate(root)
                    run(root, 'sh /etc/uci-defaults/99-default-settings; sh /etc/uci-defaults/99-default-settings-chinese; sh /etc/uci-defaults/30_luci-theme-bootstrap; bash /etc/uci-defaults/luci-openclash')
                    run(root, 'sh /etc/uci-defaults/99-crontab')
                    if case == 'commit-failure':
                        (root / 'sbin/uci').rename(root / 'sbin/uci-real')
                        write(root, '/sbin/uci', '#!/bin/sh\nfor arg in "$@"; do [ "$arg" != commit ] || exit 1; done\nexec /sbin/uci-real "$@"\n')
                        (root / 'sbin/uci').chmod(0o755)
                        assert migrate(root).returncode != 0
                        assert not (root / 'etc/personal-firmware/migrations/001-orphan-includes').exists()
                        (root / 'sbin/uci').unlink()
                        (root / 'sbin/uci-real').rename(root / 'sbin/uci')
                        assert migrate(root).returncode == 0, 'Commit failure did not recover'
                        run(root, 'uci -q revert firewall', check=False)
                        assert run(root, 'uci -q get firewall.old_zt', check=False).returncode != 0
                        assert run(root, 'uci -q get firewall.old_upnp', check=False).returncode != 0
                    else:
                        write(root, '/etc/openclash/core/clash_meta', 'old executable fixture')
                        assert migrate(root).returncode == 0
                        assert (root / 'etc/openclash/core/clash_meta').read_bytes() == new_core
                        after = snapshot(root)
                        if case == 'orphans':
                            assert run(root, 'uci -q get firewall.old_zt', check=False).returncode != 0
                            assert run(root, 'uci -q get firewall.old_upnp', check=False).returncode != 0
                            assert (root / 'etc/personal-firmware/backups/001/firewall').is_file()
                        assert_preserved(before, after, case)
                        if case == 'new-app':
                            assert run(root, 'uci get openclash.config.enable').stdout.strip() == '0'
                            assert run(root, 'uci get openclash.config.core_version').stdout.strip() == 'linux-arm64'
                        if case == 'preserve':
                            backup = run(root, '/sbin/sysupgrade -l').stdout.splitlines()
                            for name in ['/etc/config/tailscale', '/etc/tailscale/user-node.state', '/etc/config/network', '/etc/config/wireless', '/etc/config/dhcp', '/etc/config/firewall', '/etc/config/cpufreq', '/etc/config/uhttpd', '/etc/dropbear/authorized_keys', '/etc/personal-firmware/migrations/001-orphan-includes', '/etc/config/openclash', '/etc/openclash/config/user.yaml', '/etc/openclash/custom/user.list', '/etc/openclash/rule_provider/user.yaml', '/etc/crontabs/root', '/etc/apk/repositories.d/customfeeds.list']:
                                assert name in backup, f'User data missing from backup: {name}'
                            assert not any(name.startswith('/etc/openclash/core/') for name in backup)
                            assert '/etc/apk/repositories.d/distfeeds.list' not in backup
                        stable = snapshot(root)
                        assert migrate(root).returncode == 0
                        assert stable == snapshot(root), 'Migration repeated edits'
                        (root / 'tmp/personal-config-restored').unlink()
                        assert capture(root) == 'configured'
                        assert migrate(root).returncode == 0
                        assert stable == snapshot(root), 'Ordinary reboot changed settings'
            print(f'UPGRADE CONTRACT PASSED: {case}', flush=True)
            shutil.rmtree(root)
        print('Factory defaults, preserved upgrades, empty cron, orphan cleanup, retries and failures verified.', flush=True)


if __name__ == '__main__':
    main()
