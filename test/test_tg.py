import sys
from pathlib import Path
import requests

# Ironclad path fix
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config

print("=== SIGNALFORGE TELEGRAM DIAGNOSTIC ===")
print(f"1. Raw Token: '{config.TELEGRAM_BOT_TOKEN}'")

# Use getattr to safely check what Python actually sees in config.py
prem_id = getattr(config, 'TELEGRAM_PREMIUM_CHAT_ID', getattr(config, 'TELEGRAM_PRO_CHAT_ID', None))
free_id = getattr(config, 'TELEGRAM_FREE_CHAT_ID', None)

print(f"2. Premium ID Python sees: '{prem_id}'")
print(f"3. Free ID Python sees: '{free_id}'")

if not prem_id:
    print("❌ ERROR: Premium ID is None. Your config.py is not loading the .env correctly.")
    sys.exit(1)

print("\nAttempting raw API connection to Premium Channel...")
url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
payload = {
    "chat_id": prem_id,
    "text": "Diagnostic Test: If you see this, the API works."
}

try:
    res = requests.post(url, json=payload).json()
    print(f"API Response: {res}")
except Exception as e:
    print(f"Request failed: {e}")