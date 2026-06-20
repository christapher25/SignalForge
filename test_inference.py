# test_inference.py
from loguru import logger
import sys
from pathlib import Path

# Force log level to catch detailed trace messages
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from signals.signal_generator import generate_signal

if __name__ == "__main__":
    logger.info("Initializing diagnostic mock test for AAPL inference...")
    signal_data = generate_signal("AAPL", "INTRADAY")

    if signal_data:
        logger.info("=== TARGET INFERENCE SIGNAL GENERATED ===")
        logger.info(f"Ticker:     {signal_data['ticker']}")
        logger.info(f"Action:     {signal_data['action']}")
        logger.info(f"Confidence: {signal_data['confidence']}%")
        logger.info(f"Raw Prob:   {signal_data['raw_prob']}")
        logger.info(f"Composite:  {signal_data['raw_composite']}")
        logger.info("=========================================")
    else:
        logger.error("Test failed: Signal generation returned None.")