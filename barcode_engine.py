import io
import base64
from typing import Optional, List, Dict, Any

try:
    import barcode
    from barcode.writer import SVGWriter, ImageWriter
except ImportError:
    barcode = None
    SVGWriter = None
    ImageWriter = None

def generate_barcode_svg(code: str, barcode_type: str = "code128") -> str:
    """Generate clean, non-clipped SVG representation of barcode for labels and web"""
    if not code:
        code = "00000000"
    code = str(code).strip()
    
    if barcode:
        try:
            code_cls = barcode.get_barcode_class('code128')
            writer = SVGWriter()
            writer_options = {
                'module_width': 0.28,
                'module_height': 15.0,
                'font_size': 10,
                'text_distance': 5.0,
                'quiet_zone': 6.0,
                'write_text': True
            }
            rv = io.BytesIO()
            code_obj = code_cls(code, writer=writer)
            code_obj.write(rv, options=writer_options)
            return rv.getvalue().decode("utf-8")
        except Exception as e:
            print(f"[Barcode SVG Error] {e}")
            
    # Pure Python SVG Fallback with extra vertical headroom
    return _generate_fallback_barcode_svg(code)

def generate_barcode_base64(code: str) -> str:
    """Generate PNG base64 representation of barcode"""
    if not code:
        code = "00000000"
    code = str(code).strip()
    
    if barcode:
        try:
            code_cls = barcode.get_barcode_class('code128')
            writer = ImageWriter()
            rv = io.BytesIO()
            code_obj = code_cls(code, writer=writer)
            code_obj.write(rv, options={'module_width': 0.28, 'module_height': 15.0, 'font_size': 10, 'text_distance': 5.0})
            return f"data:image/png;base64,{base64.b64encode(rv.getvalue()).decode('utf-8')}"
        except Exception as e:
            print(f"[Barcode PNG Error] {e}")
            
    # SVG data URL fallback
    svg = _generate_fallback_barcode_svg(code)
    b64_svg = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64_svg}"

def _generate_fallback_barcode_svg(code: str) -> str:
    """Generate standard pseudo-Code128 SVG with ample height so digits never get cut off"""
    bars = []
    x = 12
    height = 42
    
    # Start guard
    bars.append(f'<rect x="{x}" y="4" width="3.5" height="{height}" fill="#0f172a"/>')
    x += 6
    bars.append(f'<rect x="{x}" y="4" width="2" height="{height}" fill="#0f172a"/>')
    x += 5
    
    for ch in code:
        val = ord(ch) % 8 + 1
        width = 2.5 if val % 2 == 0 else 3.5
        gap = 2.5 if (val + 1) % 3 == 0 else 3.5
        bars.append(f'<rect x="{x}" y="4" width="{width}" height="{height}" fill="#0f172a"/>')
        x += width + gap
        
    # Stop guard
    bars.append(f'<rect x="{x}" y="4" width="3.5" height="{height}" fill="#0f172a"/>')
    x += 6
    bars.append(f'<rect x="{x}" y="4" width="2" height="{height}" fill="#0f172a"/>')
    x += 12
    
    total_height = 76
    text_y = height + 24
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {x} {total_height}" width="100%" height="100%">
        <rect width="100%" height="100%" fill="white"/>
        {''.join(bars)}
        <text x="{x / 2}" y="{text_y}" font-family="Courier New, monospace" font-size="12" font-weight="bold" text-anchor="middle" fill="#0f172a" letter-spacing="1">{code}</text>
    </svg>'''
    return svg
