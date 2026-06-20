import sys
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from loguru import logger

# --- IRONCLAD PATH FIX ---
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from delivery.scheduler import refresh_rag_database, run_market_scan
except ImportError:
    logger.warning("Could not import scheduler functions. Ensure they exist in delivery/scheduler.py")

router = APIRouter()

@router.post("/force-news")
async def force_news_update(background_tasks: BackgroundTasks):
    """
    Manually triggers the RAG Chunker to download the latest news and SEC filings.
    """
    logger.info("ADMIN OVERRIDE: Forcing RAG News Update...")
    try:
        background_tasks.add_task(refresh_rag_database)
        return {"status": "success", "message": "News update triggered in the background. Check terminal logs."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/force-broadcast")
async def force_telegram_broadcast(
    background_tasks: BackgroundTasks,
    mode: str = Query("INTRADAY", description="Scan mode: INTRADAY or LONG TERM")
):
    """
    Manually forces the AI to scan the market right now and push the resulting signals
    to the Free and Pro Telegram channels, bypassing the clock.
    """
    mode = mode.upper()
    logger.info(f"ADMIN OVERRIDE: Forcing Telegram Broadcast for {mode}...")
    try:
        # Fixed: Explicitly passing the mode to the scheduler task
        background_tasks.add_task(run_market_scan, mode)
        return {"status": "success", "message": f"Market scan ({mode}) and Telegram broadcast triggered. Check terminal logs."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))