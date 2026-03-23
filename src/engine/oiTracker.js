import axios from 'axios';
import { config } from '../../config/config.js';

export class OITracker {
  constructor() {
    this.prevOI = new Map();
    this.currentOI = new Map();
    this.changeCache = new Map();
    this.changeHistory = new Map();
    this.lastUpdate = new Map();
    this.updateWindowMs = 10000;
    this.trackedSymbols = new Set();
    this.updateIndex = 0;
    this.allSymbols = [];
  }

  setSymbols(symbols) {
    this.allSymbols = symbols;
    this.updateIndex = 0;
  }

  async fetch(symbol) {
    if (!symbol) return 0;

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
      const lastTime = this.lastUpdate.get(symbol) || 0;
      const now = Date.now();
      
      let change = 0;
      
      if (!prevStored) {
        this.prevOI.set(symbol, currOIValue);
        this.lastUpdate.set(symbol, now);
        change = 0;
      } else if (now - lastTime >= this.updateWindowMs) {
        change = ((currOIValue - prevStored) / prevStored) * 100;
        this.prevOI.set(symbol, currOIValue);
        this.lastUpdate.set(symbol, now);
      } else {
        change = this.changeCache.get(symbol) || 0;
      }
      
      this.changeCache.set(symbol, change);
      this.addToHistory(symbol, change);

      if (symbol === 'BTCUSDT' && Math.abs(change) > 0.1) {
        console.log(`📊 OI DEBUG BTC: curr=${currOIValue} prev=${prevStored} change=${change.toFixed(3)}%`);
      }

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
    if (history.length > 30) history.shift();
  }

  getAverageChange(symbol) {
    const history = this.changeHistory.get(symbol);
    if (!history || history.length === 0) return 0;
    
    const recent = history.slice(-10);
    const sum = recent.reduce((a, b) => a + b, 0);
    return sum / recent.length;
  }

  async fetchBatch(symbols) {
    const batchSize = 20;
    const batches = [];
    
    for (let i = 0; i < symbols.length; i += batchSize) {
      batches.push(symbols.slice(i, i + batchSize));
    }
    
    for (const batch of batches) {
      await Promise.all(batch.map(s => this.fetch(s)));
    }
  }

  getNextBatch() {
    if (!this.allSymbols || this.allSymbols.length === 0) return [];
    
    const batchSize = 50;
    const start = this.updateIndex;
    const end = Math.min(start + batchSize, this.allSymbols.length);
    const batch = this.allSymbols.slice(start, end);
    
    this.updateIndex = end >= this.allSymbols.length ? 0 : end;
    
    return batch;
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
    else if (avgChange > 0.3) trend = 'INCREASE';
    else if (avgChange < -2) trend = 'STRONG_DECREASE';
    else if (avgChange < -0.3) trend = 'DECREASE';

    return { current, previous: prev, change, avgChange, trend };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let neutral = 0;

    for (const symbol of this.trackedSymbols) {
      const avg = this.getAverageChange(symbol);
      if (avg > 0.3) positive++;
      else if (avg < -0.3) negative++;
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
    this.lastUpdate.clear();
    this.trackedSymbols.clear();
    this.updateIndex = 0;
  }
}

export const oiTracker = new OITracker();
