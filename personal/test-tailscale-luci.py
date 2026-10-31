#!/usr/bin/env python3
"""Exercise real ARM64 UCI/ucode and the app in an isolated image root, offline."""
from pathlib import Path
import json
import os
from runpy import run_path
import shutil
import stat
import subprocess
import sys
import tempfile

helpers = run_path(str(Path(__file__).with_name('test-upgrade.py')))
run, write, fit_images = (helpers[name] for name in ('run', 'write', 'fit_images'))


def main():
    with tempfile.TemporaryDirectory(prefix='tailscale-luci-test-') as tmp:
        tmp = Path(tmp)
        image = tmp / 'root.squashfs'
        for props, data in fit_images(Path(sys.argv[1]).read_bytes()):
            if props['type'] == b'filesystem\0':
                image.write_bytes(data)
        root = tmp / 'root'
        excluded = tmp / 'exclude.txt'
        excluded.write_text('dev\n')
        subprocess.run(['unsquashfs', '-no-progress', '-processors', '2', '-exclude-file', str(excluded),
                        '-d', str(root), str(image)], check=True, stdout=subprocess.DEVNULL)
        if len(sys.argv) == 3:
            # Prebuild test: apply exactly the same patched package files to the old image.
            shutil.copytree(Path(sys.argv[2]) / 'root', root, dirs_exist_ok=True)
        (root / 'dev').mkdir(exist_ok=True)
        for name, major, minor in [('null', 1, 3), ('urandom', 1, 9)]:
            os.mknod(root / 'dev' / name, stat.S_IFCHR | 0o666, os.makedev(major, minor))
        cli = run(root, 'tailscale set --help')
        help_text = cli.stdout + cli.stderr
        assert 'random unused port' in help_text and 'empty string to disable' in help_text
        print('TAILSCALE LUCI PASSED: real CLI documents relay port 0 as random, empty as disabled', flush=True)

        run(root, "uci set tailscale.settings.port=41642; "
                  "uci set tailscale.settings.state_file=/etc/tailscale/user-node.state; "
                  "uci set tailscale.settings.future_option=preserve-me; uci commit tailscale")
        config = (root / 'etc/config/tailscale').read_bytes()
        state = 'fixture-only-node-identity\n'
        write(root, '/etc/tailscale/user-node.state', state)
        write(root, '/etc/config/dhcp', "config dnsmasq\n list server '127.0.0.1#7874'\n")
        write(root, '/usr/sbin/tailscale', '''#!/bin/sh
printf '%s\\n' "$*" >> /tmp/tailscale-calls
case "$1" in
debug) cat /tmp/tailscale-prefs.json ;;
status)
  if [ "$2" = --json ]; then cat /tmp/tailscale-status.json
  else echo 'Log in at https://example.invalid/login'; fi ;;
version) echo '1.104.1' ;;
login|logout|set) exit 0 ;;
*) exit 1 ;;
esac
''')
        (root / 'usr/sbin/tailscale').chmod(0o755)
        write(root, '/usr/bin/pidof', '#!/bin/sh\necho 1234\n')
        (root / 'usr/bin/pidof').chmod(0o755)
        write(root, '/etc/init.d/tailscale', '#!/bin/sh\nprintf "%s\\n" "$*" >> /tmp/native-service-calls\n')
        (root / 'etc/init.d/tailscale').chmod(0o755)
        # Merely adding the app, booting or reloading a legacy config must do nothing.
        service = '. /lib/functions.sh; . /etc/init.d/tailscale-settings; '
        run(root, service + 'start_service; reload_service')
        assert not (root / 'tmp/tailscale-calls').exists()
        assert not (root / 'tmp/native-service-calls').exists()
        assert (root / 'etc/config/tailscale').read_bytes() == config
        assert (root / 'etc/tailscale/user-node.state').read_text() == state
        assert run(root, 'uci get dhcp.@dnsmasq[0].server').stdout.strip() == '127.0.0.1#7874'
        print('TAILSCALE LUCI PASSED: legacy boot/reload preserves state, preferences, daemon and DNS', flush=True)

        prefs = {'RouteAll': True, 'AdvertiseRoutes': ['192.0.2.0/24', '0.0.0.0/0', '::/0'],
                 'ExitNodeIP': '100.64.0.2', 'ExitNodeID': 'fixture-node', 'ExitNodeAllowLANAccess': True,
                 'CorpDNS': True, 'RunSSH': True, 'NoSNAT': True, 'ShieldsUp': True,
                 'RunWebClient': True, 'Hostname': 'fixture-router', 'RelayServerPort': None}
        write(root, '/tmp/tailscale-prefs.json', json.dumps(prefs))
        write(root, '/tmp/tailscale-status.json', json.dumps({'BackendState': 'NeedsLogin', 'Version': '1.104.1', 'Peer': {}}))
        rpc = "let r = loadfile('/usr/share/rpcd/ucode/tailscale.uc')(); "
        def call(method, args=''):
            command = rpc + f'print(sprintf("%J", r.tailscale.{method}.call({args})));'
            return json.loads(run(root, '/usr/bin/ucode -e ' + helpers['shlex'].quote(command)).stdout)
        settings = call('get_settings')
        assert settings['accept_routes'] and settings['advertise_exit_node']
        assert settings['advertise_routes'] == ['192.0.2.0/24']
        assert settings['exit_node'] == '100.64.0.2'
        assert settings['dns_mode'] == 'magicdns' and settings['fw_mode'] == 'nftables'
        assert settings['ssh'] and settings['nosnat'] and settings['service_enabled']
        assert not settings['enable_relay']
        prefs['RelayServerPort'] = 0
        write(root, '/tmp/tailscale-prefs.json', json.dumps(prefs))
        random_port = call('get_settings')
        assert random_port['enable_relay'] and random_port['relay_server_port'] == 0
        assert (root / 'etc/config/tailscale').read_bytes() == config
        assert call('get_status')['status'] == 'logout'
        assert call('do_login', '{ args: { form_data: { loginserver: "", loginserver_authkey: "" } } }')['url'] == 'https://example.invalid/login'
        print('TAILSCALE LUCI PASSED: actual ucode reads CLI prefs, reports login state and returns mock login URL', flush=True)

        run(root, "uci set tailscale.settings.service_enabled=1; uci set tailscale.settings.accept_routes=1; "
                  "uci set tailscale.settings.dns_mode=disabled; uci set tailscale.settings.ssh=1; "
                  "uci add_list tailscale.settings.advertise_routes=192.0.2.0/24; uci commit tailscale")
        before = (root / 'etc/config/tailscale').read_bytes()
        run(root, service + 'start_service')
        calls = (root / 'tmp/tailscale-calls').read_text().splitlines()
        applied = [line for line in calls if line.startswith('set ')]
        assert len(applied) == 1
        for flag in ['--accept-routes=true', '--accept-dns=false', '--ssh=true',
                     '--advertise-routes=192.0.2.0/24', '--relay-server-port=']:
            assert flag in applied[0], applied[0]
        assert '--relay-server-port=0' not in applied[0], 'Zero enables random-port relay; it does not disable it'
        assert (root / 'etc/config/tailscale').read_bytes() == before
        assert (root / 'etc/tailscale/user-node.state').read_text() == state
        run(root, 'uci set tailscale.settings.service_enabled=0; uci commit tailscale')
        run(root, service + 'reload_service')
        assert (root / 'tmp/native-service-calls').read_text().splitlines()[-2:] == ['stop', 'disable']
        assert len([line for line in (root / 'tmp/tailscale-calls').read_text().splitlines() if line.startswith('set ')]) == 1
        print('TAILSCALE LUCI PASSED: explicit managed settings apply; disabling service does not reapply preferences', flush=True)
        print('TAILSCALE LUCI ALL VERIFIED', flush=True)


if __name__ == '__main__':
    main()
