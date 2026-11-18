# Production setup

Use the README's offline tests before configuring any live services.

## Databricks

Create or choose a Unity Catalog Volume and grant the execution identity access
to it and to the target tables. Configure SDK authentication locally, using a
Databricks profile or environment variables. Never commit a populated `.env`
file, token, or `.databrickscfg`.

Required configuration for the collector:

| Variable | Purpose |
| --- | --- |
| `DATABRICKS_HOST` | Your workspace URL |
| `DATABRICKS_TOKEN` | Local SDK authentication, if using a personal access token |
| `DATABRICKS_VOLUME_PATH` | `/Volumes/<catalog>/<schema>/<volume>` |
| `DATABRICKS_INGESTION_JOB_ID` | The deployed single-writer ingestion Job |

Inspect the deployment scripts and target catalogue/schema before deploying:

- `tools/build_cloud_ingestion.py` generates the ingestion notebook.
- `tools/deploy_cloud_ingestion.py` deploys the notebook and ingestion Job.
- `tools/build_price_model.py` / `tools/deploy_price_model.py` prepare the model.
- `tools/build_product_analysis.py` / `tools/deploy_product_analysis.py` prepare
  the curated analysis layer.

The supplied SQL and deployment code use `workspace.default`; adapt those targets
to your environment before running them. Deployment creates or updates cloud
resources and tables; it is not part of the offline quickstart.

After deployment, start the full pipeline with:

```powershell
.\.venv\Scripts\python.exe run_pipelines.py
```

Review the generated `data/production_*/manifest.json`, the Databricks Job result
and batch ingestion ledger. Exit code 2 means cloud processing was not confirmed;
already uploaded files may still be safe. Investigate the batch before recollecting.

## Scheduling

The current working installation uses Windows Task Scheduler to launch
`tools/boot_daily.py` at 09:15 in New Zealand time. BIOS power-on is configured
separately on that computer. Task credentials, machine paths, and power-management
settings are machine-specific and are not exported as ready-to-import task XML.

`tools/install_daily_task.ps1` documents an earlier interactive-user scheduling
option; it requires a signed-in user. Do not run it over an existing background
task without reviewing the selected logon mode. A collector does not need an
automatic shutdown rule to function.

The Databricks Job processes published batches as a single writer. Its daily
fallback schedule can process batches whose immediate job submission failed.

## Cloud collection experiment

The GitHub Actions cloud browser probe did not pass retailer access/store-selection
checks. The production GitHub collection workflow is therefore gated by
`CLOUD_COLLECTION_ENABLED`; leave it unset or false. The ordinary test workflow
requires no production secrets and performs no production uploads.

See `CLOUD_COLLECTION.md` for the experimental configuration. This is distinct
from the working Databricks cloud ingestion deployment.
