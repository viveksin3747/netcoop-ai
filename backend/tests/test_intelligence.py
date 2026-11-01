import asyncio
from datetime import datetime,timedelta,timezone
import pytest
from backend import store,monitoring,live,speed
from backend.analytics import anomalies,topology
from backend.demo import scenario
from backend.schemas import Settings,Telemetry
from backend.orchestrator import new_incident,execute
from backend.reports import export

@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'intel.sqlite3'))

def seed(count,source='healthy-network'):
    for n in range(count):
        t=scenario(source);t.timestamp=datetime.now(timezone.utc)-timedelta(minutes=n+1)
        i=new_incident(t,Settings());i['status']='completed';store.put('incident',i['id'],i)

def test_historical_anomaly_requires_five_comparable_points():
    seed(4)
    t=scenario('healthy-network');t.devices[0].latency_ms=80
    i=new_incident(t,Settings())
    assert not anomalies(i,'performance_agent')
    t2=scenario('healthy-network');t2.timestamp=datetime.now(timezone.utc)-timedelta(minutes=10)
    old=new_incident(t2,Settings());old['status']='completed';store.put('incident',old['id'],old)
    found=anomalies(i,'performance_agent')
    assert len(found)==1 and found[0]['sample_count']==5
    assert found[0]['baseline_median']==12 and found[0]['threshold']==32
    assert len(found[0]['baseline_incident_ids'])==5

def test_history_sources_and_scenarios_are_separated():
    seed(6,'router-overload')
    t=scenario('healthy-network');t.devices[0].latency_ms=300
    assert not anomalies(new_incident(t,Settings()),'performance_agent')

def test_campus_topology_and_explainable_conflict():
    i=new_incident(scenario('campus-outage'),Settings());asyncio.run(execute(i['id']))
    i=store.get('incident',i['id']);top=i['topology']
    assert 'SW-01' in top['observed_devices']
    assert {'AP-01','SRV-01'}<=set(top['potential_devices'])
    assert any(g['name']=='Hostel A' and g['potentially_affected'] for g in top['groups'])
    ids={e['evidence_id'] for e in i['evidence']}
    assert all(e['evidence_id'] in ids for e in i['correlation']['explanation'])
    i=new_incident(scenario('multiple-causes'),Settings());asyncio.run(execute(i['id']));i=store.get('incident',i['id'])
    assert i['correlation']['confidence_category']=='insufficient evidence'
    assert i['correlation']['conflicts']
    assert any('Unresolved' in c['resolution'] for c in i['correlation']['conflicts'])

def test_anomalies_flow_through_agents_into_reports():
    seed(5)
    t=scenario('healthy-network');t.devices[0].latency_ms=80
    i=new_incident(t,Settings());asyncio.run(execute(i['id']));i=store.get('incident',i['id'])
    assert i['alerts']
    r=store.get('report',i['report_id'])
    section=next(s for s in r['sections'] if s['title']=='Historical anomaly alerts')
    assert 'historical median' in section['paragraphs'][0]

def test_scheduler_interval_persistence_and_stop(monkeypatch):
    store.put('monitor','state',dict(enabled=True,next_check_at=None))
    t=scenario('healthy-network');t.source_type='live';t.data_mode='observed'
    monkeypatch.setattr(live,'collect',lambda:(t,{}))
    monkeypatch.setattr(speed,'measure',lambda:{'status':'failed'})
    calls=[]
    def start(t,**kwargs):calls.append(kwargs);return {'id':'INC-test'}
    asyncio.run(monitoring.tick(start))
    config=monitoring.state()
    assert len(calls)==1 and config['last_incident_id']=='INC-test'
    delta=datetime.fromisoformat(config['next_check_at'])-datetime.fromisoformat(config['last_check_at'])
    assert delta.total_seconds()==300
    asyncio.run(monitoring.tick(start));assert len(calls)==1
    config['enabled']=False;store.put('monitor','state',config)
    asyncio.run(monitoring.tick(start));assert len(calls)==1

def test_scheduler_failure_is_recorded(monkeypatch):
    store.put('monitor','state',dict(enabled=True,next_check_at=None))
    def fail():raise ValueError('no connection')
    monkeypatch.setattr(live,'collect',fail)
    asyncio.run(monitoring.tick(lambda *a,**k:None))
    assert monitoring.state()['last_error']
    assert store.all_records('monitor-event')[0]['status']=='failed'

def test_period_calendar_and_report_contents():
    at=datetime(2026,11,1,0,5,tzinfo=monitoring.IST)
    start,end=monitoring.bounds('monthly',at,True)
    assert start.day==1 and start.month==10 and end.month==11
    start,end=monitoring.bounds('weekly',at)
    assert start.weekday()==0 and (end-start).days==7
    t=scenario('healthy-network');t.source_type='live';t.data_mode='observed'
    i=new_incident(t,Settings());asyncio.run(execute(i['id']))
    report=monitoring.aggregate('monthly')
    assert len(report['incidents'])==1 and report['incidents'][0]['id']==i['id']
    assert export(report,'pdf').startswith(b'%PDF')
    assert export(report,'docx').startswith(b'PK')
    one=monitoring.aggregate('weekly',previous=True,automatic=True)
    two=monitoring.aggregate('weekly',previous=True,automatic=True)
    assert one['report_id']==two['report_id']

def test_no_data_period_does_not_claim_health():
    r=monitoring.aggregate('monthly')
    assert r['status']=='inconclusive' and not r['incidents']

def test_interval_migration_preserves_enabled_state():
    store.put('monitor','state',dict(enabled=True,interval_minutes=15,last_check_at='2026-11-01T01:00:00+00:00',next_check_at='2026-11-01T01:15:00+00:00'))
    migrated=monitoring.state()
    assert migrated['enabled'] and migrated['interval_minutes']==5
    assert migrated['next_check_at']=='2026-11-01T01:05:00+00:00'
    assert store.get('monitor','state')['interval_minutes']==5
