#!/bin/sh
# Runtime state only: factory defaults live in package templates/generators.
personal_capture_boot_context() {
	mkdir -p /tmp/personal-upgrade || return 1
	if [ -e /tmp/personal-config-restore-failed ]; then
		printf '%s\n' restore-failed > /tmp/personal-upgrade/mode
	elif [ -e /tmp/personal-config-restored ]; then
		printf '%s\n' upgrade-preserve > /tmp/personal-upgrade/mode
		if sed 's,^\./,,; s,^/,,' /tmp/personal-restored-files 2>/dev/null | grep -qx 'etc/config/openclash'; then
			touch /tmp/personal-upgrade/openclash-preserved
		fi
	elif [ -s /etc/config/network ] || [ -s /etc/config/wireless ]; then
		printf '%s\n' configured > /tmp/personal-upgrade/mode
	else
		printf '%s\n' factory > /tmp/personal-upgrade/mode
	fi
}

personal_refresh_bundled_core() {
	local source=/rom/etc/openclash/core/clash_meta
	local target=/etc/openclash/core/clash_meta
	[ -f "$source" ] || return 0
	cmp -s "$source" "$target" && return 0
	mkdir -p /etc/openclash/core || return 1
	cp "$source" "$target.personal-new" && chmod 755 "$target.personal-new" &&
		mv -f "$target.personal-new" "$target"
}

personal_migrate_orphan_includes_v1() {
	local state=/etc/personal-firmware/migrations/001-orphan-includes
	local section path sections changed=0
	[ ! -e "$state" ] || return 0
	sections=$(uci -q show firewall) || return 1
	sections=$(printf '%s\n' "$sections" | sed -n 's/^firewall\.\([^.=]*\)=include$/\1/p') || return 1
	for section in $sections; do
		path=$(uci -q get "firewall.$section.path") || continue
		case "$path" in
		/var/run/zerotier-one/_fw4/input.nft|/var/run/zerotier-one/_fw4/srcnat.nft|/var/run/zerotier-one/_fw4/forward.nft)
			[ ! -x /usr/bin/zerotier-one ] && [ ! -x /usr/sbin/zerotier-one ] || continue ;;
		/usr/share/miniupnpd/firewall.include)
			[ ! -x /usr/sbin/miniupnpd ] || continue ;;
		*) continue ;;
		esac
		if [ "$changed" = 0 ]; then
			mkdir -p /etc/personal-firmware/backups/001 || return 1
			chmod 700 /etc/personal-firmware /etc/personal-firmware/backups /etc/personal-firmware/backups/001 || return 1
			if [ ! -e /etc/personal-firmware/backups/001/firewall ]; then
				uci -q export firewall > /etc/personal-firmware/backups/001/firewall || return 1
				chmod 600 /etc/personal-firmware/backups/001/firewall || return 1
			fi
		fi
		uci -q delete "firewall.$section" || return 1
		changed=1
	done
	# Also flush deletions staged by an earlier failed commit before marking done.
	uci -q commit firewall || return 1
	mkdir -p /etc/personal-firmware/migrations || return 1
	chmod 700 /etc/personal-firmware /etc/personal-firmware/migrations || return 1
	printf '1\n' > "$state"
}
