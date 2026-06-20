CREATE TABLE IF NOT EXISTS ohlcv (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume INTEGER, adj_close REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS indicators (
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    rsi_14 REAL, macd REAL, macd_signal REAL, macd_delta REAL,
    bb_upper REAL, bb_lower REAL, bb_position REAL,
    atr REAL, atr_normalized REAL,
    adx_14 REAL, obv REAL, obv_trend REAL,
    ema_200 REAL, volume_ratio REAL,
    dist_52w_high REAL, dist_52w_low REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,
    date DATE,
    headline TEXT,
    source TEXT,
    full_text TEXT,
    finbert_sentiment REAL,
    vader_sentiment REAL,
    sentiment_method TEXT,
    embedding_id TEXT
);

CREATE TABLE IF NOT EXISTS macro (
    date DATE PRIMARY KEY,
    fed_rate REAL,
    cpi REAL,
    gdp_growth REAL,
    unemployment REAL,
    vix REAL,
    spy_close REAL,
    spy_ema_200 REAL,
    spy_above_200ema INTEGER
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    mode TEXT NOT NULL,
    action TEXT NOT NULL,
    entry REAL,
    target REAL,
    stop_loss REAL,
    confidence REAL,
    technical_score REAL,
    fundamental_score REAL,
    sentiment_score REAL,
    market_context_score REAL,
    xgboost_probability REAL,
    reasoning TEXT,
    feature_snapshot TEXT,
    actual_outcome INTEGER,
    pct_change_actual REAL,
    sent_telegram_free INTEGER DEFAULT 0,
    sent_telegram_paid INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS walk_forward_results (
    window_id TEXT PRIMARY KEY,
    train_start DATE,
    train_end DATE,
    test_year TEXT,
    n_samples INTEGER,
    accuracy REAL,
    precision_score REAL,
    recall REAL,
    f1 REAL,
    auc REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id TEXT UNIQUE,
    gumroad_sale_id TEXT,
    email TEXT,
    tier TEXT DEFAULT 'paid',
    active INTEGER DEFAULT 1,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME
);