"""Market data via Yahoo Finance's public chart endpoint.

We hit the lightweight `v8/finance/chart/{symbol}` JSON directly rather than
using a library like yfinance: it's a single stdlib HTTP call, gives us price
+ previous close in one shot, and has no dependency that can break over time.

Every symbol is fetched independently. A symbol that fails (delisted, renamed,
rate-limited) simply drops out of the snapshot — the briefing still renders.
"""

import os
import time

from . import http

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
CHART_URL_ALT = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"

# Yahoo returns HTTP 429 to cookieless clients. Hitting one of these once seeds
# a consent/session cookie into the shared jar (see http._COOKIE_JAR); every
# chart request thereafter is accepted. Best-effort: if it fails the quotes
# simply drop out, exactly as before.
_SEED_URLS = ("https://fc.yahoo.com/", "https://finance.yahoo.com/")
_session_primed = False


def _prime_session(timeout):
    """Seed Yahoo's session cookie once per process. Safe to call repeatedly.

    The cookie is set as a side effect of the request (into curl's jar when curl
    is used, else urllib's), so we gate on getting *any* response, not on a
    particular cookie store.
    """
    global _session_primed
    if _session_primed:
        return
    for url in _SEED_URLS:
        body = http.get(url, timeout=timeout, retries=1, prefer_curl=True)
        if body is not None or http.cookie_count() > 0:
            break
    _session_primed = True


class Quote(object):
    """One instrument's snapshot."""

    def __init__(self, symbol, label, price, prev_close, currency=None, name=None):
        self.symbol = symbol
        self.label = label
        self.price = price
        self.prev_close = prev_close
        self.currency = currency
        self.name = name
        self.stale = False          # True when filled from the last-known-good cache
        self.as_of = ""             # friendly timestamp of the cached value

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
        data = http.get_json(url, timeout=timeout, retries=1, prefer_curl=True)
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
    _prime_session(timeout)
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


# ---------------------------------------------------------------------------
# Last-known-good cache.
#
# Market data sources (Yahoo especially) can be temporarily blocked — most
# acutely from datacenter IPs like CI runners. Rather than show a wall of
# "unavailable", we remember the last good value for every symbol and fall back
# to it, clearly flagged with the time it was captured. The briefing always has
# numbers; the reader always knows how fresh they are.
# ---------------------------------------------------------------------------
import json as _json
from datetime import datetime as _datetime, timezone as _timezone

from . import timeutil as _timeutil


def load_cache(path):
    """Read the cache file into a dict {symbol: {...}}; {} on any problem."""
    try:
        with open(path, encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _friendly_ts(iso):
    try:
        dt = _datetime.fromisoformat(iso.replace("Z", "+00:00"))
        local, label = _timeutil.to_aest(dt)
        day = local.strftime("%-d %b") if _timeutil._supports_dash() else local.strftime("%d %b")
        return "%s %s" % (day, label)
    except Exception:
        return ""


def apply_cache(quotes, cache):
    """Fill any failed quote from cache, flagging it stale. Returns the list."""
    for q in quotes:
        if q.ok or not cache:
            continue
        c = cache.get(q.symbol)
        if not c or c.get("price") is None:
            continue
        q.price = c.get("price")
        q.prev_close = c.get("prev_close")
        q.currency = q.currency or c.get("currency")
        q.name = q.name or c.get("name")
        q.stale = True
        q.as_of = _friendly_ts(c.get("ts", ""))
    return quotes


def save_cache(path, quote_lists):
    """Persist freshly fetched (non-stale) quotes, merged over the existing file
    so a symbol that failed this run keeps its previous value."""
    cache = load_cache(path)
    now = _datetime.now(_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for quotes in quote_lists:
        for q in quotes:
            if q.ok and not q.stale:
                cache[q.symbol] = {
                    "price": q.price,
                    "prev_close": q.prev_close,
                    "currency": q.currency,
                    "name": q.name,
                    "ts": now,
                }
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(cache, f, indent=2, sort_keys=True)
    except Exception as e:
        print("  ! market cache save failed: %s" % e)
