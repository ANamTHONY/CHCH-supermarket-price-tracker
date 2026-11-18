"""Validate a completed manifest's raw CSVs and compare them to Volume copies."""
import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from price_storage import load_user_environment


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    args=parser.parse_args()
    state=json.loads(args.manifest.read_text(encoding='utf-8'))
    load_user_environment()
    from databricks.sdk import WorkspaceClient
    client=WorkspaceClient()

    def inspect(record):
        outcome={'source':record['source'],'store_id':record['store_id'],'errors':[]}
        if record['status']!='uploaded':
            outcome['errors'].append('Not uploaded')
            return outcome
        local=ROOT/'data'/record['remote_file'].rsplit('/',1)[-1]
        payload=local.read_bytes()
        response=client.files.download(record['remote_file'])
        with response.contents as stream:remote=stream.read()
        outcome['sha256']=hashlib.sha256(payload).hexdigest()
        if hashlib.sha256(remote).hexdigest()!=outcome['sha256']:
            outcome['errors'].append('Volume/local content mismatch')
        rows=list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
        outcome['rows']=len(rows)
        if len(rows)!=record['rows']:outcome['errors'].append('Row count mismatch')
        identities=[]
        categories=Counter()
        missing_units=0
        for row in rows:
            if (row['source'],row['store_id'],row['collected_date'])!=(record['source'],record['store_id'],state['collected_date']):
                outcome['errors'].append('Source/store/date mismatch')
            if row['store_verified'].lower()!='true':outcome['errors'].append('Unverified store')
            if not row['source_product_id'] or not row['product_url']:outcome['errors'].append('Missing SKU or URL')
            try:
                price=Decimal(row['total_price'])
                if not price.is_finite() or price<=0:raise ValueError()
            except (InvalidOperation,ValueError):outcome['errors'].append('Invalid public price')
            identities.append((row['category_id'],row['source_product_id']))
            categories[row['category_id']]+=1
            missing_units+=row['unit_price'] in ('','None')
        if len(identities)!=len(set(identities)):outcome['errors'].append('Duplicate category/SKU')
        if set(categories)!={'1','2','3'}:outcome['errors'].append('Incomplete categories')
        outcome['category_counts']=dict(categories)
        outcome['missing_raw_unit_price']=missing_units
        outcome['errors']=sorted(set(outcome['errors']))
        return outcome

    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(inspect,state['results']))
    selected=state.get('selected_stores',[])
    expected={(s['source'],s['store_id']) for s in selected}
    actual={(s['source'],s['store_id']) for s in results}
    passed=bool(expected) and actual==expected and len(results)==len(expected) and all(not r['errors'] for r in results)
    report={'date':state['collected_date'],'status':'passed' if passed else 'failed',
            'stores':len(results),'rows':sum(r.get('rows',0) for r in results),
            'results':results,'scope':'raw CSV and Volume only; database tables require separate checks'}
    folder=ROOT/'data'/('audit_'+state['collected_date']);folder.mkdir(exist_ok=True)
    path=folder/'raw_volume_validation.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(report['status'],report['stores'],'stores',report['rows'],'rows',path)
    for result in results:
        if result['errors']:print(result['store_id'],result['errors'])
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
