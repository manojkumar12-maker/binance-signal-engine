const STAGES = {
  IDLE: 'IDLE',
  ACCUMULATION: 'ACCUMULATION',
  PREDICT: 'PREDICT',
  SNIPER: 'SNIPER'
};

const stateMap = new Map();
let oiTrackerModule = null;

const patternMemory = [];
const MAX_PATTERN_MEMORY = 100;

const lastSignalTime = {};
const SIGNAL_COOLDOWN = 3 * 60 * 1000;

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
  if (d.oiChange < -0.05 && d.priceChange > 0) {
    return 'SHORT_SQUEEZE';
  }
  if (d.oiChange > 0.05 && d.priceChange > 0) {
    return 'LONG_BUILDUP';
  }
  return null;
}

function isAbsorption(d) {
  return (
    d.priceChange < 2 &&
    d.volume > 2 &&
    d.orderFlow > 1.3
  );
}

function isExplosive(d) {
  return d.priceAcceleration > 0.15 && d.momentum > 0.1;
}

function isRealVolume(d) {
  return d.volume > 2;
}

function getEffectiveOI(d) {
  if (Math.abs(d.oiChange) > 0.01) return d.oiChange;
  return d.fakeOI || 0;
}

function isTrap(d) {
  return (
    (d.priceChange > 5 && d.orderFlow < 1.1) ||
    (d.priceChange < -5 && d.orderFlow < 1.1)
  );
}

function isAccumulation(d) {
  const effectiveOI = getEffectiveOI(d);
  return (
    d.volume > 1.5 &&
    Math.abs(d.priceChange) < 3 &&
    (Math.abs(d.fakeOI || 0) > 0.05 || Math.abs(d.oiChange || 0) > 0.01) &&
    d.orderFlow > 1.05
  );
}

function isPumpIncoming(d) {
  const effectiveOI = getEffectiveOI(d);
  return (
    d.volume > 1.8 &&
    d.orderFlow > 1.2 &&
    Math.abs(effectiveOI) > 0.01
  );
}

function getBreakoutTimer(d) {
  if (d.fakeOI > 0.2 && d.volume > 3) return '5-10 sec';
  if (d.fakeOI > 0.1) return '10-30 sec';
  if (Math.abs(d.oiChange || 0) > 0.05 || Math.abs(d.fakeOI || 0) > 0.05) return '30-60 sec';
  return 'soon';
}

function isExplosiveSetup(d) {
  return (
    d.volume > 2.5 &&
    d.orderFlow > 1.3
  );
}

function isSniper(d) {
  if (!isExplosive(d)) return false;
  if (!isRealVolume(d)) return false;
  
  const effectiveOI = getEffectiveOI(d);
  return (
    d.priceAcceleration > 0.1 &&
    d.volume > 1.8 &&
    d.orderFlow > 1.1 &&
    Math.abs(effectiveOI) > 0.005 &&
    !isTrap(d)
  );
}

function matchPattern(d) {
  if (patternMemory.length < 3) return false;
  
  const recent = patternMemory.slice(-5);
  return recent.some(p =>
    Math.abs(p.volume - d.volume) < 0.5 &&
    p.result === 'WIN'
  );
}

function canTrade(symbol) {
  const lastTime = lastSignalTime[symbol] || 0;
  if (Date.now() - lastTime < SIGNAL_COOLDOWN) {
    return false;
  }
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
  
  if (patternMemory.length > MAX_PATTERN_MEMORY) {
    patternMemory.shift();
  }
}

function calculateConfidence(d) {
  let conf = 30;
  const regime = getMarketRegime();

  if (Math.abs(d.oiChange || 0) > 0.1) conf += 15;
  else if (Math.abs(d.oiChange || 0) > 0.02) conf += 10;
  
  if (d.volume > 3) conf += 20;
  else if (d.volume > 2) conf += 15;
  else if (d.volume > 1.5) conf += 10;
  
  if (d.orderFlow > 1.8) conf += 15;
  else if (d.orderFlow > 1.3) conf += 10;
  else if (d.orderFlow > 1.05) conf += 5;
  
  if (Math.abs(d.fakeOI || 0) > 0.3) conf += 20;
  else if (Math.abs(d.fakeOI || 0) > 0.1) conf += 15;
  else if (Math.abs(d.fakeOI || 0) > 0.03) conf += 5;

  const squeeze = detectSqueeze(d);
  if (squeeze === 'SHORT_SQUEEZE') conf += 20;
  if (squeeze === 'LONG_BUILDUP') conf += 10;

  if (isAbsorption(d)) conf += 10;
  if (isExplosive(d)) conf += 15;
  if (isExplosiveSetup(d)) conf += 10;
  
  if (matchPattern(d)) conf += 10;

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

  if (state.stage === STAGES.IDLE) {
    if (isAccumulation(d)) {
      state.stage = STAGES.ACCUMULATION;
      state.accTime = Date.now();
      stateMap.set(symbol, state);
      lastSignalTime[symbol] = Date.now();
      
      const breakoutTimer = getBreakoutTimer(d);
      const confidence = calculateConfidence(d);
      
      console.log(`🟠 ACCUMULATION: ${symbol} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(2)} | OI=${d.oiChange.toFixed(2)}% | F=${d.fakeOI.toFixed(3)} | Conf=${confidence}% | ⏱️${breakoutTimer}`);
      
      return { type: 'ACCUMULATION', symbol, confidence, data: d, breakoutTimer };
    }
  }

  if (state.stage === STAGES.ACCUMULATION) {
    if (isPumpIncoming(d)) {
      const breakoutTimer = getBreakoutTimer(d);
      state.stage = STAGES.PREDICT;
      state.predictTime = Date.now();
      stateMap.set(symbol, state);
      const confidence = calculateConfidence(d);
      
      console.log(`🟠 PUMP INCOMING: ${symbol} | Vol=${d.volume.toFixed(1)}x | OF=${d.orderFlow.toFixed(2)} | OI=${d.oiChange.toFixed(2)}% | F=${d.fakeOI.toFixed(3)} | Conf=${confidence}% | ⏱️${breakoutTimer}`);
      
      return { type: 'PREDICT', symbol, confidence, data: d, breakoutTimer };
    }
  }

  if (state.stage === STAGES.PREDICT) {
    if (isSniper(d)) {
      const confidence = calculateConfidence(d);
      
      if (confidence < 50) {
        console.log(`❌ ${symbol} → LowConf: conf=${confidence}%`);
        stateMap.set(symbol, { stage: STAGES.IDLE });
        return null;
      }

      const entry = d.price;
      const risk = entry * 0.025;
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

export function getEffectiveOIFromPipeline(data) {
  if (Math.abs(data.oiChange) > 0.01) return data.oiChange;
  return data.fakeOI || 0;
}

const signalStateMachine = {
  getState(symbol) {
    return stateMap.get(symbol) || {
      stage: STAGES.IDLE,
      score: 0,
      lastUpdate: 0,
      data: null,
      persistence: 0,
      maxVolume: 0,
      maxOI: 0,
      stageHistory: []
    };
  },
  setState(symbol, stage, data = {}) {
    const current = this.getState(symbol);
    const newPersistence = stage === current.stage ? current.persistence + 1 : 1;
    
    const newState = {
      stage,
      score: data.confidence || current.score,
      lastUpdate: Date.now(),
      persistence: newPersistence,
      maxVolume: Math.max(current.maxVolume || 0, data.volume || 0),
      maxOI: Math.max(current.maxOI || 0, data.smartOI || data.oiChange || 0),
      data: { ...current.data, ...data },
      stageHistory: [...current.stageHistory, { stage, time: Date.now() }].slice(-10)
    };
    
    stateMap.set(symbol, newState);
    return newState;
  },
  checkTimeout(symbol) {
    const STAGE_TIMEOUTS = {
      ACCUMULATION: 10 * 60 * 1000,
      PREDICT: 5 * 60 * 1000,
      SNIPER: 2 * 60 * 1000
    };
    
    const state = this.getState(symbol);
    const timeout = STAGE_TIMEOUTS[state.stage];
    
    if (timeout && Date.now() - state.lastUpdate > timeout) {
      stateMap.set(symbol, {
        stage: STAGES.IDLE,
        score: 0,
        lastUpdate: Date.now(),
        data: null,
        persistence: 0,
        maxVolume: 0,
        maxOI: 0,
        stageHistory: []
      });
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

export const signalPipeline = {
  processSymbol,
  getState,
  reset,
  setOITracker
};

export { STAGES, signalStateMachine, detectSqueeze, isAbsorption, isExplosive, isRealVolume, getBreakoutTimer };
