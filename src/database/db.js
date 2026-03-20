import pg from 'pg';

const { Pool } = pg;

const pool = new Pool({
  connectionString: 'postgresql://postgres:TlAzA0LAGt5JIaSI@db.ismflaoeenxbstgvfusw.supabase.co:5432/postgres',
  ssl: { rejectUnauthorized: false }
});

let stats = { total: 0, early: 0, confirmed: 0, sniper: 0, active: 0 };

export async function initDatabase() {
  try {
    await pool.query(`
      CREATE TABLE IF NOT EXISTS signals (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(50) NOT NULL,
        type VARCHAR(20) NOT NULL,
        tier VARCHAR(20) NOT NULL,
        timestamp TIMESTAMP DEFAULT NOW(),
        entry_price DECIMAL(20, 10),
        atr DECIMAL(20, 10),
        tp1 DECIMAL(20, 10),
        tp2 DECIMAL(20, 10),
        tp3 DECIMAL(20, 10),
        tp4 DECIMAL(20, 10),
        tp5 DECIMAL(20, 10),
        stop_loss DECIMAL(20, 10),
        tp1_rr DECIMAL(10, 2),
        tp2_rr DECIMAL(10, 2),
        tp3_rr DECIMAL(10, 2),
        price_change DECIMAL(10, 4),
        volume_spike DECIMAL(10, 2),
        momentum DECIMAL(10, 6),
        score DECIMAL(10, 2),
        factors TEXT,
        status VARCHAR(20) DEFAULT 'ACTIVE',
        closed_at TIMESTAMP,
        closed_price DECIMAL(20, 10)
      )
    `);
    
    await pool.query(`CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)`);
    await pool.query(`CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)`);
    await pool.query(`CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC)`);
    
    const countResult = await pool.query('SELECT COUNT(*) FROM signals');
    console.log(`✅ Database connected (${countResult.rows[0].count} signals)`);
  } catch (error) {
    console.error('Database init error:', error.message);
  }
}

export async function createSignal(data) {
  try {
    const result = await pool.query(`
      INSERT INTO signals (symbol, type, tier, entry_price, atr, tp1, tp2, tp3, tp4, tp5, stop_loss, tp1_rr, tp2_rr, tp3_rr, price_change, volume_spike, momentum, score, factors, status)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
      RETURNING *
    `, [
      data.symbol,
      data.type,
      data.tier,
      data.entryPrice,
      data.atr,
      data.targets?.tp1,
      data.targets?.tp2,
      data.targets?.tp3,
      data.targets?.tp4,
      data.targets?.tp5,
      data.stopLoss,
      data.riskReward?.tp1 ? parseFloat(data.riskReward.tp1) : null,
      data.riskReward?.tp2 ? parseFloat(data.riskReward.tp2) : null,
      data.riskReward?.tp3 ? parseFloat(data.riskReward.tp3) : null,
      parseFloat(data.metrics?.priceChange),
      parseFloat(data.metrics?.volumeSpike),
      data.metrics?.momentum ? parseFloat(data.metrics.momentum) : null,
      data.metrics?.score || data.score,
      JSON.stringify(data.factors || []),
      data.status || 'ACTIVE'
    ]);
    
    stats.total++;
    if (data.tier === 'EARLY') stats.early++;
    if (data.tier === 'CONFIRMED') stats.confirmed++;
    if (data.tier === 'SNIPER') stats.sniper++;
    
    return formatSignal(result.rows[0]);
  } catch (error) {
    console.error('Create signal error:', error.message);
    return null;
  }
}

export async function getSignals(limit = 100, status = null) {
  try {
    let query = 'SELECT * FROM signals';
    const params = [];
    
    if (status) {
      query += ' WHERE status = $1';
      params.push(status);
    }
    
    query += ' ORDER BY timestamp DESC LIMIT $' + (params.length + 1);
    params.push(limit);
    
    const result = await pool.query(query, params);
    return result.rows.map(formatSignal);
  } catch (error) {
    console.error('Get signals error:', error.message);
    return [];
  }
}

export async function getSignalBySymbol(symbol) {
  try {
    const result = await pool.query(
      'SELECT * FROM signals WHERE symbol = $1 AND status IN ($2, $3) ORDER BY timestamp DESC LIMIT 1',
      [symbol, 'ACTIVE', 'HOT']
    );
    return result.rows[0] ? formatSignal(result.rows[0]) : null;
  } catch (error) {
    console.error('Get signal by symbol error:', error.message);
    return null;
  }
}

export async function updateSignalStatus(id, status, closedPrice = null) {
  try {
    const result = await pool.query(
      'UPDATE signals SET status = $1, closed_at = NOW(), closed_price = $2 WHERE id = $3 RETURNING *',
      [status, closedPrice, id]
    );
    return result.rows[0] ? formatSignal(result.rows[0]) : null;
  } catch (error) {
    console.error('Update signal status error:', error.message);
    return null;
  }
}

export async function getSignalStats() {
  try {
    const [total, active, tpHits, stoppedOut, tierCounts] = await Promise.all([
      pool.query('SELECT COUNT(*) FROM signals'),
      pool.query("SELECT COUNT(*) FROM signals WHERE status IN ('ACTIVE', 'HOT', 'WATCHLIST')"),
      pool.query("SELECT COUNT(*) FROM signals WHERE status LIKE 'TP%'"),
      pool.query("SELECT COUNT(*) FROM signals WHERE status = 'STOPPED_OUT'"),
      pool.query('SELECT tier, COUNT(*) FROM signals GROUP BY tier')
    ]);
    
    const counts = { SNIPER: 0, CONFIRMED: 0, EARLY: 0 };
    tierCounts.rows.forEach(row => {
      if (counts.hasOwnProperty(row.tier)) {
        counts[row.tier] = parseInt(row.count);
      }
    });
    
    return {
      total: parseInt(total.rows[0].count),
      active: parseInt(active.rows[0].count),
      tpHits: parseInt(tpHits.rows[0].count),
      stoppedOut: parseInt(stoppedOut.rows[0].count),
      tierCounts: counts
    };
  } catch (error) {
    console.error('Get stats error:', error.message);
    return { total: stats.total, active: 0, tpHits: 0, stoppedOut: 0, tierCounts: { SNIPER: 0, CONFIRMED: 0, EARLY: 0 } };
  }
}

export async function closeDatabase() {
  await pool.end();
}

function formatSignal(row) {
  return {
    id: row.id,
    symbol: row.symbol,
    type: row.type,
    tier: row.tier,
    timestamp: new Date(row.timestamp).getTime(),
    entryPrice: parseFloat(row.entry_price),
    atr: row.atr ? parseFloat(row.atr) : null,
    targets: {
      tp1: row.tp1 ? parseFloat(row.tp1) : null,
      tp2: row.tp2 ? parseFloat(row.tp2) : null,
      tp3: row.tp3 ? parseFloat(row.tp3) : null,
      tp4: row.tp4 ? parseFloat(row.tp4) : null,
      tp5: row.tp5 ? parseFloat(row.tp5) : null
    },
    stopLoss: row.stop_loss ? parseFloat(row.stop_loss) : null,
    riskReward: {
      tp1: row.tp1_rr ? parseFloat(row.tp1_rr) : null,
      tp2: row.tp2_rr ? parseFloat(row.tp2_rr) : null,
      tp3: row.tp3_rr ? parseFloat(row.tp3_rr) : null
    },
    metrics: {
      priceChange: row.price_change ? parseFloat(row.price_change) : null,
      volumeSpike: row.volume_spike ? parseFloat(row.volume_spike) : null,
      momentum: row.momentum ? parseFloat(row.momentum) : null,
      score: row.score ? parseFloat(row.score) : null
    },
    factors: row.factors ? JSON.parse(row.factors) : [],
    status: row.status,
    closedAt: row.closed_at ? new Date(row.closed_at).getTime() : null,
    closedPrice: row.closed_price ? parseFloat(row.closed_price) : null
  };
}
