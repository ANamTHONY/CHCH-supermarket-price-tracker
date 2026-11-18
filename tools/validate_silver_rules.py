"""Exercise the real Databricks SQL cleaner on synthetic read-only inputs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ingest_prices import SqlClient
from product_model import sql_string
from silver_rules import CLEAN_DDL

cases=[
 ('carton','Meadow Fresh Calci Trim Milk 1L Carton','NA','l','3.90',None,'2026-10-27','1l','l','3.900000',None,'parsed_from_name'),
 ('bottle','Meadow Fresh Milk Standard Original 2L Bottle','NA','l','3.20','2.90','2026-10-27','2l','l','3.200000','2.900000','parsed_from_name'),
 ('eggs','Farmer Brown Eggs Barn Size 7 12 Pack','NA','ea','0.80',None,'2026-10-27','12pk','ea','0.800000',None,'parsed_from_name'),
 ('estimate','Meat Min Order 800g','800g','kg$17.00 / 1ea (approx)','21.25',None,'2026-10-27',None,'kg','21.250000',None,'variable_weight'),
 ('range','Lamb 0.17-0.55kg','0.55kg','kg','29.99',None,'2026-10-27',None,'kg','29.990000',None,'variable_weight'),
 ('hundred','Powder 400g','400g','100g','1.35','1.20','2026-10-27','400g','kg','13.500000','12.000000','reported'),
 ('unknown','Meat','kg','100','52.65',None,'2026-10-27','kg',None,None,None,'reported'),
 ('missing','Milk 1L Bottle','NA','l',None,None,'2026-10-27','1l','l',None,None,'parsed_from_name'),
 ('historic','Milk 1L Bottle','NA','l','3.00',None,'2026-10-26','1l','l','3.000000',None,'parsed_from_name'),
]
values=','.join('('+','.join(sql_string(v) for v in r[:7])+')' for r in cases)
source=f'(SELECT * FROM VALUES {values} AS fixture(test_id,original_name,total_quant,unit,unit_price,member_unit_price,collected_date))'
query=CLEAN_DDL[CLEAN_DDL.index('WITH parsed'):].replace('workspace.default.bronze_prices',source)
rows=SqlClient().run('SELECT test_id,total_quant,normalized_unit,cast(normalized_unit_price AS STRING),cast(normalized_member_unit_price AS STRING),specification_quality_status FROM ('+query+') ORDER BY test_id')
actual={r[0]:r[1:] for r in rows}
expected={r[0]:list(r[7:]) for r in cases if r[6]>='2026-10-27'}
assert actual==expected,(actual,expected)
print('PASS: 9 SQL fixtures; bottle/carton suffix, egg grade, variable/range weight, 100g conversion, unknown units, NULL and production date boundary')
