import time

def safe_update(ws, data):
    try:
        ws.clear()

        print(f"[SHEETS DEBUG] Writing to {ws.title}")
        print(f"[SHEETS DEBUG] Rows={len(data)}")

        worksheet.update(values=data, range_name="A1")
        
        print(f"[SHEETS OK] Updated {ws.title} rows={len(data)}")

        print(
            "VERIFY:",
            ws.acell("A1").value
        )
        
    except Exception as e:
        print(f"[SHEETS ERROR] {ws.title} -> {e}")
        raise
