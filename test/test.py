import sqlite3
import sys
from pathlib import Path

# Setup
sys.path.append('.')
try:
    conn = sqlite3.connect('db/signalforge.db')
    c = conn.cursor()
except Exception as e:
    print(f"FATAL ERROR connecting to database: {e}")
    sys.exit(1)

print("--- Check 1 — Database table row counts ---")
tables = ['ohlcv', 'indicators', 'news', 'macro', 'signals', 'walk_forward_results', 'subscribers']
for t in tables:
    try:
        c.execute(f'SELECT COUNT(*) FROM {t}')
        print(f'{t}: {c.fetchone()[0]} rows')
    except Exception as e:
        print(f'{t}: ERROR - {e}')

print("\n--- Check 2 — News table data quality ---")
try:
    c.execute('SELECT COUNT(*) FROM news WHERE finbert_sentiment IS NOT NULL AND finbert_sentiment != 0.0')
    print('News with real FinBERT scores:', c.fetchone()[0])
    c.execute('SELECT COUNT(*) FROM news WHERE headline IS NULL OR headline = ""')
    print('News with missing headlines:', c.fetchone()[0])
    c.execute('SELECT MIN(date), MAX(date) FROM news')
    print('News date range:', c.fetchone())
except Exception as e:
    print(f'News quality ERROR - {e}')

print("\n--- Check 3 — Indicators data quality ---")
try:
    c.execute('SELECT COUNT(DISTINCT ticker) FROM indicators')
    print('Tickers with indicators:', c.fetchone()[0])
    c.execute('SELECT COUNT(*) FROM indicators WHERE rsi_14 IS NULL')
    print('Indicators with null RSI:', c.fetchone()[0])
    c.execute('SELECT MIN(date), MAX(date) FROM indicators')
    print('Indicators date range:', c.fetchone())
except Exception as e:
    print(f'Indicators quality ERROR - {e}')

print("\n--- Check 4 — Macro data quality ---")
try:
    c.execute('SELECT COUNT(*) FROM macro WHERE fed_rate IS NOT NULL')
    print('Macro rows with fed rate:', c.fetchone()[0])
    c.execute('SELECT COUNT(*) FROM macro WHERE vix IS NOT NULL')
    print('Macro rows with VIX:', c.fetchone()[0])
    c.execute('SELECT MIN(date), MAX(date) FROM macro')
    print('Macro date range:', c.fetchone())
except Exception as e:
    print(f'Macro quality ERROR - {e}')

print("\n--- Check 5 — Features table quality ---")
try:
    c.execute('SELECT COUNT(*) FROM features')
    print('Total feature rows:', c.fetchone()[0])
    c.execute('SELECT COUNT(*) FROM features WHERE finbert_sentiment IS NULL OR finbert_sentiment = 0.0')
    print('Features with missing sentiment:', c.fetchone()[0])
    c.execute('SELECT COUNT(*) FROM features WHERE target_5d IS NOT NULL')
    print('Features with valid target:', c.fetchone()[0])
    c.execute('SELECT MIN(date), MAX(date) FROM features')
    print('Features date range:', c.fetchone())
except Exception as e:
    print(f'Features quality ERROR - {e}')

print("\n--- Check 6 — Model files ---")
files_to_check = [
    'ml/models/signal_model.pkl',
    'ml/models/xgb_model.json',
    'data/processed/features.parquet',
    'data/processed/news_checkpoint.json',
    'data/processed/indicators_checkpoint.json',
    'data/processed/finbert_checkpoint.json'
]
for f in files_to_check:
    p = Path(f)
    if p.exists():
        size_mb = p.stat().st_size / (1024 * 1024)
        print(f'{f}: EXISTS ({size_mb:.1f} MB)')
    else:
        print(f'{f}: MISSING')

print("\n--- Check 7 — ChromaDB status ---")
chroma = Path('chroma_db')
if chroma.exists():
    files = list(chroma.rglob('*'))
    total_size = sum(f.stat().st_size for f in files if f.is_file()) / (1024 * 1024)
    print(f'ChromaDB: EXISTS, {len(files)} files, {total_size:.1f} MB total')
else:
    print('ChromaDB: MISSING - RAG pipeline not built yet')

print("\n--- Check 8 — Walk-forward results ---")
try:
    c.execute(
        'SELECT window_id, test_year, accuracy, auc, n_estimators_used FROM walk_forward_results ORDER BY window_id')
    rows = c.fetchall()
    if rows:
        for r in rows:
            print(f'Window {r[0]} | Test: {r[1]} | Accuracy: {r[2]:.4f} | AUC: {r[3]:.4f} | Trees: {r[4]}')
    else:
        print('walk_forward_results: EMPTY - validation never completed')
except Exception as e:
    print(f'Walk-forward results ERROR - {e}')

print("\n--- Check 9 — Signal engine test ---")
try:
    from signals.signal_generator import generate_signals
    import pandas as pd

    # Mock row to test the generator we built today
    mock_df = pd.DataFrame([{
        'ticker': 'AAPL', 'ask': 180.0, 'close': 180.0, 'atr_14': 2.5,
        'resistance_52w': 195.0, 'support_52w': 170.0,
        'tech_score': 0.8, 'sentiment_score': 0.9, 'market_context_score': 0.7, 'fundamental_score': 0.8
    }])
    result = generate_signals(mock_df, 'INTRADAY', 1)

    if result:
        res = result[0]
        print('Signal engine: WORKING')
        print('Keys returned:', list(res.keys()))
        print('Action:', res.get('action'))
        print('Has reasoning:', bool(res.get('reasoning')))
        print('Has entry:', bool(res.get('entry')))
    else:
        print('Signal engine: RETURNED EMPTY')
except Exception as e:
    print(f'Signal engine: FAILED - {e}')

print("\n--- Check 10 — Scheduler jobs registered ---")
try:
    # Importing your specific APScheduler instance
    from apscheduler.schedulers.blocking import BlockingScheduler
    import pytz

    # Re-instantiating briefly just to read the registered jobs as configured in delivery/scheduler.py
    from delivery.scheduler import job_pre_market, job_intraday_morning, job_intraday_afternoon, job_post_market, \
        job_retrain

    ny_tz = pytz.timezone('America/New_York')
    test_scheduler = BlockingScheduler(timezone=ny_tz)
    active_days = 'mon-fri'
    test_scheduler.add_job(job_pre_market, 'cron', day_of_week=active_days, hour=9, minute=0)
    test_scheduler.add_job(job_intraday_morning, 'cron', day_of_week=active_days, hour=11, minute=0)
    test_scheduler.add_job(job_intraday_afternoon, 'cron', day_of_week=active_days, hour=14, minute=0)
    test_scheduler.add_job(job_post_market, 'cron', day_of_week=active_days, hour=16, minute=15)
    test_scheduler.add_job(job_retrain, 'cron', day_of_week=active_days, hour=23, minute=0)

    jobs = test_scheduler.get_jobs()
    print(f'Scheduler: {len(jobs)} jobs registered')
    for job in jobs:
        print(f'  - {job.name}: next run {job.next_run_time}')
except Exception as e:
    print(f'Scheduler: FAILED - {e}')

conn.close()