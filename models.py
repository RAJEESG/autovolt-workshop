from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field

# --- Workshop & Profile Models ---
class WorkshopProfile(BaseModel):
    id: Optional[str] = "default"
    name: str = "SPARK AUTO ELECTRICALS"
    subtitle: Optional[str] = "Automotive Electrical & Electronic Service Center"
    owner_name: Optional[str] = "Shafi V."
    phone: str = "+91 98765 43210"
    email: Optional[str] = "sparkautocare@gmail.com"
    address: str = "Near Highway Junction, Ernakulam, Kerala - 682001"
    gstin: Optional[str] = "32AABCS1429B1Z8"
    upi_id: str = "sparkautoworkshop@okaxis"
    bank_name: Optional[str] = "State Bank of India"
    bank_account_no: Optional[str] = "39876543210"
    bank_ifsc: Optional[str] = "SBIN0001234"
    bank_branch: Optional[str] = "Ernakulam Main"
    currency: str = "₹"
    terms: Optional[str] = "1. Electrical parts warranty as per manufacturer policy.\n2. Goods once sold cannot be taken back after installation.\n3. Payment due upon completion of work."
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

# --- Technician Models ---
class Technician(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str
    role: str = "Senior Electrician"  # Senior Electrician, Wireman, AC Electrician, Battery Specialist, Trainee
    commission_pct: float = 0.0
    status: str = "Active"  # Active, Inactive
    notes: Optional[str] = None
    total_jobs: int = 0
    created_at: Optional[str] = None

# --- Customer & Vehicle Models ---
class Customer(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str
    address: Optional[str] = None
    gstin: Optional[str] = None
    whatsapp_opt_in: bool = True
    total_visits: int = 0
    khata_balance: float = 0.0  # Pending unpaid dues
    created_at: Optional[str] = None

class Vehicle(BaseModel):
    id: Optional[str] = None
    reg_number: str  # e.g., KL-07-CD-1234
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    make_model: str  # e.g., Maruti Swift, Tata Ace, Hyundai Creta, Ashok Leyland
    vehicle_type: str = "Car"  # Car, Auto, Van, Mini-Truck, Bus/Heavy, Two-Wheeler
    fuel_type: str = "Diesel"  # Diesel, Petrol, CNG, EV
    odometer: Optional[int] = 0
    chassis_no: Optional[str] = None
    created_at: Optional[str] = None

# --- Inventory & Barcode Models ---
class InventoryItem(BaseModel):
    id: Optional[str] = None
    part_name: str
    sku: Optional[str] = None
    barcode: str  # EAN / Code-128 barcode number on the box
    category: str = "Relays & Fuses"  # Relays & Fuses, Starters & Alternators, Wiring & Sleeves, Batteries, Bulbs & LEDs, Sensors & OBD, Switches & Horns, Accessories
    stock_qty: int = 0
    min_stock_alert: int = 5
    cost_price: float = 0.0
    selling_price: float = 0.0
    tax_rate: float = 18.0  # 0%, 5%, 12%, 18%, 28%
    hsn_code: Optional[str] = "8536"  # Common Electrical HSN
    unit: str = "pcs"  # pcs, mtr, set, pkt
    warranty_months: int = 0
    supplier_name: Optional[str] = None
    location_rack: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class StockLog(BaseModel):
    id: Optional[str] = None
    item_id: str
    part_name: Optional[str] = None
    barcode: Optional[str] = None
    change_qty: int
    new_stock_qty: int
    action_type: str  # PURCHASE, JOB_USE, COUNTER_SALE, RETURN, ADJUSTMENT
    unit_cost: float = 0.0
    reference_id: Optional[str] = None  # Invoice # or Job #
    notes: Optional[str] = None
    created_at: Optional[str] = None

# --- Bank & Expense Models ---
class BankAccount(BaseModel):
    id: Optional[str] = None
    account_name: str  # e.g., "SBI Current A/c", "Main Cash Register", "GPay Business"
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    upi_vpa: Optional[str] = None
    account_type: str = "BANK"  # BANK, CASH, UPI_WALLET
    current_balance: float = 0.0
    is_primary: bool = False
    created_at: Optional[str] = None

class Expense(BaseModel):
    id: Optional[str] = None
    title: str
    category: str = "Workshop Rent"  # Workshop Rent, Electricity Bill, Staff Wages, Consumables & Tools, Tea & Refreshments, Spare Purchases, General Maintenance
    amount: float
    payment_mode: str = "CASH"  # CASH, UPI, BANK_TRANSFER
    bank_account_id: Optional[str] = None
    expense_date: str
    paid_to: Optional[str] = None
    reference_no: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

# --- Job Card / Service Book Models ---
class JobItem(BaseModel):
    id: Optional[str] = None
    job_card_id: Optional[str] = None
    item_type: str = "LABOR"  # LABOR or PART
    item_id: Optional[str] = None  # Link to InventoryItem if PART
    barcode: Optional[str] = None
    name: str  # "Starter Overhaul Labor" or "Lucas Relay 4-Pin"
    hsn_code: Optional[str] = None
    quantity: int = 1
    unit_price: float = 0.0
    tax_rate: float = 0.0
    total_price: float = 0.0
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None

class JobCard(BaseModel):
    id: Optional[str] = None
    job_number: str  # e.g. "JOB-2026-001"
    customer_id: Optional[str] = None
    customer_name: str
    customer_phone: str
    vehicle_id: Optional[str] = None
    vehicle_reg_no: str
    vehicle_make_model: str
    odometer: Optional[int] = 0
    assigned_technician_id: Optional[str] = None
    assigned_technician_name: Optional[str] = None
    
    status: str = "RECEIVED"  # RECEIVED, INSPECTION, IN_PROGRESS, WAITING_PARTS, COMPLETED, DELIVERED, CANCELLED
    
    complaints: List[str] = []  # e.g., ["Battery light ON", "Starting trouble / Clicking sound", "AC blower not working"]
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

# --- Invoice / Billing Models ---
class InvoiceItem(BaseModel):
    id: Optional[str] = None
    invoice_id: Optional[str] = None
    item_type: str = "PART"  # PART or LABOR
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
    invoice_number: str  # e.g. "INV-2026-001"
    invoice_date: str
    invoice_type: str = "JOB_SERVICE"  # JOB_SERVICE or COUNTER_SALE
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
    payment_status: str = "PAID"  # PAID, PARTIAL, UNPAID
    payment_mode: str = "UPI"  # CASH, UPI, BANK_TRANSFER, CARD, KHATA_CREDIT
    bank_account_id: Optional[str] = None
    upi_ref_no: Optional[str] = None
    
    upi_payment_link: Optional[str] = None
    whatsapp_sent: bool = False
    notes: Optional[str] = None
    created_at: Optional[str] = None

# --- Barcode Scan Request ---
class BarcodeScanRequest(BaseModel):
    barcode: str
    quantity: int = 1
