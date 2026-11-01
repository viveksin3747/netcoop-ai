"""Generate representative real report files for manual/visual QA."""
import asyncio
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['NETCOOP_DB']='tmp/export-verification.sqlite3'
from backend import store
from backend.demo import scenario
from backend.schemas import Settings
from backend.orchestrator import new_incident, execute
from backend.reports import export

out=Path('output/verification');out.mkdir(parents=True,exist_ok=True)
i=new_incident(scenario('router-overload'),Settings())
asyncio.run(execute(i['id']))
r=store.get('report',store.get('incident',i['id'])['report_id'])
for fmt in ('pdf','docx','json'):
    path=out/f'router-overload.{fmt}'
    path.write_bytes(export(r,fmt))
    print(path.resolve())
