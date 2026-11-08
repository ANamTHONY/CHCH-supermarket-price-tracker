import copy
import unittest
from batch_protocol import validate_batch,latest_files,digest

V='/Volumes/workspace/default/price_tracker'
def batch(run='production_20261102T014143Z_800c2386'):
    return {'protocol_version':1,'mode':'production','run_id':run,'collected_date':'2026-11-02',
            'files':[{'source':'woolworths','store_id':'001','rows':3,
                      'category_counts':{'Egg':1,'Milk':1,'Meat':1},
                      'remote_file':V+'/prices_woolworths_test.csv'}]}

class BatchProtocolTests(unittest.TestCase):
    def test_valid_and_stable_hash(self):
        b=batch();self.assertIs(validate_batch(b,V),b)
        self.assertEqual(digest(b),digest(copy.deepcopy(b)))
    def test_test_run_not_ingested(self):
        b=batch();b['mode']='test'
        with self.assertRaises(ValueError):validate_batch(b,V)
    def test_duplicates_rejected(self):
        b=batch();b['files']*=2
        with self.assertRaises(ValueError):validate_batch(b,V)
    def test_paths_outside_volume_rejected(self):
        b=batch();b['files'][0]['remote_file']='/Volumes/other/default/price_tracker/prices_woolworths_test.csv'
        with self.assertRaises(ValueError):validate_batch(b,V)
    def test_old_batch_cannot_replace_newer_batch(self):
        old=batch();new=batch('production_20261102T054143Z_800c2387')
        for order in ([old,new],[new,old]):
            self.assertEqual(latest_files(order)[('woolworths','001','2026-11-02')][0],new['run_id'])
    def test_prior_dates_are_not_discarded(self):
        old=batch();new=batch('production_20261103T054143Z_800c2387');new['collected_date']='2026-11-03'
        self.assertEqual(len(latest_files([old,new])),2)
