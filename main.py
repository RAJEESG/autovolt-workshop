import os
import io
import json
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, Form, Response, Query
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

app = FastAPI(title="AutoVolt Pro — Auto Electrical Workshop Management", version="1.0.0")

# Mount Static Files & Templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helper: Get current workshop profile
def get_current_workshop() -> Dict[str, Any]:
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM workshop_profile WHERE id = 'default'")
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
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
        "currency": "₹",
        "terms": "1. Electrical parts warranty as per manufacturer.\n2. Goods once fitted cannot be returned."
    }

# Base URL for public links
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

# =========================================================
# 📊 PAGE ROUTES (HTML FRONTEND)
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Metrics
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
    
    # Active Jobs
    cursor.execute("SELECT * FROM job_cards WHERE status NOT IN ('DELIVERED', 'CANCELLED') ORDER BY created_at DESC LIMIT 6")
    active_jobs = [dict(row) for row in cursor.fetchall()]
    
    # Technicians
    cursor.execute("SELECT * FROM technicians ORDER BY total_jobs DESC")
    technicians = [dict(row) for row in cursor.fetchall()]
    
    # Recent Invoices
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
async def job_cards_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM job_cards ORDER BY created_at DESC")
    all_jobs = [dict(row) for row in cursor.fetchall()]
    
    # Group by Kanban status
    jobs_by_status = {
        "RECEIVED": [],
        "INSPECTION": [],
        "IN_PROGRESS": [],
        "COMPLETED": [],
        "DELIVERED": []
    }
    for job in all_jobs:
        st = job["status"]
        if st in jobs_by_status:
            jobs_by_status[st].append(job)
        else:
            jobs_by_status["IN_PROGRESS"].append(job)
            
    cursor.execute("SELECT * FROM technicians WHERE status = 'Active'")
    technicians = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="job_cards.html",
        context={
            "active_page": "job_cards",
            "jobs_by_status": jobs_by_status,
            "technicians": technicians
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
    
    # Parse complaints list
    try:
        complaints_list = json.loads(job["complaints"]) if job["complaints"] else []
    except Exception:
        complaints_list = [job["complaints"]] if job["complaints"] else []
        
    # Get Line Items
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    items = [dict(row) for row in cursor.fetchall()]
    
    # Calculate totals
    total_labor = sum(i["total_price"] for i in items if i["item_type"] == "LABOR")
    total_parts = sum(i["total_price"] for i in items if i["item_type"] == "PART")
    grand_total = total_labor + total_parts
    
    # Technicians & Inventory Items
    cursor.execute("SELECT * FROM technicians WHERE status = 'Active'")
    technicians = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM inventory_items WHERE stock_qty > 0 ORDER BY part_name")
    inventory_items = [dict(row) for row in cursor.fetchall()]
    
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
            "inventory_items": inventory_items
        }
    )

@app.get("/billing", response_class=HTMLResponse)
async def billing_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM inventory_items ORDER BY part_name")
    inventory_items = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM invoices ORDER BY created_at DESC LIMIT 50")
    invoices = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="billing.html",
        context={
            "active_page": "billing",
            "inventory_items": inventory_items,
            "invoices": invoices
        }
    )

@app.get("/barcode-labels", response_class=HTMLResponse)
async def barcode_labels_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory_items ORDER BY part_name")
    inventory_items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="barcode_labels.html",
        context={
            "active_page": "barcode_labels",
            "inventory_items": inventory_items
        }
    )

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

@app.get("/technicians", response_class=HTMLResponse)
async def technicians_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM technicians ORDER BY total_jobs DESC")
    technicians = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="technicians.html",
        context={
            "active_page": "technicians",
            "technicians": technicians
        }
    )

@app.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vehicles ORDER BY created_at DESC")
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

@app.get("/ca-reports", response_class=HTMLResponse)
async def ca_reports_page(request: Request, start_date: Optional[str] = None, end_date: Optional[str] = None):
    gstr1 = ca_reports.generate_gstr1_report(start_date, end_date)
    pnl = ca_reports.generate_profit_and_loss_report(start_date, end_date)
    valuation = ca_reports.generate_inventory_valuation_report()
    
    return templates.TemplateResponse(
        request=request,
        name="ca_reports.html",
        context={
            "active_page": "ca_reports",
            "gstr1": gstr1,
            "pnl": pnl,
            "valuation": valuation,
            "start_date": start_date or "",
            "end_date": end_date or ""
        }
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

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    profile = get_current_workshop()
    is_supabase_connected = bool(db.supabase_client)
    
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_page": "settings",
            "profile": profile,
            "is_supabase_connected": is_supabase_connected
        }
    )

# =========================================================
# 🌐 PUBLIC CUSTOMER VIEWS & PRINT FORMATS
# =========================================================

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
    
    # Dynamic UPI QR Code
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

@app.get("/invoice/{invoice_id}/print", response_class=HTMLResponse)
async def print_invoice_page(request: Request, invoice_id: str, format: str = Query("a4")):
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
    
    # UPI QR for Thermal
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    grand_total = float(invoice.get("grand_total", 0.0))
    upi_link = invoice.get("upi_payment_link") or generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), grand_total, f"Inv_{invoice.get('invoice_number')}")
    upi_qr_url = generate_upi_qr_data_url(upi_link)
    
    return templates.TemplateResponse(
        request=request,
        name="print_invoice.html",
        context={
            "invoice": invoice,
            "items": invoice["items"],
            "workshop": workshop,
            "print_format": format,
            "upi_qr_url": upi_qr_url
        }
    )

# =========================================================
# ⚡ REST APIS (BARCODE POS, INVENTORY, JOBS, INVOICES)
# =========================================================

@app.get("/api/inventory/scan/{barcode}")
async def scan_barcode_lookup(barcode: str):
    """Instant lookup of item by barcode for USB/Bluetooth Gun Scanner or Camera"""
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
    """Return inline SVG for barcode sticker printing"""
    svg = generate_barcode_svg(barcode)
    return {"barcode": barcode, "svg": svg}

@app.post("/api/inventory")
async def add_inventory_item(
    part_name: str = Form(...),
    barcode: str = Form(...),
    category: str = Form("Relays & Fuses"),
    stock_qty: int = Form(10),
    cost_price: float = Form(0.0),
    selling_price: float = Form(0.0),
    tax_rate: float = Form(18.0),
    hsn_code: str = Form("8536"),
    warranty_months: int = Form(0)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    item_id = f"item_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO inventory_items (
        id, part_name, sku, barcode, category, stock_qty, min_stock_alert,
        cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (item_id, part_name, barcode, barcode, category, stock_qty, 5, cost_price, selling_price, tax_rate, hsn_code, "pcs", warranty_months))
    
    # Audit log
    db.log_audit("ADD_INVENTORY_PART", "inventory_items", item_id, f"Added part: {part_name} (Barcode: {barcode})")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/inventory", status_code=303)

@app.post("/api/inventory/adjust")
async def adjust_inventory_stock(
    item_id: str = Form(...),
    action_type: str = Form("PURCHASE"),
    change_qty: int = Form(...)
):
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
    
    # Stock Log
    log_id = f"stk_{uuid.uuid4().hex[:8]}"
    cursor.execute("""
    INSERT INTO stock_logs (id, item_id, part_name, barcode, change_qty, new_stock_qty, action_type, unit_cost, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (log_id, item_id, row["part_name"], row["barcode"], change_qty, new_qty, action_type, row["cost_price"]))
    
    conn.commit()
    conn.close()
    return RedirectResponse(url="/inventory", status_code=303)

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
    
    # Generate sequential Job Number
    cursor.execute("SELECT COUNT(*) FROM job_cards")
    cnt = cursor.fetchone()[0] + 1
    job_number = f"JOB-2026-{cnt:03d}"
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    
    # Technician Name
    tech_name = None
    if assigned_technician_id:
        cursor.execute("SELECT name FROM technicians WHERE id = ?", (assigned_technician_id,))
        t_row = cursor.fetchone()
        if t_row:
            tech_name = t_row["name"]
            
    # Customer / Vehicle Record update
    cursor.execute("SELECT id FROM customers WHERE phone = ?", (customer_phone.strip(),))
    c_row = cursor.fetchone()
    if c_row:
        customer_id = c_row["id"]
        cursor.execute("UPDATE customers SET total_visits = total_visits + 1 WHERE id = ?", (customer_id,))
    else:
        customer_id = f"cust_{uuid.uuid4().hex[:8]}"
        cursor.execute("INSERT INTO customers (id, name, phone, created_at) VALUES (?, ?, ?, datetime('now'))", (customer_id, customer_name, customer_phone))
        
    cursor.execute("SELECT id FROM vehicles WHERE reg_number = ?", (vehicle_reg_no.strip().upper(),))
    v_row = cursor.fetchone()
    if v_row:
        vehicle_id = v_row["id"]
        cursor.execute("UPDATE vehicles SET odometer = ? WHERE id = ?", (odometer, vehicle_id))
    else:
        vehicle_id = f"veh_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO vehicles (id, reg_number, customer_id, customer_name, customer_phone, make_model, odometer, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (vehicle_id, vehicle_reg_no.strip().upper(), customer_id, customer_name, customer_phone, vehicle_make_model, odometer))
        
    # Insert Job Card
    complaints_json = json.dumps(complaints)
    cursor.execute("""
    INSERT INTO job_cards (
        id, job_number, customer_id, customer_name, customer_phone, vehicle_id, vehicle_reg_no,
        vehicle_make_model, odometer, assigned_technician_id, assigned_technician_name,
        status, complaints, custom_complaint_notes, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'RECEIVED', ?, ?, datetime('now'))
    """, (
        job_id, job_number, customer_id, customer_name, customer_phone, vehicle_id,
        vehicle_reg_no.strip().upper(), vehicle_make_model, odometer, assigned_technician_id,
        tech_name, complaints_json, custom_complaint_notes
    ))
    
    db.log_audit("CREATE_JOB_CARD", "job_cards", job_id, f"Job {job_number} for {vehicle_reg_no}")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

@app.post("/api/job-cards/{job_id}/status")
async def update_job_status(job_id: str, status: str = Form(...)):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE job_cards SET status = ? WHERE id = ?", (status, job_id))
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
    tax_rate = 18.0
    
    if item_type == "PART" and item_id:
        cursor.execute("SELECT * FROM inventory_items WHERE id = ?", (item_id,))
        p_row = cursor.fetchone()
        if p_row:
            name = p_row["part_name"]
            barcode = p_row["barcode"]
            hsn_code = p_row["hsn_code"] or "8536"
            tax_rate = p_row["tax_rate"] or 18.0
            if unit_price is None or unit_price == 0:
                unit_price = p_row["selling_price"]
                
            # Automatically reduce stock from inventory
            cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (quantity, item_id))
    else:
        hsn_code = "9987" # Service Code
        tax_rate = 0.0
        
    line_total = (unit_price or 0.0) * quantity
    line_id = f"ji_{uuid.uuid4().hex[:8]}"
    
    cursor.execute("""
    INSERT INTO job_items (
        id, job_card_id, item_type, item_id, barcode, name, hsn_code,
        quantity, unit_price, tax_rate, total_price, technician_id, technician_name
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        line_id, job_id, item_type, item_id, barcode, name or "Labor Charge",
        hsn_code, quantity, unit_price or 0.0, tax_rate, line_total, technician_id, tech_name
    ))
    
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

@app.post("/api/job-cards/{job_id}/items/{item_id}/delete")
async def delete_job_card_item(job_id: str, item_id: str):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM job_items WHERE id = ? AND job_card_id = ?", (item_id, job_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/job-cards/{job_id}", status_code=303)

@app.post("/api/job-cards/{job_id}/create-invoice")
async def convert_job_card_to_invoice(job_id: str):
    """Convert completed Job Card to official Invoice"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM job_cards WHERE id = ?", (job_id,))
    job = cursor.fetchone()
    if not job:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")
        
    cursor.execute("SELECT * FROM job_items WHERE job_card_id = ?", (job_id,))
    items = [dict(row) for row in cursor.fetchall()]
    
    # Generate sequential Invoice Number
    cursor.execute("SELECT COUNT(*) FROM invoices")
    cnt = cursor.fetchone()[0] + 1
    invoice_number = f"INV-2026-{cnt:03d}"
    invoice_id = f"inv_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    subtotal_labor = sum(i["total_price"] for i in items if i["item_type"] == "LABOR")
    subtotal_parts = sum(i["total_price"] for i in items if i["item_type"] == "PART")
    grand_total = subtotal_labor + subtotal_parts
    
    workshop = get_current_workshop()
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), grand_total, f"Inv_{invoice_number}")
    
    # Insert Invoice
    cursor.execute("""
    INSERT INTO invoices (
        id, invoice_number, invoice_date, invoice_type, job_card_id, job_number,
        customer_id, customer_name, customer_phone, vehicle_reg_no, vehicle_make_model,
        odometer, subtotal_labor, subtotal_parts, taxable_subtotal, grand_total,
        amount_paid, balance_due, payment_status, payment_mode, upi_payment_link, created_at
    ) VALUES (?, ?, ?, 'JOB_SERVICE', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PAID', 'UPI', ?, datetime('now'))
    """, (
        invoice_id, invoice_number, today_str, job_id, job["job_number"],
        job["customer_id"], job["customer_name"], job["customer_phone"],
        job["vehicle_reg_no"], job["vehicle_make_model"], job["odometer"],
        subtotal_labor, subtotal_parts, grand_total, grand_total, grand_total,
        0.0, upi_link
    ))
    
    # Insert Invoice Items
    for i in items:
        inv_item_id = f"ii_{uuid.uuid4().hex[:8]}"
        cursor.execute("""
        INSERT INTO invoice_items (
            id, invoice_id, item_type, item_id, barcode, name, hsn_sac,
            quantity, unit_price, tax_rate, taxable_amount, total_price, technician_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inv_item_id, invoice_id, i["item_type"], i["item_id"], i["barcode"],
            i["name"], i["hsn_code"] or "8536", i["quantity"], i["unit_price"],
            i["tax_rate"], i["total_price"], i["total_price"], i["technician_name"]
        ))
        
    # Mark Job as COMPLETED
    cursor.execute("UPDATE job_cards SET status = 'COMPLETED', completed_at = datetime('now') WHERE id = ?", (job_id,))
    
    # Update Technician stats
    if job["assigned_technician_id"]:
        cursor.execute("UPDATE technicians SET total_jobs = total_jobs + 1 WHERE id = ?", (job["assigned_technician_id"],))
        
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/billing", status_code=303)

@app.post("/api/invoices")
async def create_pos_invoice(payload: Dict[str, Any]):
    """Create Rapid POS Barcode Bill"""
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM invoices")
    cnt = cursor.fetchone()[0] + 1
    invoice_number = f"INV-2026-{cnt:03d}"
    invoice_id = f"inv_{uuid.uuid4().hex[:8]}"
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    items = payload.get("items", [])
    subtotal_labor = sum(i["unit_price"] * i["quantity"] for i in items if i.get("item_type") == "LABOR")
    subtotal_parts = sum(i["unit_price"] * i["quantity"] for i in items if i.get("item_type") == "PART")
    discount = float(payload.get("discount_amount", 0.0))
    grand_total = max(0.0, (subtotal_labor + subtotal_parts) - discount)
    amount_paid = float(payload.get("amount_paid", grand_total))
    balance_due = max(0.0, grand_total - amount_paid)
    payment_status = "PAID" if balance_due <= 0 else ("PARTIAL" if amount_paid > 0 else "UNPAID")
    
    workshop = get_current_workshop()
    vpa = workshop.get("upi_id", "sparkautoworkshop@okaxis")
    upi_link = generate_upi_link(vpa, workshop.get("name", "Auto Workshop"), grand_total, f"Inv_{invoice_number}")
    
    cursor.execute("""
    INSERT INTO invoices (
        id, invoice_number, invoice_date, invoice_type,
        customer_name, customer_phone, vehicle_reg_no,
        subtotal_labor, subtotal_parts, taxable_subtotal, discount_amount,
        grand_total, amount_paid, balance_due, payment_status, payment_mode,
        upi_payment_link, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        invoice_id, invoice_number, today_str, payload.get("invoice_type", "COUNTER_SALE"),
        payload.get("customer_name", "Walk-in"), payload.get("customer_phone", "9876543210"),
        payload.get("vehicle_reg_no", ""),
        subtotal_labor, subtotal_parts, grand_total, discount,
        grand_total, amount_paid, balance_due, payment_status,
        payload.get("payment_mode", "UPI"), upi_link
    ))
    
    # Line items & Inventory Stock Deductions
    for i in items:
        inv_item_id = f"ii_{uuid.uuid4().hex[:8]}"
        line_total = i["unit_price"] * i["quantity"]
        cursor.execute("""
        INSERT INTO invoice_items (
            id, invoice_id, item_type, item_id, barcode, name, hsn_sac,
            quantity, unit_price, tax_rate, taxable_amount, total_price
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inv_item_id, invoice_id, i.get("item_type", "PART"), i.get("item_id"),
            i.get("barcode"), i.get("name", "Item"), i.get("hsn_sac", "8536"),
            i["quantity"], i["unit_price"], i.get("tax_rate", 18.0),
            line_total, line_total
        ))
        
        # Deduct stock if inventory item
        if i.get("item_id"):
            cursor.execute("UPDATE inventory_items SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (i["quantity"], i["item_id"]))
            
    conn.commit()
    conn.close()
    return {"success": True, "invoice_id": invoice_id, "invoice_number": invoice_number}

@app.get("/api/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(invoice_id: str):
    """Download crisp A4 PDF invoice"""
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
    """Generate 1-Click WhatsApp sharing URL"""
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
        workshop_phone=workshop["phone"]
    )
    
    wa_url = generate_wa_me_url(inv["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}

@app.get("/api/job-cards/{job_id}/whatsapp-link")
async def get_job_whatsapp_link(job_id: str):
    """Generate WhatsApp status update link for Job Card"""
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
        workshop_phone=workshop["phone"]
    )
    
    wa_url = generate_wa_me_url(job["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}

@app.get("/api/invoices/{invoice_id}/khata-reminder-link")
async def get_khata_reminder_link(invoice_id: str):
    """Generate WhatsApp payment reminder for khata dues"""
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
    msg = format_khata_due_reminder_whatsapp_message(
        workshop_name=workshop["name"],
        customer_name=inv["customer_name"],
        due_amount=inv["balance_due"],
        upi_payment_link=inv.get("upi_payment_link", ""),
        workshop_phone=workshop["phone"]
    )
    
    wa_url = generate_wa_me_url(inv["customer_phone"], msg)
    return {"whatsapp_url": wa_url, "message": msg}

@app.get("/api/ca-reports/export-gstr1-excel")
async def export_ca_gstr1_excel():
    """Download GSTR-1 Excel for CA"""
    excel_bytes = ca_reports.export_gstr1_excel()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=GSTR1_Sales_Audit_Report.xlsx"}
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
    INSERT INTO technicians (id, name, phone, role, commission_pct, status, notes, total_jobs, created_at)
    VALUES (?, ?, ?, ?, ?, 'Active', ?, 0, datetime('now'))
    """, (tech_id, name, phone, role, commission_pct, notes))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/technicians", status_code=303)

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
    terms: Optional[str] = Form(None)
):
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE workshop_profile SET
        name = ?, subtitle = ?, phone = ?, email = ?, address = ?, gstin = ?,
        upi_id = ?, bank_name = ?, bank_account_no = ?, bank_ifsc = ?, bank_branch = ?,
        terms = ?, updated_at = datetime('now')
    WHERE id = 'default'
    """, (name, subtitle, phone, email, address, gstin, upi_id, bank_name, bank_account_no, bank_ifsc, bank_branch, terms))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/settings", status_code=303)

# If executed directly
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
