import os
import hashlib
import hmac
import secrets
import time
from typing import Optional, Dict, Any

SECRET_KEY = os.getenv("JWT_SECRET", "autovolt-pro-super-secret-key-2026-saas-enterprise")

def hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt"""
    salt = secrets.token_hex(8)
    pw_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}:{pw_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:hash format"""
    if not stored_hash or ":" not in stored_hash:
        # Fallback for plain text during initial migration
        return password == stored_hash
    try:
        salt, pw_hash = stored_hash.split(":", 1)
        test_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return hmac.compare_digest(pw_hash, test_hash)
    except Exception:
        return False

def verify_master_pin(entered_pin: str, actual_pin: str = "1234") -> bool:
    """Verify owner master security PIN for sensitive actions (delete/edit bills)"""
    if not entered_pin:
        return False
    return str(entered_pin).strip() == str(actual_pin).strip()

def generate_reset_token() -> str:
    """Generate secure password reset token"""
    return secrets.token_urlsafe(32)
