import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from main import app
import database as db

client = TestClient(app)

def run_endpoint_tests():
    print("🌐 Running FastAPI Endpoints Integration Tests...")

    # 1. Test Login & Public Pages
    pages_to_test = [
        ("/", 200),
        ("/job-cards", 200),
        ("/billing", 200),
        ("/inventory", 200),
        ("/technicians", 200),
        ("/customers", 200),
        ("/bank-accounts", 200),
        ("/expenses", 200),
        ("/ca-reports", 200),
        ("/khata", 200),
        ("/settings", 200),
        ("/purchases", 200),
        ("/sales-returns", 200),
        ("/activity-logs", 200),
        ("/super-admin", 200),
        ("/login", 200),
        ("/forgot-password", 200),
        ("/reset-password", 200),
        ("/barcode-labels", 200),
    ]

    for path, expected_status in pages_to_test:
        response = client.get(path, follow_redirects=True)
        assert response.status_code == expected_status, f"Failed GET {path}: Got {response.status_code}"
        print(f"✅ GET {path:20} -> Status {response.status_code}")

    # 2. Test Barcode Scanner API
    r_scan = client.get("/api/inventory/scan/89012340001")
    assert r_scan.status_code == 200
    data = r_scan.json()
    assert "part_name" in data and data["barcode"] == "89012340001"
    print(f"✅ GET /api/inventory/scan/89012340001 -> {data['part_name']}")

    # 3. Test Barcode SVG API
    r_svg = client.get("/api/inventory/barcode-svg/89012340001")
    assert r_svg.status_code == 200
    assert "<svg" in r_svg.json()["svg"]
    print("✅ GET /api/inventory/barcode-svg/89012340001 -> Valid SVG returned")

    # 4. Test Excel Template API
    r_tmpl = client.get("/api/inventory/template/excel")
    assert r_tmpl.status_code == 200
    assert len(r_tmpl.content) > 1000
    print(f"✅ GET /api/inventory/template/excel -> {len(r_tmpl.content)} bytes .xlsx")

    # 5. Test Technician Toggle Leave API with dynamic ID
    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM technicians LIMIT 1")
    tech_row = c.fetchone()
    tech_id = tech_row["id"] if tech_row else "tech_1"
    conn.close()

    r_toggle = client.post(f"/api/technicians/{tech_id}/toggle-leave")
    assert r_toggle.status_code == 200
    print(f"✅ POST /api/technicians/{tech_id}/toggle-leave -> is_on_leave: {r_toggle.json()['is_on_leave']}")

    # 6. Test Job Card creation & WhatsApp Link
    r_create_job = client.post("/api/job-cards", data={
        "vehicle_reg_no": "KL-07-TEST-100",
        "vehicle_make_model": "Swift Diesel",
        "customer_name": "Test Customer",
        "customer_phone": "9847000000",
        "assigned_technician_id": tech_id,
        "odometer": 50000,
        "custom_complaint_notes": "Starter motor test"
    }, follow_redirects=False)
    assert r_create_job.status_code == 303
    print("✅ POST /api/job-cards -> Redirect 303 (Job Card created)")

    conn = db.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM job_cards ORDER BY created_at DESC LIMIT 1")
    job_id = c.fetchone()["id"]
    conn.close()

    r_job_wa = client.get(f"/api/job-cards/{job_id}/whatsapp-link")
    assert r_job_wa.status_code == 200
    assert "whatsapp_url" in r_job_wa.json()
    print("✅ GET /api/job-cards/{id}/whatsapp-link -> WhatsApp URL generated")

    # 7. Test POS Invoice creation, WhatsApp Link & PDF
    r_create_inv = client.post("/api/invoices", json={
        "customer_name": "Walk-in Rahul",
        "customer_phone": "9847012345",
        "vehicle_reg_no": "KL-07-AB-9999",
        "invoice_type": "COUNTER_SALE",
        "payment_mode": "UPI",
        "discount_amount": 0.0,
        "amount_paid": 280.0,
        "items": [
            {
                "item_type": "PART",
                "item_id": "item_1",
                "name": "Lucas 4-Pin Horn Relay 12V 30A",
                "barcode": "89012340001",
                "hsn_sac": "8536",
                "quantity": 2,
                "unit_price": 140.0,
                "tax_rate": 18.0
            }
        ]
    })
    assert r_create_inv.status_code == 200
    inv_data = r_create_inv.json()
    inv_id = inv_data["invoice_id"]
    print(f"✅ POST /api/invoices -> Created Invoice #{inv_data['invoice_number']}")

    r_inv_wa = client.get(f"/api/invoices/{inv_id}/whatsapp-link")
    assert r_inv_wa.status_code == 200
    print("✅ GET /api/invoices/{id}/whatsapp-link -> WhatsApp URL generated")

    r_pdf = client.get(f"/api/invoices/{inv_id}/pdf")
    assert r_pdf.status_code == 200
    assert len(r_pdf.content) > 2000
    print(f"✅ GET /api/invoices/{inv_id}/pdf -> {len(r_pdf.content)} bytes PDF")

    # 8. Test Installment Payment & Delete with Master PIN
    r_partial_inv = client.post("/api/invoices", json={
        "customer_name": "Credit Customer",
        "customer_phone": "9847055555",
        "vehicle_reg_no": "KL-07-DUE-111",
        "invoice_type": "COUNTER_SALE",
        "payment_mode": "KHATA_CREDIT",
        "amount_paid": 0.0,
        "items": [
            {
                "item_type": "PART",
                "item_id": "item_2",
                "name": "Bosch Relay",
                "barcode": "89012340002",
                "hsn_sac": "8536",
                "quantity": 1,
                "unit_price": 180.0,
                "tax_rate": 18.0
            }
        ]
    })
    due_inv_id = r_partial_inv.json()["invoice_id"]
    r_pay = client.post(f"/api/invoices/{due_inv_id}/record-payment", json={
        "amount": 180.0,
        "payment_mode": "UPI",
        "notes": "Full settlement via GPay"
    })
    assert r_pay.status_code == 200
    assert r_pay.json()["new_status"] == "PAID"
    print("✅ POST /api/invoices/{id}/record-payment -> Recorded settlement, status updated to PAID")

    r_del = client.post(f"/api/invoices/{due_inv_id}/delete", json={"pin": "1234"})
    assert r_del.status_code == 200
    assert r_del.json()["success"] is True
    print("✅ POST /api/invoices/{id}/delete -> Master PIN (1234) verified, invoice deleted")

    # 9. Test GSTR-1 Excel Export API
    r_gstr1_xl = client.get("/api/ca-reports/export-gstr1-excel")
    assert r_gstr1_xl.status_code == 200
    print(f"✅ GET /api/ca-reports/export-gstr1-excel -> {len(r_gstr1_xl.content)} bytes Excel")

    print("\n🎉 ALL API ENDPOINTS TESTED AND 100% OPERATIONAL! 🚀")

if __name__ == "__main__":
    run_endpoint_tests()
