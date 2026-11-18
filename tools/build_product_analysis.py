"""Generate the selected-product setup and refreshed daily ingestion notebook."""
import csv,json,sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pandas as pd
from product_model import *
from notebook_layout import readable_cells
ROOT=Path(__file__).resolve().parents[1]

def cell(kind,text):
 d={'cell_type':kind,'metadata':{},'source':text.splitlines(True)}
 if kind=='code':compile(text,'cell','exec');d.update(execution_count=None,outputs=[])
 return d

def save_nb(name,cells):
 nb={'cells':readable_cells(cells),'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':5}
 (ROOT/'notebooks'/name).write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8')

def values(rows):
 return ',\n'.join('('+','.join('true' if x is True else 'false' if x is False else str(x) if isinstance(x,int) else sql_string(x) for x in row)+')' for row in rows)

products=pd.read_excel(ROOT/'map.xlsx',dtype=str).to_dict('records')
selected=[];rank=defaultdict(int)
for p in products:
 id=p['id'].zfill(4)
 if id not in SELECTED_IDS:continue
 cat=int(p['category_id']);rank[cat]+=1
 notes=('Match brand, egg grade, farming method and pack size.' if cat==1 else 'Match Meadow Fresh product line, fat type and bottle volume.' if cat==2 else 'Review NZ origin, cut, fresh/frozen, bone and fat content, plus per-kg vs pack pricing before comparison.')
 selected.append({'product_id':id,'product_name':p['prod_name'],'category_id':cat,'specification':p['quant'],'is_analysis_selected':True,'analysis_rank':rank[cat],'comparison_ready':cat!=3,'selection_notes':notes})
assert dict(rank)=={1:5,2:5,3:5}
(ROOT/'reference/analysis_products.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
new_aliases=[('woolworths','Henergy Eggs Cage Free Size 6 12 Pack','12pk','0015'),('woolworths','Farmer Brown Eggs Cage Free Barn Size 6 12 Pack','12pk','0001')]
existing=json.loads((ROOT/'data/product_aliases.json').read_text(encoding='utf-8'))
aliases=existing+new_aliases
lookup=defaultdict(set)
category={p['id'].zfill(4):int(p['category_id']) for p in products}
for source,name,spec,id in aliases:lookup[(source,normalize_name(name),normalize_spec(spec))].add(id)
observed={}
for result in json.loads((ROOT/'data/store_switch_test/results.json').read_text(encoding='utf-8')):
 if not result.get('verified'):continue
 for p in result.get('products',[]):
  source=result['source'];sku=p.get('source_product_id') or p.get('sku')
  key=(source,str(sku));name=p['original_name'];spec=p['total_quant']
  candidates=lookup[(source,normalize_name(name),normalize_spec(spec))]
  pid=next(iter(candidates)) if len(candidates)==1 else None
  if pid and category[pid]!=1:pid=None
  row=(source,str(sku),pid,name,spec,1,p.get('product_url'), 'exact_reference' if pid else 'pending','Observed verified-store test SKU; exact reference match only.')
  if key in observed and observed[key][2]!=pid:raise ValueError(f'Conflicting source SKU {key}')
  observed[key]=row
(ROOT/'reference/source_product_mappings.json').write_text(json.dumps([dict(zip(['source','source_product_id','product_id','original_name','original_specification','category_id','product_url','mapping_status','mapping_note'],r)) for r in observed.values()],ensure_ascii=False,indent=2),encoding='utf-8')
select_sql=f'''MERGE INTO workspace.default.silver_dim_product t USING
(SELECT * FROM VALUES {values([(p['product_id'],p['is_analysis_selected'],p['analysis_rank'],p['selection_notes'],p['comparison_ready']) for p in selected])}
AS v(product_id,is_analysis_selected,analysis_rank,selection_notes,comparison_ready)) s ON t.product_id=s.product_id
WHEN MATCHED AND t.analysis_rank IS NULL THEN UPDATE SET t.is_analysis_selected=s.is_analysis_selected,
t.analysis_rank=s.analysis_rank,t.selection_notes=s.selection_notes,t.comparison_ready=s.comparison_ready'''
alias_sql=f'''MERGE INTO workspace.default.silver_dim_product_alias t USING
(SELECT * FROM VALUES {values(new_aliases)} AS v(source,original_name,original_specification,product_id)) s
ON t.source=s.source AND t.original_name=s.original_name AND t.original_specification=s.original_specification
WHEN NOT MATCHED THEN INSERT *'''
source_sql=f'''MERGE INTO workspace.default.silver_dim_product_source t USING
(SELECT * FROM VALUES {values(list(observed.values()))} AS v(source,source_product_id,product_id,original_name,original_specification,category_id,product_url,mapping_status,mapping_note)) s
ON t.source=s.source AND t.source_product_id=s.source_product_id
WHEN MATCHED AND t.mapping_status='pending' AND s.product_id IS NOT NULL THEN UPDATE SET t.product_id=s.product_id,t.mapping_status=s.mapping_status,t.mapping_note=s.mapping_note
WHEN NOT MATCHED THEN INSERT *'''
migrations={'workspace.default.bronze_prices':EXTRA_COLUMNS,'workspace.default.silver_dim_product':PRODUCT_COLUMNS,'workspace.default.silver_fact_product_price':FACT_COLUMNS}
seeds=["UPDATE workspace.default.silver_dim_product SET is_analysis_selected=false WHERE is_analysis_selected IS NULL",select_sql,alias_sql,source_sql]
base=json.loads((ROOT/'notebooks/price_model_statements.json').read_text(encoding='utf-8'))
refresh=[base['refresh'][0],'''MERGE INTO workspace.default.silver_dim_date t USING (
 SELECT DISTINCT cast(date_format(collected_date,'yyyyMMdd') AS INT) date_id,collected_date calendar_date,
 year(collected_date) year,quarter(collected_date) quarter,month(collected_date) month,day(collected_date) day,
 weekday(collected_date)+1 day_of_week,weekday(collected_date)>=5 is_weekend FROM workspace.default.bronze_prices
) s ON t.date_id=s.date_id WHEN NOT MATCHED THEN INSERT *''',*SILVER_PREPARE,LEARN_SOURCE_SQL,*MAPPING_REVIEW,FACT_REFRESH]
plan={'migrations':migrations,'ddl':[SOURCE_DDL],'seeds':seeds,'refresh':refresh,'views':VIEWS}
(ROOT/'notebooks/product_analysis_statements.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
migration_code='''# Add nullable metadata columns without changing existing values.
MIGRATIONS = '''+repr(migrations)+'''
for table,columns in MIGRATIONS.items():
    if not spark.catalog.tableExists(table):
        raise ValueError(f"Run setup_price_model / initial ingestion first: {table}")
    current=set(spark.table(table).columns)
    missing=[f"{name} {kind}" for name,kind in columns.items() if name not in current]
    if missing:spark.sql(f"ALTER TABLE {table} ADD COLUMNS ({', '.join(missing)})")
'''
setup_code=migration_code+'\nstatements='+repr(plan['ddl']+seeds+refresh+VIEWS)+'''\nfor statement in statements:
    spark.sql(statement)
display(spark.sql("SELECT * FROM workspace.default.gold_v_analysis_products ORDER BY category_id,analysis_rank"))
'''
save_nb('setup_product_analysis.ipynb',[cell('markdown','''# 商品分析对象与精确映射初始化

每类 5 个，共 15 个标准商品。全量采集保持不变，仅分析视图筛选。
商品官网 ID 按超市分别维护；精确名称/规格/分类匹配用于学习来源 SKU，再通过已确认 SKU 映射。
pending_review 暂缓映射，不能通过别名回退绕过审核。清洗原值保留在 raw_specification/raw_reported_unit。
不使用模糊名称匹配，不将测试报价写入正式事实表。肉类比较需要进一步核实。
此初始化保留已有门店、商品和手工确认的映射；重复运行不覆盖已维护的选择标记。
'''),cell('code',setup_code)])
silver_code=migration_code+'\nstatements='+repr(refresh+VIEWS)+'''\n
before=spark.table('workspace.default.bronze_prices').count()
valid=spark.sql("SELECT count(*) n FROM workspace.default.bronze_prices WHERE collected_date >= DATE '2026-10-27'").first().n
if not valid:raise ValueError('No production Bronze input; existing Silver remains unchanged')
for statement in statements:spark.sql(statement)
check=spark.sql("SELECT count(*)-count(DISTINCT observation_id) duplicates,count_if(collected_date < DATE '2026-10-27') historical FROM workspace.default.silver_fact_product_price").first()
assert check.duplicates==0 and check.historical==0
assert spark.table('workspace.default.bronze_prices').count()==before
display(spark.table('workspace.default.silver_v_price_quality'))
display(spark.table('workspace.default.silver_v_product_mapping_queue'))
'''
save_nb('bronze_to_silver.ipynb',[cell('markdown','''# Bronze → Silver 价格清洗与商品映射

直接读取 bronze_prices，不需要重新爬取或读取 CSV。生产起点：2026-10-27。
保留所有类别及未映射报价；统一规格与计价单位，普通价和会员价分别处理。
来源 SKU 优先映射；未确认或存在歧义的 SKU 保留空 product_id 并进入待映射清单。
适合当前小规模数据：每次全量清洗生产期 Bronze，原子覆盖 fact；修订映射后重跑即可回填历史。
各表单独提交，整本 notebook 并非跨表事务；失败后重跑。避免并发运行多个刷新任务。
仅 Gold 选择肉/蛋/奶各 5 个分析对象。本 notebook 不修改 Bronze。
'''),cell('code',silver_code)])
config='''import re
from functools import reduce
from datetime import date
from pyspark.sql import functions as F
from pyspark.sql.window import Window

dbutils.widgets.text("volume_path","/Volumes/workspace/default/price_tracker")
dbutils.widgets.text("collected_date","")
VOLUME_PATH=dbutils.widgets.get("volume_path").rstrip("/")
DATE_FILTER=dbutils.widgets.get("collected_date").strip()
TARGET_TABLE="workspace.default.bronze_prices"
if DATE_FILTER:
    date.fromisoformat(DATE_FILTER)
    if DATE_FILTER < '2026-10-27':raise ValueError('Production begins on 2026-10-27')
if not VOLUME_PATH.startswith("/Volumes/"):raise ValueError("Expected a /Volumes/ path")
'''
reader='''# Read each header separately: old/new CSV layouts are aligned by name, never by position.
BASE_FIELDS=["product_id","store_id","category_id","total_price","total_quant","unit","unit_price","original_name","collected_date","is_promo","source"]
EXTRA_FIELDS='''+repr(list(EXTRA_COLUMNS))+'''
FIELDS=BASE_FIELDS+EXTRA_FIELDS
files=sorted(f.path for f in dbutils.fs.ls(VOLUME_PATH) if f.name.startswith("prices_") and f.name.endswith(".csv"))
if not files:raise ValueError("No production price CSV files found")
frames=[]
for path in files:
    frame=(spark.read.format("csv").option("header",True).option("inferSchema",False)
           .option("multiLine",True).option("escape",'"').option("mode","FAILFAST").load(path))
    if not set(BASE_FIELDS).issubset(frame.columns) or set(frame.columns)-set(FIELDS):
        raise ValueError(f"Unexpected CSV header: {path}: {frame.columns}")
    for name in EXTRA_FIELDS:
        if name not in frame.columns:frame=frame.withColumn(name,F.lit(None).cast("string"))
    frames.append(frame.select(*FIELDS).withColumn("source_file",F.lit(path)))
raw=reduce(lambda a,b:a.unionByName(b),frames)
for name in ["source","store_id","collected_date"]:raw=raw.withColumn(name,F.trim(F.col(name)))
raw=raw.withColumn("date_text",F.col("collected_date")).withColumn("collected_date",F.expr("try_cast(date_text AS DATE)"))
raw=raw.filter(F.col("collected_date") >= F.lit('2026-10-27').cast('date'))
if DATE_FILTER:raw=raw.filter(F.col("date_text")==DATE_FILTER)
if not raw.take(1):raise ValueError("No input rows; target remains unchanged")
bad=raw.filter(F.col("source").isNull() | ~F.col("source").isin("newworld","paknsave","woolworths") |
 F.col("store_id").isNull() | (F.col("store_id")=="") | F.col("collected_date").isNull() |
 ~F.col("date_text").rlike(r"^\\d{4}-\\d{2}-\\d{2}$"))
if bad.take(1):
    display(bad)
    raise ValueError("Invalid source/store/date; target remains unchanged")
raw=raw.drop("date_text").withColumn("file_name",F.regexp_extract("source_file",r"([^/]+)$",1))
raw=raw.withColumn("batch_time",F.regexp_extract("file_name",r"^prices_(?:woolworths|newworld|paknsave)_(\\d{4}-\\d{2}-\\d{2}T\\d{12}Z)_[0-9a-f]{8}\\.csv$",1))
if raw.filter("batch_time = ''").take(1):raise ValueError("Unexpected production filename")
KEYS=["source","store_id","collected_date"]
window=Window.partitionBy(*KEYS).orderBy(F.desc("batch_time"),F.desc("source_file"))
latest=(raw.select(*KEYS,"batch_time","source_file").distinct().withColumn("rank",F.row_number().over(window))
        .filter("rank = 1").drop("rank","batch_time"))
incoming=(raw.join(latest,KEYS+["source_file"],"inner").select(*FIELDS,"source_file")
          .dropDuplicates().withColumn("ingested_at",F.current_timestamp()))
display(incoming.groupBy(*KEYS,"source_file").count().orderBy(*KEYS))
display(incoming.limit(20))
'''
writer=migration_code+'''
expected={f.name:f.dataType.simpleString() for f in incoming.schema.fields}
actual={f.name:f.dataType.simpleString() for f in spark.table(TARGET_TABLE).schema.fields}
if actual!=expected:raise ValueError(f"Target schema mismatch: {actual}")
keys=incoming.select(*KEYS).distinct().limit(5001).collect()
if not keys or len(keys)>5000:raise ValueError("Empty or oversized replacement scope")
def sql_string(value):return "'"+value.replace("\\\\","\\\\\\\\").replace("'","\\\\'")+"'"
predicate=" OR ".join("(source="+sql_string(r.source)+" AND store_id="+sql_string(r.store_id)+" AND collected_date=DATE '"+r.collected_date.isoformat()+"')" for r in keys)
(incoming.select(*spark.table(TARGET_TABLE).columns).write.format("delta").mode("overwrite")
 .option("replaceWhere",predicate).saveAsTable(TARGET_TABLE))
print(f"Replaced {len(keys)} source/store/date groups")
'''
refresh_code='statements='+repr(refresh+VIEWS)+'''\nfor statement in statements:spark.sql(statement)
display(spark.sql("SELECT * FROM workspace.default.gold_v_analysis_products ORDER BY category_id,analysis_rank"))
display(spark.sql("SELECT source,category_id,count(*) observations,count_if(comparison_ready) ready FROM workspace.default.gold_v_analysis_prices GROUP BY source,category_id"))
'''
save_nb('ingest_daily_prices.ipynb',[cell('markdown','''# 每日价格入库与分析

保留所有采集记录；仅 Gold 分析视图选择蛋/奶/肉各 5 个标准商品。
同超市、门店、采集日只用最新 CSV，使用单次 Delta 原子替换，重跑不会累加。
旧文件缺失官网商品 ID、会员价及门店验证信息时保留空值，不能伪造历史验证结果。
`_tests`、`_details` 子目录不导入正式报价。先运行一次 setup_product_analysis。
'''),cell('code',config),cell('code',reader),cell('code',writer),cell('code',refresh_code)])
print('Selected',len(selected),'products; observed',len(observed),'source SKUs;',sum(1 for r in observed.values() if r[2]),'mapped exactly')
