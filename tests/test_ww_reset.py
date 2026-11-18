import unittest
from rerun_woolworths_today import reset_rows, TABLES


class FakeDb:
    def __init__(self, bad_backup=False):
        self.sql=[]
        self.bad_backup=bad_backup
        self.deleted=set()

    def run(self, sql):
        self.sql.append(sql)
        if sql.startswith('DELETE'):
            self.deleted.add(sql.split()[2])
        if not sql.startswith('SELECT'):
            return []
        if 'WHERE NOT coalesce' in sql:return [['8404']]
        if 'backup_' in sql:return [['895' if self.bad_backup else '896']]
        table=sql.split('FROM ')[1].split()[0]
        return [['0' if table in self.deleted else '896']]


class ResetTests(unittest.TestCase):
    def test_backup_mismatch_prevents_all_deletes(self):
        db=FakeDb(bad_backup=True)
        with self.assertRaises(RuntimeError):
            reset_rows(db,{n:'backup_'+n for n in TABLES},{'tables':{}},lambda:None,lambda:None)
        self.assertFalse(db.deleted)

    def test_both_backups_precede_scoped_deletes(self):
        db=FakeDb()
        report={'tables':{}}
        reset_rows(db,{n:'backup_'+n for n in TABLES},report,lambda:None,lambda:None)
        creates=[i for i,s in enumerate(db.sql) if s.startswith('CREATE')]
        deletes=[i for i,s in enumerate(db.sql) if s.startswith('DELETE')]
        self.assertEqual(len(creates),2)
        self.assertEqual(len(deletes),2)
        self.assertLess(max(creates),min(deletes))
        for i in deletes:
            self.assertIn("source = 'woolworths' AND collected_date = DATE '2026-10-28'",db.sql[i])

    def test_date_guard_prevents_sql(self):
        db=FakeDb()
        def expired():raise RuntimeError('Wrong day')
        with self.assertRaises(RuntimeError):
            reset_rows(db,{}, {'tables':{}},lambda:None,expired)
        self.assertEqual(db.sql,[])
