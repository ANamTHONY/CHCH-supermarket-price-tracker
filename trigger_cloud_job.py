"""Queue and monitor cloud ingestion after a complete local upload."""
import hashlib
import json
import os
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent


def value(enum):
    return getattr(enum,'value',enum)


def trigger_batch(batch_id, on_update, *, client=None, job_id=None, timeout=3600,
                  submission_delays=(60,180,300)):
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.jobs import QueueSettings
    from price_storage import load_user_environment
    if client is None:
        load_user_environment()
        client=WorkspaceClient()
    if job_id is None:
        configured=os.environ.get('DATABRICKS_INGESTION_JOB_ID')
        if configured:
            job_id=int(configured)
        else:
            config=json.loads((ROOT/'data/cloud_ingestion_deployment.json').read_text(encoding='utf-8'))
            job_id=int(config['job_id'])
    print('CLOUD JOB preflight',job_id,'at',datetime.now(ZoneInfo('Pacific/Auckland')).isoformat(),flush=True)
    settings=client.jobs.get(job_id).settings
    if settings.max_concurrent_runs!=1:
        raise RuntimeError('Cloud ingestion Job must have max_concurrent_runs=1')
    # Queue even if a previous run is active: that run may have scanned before
    # this batch was published. Repeated submissions for the same batch reuse a run.
    token=hashlib.sha256(('price-tracker:'+batch_id).encode()).hexdigest()
    errors=[]
    for attempt in range(len(submission_delays)+1):
        try:
            print('CLOUD JOB submitting',job_id,'attempt',attempt+1,
                  'at',datetime.now(ZoneInfo('Pacific/Auckland')).isoformat(),flush=True)
            run_id=client.jobs.run_now(job_id,idempotency_token=token,queue=QueueSettings(enabled=True)).run_id
            break
        except Exception as error:
            diagnostic={'stage':'run_now','attempt':attempt+1,
                'occurred_at':datetime.now(ZoneInfo('Pacific/Auckland')).isoformat(),
                'exception_type':type(error).__name__,'message':str(error)}
            # Whitelist metadata; never log credentials, headers, or request bodies.
            for field in ('error_code','status','retry_after_secs','request_id'):
                val=getattr(error,field,None)
                if isinstance(val,(str,int,float,bool)):
                    diagnostic[field]=val
            errors.append(diagnostic)
            temporary=('triggering new runs' in str(error).lower()
                       and 'disabled temporarily' in str(error).lower())
            retry=temporary and attempt<len(submission_delays)
            if retry:diagnostic['retry_in_seconds']=submission_delays[attempt]
            failure={'status':'retrying' if retry else 'unconfirmed','job_id':job_id,
                     'submission_errors':[dict(x) for x in errors]}
            on_update(failure)
            print('CLOUD JOB submission error',json.dumps(diagnostic,ensure_ascii=False),flush=True)
            if not retry:raise
            time.sleep(submission_delays[attempt])
    result={'status':'submitted','job_id':job_id,'run_id':run_id,
            'run_url':client.config.host.rstrip('/')+f'/#job/{job_id}/run/{run_id}'}
    result['submitted_at']=datetime.now(ZoneInfo('Pacific/Auckland')).isoformat()
    result['submission_attempts']=len(errors)+1
    if errors:result['submission_errors']=[dict(x) for x in errors]
    on_update(dict(result))
    print('CLOUD JOB submitted:',result['run_url'],flush=True)
    deadline=time.monotonic()+timeout
    last_state=None
    last_log=0
    while True:
        run=client.jobs.get_run(run_id)
        lifecycle=value(run.state.life_cycle_state)
        outcome=value(run.state.result_state)
        if lifecycle!=last_state or time.monotonic()-last_log>=30:
            print('CLOUD JOB',run_id,lifecycle,outcome or '',flush=True)
            last_state=lifecycle;last_log=time.monotonic()
        if lifecycle in ('TERMINATED','SKIPPED','INTERNAL_ERROR'):
            result['job_result']=outcome
            if outcome!='SUCCESS':
                result.update(status='failed',message=run.state.state_message or 'Job did not succeed')
                on_update(dict(result));return result
            tasks=[t for t in run.tasks or [] if t.task_key=='ingest_ready_batches']
            if len(tasks)!=1:raise RuntimeError('Cannot identify ingestion task output')
            output=client.jobs.get_run_output(tasks[0].run_id)
            if not output.notebook_output or output.notebook_output.truncated:
                raise RuntimeError('Cannot verify batch status from notebook output')
            payload=json.loads(output.notebook_output.result)
            entry=next((r for r in payload.get('ledger',[]) if r['run_id']==batch_id),None)
            if not entry or entry['status'] not in ('SUCCEEDED','SUPERSEDED'):
                result.update(status='unverified',message='Job succeeded but this batch is not confirmed processed')
            else:
                result.update(status='succeeded' if entry['status']=='SUCCEEDED' else 'superseded',batch=entry)
            on_update(dict(result));return result
        if time.monotonic()>=deadline:
            result.update(status='pending',message='Local wait timed out; cloud run continues. Check the run URL.')
            on_update(dict(result));return result
        time.sleep(10)
