import { createServer } from 'http';
import { WebSocketServer } from 'ws';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { getSignals, getSignalStats, createSignal as dbCreateSignal, updateSignalStatus as dbUpdateSignalStatus, clearSignals, clearOldSignals } from '../database/db.js';
import { state, getRecentSignals } from '../state.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || process.env.SERVER_PORT || 8080;

class SignalAPIServer {
  constructor() {
    this.server = null;
    this.wss = null;
    this.clients = new Set();
  }

  async start() {
    console.log(`🔧 Starting server on port ${PORT} (env PORT=${process.env.PORT})...`);
    
    return new Promise((resolve, reject) => {
      this.server = createServer((req, res) => {
        this.handleRequest(req, res);
      });

      this.wss = new WebSocketServer({ server: this.server });

      this.wss.on('connection', (ws) => {
        this.clients.add(ws);
        ws.on('close', () => this.clients.delete(ws));
        ws.on('error', () => this.clients.delete(ws));
        
        ws.send(JSON.stringify({ type: 'CONNECTED', message: 'Dashboard connected' }));
      });

      const timeout = setTimeout(() => {
        console.error('❌ Server start timeout!');
        reject(new Error('Server start timeout'));
      }, 10000);

      this.server.on('listening', () => {
        clearTimeout(timeout);
        console.log(`✅ Server listening on port ${PORT}`);
        resolve();
      });

      this.server.on('error', (err) => {
        clearTimeout(timeout);
        console.error('❌ Server error:', err.message);
        reject(err);
      });

      this.server.listen(PORT, '0.0.0.0');
    });
  }

  handleRequest(req, res) {
    const url = req.url.split('?')[0];

    if (url === '/' || url === '/dashboard') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(readFileSync(join(__dirname, '../../frontend/index.html')));
      return;
    }

    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Content-Type', 'application/json');

    if (url === '/api/stats' && req.method === 'GET') {
      this.getStats().then(stats => res.end(JSON.stringify(stats)));
    } else if (url === '/api/signals' && req.method === 'GET') {
      this.getAllSignals().then(data => res.end(JSON.stringify(data)));
    } else if (url === '/api/health' && req.method === 'GET') {
      res.end(JSON.stringify({ status: 'ok', uptime: process.uptime() }));
    } else if (url === '/api/signals/clear' && (req.method === 'DELETE' || req.method === 'GET')) {
      clearSignals(false).then(result => res.end(JSON.stringify({ success: result, deleted: true })));
    } else if (url === '/api/signals/clear-old' && (req.method === 'DELETE' || req.method === 'GET')) {
      const hours = parseInt(req.url.split('=')[1]) || 24;
      clearOldSignals(hours).then(result => res.end(JSON.stringify({ success: result, hours })));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: 'Not found' }));
    }
  }

  async getStats() {
    const dbStats = await getSignalStats();
    const recentSignals = getRecentSignals(20);
    
    return {
      signalsGenerated: dbStats.total || state.stats.total,
      signalsByTier: dbStats.tierCounts || state.stats,
      symbolsMonitored: global.engine?.stats?.symbolsMonitored || 0,
      activeSignals: dbStats.active || state.stats.active,
      uptime: global.engine?.stats?.startedAt ? Date.now() - global.engine.stats.startedAt : 0,
      recentSignals: recentSignals.map(s => ({
        symbol: s.symbol,
        tier: s.tier,
        score: s.metrics?.score,
        priceChange: s.metrics?.priceChange,
        volumeSpike: s.metrics?.volumeSpike,
        timestamp: s.timestamp
      })),
      autoTuner: global.autoTuner?.getStats?.() || {},
      state: state.stats
    };
  }

  async getAllSignals() {
    const dbSignals = await getSignals(100);
    const localSignals = getRecentSignals(100);
    
    const allSignals = [...localSignals];
    
    for (const dbSignal of dbSignals) {
      const exists = allSignals.find(s => s.id === dbSignal.id);
      if (!exists) {
        allSignals.push(this.formatSignalForApi(dbSignal));
      }
    }
    
    allSignals.sort((a, b) => b.timestamp - a.timestamp);
    
    return { 
      signals: allSignals.slice(0, 100), 
      count: allSignals.length,
      stats: state.stats
    };
  }

  formatSignalForApi(signal) {
    if (signal.timestamp instanceof Date) {
      signal.timestamp = signal.timestamp.getTime();
    }
    
    if (signal.closedAt instanceof Date) {
      signal.closedAt = signal.closedAt.getTime();
    }
    
    return {
      id: signal.id,
      symbol: signal.symbol,
      type: signal.type,
      tier: signal.tier,
      timestamp: signal.timestamp,
      entryPrice: signal.entryPrice,
      atr: signal.atr,
      targets: {
        tp1: signal.tp1 || signal.targets?.tp1,
        tp2: signal.tp2 || signal.targets?.tp2,
        tp3: signal.tp3 || signal.targets?.tp3,
        tp4: signal.tp4 || signal.targets?.tp4,
        tp5: signal.tp5 || signal.targets?.tp5
      },
      stopLoss: signal.stopLoss,
      riskReward: {
        tp1: signal.tp1RR || signal.riskReward?.tp1,
        tp2: signal.tp2RR || signal.riskReward?.tp2,
        tp3: signal.tp3RR || signal.riskReward?.tp3
      },
      metrics: {
        priceChange: signal.priceChange || signal.metrics?.priceChange,
        volumeSpike: signal.volumeSpike || signal.metrics?.volumeSpike,
        momentum: signal.momentum || signal.metrics?.momentum,
        score: signal.score || signal.metrics?.score
      },
      factors: typeof signal.factors === 'string' ? JSON.parse(signal.factors) : (signal.factors || []),
      status: signal.status,
      closedAt: signal.closedAt,
      closedPrice: signal.closedPrice
    };
  }

  broadcast(data) {
    const message = JSON.stringify(data);
    this.clients.forEach(client => {
      if (client.readyState === 1) {
        try {
          client.send(message);
        } catch (e) {
          this.clients.delete(client);
        }
      }
    });
  }

  async addSignal(signal) {
    try {
      const dbSignal = await dbCreateSignal(signal);
      const formattedSignal = this.formatSignalForApi(dbSignal);
      
      state.signals.unshift(formattedSignal);
      if (state.signals.length > 500) state.signals.pop();
      
      this.broadcast({ type: 'NEW_SIGNAL', signal: formattedSignal });
      
      return formattedSignal;
    } catch (error) {
      console.error('Failed to save signal:', error);
      return signal;
    }
  }

  async updateSignalStatus(symbol, status, closedPrice = null) {
    try {
      const signal = state.signals.find(s => s.symbol === symbol && 
        (s.status === 'ACTIVE' || s.status === 'HOT' || s.status === 'WATCHLIST'));
      
      if (signal?.id) {
        await dbUpdateSignalStatus(signal.id, status, closedPrice);
        signal.status = status;
        if (closedPrice) {
          signal.closedPrice = closedPrice;
          signal.closedAt = Date.now();
        }
        this.broadcast({ type: 'UPDATE_SIGNAL', symbol, status, closedPrice });
      }
    } catch (error) {
      console.error('Failed to update signal status:', error);
    }
  }
}

export const apiServer = new SignalAPIServer();
