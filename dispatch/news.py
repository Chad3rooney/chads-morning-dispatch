"""News gathering from RSS / Atom feeds, standard library only.

Parses both RSS 2.0 and Atom with xml.etree, tolerates namespaces and malformed
content, strips HTML to clean excerpts, parses publish dates, de-duplicates, and
trims each category to the top N most recent items.

A feed that is slow, down, or malformed is skipped silently — never fatal.
"""

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import http
from . import timeutil

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class Story(object):
    def __init__(self, title, link, summary, source, published, category, weight=1.0):
        self.title = title
        self.link = link
        self.summary = summary
        self.source = source
        self.published = published          # aware datetime (AEST) or None
        self.category = category
        self.weight = weight
        self.age = ""                       # filled in later, e.g. "2h ago"


def _local(tag):
    """Strip an XML namespace: '{http://...}item' -> 'item'."""
    return tag.rsplit("}", 1)[-1].lower() if "}" in tag else tag.lower()


def _find_text(elem, *names):
    """First non-empty child text whose local tag is in names."""
    wanted = set(n.lower() for n in names)
    for child in elem:
        if _local(child.tag) in wanted:
            text = (child.text or "").strip()
            if not text:
                # content:encoded sometimes nests; grab inner text
                text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _find_link(elem):
    """Extract a usable article URL from an item/entry."""
    # RSS: <link>http://...</link>
    for child in elem:
        if _local(child.tag) == "link":
            if child.text and child.text.strip():
                return child.text.strip()
            # Atom: <link href="..." rel="alternate"/>
            href = child.attrib.get("href")
            rel = child.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                return href.strip()
    # Fallback: any link href
    for child in elem:
        if _local(child.tag) == "link" and child.attrib.get("href"):
            return child.attrib["href"].strip()
    return ""


def _clean_text(raw, limit=240):
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text).strip()
    # Drop common feed boilerplate tails
    text = re.sub(r"(Continue reading|Read more|The post).*$", "", text).strip()
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = cut.rstrip(",.;:") + "…"
    return text


def _parse_date(raw):
    """Parse RFC822 (RSS) or ISO8601 (Atom) into an aware UTC datetime, or None."""
    if not raw:
        return None
    raw = raw.strip()
    # RFC822 first (most RSS feeds)
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
    except (TypeError, ValueError, IndexError):
        pass
    # ISO8601 (Atom)
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _parse_feed(xml_text, feed):
    """Return a list of Story from one feed's XML body."""
    stories = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        # Some feeds emit a stray prefix/byte; retry from the first '<'.
        idx = xml_text.find("<rss")
        if idx == -1:
            idx = xml_text.find("<feed")
        if idx > 0:
            try:
                root = ET.fromstring(xml_text[idx:])
            except ET.ParseError:
                return stories
        else:
            return stories

    # Items live under channel/item (RSS) or directly as entry (Atom).
    items = []
    for elem in root.iter():
        if _local(elem.tag) in ("item", "entry"):
            items.append(elem)

    for item in items:
        title = _clean_text(_find_text(item, "title"), limit=200)
        if not title:
            continue
        link = _find_link(item)
        summary = _clean_text(
            _find_text(item, "description", "summary", "encoded", "content"),
            limit=240,
        )
        published = _parse_date(
            _find_text(item, "pubdate", "published", "updated", "date")
        )
        stories.append(Story(
            title=title,
            link=link,
            summary=summary,
            source=feed["name"],
            published=published,
            category=feed["category"],
            weight=feed.get("weight", 1.0),
        ))
    return stories


def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", "", t.lower())[:80]


def gather(feeds, lookback_hours=30, per_category=6, timeout=12):
    """Fetch all feeds, dedupe, filter by recency, and bucket by category.

    Returns: dict category_key -> list[Story] (already trimmed + dated).
    """
    now_dt, _ = timeutil.now_aest()
    cutoff = now_dt.timestamp() - lookback_hours * 3600

    all_stories = []
    for feed in feeds:
        body = http.get(feed["url"], timeout=timeout, retries=2)
        if not body:
            continue
        all_stories.extend(_parse_feed(body, feed))

    # Dedupe by normalised title and by link, keeping the newest.
    seen_titles = {}
    seen_links = {}
    for s in all_stories:
        key_t = _norm_title(s.title)
        key_l = (s.link or "").split("?")[0].rstrip("/")
        ts = s.published.timestamp() if s.published else 0
        prev = seen_titles.get(key_t)
        if prev is None or ts > (prev.published.timestamp() if prev.published else 0):
            seen_titles[key_t] = s
        if key_l:
            seen_links.setdefault(key_l, s)

    deduped = list({id(s): s for s in seen_titles.values()}.values())

    # Recency filter (keep undated stories — better to show than to lose signal).
    fresh = []
    for s in deduped:
        if s.published is None:
            fresh.append(s)
            continue
        local, _ = timeutil.to_aest(s.published)
        s.published = local
        if local.timestamp() >= cutoff:
            fresh.append(s)

    # Sort: weighted recency (newer + higher weight first).
    def sort_key(s):
        ts = s.published.timestamp() if s.published else 0
        return ts + (s.weight - 1.0) * 1800        # weight nudges by up to ~30min
    fresh.sort(key=sort_key, reverse=True)

    # Bucket and trim.
    buckets = {}
    for s in fresh:
        s.age = timeutil.relative_age(s.published, now_dt) if s.published else ""
        buckets.setdefault(s.category, [])
        if len(buckets[s.category]) < per_category:
            buckets[s.category].append(s)
    return buckets
