from fastapi import APIRouter, HTTPException
from signals.signal_generator import generate_signal
from loguru import logger

router = APIRouter()

@router.get("/signal")
def get_signal(ticker: str, mode: str = "intraday"):
    """
    Triggers the end-to-end SignalForge inference pipeline.
    """
    logger.info(f"API Request received for signal: {ticker} ({mode})")
    try:
        signal_data = generate_signal(ticker, mode)
        if not signal_data:
            raise HTTPException(status_code=404, detail="Signal generation failed or no data found.")
        return signal_data
    except Exception as e:
        logger.error(f"API Error generating signal for {ticker}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))