import os
import json
import feedparser
from datetime import datetime, timezone

SOURCES = [
    {
        "name": "Hacker News",
        "url": "https://hnrss.org/newest",
        "label": "Developer Projects",
    },
    {
        "name": "Product Hunt",
        "url": "https://www.producthunt.com/feed",
        "label": "New Websites",
    },
]

MAX_ITEMS = 20
OUTPUT_FILE = "discoveries.json"


def discover_products():
    products = []
    seen_links = set()

    for source in SOURCES:
        print(f"Checking {source['name']}...")

        try:
            feed = feedparser.parse(source["url"])

            for entry in feed.entries[:MAX_ITEMS]:
                link = entry.get("link", "").strip()
                title = entry.get("title", "").strip()
                summary = entry.get("summary", "").strip()

                if not link or not title or link in seen_links:
                    continue

                seen_links.add(link)

                products.append({
                    "title": title,
                    "description": summary[:1500],
                    "url": link,
                    "source": source["name"],
                    "label": source["label"],
                    "discovered_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                })

        except Exception as error:
            print(f"Could not read {source['name']}: {error}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(products, file, ensure_ascii=False, indent=2)

    print(f"Discovery finished: {len(products)} items saved.")


if __name__ == "__main__":
    discover_products()
