"""Market data via Yahoo Finance's public chart endpoint.

We hit the lightweight `v8/finance/chart/{symbol}` JSON directly rather than
using a library like yfinance: it's a single stdlib HTTP call, gives us price
+ previous close in one shot, and has no dependency that can break over time.

Every symbol is fetched independently. A symbol that fails (delisted, renamed,
rate-limited) simply drops out of the snapshot — the briefing still renders.
"""

import time

from . import http

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
CHART_URL_ALT = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"


class Quote(object):
    """One instrument's snapshot."""

    def __init__(self, symbol, label, price, prev_close, currency=None, name=None):
        self.symbol = symbol
        self.label = label
        self.price = price
        self.prev_close = prev_close
        self.currency = currency
        self.name = name

    @property
    def ok(self):
        return self.price is not None and self.prev_close not in (None, 0)

    @property
    def change(self):
        if not self.ok:
            return None
        return self.price - self.prev_close

    @property
    def pct(self):
        if not self.ok:
            return None
        return (self.price - self.prev_close) / self.prev_close * 100.0

    @property
    def direction(self):
        c = self.change
        if c is None:
            return "flat"
        if c > 0:
            return "up"
        if c < 0:
            return "down"
        return "flat"


def _fetch_one(symbol, label, timeout):
    import urllib.parse
    sym = urllib.parse.quote(symbol, safe="")
    for url in (CHART_URL.format(sym=sym), CHART_URL_ALT.format(sym=sym)):
        data = http.get_json(url, timeout=timeout, retries=2)
        try:
            meta = data["chart"]["result"][0]["meta"]
        except (TypeError, KeyError, IndexError):
            continue
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None:
            continue
        return Quote(
            symbol=symbol,
            label=label,
            price=price,
            prev_close=prev,
            currency=meta.get("currency"),
            name=meta.get("shortName") or meta.get("longName"),
        )
    # Failed — return a placeholder so the caller knows it was requested.
    return Quote(symbol, label, None, None)


def fetch_quotes(pairs, timeout=12, polite_delay=0.15):
    """Fetch a list of (symbol, label) tuples. Returns a list of Quote.

    Sequential with a small delay to stay polite and avoid rate limits; a daily
    batch of a few dozen symbols completes in a handful of seconds.
    """
    out = []
    for symbol, label in pairs:
        out.append(_fetch_one(symbol, label, timeout))
        if polite_delay:
            time.sleep(polite_delay)
    return out


def fetch_market_groups(groups, timeout=12):
    """Resolve config MARKET_GROUPS into the same structure with live Quotes."""
    resolved = []
    for g in groups:
        quotes = fetch_quotes(g["tickers"], timeout=timeout)
        resolved.append({
            "title": g["title"],
            "note": g.get("note", ""),
            "quotes": quotes,
        })
    return resolved
