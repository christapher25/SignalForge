# run_live.py
import sys
import time
from pathlib import Path
from loguru import logger
from collections import deque
import numpy as np

# Ensure project root is accessible
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import config
from main import SignalForgeOrchestrator

try:
    from alpaca.data.live import StockDataStream
except ImportError:
    logger.critical("Alpaca-py missing. Run: pip install alpaca-py")
    sys.exit(1)


class LiveMarketRunner:
    """The 24/7 Production Sentinel that listens to the market and triggers the AI."""

    def __init__(self, target_ticker: str = "NVDA"):
        self.ticker = target_ticker
        self.orchestrator = SignalForgeOrchestrator()

        # 1. Alpaca Stream setup
        self.api_key = getattr(config, "ALPACA_API_KEY", None)
        self.secret_key = getattr(config, "ALPACA_SECRET_KEY", None)

        if not self.api_key or not self.secret_key:
            logger.critical("Alpaca API credentials missing in config.py or .env.")
            sys.exit(1)

        self.stream = StockDataStream(self.api_key, self.secret_key)

        # 2. Feature Engine Memory Buffer
        # We hold the last 25 ticks in memory for real-time math
        self.price_buffer = deque(maxlen=25)
        self.volume_buffer = deque(maxlen=25)
        self.tick_count = 0

        # 3. Spam Prevention Cooldown
        self.last_signal_time = 0
        self.cooldown_seconds = 300  # Wait at least 5 minutes between Telegram alerts

    async def handle_trade(self, trade):
        """Callback triggered by Alpaca for every single live trade tick."""
        price = trade.price
        vol = trade.size
        self.tick_count += 1

        # Update memory buffers
        self.price_buffer.append(price)
        self.volume_buffer.append(vol)

        # Only evaluate logic if the buffer is full
        if len(self.price_buffer) == self.price_buffer.maxlen:
            self.evaluate_signal(price)

    def evaluate_signal(self, current_price):
        """Real-time Feature Engineering & Signal Trigger Logic"""
        current_time = time.time()

        # If we recently sent an alert, skip evaluating to prevent channel spam
        if current_time - self.last_signal_time < self.cooldown_seconds:
            return

            # Calculate live rolling metrics
        prices = np.array(self.price_buffer)
        volumes = np.array(self.volume_buffer)
        vwap = np.sum(prices * volumes) / np.sum(volumes)
        volatility = np.std(prices)

        # Calculate deviation from VWAP
        deviation = abs(current_price - vwap)

        # Log a heartbeat every 50 ticks so you know the stream is alive
        if self.tick_count % 50 == 0:
            logger.info(
                f"Live Ticker: {self.ticker} | Price: ${current_price:.2f} | VWAP: ${vwap:.2f} | Volatility: {volatility:.3f}")

        # ==============================================================
        # 🚀 THE SIGNAL TRIGGER
        # If the price deviates sharply from the VWAP (e.g., > $0.50), trigger!
        # (In the future, you will link your XGBoost model score here)
        # ==============================================================
        if deviation > 0.50:
            logger.warning(f"🚨 LIVE VOLATILITY BREACH DETECTED ON {self.ticker} 🚨")
            self.last_signal_time = current_time

            # Package the exact live market metrics
            metrics = {
                "last_price": round(current_price, 2),
                "vwap": round(vwap, 2),
                "volatility": round(volatility, 3),
                "tick_count": self.tick_count
            }

            # (In production, this queries your ChromaDB for the latest scraped news)
            live_news_context = [
                f"Live momentum breakout detected on {self.ticker} tracking unusual volume streams.",
                "Algorithm notes high intraday deviation from volume-weighted averages."
            ]

            # FIRE THE PIPELINE!
            self.orchestrator.process_signal_event(
                ticker=self.ticker,
                technical_metrics=metrics,
                mock_db_context=live_news_context
            )

    def start(self):
        """Ignites the infinite listening loop."""
        logger.info(f"Subscribing to live Alpaca trade stream for {self.ticker}...")
        self.stream.subscribe_trades(self.handle_trade, self.ticker)

        logger.info("🟢 LIVE RUNNER ACTIVE. Listening to the market 24/7...")
        try:
            self.stream.run()
        except KeyboardInterrupt:
            logger.warning("Live runner terminated by user.")
            self.stream.stop()


if __name__ == "__main__":
    # Ensure standard numpy library is installed first
    try:
        import numpy as np
    except ImportError:
        logger.critical("Dependency missing. Run: pip install numpy")
        sys.exit(1)

    # Start the engine!
    runner = LiveMarketRunner(target_ticker="NVDA")
    runner.start()