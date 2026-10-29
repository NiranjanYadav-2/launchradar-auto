
import json
import re
import os
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import feedparser
from bs4 import BeautifulSoup

SOURCES = [
    {
        "name": "Hacker News",
        "url": "https://hnrss.org/newest",
    },
    {
        "name": "Product Hunt",
        "url": "https://www.producthunt.com/feed",
    },
]

OUTPUT_FILE = "discoveries.json"
MAX_ITEMS = 50

CATEGORY_RULES = {
    "Android Apps": [
        "android app", "android", "google play", "play store",
        "mobile app", "ios app", "iphone app"
    ],
    "AI Tools": [
        "ai tool", "artificial intelligence", "ai-powered",
        "ai powered", "llm", "chatgpt", "generative ai",
        "ai agent", "machine learning"
    ],
    "Free Online Tools": [
        "free online tool", "online tool", "converter",
        "generator", "formatter", "calculator", "pdf tool",
        "image editor", "browser-based"
    ],
    "Developer Projects": [
        "open source", "github", "developer tool", "api",
        "programming", "self-hosted", "cli tool",
        "developer project"
    ],
    "New Websites": [
        "website", "web app", "webapp", "platform",
        "saas", "launch", "productivity", "marketplace"
    ],
}


def clean_text(value):
    soup = BeautifulSoup(value or "", "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()


def normalize_url(url):
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return url.strip()

        ignored = {
            "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "ref", "fbclid", "gclid"
        }

        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in ignored
        ]

        path = parts.path.rstrip("/") or "/"

        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(query),
            ""
        ))
    except Exception:
        return url.strip()


def classify(title, description):
    text = f"{title} {description}".lower()

    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in text for keyword in keywords):
            return category

    return "Needs Review"


def load_existing():
    if not os.path.exists(OUTPUT_FILE):
        return []

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def discover_products():
    existing = load_existing()
    products_by_url = {}

    # Keep only previously stored entries that meet the new quality rules.
    for item in existing:
        title = clean_text(item.get("title", ""))
        url = normalize_url(item.get("url", ""))
        source = item.get("source", "")

        if not title or not url:
            continue

        if source == "Hacker News" and not re.match(
            r"^(show hn|launch hn)\s*:", title, re.IGNORECASE
        ):
            continue

        item["title"] = title
        item["url"] = url
        item["description"] = clean_text(item.get("description", ""))[:1500]
        item["label"] = classify(title, item["description"])

        products_by_url[url] = item

    added = 0

    for source in SOURCES:
        print(f"Checking {source['name']}...")

        try:
            feed = feedparser.parse(source["url"])

            if getattr(feed, "bozo", False):
                print(f"Feed warning for {source['name']}.")

            for entry in feed.entries[:MAX_ITEMS]:
                title = clean_text(entry.get("title", ""))
                raw_url = entry.get("link", "").strip()
                url = normalize_url(raw_url)
                description = clean_text(
                    entry.get("summary", entry.get("description", ""))
                )[:1500]

                if not title or not url:
                    continue

                if source["name"] == "Hacker News":
                    if not re.match(
                        r"^(show hn|launch hn)\s*:",
                        title,
                        re.IGNORECASE
                    ):
                        continue

                if url in products_by_url:
                    continue

                product = {
                    "id": hashlib.sha256(
                        url.encode("utf-8")
                    ).hexdigest()[:16],
                    "title": title,
                    "description": description,
                    "url": url,
                    "source": source["name"],
                    "label": classify(title, description),
                    "discovered_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                    "status": "needs_review",
                }

                products_by_url[url] = product
                added += 1

        except Exception as error:
            print(f"Could not read {source['name']}: {error}")

    products = sorted(
        products_by_url.values(),
        key=lambda item: item.get("discovered_at", ""),
        reverse=True
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(products, file, ensure_ascii=False, indent=2)

    print(f"Discovery finished. New products added: {added}")
    print(f"Total candidates saved: {len(products)}")
    print("Review candidates before publishing.")


if __name__ == "__main__":
    discover_products()
