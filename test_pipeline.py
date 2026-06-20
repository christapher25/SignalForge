# test_pipeline.py
import sys
import random
import time
from pathlib import Path
from loguru import logger

# Establish runtime paths
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from data.feature_engine import LiveFeatureEngine


def run_diagnostic_simulation():
    logger.info("⚙️ Initializing Local Feature Engine Test Harness...")

    # We set a tight window size of 10 to easily observe the buffer filling up and capping out
    test_window = 10
    engine = LiveFeatureEngine(window_size=test_window)

    ticker = "NVDA"
    base_price = 1050.00

    logger.info(f"🚀 Simulating a high-frequency burst of 25 ticks for {ticker}...")
    print("-" * 80)

    for i in range(1, 26):
        # Generate realistic random micro-price movements and random order sizes
        price_skew = random.uniform(-2.50, 2.50)
        current_price = round(base_price + price_skew, 2)
        current_volume = float(random.randint(5, 200))

        # Ingest the tick into the engine exactly like alpaca_stream.py does
        metrics = engine.process_tick(ticker, current_price, current_volume)

        # Print status details for every single tick so you can inspect the data transformation
        print(
            f"Tick #{i:02d} | Raw Trade: ${current_price:<7.2f} (Vol: {int(current_volume):<3}) | "
            f"Calculated VWAP: ${metrics['vwap']:<7.2f} | "
            f"Volatility: {metrics['volatility']:<5.3f} | "
            f"Buffer Size: {metrics['tick_count']}/{test_window}"
        )

        # Small delay to mimic standard network stream bursts
        time.sleep(0.05)

    print("-" * 80)
    logger.info("🔍 Running Post-Simulation Architecture Checks...")

    # Structural Verification 1: Did the rolling ring buffer effectively cap its memory profile?
    final_features = engine.get_latest_features(ticker)
    if final_features["tick_count"] == test_window:
        logger.success(f"Verification Pass: Buffer strictly capped at maxlen={test_window}. Memory leak safety holds.")
    else:
        logger.error(
            f"Verification Fail: Buffer size is {final_features['tick_count']}. Expected rigid cap of {test_window}.")

    # Structural Verification 2: Are math calculations resolving to numbers instead of NaN/zeros?
    if final_features["vwap"] > 0 and final_features["volatility"] > 0:
        logger.success(
            f"Verification Pass: Real-time math engine is functional. VWAP and Volatility are actively updating.")
    else:
        logger.error("Verification Fail: Numerical engine returned dead values.")


if __name__ == "__main__":
    try:
        run_diagnostic_simulation()
    except KeyboardInterrupt:
        logger.warning("Diagnostic testing stopped by user choice.")