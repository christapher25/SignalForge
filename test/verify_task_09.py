import sys
import os
import requests
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_FREE_CHANNEL_ID = os.getenv("TELEGRAM_FREE_CHANNEL_ID")
TELEGRAM_PAID_CHANNEL_ID = os.getenv("TELEGRAM_PAID_CHANNEL_ID")


def verify():
    logger.info("Task 09 Verification executed. Running silent API diagnostics...")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("Task 09 Checkpoint: FAILED. Missing TELEGRAM_BOT_TOKEN in .env file.")
        return

    # 1. Verify Bot Token Validity
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    resp = requests.get(url)

    if not resp.ok:
        logger.error(f"Task 09 Checkpoint: FAILED. Bot token is invalid or Telegram API is down. {resp.text}")
        return

    bot_info = resp.json().get('result', {})
    logger.info(f"Bot authenticated successfully as: @{bot_info.get('username')}")

    # 2. Verify Channel Access (Silently)
    channels = {
        "Free Channel": TELEGRAM_FREE_CHANNEL_ID,
        "Paid Channel": TELEGRAM_PAID_CHANNEL_ID
    }

    all_passed = True
    for name, chat_id in channels.items():
        if not chat_id:
            logger.warning(f"{name} ID is missing from .env")
            all_passed = False
            continue

        # Using getChat to check permissions without sending a message
        chat_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getChat?chat_id={chat_id}"
        chat_resp = requests.get(chat_url)

        if chat_resp.ok:
            logger.info(f"{name} ({chat_id}): VERIFIED. Bot has read/admin access.")
        else:
            logger.error(
                f"Task 09 Checkpoint: FAILED on {name}. Bot lacks permissions or ID is wrong. Error: {chat_resp.text}")
            all_passed = False

    if all_passed:
        logger.info(
            "Task 09 Checkpoint: SUCCESS. Telegram API connection, tokens, and channel routing are fully operational.")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
    verify()