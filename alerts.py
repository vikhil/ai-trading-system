import os
import requests

def send_telegram(message):

    token = os.getenv("TG_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")

    if not token:
        print("TELEGRAM ERROR: TG_TOKEN missing")
        return

    if not chat_id:
        print("TELEGRAM ERROR: TG_CHAT_ID missing")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message
        }
    )

    print("Telegram Status:", response.status_code)
    print("Telegram Response:", response.text)
