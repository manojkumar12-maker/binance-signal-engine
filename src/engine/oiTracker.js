import axios from 'axios';
import { config } from '../../config/config.js';

export class OITracker {
  constructor() {
    this.prev = new Map();
    this.current = new Map();
    this.changeCache = new Map();
    this.lastFetch = new Map();
    this.fetchInterval = 15000;
  }

  async fetch(symbol) {
    const now = Date.now();
    const lastFetch = this.lastFetch.get(symbol) || 0;
    
    if (now - lastFetch < this.fetchInterval) {
      return this.changeCache.get(symbol) || 0;
    }

    try {
      const res = await axios.get(
        `${config.binance.apiUrl}/fapi/v1/openInterest`,
        {
          params: { symbol },
          timeout: 5000
        }
      );

      const oi = parseFloat(res.data.openInterest);

      if (isNaN(oi) || oi === 0) {
        return this.changeCache.get(symbol) || 0;
      }

      this.current.set(symbol, oi);

      const change = this.calculateChange(symbol);

      this.changeCache.set(symbol, change);
      this.lastFetch.set(symbol, now);

      return change;
    } catch (e) {
      return this.changeCache.get(symbol) || 0;
    }
  }

  calculateChange(symbol) {
    const prev = this.prev.get(symbol);
    const curr = this.current.get(symbol);

    if (!prev || !curr) {
      if (curr) {
        this.prev.set(symbol, curr);
      }
      return 0;
    }

    if (prev === 0) return 0;

    const change = ((curr - prev) / prev) * 100;

    this.prev.set(symbol, curr);

    return change;
  }

  async fetchBatch(symbols) {
    const results = [];
    for (const symbol of symbols) {
      const change = await this.fetch(symbol);
      results.push({ symbol, change });
    }
    return results;
  }

  getChange(symbol) {
    return this.changeCache.get(symbol) || 0;
  }

  getCurrent(symbol) {
    return this.current.get(symbol) || 0;
  }

  getOIData(symbol) {
    const current = this.current.get(symbol) || 0;
    const prev = this.prev.get(symbol) || current;
    const change = this.changeCache.get(symbol) || 0;

    let trend = 'NEUTRAL';
    if (change > 3) trend = 'STRONG_INCREASE';
    else if (change > 1) trend = 'INCREASE';
    else if (change < -3) trend = 'STRONG_DECREASE';
    else if (change < -1) trend = 'DECREASE';

    return {
      current,
      previous: prev,
      change,
      trend
    };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let neutral = 0;

    for (const change of this.changeCache.values()) {
      if (change > 1) positive++;
      else if (change < -1) negative++;
      else neutral++;
    }

    return {
      tracked: this.changeCache.size,
      positive,
      negative,
      neutral
    };
  }

  reset() {
    this.prev.clear();
    this.current.clear();
    this.changeCache.clear();
    this.lastFetch.clear();
  }
}

export const oiTracker = new OITracker();
