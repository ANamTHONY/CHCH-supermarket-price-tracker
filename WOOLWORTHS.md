# Woolworths NZ 采集

`pipeline_countdown.py` 已适配当前网页。每家店使用独立匿名 Chrome 会话：
打开鸡蛋页 → Select an address → Pick up → 搜索门店 → Save and continue →
关闭时段弹窗 → 刷新并核对页面顶部 Selected Store → 采集商品。
使用实际标签 ID `tab-1-pickup`，不再依赖旧版 Change location/地区下拉菜单。
不登录、不加入购物车、不预约时段。

## 默认：三店，每店五个，测试目录

```powershell
.\.venv\Scripts\python.exe pipeline_countdown.py
```

默认 Avonhead (`001`)、Church Corner (`006`)、Christchurch Airport (`005`)，
每家只采 5 个鸡蛋类商品。输出到 `data/woolworths_<批次>/`，自动上传到
`/Volumes/workspace/default/price_tracker/_tests/<批次>/`。
不会替换正式门店日数据。

只测试一家，或只保存在本地：

```powershell
.\.venv\Scripts\python.exe pipeline_countdown.py --stores 001 --limit 5 --local-only
```

## 全量模式

```powershell
.\.venv\Scripts\python.exe pipeline_countdown.py --full
```

全量模式使用原来的 13 家门店及蛋、奶、牛肉、羊肉分类，跟随分页。
可用 `--stores 001 006 005` 限定门店；全量模式不使用测试条数限制。
原列表包含 Ashburton，若只采市区，请显式排除 `002`。
当前实测覆盖上述三店各 5 个鸡蛋；其他分类与全量分页未做端到端采集验证。

正式 CSV 保留现有字段并追加官网商品 ID、链接、会员价等元数据：`total_price` 是当前普通/非会员售价，
`unit_price` 与它对应。会员价绝不填入普通售价；普通售价缺失则保留 NULL。

包含下列扩展字段的完整明细写入 `details.jsonl`，上传到 Volume 的
`_details/<正式CSV同名批次>.jsonl`：

- `source_product_id`、`product_url`、实际门店名称及验证标记。
- `non_member_price`、`member_price`、`was_price`。
- 普通与会员单位价、促销标记、原始商品卡片文字。

新版每日 Notebook 已将 CSV 中的官网商品 ID、链接、会员价、会员单位价和原价写入
bronze/silver；JSONL 另保留完整网页文字，便于追溯。商品映射和 15 个分析对象的维护见
`PRODUCT_ANALYSIS.md`。

每条记录都检查门店身份。切店失败、解析失败、分页循环或存储失败会报错，
失败页面与截图保存到批次目录。全量运行失败时保留本地 CSV，不自动上传部分批次，
避免不完整采集替换当天完整数据。

## 已验证

- 三家店的选择、刷新后状态和五条商品采集。
- 普通价、会员价、原价以及单位价分离。
- `100g` 单位分母不会误删数字；商品规格与鸡蛋 Size 等级区分。
- 全量中途异常不上传部分 CSV。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
