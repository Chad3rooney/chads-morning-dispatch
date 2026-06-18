"""Cheapest fuel via projectzerothree — free, keyless. State-level, so it reads
as the market floor (the cheapest in the state) rather than a local pump price.
"""

from . import http

API = "https://projectzerothree.info/api.php?format=json"


def fetch_fuel(state="NSW", ftype="U91", timeout=12):
    """Return the cheapest {ftype} in {state}: {price, name, suburb} or None."""
    data = http.get_json(API, timeout=timeout, retries=2)   # urllib follows the 302
    try:
        regions = data["regions"]
    except (TypeError, KeyError):
        return None
    best = None
    for r in regions:
        for p in r.get("prices", []):
            if p.get("type") == ftype and p.get("state") == state and p.get("price"):
                if best is None or p["price"] < best["price"]:
                    best = p
    if not best:
        return None
    return {"price": best["price"], "name": best.get("name", ""),
            "suburb": best.get("suburb", ""), "type": ftype, "state": state}
