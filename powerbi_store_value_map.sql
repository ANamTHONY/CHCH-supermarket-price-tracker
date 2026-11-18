WITH target_stores AS (
    SELECT store_key, source
    FROM workspace.default.silver_dim_store
    WHERE is_christchurch_urban = TRUE
),
chain_counts AS (
    SELECT source, COUNT(*) AS target_store_count
    FROM target_stores
    GROUP BY source
),
store_skus AS (
    SELECT
        collected_date,
        source,
        store_key,
        source_product_id,
        CASE WHEN COUNT(original_specification) = COUNT(*)
                  AND COUNT(DISTINCT original_specification) = 1
             THEN MIN(original_specification) END AS pack_size,
        CASE WHEN COUNT(total_price) = COUNT(*)
                  AND COUNT(DISTINCT total_price) = 1 AND MIN(total_price) > 0
             THEN MIN(total_price) END AS price,
        CASE WHEN COUNT(is_promo) = COUNT(*)
                  AND COUNT(DISTINCT is_promo) = 1
             THEN MAX(CAST(is_promo AS INT)) END AS promo
    FROM workspace.default.silver_fact_product_price
    WHERE store_verification_status = 'verified'
      AND store_key IN (SELECT store_key FROM target_stores)
      AND category_id IN (1, 2, 3)
      AND NULLIF(TRIM(source_product_id), '') IS NOT NULL
    GROUP BY collected_date, source, store_key, source_product_id
),
peer_prices AS (
    SELECT s.*, c.target_store_count,
        COUNT(CASE WHEN price > 0 THEN promo END) OVER (
            PARTITION BY collected_date, s.source, source_product_id
        ) AS promo_store_count,
        COUNT(price) OVER peers AS price_store_count,
        MEDIAN(price) OVER peers AS median_price
    FROM store_skus s
    JOIN chain_counts c ON s.source = c.source
    WINDOW peers AS (
        PARTITION BY collected_date, s.source, source_product_id, pack_size
    )
),
daily AS (
    SELECT
        collected_date, source, store_key,
        COUNT_IF(pack_size IS NOT NULL AND price IS NOT NULL
                 AND price_store_count >= 2) AS comparable_skus,
        AVG(CASE WHEN pack_size IS NOT NULL AND price_store_count >= 2
                 THEN 100 * TRY_DIVIDE(price, median_price) END) AS price_index,
        COUNT_IF(promo_store_count = target_store_count
                 AND target_store_count >= 2) AS known_promo_skus,
        COUNT_IF(promo_store_count = target_store_count
                 AND target_store_count >= 2 AND promo = 1) AS promo_skus
    FROM peer_prices
    GROUP BY collected_date, source, store_key
)
SELECT collected_date, source, store_key, 'Cheaper!' AS map_mode,
       price_index AS metric_value, 100 - price_index AS color_value,
       comparable_skus AS sample_skus
FROM daily
UNION ALL
SELECT collected_date, source, store_key, 'More Promos!' AS map_mode,
       100 * TRY_DIVIDE(promo_skus, known_promo_skus) AS metric_value,
       100 * TRY_DIVIDE(promo_skus, known_promo_skus) AS color_value,
       known_promo_skus AS sample_skus
FROM daily
