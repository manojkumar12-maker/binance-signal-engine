import axios from 'axios';
import { config } from '../../config/config.js';

const BINANCE_API = 'https://fapi.binance.com';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

class OITracker {
  constructor() {
    this.currentOI = new Map();
    this.oiHistory = new Map();
    this.changeCache = new Map();
    this.trackedSymbols = new Set();
    this.symbols = [];
    this.validFuturesSymbols = new Set();
    this.historyWindow = 60;
    this.loaded = false;
  }

  async loadValidSymbols() {
    if (this.loaded) return;
    try {
      const res = await axios.get(`${BINANCE_API}/fapi/v1/exchangeInfo`, {
        timeout: 10000,
        headers: { 'User-Agent': 'Mozilla/5.0' }
      });
      
      res.data.symbols.forEach(s => {
        if (s.contractType === 'PERPETUAL' && s.status === 'TRADING') {
          this.validFuturesSymbols.add(s.symbol);
        }
      });
      
      this.loaded = true;
      console.log(`📊 OI Tracker: loaded ${this.validFuturesSymbols.size} valid futures symbols`);
    } catch (e) {
      console.log('⚠️ Failed to load valid symbols, using all');
      this.loaded = true;
    }
  }

  isValidSymbol(symbol) {
    return this.validFuturesSymbols.has(symbol);
  }

  setSymbols(symbols) {
    this.symbols = symbols.filter(s => this.isValidSymbol(s));
  }

  async fetch(symbol) {
    if (!symbol || !this.isValidSymbol(symbol)) return 0;

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
      if (history.length >= 10) {
        const prevOI = history[0];
        const latestOI = history[history.length - 1];
        if (prevOI > 0) {
          change = ((latestOI - prevOI) / prevOI) * 100;
        }
      }

      this.changeCache.set(symbol, change);
      
      if (symbol === 'BTCUSDT' && Math.abs(change) > 0.1) {
        console.log(`📊 OI BTC: current=${currOI.toFixed(0)} len=${history.length} change=${change.toFixed(3)}%`);
      }

      return change;
    } catch (e) {
      return this.changeCache.get(symbol) || 0;
    }
  }

  async fetchSymbols(symbols) {
    const valid = symbols.filter(s => this.isValidSymbol(s)).slice(0, 200);
    
    for (const symbol of valid) {
      await this.fetch(symbol);
      await sleep(20);
    }
    
    return this.trackedSymbols.size;
  }

  async fetchTopByVolume(marketData, count = 150) {
    const entries = Object.entries(marketData || {});
    const active = entries
      .filter(([s, d]) => d.volume > 500000 && this.isValidSymbol(s))
      .sort((a, b) => (b[1]?.volume || 0) - (a[1]?.volume || 0))
      .slice(0, count)
      .map(([s]) => s);
    
    for (const symbol of active) {
      await this.fetch(symbol);
      await sleep(20);
    }
    
    return { tracked: this.trackedSymbols.size, active };
  }

  getChange(symbol) {
    return this.changeCache.get(symbol) || 0;
  }

  getOIData(symbol) {
    if (!symbol || !this.isValidSymbol(symbol)) {
      return { current: 0, previous: 0, change: 0, trend: 'INVALID' };
    }
    
    const current = this.currentOI.get(symbol) || 0;
    const history = this.oiHistory.get(symbol) || [];
    const change = this.changeCache.get(symbol) || 0;
    
    let prev = current;
    if (history.length >= 2) {
      prev = history[0];
    }

    let trend = 'NEUTRAL';
    if (change > 0.5) trend = 'STRONG_INCREASE';
    else if (change > 0.3) trend = 'INCREASE';
    else if (change < -0.5) trend = 'STRONG_DECREASE';
    else if (change < -0.3) trend = 'DECREASE';

    return { current, previous: prev, change, trend };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let neutral = 0;

    for (const [symbol, change] of this.changeCache) {
      if (!this.isValidSymbol(symbol)) continue;
      if (change > 0.3) positive++;
      else if (change < -0.3) negative++;
      else neutral++;
    }

    return {
      tracked: this.trackedSymbols.size,
      positive,
      negative,
      neutral,
      validCount: this.validFuturesSymbols.size
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
