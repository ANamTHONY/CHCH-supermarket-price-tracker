# 商品筛选与映射

采集端保留所有商品。标准商品映射和分析对象筛选在 Databricks 完成。
现有 51 个标准商品保留，只标记其中 15 个用于分析。
正式报价从新西兰日期 **2026-10-27** 开始；更早的原始 CSV/Bronze 可供追溯，但不得进入 fact。

正式运行：`.\.venv\Scripts\python.exe run_pipelines.py`。
默认采集配置中的 28 家基督城门店，肉、蛋、奶全部配置分类及分页，不限制商品数量。
每家门店三类完成后上传；失败批次只留本地。运行结束后自动校验并原子替换同来源/门店/日期的 Bronze 数据，刷新 fact。
`--no-ingest` 只上传，随后可运行 Databricks 的 `ingest_daily_prices` notebook。
`--test` 仅采集 5 个蛋类商品作跳转测试，不上传正式数据。

| 分类 | 选择的标准商品 |
|---|---|
| 蛋 | Farmer Brown Barn Size 6 / 7 各 12pk；Woodland Free Range Size 6 / 7 各 10pk；Henergy Cage Free Size 6 12pk |
| 奶 | Meadow Fresh Original 1L / 2L / 3L；Calci-Trim 1L / 2L |
| 肉 | Beef Rump Steak；NZ Beef Chuck Steak；Prime Beef Mince；NZ Diced Beef；Lamb Leg |

清单保存于 `reference/analysis_products.json`，沿用已有商品 ID。
肉类在比较前必须进一步核实产地、鲜冻、部位、骨和脂肪含量，以及每 kg/每包装的计价方式；
这 5 个肉类对象的 `comparison_ready=false`。

## 表与视图

均位于 `workspace.default`：

- `silver_dim_product`：标准品名、分类、规格。新增 `is_analysis_selected`、
  `analysis_rank`、`selection_notes`、`comparison_ready`。
- `silver_dim_product_alias`：各超市原始名称与规格到标准商品的对应关系。
- `silver_dim_product_source`：以 `(source, source_product_id)` 为键的官网商品 ID 映射。
  已确认的状态为 `approved` 或 `exact_reference`，未知商品为 `pending`。
- `gold_v_analysis_products`：15 个分析对象及官网 ID 映射覆盖情况，无报价也会列出。
- `gold_v_analysis_prices`：只取这 15 个对象的已映射报价，保留质量标记。
- `gold_v_unmapped_products`：未映射商品及出现次数，便于补映射。

官网 ID 不同于项目内部 `product_id`，也不应在不同超市之间直接互认。
New World/PAK'nSAVE 保存页面完整的 `product-...` 标识，Woolworths 保存商品链接中的数字 ID。

## 匹配规则

1. 优先使用已确认的 `(source, source_product_id)`，并检查分类一致。
2. 没有确认的 ID 映射时，按超市来源、名称、规格、分类精确匹配别名表。
3. 名称只统一大小写和连续空格；规格统一空格及 `Pack`/`pk`。
   不模糊匹配品牌、蛋的等级/饲养方式、牛奶脂肪类型或肉类部位。
4. 归一化后出现多个标准商品的候选会被排除。采集端旧的标准 ID 不再作为猜测依据。
5. 未匹配商品仍进入事实表，只是标准商品 ID 为空。

已用通过门店验证的测试样本建立 21 条官网 ID 记录，其中 9 条能精确对应既有标准商品；
其余 12 条待匹配。这里只使用样本的身份信息，测试价格没有导入正式报价表。

## 日常运行

首次商品初始化使用 `setup_product_analysis`。已在当前 Workspace 执行。
以后每天运行更新后的 `ingest_daily_prices`：

全量 CSV → 按超市/门店/日期原子替换 bronze → 更新官网 ID 对照 →
刷新全量 silver 价格事实表 → 由 Gold 视图筛选 15 个标准商品。

`run_pipelines.py` 作为正式全量入口，会向 Woolworths 显式传入 `--full`。
单独运行 `pipeline_countdown.py` 的默认三店五商品测试模式保持不变。

读取 CSV 时逐文件读取表头，再按列名合并，兼容旧版 11 列与扩展版 17 列；
缺失字段为空，不会把旧字段按位置错读成新字段。`_tests`、`_details` 不进入正式报价。

原始 CSV 追加 `source_product_id`、`product_url`、`member_price`、
`member_unit_price`、`was_price`、`store_verified`。
事实表保存这些价格元数据，并将历史门店验证未知的记录标记为 `legacy_unverified`。

`gold_v_analysis_prices.comparison_ready` 只有在商品规格可比较、门店已验证、价格有效时才为 true。
现有旧报价均缺少门店验证信息，因此当前视图可用于检查映射，不能据此宣称已完成可靠的跨店比价。
未来正确验证的采集批次入库后，满足条件的蛋/奶报价才会成为可比较记录。

## 维护

更换分析对象时，在 `silver_dim_product` 调整选择标记与组内排序；保持每类 5 个。
为待匹配官网 ID 设置标准商品 ID 后，将 `silver_dim_product_source.mapping_status` 设为 `approved`，
再运行每日 Notebook 刷新。确认具体规格一致之后才批准映射。
初始化脚本保留已有排序、手工选择和已批准的 ID 映射。

验证包括：每类 5 个、事实 ID 唯一、刷新幂等、原始报价不变、官网 ID 优先、精确回退、
不信任旧 ID、不同超市 ID 隔离，以及扩展 CSV 的字段和前导零。
