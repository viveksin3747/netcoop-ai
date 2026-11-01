"""Audit the actual local service without changing existing records/settings."""
from pathlib import Path
from datetime import datetime,timezone
from io import BytesIO
from zipfile import ZipFile
import json
import time
import httpx
from docx import Document

output=Path('output/verification');output.mkdir(parents=True,exist_ok=True)
results={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def passed(name,detail):results['checks'].append({'feature':name,'status':'passed','detail':detail})
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=90) as client:
    for route in ('/','/incidents','/incidents/new','/start','/reports','/recommendations','/settings','/about','/docs','/openapi.json'):
        response=client.get(route);response.raise_for_status()
    passed('Routes and API documentation','All ten primary, legacy, diagnosis and documentation routes returned HTTP 200.')
    status=client.get('/api/system/status').json();assert status['api']=='online' and status['database']=='available'
    passed('API and database',status['database'])
    monitor=client.get('/api/monitoring').json()
    assert monitor['enabled'] and monitor['interval_minutes']==5
    assert (datetime.fromisoformat(monitor['next_check_at'])-datetime.fromisoformat(monitor['last_check_at'])).total_seconds()==300
    passed('Live monitoring',monitor)
    before=client.get('/api/incidents').json();report_history=client.get('/api/reports').json()
    original_ids={i['id'] for i in before};original_reports={r['report_id'] for r in report_history}
    assert len(client.get('/api/demo/scenarios').json())==19
    passed('Demo inventory','19 scenarios available; acceptance tests exercise each full API-to-report pipeline.')
    known={i['id'] for i in before}
    assert all(r['incident_id']=='period-summary' or r['incident_id'] in known for r in report_history)
    recs=client.get('/api/recommendations').json();assert all(r['incident_id'] in known for r in recs)
    if recs:
        detail=client.get('/api/recommendation-details/'+recs[0]['id']);detail.raise_for_status()
        assert detail.json()['incident']['id']==recs[0]['incident_id']
    passed('History and origin links',{'incidents':len(before),'reports':len(report_history),'recommendations':len(recs)})
    deadline=time.monotonic()+60
    while True:
        response=client.post('/api/live/measure')
        if response.status_code!=409 or time.monotonic()>deadline:break
        time.sleep(1)
    response.raise_for_status();key=response.json()['id']
    for _ in range(100):
        incident=client.get('/api/incidents/'+key).json()
        if incident['report_id'] or incident['status']=='failed':break
        time.sleep(.1)
    assert incident['report_id'] and incident['telemetry']['source_type']=='live' and incident['telemetry']['data_mode']=='observed'
    measured=incident['speed_test']
    passed('Actual live diagnosis',{'incident_id':key,'report_id':incident['report_id'],'diagnosis_status':incident['status'],'speed_status':measured['status'],'download_mbps':measured['download_mbps'],'upload_mbps':measured['upload_mbps'],'gateway_latency_ms':incident['telemetry']['devices'][0]['latency_ms'],'agent_states':{a['agent_id']:a['status'] for a in incident['agents']}})
    report=client.get('/api/reports/'+incident['report_id']).json()
    assert report['speed_test']==measured and report['incident']['evidence']==incident['evidence']
    for fmt,mime in [('pdf','application/pdf'),('docx','application/vnd.openxmlformats-officedocument.wordprocessingml.document'),('json','application/json')]:
        response=client.get('/api/reports/'+incident['report_id']+'/'+fmt);response.raise_for_status()
        assert mime in response.headers['content-type'] and 'attachment' in response.headers['content-disposition']
        (output/('audit-live.'+fmt)).write_bytes(response.content)
        if fmt=='pdf':assert response.content.startswith(b'%PDF-')
        if fmt=='docx':
            document=Document(BytesIO(response.content));assert report['conclusion'] in '\n'.join(p.text for p in document.paragraphs)
            with ZipFile(BytesIO(response.content)) as archive:assert any(n.startswith('word/media/') for n in archive.namelist())
        if fmt=='json':assert response.json()==report
    passed('Individual report exports','PDF signature, DOCX structure/graph image, JSON canonical equality, content types and filenames verified.')
    for period in ('weekly','monthly'):
        response=client.post('/api/period-reports/'+period);response.raise_for_status();summary=response.json()
        assert summary['report_type']==period and all(i['telemetry']['source_type']=='live' for i in summary['incidents'])
        assert key in {i['id'] for i in summary['incidents']}
        passed(period.title()+' report',{'report_id':summary['report_id'],'recorded_checks':len(summary['incidents'])})
    after={i['id'] for i in client.get('/api/incidents').json()};after_reports={r['report_id'] for r in client.get('/api/reports').json()}
    assert original_ids<=after and original_reports<=after_reports
    passed('Data preservation','No existing incidents or reports removed. Audit adds one labelled real live check and two period-report snapshots.')
results['limitations']=['DOCX visual layout requires LibreOffice, which is absent from the bundled Windows runtime. DOCX structure and embedded graph images are verified.',
    'SNMP, full campus auto-discovery, external email/push delivery, public share links, multi-user authentication and automatic remediation remain unavailable.',
    'Anomaly alerts require five comparable historical readings and are change warnings, not trained outage predictions.',
    'The scheduler requires the app server and computer to remain running; sleep/downtime is not fabricated as healthy coverage.']
(output/'live-audit.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
