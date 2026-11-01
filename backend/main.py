import asyncio
import logging
import re
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError, Field
from typing import Literal
from . import store
from .schemas import Settings, Telemetry, AGENTS, now
from .telemetry import parse_upload, quality
from .demo import SCENARIOS, scenario
from .orchestrator import new_incident, execute
from .reports import create_report, export
from . import live, speed, monitoring

logging.basicConfig(level=logging.INFO)
tasks=set()

@asynccontextmanager
async def lifespan(app):
    for incident in store.all_records('incident'):
        if incident['status']=='running':
            incident.update(status='failed',error='Server restarted during diagnosis. Run diagnosis again.')
            for agent in incident['agents']:
                if agent['status'] in ('running','waiting'): agent.update(status='failed',error='Interrupted by restart')
            store.put('incident',incident['id'],incident)
    scheduler=asyncio.create_task(monitoring.loop(start))
    yield
    scheduler.cancel()
    await asyncio.gather(scheduler,return_exceptions=True)
    for task in list(tasks): task.cancel()
    if tasks: await asyncio.gather(*tasks,return_exceptions=True)

app=FastAPI(title='NetCoop AI',version='1.0.0',lifespan=lifespan)

@app.middleware('http')
async def local_guard(request: Request, call_next):
    # Loopback service only. Refuse foreign browser origins (including CSRF uploads).
    host=request.url.hostname
    if host not in ('127.0.0.1','localhost','testserver','::1'):
        return Response('Local access only',status_code=403)
    origin=request.headers.get('origin')
    if origin and origin not in ('http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:5173','http://localhost:5173'):
        return Response('Origin not allowed',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    return response

def settings(): return Settings.model_validate(store.get('settings','default') or {})
def required(kind,key):
    if not re.fullmatch(r'(INC|RPT)-[a-f0-9]{12}',key): raise HTTPException(404,'Record not found')
    result=store.get(kind,key)
    if result is None: raise HTTPException(404,'Record not found')
    return result
def start(t, test_context=None, speed_test=None):
    if len(tasks)>=4: raise HTTPException(429,'Four diagnoses already running; wait and retry')
    incident=new_incident(t,settings())
    if speed_test:
        incident['speed_test']=speed_test
        store.put('incident',incident['id'],incident)
    if test_context:
        incident['test_context']=test_context
        store.put('incident',incident['id'],incident)
    task=asyncio.create_task(execute(incident['id'])); tasks.add(task); task.add_done_callback(tasks.discard)
    return incident

@app.get('/api/health')
def health(): return {'status':'online','live_monitoring':True,'live_scope':'default gateway ICMP'}

@app.get('/api/system/status')
def system_status():
    try:
        with store.connect() as db:db.execute('SELECT 1').fetchone()
        database='available'
    except Exception:database='unavailable'
    proof=Path(__file__).resolve().parents[1]/'docs'/'test-status.json'
    try:tests=json.loads(proof.read_text())
    except (OSError,ValueError):tests={'status':'not recorded','message':'Run verification to record a timestamped result.'}
    github=os.getenv('NETCOOP_GITHUB_URL','')
    return dict(api='online',database=database,version=app.version,tests=tests,
        github_url=github if re.fullmatch(r'https://github\.com/[\w.-]+/[\w.-]+/?',github) else None,
        monitoring=monitoring.state(),source_scope='Default gateway ICMP and bounded internet transfer tests')

@app.get('/api/documentation')
def documentation():return Response((Path(__file__).resolve().parents[1]/'README.md').read_text(encoding='utf-8'),media_type='text/plain')

@app.get('/api/workspace/export')
def workspace_export():
    payload=dict(exported_at=now(),incidents=store.all_records('incident'),reports=store.all_records('report'),
        settings=settings().model_dump(),monitoring=monitoring.state(),monitoring_events=store.all_records('monitor-event'))
    return Response(json.dumps(payload,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="netcoop-workspace.json"'})

@app.get('/api/monitoring')
def monitoring_status():return monitoring.state()

class MonitorRequest(BaseModel): enabled: bool

@app.put('/api/monitoring')
def set_monitoring(body:MonitorRequest):
    config=monitoring.state();config['enabled']=body.enabled
    if body.enabled:config['next_check_at']=now()
    store.put('monitor','state',config)
    return config

@app.post('/api/period-reports/{period}')
def period_report(period:Literal['weekly','monthly']):return monitoring.aggregate(period)

@app.get('/api/alerts')
def alerts():return [a for i in store.all_records('incident') for a in i.get('alerts',[])]

@app.post('/api/live/measure',status_code=202)
async def measure_live():
    if live.lock.locked() or speed.lock.locked(): raise HTTPException(409,'A measurement is already running. Wait for it to finish.')
    async with live.lock,speed.lock:
        try: telemetry, sample=await asyncio.to_thread(live.collect)
        except (ValueError, OSError, TimeoutError, __import__('subprocess').TimeoutExpired) as exc:
            raise HTTPException(503,str(exc))
        result=await asyncio.to_thread(speed.measure)
        result['related_report_id']=None
        return start(telemetry,speed_test=result)
@app.get('/api/settings')
def get_settings(): return settings()

@app.post('/api/reports/{key}/speed-test',status_code=202)
async def run_speed_test(key: str):
    original=required('report',key)
    if speed.lock.locked() or live.lock.locked(): raise HTTPException(409,'Another connection test is running. Please retry shortly.')
    async with speed.lock,live.lock:
        if len(tasks)>=4: raise HTTPException(429,'Wait for the active diagnoses to finish.')
        try: telemetry,_=await asyncio.to_thread(live.collect)
        except (ValueError,OSError,TimeoutError,__import__('subprocess').TimeoutExpired):
            raise HTTPException(503,'Cannot identify the current router. Connect to Wi-Fi or Ethernet and retry.')
        result=await asyncio.to_thread(speed.measure)
        result['related_report_id']=original['report_id']
        return start(telemetry,speed_test=result)
@app.put('/api/settings')
def save_settings(value: Settings):
    store.put('settings','default',value.model_dump()); return value
@app.get('/api/demo/scenarios')
def demos(): return SCENARIOS
class DemoRequest(BaseModel): scenario_id: str
@app.post('/api/demo/run',status_code=202)
async def run_demo(body: DemoRequest):
    try: t=scenario(body.scenario_id)
    except ValueError as exc: raise HTTPException(422,str(exc))
    return start(t)
@app.post('/api/telemetry/validate')
def validate(t: Telemetry): return {'telemetry':t.model_dump(mode='json'),'quality':quality(t,settings().stale_after_minutes)}
@app.post('/api/telemetry/upload')
async def upload(file: UploadFile=File(...)):
    content=await file.read(2*1024*1024+1)
    try: t=parse_upload(file.filename or 'upload.txt',content)
    except (ValueError,UnicodeError) as exc: raise HTTPException(422,str(exc))
    return {'telemetry':t.model_dump(mode='json'),'quality':quality(t,settings().stale_after_minutes)}
@app.post('/api/diagnosis/start',status_code=202)
async def diagnose(t: Telemetry):
    if t.source_type!='upload': raise HTTPException(422,'Use the demo endpoint for simulated scenarios; live integration unavailable')
    return start(t)
@app.get('/api/incidents')
def incidents(): return store.all_records('incident')
@app.get('/api/incidents/{key}')
def incident(key: str): return required('incident',key)
@app.get('/api/diagnosis/{key}/status')
def status(key: str):
    i=required('incident',key); return {k:i[k] for k in ('id','status','agents','error','report_id')}
@app.get('/api/diagnosis/{key}/{area}')
def diagnosis_area(key: str,area: Literal['agents','evidence','correlation']): return required('incident',key)[area]
@app.get('/api/dashboard/overview')
def overview():
    rows=store.all_records('incident'); latest=rows[0] if rows else None
    devices=latest['telemetry']['devices'] if latest else []
    affected=(latest.get('correlation') or {}).get('affected_devices',[]) if latest else []
    return dict(total_devices=len(devices),healthy_devices=sum(d['status']=='online' and d['device_id'] not in affected for d in devices),
        incidents=len(rows),critical_incidents=sum((r.get('correlation') or {}).get('severity')=='critical' for r in rows),
        latest=latest,live_monitoring=monitoring.state()['enabled'])
@app.get('/api/dashboard/metrics')
def metrics():
    result=[]
    for i in reversed(store.all_records('incident')[:20]):
        row={'timestamp':i['created_at'],'data_mode':i['telemetry']['data_mode']}
        for metric in ('latency_ms','packet_loss_percent','jitter_ms'):
            values=[d[metric] for d in i['telemetry']['devices'] if d.get(metric) is not None]
            row[metric]=sum(values)/len(values) if values else None
        result.append(row)
    return result
@app.get('/api/agents/status')
def agent_status():
    rows=store.all_records('incident')
    return rows[0]['agents'] if rows else [{'agent_id':a,'status':'idle'} for a in AGENTS]
@app.get('/api/recommendations')
def recommendations(): return [r for i in store.all_records('incident') for r in i['recommendations']]
@app.get('/api/recommendations/{key}')
def incident_recommendations(key: str): return required('incident',key)['recommendations']
class RecStatus(BaseModel):
    status: Literal['Pending','In Progress','Completed','Dismissed']
    operator_confirmed: bool=False
    verification_note: str=Field(default='',max_length=2000)

@app.get('/api/recommendation-details/{key}')
def recommendation_details(key: str):
    for i in store.all_records('incident'):
        rec=next((r for r in i['recommendations'] if r['id']==key),None)
        if rec:
            tests=[dict(id=t['id'],status=t['status'],created_at=t['created_at'],report_id=t.get('report_id'),
                target_matches_original=t['test_context'].get('target_matches_original',False))
                for t in store.all_records('incident') if t.get('test_context',{}).get('recommendation_id')==key]
            return dict(recommendation=rec,incident=i,tests=tests)
    raise HTTPException(404,'Recommendation not found')
@app.post('/api/recommendations/{key}/test',status_code=202)
async def test_recommendation(key: str):
    original=None; recommendation=None
    for row in store.all_records('incident'):
        recommendation=next((r for r in row['recommendations'] if r['id']==key),None)
        if recommendation:
            original=row;break
    if not original: raise HTTPException(404,'Recommendation not found')
    if live.lock.locked() or speed.lock.locked(): raise HTTPException(409,'A live measurement is already running. Please retry shortly.')
    async with live.lock,speed.lock:
        try: telemetry,sample=await asyncio.to_thread(live.collect)
        except (ValueError,OSError,TimeoutError,__import__('subprocess').TimeoutExpired):
            raise HTTPException(503,'Router measurement failed. Check your connection and retry.')
        same_target=original['telemetry']['source_type']=='live' and any(
            d.get('ip_address')==sample['gateway'] for d in original['telemetry']['devices'])
        speed_result=await asyncio.to_thread(speed.measure)
        speed_result['related_report_id']=original.get('report_id')
        result=start(telemetry,dict(recommendation_id=key,original_incident_id=original['id'],
            original_report_id=original.get('report_id'),action=recommendation['action'],
            target_matches_original=same_target,
            scope='Current default gateway: latency, unanswered ICMP probes and response-time variation only.',
            limitation='This check cannot verify CPU, memory, repairs, or simulated devices. It does not mark the recommendation completed.'),speed_test=speed_result)
        store.recommendation_event(original['id'],key,dict(timestamp=now(),event='live_test_started',test_incident_id=result['id'],target_matches_original=same_target))
        return result
@app.put('/api/recommendations/{key}/status')
def rec_status(key: str,body: RecStatus):
    if body.status=='Completed' and (not body.operator_confirmed or not body.verification_note.strip()):
        raise HTTPException(422,'Confirm operator verification and describe how recovery was checked before marking completed.')
    for i in store.all_records('incident'):
        if store.update_recommendation(i['id'],key,body.status,body.verification_note.strip(),body.operator_confirmed): return {'status':body.status}
    raise HTTPException(404,'Recommendation not found')
@app.get('/api/reports')
def reports():
    return [{k:v for k,v in r.items() if k not in ('incident','incidents','sections','monitoring_events')} for r in store.all_records('report')]
@app.post('/api/reports/generate/{key}')
def generate(key: str):
    i=required('incident',key)
    if i['status']=='running': raise HTTPException(409,'Wait for diagnosis to finish')
    return create_report(i)
@app.get('/api/reports/{key}')
@app.get('/api/reports/{key}/preview')
def report(key: str): return required('report',key)
@app.get('/api/reports/{key}/{fmt}')
def download(key: str,fmt: Literal['pdf','docx','json']):
    r=required('report',key)
    try: content=export(r,fmt)
    except Exception:
        logging.exception('Export failed for %s',key)
        raise HTTPException(500,'Export failed. Retry or download JSON.')
    mime={'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','json':'application/json'}[fmt]
    return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{key}.{fmt}"'})
@app.get('/api/data-sources')
def sources(): return {'status':'unavailable','message':'Live SNMP and monitoring API integrations are not implemented. Upload a monitoring export or run a labelled demo. Credentials are not collected.'}
@app.post('/api/data-sources/test')
def test_source(): raise HTTPException(501,'No live connector installed. No connection was attempted.')

dist=Path(__file__).resolve().parents[1]/'frontend'/'dist'
if dist.exists():
    app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}')
    def frontend(path: str):
        if path.startswith('api/'): raise HTTPException(404,'Unknown API endpoint')
        return FileResponse(dist/'index.html')
