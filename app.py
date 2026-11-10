"""Groundhaus Airbnb Reporting V2.3 — local-only Streamlit app."""
from datetime import date
import os
import hmac
import pandas as pd
import streamlit as st
import store
from reporting import parse_csv,money
from engine import reservation_month,occupancy,summarize,reconciliation
from owner_exports import make_excel,make_pdf,zip_all

st.set_page_config(page_title='GROUNDHAUS | Villa Reporting V2.3',page_icon='🏡',layout='wide')
st.markdown('<style>h1,h2,h3 {color:#1c4e89} div[data-testid="stMetric"] {background:#f2f5fa;padding:13px;border-radius:9px}</style>',unsafe_allow_html=True)
# Online deployments require an admin password; the local launcher binds only to localhost.
local_mode = os.environ.get('APP_MODE') == 'local'
admin_password = os.environ.get('APP_PASSWORD', '')
if not local_mode:
    if len(admin_password) < 16:
        st.error('APP_PASSWORD belum diatur atau terlalu pendek (minimal 16 karakter). Aplikasi online tidak akan menampilkan data sebelum dikonfigurasi.')
        st.stop()
    if not st.session_state.get('authenticated', False):
        st.title('GROUNDHAUS · Login Admin')
        with st.form('admin_login'):
            entered = st.text_input('Password admin', type='password')
            submitted = st.form_submit_button('Login', type='primary')
            if submitted:
                if hmac.compare_digest(entered, admin_password):
                    st.session_state['authenticated'] = True
                    st.rerun()
                else:
                    st.error('Password salah.')
        st.stop()
    with st.sidebar:
        if st.button('Logout'):
            st.session_state.clear()
            st.rerun()

st.title('GROUNDHAUS · Villa Reporting')
st.caption('Local V2.3  |  Upload sekali · Mapping listing ke villa + room · Pilih villa · Review · Export owner report')

with st.sidebar:
    st.header('1. Data Master')
    uploaded=st.file_uploader('Airbnb Transaction History CSV',type=['csv'])
    if uploaded and st.button('Import CSV ke histori',type='primary'):
        try:
            parsed=parse_csv(uploaded.getvalue())
            added=store.import_transactions(parsed)
            st.success(f'{added} transaksi baru disimpan; reupload identik tidak menggandakan data.')
        except Exception as e:
            st.error(f'Import gagal: {e}')
    st.caption('Data tersimpan di app_data/groundhaus.sqlite3 pada laptop ini. Backup folder app_data secara berkala. Jangan upload CSV owner ke layanan publik.')

# Reset applies to ALL application data, not just the currently selected villa.
with st.sidebar.expander('⚠️ Reset seluruh data', expanded=False):
    st.warning('Permanen: menghapus semua reservasi, payout, mapping villa/kamar, settings, expenses, payout matching, dan approval. Tidak dapat di-undo.')
    try:
        st.download_button('Download backup database sebelum reset', store.backup_database(), file_name='groundhaus_backup.sqlite3', mime='application/octet-stream')
    except Exception as exc:
        st.error(f'Backup gagal: {exc}')
    with st.form('delete_all_data_form'):
        typed = st.text_input('Ketik HAPUS SEMUA DATA untuk konfirmasi')
        confirm_password = st.text_input('Password admin (mode online)', type='password') if not local_mode else None
        checked = st.checkbox('Saya memahami seluruh histori dan pengaturan akan dihapus permanen')
        wipe = st.form_submit_button('Hapus seluruh data')
        if wipe:
            authorized = local_mode or hmac.compare_digest(confirm_password or '', admin_password)
            if typed != 'HAPUS SEMUA DATA' or not checked or not authorized:
                st.error('Konfirmasi belum benar. Data tidak dihapus.')
            else:
                store.reset_all_data()
                # Invalidate cached report files, widgets and selection state.
                st.session_state.clear()
                st.success('Seluruh data aplikasi berhasil dihapus.')
                st.rerun()

raw=store.load_transactions()
if raw.empty:
    st.info('Mulai dengan upload CSV Airbnb di sidebar, lalu klik **Import CSV ke histori**. File contoh tersedia di sample_data.')
    st.stop()

res_all=raw[raw['Type'].eq('Reservation')].copy()
duplicates=res_all[res_all['Confirmation code'].ne('') & res_all.duplicated('Confirmation code',keep=False)]
if not duplicates.empty:
    st.error(f'{duplicates["Confirmation code"].nunique()} confirmation code memiliki lebih dari satu versi transaksi; periksa CSV sebelum finalisasi laporan. Import identik tidak menggandakan transaksi, tetapi transaksi yang berubah perlu direkonsiliasi manual.')
if (raw['Currency'].nunique()>1):
    st.info('Data memiliki lebih dari satu currency. Summary villa hanya menjumlahkan currency yang ditetapkan di pengaturan villa.')

st.subheader('2. Listing → Property → Room Mapping')
existing = store.get_mapping_detail()
names = sorted(res_all['Listing'].dropna().unique())
if not names:
    st.warning('Tidak ada reservation rows di histori.')
    st.stop()
needs_mapping = any(x not in existing for x in names)
with st.expander('Atur property dan nama kamar / unit', expanded=needs_mapping):
    st.caption('Satu property boleh punya beberapa kamar/listing. Setelah mengisi, klik **Simpan mapping**. Baru setelah itu dropdown **Pilih Villa** diperbarui.')
    with st.form('mapping_form'):
        changes = {}
        for name in names:
            saved = existing.get(name, {})
            c1,c2,c3 = st.columns([1.5,1.5,1.8])
            c1.markdown(f'**{name}**')
            villa_val = c2.text_input('Villa / Property', value=saved.get('villa',name), key='villa_'+name)
            room_val = c3.text_input('Room / Unit', value=saved.get('room') or name, key='room_'+name)
            changes[name] = {'villa':villa_val.strip(), 'room':room_val.strip()}
        if st.form_submit_button('Simpan mapping', type='primary'):
            invalid = [name for name,value in changes.items() if not value['villa'] or not value['room']]
            if invalid:
                st.error('Nama property dan kamar harus terisi.')
            else:
                store.set_mappings_bulk(changes)
                st.session_state['mapping_saved_notice'] = True
                st.rerun()

if st.session_state.pop('mapping_saved_notice', False):
    st.success('Mapping tersimpan. Dropdown Pilih Villa sekarang menggunakan nama property, bukan nama listing.')

# Always read persisted mappings after saving; never derive property choices from editable form fields.
existing = store.get_mapping_detail()
mapping_detail = {name:existing.get(name, {'villa':name,'room':name}) for name in names}
all_villas = sorted({(mapping_detail[name].get('villa') or name).strip() for name in names})

property_overview = []
for property_name in all_villas:
    listing_names = [name for name in names if (mapping_detail[name].get('villa') or name).strip() == property_name]
    room_names = sorted({(mapping_detail[name].get('room') or name).strip() for name in listing_names})
    property_overview.append({'Property':property_name, 'Jumlah Room / Unit':len(room_names), 'Jumlah Listing Airbnb':len(listing_names), 'Nama Room / Unit':', '.join(room_names)})
with st.expander('Lihat hasil penggabungan property dan kamar', expanded=True):
    st.dataframe(pd.DataFrame(property_overview), hide_index=True, use_container_width=True)

left,right=st.columns([1,2])
with left:
    st.subheader('3. Pilih Villa')
    villa=st.selectbox('Nama villa / property',all_villas, key='selected_property')
    selected_rooms=next(row['Nama Room / Unit'] for row in property_overview if row['Property']==villa)
    st.caption(f'Room / Unit: {selected_rooms}')
    period_dates=res_all['Start date'].dropna()
    default_month=period_dates.max().strftime('%Y-%m') if not period_dates.empty else date.today().strftime('%Y-%m')
    months=sorted(set(period_dates.dt.strftime('%Y-%m')).union({default_month,date.today().strftime('%Y-%m')}),reverse=True)
    month=st.selectbox('Periode check-in (YYYY-MM)',months)
    st.caption('Periode revenue = bulan check-in. Occupancy tetap dihitung berdasarkan malam yang benar-benar menginap di bulan ini.')
with right:
    st.subheader('Settings Villa')
    setting=store.get_settings(villa)
    with st.form('villa_settings'):
        c1,c2=st.columns(2)
        with c1:
            units=st.number_input('Jumlah unit/kamar tersedia',min_value=1,max_value=1000,value=int(setting['units']))
            fee_pct=st.number_input('Management fee (%)',min_value=0.0,max_value=100.0,value=float(setting['fee_pct']),step=0.5)
        with c2:
            fee_basis=st.selectbox('Dasar management fee',['Amount','Gross earnings'],index=['Amount','Gross earnings'].index(setting['fee_basis']))
            currency_options=['IDR','USD','EUR','AUD','SGD','GBP']
            curr=st.selectbox('Currency laporan',currency_options,index=currency_options.index(setting['currency']) if setting['currency'] in currency_options else 0)
        if st.form_submit_button('Simpan setting villa'):
            store.set_settings(villa,units,fee_pct,fee_basis,curr)
            st.success('Setting tersimpan')
            st.rerun()

res=reservation_month(raw,mapping_detail,villa,month)
settings=store.get_settings(villa)
expenses=store.get_expenses(villa,month)
s=summarize(res,expenses,settings)
occ=occupancy(raw,mapping_detail,villa,month,settings['units'])
foreign=res[res['Currency'].ne(settings['currency'])]
if len(foreign):
    st.error(f'{len(foreign)} reservasi bermata uang lain tidak termasuk summary {settings["currency"]}. Periksa sebelum approve.')
if occ['over_capacity']:
    st.error('Room nights melebihi kapasitas. Periksa jumlah unit, mapping room/unit, atau transaksi duplikat.')

st.divider()
st.subheader(f'4. Dashboard · {villa} / {month}')
c1,c2,c3,c4=st.columns(4)
c1.metric('Reservation Amount',money(s['amount'],s['currency']))
c2.metric('Reservation count',str(s['reservations']))
c3.metric('Occupancy',f"{occ['occupancy_pct']:.2f}%")
c4.metric('Owner balance (estimasi)',money(s['owner_estimate'],s['currency']))
c1,c2,c3,c4=st.columns(4)
c1.metric('Gross earnings*',money(s['gross'],s['currency']))
c2.metric('OTA commission',money(s['ota'],s['currency']))
c3.metric('Management fee',money(s['fee'],s['currency']))
c4.metric('Room nights',f"{occ['occupied']} / {occ['capacity']}")
st.caption('*Gross earnings adalah proxy Publish Rate dari CSV, bukan field publish-rate independen. Amount pada Reservation bukan bukti transfer dana dari Airbnb.')
if len(res):
    detail=(res[['Guest','Start date','End date','Room','Listing','Confirmation code','Currency','Nights','Gross earnings','Service fee','Amount']]
              .sort_values(['Start date','Room','Listing'])
              .rename(columns={'Guest':'Guest Name','Start date':'Check In','End date':'Check Out','Room':'Room / Unit','Listing':'Airbnb Listing','Confirmation code':'Confirmation Code','Nights':'Nights','Gross earnings':'Gross Earnings','Service fee':'OTA Commission','Amount':'Reservation Amount'}))
    money_cols=['Gross Earnings','OTA Commission','Reservation Amount']
    style_fmt={col:(lambda x, cur=settings['currency']: money(x,cur) if pd.notna(x) else '—') for col in money_cols}
    style_fmt.update({'Check In':lambda x:'' if pd.isna(x) else x.strftime('%Y-%m-%d'),'Check Out':lambda x:'' if pd.isna(x) else x.strftime('%Y-%m-%d'),'Nights':'{:,.0f}'})
    st.dataframe(detail.style.format(style_fmt),use_container_width=True,hide_index=True)
else:
    st.info('Tidak ada reservasi dengan tanggal check-in pada bulan ini.')

st.subheader('5. Additional Expenses')
st.caption('Input manual untuk bulan dan villa terpilih. Nilai positif mengurangi estimasi saldo owner; nilai negatif dapat dipakai untuk adjustment/kredit.')
with st.form('new_expense'):
    a,b,c,d=st.columns([1,2,1,1])
    category=a.selectbox('Kategori',['Owner expense','Channel Manager Fee','Maintenance','Operational','Adjustment'])
    description=b.text_input('Keterangan')
    amount=c.number_input('Nominal',value=0.0,step=10000.0)
    currency=d.selectbox('Currency',[settings['currency']])
    if st.form_submit_button('Tambah expense'):
        if not description.strip() or not amount:
            st.warning('Isi keterangan dan nominal bukan nol.')
        else:
            store.add_expense(villa,month,description.strip(),amount,currency,category)
            st.rerun()
for e in expenses:
    a,b=st.columns([6,1])
    a.write(f"{e['category']} | {e['description']} — {money(e['amount'],e['currency'])}")
    if b.button('Hapus',key=f"remove_{e['id']}"):
        store.remove_expense(e['id'],villa)
        st.rerun()

st.subheader('6. Airbnb Payout Reconciliation')
st.caption('Auto-suggestion hanya untuk satu reservasi dengan nominal dan currency yang cocok secara unik. Transfer gabungan harus dipilih manual. Pencocokan payout TIDAK membuktikan dana sudah masuk rekening.')
links=store.get_links();rows,all_res=reconciliation(raw,links)
code_to_villa={str(r['Confirmation code']):(mapping_detail.get(r['Listing'],{}).get('villa') or r['Listing']) for _,r in all_res.iterrows()}
codes_for_villa=sorted({str(r['Confirmation code']) for _,r in all_res.iterrows() if (mapping_detail.get(r['Listing'],{}).get('villa') or r['Listing'])==villa and r['Confirmation code']})
code_amount={str(r['Confirmation code']):float(r['Amount']) for _,r in all_res.iterrows() if r['Confirmation code']}
code_curr={str(r['Confirmation code']):str(r['Currency']) for _,r in all_res.iterrows() if r['Confirmation code']}
related=[]
for row in rows:
    if any(code_to_villa.get(code)==villa for code in row['codes']) or (row['suggestion'] and code_to_villa.get(row['suggestion'])==villa):
        related.append(row)
    elif row['currency']==settings['currency'] and not row['codes']:
        related.append(row)
with st.expander(f'Payout matching ({len(related)} candidate/matched)',expanded=False):
    for p in related:
        payout_date = p['date'].date() if pd.notna(p['date']) else ''
        st.markdown(f"**{p['reference']}** · {money(p['paid_out'], p['currency'])} · {payout_date}")
        selected_current=p['codes']
        if p['suggestion']:
            st.caption(f"Suggested: {p['suggestion']} (not applied until saved)")
        options=sorted(set(codes_for_villa+selected_current))
        selected=st.multiselect('Link confirmation codes',options,default=selected_current,key='match_'+p['reference'])
        total=sum(code_amount.get(c,0) for c in selected)
        valid=(not selected or (abs(total-p['paid_out'])<=1 and all(code_curr.get(c)==p['currency'] for c in selected)))
        if selected:
            st.caption(f'Selected reservation sum: {money(total,p["currency"])} | '+('Matched' if valid else 'DOES NOT MATCH payout total/currency'))
        if st.button('Save matching',key='save_'+p['reference']):
            assigned={c for ref,c in links if ref!=p['reference']}
            if not valid:
                st.error('Jumlah reservation Amount dan payout harus sama (+/- 1) dan currency harus sama.')
            elif set(selected)&assigned:
                st.error('Reservasi ini sudah ditautkan ke payout lain.')
            elif any(code_to_villa.get(c)!=villa for c in selected):
                st.error('Reservasi dari villa lain tidak bisa ditautkan di sini.')
            else:
                store.set_links(p['reference'],selected)
                st.rerun()
    st.caption('Payout tanpa kemungkinan pencocokan unik bisa diperiksa dari seluruh transaksi sumber; tidak dimasukkan ke total owner tanpa validasi.')

st.subheader('7. Review, Approve & Export')
snapshot={'villa':villa,'month':month,'settings':settings,'reservations':res[['Confirmation code','Currency','Amount','Gross earnings','Service fee','Nights','Room','Listing']].fillna('').astype(str).to_dict('records'),'occupancy':occ,'expenses':expenses,'links':sorted([(ref,code) for ref,code in links if code_to_villa.get(code)==villa])}
fp=store.fingerprint(snapshot)
approved=store.approval_state(villa,month,fp)
if approved:
    st.success('APPROVED · report matches the most recently approved data.')
else:
    st.warning('DRAFT · report requires review. Data changes invalidate previous approval.')
if st.button('Approve current report',disabled=bool(duplicates.size) or bool(occ['over_capacity']) or bool(len(foreign))):
    store.set_approval(villa,month,fp,True)
    st.rerun()
if st.button('Revoke approval'):
    store.set_approval(villa,month,fp,False)
    st.rerun()
report_payouts=[p for p in rows if p['codes'] and all(code_to_villa.get(code)==villa for code in p['codes'])]
subset = res[res['Currency'].eq(settings['currency'])]
xlsx=make_excel(villa,month,subset,s,occ,expenses,report_payouts,approved)
try:
    pdf=make_pdf(villa,month,subset,s,occ,expenses,report_payouts,approved)
    pdf_error=None
except (RuntimeError, ValueError) as exc:
    pdf=None
    pdf_error=str(exc)
    st.error('PDF belum bisa dibuat: '+pdf_error)
a,b=st.columns(2)
with a:
    st.download_button('Download Excel Villa',xlsx,file_name=f'{villa.replace("/","-")}_{month}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
with b:
    st.download_button('Download PDF Villa',pdf,file_name=f'{villa.replace("/","-")}_{month}.pdf',mime='application/pdf')
with st.expander('Export semua villa dalam satu ZIP (bulan sama)'):
    if st.button('Generate ZIP seluruh villa'):
        grouped={}
        for v in all_villas:
            vs=store.get_settings(v);vr=reservation_month(raw,mapping_detail,v,month);ve=store.get_expenses(v,month)
            ss=summarize(vr,ve,vs);oo=occupancy(raw,mapping_detail,v,month,vs['units'])
            vfp=store.fingerprint({'villa':v,'month':month,'settings':vs,'reservations':vr[['Confirmation code','Currency','Amount','Gross earnings','Service fee','Nights','Room','Listing']].fillna('').astype(str).to_dict('records'),'occupancy':oo,'expenses':ve,'links':sorted([(ref,code) for ref,code in links if code_to_villa.get(code)==v])})
            va=store.approval_state(v,month,vfp)
            vp=[p for p in rows if p['codes'] and all(code_to_villa.get(code)==v for code in p['codes'])]
            subset_v=vr[vr['Currency'].eq(vs['currency'])]
            try:
                v_pdf=make_pdf(v,month,subset_v,ss,oo,ve,vp,va)
            except (RuntimeError,ValueError) as exc:
                st.error('ZIP gagal karena PDF untuk '+v+' belum bisa dibuat: '+str(exc))
                break
            grouped[v]={'xlsx':make_excel(v,month,subset_v,ss,oo,ve,vp,va),'pdf':v_pdf}
        else:
            st.session_state['all_zip']=zip_all(grouped)
    if 'all_zip' in st.session_state:
        st.download_button('Download ZIP',st.session_state['all_zip'],file_name=f'GROUNDHAUS_OWNERS_{month}.zip',mime='application/zip')

st.subheader('8. Histori Revenue')
st.caption('Perbandingan hanya bulan check-in dengan transaksi yang sudah diimport. Bulan yang tidak ada reservasi bukan berarti properti selalu kosong.')
months_all=sorted(set(res_all['Start date'].dropna().dt.strftime('%Y-%m')))
history=[]
for mo in months_all:
    rr=reservation_month(raw,mapping_detail,villa,mo)
    sm=summarize(rr,store.get_expenses(villa,mo),settings)
    history.append({'Month':mo,'Reservation Amount':sm['amount'],'Reservation Count':sm['reservations'],'Management Fee':sm['fee']})
if history:
    hist=pd.DataFrame(history).set_index('Month')
    st.line_chart(hist['Reservation Amount'])
    hist_display = hist.reset_index()
    hist_style = hist_display.style.format({
        'Reservation Amount': lambda x, cur=settings['currency']: money(x,cur),
        'Reservation Count': '{:,.0f}',
        'Management Fee': lambda x, cur=settings['currency']: money(x,cur),
    })
    st.dataframe(hist_style,use_container_width=True,hide_index=True)
st.caption('V2.3 lokal. Backup file app_data/groundhaus.sqlite3. Hindari pengiriman database ini ke pihak lain karena berisi data tamu.')
