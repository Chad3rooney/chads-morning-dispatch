"""Render the gathered data into a single, self-contained, premium HTML page.

No template engine — just small composable functions returning HTML strings,
with everything dynamic passed through esc(). The output is fully static: it
loads instantly with zero external calls when opened.

Design goals: calm, premium, scannable. A real light/dark toggle (with a system
default and no flash-of-wrong-theme), sticky section nav, day-range micro-bars,
a top-movers strip, and clear colour + arrows for every gain/loss.
"""

import html as _html

from . import markets as _markets


def esc(s):
    return _html.escape(str(s if s is not None else ""))


def _live_attr(q):
    """data-sym for client-side live refresh (skipped for non-CNBC quotes)."""
    if getattr(q, "no_live", False) or not q.ok:
        return ""
    return ' data-sym="{}"'.format(esc(_markets.CNBC_MAP.get(q.symbol, q.symbol)))


def _sensitive_mark(q):
    if getattr(q, "sensitive", False):
        return '<span class="sens" title="{}">&#42;</span>'.format(
            esc(q.sensitive_note or "Price-sensitive announcement"))
    return ""


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


def _fmt(value, ref=None):
    if value is None:
        return "—"
    return "{:,.{d}f}".format(value, d=_decimals(ref if ref is not None else value))


def fmt_price(q):
    return _fmt(q.price) if q.ok else "—"


def fmt_change(q):
    if not q.ok:
        return ""
    return "{:+,.{d}f}".format(q.change, d=_decimals(q.price))


def fmt_pct(q):
    return "{:+.2f}%".format(q.pct) if q.ok else ""


_ARROW = {"up": "▲", "down": "▼", "flat": "•"}


# --------------------------------------------------------------------------
# Market snapshot
# --------------------------------------------------------------------------
def _range_bar(q):
    """A thin day low–high track with a dot at the last price. Empty when the
    instrument has no usable intraday band (e.g. iron ore, bond yields)."""
    pos = q.day_range_pct
    if pos is None:
        return '<span class="range range--none"></span>'
    title = "Day range: %s – %s" % (_fmt(q.day_low, q.price), _fmt(q.day_high, q.price))
    return (
        '<span class="range {dir}" title="{title}">'
        '<span class="range-track"><span class="range-dot" style="left:{pos:.1f}%"></span></span>'
        "</span>"
    ).format(dir=q.direction, title=esc(title), pos=pos)


def _quote_row(q):
    if not q.ok:
        return (
            '<div class="row muted">'
            '<span class="q-label">{label}</span>'
            '<span class="q-unavail">unavailable</span>'
            "</div>"
        ).format(label=esc(q.label))
    asof = ""
    if getattr(q, "stale", False):
        asof = '<span class="q-asof" title="Last available data — live source unreachable this run">as of {}</span>'.format(
            esc(q.as_of) if q.as_of else "earlier")
    return (
        '<div class="row {dir}{stale}"{live} data-pct="{pctv}">'
        '<div class="row-top"><span class="q-label">{label}{sens}{asof}</span>'
        '<span class="q-price">{price}</span></div>'
        '<div class="row-bot">{bar}'
        '<span class="q-chg">{arrow} {chg} <span class="q-pct">{pct}</span></span></div>'
        "</div>"
    ).format(
        dir=q.direction, stale=" is-stale" if getattr(q, "stale", False) else "",
        live=_live_attr(q), pctv=("%.4f" % q.pct) if q.ok else "",
        label=esc(q.label), sens=_sensitive_mark(q), asof=asof,
        price=fmt_price(q), bar=_range_bar(q),
        arrow=_ARROW[q.direction], chg=esc(fmt_change(q)), pct=esc(fmt_pct(q)),
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


def _movers_strip(market_groups):
    """Auto-highlight the biggest movers across the whole snapshot."""
    quotes = [q for g in market_groups for q in g["quotes"] if q.ok and abs(q.pct) >= 0.05]
    quotes.sort(key=lambda q: abs(q.pct), reverse=True)
    if not quotes:
        return ""
    chips = []
    for q in quotes[:6]:
        chips.append(
            '<span class="mover {dir}"><span class="mover-name">{label}</span>'
            '<span class="mover-pct">{arrow} {pct}</span></span>'.format(
                dir=q.direction, label=esc(q.label), arrow=_ARROW[q.direction], pct=esc(fmt_pct(q)))
        )
    return '<div class="movers"><span class="movers-label">Big movers</span>{chips}</div>'.format(
        chips="".join(chips))


def market_snapshot(market_groups):
    if not market_groups:
        return ""
    all_q = [q for g in market_groups for q in g["quotes"] if q.ok]
    up = sum(1 for q in all_q if q.direction == "up")
    down = sum(1 for q in all_q if q.direction == "down")
    breadth = ""
    if all_q:
        breadth = '<span class="breadth" id="breadth"><span class="up">{u}↑</span> <span class="down">{d}↓</span></span>'.format(
            u=up, d=down)
    live = ('<span class="live-ind" id="live-ind" hidden>'
            '<span class="live-pulse"></span><span class="live-text">live</span></span>')
    cards = "".join(_market_group(g) for g in market_groups)
    body = '<div class="movers-wrap" id="movers">{}</div>'.format(_movers_strip(market_groups)) \
        + '<div class="market-grid">{}</div>'.format(cards)
    return _section("Market Snapshot", "section-markets", body, extra_head=breadth + live)


# --------------------------------------------------------------------------
# Themes + Watch
# --------------------------------------------------------------------------
def themes_section(synth):
    if not synth.get("themes"):
        return ""
    items = []
    for i, t in enumerate(synth["themes"], 1):
        kicker = '<span class="theme-kicker">{}</span>'.format(esc(t["kicker"])) if t.get("kicker") else ""
        items.append(
            '<div class="theme">'
            '<div class="theme-num">{n}</div>'
            '<div class="theme-body">{kicker}<h4>{title}</h4><p>{body}</p></div>'
            "</div>".format(n=i, kicker=kicker, title=esc(t.get("title", "")), body=esc(t.get("body", "")))
        )
    mood = '<p class="mood">{}</p>'.format(esc(synth["mood"])) if synth.get("mood") else ""
    badge = "" if synth.get("source") == "claude" else \
        '<span class="badge-fallback" title="AI synthesis layer is off (no API key) — using the rule-based writer">basic mode</span>'
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


# --------------------------------------------------------------------------
# News
# --------------------------------------------------------------------------
def _story(s, lead=False):
    meta_bits = []
    if s.source:
        meta_bits.append('<span class="src">{}</span>'.format(esc(s.source)))
    if s.age:
        meta_bits.append('<span class="age">{}</span>'.format(esc(s.age)))
    meta = "".join(meta_bits)
    title = esc(s.title)
    if s.link:
        title = '<a href="{href}" target="_blank" rel="noopener">{t}<span class="ext">↗</span></a>'.format(
            href=esc(s.link), t=esc(s.title))
    summary = '<p class="story-sum">{}</p>'.format(esc(s.summary)) if s.summary else ""
    return (
        '<article class="story{lead}">'
        '<h4 class="story-title">{title}</h4>'
        "{summary}"
        '<div class="story-meta">{meta}</div>'
        "</article>"
    ).format(lead=" story--lead" if lead else "", title=title, summary=summary, meta=meta)


def news_section(news_buckets, categories):
    blocks = []
    for c in categories:
        items = news_buckets.get(c["key"], [])
        if not items:
            continue
        stories = "".join(_story(s, lead=(i == 0)) for i, s in enumerate(items))
        blocks.append(
            '<div class="news-cat">'
            '<h3 class="news-cat-title">{title}<span class="news-count">{n}</span></h3>'
            '<div class="stories">{stories}</div>'
            "</div>".format(title=esc(c["title"]), n=len(items), stories=stories)
        )
    if not blocks:
        return ""
    return _section("News & Announcements", "section-news",
                    '<div class="news-grid">{}</div>'.format("".join(blocks)))


# --------------------------------------------------------------------------
# Watchlist
# --------------------------------------------------------------------------
def watchlist_section(quotes):
    if not quotes:
        return ""
    rows = []
    for q in quotes:
        if q.ok:
            name = esc(q.label) + _sensitive_mark(q)
            if getattr(q, "stale", False):
                name += '<span class="q-asof" title="Last available data">as of {}</span>'.format(
                    esc(q.as_of) if q.as_of else "earlier")
            rows.append(
                '<div class="wl-row {dir}{stale}"{live}>'
                '<span class="wl-name">{label}</span>'
                '<span class="wl-price">{price}</span>'
                '<span class="wl-chg">{arrow} {chg}</span>'
                '<span class="wl-pct">{pct}</span>'
                "</div>".format(
                    dir=q.direction, label=name, price=fmt_price(q), live=_live_attr(q),
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
# Economy & Rates — recession gauge, policy rates, housing
# --------------------------------------------------------------------------
def _recession_card(rec):
    if not rec:
        return ""
    return (
        '<div class="eco-card recession {level}">'
        '<div class="eco-head"><h3>Recession risk</h3>'
        '<span class="rec-label">{label}</span></div>'
        '<div class="gauge"><div class="gauge-track"></div>'
        '<div class="gauge-marker" style="left:{gauge:.0f}%"></div></div>'
        '<div class="gauge-scale"><span>Low</span><span>Elevated</span></div>'
        '<p class="eco-detail">{detail}</p>'
        '<p class="eco-fine">US 2Y {y2:.2f}% · US 10Y {y10:.2f}% · yield-curve signal</p>'
        "</div>"
    ).format(level=esc(rec["level"]), label=esc(rec["label"]), gauge=rec["gauge"],
             detail=esc(rec["detail"]), y2=rec["y2"], y10=rec["y10"])


def _policy_card(economy):
    rates = (economy or {}).get("policy_rates") or []
    if not rates:
        return ""
    items = "".join(
        '<div class="rate-row"><span class="rate-name">{n}</span>'
        '<span class="rate-val">{v}</span>'
        '<span class="rate-note">{note}</span></div>'.format(
            n=esc(r.get("name", "")), v=esc(r.get("value", "")), note=esc(r.get("note", "")))
        for r in rates)
    return ('<div class="eco-card"><div class="eco-head"><h3>Central bank rates</h3></div>'
            '<div class="rate-list">{}</div></div>'.format(items))


def _housing_card(economy):
    h = (economy or {}).get("housing") or {}
    rows = h.get("rows") or []
    if not rows:
        return ""
    items = "".join(
        '<div class="rate-row"><span class="rate-name">{n}</span>'
        '<span class="rate-val">{v}</span>'
        '<span class="rate-note">{c}</span></div>'.format(
            n=esc(r.get("name", "")), v=esc(r.get("value", "")), c=esc(r.get("change", "")))
        for r in rows)
    asat = '<span class="card-note">{}</span>'.format(esc(h.get("as_at", ""))) if h.get("as_at") else ""
    return ('<div class="eco-card"><div class="eco-head"><h3>AU housing</h3>{asat}</div>'
            '<div class="rate-list">{items}</div></div>'.format(asat=asat, items=items))


def economy_section(recession, economy):
    cards = "".join(c for c in (
        _recession_card(recession), _policy_card(economy), _housing_card(economy)) if c)
    if not cards:
        return ""
    return _section("Economy & Rates", "section-economy",
                    '<div class="eco-grid">{}</div>'.format(cards))


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
    """Server-rendered open/closed pills (a no-JS fallback for generation time).

    These are recomputed live in the browser from the viewer's current AEST
    clock — see SCRIPTS — because the page is a static morning snapshot and the
    real market status changes through the day after it's built.
    """
    wd = now_dt.weekday()
    h = now_dt.hour + now_dt.minute / 60.0
    asx_open = (wd < 5) and (10.0 <= h < 16.0)
    asx = ("ASX open", "live") if asx_open else ("ASX closed", "closed")
    us_live = not (wd == 5)
    us = ("US futures live", "live") if us_live else ("US futures closed", "closed")
    pills = ""
    for text, cls in (us, asx):
        pills += '<span class="pill {cls}"><span class="dot"></span>{text}</span>'.format(
            cls=cls, text=esc(text))
    return pills


def _reading_time(ctx):
    words = 0
    for t in ctx["synth"].get("themes", []):
        words += len((t.get("title", "") + " " + t.get("body", "")).split())
    for items in ctx["news_buckets"].values():
        for s in items:
            words += len(((s.title or "") + " " + (s.summary or "")).split())
    return max(3, round(words / 200.0))


def render_page(ctx):
    sections = [
        market_snapshot(ctx["market_groups"]),
        themes_section(ctx["synth"]),
        watch_section(ctx["synth"]),
        economy_section(ctx.get("recession"), ctx.get("economy")),
        news_section(ctx["news_buckets"], ctx["categories"]),
        watchlist_section(ctx["watchlist"]),
    ]
    nav_meta = [
        ("section-markets", "Markets"), ("section-themes", "Overnight"),
        ("section-watch", "Watch"), ("section-economy", "Economy"),
        ("section-news", "News"), ("section-watchlist", "Watchlist"),
    ]
    present = {s.split('id="', 1)[1].split('"', 1)[0] for s in sections if s}
    nav_links = "".join(
        '<a href="#{i}">{l}</a>'.format(i=i, l=esc(l)) for i, l in nav_meta if i in present)
    body = "".join(s for s in sections if s)
    short = esc(ctx["title"].split("'")[0] if "'" in ctx["title"] else ctx["title"])

    return PAGE_TEMPLATE.format(
        title=esc(ctx["title"]),
        short=short,
        greeting=esc(ctx["greeting"]),
        date_full=esc(ctx["date_full"]),
        tagline=esc(ctx["tagline"]),
        status=_market_status(ctx["now_dt"]),
        mood=esc(ctx["synth"].get("mood", "")),
        read=_reading_time(ctx),
        nav_links=nav_links,
        stamp=esc(ctx["stamp"]),
        body=body,
        css=CSS,
        scripts=SCRIPTS,
    )


# --------------------------------------------------------------------------
# Markup
# --------------------------------------------------------------------------
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{title}</title>
<script>try{{var t=localStorage.getItem('mcd-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}</script>
<style>{css}</style>
</head>
<body>
<a id="top"></a>
<nav class="topnav">
  <a class="nav-brand" href="#top">{short}</a>
  <div class="nav-links">{nav_links}</div>
  <a class="nav-game" href="minesweeper.html" title="Warm the brain up">&#9819; Minesweeper</a>
  <button id="theme-btn" class="theme-btn" type="button" aria-label="Toggle light or dark theme">
    <span class="t-icon"></span><span class="t-label"></span>
  </button>
</nav>
<div class="wrap">
  <header class="masthead">
    <div class="mast-top">
      <span class="kicker">{title}</span>
      <div class="status" id="market-status">{status}</div>
    </div>
    <h1 class="greeting">{greeting}</h1>
    <p class="dateline">{date_full} <span class="read">· {read} min read</span></p>
    <p class="tagline">{tagline}</p>
    <p class="mast-mood">{mood}</p>
  </header>
  <main>{body}</main>
  <footer class="foot">
    <div class="foot-nav">{nav_links}</div>
    <p>Built {stamp}. Market prices refresh live in your browser; news, themes and the economy figures are this morning's snapshot.</p>
    <p class="foot-fine">Markets via CNBC &amp; Yahoo Finance · ASX data via ASX/Markit · News via public RSS feeds · Informational only, not financial advice.</p>
  </footer>
</div>
{scripts}
</body>
</html>"""


SCRIPTS = """<script>
(function(){
  // --- Live market-status pills (recomputed from the viewer's AEST clock) ---
  // The page is a static morning snapshot, so the baked-in status goes stale
  // during the day. Recompute it locally — no network, still fully static.
  function updateStatus(){
    var el = document.getElementById('market-status');
    if (!el) return;
    var syd;
    try { syd = new Date(new Date().toLocaleString('en-US', {timeZone:'Australia/Sydney'})); }
    catch(e){ return; }                       // leave the server fallback in place
    var wd = syd.getDay();                     // 0=Sun .. 6=Sat
    var h = syd.getHours() + syd.getMinutes()/60;
    var asxOpen = wd >= 1 && wd <= 5 && h >= 10 && h < 16;            // 10:00–16:00 Syd, Mon–Fri
    var usLive  = !(wd === 6 || wd === 0 || (wd === 1 && h < 8));      // CME equity futures ~Mon 8am–Sat Syd
    var pills = [
      [usLive ? 'US futures live' : 'US futures closed', usLive ? 'live' : 'closed'],
      [asxOpen ? 'ASX open' : 'ASX closed', asxOpen ? 'live' : 'closed']
    ];
    el.innerHTML = pills.map(function(p){
      return '<span class="pill ' + p[1] + '"><span class="dot"></span>' + p[0] + '</span>';
    }).join('');
  }
  updateStatus();
  setInterval(updateStatus, 60000);            // keep it correct if the page stays open

  var btn = document.getElementById('theme-btn');
  function effective(){
    var set = document.documentElement.getAttribute('data-theme');
    if (set) return set;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light';
  }
  function paint(){
    var e = effective();
    btn.querySelector('.t-icon').textContent = e === 'dark' ? '☀' : '☾';
    btn.querySelector('.t-label').textContent = e === 'dark' ? 'Light' : 'Dark';
  }
  btn.addEventListener('click', function(){
    var next = effective() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('mcd-theme', next); } catch(e){}
    paint();
  });
  // Keep the button in sync if the OS theme flips while no manual choice is set.
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change', function(){
      if (!document.documentElement.getAttribute('data-theme')) paint();
    });
  }
  paint();

  // --- Live prices (progressive enhancement) -------------------------------
  // The page ships with cached values so it loads instantly, then refreshes
  // from CNBC's CORS-enabled quote API every minute. When a market is shut,
  // CNBC's "last" is that market's previous close — so you always see the most
  // recent real result, live whenever you open the page.
  var CNBC = 'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?requestMethod=itv&fund=1&exthrs=1&output=json&symbols=';
  function dec(v){ v = Math.abs(v); return v < 2 ? 4 : (v < 20 ? 3 : 2); }
  function fnum(v, ref){ var d = dec(ref==null?v:ref); return v.toLocaleString('en-AU',{minimumFractionDigits:d, maximumFractionDigits:d}); }
  function fchg(v, ref){ return (v>=0?'+':'') + fnum(v, ref); }
  function fpct(v){ return (v>=0?'+':'') + v.toFixed(2) + '%'; }
  function parseNum(s){ if(s==null) return null; var n=parseFloat(String(s).replace(/[,%]/g,'')); return isNaN(n)?null:n; }

  function flash(el, dir){
    var c = dir==='up'?'flash-up':(dir==='down'?'flash-down':null);
    if(!c) return; el.classList.add(c); setTimeout(function(){ el.classList.remove(c); }, 800);
  }
  function applyRow(el, last, chg, hi, lo){
    if(last==null) return;
    if(chg==null) chg = 0;                       // CNBC "UNCH"
    var prev = last - chg, pct = prev? chg/prev*100 : 0;
    var dir = chg>0?'up':(chg<0?'down':'flat'), arrow = dir==='up'?'▲':(dir==='down'?'▼':'•');
    var wl = el.classList.contains('wl-row');
    el.classList.remove('up','down','flat','is-stale'); el.classList.add(dir);
    el.setAttribute('data-pct', pct.toFixed(4));
    var pe = el.querySelector(wl?'.wl-price':'.q-price');
    if(pe){ var old=pe.textContent; var nv=fnum(last,last); if(old!==nv){ pe.textContent=nv; flash(el,dir);} }
    if(wl){
      var c=el.querySelector('.wl-chg'); if(c) c.textContent=arrow+' '+fchg(chg,last);
      var p=el.querySelector('.wl-pct'); if(p) p.textContent=fpct(pct);
    } else {
      var c2=el.querySelector('.q-chg'); if(c2) c2.innerHTML=arrow+' '+fchg(chg,last)+' <span class="q-pct">'+fpct(pct)+'</span>';
      if(hi!=null && lo!=null && hi>lo){
        var dot=el.querySelector('.range-dot'), rg=el.querySelector('.range');
        if(dot) dot.style.left=Math.max(0,Math.min(100,(last-lo)/(hi-lo)*100)).toFixed(1)+'%';
        if(rg){ rg.classList.remove('up','down','flat','range--none'); rg.classList.add(dir); }
      }
      var as=el.querySelector('.q-asof'); if(as) as.remove();
    }
  }
  function refresh(){
    var up=0, down=0, movers=[];
    document.querySelectorAll('.market-grid .row').forEach(function(r){
      var pct=parseFloat(r.getAttribute('data-pct')); if(isNaN(pct)) return;
      if(r.classList.contains('up')) up++; else if(r.classList.contains('down')) down++;
      var lab=r.querySelector('.q-label'); lab = lab? (lab.childNodes[0]?lab.childNodes[0].textContent:lab.textContent).trim():'';
      movers.push({label:lab, pct:pct, dir:r.classList.contains('up')?'up':(r.classList.contains('down')?'down':'flat')});
    });
    var b=document.getElementById('breadth'); if(b) b.innerHTML='<span class="up">'+up+'\\u2191</span> <span class="down">'+down+'\\u2193</span>';
    movers.sort(function(a,b){return Math.abs(b.pct)-Math.abs(a.pct);});
    var top=movers.filter(function(m){return Math.abs(m.pct)>=0.05;}).slice(0,6);
    var mv=document.getElementById('movers');
    if(mv && top.length){
      mv.innerHTML='<div class="movers"><span class="movers-label">Big movers</span>'+top.map(function(m){
        var a=m.dir==='up'?'▲':(m.dir==='down'?'▼':'•');
        return '<span class="mover '+m.dir+'"><span class="mover-name">'+m.label+'</span><span class="mover-pct">'+a+' '+fpct(m.pct)+'</span></span>';
      }).join('')+'</div>';
    }
  }
  function chunks(arr,n){ var o=[]; for(var i=0;i<arr.length;i+=n) o.push(arr.slice(i,i+n)); return o; }
  function updateQuotes(){
    var els=[].slice.call(document.querySelectorAll('[data-sym]'));
    if(!els.length || !window.fetch) return;
    var symMap={}; els.forEach(function(e){ (symMap[e.getAttribute('data-sym')]=symMap[e.getAttribute('data-sym')]||[]).push(e); });
    var syms=Object.keys(symMap);
    Promise.all(chunks(syms,40).map(function(ch){
      return fetch(CNBC+ch.join('%7C')).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;});
    })).then(function(results){
      var got=0;
      results.forEach(function(d){
        var list=d&&d.FormattedQuoteResult&&d.FormattedQuoteResult.FormattedQuote;
        if(!list) return;
        list.forEach(function(q){
          if(String(q.code)!=='0') return;
          var els=symMap[q.symbol]; if(!els) return; got++;
          els.forEach(function(el){ applyRow(el, parseNum(q.last), parseNum(q.change), parseNum(q.high), parseNum(q.low)); });
        });
      });
      if(got){ refresh(); var ind=document.getElementById('live-ind');
        if(ind){ ind.hidden=false; var t=new Date().toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit'}); ind.querySelector('.live-text').textContent='live · '+t; } }
    });
  }
  updateQuotes();
  setInterval(updateQuotes, 60000);
})();
</script>"""


# --------------------------------------------------------------------------
# Styles — light defaults; dark via [data-theme] or system preference
# --------------------------------------------------------------------------
_DARK_VARS = """
  --bg:#121317; --bg-2:#15171d; --panel:#1b1d24; --panel-2:#21242c;
  --ink:#eef0f4; --ink-soft:#aab0bd; --ink-faint:#787d89; --line:#292c35;
  --accent:#5cb9a0; --accent-soft:#1e3b35; --kicker:#d2a36c;
  --up:#49c98f; --down:#f06d5d; --flat:#787d89;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 12px 32px rgba(0,0,0,.30);
"""

CSS = ("""
:root{
  --bg:#f4f2ec; --bg-2:#efece4; --panel:#fffdf9; --panel-2:#faf7f0;
  --ink:#1b1c21; --ink-soft:#52545d; --ink-faint:#8b8d97; --line:#e7e2d8;
  --accent:#2f6f5e; --accent-soft:#e3efe9; --kicker:#9a6a3c;
  --up:#1c7d54; --down:#c0392b; --flat:#8b8d97;
  --shadow:0 1px 2px rgba(40,35,25,.06),0 8px 24px rgba(40,35,25,.05);
}
[data-theme="dark"]{""" + _DARK_VARS + """}
@media (prefers-color-scheme:dark){:root:not([data-theme]){""" + _DARK_VARS + """}}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%; scroll-behavior:smooth}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,"Inter",sans-serif;
  line-height:1.55; font-size:16px; letter-spacing:.1px;
  transition:background .25s ease, color .25s ease;
}
.wrap{max-width:960px; margin:0 auto; padding:26px 20px 64px}
a{color:var(--accent); text-decoration:none}
a:hover{text-decoration:underline}
.section{scroll-margin-top:64px}

/* Sticky nav */
.topnav{position:sticky; top:0; z-index:50; display:flex; align-items:center; gap:14px;
  padding:9px 20px; background:color-mix(in srgb, var(--bg) 86%, transparent);
  -webkit-backdrop-filter:saturate(160%) blur(12px); backdrop-filter:saturate(160%) blur(12px);
  border-bottom:1px solid var(--line)}
.nav-brand{font-weight:800; font-size:13px; letter-spacing:.04em; color:var(--ink); flex:none}
.nav-links{display:flex; gap:4px; overflow-x:auto; flex:1; scrollbar-width:none}
.nav-links::-webkit-scrollbar{display:none}
.nav-links a{font-size:12.5px; font-weight:600; color:var(--ink-soft); padding:5px 10px;
  border-radius:8px; white-space:nowrap}
.nav-links a:hover{color:var(--ink); background:var(--panel-2); text-decoration:none}
.theme-btn{flex:none; display:inline-flex; align-items:center; gap:6px; cursor:pointer;
  font:inherit; font-size:12.5px; font-weight:600; color:var(--ink-soft);
  background:var(--panel); border:1px solid var(--line); border-radius:999px; padding:5px 12px;
  transition:color .2s, border-color .2s}
.theme-btn:hover{color:var(--ink); border-color:var(--ink-faint)}
.theme-btn .t-icon{font-size:13px; line-height:1}
.nav-game{flex:none; font-size:12.5px; font-weight:700; color:#fff;
  background:linear-gradient(135deg,var(--accent),color-mix(in srgb,var(--accent) 60%,var(--kicker)));
  border-radius:999px; padding:6px 13px; white-space:nowrap; box-shadow:var(--shadow)}
.nav-game:hover{text-decoration:none; filter:brightness(1.08); transform:translateY(-1px)}

/* Masthead */
.masthead{padding:24px 0 22px; border-bottom:1px solid var(--line); margin-bottom:26px}
.mast-top{display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap}
.kicker{font-size:12px; font-weight:700; letter-spacing:.16em; text-transform:uppercase; color:var(--kicker)}
.status{display:flex; gap:8px; flex-wrap:wrap}
.pill{display:inline-flex; align-items:center; gap:6px; font-size:11.5px; font-weight:600;
  color:var(--ink-soft); background:var(--panel); border:1px solid var(--line); border-radius:999px; padding:4px 10px}
.pill .dot{width:7px; height:7px; border-radius:50%; background:var(--flat)}
.pill.live .dot{background:var(--up); box-shadow:0 0 0 3px color-mix(in srgb,var(--up) 22%,transparent)}
.pill.closed .dot{background:var(--ink-faint)}
.greeting{font-size:33px; line-height:1.12; margin:18px 0 6px; font-weight:780; letter-spacing:-.022em}
.dateline{margin:0; color:var(--ink-soft); font-size:15px; font-weight:600}
.dateline .read{color:var(--ink-faint); font-weight:500}
.tagline{margin:7px 0 0; color:var(--ink-faint); font-size:13.5px}
.mast-mood{margin:14px 0 0; font-size:16px; color:var(--ink); font-weight:560;
  padding:12px 16px; background:var(--accent-soft); border-radius:12px; border:1px solid var(--line)}
.mast-mood:empty{display:none}

/* Sections */
.section{margin:38px 0}
.section-head{display:flex; align-items:baseline; gap:10px; margin:0 0 16px}
.section-head h2{font-size:13px; font-weight:750; letter-spacing:.13em; text-transform:uppercase;
  color:var(--ink-soft); margin:0}
.badge-fallback{font-size:10.5px; font-weight:600; color:var(--ink-faint);
  border:1px solid var(--line); border-radius:6px; padding:1px 7px}
.breadth{font-size:12px; font-weight:700; font-variant-numeric:tabular-nums}
.breadth .up{color:var(--up)} .breadth .down{color:var(--down)}

/* Movers strip */
.movers{display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:16px}
.movers-label{font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--ink-faint)}
.mover{display:inline-flex; align-items:center; gap:7px; font-size:12.5px; font-weight:650;
  background:var(--panel); border:1px solid var(--line); border-radius:999px; padding:4px 11px; box-shadow:var(--shadow)}
.mover-name{color:var(--ink)}
.mover.up .mover-pct{color:var(--up)} .mover.down .mover-pct{color:var(--down)} .mover.flat .mover-pct{color:var(--flat)}
.mover-pct{font-variant-numeric:tabular-nums}

/* Market grid */
.market-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(248px,1fr)); gap:14px}
.market-card{background:var(--panel); border:1px solid var(--line); border-radius:16px;
  padding:16px 16px 10px; box-shadow:var(--shadow)}
.card-head{display:flex; align-items:baseline; justify-content:space-between; margin-bottom:6px}
.card-head h3{font-size:14.5px; margin:0; font-weight:730}
.card-note{font-size:11px; color:var(--ink-faint)}
.rows{display:flex; flex-direction:column}
.row{padding:10px 0; border-top:1px solid var(--line)}
.row:first-child{border-top:none}
.row-top{display:flex; align-items:baseline; justify-content:space-between; gap:10px}
.q-label{font-size:14px; color:var(--ink-soft); font-weight:580}
.q-asof{display:block; font-size:10px; font-weight:500; color:var(--ink-faint); margin-top:1px}
.q-price{font-variant-numeric:tabular-nums; font-weight:700; font-size:15px; color:var(--ink)}
.row-bot{display:flex; align-items:center; gap:10px; margin-top:5px}
.q-chg{font-variant-numeric:tabular-nums; font-size:12px; font-weight:650; white-space:nowrap; margin-left:auto}
.row.up .q-chg{color:var(--up)} .row.down .q-chg{color:var(--down)} .row.flat .q-chg{color:var(--flat)}
.q-pct{opacity:.95}
.q-unavail,.wl-unavail{font-size:12px; color:var(--ink-faint); font-style:italic}
.row.muted .q-label{color:var(--ink-faint)}
.is-stale .q-price{opacity:.85}
/* day-range micro-bar */
.range{flex:1; min-width:34px; max-width:130px}
.range--none{visibility:hidden}
.range-track{position:relative; height:4px; border-radius:3px;
  background:linear-gradient(90deg,var(--line),var(--line))}
.range-dot{position:absolute; top:50%; width:8px; height:8px; border-radius:50%;
  transform:translate(-50%,-50%); background:var(--flat); border:2px solid var(--panel)}
.range.up .range-dot{background:var(--up)} .range.down .range-dot{background:var(--down)}

/* Themes */
.mood{font-size:16.5px; color:var(--ink); margin:0 0 18px; font-weight:560;
  padding-left:14px; border-left:3px solid var(--accent)}
.themes{display:flex; flex-direction:column; gap:2px}
.theme{display:flex; gap:14px; padding:16px 0; border-top:1px solid var(--line)}
.theme:first-child{border-top:none}
.theme-num{flex:none; width:27px; height:27px; border-radius:50%; background:var(--accent);
  color:#fff; font-size:13px; font-weight:700; display:flex; align-items:center; justify-content:center}
.theme-kicker{display:block; font-size:10.5px; font-weight:700; letter-spacing:.1em;
  text-transform:uppercase; color:var(--kicker); margin-bottom:3px}
.theme-body h4{margin:0 0 5px; font-size:16.5px; font-weight:720; line-height:1.3}
.theme-body p{margin:0; color:var(--ink-soft); font-size:14.5px}

/* Watch */
.watch-list{list-style:none; margin:0; padding:0; display:grid;
  grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:12px}
.watch-list li{display:flex; gap:11px; align-items:flex-start; background:var(--panel);
  border:1px solid var(--line); border-radius:13px; padding:14px 15px; box-shadow:var(--shadow)}
.watch-dot{flex:none; width:8px; height:8px; border-radius:50%; background:var(--kicker); margin-top:7px}
.watch-text{display:flex; flex-direction:column; gap:3px}
.watch-text strong{font-size:14.5px; font-weight:680}
.watch-detail{font-size:13px; color:var(--ink-soft)}

/* News */
.news-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(330px,1fr)); gap:14px 30px}
.news-cat-title{font-size:14px; font-weight:760; margin:0 0 8px; padding-bottom:8px;
  border-bottom:2px solid var(--line); color:var(--ink); display:flex; align-items:center; gap:8px;
  text-transform:uppercase; letter-spacing:.06em}
.news-count{font-size:11px; font-weight:600; color:var(--ink-faint); background:var(--panel-2);
  border-radius:999px; padding:1px 8px; letter-spacing:0}
.stories{display:flex; flex-direction:column}
.story{padding:13px 0; border-top:1px solid var(--line)}
.story:first-child{border-top:none}
.story-title{margin:0 0 4px; font-size:15px; font-weight:640; line-height:1.34}
.story--lead .story-title{font-size:16.5px; font-weight:720}
.story-title a{color:var(--ink)} .story-title a:hover{color:var(--accent)}
.ext{font-size:11px; color:var(--ink-faint); font-weight:400; margin-left:4px}
.story-sum{margin:0 0 6px; color:var(--ink-soft); font-size:13.5px; line-height:1.5}
.story-meta{display:flex; gap:8px; align-items:center; font-size:11px; font-weight:600;
  letter-spacing:.03em; text-transform:uppercase}
.story-meta .src{color:var(--accent)}
.story-meta .age{color:var(--ink-faint)}

/* Watchlist */
.watchlist{background:var(--panel); border:1px solid var(--line); border-radius:16px;
  overflow:hidden; box-shadow:var(--shadow)}
.wl-row{display:grid; grid-template-columns:1fr auto auto auto; gap:12px; align-items:center;
  padding:12px 16px; border-top:1px solid var(--line); transition:background .15s}
.wl-row:first-child{border-top:none}
.wl-row:hover{background:var(--panel-2)}
.wl-name{font-weight:620; font-size:14.5px}
.wl-price{font-variant-numeric:tabular-nums; font-weight:700; text-align:right; color:var(--ink)}
.wl-chg,.wl-pct{font-variant-numeric:tabular-nums; font-size:13px; font-weight:650; text-align:right; min-width:66px}
.wl-row.up .wl-chg,.wl-row.up .wl-pct{color:var(--up)}
.wl-row.down .wl-chg,.wl-row.down .wl-pct{color:var(--down)}
.wl-row.flat .wl-chg,.wl-row.flat .wl-pct{color:var(--flat)}
.wl-row.muted{grid-template-columns:1fr auto}

/* Live indicator + price flash */
.live-ind{display:inline-flex; align-items:center; gap:6px; font-size:11px; font-weight:700;
  letter-spacing:.06em; text-transform:uppercase; color:var(--up)}
.live-pulse{width:8px; height:8px; border-radius:50%; background:var(--up); position:relative}
.live-pulse::after{content:""; position:absolute; inset:0; border-radius:50%; background:var(--up);
  animation:pulse 1.8s ease-out infinite}
@keyframes pulse{0%{transform:scale(1);opacity:.7} 100%{transform:scale(3);opacity:0}}
@keyframes flashUp{0%{background:color-mix(in srgb,var(--up) 26%,transparent)} 100%{background:transparent}}
@keyframes flashDown{0%{background:color-mix(in srgb,var(--down) 26%,transparent)} 100%{background:transparent}}
.row.flash-up,.wl-row.flash-up{animation:flashUp .8s ease-out}
.row.flash-down,.wl-row.flash-down{animation:flashDown .8s ease-out}
.q-price,.wl-price,.q-chg,.wl-chg,.wl-pct{transition:color .25s}

/* Price-sensitive announcement flag */
.sens{color:var(--down); font-weight:800; margin-left:4px; cursor:help; font-size:15px; vertical-align:top}

/* Economy & Rates */
.eco-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px}
.eco-card{background:var(--panel); border:1px solid var(--line); border-radius:16px;
  padding:16px 16px 14px; box-shadow:var(--shadow)}
.eco-head{display:flex; align-items:baseline; justify-content:space-between; margin-bottom:12px}
.eco-head h3{font-size:14.5px; margin:0; font-weight:730}
.rec-label{font-size:12px; font-weight:800; padding:2px 10px; border-radius:999px}
.recession.low .rec-label{color:var(--up); background:color-mix(in srgb,var(--up) 16%,transparent)}
.recession.watch .rec-label{color:var(--kicker); background:color-mix(in srgb,var(--kicker) 16%,transparent)}
.recession.moderate .rec-label{color:#d08a2c; background:color-mix(in srgb,#d08a2c 16%,transparent)}
.recession.high .rec-label{color:var(--down); background:color-mix(in srgb,var(--down) 16%,transparent)}
.gauge{position:relative; height:10px; border-radius:6px; margin:6px 0 4px;
  background:linear-gradient(90deg,var(--up) 0%,#e0b94e 52%,var(--down) 100%)}
.gauge-marker{position:absolute; top:50%; width:4px; height:18px; border-radius:3px;
  background:var(--ink); transform:translate(-50%,-50%); box-shadow:0 0 0 2px var(--panel)}
.gauge-scale{display:flex; justify-content:space-between; font-size:10.5px; color:var(--ink-faint); font-weight:600}
.eco-detail{margin:10px 0 6px; font-size:13.5px; color:var(--ink-soft); line-height:1.5}
.eco-fine{margin:0; font-size:11px; color:var(--ink-faint); font-variant-numeric:tabular-nums}
.rate-list{display:flex; flex-direction:column}
.rate-row{display:grid; grid-template-columns:1fr auto; gap:4px 12px; padding:9px 0; border-top:1px solid var(--line)}
.rate-row:first-child{border-top:none}
.rate-name{font-size:14px; font-weight:600; color:var(--ink)}
.rate-val{font-size:14.5px; font-weight:730; text-align:right; font-variant-numeric:tabular-nums; color:var(--ink)}
.rate-note{grid-column:1/-1; font-size:11.5px; color:var(--ink-faint); margin-top:-2px}

/* Footer */
.foot{margin-top:52px; padding-top:22px; border-top:1px solid var(--line); color:var(--ink-faint); font-size:12.5px}
.foot-nav{display:flex; gap:14px; flex-wrap:wrap; margin-bottom:14px}
.foot-nav a{font-size:12.5px; font-weight:600; color:var(--ink-soft)}
.foot p{margin:0 0 5px}
.foot-fine{font-size:11.5px}

/* Card hover lift + fade-in */
.market-card,.eco-card,.watch-list li{transition:transform .18s ease, box-shadow .18s ease}
.market-card:hover,.eco-card:hover{transform:translateY(-2px)}
main>.section{animation:rise .5s ease both}
@keyframes rise{from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important; transition:none!important}}

@media (max-width:560px){
  .wrap{padding:20px 15px 48px}
  .greeting{font-size:27px}
  .market-grid,.news-grid{grid-template-columns:1fr}
  .wl-row{grid-template-columns:1fr auto auto; row-gap:2px}
  .wl-pct{display:none}
  .nav-brand{display:none}
}
@media print{
  .topnav,.theme-btn{display:none}
  body{background:#fff; color:#000}
}
""")


# --------------------------------------------------------------------------
# Minesweeper — a standalone brain-warmer page (18x18, 20 mines)
# --------------------------------------------------------------------------
def minesweeper_page(title):
    """Self-contained Minesweeper page sharing the dispatch's palette + theme."""
    return _MINESWEEPER.replace("{{TITLE}}", esc(title))


_MINESWEEPER = ("""<!DOCTYPE html>
<html lang="en-AU"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="color-scheme" content="light dark">
<title>Minesweeper — {{TITLE}}</title>
<script>try{var t=localStorage.getItem('mcd-theme');if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}</script>
<style>
:root{ --bg:#f4f2ec; --panel:#fffdf9; --panel-2:#efece4; --ink:#1b1c21; --ink-soft:#52545d;
  --ink-faint:#8b8d97; --line:#ddd7ca; --accent:#2f6f5e; --kicker:#9a6a3c; --down:#c0392b;
  --shadow:0 1px 2px rgba(40,35,25,.06),0 8px 24px rgba(40,35,25,.05);
  --c1:#2f6f5e;--c2:#9a6a3c;--c3:#c0392b;--c4:#5a4db1;--c5:#b1592f;--c6:#1f8a8a;--c7:#444;--c8:#888; }
"""
"""[data-theme="dark"]{ --bg:#121317; --panel:#1b1d24; --panel-2:#21242c; --ink:#eef0f4; --ink-soft:#aab0bd;
  --ink-faint:#787d89; --line:#2a2d36; --accent:#5cb9a0; --kicker:#d2a36c; --down:#f06d5d;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 12px 32px rgba(0,0,0,.3);
  --c1:#5cb9a0;--c2:#d2a36c;--c3:#f06d5d;--c4:#9b8cf0;--c5:#e0945c;--c6:#5ad0d0;--c7:#cfd3da;--c8:#9aa0ab; }
@media (prefers-color-scheme:dark){:root:not([data-theme]){ --bg:#121317; --panel:#1b1d24; --panel-2:#21242c;
  --ink:#eef0f4; --ink-soft:#aab0bd; --ink-faint:#787d89; --line:#2a2d36; --accent:#5cb9a0; --kicker:#d2a36c; --down:#f06d5d;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 12px 32px rgba(0,0,0,.3);
  --c1:#5cb9a0;--c2:#d2a36c;--c3:#f06d5d;--c4:#9b8cf0;--c5:#e0945c;--c6:#5ad0d0;--c7:#cfd3da;--c8:#9aa0ab; }}
*{box-sizing:border-box}
body{margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-text-size-adjust:100%; display:flex; flex-direction:column; align-items:center; min-height:100vh}
.bar{width:100%; max-width:560px; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:14px 16px}
.back{font-size:13px; font-weight:700; color:var(--ink-soft); text-decoration:none}
.back:hover{color:var(--accent)}
.title{font-size:13px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:var(--kicker)}
.hud{width:100%; max-width:560px; display:flex; align-items:center; justify-content:space-between; gap:10px; padding:0 16px 12px}
.stat{display:flex; align-items:center; gap:7px; font-variant-numeric:tabular-nums; font-weight:800; font-size:18px;
  background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:8px 14px; box-shadow:var(--shadow)}
.stat small{font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--ink-faint)}
.btn{cursor:pointer; font:inherit; font-weight:700; font-size:14px; color:var(--ink); background:var(--panel);
  border:1px solid var(--line); border-radius:12px; padding:8px 14px; box-shadow:var(--shadow)}
.btn:hover{border-color:var(--ink-faint)}
.btn.on{background:var(--accent); color:#fff; border-color:transparent}
.wrap{padding:0 12px 26px}
#board{display:grid; gap:2px; width:min(94vw,540px); background:var(--line); padding:2px; border-radius:12px;
  box-shadow:var(--shadow); touch-action:manipulation; user-select:none; -webkit-user-select:none}
.cell{aspect-ratio:1/1; display:flex; align-items:center; justify-content:center;
  font-weight:800; font-size:clamp(11px,3vw,16px); border-radius:4px; background:var(--panel-2); cursor:pointer;
  font-variant-numeric:tabular-nums}
.cell.rev{background:var(--panel); cursor:default}
.cell.flag{background:var(--panel-2)}
.cell.mine{background:var(--down); color:#fff}
.cell.boom{background:var(--down); color:#fff; box-shadow:0 0 0 2px var(--down)}
.c1{color:var(--c1)}.c2{color:var(--c2)}.c3{color:var(--c3)}.c4{color:var(--c4)}
.c5{color:var(--c5)}.c6{color:var(--c6)}.c7{color:var(--c7)}.c8{color:var(--c8)}
.msg{height:24px; margin:14px 0 0; font-weight:800; font-size:16px}
.msg.win{color:var(--accent)} .msg.lose{color:var(--down)}
</style></head>
<body>
<div class="bar"><a class="back" href="index.html">&larr; Back to Dispatch</a>
  <span class="title">Brain Warmer</span>
  <button class="btn" id="theme" type="button">Theme</button></div>
<div class="hud">
  <span class="stat"><small>Mines</small> <span id="mines">20</span></span>
  <button class="btn" id="restart" type="button">&#8635; New game</button>
  <button class="btn" id="flagmode" type="button">&#9873; Flag</button>
  <span class="stat"><small>Time</small> <span id="time">0</span></span>
</div>
<div class="wrap"><div id="board"></div><div class="msg" id="msg"></div></div>
<script>
(function(){
  var N=18, MINES=20;
  var board=document.getElementById('board'), msg=document.getElementById('msg');
  var minesEl=document.getElementById('mines'), timeEl=document.getElementById('time');
  var cells=[], mine=[], adj=[], rev=[], flag=[], started=false, over=false, t=0, timer=null, flagMode=false;
  board.style.gridTemplateColumns='repeat('+N+',1fr)';
  function idx(r,c){return r*N+c;}
  function neigh(i){var r=(i/N)|0,c=i%N,o=[];for(var dr=-1;dr<=1;dr++)for(var dc=-1;dc<=1;dc++){if(!dr&&!dc)continue;var nr=r+dr,nc=c+dc;if(nr>=0&&nr<N&&nc>=0&&nc<N)o.push(idx(nr,nc));}return o;}
  function build(){
    board.innerHTML=''; cells=[]; mine=[]; adj=[]; rev=[]; flag=[];
    for(var i=0;i<N*N;i++){mine[i]=false;adj[i]=0;rev[i]=false;flag[i]=false;
      var d=document.createElement('div'); d.className='cell'; d.dataset.i=i; board.appendChild(d); cells[i]=d;}
    started=false; over=false; t=0; timeEl.textContent='0'; minesEl.textContent=MINES; msg.textContent=''; msg.className='msg';
    if(timer){clearInterval(timer);timer=null;}
  }
  function place(safe){
    var banned={}; banned[safe]=1; neigh(safe).forEach(function(x){banned[x]=1;});
    var pool=[]; for(var i=0;i<N*N;i++) if(!banned[i]) pool.push(i);
    for(var m=0;m<MINES;m++){var k=Math.floor(Math.random()*pool.length); mine[pool[k]]=true; pool.splice(k,1);}
    for(var i2=0;i2<N*N;i2++){ if(mine[i2])continue; var cnt=0; neigh(i2).forEach(function(x){if(mine[x])cnt++;}); adj[i2]=cnt; }
  }
  function startTimer(){ timer=setInterval(function(){t++; timeEl.textContent=t;},1000); }
  function reveal(i){
    if(rev[i]||flag[i]) return;
    rev[i]=true; var d=cells[i]; d.classList.add('rev');
    if(mine[i]){ d.classList.add('boom'); d.textContent='\\u2737'; return lose(); }
    if(adj[i]>0){ d.textContent=adj[i]; d.classList.add('c'+adj[i]); }
    else { neigh(i).forEach(function(x){ if(!rev[x]) reveal(x); }); }
  }
  function flagCount(){var n=0;for(var i=0;i<N*N;i++)if(flag[i])n++;return n;}
  function toggleFlag(i){ if(rev[i]) return; flag[i]=!flag[i]; var d=cells[i];
    d.classList.toggle('flag',flag[i]); d.textContent=flag[i]?'\\u2691':''; minesEl.textContent=MINES-flagCount(); }
  function lose(){ over=true; clearInterval(timer);
    for(var i=0;i<N*N;i++){ if(mine[i]&&!flag[i]){cells[i].classList.add('rev','mine'); if(!cells[i].textContent)cells[i].textContent='\\u2737';} }
    msg.textContent='Boom. New game?'; msg.className='msg lose'; }
  function checkWin(){ var safe=0; for(var i=0;i<N*N;i++) if(!mine[i]&&rev[i]) safe++;
    if(safe===N*N-MINES){ over=true; clearInterval(timer); msg.textContent='Cleared in '+t+'s. Nice.'; msg.className='msg win'; } }
  function tap(i){
    if(over) return;
    if(!started){ started=true; place(i); startTimer(); }
    if(flagMode){ toggleFlag(i); return; }
    if(flag[i]) return;
    reveal(i); if(!over) checkWin();
  }
  board.addEventListener('click',function(e){var c=e.target.closest('.cell'); if(c) tap(+c.dataset.i);});
  board.addEventListener('contextmenu',function(e){e.preventDefault(); var c=e.target.closest('.cell'); if(c&&!over){ if(!started){started=true;place(+c.dataset.i);startTimer();} toggleFlag(+c.dataset.i);} });
  // long-press to flag on touch
  var lp=null;
  board.addEventListener('touchstart',function(e){var c=e.target.closest('.cell'); if(!c)return; lp=setTimeout(function(){lp=null; if(!over){ if(!started){started=true;place(+c.dataset.i);startTimer();} toggleFlag(+c.dataset.i);}},420);},{passive:true});
  board.addEventListener('touchend',function(){ if(lp){clearTimeout(lp);lp=null;} });
  document.getElementById('restart').addEventListener('click',build);
  document.getElementById('flagmode').addEventListener('click',function(){ flagMode=!flagMode; this.classList.toggle('on',flagMode); });
  document.getElementById('theme').addEventListener('click',function(){
    var cur=document.documentElement.getAttribute('data-theme');
    var eff=cur||(window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
    var next=eff==='dark'?'light':'dark'; document.documentElement.setAttribute('data-theme',next);
    try{localStorage.setItem('mcd-theme',next);}catch(e){}
  });
  build();
})();
</script>
</body></html>""")
