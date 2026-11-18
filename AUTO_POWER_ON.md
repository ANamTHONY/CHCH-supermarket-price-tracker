# 定时开机方案：待完成验证

**2026-11-17：用户要求每周二、三、四 10:30 正常关机。已准备 `tools/weekly_shutdown_task.xml`，后台 S4U 任务注册被系统拒绝，需要在管理员窗口导入。计划任务名 `PriceTracker-WeeklyShutdown`；首个未来触发为 2026-11-18 10:30。无错过时间补跑，不唤醒已关机的机器，不强制关闭应用。11 月 13—15 日的临时关机任务已过期，与此新任务独立。**

**2026-11-12 修正：每日任务和正式后台 XML 均只保留每日 09:15 触发。已删除登录/开机补跑触发器，并关闭 StartWhenAvailable；因此下午开机或登录不会自动采集。下文提及的启动后补跑是旧配置，已取消。**

用户于 2026-11-12 选择改用定时开机。当前每日 09:15 任务仍保留，但已添加 `--no-hibernate`，不会再主动休眠。未启用自动关机，避免尚未设置定时开机时次日无法采集。

## 第一步：无人登录的后台采集验证

普通权限注册 S4U 后台任务被 Windows 返回“拒绝访问”，需要一次管理员操作。在管理员 PowerShell 中执行：

```powershell
& 'D:\python\price-tracker\tools\install_boot_probe.ps1'
```

该操作仅创建并启动一个无日程的后台测试任务 `PriceTracker-BootProbe`，以 Yan 用户的批处理会话运行，不保存 Windows 密码。测试检查已有 Databricks 目录读取权限，使用无界面 Chrome，分别读取三品牌一家门店的五个商品。不写生产数据，不关机、不休眠。

结果见 `data/boot_probe/result.json` 和 `probe.log`。三家通过后仍需验证正式采集及关机后启动周期。若后台模式失败，不能宣称免登录无人值守已经可用；应先诊断，不擅自设置自动登录。

## 第二步：主板定时开机

主板：MSI MPG Z790I EDGE WIFI（MS-7E03）。需用户重启进入 BIOS，实际选项以机器界面为准：

- `Settings > Advanced > Wake Up Event Setup`
- `Wake Up Event By` 选择 BIOS（如果有该选项）。
- `Resume By RTC Alarm` 启用。
- 设置每天 09:10，给 09:15 采集预留五分钟。先核对 BIOS 当前时间，避免误用 UTC 或错误时钟。
- 若关机后无法定时启动，检查 `Settings > Advanced > Power Management Setup > ErP Ready`；MSI 官方 FAQ 说明应将该设置禁用。
- 保持插座、电源供电，不能关闭电源插排或电源背部开关。

参考：https://latam.msi.com/faq/10982 、https://uk.msi.com/faq/9987

## 第三步：切换正式任务

只有后台采集与 BIOS 定时开机验证成功后，再切换正式任务为启动后可运行的后台模式，并添加空闲保护下的自动关机。届时需验证正在使用电脑时不会被打断。当前仍为交互式会话日常任务，不代表已经完成免登录的开机采集部署。

### 2026-11-12 验证进展

S4U Session 0 实测：Databricks 目录访问成功；普通 Chrome 模式三品牌各五件商品均成功，无生产写入。无界面 Chrome 模式未通过，因此正式后台入口明确使用普通 Chrome，不依赖桌面用户登录。正式入口 dry-run 也已在 Session 0 通过；54 项测试通过。

`tools/boot_daily_task.xml` 已生成，尚未导入替换每日任务。BIOS 设置完成后，可在管理员 PowerShell 使用原生程序导入，不修改脚本执行策略：

```powershell
schtasks.exe /Create /TN "PriceTracker-Daily" /XML "D:\python\price-tracker\tools\boot_daily_task.xml" /F
```

正式任务每天 09:15，并在启动后延迟两分钟检查（09:15 以前不会采集）；后台运行无需自动登录。自动关机仍由 `data/boot_power_enabled.json` 中的 `bios_wake_verified=true` 单独控制，在实际验证 BIOS 从关机定时启动前不启用。

关机条件：当天完整采集及云端入库已确认、BIOS 定时开机已验证、启动及结束均没有任何已登录的桌面会话。登录桌面（包括已锁定或断开的会话）或查询会话状态失败，均跳过关机。两分钟等待内出现用户会话会取消关机；不强制关闭程序。完整 28 店后台采集和从关机启动的周期尚未实测。
