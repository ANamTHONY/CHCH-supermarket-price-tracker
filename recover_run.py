"""Recover table ingestion from confirmed uploads; never collect new data."""
import json
from pathlib import Path
from datetime import datetime,timezone


def recovery_scope(state, locations):
    if state.get('mode') != 'production':
        raise ValueError('Only production manifests can be recovered')
    uploaded = [r for r in state['results'] if r['status']=='uploaded']
    if not uploaded:
        raise ValueError('No confirmed uploads to recover')
    selected = state.get('selected_stores')
    if not selected:
        # Old all-store manifests did not save the selected store list.
        selected = [s for s in locations if s.get('is_christchurch_urban') is True]
        if len(selected) != state['expected_stores']:
            raise ValueError('Legacy manifest scope is ambiguous; cannot recover automatically')
    return selected


def recover(path):
    from ingest_prices import ingest_manifest
    from daily_checks import check_run
    path=Path(path).resolve()
    state=json.loads(path.read_text(encoding='utf-8'))
    locations=json.loads((Path(__file__).parent/'reference/store_locations.json').read_text(encoding='utf-8'))
    selected=recovery_scope(state,locations)
    # Keep the original interruption/failure evidence intact.
    report=path.with_name('recovery_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    outcome={'original_manifest':str(path),'status':'running'}
    try:
        outcome['ingestion']=ingest_manifest(path)
        outcome['checks']=check_run(state,selected)
        outcome['status']='complete' if outcome['checks']['status']=='passed' else 'partial_recovery'
    except Exception as error:
        outcome['status']='failed';outcome['error']=str(error)
        raise
    finally:
        report.write_text(json.dumps(outcome,ensure_ascii=False,indent=2),encoding='utf-8')
        print('RECOVERY',report,flush=True)
        print('RECOVERY STATUS',outcome['status'],flush=True)
    if outcome['status']!='complete':
        print('Uploaded stores recovered, but the original daily collection is incomplete.',flush=True)
        raise SystemExit(1)
