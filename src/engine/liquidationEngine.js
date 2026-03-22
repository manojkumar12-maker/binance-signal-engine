export class LiquidationEngine {
  constructor() {
    this.levels = new Map();
    this.lastFetch = new Map();
    this.fetchInterval = 300000;
  }

  setLevels(symbol, levels) {
    if (!levels || !Array.isArray(levels)) return;
    this.levels.set(symbol, levels);
    this.lastFetch.set(symbol, Date.now());
  }

  analyze(symbol, currentPrice) {
    const levels = this.levels.get(symbol);
    
    if (!levels || levels.length === 0) {
      return { signal: false, direction: null, target: null, distance: 0 };
    }

    const above = levels.filter(l => l.price > currentPrice);
    const below = levels.filter(l => l.price < currentPrice);

    above.sort((a, b) => a.price - b.price);
    below.sort((a, b) => b.price - a.price);

    const nearestAbove = above[0];
    const nearestBelow = below[0];

    if (nearestAbove) {
      const distance = ((nearestAbove.price - currentPrice) / currentPrice) * 100;
      
      if (distance < 2) {
        return {
          signal: true,
          direction: 'UP',
          target: nearestAbove.price,
          distance: distance.toFixed(2),
          volume: nearestAbove.volume || 0
        };
      }
    }

    if (nearestBelow) {
      const distance = ((currentPrice - nearestBelow.price) / currentPrice) * 100;
      
      if (distance < 2) {
        return {
          signal: true,
          direction: 'DOWN',
          target: nearestBelow.price,
          distance: distance.toFixed(2),
          volume: nearestBelow.volume || 0
        };
      }
    }

    return { signal: false, direction: null, target: null, distance: 0 };
  }

  getTargets(symbol, currentPrice, limit = 5) {
    const levels = this.levels.get(symbol);
    
    if (!levels || levels.length === 0) return [];

    return levels
      .filter(l => l.price > currentPrice)
      .sort((a, b) => a.price - b.price)
      .slice(0, limit)
      .map(l => ({
        price: l.price,
        distance: ((l.price - currentPrice) / currentPrice * 100).toFixed(2),
        volume: l.volume || 0
      }));
  }

  getSqueezeZones(symbol, currentPrice) {
    const levels = this.levels.get(symbol);
    
    if (!levels || levels.length === 0) return [];

    return levels
      .filter(l => Math.abs((l.price - currentPrice) / currentPrice) < 0.05)
      .map(l => ({
        price: l.price,
        direction: l.price > currentPrice ? 'LONG_LIQ' : 'SHORT_LIQ',
        distance: (Math.abs(l.price - currentPrice) / currentPrice * 100).toFixed(2),
        volume: l.volume || 0
      }));
  }

  addMockLevels(symbol) {
    const mockLevels = [
      { price: 0, volume: 0 }
    ];
    this.levels.set(symbol, mockLevels);
  }

  getStats() {
    return {
      trackedSymbols: this.levels.size,
      lastFetch: Object.fromEntries(this.lastFetch)
    };
  }
}

export const liquidationEngine = new LiquidationEngine();
