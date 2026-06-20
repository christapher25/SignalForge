import sys
import requests
from loguru import logger
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config


def send_telegram_payload(url: str, chat_id: str, text: str):
    """Utility helper to dispatch a separate network request per tier."""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.success(f"Successfully posted digest segment to Chat ID: {chat_id}")
        else:
            logger.error(f"Telegram API Error for Chat ID {chat_id}: {response.text}")
    except Exception as e:
        logger.error(f"Failed transmission to Chat ID {chat_id}: {e}")


def clean_reasoning(text: str) -> str:
    """
    Filters out complicated algorithmic terms, technical model names,
    and raw percentages to expose only narrative news factors.
    """
    if not text:
        return "Market velocity and baseline underlying trend align with current structural shift."

    sentences = text.split('.')
    clean_sentences = []

    # Target elements that distract retail traders
    jargon_blacklist = ['xgboost', 'finbert', 'confidence', 'probability', 'threshold', 'model', 'dataset']

    for sentence in sentences:
        lowered = sentence.lower()
        # Skip sentences focused on backend weights/scores
        if any(jargon in lowered for jargon in jargon_blacklist):
            continue
        if sentence.strip():
            clean_sentences.append(sentence.strip())

    if not clean_sentences:
        return "Key market catalysts confirm solid directional validation."

    return '. '.join(clean_sentences) + '.'


def broadcast_signals(signals: list, scan_time: str):
    """
    Splits and delivers custom distinct payloads to Paid (Pro) and Free channels.
    Hides math complexities and showcases clean catalyst updates instead.
    """
    if not signals:
        return

    bot_token = getattr(config, 'TELEGRAM_BOT_TOKEN', None)
    if not bot_token:
        logger.error("Missing TELEGRAM_BOT_TOKEN inside configuration.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    mode_title = signals[0].get('mode', 'MARKET').upper()

    # Fetch configured chat targets
    pro_chat_id = getattr(config, 'TELEGRAM_PREMIUM_CHAT_ID', None)
    free_chat_id = getattr(config, 'TELEGRAM_FREE_CHAT_ID', None)

    # 1. DELIVER TO PAID (PRO) CHANNEL: Full Analytical Breakdown (Scrubbed News Only)
    if pro_chat_id:
        pro_msg = f"👑 **SIGNALFORGE {mode_title} PRO DIGEST** | {scan_time}\n"
        pro_msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for sig in signals:
            action_icon = "🟢" if sig['action'] == "BUY" else "🔴"
            pro_msg += f"{action_icon} **{sig['ticker']}** | {sig['action']} (PRO)\n"
            pro_msg += f"🎯 Entry: ${sig['entry_price']:.2f}\n"
            pro_msg += f"📈 Target: ${sig['take_profit']:.2f} | 🛑 Stop: ${sig['stop_loss']:.2f}\n"

            # Extract and filter complex raw text strings
            raw_reasoning = sig.get('reasoning', 'Structure aligned.')
            refined_news = clean_reasoning(raw_reasoning)

            pro_msg += f"📰 **Catalyst & Impact:**\n_{refined_news}_\n"
            pro_msg += "───────────────\n"

        pro_msg += "\n*Exclusively distributed to verified Pro accounts.*"
        logger.info("Compiling premium layout for Paid Tier...")
        send_telegram_payload(url, pro_chat_id, pro_msg)

    # 2. DELIVER TO FREE CHANNEL: Partial Teaser Format
    if free_chat_id:
        free_msg = f"🚨 **SIGNALFORGE {mode_title} FREE PREVIEW** | {scan_time}\n"
        free_msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for sig in signals:
            action_icon = "🟢" if sig['action'] == "BUY" else "🔴"
            free_msg += f"{action_icon} **{sig['ticker']}** | {sig['action']}\n"
            free_msg += f"🎯 Entry Reference: ${sig['entry_price']:.2f}\n"
            free_msg += f"🔒 **Catalyst & Impact:** Locked for free tier.\n"
            free_msg += "───────────────\n"

        free_msg += "\n💡 *Upgrade membership tiers to unlock take-profit lines, dynamic stop-losses, and live AI veto engines.*"
        logger.info("Compiling preview layout for Free Tier...")
        send_telegram_payload(url, free_chat_id, free_msg)