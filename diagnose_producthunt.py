
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit

PRODUCT_URL = "https://www.producthunt.com/products/zest-6"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
}


def main():
    print("Checking Product Hunt page...")
    print("URL:", PRODUCT_URL)

    try:
        response = requests.get(
            PRODUCT_URL,
            headers=HEADERS,
            timeout=25
        )

        print("HTTP status:", response.status_code)
        print("Final URL:", response.url)
        print("HTML size:", len(response.text), "characters")

        soup = BeautifulSoup(response.text, "html.parser")

        print("\n--- Website-related metadata ---")
        found_metadata = False

        for tag in soup.find_all("meta"):
            key = (
                tag.get("property", "") + " " +
                tag.get("name", "")
            ).lower()
            value = tag.get("content", "").strip()

            if value and any(word in key for word in (
                "website", "see_also", "canonical", "og:url"
            )):
                print(key, "=>", value[:300])
                found_metadata = True

        if not found_metadata:
            print("No matching metadata found.")

        print("\n--- External links ---")
        seen = set()
        count = 0

        for tag in soup.find_all("a", href=True):
            href = urljoin(response.url, tag["href"])
            parts = urlsplit(href)
            host = parts.netloc.lower()

            if parts.scheme not in ("http", "https"):
                continue

            if not host or "producthunt.com" in host:
                continue

            if href in seen:
                continue

            seen.add(href)
            label = " ".join(tag.get_text(" ", strip=True).split())
            print(f"Text: {label[:100] or '[no text]'}")
            print(f"URL:  {href[:300]}")
            print("---")

            count += 1
            if count >= 30:
                break

        if count == 0:
            print("No external links found in the returned HTML.")

        print("\nDiagnostic finished.")

    except requests.RequestException as error:
        print("Request failed:", str(error))


if __name__ == "__main__":
    main()
