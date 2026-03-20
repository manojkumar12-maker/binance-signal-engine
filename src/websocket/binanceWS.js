import WebSocket from 'ws';
import axios from 'axios';
import { config } from '../../config/config.js';

class BinanceWebSocketManager {
  constructor() {
    this.ws = null;
    this.tickers = new Map();
    this.klines = new Map();
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
      
      if (config.filters.excludeStablecoins) {
        const stablecoins = ['BUSDUSDT', 'USDCUSDT', 'TUSDUSDT', 'FDUSDUSDT'];
        this.symbols = this.symbols.filter(s => !stablecoins.includes(s));
      }

      console.log(`📊 Loaded ${this.symbols.length} USDT perpetual symbols`);
    } catch (error) {
      console.error('❌ Failed to fetch symbols:', error.message);
      this.symbols = [];
    }
  }

  connect() {
    const streams = this.symbols.map(s => `${s.toLowerCase()}@ticker`).join('/');
    this.ws = new WebSocket(`${config.binance.wsUrl}/${streams}`);

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
  }

  handleMessage(message) {
    if (message.e === '24hrTicker') {
      this.handleTicker(message);
    }
  }

  handleTicker(ticker) {
    const data = {
      symbol: ticker.s,
      price: parseFloat(ticker.c),
      priceChange: parseFloat(ticker.p),
      priceChangePercent: parseFloat(ticker.P),
      high24h: parseFloat(ticker.h),
      low24h: parseFloat(ticker.l),
      volume: parseFloat(ticker.v),
      quoteVolume: parseFloat(ticker.q),
      timestamp: ticker.E
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
      setTimeout(() => this.connect(), 3000 * this.reconnectAttempts);
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
