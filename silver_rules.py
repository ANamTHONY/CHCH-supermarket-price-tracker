"""SQL rules for conservative normalization; Bronze values are never updated."""

CLEAN_DDL = r'''CREATE OR REPLACE VIEW workspace.default.silver_v_prices_clean AS
WITH parsed AS (
 SELECT *,
 lower(regexp_replace(trim(coalesce(total_quant,'')), '\\s+', '')) raw_spec_key,
 lower(trim(coalesce(unit,''))) raw_unit_key,
 nullif(regexp_extract(lower(original_name), '(\\d+(?:\\.\\d+)?\\s*(?:ml|kg|pack|pk|g|l|ea))(?:\\s+(?:bottle|carton))?\\s*$',1),'') name_spec,
 lower(original_name) RLIKE '(min\\s+order|\\d+(?:\\.\\d+)?\\s*[-–]\\s*\\d+(?:\\.\\d+)?\\s*(kg|g))' variable_weight
 FROM workspace.default.bronze_prices WHERE collected_date >= DATE '2026-10-27'
), normalized AS (
 SELECT *,
 CASE WHEN variable_weight THEN NULL
 WHEN raw_spec_key RLIKE '^(\\d+(\\.\\d+)?(ml|l|g|kg|pk|pack|ea)|kg|ea)$'
 THEN replace(raw_spec_key,'pack','pk')
 ELSE replace(regexp_replace(name_spec,'\\s+',''),'pack','pk') END clean_spec,
 CASE WHEN raw_unit_key RLIKE '^kg\\s*\\$' THEN 'kg'
 WHEN raw_unit_key IN ('kg','l','ea','100g','100ml') THEN raw_unit_key END clean_unit
 FROM parsed
)
SELECT * EXCEPT(total_quant,unit,raw_spec_key,raw_unit_key,name_spec,variable_weight,clean_spec,clean_unit),
 total_quant raw_specification,unit raw_reported_unit,
 clean_spec total_quant,clean_unit unit,
 CASE WHEN variable_weight THEN 'variable_weight' WHEN clean_spec IS NULL THEN 'unknown'
 WHEN raw_spec_key IN ('','na') THEN 'parsed_from_name' ELSE 'reported' END specification_quality_status,
 CASE WHEN clean_unit IS NULL THEN 'unknown' ELSE 'ok' END unit_quality_status,
 CASE WHEN clean_unit IN ('kg','100g') THEN 'kg' WHEN clean_unit IN ('l','100ml') THEN 'l'
 WHEN clean_unit='ea' THEN 'ea' END normalized_unit,
 CASE WHEN clean_unit IS NOT NULL AND try_cast(unit_price AS DECIMAL(16,6))>0
 THEN try_cast(unit_price AS DECIMAL(16,6))*CASE WHEN clean_unit IN ('100g','100ml') THEN 10 ELSE 1 END END normalized_unit_price,
 CASE WHEN clean_unit IS NOT NULL AND try_cast(member_unit_price AS DECIMAL(16,6))>0
 THEN try_cast(member_unit_price AS DECIMAL(16,6))*CASE WHEN clean_unit IN ('100g','100ml') THEN 10 ELSE 1 END END normalized_member_unit_price
FROM normalized'''

SILVER_COLUMNS = {
 'raw_specification':'STRING','raw_reported_unit':'STRING',
 'specification_quality_status':'STRING','unit_quality_status':'STRING',
 'normalized_unit':'STRING','normalized_unit_price':'DECIMAL(16,6)',
 'normalized_member_unit_price':'DECIMAL(16,6)',
}

PENDING_VIEW = '''CREATE OR REPLACE VIEW workspace.default.silver_v_product_mapping_queue AS
SELECT f.source,f.source_product_id,f.category_id,max(f.original_name) original_name,
 max(f.original_specification) normalized_specification,max(f.raw_specification) raw_specification,
 max(f.product_url) product_url,max(s.mapping_status) registry_status,max(s.mapping_note) review_note,
 count(*) observations,count(DISTINCT f.store_key) stores,min(f.collected_date) first_seen,max(f.collected_date) last_seen
FROM workspace.default.silver_fact_product_price f
LEFT JOIN workspace.default.silver_dim_product_source s ON f.source=s.source AND f.source_product_id=s.source_product_id
WHERE f.product_id IS NULL GROUP BY f.source,f.source_product_id,f.category_id'''

QUALITY_VIEW = '''CREATE OR REPLACE VIEW workspace.default.silver_v_price_quality AS
SELECT collected_date,source,category_id,count(*) observations,count(DISTINCT store_key) stores,
 count_if(product_id IS NULL) unmapped,count_if(price_quality_status<>'ok') invalid_price,
 count_if(unit_quality_status<>'ok') unknown_unit,count_if(specification_quality_status='unknown') unknown_specification,
 count_if(specification_quality_status='variable_weight') variable_weight
FROM workspace.default.silver_fact_product_price GROUP BY collected_date,source,category_id'''

ANALYSIS_VIEW = '''CREATE OR REPLACE VIEW workspace.default.gold_v_analysis_prices AS
WITH candidates AS (
 SELECT f.*,p.product_name,p.specification standard_specification,p.comparison_unit,p.analysis_rank,
 p.comparison_ready product_comparison_ready,
 count(*) OVER (PARTITION BY f.collected_date,f.store_key,f.product_id) mapped_skus_in_store
 FROM workspace.default.silver_fact_product_price f
 JOIN workspace.default.silver_dim_product p ON f.product_id=p.product_id WHERE p.is_analysis_selected=true
)
SELECT * EXCEPT(product_comparison_ready),
 coalesce(product_comparison_ready AND store_verification_status='verified' AND price_quality_status='ok'
 AND unit_quality_status='ok' AND normalized_unit_price>0 AND mapped_skus_in_store=1
 AND specification_quality_status IN ('reported','parsed_from_name')
 AND product_mapping_status IN ('source_id','name_spec_exact'),false) comparison_ready
FROM candidates'''

# Exact source card identities reviewed during the 2026-10-27 audit. No fuzzy matching.
REVIEWED_MAPPINGS = [
 ('52242','0003','Farmer Brown Eggs Cage Free Barn Size 7 12 Pack','12pk',1),
 ('774152','0011','Woodland Eggs Free Range Size 6 10 Pack','10pk',1),
 ('774153','0014','Woodland Eggs Free Range Size 7 10 Pack','10pk',1),
 ('546293','0019','Meadow Fresh Milk Standard Original 1L Bottle','1l',2),
 ('282793','0020','Meadow Fresh Milk Standard Original 2L Bottle','2l',2),
 ('701971','0021','Meadow Fresh Milk Standard Original 3L Bottle','3l',2),
 ('546321','0022','Meadow Fresh Calci-Trim Milk Trim Calci-Trim 1L Bottle','1l',2),
 ('282729','0023','Meadow Fresh Calci-Trim Milk Trim Calci-Trim 2L Bottle','2l',2),
]

def reviewed_sql(quote):
    values=','.join('('+','.join([quote(sku),quote(pid),quote(name),quote(spec),str(cat)])+')' for sku,pid,name,spec,cat in REVIEWED_MAPPINGS)
    return f'''MERGE INTO workspace.default.silver_dim_product_source t
USING (SELECT 'woolworths' source,v.*,max(b.product_url) product_url FROM
 (SELECT * FROM VALUES {values} AS v(source_product_id,product_id,original_name,original_specification,category_id)) v
 JOIN workspace.default.silver_v_prices_clean b ON b.source='woolworths' AND b.source_product_id=v.source_product_id
 AND b.original_name=v.original_name AND b.total_quant=v.original_specification AND try_cast(b.category_id AS INT)=v.category_id
 GROUP BY ALL) s ON t.source=s.source AND t.source_product_id=s.source_product_id
WHEN MATCHED AND t.mapping_status IN ('pending','exact_reference') THEN UPDATE SET
 t.product_id=s.product_id,t.mapping_status='approved',t.original_specification=s.original_specification,
 t.mapping_note='Reviewed exact source SKU, brand, product line, egg grade/farming method or fresh bottle volume; 2026-10-27'
WHEN NOT MATCHED THEN INSERT (source,source_product_id,product_id,original_name,original_specification,category_id,product_url,mapping_status,mapping_note)
VALUES (s.source,s.source_product_id,s.product_id,s.original_name,s.original_specification,s.category_id,s.product_url,'approved','Reviewed exact source card identity; 2026-10-27')'''

HOLD_AMBIGUOUS = '''UPDATE workspace.default.silver_dim_product_source SET
 product_id=NULL,mapping_status='pending_review',
 mapping_note='Two distinct source SKUs share Original Fresh Milk 1L title. Review bottle/carton/product identity before comparison; 2026-10-27'
WHERE source IN ('newworld','paknsave') AND source_product_id IN ('product-5026254-EA-000','product-5026255-EA-000')
AND mapping_status IN ('pending','exact_reference')'''
