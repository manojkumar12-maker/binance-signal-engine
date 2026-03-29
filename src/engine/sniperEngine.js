export const sniperState = {
  imbalance: {},
  volumeRatio: {},
  prevHigh: {},
  prevFast: {},
  price: {},
  priceHistory: new Map(),
  oiChange: {},
  priceChangePercent: {},  // ✅ FIX 4: Add priceChangePercent to state
  symbols: new Set(),
  signalHistory: new Map()
};

export function updateSniperState(symbol, data) {
  sniperState.symbols.add(symbol);
  if (data.imbalance !== undefined) sniperState.imbalance[symbol] = data.imbalance;
  if (data.volumeRatio !== undefined) sniperState.volumeRatio[symbol] = data.volumeRatio;
  if (data.price !== undefined) sniperState.price[symbol] = data.price;
  if (data.oiChange !== undefined) sniperState.oiChange[symbol] = data.oiChange;
  if (data.priceChangePercent !== undefined) sniperState.priceChangePercent[symbol] = data.priceChangePercent; // ✅ FIX 4
  
  // Track price history for EMA calculation
  if (data.price !== undefined) {
    if (!sniperState.priceHistory.has(symbol)) {
      sniperState.priceHistory.set(symbol, []);
    }
    const history = sniperState.priceHistory.get(symbol);
    history.push(data.price);
    if (history.length > 250) history.shift();
  }
}

import { shouldEmit, selectTopSignals, isHighQuality, isExecutionReady, getCooldownForType, getDirection, isInNoTradeZone, validateDirection, getOIDirection, isNoTradeZone, getTrendDirection, marketState, updateTrend, updateVolatility, updateAvgVolume, getAdaptiveWeights, isOISignificant, detectOICluster, isMarketChop, isNoise, analyzeOIContext, updateMarketBias } from '../signals/signalFilters.js';
import { getSessionInfo } from '../signals/advancedFilters.js';

// ========== LIQUIDITY SWEEP DETECTION (Institutional) ==========
const priceCache = new Map();

export function detectLiquiditySweep(symbol, currentPrice, high, low, close) {
  if (!priceCache.has(symbol)) {
    priceCache.set(symbol, { high: 0, low: Infinity, close: currentPrice });
  }
  
  const cache = priceCache.get(symbol);
  const prevHigh = cache.high;
  const prevLow = cache.low;
  
  // Update cache
  cache.high = Math.max(cache.high, high);
  cache.low = Math.min(cache.low, low);
  cache.close = close;
  
  // Liquidity Sweep UP (fake breakout) - bearish signal
  if (high > prevHigh && close < prevHigh * 0.999) {
    return { type: 'BEARISH_SWEEP', reason: 'Liquidity sweep up - weak bullish' };
  }
  
  // Liquidity Sweep DOWN (fake breakdown) - bullish signal
  if (low < prevLow && close > prevLow * 1.001) {
    return { type: 'BULLISH_SWEEP', reason: 'Liquidity sweep down - weak bearish' };
  }
  
  return null;
}

// ========== ABSORPTION DETECTION ==========
const absorptionCache = new Map();

export function detectAbsorption(symbol, volume, priceChange, high, low) {
  const key = symbol;
  
  if (!absorptionCache.has(key)) {
    absorptionCache.set(key, { volumeSum: 0, priceSum: 0, count: 0 });
  }
  
  const cache = absorptionCache.get(key);
  cache.volumeSum += volume;
  cache.priceSum += Math.abs(priceChange);
  cache.count++;
  
  if (cache.count < 10) return false;
  
  const avgVolume = cache.volumeSum / cache.count;
  const avgPriceMove = cache.priceSum / cache.count;
  
  // High volume but low price movement = absorption
  if (volume > avgVolume * 1.5 && Math.abs(priceChange) < avgPriceMove * 0.5) {
    return true;
  }
  
  return false;
}

function canEmitSignal(symbol, type) {
  const cooldown = getCooldownForType(type);
  const last = sniperState.signalHistory.get(symbol) || 0;
  return Date.now() - last > cooldown;
}

function recordSignal(symbol) {
  sniperState.signalHistory.set(symbol, Date.now());
}

// ==============================
// STAGE 1 — PRESSURE (Require imbalance)
// ==============================
function detectPressure(symbol) {
  const imbalance = sniperState.imbalance[symbol] || 1;
  const volume = sniperState.volumeRatio[symbol] || 1;

  if (isInNoTradeZone(imbalance)) return false;
  
  const hasImbalance = imbalance > 1.15 || imbalance < 0.85;
  const hasVolume = volume > 1.3;
  
  return hasImbalance && hasVolume;
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

  return velocity > 0.0003;
}

// ==============================
// CALCULATE ADAPTIVE SCORE (Direction weighted + Cluster + Z-Score)
// ==============================
function calculateScore(data) {
  let score = 0;
  const { oiChange, volumeRatio, imbalance, symbol } = data;
  
  if (isInNoTradeZone(imbalance)) return 0;
  
  const direction = getDirection(imbalance);
  if (!direction) return 0;
  
  // Volume scoring
  if (volumeRatio > 1.5) score += 10;
  if (volumeRatio > 2) score += 5;
  if (volumeRatio > 3) score += 5;
  
  // OI scoring with noise filtering
  if (Math.abs(oiChange) > 0.1) score += 10;
  if (Math.abs(oiChange) > 0.3) score += 5;
  if (Math.abs(oiChange) > 0.5) score += 5;
  
  // Cluster detection boost (consecutive OI builds are stronger)
  const cluster = detectOICluster(symbol, oiChange);
  if (cluster.isCluster) {
    score += 15; // Significant boost for cluster
  }
  
  // Z-score boost (unusual OI activity)
  const oiSig = isOISignificant(symbol, oiChange);
  if (oiSig.zScore > 2) score += 10;
  if (oiSig.zScore > 3) score += 10;
  
  // Imbalance scoring
  if (imbalance > 1.2) score += 20;
  if (imbalance > 1.4) score += 15;
  if (imbalance > 1.6) score += 10;
  
  if (imbalance < 0.8) score += 20;
  if (imbalance < 0.6) score += 15;
  if (imbalance < 0.5) score += 10;
  
  return Math.min(100, score);
}

// ==============================
// STAGE 4 — ENTRY LOGIC (Direction required + Trend Filter)
// ==============================
function getEntrySignal(symbol, data) {
  const { price, oiChange, volumeRatio, imbalance, priceChangePercent, high, low } = data;

  if (isInNoTradeZone(imbalance)) return null;
  
  // Check No Trade Zone (low volatility/volume)
  const noTrade = isNoTradeZone(symbol, volumeRatio);
  if (noTrade.blocked) {
    return null;
  }
  
  const direction = getDirection(imbalance);
  if (!direction) return null;

  // TREND FILTER - Only trade with trend
  const priceHistory = sniperState.priceHistory?.get(symbol) || [];
  const trend = updateTrend(symbol, price, priceHistory);
  marketState.trend = trend;
  
  const trendDirection = getTrendDirection(symbol, price);
  if (trendDirection && trendDirection !== direction) {
    // Counter-trend signal - BLOCK
    return null;
  }

  // OI + PRICE + VOLUME COMBINATION (Enhanced Institutional Logic)
  const oiContext = analyzeOIContext(oiChange, priceChangePercent, volumeRatio);
  
  // Block absorption signals
  if (oiContext.signal === 'ABSORPTION') {
    return null;
  }
  
  // Only proceed if we have meaningful combination
  if (oiContext.signal === 'NEUTRAL') {
    return null;
  }

  // NOISE FILTER - Ignore tiny movements
  const noiseCheck = isNoise(oiChange, volumeRatio, priceChangePercent);
  if (noiseCheck.noise) {
    return null;
  }

  // Z-SCORE OI DETECTION - Only significant OI spikes
  const oiSignificance = isOISignificant(symbol, oiChange);
  if (!oiSignificance.significant && Math.abs(oiChange) < 0.05) {
    return null; // Not a significant OI move
  }

  // CLUSTER DETECTION - Consecutive OI builds are stronger
  const cluster = detectOICluster(symbol, oiChange);
  
  // MARKET BIAS - Skip chop markets
  const marketBias = updateMarketBias(symbol, oiChange, priceChangePercent);
  if (marketBias === 'CHOP') {
    return null; // Market is balanced/neutral - skip
  }

  // Update volatility tracking
  if (high && low) {
    updateVolatility(symbol, price, high, low);
  }
  updateAvgVolume(symbol, volumeRatio);

  const pressure = detectPressure(symbol);
  const breakout = detectBreakout(symbol, price);
  const momentum = detectMomentum(symbol, price);
  
  // Liquidity Sweep Detection
  const sweep = detectLiquiditySweep(symbol, price, high || price * 1.001, low || price * 0.999, price);
  if (sweep && sweep.type === 'BEARISH_SWEEP' && direction === 'LONG') {
    return null; // Block false bullish breakout
  }
  
  const score = calculateScore(data);

  // 🔥 EXPLOSION (HIGH CONFIDENCE + DIRECTION)
  if (pressure && momentum && volumeRatio > 2 && score >= 40) {
    if (canEmitSignal(symbol, 'CONFIRMED_ENTRY')) {
      recordSignal(symbol);
      return {
        type: "CONFIRMED ENTRY",
        finalScore: score + 30,
        level: "EXPLOSION",
        direction
      };
    }
  }

  const sessionInfo = getSessionInfo();
  const isHighScore = score >= 40;
  const isHighVolume = volumeRatio > 2;
  
  if (!isHighScore && !isHighVolume) {
    return null;
  }

  // 🔴 SNIPER (Good conditions + DIRECTION)
  if (pressure && breakout && volumeRatio > 1.5 && score >= 30) {
    if (canEmitSignal(symbol, 'SNIPER_ENTRY')) {
      recordSignal(symbol);
      return {
        type: "SNIPER ENTRY",
        finalScore: score + 20,
        level: "ENTRY",
        direction,
        session: sessionInfo.session,
        score
      };
    }
  }

  // ⚡ EARLY ENTRY (Building + DIRECTION) - BLOCK in elite mode if score < 40
  if (score < 40) {
    return null;
  }
  
  if ((pressure || breakout) && score >= 30) {
    if (canEmitSignal(symbol, 'EARLY_ENTRY')) {
      recordSignal(symbol);
      return {
        type: "EARLY ENTRY",
        finalScore: score + 10,
        level: "BUILDING",
        direction,
        session: sessionInfo.session,
        score
      };
    }
  }

  // 👀 WATCH - BLOCK in elite mode
  if (score >= 40 && direction) {
    if (canEmitSignal(symbol, 'WATCH')) {
      recordSignal(symbol);
      return {
        type: "WATCH",
        finalScore: score,
        level: "WATCH",
        direction,
        session: sessionInfo.session,
        score
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
      imbalance: sniperState.imbalance[s] || 1,
      symbol: s
    };
    
    if (!data.price) continue;
    
    const direction = getDirection(data.imbalance);
    const score = calculateScore(data);
    
    // Get additional context
    const oiSig = isOISignificant(s, data.oiChange);
    const cluster = detectOICluster(s, data.oiChange);
    
    // Always show top symbols even if score is low (for monitoring)
    watching.push({
      symbol: s,
      ...data,
      score,
      zScore: oiSig.zScore,
      isCluster: cluster.isCluster,
      direction: direction || 'NEUTRAL',
      level: score >= 50 ? "EXPLOSION" : 
             score >= 40 ? "ENTRY" : 
             score >= 30 ? "BUILDING" : "WATCH"
    });
  }
  
  return watching
    .sort((a, b) => b.score - a.score)
    .slice(0, 15);
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
      imbalance: sniperState.imbalance[s] || 1,
      priceChangePercent: sniperState.priceChangePercent?.[s] || 0  // ✅ FIX 4
    };

    if (!data.price) continue;
    if (isInNoTradeZone(data.imbalance)) continue;

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
