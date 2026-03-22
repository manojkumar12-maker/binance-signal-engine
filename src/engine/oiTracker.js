import axios from 'axios';
import { config } from '../../config/config.js';

export class OITracker {
  constructor() {
    this.prevOI = new Map();
    this.currentOI = new Map();
    this.changeCache = new Map();
    this.lastFetch = new Map();
    this.fetchInterval = 20000;
  }

  async fetch(symbol) {
    const now = Date.now();
    const lastFetch = this.lastFetch.get(symbol) || 0;
    
    if (now - lastFetch < this.fetchInterval) {
      return this.changeCache.get(symbol) || 0;
    }

    try {
      const res = await axios.get(
        `${config.binance.apiUrl}/futures/data/openInterestHist`,
        {
          params: {
            symbol,
            period: '5m',
            limit: 2
          },
          timeout: 5000
        }
      );

      if (!res.data || res.data.length < 2) {
        return this.changeCache.get(symbol) || 0;
      }

      const prevOIValue = parseFloat(res.data[0].sumOpenInterest);
      const currOIValue = parseFloat(res.data[1].sumOpenInterest);

      if (isNaN(prevOIValue) || isNaN(currOIValue) || prevOIValue === 0) {
        return this.changeCache.get(symbol) || 0;
      }

      this.currentOI.set(symbol, currOIValue);
      
      const prevStored = this.prevOI.get(symbol) || prevOIValue;
      const change = ((currOIValue - prevStored) / prevStored) * 100;

      this.prevOI.set(symbol, currOIValue);

      this.changeCache.set(symbol, change);
      this.lastFetch.set(symbol, now);

      return change;
    } catch (e) {
      return this.changeCache.get(symbol) || 0;
    }
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
    return this.currentOI.get(symbol) || 0;
  }

  getOIData(symbol) {
    const current = this.currentOI.get(symbol) || 0;
    const prev = this.prevOI.get(symbol) || current;
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
    this.prevOI.clear();
    this.currentOI.clear();
    this.changeCache.clear();
    this.lastFetch.clear();
  }
}

export const oiTracker = new OITracker();
