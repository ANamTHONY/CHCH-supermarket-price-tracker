"""Immutable publication contract; shared by local publisher and cloud notebook."""
import hashlib
import json
import re
from datetime import date


def validate_batch(batch, volume):
    if batch.get('protocol_version') != 1 or batch.get('mode') != 'production':
        raise ValueError('Unsupported batch protocol')
    if not re.fullmatch(r'production_\d{8}T\d{6}Z_[0-9a-f]{8}',batch.get('run_id','')):
        raise ValueError('Invalid run ID')
    day=date.fromisoformat(batch['collected_date'])
    if day<date(2026,10,27):raise ValueError('Before official collection start')
    seen=set()
    for record in batch['files']:
        key=(record['source'],record['store_id'])
        if key in seen:raise ValueError('Duplicate store batch')
        seen.add(key)
        if record['source'] not in ('woolworths','newworld','paknsave'):raise ValueError('Unknown source')
        if not re.fullmatch(r'[A-Za-z0-9-]+',record['store_id']):raise ValueError('Invalid store ID')
        path=record['remote_file']
        if not path.startswith(volume+'/prices_'+record['source']+'_') or '/' in path[len(volume)+1:] or not path.endswith('.csv'):
            raise ValueError('Unexpected file path')
        if not isinstance(record['rows'],int) or record['rows']<=0:raise ValueError('Empty batch')
        if any(record['category_counts'].get(c,0)<=0 for c in ('Egg','Milk','Meat')):raise ValueError('Missing category')
    if not seen:raise ValueError('No complete store files')
    return batch


def digest(batch):
    return hashlib.sha256(json.dumps(batch,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def latest_files(batches):
    """Choose newest published run per source/store/day, including processed runs."""
    latest={}
    for batch in batches:
        for record in batch['files']:
            key=(record['source'],record['store_id'],batch['collected_date'])
            if key not in latest or batch['run_id']>latest[key][0]:
                latest[key]=(batch['run_id'],record)
    return latest
