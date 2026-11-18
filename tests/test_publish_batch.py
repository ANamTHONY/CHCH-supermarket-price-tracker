import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from databricks.sdk.errors import NotFound
from publish_batch import publish


class PublicationTests(unittest.TestCase):
    def state(self):
        return {'mode':'production','status':'collected','run_id':'production_20261102T014143Z_800c2386',
                'collected_date':'2026-11-02','expected_stores':1,'results':[
                    {'source':'woolworths','store_id':'001','store_name':'Example','status':'uploaded',
                     'rows':3,'category_counts':{'Egg':1,'Milk':1,'Meat':1},
                     'remote_file':'/Volumes/workspace/default/price_tracker/prices_woolworths_test.csv'}]}

    def test_no_ready_marker_if_remote_file_is_missing(self):
        client=Mock();client.files.get_metadata.side_effect=NotFound('missing')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'manifest.json';path.write_text(json.dumps(self.state()))
            with patch('publish_batch.volume_path',return_value='/Volumes/workspace/default/price_tracker'),patch('databricks.sdk.WorkspaceClient',return_value=client):
                with self.assertRaises(NotFound):publish(path)
        client.files.upload.assert_not_called()

    def test_publish_after_remote_check_and_never_overwrite_marker(self):
        client=Mock();client.files.download.side_effect=NotFound('no marker')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'manifest.json';path.write_text(json.dumps(self.state()))
            with patch('publish_batch.volume_path',return_value='/Volumes/workspace/default/price_tracker'),patch('databricks.sdk.WorkspaceClient',return_value=client):
                publish(path)
        client.files.get_metadata.assert_called_once()
        self.assertFalse(client.files.upload.call_args.kwargs['overwrite'])
        self.assertLess([x[0] for x in client.mock_calls].index('files.get_metadata'),[x[0] for x in client.mock_calls].index('files.upload'))
