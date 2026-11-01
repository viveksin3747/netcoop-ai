"""Persisted five-minute app scheduler and calendar period reports (India time)."""
import asyncio
import logging
from datetime import datetime,timedelta,timezone
from . import store,live,speed
from .agents import uid
from .schemas import now

IST=timezone(timedelta(hours=5,minutes=30))
INTERVAL=300
def state():
    config=dict(enabled=False,interval_minutes=5,next_check_at=None,last_check_at=None,last_success_at=None,last_incident_id=None,last_error=None,
        timezone='Asia/Calcutta') | (store.get('monitor','state') or {})
    if config['interval_minutes']!=INTERVAL//60:
        config['interval_minutes']=INTERVAL//60
        if config['enabled']:
            config['next_check_at']=(datetime.fromisoformat(config['last_check_at'])+timedelta(seconds=INTERVAL)).isoformat() if config.get('last_check_at') else now()
        store.put('monitor','state',config)
    if not config['last_success_at'] and config.get('last_incident_id'):
        incident=store.get('incident',config['last_incident_id'])
        if incident:config['last_success_at']=incident['telemetry']['timestamp']
    return config

def bounds(period,at=None,previous=False):
    at=(at or datetime.now(IST)).astimezone(IST)
    start=at.replace(hour=0,minute=0,second=0,microsecond=0)
    if period=='weekly':
        start-=timedelta(days=start.weekday())
        if previous:start-=timedelta(days=7)
        end=start+timedelta(days=7)
    else:
        start=start.replace(day=1)
        if previous:start=(start-timedelta(days=1)).replace(day=1)
        end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    return start,end

def aggregate(period,at=None,previous=False,automatic=False):
    start,end=bounds(period,at,previous)
    if automatic:
        existing=store.get('period-index',f'{period}:{start.isoformat()}')
        if existing:return store.get('report',existing['report_id'])
    incidents=[i for i in store.all_records('incident') if i['telemetry']['source_type']=='live' and
        start<=datetime.fromisoformat(i['created_at'])<end and i['status']!='running']
    events=[e for e in store.all_records('monitor-event') if start<=datetime.fromisoformat(e['timestamp'])<end]
    failed=[e for e in events if e['status']=='failed']
    rid=uid('RPT')
    averages={}
    for name in ('download_mbps','upload_mbps'):
        vals=[i['speed_test'][name] for i in incidents if i.get('speed_test',{}).get(name) is not None]
        averages[name]=dict(count=len(vals),average=round(sum(vals)/len(vals),2) if vals else None,min=min(vals) if vals else None,max=max(vals) if vals else None)
    network_stats={}
    for metric in ('latency_ms','packet_loss_percent','bandwidth_utilization_percent','cpu_usage_percent','memory_usage_percent'):
        values=[d[metric] for i in incidents for d in i['telemetry']['devices'] if d.get(metric) is not None]
        network_stats[metric]=dict(count=len(values),average=round(sum(values)/len(values),2) if values else None,min=min(values) if values else None,max=max(values) if values else None)
    sections=[dict(title=f'{period.title()} live network summary',paragraphs=[
        f"Period: {start.isoformat()} to {end.isoformat()} (end exclusive). Generated: {now()}.",
        f"Recorded checks: {len(incidents)} | Recorded scheduler failures: {len(failed)} | Current monitoring interval: 5 minutes. Earlier checks may use a previous interval; see actual timestamps.",
        'Coverage includes only saved checks. Server downtime, sleep, disabled monitoring and missing readings are not counted as healthy uptime. This report does not claim full-period availability.',
        f"Severity counts: "+str({s:sum((i.get('correlation') or {}).get('severity')==s for i in incidents) for s in ('critical','high','healthy','unknown')})]),
        dict(title='Network measurement statistics',paragraphs=[f"{key.replace('_',' ')}: {value['count']} measurements; average {value['average'] if value['average'] is not None else 'unavailable'}; lowest {value['min']}; highest {value['max']}." for key,value in network_stats.items()]),
        dict(title='Internet speed statistics',paragraphs=[f"{key.replace('_',' ')}: {value['count']} measurements; average {value['average'] if value['average'] is not None else 'unavailable'}; lowest {value['min']}; highest {value['max']}." for key,value in averages.items()]),
        dict(title='Recorded monitoring events',paragraphs=[f"{e['timestamp']}: {e['status']} — {e.get('message','')}" for e in events] or ['No scheduler events recorded.'])]
    for i in sorted(incidents,key=lambda i:i['created_at']):
        from .dependency import build
        graph=build(i)
        sections.append(dict(title='Dependency graph for '+i['id'],dependency_graph=graph,
            paragraphs=[graph['legend'],graph['limitation']]+[f"{e['source']} -> {e['target']}: {e['label']}" for e in graph['edges']]))
        c=i.get('correlation') or {}
        lines=[f"Incident {i['id']} | {i['created_at']} | {i['status']} | {c.get('root_cause','Unavailable')}",
            f"Confidence: {c.get('confidence')} ({c.get('confidence_category')}) | Report: {i.get('report_id')}",
            f"Source: {i['telemetry']['source_reference']} | Observed: {i['telemetry']['timestamp']}"]
        for device in i['telemetry']['devices']:
            lines.append('Device '+device['device_id']+': '+'; '.join(f"{k.replace('_',' ')}: {v}" for k,v in device.items() if v is not None and k!='device_id'))
        measured=i.get('speed_test')
        if measured:
            lines.append(f"Internet speed: download {measured['download_mbps'] if measured['download_mbps'] is not None else 'unavailable'} Mbps; upload {measured['upload_mbps'] if measured['upload_mbps'] is not None else 'unavailable'} Mbps. Status: {measured['status']}; provider: {measured['provider']}; time: {measured['started_at']} to {measured['completed_at']}.")
            lines.extend(measured['errors'])
        else:lines.append('Internet speed measurements unavailable for this check.')
        for agent in i['agents']:
            lines.append(f"{agent['agent_id'].replace('_',' ').title()}: {agent['status']}. Started: {agent.get('started_at','not executed')}; ended: {agent.get('ended_at','not executed')}; attempts: {agent.get('attempt',0)}.")
            lines.extend(f"Finding: {f['finding']} | Evidence: {', '.join(f.get('evidence_ids',[]))}" for f in agent['findings'])
            lines.extend(agent['limitations'])
            if agent.get('error'):lines.append(agent['error'])
        lines += [f"Evidence {e['evidence_id']}: {e['explanation']} | Source: {e['source_reference']}" for e in i['evidence']]
        lines += ['Recommendation: '+r['action']+' Verify: '+r['verification'] for r in i['recommendations']]
        lines += [f"Timeline: {e['timestamp']} | {e['event']}" for e in i['timeline']]
        lines += [f"Competing explanations: {' vs '.join(conflict['hypotheses'])}. {conflict['resolution']} Evidence: {', '.join(conflict['evidence_ids'])}" for conflict in c.get('conflicts',[])]
        lines += ['Historical change alert: '+alert['message'] for alert in i.get('alerts',[])]
        sections.append(dict(title='Check '+i['id'],paragraphs=lines))
    report=dict(report_id=rid,incident_id='period-summary',report_type=period,generated_at=now(),version='1.0',
        status='completed' if incidents else 'inconclusive',severity='info',data_mode='observed',source_type='live',
        conclusion=f'{period.title()} report of {len(incidents)} recorded live checks. Missing coverage is unknown.',
        period_start=start.isoformat(),period_end=end.isoformat(),sections=sections,incidents=incidents,monitoring_events=events,speed_statistics=averages,network_statistics=network_stats)
    store.put('report',rid,report)
    if automatic:store.put('period-index',f'{period}:{start.isoformat()}',dict(report_id=rid))
    return report

async def tick(start_diagnosis):
    config=state()
    if not config['enabled']:return
    # Generate the last closed calendar periods once. Current periods can be exported on demand.
    for period in ('weekly','monthly'):aggregate(period,previous=True,automatic=True)
    current=datetime.now(timezone.utc)
    due=config.get('next_check_at')
    if due and current<datetime.fromisoformat(due):return
    if live.lock.locked() or speed.lock.locked():return
    config['next_check_at']=(current+timedelta(seconds=INTERVAL)).isoformat()
    config['last_check_at']=current.isoformat()
    store.put('monitor','state',config)
    try:
        async with live.lock,speed.lock:
            t,_=await asyncio.to_thread(live.collect)
            measured=await asyncio.to_thread(speed.measure);measured['related_report_id']=None
            incident=start_diagnosis(t,speed_test=measured)
        config.update(last_incident_id=incident['id'],last_success_at=now(),last_error=None)
        event=dict(id=uid('MON'),timestamp=now(),status='measured',incident_id=incident['id'],message='5-minute live check collected; see incident for diagnosis and speed failures.')
    except Exception:
        logging.exception('Scheduled check failed')
        config['last_error']='Scheduled check failed. Check the connection and server logs.'
        event=dict(id=uid('MON'),timestamp=now(),status='failed',message=config['last_error'])
    # Respect a stop request issued while a measurement was running.
    current_config=state();config['enabled']=current_config['enabled']
    store.put('monitor','state',config);store.put('monitor-event',event['id'],event)

async def loop(start_diagnosis):
    while True:
        try:await tick(start_diagnosis)
        except Exception:logging.exception('Monitoring scheduler error')
        await asyncio.sleep(10)
