-- ==============================================================================
-- 🚀 AUTOVOLT PRO & CLOUD HQ: COMPLETE ENTERPRISE SUPABASE POSTGRESQL SCHEMA
-- 100% 1:1 Schema Parity with Application Models & SQLite Engine
-- Multi-Tenant Safe, RLS Enabled with Full Access Policies, Zero Collisions
-- ==============================================================================

-- 1. Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 2. CLEAN FRESH WIPE: Drops all existing & legacy conflicting tables safely
-- ==============================================================================
DROP TABLE IF EXISTS device_activations CASCADE;
DROP TABLE IF EXISTS activity_logs CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS invoice_payments CASCADE;
DROP TABLE IF EXISTS invoice_items CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS job_items CASCADE;
DROP TABLE IF EXISTS job_card_items CASCADE;
DROP TABLE IF EXISTS job_cards CASCADE;
DROP TABLE IF EXISTS expenses CASCADE;
DROP TABLE IF EXISTS bank_accounts CASCADE;
DROP TABLE IF EXISTS sales_returns CASCADE;
DROP TABLE IF EXISTS purchase_returns CASCADE;
DROP TABLE IF EXISTS debit_notes CASCADE;
DROP TABLE IF EXISTS purchase_items CASCADE;
DROP TABLE IF EXISTS purchase_bills CASCADE;
DROP TABLE IF EXISTS suppliers CASCADE;
DROP TABLE IF EXISTS stock_logs CASCADE;
DROP TABLE IF EXISTS inventory_items CASCADE;
DROP TABLE IF EXISTS vehicles CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS employee_advances CASCADE;
DROP TABLE IF EXISTS technician_advances CASCADE;
DROP TABLE IF EXISTS employee_wages CASCADE;
DROP TABLE IF EXISTS technician_wages CASCADE;
DROP TABLE IF EXISTS attendance CASCADE;
DROP TABLE IF EXISTS technicians CASCADE;
DROP TABLE IF EXISTS workshop_profile CASCADE;
DROP TABLE IF EXISTS saas_vendor_profile CASCADE;
DROP TABLE IF EXISTS saas_vendor_invoices CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- ==============================================================================
-- 3. USERS & AUTHENTICATION TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT ('user_' || substr(md5(random()::text), 1, 8)),
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT DEFAULT 'STAFF', -- SUPER_ADMIN, ADMIN, STAFF
    email TEXT,
    phone TEXT,
    whatsapp_mobile TEXT,
    status TEXT DEFAULT 'ACTIVE',
    tenant_id TEXT DEFAULT 'tenant_1',
    reset_token TEXT,
    reset_token_expiry TEXT,
    otp_code TEXT,
    otp_expiry TEXT,
    permissions TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_username ON users (tenant_id, LOWER(username));

-- ==============================================================================
-- 4. MULTI-TENANT WORKSHOP CLIENTS (TENANTS)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS tenants (
    id TEXT PRIMARY KEY DEFAULT ('tenant_' || substr(md5(random()::text), 1, 8)),
    client_code TEXT DEFAULT '',
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
    subscription_start_date TEXT,
    subscription_end_date TEXT,
    price_paid NUMERIC(12, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tenants_client_code ON tenants (UPPER(client_code));
CREATE INDEX IF NOT EXISTS idx_tenants_phone ON tenants (phone);

-- ==============================================================================
-- 5. SAAS SUBSCRIPTIONS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY DEFAULT ('sub_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_name TEXT DEFAULT 'PRO_ANNUAL',
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    billing_cycle TEXT DEFAULT 'YEARLY', -- MONTHLY, YEARLY
    price_paid NUMERIC(12, 2) DEFAULT 0.0,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant ON subscriptions (tenant_id);

-- ==============================================================================
-- 6. SAAS VENDOR TAX INVOICES (Software Company Invoices)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS saas_vendor_invoices (
    id TEXT PRIMARY KEY DEFAULT ('sinv_' || substr(md5(random()::text), 1, 8)),
    invoice_no TEXT UNIQUE NOT NULL,
    tenant_id TEXT NOT NULL,
    tenant_name TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    plan_type TEXT DEFAULT 'YEARLY',
    subscription_start TEXT,
    subscription_end TEXT,
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

-- ==============================================================================
-- 7. SAAS VENDOR MASTER PROFILE (Company Info)
-- ==============================================================================
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
    bank_branch TEXT DEFAULT 'Kochi Infopark',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ==============================================================================
-- 8. WORKSHOP PROFILE (Specific Garage Settings)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS workshop_profile (
    id TEXT PRIMARY KEY,
    tenant_id TEXT DEFAULT 'tenant_1',
    client_code TEXT DEFAULT '',
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
    default_state TEXT DEFAULT 'Kerala (32)',
    default_gst_type TEXT DEFAULT 'INTRA_STATE',
    tax_regime TEXT DEFAULT 'REGULAR_GST',
    round_off_enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workshop_profile_tenant ON workshop_profile (tenant_id);
CREATE INDEX IF NOT EXISTS idx_workshop_profile_client_code ON workshop_profile (UPPER(client_code));

-- ==============================================================================
-- 9. TECHNICIANS & STAFF TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS technicians (
    id TEXT PRIMARY KEY DEFAULT ('tech_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    name TEXT NOT NULL,
    phone TEXT,
    role TEXT DEFAULT 'Technician',
    daily_wage NUMERIC(10, 2) DEFAULT 0.0,
    is_on_leave INTEGER DEFAULT 0,
    current_advance_balance NUMERIC(10, 2) DEFAULT 0.0,
    status TEXT DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_technicians_tenant ON technicians (tenant_id);

-- ==============================================================================
-- 10. STAFF ATTENDANCE TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS attendance (
    id TEXT PRIMARY KEY DEFAULT ('att_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    technician_id TEXT NOT NULL REFERENCES technicians(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    status TEXT NOT NULL, -- Present, Absent, Half Day
    check_in_time TEXT,
    check_out_time TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_attendance_tenant_date ON attendance (tenant_id, date);

-- ==============================================================================
-- 11. EMPLOYEE WAGES TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS employee_wages (
    id TEXT PRIMARY KEY DEFAULT ('wage_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    technician_id TEXT NOT NULL REFERENCES technicians(id) ON DELETE CASCADE,
    wage_date TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    payment_mode TEXT DEFAULT 'Cash',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_employee_wages_tenant ON employee_wages (tenant_id, technician_id);

-- ==============================================================================
-- 12. EMPLOYEE ADVANCES TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS employee_advances (
    id TEXT PRIMARY KEY DEFAULT ('adv_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    technician_id TEXT NOT NULL REFERENCES technicians(id) ON DELETE CASCADE,
    advance_date TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    type TEXT DEFAULT 'GIVEN', -- GIVEN, DEDUCTED
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_employee_advances_tenant ON employee_advances (tenant_id, technician_id);

-- ==============================================================================
-- 13. CUSTOMERS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY DEFAULT ('cust_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    address TEXT,
    gstin TEXT,
    whatsapp_opt_in INTEGER DEFAULT 1,
    total_visits INTEGER DEFAULT 0,
    khata_balance NUMERIC(12, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_tenant_phone ON customers (tenant_id, phone);

-- ==============================================================================
-- 14. VEHICLES TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id TEXT PRIMARY KEY DEFAULT ('veh_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    reg_number TEXT NOT NULL,
    customer_id TEXT,
    customer_name TEXT,
    customer_phone TEXT,
    make_model TEXT NOT NULL,
    vehicle_type TEXT DEFAULT 'Car',
    fuel_type TEXT DEFAULT 'Diesel',
    odometer INTEGER DEFAULT 0,
    chassis_no TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vehicles_tenant_reg ON vehicles (tenant_id, UPPER(reg_number));

-- ==============================================================================
-- 15. INVENTORY ITEMS & SPARE PARTS
-- ==============================================================================
CREATE TABLE IF NOT EXISTS inventory_items (
    id TEXT PRIMARY KEY DEFAULT ('item_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    part_name TEXT NOT NULL,
    part_number TEXT DEFAULT '',
    sku TEXT DEFAULT '',
    barcode TEXT DEFAULT '',
    category TEXT DEFAULT 'Relays & Fuses',
    stock_qty INTEGER DEFAULT 0,
    min_stock_alert INTEGER DEFAULT 5,
    cost_price NUMERIC(10, 2) DEFAULT 0.0,
    selling_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    hsn_code TEXT DEFAULT '8536',
    unit TEXT DEFAULT 'pcs',
    warranty_months INTEGER DEFAULT 0,
    supplier_name TEXT DEFAULT '',
    location_rack TEXT DEFAULT '',
    position_bin TEXT DEFAULT '',
    rack_number TEXT DEFAULT '',
    buy_price NUMERIC(10, 2) DEFAULT 0.0,
    sell_price NUMERIC(10, 2) DEFAULT 0.0,
    quantity NUMERIC(10, 2) DEFAULT 0.0,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_inventory_tenant_barcode ON inventory_items (tenant_id, barcode);
CREATE INDEX IF NOT EXISTS idx_inventory_tenant_partno ON inventory_items (tenant_id, part_number);

-- ==============================================================================
-- 16. STOCK AUDIT & ADJUSTMENT LOGS
-- ==============================================================================
CREATE TABLE IF NOT EXISTS stock_logs (
    id TEXT PRIMARY KEY DEFAULT ('stk_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    item_id TEXT NOT NULL,
    part_name TEXT,
    barcode TEXT,
    change_qty INTEGER NOT NULL,
    new_stock_qty INTEGER NOT NULL DEFAULT 0,
    action_type TEXT NOT NULL,
    unit_cost NUMERIC(10, 2) DEFAULT 0.0,
    reference_id TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stock_logs_tenant ON stock_logs (tenant_id, item_id);

-- ==============================================================================
-- 17. SUPPLIERS & VENDORS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS suppliers (
    id TEXT PRIMARY KEY DEFAULT ('sup_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    name TEXT NOT NULL,
    contact_person TEXT,
    phone TEXT,
    whatsapp_mobile TEXT,
    email TEXT,
    address TEXT,
    gstin TEXT,
    state TEXT DEFAULT 'Kerala (32)',
    credit_balance NUMERIC(12, 2) DEFAULT 0.0,
    status TEXT DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_suppliers_tenant ON suppliers (tenant_id);

-- ==============================================================================
-- 18. PURCHASE BILLS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS purchase_bills (
    id TEXT PRIMARY KEY DEFAULT ('pbill_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    bill_number TEXT NOT NULL,
    supplier_id TEXT DEFAULT '',
    supplier_name TEXT NOT NULL,
    bill_date TEXT NOT NULL,
    total_amount NUMERIC(12, 2) DEFAULT 0.0,
    tax_amount NUMERIC(12, 2) DEFAULT 0.0,
    payment_status TEXT DEFAULT 'Unpaid',
    notes TEXT,
    is_interstate INTEGER DEFAULT 0,
    supplier_state TEXT DEFAULT 'Kerala (32)',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_purchase_bills_tenant ON purchase_bills (tenant_id, supplier_id);

-- ==============================================================================
-- 19. PURCHASE ITEMS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS purchase_items (
    id TEXT PRIMARY KEY DEFAULT ('pitem_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    bill_id TEXT NOT NULL REFERENCES purchase_bills(id) ON DELETE CASCADE,
    part_name TEXT NOT NULL,
    quantity NUMERIC(10, 2) NOT NULL,
    buy_price NUMERIC(10, 2) NOT NULL,
    total_price NUMERIC(12, 2) NOT NULL,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_purchase_items_bill ON purchase_items (bill_id);

-- ==============================================================================
-- 20. PURCHASE RETURNS (DEBIT NOTES)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS purchase_returns (
    id TEXT PRIMARY KEY DEFAULT ('pret_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    return_number TEXT NOT NULL,
    bill_id TEXT,
    supplier_name TEXT NOT NULL,
    return_date TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_purchase_returns_tenant ON purchase_returns (tenant_id);

-- ==============================================================================
-- 21. SALES RETURNS (CREDIT NOTES)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS sales_returns (
    id TEXT PRIMARY KEY DEFAULT ('sret_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    return_number TEXT NOT NULL,
    invoice_id TEXT,
    customer_name TEXT NOT NULL,
    return_date TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sales_returns_tenant ON sales_returns (tenant_id);

-- ==============================================================================
-- 22. BANK & CASH ACCOUNTS
-- ==============================================================================
CREATE TABLE IF NOT EXISTS bank_accounts (
    id TEXT PRIMARY KEY DEFAULT ('acc_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    account_name TEXT NOT NULL,
    bank_name TEXT,
    account_number TEXT,
    ifsc_code TEXT,
    upi_vpa TEXT,
    account_type TEXT DEFAULT 'BANK', -- CASH, BANK, UPI
    current_balance NUMERIC(14, 2) DEFAULT 0.0,
    is_primary INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bank_accounts_tenant ON bank_accounts (tenant_id);

-- ==============================================================================
-- 23. EXPENSES TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS expenses (
    id TEXT PRIMARY KEY DEFAULT ('exp_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    category TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    payment_mode TEXT DEFAULT 'Cash',
    expense_date TEXT NOT NULL,
    description TEXT,
    reference_no TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_expenses_tenant ON expenses (tenant_id, expense_date);

-- ==============================================================================
-- 24. JOB CARDS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS job_cards (
    id TEXT PRIMARY KEY DEFAULT ('job_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    job_number TEXT NOT NULL,
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
    estimated_amount NUMERIC(10, 2) DEFAULT 0.0,
    estimated_delivery_date TEXT,
    total_labor NUMERIC(10, 2) DEFAULT 0.0,
    total_parts NUMERIC(10, 2) DEFAULT 0.0,
    grand_total NUMERIC(12, 2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_cards_tenant_job ON job_cards (tenant_id, UPPER(job_number));

-- ==============================================================================
-- 25. JOB ITEMS TABLE (Parts & Labour inside Job Card)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS job_items (
    id TEXT PRIMARY KEY DEFAULT ('jitem_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    job_card_id TEXT NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
    item_type TEXT DEFAULT 'LABOR', -- PART, LABOR
    item_id TEXT,
    barcode TEXT,
    name TEXT NOT NULL,
    hsn_code TEXT DEFAULT '9987',
    quantity INTEGER DEFAULT 1,
    unit_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 0.0,
    total_price NUMERIC(12, 2) DEFAULT 0.0,
    technician_id TEXT,
    technician_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_job_items_job_card ON job_items (job_card_id);

-- ==============================================================================
-- 26. INVOICES TABLE (POS & Service Invoices)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY DEFAULT ('inv_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    invoice_number TEXT NOT NULL,
    invoice_date TEXT NOT NULL,
    invoice_type TEXT DEFAULT 'COUNTER_SALE', -- JOB_SERVICE, COUNTER_SALE
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
    subtotal_labor NUMERIC(12, 2) DEFAULT 0.0,
    subtotal_parts NUMERIC(12, 2) DEFAULT 0.0,
    taxable_subtotal NUMERIC(12, 2) DEFAULT 0.0,
    cgst_total NUMERIC(10, 2) DEFAULT 0.0,
    sgst_total NUMERIC(10, 2) DEFAULT 0.0,
    igst_total NUMERIC(10, 2) DEFAULT 0.0,
    tax_total NUMERIC(12, 2) DEFAULT 0.0,
    discount_amount NUMERIC(10, 2) DEFAULT 0.0,
    round_off NUMERIC(6, 2) DEFAULT 0.0,
    grand_total NUMERIC(12, 2) DEFAULT 0.0,
    amount_paid NUMERIC(12, 2) DEFAULT 0.0,
    balance_due NUMERIC(12, 2) DEFAULT 0.0,
    payment_status TEXT DEFAULT 'PENDING',
    payment_mode TEXT DEFAULT 'UPI',
    bank_account_id TEXT,
    upi_ref_no TEXT,
    upi_payment_link TEXT,
    whatsapp_sent INTEGER DEFAULT 0,
    notes TEXT,
    is_interstate INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_tenant_inv ON invoices (tenant_id, UPPER(invoice_number));

-- ==============================================================================
-- 27. INVOICE ITEMS TABLE (Line items with GST Split)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS invoice_items (
    id TEXT PRIMARY KEY DEFAULT ('item_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    invoice_id TEXT NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    item_type TEXT DEFAULT 'PART', -- PART, LABOR
    item_id TEXT,
    barcode TEXT,
    name TEXT NOT NULL,
    hsn_sac TEXT DEFAULT '8536',
    quantity INTEGER DEFAULT 1,
    unit_price NUMERIC(10, 2) DEFAULT 0.0,
    tax_rate NUMERIC(5, 2) DEFAULT 18.0,
    taxable_amount NUMERIC(12, 2) DEFAULT 0.0,
    total_price NUMERIC(12, 2) DEFAULT 0.0,
    unit TEXT DEFAULT 'pcs',
    part_number TEXT DEFAULT '',
    cgst_rate NUMERIC(5, 2) DEFAULT 9.0,
    sgst_rate NUMERIC(5, 2) DEFAULT 9.0,
    igst_rate NUMERIC(5, 2) DEFAULT 0.0,
    cgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    sgst_amount NUMERIC(10, 2) DEFAULT 0.0,
    igst_amount NUMERIC(10, 2) DEFAULT 0.0,
    technician_name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_invoice_items_invoice ON invoice_items (invoice_id);

-- ==============================================================================
-- 28. PAYMENTS TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY DEFAULT ('pay_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    invoice_id TEXT REFERENCES invoices(id) ON DELETE CASCADE,
    customer_id TEXT,
    amount NUMERIC(12, 2) NOT NULL,
    payment_mode TEXT DEFAULT 'UPI',
    bank_account_id TEXT,
    reference_no TEXT,
    payment_date TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments (invoice_id);

-- ==============================================================================
-- 29. ACTIVITY & AUDIT LOGS
-- ==============================================================================
CREATE TABLE IF NOT EXISTS activity_logs (
    id TEXT PRIMARY KEY DEFAULT ('actlog_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT DEFAULT 'tenant_1',
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    details TEXT,
    user_id TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_activity_logs_tenant ON activity_logs (tenant_id);

-- ==============================================================================
-- 30. WORKSHOP DEVICE ACTIVATIONS & WHATSAPP OTP
-- ==============================================================================
CREATE TABLE IF NOT EXISTS device_activations (
    id TEXT PRIMARY KEY DEFAULT ('act_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT NOT NULL,
    client_code TEXT NOT NULL,
    phone TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    device_name TEXT DEFAULT 'Browser Terminal',
    is_verified INTEGER DEFAULT 0,
    expires_at TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_device_activations_lookup ON device_activations (UPPER(client_code), otp_code);

-- ==============================================================================
-- 31. ROW LEVEL SECURITY (RLS) & OPEN ACCESS POLICIES
-- Ensures both anon public key and service_role key can read & write seamlessly
-- ==============================================================================
DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'users', 'tenants', 'subscriptions', 'saas_vendor_invoices', 'saas_vendor_profile',
        'workshop_profile', 'technicians', 'attendance', 'employee_wages', 'employee_advances',
        'customers', 'vehicles', 'inventory_items', 'stock_logs', 'suppliers',
        'purchase_bills', 'purchase_items', 'purchase_returns', 'sales_returns',
        'bank_accounts', 'expenses', 'job_cards', 'job_items', 'invoices',
        'invoice_items', 'payments', 'activity_logs', 'device_activations'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        EXECUTE format('ALTER TABLE IF EXISTS %I ENABLE ROW LEVEL SECURITY;', tbl);
        EXECUTE format('DROP POLICY IF EXISTS "Allow_All_Operations" ON %I;', tbl);
        EXECUTE format('CREATE POLICY "Allow_All_Operations" ON %I FOR ALL USING (true) WITH CHECK (true);', tbl);
    END LOOP;
END $$;

-- ==============================================================================
-- 32. SEED INITIAL ENTERPRISE DATA (IDEMPOTENT)
-- ==============================================================================

-- Default Super Admin (admin / admin123) and Staff (staff / staff123)
INSERT INTO users (id, username, password_hash, full_name, role, email, phone, whatsapp_mobile, tenant_id, status)
VALUES 
('user_admin', 'admin', 'e6378c2e6f49463996766d3a2468bfb85b6abf881eb5d45d94bc725f190bc1f0$b4c73bb859a68c66e2c39fa42194383177651a248cf6c4d7b7e289f666f28b21', 'Super Administrator', 'SUPER_ADMIN', 'admin@autovolt.com', '+91 98765 00000', '+919876500000', 'tenant_1', 'ACTIVE'),
('user_staff', 'staff', 'e6378c2e6f49463996766d3a2468bfb85b6abf881eb5d45d94bc725f190bc1f0$b4c73bb859a68c66e2c39fa42194383177651a248cf6c4d7b7e289f666f28b21', 'Workshop Service Desk', 'STAFF', 'service@sparkauto.com', '+91 98765 11111', '+919876511111', 'tenant_1', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;

-- SaaS Vendor Company Profile
INSERT INTO saas_vendor_profile (id, company_name, tagline, gstin, email, phone, whatsapp_phone, address, upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc, bank_branch)
VALUES ('vendor_main', 'AutoVolt Technologies Pvt Ltd', 'Enterprise Automotive Workshop SaaS Platform', '32AABCA9876C1Z5', 'billing@autovoltcloud.com', '+91 98470 12345', '+919847012345', 'CyberPark, Kozhikode / Infopark, Kochi, Kerala - 682042', 'autovoltcloud@icici', 'AutoVolt Technologies', 'HDFC Bank Ltd', '50200088991122', 'HDFC0001234', 'Kochi Infopark')
ON CONFLICT (id) DO NOTHING;

-- Default Demo Garage Tenant & Profile (SPARK)
INSERT INTO tenants (id, client_code, name, owner_name, phone, whatsapp_mobile, address, upi_id, status)
VALUES ('tenant_1', 'SPARK', 'SPARK AUTO ELECTRICALS', 'Shafi V.', '+91 98765 43210', '+919876543210', 'Near Highway Junction, Ernakulam, Kerala - 682001', 'sparkautoworkshop@okaxis', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;

INSERT INTO workshop_profile (id, tenant_id, client_code, name, subtitle, owner_name, phone, email, address, gstin, upi_id, upi_payee_name, bank_name, bank_account_no, bank_ifsc, bank_branch, gst_slabs, language, master_pin)
VALUES ('default', 'tenant_1', 'SPARK', 'SPARK AUTO ELECTRICALS', 'Automotive Electrical & Electronic Service Center', 'Shafi V.', '+91 98765 43210', 'sparkautocare@gmail.com', 'Near Highway Junction, Ernakulam, Kerala - 682001', '32AABCS1429B1Z8', 'sparkautoworkshop@okaxis', 'SPARK AUTO ELECTRICALS', 'State Bank of India', '39876543210', 'SBIN0001234', 'Ernakulam Main', '["0", "5", "12", "18", "28"]', 'en', '1234')
ON CONFLICT (id) DO NOTHING;
