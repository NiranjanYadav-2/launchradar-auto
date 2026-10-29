
import requests

TEST_URL = "https://www.producthunt.com/r/p/1296248?app_id=339"

def main():
    print("Testing Product Hunt redirect...")
    try:
        response = requests.get(
            TEST_URL,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=25,
            allow_redirects=True
        )

        print("HTTP status:", response.status_code)
        print("Final URL:", response.url)
        print("Redirect count:", len(response.history))

        for item in response.history:
            print("Redirect:", item.status_code, "->", item.headers.get("Location", ""))

    except requests.RequestException as error:
        print("Request failed:", error)

if __name__ == "__main__":
    main()
