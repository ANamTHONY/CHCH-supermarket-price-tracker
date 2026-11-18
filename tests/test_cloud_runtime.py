import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import run_pipelines
from trigger_cloud_job import trigger_batch


class CloudRuntimeTests(unittest.TestCase):
    def test_posix_lock_releases_when_collection_fails(self):
        fake = SimpleNamespace(flock=Mock(), LOCK_EX=2, LOCK_NB=4, LOCK_UN=8)
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'run_pipelines.py'
            with patch.object(run_pipelines, '__file__', str(script)), \
                 patch.object(run_pipelines, 'os', SimpleNamespace(name='posix')), \
                 patch.dict(sys.modules, {'fcntl': fake}):
                with self.assertRaisesRegex(RuntimeError, 'collector failed'):
                    run_pipelines.run(lambda: (_ for _ in ()).throw(RuntimeError('collector failed')))
            self.assertEqual(fake.flock.call_count, 2)
            self.assertEqual(fake.flock.call_args_list[0].args[1], 6)
            self.assertEqual(fake.flock.call_args_list[1].args[1], 8)

    def test_job_id_environment_avoids_local_deployment_file(self):
        client = Mock()
        client.jobs.get.return_value.settings.max_concurrent_runs = 2
        with patch.dict(os.environ, {'DATABRICKS_INGESTION_JOB_ID': '12345'}), \
             patch('trigger_cloud_job.Path.read_text', side_effect=AssertionError('local file unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'max_concurrent_runs'):
                trigger_batch('batch', lambda _: None, client=client)
        client.jobs.get.assert_called_once_with(12345)
