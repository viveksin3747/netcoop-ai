import csv
import io
import json
from datetime import datetime, timezone
from .schemas import Telemetry, METRICS

def parse_upload(name: str, content: bytes):
    if len(content) > 2 * 1024 * 1024:
        raise ValueError('Upload exceeds the 2 MB limit')
    text = content.decode('utf-8-sig')
    suffix = name.lower().rsplit('.',1)[-1]
    if suffix == 'json' or (suffix=='txt' and text.lstrip().startswith('{')):
        raw = json.loads(text)
    elif suffix in ('csv','txt'):
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows or len(rows)>500:
            raise ValueError('CSV/TXT requires a header and 1-500 device rows')
        stamps = {r.get('timestamp') for r in rows}
        if len(stamps)!=1 or not next(iter(stamps)):
            raise ValueError('Each CSV row requires the same timezone-aware snapshot timestamp')
        networks = {r.get('network_id','Uploaded network') for r in rows}
        if len(networks)!=1:
            raise ValueError('CSV rows must belong to one network')
        raw = {'timestamp':rows[0]['timestamp'], 'network_id':next(iter(networks)), 'devices':[]}
        for row in rows:
            raw['devices'].append({k:(None if v.strip()=='' else v.strip()) for k,v in row.items()
                if k not in ('timestamp','network_id') and v is not None})
    else:
        raise ValueError('Supported formats: JSON, CSV, or TXT containing JSON/CSV')
    if not isinstance(raw, dict):
        raise ValueError('Telemetry must be a JSON object')
    raw.update(source_type='upload', source_reference=name.replace('\\','/').split('/')[-1][:200])
    raw.setdefault('data_mode','observed')
    return Telemetry.model_validate(raw)

def quality(t: Telemetry, stale_minutes: int):
    missing = {d.device_id:[m for m in METRICS if getattr(d,m) is None] for d in t.devices}
    core = ['cpu_usage_percent','memory_usage_percent','latency_ms','packet_loss_percent','bandwidth_utilization_percent']
    completeness = sum(getattr(d,m) is not None for d in t.devices for m in core)/(len(t.devices)*len(core))
    age = (datetime.now(timezone.utc)-t.timestamp).total_seconds()/60
    return {'missing_fields':missing, 'core_completeness':round(completeness,3), 'stale':age>stale_minutes,
            'age_minutes':round(age,2), 'normalized_timezone':'UTC', 'invalid_fields':[],
            'notes':['Missing values are preserved as null. Metrics use schema units.',
                     'Cumulative error/drop counters do not establish a current fault rate.']}
