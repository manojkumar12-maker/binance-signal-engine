import WebSocket from 'ws';
import { config } from '../../config/config.js';

class OrderBookAnalyzer {
  constructor() {
    this.orderBooks = new Map();
    this.orderBookStreams = new Map();
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.callbacks = [];
    this.spoofingDetection = new Map();
  }

  start(symbols = []) {
    if (symbols.length === 0) return;
    const streams = symbols.slice(0, 100).map(s => `${s.toLowerCase()}@depth20@100ms`);
    const wsUrl = `wss://fstream.binance.com/stream?streams=${streams.join('/')}`;
    
    console.log(`📊 OrderBook Analyzer: Streaming ${streams.length} order books`);
    
    this.ws = new WebSocket(wsUrl);

    this.ws.on('open', () => {
      this.reconnectAttempts = 0;
    });

    this.ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data);
        if (msg.data) {
          this.processDepthUpdate(msg.data);
        }
      } catch (e) {}
    });

    this.ws.on('close', () => {
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => this.start(symbols), 3000 * this.reconnectAttempts);
      }
    });
  }

  processDepthUpdate(data) {
    const { s: symbol, b: bids, a: asks, E: timestamp } = data;
    if (!symbol) return;

    const book = this.orderBooks.get(symbol) || { bids: [], asks: [], lastUpdate: 0 };
    
    this.detectSpoofing(symbol, bids, asks);

    const bidVolume = bids.reduce((sum, [price, qty]) => sum + parseFloat(qty), 0);
    const askVolume = asks.reduce((sum, [price, qty]) => sum + parseFloat(qty), 0);
    
    const imbalance = bidVolume > 0 ? bidVolume / Math.max(askVolume, 1) : 1;
    const midPrice = bids.length > 0 && asks.length > 0 
      ? (parseFloat(bids[0][0]) + parseFloat(asks[0][0])) / 2 
      : 0;
    const spread = asks.length > 0 && bids.length > 0 
      ? (parseFloat(asks[0][0]) - parseFloat(bids[0][0])) / midPrice 
      : 0;

    book.bids = bids.map(([price, qty]) => ({ price: parseFloat(price), qty: parseFloat(qty) }));
    book.asks = asks.map(([price, qty]) => ({ price: parseFloat(price), qty: parseFloat(qty) }));
    book.bidVolume = bidVolume;
    book.askVolume = askVolume;
    book.imbalance = imbalance;
    book.midPrice = midPrice;
    book.spread = spread;
    book.lastUpdate = timestamp;

    this.orderBooks.set(symbol, book);

    const spoofing = this.spoofingDetection.get(symbol);
    const analysis = {
      symbol,
      imbalance,
      bidVolume,
      askVolume,
      midPrice,
      spread,
      largeBidOrders: bids.filter(b => parseFloat(b[1]) > 100000).length,
      largeAskOrders: asks.filter(a => parseFloat(a[1]) > 100000).length,
      spoofingRisk: spoofing?.risk || 0
    };

    this.callbacks.forEach(cb => cb(analysis));
  }

  detectSpoofing(symbol, bids, asks) {
    const now = Date.now();
    const prev = this.spoofingDetection.get(symbol);
    
    const largeBids = bids.filter(b => parseFloat(b[1]) > 50000);
    const largeAsks = asks.filter(a => parseFloat(a[1]) > 50000);

    if (!prev) {
      this.spoofingDetection.set(symbol, { 
        lastBids: bids, 
        lastAsks: asks, 
        lastTime: now,
        risk: 0 
      });
      return;
    }

    let bidDisappeared = 0;
    let askDisappeared = 0;

    prev.lastBids.forEach(([price, qty]) => {
      if (parseFloat(qty) > 50000 && !bids.find(b => b[0] === price)) {
        bidDisappeared++;
      }
    });

    prev.lastAsks.forEach(([price, qty]) => {
      if (parseFloat(qty) > 50000 && !asks.find(a => a[0] === price)) {
        askDisappeared++;
      }
    });

    const timeDelta = (now - prev.lastTime) / 1000;
    const risk = (bidDisappeared + askDisappeared) / Math.max(timeDelta, 1);

    this.spoofingDetection.set(symbol, { 
      lastBids: bids, 
      lastAsks: asks, 
      lastTime: now,
      risk: Math.min(risk * 10, 100)
    });
  }

  onUpdate(callback) {
    this.callbacks.push(callback);
  }

  getImbalance(symbol) {
    return this.orderBooks.get(symbol)?.imbalance || 1;
  }

  getAnalysis(symbol) {
    return this.orderBooks.get(symbol);
  }

  stop() {
    if (this.ws) {
      this.ws.close();
    }
    this.orderBooks.clear();
  }
}

export const orderBookAnalyzer = new OrderBookAnalyzer();
