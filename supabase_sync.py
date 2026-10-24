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

def sync_critical_from_supabase():
    """Pull tenants, users, workshop profiles, subscriptions from Supabase into SQLite"""
    tables = [
        ("tenants", "id"),
        ("workshop_profile", "id"),
        ("users", "id"),
        ("subscriptions", "id"),
        ("saas_vendor_invoices", "id")
    ]
    synced = {}
    for tbl, pkey in tables:
        synced[tbl] = sync_from_supabase_table(tbl, pkey)
    return synced

def fetch_and_cache_tenant_from_supabase(client_code: str) -> Optional[Dict[str, Any]]:
    """Query Supabase directly for a client_code if missing from local SQLite cache"""
    sp = get_supabase()
    if not sp or not client_code:
        return None
    try:
        clean_code = client_code.strip().upper()
        res = sp.table("tenants").select("*").or_(f"client_code.ilike.{clean_code},id.eq.{clean_code}").execute()
        rows = res.data or []
        if rows:
            tenant_row = rows[0]
            # Pull this tenant's profile and users into SQLite
            tid = tenant_row.get("id")
            sync_critical_from_supabase()
            return tenant_row
    except Exception as e:
        print(f"[Supabase Query Error] Tenant lookup {client_code}: {e}")
    return None
