import { createServer } from 'http';
import { WebSocketServer } from 'ws';

const PORT = process.env.PORT || 3000;

class SignalAPIServer {
  constructor() {
    this.signals = [];
    this.server = null;
    this.wss = null;
    this.clients = new Set();
  }

  async start() {
    this.server = createServer((req, res) => {
      this.handleRequest(req, res);
    });

    this.wss = new WebSocketServer({ server: this.server });

    this.wss.on('connection', (ws) => {
      this.clients.add(ws);
      ws.on('close', () => this.clients.delete(ws));
      ws.on('error', () => this.clients.delete(ws));
    });

    this.server.listen(PORT, () => {
      console.log(`🚀 API Server running on port ${PORT}`);
    });
  }

  handleRequest(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Content-Type', 'application/json');

    if (req.url === '/api/signals' && req.method === 'GET') {
      res.end(JSON.stringify({ signals: this.signals, count: this.signals.length }));
    } else if (req.url === '/api/health' && req.method === 'GET') {
      res.end(JSON.stringify({ status: 'ok', uptime: process.uptime() }));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: 'Not found' }));
    }
  }

  broadcast(data) {
    const message = JSON.stringify(data);
    this.clients.forEach(client => {
      if (client.readyState === 1) {
        client.send(message);
      }
    });
  }

  addSignal(signal) {
    this.signals.unshift(signal);
    if (this.signals.length > 100) this.signals.pop();
    this.broadcast({ type: 'NEW_SIGNAL', signal });
  }

  updateSignal(symbol, update) {
    const signal = this.signals.find(s => s.symbol === symbol);
    if (signal) {
      Object.assign(signal, update);
      this.broadcast({ type: 'UPDATE_SIGNAL', signal });
    }
  }
}

export const apiServer = new SignalAPIServer();
