import { getSmartOI } from './signalPipeline.js';

export class PrePumpDetector {
  constructor() {
    this.history = new Map();
    this.symbolStates = new Map();
  }

  analyze(symbol, data, state = null) {
    const {
      priceChange,
      volumeSpike,
      orderflow,
      oiChange,
      fundingRate,
      imbalance,
      momentum,
      fakeOI
    } = data;

    const smartOI = getSmartOI(oiChange || 0);

    let score = 0;
    const reasons = [];

    if (smartOI > 0.1 && Math.abs(priceChange) < 3) {
      score += 2;
      reasons.push('Smart OI buildup');
    }

    if (fakeOI !== undefined && fakeOI !== null && Math.abs(fakeOI) > 0.3 && Math.abs(priceChange) < 3) {
      score += 2;
      reasons.push(fakeOI > 0 ? 'Flow accumulation (buy)' : 'Flow accumulation (sell)');
    }

    if (orderflow > 1.3 && Math.abs(priceChange) < 3) {
      score += 2;
      reasons.push('Stealth accumulation');
    }

    if (fundingRate < -0.005) {
      score += 1;
      reasons.push('Short squeeze setup');
    }

    if (volumeSpike > 2.5) {
      score += 1;
      reasons.push('Volume rising');
    }

    if (imbalance > 1.3) {
      score += 1;
      reasons.push('Bid dominance');
    }

    if (momentum > 0.05 && Math.abs(priceChange) < 4) {
      score += 1;
      reasons.push('Momentum building');
    }

    if (state?.persistence >= 3) {
      score += 2;
      reasons.push('Persistence confirmed');
    }

    const isPrePump = score >= 5;
    const isBuilding = score >= 3;

    this.symbolStates.set(symbol, {
      isPrePump,
      isBuilding,
      score,
      reasons,
      timestamp: Date.now(),
      persistence: state?.persistence || 0
    });

    return {
      isPrePump,
      isBuilding,
      prePumpScore: score,
      reasons,
      direction: this.detectDirection(data),
      persistence: state?.persistence || 0
    };
  }

  detectDirection(data) {
    const { orderflow, oiChange, priceChange, momentum } = data;
    const smartOI = getSmartOI(oiChange || 0);

    if (orderflow > 1.5 && smartOI > 0.1 && (priceChange > 0 || momentum > 0)) {
      return 'LONG';
    }

    if (orderflow < 0.7 && smartOI < -0.1 && (priceChange < 0 || momentum < 0)) {
      return 'SHORT';
    }

    return 'NEUTRAL';
  }

  getPrePumpSignals() {
    const signals = [];
    const now = Date.now();

    for (const [symbol, state] of this.symbolStates.entries()) {
      if ((state.isPrePump || state.isBuilding) && now - state.timestamp < 300000) {
        signals.push({
          symbol,
          ...state
        });
      }
    }

    return signals.sort((a, b) => b.score - a.score);
  }

  getState(symbol) {
    return this.symbolStates.get(symbol);
  }

  clear() {
    this.symbolStates.clear();
  }
}

export const prePumpDetector = new PrePumpDetector();