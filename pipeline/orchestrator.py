import sys
from pathlib import Path
from loguru import logger

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# --- IN-MEMORY PIPELINE IMPORTS ---
from pipeline.fetch_ohlcv import run_pipeline as fetch_ohlcv
from pipeline.build_indicators import build_indicators
from pipeline.fetch_macro import run_macro_pipeline
from pipeline.merge_features import run_feature_merge
from delivery.scheduler import run_market_scan


def trigger_market_scan():
    """
    Executes the entire hedge fund pipeline sequentially in a single, memory-safe process.
    Designed to be triggered by an external chron job (AWS, GitHub Actions, Windows Task Scheduler).
    """
    logger.info("Commencing Direct Pipeline Execution...")
    try:
        logger.info("1/5: Fetching Market Data...")
        fetch_ohlcv()

        logger.info("2/5: Building Technical Indicators...")
        build_indicators()

        logger.info("3/5: Fetching Macro Economics...")
        run_macro_pipeline()

        logger.info("4/5: Merging Master Features...")
        run_feature_merge()

        logger.info("5/5: Generating Signals & Broadcasting...")
        run_market_scan("INTRADAY")

        logger.success("Pipeline executed successfully. Shutting down system.")

    except Exception as e:
        logger.error(f"CRITICAL: Pipeline Execution Failed. Error: {e}")
        logger.exception("Detailed Traceback:")

        # 🚨 TELEGRAM EMERGENCY TELEMETRY 🚨
        try:
            from delivery.channel_manager import send_telegram_message
            import config
            error_msg = f"🚨 *CRITICAL SYSTEM FAILURE* 🚨\n\nPipeline execution dropped.\nError: `{str(e)[:150]}`\n\nCheck server logs immediately."
            send_telegram_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_PRO_CHAT_ID, error_msg)
        except Exception as telecom_error:
            logger.error(f"Failed to send emergency Telegram alert: {telecom_error}")


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")

    logger.info("SignalForge Engine Armed. Initiating run...")
    trigger_market_scan()
    sys.exit(0)