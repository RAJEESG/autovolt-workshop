import sys
import os
import requests
import json
from datetime import datetime

# Configure UTF-8 for Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Test all backend functions and models directly
import database as db
import barcode_engine
import upi_helper
import whatsapp_helper
import ca_reports
import pdf_generator

def run_tests():
    print("==================================================")
    print("🚀 AutoVolt Pro — System Verification Tests")
    print("==================================================")

    # 1. Test Database Initialization & Seeding
    db.init_db()
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM inventory_items")
    inv_count = cursor.fetchone()[0]
    print(f"✅ Inventory Items in DB: {inv_count}")
    assert inv_count >= 18, "Inventory items seeding failed"

    cursor.execute("SELECT COUNT(*) FROM technicians")
    tech_count = cursor.fetchone()[0]
    print(f"✅ Staff Technicians in DB: {tech_count}")
    assert tech_count >= 6, "Technician seeding failed"

    cursor.execute("SELECT COUNT(*) FROM bank_accounts")
    bank_count = cursor.fetchone()[0]
    print(f"✅ Bank Accounts in DB: {bank_count}")
    assert bank_count >= 3, "Bank accounts seeding failed"

    conn.close()

    # 2. Test Barcode Engine
    barcode_svg = barcode_engine.generate_barcode_svg("89012340001")
    print(f"✅ Barcode SVG Generated (Length: {len(barcode_svg)} bytes)")
    assert "<svg" in barcode_svg and "89012340001" in barcode_svg, "Barcode SVG generation failed"

    # 3. Test UPI Helper
    upi_uri = upi_helper.generate_upi_link("sparkautoworkshop@okaxis", "Spark Auto Electricals", 1850.50, "Inv_INV-2026-001")
    print(f"✅ UPI Intent Link: {upi_uri}")
    assert "upi://pay?" in upi_uri and "pa=sparkautoworkshop%40okaxis" in upi_uri, "UPI link format error"

    upi_qr = upi_helper.generate_upi_qr_data_url(upi_uri)
    print(f"✅ Dynamic UPI QR Generated (Data URL length: {len(upi_qr)} bytes)")
    assert "data:image/png;base64," in upi_qr or "http" in upi_qr, "UPI QR generation error"

    # 4. Test WhatsApp Formatter
    wa_msg = whatsapp_helper.format_invoice_whatsapp_message(
        workshop_name="SPARK AUTO ELECTRICALS",
        invoice_number="INV-2026-001",
        customer_name="Muhammed Nishad",
        vehicle_reg_no="KL-07-BX-4590",
        vehicle_make_model="Maruti Swift",
        grand_total=1490.0,
        amount_paid=1490.0,
        balance_due=0.0,
        upi_payment_link=upi_uri,
        public_view_url="http://localhost:8000/view/invoice/inv_1",
        workshop_phone="+91 98765 43210"
    )
    wa_url = whatsapp_helper.generate_wa_me_url("9847123456", wa_msg)
    print(f"✅ WhatsApp Direct Chat URL Generated: {wa_url[:80]}...")
    assert "https://wa.me/919847123456" in wa_url, "WhatsApp URL generation error"

    # 5. Test CA Audit Reports
    gstr1 = ca_reports.generate_gstr1_report()
    print(f"✅ CA GSTR-1 Sales Report Generated (Total Sales: ₹{gstr1['total_sales']})")
    assert "invoices" in gstr1 and "hsn_summary" in gstr1, "GSTR-1 report structure error"

    pnl = ca_reports.generate_profit_and_loss_report()
    print(f"✅ CA Profit & Loss Statement (Gross Rev: ₹{pnl['total_revenue']}, Net Profit: ₹{pnl['net_profit']})")
    assert "net_profit" in pnl, "P&L generation error"

    valuation = ca_reports.generate_inventory_valuation_report()
    print(f"✅ Closing Stock Valuation (Cost Value: ₹{valuation['total_cost_value']}, Retail Value: ₹{valuation['total_retail_value']})")
    assert valuation["total_cost_value"] > 0, "Inventory valuation error"

    excel_bytes = ca_reports.export_gstr1_excel()
    print(f"✅ CA GSTR-1 Excel File Generated: {len(excel_bytes)} bytes")
    assert len(excel_bytes) > 1000, "Excel export error"

    # 6. Test PDF Generator
    sample_invoice = {
        "invoice_number": "INV-2026-001",
        "invoice_date": "2026-09-21",
        "job_number": "JOB-2026-001",
        "customer_name": "Muhammed Nishad",
        "customer_phone": "+91 94471 23456",
        "vehicle_reg_no": "KL-07-BX-4590",
        "vehicle_make_model": "Maruti Swift DDiS",
        "odometer": 84200,
        "subtotal_labor": 650.0,
        "subtotal_parts": 700.0,
        "tax_total": 0.0,
        "discount_amount": 0.0,
        "grand_total": 1350.0,
        "amount_paid": 1350.0,
        "balance_due": 0.0,
        "items": [
            {"item_type": "LABOR", "name": "Starter Overhaul Labor", "hsn_sac": "9987", "quantity": 1, "unit_price": 450.0, "tax_rate": 0.0, "total_price": 450.0},
            {"item_type": "PART", "name": "Lucas 4-Pin Relay", "hsn_sac": "8536", "quantity": 1, "unit_price": 140.0, "tax_rate": 18.0, "total_price": 140.0},
        ]
    }
    sample_workshop = {
        "name": "SPARK AUTO ELECTRICALS",
        "subtitle": "Auto Electrical & Electronic Service Center",
        "phone": "+91 98765 43210",
        "email": "sparkautocare@gmail.com",
        "address": "Near Highway Junction, Ernakulam, Kerala - 682001",
        "gstin": "32AABCS1429B1Z8",
        "upi_id": "sparkautoworkshop@okaxis",
        "bank_name": "State Bank of India",
        "bank_account_no": "39876543210",
        "bank_ifsc": "SBIN0001234",
        "bank_branch": "Ernakulam Main",
        "terms": "1. Parts warranty as per OEM."
    }
    pdf_bytes = pdf_generator.generate_invoice_pdf_bytes(sample_invoice, sample_workshop)
    print(f"✅ PDF Invoice Generated: {len(pdf_bytes)} bytes")
    assert len(pdf_bytes) > 2000, "PDF generation failed"

    print("\n🎉 ALL 6 AUTOMATED VERIFICATION SUITES PASSED PERFECTLY!\n")

if __name__ == "__main__":
    run_tests()
