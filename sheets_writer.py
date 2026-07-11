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

        # Local metadata only (does NOT call Google)
        print("Worksheet Row Count:", ws.row_count)

    except Exception as e:

        print(f"[SHEETS ERROR] {ws.title} -> {e}")

        raise

def write_dicts(ws, data, columns):
    """
    Writes List[Dict] to Google Sheets.

    Parameters
    ----------
    ws : gspread worksheet

    data : List[Dict]

    columns : List[str]
    """

    rows = dicts_to_rows(
        data,
        columns
    )

    safe_update(
        ws,
        rows
    )

def dicts_to_rows(dict_list):

    if not dict_list:
        return []

    headers = list(dict_list[0].keys())

    rows = [headers]

    for item in dict_list:
        rows.append(
            [item.get(col, "") for col in headers]
        )

    return rows
