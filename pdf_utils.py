from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

from config import INVOICE_DIR, IMAGE_DIR
from database import get_setting
from services import money, n, payment_summary

TEXT = colors.HexColor('#1d1d1f')
MUTED = colors.HexColor('#6e6e73')
BLUE = colors.HexColor('#0071e3')
LINE = colors.HexColor('#d2d2d7')
SOFT_LINE = colors.HexColor('#eeeeef')
GREEN = colors.HexColor('#15803d')
LIGHT_BLUE = colors.HexColor('#f5faff')
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}


def _safe_name(value: Any) -> str:
    raw = str(value or 'file').strip() or 'file'
    return ''.join(ch if ch.isalnum() or ch in ('-', '_', ' ') else '_' for ch in raw).strip().replace(' ', '_')[:90]


def _styles():
    base = getSampleStyleSheet()
    return {
        'Company': ParagraphStyle('Company', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=22, leading=23, textColor=TEXT),
        'Title': ParagraphStyle('Title', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=16, leading=18, textColor=TEXT, alignment=TA_RIGHT, spaceAfter=1),
        'DocMeta': ParagraphStyle('DocMeta', parent=base['Normal'], fontName='Helvetica', fontSize=7.4, leading=9.2, textColor=TEXT, alignment=TA_RIGHT),
        'DocMetaBold': ParagraphStyle('DocMetaBold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=10.2, textColor=TEXT, alignment=TA_RIGHT),
        'Small': ParagraphStyle('Small', parent=base['Normal'], fontName='Helvetica', fontSize=8.1, leading=9.7, textColor=TEXT),
        'SmallBold': ParagraphStyle('SmallBold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=TEXT),
        'Muted': ParagraphStyle('Muted', parent=base['Normal'], fontName='Helvetica', fontSize=8, leading=10.5, textColor=MUTED),
        'Tiny': ParagraphStyle('Tiny', parent=base['Normal'], fontName='Helvetica', fontSize=6.9, leading=8.6, textColor=MUTED),
        'TinyBold': ParagraphStyle('TinyBold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=7.2, leading=8.8, textColor=MUTED),
        'Cell': ParagraphStyle('Cell', parent=base['Normal'], fontName='Helvetica', fontSize=8, leading=10.2, textColor=TEXT),
        'CellBold': ParagraphStyle('CellBold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8.3, leading=10.5, textColor=TEXT),
        'Right': ParagraphStyle('Right', parent=base['Normal'], fontName='Helvetica', fontSize=8, leading=10.2, textColor=TEXT, alignment=TA_RIGHT),
        'RightBold': ParagraphStyle('RightBold', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=10.5, textColor=TEXT, alignment=TA_RIGHT),
        'Total': ParagraphStyle('Total', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=14, leading=16, textColor=TEXT, alignment=TA_RIGHT),
        'CenterTiny': ParagraphStyle('CenterTiny', parent=base['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=8.5, textColor=MUTED, alignment=TA_CENTER),
    }


def _xml(value: Any) -> str:
    return escape(str(value or ''))


def _image_roots() -> List[Path]:
    roots = [IMAGE_DIR, IMAGE_DIR.parent]
    seen: List[Path] = []
    for root in roots:
        if root.exists() and root not in seen:
            seen.append(root)
    return seen


def _find_image(*names):
    wanted = [str(name).strip() for name in names if str(name or '').strip()]
    for root in _image_roots():
        for name in wanted:
            p = root / name
            if p.exists() and p.suffix.lower() in IMAGE_EXTS:
                return str(p)
    lowered = {name.lower(): name for name in wanted}
    for root in _image_roots():
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and p.name.lower() in lowered:
                return str(p)
    search_terms = [Path(name).stem.lower().replace('_', ' ').replace('-', ' ') for name in wanted]
    for root in _image_roots():
        for p in root.iterdir():
            if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            label = p.stem.lower().replace('_', ' ').replace('-', ' ')
            if search_terms and any(term and term in label for term in search_terms):
                return str(p)
    for root in _image_roots():
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and any(k in p.name.lower() for k in ['logo', 'brand', 'icon']):
                return str(p)
    return None


def _img(path, w, h, align='LEFT'):
    if not path:
        return ''
    try:
        iw, ih = ImageReader(path).getSize()
        scale = min(float(w) / max(iw, 1), float(h) / max(ih, 1))
        width, height = max(1, iw * scale), max(1, ih * scale)
        im = Image(path, width=width, height=height)
        im.hAlign = align
        return im
    except Exception:
        return ''


def _draw_watermark_on_canvas(canvas, alpha=0.04):
    path=_find_image('logo watermark.png','watermark.png','waretmark.png','logo.png')
    if not path:return
    canvas.saveState()
    try:
        if hasattr(canvas,'setFillAlpha'): canvas.setFillAlpha(alpha)
        size=96*mm; x=(A4[0]-size)/2; y=(A4[1]-size)/2
        canvas.drawImage(path,x,y,width=size,height=size,preserveAspectRatio=True,anchor='c',mask='auto')
    finally:
        canvas.restoreState()


class _WatermarkCanvas(pdf_canvas.Canvas):
    """Draw watermark after page content so white cards cannot hide it."""
    def showPage(self):
        _draw_watermark_on_canvas(self, alpha=0.035)
        super().showPage()


def _draw_watermark(canvas, doc):
    # Kept for compatibility if older code passes it as a page callback.
    # The current invoice builder uses _WatermarkCanvas so the watermark is
    # drawn at page end, above white table backgrounds, with very low opacity.
    _draw_watermark_on_canvas(canvas, alpha=0.025)


def _logo_block(styles, width=116*mm):
    logo = _img(_find_image('logo.png', 'logo.jpg', 'logo.jpeg', 'brand.png', 'icon.png', 'logo watermark.png'), 27*mm, 27*mm)
    name = get_setting('company_name', 'ICON MOBILE') or 'ICON MOBILE'
    addr = get_setting('company_address', 'Sri Lanka') or 'Sri Lanka'
    phone = get_setting('company_phone', '070 144 2299') or '070 144 2299'
    email = get_setting('company_email', '')
    contact_bits = [f"Contact Numbers: <b>{_xml(phone)}</b>"]
    if addr:
        contact_bits.append(_xml(addr))
    if email:
        contact_bits.append(_xml(email))
    details = Paragraph(
        f"<font size='16'><b>{_xml(str(name).upper())}</b></font><br/>"
        f"<font color='#6e6e73' size='7.4'>Premium Mobile Store &amp; Warranty Support</font><br/>"
        f"<font color='#1d1d1f' size='7.4'>{' &#8226; '.join(contact_bits)}</font>",
        styles['Small']
    )
    tbl = Table([[logo, details]], colWidths=[30*mm, width - 30*mm])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    return tbl


def _top_header(story, title, doc_no, date_text):
    styles = _styles()
    right = Table([
        [Paragraph(f"<b>{_xml(title)}</b>", styles['Title'])],
        [Paragraph("<font color='#6e6e73'>Official ICON MOBILE document</font>", styles['DocMeta'])],
        [Paragraph("<font color='#6e6e73'>DOCUMENT NO</font>", styles['DocMeta'])],
        [Paragraph(_xml(doc_no), styles['DocMetaBold'])],
        [Paragraph("<font color='#6e6e73'>DATE</font>", styles['DocMeta'])],
        [Paragraph(_xml(date_text or '-'), styles['DocMetaBold'])],
    ], colWidths=[64*mm])
    right.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 1),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
    ]))
    header = Table([[_logo_block(styles, 116*mm), right]], colWidths=[116*mm, 64*mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LINEBELOW', (0,0), (-1,-1), 0.8, LINE),
    ]))
    story.append(header)
    story.append(Spacer(1, 7))


def _info_card(title, rows, width):
    styles = _styles()
    data = [[Paragraph(f"<font color='#6e6e73'><b>{_xml(str(title).upper())}</b></font>", styles['TinyBold'])]]
    for k, v in rows:
        data.append([Paragraph(f"<font color='#6e6e73'>{_xml(k)}</font><br/><b>{_xml(v or '-')}</b>", styles['Small'])])
    tbl = Table(data, colWidths=[width])
    tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.45, LINE),
        ('LINEBELOW', (0,0), (-1,0), 0.45, SOFT_LINE),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('ROUNDEDCORNERS', [5]),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    return tbl


def _cards(story, left_title, left_rows, right_title, right_rows):
    tbl = Table([[_info_card(left_title, left_rows, 87*mm), _info_card(right_title, right_rows, 87*mm)]], colWidths=[90*mm, 90*mm])
    tbl.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0)]))
    story.append(tbl)
    story.append(Spacer(1, 7))


def _item_table(data, widths):
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        # No dark table heads; same clean white style from user's HTML invoice.
        ('BACKGROUND', (0,0), (-1,0), colors.white),
        ('TEXTCOLOR', (0,0), (-1,0), MUTED),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7.2),
        ('LINEBELOW', (0,0), (-1,0), 1.0, SOFT_LINE),
        ('LINEBELOW', (0,1), (-1,-1), 0.35, colors.HexColor('#f0f0f2')),
        ('LEFTPADDING', (0,0), (-1,-1), 4.8),
        ('RIGHTPADDING', (0,0), (-1,-1), 4.8),
        ('TOPPADDING', (0,0), (-1,-1), 5.2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5.2),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    return tbl


def _totals(rows, grand_key='Grand Total'):
    styles = _styles()
    data = []
    for k, v in rows:
        data.append([Paragraph(_xml(k), styles['RightBold'] if k == grand_key or 'Due' in k else styles['Right']), Paragraph(_xml(v), styles['Total'] if k == grand_key or k == 'Total Due' else styles['RightBold'])])
    tbl = Table(data, colWidths=[43*mm, 40*mm], hAlign='RIGHT')
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('LINEABOVE', (0,len(data)-1), (-1,len(data)-1), 1.1, TEXT),
        ('LINEBELOW', (0,0), (-1,-2), 0.25, SOFT_LINE),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 4.5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
    ]))
    return tbl


def _brand_tile(path, title, caption, styles, width):
    image = _img(path, 15*mm, 15*mm)
    tbl = Table([[
        image,
        Paragraph(f"<b>{_xml(title)}</b><br/><font color='#6e6e73'>{_xml(caption)}</font>", styles['Tiny'])
    ]], colWidths=[17*mm, max(28*mm, width - 17*mm)])
    tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.35, SOFT_LINE),
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('ROUNDEDCORNERS', [5]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    return tbl


def _brand_image_strip(story, styles):
    assets = [
        (_find_image('warranty.png', 'warranty.jpg', 'warranty.jpeg'), 'Warranty Care', 'Bring this invoice for warranty support.'),
        (_find_image('Google reviews.png', 'google_reviews.png', 'reviews.png'), 'Google Reviews', 'Scan and share your experience.'),
        (_find_image('Map Qr.png', 'map_qr.png', 'map.png', 'googlemap.png'), 'Find Our Store', 'Scan for map and directions.'),
    ]
    tiles = [(path, title, caption) for path, title, caption in assets if path]
    if not tiles:
        return
    per_width = (174*mm) / len(tiles)
    row = [_brand_tile(path, title, caption, styles, per_width) for path, title, caption in tiles]
    tbl = Table([row], colWidths=[per_width] * len(row))
    tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 7))


def _footer_block(story, include_terms=True):
    styles = _styles()
    _brand_image_strip(story, styles)
    if include_terms:
        terms = Table([[Paragraph(
            '<b>Terms of Sale and Warranty</b><br/>'
            '1. Warranty is valid only under normal operating conditions. '
            '2. Display, Face ID, Fingerprint ID, physical damage, dents, cracks, liquid damage, moisture, tampered stickers, unauthorized repair and misuse are not covered. '
            '3. Warranty claims require this invoice and must be made before the printed expiry date.',
            styles['Tiny']
        )]], colWidths=[174*mm])
        terms.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.35, SOFT_LINE),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fbfbfd')),
            ('ROUNDEDCORNERS', [5]),
            ('LEFTPADDING', (0,0), (-1,-1), 7),
            ('RIGHTPADDING', (0,0), (-1,-1), 7),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(terms)
        story.append(Spacer(1, 10))
    else:
        story.append(Spacer(1, 3))
    sign = Table([[Spacer(1,17*mm),Spacer(1,17*mm)],[Paragraph('Client Signature',styles['CenterTiny']),Paragraph('Authorized Signature',styles['CenterTiny'])]],colWidths=[86*mm,86*mm])
    sign.setStyle(TableStyle([('LINEABOVE',(0,1),(-1,1),0.55,LINE),('ALIGN',(0,1),(-1,1),'CENTER'),('TOPPADDING',(0,1),(-1,1),6),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
    story.append(sign)
    story.append(Spacer(1, 5))
    footer = get_setting('invoice_footer', 'Thank you for choosing ICON MOBILE. Please keep this invoice for warranty claims. System by Hich web Development 0714112113.').strip()
    credit = 'System by Hich web Development 0714112113'
    main_footer = footer
    if 'System by Hich web Development' in main_footer:
        main_footer = main_footer.split('System by Hich web Development', 1)[0].strip()
    main_footer = main_footer.rstrip(' .')
    if main_footer:
        story.append(Paragraph(_xml(main_footer) + '.', ParagraphStyle('Footer', parent=styles['Tiny'], alignment=TA_CENTER, textColor=TEXT)))
        story.append(Spacer(1, 2))
    story.append(Paragraph(_xml(credit), ParagraphStyle('DeveloperCredit', parent=styles['Tiny'], fontName='Courier', fontSize=6.7, leading=8, alignment=TA_CENTER, textColor=MUTED)))


def _payments_text(rows) -> str:
    return payment_summary(rows or [])


def build_retail_invoice_pdf(inv: Dict[str, Any]) -> str:
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    date = str(inv.get('created_at') or '')[:10]
    filename = f"{_safe_name(inv['invoice_no'])}_{_safe_name(inv.get('customer_name'))}_{_safe_name(date)}.pdf"
    path = INVOICE_DIR / filename
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=9*mm, bottomMargin=9*mm)
    styles = _styles(); story: List[Any] = []
    _top_header(story, 'INVOICE', inv['invoice_no'], date)
    _cards(
        story,
        'Bill To',
        [('Client Name', inv.get('customer_name')), ('WhatsApp', inv.get('customer_whatsapp') or inv.get('customer_phone')), ('Email', inv.get('customer_email') or 'Optional / Not given')],
        'Payment Method',
        [('Payment', _payments_text(inv.get('payments', []))), ('Status', inv.get('payment_status')), ('Balance', money(inv.get('balance')))],
    )
    data = [[Paragraph('DESCRIPTION', styles['TinyBold']), Paragraph('SERIAL / ID', styles['TinyBold']), Paragraph('WARRANTY', styles['TinyBold']), Paragraph('QTY', styles['TinyBold']), Paragraph('LINE TOTAL', styles['TinyBold'])]]
    for item in inv.get('items', []):
        warranty_lines = []
        if item.get('general_warranty') and item.get('general_warranty') != 'No Warranty':
            warranty_lines.append(f"General: <b>{_xml(item.get('general_warranty'))}</b><br/><font color='#6e6e73'>Expire: {_xml(item.get('general_warranty_expire') or '-')}</font>")
        if item.get('extended_warranty_name') or n(item.get('extended_warranty_price')):
            warranty_lines.append(f"Extended: <b>{_xml(item.get('extended_warranty_name') or 'Extended')}</b><br/><font color='#6e6e73'>Amount: {money(item.get('extended_warranty_price'))} | Expire: {_xml(item.get('extended_warranty_expire') or '-')}</font>")
        if item.get('warranty_note'):
            warranty_lines.append(f"<font color='#6e6e73'>Note: {_xml(item.get('warranty_note'))}</font>")
        name = _xml(item.get('product_name') or 'Item')
        if item.get('sku'):
            name += f"<br/><font color='#6e6e73'>SKU: {_xml(item.get('sku'))}</font>"
        if str(item.get('item_source') or '').lower() == 'direct sale':
            name += "<br/><font color='#0071e3'><b>DIRECT SALE ITEM</b></font>"
            if item.get('direct_supplier'):
                name += f"<br/><font color='#6e6e73'>Bought from: {_xml(item.get('direct_supplier'))}</font>"
            if item.get('buying_note'):
                name += f"<br/><font color='#6e6e73'>Buying note: {_xml(item.get('buying_note'))}</font>"
        if item.get('offer_applied'):
            name += f"<br/><font color='#0071e3'><b>OFFER APPLIED</b></font><br/><font color='#6e6e73'>Regular: {money(item.get('regular_price'))} | Offer: {money(item.get('unit_price'))} | You save: {money(item.get('offer_saving'))}</font>"
        data.append([
            Paragraph(name, styles['CellBold']),
            Paragraph(_xml(item.get('unit_code') or '-'), styles['Cell']),
            Paragraph('<br/>'.join(warranty_lines) or '<font color="#6e6e73">No warranty issued</font>', styles['Cell']),
            Paragraph(str(item.get('qty', 1)), styles['RightBold']),
            Paragraph(money(item.get('line_total')), styles['RightBold']),
        ])
    story.append(_item_table(data, [54*mm, 36*mm, 55*mm, 11*mm, 25*mm]))
    story.append(Spacer(1, 7))
    total_rows=[['Base Subtotal',money(inv.get('subtotal'))]]
    offer_saving=sum(n(item.get('offer_saving')) for item in inv.get('items',[]))
    if offer_saving: total_rows.append(['Offer Savings',money(offer_saving)])
    if n(inv.get('extended_warranty_total')): total_rows.append(['Ext. Warranty',money(inv.get('extended_warranty_total'))])
    if n(inv.get('discount')): total_rows.append(['Discount',money(inv.get('discount'))])
    total_rows += [['Paid',money(inv.get('paid_total'))],['Balance',money(inv.get('balance'))],['Grand Total',money(inv.get('grand_total'))]]
    story.append(_totals(total_rows))
    story.append(Spacer(1, 7))
    _footer_block(story, include_terms=True)
    doc.build(story, canvasmaker=_WatermarkCanvas)
    return str(path)


def build_wholesale_invoice_pdf(inv: Dict[str, Any]) -> str:
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    date = str(inv.get('created_at') or '')[:10]
    path = INVOICE_DIR / f"{_safe_name(inv['invoice_no'])}_{_safe_name(inv.get('shop_name'))}_{_safe_name(date)}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=12*mm, leftMargin=12*mm, topMargin=9*mm, bottomMargin=9*mm)
    styles = _styles(); story=[]
    _top_header(story, 'WHOLESALE ISSUE BILL', inv['invoice_no'], date)
    shop = inv.get('shop') or {}
    _cards(story, 'Partner Shop', [('Shop', shop.get('name') or inv.get('shop_name')), ('Contact', shop.get('contact_person')), ('WhatsApp', shop.get('whatsapp') or shop.get('phone'))], 'Payment', [('Initial Payment', _payments_text(inv.get('initial_payments', []))), ('Status', inv.get('payment_status')), ('Due', money(inv.get('balance')))])
    data = [[Paragraph('ITEM', styles['TinyBold']), Paragraph('UNIT / IMEI', styles['TinyBold']), Paragraph('QTY', styles['TinyBold']), Paragraph('SELLING PRICE', styles['TinyBold']), Paragraph('TOTAL', styles['TinyBold'])]]
    for item in inv.get('items', []):
        data.append([Paragraph(_xml(item.get('product_name') or 'Item'), styles['CellBold']), Paragraph(_xml(item.get('unit_code') or '-'), styles['Cell']), Paragraph(str(item.get('qty', 1)), styles['RightBold']), Paragraph(money(item.get('selling_price')), styles['Right']), Paragraph(money(item.get('line_total')), styles['RightBold'])])
    story.append(_item_table(data, [70*mm, 38*mm, 15*mm, 30*mm, 28*mm]))
    story.append(Spacer(1,10))
    total_rows = [['Subtotal', money(inv.get('subtotal'))]]
    if n(inv.get('discount')): total_rows.append(['Discount', money(inv.get('discount'))])
    total_rows += [['Paid', money(inv.get('paid_total'))], ['Due Amount', money(inv.get('balance'))], ['Grand Total', money(inv.get('grand_total'))]]
    story.append(_totals(total_rows, grand_key='Grand Total'))
    story.append(Spacer(1,8)); story.append(Paragraph('<b>Partner Account Note:</b> Due balances are tracked under the partner profile. Future payments are allocated to oldest unpaid bills first unless a direct bill is selected.', styles['Tiny']))
    story.append(Spacer(1,14)); _footer_block(story, include_terms=False)
    doc.build(story, canvasmaker=_WatermarkCanvas)
    return str(path)


def build_shop_statement_pdf(profile: Dict[str, Any]) -> str:
    shop = profile['shop']
    name = _safe_name(shop.get('name') or 'SHOP')
    path = INVOICE_DIR / f"STATEMENT_{name}_{shop.get('id','')}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=14*mm, leftMargin=14*mm, topMargin=12*mm, bottomMargin=11*mm)
    styles = _styles(); story=[]
    _top_header(story, 'PARTNER STATEMENT', shop.get('name') or 'Shop', str(profile.get('generated_at') or ''))
    _cards(story, 'Shop Profile', [('Shop', shop.get('name')), ('Contact', shop.get('contact_person')), ('WhatsApp', shop.get('whatsapp') or shop.get('phone'))], 'Account Summary', [('Total Issued', money(profile.get('total_issued'))), ('Total Paid', money(profile.get('total_paid'))), ('Total Due', money(profile.get('balance')))])
    story.append(Paragraph('Due Items', styles['SmallBold']))
    data = [[Paragraph('INVOICE', styles['TinyBold']), Paragraph('ITEM', styles['TinyBold']), Paragraph('UNIT', styles['TinyBold']), Paragraph('QTY', styles['TinyBold']), Paragraph('LINE', styles['TinyBold']), Paragraph('INVOICE DUE', styles['TinyBold'])]]
    for item in profile.get('due_items', [])[:130]:
        data.append([Paragraph(_xml(item.get('invoice_no') or ''), styles['Cell']), Paragraph(_xml(item.get('product_name') or ''), styles['Cell']), Paragraph(_xml(item.get('unit_code') or '-'), styles['Cell']), Paragraph(str(item.get('qty')), styles['Right']), Paragraph(money(item.get('line_total')), styles['Right']), Paragraph(money(item.get('balance')), styles['RightBold'])])
    if profile.get('due_items'): story.append(_item_table(data,[28*mm,58*mm,27*mm,13*mm,27*mm,28*mm]))
    else: story.append(Paragraph('Account clear — no outstanding items or bills.',styles['SmallBold']))
    story.append(Spacer(1,8))
    story.append(Paragraph('Outstanding Bill Progress', styles['SmallBold']))
    bills = [[Paragraph('INVOICE',styles['TinyBold']),Paragraph('DATE',styles['TinyBold']),Paragraph('ITEMS',styles['TinyBold']),Paragraph('TOTAL',styles['TinyBold']),Paragraph('PAID',styles['TinyBold']),Paragraph('DUE',styles['TinyBold']),Paragraph('PROGRESS',styles['TinyBold'])]]
    for inv in profile.get('outstanding_invoices',[])[:100]:
        bills.append([Paragraph(_xml(inv.get('invoice_no') or ''),styles['Cell']),Paragraph(_xml(str(inv.get('created_at') or '')[:10]),styles['Cell']),Paragraph(str(inv.get('total_qty') or 0),styles['Right']),Paragraph(money(inv.get('grand_total')),styles['Right']),Paragraph(money(inv.get('paid_total')),styles['Right']),Paragraph(money(inv.get('balance')),styles['RightBold']),Paragraph(f"{n(inv.get('paid_percent')):.1f}%",styles['RightBold'])])
    if profile.get('outstanding_invoices'): story.append(_item_table(bills,[29*mm,24*mm,14*mm,29*mm,27*mm,27*mm,25*mm]))
    else: story.append(Paragraph('No active due bills. Settled bills are archived below.',styles['Muted']))
    story.append(Spacer(1,8))
    story.append(Paragraph('All Paid Details / Settled Bills',styles['SmallBold']))
    settled=[[Paragraph('INVOICE',styles['TinyBold']),Paragraph('DATE',styles['TinyBold']),Paragraph('ITEMS',styles['TinyBold']),Paragraph('TOTAL',styles['TinyBold']),Paragraph('PAID',styles['TinyBold']),Paragraph('SETTLED',styles['TinyBold'])]]
    for inv in profile.get('settled_invoices',[])[:150]:
        settled.append([Paragraph(_xml(inv.get('invoice_no') or ''),styles['Cell']),Paragraph(_xml(str(inv.get('created_at') or '')[:10]),styles['Cell']),Paragraph(str(inv.get('total_qty') or 0),styles['Right']),Paragraph(money(inv.get('grand_total')),styles['Right']),Paragraph(money(inv.get('paid_total')),styles['RightBold']),Paragraph(_xml(str(inv.get('last_payment_date') or inv.get('updated_at') or '')[:10]),styles['Cell'])])
    if profile.get('settled_invoices'): story.append(_item_table(settled,[31*mm,27*mm,18*mm,32*mm,32*mm,35*mm]))
    else: story.append(Paragraph('No settled bills yet.',styles['Muted']))
    story.append(Spacer(1,8))
    story.append(Paragraph('All Dated Payment Transactions', styles['SmallBold']))
    payments = [[Paragraph('PAYMENT',styles['TinyBold']),Paragraph('DATE',styles['TinyBold']),Paragraph('METHOD / REF',styles['TinyBold']),Paragraph('AMOUNT',styles['TinyBold']),Paragraph('ALLOCATIONS',styles['TinyBold'])]]
    for payment in profile.get('payment_log', profile.get('payments',[]))[:120]:
        allocation = payment.get('allocations')
        if not isinstance(allocation, str):
            allocation='; '.join(f"{a.get('invoice_no')} {money(a.get('applied'))}" for a in payment.get('allocations',[]))
        payments.append([Paragraph(_xml(payment.get('payment_no') or ''),styles['Cell']),Paragraph(_xml(str(payment.get('created_at') or '')),styles['Cell']),Paragraph(_xml(payment.get('method_detail') or payment.get('method_summary') or ''),styles['Cell']),Paragraph(money(payment.get('amount')),styles['RightBold']),Paragraph(_xml(allocation or '-'),styles['Cell'])])
    story.append(_item_table(payments,[29*mm,31*mm,36*mm,25*mm,54*mm]))
    story.append(Spacer(1,8))
    story.append(_totals([['Total Issued', money(profile.get('total_issued'))], ['Total Paid', money(profile.get('total_paid'))], ['Total Due', money(profile.get('balance'))]], grand_key='Total Due'))
    doc.build(story, canvasmaker=_WatermarkCanvas)
    return str(path)
