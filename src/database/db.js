import { readFileSync, writeFileSync, existsSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DB_PATH = join(__dirname, '../../data/signals.json');

let signals = [];
let stats = { total: 0, early: 0, confirmed: 0, sniper: 0, active: 0 };

export function initDatabase() {
  try {
    if (!existsSync(join(__dirname, '../../data'))) {
      require('fs').mkdirSync(join(__dirname, '../../data'), { recursive: true });
    }
    if (existsSync(DB_PATH)) {
      const data = JSON.parse(readFileSync(DB_PATH, 'utf8'));
      signals = data.signals || [];
      stats = data.stats || stats;
    }
    console.log('✅ Database initialized (JSON file)');
  } catch (error) {
    console.log('✅ Database initialized (fresh)');
  }
}

export function saveDatabase() {
  try {
    writeFileSync(DB_PATH, JSON.stringify({ signals, stats }, null, 2));
  } catch (error) {
    console.error('Failed to save database:', error);
  }
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
    tp1: data.targets?.tp1,
    tp2: data.targets?.tp2,
    tp3: data.targets?.tp3,
    tp4: data.targets?.tp4,
    tp5: data.targets?.tp5,
    stopLoss: data.stopLoss,
    tp1RR: data.riskReward?.tp1 ? parseFloat(data.riskReward.tp1) : null,
    tp2RR: data.riskReward?.tp2 ? parseFloat(data.riskReward.tp2) : null,
    tp3RR: data.riskReward?.tp3 ? parseFloat(data.riskReward.tp3) : null,
    priceChange: parseFloat(data.metrics?.priceChange),
    volumeSpike: parseFloat(data.metrics?.volumeSpike),
    momentum: data.metrics?.momentum ? parseFloat(data.metrics.momentum) : null,
    score: data.metrics?.score || data.score,
    factors: JSON.stringify(data.factors || []),
    status: data.status || 'ACTIVE'
  };
  
  signals.unshift(signal);
  if (signals.length > 500) signals.pop();
  
  stats.total++;
  if (data.tier === 'EARLY') stats.early++;
  if (data.tier === 'CONFIRMED') stats.confirmed++;
  if (data.tier === 'SNIPER') stats.sniper++;
  
  saveDatabase();
  return signal;
}

export async function getSignals(limit = 100, status = null) {
  let filtered = signals;
  if (status) {
    filtered = signals.filter(s => s.status === status);
  }
  return filtered.slice(0, limit);
}

export async function getSignalBySymbol(symbol) {
  return signals.find(s => s.symbol === symbol && (s.status === 'ACTIVE' || s.status === 'HOT'));
}

export async function updateSignalStatus(id, status, closedPrice = null) {
  const signal = signals.find(s => s.id === id);
  if (signal) {
    signal.status = status;
    signal.closedAt = closedPrice ? new Date().toISOString() : null;
    signal.closedPrice = closedPrice;
    saveDatabase();
  }
  return signal;
}

export async function getSignalStats() {
  const active = signals.filter(s => s.status === 'ACTIVE' || s.status === 'HOT' || s.status === 'WATCHLIST').length;
  const tpHits = signals.filter(s => s.status?.startsWith('TP')).length;
  const stoppedOut = signals.filter(s => s.status === 'STOPPED_OUT').length;
  
  return {
    total: stats.total,
    active,
    tpHits,
    stoppedOut,
    tierCounts: {
      SNIPER: stats.sniper,
      CONFIRMED: stats.confirmed,
      EARLY: stats.early
    }
  };
}

export async function closeDatabase() {
  saveDatabase();
}
