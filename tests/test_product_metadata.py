import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import price_storage as ps
from product_model import normalize_name,normalize_spec

class MetadataAndMatching(unittest.TestCase):
    def test_metadata_keeps_legacy_columns_and_leading_zero(self):
        with TemporaryDirectory() as d,patch.object(ps,'DATA_DIR',Path(d)),patch.object(ps,'volume_path',return_value='/Volumes/test/default/raw'),patch('databricks.sdk.WorkspaceClient'):
            with ps.PriceSink('newworld') as sink:
                sink.write((None,'001',1,'8.49','10pk','ea','0.85','Eggs','2026-10-26',0),source_product_id='product-5023573-EA-000',store_verified=True)
            with sink.path.open(encoding='utf-8',newline='') as stream:row=next(csv.DictReader(stream))
            self.assertEqual(row['store_id'],'001')
            self.assertEqual(row['source'],'newworld')
            self.assertEqual(row['source_product_id'],'product-5023573-EA-000')
            self.assertEqual(row['store_verified'],'True')
            self.assertEqual(row['member_price'],'')
    def test_normalization_preserves_pack_size_and_farming_grade(self):
        self.assertEqual(normalize_spec('12 Pack'),normalize_spec('12pk'))
        self.assertNotEqual(normalize_spec('12pk'),normalize_spec('18pk'))
        self.assertNotEqual(normalize_name('Size 6 Barn Eggs'),normalize_name('Size 7 Barn Eggs'))
        self.assertNotEqual(normalize_name('Free Range Eggs'),normalize_name('Barn Eggs'))
    def test_only_case_and_whitespace_are_removed_from_names(self):
        self.assertEqual(normalize_name('  Meadow  Fresh Milk '),'meadow fresh milk')
        self.assertNotEqual(normalize_name('Original Milk'),normalize_name('Calci-Trim Milk'))

if __name__=='__main__':unittest.main()
