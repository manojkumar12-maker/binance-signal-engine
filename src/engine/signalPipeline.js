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
      data: null
    };
  }

  setState(symbol, stage, data = {}) {
    const current = this.getState(symbol);
    this.states.set(symbol, {
      stage,
      score: data.confidence || current.score,
      lastUpdate: Date.now(),
      data: { ...current.data, ...data }
    });
    this.emit(stage, symbol, this.states.get(symbol));
  }

  progress(symbol, targetStage, data) {
    const current = this.getState(symbol);
    
    const allowedTransitions = {
      [STAGES.IDLE]: [STAGES.EARLY, STAGES.PRE_PUMP],
      [STAGES.EARLY]: [STAGES.CONFIRMED, STAGES.IDLE],
      [STAGES.CONFIRMED]: [STAGES.SNIPER, STAGES.EARLY, STAGES.IDLE],
      [STAGES.SNIPER]: [STAGES.IDLE],
      [STAGES.PRE_PUMP]: [STAGES.PUMP_CONFIRMED, STAGES.IDLE],
      [STAGES.PUMP_CONFIRMED]: [STAGES.IDLE]
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
      this.states.set(symbol, { stage: STAGES.IDLE, score: 0, lastUpdate: Date.now(), data: null });
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
    const oi = this.signalState.getState(symbol)?.data?.oiChange || 0;
    const fakeOI = this.signalState.getState(symbol)?.data?.fakeOI || 0;
    return { oi, fakeOI, oiValid: oi > 0.3, fakeValid: fakeOI > 0.4 };
  }

  isLiquidityTrap(d) {
    if (!d.candle) return false;
    
    const { high, close, low, open } = d.candle;
    if (!high || !low) return false;
    
    const wick = (high - Math.max(close, open)) / (high || 1);
    const lowerWick = (Math.min(close, open) - low) / (high - low || 1);
    const delta = d.buyVolume - d.sellVolume;
    
    if (d.priceChange > 5 && wick > 0.3 && delta < 0) {
      return true;
    }
    if (d.priceChange < -5 && lowerWick > 0.3 && delta > 0) {
      return true;
    }
    
    return false;
  }

  isEarly(d) {
    return (
      Math.abs(d.priceChange) > 2 &&
      d.volume > 2 &&
      d.orderFlow > 1.2
    );
  }

  isConfirmed(d) {
    const { oi, fakeOI, oiValid, fakeValid } = { oiValid: d.oiChange > 0.3, fakeValid: d.fakeOI > 0.4, oi: d.oiChange, fakeOI: d.fakeOI };
    
    return (
      Math.abs(d.priceChange) > 3 &&
      d.volume > 3 &&
      d.orderFlow > 1.5 &&
      (oiValid || fakeValid)
    );
  }

  isSniper(d) {
    const { oi, fakeOI } = d;
    const oiValid = oi > 0.5 || fakeOI > 0.6;
    
    return (
      Math.abs(d.priceChange) > 4 &&
      d.volume > 4 &&
      d.orderFlow > 1.8 &&
      oiValid &&
      d.momentumAcceleration > 1.2 &&
      !this.isLiquidityTrap(d)
    );
  }

  isPrePump(d) {
    return (
      d.volume > 2 &&
      Math.abs(d.priceChange) < 2 &&
      d.fakeOI > 0.3 &&
      d.orderFlow > 1.2
    );
  }

  isPumpConfirmed(d) {
    const { oi, fakeOI } = d;
    const oiValid = oi > 0.5 || fakeOI > 0.5;
    
    return (
      d.volume > 4 &&
      d.orderFlow > 2 &&
      oiValid &&
      d.priceAcceleration > 0.3
    );
  }

  processPrePumpFlow(symbol, d) {
    const state = this.signalState.getState(symbol);
    const now = Date.now();

    if (state.stage === STAGES.IDLE) {
      if (this.isPrePump(d)) {
        this.signalState.setState(symbol, STAGES.PRE_PUMP, {
          priceChange: d.priceChange,
          volume: d.volume,
          fakeOI: d.fakeOI,
          confidence: Math.min(70, 40 + d.volume * 5 + d.fakeOI * 20)
        });
        
        this.prePumpPanel.push({
          type: d.priceChange > 0 ? 'LONG' : 'SHORT',
          strength: 'PRE_PUMP',
          symbol,
          confidence: 50
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
          confidence: 75
        });
        
        this.pumpConfirmedPanel.push({
          type: d.priceChange > 0 ? 'LONG' : 'SHORT',
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
          confidence: 50
        });
        
        this.earlySignals.push({
          type: d.priceChange > 0 ? 'LONG' : 'SHORT',
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
          confidence: 65
        });
        
        this.confirmedSignals.push({
          type: d.priceChange > 0 ? 'LONG' : 'SHORT',
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
        let confidence = 70;
        if (Math.abs(d.oiChange) > 1 || Math.abs(d.fakeOI) > 0.8) confidence += 10;
        if (d.volume > 5) confidence += 5;
        if (d.momentumAcceleration > 2) confidence += 5;
        confidence = Math.min(confidence, 95);
        
        this.signalState.setState(symbol, STAGES.SNIPER, {
          priceChange: d.priceChange,
          volume: d.volume,
          oiChange: d.oiChange,
          fakeOI: d.fakeOI,
          confidence
        });
        
        this.sniperSignals.push({
          type: d.priceChange > 0 ? 'LONG' : 'SHORT',
          strength: 'SNIPER',
          symbol,
          confidence
        });
        
        return true;
      }
    }

    return false;
  }

  processSymbol(symbol, marketData) {
    const d = this.buildMarketData(symbol, marketData);
    
    if (d.trap === 'BULL_TRAP' || d.trap === 'BEAR_TRAP') {
      this.signalState.setState(symbol, STAGES.IDLE);
      return null;
    }
    
    this.processPrePumpFlow(symbol, d);
    this.processTrendFlow(symbol, d);
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
export { STAGES, signalStateMachine };
