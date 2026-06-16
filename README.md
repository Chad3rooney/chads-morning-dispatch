# Chad's Morning Dispatch

An autonomous daily intelligence briefing — a calm, premium "morning coffee"
catch‑up on **US & Australian markets, commodities, mining, geopolitics and the
world overnight** — fully generated and live as a static page **by 7:00am AEST
every day**.

No servers, no databases, no waiting for data to load. A scheduled job builds
one self‑contained HTML file and publishes it. When you open it at 7am, it's
already there.

```
  ┌──────────────┐   pulls   ┌─────────────────────────────┐  writes  ┌────────────┐
  │ GitHub Action │ ───────▶ │ generate.py (stdlib only)    │ ───────▶ │ index.html │
  │ 2× each AM    │          │  markets · news · synthesis  │          │  (static)  │
  └──────────────┘          └─────────────────────────────┘          └─────┬──────┘
                                                                            ▼
                                                                     GitHub Pages
```

---

## What's in the briefing

| Section | What it gives you |
|---|---|
| **Market Snapshot** | US futures (S&P/Nasdaq/Dow/Russell), commodities (gold, silver, copper, oil, gas), Australia (ASX 200, All Ords, AUD/USD), global & FX. Price, change, % — colour + arrows. |
| **Overnight Themes** | 4–6 high‑signal themes synthesising the night — *what happened and why it matters*. Written by Claude when a key is set; a clean rule‑based version otherwise. |
| **What to Watch Today** | The catalysts, releases and risks worth monitoring during the day. |
| **News & Announcements** | Categorised: Business & Markets · Australia · Geopolitics & Global · Mining, Resources & Energy. Title, excerpt, source, age, direct link. |
| **Personal Watchlist** | Your selected stocks/indices with price, change and %. |

Everything is steered from one file: [`dispatch/config.py`](dispatch/config.py).

---

## Design principles

- **Zero dependencies.** The whole generator is the Python standard library —
  nothing to `pip install`, nothing to break when a package changes. It runs on
  any Python 3.7+ and needs no install step in CI. (See `requirements.txt`.)
- **Graceful degradation.** Every data source is best‑effort. A dead feed, a
  rate‑limited ticker, a missing API key — each narrows the briefing slightly
  but **never breaks the build**. You always get a page.
- **Static output.** The result is one HTML file with inline CSS. It loads
  instantly and works offline once open.
- **Open‑ended by design.** Adding a ticker, a feed, a category, or a whole new
  section is a small, local edit — see *Extending* below.

---

## Quick start (local)

```bash
cd MCD
./run_local.sh
```

That builds `public/index.html` and opens it. To enable the AI synthesis layer:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
./run_local.sh
```

Without a key you still get a complete briefing (the themes/watch sections use a
rule‑based fallback, marked *basic mode*).

---

## Deploy it (autonomous, free) — GitHub Pages

This is the recommended setup: it runs in the cloud, so your Mac doesn't need to
be awake.

1. **Create a repo and push this folder.**
   ```bash
   cd MCD
   git init && git add -A && git commit -m "Morning Dispatch"
   gh repo create chads-morning-dispatch --private --source=. --push
   ```
2. **Enable Pages:** repo **Settings → Pages → Build and deployment → Source:
   GitHub Actions.**
3. **(Optional) Add the AI key:** **Settings → Secrets and variables → Actions →
   New repository secret**, name `ANTHROPIC_API_KEY`.
4. **Done.** The workflow ([`.github/workflows/dispatch.yml`](.github/workflows/dispatch.yml))
   runs at **19:20 and 20:20 UTC** daily and publishes to your Pages URL. You can
   also trigger it any time from the **Actions** tab → *Run workflow*.

### Why two run times?
GitHub cron is UTC and ignores daylight saving. Two runs guarantee the page is
fresh **before 7am local in both halves of the year**, and the winter run lands
*after* the US cash close so it captures the closing prints. Details are in the
workflow comments.

### Alternative: run it on your Mac
If you'd rather not use GitHub, schedule it locally with `launchd`. A starter
plist is in [`extras/local-schedule.plist`](extras/local-schedule.plist) — edit
the path, then `launchctl load` it. (Your Mac must be awake at run time.)

---

## Extending — the whole point

Everything below is a one‑ or two‑line edit to `dispatch/config.py`.

**Add a ticker to the snapshot** — drop a `(symbol, label)` into a group:
```python
{"title": "Commodities", "tickers": [ ("GC=F","Gold"), ("PL=F","Platinum") ]}
```

**Add a stock to your watchlist:**
```python
WATCHLIST = [ ("BHP.AX","BHP Group"), ("LYC.AX","Lynas Rare Earths") ]
```

**Add a news source** — one dict, tagged with a category:
```python
{"name": "AFR", "category": "business", "url": "https://.../rss"}
```

**Add a whole new category** (e.g. *RBA & Monetary Policy*):
```python
NEWS_CATEGORIES = [ ..., {"key": "rba", "title": "RBA & Monetary Policy"} ]
# then tag feeds with "category": "rba"
```

**Re‑aim the analysis** — edit one string:
```python
SYNTHESIS["focus"] = "Lean harder into iron ore, lithium and energy security."
```

**Add an entirely new section** (e.g. a long‑form analysis block): write a
`something_section(...)` function in [`dispatch/render.py`](dispatch/render.py)
(copy an existing one) and add it to the `parts` list in `render_page`. The
data for it goes in `generate.py` alongside the other stages.

Find any Yahoo symbol by searching at <https://finance.yahoo.com> and copying
the symbol shown (e.g. `LYC.AX`, `PL=F`, `^N225`).

---

## How it fits together

```
generate.py              Orchestrates the build; writes public/ + archive/
dispatch/
  config.py              ← you edit this: tickers, feeds, categories, options
  markets.py             Yahoo Finance chart API → Quote objects
  news.py                RSS/Atom fetch, parse, dedupe, bucket
  synthesis.py           Claude over HTTPS (themes + watch) + rule-based fallback
  render.py              Premium static HTML (inline CSS, light/dark, responsive)
  timeutil.py            AEST/AEDT handling, no dependencies
  http.py                Resilient urllib layer (retries, UA, SSL on macOS)
.github/workflows/       Schedule + GitHub Pages deploy
```

Output: `public/index.html` (latest) plus `public/archive/YYYY-MM-DD.html` and a
browsable `public/archive/index.html`.

---

## Notes & limits

- **Market data** is Yahoo Finance's public endpoint — reliable for a daily
  snapshot, but unofficial; the per‑ticker fallback handles the occasional miss.
- **Timezones:** in the southern summer the US cash close (after 7am AEDT) lands
  *after* the briefing, so that period leans on futures + the prior close — an
  unavoidable consequence of the clock, acknowledged in the brief.
- **Not financial advice.** Informational snapshot only.
