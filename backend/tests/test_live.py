import asyncio
import json
from types import SimpleNamespace
from backend import live, store
from backend.orchestrator import new_incident, execute
from backend.schemas import Settings
from fastapi.testclient import TestClient
from backend.main import app
import time
import pytest

@pytest.fixture(autouse=True)
def mock_speed(monkeypatch):
    from backend import speed
    monkeypatch.setattr(speed,'measure',lambda:dict(download_mbps=20,upload_mbps=10,status='completed',provider='Test',started_at='start',completed_at='end',method='test',limitation='test',measurements=[],errors=[]))

def test_recommendation_retest_link(tmp_path,monkeypatch):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'retest.sqlite3'))
    from backend.demo import scenario
    original=new_incident(scenario('router-overload'),Settings());asyncio.run(execute(original['id']))
    original=store.get('incident',original['id']);rec=original['recommendations'][0]
    from backend.schemas import Telemetry, now
    t=Telemetry(timestamp=now(),source_type='live',data_mode='observed',devices=[dict(device_id='DEFAULT-GATEWAY',ip_address='192.168.1.1',latency_ms=4,status='online',packet_loss_percent=0)])
    monkeypatch.setattr(live,'collect',lambda:(t,{'gateway':'192.168.1.1'}))
    with TestClient(app) as client:
        response=client.post(f"/api/recommendations/{rec['id']}/test")
        assert response.status_code==202
        key=response.json()['id']
        for _ in range(100):
            i=client.get(f'/api/incidents/{key}').json()
            if i['report_id']:break
            time.sleep(.02)
        assert i['test_context']['original_incident_id']==original['id']
        assert not i['test_context']['target_matches_original']
        report=client.get('/api/reports/'+i['report_id']).json()
        assert report['speed_test']['download_mbps']==20
        assert any(s['title']=='Live recommendation retest' for s in report['sections'])
        assert store.get('incident',original['id'])['recommendations'][0]['status']=='Pending'

def test_live_reports_preserve_actual_probe_results(tmp_path,monkeypatch):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'live.sqlite3'))
    raw={'gateway':'192.168.1.1','adapter':'Test adapter','gateway_candidates':1,
         'samples':[{'status':'Success','latency_ms':n} for n in (2,4,6,8,10)]}
    monkeypatch.setattr(live.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(raw)))
    t,sample=live.collect()
    assert t.source_type=='live' and t.data_mode=='observed'
    assert t.devices[0].latency_ms==6 and t.devices[0].packet_loss_percent==0
    assert t.devices[0].cpu_usage_percent is None
    i=new_incident(t,Settings());asyncio.run(execute(i['id']))
    i=store.get('incident',i['id']);r=store.get('report',i['report_id'])
    assert r['live_measurements']['samples']==raw['samples']
    assert r['status']=='inconclusive'

def test_no_ping_reply_does_not_claim_offline(tmp_path,monkeypatch):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'live.sqlite3'))
    raw={'gateway':'192.168.1.1','adapter':'Test adapter','gateway_candidates':1,
         'samples':[{'status':'TimedOut','latency_ms':None}]*5}
    monkeypatch.setattr(live.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(raw)))
    t,_=live.collect()
    assert t.devices[0].status=='unknown' and t.devices[0].latency_ms is None
