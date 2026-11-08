# 云端每日采集

目标：GitHub Actions 每天 09:15（Pacific/Auckland，自动处理夏令时）运行 Chrome，采集 28 家门店，上传现有 Databricks Volume，触发并等待现有入库 Job。电脑无需开机。

## 当前部署门槛

先运行 `Cloud collection probe`。每品牌一家门店、五个鸡蛋商品；不上传生产数据。使用 Ubuntu 24.04、Python 3.14、Chrome 和 Xvfb。遇到明确的 Access Denied 会停止，不绕过网站限制。

探测通过后配置生产凭据，手动运行 `Daily supermarket collection`，确认全部 28 家门店和云端批次成功，再将仓库变量 `CLOUD_COLLECTION_ENABLED` 设为 `true`。配置文件写好不等于已经部署或通过验证。

## 配置

GitHub Actions Secrets：`DATABRICKS_HOST`、`DATABRICKS_TOKEN`。凭据只进入受控生产步骤的环境变量，不写入代码、日志或 artifacts。

GitHub Actions Variables：`DATABRICKS_VOLUME_PATH`、`DATABRICKS_INGESTION_JOB_ID`、`CLOUD_COLLECTION_ENABLED`。Job ID 使用现有单写入者，不创建第二个入库任务。

定时 workflow 必须位于默认分支。GitHub 的定时运行可能延迟；以 Actions 和批次日期为准。公共仓库长期无活动可能停用定时任务，应检查 GitHub 的定时任务状态。失败邮件取决于用户的 GitHub Actions 通知设置。

## 故障处理

同一采集 workflow 不重叠，不取消正在采集的运行。失败不自动重跑整日；先查看 Actions 日志、manifest 和诊断附件。附件保留 7 天；已上传原始数据继续留在 Databricks Volume。

退出码 2 表示上传可能已经完成，云端处理未确认，应先查看云端 Job，避免重复抓取。部分门店失败会保留完整门店，现有 18:00 入库任务继续负责处理已发布批次。

本机入口仍可用于故障期间手动采集。云端正常运行后，不要与本机同时启动同一天采集；本机文件锁不能锁住另一台云端机器。
