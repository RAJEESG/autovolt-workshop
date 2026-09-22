import os
import sys
import json
import uuid
import io
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Form, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

import database as db
from auth_helper import hash_password, verify_password

load_dotenv()

# Initialize DB
db.init_db()

app = FastAPI(
    title="AutoVolt Cloud HQ — SaaS Master Vendor Platform",
    description="Dedicated Standalone Master Management Application for AutoVolt Pro SaaS Platform",
    version="2.0.0"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# =========================================================
# 🔐 AUTHENTICATION MIDDLEWARE FOR SAAS MASTER VENDOR PORTAL
# =========================================================
@app.middleware("http")
async def vendor_auth_middleware(request: Request, call_next):
    path = request.url.path
    exempt_prefixes = ["/static", "/login", "/logout"]
    is_exempt = any(path.startswith(p) for p in exempt_prefixes)
    
    session_user = request.cookies.get("vendor_session")
    if not is_exempt and not session_user and request.method == "GET":
        return RedirectResponse(url="/login", status_code=303)
        
    if path == "/login" and session_user and request.method == "GET":
        return RedirectResponse(url="/", status_code=303)
        
    response = await call_next(request)
    return response

# =========================================================
# 🔑 LOGIN & LOGOUT
# =========================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="admin_hq/login.html",
        context={"error": error}
    )

@app.post("/login")
async def handle_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND status = 'ACTIVE'", (username.strip(),))
    user = cursor.fetchone()

    if not user or not verify_password(password.strip(), user["password_hash"]):
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="admin_hq/login.html",
            context={"error": "Invalid Master Admin credentials. Please try again."}
        )

    # Allow superadmin or admin
    if user["role"] not in ("SUPER_ADMIN", "ADMIN"):
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="admin_hq/login.html",
            context={"error": "Access Denied: Only SaaS Master Vendor Administrators can enter."}
        )

    db.log_audit("VENDOR_HQ_LOGIN", "users", user["id"], f"Master admin {user['username']} logged into HQ", cursor=cursor)
    conn.commit()
    conn.close()

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="vendor_session", value=user["username"], max_age=86400 * 30, httponly=True)
    return response

@app.get("/logout")
async def handle_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("vendor_session")
    return response

# =========================================================
# 📊 SAAS MASTER DASHBOARD OVERVIEW
# =========================================================
@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tenants ORDER BY created_at DESC")
    tenants = [dict(row) for row in cursor.fetchall()]

    today = datetime.now().date()
    today_str = today.strftime("%Y-%m-%d")
    thirty_days_later = (today + timedelta(days=30)).strftime("%Y-%m-%d")

    active_tenants = 0
    expired_tenants = 0
    renewals_due_count = 0

    for t in tenants:
        exp_date_str = t.get("subscription_end_date", "")
        if exp_date_str:
            try:
                exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                days_left = (exp_date - today).days
                t["is_active"] = (t.get("status") == "ACTIVE") and (days_left >= 0)
                if days_left < 0:
                    t["days_left_text"] = f"Expired {abs(days_left)} days ago"
                elif days_left == 0:
                    t["days_left_text"] = "Expires today!"
                else:
                    t["days_left_text"] = f"{days_left} days remaining"

                if 0 <= days_left <= 30:
                    renewals_due_count += 1
            except Exception:
                t["is_active"] = (t.get("status") == "ACTIVE")
                t["days_left_text"] = "Active"
        else:
            t["is_active"] = (t.get("status") == "ACTIVE")
            t["days_left_text"] = "No expiry date"

        if t["is_active"]:
            active_tenants += 1
        else:
            expired_tenants += 1

    # Financial Stats from SaaS Vendor Invoices
    cursor.execute("SELECT COALESCE(SUM(total_amount), 0), COUNT(*) FROM saas_vendor_invoices WHERE payment_status = 'PAID'")
    rev_row = cursor.fetchone()
    total_revenue = rev_row[0]

    # Calculate MRR estimate
    cursor.execute("SELECT plan_name, billing_cycle, price_paid FROM subscriptions WHERE is_active = 1")
    subs = cursor.fetchall()
    mrr = 0.0
    for s in subs:
        price = s["price_paid"] or 0.0
        if s["billing_cycle"] == "YEARLY":
            mrr += (price / 12.0)
        else:
            mrr += price

    cursor.execute("SELECT * FROM saas_vendor_invoices ORDER BY created_at DESC LIMIT 6")
    recent_invoices = [dict(row) for row in cursor.fetchall()]

    conn.close()

    stats = {
        "total_tenants": len(tenants),
        "active_tenants": active_tenants,
        "expired_tenants": expired_tenants,
        "renewals_due_count": renewals_due_count,
        "total_revenue": total_revenue,
        "mrr": mrr
    }

    return templates.TemplateResponse(
        request=request,
        name="admin_hq/dashboard.html",
        context={
            "active_page": "dashboard",
            "stats": stats,
            "tenants": tenants[:6],
            "recent_invoices": recent_invoices,
            "total_tenants": len(tenants)
        }
    )

# =========================================================
# 🏢 CLIENT WORKSHOPS & MULTI-TENANT CONFIGURATION
# =========================================================
@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request, msg: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tenants ORDER BY created_at DESC")
    tenants = [dict(row) for row in cursor.fetchall()]

    today = datetime.now().date()
    for t in tenants:
        exp_str = t.get("subscription_end_date", "")
        if exp_str:
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                t["is_active"] = (t.get("status") == "ACTIVE") and (exp_date >= today)
            except Exception:
                t["is_active"] = (t.get("status") == "ACTIVE")
        else:
            t["is_active"] = (t.get("status") == "ACTIVE")

        # Parse GST Slabs JSON
        try:
            t["gst_slabs_list"] = json.loads(t.get("gst_slabs") or '["0", "5", "12", "18", "28"]')
        except Exception:
            t["gst_slabs_list"] = ["0", "5", "12", "18", "28"]

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_hq/clients.html",
        context={
            "active_page": "clients",
            "tenants": tenants,
            "msg": msg,
            "total_tenants": len(tenants)
        }
    )

@app.post("/api/admin/clients/create")
async def create_client_workshop(
    name: str = Form(...),
    owner_name: str = Form(...),
    whatsapp_mobile: str = Form(...),
    email: Optional[str] = Form(None),
    address: str = Form(...),
    gstin: Optional[str] = Form(None),
    logo_url: Optional[str] = Form(None),
    upi_id: str = Form(...),
    upi_payee_name: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account_no: Optional[str] = Form(None),
    bank_ifsc: Optional[str] = Form(None),
    gst_slabs: List[str] = Form(...),
    language: str = Form("en"),
    master_pin: str = Form("1234"),
    initial_username: str = Form(...),
    initial_password: str = Form(...),
    plan_type: str = Form("YEARLY")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
    start_date = datetime.now().strftime("%Y-%m-%d")
    days = 365 if plan_type == "YEARLY" else 30
    expiry_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    base_price = 9999.0 if plan_type == "YEARLY" else 999.0
    cgst = base_price * 0.09
    sgst = base_price * 0.09
    total_price = base_price + cgst + sgst

    gst_slabs_json = json.dumps(gst_slabs)

    # Insert Tenant
    cursor.execute("""
    INSERT INTO tenants (
        id, name, owner_name, phone, whatsapp_mobile, email, address, gstin, logo_url,
        upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc, bank_branch,
        gst_slabs, language, master_pin, status, subscription_plan, subscription_start_date, subscription_end_date, price_paid, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Main', ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, datetime('now'))
    """, (
        tenant_id, name.strip(), owner_name.strip(), whatsapp_mobile.strip(), whatsapp_mobile.strip(),
        email.strip() if email else "", address.strip(), gstin.strip() if gstin else "", logo_url.strip() if logo_url else "",
        upi_id.strip(), upi_payee_name.strip() if upi_payee_name else name.strip(),
        bank_name.strip() if bank_name else "", bank_account_no.strip() if bank_account_no else "",
        bank_ifsc.strip() if bank_ifsc else "", gst_slabs_json, language, master_pin.strip(),
        plan_type, start_date, expiry_date, total_price
    ))

    # Insert Subscription Record
    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO subscriptions (id, tenant_id, plan_name, start_date, end_date, is_active, billing_cycle, price_paid, notes, created_at)
    VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'Initial Onboarding License', datetime('now'))
    """, (sub_id, tenant_id, f"PRO_{plan_type}", start_date, expiry_date, plan_type, total_price))

    # Create Initial Admin User for this Garage if username not taken
    cursor.execute("SELECT id FROM users WHERE username = ?", (initial_username.strip(),))
    existing_user = cursor.fetchone()
    if not existing_user:
        pw_hash = hash_password(initial_password.strip())
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO users (id, username, password_hash, full_name, role, email, phone, whatsapp_mobile, tenant_id, status, created_at)
        VALUES (?, ?, ?, ?, 'ADMIN', ?, ?, ?, ?, 'ACTIVE', datetime('now'))
        """, (
            user_id, initial_username.strip(), pw_hash, owner_name.strip(),
            email.strip() if email else "", whatsapp_mobile.strip(), whatsapp_mobile.strip(), tenant_id
        ))
    else:
        cursor.execute("UPDATE users SET tenant_id = ? WHERE id = ?", (tenant_id, existing_user["id"]))

    # Auto-generate SaaS Vendor Invoice for the user's company books
    inv_id = f"sinv_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM saas_vendor_invoices")
    inv_count = cursor.fetchone()[0] + 1
    inv_no = f"HQ-INV-2026-{inv_count:03d}"

    cursor.execute("""
    INSERT INTO saas_vendor_invoices (
        id, invoice_no, tenant_id, tenant_name, invoice_date, plan_type,
        subscription_start, subscription_end, taxable_amount, cgst_rate, cgst_amount,
        sgst_rate, sgst_amount, total_amount, payment_status, payment_mode, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 9.0, ?, 9.0, ?, ?, 'PAID', 'UPI', 'Initial Workshop Setup License Invoice', datetime('now'))
    """, (
        inv_id, inv_no, tenant_id, name.strip(), start_date, plan_type,
        start_date, expiry_date, base_price, cgst, sgst, total_price
    ))

    db.log_audit("ONBOARD_CLIENT_WORKSHOP", "tenants", tenant_id, f"Onboarded client garage {name} with {plan_type} plan", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/clients?msg=Workshop+successfully+onboarded+and+license+activated!", status_code=303)

@app.post("/api/admin/clients/update")
async def update_client_workshop(
    tenant_id: str = Form(...),
    name: str = Form(...),
    owner_name: str = Form(...),
    whatsapp_mobile: str = Form(...),
    email: Optional[str] = Form(None),
    address: str = Form(...),
    gstin: Optional[str] = Form(None),
    logo_url: Optional[str] = Form(None),
    upi_id: str = Form(...),
    upi_payee_name: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account_no: Optional[str] = Form(None),
    bank_ifsc: Optional[str] = Form(None),
    gst_slabs: List[str] = Form(...),
    language: str = Form("en"),
    master_pin: str = Form("1234")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    gst_slabs_json = json.dumps(gst_slabs)

    cursor.execute("""
    UPDATE tenants SET
        name = ?, owner_name = ?, phone = ?, whatsapp_mobile = ?, email = ?,
        address = ?, gstin = ?, logo_url = ?, upi_id = ?, upi_payee_name = ?,
        bank_name = ?, bank_account_no = ?, bank_ifsc = ?,
        gst_slabs = ?, language = ?, master_pin = ?
    WHERE id = ?
    """, (
        name.strip(), owner_name.strip(), whatsapp_mobile.strip(), whatsapp_mobile.strip(), email.strip() if email else "",
        address.strip(), gstin.strip() if gstin else "", logo_url.strip() if logo_url else "",
        upi_id.strip(), upi_payee_name.strip() if upi_payee_name else name.strip(),
        bank_name.strip() if bank_name else "", bank_account_no.strip() if bank_account_no else "",
        bank_ifsc.strip() if bank_ifsc else "", gst_slabs_json, language, master_pin.strip(), tenant_id
    ))

    # Also update workshop_profile if it matches default active tenant
    cursor.execute("""
    UPDATE workshop_profile SET
        name = ?, owner_name = ?, phone = ?, email = ?, address = ?, gstin = ?,
        logo_url = ?, upi_id = ?, upi_payee_name = ?, bank_name = ?, bank_account_no = ?, bank_ifsc = ?,
        gst_slabs = ?, language = ?, master_pin = ?, updated_at = datetime('now')
    WHERE id = 'default'
    """, (
        name.strip(), owner_name.strip(), whatsapp_mobile.strip(), email.strip() if email else "",
        address.strip(), gstin.strip() if gstin else "", logo_url.strip() if logo_url else "",
        upi_id.strip(), upi_payee_name.strip() if upi_payee_name else name.strip(),
        bank_name.strip() if bank_name else "", bank_account_no.strip() if bank_account_no else "",
        bank_ifsc.strip() if bank_ifsc else "", gst_slabs_json, language, master_pin.strip()
    ))

    db.log_audit("UPDATE_CLIENT_WORKSHOP", "tenants", tenant_id, f"Updated configuration for {name}", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/clients?msg=Workshop+configuration+updated+successfully!", status_code=303)

@app.post("/api/admin/toggle-tenant-status")
async def toggle_tenant_status(tenant_id: str = Form(...), new_status: str = Form(...)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tenants SET status = ? WHERE id = ?", (new_status, tenant_id))
    db.log_audit("TOGGLE_TENANT_STATUS", "tenants", tenant_id, f"Status changed to {new_status}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/clients?msg=Workshop+status+updated!", status_code=303)

# =========================================================
# 👥 WORKSHOP USERS & OTP MANAGEMENT
# =========================================================
@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, msg: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.*, t.name as tenant_name 
        FROM users u 
        LEFT JOIN tenants t ON u.tenant_id = t.id 
        ORDER BY u.created_at DESC
    """)
    users = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT id, name, owner_name FROM tenants ORDER BY name ASC")
    tenants = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_hq/users.html",
        context={
            "active_page": "users",
            "users": users,
            "tenants": tenants,
            "msg": msg
        }
    )

@app.post("/api/admin/users/create")
async def create_user_account(
    tenant_id: str = Form(...),
    full_name: str = Form(...),
    username: str = Form(...),
    whatsapp_mobile: str = Form(...),
    role: str = Form("STAFF"),
    password: str = Form(...)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (username.strip(),))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return RedirectResponse(url="/users?msg=Error:+Username+already+exists.+Please+choose+another.", status_code=303)

    user_id = f"user_{uuid.uuid4().hex[:8]}"
    pw_hash = hash_password(password.strip())

    cursor.execute("""
    INSERT INTO users (id, username, password_hash, full_name, role, whatsapp_mobile, phone, tenant_id, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', datetime('now'))
    """, (
        user_id, username.strip(), pw_hash, full_name.strip(), role,
        whatsapp_mobile.strip(), whatsapp_mobile.strip(), tenant_id
    ))

    db.log_audit("CREATE_USER", "users", user_id, f"Created user {username} for tenant {tenant_id}", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/users?msg=User+account+created+successfully!", status_code=303)

@app.post("/api/admin/users/reset-password")
async def reset_user_password(
    user_id: str = Form(...),
    username: str = Form(...),
    new_password: str = Form(...)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    pw_hash = hash_password(new_password.strip())
    cursor.execute("""
    UPDATE users 
    SET password_hash = ?, otp_code = NULL, otp_expiry = NULL, reset_token = NULL, reset_token_expiry = NULL 
    WHERE id = ?
    """, (pw_hash, user_id))

    db.log_audit("ADMIN_RESET_PASSWORD", "users", user_id, f"Master Admin reset password for {username}", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/users?msg=Password+reset+successfully+for+user+@" + username, status_code=303)

# =========================================================
# 🔑 SAAS LICENSES & SUBSCRIPTIONS
# =========================================================
@app.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request, tenant_id: Optional[str] = None, msg: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT s.*, t.name as tenant_name 
        FROM subscriptions s 
        LEFT JOIN tenants t ON s.tenant_id = t.id 
    """
    params = []
    if tenant_id:
        query += " WHERE s.tenant_id = ? "
        params.append(tenant_id)
    query += " ORDER BY s.created_at DESC"

    cursor.execute(query, tuple(params))
    subscriptions = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT id, name, subscription_end_date FROM tenants ORDER BY name ASC")
    tenants = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_hq/subscriptions.html",
        context={
            "active_page": "subscriptions",
            "subscriptions": subscriptions,
            "tenants": tenants,
            "selected_tenant_id": tenant_id,
            "msg": msg
        }
    )

@app.post("/api/admin/subscriptions/renew")
async def renew_subscription(
    tenant_id: str = Form(...),
    billing_cycle: str = Form("YEARLY"),
    payment_mode: str = Form("UPI"),
    taxable_amount: float = Form(9999.0),
    payment_ref: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
    tenant = cursor.fetchone()
    if not tenant:
        conn.close()
        return RedirectResponse(url="/subscriptions?msg=Tenant+not+found", status_code=303)

    tenant_name = tenant["name"]
    current_end = tenant["subscription_end_date"]
    today = datetime.now().date()

    # If already active in future, extend from current end date; otherwise start from today
    start_dt = today
    if current_end:
        try:
            curr_dt = datetime.strptime(current_end, "%Y-%m-%d").date()
            if curr_dt > today:
                start_dt = curr_dt
        except Exception:
            pass

    days = 365 if billing_cycle == "YEARLY" else 30
    new_end_dt = start_dt + timedelta(days=days)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = new_end_dt.strftime("%Y-%m-%d")

    cgst = round(taxable_amount * 0.09, 2)
    sgst = round(taxable_amount * 0.09, 2)
    total_amount = round(taxable_amount + cgst + sgst, 2)

    # Update Tenant
    cursor.execute("""
    UPDATE tenants SET 
        status = 'ACTIVE', 
        subscription_plan = ?,
        subscription_start_date = ?,
        subscription_end_date = ?,
        price_paid = price_paid + ?
    WHERE id = ?
    """, (f"PRO_{billing_cycle}", start_str, end_str, total_amount, tenant_id))

    # Insert Subscription Record
    sub_id = f"sub_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO subscriptions (id, tenant_id, plan_name, start_date, end_date, is_active, billing_cycle, price_paid, notes, created_at)
    VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'License Renewal', datetime('now'))
    """, (sub_id, tenant_id, f"PRO_{billing_cycle}", start_str, end_str, billing_cycle, total_amount))

    # Auto-generate SaaS Vendor Invoice for Vendor Books
    inv_id = f"sinv_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM saas_vendor_invoices")
    inv_count = cursor.fetchone()[0] + 1
    inv_no = f"HQ-INV-2026-{inv_count:03d}"

    cursor.execute("""
    INSERT INTO saas_vendor_invoices (
        id, invoice_no, tenant_id, tenant_name, invoice_date, plan_type,
        subscription_start, subscription_end, taxable_amount, cgst_rate, cgst_amount,
        sgst_rate, sgst_amount, total_amount, payment_status, payment_mode, payment_ref, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 9.0, ?, 9.0, ?, ?, 'PAID', ?, ?, 'SaaS License Renewal', datetime('now'))
    """, (
        inv_id, inv_no, tenant_id, tenant_name, datetime.now().strftime("%Y-%m-%d"), billing_cycle,
        start_str, end_str, taxable_amount, cgst, sgst, total_amount, payment_mode, payment_ref or "UPI-PAID"
    ))

    db.log_audit("RENEW_SUBSCRIPTION", "subscriptions", sub_id, f"Renewed license for {tenant_name} until {end_str}", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/subscriptions?tenant_id={tenant_id}&msg=License+renewed+until+{end_str}+and+invoice+generated!", status_code=303)

# =========================================================
# 💰 SAAS VENDOR ACCOUNTING, REVENUE & GSTR-1 AUDIT
# =========================================================
@app.get("/accounting", response_class=HTMLResponse)
async def accounting_page(request: Request, fy: Optional[str] = "2025-2026"):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM saas_vendor_invoices"
    params = []

    if fy == "2025-2026":
        query += " WHERE invoice_date >= '2025-04-01' AND invoice_date <= '2026-03-31'"
    elif fy == "2026-2027":
        query += " WHERE invoice_date >= '2026-04-01' AND invoice_date <= '2027-03-31'"

    query += " ORDER BY invoice_date DESC"
    cursor.execute(query, tuple(params))
    invoices = [dict(row) for row in cursor.fetchall()]

    taxable_total = sum(i.get("taxable_amount", 0.0) for i in invoices)
    cgst_total = sum(i.get("cgst_amount", 0.0) for i in invoices)
    sgst_total = sum(i.get("sgst_amount", 0.0) for i in invoices)
    gross_total = sum(i.get("total_amount", 0.0) for i in invoices)

    summary = {
        "taxable_total": taxable_total,
        "cgst_total": cgst_total,
        "sgst_total": sgst_total,
        "gross_total": gross_total,
        "invoices_count": len(invoices)
    }

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_hq/accounting.html",
        context={
            "active_page": "accounting",
            "invoices": invoices,
            "summary": summary,
            "current_fy": fy
        }
    )

@app.get("/api/admin/accounting/export-gstr1-excel")
async def export_vendor_gstr1_excel(fy: Optional[str] = "2025-2026"):
    """Export SaaS Vendor GSTR-1 Sales Report in styled Excel workbook for CA"""
    conn = db.get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM saas_vendor_invoices"
    if fy == "2025-2026":
        query += " WHERE invoice_date >= '2025-04-01' AND invoice_date <= '2026-03-31'"
    elif fy == "2026-2027":
        query += " WHERE invoice_date >= '2026-04-01' AND invoice_date <= '2027-03-31'"
    query += " ORDER BY invoice_date ASC"

    cursor.execute(query)
    invoices = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM saas_vendor_profile LIMIT 1")
    prof_row = cursor.fetchone()
    vendor = dict(prof_row) if prof_row else {
        "company_name": "AutoVolt Technologies Pvt Ltd",
        "gstin": "32AABCA9876C1Z5"
    }

    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GSTR-1 SaaS Sales"
    ws.views.sheetView[0].showGridLines = True

    # Styling colors
    purple_fill = PatternFill(start_color="4C1D95", end_color="4C1D95", fill_type="solid")
    dark_header_fill = PatternFill(start_color="1E1B4B", end_color="1E1B4B", fill_type="solid")
    title_font = Font(name="Segoe UI", size=15, bold=True, color="FFFFFF")
    sub_font = Font(name="Segoe UI", size=10, color="E0E7FF")
    header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    bold_font = Font(name="Segoe UI", size=10, bold=True)
    normal_font = Font(name="Segoe UI", size=10)

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Title Banner
    ws.merge_cells("A1:J1")
    ws["A1"] = f"{vendor.get('company_name', 'AutoVolt Technologies')} — GSTR-1 SAAS SALES AUDIT REPORT"
    ws["A1"].font = title_font
    ws["A1"].fill = purple_fill
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:J2")
    ws["A2"] = f"GSTIN: {vendor.get('gstin', '')} | Financial Year: {fy} | SAC: 997331 (Software Licensing & SaaS Subscriptions)"
    ws["A2"].font = sub_font
    ws["A2"].fill = dark_header_fill
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # Headers
    headers = [
        "Sl No", "Invoice No", "Invoice Date", "Client Garage Name", "SAC Code",
        "Taxable Amount (₹)", "CGST (9%)", "SGST (9%)", "Total Tax (18%)", "Invoice Total (₹)"
    ]

    ws.append([]) # Row 3 blank
    ws.append(headers) # Row 4
    ws.row_dimensions[4].height = 24

    for col_idx, col_name in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = dark_header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    total_taxable = 0.0
    total_cgst = 0.0
    total_sgst = 0.0
    total_gross = 0.0

    current_row = 5
    for idx, inv in enumerate(invoices, 1):
        taxable = inv.get("taxable_amount", 0.0)
        cgst = inv.get("cgst_amount", 0.0)
        sgst = inv.get("sgst_amount", 0.0)
        tot_tax = cgst + sgst
        inv_tot = inv.get("total_amount", 0.0)

        total_taxable += taxable
        total_cgst += cgst
        total_sgst += sgst
        total_gross += inv_tot

        row_data = [
            idx,
            inv.get("invoice_no", ""),
            inv.get("invoice_date", ""),
            inv.get("tenant_name", ""),
            "997331",
            taxable,
            cgst,
            sgst,
            tot_tax,
            inv_tot
        ]
        ws.append(row_data)

        for c_idx in range(1, 11):
            c = ws.cell(row=current_row, column=c_idx)
            c.font = normal_font
            c.border = thin_border
            if c_idx in (6, 7, 8, 9, 10):
                c.number_format = '₹#,##0.00'
                c.alignment = Alignment(horizontal="right")
            elif c_idx in (1, 3, 5):
                c.alignment = Alignment(horizontal="center")

        current_row += 1

    # Total Summary Row
    summary_row = [
        "TOTAL", "", "", "", "",
        total_taxable, total_cgst, total_sgst, (total_cgst + total_sgst), total_gross
    ]
    ws.append(summary_row)
    ws.row_dimensions[current_row].height = 24

    for c_idx in range(1, 11):
        c = ws.cell(row=current_row, column=c_idx)
        c.font = bold_font
        c.border = thin_border
        c.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        if c_idx in (6, 7, 8, 9, 10):
            c.number_format = '₹#,##0.00'
            c.alignment = Alignment(horizontal="right")

    # Column Widths
    col_widths = [8, 18, 14, 30, 12, 20, 15, 15, 18, 20]
    for idx, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"GSTR1_SaaS_Vendor_Audit_{fy}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# =========================================================
# ⚙️ SAAS VENDOR COMPANY SETTINGS
# =========================================================
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, msg: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM saas_vendor_profile LIMIT 1")
    prof = cursor.fetchone()
    profile = dict(prof) if prof else {}

    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin_hq/settings.html",
        context={
            "active_page": "settings",
            "profile": profile,
            "msg": msg
        }
    )

@app.post("/api/admin/vendor-settings/update")
async def update_vendor_settings(
    company_name: str = Form(...),
    tagline: Optional[str] = Form(None),
    gstin: str = Form(...),
    email: str = Form(...),
    phone: Optional[str] = Form(None),
    whatsapp_phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    upi_id: str = Form(...),
    upi_payee_name: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account_no: Optional[str] = Form(None),
    bank_ifsc: Optional[str] = Form(None),
    monthly_fee: float = Form(999.0),
    yearly_fee: float = Form(9999.0)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE saas_vendor_profile SET
        company_name = ?, tagline = ?, gstin = ?, email = ?, phone = ?, whatsapp_phone = ?,
        address = ?, upi_id = ?, upi_payee_name = ?, bank_name = ?, bank_account_no = ?, bank_ifsc = ?,
        monthly_fee = ?, yearly_fee = ?, updated_at = datetime('now')
    WHERE id = 'vendor_main'
    """, (
        company_name.strip(), tagline.strip() if tagline else "", gstin.strip(), email.strip(),
        phone.strip() if phone else "", whatsapp_phone.strip() if whatsapp_phone else "",
        address.strip() if address else "", upi_id.strip(), upi_payee_name.strip() if upi_payee_name else company_name.strip(),
        bank_name.strip() if bank_name else "", bank_account_no.strip() if bank_account_no else "",
        bank_ifsc.strip() if bank_ifsc else "", monthly_fee, yearly_fee
    ))

    db.log_audit("UPDATE_VENDOR_PROFILE", "saas_vendor_profile", "vendor_main", f"Updated SaaS company profile", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/settings?msg=SaaS+vendor+settings+saved+successfully!", status_code=303)

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting AutoVolt Cloud HQ (SaaS Master Vendor Portal) on http://localhost:8500 ...")
    uvicorn.run("saas_admin_app:app", host="0.0.0.0", port=8500, reload=True)
