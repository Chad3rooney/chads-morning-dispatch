"""Render the gathered data into a single, self-contained, premium HTML page.

No template engine — just small composable functions returning HTML strings,
with everything dynamic passed through esc(). The output is fully static: it
loads instantly with zero external calls when opened.

Design goals: calm, premium, scannable. Light/dark via prefers-color-scheme.
Gains/losses are immediately obvious through colour + arrows.
"""

import html as _html


def esc(s):
    return _html.escape(str(s if s is not None else ""))


# --------------------------------------------------------------------------
# Number formatting
# --------------------------------------------------------------------------
def _decimals(value):
    av = abs(value)
    if av < 2:
        return 4
    if av < 20:
        return 3
    return 2


def fmt_price(q):
    if not q.ok:
        return "—"
    d = _decimals(q.price)
    return "{:,.{d}f}".format(q.price, d=d)


def fmt_change(q):
    if not q.ok:
        return ""
    d = _decimals(q.price)
    return "{:+,.{d}f}".format(q.change, d=d)


def fmt_pct(q):
    if not q.ok:
        return ""
    return "{:+.2f}%".format(q.pct)


_ARROW = {"up": "▲", "down": "▼", "flat": "•"}


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
def _quote_row(q):
    if not q.ok:
        return (
            '<div class="row muted">'
            '<span class="q-label">{label}</span>'
            '<span class="q-unavail">unavailable</span>'
            "</div>"
        ).format(label=esc(q.label))
    d = q.direction
    label = esc(q.label)
    if getattr(q, "stale", False):
        label += '<span class="q-asof" title="Last available data — live source was unreachable this run">as of {}</span>'.format(
            esc(q.as_of) if q.as_of else "earlier")
    return (
        '<div class="row{stale}">'
        '<span class="q-label">{label}</span>'
        '<span class="q-nums {dir}">'
        '<span class="q-price">{price}</span>'
        '<span class="q-chg">{arrow} {chg} <span class="q-pct">{pct}</span></span>'
        "</span></div>"
    ).format(
        label=label, dir=d, price=fmt_price(q),
        arrow=_ARROW[d], chg=esc(fmt_change(q)), pct=esc(fmt_pct(q)),
        stale=" is-stale" if getattr(q, "stale", False) else "",
    )


def _market_group(group):
    rows = "".join(_quote_row(q) for q in group["quotes"])
    note = '<span class="card-note">{}</span>'.format(esc(group["note"])) if group.get("note") else ""
    return (
        '<div class="market-card">'
        '<div class="card-head"><h3>{title}</h3>{note}</div>'
        '<div class="rows">{rows}</div>'
        "</div>"
    ).format(title=esc(group["title"]), note=note, rows=rows)


def market_snapshot(market_groups):
    cards = "".join(_market_group(g) for g in market_groups)
    return _section(
        "Market Snapshot", "section-markets",
        '<div class="market-grid">{}</div>'.format(cards),
    )


def themes_section(synth):
    if not synth.get("themes"):
        return ""
    items = []
    for i, t in enumerate(synth["themes"], 1):
        items.append(
            '<div class="theme">'
            '<div class="theme-num">{n}</div>'
            '<div class="theme-body"><h4>{title}</h4><p>{body}</p></div>'
            "</div>".format(n=i, title=esc(t.get("title", "")), body=esc(t.get("body", "")))
        )
    mood = ""
    if synth.get("mood"):
        mood = '<p class="mood">{}</p>'.format(esc(synth["mood"]))
    badge = "" if synth.get("source") == "claude" else \
        '<span class="badge-fallback" title="Generated without the AI synthesis layer">basic mode</span>'
    return _section(
        "Overnight Themes", "section-themes",
        mood + '<div class="themes">{}</div>'.format("".join(items)),
        extra_head=badge,
    )


def watch_section(synth):
    if not synth.get("watch"):
        return ""
    items = []
    for w in synth["watch"]:
        items.append(
            '<li><span class="watch-dot"></span>'
            '<span class="watch-text"><strong>{title}</strong>'
            '<span class="watch-detail">{detail}</span></span></li>'.format(
                title=esc(w.get("title", "")), detail=esc(w.get("detail", "")))
        )
    return _section(
        "What to Watch Today", "section-watch",
        '<ul class="watch-list">{}</ul>'.format("".join(items)),
    )


def _story(s):
    meta_bits = []
    if s.source:
        meta_bits.append(esc(s.source))
    if s.age:
        meta_bits.append(esc(s.age))
    meta = " · ".join(meta_bits)
    title_html = esc(s.title)
    if s.link:
        title_html = '<a href="{href}" target="_blank" rel="noopener">{t} <span class="ext">↗</span></a>'.format(
            href=esc(s.link), t=esc(s.title))
    summary = '<p class="story-sum">{}</p>'.format(esc(s.summary)) if s.summary else ""
    return (
        '<article class="story">'
        '<h4 class="story-title">{title}</h4>'
        "{summary}"
        '<div class="story-meta">{meta}</div>'
        "</article>"
    ).format(title=title_html, summary=summary, meta=meta)


def news_section(news_buckets, categories):
    blocks = []
    for c in categories:
        items = news_buckets.get(c["key"], [])
        if not items:
            continue
        stories = "".join(_story(s) for s in items)
        blocks.append(
            '<div class="news-cat">'
            '<h3 class="news-cat-title">{title}</h3>'
            '<div class="stories">{stories}</div>'
            "</div>".format(title=esc(c["title"]), stories=stories)
        )
    if not blocks:
        blocks.append('<p class="muted">No fresh stories cleared the threshold this run.</p>')
    return _section("News & Announcements", "section-news", "".join(blocks))


def watchlist_section(quotes):
    rows = []
    for q in quotes:
        if q.ok:
            name = esc(q.label)
            if getattr(q, "stale", False):
                name += '<span class="q-asof" title="Last available data">as of {}</span>'.format(
                    esc(q.as_of) if q.as_of else "earlier")
            rows.append(
                '<div class="wl-row {dir}{stale}">'
                '<span class="wl-name">{label}</span>'
                '<span class="wl-price">{price}</span>'
                '<span class="wl-chg">{arrow} {chg}</span>'
                '<span class="wl-pct">{pct}</span>'
                "</div>".format(
                    dir=q.direction, label=name, price=fmt_price(q),
                    arrow=_ARROW[q.direction], chg=esc(fmt_change(q)), pct=esc(fmt_pct(q)),
                    stale=" is-stale" if getattr(q, "stale", False) else "")
            )
        else:
            rows.append(
                '<div class="wl-row muted"><span class="wl-name">{label}</span>'
                '<span class="wl-unavail">unavailable</span></div>'.format(label=esc(q.label))
            )
    return _section(
        "Personal Watchlist", "section-watchlist",
        '<div class="watchlist">{}</div>'.format("".join(rows)),
    )


# --------------------------------------------------------------------------
# Shell
# --------------------------------------------------------------------------
def _section(title, anchor, body, extra_head=""):
    return (
        '<section class="section" id="{anchor}">'
        '<div class="section-head"><h2>{title}</h2>{extra}</div>'
        "{body}"
        "</section>"
    ).format(anchor=esc(anchor), title=esc(title), extra=extra_head, body=body)


def _market_status(now_dt):
    """Subtle open/closed pills based on AEST clock."""
    wd = now_dt.weekday()  # 0=Mon .. 6=Sun
    h = now_dt.hour + now_dt.minute / 60.0
    asx_open = (wd < 5) and (10.0 <= h < 16.0)
    asx = ("ASX open", "live") if asx_open else ("ASX closed", "closed")
    # US futures trade ~Sun 6pm ET to Fri 5pm ET; treat as live except a short
    # Sat window. Good enough for a subtle indicator.
    us_live = not (wd == 5)  # Saturday AEST ~ US closed
    us = ("US futures live", "live") if us_live else ("US futures closed", "closed")
    pills = ""
    for text, cls in (us, asx):
        pills += '<span class="pill {cls}"><span class="dot"></span>{text}</span>'.format(
            cls=cls, text=esc(text))
    return pills


def render_page(ctx):
    """ctx keys: greeting, date_full, time_str, stamp, now_dt, tagline,
    market_groups, synth, news_buckets, categories, watchlist, owner, title."""
    parts = [
        market_snapshot(ctx["market_groups"]),
        themes_section(ctx["synth"]),
        watch_section(ctx["synth"]),
        news_section(ctx["news_buckets"], ctx["categories"]),
        watchlist_section(ctx["watchlist"]),
    ]
    body = "".join(p for p in parts if p)
    status = _market_status(ctx["now_dt"])

    return PAGE_TEMPLATE.format(
        title=esc(ctx["title"]),
        greeting=esc(ctx["greeting"]),
        date_full=esc(ctx["date_full"]),
        tagline=esc(ctx["tagline"]),
        status=status,
        stamp=esc(ctx["stamp"]),
        body=body,
        css=CSS,
    )


# --------------------------------------------------------------------------
# Markup + styles
# --------------------------------------------------------------------------
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="mast-top">
      <span class="kicker">{title}</span>
      <div class="status">{status}</div>
    </div>
    <h1 class="greeting">{greeting}</h1>
    <p class="dateline">{date_full}</p>
    <p class="tagline">{tagline}</p>
  </header>
  <main>{body}</main>
  <footer class="foot">
    <p>Generated {stamp}. Static snapshot — figures reflect the moment of generation.</p>
    <p class="foot-fine">Market data via Yahoo Finance · News via public RSS feeds · Informational only, not financial advice.</p>
  </footer>
</div>
</body>
</html>"""


CSS = """
:root{
  --bg:#f6f4ef; --panel:#fffdf9; --ink:#1c1d22; --ink-soft:#54565f;
  --ink-faint:#8a8c95; --line:#e7e3da; --accent:#2f6f5e; --kicker:#9a6a3c;
  --up:#1c7d54; --down:#c0392b; --flat:#8a8c95; --shadow:0 1px 2px rgba(40,35,25,.06),0 8px 24px rgba(40,35,25,.05);
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#14151a; --panel:#1b1d24; --ink:#ecedf1; --ink-soft:#aab0bd;
    --ink-faint:#71757f; --line:#2a2d36; --accent:#56b399; --kicker:#cfa06a;
    --up:#46c08a; --down:#ef6b5c; --flat:#71757f; --shadow:0 1px 2px rgba(0,0,0,.3),0 10px 30px rgba(0,0,0,.25);
  }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,"Inter",sans-serif;
  line-height:1.55; font-size:16px; letter-spacing:.1px;
}
.wrap{max-width:880px; margin:0 auto; padding:32px 20px 64px}
a{color:var(--accent); text-decoration:none}
a:hover{text-decoration:underline}

/* Masthead */
.masthead{padding:8px 0 22px; border-bottom:1px solid var(--line); margin-bottom:28px}
.mast-top{display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap}
.kicker{font-size:12px; font-weight:700; letter-spacing:.16em; text-transform:uppercase; color:var(--kicker)}
.status{display:flex; gap:8px; flex-wrap:wrap}
.pill{display:inline-flex; align-items:center; gap:6px; font-size:11.5px; font-weight:600;
  color:var(--ink-soft); background:var(--panel); border:1px solid var(--line);
  border-radius:999px; padding:4px 10px}
.pill .dot{width:7px; height:7px; border-radius:50%; background:var(--flat)}
.pill.live .dot{background:var(--up)}
.pill.closed .dot{background:var(--ink-faint)}
.greeting{font-size:31px; line-height:1.15; margin:18px 0 4px; font-weight:760; letter-spacing:-.02em}
.dateline{margin:0; color:var(--ink-soft); font-size:15px; font-weight:600}
.tagline{margin:6px 0 0; color:var(--ink-faint); font-size:13.5px}

/* Sections */
.section{margin:34px 0}
.section-head{display:flex; align-items:baseline; gap:10px; margin:0 0 16px}
.section-head h2{font-size:13px; font-weight:750; letter-spacing:.13em; text-transform:uppercase;
  color:var(--ink-soft); margin:0; padding-bottom:0}
.badge-fallback{font-size:10.5px; font-weight:600; color:var(--ink-faint);
  border:1px solid var(--line); border-radius:6px; padding:1px 7px}

/* Market snapshot */
.market-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px}
.market-card{background:var(--panel); border:1px solid var(--line); border-radius:14px;
  padding:16px 16px 8px; box-shadow:var(--shadow)}
.card-head{display:flex; align-items:baseline; justify-content:space-between; margin-bottom:8px}
.card-head h3{font-size:14.5px; margin:0; font-weight:700}
.card-note{font-size:11px; color:var(--ink-faint)}
.rows{display:flex; flex-direction:column}
.row{display:flex; align-items:center; justify-content:space-between; gap:10px;
  padding:8px 0; border-top:1px solid var(--line)}
.row:first-child{border-top:none}
.q-label{font-size:14px; color:var(--ink-soft); font-weight:560}
.q-nums{display:flex; flex-direction:column; align-items:flex-end; line-height:1.25}
.q-price{font-variant-numeric:tabular-nums; font-weight:680; font-size:14.5px}
.q-chg{font-variant-numeric:tabular-nums; font-size:12px; font-weight:620}
.q-pct{opacity:.92}
.q-nums.up{color:var(--up)} .q-nums.down{color:var(--down)} .q-nums.flat{color:var(--flat)}
.q-nums.up .q-price,.q-nums.down .q-price,.q-nums.flat .q-price{color:var(--ink)}
.q-unavail,.wl-unavail{font-size:12px; color:var(--ink-faint); font-style:italic}
.row.muted .q-label{color:var(--ink-faint)}
.q-asof{display:block; font-size:10px; font-weight:500; color:var(--ink-faint);
  letter-spacing:.02em; margin-top:1px}
.is-stale .q-price,.is-stale .wl-price{opacity:.82}

/* Themes */
.mood{font-size:16.5px; color:var(--ink); margin:0 0 18px; font-weight:560;
  padding-left:14px; border-left:3px solid var(--accent)}
.themes{display:flex; flex-direction:column; gap:4px}
.theme{display:flex; gap:14px; padding:14px 0; border-top:1px solid var(--line)}
.theme:first-child{border-top:none}
.theme-num{flex:none; width:26px; height:26px; border-radius:50%; background:var(--accent);
  color:#fff; font-size:13px; font-weight:700; display:flex; align-items:center; justify-content:center}
.theme-body h4{margin:2px 0 4px; font-size:16px; font-weight:700}
.theme-body p{margin:0; color:var(--ink-soft); font-size:14.5px}

/* Watch */
.watch-list{list-style:none; margin:0; padding:0; display:grid;
  grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px}
.watch-list li{display:flex; gap:11px; align-items:flex-start; background:var(--panel);
  border:1px solid var(--line); border-radius:12px; padding:13px 14px; box-shadow:var(--shadow)}
.watch-dot{flex:none; width:8px; height:8px; border-radius:50%; background:var(--kicker); margin-top:7px}
.watch-text{display:flex; flex-direction:column; gap:2px}
.watch-text strong{font-size:14.5px; font-weight:680}
.watch-detail{font-size:13px; color:var(--ink-soft)}

/* News */
.news-cat{margin-bottom:26px}
.news-cat-title{font-size:15px; font-weight:730; margin:0 0 10px; padding-bottom:8px;
  border-bottom:2px solid var(--line); color:var(--ink)}
.stories{display:flex; flex-direction:column; gap:2px}
.story{padding:13px 0; border-top:1px solid var(--line)}
.story:first-child{border-top:none}
.story-title{margin:0 0 4px; font-size:15.5px; font-weight:640; line-height:1.35}
.story-title a{color:var(--ink)}
.story-title a:hover{color:var(--accent)}
.ext{font-size:11px; color:var(--ink-faint); font-weight:400}
.story-sum{margin:0 0 5px; color:var(--ink-soft); font-size:14px; line-height:1.5}
.story-meta{font-size:11.5px; color:var(--ink-faint); font-weight:600; letter-spacing:.02em; text-transform:uppercase}

/* Watchlist */
.watchlist{background:var(--panel); border:1px solid var(--line); border-radius:14px;
  overflow:hidden; box-shadow:var(--shadow)}
.wl-row{display:grid; grid-template-columns:1fr auto auto auto; gap:12px; align-items:center;
  padding:11px 16px; border-top:1px solid var(--line)}
.wl-row:first-child{border-top:none}
.wl-name{font-weight:600; font-size:14.5px}
.wl-price{font-variant-numeric:tabular-nums; font-weight:680; text-align:right}
.wl-chg,.wl-pct{font-variant-numeric:tabular-nums; font-size:13px; font-weight:620; text-align:right; min-width:62px}
.wl-row.up .wl-chg,.wl-row.up .wl-pct{color:var(--up)}
.wl-row.down .wl-chg,.wl-row.down .wl-pct{color:var(--down)}
.wl-row.flat .wl-chg,.wl-row.flat .wl-pct{color:var(--flat)}
.wl-row.muted{grid-template-columns:1fr auto}

/* Footer */
.foot{margin-top:48px; padding-top:20px; border-top:1px solid var(--line);
  color:var(--ink-faint); font-size:12.5px}
.foot p{margin:0 0 5px}
.foot-fine{font-size:11.5px}

@media (max-width:520px){
  .wrap{padding:22px 15px 48px}
  .greeting{font-size:26px}
  .market-grid{grid-template-columns:1fr}
  .wl-row{grid-template-columns:1fr auto auto; row-gap:2px}
  .wl-pct{display:none}
}
"""
