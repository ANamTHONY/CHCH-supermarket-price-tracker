"""Collect all three brands, then ingest today into Databricks."""
from pathlib import Path
import os


def run(action=None):
    # An OS-held lock is automatically released even if the process crashes.
    if os.name == 'nt':
        import msvcrt
    else:
        import fcntl
    lock_path = Path(__file__).resolve().parent / 'data' / 'daily_run.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit('Another daily run is active. Wait for it to finish.')
        try:
            if action is None:
                from production_runner import main
                main()
            else:
                action()
        finally:
            lock.seek(0)
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

if __name__ == "__main__":
    run()
