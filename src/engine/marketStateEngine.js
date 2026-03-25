import { getEffectiveOI, isTrapAdvanced, predictBreakout, calculatePriorityScore } from './priorityEngine.js';
import { detectMarketRegime } from './regimeDetector.js';
import { passesPatternFilter, applyPatternBoost, buildPattern, patternKey } from './patternMemory.js';
import { passesMemoryFilter, applyMemoryBoost, isOnCooldown, updateSymbolMemory } from './symbolMemory.js';

const STAGES = {
  IDLE: 'IDLE',
  PRE_PUMP: 'PRE_PUMP',
  BUILDUP: 'BUILDUP',
  BREAKOUT: 'BREAKOUT',
  SNIPER: 'SNIPER',
  EXECUTED: 'EXECUTED'
};

const STAGE_TIMEOUTS = {
  PRE_PUMP: 10 * 60 * 1000,
  BUILDUP: 5 * 60 * 1000,
  BREAKOUT: 2 * 60 * 1000,
  SNIPER: 1 * 60 * 1000
};

class MarketStateEngine {
  constructor() {
    this.states = new Map();
  }

  getState(symbol) {
    return this.states.get(symbol) || this.createInitialState(symbol);
  }

  createInitialState(symbol) {
    return {
      symbol,
      stage: STAGES.IDLE,
      score: 0,
      direction: null,
      firstSeen: Date.now(),
      lastUpdate: Date.now(),
      confirmations: 0,
      data: {},
      entry: null,
      executed: false,
      regime: 'NEUTRAL',
      breakoutETA: null,
      confidence: 0
    };
  }

  updateState(symbol, data) {
    let state = this.states.get(symbol);
    if (!state) {
      state = this.createInitialState(symbol);
      this.states.set(symbol, state);
    }

    state.lastUpdate = Date.now();
    state.data = data;
    state.regime = detectMarketRegime(data);

    const oi = getEffectiveOI(data);
    const trap = isTrapAdvanced(data);

    if (trap.isTrap) {
      this.resetState(symbol);
      return state;
    }

    const priorityScore = calculatePriorityScore({
      oiChange: oi,
      fakeOI: data.fakeOI,
      orderFlow: data.orderFlow,
      volume: data.volume,
      priceAcceleration: data.priceAcceleration,
      momentum: data.momentum,
      momentumAcceleration: data.momentumAcceleration || 0
    });

    this.transitionState(state, data, oi, priorityScore);

    return state;
  }

  transitionState(state, data, oi, priorityScore) {
    const oiStrength = Math.abs(oi);
    const fakeOIStrength = Math.abs(data.fakeOI || 0);
    const hasStrongOI = oiStrength > 0.5 || fakeOIStrength > 0.5;
    const hasVeryStrongOI = oiStrength > 1 || fakeOIStrength > 1;

    switch (state.stage) {
      case STAGES.IDLE:
        if (data.volume > 1.5 && data.orderFlow > 1.1 && (hasStrongOI || data.fakeOI > 0.25)) {
          state.stage = STAGES.PRE_PUMP;
          state.direction = data.priceChange > 0 ? 'LONG' : 'SHORT';
          state.score = priorityScore;
          state.breakoutETA = predictBreakout(data);
        }
        if (hasVeryStrongOI && data.volume > 2 && data.orderFlow > 1.3) {
          state.stage = STAGES.BUILDUP;
          state.score = priorityScore + 15;
          state.breakoutETA = predictBreakout(data);
        }
        break;

      case STAGES.PRE_PUMP:
        if (data.volume > 2 && data.orderFlow > 1.3 && data.priceAcceleration > 0.15) {
          state.stage = STAGES.BUILDUP;
          state.score += priorityScore * 0.3;
          state.breakoutETA = predictBreakout(data);
        }
        if (hasStrongOI && data.volume > 2.5) {
          state.stage = STAGES.BUILDUP;
          state.score += priorityScore * 0.4;
        }
        if (state.regime === 'SQUEEZE' && data.volume > 2.5) {
          state.stage = STAGES.BREAKOUT;
          state.score += 10;
        }
        if (hasVeryStrongOI && data.orderFlow > 1.4) {
          state.stage = STAGES.BREAKOUT;
          state.score += 15;
        }
        break;

      case STAGES.BUILDUP:
        if (data.volume > 2.5 && data.orderFlow > 1.4 && data.priceAcceleration > 0.2) {
          state.stage = STAGES.BREAKOUT;
          state.score += priorityScore * 0.5;
        }
        if (hasStrongOI && data.orderFlow > 1.5) {
          state.stage = STAGES.BREAKOUT;
          state.score += priorityScore * 0.6;
        }
        break;

      case STAGES.BREAKOUT:
        if (data.volume > 2.5 && data.orderFlow > 1.5 && (hasStrongOI || data.fakeOI > 0.4)) {
          state.stage = STAGES.SNIPER;
          state.score += priorityScore * 0.5;
          state.entry = this.calculateEntry(data);
        }
        if (data.volume > 3 && data.orderFlow > 1.6 && hasStrongOI) {
          state.stage = STAGES.SNIPER;
          state.score += priorityScore * 0.7;
          state.entry = this.calculateEntry(data);
        }
        break;
        break;

      case STAGES.BREAKOUT:
        if (data.volume > 4 && data.orderFlow > 1.8 && (Math.abs(oi) > 0.5 || data.fakeOI > 0.5)) {
          state.stage = STAGES.SNIPER;
          state.score += priorityScore * 0.5;
          state.entry = this.calculateEntry(data);
        }
        break;

      case STAGES.SNIPER:
        if (!state.executed) {
          state.score = this.calculateAIConfidence(state);
        }
        break;
    }
  }

  calculateEntry(data) {
    const volatility = data.atr || data.price * 0.002;
    const isLong = data.priceChange > 0;

    return {
      entryTrigger: isLong ? data.price + volatility * 0.5 : data.price - volatility * 0.5,
      entryRetest: isLong ? data.price + volatility * 0.1 : data.price - volatility * 0.1,
      stopLoss: isLong ? data.price - volatility * 1.5 : data.price + volatility * 1.5,
      type: isLong ? 'LONG' : 'SHORT'
    };
  }

  calculateAIConfidence(state) {
    const data = state.data;
    let score = 0;

    if (state.stage === 'SNIPER') score += 25;
    else if (state.stage === 'BREAKOUT') score += 20;
    else if (state.stage === 'BUILDUP') score += 15;
    else if (state.stage === 'PRE_PUMP') score += 10;

    const oi = getEffectiveOI(data);
    const oiStrength = Math.abs(oi);
    const fakeOIStrength = Math.abs(data.fakeOI || 0);
    const effectiveOI = Math.max(oiStrength, fakeOIStrength);

    if (effectiveOI > 2) score += 25;
    else if (effectiveOI > 1) score += 20;
    else if (effectiveOI > 0.5) score += 15;
    else if (effectiveOI > 0.3) score += 10;

    if (data.volume > 4) score += 15;
    else if (data.volume > 2.5) score += 10;
    else if (data.volume > 2) score += 5;

    if (data.orderFlow > 2) score += 15;
    else if (data.orderFlow > 1.5) score += 10;
    else if (data.orderFlow > 1.2) score += 5;

    if (data.priceAcceleration > 0.3) score += 15;
    else if (data.priceAcceleration > 0.2) score += 10;
    else if (data.priceAcceleration > 0.1) score += 5;

    if (state.regime === 'SQUEEZE') score += 15;
    else if (state.regime === 'TREND') score += 10;
    else if (state.regime === 'NEUTRAL') score += 3;
    else if (state.regime === 'CHOP') score -= 15;

    const pKey = patternKey(buildPattern(data));
    const patternMem = state.patternMemory?.get?.(pKey);
    if (patternMem) score += (patternMem.score - 50) * 0.2;

    const symMem = state.symbolMemory?.get?.(state.symbol);
    if (symMem) score += (symMem.score - 50) * 0.2;

    const trap = isTrapAdvanced(data);
    if (trap.isTrap) score -= 25;

    state.confidence = Math.max(0, Math.min(100, Math.round(score)));
    return state.confidence;
  }

  shouldExecute(state) {
    if (state.executed) return false;
    if (state.stage !== STAGES.SNIPER) return false;
    if (state.regime === 'CHOP') return false;
    if (state.confidence < 60) return false;
    if (isOnCooldown(state.symbol)) return false;
    if (!passesMemoryFilter(state.symbol)) return false;
    if (!passesPatternFilter(state.data)) return false;

    return true;
  }

  execute(state, result) {
    state.executed = true;
    state.executedAt = Date.now();
    updateSymbolMemory(state.symbol, result);
  }

  checkTimeout(symbol) {
    const state = this.states.get(symbol);
    if (!state) return false;

    const timeout = STAGE_TIMEOUTS[state.stage];
    if (timeout && Date.now() - state.lastUpdate > timeout) {
      this.resetState(symbol);
      return true;
    }
    return false;
  }

  resetState(symbol) {
    const state = this.states.get(symbol);
    if (state) {
      state.stage = STAGES.IDLE;
      state.score = 0;
      state.direction = null;
      state.entry = null;
      state.executed = false;
      state.breakoutETA = null;
    }
  }

  cleanup() {
    const now = Date.now();
    for (const [symbol, state] of this.states) {
      if (now - state.lastUpdate > 120000) {
        this.states.delete(symbol);
      }
    }
  }

  getActiveStates() {
    return Array.from(this.states.values()).filter(s => s.stage !== STAGES.IDLE);
  }

  getStateForSymbol(symbol) {
    return this.states.get(symbol);
  }

  getSetupSignals() {
    return this.getActiveStates()
      .filter(s => s.stage === STAGES.PRE_PUMP || s.stage === STAGES.BUILDUP)
      .map(s => ({
        type: 'SETUP',
        tier: s.stage,
        symbol: s.symbol,
        direction: s.direction,
        score: s.score,
        regime: s.regime,
        breakoutETA: s.breakoutETA,
        confidence: s.confidence
      }));
  }

  getExecutionSignals() {
    return this.getActiveStates()
      .filter(s => s.stage === STAGES.SNIPER && !s.executed)
      .map(s => ({
        type: 'EXECUTION',
        tier: 'SNIPER',
        symbol: s.symbol,
        direction: s.direction,
        score: s.score,
        regime: s.regime,
        confidence: s.confidence,
        entry: s.entry
      }));
  }
}

export const marketStateEngine = new MarketStateEngine();
export { STAGES };
