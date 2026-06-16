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
from dispatch import markets, news, synthesis, render, timeutil


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

    print("- Markets: snapshot groups")
    market_groups = _safe(
        "markets", lambda: markets.fetch_market_groups(cfg.MARKET_GROUPS, timeout=timeout), [])
    ok = sum(1 for g in market_groups for q in g["quotes"] if q.ok)
    total = sum(len(g["quotes"]) for g in market_groups)
    print("  %d/%d quotes resolved" % (ok, total))

    print("- Markets: watchlist")
    watchlist = _safe(
        "watchlist", lambda: markets.fetch_quotes(cfg.WATCHLIST, timeout=timeout), [])

    print("- News: %d feeds" % len(cfg.NEWS_FEEDS))
    news_buckets = _safe("news", lambda: news.gather(
        cfg.NEWS_FEEDS,
        lookback_hours=cfg.SITE.get("news_lookback_hours", 30),
        per_category=cfg.SITE.get("max_news_per_category", 6),
        timeout=timeout,
    ), {})
    n_stories = sum(len(v) for v in news_buckets.values())
    print("  %d stories across %d categories" % (n_stories, len(news_buckets)))

    print("- Synthesis")
    synth = _safe("synthesis", lambda: synthesis.synthesize(
        cfg, market_groups, news_buckets, date_full),
        {"mood": "", "themes": [], "watch": [], "source": "fallback"})
    print("  source=%s, %d themes, %d watch items" % (
        synth.get("source"), len(synth.get("themes", [])), len(synth.get("watch", []))))

    ctx = {
        "title": cfg.SITE["title"],
        "tagline": cfg.SITE["tagline"],
        "greeting": _greeting(now_dt, cfg.SITE["owner_name"]),
        "date_full": date_full,
        "stamp": stamp,
        "now_dt": now_dt,
        "market_groups": market_groups,
        "synth": synth,
        "news_buckets": news_buckets,
        "categories": cfg.NEWS_CATEGORIES,
        "watchlist": watchlist,
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

    _write_archive_index(archive_dir, cfg.SITE["title"])

    print("Done -> %s" % index_path)
    return index_path


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
