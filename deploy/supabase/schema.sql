-- ============================================================
-- BINANCE SIGNAL ENGINE - COMPLETE DATABASE SCHEMA
-- ============================================================

-- Drop existing tables (if recreating)
DROP TABLE IF EXISTS analytics CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS signals CASCADE;
DROP TABLE IF EXISTS pairs CASCADE;
DROP TABLE IF EXISTS settings CASCADE;

-- ============================================================
-- 1. PAIRS TABLE (Tracked trading pairs)
-- ============================================================
CREATE TABLE pairs (
    id SERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL DEFAULT 'USDT',
    sector TEXT DEFAULT 'OTHER',
    is_active BOOLEAN DEFAULT TRUE,
    volume_24h NUMERIC DEFAULT 0,
    price_change_24h NUMERIC DEFAULT 0,
    last_price NUMERIC DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 2. SIGNALS TABLE (Trading signals)
-- ============================================================
CREATE TABLE signals (
    id SERIAL PRIMARY KEY,
    pair_id INTEGER REFERENCES pairs(id),
    pair TEXT NOT NULL,
    signal TEXT NOT NULL CHECK (signal IN ('BUY', 'SELL', 'NO TRADE')),
    
    -- Price levels
    entry NUMERIC,
    sl NUMERIC,
    tp1 NUMERIC,
    tp2 NUMERIC,
    tp3 NUMERIC,
    
    -- Confidence scoring
    confidence INTEGER CHECK (confidence >= 0 AND confidence <= 100),
    tier TEXT CHECK (tier IN ('SNIPER', 'ELITE', 'STANDARD', 'WATCH', 'REJECT')),
    
    -- Market analysis
    regime TEXT,
    trend_strength NUMERIC,
    atr_ratio NUMERIC,
    
    -- Technical indicators
    rsi NUMERIC,
    macd NUMERIC,
    adx NUMERIC,
    ema_slope NUMERIC,
    
    -- SMC analysis
    smc_type TEXT,
    smc_score NUMERIC,
    bos_level NUMERIC,
    choch_level NUMERIC,
    sweep_level NUMERIC,
    ob_zone JSONB,
    fvg_zone JSONB,
    
    -- Volume analysis
    volume_score NUMERIC,
    volume_zscore NUMERIC,
    poc NUMERIC,
    vah NUMERIC,
    val NUMERIC,
    
    -- Whale/OI analysis
    whale_score NUMERIC,
    whale_signal TEXT,
    oi_score NUMERIC,
    oi_signal TEXT,
    oi_change_pct NUMERIC,
    
    -- Liquidation analysis
    liquidation_score NUMERIC,
    liquidation_type TEXT,
    
    -- Risk management
    risk_pct NUMERIC,
    rr_ratio NUMERIC,
    position_size NUMERIC,
    
    -- Execution tracking
    executed BOOLEAN DEFAULT FALSE,
    executed_at TIMESTAMP WITH TIME ZONE,
    executed_price NUMERIC,
    trade_id INTEGER,
    
    -- Metadata
    timeframe TEXT DEFAULT '1h',
    source TEXT DEFAULT 'engine',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 3. TRADES TABLE (Executed trades)
-- ============================================================
CREATE TABLE trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER REFERENCES signals(id),
    pair_id INTEGER REFERENCES pairs(id),
    pair TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    
    -- Entry
    entry NUMERIC NOT NULL,
    entry_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Stop Loss
    sl NUMERIC,
    sl_hit BOOLEAN DEFAULT FALSE,
    sl_hit_time TIMESTAMP WITH TIME ZONE,
    
    -- Take Profits
    tp1 NUMERIC,
    tp1_hit BOOLEAN DEFAULT FALSE,
    tp1_hit_time TIMESTAMP WITH TIME ZONE,
    tp1_pct_closed NUMERIC DEFAULT 50,
    
    tp2 NUMERIC,
    tp2_hit BOOLEAN DEFAULT FALSE,
    tp2_hit_time TIMESTAMP WITH TIME ZONE,
    tp2_pct_closed NUMERIC DEFAULT 30,
    
    tp3 NUMERIC,
    tp3_hit BOOLEAN DEFAULT FALSE,
    tp3_hit_time TIMESTAMP WITH TIME ZONE,
    tp3_pct_closed NUMERIC DEFAULT 20,
    
    -- Exit
    exit_price NUMERIC,
    exit_time TIMESTAMP WITH TIME ZONE,
    
    -- PnL
    pnl NUMERIC,
    pnl_pct NUMERIC,
    fees NUMERIC DEFAULT 0,
    net_pnl NUMERIC,
    
    -- Status
    status TEXT DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'TP1', 'TP2', 'TP3', 'SL', 'MANUAL_CLOSE', 'EXPIRED')),
    
    -- Risk management
    leverage NUMERIC DEFAULT 1,
    margin_used NUMERIC,
    risk_reward NUMERIC,
    
    -- Metadata
    strategy TEXT,
    confidence_at_entry INTEGER,
    regime_at_entry TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 4. ANALYTICS TABLE (Performance metrics)
-- ============================================================
CREATE TABLE analytics (
    id SERIAL PRIMARY KEY,
    metric TEXT NOT NULL,
    value NUMERIC,
    
    -- Categorization
    category TEXT CHECK (category IN ('performance', 'risk', 'volume', 'quality')),
    timeframe TEXT CHECK (timeframe IN ('1h', '4h', '1d', '7d', '30d', 'all')),
    
    -- Metadata
    pair TEXT,
    strategy TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- 5. SETTINGS TABLE (System configuration)
-- ============================================================
CREATE TABLE settings (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    value_numeric NUMERIC,
    value_boolean BOOLEAN,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- INDEXES (Performance optimization)
-- ============================================================
CREATE INDEX idx_pairs_active ON pairs (is_active);
CREATE INDEX idx_pairs_sector ON pairs (sector);

CREATE INDEX idx_signals_created ON signals (created_at DESC);
CREATE INDEX idx_signals_pair ON signals (pair);
CREATE INDEX idx_signals_executed ON signals (executed);
CREATE INDEX idx_signals_tier ON signals (tier);
CREATE INDEX idx_signals_confidence ON signals (confidence DESC);
CREATE INDEX idx_signals_regime ON signals (regime);
CREATE INDEX idx_signals_smc ON signals (smc_score DESC);
CREATE INDEX idx_signals_timeframe ON signals (timeframe);

CREATE INDEX idx_trades_status ON trades (status);
CREATE INDEX idx_trades_pair ON trades (pair);
CREATE INDEX idx_trades_created ON trades (created_at DESC);
CREATE INDEX idx_trades_pnl ON trades (pnl);
CREATE INDEX idx_trades_direction ON trades (direction);

CREATE INDEX idx_analytics_metric ON analytics (metric, created_at DESC);
CREATE INDEX idx_analytics_category ON analytics (category);
CREATE INDEX idx_analytics_timeframe ON analytics (timeframe);

-- ============================================================
-- VIEWS (Common queries)
-- ============================================================

-- Active signals view
CREATE VIEW v_active_signals AS
SELECT * FROM signals
WHERE executed = FALSE
AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY confidence DESC;

-- Performance summary view
CREATE VIEW v_performance_summary AS
SELECT 
    pair,
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
    SUM(pnl) as total_pnl,
    AVG(pnl_pct) as avg_pnl_pct,
    AVG(confidence_at_entry) as avg_confidence,
    MAX(pnl) as best_trade,
    MIN(pnl) as worst_trade
FROM trades
WHERE status != 'OPEN'
GROUP BY pair;

-- Daily performance view
CREATE VIEW v_daily_performance AS
SELECT 
    DATE(created_at) as date,
    COUNT(*) as signals_generated,
    COUNT(CASE WHEN executed THEN 1 END) as trades_taken,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
    AVG(confidence) as avg_confidence
FROM signals
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ============================================================
-- FUNCTIONS (Stored procedures)
-- ============================================================

-- Calculate win rate
CREATE OR REPLACE FUNCTION get_win_rate(
    p_pair TEXT DEFAULT NULL,
    p_days INTEGER DEFAULT 30
)
RETURNS NUMERIC AS $$
DECLARE
    v_wins INTEGER;
    v_total INTEGER;
BEGIN
    SELECT 
        COUNT(CASE WHEN pnl > 0 THEN 1 END),
        COUNT(*)
    INTO v_wins, v_total
    FROM trades
    WHERE status != 'OPEN'
    AND created_at > NOW() - (p_days || ' days')::INTERVAL
    AND (p_pair IS NULL OR pair = p_pair);
    
    RETURN CASE WHEN v_total > 0 THEN (v_wins::NUMERIC / v_total) * 100 ELSE 0 END;
END;
$$ LANGUAGE plpgsql;

-- Calculate profit factor
CREATE OR REPLACE FUNCTION get_profit_factor(
    p_days INTEGER DEFAULT 30
)
RETURNS NUMERIC AS $$
DECLARE
    v_gross_profit NUMERIC;
    v_gross_loss NUMERIC;
BEGIN
    SELECT 
        COALESCE(SUM(CASE WHEN pnl > 0 THEN pnl ELSE 0 END), 0),
        COALESCE(ABS(SUM(CASE WHEN pnl < 0 THEN pnl ELSE 0 END)), 0)
    INTO v_gross_profit, v_gross_loss
    FROM trades
    WHERE status != 'OPEN'
    AND created_at > NOW() - (p_days || ' days')::INTERVAL;
    
    RETURN CASE WHEN v_gross_loss > 0 THEN v_gross_profit / v_gross_loss ELSE 0 END;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================

-- Enable RLS
ALTER TABLE pairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;

-- Public read policies
CREATE POLICY "Allow public reads on pairs" ON pairs
    FOR SELECT TO anon USING (true);

CREATE POLICY "Allow public reads on signals" ON signals
    FOR SELECT TO anon USING (true);

CREATE POLICY "Allow public reads on trades" ON trades
    FOR SELECT TO anon USING (true);

CREATE POLICY "Allow public reads on analytics" ON analytics
    FOR SELECT TO anon USING (true);

CREATE POLICY "Allow public reads on settings" ON settings
    FOR SELECT TO anon USING (true);

-- Service role write policies
CREATE POLICY "Allow service writes on pairs" ON pairs
    FOR ALL TO service_role USING (true);

CREATE POLICY "Allow service writes on signals" ON signals
    FOR ALL TO service_role USING (true);

CREATE POLICY "Allow service writes on trades" ON trades
    FOR ALL TO service_role USING (true);

CREATE POLICY "Allow service writes on analytics" ON analytics
    FOR ALL TO service_role USING (true);

CREATE POLICY "Allow service writes on settings" ON settings
    FOR ALL TO service_role USING (true);

-- ============================================================
-- REALTIME (Enable for tables)
-- ============================================================

ALTER PUBLICATION supabase_realtime ADD TABLE signals;
ALTER PUBLICATION supabase_realtime ADD TABLE trades;
ALTER PUBLICATION supabase_realtime ADD TABLE analytics;

-- ============================================================
-- SEED DATA
-- ============================================================

-- Insert default settings
INSERT INTO settings (key, value, value_numeric, value_boolean, description) VALUES
    ('min_confidence', '75', 75, NULL, 'Minimum confidence to emit signal'),
    ('sniper_mode', 'true', NULL, TRUE, 'Only emit sniper signals'),
    ('max_signals_per_day', '10', 10, NULL, 'Maximum signals per day'),
    ('max_open_trades', '3', 3, NULL, 'Maximum concurrent trades'),
    ('risk_per_trade', '0.01', 0.01, NULL, 'Risk percentage per trade'),
    ('max_drawdown', '0.05', 0.05, NULL, 'Maximum drawdown before kill switch'),
    ('telegram_enabled', 'true', NULL, TRUE, 'Enable Telegram alerts'),
    ('auto_trade', 'false', NULL, FALSE, 'Auto-execute trades'),
    ('paper_trading', 'true', NULL, TRUE, 'Use paper trading mode');

-- Insert default pairs
INSERT INTO pairs (symbol, base_asset, sector, is_active) VALUES
    ('BTCUSDT', 'BTC', 'L1', TRUE),
    ('ETHUSDT', 'ETH', 'L1', TRUE),
    ('BNBUSDT', 'BNB', 'L1', TRUE),
    ('SOLUSDT', 'SOL', 'L1', TRUE),
    ('ADAUSDT', 'ADA', 'L1', TRUE),
    ('XRPUSDT', 'XRP', 'L1', TRUE),
    ('DOTUSDT', 'DOT', 'L1', TRUE),
    ('MATICUSDT', 'MATIC', 'L1', TRUE),
    ('AVAXUSDT', 'AVAX', 'L1', TRUE),
    ('LINKUSDT', 'LINK', 'L1', TRUE);

-- ============================================================
-- TRIGGERS
-- ============================================================

-- Update timestamp on signal update
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_signals_updated_at
    BEFORE UPDATE ON signals
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_trades_updated_at
    BEFORE UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pairs_updated_at
    BEFORE UPDATE ON pairs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- COMPLETION
-- ============================================================

SELECT 'Database schema created successfully!' as status;
