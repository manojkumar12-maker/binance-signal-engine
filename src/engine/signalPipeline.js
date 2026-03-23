class SignalPipeline {
  constructor() {
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
      momentum: data.momentum || 0
    };
  }

  detectEarly(d) {
    if (
      Math.abs(d.priceChange) > 2 &&
      d.volume > 2 &&
      d.orderFlow > 1.2
    ) {
      return {
        type: d.priceChange > 0 ? 'LONG' : 'SHORT',
        strength: 'EARLY',
        symbol: d.symbol
      };
    }
    return null;
  }

  detectConfirmed(d) {
    if (
      Math.abs(d.priceChange) > 3 &&
      d.volume > 3 &&
      d.orderFlow > 1.5 &&
      Math.abs(d.oiChange) > 0.3
    ) {
      return {
        type: d.priceChange > 0 ? 'LONG' : 'SHORT',
        strength: 'CONFIRMED',
        symbol: d.symbol
      };
    }
    return null;
  }

  detectSniper(d) {
    const direction = d.priceChange > 0 ? 'LONG' : 'SHORT';

    const oiValid =
      (direction === 'LONG' && d.oiChange > 0.5) ||
      (direction === 'SHORT' && d.oiChange < -0.5) ||
      (direction === 'LONG' && d.fakeOI > 0.5) ||
      (direction === 'SHORT' && d.fakeOI < -0.5);

    const trapValid = !d.trap || d.trap === 'BEAR_TRAP' || d.trap === 'BULL_TRAP';

    if (
      Math.abs(d.priceChange) > 4 &&
      d.volume > 4 &&
      d.orderFlow > 1.8 &&
      oiValid &&
      trapValid
    ) {
      let confidence = 70;
      if (Math.abs(d.oiChange) > 1) confidence += 10;
      if (d.volume > 5) confidence += 5;
      if (Math.abs(d.fakeOI) > 0.5) confidence += 5;
      confidence = Math.min(confidence, 95);

      return {
        type: direction,
        strength: 'SNIPER',
        confidence,
        symbol: d.symbol
      };
    }
    return null;
  }

  detectPrePump(d) {
    if (
      d.volume > 2 &&
      Math.abs(d.priceChange) < 2 &&
      (d.oiChange > 0.3 || d.fakeOI > 0.3) &&
      d.orderFlow > 1.2
    ) {
      return {
        type: d.priceChange > 0 ? 'LONG' : 'SHORT',
        strength: 'PRE_PUMP',
        symbol: d.symbol
      };
    }
    return null;
  }

  detectPumpConfirmed(d) {
    if (
      d.volume > 4 &&
      d.orderFlow > 2 &&
      (d.oiChange > 0.5 || d.fakeOI > 0.5) &&
      d.priceAcceleration > 0.3
    ) {
      return {
        type: d.priceChange > 0 ? 'LONG' : 'SHORT',
        strength: 'PUMP_CONFIRMED',
        symbol: d.symbol
      };
    }
    return null;
  }

  processSymbol(symbol, marketData) {
    const d = this.buildMarketData(symbol, marketData);

    const prePump = this.detectPrePump(d);
    if (prePump) {
      this.prePumpPanel.push(prePump);
    }

    const pumpConfirmed = this.detectPumpConfirmed(d);
    if (pumpConfirmed) {
      this.pumpConfirmedPanel.push(pumpConfirmed);
    }

    const early = this.detectEarly(d);
    if (early) {
      this.earlySignals.push(early);
    }

    const confirmed = this.detectConfirmed(d);
    if (confirmed) {
      this.confirmedSignals.push(confirmed);
    }

    const sniper = this.detectSniper(d);
    if (sniper) {
      this.sniperSignals.push(sniper);
    }
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

  reset() {
    this.prePumpPanel = [];
    this.pumpConfirmedPanel = [];
    this.earlySignals = [];
    this.confirmedSignals = [];
    this.sniperSignals = [];
  }
}

export const signalPipeline = new SignalPipeline();
