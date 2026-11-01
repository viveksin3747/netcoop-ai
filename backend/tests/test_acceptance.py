"""Full scenario API acceptance checks, isolated from the user's saved history."""
import time
import xml.etree.ElementTree as ET
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.demo import SCENARIOS

@pytest.mark.parametrize('scenario_id',[s['id'] for s in SCENARIOS])
def test_every_demo_reaches_traceable_report(tmp_path,monkeypatch,scenario_id):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'acceptance.sqlite3'))
    with TestClient(app) as client:
        response=client.post('/api/demo/run',json={'scenario_id':scenario_id})
        assert response.status_code==202
        key=response.json()['id']
        for _ in range(150):
            incident=client.get('/api/incidents/'+key).json()
            if incident['report_id']:break
            time.sleep(.02)
        assert incident['report_id'] and incident['status'] in ('completed','inconclusive')
        assert len(incident['agents'])==6 and all(a['status']=='completed' for a in incident['agents'])
        ids={e['evidence_id'] for e in incident['evidence']}
        for agent in incident['agents']:
            for finding in agent['findings']:assert set(finding.get('evidence_ids',[]))<=ids
        report=client.get('/api/reports/'+incident['report_id']).json()
        assert report['incident']['id']==key and report['data_mode']=='simulated'
        assert report['incident']['evidence']==incident['evidence']
        graph=report['dependency_graph'];node_ids={n['id'] for n in graph['nodes']}
        assert len(node_ids)==len(graph['nodes'])
        assert all(e['source'] in node_ids and e['target'] in node_ids for e in graph['edges'])
        for diagram in graph['diagrams']:ET.fromstring(diagram)
        if scenario_id=='healthy-network':assert report['severity']=='healthy'
