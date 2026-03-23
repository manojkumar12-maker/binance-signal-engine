import axios from 'axios';
import { config } from '../../config/config.js';

const BINANCE_API = 'https://fapi.binance.com';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

export const MAX_PER_SECOND = 15;
export const TTL_MS = 15000;
export const HISTORY_WINDOW = 60;
export const MAX_TRACKED = 200;

class FlowTracker {
  constructor() {
    this.data = new Map();
  }

  update(symbol, qty, isBuyerMaker) {
    if (!this.data.has(symbol)) {
      this.data.set(symbol, {
        buy: 0,
        sell: 0,
        volume: 0,
        history: []
      });
    }

    const d = this.data.get(symbol);
    const qtyNum = parseFloat(qty) || 0;
    
    if (isBuyerMaker) {
      d.sell += qtyNum;
    } else {
      d.buy += qtyNum;
    }

    d.volume += qtyNum;
  }

  get(symbol) {
    return this.data.get(symbol);
  }

  reset(symbol) {
    const d = this.data.get(symbol);
    if (!d) return;

    d.history.push({
      buy: d.buy,
      sell: d.sell,
      volume: d.volume
    });

    if (d.history.length > 20) d.history.shift();

    d.buy = 0;
    d.sell = 0;
    d.volume = 0;
  }

  getFakeOI(symbol) {
    const d = this.data.get(symbol);
    if (!d || d.history.length < 5) return null;

    const recent = d.history[d.history.length - 1];
    const prev = d.history[Math.max(0, d.history.length - 5)];

    const total = recent.buy + recent.sell;
    if (total === 0) return null;

    const imbalance = (recent.buy - recent.sell) / total;
    const volChange = prev.volume > 0 ? (recent.volume - prev.volume) / prev.volume : 0;

    let fakeOI = 0;

    if (Math.abs(imbalance) > 0.2 && volChange > 0.5) {
      fakeOI = imbalance * volChange * 5;
    } else if (Math.abs(imbalance) < 0.1) {
      fakeOI = 0;
    } else {
      fakeOI = imbalance * 2;
    }

    return fakeOI;
  }

  classifyFakeOI(priceChange, fakeOI) {
    if (fakeOI === null) return 'NEUTRAL';
    
    if (priceChange > 0 && fakeOI > 0.5) return 'EARLY_LONG';
    if (priceChange > 0 && fakeOI < -0.5) return 'SHORT_SQUEEZE';
    if (priceChange < 0 && fakeOI > 0.5) return 'EARLY_SHORT';
    if (priceChange < 0 && fakeOI < -0.5) return 'LONG_EXIT';
    
    return 'NEUTRAL';
  }
}

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
    this.flowTracker = new FlowTracker();
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

  handleTrade(trade) {
    const { symbol, quantity, isBuyerMaker } = trade;
    if (symbol && this.cache.isValid(symbol)) {
      this.flowTracker.update(symbol, quantity, isBuyerMaker);
    }
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

      const change = this.cache.getChange(symbol);
      const historyLen = this.cache.get(symbol)?.history.length || 0;
      if (symbol === 'BTCUSDT' && historyLen % 10 === 0) {
        console.log(`📊 OI BTC: current=${oi.toFixed(0)} history=${historyLen} change=${change.toFixed(3)}%`);
      }

      return change;
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

  getFakeOI(symbol) {
    return this.flowTracker.getFakeOI(symbol);
  }

  classifyFakeOI(priceChange, symbol) {
    const fakeOI = this.flowTracker.getFakeOI(symbol);
    return this.flowTracker.classifyFakeOI(priceChange, fakeOI);
  }

  resetFlow(symbol) {
    this.flowTracker.reset(symbol);
  }

  getStats() {
    return this.cache.getStats();
  }

  reset() {
    this.cache = new OICache();
    this.flowTracker = new FlowTracker();
  }
}

export const oiTracker = new OITracker();
export { FlowTracker };
