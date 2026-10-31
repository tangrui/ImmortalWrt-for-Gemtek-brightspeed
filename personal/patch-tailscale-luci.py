#!/usr/bin/env python3
"""Adapt the pinned LuCI app without taking ownership of existing CLI settings."""
from pathlib import Path
import sys

MARKER = 'personal-tailscale-preservation-v1'


def replace_once(text, old, new):
    assert text.count(old) == 1, f'Pinned Tailscale LuCI source changed: {old[:90]}'
    return text.replace(old, new)


def patch(root):
    root = Path(root)
    init = root / 'root/etc/init.d/tailscale-settings'
    text = init.read_text()
    if MARKER not in text:
        text = replace_once(text, '#!/bin/sh /etc/rc.common\n', '#!/bin/sh /etc/rc.common\n# ' + MARKER + '\n')
        text = replace_once(text, 'killall tailscaled 2>/dev/null', 'killall tailscaled 2>/dev/null || true')
        text = replace_once(text, 'start_service() {\n\tapply_settings\n}', '''start_service() {
	# The native daemon/state owns preferences until the user saves this UI.
	uci -q get tailscale.settings.service_enabled >/dev/null || return 0
	handle_service_state
}''')
        text = replace_once(text, 'reload_service() {\n\thandle_service_state\n}', '''reload_service() {
	uci -q get tailscale.settings.service_enabled >/dev/null || return 0
	handle_service_state
}''')
        init.write_text(text)

    backend = root / 'root/usr/share/rpcd/ucode/tailscale.uc'
    text = backend.read_text()
    if MARKER not in text:
        start = text.index('methods.get_settings = {')
        end = text.index('methods.do_login = {', start)
        text = text[:start] + '''// personal-tailscale-preservation-v1
methods.get_settings = {
	call: function() {
		uci.load('tailscale');
		let result = exec('tailscale debug prefs');
		let prefs = {};
		try {
			if (result.code == 0) prefs = json(join('', result.stdout)) || {};
		} catch (e) { /* Keep the page usable before the daemon is available. */ }
		let routes = prefs.AdvertiseRoutes || [];
		let advertise_exit = index(routes, '0.0.0.0/0') >= 0 || index(routes, '::/0') >= 0;
		let mode = uci.get('tailscale', 'settings', 'fw_mode') || 'nftables';
		let old_dns = uci.get('tailscale', 'settings', 'disable_magic_dns');
		let dns = uci.get('tailscale', 'settings', 'dns_mode');
		if (dns == null)
			dns = old_dns != null ? (old_dns == '1' ? 'disabled' : 'magicdns') :
				(prefs.CorpDNS ? 'magicdns' : 'disabled');
		return {
			service_enabled: exec('pidof tailscaled').code == 0,
			accept_routes: !!prefs.RouteAll,
			advertise_exit_node: advertise_exit,
			advertise_routes: filter(routes, route => route != '0.0.0.0/0' && route != '::/0'),
			exit_node: prefs.ExitNodeIP || prefs.ExitNodeID || '',
			exit_node_allow_lan_access: !!prefs.ExitNodeAllowLANAccess,
			shields_up: !!prefs.ShieldsUp,
			ssh: !!prefs.RunSSH,
			runwebclient: !!prefs.RunWebClient,
			nosnat: !!prefs.NoSNAT,
			hostname: prefs.Hostname || '',
			dns_mode: dns,
			fw_mode: split(mode, ' ')[0],
			enable_relay: prefs.RelayServerPort != null,
			relay_server_port: prefs.RelayServerPort ?? 40000
		};
	}
};

''' + text[end:]
        backend.write_text(text)

    view = root / 'htdocs/luci-static/resources/view/tailscale.js'
    text = view.read_text()
    if MARKER not in text:
        start = text.index('\tload() {')
        end = text.index('\trender ([status', start)
        text = text[:start] + '''	// personal-tailscale-preservation-v1
	load() {
		return Promise.all([
			L.resolveDefault(callGetStatus(), { status: '', peers: [] }),
			L.resolveDefault(callGetSettings(), {}),
			L.resolveDefault(callGetSubroutes(), { routes: [] }),
			uci.load('tailscale')
		]).then(function([status, settings, subroutes]) {
			if (uci.get('tailscale', 'settings') == null)
				uci.add('tailscale', 'settings', 'settings');
			const values = {
				service_enabled: settings.service_enabled ? '1' : '0',
				fw_mode: settings.fw_mode || 'nftables',
				dns_mode: settings.dns_mode || 'disabled',
				advertise_routes: settings.advertise_routes || [],
				exit_node: settings.exit_node || '',
				hostname: settings.hostname || '',
				relay_server_port: settings.relay_server_port ?? 40000
			};
			for (const name of ['accept_routes', 'advertise_exit_node', 'exit_node_allow_lan_access',
				'ssh', 'shields_up', 'runwebclient', 'nosnat', 'enable_relay'])
				values[name] = settings[name] ? '1' : '0';
			for (const [name, value] of Object.entries(values))
				if (uci.get('tailscale', 'settings', name) == null)
					uci.set('tailscale', 'settings', name, value);
			// These are browser-local values. Only explicit Save & Apply persists them.
			return [status, settings, subroutes];
		});
	},

''' + text[end:]
        text = replace_once(text, '''doc.body.innerHTML =
						'<h2>' + _('Error') + '</h2>' +
						'<p>' + _('Failed to get login URL. You may close this tab.') + '</p>';''',
                            "loginWindow.document.body.textContent = _('Failed to get login URL. You may close this tab.');")
        view.write_text(text)


if __name__ == '__main__':
    patch(sys.argv[1])
