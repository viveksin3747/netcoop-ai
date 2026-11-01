"""Six independently callable, deterministic diagnostic agents. No LLM required."""
from uuid import uuid4
from .schemas import now

def uid(prefix): return f'{prefix}-{uuid4().hex[:12]}'

def message(agent, incident):
    return dict(message_id=uid('MSG'),incident_id=incident['id'],agent_id=agent,timestamp=now(),
                status='completed',findings=[],evidence=[],confidence=None,limitations=[])

def observe(msg, incident, device, metric, value, threshold, unit, abnormal, explanation):
    ev = dict(evidence_id=uid('EV'),incident_id=incident['id'],source_agent=msg['agent_id'],
        device_id=device,metric=metric,observed_value=value,threshold=threshold,unit=unit,
        timestamp=incident['telemetry']['timestamp'],source_reference=incident['telemetry']['source_reference'],
        explanation=explanation,abnormal=abnormal)
    msg['evidence'].append(ev)
    if abnormal:
        msg['findings'].append(dict(finding=explanation,severity='high',evidence_ids=[ev['evidence_id']],device_id=device))

def metric_agent(agent, incident, rules):
    msg=message(agent,incident)
    for device in incident['telemetry']['devices']:
        for metric,threshold,unit in rules:
            value=device.get(metric)
            if value is None: continue
            bad=value>threshold
            explanation=f"{device['device_id']}: {metric} is {value} {unit}" + (f' (above {threshold})' if bad else ' (within configured limit)')
            observe(msg,incident,device['device_id'],metric,value,threshold,unit,bad,explanation)
    from .analytics import anomalies
    changes=anomalies(incident,agent)
    msg['evidence'].extend(changes)
    for e in changes:msg['findings'].append(dict(finding=e['explanation'],severity='warning',evidence_ids=[e['evidence_id']],device_id=e['device_id']))
    msg['limitations'].append('Historical anomaly checks require at least five comparable prior readings within 30 days. Separate sources, demo scenarios and device IPs are not mixed. Change alerts are not predictions of future outages.')
    if not msg['evidence']: msg['limitations'].append('No measurements available for this analysis.')
    return msg

def performance_agent(incident, settings):
    return metric_agent('performance_agent',incident,[('latency_ms',settings.latency_threshold,'ms'),
        ('packet_loss_percent',settings.packet_loss_threshold,'%'),('jitter_ms',30,'ms'),
        ('bandwidth_utilization_percent',settings.bandwidth_threshold,'%')])

def infrastructure_agent(incident, settings):
    msg=metric_agent('infrastructure_agent',incident,[('cpu_usage_percent',settings.cpu_threshold,'%'),
        ('memory_usage_percent',settings.memory_threshold,'%'),('temperature_c',80,'C')])
    for d in incident['telemetry']['devices']:
        for metric in ('interface_errors','dropped_packets','uptime_seconds'):
            if d.get(metric) is not None:
                observe(msg,incident,d['device_id'],metric,d[metric],None,'seconds' if metric=='uptime_seconds' else 'count',False,
                    f"{d['device_id']}: {metric} = {d[metric]}; snapshot counter, no rate inferred")
    return msg

def connectivity_agent(incident, settings):
    msg=message('connectivity_agent',incident)
    for d in incident['telemetry']['devices']:
        if d['status']!='unknown':
            observe(msg,incident,d['device_id'],'status',d['status'],'online','state',d['status']=='offline',
                    f"{d['device_id']} reported {d['status']}")
    for c in incident['telemetry']['connections']:
        if c['status']!='unknown':
            observe(msg,incident,f"{c['source_device']} -> {c['target_device']}",'link_status',c['status'],'active','state',
                    c['status']=='down',f"Link {c['source_device']} -> {c['target_device']} reported {c['status']}")
    if not incident['telemetry']['connections']: msg['limitations'].append('No topology supplied; affected segments cannot be established.')
    return msg

def correlation_agent(incident, settings):
    msg=message('correlation_agent',incident)
    ev=incident['evidence']; bad=[e for e in ev if e['abnormal']]
    hypotheses=[]
    def candidate(title, metrics, weight):
        support=[e for e in bad if e['metric'] in metrics]
        if not support: return
        assets={e['device_id'] for e in support}
        related=[e for e in bad if e['device_id'] in assets and e not in support]
        contradictions=[e for e in ev if e['device_id'] in assets and not e['abnormal'] and
                        e['metric'] in ('latency_ms','packet_loss_percent')]
        independent=len({e['source_agent'] for e in support+related})
        completeness=incident['quality']['core_completeness']
        strength=min(1,len(support)/2)
        score=min(.95,.30*strength+.20*min(independent/2,1)+.30*completeness+.20)
        score-=min(.20,len(contradictions)*.05)
        if incident['quality']['stale']: score*=.6
        if any(m['status']!='completed' for m in incident['agents'][:3]): score*=.75
        hypotheses.append(dict(hypothesis=title,evidence_ids=[e['evidence_id'] for e in support+related],
            contradictory_evidence_ids=[e['evidence_id'] for e in contradictions],affected_devices=sorted(assets),
            score=round(max(0,score),3),rank_weight=weight,
            confidence_factors=dict(strength=strength,independent_agents=independent,completeness=completeness,
                contradictory_measurements=len(contradictions),stale_penalty=incident['quality']['stale'])))
    candidate('Connectivity failure',('status','link_status'),4)
    candidate('Router overload',('cpu_usage_percent',),3)
    # CPU pressure on nonrouters should not be labelled router overload.
    for h in hypotheses:
        if h['hypothesis']=='Router overload' and not any(d['device_type']=='router' and d['device_id'] in h['affected_devices'] for d in incident['telemetry']['devices']):
            h['hypothesis']='Compute resource pressure'
    candidate('Infrastructure resource failure',('memory_usage_percent','temperature_c'),2)
    candidate('Network congestion',('bandwidth_utilization_percent',),1)
    if bad and not hypotheses: candidate('Unexplained performance degradation',('latency_ms','packet_loss_percent','jitter_ms'),0)
    hypotheses.sort(key=lambda h:(h['score'],h['rank_weight']),reverse=True)
    complete=incident['quality']['core_completeness']>=.8 and not incident['quality']['stale']
    observed_status=all(d['status']!='unknown' for d in incident['telemetry']['devices'])
    stages_ok=all(m['status']=='completed' for m in incident['agents'][:3])
    healthy=not bad and complete and observed_status and stages_ok
    decisive=bool(hypotheses) and hypotheses[0]['score']>=.5 and hypotheses[0]['rank_weight']>0
    if len(hypotheses)>1 and abs(hypotheses[0]['score']-hypotheses[1]['score'])<.08:
        decisive=False
    status='completed' if healthy or decisive else 'inconclusive'
    title=hypotheses[0]['hypothesis'] if decisive else ('No fault observed in this snapshot' if healthy else 'Inconclusive - more evidence required')
    support=hypotheses[0]['evidence_ids'] if hypotheses else [e['evidence_id'] for e in ev]
    score=hypotheses[0]['score'] if hypotheses else (round(.8*incident['quality']['core_completeness'],3) if healthy else 0)
    result=dict(status=status,root_cause=title,severity=('critical' if decisive and title=='Connectivity failure' else 'high' if bad else 'healthy' if healthy else 'unknown'),
        confidence=score,confidence_category='high' if score>=.8 else 'moderate' if score>=.5 else 'low',
        confidence_method='Heuristic evidence score, not a statistical probability. 30% strength + 20% independent support + 30% core completeness + 20% baseline consistency; subtract up to 20% contradictory normal performance; multiply by 0.6 for stale data and 0.75 for incomplete primary agents. Competing causes within 0.08 remain inconclusive.',
        hypotheses=hypotheses,supporting_evidence_ids=support,
        affected_devices=sorted({e['device_id'] for e in bad}),
        limitations=['Snapshot analysis cannot prove causality or ongoing service impact. No remediation performed.']+
            (['Stale telemetry reduces confidence.'] if incident['quality']['stale'] else [])+
            (['Core measurements are missing.'] if not complete else []))
    from .analytics import explain
    result=explain(incident,result)
    msg['findings']=[dict(finding=title,severity=result['severity'],evidence_ids=support)]
    msg['confidence']=score; msg['result']=result
    return msg

def recommendation_agent(incident, settings):
    msg=message('recommendation_agent',incident)
    c=incident['correlation']; title=c['root_cause']
    actions={
      'Connectivity failure':('Check power, cabling and interface state on affected assets.','Restore reachability after operator verification.','Repeat reachability checks and confirm link state is active.'),
      'Router overload':('Inspect router CPU processes and traffic distribution before changing configuration.','Identify the load source and reduce processing pressure.','Capture CPU, latency and loss over at least five minutes after an approved change.'),
      'Infrastructure resource failure':('Inspect memory consumers, cooling and device health.','Reduce resource pressure and prevent service interruption.','Recheck memory and temperature and verify application response.'),
      'Network congestion':('Review uplink traffic and queue utilization; assess capacity and QoS.','Reduce queueing and improve network responsiveness.','Compare utilization, jitter and loss before and after an approved change.'),
      'No fault observed in this snapshot':('Continue monitoring and collect a time series.','Detect future deviations from the observed baseline.','Compare a later snapshot against the same thresholds.')}
    action,impact,verification=actions.get(title,('Collect fresh telemetry, interface rates and reachability checks.','Resolve competing or unsupported hypotheses.','Re-run diagnosis with complete and current data.'))
    if any(e['metric']=='packet_loss_percent' and e['observed_value']>=20 for e in incident['evidence']):
        action+=' Check whether the problem affects one device or several; inspect cable connections and compare a wired connection with Wi-Fi. Ask an administrator to repeat reachability tests. Do not assume packet loss proves a router failure.'
        verification+=' Confirm repeated probes have fewer unanswered requests under comparable conditions. If disruption persists, escalate with the affected device IDs and measurements.'
    if title=='Connectivity failure':
        action+=' Check shared power and upstream connections first when several devices are disconnected. Contact the network administrator if power and cables appear normal; avoid resetting shared equipment without approval.'
        verification+=' Confirm each affected device and its link respond again, then test the service users actually need.'
    if any(e['metric']=='temperature_c' and e['observed_value']>=100 for e in incident['evidence']):
        action='Escalate the extreme temperature reading to the device owner immediately. Verify the sensor reading and inspect ventilation safely. Do not touch hot equipment or open electrical enclosures. Any shutdown must follow the operator’s approved procedure.'
        impact='Reduce the risk of heat-related device failure while preserving safe operation.'
        verification='Have the operator confirm temperature is back within the manufacturer’s operating range and verify service stability before returning to normal load.'
    if incident['quality']['stale']:
        action='Collect fresh measurements before acting on this old incident. Confirm whether users still experience the problem, then repeat reachability and performance checks. Escalate a current disruption with new timestamps.'
        impact='Avoid changing equipment based on an outage that may already have ended.'
        verification='Verify the new measurement timestamp is current and rerun diagnosis. Compare the new findings with this historical report.'
    rec=dict(id=uid('REC'),incident_id=incident['id'],priority='P1' if c['severity'] in ('critical','high') else 'P2',
        status='Pending',action=action,rationale=title,expected_impact=impact,verification=verification,
        evidence_ids=c['supporting_evidence_ids'],advisory=True,performed=False)
    msg['result']=[rec]; msg['findings']=[dict(finding=action,severity='info',evidence_ids=rec['evidence_ids'])]
    return msg

def reporting_agent(incident, settings):
    msg=message('reporting_agent',incident)
    msg['findings']=[dict(finding='Canonical report assembled from persisted incident records.',severity='info',
                          evidence_ids=incident['correlation']['supporting_evidence_ids'])]
    return msg

REGISTRY={f.__name__:f for f in (performance_agent,infrastructure_agent,connectivity_agent,correlation_agent,recommendation_agent,reporting_agent)}
