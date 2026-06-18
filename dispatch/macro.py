"""Macro helpers — a transparent, source-free recession signal.

Derived from the US 2s10s Treasury yield curve (US 2Y vs US 10Y), both of which
we already fetch. An inverted curve (10Y below 2Y) has preceded most modern US
recessions, so the spread is a defensible, explainable risk gauge — no extra
data source, no black box. Labelled clearly as a yield-curve signal.
"""


def _find(all_quotes, symbol):
    for q in all_quotes:
        if q.symbol == symbol and q.ok:
            return q
    return None


def gold_in_aud(all_quotes):
    """Gold priced in AUD/oz = gold USD/oz ÷ (USD per AUD). The benchmark most
    ASX gold juniors actually track. Returns a float or None."""
    gold = _find(all_quotes, "GC=F")          # USD/oz
    aud = _find(all_quotes, "AUDUSD=X")        # USD per 1 AUD
    if not gold or not aud or not aud.price:
        return None
    return gold.price / aud.price


def recession_signal(all_quotes):
    """Return a dict describing the curve-based recession signal, or None."""
    y2 = _find(all_quotes, "US2Y")
    y10 = _find(all_quotes, "^TNX")        # config's US 10Y symbol
    if not y2 or not y10:
        return None
    spread = y10.price - y2.price          # percentage points
    bps = round(spread * 100)

    if spread < -0.10:
        level, label = "high", "Elevated"
    elif spread < 0.20:
        level, label = "moderate", "Moderate"
    elif spread < 0.60:
        level, label = "watch", "Some risk"
    else:
        level, label = "low", "Low"

    # Gauge position 0..100 (higher = more risk). Maps a +2.0pp curve to ~5 and
    # a -1.0pp inversion to ~95.
    gauge = max(4.0, min(96.0, (2.0 - spread) / 3.0 * 100.0))

    detail = "US 2s10s curve %s at %+d bps. %s" % (
        "inverted" if spread < 0 else "positive", bps,
        "An inverted curve has preceded most US recessions — a caution signal."
        if spread < 0 else
        "A positively sloped curve is historically consistent with expansion.")

    return {
        "spread_bps": bps, "level": level, "label": label, "gauge": gauge,
        "detail": detail, "y2": y2.price, "y10": y10.price,
    }
