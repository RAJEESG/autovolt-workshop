import os
import sqlite3
import json
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from auth_helper import hash_password
from tz_helper import get_ist_now_str

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY") or "").strip()

supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client, Client
        cleaned_url = SUPABASE_URL.rstrip("/")
        if cleaned_url.endswith("/rest/v1"):
            cleaned_url = cleaned_url[:-8].rstrip("/")
        supabase_client = create_client(cleaned_url, SUPABASE_KEY)
        print("[Database] Connected successfully to Supabase Cloud Database.")
    except Exception as e:
        print(f"[Database] Supabase connection failed: {e}. Falling back to SQLite.")
        supabase_client = None

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workshop.db")

def get_db_connection():
    """Get SQLite connection with row factory, WAL mode, and busy timeout"""
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db():
    """Initialize SQLite database with complete enterprise tables and seed initial data"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users Table (Auth)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT DEFAULT 'STAFF',
        email TEXT,
        phone TEXT,
        whatsapp_mobile TEXT,
        status TEXT DEFAULT 'ACTIVE',
        tenant_id TEXT DEFAULT 'tenant_spark_auto',
        reset_token TEXT,
        reset_token_expiry TEXT,
        otp_code TEXT,
        otp_expiry TEXT,
        created_at TEXT
    );
    """)

    # 2. Tenants (SaaS Workshop Clients) Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_name TEXT,
        phone TEXT NOT NULL,
        whatsapp_mobile TEXT,
        email TEXT,
        address TEXT NOT NULL,
        gstin TEXT,
        logo_url TEXT,
        upi_id TEXT NOT NULL,
        upi_payee_name TEXT,
        bank_name TEXT,
        bank_account_no TEXT,
        bank_ifsc TEXT,
        bank_branch TEXT,
        gst_slabs TEXT DEFAULT '["0", "5", "12", "18", "28"]',
        language TEXT DEFAULT 'en',
        master_pin TEXT DEFAULT '1234',
        status TEXT DEFAULT 'ACTIVE',
        subscription_plan TEXT DEFAULT 'PRO_ANNUAL',
        subscription_start_date TEXT,
        subscription_end_date TEXT,
        price_paid REAL DEFAULT 0.0,
        created_at TEXT
    );
    """)

    # 3. SaaS Subscriptions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        plan_name TEXT DEFAULT 'PRO_ANNUAL',
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        billing_cycle TEXT DEFAULT 'YEARLY',
        price_paid REAL DEFAULT 0.0,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 3B. SaaS Vendor Invoices (SaaS Company Invoices to Garages)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saas_vendor_invoices (
        id TEXT PRIMARY KEY,
        invoice_no TEXT UNIQUE NOT NULL,
        tenant_id TEXT NOT NULL,
        tenant_name TEXT NOT NULL,
        invoice_date TEXT NOT NULL,
        plan_type TEXT DEFAULT 'YEARLY',
        subscription_start TEXT,
        subscription_end TEXT,
        taxable_amount REAL DEFAULT 0.0,
        cgst_rate REAL DEFAULT 9.0,
        cgst_amount REAL DEFAULT 0.0,
        sgst_rate REAL DEFAULT 9.0,
        sgst_amount REAL DEFAULT 0.0,
        total_amount REAL DEFAULT 0.0,
        payment_status TEXT DEFAULT 'PAID',
        payment_mode TEXT DEFAULT 'UPI',
        payment_ref TEXT,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 3C. SaaS Vendor Company Profile (SaaS Provider Books)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS saas_vendor_profile (
        id TEXT PRIMARY KEY,
        company_name TEXT NOT NULL,
        tagline TEXT,
        gstin TEXT,
        email TEXT,
        phone TEXT,
        whatsapp_phone TEXT,
        address TEXT,
        upi_id TEXT,
        upi_payee_name TEXT,
        bank_name TEXT,
        bank_account_no TEXT,
        bank_ifsc TEXT,
        monthly_fee REAL DEFAULT 999.0,
        yearly_fee REAL DEFAULT 9999.0,
        updated_at TEXT
    );
    """)

    # 4. Workshop Profile Table (Current Active Tenant Profile)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workshop_profile (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        subtitle TEXT,
        owner_name TEXT,
        phone TEXT NOT NULL,
        email TEXT,
        address TEXT NOT NULL,
        gstin TEXT,
        logo_url TEXT,
        upi_id TEXT NOT NULL,
        upi_payee_name TEXT,
        bank_name TEXT,
        bank_account_no TEXT,
        bank_ifsc TEXT,
        bank_branch TEXT,
        gst_slabs TEXT DEFAULT '["0", "5", "12", "18", "28"]',
        language TEXT DEFAULT 'en',
        currency TEXT DEFAULT '₹',
        master_pin TEXT DEFAULT '1234',
        terms TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """)

    # 5. Technicians & Staff Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS technicians (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        role TEXT DEFAULT 'Senior Electrician',
        commission_pct REAL DEFAULT 0.0,
        daily_wage REAL DEFAULT 0.0,
        status TEXT DEFAULT 'Active',
        is_on_leave INTEGER DEFAULT 0,
        current_advance_balance REAL DEFAULT 0.0,
        notes TEXT,
        total_jobs INTEGER DEFAULT 0,
        created_at TEXT
    );
    """)

    # 6. Staff Daily Attendance Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id TEXT PRIMARY KEY,
        technician_id TEXT NOT NULL,
        date TEXT NOT NULL,
        status TEXT DEFAULT 'PRESENT',
        notes TEXT,
        created_at TEXT
    );
    """)

    # 7. Staff Weekly/Monthly Wages Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employee_wages (
        id TEXT PRIMARY KEY,
        technician_id TEXT NOT NULL,
        technician_name TEXT,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        gross_amount REAL NOT NULL,
        advance_deducted REAL DEFAULT 0.0,
        net_paid REAL NOT NULL,
        payment_date TEXT NOT NULL,
        payment_mode TEXT DEFAULT 'CASH',
        notes TEXT,
        created_at TEXT
    );
    """)

    # 8. Staff Advances Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employee_advances (
        id TEXT PRIMARY KEY,
        technician_id TEXT NOT NULL,
        technician_name TEXT,
        amount REAL NOT NULL,
        advance_date TEXT NOT NULL,
        status TEXT DEFAULT 'OUTSTANDING',
        adjusted_in_wage_id TEXT,
        payment_mode TEXT DEFAULT 'CASH',
        notes TEXT,
        created_at TEXT
    );
    """)

    # 9. Customers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL UNIQUE,
        address TEXT,
        gstin TEXT,
        whatsapp_opt_in INTEGER DEFAULT 1,
        total_visits INTEGER DEFAULT 0,
        khata_balance REAL DEFAULT 0.0,
        created_at TEXT
    );
    """)

    # 10. Vehicles Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicles (
        id TEXT PRIMARY KEY,
        reg_number TEXT NOT NULL UNIQUE,
        customer_id TEXT,
        customer_name TEXT,
        customer_phone TEXT,
        make_model TEXT NOT NULL,
        vehicle_type TEXT DEFAULT 'Car',
        fuel_type TEXT DEFAULT 'Diesel',
        odometer INTEGER DEFAULT 0,
        chassis_no TEXT,
        created_at TEXT
    );
    """)

    # 11. Inventory Items Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory_items (
        id TEXT PRIMARY KEY,
        part_name TEXT NOT NULL,
        part_number TEXT DEFAULT '',
        sku TEXT,
        barcode TEXT NOT NULL UNIQUE,
        category TEXT DEFAULT 'Relays & Fuses',
        stock_qty INTEGER DEFAULT 0,
        min_stock_alert INTEGER DEFAULT 5,
        cost_price REAL DEFAULT 0.0,
        selling_price REAL DEFAULT 0.0,
        tax_rate REAL DEFAULT 18.0,
        hsn_code TEXT DEFAULT '8536',
        unit TEXT DEFAULT 'pcs',
        warranty_months INTEGER DEFAULT 0,
        supplier_name TEXT,
        location_rack TEXT,
        position_bin TEXT DEFAULT '',
        created_at TEXT,
        updated_at TEXT
    );
    """)

    # 12. Stock Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stock_logs (
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        part_name TEXT,
        barcode TEXT,
        change_qty INTEGER NOT NULL,
        new_stock_qty INTEGER NOT NULL,
        action_type TEXT NOT NULL,
        unit_cost REAL DEFAULT 0.0,
        reference_id TEXT,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 12b. Suppliers Table (Supplier Master & Directory)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS suppliers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        contact_person TEXT,
        phone TEXT NOT NULL,
        whatsapp TEXT,
        email TEXT,
        address TEXT,
        city TEXT,
        state TEXT DEFAULT 'Kerala (32)',
        gstin TEXT,
        payment_terms TEXT,
        notes TEXT,
        total_purchases REAL DEFAULT 0.0,
        outstanding_balance REAL DEFAULT 0.0,
        created_at TEXT
    );
    """)

    # 13. Purchase Bills Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_bills (
        id TEXT PRIMARY KEY,
        bill_number TEXT NOT NULL,
        supplier_id TEXT,
        supplier_name TEXT NOT NULL,
        bill_date TEXT NOT NULL,
        total_amount REAL NOT NULL,
        payment_status TEXT DEFAULT 'PAID',
        payment_mode TEXT DEFAULT 'BANK_TRANSFER',
        notes TEXT,
        created_at TEXT
    );
    """)

    # 14. Purchase Items Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_items (
        id TEXT PRIMARY KEY,
        purchase_id TEXT NOT NULL,
        item_id TEXT,
        part_name TEXT NOT NULL,
        barcode TEXT,
        quantity INTEGER DEFAULT 1,
        unit_cost REAL DEFAULT 0.0,
        total_cost REAL DEFAULT 0.0
    );
    """)

    # 15. Purchase Returns Table (Debit Notes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_returns (
        id TEXT PRIMARY KEY,
        return_number TEXT NOT NULL UNIQUE,
        purchase_id TEXT,
        supplier_name TEXT NOT NULL,
        item_id TEXT NOT NULL,
        part_name TEXT NOT NULL,
        quantity INTEGER DEFAULT 1,
        unit_cost REAL DEFAULT 0.0,
        return_amount REAL DEFAULT 0.0,
        return_date TEXT NOT NULL,
        reason TEXT DEFAULT 'Defective Part',
        created_at TEXT
    );
    """)

    # 16. Sales Returns Table (Credit Notes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sales_returns (
        id TEXT PRIMARY KEY,
        return_number TEXT NOT NULL UNIQUE,
        invoice_id TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        item_id TEXT,
        name TEXT NOT NULL,
        quantity INTEGER DEFAULT 1,
        unit_price REAL DEFAULT 0.0,
        refund_amount REAL DEFAULT 0.0,
        return_date TEXT NOT NULL,
        refund_mode TEXT DEFAULT 'CASH',
        reason TEXT DEFAULT 'Customer Returned Part',
        created_at TEXT
    );
    """)

    # 17. Bank Accounts Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bank_accounts (
        id TEXT PRIMARY KEY,
        account_name TEXT NOT NULL,
        bank_name TEXT,
        account_number TEXT,
        ifsc_code TEXT,
        upi_vpa TEXT,
        account_type TEXT DEFAULT 'BANK',
        current_balance REAL DEFAULT 0.0,
        is_primary INTEGER DEFAULT 0,
        created_at TEXT
    );
    """)

    # 18. Expenses Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_mode TEXT DEFAULT 'CASH',
        bank_account_id TEXT,
        expense_date TEXT NOT NULL,
        paid_to TEXT,
        reference_no TEXT,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 19. Job Cards Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_cards (
        id TEXT PRIMARY KEY,
        job_number TEXT NOT NULL UNIQUE,
        customer_id TEXT,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        vehicle_id TEXT,
        vehicle_reg_no TEXT NOT NULL,
        vehicle_make_model TEXT NOT NULL,
        odometer INTEGER DEFAULT 0,
        assigned_technician_id TEXT,
        assigned_technician_name TEXT,
        status TEXT DEFAULT 'RECEIVED',
        complaints TEXT DEFAULT '[]',
        custom_complaint_notes TEXT,
        diagnosis_notes TEXT,
        estimated_amount REAL DEFAULT 0.0,
        estimated_delivery_date TEXT,
        total_labor REAL DEFAULT 0.0,
        total_parts REAL DEFAULT 0.0,
        grand_total REAL DEFAULT 0.0,
        created_at TEXT,
        completed_at TEXT,
        delivered_at TEXT
    );
    """)

    # 20. Job Items Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS job_items (
        id TEXT PRIMARY KEY,
        job_card_id TEXT NOT NULL,
        item_type TEXT DEFAULT 'LABOR',
        item_id TEXT,
        barcode TEXT,
        name TEXT NOT NULL,
        hsn_code TEXT,
        quantity INTEGER DEFAULT 1,
        unit_price REAL DEFAULT 0.0,
        tax_rate REAL DEFAULT 0.0,
        total_price REAL DEFAULT 0.0,
        technician_id TEXT,
        technician_name TEXT
    );
    """)

    # 21. Invoices Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        id TEXT PRIMARY KEY,
        invoice_number TEXT NOT NULL UNIQUE,
        invoice_date TEXT NOT NULL,
        invoice_type TEXT DEFAULT 'JOB_SERVICE',
        job_card_id TEXT,
        job_number TEXT,
        customer_id TEXT,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_address TEXT,
        customer_gstin TEXT,
        vehicle_reg_no TEXT,
        vehicle_make_model TEXT,
        odometer INTEGER DEFAULT 0,
        subtotal_labor REAL DEFAULT 0.0,
        subtotal_parts REAL DEFAULT 0.0,
        taxable_subtotal REAL DEFAULT 0.0,
        cgst_total REAL DEFAULT 0.0,
        sgst_total REAL DEFAULT 0.0,
        tax_total REAL DEFAULT 0.0,
        discount_amount REAL DEFAULT 0.0,
        grand_total REAL DEFAULT 0.0,
        amount_paid REAL DEFAULT 0.0,
        balance_due REAL DEFAULT 0.0,
        payment_status TEXT DEFAULT 'PENDING',
        payment_mode TEXT DEFAULT 'UPI',
        bank_account_id TEXT,
        upi_ref_no TEXT,
        upi_payment_link TEXT,
        whatsapp_sent INTEGER DEFAULT 0,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 22. Invoice Items Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
        id TEXT PRIMARY KEY,
        invoice_id TEXT NOT NULL,
        item_type TEXT DEFAULT 'PART',
        item_id TEXT,
        barcode TEXT,
        name TEXT NOT NULL,
        hsn_sac TEXT DEFAULT '8536',
        quantity INTEGER DEFAULT 1,
        unit_price REAL DEFAULT 0.0,
        tax_rate REAL DEFAULT 18.0,
        taxable_amount REAL DEFAULT 0.0,
        cgst_amount REAL DEFAULT 0.0,
        sgst_amount REAL DEFAULT 0.0,
        total_price REAL DEFAULT 0.0,
        technician_name TEXT
    );
    """)

    # 23. Payments Ledger Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        invoice_id TEXT,
        customer_id TEXT,
        amount REAL NOT NULL,
        payment_mode TEXT DEFAULT 'UPI',
        bank_account_id TEXT,
        reference_no TEXT,
        payment_date TEXT NOT NULL,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 24. Activity Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        username TEXT DEFAULT 'Admin',
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        details TEXT,
        created_at TEXT
    );
    """)

    run_schema_migrations(cursor, conn)
    conn.commit()
    seed_initial_data(cursor, conn)
    conn.close()

def run_schema_migrations(cursor, conn):
    """Safely add any columns that may be missing from older SQLite database instances"""
    migrations = [
        ("users", "whatsapp_mobile", "TEXT"),
        ("users", "tenant_id", "TEXT DEFAULT 'tenant_1'"),
        ("users", "otp_code", "TEXT"),
        ("users", "otp_expiry", "TEXT"),
        ("tenants", "whatsapp_mobile", "TEXT"),
        ("tenants", "logo_url", "TEXT"),
        ("tenants", "upi_payee_name", "TEXT"),
        ("tenants", "gst_slabs", "TEXT DEFAULT '[\"0\", \"5\", \"12\", \"18\", \"28\"]'"),
        ("tenants", "master_pin", "TEXT DEFAULT '1234'"),
        ("tenants", "subscription_plan", "TEXT DEFAULT 'PRO_ANNUAL'"),
        ("tenants", "subscription_start_date", "TEXT"),
        ("tenants", "price_paid", "REAL DEFAULT 0.0"),
        ("workshop_profile", "logo_url", "TEXT"),
        ("workshop_profile", "upi_payee_name", "TEXT"),
        ("workshop_profile", "gst_slabs", "TEXT DEFAULT '[\"0\", \"5\", \"12\", \"18\", \"28\"]'"),
        ("workshop_profile", "language", "TEXT DEFAULT 'en'"),
        ("workshop_profile", "master_pin", "TEXT DEFAULT '1234'"),
        ("workshop_profile", "owner_name", "TEXT"),
        ("workshop_profile", "updated_at", "TEXT"),
        ("technicians", "is_on_leave", "INTEGER DEFAULT 0"),
        ("technicians", "current_advance_balance", "REAL DEFAULT 0.0"),
        ("technicians", "daily_wage", "REAL DEFAULT 0.0"),
        ("invoices", "customer_gstin", "TEXT"),
        ("invoices", "job_card_id", "TEXT"),
        ("invoices", "job_number", "TEXT"),
        ("invoices", "payment_status", "TEXT DEFAULT 'PAID'"),
        ("invoices", "payment_mode", "TEXT DEFAULT 'UPI'"),
        ("invoices", "subtotal_labor", "REAL DEFAULT 0.0"),
        ("invoices", "subtotal_parts", "REAL DEFAULT 0.0"),
        ("invoices", "taxable_subtotal", "REAL DEFAULT 0.0"),
        ("invoices", "discount_amount", "REAL DEFAULT 0.0"),
        ("invoices", "grand_total", "REAL DEFAULT 0.0"),
        ("invoices", "amount_paid", "REAL DEFAULT 0.0"),
        ("invoices", "balance_due", "REAL DEFAULT 0.0"),
        ("invoices", "cgst_total", "REAL DEFAULT 0.0"),
        ("invoices", "sgst_total", "REAL DEFAULT 0.0"),
        ("invoices", "tax_total", "REAL DEFAULT 0.0"),
        ("invoices", "upi_payment_link", "TEXT"),
        ("invoice_items", "cgst_amount", "REAL DEFAULT 0.0"),
        ("invoice_items", "sgst_amount", "REAL DEFAULT 0.0"),
        ("invoice_items", "taxable_amount", "REAL DEFAULT 0.0"),
        ("job_cards", "assigned_technician_name", "TEXT"),
        ("job_cards", "diagnosis_notes", "TEXT"),
        ("job_cards", "custom_complaint_notes", "TEXT"),
        ("job_cards", "completed_at", "TEXT"),
        ("job_cards", "delivered_at", "TEXT"),
        ("inventory_items", "location_rack", "TEXT DEFAULT 'Main'"),
        ("activity_logs", "username", "TEXT DEFAULT 'Admin'"),
        ("activity_logs", "entity_type", "TEXT"),
        ("activity_logs", "entity_id", "TEXT"),
        ("purchase_bills", "status", "TEXT DEFAULT 'CONFIRMED'"),
        ("invoices", "igst_total", "REAL DEFAULT 0.0"),
        ("invoices", "is_interstate", "INTEGER DEFAULT 0"),
        ("invoices", "place_of_supply", "TEXT DEFAULT 'Kerala (32)'"),
        ("invoices", "updated_at", "TEXT"),
        ("invoices", "status", "TEXT DEFAULT 'ACTIVE'"),
        ("purchase_bills", "cgst_amount", "REAL DEFAULT 0.0"),
        ("purchase_bills", "sgst_amount", "REAL DEFAULT 0.0"),
        ("purchase_bills", "igst_amount", "REAL DEFAULT 0.0"),
        ("purchase_bills", "is_interstate", "INTEGER DEFAULT 0"),
        ("purchase_bills", "supplier_state", "TEXT DEFAULT 'Kerala (32)'"),
        ("inventory_items", "part_number", "TEXT DEFAULT ''"),
        ("invoices", "round_off", "REAL DEFAULT 0.0"),
        ("invoice_items", "unit", "TEXT DEFAULT 'pcs'"),
        ("invoice_items", "part_number", "TEXT DEFAULT ''"),
        ("invoice_items", "cgst_rate", "REAL DEFAULT 0.0"),
        ("invoice_items", "sgst_rate", "REAL DEFAULT 0.0"),
        ("invoice_items", "igst_rate", "REAL DEFAULT 0.0"),
        ("invoice_items", "igst_amount", "REAL DEFAULT 0.0"),
        ("workshop_profile", "default_state", "TEXT DEFAULT 'Kerala (32)'"),
        ("workshop_profile", "default_gst_type", "TEXT DEFAULT 'INTRA_STATE'"),
        ("workshop_profile", "tax_regime", "TEXT DEFAULT 'REGULAR_GST'"),
        ("workshop_profile", "round_off_enabled", "INTEGER DEFAULT 1"),
        ("users", "permissions", "TEXT DEFAULT ''"),
        ("purchase_bills", "supplier_id", "TEXT DEFAULT ''"),
        ("purchase_items", "tax_rate", "REAL DEFAULT 18.0"),
        ("inventory_items", "position_bin", "TEXT DEFAULT ''"),
    ]

    for table, col, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    # Ensure admin has whatsapp_mobile default
    try:
        cursor.execute("UPDATE users SET whatsapp_mobile = '+919876500000' WHERE username = 'admin' AND (whatsapp_mobile IS NULL OR whatsapp_mobile = '')")
        cursor.execute("UPDATE users SET whatsapp_mobile = '+919876511111' WHERE username = 'staff' AND (whatsapp_mobile IS NULL OR whatsapp_mobile = '')")
    except Exception:
        pass



def seed_initial_data(cursor, conn):
    """Seed initial enterprise data: default admin user, SaaS subscription, technicians, inventory"""
    # 1. Default Super Admin User
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        admin_pw_hash = hash_password("admin123")
        cursor.execute("""
        INSERT INTO users (id, username, password_hash, full_name, role, email, phone, whatsapp_mobile, status, created_at)
        VALUES ('user_admin', 'admin', ?, 'Super Administrator', 'SUPER_ADMIN', 'admin@autovolt.com', '+91 98765 00000', '+919876500000', 'ACTIVE', datetime('now'))
        """, (admin_pw_hash,))
        
        staff_pw_hash = hash_password("staff123")
        cursor.execute("""
        INSERT INTO users (id, username, password_hash, full_name, role, email, phone, whatsapp_mobile, status, created_at)
        VALUES ('user_staff', 'staff', ?, 'Workshop Service Desk', 'STAFF', 'service@sparkauto.com', '+91 98765 11111', '+919876511111', 'ACTIVE', datetime('now'))
        """, (staff_pw_hash,))

    # 1B. SaaS Vendor Company Profile
    cursor.execute("SELECT COUNT(*) FROM saas_vendor_profile")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO saas_vendor_profile (
            id, company_name, tagline, gstin, email, phone, whatsapp_phone,
            address, upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc,
            monthly_fee, yearly_fee, updated_at
        ) VALUES (
            'vendor_main', 'AutoVolt Technologies Pvt Ltd', 'Enterprise Automotive Workshop SaaS Platform',
            '32AABCA9876C1Z5', 'billing@autovoltcloud.com', '+91 98470 12345', '+919847012345',
            'CyberPark, Kozhikode / Infopark, Kochi, Kerala - 682042', 'autovoltcloud@icici', 'AutoVolt Technologies',
            'HDFC Bank Ltd', '50200088991122', 'HDFC0001234', 999.0, 9999.0, datetime('now')
        )
        """)

    # 2. Workshop Profile / Active Tenant
    cursor.execute("SELECT COUNT(*) FROM workshop_profile")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO workshop_profile (
            id, name, subtitle, owner_name, phone, email, address, gstin, logo_url, upi_id, upi_payee_name,
            bank_name, bank_account_no, bank_ifsc, bank_branch, gst_slabs, language, currency, master_pin, terms, created_at, updated_at
        ) VALUES (
            'default', 'SPARK AUTO ELECTRICALS', 'Automotive Electrical & Electronic Service Center',
            'Shafi V.', '+91 98765 43210', 'sparkautocare@gmail.com',
            'Near Highway Junction, Ernakulam, Kerala - 682001', '32AABCS1429B1Z8', '',
            'sparkautoworkshop@okaxis', 'SPARK AUTO ELECTRICALS', 'State Bank of India', '39876543210', 'SBIN0001234',
            'Ernakulam Main', '["0", "5", "12", "18", "28"]', 'en', '₹', '1234',
            '1. Electrical parts warranty as per manufacturer policy.\n2. Goods once fitted cannot be returned.\n3. Payment due upon completion.',
            datetime('now'), datetime('now')
        )
        """)

    # 3. Default Tenant & Active 1-Year SaaS Subscription
    cursor.execute("SELECT COUNT(*) FROM tenants")
    if cursor.fetchone()[0] == 0:
        start_date = datetime.now().strftime("%Y-%m-%d")
        expiry_date = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        cursor.execute("""
        INSERT INTO tenants (
            id, name, owner_name, phone, whatsapp_mobile, email, address, gstin, logo_url,
            upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc, bank_branch,
            gst_slabs, language, master_pin, status, subscription_plan, subscription_start_date, subscription_end_date, price_paid, created_at
        ) VALUES (
            'tenant_1', 'SPARK AUTO ELECTRICALS', 'Shafi V.', '+91 98765 43210', '+919876543210', 'sparkautocare@gmail.com',
            'Near Highway Junction, Ernakulam, Kerala - 682001', '32AABCS1429B1Z8', '',
            'sparkautoworkshop@okaxis', 'SPARK AUTO ELECTRICALS', 'State Bank of India', '39876543210', 'SBIN0001234', 'Ernakulam Main',
            '["0", "5", "12", "18", "28"]', 'en', '1234', 'ACTIVE', 'PRO_ANNUAL', ?, ?, 11798.82, datetime('now')
        )
        """, (start_date, expiry_date))

        cursor.execute("""
        INSERT INTO subscriptions (id, tenant_id, plan_name, start_date, end_date, is_active, billing_cycle, price_paid, notes, created_at)
        VALUES ('sub_1', 'tenant_1', 'PRO_ANNUAL', ?, ?, 1, 'YEARLY', 11798.82, 'Annual Pro License with Unlimited Invoices', datetime('now'))
        """, (start_date, expiry_date))

        # Seed initial SaaS Vendor Invoice
        cursor.execute("""
        INSERT INTO saas_vendor_invoices (
            id, invoice_no, tenant_id, tenant_name, invoice_date, plan_type,
            subscription_start, subscription_end, taxable_amount, cgst_rate, cgst_amount,
            sgst_rate, sgst_amount, total_amount, payment_status, payment_mode, payment_ref, notes, created_at
        ) VALUES (
            'sinv_1', 'HQ-INV-2026-001', 'tenant_1', 'SPARK AUTO ELECTRICALS', ?, 'YEARLY',
            ?, ?, 9999.00, 9.0, 899.91, 9.0, 899.91, 11798.82, 'PAID', 'UPI', 'UPI-REF-889911', 'Initial Annual SaaS Subscription License', datetime('now')
        )
        """, (start_date, start_date, expiry_date))

    # 4. Technicians
    cursor.execute("SELECT COUNT(*) FROM technicians")
    if cursor.fetchone()[0] == 0:
        technicians = [
            ("tech_1", "Sajeev Kumar", "+91 98471 11223", "Senior Auto Electrician", 15.0, 950.0, "Active", 0, 0.0, "Expert in starter & alternator rebuilds", 142),
            ("tech_2", "Anil K.", "+91 98472 22334", "Wiring Specialist", 12.0, 850.0, "Active", 0, 500.0, "Full body harness & short circuit tracing", 98),
            ("tech_3", "Vineeth M.", "+91 98473 33445", "AC & Cooling Specialist", 12.0, 850.0, "Active", 0, 0.0, "Blower motors, AC clutch, relays & wiring", 85),
            ("tech_4", "Ratheesh P.", "+91 98474 44556", "Battery & Diagnostic Tech", 10.0, 800.0, "Active", 1, 0.0, "OBD2 diagnostics & battery health analysis (On Leave)", 110),
            ("tech_5", "Faisal T.", "+91 98475 55667", "Lighting & Accessories", 10.0, 800.0, "Active", 0, 0.0, "Headlight relays, LED upgrades, horns & sound", 76),
            ("tech_6", "Akhil R.", "+91 98476 66778", "Junior Electrician / Trainee", 5.0, 500.0, "Active", 0, 200.0, "Fuse box, power windows & general repairs", 45),
        ]
        for t in technicians:
            cursor.execute("""
            INSERT INTO technicians (id, name, phone, role, commission_pct, daily_wage, status, is_on_leave, current_advance_balance, notes, total_jobs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, t)

    # 5. Inventory Items
    cursor.execute("SELECT COUNT(*) FROM inventory_items")
    if cursor.fetchone()[0] == 0:
        items = [
            ("item_1", "Lucas 4-Pin Horn Relay 12V 30A", "LUC-REL-4P", "89012340001", "Relays & Fuses", 45, 10, 85.0, 140.0, 18.0, "8536", "pcs", 6, "Lucas TVS Dist.", "Rack A1"),
            ("item_2", "Bosch 5-Pin Changeover Relay 12V 40A", "BOS-REL-5P", "89012340002", "Relays & Fuses", 30, 8, 110.0, 180.0, 18.0, "8536", "pcs", 6, "Bosch Auto", "Rack A1"),
            ("item_3", "Blade Fuse Assorted Set (5A-30A)", "FUSE-SET-STD", "89012340003", "Relays & Fuses", 120, 20, 3.0, 10.0, 18.0, "8536", "pcs", 0, "National Auto", "Rack A2"),
            ("item_4", "Ceramic Headlight Bulb Holder H4 Heavy", "HL-HLD-H4", "89012340004", "Bulbs & LEDs", 50, 15, 35.0, 75.0, 18.0, "8536", "pcs", 3, "PMP Electrics", "Rack B1"),
            ("item_5", "Philips H4 12V 100/90W Rally Bulb", "PHI-H4-100", "89012340005", "Bulbs & LEDs", 24, 6, 145.0, 220.0, 18.0, "8539", "pcs", 6, "Philips India", "Rack B2"),
            ("item_6", "Universal Headlight Relay Wiring Kit with Cutout", "HL-WIR-KIT", "89012340006", "Wiring & Sleeves", 18, 5, 290.0, 480.0, 18.0, "8544", "set", 12, "Roots India", "Rack B3"),
            ("item_7", "Roots Windtone Horn Set 12V", "RTS-HORN-WT", "89012340007", "Switches & Horns", 12, 4, 620.0, 950.0, 18.0, "8512", "set", 12, "Roots Dist.", "Rack C1"),
            ("item_8", "Starter Motor Carbon Brush Set (Swift/Dzire)", "BRUSH-STR-SWF", "89012340008", "Starters & Alternators", 20, 5, 120.0, 220.0, 18.0, "8511", "set", 3, "Lucas TVS", "Rack D1"),
            ("item_9", "Alternator Rectifier / Diode Plate (Swift Diesel)", "ALT-REC-SWF", "89012340009", "Starters & Alternators", 8, 3, 580.0, 890.0, 18.0, "8511", "pcs", 6, "Denso / Bosch", "Rack D2"),
            ("item_10", "Alternator Voltage Regulator IC 12V", "ALT-REG-IC12", "89012340010", "Starters & Alternators", 10, 3, 420.0, 680.0, 18.0, "8511", "pcs", 6, "Bosch Auto", "Rack D2"),
            ("item_11", "Amaron Hi-Way 12V 35Ah Battery (AAM-HW-35)", "AMR-BAT-35AH", "89012340011", "Batteries", 6, 2, 3400.0, 4250.0, 28.0, "8507", "pcs", 36, "Amaron Agency", "Battery Bay"),
            ("item_12", "Amaron Pro 12V 45Ah Battery (AAM-PR-45)", "AMR-BAT-45AH", "89012340012", "Batteries", 5, 2, 4300.0, 5300.0, 28.0, "8507", "pcs", 60, "Amaron Agency", "Battery Bay"),
            ("item_13", "Heavy Duty Pure Brass Battery Terminal Pair", "BAT-TRM-BRS", "89012340013", "Batteries", 35, 10, 45.0, 90.0, 18.0, "8536", "pair", 12, "PMP Electrics", "Rack A3"),
            ("item_14", "Heat Shrink Sleeve Tube 6mm (1 Meter)", "SLV-HST-6MM", "89012340014", "Wiring & Sleeves", 80, 20, 12.0, 30.0, 18.0, "3917", "mtr", 0, "National Auto", "Rack B4"),
            ("item_15", "Auto Grade Copper Wire 1.5 sq mm Roll", "WIR-COP-1.5", "89012340015", "Wiring & Sleeves", 15, 3, 450.0, 750.0, 18.0, "8544", "roll", 12, "Finolex Auto", "Rack B4"),
            ("item_16", "Universal Reverse Parking Camera with Night LED", "REV-CAM-LED", "89012340016", "Accessories", 10, 3, 480.0, 850.0, 18.0, "8528", "pcs", 12, "Audio Care", "Rack E1"),
            ("item_17", "Power Window Master Switch (Maruti 4-Door)", "PWR-WIN-SWF", "89012340017", "Switches & Horns", 6, 2, 650.0, 1150.0, 18.0, "8536", "pcs", 6, "Minda Auto", "Rack C2"),
            ("item_18", "OBD2 Diagnostic & ECU Scanning Charge", "SRV-OBD-SCAN", "89012340018", "Sensors & OBD", 999, 0, 0.0, 350.0, 18.0, "9987", "service", 0, "In-House", "-"),
        ]
        for itm in items:
            cursor.execute("""
            INSERT INTO inventory_items (
                id, part_name, sku, barcode, category, stock_qty, min_stock_alert,
                cost_price, selling_price, tax_rate, hsn_code, unit, warranty_months,
                supplier_name, location_rack, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, itm)

    # 6. Bank Accounts
    cursor.execute("SELECT COUNT(*) FROM bank_accounts")
    if cursor.fetchone()[0] == 0:
        banks = [
            ("bank_1", "SBI Workshop Current A/c", "State Bank of India", "39876543210", "SBIN0001234", "sparkautoworkshop@okaxis", "BANK", 125000.0, 1),
            ("bank_2", "Workshop Cash Register", "Cash In Hand", "-", "-", "-", "CASH", 14500.0, 0),
            ("bank_3", "GPay / UPI Business Wallet", "UPI Digital", "-", "-", "sparkautoworkshop@okaxis", "UPI_WALLET", 28400.0, 0),
        ]
        for b in banks:
            cursor.execute("""
            INSERT INTO bank_accounts (id, account_name, bank_name, account_number, ifsc_code, upi_vpa, account_type, current_balance, is_primary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, b)

    # 7. Seed Initial Suppliers & Purchase Bill
    cursor.execute("SELECT COUNT(*) FROM suppliers")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO suppliers (id, name, contact_person, phone, whatsapp, email, address, city, state, gstin, payment_terms, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, [
            ("sup_001", "Lucas TVS Kerala Agency", "Sunil Kumar", "9847012345", "9847012345", "sales@lucastvskerala.com", "Auto Spares Complex, MG Road", "Kochi", "Kerala (32)", "32AABCL1234F1Z5", "30 Days Credit", "Authorized Lucas TVS distributor"),
            ("sup_002", "Bosch Auto Electricals Distributors", "Abdul Rahman", "9447098765", "9447098765", "spares@boschdealerkerala.com", "Industrial Estate, Aroor", "Alappuzha", "Kerala (32)", "32AABCB5678G1Z2", "15 Days Credit", "Batteries, Starters & Alternators"),
            ("sup_003", "Coimbatore Auto Electric Spares", "Murugan V.", "9842011223", "9842011223", "orders@cbeautospares.in", "Crosscut Road, Gandhipuram", "Coimbatore", "Tamil Nadu (33)", "33ABCDE9999K1Z1", "Immediate / Bank Transfer", "Inter-state supplier for heavy electrical components")
        ])

    cursor.execute("SELECT COUNT(*) FROM purchase_bills")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO purchase_bills (id, bill_number, supplier_id, supplier_name, bill_date, total_amount, payment_status, payment_mode, notes, created_at)
        VALUES ('pur_1', 'SUP-INV-8912', 'sup_001', 'Lucas TVS Kerala Agency', date('now', '-3 days'), 18500.0, 'PAID', 'BANK_TRANSFER', 'Bulk starter armatures and relays stock purchase', datetime('now', '-3 days'))
        """)

    conn.commit()

def log_activity_event(username: str, action: str, entity_type: str = "", entity_id: str = "", details: str = "", cursor: Any = None):
    """Record audit trail log"""
    log_id = f"act_{uuid.uuid4().hex[:8]}"
    now_ist = get_ist_now_str()
    if cursor:
        try:
            cursor.execute("""
            INSERT INTO activity_logs (id, username, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (log_id, username or "Admin", action, entity_type, entity_id, details, now_ist))
        except Exception as e:
            print(f"[Audit Log Error] {e}")
        return

    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO activity_logs (id, username, action, entity_type, entity_id, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (log_id, username or "Admin", action, entity_type, entity_id, details, now_ist))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Audit Log Error] {e}")

def log_audit(action: str, entity_type: str = "", entity_id: str = "", details: str = "", username: str = "Admin", cursor: Any = None):
    """Convenience alias for log_activity_event"""
    log_activity_event(username, action, entity_type, entity_id, details, cursor=cursor)



def check_subscription_status() -> Dict[str, Any]:
    """Check if the current workshop subscription is active or expired"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE is_active = 1 ORDER BY end_date DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {"is_active": True, "end_date": "2099-12-31", "days_left": 9999}
        
    sub = dict(row)
    end_date_str = sub["end_date"]
    try:
        end_date_obj = datetime.strptime(end_date_str.split("T")[0], "%Y-%m-%d").date()
        today = date.today()
        days_left = (end_date_obj - today).days
        is_active = days_left >= 0
        return {"is_active": is_active, "end_date": end_date_str, "days_left": days_left, "plan_name": sub.get("plan_name", "PRO")}
    except Exception:
        return {"is_active": True, "end_date": end_date_str, "days_left": 365}

# Initialize DB on load
init_db()
