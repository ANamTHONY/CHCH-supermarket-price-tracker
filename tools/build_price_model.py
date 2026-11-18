"""Build repeatable Databricks SQL notebooks from the project's known references."""
import ast
import json
from pathlib import Path
import re
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PREFIX='workspace.default.'
def q(value):
    if value is None or pd.isna(value): return 'NULL'
    return "'"+str(value).replace('\\','\\\\').replace("'","\\'")+"'"
def table(name, columns, comment):
    return f"CREATE TABLE IF NOT EXISTS {PREFIX}{name} (\n{columns}\n) USING DELTA COMMENT {q(comment)}"
def seed(name, fields, rows, keys):
    values=',\n'.join('('+', '.join(q(v) for v in row)+')' for row in rows)
    on=' AND '.join(f't.{k}=s.{k}' for k in keys)
    # Reference seeds only add missing rows; manually edited names/coordinates are preserved.
    return f"MERGE INTO {PREFIX}{name} t USING (SELECT * FROM VALUES {values} AS v({', '.join(fields)})) s ON {on} WHEN NOT MATCHED THEN INSERT ({", ".join(fields)}) VALUES ({", ".join("s."+f for f in fields)})"
def assignment(file, name):
    module=ast.parse((ROOT/file).read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in module.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))

DDL=[
table('silver_dim_brand', '''brand_id STRING NOT NULL PRIMARY KEY,
brand_name STRING NOT NULL, country_code STRING''', '超市连锁品牌；不是商品生产商'),
table('silver_dim_category', '''category_id INT NOT NULL PRIMARY KEY,
category_name STRING NOT NULL, category_name_zh STRING''', '商品分类：蛋、奶、肉'),
table('silver_dim_store', '''store_key STRING NOT NULL PRIMARY KEY,
source STRING NOT NULL, store_id STRING NOT NULL,
brand_id STRING NOT NULL REFERENCES workspace.default.silver_dim_brand(brand_id),
store_name STRING, address STRING, city STRING, region STRING, country_code STRING,
latitude DECIMAL(10,7), longitude DECIMAL(10,7), location_verified BOOLEAN,
location_source_url STRING, coordinate_source_url STRING, location_checked_date DATE,
location_status STRING, is_christchurch_urban BOOLEAN''', '门店键为 source:store_id；未核实的名称、地址和坐标留空'),
table('silver_dim_product', '''product_id STRING NOT NULL PRIMARY KEY,
product_name STRING NOT NULL,
category_id INT REFERENCES workspace.default.silver_dim_category(category_id),
specification STRING, quantity DECIMAL(12,4), quantity_unit STRING,
comparison_unit STRING, product_brand_name STRING''', '标准商品；沿用 map.xlsx 的四位商品 ID；商品生产商品牌待维护'),
table('silver_dim_product_alias', '''source STRING NOT NULL, original_name STRING NOT NULL,
original_specification STRING NOT NULL,
product_id STRING NOT NULL REFERENCES workspace.default.silver_dim_product(product_id),
PRIMARY KEY (source, original_name, original_specification)''', '三家超市原始品名及规格到标准商品的映射；精确匹配'),
table('silver_dim_date', '''date_id INT NOT NULL PRIMARY KEY, calendar_date DATE NOT NULL,
year INT, quarter INT, month INT, day INT, day_of_week INT, is_weekend BOOLEAN''', '日期维度；day_of_week 为星期一=1 至星期日=7'),
table('silver_fact_product_price', '''observation_id STRING NOT NULL PRIMARY KEY,
date_id INT NOT NULL REFERENCES workspace.default.silver_dim_date(date_id),
collected_date DATE NOT NULL,
store_key STRING NOT NULL REFERENCES workspace.default.silver_dim_store(store_key),
product_id STRING REFERENCES workspace.default.silver_dim_product(product_id),
category_id INT REFERENCES workspace.default.silver_dim_category(category_id),
source STRING NOT NULL, store_id STRING NOT NULL,
original_name STRING NOT NULL, original_specification STRING,
total_price DECIMAL(12,4), reported_unit_price DECIMAL(12,4), reported_unit STRING,
is_promo BOOLEAN, product_mapping_status STRING, price_quality_status STRING,
source_file STRING, ingested_at TIMESTAMP''', '每日门店商品报价；原始品名和规格区分未映射商品；reported 单价未标准化')]
brands=[('woolworths','Woolworths','NZ'),('newworld','New World','NZ'),('paknsave',"PAK'nSAVE",'NZ')]
SEEDS=[seed('silver_dim_brand',['brand_id','brand_name','country_code'],brands,['brand_id']),seed('silver_dim_category',['category_id','category_name','category_name_zh'],[(1,'Egg','蛋类'),(2,'Milk','奶类'),(3,'Meat','肉类')],['category_id'])]
fields=['store_key','source','store_id','brand_id','store_name','address','city','region','country_code','latitude','longitude','location_verified']
stores=[]
for id,name in assignment('pipeline_countdown.py','store_map').items():
    stores.append((f'woolworths:{id}','woolworths',id,'woolworths',name,None,None,None,'NZ',None,None,False))
known={'paknsave':{'4a279605-eaa8-470d-bcd4-0a9e3c9ab43b':"PAK'nSAVE Riccarton",'61dd754e-8525-4b9e-9e08-173389eea8a8':"PAK'nSAVE Moorhouse",'8cd700ae-d96f-4761-bd7a-805d6b93536d':"PAK'nSAVE Papanui",'be4c4780-218e-425a-a90f-63e21773572b':"PAK'nSAVE Hornby",'dbca5e00-f7f9-43ae-91de-031ad16f8a92':"PAK'nSAVE Wainoni"},'newworld':{'c6abac35-b75f-4a02-9b43-7ad5a7c7aa37':'New World Ilam','81f807e9-1879-484c-b27e-ded56245c6a4':'New World Fendalton'}}
for source,file in [('newworld','pipeline_newworld.py'),('paknsave','pipeline_paknsave.py')]:
    for id in dict.fromkeys(assignment(file,'christchurch_stores')):
        stores.append((f'{source}:{id}',source,id,source,known[source].get(id),None,None,None,'NZ',None,None,False))
SEEDS.append(seed('silver_dim_store',fields,stores,['store_key']))
df=pd.read_excel(ROOT/'map.xlsx',dtype=str).where(lambda x:x.notna(),None)
assert df['id'].is_unique
products=[];aliases=[]
for r in df.to_dict('records'):
    pid=r['id'].zfill(4)
    spec=r['quant']
    m=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(pk|pack|ea|g|kg|ml|l)',(spec or '').lower())
    products.append((pid,r['prod_name'],r['category_id'],spec,m.group(1) if m else None,m.group(2) if m else None,r['unit'],None))
    for source,col in [('newworld','neww_name'),('paknsave','pak_name'),('woolworths','wool_name')]:
        if pd.notna(r[col]) and r[col]: aliases.append((source,r[col],spec,pid))
assert len({tuple(a[:3]) for a in aliases})==len(aliases), 'Conflicting aliases'
SEEDS.append(seed('silver_dim_product',['product_id','product_name','category_id','specification','quantity','quantity_unit','comparison_unit','product_brand_name'],products,['product_id']))
SEEDS.append(seed('silver_dim_product_alias',['source','original_name','original_specification','product_id'],aliases,['source','original_name','original_specification']))

REFRESH=["""MERGE INTO workspace.default.silver_dim_store t
USING (SELECT DISTINCT concat(source, ':', store_id) AS store_key, source, store_id,
source AS brand_id, 'NZ' AS country_code FROM workspace.default.bronze_prices) s
ON t.store_key = s.store_key
WHEN NOT MATCHED THEN INSERT (store_key,source,store_id,brand_id,country_code,location_verified)
VALUES (s.store_key,s.source,s.store_id,s.brand_id,s.country_code,false)""",
"""MERGE INTO workspace.default.silver_dim_date t
USING (SELECT DISTINCT cast(date_format(collected_date,'yyyyMMdd') as int) date_id,
collected_date calendar_date, year(collected_date) year, quarter(collected_date) quarter,
month(collected_date) month, day(collected_date) day, weekday(collected_date)+1 day_of_week,
weekday(collected_date)>=5 is_weekend FROM workspace.default.bronze_prices) s
ON t.date_id=s.date_id WHEN NOT MATCHED THEN INSERT ({", ".join(fields)}) VALUES ({", ".join("s."+f for f in fields)})""",
"""INSERT OVERWRITE TABLE workspace.default.silver_fact_product_price
WITH ranked AS (
 SELECT *, row_number() OVER (
 PARTITION BY source,store_id,collected_date,category_id,original_name,coalesce(total_quant,'')
 ORDER BY ingested_at DESC,source_file DESC,total_price DESC,unit_price DESC,is_promo DESC,product_id DESC,unit DESC
 ) rn FROM workspace.default.bronze_prices
), enriched AS (
 SELECT b.*, coalesce(p.product_id,a.product_id) mapped_product_id,
 coalesce(p.category_id,ap.category_id,c.category_id) mapped_category_id,
 try_cast(b.total_price AS DECIMAL(12,4)) price_value,
 try_cast(b.unit_price AS DECIMAL(12,4)) unit_price_value
 FROM ranked b
 LEFT JOIN workspace.default.silver_dim_product p
 ON p.product_id=CASE WHEN trim(b.product_id) RLIKE '^[0-9]{1,4}$' THEN lpad(trim(b.product_id),4,'0') ELSE trim(b.product_id) END
 LEFT JOIN workspace.default.silver_dim_product_alias a
 ON b.source=a.source AND b.original_name=a.original_name AND b.total_quant=a.original_specification
 LEFT JOIN workspace.default.silver_dim_product ap ON a.product_id=ap.product_id
 LEFT JOIN workspace.default.silver_dim_category c ON try_cast(b.category_id AS INT)=c.category_id
 WHERE b.rn=1
)
SELECT sha2(to_json(named_struct('source',source,'store_id',store_id,'date',collected_date,
'category',category_id,'name',original_name,'spec',coalesce(total_quant,''))),256) observation_id,
cast(date_format(collected_date,'yyyyMMdd') AS INT) date_id, collected_date,
concat(source,':',store_id) store_key, mapped_product_id product_id, mapped_category_id category_id,
source,store_id,original_name,total_quant original_specification,
CASE WHEN price_value>=0 THEN price_value END total_price,
CASE WHEN unit_price_value>=0 THEN unit_price_value END reported_unit_price,
unit reported_unit,
CASE WHEN is_promo='1' THEN true WHEN is_promo='0' THEN false END is_promo,
CASE WHEN mapped_product_id IS NULL THEN 'unmapped' ELSE 'mapped' END product_mapping_status,
CASE WHEN price_value IS NULL THEN 'missing_or_invalid_price' WHEN price_value<0 THEN 'negative_price' ELSE 'ok' END price_quality_status,
source_file,ingested_at FROM enriched"""]

# Product metadata and SKU matching share the same implementation as daily ingestion.
import sys
sys.path.insert(0,str(ROOT))
from product_model import EXTRA_COLUMNS,PRODUCT_COLUMNS,FACT_COLUMNS,SOURCE_DDL,LEARN_SOURCE_SQL,FACT_REFRESH,SILVER_PREPARE,MAPPING_REVIEW
for index,columns in [(3,PRODUCT_COLUMNS),(6,FACT_COLUMNS)]:
    DDL[index]=DDL[index].replace("\n) USING DELTA",",\n"+",\n".join(name+" "+kind for name,kind in columns.items())+"\n) USING DELTA",1)
DDL.append(SOURCE_DDL)
REFRESH[1]=REFRESH[1][:REFRESH[1].index("WHEN NOT MATCHED")]+"WHEN NOT MATCHED THEN INSERT *"
REFRESH=[REFRESH[0],REFRESH[1],*SILVER_PREPARE,LEARN_SOURCE_SQL,*MAPPING_REVIEW,FACT_REFRESH]

def notebook(cells):
    out=[]
    for kind,text in cells:
        cell={'cell_type':kind,'metadata':{},'source':text.splitlines(True)}
        if kind=='code': cell.update(execution_count=None,outputs=[]);compile(text,'cell','exec')
        out.append(cell)
    return {'cells':out,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':5}
setup=notebook([('markdown','''# 初始化价格模型（首次运行）

命名为 bronze_prices、silver_dim_*、silver_fact_*。
只创建缺失表，引用数据只插入缺失键；不会覆盖手工维护的门店名称和坐标。
门店信息来自项目现有代码，尚未进行外部核实；未知值留空。
标准商品来自 map.xlsx，生产商品牌留空。
日常运行 ingest_daily_prices；本 Notebook 不需要每天运行。
'''),('code','statements = '+repr(DDL+SEEDS)+'\nfor statement in statements:\n    spark.sql(statement)\nprint("模型及参考数据初始化完成")\n')])
setup_path = ROOT/'notebooks/setup_price_model.ipynb'
if setup_path.exists():
    previous = json.loads(setup_path.read_text(encoding='utf-8'))
    setup['cells'].extend(c for c in previous['cells'] if c.get('metadata', {}).get('store_locations_generated'))
setup_path.write_text(json.dumps(setup,ensure_ascii=False,indent=2),encoding='utf-8')
(ROOT/'notebooks/price_model.sql').write_text(';\n\n'.join(DDL)+';\n',encoding='utf-8')
(ROOT/'notebooks/price_model_statements.json').write_text(json.dumps({'ddl':DDL,'seeds':SEEDS,'refresh':REFRESH},ensure_ascii=False,indent=2),encoding='utf-8')
p=ROOT/'notebooks/ingest_daily_prices.ipynb'
nb=json.loads(p.read_text(encoding='utf-8'))
# Replace old naming in every cell; remove generated refresh cells on rebuild.
nb['cells']=[c for c in nb['cells'] if not c.get('metadata',{}).get('price_model_generated')]
for c in nb['cells']:
    c['source']=[line.replace('prices_bronze','bronze_prices') for line in c['source']]
extra=notebook([('markdown','''## 刷新维度与价格事实表

先运行一次 setup_price_model 初始化模型。
当前数据量较小，每天从 bronze_prices 全量重建价格事实表，使用单次原子覆盖，因此不会累加重复数据。
保留未映射商品（product_id 为空），可按 product_mapping_status 排查。
reported_unit_price 保留采集算法的单价，不代表已统一为每 kg/L/个的价格。
事实表粒度为每日/超市/门店/原始品名/原始规格/原始分类，精确重复报价只保留一条。
此步骤固定处理 workspace.default.bronze_prices。
'''),('code','''if TARGET_TABLE != "workspace.default.bronze_prices":
    raise ValueError("维度/事实刷新固定使用 workspace.default.bronze_prices，请恢复默认目标表")
refresh_statements = '''+repr(REFRESH)+'''
for statement in refresh_statements:
    spark.sql(statement)
display(spark.sql("SELECT source, collected_date, count(*) rows, count_if(product_id IS NULL) unmapped FROM workspace.default.silver_fact_product_price GROUP BY source,collected_date ORDER BY collected_date DESC,source"))
''')])
for c in extra['cells']: c['metadata']['price_model_generated']=True
nb['cells'].extend(extra['cells'])
p.write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8')
print('Generated:',len(DDL),'tables;',len(stores),'stores;',len(products),'products;',len(aliases),'aliases')
