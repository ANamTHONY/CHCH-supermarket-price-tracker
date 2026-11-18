"""Apply product metadata migrations, exact mappings and analysis views."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from price_storage import load_user_environment
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat
load_user_environment();w=WorkspaceClient()
warehouse=next(h.id for h in w.warehouses.list() if h.name=='Serverless Starter Warehouse')
def run(sql,label='SQL'):
 r=w.statement_execution.execute_statement(sql,warehouse,wait_timeout='10s',row_limit=200)
 while r.status.state.value in ['PENDING','RUNNING']:
  time.sleep(2);r=w.statement_execution.get_statement(r.statement_id)
 if r.status.state.value!='SUCCEEDED':raise RuntimeError(f'{label}: {r.status.error}')
 rows=r.result.data_array if r.result else None
 print(label,rows,flush=True)
 return rows
plan=json.loads(Path('notebooks/product_analysis_statements.json').read_text(encoding='utf-8'))
before=run('SELECT count(*),sum(cast(xxhash64(source,store_id,collected_date,original_name,total_price) AS DECIMAL(38,0))) FROM workspace.default.bronze_prices','Bronze before')
for table,columns in plan['migrations'].items():
 existing={c.name for c in w.tables.get(table).columns}
 missing=[f'{name} {kind}' for name,kind in columns.items() if name not in existing]
 if missing:run(f'ALTER TABLE {table} ADD COLUMNS ({", ".join(missing)})','Migrate '+table)
for group in ['ddl','seeds','refresh','views']:
 for i,sql in enumerate(plan[group]):run(sql,f'{group} {i+1}')
after=run('SELECT count(*),sum(cast(xxhash64(source,store_id,collected_date,original_name,total_price) AS DECIMAL(38,0))) FROM workspace.default.bronze_prices','Bronze after')
assert before==after
counts=run('SELECT category_id,count(*) FROM workspace.default.gold_v_analysis_products GROUP BY category_id ORDER BY category_id','Selected per category')
assert counts==[['1','5'],['2','5'],['3','5']],counts
run('SELECT category_id,analysis_rank,product_id,product_name,specification,comparison_ready FROM workspace.default.gold_v_analysis_products ORDER BY category_id,analysis_rank','Selected products')
run('SELECT source,mapping_status,count(*) FROM workspace.default.silver_dim_product_source GROUP BY source,mapping_status ORDER BY source,mapping_status','Source registry')
run('SELECT category_id,source,count(*),count_if(comparison_ready) FROM workspace.default.gold_v_analysis_prices GROUP BY category_id,source ORDER BY category_id,source','Analysis observations')
check=run('SELECT count(*)-count(DISTINCT observation_id),count_if(product_id IS NOT NULL AND product_mapping_status=\'unmapped\') FROM workspace.default.silver_fact_product_price','Fact integrity')
assert check==[['0','0']],check
# Rerun the exact source learning + fact refresh: no duplicate accumulation.
fingerprint='SELECT count(*),sum(cast(xxhash64(observation_id,product_id,total_price) AS DECIMAL(38,0))) FROM workspace.default.silver_fact_product_price'
one=run(fingerprint,'Fact before repeat')
for sql in plan['refresh'][2:]:run(sql,'Repeat mapping/refresh')
two=run(fingerprint,'Fact after repeat');assert one==two
folder='/Users/'+w.current_user.me().user_name+'/price-tracker'
for name in ['setup_product_analysis','ingest_daily_prices','bronze_to_silver']:
 w.workspace.upload(folder+'/'+name,Path('notebooks/'+name+'.ipynb').read_bytes(),format=ImportFormat.JUPYTER,overwrite=True)
 status=w.workspace.get_status(folder+'/'+name)
 print(name,w.config.host.rstrip('/')+'/#notebook/'+str(status.object_id),flush=True)
print('PASS: bronze unchanged, 5/category selected, unique fact keys and idempotent refresh',flush=True)
