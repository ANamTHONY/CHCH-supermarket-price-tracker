"""Unattended startup collection; power-off is gated on verified BIOS setup."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def desktop_user_present():
    """Treat any active or disconnected signed-in desktop as in use; errors fail safe."""
    class Session(ctypes.Structure):
        _fields_=[('id',wintypes.DWORD),('station',wintypes.LPWSTR),('state',ctypes.c_int)]
    wts=ctypes.WinDLL('wtsapi32',use_last_error=True)
    wts.WTSEnumerateSessionsW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Session)),ctypes.POINTER(wintypes.DWORD)]
    wts.WTSEnumerateSessionsW.restype=wintypes.BOOL
    wts.WTSQuerySessionInformationW.argtypes=[wintypes.HANDLE,wintypes.DWORD,ctypes.c_int,
        ctypes.POINTER(wintypes.LPWSTR),ctypes.POINTER(wintypes.DWORD)]
    wts.WTSQuerySessionInformationW.restype=wintypes.BOOL
    wts.WTSFreeMemory.argtypes=[ctypes.c_void_p]
    sessions=ctypes.POINTER(Session)();count=wintypes.DWORD()
    if not wts.WTSEnumerateSessionsW(None,0,1,ctypes.byref(sessions),ctypes.byref(count)):
        return True
    try:
        for i in range(count.value):
            if sessions[i].id==0:continue
            username=wintypes.LPWSTR();size=wintypes.DWORD()
            if not wts.WTSQuerySessionInformationW(None,sessions[i].id,5,ctypes.byref(username),ctypes.byref(size)):
                return True
            try:
                if username.value:return True
            finally:
                wts.WTSFreeMemory(username)
        return False
    finally:
        wts.WTSFreeMemory(sessions)


def shutdown_allowed(state,bios_ready,user_present):
    return (bios_ready and not user_present and not state.get('dry_run',False)
            and state.get('status') in ('complete','already_complete'))


def save(path,state):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def bios_ready():
    path=ROOT/'data/boot_power_enabled.json'
    try:return json.loads(path.read_text(encoding='utf-8')).get('bios_wake_verified') is True
    except (ValueError,OSError):return False


def finish_shutdown(path):
    state=json.loads(path.read_text(encoding='utf-8'))
    from tools.scheduled_daily import keep_awake
    with keep_awake():
        for _ in range(24):
            time.sleep(5)
            if not shutdown_allowed(state,bios_ready(),desktop_user_present()):
                state['power']='cancelled';save(path,state);return 0
        import msvcrt
        with (ROOT/'data/daily_run.lock').open('a+b') as lock:
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                state['power']='skipped_other_collection';save(path,state);return 0
            else:
                lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
        if not shutdown_allowed(state,bios_ready(),desktop_user_present()):
            state['power']='cancelled';save(path,state);return 0
        state['power']='shutdown_requested';save(path,state)
        # No /f: applications are not forcibly closed.
        result=subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/shutdown.exe'),'/s','/t','0'],
            capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            state['power']='shutdown_failed';state['error']=result.stderr.strip();save(path,state)
        return result.returncode


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--finish-shutdown',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    if args.finish_shutdown:return finish_shutdown(args.finish_shutdown)
    os.environ['PRICE_TRACKER_HEADLESS']='0'
    initial_user=desktop_user_present()
    outcome={}
    from tools.scheduled_daily import main as daily
    def record(state,path):outcome.update(state,schedule_result=str(path))
    options=['--background','--no-hibernate']+(['--dry-run'] if args.dry_run else [])
    code=daily(options,on_result=record)
    folder=ROOT/'data/boot_runs';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(datetime.now().strftime('%Y%m%dT%H%M%S')+'_'+uuid4().hex[:8]+'.json')
    outcome['desktop_user_at_start']=initial_user
    if shutdown_allowed(outcome,bios_ready(),initial_user or desktop_user_present()):
        outcome['power']='shutdown_grace_120_seconds'
        save(path,outcome)
        subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--finish-shutdown',str(path)],cwd=ROOT,
            creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        outcome['power']='disabled_or_desktop_in_use'
        save(path,outcome)
    return code


if __name__=='__main__':raise SystemExit(main())
