"""Generate a self-contained Spark notebook; no local credentials or warehouse API."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
cells=[]
def markdown(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
def code(text):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':text.splitlines(True)})
markdown('''# Volume 批次增量入库

本地仅采集上传；本 notebook 用 Spark 计算处理 `_ready` 下的完成清单，不调用 SQL Warehouse。
检查所有未成功批次（含前几天）；没有新数据就正常结束。同店同日使用最新发布批次。
**仅通过同一个 Job 运行，最大并发 1。不要同时运行旧版入库 notebook 或本地 --ingest。**
处理记录：`workspace.default.bronze_price_ingestion_runs`。SUCCEEDED 表示发布的完整门店文件已处理，不代表整天所有门店都已采齐。
''')
code('dbutils.widgets.text("volume_path", "/Volumes/workspace/default/price_tracker")\nvolume=dbutils.widgets.get("volume_path").rstrip("/")\n')
markdown('## 1. 批次协议与最新版本选择')
code((ROOT/'batch_protocol.py').read_text(encoding='utf-8'))
markdown('## 2. 已有 Bronze → Silver 转换计划（复用统一 SQL 规则）')
plan=json.loads((ROOT/'notebooks/product_analysis_statements.json').read_text(encoding='utf-8'))
code('plan = {"refresh": [], "views": []}\n')
for group in ('refresh','views'):
    for index,statement in enumerate(plan[group],1):
        markdown(f'### {group} · {index}')
        # Raw strings preserve SQL regex escapes; standalone cells keep SQL readable.
        if '"""' in statement:raise ValueError('Unexpected triple quote in SQL')
        code(f'plan[{group!r}].append(r"""\n'+statement+'\n""")\n')
markdown('## 3. 增量入库、处理记录与验证')
code((ROOT/'cloud_batch_ingest.py').read_text(encoding='utf-8'))
markdown('## 4. 执行')
code('''result=process_batches(spark,dbutils,volume,plan)
result['ledger']=[r.asDict() for r in spark.sql("SELECT run_id,cast(collected_date AS STRING) collected_date,status,row_count,store_count FROM workspace.default.bronze_price_ingestion_runs ORDER BY collected_date,run_id").collect()]
dbutils.fs.mkdirs(volume+'/_processing')
dbutils.fs.put(volume+'/_processing/latest_result.json',json.dumps(result,ensure_ascii=False,indent=2),True)
dbutils.notebook.exit(json.dumps(result))
''')
nb={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':5}
path=ROOT/'notebooks/ingest_volume_batches.ipynb'
path.write_text(json.dumps(nb,ensure_ascii=False,indent=2),encoding='utf-8')
print(path)
