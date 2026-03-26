import { config } from '../core/config.js';
import { calculatePositionSize } from './risk.js';

const activePositions = new Map();

export function createPosition(symbol, direction, entry, confidence) {
  const size = calculatePositionSize();
  const stopLossPercent = config.STOP_LOSS_PERCENT / 100;
  
  let stopLoss, takeProfit;
  
  if (direction === 'LONG') {
    stopLoss = entry * (1 - stopLossPercent);
    takeProfit = entry * (1 + stopLossPercent * config.TP_MULTIPLIERS[2]);
  } else {
    stopLoss = entry * (1 + stopLossPercent);
    takeProfit = entry * (1 - stopLossPercent * config.TP_MULTIPLIERS[2]);
  }
  
  const position = {
    symbol,
    direction,
    entry,
    size,
    stopLoss,
    takeProfit,
    confidence,
    openedAt: Date.now(),
    status: 'OPEN'
  };
  
  activePositions.set(symbol, position);
  
  return position;
}

export function closePosition(symbol, reason, pnl = 0) {
  const pos = activePositions.get(symbol);
  if (!pos) return null;
  
  pos.status = 'CLOSED';
  pos.closedAt = Date.now();
  pos.closeReason = reason;
  pos.pnl = pnl;
  
  activePositions.delete(symbol);
  
  return pos;
}

export function getPosition(symbol) {
  return activePositions.get(symbol);
}

export function getActivePositions() {
  return Array.from(activePositions.values());
}

export function updatePosition(symbol, updates) {
  const pos = activePositions.get(symbol);
  if (!pos) return null;
  
  Object.assign(pos, updates);
  return pos;
}

export function checkTP(symbol, currentPrice) {
  const pos = activePositions.get(symbol);
  if (!pos || pos.status !== 'OPEN') return null;
  
  if (pos.direction === 'LONG' && currentPrice >= pos.takeProfit) {
    return 'TP';
  }
  
  if (pos.direction === 'SHORT' && currentPrice <= pos.takeProfit) {
    return 'TP';
  }
  
  if (pos.direction === 'LONG' && currentPrice <= pos.stopLoss) {
    return 'SL';
  }
  
  if (pos.direction === 'SHORT' && currentPrice >= pos.stopLoss) {
    return 'SL';
  }
  
  return null;
}
