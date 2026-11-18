# Bronze → Silver pipeline

Databricks notebook: `price-tracker/bronze_to_silver`。
直接点击 Run all，处理现有 Bronze；无需重新爬取或上传 CSV。
自 2026-11-03 起，日常由定时 Job 的 `ingest_volume_batches` notebook 复用相同 SQL 规则，入库后刷新 Silver；本地 `run_pipelines.py` 默认只上传并发布完成清单。
旧 `ingest_daily_prices` 和本地 `--ingest` 仅保留为人工维护工具，不要与定时 Job 并发使用。
不用在同一次运行中重复执行两本 notebook；不要同时运行多个刷新任务。

## 流程

1. `silver_v_prices_clean` 从正式起点 2026-10-27 起读取 Bronze，保留原始规格和单位。
2. 标准化 Bottle/Carton/Pack 后缀规格；变重肉类标记 variable_weight，不把最小订购重量当固定规格。
3. 分离公斤单价与包装估价；100g/100ml 统一为 kg/l，会员单价单独转换。无法识别的单位不猜测。
4. 根据标准商品别名的精确名称/规格/分类匹配维护 `silver_dim_product_source`；已批准映射不会被自动覆盖。
5. 按品牌 + 来源 SKU 映射，检查规格、类别一致；`pending_review` 不会回退到别名匹配。
6. 以品牌/门店/日期/分类/来源 SKU 去重，全量原子覆盖 `silver_fact_product_price`。
7. 更新质量、待映射和 Gold 视图。Silver 保留全部商品，Gold 才限制 15 个分析对象。

当前数据规模使用生产期全量重建，映射修订后重跑即可重处理历史。单张 fact 原子提交；整条流程不是跨表事务，失败后重跑。已有数值 NULL 不补成零，普通价不使用会员价代替。

## 查看结果

- `workspace.default.silver_v_price_quality`：日期/品牌/类别的行数、缺价、未映射、未知单位和规格情况。
- `workspace.default.silver_v_product_mapping_queue`：待映射来源 SKU、原始名称/规格、规范规格、URL 和审核原因。
- `workspace.default.silver_fact_product_price`：全部清洗报价及商品 ID。
- `workspace.default.gold_v_analysis_prices`：15 个分析商品；只有 `comparison_ready=true` 的记录可用于比较。优先使用 `normalized_unit_price` + `normalized_unit`，不能直接把所有 `total_price` 都当包装价。

## 维护映射

核实品牌、产品线、鲜奶/UHT、包装容量，或蛋大小/养殖方式/数量；肉类还需核实鲜冻、部位、带骨和脂肪含量。
确认后在 `silver_dim_product_source` 维护 `product_id`、`mapping_status='approved'` 和 `mapping_note`，然后重跑 pipeline。
无法确认的记录保留 `pending` 或 `pending_review`。新增商品须先在 `silver_dim_product` 创建标准商品，不能直接创造不存在的 product_id。
同店同日多个 SKU 映射到同一分析商品时，Gold 的比较标记为 false，不任意选最便宜项或将价格求和。

## 代码和验证

- `silver_rules.py`：规格、单位、质量视图和已审阅的来源 SKU。
- `product_model.py`：来源 SKU 学习与事实表刷新。
- `tools/build_product_analysis.py`：生成独立 Silver notebook 和日常入库 notebook。
- `tools/validate_silver_rules.py`：在 Databricks 上用只读 VALUES 测试真实 SQL 清洗规则。
- `tools/deploy_product_analysis.py`：迁移、执行、验证 Bronze 不变/重跑结果一致，并部署 notebook。

目前仍保留 26 条未采到普通价的记录，以及官网单位只显示 `100` 的报价；不能仅凭数字推断其分母。
两种 Foodstuffs Original Fresh Milk 1L 来源 SKU 暂缓映射，等待包装身份核实；肉类分析对象仍需审核。
