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

def generate_gstr1_report(start_date: Optional[str] = None, end_date: Optional[str] = None, fy: Optional[str] = None) -> Dict[str, Any]:
    """Generate GSTR-1 Sales & Tax Audit Report with FY support"""
    if fy and not start_date and not end_date:
        fy_dates = get_financial_year_dates(fy)
        start_date, end_date = fy_dates["start_date"], fy_dates["end_date"]

    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
    SELECT 
        i.invoice_number, i.invoice_date, i.customer_name, i.customer_phone,
        i.customer_gstin, i.vehicle_reg_no, i.subtotal_labor, i.subtotal_parts,
        i.taxable_subtotal, i.cgst_total, i.sgst_total, i.tax_total,
        i.discount_amount, i.grand_total, i.amount_paid, i.balance_due,
        i.payment_status, i.payment_mode
    FROM invoices i
    WHERE 1=1
    """
    params = []
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
    total_tax = sum(inv["tax_total"] for inv in invoices)
    total_labor = sum(inv["subtotal_labor"] for inv in invoices)
    total_parts = sum(inv["subtotal_parts"] for inv in invoices)
    
    # HSN Summary
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
    WHERE 1=1
    """
    hsn_params = []
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
        "total_tax": total_tax,
        "total_labor": total_labor,
        "total_parts": total_parts,
        "invoices": invoices,
        "hsn_summary": hsn_summary,
    }

def generate_profit_and_loss_report(start_date: Optional[str] = None, end_date: Optional[str] = None, fy: Optional[str] = None) -> Dict[str, Any]:
    """Generate P&L Financial Statement with FY support"""
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
        COALESCE(SUM(grand_total), 0) as total_revenue,
        COALESCE(SUM(discount_amount), 0) as total_discounts
    FROM invoices
    WHERE 1=1
    """
    params = []
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
    WHERE ii.item_type = 'PART'
    """
    cogs_params = []
    if start_date:
        cogs_query += " AND date(i.invoice_date) >= date(?)"
        cogs_params.append(start_date)
    if end_date:
        cogs_query += " AND date(i.invoice_date) <= date(?)"
        cogs_params.append(end_date)
        
    cursor.execute(cogs_query, cogs_params)
    cogs_data = cursor.fetchone()
    total_cogs = cogs_data[0] if cogs_data else 0.0
    
    exp_query = """
    SELECT 
        category,
        COALESCE(SUM(amount), 0) as category_total
    FROM expenses
    WHERE 1=1
    """
    exp_params = []
    if start_date:
        exp_query += " AND date(expense_date) >= date(?)"
        exp_params.append(start_date)
    if end_date:
        exp_query += " AND date(expense_date) <= date(?)"
        exp_params.append(end_date)
        
    exp_query += " GROUP BY category ORDER BY category_total DESC"
    cursor.execute(exp_query, exp_params)
    expense_breakdown = [dict(row) for row in cursor.fetchall()]
    total_operating_expenses = sum(item["category_total"] for item in expense_breakdown)
    
    conn.close()
    
    gross_revenue = rev_data["total_revenue"]
    gross_profit = gross_revenue - total_cogs
    gross_margin_pct = (gross_profit / gross_revenue * 100) if gross_revenue > 0 else 0.0
    net_profit = gross_profit - total_operating_expenses
    net_margin_pct = (net_profit / gross_revenue * 100) if gross_revenue > 0 else 0.0
    
    return {
        "start_date": start_date or "All Time",
        "end_date": end_date or datetime.now().strftime("%Y-%m-%d"),
        "labor_revenue": rev_data["labor_revenue"],
        "parts_revenue": rev_data["parts_revenue"],
        "total_revenue": gross_revenue,
        "sales_revenue": gross_revenue,
        "discounts": rev_data["total_discounts"],
        "cogs": total_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "expense_breakdown": expense_breakdown,
        "total_operating_expenses": total_operating_expenses,
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
    }

def generate_daily_collection_register(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """Detailed Daily Collection Register breakdown by Cash, UPI, Bank, and Card"""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
    SELECT 
        date(invoice_date) as day,
        COALESCE(SUM(CASE WHEN payment_mode = 'CASH' THEN amount_paid ELSE 0 END), 0) as cash_total,
        COALESCE(SUM(CASE WHEN payment_mode = 'UPI' THEN amount_paid ELSE 0 END), 0) as upi_total,
        COALESCE(SUM(CASE WHEN payment_mode = 'BANK_TRANSFER' THEN amount_paid ELSE 0 END), 0) as bank_total,
        COALESCE(SUM(CASE WHEN payment_mode = 'CARD' THEN amount_paid ELSE 0 END), 0) as card_total,
        COALESCE(SUM(amount_paid), 0) as day_total,
        COUNT(*) as bill_count
    FROM invoices
    WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND date(invoice_date) >= date(?)"
        params.append(start_date)
    if end_date:
        query += " AND date(invoice_date) <= date(?)"
        params.append(end_date)
    query += " GROUP BY date(invoice_date) ORDER BY date(invoice_date) DESC"
    cursor.execute(query, params)
    registers = [dict(row) for row in cursor.fetchall()]

    # Detailed collection transactions list
    dt_query = """
    SELECT invoice_number, invoice_date, customer_name, customer_phone, vehicle_reg_no, amount_paid, payment_mode, payment_status, grand_total, balance_due
    FROM invoices
    WHERE amount_paid > 0
    """
    dt_params = []
    if start_date:
        dt_query += " AND date(invoice_date) >= date(?)"
        dt_params.append(start_date)
    if end_date:
        dt_query += " AND date(invoice_date) <= date(?)"
        dt_params.append(end_date)
    dt_query += " ORDER BY date(invoice_date) DESC, invoice_number DESC"
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

def generate_inventory_valuation_report() -> Dict[str, Any]:
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
    ORDER BY category, part_name
    """)
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

def export_gstr1_excel(start_date: Optional[str] = None, end_date: Optional[str] = None, fy: Optional[str] = None) -> bytes:
    """Export GSTR-1 Sales Report to Excel (.xlsx) for CA"""
    report = generate_gstr1_report(start_date, end_date, fy)
    
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
