#!/usr/bin/env node
// Exercise the real view loader: importing CLI prefs must be browser-local only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const source = fs.readFileSync(process.argv[2], 'utf8');

async function check(existing, prefs) {
  const config = structuredClone(existing);
  const original = structuredClone(existing);
  let saves = 0;
  const rpc = { declare: ({ method }) => async () => ({
    get_status: { status: 'running', peers: [] },
    get_settings: prefs,
    get_subroutes: { routes: ['192.0.2.0/24'] }
  })[method] };
  const uci = {
    load: async () => {},
    get: (_package, _section, key) => key == null ? 'settings' : config[key] ?? null,
    add: () => { throw new Error('Native settings section must be retained'); },
    set: (_package, _section, key, value) => { config[key] = value; },
    unset: () => { throw new Error('Opening the view must not delete settings'); },
    save: () => { saves++; throw new Error('Opening the view must not persist changes'); }
  };
  const view = new Function('view', 'form', 'rpc', 'ui', 'uci', 'widgets', 'L', '_', source)(
    { extend: x => x }, {}, rpc, {}, uci, {},
    { resolveDefault: (value, fallback) => Promise.resolve(value).catch(() => fallback) }, x => x);
  await view.load();
  assert.equal(saves, 0);
  for (const [key, value] of Object.entries(original)) assert.deepEqual(config[key], value);
  return config;
}

(async () => {
  const prefs = { service_enabled: true, accept_routes: true, dns_mode: 'magicdns',
    advertise_exit_node: true, advertise_routes: ['192.0.2.0/24'], exit_node: '100.64.0.2',
    ssh: true, nosnat: true, shields_up: true, runwebclient: true,
    exit_node_allow_lan_access: true, hostname: 'fixture-router', enable_relay: false };
  const imported = await check({ port: '41642', state_file: '/etc/tailscale/user-node.state',
    fw_mode: 'nftables', future_option: 'preserve-me' }, prefs);
  assert.equal(imported.accept_routes, '1');
  assert.equal(imported.dns_mode, 'magicdns');
  assert.deepEqual(imported.advertise_routes, ['192.0.2.0/24']);
  assert.equal(imported.exit_node, '100.64.0.2');
  assert.equal(imported.service_enabled, '1');
  const existing = await check({ service_enabled: '0', dns_mode: 'openwrt_forward',
    accept_routes: '0', advertise_routes: ['198.51.100.0/24'], custom_login_url: 'https://example.invalid' }, prefs);
  assert.equal(existing.service_enabled, '0');
  const randomRelay = await check({}, { ...prefs, enable_relay: true, relay_server_port: 0 });
  assert.equal(randomRelay.relay_server_port, 0);
  assert.equal(randomRelay.enable_relay, '1');
  await check({ fw_mode: 'nftables' }, {});
  console.log('TAILSCALE VIEW VERIFIED: import CLI preferences, preserve existing UCI, no save on page load');
})().catch(error => { console.error(error); process.exitCode = 1; });
