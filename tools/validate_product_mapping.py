"""Read-only SQL integration checks using the exact deployed fact transformation."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from product_model import FACT_REFRESH,sql_string
from price_storage import load_user_environment
from databricks.sdk import WorkspaceClient
load_user_environment();w=WorkspaceClient()
h=next(x.id for x in w.warehouses.list() if x.name=='Serverless Starter Warehouse')
base={'product_id':'0003','store_id':'001','category_id':'1','total_price':'10.39','total_quant':'12pk','unit':'ea','unit_price':'0.87','original_name':'Renamed packaging label','collected_date':'2026-10-26','is_promo':'0','source':'woolworths','source_product_id':'352492','product_url':'https://example.invalid/test','member_price':'9.99','member_unit_price':'0.83','was_price':None,'store_verified':'true','source_file':'fixture.csv','ingested_at':'2026-10-26 12:00:00'}
rows=[base,{**base,'source_product_id':'unmapped-sku','original_name':'Henergy Eggs Cage Free Size 6 12 Pack','total_quant':'12 Pack'},
 {**base,'product_id':'0001','source_product_id':'422870','original_name':'Woolworths Eggs Barn Mixed Grade 20 Pack','total_quant':'20pk'},
 {**base,'source':'newworld','source_product_id':'352492'}]
parts=[]
for row in rows:
 fields=[]
 for key,value in row.items():
  text=sql_string(value)
  if key=='collected_date':text=f'cast({text} AS DATE)'
  if key=='ingested_at':text=f'cast({text} AS TIMESTAMP)'
  fields.append(text+' AS '+key)
 parts.append('SELECT '+','.join(fields))
body=FACT_REFRESH[FACT_REFRESH.index('WITH '):].replace('FROM workspace.default.bronze_prices','FROM shadow')
query=body.replace('WITH ','WITH shadow AS ('+' UNION ALL '.join(parts)+'), ',1)
r=w.statement_execution.execute_statement(query,h,wait_timeout='10s',row_limit=20)
while r.status.state.value in ['PENDING','RUNNING']:
 time.sleep(2);r=w.statement_execution.get_statement(r.statement_id)
if r.status.state.value!='SUCCEEDED':raise RuntimeError(str(r.status.error))
for row in r.result.data_array:
 source,sku,pid,method=row[6],row[18],row[4],row[14]
 expected={('woolworths','352492'):('0015','source_id'),('woolworths','unmapped-sku'):('0015','name_spec_exact'),('woolworths','422870'):(None,'unmapped'),('newworld','352492'):(None,'unmapped')}[(source,sku)]
 assert (pid,method)==expected,(source,sku,pid,method,expected)
 assert row[23]=='verified'
 print('PASS:',source,sku,method,flush=True)
assert len(r.result.data_array)==4
print('PASS: source-ID priority, normalized exact fallback, no legacy-ID guessing, cross-retailer isolation')
