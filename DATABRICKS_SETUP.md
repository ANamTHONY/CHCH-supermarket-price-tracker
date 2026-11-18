# Databricks raw price uploads

The three pipelines save UTF-8 CSV files under `data/`, then upload them to an
existing Unity Catalog Volume. Each run has a unique name including the store
chain and UTC timestamp. Columns retain the previous ten price fields, with an
additional `source` column. Missing values are empty CSV cells. These are raw
files, not Delta tables; downstream notebook processing is separate.

Install dependencies using the same Python environment as the pipelines:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configure authentication locally (never commit tokens). If Databricks CLI is
installed, use `databricks auth login --host https://YOUR-WORKSPACE`.
Alternatively, set `DATABRICKS_HOST` and `DATABRICKS_TOKEN` through your IDE's
local run configuration or local environment. The SDK also reads
`%USERPROFILE%\.databrickscfg`.

Set the existing destination Volume in the same terminal or IDE run environment:

This computer uses `/Volumes/workspace/default/price_tracker`, saved in the
Windows user environment as `DATABRICKS_VOLUME_PATH`. On Windows the scripts
also read missing Databricks settings from the user environment, so an IDE
opened before those settings were saved can still use them. Explicit process
settings take precedence.

```powershell
$env:DATABRICKS_VOLUME_PATH = '/Volumes/CATALOG/SCHEMA/VOLUME'
.\.venv\Scripts\python.exe pipeline_countdown.py
```

The identity needs permission to read the destination directory and write files.
Pipelines validate destination access before starting Chrome. For a subdirectory,
create it first or use the Volume root.

Local CSV rows are flushed after each product. On normal completion or a Python
exception, nonempty output is uploaded; a failed run can therefore leave a partial
CSV. Forced process termination or a power loss may prevent upload; the local
file remains available. Retry upload without scraping again:

```powershell
.\.venv\Scripts\python.exe price_storage.py 'D:\python\price-tracker\data\EXISTING_FILE.csv'
```

Retry overwrites the same remote filename. Independent scraping runs create
different files; downstream processing should handle duplicate observations.
