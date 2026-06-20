import requests
from fastapi import APIRouter, Request, HTTPException
from loguru import logger
import config

router = APIRouter()


def generate_unique_telegram_invite(email: str) -> str:
    """Uses the Telegram Bot API to create a 1-time use invite link for a new buyer."""

    # 1. THE SANITIZER & SAFETY GATE (Identical to channel_manager)
    clean_token = str(config.TELEGRAM_BOT_TOKEN).strip().strip("'\"")
    clean_chat_id = str(config.TELEGRAM_PRO_CHAT_ID).strip().strip("'\"")

    # Auto-correct missing channel prefix marker dynamically
    if clean_chat_id.startswith("100"):
        clean_chat_id = f"-{clean_chat_id}"

    url = f"https://api.telegram.org/bot{clean_token}/createChatInviteLink"
    payload = {
        "chat_id": clean_chat_id,
        "member_limit": 1,  # The link permanently dies after 1 person clicks it
        "name": f"Pro Member: {email[:15]}"  # Labels the link in your Telegram settings
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()

        if data.get("ok"):
            invite_link = data["result"]["invite_link"]
            logger.success(f"Generated 1-time Telegram invite link for {email}: {invite_link}")
            return invite_link
        else:
            logger.error(f"Telegram API rejected invite link request: {data}")
            logger.warning(
                f"DEBUG WEBHOOK FAIL -> Target ID: [{clean_chat_id}] | Token Prefix: [{clean_token[:10]}...]")
            return None
    except Exception as e:
        logger.error(f"Network error generating Telegram link: {e}")
        return None


@router.post("/gumroad")
async def gumroad_webhook(request: Request):
    """Listens for the Gumroad purchase ping."""
    try:
        # Gumroad sends data as a standard web form
        form_data = await request.form()

        # Extract the buyer's email
        buyer_email = form_data.get("email", "unknown_buyer@email.com")
        price = form_data.get("price", "0")

        logger.info(f"💰 New Purchase Detected! Buyer: {buyer_email} | Amount: {price} cents")

        # Generate the secure link
        invite_link = generate_unique_telegram_invite(buyer_email)

        if invite_link:
            logger.info("Ready to email invite link to buyer.")
            return {"status": "success", "buyer": buyer_email, "link": invite_link}
        else:
            raise HTTPException(status_code=500, detail="Failed to generate Telegram link.")

    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid Gumroad payload")