"""Market data via Yahoo Finance's public chart endpoint.

We hit the lightweight `v8/finance/chart/{symbol}` JSON directly rather than
using a library like yfinance: it's a single stdlib HTTP call, gives us price
+ previous close in one shot, and has no dependency that can break over time.

Every symbol is fetched independently. A symbol that fails (delisted, renamed,
rate-limited) simply drops out of the snapshot — the briefing still renders.
"""

import os
import time

import urllib.parse

from . import http

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"
CHART_URL_ALT = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=5d"

# CNBC's public quote API: keyless, reliable from datacenter IPs (where Yahoo is
# blocked), and accepts many symbols in one request. It is the primary source;
# Yahoo is used to upgrade US equity-index futures (which CNBC won't serve) to
# true overnight futures when reachable. See _fetch_cnbc_batch / fetch_quotes.
CNBC_URL = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/"
            "symbol?symbols={syms}&requestMethod=itv&fund=1&exthrs=1&output=json")

# Yahoo symbol -> CNBC symbol. Anything not listed (US tickers like NVDA, ASX
# tickers like BHP.AX) is accepted by CNBC verbatim, so it maps to itself.
# The four equity-index futures have no CNBC future, so they map to the cash
# index as a stand-in; Yahoo upgrades them to real futures when available.
CNBC_MAP = {
    "ES=F": ".SPX", "NQ=F": ".NDX", "YM=F": ".DJI", "RTY=F": ".RUT",
    "GC=F": "@GC.1", "SI=F": "@SI.1", "HG=F": "@HG.1",
    "CL=F": "@CL.1", "BZ=F": "@LCO.1", "NG=F": "@NG.1",
    "^AXJO": ".AXJO", "^AORD": ".AORD", "AUDUSD=X": "AUD=",
    "DX-Y.NYB": ".DXY", "^TNX": "US10Y", "BTC-USD": "BTC=",
}
EQUITY_FUTURES = frozenset(("ES=F", "NQ=F", "YM=F", "RTY=F"))

# Yahoo returns HTTP 429 to cookieless clients. Hitting one of these once seeds
# a consent/session cookie into the shared jar (see http._COOKIE_JAR); every
# chart request thereafter is accepted. Best-effort: if it fails the quotes
# simply drop out, exactly as before.
_SEED_URLS = ("https://fc.yahoo.com/", "https://finance.yahoo.com/")

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


def _parse_num(s):
    """Parse CNBC's display numbers ('7,511.35', '4.437%') into a float, or None."""
    if s is None:
        return None
    t = str(s).replace(",", "").replace("%", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _cnbc_symbol(symbol):
    return CNBC_MAP.get(symbol, symbol)


def _fetch_cnbc_batch(pairs, timeout):
    """Fetch many quotes in one CNBC request. Returns {yahoo_symbol: Quote}."""
    want = {}                                  # cnbc_symbol -> (yahoo_symbol, label)
    for symbol, label in pairs:
        want[_cnbc_symbol(symbol)] = (symbol, label)
    if not want:
        return {}
    joined = "%7C".join(urllib.parse.quote(s, safe="@=.") for s in want)
    data = http.get_json(CNBC_URL.format(syms=joined), timeout=timeout, retries=2)
    try:
        quotes = data["FormattedQuoteResult"]["FormattedQuote"]
    except (TypeError, KeyError):
        return {}
    out = {}
    for q in quotes:
        if str(q.get("code")) != "0":
            continue
        meta = want.get(q.get("symbol"))
        if not meta:
            continue
        symbol, label = meta
        price = _parse_num(q.get("last"))
        if price is None:
            continue
        out[symbol] = Quote(
            symbol=symbol, label=label, price=price,
            prev_close=_parse_num(q.get("previous_day_closing")),
            currency=q.get("currencyCode"), name=q.get("name"),
        )
    return out


def fetch_quotes(pairs, timeout=12, polite_delay=0.15):
    """Fetch a list of (symbol, label) tuples. Returns a list of Quote.

    Strategy, ordered for reliability and speed:
      1. One CNBC batch call resolves almost everything (keyless, works from
         CI/datacenter IPs where Yahoo is blocked).
      2. For US equity-index futures, prefer Yahoo's *real* overnight futures
         over CNBC's cash-index stand-in, when Yahoo is reachable.
      3. Anything still missing falls back to a per-symbol Yahoo fetch.
    A symbol that every source fails simply drops out — the briefing still renders.
    """
    resolved = {}
    try:
        resolved.update(_fetch_cnbc_batch(pairs, timeout))
    except Exception:
        pass

    need_yahoo = [(s, l) for s, l in pairs if s in EQUITY_FUTURES
                  or s not in resolved or not resolved[s].ok]
    if need_yahoo:
        _prime_session(timeout)
        for symbol, label in need_yahoo:
            q = _fetch_one(symbol, label, timeout)
            if q.ok:
                resolved[symbol] = q          # real futures upgrade / fill the gap
            if polite_delay:
                time.sleep(polite_delay)

    return [resolved.get(s) or Quote(s, l, None, None) for s, l in pairs]


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
