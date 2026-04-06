import { io } from "socket.io-client";

const API_URL = process.env.REACT_APP_API_URL || 'https://binance-signal-engine-production.up.railway.app';
const socket = io(API_URL, {
  transports: ['websocket'],
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
