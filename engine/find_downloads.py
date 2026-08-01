import requests
import re

url = "https://www.nseindia.com/market-data/securities-available-for-trading"

headers = {
    "User-Agent": "Mozilla/5.0"
}

r = requests.get(url, headers=headers)

print("Status:", r.status_code)

matches = re.findall(r'https://[^"]+\.csv', r.text)

for m in sorted(set(matches)):
    print(m)
