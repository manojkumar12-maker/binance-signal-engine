import { Server } from 'socket.io';
import { createServer } from 'http';

const httpServer = createServer();
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
