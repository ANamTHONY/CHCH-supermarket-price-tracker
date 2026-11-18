WITH daily_skus AS (
    SELECT f.collected_date, f.source, f.store_key, f.source_product_id,
           LOWER(TRIM(f.original_specification)) AS pack,
           LOWER(TRIM(f.normalized_unit)) AS price_unit,
           MIN(f.normalized_unit_price) AS price
    FROM workspace.default.silver_fact_product_price f
    JOIN workspace.default.silver_dim_store s ON f.store_key = s.store_key
    WHERE s.is_christchurch_urban
      AND f.store_verification_status = 'verified'
      AND f.category_id IN (1, 2, 3)
      AND NULLIF(TRIM(f.source_product_id), '') IS NOT NULL
      AND NULLIF(TRIM(f.normalized_unit), '') IS NOT NULL
    GROUP BY ALL
    HAVING COUNT(f.normalized_unit_price) = COUNT(*)
       AND COUNT(DISTINCT f.normalized_unit_price) = 1
       AND MIN(f.normalized_unit_price) > 0
), history AS (
    SELECT *, COUNT(*) OVER prior_days AS observations,
           PERCENTILE(price, 0.5) OVER prior_days AS usual_price
    FROM daily_skus
    WINDOW prior_days AS (
        PARTITION BY source, store_key, source_product_id, pack, price_unit
        ORDER BY UNIX_DATE(collected_date) RANGE BETWEEN 28 PRECEDING AND 1 PRECEDING
    )
), store_days AS (
    SELECT collected_date, source, store_key,
           COUNT_IF(price < usual_price) / COUNT(*) AS share
    FROM history WHERE observations >= 7
    GROUP BY collected_date, source, store_key
)
SELECT collected_date, source, WEEKDAY(collected_date) + 1 AS weekday_number,
       DATE_FORMAT(collected_date, 'EEE') AS weekday_name,
       AVG(share) AS low_price_share
FROM store_days
GROUP BY collected_date, source
