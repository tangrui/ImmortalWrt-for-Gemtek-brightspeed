# XR1710G personal patch

基线为作者最新非预发布标签 `20261016-04cc62e`，源码提交
`04cc62e8928308598cf2e88bddee37ede658b814`。这是作者快照的发布版，
不是 ImmortalWrt 长期维护稳定分支，也不声称复现作者资产的全部构建输入。

软件源固定到发布时刻之前的最后提交，具体见 `feeds.conf.default`。
`app_airoha` 只用于编译硬件管理界面，运行时禁用它的二进制源。
保留标准软件源；快照二进制源会继续变化，内核模块应使用本次构建产物。

`removed-packages.txt` 覆盖已确认卸载项，并排除当前设备清理后清单中已不存在的
usteer、mesh-conf、airoha-recovery、IPTV 服务及 xray-core。
保留无线驱动、Mesh 认证组件、硬件管理、UPnP、Watchcat、定时重启、无线历史和扫描工具。
构建在 defconfig 和最终 manifest 两阶段检查删除项及必备软件，依赖重新带入会直接失败。

预置 OpenClash `v0.48.002`（提交 `e553e82e01c697aefbe1555261a503f425e00ccd`）
以及 Mihomo `v1.19.33` ARM64 核心，下载时验证 SHA-256。
默认关闭 OpenClash，用户导入自己的订阅/配置后开启。
不包含个人订阅、密码、SSH 密钥或设备备份。

配置：关闭 fullcone/fullcone6 与模块自动加载，修正 firewall4 关闭状态下的探测；
暂停 WAN6 及 LAN IPv6 通告，保留协议栈；删除旧 ZeroTier 防火墙 include；使用 Bootstrap 深色主题。
未针对 GPIO 按键模块、无线扫描告警做未经验证的修复。
内核和全部模块由同一个任务从源码构建，仍须刷机后验证硬件运行状态。

推送 `patch-xr1710g` 自动构建，也可以手动运行 Build Personal Patch Firmware。
固件文件名带 `20261016-patch-<commit>`；产物含 manifest、配置、软件源版本和校验和。
只有手动选择 release/prerelease 才发布 Release。

## 后续作者升级

1. 查询作者 Releases，选择非预发布标签，创建基于该标签的新分支。
2. 将此个人定制提交 cherry-pick 到新分支；冲突必须逐项处理。
3. 按新发布时间更新五个 feed 固定提交，核对 OpenClash 与核心稳定版本及下载摘要。
4. 更新 workflow 中的基线 SHA、版本前缀和自动触发分支。
5. 构建必须通过配置和 manifest 检查，再下载带 patch 标记的 sysupgrade.itb。

不会自动合并作者滚动 master，避免未经检查的内核/驱动更新混入已选基线。
升级保留设置时，99-personal-patch 会重新应用上述策略；已有无线、PPPoE 等个人设置不写入源码。
