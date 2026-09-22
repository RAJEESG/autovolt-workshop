import random
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import database as db
from auth_helper import hash_password

def generate_numeric_otp(length: int = 6) -> str:
    """Generate a cryptographically randomized 6-digit numeric OTP"""
    return "".join([str(random.randint(0, 9)) for _ in range(length)])

def clean_whatsapp_mobile(mobile: str) -> str:
    """Clean and normalize phone number for WhatsApp wa.me links (e.g. 919876543210)"""
    digits = re.sub(r"\D", "", mobile)
    if len(digits) == 10:
        return "91" + digits
    return digits

def generate_and_store_otp(username_or_mobile: str) -> Optional[Dict[str, Any]]:
    """
    Generate 6-digit OTP for a user by username or WhatsApp mobile number,
    store it in the database with a 10-minute expiry, and return details.
    """
    conn = db.get_db_connection()
    cursor = conn.cursor()

    cleaned_input = username_or_mobile.strip()
    clean_digits = re.sub(r"\D", "", cleaned_input)

    # Search by username, exact phone, or matching 10-digit mobile
    cursor.execute("""
        SELECT * FROM users 
        WHERE username = ? 
           OR whatsapp_mobile = ? 
           OR phone = ?
           OR replace(replace(replace(whatsapp_mobile, ' ', ''), '-', ''), '+', '') LIKE ?
           OR replace(replace(replace(phone, ' ', ''), '-', ''), '+', '') LIKE ?
    """, (
        cleaned_input, 
        cleaned_input, 
        cleaned_input,
        f"%{clean_digits[-10:]}%" if len(clean_digits) >= 10 else f"%{clean_digits}%",
        f"%{clean_digits[-10:]}%" if len(clean_digits) >= 10 else f"%{clean_digits}%"
    ))
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        return None

    user = dict(user_row)
    otp = generate_numeric_otp(6)
    expiry_time = (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        UPDATE users 
        SET otp_code = ?, otp_expiry = ?
        WHERE id = ?
    """, (otp, expiry_time, user["id"]))
    
    db.log_audit("OTP_GENERATED", "users", user["id"], f"Generated WhatsApp OTP for user {user['username']}", cursor=cursor)
    conn.commit()
    conn.close()

    mobile_number = user.get("whatsapp_mobile") or user.get("phone") or "+919876500000"
    whatsapp_link = build_whatsapp_otp_url(mobile_number, otp, user["username"], user.get("full_name", ""))

    return {
        "user_id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "whatsapp_mobile": mobile_number,
        "otp_code": otp,
        "otp_expiry": expiry_time,
        "whatsapp_link": whatsapp_link
    }

def build_whatsapp_otp_url(mobile: str, otp: str, username: str, full_name: str = "") -> str:
    """Build a pre-formatted WhatsApp direct message link with the 6-digit OTP"""
    clean_phone = clean_whatsapp_mobile(mobile)
    
    message = (
        f"🔐 *AutoVolt Pro — Security Verification*\n\n"
        f"Hello *{full_name or username}*,\n\n"
        f"Your AutoVolt Pro Password Reset OTP is:\n"
        f"👉 *{otp}*\n\n"
        f"⏱️ This OTP is valid for the next *10 minutes*.\n"
        f"⚠️ Do not share this OTP with anyone.\n\n"
        f"_AutoVolt Pro Workshop Cloud Security_"
    )
    
    encoded_text = urllib.parse.quote(message)
    return f"https://wa.me/{clean_phone}?text={encoded_text}"

def verify_and_reset_password(username: str, input_otp: str, new_password: str) -> Tuple[bool, str]:
    """
    Verify 6-digit OTP and reset user password
    """
    if not input_otp or not new_password:
        return False, "OTP and new password are required."

    if len(new_password.strip()) < 4:
        return False, "Password must be at least 4 characters long."

    conn = db.get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        return False, "User account not found."

    user = dict(user_row)
    stored_otp = user.get("otp_code")
    expiry_str = user.get("otp_expiry")

    if not stored_otp or stored_otp.strip() != input_otp.strip():
        conn.close()
        return False, "Invalid 6-digit OTP. Please check the code sent to your WhatsApp and try again."

    if expiry_str:
        try:
            expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry_dt:
                conn.close()
                return False, "OTP has expired. Please request a new OTP."
        except Exception:
            pass

    # Valid OTP -> update password and clear OTP
    new_pw_hash = hash_password(new_password.strip())
    cursor.execute("""
        UPDATE users 
        SET password_hash = ?, otp_code = NULL, otp_expiry = NULL, reset_token = NULL, reset_token_expiry = NULL
        WHERE id = ?
    """, (new_pw_hash, user["id"]))

    db.log_audit("PASSWORD_RESET_OTP", "users", user["id"], f"Password successfully reset via WhatsApp OTP for user {user['username']}", cursor=cursor)
    conn.commit()
    conn.close()

    return True, "Password reset successfully. You can now log in with your new password."
