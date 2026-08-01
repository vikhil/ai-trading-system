import requests
import pandas as pd
from io import StringIO

from discover_nse_downloads import get_download_links


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    ),
    "Referer": "https://www.nseindia.com/",
}


def download_csv(url):

    session = requests.Session()

    response = session.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    df = pd.read_csv(
        StringIO(response.text)
    )

    df.columns = df.columns.str.strip()

    for col in df.select_dtypes(include="object"):
        df[col] = df[col].str.strip()

    return df


def main():

    links = get_download_links()

    datasets = {}

    for name, url in links.items():

        try:

            print(f"Downloading {name}")

            df = download_csv(url)

            datasets[name] = df

            print(
                name,
                "Rows:",
                len(df)
            )

            print(df.head())

        except Exception as e:

            print(
                f"{name} FAILED:",
                e
            )

    print()

    print("Summary")

    for k, v in datasets.items():

        print(
            k,
            len(v)
        )


if __name__ == "__main__":

    main()
