import time
from gspread.exceptions import APIError

def safe_update(ws, data, retries=5):
    for i in range(retries):
        try:
            ws.clear()
            ws.update("A1", data)
            return

        except APIError as e:
            wait = 2 ** i
            print(f"Retrying Sheets update in {wait}s...")
            time.sleep(wait)

    raise Exception("Google Sheets update failed after retries")
