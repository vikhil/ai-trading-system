import os
import requests

def send_telegram(message):

   TOKEN = os.getenv("TG_TOKEN")
    CHAT_ID = os.getenv("TG_CHAT_ID")
    
    if not TOKEN or not CHAT_ID:
        print("Telegram not configured")
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
