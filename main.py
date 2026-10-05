import os
import io
import json
import uuid
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
    format_khata_due_reminder_whatsapp_message
)
import ca_reports
from pdf_generator import generate_invoice_pdf_bytes
from excel_importer import generate_inventory_import_template, parse_inventory_file
from auth_helper import hash_password, verify_password, verify_master_pin, generate_reset_token
import otp_helper

app = FastAPI(title="AutoVolt Pro — Auto Electrical Workshop Management", version="2.0.0")

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

templates.env.filters["tojson"] = to_json_filter
templates.env.filters["to_ist"] = format_dt_to_ist
templates.env.filters["elapsed_ist"] = elapsed_time_ist

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper: Get current active workshop profile
def get_current_workshop() -> Dict[str, Any]:
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workshop_profile WHERE id = 'default'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "id": "default",
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
def check_saas_subscription() -> Dict[str, Any]:
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tenants WHERE id = 'tenant_1' OR id = 'default-workshop' LIMIT 1")
    t_row = cursor.fetchone()
    cursor.execute("SELECT * FROM subscriptions WHERE is_active = 1 ORDER BY end_date DESC LIMIT 1")
    s_row = cursor.fetchone()
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
        "/subscription-expired", "/view", "/invoice"
    ]
    
    is_exempt = any(path.startswith(prefix) for prefix in exempt_prefixes)
    session_user = request.cookies.get("session_user")
    
    # If not logged in and accessing protected page, redirect to login
    if not is_exempt and not session_user:
        if request.method == "GET":
            return RedirectResponse(url="/login", status_code=303)
        else:
            return JSONResponse({"error": "Authentication required", "redirect": "/login"}, status_code=401)
            
    # If already logged in and visiting login page, redirect to dashboard
    if path == "/login" and session_user and request.method == "GET":
        return RedirectResponse(url="/", status_code=303)
    
    # SaaS Expiration Check for authenticated users
    if not is_exempt and request.method == "GET":
        sub_info = check_saas_subscription()
        if sub_info["is_expired"]:
            return RedirectResponse(url="/subscription-expired", status_code=303)
            
    response = await call_next(request)
    return response

# Helper to get current logged in user dict
def get_session_user(request: Request) -> Optional[dict]:
    username = request.cookies.get("session_user")
    if not username:
        return None
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, role, full_name, email, phone, whatsapp_mobile, permissions FROM users WHERE username = ? AND status = 'ACTIVE'", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

templates.env.globals["get_session_user"] = get_session_user

# Base URL for public links
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# =========================================================
# 🔐 AUTHENTICATION & WHATSAPP OTP PASSWORD RESET
# =========================================================

@app.get("/login", response_class=HTMLResponse)
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
    password: str = Form(...)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ? AND status = 'ACTIVE'", (username.strip(),))
    user_row = cursor.fetchone()

    if not user_row or not verify_password(password.strip(), user_row["password_hash"]):
        conn.close()
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Invalid username or password. Please try again."}
        )

    user = dict(user_row)
    db.log_audit("USER_LOGIN", "users", user["id"], f"User {user['username']} logged in", cursor=cursor)
    conn.commit()
    conn.close()
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session_user", value=user["username"], max_age=86400 * 30, httponly=True)
    return response

@app.get("/logout")
async def handle_logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_user")
    return response

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

    return templates.TemplateResponse(
        request=request,
        name="verify_otp.html",
        context={
            "username": username,
            "whatsapp_mobile": mobile,
            "whatsapp_link": whatsapp_link,
            "otp_preview": otp_code,
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
    workshop = get_current_workshop()
    return templates.TemplateResponse(
        request=request,
        name="subscription_expired.html",
        context={"workshop": workshop}
    )

# =========================================================
# 📊 MAIN DASHBOARD & JOB CARDS
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM job_cards WHERE status NOT IN ('DELIVERED', 'CANCELLED')")
    active_jobs_count = cursor.fetchone()[0]
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COALESCE(SUM(amount_paid), 0), COUNT(*) FROM invoices WHERE date(invoice_date) = date(?)", (today_str,))
    rev_row = cursor.fetchone()
    today_revenue = rev_row[0]
    today_invoices_count = rev_row[1]
    
    cursor.execute("SELECT COALESCE(SUM(balance_due), 0) FROM invoices WHERE balance_due > 0")
    total_khata_dues = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM inventory_items WHERE stock_qty <= min_stock_alert")
    low_stock_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT * FROM job_cards WHERE status NOT IN ('DELIVERED', 'CANCELLED') ORDER BY created_at DESC LIMIT 6")
    active_jobs = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM technicians ORDER BY total_jobs DESC")
    technicians = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM invoices ORDER BY created_at DESC LIMIT 8")
    recent_invoices = [dict(row) for row in cursor.fetchall()]
    
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
        }
    )

@app.get("/job-cards", response_class=HTMLResponse)
async def job_cards_page(request: Request, filter: Optional[str] = None, status: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM job_cards ORDER BY created_at DESC")
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
        
    cursor.execute("SELECT * FROM technicians ORDER BY name ASC")
    technicians = [dict(row) for row in cursor.fetchall()]

    # Fetch registered customers & vehicles for quick auto-fill in modal
    cursor.execute("""
    SELECT c.name as customer_name, c.phone as customer_phone,
           v.reg_number as vehicle_reg_no, v.make_model as vehicle_make_model, v.odometer
    FROM customers c
    LEFT JOIN vehicles v ON c.id = v.customer_id
    ORDER BY c.name ASC
    """)
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
    
    cursor.execute("SELECT * FROM technicians WHERE status = 'Active'")
    technicians = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM inventory_items WHERE stock_qty > 0 ORDER BY part_name")
    inventory_items = [dict(row) for row in cursor.fetchall()]

    # Check for linked invoice
    cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? ORDER BY created_at DESC LIMIT 1", (job_id,))
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
            "grand_total": grand_total,
            "technicians": technicians,
            "inventory_items": inventory_items,
            "linked_invoice": linked_invoice,
            "milestones": milestones
        }
    )


@app.post("/api/job-cards")
async def create_job_card(
    vehicle_reg_no: str = Form(...),
    vehicle_make_model: str = Form(...),
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    assigned_technician_id: Optional[str] = Form(None),
    odometer: Optional[int] = Form(0),
    complaints: List[str] = Form([]),
    custom_complaint_notes: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM job_cards")
    cnt = cursor.fetchone()[0] + 1
    job_number = f"JOB-2026-{cnt:03d}"
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    
    tech_name = None
    if assigned_technician_id:
        cursor.execute("SELECT name FROM technicians WHERE id = ?", (assigned_technician_id,))
        t_row = cursor.fetchone()
        if t_row:
            tech_name = t_row["name"]
            
    now_ist = get_ist_now_str()
    cursor.execute("SELECT id FROM customers WHERE phone = ?", (customer_phone.strip(),))
    c_row = cursor.fetchone()
    if c_row:
        customer_id = c_row["id"]
        cursor.execute("UPDATE customers SET total_visits = total_visits + 1 WHERE id = ?", (customer_id,))
    else:
        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        cursor.execute("INSERT INTO customers (id, name, phone, created_at) VALUES (?, ?, ?, ?)", (customer_id, customer_name, customer_phone, now_ist))
        
    cursor.execute("SELECT id FROM vehicles WHERE reg_number = ?", (vehicle_reg_no.strip().upper(),))
    v_row = cursor.fetchone()
    if v_row:
        vehicle_id = v_row["id"]
        cursor.execute("UPDATE vehicles SET odometer = ? WHERE id = ?", (odometer, vehicle_id))
    else:
        vehicle_id = f"veh_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO vehicles (id, reg_number, customer_id, customer_name, customer_phone, make_model, odometer, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (vehicle_id, vehicle_reg_no.strip().upper(), customer_id, customer_name, customer_phone, vehicle_make_model, odometer, now_ist))
        
    complaints_json = json.dumps(complaints)
    cursor.execute("""
    INSERT INTO job_cards (
        id, job_number, customer_id, customer_name, customer_phone, vehicle_id, vehicle_reg_no,
        vehicle_make_model, odometer, assigned_technician_id, assigned_technician_name,
        status, complaints, custom_complaint_notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RECEIVED', ?, ?, ?)
    """, (
        job_id, job_number, customer_id, customer_name, customer_phone, vehicle_id,
        vehicle_reg_no.strip().upper(), vehicle_make_model, odometer, assigned_technician_id,
        tech_name, complaints_json, custom_complaint_notes, now_ist
    ))
    
    db.log_audit("CREATE_JOB_CARD", "job_cards", job_id, f"Job {job_number} for {vehicle_reg_no}", cursor=cursor)
    conn.commit()
    conn.close()
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

    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

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
    
    prefill_job = None
    editing_invoice = None
    existing_linked_invoice = None
    prefill_items_json = "[]"
    
    if edit_invoice:
        cursor.execute("SELECT * FROM invoices WHERE id = ?", (edit_invoice,))
        inv_r = cursor.fetchone()
        if inv_r:
            cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (edit_invoice,))
            inv_items = [dict(r) for r in cursor.fetchall()]
            editing_invoice = dict(inv_r)
            editing_invoice["items"] = inv_items
            prefill_items_json = json.dumps(inv_items, default=str)
    elif from_job:
        cursor.execute("SELECT * FROM job_cards WHERE id = ?", (from_job,))
        job_row = cursor.fetchone()
        if job_row:
            cursor.execute("SELECT * FROM invoices WHERE job_card_id = ? AND payment_status != 'CANCELLED' ORDER BY created_at DESC LIMIT 1", (from_job,))
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

    cursor.execute("SELECT * FROM inventory_items ORDER BY part_name")
    inventory_items = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM invoices ORDER BY created_at DESC LIMIT 50")
    invoices = [dict(row) for row in cursor.fetchall()]

    cursor.execute("""
    SELECT c.name, c.phone, v.reg_number as vehicle_reg_no, v.make_model as vehicle_make_model
    FROM customers c
    LEFT JOIN vehicles v ON c.id = v.customer_id
    ORDER BY c.name ASC
    """)
    customers = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT gst_slabs FROM workshop_profile WHERE id = 'default'")
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
async def save_or_update_pos_invoice(payload: Dict[str, Any], invoice_id: Optional[str] = None):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    editing_id = invoice_id or payload.get("editing_invoice_id")
    workshop = get_current_workshop()
    now_ist = get_ist_now_str()
    today_str = get_ist_today_str()
    
    items = payload.get("items", [])
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
                VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'EDIT_RESTORE', ?, ?, ?)
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
            payload.get("customer_name", "Walk-in"), payload.get("customer_phone", "9876543210"),
            payload.get("vehicle_reg_no", ""),
            subtotal_labor, subtotal_parts, taxable_subtotal,
            cgst_total, sgst_total, igst_total, total_tax,
            discount, round_off, grand_total, amount_paid, balance_due,
            payment_status, payload.get("payment_mode", "UPI"), is_interstate,
            upi_link, now_ist, editing_id
        ))
        
        # 4. Adjust customer khata balance if balance changed
        old_bal = float(old_inv["balance_due"] or 0.0)
        bal_diff = balance_due - old_bal
        if bal_diff != 0 and payload.get("customer_phone"):
            cursor.execute("UPDATE customers SET khata_balance = MAX(0, khata_balance + ?) WHERE phone = ?", (bal_diff, payload.get("customer_phone").strip()))
            
        db.log_audit("EDIT_INVOICE", "invoices", editing_id, f"Updated bill #{inv_number} (New Total: ₹{grand_total:.2f}, Status: {payment_status})", cursor=cursor)
    else:
        # --- CREATE NEW INVOICE ---
        cursor.execute("SELECT COUNT(*) FROM invoices")
        cnt = cursor.fetchone()[0] + 1
        inv_number = f"INV-2026-{cnt:03d}"
        inv_id = f"inv_{uuid.uuid4().hex[:8]}"
        upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), pay_for_qr, f"Inv_{inv_number}")

        cursor.execute("""
        INSERT INTO invoices (
            id, invoice_number, invoice_date, invoice_type, job_card_id, job_number,
            customer_name, customer_phone, vehicle_reg_no,
            subtotal_labor, subtotal_parts, taxable_subtotal,
            cgst_total, sgst_total, igst_total, tax_total, discount_amount,
            round_off, grand_total, amount_paid, balance_due, payment_status, payment_mode,
            is_interstate, upi_payment_link, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inv_id, inv_number, today_str, payload.get("invoice_type", "JOB_SERVICE" if job_card_id else "COUNTER_SALE"),
            job_card_id, job_number,
            payload.get("customer_name", "Walk-in"), payload.get("customer_phone", "9876543210"),
            payload.get("vehicle_reg_no", ""),
            subtotal_labor, subtotal_parts, taxable_subtotal,
            cgst_total, sgst_total, igst_total, total_tax, discount,
            round_off, grand_total, amount_paid, balance_due, payment_status,
            payload.get("payment_mode", "UPI"), is_interstate, upi_link, now_ist
        ))
        
        # Update customer khata if unpaid/partial
        if balance_due > 0 and payload.get("customer_phone"):
            cursor.execute("UPDATE customers SET khata_balance = khata_balance + ? WHERE phone = ?", (balance_due, payload.get("customer_phone").strip()))

        # Record payment if amount_paid > 0
        if amount_paid > 0:
            pay_id = f"pay_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO payments (id, invoice_id, amount, payment_mode, payment_date, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (pay_id, inv_id, amount_paid, payload.get("payment_mode", "UPI"), today_str, f"Payment for {inv_number}", now_ist))

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
        
        if i.get("item_id") and not i.get("already_deducted"):
            cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (u_qty, i["item_id"]))
            log_id = f"stk_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, reference_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'SALE_OUT', ?, ?, ?)
            """, (log_id, i["item_id"], i.get("name"), i.get("barcode"), -u_qty, i["item_id"], inv_number, f"Billed in Invoice {inv_number}", now_ist))
            
    # If linked to job card, mark job card as COMPLETED
    if job_card_id:
        cursor.execute("UPDATE job_cards SET status = 'COMPLETED', completed_at = ? WHERE id = ?", (now_ist, job_card_id))

    conn.commit()
    conn.close()
    return {"success": True, "invoice_id": inv_id, "invoice_number": inv_number, "is_updated": bool(editing_id)}

@app.post("/api/invoices/{invoice_id}/cancel")
async def cancel_invoice_with_pin(invoice_id: str, payload: Dict[str, Any]):
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
    
    if inv["payment_status"] == "CANCELLED":
        conn.close()
        return {"success": True, "message": "Invoice is already cancelled"}

    now_ist = get_ist_now_str()
    invoice_number = inv["invoice_number"]

    # 1. Restore inventory stock for all parts in the invoice (Sales Return)
    cursor.execute("SELECT * FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
    items = cursor.fetchall()
    restored_parts_count = 0
    for itm in items:
        if itm["item_type"] == "PART" and itm["item_id"]:
            cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ?", (itm["quantity"], itm["item_id"]))
            log_id = f"stk_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, reference_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'SALES_RETURN', ?, ?, ?)
            """, (log_id, itm["item_id"], itm["name"], itm["barcode"], int(itm["quantity"]), itm["item_id"], invoice_number, f"Sales Return / Bill {invoice_number} Cancelled", now_ist))
            restored_parts_count += 1

    # 2. Record Sales Return entry
    sr_id = f"sr_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM sales_returns")
    cnt = cursor.fetchone()[0] + 1
    return_num = f"CN-2026-{cnt:03d}"
    try:
        cursor.execute("""
        INSERT INTO sales_returns (
            id, return_number, invoice_id, customer_name, customer_phone,
            item_id, item_name, quantity, refund_amount, return_reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sr_id, return_num, invoice_id, inv["customer_name"], inv["customer_phone"],
            "ALL", f"Sales Return for Bill #{invoice_number}", len(items),
            inv["grand_total"], "Invoice Cancelled & Stock Restored", now_ist
        ))
    except Exception:
        pass

    # 3. If there was an unpaid balance on customer khata, deduct it
    bal = float(inv["balance_due"] or 0.0)
    if bal > 0 and inv["customer_phone"]:
        cursor.execute("UPDATE customers SET khata_balance = MAX(0, khata_balance - ?) WHERE phone = ?", (bal, inv["customer_phone"].strip()))

    # 4. Mark invoice status as CANCELLED
    cursor.execute("""
    UPDATE invoices SET payment_status = 'CANCELLED', status = 'CANCELLED',
    notes = COALESCE(notes, '') || ' [CANCELLED on ' || ? || ' - Sales Return Restocked]'
    WHERE id = ?
    """, (now_ist, invoice_id))

    # 5. If linked to job card, update job card status
    if inv["job_card_id"]:
        cursor.execute("UPDATE job_cards SET status = 'IN_PROGRESS' WHERE id = ?", (inv["job_card_id"],))

    db.log_audit("CANCEL_INVOICE", "invoices", invoice_id, f"Cancelled #{invoice_number} and processed Sales Return (+stock restored)", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True, "message": f"Invoice #{invoice_number} cancelled and parts restored to inventory."}


@app.post("/api/invoices/{invoice_id}/record-payment")
async def record_invoice_payment(invoice_id: str, payload: Dict[str, Any]):
    amount = float(payload.get("amount", 0.0))
    mode = payload.get("payment_mode", "UPI")
    notes = payload.get("notes", "")

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    inv = cursor.fetchone()
    if not inv:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    old_paid = inv["amount_paid"] or 0.0
    new_paid = old_paid + amount
    grand_total = inv["grand_total"]
    new_balance = max(0.0, grand_total - new_paid)
    new_status = "PAID" if new_balance <= 0 else "PARTIAL"

    cursor.execute("""
    UPDATE invoices SET amount_paid = ?, balance_due = ?, payment_status = ?, payment_mode = ? WHERE id = ?
    """, (new_paid, new_balance, new_status, mode, invoice_id))

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
    
    workshop = get_current_workshop()
    pdf_bytes = generate_invoice_pdf_bytes(invoice, workshop)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=Invoice_{invoice['invoice_number']}.pdf"}
    )

@app.get("/api/invoices/{invoice_id}/whatsapp-link")
async def get_invoice_whatsapp_link(invoice_id: str):
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
    public_url = f"{APP_BASE_URL}/view/invoice/{invoice_id}"
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
async def get_job_whatsapp_link(job_id: str):
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
    public_url = f"{APP_BASE_URL}/view/job/{job_id}"
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
async def get_khata_reminder_link(invoice_id: str):
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
    msg = format_khata_due_reminder_whatsapp_message(
        workshop_name=workshop["name"],
        customer_name=inv["customer_name"],
        due_amount=inv["balance_due"],
        upi_payment_link=inv.get("upi_payment_link", ""),
        workshop_phone=workshop["phone"],
        lang=lang
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
    
    query = "SELECT * FROM inventory_items WHERE 1=1"
    params = []
    
    if filter == "low":
        query += " AND stock_qty <= min_stock_alert"
    elif category:
        query += " AND category = ?"
        params.append(category)
        
    query += " ORDER BY category, part_name"
    cursor.execute(query, params)
    items = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT COUNT(*) FROM inventory_items WHERE stock_qty <= min_stock_alert")
    low_stock_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT DISTINCT category FROM inventory_items WHERE category IS NOT NULL")
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
            "low_stock_count": low_stock_count
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
async def import_inventory_excel(file: UploadFile = File(...)):
    file_bytes = await file.read()
    items, errors = parse_inventory_file(file_bytes, file.filename)
    
    if not items:
        err_msg = ", ".join(errors) if errors else "No valid items found in file."
        raise HTTPException(status_code=400, detail=f"Import failed: {err_msg}")

    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    imported_count = 0
    for itm in items:
        cursor.execute("SELECT id FROM inventory_items WHERE barcode = ?", (itm["barcode"],))
        existing = cursor.fetchone()
        if existing:
            cursor.execute("""
            UPDATE inventory_items SET
                part_name = ?, part_number = COALESCE(NULLIF(?, ''), part_number), category = ?, stock_qty = stock_qty + ?,
                cost_price = ?, selling_price = ?, tax_rate = ?, hsn_code = ?,
                unit = ?, warranty_months = ?, location_rack = ?, position_bin = COALESCE(NULLIF(?, ''), position_bin), updated_at = datetime('now')
            WHERE id = ?
            """, (
                itm["part_name"], itm.get("part_number", ""), itm["category"], itm["stock_qty"],
                itm["cost_price"], itm["selling_price"], itm["tax_rate"], itm["hsn_code"],
                itm["unit"], itm["warranty_months"], itm["location_rack"], itm.get("position_bin", ""), existing["id"]
            ))
        else:
            item_id = f"item_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO inventory_items (
                id, part_name, part_number, sku, barcode, category, stock_qty, min_stock_alert,
                cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
                location_rack, position_bin, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 5, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                item_id, itm["part_name"], itm.get("part_number", ""), itm["barcode"], itm["barcode"], itm["category"],
                itm["stock_qty"], itm["cost_price"], itm["selling_price"], itm["tax_rate"],
                itm["hsn_code"], itm["unit"], itm["warranty_months"], itm["location_rack"], itm.get("position_bin", "")
            ))
        imported_count += 1

    db.log_audit("BULK_EXCEL_IMPORT", "inventory_items", "bulk", f"Imported {imported_count} parts from {file.filename}", cursor=cursor)
    conn.commit()
    conn.close()

    return RedirectResponse(url="/inventory", status_code=303)

@app.get("/api/inventory/scan/{barcode}")
async def scan_barcode_lookup(barcode: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory_items WHERE barcode = ? OR sku = ?", (barcode.strip(), barcode.strip()))
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
    cursor.execute("SELECT * FROM inventory_items ORDER BY part_name")
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
    item_id = f"item_{uuid.uuid4().hex[:8]}"
    clean_pn = (part_number or "").strip().upper()
    clean_rack = (location_rack or "Main").strip()
    clean_bin = (position_bin or "").strip()
    cursor.execute("""
    INSERT INTO inventory_items (
        id, part_name, part_number, sku, barcode, category, stock_qty, min_stock_alert,
        cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
        location_rack, position_bin, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, 5, ?, ?, ?, ?, 'pcs', ?, ?, ?, datetime('now'), datetime('now'))
    """, (item_id, part_name, clean_pn, barcode, barcode, category, stock_qty, cost_price, selling_price, tax_rate, hsn_code, warranty_months, clean_rack, clean_bin))
    
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
    cursor.execute("SELECT * FROM technicians ORDER BY total_jobs DESC")
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
    name: str = Form(...),
    phone: str = Form(...),
    role: str = Form("Senior Auto Electrician"),
    commission_pct: float = Form(10.0),
    notes: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    tech_id = f"tech_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO technicians (id, name, phone, role, commission_pct, status, is_on_leave, current_advance_balance, notes, total_jobs, created_at)
    VALUES (?, ?, ?, ?, ?, 'Active', 0, 0.0, ?, 0, datetime('now'))
    """, (tech_id, name, phone, role, commission_pct, notes))
    db.log_audit("ADD_TECHNICIAN", "technicians", tech_id, f"Added staff: {name} ({role})", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

@app.post("/api/technicians/{tech_id}/toggle-leave")
async def toggle_technician_leave(tech_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_on_leave, name FROM technicians WHERE id = ?", (tech_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")

    new_leave_state = 0 if row["is_on_leave"] == 1 else 1
    cursor.execute("UPDATE technicians SET is_on_leave = ? WHERE id = ?", (new_leave_state, tech_id))
    
    att_id = f"att_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    att_status = "ON_LEAVE" if new_leave_state == 1 else "PRESENT"
    cursor.execute("""
    INSERT INTO attendance (id, technician_id, date, status, created_at)
    VALUES (?, ?, ?, ?, datetime('now'))
    """, (att_id, tech_id, today_str, att_status))

    db.log_audit("TOGGLE_LEAVE", "technicians", tech_id, f"{row['name']} marked as {att_status}", cursor=cursor)
    conn.commit()
    conn.close()
    return {"success": True, "is_on_leave": bool(new_leave_state)}

@app.post("/api/technicians/advances")
async def record_technician_advance(
    technician_id: str = Form(...),
    amount: float = Form(...),
    payment_mode: str = Form("CASH"),
    notes: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM technicians WHERE id = ?", (technician_id,))
    tech = cursor.fetchone()
    if not tech:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")

    adv_id = f"adv_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO employee_advances (id, technician_id, technician_name, amount, advance_date, status, payment_mode, notes, created_at)
    VALUES (?, ?, ?, ?, ?, 'OUTSTANDING', ?, ?, datetime('now'))
    """, (adv_id, technician_id, tech["name"], amount, today_str, payment_mode, notes))

    cursor.execute("UPDATE technicians SET current_advance_balance = current_advance_balance + ? WHERE id = ?", (amount, technician_id))

    db.log_audit("STAFF_ADVANCE", "technicians", technician_id, f"Disbursed advance ₹{amount:.2f} to {tech['name']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

@app.post("/api/technicians/wages")
async def record_technician_wages(
    technician_id: str = Form(...),
    base_wages: float = Form(4000.0),
    commission_amount: float = Form(0.0),
    advance_deducted: float = Form(0.0),
    payment_mode: str = Form("CASH")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, current_advance_balance FROM technicians WHERE id = ?", (technician_id,))
    tech = cursor.fetchone()
    if not tech:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")

    gross = base_wages + commission_amount
    net_paid = max(0.0, gross - advance_deducted)
    wage_id = f"wage_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    start_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO employee_wages (
        id, technician_id, technician_name, period_start, period_end,
        gross_amount, advance_deducted, net_paid, payment_date, payment_mode, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        wage_id, technician_id, tech["name"], start_str, today_str,
        gross, advance_deducted, net_paid, today_str, payment_mode
    ))

    if advance_deducted > 0:
        cursor.execute("UPDATE technicians SET current_advance_balance = MAX(0.0, current_advance_balance - ?) WHERE id = ?", (advance_deducted, technician_id))

    db.log_audit("PAY_WAGES", "technicians", technician_id, f"Paid weekly wages ₹{net_paid:.2f} to {tech['name']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

@app.get("/api/technicians/{tech_id}/ledger")
async def get_technician_ledger(tech_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM technicians WHERE id = ?", (tech_id,))
    tech = cursor.fetchone()
    if not tech:
        conn.close()
        raise HTTPException(status_code=404, detail="Technician not found")
    
    tech_data = dict(tech)
    commission_pct = float(tech_data.get("commission_pct") or 0.0)

    # 1. Fetch Advances
    cursor.execute("""
        SELECT * FROM employee_advances 
        WHERE technician_id = ? 
        ORDER BY advance_date DESC, created_at DESC
    """, (tech_id,))
    advances = [dict(r) for r in cursor.fetchall()]

    # 2. Fetch Wages
    cursor.execute("""
        SELECT * FROM employee_wages 
        WHERE technician_id = ? 
        ORDER BY payment_date DESC, created_at DESC
    """, (tech_id,))
    wages = [dict(r) for r in cursor.fetchall()]

    # 3. Fetch Assigned Job Cards
    cursor.execute("""
        SELECT id, job_number, customer_name, customer_phone, vehicle_reg_no, vehicle_make_model,
               status, total_labor, total_parts, grand_total, created_at, completed_at, delivered_at
        FROM job_cards 
        WHERE assigned_technician_id = ? OR assigned_technician_name = ?
        ORDER BY created_at DESC
    """, (tech_id, tech_data["name"]))
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
    
    cursor.execute("SELECT * FROM purchase_bills ORDER BY bill_date DESC")
    purchases = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM purchase_returns ORDER BY return_date DESC")
    purchase_returns = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM inventory_items ORDER BY part_name")
    inventory_items = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM suppliers ORDER BY name")
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
    pur_id = f"pur_{uuid.uuid4().hex[:8]}"
    now_ist = get_ist_now_str()

    clean_sup_name = supplier_name.strip()
    # Resolve or create supplier record to maintain complete supplier history
    if not supplier_id and clean_sup_name:
        cursor.execute("SELECT id FROM suppliers WHERE LOWER(name) = LOWER(?)", (clean_sup_name,))
        s_row = cursor.fetchone()
        if s_row:
            supplier_id = s_row["id"]
        else:
            supplier_id = f"sup_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO suppliers (id, name, phone, state, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """, (supplier_id, clean_sup_name, "", supplier_state or "Kerala (32)"))

    if supplier_id:
        cursor.execute("UPDATE suppliers SET total_purchases = total_purchases + ? WHERE id = ?", (total_amount, supplier_id))

    cursor.execute("""
    INSERT INTO purchase_bills (
        id, bill_number, supplier_id, supplier_name, bill_date, total_amount, payment_mode, 
        status, notes, created_at, supplier_state, is_interstate, cgst_amount, sgst_amount, igst_amount
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pur_id, bill_number, supplier_id, clean_sup_name, bill_date, total_amount, payment_mode, 
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
                    cursor.execute("""
                    UPDATE inventory_items 
                    SET stock_qty = stock_qty + ?, cost_price = ? 
                    WHERE id = ?
                    """, (qty, unit_cost, part_id))

                    stk_id = f"stk_{uuid.uuid4().hex[:8]}"
                    cursor.execute("""
                    INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, unit_cost, reference_id, notes, created_at)
                    VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'PURCHASE_IN', ?, ?, ?, ?)
                    """, (stk_id, part_id, part_name, barcode, qty, part_id, unit_cost, bill_number, f"Supplier Bill #{bill_number} from {clean_sup_name}", now_ist))
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
            cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ?, cost_price = ? WHERE id = ?", (qty, unit_cost, part_id))
            stk_id = f"stk_{uuid.uuid4().hex[:8]}"
            cursor.execute("""
            INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, unit_cost, reference_id, notes, created_at)
            VALUES (?, ?, ?, ?, ?, (SELECT stock_qty FROM inventory_items WHERE id = ?), 'PURCHASE_IN', ?, ?, ?, ?)
            """, (stk_id, part_id, itm.get("part_name"), itm.get("barcode"), qty, part_id, unit_cost, pur["bill_number"], f"Confirmed Supplier Bill #{pur['bill_number']}", now_ist))

    cursor.execute("UPDATE purchase_bills SET status = 'CONFIRMED' WHERE id = ?", (pur_id,))
    db.log_audit("CONFIRM_PURCHASE", "purchase_bills", pur_id, f"Confirmed Purchase Bill #{pur['bill_number']}", cursor=cursor)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/purchases", status_code=303)

@app.post("/api/purchases/returns")
async def record_purchase_return(
    supplier_name: str = Form(...),
    item_id: str = Form(...),
    quantity: int = Form(1),
    return_amount: float = Form(...),
    reason: str = Form("Defective Part")
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT part_name, cost_price FROM inventory_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    ret_id = f"pr_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM purchase_returns")
    cnt = cursor.fetchone()[0] + 1
    return_number = f"DN-2026-{cnt:03d}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO purchase_returns (id, return_number, supplier_name, item_id, part_name, quantity, unit_cost, return_amount, return_date, reason, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (ret_id, return_number, supplier_name, item_id, item["part_name"], quantity, item["cost_price"], return_amount, today_str, reason))

    cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (quantity, item_id))

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
    
    cursor.execute("""
    SELECT s.*, 
           COUNT(DISTINCT pb.id) as total_bills,
           COALESCE(SUM(pb.total_amount), 0.0) as calculated_total_purchases
    FROM suppliers s
    LEFT JOIN purchase_bills pb ON s.id = pb.supplier_id OR LOWER(s.name) = LOWER(pb.supplier_name)
    GROUP BY s.id
    ORDER BY s.name
    """)
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
    sup_id = f"sup_{uuid.uuid4().hex[:8]}"
    
    cursor.execute("""
    INSERT INTO suppliers (
        id, name, contact_person, phone, whatsapp, email, address, city, state, gstin, payment_terms, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (sup_id, name.strip(), contact_person, phone.strip(), whatsapp or phone.strip(), email, address, city, state, gstin, payment_terms, notes))
    
    db.log_audit("CREATE_SUPPLIER", "suppliers", sup_id, f"Created supplier {name}", cursor=cursor)
    conn.commit()
    return RedirectResponse(url="/suppliers", status_code=303)

@app.post("/api/suppliers/quick-create")
async def quick_create_supplier(payload: Dict[str, Any]):
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
        id, name, contact_person, phone, whatsapp, email, address, city, state, gstin, payment_terms, notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (sup_id, name, contact_person, phone, phone, None, None, city, state, gstin, None, None))

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
async def get_supplier_details(supplier_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
    sup_row = cursor.fetchone()
    if not sup_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Supplier not found")
    supplier = dict(sup_row)
    
    # Get purchase bills
    cursor.execute("SELECT * FROM purchase_bills WHERE supplier_id = ? OR LOWER(supplier_name) = LOWER(?) ORDER BY bill_date DESC", (supplier_id, supplier["name"]))
    bills = [dict(r) for r in cursor.fetchall()]
    
    # Get all distinct products supplied
    cursor.execute("""
    SELECT pi.part_name, pi.barcode, pi.unit_cost, pi.quantity, pi.total_cost, pb.bill_number, pb.bill_date
    FROM purchase_items pi
    JOIN purchase_bills pb ON pi.purchase_id = pb.id
    WHERE pb.supplier_id = ? OR LOWER(pb.supplier_name) = LOWER(?)
    ORDER BY pb.bill_date DESC
    """, (supplier_id, supplier["name"]))
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
async def quick_create_inventory_item(payload: Dict[str, Any]):
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
        id, part_name, part_number, sku, barcode, category, stock_qty, min_stock_alert,
        cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
        location_rack, position_bin,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, 0, 5, ?, ?, ?, ?, 'pcs', 6, ?, ?, datetime('now'), datetime('now'))
    """, (item_id, part_name, part_number, barcode, barcode, category, cost_price, selling_price, tax_rate, hsn_code, location_rack, position_bin))
    
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
    cursor.execute("SELECT * FROM sales_returns ORDER BY return_date DESC")
    returns = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM inventory_items ORDER BY part_name")
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
    cursor.execute("SELECT part_name, selling_price FROM inventory_items WHERE id = ?", (item_id,))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Item not found")

    sr_id = f"sr_{uuid.uuid4().hex[:8]}"
    cursor.execute("SELECT COUNT(*) FROM sales_returns")
    cnt = cursor.fetchone()[0] + 1
    return_number = f"CN-2026-{cnt:03d}"
    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    INSERT INTO sales_returns (id, return_number, invoice_id, customer_name, item_id, name, quantity, unit_price, refund_amount, return_date, refund_mode, reason, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (sr_id, return_number, invoice_id, customer_name, item_id, item["part_name"], quantity, item["selling_price"], refund_amount, today_str, refund_mode, reason))

    cursor.execute("UPDATE inventory_items SET stock_qty = stock_qty + ? WHERE id = ?", (quantity, item_id))

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
    cursor.execute("""
    SELECT v.*, c.khata_balance, c.total_visits, c.id as cust_id
    FROM vehicles v
    LEFT JOIN customers c ON v.customer_id = c.id OR v.customer_phone = c.phone
    ORDER BY v.created_at DESC
    """)
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
async def get_customer_history(customer_id_or_phone: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM customers WHERE id = ? OR phone = ? LIMIT 1", (customer_id_or_phone, customer_id_or_phone))
    c_row = cursor.fetchone()
    
    veh_row = None
    if not c_row:
        cursor.execute("SELECT * FROM vehicles WHERE reg_number = ? LIMIT 1", (customer_id_or_phone.strip().upper(),))
        veh_row = cursor.fetchone()
        if veh_row and veh_row["customer_phone"]:
            cursor.execute("SELECT * FROM customers WHERE phone = ? LIMIT 1", (veh_row["customer_phone"],))
            c_row = cursor.fetchone()

    customer = dict(c_row) if c_row else None
    
    vehicles = []
    if customer:
        cursor.execute("SELECT * FROM vehicles WHERE customer_id = ? OR customer_phone = ?", (customer["id"], customer["phone"]))
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
        params = []
        if cust_phone:
            conditions.append("customer_phone = ?")
            params.append(cust_phone)
        if veh_regs:
            placeholders = ",".join(["?"] * len(veh_regs))
            conditions.append(f"vehicle_reg_no IN ({placeholders})")
            params.extend(veh_regs)
        
        where_clause = " OR ".join(conditions)
        cursor.execute(f"SELECT * FROM job_cards WHERE {where_clause} ORDER BY created_at DESC", tuple(params))
        job_cards = [dict(r) for r in cursor.fetchall()]

        cursor.execute(f"SELECT * FROM invoices WHERE {where_clause} ORDER BY created_at DESC", tuple(params))
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
    cursor.execute("SELECT * FROM bank_accounts ORDER BY is_primary DESC, current_balance DESC")
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
    acc_id = f"bank_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO bank_accounts (id, account_name, bank_name, account_type, account_number, ifsc_code, upi_vpa, current_balance, is_primary, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
    """, (acc_id, account_name, bank_name, account_type, account_number, ifsc_code, upi_vpa, current_balance))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/bank-accounts", status_code=303)

@app.get("/expenses", response_class=HTMLResponse)
async def expenses_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses ORDER BY expense_date DESC, created_at DESC")
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
    exp_id = f"exp_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO expenses (id, title, category, amount, payment_mode, expense_date, paid_to, reference_no, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (exp_id, title, category, amount, payment_mode, expense_date, paid_to, reference_no))
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
    fy_dates = ca_reports.get_financial_year_dates(financial_year)
    s_date = start_date or fy_dates["start_date"]
    e_date = end_date or fy_dates["end_date"]

    gstr1 = ca_reports.generate_gstr1_report(s_date, e_date)
    pnl = ca_reports.generate_profit_and_loss_report(s_date, e_date)
    valuation = ca_reports.generate_inventory_valuation_report()
    collections = ca_reports.generate_daily_collection_register(s_date, e_date)

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
async def export_ca_gstr1_excel(financial_year: Optional[str] = None):
    fy_dates = ca_reports.get_financial_year_dates(financial_year)
    excel_bytes = ca_reports.export_gstr1_excel(fy_dates["start_date"], fy_dates["end_date"])
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=GSTR1_Audit_Report_{fy_dates['financial_year']}.xlsx"}
    )

@app.get("/khata", response_class=HTMLResponse)
async def khata_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM invoices WHERE balance_due > 0 ORDER BY invoice_date DESC")
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
    profile = get_current_workshop()
    saas_info = check_saas_subscription()
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
    cursor.execute("""
    UPDATE workshop_profile SET
        name = ?, subtitle = ?, phone = ?, email = ?, address = ?, gstin = ?,
        upi_id = ?, bank_name = ?, bank_account_no = ?, bank_ifsc = ?, bank_branch = ?,
        language = ?, master_pin = ?, terms = ?,
        default_state = ?, tax_regime = ?, round_off_enabled = ?,
        updated_at = datetime('now')
    WHERE id = 'default'
    """, (name, subtitle, phone, email, address, gstin, upi_id, bank_name, bank_account_no, bank_ifsc, bank_branch, whatsapp_lang, master_pin, terms, default_state, tax_regime, round_off_enabled))
    db.log_audit("UPDATE_PROFILE", "workshop_profile", "default", f"Updated garage profile ({name})", cursor=cursor)
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
    
    workshop = get_current_workshop()
    
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
        
    workshop = get_current_workshop()
    
    return templates.TemplateResponse(
        request=request,
        name="public_job_view.html",
        context={
            "job": job,
            "complaints_list": complaints_list,
            "workshop": workshop
        }
    )

@app.get("/invoice/{invoice_id}/print")
async def print_invoice_page(request: Request, invoice_id: str):
    return RedirectResponse(url=f"/api/invoices/{invoice_id}/pdf", status_code=303)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
