import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials


def load_stock_master():

    creds_dict = json.loads(
        os.environ["GOOGLE_CREDENTIALS"]
    )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )

    client = gspread.authorize(creds)

    sheet = client.open_by_key(
        "1qGsaLVDzxxPSuYnY_Qd2vcEiYXE4tWoTEuxLfH38hPI"
    )

    ws = sheet.worksheet("Stock_Master")

    return ws.get_all_records()
