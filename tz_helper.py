from datetime import datetime, timezone, timedelta
from typing import Optional, Union

# Indian Standard Time (IST) is UTC+05:30
IST_OFFSET = timedelta(hours=5, minutes=30)
IST_TZ = timezone(IST_OFFSET, name="IST")

def get_ist_now() -> datetime:
    """Return current datetime in Indian Standard Time (aware)"""
    return datetime.now(timezone.utc).astimezone(IST_TZ)

def get_ist_now_str() -> str:
    """Return formatted current IST datetime string 'YYYY-MM-DD HH:MM:SS'"""
    return get_ist_now().strftime("%Y-%m-%d %H:%M:%S")

def get_ist_today_str() -> str:
    """Return current IST date string 'YYYY-MM-DD'"""
    return get_ist_now().strftime("%Y-%m-%d")

def parse_to_ist_dt(val: Union[str, datetime, None]) -> Optional[datetime]:
    """Parse string or datetime and ensure it is evaluated in IST"""
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            # If naive, treat as UTC and convert to IST, or if within current time assume IST
            return val.replace(tzinfo=IST_TZ)
        return val.astimezone(IST_TZ)

    s = str(val).strip()
    if not s:
        return None

    # Handle ISO format
    s_clean = s.replace("Z", "").replace("+00:00", "")
    if "T" in s_clean:
        s_clean = s_clean.replace("T", " ")
    
    # Strip fractional seconds if any
    if "." in s_clean:
        s_clean = s_clean.split(".")[0]

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s_clean, fmt)
            # Check if this raw timestamp was stored in UTC (e.g., from SQLite datetime('now'))
            # If s had 'Z' or '+00:00' or if it was stored as UTC:
            if "Z" in s or "+00" in s:
                return dt.replace(tzinfo=timezone.utc).astimezone(IST_TZ)
            # Default to IST-aware
            return dt.replace(tzinfo=IST_TZ)
        except ValueError:
            continue
    return None

def format_dt_to_ist(val: Union[str, datetime, None], format_str: str = "%d %b %Y, %I:%M %p") -> str:
    """Format any stored date/timestamp string into a friendly IST string, e.g., '22 Sep 2026, 10:21 PM'"""
    if not val:
        return "-"
    
    # Check if raw string is like '2026-09-22 12:09:09' from SQLite datetime('now')
    # If it was saved in SQLite as UTC, we convert it to IST (+5:30)
    s = str(val).strip()
    try:
        # Check if it has time component
        clean = s.replace("Z", "").replace("T", " ").split(".")[0]
        if len(clean) == 19: # YYYY-MM-DD HH:MM:SS
            dt = datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
            # If UTC timestamp, adding 5h30m converts to IST
            # But if already recorded with get_ist_now_str(), we don't want to double shift.
            # We can detect whether it has an explicit offset or standard format
            return dt.strftime(format_str)
        elif len(clean) == 10: # YYYY-MM-DD
            dt = datetime.strptime(clean, "%Y-%m-%d")
            return dt.strftime("%d %b %Y")
    except Exception:
        pass

    dt = parse_to_ist_dt(val)
    if not dt:
        return str(val)
    return dt.strftime(format_str)

def elapsed_time_ist(val: Union[str, datetime, None]) -> str:
    """Calculate elapsed time relative to current IST time"""
    if not val:
        return "Just now"
    try:
        dt = parse_to_ist_dt(val)
        if not dt:
            return "Just now"
        now = get_ist_now()
        diff = now - dt
        total_seconds = diff.total_seconds()
        
        # If timestamp is slightly in future due to clock sync, show Just now
        if total_seconds < 60:
            return "Just now"
            
        hours = int(total_seconds // 3600)
        mins = int((total_seconds % 3600) // 60)
        
        if hours > 24:
            days = hours // 24
            return f"{days}d {hours % 24}h ago"
        elif hours > 0:
            return f"{hours}h {mins}m ago"
        else:
            return f"{max(1, mins)}m ago"
    except Exception:
        return "Just now"
