import unittest
from unittest.mock import Mock
from ingest_prices import SqlClient


class SqlReadinessTests(unittest.TestCase):
    def test_ready_requires_successful_query(self):
        db=SqlClient.__new__(SqlClient)
        db.run=Mock(return_value=[['1']])
        db.check_ready()
        db.run.assert_called_once_with('SELECT 1')

    def test_unexpected_response_fails(self):
        db=SqlClient.__new__(SqlClient)
        db.run=Mock(return_value=[])
        with self.assertRaises(RuntimeError):db.check_ready()

    def test_submission_error_does_not_retry_write(self):
        db=SqlClient.__new__(SqlClient)
        db.warehouse='test'
        db.client=Mock()
        execute=db.client.statement_execution.execute_statement
        execute.side_effect=RuntimeError('warehouse unavailable')
        with self.assertRaisesRegex(RuntimeError,'recover the manifest'):
            db.run('DELETE FROM example WHERE false')
        self.assertEqual(execute.call_count,1)
