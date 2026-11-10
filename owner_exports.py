"""Owner-facing Excel and PDF, resembling the sample monthly recap layout."""
import io,zipfile,re,os,glob,unicodedata
from datetime import date
from openpyxl import Workbook
from openpyxl.styles import PatternFill,Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4,landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT
from xml.sax.saxutils import escape
from reporting import excel_safe,money

BLUE='1C4E89'

# Unicode fonts are found on the user's computer; font files are not included in the app.
_FONT_NAME = 'GroundhausUnicode'
_RTL_RANGE = re.compile(r'[\u0590-\u08ff\ufb1d-\ufeff]')

def _unicode_font():
    """Register a TTF Unicode font (macOS/Linux), fail rather than printing black squares."""
    if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _FONT_NAME
    candidates = []
    if os.environ.get('GROUNDHAUS_UNICODE_FONT'):
        candidates.append(os.environ['GROUNDHAUS_UNICODE_FONT'])
    candidates += [
        '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
        '/Library/Fonts/Arial Unicode.ttf',
        '/Library/Fonts/DejaVuSans.ttf',
        '/Library/Fonts/NotoSansArabic-Regular.ttf',
        '/Library/Fonts/NotoNaskhArabic-Regular.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf',
        '/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf',
    ]
    candidates += sorted(glob.glob('/Library/Fonts/*Unicode*.ttf'))
    candidates += sorted(glob.glob('/Library/Fonts/*Arabic*.ttf'))
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NAME,path))
            # Check for glyph coverage. In particular, ReportLab can load a font
            # that lacks Arabic and silently substitute black square glyphs.
            font=pdfmetrics.getFont(_FONT_NAME)
            cmap=getattr(getattr(font,'face',None),'charToGlyph',{})
            if ord('م') in cmap and ord('ﺑ') in cmap:
                return _FONT_NAME
        except Exception:
            pass
        # A font without Arabic can be registered, but must not be used.
        try: del pdfmetrics._fonts[_FONT_NAME]
        except Exception: pass
    raise RuntimeError(
        'Font Unicode Arabic tidak ditemukan. Install font DejaVu Sans (TTF), '
        'atau set GROUNDHAUS_UNICODE_FONT ke path file .ttf dengan dukungan Arab. '
        'Font .ttc/.otf belum didukung oleh modul ini.'
    )

def _pdf_text(value):
    """Preserve original stored text; reshape only its PDF display representation."""
    text = str(value if value is not None else '')
    if _RTL_RANGE.search(text):
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
        except ImportError as exc:
            raise RuntimeError(
                'Modul Arabic PDF belum terpasang. Jalankan bash run_mac.command '
                'untuk menginstall arabic-reshaper dan python-bidi.'
            ) from exc
        text = get_display(arabic_reshaper.reshape(text), base_dir='R')
    return escape(text)

COLUMNS=['No','Guest Name','Check In','Check Out','Nights','Room / Listing','Publish Rate*','OTA Commission','Payout (Amount)','Remarks']

def _room_listing_label(r):
    room = str(r.get('Room') or '').strip()
    listing = str(r.get('Listing') or '').strip()
    if room and room != listing:
        return f'{room} | {listing}'
    return room or listing

def _rows(res):
    out=[]
    for i,(_,r) in enumerate(res.sort_values('Start date').iterrows(),1):
        dt=lambda v:v.date() if hasattr(v,'date') and not str(v)=='NaT' else None
        out.append([i,excel_safe(r['Guest']),dt(r['Start date']),dt(r['End date']),float(r['Nights']),excel_safe(_room_listing_label(r)),float(r['Gross earnings']) if str(r['Gross earnings'])!='nan' else 0,float(r['Service fee']) if str(r['Service fee'])!='nan' else 0,float(r['Amount']) if str(r['Amount'])!='nan' else 0,excel_safe(r['Confirmation code'])])
    return out

def make_excel(villa,month,res,s,occ,expenses,payouts,approved):
    book=Workbook(); ws=book.active;ws.title='MONTHLY RECAP'
    ws.merge_cells('A1:J1');ws['A1']=f'{villa} | MONTHLY REPORT | {month}';ws['A1'].font=Font(size=15,bold=True,color='FFFFFF');ws['A1'].fill=PatternFill('solid',fgColor=BLUE);ws.row_dimensions[1].height=30
    for j,h in enumerate(COLUMNS,1):ws.cell(3,j,h)
    for i,row in enumerate(_rows(res),4):
        for j,value in enumerate(row,1):ws.cell(i,j,value)
    last=3+len(res);total=last+1
    ws.cell(total,2,'TOTAL');ws.cell(total,5,f'=SUM(E4:E{last})' if last>=4 else 0)
    for j in (7,8,9):ws.cell(total,j,f'=SUM({get_column_letter(j)}4:{get_column_letter(j)}{last})' if last>=4 else 0)
    p=total+3
    effective_pct = s['fee'] / (s['gross'] if s['fee'] and s['gross'] else s['amount'] if s['amount'] else 1)*100 if s['fee'] or s['gross'] or s['amount'] else 0
    for row in [('SUMMARY',None),('Total Publish Rate*',s['gross']),('Total OTA Commission',s['ota']),('Total Payout / Reservation Amount',s['amount']),('Occupancy',occ['occupancy_pct']/100),('Occupied Room Nights',occ['occupied']),('Available Room Nights',occ['capacity']),('MANAGEMENT & OWNER SETTLEMENT',None),(f"Management Fee ({s['currency']}, {effective_pct:.2f}% effective)",s['fee']),('Additional Expenses',s['expenses']),('Estimated Owner Balance',s['owner_estimate']),('Report Status','APPROVED' if approved else 'DRAFT - NOT APPROVED')]:
        ws.cell(p,2,row[0]);ws.cell(p,4,row[1]);p+=1
    ws.cell(p+1,2,'* Publish Rate uses Airbnb Gross earnings as available CSV proxy, not a separate published-rate field.')
    ws.cell(p+2,2,'Revenue uses CHECK-IN month. Occupancy counts actual nights in selected month (even for prior check-ins).')
    ws.cell(p+3,2,'Reservation Amount is not proof of bank settlement. Payout matching status is tracked separately.')
    widths=[8,26,16,16,11,54,22,22,23,24]
    for j,w in enumerate(widths,1):ws.column_dimensions[get_column_letter(j)].width=w
    ws.freeze_panes='C4';ws.auto_filter.ref=f'A3:J{max(3,last)}'
    for cell in ws[3]:cell.fill=PatternFill('solid',fgColor=BLUE);cell.font=Font(color='FFFFFF',bold=True)
    for row in ws.iter_rows(min_row=4,max_row=total):
        for c in row:
            if c.column in (3,4) and isinstance(c.value,date):c.number_format='dd mmm yyyy'
            if c.column in (7,8,9):c.number_format='#,##0.00;[Red](#,##0.00)'
    for c in ws[total]:c.fill=PatternFill('solid',fgColor='EAEFF7');c.font=Font(bold=True)
    for r in range(total+3,p):
        if ws.cell(r,4).value is None:
            for c in ws[r][:4]:c.fill=PatternFill('solid',fgColor=BLUE);c.font=Font(color='FFFFFF',bold=True)
        elif ws.cell(r,2).value=='Occupancy':ws.cell(r,4).number_format='0.00%'
        elif isinstance(ws.cell(r,4).value,(int,float)):ws.cell(r,4).number_format='#,##0.00'
    details=book.create_sheet('AIRBNB PAYMENT REPORT')
    payment_headers=['Payout Date','Arriving By','Reference Code','Transfer Detail','Currency','Paid Out','Reservation Codes','Matching Status']
    details.append(payment_headers)
    for pmt in payouts:
        details.append([pmt['date'].date() if hasattr(pmt['date'],'date') else '', '',excel_safe(pmt['reference']),excel_safe(pmt['details']),pmt['currency'],pmt['paid_out'],', '.join(pmt['codes']),'MANUAL VERIFIED' if pmt['codes'] else 'SUGGESTED' if pmt['suggestion'] else 'UNMATCHED'])
    for cell in details[1]:cell.fill=PatternFill('solid',fgColor=BLUE);cell.font=Font(color='FFFFFF',bold=True)
    for col,w in enumerate([17,19,38,54,12,20,34,20],1):details.column_dimensions[get_column_letter(col)].width=w
    details.freeze_panes='A2';details.auto_filter.ref=details.dimensions
    ex=book.create_sheet('ADDITIONAL EXPENSES')
    ex.append(['Category','Description','Currency','Amount'])
    for e in expenses:ex.append([excel_safe(e['category']),excel_safe(e['description']),e['currency'],e['amount']])
    for c in ex[1]:c.fill=PatternFill('solid',fgColor=BLUE);c.font=Font(bold=True,color='FFFFFF')
    for i,w in enumerate([24,55,15,22],1):ex.column_dimensions[get_column_letter(i)].width=w
    guide=book.create_sheet('GUIDE');notes=[['GROUNDHAUS - REPORT NOTES'],['Basis revenue','Tanggal check-in dalam bulan laporan'],['Occupancy','Malam ditempati dalam bulan laporan / (units x hari kalender)'],['Room tracking','Nama kamar/unit mengikuti mapping listing Airbnb ke villa + room/unit'],['Publish rate proxy','Gross earnings dari CSV Airbnb; mungkin tidak sama dengan harga publish owner'],['Payout / Amount','Nominal kolom Amount baris Reservation; bukan bukti transfer bank'],['OTA Commission','Service fee yang tertulis pada baris Reservation'],['Fee basis','Konfigurasi individual villa, tercatat pada aplikasi'],['Currencies','Angka settlement hanya mata uang villa; currency lain dikecualikan'],['Approval','Perubahan data/config/expense membuat approval lama tidak berlaku'],['Payout matching','Belum cocok dengan bank statement; bukan kepastian dana diterima']]
    for row in notes:guide.append(row)
    guide.column_dimensions['A'].width=25;guide.column_dimensions['B'].width=96
    for c in guide[1]:c.fill=PatternFill('solid',fgColor=BLUE);c.font=Font(bold=True,color='FFFFFF')
    b=io.BytesIO();book.save(b);return b.getvalue()

def make_pdf(villa,month,res,s,occ,expenses,payouts,approved):
    b=io.BytesIO();doc=SimpleDocTemplate(b,pagesize=landscape(A4),topMargin=15*mm,bottomMargin=15*mm,leftMargin=14*mm,rightMargin=14*mm)
    font_name=_unicode_font()
    styles=getSampleStyleSheet()
    normal=ParagraphStyle('GhUnicodeNormal',parent=styles['Normal'],fontName=font_name,fontSize=8,leading=12)
    title=ParagraphStyle('GhUnicodeTitle',parent=styles['Title'],fontName=font_name)
    h2=ParagraphStyle('GhUnicodeH2',parent=styles['Heading2'],fontName=font_name)
    h3=ParagraphStyle('GhUnicodeH3',parent=styles['Heading3'],fontName=font_name)
    rtl_normal=ParagraphStyle('GhUnicodeRTL',parent=normal,alignment=TA_RIGHT)
    def named_para(value):
        txt = str(value if value is not None else '')
        return Paragraph(_pdf_text(txt), rtl_normal if _RTL_RANGE.search(txt) else normal)

    story=[Paragraph('GROUNDHAUS  |  MONTHLY OWNER REPORT',title),Paragraph(_pdf_text(villa),h2),Paragraph(f'Period: {escape(month)}  |  Status: {"APPROVED" if approved else "DRAFT — NOT APPROVED"}',normal),Spacer(1,7*mm)]
    summaryrows=[['Metric','Value'],['Publish Rate*',money(s['gross'],s['currency'])],['OTA Commission',money(s['ota'],s['currency'])],['Reservation Amount',money(s['amount'],s['currency'])],['Occupancy',f"{occ['occupancy_pct']:.2f}% ({occ['occupied']}/{occ['capacity']} room nights)"],['Management Fee',money(s['fee'],s['currency'])],['Additional Expenses',money(s['expenses'],s['currency'])],['Estimated Owner Balance',money(s['owner_estimate'],s['currency'])]]
    st=Table(summaryrows,colWidths=[82*mm,77*mm],hAlign='LEFT');st.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1C4E89')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F1F4F8')]),('PADDING',(0,0),(-1,-1),6)]));story +=[st,Spacer(1,8*mm),Paragraph('RESERVATION DETAILS',h3)]
    headers=['Guest','Check in','Check out','Nights','Room / Listing','Gross*','OTA Fee','Amount']
    data=[headers]
    for r in _rows(res):data.append([named_para(str(r[1])),str(r[2] or ''),str(r[3] or ''),str(int(r[4])),named_para(str(r[5])[:80]),money(r[6],s['currency']),money(r[7],s['currency']),money(r[8],s['currency'])])
    if len(data)==1:data.append(['No reservation','','','','','','',''])
    t=Table(data,repeatRows=1,colWidths=[45*mm,25*mm,25*mm,14*mm,60*mm,30*mm,30*mm,30*mm]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1C4E89')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('VALIGN',(0,0),(-1,-1),'TOP'),('FONTSIZE',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F1F4F8')]),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5)]));story.append(t)
    story +=[Spacer(1,7*mm),Paragraph('ADDITIONAL EXPENSES',h3)]
    if expenses:
        for e in expenses:story.append(named_para(str(e['description'])+' — '+money(e['amount'],e['currency'])))
    else:story.append(Paragraph('None recorded.',normal))
    story +=[Spacer(1,5*mm),Paragraph('* Gross earnings is the available CSV proxy for publish rate. Revenue is based on check-in month; occupancy uses nights within the selected month. Reservation Amount is not proof of bank receipt. Payout matching requires verification.',normal)]
    doc.build(story);return b.getvalue()

def zip_all(data):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for villa,files in data.items():
            safe=re.sub('[^A-Za-z0-9_-]+','_',villa).strip('_') or 'villa'
            for extension,blob in files.items():z.writestr(f'{safe}.{extension}',blob)
    return b.getvalue()
