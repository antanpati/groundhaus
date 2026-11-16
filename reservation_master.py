"""V2.6: non-destructive reservation master, import snapshots, review and adjustments.
Legacy transaction table is preserved. Paid rows continue to live there; upcoming is
stored separately. No database records are deleted or rewritten during migration.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime
import pandas as pd
import store

FIELDS = ('Listing','Start date','End date','Nights','Currency','Amount','Service fee','Gross earnings','Guest')
FINANCIAL = ('Amount','Service fee','Gross earnings')
DATE_FIELDS = ('Start date','End date')

def _plain(v):
    if v is None or (not isinstance(v,(str,dict,list)) and pd.isna(v)): return None
    if isinstance(v,(pd.Timestamp,datetime)): return v.strftime('%Y-%m-%d')
    if isinstance(v,float): return round(v,4)
    return v

def normalize(row):
    out={str(k):_plain(v) for k,v in dict(row).items() if k!='row_id'}
    for key in FINANCIAL + ('Nights',):
        v=out.get(key)
        out[key]=float(v) if v is not None and str(v)!='' else 0.0
    for key in DATE_FIELDS:
        if out.get(key): out[key]=pd.to_datetime(out[key]).strftime('%Y-%m-%d')
    for key in ('Confirmation code','Listing','Currency','Type'):
        out[key]=str(out.get(key) or '').strip()
    return out

def _sig(obj):
    # Comparing business-critical reservation fields, not CSV schema / empty ancillary columns.
    canonical={k:obj.get(k) for k in FIELDS}
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()

def _hash(s): return hashlib.sha256(s.encode()).hexdigest()

def _tables(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS v26_uploads(id INTEGER PRIMARY KEY, source TEXT NOT NULL, file_hash TEXT NOT NULL, filename TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(source,file_hash));
    CREATE TABLE IF NOT EXISTS v26_versions(id INTEGER PRIMARY KEY, code TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('paid','upcoming')), signature TEXT NOT NULL, payload TEXT NOT NULL, upload_id INTEGER REFERENCES v26_uploads(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(code,source,signature));
    CREATE TABLE IF NOT EXISTS v26_choice(code TEXT PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES v26_versions(id), decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, note TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS v26_override(code TEXT PRIMARY KEY, status TEXT NOT NULL, payload TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS v26_events(id INTEGER PRIMARY KEY, code TEXT NOT NULL, action TEXT NOT NULL, before_json TEXT, after_json TEXT, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS v26_adjustment_decision(tx_key TEXT PRIMARY KEY, code TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('applied','included','excluded')), reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    ''')

def init():
    with store.connection() as con: _tables(con)

def _versions(con):
    return [dict(r) for r in con.execute('SELECT * FROM v26_versions ORDER BY id')]

def _backfill(con):
    # Once per unique row, so repeatedly loading does not inflate counts.
    for row in con.execute("SELECT payload FROM transactions WHERE kind='Reservation' ORDER BY imported_at, rowid"):
        obj=normalize(json.loads(row['payload']))
        code=obj.get('Confirmation code','')
        if code:
            sig=_sig(obj)
            con.execute('INSERT OR IGNORE INTO v26_versions(code,source,signature,payload) VALUES(?,?,?,?)',
                        (code,'paid',sig,json.dumps(obj,ensure_ascii=False,sort_keys=True)))

def import_upcoming(data:bytes,filename:str,df:pd.DataFrame):
    init()
    if df.empty or any(str(t).lower()!='reservation' for t in df['Type']):
        raise ValueError('Upcoming harus berisi baris Reservation saja. Jangan impor Paid/Payout di menu ini.')
    missing=df[df['Confirmation code'].astype(str).str.strip().eq('')]
    if len(missing): raise ValueError('Ada reservation tanpa Confirmation Code. Perbaiki sumber CSV dahulu.')
    fh=_hash(data.decode('latin1'))
    with store.connection() as con:
        _tables(con)
        _backfill(con)
        if con.execute('SELECT 1 FROM v26_uploads WHERE source=? AND file_hash=?',('upcoming',fh)).fetchone():
            return {'new_versions':0,'repeated':True}
        cur=con.execute('INSERT INTO v26_uploads(source,file_hash,filename) VALUES(?,?,?)',('upcoming',fh,filename))
        added=0
        for _,r in df.iterrows():
            obj=normalize(r.to_dict()); code=obj['Confirmation code']; sig=_sig(obj)
            result=con.execute('INSERT OR IGNORE INTO v26_versions(code,source,signature,payload,upload_id) VALUES(?,?,?,?,?)',
                               (code,'upcoming',sig,json.dumps(obj,ensure_ascii=False,sort_keys=True),cur.lastrowid))
            added+=result.rowcount
    return {'new_versions':added,'repeated':False}

def import_paid(data:bytes,filename:str,df:pd.DataFrame):
    init()
    # Write legacy transactions once for compatibility with V2.5 payout and historical reporting.
    added=store.import_transactions(df)
    with store.connection() as con:
        _tables(con)
        fh=_hash(data.decode('latin1'))
        con.execute('INSERT OR IGNORE INTO v26_uploads(source,file_hash,filename) VALUES(?,?,?)',('paid',fh,filename))
        _backfill(con)
    return added

def _all_versions():
    init()
    with store.connection() as con:
        _backfill(con)
        versions=_versions(con)
        choices={r['code']:r['version_id'] for r in con.execute('SELECT code,version_id FROM v26_choice')}
        overrides={r['code']:dict(r) for r in con.execute('SELECT * FROM v26_override')}
        decisions={r['tx_key']:dict(r) for r in con.execute('SELECT * FROM v26_adjustment_decision')}
    return versions,choices,overrides,decisions

def get_state():
    versions,choices,overrides,decisions=_all_versions()
    bycode={}
    for v in versions: bycode.setdefault(v['code'],[]).append(v)
    selected={}; conflicts=[]; upcoming=[]; actual=[]
    for code,items in bycode.items():
        # Paid takes precedence for effective actuals. Do not silently override differing paid versions.
        paid=[v for v in items if v['source']=='paid']; pending=[v for v in items if v['source']=='upcoming']
        chosen=next((v for v in items if v['id']==choices.get(code)),None)
        if not chosen:
            chosen=paid[0] if paid else pending[0]
        payload=json.loads(chosen['payload'])
        sigs={v['signature'] for v in items if v['source']==chosen['source']}
        if len(sigs)>1 and code not in choices:
            conflicts.append({'code':code,'versions':items,'selected':chosen,'kind':'multiple versions of same source'})
        # If upcoming and paid disagree, actual remains paid. Show mismatch for review, never double count.
        if paid and pending and code not in choices and not set(v['signature'] for v in paid).intersection(v['signature'] for v in pending):
            conflicts.append({'code':code,'versions':items,'selected':chosen,'kind':'upcoming / paid mismatch'})
        status='Paid' if chosen['source']=='paid' else 'Upcoming'
        if code in overrides:
            ov=overrides[code]
            payload.update(json.loads(ov['payload']))
            status=ov['status']
        payload['Type']='Reservation'
        payload['_source']=chosen['source'];payload['_status']=status;payload['_code']=code
        selected[code]=payload
        if chosen['source']=='paid': actual.append(payload)
        else: upcoming.append(payload)
    # Paid adjustment ledger is kept separate until a human decides if it is already included.
    with store.connection() as con:
        txs=[dict(r) for r in con.execute("SELECT key,payload FROM transactions WHERE kind='Adjustment' ORDER BY imported_at, rowid")]
    adjustments=[]
    for t in txs:
        a=normalize(json.loads(t['payload']))
        a['_key']=t['key']
        a['_decision']=decisions.get(t['key'],{}).get('mode','unreviewed')
        adjustments.append(a)
    # only explicit 'applied' decisions affect the selected reservation Amount
    for a in adjustments:
        code=a.get('Confirmation code')
        if a['_decision']=='applied' and code in selected and code not in overrides:
            selected[code]['Amount']=float(selected[code].get('Amount') or 0)+float(a.get('Amount') or 0)
            selected[code]['_adjustment_applied']=True
    actual=[selected[r['_code']] for r in actual]; upcoming=[selected[r['_code']] for r in upcoming]
    return {'actual':actual,'upcoming':upcoming,'selected':selected,'conflicts':conflicts,'adjustments':adjustments,'versions':bycode,'overrides':overrides}

def as_frame(records):
    # Keep the same column shapes the old engine and owner exports expect.
    if not records:
        return pd.DataFrame(columns=['Type','Confirmation code','Listing','Guest','Currency','Start date','End date','Date','Booking date','Arriving by date','Nights','Amount','Service fee','Gross earnings','Paid out','Details','Reference code','row_id'])
    df=pd.DataFrame(records)
    for c in ['Date','Booking date','Start date','End date','Arriving by date']:
        if c not in df: df[c]=pd.NaT
        df[c]=pd.to_datetime(df[c],errors='coerce')
    for c in ['Amount','Paid out','Service fee','Fast pay fee','Cleaning fee','Gross earnings','Airbnb remitted tax','Nights']:
        if c not in df:df[c]=0.0
        df[c]=pd.to_numeric(df[c],errors='coerce').fillna(0)
    df['row_id']=range(1,len(df)+1)
    return df

def actual_raw(legacy,state):
    res=as_frame(state['actual'])
    nonres=legacy[legacy['Type'].ne('Reservation')].copy() if not legacy.empty else pd.DataFrame()
    if res.empty: return nonres.reset_index(drop=True)
    return pd.concat([res,nonres],ignore_index=True)

def choose(code,version_id,note):
    state=get_state()
    version=next((v for v in state['versions'].get(code,[]) if v['id']==version_id),None)
    if not version:raise ValueError('Versi tidak ditemukan untuk confirmation code.')
    if version['source']=='upcoming' and any(v['source']=='paid' for v in state['versions'].get(code,[])):
        raise ValueError('Upcoming tidak dapat menggantikan data Paid. Pilih versi Paid, lalu edit manual jika perlu.')
    with store.connection() as con:
        prev=con.execute('SELECT version_id FROM v26_choice WHERE code=?',(code,)).fetchone()
        con.execute('INSERT INTO v26_choice(code,version_id,note) VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET version_id=excluded.version_id,note=excluded.note,decided_at=CURRENT_TIMESTAMP',(code,version_id,note))
        con.execute('INSERT INTO v26_events(code,action,before_json,after_json,reason) VALUES(?,?,?,?,?)',
                    (code,'SELECT_VERSION',json.dumps(dict(prev) if prev else {}),version['payload'],note))

def save_override(code,mode,start,end,amount,fee,gross,reason):
    state=get_state(); old=state['selected'].get(code)
    if not old:raise ValueError('Reservation tidak ditemukan.')
    if any(a['_decision']=='applied' and a.get('Confirmation code')==code for a in state['adjustments']):
        raise ValueError('Ubah keputusan Adjustment menjadi sudah termasuk / excluded sebelum edit manual agar Amount tidak dihitung ganda.')
    if not reason.strip():raise ValueError('Alasan perubahan wajib diisi.')
    a=pd.to_datetime(start);b=pd.to_datetime(end)
    if b<a:raise ValueError('Check-out tidak boleh sebelum check-in.')
    if mode not in ('Modified','Cancelled','Confirmed'):raise ValueError('Status tidak dikenal.')
    nights=(b-a).days if mode!='Cancelled' else 0
    if mode=='Cancelled': b=a
    payload={'Start date':a.strftime('%Y-%m-%d'),'End date':b.strftime('%Y-%m-%d'),
             'Nights':nights,'Amount':float(amount),'Service fee':float(fee),'Gross earnings':float(gross)}
    if mode=='Cancelled' and nights != 0: raise ValueError('Cancelled harus 0 malam.')
    if any(float(payload[k]) < 0 for k in ('Amount','Gross earnings')):
        raise ValueError('Nilai final Amount / Gross tidak boleh negatif.')
    with store.connection() as con:
        con.execute('INSERT INTO v26_override(code,status,payload,reason) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET status=excluded.status,payload=excluded.payload,reason=excluded.reason,created_at=CURRENT_TIMESTAMP',
                    (code,mode,json.dumps(payload),reason))
        con.execute('INSERT INTO v26_events(code,action,before_json,after_json,reason) VALUES(?,?,?,?,?)',
                    (code,'OVERRIDE',json.dumps(old,default=str,ensure_ascii=False),json.dumps(payload),reason))

def remove_override(code,reason):
    if not reason.strip():raise ValueError('Alasan wajib diisi.')
    with store.connection() as con:
        prev=con.execute('SELECT * FROM v26_override WHERE code=?',(code,)).fetchone()
        if prev:
            con.execute('DELETE FROM v26_override WHERE code=?',(code,))
            con.execute('INSERT INTO v26_events(code,action,before_json,after_json,reason) VALUES(?,?,?,?,?)',
                        (code,'REMOVE_OVERRIDE',prev['payload'],'{}',reason))

def set_adjustment(key,mode,reason):
    state=get_state()
    a=next((a for a in state['adjustments'] if a['_key']==key),None)
    if not a:raise ValueError('Adjustment tidak ditemukan.')
    if mode not in ('applied','included','excluded'):raise ValueError('Mode tidak dikenal.')
    if not reason.strip():raise ValueError('Alasan keputusan wajib diisi.')
    if mode=='applied' and a.get('Confirmation code') in state['overrides']:
        raise ValueError('Reservasi punya edit manual. Pilih included/excluded dahulu agar adjustment tidak dihitung ganda.')
    if mode=='applied' and a.get('Confirmation code') not in state['selected']:
        raise ValueError('Reservasi untuk adjustment belum ada dalam data. Jangan terapkan tanpa reservation master.')
    with store.connection() as con:
        con.execute('INSERT INTO v26_adjustment_decision(tx_key,code,mode,reason) VALUES(?,?,?,?) ON CONFLICT(tx_key) DO UPDATE SET mode=excluded.mode,reason=excluded.reason,created_at=CURRENT_TIMESTAMP',(key,a.get('Confirmation code',''),mode,reason))
        con.execute('INSERT INTO v26_events(code,action,before_json,after_json,reason) VALUES(?,?,?,?,?)',
                    (a.get('Confirmation code',''),'ADJUSTMENT_DECISION',json.dumps({'previous':a['_decision']}),json.dumps({'mode':mode,'amount':a.get('Amount')}),reason))

def event_history(code):
    with store.connection() as con:
        return [dict(r) for r in con.execute('SELECT action,reason,created_at FROM v26_events WHERE code=? ORDER BY id DESC',(code,))]

def unresolved_for_villa(state,mapping,villa,month):
    """Block approval in any affected stay month, not just check-in month."""
    from stay_allocation import months_touched
    from datetime import date
    def touches(row):
        listing=row.get('Listing','')
        mapped=mapping.get(listing,{})
        if (mapped.get('villa') or listing)!=villa:return False
        first=pd.to_datetime(row.get('Start date'),errors='coerce')
        end=pd.to_datetime(row.get('End date'),errors='coerce')
        if pd.isna(first):return False
        if pd.isna(end):return str(first.date())[:7]==month
        if first==end:return str(first.date())[:7]==month
        return any(m==month for m,_ in months_touched(first.date(),end.date()))
    codes=set()
    for c in state['conflicts']:
        code=c['code']
        # Also inspect all versions: a stay can move across months in a conflict.
        if any(touches(json.loads(v['payload'])) for v in c['versions']): codes.add(code)
    unresolved_adj=[]
    for a in state['adjustments']:
        if a['_decision']=='unreviewed':
            row=state['selected'].get(a.get('Confirmation code'),{})
            if touches(row):unresolved_adj.append(a)
    return codes,unresolved_adj
