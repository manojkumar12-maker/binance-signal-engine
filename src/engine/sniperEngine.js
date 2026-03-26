export const sniperState = {
  imbalance: {},
  volumeRatio: {},
  prevHigh: {},
  prevFast: {},
  price: {},
  oiChange: {},
  symbols: new Set(),
  signalHistory: new Map()
};

export function updateSniperState(symbol, data) {
  sniperState.symbols.add(symbol);
  if (data.imbalance !== undefined) sniperState.imbalance[symbol] = data.imbalance;
  if (data.volumeRatio !== undefined) sniperState.volumeRatio[symbol] = data.volumeRatio;
  if (data.price !== undefined) sniperState.price[symbol] = data.price;
  if (data.oiChange !== undefined) sniperState.oiChange[symbol] = data.oiChange;
}

import { shouldEmit, selectTopSignals, isHighQuality, isExecutionReady, getCooldownForType } from '../signals/signalFilters.js';

function canEmitSignal(symbol, type) {
  const cooldown = getCooldownForType(type);
  const last = sniperState.signalHistory.get(symbol) || 0;
  return Date.now() - last > cooldown;
}

function recordSignal(symbol) {
  sniperState.signalHistory.set(symbol, Date.now());
}

// ==============================
// STAGE 1 — PRESSURE (Relaxed)
// ==============================
function detectPressure(symbol) {
  const imbalance = sniperState.imbalance[symbol] || 1;
  const volume = sniperState.volumeRatio[symbol] || 1;

  if (imbalance > 1.03 || volume > 1.2) {
    return true;
  }
  return false;
}

// ==============================
// STAGE 2 — BREAKOUT (Relaxed)
// ==============================
function detectBreakout(symbol, price) {
  const prevHigh = sniperState.prevHigh[symbol] || price;

  if (price > prevHigh * 1.0005) {
    sniperState.prevHigh[symbol] = price;
    return true;
  }

  sniperState.prevHigh[symbol] = price;
  return false;
}

// ==============================
// STAGE 3 — MOMENTUM (Relaxed)
// ==============================
function detectMomentum(symbol, price) {
  const prev = sniperState.prevFast[symbol] || price;

  const velocity = prev > 0 ? (price - prev) / prev : 0;
  sniperState.prevFast[symbol] = price;

  return velocity > 0.0005;
}

// ==============================
// CALCULATE ADAPTIVE SCORE
// ==============================
function calculateScore(data) {
  let score = 0;
  const { oiChange, volumeRatio, imbalance } = data;
  
  if (volumeRatio > 1.5) score += 15;
  if (volumeRatio > 2) score += 10;
  if (volumeRatio > 3) score += 10;
  
  if (Math.abs(oiChange) > 0.1) score += 20;
  if (Math.abs(oiChange) > 0.3) score += 15;
  if (Math.abs(oiChange) > 0.5) score += 10;
  
  if (imbalance > 1.1) score += 15;
  if (imbalance > 1.2) score += 10;
  if (imbalance > 1.4) score += 10;
  
  return Math.min(100, score);
}

// ==============================
// STAGE 4 — ENTRY LOGIC (Adaptive)
// ==============================
function getEntrySignal(symbol, data) {
  const { price, oiChange, volumeRatio, imbalance } = data;

  const pressure = detectPressure(symbol);
  const breakout = detectBreakout(symbol, price);
  const momentum = detectMomentum(symbol, price);
  
  const score = calculateScore(data);

  // 🔥 EXPLOSION (HIGH CONFIDENCE)
  if (pressure && momentum && oiChange > 0.2 && volumeRatio > 2) {
    if (canEmitSignal(symbol, 'CONFIRMED_ENTRY')) {
      recordSignal(symbol);
      return {
        type: "CONFIRMED ENTRY",
        finalScore: score + 30,
        level: "EXPLOSION"
      };
    }
  }

  // 🔴 SNIPER (Good conditions)
  if (pressure && breakout && oiChange > 0.1 && volumeRatio > 1.5) {
    if (canEmitSignal(symbol, 'SNIPER_ENTRY')) {
      recordSignal(symbol);
      return {
        type: "SNIPER ENTRY",
        finalScore: score + 20,
        level: "ENTRY"
      };
    }
  }

  // ⚡ EARLY ENTRY (Building)
  if (pressure || breakout) {
    if (canEmitSignal(symbol, 'EARLY_ENTRY')) {
      recordSignal(symbol);
      return {
        type: "EARLY ENTRY",
        finalScore: score + 10,
        level: "BUILDING"
      };
    }
  }

  // 👀 WATCH (Score based)
  if (score >= 30) {
    if (canEmitSignal(symbol, 'WATCH')) {
      recordSignal(symbol);
      return {
        type: "WATCH",
        finalScore: score,
        level: "WATCH"
      };
    }
  }

  return null;
}

// ==============================
// STAGE 5 — RANKING (Top 5 only)
// ==============================
function rankSignals(signals) {
  return selectTopSignals(signals, 5);
}

// ==============================
// GET TOP WATCHING (Even without signals)
// ==============================
export function getTopWatching() {
  const watching = [];
  
  for (const s of sniperState.symbols) {
    const data = {
      price: sniperState.price[s],
      oiChange: sniperState.oiChange[s] || 0,
      volumeRatio: sniperState.volumeRatio[s] || 1,
      imbalance: sniperState.imbalance[s] || 1
    };
    
    if (!data.price) continue;
    
    const score = calculateScore(data);
    watching.push({
      symbol: s,
      ...data,
      score,
      level: score >= 50 ? "EXPLOSION" : 
             score >= 40 ? "ENTRY" : 
             score >= 30 ? "BUILDING" : "WATCH"
    });
  }
  
  return watching
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

// ==============================
// RUNNER
// ==============================
export function runSniper() {
  const signals = [];

  for (const s of sniperState.symbols) {
    const data = {
      price: sniperState.price[s],
      oiChange: sniperState.oiChange[s] || 0,
      volumeRatio: sniperState.volumeRatio[s] || 1,
      imbalance: sniperState.imbalance[s] || 1
    };

    if (!data.price) continue;

    const signal = getEntrySignal(s, data);

    if (signal) {
      signals.push({
        symbol: s,
        ...signal,
        ...data
      });
    }
  }

  return rankSignals(signals);
}
