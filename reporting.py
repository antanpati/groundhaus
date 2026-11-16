"""Airbnb transaction CSV normalization and owner-reporting calculations."""
from __future__ import annotations
import io
import re
from datetime import date
import pandas as pd

NEEDED = {'Date', 'Type', 'Listing', 'Currency', 'Amount'}
DATE_COLS = ['Date', 'Booking date', 'Start date', 'End date', 'Arriving by date']
NUM_COLS = ['Amount', 'Paid out', 'Service fee', 'Fast pay fee', 'Cleaning fee', 'Gross earnings', 'Airbnb remitted tax', 'Nights']

# Accept the English and Indonesian CSV export layouts used by Airbnb.
# Normalize headers before applying the existing reservation-master logic.
HEADER_ALIASES = {
    'Tanggal': 'Date',
    'Tipe': 'Type',
    'Kode Konfirmasi': 'Confirmation code',
    'Tanggal pemesanan': 'Booking date',
    'Tanggal mulai': 'Start date',
    'Tanggal selesai': 'End date',
    'Tanggal kedatangan dana': 'Arriving by date',
    'Malam': 'Nights',
    'Tamu': 'Guest',
    'Dewasa': 'Adults',
    'Anak': 'Children',
    'Bayi': 'Infants',
    'Detail': 'Details',
    'Kode referensi': 'Reference code',
    'Mata Uang': 'Currency',
    'Nominal': 'Amount',
    'Dibayarkan': 'Paid out',
    'Biaya layanan': 'Service fee',
    'Biaya pembayaran cepat': 'Fast pay fee',
    'Biaya kebersihan': 'Cleaning fee',
    'Pendapatan kotor': 'Gross earnings',
    'Pajak yang disetorkan Airbnb': 'Airbnb remitted tax',
    'Tahun pendapatan': 'Earnings year',
}
TYPE_ALIASES = {
    'reservasi': 'Reservation',
    'reservation': 'Reservation',
    'payout': 'Payout',
    'pembayaran': 'Payout',
    'adjustment': 'Adjustment',
    'penyesuaian': 'Adjustment',
}

def _number(value):
    """Parse ID/EN amounts, e.g. 237.428,00 and 237,428.00 to 237428."""
    if value is None or pd.isna(value):
        return float('nan')
    raw=str(value).strip().replace('\u00a0','').replace(' ','')
    if not raw: return float('nan')
    negative = raw.startswith('(') and raw.endswith(')')
    raw=re.sub(r'[^0-9,.-]', '', raw)
    if not raw or raw=='-':return float('nan')
    if '.' in raw and ',' in raw:
        # The rightmost punctuation is the decimal point.
        decimal = '.' if raw.rfind('.') > raw.rfind(',') else ','
        thousands = ',' if decimal=='.' else '.'
        raw=raw.replace(thousands,'').replace(decimal,'.')
    elif ',' in raw:
        parts=raw.split(',')
        if len(parts)>2 and all(len(part)==3 for part in parts[1:]):raw=''.join(parts)
        elif len(parts)==2 and len(parts[1])==3:raw=''.join(parts)
        else:raw=raw.replace(',','.')
    elif raw.count('.')>1:
        parts=raw.split('.')
        if all(len(part)==3 for part in parts[1:]):raw=''.join(parts)
        else:raw=''.join(parts[:-1])+'.'+parts[-1]
    try:
        result=float(raw)
        return -abs(result) if negative else result
    except ValueError:
        return float('nan')

def parse_csv(content: bytes) -> pd.DataFrame:
    errors=[]
    for encoding in ('utf-8-sig','utf-8','cp1252'):
        try:
            df=pd.read_csv(io.BytesIO(content), encoding=encoding, dtype=str, keep_default_na=False, sep=None, engine='python')
            break
        except Exception as exc:
            errors.append(str(exc))
    else:
        raise ValueError('CSV tidak dapat dibaca: '+'; '.join(errors[:2]))
    df.columns=[str(c).strip().lstrip('\ufeff') for c in df.columns]
    renamed={col:HEADER_ALIASES.get(col,col) for col in df.columns}
    if len(set(renamed.values())) != len(renamed):
        raise ValueError('Ada kolom CSV yang menjadi duplikat setelah normalisasi bahasa. Periksa header CSV.')
    df=df.rename(columns=renamed)
    missing=NEEDED-set(df.columns)
    if missing:
        raise ValueError('Kolom wajib tidak ditemukan: '+', '.join(sorted(missing)))
    for col in DATE_COLS:
        if col not in df:df[col]=''
        df[col]=pd.to_datetime(df[col].replace('',None),errors='coerce',format='%m/%d/%Y')
    for col in NUM_COLS:
        if col not in df:df[col]=''
        df[col]=df[col].map(_number)
    for col in ('Listing','Currency','Type','Guest','Confirmation code','Reference code','Details'):
        if col not in df:df[col]=''
        df[col]=df[col].fillna('').astype(str).str.strip()
    df['Type']=df['Type'].map(lambda x:TYPE_ALIASES.get(x.casefold(),x.title()))
    df['Currency']=df['Currency'].str.upper()
    df['Listing']=df['Listing'].replace('', '(Listing tidak diketahui)')
    df['row_id']=range(1,len(df)+1)
    return df

def _villa_name(mapping_detail: dict, listing: str) -> str:
    val = mapping_detail.get(listing, {})
    if isinstance(val, dict):
        return (val.get('villa') or listing).strip()
    return str(val or listing).strip()

def _room_name(mapping_detail: dict, listing: str) -> str:
    val = mapping_detail.get(listing, {})
    if isinstance(val, dict):
        room = (val.get('room') or '').strip()
        return room or listing
    return str(listing)

def make_reservations(df: pd.DataFrame, mapping_detail: dict[str,dict], date_mode: str, start: date, end: date, selected: list[str] | None = None) -> pd.DataFrame:
    reservations = df[df['Type'].eq('Reservation')].copy()
    reservations['Villa'] = reservations['Listing'].map(lambda x: _villa_name(mapping_detail, x))
    reservations['Room'] = reservations['Listing'].map(lambda x: _room_name(mapping_detail, x))
    date_col = {'Transaction date':'Date', 'Check-in date':'Start date', 'Booking date':'Booking date'}[date_mode]
    dates = reservations[date_col].dt.date
    reservations = reservations.loc[dates.ge(start) & dates.le(end)].copy()
    if selected is not None:
        reservations = reservations[reservations['Villa'].isin(selected)].copy()
    reservations['Net amount'] = reservations['Amount']
    reservations['Host fee'] = reservations['Service fee'].fillna(0)
    reservations['Gross'] = reservations['Gross earnings']
    reservations['Nights'] = reservations['Nights'].fillna(0)
    return reservations

def summary(reservations: pd.DataFrame) -> pd.DataFrame:
    columns = ['Villa','Currency','Reservations','Nights','Gross earnings','Service fee','Amount']
    if reservations.empty:
        return pd.DataFrame(columns=columns)
    group = reservations.groupby(['Villa','Currency'], dropna=False, as_index=False).agg(
        Reservations=('row_id','count'), Nights=('Nights','sum'),
        **{'Gross earnings':('Gross earnings','sum'),'Service fee':('Host fee','sum'),'Amount':('Amount','sum')})
    return group.sort_values(['Villa','Currency']).reset_index(drop=True)

def payout_table(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    payout = df[df['Type'].eq('Payout')].copy()
    payout = payout[payout['Date'].dt.date.ge(start) & payout['Date'].dt.date.le(end)]
    return payout

def money(x, currency='IDR'):
    if pd.isna(x):
        return '—'
    if currency == 'IDR':
        return 'IDR ' + f'{float(x):,.0f}'.replace(',', '.')
    return f'{currency} {float(x):,.2f}'

def excel_safe(value):
    """Prevent spreadsheet formula injection from user/CSV strings."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ''
    if isinstance(value, (pd.Timestamp, date)):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, str):
        return "'" + value if re.match(r'^\s*[=+@\-\t\r]', value) else value
    return float(value) if isinstance(value, (int, float)) else str(value)
