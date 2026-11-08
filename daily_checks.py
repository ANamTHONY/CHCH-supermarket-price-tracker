"""Read-only acceptance checks for one production manifest."""
from collections import Counter

from ingest_prices import SqlClient
from product_model import sql_string


def check_run(state, selected):
    db = SqlClient()
    day = sql_string(state['collected_date'])
    expected = {(s['source'], s['store_id']) for s in selected}
    results = state['results']
    uploaded = {(r['source'], r['store_id']): r for r in results if r['status'] == 'uploaded'}
    errors = []
    if len(results) != len(expected) or len({(r['source'], r['store_id']) for r in results}) != len(results):
        errors.append('Missing or duplicate store results in manifest')
    if set(uploaded) != expected:
        errors.append('Stores not uploaded: ' + repr(sorted(expected - set(uploaded))))
    scope = ' OR '.join(
        f'(source={sql_string(src)} AND store_id={sql_string(store)})'
        for src, store in sorted(expected)
    )
    where = f'collected_date=DATE {day} AND ({scope})'
    bronze = db.run(f'SELECT source,store_id,count(*) FROM workspace.default.bronze_prices WHERE {where} GROUP BY 1,2')
    bronze_counts = {(r[0], r[1]): int(r[2]) for r in bronze}
    for key, result in uploaded.items():
        if bronze_counts.get(key) != result['rows']:
            errors.append(f'Bronze count mismatch: {key}')
        if any(result['category_counts'].get(c, 0) <= 0 for c in ('Meat', 'Egg', 'Milk')):
            errors.append(f'Incomplete collected categories: {key}')
    # Match the fact transformation's deduplication key, rather than raw CSV count.
    clean = db.run(f"""
        SELECT source,store_id,count(*) FROM (
          SELECT DISTINCT source,store_id,collected_date,category_id,
            CASE WHEN nullif(source_product_id,'') IS NOT NULL THEN source_product_id
                 ELSE concat_ws('||',original_name,coalesce(total_quant,'')) END identity
          FROM workspace.default.silver_v_prices_clean WHERE {where}
        ) GROUP BY 1,2
    """)
    expected_fact = {(r[0], r[1]): int(r[2]) for r in clean}
    fact = db.run(f"""
        SELECT source,store_id,count(*),count(DISTINCT category_id),
          count(*)-count(DISTINCT observation_id),
          count_if(coalesce(store_verification_status,'')<>'verified'),
          count_if(total_price IS NULL OR total_price<=0),
          count_if(product_id IS NULL),count_if(normalized_unit_price IS NULL)
        FROM workspace.default.silver_fact_product_price WHERE {where} GROUP BY 1,2
    """)
    fact_counts = {(r[0], r[1]): int(r[2]) for r in fact}
    if set(fact_counts) != expected or fact_counts != expected_fact:
        errors.append('Silver store coverage or deduplicated row counts do not match Bronze clean view')
    warnings = Counter()
    for row in fact:
        if int(row[3]) != 3 or int(row[4]) or int(row[5]):
            errors.append(f'Silver category/duplicate/store verification check failed: {row[:2]}')
        warnings['missing_or_nonpositive_price'] += int(row[6])
        warnings['unmapped_product'] += int(row[7])
        warnings['missing_normalized_unit_price'] += int(row[8])
    orphans = db.run(f"""
        SELECT count_if(s.store_key IS NULL),count_if(d.date_id IS NULL),
          count_if(f.product_id IS NOT NULL AND p.product_id IS NULL)
        FROM (SELECT * FROM workspace.default.silver_fact_product_price WHERE {where}) f
        LEFT JOIN workspace.default.silver_dim_store s ON f.store_key=s.store_key
        LEFT JOIN workspace.default.silver_dim_date d ON f.date_id=d.date_id
        LEFT JOIN workspace.default.silver_dim_product p ON f.product_id=p.product_id
    """)
    if any(int(v or 0) for row in orphans for v in row):
        errors.append('Fact rows reference missing store/date/product dimensions')
    return {'status': 'failed' if errors else 'passed', 'errors': errors,
            'quality_warnings': dict(warnings), 'expected_stores': len(expected),
            'uploaded_stores': len(uploaded), 'silver_rows': sum(fact_counts.values()),
            'silver_store_counts': [{'source': r[0], 'store_id': r[1], 'rows': int(r[2])} for r in fact]}
