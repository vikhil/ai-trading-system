import time

def safe_update(ws, data):
    try:
        ws.clear()
        ws.update("A1", data)
        print(f"[SHEETS OK] Updated {ws.title} rows={len(data)}")

    except Exception as e:
        print(f"[SHEETS ERROR] {ws.title} -> {e}")
        raise
