import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(" '\r\n\"")

print("Asking Telegram servers for your exact Channel IDs...")
url = f"https://api.telegram.org/bot{token}/getUpdates"

response = requests.get(url).json()

if response.get("ok"):
    updates = response.get("result", [])
    if not updates:
        print("No messages found! Please go post 'test' in your channels and run this again.")

    found_ids = set()
    for update in updates:
        post = update.get("channel_post") or update.get("message")
        if post:
            chat = post.get("chat", {})
            chat_id = chat.get("id")
            title = chat.get("title", "Direct Message / Unknown")

            if chat_id not in found_ids:
                print(f"✅ Found Channel: '{title}' ---> TRUE ID: {chat_id}")
                found_ids.add(chat_id)
else:
    print(f"❌ Telegram API Error: {response}")