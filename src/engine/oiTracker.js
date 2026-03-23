import axios from 'axios';

const BINANCE_API = 'https://fapi.binance.com';

const MAX_BATCH = 50;
const FETCH_INTERVAL = 5000;
const HISTORY_SIZE = 20;
const MAX_TRACKED = 200;

class FlowTracker {
  constructor() {
    this.data = new Map();
  }

  update(symbol, qty, isBuyerMaker) {
    if (!this.data.has(symbol)) {
      this.data.set(symbol, { buy: 0, sell: 0, volume: 0, history: [] });
    }

    const d = this.data.get(symbol);
    const qtyNum = parseFloat(qty) || 0;
    
    if (isBuyerMaker) d.sell += qtyNum;
    else d.buy += qtyNum;
    d.volume += qtyNum;
  }

  reset(symbol) {
    const d = this.data.get(symbol);
    if (!d) return;

    d.history.push({ buy: d.buy, sell: d.sell, volume: d.volume, time: Date.now() });
    if (d.history.length > 20) d.history.shift();

    d.buy = 0;
    d.sell = 0;
    d.volume = 0;
  }

  getFakeOI(symbol) {
    const d = this.data.get(symbol);
    if (!d || d.history.length < 3) return null;

    const recent = d.history[d.history.length - 1];
    const prev = d.history[Math.max(0, d.history.length - 3)];

    const total = recent.buy + recent.sell;
    if (total === 0) return null;

    const imbalance = (recent.buy - recent.sell) / total;
    const volChange = prev.volume > 0 ? (recent.volume - prev.volume) / prev.volume : 0;

    if (Math.abs(imbalance) > 0.2 && volChange > 0.3) {
      return imbalance * volChange * 10;
    } else if (Math.abs(imbalance) < 0.1) {
      return 0;
    }
    return imbalance * 3;
  }

  classifyFakeOI(priceChange, fakeOI) {
    if (fakeOI === null || Math.abs(fakeOI) < 0.3) return 'NEUTRAL';
    
    if (priceChange > 0 && fakeOI > 0.5) return 'EARLY_LONG';
    if (priceChange > 0 && fakeOI < -0.5) return 'SHORT_SQUEEZE';
    if (priceChange < 0 && fakeOI > 0.5) return 'EARLY_SHORT';
    if (priceChange < 0 && fakeOI < -0.5) return 'LONG_EXIT';
    
    return 'NEUTRAL';
  }
}

class OICache {
  constructor() {
    this.cache = new Map();
    this.validSymbols = new Set();
  }

  async init() {
    try {
      const res = await axios.get(`${BINANCE_API}/fapi/v1/exchangeInfo`, {
        timeout: 15000,
        headers: { 'User-Agent': 'Mozilla/5.0' }
      });
      
      res.data.symbols.forEach(s => {
        if (s.contractType === 'PERPETUAL' && s.status === 'TRADING') {
          this.validSymbols.add(s.symbol);
        }
      });
      
      console.log(`📊 OI: loaded ${this.validSymbols.size} valid symbols`);
    } catch (e) {
      console.log('⚠️ OI: symbol load failed');
    }
  }

  isValid(symbol) {
    return this.validSymbols.has(symbol);
  }

  update(symbol, oi) {
    if (!this.cache.has(symbol)) {
      this.cache.set(symbol, []);
    }

    const arr = this.cache.get(symbol);
    arr.push({ oi, time: Date.now() });
    
    if (arr.length > HISTORY_SIZE) {
      arr.shift();
    }
  }

  get(symbol) {
    return this.cache.get(symbol);
  }

  getChange(symbol) {
    const arr = this.cache.get(symbol);
    if (!arr || arr.length < 2) return 0;

    const first = arr[0].oi;
    const last = arr[arr.length - 1].oi;
    
    if (!first || !last || first === 0) return 0;

    return ((last - first) / first) * 100;
  }

  getOIData(symbol) {
    const arr = this.cache.get(symbol);
    const current = arr?.length > 0 ? arr[arr.length - 1].oi : 0;
    const change = this.getChange(symbol);
    
    let trend = 'NEUTRAL';
    if (change > 0.5) trend = 'INCREASE';
    else if (change < -0.5) trend = 'DECREASE';
    else if (change > 1) trend = 'STRONG_INCREASE';
    else if (change < -1) trend = 'STRONG_DECREASE';

    return { current, change, trend };
  }

  getStats() {
    let positive = 0;
    let negative = 0;
    let nonZero = 0;

    for (const [symbol, arr] of this.cache) {
      if (!this.isValid(symbol)) continue;
      if (arr.length < 2) continue;
      
      const change = this.getChange(symbol);
      if (Math.abs(change) > 0.001) nonZero++;
      if (change > 0.01) positive++;
      else if (change < -0.01) negative++;
    }

    return { tracked: this.cache.size, positive, negative, nonZero };
  }
}

class OITracker {
  constructor() {
    this.cache = new OICache();
    this.flowTracker = new FlowTracker();
    this.symbols = [];
    this.batchIndex = 0;
    this.lastFetch = new Map();
  }

  async init(symbols) {
    await this.cache.init();
    this.symbols = symbols.filter(s => this.cache.isValid(s));
    console.log(`📊 OIT: tracking ${this.symbols.length} symbols`);
  }

  handleTrade(trade) {
    const { symbol, quantity, isBuyerMaker } = trade;
    if (symbol && this.cache.isValid(symbol)) {
      this.flowTracker.update(symbol, quantity, isBuyerMaker);
    }
  }

  markPriority(symbol) {
    // priority handled in fetch
  }

  async fetchSymbol(symbol) {
    const now = Date.now();
    const lastFetch = this.lastFetch.get(symbol) || 0;
    
    if (now - lastFetch < 5000) {
      return this.cache.getChange(symbol);
    }

    try {
      const res = await axios.get(
        `${BINANCE_API}/fapi/v1/openInterest?symbol=${symbol}`,
        { timeout: 3000 }
      );

      this.lastFetch.set(symbol, now);

      if (!res.data?.openInterest) return 0;

      const oi = parseFloat(res.data.openInterest);
      const arr = this.cache.get(symbol);
      const prevOI = arr && arr.length > 0 ? arr[arr.length - 1].oi : 0;
      
      if (oi > 0) {
        if (prevOI > 0) {
          const pctChange = ((oi - prevOI) / prevOI) * 100;
          if (Math.abs(pctChange) > 0.0001) {
            console.log(`📊 OI ${symbol}: prev=${prevOI.toFixed(2)} new=${oi.toFixed(2)} change=${pctChange.toFixed(4)}%`);
          }
        }
        this.cache.update(symbol, oi);
      }

      return this.cache.getChange(symbol);
    } catch (e) {
      if (e.response?.status === 429) {
        console.log(`⚠️ OI rate limited for ${symbol}`);
      }
      return this.cache.getChange(symbol);
    }
  }

  async fetchBatch(symbols) {
    let success = 0;
    let fail = 0;
    
    for (const symbol of symbols) {
      try {
        const result = await this.fetchSymbol(symbol);
        if (result !== 0 || this.cache.get(symbol)?.length > 0) {
          success++;
        } else {
          fail++;
        }
      } catch (e) {
        fail++;
      }
    }
    
    if (success > 0 || fail > 0) {
      console.log(`📊 OI batch: ${success} ok, ${fail} failed`);
    }
    
    return symbols.map(s => this.cache.getChange(s));
  }

  async runCycle() {
    const start = this.batchIndex;
    const end = Math.min(start + MAX_BATCH, this.symbols.length);
    const batch = this.symbols.slice(start, end);
    
    this.batchIndex = end >= this.symbols.length ? 0 : end;

    await this.fetchBatch(batch);

    const stats = this.cache.getStats();
    const btcChange = this.cache.getChange('BTCUSDT');
    
    console.log(`📊 OI: tracked=${stats.tracked} BTC=${btcChange.toFixed(4)}% pos=${stats.positive} neg=${stats.negative}`);
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

  getFlowData(symbol) {
    return this.flowTracker.data.get(symbol);
  }
}

export const oiTracker = new OITracker();
export { MAX_TRACKED };
