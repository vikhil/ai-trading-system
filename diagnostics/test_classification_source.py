import requests
from bs4 import BeautifulSoup


SYMBOL = "3PLAND"

URL = f"https://www.screener.in/company/{SYMBOL}/"


def main():

    print("=" * 70)
    print("CLASSIFICATION SOURCE TEST")
    print("=" * 70)

    print(f"Symbol : {SYMBOL}")
    print(f"URL    : {URL}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/151.0 Safari/537.36"
        )
    }

    response = requests.get(
        URL,
        headers=headers,
        timeout=30
    )

    print(
        f"HTTP Status : {response.status_code}"
    )

    if response.status_code != 200:
        raise RuntimeError(
            "Unable to retrieve Screener company page."
        )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    text = soup.get_text(
        "\n",
        strip=True
    )

    print()
    print("Searching page for classification terms...")
    print()

    interesting_terms = [
        "Macro Economic Sector",
        "Macro Sector",
        "Sector",
        "Industry",
        "Basic Industry",
        "Financial Services",
        "Realty",
        "Finance",
        "Investment Company",
    ]

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    found = set()

    for line in lines:

        for term in interesting_terms:

            if term.lower() in line.lower():

                found.add(line)

    for line in sorted(found):

        print(
            f"  {line}"
        )

    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
