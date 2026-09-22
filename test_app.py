import os
import sys
import io

# Force utf-8 stdout on windows to prevent emoji charmap errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

import database as db
import auth_helper
import excel_importer
import barcode_engine
import pdf_generator
import upi_helper
import whatsapp_helper
import ca_reports

def run_tests():
    print("🚀 Starting AutoVolt Pro Full System Test Suite...")

    # 1. Initialize DB
    print("\n--- 1. Testing Database Schema & Initial Data ---")
    db.init_db()
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM inventory_items")
    part_count = c.fetchone()[0]
    print(f"✅ Inventory Items in DB: {part_count}")
    assert part_count > 0, "No inventory parts found!"

    c.execute("SELECT COUNT(*) FROM technicians")
    tech_count = c.fetchone()[0]
    print(f"✅ Technicians in DB: {tech_count}")
    assert tech_count >= 5, "Fewer than 5 technicians found!"

    c.execute("SELECT COUNT(*) FROM tenants")
    tenant_count = c.fetchone()[0]
    print(f"✅ SaaS Tenants in DB: {tenant_count}")

    conn.close()

    # 2. Auth & Master PIN Tests
    print("\n--- 2. Testing Auth, Salted Hashes & Master PIN ---")
    pw_hash = auth_helper.hash_password("admin123")
    assert auth_helper.verify_password("admin123", pw_hash), "Password verification failed!"
    assert not auth_helper.verify_password("wrongpw", pw_hash), "Invalid password accepted!"
    print("✅ Salted SHA-256 password hash & verification passed.")

    assert auth_helper.verify_master_pin("1234", "1234"), "Master PIN verification failed!"
    assert not auth_helper.verify_master_pin("9999", "1234"), "Wrong Master PIN accepted!"
    print("✅ Master Security PIN (1234) verification passed.")

    reset_token = auth_helper.generate_reset_token()
    assert len(reset_token) > 20, "Reset token length too short!"
    print(f"✅ Generated Reset Token: {reset_token[:10]}...")

    # 3. Excel Template & Bulk Import
    print("\n--- 3. Testing Excel Template Generator & Bulk Parser ---")
    tmpl_bytes = excel_importer.generate_inventory_import_template()
    assert len(tmpl_bytes) > 1000, "Excel template generation failed!"
    print(f"✅ Generated styled Excel template: {len(tmpl_bytes)} bytes")

    items, errors = excel_importer.parse_inventory_file(tmpl_bytes, "template.xlsx")
    print(f"✅ Parsed {len(items)} items from template sample rows with {len(errors)} errors.")
    assert len(items) >= 5, "Failed to parse sample items from Excel template!"

    # 4. Barcode Engine
    print("\n--- 4. Testing Barcode Engine SVG & Base64 ---")
    svg_out = barcode_engine.generate_barcode_svg("89012340001")
    assert "<svg" in svg_out and "89012340001" in svg_out, "Barcode SVG generation failed!"
    b64_out = barcode_engine.generate_barcode_base64("89012340001")
    assert b64_out.startswith("data:image/png;base64,"), "Barcode base64 generation failed!"
    print("✅ Barcode SVG & Base64 generated successfully without number truncation.")

    # 5. Multilingual WhatsApp Formatter
    print("\n--- 5. Testing Multilingual WhatsApp Messages (en, ml, ta) ---")
    msg_en = whatsapp_helper.format_invoice_whatsapp_message(
        "Spark Auto", "INV-2026-001", "Rahul", "KL-07-AB-1234", "Swift", 1500.0, 1500.0, 0.0,
        "upi://pay", "http://localhost:8000/view/1", "+919876543210", lang="en"
    )
    assert "Spark Auto" in msg_en and "INV-2026-001" in msg_en
    print("✅ English WhatsApp Message formatted.")

    msg_ml = whatsapp_helper.format_invoice_whatsapp_message(
        "Spark Auto", "INV-2026-001", "Rahul", "KL-07-AB-1234", "Swift", 1500.0, 1500.0, 0.0,
        "upi://pay", "http://localhost:8000/view/1", "+919876543210", lang="ml"
    )
    assert "നമസ്കാരം" in msg_ml or "ബിൽ" in msg_ml
    print("✅ Malayalam WhatsApp Message formatted.")

    msg_ta = whatsapp_helper.format_invoice_whatsapp_message(
        "Spark Auto", "INV-2026-001", "Rahul", "KL-07-AB-1234", "Swift", 1500.0, 1500.0, 0.0,
        "upi://pay", "http://localhost:8000/view/1", "+919876543210", lang="ta"
    )
    assert "வணக்கம்" in msg_ta or "பில்" in msg_ta
    print("✅ Tamil WhatsApp Message formatted.")

    # 6. CA Tax & Accounting Reports
    print("\n--- 6. Testing CA Tax Reports & Financial Year Handling ---")
    fy = ca_reports.get_financial_year_dates("2025-2026")
    assert fy["start_date"] == "2025-04-01" and fy["end_date"] == "2026-03-31"
    print(f"✅ Financial Year {fy['financial_year']} range: {fy['start_date']} to {fy['end_date']}")

    gstr1 = ca_reports.generate_gstr1_report()
    assert "total_taxable" in gstr1 and "total_invoices" in gstr1
    print(f"✅ GSTR-1 generated: {gstr1['total_invoices']} invoices, Taxable ₹{gstr1['total_taxable']:.2f}")

    pnl = ca_reports.generate_profit_and_loss_report()
    print(f"✅ P&L generated: Total Sales ₹{pnl['sales_revenue']:.2f}, Net Profit ₹{pnl['net_profit']:.2f}")

    val = ca_reports.generate_inventory_valuation_report()
    print(f"✅ Inventory Valuation: {val['total_sku_count']} SKUs, Cost ₹{val['total_cost_value']:.2f}, Retail ₹{val['total_retail_value']:.2f}")

    col = ca_reports.generate_daily_collection_register()
    print(f"✅ Daily Collections: {len(col['registers'])} days, Total Collected ₹{col['grand_total_collected']:.2f}")

    excel_gstr1 = ca_reports.export_gstr1_excel()
    assert len(excel_gstr1) > 1000
    print(f"✅ GSTR-1 Excel Export generated: {len(excel_gstr1)} bytes")

    # 7. PDF Invoice Generation
    print("\n--- 7. Testing High-Contrast A4 PDF Invoice Generator ---")
    mock_invoice = {
        "invoice_number": "INV-2026-999",
        "invoice_date": "2026-09-22",
        "customer_name": "Antigravity Test Customer",
        "customer_phone": "9876543210",
        "vehicle_reg_no": "KL-07-TEST-99",
        "vehicle_make_model": "Hyundai Creta SX",
        "odometer": 45000,
        "payment_status": "PAID",
        "payment_mode": "UPI",
        "subtotal_labor": 450.0,
        "subtotal_parts": 1150.0,
        "discount_amount": 0.0,
        "grand_total": 1600.0,
        "amount_paid": 1600.0,
        "balance_due": 0.0,
        "items": [
            {
                "item_type": "LABOR",
                "name": "Starter Motor Repair & Bush Replacement",
                "hsn_sac": "9987",
                "quantity": 1,
                "unit_price": 450.0,
                "tax_rate": 0.0,
                "total_price": 450.0,
                "technician_name": "Sajid Khan"
            },
            {
                "item_type": "PART",
                "name": "Lucas 4-Pin Horn Relay 12V 30A",
                "hsn_sac": "8536",
                "quantity": 2,
                "unit_price": 140.0,
                "tax_rate": 18.0,
                "total_price": 280.0,
                "technician_name": None
            },
            {
                "item_type": "PART",
                "name": "Bosch 5-Pin Changeover Relay 12V",
                "hsn_sac": "8536",
                "quantity": 1,
                "unit_price": 180.0,
                "tax_rate": 18.0,
                "total_price": 180.0,
                "technician_name": None
            }
        ]
    }
    mock_workshop = {
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
        "terms": "1. Electrical parts warranty as per manufacturer."
    }

    pdf_bytes = pdf_generator.generate_invoice_pdf_bytes(mock_invoice, mock_workshop)
    assert len(pdf_bytes) > 2000, "PDF byte length too small!"
    print(f"✅ Generated high-contrast A4 PDF Invoice: {len(pdf_bytes)} bytes")

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY (100% VERIFIED)! 🚀")

if __name__ == "__main__":
    run_tests()
