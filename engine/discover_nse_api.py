import requests

headers = {
    "User-Agent":
        "Mozilla/5.0",
    "Referer":
        "https://www.nseindia.com/",
    "Accept":
        "application/json,text/plain,*/*"
}

session = requests.Session()

session.get(
    "https://www.nseindia.com",
    headers=headers
)

urls = [

    "https://www.nseindia.com/api/market-data-pre-open?key=ALL",

    "https://www.nseindia.com/api/allIndices",

    "https://www.nseindia.com/api/master-quote",

    "https://www.nseindia.com/api/equity-stockIndices",

    "https://www.nseindia.com/api/search/autocomplete?q=etf",

    "https://www.nseindia.com/api/search/autocomplete?q=reit",

    "https://www.nseindia.com/api/search/autocomplete?q=invit"

]

for url in urls:

    try:

        r = session.get(
            url,
            headers=headers,
            timeout=30
        )

        print()

        print(url)

        print(r.status_code)

        print(r.text[:400])

    except Exception as e:

        print(url)

        print(e)
