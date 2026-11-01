import asyncio
import logging
from copy import deepcopy
from . import store
from .schemas import AGENTS, Settings, now
from .agents import REGISTRY, uid, message
from .telemetry import quality

logger=logging.getLogger(__name__)

def new_incident(telemetry, settings):
    incident=dict(id=uid('INC'),created_at=now(),status='running',telemetry=telemetry.model_dump(mode='json'),
        quality=quality(telemetry,settings.stale_after_minutes),settings=settings.model_dump(),agents=[],evidence=[],
        correlation=None,recommendations=[],report_id=None,error=None,
        timeline=[dict(timestamp=now(),event='Telemetry validated and normalized to UTC')])
    incident['agents']=[dict(agent_id=a,status='waiting',findings=[],evidence=[],limitations=[]) for a in AGENTS]
    store.put('incident',incident['id'],incident)
    return incident

def fallback():
    return dict(status='inconclusive',root_cause='Inconclusive - correlation unavailable',severity='unknown',confidence=0,
        confidence_category='insufficient evidence',confidence_method='No score available',hypotheses=[],supporting_evidence_ids=[],
        affected_devices=[],limitations=['Correlation did not complete. No remediation performed.'])

async def execute(incident_id):
    from .reports import create_report
    incident=store.get('incident',incident_id)
    settings=Settings.model_validate(incident['settings'])
    try:
        for index,agent in enumerate(AGENTS):
            execution=incident['agents'][index]
            if agent not in settings.enabled_agents:
                execution.update(status='skipped',limitations=['Disabled in diagnostic settings'])
            else:
                for attempt in range(settings.retry_limit+1):
                    execution.update(status='running',started_at=now(),attempt=attempt+1)
                    incident['timeline'].append(dict(timestamp=now(),event=f'{agent} started (attempt {attempt+1})'))
                    store.put('incident',incident_id,incident)
                    try:
                        result=await asyncio.wait_for(asyncio.to_thread(REGISTRY[agent],deepcopy(incident),settings),settings.timeout_seconds)
                        execution.update(result)
                        execution.pop('error',None)
                        execution['ended_at']=now()
                        incident['evidence'].extend(result['evidence'])
                        if agent=='correlation_agent': incident['correlation']=result['result']
                        if agent=='recommendation_agent': incident['recommendations']=result['result']
                        if agent=='recommendation_agent':
                            from .dependency import build
                            incident['dependency_graph']=build(incident)
                        break
                    except Exception as exc:
                        logger.exception('Agent %s failed',agent)
                        execution.update(status='failed',ended_at=now(),error='Execution timed out' if isinstance(exc,TimeoutError) else 'Agent execution failed; consult server logs',limitations=['Analysis unavailable'])
                        incident['timeline'].append(dict(timestamp=now(),event=f'{agent} attempt {attempt+1} failed'))
            if agent=='correlation_agent' and not incident['correlation']: incident['correlation']=fallback()
            if agent=='connectivity_agent':
                from .analytics import topology
                incident['topology']=topology(incident)
                incident['alerts']=[dict(id=e['evidence_id'],evidence_id=e['evidence_id'],incident_id=incident_id,
                    message=e['explanation'],timestamp=e['timestamp'],severity='warning') for e in incident['evidence'] if e.get('kind')=='historical_anomaly']
            incident['timeline'].append(dict(timestamp=now(),event=f"{agent}: {execution['status']}"))
            store.put('incident',incident_id,incident)
        incident['status']='partial' if any(a['status']!='completed' for a in incident['agents']) else incident['correlation']['status']
        incident['completed_at']=now()
        store.put('incident',incident_id,incident)
        if incident['agents'][-1]['status']=='completed':
            try: create_report(incident)
            except Exception:
                logger.exception('Report generation failed')
                incident['status']='partial'
                incident['agents'][-1].update(status='failed',error='Report generation failed; retry from Incident Details')
                incident['error']='Report generation failed; retry available'
                store.put('incident',incident_id,incident)
    except Exception:
        logger.exception('Orchestrator failed')
        incident.update(status='failed',error='Diagnosis interrupted; inspect logs and rerun',completed_at=now())
        store.put('incident',incident_id,incident)
