import httpx
from backend import speed

def test_speed_calculation_and_failure(monkeypatch):
    real_client=httpx.Client
    def handler(request):
        if request.method=='POST': return httpx.Response(503)
        return httpx.Response(200,content=b'x'*speed.DOWNLOAD_BYTES)
    monkeypatch.setattr(speed.httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handler)))
    result=speed.measure()
    assert result['download_mbps']>0
    assert result['upload_mbps'] is None
    assert result['status']=='partial'
    assert result['measurements'][0]['bytes']==10_000_000
    m=result['measurements'][0]
    assert abs(m['mbps']-m['bytes']*8/m['elapsed_seconds']/1e6)/m['mbps']<.01

def test_report_speed_sections(tmp_path,monkeypatch):
    import asyncio
    from backend.demo import scenario
    from backend.orchestrator import new_incident,execute
    from backend.schemas import Settings
    from backend import store
    from backend.reports import create_report,export
    monkeypatch.setenv('NETCOOP_DB',str(tmp_path/'speed.sqlite3'))
    i=new_incident(scenario('healthy-network'),Settings());asyncio.run(execute(i['id']))
    i=store.get('incident',i['id'])
    i['speed_test']=dict(download_mbps=42.5,upload_mbps=None,status='partial',provider='Cloudflare',
        started_at='start',completed_at='end',related_report_id=i['report_id'],method='method',limitation='limited',
        measurements=[],errors=['Upload failed'])
    r=create_report(i)
    section=next(s for s in r['sections'] if s['title']=='Internet download and upload speed')
    assert 'Download: 42.5 Mbps' in section['paragraphs'] and 'Upload: Unavailable' in section['paragraphs']
    assert r['speed_test']==i['speed_test']
    assert export(r,'pdf').startswith(b'%PDF')
