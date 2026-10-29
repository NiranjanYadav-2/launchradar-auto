
import feedparser

FEED_URL = "https://www.producthunt.com/feed"


def main():
    print("Checking Product Hunt RSS feed...")
    feed = feedparser.parse(FEED_URL)

    print("Feed status:", getattr(feed, "status", "unknown"))
    print("Feed bozo:", feed.bozo)
    print("Entries found:", len(feed.entries))

    for entry in feed.entries[:5]:
        print("\n---")
        print("Title:", entry.get("title", ""))
        print("Product Hunt URL:", entry.get("link", ""))

        for key in ("summary", "description", "content"):
            value = entry.get(key, "")
            if isinstance(value, list):
                value = " ".join(
                    str(item.get("value", "")) for item in value
                )
            if value:
                print(key.title() + ":", str(value)[:1200])

    print("\nRSS diagnostic finished.")


if __name__ == "__main__":
    main()
