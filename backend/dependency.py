"""Canonical dependency graph and paginated vector diagrams for every report format."""
import math
import textwrap
from xml.sax.saxutils import escape
from .analytics import topology

COLORS={'observed':'#d63f60','potential':'#c77b16','none':'#286ebd','assessment':'#7554ad'}

def build(incident):
    topo=topology(incident);c=incident.get('correlation') or {}
    nodes=[dict(id='#assessment',label=c.get('root_cause','Assessment unavailable'),kind='assessment',impact='assessment',
        detail=f"Confidence {c.get('confidence',0):.0%} ({c.get('confidence_category','unavailable')})",evidence_ids=c.get('supporting_evidence_ids',[]))]
    edges=[]
    for d in topo['nodes']:
        ev=[e for e in incident['evidence'] if e['device_id']==d['device_id'] and e['abnormal']]
        detail=f"{d['device_type']} | {d['status']} | {d['impact']} impact"
        if ev:detail+=' | '+'; '.join(f"{e['metric']}={e['observed_value']} {e['unit']}" for e in ev)
        nodes.append(dict(id=d['device_id'],label=d['device_id'],kind='device',impact=d['impact'],detail=detail,evidence_ids=[e['evidence_id'] for e in ev]))
    for link in topo['links']:
        edges.append(dict(source=link['source_device'],target=link['target_device'],label='Supplied link: '+link['status'],kind='dependency'))
    incoming={e['target'] for e in edges}
    roots=[d['device_id'] for d in topo['nodes'] if d['device_id'] not in incoming]
    if not roots and topo['nodes']:roots=[topo['nodes'][0]['device_id']]
    for root in roots:edges.append(dict(source='#assessment',target=root,label='Assessment context',kind='association'))
    for index,group in enumerate(topo['groups']):
        key=f'#group:{index}'
        nodes.append(dict(id=key,label=group['name'],kind=group['kind'],impact='potential' if group['potentially_affected'] else 'none',detail='Supplied '+group['kind'].replace('_id','')+' membership',evidence_ids=[]))
        for member in group['devices']:edges.append(dict(source=member,target=key,label='Supplied membership',kind='membership'))
    for d in topo['nodes']:
        for index,service in enumerate(d.get('services',[])):
            key=f"#service:{d['device_id']}:{index}"
            nodes.append(dict(id=key,label=service,kind='service',impact='potential' if d['impact']!='none' else 'none',detail='Service reported on '+d['device_id']+'; availability not independently tested',evidence_ids=[]))
            edges.append(dict(source=d['device_id'],target=key,label='Reported service dependency',kind='dependency'))
    for index,rec in enumerate(incident['recommendations']):
        key=f'#action:{index}'
        nodes.append(dict(id=key,label='Next step: '+rec['priority'],kind='recommendation',impact='assessment',detail=rec['action'],evidence_ids=rec['evidence_ids']))
        edges.append(dict(source='#assessment',target=key,label='Advisory response',kind='association'))
    # Stable breadth-first layers; cycles are retained and never recursively expanded.
    levels={'#assessment':0}
    for _ in nodes:
        changed=False
        for e in edges:
            if e['source'] in levels and e['target'] not in levels:
                levels[e['target']]=levels[e['source']]+1;changed=True
        if not changed:break
    for n in nodes:n['level']=levels.get(n['id'],1)
    nodes.sort(key=lambda n:(n['level'],n['id']))
    graph=dict(nodes=nodes,edges=edges,
        legend='Red: observed fault/anomaly. Orange: potential downstream impact. Blue: no impact established. Purple: assessment or advice.',
        limitation='Arrows describe supplied dependencies or labelled associations, not proof of causation. Service and location impact is inferred and needs verification. Missing topology is not invented. Full details and evidence are listed below the diagram.')
    graph['diagrams']=[svg(graph,chunk) for chunk in pages(graph)]
    return graph

def pages(graph):return [graph['nodes'][i:i+8] for i in range(0,len(graph['nodes']),8)]

def layout(nodes):
    levels=sorted({n['level'] for n in nodes});positions={};row=0
    for level in levels:
        layer=[n for n in nodes if n['level']==level]
        for offset in range(0,len(layer),3):
            group=layer[offset:offset+3]
            for k,n in enumerate(group):positions[n['id']]=(15+k*290+(3-len(group))*145,row*155+25)
            row+=1
    return positions,max(210,row*155+30)

def svg(graph,nodes):
    positions,height=layout(nodes);parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="none" stroke="#7890ae"/></marker></defs>']
    for e in graph['edges']:
        if e['source'] not in positions or e['target'] not in positions:continue
        x,y=positions[e['source']];tx,ty=positions[e['target']]
        parts.append(f'<path d="M{x+130},{y+100} L{tx+130},{ty}" fill="none" stroke="#7890ae" stroke-width="2" marker-end="url(#arrow)"/><title>{escape(e["label"])}</title>')
        parts.append(f'<text x="{(x+tx)/2+130}" y="{(y+100+ty)/2-4}" text-anchor="middle" font-family="Arial" font-size="10" fill="#4e6380">{escape(e["label"][:34])}</text>')
    for n in nodes:
        external=[e['source'] for e in graph['edges'] if e['target']==n['id'] and e['source'] not in positions]
        if external:
            x,y=positions[n['id']]
            parts.append(f'<text x="{x+5}" y="{y-7}" font-family="Arial" font-size="9" fill="#667994">{escape(("From other diagram: "+", ".join(external))[:48])}</text>')
    for n in nodes:
        x,y=positions[n['id']];color=COLORS[n['impact']]
        external=[e['source'] for e in graph['edges'] if e['target']==n['id'] and e['source'] not in positions]
        parts.append(f'<rect x="{x}" y="{y}" width="260" height="100" rx="8" fill="#f8faff" stroke="{color}" stroke-width="2"/>')
        text=[n['label'][:30]]+textwrap.wrap(n['detail'],38)[:3]
        for k,line in enumerate(text):parts.append(f'<text x="{x+10}" y="{y+20+k*19}" font-family="Arial,sans-serif" font-size="{16 if k==0 else 13}" fill="{color if k==0 else "#4e6380"}">{escape(line[:42])}</text>')
    return ''.join(parts)+'</svg>'

def drawing(graph,nodes):
    from reportlab.graphics.shapes import Drawing,Rect,Line,String,Polygon
    from reportlab.lib.colors import HexColor
    positions,height=layout(nodes);d=Drawing(900,height)
    for e in graph['edges']:
        if e['source'] not in positions or e['target'] not in positions:continue
        x,y=positions[e['source']];tx,ty=positions[e['target']]
        ax,ay=x+130,height-y-100;bx,by=tx+130,height-ty
        d.add(Line(ax,ay,bx,by,strokeColor=HexColor('#7890ae'),strokeWidth=1.5))
        d.add(String((ax+bx)/2,(ay+by)/2+4,e['label'][:34],textAnchor='middle',fontName='Helvetica',fontSize=10,fillColor=HexColor('#4e6380')))
        angle=math.atan2(by-ay,bx-ax)
        d.add(Polygon([bx,by,bx-9*math.cos(angle-.4),by-9*math.sin(angle-.4),bx-9*math.cos(angle+.4),by-9*math.sin(angle+.4)],fillColor=HexColor('#7890ae'),strokeColor=None))
    for n in nodes:
        x,y=positions[n['id']];bottom=height-y-100;color=HexColor(COLORS[n['impact']])
        external=[e['source'] for e in graph['edges'] if e['target']==n['id'] and e['source'] not in positions]
        if external:d.add(String(x+5,height-y+7,('From other diagram: '+', '.join(external))[:48],fontName='Helvetica',fontSize=9,fillColor=HexColor('#667994')))
        d.add(Rect(x,bottom,260,100,rx=8,ry=8,fillColor=HexColor('#f8faff'),strokeColor=color,strokeWidth=2))
        for k,line in enumerate([n['label'][:30]]+textwrap.wrap(n['detail'],38)[:3]):
            d.add(String(x+10,height-y-20-k*19,line[:42],fontName='Helvetica-Bold' if k==0 else 'Helvetica',fontSize=16 if k==0 else 13,fillColor=color if k==0 else HexColor('#4e6380')))
    return d

def png(graph,nodes):
    from PIL import Image,ImageDraw,ImageFont
    from io import BytesIO
    positions,height=layout(nodes);im=Image.new('RGB',(900,height),'white');draw=ImageDraw.Draw(im)
    try:font=ImageFont.truetype('arial.ttf',12)
    except OSError:font=ImageFont.load_default()
    for e in graph['edges']:
        if e['source'] not in positions or e['target'] not in positions:continue
        x,y=positions[e['source']];tx,ty=positions[e['target']];a=(x+130,y+100);b=(tx+130,ty)
        draw.line([a,b],fill='#7890ae',width=2);angle=math.atan2(b[1]-a[1],b[0]-a[0])
        draw.polygon([b,(b[0]-9*math.cos(angle-.4),b[1]-9*math.sin(angle-.4)),(b[0]-9*math.cos(angle+.4),b[1]-9*math.sin(angle+.4))],fill='#7890ae')
    for n in nodes:
        x,y=positions[n['id']];color=COLORS[n['impact']]
        external=[e['source'] for e in graph['edges'] if e['target']==n['id'] and e['source'] not in positions]
        if external:draw.text((x+5,y-16),('From other diagram: '+', '.join(external))[:48],fill='#667994',font=font)
        draw.rounded_rectangle((x,y,x+260,y+100),radius=8,fill='#f8faff',outline=color,width=2)
        for k,line in enumerate([n['label']]+textwrap.wrap(n['detail'],42)[:3]):draw.text((x+10,y+8+k*19),line[:48],fill=color if k==0 else '#4e6380',font=font)
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()
