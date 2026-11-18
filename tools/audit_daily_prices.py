"""Read-only quality and analysis mapping audit for a collected day."""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ingest_prices import SqlClient

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('date',type=date.fromisoformat)
    args=parser.parse_args()
    day=args.date.isoformat()
    db=SqlClient()
    f=f"(SELECT * FROM workspace.default.silver_fact_product_price WHERE collected_date=DATE '{day}')"
    queries={
      'summary':f"SELECT source,count(*) rows,count(DISTINCT store_id) stores,count(DISTINCT source_product_id) skus,count_if(product_id IS NOT NULL) mapped,count_if(total_price IS NULL) missing_price,count_if(total_price=0) zero_price,count_if(reported_unit_price IS NULL) missing_unit_price,count_if(member_price IS NOT NULL) member_prices,count_if(member_price>total_price) member_above_public,count_if(store_verification_status<>'verified') unverified FROM {f} GROUP BY source ORDER BY source",
      'categories':f"SELECT source,category_id,count(*) rows,count(DISTINCT store_id) stores,count_if(total_price IS NULL) missing_price,count_if(reported_unit_price IS NULL) missing_unit_price FROM {f} GROUP BY source,category_id ORDER BY source,category_id",
      'integrity':f"SELECT count(*)-count(DISTINCT observation_id) duplicate_ids,count_if(nullif(source_product_id,'') IS NULL) missing_sku,count_if(nullif(product_url,'') IS NULL) missing_url,count_if(s.store_key IS NULL) orphan_store,count_if(p.product_id IS NULL AND a.product_id IS NOT NULL) orphan_product,count_if(d.date_id IS NULL) orphan_date FROM {f} a LEFT JOIN workspace.default.silver_dim_store s ON a.store_key=s.store_key LEFT JOIN workspace.default.silver_dim_product p ON a.product_id=p.product_id LEFT JOIN workspace.default.silver_dim_date d ON a.date_id=d.date_id",
      'units':f"SELECT source,category_id,reported_unit,count(*) rows,min(reported_unit_price) min_unit_price,max(reported_unit_price) max_unit_price FROM {f} GROUP BY source,category_id,reported_unit ORDER BY source,category_id,rows DESC",
      'selected':f"SELECT p.category_id,p.analysis_rank,p.product_id,p.product_name,p.specification,p.comparison_unit,p.comparison_ready,count(f.observation_id) observations,count(DISTINCT f.source) brands,count(DISTINCT f.store_key) stores,count_if(f.source='woolworths') woolworths,count_if(f.source='newworld') newworld,count_if(f.source='paknsave') paknsave,count_if(f.total_price IS NULL AND f.observation_id IS NOT NULL) missing_price FROM workspace.default.silver_dim_product p LEFT JOIN {f} f ON p.product_id=f.product_id WHERE p.is_analysis_selected=true GROUP BY ALL ORDER BY p.category_id,p.analysis_rank",
      'analysis_ready':f"SELECT source,category_id,count(*) rows,count_if(comparison_ready) ready FROM workspace.default.gold_v_analysis_prices WHERE collected_date=DATE '{day}' GROUP BY source,category_id ORDER BY source,category_id",
      'missing_prices':f"SELECT source,source_product_id,category_id,original_name,original_specification,reported_unit,member_price,count(*) stores FROM {f} WHERE total_price IS NULL OR total_price=0 GROUP BY ALL ORDER BY source,stores DESC LIMIT 80",
      'mapping_examples':f"SELECT source,source_product_id,category_id,original_name,original_specification,product_id,product_mapping_status,count(*) stores FROM {f} WHERE lower(original_name) RLIKE 'farmer brown|woodland|henergy|meadow fresh|rump|chuck|prime beef mince|diced beef|lamb leg' GROUP BY ALL ORDER BY category_id,source,original_name LIMIT 200",
      'store_counts':f"SELECT source,store_id,category_id,count(*) rows FROM {f} GROUP BY source,store_id,category_id ORDER BY source,store_id,category_id",
      'dates':"SELECT collected_date,count(*) rows FROM workspace.default.silver_fact_product_price GROUP BY collected_date ORDER BY collected_date",
      'source_conflicts':f"SELECT source,source_product_id,count(DISTINCT category_id) categories,count(DISTINCT original_name) names,count(DISTINCT original_specification) specs FROM {f} GROUP BY source,source_product_id HAVING categories>1 OR names>1 OR specs>1 LIMIT 100",
    }
    result={'date':day,'queries':queries,'results':{},'columns':{}}
    def run(item):
        name,sql=item
        response=db.client.statement_execution.execute_statement(sql,db.warehouse,wait_timeout='10s',row_limit=1000)
        import time
        while response.status.state.value in ('RUNNING','PENDING'):
            time.sleep(2);response=db.client.statement_execution.get_statement(response.statement_id)
        if response.status.state.value!='SUCCEEDED':raise RuntimeError(f'{name}: {response.status.error}')
        if response.manifest.truncated:raise RuntimeError('Truncated: '+name)
        return name,[c.name for c in response.manifest.schema.columns],response.result.data_array or []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(run,item) for item in queries.items()]):
            name,columns,rows=future.result()
            result['columns'][name]=columns;result['results'][name]=rows
            print(name,len(rows),'rows',flush=True)
    folder=Path('data')/('audit_'+day);folder.mkdir(exist_ok=True)
    path=folder/'audit.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(path.resolve(),flush=True)

if __name__=='__main__':main()
