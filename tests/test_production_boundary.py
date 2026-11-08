import json
from pathlib import Path
import tempfile
import unittest
from ingest_prices import ingest_manifest
from product_model import FACT_REFRESH
from silver_rules import CLEAN_DDL

class ProductionBoundaryTests(unittest.TestCase):
    def test_old_manifest_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'manifest.json'
            path.write_text(json.dumps({'mode':'production','collected_date':'2026-10-26','results':[]}),encoding='utf-8')
            with self.assertRaises(ValueError):ingest_manifest(path)

    def test_fact_refresh_excludes_test_history(self):
        self.assertIn("FROM workspace.default.bronze_prices WHERE collected_date >= DATE '2026-10-27'",CLEAN_DDL)
        self.assertIn("WHERE collected_date >= DATE '2026-10-27'",FACT_REFRESH)

if __name__=='__main__':unittest.main()
