"""
AutoVolt Pro - Supabase Real-Time Cloud Sync Engine
Synchronizes SQLite local cache with Supabase PostgreSQL Cloud Database.
Ensures zero data loss across Render containers, multi-instance deployments, and local machines.
"""
import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List
import database as db

def get_supabase():
    """Get active Supabase client instance"""
    return db.supabase_client

def push_to_supabase(table_name: str, record: Dict[str, Any]) -> bool:
    """Safely upsert a record into Supabase PostgreSQL Cloud Table"""
    sp = get_supabase()
    if not sp:
        return False
    try:
        clean_record = {}
        for k, v in record.items():
            if isinstance(v, (datetime,)):
                clean_record[k] = v.isoformat()
            else:
                clean_record[k] = v
        sp.table(table_name).upsert(clean_record).execute()
        return True
    except Exception as e:
        print(f"[Supabase Sync Error] Failed to push to {table_name}: {e}")
        return False

def sync_from_supabase_table(table_name: str, pkey: str = "id") -> int:
    """Pull records from Supabase table into local SQLite database"""
    sp = get_supabase()
    if not sp:
        return 0
    try:
        res = sp.table(table_name).select("*").execute()
        rows = res.data or []
        if not rows:
            return 0

        conn = db.get_db_connection()
        cursor = conn.cursor()
        count = 0

        # Get existing columns in SQLite table
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {col[1] for col in cursor.fetchall()}
        if not existing_cols:
            conn.close()
            return 0

        for row in rows:
            # Filter keys to only those present in SQLite schema
            valid_items = {k: v for k, v in row.items() if k in existing_cols}
            if not valid_items:
                continue

            # Convert dicts/lists to JSON strings for SQLite
            for k, v in valid_items.items():
                if isinstance(v, (dict, list)):
                    valid_items[k] = json.dumps(v)

            cols = list(valid_items.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            vals = [valid_items[c] for c in cols]

            cursor.execute(f"""
            INSERT OR REPLACE INTO {table_name} ({col_names})
            VALUES ({placeholders})
            """, vals)
            count += 1

        conn.commit()
        conn.close()
        return count
    except Exception as e:
        print(f"[Supabase Sync Error] Failed to pull from {table_name}: {e}")
        return 0

def sync_critical_from_supabase() -> Dict[str, int]:
    """Pull tenants, users, workshop profiles, subscriptions, bank accounts from Supabase into SQLite"""
    tables = [
        ("tenants", "id"),
        ("workshop_profile", "id"),
        ("users", "id"),
        ("subscriptions", "id"),
        ("saas_vendor_invoices", "id"),
        ("bank_accounts", "id"),
        ("suppliers", "id")
    ]
    synced = {}
    for tbl, pkey in tables:
        synced[tbl] = sync_from_supabase_table(tbl, pkey)
    return synced

def fetch_and_cache_tenant_from_supabase(client_code_or_id: str) -> Optional[Dict[str, Any]]:
    """
    Query Supabase directly for a client_code or tenant_id.
    Handles case-insensitivity seamlessly (e.g. 'tenant_a1b2' or 'TENANT_A1B2' or 'SPARK').
    Caches the tenant, profile, and users into local SQLite cache.
    """
    sp = get_supabase()
    if not sp or not client_code_or_id:
        return None

    clean = client_code_or_id.strip()
    clean_upper = clean.upper()
    clean_lower = clean.lower()

    try:
        # 1. Search tenants table by client_code, id (lowercase & uppercase), or workshop name
        filter_str = f"client_code.ilike.{clean_upper},id.ilike.{clean},id.ilike.{clean_lower},name.ilike.{clean}"
        res = sp.table("tenants").select("*").or_(filter_str).execute()
        rows = res.data or []

        # 2. Fallback: Search workshop_profile table
        if not rows:
            res_p = sp.table("workshop_profile").select("*").or_(
                f"client_code.ilike.{clean_upper},tenant_id.ilike.{clean},tenant_id.ilike.{clean_lower},id.ilike.{clean}"
            ).execute()
            rows_p = res_p.data or []
            if rows_p:
                p_row = rows_p[0]
                tid = p_row.get("tenant_id") or p_row.get("id")
                res = sp.table("tenants").select("*").eq("id", tid).execute()
                rows = res.data or []
                if not rows:
                    # Construct minimal tenant row from profile
                    rows = [{
                        "id": tid,
                        "client_code": p_row.get("client_code") or clean_upper,
                        "name": p_row.get("name", "AutoVolt Workshop"),
                        "owner_name": p_row.get("owner_name", ""),
                        "phone": p_row.get("phone", ""),
                        "whatsapp_mobile": p_row.get("phone", ""),
                        "address": p_row.get("address", ""),
                        "status": "ACTIVE"
                    }]

        if rows:
            tenant_row = rows[0]
            tid = tenant_row.get("id")

            # Write this tenant row directly into local SQLite
            conn = db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tenants)")
            existing_cols = {col[1] for col in cursor.fetchall()}

            valid_items = {k: v for k, v in tenant_row.items() if k in existing_cols}
            cols = list(valid_items.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            vals = [valid_items[c] for c in cols]

            cursor.execute(f"INSERT OR REPLACE INTO tenants ({col_names}) VALUES ({placeholders})", vals)
            conn.commit()
            conn.close()

            # Now sync profile, users, subscriptions from cloud
            sync_critical_from_supabase()
            return tenant_row

    except Exception as e:
        print(f"[Supabase Query Error] Tenant lookup {client_code_or_id}: {e}")

    return None
