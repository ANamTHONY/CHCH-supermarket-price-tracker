"""Notebook runtime. Spark and dbutils are supplied by Databricks, not a SQL Warehouse.

Only the scheduled Job may write these tables; max_concurrent_runs must be 1.
The generated notebook embeds this module, batch_protocol and the SQL plan.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo


def process_batches(spark, dbutils, volume, plan):
    from pyspark.sql import functions as F
    ledger='workspace.default.bronze_price_ingestion_runs'
    def quote(value):return "'"+str(value).replace('\\','\\\\').replace("'","''")+"'"
    def sql(query):return spark.sql(query).collect()
    sql(f'''CREATE TABLE IF NOT EXISTS {ledger} (
        run_id STRING, manifest_hash STRING, collected_date DATE, status STRING,
        row_count BIGINT, store_count BIGINT, error_message STRING, updated_at TIMESTAMP
    ) USING DELTA''')
    dbutils.fs.mkdirs(volume+'/_ready')
    batches=[]
    today=datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat()
    for file in dbutils.fs.ls(volume+'/_ready'):
        if not file.name.endswith('.json'):continue
        with open(file.path.removeprefix('dbfs:'),encoding='utf-8') as stream:batch=json.load(stream)
        validate_batch(batch,volume)
        if batch['collected_date']>today:raise ValueError('Future-dated batch')
        batches.append(batch)
    if len({b['run_id'] for b in batches})!=len(batches):raise ValueError('Duplicate run IDs')
    known={r.run_id:r.asDict() for r in sql(f'SELECT * FROM {ledger}')}
    for batch in batches:
        prior=known.get(batch['run_id'])
        if prior and prior['manifest_hash']!=digest(batch):raise ValueError('Published manifest changed')
    latest=latest_files(batches)
    pending=[b for b in sorted(batches,key=lambda b:b['run_id'])
             if known.get(b['run_id'],{}).get('status') not in ('SUCCEEDED','SUPERSEDED')]
    if not pending:
        print('NO_NEW_BATCHES: no unprocessed published batches, including previous dates.')
        return {'status':'no_new_batches','processed':0}

    def record(batch,status,rows=0,stores=0,error=''):
        sql(f'''MERGE INTO {ledger} t USING (SELECT
            {quote(batch['run_id'])} run_id,{quote(digest(batch))} manifest_hash,
            DATE {quote(batch['collected_date'])} collected_date,{quote(status)} status,
            CAST({rows} AS BIGINT) row_count,CAST({stores} AS BIGINT) store_count,
            {quote(error[:4000])} error_message,current_timestamp() updated_at) s
            ON t.run_id=s.run_id WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *''')

    fields=['product_id','store_id','category_id','total_price','total_quant','unit','unit_price',
            'original_name','collected_date','is_promo','source','source_product_id','product_url',
            'member_price','member_unit_price','was_price','store_verified']
    schema=','.join(k+' STRING' for k in fields)
    applied=[]
    try:
        for batch in pending:
            run_id=batch['run_id']
            chosen=[r for r in batch['files'] if latest[(r['source'],r['store_id'],batch['collected_date'])][0]==run_id]
            if not chosen:
                record(batch,'SUPERSEDED')
                continue
            record(batch,'RUNNING')
            print('PROCESS',run_id,'stores',len(chosen),'of',batch['expected_stores'])
            frames=[]
            expected={}
            predicates=[]
            for item in chosen:
                frame=(spark.read.format('csv').schema(schema).option('header','true')
                       .option('multiLine','true').option('escape','"').option('mode','FAILFAST')
                       .load(item['remote_file'])
                       .withColumn('collected_date',F.to_date('collected_date'))
                       .withColumn('source_file',F.lit(item['remote_file']))
                       .withColumn('ingested_at',F.current_timestamp()))
                # Validate each file's identity, not merely totals across the union.
                summary=frame.groupBy('source','store_id','collected_date').count().collect()
                key=(item['source'],item['store_id'],batch['collected_date'])
                if len(summary)!=1 or (summary[0]['source'],summary[0]['store_id'],str(summary[0]['collected_date']))!=key or summary[0]['count']!=item['rows']:
                    raise ValueError('File identity/row count mismatch: '+item['remote_file'])
                frames.append(frame);expected[key]=item['rows']
                predicates.append(f"(source={quote(key[0])} AND store_id={quote(key[1])} AND collected_date=DATE {quote(key[2])})")
            stage=frames[0]
            for frame in frames[1:]:stage=stage.unionByName(frame)
            view='_price_batch_stage'
            stage.createOrReplaceTempView(view)
            checks=sql(f'''SELECT source,store_id,count(DISTINCT category_id) categories,
                count_if(coalesce(try_cast(store_verified AS BOOLEAN),false)=false) unverified,
                count_if(nullif(source_product_id,'') IS NULL) missing_sku,
                count(*)-count(DISTINCT struct(category_id,source_product_id)) duplicates
                FROM {view} GROUP BY 1,2''')
            if any(r.categories!=3 or r.unverified or r.missing_sku or r.duplicates for r in checks):
                raise ValueError('Category/store/SKU validation failed')
            predicate=' OR '.join(predicates)
            columns=','.join('`'+c+'`' for c in spark.table('workspace.default.bronze_prices').columns)
            # Each store/day replacement is idempotent. Ledger commits are separate;
            # a crash before SUCCEEDED causes safe replacement and transformation retry.
            sql(f'INSERT INTO workspace.default.bronze_prices REPLACE WHERE {predicate} SELECT {columns} FROM {view}')
            observed=sql(f'''SELECT source,store_id,cast(collected_date AS STRING) day,count(*) n
                FROM workspace.default.bronze_prices WHERE {predicate} GROUP BY 1,2,3''')
            if {(r.source,r.store_id,r.day):r.n for r in observed}!=expected:raise ValueError('Bronze verification failed')
            applied.append((batch,sum(expected.values()),len(chosen),predicate))
            record(batch,'BRONZE_WRITTEN',sum(expected.values()),len(chosen))
        if applied:
            # Once per scheduled execution, not once per store or batch.
            for index,statement in enumerate(plan['refresh']+plan['views'],1):
                print('TRANSFORM',index)
                sql(statement)
            integrity=sql('''SELECT count(*)-count(DISTINCT observation_id) duplicates,
                count_if(collected_date < DATE '2026-10-27') historical
                FROM workspace.default.silver_fact_product_price''')[0]
            if integrity.duplicates or integrity.historical:raise ValueError('Silver integrity failure')
            for batch,rows,stores,predicate in applied:
                counts=sql(f'''SELECT count(*) rows,count(DISTINCT store_key) stores,
                    count_if(coalesce(store_verification_status,'')<>'verified') unverified
                    FROM workspace.default.silver_fact_product_price WHERE {predicate}''')[0]
                if counts.rows!=rows or counts.stores!=stores or counts.unverified:
                    raise ValueError('Silver batch count/store verification failed')
            for batch,rows,stores,_ in applied:record(batch,'SUCCEEDED',rows,stores)
        print('COMPLETE',len(applied),'batches; partial collections remain explicitly marked in each ready manifest.')
        return {'status':'complete','processed':len(applied)}
    except Exception as error:
        # Preserve successful earlier records; RUNNING/BRONZE_WRITTEN/FAILED all retry.
        for batch in pending:
            rows=sql(f'SELECT status FROM {ledger} WHERE run_id={quote(batch["run_id"])}')
            if rows and rows[0].status in ('RUNNING','BRONZE_WRITTEN'):
                record(batch,'FAILED',error=str(error))
        raise
