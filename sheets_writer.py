import time

def safe_update(ws, data, retries=5):
    for i in range(retries):
        try:
            ws.batch_clear(["A:Z"])  # safer than ws.clear()

            ws.update(
                "A1",
                data,
                value_input_option="RAW"
            )

            return

        except Exception as e:
            wait = 2 ** i
            print(f"Sheets retry in {wait}s... Error:", e)
            time.sleep(wait)

    raise Exception("Google Sheets update failed after retries")
