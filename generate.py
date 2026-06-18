#!/usr/bin/env python3
"""
Chad's Morning Dispatch — build entry point.

    python3 generate.py            # build into ./public
    python3 generate.py --out DIR  # build into a custom directory

Pulls markets + news, synthesises the overnight, and writes a single static
HTML briefing to <out>/index.html (plus a dated copy in <out>/archive/).

Every stage degrades gracefully: a failed data source narrows the briefing but
never breaks the build. Designed to run unattended from GitHub Actions.
"""

import argparse
import glob
import os
import sys
import traceback

from dispatch import config as cfg
from dispatch import markets, news, synthesis, render, timeutil, macro, weather, fuel


def _greeting(now_dt, owner):
    h = now_dt.hour
    part = "morning" if h < 12 else ("afternoon" if h < 18 else "evening")
    return "Good %s, %s." % (part, owner)


def _safe(label, fn, fallback):
    """Run a stage, catching anything so the build always completes."""
    try:
        return fn()
    except Exception as e:                       # noqa: broad — resilience is the point
        print("  ! %s failed: %s" % (label, e))
        traceback.print_exc()
        return fallback


def build(out_dir):
    now_dt, tz_label = timeutil.now_aest()
    date_full = timeutil.fmt_full(now_dt, tz_label)
    stamp = timeutil.fmt_stamp(now_dt, tz_label)
    date_key = now_dt.strftime("%Y-%m-%d")
    print("Building %s for %s" % (cfg.SITE["title"], stamp))

    timeout = cfg.SITE.get("request_timeout", 12)
    cache_path = cfg.SITE.get("market_cache_path", "data/market_cache.json")
    market_cache = markets.load_cache(cache_path)

    print("- Markets: snapshot groups")
    market_groups = _safe(
        "markets", lambda: markets.fetch_market_groups(cfg.MARKET_GROUPS, timeout=timeout), [])

    print("- Markets: watchlist")
    watchlist = _safe(
        "watchlist", lambda: markets.fetch_quotes(cfg.WATCHLIST, timeout=timeout), [])

    print("- Markets: mining watch")
    mw_cfg = cfg.__dict__.get("MINING_WATCH", [])
    mw_quotes = _safe("mining_watch", lambda: markets.fetch_quotes(
        [(s, l) for s, l, _ in mw_cfg], timeout=timeout), [])

    # Micro pick of the day (rotates daily).
    picks = cfg.__dict__.get("MICRO_PICKS", [])
    micro_pick = None
    pick_quotes = []
    if picks:
        psym, plabel, pthesis = picks[now_dt.timetuple().tm_yday % len(picks)]
        pq = _safe("micro_pick", lambda: markets.fetch_quotes([(psym, plabel)], timeout=timeout),
                   [markets.Quote(psym, plabel, None, None)])
        pick_quotes = pq
        micro_pick = (pq[0], plabel, pthesis)

    # Fill any symbol that failed this run from the last-known-good cache (clearly
    # flagged as stale), then persist the fresh values for next time.
    all_quote_lists = [g["quotes"] for g in market_groups] + [watchlist, mw_quotes, pick_quotes]
    for quotes in all_quote_lists:
        markets.apply_cache(quotes, market_cache)
    markets.save_cache(cache_path, all_quote_lists)

    # Flag any sovereign-bond yield sitting at/above its danger threshold.
    for g in market_groups:
        markets.apply_bond_danger(g["quotes"], cfg.__dict__.get("BOND_DANGER", {}))

    flat = [q for quotes in all_quote_lists for q in quotes]
    live = sum(1 for q in flat if q.ok and not q.stale)
    stale = sum(1 for q in flat if q.stale)
    print("  %d live, %d from cache, %d/%d total resolved" % (
        live, stale, sum(1 for q in flat if q.ok), len(flat)))

    # Recession signal + gold-in-AUD from the yield curve / FX (no extra source).
    recession = _safe("recession", lambda: macro.recession_signal(flat), None)
    gold_aud = _safe("gold_aud", lambda: macro.gold_in_aud(flat), None)

    # Local weather, beach swell and fuel for the Port Stephens brief.
    wx = marine = fuel_info = None
    local = cfg.__dict__.get("LOCAL")
    if local:
        print("- Local weather / beach / fuel")
        wx = _safe("weather", lambda: weather.fetch_weather(
            local["lat"], local["lon"], timeout=timeout), None)
        marine = _safe("marine", lambda: weather.fetch_marine(
            local.get("beach_lat", local["lat"]), local.get("beach_lon", local["lon"]),
            timeout=timeout), None)
    fuel_cfg = cfg.__dict__.get("FUEL")
    if fuel_cfg:
        fuel_info = _safe("fuel", lambda: fuel.fetch_fuel(
            fuel_cfg.get("state", "NSW"), fuel_cfg.get("type", "U91"), timeout=timeout), None)

    # Price-sensitive ASX announcement flags (watchlist + mining watch).
    if cfg.__dict__.get("ANNOUNCEMENTS", {}).get("enabled"):
        print("- ASX announcements")
        asx_syms = [s for s, _ in cfg.WATCHLIST] + [s for s, _, _ in mw_cfg]
        flags = _safe("announcements", lambda: markets.fetch_announcements(
            asx_syms, cfg.ANNOUNCEMENTS.get("lookback_hours", 48), timeout=timeout), {})
        markets.apply_announcements(watchlist, flags)
        markets.apply_announcements(mw_quotes, flags)
        markets.apply_announcements(pick_quotes, flags)
        print("  %d price-sensitive flag(s)" % sum(1 for q in flat if q.sensitive))

    mining_watch = list(zip(mw_quotes, [r for _, _, r in mw_cfg]))

    print("- News: %d feeds" % len(cfg.NEWS_FEEDS))
    news_buckets = _safe("news", lambda: news.gather(
        cfg.NEWS_FEEDS,
        lookback_hours=cfg.SITE.get("news_lookback_hours", 30),
        per_category=cfg.SITE.get("max_news_per_category", 6),
        timeout=timeout,
        exclude_business=cfg.__dict__.get("NEWS_FILTER", {}).get("exclude_business"),
    ), {})
    n_stories = sum(len(v) for v in news_buckets.values())
    print("  %d stories across %d categories" % (n_stories, len(news_buckets)))

    highlights = _safe("highlights", lambda: news.pick_highlights(
        news_buckets, cfg.__dict__.get("NEWS_FILTER", {}).get("highlight_keywords"), 4), [])

    print("- Synthesis")
    synth = _safe("synthesis", lambda: synthesis.synthesize(
        cfg, market_groups, news_buckets, date_full),
        {"mood": "", "themes": [], "watch": [], "source": "fallback"})
    print("  source=%s, %d themes, %d watch items" % (
        synth.get("source"), len(synth.get("themes", [])), len(synth.get("watch", []))))

    ctx = {
        "title": cfg.SITE["title"],
        "tagline": cfg.SITE["tagline"],
        "owner": cfg.SITE["owner_name"],
        "greeting": _greeting(now_dt, cfg.SITE["owner_name"]),
        "date_full": date_full,
        "stamp": stamp,
        "now_dt": now_dt,
        "market_groups": market_groups,
        "synth": synth,
        "news_buckets": news_buckets,
        "categories": cfg.NEWS_CATEGORIES,
        "watchlist": watchlist,
        "mining_watch": mining_watch,
        "micro_pick": micro_pick,
        "gold_aud": gold_aud,
        "highlights": highlights,
        "weather": wx,
        "marine": marine,
        "fuel": fuel_info,
        "local": local,
        "hsc": cfg.__dict__.get("HSC_EXAM"),
        "recession": recession,
        "economy": cfg.__dict__.get("ECONOMY"),
    }

    print("- Rendering")
    page = render.render_page(ctx)

    os.makedirs(out_dir, exist_ok=True)
    archive_dir = os.path.join(out_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    index_path = os.path.join(out_dir, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(page)
    archive_path = os.path.join(archive_dir, "%s.html" % date_key)
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(page)

    # The brain-warmer: a self-contained Minesweeper page linked from the nav.
    with open(os.path.join(out_dir, "minesweeper.html"), "w", encoding="utf-8") as f:
        f.write(render.minesweeper_page(cfg.SITE["title"]))

    _write_pwa(out_dir, cfg.SITE["title"])
    _write_archive_index(archive_dir, cfg.SITE["title"])

    print("Done -> %s" % index_path)
    return index_path


def _icon_png(size):
    """A small PNG icon (dark bg + accent up-triangle) drawn with the stdlib —
    no image library. Used for the installable PWA / home-screen icon."""
    import struct
    import zlib
    bg = (0x14, 0x15, 0x1a, 255)
    fg = (0x46, 0xc0, 0x8a, 255)
    ax, ay = size / 2.0, size * 0.26
    blx, bly = size * 0.27, size * 0.74
    brx, bry = size * 0.73, size * 0.74

    def sign(x1, y1, x2, y2, x3, y3):
        return (x1 - x3) * (y2 - y3) - (x2 - x3) * (y1 - y3)

    def inside(x, y):
        d1 = sign(x, y, ax, ay, blx, bly)
        d2 = sign(x, y, blx, bly, brx, bry)
        d3 = sign(x, y, brx, bry, ax, ay)
        return not (((d1 < 0) or (d2 < 0) or (d3 < 0)) and ((d1 > 0) or (d2 > 0) or (d3 > 0)))

    raw = bytearray()
    for y in range(size):
        raw.append(0)                       # PNG filter byte per scanline
        for x in range(size):
            raw += bytes(fg if inside(x + 0.5, y + 0.5) else bg)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            chunk(b"IEND", b""))


def _write_pwa(out_dir, title):
    """Write the manifest, service worker and icons that make the dispatch an
    installable, offline-capable phone app. Best-effort — never fatal."""
    try:
        import json
        for size in (192, 512):
            with open(os.path.join(out_dir, "icon-%d.png" % size), "wb") as f:
                f.write(_icon_png(size))
        manifest = {
            "name": title, "short_name": "Dispatch",
            "start_url": ".", "scope": ".", "display": "standalone",
            "orientation": "portrait",
            "background_color": "#14151a", "theme_color": "#14151a",
            "description": "Chad's personal morning briefing.",
            "icons": [
                {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with open(os.path.join(out_dir, "sw.js"), "w", encoding="utf-8") as f:
            f.write(_SERVICE_WORKER)
    except Exception as e:
        print("  ! PWA assets failed: %s" % e)


_SERVICE_WORKER = """// Chad's Morning Dispatch — offline shell cache.
const C = 'mcd-v1';
const SHELL = ['./', './index.html', './minesweeper.html', './manifest.json', './icon-192.png'];
self.addEventListener('install', e => { e.waitUntil(caches.open(C).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener('activate', e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', e => {
  const r = e.request; if (r.method !== 'GET') return;
  if (new URL(r.url).hostname !== location.hostname) return;   // let live APIs hit the network
  e.respondWith(
    fetch(r).then(resp => { const cp = resp.clone(); caches.open(C).then(c => c.put(r, cp)); return resp; })
            .catch(() => caches.match(r).then(m => m || caches.match('./index.html')))
  );
});
"""


def _write_archive_index(archive_dir, title):
    files = sorted(glob.glob(os.path.join(archive_dir, "20*.html")), reverse=True)
    rows = []
    for path in files:
        name = os.path.basename(path)
        date_key = name[:-5]
        rows.append('<li><a href="{n}">{d}</a></li>'.format(n=render.esc(name), d=render.esc(date_key)))
    listing = "".join(rows) or '<li class="muted">No past editions yet.</li>'
    page = (
        '<!DOCTYPE html><html lang="en-AU"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark"><title>{title} — Archive</title>'
        '<style>{css}'
        'body{{padding:0}} .arch{{max-width:560px;margin:0 auto;padding:40px 20px}}'
        '.arch h1{{font-size:22px;margin:0 0 4px}} .arch p{{color:var(--ink-faint);margin:0 0 24px}}'
        '.arch ul{{list-style:none;padding:0;margin:0}}'
        '.arch li{{padding:12px 0;border-top:1px solid var(--line);font-size:16px;font-weight:600}}'
        '.arch a{{color:var(--ink)}} .arch a:hover{{color:var(--accent)}}'
        '.arch .muted{{color:var(--ink-faint);font-weight:400}}</style></head>'
        '<body><div class="arch"><h1>{title}</h1><p>Past editions</p>'
        '<p><a href="../index.html">&larr; Latest briefing</a></p><ul>{listing}</ul></div></body></html>'
    ).format(title=render.esc(title), css=render.CSS, listing=listing)
    with open(os.path.join(archive_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser(description="Build Chad's Morning Dispatch")
    ap.add_argument("--out", default="public", help="output directory (default: public)")
    args = ap.parse_args()
    try:
        build(args.out)
        return 0
    except Exception as e:
        print("FATAL: build failed: %s" % e, file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
