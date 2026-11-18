"""Upload the incremental notebook and upsert its daily serverless Job."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from price_storage import load_user_environment,volume_path
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat
from databricks.sdk.service.jobs import Task,NotebookTask,CronSchedule,PauseStatus,JobSettings

load_user_environment()
w=WorkspaceClient()
folder='/Users/'+w.current_user.me().user_name+'/price-tracker'
path=folder+'/ingest_volume_batches'
w.workspace.mkdirs(folder)
w.workspace.upload(path,(ROOT/'notebooks/ingest_volume_batches.ipynb').read_bytes(),format=ImportFormat.JUPYTER,overwrite=True)
name='price-tracker-volume-ingestion'
matches=list(w.jobs.list(name=name))
if len(matches)>1:raise RuntimeError('Multiple jobs with this name; refusing ambiguous update')
settings=dict(name=name,description='Process completed Volume batches, including missed dates; Bronze then Silver. Single writer.',
              max_concurrent_runs=1,timeout_seconds=3600,
              schedule=CronSchedule(quartz_cron_expression='0 0 18 * * ?',timezone_id='Pacific/Auckland',pause_status=PauseStatus.UNPAUSED),
              tasks=[Task(task_key='ingest_ready_batches',notebook_task=NotebookTask(notebook_path=path,
                          base_parameters={'volume_path':volume_path()}),max_retries=1,min_retry_interval_millis=300000)])
if matches:
    job_id=matches[0].job_id
    w.jobs.update(job_id,new_settings=JobSettings(**settings))
else:job_id=w.jobs.create(**settings).job_id
remote=w.jobs.get(job_id)
assert remote.settings.max_concurrent_runs==1
assert remote.settings.schedule.timezone_id=='Pacific/Auckland'
assert remote.settings.schedule.quartz_cron_expression=='0 0 18 * * ?'
nb=w.workspace.get_status(path)
report={'job_id':job_id,'job_url':w.config.host.rstrip('/')+'/#job/'+str(job_id),
        'notebook_url':w.config.host.rstrip('/')+'/#notebook/'+str(nb.object_id),
        'notebook_path':path,'schedule':'Daily 18:00 Pacific/Auckland','max_concurrent_runs':1}
(ROOT/'data/cloud_ingestion_deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
