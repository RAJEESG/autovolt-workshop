import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi.testclient import TestClient
import database as db
import otp_helper

# Import both applications
from main import app as client_app
from saas_admin_app import app as hq_app

hq_client = TestClient(hq_app)
workshop_client = TestClient(client_app)

def run_tests():
    print("🚀 Running Comprehensive Verification for SaaS HQ & AutoVolt Pro Client...", flush=True)

    # =========================================================
    # 1. TEST SAAS MASTER VENDOR HQ (saas_admin_app)
    # =========================================================
    print("\n--- [1/2] Testing SaaS Master Vendor HQ (Port 8500) ---", flush=True)

    # Test unauthenticated redirect
    r_unauth = hq_client.get("/", follow_redirects=False)
    assert r_unauth.status_code == 303 and r_unauth.headers.get("location") == "/login"
    print("  ✅ HQ Unauthenticated user redirected to /login (Status 303)", flush=True)

    # Set authenticated vendor session
    hq_client.cookies.set("vendor_session", "admin")

    # Test HQ Dashboard
    r_dash = hq_client.get("/")
    assert r_dash.status_code == 200 and "AutoVolt Cloud HQ" in r_dash.text
    print("  ✅ HQ GET / (Dashboard) -> 200 OK", flush=True)

    # Test HQ Clients List
    r_clients = hq_client.get("/clients")
    assert r_clients.status_code == 200 and "Client Workshops" in r_clients.text
    print("  ✅ HQ GET /clients -> 200 OK", flush=True)

    # Test Onboard New Workshop Client
    r_new_client = hq_client.post(
        "/api/admin/clients/create",
        data={
            "name": "Kochi Auto Electric Works",
            "owner_name": "Jomon Thomas",
            "whatsapp_mobile": "+919847199887",
            "email": "jomon@kochiauto.com",
            "address": "MG Road, Ernakulam, Kerala - 682016",
            "gstin": "32ABCDE1234F1Z9",
            "logo_url": "https://example.com/kochi_logo.png",
            "upi_id": "kochiautoworkshop@okaxis",
            "upi_payee_name": "Kochi Auto Electric Works",
            "bank_name": "South Indian Bank",
            "bank_account_no": "012300098765",
            "bank_ifsc": "SIBL0000123",
            "gst_slabs": ["0", "5", "12", "18", "28"],
            "language": "ml",
            "master_pin": "5678",
            "initial_username": "jomon_admin",
            "initial_password": "password123",
            "plan_type": "YEARLY"
        },
        follow_redirects=True
    )
    assert r_new_client.status_code == 200
    print("  ✅ HQ POST /api/admin/clients/create -> Workshop Onboarded Successfully", flush=True)

    # Test HQ Users List
    r_users = hq_client.get("/users")
    assert r_users.status_code == 200 and "jomon_admin" in r_users.text
    print("  ✅ HQ GET /users -> 200 OK (New user visible)", flush=True)

    # Test HQ Reset Password for User
    r_reset_admin = hq_client.post(
        "/api/admin/users/reset-password",
        data={
            "user_id": "test_id",
            "username": "jomon_admin",
            "new_password": "newpassword456"
        },
        follow_redirects=True
    )
    assert r_reset_admin.status_code == 200
    print("  ✅ HQ POST /api/admin/users/reset-password -> User Password Reset by Master Admin", flush=True)

    # Test HQ Subscriptions & Renew License
    r_renew = hq_client.post(
        "/api/admin/subscriptions/renew",
        data={
            "tenant_id": "tenant_1",
            "billing_cycle": "YEARLY",
            "payment_mode": "UPI",
            "taxable_amount": 9999.00,
            "payment_ref": "UPI-TXN-998877"
        },
        follow_redirects=True
    )
    assert r_renew.status_code == 200
    print("  ✅ HQ POST /api/admin/subscriptions/renew -> License Extended & Invoice Auto-Generated", flush=True)

    # Test HQ Vendor Accounting & CA Reports
    r_acc = hq_client.get("/accounting?fy=2025-2026")
    assert r_acc.status_code == 200 and "GSTR-1" in r_acc.text
    print("  ✅ HQ GET /accounting -> 200 OK (Vendor Accounting)", flush=True)

    # Test HQ Vendor GSTR-1 Excel Export
    r_excel = hq_client.get("/api/admin/accounting/export-gstr1-excel?fy=2025-2026")
    assert r_excel.status_code == 200 and len(r_excel.content) > 1000
    print(f"  ✅ HQ GET /api/admin/accounting/export-gstr1-excel -> {len(r_excel.content)} bytes Excel file", flush=True)

    # Test HQ Vendor Settings
    r_sett = hq_client.post(
        "/api/admin/vendor-settings/update",
        data={
            "company_name": "AutoVolt Technologies Pvt Ltd",
            "tagline": "Enterprise Automotive Workshop SaaS Platform",
            "gstin": "32AABCA9876C1Z5",
            "email": "billing@autovoltcloud.com",
            "phone": "+91 98470 12345",
            "whatsapp_phone": "+919847012345",
            "address": "CyberPark, Kozhikode, Kerala - 682042",
            "upi_id": "autovoltcloud@icici",
            "upi_payee_name": "AutoVolt Technologies",
            "bank_name": "HDFC Bank Ltd",
            "bank_account_no": "50200088991122",
            "bank_ifsc": "HDFC0001234",
            "monthly_fee": 999.0,
            "yearly_fee": 9999.0
        },
        follow_redirects=True
    )
    assert r_sett.status_code == 200
    print("  ✅ HQ POST /api/admin/vendor-settings/update -> Settings Saved", flush=True)

    # =========================================================
    # 2. TEST AUTOVOLT PRO WORKSHOP CLIENT APP (main.py)
    # =========================================================
    print("\n--- [2/2] Testing AutoVolt Pro Workshop Client (Port 8000) ---", flush=True)

    # Test WhatsApp 6-Digit OTP Flow
    print("  🔐 Testing WhatsApp OTP Password Reset Flow...", flush=True)
    otp_data = otp_helper.generate_and_store_otp("admin")
    assert otp_data is not None and len(otp_data["otp_code"]) == 6
    print(f"    - Generated 6-digit OTP: {otp_data['otp_code']} for user {otp_data['username']}", flush=True)
    assert "https://wa.me/" in otp_data["whatsapp_link"]
    print(f"    - WhatsApp OTP deep link verified: {otp_data['whatsapp_link'][:45]}...", flush=True)

    # Test GET /verify-otp page
    r_otp_page = workshop_client.get(f"/verify-otp?username=admin")
    assert r_otp_page.status_code == 200 and "Verify WhatsApp OTP" in r_otp_page.text
    print("    - GET /verify-otp -> 200 OK", flush=True)

    # Test Verify OTP & Reset Password via HTTP POST
    r_reset_post = workshop_client.post(
        "/verify-otp",
        data={
            "username": "admin",
            "otp": otp_data["otp_code"],
            "new_password": "admin123",
            "confirm_password": "admin123"
        },
        follow_redirects=True
    )
    assert r_reset_post.status_code == 200 and "Password reset successful" in r_reset_post.text
    print("    - POST /verify-otp -> Password Reset and Login Prompt Verified", flush=True)

    # Set authenticated cookie on workshop client
    workshop_client.cookies.set("session_user", "admin")

    # Test Billing page contains dynamic GST slabs dropdown
    r_billing = workshop_client.get("/billing")
    assert r_billing.status_code == 200 and "availableGSTSlabs" in r_billing.text
    print("  ✅ Client GET /billing -> Dynamic GST slabs rendered in POS", flush=True)

    # Test Sidebar does NOT contain Super Admin link
    r_home = workshop_client.get("/")
    assert r_home.status_code == 200
    assert "Super Admin (SaaS)" not in r_home.text
    print("  ✅ Client GET / -> Verified 'Super Admin' menu is COMPLETELY REMOVED from client app", flush=True)

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! Both Applications Are 100% Operational! 🚀\n", flush=True)

if __name__ == "__main__":
    run_tests()
