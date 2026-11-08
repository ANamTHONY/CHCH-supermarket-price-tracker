import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import price_storage as ps

class IncompleteRun(unittest.TestCase):
    def test_woolworths_partial_run_stays_local_without_upload(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(ps,'DATA_DIR',Path(temp)), patch.object(ps,'volume_path',return_value='/Volumes/test/default/raw'), patch('databricks.sdk.WorkspaceClient') as client:
            with self.assertRaisesRegex(RuntimeError,'store verification failed'):
                with ps.PriceSink('woolworths',upload_on_error=False) as sink:
                    sink.write((None,'001',1,'15.69','20pk','ea','0.78','Eggs','2026-10-26',1))
                    raise RuntimeError('store verification failed')
            client.return_value.files.upload.assert_not_called()
            self.assertTrue(sink.path.exists())
            with sink.path.open(encoding='utf-8',newline='') as stream:
                self.assertEqual(len(list(csv.DictReader(stream))),1)

if __name__=='__main__':unittest.main()
