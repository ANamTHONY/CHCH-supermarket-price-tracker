"""Test batch-logon Chrome collection without changing production data or power state."""
import ctypes
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    folder=ROOT/'data/boot_probe';folder.mkdir(parents=True,exist_ok=True)
    result={'status':'running','production_writes':False,'brands':{}}
    status=folder/'result.json'
    def save():status.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    with (folder/'probe.log').open('w',encoding='utf-8',buffering=1) as stream, redirect_stdout(stream), redirect_stderr(stream):
        try:
            session=ctypes.c_uint()
            if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(),ctypes.byref(session)):
                raise ctypes.WinError()
            result['windows_session_id']=session.value
            settings_path=folder/'settings.json'
            settings=json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
            result['headless']=settings.get('headless',True)
            os.environ['PRICE_TRACKER_HEADLESS']='1' if result['headless'] else '0'
            save()
            from price_storage import load_user_environment,volume_path
            load_user_environment()
            from databricks.sdk import WorkspaceClient
            WorkspaceClient().files.get_directory_metadata(volume_path())
            result['databricks_access']='passed';save()
            if settings.get('runtime_dry_run'):
                from tools.boot_daily import main as boot
                code=boot(['--dry-run'])
                result['status']='passed' if code==0 else 'failed'
                result['runtime_dry_run']=True
                save();return code
            from run_pipelines import run
            from production_runner import main as collect
            stores=json.loads((ROOT/'reference/store_locations.json').read_text(encoding='utf-8'))
            for source in ('woolworths','newworld','paknsave'):
                store=next(s for s in stores if s['source']==source and s.get('is_christchurch_urban'))
                try:
                    run(lambda:collect(argv=['--source',source,'--stores',store['store_id'],
                        '--test','--limit','5','--workers','1','--retries','0']))
                    result['brands'][source]='passed'
                except BaseException as error:
                    result['brands'][source]={'status':'failed','error_type':type(error).__name__,'error':str(error)}
                    traceback.print_exc()
                save()
            result['status']='passed' if all(v=='passed' for v in result['brands'].values()) else 'failed'
        except BaseException as error:
            result.update(status='failed',error_type=type(error).__name__,error=str(error))
            traceback.print_exc()
        save()
        return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
