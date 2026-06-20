import sys
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from signals.signal_generator import generate_signal

# Test tickers from the middle and end of the alphabet
test_tickers = ["TSLA", "NVDA", "ZM", "PLTR", "META"]

print("--- TESTING SIGNAL GENERATION ACROSS THE ALPHABET ---")
for ticker in test_tickers:
    print(f"\nScanning {ticker}...")
    try:
        sig = generate_signal(ticker, mode="INTRADAY")
        if sig:
            print(f"✅ SIGNAL FOUND: {sig['action']} | Entry: ${sig['entry_price']} | Conf: {sig['confidence']}")
        else:
            print(f"⏸️ NO SIGNAL: Market structure is flat (HOLD).")
    except Exception as e:
        print(f"❌ ERROR on {ticker}: {e}")