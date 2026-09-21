import sqlite3
import pandas as pd
import io
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from database import get_db_connection

def generate_gstr1_report(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate GSTR-1 Sales & Tax Audit Report for Chartered Accountant
    Includes B2B, B2C, Taxable Values, CGST, SGST, and HSN Summary
    """
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
    
    # Calculate totals
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

def generate_profit_and_loss_report(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate P&L Financial Statement:
    Revenue (Labor + Spares) - COGS (Parts Cost) - Operating Expenses = Net Profit
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Revenue & Cost of Goods Sold
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
    
    # Calculate COGS (Cost of parts used/sold)
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
    
    # 2. Operating Expenses
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
        "discounts": rev_data["total_discounts"],
        "cogs": total_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": gross_margin_pct,
        "expense_breakdown": expense_breakdown,
        "total_operating_expenses": total_operating_expenses,
        "net_profit": net_profit,
        "net_margin_pct": net_margin_pct,
    }

def generate_inventory_valuation_report() -> Dict[str, Any]:
    """Generate Stock Valuation Report for Balance Sheet / Audit"""
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
    
    total_items_count = len(items)
    total_stock_units = sum(i["stock_qty"] for i in items)
    total_inventory_cost_value = sum(i["total_cost_value"] for i in items)
    total_inventory_retail_value = sum(i["total_retail_value"] for i in items)
    low_stock_count = sum(1 for i in items if i["stock_qty"] <= i["min_stock_alert"])
    
    return {
        "total_items_count": total_items_count,
        "total_stock_units": total_stock_units,
        "total_cost_value": total_inventory_cost_value,
        "total_retail_value": total_inventory_retail_value,
        "potential_profit": total_inventory_retail_value - total_inventory_cost_value,
        "low_stock_count": low_stock_count,
        "items": items
    }

def generate_daybook_report(report_date: Optional[str] = None) -> Dict[str, Any]:
    """Generate Daily Cash & Bank Receipts and Payments Daybook"""
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Receipts (Invoices)
    cursor.execute("""
    SELECT 
        invoice_number as doc_no, 'INVOICE' as doc_type, customer_name as party_name,
        payment_mode, amount_paid as amount, created_at, notes
    FROM invoices
    WHERE date(invoice_date) = date(?) AND amount_paid > 0
    ORDER BY created_at ASC
    """, (report_date,))
    receipts = [dict(row) for row in cursor.fetchall()]
    
    # Payments (Expenses)
    cursor.execute("""
    SELECT 
        reference_no as doc_no, 'EXPENSE' as doc_type, title as party_name,
        category, payment_mode, amount, created_at, notes
    FROM expenses
    WHERE date(expense_date) = date(?)
    ORDER BY created_at ASC
    """, (report_date,))
    payments = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    total_receipts = sum(r["amount"] for r in receipts)
    total_payments = sum(p["amount"] for p in payments)
    net_daily_flow = total_receipts - total_payments
    
    return {
        "report_date": report_date,
        "receipts": receipts,
        "payments": payments,
        "total_receipts": total_receipts,
        "total_payments": total_payments,
        "net_daily_flow": net_daily_flow,
    }

def export_gstr1_excel(start_date: Optional[str] = None, end_date: Optional[str] = None) -> bytes:
    """Export GSTR-1 Tax Audit Report to Excel (.xlsx) file for Chartered Accountant submission"""
    report = generate_gstr1_report(start_date, end_date)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Invoices Sheet
        df_invoices = pd.DataFrame(report["invoices"])
        if not df_invoices.empty:
            df_invoices.to_excel(writer, sheet_name='GSTR1_Sales_Invoices', index=False)
            
        # HSN Summary Sheet
        df_hsn = pd.DataFrame(report["hsn_summary"])
        if not df_hsn.empty:
            df_hsn.to_excel(writer, sheet_name='HSN_Summary', index=False)
            
    output.seek(0)
    return output.getvalue()
