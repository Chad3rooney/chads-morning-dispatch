"""
============================================================================
 CHAD'S MORNING DISPATCH — CONFIGURATION
============================================================================

This file is the steering wheel for the whole briefing. Everything that
decides *what* the dispatch covers lives here, in plain Python data.

You almost never need to touch the other files. To point the briefing in a
new direction you edit the lists and dicts below:

  - Add a ticker to the snapshot ........ add one line to MARKET_GROUPS
  - Add a stock to your watchlist ....... add one line to WATCHLIST
  - Add a news source ................... add one dict to NEWS_FEEDS
  - Add a whole news category ........... add to NEWS_CATEGORIES + tag feeds
  - Change synthesis emphasis ........... edit SYNTHESIS["focus"]
  - Rebrand / retitle ................... edit SITE

Symbols use Yahoo Finance notation:
  ES=F  S&P 500 futures      ^GSPC  S&P 500 index
  NQ=F  Nasdaq 100 futures   ^AXJO  ASX 200 index
  GC=F  Gold                 BHP.AX BHP on the ASX
  CL=F  WTI crude            AUDUSD=X  AUD/USD
Find any symbol at https://finance.yahoo.com (search, copy the symbol).
============================================================================
"""

# ---------------------------------------------------------------------------
# SITE — top-level identity and global knobs
# ---------------------------------------------------------------------------
SITE = {
    "title": "Chad's Morning Dispatch",
    "owner_name": "Chad",                 # used in the greeting ("Good morning, Chad")
    "tagline": "Markets · Mining · Geopolitics · The world overnight",
    "max_news_per_category": 6,           # quality over quantity
    "news_lookback_hours": 30,            # ignore stories older than this
    "request_timeout": 12,                # seconds per network call
    # Last-known-good market values live here. If a source is temporarily
    # blocked (Yahoo throttles datacenter IPs hard), the briefing falls back to
    # these, flagged "as of <time>", instead of showing "unavailable".
    "market_cache_path": "data/market_cache.json",
}

# ---------------------------------------------------------------------------
# MARKET_GROUPS — the Market Snapshot section.
# Ordered groups of (symbol, label). Each becomes a card row with price,
# change and % change. Reorder, add or remove freely.
# ---------------------------------------------------------------------------
MARKET_GROUPS = [
    {
        "title": "US Futures",
        "note": "Overnight / pre-market",
        "tickers": [
            ("ES=F", "S&P 500"),
            ("NQ=F", "Nasdaq 100"),
            ("YM=F", "Dow"),
            ("RTY=F", "Russell 2000"),
        ],
    },
    {
        "title": "Commodities",
        "note": "Resources & energy",
        "tickers": [
            ("GC=F", "Gold"),
            ("SI=F", "Silver"),
            ("HG=F", "Copper"),
            ("CL=F", "WTI Crude"),
            ("BZ=F", "Brent Crude"),
            ("NG=F", "Nat Gas"),
            # Iron ore has no clean Yahoo spot symbol — tracked via BHP/RIO/FMG
            # in the watchlist below. See README "Extending" for adding a feed.
        ],
    },
    {
        "title": "Australia",
        "note": "Local context (prior close)",
        "tickers": [
            ("^AXJO", "ASX 200"),
            ("^AORD", "All Ordinaries"),
            ("AUDUSD=X", "AUD / USD"),
        ],
    },
    {
        "title": "Global & FX",
        "note": "Currencies & risk",
        "tickers": [
            ("DX-Y.NYB", "US Dollar Index"),
            ("^TNX", "US 10Y Yield"),
            ("BTC-USD", "Bitcoin"),
        ],
    },
]

# ---------------------------------------------------------------------------
# WATCHLIST — the Personal Watchlist section.
# A flat list of (symbol, label). Keep it to the names you actually track.
# ---------------------------------------------------------------------------
WATCHLIST = [
    ("BHP.AX", "BHP Group"),
    ("RIO.AX", "Rio Tinto"),
    ("FMG.AX", "Fortescue"),
    ("WDS.AX", "Woodside Energy"),
    ("PLS.AX", "Pilbara Minerals"),
    ("CBA.AX", "Commonwealth Bank"),
    ("CSL.AX", "CSL Ltd"),
    ("NVDA", "NVIDIA"),
    ("AAPL", "Apple"),
]

# ---------------------------------------------------------------------------
# NEWS_CATEGORIES — display order of the News & Announcements section.
# The "key" must match the "category" tag used on feeds below.
# ---------------------------------------------------------------------------
NEWS_CATEGORIES = [
    {"key": "business",    "title": "Business & Markets"},
    {"key": "australia",   "title": "Australia"},
    {"key": "geopolitics", "title": "Geopolitics & Global"},
    {"key": "mining",      "title": "Mining, Resources & Energy"},
]

# ---------------------------------------------------------------------------
# NEWS_FEEDS — RSS/Atom sources. Each is tagged with a category (above).
# "weight" (optional, default 1.0) nudges ranking when trimming to the top N.
# All feeds are best-effort: a dead or slow feed is skipped, never fatal.
# ---------------------------------------------------------------------------
NEWS_FEEDS = [
    # --- Business & Markets ---
    {"name": "ABC Business",        "category": "business",    "url": "https://www.abc.net.au/news/feed/51892/rss.xml"},
    {"name": "CNBC Markets",        "category": "business",    "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135"},
    {"name": "CNBC Finance",        "category": "business",    "url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"},
    {"name": "MarketWatch Top",     "category": "business",    "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},

    # --- Australia ---
    {"name": "ABC Top Stories",     "category": "australia",   "url": "https://www.abc.net.au/news/feed/51120/rss.xml"},
    {"name": "ABC Just In",         "category": "australia",   "url": "https://www.abc.net.au/news/feed/45910/rss.xml"},
    {"name": "The Guardian AU",     "category": "australia",   "url": "https://www.theguardian.com/australia-news/rss"},
    {"name": "SBS News",            "category": "australia",   "url": "https://www.sbs.com.au/news/feed"},

    # --- Geopolitics & Global ---
    {"name": "Al Jazeera",          "category": "geopolitics", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "Guardian World",      "category": "geopolitics", "url": "https://www.theguardian.com/world/rss"},
    {"name": "BBC World",           "category": "geopolitics", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Reuters via GDELT",   "category": "geopolitics", "url": "https://www.france24.com/en/rss"},

    # --- Mining, Resources & Energy ---
    {"name": "Mining.com",          "category": "mining",      "url": "https://www.mining.com/feed/"},
    {"name": "Mining Weekly",       "category": "mining",      "url": "https://www.miningweekly.com/topic/feed/mining"},
    {"name": "OilPrice.com",        "category": "mining",      "url": "https://oilprice.com/rss/main"},
    {"name": "ABC Rural",           "category": "mining",      "url": "https://www.abc.net.au/news/feed/51892/rss.xml", "weight": 0.5},
]

# ---------------------------------------------------------------------------
# SYNTHESIS — the "Overnight Themes" and "What to Watch Today" sections.
#
# If an ANTHROPIC_API_KEY is present in the environment, the dispatch asks
# Claude to read the gathered markets + headlines and write a calm, neutral
# analyst's synthesis. Without a key it falls back to a clean rule-based
# summary so the briefing is never broken.
# ---------------------------------------------------------------------------
SYNTHESIS = {
    "enabled": True,
    "model": "claude-sonnet-4-6",         # quality + cost balance for a daily run
    "max_themes": 6,                       # 4–6 reads best
    "max_watch_items": 6,
    # A short steer on emphasis. Edit this one string to re-aim the analysis
    # (e.g. "Lean harder into mining, iron ore and energy security.").
    "focus": (
        "You are writing for an Australian reader who cares about markets, "
        "mining and resources, geopolitics, and global macro. Be calm, neutral "
        "and genuinely insightful — like a sharp colleague over morning coffee, "
        "not a hype newsletter. Connect overnight moves to what they mean for "
        "Australia where relevant."
    ),
}
