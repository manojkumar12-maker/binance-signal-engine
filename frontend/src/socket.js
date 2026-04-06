import { io } from "socket.io-client";

const SOCKET_URL = process.env.REACT_APP_SOCKET_URL || 'https://binance-signal-engine-production.up.railway.app';
const socket = io(SOCKET_URL, {
  path: '/socket.io',
  transports: ['websocket', 'polling'],
  reconnection: true,
  reconnectionAttempts: 10,
  reconnectionDelay: 1000,
});

socket.on('connect', () => {
  console.log('✅ WebSocket connected');
});

socket.on('disconnect', () => {
  console.log('❌ WebSocket disconnected');
});

socket.on('error', (error) => {
  console.error('WebSocket error:', error);
});

export default socket;
