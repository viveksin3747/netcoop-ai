"""Immutable canonical report snapshots and safe, on-demand document exports."""
import json
import os
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from . import store
from .agents import uid
from .schemas import now
from . import dependency

def create_report(incident):
    if incident['status']=='running': raise ValueError('Diagnosis is still running')
    report_id=uid('RPT')
    generated=now()
    incident=deepcopy(incident)
    incident['timeline'].append(dict(timestamp=generated,event=f'Report {report_id} generated'))
    incident['report_id']=report_id
    c=incident.get('correlation') or {'root_cause':'Diagnosis failed before correlation','confidence':0,'severity':'unknown','limitations':[]}
    report=dict(report_id=report_id,incident_id=incident['id'],version='1.0',generated_at=generated,timezone='UTC',
        status=incident['status'],source_type=incident['telemetry']['source_type'],data_mode=incident['telemetry']['data_mode'],
        severity=c['severity'],generation_error=None,creator=None,incident=incident,
        conclusion=f"{c['root_cause']}. Advisory analysis only; no network changes were performed.",
        limitations=c['limitations']+['Public sharing and multi-user authentication are not available in this local MVP.']+
            (['Live gateway check uses five ICMP probes. Missing replies can reflect blocked ICMP, not an offline device. CPU, memory and bandwidth are not measured. This does not establish Internet-wide connectivity.'] if incident['telemetry']['source_type']=='live' else []))
    if incident['telemetry']['source_type']=='live':
        key=incident['telemetry']['source_reference'].split(':',1)[0]
        report['live_measurements']=store.get('live-sample',key)
    if incident.get('speed_test'): report['speed_test']=incident['speed_test']
    graph=dependency.build(incident)
    graph['diagrams']=[dependency.svg(graph,nodes) for nodes in dependency.pages(graph)]
    report['dependency_graph']=graph
    report['sections']=sections(report)
    store.put('report',report_id,report)
    store.put('incident',incident['id'],incident)
    return report

def sections(r):
    i=r['incident']; t=i['telemetry']; c=i.get('correlation') or {}
    rows=[]
    def add(title,lines): rows.append(dict(title=title,paragraphs=[str(x) for x in lines]))
    graph=r.get('dependency_graph')
    if graph:
        add('Root cause dependency graph',[graph['legend'],graph['limitation'],
            'Large graphs continue across numbered diagrams. All nodes, arrows and evidence references are retained in the registers below.']+
            [f"{n['id']} | {n['label']} | {n['detail']} | Evidence: {', '.join(n['evidence_ids']) or 'none; supplied relationship or inferred impact'}" for n in graph['nodes']]+
            [f"{e['source']} -> {e['target']}: {e['label']}" for e in graph['edges']])
    if i.get('speed_test'):
        speed=i['speed_test']
        add('Internet download and upload speed',[
            'Download: '+(str(speed['download_mbps'])+' Mbps' if speed['download_mbps'] is not None else 'Unavailable'),
            'Upload: '+(str(speed['upload_mbps'])+' Mbps' if speed['upload_mbps'] is not None else 'Unavailable'),
            'Download means receiving files or videos; upload means sending files or video calls. Mbps means megabits per second.',
            f"Status: {speed['status']} | Provider: {speed['provider']} | Measured: {speed['started_at']} to {speed['completed_at']}",
            'Related original report: '+(speed['related_report_id'] or 'New live diagnosis'),speed['method'],speed['limitation']]+
            [f"{m['direction']}: {m['bytes']} bytes / {m['elapsed_seconds']} seconds = {m['mbps']} Mbps" for m in speed['measurements']]+speed['errors'])
    if i.get('topology'):
        topo=i['topology']
        add('Network topology and potential impact',[topo['limitation'],
            'Observed affected devices: '+str(topo['observed_devices']),
            'Potential downstream impact: '+str(topo['potential_devices'])]+
            [f"{g['kind']}: {g['name']} | Devices: {g['devices']} | Potentially affected: {g['potentially_affected']}" for g in topo['groups']])
    if c.get('explanation'):
        add('Why this diagnosis was reached',[f"{e['agent']} observed {e['metric']}={e['observed']} on {e['device_id']}; threshold {e['threshold']}; evidence {e['evidence_id']}. {e['explanation']}" for e in c['explanation']])
    if c.get('conflicts'):
        add('Agent conflict resolution',[str(conflict) for conflict in c['conflicts']])
    add('Historical anomaly alerts',[a['message']+' | Evidence: '+a['evidence_id'] for a in i.get('alerts',[])] or ['No historical anomaly established. At least five comparable prior observations are required; absence of an alert is not proof of future health.'])
    if i.get('test_context'):
        context=i['test_context']
        add('Live recommendation retest',[f"Original incident: {context['original_incident_id']} | Recommendation: {context['recommendation_id']}",
            f"Original report: {context['original_report_id'] or 'not generated'}",context['action'],context['scope'],
            'Target matches original: '+str(context['target_matches_original']),context['limitation']])
    add('Executive summary',[r['conclusion'],f"Assessment: {r['status']} | Severity: {r['severity']} | Mode: {r['data_mode']}",
        f"Confidence: {c.get('confidence',0):.0%} ({c.get('confidence_category','unavailable')}); heuristic score, not probability.",
        'Next step: '+(i['recommendations'][0]['action'] if i['recommendations'] else 'Complete missing diagnostic stages and collect fresh telemetry.')])
    add('Incident overview',[f"Network: {t['network_id']} | Incident: {i['id']}",
        f"Source: {t['source_type']} / {t['source_reference']} | Measurement timestamp: {t['timestamp']}",
        f"Devices: {len(t['devices'])} | Connections: {len(t['connections'])}",
        f"Started: {i['created_at']} | Completed: {i.get('completed_at','unavailable')}"])
    add('Telemetry and data quality',[f"Core completeness: {i['quality']['core_completeness']:.0%} | Stale: {i['quality']['stale']}"]+
        [f"{d['device_id']}: "+'; '.join(f'{k}={v}' for k,v in d.items() if v is not None and k!='device_id') for d in t['devices']]+
        [f"Missing fields for {device}: {', '.join(fields) or 'none'}" for device,fields in i['quality']['missing_fields'].items()]+i['quality']['notes'])
    for a in i['agents']:
        add(a['agent_id'].replace('_',' ').title(),[f"Status: {a['status']} | Started: {a.get('started_at','not executed')} | Ended: {a.get('ended_at','not executed')} | Attempts: {a.get('attempt',0)}"]+
            [f"{f['finding']} | Evidence: {', '.join(f.get('evidence_ids',[])) or 'none'}" for f in a['findings']]+
            a.get('limitations',[])+([a['error']] if a.get('error') else []))
    add('Evidence register',[f"{e['evidence_id']} | {e['source_agent']} | {e['device_id']} | {e['metric']} = {e['observed_value']} {e['unit']} | Threshold: {e['threshold']} | {e['timestamp']} | Source: {e['source_reference']}" for e in i['evidence']])
    add('Root cause assessment',[c.get('root_cause','Unavailable'),c.get('confidence_method','No score available')]+
        [f"Candidate: {h['hypothesis']} | Score: {h['score']:.0%} | Support: {', '.join(h['evidence_ids'])} | Contradictions: {', '.join(h['contradictory_evidence_ids']) or 'none observed'}" for h in c.get('hypotheses',[])])
    add('Impact assessment',['Observed affected assets: '+(', '.join(c.get('affected_devices',[])) or 'none established'),
        'Service degradation is possible where abnormal measurements were observed. Service impact is inferred; affected-user counts are unknown.'])
    add('Recommendations',[f"{x['priority']} | {x['status']} | {x['action']} Rationale: {x['rationale']}. Expected impact: {x['expected_impact']} Verification: {x['verification']} Evidence: {', '.join(x['evidence_ids']) or 'none; collect data'}. Advisory; not performed." for x in i['recommendations']])
    add('Execution timeline',[f"{event['timestamp']} | {event['event']}" for event in i['timeline']])
    add('Limitations and next steps',r['limitations']+[f"{a['agent_id']}: {a['status']}" for a in i['agents'] if a['status']!='completed'])
    add('Final conclusion',[r['conclusion'],'The JSON export includes the full normalized telemetry, structured agent messages, evidence and settings snapshot.'])
    return rows

def export(r, fmt):
    if fmt=='json': return json.dumps(r,indent=2,ensure_ascii=False).encode('utf-8')
    stream=BytesIO()
    if fmt=='pdf':
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.enums import TA_LEFT
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
        from reportlab.lib.pagesizes import A4
        styles=getSampleStyleSheet()
        styles['BodyText'].fontSize=8; styles['BodyText'].leading=12; styles['BodyText'].spaceAfter=8
        styles['BodyText'].textColor=colors.HexColor('#667994')
        styles['Heading2'].fontSize=12; styles['Heading2'].leading=16
        styles['Heading2'].textColor=colors.HexColor('#285596'); styles['Heading2'].spaceBefore=18
        styles['Title'].fontSize=22; styles['Title'].leading=28; styles['Title'].alignment=TA_LEFT
        styles['Title'].textColor=colors.HexColor('#142441')
        styles['Heading1'].fontSize=15; styles['Heading1'].textColor=colors.HexColor('#2478ef')
        styles['BodyText'].wordWrap='CJK'
        def p(text,style='BodyText'): return Paragraph(escape(str(text)),styles[style])
        story=[p('NetCoop AI','Heading1'),Spacer(1,14),p('Network Diagnostic Report','Title'),p('Smarter Diagnosis. Stronger Networks.'),Spacer(1,16)]
        table=Table([[p('Report'),p('Incident')],[p(r['report_id']),p(r['incident_id'])],
                     [p('Generated (UTC)'),p('Status / data mode')],
                     [p(r['generated_at']),p(f"{r['status']} / {r['data_mode']}")]],colWidths=[247,247])
        table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),15),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        story += [table,Spacer(1,14)]
        for section in r['sections']:
            story.append(p(section['title'],'Heading2'))
            graph=section.get('dependency_graph') or (r.get('dependency_graph') if section['title']=='Root cause dependency graph' else None)
            if graph:
                for index,nodes in enumerate(dependency.pages(graph)):
                    caption=p(f'Dependency diagram {index+1} of {len(dependency.pages(graph))}. See register for all labels, cross-diagram arrows and evidence.')
                    chart=dependency.drawing(graph,nodes)
                    scale=min(494/chart.width,440/chart.height)
                    chart.scale(scale,scale);chart.width*=scale;chart.height*=scale
                    story.append(KeepTogether([caption,chart,Spacer(1,12)]))
            story.extend(p(line) for line in section['paragraphs'])
        def footer(canvas,doc):
            canvas.setFont('Helvetica',8); canvas.setFillColor(colors.HexColor('#52617b'))
            canvas.drawString(45,25,f"NetCoop AI | {r['data_mode'].upper()} | {r['report_id']}")
            canvas.drawRightString(A4[0]-45,25,f'Page {doc.page}')
        SimpleDocTemplate(stream,pagesize=A4,rightMargin=45,leftMargin=45,topMargin=40,bottomMargin=45,
                          title='NetCoop AI Network Diagnostic Report').build(story,onFirstPage=footer,onLaterPages=footer)
    elif fmt=='docx':
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        doc=Document(); section=doc.sections[0]
        section.header.paragraphs[0].text='NetCoop AI | Network Diagnostic Report'
        section.top_margin=section.bottom_margin=Inches(.7)
        normal=doc.styles['Normal']; normal.font.name='Calibri'; normal.font.size=Pt(10)
        normal.paragraph_format.space_after=Pt(7)
        doc.add_heading('NetCoop AI Network Diagnostic Report',0)
        doc.add_paragraph('Smarter Diagnosis. Stronger Networks.')
        table=doc.add_table(rows=0, cols=2); table.style='Light Shading Accent 1'
        for key,value in [('Report',r['report_id']),('Generated UTC',r['generated_at']),('Status',r['status']),('Data mode',r['data_mode'])]:
            cells=table.add_row().cells; cells[0].text=key; cells[1].text=value
        for item in r['sections']:
            doc.add_heading(item['title'],level=1)
            graph=item.get('dependency_graph') or (r.get('dependency_graph') if item['title']=='Root cause dependency graph' else None)
            if graph:
                for index,nodes in enumerate(dependency.pages(graph)):
                    doc.add_paragraph(f'Dependency diagram {index+1}. Cross-diagram arrows and complete labels are listed in the graph register.')
                    doc.add_picture(BytesIO(dependency.png(graph,nodes)),width=Inches(6.1))
            for line in item['paragraphs']: doc.add_paragraph(line)
        doc.save(stream)
    else: raise ValueError('Unsupported export format')
    return stream.getvalue()
