#!/usr/bin/env python3
"""Fetch publisher RSS headlines for The Curious Mind; no paid APIs."""
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FEEDS = [
    ("MIT News", "science", "https://news.mit.edu/rss/feed"),
    ("MIT News · AI", "science", "https://news.mit.edu/rss/topic/artificial-intelligence"),
    ("BBC News · Business", "business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC News · Science", "science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("BBC News · World", "world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
]
KEYWORDS = {
    "business": ("biotech", "pharma", "drug", "manufactur", "econom", "trade", "tariff", "supply", "business", "market", "investment", "growth", "leadership", "earnings"),
    "science": ("biology", "science", "genome", "protein", "medical", "medicine", "clinical", "research", "artificial intelligence", "discovery", "robot", "quantum", "neuroscience", "health"),
    "world": ("econom", "trade", "technology", "policy", "election", "diplomac", "climate", "migration", "international", "education", "culture", "science"),
}
LIMITS = {"business": 5, "science": 5, "world": 3}
NOW = datetime.now(timezone.utc)

def cleaned(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s or ""))).strip()

def published_at(raw):
    try:
        value = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

def read_feed(source, topic, url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TheCuriousMindRSSReader/1.0", "Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(request, timeout=12) as response:
        root = ET.fromstring(response.read(1024 * 1024))
    items = root.findall(".//item")
    atom = not bool(items)
    if atom:
        ns = "{http://www.w3.org/2005/Atom}"
        items = root.findall(ns + "entry")
    results = []
    for item in items[:50]:
        if atom:
            title = cleaned(item.findtext(ns + "title"))
            link = item.find(ns + "link")
            url = link.get("href", "") if link is not None else ""
            date = item.findtext(ns + "published") or item.findtext(ns + "updated")
        else:
            title = cleaned(item.findtext("title"))
            url = (item.findtext("link") or "").strip()
            date = item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date")
        when = published_at(date)
        if not when or not url.startswith("https://") or not 16 <= len(title) <= 250:
            continue
        age = NOW - when
        if not timedelta(days=-1) <= age <= timedelta(days=9):
            continue
        score = sum(2 for keyword in KEYWORDS[topic] if keyword in title.casefold())
        score += max(0, 9 - int(age.total_seconds() / 86400))
        results.append({
            "id": sha256(url.encode()).hexdigest()[:14], "title": title,
            "source": source, "topic": topic,
            "published": when.date().isoformat(), "url": url,
            "_score": score, "_time": when.timestamp()
        })
    return results

def main():
    pools = {topic: [] for topic in LIMITS}
    success = 0
    for source, topic, url in FEEDS:
        try:
            articles = read_feed(source, topic, url)
            pools[topic].extend(articles)
            success += 1
            print(f"{source}: {len(articles)} recent articles")
        except Exception as err:
            print(f"WARNING: {source}: {type(err).__name__}: {err}")
    if success == 0:
        raise RuntimeError("All RSS sources failed; keeping previous news feed.")
    used = set()
    selected = []
    for topic, limit in LIMITS.items():
        count = 0
        for article in sorted(pools[topic], key=lambda a: (a["_score"], a["_time"]), reverse=True):
            key = re.sub(r"[^a-z0-9]", "", article["title"].lower())[:100]
            if key in used:
                continue
            used.add(key)
            selected.append({k: v for k, v in article.items() if not k.startswith("_")})
            count += 1
            if count == limit:
                break
    if not selected:
        raise RuntimeError("No recent articles collected; keeping previous news feed.")
    output = {
        "schema": 1,
        "generated_at": NOW.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "policy": "Publisher RSS titles, dates, source names, and links only; not independently verified or AI-written summaries.",
        "items": selected
    }
    target = Path("docs/feed.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(selected)} headlines.")

if __name__ == "__main__":
    main()
