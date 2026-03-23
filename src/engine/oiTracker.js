import axios from 'axios';

const BINANCE_API = 'https://fapi.binance.com';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

class OITracker {
  constructor() {
    this.currentOI = new Map();
    this.prevOI = new Map();
    this.changeHistory = new Map();
    this.changeCache = new Map();
    this.trackedSymbols = new Set();
    this.updateTimestamps = new Map();
    this.updateInterval = 15000;
    this.batchSize = 10;
    this.symbols = [];
    this.batchIndex = 0;
  }

  setSymbols(symbols) {
    this.symbols = symbols;
    this.batchIndex = 0;
  }

  async fetch(symbol) {
    if (!symbol) return 0;

    try {
      const res = await axios.get(
        `${BINANCE_API}/fapi/v1/openInterest`,
        {
          params: { symbol },
          timeout: 5000,
          headers: { 'User-Agent': 'Mozilla/5.0' }
        }
      );

      if (!res.data || res.data.openInterest === undefined) return 0;

      const currOI = parseFloat(res.data.openInterest);
      if (isNaN(currOI) || currOI === 0) return 0;

      this.trackedSymbols.add(symbol);
      this.currentOI.set(symbol, currOI);

      const prev = this.prevOI.get(symbol);
      const lastUpdate = this.updateTimestamps.get(symbol) || 0;
      const now = Date.now();

      let change = 0;

      if (prev === undefined) {
        this.prevOI.set(symbol, currOI);
        this.updateTimestamps.set(symbol, now);
        change = 0;
      } else if (now - lastUpdate >= this.updateInterval) {
        change = ((currOI - prev) / prev) * 100;
        this.prevOI.set(symbol, currOI);
        this.updateTimestamps.set(symbol, now);
      } else {
        change = this.changeCache.get(symbol) || 0;
      }

      this.changeCache.set(symbol, change);
      this.addToHistory(symbol, change);

      return change;
    } catch (e) {
      return this.changeCache.get(symbol) || 0;
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
    if (!history || history.length < 2) return 0;
    const recent = history.slice(-5);
    return recent.reduce((a, b) => a + b, 0) / recent.length;
  }

  async fetchTopSymbols(count = 50) {
    const topSymbols = this.symbols.slice(0, count);
    let updated = 0;

    for (const symbol of topSymbols) {
      const change = await this.fetch(symbol);
      if (change !== 0) updated++;
      await sleep(30);
    }

    return updated;
  }

  getChange(symbol) {
    return this.changeCache.get(symbol) || 0;
  }

  getOIData(symbol) {
    const current = this.currentOI.get(symbol) || 0;
    const prev = this.prevOI.get(symbol) || current;
    const change = this.changeCache.get(symbol) || 0;
    const avgChange = this.getAverageChange(symbol);

    let trend = 'NEUTRAL';
    if (avgChange > 0.5) trend = 'INCREASE';
    else if (avgChange > 2) trend = 'STRONG_INCREASE';
    else if (avgChange < -0.5) trend = 'DECREASE';
    else if (avgChange < -2) trend = 'STRONG_DECREASE';

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
    this.currentOI.clear();
    this.prevOI.clear();
    this.changeHistory.clear();
    this.changeCache.clear();
    this.trackedSymbols.clear();
    this.updateTimestamps.clear();
  }
}

export const oiTracker = new OITracker();
