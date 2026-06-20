import sys
import requests
from pathlib import Path
from loguru import logger
from tenacity import retry, wait_exponential, stop_after_attempt

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))
import config


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
def send_telegram_message(text: str, chat_id: str):
    """Sends a raw text message to a specific Telegram Chat ID."""

    # 1. SCRUB THE STRINGS: Kills all hidden spaces, newlines, and quotes
    token = str(getattr(config, 'TELEGRAM_BOT_TOKEN', '')).strip(" '\r\n\"")
    clean_id = str(chat_id).strip(" '\r\n\"")

    if not token or not clean_id or clean_id == "None":
        logger.warning(f"Telegram credentials missing or Chat ID not found. Simulated output:\n\n{text}")
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": clean_id, "text": text, "parse_mode": "HTML"}

    response = requests.post(url, json=payload, timeout=10)
    if response.status_code != 200:
        logger.error(f"Telegram API Error: {response.text}")
        response.raise_for_status()
    return True


def format_signal(sig: dict, is_free_channel: bool = False) -> str:
    """Formats the signal dictionary into a professional Telegram HTML alert."""

    # Safely extract data with fallbacks for both your old and new JSON structures
    ticker = sig.get('ticker', 'UNKNOWN')
    action = sig.get('action', 'HOLD')
    mode = sig.get('mode', 'INTRADAY')
    conf = sig.get('confidence', sig.get('probability', 0.0) * 100)
    entry = sig.get('entry', sig.get('entry_price', 0.0))
    target = sig.get('target', sig.get('take_profit', 0.0))
    stop = sig.get('stop_loss', 0.0)
    tech_score = sig.get('technical_score', 'N/A')
    sent_score = sig.get('sentiment_score', 'N/A')
    ctx_score = sig.get('market_context_score', 'N/A')
    reasoning = sig.get('reasoning', 'Quantitative Edge Confirmed.')

    # 1. Marketing hook: Mask the ticker for free users
    display_ticker = "🔒 [PRO ONLY]" if is_free_channel else f"<b>{ticker}</b>"

    # 2. Fix Emoji Logic
    if action == "BUY":
        action_emoji = "🟢"
    elif action == "SELL":
        action_emoji = "🔴"
    else:
        action_emoji = "🟡"

    mode_text = "Intraday Swing" if str(mode).upper() == "INTRADAY" else "Long Term Position"

    # 3. Ensure confidence is capped correctly
    display_confidence = float(conf) if float(conf) <= 100 else float(conf) / 100

    header = f"{action_emoji} <b>SIGNALFORGE ALERT</b> | {mode_text}\n"
    header += f"━━━━━━━━━━━━━━━━━━━━━━\n"

    body = f"<b>Asset:</b> {display_ticker}\n"
    body += f"<b>Action:</b> {action}\n"
    body += f"<b>Confidence:</b> {display_confidence:.2f}%\n\n"

    # 4. Fix Target Display Logic
    if not is_free_channel and action in ['BUY', 'SELL']:
        body += f"🎯 <b>Entry:</b> ${float(entry):.2f}\n"
        body += f"📈 <b>Target:</b> ${float(target):.2f}\n"
        body += f"🛑 <b>Stop Loss:</b> ${float(stop):.2f}\n\n"
    elif is_free_channel and action in ['BUY', 'SELL']:
        body += f"🎯 <b>Entry/Targets:</b> 🔒 Hidden for Free Users\n\n"

    body += f"📊 <b>Quantitative Breakdown:</b>\n"
    body += f"• Technicals: {tech_score}\n"
    body += f"• Sentiment: {sent_score}\n"
    body += f"• Market Context: {ctx_score}\n\n"

    if not is_free_channel:
        body += f"🧠 <b>AI Reasoning:</b>\n{reasoning}\n\n"

    # INVARIANT 8: Legal Disclaimer
    footer = f"<i>Disclaimer: For educational purposes only. Not financial advice. Past performance does not guarantee future results.</i>"

    if is_free_channel:
        footer += f"\n\n💎 <b>Upgrade to Pro to unlock tickers and targets: [Your Gumroad Link]</b>"

    return header + body + footer