import { 
  calculatePriorityScore, 
  getEffectiveOI, 
  isPerfectSniper, 
  isTrapAdvanced, 
  predictBreakout, 
  applySniperFilter,
  calculateSniperConfidence 
} from './priorityEngine.js';

const STAGES = {
  IDLE: 'IDLE',
  EARLY: 'EARLY',
  CONFIRMED: 'CONFIRMED',
  SNIPER: 'SNIPER',
  PRE_PUMP: 'PRE_PUMP',
  PUMP_CONFIRMED: 'PUMP_CONFIRMED'
};

const STAGE_TIMEOUTS = {
  EARLY: 5 * 60 * 1000,
  CONFIRMED: 3 * 60 * 1000,
  SNIPER: 2 * 60 * 1000,
  PRE_PUMP: 10 * 60 * 1000,
  PUMP_CONFIRMED: 3 * 60 * 1000
};

class SignalStateMachine {
  constructor() {
    this.states = new Map();
    this.listeners = new Map();
  }

  getState(symbol) {
    return this.states.get(symbol) || {
      stage: STAGES.IDLE,
      score: 0,
      lastUpdate: 0,
      data: null,
      persistence: 0,
      maxVolume: 0,
      maxOI: 0,
      stageHistory: []
    };
  }

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
    
    this.states.set(symbol, newState);
    this.emit(stage, symbol, newState);
    return newState;
  }

  progress(symbol, targetStage, data) {
    const current = this.getState(symbol);
    
    const allowedTransitions = {
      [STAGES.IDLE]: [STAGES.EARLY, STAGES.PRE_PUMP],
      [STAGES.EARLY]: [STAGES.CONFIRMED, STAGES.IDLE],
      [STAGES.CONFIRMED]: [STAGES.SNIPER, STAGES.EARLY, STAGES.IDLE],
      [STAGES.SNIPER]: [STAGES.IDLE],
      [STAGES.PRE_PUMP]: [STAGES.PUMP_CONFIRMED, STAGES.IDLE],
      [STAGES.PUMP_CONFIRMED]: [STAGES.IDLE, STAGES.SNIPER]
    };

    const allowed = allowedTransitions[current.stage] || [];

    if (allowed.includes(targetStage)) {
      this.setState(symbol, targetStage, data);
      return true;
    }

    return false;
  }

  checkTimeout(symbol) {
    const state = this.getState(symbol);
    const timeout = STAGE_TIMEOUTS[state.stage];
    
    if (timeout && Date.now() - state.lastUpdate > timeout) {
      this.states.set(symbol, {
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
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  emit(event, symbol, state) {
    const callbacks = this.listeners.get(event) || [];
    callbacks.forEach(cb => cb(symbol, state));
  }

  getActiveSignals() {
    return Array.from(this.states.entries())
      .filter(([_, s]) => s.stage !== STAGES.IDLE)
      .map(([symbol, state]) => ({ symbol, ...state }));
  }

  reset() {
    this.states.clear();
  }
}

const signalStateMachine = new SignalStateMachine();

function getSmartOI(oiChange) {
  return oiChange * 10;
}

function normalizeOI(oiChange, symbol) {
  if (!oiTrackerModule || !symbol) return oiChange * 10;
  
  try {
    const historyLen = oiTrackerModule.getOIHistoryLength?.(symbol) || 0;
    if (historyLen < 10) return oiChange * 10;
    
    const fakeOI = oiTrackerModule.getFakeOI?.(symbol);
    if (fakeOI !== null && fakeOI !== undefined) {
      return fakeOI * 10;
    }
    
    return oiChange * 10;
  } catch (e) {
    return oiChange * 10;
  }
}

function getVelocity(data) {
  return (data.priceAcceleration || 0) + (data.momentumAcceleration || 0);
}

function estimateBreakoutTime(data) {
  if (!data) return null;
  
  let score = 0;

  if (data.fakeOI > 0.4) score += 2;
  if (data.orderFlow > 1.8) score += 2;
  if (data.volume > 3) score += 2;

  if (data.priceAcceleration > 0.15) score += 2;
  if (data.priceAcceleration > 0.25) score += 3;

  if (data.momentum > 0) score += 1;
  if (data.momentumAcceleration > 0) score += 1;

  const normOI = normalizeOI(data.oiChange || 0, data.symbol);
  if (normOI > 0.3) score += 1;

  if (score >= 10) return 'IMMINENT';
  if (score >= 8) return 'VERY_SOON';
  if (score >= 6) return 'SOON';
  if (score >= 4) return 'BUILDING';

  return null;
}

function isBreakingOut(data) {
  if (!data) return false;
  return (
    data.priceAcceleration > 0.15 &&
    data.volume > 2.5 &&
    data.orderFlow > 1.4
  );
}

function getSniperEntry(data, price) {
  if (!data || !price) return null;

  const isLong = data.priceChange > 0;
  const isShort = data.priceChange < 0;

  const volatility = data.atr || price * 0.002;
  
  if (isLong) {
    return {
      type: 'LONG',
      entryTrigger: price + volatility * 0.5,
      entryRetest: price + volatility * 0.1,
      stopLoss: price - volatility * 1.5,
      invalidation: price - volatility * 2
    };
  }

  if (isShort) {
    return {
      type: 'SHORT',
      entryTrigger: price - volatility * 0.5,
      entryRetest: price - volatility * 0.1,
      stopLoss: price + volatility * 1.5,
      invalidation: price + volatility * 2
    };
  }

  return null;
}

function validateSniperEntry(data) {
  if (!data) return false;

  if (data.volume < 2.5) return false;
  if (data.orderFlow < 1.3) return false;

  const normOI = normalizeOI(data.oiChange || 0, data.symbol);
  if (normOI < 0.2 && (data.fakeOI || 0) < 0.3) return false;

  if (data.trap) return false;

  return true;
}

function getPrePumpType(data) {
  if (!data) return 'PRE_PUMP';
  
  if (data.fakeOI > 0.35 && Math.abs(data.priceChange || 0) < 1.5 && (data.volume || 0) > 2) {
    return 'PRE_PUMP_STEALTH';
  }
  if ((data.volume || 0) > 3 && (data.orderFlow || 0) > 1.5 && (data.fakeOI || 0) > 0.4) {
    return 'PRE_PUMP_AGGRESSIVE';
  }
  if ((data.oiChange || 0) < 0 && (data.priceChange || 0) > 0 && (data.fakeOI || 0) > 0.3) {
    return 'PRE_PUMP_SQUEEZE';
  }
  
  return 'PRE_PUMP';
}

function calculatePositionSize(balance, riskPercent, entry, stop) {
  const riskAmount = balance * riskPercent;
  const stopDistance = Math.abs(entry - stop);
  if (stopDistance === 0) return 0;
  return riskAmount / stopDistance;
}

function getWeightedOI(oiChange) {
  const absOI = Math.abs(oiChange) * 10;
  if (absOI > 5) return 3;
  if (absOI > 2) return 2;
  if (absOI > 0.5) return 1;
  return 0;
}

function getMomentumBurst(data) {
  return data.priceAcceleration > 0.15 && data.momentumAcceleration > 0.1;
}

function detectSqueeze(data) {
  if (data.oiChange < 0 && data.priceChange > 0) {
    return 'SHORT_SQUEEZE';
  }
  if (data.oiChange < 0 && data.priceChange < 0) {
    return 'LONG_EXIT';
  }
  if (data.oiChange > 0 && data.priceChange < 0) {
    return 'SHORT_BUILDUP';
  }
  if (data.oiChange > 0 && data.priceChange > 0) {
    return 'LONG_BUILDUP';
  }
  return null;
}

function detectShortSetup(data) {
  return (
    data.priceChange < 0 &&
    data.orderFlow < 0.8 &&
    normalizeOI(data.oiChange) < -0.2
  );
}

function getSignalDirection(data) {
  const squeeze = detectSqueeze(data);
  if (squeeze === 'SHORT_SQUEEZE' || squeeze === 'SHORT_BUILDUP') return 'SHORT';
  if (detectShortSetup(data)) return 'SHORT';
  if (data.priceChange > 0) return 'LONG';
  return 'LONG';
}

function getOIStrength(symbol) {
  if (!oiTrackerModule) return 0;
  
  try {
    const historyLen = oiTrackerModule.getOIHistoryLength?.(symbol) || 0;
    if (historyLen < 5) return 0;
    
    const oiChange = oiTrackerModule.getChange?.(symbol) || 0;
    const fakeOI = oiTrackerModule.getFakeOI?.(symbol);
    
    if (oiChange === 0) return 0;
    
    let score = 0;
    if (Math.abs(oiChange) > 0.3) score += 1;
    if (Math.abs(oiChange) > 0.6) score += 2;
    if (fakeOI && Math.abs(fakeOI) > 0.3) score += 1;
    if (fakeOI && Math.abs(fakeOI) > 0.5) score += 1;
    
    return score;
  } catch (e) {
    return 0;
  }
}

function isBreakoutImminent(data) {
  return (
    data.volume > 3 &&
    data.orderFlow > 1.8 &&
    data.fakeOI > 0.4 &&
    data.priceAcceleration > 0.25
  );
}

function isStableFakeOI(fakeOI, priceChange, volumeTrend) {
  if (Math.abs(fakeOI) < 0.2) return false;
  if (Math.sign(fakeOI) !== Math.sign(priceChange)) return false;
  if (volumeTrend && volumeTrend < 1.5) return false;
  return true;
}

function isSniperEntry(data) {
  if (!data) return false;
  
  const priorityScore = calculatePriorityScore(data);
  if (priorityScore < 60) return false;
  
  return isPerfectSniper(data);
}

function rankSignal(data, confidence) {
  return (
    confidence * 0.4 +
    (data.volume || 0) * 4 +
    (data.orderFlow || 0) * 10 +
    Math.abs(data.oiChange || 0) * 10
  );
}

function isConfirmedScore(data) {
  let score = 0;

  if (data.priceChange > 2.5) score += 2;
  if (data.volume > 1.8) score += 2;
  if (data.orderFlow > 1.2) score += 2;

  if (data.fakeOI > 0.25) score += 3;
  else if (data.fakeOI > 0.15) score += 2;

  score += getWeightedOI(data.oiChange);

  const velocity = getVelocity(data);
  if (velocity > 0.2) score += 2;

  const squeeze = detectSqueeze(data);
  if (squeeze === 'LONG_BUILDUP' || squeeze === 'SHORT_SQUEEZE') score += 3;

  if (data.volume < 1) score -= 2;

  return score >= 4;
}

function isSniperScore(data, symbol) {
  let score = 0;

  if (data.priceChange > 3) score += 2;
  if (data.volume > 2) score += 2;
  if (data.orderFlow > 1.4) score += 2;

  if (data.fakeOI > 0.35) score += 3;
  else if (data.fakeOI > 0.2) score += 2;

  if (normalizeOI(data.oiChange, symbol) > 0.5 || Math.abs(data.fakeOI) > 0.3) score += 2;

  score += getWeightedOI(data.oiChange);

  const momentumBurst = getMomentumBurst(data);
  if (momentumBurst) score += 2;

  const velocity = getVelocity(data);
  if (velocity > 0.3) score += 3;
  else if (velocity > 0.15) score += 1;

  if (isSniperEntry(data)) score += 3;

  const oiStrength = getOIStrength(symbol);
  score += oiStrength;

  if (normalizeOI(data.oiChange, symbol) > 0.7) score += 2;
  if (data.fakeOI > 0.5) score += 3;

  const squeeze = detectSqueeze(data);
  if (squeeze === 'SHORT_SQUEEZE' || squeeze === 'LONG_BUILDUP') score += 4;

  if (data.volume < 1) score -= 2;

  return score >= 6;
}

let oiTrackerModule = null;

export function setOITracker(tracker) {
  oiTrackerModule = tracker;
}

function isOIReady(symbol) {
  if (!oiTrackerModule) return true;
  return oiTrackerModule.isOIReady(symbol);
}

function getOIHistoryLength(symbol) {
  if (!oiTrackerModule) return 0;
  return oiTrackerModule.getOIHistoryLength(symbol);
}

function detectTrap(data) {
  if (!data.candle) return null;
  
  const { high, low, close, open, volume } = data.candle;
  const body = Math.abs(close - open) || 1;
  const wick = high - Math.max(close, open);
  const wickRatio = wick / body;
  const { orderFlow, fakeOI, priceChange } = data;

  if (wickRatio > 2 && orderFlow < 1 && fakeOI < 0) return 'BULL_TRAP';
  if (wickRatio > 2 && orderFlow > 1 && fakeOI > 0) return 'BEAR_TRAP';
  
  if (volume > 5 && Math.abs(priceChange) < 1 && Math.abs(fakeOI) > 0.5) return 'ABSORPTION_TRAP';

  return null;
}

function detectPrePump(data, state) {
  const trapCheck = isTrapAdvanced(data);
  if (trapCheck.isTrap) return { isPrePump: false, score: 0, reasons: [trapCheck.reason], type: null, breakoutTime: null, breakoutETA: null };
  
  const smartOI = normalizeOI(data.oiChange, data.symbol);
  const stableFakeOI = isStableFakeOI(data.fakeOI, data.priceChange, data.volume);
  const effectiveOI = getEffectiveOI(data);
  
  let score = 0;
  const reasons = [];

  if (data.volume > 2 && data.orderFlow > 1.3 && (Math.abs(effectiveOI) > 0.25 || smartOI > 0.2)) {
    const breakoutETA = predictBreakout(data);
    return { isPrePump: true, score: 10, reasons: ['Early breakout trigger'], type: getPrePumpType(data), breakoutTime: breakoutETA?.eta || null, breakoutETA };
  }

  if (data.volume < 1.5 && Math.abs(data.fakeOI || 0) < 0.2 && Math.abs(data.priceChange || 0) < 1) {
    return { isPrePump: false, score: 0, reasons: ['Weak signal'], type: null, breakoutTime: null, breakoutETA: null };
  }

  if (smartOI > 0.1) { score += 2; reasons.push('Smart OI buildup'); }
  if (Math.abs(data.fakeOI) > 0.15) { 
    score += stableFakeOI ? 3 : 1; 
    reasons.push(stableFakeOI ? 'Stable flow accumulation' : 'Flow accumulation'); 
  }
  if (data.orderFlow > 1.05 || data.orderFlow < 0.95) { score += 1; reasons.push('Stealth accumulation'); }
  if (data.volume > 1.3) { score += 1; reasons.push('Volume rising'); }
  if (data.momentumAcceleration > 0 || data.momentumAcceleration < 0) { score += 1; reasons.push('Momentum building'); }

  score += getWeightedOI(data.oiChange);

  if (data.priceChange < 3) { score += 1; reasons.push('Pre-move consolidation'); }

  if (data.priceAcceleration > 0.1) { score += 2; reasons.push('Breakout imminent'); }

  if (state?.persistence >= 2) { score += 2; reasons.push('Persistence confirmed'); }

  const breakoutETA = score >= 3 ? predictBreakout(data) : null;
  const breakoutTime = breakoutETA?.eta || null;
  
  return { 
    isPrePump: score >= 3, 
    score, 
    reasons, 
    type: getPrePumpType(data),
    breakoutTime,
    breakoutETA
  };
}

function detectPumpConfirmed(data, state) {
  if (state?.stage !== STAGES.PRE_PUMP) return false;

  const breakingOut = isBreakingOut(data);
  const breakoutImminent = estimateBreakoutTime(data);
  
  const smartOI = normalizeOI(data.oiChange, data.symbol);
  const fakeOIPrimary = (data.fakeOI || 0) > 0.25;
  
  const volumeValid = (data.volume || 0) > 1.8;
  const orderFlowValid = (data.orderFlow || 1) > 1.2;
  const priceAccelValid = (data.priceAcceleration || 0) > 0.08;
  const oiValid = fakeOIPrimary || smartOI > 0.15;

  if (breakingOut && volumeValid && orderFlowValid) return true;
  if (breakoutImminent === 'IMMINENT' || breakoutImminent === 'VERY_SOON') return true;

  return volumeValid && orderFlowValid && priceAccelValid && oiValid;
}

function detectEarly(data, state) {
  if (state?.stage !== STAGES.IDLE) return false;
  if (data.fakeOI !== undefined && data.fakeOI < -0.3) return false;

  return (
    Math.abs(data.priceChange) > 1.5 &&
    data.volume > 1.5 &&
    data.orderFlow > 1.1
  );
}

function detectConfirmed(data, state) {
  if (state?.stage !== STAGES.EARLY) return false;
  return isConfirmedScore(data);
}

function detectSniper(data, state) {
  if (!state) return false;
  const validStage = state.stage === STAGES.CONFIRMED || state.stage === STAGES.PUMP_CONFIRMED;
  if (!validStage) return false;
  if (state.persistence < 2) return false;
  
  const trapCheck = isTrapAdvanced(data);
  if (trapCheck.isTrap) return false;
  
  if (data.priceChange < 0 || data.priceChange > 15) return false;
  
  const filterResult = applySniperFilter(data);
  if (!filterResult.pass) return false;
  
  const priorityScore = calculatePriorityScore(data);
  if (priorityScore < 60) return false;
  
  return true;
}

function getSniperScore(data) {
  const filterResult = applySniperFilter(data);
  if (!filterResult.pass) {
    return 0;
  }

  const priorityScore = calculatePriorityScore(data);
  if (priorityScore < 60) {
    return 0;
  }

  return calculateSniperConfidence(data);
}

class SignalPipeline {
  constructor() {
    this.signalState = signalStateMachine;
    this.prePumpPanel = [];
    this.pumpConfirmedPanel = [];
    this.earlySignals = [];
    this.confirmedSignals = [];
    this.sniperSignals = [];
  }

  buildMarketData(symbol, data) {
    return {
      symbol,
      priceChange: data.priceChange || 0,
      volume: data.volume || 1,
      orderFlow: data.orderFlow || 1,
      oiChange: data.oiChange || 0,
      fakeOI: data.fakeOI || 0,
      smartOI: getSmartOI(data.oiChange || 0),
      liquidity: data.liquidity || 'BALANCED',
      trap: data.trap || null,
      priceAcceleration: data.priceAcceleration || 0,
      momentum: data.momentum || 0,
      momentumAcceleration: data.momentumAcceleration || 0,
      candle: data.candle || null,
      buyVolume: data.buyVolume || 0,
      sellVolume: data.sellVolume || 0,
      high: data.high || 0,
      close: data.close || 0
    };
  }

  getOIValidation(symbol) {
    const state = this.signalState.getState(symbol);
    const oi = state?.data?.oiChange || 0;
    const fakeOI = state?.data?.fakeOI || 0;
    const smartOI = getSmartOI(oi);
    return { oi, fakeOI, smartOI, oiValid: smartOI > 0.2, fakeValid: fakeOI > 0.4 };
  }

  isLiquidityTrap(d) {
    return detectTrap(d) !== null;
  }

  isEarly(d) {
    return detectEarly(d, this.signalState.getState(d.symbol));
  }

  isConfirmed(d) {
    return detectConfirmed(d, this.signalState.getState(d.symbol));
  }

  isSniper(d) {
    return detectSniper(d, this.signalState.getState(d.symbol));
  }

  isPrePump(d) {
    const result = detectPrePump(d, this.signalState.getState(d.symbol));
    return result.isPrePump;
  }

  isPumpConfirmed(d) {
    return detectPumpConfirmed(d, this.signalState.getState(d.symbol));
  }

  processPrePumpFlow(symbol, d) {
    const state = this.signalState.getState(symbol);
    const prePumpResult = detectPrePump(d, state);

    if (state.stage === STAGES.IDLE) {
      if (prePumpResult.isPrePump) {
        this.signalState.setState(symbol, STAGES.PRE_PUMP, {
          priceChange: d.priceChange,
          volume: d.volume,
          fakeOI: d.fakeOI,
          smartOI: getSmartOI(d.oiChange),
          oiChange: d.oiChange,
          confidence: Math.min(70, 40 + d.volume * 5 + (d.fakeOI || 0) * 20 + prePumpResult.score * 2)
        });

        this.prePumpPanel.push({
          type: getSignalDirection(d),
          strength: 'PRE_PUMP',
          symbol,
          confidence: 50,
          score: prePumpResult.score,
          reasons: prePumpResult.reasons
        });
        return true;
      }
    }

    if (state.stage === STAGES.PRE_PUMP) {
      this.signalState.checkTimeout(symbol);
      const currentState = this.signalState.getState(symbol);
      if (currentState.stage !== STAGES.PRE_PUMP) return false;

      if (this.isPumpConfirmed(d)) {
        this.signalState.setState(symbol, STAGES.PUMP_CONFIRMED, {
          priceChange: d.priceChange,
          volume: d.volume,
          oiChange: d.oiChange,
          fakeOI: d.fakeOI,
          smartOI: getSmartOI(d.oiChange),
          confidence: 75
        });

        this.pumpConfirmedPanel.push({
          type: getSignalDirection(d),
          strength: 'PUMP_CONFIRMED',
          symbol,
          confidence: 75
        });
        return true;
      }
    }

    return false;
  }

  processTrendFlow(symbol, d) {
    const state = this.signalState.getState(symbol);

    if (state.stage === STAGES.IDLE) {
      if (this.isEarly(d)) {
        this.signalState.setState(symbol, STAGES.EARLY, {
          priceChange: d.priceChange,
          volume: d.volume,
          orderFlow: d.orderFlow,
          oiChange: d.oiChange,
          fakeOI: d.fakeOI,
          smartOI: getSmartOI(d.oiChange),
          confidence: 50
        });

        this.earlySignals.push({
          type: getSignalDirection(d),
          strength: 'EARLY',
          symbol,
          confidence: 50
        });
        return true;
      }
    }

    if (state.stage === STAGES.EARLY) {
      this.signalState.checkTimeout(symbol);
      const currentState = this.signalState.getState(symbol);
      if (currentState.stage !== STAGES.EARLY) return false;

      if (this.isConfirmed(d)) {
        this.signalState.setState(symbol, STAGES.CONFIRMED, {
          priceChange: d.priceChange,
          volume: d.volume,
          oiChange: d.oiChange,
          fakeOI: d.fakeOI,
          smartOI: getSmartOI(d.oiChange),
          confidence: 65
        });

        this.confirmedSignals.push({
          type: getSignalDirection(d),
          strength: 'CONFIRMED',
          symbol,
          confidence: 65
        });
        return true;
      }
    }

    if (state.stage === STAGES.CONFIRMED) {
      this.signalState.checkTimeout(symbol);
      const currentState = this.signalState.getState(symbol);
      if (currentState.stage !== STAGES.CONFIRMED) return false;

      if (this.isSniper(d)) {
        let confidence = getSniperScore(d);
        
        const stateData = this.signalState.getState(symbol);
        if (stateData.maxVolume > 5) confidence += 5;
        if (stateData.maxOI > 0.3) confidence += 5;
        
        confidence = Math.min(confidence, 95);

        this.signalState.setState(symbol, STAGES.SNIPER, {
          priceChange: d.priceChange,
          volume: d.volume,
          oiChange: d.oiChange,
          fakeOI: d.fakeOI,
          smartOI: getSmartOI(d.oiChange),
          confidence,
          sniperScore: confidence
        });

        this.sniperSignals.push({
          type: getSignalDirection(d),
          strength: 'SNIPER',
          symbol,
          confidence,
          score: confidence
        });
        return true;
      }
    }

    return false;
  }

  processSymbol(symbol, marketData) {
    const d = this.buildMarketData(symbol, marketData);
    
    const oiHistoryLen = getOIHistoryLength(symbol);
    
    d.trap = detectTrap(d);
    if (d.trap) {
      this.signalState.setState(symbol, STAGES.IDLE);
      return null;
    }

    this.processPrePumpFlow(symbol, d);
    this.processTrendFlow(symbol, d);
    
    const finalState = this.signalState.getState(symbol);
    return finalState.stage !== STAGES.IDLE ? finalState : null;
  }

  getTopSignals(strength, limit = 5) {
    const signals = {
      'PRE_PUMP': this.prePumpPanel,
      'PUMP_CONFIRMED': this.pumpConfirmedPanel,
      'EARLY': this.earlySignals,
      'CONFIRMED': this.confirmedSignals,
      'SNIPER': this.sniperSignals
    }[strength] || [];

    return signals.slice(0, limit);
  }

  getPipelineSummary() {
    return {
      prePump: this.prePumpPanel.slice(0, 10),
      pumpConfirmed: this.pumpConfirmedPanel.slice(0, 10),
      early: this.earlySignals.slice(0, 5),
      confirmed: this.confirmedSignals.slice(0, 5),
      sniper: this.sniperSignals.slice(0, 5)
    };
  }

  getActiveStates() {
    return this.signalState.getActiveSignals();
  }

  getState(symbol) {
    return this.signalState.getState(symbol);
  }

  reset() {
    this.prePumpPanel = [];
    this.pumpConfirmedPanel = [];
    this.earlySignals = [];
    this.confirmedSignals = [];
    this.sniperSignals = [];
    this.signalState.reset();
  }
}

export const signalPipeline = new SignalPipeline();
export { STAGES, signalStateMachine, getSniperScore, getSmartOI, calculatePriorityScore, getEffectiveOI, isPerfectSniper, isTrapAdvanced, predictBreakout, applySniperFilter, calculateSniperConfidence };