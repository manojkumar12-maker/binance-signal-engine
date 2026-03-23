import axios from 'axios';

const BINANCE_API = 'https://fapi.binance.com';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

class OITracker {
  constructor() {
    this.currentOI = new Map();
    this.oiHistory = new Map();
    this.changeCache = new Map();
    this.trackedSymbols = new Set();
    this.symbols = [];
    this.updateInterval = 30000;
    this.historyWindow = 60;
    this.batchSize = 15;
  }

  setSymbols(symbols) {
    this.symbols = symbols;
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

      if (!this.oiHistory.has(symbol)) {
        this.oiHistory.set(symbol, []);
      }
      const history = this.oiHistory.get(symbol);
      history.push(currOI);
      if (history.length > this.historyWindow) {
        history.shift();
      }

      let change = 0;
      if (history.length >= 2) {
        const prevOI = history[0];
        const latestOI = history[history.length - 1];
        if (prevOI > 0) {
          change = ((latestOI - prevOI) / prevOI) * 100;
        }
      }

      this.changeCache.set(symbol, change);
      
      if (symbol === 'BTCUSDT' && Math.abs(change) > 0.01) {
        console.log(`📊 OI BTC: current=${currOI} history_len=${history.length} change=${change.toFixed(3)}%`);
      }

      return change;
    } catch (e) {
      return this.changeCache.get(symbol) || 0;
    }
  }

  async fetchTopSymbols(count = 150) {
    const topSymbols = this.symbols.slice(0, count);
    
    for (const symbol of topSymbols) {
      await this.fetch(symbol);
      await sleep(20);
    }
    
    return this.trackedSymbols.size;
  }

  async fetchActiveSymbols(activeSymbols) {
    const toFetch = activeSymbols.slice(0, 200);
    
    for (const symbol of toFetch) {
      await this.fetch(symbol);
      await sleep(20);
    }
    
    return this.trackedSymbols.size;
  }

  getChange(symbol) {
    return this.changeCache.get(symbol) || 0;
  }

  getOIData(symbol) {
    const current = this.currentOI.get(symbol) || 0;
    const history = this.oiHistory.get(symbol) || [];
    const change = this.changeCache.get(symbol) || 0;
    
    let prev = current;
    if (history.length >= 2) {
      prev = history[0];
    }

    let trend = 'NEUTRAL';
    if (change > 0.3) trend = 'INCREASE';
    else if (change > 1) trend = 'STRONG_INCREASE';
    else if (change < -0.3) trend = 'DECREASE';
    else if (change < -1) trend = 'STRONG_DECREASE';

    return { current, previous: prev, change, trend };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let neutral = 0;

    for (const [symbol, change] of this.changeCache) {
      if (change > 0.3) positive++;
      else if (change < -0.3) negative++;
      else neutral++;
    }

    return {
      tracked: this.trackedSymbols.size,
      positive,
      negative,
      neutral,
      totalTracked: this.symbols.length
    };
  }

  reset() {
    this.currentOI.clear();
    this.oiHistory.clear();
    this.changeCache.clear();
    this.trackedSymbols.clear();
  }
}

export const oiTracker = new OITracker();
