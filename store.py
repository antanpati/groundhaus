"""Persistent local SQLite store. No remote services."""
import sqlite3, json, hashlib
from pathlib import Path
import pandas as pd

DB = Path(__file__).resolve().parent / 'app_data' / 'groundhaus.sqlite3'

def _ensure_columns(con):
    mapping_cols = {r[1] for r in con.execute("PRAGMA table_info(mapping)").fetchall()}
    if 'room' not in mapping_cols:
        con.execute("ALTER TABLE mapping ADD COLUMN room TEXT NOT NULL DEFAULT ''")

def connection():
    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    con.executescript('''
    CREATE TABLE IF NOT EXISTS transactions (key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, imported_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS mapping (listing TEXT PRIMARY KEY, villa TEXT NOT NULL, room TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS villas (villa TEXT PRIMARY KEY, units INTEGER NOT NULL DEFAULT 1, fee_pct REAL NOT NULL DEFAULT 10, fee_basis TEXT NOT NULL DEFAULT 'Amount', currency TEXT NOT NULL DEFAULT 'IDR');
    CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, villa TEXT NOT NULL, month TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Owner expense');
    CREATE TABLE IF NOT EXISTS payout_links (reference TEXT NOT NULL, confirmation TEXT NOT NULL, PRIMARY KEY(reference, confirmation));
    CREATE TABLE IF NOT EXISTS approval (villa TEXT NOT NULL, month TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0, fingerprint TEXT NOT NULL, approved_at TEXT, PRIMARY KEY(villa, month));
    ''')
    _ensure_columns(con)
    return con

def import_transactions(df):
    records = df.copy()
    for col in records.select_dtypes(include=['datetime64[ns]']).columns:
        records[col] = records[col].dt.strftime('%Y-%m-%d').fillna('')
    records = records.where(pd.notna(records), None)
    count = 0
    with connection() as con:
        for _, r in records.iterrows():
            obj = r.to_dict(); obj.pop('row_id', None)
            serial = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
            key = hashlib.sha256(serial.encode('utf8')).hexdigest()
            result = con.execute('INSERT OR IGNORE INTO transactions(key,kind,payload) VALUES(?,?,?)', (key, obj['Type'], serial))
            count += result.rowcount
    return count

def load_transactions():
    with connection() as con:
        objs = [json.loads(r['payload']) for r in con.execute('SELECT payload FROM transactions ORDER BY imported_at, key')]
    if not objs: return pd.DataFrame()
    df = pd.DataFrame(objs)
    for c in ['Date','Booking date','Start date','End date','Arriving by date']:
        if c in df: df[c] = pd.to_datetime(df[c], errors='coerce')
    for c in ['Amount','Paid out','Service fee','Fast pay fee','Cleaning fee','Gross earnings','Airbnb remitted tax','Nights']:
        if c in df: df[c] = pd.to_numeric(df[c], errors='coerce')
    df['row_id'] = range(1,len(df)+1)
    return df

def get_mapping_detail():
    with connection() as con:
        rows = con.execute('SELECT listing,villa,room FROM mapping').fetchall()
    return {r['listing']:{'villa':r['villa'],'room':r['room']} for r in rows}

def get_mapping():
    details = get_mapping_detail()
    return {listing: data['villa'] for listing, data in details.items()}

def set_mapping(listing,villa,room=''):
    room = room or ''
    with connection() as con:
        con.execute('INSERT INTO mapping(listing,villa,room) VALUES(?,?,?) ON CONFLICT(listing) DO UPDATE SET villa=excluded.villa, room=excluded.room',(listing,villa,room))

def set_mappings_bulk(changes):
    """Atomically save all mapping rows so partial form saves cannot split properties."""
    if not changes or any(not v.get('villa','').strip() or not v.get('room','').strip() for v in changes.values()):
        raise ValueError('Property dan room/unit wajib diisi untuk setiap listing.')
    with connection() as con:
        for listing, values in changes.items():
            con.execute('''INSERT INTO mapping(listing,villa,room) VALUES(?,?,?)
                ON CONFLICT(listing) DO UPDATE SET villa=excluded.villa,room=excluded.room''',
                (listing,values['villa'].strip(),values['room'].strip()))

def get_settings(villa):
    with connection() as con:
        row = con.execute('SELECT * FROM villas WHERE villa=?',(villa,)).fetchone()
    return dict(row) if row else {'villa':villa,'units':1,'fee_pct':10.0,'fee_basis':'Amount','currency':'IDR'}

def set_settings(villa, units, fee_pct, fee_basis, currency):
    with connection() as con:
        con.execute('INSERT INTO villas(villa,units,fee_pct,fee_basis,currency) VALUES(?,?,?,?,?) ON CONFLICT(villa) DO UPDATE SET units=excluded.units,fee_pct=excluded.fee_pct,fee_basis=excluded.fee_basis,currency=excluded.currency',(villa,units,fee_pct,fee_basis,currency))

def get_expenses(villa,month):
    with connection() as con: return [dict(r) for r in con.execute('SELECT * FROM expenses WHERE villa=? AND month=? ORDER BY id',(villa,month))]

def add_expense(villa,month,desc,amount,currency,category):
    with connection() as con: con.execute('INSERT INTO expenses(villa,month,description,amount,currency,category) VALUES(?,?,?,?,?,?)',(villa,month,desc,amount,currency,category))

def remove_expense(eid,villa):
    with connection() as con: con.execute('DELETE FROM expenses WHERE id=? AND villa=?',(eid,villa))

def get_links():
    with connection() as con: return [(r['reference'],r['confirmation']) for r in con.execute('SELECT reference,confirmation FROM payout_links')]

def set_links(reference,codes):
    with connection() as con:
        con.execute('DELETE FROM payout_links WHERE reference=?',(reference,))
        for code in codes: con.execute('INSERT INTO payout_links(reference,confirmation) VALUES(?,?)',(reference,code))

def fingerprint(snapshot): return hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()

def approval_state(villa, month, fp):
    with connection() as con: row = con.execute('SELECT * FROM approval WHERE villa=? AND month=?',(villa,month)).fetchone()
    return bool(row and row['approved'] and row['fingerprint']==fp)

def set_approval(villa,month,fp,approved):
    with connection() as con: con.execute('INSERT INTO approval(villa,month,approved,fingerprint,approved_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(villa,month) DO UPDATE SET approved=excluded.approved,fingerprint=excluded.fingerprint,approved_at=CURRENT_TIMESTAMP',(villa,month,int(approved),fp))


def backup_database():
    """Create a consistent, downloadable SQLite snapshot via sqlite backup API."""
    import tempfile
    import os
    with connection() as source:
        fd, tmp = tempfile.mkstemp(suffix='.sqlite3')
        os.close(fd)
        try:
            with sqlite3.connect(tmp) as target:
                source.backup(target)
            with open(tmp,'rb') as infile:
                return infile.read()
        finally:
            os.unlink(tmp)


def reset_all_data():
    """Atomic reset of all user data; preserve the schema and application."""
    with connection() as con:
        con.execute('BEGIN IMMEDIATE')
        # Exact allowlist: never delete arbitrary tables or filesystem paths.
        for table in ('approval', 'payout_links', 'expenses', 'villas', 'mapping', 'transactions'):
            con.execute('DELETE FROM ' + table)
        con.execute("DELETE FROM sqlite_sequence WHERE name='expenses'")
