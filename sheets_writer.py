import time

def safe_update(ws, data):
    try:
        ws.clear()

        print(f"[SHEETS DEBUG] Writing to {ws.title}")
        print(f"[SHEETS DEBUG] Rows={len(data)}")

        ws.update(values=data, range_name="A1")
        
        print(f"[SHEETS OK] Updated {ws.title} rows={len(data)}")

        print("VERIFY A1:", ws.acell("A1").value)

        try:
            print("VERIFY A2:", ws.acell("A2").value)
            print("VERIFY B2:", ws.acell("B2").value)
        except Exception:
            pass
        
        print("Worksheet Row Count:", len(ws.get_all_values()))
        
    except Exception as e:
        print(f"[SHEETS ERROR] {ws.title} -> {e}")
        raise
