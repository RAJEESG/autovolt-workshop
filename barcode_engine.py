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
    """Generate SVG representation of barcode for inline web and label rendering"""
    if not code:
        code = "00000000"
    code = str(code).strip()
    
    if barcode:
        try:
            # Clean non-alphanumeric if needed
            code_cls = barcode.get_barcode_class('code128')
            writer = SVGWriter()
            # Custom writer options for clean crisp lines
            writer_options = {
                'module_width': 0.25,
                'module_height': 12.0,
                'font_size': 9,
                'text_distance': 4.0,
                'quiet_zone': 4.0,
                'write_text': True
            }
            rv = io.BytesIO()
            code_obj = code_cls(code, writer=writer)
            code_obj.write(rv, options=writer_options)
            return rv.getvalue().decode("utf-8")
        except Exception as e:
            print(f"[Barcode SVG Error] {e}")
            
    # Pure Python SVG Fallback if library fails or during install
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
            code_obj.write(rv, options={'module_width': 0.25, 'module_height': 12.0, 'font_size': 9, 'text_distance': 4.0})
            return f"data:image/png;base64,{base64.b64encode(rv.getvalue()).decode('utf-8')}"
        except Exception as e:
            print(f"[Barcode PNG Error] {e}")
            
    # SVG data URL fallback
    svg = _generate_fallback_barcode_svg(code)
    b64_svg = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64_svg}"

def _generate_fallback_barcode_svg(code: str) -> str:
    """Generate standard pseudo-Code128 SVG for instant rendering"""
    # Deterministic pattern generation based on characters in code
    bars = []
    x = 10
    height = 50
    
    # Start guard
    bars.append(f'<rect x="{x}" y="0" width="3" height="{height}" fill="#111827"/>')
    x += 5
    bars.append(f'<rect x="{x}" y="0" width="2" height="{height}" fill="#111827"/>')
    x += 4
    
    for ch in code:
        val = ord(ch) % 8 + 1
        width = 2 if val % 2 == 0 else 3
        gap = 2 if (val + 1) % 3 == 0 else 3
        bars.append(f'<rect x="{x}" y="0" width="{width}" height="{height}" fill="#111827"/>')
        x += width + gap
        
    # Stop guard
    bars.append(f'<rect x="{x}" y="0" width="3" height="{height}" fill="#111827"/>')
    x += 5
    bars.append(f'<rect x="{x}" y="0" width="2" height="{height}" fill="#111827"/>')
    x += 10
    
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {x} 70" width="100%" height="100%">
        <rect width="100%" height="100%" fill="white"/>
        {''.join(bars)}
        <text x="{x / 2}" y="65" font-family="monospace" font-size="11" font-weight="bold" text-anchor="middle" fill="#111827">{code}</text>
    </svg>'''
    return svg
