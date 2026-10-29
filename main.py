
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
    "User-Agent": "Mozilla/5.0 (compatible; LaunchRadarBot/1.0)"
}

CATEGORY_RULES = {
    "Android Apps": [
        "android app", "google play", "play store",
        "mobile app", "android", "ios app", "iphone app"
    ],
    "AI Tools": [
        "artificial intelligence", "ai tool", "ai-powered",
        "ai powered", "chatgpt", "llm", "machine learning",
        "ai agent", "generative ai"
    ],
    "Free Online Tools": [
        "online tool", "converter", "generator", "formatter",
        "calculator", "pdf tool", "free tool"
    ],
    "Developer Projects": [
        "open source", "github", "developer tool", "api",
        "programming", "self-hosted", "cli tool", "library"
    ],
    "New Websites": [
        "website", "web app", "webapp", "platform", "saas",
        "marketplace", "productivity"
    ],
}


def clean_text(value):
    return re.sub(
        r"\s+", " ",
        BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    ).strip()


def normalize_url(url):
    try:
        parts = urlsplit(url.strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return ""

        ignored = {
            "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "ref", "fbclid", "gclid"
        }
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query)
            if key.lower() not in ignored
        ]

        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            ""
        ))
    except Exception:
        return ""


def classify(title, description):
    text = f"{title} {description}".lower()

    for category, keywords in CATEGORY_RULES.items():
        if any(word in text for word in keywords):
            return category

    return "Needs Review"


def find_hn_project_url(description):
    """Find a plausible project link from a Hacker News description."""
    soup = BeautifulSoup(description or "", "html.parser")

    # Prefer the explicitly labelled Article URL when present.
    text = soup.get_text(" ", strip=True)
    match = re.search(
        r"Article URL:\s*(https?://\S+)",
        text,
        re.IGNORECASE
    )
    if match:
        candidate = normalize_url(match.group(1).rstrip(".,);"))
        if candidate and "news.ycombinator.com" not in candidate:
            return candidate

    # Otherwise prefer a GitHub project link if one is present.
    links = [
        normalize_url(a.get("href", ""))
        for a in soup.find_all("a", href=True)
    ]
    for link in links:
        if link and "github.com" in urlsplit(link).netloc.lower():
            return link

    # Fall back to an external URL in the text, excluding HN comments.
    for candidate in re.findall(r"https?://[^\s<>\"']+", text):
        candidate = normalize_url(candidate.rstrip(".,);"))
        if not candidate:
            continue
        host = urlsplit(candidate).netloc.lower()
        if "news.ycombinator.com" in host:
            continue
        return candidate

    return ""


def find_producthunt_website(product_url):
    """Try multiple page signals; blank means the official site was not found."""
    try:
        response = requests.get(
            product_url,
            headers=HEADERS,
            timeout=20
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Look for common metadata attributes that may contain the website.
        for tag in soup.find_all("meta"):
            key = (
                tag.get("property", "") + " " +
                tag.get("name", "")
            ).lower()
            value = tag.get("content", "").strip()

            if not value.startswith(("https://", "http://")):
                continue

            if any(word in key for word in (
                "og:see_also", "product:website", "website", "twitter:url"
            )):
                host = urlsplit(value).netloc.lower()
                if host and "producthunt.com" not in host:
                    return normalize_url(value)

        # Look for links whose visible label clearly indicates a website.
        for link in soup.find_all("a", href=True):
            href = normalize_url(link.get("href", ""))
            if not href:
                continue

            host = urlsplit(href).netloc.lower()
            if not host or "producthunt.com" in host:
                continue

            label = clean_text(
                link.get_text(" ", strip=True) + " " +
                link.get("aria-label", "") + " " +
                link.get("title", "")
            ).lower()

            if any(term in label for term in (
                "visit website", "visit site", "website", "launch website"
            )):
                return href

    except Exception as error:
        print(f"Could not inspect Product Hunt page: {error}")

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

    # Keep previously saved valid candidates and update missing fields.
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
        )[:3000]
        item["label"] = classify(title, item["description"])
        item.setdefault("official_website", "")
        item.setdefault("status", "needs_review")

        # Recover an HN project URL from its stored description if possible.
        if source == "Hacker News" and not item["official_website"]:
            item["official_website"] = find_hn_project_url(
                item["description"]
            )

        products_by_url[url] = item

    added = 0

    for source in SOURCES:
        print(f"Checking {source['name']}...")

        try:
            feed = feedparser.parse(source["url"])

            for entry in feed.entries[:MAX_ITEMS]:
                title = clean_text(entry.get("title", ""))
                raw_url = entry.get("link", "").strip()
                url = normalize_url(raw_url)
                raw_description = entry.get(
                    "summary", entry.get("description", "")
                )
                description = clean_text(raw_description)[:3000]

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
                    # Do not overwrite existing records just because they
                    # appeared in the feed again.
                    continue

                official_website = ""
                if source["name"] == "Hacker News":
                    official_website = find_hn_project_url(raw_description)
                elif source["name"] == "Product Hunt":
                    official_website = find_producthunt_website(url)

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
    print("Blank official_website means no suitable link was found.")
    print("Review all candidates before publishing.")
    print("No Blogger posts were published.")


if __name__ == "__main__":
    discover_products()
