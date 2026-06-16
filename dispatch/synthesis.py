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
# Rule-based fallback — no LLM. Clusters the freshest headlines into themes.
# --------------------------------------------------------------------------
def _fallback(cfg, market_groups, news_buckets):
    # Mood from breadth of US futures.
    mood = "A quiet overnight session."
    futures = []
    for g in market_groups:
        if "futures" in g["title"].lower() or g["title"] == "US Futures":
            futures = [q for q in g["quotes"] if q.ok]
    if futures:
        avg = sum(q.pct for q in futures) / len(futures)
        if avg > 0.4:
            mood = "US futures point higher; a constructive overnight tone."
        elif avg < -0.4:
            mood = "US futures point lower; a cautious overnight tone."
        else:
            mood = "US futures are little changed; a measured overnight tone."

    # Themes: lead headline from each populated category.
    themes = []
    for c in cfg.NEWS_CATEGORIES:
        items = news_buckets.get(c["key"], [])
        if not items:
            continue
        lead = items[0]
        extra = ("Also: " + items[1].title) if len(items) > 1 else ""
        body = (lead.summary or lead.title)
        if extra:
            body = (body + " " + extra).strip()
        themes.append({"title": "%s — %s" % (c["title"], lead.title[:60]), "body": body})
        if len(themes) >= cfg.SYNTHESIS["max_themes"]:
            break

    # Watch: biggest movers in the snapshot.
    movers = []
    for g in market_groups:
        for q in g["quotes"]:
            if q.ok:
                movers.append(q)
    movers.sort(key=lambda q: abs(q.pct), reverse=True)
    watch = []
    for q in movers[:cfg.SYNTHESIS["max_watch_items"]]:
        watch.append({
            "title": "%s (%+.2f%%)" % (q.label, q.pct),
            "detail": "A notable overnight move worth tracking into the local session.",
        })

    return {"mood": mood, "themes": themes, "watch": watch, "source": "fallback"}


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
