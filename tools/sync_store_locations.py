"""Apply reviewed location references to existing store IDs without changing prices."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from price_storage import load_user_environment
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat
load_user_environment();w=WorkspaceClient()
warehouse_id=next(h.id for h in w.warehouses.list() if h.name=='Serverless Starter Warehouse')
def run(sql):
 r=w.statement_execution.execute_statement(sql,warehouse_id,wait_timeout='10s',row_limit=100)
 while r.status.state.value in ['PENDING','RUNNING']:
  time.sleep(2);r=w.statement_execution.get_statement(r.statement_id)
 if r.status.state.value!='SUCCEEDED':raise RuntimeError(str(r.status.error))
 return r.result.data_array if r.result else None
def q(v):
 if v is None:return 'NULL'
 if isinstance(v,bool):return str(v).lower()
 if isinstance(v,(int,float)):return str(v)
 return "'"+str(v).replace('\\','\\\\').replace("'","\\'")+"'"
table='workspace.default.silver_dim_store'
cols={c.name for c in w.tables.get(table).columns}
extra={'location_source_url':'STRING','coordinate_source_url':'STRING','location_checked_date':'DATE','location_status':'STRING','is_christchurch_urban':'BOOLEAN'}
missing=[f'{k} {v}' for k,v in extra.items() if k not in cols]
if missing:run(f'ALTER TABLE {table} ADD COLUMNS ({", ".join(missing)})')
rows=json.loads(Path('reference/store_locations.json').read_text(encoding='utf-8'))
fields=list(rows[0])
assert len({r['store_key'] for r in rows})==len(rows)
values=',\n'.join('('+','.join(q(r[k]) for k in fields)+')' for r in rows)
assign=', '.join(f't.{k}=s.{k}' for k in fields if k!='store_key')
query=f'''MERGE INTO {table} t USING (SELECT * FROM VALUES {values} AS v({','.join(fields)})) s
ON t.store_key=s.store_key
WHEN MATCHED AND (t.latitude IS NULL OR t.longitude IS NULL OR t.coordinate_source_url IS NULL)
THEN UPDATE SET {assign}
WHEN NOT MATCHED THEN INSERT ({",".join(fields)}) VALUES ({",".join("s."+k for k in fields)})'''
before=run(f'SELECT count(*) FROM {table}')
snapshot=run(f'SELECT to_json(struct(*)) FROM {table}')
Path('data/store_locations_before_update.json').write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
print('Location merge:',run(query),flush=True)
after=run(f'SELECT count(*) FROM {table}')
assert int(after[0][0]) >= int(before[0][0])
run(f"UPDATE {table} SET location_status='unresolved_store_identity' WHERE source='newworld' AND store_name IS NULL AND latitude IS NULL AND location_status IS NULL")
print('Store count after references:' ,after,flush=True)
print('Coverage:',run(f'''SELECT source,count(*) stores,count(latitude) with_coordinates,count_if(location_verified) verified FROM {table} GROUP BY source ORDER BY source'''),flush=True)
print('Unresolved:',run(f'SELECT store_key,store_name,location_status FROM {table} WHERE latitude IS NULL OR longitude IS NULL'),flush=True)
print('Urban scope:',run(f'SELECT store_name,city,is_christchurch_urban FROM {table} WHERE is_christchurch_urban=false'),flush=True)
print('Coordinate validation:',run(f'''SELECT count(*) FROM {table} WHERE latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180'''),flush=True)
# Repeatable setup notebook cell; it only fills missing location references.
setup_path=Path('notebooks/setup_price_model.ipynb')
nb=json.loads(setup_path.read_text(encoding='utf-8'))
nb['cells']=[c for c in nb['cells'] if not c.get('metadata',{}).get('store_locations_generated')]
nb['cells'].append({'cell_type':'markdown','metadata':{'store_locations_generated':True},'source':['## 门店地址与坐标\n','只补缺失坐标/来源，保留已有核实结果和手工维护的资料。供应商坐标未完成地图核对时 location_verified=false。\n']})
code='location_sql = '+repr(query)+'\nspark.sql(location_sql)\n'
compile(code,'location_cell','exec')
nb['cells'].append({'cell_type':'code','metadata':{'store_locations_generated':True},'execution_count':None,'outputs':[],'source':code.splitlines(True)})
setup_path.write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8')
Path('reference/store_locations.sql').write_text(query+';\n',encoding='utf-8')
folder='/Users/'+w.current_user.me().user_name+'/price-tracker'
w.workspace.upload(folder+'/setup_price_model',setup_path.read_bytes(),format=ImportFormat.JUPYTER,overwrite=True)
print('Setup notebook updated',flush=True)
