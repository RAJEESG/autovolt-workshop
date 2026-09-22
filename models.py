from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

# --- User & Authentication Models ---
class User(BaseModel):
    id: Optional[str] = None
    username: str
    full_name: str
    role: str = "STAFF"  # SUPER_ADMIN, OWNER, MANAGER, STAFF
    email: Optional[str] = None
    phone: Optional[str] = None
    status: str = "ACTIVE"  # ACTIVE, INACTIVE
    created_at: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class PasswordResetRequest(BaseModel):
    email_or_phone: str

class MasterPinVerifyRequest(BaseModel):
    pin: str
    action: str = "DELETE_RECORD"
    record_id: Optional[str] = None

# --- SaaS Multi-tenant & Subscription Models ---
class Subscription(BaseModel):
    id: Optional[str] = None
    tenant_id: str
    plan_name: str = "PRO_ANNUAL"  # MONTHLY, ANNUAL, TRIAL, ENTERPRISE
    start_date: str
    end_date: str
    is_active: bool = True
    billing_cycle: str = "YEARLY"  # MONTHLY, YEARLY
    price_paid: float = 0.0
    notes: Optional[str] = None

class Tenant(BaseModel):
    id: Optional[str] = None
    name: str = "SPARK AUTO ELECTRICALS"
    owner_name: str = "Shafi V."
    phone: str = "+91 98765 43210"
    email: Optional[str] = "sparkautocare@gmail.com"
    address: str = "Near Highway Junction, Ernakulam, Kerala - 682001"
    gstin: Optional[str] = "32AABCS1429B1Z8"
    upi_id: str = "sparkautoworkshop@okaxis"
    bank_name: Optional[str] = "State Bank of India"
    bank_account_no: Optional[str] = "39876543210"
    bank_ifsc: Optional[str] = "SBIN0001234"
    bank_branch: Optional[str] = "Ernakulam Main"
    language: str = "en"  # en, ta (Tamil), ml (Malayalam)
    status: str = "ACTIVE"  # ACTIVE, EXPIRED, SUSPENDED
    subscription_end_date: Optional[str] = None
    created_at: Optional[str] = None

# --- Technician, Wages & Attendance Models ---
class Technician(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str
    role: str = "Senior Electrician"
    commission_pct: float = 0.0
    daily_wage: float = 0.0
    status: str = "Active"  # Active, Inactive
    is_on_leave: bool = False
    current_advance_balance: float = 0.0
    notes: Optional[str] = None
    total_jobs: int = 0
    created_at: Optional[str] = None

class EmployeeWage(BaseModel):
    id: Optional[str] = None
    technician_id: str
    technician_name: Optional[str] = None
    period_start: str
    period_end: str
    gross_amount: float
    advance_deducted: float = 0.0
    net_paid: float
    payment_date: str
    payment_mode: str = "CASH"  # CASH, UPI, BANK_TRANSFER
    notes: Optional[str] = None
    created_at: Optional[str] = None

class EmployeeAdvance(BaseModel):
    id: Optional[str] = None
    technician_id: str
    technician_name: Optional[str] = None
    amount: float
    advance_date: str
    status: str = "OUTSTANDING"  # OUTSTANDING, ADJUSTED, REPAID
    adjusted_in_wage_id: Optional[str] = None
    payment_mode: str = "CASH"
    notes: Optional[str] = None
    created_at: Optional[str] = None

class AttendanceRecord(BaseModel):
    id: Optional[str] = None
    technician_id: str
    date: str
    status: str = "PRESENT"  # PRESENT, LEAVE, HALF_DAY
    notes: Optional[str] = None

# --- Purchases & Returns Models ---
class PurchaseItem(BaseModel):
    id: Optional[str] = None
    purchase_id: Optional[str] = None
    item_id: Optional[str] = None
    part_name: str
    barcode: Optional[str] = None
    quantity: int = 1
    unit_cost: float = 0.0
    total_cost: float = 0.0

class PurchaseBill(BaseModel):
    id: Optional[str] = None
    bill_number: str  # Supplier invoice #
    supplier_name: str
    bill_date: str
    total_amount: float
    payment_status: str = "PAID"  # PAID, PENDING
    payment_mode: str = "BANK_TRANSFER"
    items: List[PurchaseItem] = []
    notes: Optional[str] = None
    created_at: Optional[str] = None

class PurchaseReturn(BaseModel):
    id: Optional[str] = None
    return_number: str  # Debit Note #
    purchase_id: Optional[str] = None
    supplier_name: str
    item_id: str
    part_name: str
    quantity: int = 1
    unit_cost: float = 0.0
    return_amount: float = 0.0
    return_date: str
    reason: Optional[str] = "Defective Part"
    created_at: Optional[str] = None

class SalesReturn(BaseModel):
    id: Optional[str] = None
    return_number: str  # Credit Note #
    invoice_id: str
    customer_name: str
    item_id: Optional[str] = None
    name: str
    quantity: int = 1
    unit_price: float = 0.0
    refund_amount: float = 0.0
    return_date: str
    refund_mode: str = "CASH"
    reason: Optional[str] = "Customer Returned Part"
    created_at: Optional[str] = None

# --- Activity Audit Trail ---
class ActivityLog(BaseModel):
    id: Optional[str] = None
    username: str = "Admin"
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    details: Optional[str] = None
    created_at: Optional[str] = None

# --- Customer, Vehicle, Inventory & Job Models ---
class Customer(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str
    address: Optional[str] = None
    gstin: Optional[str] = None
    whatsapp_opt_in: bool = True
    total_visits: int = 0
    khata_balance: float = 0.0
    created_at: Optional[str] = None

class Vehicle(BaseModel):
    id: Optional[str] = None
    reg_number: str
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    make_model: str
    vehicle_type: str = "Car"
    fuel_type: str = "Diesel"
    odometer: Optional[int] = 0
    chassis_no: Optional[str] = None
    created_at: Optional[str] = None

class InventoryItem(BaseModel):
    id: Optional[str] = None
    part_name: str
    sku: Optional[str] = None
    barcode: str
    category: str = "Relays & Fuses"
    stock_qty: int = 0
    min_stock_alert: int = 5
    cost_price: float = 0.0
    selling_price: float = 0.0
    tax_rate: float = 18.0
    hsn_code: Optional[str] = "8536"
    unit: str = "pcs"
    warranty_months: int = 0
    supplier_name: Optional[str] = None
    location_rack: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class JobItem(BaseModel):
    id: Optional[str] = None
    job_card_id: Optional[str] = None
    item_type: str = "LABOR"
    item_id: Optional[str] = None
    barcode: Optional[str] = None
    name: str
    hsn_code: Optional[str] = None
    quantity: int = 1
    unit_price: float = 0.0
    tax_rate: float = 0.0
    total_price: float = 0.0
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None

class JobCard(BaseModel):
    id: Optional[str] = None
    job_number: str
    customer_id: Optional[str] = None
    customer_name: str
    customer_phone: str
    vehicle_id: Optional[str] = None
    vehicle_reg_no: str
    vehicle_make_model: str
    odometer: Optional[int] = 0
    assigned_technician_id: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    status: str = "RECEIVED"
    complaints: List[str] = []
    custom_complaint_notes: Optional[str] = None
    diagnosis_notes: Optional[str] = None
    estimated_amount: float = 0.0
    estimated_delivery_date: Optional[str] = None
    items: List[JobItem] = []
    total_labor: float = 0.0
    total_parts: float = 0.0
    grand_total: float = 0.0
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    delivered_at: Optional[str] = None

class InvoiceItem(BaseModel):
    id: Optional[str] = None
    invoice_id: Optional[str] = None
    item_type: str = "PART"
    item_id: Optional[str] = None
    barcode: Optional[str] = None
    name: str
    hsn_sac: str = "8536"
    quantity: int = 1
    unit_price: float = 0.0
    tax_rate: float = 18.0
    taxable_amount: float = 0.0
    cgst_amount: float = 0.0
    sgst_amount: float = 0.0
    total_price: float = 0.0
    technician_name: Optional[str] = None

class Invoice(BaseModel):
    id: Optional[str] = None
    invoice_number: str
    invoice_date: str
    invoice_type: str = "JOB_SERVICE"
    job_card_id: Optional[str] = None
    job_number: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: str
    customer_phone: str
    customer_address: Optional[str] = None
    customer_gstin: Optional[str] = None
    vehicle_reg_no: Optional[str] = None
    vehicle_make_model: Optional[str] = None
    odometer: Optional[int] = 0
    items: List[InvoiceItem] = []
    subtotal_labor: float = 0.0
    subtotal_parts: float = 0.0
    taxable_subtotal: float = 0.0
    cgst_total: float = 0.0
    sgst_total: float = 0.0
    tax_total: float = 0.0
    discount_amount: float = 0.0
    grand_total: float = 0.0
    amount_paid: float = 0.0
    balance_due: float = 0.0
    payment_status: str = "PENDING"  # PENDING, PARTIAL, PAID
    payment_mode: str = "UPI"
    bank_account_id: Optional[str] = None
    upi_payment_link: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None
