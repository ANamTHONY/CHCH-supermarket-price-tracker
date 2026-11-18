"""Persist raw prices locally and upload completed or partial runs to a UC Volume."""
import argparse
import csv
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

FIELDS = (
    "product_id", "store_id", "category_id", "total_price", "total_quant",
    "unit", "unit_price", "original_name", "collected_date", "is_promo",
)
EXTRA_FIELDS = ("source_product_id", "product_url", "member_price", "member_unit_price", "was_price", "store_verified")
DATA_DIR = Path(__file__).resolve().parent / "data"


def load_user_environment():
    """Pick up Windows user settings added after the IDE was started."""
    if os.name != "nt":
        return
    import winreg
    names = (
        "DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE",
        "DATABRICKS_VOLUME_PATH", "DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
    )
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name in names:
            if name not in os.environ:
                try:
                    value, _ = winreg.QueryValueEx(key, name)
                except FileNotFoundError:
                    continue
                os.environ[name] = value


def volume_path():
    load_user_environment()
    path = os.environ.get("DATABRICKS_VOLUME_PATH", "").rstrip("/")
    parts = path.split("/")
    if len(parts) < 5 or parts[:2] != ["", "Volumes"] or any(
        part in ("", ".", "..") for part in parts[2:]
    ):
        raise ValueError("Set DATABRICKS_VOLUME_PATH=/Volumes/<catalog>/<schema>/<volume>[/folder]")
    return path


def upload_csv(local_path, client=None):
    """Retry an existing file using the same remote name, without duplicating it."""
    target = volume_path()
    if client is None:
        from databricks.sdk import WorkspaceClient
        client = WorkspaceClient()
    client.files.create_directory(target)
    remote = f"{target}/{Path(local_path).name}"
    with Path(local_path).open("rb") as stream:
        client.files.upload(remote, stream, overwrite=True)
    print(f"Databricks upload complete: {remote}")
    return remote


class PriceSink:
    def __init__(self, source, *, upload_on_error=True):
        self.source = source
        self.upload_on_error = upload_on_error
        self.rows = 0

    def __enter__(self):
        # Fail before scraping when destination/authentication is missing.
        volume_path()
        from databricks.sdk import WorkspaceClient
        self.client = WorkspaceClient()
        self.client.files.get_directory_metadata(volume_path())
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S%fZ")
        self.path = DATA_DIR / f"prices_{self.source}_{stamp}_{uuid4().hex[:8]}.csv"
        self.file = self.path.open("x", encoding="utf-8", newline="")
        self.writer = csv.writer(self.file)
        self.writer.writerow((*FIELDS, "source", *EXTRA_FIELDS))
        self.file.flush()
        print(f"Local CSV: {self.path}")
        return self

    def write(self, values, **metadata):
        if len(values) != len(FIELDS):
            raise ValueError(f"Expected {len(FIELDS)} price fields")
        if set(metadata) - set(EXTRA_FIELDS):
            raise ValueError(f"Unknown price metadata: {set(metadata) - set(EXTRA_FIELDS)}")
        self.writer.writerow((*values, self.source, *(metadata.get(field) for field in EXTRA_FIELDS)))
        self.file.flush()
        self.rows += 1

    def __exit__(self, exc_type, exc, traceback):
        self.file.close()
        if exc is not None and not self.upload_on_error:
            print(f"Incomplete run retained locally; no production upload: {self.path}")
            return False
        if self.rows:
            try:
                upload_csv(self.path, self.client)
            except Exception as upload_error:
                print(f"Upload failed; {self.rows} rows retained in {self.path}. "
                      f"Retry: python price_storage.py \"{self.path}\"")
                if exc is None:
                    raise
                raise upload_error from exc
        else:
            print("No prices collected; no file uploaded.")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload an existing prices CSV to Databricks")
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    upload_csv(args.csv)
