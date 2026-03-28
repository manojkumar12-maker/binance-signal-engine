import { 
  filterByD1Trend, 
  filterByH4Zone, 
  filterBySession, 
  confirmM15Entry,
  calculateWeightedScore,
  formatEnhancedSignal,
  applyAllFilters,
  getSessionInfo,
  updateMarketTimeframes,
  getDirection,
  detectWhale,
  getDirectionFromWhale,
  getNewsImpact,
  setWhaleFilter,
  setNewsFilter,
  analyzeNewsSentiment
} from '../signals/advancedFilters.js';

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
const MIN_SIGNAL_SCORE = 30;
const MIN_OI_READY_HISTORY = 2;
const MAX_ACTIVE_SIGNALS = 10;

let btcPriceChange = 0;
let enableAdvancedFilters = true;

function isOIReady(symbol) {
  if (!oiTrackerModule) return true;
  return oiTrackerModule.isOIReady(symbol);
}

function getOIChange(symbol) {
  if (!oiTrackerModule) return 0;
  return oiTrackerModule.getChange(symbol) || 0;
}

function isValidSignal(d) {
  return (
    d.volume >= 1.1 &&
    Math.abs(d.oiChange) >= 0.05 &&
    d.orderFlow >= 1.05
  );
}

function calculateNormalizedScore(d, whale, newsScore = 0) {
  const vol = Math.min(d.volume, 3);
  const oi = Math.min(Math.abs(d.oiChange), 1);
  const of = Math.min(d.orderFlow, 2);
  
  let score = 0;
  score += vol * 10;
  score += oi * 25;
  score += of * 10;
  score += Math.max(0, d.momentum) * 10;
  
  if (whale) score += 15;
  score += newsScore;
  
  return Math.round(Math.min(100, score));
}

function getDirectionWithWhale(d, whale) {
  if (
    whale === 'ACCUMULATION' &&
    d.orderFlow > 1.1 &&
    d.momentum > 0
  ) return 'LONG';
  
  if (
    whale === 'DISTRIBUTION' &&
    d.orderFlow < 0.9 &&
    d.momentum < 0
  ) return 'SHORT';
  
  return null;
}

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

function applyFiltersToSignal(signal) {
  if (!signal || !enableAdvancedFilters) return signal;
  
  const filterResult = applyAllFilters(signal, {
    allowAsia: false,
    requireM15: true,
    requireD1: true,
    requireH4: true,
    requireWhale: true
  });
  
  if (filterResult.filtered) {
    console.log(`🚫 FILTERED: ${signal.symbol} - ${filterResult.reason}`);
    return null;
  }
  
  const enhanced = formatEnhancedSignal(signal);
  return enhanced;
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
  if (!isOIReady(symbol)) {
    return null;
  }
  
  if (isNoise(marketData)) return null;
  
  const d = {
    ...marketData,
    priceChange: marketData.priceChange || 0,
    volume: marketData.volume || 1,
    orderFlow: marketData.orderFlow || 1,
    oiChange: marketData.oiChange || getOIChange(symbol) || 0,
    fakeOI: marketData.fakeOI || 0,
    priceAcceleration: marketData.priceAcceleration || 0,
    momentum: marketData.momentum || 0,
    price: marketData.price || 0
  };
  
  const isTrap = detectTrap(d);
  
  const whale = detectWhale(d);
  
  if (isTrap && whale) {
    return null;
  }
  
  if (isTrap) {
    stateMap.set(symbol, { stage: STAGES.WATCH });
    const trapDirection = d.priceChange > 0 ? 'SHORT' : 'LONG';
    return { symbol, type: 'TRAP', direction: trapDirection, confidence: 0 };
  }
  
  if (!whale) {
    return null;
  }
  
  if (!canTrade(symbol)) {
    return null;
  }
  
  if (!isValidSignal(d)) {
    return null;
  }
  
  const normalizedScore = calculateNormalizedScore(d, whale, d.newsScore || 0);
  
  if (normalizedScore < MIN_SIGNAL_SCORE) {
    return null;
  }
  
  d.score = normalizedScore;
  d.whale = whale;
  symbolScores.set(symbol, normalizedScore);
  
  const level = getSignalLevel(normalizedScore);
  const state = stateMap.get(symbol) || { stage: STAGES.WATCH };
  
  let smartDirection = getDirectionWithWhale(d, whale);
  
  if (!smartDirection) {
    return null;
  }
  
  if (detectHighPump(d)) {
    
    if (!whale) {
      console.log(`🚫 HIGH_PUMP FILTERED: ${symbol} - NO WHALE ACTIVITY`);
      return null;
    }
    
    stateMap.set(symbol, { stage: STAGES.EXPLOSION, score: normalizedScore, startTime: Date.now() });
    lastSignalTime[symbol] = Date.now();
    
    const entry = d.price;
    const risk = entry * 0.015;
    
    console.log(`🔥 HIGH_PUMP: ${symbol} | Score=${normalizedScore} | Dir=${smartDirection} | PC=${d.priceChange.toFixed(1)}% | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(1)}`);
    
    const signal = {
      type: 'HIGH_PUMP',
      symbol,
      direction: smartDirection,
      entry,
      stopLoss: smartDirection === 'LONG' ? entry - risk : entry + risk,
      tp1: entry + risk * 1,
      tp2: entry + risk * 2,
      tp3: entry + risk * 3,
      confidence: normalizedScore,
      score: normalizedScore,
      level,
      data: d,
      whale,
      newsImpact
    };
    
    return applyFiltersToSignal(signal);
  }
  
  if (detectExplosion(d) && normalizedScore >= 40) {
    if (!smartDirection) {
      console.log(`🚫 SNIPER FILTERED: ${symbol} - NO CLEAR DIRECTION`);
      return null;
    }
    
    if (!whale) {
      console.log(`🚫 SNIPER FILTERED: ${symbol} - NO WHALE ACTIVITY`);
      return null;
    }
    
    const entry = d.price;
    const risk = entry * 0.015;
    
    stateMap.set(symbol, { stage: STAGES.EXPLOSION, score: normalizedScore, startTime: Date.now() });
    lastSignalTime[symbol] = Date.now();
    
    const sessionInfo = getSessionInfo();
    console.log(`🔴 SNIPER: ${symbol} | Score=${normalizedScore} | Dir=${smartDirection} | Whale=${whale || 'NONE'} | Entry=${entry.toFixed(6)} | Vol=${d.volume.toFixed(1)}x | Session=${sessionInfo.session}`);
    
    const signal = {
      type: 'SNIPER',
      symbol,
      direction: smartDirection,
      entry,
      stopLoss: smartDirection === 'LONG' ? entry - risk : entry + risk,
      tp1: entry + risk * 1,
      tp2: entry + risk * 2,
      tp3: entry + risk * 3,
      confidence: normalizedScore,
      score: normalizedScore,
      level,
      data: d,
      session: sessionInfo.session,
      whale,
      newsImpact
    };
    
    return applyFiltersToSignal(signal);
  }
  
  if (detectPressure(d) && score >= 30) {
    if (!smartDirection || !whale) return null;
    
    stateMap.set(symbol, { stage: STAGES.BUILDING, score, startTime: Date.now() });
    
    console.log(`🟣 PRESSURE: ${symbol} | Score=${score} | Dir=${smartDirection} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(1)}`);
    
    return {
      type: 'PRESSURE',
      symbol,
      direction: smartDirection,
      confidence: score,
      level,
      data: d,
      entry: d.price
    };
  }
  
  if (detectAccumulation(d) && score >= 25) {
    if (!smartDirection || !whale) return null;
    
    stateMap.set(symbol, { stage: STAGES.BUILDING, score, startTime: Date.now() });
    
    console.log(`📦 ACCUMULATION: ${symbol} | Score=${score} | Dir=${smartDirection} | Vol=${d.volume.toFixed(1)}x`);
    
    return {
      type: 'ACCUMULATION',
      symbol,
      direction: smartDirection,
      confidence: score,
      level,
      data: d,
      entry: d.price
    };
  }
  
  if (detectEarlyPump(d) && score >= 20) {
    if (!smartDirection) return null;
    
    stateMap.set(symbol, { stage: STAGES.WATCH, score, startTime: Date.now() });
    
    console.log(`👀 EARLY_PUMP: ${symbol} | Score=${score} | Dir=${smartDirection} | Vol=${d.volume.toFixed(1)}x | OI=${d.oiChange.toFixed(1)}%`);
    
    return {
      type: 'EARLY_PUMP',
      symbol,
      direction: smartDirection,
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
  getAllScores,
  setAdvancedFilters: (enabled) => { enableAdvancedFilters = enabled; },
  isAdvancedFiltersEnabled: () => enableAdvancedFilters,
  setWhaleFilter,
  setNewsFilter,
  updateTimeframes: updateMarketTimeframes
};

export const signalStateMachine = {
  getState,
  setState: (s, s2, d) => stateMap.set(s, { stage: s2, ...d }),
  checkTimeout: () => false,
  getActiveSignals: () => [],
  getTopSymbols
};

export { STAGES, calculateAdaptiveScore, calculateWeightedScore, getSignalLevel, detectEarlyPump, calculateBuyPressure, detectTrap, isNoise, getSessionInfo };
