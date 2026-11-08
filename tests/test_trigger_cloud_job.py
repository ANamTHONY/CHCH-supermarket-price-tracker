import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock,patch
from trigger_cloud_job import trigger_batch


class CloudTriggerTests(unittest.TestCase):
    def client(self,ledger=None,outcome='SUCCESS'):
        client=Mock()
        client.config.host='https://example.databricks.com'
        client.jobs.get.return_value.settings.max_concurrent_runs=1
        client.jobs.run_now.return_value.run_id=123
        client.jobs.get_run.return_value=NS(state=NS(life_cycle_state='TERMINATED',result_state=outcome,state_message=''),
            tasks=[NS(task_key='ingest_ready_batches',run_id=456)])
        client.jobs.get_run_output.return_value=NS(notebook_output=NS(truncated=False,result=json.dumps({'ledger':ledger or []})))
        return client

    def test_success_requires_this_batch_and_submission_is_idempotent(self):
        c=self.client([{'run_id':'batch1','status':'SUCCEEDED','row_count':495}])
        updates=[]
        result=trigger_batch('batch1',updates.append,client=c,job_id=7)
        self.assertEqual(result['status'],'succeeded')
        self.assertEqual(updates[0]['status'],'submitted')
        token=c.jobs.run_now.call_args.kwargs['idempotency_token']
        self.assertTrue(c.jobs.run_now.call_args.kwargs['queue'].enabled)
        trigger_batch('batch1',updates.append,client=c,job_id=7)
        self.assertEqual(c.jobs.run_now.call_args.kwargs['idempotency_token'],token)

    def test_job_success_without_batch_does_not_claim_ingestion(self):
        c=self.client([{'run_id':'different_batch','status':'SUCCEEDED'}])
        self.assertEqual(trigger_batch('batch1',lambda _:None,client=c,job_id=7)['status'],'unverified')

    def test_failed_job_not_reported_as_success(self):
        c=self.client(outcome='FAILED')
        self.assertEqual(trigger_batch('batch1',lambda _:None,client=c,job_id=7)['status'],'failed')
        c.jobs.get_run_output.assert_not_called()

    def test_timeout_does_not_cancel_cloud_job(self):
        c=self.client()
        c.jobs.get_run.return_value=NS(state=NS(life_cycle_state='QUEUED',result_state=None))
        self.assertEqual(trigger_batch('batch1',lambda _:None,client=c,job_id=7,timeout=0)['status'],'pending')
        c.jobs.cancel_run.assert_not_called()

    def test_parallel_writer_config_rejected(self):
        c=self.client();c.jobs.get.return_value.settings.max_concurrent_runs=2
        with self.assertRaises(RuntimeError):trigger_batch('batch1',lambda _:None,client=c,job_id=7)
        c.jobs.run_now.assert_not_called()
