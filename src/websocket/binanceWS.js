import WebSocket from 'ws';
import axios from 'axios';
import { config } from '../../config/config.js';

class BinanceWebSocketManager {
  constructor() {
    this.ws = null;
    this.tickers = new Map();
    this.callbacks = {
      ticker: [],
      kline: [],
      pump: []
    };
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.pingInterval = null;
  }

  async initialize() {
    console.log('🔌 Initializing Binance WebSocket connection...');
    await this.fetchAllSymbols();
    this.connect();
  }

  async fetchAllSymbols() {
    try {
      const response = await axios.get(`${config.binance.apiUrl}/fapi/v1/exchangeInfo`);
      this.symbols = response.data.symbols
        .filter(s => s.contractType === 'PERPETUAL' && s.quoteAsset === 'USDT' && s.status === 'TRADING')
        .map(s => s.symbol);
      
      if (config?.preFilters?.excludeStablecoins) {
        const stablecoins = ['BUSDUSDT', 'USDCUSDT', 'TUSDUSDT', 'FDUSDUSDT'];
        this.symbols = this.symbols.filter(s => !stablecoins.includes(s));
      }

      console.log(`📊 Loaded ${this.symbols.length} USDT perpetual symbols`);
    } catch (error) {
      console.error('❌ Failed to fetch symbols:', error.message);
      this.symbols = [];
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
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      console.log(`🔄 Reconnecting... Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
      const delay = Math.min(3000 * Math.pow(2, this.reconnectAttempts - 1), 30000);
      setTimeout(() => this.connect(), delay);
    } else {
      console.error('❌ Max reconnection attempts reached');
    }
  }

  onTicker(callback) {
    this.callbacks.ticker.push(callback);
  }

  onPump(callback) {
    this.callbacks.pump.push(callback);
  }

  getTickers() {
    return Array.from(this.tickers.values());
  }

  getTicker(symbol) {
    return this.tickers.get(symbol);
  }

  disconnect() {
    this.stopPing();
    if (this.ws) {
      this.ws.close();
    }
  }
}

export const wsManager = new BinanceWebSocketManager();
