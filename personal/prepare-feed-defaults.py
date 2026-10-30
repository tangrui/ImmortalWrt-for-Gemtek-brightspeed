#!/usr/bin/env python3
"""Change factory data only. A restored /etc/config/luci overrides this template."""
from pathlib import Path
p = Path('feeds/luci/modules/luci-base/root/etc/config/luci')
s = p.read_text()
old = "option mediaurlbase '/luci-static/bootstrap'"
new = "option mediaurlbase '/luci-static/bootstrap-dark'"
assert old in s or new in s, 'LuCI default template changed; review before building'
p.write_text(s.replace(old, new))
