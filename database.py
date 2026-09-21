import os
import sqlite3
import json
import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

# Check for Supabase Cloud Database credentials
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
    """Get SQLite connection with row factory"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize SQLite database with full tables and seed initial auto-electrical data"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Workshop Profile Table
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
        upi_id TEXT NOT NULL,
        bank_name TEXT,
        bank_account_no TEXT,
        bank_ifsc TEXT,
        bank_branch TEXT,
        currency TEXT DEFAULT '₹',
        terms TEXT,
        created_at TEXT,
        updated_at TEXT
    );
    """)

    # 2. Technicians Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS technicians (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        phone TEXT NOT NULL,
        role TEXT DEFAULT 'Senior Electrician',
        commission_pct REAL DEFAULT 0.0,
        status TEXT DEFAULT 'Active',
        notes TEXT,
        total_jobs INTEGER DEFAULT 0,
        created_at TEXT
    );
    """)

    # 3. Customers Table
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

    # 4. Vehicles Table
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

    # 5. Inventory Items Table (with Barcode & HSN)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inventory_items (
        id TEXT PRIMARY KEY,
        part_name TEXT NOT NULL,
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
        created_at TEXT,
        updated_at TEXT
    );
    """)

    # 6. Stock Logs Table
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

    # 7. Bank Accounts Table
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

    # 8. Workshop Operating Expenses Table
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

    # 9. Job Cards Table
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

    # 10. Job Items Table (Parts + Labor on Job Card)
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

    # 11. Invoices Table
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
        payment_status TEXT DEFAULT 'PAID',
        payment_mode TEXT DEFAULT 'UPI',
        bank_account_id TEXT,
        upi_ref_no TEXT,
        upi_payment_link TEXT,
        whatsapp_sent INTEGER DEFAULT 0,
        notes TEXT,
        created_at TEXT
    );
    """)

    # 12. Invoice Items Table
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

    # 13. Payments Ledger Table
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

    # 14. Activity Audit Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        entity_type TEXT,
        entity_id TEXT,
        details TEXT,
        created_at TEXT
    );
    """)

    conn.commit()
    seed_initial_data(cursor, conn)
    conn.close()

def seed_initial_data(cursor, conn):
    """Seed initial workshop profile, 6 staff technicians, and common auto-electrical items with barcodes"""
    # 1. Workshop Profile
    cursor.execute("SELECT COUNT(*) FROM workshop_profile")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO workshop_profile (
            id, name, subtitle, owner_name, phone, email, address, gstin, upi_id,
            bank_name, bank_account_no, bank_ifsc, bank_branch, currency, terms, created_at, updated_at
        ) VALUES (
            'default', 'SPARK AUTO ELECTRICALS', 'Auto Electrical & Electronic Service Center',
            'Shafi V.', '+91 98765 43210', 'sparkautocare@gmail.com',
            'Near Highway Junction, Ernakulam, Kerala - 682001', '32AABCS1429B1Z8',
            'sparkautoworkshop@okaxis', 'State Bank of India', '39876543210', 'SBIN0001234',
            'Ernakulam Main', '₹', '1. Electrical parts warranty as per manufacturer policy.\n2. Goods once installed cannot be returned.\n3. Payment due upon completion.',
            datetime('now'), datetime('now')
        )
        """)

    # 2. Seed 6 Technicians
    cursor.execute("SELECT COUNT(*) FROM technicians")
    if cursor.fetchone()[0] == 0:
        technicians = [
            ("tech_1", "Sajeev Kumar", "+91 98471 11223", "Senior Auto Electrician", 15.0, "Active", "Expert in starter & alternator rebuilds", 142),
            ("tech_2", "Anil K.", "+91 98472 22334", "Wiring Specialist", 12.0, "Active", "Full body harness & short circuit tracing", 98),
            ("tech_3", "Vineeth M.", "+91 98473 33445", "AC & Cooling Specialist", 12.0, "Active", "Blower motors, AC clutch, relays & wiring", 85),
            ("tech_4", "Ratheesh P.", "+91 98474 44556", "Battery & Diagnostic Tech", 10.0, "Active", "OBD2 diagnostics & battery health analysis", 110),
            ("tech_5", "Faisal T.", "+91 98475 55667", "Lighting & Accessories", 10.0, "Active", "Headlight relays, LED upgrades, horns & sound", 76),
            ("tech_6", "Akhil R.", "+91 98476 66778", "Junior Electrician / Trainee", 5.0, "Active", "Fuse box, power windows & general repairs", 45),
        ]
        for t in technicians:
            cursor.execute("""
            INSERT INTO technicians (id, name, phone, role, commission_pct, status, notes, total_jobs, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, t)

    # 3. Seed Bank Accounts
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

    # 4. Seed Auto Electrical Inventory with Real Barcodes
    cursor.execute("SELECT COUNT(*) FROM inventory_items")
    if cursor.fetchone()[0] == 0:
        items = [
            # ID, Name, SKU, Barcode, Category, Stock, MinAlert, Cost, Selling, Tax%, HSN, Unit, Warranty, Supplier, Rack
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

    # 5. Seed Sample Customer & Vehicle & Completed Job
    cursor.execute("SELECT COUNT(*) FROM customers")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO customers (id, name, phone, address, gstin, whatsapp_opt_in, total_visits, khata_balance, created_at)
        VALUES ('cust_1', 'Muhammed Nishad', '+91 94471 23456', 'Kaloor, Ernakulam', '', 1, 3, 0.0, datetime('now'))
        """)
        cursor.execute("""
        INSERT INTO vehicles (id, reg_number, customer_id, customer_name, customer_phone, make_model, vehicle_type, fuel_type, odometer, created_at)
        VALUES ('veh_1', 'KL-07-BX-4590', 'cust_1', 'Muhammed Nishad', '+91 94471 23456', 'Maruti Suzuki Swift DDiS', 'Car', 'Diesel', 84200, datetime('now'))
        """)

        # Sample Job Card
        cursor.execute("""
        INSERT INTO job_cards (
            id, job_number, customer_id, customer_name, customer_phone, vehicle_id, vehicle_reg_no,
            vehicle_make_model, odometer, assigned_technician_id, assigned_technician_name,
            status, complaints, custom_complaint_notes, diagnosis_notes, estimated_amount,
            estimated_delivery_date, total_labor, total_parts, grand_total, created_at
        ) VALUES (
            'job_1', 'JOB-2026-001', 'cust_1', 'Muhammed Nishad', '+91 94471 23456',
            'veh_1', 'KL-07-BX-4590', 'Maruti Suzuki Swift DDiS', 84200, 'tech_1', 'Sajeev Kumar',
            'COMPLETED', '["Starting Trouble / Clicking Noise", "Headlight Dim on Low Beam"]',
            'Morning starting delay, battery light blinking occasionally',
            'Starter motor carbon brush worn out. Headlight relay kit installed.',
            1850.0, datetime('now', '+4 hours'), 650.0, 840.0, 1490.0, datetime('now')
        )
        """)

        # Sample Job Items
        cursor.execute("""
        INSERT INTO job_items (id, job_card_id, item_type, item_id, barcode, name, hsn_code, quantity, unit_price, tax_rate, total_price, technician_name)
        VALUES ('ji_1', 'job_1', 'LABOR', NULL, NULL, 'Starter Motor Overhaul & Testing Labor', '9987', 1, 450.0, 0.0, 450.0, 'Sajeev Kumar')
        """)
        cursor.execute("""
        INSERT INTO job_items (id, job_card_id, item_type, item_id, barcode, name, hsn_code, quantity, unit_price, tax_rate, total_price, technician_name)
        VALUES ('ji_2', 'job_1', 'LABOR', NULL, NULL, 'Headlight Relay Wiring & Alignment Labor', '9987', 1, 200.0, 0.0, 200.0, 'Faisal T.')
        """)
        cursor.execute("""
        INSERT INTO job_items (id, job_card_id, item_type, item_id, barcode, name, hsn_code, quantity, unit_price, tax_rate, total_price, technician_name)
        VALUES ('ji_3', 'job_1', 'PART', 'item_8', '89012340008', 'Starter Motor Carbon Brush Set (Swift/Dzire)', '8511', 1, 220.0, 18.0, 220.0, 'Sajeev Kumar')
        """)
        cursor.execute("""
        INSERT INTO job_items (id, job_card_id, item_type, item_id, barcode, name, hsn_code, quantity, unit_price, tax_rate, total_price, technician_name)
        VALUES ('ji_4', 'job_1', 'PART', 'item_6', '89012340006', 'Universal Headlight Relay Wiring Kit with Cutout', '8544', 1, 480.0, 18.0, 480.0, 'Faisal T.')
        """)

        # Sample Invoice
        cursor.execute("""
        INSERT INTO invoices (
            id, invoice_number, invoice_date, invoice_type, job_card_id, job_number,
            customer_id, customer_name, customer_phone, vehicle_reg_no, vehicle_make_model,
            odometer, subtotal_labor, subtotal_parts, taxable_subtotal, cgst_total, sgst_total,
            tax_total, discount_amount, grand_total, amount_paid, balance_due,
            payment_status, payment_mode, bank_account_id, upi_ref_no, upi_payment_link, whatsapp_sent, notes, created_at
        ) VALUES (
            'inv_1', 'INV-2026-001', date('now'), 'JOB_SERVICE', 'job_1', 'JOB-2026-001',
            'cust_1', 'Muhammed Nishad', '+91 94471 23456', 'KL-07-BX-4590', 'Maruti Suzuki Swift DDiS',
            84200, 650.0, 700.0, 1350.0, 0.0, 0.0, 0.0, 0.0, 1350.0, 1350.0, 0.0,
            'PAID', 'UPI', 'bank_1', 'UPI982347201948', 'upi://pay?pa=sparkautoworkshop@okaxis&pn=SPARK%20AUTO%20ELECTRICALS&am=1350.00&tn=Bill_INV-2026-001&cu=INR', 1, 'Payment settled via GPay QR at workshop', datetime('now')
        )
        """)

        # Sample Operating Expense
        cursor.execute("""
        INSERT INTO expenses (id, title, category, amount, payment_mode, bank_account_id, expense_date, paid_to, reference_no, notes, created_at)
        VALUES ('exp_1', 'Workshop Monthly Electricity & Power Bill', 'Electricity Bill', 2450.0, 'BANK_TRANSFER', 'bank_1', date('now'), 'KSEB Section 4', 'EB-987214', 'Power bill for workshop electrical test benches & chargers', datetime('now'))
        """)

    conn.commit()

# Helper Audit Log
def log_audit(action: str, entity_type: str = "", entity_id: str = "", details: str = ""):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        log_id = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO activity_logs (id, action, entity_type, entity_id, details, created_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (log_id, action, entity_type, entity_id, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Audit Log Error] {e}")

# Initialize on module load
init_db()
