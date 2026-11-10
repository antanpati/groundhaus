"""Revenue on check-in; occupancy counts in-month night overlap."""
import calendar
from datetime import date, timedelta
import pandas as pd
from reporting import make_reservations

def month_limits(month):
    y,m = map(int,month.split('-'))
    return date(y,m,1),date(y,m,calendar.monthrange(y,m)[1])

def _villa_name(mapping_detail, listing):
    val = mapping_detail.get(listing, {})
    if isinstance(val, dict):
        return (val.get('villa') or listing).strip()
    return str(val or listing).strip()

def _room_name(mapping_detail, listing):
    val = mapping_detail.get(listing, {})
    if isinstance(val, dict):
        room = (val.get('room') or '').strip()
        return room or listing
    return str(listing)

def reservation_month(df,mapping_detail,villa,month):
    start,end = month_limits(month)
    return make_reservations(df,mapping_detail,'Check-in date',start,end,[villa])

def occupancy(df,mapping_detail,villa,month,units):
    start,end = month_limits(month)
    r=df[df['Type'].eq('Reservation')].copy()
    r['Villa']=r['Listing'].map(lambda x:_villa_name(mapping_detail,x))
    r['Room']=r['Listing'].map(lambda x:_room_name(mapping_detail,x))
    r=r[r['Villa']==villa]
    nights=set()
    for _,row in r.iterrows():
        a,b=row['Start date'],row['End date']
        if pd.isna(a) or pd.isna(b):
            continue
        room_key = str(row['Room'] or row['Listing'])
        day=max(a.date(),start)
        stop=min(b.date(),end+timedelta(days=1))
        while day<stop:
            nights.add((room_key,day.isoformat()))
            day+=timedelta(days=1)
    capacity=units*(end-start).days+units
    occupied=len(nights)
    return {'occupied':occupied,'capacity':capacity,'occupancy_pct':occupied/capacity*100 if capacity else 0,'over_capacity':occupied>capacity}

def summarize(res,expenses,settings):
    curr=settings['currency']
    sub=res[res['Currency'].eq(curr)] if not res.empty else res
    gross=float(sub['Gross earnings'].sum()) if len(sub) else 0
    ota=float(sub['Service fee'].sum()) if len(sub) else 0
    amount=float(sub['Amount'].sum()) if len(sub) else 0
    base= gross if settings['fee_basis']=='Gross earnings' else amount
    fee=round(base*float(settings['fee_pct'])/100,2)
    costs=sum(float(e['amount']) for e in expenses if e['currency']==curr)
    return dict(currency=curr,reservations=len(sub),nights=float(sub['Nights'].sum()) if len(sub) else 0,gross=gross,ota=ota,amount=amount,fee=fee,expenses=costs,owner_estimate=amount-fee-costs,foreign_currencies=sorted(set(res['Currency'].dropna())-{curr}) if len(res) else [])

def reconciliation(df,existing_links):
    if df.empty: return [],[]
    res=df[df['Type'].eq('Reservation')].copy()
    payouts=df[df['Type'].eq('Payout')].copy()
    manual={}
    for reference,code in existing_links:manual.setdefault(reference,[]).append(code)
    rows=[]; used=set()
    for _,p in payouts.iterrows():
        reference=p.get('Reference code','')
        if not reference:continue
        current=manual.get(reference,[])
        options=res[(res['Currency']==p['Currency']) & (abs(res['Amount']-p['Paid out'])<=1)]
        suggestion=''
        if len(options)==1 and not current:
            code=options.iloc[0]['Confirmation code']
            if code not in used and code not in {c for codes in manual.values() for c in codes}: suggestion=code
        used.update(current)
        rows.append(dict(reference=reference,date=p['Date'],currency=p['Currency'],paid_out=float(p['Paid out']) if pd.notna(p['Paid out']) else 0,codes=current,suggestion=suggestion,details=p.get('Details','')))
    return rows,res
