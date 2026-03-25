import { Server } from 'socket.io';
import { createServer } from 'http';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const httpServer = createServer((req, res) => {
  const dashboardPath = join(__dirname, '../../frontend/dashboard.html');
  
  if (req.url === '/' || req.url === '/dashboard') {
    try {
      const html = readFileSync(dashboardPath, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(html);
    } catch (err) {
      res.writeHead(500);
      res.end('Error loading dashboard');
    }
  } else if (req.url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', timestamp: Date.now() }));
  } else {
    res.writeHead(404);
    res.end('Not found');
  }
});

const io = new Server(httpServer, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});

const signalHistory = [];
const MAX_HISTORY = 100;

io.on('connection', (socket) => {
  console.log('📊 Dashboard connected:', socket.id);

  socket.emit('history', signalHistory.slice(0, 50));

  socket.on('disconnect', () => {
    console.log('📊 Dashboard disconnected:', socket.id);
  });
});

export function emitSignal(signal) {
  const signalData = {
    ...signal,
    emittedAt: Date.now()
  };

  signalHistory.unshift(signalData);
  if (signalHistory.length > MAX_HISTORY) {
    signalHistory.pop();
  }

  io.emit('signal', signalData);

  if (signalData.type === 'SNIPER') {
    io.emit('sniper', signalData);
  } else if (signalData.type === 'PREDICT' || signalData.type === 'ACCUMULATION') {
    io.emit('predict', signalData);
  }
}

export function emitStateUpdate(data) {
  io.emit('stateUpdate', data);
}

export function emitMarketData(data) {
  io.emit('marketData', data);
}

export function getSignalHistory() {
  return signalHistory;
}

const PORT = process.env.DASHBOARD_PORT || 3001;

export function startDashboardServer() {
  httpServer.listen(PORT, () => {
    console.log(`📊 Dashboard server running on port ${PORT}`);
  });
}

export default io;
