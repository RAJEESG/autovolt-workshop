import sqlite3
import pandas as pd
import io
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from database import get_db_connection

def get_financial_year_dates(fy_str: Optional[str] = None) -> Dict[str, str]:
    """Return {start_date, end_date, financial_year} for Indian Financial Year (Apr 1 to Mar 31)"""
    today = date.today()
    if not fy_str or fy_str == "current":
        curr_year = today.year if today.month >= 4 else today.year - 1
    elif fy_str == "prev":
        curr_year = (today.year if today.month >= 4 else today.year - 1) - 1
    elif "-" in str(fy_str):
        try:
            curr_year = int(fy_str.split("-")[0].strip())
        except Exception:
            curr_year = today.year if today.month >= 4 else today.year - 1
    else:
        try:
            curr_year = int(str(fy_str).strip())
        except Exception:
            curr_year = today.year if today.month >= 4 else today.year - 1

    start_date = f"{curr_year}-04-01"
    end_date = f"{curr_year + 1}-03-31"
    fy_label = f"{curr_year}-{curr_year + 1}"
    return {
        "start_date": start_date,
        "end_date": end_date,
        "financial_year": fy_label
    }

def generate_gstr1_report(start_date: Optional[str] = None, end_date: Optional[str] = None, fy: Optional[str] = None, tenant_id: str = "tenant_1") -> Dict[str, Any]:
    """Generate GSTR-1 Sales & Tax Audit Report with FY support (excluding cancelled bills)"""
    if fy and not start_date and not end_date:
        fy_dates = get_financial_year_dates(fy)
        start_date, end_date = fy_dates["start_date"], fy_dates["end_date"]

    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT 
        i.invoice_number, i.invoice_date, i.customer_name, i.customer_phone,
        i.customer_gstin, i.vehicle_reg_no, i.subtotal_labor, i.subtotal_parts,
        i.taxable_subtotal, i.cgst_total, i.sgst_total, i.igst_total, i.tax_total,
        i.discount_amount, i.grand_total, i.amount_paid, i.balance_due,
        i.payment_status, i.payment_mode
    FROM invoices i
    WHERE (i.payment_status != 'CANCELLED' AND i.status != 'CANCELLED') AND i.tenant_id = ?
    """
    params = [tenant_id]
    if start_date:
        query += " AND date(i.invoice_date) >= date(?)"
        params.append(start_date)
    if end_date:
        query += " AND date(i.invoice_date) <= date(?)"
        params.append(end_date)
        
    query += " ORDER BY date(i.invoice_date) DESC, i.invoice_number DESC"
    cursor.execute(query, params)
    invoices = [dict(row) for row in cursor.fetchall()]
    
    total_sales = sum(inv["grand_total"] for inv in invoices)
    total_taxable = sum(inv["taxable_subtotal"] for inv in invoices)
    total_cgst = sum(inv["cgst_total"] for inv in invoices)
    total_sgst = sum(inv["sgst_total"] for inv in invoices)
    total_igst = sum(inv.get("igst_total", 0.0) or 0.0 for inv in invoices)
    total_tax = sum(inv["tax_total"] for inv in invoices)
    total_labor = sum(inv["subtotal_labor"] for inv in invoices)
    total_parts = sum(inv["subtotal_parts"] for inv in invoices)
    
    # HSN Summary (excluding cancelled bills)
    hsn_query = """
    SELECT 
        ii.hsn_sac,
        SUM(ii.quantity) as total_qty,
        SUM(ii.taxable_amount) as total_taxable,
        SUM(ii.cgst_amount) as total_cgst,
        SUM(ii.sgst_amount) as total_sgst,
        SUM(ii.total_price) as total_val
    FROM invoice_items ii
    JOIN invoices i ON ii.invoice_id = i.id
    WHERE (i.payment_status != 'CANCELLED' AND i.status != 'CANCELLED') AND i.tenant_id = ?
    """
    hsn_params = [tenant_id]
    if start_date:
        hsn_query += " AND date(i.invoice_date) >= date(?)"
        hsn_params.append(start_date)
    if end_date:
        hsn_query += " AND date(i.invoice_date) <= date(?)"
        hsn_params.append(end_date)
    hsn_query += " GROUP BY ii.hsn_sac"
    cursor.execute(hsn_query, hsn_params)
    hsn_summary = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "start_date": start_date or "All Time",
        "end_date": end_date or datetime.now().strftime("%Y-%m-%d"),
        "total_invoices": len(invoices),
        "total_sales": total_sales,
        "total_taxable": total_taxable,
        "total_cgst": total_cgst,
        "total_sgst": total_sgst,
        "total_igst": total_igst,
        "total_tax": total_tax,
        "total_labor": total_labor,
        "total_parts": total_parts,
        "invoices": invoices,
        "hsn_summary": hsn_summary,
    }

def generate_profit_and_loss_report(start_date: Optional[str] = None, end_date: Optional[str] = None, fy: Optional[str] = None, tenant_id: str = "tenant_1") -> Dict[str, Any]:
    """Generate P&L Financial Statement with FY support, correct Taxable Revenue separation, and Wages"""
    if fy and not start_date and not end_date:
        fy_dates = get_financial_year_dates(fy)
        start_date, end_date = fy_dates["start_date"], fy_dates["end_date"]

    conn = get_db_connection()
    cursor = conn.cursor()
    
    inv_query = """
    SELECT 
        COUNT(*) as count,
        COALESCE(SUM(subtotal_labor), 0) as labor_revenue,
        COALESCE(SUM(subtotal_parts), 0) as parts_revenue,
        COALESCE(SUM(taxable_subtotal), 0) as taxable_revenue,
        COALESCE(SUM(grand_total), 0) as total_gross_billed,
        COALESCE(SUM(tax_total), 0) as total_tax_collected,
        COALESCE(SUM(discount_amount), 0) as total_discounts
    FROM invoices
    WHERE (payment_status != 'CANCELLED' AND status != 'CANCELLED') AND tenant_id = ?
    """
    params = [tenant_id]
    if start_date:
        inv_query += " AND date(invoice_date) >= date(?)"
        params.append(start_date)
    if end_date:
        inv_query += " AND date(invoice_date) <= date(?)"
        params.append(end_date)
        
    cursor.execute(inv_query, params)
    rev_data = dict(cursor.fetchone())
    
    cogs_query = """
    SELECT 
        COALESCE(SUM(ii.quantity * COALESCE(inv.cost_price, 0)), 0) as total_cogs
    FROM invoice_items ii
    JOIN invoices i ON ii.invoice_id = i.id
    LEFT JOIN inventory_items inv ON ii.item_id = inv.id
    WHERE ii.item_type = 'PART' AND (i.payment_status != 'CANCELLED' AND i.status != 'CANCELLED') AND i.tenant_id = ?
    """
    cogs_params = [tenant_id]
    if start_date:
        cogs_query += " AND date(i.invoice_date) >= date(?)"
        cogs_params.append(start_date)
    if end_date:
        cogs_query += " AND date(i.invoice_date) <= date(?)"
        cogs_params.append(end_date)
        
    cursor.execute(cogs_query, cogs_params)
    cogs_data = cursor.fetchone()
    total_cogs = cogs_data[0] if cogs_data else 0.0
    
    # 1. Operating Expenses Breakdown
    exp_query = """
    SELECT 
        category,
        COALESCE(SUM(amount), 0) as category_total
    FROM expenses
    WHERE tenant_id = ?
    """
    exp_params = [tenant_id]
    if start_date:
        exp_query += " AND date(expense_date) >= date(?)"
        exp_params.append(start_date)
    if end_date:
        exp_query += " AND date(expense_date) <= date(?)"
        exp_params.append(end_date)
        
    exp_query += " GROUP BY category ORDER BY category_total DESC"
    cursor.execute(exp_query, exp_params)
    expense_breakdown = [dict(row) for row in cursor.fetchall()]

    # 2. Add Employee Wages to Expenses if not already captured in expenses table
    wage_query = """
    SELECT COALESCE(SUM(net_paid), 0) as total_wages
    FROM employee_wages
    WHERE tenant_id = ?
    """
    wage_params = [tenant_id]
    if start_date:
        wage_query += " AND date(payment_date) >= date(?)"
        wage_params.append(start_date)
    if end_date:
        wage_query += " AND date(payment_date) <= date(?)"
        wage_params.append(end_date)
    cursor.execute(wage_query, wage_params)
    wages_row = cursor.fetchone()
    total_wages = wages_row[0] if wages_row else 0.0

    # Check if Staff Wages is already in expense breakdown
    wages_in_expenses = any("wage" in item["category"].lower() or "salary" in item["category"].lower() for item in expense_breakdown)
    if total_wages > 0 and not wages_in_expenses:
        expense_breakdown.append({"category": "Technician & Staff Wages", "category_total": total_wages})

    total_operating_expenses = sum(item["category_total"] for item in expense_breakdown)
    
    conn.close()
    
    # In accounting, revenue = Taxable Net Turnover (excluding GST collected which is a liability)
    taxable_revenue = rev_data["taxable_revenue"] if rev_data["taxable_revenue"] > 0 else (rev_data["total_gross_billed"] - rev_data["total_tax_collected"])
    gross_revenue = taxable_revenue
    gross_profit = gross_revenue - total_cogs
    gross_margin_pct = (gross_profit / gross_revenue * 100) if gross_revenue > 0 else 0.0
    net_profit = gross_profit - total_operating_expenses
    net_margin_pct = (net_profit / gross_revenue * 100) if gross_revenue > 0 else 0.0
    
    return {
        "start_date": start_date or "All Time",
        "end_date": end_date or datetime.now().strftime("%Y-%m-%d"),
        "labor_revenue": rev_data["labor_revenue"],
        "parts_revenue": rev_data["parts_revenue"],
        "taxable_revenue": taxable_revenue,
        "total_revenue": gross_revenue,
        "sales_revenue": gross_revenue,
        "total_gross_billed": rev_data["total_gross_billed"],
        "tax_collected": rev_data["total_tax_collected"],
        "discounts": rev_data["total_discounts"],
        "cogs": total_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "expense_breakdown": expense_breakdown,
        "total_operating_expenses": total_operating_expenses,
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
    }

def generate_daily_collection_register(start_date: Optional[str] = None, end_date: Optional[str] = None, tenant_id: str = "tenant_1") -> Dict[str, Any]:
    """Detailed Daily Collection Register breakdown by Cash, UPI, Bank, and Card from payments table"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query payments table as primary source of actual collections
    query = """
    SELECT 
        date(p.payment_date) as day,
        COALESCE(SUM(CASE WHEN p.payment_mode = 'CASH' THEN p.amount ELSE 0 END), 0) as cash_total,
        COALESCE(SUM(CASE WHEN p.payment_mode = 'UPI' THEN p.amount ELSE 0 END), 0) as upi_total,
        COALESCE(SUM(CASE WHEN p.payment_mode = 'BANK_TRANSFER' THEN p.amount ELSE 0 END), 0) as bank_total,
        COALESCE(SUM(CASE WHEN p.payment_mode = 'CARD' THEN p.amount ELSE 0 END), 0) as card_total,
        COALESCE(SUM(p.amount), 0) as day_total,
        COUNT(DISTINCT p.id) as bill_count
    FROM payments p
    WHERE p.tenant_id = ?
    """
    params = [tenant_id]
    if start_date:
        query += " AND date(p.payment_date) >= date(?)"
        params.append(start_date)
    if end_date:
        query += " AND date(p.payment_date) <= date(?)"
        params.append(end_date)
    query += " GROUP BY date(p.payment_date) ORDER BY date(p.payment_date) DESC"
    cursor.execute(query, params)
    registers = [dict(row) for row in cursor.fetchall()]

    # Detailed collection transactions list
    dt_query = """
    SELECT 
        p.id as payment_id,
        COALESCE(i.invoice_number, 'Direct Payment') as invoice_number,
        p.payment_date as invoice_date,
        COALESCE(i.customer_name, 'Direct Customer') as customer_name,
        COALESCE(i.customer_phone, '-') as customer_phone,
        COALESCE(i.vehicle_reg_no, '-') as vehicle_reg_no,
        p.amount as amount_paid,
        p.payment_mode,
        COALESCE(i.payment_status, 'PAID') as payment_status,
        COALESCE(i.grand_total, p.amount) as grand_total,
        COALESCE(i.balance_due, 0.0) as balance_due,
        p.notes
    FROM payments p
    LEFT JOIN invoices i ON p.invoice_id = i.id
    WHERE p.amount > 0 AND p.tenant_id = ?
    """
    dt_params = [tenant_id]
    if start_date:
        dt_query += " AND date(p.payment_date) >= date(?)"
        dt_params.append(start_date)
    if end_date:
        dt_query += " AND date(p.payment_date) <= date(?)"
        dt_params.append(end_date)
    dt_query += " ORDER BY date(p.payment_date) DESC, p.created_at DESC"
    cursor.execute(dt_query, dt_params)
    transactions = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "registers": registers,
        "transactions": transactions,
        "grand_total_collected": sum(r["day_total"] for r in registers),
        "total_cash": sum(r["cash_total"] for r in registers),
        "total_upi": sum(r["upi_total"] for r in registers),
        "total_bank": sum(r["bank_total"] for r in registers),
        "total_card": sum(r["card_total"] for r in registers)
    }

def generate_inventory_valuation_report(tenant_id: str = "tenant_1") -> Dict[str, Any]:
    """Stock Valuation Report for Balance Sheet"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT 
        id, part_name, sku, barcode, category, stock_qty, min_stock_alert,
        cost_price, selling_price, tax_rate, hsn_code, unit,
        (stock_qty * cost_price) as total_cost_value,
        (stock_qty * selling_price) as total_retail_value
    FROM inventory_items
    WHERE tenant_id = ?
    ORDER BY category, part_name
    """, (tenant_id,))
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return {
        "total_items_count": len(items),
        "total_sku_count": len(items),
        "total_stock_units": sum(i["stock_qty"] for i in items),
        "total_cost_value": sum(i["total_cost_value"] for i in items),
        "total_retail_value": sum(i["total_retail_value"] for i in items),
        "potential_profit": sum(i["total_retail_value"] for i in items) - sum(i["total_cost_value"] for i in items),
        "low_stock_count": sum(1 for i in items if i["stock_qty"] <= i["min_stock_alert"]),
        "items": items
    }

def export_gstr1_excel(start_date: Optional[str] = None, end_date: Optional[str] = None, fy: Optional[str] = None, tenant_id: str = "tenant_1") -> bytes:
    """Export GSTR-1 Sales Report to Excel (.xlsx) for CA"""
    report = generate_gstr1_report(start_date, end_date, fy, tenant_id=tenant_id)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_invoices = pd.DataFrame(report["invoices"])
        if not df_invoices.empty:
            df_invoices.to_excel(writer, sheet_name='GSTR1_Sales', index=False)
            
        df_hsn = pd.DataFrame(report["hsn_summary"])
        if not df_hsn.empty:
            df_hsn.to_excel(writer, sheet_name='HSN_Summary', index=False)
            
    output.seek(0)
    return output.getvalue()
