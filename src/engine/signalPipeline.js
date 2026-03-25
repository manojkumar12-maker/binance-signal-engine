const STAGES = {
  IDLE: 'IDLE',
  ACCUMULATION: 'ACCUMULATION',
  PREDICT: 'PREDICT',
  SNIPER: 'SNIPER',
  EARLY: 'EARLY',
  CONFIRMED: 'CONFIRMED',
  PRE_PUMP: 'PRE_PUMP',
  PUMP_CONFIRMED: 'PUMP_CONFIRMED'
};

const stateMap = new Map();
let oiTrackerModule = null;

export function setOITracker(tracker) {
  oiTrackerModule = tracker;
}

function getEffectiveOI(d) {
  if (Math.abs(d.oiChange) > 0.2) return d.oiChange;
  return d.fakeOI || 0;
}

function isTrap(d) {
  return (
    (d.priceChange > 3 && d.orderFlow < 1.2) ||
    (d.priceChange < -3 && d.orderFlow < 1.2)
  );
}

function isAccumulation(d) {
  return (
    d.volume > 2 &&
    Math.abs(d.priceChange) < 1.5 &&
    Math.abs(d.fakeOI || 0) > 0.3 &&
    Math.abs(d.oiChange || 0) > 0.3 &&
    d.orderFlow > 1.2
  );
}

function isPumpIncoming(d) {
  return (
    d.volume > 2.5 &&
    d.orderFlow > 1.5 &&
    Math.abs(getEffectiveOI(d)) > 0.5
  );
}

function isSniper(d) {
  return (
    d.priceAcceleration > 0.3 &&
    d.volume > 3 &&
    d.orderFlow > 1.8 &&
    Math.abs(getEffectiveOI(d)) > 0.5 &&
    !isTrap(d)
  );
}

function calculateConfidence(d) {
  let conf = 50;

  if (Math.abs(d.oiChange || 0) > 1) conf += 20;
  if (d.volume > 3) conf += 15;
  if (d.orderFlow > 1.8) conf += 10;
  if (Math.abs(d.fakeOI || 0) > 0.5) conf += 10;

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
    atr: data.atr || 0
  };
}

export function processSymbol(symbol, marketData) {
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
      return { type: 'ACCUMULATION', symbol, confidence: 50, data: d };
    }
  }

  if (state.stage === STAGES.ACCUMULATION) {
    if (isPumpIncoming(d)) {
      state.stage = STAGES.PREDICT;
      state.predictTime = Date.now();
      stateMap.set(symbol, state);
      return { type: 'PREDICT', symbol, confidence: 70, data: d };
    }
  }

  if (state.stage === STAGES.PREDICT) {
    if (isSniper(d)) {
      const confidence = calculateConfidence(d);
      
      if (confidence < 80) {
        stateMap.set(symbol, { stage: STAGES.IDLE });
        return null;
      }

      const entry = d.price;
      const risk = entry * 0.03;
      const sl = entry - risk;

      state.stage = STAGES.SNIPER;
      stateMap.set(symbol, state);

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
        data: d
      };
    }
  }

  stateMap.set(symbol, state);
  return null;
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
  if (Math.abs(data.oiChange) > 0.2) return data.oiChange;
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
      EARLY: 5 * 60 * 1000,
      CONFIRMED: 3 * 60 * 1000,
      SNIPER: 2 * 60 * 1000,
      PRE_PUMP: 10 * 60 * 1000,
      PUMP_CONFIRMED: 3 * 60 * 1000
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

export { STAGES, signalStateMachine };
