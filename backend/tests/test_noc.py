import asyncio
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import store
from backend.demo import scenario
from backend.orchestrator import new_incident,execute
from backend.schemas import Settings

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'noc.sqlite3'))

def test_recommendation_confirmation_and_history():
    i=new_incident(scenario('router-overload'),Settings());asyncio.run(execute(i['id']));i=store.get('incident',i['id']);key=i['recommendations'][0]['id'];report=i['report_id']
    with TestClient(app) as c:
        assert c.put(f'/api/recommendations/{key}/status',json={'status':'Completed'}).status_code==422
        assert c.put(f'/api/recommendations/{key}/status',json={'status':'Completed','operator_confirmed':True}).status_code==422
        assert c.put(f'/api/recommendations/{key}/status',json={'status':'In Progress'}).status_code==200
        assert c.put(f'/api/recommendations/{key}/status',json={'status':'Completed','operator_confirmed':True,'verification_note':'Repeated checks and verified recovery with the device owner.'}).status_code==200
        detail=c.get(f'/api/recommendation-details/{key}').json()
        assert detail['recommendation']['completion_verification']['operator_confirmed']
        assert len(detail['recommendation']['history'])==2
        assert detail['incident']['id']==i['id']
        assert store.get('report',report)['incident']['recommendations'][0]['status']=='Pending'
        assert c.get('/api/recommendation-details/unknown').status_code==404

def test_health_backup_and_existing_history_survive_reorganization():
    i=new_incident(scenario('healthy-network'),Settings());asyncio.run(execute(i['id']))
    store.put('monitor','state',dict(enabled=False,next_check_at='2026-12-01T00:00:00+00:00',last_check_at='2026-11-01T00:00:00+00:00'))
    with TestClient(app) as c:
        status=c.get('/api/system/status').json();assert status['api']=='online' and status['database']=='available'
        assert status['monitoring']['next_check_at']=='2026-12-01T00:00:00+00:00'
        backup=c.get('/api/workspace/export');assert backup.json()['incidents'][0]['id']==i['id']
        assert 'attachment' in backup.headers['content-disposition']
        assert c.get('/api/documentation').status_code==200
        assert len(c.get('/api/demo/scenarios').json())==19
    with TestClient(app) as c:
        assert c.get('/api/incidents/'+i['id']).status_code==200
        assert not c.get('/api/monitoring').json()['enabled']
