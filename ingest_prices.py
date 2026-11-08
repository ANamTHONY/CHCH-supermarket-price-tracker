"""Validate completed store batches and atomically replace their daily Bronze rows."""
import json
import os
import time
from pathlib import Path
from uuid import uuid4
from databricks.sdk import WorkspaceClient
from price_storage import FIELDS, EXTRA_FIELDS, load_user_environment, volume_path
from product_model import sql_string

START_DATE = '2026-10-27'
ROOT = Path(__file__).resolve().parent

class SqlClient:
    def __init__(self):
        load_user_environment()
        self.client = WorkspaceClient()
        self.warehouse = os.environ.get('DATABRICKS_WAREHOUSE_ID') or next(
            h.id for h in self.client.warehouses.list() if h.name == 'Serverless Starter Warehouse')

    def run(self, sql):
        try:
            result = self.client.statement_execution.execute_statement(sql, self.warehouse, wait_timeout='10s', row_limit=1000)
        except Exception as error:
            # Submission may have an unknown outcome: never blindly retry writes.
            raise RuntimeError(
                f'Databricks SQL warehouse {self.warehouse} rejected or could not confirm submission: {error}. '
                'Uploaded CSV files are retained. Check warehouse availability and recover the manifest; '
                'do not rerun collection just to retry ingestion.'
            ) from error
        while result.status.state.value in ('PENDING', 'RUNNING'):
            time.sleep(2)
            result = self.client.statement_execution.get_statement(result.statement_id)
        if result.status.state.value != 'SUCCEEDED':
            raise RuntimeError(str(result.status.error))
        if result.manifest and result.manifest.truncated:
            raise RuntimeError('SQL result truncated')
        return (result.result.data_array if result.result else None) or []

    def check_ready(self):
        """A real query is required; a warehouse status alone is not sufficient."""
        if self.run('SELECT 1') != [['1']]:
            raise RuntimeError('Databricks SQL readiness query returned an unexpected result')

def ingest_manifest(path):
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    if state['mode'] != 'production' or state['collected_date'] < START_DATE:
        raise ValueError('Only production data from 2026-10-27 onward may be ingested')
    records = [r for r in state['results'] if r['status'] == 'uploaded']
    if not records:
        raise ValueError('No completed store batches to ingest')
    db = SqlClient()
    db.check_ready()
    fields = list(FIELDS) + ['source'] + list(EXTRA_FIELDS)
    schema = ','.join(f'{name} STRING' for name in fields)
    selects = []
    expected = {}
    predicates = []
    for record in records:
        remote = record['remote_file']
        if not remote.startswith(volume_path() + '/prices_'):
            raise ValueError('Unexpected production file path')
        key = (record['source'], record['store_id'], state['collected_date'])
        if key in expected:
            raise ValueError('Duplicate store batch')
        expected[key] = record['rows']
        cols = ','.join('try_cast(collected_date AS DATE) collected_date' if k == 'collected_date' else k for k in fields)
        selects.append(f"SELECT {cols},{sql_string(remote)} source_file,current_timestamp() ingested_at FROM read_files({sql_string(remote)},format=>'csv',header=>true,multiLine=>true,escape=>'\"',mode=>'FAILFAST',schema=>{sql_string(schema)})")
        predicates.append(f"(source={sql_string(key[0])} AND store_id={sql_string(key[1])} AND collected_date=DATE {sql_string(key[2])})")
    stage = 'workspace.default._price_ingest_' + uuid4().hex
    print('INGEST stage',stage,'stores',len(records),flush=True)
    db.run(f'CREATE TABLE {stage} USING DELTA AS ' + ' UNION ALL '.join(selects))
    # Keep the staging table on failure for diagnosis; never publish incomplete inputs.
    observed = db.run(f'SELECT source,store_id,cast(collected_date AS STRING),count(*),count(DISTINCT category_id),count_if(coalesce(try_cast(store_verified AS BOOLEAN),false)=false) FROM {stage} GROUP BY 1,2,3')
    if {tuple(r[:3]):int(r[3]) for r in observed} != expected or any(int(r[4]) != 3 or int(r[5]) for r in observed):
        raise ValueError(f'Batch validation failed; staging retained: {stage}')
    columns = [c.name for c in db.client.tables.get('workspace.default.bronze_prices').columns]
    predicate = ' OR '.join(predicates)
    db.run(f"INSERT INTO workspace.default.bronze_prices REPLACE WHERE {predicate} SELECT {','.join(columns)} FROM {stage}")
    print('INGEST Bronze replaced; refreshing Silver and views',flush=True)
    plan = json.loads((ROOT/'notebooks/product_analysis_statements.json').read_text(encoding='utf-8'))
    for step,sql in enumerate(plan['refresh'] + plan['views'],1):
        print('INGEST transformation',step,flush=True)
        db.run(sql)
    check = db.run('SELECT count(*)-count(DISTINCT observation_id),count_if(collected_date < DATE \'2026-10-27\') FROM workspace.default.silver_fact_product_price')
    if check != [['0','0']]:
        raise ValueError(f'Fact validation failed: {check}')
    verified = db.run(f'SELECT source,store_id,cast(collected_date AS STRING),count(*) FROM workspace.default.bronze_prices WHERE {predicate} GROUP BY 1,2,3')
    if {tuple(r[:3]):int(r[3]) for r in verified} != expected:
        raise ValueError('Bronze row counts do not match the completed batches')
    db.run(f'DROP TABLE {stage}')
    return {'status':'complete','stores':len(records),'rows':sum(expected.values()),'collected_date':state['collected_date']}

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    args = parser.parse_args()
    result = ingest_manifest(args.manifest)
    state = json.loads(args.manifest.read_text(encoding='utf-8'))
    state['ingestion'] = result
    args.manifest.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
