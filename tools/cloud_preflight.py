"""Check credentials and single-writer ingestion before opening any browser."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    required = ('DATABRICKS_HOST', 'DATABRICKS_TOKEN', 'DATABRICKS_VOLUME_PATH',
                'DATABRICKS_INGESTION_JOB_ID')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError('Missing cloud configuration: ' + ', '.join(missing))
    from databricks.sdk import WorkspaceClient
    from price_storage import volume_path
    client = WorkspaceClient()
    client.files.get_directory_metadata(volume_path())
    job = client.jobs.get(int(os.environ['DATABRICKS_INGESTION_JOB_ID']))
    if job.settings.max_concurrent_runs != 1:
        raise RuntimeError('Ingestion Job must have max_concurrent_runs=1')
    print('Cloud authentication, destination and single-writer Job verified')


if __name__ == '__main__':
    main()
