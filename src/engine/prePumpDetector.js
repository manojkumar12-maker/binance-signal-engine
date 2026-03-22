export class PrePumpDetector {
  constructor() {
    this.history = new Map();
    this.symbolStates = new Map();
  }

  analyze(symbol, data) {
    const {
      priceChange,
      volumeSpike,
      orderflow,
      oiChange,
      fundingRate,
      imbalance,
      momentum
    } = data;

    let score = 0;
    const reasons = [];

    if (oiChange > 3 && Math.abs(priceChange) < 1) {
      score += 2;
      reasons.push('OI buildup');
    }

    if (orderflow > 1.2 && Math.abs(priceChange) < 1) {
      score += 2;
      reasons.push('Stealth accumulation');
    }

    if (fundingRate < -0.01) {
      score += 1;
      reasons.push('Short squeeze setup');
    }

    if (volumeSpike > 1.5) {
      score += 1;
      reasons.push('Volume rising');
    }

    if (imbalance > 1.3) {
      score += 1;
      reasons.push('Bid dominance');
    }

    if (momentum > 0.05 && Math.abs(priceChange) < 2) {
      score += 1;
      reasons.push('Momentum building');
    }

    const isPrePump = score >= 4;
    const isBuilding = score >= 3;

    this.symbolStates.set(symbol, {
      isPrePump,
      isBuilding,
      score,
      reasons,
      timestamp: Date.now()
    });

    return {
      isPrePump,
      isBuilding,
      prePumpScore: score,
      reasons,
      direction: this.detectDirection(data)
    };
  }

  detectDirection(data) {
    const { orderflow, oiChange, priceChange, momentum } = data;
    
    if (orderflow > 1.3 && oiChange > 2 && (priceChange > 0 || momentum > 0)) {
      return 'LONG';
    }
    
    if (orderflow < 0.7 && oiChange < -2 && (priceChange < 0 || momentum < 0)) {
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
