import os
# Forcefully disable ChromaDB's broken background telemetry tracking immediately on boot
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# 1. IRONCLAD PATH & ENVIRONMENT BOOT SEQUENCE
# ==========================================
# Force the system to resolve the exact directory of this config.py file
BASE_DIR = Path(__file__).resolve().parent

# Point directly to the .env file in the same directory
ENV_PATH = BASE_DIR / ".env"

# Explicitly load the .env file and override the PyCharm terminal environment cache
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ==========================================
# 2. DIRECTORY STRUCTURE
# ==========================================
DATA_DIR = BASE_DIR / 'data'
RAW_DIR = DATA_DIR / 'raw'
PROCESSED_DIR = DATA_DIR / 'processed'
CONSTITUENTS_DIR = DATA_DIR / 'constituents'
MODELS_DIR = BASE_DIR / 'ml' / 'models'
CHROMA_DIR = BASE_DIR / 'chroma_db'
LOGS_DIR = BASE_DIR / 'logs'
DB_PATH = BASE_DIR / 'db' / 'signalforge.db'

# ==========================================
# 3. API KEYS & SECRETS (Loaded from .env)
# ==========================================
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = 'https://paper-api.alpaca.markets'

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')
FRED_API_KEY = os.getenv('FRED_API_KEY')

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(" '\r\n\"")
TELEGRAM_PREMIUM_CHAT_ID = os.getenv("TELEGRAM_PAID_CHANNEL_ID", "").strip(" '\r\n\"")
TELEGRAM_FREE_CHAT_ID = os.getenv("TELEGRAM_FREE_CHANNEL_ID", "").strip(" '\r\n\"")

GUMROAD_SECRET = os.getenv('GUMROAD_SECRET')

# ==========================================
# 4. QUANTITATIVE & ML THRESHOLDS
# ==========================================
XGBOOST_THRESHOLD = 0.72
MIN_OUTCOMES_FOR_RETRAIN = 20

# LOWERED TO MAKE THE AI MORE AGGRESSIVE
BUY_THRESHOLD = 55   # Previously 65 (Now it only needs to be 55% sure to BUY)
SELL_THRESHOLD = 45  # Previously 35 (Now it only needs to be 55% sure to SELL)

NEWS_DANGER_THRESHOLD = -0.7
SIGNAL_LABEL_DAYS = 3
PRICE_MOVE_THRESHOLD = 0.02

# ==========================================
# 5. UNIVERSE & BACKTESTING SETTINGS
# ==========================================
UNIVERSE_SIZE = 800
HISTORY_YEARS = 20
START_DATE = '2004-01-01'

# ==========================================
# 6. ML & NLP MODEL SETTINGS
# ==========================================
FINBERT_BATCH_SIZE = 64
MINILM_BATCH_SIZE = 128
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
FINBERT_MODEL = 'ProsusAI/finbert'

# ==========================================
# 7. SCHEDULER TIMINGS
# ==========================================
PREMARKET_SCAN_TIME = '08:00'
INTRADAY_SCAN_1 = '11:30'
INTRADAY_SCAN_2 = '14:00'
POSTMARKET_TIME = '16:15'
RETRAIN_TIME = '23:00'

# ==========================================
# 8. LOGGING SETTINGS
# ==========================================
LOG_ROTATION = '1 day'
LOG_RETENTION = '7 days'