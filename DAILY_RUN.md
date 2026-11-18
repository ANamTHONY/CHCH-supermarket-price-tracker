# 每日运行（2026-11-03 更新）

本机已配置每日 09:15 自动唤醒采集任务 `PriceTracker-Daily`；成功且无人操作时自动休眠。使用条件、暂停方法及日志位置见 `LOCAL_AUTOMATION.md`。首次休眠唤醒的完整流程仍需实测。

商品总数允许每天及采集途中变化。Foodstuffs 和 Woolworths 按实际分页读取到末页、按 SKU 去重，等商品卡片内容稳定后再解析。网页显示总数或范围不一致只记 `collection_warnings`，不按固定数量、昨日数量或最初显示的总数判失败。分页循环、重复整页、明确缺失下一页控件、加载超时、商品身份解析失败及门店不匹配仍会拦截；数量告警不等于实时变化期间获得了原子快照。

Woolworths 还会等待正常商品的公开售价就绪，会员价不能替代公开价，SAVE 折扣金额不能替代售价。价格未加载会等待并有限刷新/分类重试，仍失败则不上传半加载门店；明确缺货且源页面未提供售价的商品可保留空值，但会记录告警。此价格就绪检查与商品总数检查独立。

## 本地：采集、上传，然后触发云端 Job

双击 `run_daily.cmd`。三家超市正常启用；Woolworths 门店串行，页面导航至少间隔 10 秒，遇到 Access Denied 停止该品牌。

默认不连接 SQL Warehouse，不在本地执行入表和转换。完成的门店 CSV 上传 Volume；部分采集文件留本地。最后发布不可变的 `_ready/<run_id>.json`。本次选定门店全部上传成功后，自动触发现有云端 Job；单店补跑成功也会触发。

脚本分别打印上传结果、Job 链接/状态、批次入库结果。通过 Job 输出的处理记录确认本 run_id 为 SUCCEEDED 后才报告云端成功。若批次已被更新的批次取代，会明确记录 superseded。云端状态保存在 manifest 的 cloud_job/cloud_processing 中。

已有 Job 在运行时，新请求进入队列，仍遵守最大并发 1。同一批次使用固定幂等提交标识，防止网络重试造成重复提交。最多等待 60 分钟；超时不取消云端任务。

针对平台明确返回 `Triggering new runs ... disabled temporarily` 的提交拒绝，脚本会等待 1、3、5 分钟再试，总计最多提交四次，沿用同一幂等标识。认证、权限及其他错误不做这种重试。失败时间、阶段、异常类型和 SDK 提供的错误码保存到 manifest 的 `cloud_job.submission_errors`；不会记录凭据。重试用尽仍报告入库未确认，已上传数据继续等待云端补漏，不重新采集。

退出码 2 表示上传已完成，但云端触发失败、运行失败或尚未确认结果。不要因此重新抓取；查看 Job 链接或等待每天 18:00 的补漏任务。部分门店失败时不自动触发，已发布的完整门店仍由定时任务处理。

若部分门店失败，完整门店仍可发布和处理，但本地最终返回失败，manifest 明确保留缺口。不要把这些批次视为全天完整覆盖。不要同时启动单品牌脚本、多个入口或手动入库。

## 云端：自动触发入库，定时任务补漏

Notebook：`ingest_volume_batches`。Job：`price-tracker-volume-ingestion`，每天 18:00，时区 Pacific/Auckland，最大并发 1。

- 扫描 `_ready`，处理所有未成功批次，包括前几天遗漏数据。
- 无新批次正常结束，不刷新全量 Silver。
- 同超市、门店、采集日期选最新发布的 run_id；旧批次不会覆盖已发布的新批次。
- 完整验证各文件的行数、日期、门店、分类、SKU 后原子替换对应 Bronze 数据，再更新 Silver/Gold。
- `bronze_price_ingestion_runs` 记录 RUNNING、BRONZE_WRITTEN、SUCCEEDED、FAILED、SUPERSEDED。
- SUCCEEDED 表示发布清单中的门店成功处理；是否全天齐全仍需看 expected_stores 和 incomplete_stores。
- 成功批次跳过。失败或中断批次下次重试；写表与处理记录不是跨表事务，因此重试采用幂等替换。
- 仅由此 Job 写入。不要同时运行旧入库 notebook、本地 `--ingest` 或复制第二个写入 Job。
- 完整上传会自动触发，不必等到 18:00。自动触发失败、部分成功批次或手动发布的历史批次由定时任务补漏，也可在 Job 页面手动 Run now。

Notebook 用 Spark 计算，不调用 SQL Warehouse；仍受 Databricks notebook/serverless 资源可用性与额度约束。

## 上传已完成但尚未发布的历史批次

```powershell
.\.venv\Scripts\python.exe -u run_pipelines.py --publish-manifest data\production_20261102T014143Z_800c2386\manifest.json
```

这只核验已上传文件存在并发布清单，不重新爬取、不执行 SQL。同一 run_id 的清单不可修改；同样内容重复发布安全。不会自动导入旧 `_runs` 里的历史测试/半成品批次。

`--recover` 与 `--ingest` 保留为旧式人工 SQL 恢复工具，需要 Warehouse；日常流程不再使用。若本次仅想上传、不触发 Job，可使用 `--no-trigger`（`--no-ingest` 也具有此效果）。测试模式和旧式 `--ingest` 模式不触发云端 Job。

`rerun_woolworths_today.cmd` 是限定 2026-10-28 的旧临时工具，不可用于日常运行。

## 文件

- `data/production_*/manifest.json`：本地采集结果。
- Volume `_ready/*.json`：云端可处理的批次清单。
- `data/cloud_ingestion_deployment.json`：部署链接与日程。
- `tools/build_cloud_ingestion.py`：从共享转换计划生成自包含 notebook。
- `tools/deploy_cloud_ingestion.py`：更新 notebook 和唯一同名 Job，不创建重复日程。

修改 SQL 转换规则后，重新生成并部署 notebook，避免云端使用旧版规则。
