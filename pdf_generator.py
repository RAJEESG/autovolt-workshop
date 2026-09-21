import io
import base64
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm

from upi_helper import generate_upi_link, generate_upi_qr_data_url

def generate_invoice_pdf_bytes(invoice: Dict[str, Any], workshop: Dict[str, Any]) -> bytes:
    """
    Generate professional A4 PDF Invoice for Auto Electrical Workshop
    Includes workshop branding, GSTIN, Bank A/c, UPI QR Code, Labor & Parts breakdown
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )
    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#475569'),
        fontName='Helvetica'
    )
    section_heading = ParagraphStyle(
        'SectionHead',
        parent=styles['Heading2'],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
        fontName='Helvetica-Bold'
    )
    bold_cell = ParagraphStyle(
        'BoldCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )
    normal_cell = ParagraphStyle(
        'NormCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#334155'),
        fontName='Helvetica'
    )
    right_cell = ParagraphStyle(
        'RightCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        alignment=2,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica'
    )
    right_bold = ParagraphStyle(
        'RightBold',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )

    story = []
    
    # --- HEADER SECTION ---
    header_data = [
        [
            Paragraph(f"<b>{workshop.get('name', 'SPARK AUTO ELECTRICALS')}</b><br/><font size=8 color='#64748b'>{workshop.get('subtitle', 'Auto Electrical & Electronic Service Center')}<br/>{workshop.get('address', '')}<br/>Phone: {workshop.get('phone', '')} | GSTIN: {workshop.get('gstin', 'N/A')}</font>", sub_style),
            Paragraph(f"<font size=16 color='#0284c7'><b>TAX INVOICE</b></font><br/><font size=9><b>Invoice #:</b> {invoice.get('invoice_number', '')}<br/><b>Date:</b> {invoice.get('invoice_date', '')}<br/><b>Job #:</b> {invoice.get('job_number') or 'Direct Sale'}</font>", sub_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[110 * mm, 70 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=8))

    # --- CUSTOMER & VEHICLE INFO BOX ---
    info_data = [
        [
            Paragraph("<b>CUSTOMER DETAILS</b>", section_heading),
            Paragraph("<b>VEHICLE DETAILS</b>", section_heading)
        ],
        [
            Paragraph(f"<b>Name:</b> {invoice.get('customer_name', 'Walk-in')}<br/><b>Phone:</b> {invoice.get('customer_phone', 'N/A')}<br/><b>Address:</b> {invoice.get('customer_address') or 'N/A'}<br/><b>GSTIN:</b> {invoice.get('customer_gstin') or 'Unregistered'}", normal_cell),
            Paragraph(f"<b>Reg No:</b> <font color='#0284c7'><b>{invoice.get('vehicle_reg_no') or 'Counter Sale'}</b></font><br/><b>Make & Model:</b> {invoice.get('vehicle_make_model') or 'General'}<br/><b>Odometer:</b> {invoice.get('odometer', 0):,} km", normal_cell)
        ]
    ]
    info_table = Table(info_data, colWidths=[90 * mm, 90 * mm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 4 * mm))

    # --- LINE ITEMS TABLE ---
    items_header = [
        Paragraph("#", bold_cell),
        Paragraph("Type", bold_cell),
        Paragraph("Item / Labor Description", bold_cell),
        Paragraph("HSN/SAC", bold_cell),
        Paragraph("Qty", bold_cell),
        Paragraph("Rate (₹)", bold_cell),
        Paragraph("Tax %", bold_cell),
        Paragraph("Amount (₹)", right_bold)
    ]
    
    table_rows = [items_header]
    items = invoice.get("items", [])
    for idx, itm in enumerate(items, 1):
        itype = "⚡ Labor" if itm.get("item_type") == "LABOR" else "📦 Part"
        table_rows.append([
            Paragraph(str(idx), normal_cell),
            Paragraph(itype, normal_cell),
            Paragraph(f"<b>{itm.get('name', '')}</b>", normal_cell),
            Paragraph(itm.get("hsn_sac") or "8536", normal_cell),
            Paragraph(str(itm.get("quantity", 1)), normal_cell),
            Paragraph(f"{itm.get('unit_price', 0):,.2f}", normal_cell),
            Paragraph(f"{itm.get('tax_rate', 0):.0f}%", normal_cell),
            Paragraph(f"{itm.get('total_price', 0):,.2f}", right_cell),
        ])

    items_table = Table(table_rows, colWidths=[8*mm, 16*mm, 68*mm, 18*mm, 12*mm, 20*mm, 14*mm, 24*mm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BOTTOMPADDING', (0,0), (-1,0), 5),
        ('TOPPADDING', (0,0), (-1,0), 5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('PADDING', (0,1), (-1,-1), 4),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # --- SUMMARY & BANK / UPI QR SECTION ---
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    grand_total = float(invoice.get("grand_total", 0.0))
    upi_link = invoice.get("upi_payment_link") or generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), grand_total, f"Inv_{invoice.get('invoice_number')}")
    
    # Summary Calculations Table
    summary_data = [
        [Paragraph("Labor Subtotal:", normal_cell), Paragraph(f"₹ {invoice.get('subtotal_labor', 0):,.2f}", right_cell)],
        [Paragraph("Spare Parts Subtotal:", normal_cell), Paragraph(f"₹ {invoice.get('subtotal_parts', 0):,.2f}", right_cell)],
    ]
    if invoice.get("tax_total", 0) > 0:
        summary_data.append([Paragraph(f"GST Tax Total:", normal_cell), Paragraph(f"₹ {invoice.get('tax_total', 0):,.2f}", right_cell)])
    if invoice.get("discount_amount", 0) > 0:
        summary_data.append([Paragraph("Discount:", normal_cell), Paragraph(f"- ₹ {invoice.get('discount_amount', 0):,.2f}", right_cell)])
        
    summary_data.append([Paragraph("<b>Grand Total:</b>", bold_cell), Paragraph(f"<b>₹ {grand_total:,.2f}</b>", right_bold)])
    summary_data.append([Paragraph("Amount Paid:", normal_cell), Paragraph(f"₹ {invoice.get('amount_paid', 0):,.2f}", right_cell)])
    
    balance = float(invoice.get("balance_due", 0.0))
    bal_color = "#dc2626" if balance > 0 else "#16a34a"
    summary_data.append([
        Paragraph(f"<font color='{bal_color}'><b>Balance Due:</b></font>", bold_cell),
        Paragraph(f"<font color='{bal_color}'><b>₹ {balance:,.2f}</b></font>", right_bold)
    ])
    
    summary_table = Table(summary_data, colWidths=[40 * mm, 38 * mm])
    summary_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#f1f5f9')),
        ('PADDING', (0,0), (-1,-1), 3.5),
        ('BACKGROUND', (0,-2), (-1,-2), colors.HexColor('#e0f2fe')),
    ]))

    # Bank & Payment Info Box
    bank_text = f"""<b>BANK & PAYMENT DETAILS</b><br/>
    <b>Bank:</b> {workshop.get('bank_name', 'State Bank of India')}<br/>
    <b>A/c No:</b> {workshop.get('bank_account_no', '39876543210')}<br/>
    <b>IFSC:</b> {workshop.get('bank_ifsc', 'SBIN0001234')}<br/>
    <b>Branch:</b> {workshop.get('bank_branch', 'Main')}<br/>
    <b>UPI ID:</b> <font color='#0284c7'><b>{vpa}</b></font><br/>
    <i>Scan UPI QR with GPay, PhonePe, or Paytm to Pay Instantly.</i>
    """
    bank_p = Paragraph(bank_text, normal_cell)

    footer_grid = [
        [bank_p, summary_table]
    ]
    footer_table = Table(footer_grid, colWidths=[102 * mm, 78 * mm])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(footer_table)
    story.append(Spacer(1, 5 * mm))

    # --- TERMS & SIGNATURE ---
    terms_text = f"<b>Terms & Conditions:</b><br/>" + (workshop.get("terms", "1. Electrical components warranty as per OEM. 2. Goods once fitted cannot be returned.")).replace("\n", "<br/>")
    terms_p = Paragraph(terms_text, ParagraphStyle('Terms', parent=styles['Normal'], fontSize=7.5, leading=10, textColor=colors.HexColor('#64748b')))
    
    sig_text = f"<br/><br/><br/><b>For {workshop.get('name', 'SPARK AUTO ELECTRICALS')}</b><br/><font size=7 color='#64748b'>Authorized Signatory</font>"
    sig_p = Paragraph(sig_text, ParagraphStyle('Sig', parent=styles['Normal'], fontSize=8.5, leading=11, alignment=2, textColor=colors.HexColor('#0f172a')))

    terms_table = Table([[terms_p, sig_p]], colWidths=[115 * mm, 65 * mm])
    terms_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('PADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(terms_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
