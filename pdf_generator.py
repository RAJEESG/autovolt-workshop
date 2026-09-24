import io
import base64
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm

from upi_helper import generate_upi_link, generate_upi_qr_data_url

def generate_invoice_pdf_bytes(invoice: Dict[str, Any], workshop: Dict[str, Any]) -> bytes:
    """
    Generate crisp, professional A4 PDF Tax Invoice with high-contrast visible headers,
    clear item breakdown, bank details, and dynamic UPI QR code.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )
    
    styles = getSampleStyleSheet()
    
    # Custom high-contrast styles
    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#334155'),
        fontName='Helvetica'
    )
    section_heading = ParagraphStyle(
        'SectionHead',
        parent=styles['Heading2'],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )
    header_cell_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )
    header_right_style = ParagraphStyle(
        'HeaderRight',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        alignment=2,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )
    normal_cell = ParagraphStyle(
        'NormCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#1e293b'),
        fontName='Helvetica'
    )
    bold_cell = ParagraphStyle(
        'BoldCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold'
    )
    right_cell = ParagraphStyle(
        'RightCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11.5,
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
    
    if invoice.get("payment_status") == "CANCELLED" or invoice.get("status") == "CANCELLED":
        cancel_p = Paragraph("<font size=11 color='#dc2626'><b>⚠️ THIS INVOICE IS CANCELLED — PARTS RESTOCKED (SALES RETURN) ⚠️</b></font>", ParagraphStyle('Canc', parent=styles['Normal'], alignment=1))
        story.append(cancel_p)
        story.append(Spacer(1, 2 * mm))
        
    # --- 1. WORKSHOP HEADER ---
    header_data = [
        [
            Paragraph(f"<font size=14 color='#0f172a'><b>{workshop.get('name', 'SPARK AUTO ELECTRICALS')}</b></font><br/><font size=8 color='#475569'>{workshop.get('subtitle', 'Auto Electrical & Electronic Service Center')}<br/>{workshop.get('address', '')}<br/>Phone: <b>{workshop.get('phone', '')}</b> | Email: {workshop.get('email', '')}<br/>GSTIN: <b>{workshop.get('gstin', 'N/A')}</b></font>", sub_style),
            Paragraph(f"<font size=15 color='#0284c7'><b>TAX INVOICE</b></font><br/><font size=9><b>Invoice #:</b> {invoice.get('invoice_number', '')}<br/><b>Date:</b> {invoice.get('invoice_date', '')}<br/><b>Job #:</b> {invoice.get('job_number') or 'Direct Counter'}</font>", sub_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[112 * mm, 70 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=6))

    # --- 2. CUSTOMER & VEHICLE INFO BOX ---
    info_data = [
        [
            Paragraph("<b>BILLED TO (CUSTOMER)</b>", section_heading),
            Paragraph("<b>VEHICLE DETAILS</b>", section_heading)
        ],
        [
            Paragraph(f"<b>Name:</b> {invoice.get('customer_name', 'Walk-in Customer')}<br/><b>Phone:</b> {invoice.get('customer_phone', 'N/A')}<br/><b>Address:</b> {invoice.get('customer_address') or 'N/A'}<br/><b>GSTIN:</b> {invoice.get('customer_gstin') or 'Unregistered / B2C'}", normal_cell),
            Paragraph(f"<b>Reg Number:</b> <font color='#0284c7'><b>{invoice.get('vehicle_reg_no') or 'Counter Sale'}</b></font><br/><b>Make & Model:</b> {invoice.get('vehicle_make_model') or 'General'}<br/><b>Odometer:</b> {invoice.get('odometer', 0):,} km", normal_cell)
        ]
    ]
    info_table = Table(info_data, colWidths=[91 * mm, 91 * mm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 4 * mm))

    # --- 3. LINE ITEMS TABLE (WITH HIGH CONTRAST VISIBLE HEADERS) ---
    items_header = [
        Paragraph("#", header_cell_style),
        Paragraph("Type", header_cell_style),
        Paragraph("Description / Service", header_cell_style),
        Paragraph("HSN/SAC", header_cell_style),
        Paragraph("Qty", header_cell_style),
        Paragraph("Rate (₹)", header_cell_style),
        Paragraph("Tax %", header_cell_style),
        Paragraph("Amount (₹)", header_right_style)
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

    items_table = Table(table_rows, colWidths=[8*mm, 18*mm, 66*mm, 18*mm, 12*mm, 20*mm, 15*mm, 25*mm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')), # Dark Navy Blue Background
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('TOPPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
        ('PADDING', (0,1), (-1,-1), 4),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4 * mm))

    # --- 4. CALCULATION & BANK / UPI QR SECTION ---
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    grand_total = float(invoice.get("grand_total", 0.0))
    balance_due = float(invoice.get("balance_due", 0.0))
    pay_amount = balance_due if balance_due > 0 else grand_total
    
    upi_link = invoice.get("upi_payment_link") or generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), pay_amount, f"Inv_{invoice.get('invoice_number')}")
    
    summary_data = [
        [Paragraph("Labor Subtotal:", normal_cell), Paragraph(f"₹ {invoice.get('subtotal_labor', 0):,.2f}", right_cell)],
        [Paragraph("Parts Subtotal:", normal_cell), Paragraph(f"₹ {invoice.get('subtotal_parts', 0):,.2f}", right_cell)],
    ]
    
    is_interstate = bool(invoice.get("is_interstate"))
    cgst = float(invoice.get("cgst_total") or 0.0)
    sgst = float(invoice.get("sgst_total") or 0.0)
    igst = float(invoice.get("igst_total") or 0.0)
    tax_total = float(invoice.get("tax_total") or (cgst + sgst + igst))
    
    if is_interstate or igst > 0:
        summary_data.append([Paragraph("IGST Total (Inter-State):", normal_cell), Paragraph(f"₹ {igst or tax_total:,.2f}", right_cell)])
    else:
        if cgst > 0 or sgst > 0:
            summary_data.append([Paragraph("CGST Total (Central):", normal_cell), Paragraph(f"₹ {cgst:,.2f}", right_cell)])
            summary_data.append([Paragraph("SGST Total (State):", normal_cell), Paragraph(f"₹ {sgst:,.2f}", right_cell)])
        elif tax_total > 0:
            half = round(tax_total / 2.0, 2)
            summary_data.append([Paragraph("CGST Total (Central):", normal_cell), Paragraph(f"₹ {half:,.2f}", right_cell)])
            summary_data.append([Paragraph("SGST Total (State):", normal_cell), Paragraph(f"₹ {tax_total - half:,.2f}", right_cell)])
            
    if invoice.get("discount_amount", 0) > 0:
        summary_data.append([Paragraph("Discount:", normal_cell), Paragraph(f"- ₹ {invoice.get('discount_amount', 0):,.2f}", right_cell)])
        
    summary_data.append([Paragraph("<b>Grand Total:</b>", bold_cell), Paragraph(f"<b>₹ {grand_total:,.2f}</b>", right_bold)])
    summary_data.append([Paragraph("Amount Paid:", normal_cell), Paragraph(f"₹ {invoice.get('amount_paid', 0):,.2f}", right_cell)])
    
    if invoice.get("payment_status") == "CANCELLED":
        summary_data.append([
            Paragraph("<font color='#dc2626'><b>Status:</b></font>", bold_cell),
            Paragraph("<font color='#dc2626'><b>CANCELLED / VOID</b></font>", right_bold)
        ])
    else:
        bal_color = "#dc2626" if balance_due > 0 else "#16a34a"
        summary_data.append([
            Paragraph(f"<font color='{bal_color}'><b>Balance Due:</b></font>", bold_cell),
            Paragraph(f"<font color='{bal_color}'><b>₹ {balance_due:,.2f}</b></font>", right_bold)
        ])
    
    summary_table = Table(summary_data, colWidths=[40 * mm, 38 * mm])
    summary_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#f1f5f9')),
        ('PADDING', (0,0), (-1,-1), 3.5),
        ('BACKGROUND', (0,-2), (-1,-2), colors.HexColor('#e0f2fe')),
    ]))

    # Bank Details Text
    bank_text = f"""<b>BANK & PAYMENT DETAILS FOR DIRECT SETTLEMENT</b><br/>
    <b>Bank:</b> {workshop.get('bank_name', 'State Bank of India')}<br/>
    <b>A/c No:</b> {workshop.get('bank_account_no', '39876543210')}<br/>
    <b>IFSC:</b> {workshop.get('bank_ifsc', 'SBIN0001234')} | <b>Branch:</b> {workshop.get('bank_branch', 'Main')}<br/>
    <b>UPI ID:</b> <font color='#0284c7'><b>{vpa}</b></font><br/>
    <i>Scan UPI QR with GPay, PhonePe, or Paytm to Pay Instantly.</i>
    """
    bank_p = Paragraph(bank_text, normal_cell)

    footer_grid = [
        [bank_p, summary_table]
    ]
    footer_table = Table(footer_grid, colWidths=[104 * mm, 78 * mm])
    footer_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(footer_table)
    story.append(Spacer(1, 4 * mm))

    # --- 5. TERMS & SIGNATURE ---
    terms_text = f"<b>Terms & Conditions:</b><br/>" + (workshop.get("terms", "1. Electrical parts warranty as per manufacturer policy.\n2. Goods once fitted cannot be returned.")).replace("\n", "<br/>")
    terms_p = Paragraph(terms_text, ParagraphStyle('Terms', parent=styles['Normal'], fontSize=7.5, leading=10, textColor=colors.HexColor('#64748b')))
    
    sig_text = f"<br/><br/><b>For {workshop.get('name', 'SPARK AUTO ELECTRICALS')}</b><br/><font size=7 color='#64748b'>Authorized Signatory</font>"
    sig_p = Paragraph(sig_text, ParagraphStyle('Sig', parent=styles['Normal'], fontSize=8.5, leading=11, alignment=2, textColor=colors.HexColor('#0f172a')))

    terms_table = Table([[terms_p, sig_p]], colWidths=[118 * mm, 64 * mm])
    terms_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('PADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(terms_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
