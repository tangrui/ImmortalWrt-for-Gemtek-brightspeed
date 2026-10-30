# XR1710G Reset 按键验证

2026-10-30 只读核查：当前仍为作者 `20261016-1a34e17c`，`/proc/modules` 未见 gpio_button_hotplug，dmesg 仍有 `.gnu.linkonce.this_module section size must match`。本次没有修改按键处理器、加载模块、操作按键或重启。

## 先区分三件事

- 上电早期按 Reset 进入 U-Boot 恢复网页：由引导程序处理，用户此前已验证。
- Linux 正常运行时的按下/松开事件：依赖当前按键驱动和事件分发。
- Linux 按键对应动作：当前脚本短按会重启；松开时 SEEN >= 5 且 overlay 存在会恢复出厂并重启。不要用长按清空配置来做验证。

引导恢复网页正常不代表 Linux 按键正常。模块没加载也不代表实体按钮损坏。

## 第一步：只读检查驱动

在完全启动、SSH 正常后执行：

```sh
cat /etc/openwrt_release
grep '^gpio_button_hotplug ' /proc/modules
ls -l /sys/bus/platform/drivers/gpio-keys/
dmesg | grep -E 'gpio.button|gpio_button|struct module|section size' | tail -20
```

当前原版已明确加载失败，无需靠实体长按再次证明。如果新固件仍未加载且有同类错误，先停止按键测试并追查模块，不强制加载。
检查日志应结合本次启动和当前加载状态，不能仅因历史日志里有错误就认定当前仍失败。

新固件构建会离线比较 GPIO 与 MT7996 模块的 vermagic 和 `.gnu.linkonce.this_module` 大小。它针对已知 ABI 错误，不能替代实际加载和实体按键验证。

## 第二步：先临时阻断软件动作，再观察事件

这是需要临时修改路由器处理器的步骤，目前尚未执行。

1. 先确认是正常运行期而非上电/恢复窗口，并保存当前配置备份，确认 SSH 可用。
2. 检查 `/etc/hotplug.json` 和 `/etc/hotplug.d/button/`，确保没有其他会重启/清空配置的处理链。此次只读检查中，标准 button 分发指向 `/etc/rc.button/%BUTTON%`，未列出额外 button 脚本；实际测试前应重新核对。
3. 把 `/etc/rc.button/reset` 的原文件备份到本次专用 `/root/reset-button-test.*` 目录，记下完整路径。不能只备份到重启即消失的 `/tmp`，也不要覆盖此前的备份。
4. 将 Reset 处理器临时改为仅记录日志并返回成功：

```sh
#!/bin/sh
logger -t reset-probe "BUTTON=${BUTTON:-?} ACTION=${ACTION:-?} SEEN=${SEEN:-?}"
exit 0
```

5. 先验证日志处理器内容已经安装，再在另一个 SSH 窗口监测：

```sh
logread -f -e reset-probe
```

6. **只短按一次并立即松开**，观察是否出现 `BUTTON=reset ACTION=pressed` 和 `ACTION=released`。不测试长按，不在重启/上电过程中按，不按住等待。
7. 确认按钮完全松开、不再操作后，恢复原处理器，并逐字节比较恢复结果与备份一致。

不要用固定倒计时自动恢复处理器：若恢复时按钮仍按住，随后松开可能重新触发原来的恢复出厂逻辑。
测试期间不要重启或断电；若测试中断，先确认实体按钮已松开，再通过持久备份恢复。日志模式只阻断该软件处理器，不能保证阻断硬件层的复位线路，因此始终只做短按。

## 如何判定

- 驱动未加载：先解决模块问题，不做实体长按测试。
- 驱动已加载，日志有 pressed/released：Linux 事件链已验证；不等于已执行重启或恢复出厂。
- 驱动加载但无事件：继续查设备树 GPIO、驱动绑定、引脚和其他处理链，不盲目重复长按。
- 如需验证短按重启动作，恢复原处理器后，在接受短时断网的维护时间单独测试，用新的启动标识确认实际重启。
- 不建议为了验证长按动作而清空现有配置；这与验证按键事件不是同一个目标。
