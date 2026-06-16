"""Time handling for Australian Eastern time, dependency-free.

Australia's eastern states (NSW/VIC/ACT/TAS) observe:
  - AEDT (UTC+11) from the first Sunday in October to the first Sunday in April
  - AEST (UTC+10) the rest of the year

We prefer the stdlib `zoneinfo` (Python 3.9+) when present, and fall back to a
small manual calculator so the briefing also runs on older Pythons with no
extra packages.
"""

from datetime import datetime, timedelta, timezone

_TZNAME = "Australia/Sydney"

try:                                    # Python 3.9+
    from zoneinfo import ZoneInfo
    _ZONE = ZoneInfo(_TZNAME)
except Exception:                       # pragma: no cover - older Pythons
    _ZONE = None


def _first_sunday(year, month):
    """Date of the first Sunday of the given month."""
    d = datetime(year, month, 1)
    # weekday(): Monday=0 .. Sunday=6
    return d + timedelta(days=(6 - d.weekday()) % 7)


def _manual_offset(utc_dt):
    """Return (timedelta_offset, label) for Australian Eastern time, manually.

    `utc_dt` must be a naive or aware datetime understood as UTC.
    """
    y = utc_dt.year
    # DST starts first Sunday of October 02:00 local, ends first Sunday of
    # April 03:00 local. We compare against the UTC instant of those switches.
    dst_start = _first_sunday(y, 10).replace(hour=16)   # 02:00 AEST = 16:00 UTC prev day-ish
    dst_end = _first_sunday(y, 4).replace(hour=16)      # 03:00 AEDT = 16:00 UTC
    naive_utc = utc_dt.replace(tzinfo=None)
    # Southern hemisphere: DST spans the new year (Oct -> Apr).
    is_dst = naive_utc >= dst_start or naive_utc < dst_end
    if is_dst:
        return timedelta(hours=11), "AEDT"
    return timedelta(hours=10), "AEST"


def now_aest():
    """Return (aware_datetime_in_eastern_australia, label) for 'now'."""
    utc = datetime.now(timezone.utc)
    return to_aest(utc)


def to_aest(dt):
    """Convert an aware datetime to eastern Australian time. Returns (dt, label)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc = dt.astimezone(timezone.utc)
    if _ZONE is not None:
        local = utc.astimezone(_ZONE)
        label = local.tzname() or "AEST"
        # Normalise label (zoneinfo may return 'AEST'/'AEDT' already)
        return local, label
    offset, label = _manual_offset(utc)
    return utc.astimezone(timezone(offset)), label


def fmt_full(dt, label):
    """e.g. 'Tuesday, 16 June 2026'."""
    return dt.strftime("%A, %-d %B %Y") if _supports_dash() else dt.strftime("%A, %d %B %Y")


def fmt_time(dt, label):
    """e.g. '6:20am AEST'."""
    h = dt.strftime("%-I") if _supports_dash() else str(int(dt.strftime("%I")))
    return "%s:%s%s %s" % (h, dt.strftime("%M"), dt.strftime("%p").lower(), label)


def fmt_stamp(dt, label):
    """e.g. 'Tue 16 Jun, 6:20am AEST' — compact, for the generated-at line."""
    return "%s, %s" % (dt.strftime("%a %d %b"), fmt_time(dt, label))


def relative_age(dt_aest, now_dt):
    """Human 'time ago' string from an AEST datetime to now."""
    if dt_aest is None:
        return ""
    delta = now_dt - dt_aest
    secs = delta.total_seconds()
    if secs < 0:
        return "just now"
    mins = int(secs // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return "%dm ago" % mins
    hrs = mins // 60
    if hrs < 24:
        return "%dh ago" % hrs
    days = hrs // 24
    return "%dd ago" % days


def _supports_dash():
    """strftime('%-d') works on macOS/Linux but not Windows."""
    try:
        datetime(2000, 1, 1).strftime("%-d")
        return True
    except ValueError:
        return False
