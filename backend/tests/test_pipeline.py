import asyncio
import json
import time
from io import BytesIO
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from docx import Document
from backend.main import app
from backend import store
from backend.demo import scenario, SCENARIOS
from backend.schemas import Telemetry, Settings, now, AGENTS
from backend.telemetry import parse_upload, quality
from backend.orchestrator import new_incident, execute
from backend.agents import REGISTRY
from backend.reports import create_report, export

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch): monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'test.sqlite3'))

def run(key,settings=None):
    i=new_incident(scenario(key),settings or Settings())
    asyncio.run(execute(i['id']))
    return store.get('incident',i['id'])

@pytest.mark.parametrize('key,expected',[
 ('router-overload','Router overload'),('network-congestion','Network congestion'),
 ('connectivity-failure','Connectivity failure'),('resource-failure','Infrastructure resource failure'),
 ('healthy-network','No fault observed in this snapshot')])
def test_scenarios(key,expected):
    i=run(key)
    assert i['correlation']['root_cause']==expected
    assert i['status']=='completed'
    assert len(i['agents'])==6
    assert all(a['status']=='completed' for a in i['agents'])
    ids={e['evidence_id'] for e in i['evidence']}
    assert ids
    for a in i['agents']:
        for f in a['findings']: assert set(f['evidence_ids'])<=ids
    assert i['recommendations'][0]['advisory'] and not i['recommendations'][0]['performed']
    if key=='healthy-network': assert i['correlation']['severity']=='healthy'
    r=store.get('report',i['report_id'])
    assert r['incident']['evidence']==i['evidence']
    assert r['data_mode']=='simulated'

def test_missing_and_stale():
    t=Telemetry(timestamp='2020-01-01T00:00:00Z',devices=[{'device_id':'R1'}])
    assert t.devices[0].cpu_usage_percent is None
    i=new_incident(t,Settings());asyncio.run(execute(i['id']));i=store.get('incident',i['id'])
    assert i['status']=='inconclusive' and i['correlation']['confidence']==0
    assert i['quality']['stale'] and i['quality']['core_completeness']==0

@pytest.mark.parametrize('key,expected',[
 ('slow-response','Inconclusive - more evidence required'),
 ('unstable-calls','Inconclusive - more evidence required'),
 ('wifi-disconnected','Connectivity failure'),
 ('server-cpu','Compute resource pressure'),
 ('overheating','Infrastructure resource failure'),
 ('multiple-causes','Inconclusive - more evidence required'),
 ('missing-data','Inconclusive - more evidence required')])
def test_additional_scenarios(key,expected):
    i=run(key)
    assert i['correlation']['root_cause']==expected
    assert i['report_id']

@pytest.mark.parametrize('key,action_fragment',[
 ('severe-packet-loss','wired connection'),('branch-outage','shared power'),
 ('router-memory','memory'),('thermal-emergency','Do not touch hot equipment'),
 ('stale-outage','fresh measurements')])
def test_bad_scenario_guidance(key,action_fragment):
    i=run(key)
    assert action_fragment in i['recommendations'][0]['action']
    assert i['report_id'] and i['recommendations'][0]['verification']
    assert i['correlation']['severity']!='healthy'

@pytest.mark.parametrize('patch',[{'cpu_usage_percent':101},{'latency_ms':-1},{'packet_loss_percent':float('nan')},{'password':'secret'}])
def test_invalid_metrics_and_secrets(patch):
    with pytest.raises(ValidationError): Telemetry(timestamp=now(),devices=[dict(device_id='R1',**patch)])

def test_upload_normalization():
    csv=f'device_id,timestamp,cpu_usage_percent,latency_ms\nR1,{now()},,20\n'
    t=parse_upload('metrics.csv',csv.encode())
    assert t.devices[0].cpu_usage_percent is None and t.devices[0].latency_ms==20
    assert t.source_type=='upload' and t.source_reference=='metrics.csv'
    with pytest.raises(ValueError):parse_upload('x.txt',b'arbitrary unstructured log')
    with pytest.raises(ValueError):parse_upload('x.csv',b'x'*2097153)

def test_bad_topology_and_duplicate():
    with pytest.raises(ValidationError):Telemetry(timestamp=now(),devices=[{'device_id':'R1'},{'device_id':'R1'}])
    with pytest.raises(ValidationError):Telemetry(timestamp=now(),devices=[{'device_id':'R1'}],connections=[{'source_device':'R1','target_device':'R2'}])
    with pytest.raises(ValidationError):Telemetry(timestamp='2026-01-01T00:00:00',devices=[{'device_id':'R1'}])

def test_disabled_agent_partial():
    i=run('router-overload',Settings(enabled_agents=[a for a in AGENTS if a!='infrastructure_agent']))
    assert i['status']=='partial'
    assert i['agents'][1]['status']=='skipped'
    assert store.get('report',i['report_id'])['status']=='partial'

def test_timeout_retry_and_partial(monkeypatch):
    def slow(*args): time.sleep(.15);return {}
    monkeypatch.setitem(REGISTRY,'performance_agent',slow)
    i=run('router-overload',Settings(timeout_seconds=.1,retry_limit=1))
    assert i['agents'][0]['status']=='failed' and i['agents'][0]['attempt']==2
    assert i['status']=='partial'

def test_failure_recovery(monkeypatch):
    count=[0]; original=REGISTRY['performance_agent']
    def fail_once(*args):
        count[0]+=1
        if count[0]==1: raise RuntimeError('Test transient failure')
        return original(*args)
    monkeypatch.setitem(REGISTRY,'performance_agent',fail_once)
    i=run('healthy-network');assert i['agents'][0]['attempt']==2 and i['status']=='completed'
    assert 'error' not in i['agents'][0]

def test_history_order_survives_old_record_update():
    older=run('healthy-network');newer=run('router-overload')
    store.put('incident',older['id'],older)
    assert store.all_records('incident')[0]['id']==newer['id']

def test_conflicting_hypotheses_and_stale_confidence():
    t=scenario('router-overload');t.devices[0].bandwidth_utilization_percent=98
    i=new_incident(t,Settings());asyncio.run(execute(i['id']));i=store.get('incident',i['id'])
    assert i['status']=='inconclusive' and len(i['correlation']['hypotheses'])==2
    fresh=run('router-overload')['correlation']['confidence']
    t=scenario('router-overload');t.timestamp=Telemetry(timestamp='2020-01-01T00:00:00Z',devices=[{'device_id':'r'}]).timestamp
    i=new_incident(t,Settings());asyncio.run(execute(i['id']));i=store.get('incident',i['id'])
    assert i['correlation']['confidence']<fresh

def test_actual_exports_and_immutable_snapshot():
    i=run('router-overload');r=store.get('report',i['report_id'])
    pdf=export(r,'pdf');assert pdf.startswith(b'%PDF-') and len(pdf)>3000
    docx=Document(BytesIO(export(r,'docx')))
    text='\n'.join(p.text for p in docx.paragraphs)
    assert r['conclusion'] in text and 'Evidence register' in text
    payload=json.loads(export(r,'json'));assert payload==r
    assert store.update_recommendation(i['id'],i['recommendations'][0]['id'],'Completed')
    assert store.get('report',r['report_id'])['incident']['recommendations'][0]['status']=='Pending'
    fresh=create_report(store.get('incident',i['id']))
    assert fresh['incident']['recommendations'][0]['status']=='Completed'

def test_failed_and_inconclusive_reports():
    i=new_incident(scenario('router-overload'),Settings());i['status']='failed'
    r=create_report(i);assert r['status']=='failed' and export(r,'pdf').startswith(b'%PDF')
    t=Telemetry(timestamp=now(),devices=[{'device_id':'r'}]);i=new_incident(t,Settings());asyncio.run(execute(i['id']))
    r=store.get('report',store.get('incident',i['id'])['report_id']);assert r['status']=='inconclusive'

def test_api_journey_and_access():
    with TestClient(app) as c:
        assert c.get('/api/demo/scenarios').status_code==200
        resp=c.post('/api/demo/run',json={'scenario_id':'router-overload'});assert resp.status_code==202
        key=resp.json()['id']
        for _ in range(100):
            i=c.get(f'/api/incidents/{key}').json()
            if i['report_id']:break
            time.sleep(.02)
        assert i['report_id']
        rid=i['report_id'];r=c.get(f'/api/reports/{rid}/preview').json()
        assert r['incident']['id']==key
        for fmt,mime in [('pdf','application/pdf'),('json','application/json'),('docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document')]:
            response=c.get(f'/api/reports/{rid}/{fmt}')
            assert response.status_code==200 and mime in response.headers['content-type']
            assert rid in response.headers['content-disposition']
        assert c.post('/api/data-sources/test').status_code==501
        assert c.get('/api/reports/not-a-report').status_code==404
        assert c.get('/api/health',headers={'host':'attacker.example'}).status_code==403
        assert c.post('/api/demo/run',json={'scenario_id':'healthy-network'},headers={'origin':'https://attacker.example'}).status_code==403
        assert len(c.get('/api/incidents').json())==1
    with TestClient(app) as c: assert c.get(f'/api/incidents/{key}').json()['report_id']==rid

def test_upload_api():
    with TestClient(app) as c:
        raw=scenario('healthy-network').model_dump(mode='json')
        response=c.post('/api/telemetry/upload',files={'file':('test.json',json.dumps(raw),'application/json')})
        assert response.status_code==200
        assert response.json()['telemetry']['source_type']=='upload'
        assert c.post('/api/telemetry/upload',files={'file':('test.exe',b'bad')}).status_code==422
        assert c.put('/api/settings',json={'enabled_agents':['imaginary']}).status_code==422
