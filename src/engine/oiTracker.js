import axios from 'axios';
import { config } from '../../config/config.js';

const BINANCE_API = 'https://fapi.binance.com';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const MAX_PER_SECOND = 15;
const TTL_MS = 15000;
const HISTORY_WINDOW = 60;
const MAX_TRACKED = 120;

class OICache {
  constructor() {
    this.data = new Map();
    this.validFuturesSymbols = new Set();
    this.loaded = false;
    this.prioritySymbols = new Set();
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
      console.log(`📊 OI Cache: loaded ${this.validFuturesSymbols.size} valid futures symbols`);
    } catch (e) {
      console.log('⚠️ Failed to load valid symbols');
      this.loaded = true;
    }
  }

  isValid(symbol) {
    return this.validFuturesSymbols.has(symbol);
  }

  markPriority(symbol) {
    this.prioritySymbols.add(symbol);
  }

  clearPriority(symbol) {
    this.prioritySymbols.delete(symbol);
  }

  update(symbol, oi) {
    if (!this.data.has(symbol)) {
      this.data.set(symbol, {
        history: [],
        lastUpdate: 0,
        lastRequest: 0
      });
    }

    const entry = this.data.get(symbol);
    entry.history.push(oi);
    if (entry.history.length > HISTORY_WINDOW) entry.history.shift();
    entry.value = oi;
    entry.lastUpdate = Date.now();
  }

  shouldFetch(symbol) {
    const d = this.data.get(symbol);
    const now = Date.now();
    
    if (!d) return true;
    if (now - d.lastUpdate > TTL_MS) return true;
    
    return false;
  }

  get(symbol) {
    return this.data.get(symbol);
  }

  getChange(symbol) {
    const d = this.data.get(symbol);
    if (!d || d.history.length < 10) return 0;

    const first = d.history[0];
    const last = d.history[d.history.length - 1];
    if (first <= 0) return 0;

    return ((last - first) / first) * 100;
  }

  getOIData(symbol) {
    const d = this.data.get(symbol);
    const current = d?.value || 0;
    const change = this.getChange(symbol);
    
    let trend = 'NEUTRAL';
    if (change > 1) trend = 'STRONG_INCREASE';
    else if (change > 0.5) trend = 'INCREASE';
    else if (change < -1) trend = 'STRONG_DECREASE';
    else if (change < -0.5) trend = 'DECREASE';

    return { current, change, trend };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let neutral = 0;

    for (const [symbol] of this.data) {
      if (!this.isValid(symbol)) continue;
      const change = this.getChange(symbol);
      if (change > 0.3) positive++;
      else if (change < -0.3) negative++;
      else neutral++;
    }

    return {
      tracked: this.data.size,
      positive,
      negative,
      neutral,
      validCount: this.validFuturesSymbols.size
    };
  }
}

class OITracker {
  constructor() {
    this.cache = new OICache();
    this.allSymbols = [];
    this.activeSymbols = [];
    this.marketData = {};
    this.fetchQueue = [];
    this.isProcessing = false;
    this.lastProcessedCount = 0;
  }

  async initialize(symbols) {
    await this.cache.loadValidSymbols();
    this.allSymbols = symbols.filter(s => this.cache.isValid(s));
    console.log(`📊 OIT: initialized with ${this.allSymbols.length} valid symbols`);
  }

  updateMarketData(marketData) {
    this.marketData = marketData || {};
    
    const sorted = Object.entries(this.marketData)
      .filter(([s, d]) => d.volume > 2000000 && this.cache.isValid(s))
      .sort((a, b) => (b[1]?.volume || 0) - (a[1]?.volume || 0))
      .slice(0, MAX_TRACKED)
      .map(([s]) => s);
    
    this.activeSymbols = sorted;
  }

  markPriority(symbol) {
    this.cache.markPriority(symbol);
  }

  async fetch(symbol) {
    if (!symbol || !this.cache.isValid(symbol)) return 0;

    const d = this.cache.get(symbol);
    const now = Date.now();
    
    if (d && now - d.lastUpdate < TTL_MS) {
      return this.cache.getChange(symbol);
    }

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

      const oi = parseFloat(res.data.openInterest);
      if (isNaN(oi) || oi === 0) return 0;

      this.cache.update(symbol, oi);

      if (symbol === 'BTCUSDT') {
        const change = this.cache.getChange(symbol);
        if (Math.abs(change) > 0.05) {
          console.log(`📊 OI BTC: current=${oi.toFixed(0)} len=${d.history.length} change=${change.toFixed(3)}%`);
        }
      }

      return this.cache.getChange(symbol);
    } catch (e) {
      return this.cache.getChange(symbol);
    }
  }

  async processQueue() {
    if (this.isProcessing) return;
    this.isProcessing = true;

    const priority = [...this.cache.prioritySymbols].filter(s => this.cache.shouldFetch(s));
    const rest = this.activeSymbols.filter(s => !this.cache.prioritySymbols.has(s) && this.cache.shouldFetch(s));
    const queue = [...priority, ...rest].slice(0, 50);

    if (queue.length === 0) {
      this.isProcessing = false;
      return;
    }

    const batches = [];
    for (let i = 0; i < queue.length; i += MAX_PER_SECOND) {
      batches.push(queue.slice(i, i + MAX_PER_SECOND));
    }

    for (const batch of batches) {
      await Promise.all(batch.map(s => this.fetch(s)));
      await sleep(1000);
    }

    this.lastProcessedCount = queue.length;
    this.cache.prioritySymbols.clear();
    this.isProcessing = false;
  }

  getChange(symbol) {
    return this.cache.getChange(symbol);
  }

  getOIData(symbol) {
    return this.cache.getOIData(symbol);
  }

  getStats() {
    return this.cache.getStats();
  }

  reset() {
    this.cache = new OICache();
  }
}

export const oiTracker = new OITracker();
