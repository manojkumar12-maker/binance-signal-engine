import pg from 'pg';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { initRedis, cacheGet, cacheSet, invalidateSignalCache, closeRedis, CACHE_TTL } from './redis.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, '../../data');
const SIGNALS_FILE = join(DATA_DIR, 'signals.json');
const STATS_FILE = join(DATA_DIR, 'stats.json');

let pool = null;
let usePostgres = false;

// JSON fallback state
let jsonSignals = [];
let jsonStats = { total: 0, early: 0, confirmed: 0, sniper: 0, prePump: 0, active: 0 };
let initialized = false;

// ─── PostgreSQL Setup ─────────────────────────────────────────

const CREATE_TABLE_SQL = `
  CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    type TEXT,
    tier TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    entry_price DOUBLE PRECISION,
    atr DOUBLE PRECISION,
    tp1 DOUBLE PRECISION, tp2 DOUBLE PRECISION, tp3 DOUBLE PRECISION,
    tp4 DOUBLE PRECISION, tp5 DOUBLE PRECISION,
    stop_loss DOUBLE PRECISION,
    risk_reward JSONB,
    metrics JSONB,
    factors JSONB,
    status TEXT DEFAULT 'ACTIVE',
    confidence DOUBLE PRECISION,
    closed_at TIMESTAMPTZ,
    closed_price DOUBLE PRECISION,
    price_change DOUBLE PRECISION,
    volume_spike DOUBLE PRECISION,
    rank_score DOUBLE PRECISION,
    oi_change DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
  );

  CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
  CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
  CREATE INDEX IF NOT EXISTS idx_signals_tier ON signals(tier);
  CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
`;

async function initPostgres() {
  const databaseUrl = process.env.DATABASE_URL;
  
  console.log('🔍 DATABASE_URL available:', !!databaseUrl);
  
  if (!databaseUrl) return false;

  try {
    console.log('🔄 Attempting PostgreSQL connection...');
    
    pool = new pg.Pool({
      connectionString: databaseUrl,
      ssl: { rejectUnauthorized: false },
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 10000
    });

    const client = await pool.connect();
    await client.query(CREATE_TABLE_SQL);
    client.release();

    console.log('✅ PostgreSQL connected');
    return true;
  } catch (error) {
    console.error('⚠️ PostgreSQL connection failed:', error.message);
    console.log('↩️ Falling back to JSON file storage');
    pool = null;
    return false;
  }
}

// ─── JSON Fallback ────────────────────────────────────────────

function ensureDataDir() {
  if (!existsSync(DATA_DIR)) {
    mkdirSync(DATA_DIR, { recursive: true });
  }
}

function loadJsonData() {
  try {
    ensureDataDir();
    if (existsSync(SIGNALS_FILE)) {
      jsonSignals = JSON.parse(readFileSync(SIGNALS_FILE, 'utf8'));
    }
    if (existsSync(STATS_FILE)) {
      jsonStats = JSON.parse(readFileSync(STATS_FILE, 'utf8'));
    }
  } catch {
    jsonSignals = [];
    jsonStats = { total: 0, early: 0, confirmed: 0, sniper: 0, prePump: 0, active: 0 };
  }
}

function saveJsonData() {
  try {
    ensureDataDir();
    writeFileSync(SIGNALS_FILE, JSON.stringify(jsonSignals, null, 2));
    writeFileSync(STATS_FILE, JSON.stringify(jsonStats, null, 2));
  } catch {
    // silent fail
  }
}

// ─── Public API ───────────────────────────────────────────────

export async function initDatabase() {
  usePostgres = await initPostgres();
  await initRedis();

  if (!usePostgres) {
    loadJsonData();
    console.log(`✅ Database initialized — JSON fallback (${jsonSignals.length} signals)`);
  } else {
    const result = await pool.query('SELECT COUNT(*) as count FROM signals');
    console.log(`✅ Database initialized — PostgreSQL (${result.rows[0].count} signals)`);
  }
  initialized = true;
}

export async function createSignal(data) {
  const signal = {
    id: `sig_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    symbol: data.symbol,
    type: data.type,
    tier: data.tier,
    timestamp: new Date().toISOString(),
    entryPrice: data.entryPrice,
    atr: data.atr,
    targets: {
      tp1: data.targets?.tp1,
      tp2: data.targets?.tp2,
      tp3: data.targets?.tp3,
      tp4: data.targets?.tp4,
      tp5: data.targets?.tp5
    },
    stopLoss: data.stopLoss,
    riskReward: data.riskReward,
    metrics: data.metrics,
    factors: data.factors || [],
    status: data.status || 'ACTIVE',
    confidence: data.confidence,
    priceChange: data.metrics?.priceChange,
    volumeSpike: data.metrics?.volumeSpike,
    rankScore: data.rankScore,
    oiChange: data.oiChange
  };

  if (usePostgres && pool) {
    try {
      await pool.query(
        `INSERT INTO signals (id, symbol, type, tier, timestamp, entry_price, atr,
          tp1, tp2, tp3, tp4, tp5, stop_loss, risk_reward, metrics, factors,
          status, confidence, price_change, volume_spike, rank_score, oi_change)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)`,
        [
          signal.id, signal.symbol, signal.type, signal.tier, signal.timestamp,
          signal.entryPrice, signal.atr,
          signal.targets.tp1, signal.targets.tp2, signal.targets.tp3,
          signal.targets.tp4, signal.targets.tp5,
          signal.stopLoss,
          JSON.stringify(signal.riskReward),
          JSON.stringify(signal.metrics),
          JSON.stringify(signal.factors),
          signal.status, signal.confidence,
          signal.priceChange, signal.volumeSpike, signal.rankScore, signal.oiChange
        ]
      );
      await invalidateSignalCache();
    } catch (error) {
      console.error('DB insert error:', error.message);
    }
  } else {
    jsonSignals.unshift(signal);
    if (jsonSignals.length > 500) jsonSignals.pop();
    jsonStats.total++;
    if (data.tier === 'EARLY') jsonStats.early++;
    if (data.tier === 'CONFIRMED') jsonStats.confirmed++;
    if (data.tier === 'SNIPER') jsonStats.sniper++;
    if (data.tier === 'PRE_PUMP') jsonStats.prePump++;
    if (initialized) saveJsonData();
  }

  return signal;
}

export async function getSignals(limit = 100, status = null) {
  // Try Redis cache first
  const cacheKey = `signals:${status || 'all'}:${limit}`;
  const cached = await cacheGet(cacheKey);
  if (cached) return cached;

  let result;
  if (usePostgres && pool) {
    try {
      let query = 'SELECT * FROM signals';
      const params = [];
      if (status) {
        query += ' WHERE status = $1';
        params.push(status);
      }
      query += ' ORDER BY timestamp DESC LIMIT $' + (params.length + 1);
      params.push(limit);

      const res = await pool.query(query, params);
      result = res.rows.map(formatPgSignal);
    } catch (error) {
      console.error('DB query error:', error.message);
      result = [];
    }
  } else {
    if (status) {
      result = jsonSignals.filter(s => s.status === status).slice(0, limit);
    } else {
      result = jsonSignals.slice(0, limit);
    }
  }

  await cacheSet(cacheKey, result, CACHE_TTL.recentSignals);
  return result;
}

export async function getSignalBySymbol(symbol) {
  if (usePostgres && pool) {
    try {
      const res = await pool.query(
        "SELECT * FROM signals WHERE symbol = $1 AND status IN ('ACTIVE','HOT') ORDER BY timestamp DESC LIMIT 1",
        [symbol]
      );
      return res.rows[0] ? formatPgSignal(res.rows[0]) : null;
    } catch {
      return null;
    }
  }
  return jsonSignals.find(s => s.symbol === symbol && (s.status === 'ACTIVE' || s.status === 'HOT'));
}

export async function updateSignalStatus(id, status, closedPrice = null) {
  if (usePostgres && pool) {
    try {
      const res = await pool.query(
        `UPDATE signals SET status = $1, closed_price = $2, closed_at = $3 WHERE id = $4 OR symbol = $4 RETURNING *`,
        [status, closedPrice, closedPrice ? new Date().toISOString() : null, id]
      );
      await invalidateSignalCache();
      return res.rows[0] ? formatPgSignal(res.rows[0]) : null;
    } catch (error) {
      console.error('DB update error:', error.message);
      return null;
    }
  }

  const signal = jsonSignals.find(s => s.id === id || s.symbol === id);
  if (signal) {
    signal.status = status;
    signal.closedAt = closedPrice ? new Date().toISOString() : null;
    signal.closedPrice = closedPrice;
    if (initialized) saveJsonData();
  }
  return signal;
}

export async function getSignalStats() {
  // Try Redis cache first
  const cached = await cacheGet('signals:stats');
  if (cached) return cached;

  let result;
  if (usePostgres && pool) {
    try {
      const totalRes = await pool.query('SELECT COUNT(*) as count FROM signals');
      const activeRes = await pool.query("SELECT COUNT(*) as count FROM signals WHERE status IN ('ACTIVE','HOT','WATCHLIST')");
      const tpRes = await pool.query("SELECT COUNT(*) as count FROM signals WHERE status LIKE 'TP%'");
      const slRes = await pool.query("SELECT COUNT(*) as count FROM signals WHERE status = 'STOPPED_OUT'");
      const tierRes = await pool.query("SELECT tier, COUNT(*) as count FROM signals GROUP BY tier");

      const tierCounts = {};
      for (const row of tierRes.rows) {
        tierCounts[row.tier] = parseInt(row.count);
      }

      result = {
        total: parseInt(totalRes.rows[0].count),
        active: parseInt(activeRes.rows[0].count),
        tpHits: parseInt(tpRes.rows[0].count),
        stoppedOut: parseInt(slRes.rows[0].count),
        tierCounts
      };
    } catch (error) {
      console.error('DB stats error:', error.message);
      result = { total: 0, active: 0, tpHits: 0, stoppedOut: 0, tierCounts: {} };
    }
  } else {
    const active = jsonSignals.filter(s => s.status === 'ACTIVE' || s.status === 'HOT' || s.status === 'WATCHLIST').length;
    const tpHits = jsonSignals.filter(s => s.status?.startsWith('TP')).length;
    const stoppedOut = jsonSignals.filter(s => s.status === 'STOPPED_OUT').length;

    result = {
      total: jsonStats.total,
      active,
      tpHits,
      stoppedOut,
      tierCounts: {
        SNIPER: jsonStats.sniper,
        CONFIRMED: jsonStats.confirmed,
        EARLY: jsonStats.early,
        PRE_PUMP: jsonStats.prePump
      }
    };
  }

  await cacheSet('signals:stats', result, CACHE_TTL.stats);
  return result;
}

export async function closeDatabase() {
  if (!usePostgres) saveJsonData();
  if (pool) {
    try { await pool.end(); } catch { /* silent */ }
  }
  await closeRedis();
}

// ─── Helpers ──────────────────────────────────────────────────

function formatPgSignal(row) {
  return {
    id: row.id,
    symbol: row.symbol,
    type: row.type,
    tier: row.tier,
    timestamp: row.timestamp instanceof Date ? row.timestamp.toISOString() : row.timestamp,
    entryPrice: row.entry_price,
    atr: row.atr,
    targets: {
      tp1: row.tp1, tp2: row.tp2, tp3: row.tp3, tp4: row.tp4, tp5: row.tp5
    },
    stopLoss: row.stop_loss,
    riskReward: row.risk_reward,
    metrics: row.metrics,
    factors: row.factors,
    status: row.status,
    confidence: row.confidence,
    closedAt: row.closed_at,
    closedPrice: row.closed_price,
    priceChange: row.price_change,
    volumeSpike: row.volume_spike,
    rankScore: row.rank_score,
    oiChange: row.oi_change
  };
}
