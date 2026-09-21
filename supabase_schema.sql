-- =========================================================
-- AUTVOLT PRO: AUTO ELECTRICAL WORKSHOP & SERVICE CENTER
-- SUPABASE POSTGRESQL DATABASE SCHEMA
-- =========================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Workshop Profile Table
CREATE TABLE IF NOT EXISTS workshop_profile (
    id TEXT PRIMARY KEY DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'SPARK AUTO ELECTRICALS',
    subtitle TEXT DEFAULT 'Auto Electrical & Electronic Service Center',
    owner_name TEXT DEFAULT 'Shafi V.',
    phone TEXT NOT NULL DEFAULT '+91 98765 43210',
    email TEXT DEFAULT 'sparkautocare@gmail.com',
    address TEXT NOT NULL DEFAULT 'Near Highway Junction, Ernakulam, Kerala - 682001',
    gstin TEXT DEFAULT '32AABCS1429B1Z8',
    upi_id TEXT NOT NULL DEFAULT 'sparkautoworkshop@okaxis',
    bank_name TEXT DEFAULT 'State Bank of India',
    bank_account_no TEXT DEFAULT '39876543210',
    bank_ifsc TEXT DEFAULT 'SBIN0001234',
    bank_branch TEXT DEFAULT 'Ernakulam Main',
    currency TEXT DEFAULT '₹',
    terms TEXT DEFAULT '1. Electrical parts warranty as per manufacturer policy.\n2. Goods once fitted cannot be returned.\n3. Payment due upon completion.',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Technicians Table (5-6 Staff Mechanics)
CREATE TABLE IF NOT EXISTS technicians (
    id TEXT PRIMARY KEY DEFAULT ('tech_' || substr(md5(random()::text), 1, 8)),
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    role TEXT DEFAULT 'Senior Auto Electrician',
    commission_pct NUMERIC(5, 2) DEFAULT 10.0,
    status TEXT DEFAULT 'Active',
    notes TEXT,
    total_jobs INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Customers Table
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY DEFAULT ('cust_' || substr(md5(random()::text), 1, 8)),
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    address TEXT,
    gstin TEXT,
    whatsapp_opt_in BOOLEAN DEFAULT TRUE,
    total_visits INTEGER DEFAULT 1,
    khata_balance NUMERIC(12, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Vehicles Table
CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY DEFAULT ('veh_' || substr(md5(random()::text), 1, 8)),
    reg_number TEXT NOT NULL UNIQUE,
    customer_id TEXT REFERENCES customers(id) ON DELETE SET NULL,
    customer_name TEXT,
    customer_phone TEXT,
    make_model TEXT NOT NULL,
    vehicle_type TEXT DEFAULT 'Car',
    fuel_type TEXT DEFAULT 'Diesel',
    odometer INTEGER DEFAULT 0,
    chassis_no TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Inventory & Spare Parts Table (with Barcode & HSN)
CREATE TABLE IF NOT EXISTS inventory_items (
    id TEXT PRIMARY KEY DEFAULT ('item_' || substr(md5(random()::text), 1, 8)),
    part_name TEXT NOT NULL,
    sku TEXT,
    barcode TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT 'Relays & Fuses',
    stock_qty INTEGER DEFAULT 0,
    min_stock_alert INTEGER DEFAULT 5,
    cost_price NUMERIC(10, 2) DEFAULT 0.0,
    selling_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    hsn_code TEXT DEFAULT '8536',
    unit TEXT DEFAULT 'pcs',
    warranty_months INTEGER DEFAULT 0,
    supplier_name TEXT,
    location_rack TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Stock Adjustment Logs
CREATE TABLE IF NOT EXISTS stock_logs (
    id TEXT PRIMARY KEY DEFAULT ('stk_' || substr(md5(random()::text), 1, 8)),
    item_id TEXT REFERENCES inventory_items(id) ON DELETE CASCADE,
    part_name TEXT,
    barcode TEXT,
    change_qty INTEGER NOT NULL,
    new_stock_qty INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    unit_cost NUMERIC(10, 2) DEFAULT 0.0,
    reference_id TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Bank Accounts Table
CREATE TABLE IF NOT EXISTS bank_accounts (
    id TEXT PRIMARY KEY DEFAULT ('bank_' || substr(md5(random()::text), 1, 8)),
    account_name TEXT NOT NULL,
    bank_name TEXT,
    account_number TEXT,
    ifsc_code TEXT,
    upi_vpa TEXT,
    account_type TEXT DEFAULT 'BANK',
    current_balance NUMERIC(12, 2) DEFAULT 0.0,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. Workshop Operating Expenses
CREATE TABLE IF NOT EXISTS expenses (
    id TEXT PRIMARY KEY DEFAULT ('exp_' || substr(md5(random()::text), 1, 8)),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    payment_mode TEXT DEFAULT 'CASH',
    bank_account_id TEXT,
    expense_date DATE NOT NULL,
    paid_to TEXT,
    reference_no TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Job Cards Table (Service Center Job Book)
CREATE TABLE IF NOT EXISTS job_cards (
    id TEXT PRIMARY KEY DEFAULT ('job_' || substr(md5(random()::text), 1, 8)),
    job_number TEXT NOT NULL UNIQUE,
    customer_id TEXT REFERENCES customers(id) ON DELETE SET NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    vehicle_id TEXT REFERENCES vehicles(id) ON DELETE SET NULL,
    vehicle_reg_no TEXT NOT NULL,
    vehicle_make_model TEXT NOT NULL,
    odometer INTEGER DEFAULT 0,
    assigned_technician_id TEXT REFERENCES technicians(id) ON DELETE SET NULL,
    assigned_technician_name TEXT,
    status TEXT DEFAULT 'RECEIVED',
    complaints JSONB DEFAULT '[]'::jsonb,
    custom_complaint_notes TEXT,
    diagnosis_notes TEXT,
    estimated_amount NUMERIC(10, 2) DEFAULT 0.0,
    estimated_delivery_date TIMESTAMP WITH TIME ZONE,
    total_labor NUMERIC(10, 2) DEFAULT 0.0,
    total_parts NUMERIC(10, 2) DEFAULT 0.0,
    grand_total NUMERIC(10, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE
);

-- 10. Job Items (Labor + Parts on Job Card)
CREATE TABLE IF NOT EXISTS job_items (
    id TEXT PRIMARY KEY DEFAULT ('ji_' || substr(md5(random()::text), 1, 8)),
    job_card_id TEXT NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
    item_type TEXT DEFAULT 'LABOR',
    item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
    barcode TEXT,
    name TEXT NOT NULL,
    hsn_code TEXT,
    quantity INTEGER DEFAULT 1,
    unit_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 0.0,
    total_price NUMERIC(10, 2) DEFAULT 0.0,
    technician_id TEXT REFERENCES technicians(id) ON DELETE SET NULL,
    technician_name TEXT
);

-- 11. Invoices Table
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY DEFAULT ('inv_' || substr(md5(random()::text), 1, 8)),
    invoice_number TEXT NOT NULL UNIQUE,
    invoice_date DATE NOT NULL DEFAULT CURRENT_DATE,
    invoice_type TEXT DEFAULT 'JOB_SERVICE',
    job_card_id TEXT REFERENCES job_cards(id) ON DELETE SET NULL,
    job_number TEXT,
    customer_id TEXT REFERENCES customers(id) ON DELETE SET NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    customer_address TEXT,
    customer_gstin TEXT,
    vehicle_reg_no TEXT,
    vehicle_make_model TEXT,
    odometer INTEGER DEFAULT 0,
    subtotal_labor NUMERIC(12, 2) DEFAULT 0.0,
    subtotal_parts NUMERIC(12, 2) DEFAULT 0.0,
    taxable_subtotal NUMERIC(12, 2) DEFAULT 0.0,
    cgst_total NUMERIC(10, 2) DEFAULT 0.0,
    sgst_total NUMERIC(10, 2) DEFAULT 0.0,
    tax_total NUMERIC(10, 2) DEFAULT 0.0,
    discount_amount NUMERIC(10, 2) DEFAULT 0.0,
    grand_total NUMERIC(12, 2) DEFAULT 0.0,
    amount_paid NUMERIC(12, 2) DEFAULT 0.0,
    balance_due NUMERIC(12, 2) DEFAULT 0.0,
    payment_status TEXT DEFAULT 'PAID',
    payment_mode TEXT DEFAULT 'UPI',
    bank_account_id TEXT,
    upi_ref_no TEXT,
    upi_payment_link TEXT,
    whatsapp_sent BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 12. Invoice Items Table
CREATE TABLE IF NOT EXISTS invoice_items (
    id TEXT PRIMARY KEY DEFAULT ('ii_' || substr(md5(random()::text), 1, 8)),
    invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    item_type TEXT DEFAULT 'PART',
    item_id TEXT REFERENCES inventory_items(id) ON DELETE SET NULL,
    barcode TEXT,
    name TEXT NOT NULL,
    hsn_sac TEXT DEFAULT '8536',
    quantity INTEGER DEFAULT 1,
    unit_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    taxable_amount NUMERIC(10, 2) DEFAULT 0.0,
    cgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    sgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    total_price NUMERIC(10, 2) DEFAULT 0.0,
    technician_name TEXT
);

-- Indexes for lightning fast lookups
CREATE INDEX IF NOT EXISTS idx_inv_items_barcode ON inventory_items(barcode);
CREATE INDEX IF NOT EXISTS idx_job_cards_status ON job_cards(status);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_vehicles_reg ON vehicles(reg_number);
