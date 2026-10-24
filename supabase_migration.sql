-- =========================================================
-- 🚀 AUTVOLT PRO: SAFE SUPABASE UPGRADE MIGRATION SCRIPT
-- RUN THIS IN SUPABASE SQL EDITOR FOR EXISTING DATABASES
-- 100% Safe: Never deletes tables or data; checks existence first!
-- =========================================================

-- 1. Tenants Table Upgrades (Multi-Tenant Workshop ID)
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS client_code TEXT DEFAULT '';
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS whatsapp_mobile TEXT;
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS upi_payee_name TEXT;
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS gst_slabs TEXT DEFAULT '["0", "5", "12", "18", "28"]';
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'en';
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS master_pin TEXT DEFAULT '1234';
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS subscription_plan TEXT DEFAULT 'PRO_ANNUAL';
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS subscription_start_date DATE DEFAULT CURRENT_DATE;
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS subscription_end_date DATE DEFAULT (CURRENT_DATE + INTERVAL '1 year');
ALTER TABLE IF EXISTS tenants ADD COLUMN IF NOT EXISTS price_paid NUMERIC(12, 2) DEFAULT 0.0;

-- 2. Workshop Profile Table Upgrades
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS client_code TEXT DEFAULT '';
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS logo_url TEXT;
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS upi_payee_name TEXT;
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS gst_slabs TEXT DEFAULT '["0", "5", "12", "18", "28"]';
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS default_state TEXT DEFAULT 'Kerala (32)';
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS default_gst_type TEXT DEFAULT 'INTRA_STATE';
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS tax_regime TEXT DEFAULT 'REGULAR_GST';
ALTER TABLE IF EXISTS workshop_profile ADD COLUMN IF NOT EXISTS round_off_enabled INTEGER DEFAULT 1;

-- 3. Users Table (Multi-Tenant Username Isolation)
-- Allows different workshops to have identical usernames (e.g. 'admin') without collision
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS permissions TEXT;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS whatsapp_mobile TEXT;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS otp_code TEXT;
ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS otp_expiry TIMESTAMP WITH TIME ZONE;

-- Safely drop old global unique constraint on username if present
DO $$ 
BEGIN 
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE constraint_name = 'users_username_key' AND table_name = 'users'
    ) THEN 
        ALTER TABLE users DROP CONSTRAINT users_username_key; 
    END IF; 
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tenant_username ON users (tenant_id, username);

-- 4. Multi-Tenant column check across operational tables
ALTER TABLE IF EXISTS technicians ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS technician_wages ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS technician_advances ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS customers ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS inventory_items ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS stock_logs ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS job_cards ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS invoices ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS invoice_payments ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS purchase_bills ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS debit_notes ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS sales_returns ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS expenses ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS bank_accounts ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';
ALTER TABLE IF EXISTS activity_logs ADD COLUMN IF NOT EXISTS tenant_id TEXT DEFAULT 'tenant_1';

-- 5. Safe Unique Indexes per-tenant (replaces old global collision keys)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'job_cards_job_number_key' AND table_name = 'job_cards') THEN
        ALTER TABLE job_cards DROP CONSTRAINT job_cards_job_number_key;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name = 'invoices_invoice_number_key' AND table_name = 'invoices') THEN
        ALTER TABLE invoices DROP CONSTRAINT invoices_invoice_number_key;
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_job_cards_tenant_job ON job_cards (tenant_id, job_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_invoices_tenant_inv ON invoices (tenant_id, invoice_number);

-- 6. Workshop Device Activations & WhatsApp OTP Table
CREATE TABLE IF NOT EXISTS device_activations (
    id TEXT PRIMARY KEY DEFAULT ('act_' || substr(md5(random()::text), 1, 8)),
    tenant_id TEXT NOT NULL,
    client_code TEXT NOT NULL,
    phone TEXT NOT NULL,
    otp_code TEXT NOT NULL,
    device_name TEXT DEFAULT 'Browser Terminal',
    is_verified INTEGER DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
