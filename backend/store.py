"""SQLite snapshot records preserve evidence and report versions atomically."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def connect():
    path = Path(os.getenv('NETCOOP_DB', 'data/netcoop.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, payload TEXT NOT NULL, PRIMARY KEY(kind,id))')
        with db:
            yield db
    finally:
        db.close()

def put(kind, key, value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)', (kind, key, json.dumps(value, allow_nan=False)))

def get(kind, key):
    with connect() as db:
        row = db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind,key)).fetchone()
    return json.loads(row[0]) if row else None

def all_records(kind):
    with connect() as db:
        rows = db.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
    records = [json.loads(r[0]) for r in rows]
    if kind in ('incident','report'):
        field = 'created_at' if kind=='incident' else 'generated_at'
        records.sort(key=lambda r:r.get(field,''),reverse=True)
    return records

def update_recommendation(incident_id, recommendation_id, status, note=None, confirmed=False):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT payload FROM records WHERE kind=? AND id=?', ('incident',incident_id)).fetchone()
        if not row:
            return False
        incident = json.loads(row[0])
        rec = next((r for r in incident['recommendations'] if r['id']==recommendation_id), None)
        if not rec:
            return False
        from .schemas import now
        previous=rec['status']
        rec['status'] = status
        rec.setdefault('history',[]).append(dict(timestamp=now(),event='status_changed',from_status=previous,
            to_status=status,note=note or '',operator_confirmed=confirmed))
        if status=='Completed' and confirmed:
            rec['completion_verification']=dict(timestamp=now(),note=note,operator_confirmed=True)
        db.execute('UPDATE records SET payload=? WHERE kind=? AND id=?', (json.dumps(incident),'incident',incident_id))
    return True

def recommendation_event(incident_id, recommendation_id, event):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT payload FROM records WHERE kind=? AND id=?',('incident',incident_id)).fetchone()
        if not row:return
        incident=json.loads(row[0])
        recommendation=next((r for r in incident['recommendations'] if r['id']==recommendation_id),None)
        if not recommendation:return
        recommendation.setdefault('history',[]).append(event)
        db.execute('UPDATE records SET payload=? WHERE kind=? AND id=?',(json.dumps(incident),'incident',incident_id))
