import os
import requests

def send_telegram(message):

    token = os.getenv("TG_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")

    if not token or not chat_id:
        print("Telegram disabled: missing TG_TOKEN or TG_CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": message
            },
            timeout=10
        )

    except Exception as e:
        print("Telegram Error:", e)
