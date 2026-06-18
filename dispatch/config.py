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

A few instruments only exist on the CNBC feed (the primary, since Yahoo blocks
datacenter IPs) and are written in CNBC notation: @TIO.1 (Iron Ore 62%),
AU10Y (Australia 10Y bond), US2Y (US 2Y Treasury). See dispatch/markets.py
CNBC_MAP for how Yahoo symbols translate.
============================================================================
"""

# ---------------------------------------------------------------------------
# SITE — top-level identity and global knobs
# ---------------------------------------------------------------------------
SITE = {
    "title": "Chad's Morning Dispatch",
    "owner_name": "Chad",                 # used in the greeting ("Good morning, Chad")
    "tagline": "Markets · Mining · Geopolitics · The world overnight",
    "max_news_per_category": 8,           # quality over quantity
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
        "title": "US Markets",
        "note": "Futures / latest",
        "tickers": [
            ("ES=F", "S&P 500"),
            ("NQ=F", "Nasdaq 100"),
            ("YM=F", "Dow"),
            ("RTY=F", "Russell 2000"),
        ],
    },
    {
        "title": "Metals & Mining",
        "note": "Precious & base metals",
        "tickers": [
            ("GC=F", "Gold"),
            ("SI=F", "Silver"),
            ("HG=F", "Copper"),
            ("@TIO.1", "Iron Ore 62%"),   # CNBC-native; key for AU miners
            ("PL=F", "Platinum"),
            ("PA=F", "Palladium"),
        ],
    },
    {
        "title": "Energy",
        "note": "Oil & gas",
        "tickers": [
            ("CL=F", "WTI Crude"),
            ("BZ=F", "Brent Crude"),
            ("NG=F", "Nat Gas"),
        ],
    },
    {
        "title": "World Markets",
        "note": "Major global indices",
        "tickers": [
            (".FTSE", "FTSE 100"),        # CNBC-native indices
            (".GDAXI", "DAX (Germany)"),
            (".N225", "Nikkei 225"),
            (".HSI", "Hang Seng"),
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
        "title": "Currencies",
        "note": "Major FX pairs",
        "tickers": [
            ("EURUSD=X", "EUR / USD"),
            ("USDJPY=X", "USD / JPY"),
            ("GBPUSD=X", "GBP / USD"),
            ("NZDUSD=X", "NZD / USD"),
        ],
    },
    {
        "title": "Sovereign Bonds",
        "note": "10Y yields & the curve",
        "tickers": [
            ("US2Y", "US 2Y"),            # CNBC-native rate symbols
            ("^TNX", "US 10Y"),
            ("US30Y", "US 30Y"),
            ("AU2Y", "Australia 2Y"),
            ("AU10Y", "Australia 10Y"),
            ("DE10Y-DE", "Germany 10Y"),
            ("GB10Y-GB", "UK 10Y"),
            ("JP10Y-JP", "Japan 10Y"),
        ],
    },
    {
        "title": "Rates & Risk",
        "note": "USD & volatility",
        "tickers": [
            ("DX-Y.NYB", "US Dollar Index"),
            ("^VIX", "VIX Volatility"),
        ],
    },
    {
        "title": "Crypto",
        "note": "Digital assets",
        "tickers": [
            ("BTC-USD", "Bitcoin"),
            ("ETH-USD", "Ethereum"),
        ],
    },
]

# ---------------------------------------------------------------------------
# WATCHLIST — the Personal Watchlist section.
# A flat list of (symbol, label). Keep it to the names you actually track.
# ---------------------------------------------------------------------------
WATCHLIST = [
    # Miners & resources (the core focus)
    ("BHP.AX", "BHP Group"),
    ("RIO.AX", "Rio Tinto"),
    ("FMG.AX", "Fortescue"),
    ("MIN.AX", "Mineral Resources"),
    ("PLS.AX", "Pilbara Minerals"),
    ("LYC.AX", "Lynas Rare Earths"),
    ("NST.AX", "Northern Star"),
    # Explorers & small caps
    ("SHN.AX", "Sunshine Metals"),
    ("TSO.AX", "Tesoro Gold"),
    ("AZY.AX", "Antipa Minerals"),
    # Energy
    ("WDS.AX", "Woodside Energy"),
    ("STO.AX", "Santos"),
    # Banks & blue chips
    ("CBA.AX", "Commonwealth Bank"),
    ("MQG.AX", "Macquarie Group"),
    ("CSL.AX", "CSL Ltd"),
    # US tech
    ("NVDA", "NVIDIA"),
    ("MSFT", "Microsoft"),
    ("AAPL", "Apple"),
    ("TSLA", "Tesla"),
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
    {"name": "Guardian AU Business","category": "business",    "url": "https://www.theguardian.com/au/business/rss"},
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
    {"name": "Stockhead Resources", "category": "mining",      "url": "https://stockhead.com.au/category/resources/feed/"},
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

# ---------------------------------------------------------------------------
# ANNOUNCEMENTS — ASX price-sensitive announcement flags on the watchlist.
#
# For each ASX (.AX) watchlist ticker we check the ASX announcements feed and,
# if a *price-sensitive* announcement landed within `lookback_hours`, mark the
# stock with a red asterisk (hover shows the headline). Best-effort: a failed
# lookup just means no flag.
# ---------------------------------------------------------------------------
ANNOUNCEMENTS = {
    "enabled": True,
    "lookback_hours": 48,
}

# ---------------------------------------------------------------------------
# ECONOMY — the "Economy & Rates" section: policy rates, a yield-curve-based
# recession gauge, and the housing block.
#
# Policy rates and housing have no clean free live feed, so they're set here and
# updated by hand when they change (rarely). Everything else on the page is live.
# The recession gauge is computed automatically from the US 2s10s yield curve.
# ---------------------------------------------------------------------------
ECONOMY = {
    # Central-bank policy rates — update after each decision (≈8×/year).
    "policy_rates": [
        {"name": "RBA Cash Rate",   "value": "3.85%", "note": "Reserve Bank of Australia", "as_at": "2026-05"},
        {"name": "US Fed Funds",    "value": "4.25–4.50%", "note": "Upper bound 4.50%", "as_at": "2026-05"},
        {"name": "ECB Deposit Rate","value": "2.00%", "note": "European Central Bank", "as_at": "2026-05"},
        {"name": "BoE Bank Rate",   "value": "4.00%", "note": "Bank of England", "as_at": "2026-05"},
    ],
    # AU housing — there is no reliable free live API, so these are indicative
    # figures you refresh from ABS/CoreLogic (monthly is plenty). Clearly labelled
    # "indicative" on the page so they're never mistaken for a live feed.
    "housing": {
        "as_at": "indicative · update in config",
        "rows": [
            {"name": "National median dwelling", "value": "$820,000", "change": "+0.4% m/m"},
            {"name": "Sydney median dwelling",   "value": "$1,190,000", "change": "+0.3% m/m"},
            {"name": "NSW regional median",      "value": "$745,000", "change": "+0.5% m/m"},
        ],
    },
}

# ---------------------------------------------------------------------------
# LOCAL — the Port Stephens Brief (top section). Weather is LIVE (Open-Meteo);
# the fire danger rating has no clean free feed, so set it here (updates rarely
# — winter sits at Low–Moderate for weeks). Coords are Nelson Bay.
# ---------------------------------------------------------------------------
LOCAL = {
    "place": "Nelson Bay · Port Stephens",
    "lat": -32.72, "lon": 152.15,
    "fire_district": "Greater Hunter",
    "fire_rating": "Moderate",            # Moderate | High | Extreme | Catastrophic | No Rating
    "fire_advice": "Plan and prepare.",
    "note": "Good conditions for outdoor work and Prado jobs today.",
}

# ---------------------------------------------------------------------------
# TODAYS_FOCUS — a short personal intention + a rotating quote. Edit freely;
# the quote rotates by day so it changes daily.
# ---------------------------------------------------------------------------
TODAYS_FOCUS = {
    "intention": "Two solid HSC study blocks, gym, and an hour on the Prado.",
    "priorities": [
        "HSC: 2× 50-min blocks (Maths + Physics), phone in the other room",
        "Career: 20 min comparing Mining Eng entry vs RAN (gap year / ADFA)",
        "Body + build: gym session, then diff-breather job on the Prado",
    ],
    "quotes": [
        ("“Discipline equals freedom.”", "Jocko Willink"),
        ("“The mine is only as good as the people who run it.”", "Mining proverb"),
        ("“Amateurs talk strategy; professionals talk logistics.”", "Gen. Omar Bradley"),
        ("“Hard times create strong men.”", "G. Michael Hopf"),
        ("“The best time to plant a tree was 20 years ago. The second best is now.”", "Proverb"),
        ("“Fortune favours the prepared mind.”", "Louis Pasteur"),
        ("“Dig where the gold is — but only if you need the money.”", "Robert Kiyosaki"),
    ],
}

# ---------------------------------------------------------------------------
# MINING_WATCH — Chad's specific junior/resource names, with a one-line reason.
# Symbols use the same notation as WATCHLIST (CNBC/ASX).
# ---------------------------------------------------------------------------
MINING_WATCH = [
    ("TSO.AX", "Tesoro Gold",      "Kun gold project, Chile — drilling + gold leverage"),
    ("SHN.AX", "Sunshine Metals",  "Qld copper-gold-zinc; resource growth story"),
    ("BHL.AX", "Black Horse Min.", "Iron ore / exploration — early-stage spec"),
    ("TMS.AX", "Tennant Minerals", "NT copper-gold (Bluebird) — high-grade hits"),
    ("ORI.AX", "Orica",            "Explosives bellwether — reads mining activity"),
    ("BHP.AX", "BHP Group",        "Iron ore + copper anchor for the sector"),
    ("RIO.AX", "Rio Tinto",        "Iron ore majors / Pilbara + Simandou"),
]

# ---------------------------------------------------------------------------
# PRADO — the 2007 Prado 120 build pulse (light personal section).
# ---------------------------------------------------------------------------
PRADO = {
    "status": "Daily-driver spec, mild touring setup. Running well.",
    "next": "285/70R17 KO3s + speedo recalibration; then diff breathers.",
    "on_order": "Diff-breather kit · sway-bar disconnects (researching exhaust).",
}

# ---------------------------------------------------------------------------
# WATCH_PERSONAL — personal items merged into "What to Watch Today" alongside
# the auto-generated market/news items.
# ---------------------------------------------------------------------------
WATCH_PERSONAL = [
    {"title": "HSC study blocks", "detail": "Lock in two deep-work sessions before midday."},
    {"title": "RFS availability", "detail": "Check the pager / brigade roster for the week."},
]

# ---------------------------------------------------------------------------
# BOND_DANGER — yield thresholds (%). A sovereign-bond row turns red with a ⚠
# when its yield is at/above its danger level (a rough fiscal-stress signal).
# ---------------------------------------------------------------------------
BOND_DANGER = {
    "^TNX": 4.80,     # US 10Y
    "US2Y": 4.80,     # US 2Y
    "US30Y": 5.00,    # US 30Y
    "AU10Y": 5.00,    # Australia 10Y
    "AU2Y": 4.80,     # Australia 2Y
    "GB10Y-GB": 5.00, # UK 10Y
    "JP10Y-JP": 2.50, # Japan 10Y (low base; >2.5% is notable stress)
    "DE10Y-DE": 3.50, # Germany 10Y
}

# ---------------------------------------------------------------------------
# NEWS_FILTER — keep Business & Markets pure macro/markets.
#   exclude: drop stories whose title contains any of these (personal-finance
#            "agony aunt" noise). Applied to the business category.
#   highlight: stories matching these (any category) feed "Chad's Highlights",
#            ranked for relevance to mining juniors, resources, energy & career.
# ---------------------------------------------------------------------------
NEWS_FILTER = {
    "exclude_business": [
        "inheritance", "my husband", "my wife", "retirement", "i'm 60", "i am 60",
        "i'm 65", "nest egg", "aged care", "centrelink", "pension", "should i sell my",
        "agony", "ask the expert", "money problem", "dear ", "superannuation balance",
    ],
    "highlight_keywords": [
        "mining", "miner", "lithium", "copper", "gold", "iron ore", "nickel", "uranium",
        "rare earth", "cobalt", "drill", "exploration", "BHP", "Rio Tinto", "Fortescue",
        "resources", "commodity", "commodities", "oil", "gas", "energy", "OPEC",
        "ASX", "critical minerals", "Pilbara", "RBA", "Fed", "tariff", "China",
    ],
}
