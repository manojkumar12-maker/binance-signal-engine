import WebSocket from 'ws';
import axios from 'axios';
import fs from 'fs';
import { config } from '../../config/config.js';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const SYMBOLS_CACHE_FILE = 'symbols_cache.json';
const CACHE_MAX_AGE = 24 * 60 * 60 * 1000;

async function fetchWithRetry(url, options = {}, retries = 5, delay = 5000) {
  try {
    const response = await axios.get(url, {
      ...options,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        ...options.headers
      },
      timeout: 20000
    });
    return response;
  } catch (error) {
    if (retries === 0) {
      console.error(`❌ ${url} failed after all retries`);
      throw error;
    }
    
    if (error.response?.status === 418) {
      const backoffDelay = (6 - retries) * 15000;
      console.log(`⚠️ 418 Rate Limited! Backing off for ${backoffDelay/1000}s (${retries} retries left)`);
      await sleep(backoffDelay);
      return fetchWithRetry(url, options, retries - 1, delay * 2);
    } else {
      console.log(`⚠️ ${error.message}, retry in ${delay}ms... (${retries} left)`);
      await sleep(delay);
      return fetchWithRetry(url, options, retries - 1, delay * 1.5);
    }
  }
}

function loadCachedSymbols() {
  try {
    if (fs.existsSync(SYMBOLS_CACHE_FILE)) {
      const data = JSON.parse(fs.readFileSync(SYMBOLS_CACHE_FILE, 'utf8'));
      if (data.timestamp && (Date.now() - data.timestamp) < CACHE_MAX_AGE) {
        console.log('📦 Loaded symbols from cache:', data.symbols.length);
        return data.symbols;
      }
    }
  } catch (e) {
    console.log('⚠️ Cache read failed:', e.message);
  }
  return null;
}

function saveCachedSymbols(symbols) {
  try {
    fs.writeFileSync(SYMBOLS_CACHE_FILE, JSON.stringify({
      symbols,
      timestamp: Date.now()
    }));
  } catch (e) {
    console.log('⚠️ Cache write failed:', e.message);
  }
}

const FALLBACK_SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
  'ADAUSDT', 'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'SHIBUSDT',
  'LTCUSDT', 'AVAXUSDT', 'LINKUSDT', 'ATOMUSDT', 'UNIUSDT',
  'ETCUSDT', 'XLMUSDT', 'NEARUSDT', 'APTUSDT', 'ARBUSDT',
  'OPUSDT', 'FILUSDT', 'LDOUSDT', 'VETUSDT', 'ICPUSDT'
];

class BinanceWebSocketManager {
  constructor() {
    this.ws = null;
    this.tradeWs = null;
    this.tickers = new Map();
    this.callbacks = {
      ticker: [],
      kline: [],
      pump: [],
      trade: [],
      liquidation: []
    };
    this.liqStreamReady = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.pingInterval = null;
    this.tradePingInterval = null;
    this.isReconnecting = false;
    this.tradeStreamConnecting = false;
    this.tradeStreamReady = false;
    this.symbolsLoaded = false;
  }

  async initialize() {
    console.log('🔌 Initializing Binance WebSocket connection...');
    await this.fetchAllSymbols();
    
    if (this.symbols.length > 0) {
      this.connect();
      setTimeout(() => {
        this.connectTradeStream();
      }, 3000);
    } else {
      console.log('⚠️ Using fallback symbols due to API failure');
      this.symbols = FALLBACK_SYMBOLS;
      this.connect();
      setTimeout(() => {
        this.connectTradeStream();
      }, 3000);
    }
  }

  async fetchAllSymbols() {
    console.log('🔄 Fetching symbols from Binance API...');
    
    const cached = loadCachedSymbols();
    if (cached) {
      this.symbols = cached;
      this.symbolsLoaded = true;
      console.log(`📊 Loaded ${this.symbols.length} symbols from cache`);
      return;
    }
    
    try {
      const response = await fetchWithRetry(`${config.binance.apiUrl}/fapi/v1/exchangeInfo`);
      console.log('📡 API response status:', response.status);
      
      this.symbols = response.data.symbols
        .filter(s => s.contractType === 'PERPETUAL' && s.quoteAsset === 'USDT' && s.status === 'TRADING')
        .map(s => s.symbol);
      
      if (config?.preFilters?.excludeStablecoins) {
        const stablecoins = ['BUSDUSDT', 'USDCUSDT', 'TUSDUSDT', 'FDUSDUSDT'];
        this.symbols = this.symbols.filter(s => !stablecoins.includes(s));
      }
      
      saveCachedSymbols(this.symbols);

      this.symbolsLoaded = true;
      console.log(`📊 Loaded ${this.symbols.length} USDT perpetual symbols`);
      if (this.symbols.length > 0) {
        console.log('📊 First 5 symbols:', this.symbols.slice(0, 5));
      }
    } catch (error) {
      console.error('❌ Failed to fetch symbols:', error.message);
      console.error('❌ Using fallback symbols');
      this.symbols = FALLBACK_SYMBOLS;
      this.symbolsLoaded = true;
    }
  }

  chunkArray(arr, size) {
    const result = [];
    for (let i = 0; i < arr.length; i += size) {
      result.push(arr.slice(i, i + size));
    }
    return result;
  }

  connect() {
    if (!this.symbols || this.symbols.length === 0) {
      console.error('❌ No symbols loaded. Skipping WebSocket.');
      return;
    }

    const streams = ['!ticker@arr'];
    const wsUrl = `wss://fstream.binance.com/stream?streams=${streams.join('/')}`;
    
    console.log(`🔌 Connecting to Binance WebSocket...`);
    this.ws = new WebSocket(wsUrl);

    this.ws.on('open', () => {
      console.log('✅ WebSocket connected to Binance');
      this.reconnectAttempts = 0;
      this.startPing();
    });

    this.ws.on('message', (data) => {
      try {
        const message = JSON.parse(data);
        this.handleMessage(message);
      } catch (error) {
        console.error('❌ Error parsing message:', error.message);
      }
    });

    this.ws.on('close', () => {
      console.log('⚠️ WebSocket disconnected');
      this.stopPing();
      this.isReconnecting = false;
      this.reconnect();
    });

    this.ws.on('error', (error) => {
      console.error('❌ WebSocket error:', error.message);
    });

    this.ws.on('ping', () => {
      if (this.ws) this.ws.pong();
    });
  }

  handleMessage(message) {
    try {
      if (message.stream === '!ticker@arr' && message.data) {
        const tickers = Array.isArray(message.data) ? message.data : [message.data];
        tickers.forEach(ticker => {
          if (ticker.s && ticker.s.endsWith('USDT')) {
            this.handleTicker(ticker);
          }
        });
      } else if (message.e === '24hrTicker') {
        this.handleTicker(message.data || message);
      }
    } catch (error) {
      // Silent fail for malformed messages
    }
  }

  handleTicker(ticker) {
    if (!ticker.s) return;
    this.tickerCount = (this.tickerCount || 0) + 1;
    if (this.tickerCount % 1000 === 0) {
      console.log(`📊 Tickers processed: ${this.tickerCount}, Cached symbols: ${this.tickers.size}`);
    }
    
    const data = {
      symbol: ticker.s,
      price: parseFloat(ticker.c) || 0,
      priceChange: parseFloat(ticker.p) || 0,
      priceChangePercent: parseFloat(ticker.P) || 0,
      high: parseFloat(ticker.h) || parseFloat(ticker.c) || 0,
      low: parseFloat(ticker.l) || parseFloat(ticker.c) || 0,
      high24h: parseFloat(ticker.h) || 0,
      low24h: parseFloat(ticker.l) || 0,
      volume: parseFloat(ticker.v) || 0,
      quoteVolume: parseFloat(ticker.q) || 0,
      bid: parseFloat(ticker.b) || parseFloat(ticker.c) * 0.999 || 0,
      ask: parseFloat(ticker.a) || parseFloat(ticker.c) * 1.001 || 0,
      timestamp: ticker.E || Date.now()
    };

    this.tickers.set(data.symbol, data);
    this.callbacks.ticker.forEach(cb => cb(data));
  }

  startPing() {
    this.pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.ping();
      }
    }, 30000);
  }

  stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  reconnect() {
    if (this.isReconnecting) return;
    this.isReconnecting = true;
    
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`🔄 Reconnecting... Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
      const delay = Math.min(2000 * Math.pow(2, this.reconnectAttempts - 1), 15000);
      setTimeout(() => {
        this.isReconnecting = false;
        this.connect();
      }, delay);
    } else {
      this.isReconnecting = false;
      console.error('❌ Max reconnection attempts reached');
    }
  }

  connectTradeStream() {
    if (this.tradeStreamConnecting || this.tradeStreamReady) return;
    this.tradeStreamConnecting = true;
    if (!this.symbols || this.symbols.length === 0) return;

    const chunkSize = 100;
    const chunks = this.chunkArray(this.symbols, chunkSize);
    
    console.log(`📡 Connecting trade stream: ${this.symbols.length} symbols in ${chunks.length} chunks (${chunkSize} each)`);
    
    chunks.forEach((chunk, index) => {
      setTimeout(() => {
        const streams = chunk.map(s => `${s.toLowerCase()}@trade`);
        const wsUrl = `wss://fstream.binance.com/stream?streams=${streams.join('/')}`;
        
        const tradeWs = new WebSocket(wsUrl);
        
        tradeWs.on('open', () => {
          this.tradeStreamReady = true;
          this.tradeStreamConnecting = false;
          console.log(`✅ Trade stream ${index + 1}/${chunks.length} connected (${chunk.length} symbols)`);
        });
        
        tradeWs.on('message', (data) => {
          try {
            const message = JSON.parse(data);
            if (message.data) {
              this.handleTrade(message.data);
            } else if (message.stream && message.stream.includes('@trade')) {
              console.log('⚠️ Unexpected trade format:', JSON.stringify(message).slice(0, 200));
            }
          } catch (error) {
            console.error('❌ Trade parse error:', error.message);
          }
        });
        
        tradeWs.on('close', () => {
          console.log(`⚠️ Trade stream ${index + 1} closed, reconnecting...`);
          this.tradeStreamReady = false;
          setTimeout(() => {
            this.connectTradeStream();
          }, 2000);
        });
        
        tradeWs.on('error', (err) => {
          console.error(`❌ Trade stream ${index + 1} error: ${err.message}`);
          tradeWs.close();
        });
      }, index * 2000);
    });
    
    setTimeout(() => {
      this.connectLiquidationStream();
    }, 5000);
  }
  
  connectLiquidationStream() {
    if (this.liqStreamReady) return;
    if (!this.symbols || this.symbols.length === 0) return;
    
    const topSymbols = this.symbols.slice(0, 30);
    const streams = topSymbols.map(s => `${s.toLowerCase()}@forceOrder`);
    const wsUrl = `wss://fstream.binance.com/stream?streams=${streams.join('/')}`;
    
    this.liqWs = new WebSocket(wsUrl);
    
    this.liqWs.on('open', () => {
      this.liqStreamReady = true;
      console.log('✅ Liquidation stream connected');
    });
    
    this.liqWs.on('message', (data) => {
      try {
        const message = JSON.parse(data);
        if (message.data) {
          const liq = message.data;
          const symbol = liq.s;
          const side = liq.S;
          const price = parseFloat(liq.p);
          const qty = parseFloat(liq.q);
          
          console.log(`💥 LIQ ${symbol} ${side} ${price} x${qty}`);
          
          this.callbacks.liquidation.forEach(cb => cb({ symbol, side, price, qty }));
        }
      } catch (error) {}
    });
    
    this.liqWs.on('close', () => {
      console.log('⚠️ Liquidation stream closed, reconnecting...');
      this.liqStreamReady = false;
      setTimeout(() => this.connectLiquidationStream(), 5000);
    });
  }

  handleTrade(trade) {
    const tradeData = {
      symbol: trade.s,
      price: parseFloat(trade.p),
      quantity: parseFloat(trade.q),
      isBuyerMaker: trade.m,
      timestamp: trade.T
    };

    if (!tradeData.symbol) {
      if ((this.tradeCount || 0) % 50000 === 0) {
        console.log('❌ Trade missing symbol:', JSON.stringify(trade).slice(0, 200));
      }
      return;
    }

    this.callbacks.trade.forEach(cb => cb(tradeData));

    this.tradeCount = (this.tradeCount || 0) + 1;
    this.lastSymbol = tradeData.symbol;
    
    if (this.tradeCount % 10000 === 0) {
      console.log(`📊 Trades received: ${this.tradeCount} (${this.tickers.size} symbols) | Last: ${this.lastSymbol}`);
    }
  }

  onTicker(callback) {
    this.callbacks.ticker.push(callback);
  }

  onTrade(callback) {
    this.callbacks.trade.push(callback);
  }

  onPump(callback) {
    this.callbacks.pump.push(callback);
  }
  
  onLiquidation(callback) {
    this.callbacks.liquidation.push(callback);
  }

  getTickers() {
    return Array.from(this.tickers.values());
  }

  getTicker(symbol) {
    return this.tickers.get(symbol);
  }

  disconnect() {
    this.stopPing();
    this.isReconnecting = false;
    this.tradeStreamConnecting = false;
    this.tradeStreamReady = false;
    if (this.ws) {
      this.ws.close();
    }
  }
}

export const wsManager = new BinanceWebSocketManager();
