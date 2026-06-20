import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from signals.signal_generator import generate_signal

# Test a representative sample of your universe
test_tickers = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'AMZN', 'META', 'GOOGL', 'TSLA']

print("====================================================")
print("          CRITICAL SIGNAL MATRIX DIAGNOSTIC         ")
print("====================================================")
print(f"Current Config Gateways -> BUY: >={config.BUY_THRESHOLD}% | SELL: <={config.SELL_THRESHOLD}%")
print("----------------------------------------------------")

for ticker in test_tickers:
    try:
        sig = generate_signal(ticker, "INTRADAY")

        # Pull raw values directly from the signature payload
        action = sig.get('action')
        confidence = sig.get('confidence', 50.0)
        danger = sig.get('danger_alert', False)

        print(
            f"Ticker: {ticker:<6} | Output Action: {action:<5} | Confidence: {confidence:.2f}% | Macro Danger: {danger}")

    except Exception as e:
        print(f"Ticker: {ticker:<6} | Failed to analyze: {e}")

print("====================================================")