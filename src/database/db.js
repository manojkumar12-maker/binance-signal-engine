import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, '../../data');
const SIGNALS_FILE = join(DATA_DIR, 'signals.json');
const STATS_FILE = join(DATA_DIR, 'stats.json');

let signals = [];
let stats = { total: 0, early: 0, confirmed: 0, sniper: 0, prePump: 0, active: 0 };
let initialized = false;

function ensureDataDir() {
  if (!existsSync(DATA_DIR)) {
    mkdirSync(DATA_DIR, { recursive: true });
  }
}

function loadData() {
  try {
    ensureDataDir();
    if (existsSync(SIGNALS_FILE)) {
      signals = JSON.parse(readFileSync(SIGNALS_FILE, 'utf8'));
    }
    if (existsSync(STATS_FILE)) {
      stats = JSON.parse(readFileSync(STATS_FILE, 'utf8'));
    }
  } catch (e) {
    signals = [];
    stats = { total: 0, early: 0, confirmed: 0, sniper: 0, prePump: 0, active: 0 };
  }
}

function saveData() {
  try {
    ensureDataDir();
    writeFileSync(SIGNALS_FILE, JSON.stringify(signals, null, 2));
    writeFileSync(STATS_FILE, JSON.stringify(stats, null, 2));
  } catch (e) {
    // Silently fail - don't crash the app
  }
}

export async function initDatabase() {
  loadData();
  console.log(`✅ Database initialized (${signals.length} signals, ${stats.total} total)`);
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
    confidence: data.confidence
  };
  
  signals.unshift(signal);
  if (signals.length > 500) signals.pop();
  
  stats.total++;
  if (data.tier === 'EARLY') stats.early++;
  if (data.tier === 'CONFIRMED') stats.confirmed++;
  if (data.tier === 'SNIPER') stats.sniper++;
  if (data.tier === 'PRE_PUMP') stats.prePump++;
  
  if (initialized) saveData();
  return signal;
}

export async function getSignals(limit = 100, status = null) {
  if (status) {
    return signals.filter(s => s.status === status).slice(0, limit);
  }
  return signals.slice(0, limit);
}

export async function getSignalBySymbol(symbol) {
  return signals.find(s => s.symbol === symbol && (s.status === 'ACTIVE' || s.status === 'HOT'));
}

export async function updateSignalStatus(id, status, closedPrice = null) {
  const signal = signals.find(s => s.id === id || s.symbol === id);
  if (signal) {
    signal.status = status;
    signal.closedAt = closedPrice ? new Date().toISOString() : null;
    signal.closedPrice = closedPrice;
    if (initialized) saveData();
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
      EARLY: stats.early,
      PRE_PUMP: stats.prePump
    }
  };
}

export async function closeDatabase() {
  saveData();
}
