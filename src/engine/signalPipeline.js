const STAGES = {
  IDLE: 'IDLE',
  PRE_PUMP: 'PRE_PUMP',
  PUMP_CONFIRMED: 'PUMP_CONFIRMED',
  SNIPER: 'SNIPER'
};

const stateMap = new Map();
let oiTrackerModule = null;

const patternMemory = [];
const MAX_PATTERN_MEMORY = 100;

const lastSignalTime = {};
const SIGNAL_COOLDOWN = 2 * 60 * 1000;

let btcPriceChange = 0;

export function setOITracker(tracker) {
  oiTrackerModule = tracker;
}

export function updateBTCPrice(btcChange) {
  btcPriceChange = btcChange;
}

function getMarketRegime() {
  if (btcPriceChange > 1) return 'BULL';
  if (btcPriceChange < -1) return 'BEAR';
  return 'RANGE';
}

function detectSqueeze(d) {
  if (d.oiChange < -0.05 && d.priceChange > 0) return 'SHORT_SQUEEZE';
  if (d.oiChange > 0.05 && d.priceChange > 0) return 'LONG_BUILDUP';
  return null;
}

function isTrap(d) {
  return (
    (d.priceChange > 5 && d.orderFlow < 1.1) ||
    (d.priceChange < -5 && d.orderFlow < 1.1)
  );
}

function isMicroAccumulation(d) {
  return (
    d.priceChange < 1.5 &&
    d.volume > 1.8 &&
    d.orderFlow > 1.3 &&
    (d.fakeOI > 0.1 || Math.abs(d.oiChange) > 0.05)
  );
}

function isBreakout(d) {
  return (
    d.priceAcceleration > 0.25 &&
    d.volume > 2.5 &&
    d.orderFlow > 1.5
  );
}

function isExplosive(d) {
  return (
    d.volume > 2.5 &&
    d.orderFlow > 1.5 &&
    d.priceAcceleration > 0.2
  );
}

function isStrongOI(d) {
  return d.oiChange > 0.1 || d.fakeOI > 0.15;
}

function isSniperOI(d) {
  return d.oiChange > 0.1 || d.fakeOI > 0.2;
}

function getBreakoutTimer(d) {
  if (d.volume > 4 && d.orderFlow > 2) return '5-10 sec';
  if (d.volume > 3 && d.orderFlow > 1.8) return '10-20 sec';
  if (d.volume > 2.5) return '20-40 sec';
  return 'soon';
}

function canTrade(symbol) {
  const lastTime = lastSignalTime[symbol] || 0;
  if (Date.now() - lastTime < SIGNAL_COOLDOWN) return false;
  return true;
}

function recordPattern(d, result) {
  patternMemory.push({
    volume: d.volume,
    oi: d.oiChange,
    flow: d.orderFlow,
    result,
    timestamp: Date.now()
  });
  if (patternMemory.length > MAX_PATTERN_MEMORY) patternMemory.shift();
}

function calculateConfidence(d) {
  let conf = 25;
  const regime = getMarketRegime();

  if (Math.abs(d.oiChange) > 0.25) conf += 20;
  else if (Math.abs(d.oiChange) > 0.15) conf += 15;
  else if (Math.abs(d.oiChange) > 0.05) conf += 8;

  if (d.volume > 4) conf += 20;
  else if (d.volume > 3) conf += 15;
  else if (d.volume > 2) conf += 10;

  if (d.orderFlow > 2) conf += 15;
  else if (d.orderFlow > 1.5) conf += 10;
  else if (d.orderFlow > 1.2) conf += 5;

  if (Math.abs(d.fakeOI) > 0.4) conf += 20;
  else if (Math.abs(d.fakeOI) > 0.2) conf += 15;
  else if (Math.abs(d.fakeOI) > 0.08) conf += 8;

  const squeeze = detectSqueeze(d);
  if (squeeze === 'SHORT_SQUEEZE') conf += 20;
  if (squeeze === 'LONG_BUILDUP') conf += 10;

  if (isBreakout(d)) conf += 15;
  if (isExplosive(d)) conf += 10;

  if (regime === 'BULL') conf += 10;

  return Math.min(conf, 95);
}

export function buildMarketData(symbol, data) {
  return {
    symbol,
    priceChange: data.priceChange || 0,
    volume: data.volume || 1,
    orderFlow: data.orderFlow || 1,
    oiChange: data.oiChange || 0,
    fakeOI: data.fakeOI || 0,
    priceAcceleration: data.priceAcceleration || 0,
    momentum: data.momentum || 0,
    price: data.price || data.entryPrice || 0,
    atr: data.atr || 0,
    candle: data.candle || null,
    tradeCount: data.tradeCount || 0,
    usdVolume: data.usdVolume || 0
  };
}

export function processSymbol(symbol, marketData) {
  if (!canTrade(symbol)) return null;
  
  const d = buildMarketData(symbol, marketData);
  const state = stateMap.get(symbol) || { stage: STAGES.IDLE };

  if (isTrap(d)) {
    stateMap.set(symbol, { stage: STAGES.IDLE });
    return null;
  }

  // IDLE -> PRE_PUMP (micro accumulation)
  if (state.stage === STAGES.IDLE) {
    if (isMicroAccumulation(d)) {
      state.stage = STAGES.PRE_PUMP;
      state.accTime = Date.now();
      stateMap.set(symbol, state);
      lastSignalTime[symbol] = Date.now();
      
      const confidence = calculateConfidence(d);
      const breakoutTimer = getBreakoutTimer(d);
      
      console.log(`🟣 PRE_PUMP: ${symbol} | PC=${d.priceChange.toFixed(1)}% | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(2)} | OI=${d.oiChange.toFixed(2)}% | F=${d.fakeOI.toFixed(3)} | Conf=${confidence}% | ⏱️${breakoutTimer}`);
      
      return { type: 'ACCUMULATION', symbol, confidence, data: d, breakoutTimer };
    }
  }

  // PRE_PUMP -> PUMP_CONFIRMED (breakout)
  if (state.stage === STAGES.PRE_PUMP) {
    if (isBreakout(d)) {
      state.stage = STAGES.PUMP_CONFIRMED;
      state.confirmTime = Date.now();
      stateMap.set(symbol, state);
      
      const confidence = calculateConfidence(d);
      const breakoutTimer = getBreakoutTimer(d);
      
      console.log(`🟠 PUMP_CONFIRMED: ${symbol} | PC=${d.priceChange.toFixed(1)}% | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(2)} | OI=${d.oiChange.toFixed(2)}% | F=${d.fakeOI.toFixed(3)} | Conf=${confidence}% | ⏱️${breakoutTimer}`);
      
      return { type: 'PREDICT', symbol, confidence, data: d, breakoutTimer };
    }
  }

  // PUMP_CONFIRMED -> SNIPER (explosive entry)
  if (state.stage === STAGES.PUMP_CONFIRMED) {
    if (isExplosive(d) && isSniperOI(d)) {
      const confidence = calculateConfidence(d);
      
      if (confidence < 45) {
        stateMap.set(symbol, { stage: STAGES.IDLE });
        return null;
      }

      const entry = d.price;
      const risk = entry * 0.02;
      const sl = entry - risk;

      state.stage = STAGES.SNIPER;
      stateMap.set(symbol, state);
      lastSignalTime[symbol] = Date.now();

      const squeeze = detectSqueeze(d);
      const breakoutTimer = getBreakoutTimer(d);
      
      console.log(`🔴 SNIPER: ${symbol} | Entry=${entry.toFixed(6)} | SL=${sl.toFixed(6)} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(2)} | OI=${d.oiChange.toFixed(2)}% | F=${d.fakeOI.toFixed(3)} | Conf=${confidence}% | ${squeeze || ''}`);
      
      return {
        type: 'SNIPER',
        symbol,
        entry,
        stopLoss: sl,
        tp1: entry + risk * 1,
        tp2: entry + risk * 2,
        tp3: entry + risk * 3,
        confidence,
        timeToPump: Date.now() - state.accTime,
        data: d,
        squeeze,
        breakoutTimer
      };
    }
  }

  // Direct SNIPER from IDLE for very explosive setups
  if (state.stage === STAGES.IDLE && isExplosive(d) && isSniperOI(d)) {
    const confidence = calculateConfidence(d);
    
    if (confidence < 50) {
      return null;
    }

    const entry = d.price;
    const risk = entry * 0.02;
    const sl = entry - risk;

    state.stage = STAGES.SNIPER;
    stateMap.set(symbol, state);
    lastSignalTime[symbol] = Date.now();

    const squeeze = detectSqueeze(d);
    
    console.log(`🔴 SNIPER (DIRECT): ${symbol} | Entry=${entry.toFixed(6)} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(2)} | OI=${d.oiChange.toFixed(2)}% | Conf=${confidence}% | ${squeeze || ''}`);
    
    return {
      type: 'SNIPER',
      symbol,
      entry,
      stopLoss: sl,
      tp1: entry + risk * 1,
      tp2: entry + risk * 2,
      tp3: entry + risk * 3,
      confidence,
      timeToPump: 0,
      data: d,
      squeeze,
      breakoutTimer: 'immediate'
    };
  }

  stateMap.set(symbol, state);
  return null;
}

export function recordWin(symbol) {
  const state = stateMap.get(symbol);
  if (state && state.data) {
    recordPattern(state.data, 'WIN');
  }
}

export function recordLoss(symbol) {
  const state = stateMap.get(symbol);
  if (state && state.data) {
    recordPattern(state.data, 'LOSS');
  }
}

export function getState(symbol) {
  return stateMap.get(symbol) || { stage: STAGES.IDLE };
}

export function reset() {
  stateMap.clear();
}

export function getSmartOI(oiChange) {
  return oiChange * 10;
}

export const signalPipeline = {
  processSymbol,
  getState,
  reset,
  setOITracker
};

export { STAGES, detectSqueeze, getBreakoutTimer };

export const signalStateMachine = {
  getState(symbol) {
    return stateMap.get(symbol) || { stage: STAGES.IDLE, score: 0, data: null };
  },
  setState(symbol, stage, data = {}) {
    const current = stateMap.get(symbol) || { stage: STAGES.IDLE };
    stateMap.set(symbol, { ...current, stage, ...data });
    return stateMap.get(symbol);
  },
  checkTimeout(symbol) {
    const state = stateMap.get(symbol);
    if (state && state.stage !== STAGES.IDLE && Date.now() - (state.lastUpdate || 0) > 300000) {
      stateMap.set(symbol, { stage: STAGES.IDLE });
      return true;
    }
    return false;
  },
  getActiveSignals() {
    return Array.from(stateMap.entries())
      .filter(([_, s]) => s.stage !== STAGES.IDLE)
      .map(([symbol, state]) => ({ symbol, ...state }));
  }
};
