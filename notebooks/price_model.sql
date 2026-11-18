CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_brand (
brand_id STRING NOT NULL PRIMARY KEY,
brand_name STRING NOT NULL, country_code STRING
) USING DELTA COMMENT '超市连锁品牌；不是商品生产商';

CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_category (
category_id INT NOT NULL PRIMARY KEY,
category_name STRING NOT NULL, category_name_zh STRING
) USING DELTA COMMENT '商品分类：蛋、奶、肉';

CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_store (
store_key STRING NOT NULL PRIMARY KEY,
source STRING NOT NULL, store_id STRING NOT NULL,
brand_id STRING NOT NULL REFERENCES workspace.default.silver_dim_brand(brand_id),
store_name STRING, address STRING, city STRING, region STRING, country_code STRING,
latitude DECIMAL(10,7), longitude DECIMAL(10,7), location_verified BOOLEAN,
location_source_url STRING, coordinate_source_url STRING, location_checked_date DATE,
location_status STRING, is_christchurch_urban BOOLEAN
) USING DELTA COMMENT '门店键为 source:store_id；未核实的名称、地址和坐标留空';

CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_product (
product_id STRING NOT NULL PRIMARY KEY,
product_name STRING NOT NULL,
category_id INT REFERENCES workspace.default.silver_dim_category(category_id),
specification STRING, quantity DECIMAL(12,4), quantity_unit STRING,
comparison_unit STRING, product_brand_name STRING,
is_analysis_selected BOOLEAN,
analysis_rank INT,
selection_notes STRING,
comparison_ready BOOLEAN
) USING DELTA COMMENT '标准商品；沿用 map.xlsx 的四位商品 ID；商品生产商品牌待维护';

CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_product_alias (
source STRING NOT NULL, original_name STRING NOT NULL,
original_specification STRING NOT NULL,
product_id STRING NOT NULL REFERENCES workspace.default.silver_dim_product(product_id),
PRIMARY KEY (source, original_name, original_specification)
) USING DELTA COMMENT '三家超市原始品名及规格到标准商品的映射；精确匹配';

CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_date (
date_id INT NOT NULL PRIMARY KEY, calendar_date DATE NOT NULL,
year INT, quarter INT, month INT, day INT, day_of_week INT, is_weekend BOOLEAN
) USING DELTA COMMENT '日期维度；day_of_week 为星期一=1 至星期日=7';

CREATE TABLE IF NOT EXISTS workspace.default.silver_fact_product_price (
observation_id STRING NOT NULL PRIMARY KEY,
date_id INT NOT NULL REFERENCES workspace.default.silver_dim_date(date_id),
collected_date DATE NOT NULL,
store_key STRING NOT NULL REFERENCES workspace.default.silver_dim_store(store_key),
product_id STRING REFERENCES workspace.default.silver_dim_product(product_id),
category_id INT REFERENCES workspace.default.silver_dim_category(category_id),
source STRING NOT NULL, store_id STRING NOT NULL,
original_name STRING NOT NULL, original_specification STRING,
total_price DECIMAL(12,4), reported_unit_price DECIMAL(12,4), reported_unit STRING,
is_promo BOOLEAN, product_mapping_status STRING, price_quality_status STRING,
source_file STRING, ingested_at TIMESTAMP,
source_product_id STRING,
product_url STRING,
member_price DECIMAL(12,4),
member_unit_price DECIMAL(12,4),
was_price DECIMAL(12,4),
store_verification_status STRING,
raw_specification STRING,
raw_reported_unit STRING,
specification_quality_status STRING,
unit_quality_status STRING,
normalized_unit STRING,
normalized_unit_price DECIMAL(16,6),
normalized_member_unit_price DECIMAL(16,6)
) USING DELTA COMMENT '每日门店商品报价；原始品名和规格区分未映射商品；reported 单价未标准化';

CREATE TABLE IF NOT EXISTS workspace.default.silver_dim_product_source (
 source STRING NOT NULL, source_product_id STRING NOT NULL,
 product_id STRING REFERENCES workspace.default.silver_dim_product(product_id),
 original_name STRING, original_specification STRING, category_id INT,
 product_url STRING, mapping_status STRING, mapping_note STRING,
 PRIMARY KEY (source,source_product_id)
) USING DELTA COMMENT 'Source SKU registry. Only approved/exact_reference mappings resolve a product; pending stays unmapped.' ;
