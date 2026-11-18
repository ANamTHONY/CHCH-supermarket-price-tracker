"""Apply generated model SQL and publish the two notebooks."""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from price_storage import load_user_environment
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat
load_user_environment()
w=WorkspaceClient()
warehouses=list(w.warehouses.list())
warehouse_id=next(h.id for h in warehouses if h.name=='Serverless Starter Warehouse')
def run(sql, label):
    result=w.statement_execution.execute_statement(sql,warehouse_id,wait_timeout='10s',row_limit=100)
    while result.status.state.value in ('PENDING','RUNNING'):
        time.sleep(2)
        result=w.statement_execution.get_statement(result.statement_id)
    if result.status.state.value!='SUCCEEDED':
        raise RuntimeError(f'{label}: {result.status.error}')
    print(label, result.result.data_array if result.result else '',flush=True)
    return result
names={t.name for t in w.tables.list(catalog_name='workspace',schema_name='default')}
if 'prices_bronze' in names:
    if 'bronze_prices' in names: raise RuntimeError('Both old and new bronze tables exist; resolve before migration')
    run('ALTER TABLE workspace.default.prices_bronze RENAME TO workspace.default.bronze_prices','Rename bronze')
statements=json.loads(Path('notebooks/price_model_statements.json').read_text(encoding='utf-8'))
for group in ['ddl','seeds','refresh']:
    for i,s in enumerate(statements[group]):run(s,f'{group} {i+1}')
run('''SELECT 'bronze_prices' table_name,count(*) rows FROM workspace.default.bronze_prices
UNION ALL SELECT 'silver_dim_brand',count(*) FROM workspace.default.silver_dim_brand
UNION ALL SELECT 'silver_dim_category',count(*) FROM workspace.default.silver_dim_category
UNION ALL SELECT 'silver_dim_store',count(*) FROM workspace.default.silver_dim_store
UNION ALL SELECT 'silver_dim_product',count(*) FROM workspace.default.silver_dim_product
UNION ALL SELECT 'silver_dim_product_alias',count(*) FROM workspace.default.silver_dim_product_alias
UNION ALL SELECT 'silver_dim_date',count(*) FROM workspace.default.silver_dim_date
UNION ALL SELECT 'silver_fact_product_price',count(*) FROM workspace.default.silver_fact_product_price''','Table counts')
run('''SELECT count(*) rows,count(distinct observation_id) distinct_ids,
count_if(product_id IS NULL) unmapped,count_if(price_quality_status!='ok') invalid_price
FROM workspace.default.silver_fact_product_price''','Fact integrity')
run('''SELECT count(*) orphan_stores FROM workspace.default.silver_fact_product_price f
LEFT ANTI JOIN workspace.default.silver_dim_store s ON f.store_key=s.store_key''','Store integrity')
integrity = run("""SELECT count(*)-count(DISTINCT observation_id) duplicate_ids,
count_if(store_key IS NULL OR date_id IS NULL) invalid_keys
FROM workspace.default.silver_fact_product_price""", 'Uniqueness check')
assert integrity.result.data_array[0] == ['0','0'], integrity.result.data_array
fingerprint_sql = "SELECT count(*),sum(cast(xxhash64(observation_id, total_price, source_file) AS DECIMAL(38,0))) FROM workspace.default.silver_fact_product_price"
before = run(fingerprint_sql,'Before repeat').result.data_array
run(statements['refresh'][-1], 'Repeat fact refresh')
after = run(fingerprint_sql,'After repeat').result.data_array
assert before == after, (before,after)
print('PASS: repeated refresh preserves fact count and fingerprint', flush=True)
folder='/Users/' +w.current_user.me().user_name+'/price-tracker'
w.workspace.mkdirs(folder)
for name in ['setup_price_model','ingest_daily_prices']:
    path=folder+'/'+name
    w.workspace.upload(path,Path('notebooks/'+name+'.ipynb').read_bytes(),format=ImportFormat.JUPYTER,overwrite=True)
    obj=w.workspace.get_status(path)
    print('Notebook:',name,w.config.host.rstrip('/')+'/#notebook/'+str(obj.object_id),flush=True)
