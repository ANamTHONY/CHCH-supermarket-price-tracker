"""Product selection and exact, source-aware mapping rules shared by SQL/notebooks."""
import re

EXTRA_COLUMNS={'source_product_id':'STRING','product_url':'STRING','member_price':'STRING','member_unit_price':'STRING','was_price':'STRING','store_verified':'STRING'}
PRODUCT_COLUMNS={'is_analysis_selected':'BOOLEAN','analysis_rank':'INT','selection_notes':'STRING','comparison_ready':'BOOLEAN'}
FACT_COLUMNS={'source_product_id':'STRING','product_url':'STRING','member_price':'DECIMAL(12,4)','member_unit_price':'DECIMAL(12,4)','was_price':'DECIMAL(12,4)','store_verification_status':'STRING'}
SELECTED_IDS=['0001','0003','0011','0014','0015','0019','0020','0021','0022','0023','0042','0043','0045','0047','0048']

def normalize_name(value):return re.sub(r'\s+',' ',(value or '').strip()).lower()
def normalize_spec(value):return re.sub(r'\s+','',(value or '').strip()).lower().replace('pack','pk')
def sql_string(value):
    if value is None:return 'NULL'
    return "'"+str(value).replace('\\','\\\\').replace("'","\\'")+"'"
def sql_name(column):return f"lower(regexp_replace(trim(coalesce({column},'')), '\\\\s+', ' '))"
def sql_spec(column):return f"replace(lower(regexp_replace(trim(coalesce({column},'')), '\\\\s+', '')), 'pack', 'pk')"

SOURCE_DDL='''CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_product_source (
 source STRING NOT NULL, source_product_id STRING NOT NULL,
 product_id STRING REFERENCES workspace.default.silver_dim_product(product_id),
 original_name STRING, original_specification STRING, category_id INT,
 product_url STRING, mapping_status STRING, mapping_note STRING,
 PRIMARY KEY (source,source_product_id)
) USING DELTA COMMENT 'Source SKU registry. Only approved/exact_reference mappings resolve a product; pending stays unmapped.' '''

ALIAS_CTE=f'''alias_map AS (
 SELECT a.source, {sql_name('a.original_name')} name_key,
 {sql_spec('a.original_specification')} spec_key, p.category_id,
 min(a.product_id) product_id
 FROM workspace.default.silver_dim_product_alias a
 JOIN workspace.default.silver_dim_product p ON a.product_id=p.product_id
 GROUP BY a.source,{sql_name('a.original_name')},{sql_spec('a.original_specification')},p.category_id
 HAVING count(DISTINCT a.product_id)=1
)'''

LEARN_SOURCE_SQL=f'''MERGE INTO workspace.default.silver_dim_product_source t
USING (WITH {ALIAS_CTE}, candidates AS (
 SELECT b.source,b.source_product_id,min(a.product_id) product_id,
 max(b.original_name) original_name,max(b.total_quant) original_specification,
 max(try_cast(b.category_id AS INT)) category_id,max(b.product_url) product_url
 FROM workspace.default.bronze_prices b LEFT JOIN alias_map a
 ON b.source=a.source AND {sql_name('b.original_name')}=a.name_key
 AND {sql_spec('b.total_quant')}=a.spec_key AND try_cast(b.category_id AS INT)=a.category_id
 WHERE b.source_product_id IS NOT NULL AND trim(b.source_product_id)<>''
 GROUP BY b.source,b.source_product_id
 HAVING count(DISTINCT a.product_id)<=1
) SELECT *,CASE WHEN product_id IS NOT NULL THEN 'exact_reference' ELSE 'pending' END mapping_status,
 'Exact name/spec/category reference match; no fuzzy matching' mapping_note FROM candidates) s
ON t.source=s.source AND t.source_product_id=s.source_product_id
WHEN MATCHED AND t.mapping_status='pending' AND s.product_id IS NOT NULL THEN UPDATE SET
 t.product_id=s.product_id,t.mapping_status=s.mapping_status,t.mapping_note=s.mapping_note
WHEN NOT MATCHED THEN INSERT *'''

FACT_BASE=['observation_id','date_id','collected_date','store_key','product_id','category_id','source','store_id','original_name','original_specification','total_price','reported_unit_price','reported_unit','is_promo','product_mapping_status','price_quality_status','source_file','ingested_at']
FACT_REFRESH=f'''INSERT OVERWRITE TABLE workspace.default.silver_fact_product_price
({','.join(FACT_BASE+list(FACT_COLUMNS))})
WITH {ALIAS_CTE}, ranked AS (
 SELECT *,row_number() OVER (
 PARTITION BY source,store_id,collected_date,category_id,
 CASE WHEN nullif(source_product_id,'') IS NOT NULL THEN source_product_id ELSE concat_ws('||',original_name,coalesce(total_quant,'')) END
 ORDER BY ingested_at DESC,source_file DESC,total_price DESC,unit_price DESC,is_promo DESC
 ) rn FROM workspace.default.bronze_prices WHERE collected_date >= DATE '2026-10-27'
), enriched AS (
 SELECT b.*,coalesce(p.product_id,a.product_id) mapped_product_id,
 coalesce(p.category_id,a.category_id,c.category_id) mapped_category_id,
 CASE WHEN p.product_id IS NOT NULL THEN 'source_id' WHEN a.product_id IS NOT NULL THEN 'name_spec_exact' ELSE 'unmapped' END mapping_method,
 try_cast(b.total_price AS DECIMAL(12,4)) price_value,
 try_cast(b.unit_price AS DECIMAL(12,4)) unit_price_value
 FROM ranked b
 LEFT JOIN workspace.default.silver_dim_product_source s
 ON b.source=s.source AND b.source_product_id=s.source_product_id AND s.mapping_status IN ('approved','exact_reference')
 LEFT JOIN workspace.default.silver_dim_product p ON s.product_id=p.product_id AND p.category_id=try_cast(b.category_id AS INT)
 LEFT JOIN alias_map a ON b.source=a.source AND {sql_name('b.original_name')}=a.name_key
 AND {sql_spec('b.total_quant')}=a.spec_key AND try_cast(b.category_id AS INT)=a.category_id
 LEFT JOIN workspace.default.silver_dim_category c ON try_cast(b.category_id AS INT)=c.category_id
 WHERE b.rn=1
)
SELECT sha2(to_json(named_struct('source',source,'store_id',store_id,'date',collected_date,'category',category_id,
 'identity',CASE WHEN nullif(source_product_id,'') IS NOT NULL THEN source_product_id ELSE concat_ws('||',original_name,coalesce(total_quant,'')) END)),256),
 cast(date_format(collected_date,'yyyyMMdd') AS INT),collected_date,concat(source,':',store_id),mapped_product_id,mapped_category_id,
 source,store_id,original_name,total_quant,
 CASE WHEN price_value>=0 THEN price_value END,CASE WHEN unit_price_value>=0 THEN unit_price_value END,unit,
 CASE WHEN is_promo='1' THEN true WHEN is_promo='0' THEN false END,mapping_method,
 CASE WHEN price_value IS NULL THEN 'missing_or_invalid_price' WHEN price_value<0 THEN 'negative_price' ELSE 'ok' END,
 source_file,ingested_at,source_product_id,product_url,
 CASE WHEN try_cast(member_price AS DECIMAL(12,4))>=0 THEN try_cast(member_price AS DECIMAL(12,4)) END,
 CASE WHEN try_cast(member_unit_price AS DECIMAL(12,4))>=0 THEN try_cast(member_unit_price AS DECIMAL(12,4)) END,
 CASE WHEN try_cast(was_price AS DECIMAL(12,4))>=0 THEN try_cast(was_price AS DECIMAL(12,4)) END,
 CASE WHEN try_cast(store_verified AS BOOLEAN)=true THEN 'verified' ELSE 'legacy_unverified' END
FROM enriched'''

VIEWS=[
'''CREATE OR REPLACE VIEW workspace.default.gold_v_analysis_products AS
SELECT p.*,c.category_name,
 (SELECT count(DISTINCT s.source) FROM workspace.default.silver_dim_product_source s WHERE s.product_id=p.product_id AND s.mapping_status IN ('approved','exact_reference')) source_id_brand_coverage
FROM workspace.default.silver_dim_product p JOIN workspace.default.silver_dim_category c ON p.category_id=c.category_id
WHERE p.is_analysis_selected=true''',
'''CREATE OR REPLACE VIEW workspace.default.gold_v_analysis_prices AS
SELECT f.*,p.product_name,p.specification standard_specification,p.comparison_unit,p.analysis_rank,
 coalesce(p.comparison_ready AND f.store_verification_status='verified' AND f.price_quality_status='ok'
 AND f.product_mapping_status IN ('source_id','name_spec_exact'),false) comparison_ready
FROM workspace.default.silver_fact_product_price f
JOIN workspace.default.silver_dim_product p ON f.product_id=p.product_id WHERE p.is_analysis_selected=true''',
'''CREATE OR REPLACE VIEW workspace.default.gold_v_unmapped_products AS
SELECT source,source_product_id,category_id,original_name,original_specification,count(*) observations,
 min(collected_date) first_seen,max(collected_date) last_seen
FROM workspace.default.silver_fact_product_price WHERE product_id IS NULL
GROUP BY source,source_product_id,category_id,original_name,original_specification''']

# All entry points share the same Bronze -> Silver rules.
from silver_rules import CLEAN_DDL,SILVER_COLUMNS,PENDING_VIEW,QUALITY_VIEW,ANALYSIS_VIEW,HOLD_AMBIGUOUS,reviewed_sql
OLD_FACT_COLUMNS=list(FACT_COLUMNS)
FACT_COLUMNS.update(SILVER_COLUMNS)
LEARN_SOURCE_SQL=LEARN_SOURCE_SQL.replace('workspace.default.bronze_prices b','workspace.default.silver_v_prices_clean b')
FACT_REFRESH=FACT_REFRESH.replace(','.join(FACT_BASE+OLD_FACT_COLUMNS),','.join(FACT_BASE+list(FACT_COLUMNS)))
FACT_REFRESH=FACT_REFRESH.replace('FROM workspace.default.bronze_prices WHERE','FROM workspace.default.silver_v_prices_clean WHERE')
FACT_REFRESH=FACT_REFRESH.replace('coalesce(p.product_id,a.product_id) mapped_product_id','p.product_id mapped_product_id')
FACT_REFRESH=FACT_REFRESH.replace("WHEN a.product_id IS NOT NULL THEN 'name_spec_exact' ELSE 'unmapped'","WHEN s.mapping_status='pending_review' THEN 'pending_review' ELSE 'unmapped'")
# Keep registry state visible, but resolve only explicitly accepted mappings.
FACT_REFRESH=FACT_REFRESH.replace(" AND s.mapping_status IN ('approved','exact_reference')",'')
FACT_REFRESH=FACT_REFRESH.replace('ON s.product_id=p.product_id AND p.category_id=try_cast(b.category_id AS INT)',
 "ON s.product_id=p.product_id AND s.mapping_status IN ('approved','exact_reference') AND p.category_id=try_cast(b.category_id AS INT) AND "+sql_spec('p.specification')+'='+sql_spec('b.total_quant'))
FACT_REFRESH=FACT_REFRESH.replace("WHEN price_value<0 THEN 'negative_price' ELSE 'ok'", "WHEN price_value<0 THEN 'negative_price' WHEN price_value=0 THEN 'zero_price' ELSE 'ok'")
FACT_REFRESH=FACT_REFRESH.replace('\nFROM enriched',',\n'+','.join(SILVER_COLUMNS)+'\nFROM enriched')
VIEWS[1]=ANALYSIS_VIEW
VIEWS.extend([PENDING_VIEW,QUALITY_VIEW])
SILVER_PREPARE=[CLEAN_DDL]
MAPPING_REVIEW=[reviewed_sql(sql_string),HOLD_AMBIGUOUS,
 "UPDATE workspace.default.silver_dim_product SET comparison_unit='l' WHERE category_id=2 AND is_analysis_selected=true AND comparison_unit<>'l'"]
