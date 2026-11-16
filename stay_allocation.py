"""Stay-based monthly allocation for actual and upcoming reservations.

Source booking amounts are not modified. Monetary amounts are allocated by
night-overlap using Decimal cents/IDR units and a residual on the last month.
A fully cancelled stay with an explicitly retained penalty is assigned to its
original/effective check-in month (no occupied room nights).
"""
from __future__ import annotations
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

MONEY_FIELDS = ('Amount', 'Service fee', 'Gross earnings')
ZERO_NIGHT_REASON = 'cancelled-penalty-checkin-month'

def _date(value):
    if isinstance(value, date) and not isinstance(value, pd.Timestamp): return value
    d = pd.to_datetime(value, errors='coerce')
    return None if pd.isna(d) else d.date()

def _first_next_month(d):
    return (d.replace(day=28)+timedelta(days=4)).replace(day=1)

def months_touched(start, end):
    """Stay interval is [check-in, check-out); checkout contributes zero nights."""
    if not start or not end or end <= start: return []
    months=[]; current=start.replace(day=1)
    while current < end:
        following=_first_next_month(current)
        nights=max(0,(min(end,following)-max(start,current)).days)
        if nights: months.append((current.strftime('%Y-%m'),nights))
        current=following
    return months

def allocate_value(value, weights, places=2):
    """Allocate a booking's value exactly across months, including signed values.

    Uses the original total as the rounding basis. Remainder goes to last month,
    making the sum of allocations equal to the source total to the cent.
    """
    if not weights: return []
    quant=Decimal('1').scaleb(-places)
    total=Decimal(str(0 if pd.isna(value) else value)).quantize(quant, rounding=ROUND_HALF_UP)
    den=Decimal(sum(weights))
    previous=Decimal('0'); result=[]
    for index,weight in enumerate(weights):
        share=total-previous if index==len(weights)-1 else (total*Decimal(weight)/den).quantize(quant,rounding=ROUND_HALF_UP)
        result.append(float(share));previous+=share
    return result

def allocate_month(df:pd.DataFrame, month:str, *, include_cancelled_penalty=True):
    """Return one row per booking relevant to the given calendar month.

    Columns Nights/Amount/Service fee/Gross earnings contain month-only values.
    Original source values are preserved in Original * columns. Listing,
    Room, Guest and full check-in/out are kept for reconciliation and audit.
    """
    cols=['Original Nights','Original Amount','Original Service fee',
          'Original Gross earnings','Allocation Rule','Allocation Month','Allocation Ratio']
    if df.empty:
        return df.assign(**{c:pd.Series(dtype='object') for c in cols})
    rows=[]
    for _,item in df.iterrows():
        start=_date(item.get('Start date'));end=_date(item.get('End date'))
        if not start:continue
        nights=(end-start).days if end else 0
        if nights < 0: continue
        original=item.to_dict()
        if nights==0:
            # Cancelled booking with a penalty is not a stay. Post retained
            # revenue to effective check-in month only; never inflate occupancy.
            if not include_cancelled_penalty or str(original.get('_status',''))!='Cancelled' or start.strftime('%Y-%m')!=month:
                continue
            row=original.copy()
            row.update({'Original Nights':0, 'Original Amount':float(original.get('Amount') or 0),
                        'Original Service fee':float(original.get('Service fee') or 0),
                        'Original Gross earnings':float(original.get('Gross earnings') or 0),
                        'Nights':0, 'Allocation Rule':ZERO_NIGHT_REASON,
                        'Allocation Month':month,'Allocation Ratio':0.0})
            rows.append(row);continue
        pieces=months_touched(start,end)
        matching=[(i,n) for i,(m,n) in enumerate(pieces) if m==month]
        if not matching:continue
        ix, allocated_nights=matching[0]; weights=[n for _,n in pieces]
        row=original.copy()
        row['Original Nights']=nights
        row['Nights']=allocated_nights
        row['Allocation Month']=month
        row['Allocation Rule']='stay-nights'
        row['Allocation Ratio']=allocated_nights/nights
        for field in MONEY_FIELDS:
            row['Original '+field]=float(original.get(field) or 0)
            row[field]=allocate_value(original.get(field) or 0,weights)[ix]
        rows.append(row)
    if not rows:return df.iloc[:0].copy().assign(**{c:pd.Series(dtype='object') for c in cols})
    return pd.DataFrame(rows).reset_index(drop=True)

def available_months(df):
    months=set()
    if df.empty:return []
    for _,r in df.iterrows():
        start=_date(r.get('Start date'));end=_date(r.get('End date'))
        if not start:continue
        months.update(m for m,_ in months_touched(start,end))
        if start==end and str(r.get('_status',''))=='Cancelled':
            months.add(start.strftime('%Y-%m'))
    return sorted(months)
