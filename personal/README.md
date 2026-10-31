# XR1710G custom firmware

基线为作者最新非预发布标签 `20261016-04cc62e`，源码提交
`04cc62e8928308598cf2e88bddee37ede658b814`。这是作者快照的发布版，
不是 ImmortalWrt 长期维护稳定分支，也不声称复现作者资产的全部构建输入。

软件源固定到发布时刻之前的最后提交，具体见 `feeds.conf.default`。
`app_airoha` 只用于编译硬件管理界面，运行时禁用它的二进制源。
保留与当前设备相同的 mirrors.vsean.net 标准软件源；快照二进制源会继续变化，内核模块应使用本次构建产物。

`removed-packages.txt` 覆盖已确认卸载项，并排除当前设备清理后清单中已不存在的
usteer、mesh-conf、airoha-recovery、IPTV 服务及 xray-core。
tcping 单独从 fw876/helloworld 提交 `1f0849ec0668e59865c30ab7d89bb2139c270d00`
引入源码到 `package/personal/tcping`，不启用该 feed；保留现有 PPPoE 发现工具。
保留无线驱动、Mesh 认证组件、硬件管理、定时重启、无线历史和扫描工具。
移除原生 WireGuard 的 kmod-wireguard、wireguard-tools、luci-proto-wireguard、rpcd-mod-wireguard，保留 TUN 支持。
已排除 Watchcat、UPnP 应用、语言包、miniupnpd 后端和相关独立客户端库。
它们没有独立 feed，来自共享 packages/luci；共享源保留，app_airoha 二进制源通过构建配置直接注释。
修正隐藏板级配置包在多机型构建下变为 m 的默认值，确保其为 y。
固定 feeds 内存在循环依赖的未选中 HomeProxy、IPsec 服务、Passwall 和 Squeezelite 构建入口已移除。
构建在 defconfig 和最终 manifest 两阶段检查删除项及必备软件，依赖重新带入会直接失败。

预置 OpenClash `v0.48.002`（提交 `e553e82e01c697aefbe1555261a503f425e00ccd`）
以及 Mihomo `v1.19.33` ARM64 核心，下载时验证 SHA-256。
全新安装默认关闭 OpenClash，用户导入自己的订阅/配置后开启；保留设置升级保持原启用状态。
不包含个人订阅、密码、SSH 密钥或设备备份。

无线国家设为 CN，停用 6GHz，保留 2.4GHz 自动信道 HE20、5GHz 信道 36 EHT160。
默认 LED 计划为 21:30 关灯、07:00 开灯。

出厂默认：关闭 fullcone/fullcone6 与模块自动加载，修正 firewall4 关闭状态下的探测；
暂停 WAN6 及 LAN IPv6 通告，保留协议栈；使用 Bootstrap 深色主题。
这些偏好在模板/生成器中初始化，保留设置升级时已有取值优先，不会关闭用户后来启用的 IPv6、OpenClash 或 6GHz。
未针对 GPIO 按键模块、无线扫描告警做未经验证的修复。
内核和全部模块由同一个任务从源码构建，仍须刷机后验证硬件运行状态。

推送现有 `patch-xr1710g` 分支自动构建，也可以手动选择该分支运行 Build Custom Firmware。
新固件文件名、系统版本、构建附件与 Release 标签使用 `custom`，例如 `20261016-custom-<commit>`；产物含 manifest、配置、软件源版本和校验和。
分支名与内部 `99-personal-patch` 脚本保留，避免把改名误当成新的配置迁移；历史产物名称不回写。
只有手动选择 release/prerelease 才发布 Release。

## 后续作者升级

1. 查询作者 Releases，选择非预发布标签，创建基于该标签的新分支。
2. 将此个人定制提交 cherry-pick 到新分支；冲突必须逐项处理。
3. 按新发布时间更新五个 feed 固定提交，核对 OpenClash 与核心稳定版本及下载摘要。
4. 更新 workflow 中的基线 SHA、版本前缀和自动触发分支。
5. 构建必须通过配置和 manifest 检查，再下载带 custom 标记的 sysupgrade.itb。

不会自动合并作者滚动 master，避免未经检查的内核/驱动更新混入已选基线。
升级保留设置时不重新应用出厂偏好；PPPoE、无线密码、OpenClash 订阅等个人数据不写入源码。

## 产物复核与检查脚本

作者原工作流使用递归 `find ... -path '*/linux-*/.config'`，该模式会匹配构建目录中
backports 等其他组件的 `.config`。现在仅接受 Linux 源码目录根部的唯一配置，并将其保存为
`kernel.config`，防止用其他组件配置误判 NPU 缺失。附带回归检查覆盖多个 `.config` 的情况。

`verify-image.py` 直接检查两个 ITB 的 SHA-256、FIT 内部散列、内核内置 NPU 驱动符号，
解包根文件系统核对 OpenClash、Mihomo、全锥形修正、无线、LED 和个人首次启动策略。
完整构建结束后自动运行这些检查。已有编译产物也可在同一个工作流中填写 `verify_run_id`
重新下载复核，不重复编译；留空则完整构建。复核保留原镜像版本与散列，不改包或重打镜像。

## 升级保留契约（本轮修订）

- `80_mount_root` 记录真实配置恢复结果，`81_personal_config_state` 在配置生成前记录启动类型；不依赖旧固件没有的私有标记判断是否保留配置。
- 网络/IPv6 默认值只在 `config_generate` 创建配置时设置。无线参数放在 board.json，mac80211 先跳过已有无线设备，只为新设备生成默认值。
- 删除重复重设无线、流量卸载、CPU 调频的初始化脚本。CPU 及主题改为出厂模板；保留已有配置时由恢复文件覆盖模板。
- 本基线不变更当前接口命名；取消无版本约束的旧端口自动改写，保留用户 VLAN、桥接、DHCP 客户标识。未来涉及实际接口/格式变化时必须另写有明确来源条件的兼容迁移。
- 空 crontab 表示用户禁用了计划，不重新填入 LED 计划。上游语言、时区、NTP 和 DNS 日志默认设置也仅限出厂初始化，即使旧配置没有初始化标记也不覆盖。
- `99-personal-patch` 不写偏好，只更新固件自带 Mihomo 程序，按版本清理确认为孤立的 ZeroTier/旧 UPnP include。迁移前保存防火墙副本，提交成功后才登记完成；失败保留重试能力。
- `/etc/config/openclash`、订阅、配置、规则、providers、用户计划与自定义软件源列入保留范围。默认备份和完整 overlay 备份都排除旧核心程序及自动生成的 distfeeds.list；软件源随新固件重新生成，用户 customfeeds.list 保留。
- Mihomo 核心属于固件程序，升级时更新为固件预置版本；自行替换的核心二进制不作为用户配置保留。程序与内核模块不通过配置备份继承。
- OpenClash 初始化保留恢复的启用状态、密码、核心架构、DNS 原始设置和 GSO 选择；不强制改动现有网页服务超时。新加入 OpenClash 时仍允许初始化缺失配置。
- 被删除应用的历史配置可随用户备份保留，程序和启动服务不会因此重新安装；不为精简软件而擦除个人配置。

构建后 `test-upgrade.py` 使用镜像内真实 ARM64 UCI、ucode，在隔离根目录模拟：
全新初始化、从作者固件保留升级、新增应用、空计划、孤立 include、普通重启、重复迁移、恢复失败和提交失败后重试。
这些测试不访问路由器，不代替真实设备刷机与硬件验证。兼容的 sysupgrade 保留设置才能恢复配置；不保留设置和恢复出厂会重新使用默认值。

## Tailscale

预装固定 packages feed 中的 Tailscale `1.104.1`，同一个包提供 `tailscale` 和 `tailscaled`。
不依赖原生 WireGuard 软件包，使用自身 WireGuard 用户态实现；`kmod-tun`、CA 证书和 nftables 基础保留。
遵循该包的原生启动方式：守护进程随系统启动，出厂未登录，没有预置授权密钥、节点身份、出口节点或子网公告。
预装同一固定 LuCI feed 中的 `luci-app-tailscale-community` 与 `luci-i18n-tailscale-community-zh-cn`，无需新增软件源。
入口为“VPN → Tailscale”，可查看状态、获取登录链接、管理路由与服务；也可继续通过 SSH 使用原生 CLI。
路由、DNS、子网公告等由用户选择，不自动替用户设置；真正授权需要用户完成账号登录，构建测试不接入真实 tailnet。

`patch-tailscale-luci.py` 对固定版本作有边界的兼容处理：

- 没有保存过 LuCI 管理设置时，界面辅助服务在启动及配置重载时不执行 `tailscale set`，保留已有命令行偏好和节点身份。
- 界面从 `tailscale debug prefs` 读取当前运行配置，仅在浏览器内补齐缺失表单字段；打开页面不保存、不改 DNS。用户明确“保存并应用”之后才由界面管理对应设置。
- 已有 UCI 字段优先，保留自定义守护进程端口、状态文件路径和未知字段。节点状态仍由原生 daemon 使用，界面不重写身份文件。
- Peer Relay 保留原生语义：空参数禁用，端口 0 表示随机端口，读取时区分空值与 0。
- 修正获取登录链接失败时引用未定义窗口对象的问题。
- 停止服务操作在 daemon 已退出时仍成功返回，避免重复停止产生误报。

`test-tailscale-view.cjs` 验证真实前端加载逻辑不持久化设置；`test-tailscale-luci.py` 使用实际镜像中的 ARM64 UCI/ucode 与离线模拟 CLI 验证后台、登录状态、显式保存及服务开关。

显式保留 `/etc/config/tailscale` 和 `/etc/tailscale/`，含机器身份、登录状态和路由偏好所在状态文件。
默认 state_file 为 `/etc/tailscale/tailscaled.state`；若自行改到目录以外，应将自定义路径加入备份。
升级回归覆盖 Tailscale 的自定义端口、状态文件路径、未知配置字段及模拟设备身份的保留；不接入真实 tailnet。

## Reset 验证

见 [安全验证步骤](RESET_BUTTON_TEST.md)。当前原作者版本的 GPIO 模块与 MT7996 模块虽然 vermagic 相同，
但 `.gnu.linkonce.this_module` 分别为 704 与 1216 字节；离线检查会拒绝这份已知不一致镜像。
此前干净构建 `d9fcac54` 的二者均为 1216 字节。本次和后续构建继续校验模块一致性。
2026-10-31 已在实际设备的 `3fe10781` 版本验证驱动加载、按下/松开、短按保留配置重启、长按清空用户配置；没有更改 Reset 的正常逻辑。
后续构建继续离线校验一致性，不据此替代每次新内核/驱动更新后的硬件验证。

本轮保持 2.4 GHz 自动选信道。固定信道曾使热点提前约 8 秒，但未证明信道 6 的日常无线表现最优，因此不把排查参数写成出厂默认值。
