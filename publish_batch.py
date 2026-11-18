"""Publish a final ready marker after confirmed CSV uploads; no SQL compute required."""
import io
import json
from pathlib import Path
from batch_protocol import validate_batch,digest
from price_storage import volume_path


def publish(path):
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.errors import NotFound
    volume=volume_path()
    client=WorkspaceClient()
    state=json.loads(Path(path).read_text(encoding='utf-8'))
    if state['mode']!='production':raise ValueError('Cannot publish test runs')
    if state['status'] in ('running','interrupted'):
        raise ValueError('Collection is not finalized; do not publish an active/interrupted manifest')
    fields=('source','store_id','store_name','rows','category_counts','remote_file')
    batch={'protocol_version':1,'run_id':state['run_id'],'mode':'production',
           'collected_date':state['collected_date'],'expected_stores':state['expected_stores'],
           'files':[{k:r[k] for k in fields} for r in state['results'] if r['status']=='uploaded'],
           'incomplete_stores':[{'source':r['source'],'store_id':r['store_id'],'status':r['status']}
                                for r in state['results'] if r['status']!='uploaded']}
    validate_batch(batch,volume)
    # Verify remote presence before exposing the ready marker.
    for record in batch['files']:client.files.get_metadata(record['remote_file'])
    target=volume+'/_ready/'+batch['run_id']+'.json'
    try:
        with client.files.download(target).contents as stream:existing=json.load(stream)
    except NotFound:
        client.files.create_directory(volume+'/_ready')
        client.files.upload(target,io.BytesIO(json.dumps(batch,ensure_ascii=False,indent=2).encode()),overwrite=False)
    else:
        if digest(existing)!=digest(batch):raise ValueError('Published run ID is immutable; content differs')
    print('PUBLISHED',target,'complete stores',len(batch['files']),flush=True)
    return target
