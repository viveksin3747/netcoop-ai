"""Explainable topology, robust historical comparisons and conflict assessment."""
from datetime import datetime
from statistics import median
from . import store
from .agents import uid

RULES={
 'latency_ms':(20,'ms'), 'packet_loss_percent':(2,'%'),
 'bandwidth_utilization_percent':(15,'%'), 'cpu_usage_percent':(15,'%'),
 'memory_usage_percent':(15,'%')}

def anomalies(incident,agent_id):
    metrics = ('latency_ms','packet_loss_percent','bandwidth_utilization_percent') if agent_id=='performance_agent' else ('cpu_usage_percent','memory_usage_percent')
    t=incident['telemetry']; timestamp=datetime.fromisoformat(t['timestamp'].replace('Z','+00:00'))
    candidates=[]
    for old in store.all_records('incident'):
        ot=old['telemetry']
        if old['id']==incident['id'] or old['status']=='running': continue
        if any(ot[k]!=t[k] for k in ('source_type','data_mode','network_id')):continue
        # Never mix different demo scenarios, gateway addresses or future observations.
        if t['source_type']=='demo' and ot['source_reference']!=t['source_reference']:continue
        observed=datetime.fromisoformat(ot['timestamp'].replace('Z','+00:00'))
        if not 0 < (timestamp-observed).total_seconds() <= 30*86400:continue
        candidates.append(old)
    candidates.sort(key=lambda i:i['telemetry']['timestamp'],reverse=True)
    output=[]
    for d in t['devices']:
        for metric in metrics:
            value=d.get(metric)
            if value is None: continue
            points=[]; refs=[]; seen=set()
            for old in candidates:
                stamp=old['telemetry']['timestamp']
                if stamp in seen:continue
                od=next((x for x in old['telemetry']['devices'] if x['device_id']==d['device_id'] and x.get('ip_address')==d.get('ip_address')),None)
                if od is not None and od.get(metric) is not None:
                    points.append(od[metric]);refs.append(old['id']);seen.add(stamp)
                if len(points)==20:break
            if len(points)<5:continue
            baseline=median(points);mad=median([abs(x-baseline) for x in points])
            floor,unit=RULES[metric]
            margin=max(floor,abs(baseline)*.5,3*1.4826*mad)
            if value<=baseline+margin:continue
            output.append(dict(evidence_id=uid('EV'),incident_id=incident['id'],source_agent=agent_id,
                device_id=d['device_id'],metric=metric,observed_value=value,threshold=round(baseline+margin,3),
                unit=unit,timestamp=t['timestamp'],source_reference=t['source_reference'],abnormal=True,
                kind='historical_anomaly',baseline_median=baseline,baseline_mad=mad,sample_count=len(points),baseline_incident_ids=refs,
                explanation=f"{d['device_id']}: {metric} rose to {value} {unit}; historical median {baseline} {unit} across {len(points)} prior checks. Investigate before conditions worsen; this is a change alert, not a forecast."))
    return output

def topology(i):
    t=i['telemetry'];affected={e['device_id'] for e in i['evidence'] if e['abnormal']}
    direct={d['device_id'] for d in t['devices'] if d['device_id'] in affected or d['status']=='offline'}
    down=[c for c in t['connections'] if c['status']=='down']
    seeds=direct|{c['target_device'] for c in down}
    potential=set(seeds)
    for _ in t['devices']:
        expanded=potential|{c['target_device'] for c in t['connections'] if c['source_device'] in potential}
        if expanded==potential:break
        potential=expanded
    groups=[]
    for kind in ('hostel','department','segment_id'):
        for name in sorted({d.get(kind) for d in t['devices'] if d.get(kind)}):
            members=[d['device_id'] for d in t['devices'] if d.get(kind)==name]
            groups.append(dict(kind=kind,name=name,devices=members,potentially_affected=bool(set(members)&potential)))
    return dict(nodes=[dict(**d,impact='observed' if d['device_id'] in direct else 'potential' if d['device_id'] in potential else 'none') for d in t['devices']],
        links=t['connections'],groups=groups,observed_devices=sorted(direct),potential_devices=sorted(potential-direct),
        limitation='Only supplied links and location metadata are mapped. Potential downstream impact follows source-to-target links and requires operator verification. Gateway ping does not discover a campus topology.')

def explain(i,result):
    ev={e['evidence_id']:e for e in i['evidence']}
    result['explanation']=[dict(evidence_id=key,metric=ev[key]['metric'],device_id=ev[key]['device_id'],
        observed=ev[key]['observed_value'],threshold=ev[key]['threshold'],agent=ev[key]['source_agent'],explanation=ev[key]['explanation'])
        for key in result['supporting_evidence_ids'] if key in ev]
    conflicts=[]
    hypotheses=result['hypotheses']
    for a in range(len(hypotheses)):
        for b in range(a+1,len(hypotheses)):
            first,second=hypotheses[a],hypotheses[b]
            overlap=set(first['affected_devices'])&set(second['affected_devices'])
            gap=round(abs(first['score']-second['score']),3)
            conflicts.append(dict(hypotheses=[first['hypothesis'],second['hypothesis']],score_gap=gap,
                shared_devices=sorted(overlap),evidence_ids=sorted(set(first['evidence_ids']+second['evidence_ids'])),
                resolution='Unresolved competing explanations; collect interface rates, CPU process data and upstream reachability.' if gap<.08 else 'Higher evidence score ranks first; lower-ranked explanation remains possible.',
                independent_agents=sorted({ev[k]['source_agent'] for k in first['evidence_ids']+second['evidence_ids'] if k in ev})))
    result['conflicts']=conflicts
    result['uncertainty_reasons']=result['limitations'].copy()
    if result['status']=='inconclusive':
        result['confidence_category']='insufficient evidence'
        result['uncertainty_reasons'].append('No defensible single leading cause. A candidate score is not confirmation.')
    if conflicts:result['uncertainty_reasons'].append('Multiple explanations may coexist; ranking is not proof of causality.')
    return result
