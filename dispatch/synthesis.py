"""Overnight synthesis: 'Themes' + 'What to Watch Today'.

If ANTHROPIC_API_KEY is set, Claude reads the gathered markets and headlines and
writes a calm, neutral analyst's take (via a plain HTTPS call — no SDK needed).
Without a key, or if the call fails, a rule-based fallback keeps the section
populated so the briefing is always complete.

Return shape (both paths produce the same structure):
    {
      "mood": "<one short sentence on the overnight tone>",
      "themes": [{"title": str, "body": str}, ...],
      "watch":  [{"title": str, "detail": str}, ...],
      "source": "claude" | "fallback",
    }
"""

import os

from . import http

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


# --------------------------------------------------------------------------
# Build the compact context we hand to the model (or summarise in fallback).
# --------------------------------------------------------------------------
def _market_lines(market_groups):
    lines = []
    for g in market_groups:
        parts = []
        for q in g["quotes"]:
            if q.ok:
                parts.append("%s %+.2f%%" % (q.label, q.pct))
        if parts:
            lines.append("%s: %s" % (g["title"], "; ".join(parts)))
    return lines


def _headline_lines(news_buckets, cat_titles, per_cat=8):
    lines = []
    for key, title in cat_titles:
        items = news_buckets.get(key, [])[:per_cat]
        if not items:
            continue
        lines.append("[%s]" % title)
        for s in items:
            src = " (%s)" % s.source if s.source else ""
            lines.append("- %s%s" % (s.title, src))
    return lines


def _build_prompt(cfg, market_groups, news_buckets, date_label):
    mkt = "\n".join(_market_lines(market_groups))
    cat_titles = [(c["key"], c["title"]) for c in cfg.NEWS_CATEGORIES]
    heads = "\n".join(_headline_lines(news_buckets, cat_titles))
    syn = cfg.SYNTHESIS
    return (
        "%s\n\n"
        "Date: %s.\n\n"
        "OVERNIGHT MARKET MOVES:\n%s\n\n"
        "HEADLINES BY CATEGORY:\n%s\n\n"
        "Write the morning synthesis. Respond with ONLY a JSON object, no prose "
        "around it, in exactly this shape:\n"
        "{\n"
        '  "mood": "one calm sentence capturing the overnight tone",\n'
        '  "themes": [{"title": "short theme title", "body": "2-3 sentences: '
        'what happened and why it matters"}],\n'
        '  "watch": [{"title": "thing to watch today", "detail": "one line on '
        'why / what to look for"}]\n'
        "}\n"
        "Provide %d-%d themes and up to %d watch items. Ground every theme in the "
        "data above; do not invent specific numbers that were not provided. "
        "Prefer signal over noise."
        % (syn["focus"], date_label, mkt or "(unavailable)",
           heads or "(unavailable)", max(4, syn["max_themes"] - 2),
           syn["max_themes"], syn["max_watch_items"])
    )


def _extract_json(text):
    """Pull the first JSON object out of a model response."""
    import json
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    blob = text[start:end + 1]
    try:
        return json.loads(blob)
    except ValueError:
        return None


def _via_claude(cfg, market_groups, news_buckets, date_label, api_key):
    prompt = _build_prompt(cfg, market_groups, news_buckets, date_label)
    payload = {
        "model": cfg.SYNTHESIS["model"],
        "max_tokens": 1800,
        "temperature": 0.4,
        "system": (
            "You are the analyst behind a premium daily market briefing for an "
            "Australian reader. You are calm, neutral, precise and genuinely "
            "insightful. You never hype. You output only valid JSON when asked."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
    }
    data, err = http.post_json(ANTHROPIC_URL, payload, headers=headers, timeout=90)
    if err or not data:
        return None, err or "no response"
    try:
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
    except (AttributeError, TypeError):
        return None, "unexpected response shape"
    parsed = _extract_json(text)
    if not parsed:
        return None, "could not parse JSON from model"
    return parsed, None


# --------------------------------------------------------------------------
# Rule-based fallback — no LLM, no cost. Synthesises the snapshot and the
# freshest headlines into themes and a "what to watch" list that is never empty.
# Deliberately written to read like a brief analyst note rather than a raw list.
# --------------------------------------------------------------------------
def _all_quotes(market_groups):
    return [q for g in market_groups for q in g["quotes"] if q.ok]


def _mood(market_groups):
    futures = []
    for g in market_groups:
        if "futures" in g["title"].lower() or g["title"] == "US Futures":
            futures = [q for q in g["quotes"] if q.ok]
    if not futures:
        ok = _all_quotes(market_groups)
        if not ok:
            return "Markets data is thin this run; leading with the overnight news."
        futures = ok
    avg = sum(q.pct for q in futures) / len(futures)
    if avg > 0.4:
        return "US futures point higher; a constructive, risk-on overnight tone."
    if avg < -0.4:
        return "US futures point lower; a cautious, risk-off overnight tone."
    return "US futures are little changed; a measured, wait-and-see overnight tone."


def _markets_theme(market_groups):
    """A single synthesised paragraph on the overnight market picture."""
    ok = _all_quotes(market_groups)
    if not ok:
        return None
    gainers = [q for q in ok if q.pct > 0]
    losers = [q for q in ok if q.pct < 0]
    if len(gainers) > len(losers) * 1.3:
        breadth = "Risk appetite looks firm"
    elif len(losers) > len(gainers) * 1.3:
        breadth = "Caution is the dominant note"
    else:
        breadth = "The picture is mixed"
    movers = sorted(ok, key=lambda q: abs(q.pct), reverse=True)[:3]
    moves = "; ".join("%s %+.2f%%" % (q.label, q.pct) for q in movers)
    body = ("%s — %d of %d tracked instruments higher. The biggest overnight moves: "
            "%s. That sets the backdrop for the local session." % (
                breadth, len(gainers), len(ok), moves))
    return {"title": "Markets — the overnight picture", "body": body}


def _clip(text, n):
    """Trim to <= n chars on a word boundary with an ellipsis — never mid-word."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


def _category_themes(cfg, news_buckets, room):
    themes = []
    for c in cfg.NEWS_CATEGORIES:
        if room <= 0:
            break
        items = news_buckets.get(c["key"], [])
        if not items:
            continue
        lead = items[0]
        body = lead.summary or lead.title
        if len(items) > 1:
            body = (body + " Also developing: " + items[1].title).strip()
        themes.append({"title": "%s — %s" % (c["title"], _clip(lead.title, 72)), "body": body})
        room -= 1
    return themes


def _fallback(cfg, market_groups, news_buckets):
    max_themes = cfg.SYNTHESIS["max_themes"]
    max_watch = cfg.SYNTHESIS["max_watch_items"]

    # Themes: a synthesised markets paragraph, then the lead per news category.
    themes = []
    mkt = _markets_theme(market_groups)
    if mkt:
        themes.append(mkt)
    themes.extend(_category_themes(cfg, news_buckets, max_themes - len(themes)))

    # Watch: biggest market movers first, then news leads so it's never empty.
    watch, seen = [], set()
    movers = sorted(_all_quotes(market_groups), key=lambda q: abs(q.pct), reverse=True)
    for q in movers[: max(0, max_watch - 2)]:
        verb = "extending higher" if q.pct > 0 else "under pressure"
        watch.append({
            "title": "%s (%+.2f%%)" % (q.label, q.pct),
            "detail": "%s overnight — watch for follow-through into the local session." % verb.capitalize(),
        })
        seen.add(q.label)
    for key in ("geopolitics", "business", "australia", "mining"):
        if len(watch) >= max_watch:
            break
        items = news_buckets.get(key, [])
        if items and items[0].title not in seen:
            s = items[0]
            watch.append({
                "title": s.title[:72],
                "detail": "Developing story (%s) — worth tracking today." % (s.source or "see link"),
            })
            seen.add(s.title)

    return {"mood": _mood(market_groups), "themes": themes, "watch": watch, "source": "fallback"}


# --------------------------------------------------------------------------
# Public entry point.
# --------------------------------------------------------------------------
def synthesize(cfg, market_groups, news_buckets, date_label):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if cfg.SYNTHESIS.get("enabled", True) and api_key:
        result, err = _via_claude(cfg, market_groups, news_buckets, date_label, api_key)
        if result:
            result.setdefault("mood", "")
            result.setdefault("themes", [])
            result.setdefault("watch", [])
            result["source"] = "claude"
            return result
        # Fall through to heuristic on any failure.
        print("  synthesis: Claude path failed (%s) — using fallback" % err)
    else:
        if not api_key:
            print("  synthesis: no ANTHROPIC_API_KEY — using rule-based fallback")
    return _fallback(cfg, market_groups, news_buckets)
