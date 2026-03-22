import axios from 'axios';

export class LiquidationService {
  constructor() {
    this.cache = new Map();
    this.lastFetch = new Map();
    this.fetchInterval = 60000;
    this.apiKey = process.env.COINGLASS_API_KEY;
  }

  async fetch(symbol) {
    const now = Date.now();
    const lastFetch = this.lastFetch.get(symbol) || 0;
    
    if (now - lastFetch < this.fetchInterval) {
      return this.cache.get(symbol) || null;
    }

    if (!this.apiKey) {
      return this.getMockData(symbol);
    }

    try {
      const res = await axios.get(
        `https://api.coinglass.com/api/pro/futures/liquidation_chart?symbol=${symbol}`,
        {
          headers: {
            'coinglassSecret': this.apiKey
          },
          timeout: 5000
        }
      );

      if (res.data && res.data.data) {
        this.cache.set(symbol, res.data.data);
        this.lastFetch.set(symbol, now);
        return res.data.data;
      }
    } catch (err) {
      console.log(`Liq API unavailable for ${symbol}, using cache/mock`);
    }

    return this.cache.get(symbol) || this.getMockData(symbol);
  }

  getMockData(symbol) {
    if (this.cache.has(symbol)) {
      return this.cache.get(symbol);
    }
    return null;
  }

  async analyze(symbol, currentPrice) {
    const data = await this.fetch(symbol);
    
    if (!data || !Array.isArray(data)) {
      return { signal: false, direction: null, target: null, clusters: [] };
    }

    const clustersAbove = data.filter(l => l.price > currentPrice);
    const clustersBelow = data.filter(l => l.price < currentPrice);

    clustersAbove.sort((a, b) => a.price - b.price);
    clustersBelow.sort((a, b) => b.price - a.price);

    const nearestAbove = clustersAbove[0];
    const nearestBelow = clustersBelow[0];

    let signal = false;
    let direction = null;
    let target = null;
    let distancePercent = 0;

    if (nearestAbove) {
      distancePercent = ((nearestAbove.price - currentPrice) / currentPrice) * 100;
      if (distancePercent < 2) {
        signal = true;
        direction = 'UP';
        target = nearestAbove.price;
      }
    }

    if (nearestBelow) {
      distancePercent = ((currentPrice - nearestBelow.price) / currentPrice) * 100;
      if (distancePercent < 2) {
        signal = true;
        direction = 'DOWN';
        target = nearestBelow.price;
      }
    }

    return {
      signal,
      direction,
      target,
      distancePercent: distancePercent.toFixed(2),
      shortClusterSize: nearestBelow?.totalVolume || 0,
      longClusterSize: nearestAbove?.totalVolume || 0,
      clusters: {
        above: clustersAbove.slice(0, 3),
        below: clustersBelow.slice(0, 3)
      }
    };
  }

  async getTopTargets(symbol, currentPrice, limit = 5) {
    const data = await this.fetch(symbol);
    
    if (!data || !Array.isArray(data)) {
      return [];
    }

    const above = data
      .filter(l => l.price > currentPrice)
      .sort((a, b) => a.price - b.price)
      .slice(0, limit);

    return above.map(l => ({
      price: l.price,
      distance: ((l.price - currentPrice) / currentPrice * 100).toFixed(2),
      volume: l.totalVolume || 0
    }));
  }

  async getShortSqueezeZones(symbol, currentPrice) {
    const data = await this.fetch(symbol);
    
    if (!data || !Array.isArray(data)) {
      return [];
    }

    return data
      .filter(l => Math.abs((l.price - currentPrice) / currentPrice) < 0.05)
      .map(l => ({
        price: l.price,
        direction: l.price > currentPrice ? 'LONG_LIQ' : 'SHORT_LIQ',
        volume: l.totalVolume || 0,
        distance: (Math.abs(l.price - currentPrice) / currentPrice * 100).toFixed(2)
      }));
  }
}

export const liquidationService = new LiquidationService();
