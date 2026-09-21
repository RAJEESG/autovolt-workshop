import io
import urllib.parse
import base64
from typing import Optional

try:
    import qrcode
    from PIL import Image
except ImportError:
    qrcode = None
    Image = None

def generate_upi_link(vpa: str, payee_name: str, amount: float, transaction_note: str = "", currency: str = "INR") -> str:
    """
    Generate NPCI Standard UPI Intent URI for Google Pay, PhonePe, Paytm, BHIM.
    Format: upi://pay?pa=vpa&pn=PayeeName&am=150.00&tn=Note&cu=INR
    """
    if not vpa:
        vpa = "sparkautoworkshop@okaxis"
    vpa = vpa.strip()
    payee_name = payee_name.strip()
    
    params = {
        "pa": vpa,
        "pn": payee_name,
        "am": f"{amount:.2f}",
        "cu": currency,
    }
    if transaction_note:
        params["tn"] = transaction_note
        
    query_string = urllib.parse.urlencode(params)
    return f"upi://pay?{query_string}"

def generate_upi_qr_data_url(upi_link: str) -> str:
    """Generate Base64 PNG Data URL for UPI QR Code to render in browser and PDF"""
    if qrcode:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(upi_link)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
            
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64_str}"
        except Exception as e:
            print(f"[UPI QR Error] {e}")
            
    # Fallback to Google Charts QR or QuickChart public API if local PIL not ready
    encoded = urllib.parse.quote_plus(upi_link)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={encoded}"
