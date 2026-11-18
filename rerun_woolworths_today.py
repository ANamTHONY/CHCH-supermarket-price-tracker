"""One-off reset and recollection for Woolworths on 2026-10-28 (NZ time)."""
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from run_pipelines import run

TARGET_DATE = '2026-10-28'
TABLES = ('bronze_prices', 'silver_fact_product_price')
ROOT = Path(__file__).resolve().parent


def require_target_day():
    today = datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat()
    if today != TARGET_DATE:
        raise RuntimeError(f'This temporary script is only for {TARGET_DATE}; NZ date is {today}. No deletion allowed.')


def reset_rows(db, backups, report, persist, date_check=require_target_day):
    """Finish and verify both backups before deleting either table's target rows."""
    predicate = f"source = 'woolworths' AND collected_date = DATE '{TARGET_DATE}'"
    for name in TABLES:
        date_check()
        table = 'workspace.default.' + name
        before = int(db.run(f'SELECT count(*) FROM {table} WHERE {predicate}')[0][0])
        untouched = int(db.run(f'SELECT count(*) FROM {table} WHERE NOT coalesce(({predicate}), false)')[0][0])
        db.run(f'CREATE TABLE {backups[name]} USING DELTA AS SELECT * FROM {table} WHERE {predicate}')
        saved = int(db.run(f'SELECT count(*) FROM {backups[name]}')[0][0])
        report['tables'][name] = {'backup_table': backups[name], 'before_rows': before,
                                 'backup_rows': saved, 'untouched_rows': untouched}
        persist()
        if saved != before:
            raise RuntimeError(f'Backup verification failed for {table}; nothing deleted')
    report['status'] = 'backed_up'
    persist()
    for name in TABLES:
        date_check()
        table = 'workspace.default.' + name
        report['status'] = 'deleting_' + name
        persist()
        db.run(f'DELETE FROM {table} WHERE {predicate}')
        remaining = int(db.run(f'SELECT count(*) FROM {table} WHERE {predicate}')[0][0])
        untouched = int(db.run(f'SELECT count(*) FROM {table} WHERE NOT coalesce(({predicate}), false)')[0][0])
        if remaining or untouched != report['tables'][name]['untouched_rows']:
            raise RuntimeError(f'Deletion scope verification failed for {table}; backups retained')
        report['tables'][name]['deleted_rows'] = report['tables'][name]['before_rows']
        persist()


def rebuild():
    require_target_day()
    from ingest_prices import SqlClient
    from production_runner import main

    job = 'ww_reset_20261028_' + uuid4().hex[:12]
    folder = ROOT / 'data' / job
    folder.mkdir(parents=True, exist_ok=False)
    report_path = folder / 'reset_report.json'
    report = {'date': TARGET_DATE, 'source': 'woolworths', 'status': 'starting', 'tables': {}}

    def persist():
        tmp = report_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(report_path)

    backups = {name: f'workspace.default._{job}_{name}' for name in TABLES}
    print('RESET: Woolworths only, NZ date', TARGET_DATE, flush=True)
    print('REPORT:', report_path, flush=True)
    persist()
    try:
        reset_rows(SqlClient(), backups, report, persist)
        require_target_day()
        report['status'] = 'collecting'
        persist()
        print('Today\'s Woolworths Bronze/Silver rows removed; starting fresh collection.', flush=True)
        manifest = main(argv=['--source', 'woolworths', '--workers', '1', '--retries', '0', '--ingest'])
        report['collection_manifest'] = str(manifest)
        report['status'] = 'complete'
    except BaseException as error:
        report['failed_phase'] = report['status']
        report['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        report['error'] = f'{type(error).__name__}: {error}'
        print('Not complete. Backups retained; see reset report and collection manifest.', flush=True)
        raise
    finally:
        persist()
        print('RESET RESULT:', report['status'], flush=True)


if __name__ == '__main__':
    run(rebuild)
