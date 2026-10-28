import os
import io
import json
import uuid
import re
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Form, Response, Query, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
import models
from barcode_engine import generate_barcode_svg, generate_barcode_base64
from upi_helper import generate_upi_link, generate_upi_qr_data_url
from whatsapp_helper import (
    generate_wa_me_url,
    format_invoice_whatsapp_message,
    format_job_status_whatsapp_message,
    format_khata_due_reminder_whatsapp_message,
    format_proforma_whatsapp_message
)
import ca_reports
from pdf_generator import generate_invoice_pdf_bytes, generate_proforma_pdf_bytes
from excel_importer import generate_inventory_import_template, parse_inventory_file
from auth_helper import (
    hash_password,
    verify_password,
    verify_master_pin,
    generate_reset_token,
    create_signed_session_cookie,
    verify_signed_session_cookie
)
import otp_helper

app = FastAPI(title="AutoVolt Pro — Auto Electrical Workshop Management", version="2.0.0")

@app.on_event("startup")
async def app_startup_sync():
    """Sync tenants and users from Supabase Cloud on boot"""
    try:
        import supabase_sync
        supabase_sync.sync_critical_from_supabase()
    except Exception as e:
        print(f"[Supabase Startup Sync] {e}")

# Mount Static Files & Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

from tz_helper import (
    get_ist_now,
    get_ist_now_str,
    get_ist_today_str,
    format_dt_to_ist,
    elapsed_time_ist
)

def to_json_filter(obj):
    try:
        from markupsafe import Markup
        return Markup(json.dumps(obj, default=str))
    except Exception:
        return json.dumps(obj, default=str)

def format_currency_filter(val):
    try:
        if val is None or str(val).strip() == "":
            return "0.00"
        return f"{float(val):,.2f}"
    except Exception:
        return "0.00"

def format_int_comma_filter(val):
    try:
        if val is None or str(val).strip() == "":
            return "0"
        return f"{int(float(val)):,}"
    except Exception:
        return "0"

templates.env.filters["tojson"] = to_json_filter
templates.env.filters["to_ist"] = format_dt_to_ist
templates.env.filters["elapsed_ist"] = elapsed_time_ist
templates.env.filters["currency"] = format_currency_filter
templates.env.filters["int_comma"] = format_int_comma_filter

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper to get current active tenant_id from request user session
def get_current_tenant_id(request: Optional[Request] = None, fallback: str = "tenant_1") -> str:
    if request:
        user = get_session_user(request)
        if user and user.get("tenant_id"):
            return user["tenant_id"]
    return fallback

# Helper: Get current active workshop profile for specific tenant or logged-in session user
def get_current_workshop(request: Optional[Request] = None, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    tid = tenant_id
    if not tid and request:
        user = get_session_user(request)
        if user and user.get("tenant_id"):
            tid = user["tenant_id"]

    if not tid:
        tid = "tenant_1"

    row = None
    # 1. Look up workshop_profile by tenant_id or id
    cursor.execute("SELECT * FROM workshop_profile WHERE tenant_id = ? OR id = ? LIMIT 1", (tid, tid))
    row = cursor.fetchone()
    
    # 2. If not found in workshop_profile, check tenants table and auto-create profile
    if not row:
        cursor.execute("SELECT * FROM tenants WHERE id = ? LIMIT 1", (tid,))
        t_row = cursor.fetchone()
        if t_row:
            t = dict(t_row)
            cursor.execute("""
            INSERT OR REPLACE INTO workshop_profile (
                id, tenant_id, name, subtitle, owner_name, phone, email, address, gstin, logo_url,
                upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc, bank_branch,
                gst_slabs, language, currency, master_pin, terms, default_state, default_gst_type, tax_regime, round_off_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Main', ?, ?, '₹', ?, ?, 'Kerala (32)', 'INTRA_STATE', 'REGULAR_GST', 1, datetime('now'), datetime('now'))
            """, (
                t["id"], t["id"], t["name"], "Automotive Electrical & Electronic Service Center",
                t.get("owner_name", ""), t.get("phone", ""), t.get("email", ""), t.get("address", ""),
                t.get("gstin", ""), t.get("logo_url", ""), t.get("upi_id", ""), t.get("upi_payee_name", t["name"]),
                t.get("bank_name", ""), t.get("bank_account_no", ""), t.get("bank_ifsc", ""),
                t.get("gst_slabs", '["0", "5", "12", "18", "28"]'), t.get("language", "en"), t.get("master_pin", "1234"),
                "1. Electrical parts warranty as per manufacturer policy.\n2. Goods once fitted cannot be returned."
            ))
            conn.commit()
            cursor.execute("SELECT * FROM workshop_profile WHERE tenant_id = ? LIMIT 1", (tid,))
            row = cursor.fetchone()

    # 3. Fallback to default
    if not row:
        cursor.execute("SELECT * FROM workshop_profile WHERE id = 'default' LIMIT 1")
        row = cursor.fetchone()

    conn.close()
    if row:
        return dict(row)
    return {
        "id": tid,
        "tenant_id": tid,
        "name": "SPARK AUTO ELECTRICALS",
        "subtitle": "Auto Electrical & Electronic Service Center",
        "owner_name": "Suresh Kumar",
        "phone": "+91 98765 43210",
        "email": "sparkautocare@gmail.com",
        "address": "Near Highway Junction, Ernakulam, Kerala - 682001",
        "gstin": "32AABCS1429B1Z8",
        "upi_id": "sparkautoworkshop@okaxis",
        "bank_name": "State Bank of India",
        "bank_account_no": "39876543210",
        "bank_ifsc": "SBIN0001234",
        "bank_branch": "Ernakulam Main",
        "language": "en",
        "currency": "₹",
        "master_pin": "1234",
        "terms": "1. Electrical parts warranty as per manufacturer policy.\n2. Goods once fitted cannot be returned."
    }

# Helper: Check current SaaS subscription status
def check_saas_subscription(request: Optional[Request] = None, tenant_id: Optional[str] = None) -> Dict[str, Any]:
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tid = tenant_id
    if not tid and request:
        user = get_session_user(request)
        if user and user.get("tenant_id"):
            tid = user["tenant_id"]

    if not tid:
        tid = "tenant_1"

    cursor.execute("SELECT * FROM tenants WHERE id = ? LIMIT 1", (tid,))
    t_row = cursor.fetchone()
    cursor.execute("SELECT * FROM subscriptions WHERE tenant_id = ? AND is_active = 1 ORDER BY end_date DESC LIMIT 1", (tid,))
    s_row = cursor.fetchone()

    if not t_row:
        cursor.execute("SELECT * FROM tenants LIMIT 1")
        t_row = cursor.fetchone()

    conn.close()

    tenant = dict(t_row) if t_row else None
    sub = dict(s_row) if s_row else None

    is_expired = False
    today_str = datetime.now().strftime("%Y-%m-%d")
    if sub and sub.get("end_date"):
        if sub["end_date"] < today_str or sub.get("is_active") == 0:
            is_expired = True

    return {
        "tenant": tenant,
        "subscription": sub,
        "is_expired": is_expired
    }

# SaaS Subscription & Authentication Middleware
@app.middleware("http")
async def auth_and_subscription_middleware(request: Request, call_next):
    path = request.url.path
    
    # Exempt routes that should always remain accessible without login
    exempt_prefixes = [
        "/static", "/login", "/logout", "/forgot-password", "/verify-otp", "/reset-password",
        "/subscription-expired", "/view", "/invoice", "/api/device", "/health", "/ping"
    ]
    
    is_exempt = any(path.startswith(prefix) for prefix in exempt_prefixes)

    # Gracefully handle Uptime monitors (UptimeRobot, Render Health checks, HEAD requests)
    if request.method == "HEAD":
        if path in ["/", "/health", "/ping", "/login"] or is_exempt:
            return Response(status_code=200)
    
    raw_cookie = request.cookies.get("session_user")
    session_user = verify_signed_session_cookie(raw_cookie)
    last_active_str = request.cookies.get("session_last_active")
    
    now_ts = datetime.now().timestamp()
    is_session_expired = False
    valid_db_user = None

    if session_user:
        # Check 30-minute inactivity timeout (1800 seconds)
        if last_active_str:
            try:
                if now_ts - float(last_active_str) > 1800:
                    is_session_expired = True
            except Exception:
                pass

        # Verify active user in DB
        if not is_session_expired:
            conn = db.get_db_connection()
            cursor = conn.cursor()
            if ":" in session_user:
                tid, uname = session_user.split(":", 1)
                cursor.execute("SELECT id, username FROM users WHERE username = ? AND tenant_id = ? AND status = 'ACTIVE'", (uname, tid))
            elif session_user.startswith("user_"):
                cursor.execute("SELECT id, username FROM users WHERE id = ? AND status = 'ACTIVE'", (session_user,))
            else:
                cursor.execute("SELECT id, username FROM users WHERE username = ? AND status = 'ACTIVE'", (session_user,))
            valid_db_user = cursor.fetchone()
            conn.close()
            if not valid_db_user:
                is_session_expired = True

    # If session expired or invalid user, force redirect to login
    if not is_exempt and (not session_user or is_session_expired):
        redirect_url = "/login?error=" + ("Session+expired+due+to+inactivity.+Please+log+in+again." if is_session_expired else "Authentication+required.")
        response = RedirectResponse(url=redirect_url, status_code=303) if request.method == "GET" else JSONResponse({"error": "Authentication required", "redirect": "/login"}, status_code=401)
        response.delete_cookie("session_user")
        response.delete_cookie("session_last_active")
        return response

    # If already logged in with valid session visiting login page, redirect to dashboard
    if path == "/login" and session_user and not is_session_expired and request.method == "GET":
        return RedirectResponse(url="/", status_code=303)
    
    # SaaS Expiration Check for authenticated users
    if not is_exempt and request.method == "GET":
        sub_info = check_saas_subscription(request)
        if sub_info["is_expired"]:
            return RedirectResponse(url="/subscription-expired", status_code=303)
            
    response = await call_next(request)
    
    # Refresh inactivity timestamp cookie for active logged-in user
    if session_user and not is_session_expired:
        response.set_cookie(key="session_last_active", value=str(int(now_ts)), max_age=86400, httponly=True)
        
    return response

# Helper to get current logged in user dict
def get_session_user(request: Request) -> Optional[dict]:
    raw_user = request.cookies.get("session_user")
    session_user = verify_signed_session_cookie(raw_user)
    if not session_user:
        return None
    conn = db.get_db_connection()
    cursor = conn.cursor()
    if ":" in session_user:
        tid, uname = session_user.split(":", 1)
        cursor.execute("SELECT id, username, role, full_name, email, phone, whatsapp_mobile, permissions, tenant_id FROM users WHERE username = ? AND tenant_id = ? AND status = 'ACTIVE'", (uname, tid))
    elif session_user.startswith("user_"):
        cursor.execute("SELECT id, username, role, full_name, email, phone, whatsapp_mobile, permissions, tenant_id FROM users WHERE id = ? AND status = 'ACTIVE'", (session_user,))
    else:
        cursor.execute("SELECT id, username, role, full_name, email, phone, whatsapp_mobile, permissions, tenant_id FROM users WHERE username = ? AND status = 'ACTIVE'", (session_user,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

templates.env.globals["get_session_user"] = get_session_user
templates.env.globals["get_current_workshop"] = get_current_workshop

# Dynamic Base URL resolver for public share links & WhatsApp downloads
def get_base_url(request: Optional[Request] = None) -> str:
    env_url = os.getenv("APP_BASE_URL", "").strip()
    if env_url and "localhost" not in env_url and "127.0.0.1" not in env_url:
        return env_url.rstrip("/")

    if request:
        forwarded_host = request.headers.get("x-forwarded-host")
        forwarded_proto = request.headers.get("x-forwarded-proto", "https")
        if forwarded_host:
            return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
        
        host = request.headers.get("host")
        if host:
            proto = "https" if request.url.scheme == "https" or "onrender.com" in host or "herokuapp.com" in host else "http"
            return f"{proto}://{host}".rstrip("/")

        return str(request.base_url).rstrip("/")

    return os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# =========================================================
# 🩺 HEALTH & UPTIME MONITORING ENDPOINTS
# =========================================================
@app.api_route("/health", methods=["GET", "HEAD"])
@app.api_route("/ping", methods=["GET", "HEAD"])
async def workshop_health_check():
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "app": "AutoVolt Workshop Manager",
            "timestamp": datetime.now().isoformat()
        }
    )

# =========================================================
# 🔐 AUTHENTICATION & WHATSAPP OTP PASSWORD RESET
# =========================================================

@app.api_route("/login", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[str] = None, success_msg: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error, "success_msg": success_msg}
    )

@app.post("/login")
async def handle_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    workshop_code: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()

    clean_username = username.strip()
    clean_code = (workshop_code or "").strip()

    target_tenant_id = None
    if clean_code:
        cursor.execute("SELECT id, name FROM tenants WHERE UPPER(client_code) = UPPER(?) OR UPPER(id) = UPPER(?) OR id = ?", (clean_code, clean_code, clean_code))
        t_row = cursor.fetchone()
        if not t_row:
            cursor.execute("SELECT id, tenant_id, name FROM workshop_profile WHERE UPPER(client_code) = UPPER(?) OR UPPER(id) = UPPER(?) OR id = ?", (clean_code, clean_code, clean_code))
            p_row = cursor.fetchone()
            if p_row:
                target_tenant_id = p_row["tenant_id"] or p_row["id"]
        else:
            target_tenant_id = t_row["id"]

        if not target_tenant_id:
            conn.close()
            try:
                import supabase_sync
                cloud_t = supabase_sync.fetch_and_cache_tenant_from_supabase(clean_code)
                if cloud_t:
                    target_tenant_id = cloud_t.get("id")
            except Exception as e:
                print(f"[Supabase Login Tenant Lookup] {e}")
            conn = db.get_db_connection()
            cursor = conn.cursor()

        if not target_tenant_id:
            conn.close()
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={"error": f"Workshop ID '{clean_code.upper()}' not found. Please verify with your workshop owner."}
            )

    if target_tenant_id:
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND tenant_id = ? AND status = 'ACTIVE'", (clean_username, target_tenant_id))
        user_rows = cursor.fetchall()
    else:
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND status = 'ACTIVE'", (clean_username,))
        user_rows = cursor.fetchall()

    if not user_rows:
        try:
            import supabase_sync
            supabase_sync.sync_critical_from_supabase()
            if target_tenant_id:
                cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND tenant_id = ? AND status = 'ACTIVE'", (clean_username, target_tenant_id))
            else:
                cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?) AND status = 'ACTIVE'", (clean_username,))
            user_rows = cursor.fetchall()
        except Exception as e:
            print(f"[Supabase Login User Lookup] {e}")

    if not user_rows:
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid credentials. Please verify username and Workshop ID."}
        )

    if len(user_rows) > 1 and not target_tenant_id:
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Multiple workshops use this username. Please enter your Workshop ID (e.g. SPARK or KOCHI)."}
        )

    user_row = user_rows[0]
    if not verify_password(password.strip(), user_row["password_hash"]):
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid password. Please try again."}
        )

    user = dict(user_row)
    db.log_audit("USER_LOGIN", "users", user["id"], f"User {user['username']} logged into {user.get('tenant_id')}", cursor=cursor)
    conn.commit()
    conn.close()
    
    response = RedirectResponse(url="/", status_code=303)
    now_ts_str = str(int(datetime.now().timestamp()))
    signed_session = create_signed_session_cookie(f"{user['tenant_id']}:{user['username']}", expires_in=86400 * 7)
    response.set_cookie(key="session_user", value=signed_session, max_age=86400 * 7, httponly=True, samesite="lax")
    response.set_cookie(key="session_last_active", value=now_ts_str, max_age=86400 * 7, httponly=True, samesite="lax")
    return response

@app.get("/logout")
async def handle_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_user")
    response.delete_cookie("session_last_active")
    return response

# =========================================================
# 📱 WORKSHOP DEVICE ACTIVATION & WHATSAPP OTP ENDPOINTS
# One-time OTP device authorization for computers / phones
# =========================================================

@app.post("/api/device/request-otp")
async def request_device_otp(workshop_code: str = Form(...)):
    clean_code = (workshop_code or "").strip()
    if not clean_code:
        return JSONResponse({"success": False, "error": "Workshop ID / Client Code is required."}, status_code=400)

    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tenants WHERE UPPER(client_code) = UPPER(?) OR UPPER(id) = UPPER(?) OR id = ?", (clean_code, clean_code, clean_code))
    t_row = cursor.fetchone()
    if not t_row:
        cursor.execute("SELECT * FROM workshop_profile WHERE UPPER(client_code) = UPPER(?) OR UPPER(id) = UPPER(?) OR id = ?", (clean_code, clean_code, clean_code))
        t_row = cursor.fetchone()

    # Cloud fallback check if not in local cache
    if not t_row:
        conn.close()
        try:
            import supabase_sync
            cloud_t = supabase_sync.fetch_and_cache_tenant_from_supabase(clean_code)
            if cloud_t:
                t_row = cloud_t
        except Exception as e:
            print(f"[Supabase Sync Device Request] {e}")
        conn = db.get_db_connection()
        cursor = conn.cursor()

    if not t_row:
        conn.close()
        return JSONResponse({"success": False, "error": f"Workshop ID '{clean_code.upper()}' not found. Please verify with your workshop owner."}, status_code=404)

    tenant = dict(t_row)
    phone = (tenant.get("whatsapp_mobile") or tenant.get("phone") or "").strip()
    if not phone:
        conn.close()
        return JSONResponse({"success": False, "error": "No WhatsApp mobile number registered for this workshop."}, status_code=400)

    # Generate 6-digit OTP
    otp_code = otp_helper.generate_numeric_otp(6)
    act_id = f"act_{uuid.uuid4().hex[:8]}"
    expires_at = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")

    # Invalidate previous unused OTPs for this client
    cursor.execute("UPDATE device_activations SET is_verified = 2 WHERE client_code = ? AND is_verified = 0", (clean_code,))

    # Store in SQLite
    cursor.execute("""
    INSERT INTO device_activations (id, tenant_id, client_code, phone, otp_code, device_name, is_verified, expires_at, created_at)
    VALUES (?, ?, ?, ?, ?, 'Browser Terminal', 0, ?, datetime('now'))
    """, (act_id, tenant.get("id"), clean_code, phone, otp_code, expires_at))
    conn.commit()
    conn.close()

    # Push to Supabase Cloud if available
    try:
        import supabase_sync
        supabase_sync.push_to_supabase("device_activations", {
            "id": act_id, "tenant_id": tenant.get("id"), "client_code": clean_code,
            "phone": phone, "otp_code": otp_code, "device_name": "Browser Terminal",
            "is_verified": 0, "expires_at": expires_at, "created_at": datetime.now().isoformat()
        })
    except Exception as e:
        print(f"[Supabase Device Push] {e}")

    # 1. Attempt sending via Meta WhatsApp API (e.g. MoneyMate or AutoVolt Meta account)
    import whatsapp_helper
    meta_res = whatsapp_helper.send_meta_whatsapp_otp(
        to_phone=phone,
        otp_code=otp_code,
        workshop_name=tenant.get("name", "AutoVolt Pro"),
        client_code=clean_code
    )

    # 2. Build 1-Click WhatsApp direct link
    wa_msg = (
        f"🔐 *AutoVolt Pro - Workshop Device Registration*\n\n"
        f"Workshop: *{tenant.get('name')}* ({clean_code})\n"
        f"Your 6-digit Device Activation Code is: *{otp_code}*\n\n"
        f"Enter this code on your computer or mobile browser to authorize this device. "
        f"Valid for 15 minutes."
    )
    wa_url = whatsapp_helper.generate_wa_me_url(phone, wa_msg)

    # Masked phone for UI display (e.g. +91 98470XXXX5)
    digits_only = re.sub(r"\D", "", phone)
    if len(digits_only) >= 10:
        masked = f"+91 {digits_only[-10:-5]}XXXX{digits_only[-2:]}"
    else:
        masked = phone

    return JSONResponse({
        "success": True,
        "workshop_name": tenant.get("name"),
        "client_code": clean_code,
        "masked_phone": masked,
        "wa_url": wa_url,
        "meta_sent": meta_res.get("success", False),
        "dev_otp": otp_code  # convenient preview for workshop owner/developer
    })

@app.post("/api/device/verify-otp")
async def verify_device_otp(workshop_code: str = Form(...), otp_code: str = Form(...)):
    clean_code = (workshop_code or "").strip().upper()
    clean_otp = (otp_code or "").strip()

    if not clean_code or not clean_otp:
        return JSONResponse({"success": False, "error": "Workshop ID and OTP are required."}, status_code=400)

    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT * FROM device_activations
    WHERE (UPPER(client_code) = UPPER(?) OR UPPER(tenant_id) = UPPER(?)) AND otp_code = ? AND is_verified = 0 AND expires_at >= datetime('now')
    ORDER BY created_at DESC LIMIT 1
    """, (clean_code, clean_code, clean_otp))
    act = cursor.fetchone()

    # Cloud fallback if not in local table
    if not act:
        try:
            import supabase_sync
            sp = supabase_sync.get_supabase()
            if sp:
                res = sp.table("device_activations").select("*").or_(f"client_code.ilike.{clean_code},tenant_id.ilike.{clean_code}").eq("otp_code", clean_otp).eq("is_verified", 0).execute()
                rows = res.data or []
                if rows:
                    act = rows[0]
                    cursor.execute("INSERT OR REPLACE INTO device_activations (id, tenant_id, client_code, phone, otp_code, is_verified, expires_at, created_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                                   (act["id"], act["tenant_id"], act["client_code"], act["phone"], act["otp_code"], act["expires_at"], act["created_at"]))
                    conn.commit()
        except Exception as e:
            print(f"[Supabase Verify Device Fallback] {e}")

    if not act:
        conn.close()
        return JSONResponse({"success": False, "error": "Invalid or expired OTP code. Please request a new OTP."}, status_code=400)

    # Mark as verified
    act_dict = dict(act)
    cursor.execute("UPDATE device_activations SET is_verified = 1 WHERE id = ?", (act_dict["id"],))
    conn.commit()

    # Get workshop details
    cursor.execute("SELECT name FROM tenants WHERE UPPER(client_code) = UPPER(?) OR UPPER(id) = UPPER(?) OR id = ?", (clean_code, clean_code, clean_code))
    t_row = cursor.fetchone()
    ws_name = t_row["name"] if t_row else clean_code
    conn.close()

    return JSONResponse({
        "success": True,
        "message": f"Device registered successfully for {ws_name}!",
        "workshop_code": clean_code,
        "workshop_name": ws_name
    })

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(
        request=request,
        name="forgot_password.html",
        context={"error": error}
    )

@app.post("/forgot-password")
async def handle_forgot_password(request: Request, username_or_mobile: str = Form(...)):
    otp_data = otp_helper.generate_and_store_otp(username_or_mobile.strip())
    
    if not otp_data:
        return templates.TemplateResponse(
            request=request,
            name="forgot_password.html",
            context={"error": "No active account found for that username or WhatsApp mobile number."}
        )

    # Redirect to OTP verification page
    username = otp_data["username"]
    return RedirectResponse(url=f"/verify-otp?username={username}", status_code=303)

@app.get("/verify-otp", response_class=HTMLResponse)
async def verify_otp_page(request: Request, username: str = Query(...), error: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return RedirectResponse(url="/forgot-password?error=User+not+found", status_code=303)

    user_dict = dict(user)
    mobile = user_dict.get("whatsapp_mobile") or user_dict.get("phone") or "+919876500000"
    otp_code = user_dict.get("otp_code", "")
    whatsapp_link = otp_helper.build_whatsapp_otp_url(mobile, otp_code, username, user_dict.get("full_name", ""))

    show_dev_otp = os.getenv("DEBUG_MODE", "").lower() in ("true", "1")
    return templates.TemplateResponse(
        request=request,
        name="verify_otp.html",
        context={
            "username": username,
            "whatsapp_mobile": mobile,
            "whatsapp_link": whatsapp_link,
            "otp_preview": otp_code if show_dev_otp else None,
            "show_otp_preview": show_dev_otp,
            "error": error
        }
    )

@app.post("/verify-otp")
async def handle_verify_otp(
    request: Request,
    username: str = Form(...),
    otp: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    if new_password.strip() != confirm_password.strip():
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
        user = cursor.fetchone()
        conn.close()
        mobile = user["whatsapp_mobile"] if user else ""
        otp_code = user["otp_code"] if user else ""
        wa_link = otp_helper.build_whatsapp_otp_url(mobile, otp_code, username) if user else ""

        return templates.TemplateResponse(
            request=request,
            name="verify_otp.html",
            context={
                "username": username,
                "whatsapp_mobile": mobile,
                "whatsapp_link": wa_link,
                "otp_preview": otp_code,
                "error": "Passwords do not match. Please re-enter."
            }
        )

    success, msg = otp_helper.verify_and_reset_password(username.strip(), otp.strip(), new_password.strip())
    
    if not success:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
        user = cursor.fetchone()
        conn.close()
        mobile = user["whatsapp_mobile"] if user else ""
        otp_code = user["otp_code"] if user else ""
        wa_link = otp_helper.build_whatsapp_otp_url(mobile, otp_code, username) if user else ""

        return templates.TemplateResponse(
            request=request,
            name="verify_otp.html",
            context={
                "username": username,
                "whatsapp_mobile": mobile,
                "whatsapp_link": wa_link,
                "otp_preview": otp_code,
                "error": msg
            }
        )

    return RedirectResponse(url="/login?success_msg=Password+reset+successful!+Please+log+in+with+your+new+password.", status_code=303)

@app.get("/subscription-expired", response_class=HTMLResponse)
async def subscription_expired_page(request: Request):
    workshop = get_current_workshop(request)
    return templates.TemplateResponse(
        request=request,
        name="subscription_expired.html",
        context={"workshop": workshop}
    )

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: Optional[str] = None, error: Optional[str] = None):
    user = None
    if token:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username FROM users WHERE reset_token = ?", (token.strip(),))
        user_row = cursor.fetchone()
        conn.close()
        if user_row:
            user = dict(user_row)
    return templates.TemplateResponse(
        request=request,
        name="reset_password.html",
        context={"token": token, "user": user, "error": error}
    )

@app.post("/reset-password")
async def handle_reset_password(
    request: Request,
    token: Optional[str] = Form(None),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    if new_password.strip() != confirm_password.strip():
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={"token": token, "error": "Passwords do not match. Please re-enter."}
        )
    if len(new_password.strip()) < 4:
        return templates.TemplateResponse(
            request=request,
            name="reset_password.html",
            context={"token": token, "error": "Password must be at least 4 characters long."}
        )

    conn = db.get_db_connection()
    cursor = conn.cursor()
    if token:
        cursor.execute("SELECT id, username FROM users WHERE reset_token = ?", (token.strip(),))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return templates.TemplateResponse(
                request=request,
                name="reset_password.html",
                context={"token": token, "error": "Invalid or expired reset token."}
            )
        pw_hash = hash_password(new_password.strip())
        cursor.execute("UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expiry = NULL WHERE id = ?", (pw_hash, user["id"]))
        conn.commit()
        conn.close()
        return RedirectResponse(url="/login?success_msg=Password+reset+successful!+Please+log+in+with+your+new+password.", status_code=303)
    else:
        conn.close()
        return RedirectResponse(url="/forgot-password?error=Please+request+a+password+reset+OTP+first.", status_code=303)

@app.get("/super-admin", response_class=HTMLResponse)
async def super_admin_page(request: Request):
    user = get_session_user(request)
    if not user or user.get("role") not in ("SUPER_ADMIN", "ADMIN"):
        return RedirectResponse(url="/login?error=Super+Admin+access+required.", status_code=303)
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenants ORDER BY created_at DESC")
    tenants = [dict(r) for r in cursor.fetchall()]
    profile = get_current_workshop(request)
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="super_admin.html",
        context={
            "active_page": "super_admin",
            "tenants": tenants,
            "profile": profile
        }
    )

@app.post("/api/admin/update-master-pin")
async def update_master_pin(request: Request, master_pin: str = Form(...)):
    user = get_session_user(request)
    if not user or user.get("role") not in ("SUPER_ADMIN", "ADMIN"):
        raise HTTPException(status_code=403, detail="Super Admin access required")
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE workshop_profile SET master_pin = ? WHERE id = 'default'", (master_pin.strip(),))
    cursor.execute("UPDATE tenants SET master_pin = ? WHERE id = 'tenant_1'", (master_pin.strip(),))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/super-admin?msg=Master+PIN+updated+successfully", status_code=303)

# =========================================================
# 📊 MAIN DASHBOARD & JOB CARDS
# =========================================================

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def dashboard_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("SELECT COUNT(*) FROM job_cards WHERE tenant_id = ? AND status NOT IN ('DELIVERED', 'CANCELLED')", (tenant_id,))
    active_jobs_count = cursor.fetchone()[0]
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COALESCE(SUM(amount_paid), 0), COUNT(*) FROM invoices WHERE tenant_id = ? AND date(invoice_date) = date(?)", (tenant_id, today_str))
    rev_row = cursor.fetchone()
    today_revenue = rev_row[0]
    today_invoices_count = rev_row[1]
    
    cursor.execute("SELECT COALESCE(SUM(balance_due), 0) FROM invoices WHERE tenant_id = ? AND balance_due > 0", (tenant_id,))
    total_khata_dues = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM inventory_items WHERE tenant_id = ? AND stock_qty <= min_stock_alert", (tenant_id,))
    low_stock_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT * FROM job_cards WHERE tenant_id = ? AND status NOT IN ('DELIVERED', 'CANCELLED') ORDER BY created_at DESC LIMIT 6", (tenant_id,))
    active_jobs = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM technicians WHERE tenant_id = ? ORDER BY total_jobs DESC", (tenant_id,))
    technicians = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM invoices WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 8", (tenant_id,))
    recent_invoices = [dict(row) for row in cursor.fetchall()]
    
    workshop = get_current_workshop(request)
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_page": "dashboard",
            "active_jobs_count": active_jobs_count,
            "today_revenue": today_revenue,
            "today_invoices_count": today_invoices_count,
            "total_khata_dues": total_khata_dues,
            "low_stock_count": low_stock_count,
            "active_jobs": active_jobs,
            "technicians": technicians,
            "recent_invoices": recent_invoices,
            "workshop": workshop
        }
    )

@app.get("/job-cards", response_class=HTMLResponse)
async def job_cards_page(request: Request, filter: Optional[str] = None, status: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("SELECT * FROM job_cards WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,))
    all_jobs_raw = [dict(row) for row in cursor.fetchall()]
    
    all_jobs = []
    active_count = 0
    for j in all_jobs_raw:
        st = j.get("status", "RECEIVED")
        if st not in ("DELIVERED", "CANCELLED"):
            active_count += 1
            
        j["elapsed_time_str"] = elapsed_time_ist(j.get("created_at"))
        j["arrival_time_formatted"] = format_dt_to_ist(j.get("created_at"))
        all_jobs.append(j)
        
    filtered_jobs = all_jobs
    if filter == "active":
        filtered_jobs = [j for j in all_jobs if j.get("status") not in ("DELIVERED", "CANCELLED")]
    elif status:
        filtered_jobs = [j for j in all_jobs if j.get("status") == status]
        
    cursor.execute("SELECT * FROM technicians WHERE tenant_id = ? ORDER BY name ASC", (tenant_id,))
    technicians = [dict(row) for row in cursor.fetchall()]

    # Fetch registered customers & vehicles for quick auto-fill in modal
    cursor.execute("""
    SELECT c.name as customer_name, c.phone as customer_phone,
           v.reg_number as vehicle_reg_no, v.make_model as vehicle_make_model, v.odometer
    FROM customers c
    LEFT JOIN vehicles v ON c.id = v.customer_id
    WHERE c.tenant_id = ?
    ORDER BY c.name ASC
    """, (tenant_id,))
    registered_customers = [dict(row) for row in cursor.fetchall()]

    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="job_cards.html",
        context={
            "active_page": "job_cards",
            "jobs": filtered_jobs,
            "all_jobs": all_jobs,
            "active_count": active_count,
            "filter_mode": filter or "",
            "filter_status": status or "",
            "technicians": technicians,
            "registered_customers": registered_customers
        }
    )

@app.get("/job-cards/{job_id}", response_class=HTMLResponse)
async def job_detail_page(request: Request, job_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job Card not found")
    job = dict(job_row)
    
    try:
        complaints_list = json.loads(job["complaints"]) if job["complaints"] else []
    except Exception:
        complaints_list = [job["complaints"]] if job["complaints"] else []
        
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    raw_items = [dict(row) for row in cursor.fetchall()]
    
    items = []
    total_labor = 0.0
    total_parts = 0.0
    total_tax = 0.0
    
    for i in raw_items:
        qty = int(i.get("quantity") or 1)
        unit_price = float(i.get("unit_price") or 0.0)
        base = round(unit_price * qty, 2)
        t_rate = float(i.get("tax_rate") if i.get("tax_rate") is not None else (18.0 if i.get("item_type") == "LABOR" else 18.0))
        tax_amt = round(base * (t_rate / 100.0), 2)
        line_tot = round(base + tax_amt, 2)
        
        i["base_amount"] = base
        i["tax_rate"] = t_rate
        i["tax_amount"] = tax_amt
        i["total_price"] = line_tot
        i["line_total"] = line_tot
        
        if i.get("item_type") == "LABOR":
            total_labor += base
        else:
            total_parts += base
        total_tax += tax_amt
        items.append(i)
        
    grand_total = round(total_labor + total_parts + total_tax, 2)
    
    cursor.execute("""
    UPDATE job_cards SET total_labor = ?, total_parts = ?, grand_total = ? WHERE id = ?
    """, (total_labor, total_parts, grand_total, job_id))
    conn.commit()
    
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM technicians WHERE tenant_id = ? AND status = 'Active'", (tenant_id,))
    technicians = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM inventory_items WHERE tenant_id = ? AND stock_qty > 0 ORDER BY part_name", (tenant_id,))
    inventory_items = [dict(row) for row in cursor.fetchall()]

    # Check for linked invoice
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? AND tenant_id = ? ORDER BY created_at DESC LIMIT 1", (job_id, tenant_id))
    inv_row = cursor.fetchone()
    linked_invoice = dict(inv_row) if inv_row else None

    # Lifecycle Milestones data
    milestones = {
        "arrival_time": format_dt_to_ist(job.get("created_at")),
        "completed_time": format_dt_to_ist(job.get("completed_at")) if job.get("completed_at") else None,
        "delivered_time": format_dt_to_ist(job.get("delivered_at")) if job.get("delivered_at") else None,
        "invoice": linked_invoice
    }
    
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="job_detail.html",
        context={
            "active_page": "job_cards",
            "job": job,
            "complaints_list": complaints_list,
            "items": items,
            "total_labor": total_labor,
            "total_parts": total_parts,
            "total_tax": total_tax,
            "grand_total": grand_total,
            "technicians": technicians,
            "inventory_items": inventory_items,
            "linked_invoice": linked_invoice,
            "milestones": milestones,
            "workshop": get_current_workshop()
        }
    )


@app.get("/job-cards/{job_id}/print", response_class=HTMLResponse)
async def print_job_sheet(request: Request, job_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job Card not found")
    job = dict(row)
    
    complaints_list = []
    if job.get("complaints"):
        try:
            complaints_list = json.loads(job["complaints"])
        except Exception:
            complaints_list = [job["complaints"]]
            
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()
    
    raw_odo = job.get("odometer")
    job["odometer_str"] = f"{int(raw_odo):,} km" if (raw_odo and str(raw_odo).strip().isdigit() and int(raw_odo) > 0) else ""
    workshop = get_current_workshop(request=request, tenant_id=job.get("tenant_id"))
    
    return templates.TemplateResponse(
        request=request,
        name="print_job_sheet.html",
        context={
            "job": job,
            "complaints": complaints_list,
            "items": items,
            "workshop": workshop
        }
    )


@app.post("/api/job-cards")
async def create_job_card(
    request: Request,
    vehicle_reg_no: str = Form(...),
    vehicle_make_model: str = Form(...),
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    assigned_technician_id: Optional[str] = Form(None),
    odometer: Optional[int] = Form(0),
    custom_complaint_notes: Optional[str] = Form(None)
):
    form_data = await request.form()
    complaints = form_data.getlist("complaints")
    if isinstance(complaints, str):
        comp_list = [complaints] if complaints.strip() else []
    elif isinstance(complaints, list):
        comp_list = [str(c).strip() for c in complaints if str(c).strip()]
    else:
        comp_list = []
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("SELECT COUNT(*) FROM job_cards WHERE tenant_id = ?", (tenant_id,))
    cnt = cursor.fetchone()[0] + 1
    job_number = f"JOB-2026-{cnt:03d}"
    cursor.execute("SELECT id FROM job_cards WHERE job_number = ? AND tenant_id = ?", (job_number, tenant_id))
    while cursor.fetchone():
        cnt += 1
        job_number = f"JOB-2026-{cnt:03d}"
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    
    clean_tech_id = assigned_technician_id.strip() if (assigned_technician_id and assigned_technician_id.strip()) else None
    tech_name = None
    if clean_tech_id:
        cursor.execute("SELECT name FROM technicians WHERE id = ? AND tenant_id = ?", (clean_tech_id, tenant_id))
        t_row = cursor.fetchone()
        if t_row:
            tech_name = t_row["name"]
            
    now_ist = get_ist_now_str()
    cursor.execute("SELECT id FROM customers WHERE phone = ? AND tenant_id = ?", (customer_phone.strip(), tenant_id))
    c_row = cursor.fetchone()
    if c_row:
        customer_id = c_row["id"]
        cursor.execute("UPDATE customers SET total_visits = total_visits + 1 WHERE id = ?", (customer_id,))
    else:
        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        cursor.execute("INSERT INTO customers (id, tenant_id, name, phone, created_at) VALUES (?, ?, ?, ?, ?)", (customer_id, tenant_id, customer_name, customer_phone, now_ist))
        
    cursor.execute("SELECT id FROM vehicles WHERE reg_number = ? AND tenant_id = ?", (vehicle_reg_no.strip().upper(), tenant_id))
    v_row = cursor.fetchone()
    if v_row:
        vehicle_id = v_row["id"]
        cursor.execute("UPDATE vehicles SET odometer = ? WHERE id = ?", (odometer, vehicle_id))
    else:
        vehicle_id = f"veh_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO vehicles (id, tenant_id, reg_number, customer_id, customer_name, customer_phone, make_model, odometer, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (vehicle_id, tenant_id, vehicle_reg_no.strip().upper(), customer_id, customer_name, customer_phone, vehicle_make_model, odometer, now_ist))
        
    complaints_json = json.dumps(comp_list)
    cursor.execute("""
    INSERT INTO job_cards (
        id, tenant_id, job_number, customer_id, customer_name, customer_phone, vehicle_id, vehicle_reg_no,
        vehicle_make_model, odometer, assigned_technician_id, assigned_technician_name,
        status, complaints, custom_complaint_notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RECEIVED', ?, ?, ?)
    """, (
        job_id, tenant_id, job_number, customer_id, customer_name, customer_phone, vehicle_id,
        vehicle_reg_no.strip().upper(), vehicle_make_model, odometer, clean_tech_id,
        tech_name, complaints_json, custom_complaint_notes, now_ist
    ))
    
    db.log_audit("CREATE_JOB_CARD", "job_cards", job_id, f"Job {job_number} for {vehicle_reg_no}", cursor=cursor)
    conn.commit()
    conn.close()

    try:
        import supabase_sync
        supabase_sync.push_to_supabase("job_cards", {
            "id": job_id, "tenant_id": tenant_id, "job_number": job_number,
            "customer_id": customer_id, "customer_name": customer_name, "customer_phone": customer_phone,
            "vehicle_id": vehicle_id, "vehicle_reg_no": vehicle_reg_no.strip().upper(),
            "vehicle_make_model": vehicle_make_model, "odometer": odometer,
            "assigned_technician_name": tech_name, "status": "RECEIVED",
            "complaints": complaints_json, "custom_complaint_notes": custom_complaint_notes,
            "created_at": now_ist
        })
    except Exception as e:
        print(f"[Supabase Job Push Error] {e}")

    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

@app.post("/api/job-cards/{job_id}/status")
async def update_job_status(job_id: str, status: str = Form(...)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    now_ist = get_ist_now_str()
    
    if status == "COMPLETED":
        cursor.execute("UPDATE job_cards SET status = ?, completed_at = ? WHERE id = ?", (status, now_ist, job_id))
    elif status == "DELIVERED":
        cursor.execute("UPDATE job_cards SET status = ?, delivered_at = ? WHERE id = ?", (status, now_ist, job_id))
    else:
        cursor.execute("UPDATE job_cards SET status = ? WHERE id = ?", (status, job_id))
        
    db.log_audit("UPDATE_JOB_STATUS", "job_cards", job_id, f"Status changed to {status}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards", status_code=303)

@app.post("/api/job-cards/{job_id}/update-diagnosis")
async def update_job_diagnosis(job_id: str, diagnosis_notes: str = Form(...)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE job_cards SET diagnosis_notes = ? WHERE id = ?", (diagnosis_notes, job_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

def sync_job_card_to_invoice(cursor, job_id: str):
    """If an active (non-cancelled) invoice is linked to this job card, update its items & totals to match current job_items"""
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? AND payment_status != 'CANCELLED' ORDER BY created_at DESC LIMIT 1", (job_id,))
    inv = cursor.fetchone()
    if not inv:
        return
        
    inv_id = inv["id"]
    
    # Fetch current job items
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    job_items = [dict(r) for r in cursor.fetchall()]
    
    # Remove old invoice items
    cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (inv_id,))
    
    subtotal_labor = 0.0
    subtotal_parts = 0.0
    total_tax = 0.0
    
    # Re-insert invoice items matching job items
    for ji in job_items:
        qty = int(ji.get("quantity") or 1)
        u_price = float(ji.get("unit_price") or 0.0)
        t_rate = float(ji.get("tax_rate") or 0.0)
        item_t = ji.get("item_type") or "PART"
        
        line_base = round(qty * u_price, 2)
        line_tax = round(line_base * (t_rate / 100.0), 2)
        line_tot = round(line_base + line_tax, 2)
        
        if item_t == "LABOR":
            subtotal_labor += line_base
        else:
            subtotal_parts += line_base
            
        total_tax += line_tax
        
        ii_id = f"ii_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO invoice_items (
            id, invoice_id, item_type, item_id, name, barcode, hsn_sac,
            quantity, unit_price, tax_rate, taxable_amount, total_price
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ii_id, inv_id, item_t, ji.get("item_id"), ji.get("name"), ji.get("barcode"),
            ji.get("hsn_code") or ("9987" if item_t == "LABOR" else "8536"),
            qty, u_price, t_rate, line_base, line_tot
        ))
        
    taxable_subtotal = subtotal_labor + subtotal_parts
    total_tax = round(total_tax, 2)
    is_interstate = inv["is_interstate"] if "is_interstate" in inv.keys() else 0
    
    if is_interstate:
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = total_tax
    else:
        cgst_total = round(total_tax / 2.0, 2)
        sgst_total = round(total_tax - cgst_total, 2)
        igst_total = 0.0
        
    discount = float(inv["discount_amount"] or 0.0)
    raw_grand_total = max(0.0, (taxable_subtotal + total_tax) - discount)
    rounded_grand_total = float(round(raw_grand_total))
    round_off = round(rounded_grand_total - raw_grand_total, 2)
    grand_total = rounded_grand_total
    
    old_paid = float(inv["amount_paid"] or 0.0)
    old_payment_status = inv["payment_status"]
    
    if old_payment_status == "PAID" or old_paid >= inv["grand_total"]:
        amount_paid = grand_total
        balance_due = 0.0
        payment_status = "PAID"
    elif inv["payment_mode"] == "KHATA_CREDIT" or old_paid <= 0:
        amount_paid = 0.0
        balance_due = grand_total
        payment_status = "UNPAID"
    else:
        amount_paid = min(old_paid, grand_total)
        balance_due = max(0.0, grand_total - amount_paid)
        payment_status = "PAID" if balance_due <= 0 else ("PARTIAL" if amount_paid > 0 else "UNPAID")
        
    now_ist = get_ist_now_str()
    cursor.execute("""
    UPDATE invoices SET
        subtotal_labor = ?, subtotal_parts = ?, taxable_subtotal = ?,
        cgst_total = ?, sgst_total = ?, igst_total = ?, tax_total = ?,
        round_off = ?, grand_total = ?, amount_paid = ?, balance_due = ?,
        payment_status = ?, updated_at = ?
    WHERE id = ?
    """, (
        subtotal_labor, subtotal_parts, taxable_subtotal,
        cgst_total, sgst_total, igst_total, total_tax,
        round_off, grand_total, amount_paid, balance_due,
        payment_status, now_ist, inv_id
    ))

@app.post("/api/job-cards/{job_id}/items")
async def add_job_card_item(
    job_id: str,
    item_type: str = Form(...),
    name: Optional[str] = Form(None),
    item_id: Optional[str] = Form(None),
    quantity: int = Form(1),
    unit_price: Optional[float] = Form(None),
    tax_rate: Optional[float] = Form(None),
    technician_id: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    tech_name = None
    if technician_id:
        cursor.execute("SELECT name FROM technicians WHERE id = ?", (technician_id,))
        t_row = cursor.fetchone()
        if t_row:
            tech_name = t_row["name"]
            
    barcode = None
    hsn_code = "8536"
    final_tax_rate = float(tax_rate) if tax_rate is not None else 18.0
    
    if item_type == "PART" and item_id:
        cursor.execute("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
        p_row = cursor.fetchone()
        if p_row:
            name = p_row["part_name"]
            barcode = p_row["barcode"]
            hsn_code = p_row["hsn_code"] or "8536"
            if tax_rate is None:
                final_tax_rate = float(p_row["tax_rate"] if p_row["tax_rate"] is not None else 18.0)
            if unit_price is None or unit_price == 0:
                unit_price = float(p_row["selling_price"] or 0.0)
                
            cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (quantity, item_id))
    else:
        hsn_code = "9987"
        if tax_rate is None:
            final_tax_rate = 18.0
        
    base_amount = round((unit_price or 0.0) * quantity, 2)
    tax_amount = round(base_amount * (final_tax_rate / 100.0), 2)
    line_total = round(base_amount + tax_amount, 2)
    line_id = f"ji_{uuid.uuid4().hex[:8]}"
    
    cursor.execute("""
    INSERT INTO job_items (
        id, job_card_id, item_type, item_id, barcode, name, hsn_code,
        quantity, unit_price, tax_rate, total_price, technician_id, technician_name
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        line_id, job_id, item_type, item_id, barcode, name or "Labor Charge",
        hsn_code, quantity, unit_price or 0.0, final_tax_rate, line_total, technician_id, tech_name
    ))
    
    # Recalculate job totals
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    all_items = [dict(r) for r in cursor.fetchall()]
    tot_labor = sum(i["unit_price"] * i["quantity"] for i in all_items if i["item_type"] == "LABOR")
    tot_parts = sum(i["unit_price"] * i["quantity"] for i in all_items if i["item_type"] == "PART")
    tot_tax = sum((i["unit_price"] * i["quantity"]) * ((i["tax_rate"] or 0.0) / 100.0) for i in all_items)
    tot_grand = round(tot_labor + tot_parts + tot_tax, 2)
    cursor.execute("UPDATE job_cards SET total_labor = ?, total_parts = ?, grand_total = ? WHERE id = ?", (tot_labor, tot_parts, tot_grand, job_id))

    # Auto-sync to linked invoice if already billed
    sync_job_card_to_invoice(cursor, job_id)

    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

@app.post("/api/job-cards/{job_id}/items/{item_id}/delete")
async def delete_job_card_item(job_id: str, item_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT item_type, item_id, quantity FROM job_items WHERE id = ? AND job_card_id = ?", (item_id, job_id))
    del_row = cursor.fetchone()
    if del_row and del_row["item_type"] == "PART" and del_row["item_id"]:
        cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ?", (del_row["quantity"], del_row["item_id"]))
    cursor.execute("DELETE FROM job_items WHERE id = ? AND job_card_id = ?", (item_id, job_id))
    
    # Recalculate job totals
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    all_items = [dict(r) for r in cursor.fetchall()]
    tot_labor = sum(i["unit_price"] * i["quantity"] for i in all_items if i["item_type"] == "LABOR")
    tot_parts = sum(i["unit_price"] * i["quantity"] for i in all_items if i["item_type"] == "PART")
    tot_tax = sum((i["unit_price"] * i["quantity"]) * ((i["tax_rate"] or 0.0) / 100.0) for i in all_items)
    tot_grand = round(tot_labor + tot_parts + tot_tax, 2)
    cursor.execute("UPDATE job_cards SET total_labor = ?, total_parts = ?, grand_total = ? WHERE id = ?", (tot_labor, tot_parts, tot_grand, job_id))

    # Auto-sync to linked invoice if already billed
    sync_job_card_to_invoice(cursor, job_id)

    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

@app.post("/api/job-cards/{job_id}/verify-edit-pin")
async def verify_job_card_edit_pin(job_id: str, payload: Dict[str, Any]):
    pin = payload.get("pin", "")
    workshop = get_current_workshop()
    if not verify_master_pin(pin, workshop.get("master_pin", "1234")):
        raise HTTPException(status_code=403, detail="Invalid Master Security PIN")
    return {"success": True}

@app.post("/api/job-cards/{job_id}/delete")
async def delete_job_card_with_pin(job_id: str, payload: Dict[str, Any]):
    pin = payload.get("pin", "")
    workshop = get_current_workshop()
    if not verify_master_pin(pin, workshop.get("master_pin", "1234")):
        raise HTTPException(status_code=403, detail="Invalid Master Security PIN")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_items WHERE job_card_id = ?", (job_id,))
    cursor.execute("DELETE FROM job_cards WHERE id = ?", (job_id,))
    db.log_audit("DELETE_JOB_CARD", "job_cards", job_id, f"Deleted job card {job_id} using Master PIN", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/customers/dues-check")
async def check_customer_dues(request: Request, phone: Optional[str] = None, customer_name: Optional[str] = None, vehicle_reg_no: Optional[str] = None):
    """Check if customer/vehicle has previous unpaid Khata dues or unpaid invoices, strictly isolated per workshop tenant"""
    tenant_id = get_current_tenant_id(request)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    dues_amount = 0.0
    cust = None
    unpaid_invoices = []
    
    clean_phone = (phone or "").strip()
    clean_veh = (vehicle_reg_no or "").strip().upper()

    if clean_phone:
        cursor.execute("SELECT * FROM customers WHERE phone = ? AND tenant_id = ? LIMIT 1", (clean_phone, tenant_id))
        c_row = cursor.fetchone()
        if c_row:
            cust = dict(c_row)
            dues_amount += float(cust.get("khata_balance") or 0.0)
            
        cursor.execute("SELECT * FROM invoices WHERE customer_phone = ? AND tenant_id = ? AND balance_due > 0 AND payment_status != 'CANCELLED'", (clean_phone, tenant_id))
        unpaid_invoices = [dict(r) for r in cursor.fetchall()]
        
    elif clean_veh:
        cursor.execute("SELECT * FROM vehicles WHERE reg_number = ? AND tenant_id = ? LIMIT 1", (clean_veh, tenant_id))
        v_row = cursor.fetchone()
        if v_row and v_row.get("customer_phone"):
            c_phone = v_row["customer_phone"].strip()
            cursor.execute("SELECT * FROM customers WHERE phone = ? AND tenant_id = ? LIMIT 1", (c_phone, tenant_id))
            c_row = cursor.fetchone()
            if c_row:
                cust = dict(c_row)
                dues_amount += float(cust.get("khata_balance") or 0.0)
                
            cursor.execute("SELECT * FROM invoices WHERE (vehicle_reg_no = ? OR customer_phone = ?) AND tenant_id = ? AND balance_due > 0 AND payment_status != 'CANCELLED'", (clean_veh, c_phone, tenant_id))
            unpaid_invoices = [dict(r) for r in cursor.fetchall()]

    conn.close()
    
    inv_dues = sum(float(inv.get("balance_due") or 0.0) for inv in unpaid_invoices)
    total_dues = max(dues_amount, inv_dues)
    
    return {
        "has_dues": total_dues > 0,
        "dues_amount": round(total_dues, 2),
        "customer": cust,
        "unpaid_invoices": unpaid_invoices
    }


@app.post("/api/job-cards/{job_id}/regenerate-invoice")
async def regenerate_job_invoice(job_id: str):
    """Regenerate existing linked invoice for a job card with updated charges, keeping same invoice number"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? AND payment_status != 'CANCELLED' ORDER BY created_at DESC LIMIT 1", (job_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="No linked invoice found for this job card to regenerate. Generate a new bill first.")
        
    sync_job_card_to_invoice(cursor, job_id)
    conn.commit()
    
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (inv["id"],))
    updated_inv = dict(cursor.fetchone())
    conn.close()
    
    return {
        "success": True,
        "invoice_id": updated_inv["id"],
        "invoice_number": updated_inv["invoice_number"],
        "grand_total": updated_inv["grand_total"],
        "message": f"Bill #{updated_inv['invoice_number']} updated successfully with revised Job Card charges!"
    }


@app.post("/api/job-cards/{job_id}/generate-proforma")
async def generate_job_proforma(request: Request, job_id: str):
    """Generate or update Proforma Service Estimate (Pre-Bill) for a job card"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    j_row = cursor.fetchone()
    if not j_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job Card not found")
    job = dict(j_row)
    if job.get("tenant_id"):
        tenant_id = job["tenant_id"]
    
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    job_items = [dict(r) for r in cursor.fetchall()]
    
    workshop = get_current_workshop(request=request, tenant_id=tenant_id)
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    now_ist = get_ist_now_str()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? AND invoice_type = 'PROFORMA' AND tenant_id = ? LIMIT 1", (job_id, tenant_id))
    existing_prof = cursor.fetchone()
    
    subtotal_labor = sum(float(ji["unit_price"] or 0) * int(ji["quantity"] or 1) for ji in job_items if ji.get("item_type") == "LABOR")
    subtotal_parts = sum(float(ji["unit_price"] or 0) * int(ji["quantity"] or 1) for ji in job_items if ji.get("item_type") == "PART")
    taxable_subtotal = subtotal_labor + subtotal_parts
    tax_total = sum((float(ji["unit_price"] or 0) * int(ji["quantity"] or 1)) * (float(ji.get("tax_rate") or 0.0) / 100.0) for ji in job_items)
    tax_total = round(tax_total, 2)
    grand_total = round(taxable_subtotal + tax_total, 2)
    
    if existing_prof:
        prof_id = existing_prof["id"]
        prof_number = existing_prof["invoice_number"]
        upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), grand_total, f"Est_{prof_number}")
        
        cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (prof_id,))
        cursor.execute("""
        UPDATE invoices SET
            subtotal_labor = ?, subtotal_parts = ?, taxable_subtotal = ?,
            tax_total = ?, grand_total = ?, balance_due = ?, upi_payment_link = ?, updated_at = ?
        WHERE id = ?
        """, (subtotal_labor, subtotal_parts, taxable_subtotal, tax_total, grand_total, grand_total, upi_link, now_ist, prof_id))
    else:
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE invoice_type = 'PROFORMA' AND tenant_id = ?", (tenant_id,))
        cnt = cursor.fetchone()[0] + 1
        prof_number = f"EST-2026-{cnt:03d}"
        prof_id = f"prof_{uuid.uuid4().hex[:8]}"
        upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), grand_total, f"Est_{prof_number}")
        
        cursor.execute("""
        INSERT INTO invoices (
            id, tenant_id, invoice_number, invoice_date, invoice_type, job_card_id, job_number,
            customer_name, customer_phone, vehicle_reg_no, vehicle_make_model, odometer,
            subtotal_labor, subtotal_parts, taxable_subtotal, tax_total, grand_total,
            amount_paid, balance_due, payment_status, payment_mode, upi_payment_link, created_at
        ) VALUES (?, ?, ?, ?, 'PROFORMA', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 'UNPAID', 'UPI', ?, ?)
        """, (
            prof_id, tenant_id, prof_number, today_str, job_id, job["job_number"],
            job["customer_name"], job["customer_phone"], job["vehicle_reg_no"], job["vehicle_make_model"], job.get("odometer", 0),
            subtotal_labor, subtotal_parts, taxable_subtotal, tax_total, grand_total, grand_total, upi_link, now_ist
        ))
        
    for ji in job_items:
        ii_id = f"ii_{uuid.uuid4().hex[:8]}"
        qty = int(ji.get("quantity") or 1)
        u_price = float(ji.get("unit_price") or 0.0)
        t_rate = float(ji.get("tax_rate") or 0.0)
        line_base = round(qty * u_price, 2)
        line_tot = round(line_base + (line_base * t_rate / 100.0), 2)
        cursor.execute("""
        INSERT INTO invoice_items (id, invoice_id, item_type, item_id, name, barcode, hsn_sac, quantity, unit_price, tax_rate, taxable_amount, total_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ii_id, prof_id, ji.get("item_type"), ji.get("item_id"), ji.get("name"), ji.get("barcode"), ji.get("hsn_code") or "8536", qty, u_price, t_rate, line_base, line_tot))
        
    db.log_audit("GENERATE_PROFORMA", "invoices", prof_id, f"Generated proforma estimate #{prof_number} (₹{grand_total:.2f}) for job {job['job_number']}", cursor=cursor)
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "proforma_id": prof_id,
        "proforma_number": prof_number,
        "grand_total": grand_total,
        "message": f"Proforma Estimate #{prof_number} generated successfully!"
    }


@app.get("/api/proforma/{proforma_id}/pdf")
async def download_proforma_pdf(proforma_id: str):
    """Generate printable PDF for Proforma Service Estimate"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ? OR job_card_id = ? ORDER BY created_at DESC LIMIT 1", (proforma_id, proforma_id))
    prof_row = cursor.fetchone()
    if not prof_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Proforma Estimate not found")
    proforma = dict(prof_row)
    
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (proforma["id"],))
    proforma["items"] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    workshop = get_current_workshop(tenant_id=proforma.get("tenant_id"))
    pdf_bytes = generate_proforma_pdf_bytes(proforma, workshop)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Proforma_{proforma.get('invoice_number') or proforma_id}.pdf"}
    )


@app.get("/api/job-cards/{job_id}/whatsapp-proforma-link")
async def get_job_proforma_whatsapp_link(request: Request, job_id: str):
    """Generate WhatsApp Work Complete message with Proforma Estimate & UPI/Bank details"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job Card not found")
    job = dict(job_row)
    
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? ORDER BY created_at DESC LIMIT 1", (job_id,))
    prof_row = cursor.fetchone()
    conn.close()
    
    if not prof_row:
        await generate_job_proforma(job_id)
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? ORDER BY created_at DESC LIMIT 1", (job_id,))
        prof_row = cursor.fetchone()
        conn.close()
        
    proforma = dict(prof_row)
    workshop = get_current_workshop()
    base_url = get_base_url(request)
    public_url = f"{base_url}/view/proforma/{proforma['id']}"
    lang = workshop.get("language", "en")
    
    msg = format_proforma_whatsapp_message(
        workshop_name=workshop["name"],
        proforma_number=proforma["invoice_number"],
        customer_name=job["customer_name"],
        vehicle_reg_no=job["vehicle_reg_no"],
        vehicle_make_model=job["vehicle_make_model"],
        grand_total=proforma["grand_total"],
        public_proforma_url=public_url,
        upi_payment_link=proforma.get("upi_payment_link", ""),
        bank_name=workshop.get("bank_name", "State Bank of India"),
        bank_account_no=workshop.get("bank_account_no", "39876543210"),
        bank_ifsc=workshop.get("bank_ifsc", "SBIN0001234"),
        upi_id=workshop.get("upi_id", "sparkautoworkshop@okaxis"),
        workshop_phone=workshop["phone"],
        lang=lang
    )
    
    wa_url = generate_wa_me_url(job["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}


@app.post("/api/job-cards/{job_id}/convert-proforma-to-invoice")
async def convert_proforma_to_final_tax_invoice(request: Request, job_id: str, payment_mode: str = Form("UPI"), amount_paid: Optional[float] = Form(None)):
    """Convert Proforma Estimate to official Tax Invoice (INV-2026-XXX) and mark as PAID"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? ORDER BY created_at DESC LIMIT 1", (job_id,))
    prof_row = cursor.fetchone()
    if not prof_row:
        conn.close()
        raise HTTPException(status_code=404, detail="No Proforma Estimate or linked bill found to convert.")
        
    prof = dict(prof_row)
    if prof.get("tenant_id"):
        tenant_id = prof["tenant_id"]
    now_ist = get_ist_now_str()
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if prof["invoice_type"] != "PROFORMA":
        new_tax_inv_no = prof["invoice_number"]
    else:
        cursor.execute("SELECT COUNT(*) FROM invoices WHERE invoice_type != 'PROFORMA' AND tenant_id = ?", (tenant_id,))
        cnt = cursor.fetchone()[0] + 1
        new_tax_inv_no = f"INV-2026-{cnt:03d}"
    
    g_total = float(prof["grand_total"] or 0.0)
    paid = float(amount_paid) if amount_paid is not None else g_total
    bal_due = max(0.0, g_total - paid)
    pay_status = "PAID" if bal_due <= 0 else ("PARTIAL" if paid > 0 else "UNPAID")
    
    cursor.execute("""
    UPDATE invoices SET
        invoice_number = ?, invoice_type = 'JOB_SERVICE', payment_status = ?,
        amount_paid = ?, balance_due = ?, payment_mode = ?, updated_at = ?
    WHERE id = ?
    """, (new_tax_inv_no, pay_status, paid, bal_due, payment_mode, now_ist, prof["id"]))
    
    cursor.execute("UPDATE job_cards SET status = 'COMPLETED', completed_at = COALESCE(completed_at, ?) WHERE id = ?", (now_ist, job_id))
    
    if paid > 0:
        pay_id = f"pay_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO payments (id, tenant_id, invoice_id, amount, payment_mode, payment_date, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (pay_id, tenant_id, prof["id"], paid, payment_mode, today_str, f"Payment for Tax Inv {new_tax_inv_no}", now_ist))

        # Update bank account / cash drawer
        cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
        p_acc = cursor.fetchone()
        if p_acc:
            cursor.execute("UPDATE bank_accounts SET current_balance = current_balance + ? WHERE id = ?", (paid, p_acc["id"]))
        elif payment_mode == "CASH":
            cursor.execute("UPDATE bank_accounts SET current_balance = current_balance + ? WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (paid, tenant_id))
        
    db.log_audit("CONVERT_PROFORMA_TO_TAX_INVOICE", "invoices", prof["id"], f"Converted Proforma to Tax Invoice #{new_tax_inv_no} (Paid: ₹{paid:.2f})", cursor=cursor)
    conn.commit()
    conn.close()
    
    return {
        "success": True,
        "invoice_id": prof["id"],
        "invoice_number": new_tax_inv_no,
        "payment_status": pay_status,
        "message": f"Tax Invoice #{new_tax_inv_no} generated successfully!"
    }


@app.get("/api/job-cards/{job_id}/create-invoice")
@app.post("/api/job-cards/{job_id}/create-invoice")
async def convert_job_card_to_invoice(job_id: str):
    """Redirect to manual billing page pre-filled with this job card's customer & parts info"""
    return RedirectResponse(url=f"/billing?from_job={job_id}", status_code=303)

# =========================================================
# 💳 BILLING, BARCODE SCAN POS & INVOICES
# =========================================================

@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request, from_job: Optional[str] = Query(None), edit_invoice: Optional[str] = Query(None)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    prefill_job = None
    editing_invoice = None
    existing_linked_invoice = None
    prefill_items_json = "[]"
    
    if edit_invoice:
        cursor.execute("SELECT * FROM invoices WHERE id = ? AND tenant_id = ?", (edit_invoice, tenant_id))
        inv_r = cursor.fetchone()
        if inv_r:
            cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (edit_invoice,))
            inv_items = [dict(r) for r in cursor.fetchall()]
            editing_invoice = dict(inv_r)
            editing_invoice["items"] = inv_items
            prefill_items_json = json.dumps(inv_items, default=str)
    elif from_job:
        cursor.execute("SELECT * FROM job_cards WHERE id = ? AND tenant_id = ?", (from_job, tenant_id))
        job_row = cursor.fetchone()
        if job_row:
            cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? AND payment_status != 'CANCELLED' AND tenant_id = ? ORDER BY created_at DESC LIMIT 1", (from_job, tenant_id))
            eli = cursor.fetchone()
            if eli:
                existing_linked_invoice = dict(eli)
                
            cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (from_job,))
            job_items = [dict(r) for r in cursor.fetchall()]
            prefill_job = {
                "job": dict(job_row),
                "items": job_items
            }
            prefill_items_json = json.dumps(job_items, default=str)

    cursor.execute("SELECT * FROM inventory_items WHERE tenant_id = ? ORDER BY part_name", (tenant_id,))
    inventory_items = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM invoices WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 50", (tenant_id,))
    invoices = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
    SELECT c.name, c.phone, v.reg_number as vehicle_reg_no, v.make_model as vehicle_make_model
    FROM customers c
    LEFT JOIN vehicles v ON c.id = v.customer_id
    WHERE c.tenant_id = ?
    ORDER BY c.name ASC
    """, (tenant_id,))
    customers = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT gst_slabs FROM workshop_profile WHERE tenant_id = ? OR id = ?", (tenant_id, tenant_id))
    prof_row = cursor.fetchone()
    gst_slabs_list = ["0", "5", "12", "18", "28"]
    if prof_row and prof_row["gst_slabs"]:
        try:
            gst_slabs_list = json.loads(prof_row["gst_slabs"])
        except Exception:
            pass

    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="billing.html",
        context={
            "active_page": "billing",
            "inventory_items": inventory_items,
            "invoices": invoices,
            "customers": customers,
            "gst_slabs_list": gst_slabs_list,
            "prefill_job": prefill_job,
            "editing_invoice": editing_invoice,
            "existing_linked_invoice": existing_linked_invoice,
            "prefill_items_json": prefill_items_json,
            "from_job": from_job
        }
    )

@app.post("/api/invoices/verify-pin")
async def verify_invoice_pin(payload: Dict[str, Any]):
    pin = payload.get("pin", "")
    workshop = get_current_workshop()
    if not verify_master_pin(pin, workshop.get("master_pin", "1234")):
        raise HTTPException(status_code=403, detail="Invalid Master Security PIN")
    return {"success": True}

@app.get("/api/invoices/{invoice_id}")
async def get_invoice_detail(invoice_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = dict(inv)
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    invoice["items"] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"success": True, "invoice": invoice}

@app.post("/api/invoices")
@app.post("/api/invoices/{invoice_id}/edit")
@app.put("/api/invoices/{invoice_id}")
async def save_or_update_pos_invoice(request: Request, payload: Dict[str, Any], invoice_id: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    editing_id = invoice_id or payload.get("editing_invoice_id")
    workshop = get_current_workshop(request)
    now_ist = get_ist_now_str()
    today_str = get_ist_today_str()
    
    items = payload.get("items", [])
    if not items and not editing_id:
        conn.close()
        raise HTTPException(status_code=422, detail="Invoice must contain at least one line item.")

    # Validate numeric types to prevent 500 crashes
    try:
        for itm in items:
            float(itm.get("unit_price") or 0.0)
            int(itm.get("quantity") or 1)
            float(itm.get("tax_rate") or 0.0)
    except (ValueError, TypeError) as e:
        conn.close()
        raise HTTPException(status_code=422, detail=f"Invalid numeric input in line items: {str(e)}")

    # Check stock availability for physical parts
    for itm in items:
        if itm.get("item_type") == "PART" and itm.get("item_id") and not itm.get("already_deducted"):
            req_qty = int(itm.get("quantity") or 1)
            cursor.execute("SELECT part_name, stock_qty FROM inventory_items WHERE id = ?", (itm["item_id"],))
            stk_row = cursor.fetchone()
            if stk_row and stk_row["stock_qty"] < req_qty:
                conn.close()
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for '{stk_row['part_name']}'. In stock: {stk_row['stock_qty']}, Requested: {req_qty}"
                )

    subtotal_labor = sum((float(i.get("unit_price") or 0.0)) * (int(i.get("quantity") or 1)) for i in items if i.get("item_type") == "LABOR")
    subtotal_parts = sum((float(i.get("unit_price") or 0.0)) * (int(i.get("quantity") or 1)) for i in items if i.get("item_type") == "PART")
    taxable_subtotal = subtotal_labor + subtotal_parts
    
    is_interstate = 1 if payload.get("is_interstate") else 0
    
    total_tax = 0.0
    for i in items:
        u_p = float(i.get("unit_price") or 0.0)
        u_q = int(i.get("quantity") or 1)
        t_r = float(i.get("tax_rate") or 0.0)
        total_tax += (u_p * u_q) * (t_r / 100.0)
    total_tax = round(total_tax, 2)
    
    if is_interstate:
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = total_tax
    else:
        cgst_total = round(total_tax / 2.0, 2)
        sgst_total = round(total_tax - cgst_total, 2)
        igst_total = 0.0
        
    discount = float(payload.get("discount_amount", 0.0))
    raw_grand_total = max(0.0, (subtotal_labor + subtotal_parts + total_tax) - discount)
    rounded_grand_total = float(round(raw_grand_total))
    round_off = round(rounded_grand_total - raw_grand_total, 2)
    grand_total = rounded_grand_total

    # Amount paid: if passed, use it; else default to rounded grand total
    amount_paid_raw = payload.get("amount_paid")
    amount_paid = float(amount_paid_raw) if (amount_paid_raw is not None and str(amount_paid_raw).strip() != "") else grand_total
    balance_due = max(0.0, grand_total - amount_paid)
    payment_status = "PAID" if balance_due <= 0 else ("PARTIAL" if amount_paid > 0 else "UNPAID")
    
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    pay_for_qr = balance_due if balance_due > 0 else grand_total
    
    job_card_id = payload.get("job_card_id")
    job_number = payload.get("job_number")

    cust_phone = (payload.get("customer_phone") or "").strip()
    cust_name = (payload.get("customer_name") or "Walk-in").strip()
    cust_addr = (payload.get("customer_address") or "").strip()
    cust_gstin = (payload.get("customer_gstin") or "").strip()
    cust_id = None

    tenant_id = get_current_tenant_id(request)

    try:
        if cust_phone:
            cursor.execute("SELECT id, khata_balance FROM customers WHERE phone = ? AND tenant_id = ?", (cust_phone, tenant_id))
            c_row = cursor.fetchone()
            if c_row:
                cust_id = c_row["id"]
                if balance_due > 0 and not editing_id:
                    cursor.execute("UPDATE customers SET total_visits = total_visits + 1, khata_balance = khata_balance + ? WHERE id = ?", (balance_due, cust_id))
                else:
                    cursor.execute("UPDATE customers SET total_visits = total_visits + 1 WHERE id = ?", (cust_id,))
            else:
                cust_id = f"cust_{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                INSERT OR REPLACE INTO customers (id, tenant_id, name, phone, address, gstin, total_visits, khata_balance, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                """, (cust_id, tenant_id, cust_name, cust_phone, cust_addr, cust_gstin, balance_due, now_ist))

        veh_reg = (payload.get("vehicle_reg_no") or "").strip().upper()
        if veh_reg:
            cursor.execute("SELECT id FROM vehicles WHERE reg_number = ? AND tenant_id = ?", (veh_reg, tenant_id))
            v_row = cursor.fetchone()
            if not v_row:
                v_id = f"veh_{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                INSERT OR REPLACE INTO vehicles (id, tenant_id, reg_number, customer_id, customer_name, customer_phone, make_model, odometer, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """, (v_id, tenant_id, veh_reg, cust_id, cust_name, cust_phone, payload.get("vehicle_make_model", "General"), now_ist))
        
        if editing_id:
            # --- UPDATE EXISTING INVOICE (Same invoice # and id preserved) ---
            cursor.execute("SELECT * FROM invoices WHERE id = ?", (editing_id,))
            old_inv = cursor.fetchone()
            if not old_inv:
                conn.close()
                raise HTTPException(status_code=404, detail="Existing invoice not found to update")
                
            inv_number = old_inv["invoice_number"]
            inv_id = editing_id
            upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), pay_for_qr, f"Inv_{inv_number}")
            
            # 1. Restore stock from previous invoice items
            cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (editing_id,))
            old_items = cursor.fetchall()
            for oi in old_items:
                if oi["item_type"] == "PART" and oi["item_id"]:
                    cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ?", (oi["quantity"], oi["item_id"]))
                    log_id = f"stk_{uuid.uuid4().hex[:8]}"
                    cursor.execute("""
                    INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, reference_id, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, COALESCE((SELECT stock_qty FROM inventory_items WHERE id = ?), 0), 'EDIT_RESTORE', ?, ?, ?)
                    """, (log_id, oi["item_id"], oi["name"], oi["barcode"], int(oi["quantity"]), oi["item_id"], inv_number, f"Restored during edit of {inv_number}", now_ist))
            
            # 2. Clear old items
            cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (editing_id,))
            
            # 3. Update invoice record
            cursor.execute("""
            UPDATE invoices SET
                customer_name = ?, customer_phone = ?, vehicle_reg_no = ?,
                subtotal_labor = ?, subtotal_parts = ?, taxable_subtotal = ?,
                cgst_total = ?, sgst_total = ?, igst_total = ?, tax_total = ?,
                discount_amount = ?, round_off = ?, grand_total = ?, amount_paid = ?, balance_due = ?,
                payment_status = ?, payment_mode = ?, is_interstate = ?,
                upi_payment_link = ?, updated_at = ?
            WHERE id = ?
            """, (
                cust_name, cust_phone,
                veh_reg,
                subtotal_labor, subtotal_parts, taxable_subtotal,
                cgst_total, sgst_total, igst_total, total_tax,
                discount, round_off, grand_total, amount_paid, balance_due,
                payment_status, payload.get("payment_mode", "UPI"), is_interstate,
                upi_link, now_ist, editing_id
            ))
            
            # 4. Adjust customer khata balance if balance changed
            old_bal = float(old_inv["balance_due"] or 0.0)
            bal_diff = balance_due - old_bal
            if bal_diff != 0 and cust_phone:
                cursor.execute("UPDATE customers SET khata_balance = MAX(0, khata_balance + ?) WHERE phone = ? AND tenant_id = ?", (bal_diff, cust_phone, tenant_id))
                
            db.log_audit("EDIT_INVOICE", "invoices", editing_id, f"Updated bill #{inv_number} (New Total: ₹{grand_total:.2f}, Status: {payment_status})", cursor=cursor)
        else:
            # --- CREATE NEW INVOICE ---
            cursor.execute("SELECT COUNT(*) FROM invoices WHERE tenant_id = ?", (tenant_id,))
            cnt = cursor.fetchone()[0] + 1
            inv_number = f"INV-2026-{cnt:03d}"
            cursor.execute("SELECT id FROM invoices WHERE invoice_number = ? AND tenant_id = ?", (inv_number, tenant_id))
            while cursor.fetchone():
                cnt += 1
                inv_number = f"INV-2026-{cnt:03d}"
            inv_id = f"inv_{uuid.uuid4().hex[:8]}"
            upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), pay_for_qr, f"Inv_{inv_number}")

            cursor.execute("""
            INSERT INTO invoices (
                id, tenant_id, invoice_number, invoice_date, invoice_type, job_card_id, job_number,
                customer_name, customer_phone, vehicle_reg_no,
                subtotal_labor, subtotal_parts, taxable_subtotal,
                cgst_total, sgst_total, igst_total, tax_total, discount_amount,
                round_off, grand_total, amount_paid, balance_due, payment_status, payment_mode,
                is_interstate, upi_payment_link, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inv_id, tenant_id, inv_number, today_str, payload.get("invoice_type", "JOB_SERVICE" if job_card_id else "COUNTER_SALE"),
                job_card_id, job_number,
                cust_name, cust_phone,
                veh_reg,
                subtotal_labor, subtotal_parts, taxable_subtotal,
                cgst_total, sgst_total, igst_total, total_tax, discount,
                round_off, grand_total, amount_paid, balance_due, payment_status,
                payload.get("payment_mode", "UPI"), is_interstate, upi_link, now_ist
            ))

            # Record payment if amount_paid > 0
            if amount_paid > 0:
                pay_id = f"pay_{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                INSERT INTO payments (id, tenant_id, invoice_id, customer_id, amount, payment_mode, payment_date, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (pay_id, tenant_id, inv_id, cust_id, amount_paid, payload.get("payment_mode", "UPI"), today_str, f"Initial payment for {inv_number}", now_ist))

                # Update bank account / cash register balance
                cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
                p_acc = cursor.fetchone()
                if p_acc:
                    cursor.execute("UPDATE bank_accounts SET current_balance = current_balance + ? WHERE id = ?", (amount_paid, p_acc["id"]))
                elif payload.get("payment_mode") == "CASH":
                    cursor.execute("UPDATE bank_accounts SET current_balance = current_balance + ? WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (amount_paid, tenant_id))

            db.log_audit("CREATE_INVOICE", "invoices", inv_id, f"Created bill #{inv_number} (₹{grand_total:.2f}, Status: {payment_status})", cursor=cursor)

        # Insert items and apply stock deductions
        for i in items:
            inv_item_id = f"ii_{uuid.uuid4().hex[:8]}"
            u_price = float(i.get("unit_price") or 0.0)
            u_qty = int(i.get("quantity") or 1)
            line_base = u_price * u_qty
            t_rate = float(i.get("tax_rate") or 0.0)
            line_tax = line_base * (t_rate / 100.0)
            line_total = line_base + line_tax

            unit_str = str(i.get("unit") or ("hrs" if i.get("item_type") == "LABOR" else "pcs")).lower()
            part_no = str(i.get("part_number") or "").strip()

            if is_interstate:
                c_rate, s_rate, i_rate = 0.0, 0.0, t_rate
                c_amt, s_amt, i_amt = 0.0, 0.0, line_tax
            else:
                c_rate, s_rate, i_rate = (t_rate / 2.0), (t_rate / 2.0), 0.0
                c_amt, s_amt, i_amt = (line_tax / 2.0), (line_tax / 2.0), 0.0

            cursor.execute("""
            INSERT INTO invoice_items (
                id, invoice_id, item_type, item_id, barcode, name, hsn_sac,
                quantity, unit_price, tax_rate, taxable_amount, total_price,
                unit, part_number, cgst_rate, sgst_rate, igst_rate, cgst_amount, sgst_amount, igst_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                inv_item_id, inv_id, i.get("item_type", "PART"), i.get("item_id"),
                i.get("barcode"), i.get("name", "Item"), i.get("hsn_sac", "8536"),
                u_qty, u_price, t_rate,
                line_base, line_total,
                unit_str, part_no, c_rate, s_rate, i_rate, c_amt, s_amt, i_amt
            ))
            
            # Only deduct inventory for physical PART items!
            if i.get("item_type") == "PART" and i.get("item_id") and not i.get("already_deducted"):
                cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (u_qty, i["item_id"]))
                log_id = f"stk_{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, reference_id, notes, created_at)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT stock_qty FROM inventory_items WHERE id = ?), 0), 'SALE_OUT', ?, ?, ?)
                """, (log_id, i["item_id"], i.get("name"), i.get("barcode"), -u_qty, i["item_id"], inv_number, f"Billed in Invoice {inv_number}", now_ist))
                
        # If linked to job card, mark job card as COMPLETED
        if job_card_id:
            cursor.execute("UPDATE job_cards SET status = 'COMPLETED', completed_at = ? WHERE id = ?", (now_ist, job_card_id))

        conn.commit()
        conn.close()

        try:
            import supabase_sync
            supabase_sync.push_to_supabase("invoices", {
                "id": inv_id,
                "tenant_id": tenant_id,
                "invoice_number": inv_number,
                "invoice_date": today_str,
                "invoice_type": payload.get("invoice_type", "JOB_SERVICE" if job_card_id else "COUNTER_SALE"),
                "job_card_id": job_card_id,
                "job_number": job_number,
                "customer_name": cust_name,
                "customer_phone": cust_phone,
                "vehicle_reg_no": veh_reg,
                "subtotal_labor": subtotal_labor,
                "subtotal_parts": subtotal_parts,
                "taxable_subtotal": taxable_subtotal,
                "cgst_total": cgst_total,
                "sgst_total": sgst_total,
                "igst_total": igst_total,
                "tax_total": total_tax,
                "discount_amount": discount,
                "round_off": round_off,
                "grand_total": grand_total,
                "amount_paid": amount_paid,
                "balance_due": balance_due,
                "payment_status": payment_status,
                "payment_mode": payload.get("payment_mode", "UPI"),
                "created_at": now_ist
            })
        except Exception as e:
            print(f"[Supabase Invoice Push Error] {e}")

        return {"success": True, "invoice_id": inv_id, "invoice_number": inv_number, "is_updated": bool(editing_id)}
    except HTTPException:
        conn.rollback()
        conn.close()
        raise
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[POS Invoice Error] {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Bill generation error: {str(e)}")

@app.post("/api/invoices/{invoice_id}/cancel")
async def cancel_invoice_with_pin(request: Request, invoice_id: str, payload: Dict[str, Any]):
    pin = payload.get("pin", "")
    tenant_id = get_current_tenant_id(request)
    workshop = get_current_workshop(request=request, tenant_id=tenant_id)
    if not verify_master_pin(pin, workshop.get("master_pin", "1234")):
        raise HTTPException(status_code=403, detail="Invalid Master Security PIN")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    if inv.get("tenant_id"):
        tenant_id = inv["tenant_id"]
    
    if inv["payment_status"] == "CANCELLED":
        conn.close()
        return {"success": True, "message": "Invoice is already cancelled"}

    now_ist = get_ist_now_str()
    today_date = get_ist_today_str()
    invoice_number = inv["invoice_number"]

    # 1. Restore inventory stock for all parts in the invoice (Sales Return)
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    items = cursor.fetchall()
    restored_parts_count = 0
    for itm in items:
        if itm["item_type"] == "PART" and itm["item_id"]:
            cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ? AND tenant_id = ?", (itm["quantity"], itm["item_id"], tenant_id))
            log_id = f"stk_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO stock_logs (id, tenant_id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, reference_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'SALES_RETURN', ?, ?, ?)
            """, (log_id, tenant_id, itm["item_id"], itm["name"], itm["barcode"], int(itm["quantity"]), itm["item_id"], invoice_number, f"Sales Return / Bill {invoice_number} Cancelled", now_ist))
            restored_parts_count += 1

    # 2. Record Sales Return entry with proper columns matching schema
    sr_id = f"sr_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM sales_returns WHERE tenant_id = ?", (tenant_id,))
    cnt = cursor.fetchone()[0] + 1
    return_num = f"CN-2026-{cnt:03d}"
    try:
        cursor.execute("""
        INSERT INTO sales_returns (
            id, tenant_id, return_number, invoice_id, customer_name, item_id, name,
            quantity, unit_price, refund_amount, return_date, refund_mode, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sr_id, tenant_id, return_num, invoice_id, inv["customer_name"] or "Customer",
            "ALL", f"Sales Return for Bill #{invoice_number}", len(items),
            inv["grand_total"], inv["amount_paid"] or 0.0, today_date,
            inv["payment_mode"] or "CASH", "Invoice Cancelled & Stock Restored", now_ist
        ))
    except Exception as e:
        print(f"[Sales Return Insert Error on Cancel] {e}")

    # 3. If there was an unpaid balance on customer khata, deduct it
    bal = float(inv["balance_due"] or 0.0)
    if bal > 0 and inv["customer_phone"]:
        cursor.execute("UPDATE customers SET khata_balance = MAX(0, khata_balance - ?) WHERE phone = ? AND tenant_id = ?", (bal, inv["customer_phone"].strip(), tenant_id))

    # 4. If customer had paid, deduct refund from bank/cash account
    paid_amt = float(inv["amount_paid"] or 0.0)
    if paid_amt > 0:
        cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
        p_acc = cursor.fetchone()
        if p_acc:
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE id = ?", (paid_amt, p_acc["id"]))
        elif inv["payment_mode"] == "CASH":
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (paid_amt, tenant_id))

    # 5. Mark invoice status as CANCELLED
    cursor.execute("""
    UPDATE invoices SET payment_status = 'CANCELLED', status = 'CANCELLED',
    notes = COALESCE(notes, '') || ' [CANCELLED on ' || ? || ' - Sales Return Restocked]'
    WHERE id = ?
    """, (now_ist, invoice_id))

    # 6. If linked to job card, update job card status
    if inv["job_card_id"]:
        cursor.execute("UPDATE job_cards SET status = 'IN_PROGRESS' WHERE id = ?", (inv["job_card_id"],))

    db.log_audit("CANCEL_INVOICE", "invoices", invoice_id, f"Cancelled #{invoice_number} and processed Sales Return (+stock restored)", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Invoice #{invoice_number} cancelled and parts restored to inventory."}

@app.post("/api/invoices/{invoice_id}/record-payment")
async def record_invoice_payment(request: Request, invoice_id: str, payload: Dict[str, Any]):
    amount = float(payload.get("amount", 0.0))
    mode = payload.get("payment_mode", "UPI")
    notes = payload.get("notes", "")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    tenant_id = get_current_tenant_id(request)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    if inv.get("tenant_id"):
        tenant_id = inv["tenant_id"]

    old_paid = inv["amount_paid"] or 0.0
    new_paid = old_paid + amount
    grand_total = inv["grand_total"]
    new_balance = max(0.0, grand_total - new_paid)
    new_status = "PAID" if new_balance <= 0 else "PARTIAL"
    now_ist = get_ist_now_str()
    today_date = get_ist_today_str()

    # 1. Update invoice
    cursor.execute("""
    UPDATE invoices SET amount_paid = ?, balance_due = ?, payment_status = ?, payment_mode = ? WHERE id = ?
    """, (new_paid, new_balance, new_status, mode, invoice_id))

    # 2. Insert into payments table
    pay_id = f"pay_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO payments (id, tenant_id, invoice_id, amount, payment_mode, payment_date, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (pay_id, tenant_id, invoice_id, amount, mode, today_date, notes or f"Installment payment for {inv['invoice_number']}", now_ist))

    # 3. Update customer khata balance
    if inv["customer_phone"]:
        cursor.execute("UPDATE customers SET khata_balance = MAX(0.0, khata_balance - ?) WHERE phone = ? AND tenant_id = ?", (amount, inv["customer_phone"].strip(), tenant_id))

    # 4. Update bank account / cash register balance
    cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
    p_acc = cursor.fetchone()
    if p_acc:
        cursor.execute("UPDATE bank_accounts SET current_balance = current_balance + ? WHERE id = ?", (amount, p_acc["id"]))
    elif mode == "CASH":
        cursor.execute("UPDATE bank_accounts SET current_balance = current_balance + ? WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (amount, tenant_id))

    db.log_audit("RECORD_PAYMENT", "invoices", invoice_id, f"Recorded ₹{amount:.2f} via {mode}. New status: {new_status}", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True, "new_balance": new_balance, "new_status": new_status}

@app.post("/api/invoices/{invoice_id}/delete")
async def delete_invoice_with_pin(invoice_id: str, payload: Dict[str, Any]):
    pin = payload.get("pin", "")
    workshop = get_current_workshop()
    if not verify_master_pin(pin, workshop.get("master_pin", "1234")):
        raise HTTPException(status_code=403, detail="Invalid Master Security PIN")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    items = cursor.fetchall()
    for itm in items:
        if itm["item_type"] == "PART" and itm["item_id"]:
            cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ?", (itm["quantity"], itm["item_id"]))

    cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    cursor.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    db.log_audit("DELETE_INVOICE", "invoices", invoice_id, f"Deleted #{inv['invoice_number']} and restored stock", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True}

@app.get("/api/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv_row = cursor.fetchone()
    if not inv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = dict(inv_row)
    
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    invoice["items"] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    workshop = get_current_workshop(tenant_id=invoice.get("tenant_id"))
    pdf_bytes = generate_invoice_pdf_bytes(invoice, workshop)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Invoice_{invoice['invoice_number']}.pdf"}
    )

@app.get("/api/invoices/{invoice_id}/whatsapp-link")
async def get_invoice_whatsapp_link(request: Request, invoice_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv_row = cursor.fetchone()
    if not inv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    inv = dict(inv_row)
    conn.close()
    
    workshop = get_current_workshop()
    base_url = get_base_url(request)
    public_url = f"{base_url}/view/invoice/{invoice_id}"
    lang = workshop.get("language", "en")
    
    msg = format_invoice_whatsapp_message(
        workshop_name=workshop["name"],
        invoice_number=inv["invoice_number"],
        customer_name=inv["customer_name"],
        vehicle_reg_no=inv["vehicle_reg_no"] or "Counter",
        vehicle_make_model=inv["vehicle_make_model"] or "Vehicle",
        grand_total=inv["grand_total"],
        amount_paid=inv["amount_paid"],
        balance_due=inv["balance_due"],
        upi_payment_link=inv.get("upi_payment_link", ""),
        public_view_url=public_url,
        workshop_phone=workshop["phone"],
        lang=lang
    )
    
    wa_url = generate_wa_me_url(inv["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}

@app.get("/api/job-cards/{job_id}/whatsapp-link")
async def get_job_whatsapp_link(request: Request, job_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
    job = dict(job_row)
    conn.close()
    
    workshop = get_current_workshop()
    base_url = get_base_url(request)
    public_url = f"{base_url}/view/job/{job_id}"
    lang = workshop.get("language", "en")
    
    msg = format_job_status_whatsapp_message(
        workshop_name=workshop["name"],
        job_number=job["job_number"],
        status=job["status"],
        customer_name=job["customer_name"],
        vehicle_reg_no=job["vehicle_reg_no"],
        vehicle_make_model=job["vehicle_make_model"],
        technician_name=job["assigned_technician_name"] or "Team",
        notes=job.get("diagnosis_notes") or "",
        public_job_url=public_url,
        workshop_phone=workshop["phone"],
        lang=lang
    )
    
    wa_url = generate_wa_me_url(job["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}

@app.get("/api/invoices/{invoice_id}/khata-reminder-link")
async def get_khata_reminder_link(request: Request, invoice_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv_row = cursor.fetchone()
    if not inv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    inv = dict(inv_row)
    conn.close()

    workshop = get_current_workshop()
    lang = workshop.get("language", "en")
    base_url = str(request.base_url).rstrip('/')
    public_view_url = f"{base_url}/view/invoice/{inv['id']}"

    msg = format_khata_due_reminder_whatsapp_message(
        workshop_name=workshop["name"],
        customer_name=inv["customer_name"],
        due_amount=inv["balance_due"],
        upi_payment_link=inv.get("upi_payment_link", ""),
        workshop_phone=workshop["phone"],
        lang=lang,
        public_view_url=public_view_url
    )

    wa_url = generate_wa_me_url(inv["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}

# =========================================================
# 📦 INVENTORY, EXCEL BULK IMPORT & BARCODES
# =========================================================

@app.get("/inventory", response_class=HTMLResponse)
async def inventory_page(request: Request, category: Optional[str] = None, filter: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    query = "SELECT * FROM inventory_items WHERE tenant_id = ?"
    params = [tenant_id]
    
    if filter == "low":
        query += " AND stock_qty <= min_stock_alert"
    elif category:
        query += " AND category = ?"
        params.append(category)
        
    query += " ORDER BY category, part_name"
    cursor.execute(query, params)
    items = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT COUNT(*) FROM inventory_items WHERE tenant_id = ? AND stock_qty <= min_stock_alert", (tenant_id,))
    low_stock_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT DISTINCT category FROM inventory_items WHERE tenant_id = ? AND category IS NOT NULL", (tenant_id,))
    categories = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={
            "active_page": "inventory",
            "items": items,
            "categories": categories,
            "selected_category": category,
            "is_low_filter": filter == "low",
            "low_stock_count": low_stock_count,
            "workshop": get_current_workshop(request)
        }
    )

@app.get("/inventory/stock-audit-sheet", response_class=HTMLResponse)
async def stock_audit_sheet_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM inventory_items WHERE tenant_id = ? ORDER BY category, location_rack, part_name", (tenant_id,))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="stock_audit_sheet.html",
        context={
            "items": items,
            "workshop": get_current_workshop(request),
            "today_date": datetime.now().strftime("%d %b %Y")
        }
    )

@app.get("/api/inventory/template/excel")
async def download_inventory_excel_template():
    excel_bytes = generate_inventory_import_template()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=AutoVolt_Inventory_Import_Template.xlsx"}
    )

@app.post("/api/inventory/import/excel")
async def import_inventory_excel(request: Request, file: UploadFile = File(...)):
    file_bytes = await file.read()
    items, errors = parse_inventory_file(file_bytes, file.filename)
    
    if not items:
        err_msg = ", ".join(errors) if errors else "No valid items found in file."
        raise HTTPException(status_code=400, detail=f"Import failed: {err_msg}")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    imported_count = 0
    for itm in items:
        cursor.execute("SELECT id FROM inventory_items WHERE barcode = ? AND tenant_id = ?", (itm["barcode"], tenant_id))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
            UPDATE inventory_items SET
                part_name = ?, part_number = COALESCE(NULLIF(?, ''), part_number), category = ?, stock_qty = stock_qty + ?,
                cost_price = ?, selling_price = ?, tax_rate = ?, hsn_code = ?,
                unit = ?, warranty_months = ?, location_rack = ?, position_bin = COALESCE(NULLIF(?, ''), position_bin), updated_at = datetime('now')
            WHERE id = ? AND tenant_id = ?
            """, (
                itm["part_name"], itm.get("part_number", ""), itm["category"], itm["stock_qty"],
                itm["cost_price"], itm["selling_price"], itm["tax_rate"], itm["hsn_code"],
                itm["unit"], itm["warranty_months"], itm["location_rack"], itm.get("position_bin", ""), existing["id"], tenant_id
            ))
        else:
            item_id = f"item_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO inventory_items (
                id, tenant_id, part_name, part_number, sku, barcode, category, stock_qty, min_stock_alert,
                cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
                location_rack, position_bin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                item_id, tenant_id, itm["part_name"], itm.get("part_number", ""), itm["barcode"], itm["barcode"], itm["category"],
                itm["stock_qty"], itm["cost_price"], itm["selling_price"], itm["tax_rate"],
                itm["hsn_code"], itm["unit"], itm["warranty_months"], itm["location_rack"], itm.get("position_bin", "")
            ))
        imported_count += 1

    db.log_audit("BULK_EXCEL_IMPORT", "inventory_items", "bulk", f"Imported {imported_count} parts from {file.filename}", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/inventory", status_code=303)

@app.get("/api/inventory/scan/{barcode}")
async def scan_barcode_lookup(request: Request, barcode: str):
    tenant_id = get_current_tenant_id(request)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    clean_b = barcode.strip()
    cursor.execute("SELECT * FROM inventory_items WHERE (barcode = ? OR sku = ? OR part_number = ?) AND tenant_id = ?", (clean_b, clean_b, clean_b, tenant_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Barcode item not found")
    return dict(row)

@app.get("/api/inventory/barcode-svg/{barcode}")
async def get_barcode_svg_endpoint(barcode: str):
    svg = generate_barcode_svg(barcode)
    return {"barcode": barcode, "svg": svg}

@app.get("/barcode-labels", response_class=HTMLResponse)
async def barcode_labels_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM inventory_items WHERE tenant_id = ? ORDER BY part_name", (tenant_id,))
    inventory_items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for item in inventory_items:
        sp = float(item.get("selling_price") or 0.0)
        t_rate = float(item.get("tax_rate") if item.get("tax_rate") is not None else 18.0)
        item["mrp"] = round(sp * (1.0 + t_rate / 100.0), 2)
    
    return templates.TemplateResponse(
        request=request,
        name="barcode_labels.html",
        context={
            "active_page": "barcode_labels",
            "inventory_items": inventory_items
        }
    )

@app.post("/api/inventory")
async def add_inventory_item(
    request: Request,
    part_name: str = Form(...),
    barcode: str = Form(...),
    part_number: Optional[str] = Form(None),
    category: str = Form("Relays & Fuses"),
    stock_qty: int = Form(10),
    cost_price: float = Form(0.0),
    selling_price: float = Form(0.0),
    tax_rate: float = Form(18.0),
    hsn_code: str = Form("8536"),
    warranty_months: int = Form(0),
    location_rack: str = Form("Main"),
    position_bin: Optional[str] = Form("")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    item_id = f"item_{uuid.uuid4().hex[:8]}"
    clean_pn = (part_number or "").strip().upper()
    clean_rack = (location_rack or "Main").strip()
    clean_bin = (position_bin or "").strip()
    cursor.execute("""
    INSERT INTO inventory_items (
        id, tenant_id, part_name, part_number, sku, barcode, category, stock_qty, min_stock_alert,
        cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
        location_rack, position_bin, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 5, ?, ?, ?, ?, 'pcs', ?, ?, ?, datetime('now'), datetime('now'))
    """, (item_id, tenant_id, part_name, clean_pn, barcode, barcode, category, stock_qty, cost_price, selling_price, tax_rate, hsn_code, warranty_months, clean_rack, clean_bin))
    
    db.log_audit("ADD_INVENTORY_PART", "inventory_items", item_id, f"Added part: {part_name} (PN: {clean_pn}, Barcode: {barcode}, Rack: {clean_rack}, Pos: {clean_bin})", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/inventory", status_code=303)

@app.post("/api/inventory/adjust")
async def adjust_inventory_stock(
    item_id: str = Form(...),
    action_type: str = Form("PURCHASE"),
    change_qty: int = Form(...),
    pin: str = Form("1234")
):
    workshop = get_current_workshop()
    if not verify_master_pin(pin, workshop.get("master_pin", "1234")):
        raise HTTPException(status_code=403, detail="Invalid Master Security PIN. Stock adjustment not authorized.")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT stock_qty, part_name, barcode, cost_price FROM inventory_items WHERE id = ?", (item_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")
        
    old_qty = row["stock_qty"]
    new_qty = old_qty + change_qty
    cursor.execute("UPDATE inventory_items SET stock_qty = ?, updated_at = datetime('now') WHERE id = ?", (new_qty, item_id))
    
    log_id = f"stk_{uuid.uuid4().hex[:8]}"
    now_ist = get_ist_now_str()
    cursor.execute("""
    INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, unit_cost, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (log_id, item_id, row["part_name"], row["barcode"], change_qty, new_qty, action_type, row["cost_price"], now_ist))
    
    db.log_audit("ADJUST_STOCK", "inventory_items", item_id, f"Adjusted stock for {row['part_name']} by {change_qty:+d} (New: {new_qty}) using Master PIN", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/inventory", status_code=303)

# =========================================================
# 👨‍🔧 TECHNICIANS, WAGES, ADVANCES & ATTENDANCE
# =========================================================

@app.get("/technicians", response_class=HTMLResponse)
async def technicians_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM technicians WHERE tenant_id = ? ORDER BY total_jobs DESC", (tenant_id,))
    technicians = [dict(row) for row in cursor.fetchall()]
    
    for t in technicians:
        t["advance_balance"] = t.get("current_advance_balance", 0.0)

    on_leave_count = sum(1 for t in technicians if t.get("is_on_leave") == 1)
    present_count = len(technicians) - on_leave_count
    total_advance_balance = sum(float(t.get("advance_balance") or 0.0) for t in technicians)

    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="technicians.html",
        context={
            "active_page": "technicians",
            "technicians": technicians,
            "total_staff": len(technicians),
            "present_count": present_count,
            "on_leave_count": on_leave_count,
            "total_advance_balance": total_advance_balance
        }
    )

@app.post("/api/technicians")
async def add_technician(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    role: str = Form("Senior Auto Electrician"),
    commission_pct: float = Form(10.0),
    notes: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    tech_id = f"tech_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO technicians (id, tenant_id, name, phone, role, commission_pct, status, is_on_leave, current_advance_balance, notes, total_jobs, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'Active', 0, 0.0, ?, 0, datetime('now'))
    """, (tech_id, tenant_id, name, phone, role, commission_pct, notes))
    db.log_audit("ADD_TECHNICIAN", "technicians", tech_id, f"Added staff: {name} ({role})", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

@app.post("/api/technicians/{tech_id}/toggle-leave")
async def toggle_technician_leave(request: Request, tech_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT is_on_leave, name, tenant_id FROM technicians WHERE id = ?", (tech_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")

    if row["tenant_id"]:
        tenant_id = row["tenant_id"]

    new_leave_state = 0 if row["is_on_leave"] == 1 else 1
    cursor.execute("UPDATE technicians SET is_on_leave = ? WHERE id = ? AND tenant_id = ?", (new_leave_state, tech_id, tenant_id))
    
    att_id = f"att_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    att_status = "ON_LEAVE" if new_leave_state == 1 else "PRESENT"
    cursor.execute("""
    INSERT INTO attendance (id, tenant_id, technician_id, date, status, created_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (att_id, tenant_id, tech_id, today_str, att_status))

    db.log_audit("TOGGLE_LEAVE", "technicians", tech_id, f"{row['name']} marked as {att_status}", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True, "is_on_leave": bool(new_leave_state)}

@app.post("/api/technicians/advances")
async def record_technician_advance(
    request: Request,
    technician_id: str = Form(...),
    amount: float = Form(...),
    payment_mode: str = Form("CASH"),
    notes: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT name, tenant_id FROM technicians WHERE id = ?", (technician_id,))
    tech = cursor.fetchone()
    if not tech:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")

    if tech["tenant_id"]:
        tenant_id = tech["tenant_id"]

    adv_id = f"adv_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO employee_advances (id, tenant_id, technician_id, technician_name, amount, advance_date, status, payment_mode, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'OUTSTANDING', ?, ?, datetime('now'))
    """, (adv_id, tenant_id, technician_id, tech["name"], amount, today_str, payment_mode, notes))

    cursor.execute("UPDATE technicians SET current_advance_balance = current_advance_balance + ? WHERE id = ? AND tenant_id = ?", (amount, technician_id, tenant_id))

    # Deduct advance disbursed from bank/cash account
    if amount > 0:
        cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
        p_acc = cursor.fetchone()
        if p_acc:
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE id = ?", (amount, p_acc["id"]))
        elif payment_mode == "CASH":
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (amount, tenant_id))

    db.log_audit("STAFF_ADVANCE", "technicians", technician_id, f"Disbursed advance ₹{amount:.2f} to {tech['name']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

@app.post("/api/technicians/wages")
async def record_technician_wages(
    request: Request,
    technician_id: str = Form(...),
    base_wages: float = Form(4000.0),
    commission_amount: float = Form(0.0),
    advance_deducted: float = Form(0.0),
    payment_mode: str = Form("CASH")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT name, current_advance_balance, tenant_id FROM technicians WHERE id = ?", (technician_id,))
    tech = cursor.fetchone()
    if not tech:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")

    if tech["tenant_id"]:
        tenant_id = tech["tenant_id"]

    gross = base_wages + commission_amount
    net_paid = max(0.0, gross - advance_deducted)
    wage_id = f"wage_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    start_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO employee_wages (
        id, tenant_id, technician_id, technician_name, period_start, period_end,
        gross_amount, advance_deducted, net_paid, payment_date, payment_mode, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        wage_id, tenant_id, technician_id, tech["name"], start_str, today_str,
        gross, advance_deducted, net_paid, today_str, payment_mode
    ))

    if advance_deducted > 0:
        cursor.execute("UPDATE technicians SET current_advance_balance = MAX(0.0, current_advance_balance - ?) WHERE id = ? AND tenant_id = ?", (advance_deducted, technician_id, tenant_id))

    # Record wage payment into expenses table and adjust bank balance
    if net_paid > 0:
        exp_id = f"exp_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO expenses (id, tenant_id, title, category, amount, payment_mode, expense_date, paid_to, reference_no, created_at)
        VALUES (?, ?, ?, 'Staff Wages & Salary', ?, ?, ?, ?, ?, datetime('now'))
        """, (exp_id, tenant_id, f"Wages for {tech['name']}", net_paid, payment_mode, today_str, tech["name"], wage_id))

        cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
        p_acc = cursor.fetchone()
        if p_acc:
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE id = ?", (net_paid, p_acc["id"]))
        elif payment_mode == "CASH":
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (net_paid, tenant_id))

    db.log_audit("PAY_WAGES", "technicians", technician_id, f"Paid weekly wages ₹{net_paid:.2f} to {tech['name']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

@app.get("/api/technicians/{tech_id}/ledger")
async def get_technician_ledger(request: Request, tech_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM technicians WHERE id = ?", (tech_id,))
    tech = cursor.fetchone()
    if not tech:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")
    
    tech_data = dict(tech)
    if tech_data.get("tenant_id"):
        tenant_id = tech_data["tenant_id"]
    commission_pct = float(tech_data.get("commission_pct") or 0.0)

    # 1. Fetch Advances
    cursor.execute("""
        SELECT * FROM employee_advances 
        WHERE technician_id = ? AND tenant_id = ?
        ORDER BY advance_date DESC, created_at DESC
    """, (tech_id, tenant_id))
    advances = [dict(r) for r in cursor.fetchall()]

    # 2. Fetch Wages
    cursor.execute("""
        SELECT * FROM employee_wages 
        WHERE technician_id = ? AND tenant_id = ?
        ORDER BY payment_date DESC, created_at DESC
    """, (tech_id, tenant_id))
    wages = [dict(r) for r in cursor.fetchall()]

    # 3. Fetch Assigned Job Cards
    cursor.execute("""
        SELECT id, job_number, customer_name, customer_phone, vehicle_reg_no, vehicle_make_model,
               status, total_labor, total_parts, grand_total, created_at, completed_at, delivered_at
        FROM job_cards 
        WHERE (assigned_technician_id = ? OR assigned_technician_name = ?) AND tenant_id = ?
        ORDER BY created_at DESC
    """, (tech_id, tech_data["name"], tenant_id))
    jobs = []
    total_labor = 0.0
    for r in cursor.fetchall():
        jd = dict(r)
        lab = float(jd.get("total_labor") or 0.0)
        total_labor += lab
        jd["commission_earned"] = round(lab * (commission_pct / 100.0), 2)
        jobs.append(jd)

    total_advances_given = sum(float(a.get("amount") or 0.0) for a in advances)
    total_wages_paid = sum(float(w.get("net_paid") or 0.0) for w in wages)
    total_advances_deducted = sum(float(w.get("advance_deducted") or 0.0) for w in wages)
    total_commissions_earned = round(total_labor * (commission_pct / 100.0), 2)

    conn.close()

    return {
        "technician": tech_data,
        "advances": advances,
        "wages": wages,
        "jobs": jobs,
        "summary": {
            "total_jobs": len(jobs),
            "total_labor_generated": total_labor,
            "total_commissions_earned": total_commissions_earned,
            "total_advances_given": total_advances_given,
            "total_advances_deducted": total_advances_deducted,
            "current_advance_balance": float(tech_data.get("current_advance_balance") or 0.0),
            "total_wages_paid": total_wages_paid
        }
    }

# =========================================================
# 📥 PURCHASES & RETURNS (DEBIT NOTES / CREDIT NOTES)
# =========================================================

@app.get("/purchases", response_class=HTMLResponse)
async def purchases_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("SELECT * FROM purchase_bills WHERE tenant_id = ? ORDER BY bill_date DESC", (tenant_id,))
    purchases = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM purchase_returns WHERE tenant_id = ? ORDER BY return_date DESC", (tenant_id,))
    purchase_returns = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM inventory_items WHERE tenant_id = ? ORDER BY part_name", (tenant_id,))
    inventory_items = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM suppliers WHERE tenant_id = ? ORDER BY name", (tenant_id,))
    suppliers = [dict(row) for row in cursor.fetchall()]

    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="purchases.html",
        context={
            "active_page": "purchases",
            "purchases": purchases,
            "purchase_returns": purchase_returns,
            "inventory_items": inventory_items,
            "suppliers": suppliers
        }
    )

@app.post("/api/purchases")
async def record_purchase_bill(
    request: Request,
    supplier_name: str = Form(...),
    bill_number: str = Form(...),
    bill_date: str = Form(...),
    total_amount: float = Form(...),
    supplier_id: Optional[str] = Form(None),
    payment_mode: str = Form("BANK_TRANSFER"),
    status: str = Form("CONFIRMED"),
    notes: Optional[str] = Form(None),
    items_json: Optional[str] = Form(None),
    supplier_state: Optional[str] = Form("Kerala (32)"),
    is_interstate: Optional[int] = Form(0),
    cgst_amount: Optional[float] = Form(0.0),
    sgst_amount: Optional[float] = Form(0.0),
    igst_amount: Optional[float] = Form(0.0)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    pur_id = f"pur_{uuid.uuid4().hex[:8]}"
    now_ist = get_ist_now_str()

    clean_sup_name = supplier_name.strip()
    # Resolve or create supplier record to maintain complete supplier history
    if not supplier_id and clean_sup_name:
        cursor.execute("SELECT id FROM suppliers WHERE LOWER(name) = LOWER(?) AND tenant_id = ?", (clean_sup_name, tenant_id))
        s_row = cursor.fetchone()
        if s_row:
            supplier_id = s_row["id"]
        else:
            supplier_id = f"sup_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO suppliers (id, tenant_id, name, phone, state, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (supplier_id, tenant_id, clean_sup_name, "", supplier_state or "Kerala (32)"))

    if supplier_id:
        cursor.execute("UPDATE suppliers SET total_purchases = total_purchases + ? WHERE id = ?", (total_amount, supplier_id))

    cursor.execute("""
    INSERT INTO purchase_bills (
        id, tenant_id, bill_number, supplier_id, supplier_name, bill_date, total_amount, payment_mode, 
        status, notes, created_at, supplier_state, is_interstate, cgst_amount, sgst_amount, igst_amount
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pur_id, tenant_id, bill_number, supplier_id, clean_sup_name, bill_date, total_amount, payment_mode, 
        status, notes, now_ist, supplier_state or "Kerala (32)", is_interstate or 0,
        cgst_amount or 0.0, sgst_amount or 0.0, igst_amount or 0.0
    ))

    # Parse items if passed
    if items_json:
        try:
            items = json.loads(items_json)
            for itm in items:
                pi_id = f"pi_{uuid.uuid4().hex[:8]}"
                part_id = itm.get("item_id")
                part_name = itm.get("part_name", "")
                barcode = itm.get("barcode", "")
                qty = int(itm.get("quantity", 1))
                unit_cost = float(itm.get("unit_cost", 0.0))
                total_cost = unit_cost * qty
                t_rate = float(itm.get("tax_rate", 18.0))

                cursor.execute("""
                INSERT INTO purchase_items (id, purchase_id, item_id, part_name, barcode, quantity, unit_cost, total_cost, tax_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (pi_id, pur_id, part_id, part_name, barcode, qty, unit_cost, total_cost, t_rate))

                # If CONFIRMED, update inventory stock and write stock movement log!
                if status == "CONFIRMED" and part_id:
                    cursor.execute("SELECT stock_qty, cost_price FROM inventory_items WHERE id = ?", (part_id,))
                    c_item = cursor.fetchone()
                    if c_item:
                        old_qty = max(0, c_item["stock_qty"] or 0)
                        old_cost = float(c_item["cost_price"] or 0.0)
                        if old_qty > 0 and old_cost > 0:
                            effective_cost = round(((old_qty * old_cost) + (qty * unit_cost)) / (old_qty + qty), 2)
                        else:
                            effective_cost = unit_cost
                    else:
                        effective_cost = unit_cost

                    cursor.execute("""
                    UPDATE inventory_items 
                    SET stock_qty = stock_qty + ?, cost_price = ? 
                    WHERE id = ?
                    """, (qty, effective_cost, part_id))

                    stk_id = f"stk_{uuid.uuid4().hex[:8]}"
                    cursor.execute("""
                    INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, unit_cost, reference_id, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'PURCHASE_IN', ?, ?, ?, ?)
                    """, (stk_id, part_id, part_name, barcode, qty, part_id, effective_cost, bill_number, f"Supplier Bill #{bill_number} from {clean_sup_name}", now_ist))
        except Exception as e:
            print(f"[Purchase Items Error] {e}")

    db.log_audit("RECORD_PURCHASE", "purchase_bills", pur_id, f"Purchase bill #{bill_number} from {supplier_name} (₹{total_amount:.2f}, Status: {status})", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/purchases", status_code=303)

@app.post("/api/purchases/{pur_id}/confirm")
async def confirm_purchase_bill(pur_id: str):
    """Confirm a draft purchase bill and apply stock updates"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    now_ist = get_ist_now_str()

    cursor.execute("SELECT * FROM purchase_bills WHERE id = ?", (pur_id,))
    pur = cursor.fetchone()
    if not pur:
        conn.close()
        raise HTTPException(status_code=404, detail="Purchase bill not found")

    cursor.execute("SELECT * FROM purchase_items WHERE purchase_id = ?", (pur_id,))
    items = [dict(r) for r in cursor.fetchall()]

    for itm in items:
        part_id = itm.get("item_id")
        qty = itm.get("quantity", 1)
        unit_cost = itm.get("unit_cost", 0.0)
        if part_id:
            cursor.execute("SELECT stock_qty, cost_price FROM inventory_items WHERE id = ?", (part_id,))
            c_item = cursor.fetchone()
            if c_item:
                old_qty = max(0, c_item["stock_qty"] or 0)
                old_cost = float(c_item["cost_price"] or 0.0)
                if old_qty > 0 and old_cost > 0:
                    effective_cost = round(((old_qty * old_cost) + (qty * unit_cost)) / (old_qty + qty), 2)
                else:
                    effective_cost = unit_cost
            else:
                effective_cost = unit_cost

            cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ?, cost_price = ? WHERE id = ?", (qty, effective_cost, part_id))
            stk_id = f"stk_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, unit_cost, reference_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'PURCHASE_IN', ?, ?, ?, ?)
            """, (stk_id, part_id, itm.get("part_name"), itm.get("barcode"), qty, part_id, effective_cost, pur["bill_number"], f"Confirmed Supplier Bill #{pur['bill_number']}", now_ist))

    cursor.execute("UPDATE purchase_bills SET status = 'CONFIRMED' WHERE id = ?", (pur_id,))
    db.log_audit("CONFIRM_PURCHASE", "purchase_bills", pur_id, f"Confirmed Purchase Bill #{pur['bill_number']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/purchases", status_code=303)

@app.post("/api/purchases/returns")
async def record_purchase_return(
    request: Request,
    supplier_name: str = Form(...),
    item_id: str = Form(...),
    quantity: int = Form(1),
    return_amount: float = Form(...),
    reason: str = Form("Defective Part")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT part_name, cost_price FROM inventory_items WHERE id = ? AND tenant_id = ?", (item_id, tenant_id))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    ret_id = f"pr_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM purchase_returns WHERE tenant_id = ?", (tenant_id,))
    cnt = cursor.fetchone()[0] + 1
    return_number = f"DN-2026-{cnt:03d}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO purchase_returns (id, tenant_id, return_number, supplier_name, item_id, part_name, quantity, unit_cost, return_amount, return_date, reason, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (ret_id, tenant_id, return_number, supplier_name, item_id, item["part_name"], quantity, item["cost_price"], return_amount, today_str, reason))

    cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ? AND tenant_id = ?", (quantity, item_id, tenant_id))

    db.log_audit("PURCHASE_RETURN", "purchase_returns", ret_id, f"Debit note #{return_number} for {quantity}x {item['part_name']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/purchases", status_code=303)

# =========================================================
# 🚚 SUPPLIERS DIRECTORY & PURCHASE HISTORY
# =========================================================

@app.get("/suppliers", response_class=HTMLResponse)
async def suppliers_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("""
    SELECT s.*, 
           COUNT(DISTINCT pb.id) as total_bills,
           COALESCE(SUM(pb.total_amount), 0.0) as calculated_total_purchases
    FROM suppliers s
    LEFT JOIN purchase_bills pb ON (s.id = pb.supplier_id OR LOWER(s.name) = LOWER(pb.supplier_name)) AND pb.tenant_id = ?
    WHERE s.tenant_id = ?
    GROUP BY s.id
    ORDER BY s.name
    """, (tenant_id, tenant_id))
    suppliers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="suppliers.html",
        context={
            "active_page": "suppliers",
            "suppliers": suppliers
        }
    )

@app.post("/api/suppliers")
async def create_supplier(
    request: Request,
    name: str = Form(...),
    contact_person: Optional[str] = Form(None),
    phone: str = Form(...),
    whatsapp: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: str = Form("Kerala (32)"),
    gstin: Optional[str] = Form(None),
    payment_terms: Optional[str] = Form(None),
    notes: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    sup_id = f"sup_{uuid.uuid4().hex[:8]}"
    
    cursor.execute("""
    INSERT INTO suppliers (
        id, tenant_id, name, contact_person, phone, whatsapp, email, address, city, state, gstin, payment_terms, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (sup_id, tenant_id, name.strip(), contact_person, phone.strip(), whatsapp or phone.strip(), email, address, city, state, gstin, payment_terms, notes))
    
    db.log_audit("CREATE_SUPPLIER", "suppliers", sup_id, f"Created supplier {name}", cursor=cursor)
    conn.commit()
    return RedirectResponse(url="/suppliers", status_code=303)

@app.post("/api/suppliers/quick-create")
async def quick_create_supplier(request: Request, payload: Dict[str, Any]):
    tenant_id = get_current_tenant_id(request)
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Supplier name is required")
    phone = (payload.get("phone") or "").strip()
    contact_person = (payload.get("contact_person") or "").strip()
    state = (payload.get("state") or "Kerala (32)").strip()
    city = (payload.get("city") or "").strip()
    gstin = (payload.get("gstin") or "").strip().upper()

    conn = db.get_db_connection()
    cursor = conn.cursor()
    sup_id = f"sup_{uuid.uuid4().hex[:8]}"

    cursor.execute("""
    INSERT INTO suppliers (
        id, tenant_id, name, contact_person, phone, whatsapp, email, address, city, state, gstin, payment_terms, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (sup_id, tenant_id, name, contact_person, phone, phone, None, None, city, state, gstin, None, None))

    db.log_audit("CREATE_SUPPLIER_QUICK", "suppliers", sup_id, f"Quick created supplier {name}", cursor=cursor)
    conn.commit()
    conn.close()

    return {
        "success": True,
        "supplier": {
            "id": sup_id,
            "name": name,
            "phone": phone,
            "state": state,
            "city": city,
            "gstin": gstin
        }
    }

@app.get("/api/suppliers/{supplier_id}")
async def get_supplier_details(request: Request, supplier_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM suppliers WHERE id = ? AND tenant_id = ?", (supplier_id, tenant_id))
    sup_row = cursor.fetchone()
    if not sup_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Supplier not found")
    supplier = dict(sup_row)
    
    # Get purchase bills
    cursor.execute("SELECT * FROM purchase_bills WHERE (supplier_id = ? OR LOWER(supplier_name) = LOWER(?)) AND tenant_id = ? ORDER BY bill_date DESC", (supplier_id, supplier["name"], tenant_id))
    bills = [dict(r) for r in cursor.fetchall()]
    
    # Get all distinct products supplied
    cursor.execute("""
    SELECT pi.part_name, pi.barcode, pi.unit_cost, pi.quantity, pi.total_cost, pb.bill_number, pb.bill_date
    FROM purchase_items pi
    JOIN purchase_bills pb ON pi.purchase_id = pb.id
    WHERE (pb.supplier_id = ? OR LOWER(pb.supplier_name) = LOWER(?)) AND pb.tenant_id = ?
    ORDER BY pb.bill_date DESC
    """, (supplier_id, supplier["name"], tenant_id))
    products = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    return {
        "supplier": supplier,
        "bills": bills,
        "products": products
    }

# =========================================================
# 📦 INVENTORY PRODUCT HISTORY & QUICK PART CREATION
# =========================================================

@app.get("/api/inventory/{item_id}/history")
async def get_inventory_item_history(item_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
    item_row = cursor.fetchone()
    if not item_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Inventory item not found")
    item = dict(item_row)

    # 1. Purchase History (every supplier bill where this product was purchased)
    cursor.execute("""
    SELECT pi.id, pi.quantity, pi.unit_cost, pi.total_cost,
           pb.id as purchase_id, pb.bill_number, pb.supplier_name, pb.bill_date, pb.payment_mode, pb.created_at
    FROM purchase_items pi
    JOIN purchase_bills pb ON pi.purchase_id = pb.id
    WHERE pi.item_id = ?
    ORDER BY pb.bill_date DESC, pb.created_at DESC
    """, (item_id,))
    purchases = [dict(r) for r in cursor.fetchall()]

    # 2. Stock movement logs
    cursor.execute("""
    SELECT * FROM stock_logs
    WHERE item_id = ?
    ORDER BY created_at DESC
    LIMIT 100
    """, (item_id,))
    logs = [dict(r) for r in cursor.fetchall()]

    conn.close()

    # 3. Calculate Price Trend
    price_trend = {
        "status": "INITIAL",  # INCREASED, DECREASED, UNCHANGED, INITIAL
        "diff": 0.0,
        "percentage": 0.0,
        "latest_cost": item["cost_price"],
        "previous_cost": item["cost_price"],
        "message": "Current Base Cost"
    }

    if len(purchases) >= 2:
        latest = purchases[0]["unit_cost"]
        prev = purchases[1]["unit_cost"]
        price_trend["latest_cost"] = latest
        price_trend["previous_cost"] = prev
        diff = round(latest - prev, 2)
        price_trend["diff"] = abs(diff)
        pct = round((abs(diff) / prev) * 100, 1) if prev > 0 else 0
        price_trend["percentage"] = pct

        if diff > 0:
            price_trend["status"] = "INCREASED"
            price_trend["message"] = f"Purchase cost increased by ₹{abs(diff):.2f} (+{pct}%) since previous bill"
        elif diff < 0:
            price_trend["status"] = "DECREASED"
            price_trend["message"] = f"Purchase cost decreased by ₹{abs(diff):.2f} (-{pct}%) since previous bill"
        else:
            price_trend["status"] = "UNCHANGED"
            price_trend["message"] = "Purchase cost stable / unchanged"
    elif len(purchases) == 1:
        price_trend["latest_cost"] = purchases[0]["unit_cost"]
        price_trend["message"] = f"Initial recorded purchase at ₹{purchases[0]['unit_cost']:.2f}"
    else:
        # Check stock logs if any purchase costs logged
        costs = [l["unit_cost"] for l in logs if l.get("unit_cost") and l["unit_cost"] > 0]
        if len(costs) >= 2:
            latest = costs[0]
            prev = costs[1]
            diff = round(latest - prev, 2)
            pct = round((abs(diff) / prev) * 100, 1) if prev > 0 else 0
            if diff > 0:
                price_trend["status"] = "INCREASED"
                price_trend["diff"] = abs(diff)
                price_trend["percentage"] = pct
                price_trend["message"] = f"Cost increased by ₹{abs(diff):.2f} (+{pct}%)"
            elif diff < 0:
                price_trend["status"] = "DECREASED"
                price_trend["diff"] = abs(diff)
                price_trend["percentage"] = pct
                price_trend["message"] = f"Cost decreased by ₹{abs(diff):.2f} (-{pct}%)"

    return {
        "item": item,
        "purchases": purchases,
        "logs": logs,
        "price_trend": price_trend
    }

@app.post("/api/inventory/quick-create")
async def quick_create_inventory_item(request: Request, payload: Dict[str, Any]):
    tenant_id = get_current_tenant_id(request)
    part_name = payload.get("part_name", "").strip()
    if not part_name:
        raise HTTPException(status_code=400, detail="Part name is required")
        
    barcode = payload.get("barcode", "").strip()
    if not barcode:
        barcode = f"890{uuid.uuid4().int % 100000000:08d}"
        
    part_number = payload.get("part_number", "").strip().upper()
    category = payload.get("category", "Relays & Fuses")
    cost_price = float(payload.get("cost_price", 0.0))
    selling_price = float(payload.get("selling_price", 0.0))
    tax_rate = float(payload.get("tax_rate", 18.0))
    hsn_code = payload.get("hsn_code", "8536").strip()
    location_rack = (payload.get("location_rack") or "Main").strip()
    position_bin = (payload.get("position_bin") or "").strip()
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    item_id = f"item_{uuid.uuid4().hex[:8]}"
    
    cursor.execute("""
    INSERT INTO inventory_items (
        id, tenant_id, part_name, part_number, sku, barcode, category, stock_qty, min_stock_alert,
        cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
        location_rack, position_bin,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 5, ?, ?, ?, ?, 'pcs', 6, ?, ?, datetime('now'), datetime('now'))
    """, (item_id, tenant_id, part_name, part_number, barcode, barcode, category, cost_price, selling_price, tax_rate, hsn_code, location_rack, position_bin))
    
    db.log_audit("QUICK_CREATE_PART", "inventory_items", item_id, f"Quick created part: {part_name} (PN: {part_number}, Rack: {location_rack}, Bin: {position_bin})", cursor=cursor)
    conn.commit()
    conn.close()
    
    return {
        "status": "ok",
        "item": {
            "id": item_id,
            "part_name": part_name,
            "name": part_name,
            "part_number": part_number,
            "barcode": barcode,
            "cost_price": cost_price,
            "cost": cost_price,
            "selling_price": selling_price,
            "tax_rate": tax_rate,
            "hsn_code": hsn_code,
            "unit": "pcs",
            "stock_qty": 0,
            "location_rack": location_rack,
            "position_bin": position_bin
        }
    }

@app.get("/sales-returns", response_class=HTMLResponse)
async def sales_returns_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM sales_returns WHERE tenant_id = ? ORDER BY return_date DESC", (tenant_id,))
    returns = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM inventory_items WHERE tenant_id = ? ORDER BY part_name", (tenant_id,))
    inventory_items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="sales_returns.html",
        context={
            "active_page": "sales_returns",
            "returns": returns,
            "inventory_items": inventory_items
        }
    )

@app.post("/api/sales-returns")
async def record_sales_return(
    request: Request,
    invoice_id: str = Form(...),
    customer_name: str = Form(...),
    item_id: str = Form(...),
    quantity: int = Form(1),
    refund_amount: float = Form(...),
    refund_mode: str = Form("CASH"),
    reason: str = Form("Customer Returned Part")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT part_name, barcode, selling_price FROM inventory_items WHERE id = ? AND tenant_id = ?", (item_id, tenant_id))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    sr_id = f"sr_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM sales_returns WHERE tenant_id = ?", (tenant_id,))
    cnt = cursor.fetchone()[0] + 1
    return_number = f"CN-2026-{cnt:03d}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO sales_returns (id, tenant_id, return_number, invoice_id, customer_name, item_id, name, quantity, unit_price, refund_amount, return_date, refund_mode, reason, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (sr_id, tenant_id, return_number, invoice_id, customer_name, item_id, item["part_name"], quantity, item["selling_price"], refund_amount, today_str, refund_mode, reason))

    cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ? AND tenant_id = ?", (quantity, item_id, tenant_id))

    stk_id = f"stk_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO stock_logs (id, tenant_id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, reference_id, notes, created_at)
    VALUES (?, ?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'SALES_RETURN', ?, ?, datetime('now'))
    """, (stk_id, tenant_id, item_id, item["part_name"], item["barcode"] or "", quantity, item_id, return_number, f"Sales Return #{return_number}: {reason}"))

    # Deduct refund from bank account or cash drawer
    if refund_amount > 0:
        cursor.execute("SELECT id FROM bank_accounts WHERE is_primary = 1 AND tenant_id = ? LIMIT 1", (tenant_id,))
        p_acc = cursor.fetchone()
        if p_acc:
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE id = ?", (refund_amount, p_acc["id"]))
        elif refund_mode == "CASH":
            cursor.execute("UPDATE bank_accounts SET current_balance = MAX(0.0, current_balance - ?) WHERE account_type = 'CASH' AND tenant_id = ? LIMIT 1", (refund_amount, tenant_id))

    db.log_audit("SALES_RETURN", "sales_returns", sr_id, f"Credit note #{return_number} for {customer_name}: {quantity}x {item['part_name']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/sales-returns", status_code=303)

# =========================================================
# 👥 CUSTOMERS, BANK ACCOUNTS & EXPENSES
# =========================================================

@app.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("""
    SELECT v.*, c.khata_balance, c.total_visits, c.id as cust_id
    FROM vehicles v
    LEFT JOIN customers c ON (v.customer_id = c.id OR v.customer_phone = c.phone) AND c.tenant_id = ?
    WHERE v.tenant_id = ?
    ORDER BY v.created_at DESC
    """, (tenant_id, tenant_id))
    vehicles = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="customers.html",
        context={
            "active_page": "customers",
            "vehicles": vehicles
        }
    )

@app.get("/api/customers/{customer_id_or_phone}/history")
async def get_customer_history(request: Request, customer_id_or_phone: str):
    tenant_id = get_current_tenant_id(request)
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    clean_val = customer_id_or_phone.strip()
    cursor.execute("SELECT * FROM customers WHERE (id = ? OR phone = ?) AND tenant_id = ? LIMIT 1", (clean_val, clean_val, tenant_id))
    c_row = cursor.fetchone()
    
    veh_row = None
    if not c_row:
        cursor.execute("SELECT * FROM vehicles WHERE reg_number = ? AND tenant_id = ? LIMIT 1", (clean_val.upper(), tenant_id))
        veh_row = cursor.fetchone()
        if veh_row and veh_row.get("customer_phone"):
            cursor.execute("SELECT * FROM customers WHERE phone = ? AND tenant_id = ? LIMIT 1", (veh_row["customer_phone"], tenant_id))
            c_row = cursor.fetchone()

    customer = dict(c_row) if c_row else None
    
    vehicles = []
    if customer:
        cursor.execute("SELECT * FROM vehicles WHERE (customer_id = ? OR customer_phone = ?) AND tenant_id = ?", (customer["id"], customer["phone"], tenant_id))
        vehicles = [dict(r) for r in cursor.fetchall()]
    elif veh_row:
        vehicles = [dict(veh_row)]
        customer = {
            "name": veh_row["customer_name"],
            "phone": veh_row["customer_phone"],
            "khata_balance": 0.0,
            "total_visits": 1
        }

    cust_phone = customer["phone"] if customer else ""
    veh_regs = [v["reg_number"] for v in vehicles]

    job_cards = []
    invoices = []
    if cust_phone or veh_regs:
        conditions = []
        params = [tenant_id]
        if cust_phone:
            conditions.append("customer_phone = ?")
            params.append(cust_phone)
        if veh_regs:
            placeholders = ",".join(["?"] * len(veh_regs))
            conditions.append(f"vehicle_reg_no IN ({placeholders})")
            params.extend(veh_regs)
        
        where_clause = " OR ".join(conditions)
        cursor.execute(f"SELECT * FROM job_cards WHERE tenant_id = ? AND ({where_clause}) ORDER BY created_at DESC", tuple(params))
        job_cards = [dict(r) for r in cursor.fetchall()]

        cursor.execute(f"SELECT * FROM invoices WHERE tenant_id = ? AND ({where_clause}) ORDER BY created_at DESC", tuple(params))
        invoices = [dict(r) for r in cursor.fetchall()]

    for j in job_cards:
        j["created_at_ist"] = format_dt_to_ist(j.get("created_at"))
        j["completed_at_ist"] = format_dt_to_ist(j.get("completed_at"))
        try:
            j["complaints_list"] = json.loads(j["complaints"]) if j["complaints"] else []
        except Exception:
            j["complaints_list"] = [j["complaints"]] if j["complaints"] else []

    for inv in invoices:
        inv["created_at_ist"] = format_dt_to_ist(inv.get("created_at"))
        inv["invoice_date_ist"] = format_dt_to_ist(inv.get("invoice_date"), "%d %b %Y")

    total_spent = sum(inv.get("grand_total", 0.0) for inv in invoices)
    total_due = sum(inv.get("balance_due", 0.0) for inv in invoices)

    conn.close()
    return {
        "success": True,
        "customer": customer,
        "vehicles": vehicles,
        "job_cards": job_cards,
        "invoices": invoices,
        "stats": {
            "total_visits": len(job_cards),
            "total_invoices": len(invoices),
            "total_spent": total_spent,
            "total_due": total_due
        }
    }


@app.get("/bank-accounts", response_class=HTMLResponse)
async def bank_accounts_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM bank_accounts WHERE tenant_id = ? ORDER BY is_primary DESC, current_balance DESC", (tenant_id,))
    accounts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="bank_accounts.html",
        context={
            "active_page": "bank_accounts",
            "accounts": accounts
        }
    )

@app.post("/api/bank-accounts")
async def add_bank_account(
    request: Request,
    account_name: str = Form(...),
    bank_name: Optional[str] = Form(None),
    account_type: str = Form("BANK"),
    account_number: Optional[str] = Form(None),
    ifsc_code: Optional[str] = Form(None),
    upi_vpa: Optional[str] = Form(None),
    current_balance: float = Form(0.0)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    acc_id = f"bank_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO bank_accounts (id, tenant_id, account_name, bank_name, account_type, account_number, ifsc_code, upi_vpa, current_balance, is_primary, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
    """, (acc_id, tenant_id, account_name, bank_name, account_type, account_number, ifsc_code, upi_vpa, current_balance))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/bank-accounts", status_code=303)

@app.get("/expenses", response_class=HTMLResponse)
async def expenses_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM expenses WHERE tenant_id = ? ORDER BY expense_date DESC, created_at DESC", (tenant_id,))
    expenses = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    return templates.TemplateResponse(
        request=request,
        name="expenses.html",
        context={
            "active_page": "expenses",
            "expenses": expenses,
            "today_date": today_date
        }
    )

@app.post("/api/expenses")
async def record_expense(
    request: Request,
    title: str = Form(...),
    category: str = Form("Electricity Bill"),
    amount: float = Form(...),
    payment_mode: str = Form("CASH"),
    expense_date: str = Form(...),
    paid_to: Optional[str] = Form(None),
    reference_no: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    exp_id = f"exp_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO expenses (id, tenant_id, title, category, amount, payment_mode, expense_date, paid_to, reference_no, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (exp_id, tenant_id, title, category, amount, payment_mode, expense_date, paid_to, reference_no))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/expenses", status_code=303)

# =========================================================
# 📊 CA TAX AUDIT REPORTS & KHATA
# =========================================================

@app.get("/ca-reports", response_class=HTMLResponse)
async def ca_reports_page(
    request: Request,
    financial_year: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    tenant_id = get_current_tenant_id(request)
    fy_dates = ca_reports.get_financial_year_dates(financial_year)
    s_date = start_date or fy_dates["start_date"]
    e_date = end_date or fy_dates["end_date"]

    gstr1 = ca_reports.generate_gstr1_report(s_date, e_date, tenant_id=tenant_id)
    pnl = ca_reports.generate_profit_and_loss_report(s_date, e_date, tenant_id=tenant_id)
    valuation = ca_reports.generate_inventory_valuation_report(tenant_id=tenant_id)
    collections = ca_reports.generate_daily_collection_register(s_date, e_date, tenant_id=tenant_id)

    return templates.TemplateResponse(
        request=request,
        name="ca_reports.html",
        context={
            "active_page": "ca_reports",
            "gstr1": gstr1,
            "pnl": pnl,
            "valuation": valuation,
            "collections": collections,
            "financial_year": financial_year or fy_dates["financial_year"],
            "start_date": s_date,
            "end_date": e_date
        }
    )

@app.get("/api/ca-reports/export-gstr1-excel")
async def export_ca_gstr1_excel(request: Request, financial_year: Optional[str] = None):
    tenant_id = get_current_tenant_id(request)
    fy_dates = ca_reports.get_financial_year_dates(financial_year)
    excel_bytes = ca_reports.export_gstr1_excel(fy_dates["start_date"], fy_dates["end_date"], tenant_id=tenant_id)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=GSTR1_Audit_Report_{fy_dates['financial_year']}.xlsx"}
    )

@app.get("/khata", response_class=HTMLResponse)
async def khata_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    cursor.execute("SELECT * FROM invoices WHERE tenant_id = ? AND balance_due > 0 ORDER BY invoice_date DESC", (tenant_id,))
    unpaid_invoices = [dict(row) for row in cursor.fetchall()]
    
    total_dues = sum(inv["balance_due"] for inv in unpaid_invoices)
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="khata.html",
        context={
            "active_page": "khata",
            "unpaid_invoices": unpaid_invoices,
            "total_dues": total_dues
        }
    )

@app.get("/activity-logs", response_class=HTMLResponse)
async def activity_logs_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 100")
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return templates.TemplateResponse(
        request=request,
        name="activity_logs.html",
        context={
            "active_page": "activity_logs",
            "logs": logs
        }
    )

# =========================================================
# ⚙️ WORKSHOP SETTINGS & PUBLIC VIEWS
# =========================================================

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    profile = get_current_workshop(request)
    saas_info = check_saas_subscription(request)
    is_supabase_connected = bool(db.supabase_client)
    
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_page": "settings",
            "profile": profile,
            "tenant": saas_info["tenant"],
            "subscription": saas_info["subscription"],
            "is_supabase_connected": is_supabase_connected
        }
    )

@app.post("/api/settings/profile")
async def update_workshop_profile(
    request: Request,
    name: str = Form(...),
    subtitle: Optional[str] = Form(None),
    phone: str = Form(...),
    email: Optional[str] = Form(None),
    address: str = Form(...),
    gstin: Optional[str] = Form(None),
    upi_id: str = Form(...),
    bank_name: Optional[str] = Form(None),
    bank_account_no: Optional[str] = Form(None),
    bank_ifsc: Optional[str] = Form(None),
    bank_branch: Optional[str] = Form(None),
    whatsapp_lang: str = Form("en"),
    master_pin: str = Form("1234"),
    default_state: str = Form("Kerala (32)"),
    tax_regime: str = Form("REGULAR_GST"),
    round_off_enabled: int = Form(1),
    terms: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tenant_id = get_current_tenant_id(request)
    
    cursor.execute("""
    UPDATE workshop_profile SET
        name = ?, subtitle = ?, phone = ?, email = ?, address = ?, gstin = ?,
        upi_id = ?, bank_name = ?, bank_account_no = ?, bank_ifsc = ?, bank_branch = ?,
        language = ?, master_pin = ?, terms = ?,
        default_state = ?, tax_regime = ?, round_off_enabled = ?,
        updated_at = datetime('now')
    WHERE tenant_id = ? OR id = ?
    """, (name, subtitle, phone, email, address, gstin, upi_id, bank_name, bank_account_no, bank_ifsc, bank_branch, whatsapp_lang, master_pin, terms, default_state, tax_regime, round_off_enabled, tenant_id, tenant_id))
    
    cursor.execute("""
    UPDATE tenants SET
        name = ?, phone = ?, whatsapp_mobile = ?, email = ?, address = ?, gstin = ?,
        upi_id = ?, bank_name = ?, bank_account_no = ?, bank_ifsc = ?, bank_branch = ?,
        language = ?, master_pin = ?
    WHERE id = ?
    """, (name, phone, phone, email, address, gstin, upi_id, bank_name, bank_account_no, bank_ifsc, bank_branch, whatsapp_lang, master_pin, tenant_id))

    db.log_audit("UPDATE_PROFILE", "workshop_profile", tenant_id, f"Updated garage profile ({name})", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/settings", status_code=303)

@app.get("/view/invoice/{invoice_id}", response_class=HTMLResponse)
async def public_invoice_view(request: Request, invoice_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv_row = cursor.fetchone()
    if not inv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = dict(inv_row)
    
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    invoice["items"] = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    workshop = get_current_workshop(request=request, tenant_id=invoice.get("tenant_id"))
    
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    grand_total = float(invoice.get("grand_total", 0.0))
    balance_due = float(invoice.get("balance_due", 0.0))
    pay_amount = balance_due if balance_due > 0 else grand_total
    
    upi_link = invoice.get("upi_payment_link") or generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), pay_amount, f"Inv_{invoice.get('invoice_number')}")
    upi_qr_url = generate_upi_qr_data_url(upi_link)
    
    return templates.TemplateResponse(
        request=request,
        name="public_invoice.html",
        context={
            "invoice": invoice,
            "items": invoice["items"],
            "workshop": workshop,
            "upi_qr_url": upi_qr_url
        }
    )

@app.get("/view/job/{job_id}", response_class=HTMLResponse)
async def public_job_view(request: Request, job_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Job Card not found")
    job = dict(row)
    conn.close()
    
    try:
        complaints_list = json.loads(job["complaints"]) if job["complaints"] else []
    except Exception:
        complaints_list = [job["complaints"]] if job["complaints"] else []
        
    workshop = get_current_workshop(request=request, tenant_id=job.get("tenant_id"))
    
    return templates.TemplateResponse(
        request=request,
        name="public_job_view.html",
        context={
            "job": job,
            "complaints_list": complaints_list,
            "workshop": workshop
        }
    )

@app.get("/invoice/{invoice_id}/print", response_class=HTMLResponse)
@app.get("/invoices/{invoice_id}/print", response_class=HTMLResponse)
async def print_invoice_page(request: Request, invoice_id: str, format: Optional[str] = "a4"):
    if format == "pdf":
        return RedirectResponse(url=f"/api/invoices/{invoice_id}/pdf", status_code=303)

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv_row = cursor.fetchone()
    if not inv_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice = dict(inv_row)
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()

    workshop = get_current_workshop(request=request, tenant_id=invoice.get("tenant_id"))
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    
    # Safe float & string conversions to prevent Jinja2 format crashes
    invoice["subtotal_labor"] = float(invoice.get("subtotal_labor") or 0.0)
    invoice["subtotal_parts"] = float(invoice.get("subtotal_parts") or 0.0)
    invoice["tax_total"] = float(invoice.get("tax_total") or 0.0)
    invoice["discount_amount"] = float(invoice.get("discount_amount") or 0.0)
    invoice["grand_total"] = float(invoice.get("grand_total") or 0.0)
    invoice["amount_paid"] = float(invoice.get("amount_paid") or 0.0)
    invoice["balance_due"] = float(invoice.get("balance_due") or 0.0)
    raw_odo = invoice.get("odometer")
    invoice["odometer_str"] = f"{int(raw_odo):,} km" if (raw_odo and str(raw_odo).strip().isdigit() and int(raw_odo) > 0) else ""

    for itm in items:
        itm["unit_price"] = float(itm.get("unit_price") or 0.0)
        itm["total_price"] = float(itm.get("total_price") or 0.0)
        itm["tax_rate"] = float(itm.get("tax_rate") or 0.0)

    grand_total = invoice["grand_total"]
    balance_due = invoice["balance_due"]
    pay_amount = balance_due if balance_due > 0 else grand_total
    upi_link = invoice.get("upi_payment_link") or generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), pay_amount, f"Inv_{invoice.get('invoice_number')}")
    upi_qr_url = generate_upi_qr_data_url(upi_link)

    return templates.TemplateResponse(
        request=request,
        name="print_invoice.html",
        context={
            "invoice": invoice,
            "items": items,
            "workshop": workshop,
            "upi_qr_url": upi_qr_url,
            "print_format": format or "a4"
        }
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
