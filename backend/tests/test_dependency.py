import asyncio
from io import BytesIO
from zipfile import ZipFile
from backend.demo import scenario
from backend.schemas import Settings,Telemetry,now
from backend.orchestrator import new_incident,execute
from backend.dependency import build,pages,svg
from backend import store
from backend.reports import create_report,export

def test_dependency_graph_and_report_formats(tmp_path,monkeypatch):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'graph.sqlite3'))
    i=new_incident(scenario('campus-outage'),Settings());asyncio.run(execute(i['id']))
    i=store.get('incident',i['id']);g=i['dependency_graph']
    assert any(e['source']=='SW-01' and e['target']=='AP-01' for e in g['edges'])
    assert any(n['label']=='Hostel A' and n['impact']=='potential' for n in g['nodes'])
    assert any(n['label']=='Learning portal' and n['impact']=='potential' for n in g['nodes'])
    ids={e['evidence_id'] for e in i['evidence']}
    assert all(set(n['evidence_ids'])<=ids for n in g['nodes'])
    r=store.get('report',i['report_id'])
    assert r['dependency_graph']==g
    assert len(g['diagrams'])==len(pages(g)) and all('<svg' in s for s in g['diagrams'])
    assert export(r,'pdf').startswith(b'%PDF')
    with ZipFile(BytesIO(export(r,'docx'))) as doc:
        assert any(p.startswith('word/media/') for p in doc.namelist())

def test_graph_cycles_missing_topology_and_escaping(tmp_path,monkeypatch):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'graph.sqlite3'))
    t=Telemetry(timestamp=now(),devices=[{'device_id':'A','services':['<script>alert(1)</script>']},{'device_id':'B'}],connections=[{'source_device':'A','target_device':'B'},{'source_device':'B','target_device':'A'}])
    i=new_incident(t,Settings());g=build(i)
    assert len(g['nodes'])==4
    assert '<script>' not in ''.join(g['diagrams']) and '&lt;script&gt;' in ''.join(g['diagrams'])
    t=Telemetry(timestamp=now(),devices=[{'device_id':'GATEWAY'}]);i=new_incident(t,Settings());g=build(i)
    assert not any(n['kind']=='service' for n in g['nodes'])
    assert len(g['nodes'])==2

def test_device_ids_cannot_collide_with_internal_graph_nodes(tmp_path,monkeypatch):
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'ids.sqlite3'))
    t=Telemetry(timestamp=now(),devices=[{'device_id':'assessment','department':'Engineering'},
        {'device_id':'group:0'},{'device_id':'action:0'}],
        connections=[{'source_device':'assessment','target_device':'group:0'}])
    graph=build(new_incident(t,Settings()))
    ids=[node['id'] for node in graph['nodes']]
    assert len(ids)==len(set(ids))
    assert any(edge['source']=='assessment' and edge['target']=='group:0' for edge in graph['edges'])
