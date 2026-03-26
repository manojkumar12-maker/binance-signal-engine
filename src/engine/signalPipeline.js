const STAGES = {
  WATCH: 'WATCH',
  BUILDING: 'BUILDING',
  ENTRY: 'ENTRY',
  EXPLOSION: 'EXPLOSION'
};

const stateMap = new Map();
let oiTrackerModule = null;
let avgMarketOI = 0.1;

const oiRanking = new Map();
const SIGNAL_COOLDOWN = 2 * 60 * 1000;
const lastSignalTime = {};

const symbolScores = new Map();
const MIN_SIGNAL_SCORE = 20;
const MAX_ACTIVE_SIGNALS = 10;

let btcPriceChange = 0;

export function setOITracker(tracker) {
  oiTrackerModule = tracker;
}

export function updateBTCPrice(btcChange) {
  btcPriceChange = btcChange;
}

function normalizeOI(oi, allOI) {
  if (!allOI || allOI.length === 0) return 0;
  const max = Math.max(...allOI.filter(v => !isNaN(v) && v > 0));
  return max > 0 ? oi / max : 0;
}

function calculateAdaptiveScore(d) {
  let score = 0;
  
  if (d.volume > 1.5) score += 15;
  if (d.volume > 2) score += 10;
  if (d.volume > 3) score += 10;
  
  if (Math.abs(d.oiChange) > 0.2) score += 20;
  if (Math.abs(d.oiChange) > 0.5) score += 15;
  if (Math.abs(d.oiChange) > 1) score += 10;
  
  if (d.orderFlow > 1.2) score += 15;
  if (d.orderFlow > 1.4) score += 10;
  if (d.orderFlow > 1.6) score += 10;
  
  if (d.fakeOI > 0.1) score += 10;
  if (d.fakeOI > 0.3) score += 10;
  if (d.fakeOI > 0.5) score += 10;
  
  if (d.momentum > 0) score += 10;
  if (d.priceAcceleration > 0.001) score += 10;
  
  return Math.min(100, score);
}

function getSignalLevel(score) {
  if (score >= 50) return 'EXPLOSION';
  if (score >= 40) return 'ENTRY';
  if (score >= 30) return 'BUILDING';
  if (score >= 20) return 'WATCH';
  return null;
}

function detectEarlyPump(d) {
  return (
    d.volume > 1.5 &&
    d.oiChange > 0.1 &&
    Math.abs(d.priceChange) < 1.5
  );
}

function calculateBuyPressure(buyVolume, sellVolume) {
  const total = buyVolume + sellVolume;
  if (total === 0) return 0.5;
  return buyVolume / total;
}

function detectTrap(d) {
  return (
    (d.priceChange > 5 && d.orderFlow < 1.1) ||
    (d.priceChange < -5 && d.orderFlow < 1.1)
  );
}

function isNoise(d) {
  return (
    d.volume < 1.1 &&
    Math.abs(d.oiChange) < 0.05 &&
    d.orderFlow < 1.05
  );
}

function detectAccumulation(d) {
  return (
    d.volume > 1.8 &&
    d.orderFlow > 1.2 &&
    Math.abs(d.priceChange) < 1 &&
    d.fakeOI > 0.1
  );
}

function detectPressure(d) {
  return (
    d.volume > 1.5 &&
    d.orderFlow > 1.2 &&
    (d.oiChange > 0.1 || d.fakeOI > 0.1) &&
    d.momentum >= 0
  );
}

function detectExplosion(d) {
  return (
    d.volume > 2 &&
    d.orderFlow > 1.4 &&
    (Math.abs(d.oiChange) > 0.3 || d.fakeOI > 0.2) &&
    d.priceAcceleration > 0.002
  );
}

function detectHighPump(d) {
  return (
    d.volume > 2.5 &&
    d.orderFlow > 1.5 &&
    d.oiChange > 0.5 &&
    Math.abs(d.priceChange) > 1 &&
    d.score >= 40
  );
}

function canTrade(symbol) {
  const last = lastSignalTime[symbol] || 0;
  return Date.now() - last > SIGNAL_COOLDOWN;
}

export function getTopSymbols(limit = 10) {
  const sorted = [...symbolScores.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
  return sorted;
}

export function isSymbolEligible(symbol) {
  const topSymbols = getTopSymbols(MAX_ACTIVE_SIGNALS);
  return topSymbols.some(([s, score]) => s === symbol && score >= MIN_SIGNAL_SCORE);
}

export function processSymbol(symbol, marketData) {
  if (isNoise(marketData)) return null;
  if (!canTrade(symbol)) return null;
  
  const d = {
    ...marketData,
    priceChange: marketData.priceChange || 0,
    volume: marketData.volume || 1,
    orderFlow: marketData.orderFlow || 1,
    oiChange: marketData.oiChange || 0,
    fakeOI: marketData.fakeOI || 0,
    priceAcceleration: marketData.priceAcceleration || 0,
    momentum: marketData.momentum || 0,
    price: marketData.price || 0
  };
  
  if (detectTrap(d)) {
    stateMap.set(symbol, { stage: STAGES.WATCH });
    return { symbol, type: 'TRAP', confidence: 0 };
  }
  
  const score = calculateAdaptiveScore(d);
  d.score = score;
  symbolScores.set(symbol, score);
  
  const level = getSignalLevel(score);
  const state = stateMap.get(symbol) || { stage: STAGES.WATCH };
  
  if (detectHighPump(d)) {
    stateMap.set(symbol, { stage: STAGES.EXPLOSION, score, startTime: Date.now() });
    lastSignalTime[symbol] = Date.now();
    
    const direction = d.priceChange > 0 ? 'LONG' : 'SHORT';
    const entry = d.price;
    const risk = entry * 0.02;
    
    console.log(`🔥 HIGH_PUMP: ${symbol} | Score=${score} | PC=${d.priceChange.toFixed(1)}% | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(1)}`);
    
    return {
      type: 'HIGH_PUMP',
      symbol,
      direction,
      entry,
      stopLoss: direction === 'LONG' ? entry - risk : entry + risk,
      tp1: entry + risk * 1,
      tp2: entry + risk * 2,
      tp3: entry + risk * 3,
      confidence: score,
      level,
      data: d
    };
  }
  
  if (detectExplosion(d) && score >= 40) {
    const direction = d.priceChange > 0 ? 'LONG' : 'SHORT';
    const entry = d.price;
    const risk = entry * 0.02;
    
    stateMap.set(symbol, { stage: STAGES.EXPLOSION, score, startTime: Date.now() });
    lastSignalTime[symbol] = Date.now();
    
    console.log(`🔴 SNIPER: ${symbol} | Score=${score} | Entry=${entry.toFixed(6)} | Vol=${d.volume.toFixed(1)}x`);
    
    return {
      type: 'SNIPER',
      symbol,
      direction,
      entry,
      stopLoss: direction === 'LONG' ? entry - risk : entry + risk,
      tp1: entry + risk * 1,
      tp2: entry + risk * 2,
      tp3: entry + risk * 3,
      confidence: score,
      level,
      data: d
    };
  }
  
  if (detectPressure(d) && score >= 30) {
    stateMap.set(symbol, { stage: STAGES.BUILDING, score, startTime: Date.now() });
    
    console.log(`🟣 PRESSURE: ${symbol} | Score=${score} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(1)}`);
    
    return {
      type: 'PRESSURE',
      symbol,
      confidence: score,
      level,
      data: d,
      entry: d.price
    };
  }
  
  if (detectAccumulation(d) && score >= 25) {
    stateMap.set(symbol, { stage: STAGES.BUILDING, score, startTime: Date.now() });
    
    console.log(`📦 ACCUMULATION: ${symbol} | Score=${score} | Vol=${d.volume.toFixed(1)}x`);
    
    return {
      type: 'ACCUMULATION',
      symbol,
      confidence: score,
      level,
      data: d,
      entry: d.price
    };
  }
  
  if (detectEarlyPump(d) && score >= 20) {
    stateMap.set(symbol, { stage: STAGES.WATCH, score, startTime: Date.now() });
    
    console.log(`👀 EARLY_PUMP: ${symbol} | Score=${score} | Vol=${d.volume.toFixed(1)}x | OI=${d.oiChange.toFixed(1)}%`);
    
    return {
      type: 'EARLY_PUMP',
      symbol,
      confidence: score,
      level,
      data: d,
      entry: d.price
    };
  }
  
  if (score >= 30) {
    stateMap.set(symbol, { stage: STAGES.BUILDING, score, startTime: Date.now() });
    
    return {
      type: 'BUILDING',
      symbol,
      confidence: score,
      level,
      data: d,
      entry: d.price
    };
  }
  
  if (score >= 20) {
    stateMap.set(symbol, { stage: STAGES.WATCH, score, startTime: Date.now() });
    
    return {
      type: 'WATCH',
      symbol,
      confidence: score,
      level,
      data: d
    };
  }
  
  stateMap.set(symbol, state);
  return null;
}

export function updateOIRanking(symbol, oi) {
  oiRanking.set(symbol, Math.abs(oi));
}

export function getState(symbol) {
  return stateMap.get(symbol) || { stage: STAGES.WATCH };
}

export function reset() {
  stateMap.clear();
}

export function getSmartOI(oiChange) {
  return oiChange * 10;
}

export function getAllScores() {
  return [...symbolScores.entries()]
    .sort((a, b) => b[1] - a[1]);
}

export const signalPipeline = {
  processSymbol,
  getState,
  reset,
  setOITracker,
  getTopSymbols,
  isSymbolEligible,
  getAllScores
};

export const signalStateMachine = {
  getState,
  setState: (s, s2, d) => stateMap.set(s, { stage: s2, ...d }),
  checkTimeout: () => false,
  getActiveSignals: () => [],
  getTopSymbols
};

export { STAGES, calculateAdaptiveScore, getSignalLevel, detectEarlyPump, calculateBuyPressure, detectTrap, isNoise };
