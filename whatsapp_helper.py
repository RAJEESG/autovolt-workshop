import os
import re
import urllib.parse
import requests
from typing import Optional, Dict, Any

META_WHATSAPP_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "").strip()
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "").strip()

def clean_phone_number(phone: str) -> str:
    """Normalize phone number to international format without plus or spaces (e.g. 919876543210)"""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"91{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"91{digits[1:]}"
    return digits

def generate_wa_me_url(phone: str, message: str) -> str:
    """Generate 1-Click WhatsApp Direct Chat URL"""
    clean_num = clean_phone_number(phone)
    encoded_text = urllib.parse.quote(message)
    return f"https://wa.me/{clean_num}?text={encoded_text}"

def format_invoice_whatsapp_message(
    workshop_name: str,
    invoice_number: str,
    customer_name: str,
    vehicle_reg_no: str,
    vehicle_make_model: str,
    grand_total: float,
    amount_paid: float,
    balance_due: float,
    upi_payment_link: str,
    public_view_url: str,
    workshop_phone: str,
) -> str:
    """Generate professional Malayalam/English formatted WhatsApp invoice message"""
    pay_status = "✅ PAID (പണം ലഭിച്ചു)" if balance_due <= 0 else f"⚠️ PENDING (ബാക്കി: ₹{balance_due:,.2f})"
    
    msg = f"""⚡ *{workshop_name}* ⚡
_Automotive Electrical & Electronic Service Center_

പ്രിയമുള്ള *{customer_name}*,
നിങ്ങളുടെ വാഹനം *{vehicle_reg_no}* ({vehicle_make_model})-ന്റെ ഇലക്ട്രിക്കൽ ജോലികളുടെ ബിൽ വിവരങ്ങൾ താഴെ നൽകുന്നു:

📄 *Invoice No:* #{invoice_number}
🚗 *Vehicle No:* {vehicle_reg_no}
💰 *Total Amount:* ₹{grand_total:,.2f}
💳 *Amount Paid:* ₹{amount_paid:,.2f}
📌 *Status:* {pay_status}

🔗 *View Invoice & Download PDF:*
{public_view_url}
"""
    if balance_due > 0 and upi_payment_link:
        msg += f"""
📱 *Pay Now via GooglePay / PhonePe / Paytm:*
{upi_payment_link}
"""

    msg += f"""
📞 *Contact Workshop:* {workshop_phone}
_Thank you for choosing {workshop_name}!_"""
    return msg

def format_job_status_whatsapp_message(
    workshop_name: str,
    job_number: str,
    status: str,
    customer_name: str,
    vehicle_reg_no: str,
    vehicle_make_model: str,
    technician_name: str,
    notes: str,
    public_job_url: str,
    workshop_phone: str,
) -> str:
    """Generate WhatsApp status update for vehicle repair milestones"""
    status_titles = {
        "RECEIVED": "🚗 *Vehicle Received for Electrical Service*",
        "INSPECTION": "🔍 *Electrical Diagnosis & Inspection Underway*",
        "IN_PROGRESS": "⚡ *Electrical Repair Work in Progress*",
        "WAITING_PARTS": "📦 *Awaiting Electrical Spare Parts*",
        "COMPLETED": "✨ *Vehicle Electrical Service Completed & Tested!*",
        "DELIVERED": "🏁 *Vehicle Delivered. Thank you!*",
    }
    header = status_titles.get(status, f"🛠️ *Job Status Update: {status}*")
    
    msg = f"""⚡ *{workshop_name}* ⚡
{header}

പ്രിയമുള്ള *{customer_name}*,
🚗 *Vehicle:* {vehicle_reg_no} ({vehicle_make_model})
📋 *Job Card:* #{job_number}
👨‍🔧 *Technician:* {technician_name or 'Auto Electric Team'}

📌 *Work / Inspection Notes:*
{notes or 'Work proceeding as scheduled.'}

🔗 *Track Live Vehicle Repair Status:*
{public_job_url}

📞 *Helpline:* {workshop_phone}"""
    return msg

def format_khata_due_reminder_whatsapp_message(
    workshop_name: str,
    customer_name: str,
    due_amount: float,
    upi_payment_link: str,
    workshop_phone: str,
) -> str:
    """Generate friendly WhatsApp reminder for pending khata dues"""
    return f"""⚡ *{workshop_name}* ⚡

പ്രിയമുള്ള *{customer_name}*,
നിങ്ങളുടെ വർക്ക്‌ഷോപ്പ് അക്കൗണ്ടിൽ *₹{due_amount:,.2f}* കുടിശ്ശികയുള്ളതായി കാണുന്നു.

📱 *താഴെയുള്ള ലിങ്കിൽ ക്ലിക്ക് ചെയ്ത് GPay / PhonePe വഴി ഉടൻ പണമടയ്ക്കാം:*
{upi_payment_link}

📞 സംശയങ്ങൾക്ക് വിളിക്കുക: {workshop_phone}
_നന്ദി!_"""

def send_meta_cloud_api_message(phone: str, message: str) -> Dict[str, Any]:
    """Optional Meta WhatsApp Cloud API sender if credentials are configured"""
    if not META_WHATSAPP_TOKEN or not META_PHONE_NUMBER_ID:
        return {"success": False, "message": "Meta Cloud API not configured, using wa.me direct links."}
    
    clean_num = clean_phone_number(phone)
    url = f"https://graph.facebook.com/v19.0/{META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_num,
        "type": "text",
        "text": {"body": message}
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        return {"success": resp.status_code == 200, "response": resp.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}
