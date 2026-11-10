"""Airbnb transaction CSV normalization and owner-reporting calculations."""
from __future__ import annotations
import io
import re
from datetime import date
import pandas as pd

NEEDED = {'Date', 'Type', 'Listing', 'Currency', 'Amount'}
DATE_COLS = ['Date', 'Booking date', 'Start date', 'End date', 'Arriving by date']
NUM_COLS = ['Amount', 'Paid out', 'Service fee', 'Fast pay fee', 'Cleaning fee', 'Gross earnings', 'Airbnb remitted tax', 'Nights']

def parse_csv(content: bytes) -> pd.DataFrame:
    errors = []
    for encoding in ('utf-8-sig', 'utf-8', 'cp1252'):
        try:
            df = pd.read_csv(io.BytesIO(content), encoding=encoding, dtype=str, keep_default_na=False, sep=None, engine='python')
            break
        except Exception as exc:
            errors.append(str(exc))
    else:
        raise ValueError('CSV tidak dapat dibaca: ' + '; '.join(errors[:2]))
    df.columns = [str(c).strip() for c in df.columns]
    missing = NEEDED - set(df.columns)
    if missing:
        raise ValueError('Kolom wajib tidak ditemukan: ' + ', '.join(sorted(missing)))
    for col in DATE_COLS:
        if col not in df:
            df[col] = ''
        df[col] = pd.to_datetime(df[col].replace('', None), errors='coerce', format='%m/%d/%Y')
    for col in NUM_COLS:
        if col not in df:
            df[col] = ''
        cleaned = df[col].astype(str).str.replace(',', '', regex=False).str.replace(r'[^0-9.\-]', '', regex=True)
        df[col] = pd.to_numeric(cleaned.replace('', None), errors='coerce')
    for col in ('Listing', 'Currency', 'Type', 'Guest', 'Confirmation code', 'Reference code', 'Details'):
        if col not in df:
            df[col] = ''
        df[col] = df[col].fillna('').astype(str).str.strip()
    df['Type'] = df['Type'].str.title()
    df['Currency'] = df['Currency'].str.upper()
    df['Listing'] = df['Listing'].replace('', '(Listing tidak diketahui)')
    df['row_id'] = range(1, len(df)+1)
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
