class LiquidityTrapDetector {
  constructor() {
    this.trapHistory = new Map();
  }

  detectWickTrap(candle) {
    if (!candle || candle.high === candle.low) return null;
    
    const body = Math.abs(candle.close - candle.open);
    const upperWick = candle.high - Math.max(candle.open, candle.close);
    const lowerWick = Math.min(candle.open, candle.close) - candle.low;

    const wickRatio = Math.max(upperWick, lowerWick) / (body || 1);

    if (wickRatio > 2.5) {
      if (upperWick > lowerWick) return 'BEARISH_TRAP';
      else return 'BULLISH_TRAP';
    }

    return null;
  }

  detectBreakoutFailure(price, level, prevPrice) {
    const breakout = price > level && prevPrice <= level;

    if (!breakout) return null;

    if (price < level * 0.995) {
      return 'FAILED_BREAKOUT';
    }

    return null;
  }

  detectAbsorption(volume, priceChange) {
    if (volume > 3 && Math.abs(priceChange) < 0.5) {
      return 'ABSORPTION';
    }
    return null;
  }

  detectVolumeTrap(volume, priceChange, expectedMove) {
    const volumeEfficiency = Math.abs(priceChange) / (volume || 1);
    
    if (volume > 5 && volumeEfficiency < 0.1) {
      return 'VOLUME_TRAP';
    }
    return null;
  }

  detect(data) {
    const { priceChange, volume, oi, fakeOI, candle, symbol } = data;

    const wickTrap = this.detectWickTrap(candle);
    const absorption = this.detectAbsorption(volume, priceChange);
    const volTrap = this.detectVolumeTrap(volume, priceChange);

    const trapScore = {
      type: null,
      confidence: 0,
      reasons: []
    };

    if (priceChange > 0 && fakeOI > 0.5 && oi < 0 && (wickTrap === 'BEARISH_TRAP' || absorption)) {
      trapScore.type = 'BULL_TRAP';
      trapScore.confidence = 80;
      trapScore.reasons.push('Price up + OI down');
      trapScore.reasons.push('Wick rejection detected');
      trapScore.reasons.push('Fake OI conflicting');
    }

    if (priceChange < 0 && fakeOI < -0.5 && oi > 0 && (wickTrap === 'BULLISH_TRAP' || absorption)) {
      trapScore.type = 'BEAR_TRAP';
      trapScore.confidence = 80;
      trapScore.reasons.push('Price down + OI up');
      trapScore.reasons.push('Wick rejection detected');
      trapScore.reasons.push('Fake OI conflicting');
    }

    if (wickTrap === 'BEARISH_TRAP' && priceChange > 2 && volume > 4) {
      trapScore.type = 'BULL_TRAP';
      trapScore.confidence = 90;
      trapScore.reasons.push('Strong bearish wick on rally');
      trapScore.reasons.push('High volume + price rejection');
    }

    if (wickTrap === 'BULLISH_TRAP' && priceChange < -2 && volume > 4) {
      trapScore.type = 'BEAR_TRAP';
      trapScore.confidence = 90;
      trapScore.reasons.push('Strong bullish wick on dump');
      trapScore.reasons.push('High volume + price rejection');
    }

    if (absorption) {
      trapScore.reasons.push('Volume absorption detected');
    }

    if (volTrap) {
      trapScore.reasons.push('Volume trap: no price follow-through');
    }

    if (trapScore.type) {
      this.trapHistory.set(symbol, {
        type: trapScore.type,
        timestamp: Date.now(),
        confidence: trapScore.confidence
      });
    }

    return trapScore;
  }

  isTrapActive(symbol, windowMs = 60000) {
    const trap = this.trapHistory.get(symbol);
    if (!trap) return null;
    
    if (Date.now() - trap.timestamp > windowMs) {
      return null;
    }
    
    return trap.type;
  }

  shouldSkipSignal(symbol, priceChange) {
    const trap = this.isTrapActive(symbol);
    
    if (!trap) return { skip: false };
    
    if (trap === 'BULL_TRAP' && priceChange > 0) {
      return { skip: true, reason: 'SMART_MONEY_EXIT', type: 'BULL_TRAP' };
    }
    
    if (trap === 'BEAR_TRAP' && priceChange < 0) {
      return { skip: true, reason: 'SMART_MONEY_EXIT', type: 'BEAR_TRAP' };
    }
    
    return { skip: false };
  }

  isReversalSetup(symbol, priceChange) {
    const trap = this.isTrapActive(symbol);
    
    if (!trap) return false;
    
    if (trap === 'BEAR_TRAP' && priceChange < 0) {
      return true;
    }
    
    if (trap === 'BULL_TRAP' && priceChange > 0) {
      return true;
    }
    
    return false;
  }

  clearHistory(symbol) {
    if (symbol) {
      this.trapHistory.delete(symbol);
    }
  }

  getStats() {
    const now = Date.now();
    let bullTraps = 0;
    let bearTraps = 0;
    
    for (const [_, trap] of this.trapHistory) {
      if (now - trap.timestamp < 300000) {
        if (trap.type === 'BULL_TRAP') bullTraps++;
        if (trap.type === 'BEAR_TRAP') bearTraps++;
      }
    }
    
    return { bullTraps, bearTraps, total: bullTraps + bearTraps };
  }
}

export const liquidityTrapDetector = new LiquidityTrapDetector();
