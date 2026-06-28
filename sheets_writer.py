import time

def dicts_to_rows(data, columns):
    """
    Converts List[Dict] into Google Sheet rows.

    Returns:
        [
            header,
            row1,
            row2,
            ...
        ]
    """

    rows = [columns]

    for item in data:

        rows.append([
            item.get(col, "")
            for col in columns
        ])

    return rows
    
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
