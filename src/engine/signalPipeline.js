const STAGES = {
  IDLE: 'IDLE',
  PRESSURE: 'PRESSURE',
  BREAKOUT: 'BREAKOUT',
  SNIPER: 'SNIPER'
};

const stateMap = new Map();
let oiTrackerModule = null;

const oiRanking = new Map();
const SIGNAL_COOLDOWN = 2 * 60 * 1000;
const lastSignalTime = {};

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

function detectTrap(d) {
  return (
    (d.priceChange > 5 && d.orderFlow < 1.1) ||
    (d.priceChange < -5 && d.orderFlow < 1.1)
  );
}

function isNoise(d) {
  return (
    Math.abs(d.oiChange) < 0.03 &&
    Math.abs(d.fakeOI) < 0.15 &&
    d.volume < 1.8
  );
}

function detectAccumulation(d) {
  return (
    d.priceChange < 2 &&
    d.volume > 1.8 &&
    d.orderFlow > 1.3 &&
    d.fakeOI > 0.2
  );
}

function detectPressure(d) {
  return (
    d.volume > 2.5 &&
    d.orderFlow > 1.5 &&
    (d.fakeOI > 0.3 || Math.abs(d.oiChange) > 0.1) &&
    d.priceAcceleration > 0.12
  );
}

function detectExplosion(d) {
  return (
    d.volume > 3 &&
    d.orderFlow > 1.6 &&
    (Math.abs(d.oiChange) > 0.15 || d.fakeOI > 0.4) &&
    d.priceAcceleration > 0.2
  );
}

function isExploding(d) {
  return d.priceAcceleration > 0.2;
}

function isAggressiveFlow(d) {
  return d.orderFlow > 1.6 || d.orderFlow < 0.65;
}

function calculateScore(d, oiRank = 0) {
  let score = 0;
  
  if (detectAccumulation(d)) score += 10;
  if (detectPressure(d)) score += 25;
  if (detectExplosion(d)) score += 40;
  if (isExploding(d)) score += 15;
  if (isAggressiveFlow(d)) score += 10;
  
  if (Math.abs(d.oiChange) > 0.5) score += 25;
  else if (Math.abs(d.oiChange) > 0.3) score += 15;
  else if (Math.abs(d.oiChange) > 0.15) score += 8;
  
  if (d.fakeOI > 0.6) score += 20;
  else if (d.fakeOI > 0.4) score += 15;
  else if (d.fakeOI > 0.25) score += 8;
  
  if (d.volume > 6) score += 15;
  else if (d.volume > 4) score += 10;
  else if (d.volume > 3) score += 5;
  
  score += oiRank * 20;
  
  if (detectTrap(d)) score -= 50;
  
  return Math.max(0, Math.min(100, score));
}

function canTrade(symbol) {
  const last = lastSignalTime[symbol] || 0;
  return Date.now() - last > SIGNAL_COOLDOWN;
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
  
  const state = stateMap.get(symbol) || { stage: STAGES.IDLE };
  
  if (detectTrap(d)) {
    stateMap.set(symbol, { stage: STAGES.IDLE });
    return null;
  }
  
  const allOI = Array.from(oiRanking.values());
  const oiRank = normalizeOI(Math.abs(d.oiChange) + Math.abs(d.fakeOI), allOI);
  const score = calculateScore(d, oiRank);
  
  if (state.stage === STAGES.IDLE) {
    if (detectPressure(d)) {
      state.stage = STAGES.PRESSURE;
      state.score = score;
      state.startTime = Date.now();
      stateMap.set(symbol, state);
      lastSignalTime[symbol] = Date.now();
      
      console.log(`🟣 PRESSURE: ${symbol} | PC=${d.priceChange.toFixed(1)}% | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(1)} | F=${d.fakeOI.toFixed(2)} | Score=${score}`);
      
      return { type: 'ACCUMULATION', symbol, confidence: score, data: d };
    }
  }
  
  if (state.stage === STAGES.PRESSURE) {
    if (detectExplosion(d) && score >= 50) {
      const entry = d.price;
      const risk = entry * 0.02;
      const sl = entry - risk;
      
      state.stage = STAGES.SNIPER;
      stateMap.set(symbol, state);
      lastSignalTime[symbol] = Date.now();
      
      console.log(`🔴 SNIPER: ${symbol} | Entry=${entry.toFixed(6)} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(1)} | F=${d.fakeOI.toFixed(2)} | Score=${score}`);
      
      return {
        type: 'SNIPER',
        symbol,
        entry,
        stopLoss: sl,
        tp1: entry + risk * 1,
        tp2: entry + risk * 2,
        tp3: entry + risk * 3,
        confidence: score,
        data: d
      };
    }
    
    if (score < 30) {
      stateMap.set(symbol, { stage: STAGES.IDLE });
    }
  }
  
  if (state.stage === STAGES.IDLE && detectExplosion(d) && score >= 60) {
    const entry = d.price;
    const risk = entry * 0.02;
    const sl = entry - risk;
    
    stateMap.set(symbol, { stage: STAGES.SNIPER });
    lastSignalTime[symbol] = Date.now();
    
    console.log(`🔴 SNIPER (DIRECT): ${symbol} | Vol=${d.volume.toFixed(1)}x | Score=${score}`);
    
    return {
      type: 'SNIPER',
      symbol,
      entry,
      stopLoss: sl,
      tp1: entry + risk * 1,
      tp2: entry + risk * 2,
      tp3: entry + risk * 3,
      confidence: score,
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
  return stateMap.get(symbol) || { stage: STAGES.IDLE };
}

export function reset() {
  stateMap.clear();
}

export const signalPipeline = {
  processSymbol,
  getState,
  reset,
  setOITracker
};

export { STAGES };
