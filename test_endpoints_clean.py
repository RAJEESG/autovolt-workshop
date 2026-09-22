import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
from main import app
import database as db

client = TestClient(app)

def run_tests():
    print("🌐 Testing All Application Pages & Endpoints...", flush=True)

    # Test Unauthenticated Redirect
    r_unauth = client.get("/", follow_redirects=False)
    assert r_unauth.status_code == 303 and r_unauth.headers.get("location") == "/login"
    print("  ✅ Unauthenticated user redirected to /login (Status 303)", flush=True)

    # Set authenticated cookie
    client.cookies.set("session_user", "admin")

    endpoints = [
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

    for path, expected in endpoints:
        r = client.get(path, follow_redirects=True)
        assert r.status_code == expected, f"Failed {path}: {r.status_code}"
        print(f"  ✅ GET {path:22} -> Status {r.status_code}", flush=True)

    # Test Barcode scan
    r_scan = client.get("/api/inventory/scan/89012340001")
    assert r_scan.status_code == 200
    print(f"  ✅ GET /api/inventory/scan/89012340001 -> {r_scan.json()['part_name']}", flush=True)

    # Test Barcode SVG
    r_svg = client.get("/api/inventory/barcode-svg/89012340001")
    assert r_svg.status_code == 200 and "<svg" in r_svg.json()["svg"]
    print(f"  ✅ GET /api/inventory/barcode-svg -> SVG OK", flush=True)

    # Test Template Excel
    r_tmpl = client.get("/api/inventory/template/excel")
    assert r_tmpl.status_code == 200 and len(r_tmpl.content) > 1000
    print(f"  ✅ GET /api/inventory/template/excel -> {len(r_tmpl.content)} bytes", flush=True)

    # Test Technician Leave Toggle
    r_leave = client.post("/api/technicians/tech_1/toggle-leave")
    assert r_leave.status_code == 200
    print(f"  ✅ POST /api/technicians/tech_1/toggle-leave -> is_on_leave: {r_leave.json()['is_on_leave']}", flush=True)

    # Test Create Job Card
    r_job = client.post("/api/job-cards", data={
        "vehicle_reg_no": "KL-07-TEST-999",
        "vehicle_make_model": "Swift Diesel",
        "customer_name": "Test Customer",
        "customer_phone": "9847000000",
        "assigned_technician_id": "tech_1",
        "odometer": 50000,
        "custom_complaint_notes": "Starter motor test"
    }, follow_redirects=False)
    assert r_job.status_code == 303
    print(f"  ✅ POST /api/job-cards -> 303 Redirect", flush=True)

    # Test Create POS Invoice
    r_inv = client.post("/api/invoices", json={
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
    assert r_inv.status_code == 200
    inv_id = r_inv.json()["invoice_id"]
    print(f"  ✅ POST /api/invoices -> Created Invoice #{r_inv.json()['invoice_number']}", flush=True)

    # Test PDF Invoice
    r_pdf = client.get(f"/api/invoices/{inv_id}/pdf")
    assert r_pdf.status_code == 200 and len(r_pdf.content) > 2000
    print(f"  ✅ GET /api/invoices/{inv_id}/pdf -> {len(r_pdf.content)} bytes", flush=True)

    # Test WhatsApp Link
    r_wa = client.get(f"/api/invoices/{inv_id}/whatsapp-link")
    assert r_wa.status_code == 200 and "whatsapp_url" in r_wa.json()
    print(f"  ✅ GET /api/invoices/{inv_id}/whatsapp-link -> WhatsApp Link OK", flush=True)

    # Test GSTR1 Excel Export
    r_gstr1 = client.get("/api/ca-reports/export-gstr1-excel")
    assert r_gstr1.status_code == 200 and len(r_gstr1.content) > 1000
    print(f"  ✅ GET /api/ca-reports/export-gstr1-excel -> {len(r_gstr1.content)} bytes", flush=True)

    print("\n🎉 ALL TESTS COMPLETED SUCCESSFULLY (100% OPERATIONAL)! 🚀", flush=True)

if __name__ == "__main__":
    run_tests()
