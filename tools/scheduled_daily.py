"""Windows daily collection with an unattended, cancellable return to hibernation."""
import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import ctypes
from datetime import datetime, time as daytime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NZ = ZoneInfo('Pacific/Auckland')


def last_input():
    class Info(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_uint), ('dwTime', ctypes.c_uint)]
    info = Info()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise ctypes.WinError()
    tick = ctypes.windll.kernel32.GetTickCount()
    return info.dwTime, ((tick - info.dwTime) & 0xffffffff) / 1000


@contextmanager
def keep_awake():
    kernel = ctypes.windll.kernel32
    kernel.SetThreadExecutionState.argtypes = [ctypes.c_uint]
    kernel.SetThreadExecutionState.restype = ctypes.c_uint
    if not kernel.SetThreadExecutionState(0x80000001):
        raise ctypes.WinError()
    try:
        yield
    finally:
        kernel.SetThreadExecutionState(0x80000000)


def completed(state, expected, day):
    results = state.get('results', [])
    keys = {(r.get('source'), r.get('store_id')) for r in results}
    return (state.get('collected_date') == day and state.get('mode') == 'production'
            and state.get('status') == 'complete'
            and state.get('cloud_processing') == 'succeeded'
            and state.get('expected_stores') == len(expected)
            and len(results) == len(expected) and keys == expected
            and all(r.get('status') == 'uploaded' and r.get('rows', 0) > 0
                    and all(r.get('category_counts', {}).get(c, 0) > 0 for c in ('Egg', 'Milk', 'Meat'))
                    for r in results))


def previous_success(day):
    stores = json.loads((ROOT/'reference/store_locations.json').read_text(encoding='utf-8'))
    expected = {(s['source'], s['store_id']) for s in stores if s.get('is_christchurch_urban') is True}
    for path in sorted((ROOT/'data').glob('production_*/manifest.json'), reverse=True):
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            continue
        if completed(state, expected, day):
            return path
    return None


def hibernate_allowed(success, initial_idle, initial_input, current_input):
    return success and initial_idle >= 600 and initial_input == current_input


def write_state(path, state):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def hibernate_after(path):
    """Separate helper allows the scheduled task and collection lock to finish first."""
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('status') not in ('complete', 'already_complete'):
        return 1
    if not hibernate_allowed(True, state['initial_idle_seconds'], state['initial_input'], last_input()[0]):
        state['hibernate'] = 'skipped_user_active'
        write_state(path, state)
        return 0
    with keep_awake():
        # Any keyboard or mouse input during the grace period cancels hibernation.
        for _ in range(24):
            time.sleep(5)
            if last_input()[0] != state['initial_input']:
                state['hibernate'] = 'cancelled_user_active'
                write_state(path, state)
                return 0
        # Do not sleep over another entry point's active collection.
        import msvcrt
        lock_path = ROOT/'data/daily_run.lock'
        with lock_path.open('a+b') as lock:
            if lock.tell() == 0:
                lock.write(b'0'); lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                state['hibernate'] = 'skipped_other_collection_active'
                write_state(path, state)
                return 0
            else:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        if last_input()[0] != state['initial_input']:
            state['hibernate'] = 'cancelled_user_active'
            write_state(path, state)
            return 0
        state['hibernate'] = 'requested'
        write_state(path, state)
        result = subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/shutdown.exe'), '/h'],
                                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            state['hibernate'] = 'failed'
            state['hibernate_error'] = result.stderr.strip() or result.stdout.strip()
            write_state(path, state)
        return result.returncode


def wait_for_network():
    from price_storage import load_user_environment
    load_user_environment()
    from databricks.sdk import WorkspaceClient
    host = urlsplit(WorkspaceClient().config.host).hostname
    if not host:
        raise RuntimeError('Missing Databricks host')
    deadline = time.monotonic() + 180
    while True:
        try:
            with socket.create_connection((host, 443), timeout=10):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Network did not recover within three minutes') from None
            time.sleep(10)


def main(argv=None, on_result=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-hibernate', action='store_true', help='Keep the computer on after collection')
    parser.add_argument('--background', action='store_true', help='Batch session without desktop input tracking')
    parser.add_argument('--after', default='09:15')
    parser.add_argument('--hibernate-after', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.background and not args.no_hibernate:
        parser.error('--background requires --no-hibernate; use the separate guarded boot launcher for shutdown')
    if os.name != 'nt':
        raise RuntimeError('This entry point requires Windows')
    if args.hibernate_after:
        return hibernate_after(args.hibernate_after)
    now = datetime.now(NZ)
    folder = ROOT/'data/scheduled_runs'
    folder.mkdir(parents=True, exist_ok=True)
    tag = now.strftime('%Y%m%dT%H%M%S') + '_' + uuid4().hex[:8]
    status_path = folder/(tag+'.json')
    state = {'started_at': now.isoformat(), 'status': 'starting', 'hibernate': 'not_requested',
             'dry_run': args.dry_run, 'background': args.background, 'log': str(folder/(tag+'.log'))}
    with open(state['log'], 'w', encoding='utf-8', buffering=1) as log, redirect_stdout(log), redirect_stderr(log):
        try:
            state['initial_input'], state['initial_idle_seconds'] = (None,0) if args.background else last_input()
            print('SCHEDULED', now.isoformat(), 'idle seconds', state['initial_idle_seconds'])
            from run_pipelines import run
            def action():
                if args.dry_run:
                    from price_storage import volume_path, load_user_environment
                    load_user_environment()
                    from databricks.sdk import WorkspaceClient
                    WorkspaceClient().files.get_directory_metadata(volume_path())
                    state['status'] = 'dry_run_passed'
                    print('DRY RUN passed: session, lock and Databricks destination; no collection or hibernation')
                    return
                if now.time().replace(tzinfo=None) < daytime.fromisoformat(args.after):
                    state['status'] = 'before_schedule'
                    return
                with keep_awake():
                    wait_for_network()
                    path = previous_success(now.date().isoformat())
                    if path:
                        state['status'] = 'already_complete'
                    else:
                        from production_runner import main as collect
                        path = collect(argv=[])
                        if not previous_success(now.date().isoformat()):
                            raise RuntimeError('Full-day collection and cloud ingestion not confirmed')
                        state['status'] = 'complete'
                    state['manifest'] = str(path)
            run(action)
            if not args.dry_run and not args.no_hibernate and hibernate_allowed(state['status'] in ('complete', 'already_complete'),
                    state['initial_idle_seconds'], state['initial_input'], last_input()[0]):
                state['hibernate'] = 'grace_period_120_seconds'
                write_state(status_path, state)
                subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--hibernate-after', str(status_path)],
                    cwd=ROOT, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif state['status'] in ('complete', 'already_complete'):
                state['hibernate'] = 'disabled' if args.no_hibernate else 'skipped_user_active'
            write_state(status_path, state)
            if on_result:on_result(state,status_path)
            return 0
        except BaseException as error:
            state['status'] = 'failed'
            state['error_type'] = type(error).__name__
            state['error'] = str(error)
            traceback.print_exc()
            write_state(status_path, state)
            if on_result:on_result(state,status_path)
            return int(error.code) if isinstance(error, SystemExit) and isinstance(error.code, int) and error.code else 1


if __name__ == '__main__':
    raise SystemExit(main())
