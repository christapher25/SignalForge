import os
import requests
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

token = os.getenv("TELEGRAM_BOT_TOKEN")
channel = os.getenv("TELEGRAM_PAID_CHANNEL_ID")

def test():
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": channel, "text": "SignalForge System Test"}
    try:
        r = requests.post(url, json=payload)
        r.raise_for_status()
        print("SUCCESS: Message sent to Paid Channel.")
    except Exception as e:
        print(f"FAILED: Telegram API returned: {e.response.text}")

test()