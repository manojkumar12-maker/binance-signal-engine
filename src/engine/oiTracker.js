import axios from 'axios';
import { config } from '../../config/config.js';

export class OITracker {
  constructor() {
    this.prevOI = new Map();
    this.currentOI = new Map();
    this.changeCache = new Map();
    this.changeHistory = new Map();
    this.lastFetch = new Map();
    this.fetchInterval = 2000;
    this.trackedSymbols = new Set();
  }

  async fetch(symbol) {
    if (!symbol) return 0;
    const now = Date.now();
    const lastFetch = this.lastFetch.get(symbol) || 0;
    
    if (now - lastFetch < this.fetchInterval) {
      return this.getChange(symbol);
    }

    try {
      const res = await axios.get(
        `${config.binance.apiUrl}/fapi/v1/openInterest`,
        {
          params: { symbol },
          timeout: 5000
        }
      );

      if (!res.data || res.data.openInterest === undefined) {
        return this.getChange(symbol);
      }

      const currOIValue = parseFloat(res.data.openInterest);

      if (isNaN(currOIValue) || currOIValue === 0) {
        return this.getChange(symbol);
      }

      this.trackedSymbols.add(symbol);
      this.currentOI.set(symbol, currOIValue);
      
      const prevStored = this.prevOI.get(symbol);
      let change = 0;
      
      if (prevStored && prevStored > 0 && currOIValue > 0) {
        change = ((currOIValue - prevStored) / prevStored) * 100;
      } else {
        change = 0;
      }
      
      this.changeCache.set(symbol, change);
      this.prevOI.set(symbol, currOIValue);
      this.lastFetch.set(symbol, now);
      this.addToHistory(symbol, change);

      return change;
    } catch (e) {
      return this.getChange(symbol);
    }
  }

  addToHistory(symbol, change) {
    if (!this.changeHistory.has(symbol)) {
      this.changeHistory.set(symbol, []);
    }
    const history = this.changeHistory.get(symbol);
    history.push(change);
    if (history.length > 20) history.shift();
  }

  getAverageChange(symbol) {
    const history = this.changeHistory.get(symbol);
    if (!history || history.length === 0) return 0;
    return history.reduce((a, b) => a + b, 0) / history.length;
  }

  async fetchBatch(symbols) {
    for (const symbol of symbols) {
      await this.fetch(symbol);
    }
  }

  getChange(symbol) {
    if (!symbol) return 0;
    return this.changeCache.get(symbol) || 0;
  }

  getCurrent(symbol) {
    if (!symbol) return 0;
    return this.currentOI.get(symbol) || 0;
  }

  getOIData(symbol) {
    if (!symbol) return { current: 0, previous: 0, change: 0, avgChange: 0, trend: 'NEUTRAL' };
    const current = this.currentOI.get(symbol) || 0;
    const prev = this.prevOI.get(symbol) || current;
    const change = this.changeCache.get(symbol) || 0;
    const avgChange = this.getAverageChange(symbol);

    let trend = 'NEUTRAL';
    if (avgChange > 2) trend = 'STRONG_INCREASE';
    else if (avgChange > 0.5) trend = 'INCREASE';
    else if (avgChange < -2) trend = 'STRONG_DECREASE';
    else if (avgChange < -0.5) trend = 'DECREASE';

    return { current, previous: prev, change, avgChange, trend };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let neutral = 0;

    for (const symbol of this.trackedSymbols) {
      const avg = this.getAverageChange(symbol);
      if (avg > 0.5) positive++;
      else if (avg < -0.5) negative++;
      else neutral++;
    }

    return {
      tracked: this.trackedSymbols.size,
      positive,
      negative,
      neutral
    };
  }

  reset() {
    this.prevOI.clear();
    this.currentOI.clear();
    this.changeCache.clear();
    this.changeHistory.clear();
    this.lastFetch.clear();
    this.trackedSymbols.clear();
  }
}

export const oiTracker = new OITracker();
