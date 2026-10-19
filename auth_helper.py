import os
import hashlib
import hmac
import secrets
import time
from typing import Optional, Dict, Any

SECRET_KEY = os.getenv("JWT_SECRET", "autovolt-pro-super-secret-key-2026-saas-enterprise")

def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations and salt"""
    salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"pbkdf2:100000:{salt}:{pw_hash}"

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password supporting PBKDF2, legacy salted SHA-256, and plain text"""
    if not stored_hash:
        return False
    try:
        # 1. PBKDF2 format: pbkdf2:iterations:salt:hash
        if stored_hash.startswith("pbkdf2:"):
            parts = stored_hash.split(":")
            if len(parts) == 4:
                _, iterations_str, salt, target_hash = parts
                iterations = int(iterations_str)
                test_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
                return hmac.compare_digest(target_hash, test_hash)

        # 2. Legacy salted SHA-256: salt:hash
        if ":" in stored_hash:
            salt, pw_hash = stored_hash.split(":", 1)
            test_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
            return hmac.compare_digest(pw_hash, test_hash)

        # 3. Fallback for plain text during initial migration
        return password == stored_hash
    except Exception:
        return False

def verify_master_pin(entered_pin: str, actual_pin: str = "1234") -> bool:
    """Verify owner master security PIN for sensitive actions (delete/edit bills)"""
    if not entered_pin:
        return False
    return hmac.compare_digest(str(entered_pin).strip(), str(actual_pin).strip())

def generate_reset_token() -> str:
    """Generate secure password reset token"""
    return secrets.token_urlsafe(32)

def create_signed_session_cookie(username: str, expires_in: int = 86400 * 7) -> str:
    """Create a tamper-proof cryptographically signed session cookie"""
    expiry_ts = int(time.time()) + expires_in
    data_to_sign = f"{username}:{expiry_ts}"
    signature = hmac.new(SECRET_KEY.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{username}:{expiry_ts}:{signature}"

def verify_signed_session_cookie(cookie_val: Optional[str]) -> Optional[str]:
    """
    Verify the cryptographic signature and expiration of a session cookie.
    Returns username if valid, otherwise None.
    Also allows plain username during transition if it matches an active DB check in caller.
    """
    if not cookie_val:
        return None
    try:
        parts = cookie_val.split(":")
        if len(parts) == 3:
            username, expiry_str, signature = parts
            expiry_ts = int(expiry_str)
            if time.time() > expiry_ts:
                return None  # Expired
            data_to_sign = f"{username}:{expiry_str}"
            expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
            if hmac.compare_digest(signature, expected_sig):
                return username
        # Reject any unsigned cookie to prevent impersonation
        return None
    except Exception:
        return None
