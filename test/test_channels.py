# test_channels.py
from delivery.channel_manager import broadcast_signals

mock_signals = [
    {
        "ticker": "AAPL",
        "action": "BUY",
        "confidence": 84.50,
        "entry_price": 175.20,
        "atr_value": 3.10,
        "explanation": "Strong systematic break past resistance confirmed by volume trends."
    },
    {
        "ticker": "NVDA",
        "action": "SELL",
        "confidence": 76.20,
        "entry_price": 850.00,
        "atr_value": 22.40,
        "explanation": "Overextended momentum signature combined with sharp moving average divergence."
    }
]

if __name__ == "__main__":
    print("Testing 11:00 AM Scan Routing (Pro Only expected)...")
    broadcast_signals(mock_signals, "11:00AM")

    print("\nTesting 4:15 PM Scan Routing (Pro gets both, Free gets AAPL only since it has higher confidence)...")
    broadcast_signals(mock_signals, "4:15PM")