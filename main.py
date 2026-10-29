
import json
import re
import os
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import requests
import feedparser
from bs4 import BeautifulSoup

OUTPUT_FILE = "discoveries.json"
MAX_ITEMS = 50

SOURCES = [
    {"name": "Product Hunt", "url": "https://www.producthunt.com/feed"},
    {"name": "Hacker News", "url": "https://hnrss.org/newest"},
]

HEADERS = {
    "User-Agent": "LaunchRadarBot/1.0 (product discovery)"
}

CATEGORY_RULES = {
    "Android Apps": [
        "android app", "google play", "play store", "mobile app",
        "android", "iphone app", "ios app"
    ],
    "AI Tools": [
        "artificial intelligence", "ai tool", "ai-powered", "ai powered",
        "chatgpt", "llm", "machine learning", "ai agent", "generative ai"
    ],
    "Free Online Tools": [
        "online tool", "converter", "generator", "formatter",
        "calculator", "pdf tool", "free tool"
    ],
    "Developer Projects": [
        "open source", "github", "developer tool", "api",
        "programming", "self-hosted", "cli tool"
    ],
    "New Websites": [
        "website", "web app", "webapp", "platform", "saas",
        "marketplace", "productivity"
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
            (k, v) for k, v in parse_qsl(parts.query)
            if k.lower() not in ignored
        ]

        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            ""
        ))
    except Exception:
        return url.strip()


def classify(title, description):
    text = f"{title} {description}".lower()

    for category, keywords in CATEGORY_RULES.items():
        if any(word in text for word in keywords):
            return category

    return "Needs Review"


def get_official_website(product_url):
    """Try to find an external official website from a Product Hunt page."""
    try:
        response = requests.get(
            product_url,
            headers=HEADERS,
            timeout=15
        )
        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        # First try common structured metadata.
        for key in ("og:url", "og:see_also"):
            tag = soup.find("meta", property=key)
            if tag and tag.get("content"):
                candidate = tag["content"].strip()
                if candidate.startswith(("http://", "https://")):
                    host = urlsplit(candidate).netloc.lower()
                    if "producthunt.com" not in host:
                        return normalize_url(candidate)

        # Then look for links explicitly labelled as the product's website.
        for link in soup.find_all("a", href=True):
            label = clean_text(
                " ".join([
                    link.get_text(" ", strip=True),
                    link.get("aria-label", ""),
                    link.get("title", "")
                ])
            ).lower()

            href = link["href"].strip()
            if not href.startswith(("http://", "https://")):
                continue

            host = urlsplit(href).netloc.lower()
            if "producthunt.com" in host:
                continue

            if any(term in label for term in (
                "visit website", "website", "visit site", "launch website"
            )):
                return normalize_url(href)

    except requests.RequestException as error:
        print(f"Website lookup failed for {product_url}: {error}")
    except Exception as error:
        print(f"Could not inspect {product_url}: {error}")

    return ""


def load_existing():
    if not os.path.exists(OUTPUT_FILE):
        return []

    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def discover_products():
    existing = load_existing()
    products_by_url = {}

    # Retain existing valid candidates, removing unrelated Hacker News posts.
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
        item["description"] = clean_text(
            item.get("description", "")
        )[:2000]
        item["label"] = classify(title, item["description"])
        item.setdefault("official_website", "")
        item.setdefault("status", "needs_review")

        products_by_url[url] = item

    added = 0

    for source in SOURCES:
        print(f"Checking {source['name']}...")

        try:
            feed = feedparser.parse(source["url"])

            for entry in feed.entries[:MAX_ITEMS]:
                title = clean_text(entry.get("title", ""))
                url = normalize_url(entry.get("link", ""))
                description = clean_text(
                    entry.get("summary", entry.get("description", ""))
                )[:2000]

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

                official_website = ""
                if source["name"] == "Product Hunt":
                    official_website = get_official_website(url)

                product = {
                    "id": hashlib.sha256(
                        url.encode("utf-8")
                    ).hexdigest()[:16],
                    "title": title,
                    "description": description,
                    "url": url,
                    "official_website": official_website,
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

    print(f"New candidates added: {added}")
    print(f"Total candidates saved: {len(products)}")
    print("Official website may be blank if it could not be verified.")
    print("No Blogger posts were published.")


if __name__ == "__main__":
    discover_products()
