import time

def safe_update(ws, data):
    try:
        ws.clear()
        ws.update(values=data, range_name="A1")
        print(f"[SHEETS OK] Updated {ws.title} rows={len(data)}")
    except Exception as e:
        print(f"[SHEETS ERROR] {ws.title} -> {e}")
