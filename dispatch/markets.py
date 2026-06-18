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
    # US equity-index futures -> CNBC cash index (Yahoo upgrades to real futures)
    "ES=F": ".SPX", "NQ=F": ".NDX", "YM=F": ".DJI", "RTY=F": ".RUT", "^VIX": ".VIX",
    # Metals & energy
    "GC=F": "@GC.1", "SI=F": "@SI.1", "HG=F": "@HG.1", "PL=F": "@PL.1", "PA=F": "@PA.1",
    "CL=F": "@CL.1", "BZ=F": "@LCO.1", "NG=F": "@NG.1",
    # Australia + FX
    "^AXJO": ".AXJO", "^AORD": ".AORD",
    "AUDUSD=X": "AUD=", "EURUSD=X": "EUR=", "USDJPY=X": "JPY=",
    "GBPUSD=X": "GBP=", "NZDUSD=X": "NZD=",
    # Rates, dollar, crypto
    "DX-Y.NYB": ".DXY", "^TNX": "US10Y", "BTC-USD": "BTC=", "ETH-USD": "ETH=",
    # CNBC-native instruments (no clean Yahoo symbol) are used verbatim in config:
    #   @TIO.1 = Iron Ore 62%, AU10Y = Australia 10Y bond, US2Y = US 2Y Treasury
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

    def __init__(self, symbol, label, price, prev_close, currency=None, name=None,
                 day_open=None, day_high=None, day_low=None,
                 year_high=None, year_low=None):
        self.symbol = symbol
        self.label = label
        self.price = price
        self.prev_close = prev_close
        self.currency = currency
        self.name = name
        self.day_open = day_open
        self.day_high = day_high
        self.day_low = day_low
        self.year_high = year_high
        self.year_low = year_low
        self.stale = False          # True when filled from the last-known-good cache
        self.as_of = ""             # friendly timestamp of the cached value
        self.sensitive = False      # ASX price-sensitive announcement flag
        self.sensitive_note = ""    # headline of that announcement (for the tooltip)
        self.no_live = False        # True for non-CNBC quotes the browser can't refresh
        self.danger = False         # bond yield at/above its danger threshold
        self.danger_at = None       # the threshold (for the tooltip / live JS)

    @property
    def day_range_pct(self):
        """Where `price` sits in the day's low–high band, 0..100, or None.

        Drives the day-range micro-bar in the snapshot. None when the band is
        missing or degenerate (e.g. iron ore, which only has a daily settle).
        """
        lo, hi, p = self.day_low, self.day_high, self.price
        if None in (lo, hi, p) or hi <= lo:
            return None
        return max(0.0, min(100.0, (p - lo) / (hi - lo) * 100.0))

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
            day_open=meta.get("regularMarketOpen"),
            day_high=meta.get("regularMarketDayHigh"),
            day_low=meta.get("regularMarketDayLow"),
            year_high=meta.get("fiftyTwoWeekHigh"),
            year_low=meta.get("fiftyTwoWeekLow"),
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
        # Use CNBC's own day-change field, not last - previous_day_closing: when a
        # market is closed CNBC sets previous_day_closing == last (giving a false
        # 0.00%), but `change` still reflects the last session's move.
        chg = _parse_num(q.get("change"))     # None for "UNCH"
        prev = price - (chg if chg is not None else 0.0)
        out[symbol] = Quote(
            symbol=symbol, label=label, price=price,
            prev_close=prev,
            currency=q.get("currencyCode"), name=q.get("name"),
            day_open=_parse_num(q.get("open")),
            day_high=_parse_num(q.get("high")),
            day_low=_parse_num(q.get("low")),
            year_high=_parse_num(q.get("yrhiprice")),
            year_low=_parse_num(q.get("yrloprice")),
        )
    return out


# ---------------------------------------------------------------------------
# ASX (markitdigital) — a server-side source for ASX tickers CNBC doesn't carry
# (e.g. small-cap explorers) and for price-sensitive announcement flags. It has
# no CORS headers, so these can't refresh in the browser — markitdigital quotes
# are flagged no_live.
# ---------------------------------------------------------------------------
MARKIT = "https://asx.api.markitdigital.com/asx-research/1.0/companies/{t}/{ep}"


def _markit_code(symbol):
    return symbol[:-3].lower() if symbol.upper().endswith(".AX") else None


def _fetch_markit_quote(symbol, label, timeout):
    code = _markit_code(symbol)
    if not code:
        return None
    data = http.get_json(MARKIT.format(t=code, ep="header"), timeout=timeout, retries=1)
    try:
        d = data["data"]
    except (TypeError, KeyError):
        return None
    last = d.get("priceLast")
    if last is None:
        return None
    chg = d.get("priceChange") or 0
    q = Quote(symbol, label, last, last - chg,
              currency="AUD", name=d.get("displayName"))
    q.no_live = True            # markitdigital has no CORS; can't refresh client-side
    return q


def fetch_announcements(symbols, lookback_hours=48, timeout=12):
    """Return {symbol: {sensitive, headline, date}} for ASX tickers with a
    price-sensitive announcement in the lookback window. Best-effort."""
    from datetime import datetime as _dt, timezone as _tz
    cutoff = _dt.now(_tz.utc).timestamp() - lookback_hours * 3600
    out = {}
    for symbol in symbols:
        code = _markit_code(symbol)
        if not code:
            continue
        data = http.get_json(MARKIT.format(t=code, ep="announcements") +
                             "?pageSize=8&itemsPerPage=8", timeout=timeout, retries=1)
        try:
            items = data["data"]["items"]
        except (TypeError, KeyError):
            continue
        for it in items or []:
            if not it.get("isPriceSensitive"):
                continue
            ts = _parse_iso(it.get("date"))
            if ts is None or ts < cutoff:        # only flag a confirmed-recent item
                continue
            out[symbol] = {"sensitive": True, "headline": it.get("headline", ""),
                           "date": it.get("date", "")}
            break
        time.sleep(0.1)
    return out


def _parse_iso(s):
    from datetime import datetime as _dt, timezone as _tz
    if not s:
        return None
    try:
        return _dt.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def apply_announcements(quotes, flags):
    for q in quotes:
        f = flags.get(q.symbol)
        if f and f.get("sensitive"):
            q.sensitive = True
            q.sensitive_note = f.get("headline", "Price-sensitive announcement")
    return quotes


def apply_bond_danger(quotes, thresholds):
    """Attach each configured bond's danger threshold (so the row can be
    re-evaluated live in the browser) and flag it red when the yield is at or
    above that level."""
    for q in quotes:
        lvl = (thresholds or {}).get(q.symbol)
        if lvl is None:
            continue
        q.danger_at = lvl
        if q.ok and q.price is not None and q.price >= lvl:
            q.danger = True
    return quotes


def fetch_quotes(pairs, timeout=12, polite_delay=0.15):
    """Fetch a list of (symbol, label) tuples. Returns a list of Quote.

    Strategy, ordered for reliability and speed:
      1. One CNBC batch call resolves almost everything (keyless, CORS-enabled,
         works from CI/datacenter IPs where Yahoo is blocked).
      2. For US equity-index futures, prefer Yahoo's *real* overnight futures
         over CNBC's cash-index stand-in, when Yahoo is reachable.
      3. Remaining ASX tickers fall back to the ASX (markitdigital) feed; any
         other gap falls back to a per-symbol Yahoo fetch.
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
            elif _markit_code(symbol):
                mq = _fetch_markit_quote(symbol, label, timeout)
                if mq and mq.ok:
                    resolved[symbol] = mq
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
        q.day_open = c.get("day_open")
        q.day_high = c.get("day_high")
        q.day_low = c.get("day_low")
        q.year_high = c.get("year_high")
        q.year_low = c.get("year_low")
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
                    "day_open": q.day_open,
                    "day_high": q.day_high,
                    "day_low": q.day_low,
                    "year_high": q.year_high,
                    "year_low": q.year_low,
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
