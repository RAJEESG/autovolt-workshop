import sys, os
sys.path.insert(0, r"C:\Users\Administrator\Desktop\Project_20260720_120758_194\auto_electric_workshop_manager")

import database as db
from main import app
from fastapi.testclient import TestClient

client = TestClient(app)
client.cookies.set("session_user", "admin")
client.cookies.set("session_last_active", "9999999999")

print("=== 1. Testing Dues Check Endpoint ===")
r = client.get("/api/customers/dues-check?phone=9847012345&vehicle_reg=KL07AB1234")
print("Status:", r.status_code, "Dues Data:", r.json())
assert r.status_code == 200

print("\n=== 2. Fetching Sample Job Card ===")
conn = db.get_db_connection()
cursor = conn.cursor()
cursor.execute("SELECT id, job_number FROM job_cards LIMIT 1")
job = cursor.fetchone()
conn.close()

if job:
    job_id = job["id"]
    job_no = job["job_number"]
    print(f"Testing with Job ID {job_id} (#{job_no})")

    print("\n=== 3. Testing Verify Edit PIN ===")
    r_pin = client.post(f"/api/job-cards/{job_id}/verify-edit-pin", json={"pin": "1234"})
    print("PIN Status:", r_pin.status_code, r_pin.json())
    assert r_pin.status_code == 200 and r_pin.json().get("success")

    print("\n=== 4. Testing Generate Proforma Estimate ===")
    r_prof = client.post(f"/api/job-cards/{job_id}/generate-proforma")
    print("Proforma Status:", r_prof.status_code, r_prof.json())
    assert r_prof.status_code == 200

    prof_id = r_prof.json()["proforma_id"]

    print("\n=== 5. Testing Proforma PDF Download ===")
    r_pdf = client.get(f"/api/proforma/{prof_id}/pdf")
    print("PDF Download Status:", r_pdf.status_code, "PDF Length:", len(r_pdf.content))
    assert r_pdf.status_code == 200 and len(r_pdf.content) > 500

    print("\n=== 6. Testing WhatsApp Work Complete Link ===")
    r_wa = client.get(f"/api/job-cards/{job_id}/whatsapp-proforma-link")
    print("WhatsApp Status:", r_wa.status_code, "URL:", r_wa.json().get("whatsapp_url")[:70])
    assert r_wa.status_code == 200

    print("\n=== 7. Testing Convert Proforma to Official Tax Invoice ===")
    r_conv = client.post(f"/api/job-cards/{job_id}/convert-proforma-to-invoice", data={"payment_mode": "UPI", "amount_paid": "500"})
    print("Convert Status:", r_conv.status_code, r_conv.json())
    assert r_conv.status_code == 200

    print("\n=== 8. Testing Regenerate Invoice (Preserving Inv #) ===")
    r_regen = client.post(f"/api/job-cards/{job_id}/regenerate-invoice")
    print("Regenerate Status:", r_regen.status_code, r_regen.json())
    assert r_regen.status_code == 200

print("\nALL WORKFLOW TESTS PASSED SUCCESSFULLY!")
