"""Production collection: all configured Christchurch stores, all configured meat/egg/milk pages."""
import argparse,csv,json,sys,threading,time,traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from browser_driver import create_driver
from price_storage import PriceSink,FIELDS,EXTRA_FIELDS,volume_path
from woolworths_scraper import collect_store as collect_woolworths,save_diagnostics
from foodstuffs_scraper import collect_store as collect_foodstuffs
from access_guard import AccessDeniedError,check_access

ROOT=Path(__file__).resolve().parent
LOCK=threading.Lock()


def main(source=None,argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',choices=['all','woolworths','newworld','paknsave'],default=source or 'all')
    parser.add_argument('--stores',nargs='+',help='Store IDs within the selected brand')
    parser.add_argument('--exclude-source',nargs='+',choices=['woolworths','newworld','paknsave'],default=[],help='Brands temporarily excluded from this run')
    parser.add_argument('--test',action='store_true',help='Explicit smoke test: five egg products per store, no production upload')
    parser.add_argument('--limit',type=int,default=5,help='Only applies to --test')
    parser.add_argument('--full',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--workers',type=int,default=3,choices=[1,2,3])
    parser.add_argument('--retries',type=int,default=1,choices=[0,1,2],help='Whole-store retries for New World and PAKnSAVE; Woolworths does not retry whole stores')
    parser.add_argument('--no-ingest',action='store_true',help='Upload only; leave table ingestion to the notebook')
    parser.add_argument('--no-trigger',action='store_true',help='Upload and publish only; wait for the scheduled cloud Job')
    parser.add_argument('--ingest',action='store_true',help='Legacy manual SQL ingestion; default is upload only')
    parser.add_argument('--publish-manifest',type=Path,help='Publish an existing completed upload manifest for cloud processing; no scraping')
    parser.add_argument('--recover',type=Path,help='Ingest already-uploaded files from this manifest without opening browsers')
    args=parser.parse_args(argv)
    if args.ingest and args.no_ingest:parser.error('--ingest and --no-ingest cannot be combined')
    if args.publish_manifest:
        from publish_batch import publish
        publish(args.publish_manifest)
        return
    if args.recover:
        if args.test or args.no_ingest or args.stores or args.source!='all':
            parser.error('--recover cannot be combined with collection filters or test/upload-only mode')
        from recover_run import recover
        recover(args.recover)
        return
    if args.full and args.test:parser.error('--full and --test cannot be combined')
    if args.limit<1:parser.error('--limit must be positive')
    locations=json.loads((ROOT/'reference/store_locations.json').read_text(encoding='utf-8'))
    selected=[s for s in locations if s.get('is_christchurch_urban') is True and (args.source=='all' or s['source']==args.source)]
    selected=[s for s in selected if s['source'] not in args.exclude_source]
    if args.exclude_source:print('EXCLUDED BRANDS',', '.join(args.exclude_source),flush=True)
    if args.stores:
        if args.source=='all':parser.error('--stores requires a specific --source')
        selected=[s for s in selected if s['store_id'] in args.stores]
        if {s['store_id'] for s in selected}!=set(args.stores):parser.error('Unknown or out-of-city store IDs')
    if not selected:parser.error('No configured stores')
    if not args.test and args.ingest:
        from ingest_prices import SqlClient
        print('PREFLIGHT: checking Databricks SQL before opening browsers',flush=True)
        SqlClient().check_ready()
    categories=json.loads((ROOT/'reference/collection_categories.json').read_text(encoding='utf-8'))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    run_id='production_'+stamp+'_'+uuid4().hex[:8]
    output=ROOT/'data'/run_id;output.mkdir(parents=True,exist_ok=False)
    state={'run_id':run_id,'collected_date':datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat(),
           'mode':'test' if args.test else 'production','expected_stores':len(selected),
           'selected_stores':selected,'results':[],'status':'running'}
    brand_locks={s['source']:threading.Lock() for s in selected}
    blocked={s['source']:threading.Event() for s in selected}
    stopping=threading.Event()

    def persist():
        with LOCK:
            tmp=output/'manifest.tmp'
            tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(output/'manifest.json')

    persist()
    print('RUN',run_id,'stores',len(selected),'mode',state['mode'],flush=True)
    def capture(store):
        src=store['source'];id=store['store_id'];name=store['store_name']
        retries=0 if src=='woolworths' else args.retries
        for attempt in range(retries+1):
            if stopping.is_set() or blocked[src].is_set():
                return {'source':src,'store_id':id,'store_name':name,'status':'skipped',
                        'rows':0,'reason':'interrupted' if stopping.is_set() else 'brand_access_denied'}
            folder=output/src/id/str(attempt+1);folder.mkdir(parents=True,exist_ok=True)
            driver=None;counts=Counter();rows=0;remote=None
            try:
                print('START',src,name,'attempt',attempt+1,flush=True)
                driver=create_driver(page_load_strategy='normal')
                print('BROWSER READY',src,name,flush=True)
                driver.set_page_load_timeout(45)
                use_categories=categories[src][:1] if args.test else categories[src]
                collector=(collect_woolworths(driver,id,name,use_categories,args.limit if args.test else None)
                           if src=='woolworths' else collect_foodstuffs(driver,src,id,name,use_categories,args.limit if args.test else None))
                if args.test:
                    records=list(collector)
                    if len(records)!=args.limit:raise RuntimeError('Smoke test returned too few products')
                    with (folder/'products.csv').open('w',encoding='utf-8',newline='') as stream:
                        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
                    counts.update(r['category_name'] for r in records);rows=len(records)
                else:
                    with PriceSink(src,upload_on_error=False) as sink:
                        with (folder/'details.jsonl').open('w',encoding='utf-8') as details:
                            for record in collector:
                                if record['collected_date']!=state['collected_date']:
                                    raise RuntimeError('Run crossed local midnight; start a new daily run')
                                sink.write(tuple(record.get(k) for k in FIELDS),**{k:record.get(k) for k in EXTRA_FIELDS})
                                details.write(json.dumps(record,ensure_ascii=False)+'\n');details.flush()
                                rows+=1;counts[record['category_name']]+=1
                        if any(counts[k]==0 for k in ['Egg','Milk','Meat']):
                            raise RuntimeError(f'Incomplete store categories: {dict(counts)}')
                        # Publish detail evidence before the price file. Context exit uploads only a complete store.
                        detail_target=volume_path()+'/_details'
                        sink.client.files.create_directory(detail_target)
                        with (folder/'details.jsonl').open('rb') as stream:
                            sink.client.files.upload(detail_target+'/'+sink.path.stem+'.jsonl',stream,overwrite=True)
                    remote=volume_path()+'/'+sink.path.name
                result={'source':src,'store_id':id,'store_name':name,'status':'uploaded' if not args.test else 'test_passed',
                        'rows':rows,'category_counts':dict(counts),'remote_file':remote,'attempt':attempt+1}
                print('DONE',src,name,'rows',rows,'categories',dict(counts),flush=True)
                return result
            except Exception as error:
                if driver is not None and not isinstance(error,AccessDeniedError):
                    try:check_access(driver)
                    except AccessDeniedError as denied:error=denied
                    except Exception:pass
                if isinstance(error,AccessDeniedError):blocked[src].set()
                if driver is not None:
                    try:save_diagnostics(driver,folder)
                    except Exception:pass
                (folder/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                traceback.print_exc()
                print('ERROR',src,name,type(error).__name__,str(error)[:250],flush=True)
                if attempt==retries or blocked[src].is_set():
                    return {'source':src,'store_id':id,'store_name':name,'status':'failed','rows':rows,
                            'category_counts':dict(counts),'error_type':type(error).__name__,'error':str(error)}
            finally:
                if driver is not None:
                    try:driver.quit()
                    except Exception:pass
        raise AssertionError('Unreachable')

    def capture_serial(store):
        # Only one store per brand is active, so denial cannot race other stores.
        with brand_locks[store['source']]:
            result=capture(store)
            with LOCK:state['results'].append(result)
            persist()
            return result

    # Interleave brands so waiting stores do not occupy every worker.
    groups={src:[s for s in selected if s['source']==src] for src in brand_locks}
    scheduled=[group[i] for i in range(max(map(len,groups.values())))
               for group in groups.values() if i<len(group)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(capture_serial,store):store for store in scheduled}
        try:
            for future in as_completed(futures):
                future.result()
                print('PROGRESS',len(state['results']),'/',len(selected),'completed',flush=True)
        except BaseException:
            stopping.set()
            state['status']='interrupted';persist()
            print('Interrupted. Completed uploads are recorded; use --recover with this manifest.',flush=True)
            raise
    state['status']='collected';persist()
    if not args.test and any(r['status']=='uploaded' for r in state['results']):
        from publish_batch import publish
        try:
            state['ready_manifest']=publish(output/'manifest.json')
            state['cloud_processing']='pending'
            persist()
        except Exception as error:
            state['status']='publication_failed';state['publication_error']=str(error);persist();raise
    if not args.test and args.ingest and any(r['status']=='uploaded' for r in state['results']):
        try:
            from ingest_prices import ingest_manifest
            state['ingestion']=ingest_manifest(output/'manifest.json')
            state['status']='complete' if all(r['status']=='uploaded' for r in state['results']) else 'partial_failure'
        except Exception as error:
            state['status']='ingestion_failed';state['ingestion_error']=str(error);persist();raise
        try:
            from daily_checks import check_run
            state['checks']=check_run(state,selected)
            if state['checks']['status']!='passed':state['status']='validation_failed'
            print('CHECKS',json.dumps(state['checks'],ensure_ascii=False),flush=True)
        except Exception as error:
            state['status']='validation_failed'
            state['checks']={'status':'error','error':str(error)}
            persist()
            raise
    else:state['status']='complete' if all(r['status'] in ('uploaded','test_passed') for r in state['results']) else 'partial_failure'
    persist()
    cloud_failed=False
    if not args.test and not args.ingest and not args.no_ingest and not args.no_trigger and state['status']=='complete':
        from trigger_cloud_job import trigger_batch
        def cloud_update(result):
            state['cloud_job']=result
            state['cloud_processing']=result['status']
            persist()
        try:
            result=trigger_batch(run_id,cloud_update)
            cloud_failed=result['status'] not in ('succeeded','superseded')
        except Exception as error:
            state['cloud_trigger_error']=str(error)
            state['cloud_processing']='unconfirmed'
            persist();cloud_failed=True
            print('CLOUD JOB could not be confirmed:',error,flush=True)
        if cloud_failed:print('Uploads are safe. The 18:00 scheduled Job can process pending batches; see cloud_job in manifest.',flush=True)
    if not args.test:
        from databricks.sdk import WorkspaceClient
        target=volume_path()+'/_runs/'+run_id;client=WorkspaceClient()
        client.files.create_directory(target)
        with (output/'manifest.json').open('rb') as stream:client.files.upload(target+'/manifest.json',stream,overwrite=True)
    print('MANIFEST',output/'manifest.json',flush=True)
    print('FINAL',state['status'],'stores',len(state['results']),'uploaded rows',sum(r['rows'] for r in state['results'] if r['status']=='uploaded'),flush=True)
    if not args.test and not args.ingest:print('CLOUD PROCESSING',state.get('cloud_processing','pending'),'see manifest for details.',flush=True)
    if state['status'] not in ['complete']:raise SystemExit(1)
    if cloud_failed:raise SystemExit(2)
    return output/'manifest.json'

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
