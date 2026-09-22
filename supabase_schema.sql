-- =========================================================
-- AUTVOLT PRO & CLOUD HQ: COMPLETE SUPABASE POSTGRESQL SCHEMA
-- PostgreSQL schema for Supabase Cloud Database Deployment
-- =========================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users & Authentication Table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT ('user_' || substr(md5(random()::text), 1, 8)),
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT DEFAULT 'STAFF', -- SUPER_ADMIN, ADMIN, STAFF
    email TEXT,
    phone TEXT,
    whatsapp_mobile TEXT,
    tenant_id TEXT DEFAULT 'tenant_1',
    status TEXT DEFAULT 'ACTIVE',
    reset_token TEXT,
    reset_token_expiry TIMESTAMP WITH TIME ZONE,
    otp_code TEXT,
    otp_expiry TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Multi-Tenant SaaS Workshop Clients Table
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY DEFAULT ('tenant_' || substr(md5(random()::text), 1, 8)),
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
    bank_branch TEXT DEFAULT 'Main',
    gst_slabs TEXT DEFAULT '["0", "5", "12", "18", "28"]',
    language TEXT DEFAULT 'en',
    master_pin TEXT DEFAULT '1234',
    status TEXT DEFAULT 'ACTIVE', -- ACTIVE, LOCKED, SUSPENDED
    subscription_plan TEXT DEFAULT 'PRO_ANNUAL',
    subscription_start_date DATE DEFAULT CURRENT_DATE,
    subscription_end_date DATE DEFAULT (CURRENT_DATE + INTERVAL '1 year'),
    price_paid NUMERIC(12, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. SaaS Subscriptions History Table
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY DEFAULT ('sub_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT REFERENCES tenants(id) ON DELETE CASCADE,
    plan_name TEXT DEFAULT 'PRO_ANNUAL',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    is_active INTEGER DEFAULT 1,
    billing_cycle TEXT DEFAULT 'YEARLY', -- MONTHLY, YEARLY
    price_paid NUMERIC(12, 2) DEFAULT 0.0,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. SaaS Vendor Tax Invoices (Software Company Books)
CREATE TABLE IF NOT EXISTS saas_vendor_invoices (
    id TEXT PRIMARY KEY DEFAULT ('sinv_' || substr(md5(random()::text), 1, 8)),
    invoice_no TEXT UNIQUE NOT NULL,
    tenant_id TEXT NOT NULL,
    tenant_name TEXT NOT NULL,
    invoice_date DATE NOT NULL DEFAULT CURRENT_DATE,
    plan_type TEXT DEFAULT 'YEARLY',
    subscription_start DATE,
    subscription_end DATE,
    taxable_amount NUMERIC(12, 2) DEFAULT 0.0,
    cgst_rate NUMERIC(5, 2) DEFAULT 9.0,
    cgst_amount NUMERIC(12, 2) DEFAULT 0.0,
    sgst_rate NUMERIC(5, 2) DEFAULT 9.0,
    sgst_amount NUMERIC(12, 2) DEFAULT 0.0,
    total_amount NUMERIC(12, 2) DEFAULT 0.0,
    payment_status TEXT DEFAULT 'PAID',
    payment_mode TEXT DEFAULT 'UPI',
    payment_ref TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. SaaS Vendor Company Profile (Software Provider Details)
CREATE TABLE IF NOT EXISTS saas_vendor_profile (
    id TEXT PRIMARY KEY DEFAULT 'vendor_main',
    company_name TEXT NOT NULL DEFAULT 'AutoVolt Technologies Pvt Ltd',
    tagline TEXT DEFAULT 'Enterprise Automotive Workshop SaaS Platform',
    gstin TEXT DEFAULT '32AABCA9876C1Z5',
    email TEXT DEFAULT 'billing@autovoltcloud.com',
    phone TEXT DEFAULT '+91 98470 12345',
    whatsapp_phone TEXT DEFAULT '+919847012345',
    address TEXT DEFAULT 'CyberPark, Kozhikode / Infopark, Kochi, Kerala - 682042',
    upi_id TEXT DEFAULT 'autovoltcloud@icici',
    upi_payee_name TEXT DEFAULT 'AutoVolt Technologies',
    bank_name TEXT DEFAULT 'HDFC Bank Ltd',
    bank_account_no TEXT DEFAULT '50200088991122',
    bank_ifsc TEXT DEFAULT 'HDFC0001234',
    monthly_fee NUMERIC(10, 2) DEFAULT 999.0,
    yearly_fee NUMERIC(10, 2) DEFAULT 9999.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. Workshop Profile Table (Active Client Garage Details)
CREATE TABLE IF NOT EXISTS workshop_profile (
    id TEXT PRIMARY KEY DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'SPARK AUTO ELECTRICALS',
    subtitle TEXT DEFAULT 'Auto Electrical & Electronic Service Center',
    owner_name TEXT DEFAULT 'Shafi V.',
    phone TEXT NOT NULL DEFAULT '+91 98765 43210',
    email TEXT DEFAULT 'sparkautocare@gmail.com',
    address TEXT NOT NULL DEFAULT 'Near Highway Junction, Ernakulam, Kerala - 682001',
    gstin TEXT DEFAULT '32AABCS1429B1Z8',
    logo_url TEXT,
    upi_id TEXT NOT NULL DEFAULT 'sparkautoworkshop@okaxis',
    upi_payee_name TEXT DEFAULT 'SPARK AUTO ELECTRICALS',
    bank_name TEXT DEFAULT 'State Bank of India',
    bank_account_no TEXT DEFAULT '39876543210',
    bank_ifsc TEXT DEFAULT 'SBIN0001234',
    bank_branch TEXT DEFAULT 'Ernakulam Main',
    gst_slabs TEXT DEFAULT '["0", "5", "12", "18", "28"]',
    language TEXT DEFAULT 'en',
    currency TEXT DEFAULT '₹',
    master_pin TEXT DEFAULT '1234',
    terms TEXT DEFAULT '1. Electrical parts warranty as per manufacturer policy.\n2. Goods once fitted cannot be returned.\n3. Payment due upon completion.',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 7. Technicians & Staff Table
CREATE TABLE IF NOT EXISTS technicians (
    id TEXT PRIMARY KEY DEFAULT ('tech_' || substr(md5(random()::text), 1, 8)),
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    role TEXT DEFAULT 'Senior Auto Electrician',
    commission_pct NUMERIC(5, 2) DEFAULT 10.0,
    daily_wage NUMERIC(10, 2) DEFAULT 0.0,
    status TEXT DEFAULT 'Active',
    is_on_leave INTEGER DEFAULT 0,
    current_advance_balance NUMERIC(10, 2) DEFAULT 0.0,
    notes TEXT,
    total_jobs INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 8. Technician Wages & Payroll
CREATE TABLE IF NOT EXISTS technician_wages (
    id TEXT PRIMARY KEY DEFAULT ('wage_' || substr(md5(random()::text), 1, 8)),
    technician_id TEXT REFERENCES technicians(id) ON DELETE CASCADE,
    technician_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    days_worked INTEGER DEFAULT 6,
    daily_rate NUMERIC(10, 2) DEFAULT 0.0,
    base_wages NUMERIC(10, 2) DEFAULT 0.0,
    advance_deductions NUMERIC(10, 2) DEFAULT 0.0,
    net_paid NUMERIC(10, 2) DEFAULT 0.0,
    payment_mode TEXT DEFAULT 'CASH',
    payment_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Technician Advance Ledger
CREATE TABLE IF NOT EXISTS technician_advances (
    id TEXT PRIMARY KEY DEFAULT ('adv_' || substr(md5(random()::text), 1, 8)),
    technician_id TEXT REFERENCES technicians(id) ON DELETE CASCADE,
    technician_name TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    advance_date DATE DEFAULT CURRENT_DATE,
    reason TEXT,
    status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 10. Customers Table
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

-- 11. Vehicles Table
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

-- 12. Inventory Items & Spare Parts Table
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
    location_rack TEXT DEFAULT 'Main',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 13. Stock Adjustment Logs
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

-- 14. Job Cards Table (Vehicle Service Book)
CREATE TABLE IF NOT EXISTS job_cards (
    id TEXT PRIMARY KEY DEFAULT ('job_' || substr(md5(random()::text), 1, 8)),
    job_number TEXT NOT NULL UNIQUE,
    vehicle_reg_no TEXT NOT NULL,
    vehicle_make_model TEXT,
    customer_id TEXT,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    odometer INTEGER DEFAULT 0,
    fuel_level TEXT DEFAULT 'Half',
    complaint_checklist TEXT DEFAULT '[]',
    custom_complaint_notes TEXT,
    diagnosis_notes TEXT,
    assigned_technician_id TEXT REFERENCES technicians(id) ON DELETE SET NULL,
    assigned_technician_name TEXT,
    status TEXT DEFAULT 'RECEIVED', -- RECEIVED, INSPECTION, IN_PROGRESS, COMPLETED, DELIVERED, CANCELLED
    estimated_cost NUMERIC(10, 2) DEFAULT 0.0,
    final_cost NUMERIC(10, 2) DEFAULT 0.0,
    invoice_id TEXT,
    inward_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    estimated_delivery TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 15. Job Card Items (Parts & Labor)
CREATE TABLE IF NOT EXISTS job_card_items (
    id TEXT PRIMARY KEY DEFAULT ('jitem_' || substr(md5(random()::text), 1, 8)),
    job_card_id TEXT REFERENCES job_cards(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL, -- PART, LABOR, OUTSOURCED
    item_id TEXT,
    barcode TEXT,
    name TEXT NOT NULL,
    hsn_code TEXT DEFAULT '8536',
    quantity NUMERIC(10, 2) DEFAULT 1.0,
    unit_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    total_price NUMERIC(10, 2) DEFAULT 0.0,
    technician_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 16. Invoices Table (Tax Invoices)
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY DEFAULT ('inv_' || substr(md5(random()::text), 1, 8)),
    invoice_number TEXT NOT NULL UNIQUE,
    job_card_id TEXT,
    customer_id TEXT,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    customer_address TEXT,
    customer_gstin TEXT,
    vehicle_reg_no TEXT,
    vehicle_model TEXT,
    subtotal_labor NUMERIC(10, 2) DEFAULT 0.0,
    subtotal_parts NUMERIC(10, 2) DEFAULT 0.0,
    discount_amount NUMERIC(10, 2) DEFAULT 0.0,
    taxable_amount NUMERIC(10, 2) DEFAULT 0.0,
    cgst_total NUMERIC(10, 2) DEFAULT 0.0,
    sgst_total NUMERIC(10, 2) DEFAULT 0.0,
    tax_total NUMERIC(10, 2) DEFAULT 0.0,
    grand_total NUMERIC(10, 2) DEFAULT 0.0,
    amount_paid NUMERIC(10, 2) DEFAULT 0.0,
    balance_due NUMERIC(10, 2) DEFAULT 0.0,
    payment_mode TEXT DEFAULT 'UPI',
    payment_status TEXT DEFAULT 'PAID',
    payment_reference TEXT,
    upi_payment_link TEXT,
    pdf_path TEXT,
    invoice_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 17. Invoice Items Table
CREATE TABLE IF NOT EXISTS invoice_items (
    id TEXT PRIMARY KEY DEFAULT ('inv_item_' || substr(md5(random()::text), 1, 8)),
    invoice_id TEXT REFERENCES invoices(id) ON DELETE CASCADE,
    item_type TEXT NOT NULL,
    item_id TEXT,
    barcode TEXT,
    name TEXT NOT NULL,
    hsn_sac TEXT DEFAULT '8536',
    quantity NUMERIC(10, 2) DEFAULT 1.0,
    unit_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    taxable_amount NUMERIC(10, 2) DEFAULT 0.0,
    cgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    sgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    total_price NUMERIC(10, 2) DEFAULT 0.0,
    technician_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 18. Invoice Payment Transactions (Khata Settlement)
CREATE TABLE IF NOT EXISTS invoice_payments (
    id TEXT PRIMARY KEY DEFAULT ('pay_' || substr(md5(random()::text), 1, 8)),
    invoice_id TEXT REFERENCES invoices(id) ON DELETE CASCADE,
    invoice_number TEXT NOT NULL,
    payment_date DATE DEFAULT CURRENT_DATE,
    amount_paid NUMERIC(10, 2) NOT NULL,
    payment_mode TEXT DEFAULT 'UPI',
    reference_no TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 19. Purchase Bills (Supplier Inward)
CREATE TABLE IF NOT EXISTS purchase_bills (
    id TEXT PRIMARY KEY DEFAULT ('pur_' || substr(md5(random()::text), 1, 8)),
    bill_number TEXT NOT NULL UNIQUE,
    supplier_name TEXT NOT NULL,
    supplier_gstin TEXT,
    supplier_phone TEXT,
    bill_date DATE DEFAULT CURRENT_DATE,
    taxable_amount NUMERIC(10, 2) DEFAULT 0.0,
    cgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    sgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    total_amount NUMERIC(10, 2) DEFAULT 0.0,
    payment_status TEXT DEFAULT 'PAID',
    payment_mode TEXT DEFAULT 'BANK_TRANSFER',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 20. Purchase Items
CREATE TABLE IF NOT EXISTS purchase_items (
    id TEXT PRIMARY KEY DEFAULT ('pitem_' || substr(md5(random()::text), 1, 8)),
    purchase_bill_id TEXT REFERENCES purchase_bills(id) ON DELETE CASCADE,
    part_name TEXT NOT NULL,
    barcode TEXT,
    hsn_code TEXT DEFAULT '8536',
    quantity INTEGER DEFAULT 1,
    unit_cost NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    total_cost NUMERIC(10, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 21. Debit Notes (Purchase Returns to Supplier)
CREATE TABLE IF NOT EXISTS debit_notes (
    id TEXT PRIMARY KEY DEFAULT ('dn_' || substr(md5(random()::text), 1, 8)),
    debit_note_no TEXT NOT NULL UNIQUE,
    purchase_bill_id TEXT,
    supplier_name TEXT NOT NULL,
    return_date DATE DEFAULT CURRENT_DATE,
    part_name TEXT NOT NULL,
    barcode TEXT,
    return_qty INTEGER DEFAULT 1,
    unit_cost NUMERIC(10, 2) DEFAULT 0.0,
    total_amount NUMERIC(10, 2) DEFAULT 0.0,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 22. Sales Returns / Credit Notes (Customer Returns)
CREATE TABLE IF NOT EXISTS sales_returns (
    id TEXT PRIMARY KEY DEFAULT ('cn_' || substr(md5(random()::text), 1, 8)),
    credit_note_no TEXT NOT NULL UNIQUE,
    invoice_number TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    return_date DATE DEFAULT CURRENT_DATE,
    part_name TEXT NOT NULL,
    barcode TEXT,
    return_qty INTEGER DEFAULT 1,
    refund_amount NUMERIC(10, 2) DEFAULT 0.0,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 23. Operating Expenses Table
CREATE TABLE IF NOT EXISTS expenses (
    id TEXT PRIMARY KEY DEFAULT ('exp_' || substr(md5(random()::text), 1, 8)),
    expense_category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    payment_mode TEXT DEFAULT 'CASH',
    paid_to TEXT,
    receipt_no TEXT,
    expense_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 24. Bank & Cash Ledgers
CREATE TABLE IF NOT EXISTS bank_accounts (
    id TEXT PRIMARY KEY DEFAULT ('bank_' || substr(md5(random()::text), 1, 8)),
    account_name TEXT NOT NULL,
    account_type TEXT DEFAULT 'CURRENT',
    bank_name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    ifsc_code TEXT NOT NULL,
    opening_balance NUMERIC(12, 2) DEFAULT 0.0,
    current_balance NUMERIC(12, 2) DEFAULT 0.0,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 25. Activity Audit Logs
CREATE TABLE IF NOT EXISTS activity_logs (
    id TEXT PRIMARY KEY DEFAULT ('log_' || substr(md5(random()::text), 1, 8)),
    username TEXT DEFAULT 'Admin',
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- =========================================================
-- SEED INITIAL ENTERPRISE DATA
-- =========================================================

-- Insert Default Super Admin and Staff (Password: admin123, staff123)
-- SHA-256 with static seed for instant login
INSERT INTO users (id, username, password_hash, full_name, role, email, phone, whatsapp_mobile, status)
VALUES 
('user_admin', 'admin', 'e6378c2e6f49463996766d3a2468bfb85b6abf881eb5d45d94bc725f190bc1f0$b4c73bb859a68c66e2c39fa42194383177651a248cf6c4d7b7e289f666f28b21', 'Super Administrator', 'SUPER_ADMIN', 'admin@autovolt.com', '+91 98765 00000', '+919876500000', 'ACTIVE'),
('user_staff', 'staff', 'e6378c2e6f49463996766d3a2468bfb85b6abf881eb5d45d94bc725f190bc1f0$b4c73bb859a68c66e2c39fa42194383177651a248cf6c4d7b7e289f666f28b21', 'Workshop Service Desk', 'STAFF', 'service@sparkauto.com', '+91 98765 11111', '+919876511111', 'ACTIVE')
ON CONFLICT (username) DO NOTHING;

-- Insert SaaS Vendor Company Profile
INSERT INTO saas_vendor_profile (id, company_name, tagline, gstin, email, phone, whatsapp_phone, address, upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc)
VALUES ('vendor_main', 'AutoVolt Technologies Pvt Ltd', 'Enterprise Automotive Workshop SaaS Platform', '32AABCA9876C1Z5', 'billing@autovoltcloud.com', '+91 98470 12345', '+919847012345', 'CyberPark, Kozhikode / Infopark, Kochi, Kerala - 682042', 'autovoltcloud@icici', 'AutoVolt Technologies', 'HDFC Bank Ltd', '50200088991122', 'HDFC0001234')
ON CONFLICT (id) DO NOTHING;

-- Insert Active Workshop Profile
INSERT INTO workshop_profile (id, name, subtitle, owner_name, phone, email, address, gstin, upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc, bank_branch, gst_slabs, language, master_pin)
VALUES ('default', 'SPARK AUTO ELECTRICALS', 'Automotive Electrical & Electronic Service Center', 'Shafi V.', '+91 98765 43210', 'sparkautocare@gmail.com', 'Near Highway Junction, Ernakulam, Kerala - 682001', '32AABCS1429B1Z8', 'sparkautoworkshop@okaxis', 'SPARK AUTO ELECTRICALS', 'State Bank of India', '39876543210', 'SBIN0001234', 'Ernakulam Main', '["0", "5", "12", "18", "28"]', 'en', '1234')
ON CONFLICT (id) DO NOTHING;
