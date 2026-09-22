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
    language: str = "en",
    lang: Optional[str] = None
) -> str:
    """Generate professional formatted WhatsApp invoice message in English, Tamil, or Malayalam"""
    target_lang = (lang or language or "en").lower()
    
    if target_lang == "ta":
        # TAMIL LANGUAGE TEMPLATE
        pay_status = "✅ கட்டணம் செலுத்தப்பட்டது (PAID)" if balance_due <= 0 else f"⚠️ நிலுவைத் தொகை: ₹{balance_due:,.2f}"
        msg = f"""⚡ *{workshop_name}* ⚡
_வாகன மின் மற்றும் மின்னணு சேவை மையம்_

வணக்கம் *{customer_name}*,
உங்கள் வாகனம் *{vehicle_reg_no}* ({vehicle_make_model})-ன் எலக்ட்ரிக்கல் பில் விவரங்கள்:

📄 *இன்வாய்ஸ் எண்:* #{invoice_number}
🚗 *வாகன எண்:* {vehicle_reg_no}
💰 *மொத்த தொகை:* ₹{grand_total:,.2f}
💳 *செலுத்திய தொகை:* ₹{amount_paid:,.2f}
📌 *நிலை:* {pay_status}

🔗 *பில்லைப் பார்க்க & PDF பதிவிறக்க:*
{public_view_url}
"""
        if balance_due > 0 and upi_payment_link:
            msg += f"""
📱 *GPay / PhonePe மூலம் உடனடியாக செலுத்த:*
{upi_payment_link}
"""
        msg += f"""
📞 *தொடர்புக்கு:* {workshop_phone}
_நன்றி!_"""
        return msg

    elif target_lang == "ml":
        # MALAYALAM LANGUAGE TEMPLATE
        pay_status = "✅ PAID (പണം ലഭിച്ചു)" if balance_due <= 0 else f"⚠️ PENDING (ബാക്കി: ₹{balance_due:,.2f})"
        msg = f"""⚡ *{workshop_name}* ⚡
_Auto Electrical & Electronic Service Center_

പ്രിയമുള്ള *{customer_name}*,
നിങ്ങളുടെ വാഹനം *{vehicle_reg_no}* ({vehicle_make_model})-ന്റെ ഇലക്ട്രിക്കൽ ജോലികളുടെ ബിൽ വിവരങ്ങൾ:

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
📱 *Pay Now via GooglePay / PhonePe:*
{upi_payment_link}
"""
        msg += f"""
📞 *Contact Workshop:* {workshop_phone}
_Thank you for choosing {workshop_name}!_"""
        return msg

    else:
        # ENGLISH LANGUAGE TEMPLATE (DEFAULT)
        pay_status = "✅ PAID (Full Payment Received)" if balance_due <= 0 else f"⚠️ PENDING DUE: ₹{balance_due:,.2f}"
        msg = f"""⚡ *{workshop_name}* ⚡
_Automotive Electrical & Electronic Service Center_

Dear *{customer_name}*,
Here is the invoice summary for electrical services on your vehicle *{vehicle_reg_no}* ({vehicle_make_model}):

📄 *Invoice No:* #{invoice_number}
🚗 *Vehicle No:* {vehicle_reg_no}
💰 *Total Amount:* ₹{grand_total:,.2f}
💳 *Amount Paid:* ₹{amount_paid:,.2f}
📌 *Payment Status:* {pay_status}

🔗 *View Bill & Download PDF:*
{public_view_url}
"""
        if balance_due > 0 and upi_payment_link:
            msg += f"""
📱 *Instant Pay via GPay / PhonePe / Paytm:*
{upi_payment_link}
"""
        msg += f"""
📞 *Helpline:* {workshop_phone}
_Thank you for your business!_"""
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
    language: str = "en",
    lang: Optional[str] = None
) -> str:
    """Generate WhatsApp status update in English, Tamil, or Malayalam"""
    target_lang = (lang or language or "en").lower()

    if target_lang == "ta":
        status_titles = {
            "RECEIVED": "🚗 *வாகனம் சேவைக்கு பெறப்பட்டது*",
            "INSPECTION": "🔍 *மின் ஆய்வு நடைபெறுகிறது*",
            "IN_PROGRESS": "⚡ *பழுதுபார்க்கும் பணி நடக்கிறது*",
            "COMPLETED": "✨ *பணி முடிந்தது, வாகனம் தயார்!*",
            "DELIVERED": "🏁 *வாகனம் ஒப்படைக்கப்பட்டது. நன்றி!*",
        }
        header = status_titles.get(status, f"🛠️ *நிலை: {status}*")
        return f"""⚡ *{workshop_name}* ⚡
{header}

வணக்கம் *{customer_name}*,
🚗 *வாகனம்:* {vehicle_reg_no} ({vehicle_make_model})
📋 *ஜாப் கார்டு:* #{job_number}
👨‍🔧 *மெக்கானிக்:* {technician_name or 'எலக்ட்ரிக்கல் குழு'}

📌 *குறிப்பு:*
{notes or 'வேலை திட்டமிட்டபடி நடக்கிறது.'}

🔗 *வாகன நிலையை நேரடியாகக் கண்காணிக்க:*
{public_job_url}

📞 *தொடர்புக்கு:* {workshop_phone}"""

    elif target_lang == "ml":
        status_titles = {
            "RECEIVED": "🚗 *വാഹനം സർവീസിന് ലഭിച്ചു*",
            "INSPECTION": "🔍 *ഇലക്ട്രിക്കൽ പരിശോധന നടക്കുന്നു*",
            "IN_PROGRESS": "⚡ *പണി പുരോഗമിക്കുന്നു*",
            "COMPLETED": "✨ *പണി പൂർത്തിയായി, വാഹനം റെഡി!*",
            "DELIVERED": "🏁 *വാഹനം ഡെലിവറി ചെയ്തു. നന്ദി!*",
        }
        header = status_titles.get(status, f"🛠️ *Status: {status}*")
        return f"""⚡ *{workshop_name}* ⚡
{header}

പ്രിയമുള്ള *{customer_name}*,
🚗 *Vehicle:* {vehicle_reg_no} ({vehicle_make_model})
📋 *Job Card:* #{job_number}
👨‍🔧 *Technician:* {technician_name or 'Auto Electric Team'}

📌 *Notes:*
{notes or 'Work proceeding as scheduled.'}

🔗 *Live Status Tracker:*
{public_job_url}

📞 *Helpline:* {workshop_phone}"""

    else:
        status_titles = {
            "RECEIVED": "🚗 *Vehicle Received for Electrical Service*",
            "INSPECTION": "🔍 *Electrical Diagnosis & Inspection Underway*",
            "IN_PROGRESS": "⚡ *Repair Work in Progress*",
            "COMPLETED": "✨ *Service Completed & Tested! Vehicle Ready.*",
            "DELIVERED": "🏁 *Vehicle Delivered. Thank you!*",
        }
        header = status_titles.get(status, f"🛠️ *Job Status: {status}*")
        return f"""⚡ *{workshop_name}* ⚡
{header}

Dear *{customer_name}*,
🚗 *Vehicle:* {vehicle_reg_no} ({vehicle_make_model})
📋 *Job Card:* #{job_number}
👨‍🔧 *Technician:* {technician_name or 'Auto Electric Team'}

📌 *Service Notes:*
{notes or 'Work proceeding as scheduled.'}

🔗 *Track Live Progress:*
{public_job_url}

📞 *Helpline:* {workshop_phone}"""

def format_khata_due_reminder_whatsapp_message(
    workshop_name: str,
    customer_name: str,
    due_amount: float,
    upi_payment_link: str,
    workshop_phone: str,
    language: str = "en",
    lang: Optional[str] = None
) -> str:
    """Generate friendly WhatsApp reminder for pending khata dues in English, Tamil, or Malayalam"""
    target_lang = (lang or language or "en").lower()

    if target_lang == "ta":
        return f"""⚡ *{workshop_name}* ⚡

வணக்கம் *{customer_name}*,
உங்கள் கணக்கில் *₹{due_amount:,.2f}* நிலுவைத் தொகை உள்ளது.

📱 *கீழே உள்ள லிங்க்கை கிளிக் செய்து GPay / PhonePe மூலம் உடனடியாக செலுத்தலாம்:*
{upi_payment_link}

📞 *தொடர்புக்கு:* {workshop_phone}
_நன்றி!_"""

    elif target_lang == "ml":
        return f"""⚡ *{workshop_name}* ⚡

പ്രിയമുള്ള *{customer_name}*,
നിങ്ങളുടെ വർക്ക്‌ഷോപ്പ് അക്കൗണ്ടിൽ *₹{due_amount:,.2f}* കുടിശ്ശികയുള്ളതായി കാണുന്നു.

📱 *താഴെയുള്ള ലിങ്കിൽ ക്ലിക്ക് ചെയ്ത് GPay / PhonePe വഴി ഉടൻ പണമടയ്ക്കാം:*
{upi_payment_link}

📞 *വിളിക്കുക:* {workshop_phone}
_നന്ദി!_"""

    else:
        return f"""⚡ *{workshop_name}* ⚡

Dear *{customer_name}*,
This is a gentle reminder regarding your outstanding workshop balance of *₹{due_amount:,.2f}*.

📱 *Tap below to pay instantly via Google Pay / PhonePe:*
{upi_payment_link}

📞 *Questions? Call:* {workshop_phone}
_Thank you!_"""
